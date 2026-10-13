import unittest

from backend.signal_identity import (
    make_candle_id,
    make_signal_identity,
)


class TestSignalIdentity(unittest.TestCase):

    def test_equivalent_timezones_produce_same_candle_id(self):
        first = make_candle_id("2026-10-12T08:00:00Z")
        second = make_candle_id("2026-10-12T08:00:00+00:00")

        self.assertEqual(first, second)

    def test_different_candles_produce_different_ids(self):
        first = make_candle_id("2026-10-12T08:00:00Z")
        second = make_candle_id("2026-10-12T08:05:00Z")

        self.assertNotEqual(first, second)

    def test_signal_identity_normalizes_symbol_and_timeframe(self):
        first = make_signal_identity(
            "XAUUSD", "5m", "2026-10-12T08:00:00Z"
        )
        second = make_signal_identity(
            "xauusd", "5M", "2026-10-12T08:00:00+00:00"
        )

        self.assertEqual(first, second)

    def test_empty_timestamp_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "required"):
            make_candle_id("")

    def test_invalid_timestamp_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Invalid"):
            make_candle_id("not-a-timestamp")

    def test_timezone_naive_timestamp_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "timezone"):
            make_candle_id("2026-10-12T08:00:00")

    def test_empty_symbol_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "symbol"):
            make_signal_identity(
                "", "5m", "2026-10-12T08:00:00Z"
            )

    def test_empty_timeframe_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "timeframe"):
            make_signal_identity(
                "XAUUSD", "", "2026-10-12T08:00:00Z"
            )


if __name__ == "__main__":
    unittest.main()
