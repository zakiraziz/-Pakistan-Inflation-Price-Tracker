"""
core/security.py
----------------
Security response headers and structured error handling.

- Strict-ish CSP that allows only what the dashboard needs (Chart.js CDN and
  Google Fonts); everything else is same-origin only.
- Errors never leak stack traces: exceptions are logged server-side and the
  client gets a predictable JSON envelope (APIs) or a plain page (browsers).
"""
from __future__ import annotations

import logging

from flask import jsonify, make_response, render_template_string, request
from werkzeug.exceptions import HTTPException

logger = logging.getLogger("app.security")

CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' https://cdn.jsdelivr.net",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data:",
    "connect-src 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
])

ERROR_PAGE = """
<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>{{ code }} · Pakistan Inflation Tracker</title>
<link rel="stylesheet" href="/static/style.css"></head>
<body><main class="errpage">
<h1>{{ code }}</h1><p>{{ message }}</p>
<p><a href="/">Back to the tracker</a></p></main></body></html>
"""


def _wants_json() -> bool:
    if request.path.startswith("/api/") or request.path == "/ingest/next":
        return True
    accept = request.headers.get("Accept", "")
    return "application/json" in accept and "text/html" not in accept


def _error_body(code: int, message: str):
    if _wants_json():
        return jsonify({"error": {"code": code, "message": message}}), code
    return render_template_string(ERROR_PAGE, code=code, message=message), code


def install(app) -> None:
    """Attach security headers and JSON error handling to ``app``."""

    @app.after_request
    def _headers(response):  # pragma: no cover - exercised via integration
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy",
                                    "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy",
                                    "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Content-Security-Policy", CSP)
        if app.config.get("FORCE_HTTPS"):
            response.headers.setdefault("Strict-Transport-Security",
                                        "max-age=31536000; includeSubDomains")
        return response

    @app.errorhandler(404)
    def _not_found(_e):
        return _error_body(404, "This page or endpoint does not exist.")

    @app.errorhandler(405)
    def _method_not_allowed(_e):
        return _error_body(405, "Method not allowed for this endpoint.")

    @app.errorhandler(429)
    def _too_many_requests(_e):
        # _error_body already returns a complete (body, code) tuple; wrapping it
        # again would make Flask raise and surface as a 500.
        response = make_response(_error_body(429, "Too many requests. Slow down."))
        response.headers["Retry-After"] = "60"
        return response

    @app.errorhandler(Exception)
    def _server_error(e):
        logger.exception("unhandled error on %s", request.path)
        if isinstance(e, HTTPException):
            return _error_body(e.code or 500, e.description or "Error")
        return _error_body(500, "Internal server error.")