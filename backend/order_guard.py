"""Persistent, concurrency-safe duplicate-signal protection."""

import fcntl
import json
import os
import tempfile
from pathlib import Path

STATE_PATH = Path(__file__).resolve().parent / "order_state.json"


def signal_key(symbol, timeframe, candle_id):
    """Create a stable key for one symbol, timeframe and candle."""

    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("A valid symbol is required.")

    if not isinstance(timeframe, str) or not timeframe.strip():
        raise ValueError("A valid timeframe is required.")

    if candle_id is None or isinstance(candle_id, bool):
        raise ValueError("A valid candle ID is required.")

    candle = str(candle_id).strip()

    if not candle:
        raise ValueError("A valid candle ID is required.")

    return f"{symbol.strip().upper()}|{timeframe.strip().lower()}|{candle}"


def reserve_signal(symbol, timeframe, candle_id, state_path=STATE_PATH):
    """
    Atomically reserve a signal.

    Returns True for a new reservation and False for a duplicate.
    Uses an exclusive file lock to prevent concurrent duplicate reservations.

    Reservations are persistent and are not automatically removed.
    """

    state_path = Path(state_path)
    state_path.parent.mkdir(parents=True, exist_ok=True)

    key = signal_key(symbol, timeframe, candle_id)
    lock_path = state_path.with_suffix(state_path.suffix + ".lock")

    with lock_path.open("a", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)

        try:
            if state_path.exists():
                try:
                    data = json.loads(
                        state_path.read_text(encoding="utf-8")
                    )
                except (OSError, json.JSONDecodeError) as exc:
                    raise RuntimeError(
                        "Order state is unreadable; refusing to proceed."
                    ) from exc
            else:
                data = {"reserved_signals": []}

            if not isinstance(data, dict):
                raise RuntimeError("Order state is invalid; refusing to proceed.")

            keys = data.get("reserved_signals")

            if not isinstance(keys, list) or not all(
                isinstance(item, str) for item in keys
            ):
                raise RuntimeError("Order state is invalid; refusing to proceed.")

            if key in keys:
                return False

            keys.append(key)

            fd, temp_name = tempfile.mkstemp(
                prefix="order_state_",
                suffix=".tmp",
                dir=str(state_path.parent),
            )

            try:
                with os.fdopen(fd, "w", encoding="utf-8") as file:
                    json.dump(data, file, indent=2)
                    file.flush()
                    os.fsync(file.fileno())

                os.replace(temp_name, state_path)

                # Persist the directory entry where supported.
                try:
                    dir_fd = os.open(state_path.parent, os.O_RDONLY)
                    try:
                        os.fsync(dir_fd)
                    finally:
                        os.close(dir_fd)
                except OSError:
                    pass

            finally:
                if os.path.exists(temp_name):
                    os.unlink(temp_name)

            return True

        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
