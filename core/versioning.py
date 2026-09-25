"""
core/versioning.py
------------------
Version the public API surface.

Every ``/api/...`` operation is also reachable at ``/api/v1/...``. The alias is
added programmatically from the *same view function*, so the two paths can never
drift apart in behaviour, and clients get a stable, explicit contract to pin
against. ``/api/version`` advertises the version and this deployment's
capabilities, and ``X-API-Version`` is stamped on every API response.

Aliases under ``/api/admin/...`` are protected exactly like their canonical
counterparts (see :mod:`core.auth`).
"""

from __future__ import annotations

import os

import log
from services.openapi import API_VERSION

logger = log.get_logger("versioning")

ALIAS_PREFIX = "/api/v1"


def install(app) -> int:
    """Register ``/api/version`` and ``/api/v1/*`` aliases. Returns alias count."""

    @app.route("/api/version")
    def api_version():
        """Version and capabilities of this deployment (uncacheable)."""
        from flask import jsonify, request

        response = jsonify(
            {
                "api_version": API_VERSION,
                "openapi": "3.1.0",
                "aliases": ALIAS_PREFIX + "/*",
                "canonical": "/api/*",
                "asset_version": app.config.get("ASSET_VERSION", "0"),
                "requested_path": request.path,
                "capabilities": {
                    "cache": app.config.get("CACHE_TYPE", "SimpleCache"),
                    "cache_ttl_seconds": app.config.get("CACHE_DEFAULT_TIMEOUT", 0),
                    "rate_limit": app.config.get("DEFAULT_RATELIMIT", "300 per minute"),
                    "admin_token_required": bool(os.environ.get("ADMIN_TOKEN", "").strip()),
                    "live_stream": "/api/stream",
                    "sse_events": ["hello", "update", "heartbeat"],
                    "pages": [
                        "/", "/items", "/item/<slug>", "/compare", "/insights",
                        "/alerts", "/data", "/status", "/docs", "/admin/review",
                        "/methodology",
                    ],
                },
            }
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.after_request
    def _stamp_version(response):  # pragma: no cover - header only
        if response.mimetype == "text/event-stream":
            return response
        response.headers.setdefault("X-API-Version", API_VERSION)
        return response

    # Alias pass runs last so it sees every rule registered above, including
    # /api/version and the openapi document.
    added = 0
    for rule in list(app.url_map.iter_rules()):
        path = rule.rule
        if not path.startswith("/api/") or path.startswith(ALIAS_PREFIX + "/"):
            continue
        alias = ALIAS_PREFIX + path[len("/api"):]
        endpoint = "v1_" + rule.endpoint
        if endpoint in app.view_functions:
            continue
        methods = sorted((rule.methods or set()) - {"HEAD", "OPTIONS"})
        app.add_url_rule(
            alias,
            endpoint=endpoint,
            view_func=app.view_functions[rule.endpoint],
            methods=methods or ["GET"],
        )
        added += 1

    logger.info("registered %s versioned API alias(es) under %s", added, ALIAS_PREFIX)
    return added
