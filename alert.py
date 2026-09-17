"""
alert.py
--------
Simple alerting: flag any week where an item's price jumps by more than a
threshold percentage vs the previous week's observation.

A threshold of 5.0 means "a jump of 5% or more in one week". Fresh produce
(onions, potatoes) will naturally trip this more often because they are
volatile — that is exactly the kind of signal a price tracker should surface.
"""

from __future__ import annotations

import db


def compute_alerts(con, threshold: float = 5.0, clear: bool = True):
    """(Re)build the alerts table for the most recent week of every item.

    If ``clear`` is True (default) the table is wiped first, so the alert
    set always reflects the latest data. Returns the number of alerts.
    """
    if clear:
        con.execute("DELETE FROM alerts")

    rows = con.execute(
        """
        WITH ranked AS (
            SELECT id, item_id, date, price,
                   LAG(price) OVER (PARTITION BY item_id ORDER BY date) AS prev
            FROM prices
            WHERE status = ?
        ),
        latest AS (
            SELECT * FROM (
                SELECT *, ROW_NUMBER() OVER (PARTITION BY item_id ORDER BY date DESC) rn
                FROM ranked
            ) WHERE rn = 1
        )
        SELECT item_id, date, price, prev,
               ROUND((price - prev) * 100.0 / prev, 2) AS pct
        FROM latest
        WHERE prev IS NOT NULL AND (price - prev) * 100.0 / prev >= ?
        """,
        (db.STATUS_APPROVED, threshold),
    ).fetchall()

    bulk = [(r["item_id"], r["date"], r["price"], r["prev"], r["pct"], threshold) for r in rows]
    con.executemany(
        "INSERT INTO alerts (item_id, date, price, prev_price, pct_change, threshold) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        bulk,
    )
    con.commit()
    return len(bulk)


def latest_alerts(con, threshold: float = 5.0, start: str = None, end: str = None):
    compute_alerts(con, threshold=threshold)
    q = (
        "SELECT i.name, i.category, d.date, d.price, d.prev_price, "
        "       ROUND(d.pct_change,1) AS pct "
        "FROM alerts d JOIN items i ON i.id = d.item_id"
    )
    cond, params = [], []
    if start:
        cond.append("d.date >= ?")
        params.append(start)
    if end:
        cond.append("d.date <= ?")
        params.append(end)
    if cond:
        q += " WHERE " + " AND ".join(cond)
    q += " ORDER BY d.pct_change DESC"
    return con.execute(q, params).fetchall()
