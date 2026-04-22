# Finalto — Risk Management Dashboard

A real-time MVP risk management dashboard for FX/commodity book management.
Simulates market data streaming, client trading activity, and presents live
risk metrics in an interactive web UI.

**Stack:** Django 5 backend · Plotly.js frontend · pure in-memory simulation

---

## Quick start

```bash
# 1. Clone and enter the repo
git clone <repo-url>
cd fintech-dashboard

# 2. Install dependencies (requires uv ≥ 0.4)
uv sync

# 3. Run
uv run python run.py
```

Open **http://127.0.0.1:8050/** in your browser.

---

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | ≥ 3.10 | https://python.org or `winget install Python.Python.3.11` |
| uv | ≥ 0.4 | https://docs.astral.sh/uv/getting-started/installation/ |

`uv sync` reads `pyproject.toml`, creates an isolated virtual environment
(`.venv/`), and installs all dependencies — no manual pip commands needed.

### Windows notes

- Run commands in **PowerShell** or **CMD** (WSL also works).
- If `uv` is not on your PATH after installation, restart your terminal or
  follow the PATH instructions in the uv installer output.
- `uv run python run.py` activates the venv automatically — no need to call
  `.venv\Scripts\activate` manually.

---

## Command-line options

```
uv run python run.py [--host HOST] [--port PORT] [--reload]

  --host HOST   Bind address  (default: 127.0.0.1)
  --port PORT   Bind port     (default: 8050)
  --reload      Enable Django's file-watcher autoreloader
```

You can also use Django's management command directly:

```bash
uv run python manage.py runserver 127.0.0.1:8050 --noreload
```

---

## Dashboard panels

| Panel | Description |
|-------|-------------|
| **KPI cards** | Total PnL · Spread income · Trade count · Open positions |
| **PnL Over Time** | Running MTM PnL curve with area fill |
| **Net Positions** | Long/short exposure in lots per instrument |
| **PnL Attribution** | Per-instrument contribution to total PnL |
| **Client Yield** | Per-client PnL attribution |
| **Spread Income** | Cumulative bid-ask spread monetisation |
| **Live Price Feed** | Current bid/mid/ask and spread in pips |
| **Recent Trades** | Last 20 trades with client, direction, size, price, spread earned |

All Plotly charts support interactive hover tooltips (timestamp + value).

---

## Architecture

```
Django dev server (main process)
  │
  ├── SimulationConfig.ready()       ← called once on startup
  │     ├── DataStore                  thread-safe shared state (RLock + deques)
  │     ├── MarketDataStreamer [daemon] random-walk prices → DataStore every 100 ms
  │     ├── TradingEngine     [daemon] client trades       → DataStore every 500 ms
  │     └── RiskEngine        [daemon] MTM PnL snapshot    → DataStore every 1 s
  │
  ├── GET /                          renders dashboard/index.html
  │
  └── GET /api/data/                 JSON snapshot of all simulation state
        ↑ polled every 1 s by the browser's setInterval()
```

### Why Django?

Django provides a clean application boundary between the simulation engine
(the `simulation` Django app) and the presentation layer (the `dashboard` app).
`AppConfig.ready()` is the standard Django hook for process-startup work —
exactly what is needed to launch background threads before the first request.

### Why polling instead of WebSockets?

For 1-second UI refresh intervals, a simple `GET /api/data/` fetch is:
- Easier to debug (visible in the browser's Network tab)
- No extra dependencies (no channels, no Redis)
- Stateless and trivially scalable

WebSockets would be the right upgrade if sub-second latency becomes a
requirement.

### Scalability

`src/config.py` contains a commented-out **10× scale preset**:

```python
# TRADE_PROBABILITY = 1.0
# PRICE_TICK_INTERVAL = 0.01
# DASHBOARD_REFRESH_MS = 2_000
```

Uncommenting these raises the simulation to ~60 trades/sec and 100 price
ticks/sec.  Increasing `DASHBOARD_REFRESH_MS` throttles the UI independently
of data generation so the browser stays responsive.

---

## Project layout

```
simple-risk-dashboard/
├── pyproject.toml              # uv project — deps: django, numpy, pandas
├── .python-version             # Python ≥ 3.10
├── manage.py                   # Standard Django management entry point
├── run.py                      # Convenience launcher (wraps manage.py)
├── README.md
│
├── fintech/                    # Django project package
│   ├── settings.py             # App settings (no DB, minimal middleware)
│   ├── urls.py                 # Root URL conf → dashboard.urls
│   └── wsgi.py                 # WSGI callable for production deployment
│
├── simulation/                 # Django app — simulation engine
│   ├── apps.py                 # SimulationConfig.ready() starts threads
│   ├── state.py                # Module-level DataStore + RiskEngine singletons
│   ├── config.py               # Instruments, clients, simulation parameters
│   ├── data_store.py           # Thread-safe shared state (RLock + deques)
│   ├── streamer.py             # Market data price simulator
│   ├── trading_engine.py       # Client trade simulator + book updater
│   └── risk_engine.py          # MTM PnL and risk metric calculations
│
└── dashboard/                  # Django app — UI + JSON API
    ├── apps.py
    ├── urls.py                 # / → index, /api/data/ → api_data
    ├── views.py                # index view + api_data JSON view
    └── templates/
        └── dashboard/
            └── index.html      # Single-page dashboard (Bootstrap 5 + Plotly.js)
```

---

## Dependencies

Managed entirely by `uv sync` from `pyproject.toml`:

| Package | Purpose |
|---------|---------|
| `django` | Web framework, routing, templating, dev server |
| `numpy` | Gaussian random-walk price generation |
| `pandas` | Available for future data analysis extensions |

Plotly.js and Bootstrap 5 are loaded from CDN in the HTML template — no
Node.js or npm build step required.
