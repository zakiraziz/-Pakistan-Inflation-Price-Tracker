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

from flask import Flask, jsonify, render_template_string, request

import db
from alert import latest_alerts

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder="static", static_url_path="/static")

DEFAULT_START = "2025-07-01"


@app.route("/")
def index():
    with open(os.path.join(BASE_DIR, "static", "index.html"), encoding="utf-8") as f:
        return render_template_string(f.read())


@app.route("/api/items")
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


def _series_between(start, end, ids):
    con = db.connect()
    if ids is None:
        ids = [r["id"] for r in db.get_items(con)]
    ph = ",".join("?" * len(ids))
    q = ("SELECT i.name AS name, p.date AS date, p.price AS price "
         "FROM prices p JOIN items i ON i.id = p.item_id "
         "WHERE p.item_id IN ({})".format(ph))
    params = list(ids)
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
def api_series():
    start, end, ids = _parse_window()
    rows = _series_between(start, end, ids)
    return jsonify(
        [{"name": r["name"], "date": r["date"], "price": r["price"]} for r in rows]
    )


@app.route("/api/index")
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
def run_job():
    import job
    import model
    from datetime import date
    con = db.connect()
    when = date.today()
    if request.is_json and request.get_json(silent=True).get("date"):
        when = date.fromisoformat(request.get_json()["date"])
    n, snap = job.add_next_week(con, when)
    con.close()
    return jsonify({"inserted": n, "for_week": snap.isoformat()})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5010, debug=True)