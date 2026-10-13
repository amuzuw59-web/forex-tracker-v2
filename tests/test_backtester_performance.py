import unittest
from unittest.mock import patch

import pandas as pd

from backend.backtester import run_backtest


class TestBacktesterPerformance(unittest.TestCase):
    def make_candles(self):
        count = 65
        return pd.DataFrame({
            "open": [100.0] * count,
            "high": [101.0] * count,
            "low": [99.0] * count,
            "close": [100.0] * count,
        })

    def run_with_trade_results(self, outcomes):
        candles = self.make_candles()
        fake_indicators = candles.copy()

        # Generate only as many BUY signals as there are outcomes.
        # Signals occur at indices 0, 2, 4, etc.
        signal_indices = set(range(0, 2 * len(outcomes), 2))

        fake_indicators["EMA20"] = [
            101.0 if i in signal_indices else 99.0
            for i in range(len(candles))
        ]
        fake_indicators["EMA50"] = 100.0
        fake_indicators["RSI14"] = 60.0
        fake_indicators["ATR14"] = 1.0

        trade_results = iter(outcomes)

        def fake_exit(
            side,
            open_price,
            high,
            low,
            stop_price,
            target_price,
        ):
            return next(trade_results)

        with (
            patch(
                "backend.backtester.calculate_indicators",
                return_value=fake_indicators,
            ),
            patch(
                "backend.backtester.evaluate_trade_exit",
                side_effect=fake_exit,
            ),
        ):
            return run_backtest(candles)

    def test_profit_and_loss_metrics(self):
        result = self.run_with_trade_results([
            (103.0, "take_profit"),
            (98.5, "stop_loss"),
            (103.0, "take_profit"),
        ])

        self.assertEqual(result["trades_count"], 3)
        self.assertEqual(result["winning_trades"], 2)
        self.assertEqual(result["losing_trades"], 1)
        self.assertEqual(result["win_rate_percent"], 66.67)
        self.assertEqual(result["net_profit_r"], 3.0)
        self.assertEqual(result["gross_profit_r"], 4.0)
        self.assertEqual(result["gross_loss_r"], 1.0)
        self.assertEqual(result["profit_factor"], 4.0)
        self.assertEqual(result["max_drawdown_r"], 1.0)

    def test_all_winning_trades_have_undefined_profit_factor(self):
        result = self.run_with_trade_results([
            (103.0, "take_profit"),
        ])

        self.assertEqual(result["trades_count"], 1)
        self.assertEqual(result["net_profit_r"], 2.0)
        self.assertIsNone(result["profit_factor"])

    def test_backtest_never_enables_trading(self):
        result = self.run_with_trade_results([
            (103.0, "take_profit"),
        ])

        self.assertFalse(result["trading_enabled"])
        self.assertFalse(result["monetary_results_available"])


if __name__ == "__main__":
    unittest.main()
