"""A random walk has no exploitable pattern. With realistic costs, any rule
applied to it must lose on average. If a backtester 'finds' profit here,
the backtester is broken (or cheating)."""
import unittest

from forexlab.engine import BacktestConfig, run_backtest
from forexlab.metrics import compute_metrics
from forexlab.strategies import REGISTRY
from tests.synthetic import random_walk


class NoEdgeInNoise(unittest.TestCase):
    def test_strategies_do_not_beat_random_noise(self):
        cfg = BacktestConfig(rr=2.0, spread=0.0001, slippage=0.00003, max_hold_bars=100)
        for name, fn in REGISTRY.items():
            rs = []
            for seed in (11, 12, 13):
                df = random_walk(n=20000, seed=seed)
                rs.extend(run_backtest(df, fn(df), cfg).trades["r"].tolist())
            import pandas as pd
            m = compute_metrics(pd.DataFrame({"r": rs, "exit_reason": "x"}), 1.0, 7.0)
            self.assertGreater(m["trades"], 300, name)
            self.assertLess(m["expectancy_r"], 0.05, f"{name} found profit in pure noise: {m['expectancy_r']:.3f}R")


if __name__ == "__main__":
    unittest.main()
