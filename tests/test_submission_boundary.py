import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

from backend.submission_boundary import submit_signal_once


class TestSubmissionBoundary(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_path = Path(self.temp_dir.name) / "order_state.json"
        self.candle_time = datetime.now(timezone.utc).isoformat()

        self.connection = unittest.mock.Mock()
        self.connection.create_market_buy_order = AsyncMock()
        self.connection.create_market_sell_order = AsyncMock()
        self.connection.get_positions = AsyncMock(return_value=[])
        self.connection.get_orders = AsyncMock(return_value=[])

        self.args = {
            "symbol": "XAUUSD",
            "timeframe": "5m",
            "candle_time": self.candle_time,
            "side": "BUY",
            "volume": 0.01,
            "stop_loss": 2600.0,
            "take_profit": 2800.0,
            "state_path": self.state_path,
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    async def test_duplicate_signal_is_not_submitted_twice(self):
        self.connection.create_market_buy_order.return_value = {
            "numericCode": 10009,
            "stringCode": "TRADE_RETCODE_DONE",
            "orderId": "order-1",
            "positionId": "position-1",
        }
        self.connection.get_positions.return_value = [
            {"id": "position-1"}
        ]

        first = await submit_signal_once(
            self.connection, **self.args
        )
        second = await submit_signal_once(
            self.connection, **self.args
        )

        self.assertEqual(first["status"], "verified_position")
        self.assertEqual(second["status"], "blocked")
        self.connection.create_market_buy_order.assert_awaited_once()

    async def test_submission_exception_is_uncertain_and_not_retried(self):
        self.connection.create_market_buy_order.side_effect = TimeoutError()

        first = await submit_signal_once(
            self.connection, **self.args
        )
        second = await submit_signal_once(
            self.connection, **self.args
        )

        self.assertEqual(first["status"], "uncertain")
        self.assertFalse(first["automatic_retry"])
        self.assertEqual(second["status"], "blocked")
        self.connection.create_market_buy_order.assert_awaited_once()

    async def test_rejected_response_is_not_retried(self):
        self.connection.create_market_buy_order.return_value = {
            "numericCode": 10006,
            "stringCode": "TRADE_RETCODE_REJECT",
            "message": "Rejected by broker",
        }

        result = await submit_signal_once(
            self.connection, **self.args
        )

        self.assertEqual(result["status"], "rejected")
        self.assertFalse(result["automatic_retry"])
        self.connection.get_positions.assert_not_awaited()
        self.connection.get_orders.assert_not_awaited()

    async def test_success_response_without_matching_state_is_uncertain(self):
        self.connection.create_market_buy_order.return_value = {
            "numericCode": 10009,
            "stringCode": "TRADE_RETCODE_DONE",
            "orderId": "order-1",
            "positionId": "position-1",
        }

        result = await submit_signal_once(
            self.connection, **self.args
        )

        self.assertEqual(result["status"], "uncertain")
        self.assertFalse(result["automatic_retry"])

    async def test_sell_signal_uses_sell_method(self):
        self.connection.create_market_sell_order.return_value = {
            "numericCode": 10009,
            "stringCode": "TRADE_RETCODE_DONE",
            "orderId": "order-2",
            "positionId": "position-2",
        }
        self.connection.get_positions.return_value = [
            {"id": "position-2"}
        ]

        args = {**self.args, "side": "SELL"}
        result = await submit_signal_once(
            self.connection, **args
        )

        self.assertEqual(result["status"], "verified_position")
        self.connection.create_market_sell_order.assert_awaited_once()
        self.connection.create_market_buy_order.assert_not_awaited()



    async def test_verification_failure_is_uncertain_and_not_retried(self):
        self.connection.create_market_buy_order.return_value = {
            "numericCode": 10009,
            "stringCode": "TRADE_RETCODE_DONE",
            "orderId": "order-verify-fail",
            "positionId": "position-verify-fail",
        }
        self.connection.get_positions.side_effect = TimeoutError()

        result = await submit_signal_once(
            self.connection, **self.args
        )

        self.assertEqual(result["status"], "uncertain")
        self.assertFalse(result["automatic_retry"])
        self.connection.create_market_buy_order.assert_awaited_once()

    async def test_matching_order_without_position_is_verified_order(self):
        self.connection.create_market_buy_order.return_value = {
            "numericCode": 10008,
            "stringCode": "TRADE_RETCODE_PLACED",
            "orderId": "pending-order-1",
            "positionId": None,
        }
        self.connection.get_orders.return_value = [
            {"id": "pending-order-1"}
        ]

        result = await submit_signal_once(
            self.connection, **self.args
        )

        self.assertEqual(result["status"], "verified_order")
        self.assertFalse(result["automatic_retry"])
        self.connection.create_market_buy_order.assert_awaited_once()

if __name__ == "__main__":
    unittest.main()
