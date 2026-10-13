"""Safety validation for proposed Forex demo trades.

This module validates orders but does not connect to a broker or submit them.
"""
import json
import math
from pathlib import Path

CONFIG_PATH = Path(__file__).with_name("config.json")


def load_config():
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def _finite_number(name, value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric.")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite.")
    return float(value)


def validate_trade_request(
    signal,
    account_type,
    equity,
    volume,
    entry_price,
    stop_loss,
    take_profit,
    open_positions=0,
    manual_confirmation=False,
    contract_size=100.0,
    min_volume=0.01,
    max_volume=100.0,
    volume_step=0.01,
):
    """Validate a proposed trade and estimate price-movement risk."""
    config = load_config()
    trading = config["trading"]

    if not trading.get("enabled", False):
        raise ValueError("Trading is disabled in configuration.")

    if trading.get("require_demo_account", True):
        if account_type != "demo":
            raise ValueError("Demo account required.")

    if trading.get("require_manual_confirmation", True):
        if manual_confirmation is not True:
            raise ValueError("Explicit manual confirmation required.")

    if signal not in ("BUY", "SELL"):
        raise ValueError("Only BUY or SELL signals are permitted.")

    values = {
        "equity": equity,
        "volume": volume,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "contract_size": contract_size,
        "min_volume": min_volume,
        "max_volume": max_volume,
        "volume_step": volume_step,
    }

    checked = {
        name: _finite_number(name, value)
        for name, value in values.items()
    }

    equity = checked["equity"]
    volume = checked["volume"]
    entry_price = checked["entry_price"]
    stop_loss = checked["stop_loss"]
    take_profit = checked["take_profit"]
    contract_size = checked["contract_size"]
    min_volume = checked["min_volume"]
    max_volume = checked["max_volume"]
    volume_step = checked["volume_step"]

    if equity <= 0:
        raise ValueError("Equity must be positive.")

    if any(x <= 0 for x in (
        volume, entry_price, stop_loss, take_profit,
        contract_size, min_volume, max_volume, volume_step
    )):
        raise ValueError("Volume, prices, and contract specifications must be positive.")

    if min_volume > max_volume:
        raise ValueError("Minimum volume cannot exceed maximum volume.")

    if volume < min_volume or volume > max_volume:
        raise ValueError("Volume is outside broker limits.")

    steps = (volume - min_volume) / volume_step
    if not math.isclose(steps, round(steps), rel_tol=0, abs_tol=1e-7):
        raise ValueError("Volume does not match the broker's volume step.")

    if isinstance(open_positions, bool) or not isinstance(open_positions, int):
        raise ValueError("Open position count must be an integer.")

    if open_positions < 0:
        raise ValueError("Open position count cannot be negative.")

    max_positions = trading.get("max_open_positions", 1)
    if isinstance(max_positions, bool) or not isinstance(max_positions, int) or max_positions < 1:
        raise ValueError("Maximum open-position limit must be a positive integer.")

    if open_positions >= max_positions:
        raise ValueError("Maximum open-position limit reached.")

    risk_percent = _finite_number(
        "max_risk_percent", trading.get("max_risk_percent", 0.5)
    )
    if not 0 < risk_percent <= 0.5:
        raise ValueError("Risk limit must be greater than 0 and at most 0.5%.")

    if signal == "BUY":
        if not stop_loss < entry_price < take_profit:
            raise ValueError("BUY requires stop-loss < entry < take-profit.")
    else:
        if not take_profit < entry_price < stop_loss:
            raise ValueError("SELL requires take-profit < entry < stop-loss.")

    # Theoretical price-movement loss; excludes spread, commission,
    # slippage, swaps, and broker-specific conversion adjustments.
    estimated_loss = abs(entry_price - stop_loss) * contract_size * volume
    maximum_allowed_loss = equity * risk_percent / 100.0

    if estimated_loss > maximum_allowed_loss:
        raise ValueError(
            f"Estimated loss {estimated_loss:.2f} exceeds the "
            f"maximum allowed {maximum_allowed_loss:.2f}."
        )

    return {
        "approved": True,
        "signal": signal,
        "volume": volume,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "estimated_loss": round(estimated_loss, 8),
        "maximum_allowed_loss": round(maximum_allowed_loss, 8),
        "risk_percent": risk_percent,
        "account_type": account_type,
        "automatic_order_submitted": False,
    }
