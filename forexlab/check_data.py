"""Print a data-quality report for everything in the database.
Usage: python -m forexlab.check_data"""
from .db import list_datasets, load_candles
from .quality import check_candles


def main():
    sets = list_datasets()
    if not sets:
        print("Database is empty. Run: python -m forexlab.fetch_data")
        return
    for symbol, tf, sources in sets:
        r = check_candles(load_candles(symbol, tf), tf)
        print(f"\n{symbol} {tf}  [source: {sources}]")
        print(f"  bars: {r['bars']}   range: {r['first']:%Y-%m-%d} -> {r['last']:%Y-%m-%d}")
        print(f"  invalid OHLC: {r['invalid_ohlc']}   zero-range bars: {r['zero_range_bars']}   "
              f"suspicious moves: {r['suspicious_moves']}")
        print(f"  unexpected gaps: {r['unexpected_gaps']}  {r['gap_examples']}")
        print(f"  age of newest candle: {r['hours_since_last']} hours")
        if "," in (sources or ""):
            print("  WARNING: mixed data sources. Candle boundaries may differ. Prefer one source per dataset.")
        if r["invalid_ohlc"]:
            print("  WARNING: invalid candles found. Do not trust backtests on this data until fixed.")


if __name__ == "__main__":
    main()
