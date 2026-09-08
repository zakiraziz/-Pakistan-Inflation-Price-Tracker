"""
pipeline.py
-----------
The ingestion pipeline: take fetched points, validate them, stage them with
full provenance, and only commit (auto-approve) the ones that pass automated
checks. Everything else is held *pending* so bad scrapes never reach the index.

Pipeline steps:
    fetch (a Source) -> validate (validators.classify) -> insert with
    provenance -> audit (ingestions table).
"""
from __future__ import annotations

from datetime import datetime, timezone

import db
from validators import classify

STATUS_COUNTS = (db.STATUS_APPROVED, db.STATUS_PENDING, db.STATUS_REJECTED)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def latest_approved_before(con, item_id: int, date: str):
    return con.execute(
        "SELECT price FROM prices WHERE item_id = ? AND status = ? AND date < ? "
        "ORDER BY date DESC LIMIT 1",
        (item_id, db.STATUS_APPROVED, date),
    ).fetchone()


def ingest(con, points, source_name: str, method: str = "",
           auto_approve: bool = True, target_date: str = None) -> dict:
    """Insert a batch of points with validation + provenance.

    Returns counts: {"total","approved","pending","rejected","skipped"}.
    Idempotent: a point already present for an item+date is skipped.
    """
    counts = {"total": 0, db.STATUS_APPROVED: 0, db.STATUS_PENDING: 0,
              db.STATUS_REJECTED: 0, "skipped": 0}
    item_map = db.get_item_map(con)
    now = _utc_now()

    for pt in points:
        counts["total"] += 1
        item = item_map.get(pt.get("item"))
        if item is None:
            counts[db.STATUS_REJECTED] += 1
            continue
        if con.execute(
            "SELECT 1 FROM prices WHERE item_id = ? AND date = ?",
            (item["id"], pt.get("date")),
        ).fetchone():
            counts["skipped"] += 1
            continue

        prev = latest_approved_before(con, item["id"], pt.get("date"))
        status, note = classify(item["category"], pt.get("price"),
                                prev["price"] if prev else None)
        if status == db.STATUS_APPROVED and not auto_approve:
            status, note = db.STATUS_PENDING, "held for manual review"

        con.execute(
            "INSERT INTO prices "
            "(item_id, date, price, source, method, collected_at, status, review_note) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (item["id"], pt.get("date"), pt.get("price"), source_name,
             method or pt.get("method", ""), now, status, note),
        )
        counts[status] += 1

    con.commit()
    db.record_ingestion(con, source_name, method or "auto", target_date, counts)
    con.commit()
    return counts