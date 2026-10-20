import asyncio
import contextlib
import io
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from backend import risk_inspection


class TestRiskInspectionTimestamps(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.server_time = datetime(2026, 10, 20, 8, 0, tzinfo=timezone.utc)
        self.quote_time = self.server_time - timedelta(seconds=10)

        self.api = MagicMock()
        self.api.close = MagicMock()

        account = MagicMock()
        account.wait_connected = AsyncMock()
        account.get_rpc_connection.return_value = MagicMock()
        self.connection = account.get_rpc_connection.return_value

        self.api.metatrader_account_api.get_account = AsyncMock(
            return_value=account
        )
        self.connection.connect = AsyncMock()
        self.connection.wait_synchronized = AsyncMock()
        self.connection.get_account_information = AsyncMock(
            return_value={
                "type": "ACCOUNT_TRADE_MODE_DEMO",
                "currency": "USD",
                "equity": 10000.0,
                "freeMargin": 9000.0,
                "tradeAllowed": True,
                "investorMode": False,
            }
        )
        self.connection.get_symbol_price = AsyncMock(
            return_value={
                "time": self.quote_time,
                "bid": 2000.0,
                "ask": 2000.2,
                "lossTickValue": 1.0,
                "profitTickValue": 1.0,
            }
        )
        self.connection.get_server_time = AsyncMock(
            return_value={"time": self.server_time}
        )
        self.connection.get_symbol_specification = AsyncMock(
            return_value={
                "baseCurrency": "XAU",
                "profitCurrency": "USD",
                "marginCurrency": "USD",
                "contractSize": 100.0,
                "tickSize": 0.01,
                "minVolume": 0.01,
                "volumeStep": 0.01,
            }
        )
        self.connection.calculate_margin = AsyncMock(
            return_value={"margin": 20.0}
        )
        self.connection.close = AsyncMock()

        self.env_patch = patch.dict(
            os.environ,
            {
                "METAAPI_TOKEN": "test-token",
                "METAAPI_ACCOUNT_ID": "test-account",
            },
        )
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

        self.api_patch = patch.object(
            risk_inspection, "MetaApi", return_value=self.api
        )
        self.api_patch.start()
        self.addCleanup(self.api_patch.stop)

    async def inspect_quietly(self):
        with contextlib.redirect_stdout(io.StringIO()):
            await risk_inspection.inspect_risk_data()

    async def test_fresh_timezone_aware_quote_is_accepted(self):
        await self.inspect_quietly()
        self.connection.get_symbol_specification.assert_awaited_once_with(
            "XAUUSD"
        )
        self.connection.close.assert_awaited_once()
        self.api.close.assert_called_once()

    async def test_quote_older_than_60_seconds_is_rejected(self):
        self.connection.get_symbol_price.return_value["time"] = (
            self.server_time - timedelta(seconds=61)
        )
        with self.assertRaisesRegex(RuntimeError, "quote age"):
            await self.inspect_quietly()
        self.connection.get_symbol_specification.assert_not_awaited()

    async def test_future_dated_quote_is_rejected(self):
        self.connection.get_symbol_price.return_value["time"] = (
            self.server_time + timedelta(seconds=1)
        )
        with self.assertRaisesRegex(RuntimeError, "quote age"):
            await self.inspect_quietly()
        self.connection.get_symbol_specification.assert_not_awaited()

    async def test_missing_quote_timestamp_is_rejected(self):
        self.connection.get_symbol_price.return_value.pop("time")
        with self.assertRaisesRegex(RuntimeError, "quote timestamp"):
            await self.inspect_quietly()
        self.connection.get_symbol_specification.assert_not_awaited()

    async def test_non_datetime_quote_timestamp_is_rejected(self):
        self.connection.get_symbol_price.return_value["time"] = "not-a-date"
        with self.assertRaisesRegex(RuntimeError, "quote timestamp"):
            await self.inspect_quietly()

    async def test_timezone_naive_quote_timestamp_is_rejected(self):
        self.connection.get_symbol_price.return_value["time"] = (
            self.server_time.replace(tzinfo=None)
        )
        with self.assertRaisesRegex(RuntimeError, "has no timezone"):
            await self.inspect_quietly()

    async def test_missing_server_timestamp_is_rejected(self):
        self.connection.get_server_time.return_value = {}
        with self.assertRaisesRegex(RuntimeError, "server time"):
            await self.inspect_quietly()
        self.connection.get_symbol_specification.assert_not_awaited()

    async def test_timezone_naive_server_timestamp_is_rejected(self):
        self.connection.get_server_time.return_value = {
            "time": self.server_time.replace(tzinfo=None)
        }
        with self.assertRaisesRegex(RuntimeError, "has no timezone"):
            await self.inspect_quietly()


if __name__ == "__main__":
    unittest.main()
