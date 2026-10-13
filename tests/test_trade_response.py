import unittest

from backend.trade_response import validate_trade_response


class TestTradeResponse(unittest.TestCase):
    def test_successful_market_order_response(self):
        result = validate_trade_response({
            "numericCode": 10009,
            "stringCode": "TRADE_RETCODE_DONE",
            "message": "Request completed",
            "orderId": "123",
            "positionId": "456",
        })
        self.assertEqual(result["status"], "response_success")
        self.assertEqual(result["order_id"], "123")

    def test_rejected_order_response(self):
        result = validate_trade_response({
            "numericCode": 10006,
            "stringCode": "TRADE_RETCODE_REJECT",
            "message": "Rejected",
        })
        self.assertEqual(result["status"], "rejected")

    def test_missing_response_is_uncertain(self):
        result = validate_trade_response(None)
        self.assertEqual(result["status"], "uncertain")

    def test_missing_code_is_uncertain(self):
        result = validate_trade_response({
            "numericCode": 10009,
            "message": "Request completed",
        })
        self.assertEqual(result["status"], "uncertain")

    def test_boolean_numeric_code_is_rejected_as_invalid(self):
        result = validate_trade_response({
            "numericCode": True,
            "stringCode": "TRADE_RETCODE_DONE",
        })
        self.assertEqual(result["status"], "uncertain")


    def test_mismatched_success_codes_are_uncertain(self):
        result = validate_trade_response({
            "numericCode": 10009,
            "stringCode": "TRADE_RETCODE_PLACED",
            "message": "Inconsistent response",
        })
        self.assertEqual(result["status"], "uncertain")



    def test_placed_response_is_not_proof_of_open_position(self):
        result = validate_trade_response({
            "numericCode": 10008,
            "stringCode": "TRADE_RETCODE_PLACED",
            "orderId": "123",
        })

        self.assertEqual(result["status"], "response_success")
        self.assertIn("does not confirm an open position", result["note"])

    def test_malformed_numeric_code_is_uncertain(self):
        result = validate_trade_response({
            "numericCode": "10009",
            "stringCode": "TRADE_RETCODE_DONE",
        })

        self.assertEqual(result["status"], "uncertain")

    def test_mismatched_rejection_codes_are_uncertain(self):
        result = validate_trade_response({
            "numericCode": 10009,
            "stringCode": "TRADE_RETCODE_REJECT",
        })

        self.assertEqual(result["status"], "uncertain")

if __name__ == "__main__":
    unittest.main()
