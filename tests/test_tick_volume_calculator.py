import unittest

from backend.demo_executor import calculate_volume_from_tick_value


class TestTickVolumeCalculator(unittest.TestCase):

    def setUp(self):
        self.valid_inputs = {
            "equity": 10000.0,
            "entry_price": 4200.10,
            "stop_loss": 4190.10,
            "tick_size": 0.01,
            "loss_tick_value": 1.0,
            "risk_percent": 0.5,
            "min_volume": 0.01,
            "max_volume": 100.0,
            "volume_step": 0.01,
        }

    def calculate(self, **overrides):
        inputs = self.valid_inputs.copy()
        inputs.update(overrides)
        return calculate_volume_from_tick_value(**inputs)

    def test_valid_volume_stays_within_risk_limit(self):
        result = self.calculate()

        self.assertGreaterEqual(result["volume"], 0.01)
        self.assertLessEqual(
            result["estimated_loss"],
            result["maximum_allowed_loss"],
        )
        self.assertEqual(
            result["risk_basis"],
            "broker_quote_loss_tick_value",
        )

    def test_volume_respects_broker_step(self):
        result = self.calculate()

        steps = round(
            (result["volume"] - 0.01) / 0.01
        )
        self.assertAlmostEqual(
            result["volume"],
            0.01 + steps * 0.01,
            places=7,
        )

    def test_minimum_volume_above_risk_budget_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "risk limit"):
            self.calculate(
                equity=100.0,
                entry_price=4200.10,
                stop_loss=4190.10,
                min_volume=0.01,
                max_volume=100.0,
                volume_step=0.01,
            )

    def test_zero_tick_size_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "tick_size"):
            self.calculate(tick_size=0.0)

    def test_negative_tick_value_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "loss_tick_value"):
            self.calculate(loss_tick_value=-1.0)

    def test_nan_tick_value_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "loss_tick_value"):
            self.calculate(loss_tick_value=float("nan"))

    def test_boolean_tick_value_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "loss_tick_value"):
            self.calculate(loss_tick_value=True)

    def test_zero_volume_step_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "volume_step"):
            self.calculate(volume_step=0.0)

    def test_inconsistent_volume_limits_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "volume limits"):
            self.calculate(
                min_volume=1.0,
                max_volume=0.1,
            )

    def test_risk_above_half_percent_is_rejected(self):
        with self.assertRaises(ValueError):
            self.calculate(risk_percent=0.6)

    def test_identical_entry_and_stop_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Stop-loss"):
            self.calculate(
                stop_loss=4200.10,
            )


    def test_infinite_tick_value_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "loss_tick_value"):
            self.calculate(loss_tick_value=float("inf"))

    def test_negative_infinite_tick_value_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "loss_tick_value"):
            self.calculate(loss_tick_value=float("-inf"))

    def test_nan_volume_step_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "volume_step"):
            self.calculate(volume_step=float("nan"))

    def test_infinite_equity_is_rejected(self):
        with self.assertRaises(ValueError):
            self.calculate(equity=float("inf"))

    def test_nan_entry_price_is_rejected(self):
        with self.assertRaises(ValueError):
            self.calculate(entry_price=float("nan"))



    def test_volume_never_exceeds_maximum(self):
        result = self.calculate(max_volume=0.05)
        self.assertLessEqual(result["volume"], 0.05)

    def test_volume_is_rounded_down_to_step(self):
        result = self.calculate(
            equity=10000.0,
            entry_price=4200.10,
            stop_loss=4190.10,
            tick_size=0.01,
            loss_tick_value=1.0,
            risk_percent=0.5,
            min_volume=0.01,
            max_volume=100.0,
            volume_step=0.03,
        )
        volume = result["volume"]
        self.assertGreaterEqual(volume, 0.01)
        self.assertAlmostEqual(
            (volume - 0.01) / 0.03,
            round((volume - 0.01) / 0.03),
            places=7,
        )

    def test_minimum_volume_not_aligned_to_zero_step_is_handled(self):
        result = self.calculate(
            min_volume=0.02,
            volume_step=0.03,
        )
        volume = result["volume"]
        self.assertGreaterEqual(volume, 0.02)
        self.assertAlmostEqual(
            (volume - 0.02) / 0.03,
            round((volume - 0.02) / 0.03),
            places=7,
        )


    def test_contract_size_cross_check_accepts_matching_estimates(self):
        result = self.calculate(contract_size=100.0)
        self.assertEqual(
            result["risk_basis"],
            "tick_value_cross_checked_against_contract_size",
        )

    def test_contract_size_cross_check_rejects_mismatch(self):
        with self.assertRaisesRegex(ValueError, "estimates disagree"):
            self.calculate(contract_size=90.0)

    def test_default_cost_reserve_keeps_total_within_risk_limit(self):
        result = self.calculate()
        self.assertEqual(result["cost_reserve_percent"], 20.0)
        self.assertAlmostEqual(result["estimated_cost_reserve"], 10.0)
        self.assertLessEqual(
            result["estimated_total_risk"],
            result["maximum_allowed_loss"],
        )
        self.assertAlmostEqual(result["estimated_total_risk"], 50.0)

    def test_invalid_cost_reserve_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Cost reserve"):
            self.calculate(cost_reserve_percent=100.0)

if __name__ == "__main__":
    unittest.main()
