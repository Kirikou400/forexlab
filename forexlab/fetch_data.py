"""Download candles from Twelve Data into the local database.
Usage:  python -m forexlab.fetch_data
        python -m forexlab.fetch_data --symbols EUR/USD --timeframes 1h --bars 3000"""
import argparse
import os
import sys

from dotenv import load_dotenv

from .candles import drop_unclosed
from .config import DEFAULT_BARS, PAIRS, ROOT, TIMEFRAMES
from .db import upsert_candles
from .twelvedata import fetch_history


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbols", nargs="*", default=list(PAIRS))
    ap.add_argument("--timeframes", nargs="*", default=list(TIMEFRAMES))
    ap.add_argument("--bars", type=int, default=None,
                    help="candles per symbol/timeframe (default depends on timeframe)")
    args = ap.parse_args(argv)

    load_dotenv(ROOT / ".env")
    key = os.getenv("TWELVEDATA_API_KEY")
    if not key or key == "your_key_here":
        sys.exit("No API key found. Copy .env.example to .env and paste your Twelve Data key.")

    for sym in args.symbols:
        for tf in args.timeframes:
            target = args.bars or DEFAULT_BARS[tf]
            print(f"Fetching {sym} {tf} (target {target} candles)...")
            try:
                df = fetch_history(sym, tf, key, target)
            except Exception as e:  # keep going with the other pairs
                print(f"  FAILED: {e}")
                continue
            df = drop_unclosed(df, tf)
            n = upsert_candles(df, sym, tf, "twelvedata")
            if n:
                print(f"  saved {n} candles: {df.index.min()} -> {df.index.max()}")
            else:
                print("  nothing saved")
    print("Done. Next: python -m forexlab.check_data")


if __name__ == "__main__":
    main()
