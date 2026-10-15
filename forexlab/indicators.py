"""Indicators. Every value at bar t uses only data up to and including bar t.
(Tests in tests/test_no_lookahead.py enforce this.)"""
import numpy as np
import pandas as pd


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """Wilder's RSI."""
    d = close.diff()
    gain = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    out = 100 - 100 / (1 + gain / loss)
    return out.where(loss != 0, 100.0).where(gain.notna() & loss.notna())


def true_range(high, low, close) -> pd.Series:
    pc = close.shift(1)
    return pd.concat([high - low, (high - pc).abs(), (low - pc).abs()], axis=1).max(axis=1)


def atr(high, low, close, n: int = 14) -> pd.Series:
    """Wilder's Average True Range, in price units."""
    tr = true_range(high, low, close).where(close.shift(1).notna())
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def donchian_high(high: pd.Series, n: int) -> pd.Series:
    """Highest high of the PREVIOUS n bars (excludes the current bar)."""
    return high.rolling(n, min_periods=n).max().shift(1)


def donchian_low(low: pd.Series, n: int) -> pd.Series:
    return low.rolling(n, min_periods=n).min().shift(1)


def swing_points(high: pd.Series, low: pd.Series, k: int = 3) -> pd.DataFrame:
    """Swing highs/lows (fractals): a bar whose high (low) is the highest
    (lowest) of k bars on each side. A swing at bar i can only be KNOWN at
    bar i+k, so the value is reported at the confirmation bar i+k, never at i.
    Returns swing_high / swing_low (the swing's price, at its confirmation bar)
    plus last_swing_high / last_swing_low (most recent confirmed swing)."""
    w = 2 * k + 1
    centre_high, centre_low = high.shift(k), low.shift(k)
    is_high = (centre_high >= high.rolling(w, min_periods=w).max()) & centre_high.notna()
    is_low = (centre_low <= low.rolling(w, min_periods=w).min()) & centre_low.notna()
    sh = centre_high.where(is_high)
    sl = centre_low.where(is_low)
    return pd.DataFrame({"swing_high": sh, "swing_low": sl,
                         "last_swing_high": sh.ffill(), "last_swing_low": sl.ffill()})
