"""Conservative monetary-risk calculations.

These functions estimate hypothetical price-movement risk only.
They do not connect to a broker or submit orders.
"""

import math


def _validate_positive_number(name, value):
    """Require a finite, positive numeric value."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric.")

    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive.")


def validate_broker_tick_value(tick_size, tick_value_per_lot):
    """Validate tick inputs without assuming their broker-specific accuracy."""
    _validate_positive_number("tick_size", tick_size)
    _validate_positive_number(
        "tick_value_per_lot", tick_value_per_lot
    )
    return True


def estimate_price_movement_loss(
    entry_price,
    stop_loss,
    tick_size,
    tick_value_per_lot,
    volume,
):
    """Estimate price-movement loss in account currency.

    The broker's tick value must be verified for the symbol,
    volume convention, and account currency before relying on
    this estimate for trade authorization.
    """
    values = {
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "tick_size": tick_size,
        "tick_value_per_lot": tick_value_per_lot,
        "volume": volume,
    }

    for name, value in values.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{name} must be numeric.")
        if not math.isfinite(value):
            raise ValueError(f"{name} must be finite.")

    if entry_price <= 0 or stop_loss <= 0:
        raise ValueError("Prices must be positive.")
    if tick_size <= 0:
        raise ValueError("Tick size must be positive.")
    if tick_value_per_lot <= 0:
        raise ValueError("Tick value must be positive.")
    if volume <= 0:
        raise ValueError("Volume must be positive.")

    ticks = abs(entry_price - stop_loss) / tick_size
    return ticks * tick_value_per_lot * volume


def calculate_risk_limit(equity, risk_percent):
    """Calculate the maximum permitted theoretical monetary risk."""
    values = {
        "equity": equity,
        "risk_percent": risk_percent,
    }

    for name, value in values.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{name} must be numeric.")
        if not math.isfinite(value):
            raise ValueError("Risk inputs must be finite.")

    if equity <= 0:
        raise ValueError("Equity must be positive.")
    if not 0 < risk_percent <= 0.5:
        raise ValueError(
            "Risk percentage must be above 0 and at most 0.5."
        )

    return equity * risk_percent / 100.0


def check_risk_limit(estimated_loss, equity, risk_percent):
    """Check an estimated loss against the configured risk ceiling."""
    if (
        isinstance(estimated_loss, bool)
        or not isinstance(estimated_loss, (int, float))
    ):
        raise ValueError("Estimated loss must be numeric.")

    if not math.isfinite(estimated_loss) or estimated_loss < 0:
        raise ValueError(
            "Estimated loss must be finite and non-negative."
        )

    limit = calculate_risk_limit(equity, risk_percent)

    return {
        "estimated_loss": estimated_loss,
        "maximum_allowed_loss": limit,
        "within_limit": estimated_loss <= limit,
    }


def estimate_contract_price_movement_loss(
    entry_price,
    stop_loss,
    contract_size,
    volume,
):
    """Calculate theoretical price-movement loss using contract size.

    This estimate excludes spread, commission, slippage, swaps,
    and broker-specific profit adjustments. It does not approve
    or execute trades.
    """
    values = {
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "contract_size": contract_size,
        "volume": volume,
    }

    for name, value in values.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{name} must be numeric.")
        if not math.isfinite(value):
            raise ValueError(f"{name} must be finite.")

    if entry_price <= 0 or stop_loss <= 0:
        raise ValueError("Prices must be positive.")
    if contract_size <= 0:
        raise ValueError("Contract size must be positive.")
    if volume <= 0:
        raise ValueError("Volume must be positive.")

    price_distance = abs(entry_price - stop_loss)
    return price_distance * contract_size * volume
