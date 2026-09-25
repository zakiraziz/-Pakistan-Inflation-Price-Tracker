"""
services/openapi.py
-------------------
A single declarative catalogue of the HTTP surface, used to build:

* ``/api/v1/openapi.json`` - a real OpenAPI 3.1 document, and
* ``/docs`` - a server-rendered API reference (no CDN, so it always loads).

Keeping the catalogue in one place means the docs cannot silently drift from
the API: a test asserts every documented path is registered on the app.
"""

from __future__ import annotations

API_VERSION = "1.0.0"

# Shared parameter definitions, referenced by name to avoid copy-paste drift.
P_START = {
    "name": "start",
    "in": "query",
    "type": "string",
    "format": "date",
    "default": "2025-07-01",
    "description": "First date of the window (inclusive, ISO yyyy-mm-dd).",
}
P_END = {
    "name": "end",
    "in": "query",
    "type": "string",
    "format": "date",
    "description": "Last date of the window (inclusive). Defaults to the latest observation.",
}
P_ITEMS = {
    "name": "items",
    "in": "query",
    "type": "string",
    "description": "Comma-separated item ids. Omit for every tracked item.",
    "example": "1,2,3",
}
P_THRESHOLD = {
    "name": "threshold",
    "in": "query",
    "type": "number",
    "default": 5,
    "description": "Percentage move in one week that counts as an alert.",
}

