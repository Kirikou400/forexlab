"""Import candles from a CSV file (e.g. free historical data from Dukascopy).
You can import 1-minute (or other) data and it will be converted to 15min/1h/4h.

Usage:
  python -m forexlab.csv_import data\\eurusd_1m.csv --symbol EUR/USD ^
      --file-timeframe 1min --store 15min 1h 4h --source dukascopy

Times must be UTC. Use --dayfirst if dates look like 31.01.2024."""
import argparse

import pandas as pd

from .candles import TF_SECONDS, drop_unclosed, resample_ohlc
from .config import TIMEFRAMES
from .db import upsert_candles

TIME_NAMES = ["datetime", "date", "time", "timestamp", "gmt time", "local time", "time (utc)"]


def read_ohlc_csv(path, tz="UTC", dayfirst=False) -> pd.DataFrame:
    raw = pd.read_csv(path)
    cols = {c.strip().lower(): c for c in raw.columns}
    tcol = next((cols[n] for n in TIME_NAMES if n in cols), None)
    if tcol is None:
        raise ValueError(f"No time column found. Columns are: {list(raw.columns)}")
    t = raw[tcol]
    if pd.api.types.is_numeric_dtype(t):
        ts = pd.to_datetime(t, unit="ms" if t.iloc[0] > 1e11 else "s", utc=True)
    else:
        ts = pd.to_datetime(t, dayfirst=dayfirst)
        if ts.dt.tz is None:
            ts = ts.dt.tz_localize(tz, ambiguous="NaT", nonexistent="NaT")
        ts = ts.dt.tz_convert("UTC")
    out = pd.DataFrame(index=pd.DatetimeIndex(ts, name="ts"))
    for name in ("open", "high", "low", "close", "volume"):
        if name in cols:
            out[name] = pd.to_numeric(raw[cols[name]].to_numpy(), errors="coerce")
        elif name != "volume":
            raise ValueError(f"Missing column: {name}")
    out = out[out.index.notna()].sort_index()
    return out[~out.index.duplicated(keep="last")]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("path")
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--file-timeframe", required=True, choices=list(TF_SECONDS))
    ap.add_argument("--store", nargs="*", default=list(TIMEFRAMES))
    ap.add_argument("--source", default="csv")
    ap.add_argument("--tz", default="UTC")
    ap.add_argument("--dayfirst", action="store_true")
    a = ap.parse_args(argv)

    df = read_ohlc_csv(a.path, a.tz, a.dayfirst)
    print(f"Read {len(df)} rows: {df.index.min()} -> {df.index.max()}")
    for tf in a.store:
        if TF_SECONDS[tf] < TF_SECONDS[a.file_timeframe]:
            print(f"  skipping {tf}: finer than the file's data")
            continue
        out = df if tf == a.file_timeframe else resample_ohlc(df, tf, a.file_timeframe)
        out = drop_unclosed(out, tf)
        print(f"  {tf}: saved {upsert_candles(out, a.symbol, tf, a.source)} candles")


if __name__ == "__main__":
    main()
