"""
Configuration: instruments, clients, and simulation parameters.

All tuneable knobs live here so callers never need to hard-code values.
"""
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Instrument definitions
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class InstrumentConfig:
    symbol: str
    initial_price: float   # Starting mid price
    half_spread: float     # Half-spread applied symmetrically to mid
    volatility: float      # Per-tick σ for the Gaussian random walk on mid
    lot_size: float        # Units of base currency per 1 lot
    quote_currency: str    # Quote currency (used for PnL conversion to USD)


# FX majors + Gold.  Spreads and vol are illustrative, not live-market data.
INSTRUMENTS: dict[str, InstrumentConfig] = {
    "EUR/USD": InstrumentConfig("EUR/USD", 1.0850, 0.00005, 0.00025, 100_000, "USD"),
    "GBP/USD": InstrumentConfig("GBP/USD", 1.2650, 0.00008, 0.00035, 100_000, "USD"),
    "USD/JPY": InstrumentConfig("USD/JPY", 149.50,  0.010,   0.040,  100_000, "JPY"),
    "USD/CHF": InstrumentConfig("USD/CHF",   0.905, 0.00008, 0.00030, 100_000, "CHF"),
    "AUD/USD": InstrumentConfig("AUD/USD",   0.655, 0.00007, 0.00025, 100_000, "USD"),
    "XAU/USD": InstrumentConfig("XAU/USD", 2350.0,   0.25,    0.80,       1, "USD"),
}

# ---------------------------------------------------------------------------
# Simulated clients
# ---------------------------------------------------------------------------

CLIENTS: list[str] = [
    "Alpha Capital",
    "Beta Trading",
    "Gamma Fund",
    "Delta Partners",
    "Epsilon Hedge",
]

# ---------------------------------------------------------------------------
# Simulation parameters  (tweak these to stress-test the system)
# ---------------------------------------------------------------------------

# How often the price streamer ticks (seconds).
# Lower → more ticks → higher CPU / memory pressure.
PRICE_TICK_INTERVAL: float = 5.0   # 1 tick per instrument every 5 s

# How often the trading engine fires (seconds).
TRADE_CHECK_INTERVAL: float = 0.5  # 2 checks/sec per client/instrument

# Probability that a given client places a trade on any given check.
# Scale: 5 clients × 6 instruments × 1 check/5 s × 0.10 prob ≈ 0.6 trades/5 s.
TRADE_PROBABILITY: float = 0.10

# Trade size bounds (lots).
MIN_LOTS: float = 0.10
MAX_LOTS: float = 3.00

# Hard cap on lots per instrument to prevent the book from growing unbounded
# in a long-running simulation.
MAX_NET_LOTS: float = 50.0

# How many data points to keep in rolling history buffers (per series).
MAX_HISTORY_POINTS: int = 500

# Dash UI refresh rate (milliseconds).  1 000 ms ≈ real-time for human eyes.
DASHBOARD_REFRESH_MS: int = 5_000

# ---------------------------------------------------------------------------
# 10× scale preset — swap in to stress-test scalability
# ---------------------------------------------------------------------------
# TRADE_PROBABILITY = 1.0
# PRICE_TICK_INTERVAL = 0.01
# DASHBOARD_REFRESH_MS = 2_000   # throttle UI when data is very dense
