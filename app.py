"""
app.py
------
Flask API + dashboard for the Pakistan Inflation / Price Tracker.

Endpoints
---------
GET  /                 -> dashboard (static/index.html)
GET  /api/items        -> list of tracked items
GET  /api/series?start=&end=&items=  -> filtered time-series
GET  /api/alerts?threshold= -> latest price-jump alerts
POST /ingest/next      -> run the ingest job (adds next week + recomputes alerts)

Run locally:
    python app.py
then open  http://127.0.0.1:5010
"""
from __future__ import annotations

import os
import time

from flask import Flask, jsonify, make_response, render_template_string, request

import db
import log
from alert import latest_alerts
from core.config import settings
from core.security import install

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config["FORCE_HTTPS"] = settings.force_https

# --- caching (flask-caching; CACHE_TYPE=RedisCache to move to Redis) --------
from flask_caching import Cache

app.config["CACHE_TYPE"] = settings.cache_type
app.config["CACHE_DEFAULT_TIMEOUT"] = settings.cache_ttl
if settings.redis_url:
    app.config.setdefault("CACHE_REDIS_URL", settings.redis_url)
cache = Cache(app)

# --- rate limiting (Flask-Limiter) ------------------------------------------
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(get_remote_address, app=app,
                  default_limits=[settings.rate_limit_default],
                  storage_uri=settings.rate_limit_storage)
write_limit = settings.rate_limit_write

install(app)          # security headers + structured error handling
logger = log.get_logger("app")

DEFAULT_START = "2025-07-01"
STARTED_AT = time.time()


def asset_version():
    """Cache-busting build id: newest mtime of the front-end assets.

    app.js / helpers.js / style.css are served with a ?v=<id> stamp so a browser
    can never keep running an old bundle against new markup (which silently
    breaks the dashboard: listeners wired but nothing renders).
    """
    newest = 0.0
    for name in ("app.js", "helpers.js", "style.css"):
        try:
            newest = max(newest, os.path.getmtime(os.path.join(BASE_DIR, "static", name)))
        except OSError:  # pragma: no cover - asset always shipped
            pass
    return str(int(newest))


ASSET_VERSION = asset_version()


@app.route("/readyz")
def readyz():
    """Readiness: the app can serve data (schema present, has approved rows)."""
    try:
        con = db.connect()
        con.execute("SELECT 1 FROM sqlite_master LIMIT 1")
        approved = con.execute("SELECT COUNT(*) AS c FROM prices "
                               "WHERE status = ?", (db.STATUS_APPROVED,)).fetchone()["c"]
        con.close()
        ready = approved > 0
        return jsonify({"status": "ready" if ready else "not_ready",
                        "approved_points": approved}), (200 if ready else 503)
    except Exception as exc:  # pragma: no cover - defensive
        return jsonify({"status": "not_ready", "error": str(exc)}), 503


@app.route("/healthz")
def healthz():
    ok, detail = True, {}
    try:
        con = db.connect()
        detail["items"] = len(db.get_items(con))
        row = con.execute("SELECT MAX(date) AS d, COUNT(*) AS c FROM prices "
                          "WHERE status = ?", (db.STATUS_APPROVED,)).fetchone()
        detail["latest_date"] = row["d"]
        detail["approved_points"] = row["c"]
        detail["pending_points"] = db.count_status(con, db.STATUS_PENDING)
        con.close()
    except Exception as exc:  # pragma: no cover - defensive
        ok, detail["error"] = False, str(exc)
    detail["uptime_seconds"] = round(time.time() - STARTED_AT, 1)
    return jsonify({"status": "ok" if ok else "degraded", **detail}), (200 if ok else 503)


@app.route("/")
def index():
    """Dashboard shell, stamped with the asset build id (see asset_version)."""
    with open(os.path.join(BASE_DIR, "static", "index.html"), encoding="utf-8") as f:
        html = f.read()
    resp = make_response(render_template_string(html, v=ASSET_VERSION))
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/methodology")
def methodology():
    """Render the index methodology (source: docs/methodology.md)."""
    with open(os.path.join(BASE_DIR, "static", "methodology.html"),
              encoding="utf-8") as f:
        return render_template_string(f.read())


@app.route("/api/items")
@cache.cached(query_string=True)
def api_items():
    con = db.connect()
    rows = db.get_items(con)
    con.close()
    return jsonify(
        [{"id": r["id"], "name": r["name"], "category": r["category"],
          "unit": r["unit"]} for r in rows]
    )


def _parse_window():
    start = request.args.get("start", DEFAULT_START) or ""
    end = request.args.get("end") or ""
    items_arg = request.args.get("items", "")
    ids = None
    if items_arg.strip():
        ids = [int(x) for x in items_arg.split(",") if x.strip().isdigit()]
    return start, end, ids


