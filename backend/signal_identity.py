"""Stable identities for closed-candle forex signals."""

from datetime import datetime, timezone


def make_candle_id(candle_time):
    """Normalize a timezone-aware candle timestamp to UTC."""
    if not isinstance(candle_time, str) or not candle_time.strip():
        raise ValueError("A candle timestamp is required.")

    try:
        parsed = datetime.fromisoformat(
            candle_time.strip().replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise ValueError("Invalid candle timestamp.") from exc

    if parsed.tzinfo is None:
        raise ValueError("Candle timestamp must include a timezone.")

    return parsed.astimezone(timezone.utc).isoformat()


def make_signal_identity(symbol, timeframe, candle_time):
    """Build a stable identity from symbol, timeframe, and candle time."""
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("A valid symbol is required.")

    if not isinstance(timeframe, str) or not timeframe.strip():
        raise ValueError("A valid timeframe is required.")

    candle_id = make_candle_id(candle_time)

    return (
        f"{symbol.strip().upper()}|"
        f"{timeframe.strip().lower()}|"
        f"{candle_id}"
    )


def reserve_signal_identity(symbol, timeframe, candle_time, state_path=None):
    """
    Atomically reserve a signal identified by its canonical UTC candle time.

    Returns True for a new reservation and False for a duplicate.
    Call only at the actual order-submission boundary, not during
    signal generation or validation-only checks.
    """
    from .order_guard import STATE_PATH, reserve_signal

    candle_id = make_candle_id(candle_time)
    path = STATE_PATH if state_path is None else state_path

    return reserve_signal(
        symbol=symbol,
        timeframe=timeframe,
        candle_id=candle_id,
        state_path=path,
    )
