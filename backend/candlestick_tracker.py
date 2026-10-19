"""Rule-based candlestick outlook. Analysis only; never places orders."""

import math

import pandas as pd

from backend.analysis import calculate_indicators


def track_next_move(candles, symbol="XAUUSD", timeframe="5m"):
    """Analyze closed OHLC candles and return a cautious next-move outlook."""
    result = {
        "status": "unavailable",
        "symbol": symbol,
        "timeframe": timeframe,
        "pattern": "UNKNOWN",
        "outlook": "NEUTRAL",
        "score": 0,
        "score_meaning": "Rule-based agreement score, not win probability.",
        "latest_close": None,
        "atr14": None,
        "upside_scenario": None,
        "downside_scenario": None,
        "confirmation": "Wait for the next candle to close.",
        "order_execution_enabled": False,
    }

    if not isinstance(candles, pd.DataFrame) or len(candles) < 60:
        result["message"] = "At least 60 closed candles are required."
        return result

    try:
        df = calculate_indicators(candles)
        previous = df.iloc[-2]
        current = df.iloc[-1]

        values = [
            current["open"], current["high"], current["low"],
            current["close"], current["EMA20"], current["EMA50"],
            current["RSI14"], current["ATR14"],
        ]
        if not all(math.isfinite(float(v)) for v in values):
            result["message"] = "Indicator data is incomplete."
            return result

        o, h, low, c = map(
            float, (current["open"], current["high"],
                    current["low"], current["close"])
        )
        po, pc = float(previous["open"]), float(previous["close"])
        candle_range = h - low
        if candle_range <= 0:
            result["message"] = "Latest candle has no usable range."
            return result

        body = abs(c - o)
        upper_wick = h - max(o, c)
        lower_wick = min(o, c) - low

        pattern = "NO_CLEAR_PATTERN"
        pattern_bias = 0

        # Two-candle reversal patterns
        if pc < po and c > o and o <= pc and c >= po:
            pattern, pattern_bias = "BULLISH_ENGULFING", 2
        elif pc > po and c < o and o >= pc and c <= po:
            pattern, pattern_bias = "BEARISH_ENGULFING", -2
        # Single-candle patterns
        elif body / candle_range <= 0.10:
            pattern = "DOJI"
        elif (
            lower_wick >= 2 * max(body, candle_range * 0.01)
            and upper_wick <= body
            and c > low + candle_range * 0.55
        ):
            pattern, pattern_bias = "HAMMER", 1
        elif (
            upper_wick >= 2 * max(body, candle_range * 0.01)
            and lower_wick <= body
            and c < low + candle_range * 0.45
        ):
            pattern, pattern_bias = "SHOOTING_STAR", -1

        ema20, ema50 = float(current["EMA20"]), float(current["EMA50"])
        rsi, atr = float(current["RSI14"]), float(current["ATR14"])

        # Directional evidence; intentionally not a trained probability.
        score = pattern_bias
        if ema20 > ema50:
            score += 1
        elif ema20 < ema50:
            score -= 1

        if c > ema20:
            score += 1
        elif c < ema20:
            score -= 1

        if 50 < rsi < 70:
            score += 1
        elif 30 < rsi < 50:
            score -= 1

        # Require more than a single weak clue for a directional outlook.
        outlook = "BULLISH" if score >= 2 else (
            "BEARISH" if score <= -2 else "NEUTRAL"
        )

        result.update({
            "status": "ok",
            "pattern": pattern,
            "outlook": outlook,
            "score": score,
            "latest_close": c,
            "atr14": atr,
            "ema20": ema20,
            "ema50": ema50,
            "rsi14": rsi,
            "upside_scenario": round(c + atr, 2),
            "downside_scenario": round(c - atr, 2),
            "message": (
                "Rule-based outlook from the latest closed candle. "
                "Not a guarantee or a calibrated probability."
            ),
        })
        return result

    except (ValueError, TypeError, KeyError, IndexError) as exc:
        result["message"] = f"Tracker could not analyze these candles: {exc}"
        return result
