import unittest
from unittest.mock import patch

import pandas as pd

from backend.backtester import run_backtest


class TestBacktesterReliability(unittest.TestCase):
    def make_candles(self, count=65):
        return pd.DataFrame({
            "open": [100.0] * count,
            "high": [101.0] * count,
            "low": [99.0] * count,
            "close": [100.0] * count,
        })

    def make_indicators(self, candles, signal_indices=(), atr=1.0):
        result = candles.copy()
        signal_indices = set(signal_indices)

        # BUY signals occur only at explicitly selected indices.
        result["EMA20"] = [
            101.0 if i in signal_indices else 99.0
            for i in range(len(result))
        ]
        result["EMA50"] = 100.0
        result["RSI14"] = 60.0
        result["ATR14"] = atr
        return result

    def test_no_signals_produce_zero_trades(self):
        candles = self.make_candles()
        indicators = self.make_indicators(candles)

        with patch(
            "backend.backtester.calculate_indicators",
            return_value=indicators,
        ):
            result = run_backtest(candles)

        self.assertEqual(result["trades_count"], 0)
        self.assertEqual(result["incomplete_trades_count"], 0)
        self.assertEqual(result["winning_trades"], 0)
        self.assertEqual(result["losing_trades"], 0)
        self.assertEqual(result["net_profit_r"], 0.0)
        self.assertEqual(result["win_rate_percent"], 0.0)
        self.assertEqual(result["trades"], [])
        self.assertFalse(result["trading_enabled"])

    def test_unfinished_trade_is_not_counted_as_completed(self):
        candles = self.make_candles()

        # The entry is at 100. The later candles never reach
        # the BUY stop at 98.5 or target at 103.
        indicators = self.make_indicators(
            candles,
            signal_indices={0},
        )

        with patch(
            "backend.backtester.calculate_indicators",
            return_value=indicators,
        ):
            result = run_backtest(candles)

        self.assertEqual(result["trades_count"], 0)
        self.assertEqual(result["incomplete_trades_count"], 1)
        self.assertEqual(result["trades"], [])
        self.assertEqual(result["net_profit_r"], 0.0)
        self.assertFalse(result["trading_enabled"])

    def test_non_positive_atr_produces_no_trades(self):
        candles = self.make_candles()
        indicators = self.make_indicators(
            candles,
            signal_indices={0, 2, 4},
            atr=0.0,
        )

        with patch(
            "backend.backtester.calculate_indicators",
            return_value=indicators,
        ):
            result = run_backtest(candles)

        self.assertEqual(result["trades_count"], 0)
        self.assertEqual(result["trades"], [])
        self.assertFalse(result["trading_enabled"])

    def test_backtest_results_are_not_monetary_profit(self):
        candles = self.make_candles()
        indicators = self.make_indicators(candles)

        with patch(
            "backend.backtester.calculate_indicators",
            return_value=indicators,
        ):
            result = run_backtest(candles)

        self.assertFalse(result["monetary_results_available"])
        self.assertFalse(result["trading_enabled"])


if __name__ == "__main__":
    unittest.main()
