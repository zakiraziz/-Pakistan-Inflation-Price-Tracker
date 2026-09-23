"""
services/readmodels.py
----------------------
Pure analytics over the price table: the numbers every page and endpoint shows.

Design rules
------------
* Only **approved** points are ever read here (the public index contract).
* Functions return plain dicts/lists so they can be serialised to JSON, fed to
  Jinja templates, or asserted on in tests without any Flask involvement.
* No rounding surprises: percentages are rounded once, at the boundary.
"""

from __future__ import annotations

import re
import statistics

import db

# ---------------------------------------------------------------------------
# Slugs / lookups
# ---------------------------------------------------------------------------

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    """'Wheat flour (atta)' -> 'wheat-flour-atta' (stable, URL-safe)."""
    return _SLUG_RE.sub("-", name.lower()).strip("-")


def all_items(con):
    """Every tracked item with its slug, ordered for stable display."""
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "category": r["category"],
            "unit": r["unit"],
            "slug": slugify(r["name"]),
        }
        for r in db.get_items(con)
    ]


def item_by_slug(con, slug: str):
    """Resolve a URL slug back to an item dict, or ``None``."""
    for item in all_items(con):
        if item["slug"] == slug:
            return item
    return None


def ids_for_slugs(con, slugs) -> list:
    """Map a list of slugs to item ids (unknown slugs are dropped)."""
    wanted = {s.strip() for s in slugs if s and s.strip()}
    return [i["id"] for i in all_items(con) if i["slug"] in wanted]


# ---------------------------------------------------------------------------
# Windows + raw series
# ---------------------------------------------------------------------------


def parse_window(args, default_start: str = "2025-07-01"):
    """(start, end, ids) from a request-like mapping (Flask ``request.args``)."""
    start = (args.get("start") or default_start or "").strip()
    end = (args.get("end") or "").strip()
    raw = (args.get("items") or "").strip()
    ids = [int(x) for x in raw.split(",") if x.strip().isdigit()] if raw else None
    return start, end, (ids or None)


def series(con, start="", end="", ids=None, status=db.STATUS_APPROVED):
    """Approved price rows for the window, oldest first."""
    if ids is None:
        ids = [i["id"] for i in all_items(con)]
    if not ids:
        con.close()
        return []
    ph = ",".join("?" * len(ids))
    q = (
        "SELECT i.name AS name, i.category AS category, i.unit AS unit, "
        "       p.date AS date, p.price AS price "
        "FROM prices p JOIN items i ON i.id = p.item_id "
        f"WHERE p.status = ? AND p.item_id IN ({ph})"
    )
    params: list = [status, *ids]
    if start:
        q += " AND p.date >= ?"
        params.append(start)
    if end:
        q += " AND p.date <= ?"
        params.append(end)
    q += " ORDER BY p.date, i.name"
    rows = [dict(r) for r in con.execute(q, params).fetchall()]
    con.close()
    return rows


def series_of(con, item_id: int, start="", end=""):
    """Price history for one item (approved only), with its provenance."""
    q = (
        "SELECT date, price, source, method, collected_at FROM prices "
        "WHERE item_id = ? AND status = ?"
    )
    params: list = [item_id, db.STATUS_APPROVED]
    if start:
        q += " AND date >= ?"
        params.append(start)
    if end:
        q += " AND date <= ?"
        params.append(end)
    q += " ORDER BY date"
    rows = [dict(r) for r in con.execute(q, params).fetchall()]
    con.close()
    return rows
