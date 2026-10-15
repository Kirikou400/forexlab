"""The most important tests: results at bar t must not change if the future
is removed. If they did, the code would be using information it could not
have had at the time."""
import unittest

import pandas as pd

from forexlab.engine import BacktestConfig, run_backtest
from forexlab.indicators import atr, donchian_high, ema, rsi, swing_points
from forexlab.strategies import REGISTRY
from tests.synthetic import random_walk

DF = random_walk(n=1500, seed=7)


class NoLookahead(unittest.TestCase):
    def test_indicators_ignore_the_future(self):
        for k in (400, 800, 1200):
            full, part = DF, DF.iloc[:k]
            for name, fn in {
                "ema": lambda d: ema(d["close"], 20), "rsi": lambda d: rsi(d["close"], 14),
                "atr": lambda d: atr(d["high"], d["low"], d["close"], 14),
                "donchian": lambda d: donchian_high(d["high"], 20),
            }.items():
                pd.testing.assert_series_equal(fn(full).iloc[:k], fn(part), check_exact=False, rtol=1e-9, obj=name)
            pd.testing.assert_frame_equal(swing_points(full["high"], full["low"]).iloc[:k],
                                          swing_points(part["high"], part["low"]), check_exact=False, rtol=1e-9)

    def test_swings_are_reported_only_after_confirmation(self):
        k = 3
        sp = swing_points(DF["high"], DF["low"], k)
        pos = DF.index.get_indexer(sp["swing_high"].dropna().index)
        for p in pos:                       # value at confirmation bar p is the high of bar p-k
            self.assertAlmostEqual(sp["swing_high"].iloc[p], DF["high"].iloc[p - k])
        self.assertTrue(sp["swing_high"].iloc[:2 * k].isna().all())

    def test_strategy_signals_ignore_the_future(self):
        for name, fn in REGISTRY.items():
            full = fn(DF)
            for k in (400, 900, 1300):
                pd.testing.assert_frame_equal(full.iloc[:k], fn(DF.iloc[:k]), check_exact=False, rtol=1e-9, obj=name)

    def test_finished_trades_do_not_change_when_future_is_removed(self):
        cfg = BacktestConfig(rr=2.0, spread=0.0001, slippage=0.00003, max_hold_bars=50)
        for name, fn in REGISTRY.items():
            sig = fn(DF)
            full = run_backtest(DF, sig, cfg).trades
            k = 900
            part = run_backtest(DF.iloc[:k], sig, cfg).trades
            cutoff = DF.index[k - 2]
            a = full[full["exit_ts"] < cutoff].reset_index(drop=True)
            b = part[part["exit_ts"] < cutoff].reset_index(drop=True)
            pd.testing.assert_frame_equal(a, b, obj=name)
            self.assertGreater(len(a), 0)


if __name__ == "__main__":
    unittest.main()
