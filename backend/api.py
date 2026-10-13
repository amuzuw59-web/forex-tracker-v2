import os
import hmac
from datetime import datetime, timezone

from flask import Flask, jsonify, request

from backend.analysis import analyze_candles
from backend.data_provider import get_candles
from backend.demo_executor import validate_signal_freshness, execute_demo_signal

app = Flask(__name__)


@app.get("/")
def home():
    return jsonify({
        "name": "Forex Signal Tracker API",
        "version": "1.0.0",
        "status": "running",
        "automatic_trading": False,
        "endpoints": [
            "/health",
            "/api/signal",
        ],
    })


@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "forex-signal-tracker",
        "automatic_trading": False,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


@app.get("/api/signal")
def signal():
    try:
        symbol, timeframe, candles = get_candles()

        if candles is None or candles.empty:
            raise ValueError("No market candles are available.")

        latest_candle_time = candles.iloc[-1]["datetime"].isoformat()
        freshness = validate_signal_freshness(
            latest_candle_time,
            timeframe,
        )

        result = analyze_candles(candles)

        return jsonify({
            "status": "ok",
            "symbol": symbol,
            "timeframe": timeframe,
            "signal": result,
            "latest_candle": latest_candle_time,
            "candle_freshness": freshness,
            "candles_available": len(candles),
            "automatic_trading": False,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    except Exception:
        app.logger.exception("Signal endpoint failed")
        return jsonify({
            "status": "error",
            "message": "Market signal is temporarily unavailable.",
            "automatic_trading": False,
        }), 503




@app.post("/api/demo/execute")
def execute_demo():
    """Manually request safety-gated demo signal validation."""

    # Disabled by default.
    if os.getenv("DEMO_EXECUTION_API_ENABLED", "false").lower() != "true":
        return jsonify({
            "status": "disabled",
            "reason": "Demo execution endpoint is disabled.",
            "automatic_order_submitted": False,
        }), 404

    expected_token = os.getenv("DEMO_EXECUTION_API_TOKEN", "")
    provided_token = request.headers.get("Authorization", "")

    if (
        not expected_token
        or not hmac.compare_digest(
            provided_token,
            f"Bearer {expected_token}",
        )
    ):
        return jsonify({
            "status": "blocked",
            "reason": "Authentication required.",
            "automatic_order_submitted": False,
        }), 401
    import asyncio

    payload = request.get_json(silent=True) or {}

    if payload.get("manual_confirmation") is not True:
        return jsonify({
            "status": "blocked",
            "reason": "Explicit manual confirmation is required.",
            "automatic_order_submitted": False,
        }), 400

    try:
        symbol, timeframe, candles = get_candles()

        if candles is None or candles.empty:
            return jsonify({
                "status": "blocked",
                "reason": "No market candles are available.",
                "automatic_order_submitted": False,
            }), 503

        candle_time = candles.iloc[-1]["datetime"]
        if hasattr(candle_time, "isoformat"):
            candle_time = candle_time.isoformat()

        validate_signal_freshness(candle_time, timeframe)
        signal = analyze_candles(candles)

        if signal.get("signal") not in ("BUY", "SELL"):
            return jsonify({
                "status": "blocked",
                "reason": "No actionable BUY or SELL signal.",
                "signal": signal.get("signal"),
                "automatic_order_submitted": False,
            }), 200

        result = asyncio.run(
            execute_demo_signal(
                signal=signal,
                candle_id=f"{symbol}:{timeframe}:{candle_time}",
                candle_time=candle_time,
                manual_confirmation=True,
            )
        )

        return jsonify(result), 200

    except ValueError as exc:
        return jsonify({
            "status": "blocked",
            "reason": str(exc),
            "automatic_order_submitted": False,
        }), 400
    except Exception:
        app.logger.exception("Demo execution endpoint failed")
        return jsonify({
            "status": "error",
            "reason": "Demo execution request failed.",
            "automatic_order_submitted": False,
        }), 500

if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=8080,
        debug=False,
    )
