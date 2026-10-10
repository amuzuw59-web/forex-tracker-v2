import unittest
from unittest.mock import patch

import pandas as pd

from backend.api import app


class TestAPI(unittest.TestCase):

    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_home_endpoint(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

        data = response.get_json()
        self.assertEqual(data["status"], "running")
        self.assertFalse(data["automatic_trading"])

    def test_health_endpoint(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)

        data = response.get_json()
        self.assertEqual(data["status"], "ok")
        self.assertFalse(data["automatic_trading"])

    @patch("backend.api.analyze_candles")
    @patch("backend.api.get_candles")
    def test_signal_endpoint(self, mock_get_candles, mock_analyze):
        candles = pd.DataFrame({
            "datetime": [pd.Timestamp("2026-10-10T10:00:00Z")],
            "open": [4100.0],
            "high": [4110.0],
            "low": [4090.0],
            "close": [4105.0],
        })

        mock_get_candles.return_value = ("XAUUSD", "5m", candles)
        mock_analyze.return_value = {
            "signal": "HOLD",
            "reason": "API test",
            "trading_enabled": False,
        }

        response = self.client.get("/api/signal")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["symbol"], "XAUUSD")
        self.assertEqual(data["timeframe"], "5m")
        self.assertFalse(data["automatic_trading"])

    @patch("backend.api.get_candles")
    def test_stale_market_data_returns_503(self, mock_get_candles):
        mock_get_candles.side_effect = RuntimeError(
            "Latest closed candle is stale"
        )

        response = self.client.get("/api/signal")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["status"], "error")
        self.assertFalse(
            response.get_json()["automatic_trading"]
        )


if __name__ == "__main__":
    unittest.main()
