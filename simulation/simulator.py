"""
Simulation loop — single background thread that advances the entire simulation
on every tick.

Each tick (every SIMULATION_TICK_INTERVAL seconds) the loop runs three phases
in sequence:
  1. _update_prices  — advance each instrument's mid price with a Gaussian
                       random walk, then derive bid/ask from the half-spread.
  2. _generate_trades — for each client/instrument pair, roll a random number
                        against TRADE_PROBABILITY and, on a hit, generate a
                        synthetic trade and update the book.
  3. _calculate_risk  — compute mark-to-market PnL for every instrument and
                        client, store a snapshot in history, and write the
                        latest metrics back to the DataStore.

Having one thread with one sleep interval makes the data flow easy to follow:
prices → trades → risk, all in sequence, once every five seconds.
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
    SIMULATION_TICK_INTERVAL,
    TRADE_PROBABILITY,
)
from simulation.data_store import DataStore, PriceTick, RiskMetrics, Trade


class SimulationLoop(threading.Thread):
    """
    Single daemon thread that drives prices, trades, and risk metrics.
    """

    def __init__(self, store: DataStore) -> None:
        super().__init__(name="SimulationLoop", daemon=True)
        self._store = store
        self._stop_event = threading.Event()
        self._rng = np.random.default_rng()

        # Working copy of mid prices; updated in-place each tick
        self._mids: dict[str, float] = {
            sym: cfg.initial_price for sym, cfg in INSTRUMENTS.items()
        }

    def stop(self) -> None:
        """Signal the thread to exit cleanly after the current tick."""
        self._stop_event.set()

    def run(self) -> None:
        while not self._stop_event.is_set():
            tick_start = time.monotonic()
            self._tick()
            elapsed = time.monotonic() - tick_start
            self._stop_event.wait(timeout=max(0.0, SIMULATION_TICK_INTERVAL - elapsed))

    # ------------------------------------------------------------------
    # Tick phases — called in order each iteration
    # ------------------------------------------------------------------

    def _tick(self) -> None:
        now = datetime.now(tz=timezone.utc)
        self._update_prices(now)
        self._generate_trades(now)
        self._calculate_risk(now)

    def _update_prices(self, now: datetime) -> None:
        """Advance each instrument's mid price by one Gaussian random-walk step."""
        for sym, cfg in INSTRUMENTS.items():
            self._mids[sym] += self._rng.normal(0.0, cfg.volatility)
            # Keep mid above zero (at least twice the half-spread)
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

    def _generate_trades(self, now: datetime) -> None:
        """
        For each client/instrument pair, roll against TRADE_PROBABILITY.
        On a hit, choose a random side and size, respect the net-lots cap,
        then write the trade and book update to the store.
        """
        for client in CLIENTS:
            for sym, cfg in INSTRUMENTS.items():
                if self._rng.random() > TRADE_PROBABILITY:
                    continue

                price_tick = self._store.latest_prices.get(sym)
                if price_tick is None:
                    continue

                side = "BUY" if self._rng.random() < 0.5 else "SELL"
                lots = round(float(self._rng.uniform(MIN_LOTS, MAX_LOTS)), 2)

                # Flip side if adding would breach the net-lots cap
                our_delta = -lots if side == "BUY" else lots
                if abs(self._store.book[sym].net_lots + our_delta) > MAX_NET_LOTS:
                    side = "SELL" if self._store.book[sym].net_lots > 0 else "BUY"

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

    def _calculate_risk(self, now: datetime) -> None:
        """
        Compute MTM PnL for all instruments and clients, write a PnL snapshot
        to history, and update the store's latest metrics.
        """
        snap = self._store.snapshot()

        per_instrument: dict[str, float] = {}
        total = 0.0
        for sym, cfg in INSTRUMENTS.items():
            mid = snap.latest_prices[sym].mid if sym in snap.latest_prices else cfg.initial_price
            pnl = _compute_pnl_usd(snap.book[sym], sym, mid, cfg.lot_size)
            per_instrument[sym] = pnl
            total += pnl

        per_client: dict[str, float] = {}
        for client in CLIENTS:
            client_total = 0.0
            for sym, cfg in INSTRUMENTS.items():
                mid = snap.latest_prices[sym].mid if sym in snap.latest_prices else cfg.initial_price
                client_total += _compute_pnl_usd(snap.client_book[client][sym], sym, mid, cfg.lot_size)
            per_client[client] = client_total

        self._store.snapshot_pnl(now, total)
        self._store.update_metrics(RiskMetrics(
            total_pnl_usd=total,
            per_instrument_pnl_usd=per_instrument,
            per_client_pnl_usd=per_client,
        ))


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _to_usd(amount_quote: float, symbol: str, mid: float) -> float:
    """Convert an amount in the instrument's quote currency to USD."""
    if symbol in ("USD/JPY", "USD/CHF"):
        return amount_quote / mid if mid > 0 else 0.0
    return amount_quote


def _compute_pnl_usd(entry, symbol: str, mid: float, lot_size: float) -> float:
    """Mark-to-market PnL in USD for a single book entry."""
    if entry.net_lots == 0.0 and entry.realised_pnl_usd == 0.0:
        return 0.0
    unrealised_quote = entry.net_lots * lot_size * (mid - entry.avg_entry_price)
    if symbol in ("USD/JPY", "USD/CHF"):
        unrealised_usd = unrealised_quote / mid if mid > 0 else 0.0
    else:
        unrealised_usd = unrealised_quote
    return entry.realised_pnl_usd + unrealised_usd
