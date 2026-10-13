import unittest

from backend.risk_calculator import (
    validate_broker_tick_value,
    estimate_price_movement_loss,
    calculate_risk_limit,
    check_risk_limit,
)


class TestBrokerTickRisk(unittest.TestCase):

    def test_valid_broker_tick_values(self):
        self.assertTrue(validate_broker_tick_value(0.01, 1.0))

    def test_zero_tick_size_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_broker_tick_value(0, 1.0)

    def test_zero_tick_value_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_broker_tick_value(0.01, 0)

    def test_non_finite_tick_value_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_broker_tick_value(0.01, float("nan"))

    def test_boolean_tick_value_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_broker_tick_value(0.01, True)

    def test_loss_uses_tick_value_and_volume(self):
        loss = estimate_price_movement_loss(
            entry_price=4166.00,
            stop_loss=4165.00,
            tick_size=0.01,
            tick_value_per_lot=1.0,
            volume=0.01,
        )
        self.assertAlmostEqual(loss, 1.0)

    def test_equity_risk_ceiling(self):
        limit = calculate_risk_limit(99998.97, 0.5)
        self.assertAlmostEqual(limit, 499.99485)

    def test_loss_over_risk_ceiling_is_rejected(self):
        result = check_risk_limit(
            estimated_loss=500.00,
            equity=99998.97,
            risk_percent=0.5,
        )
        self.assertFalse(result["within_limit"])

    def test_loss_within_risk_ceiling_is_accepted(self):
        result = check_risk_limit(
            estimated_loss=100.00,
            equity=99998.97,
            risk_percent=0.5,
        )
        self.assertTrue(result["within_limit"])


if __name__ == "__main__":
    unittest.main()
