import asyncio
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from metaapi_cloud_sdk import MetaApi


BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "backend" / "config.json"

load_dotenv(BASE_DIR / ".env")


def load_market_config():
    import json

    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        config = json.load(file)

    return config["market"], config.get("data", {})


async def fetch_candles():
    """Fetch historical candles from MetaApi. Does not place orders."""
    token = os.getenv("METAAPI_TOKEN")
    account_id = os.getenv("METAAPI_ACCOUNT_ID")

    if not token or not account_id:
        raise RuntimeError(
            "MetaApi credentials are missing. Check your .env file."
        )

    market, data_config = load_market_config()
    symbol = market.get("symbol", "XAUUSD")
    timeframe = market.get("timeframe", "5m")
    candle_count = int(market.get("candle_count", 100))

    api = MetaApi(token)
    connection = None

    try:
        account = await api.metatrader_account_api.get_account(account_id)
        connection = account.get_rpc_connection()

        await connection.connect()
        await connection.wait_synchronized()

        timeframe_minutes = {
            "1m": 1,
            "5m": 5,
            "15m": 15,
            "30m": 30,
            "1h": 60,
            "4h": 240,
            "1d": 1440,
        }
        start_time = datetime.now(timezone.utc)

        candles = await account.get_historical_candles(
            symbol, timeframe, start_time, candle_count
        )

        if not candles:
            raise RuntimeError(
                f"MetaApi returned no candles for {symbol} ({timeframe})."
            )

        rows = []
        for candle in candles:
            rows.append({
                "datetime": candle.get("time"),
                "open": candle.get("open"),
                "high": candle.get("high"),
                "low": candle.get("low"),
                "close": candle.get("close"),
            })

        df = pd.DataFrame(rows)
        df["datetime"] = pd.to_datetime(df["datetime"], utc=True, errors="coerce")
        df = df.dropna(subset=["datetime"])
        df = df.sort_values("datetime").drop_duplicates(
            subset=["datetime"], keep="last"
        ).reset_index(drop=True)

        if len(df) < 60:
            raise RuntimeError(
                f"Only {len(df)} valid candles received; at least 60 are required."
            )

        # Exclude the latest candle because it may still be forming.
        df = df.iloc[:-1].reset_index(drop=True)

        if df.empty:
            raise RuntimeError("No closed candles remain after filtering.")

        age_limits = data_config.get("max_candle_age_minutes", {})
        max_age = age_limits.get(timeframe)

        if max_age is not None:
            latest_time = df["datetime"].iloc[-1].to_pydatetime()
            age_minutes = (
                datetime.now(timezone.utc) - latest_time
            ).total_seconds() / 60

            if age_minutes < 0 or age_minutes > float(max_age):
                raise RuntimeError(
                    f"Latest closed candle is stale: {age_minutes:.1f} minutes old."
                )

        return symbol, timeframe, df

    finally:
        if connection is not None:
            try:
                await connection.close()
            except Exception:
                pass
        api.close()


def get_candles():
    """Synchronous wrapper for scripts and Flask routes."""
    return asyncio.run(fetch_candles())


if __name__ == "__main__":
    try:
        symbol, timeframe, candles = get_candles()
        print(f"Symbol: {symbol}")
        print(f"Timeframe: {timeframe}")
        print(f"Closed candles received: {len(candles)}")
        print("\nLatest closed candle:")
        print(candles.tail(1).to_string(index=False))
    except Exception as exc:
        print(f"Market data error: {exc}")
        raise SystemExit(1)
