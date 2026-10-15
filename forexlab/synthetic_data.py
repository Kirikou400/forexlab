"""Generate realistic sample forex market candles for local exploration without an API key.

Usage:
    python -m forexlab.synthetic_data
"""
import argparse
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .candles import drop_unclosed
from .config import PAIRS, ROOT, TIMEFRAMES
from .db import upsert_candles

START_PRICES = {
    "EUR/USD": 1.0850,
    "GBP/USD": 1.2950,
    "USD/JPY": 152.40,
    "AUD/USD": 0.6550,
}

FREQ_MAP = {
    "15min": "15min",
    "1h": "1h",
    "4h": "4h",
}


def make_market_series(symbol: str, timeframe: str, n: int = 600, seed: int = 42) -> pd.DataFrame:
    """Generate realistic OHLCV candle series ending at the current closed hour."""
    rng = np.random.default_rng(seed)
    start_price = START_PRICES.get(symbol, 1.1000)
    sigma = 0.0003 if timeframe == "15min" else (0.0007 if timeframe == "1h" else 0.0015)
    pip = PAIRS.get(symbol, {}).get("pip", 0.0001)

    # Autoregressive / regime drift with mean reversion
    returns = rng.normal(0, sigma, n)
    # Add minor cyclical waves to trigger technical indicator crossovers naturally
    t = np.linspace(0, 16 * np.pi, n)
    cycle = np.sin(t) * sigma * 0.4
    total_returns = returns + cycle

    price_path = start_price * np.exp(np.cumsum(total_returns))
    close = price_path
    open_ = np.concatenate([[start_price], close[:-1]])

    # Realistic wicks
    wick_up = np.abs(rng.normal(0, sigma * 0.6, n)) * close
    wick_dn = np.abs(rng.normal(0, sigma * 0.6, n)) * close
    high = np.maximum(open_, close) + wick_up
    low = np.minimum(open_, close) - wick_dn

    # Ensure high >= low and valid ranges
    high = np.maximum(high, np.maximum(open_, close) + pip * 0.5)
    low = np.minimum(low, np.minimum(open_, close) - pip * 0.5)

    # Realistic volume
    volume = np.maximum(50, rng.normal(1200, 300, n)).astype(int)

    # Generate dates backwards from now, aligned to timeframe
    now = pd.Timestamp.now(tz="UTC").floor(timeframe)
    idx = pd.date_range(end=now, periods=n, freq=FREQ_MAP[timeframe], tz="UTC", name="ts")

    df = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )
    return df


def load_demo_data(symbols=None, timeframes=None, n=600, db_path=None):
    """Seed SQLite database with clean sample market data across requested symbols & timeframes."""
    symbols = symbols or list(PAIRS)
    timeframes = timeframes or list(TIMEFRAMES)
    total_saved = 0
    seed_base = 100

    for s_idx, sym in enumerate(symbols):
        for tf_idx, tf in enumerate(timeframes):
            seed = seed_base + s_idx * 10 + tf_idx
            df = make_market_series(sym, tf, n=n, seed=seed)
            df = drop_unclosed(df, tf)
            saved = upsert_candles(df, sym, tf, "demo", db_path=db_path)
            total_saved += saved

    return total_saved


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", nargs="*", default=list(PAIRS))
    parser.add_argument("--timeframes", nargs="*", default=list(TIMEFRAMES))
    parser.add_argument("--bars", type=int, default=600)
    args = parser.parse_args(argv)

    print(f"Generating sample data for {args.symbols} on {args.timeframes} ({args.bars} bars each)...")
    count = load_demo_data(args.symbols, args.timeframes, n=args.bars)
    print(f"Successfully loaded {count} demo candles into SQLite database.")
    print("You can now open the dashboard or run backtests without an external API key!")


if __name__ == "__main__":
    main()