def _series_between(start, end, ids, status=db.STATUS_APPROVED):
    con = db.connect()
    if ids is None:
        ids = [r["id"] for r in db.get_items(con)]
    ph = ",".join("?" * len(ids))
    q = ("SELECT i.name AS name, p.date AS date, p.price AS price "
         "FROM prices p JOIN items i ON i.id = p.item_id "
         "WHERE p.status = ? AND p.item_id IN ({})".format(ph))
    params = [status, *ids]
    if start:
        q += " AND p.date >= ?"
        params.append(start)
    if end:
        q += " AND p.date <= ?"
        params.append(end)
    q += " ORDER BY p.date"
    rows = con.execute(q, params).fetchall()
    con.close()
    return rows


@app.route("/api/series")
@cache.cached(query_string=True)
def api_series():
    start, end, ids = _parse_window()
    rows = _series_between(start, end, ids)
    return jsonify(
        [{"name": r["name"], "date": r["date"], "price": r["price"]} for r in rows]
    )


@app.route("/api/index")
@cache.cached(query_string=True)
def api_index():
    """Equal-weight basket cost index, normalised to 100 on the window start."""
    start, end, ids = _parse_window()
    rows = _series_between(start, end, ids)
    sums = {}
    for r in rows:
        sums[r["date"]] = sums.get(r["date"], 0.0) + r["price"]
    dates = sorted(sums)
    if not dates:
        return jsonify([])
    base = sums[dates[0]]
    return jsonify(
        [{"date": d, "index": round(sums[d] / base * 100, 2)} for d in dates]
    )


@app.route("/api/metrics")
@cache.cached(query_string=True)
def api_metrics():
    """Summary stats for the selected window (drives the dashboard cards)."""
    start, end, ids = _parse_window()
    rows = _series_between(start, end, ids)
    if not rows:
        return jsonify({"count": 0, "weeks": 0})
    by = {}
    for r in rows:
        by.setdefault(r["name"], []).append(r["price"])
    names = list(by)
    first_tot = sum(v[0] for v in by.values())
    last_tot = sum(v[-1] for v in by.values())
    basket_pct = (last_tot - first_tot) / first_tot * 100 if first_tot else 0.0

    stats = []
    for name, pxs in by.items():
        if len(pxs) >= 2:
            stats.append((name, (pxs[-1] - pxs[0]) / pxs[0] * 100))
    riser = max(stats, key=lambda t: t[1]) if stats else None
    faller = min(stats, key=lambda t: t[1]) if stats else None
    dates = sorted({r["date"] for r in rows})
    return jsonify({
        "count": len(names),
        "weeks": len(dates),
        "first_date": dates[0],
        "last_date": dates[-1],
        "basket_pct": round(basket_pct, 2),
        "start_total": round(first_tot, 2),
        "end_total": round(last_tot, 2),
        "biggest_riser": {"name": riser[0], "pct": round(riser[1], 2)} if riser else None,
        "biggest_faller": {"name": faller[0], "pct": round(faller[1], 2)} if faller else None,
    })


@app.route("/api/pivot")
@cache.cached(query_string=True)
def api_pivot():
    """Item x date matrix + equal-weight basket index for the window."""
    start, end, ids = _parse_window()
    con = db.connect()
    if ids is None:
        ids = [r["id"] for r in db.get_items(con)]
    ph = ",".join("?" * len(ids))
    q = ("SELECT i.name AS name, i.category AS category, i.unit AS unit, "
         "       p.date AS date, p.price AS price "
         "FROM prices p JOIN items i ON i.id = p.item_id "
         "WHERE p.item_id IN ({})".format(ph))
    params = list(ids)
    if start:
        q += " AND p.date >= ?"; params.append(start)
    if end:
        q += " AND p.date <= ?"; params.append(end)
    q += " ORDER BY p.date"
    rows = con.execute(q, params).fetchall()
    con.close()

    dates, seen, by = [], {}, {}
    for r in rows:
        if r["date"] not in seen:
            seen[r["date"]] = 1
            dates.append(r["date"])
        by.setdefault(r["name"],
                      {"category": r["category"], "unit": r["unit"], "prices": []}
                      )["prices"].append(r["price"])

    items_out = []
    for name, d in by.items():
        px = d["prices"]
        first, last = px[0], px[-1]
        items_out.append({
            "name": name, "category": d["category"], "unit": d["unit"],
            "first": first, "last": last,
            "pct": round((last - first) / first * 100, 2) if first else 0.0,
            "prices": px,
        })

    index = []
    if dates and by:
        total0 = sum(items_out[i]["prices"][0] for i in range(len(items_out)))
        for i in range(len(dates)):
            total = sum(items_out[j]["prices"][i] for j in range(len(items_out)))
            index.append(round(total / total0 * 100, 2))

    return jsonify({"dates": dates, "index": index, "items": items_out})


