import unittest

import numpy as np
import pandas as pd

from forexlab.live_signals import build_live_signals, confidence_score
from forexlab.strategies import REGISTRY


class LiveSignalTests(unittest.TestCase):
    def setUp(self):
        close = 1.1 + np.sin(np.linspace(0, 24, 300)) * 0.004
        self.frame = pd.DataFrame(
            {
                "open": close,
                "high": close + 0.0005,
                "low": close - 0.0005,
                "close": close,
            },
            index=pd.date_range("2025-01-01", periods=len(close), freq="h", tz="UTC"),
        )

    def test_registered_strategies_follow_backtest_signal_contract(self):
        for name, strategy in REGISTRY.items():
            with self.subTest(strategy=name):
                result = strategy(self.frame)
                self.assertEqual(list(result.columns), ["direction", "sl_dist"])
                self.assertTrue(set(result["direction"].unique()).issubset({-1, 0, 1}))
                valid_stops = result.loc[result["direction"] != 0, "sl_dist"]
                self.assertTrue((valid_stops > 0).all())

    def test_confidence_renormalizes_when_news_is_unavailable(self):
        self.assertEqual(confidence_score(100, 100), 100)
        self.assertEqual(confidence_score(100, 100, news=0), 85)

    def test_live_signal_contains_risk_and_news_status(self):
        signals = build_live_signals(self.frame, "EUR/USD", "1h")
        for signal in signals:
            self.assertIn(signal["direction"], {"BUY", "SELL"})
            self.assertGreaterEqual(signal["confidence"], 0)
            self.assertLessEqual(signal["confidence"], 100)
            self.assertIn("not probability", signal["score_label"])
            self.assertEqual(signal["news_status"], "not_configured")
            self.assertNotEqual(signal["stop"], signal["price"])
            self.assertNotEqual(signal["target"], signal["price"])


if __name__ == "__main__":
    unittest.main()
