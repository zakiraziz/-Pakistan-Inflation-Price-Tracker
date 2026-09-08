"""
job.py
------
The "job that adds new data over time".

Each run computes and inserts the *next* weekly data point for every item —
either the first week after the last stored date, or for the current week if
the scheduler has fallen behind. It is safe to run on a schedule (cron /
Task Scheduler / GitHub Actions) because it is idempotent.

Usage:
    python job.py [--date YYYY-MM-DD] [--threshold 5]

After inserting new data it recomputes jump alerts and prints them.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta

import db
import model
from alert import compute_alerts
from ingest.pipeline import ingest


def add_next_week(con, when: date, threshold: float = 5.0,
                  auto_approve: bool = True):
    """Ingest one weekly observation per item for the week containing `when`.

    Points flow through the validated ingestion pipeline (provenance +
    approval). Returns (inserted, snaps_tart, counts). Snaps `when` to the same
    7-day grid used by the seed so dates stay aligned. Idempotent.
    """
    days_since_start = (when - model.START_DATE).days
    snap_days = max(0, (days_since_start // model.WEEK) * model.WEEK)
    snap = model.START_DATE + timedelta(days=snap_days)
    iso = snap.isoformat()

    points = [{"item": item[0], "date": iso,
               "price": model.price_at(snap, item), "method": "generator"}
              for item in model.ITEMS]

    counts = ingest(con, points, source_name="weekly-job", method="generator",
                    auto_approve=auto_approve, target_date=iso)
    inserted = counts["approved"] + counts["pending"]

    # recompute alerts over approved data for this new week
    compute_alerts(con, threshold=threshold)
    return inserted, snap, counts


if __name__ == "__main__":
    con = db.init_db()
    when = date.today()
    threshold = 5.0
    auto_approve = True
    args = sys.argv[1:]
    if "--date" in args:
        when = date.fromisoformat(args[args.index("--date") + 1])
    if "--threshold" in args:
        threshold = float(args[args.index("--threshold") + 1])
    if "--manual" in args:
        auto_approve = False

    n, snap, counts = add_next_week(con, when, threshold, auto_approve)
    if n:
        print(f"[job] inserted {n} rows for week of {snap.isoformat()} "
              f"(snapped from {when.isoformat()})  {counts}")
    else:
        print(f"[job] week of {snap.isoformat()} already present; nothing to do")

    rows = con.execute(
        "SELECT i.name, d.date, d.price, "
        "       d.prev_price, ROUND(d.pct_change,1) AS pct "
        "FROM alerts d JOIN items i ON i.id = d.item_id ORDER BY d.pct_change DESC"
    ).fetchall()
    if rows:
        print("[job] alerts raised:")
        for r in rows:
            print(f"  {r['name']:<22} {r['date']} Rs {r['price']:>8.2f} "
                  f"(+{r['pct']}% vs prev {r['prev_price']:>7.2f})")
    else:
        print("[job] no alerts above threshold")
    pending = db.count_status(con, db.STATUS_PENDING)
    if pending:
        print(f"[job] NOTE: {pending} point(s) held pending for approval.")
    con.close()