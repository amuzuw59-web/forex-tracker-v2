import os
import asyncio
import secrets
import hmac
import threading
import time
from datetime import datetime, timezone

from flask import Flask, jsonify, request

from backend.analysis import analyze_candles
from backend.candlestick_tracker import track_next_move
from backend.data_provider import get_candles
from backend.demo_executor import validate_signal_freshness, execute_demo_signal
from backend.signal_identity import make_signal_identity

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


_signal_cache = {"payload": None, "cached_at": 0.0}
_signal_cache_lock = threading.Lock()
_SIGNAL_CACHE_TTL_SECONDS = 20

_DEMO_PROPOSAL_TTL_SECONDS = 120
_demo_proposals = {}
_demo_proposals_lock = threading.Lock()


def _demo_request_authenticated():
    expected_token = os.getenv("DEMO_EXECUTION_API_TOKEN", "")
    provided_token = request.headers.get("Authorization", "")
    return bool(
        expected_token
        and hmac.compare_digest(provided_token, f"Bearer {expected_token}")
    )


def _expire_demo_proposals(now):
    expired = [
        proposal_id
        for proposal_id, proposal in _demo_proposals.items()
        if now - proposal["created_at"] >= _DEMO_PROPOSAL_TTL_SECONDS
    ]
    for proposal_id in expired:
        _demo_proposals.pop(proposal_id, None)



def _build_signal_payload():
    symbol, timeframe, candles = get_candles()
    if candles is None or candles.empty:
        raise ValueError("No market candles are available.")

    latest_candle_time = candles.iloc[-1]["datetime"].isoformat()
    freshness = validate_signal_freshness(latest_candle_time, timeframe)
    result = analyze_candles(candles)

    # Informational only: tracker failures must not break existing signals.
    try:
        candlestick_tracker = track_next_move(
            candles, symbol=symbol, timeframe=timeframe
        )
    except Exception:
        app.logger.exception("Candlestick tracker analysis failed")
        candlestick_tracker = {
            "status": "unavailable",
            "symbol": symbol,
            "timeframe": timeframe,
            "outlook": "NEUTRAL",
            "message": "Candlestick outlook is temporarily unavailable.",
            "order_execution_enabled": False,
        }

    return {
        "status": "ok",
        "symbol": symbol,
        "timeframe": timeframe,
        "signal": result,
        "candlestick_tracker": candlestick_tracker,
        "latest_candle": latest_candle_time,
        "candle_freshness": freshness,
        "candles_available": len(candles),
        "automatic_trading": False,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


from backend.openai_assistant import ask_assistant


@app.post("/api/assistant")
def assistant():
    expected = os.environ.get("ASSISTANT_ACCESS_TOKEN", "").strip()
    supplied = request.headers.get("X-Assistant-Token", "")

    if not expected:
        return jsonify({
            "status": "error",
            "error": "Assistant access is not configured."
        }), 503

    if not supplied or not hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8")):
        return jsonify({"error": "Unauthorized."}), 401

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "Send a JSON object."}), 400

    message = body.get("message")
    if not isinstance(message, str) or not message.strip():
        return jsonify({"error": "A message is required."}), 400
    if len(message) > 2000:
        return jsonify({"error": "Message exceeds 2000 characters."}), 413

    try:
        answer = ask_assistant(message.strip())
        return jsonify({"status": "ok", "answer": answer}), 200
    except RuntimeError as exc:
        return jsonify({"status": "error", "error": str(exc)}), 503
    except Exception:
        app.logger.exception("AI assistant request failed")
        return jsonify({
            "status": "error",
            "error": "Assistant temporarily unavailable."
        }), 503

@app.get("/api/signal")
def signal():
    try:
        # Tests bypass the cache so mocked data remains isolated per test.
        if app.testing:
            return jsonify(_build_signal_payload())

        now = time.monotonic()
        with _signal_cache_lock:
            payload = _signal_cache["payload"]
            cache_age = now - _signal_cache["cached_at"]

            if payload is None or cache_age >= _SIGNAL_CACHE_TTL_SECONDS:
                payload = _build_signal_payload()
                _signal_cache["payload"] = payload
                _signal_cache["cached_at"] = time.monotonic()
            else:
                payload = dict(payload)
                payload["candle_freshness"] = validate_signal_freshness(
                    payload["latest_candle"], payload["timeframe"]
                )
                payload["timestamp"] = datetime.now(timezone.utc).isoformat()

        return jsonify(payload)
    except Exception:
        app.logger.exception("Signal endpoint failed")
        return jsonify({
            "status": "error",
            "message": "Market signal is temporarily unavailable.",
            "automatic_trading": False,
        }), 503


