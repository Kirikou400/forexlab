"""Candle helpers. Convention used everywhere:
   the timestamp of a candle is its OPEN time, in UTC."""
import pandas as pd

TF_SECONDS = {"1min": 60, "5min": 300, "15min": 900, "30min": 1800,
              "1h": 3600, "4h": 14400}


def drop_unclosed(df: pd.DataFrame, timeframe: str, now=None) -> pd.DataFrame:
    """Remove a candle that is still forming. A candle is only usable once
    its full period has elapsed; using a live candle would be look-ahead."""
    now = now if now is not None else pd.Timestamp.now(tz="UTC")
    cutoff = now - pd.Timedelta(seconds=TF_SECONDS[timeframe])
    return df[df.index <= cutoff]


def resample_ohlc(df: pd.DataFrame, target: str, source: str) -> pd.DataFrame:
    """Build bigger candles from smaller ones (e.g. 1min -> 15min/1h/4h).
    The final bucket is dropped if the source data doesn't fully cover it."""
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    if "volume" in df.columns:
        agg["volume"] = "sum"
    g = df.resample(target, label="left", closed="left")
    out = g.agg(agg)
    counts = g["close"].count()
    out = out[counts > 0]
    expected = TF_SECONDS[target] // TF_SECONDS[source]
    if len(out) and counts.loc[out.index[-1]] < expected:
        out = out.iloc[:-1]
    return out.dropna(subset=["open", "high", "low", "close"])
