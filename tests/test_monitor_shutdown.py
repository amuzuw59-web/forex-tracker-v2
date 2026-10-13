import asyncio
import unittest
from unittest.mock import patch

from backend import monitor


class TestMonitorShutdown(unittest.IsolatedAsyncioTestCase):
    async def test_request_stop_sets_event_on_running_loop(self):
        event = asyncio.Event()
        loop = asyncio.get_running_loop()

        with (
            patch.object(monitor, "STOP_EVENT", event),
            patch.object(monitor, "STOP_LOOP", loop),
        ):
            monitor.request_stop()

            await asyncio.wait_for(event.wait(), timeout=1)

        self.assertTrue(event.is_set())

    def test_request_stop_is_safe_before_monitor_starts(self):
        with (
            patch.object(monitor, "STOP_EVENT", None),
            patch.object(monitor, "STOP_LOOP", None),
        ):
            monitor.request_stop()

    def test_request_stop_is_safe_with_closed_loop(self):
        loop = asyncio.new_event_loop()
        loop.close()

        with (
            patch.object(monitor, "STOP_EVENT", asyncio.Event()),
            patch.object(monitor, "STOP_LOOP", loop),
        ):
            monitor.request_stop()


if __name__ == "__main__":
    unittest.main()
