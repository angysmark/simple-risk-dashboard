"""
Market data streamer.

Runs in its own daemon thread.  On every tick it advances each instrument's
mid price by a Gaussian random walk, then derives bid/ask from the configured
half-spread and writes the result into the shared DataStore.

Random walk model
-----------------
  mid[t] = mid[t-1] + N(0, σ)

where σ = InstrumentConfig.volatility (per tick, not annualised).

Thread safety
-------------
All writes go through DataStore.update_price(), which holds the store's lock.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

import numpy as np

from simulation.config import INSTRUMENTS, PRICE_TICK_INTERVAL
from simulation.data_store import DataStore, PriceTick


class MarketDataStreamer(threading.Thread):
    """
    Background thread that continuously streams bid/ask prices for all
    configured instruments into *store*.
    """

    def __init__(self, store: DataStore) -> None:
        super().__init__(name="MarketDataStreamer", daemon=True)
        self._store = store
        self._stop_event = threading.Event()

        # Initialise mid prices from config (mutable working copy per thread)
        self._mids: dict[str, float] = {
            sym: cfg.initial_price for sym, cfg in INSTRUMENTS.items()
        }
        self._rng = np.random.default_rng()

    def stop(self) -> None:
        """Signal the thread to exit cleanly."""
        self._stop_event.set()

    def run(self) -> None:
        while not self._stop_event.is_set():
            tick_start = time.monotonic()

            now = datetime.now(tz=timezone.utc)
            for sym, cfg in INSTRUMENTS.items():
                self._mids[sym] += self._rng.normal(0.0, cfg.volatility)
                self._mids[sym] = max(self._mids[sym], cfg.half_spread * 2 + 1e-6)

                mid = self._mids[sym]
                tick = PriceTick(
                    timestamp=now,
                    symbol=sym,
                    mid=mid,
                    bid=mid - cfg.half_spread,
                    ask=mid + cfg.half_spread,
                )
                self._store.update_price(tick)

            elapsed = time.monotonic() - tick_start
            sleep_for = max(0.0, PRICE_TICK_INTERVAL - elapsed)
            self._stop_event.wait(timeout=sleep_for)
