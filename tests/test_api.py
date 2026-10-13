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
            "datetime": [pd.Timestamp.now(tz="UTC").floor("min")],
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



    def test_demo_execute_disabled_by_default(self):
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("DEMO_EXECUTION_API_ENABLED", None)
            response = self.client.post(
                "/api/demo/execute",
                json={"manual_confirmation": True},
            )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["status"], "disabled")
        self.assertFalse(
            response.get_json()["automatic_order_submitted"]
        )

    def test_demo_execute_requires_authentication(self):
        with patch.dict(
            "os.environ",
            {"DEMO_EXECUTION_API_ENABLED": "true",
             "DEMO_EXECUTION_API_TOKEN": "test-only-secret"},
        ):
            response = self.client.post(
                "/api/demo/execute",
                json={"manual_confirmation": True},
            )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["status"], "blocked")

    def test_demo_execute_requires_manual_confirmation(self):
        with patch.dict(
            "os.environ",
            {"DEMO_EXECUTION_API_ENABLED": "true",
             "DEMO_EXECUTION_API_TOKEN": "test-only-secret"},
        ):
            response = self.client.post(
                "/api/demo/execute",
                headers={"Authorization": "Bearer test-only-secret"},
                json={"manual_confirmation": False},
            )

        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertEqual(data["status"], "blocked")
        self.assertFalse(data["automatic_order_submitted"])

    @patch("backend.api.execute_demo_signal")
    @patch("backend.api.analyze_candles")
    @patch("backend.api.get_candles")
    def test_demo_execute_does_not_submit_when_trading_disabled(
        self, mock_get_candles, mock_analyze, mock_execute
    ):
        import json
        from pathlib import Path

        config = json.loads(Path("backend/config.json").read_text())
        trading = config["trading"]

        self.assertFalse(trading["enabled"])
        self.assertFalse(trading["submission_enabled"])

        candles = pd.DataFrame({
            "datetime": [
                pd.Timestamp.now(tz="UTC").floor("5min")
            ],
            "open": [4100.0],
            "high": [4110.0],
            "low": [4090.0],
            "close": [4105.0],
        })
        mock_get_candles.return_value = ("XAUUSD", "5m", candles)
        mock_analyze.return_value = {
            "signal": "BUY",
            "reason": "API safety test",
            "trading_enabled": False,
        }

        mock_execute.return_value = {
            "status": "blocked",
            "message": "Trading is disabled",
            "automatic_order_submitted": False,
        }

        with patch.dict(
            "os.environ",
            {"DEMO_EXECUTION_API_ENABLED": "true",
             "DEMO_EXECUTION_API_TOKEN": "test-only-secret"},
        ):
            response = self.client.post(
                "/api/demo/execute",
                headers={"Authorization": "Bearer test-only-secret"},
                json={"manual_confirmation": True},
            )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            response.get_json().get("automatic_order_submitted", False)
        )
        mock_execute.assert_called_once()

    @patch("backend.api.get_candles")
    def test_demo_execute_handles_missing_market_data(self, mock_get_candles):
        mock_get_candles.return_value = ("XAUUSD", "5m", pd.DataFrame())

        with patch.dict(
            "os.environ",
            {"DEMO_EXECUTION_API_ENABLED": "true",
             "DEMO_EXECUTION_API_TOKEN": "test-only-secret"},
        ):
            response = self.client.post(
                "/api/demo/execute",
                headers={"Authorization": "Bearer test-only-secret"},
                json={"manual_confirmation": True},
            )

        self.assertEqual(response.status_code, 503)
        self.assertFalse(
            response.get_json().get("automatic_order_submitted", False)
        )

if __name__ == "__main__":
    unittest.main()
