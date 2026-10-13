import asyncio
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from backend import monitor


class TestMonitorDeduplication(unittest.IsolatedAsyncioTestCase):
    async def test_repeated_candle_is_not_saved_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            history_path = Path(tmp) / "history.jsonl"
            candle_time = pd.Timestamp("2026-10-13T08:00:00Z")
            candle_id = f"XAUUSD:5m:{candle_time.isoformat()}"

            existing_record = {
                "symbol": "XAUUSD",
                "timeframe": "5m",
                "candle_id": candle_id,
                "signal": "HOLD",
                "trading_enabled": False,
                "order_submitted": False,
            }
            history_path.write_text(
                json.dumps(existing_record) + "\n",
                encoding="utf-8",
            )

            config = {
                "market": {
                    "symbol": "XAUUSD",
                    "timeframe": "5m",
                },
                "monitor": {
                    "poll_seconds": 30,
                    "max_history_entries": 10,
                    "signal_history_file": str(history_path),
                },
            }

            fetch_started = threading.Event()

            def fake_get_candles():
                fetch_started.set()
                return (
                    "XAUUSD",
                    "5m",
                    pd.DataFrame({"datetime": [candle_time]}),
                )

            monitor.STOP_EVENT = None
            monitor.STOP_LOOP = None

            with (
                patch.object(monitor, "load_config", return_value=config),
                patch.object(monitor, "get_candles", side_effect=fake_get_candles),
                patch.object(monitor, "analyze_candles") as analyze,
            ):
                task = asyncio.create_task(monitor.monitor())

                try:
                    started = await asyncio.to_thread(
                        fetch_started.wait, 2
                    )
                    self.assertTrue(started, "Monitor did not fetch mock data.")

                    # Allow the monitor to process the duplicate.
                    await asyncio.sleep(0.05)
                    monitor.request_stop()
                    await asyncio.wait_for(task, timeout=2)
                finally:
                    if not task.done():
                        monitor.request_stop()
                        await asyncio.wait_for(task, timeout=2)

            records = [
                json.loads(line)
                for line in history_path.read_text(
                    encoding="utf-8"
                ).splitlines()
            ]

            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["candle_id"], candle_id)
            analyze.assert_not_called()


if __name__ == "__main__":
    unittest.main()
