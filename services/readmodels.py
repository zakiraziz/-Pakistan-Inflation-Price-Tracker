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


# ---------------------------------------------------------------------------
# Shaping helpers
# ---------------------------------------------------------------------------


def group_by_item(rows):
    """{name: {"category":…, "unit":…, "points": [(date, price), …]}}"""
    out: dict = {}
    for r in rows:
        bucket = out.setdefault(
            r["name"], {"category": r["category"], "unit": r["unit"], "points": []}
        )
        bucket["points"].append((r["date"], r["price"]))
    for bucket in out.values():
        bucket["points"].sort()
    return out


def weekly_changes(prices):
    """Week-over-week percentage changes for a list of prices."""
    out = []
    for prev, cur in zip(prices, prices[1:]):
        if prev:
            out.append((cur - prev) / prev * 100.0)
    return out


def volatility(prices):
    """Standard deviation of weekly % changes (0.0 when undefined)."""
    changes = weekly_changes(prices)
    if len(changes) < 2:
        return 0.0
    return statistics.pstdev(changes)


def trend_direction(prices, lookback: int = 4, flat_band: float = 1.0) -> str:
    """'Rising' / 'Falling' / 'Stable' from the last ``lookback`` weeks."""
    if len(prices) < lookback * 2:
        return "Stable"
    recent = statistics.fmean(prices[-lookback:])
    prior = statistics.fmean(prices[-lookback * 2 : -lookback])
    if not prior:
        return "Stable"
    pct = (recent - prior) / prior * 100.0
    if pct > flat_band:
        return "Rising"
    if pct < -flat_band:
        return "Falling"
    return "Stable"


def stats(prices) -> dict:
    """Summary statistics for one item's price path."""
    if not prices:
        return {
            "weeks": 0, "first": 0.0, "last": 0.0, "min": 0.0, "max": 0.0,
            "mean": 0.0, "pct": 0.0, "volatility": 0.0, "trend": "Stable",
            "consecutive": 0, "last_change_pct": 0.0, "zscore": None,
        }
    first, last = prices[0], prices[-1]
    changes = weekly_changes(prices)
    consecutive = 0
    for change in reversed(changes):
        if change > 0:
            consecutive += 1
        else:
            break
    return {
        "weeks": len(prices),
        "first": round(first, 2),
        "last": round(last, 2),
        "min": round(min(prices), 2),
        "max": round(max(prices), 2),
        "mean": round(statistics.fmean(prices), 2),
        "pct": round((last - first) / first * 100.0, 2) if first else 0.0,
        "volatility": round(volatility(prices), 2),
        "trend": trend_direction(prices),
        "consecutive": consecutive,
        "last_change_pct": round(changes[-1], 2) if changes else 0.0,
        "zscore": zscore_of_last_change(prices),
    }


def zscore_of_last_change(prices):
    """How unusual the newest week-over-week move is vs this item's own history.

    Returns ``None`` when there is not enough history to say anything. Beyond
    ±2 is the classic "two standard deviations" flag; the pages always label
    this as *calculated from the data you can see*, never as a cause.
    """
    changes = weekly_changes(prices)
    if len(changes) < 8:
        return None
    sd = statistics.pstdev(changes)
    if sd == 0:
        return None
    return round((changes[-1] - statistics.fmean(changes)) / sd, 2)


def basket_index(rows):
    """Equal-weight basket cost index (100 on the first date of the window)."""
    totals: dict = {}
    for r in rows:
        totals[r["date"]] = totals.get(r["date"], 0.0) + r["price"]
    dates = sorted(totals)
    if not dates or not totals[dates[0]]:
        return []
    base = totals[dates[0]]
    return [{"date": d, "index": round(totals[d] / base * 100.0, 2)} for d in dates]


def basket_totals(rows):
    """[(date, total)] - the raw cost of the basket each week."""
    totals: dict = {}
    for r in rows:
        totals[r["date"]] = totals.get(r["date"], 0.0) + r["price"]
    return [(d, round(totals[d], 2)) for d in sorted(totals)]


def annualized(pct: float, weeks: int) -> float:
    """Annualise a percentage change observed over ``weeks`` weekly points."""
    if weeks < 2 or pct <= -100:
        return 0.0
    growth = 1.0 + pct / 100.0
    return (growth ** (52.0 / (weeks - 1)) - 1.0) * 100.0


def monthly_rollup(rows):
    """[(month, average basket cost)] - a coarse view for long windows."""
    buckets: dict = {}
    for d, total in basket_totals(rows):
        buckets.setdefault(d[:7], []).append(total)
    return [(m, round(sum(v) / len(v), 2)) for m, v in sorted(buckets.items())]


def item_views(con, start="", end="", ids=None):
    """Per-item rows for tables: price path, change, volatility, contribution.

    ``contribution_pct`` is the item's share of the basket's total move, in
    percentage points - summed across items it reconstructs the basket change.
    """
    rows = series(con, start, end, ids)
    grouped = group_by_item(rows)
    basket_first = sum(b["points"][0][1] for b in grouped.values() if b["points"])
    out = []
    for name, bucket in grouped.items():
        prices = [p for _, p in bucket["points"]]
        st = stats(prices)
        delta = st["last"] - st["first"]
        out.append(
            {
                "name": name,
                "slug": slugify(name),
                "category": bucket["category"],
                "unit": bucket["unit"],
                "series": prices,
                "dates": [d for d, _ in bucket["points"]],
                "contribution_pct": (
                    round(delta / basket_first * 100.0, 2) if basket_first else 0.0
                ),
                **st,
            }
        )
    out.sort(key=lambda r: r["pct"], reverse=True)
    return out


