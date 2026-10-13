import unittest

from backend.backtester import evaluate_trade_exit


class TestTradeExit(unittest.TestCase):

    def test_buy_take_profit(self):
        result = evaluate_trade_exit(
            "BUY", 100, 106, 99, 95, 105
        )
        self.assertEqual(result, (105.0, "take_profit"))

    def test_buy_stop_loss(self):
        result = evaluate_trade_exit(
            "BUY", 100, 102, 94, 95, 110
        )
        self.assertEqual(result, (95.0, "stop_loss"))

    def test_sell_take_profit(self):
        result = evaluate_trade_exit(
            "SELL", 100, 101, 94, 105, 95
        )
        self.assertEqual(result, (95.0, "take_profit"))

    def test_sell_stop_loss(self):
        result = evaluate_trade_exit(
            "SELL", 100, 106, 99, 105, 90
        )
        self.assertEqual(result, (105.0, "stop_loss"))

    def test_buy_stop_loss_gap_uses_open(self):
        result = evaluate_trade_exit(
            "BUY", 93, 96, 92, 95, 110
        )
        self.assertEqual(result, (93.0, "stop_loss_gap"))

    def test_buy_take_profit_gap_uses_open(self):
        result = evaluate_trade_exit(
            "BUY", 112, 114, 111, 95, 110
        )
        self.assertEqual(result, (112.0, "take_profit_gap"))

    def test_sell_stop_loss_gap_uses_open(self):
        result = evaluate_trade_exit(
            "SELL", 108, 109, 106, 105, 90
        )
        self.assertEqual(result, (108.0, "stop_loss_gap"))

    def test_sell_take_profit_gap_uses_open(self):
        result = evaluate_trade_exit(
            "SELL", 88, 90, 86, 105, 90
        )
        self.assertEqual(result, (88.0, "take_profit_gap"))

    def test_buy_ambiguous_candle_assumes_stop_first(self):
        result = evaluate_trade_exit(
            "BUY", 100, 111, 94, 95, 110
        )
        self.assertEqual(
            result, (95.0, "stop_loss_ambiguous_candle")
        )

    def test_sell_ambiguous_candle_assumes_stop_first(self):
        result = evaluate_trade_exit(
            "SELL", 100, 106, 89, 105, 90
        )
        self.assertEqual(
            result, (105.0, "stop_loss_ambiguous_candle")
        )

    def test_no_exit_when_neither_level_is_hit(self):
        result = evaluate_trade_exit(
            "BUY", 100, 104, 98, 95, 110
        )
        self.assertEqual(result, (None, None))

    def test_invalid_side_is_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_trade_exit(
                "HOLD", 100, 104, 98, 95, 110
            )

    def test_invalid_candle_range_is_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_trade_exit(
                "BUY", 100, 95, 105, 90, 110
            )

    def test_invalid_stop_target_order_is_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_trade_exit(
                "BUY", 100, 104, 98, 110, 95
            )

    def test_non_finite_price_is_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_trade_exit(
                "BUY", float("nan"), 104, 98, 95, 110
            )


if __name__ == "__main__":
    unittest.main()
