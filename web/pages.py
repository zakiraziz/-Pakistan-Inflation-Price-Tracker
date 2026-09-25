"""
web/pages.py
------------
Server-rendered pages: items index, item drill-down, compare, insights, alerts,
data, status, API reference and the admin review queue.

Rendering on the server (rather than shipping an empty shell and filling it with
JavaScript) means every page has content in the first response: it works with
JS disabled, it is printable, and it cannot be left blank by a blocked CDN.

The JSON API lives in ``app.py``; this module is the human-facing surface.
"""

from __future__ import annotations

import contextlib
import os
from datetime import date, timedelta

from flask import (
    Blueprint,
    abort,
    current_app,
    redirect,
    render_template,
    request,
    url_for,
)

import db
import log
import services.insights as insights
import services.openapi as openapi
import services.readmodels as rm
from web import svg

bp = Blueprint("pages", __name__)
logger = log.get_logger("pages")

DEFAULT_DAYS = 180
NAV = [
    ("/", "Dashboard"),
    ("/items", "Items"),
    ("/compare", "Compare"),
    ("/insights", "Insights"),
    ("/alerts", "Alerts"),
    ("/data", "Data"),
    ("/status", "Status"),
    ("/docs", "API"),
]


def _int_arg(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(request.args.get(name, default))
    except (TypeError, ValueError):
        return default
    return max(low, min(high, value))


def _float_arg(name: str, default: float, low: float, high: float) -> float:
    try:
        value = float(request.args.get(name, default))
    except (TypeError, ValueError):
        return default
    return max(low, min(high, value))


def _window(days: int = DEFAULT_DAYS) -> dict:
    """Requested window, defaulting to the last ``days`` of data."""
    end = (request.args.get("end") or "").strip()
    start = (request.args.get("start") or "").strip()
    if not start:
        con = db.connect()
        row = con.execute(
            "SELECT MAX(date) AS d FROM prices WHERE status = ?",
            (db.STATUS_APPROVED,),
        ).fetchone()
        con.close()
        latest = row["d"] if row and row["d"] else date.today().isoformat()
        start = (date.fromisoformat(latest) - timedelta(days=days)).isoformat()
    return {"start": start, "end": end, "days": days}


def _common(title: str, subtitle: str = "", **extra) -> dict:
    """Context every page needs: nav, freshness banner, shell metadata."""
    con = db.connect()
    status = rm.status_snapshot(con)  # closes the connection
    ctx = {
        "title": title,
        "subtitle": subtitle,
        "nav": NAV,
        "asset_v": current_app.config.get("ASSET_VERSION", "0"),
        "status": status,
        "today": date.today().isoformat(),
        "api_version": openapi.API_VERSION,
    }
    ctx.update(extra)
    return ctx


def _dated_window() -> dict:
    """Window resolved to concrete dates (falls back to the whole dataset)."""
    window = _window()
    con = db.connect()
    row = con.execute(
        "SELECT MIN(date) AS a, MAX(date) AS b FROM prices WHERE status = ?",
        (db.STATUS_APPROVED,),
    ).fetchone()
    con.close()
    start = window["start"] or (row["a"] if row else "")
    end = window["end"] or (row["b"] if row else "")
    return {"start": start, "end": end}


# ---------------------------------------------------------------------------
# Items index + drill-down
# ---------------------------------------------------------------------------


@bp.route("/items")
def items_index():
    """Every tracked item: change, trend, volatility, sparkline, drill-down link."""
    window = _dated_window()
    threshold = _float_arg("threshold", 5.0, 0.1, 100.0)
    views = rm.item_views(db.connect(), window["start"], window["end"])
    summary = rm.basket_summary(views)
    risers, fallers = rm.top_movers(views, 5)
    cards = [
        {"name": v["name"], "slug": v["slug"], "values": v["series"],
         "color": svg.color_for(i)}
        for i, v in enumerate(views)
    ]
    return render_template(
        "items.html",
        **_common(
            "Items",
            f"{summary['count']} items · {summary['weeks']} weekly observations",
            window=window,
            views=views,
            summary=summary,
            risers=risers,
            fallers=fallers,
            sprites={c["slug"]: svg.sparkline(c["values"], color=c["color"]) for c in cards},
            threshold=threshold,
        ),
    )


@bp.route("/item/<slug>")
def item_detail(slug: str):
    """One item: history chart, statistics, basket contribution, provenance."""
    con = db.connect()
    item = rm.item_by_slug(con, slug)
    if not item:
        con.close()
        abort(404)
    window = _dated_window()
    history = rm.series_of(con, item["id"], window["start"], window["end"])
    if not history:
        all_history = rm.series_of(db.connect(), item["id"])
        return render_template(
            "item.html",
            **_common(
                item["name"],
                "No approved observations in the selected window",
                item=item,
                window=window,
                history=[],
                chart_html=svg.chart([], []),
                stats=None,
                insight=None,
                provenance=[],
                related=[],
                available_from=all_history[0]["date"] if all_history else "",
            ),
        )

    prices = [row["price"] for row in history]
    dates = [row["date"] for row in history]
    stats = rm.stats(prices)
    views = rm.item_views(db.connect(), window["start"], window["end"])
    mine = next((v for v in views if v["slug"] == slug), None)
    if mine:
        stats["contribution_pct"] = mine["contribution_pct"]
    detail = insights.for_item(db.connect(), item, window["start"], window["end"])

    provenance: dict = {}
    for row in history:
        key = (row["source"], row["method"])
        entry = provenance.setdefault(
            key, {"source": row["source"], "method": row["method"], "points": 0,
                  "first": row["date"], "last": row["date"],
                  "collected": row["collected_at"]}
        )
        entry["points"] += 1
        entry["first"] = min(entry["first"], row["date"])
        entry["last"] = max(entry["last"], row["date"])
        entry["collected"] = max(entry["collected"], row["collected_at"])

    con = db.connect()
    related = [
        i for i in rm.all_items(con) if i["category"] == item["category"] and i["id"] != item["id"]
    ]
    con.close()
    return render_template(
        "item.html",
        **_common(
            item["name"],
            f"{item['category']} · {item['unit']}",
            item=item,
            window=window,
            history=history,
            stats=stats,
            chart_html=svg.chart(
                [{"name": item["name"], "values": prices, "color": svg.color_for(0)}],
                dates,
                label=f"{item['name']} price history",
            ),
            insight=detail,
            provenance=sorted(provenance.values(), key=lambda p: -p["points"]),
            related=related,
        ),
    )


# ---------------------------------------------------------------------------
# Compare
# ---------------------------------------------------------------------------


def _default_periods() -> tuple:
    """Two equal, non-overlapping windows ending at the latest observation."""
    con = db.connect()
    row = con.execute(
        "SELECT MAX(date) AS d FROM prices WHERE status = ?",
        (db.STATUS_APPROVED,),
    ).fetchone()
    con.close()
    latest = date.fromisoformat(row["d"]) if row and row["d"] else date.today()
    b_end = latest
    b_start = latest - timedelta(days=90)
    a_end = b_start - timedelta(days=7)
    a_start = a_end - timedelta(days=90)
    return (
        {"start": a_start.isoformat(), "end": a_end.isoformat()},
        {"start": b_start.isoformat(), "end": b_end.isoformat()},
    )


@bp.route("/compare")
def compare():
    """Compare the same items across two periods (or two subsets of items)."""
    default_a, default_b = _default_periods()
    a = {
        "start": request.args.get("a_start") or default_a["start"],
        "end": request.args.get("a_end") or default_a["end"],
    }
    b = {
        "start": request.args.get("b_start") or default_b["start"],
        "end": request.args.get("b_end") or default_b["end"],
    }
    con = db.connect()
    items = rm.all_items(con)
    slugs = [s for s in (request.args.get("items") or "").split(",") if s.strip()]
    ids = rm.ids_for_slugs(con, slugs) if slugs else None
    con.close()

    rows = rm.compare_windows(a, b, ids)
    chart_rows = [
        (r["name"], r["delta"], svg.change_color(r["delta"]))
        for r in rows
        if r["delta"] is not None
    ][:14]

    # Overlay the basket index of both windows so the shapes can be compared.
    series = []
    dates = []
    for label, win, color in (("Period A", a, svg.color_for(0)),
                              ("Period B", b, svg.color_for(1))):
        points = rm.basket_index(rm.series(db.connect(), win["start"], win["end"], ids))
        series.append({"name": label, "values": [p["index"] for p in points],
                       "color": color})
        if len(points) > len(dates):
            dates = [p["date"] for p in points]

    return render_template(
        "compare.html",
        **_common(
            "Compare",
            "The same basket across two periods - accelerating or reversing?",
            a=a,
            b=b,
            rows=rows,
            items=items,
            selected=slugs,
            chart_html=svg.chart(
                series, dates, label="Basket index, period A vs period B",
                y_tick=4,
            ),
            bars_html=svg.bars(
                chart_rows, label="Change between period A and period B "
                "(percentage points)",
            ),
        ),
    )


# ---------------------------------------------------------------------------
# Insights
# ---------------------------------------------------------------------------


@bp.route("/insights")
def insights_page():
    """Rule-based narratives: what changed, by how much, and where to look."""
    window = _dated_window()
    threshold = _float_arg("threshold", 5.0, 0.1, 100.0)
    payload = insights.build(
        db.connect(), window["start"], window["end"], None, threshold
    )
    return render_template(
        "insights.html",
        **_common(
            "Insights",
            "What changed, how much, and where to look next",
            window=window,
            payload=payload,
            threshold=threshold,
        ),
    )


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------


@bp.route("/alerts")
def alerts_page():
    """Every item whose latest weekly move crossed the threshold."""
    window = _dated_window()
    threshold = _float_arg("threshold", 5.0, 0.1, 100.0)
    con = db.connect()
    rows = [
        dict(r)
        for r in con.execute(
            "SELECT i.name, i.category, i.unit, a.date, a.price, a.prev_price, "
            "       ROUND(a.pct_change, 2) AS pct "
            "FROM alerts a JOIN items i ON i.id = a.item_id "
            "ORDER BY a.pct_change DESC"
        ).fetchall()
    ]
    con.close()
    for row in rows:
        row["slug"] = rm.slugify(row["name"])
    return render_template(
        "alerts.html",
        **_common(
            "Alerts",
            f"Movements of {threshold:g}% or more in a single week",
            window=window,
            rows=rows,
            threshold=threshold,
            breaches=[r for r in rows if row_free_threshold(r, threshold)],
        ),
    )


def row_free_threshold(row: dict, threshold: float) -> bool:
    """A row clears the threshold (kept separate so the template stays dumb)."""
    return (row.get("pct") or 0) >= threshold


# ---------------------------------------------------------------------------
# Data explorer
# ---------------------------------------------------------------------------


@bp.route("/data")
def data_page():
    """Freshness, the item x date matrix, bulk exports and data lineage."""
    window = _dated_window()
    rows = rm.series(db.connect(), window["start"], window["end"])
    grouped = rm.group_by_item(rows)
    dates = sorted({r["date"] for r in rows})
    matrix = [
        {
            "name": name,
            "category": bucket["category"],
            "unit": bucket["unit"],
            "slug": rm.slugify(name),
            "by_date": dict(bucket["points"]),
        }
        for name, bucket in sorted(grouped.items())
    ]
    return render_template(
        "data.html",
        **_common(
            "Data",
            "Every approved observation, its provenance and the audit log",
            window=window,
            dates=dates,
            matrix=matrix,
            index=rm.basket_index(rows),
            provenance=rm.provenance(db.connect()),
            ingestions=rm.ingestions(db.connect(), 15),
            monthly=rm.monthly_rollup(rows),
        ),
    )


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


@bp.route("/status")
def status_page():
    """Coverage, approval counts, freshness and the ingestion audit log."""
    return render_template(
        "status.html",
        **_common(
            "Status",
            "Coverage, data quality and pipeline health",
            snapshot=rm.status_snapshot(db.connect()),
            provenance=rm.provenance(db.connect()),
            ingestions=rm.ingestions(db.connect(), 20),
        ),
    )


# ---------------------------------------------------------------------------
# API reference
# ---------------------------------------------------------------------------


@bp.route("/docs")
def docs_page():
    """Human-readable API reference rendered from the OpenAPI catalogue."""
    spec = openapi.document("/")
    return render_template(
        "docs.html",
        **_common(
            "API reference",
            f"OpenAPI {spec['openapi']} · version {openapi.API_VERSION}",
            groups=openapi.grouped(),
            pages=openapi.PAGES,
            spec_paths=sorted(spec["paths"]),
            examples={e["path"]: openapi.curl_example(e) for e in openapi.ENDPOINTS},
        ),
    )


@bp.route("/api/v1/openapi.json")
def openapi_json():
    """The machine-readable contract (same catalogue that renders /docs)."""
    import json

    return current_app.response_class(
        json.dumps(openapi.document(request.url_root), indent=2),
        mimetype="application/json",
    )


# ---------------------------------------------------------------------------
# Admin review queue
# ---------------------------------------------------------------------------


@bp.route("/admin/review")
def review_page():
    """Approve or reject observations that validation held back."""
    return render_template(
        "review.html",
        **_common(
            "Review queue",
            "Bad scrapes are held here so they can never poison the index",
            pending=[dict(r) for r in db.pending_points(db.connect(), 200)],
            snapshot=rm.status_snapshot(db.connect()),
            token_required=bool(os.environ.get("ADMIN_TOKEN", "").strip()),
        ),
    )


def _decide(new_status: str, note: str, ids, apply_all: bool) -> int:
    """Apply an approval/rejection decision and return the number of rows hit."""
    con = db.connect()
    if apply_all:
        count = con.execute(
            "UPDATE prices SET status = ?, review_note = ? WHERE status = ?",
            (new_status, note, db.STATUS_PENDING),
        ).rowcount
    else:
        count = 0
        for pid in ids:
            count += con.execute(
                "UPDATE prices SET status = ?, review_note = ? "
                "WHERE id = ? AND status = ?",
                (new_status, note, pid, db.STATUS_PENDING),
            ).rowcount
    con.commit()
    con.close()
    if count:
        _invalidate()
    logger.info("review: %s %s point(s)", new_status, count)
    return count


@bp.route("/admin/review/approve", methods=["POST"])
def review_approve():
    """Form handler for the review page (guarded by core.auth, like /api/admin)."""
    ids = [int(v) for v in request.form.getlist("ids") if v.isdigit()]
    count = _decide(db.STATUS_APPROVED, "approved from review page", ids,
                    request.form.get("all") == "1")
    return redirect(url_for("pages.review_page", done=f"approved {count}"))


@bp.route("/admin/review/reject", methods=["POST"])
def review_reject():
    """Discard held-back observations so they never enter the index."""
    ids = [int(v) for v in request.form.getlist("ids") if v.isdigit()]
    count = _decide(db.STATUS_REJECTED, "rejected from review page", ids,
                    request.form.get("all") == "1")
    return redirect(url_for("pages.review_page", done=f"rejected {count}"))


def _invalidate() -> None:
    """Drop cached API responses and tell open dashboards the data changed.

    ``app.extensions["cache"]`` is a *mapping of Cache objects to backends*, so
    it must never be cleared directly - clearing it removes the registered
    cache. The app's ``Cache`` instance is imported lazily instead.
    """
    with contextlib.suppress(Exception):
        from app import cache  # local import: app.py imports this module

        cache.clear()
    with contextlib.suppress(Exception):
        from core import live

        live.bump("review decision")
