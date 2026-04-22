"""
Risk engine — computes mark-to-market PnL and related risk metrics.

Runs in its own daemon thread.  See src/risk_engine.py for the full
design rationale; this file only updates the import paths for Django.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from simulation.config import CLIENTS, INSTRUMENTS
from simulation.data_store import DataStore, InstrumentBook

RISK_CALC_INTERVAL: float = 1.0


@dataclass
class RiskMetrics:
    total_pnl_usd: float = 0.0
    per_instrument_pnl_usd: dict[str, float] = field(default_factory=dict)
    per_client_pnl_usd: dict[str, float] = field(default_factory=dict)


class RiskEngine(threading.Thread):
    """
    Background thread that periodically recalculates risk metrics and
    snapshots the total PnL into the DataStore's history buffers.
    """

    def __init__(self, store: DataStore) -> None:
        super().__init__(name="RiskEngine", daemon=True)
        self._store = store
        self._stop_event = threading.Event()
        self._metrics = RiskMetrics()
        self._metrics_lock = threading.Lock()

    def stop(self) -> None:
        self._stop_event.set()

    def latest_metrics(self) -> RiskMetrics:
        with self._metrics_lock:
            return RiskMetrics(
                total_pnl_usd=self._metrics.total_pnl_usd,
                per_instrument_pnl_usd=dict(self._metrics.per_instrument_pnl_usd),
                per_client_pnl_usd=dict(self._metrics.per_client_pnl_usd),
            )

    def run(self) -> None:
        while not self._stop_event.is_set():
            tick_start = time.monotonic()
            self._recalculate()
            elapsed = time.monotonic() - tick_start
            self._stop_event.wait(timeout=max(0.0, RISK_CALC_INTERVAL - elapsed))

    def _recalculate(self) -> None:
        from datetime import datetime, timezone

        snap = self._store.snapshot()
        now = datetime.now(tz=timezone.utc)

        per_instrument: dict[str, float] = {}
        total = 0.0

        for sym, cfg in INSTRUMENTS.items():
            book_entry = snap.book[sym]
            mid = snap.latest_prices[sym].mid if sym in snap.latest_prices else cfg.initial_price
            pnl = _compute_pnl_usd(book_entry, sym, mid, cfg.lot_size)
            per_instrument[sym] = pnl
            total += pnl

        per_client: dict[str, float] = {}
        for client in CLIENTS:
            client_total = 0.0
            for sym, cfg in INSTRUMENTS.items():
                client_entry = snap.client_book[client][sym]
                mid = snap.latest_prices[sym].mid if sym in snap.latest_prices else cfg.initial_price
                client_total += _compute_pnl_usd(client_entry, sym, mid, cfg.lot_size)
            per_client[client] = client_total

        self._store.snapshot_pnl(now, total)

        with self._metrics_lock:
            self._metrics.total_pnl_usd = total
            self._metrics.per_instrument_pnl_usd = per_instrument
            self._metrics.per_client_pnl_usd = per_client


def _compute_pnl_usd(
    entry: InstrumentBook,
    symbol: str,
    mid: float,
    lot_size: float,
) -> float:
    if entry.net_lots == 0.0 and entry.realised_pnl_usd == 0.0:
        return 0.0

    unrealised_quote = entry.net_lots * lot_size * (mid - entry.avg_entry_price)

    if symbol in ("USD/JPY", "USD/CHF"):
        unrealised_usd = unrealised_quote / mid if mid > 0 else 0.0
    else:
        unrealised_usd = unrealised_quote

    return entry.realised_pnl_usd + unrealised_usd
