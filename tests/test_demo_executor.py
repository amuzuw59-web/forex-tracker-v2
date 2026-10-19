from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from backend.demo_executor import (
    calculate_volume,
    calculate_volume_from_tick_value,
    execute_demo_signal,
    validate_signal_freshness,
    validate_broker_quote_freshness,
)


class TestDemoExecutorSafety(unittest.IsolatedAsyncioTestCase):
    async def test_unverified_monetary_risk_blocks_submission(self):
        config = {
            "trading": {
                "enabled": True,
                "submission_enabled": True,
                "monetary_risk_independently_verified": False,
                "require_demo_account": True,
                "require_manual_confirmation": True,
                "max_open_positions": 1,
                "max_risk_percent": 0.5,
            },
            "market": {"symbol": "XAUUSD", "timeframe": "5m"},
            "data": {"max_candle_age_minutes": {"5m": 20}},
        }

        with (
            patch("backend.demo_executor.load_config", return_value=config),
            patch("backend.demo_executor.MetaApi") as meta_api,
        ):
            result = await execute_demo_signal(
                {"signal": "BUY"},
                "risk-verification-test",
                datetime.now(timezone.utc).isoformat(),
                manual_confirmation=True,
            )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(
            result["risk_validation"],
            "pending_broker_value_verification",
        )
        self.assertFalse(result["automatic_order_submitted"])
        meta_api.assert_not_called()


    async def test_disabled_trading_stops_before_broker_connection(self):
        with patch(
            "backend.demo_executor.load_config",
            return_value={
                "trading": {"enabled": False},
                "market": {"symbol": "XAUUSD", "timeframe": "5m"},
            },
        ), patch("backend.demo_executor.MetaApi") as meta_api:
            result = await execute_demo_signal(
                {"signal": "BUY"},
                "test-candle-1",
                "2026-10-12T14:45:00+00:00",
            )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "Trading is disabled.")
        meta_api.assert_not_called()

    async def test_hold_signal_is_rejected_when_execution_enabled(self):
        with patch(
            "backend.demo_executor.load_config",
            return_value={
                "trading": {
                    "enabled": True,
                    "require_demo_account": True,
                },
                "market": {"symbol": "XAUUSD", "timeframe": "5m"},
                "data": {"max_candle_age_minutes": {"5m": 20}},
            },
        ), patch("backend.demo_executor.MetaApi") as meta_api:
            result = await execute_demo_signal(
                {"signal": "HOLD"},
                "test-candle-2",
                "2026-10-12T14:45:00+00:00",
            )

        self.assertEqual(result["status"], "blocked")
        self.assertIn("BUY or SELL", result["reason"])
        meta_api.assert_not_called()

    async def test_missing_candle_id_is_rejected(self):
        with patch(
            "backend.demo_executor.load_config",
            return_value={
                "trading": {
                    "enabled": True,
                    "require_demo_account": True,
                },
                "market": {"symbol": "XAUUSD", "timeframe": "5m"},
                "data": {"max_candle_age_minutes": {"5m": 20}},
            },
        ), patch("backend.demo_executor.MetaApi") as meta_api:
            result = await execute_demo_signal(
                {"signal": "BUY"},
                "",
                "2026-10-12T14:45:00+00:00",
            )

        self.assertEqual(result["status"], "blocked")
        self.assertIn("candle ID", result["reason"])
        meta_api.assert_not_called()

    def test_future_candle_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "future"):
            validate_signal_freshness(
                "2099-01-01T00:00:00+00:00",
                "5m",
                {
                    "data": {
                        "max_candle_age_minutes": {"5m": 20}
                    }
                },
            )

    def test_naive_timestamp_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "timezone"):
            validate_signal_freshness(
                "2026-10-12T14:45:00",
                "5m",
                {
                    "data": {
                        "max_candle_age_minutes": {"5m": 20}
                    }
                },
            )

    def test_stale_candle_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "stale"):
            validate_signal_freshness(
                "2020-01-01T00:00:00+00:00",
                "5m",
                {
                    "data": {
                        "max_candle_age_minutes": {"5m": 20}
                    }
                },
            )

    def test_volume_calculation_respects_risk_limit(self):
        result = calculate_volume(
            equity=10000,
            entry_price=4200,
            stop_loss=4190,
            contract_size=100,
            risk_percent=0.5,
            min_volume=0.01,
            max_volume=100,
            volume_step=0.01,
        )

        self.assertLessEqual(
            result["estimated_loss"],
            result["maximum_allowed_loss"],
        )
        self.assertGreaterEqual(result["volume"], 0.01)

    def test_volume_rejects_risk_above_half_percent(self):
        with self.assertRaisesRegex(ValueError, "cannot exceed 0.5%"):
            calculate_volume(
                equity=10000,
                entry_price=4200,
                stop_loss=4190,
                contract_size=100,
                risk_percent=0.6,
                min_volume=0.01,
                max_volume=100,
                volume_step=0.01,
            )



    def test_zero_volume_step_is_rejected(self):
        with self.assertRaises(ValueError):
            calculate_volume(
                equity=10000,
                entry_price=4200,
                stop_loss=4190,
                contract_size=100,
                risk_percent=0.5,
                min_volume=0.01,
                max_volume=100,
                volume_step=0,
            )

    def test_minimum_volume_above_risk_budget_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "risk limit"):
            calculate_volume(
                equity=100,
                entry_price=4200,
                stop_loss=4190,
                contract_size=100,
                risk_percent=0.5,
                min_volume=0.01,
                max_volume=100,
                volume_step=0.01,
            )

    def test_volume_limits_must_be_consistent(self):
        with self.assertRaises(ValueError):
            calculate_volume(
                equity=10000,
                entry_price=4200,
                stop_loss=4190,
                contract_size=100,
                risk_percent=0.5,
                min_volume=1.0,
                max_volume=0.1,
                volume_step=0.01,
            )

    def test_negative_risk_percentage_is_rejected(self):
        with self.assertRaises(ValueError):
            calculate_volume(
                equity=10000,
                entry_price=4200,
                stop_loss=4190,
                contract_size=100,
                risk_percent=-0.1,
                min_volume=0.01,
                max_volume=100,
                volume_step=0.01,
            )

    async def test_manual_confirmation_required_before_broker_connection(self):
        from datetime import datetime, timezone

        config = {
            "trading": {
                "enabled": True,
                "require_demo_account": True,
                "require_manual_confirmation": True,
            },
            "market": {"symbol": "XAUUSD", "timeframe": "5m"},
            "data": {"max_candle_age_minutes": {"5m": 20}},
        }

        with patch(
            "backend.demo_executor.load_config",
            return_value=config,
        ), patch("backend.demo_executor.MetaApi") as meta_api:
            result = await execute_demo_signal(
                {"signal": "BUY"},
                "test-candle-manual-confirmation",
                datetime.now(timezone.utc).isoformat(),
                manual_confirmation=False,
            )

        self.assertEqual(result["status"], "blocked")
        self.assertIn("manual confirmation", result["reason"])
        meta_api.assert_not_called()


    async def test_submission_disabled_after_successful_validation(self):
        from unittest.mock import AsyncMock, MagicMock

        config = {
            "trading": {
                "enabled": True,
                "require_demo_account": True,
                "require_manual_confirmation": True,
                "max_open_positions": 1,
                "max_risk_percent": 0.5,
                "submission_enabled": False,
            },
            "market": {"symbol": "XAUUSD", "timeframe": "5m"},
            "data": {"max_candle_age_minutes": {"5m": 20}},
        }

        connection = MagicMock()
        connection.connect = AsyncMock()
        connection.wait_synchronized = AsyncMock()
        connection.get_account_information = AsyncMock(return_value={
            "type": "ACCOUNT_TRADE_MODE_DEMO",
            "tradeAllowed": True,
            "investorMode": False,
            "equity": 10000.0,
        })
        connection.get_symbol_specification = AsyncMock(return_value={
            "tickSize": 0.01,
                    "contractSize": 100.0,
            "minVolume": 0.01,
            "maxVolume": 100.0,
            "volumeStep": 0.01,
        })
        connection.get_symbol_price = AsyncMock(return_value={
            "time": datetime.now(timezone.utc).isoformat(),
            "bid": 4200.0,
            "ask": 4200.1,
            "lossTickValue": 1.0,
        })
        connection.get_positions = AsyncMock(return_value=[])
        connection.get_orders = AsyncMock(return_value=[])
        connection.close = AsyncMock()

        account = MagicMock()
        account.get_rpc_connection.return_value = connection

        account_api = MagicMock()
        account_api.get_account = AsyncMock(return_value=account)

        api = MagicMock()
        api.metatrader_account_api = account_api

        with (
            patch("backend.demo_executor.load_config", return_value=config),
            patch("backend.demo_executor.MetaApi", return_value=api),
            patch.dict("os.environ", {
                "METAAPI_TOKEN": "test-token",
                "METAAPI_ACCOUNT_ID": "test-account",
            }),
            patch("backend.demo_executor.submit_signal_once",
                  new_callable=AsyncMock) as submit,
        ):
            result = await execute_demo_signal(
                {
                    "signal": "BUY",
                    "stop_loss": 4190.0,
                    "take_profit": 4220.0,
                },
                "test-submission-disabled",
                datetime.now(timezone.utc).isoformat(),
                manual_confirmation=True,
            )

        self.assertEqual(result["status"], "validated_not_submitted")
        self.assertFalse(result["automatic_order_submitted"])
        submit.assert_not_awaited()
        connection.close.assert_awaited_once()
        api.close.assert_called_once()




    async def test_prepare_only_never_submits_order(self):
        from unittest.mock import AsyncMock, MagicMock

        config = {
            "trading": {
                "enabled": False,
                "require_demo_account": True,
                "require_manual_confirmation": True,
                "max_open_positions": 1,
                "max_risk_percent": 0.5,
                "submission_enabled": False,
                "monetary_risk_independently_verified": False,
            },
            "market": {"symbol": "XAUUSD", "timeframe": "5m"},
            "data": {"max_candle_age_minutes": {"5m": 20}},
        }

        connection = MagicMock()
        connection.connect = AsyncMock()
        connection.wait_synchronized = AsyncMock()
        connection.get_account_information = AsyncMock(return_value={
            "type": "ACCOUNT_TRADE_MODE_DEMO",
            "tradeAllowed": True,
            "investorMode": False,
            "equity": 10000.0,
        })
        connection.get_symbol_specification = AsyncMock(return_value={
            "tickSize": 0.01,
            "contractSize": 100.0,
            "minVolume": 0.01,
            "maxVolume": 100.0,
            "volumeStep": 0.01,
        })
        connection.get_symbol_price = AsyncMock(return_value={
            "time": datetime.now(timezone.utc).isoformat(),
            "bid": 4200.0,
            "ask": 4200.1,
            "lossTickValue": 1.0,
        })
        connection.get_positions = AsyncMock(return_value=[])
        connection.get_orders = AsyncMock(return_value=[])
        connection.close = AsyncMock()

        account = MagicMock()
        account.get_rpc_connection.return_value = connection

        account_api = MagicMock()
        account_api.get_account = AsyncMock(return_value=account)

        api = MagicMock()
        api.metatrader_account_api = account_api

        with (
            patch("backend.demo_executor.load_config", return_value=config),
            patch("backend.demo_executor.MetaApi", return_value=api),
            patch.dict("os.environ", {
                "METAAPI_TOKEN": "test-token",
                "METAAPI_ACCOUNT_ID": "test-account",
            }),
            patch(
                "backend.demo_executor.submit_signal_once",
                new_callable=AsyncMock,
            ) as submit,
        ):
            result = await execute_demo_signal(
                {
                    "signal": "BUY",
                    "stop_loss": 4190.0,
                    "take_profit": 4220.0,
                },
                "test-prepare-only",
                datetime.now(timezone.utc).isoformat(),
                prepare_only=True,
            )

        self.assertEqual(result["status"], "proposal_ready")
        self.assertFalse(result["automatic_order_submitted"])
        submit.assert_not_awaited()
        connection.close.assert_awaited_once()
        api.close.assert_called_once()

    async def test_stale_broker_quote_blocks_before_positions_check(self):
        from datetime import timedelta
        from unittest.mock import AsyncMock, MagicMock

        config = {
            "trading": {
                "enabled": True,
                "require_demo_account": True,
                "require_manual_confirmation": True,
                "max_open_positions": 1,
                "max_risk_percent": 0.5,
                "submission_enabled": False,
            },
            "market": {"symbol": "XAUUSD", "timeframe": "5m"},
            "data": {
                "max_candle_age_minutes": {"5m": 20},
                "max_quote_age_seconds": 60,
            },
        }

        stale_time = (
            datetime.now(timezone.utc) - timedelta(seconds=120)
        ).isoformat()

        connection = MagicMock()
        connection.connect = AsyncMock()
        connection.wait_synchronized = AsyncMock()
        connection.get_account_information = AsyncMock(return_value={
            "type": "ACCOUNT_TRADE_MODE_DEMO",
            "tradeAllowed": True,
            "investorMode": False,
            "equity": 10000.0,
        })
        connection.get_symbol_specification = AsyncMock(return_value={
            "tickSize": 0.01,
            "contractSize": 100.0,
            "minVolume": 0.01,
            "maxVolume": 100.0,
            "volumeStep": 0.01,
        })
        connection.get_symbol_price = AsyncMock(return_value={
            "time": stale_time,
            "bid": 4200.0,
            "ask": 4200.1,
            "lossTickValue": 1.0,
        })
        connection.get_positions = AsyncMock(return_value=[])
        connection.get_orders = AsyncMock(return_value=[])
        connection.close = AsyncMock()

        account = MagicMock()
        account.get_rpc_connection.return_value = connection
        account_api = MagicMock()
        account_api.get_account = AsyncMock(return_value=account)
        api = MagicMock()
        api.metatrader_account_api = account_api

        with (
            patch("backend.demo_executor.load_config", return_value=config),
            patch("backend.demo_executor.MetaApi", return_value=api),
            patch.dict("os.environ", {
                "METAAPI_TOKEN": "test-token",
                "METAAPI_ACCOUNT_ID": "test-account",
            }),
            patch(
                "backend.demo_executor.submit_signal_once",
                new_callable=AsyncMock,
            ) as submit,
        ):
            result = await execute_demo_signal(
                {
                    "signal": "BUY",
                    "stop_loss": 4190.0,
                    "take_profit": 4220.0,
                },
                "test-stale-broker-quote",
                datetime.now(timezone.utc).isoformat(),
                manual_confirmation=True,
            )

        self.assertEqual(result["status"], "blocked")
        self.assertIn("stale", result["reason"].lower())
        connection.get_positions.assert_not_awaited()
        connection.get_orders.assert_not_awaited()
        submit.assert_not_awaited()
        connection.close.assert_awaited_once()

    async def test_existing_open_order_blocks_execution(self):
        from unittest.mock import AsyncMock, MagicMock

        config = {
            "trading": {
                "enabled": True,
                "require_demo_account": True,
                "require_manual_confirmation": True,
                "max_open_positions": 1,
                "max_risk_percent": 0.5,
                "submission_enabled": False,
            },
            "market": {"symbol": "XAUUSD", "timeframe": "5m"},
            "data": {"max_candle_age_minutes": {"5m": 20}},
        }

        connection = MagicMock()
        connection.connect = AsyncMock()
        connection.wait_synchronized = AsyncMock()
        connection.get_account_information = AsyncMock(return_value={
            "type": "ACCOUNT_TRADE_MODE_DEMO",
            "tradeAllowed": True,
            "investorMode": False,
            "equity": 10000.0,
        })
        connection.get_symbol_specification = AsyncMock(return_value={
            "tickSize": 0.01,
                    "contractSize": 100.0,
            "minVolume": 0.01,
            "maxVolume": 100.0,
            "volumeStep": 0.01,
        })
        connection.get_symbol_price = AsyncMock(return_value={
            "time": datetime.now(timezone.utc).isoformat(),
            "bid": 4200.0,
            "ask": 4200.1,
            "lossTickValue": 1.0,
        })
        connection.get_positions = AsyncMock(return_value=[])
        connection.get_orders = AsyncMock(
            return_value=[{"id": "pending-test-order"}]
        )
        connection.close = AsyncMock()

        account = MagicMock()
        account.get_rpc_connection.return_value = connection

        account_api = MagicMock()
        account_api.get_account = AsyncMock(return_value=account)

        api = MagicMock()
        api.metatrader_account_api = account_api

        with (
            patch("backend.demo_executor.load_config", return_value=config),
            patch("backend.demo_executor.MetaApi", return_value=api),
            patch.dict("os.environ", {
                "METAAPI_TOKEN": "test-token",
                "METAAPI_ACCOUNT_ID": "test-account",
            }),
            patch("backend.demo_executor.submit_signal_once",
                  new_callable=AsyncMock) as submit,
        ):
            result = await execute_demo_signal(
                {
                    "signal": "BUY",
                    "stop_loss": 4190.0,
                    "take_profit": 4220.0,
                },
                "test-existing-pending-order",
                datetime.now(timezone.utc).isoformat(),
                manual_confirmation=True,
            )

        self.assertEqual(result["status"], "blocked")
        self.assertIn("Open orders exist", result["reason"])
        self.assertFalse(result["automatic_order_submitted"])
        submit.assert_not_awaited()
        connection.close.assert_awaited_once()
        api.close.assert_called_once()


    async def test_concurrent_executions_serialize_account_checks(self):
        import asyncio
        from unittest.mock import AsyncMock, MagicMock

        config = {
            "trading": {
                "enabled": True,
                "require_demo_account": True,
                "require_manual_confirmation": True,
                "max_open_positions": 1,
                "max_risk_percent": 0.5,
                "submission_enabled": False,
            },
            "market": {"symbol": "XAUUSD", "timeframe": "5m"},
            "data": {"max_candle_age_minutes": {"5m": 20}},
        }

        first_positions_started = asyncio.Event()
        release_first_positions = asyncio.Event()

        def make_api(first=False):
            connection = MagicMock()
            connection.connect = AsyncMock()
            connection.wait_synchronized = AsyncMock()
            connection.get_account_information = AsyncMock(return_value={
                "type": "ACCOUNT_TRADE_MODE_DEMO",
                "tradeAllowed": True,
                "investorMode": False,
                "equity": 10000.0,
            })
            connection.get_symbol_specification = AsyncMock(return_value={
                "tickSize": 0.01,
                    "contractSize": 100.0,
                "minVolume": 0.01,
                "maxVolume": 100.0,
                "volumeStep": 0.01,
            })
            connection.get_symbol_price = AsyncMock(return_value={
                "time": datetime.now(timezone.utc).isoformat(),
                "bid": 4200.0,
                "ask": 4200.1,
                "lossTickValue": 1.0,
            })
            connection.get_orders = AsyncMock(return_value=[])
            connection.close = AsyncMock()

            if first:
                async def first_get_positions():
                    first_positions_started.set()
                    await release_first_positions.wait()
                    return []
                connection.get_positions = AsyncMock(
                    side_effect=first_get_positions
                )
            else:
                connection.get_positions = AsyncMock(return_value=[])

            account = MagicMock()
            account.get_rpc_connection.return_value = connection

            account_api = MagicMock()
            account_api.get_account = AsyncMock(return_value=account)

            api = MagicMock()
            api.metatrader_account_api = account_api
            return api, connection

        api1, connection1 = make_api(first=True)
        api2, connection2 = make_api()

        with (
            patch("backend.demo_executor.load_config", return_value=config),
            patch(
                "backend.demo_executor.MetaApi",
                side_effect=[api1, api2],
            ),
            patch.dict("os.environ", {
                "METAAPI_TOKEN": "test-token",
                "METAAPI_ACCOUNT_ID": "test-account-concurrency",
            }),
            patch(
                "backend.demo_executor.submit_signal_once",
                new_callable=AsyncMock,
            ) as submit,
        ):
            signal = {
                "signal": "BUY",
                "stop_loss": 4190.0,
                "take_profit": 4220.0,
            }
            candle_time = datetime.now(timezone.utc).isoformat()

            first_task = asyncio.create_task(
                execute_demo_signal(
                    signal, "concurrency-candle-1", candle_time,
                    manual_confirmation=True,
                )
            )

            second_task = None
            try:
                await asyncio.wait_for(
                    first_positions_started.wait(), timeout=3
                )

                second_task = asyncio.create_task(
                    execute_demo_signal(
                        signal, "concurrency-candle-2", candle_time,
                        manual_confirmation=True,
                    )
                )

                await asyncio.sleep(0.15)

                # The second execution must wait before account checks.
                connection2.get_account_information.assert_not_awaited()

                release_first_positions.set()

                first_result, second_result = await asyncio.wait_for(
                    asyncio.gather(first_task, second_task), timeout=5
                )

                self.assertEqual(
                    first_result["status"], "validated_not_submitted"
                )
                self.assertEqual(
                    second_result["status"], "validated_not_submitted"
                )
                connection2.get_account_information.assert_awaited_once()
                submit.assert_not_awaited()
            finally:
                release_first_positions.set()
                for task in (first_task, second_task):
                    if task is not None and not task.done():
                        task.cancel()
                await asyncio.gather(
                    first_task,
                    *([second_task] if second_task is not None else []),
                    return_exceptions=True,
                )
                connection1.close.assert_awaited_once()
                api1.close.assert_called_once()
                if second_task is not None and second_task.done():
                    connection2.close.assert_awaited_once()
                    api2.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()


