"""
Trading engine — simulates client activity and updates the book.

Runs in its own daemon thread.  See src/trading_engine.py for the full
design rationale; this file only updates the import paths for Django.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

import numpy as np

from simulation.config import (
    CLIENTS,
    INSTRUMENTS,
    MAX_NET_LOTS,
    MAX_LOTS,
    MIN_LOTS,
    TRADE_CHECK_INTERVAL,
    TRADE_PROBABILITY,
)
from simulation.data_store import DataStore, Trade


class TradingEngine(threading.Thread):
    """
    Background thread that generates synthetic client trades and writes them
    to *store* via the DataStore API.
    """

    def __init__(self, store: DataStore) -> None:
        super().__init__(name="TradingEngine", daemon=True)
        self._store = store
        self._stop_event = threading.Event()
        self._rng = np.random.default_rng()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        # Brief initial delay so the streamer can populate prices first
        self._stop_event.wait(timeout=0.5)

        while not self._stop_event.is_set():
            tick_start = time.monotonic()
            now = datetime.now(tz=timezone.utc)

            for client in CLIENTS:
                for sym, cfg in INSTRUMENTS.items():
                    if self._rng.random() > TRADE_PROBABILITY:
                        continue

                    price_tick = self._store.latest_prices.get(sym)
                    if price_tick is None:
                        continue

                    side = "BUY" if self._rng.random() < 0.5 else "SELL"
                    lots = round(float(self._rng.uniform(MIN_LOTS, MAX_LOTS)), 2)

                    # Respect the net-lots cap to keep the book bounded
                    current_book = self._store.book[sym]
                    our_delta = -lots if side == "BUY" else lots
                    projected_net = current_book.net_lots + our_delta
                    if abs(projected_net) > MAX_NET_LOTS:
                        side = "SELL" if current_book.net_lots > 0 else "BUY"
                        our_delta = -lots if side == "BUY" else lots

                    exec_price = price_tick.ask if side == "BUY" else price_tick.bid

                    spread_income_quote = 2 * cfg.half_spread * cfg.lot_size * lots
                    spread_income_usd = _to_usd(spread_income_quote, sym, price_tick.mid)

                    trade = Trade(
                        timestamp=now,
                        client=client,
                        symbol=sym,
                        side=side,
                        lots=lots,
                        price=exec_price,
                        spread_income=spread_income_usd,
                    )
                    self._store.record_trade(trade)
                    self._store.update_book(sym, client, side, lots, exec_price, spread_income_usd)

            elapsed = time.monotonic() - tick_start
            sleep_for = max(0.0, TRADE_CHECK_INTERVAL - elapsed)
            self._stop_event.wait(timeout=sleep_for)


def _to_usd(amount_quote: float, symbol: str, mid: float) -> float:
    """Convert an amount in the instrument's quote currency to USD."""
    if symbol in ("USD/JPY", "USD/CHF"):
        return amount_quote / mid if mid > 0 else 0.0
    return amount_quote
