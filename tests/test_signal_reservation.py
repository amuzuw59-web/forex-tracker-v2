import tempfile
import unittest
from pathlib import Path

from backend.signal_identity import reserve_signal_identity


class TestSignalReservation(unittest.TestCase):
    def test_first_candle_can_be_reserved(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"

            result = reserve_signal_identity(
                "XAUUSD", "5m", "2026-10-12T10:00:00Z", state
            )

            self.assertTrue(result)

    def test_equivalent_timezone_timestamp_is_duplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"

            first = reserve_signal_identity(
                "XAUUSD", "5m", "2026-10-12T10:00:00Z", state
            )
            second = reserve_signal_identity(
                "xauusd", "5M", "2026-10-12T12:00:00+02:00", state
            )

            self.assertTrue(first)
            self.assertFalse(second)

    def test_invalid_naive_timestamp_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"

            with self.assertRaisesRegex(ValueError, "timezone"):
                reserve_signal_identity(
                    "XAUUSD", "5m", "2026-10-12T10:00:00", state
                )


if __name__ == "__main__":
    unittest.main()
