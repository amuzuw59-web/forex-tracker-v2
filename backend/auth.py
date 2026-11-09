"""Google OpenID Connect authentication for the Flask web surface.

The OAuth client is configured only from environment variables. Authlib stores
and verifies the OAuth state in Flask's signed session cookie and validates the
Google ID token using Google's discovery document/JWKS metadata.
"""

from __future__ import annotations

import os
from functools import wraps
from urllib.parse import urlparse

from authlib.integrations.flask_client import OAuth
from flask import jsonify, redirect, request, session, url_for


GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"


def _configured(value: str | None) -> bool:
    return bool(value and value.strip())


def google_oauth_configured() -> bool:
    return _configured(os.getenv("GOOGLE_CLIENT_ID")) and _configured(
        os.getenv("GOOGLE_CLIENT_SECRET")
    )


def safe_next_path(value: str | None) -> str:
    """Allow only a local path to prevent an open redirect after login."""
    if not value:
        return "/dashboard"
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc or not value.startswith("/") or value.startswith("//"):
        return "/dashboard"
    return value


def configure_oauth(oauth: OAuth) -> None:
    oauth.register(
        name="google",
        server_metadata_url=GOOGLE_DISCOVERY_URL,
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        client_kwargs={"scope": "openid email profile"},
    )


def current_user() -> dict | None:
    user = session.get("user")
    return user if isinstance(user, dict) else None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user() is not None:
            return view(*args, **kwargs)
        if request.path.startswith("/api/"):
            return jsonify({"status": "unauthorized", "message": "Sign-in required."}), 401
        next_path = request.full_path.rstrip("?")
        return redirect(url_for("login", next=next_path))

    return wrapped