ENDPOINTS = [
    {
        "group": "Service",
        "method": "GET",
        "path": "/healthz",
        "summary": "Liveness probe",
        "description": "Process is up. Reports item count, approved/pending "
        "observations, latest date and uptime.",
        "auth": "public",
    },
    {
        "group": "Service",
        "method": "GET",
        "path": "/readyz",
        "summary": "Readiness probe",
        "description": "Schema present and at least one approved observation. "
        "503 until the dataset has been seeded.",
        "auth": "public",
    },
    {
        "group": "Service",
        "method": "GET",
        "path": "/api/version",
        "summary": "API version and capabilities",
        "description": "Version, build id and the capabilities this deployment "
        "exposes (cache backend, auth mode, live stream).",
        "auth": "public",
    },
    {
        "group": "Data",
        "method": "GET",
        "path": "/api/items",
        "summary": "Tracked items",
        "description": "Every item in the basket with category and unit.",
        "auth": "public",
    },
    {
        "group": "Data",
        "method": "GET",
        "path": "/api/series",
        "summary": "Filtered price series",
        "description": "Approved weekly observations as flat rows: name, date, price.",
        "params": [P_START, P_END, P_ITEMS],
        "auth": "public",
    },
    {
        "group": "Data",
        "method": "GET",
        "path": "/api/index",
        "summary": "Basket cost index",
        "description": "Equal-weight basket index, normalised to 100 on the "
        "first date of the window.",
        "params": [P_START, P_END, P_ITEMS],
        "auth": "public",
    },
    {
        "group": "Data",
        "method": "GET",
        "path": "/api/pivot",
        "summary": "Item x date matrix",
        "description": "Per-item price arrays plus the basket index - one call "
        "for a chart of everything.",
        "params": [P_START, P_END, P_ITEMS],
        "auth": "public",
    },
    {
        "group": "Analytics",
        "method": "GET",
        "path": "/api/metrics",
        "summary": "Summary metrics",
        "description": "Counts, first/last basket totals, basket change, "
        "biggest riser and biggest faller.",
        "params": [P_START, P_END, P_ITEMS],
        "auth": "public",
    },
    {
        "group": "Analytics",
        "method": "GET",
        "path": "/api/inflation",
        "summary": "Inflation rates",
        "description": "Basket change, annualised rate, average weekly rate "
        "and year-over-year change.",
        "params": [P_START, P_END, P_ITEMS],
        "auth": "public",
    },
    {
        "group": "Analytics",
        "method": "GET",
        "path": "/api/insights",
        "summary": "What changed and why",
        "description": "Rule-based narratives: headline basket move, top "
        "risers/fallers, threshold breaches and statistically unusual moves. "
        "Calculated facts are separated from possible contributing factors.",
        "params": [P_START, P_END, P_ITEMS, P_THRESHOLD],
        "auth": "public",
    },
    {
        "group": "Analytics",
        "method": "GET",
        "path": "/api/items/{slug}",
        "summary": "Item detail",
        "description": "Full history, statistics, volatility, contribution to "
        "the basket and the provenance of every observation for one item.",
        "params": [
            {
                "name": "slug",
                "in": "path",
                "type": "string",
                "required": True,
                "description": "URL slug of the item, e.g. 'onion'.",
            },
            P_START,
            P_END,
        ],
        "auth": "public",
    },
    {
        "group": "Analytics",
        "method": "GET",
        "path": "/api/compare",
        "summary": "Compare two windows",
        "description": "The same items across two date ranges, with the "
        "difference between the two changes to show acceleration or reversal.",
        "params": [
            P_ITEMS,
            {
                "name": "a_start", "in": "query", "type": "string",
                "format": "date", "required": True,
                "description": "Start of window A.",
            },
            {
                "name": "a_end", "in": "query", "type": "string",
                "format": "date", "description": "End of window A.",
            },
            {
                "name": "b_start", "in": "query", "type": "string",
                "format": "date", "required": True,
                "description": "Start of window B.",
            },
            {
                "name": "b_end", "in": "query", "type": "string",
                "format": "date", "description": "End of window B.",
            },
        ],
        "auth": "public",
    },
    {
        "group": "Alerts",
        "method": "GET",
        "path": "/api/alerts",
        "summary": "Price-jump alerts",
        "description": "Items whose most recent weekly move crossed the "
        "threshold, largest first.",
        "params": [P_START, P_END, P_THRESHOLD],
        "auth": "public",
    },
    {
        "group": "Alerts",
        "method": "GET",
        "path": "/api/alerts.csv",
        "summary": "Alerts as CSV",
        "description": "Download the alert list as a CSV file.",
        "params": [P_START, P_END, P_THRESHOLD],
        "auth": "public",
    },
    {
        "group": "Export",
        "method": "GET",
        "path": "/api/series.csv",
        "summary": "Series as CSV",
        "description": "Download the filtered price series as a CSV file.",
        "params": [P_START, P_END, P_ITEMS],
        "auth": "public",
    },
    {
        "group": "Export",
        "method": "GET",
        "path": "/api/export.json",
        "summary": "Bulk open-data export",
        "description": "One self-describing document: items, every approved "
        "observation, the basket index and the provenance summary.",
        "params": [P_START, P_END, P_ITEMS],
        "auth": "public",
    },
    {
        "group": "Transparency",
        "method": "GET",
        "path": "/api/status",
        "summary": "Data status",
        "description": "Coverage, freshness, counts by approval status, "
        "provenance rows and the ingestion audit log.",
        "auth": "public",
    },
    {
        "group": "Live",
        "method": "GET",
        "path": "/api/live",
        "summary": "Freshness snapshot",
        "description": "Cheap, never-cached revision and counts. Polled as the "
        "fallback when the event stream is unavailable.",
        "auth": "public",
    },
    {
        "group": "Live",
        "method": "GET",
        "path": "/api/stream",
        "summary": "Server-Sent Events stream",
        "description": "Emits 'hello' on connect, 'update' when the dataset "
        "changes, and periodic heartbeats.",
        "auth": "public",
    },
    {
        "group": "Admin",
        "method": "POST",
        "path": "/ingest/next",
        "summary": "Run the ingest job",
        "description": "Adds the next weekly observation for every item and "
        "recomputes alerts. Body: {date?, auto_approve?}.",
        "auth": "admin",
    },
    {
        "group": "Admin",
        "method": "GET",
        "path": "/api/admin/pending",
        "summary": "Review queue",
        "description": "Observations held back by validation, awaiting a human "
        "decision.",
        "auth": "admin",
    },
    {
        "group": "Admin",
        "method": "POST",
        "path": "/api/admin/approve",
        "summary": "Approve observations",
        "description": "Body: {ids: [...]} or {all: true}. Approved points "
        "enter the public index immediately.",
        "auth": "admin",
    },
    {
        "group": "Admin",
        "method": "POST",
        "path": "/api/admin/reject",
        "summary": "Reject observations",
        "description": "Body: {ids: [...]} or {all: true}. Rejected points are "
        "excluded everywhere.",
        "auth": "admin",
    },
]