@app.post("/api/demo/proposal")
def create_demo_proposal():
    """Create a short-lived, broker-validated proposal without submitting."""
    if os.getenv("DEMO_EXECUTION_API_ENABLED", "false").lower() != "true":
        return jsonify({
            "status": "disabled",
            "reason": "Demo execution API is disabled.",
            "automatic_order_submitted": False,
        }), 404

    if not _demo_request_authenticated():
        return jsonify({
            "status": "blocked",
            "reason": "Authentication required.",
            "automatic_order_submitted": False,
        }), 401

    try:
        payload = _build_signal_payload()
        signal = payload["signal"]
        if signal.get("signal") not in ("BUY", "SELL"):
            return jsonify({
                "status": "blocked",
                "reason": "No actionable BUY or SELL signal is available.",
                "automatic_order_submitted": False,
            }), 409

        candle_time = payload["latest_candle"]
        symbol = payload["symbol"]
        timeframe = payload["timeframe"]
        candle_id = make_signal_identity(symbol, timeframe, candle_time)

        # Preflight validates broker/account/risk details but cannot submit.
        result = asyncio.run(execute_demo_signal(
            signal=signal,
            candle_id=candle_id,
            candle_time=candle_time,
            prepare_only=True,
        ))

        if result.get("status") != "proposal_ready":
            return jsonify({
                "status": result.get("status", "blocked"),
                "reason": result.get("reason", result.get("message", "Preflight failed.")),
                "automatic_order_submitted": False,
            }), 409

        proposal_id = secrets.token_urlsafe(24)
        now = time.monotonic()
        proposal = {
            "proposal_id": proposal_id,
            "created_at": now,
            "approved": False,
            "symbol": symbol,
            "timeframe": timeframe,
            "signal": signal["signal"],
            "candle_time": candle_time,
            "candle_id": candle_id,
            "entry_price": result["entry_price"],
            "stop_loss": result["stop_loss"],
            "take_profit": result["take_profit"],
            "volume": result["volume"],
            "estimated_loss": result["estimated_loss"],
            "maximum_allowed_loss": result["maximum_allowed_loss"],
            "risk_percent": result["risk_percent"],
        }

        with _demo_proposals_lock:
            _expire_demo_proposals(now)
            _demo_proposals[proposal_id] = proposal

        return jsonify({
            "status": "proposal_ready",
            "proposal": {
                key: value for key, value in proposal.items()
                if key not in ("created_at", "approved")
            },
            "expires_in_seconds": _DEMO_PROPOSAL_TTL_SECONDS,
            "approval_required": True,
            "automatic_order_submitted": False,
        }), 200

    except Exception:
        app.logger.exception("Demo proposal creation failed")
        return jsonify({
            "status": "error",
            "reason": "Unable to prepare a demo trade proposal.",
            "automatic_order_submitted": False,
        }), 503


@app.post("/api/demo/approve")
def approve_demo_proposal():
    """Approve one exact proposal; approval alone never places an order."""
    if os.getenv("DEMO_EXECUTION_API_ENABLED", "false").lower() != "true":
        return jsonify({
            "status": "disabled",
            "reason": "Demo execution API is disabled.",
            "automatic_order_submitted": False,
        }), 404

    if not _demo_request_authenticated():
        return jsonify({
            "status": "blocked",
            "reason": "Authentication required.",
            "automatic_order_submitted": False,
        }), 401

    body = request.get_json(silent=True) or {}
    proposal_id = body.get("proposal_id")

    if body.get("approve") is not True or not isinstance(proposal_id, str):
        return jsonify({
            "status": "blocked",
            "reason": "Explicit approval and a valid proposal ID are required.",
            "automatic_order_submitted": False,
        }), 400

    now = time.monotonic()
    with _demo_proposals_lock:
        _expire_demo_proposals(now)
        proposal = _demo_proposals.get(proposal_id)

        if proposal is None:
            return jsonify({
                "status": "blocked",
                "reason": "Proposal is missing or expired.",
                "automatic_order_submitted": False,
            }), 409

        if proposal["approved"]:
            return jsonify({
                "status": "blocked",
                "reason": "This proposal has already been approved.",
                "automatic_order_submitted": False,
            }), 409

        proposal["approved"] = True

    return jsonify({
        "status": "approved_not_submitted",
        "proposal_id": proposal_id,
        "message": (
            "Proposal approved. Execution still requires fresh-signal "
            "matching, broker validation, and enabled safety gates."
        ),
        "automatic_order_submitted": False,
    }), 200


