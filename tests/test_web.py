import tempfile
import unittest
import warnings
from pathlib import Path
from unittest.mock import patch

warnings.filterwarnings("ignore")
from fastapi.testclient import TestClient

from forexlab.db import upsert_candles
from forexlab.synthetic_data import make_market_series
from forexlab.web import app
from tests.synthetic import random_walk


class WebApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_endpoint(self):
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["provider"], "Twelve Data")
        self.assertEqual(data["execution"], "disabled")

    def test_markets_endpoint(self):
        resp = self.client.get("/api/markets")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("pairs", data)
        self.assertIn("EUR/USD", data["pairs"])
        self.assertIn("timeframes", data)
        self.assertIn("1h", data["timeframes"])
        self.assertIn("strategies", data)
        self.assertIn("ema_cross", data["strategies"])
        self.assertIn("macd_cross", data["strategies"])

    def test_dashboard_validation_errors(self):
        resp = self.client.get("/api/dashboard?symbol=INVALID&timeframe=1h")
        self.assertEqual(resp.status_code, 422)

        resp2 = self.client.get("/api/dashboard?symbol=EUR/USD&timeframe=99h")
        self.assertEqual(resp2.status_code, 422)

    def test_dashboard_endpoint_returns_data_schema(self):
        resp = self.client.get("/api/dashboard?symbol=EUR/USD&timeframe=1h")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["symbol"], "EUR/USD")
        self.assertEqual(data["timeframe"], "1h")
        self.assertIn("candles", data)
        self.assertIn("signals", data)
        self.assertIn("status", data)

    def test_demo_data_endpoint(self):
        resp = self.client.post("/api/demo-data", json={"symbols": ["EUR/USD"], "timeframes": ["1h"], "bars": 120})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["symbol"], "EUR/USD")
        self.assertIn("demo_seed", data)
        self.assertGreater(data["demo_seed"]["saved_candles"], 0)
        self.assertGreater(len(data["candles"]), 50)

    def test_refresh_fails_safely_without_key(self):
        with patch.dict("os.environ", {"TWELVEDATA_API_KEY": ""}):
            resp = self.client.post("/api/refresh", json={"symbol": "EUR/USD", "timeframe": "1h"})
            self.assertEqual(resp.status_code, 503)

    def test_signals_history_endpoint(self):
        resp = self.client.get("/api/signals/history?limit=10")
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json(), list)

    def test_backtest_endpoint_valid_run(self):
        # Seed sufficient data first
        self.client.post("/api/demo-data", json={"symbols": ["EUR/USD"], "timeframes": ["1h"], "bars": 300})

        resp = self.client.post("/api/backtest", json={
            "symbol": "EUR/USD",
            "timeframe": "1h",
            "strategy": "ema_cross",
            "split": "train",
            "rr": 2.0,
            "risk": 1.0,
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["strategy"], "ema_cross")
        self.assertIn("metrics", data)
        self.assertIn("equity_curve", data)
        self.assertIn("trades", data)

    def test_backtest_endpoint_validation(self):
        resp = self.client.post("/api/backtest", json={
            "symbol": "EUR/USD",
            "timeframe": "1h",
            "strategy": "unknown_strategy",
            "split": "train",
        })
        self.assertEqual(resp.status_code, 422)

        resp2 = self.client.post("/api/backtest", json={
            "symbol": "EUR/USD",
            "timeframe": "1h",
            "strategy": "ema_cross",
            "split": "invalid_split",
        })
        self.assertEqual(resp2.status_code, 422)

    def test_backtests_history_endpoint(self):
        resp = self.client.get("/api/backtests?limit=5")
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json(), list)


if __name__ == "__main__":
    unittest.main()
