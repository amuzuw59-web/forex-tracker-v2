import unittest

import pandas as pd

from backend.candlestick_tracker import track_next_move


def make_candles(direction="flat", count=80):
    rows = []

    for i in range(count):
        if direction == "bullish":
            close = 4000.0 + i
            open_price = close - 0.2
        elif direction == "bearish":
            close = 4100.0 - i
            open_price = close + 0.2
        else:
            close = 4000.0
            open_price = close

        rows.append({
            "open": open_price,
            "high": max(open_price, close) + 1.0,
            "low": min(open_price, close) - 1.0,
            "close": close,
        })

    return pd.DataFrame(rows)


class TestCandlestickTracker(unittest.TestCase):

    def test_insufficient_candles_are_unavailable(self):
        result = track_next_move(make_candles(count=59))

        self.assertEqual(result["status"], "unavailable")
        self.assertIn("60", result["message"])
        self.assertFalse(result["order_execution_enabled"])

    def test_bullish_market_outlook(self):
        result = track_next_move(make_candles("bullish"))

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["outlook"], "BULLISH")
        self.assertGreaterEqual(result["score"], 2)
        self.assertIsNotNone(result["ema20"])
        self.assertIsNotNone(result["ema50"])
        self.assertIsNotNone(result["rsi14"])
        self.assertIsNotNone(result["atr14"])
        self.assertFalse(result["order_execution_enabled"])

    def test_bearish_market_outlook(self):
        result = track_next_move(make_candles("bearish"))

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["outlook"], "BEARISH")
        self.assertLessEqual(result["score"], -2)
        self.assertFalse(result["order_execution_enabled"])

    def test_flat_market_outlook_is_neutral(self):
        result = track_next_move(make_candles("flat"))

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["outlook"], "NEUTRAL")
        self.assertEqual(result["pattern"], "DOJI")
        self.assertFalse(result["order_execution_enabled"])

    def test_invalid_candle_data_is_unavailable(self):
        candles = make_candles()
        candles.loc[0, "high"] = float("nan")

        result = track_next_move(candles)

        self.assertEqual(result["status"], "unavailable")
        self.assertFalse(result["order_execution_enabled"])

    def test_missing_ohlc_column_is_unavailable(self):
        candles = make_candles().drop(columns=["high"])

        result = track_next_move(candles)

        self.assertEqual(result["status"], "unavailable")
        self.assertFalse(result["order_execution_enabled"])


if __name__ == "__main__":
    unittest.main()
