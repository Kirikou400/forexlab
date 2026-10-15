"""Rule-based strategies. Each returns a DataFrame with:
    direction : +1 buy, -1 sell, 0 nothing  (decided at the CLOSE of bar t)
    sl_dist   : stop-loss distance in price units
The engine enters at the OPEN of bar t+1. Strategies never see future bars.

These two are deliberately simple, classic baselines. The point of Step 1 is
to measure honestly, not to claim they are profitable (they probably are not)."""
import numpy as np
import pandas as pd

from .indicators import atr, donchian_high, donchian_low, ema, rsi, sma


def ema_cross(df, fast=20, slow=50, atr_n=14, atr_mult=2.0) -> pd.DataFrame:
    f, s = ema(df["close"], int(fast)), ema(df["close"], int(slow))
    up = (f > s) & (f.shift(1) <= s.shift(1))
    dn = (f < s) & (f.shift(1) >= s.shift(1))
    a = atr(df["high"], df["low"], df["close"], int(atr_n))
    return pd.DataFrame({"direction": np.select([up, dn], [1, -1], 0),
                         "sl_dist": a * atr_mult}, index=df.index)


def donchian(df, n=20, atr_n=14, atr_mult=2.0) -> pd.DataFrame:
    hi, lo = donchian_high(df["high"], int(n)), donchian_low(df["low"], int(n))
    brk_up, brk_dn = df["close"] > hi, df["close"] < lo
    up = brk_up & ~brk_up.shift(1, fill_value=False)   # first bar of a breakout only
    dn = brk_dn & ~brk_dn.shift(1, fill_value=False)
    a = atr(df["high"], df["low"], df["close"], int(atr_n))
    return pd.DataFrame({"direction": np.select([up, dn], [1, -1], 0),
                         "sl_dist": a * atr_mult}, index=df.index)


def sma_cross(df, fast=20, slow=50, atr_n=14, atr_mult=2.0) -> pd.DataFrame:
    f, s = sma(df["close"], int(fast)), sma(df["close"], int(slow))
    up = (f > s) & (f.shift(1) <= s.shift(1))
    dn = (f < s) & (f.shift(1) >= s.shift(1))
    a = atr(df["high"], df["low"], df["close"], int(atr_n))
    return pd.DataFrame({"direction": np.select([up, dn], [1, -1], 0),
                         "sl_dist": a * atr_mult}, index=df.index)


def rsi_reversal(df, n=14, oversold=30, overbought=70,
                 atr_n=14, atr_mult=2.0) -> pd.DataFrame:
    value = rsi(df["close"], int(n))
    up = (value > oversold) & (value.shift(1) <= oversold)
    dn = (value < overbought) & (value.shift(1) >= overbought)
    a = atr(df["high"], df["low"], df["close"], int(atr_n))
    return pd.DataFrame({"direction": np.select([up, dn], [1, -1], 0),
                         "sl_dist": a * atr_mult}, index=df.index)


def macd_cross(df, fast=12, slow=26, signal=9, atr_n=14,
               atr_mult=2.0) -> pd.DataFrame:
    line = ema(df["close"], int(fast)) - ema(df["close"], int(slow))
    signal_line = ema(line, int(signal))
    up = (line > signal_line) & (line.shift(1) <= signal_line.shift(1))
    dn = (line < signal_line) & (line.shift(1) >= signal_line.shift(1))
    a = atr(df["high"], df["low"], df["close"], int(atr_n))
    return pd.DataFrame({"direction": np.select([up, dn], [1, -1], 0),
                         "sl_dist": a * atr_mult}, index=df.index)


REGISTRY = {
    "ema_cross": ema_cross,
    "donchian": donchian,
    "sma_cross": sma_cross,
    "rsi_reversal": rsi_reversal,
    "macd_cross": macd_cross,
}


def parse_params(text: str) -> dict:
    """'fast=10,slow=30,atr_mult=2.5' -> {'fast': 10, 'slow': 30, 'atr_mult': 2.5}"""
    out = {}
    if not text:
        return out
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise ValueError(f"Invalid parameter item '{part}': expected 'key=value'")
        k, v = part.split("=", 1)
        k = k.strip()
        v = v.strip()
        try:
            val_float = float(v)
            out[k] = int(val_float) if val_float.is_integer() else val_float
        except ValueError as exc:
            raise ValueError(f"Invalid parameter value '{v}' for '{k}': must be numeric") from exc
    return out
