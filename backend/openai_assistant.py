import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def ask_assistant(message):
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OpenAI API key is not configured.")

    model = os.environ.get("OPENAI_MODEL", "gpt-5.5")

    payload = {
        "model": model,
        "instructions": (
            "You are the Forex Signal Tracker v2 assistant. "
            "Explain technical indicators, API health, candle freshness, "
            "and risk controls clearly. Never claim a trade was executed "
            "unless verified by the backend. Do not submit orders, change "
            "trading settings, or promise trading profits. Explain that "
            "signals are not guarantees and broker costs must be verified."
        ),
        "input": message,
        "max_output_tokens": 350,
        "store": False,
    }

    request = Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise RuntimeError("OpenAI authentication or access failed.") from None
        if exc.code == 429:
            raise RuntimeError("OpenAI rate limit or quota reached.") from None
        raise RuntimeError(
            f"OpenAI request failed with HTTP {exc.code}."
        ) from None
    except (URLError, TimeoutError):
        raise RuntimeError("Could not reach the OpenAI API.") from None

    for item in result.get("output", []):
        if item.get("type") == "message":
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    answer = content.get("text", "").strip()
                    if answer:
                        return answer

    raise RuntimeError("OpenAI returned no assistant text.")
