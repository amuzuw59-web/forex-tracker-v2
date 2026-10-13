"""Read-only MetaApi XAUUSD risk inspection.

This script never submits, modifies, or closes orders.
Theoretical calculations do not authorize trading.
"""

import asyncio
import math
import os
from pathlib import Path

from dotenv import load_dotenv
from metaapi_cloud_sdk import MetaApi

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def valid_positive_number(value):
    """Return True only for finite positive numeric values."""
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
        and value > 0
    )


def main_values_are_valid(*values):
    return all(valid_positive_number(value) for value in values)


async def inspect_risk_data():
    token = os.getenv("METAAPI_TOKEN")
    account_id = os.getenv("METAAPI_ACCOUNT_ID")

    if not token or not account_id:
        raise RuntimeError(
            "MetaApi credentials are missing. Check your .env configuration."
        )

    api = MetaApi(token)
    connection = None

    try:
        account = await api.metatrader_account_api.get_account(account_id)
        connection = account.get_rpc_connection()

        await connection.connect()
        await connection.wait_synchronized(timeout_in_seconds=30)

        info = await connection.get_account_information()
        quote = await connection.get_symbol_price("XAUUSD")
        spec = await connection.get_symbol_specification("XAUUSD")

        equity = info.get("equity")
        currency = info.get("currency")
        free_margin = info.get("freeMargin")
        bid = quote.get("bid")
        ask = quote.get("ask")
        contract_size = spec.get("contractSize")
        tick_size = spec.get("tickSize")
        loss_tick_value = quote.get("lossTickValue")
        profit_tick_value = quote.get("profitTickValue")
        min_volume = spec.get("minVolume")
        volume_step = spec.get("volumeStep")

        print("READ-ONLY XAUUSD RISK INSPECTION")
        print("================================")
        print("Account type:", info.get("type"))
        print("Account currency:", currency)
        print("Equity:", equity)
        print("Available free margin:", free_margin)
        print("Broker trade allowed:", info.get("tradeAllowed"))
        print("Investor mode:", info.get("investorMode"))
        print("Bid:", bid)
        print("Ask:", ask)
        print("Quote time:", quote.get("time"))
        print("Contract size:", contract_size)
        print("Tick size:", tick_size)
        print("Profit tick value:", profit_tick_value)
        print("Loss tick value:", loss_tick_value)
        print("Minimum volume:", min_volume)
        print("Volume step:", volume_step)

        print("\nHYPOTHETICAL RISK COMPARISON — NOT TRADE AUTHORIZATION")

        price_move = 1.00

        if main_values_are_valid(contract_size, min_volume):
            contract_loss = price_move * contract_size * min_volume
            print("Price movement:", price_move)
            print("Illustrative volume:", min_volume)
            print("Contract-size estimate:", round(contract_loss, 6), currency)
        else:
            contract_loss = None
            print("Contract-size estimate unavailable: invalid inputs.")

        if main_values_are_valid(tick_size, loss_tick_value, min_volume):
            tick_count = price_move / tick_size
            tick_loss = tick_count * loss_tick_value * min_volume

            print("Ticks in price movement:", tick_count)
            print("Tick-value estimate:", round(tick_loss, 6), currency)

            if contract_loss is not None:
                difference = abs(contract_loss - tick_loss)
                print("Absolute difference:", round(difference, 6), currency)

                if math.isclose(
                    contract_loss,
                    tick_loss,
                    rel_tol=0.01,
                    abs_tol=0.01,
                ):
                    print(
                        "Comparison: estimates are close; "
                        "tick-value units still require independent verification."
                    )
                else:
                    print(
                        "Comparison: estimates differ; "
                        "investigate broker specifications and units."
                    )
        else:
            print("Tick-value estimate unavailable: invalid inputs.")

        print("\nHYPOTHETICAL MARGIN CHECK — NO ORDER SUBMITTED")

        if (
            main_values_are_valid(ask, min_volume)
            and main_values_are_valid(free_margin)
        ):
            try:
                margin_order = {
                    "symbol": "XAUUSD",
                    "type": "ORDER_TYPE_BUY",
                    "volume": float(min_volume),
                    "openPrice": float(ask),
                }
                margin_result = await connection.calculate_margin(margin_order)

                if isinstance(margin_result, dict):
                    required_margin = margin_result.get("margin")
                else:
                    required_margin = getattr(margin_result, "margin", None)

                if (
                    isinstance(required_margin, (int, float))
                    and not isinstance(required_margin, bool)
                    and math.isfinite(required_margin)
                    and required_margin >= 0
                ):
                    print("Hypothetical volume:", min_volume)
                    print("Required margin:", required_margin, currency)
                    print("Available free margin:", free_margin)
                    if required_margin <= free_margin:
                        print("Margin check: sufficient for this hypothetical order.")
                    else:
                        print("Margin check: insufficient free margin.")
                else:
                    print("Margin check unavailable: invalid margin result.")
            except Exception as exc:
                print("Margin check unavailable:", type(exc).__name__, str(exc))
        else:
            print("Margin check skipped: invalid inputs.")

        print("\nAUTOMATIC ORDER AUTHORIZATION: DENIED")
        print("Tick-value units and monetary risk remain unverified.")
        print("No orders were submitted.")

    finally:
        if connection is not None:
            try:
                await connection.close()
            except Exception as exc:
                print("Connection cleanup warning:", type(exc).__name__)

        api.close()


if __name__ == "__main__":
    asyncio.run(inspect_risk_data())
