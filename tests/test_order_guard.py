import json
import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from tempfile import TemporaryDirectory
from backend.order_guard import reserve_signal


class TestOrderGuard(unittest.TestCase):
    def test_first_signal_is_reserved(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            self.assertTrue(reserve_signal("XAUUSD", "5m", "candle-1", state))
            data = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(len(data["reserved_signals"]), 1)

    def test_duplicate_signal_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            self.assertTrue(reserve_signal("XAUUSD", "5m", "candle-1", state))
            self.assertFalse(reserve_signal("XAUUSD", "5m", "candle-1", state))

    def test_different_candle_can_be_reserved(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            self.assertTrue(reserve_signal("XAUUSD", "5m", "candle-1", state))
            self.assertTrue(reserve_signal("XAUUSD", "5m", "candle-2", state))

    def test_corrupt_state_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            state.write_text("{broken", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "unreadable"):
                reserve_signal("XAUUSD", "5m", "candle-1", state)


    def test_concurrent_duplicate_reservation_allows_only_one(self):
        from concurrent.futures import ThreadPoolExecutor
        from pathlib import Path
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"

            def reserve(_):
                return reserve_signal(
                    "XAUUSD",
                    "5m",
                    "concurrent-candle",
                    state,
                )

            with ThreadPoolExecutor(max_workers=10) as pool:
                results = list(pool.map(reserve, range(10)))

            self.assertEqual(len(results), 10)
            self.assertEqual(sum(results), 1)
            self.assertEqual(results.count(False), 9)

if __name__ == "__main__":
    unittest.main()
