import unittest

from backend.risk_calculator import (
    estimate_contract_price_movement_loss,
)


class TestContractRisk(unittest.TestCase):

    def test_xauusd_illustrative_loss(self):
        loss = estimate_contract_price_movement_loss(
            entry_price=4200.00,
            stop_loss=4199.00,
            contract_size=100,
            volume=0.01,
        )
        self.assertAlmostEqual(loss, 1.00)

    def test_larger_volume_increases_loss(self):
        loss = estimate_contract_price_movement_loss(
            entry_price=4200.00,
            stop_loss=4199.00,
            contract_size=100,
            volume=0.02,
        )
        self.assertAlmostEqual(loss, 2.00)

    def test_invalid_volume_is_rejected(self):
        with self.assertRaises(ValueError):
            estimate_contract_price_movement_loss(
                entry_price=4200.00,
                stop_loss=4199.00,
                contract_size=100,
                volume=0,
            )

    def test_invalid_contract_size_is_rejected(self):
        with self.assertRaises(ValueError):
            estimate_contract_price_movement_loss(
                entry_price=4200.00,
                stop_loss=4199.00,
                contract_size=0,
                volume=0.01,
            )

    def test_invalid_price_is_rejected(self):
        with self.assertRaises(ValueError):
            estimate_contract_price_movement_loss(
                entry_price=0,
                stop_loss=4199.00,
                contract_size=100,
                volume=0.01,
            )


if __name__ == "__main__":
    unittest.main()
