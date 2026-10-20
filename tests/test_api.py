import unittest
from unittest.mock import patch, AsyncMock

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
        self.assertIn("candlestick_tracker", data)
        tracker = data["candlestick_tracker"]
        self.assertEqual(tracker["status"], "unavailable")
        self.assertFalse(tracker["order_execution_enabled"])

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

    def test_demo_execute_blocks_without_trade_specific_approval(self):
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

        self.assertEqual(response.status_code, 409)
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

        self.assertEqual(response.status_code, 409)
        self.assertFalse(
            response.get_json().get("automatic_order_submitted", False)
        )
        mock_execute.assert_not_called()

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

        self.assertEqual(response.status_code, 409)
        self.assertFalse(
            response.get_json().get("automatic_order_submitted", False)
        )
        mock_get_candles.assert_not_called()


    def test_demo_proposal_requires_authentication(self):
        with patch.dict(
            "os.environ",
            {
                "DEMO_EXECUTION_API_ENABLED": "true",
                "DEMO_EXECUTION_API_TOKEN": "test-only-secret",
            },
        ):
            response = self.client.post("/api/demo/proposal", json={})

        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.get_json()["automatic_order_submitted"])

    @patch("backend.api.execute_demo_signal", new_callable=AsyncMock)
    @patch("backend.api._build_signal_payload")
    def test_demo_proposal_creates_broker_validated_proposal(
        self, mock_build_payload, mock_execute
    ):
        import pandas as pd

        candle_time = pd.Timestamp.now(tz="UTC").floor("5min").isoformat()
        mock_build_payload.return_value = {
            "status": "ok",
            "symbol": "XAUUSD",
            "timeframe": "5m",
            "latest_candle": candle_time,
            "signal": {
                "signal": "BUY",
                "stop_loss": 4090.0,
                "take_profit": 4120.0,
            },
        }
        mock_execute.return_value = {
            "status": "proposal_ready",
            "entry_price": 4100.0,
            "stop_loss": 4090.0,
            "take_profit": 4120.0,
            "volume": 0.01,
            "estimated_loss": 1.0,
            "maximum_allowed_loss": 500.0,
            "risk_percent": 0.5,
        }

        with patch.dict(
            "os.environ",
            {
                "DEMO_EXECUTION_API_ENABLED": "true",
                "DEMO_EXECUTION_API_TOKEN": "test-only-secret",
            },
        ):
            response = self.client.post(
                "/api/demo/proposal",
                headers={"Authorization": "Bearer test-only-secret"},
                json={},
            )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "proposal_ready")
        self.assertTrue(data["approval_required"])
        self.assertFalse(data["automatic_order_submitted"])
        self.assertTrue(data["proposal"]["proposal_id"])
        self.assertEqual(data["proposal"]["symbol"], "XAUUSD")
        self.assertEqual(data["proposal"]["volume"], 0.01)
        mock_execute.assert_awaited_once()

    def test_demo_approval_rejects_unknown_proposal(self):
        with patch.dict(
            "os.environ",
            {
                "DEMO_EXECUTION_API_ENABLED": "true",
                "DEMO_EXECUTION_API_TOKEN": "test-only-secret",
            },
        ):
            response = self.client.post(
                "/api/demo/approve",
                headers={"Authorization": "Bearer test-only-secret"},
                json={"proposal_id": "unknown-proposal", "approve": True},
            )

        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.get_json()["automatic_order_submitted"])

    def test_demo_approval_is_one_time_only(self):
        import time
        from backend import api as api_module

        proposal_id = "test-proposal-one-time"
        proposal = {
            "proposal_id": proposal_id,
            "created_at": time.monotonic(),
            "approved": False,
        }

        with api_module._demo_proposals_lock:
            api_module._demo_proposals[proposal_id] = proposal

        headers = {"Authorization": "Bearer test-only-secret"}
        body = {"proposal_id": proposal_id, "approve": True}

        with patch.dict(
            "os.environ",
            {
                "DEMO_EXECUTION_API_ENABLED": "true",
                "DEMO_EXECUTION_API_TOKEN": "test-only-secret",
            },
        ):
            first = self.client.post(
                "/api/demo/approve", headers=headers, json=body
            )
            second = self.client.post(
                "/api/demo/approve", headers=headers, json=body
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.get_json()["status"], "approved_not_submitted")
        self.assertFalse(first.get_json()["automatic_order_submitted"])
        self.assertEqual(second.status_code, 409)

        with api_module._demo_proposals_lock:
            api_module._demo_proposals.pop(proposal_id, None)


    def test_demo_approval_rejects_expired_proposal(self):
        import time
        from backend import api as api_module

        proposal_id = "test-proposal-expired"
        proposal = {
            "proposal_id": proposal_id,
            "created_at": (
                time.monotonic()
                - api_module._DEMO_PROPOSAL_TTL_SECONDS
                - 1
            ),
            "approved": False,
        }

        with api_module._demo_proposals_lock:
            api_module._demo_proposals[proposal_id] = proposal

        try:
            with patch.dict("os.environ", {
                "DEMO_EXECUTION_API_ENABLED": "true",
                "DEMO_EXECUTION_API_TOKEN": "test-only-secret",
            }):
                response = self.client.post(
                    "/api/demo/approve",
                    headers={
                        "Authorization": "Bearer test-only-secret"
                    },
                    json={
                        "proposal_id": proposal_id,
                        "approve": True,
                    },
                )

            self.assertEqual(response.status_code, 409)
            self.assertFalse(
                response.get_json()["automatic_order_submitted"]
            )

            with api_module._demo_proposals_lock:
                self.assertNotIn(
                    proposal_id,
                    api_module._demo_proposals,
                )
        finally:
            with api_module._demo_proposals_lock:
                api_module._demo_proposals.pop(proposal_id, None)

    @patch("backend.api.execute_demo_signal", new_callable=AsyncMock)
    @patch("backend.api._build_signal_payload")
    def test_demo_execute_claims_proposal_after_failed_attempt(
        self, mock_build_payload, mock_execute
    ):
        import time
        from backend import api as api_module

        proposal_id = "test-proposal-single-execution"
        proposal = {
            "proposal_id": proposal_id,
            "created_at": time.monotonic(),
            "approved": True,
            "execution_claimed": False,
            "symbol": "XAUUSD",
            "timeframe": "5m",
            "signal": "BUY",
            "candle_time": "2026-10-15T10:00:00+00:00",
            "candle_id": "XAUUSD|5m|2026-10-15T10:00:00+00:00",
            "entry_price": 4100.0,
            "stop_loss": 4090.0,
            "take_profit": 4120.0,
            "volume": 0.01,
            "estimated_loss": 1.0,
            "maximum_allowed_loss": 500.0,
            "risk_percent": 0.5,
        }

        with api_module._demo_proposals_lock:
            api_module._demo_proposals[proposal_id] = proposal

        headers = {
            "Authorization": "Bearer test-only-secret"
        }
        body = {"proposal_id": proposal_id}

        try:
            with patch.dict("os.environ", {
                "DEMO_EXECUTION_API_ENABLED": "true",
                "DEMO_EXECUTION_API_TOKEN": "test-only-secret",
            }):
                # Simulate a failure after the proposal is claimed.
                mock_build_payload.side_effect = RuntimeError(
                    "Simulated signal retrieval failure"
                )

                first = self.client.post(
                    "/api/demo/execute",
                    headers=headers,
                    json=body,
                )

                second = self.client.post(
                    "/api/demo/execute",
                    headers=headers,
                    json=body,
                )

            self.assertEqual(first.status_code, 503)
            self.assertEqual(second.status_code, 409)
            self.assertFalse(
                first.get_json()["automatic_order_submitted"]
            )
            self.assertFalse(
                second.get_json()["automatic_order_submitted"]
            )
            mock_execute.assert_not_awaited()

            with api_module._demo_proposals_lock:
                self.assertTrue(
                    api_module._demo_proposals[proposal_id][
                        "execution_claimed"
                    ]
                )
        finally:
            with api_module._demo_proposals_lock:
                api_module._demo_proposals.pop(proposal_id, None)


    @patch("backend.api.execute_demo_signal", new_callable=AsyncMock)
    @patch("backend.api._build_signal_payload")
    def test_demo_execute_reports_verified_broker_state(
        self, mock_build_payload, mock_execute
    ):
        import time
        from backend import api as api_module

        candle_time = "2026-10-15T10:00:00+00:00"
        candle_id = api_module.make_signal_identity(
            "XAUUSD", "5m", candle_time
        )
        mock_build_payload.return_value = {
            "status": "ok",
            "symbol": "XAUUSD",
            "timeframe": "5m",
            "latest_candle": candle_time,
            "signal": {
                "signal": "BUY",
                "stop_loss": 4090.0,
                "take_profit": 4120.0,
            },
        }

        headers = {
            "Authorization": "Bearer test-only-secret"
        }

        cases = (
            ("verified_position", True, True),
            ("verified_order", True, False),
        )

        with patch.dict("os.environ", {
            "DEMO_EXECUTION_API_ENABLED": "true",
            "DEMO_EXECUTION_API_TOKEN": "test-only-secret",
        }):
            for status, broker_verified, position_verified in cases:
                proposal_id = "test-response-" + status
                proposal = {
                    "proposal_id": proposal_id,
                    "created_at": time.monotonic(),
                    "approved": True,
                    "execution_claimed": False,
                    "symbol": "XAUUSD",
                    "timeframe": "5m",
                    "signal": "BUY",
                    "candle_time": candle_time,
                    "candle_id": candle_id,
                    "entry_price": 4100.0,
                    "stop_loss": 4090.0,
                    "take_profit": 4120.0,
                    "volume": 0.01,
                    "estimated_loss": 1.0,
                    "maximum_allowed_loss": 500.0,
                    "risk_percent": 0.5,
                }

                with api_module._demo_proposals_lock:
                    api_module._demo_proposals[proposal_id] = proposal

                try:
                    mock_execute.reset_mock()
                    mock_execute.return_value = {"status": status}

                    response = self.client.post(
                        "/api/demo/execute",
                        headers=headers,
                        json={"proposal_id": proposal_id},
                    )

                    self.assertEqual(response.status_code, 200)
                    data = response.get_json()
                    self.assertEqual(data["status"], status)
                    self.assertEqual(
                        data["automatic_order_submitted"], broker_verified
                    )
                    self.assertEqual(
                        data["broker_state_verified"], broker_verified
                    )
                    self.assertEqual(
                        data["open_position_verified"], position_verified
                    )
                    mock_execute.assert_awaited_once()
                finally:
                    with api_module._demo_proposals_lock:
                        api_module._demo_proposals.pop(proposal_id, None)

if __name__ == "__main__":
    unittest.main()
