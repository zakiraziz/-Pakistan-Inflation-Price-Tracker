"""
seed.py
-------
Reproducibly load the price basket into SQLite.

Usage:
    python seed.py            # rebuild the DB from scratch (idempotent)
    python seed.py --dry-run  # print the first/last rows without writing

This is the "ingest" step of the data pipeline: it takes the deterministic
source (model.py) and writes the time-series into the database.
"""
from __future__ import annotations

import sys

import db
import model


def load(con):
    con.executescript("""
        DROP TABLE IF EXISTS alerts;
        DROP TABLE IF EXISTS prices;
        DROP TABLE IF EXISTS items;
    """)
    db.init_db()  # recreate schema (uses default DB_PATH)

    # insert items
    for row_id, (name, category, unit, *_) in enumerate(model.ITEMS, start=1):
        con.execute(
            "INSERT INTO items (id, name, category, unit) VALUES (?, ?, ?, ?)",
            (row_id, name, category, unit),
        )

    # insert weekly prices
    bulk = []
    for item_id, item in enumerate(model.ITEMS, start=1):
        for day in model.weekly_dates():
            bulk.append((item_id, day.isoformat(), model.price_at(day, item)))

    con.executemany(
        "INSERT INTO prices (item_id, date, price) VALUES (?, ?, ?)", bulk
    )
    con.commit()
    return len(bulk)


def show(con, n=3):
    print("--- items ---")
    for r in db.get_items(con):
        print(f"  #{r['id']} {r['name']} ({r['category']}) {r['unit']}")

    print("--- sample of wheat flour series ---")
    rows = con.execute(
        "SELECT p.date, p.price FROM prices p "
        "JOIN items i ON i.id = p.item_id "
        "WHERE i.name = ? ORDER BY p.date LIMIT ?",
        ("Wheat flour (atta)", n),
    ).fetchall()
    first = con.execute(
        "SELECT date, price FROM prices ORDER BY date LIMIT 1"
    ).fetchone()
    last = con.execute(
        "SELECT date, price FROM prices ORDER BY date DESC LIMIT 1"
    ).fetchone()
    for r in rows:
        print(f"    {r['date']}  Rs {r['price']:>8.2f}")
    print(f"  range: {first['date']} -> {last['date']}")


if __name__ == "__main__":
    con = db.connect()
    if "--dry-run" in sys.argv:
        print("(dry run) first 5 rows per model:")
        for it in model.ITEMS[:5]:
            print("  ", it[0], model.price_at(model.START_DATE, it))
        sys.exit(0)
    n = load(con)
    show(con)
    print(f"loaded {n} price rows -> {db.DB_PATH}")
    con.close()