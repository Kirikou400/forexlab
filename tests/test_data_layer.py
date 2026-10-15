import tempfile
import unittest
from pathlib import Path

import pandas as pd

from forexlab.candles import drop_unclosed, resample_ohlc
from forexlab.db import load_candles, load_signals_history, save_signals, upsert_candles
from forexlab.metrics import compute_metrics, longest_losing_streak, wilson_interval
from forexlab.quality import check_candles
from forexlab.splits import chronological_split
from forexlab.strategies import parse_params
from forexlab.twelvedata import TwelveDataError, fetch_history, fetch_latest, parse_time_series
from tests.synthetic import random_walk


class FakeResp:
    def __init__(self, payload): self._p = payload
    def json(self): return self._p


class DataLayer(unittest.TestCase):
    def test_parse_twelvedata_payload(self):
        payload = {"status": "ok", "values": [
            {"datetime": "2024-01-02 02:00:00", "open": "1.1010", "high": "1.1020", "low": "1.1000", "close": "1.1015"},
            {"datetime": "2024-01-02 01:00:00", "open": "1.1000", "high": "1.1012", "low": "1.0995", "close": "1.1010"}]}
        df = parse_time_series(payload)
        self.assertTrue(df.index.is_monotonic_increasing)
        self.assertEqual(str(df.index.tz), "UTC")
        self.assertAlmostEqual(df.iloc[0]["open"], 1.1000)

    def test_error_payload_raises(self):
        with self.assertRaises(TwelveDataError):
            parse_time_series({"status": "error", "code": 401, "message": "bad key"})

    def test_fetch_latest_requests_recent_candles(self):
        payload = {"status": "ok", "values": [
            {"datetime": "2024-01-02 02:00:00", "open": "1.1010", "high": "1.1020", "low": "1.1000", "close": "1.1015"}
        ]}

        def fake_get(url, params, timeout):
            self.assertEqual(params["symbol"], "EUR/USD")
            self.assertEqual(params["interval"], "1h")
            self.assertEqual(params["outputsize"], 500)
            return FakeResp(payload)

        result = fetch_latest("EUR/USD", "1h", "key", _get=fake_get)
        self.assertEqual(len(result), 1)
        self.assertEqual(str(result.index.tz), "UTC")

    def test_pagination_stops_when_history_ends(self):
        def batch(start, n):
            ts = pd.date_range(start, periods=n, freq="1h")[::-1]
            return {"status": "ok", "values": [{"datetime": str(t), "open": "1", "high": "1", "low": "1", "close": "1"} for t in ts]}
        responses = [batch("2024-01-02 00:00", 5000), {"status": "error", "code": 400, "message": "No data is available"}]
        calls = []
        def fake_get(url, params, timeout):
            calls.append(params.get("end_date")); return FakeResp(responses[len(calls) - 1])
        df = fetch_history("EUR/USD", "1h", "k", 9000, _get=fake_get, _sleep=lambda s: None)
        self.assertEqual(len(df), 5000)
        self.assertEqual(len(calls), 2)
        self.assertIsNotNone(calls[1])       # second call pages backwards using end_date

    def test_unclosed_candle_is_dropped(self):
        df = random_walk(n=10, freq="1h")
        now = df.index[-1] + pd.Timedelta(minutes=30)      # last candle is still forming
        self.assertEqual(len(drop_unclosed(df, "1h", now=now)), 9)
        now = df.index[-1] + pd.Timedelta(hours=1)         # exactly closed
        self.assertEqual(len(drop_unclosed(df, "1h", now=now)), 10)

    def test_resample_and_incomplete_last_bucket(self):
        df = random_walk(n=10, freq="15min")               # 10 x 15min = 2.5 hours
        h = resample_ohlc(df, "1h", "15min")
        self.assertEqual(len(h), 2)                        # third hour incomplete -> dropped
        self.assertAlmostEqual(h.iloc[0]["open"], df.iloc[0]["open"])
        self.assertAlmostEqual(h.iloc[0]["close"], df.iloc[3]["close"])
        self.assertAlmostEqual(h.iloc[0]["high"], df.iloc[:4]["high"].max())

    def test_db_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.db"
            df = random_walk(n=50)
            self.assertEqual(upsert_candles(df, "EUR/USD", "1h", "test", db_path=p), 50)
            self.assertEqual(upsert_candles(df, "EUR/USD", "1h", "test", db_path=p), 50)   # idempotent
            back = load_candles("EUR/USD", "1h", db_path=p)
            self.assertEqual(len(back), 50)
            pd.testing.assert_series_equal(back["close"], df["close"], check_freq=False, check_exact=False, rtol=1e-9)

    def test_quality_checker_flags_problems(self):
        df = random_walk(n=100)
        df.iloc[10, df.columns.get_loc("high")] = df.iloc[10]["low"] - 0.01     # impossible candle
        df = df.drop(df.index[40:45])                                           # missing hours mid-week
        r = check_candles(df, "1h")
        self.assertEqual(r["invalid_ohlc"], 1)
        self.assertGreaterEqual(r["unexpected_gaps"], 1)

    def test_splits_are_chronological_and_disjoint(self):
        df = random_walk(n=1000)
        s = chronological_split(df)
        self.assertLess(s["train"].index[-1], s["validation"].index[0])
        self.assertLess(s["validation"].index[-1], s["test"].index[0])
        self.assertEqual(sum(len(v) for v in s.values()), 1000)

    def test_metrics_basics(self):
        t = pd.DataFrame({"r": [2, -1, -1, 2, -1, -1, -1, 2], "exit_reason": "x",
                          "entry_ts": pd.date_range("2024", periods=8, freq="1h", tz="UTC"), "direction": 1})
        m = compute_metrics(t, 1.0, 1.0)
        self.assertEqual(m["trades"], 8)
        self.assertAlmostEqual(m["win_rate_pct"], 37.5)
        self.assertAlmostEqual(m["expectancy_r"], 0.125)   # (3x +2R, 5x -1R) = +1R over 8 trades
        self.assertEqual(longest_losing_streak(t["r"]), 3)
        self.assertTrue(any("Only 8 trades" in w for w in m["warnings"]))
        lo, hi = wilson_interval(3, 8)
        self.assertLess(lo, 0.375); self.assertGreater(hi, 0.375)

    def test_signals_history_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.db"
            sig = [{
                "symbol": "EUR/USD",
                "timeframe": "1h",
                "strategy": "ema_cross",
                "direction": "BUY",
                "confidence": 85,
                "price": 1.1000,
                "stop": 1.0950,
                "target": 1.1100,
                "stop_pips": 50.0,
                "technical_score": 80,
                "volatility_score": 90,
                "reasoning": "EMA bullish crossover",
                "created_at": "2024-01-02 00:00:00",
            }]
            saved = save_signals(sig, db_path=p)
            self.assertEqual(saved, 1)
            # Idempotent insert or ignore
            self.assertEqual(save_signals(sig, db_path=p), 1)

            history = load_signals_history("EUR/USD", "1h", db_path=p)
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]["strategy"], "ema_cross")
            self.assertEqual(history[0]["direction"], "BUY")
            self.assertEqual(history[0]["confidence"], 85)

    def test_parse_params_valid_and_invalid(self):
        self.assertEqual(parse_params("fast=10, slow=30, atr_mult=2.5"), {"fast": 10, "slow": 30, "atr_mult": 2.5})
        self.assertEqual(parse_params(""), {})
        with self.assertRaises(ValueError):
            parse_params("fast")
        with self.assertRaises(ValueError):
            parse_params("fast=abc")


if __name__ == "__main__":
    unittest.main()