@app.post("/api/demo/execute")
def execute_demo():
    """Execute only an approved, unexpired, single-use proposal."""
    if os.getenv("DEMO_EXECUTION_API_ENABLED", "false").lower() != "true":
        return jsonify({
            "status": "disabled",
            "reason": "Demo execution API is disabled.",
            "automatic_order_submitted": False,
        }), 404

    if not _demo_request_authenticated():
        return jsonify({
            "status": "blocked",
            "reason": "Authentication required.",
            "automatic_order_submitted": False,
        }), 401

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        body = {}

    proposal_id = body.get("proposal_id")
    if not isinstance(proposal_id, str) or not proposal_id.strip():
        return jsonify({
            "status": "blocked",
            "reason": "A valid proposal ID is required.",
            "automatic_order_submitted": False,
        }), 409

    # Atomically consume the approval before external work.
    with _demo_proposals_lock:
        _expire_demo_proposals(time.monotonic())
        stored = _demo_proposals.get(proposal_id)

        if stored is None:
            return jsonify({
                "status": "blocked",
                "reason": "Proposal is missing or expired.",
                "automatic_order_submitted": False,
            }), 409

        if not stored.get("approved"):
            return jsonify({
                "status": "blocked",
                "reason": "Explicit proposal approval is required.",
                "automatic_order_submitted": False,
            }), 409

        if stored.get("execution_claimed"):
            return jsonify({
                "status": "blocked",
                "reason": "Proposal has already been claimed.",
                "automatic_order_submitted": False,
            }), 409

        stored["execution_claimed"] = True
        proposal = dict(stored)

    try:
        # Always fetch fresh market data; do not trust a cached signal.
        payload = _build_signal_payload()
        signal = payload.get("signal")

        if not isinstance(signal, dict):
            raise ValueError("Fresh signal payload is invalid.")

        symbol = payload.get("symbol")
        timeframe = payload.get("timeframe")
        candle_time = payload.get("latest_candle")

        if signal.get("signal") not in ("BUY", "SELL"):
            raise ValueError("Fresh signal is no longer actionable.")

        candle_id = make_signal_identity(symbol, timeframe, candle_time)

        if (
            symbol != proposal.get("symbol")
            or timeframe != proposal.get("timeframe")
            or signal.get("signal") != proposal.get("signal")
            or candle_time != proposal.get("candle_time")
            or candle_id != proposal.get("candle_id")
        ):
            return jsonify({
                "status": "blocked",
                "reason": "Fresh signal differs from the approved proposal.",
                "automatic_order_submitted": False,
            }), 409

        result = asyncio.run(execute_demo_signal(
            signal=signal,
            candle_id=candle_id,
            candle_time=candle_time,
            manual_confirmation=True,
            expected_proposal=proposal,
        ))

        submission_status = result.get("status")
        verified = submission_status in (
            "verified_position",
            "verified_order",
        )

        return jsonify({
            **result,
            "proposal_id": proposal_id,
            "automatic_order_submitted": verified,
            "broker_state_verified": verified,
            "open_position_verified": (
                submission_status == "verified_position"
            ),
        }), (200 if verified else 409)

    except Exception:
        app.logger.exception("Approved demo execution was blocked")
        return jsonify({
            "status": "blocked",
            "reason": (
                "Execution could not be safely verified. "
                "The proposal is consumed; create a new one if needed."
            ),
            "proposal_id": proposal_id,
            "automatic_order_submitted": False,
        }), 503


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=8080,
        debug=False,
    )
