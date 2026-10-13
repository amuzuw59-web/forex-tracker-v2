import json
import tempfile
import unittest
from pathlib import Path

from backend.monitor import (
    append_history,
    load_last_processed_candle,
)


class TestMonitorHistory(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.history = Path(self.temp_dir.name) / "history.jsonl"

    def tearDown(self):
        self.temp_dir.cleanup()

    def make_record(self, candle_id, symbol="XAUUSD", timeframe="5m"):
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "candle_id": candle_id,
            "signal": "HOLD",
            "order_submitted": False,
        }

    def test_saved_candle_can_be_recovered(self):
        record = self.make_record("XAUUSD:5m:candle-1")
        append_history(self.history, record, 5000)

        recovered = load_last_processed_candle(
            self.history, "XAUUSD", "5m"
        )

        self.assertEqual(recovered, record["candle_id"])

    def test_history_limit_keeps_latest_entries(self):
        for i in range(5):
            append_history(
                self.history,
                self.make_record(f"candle-{i}"),
                3,
            )

        records = [
            json.loads(line)
            for line in self.history.read_text().splitlines()
        ]

        self.assertEqual(len(records), 3)
        self.assertEqual(records[-1]["candle_id"], "candle-4")
        self.assertEqual(records[0]["candle_id"], "candle-2")

    def test_malformed_line_does_not_hide_valid_record(self):
        record = self.make_record("valid-candle")

        self.history.write_text(
            json.dumps(record) + "\n" + '{"broken":\n',
            encoding="utf-8",
        )

        recovered = load_last_processed_candle(
            self.history, "XAUUSD", "5m"
        )

        self.assertEqual(recovered, "valid-candle")

    def test_other_symbol_is_ignored(self):
        append_history(
            self.history,
            self.make_record("GBPUSD:5m:candle-1", symbol="GBPUSD"),
            5000,
        )

        recovered = load_last_processed_candle(
            self.history, "XAUUSD", "5m"
        )

        self.assertIsNone(recovered)

    def test_missing_history_returns_none(self):
        recovered = load_last_processed_candle(
            self.history, "XAUUSD", "5m"
        )

        self.assertIsNone(recovered)


if __name__ == "__main__":
    unittest.main()
