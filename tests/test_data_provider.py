import os
import unittest
from unittest.mock import patch, MagicMock, AsyncMock

from backend import data_provider


class TestDataProvider(unittest.IsolatedAsyncioTestCase):

    async def test_missing_credentials_fails_safely(self):
        with patch.dict(os.environ, {
            "METAAPI_TOKEN": "",
            "METAAPI_ACCOUNT_ID": "",
        }), patch.object(data_provider, "MetaApi") as mock_api:
            with self.assertRaisesRegex(
                RuntimeError, "credentials are missing"
            ):
                await data_provider.fetch_candles()

            mock_api.assert_not_called()

    async def test_empty_candle_response_is_rejected(self):
        api = MagicMock()
        api._metaapi_websocket_client.close = AsyncMock()
        api._metaapi_websocket_client.stop = MagicMock()
        api._terminal_hash_manager._stop = MagicMock()
        account = MagicMock()
        connection = MagicMock()

        api.metatrader_account_api.get_account = AsyncMock(
            return_value=account
        )
        account.get_rpc_connection.return_value = connection
        connection.connect = AsyncMock()
        connection.wait_synchronized = AsyncMock()
        connection.close = AsyncMock()
        account.get_historical_candles = AsyncMock(return_value=[])

        async def complete_awaitable(awaitable, timeout):
            return await awaitable

        with patch.dict(os.environ, {
            "METAAPI_TOKEN": "test-token",
            "METAAPI_ACCOUNT_ID": "test-account",
        }), patch.object(
            data_provider, "MetaApi", return_value=api
        ), patch.object(
            data_provider,
            "load_market_config",
            return_value=(
                {
                    "symbol": "XAUUSD",
                    "timeframe": "5m",
                    "candle_count": 100,
                },
                {},
            ),
        ), patch.object(
            data_provider.asyncio,
            "wait_for",
            new=complete_awaitable,
        ):
            with self.assertRaisesRegex(RuntimeError, "no candles"):
                await data_provider.fetch_candles()

        connection.close.assert_awaited_once()


    async def test_sync_timeout_still_closes_rpc_connection(self):
        api = MagicMock()
        api._metaapi_websocket_client.close = AsyncMock()
        api._metaapi_websocket_client.stop = MagicMock()
        api._terminal_hash_manager._stop = MagicMock()

        account = MagicMock()
        connection = MagicMock()

        api.metatrader_account_api.get_account = AsyncMock(
            return_value=account
        )
        account.get_rpc_connection.return_value = connection
        connection.connect = AsyncMock()
        connection.wait_synchronized = AsyncMock(
            side_effect=TimeoutError("simulated synchronization timeout")
        )
        connection.close = AsyncMock()

        async def complete_awaitable(awaitable, timeout):
            return await awaitable

        with patch.dict("os.environ", {
            "METAAPI_TOKEN": "test-token",
            "METAAPI_ACCOUNT_ID": "test-account",
        }), patch.object(
            data_provider, "MetaApi", return_value=api
        ), patch.object(
            data_provider,
            "load_market_config",
            return_value=({"symbol": "XAUUSD", "timeframe": "5m",
                           "candle_count": 100}, {}),
        ), patch.object(
            data_provider.asyncio, "wait_for",
            new=complete_awaitable,
        ):
            with self.assertRaisesRegex(
                TimeoutError, "simulated synchronization timeout"
            ):
                await data_provider.fetch_candles()

        connection.close.assert_awaited_once()
        account.get_historical_candles.assert_not_called()


    async def _run_timestamp_validation_test(self, timestamp):
        import pandas as pd
        from datetime import datetime, timedelta, timezone

        api = MagicMock()
        api._metaapi_websocket_client.close = AsyncMock()
        api._metaapi_websocket_client.stop = MagicMock()
        api._terminal_hash_manager._stop = MagicMock()

        account = MagicMock()
        connection = MagicMock()
        api.metatrader_account_api.get_account = AsyncMock(
            return_value=account
        )
        account.get_rpc_connection.return_value = connection
        connection.connect = AsyncMock()
        connection.wait_synchronized = AsyncMock()
        connection.close = AsyncMock()

        now = datetime.now(timezone.utc)
        # Shift the entire candle series so that the latest closed candle
        # has the exact timestamp under test. The final candle is treated
        # as the potentially forming candle and removed by the provider.
        normal_latest_closed = now - timedelta(minutes=5)
        time_shift = timestamp - normal_latest_closed

        candles = []
        for i in range(100):
            candle_time = (
                now - timedelta(minutes=5 * (99 - i)) + time_shift
            )
            candles.append({
                "time": candle_time.isoformat(),
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.0,
            })
        account.get_historical_candles = AsyncMock(return_value=candles)

        async def complete_awaitable(awaitable, timeout):
            return await awaitable

        with patch.dict("os.environ", {
            "METAAPI_TOKEN": "test-token",
            "METAAPI_ACCOUNT_ID": "test-account",
        }), patch.object(
            data_provider, "MetaApi", return_value=api
        ), patch.object(
            data_provider, "load_market_config",
            return_value=(
                {"symbol": "XAUUSD", "timeframe": "5m",
                 "candle_count": 100},
                {"max_candle_age_minutes": {"5m": 20}},
            ),
        ), patch.object(
            data_provider.asyncio, "wait_for",
            new=complete_awaitable,
        ):
            with self.assertRaisesRegex(RuntimeError, "stale"):
                await data_provider.fetch_candles()

        connection.close.assert_awaited_once()

    async def test_stale_closed_candle_is_rejected(self):
        from datetime import datetime, timedelta, timezone
        old_time = datetime.now(timezone.utc) - timedelta(hours=3)
        await self._run_timestamp_validation_test(old_time)

    async def test_future_dated_closed_candle_is_rejected(self):
        from datetime import datetime, timedelta, timezone
        future_time = datetime.now(timezone.utc) + timedelta(minutes=10)
        await self._run_timestamp_validation_test(future_time)


if __name__ == "__main__":
    unittest.main()
