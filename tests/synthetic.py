"""SYNTHETIC random-walk candles. FOR AUTOMATED TESTS ONLY.
These are never written to the database and must never be used to judge
a strategy. They exist because a random walk has NO edge, so a correct
backtester must NOT find profit in it."""
import numpy as np
import pandas as pd


def random_walk(n=5000, seed=1, sigma=0.0005, start=1.1000, freq="1h") -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = start * np.exp(np.cumsum(rng.normal(0, sigma, n)))
    open_ = np.concatenate([[start], close[:-1]])
    wick_h = np.abs(rng.normal(0, sigma / 2, n)) * close
    wick_l = np.abs(rng.normal(0, sigma / 2, n)) * close
    idx = pd.date_range("2022-01-03", periods=n, freq=freq, tz="UTC", name="ts")
    return pd.DataFrame({"open": open_, "high": np.maximum(open_, close) + wick_h,
                         "low": np.minimum(open_, close) - wick_l, "close": close}, index=idx)