class TestTickValueVolumeSafety(unittest.TestCase):
    def setUp(self):
        self.valid = {
            "equity": 10000,
            "entry_price": 4200,
            "stop_loss": 4190,
            "tick_size": 0.01,
            "loss_tick_value": 1,
            "risk_percent": 0.5,
            "min_volume": 0.01,
            "max_volume": 100,
            "volume_step": 0.01,
        }

    def test_volume_stays_within_risk_limit(self):
        result = calculate_volume_from_tick_value(**self.valid)
        self.assertLessEqual(result["estimated_loss"], 50.0)
        self.assertGreaterEqual(result["volume"], 0.01)
        self.assertEqual(
            result["risk_basis"],
            "broker_quote_loss_tick_value",
        )

    def test_minimum_volume_above_risk_budget_is_rejected(self):
        values = {**self.valid, "equity": 100}
        with self.assertRaisesRegex(ValueError, "risk limit"):
            calculate_volume_from_tick_value(**values)

    def test_zero_loss_tick_value_is_rejected(self):
        values = {**self.valid, "loss_tick_value": 0}
        with self.assertRaisesRegex(ValueError, "loss_tick_value"):
            calculate_volume_from_tick_value(**values)


class TestBrokerQuoteFreshness(unittest.TestCase):
    def setUp(self):
        self.config = {"data": {"max_quote_age_seconds": 60}}
        self.now = datetime.now(timezone.utc)

    def test_accepts_fresh_quote(self):
        result = validate_broker_quote_freshness(
            {"time": self.now.isoformat()}, self.config
        )
        self.assertLessEqual(result["age_seconds"], 1)

    def test_rejects_stale_quote(self):
        old = (self.now - __import__("datetime").timedelta(seconds=90)).isoformat()
        with self.assertRaisesRegex(ValueError, "stale"):
            validate_broker_quote_freshness({"time": old}, self.config)

    def test_rejects_missing_timestamp(self):
        with self.assertRaisesRegex(ValueError, "required"):
            validate_broker_quote_freshness({"bid": 4200}, self.config)

    def test_rejects_future_timestamp(self):
        future = (self.now + __import__("datetime").timedelta(seconds=10)).isoformat()
        with self.assertRaisesRegex(ValueError, "future"):
            validate_broker_quote_freshness({"time": future}, self.config)

    def test_rejects_timezone_naive_timestamp(self):
        with self.assertRaisesRegex(ValueError, "timezone"):
            validate_broker_quote_freshness(
                {"time": "2026-10-16T12:00:00"}, self.config
            )
