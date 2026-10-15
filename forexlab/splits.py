"""Chronological data splits. Never shuffle time-series data.
  train      first 50%  : where you explore and build ideas
  validation next 25%   : where you choose between candidate settings
  test       last 25%   : LOCKED. Run once at the very end. Enforced in run_backtest.
Indicators are computed on the full history (they only look backwards), then
each split is traded separately."""
import pandas as pd


def chronological_split(df: pd.DataFrame, train=0.5, validation=0.25) -> dict:
    n = len(df)
    a, b = int(n * train), int(n * (train + validation))
    return {"train": df.iloc[:a], "validation": df.iloc[a:b], "test": df.iloc[b:]}


def rolling_windows(df: pd.DataFrame, n_windows: int) -> list:
    """Equal consecutive time windows: shows whether results are stable
    through time or driven by one lucky stretch."""
    size = len(df) // n_windows
    return [df.iloc[i * size:(i + 1) * size if i < n_windows - 1 else len(df)]
            for i in range(n_windows)]
