"""Persistent, read-only Forex signal monitor. Never submits orders."""

import asyncio
import json
import logging
from logging.handlers import RotatingFileHandler
import signal
from datetime import datetime, timezone
from pathlib import Path

from backend.analysis import analyze_candles
from backend.data_provider import get_candles

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "backend" / "config.json"
STOP_EVENT = None
STOP_LOOP = None

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
MONITOR_LOG = LOG_DIR / "monitor.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

root_logger = logging.getLogger()
if not any(
    getattr(handler, "_forex_monitor_file_handler", False)
    for handler in root_logger.handlers
):
    file_handler = RotatingFileHandler(
        MONITOR_LOG,
        maxBytes=2_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s"
        )
    )
    file_handler._forex_monitor_file_handler = True
    root_logger.addHandler(file_handler)

logger = logging.getLogger("forex-monitor")


def load_config():
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def get_history_path(config):
    configured_path = config.get("monitor", {}).get(
        "signal_history_file",
        "data/signal_history.jsonl",
    )
    path = Path(configured_path)

    if not path.is_absolute():
        path = BASE_DIR / path

    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_last_processed_candle(history_path, symbol, timeframe):
    """Recover the most recent processed candle after a restart."""
    if not history_path.exists():
        return None

    try:
        with history_path.open("rb") as file:
            file.seek(0, 2)
            position = file.tell()
            chunk_size = 4096
            data = b""

            while position > 0:
                read_size = min(chunk_size, position)
                position -= read_size
                file.seek(position)
                data = file.read(read_size) + data

                lines = data.splitlines()
                if position > 0:
                    data = lines[0] if lines else b""
                    lines = lines[1:]

                for line in reversed(lines):
                    try:
                        record = json.loads(line.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        continue

                    if (
                        record.get("symbol") == symbol
                        and record.get("timeframe") == timeframe
                        and record.get("candle_id")
                    ):
                        return record["candle_id"]

            if data:
                try:
                    record = json.loads(data.decode("utf-8"))
                    if (
                        record.get("symbol") == symbol
                        and record.get("timeframe") == timeframe
                    ):
                        return record.get("candle_id")
                except (UnicodeDecodeError, json.JSONDecodeError):
                    pass

    except OSError:
        logger.exception("Could not restore previous candle from history.")

    return None


def append_history(history_path, record, max_entries):
    """Append one record and keep the history within its configured limit."""
    with history_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, default=str) + "\n")
        file.flush()

    if max_entries <= 0:
        return

    with history_path.open("r", encoding="utf-8") as file:
        lines = file.readlines()

    if len(lines) > max_entries:
        temporary_path = history_path.with_suffix(
            history_path.suffix + ".tmp"
        )
        with temporary_path.open("w", encoding="utf-8") as file:
            file.writelines(lines[-max_entries:])
        temporary_path.replace(history_path)


async def monitor():
    global STOP_EVENT, STOP_LOOP
    STOP_EVENT = asyncio.Event()
    STOP_LOOP = asyncio.get_running_loop()
    config = load_config()
    market = config["market"]
    timeframe = market["timeframe"]
    configured_symbol = market["symbol"]
    monitor_config = config.get("monitor", {})

    poll_seconds = max(
        30,
        int(monitor_config.get("poll_seconds", 60)),
    )
    max_history_entries = int(
        monitor_config.get("max_history_entries", 5000)
    )
    history_path = get_history_path(config)

    last_processed_candle = load_last_processed_candle(
        history_path,
        configured_symbol,
        timeframe,
    )

    if last_processed_candle:
        logger.info(
            "Restored last processed candle: %s",
            last_processed_candle,
        )
    else:
        logger.info("No previous candle record found.")

    logger.info(
        "Read-only monitor started for %s (%s). "
        "Order submission is disabled. History: %s",
        configured_symbol,
        timeframe,
        history_path,
    )

    while not STOP_EVENT.is_set():
        try:
            symbol, returned_timeframe, candles = await asyncio.to_thread(
                get_candles
            )

            if candles is None or candles.empty:
                logger.warning("No candles returned; skipping this cycle.")
            else:
                candle_time = candles.iloc[-1]["datetime"]

                if hasattr(candle_time, "isoformat"):
                    candle_time = candle_time.isoformat()
                else:
                    candle_time = str(candle_time)

                candle_id = (
                    f"{symbol}:{returned_timeframe}:{candle_time}"
                )

                if candle_id == last_processed_candle:
                    logger.info(
                        "No new closed candle; waiting."
                    )
                else:
                    result = analyze_candles(candles)
                    signal_name = result.get("signal", "UNKNOWN")

                    record = {
                        "logged_at": datetime.now(
                            timezone.utc
                        ).isoformat(),
                        "symbol": symbol,
                        "timeframe": returned_timeframe,
                        "candle_time": candle_time,
                        "candle_id": candle_id,
                        "signal": signal_name,
                        "details": result,
                        "trading_enabled": False,
                        "order_submitted": False,
                    }

                    append_history(
                        history_path,
                        record,
                        max_history_entries,
                    )

                    last_processed_candle = candle_id

                    logger.info(
                        "Signal saved: symbol=%s timeframe=%s "
                        "candle=%s signal=%s",
                        symbol,
                        returned_timeframe,
                        candle_time,
                        signal_name,
                    )
                    logger.info(
                        "Signal details: %s",
                        json.dumps(result, default=str),
                    )

        except Exception as exc:
            logger.exception(
                "Monitoring cycle failed (%s). "
                "No order was submitted.",
                type(exc).__name__,
            )

        try:
            await asyncio.wait_for(
                STOP_EVENT.wait(),
                timeout=poll_seconds,
            )
        except asyncio.TimeoutError:
            pass

    logger.info("Read-only monitor stopped.")


def request_stop(*_):
    """Request a graceful stop from a signal handler."""
    event = STOP_EVENT
    loop = STOP_LOOP

    if event is None or loop is None or loop.is_closed():
        return

    loop.call_soon_threadsafe(event.set)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    try:
        asyncio.run(monitor())
    except KeyboardInterrupt:
        pass