@app.route("/api/inflation")
@cache.cached(query_string=True)
def api_inflation():
    """Headline inflation stats for the window (annualised, weekly, YoY)."""
    start, end, ids = _parse_window()
    rows = _series_between(start, end, ids)
    if not rows:
        return jsonify({"weeks": 0})
    sums = {}
    for r in rows:
        sums[r["date"]] = sums.get(r["date"], 0.0) + r["price"]
    dates = sorted(sums)
    base = sums[dates[0]]
    last_tot = sums[dates[-1]]
    basket_pct = (last_tot - base) / base * 100
    days = (len(dates) - 1) * 7
    annualized = ((last_tot / base) ** (365.0 / days) - 1) * 100 if days > 0 else 0.0
    avg_weekly = ((last_tot / base) ** (1.0 / max(1, len(dates) - 1)) - 1) * 100

    from datetime import date as _date, timedelta
    last_d = _date.fromisoformat(dates[-1])
    target = last_d - timedelta(days=364)
    yoy = None
    for dt in dates:
        if _date.fromisoformat(dt) >= target:
            yoy = (last_tot / sums[dt] - 1) * 100
            break
    return jsonify({
        "weeks": len(dates),
        "first_date": dates[0],
        "last_date": dates[-1],
        "basket_pct": round(basket_pct, 2),
        "annualized_pct": round(annualized, 2),
        "avg_weekly_pct": round(avg_weekly, 2),
        "yoy_pct": round(yoy, 2) if yoy is not None else None,
    })


@app.route("/api/series.csv")
def api_series_csv():
    """Download the current view as CSV."""
    import csv as _csv
    import io

    from flask import Response

    start, end, ids = _parse_window()
    rows = _series_between(start, end, ids)
    buf = io.StringIO()
    writer = _csv.writer(buf)
    writer.writerow(["item", "date", "price"])
    for r in rows:
        writer.writerow([r["name"], r["date"], r["price"]])
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=prices.csv"},
    )


@app.route("/api/alerts")
@cache.cached(query_string=True)
def api_alerts():
    start, end, _ = _parse_window()
    threshold = float(request.args.get("threshold", 5.0))
    con = db.connect()
    rows = latest_alerts(con, threshold=threshold, start=start, end=end)
    con.close()
    return jsonify(
        [{"name": r["name"], "category": r["category"], "date": r["date"],
          "price": r["price"], "prev_price": r["prev_price"],
          "pct": r["pct"]} for r in rows]
    )


@app.route("/ingest/next", methods=["POST"])
@limiter.limit(write_limit)
def run_job():
    import job
    from datetime import date
    con = db.connect()
    when = date.today()
    if request.is_json and request.get_json(silent=True).get("date"):
        when = date.fromisoformat(request.get_json()["date"])
    auto_approve = request.get_json(silent=True) is None or \
        bool(request.get_json(silent=True).get("auto_approve", True))
    n, snap, counts = job.add_next_week(con, when, auto_approve=auto_approve)
    con.close()
    cache.clear()          # data changed -> invalidate cached API responses
    logger.info("ingest run: %s", counts)
    return jsonify({"inserted": n, "for_week": snap.isoformat(), "counts": counts})


@app.route("/api/admin/pending")
def admin_pending():
    con = db.connect()
    rows = db.pending_points(con)
    con.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/admin/approve", methods=["POST"])
@limiter.limit(write_limit)
def admin_approve():
    """Approve pending price points: {"ids": [..]} or {"all": true}."""
    payload = request.get_json(silent=True) or {}
    con = db.connect()
    if payload.get("all"):
        n = con.execute("UPDATE prices SET status = ?, review_note = 'approved "
                        "by admin' WHERE status = ?",
                        (db.STATUS_APPROVED, db.STATUS_PENDING)).rowcount
    else:
        ids = [int(x) for x in payload.get("ids", []) if str(x).isdigit()]
        n = 0
        for pid in ids:
            n += con.execute("UPDATE prices SET status = ?, "
                             "review_note = 'approved by admin' "
                             "WHERE id = ? AND status = ?",
                             (db.STATUS_APPROVED, pid, db.STATUS_PENDING)).rowcount
    con.commit()
    con.close()
    cache.clear()
    logger.info("approved %s pending point(s)", n)
    return jsonify({"approved": n})


@app.route("/api/admin/reject", methods=["POST"])
@limiter.limit(write_limit)
def admin_reject():
    """Reject pending price points so they never enter the index."""
    payload = request.get_json(silent=True) or {}
    con = db.connect()
    if payload.get("all"):
        n = con.execute("UPDATE prices SET status = ?, review_note = 'rejected "
                        "by admin' WHERE status = ?",
                        (db.STATUS_REJECTED, db.STATUS_PENDING)).rowcount
    else:
        ids = [int(x) for x in payload.get("ids", []) if str(x).isdigit()]
        n = 0
        for pid in ids:
            n += con.execute("UPDATE prices SET status = ?, "
                             "review_note = 'rejected by admin' "
                             "WHERE id = ? AND status = ?",
                             (db.STATUS_REJECTED, pid, db.STATUS_PENDING)).rowcount
    con.commit()
    con.close()
    cache.clear()
    logger.info("rejected %s pending point(s)", n)
    return jsonify({"rejected": n})


if __name__ == "__main__":
    # Debug mode is opt-in (FLASK_DEBUG=1); never on by default.
    app.run(host="0.0.0.0", port=settings.port,
            debug=os.environ.get("FLASK_DEBUG") == "1")