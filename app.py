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


@app.route("/api/series")
def api_series():
    con = db.connect()
    start = request.args.get("start", DEFAULT_START)
    end = request.args.get("end", "")
    items_arg = request.args.get("items", "")

    # which items
    if items_arg.strip():
        ids = [int(x) for x in items_arg.split(",") if x.strip().isdigit()]
    else:
        ids = [r["id"] for r in db.get_items(con)]

    q = ("SELECT i.name AS name, p.date AS date, p.price AS price "
         "FROM prices p JOIN items i ON i.id = p.item_id "
         "WHERE p.item_id IN ({})".format(",".join("?" * len(ids))))
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
    out = [{"name": r["name"], "date": r["date"], "price": r["price"]} for r in rows]
    return jsonify(out)


@app.route("/api/alerts")
def api_alerts():
    con = db.connect()
    threshold = float(request.args.get("threshold", 5.0))
    rows = latest_alerts(con, threshold=threshold)
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