import json
from pathlib import Path

import numpy as np
import pandas as pd


CONFIG_PATH = Path(__file__).with_name("config.json")


def load_config():
    """Load the strategy configuration."""
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def validate_candles(df):
    """Validate OHLC candle data before analysis."""
    required = ["open", "high", "low", "close"]

    if not isinstance(df, pd.DataFrame):
        raise TypeError("Candle data must be a Pandas DataFrame.")

    if df.empty:
        raise ValueError("Candle data is empty.")

    missing = [column for column in required if column not in df.columns]

    if missing:
        raise ValueError(f"Missing candle columns: {missing}")

    df = df.copy()

    for column in required:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    if df[required].isna().any().any():
        raise ValueError("Candle data contains missing or invalid prices.")

    if not np.isfinite(df[required].to_numpy(dtype=float)).all():
        raise ValueError("Candle data contains non-finite prices.")

    if (df["high"] < df["low"]).any():
        raise ValueError("A candle's high price is below its low price.")

    if (df["high"] < df[["open", "close"]].max(axis=1)).any():
        raise ValueError("A candle's high is below its open or close.")

    if (df["low"] > df[["open", "close"]].min(axis=1)).any():
        raise ValueError("A candle's low is above its open or close.")

    if (df[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError("Candle prices must be positive.")

    return df.reset_index(drop=True)


def calculate_indicators(df):
    """Calculate EMA20, EMA50, RSI14, and ATR14."""
    config = load_config()
    strategy = config["strategy"]

    df = validate_candles(df)

    fast_period = int(strategy["ema_fast"])
    slow_period = int(strategy["ema_slow"])
    rsi_period = int(strategy["rsi_period"])
    atr_period = int(strategy["atr_period"])

    if min(fast_period, slow_period, rsi_period, atr_period) < 2:
        raise ValueError("Indicator periods must be at least 2.")

    if fast_period >= slow_period:
        raise ValueError("ema_fast must be smaller than ema_slow.")

    if len(df) < max(slow_period, rsi_period, atr_period) + 1:
        raise ValueError("Not enough candles to calculate reliable indicators.")

    close = df["close"]
    previous_close = close.shift(1)

    # Exponential moving averages
    df["EMA20"] = close.ewm(
        span=fast_period, adjust=False, min_periods=fast_period
    ).mean()

    df["EMA50"] = close.ewm(
        span=slow_period, adjust=False, min_periods=slow_period
    ).mean()

    # RSI using Wilder-style exponential smoothing
    change = close.diff()
    gains = change.clip(lower=0)
    losses = -change.clip(upper=0)

    average_gain = gains.ewm(
        alpha=1 / rsi_period,
        adjust=False,
        min_periods=rsi_period,
    ).mean()

    average_loss = losses.ewm(
        alpha=1 / rsi_period,
        adjust=False,
        min_periods=rsi_period,
    ).mean()

    relative_strength = average_gain / average_loss.replace(0, np.nan)
    df["RSI14"] = 100 - (100 / (1 + relative_strength))

    # Handle periods with no losses or no price movement
    df.loc[(average_loss == 0) & (average_gain > 0), "RSI14"] = 100
    df.loc[(average_loss == 0) & (average_gain == 0), "RSI14"] = 50

    # Average True Range
    previous_close = previous_close.fillna(close)

    true_range = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - previous_close).abs(),
            (df["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    df["ATR14"] = true_range.ewm(
        alpha=1 / atr_period,
        adjust=False,
        min_periods=atr_period,
    ).mean()

    return df


def analyze_candles(candles):
    """Return the latest analysis and an informational trading signal."""
    config = load_config()
    strategy = config["strategy"]
    risk = config["risk"]

    df = calculate_indicators(candles)

    # Do not analyze a still-forming candle when the caller supplies
    # a DataFrame containing only closed candles.
    latest = df.iloc[-1]

    indicator_names = ["EMA20", "EMA50", "RSI14", "ATR14"]

    if latest[indicator_names].isna().any():
        raise ValueError("Latest candle does not have all required indicators.")

    close = float(latest["close"])
    ema_fast = float(latest["EMA20"])
    ema_slow = float(latest["EMA50"])
    rsi = float(latest["RSI14"])
    atr = float(latest["ATR14"])

    if atr <= 0:
        raise ValueError("ATR must be positive.")

    signal = "HOLD"
    reason = "The conditions for a BUY or SELL signal are not all met."

    if (
        ema_fast > ema_slow
        and strategy["rsi_buy_min"] <= rsi <= strategy["rsi_buy_max"]
    ):
        signal = "BUY"
        reason = "EMA20 is above EMA50 and RSI meets the configured BUY range."

    elif (
        ema_fast < ema_slow
        and strategy["rsi_sell_min"] <= rsi <= strategy["rsi_sell_max"]
    ):
        signal = "SELL"
        reason = "EMA20 is below EMA50 and RSI meets the configured SELL range."

    stop_multiplier = float(risk["atr_stop_multiplier"])
    target_multiplier = float(risk["atr_target_multiplier"])

    if signal == "BUY":
        stop_loss = close - atr * stop_multiplier
        take_profit = close + atr * target_multiplier
    elif signal == "SELL":
        stop_loss = close + atr * stop_multiplier
        take_profit = close - atr * target_multiplier
    else:
        stop_loss = None
        take_profit = None

    return {
        "symbol": config["market"]["symbol"],
        "timeframe": config["market"]["timeframe"],
        "signal": signal,
        "reason": reason,
        "close": close,
        "ema20": ema_fast,
        "ema50": ema_slow,
        "rsi14": rsi,
        "atr14": atr,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "trading_enabled": False,
        "risk_validation": {
            "status": (
                "not_applicable"
                if signal == "HOLD"
                else "pending_broker_value_verification"
            ),
            "monetary_loss_estimate": None,
            "position_size_calculated": False,
            "order_execution_enabled": False,
            "message": (
                "No trade setup to validate."
                if signal == "HOLD"
                else (
                    "Signal levels are informational only. "
                    "Broker tick-value units and trading costs must be "
                    "verified before calculating monetary risk or volume."
                )
            ),
        },
    }