PAGES = [
    ("/", "Dashboard", "Live charts, filters and alerts for the whole basket."),
    ("/items", "Items", "Every tracked item with change, trend and volatility."),
    ("/item/<slug>", "Item detail", "One item: history, statistics, provenance, insights."),
    ("/compare", "Compare", "Two items or two periods side by side."),
    ("/insights", "Insights", "What changed, by how much, and where to look next."),
    ("/alerts", "Alerts", "Threshold breaches with a link to the evidence."),
    ("/data", "Data", "Freshness, matrix view, bulk export and lineage."),
    ("/status", "Status", "Coverage, approval counts and ingestion audit log."),
    ("/docs", "API reference", "Every endpoint, with parameters and examples."),
    ("/admin/review", "Review queue", "Approve or reject held-back observations."),
    ("/methodology", "Methodology", "How the index is computed."),
]


def _operation(spec: dict) -> dict:
    params = []
    for p in spec.get("params", []):
        entry = {
            "name": p["name"],
            "in": p["in"],
            "required": p.get("required", False),
            "description": p.get("description", ""),
            "schema": {"type": p.get("type", "string")},
        }
        if p.get("format"):
            entry["schema"]["format"] = p["format"]
        if "default" in p:
            entry["schema"]["default"] = p["default"]
        if "example" in p:
            entry["schema"]["example"] = p["example"]
        params.append(entry)
    responses = {"200": {"description": "Success"}}
    if spec.get("auth") == "admin":
        responses.update(
            {
                "401": {"description": "Admin token required"},
                "403": {"description": "Admin surface disabled"},
                "429": {"description": "Rate limit exceeded"},
            }
        )
    else:
        responses.update({"404": {"description": "Not found"}})
    return {
        "summary": spec["summary"],
        "description": spec.get("description", ""),
        "tags": [spec["group"]],
        "parameters": params,
        "security": [{"adminToken": []}] if spec.get("auth") == "admin" else [],
        "responses": responses,
    }


def document(server_url: str = "/") -> dict:
    """Build the OpenAPI 3.1 document (canonical *and* versioned paths)."""
    paths: dict = {}
    for spec in ENDPOINTS:
        op = _operation(spec)
        candidates = [spec["path"]]
        if spec["path"].startswith("/api/") and not spec["path"].startswith("/api/v1/"):
            candidates.append("/api/v1" + spec["path"][4:])
        for path in candidates:
            paths.setdefault(path, {})[spec["method"].lower()] = op
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Pakistan Inflation / Price Tracker API",
            "version": API_VERSION,
            "description": (
                "Approved weekly prices for a basket of everyday goods in "
                "Pakistan, with a cost-of-living index, jump alerts and full "
                "provenance. Only approved observations are ever served. Every "
                "operation is also available under /api/v1/* - clients should "
                "prefer the versioned paths."
            ),
            "license": {"name": "MIT"},
        },
        "servers": [{"url": server_url}],
        "tags": sorted({spec["group"] for spec in ENDPOINTS}),
        "paths": paths,
        "components": {
            "securitySchemes": {
                "adminToken": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-Admin-Token",
                    "description": "Also accepted as 'Authorization: Bearer <token>'.",
                }
            }
        },
    }


def grouped() -> list:
    """ENDPOINTS grouped for the rendered reference page."""
    order = ["Service", "Data", "Analytics", "Alerts", "Export",
             "Transparency", "Live", "Admin"]
    return [
        (name, [e for e in ENDPOINTS if e["group"] == name])
        for name in order
        if any(e["group"] == name for e in ENDPOINTS)
    ]


def curl_example(spec: dict, server: str = "http://127.0.0.1:5010") -> str:
    """A copy-pasteable curl command for one endpoint."""
    path = spec["path"].replace("{slug}", "onion")
    example = [p for p in spec.get("params", []) if p.get("example")]
    query = "?" + "&".join(f"{p['name']}={p['example']}" for p in example) if example else ""
    if spec["method"] == "POST":
        return (
            f"curl -X POST {server}{path} "
            "-H 'Content-Type: application/json' -d '{}'"
        )
    return f"curl {server}{path}{query}"


def documented_paths() -> set:
    """Every path string the docs claim exists (used to test for drift)."""
    out = set()
    for spec in ENDPOINTS:
        out.add(spec["path"])
        if spec["path"].startswith("/api/"):
            out.add("/api/v1" + spec["path"][4:])
    return out
