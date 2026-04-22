"""
Dashboard views.

index()     — serves the single-page HTML dashboard
api_data()  — JSON endpoint consumed by the frontend every second

The JSON response is self-contained: it carries everything the frontend needs
so the browser makes exactly one request per refresh cycle.
"""

from __future__ import annotations

import logging

from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpRequest, JsonResponse
from django.shortcuts import render

import simulation.state as state
from simulation.config import DASHBOARD_REFRESH_MS, INSTRUMENTS

logger = logging.getLogger(__name__)


def index(request: HttpRequest):
    """Render the single-page dashboard shell."""
    return render(request, "dashboard/index.html", {"refresh_ms": DASHBOARD_REFRESH_MS})


def api_data(request: HttpRequest) -> JsonResponse:
    """
    Return a full snapshot of simulation state as JSON.

    Shape
    -----
    {
      "kpis": {total_pnl_usd, spread_income_usd, trade_count, open_positions},
      "pnl_history":           [{"t": ISO-8601, "v": float}, ...],
      "spread_income_history": [{"t": ISO-8601, "v": float}, ...],
      "positions":   {"EUR/USD": {"net_lots": float, "avg_entry": float}, ...},
      "instrument_pnl": {"EUR/USD": float, ...},
      "client_pnl":     {"Alpha Capital": float, ...},
      "prices": {
          "EUR/USD": {"bid": float, "mid": float, "ask": float, "spread_pts": float},
          ...
      },
      "recent_trades": [
          {"time": "HH:MM:SS", "client": str, "symbol": str, "side": str,
           "lots": float, "price": float, "spread_income": float},
          ...  (most-recent first, up to 20)
      ]
    }
    """
    if state.store is None or state.risk_engine is None:
        # Very early request before simulation is up (rare race at startup)
        return JsonResponse({"error": "simulation not ready"}, status=503)

    snap = state.store.snapshot()
    metrics = state.risk_engine.latest_metrics()

    # --- KPIs ---
    open_positions = sum(1 for b in snap.book.values() if abs(b.net_lots) > 1e-6)
    kpis = {
        "total_pnl_usd": round(metrics.total_pnl_usd, 2),
        "spread_income_usd": round(snap.cumulative_spread_income_usd, 2),
        "trade_count": len(snap.trade_history),
        "open_positions": open_positions,
    }

    # --- Time series ---
    pnl_history = [
        {"t": ts.isoformat(), "v": round(v, 2)}
        for ts, v in snap.pnl_history
    ]
    spread_income_history = [
        {"t": ts.isoformat(), "v": round(v, 2)}
        for ts, v in snap.spread_income_history
    ]

    # --- Positions ---
    positions = {
        sym: {
            "net_lots": round(b.net_lots, 4),
            "avg_entry": round(b.avg_entry_price, 6),
        }
        for sym, b in snap.book.items()
    }

    # --- PnL attribution ---
    instrument_pnl = {
        sym: round(v, 2)
        for sym, v in metrics.per_instrument_pnl_usd.items()
    }
    client_pnl = {
        client: round(v, 2)
        for client, v in metrics.per_client_pnl_usd.items()
    }

    # --- Live prices ---
    prices = {}
    for sym, cfg in INSTRUMENTS.items():
        tick = snap.latest_prices.get(sym)
        if tick:
            spread_pts = round(cfg.half_spread * 2 / _pip_size(sym), 1)
            prices[sym] = {
                "bid": round(tick.bid, _price_decimals(sym)),
                "mid": round(tick.mid, _price_decimals(sym)),
                "ask": round(tick.ask, _price_decimals(sym)),
                "spread_pts": spread_pts,
                "updated": tick.timestamp.strftime("%H:%M:%S"),
            }

    # --- Recent trades (newest first, max 20) ---
    recent_trades = [
        {
            "time": t.timestamp.strftime("%H:%M:%S"),
            "client": t.client,
            "symbol": t.symbol,
            "side": t.side,
            "lots": t.lots,
            "price": round(t.price, _price_decimals(t.symbol)),
            "spread_income": round(t.spread_income, 2),
        }
        for t in reversed(list(snap.trade_history))
    ][:20]

    payload = {
        "kpis": kpis,
        "pnl_history": pnl_history,
        "spread_income_history": spread_income_history,
        "positions": positions,
        "instrument_pnl": instrument_pnl,
        "client_pnl": client_pnl,
        "prices": prices,
        "recent_trades": recent_trades,
    }

    return JsonResponse(payload, encoder=DjangoJSONEncoder)


# ---------------------------------------------------------------------------
# Formatting helpers (mirrors dashboard.py from the old Dash version)
# ---------------------------------------------------------------------------

def _price_decimals(symbol: str) -> int:
    return 2 if symbol in ("USD/JPY", "XAU/USD") else 5


def _pip_size(symbol: str) -> float:
    return 1.0 if symbol in ("USD/JPY", "XAU/USD") else 0.0001
