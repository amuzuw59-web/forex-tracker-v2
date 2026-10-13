import json
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.executor import validate_trade_request


class TestExecutorSafety(unittest.TestCase):

    def setUp(self):
        self.config_path = Path("backend/config.json")
        self.original_config = self.config_path.read_text(encoding="utf-8")

    def tearDown(self):
        # Restore the original configuration after every test.
        self.config_path.write_text(self.original_config, encoding="utf-8")

    def set_trading_config(self, **changes):
        config = json.loads(self.original_config)
        config["trading"].update(changes)
        self.config_path.write_text(
            json.dumps(config, indent=2),
            encoding="utf-8",
        )

    def request(self, **overrides):
        values = {
            "signal": "BUY",
            "account_type": "demo",
            "equity": 10000.0,
            "volume": 0.01,
            "entry_price": 4200.0,
            "stop_loss": 4190.0,
            "take_profit": 4220.0,
            "open_positions": 0,
            "manual_confirmation": True,
        }
        values.update(overrides)
        return values

    def test_disabled_trading_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Trading is disabled"):
            validate_trade_request(**self.request())

    def test_unverified_account_type_is_rejected(self):
        self.set_trading_config(enabled=True)
        with self.assertRaisesRegex(ValueError, "Demo account required"):
            validate_trade_request(
                **self.request(account_type="unknown")
            )

    def test_missing_manual_confirmation_is_rejected(self):
        self.set_trading_config(enabled=True)
        with self.assertRaisesRegex(
            ValueError, "Explicit manual confirmation required"
        ):
            validate_trade_request(
                **self.request(manual_confirmation=False)
            )

    def test_invalid_buy_stop_loss_is_rejected(self):
        self.set_trading_config(enabled=True)
        with self.assertRaisesRegex(ValueError, "BUY requires"):
            validate_trade_request(
                **self.request(stop_loss=4210.0)
            )

    def test_maximum_open_positions_is_enforced(self):
        self.set_trading_config(enabled=True)
        with self.assertRaisesRegex(
            ValueError, "Maximum open-position limit reached"
        ):
            validate_trade_request(
                **self.request(open_positions=1)
            )

    def test_risk_limit_above_half_percent_is_rejected(self):
        self.set_trading_config(enabled=True, max_risk_percent=1.0)
        with self.assertRaisesRegex(ValueError, "Risk limit"):
            validate_trade_request(**self.request())


    def test_valid_trade_risk_is_calculated(self):
        self.set_trading_config(enabled=True)
        result = validate_trade_request(**self.request())
        self.assertTrue(result["approved"])
        self.assertEqual(result["estimated_loss"], 10.0)
        self.assertEqual(result["maximum_allowed_loss"], 50.0)
        self.assertFalse(result["automatic_order_submitted"])

    def test_trade_exceeding_risk_limit_is_rejected(self):
        self.set_trading_config(enabled=True)
        with self.assertRaisesRegex(ValueError, "exceeds the maximum allowed"):
            validate_trade_request(**self.request(stop_loss=4100.0))

    def test_volume_outside_broker_limits_is_rejected(self):
        self.set_trading_config(enabled=True)
        with self.assertRaisesRegex(ValueError, "outside broker limits"):
            validate_trade_request(**self.request(volume=0.001))

    def test_volume_not_matching_broker_step_is_rejected(self):
        self.set_trading_config(enabled=True)
        with self.assertRaisesRegex(ValueError, "volume step"):
            validate_trade_request(**self.request(volume=0.015))

    def test_non_finite_equity_is_rejected(self):
        self.set_trading_config(enabled=True)
        with self.assertRaisesRegex(ValueError, "must be finite"):
            validate_trade_request(**self.request(equity=float("inf")))
if __name__ == "__main__":
    unittest.main()
