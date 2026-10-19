"""Safety-gated demo-trading execution module.

No order is submitted unless every safety check passes and the
execution kill switch is explicitly enabled.
"""
import json
import math
import os
from pathlib import Path
from datetime import datetime, timezone

from dotenv import load_dotenv
from metaapi_cloud_sdk import MetaApi
from backend.account_execution_lock import (
    acquire_account_execution_lock,
    release_account_execution_lock,
)
from backend.submission_boundary import submit_signal_once

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "backend" / "config.json"
load_dotenv(BASE_DIR / ".env")


def load_config():
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def validate_signal_freshness(candle_time, timeframe, config=None):
    """Reject missing, invalid, future-dated, or stale signal candles."""
    if config is None:
        config = load_config()

    if not isinstance(candle_time, str) or not candle_time.strip():
        raise ValueError("Signal candle timestamp is required.")

    try:
        parsed = datetime.fromisoformat(
            candle_time.strip().replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise ValueError("Signal candle timestamp is invalid.") from exc

    if parsed.tzinfo is None:
        raise ValueError("Signal candle timestamp must include a timezone.")

    parsed = parsed.astimezone(timezone.utc)
    now = datetime.now(timezone.utc)
    age_minutes = (now - parsed).total_seconds() / 60.0

    if age_minutes < 0:
        raise ValueError("Signal candle timestamp is in the future.")

    data_config = config.get("data", {})
    limits = data_config.get("max_candle_age_minutes", {})
    max_age = limits.get(timeframe)

    if max_age is None:
        raise ValueError(f"No freshness limit configured for {timeframe}.")

    if age_minutes > float(max_age):
        raise ValueError(
            f"Signal candle is stale: {age_minutes:.1f} minutes old."
        )

    return {
        "candle_time": parsed.isoformat(),
        "age_minutes": round(max(age_minutes, 0.0), 2),
        "max_age_minutes": float(max_age),
    }



def validate_broker_quote_freshness(quote, config=None):
    """Reject missing, invalid, future-dated, or stale broker quotes."""
    if not isinstance(quote, dict):
        raise ValueError("Broker quote is missing or invalid.")

    raw_time = quote.get("time")
    if isinstance(raw_time, datetime):
        parsed = raw_time
    elif isinstance(raw_time, str) and raw_time.strip():
        try:
            parsed = datetime.fromisoformat(
                raw_time.strip().replace("Z", "+00:00")
            )
        except ValueError as exc:
            raise ValueError("Broker quote timestamp is invalid.") from exc
    else:
        raise ValueError("Broker quote timestamp is required.")

    if parsed.tzinfo is None:
        raise ValueError("Broker quote timestamp must include a timezone.")

    parsed = parsed.astimezone(timezone.utc)
    age_seconds = (datetime.now(timezone.utc) - parsed).total_seconds()

    if age_seconds < 0:
        raise ValueError("Broker quote timestamp is in the future.")

    if config is None:
        config = load_config()

    data_config = config.get("data", {})
    max_age = data_config.get("max_quote_age_seconds", 60)

    if (
        isinstance(max_age, bool)
        or not isinstance(max_age, (int, float))
        or not math.isfinite(max_age)
        or max_age <= 0
    ):
        raise ValueError("Broker quote freshness limit is invalid.")

    if age_seconds > float(max_age):
        raise ValueError(
            f"Broker quote is stale: {age_seconds:.1f} seconds old."
        )

    return {
        "quote_time": parsed.isoformat(),
        "age_seconds": round(age_seconds, 2),
        "max_age_seconds": float(max_age),
    }

def calculate_volume(
    equity,
    entry_price,
    stop_loss,
    contract_size,
    risk_percent,
    min_volume,
    max_volume,
    volume_step,
):
    """Calculate a volume within a theoretical price-movement risk limit."""
    values = (
        equity, entry_price, stop_loss, contract_size,
        risk_percent, min_volume, max_volume, volume_step,
    )
    if any(
        isinstance(v, bool) or not isinstance(v, (int, float))
        or not math.isfinite(v) for v in values
    ):
        raise ValueError("Risk inputs must be finite numbers.")

    if min(values) <= 0 or entry_price == stop_loss:
        raise ValueError("Risk inputs must be positive and the stop must differ from entry.")

    if risk_percent > 0.5:
        raise ValueError("Risk limit cannot exceed 0.5%.")

    max_loss = equity * risk_percent / 100.0
    loss_per_lot = abs(entry_price - stop_loss) * contract_size

    raw_volume = max_loss / loss_per_lot
    steps = math.floor((raw_volume - min_volume) / volume_step + 1e-9)
    volume = min_volume + max(steps, 0) * volume_step

    volume = round(volume, 8)

    if volume < min_volume or volume > max_volume:
        raise ValueError("Calculated volume is outside broker limits.")

    estimated_loss = loss_per_lot * volume
    if estimated_loss > max_loss + 1e-8:
        raise ValueError("Calculated volume exceeds the configured risk limit.")

    return {
        "volume": volume,
        "estimated_loss": round(estimated_loss, 2),
        "maximum_allowed_loss": round(max_loss, 2),
        "risk_percent": risk_percent,
    }



def calculate_volume_from_tick_value(
    equity,
    entry_price,
    stop_loss,
    tick_size,
    loss_tick_value,
    risk_percent,
    min_volume,
    max_volume,
    volume_step,
    contract_size=None,
    cost_reserve_percent=20.0,
):
    """Estimate stop-loss risk using the broker quote's loss tick value."""
    from backend.risk_calculator import (
        calculate_risk_limit,
        estimate_price_movement_loss,
        estimate_contract_price_movement_loss,
    )

    values = {
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "tick_size": tick_size,
        "loss_tick_value": loss_tick_value,
        "min_volume": min_volume,
        "max_volume": max_volume,
        "volume_step": volume_step,
    }

    for name, value in values.items():
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0
        ):
            raise ValueError(f"{name} must be finite and positive.")

    if entry_price == stop_loss:
        raise ValueError("Stop-loss must differ from entry.")

    if min_volume > max_volume or volume_step > max_volume:
        raise ValueError("Broker volume limits are inconsistent.")

    risk_limit = calculate_risk_limit(equity, risk_percent)

    loss_per_lot = estimate_price_movement_loss(
        entry_price=entry_price,
        stop_loss=stop_loss,
        tick_size=tick_size,
        tick_value_per_lot=loss_tick_value,
        volume=1.0,
    )

    if (
        isinstance(cost_reserve_percent, bool)
        or not isinstance(cost_reserve_percent, (int, float))
        or not math.isfinite(cost_reserve_percent)
        or not 0 <= cost_reserve_percent < 100
    ):
        raise ValueError("Cost reserve must be between 0 and 100 percent.")

    if contract_size is not None:
        if (
            isinstance(contract_size, bool)
            or not isinstance(contract_size, (int, float))
            or not math.isfinite(contract_size)
            or contract_size <= 0
        ):
            raise ValueError("Contract size must be finite and positive.")

        contract_loss = estimate_contract_price_movement_loss(
            entry_price=entry_price,
            stop_loss=stop_loss,
            contract_size=contract_size,
            volume=1.0,
        )
        if not math.isclose(
            loss_per_lot, contract_loss, rel_tol=0.01, abs_tol=0.01
        ):
            raise ValueError(
                "Broker tick-value and contract-size loss estimates disagree."
            )

    usable_risk_limit = risk_limit * (
        1.0 - cost_reserve_percent / 100.0
    )
    raw_volume = usable_risk_limit / loss_per_lot

    # Fail immediately if even the broker's minimum lot exceeds the budget.
    if raw_volume < min_volume:
        raise ValueError(
            "Minimum broker volume exceeds the configured risk limit."
        )

    steps = math.floor((raw_volume - min_volume) / volume_step + 1e-9)
    volume = round(min_volume + steps * volume_step, 8)

    if volume < min_volume or volume > max_volume:
        raise ValueError("Calculated volume is outside broker limits.")

    estimated_loss = estimate_price_movement_loss(
        entry_price=entry_price,
        stop_loss=stop_loss,
        tick_size=tick_size,
        tick_value_per_lot=loss_tick_value,
        volume=volume,
    )

    if estimated_loss > usable_risk_limit + 1e-8:
        raise ValueError(
            "Minimum broker volume exceeds the configured risk limit."
        )

    cost_reserve = risk_limit * cost_reserve_percent / 100.0
    estimated_total_risk = estimated_loss + cost_reserve
    if estimated_total_risk > risk_limit + 1e-8:
        raise ValueError("Estimated loss plus reserve exceeds risk limit.")

    return {
        "volume": volume,
        "estimated_loss": round(estimated_loss, 2),
        "estimated_cost_reserve": round(cost_reserve, 2),
        "estimated_total_risk": round(estimated_total_risk, 2),
        "cost_reserve_percent": float(cost_reserve_percent),
        "maximum_allowed_loss": round(risk_limit, 2),
        "risk_percent": risk_percent,
        "risk_basis": (
            "tick_value_cross_checked_against_contract_size"
            if contract_size is not None
            else "broker_quote_loss_tick_value"
        ),
    }

