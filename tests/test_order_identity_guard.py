import tempfile
import unittest
from pathlib import Path

from backend.order_guard import reserve_signal
from backend.signal_identity import make_signal_identity


class TestOrderIdentityGuard(unittest.TestCase):

    def test_equivalent_timestamps_share_identity(self):
        first = make_signal_identity(
            "XAUUSD", "5m", "2026-10-12T10:00:00Z"
        )
        second = make_signal_identity(
            "xauusd", "5M", "2026-10-12T12:00:00+02:00"
        )
        self.assertEqual(first, second)

    def test_equivalent_id_cannot_be_reserved_twice(self):
        first = make_signal_identity(
            "XAUUSD", "5m", "2026-10-12T10:00:00Z"
        )
        second = make_signal_identity(
            "xauusd", "5M", "2026-10-12T12:00:00+02:00"
        )

        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"

            self.assertTrue(
                reserve_signal("XAUUSD", "5m", first, state)
            )
            self.assertFalse(
                reserve_signal("XAUUSD", "5m", second, state)
            )


if __name__ == "__main__":
    unittest.main()
