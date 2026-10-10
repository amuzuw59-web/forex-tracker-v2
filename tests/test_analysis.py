import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from analysis import analyze_candles, calculate_indicators


def make_sample_candles(count=120):
    close = 2650 + np.arange(count) * 0.5
    return pd.DataFrame({
        "open": close - 0.2,
        "high": close + 1.0,
        "low": close - 1.0,
        "close": close,
    })


class TestAnalysis(unittest.TestCase):

    def test_indicators_are_calculated(self):
        result = calculate_indicators(make_sample_candles())
        for column in ["EMA20", "EMA50", "RSI14", "ATR14"]:
            self.assertIn(column, result.columns)
            self.assertTrue(np.isfinite(result[column].iloc[-1]))

    def test_signal_is_valid(self):
        result = analyze_candles(make_sample_candles())
        self.assertIn(result["signal"], ("BUY", "SELL", "HOLD"))

    def test_automatic_trading_is_disabled(self):
        result = analyze_candles(make_sample_candles())
        self.assertFalse(result["trading_enabled"])

    def test_invalid_candle_data_is_rejected(self):
        candles = make_sample_candles()
        candles.loc[0, "close"] = np.nan
        with self.assertRaises(ValueError):
            calculate_indicators(candles)

    def test_insufficient_candles_are_rejected(self):
        candles = make_sample_candles(count=10)
        with self.assertRaises(ValueError):
            calculate_indicators(candles)


if __name__ == "__main__":
    unittest.main(verbosity=2)