async def execute_demo_signal(signal, candle_id, candle_time, manual_confirmation=False, prepare_only=False, expected_proposal=None):
    """Validate a signal and submit only when explicitly enabled.

    This function deliberately refuses execution when the configured
    execution switch is off. The caller must provide a unique candle ID
    to support duplicate-order protection.
    """
    config = load_config()
    trading = config["trading"]

    if not trading.get("enabled", False) and not prepare_only:
        return {"status": "blocked", "reason": "Trading is disabled."}

    if prepare_only and trading.get("submission_enabled", False):
        return {
            "status": "blocked",
            "reason": "Preflight mode requires submission to remain disabled.",
            "automatic_order_submitted": False,
        }

    if not trading.get("require_demo_account", True):
        return {"status": "blocked", "reason": "Demo-only protection must remain enabled."}

    if signal.get("signal") not in ("BUY", "SELL"):
        return {"status": "blocked", "reason": "No actionable BUY or SELL signal."}

    if not candle_id:
        return {"status": "blocked", "reason": "A unique signal candle ID is required."}

    try:
        freshness = validate_signal_freshness(
            candle_time, config["market"]["timeframe"], config
        )
    except ValueError as exc:
        return {"status": "blocked", "reason": str(exc)}

    if not prepare_only and trading.get("require_manual_confirmation", True):
        if manual_confirmation is not True:
            return {
                "status": "blocked",
                "reason": "Explicit manual confirmation is required.",
            }

    if (
        not prepare_only
        and trading.get("submission_enabled", False) is True
        and trading.get("monetary_risk_independently_verified", False) is not True
    ):
        return {
            "status": "blocked",
            "reason": (
                "Monetary risk is unverified: broker tick-value units and "
                "trading costs must be independently verified before submission."
            ),
            "risk_validation": "pending_broker_value_verification",
            "automatic_order_submitted": False,
        }

    token = os.getenv("METAAPI_TOKEN")
    account_id = os.getenv("METAAPI_ACCOUNT_ID")
    if not token or not account_id:
        return {"status": "blocked", "reason": "MetaApi credentials are missing."}

    api = MetaApi(token)
    connection = None
    execution_lock_file = None

    try:
        account = await api.metatrader_account_api.get_account(account_id)
        connection = account.get_rpc_connection()
        await connection.connect()
        await connection.wait_synchronized(timeout_in_seconds=30)

        # Serialize account checks and any subsequent submission.
        execution_lock_file = await acquire_account_execution_lock(
            account_id
        )

        info = await connection.get_account_information()
        if info.get("type") != "ACCOUNT_TRADE_MODE_DEMO":
            return {"status": "blocked", "reason": "Account is not confirmed as demo."}

        if info.get("tradeAllowed") is not True or info.get("investorMode") is True:
            return {"status": "blocked", "reason": "Account trading permissions are insufficient."}

        symbol = config["market"]["symbol"]
        spec = await connection.get_symbol_specification(symbol)
        quote = await connection.get_symbol_price(symbol)
        quote_freshness = validate_broker_quote_freshness(quote, config)
        positions = await connection.get_positions()
        orders = await connection.get_orders()

        max_positions = trading.get("max_open_positions", 1)
        if len(positions) >= max_positions:
            return {
                "status": "blocked",
                "reason": "Maximum open-position limit reached.",
                "automatic_order_submitted": False,
            }

        # Fail closed if any open orders exist.
        if orders:
            return {
                "status": "blocked",
                "reason": "Open orders exist; refusing new execution.",
                "automatic_order_submitted": False,
            }

        bid = float(quote["bid"])
        ask = float(quote["ask"])
        if not math.isfinite(bid) or not math.isfinite(ask) or bid <= 0 or ask < bid:
            return {"status": "blocked", "reason": "Broker quote is invalid."}

        side = signal["signal"]
        entry = ask if side == "BUY" else bid
        stop_loss = float(signal["stop_loss"])
        take_profit = float(signal["take_profit"])

        if side == "BUY" and not stop_loss < entry < take_profit:
            return {"status": "blocked", "reason": "BUY price levels are invalid."}
        if side == "SELL" and not take_profit < entry < stop_loss:
            return {"status": "blocked", "reason": "SELL price levels are invalid."}

        risk = calculate_volume_from_tick_value(
            equity=float(info["equity"]),
            entry_price=entry,
            stop_loss=stop_loss,
            tick_size=float(spec["tickSize"]),
            loss_tick_value=float(quote["lossTickValue"]),
            risk_percent=float(trading.get("max_risk_percent", 0.5)),
            min_volume=float(spec["minVolume"]),
            max_volume=float(spec["maxVolume"]),
            volume_step=float(spec["volumeStep"]),
            contract_size=float(spec["contractSize"]),
        )

        # Match the approved proposal against fresh broker-derived values.
        # Any mismatch blocks execution before the submission boundary.
        if expected_proposal is not None:
            expected_values = {
                "symbol": (expected_proposal.get("symbol"), symbol),
                "side": (expected_proposal.get("signal"), side),
                "candle_id": (
                    str(expected_proposal.get("candle_id", "")),
                    str(candle_id),
                ),
            }

            for field, (expected, actual) in expected_values.items():
                if expected != actual:
                    return {
                        "status": "blocked",
                        "reason": (
                            f"Approved proposal mismatch: {field} changed."
                        ),
                        "automatic_order_submitted": False,
                    }

            tick_size = float(spec["tickSize"])
            price_checks = {
                "entry": (expected_proposal.get("entry_price"), entry),
                "stop_loss": (
                    expected_proposal.get("stop_loss"), stop_loss
                ),
                "take_profit": (
                    expected_proposal.get("take_profit"), take_profit
                ),
            }

            for field, (expected, actual) in price_checks.items():
                if (
                    isinstance(expected, bool)
                    or not isinstance(expected, (int, float))
                    or not math.isfinite(expected)
                    or not math.isclose(
                        float(expected),
                        float(actual),
                        rel_tol=0.0,
                        abs_tol=tick_size / 2,
                    )
                ):
                    return {
                        "status": "blocked",
                        "reason": (
                            f"Approved proposal mismatch: {field} changed."
                        ),
                        "automatic_order_submitted": False,
                    }

            risk_checks = {
                "volume": (expected_proposal.get("volume"), risk["volume"]),
                "estimated_loss": (
                    expected_proposal.get("estimated_loss"),
                    risk["estimated_loss"],
                ),
                "maximum_allowed_loss": (
                    expected_proposal.get("maximum_allowed_loss"),
                    risk["maximum_allowed_loss"],
                ),
                "risk_percent": (
                    expected_proposal.get("risk_percent"),
                    risk["risk_percent"],
                ),
            }

            for field, (expected, actual) in risk_checks.items():
                if (
                    isinstance(expected, bool)
                    or not isinstance(expected, (int, float))
                    or not math.isfinite(expected)
                    or not math.isclose(
                        float(expected),
                        float(actual),
                        rel_tol=1e-6,
                        abs_tol=1e-6,
                    )
                ):
                    return {
                        "status": "blocked",
                        "reason": (
                            f"Approved proposal mismatch: {field} changed."
                        ),
                        "automatic_order_submitted": False,
                    }

        # Preflight must never submit. Normal execution also respects the
        # independent submission switch.
        if prepare_only or not trading.get("submission_enabled", False):
            return {
                "status": (
                    "proposal_ready" if prepare_only
                    else "validated_not_submitted"
                ),
                "symbol": symbol,
                "side": side,
                "entry_price": entry,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                **risk,
                "candle_id": str(candle_id),
                "freshness": freshness,
                "quote_freshness": quote_freshness,
                "automatic_order_submitted": False,
                "message": (
                    "Broker validation completed. No order was submitted."
                    if prepare_only
                    else
                    "Validation passed. Submission remains disabled by "
                    "the independent submission switch."
                ),
            }

        # Fail closed unless monetary risk verification is explicitly enabled.
        # An estimate alone is not proof that broker costs and tick-value units
        # have been independently verified.
        if trading.get("monetary_risk_independently_verified", False) is not True:
            return {
                "status": "blocked",
                "reason": (
                    "Monetary risk is unverified: broker tick-value units and "
                    "trading costs must be independently verified before submission."
                ),
                "risk_validation": "pending_broker_value_verification",
                "automatic_order_submitted": False,
            }

        # Enforce proposal matching at the final order-submission boundary.
        if expected_proposal is None:
            return {
                "status": "blocked",
                "reason": "An approved proposal is required for execution.",
                "automatic_order_submitted": False,
            }

        submission = await submit_signal_once(
            connection,
            symbol=symbol,
            timeframe=config["market"]["timeframe"],
            candle_time=candle_time,
            side=side,
            volume=risk["volume"],
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

        submission_status = submission.get("status")
        verified_statuses = ("verified_position", "verified_order")

        return {
            **submission,
            "symbol": symbol,
            "side": side,
            "entry_price": entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            **risk,
            "candle_id": str(candle_id),
            "freshness": freshness,
            "submission_attempted": submission_status != "blocked",
            "automatic_order_submitted": (
                submission_status in verified_statuses
            ),
            "broker_state_verified": (
                submission_status in verified_statuses
            ),
            "open_position_verified": (
                submission_status == "verified_position"
            ),
        }

    except Exception as exc:
        return {
            "status": "blocked",
            "reason": f"Execution validation failed: {type(exc).__name__}: {exc}",
        }

    finally:
        if execution_lock_file is not None:
            try:
                await release_account_execution_lock(execution_lock_file)
            except Exception:
                # Do not mask the execution result with a cleanup exception.
                pass

        if connection is not None:
            try:
                await connection.close()
            except Exception:
                pass
        api.close()
