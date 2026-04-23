"""
Thread-safe shared data store.

The simulation thread writes here; the Django view thread reads from here.
A single RLock guards every mutation so readers always see a consistent snapshot.

Design choices
--------------
* ``collections.deque`` with ``maxlen`` gives O(1) append and automatic eviction
  of old data — no manual trimming needed.
* We copy-on-read in ``snapshot()`` so the view thread works on stable data while
  the simulation thread continues writing.
* A single coarse-grained lock is simple and correct.  With one writer and one
  reader, contention is negligible.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from simulation.config import CLIENTS, INSTRUMENTS, MAX_HISTORY_POINTS


# ---------------------------------------------------------------------------
# Risk metrics (computed by SimulationLoop._calculate_risk each tick)
# ---------------------------------------------------------------------------

@dataclass
class RiskMetrics:
    total_pnl_usd: float = 0.0
    per_instrument_pnl_usd: dict[str, float] = field(default_factory=dict)
    per_client_pnl_usd: dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Plain-data types (no logic, just structure)
# ---------------------------------------------------------------------------

@dataclass
class PriceTick:
    timestamp: datetime
    symbol: str
    mid: float
    bid: float
    ask: float


@dataclass
class Trade:
    timestamp: datetime
    client: str
    symbol: str
    side: str          # "BUY" or "SELL"  (from the client's perspective)
    lots: float
    price: float       # execution price (ask for client buy, bid for client sell)
    spread_income: float  # half-spread × lot_size × lots, in quote currency


@dataclass
class InstrumentBook:
    """Running book state for one instrument."""
    net_lots: float = 0.0           # positive = long, negative = short
    avg_entry_price: float = 0.0    # volume-weighted average entry price
    realised_pnl_usd: float = 0.0   # locked-in PnL from closing trades


# ---------------------------------------------------------------------------
# The store itself
# ---------------------------------------------------------------------------

class DataStore:
    """Central, thread-safe state container shared by all simulation threads."""

    def __init__(self) -> None:
        self._lock = threading.RLock()

        # Latest price tick per instrument (most-recent only)
        self.latest_prices: dict[str, PriceTick] = {}

        # Rolling price history per instrument
        self.price_history: dict[str, deque[PriceTick]] = {
            sym: deque(maxlen=MAX_HISTORY_POINTS) for sym in INSTRUMENTS
        }

        # Rolling trade log (most-recent N across all instruments/clients)
        self.trade_history: deque[Trade] = deque(maxlen=MAX_HISTORY_POINTS)

        # Book position per instrument
        self.book: dict[str, InstrumentBook] = {
            sym: InstrumentBook() for sym in INSTRUMENTS
        }

        # Per-client book (same structure, tracks each client's contribution)
        self.client_book: dict[str, dict[str, InstrumentBook]] = {
            client: {sym: InstrumentBook() for sym in INSTRUMENTS}
            for client in CLIENTS
        }

        # Rolling total-PnL time series: (timestamp, total_pnl_usd)
        self.pnl_history: deque[tuple[datetime, float]] = deque(
            maxlen=MAX_HISTORY_POINTS
        )

        # Rolling cumulative spread-income time series
        self.spread_income_history: deque[tuple[datetime, float]] = deque(
            maxlen=MAX_HISTORY_POINTS
        )

        # Cumulative spread income (running total, in USD)
        self.cumulative_spread_income_usd: float = 0.0

        # Latest risk metrics (overwritten each tick by the simulation loop)
        self._latest_metrics: RiskMetrics = RiskMetrics()

    # ------------------------------------------------------------------
    # Write helpers (called by simulation threads)
    # ------------------------------------------------------------------

    def update_price(self, tick: PriceTick) -> None:
        with self._lock:
            self.latest_prices[tick.symbol] = tick
            self.price_history[tick.symbol].append(tick)

    def record_trade(self, trade: Trade) -> None:
        with self._lock:
            self.trade_history.append(trade)

    def update_book(
        self,
        symbol: str,
        client: str,
        side: str,
        lots: float,
        price: float,
        spread_income_usd: float,
    ) -> None:
        """
        Apply a trade to the aggregate book and the per-client book.

        Convention:
          client BUY  → we are SHORT → our lots change by -lots
          client SELL → we are LONG  → our lots change by +lots
        """
        with self._lock:
            our_lots = -lots if side == "BUY" else lots
            _update_book_entry(self.book[symbol], our_lots, price)
            _update_book_entry(self.client_book[client][symbol], our_lots, price)
            self.cumulative_spread_income_usd += spread_income_usd

    def snapshot_pnl(self, timestamp: datetime, total_pnl_usd: float) -> None:
        with self._lock:
            self.pnl_history.append((timestamp, total_pnl_usd))
            self.spread_income_history.append(
                (timestamp, self.cumulative_spread_income_usd)
            )

    def update_metrics(self, metrics: RiskMetrics) -> None:
        with self._lock:
            self._latest_metrics = metrics

    # ------------------------------------------------------------------
    # Read helpers (called by Dash callback thread)
    # ------------------------------------------------------------------

    def snapshot(self) -> "_Snapshot":
        """Return a consistent, unlocked copy of all state for the view thread."""
        with self._lock:
            m = self._latest_metrics
            return _Snapshot(
                latest_prices=dict(self.latest_prices),
                price_history={
                    sym: list(h) for sym, h in self.price_history.items()
                },
                trade_history=list(self.trade_history),
                book={sym: _copy_book(b) for sym, b in self.book.items()},
                client_book={
                    client: {sym: _copy_book(b) for sym, b in books.items()}
                    for client, books in self.client_book.items()
                },
                pnl_history=list(self.pnl_history),
                spread_income_history=list(self.spread_income_history),
                cumulative_spread_income_usd=self.cumulative_spread_income_usd,
                metrics=RiskMetrics(
                    total_pnl_usd=m.total_pnl_usd,
                    per_instrument_pnl_usd=dict(m.per_instrument_pnl_usd),
                    per_client_pnl_usd=dict(m.per_client_pnl_usd),
                ),
            )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _update_book_entry(entry: InstrumentBook, delta_lots: float, price: float) -> None:
    """
    Update a book entry with a new delta position.

    Uses VWAP logic: when adding to a position, blend the entry price;
    when reducing/flipping, realise PnL on the closed portion.
    """
    old_lots = entry.net_lots
    new_lots = old_lots + delta_lots

    if old_lots == 0.0:
        # Fresh position
        entry.net_lots = new_lots
        entry.avg_entry_price = price
        return

    same_sign = (old_lots > 0) == (delta_lots > 0)

    if same_sign:
        # Adding to existing position → VWAP
        total = abs(old_lots) + abs(delta_lots)
        entry.avg_entry_price = (
            abs(old_lots) * entry.avg_entry_price + abs(delta_lots) * price
        ) / total
        entry.net_lots = new_lots
    else:
        # Reducing or flipping the position
        closed = min(abs(delta_lots), abs(old_lots))
        pnl_per_lot = (price - entry.avg_entry_price) * (1 if old_lots > 0 else -1)
        entry.realised_pnl_usd += pnl_per_lot * closed
        entry.net_lots = new_lots
        if abs(new_lots) > 1e-9:
            if (new_lots > 0) != (old_lots > 0):
                # Flipped side — new entry price is the current price
                entry.avg_entry_price = price
        else:
            entry.avg_entry_price = 0.0


def _copy_book(b: InstrumentBook) -> InstrumentBook:
    return InstrumentBook(
        net_lots=b.net_lots,
        avg_entry_price=b.avg_entry_price,
        realised_pnl_usd=b.realised_pnl_usd,
    )


@dataclass
class _Snapshot:
    """Immutable snapshot — safe to read without holding the lock."""
    latest_prices: dict[str, PriceTick]
    price_history: dict[str, list[PriceTick]]
    trade_history: list[Trade]
    book: dict[str, InstrumentBook]
    client_book: dict[str, dict[str, InstrumentBook]]
    pnl_history: list[tuple[datetime, float]]
    spread_income_history: list[tuple[datetime, float]]
    cumulative_spread_income_usd: float
    metrics: RiskMetrics
