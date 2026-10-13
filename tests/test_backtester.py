import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from backend.backtester import run_backtest


class TestBacktester(unittest.TestCase):
    def make_candles(self, count=180):
        # Synthetic data for software tests only.
        x = np.arange(count, dtype=float)

        close = (
            3000
            + 0.12 * x
            + 8 * np.sin(x / 8)
            + 3 * np.sin(x / 3)
        )

        open_price = np.concatenate(([close[0]], close[:-1]))

        high = np.maximum(open_price, close) + 1.5
        low = np.minimum(open_price, close) - 1.5

        return pd.DataFrame({
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
        })

    def test_returns_expected_result_structure(self):
        result = run_backtest(self.make_candles())

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["symbol"], "XAUUSD")
        self.assertEqual(result["timeframe"], "5m")

        for key in (
            "trades_count",
            "winning_trades",
            "losing_trades",
            "win_rate_percent",
            "net_profit_r",
            "profit_factor",
            "max_drawdown_r",
            "trades",
        ):
            self.assertIn(key, result)

    def test_never_enables_trading(self):
        result = run_backtest(self.make_candles())

        self.assertFalse(result["trading_enabled"])
        self.assertFalse(result["monetary_results_available"])

    def test_does_not_modify_input(self):
        candles = self.make_candles()
        original = candles.copy(deep=True)

        run_backtest(candles)

        pd.testing.assert_frame_equal(candles, original)

    def test_rejects_empty_data(self):
        empty = pd.DataFrame(
            columns=["open", "high", "low", "close"]
        )

        with self.assertRaises(ValueError):
            run_backtest(empty)

    def test_rejects_insufficient_candles(self):
        with self.assertRaises(ValueError):
            run_backtest(self.make_candles(40))


if __name__ == "__main__":
    unittest.main()
