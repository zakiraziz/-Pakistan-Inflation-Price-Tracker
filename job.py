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


def add_next_week(con, when: date, threshold: float = 5.0) -> int:
    """Insert one weekly observation per item for the week containing `when`.

    Returns the number of rows inserted (0 if the week already exists).
    Snaps `when` to the same weekly cadence used by the seed so dates stay
    aligned (7-day grid starting at START_DATE).
    """
    days_since_start = (when - model.START_DATE).days
    snap_days = max(0, (days_since_start // model.WEEK) * model.WEEK)
    snap = model.START_DATE + timedelta(days=snap_days)
    iso = snap.isoformat()

    existing = con.execute(
        "SELECT COUNT(*) AS c FROM prices WHERE date = ?", (iso,)
    ).fetchone()["c"]
    if existing > 0:
        return 0, snap

    bulk = []
    for item_id, item in enumerate(model.ITEMS, start=1):
        bulk.append((item_id, iso, model.price_at(snap, item)))
    con.executemany(
        "INSERT INTO prices (item_id, date, price) VALUES (?, ?, ?)", bulk
    )
    con.commit()

    # recompute alerts for this new week
    compute_alerts(con, threshold=threshold)
    return len(bulk), snap


if __name__ == "__main__":
    con = db.init_db()
    when = date.today()
    threshold = 5.0
    args = sys.argv[1:]
    if "--date" in args:
        when = date.fromisoformat(args[args.index("--date") + 1])
    if "--threshold" in args:
        threshold = float(args[args.index("--threshold") + 1])

    n, snap = add_next_week(con, when, threshold)
    if n:
        print(f"[job] inserted {n} rows for week of {snap.isoformat()} "
              f"(snapped from {when.isoformat()})")
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
    con.close()