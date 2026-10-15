"""Central settings. Everything here is an ASSUMPTION you can change."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "forexlab.db"
RESULTS_DIR = ROOT / "results"

# pip = size of one pip in price units.
# spread_pips = assumed typical retail spread. REPLACE THESE with your own
# broker's real spreads. Spreads widen a lot around news and at rollover,
# so backtests using a fixed spread are optimistic.
PAIRS = {
    "EUR/USD": {"pip": 0.0001, "spread_pips": 0.8},
    "GBP/USD": {"pip": 0.0001, "spread_pips": 1.2},
    "USD/JPY": {"pip": 0.01,   "spread_pips": 1.0},
    "AUD/USD": {"pip": 0.0001, "spread_pips": 1.2},
}

# Adverse slippage (pips) applied on market entries and on stop-loss exits.
SLIPPAGE_PIPS = 0.3

# Timeframes used by the app (seconds per candle).
TIMEFRAMES = {"15min": 900, "1h": 3600, "4h": 14400}

# Default history to request from the data provider (number of candles).
DEFAULT_BARS = {"15min": 35000, "1h": 15000, "4h": 5000}


def costs_for(symbol: str):
    """Return (full_spread, slippage) in PRICE units for a symbol."""
    p = PAIRS[symbol]
    return p["spread_pips"] * p["pip"], SLIPPAGE_PIPS * p["pip"]
