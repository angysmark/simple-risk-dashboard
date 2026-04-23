"""
SimulationConfig — Django AppConfig that bootstraps the simulation engine.

Thread startup in ready()
--------------------------
Django calls AppConfig.ready() once the application registry is fully
populated, before the first request is served.  We use this hook to start
the SimulationLoop daemon thread so it is running by the time any HTTP
request arrives.

Autoreloader guard
------------------
Django's development server runs ready() in *both* the file-watcher process
and the main worker process.  Starting a thread in the watcher process wastes
resources and creates orphaned threads.  We guard with a module-level
``_started`` flag which is process-local, so the first call in each process
wins and subsequent calls are no-ops.
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
        from simulation.simulator import SimulationLoop
        import simulation.state as state

        logger.info("Initialising shared data store…")
        state.store = DataStore()

        logger.info("Starting SimulationLoop…")
        loop = SimulationLoop(state.store)
        loop.start()

        logger.info("Simulation running.")
