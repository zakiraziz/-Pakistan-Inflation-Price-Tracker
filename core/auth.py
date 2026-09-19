"""
core/auth.py
------------
Protection for the *write* / admin surface.

``/api/admin/*`` and ``POST /ingest/next`` mutate the dataset (approve, reject,
ingest). On a public deployment anybody could call them, so they are **closed by
default**:

=================  ==========================================================
``ADMIN_TOKEN``    behaviour
=================  ==========================================================
set                every request to a protected route must present the token
                   (``X-Admin-Token: <token>`` or ``Authorization: Bearer <token>``)
unset              only strict-loopback callers (``127.0.0.1`` / ``::1``) may
                   call protected routes; everyone else gets 403
=================  ==========================================================

Strict loopback (not private ranges) is deliberate: behind a reverse proxy —
Render, nginx, Caddy — ``remote_addr`` is the *proxy's* address, so a public
request never looks local. Local development and the test client keep working
untouched.

Comparison uses :func:`hmac.compare_digest` so a wrong token cannot be guessed
byte-by-byte from response timing.
"""

from __future__ import annotations

import hmac
import os

from flask import jsonify, request

import log

logger = log.get_logger("auth")

PROTECTED_PREFIX = "/api/admin/"
PROTECTED_POST = {"/ingest/next"}

LOOPBACK = {"127.0.0.1", "::1", "::ffff:127.0.0.1"}


def _configured_token() -> str:
    """Read the token per request so it can be rotated without a restart."""
    return os.environ.get("ADMIN_TOKEN", "").strip()


def _allow_local() -> bool:
    raw = os.environ.get("ADMIN_ALLOW_LOCAL")
    if raw is None:
        return True
    return raw.strip().lower() not in ("0", "false", "no", "off", "")


def is_protected(method: str, path: str) -> bool:
    """True when this request can change data / inspect the review queue."""
    if path.startswith(PROTECTED_PREFIX):
        return True
    return method.upper() == "POST" and path in PROTECTED_POST


def _presented_token() -> str:
    direct = request.headers.get("X-Admin-Token", "").strip()
    if direct:
        return direct
    auth = request.headers.get("Authorization", "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


def _is_loopback() -> bool:
    return (request.remote_addr or "") in LOOPBACK


def _deny(code: int, message: str, hint: str = ""):
    body = {"error": {"code": code, "message": message}}
    if hint:
        body["error"]["hint"] = hint
    response = jsonify(body)
    response.status_code = code
    if code == 401:
        response.headers["WWW-Authenticate"] = 'Bearer realm="admin"'
    return response


def install(app) -> None:
    """Attach the write/admin guard to ``app``."""

    @app.before_request
    def _guard_admin():
        if not is_protected(request.method, request.path):
            return None

        token = _configured_token()
        if token:
            presented = _presented_token()
            if presented and hmac.compare_digest(presented, token):
                return None
            logger.warning(
                "rejected %s %s: missing/invalid admin token", request.method, request.path
            )
            return _deny(
                401,
                "A valid admin token is required for this endpoint.",
                "Send it as 'X-Admin-Token: <token>' or " "'Authorization: Bearer <token>'.",
            )

        if _allow_local() and _is_loopback():
            return None

        logger.warning(
            "rejected %s %s: admin endpoints are closed " "(no ADMIN_TOKEN, remote caller)",
            request.method,
            request.path,
        )
        return _deny(
            403,
            "Admin endpoints are disabled on this deployment.",
            "Set ADMIN_TOKEN to enable authenticated writes.",
        )

    if not _configured_token():
        logger.warning(
            "ADMIN_TOKEN is not set: admin/write endpoints accept "
            "loopback callers only (set ADMIN_ALLOW_LOCAL=0 to close "
            "them entirely, or ADMIN_TOKEN=<secret> to enable them)"
        )
