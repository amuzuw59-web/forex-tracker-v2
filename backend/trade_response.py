"""Conservative validation of MetaApi trade responses."""

SUCCESS_CODE_PAIRS = {
    (0, "ERR_NO_ERROR"),
    (10008, "TRADE_RETCODE_PLACED"),
    (10009, "TRADE_RETCODE_DONE"),
    (10010, "TRADE_RETCODE_DONE_PARTIAL"),
    (10025, "TRADE_RETCODE_NO_CHANGES"),
}


def validate_trade_response(response):
    """
    Classify a broker response conservatively.

    A successful response code does not independently prove that
    a position is open. Broker state must be verified separately.
    """
    if not isinstance(response, dict):
        return {
            "status": "uncertain",
            "reason": "Broker response is missing or invalid.",
        }

    numeric_code = response.get("numericCode")
    string_code = response.get("stringCode")

    if isinstance(numeric_code, bool) or not isinstance(numeric_code, int):
        return {
            "status": "uncertain",
            "reason": "Broker numeric response code is invalid.",
        }

    if not isinstance(string_code, str) or not string_code.strip():
        return {
            "status": "uncertain",
            "reason": "Broker string response code is missing.",
        }

    pair = (numeric_code, string_code.strip())

    if pair in SUCCESS_CODE_PAIRS:
        return {
            "status": "response_success",
            "numeric_code": numeric_code,
            "string_code": string_code.strip(),
            "order_id": response.get("orderId"),
            "position_id": response.get("positionId"),
            "message": str(response.get("message", "")),
            "note": (
                "Verify broker order and position state separately; "
                "this response alone does not confirm an open position."
            ),
        }

    known_numeric = {code for code, _ in SUCCESS_CODE_PAIRS}
    known_string = {code for _, code in SUCCESS_CODE_PAIRS}

    if numeric_code in known_numeric or string_code.strip() in known_string:
        return {
            "status": "uncertain",
            "reason": "Broker numeric and string response codes do not match.",
            "numeric_code": numeric_code,
            "string_code": string_code.strip(),
        }

    return {
        "status": "rejected",
        "numeric_code": numeric_code,
        "string_code": string_code.strip(),
        "message": str(response.get("message", "")),
    }
