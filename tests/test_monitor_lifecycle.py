import asyncio
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from backend import monitor


class TestMonitorLifecycle(unittest.IsolatedAsyncioTestCase):
    async def test_monitor_stops_after_stop_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            history_path = Path(tmp) / "history.jsonl"
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
                return "XAUUSD", "5m", pd.DataFrame()

            # Prevent a stale event from a previous test affecting this run.
            monitor.STOP_EVENT = None
            monitor.STOP_LOOP = None

            with (
                patch.object(monitor, "load_config", return_value=config),
                patch.object(
                    monitor,
                    "load_last_processed_candle",
                    return_value=None,
                ),
                patch.object(
                    monitor,
                    "get_candles",
                    side_effect=fake_get_candles,
                ) as fetch,
            ):
                task = asyncio.create_task(monitor.monitor())

                try:
                    started = await asyncio.to_thread(
                        fetch_started.wait, 2
                    )
                    self.assertTrue(started, "Monitor did not start fetching.")

                    monitor.request_stop()
                    await asyncio.wait_for(task, timeout=2)

                    self.assertEqual(fetch.call_count, 1)
                    self.assertFalse(history_path.exists())
                finally:
                    if not task.done():
                        monitor.request_stop()
                        await asyncio.wait_for(task, timeout=2)

    async def test_monitor_starts_and_stops_in_read_only_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            history_path = Path(tmp) / "history.jsonl"
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
                return "XAUUSD", "5m", pd.DataFrame()

            monitor.STOP_EVENT = None
            monitor.STOP_LOOP = None

            with (
                patch.object(monitor, "load_config", return_value=config),
                patch.object(
                    monitor,
                    "load_last_processed_candle",
                    return_value=None,
                ),
                patch.object(
                    monitor,
                    "get_candles",
                    side_effect=fake_get_candles,
                ),
            ):
                task = asyncio.create_task(monitor.monitor())

                try:
                    started = await asyncio.to_thread(
                        fetch_started.wait, 2
                    )
                    self.assertTrue(started)
                    monitor.request_stop()
                    await asyncio.wait_for(task, timeout=2)
                finally:
                    if not task.done():
                        monitor.request_stop()
                        await asyncio.wait_for(task, timeout=2)

                self.assertFalse(history_path.exists())


if __name__ == "__main__":
    unittest.main()
