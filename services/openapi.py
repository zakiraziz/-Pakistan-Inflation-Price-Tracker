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
]
