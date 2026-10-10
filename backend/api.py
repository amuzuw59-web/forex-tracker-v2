from datetime import datetime, timezone

from flask import Flask, jsonify

from backend.analysis import analyze_candles
from backend.data_provider import get_candles

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

        result = analyze_candles(candles)

        return jsonify({
            "status": "ok",
            "symbol": symbol,
            "timeframe": timeframe,
            "signal": result,
            "latest_candle": candles.iloc[-1]["datetime"].isoformat(),
            "candles_available": len(candles),
            "automatic_trading": False,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    except Exception as exc:
        app.logger.exception("Signal endpoint failed")
        return jsonify({
            "status": "error",
            "message": str(exc),
            "automatic_trading": False,
        }), 503


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=8080,
        debug=False,
    )
