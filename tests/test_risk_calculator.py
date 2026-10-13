import unittest

from backend.risk_calculator import (
    estimate_price_movement_loss,
    estimate_contract_price_movement_loss,
    calculate_risk_limit,
    check_risk_limit,
    validate_broker_tick_value,
)


class TestRiskCalculator(unittest.TestCase):

    def test_valid_broker_tick_value(self):
        self.assertTrue(validate_broker_tick_value(0.01, 1.0))

    def test_zero_broker_tick_value_rejected(self):
        with self.assertRaises(ValueError):
            validate_broker_tick_value(0.01, 0)

    def test_non_finite_broker_tick_value_rejected(self):
        with self.assertRaises(ValueError):
            validate_broker_tick_value(0.01, float("nan"))

    def test_invalid_broker_tick_size_rejected(self):
        with self.assertRaises(ValueError):
            validate_broker_tick_value(0, 1.0)
    def test_illustrative_loss_calculation(self):
        loss = estimate_price_movement_loss(
            entry_price=4173.96,
            stop_loss=4178.17,
            tick_size=0.01,
            tick_value_per_lot=1.00,
            volume=0.01,
        )
        self.assertAlmostEqual(loss, 4.21, places=6)

    def test_contract_based_loss_calculation(self):
        loss = estimate_contract_price_movement_loss(
            entry_price=4167.38,
            stop_loss=4162.38,
            contract_size=100,
            volume=0.01,
        )
        self.assertAlmostEqual(loss, 5.00, places=6)

    def test_contract_loss_is_independent_of_direction(self):
        buy_loss = estimate_contract_price_movement_loss(
            entry_price=4167.38,
            stop_loss=4162.38,
            contract_size=100,
            volume=0.01,
        )
        sell_loss = estimate_contract_price_movement_loss(
            entry_price=4162.38,
            stop_loss=4167.38,
            contract_size=100,
            volume=0.01,
        )
        self.assertAlmostEqual(buy_loss, sell_loss, places=6)

    def test_risk_limit_calculation(self):
        limit = calculate_risk_limit(99998.97, 0.5)
        self.assertAlmostEqual(limit, 499.99485, places=6)

    def test_loss_within_limit(self):
        result = check_risk_limit(4.21, 1000.00, 0.5)
        self.assertTrue(result["within_limit"])
        self.assertAlmostEqual(result["maximum_allowed_loss"], 5.00)

    def test_loss_above_limit(self):
        result = check_risk_limit(5.01, 1000.00, 0.5)
        self.assertFalse(result["within_limit"])

    def test_loss_equal_to_limit_is_allowed_by_comparison(self):
        result = check_risk_limit(5.00, 1000.00, 0.5)
        self.assertTrue(result["within_limit"])

    def test_invalid_tick_size_rejected(self):
        with self.assertRaises(ValueError):
            estimate_price_movement_loss(
                entry_price=4173.96,
                stop_loss=4178.17,
                tick_size=0,
                tick_value_per_lot=1.00,
                volume=0.01,
            )

    def test_zero_volume_rejected(self):
        with self.assertRaises(ValueError):
            estimate_contract_price_movement_loss(
                entry_price=4167.38,
                stop_loss=4162.38,
                contract_size=100,
                volume=0,
            )

    def test_invalid_contract_size_rejected(self):
        with self.assertRaises(ValueError):
            estimate_contract_price_movement_loss(
                entry_price=4167.38,
                stop_loss=4162.38,
                contract_size=-100,
                volume=0.01,
            )

    def test_risk_above_half_percent_rejected(self):
        with self.assertRaises(ValueError):
            calculate_risk_limit(1000.00, 0.6)

    def test_non_finite_equity_rejected(self):
        with self.assertRaises(ValueError):
            calculate_risk_limit(float("inf"), 0.5)



    def test_nan_equity_rejected(self):
        with self.assertRaises(ValueError):
            calculate_risk_limit(float("nan"), 0.5)


    def test_zero_equity_rejected(self):
        with self.assertRaises(ValueError):
            calculate_risk_limit(0, 0.5)


    def test_zero_risk_percentage_rejected(self):
        with self.assertRaises(ValueError):
            calculate_risk_limit(1000, 0)


    def test_negative_estimated_loss_rejected(self):
        with self.assertRaises(ValueError):
            check_risk_limit(-1, 1000, 0.5)


    def test_nan_estimated_loss_rejected(self):
        with self.assertRaises(ValueError):
            check_risk_limit(float("nan"), 1000, 0.5)

if __name__ == "__main__":
    unittest.main()
