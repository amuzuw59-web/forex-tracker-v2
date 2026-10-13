"""Historical strategy backtesting without order execution."""

import math

import pandas as pd

from backend.analysis import calculate_indicators, load_config, validate_candles



def evaluate_trade_exit(side, open_price, high, low, stop_price, target_price):
    """Evaluate stop-loss and take-profit levels for one candle."""
    values = (open_price, high, low, stop_price, target_price)

    try:
        values = tuple(float(value) for value in values)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Trade exit prices must be numeric.") from exc

    if not all(math.isfinite(value) for value in values):
        raise ValueError("Trade exit prices must be finite numbers.")

    open_price, high, low, stop_price, target_price = values

    if low <= 0 or open_price <= 0 or high <= 0:
        raise ValueError("Candle prices must be positive.")

    if low > high or low > open_price or open_price > high:
        raise ValueError("Invalid candle price range.")

    if stop_price <= 0 or target_price <= 0:
        raise ValueError("Stop and target prices must be positive.")

    if side == "BUY":
        if stop_price >= target_price:
            raise ValueError("BUY stop-loss must be below take-profit.")

        if open_price <= stop_price:
            return open_price, "stop_loss_gap"

        if open_price >= target_price:
            return open_price, "take_profit_gap"

        if low <= stop_price and high >= target_price:
            return stop_price, "stop_loss_ambiguous_candle"

        if low <= stop_price:
            return stop_price, "stop_loss"

        if high >= target_price:
            return target_price, "take_profit"

    elif side == "SELL":
        if stop_price <= target_price:
            raise ValueError("SELL stop-loss must be above take-profit.")

        if open_price >= stop_price:
            return open_price, "stop_loss_gap"

        if open_price <= target_price:
            return open_price, "take_profit_gap"

        if high >= stop_price and low <= target_price:
            return stop_price, "stop_loss_ambiguous_candle"

        if high >= stop_price:
            return stop_price, "stop_loss"

        if low <= target_price:
            return target_price, "take_profit"

    else:
        raise ValueError("Side must be BUY or SELL.")

    return None, None


def run_backtest(candles):
    """
    Replay historical candles using the configured EMA/RSI/ATR strategy.

    Signals are evaluated at candle close.
    Entries occur at the next candle's open.

    Results are reported in R-multiples, not monetary profit.
    If stop-loss and take-profit are both touched in one candle,
    stop-loss is assumed to occur first.

    This function never places orders.
    """
    config = load_config()
    strategy = config["strategy"]
    risk = config["risk"]

    df = validate_candles(candles)
    df = calculate_indicators(df)

    if len(df) < 60:
        raise ValueError("At least 60 candles are required for backtesting.")

    required_indicators = ["EMA20", "EMA50", "RSI14", "ATR14"]
    df = df.dropna(subset=required_indicators).reset_index(drop=True)

    if len(df) < 2:
        raise ValueError("Not enough candles have valid indicators.")

    stop_multiplier = float(risk["atr_stop_multiplier"])
    target_multiplier = float(risk["atr_target_multiplier"])

    if stop_multiplier <= 0 or target_multiplier <= 0:
        raise ValueError("ATR stop and target multipliers must be positive.")

    trades = []
    equity_r = 0.0
    equity_curve = [0.0]
    peak_equity = 0.0
    max_drawdown_r = 0.0

    i = 0

    while i < len(df) - 1:
        signal_candle = df.iloc[i]

        ema_fast = float(signal_candle["EMA20"])
        ema_slow = float(signal_candle["EMA50"])
        rsi = float(signal_candle["RSI14"])
        atr = float(signal_candle["ATR14"])

        if not math.isfinite(atr) or atr <= 0:
            i += 1
            continue

        signal = "HOLD"

        if (
            ema_fast > ema_slow
            and strategy["rsi_buy_min"] <= rsi <= strategy["rsi_buy_max"]
        ):
            signal = "BUY"
        elif (
            ema_fast < ema_slow
            and strategy["rsi_sell_min"] <= rsi <= strategy["rsi_sell_max"]
        ):
            signal = "SELL"

        if signal == "HOLD":
            i += 1
            continue

        # The signal is only known after candle i closes.
        # Enter at the next candle's open.
        entry_index = i + 1
        entry_candle = df.iloc[entry_index]
        entry_price = float(entry_candle["open"])

        stop_distance = atr * stop_multiplier
        target_distance = atr * target_multiplier

        if signal == "BUY":
            stop_price = entry_price - stop_distance
            target_price = entry_price + target_distance
        else:
            stop_price = entry_price + stop_distance
            target_price = entry_price - target_distance

        exit_price = None
        exit_reason = None
        exit_index = None

        # Search forward until the stop or target is reached.
        for j in range(entry_index, len(df)):
            candle = df.iloc[j]

            open_price = float(candle["open"])
            high = float(candle["high"])
            low = float(candle["low"])

            exit_price, exit_reason = evaluate_trade_exit(
                signal, open_price, high, low, stop_price, target_price
            )

            if exit_price is not None:
                exit_index = j
                break

        # Do not invent an exit if the historical data ends first.
        if exit_price is None:
            break

        if signal == "BUY":
            pnl_price = exit_price - entry_price
        else:
            pnl_price = entry_price - exit_price

        r_multiple = pnl_price / stop_distance

        entry_time = None
        exit_time = None

        if "datetime" in df.columns:
            entry_time = str(df.iloc[entry_index]["datetime"])
            exit_time = str(df.iloc[exit_index]["datetime"])

        trades.append(
            {
                "side": signal,
                "entry_time": entry_time,
                "exit_time": exit_time,
                "entry_price": entry_price,
                "exit_price": float(exit_price),
                "stop_loss": stop_price,
                "take_profit": target_price,
                "exit_reason": exit_reason,
                "r_multiple": float(r_multiple),
            }
        )

        equity_r += r_multiple
        equity_curve.append(equity_r)

        peak_equity = max(peak_equity, equity_r)
        drawdown = peak_equity - equity_r
        max_drawdown_r = max(max_drawdown_r, drawdown)

        # Prevent overlapping trades.
        i = exit_index + 1

    winners = [t for t in trades if t["r_multiple"] > 0]
    losers = [t for t in trades if t["r_multiple"] < 0]

    gross_profit_r = sum(t["r_multiple"] for t in winners)
    gross_loss_r = abs(sum(t["r_multiple"] for t in losers))

    if gross_loss_r > 0:
        profit_factor = gross_profit_r / gross_loss_r
    elif gross_profit_r > 0:
        profit_factor = None
    else:
        profit_factor = 0.0

    count = len(trades)

    return {
        "status": "ok",
        "symbol": config["market"]["symbol"],
        "timeframe": config["market"]["timeframe"],
        "trades_count": count,
        "winning_trades": len(winners),
        "losing_trades": len(losers),
        "win_rate_percent": (
            round(len(winners) / count * 100, 2) if count else 0.0
        ),
        "net_profit_r": round(equity_r, 4),
        "gross_profit_r": round(gross_profit_r, 4),
        "gross_loss_r": round(gross_loss_r, 4),
        "profit_factor": (
            round(profit_factor, 4)
            if profit_factor is not None
            else None
        ),
        "max_drawdown_r": round(max_drawdown_r, 4),
        "monetary_results_available": False,
        "trading_enabled": False,
        "trades": trades,
    }
