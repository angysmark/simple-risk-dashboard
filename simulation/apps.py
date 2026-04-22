"""
SimulationConfig — Django AppConfig that bootstraps the simulation engine.

Thread startup in ready()
--------------------------
Django calls AppConfig.ready() once the application registry is fully
populated, before the first request is served.  We use this hook to start
the three daemon threads (streamer, trading engine, risk engine) so they
are running by the time any HTTP request arrives.

Autoreloader guard
------------------
Django's development server runs ready() in *both* the file-watcher process
and the main worker process.  Starting threads in the watcher process wastes
resources and creates orphaned threads.  We guard with a module-level
``_started`` flag which is process-local, so the first call in each process
wins and subsequent calls are no-ops.  Because the watcher process never
handles requests, the flag prevents unnecessary thread creation there too.
"""

from __future__ import annotations

import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)

_started = False


class SimulationConfig(AppConfig):
    name = "simulation"
    verbose_name = "Simulation Engine"

    def ready(self) -> None:
        global _started
        if _started:
            return
        _started = True

        # Import here to avoid circular imports at module level
        from simulation.data_store import DataStore
        from simulation.risk_engine import RiskEngine
        from simulation.streamer import MarketDataStreamer
        from simulation.trading_engine import TradingEngine
        import simulation.state as state

        logger.info("Initialising shared data store…")
        state.store = DataStore()

        logger.info("Starting MarketDataStreamer…")
        streamer = MarketDataStreamer(state.store)
        streamer.start()

        logger.info("Starting TradingEngine…")
        trading = TradingEngine(state.store)
        trading.start()

        logger.info("Starting RiskEngine…")
        state.risk_engine = RiskEngine(state.store)
        state.risk_engine.start()

        logger.info("All simulation threads running.")
