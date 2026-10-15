import unittest

import pandas as pd

from forexlab.engine import BacktestConfig, run_backtest


def candles(rows):
    idx = pd.date_range("2024-01-01", periods=len(rows), freq="1h", tz="UTC")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)


def one_signal(df, d, sl_dist=0.0010, bar=0):
    s = pd.DataFrame({"direction": 0, "sl_dist": sl_dist}, index=df.index)
    s.iloc[bar, s.columns.get_loc("direction")] = d
    return s


NO_COST = BacktestConfig(rr=2.0, spread=0.0, slippage=0.0, max_hold_bars=10)
COST = BacktestConfig(rr=2.0, spread=0.0002, slippage=0.0001, max_hold_bars=10)


class EngineTests(unittest.TestCase):
    def run_one(self, rows, d, cfg):
        df = candles(rows)
        return run_backtest(df, one_signal(df, d), cfg).trades

    def test_entry_is_next_open_not_signal_close(self):
        t = self.run_one([(1.1000, 1.1002, 1.0998, 1.1005),    # signal bar (close 1.1005)
                          (1.1000, 1.1025, 1.0995, 1.1020)], 1, NO_COST)
        self.assertAlmostEqual(t.iloc[0]["entry"], 1.1000)
        self.assertEqual(t.iloc[0]["entry_ts"], pd.Timestamp("2024-01-01 01:00", tz="UTC"))

    def test_long_take_profit(self):
        t = self.run_one([(1.1, 1.1, 1.1, 1.1), (1.1000, 1.1025, 1.0995, 1.1020)], 1, NO_COST)
        self.assertEqual(t.iloc[0]["exit_reason"], "tp")
        self.assertAlmostEqual(t.iloc[0]["r"], 2.0, places=6)

    def test_long_stop_loss(self):
        t = self.run_one([(1.1, 1.1, 1.1, 1.1), (1.1000, 1.1005, 1.0985, 1.0990)], 1, NO_COST)
        self.assertEqual(t.iloc[0]["exit_reason"], "sl")
        self.assertAlmostEqual(t.iloc[0]["r"], -1.0, places=6)

    def test_stop_and_target_same_candle_assumes_stop_first(self):
        t = self.run_one([(1.1, 1.1, 1.1, 1.1), (1.1000, 1.1030, 1.0980, 1.1000)], 1, NO_COST)
        self.assertEqual(t.iloc[0]["exit_reason"], "sl")
        self.assertAlmostEqual(t.iloc[0]["r"], -1.0, places=6)

    def test_gap_through_stop_fills_at_open(self):
        t = self.run_one([(1.1, 1.1, 1.1, 1.1),
                          (1.1000, 1.1004, 1.0996, 1.1000),
                          (1.0950, 1.0955, 1.0940, 1.0945)], 1, NO_COST)
        self.assertAlmostEqual(t.iloc[0]["r"], -5.0, places=6)     # much worse than -1R

    def test_costs_long(self):
        win = self.run_one([(1.1, 1.1, 1.1, 1.1), (1.1000, 1.1025, 1.0995, 1.1020)], 1, COST)
        self.assertAlmostEqual(win.iloc[0]["r"], 1.8, places=6)     # 2R target minus 0.2R of costs
        loss = self.run_one([(1.1, 1.1, 1.1, 1.1), (1.1000, 1.1005, 1.0985, 1.0990)], 1, COST)
        self.assertAlmostEqual(loss.iloc[0]["r"], -1.3, places=6)   # worse than -1R

    def test_costs_short(self):
        win = self.run_one([(1.1, 1.1, 1.1, 1.1), (1.1000, 1.1005, 1.0975, 1.0980)], -1, COST)
        self.assertAlmostEqual(win.iloc[0]["r"], 1.8, places=6)
        loss = self.run_one([(1.1, 1.1, 1.1, 1.1), (1.1000, 1.1015, 1.0995, 1.1010)], -1, COST)
        self.assertAlmostEqual(loss.iloc[0]["r"], -1.3, places=6)

    def test_time_exit(self):
        rows = [(1.1, 1.1, 1.1, 1.1)] + [(1.1000, 1.1005, 1.0996, 1.1002)] * 5
        df = candles(rows)
        cfg = BacktestConfig(rr=2.0, max_hold_bars=3)
        t = run_backtest(df, one_signal(df, 1), cfg).trades
        self.assertEqual(t.iloc[0]["exit_reason"], "time")
        self.assertEqual(t.iloc[0]["bars_held"], 3)

    def test_tight_stop_skipped_when_costs_dominate(self):
        df = candles([(1.1, 1.1, 1.1, 1.1), (1.1000, 1.1025, 1.0995, 1.1020)])
        res = run_backtest(df, one_signal(df, 1, sl_dist=0.0002), COST)
        self.assertEqual(len(res.trades), 0)
        self.assertEqual(res.skipped["stop_too_tight"], 1)

    def test_no_trade_when_signal_on_last_bar(self):
        df = candles([(1.1, 1.1, 1.1, 1.1), (1.1, 1.1, 1.1, 1.1)])
        self.assertEqual(len(run_backtest(df, one_signal(df, 1, bar=1), NO_COST).trades), 0)


if __name__ == "__main__":
    unittest.main()
