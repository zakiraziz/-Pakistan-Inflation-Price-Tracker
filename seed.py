"""
seed.py
-------
Reproducibly load the price basket into SQLite with full provenance.

Usage:
    python seed.py            # rebuild the DB from scratch (idempotent)
    python seed.py --dry-run  # print the first rows without writing

This is the "ingest" step of the data pipeline: it reads the deterministic
source (model.py), validates/records provenance, and writes an approved
baseline into the database.
"""
from __future__ import annotations

import sys

import db
import model
from ingest.sources import SeedSource
from ingest.pipeline import ingest


def load(con):
    con.executescript("""
        DROP TABLE IF EXISTS ingestions;
        DROP TABLE IF EXISTS alerts;
        DROP TABLE IF EXISTS prices;
        DROP TABLE IF EXISTS items;
    """)
    db.init_db()

    # insert items
    for row_id, (name, category, unit, *_) in enumerate(model.ITEMS, start=1):
        con.execute(
            "INSERT INTO items (id, name, category, unit) VALUES (?, ?, ?, ?)",
            (row_id, name, category, unit),
        )

    points = SeedSource().fetch()
    counts = ingest(con, points, source_name="seed", method="generator",
                    auto_approve=True, target_date=model.END_DATE.isoformat())
    return counts


def show(con, n=3):
    print("--- items ---")
    for r in db.get_items(con):
        print(f"  #{r['id']} {r['name']} ({r['category']}) {r['unit']}")

    print("--- sample of wheat flour series ---")
    rows = con.execute(
        "SELECT p.date, p.price, p.status FROM prices p "
        "JOIN items i ON i.id = p.item_id "
        "WHERE i.name = ? ORDER BY p.date LIMIT ?",
        ("Wheat flour (atta)", n),
    ).fetchall()
    first = con.execute("SELECT date FROM prices ORDER BY date LIMIT 1").fetchone()
    last = con.execute("SELECT date FROM prices ORDER BY date DESC LIMIT 1").fetchone()
    for r in rows:
        print(f"    {r['date']}  Rs {r['price']:>8.2f}  [{r['status']}]")
    print(f"  range: {first['date']} -> {last['date']}")


if __name__ == "__main__":
    con = db.connect()
    if "--dry-run" in sys.argv:
        for it in model.ITEMS[:5]:
            print("  ", it[0], model.price_at(model.START_DATE, it))
        sys.exit(0)
    counts = load(con)
    show(con)
    print(f"loaded {db.count_status(con, db.STATUS_APPROVED)} approved price rows "
          f"({counts['total']} total) -> {db.DB_PATH}")
    con.close()