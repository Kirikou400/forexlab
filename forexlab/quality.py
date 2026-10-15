"""Data-quality checks. Bad data silently produces fake backtest results,
so run these before trusting any number."""
import numpy as np
import pandas as pd

from .candles import TF_SECONDS


def check_candles(df: pd.DataFrame, timeframe: str) -> dict:
    tf = pd.Timedelta(seconds=TF_SECONDS[timeframe])
    out = {"bars": len(df)}
    if df.empty:
        return out
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    bad = (h < np.maximum(o, c)) | (l > np.minimum(o, c)) | (h < l) | (df[["open", "high", "low", "close"]] <= 0).any(axis=1)
    out["invalid_ohlc"] = int(bad.sum())
    out["zero_range_bars"] = int((h == l).sum())

    # Gaps: weekend closes (Fri -> Sun/Mon) are normal; anything else is suspicious.
    idx = df.index.to_series()
    diffs = idx.diff()
    big = diffs[diffs > tf]
    unexpected = []
    for nxt, d in big.items():
        prev = nxt - d
        weekend = prev.weekday() == 4 and nxt.weekday() in (6, 0) and d <= pd.Timedelta(days=3)
        if not weekend:
            unexpected.append((prev, nxt))
    out["unexpected_gaps"] = len(unexpected)
    out["gap_examples"] = [f"{a:%Y-%m-%d %H:%M} -> {b:%Y-%m-%d %H:%M}" for a, b in unexpected[:3]]

    # A single bar moving >1.5% is extremely rare in these majors: likely a bad tick.
    move = (c / o - 1).abs()
    out["suspicious_moves"] = int((move > 0.015).sum())
    out["first"], out["last"] = df.index.min(), df.index.max()
    out["hours_since_last"] = round((pd.Timestamp.now(tz="UTC") - df.index.max()).total_seconds() / 3600, 1)
    return out
