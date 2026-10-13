"""Conservative, duplicate-protected MetaApi order-submission boundary."""

from .signal_identity import reserve_signal_identity
from .trade_response import validate_trade_response


def _field(item, name):
    """Read a field from either a dictionary or an SDK model object."""
    if isinstance(item, dict):
        return item.get(name)
    return getattr(item, name, None)


async def submit_signal_once(
    connection,
    *,
    symbol,
    timeframe,
    candle_time,
    side,
    volume,
    stop_loss,
    take_profit,
    state_path=None,
):
    """Submit at most once per normalized candle identity.

    An uncertain submission remains reserved. This function never retries.
    """

    if side not in ("BUY", "SELL"):
        return {"status": "blocked", "reason": "Invalid order side."}

    try:
        reserved = reserve_signal_identity(
            symbol,
            timeframe,
            candle_time,
            state_path=state_path,
        )
    except Exception as exc:
        return {
            "status": "blocked",
            "reason": f"Signal reservation failed: {type(exc).__name__}",
        }

    if not reserved:
        return {
            "status": "blocked",
            "reason": "Duplicate signal; submission was not attempted.",
        }

    try:
        if side == "BUY":
            response = await connection.create_market_buy_order(
                symbol,
                volume,
                stop_loss=stop_loss,
                take_profit=take_profit,
            )
        else:
            response = await connection.create_market_sell_order(
                symbol,
                volume,
                stop_loss=stop_loss,
                take_profit=take_profit,
            )
    except Exception as exc:
        # The request may have reached the broker before the exception.
        # Keep the reservation and do not retry automatically.
        return {
            "status": "uncertain",
            "reason": (
                "Submission raised an exception; broker state must be "
                f"checked manually. Error type: {type(exc).__name__}."
            ),
            "automatic_retry": False,
        }

    classification = validate_trade_response(response)

    if classification["status"] == "rejected":
        return {
            **classification,
            "automatic_retry": False,
        }

    if classification["status"] != "response_success":
        return {
            **classification,
            "automatic_retry": False,
        }

    order_id = classification.get("order_id")
    position_id = classification.get("position_id")

    try:
        positions = await connection.get_positions()
        orders = await connection.get_orders()
    except Exception as exc:
        return {
            "status": "uncertain",
            "reason": (
                "Broker response was received, but order/position "
                f"verification failed: {type(exc).__name__}."
            ),
            "order_id": order_id,
            "position_id": position_id,
            "automatic_retry": False,
        }

    position_found = bool(position_id) and any(
        str(_field(item, "id")) == str(position_id)
        for item in positions
    )

    order_found = bool(order_id) and any(
        str(_field(item, "id")) == str(order_id)
        for item in orders
    )

    if position_found:
        return {
            "status": "verified_position",
            "order_id": order_id,
            "position_id": position_id,
            "automatic_retry": False,
        }

    if order_found:
        return {
            "status": "verified_order",
            "order_id": order_id,
            "position_id": position_id,
            "automatic_retry": False,
        }

    return {
        "status": "uncertain",
        "reason": (
            "Broker response indicated success, but the matching order "
            "or position was not found. Do not retry automatically."
        ),
        "order_id": order_id,
        "position_id": position_id,
        "automatic_retry": False,
    }