def basket_summary(views) -> dict:
    """Aggregate per-item views into the basket-level headline figures."""
    if not views:
        return {
            "start_total": 0.0, "end_total": 0.0, "pct": 0.0, "annualized": 0.0,
            "weeks": 0, "count": 0, "volatility": 0.0, "sharing_rises": "0/0",
        }
    start_total = sum(v["first"] for v in views)
    end_total = sum(v["last"] for v in views)
    pct = (end_total - start_total) / start_total * 100.0 if start_total else 0.0
    weeks = max(v["weeks"] for v in views)
    rises = [v for v in views if v["pct"] > 0]
    return {
        "start_total": round(start_total, 2),
        "end_total": round(end_total, 2),
        "pct": round(pct, 2),
        "annualized": round(annualized(pct, weeks), 2),
        "weeks": weeks,
        "count": len(views),
        "volatility": round(sum(v["volatility"] for v in views) / len(views), 2),
        "sharing_rises": f"{len(rises)}/{len(views)}",
    }


def top_movers(views, n: int = 5):
    """(risers, fallers) - the biggest changers in the window."""
    ordered = sorted(views, key=lambda v: v["pct"], reverse=True)
    risers = [v for v in ordered if v["pct"] > 0][:n]
    fallers = [v for v in reversed(ordered) if v["pct"] < 0][:n]
    return risers, fallers


def compare_windows(con, first: dict, second: dict, ids=None):
    """Compare the same items across two windows (acceleration vs reversal)."""
    a = {
        r["name"]: r
        for r in item_views(con, first.get("start", ""), first.get("end", ""), ids)
    }
    b = {
        r["name"]: r
        for r in item_views(con, second.get("start", ""), second.get("end", ""), ids)
    }
    names = [n for n in a if n in b] or sorted(set(a) | set(b))
    out = []
    for name in names:
        ra, rb = a.get(name), b.get(name)
        pct_a = ra["pct"] if ra else None
        pct_b = rb["pct"] if rb else None
        out.append(
            {
                "name": name,
                "slug": slugify(name),
                "category": (ra or rb)["category"],
                "unit": (ra or rb)["unit"],
                "a_pct": pct_a,
                "b_pct": pct_b,
                "delta": (
                    round(pct_b - pct_a, 2)
                    if pct_a is not None and pct_b is not None
                    else None
                ),
                "a_last": ra["last"] if ra else None,
                "b_last": rb["last"] if rb else None,
            }
        )
    out.sort(key=lambda r: (r["delta"] is None, -(r["delta"] or 0)))
    return out


# ---------------------------------------------------------------------------
# Provenance / freshness / audit
# ---------------------------------------------------------------------------


def provenance(con):
    """Where the data came from: one row per (source, method) with counts."""
    rows = con.execute(
        "SELECT p.source AS source, p.method AS method, COUNT(*) AS points, "
        "       MIN(p.date) AS first_date, MAX(p.date) AS last_date, "
        "       MAX(p.collected_at) AS last_collected "
        "FROM prices p WHERE p.status = ? "
        "GROUP BY p.source, p.method ORDER BY points DESC",
        (db.STATUS_APPROVED,),
    ).fetchall()
    out = [dict(r) for r in rows]
    con.close()
    return out


def ingestions(con, limit: int = 12):
    """The ingestion audit log, newest first (data lineage)."""
    rows = con.execute(
        "SELECT * FROM ingestions ORDER BY id DESC LIMIT ?", (int(limit),)
    ).fetchall()
    out = [dict(r) for r in rows]
    con.close()
    return out


def status_snapshot(con) -> dict:
    """Coverage, counts, freshness and quality flags for the status page."""
    from datetime import date

    items = all_items(con)
    counts = {
        r["status"]: r["c"]
        for r in con.execute(
            "SELECT status, COUNT(*) AS c FROM prices GROUP BY status"
        ).fetchall()
    }
    row = con.execute(
        "SELECT MIN(date) AS first_date, MAX(date) AS last_date, "
        "       COUNT(*) AS points, COUNT(DISTINCT date) AS weeks "
        "FROM prices WHERE status = ?",
        (db.STATUS_APPROVED,),
    ).fetchone()
    latest_collected = con.execute(
        "SELECT MAX(collected_at) AS c FROM prices WHERE status = ?",
        (db.STATUS_APPROVED,),
    ).fetchone()["c"]
    con.close()

    last_date = row["last_date"] or ""
    age_days = None
    if last_date:
        age_days = (date.today() - date.fromisoformat(last_date)).days
    return {
        "items": len(items),
        "approved_points": row["points"] or 0,
        "weeks": row["weeks"] or 0,
        "first_date": row["first_date"],
        "last_date": last_date,
        "latest_collected": latest_collected,
        "age_days": age_days,
        "freshness": freshness_label(age_days),
        "pending_points": counts.get(db.STATUS_PENDING, 0),
        "rejected_points": counts.get(db.STATUS_REJECTED, 0),
        "by_status": counts,
        "categories": sorted({i["category"] for i in items}),
    }


def freshness_label(age_days, stale_after: int = 30) -> str:
    """Honest wording for the "data updated" badge (never overstates trust)."""
    if age_days is None:
        return "No approved data"
    if age_days <= 7:
        return "Current"
    if age_days <= stale_after:
        return f"{age_days} days old"
    return f"Stale ({age_days} days)"
