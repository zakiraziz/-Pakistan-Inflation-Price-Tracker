"""
test_pipeline.py
----------------
End-to-end sanity tests for the data pipeline. Uses a throwaway database so
the real one is untouched. Run with:

    python test_pipeline.py

Assertions only (no framework needed) keeps it dependency-free and reproducible.
"""
from __future__ import annotations

import os
import sys
import tempfile

import db
import model


def test_seed_and_query(tmpdir):
    db_path = os.path.join(tmpdir, "test.db")
    con = db.connect(db_path)
    # mirror seed.load() against the temp db
    con.executescript("DROP TABLE IF EXISTS alerts; DROP TABLE IF EXISTS prices; DROP TABLE IF EXISTS items;")
    db.init_db(db_path)

    for idx, it in enumerate(model.ITEMS, start=1):
        con.execute("INSERT INTO items (id, name, category, unit) VALUES (?, ?, ?, ?)",
                    (idx, it[0], it[1], it[2]))
    bulk = []
    for item_id, it in enumerate(model.ITEMS, start=1):
        for day in model.weekly_dates():
            bulk.append((item_id, day.isoformat(), model.price_at(day, it)))
    con.executemany("INSERT INTO prices (item_id, date, price) VALUES (?, ?, ?)", bulk)
    con.commit()

    total = con.execute("SELECT COUNT(*) AS c FROM prices").fetchone()["c"]
    assert total == len(model.ITEMS) * len(list(model.weekly_dates())), f"unexpected row count {total}"

    first = con.execute("SELECT MIN(date) AS d FROM prices").fetchone()["d"]
    last = con.execute("SELECT MAX(date) AS d FROM prices").fetchone()["d"]
    assert first == model.START_DATE.isoformat()
    assert last <= model.END_DATE.isoformat()

    # every price strictly positive
    bad = con.execute("SELECT COUNT(*) AS c FROM prices WHERE price <= 0").fetchone()["c"]
    assert bad == 0, "non-positive prices present"

    # date range filter works
    sub = con.execute(
        "SELECT COUNT(DISTINCT date) AS c FROM prices WHERE date >= '2024-01-01' AND date <= '2024-12-31'"
    ).fetchone()["c"]
    assert sub > 0

    # determinism: regenerating yields same numbers
    con2 = db.connect(db_path.replace(".db", "2.db"))
    model2 = model
    b2 = []
    for item_id, it in enumerate(model2.ITEMS, start=1):
        for day in model2.weekly_dates():
            b2.append((item_id, day.isoformat(), model2.price_at(day, it)))
    assert b2 == bulk, "regeneration differs -> pipeline is NOT reproducible"
    con2.close()
    con.close()
    print("test_seed_and_query  OK")


def test_alert_trigger(tmpdir):
    db_path = os.path.join(tmpdir, "alert.db")
    con = db.connect(db_path)
    db.init_db(db_path)
    from alert import compute_alerts
    con.execute("INSERT INTO items (id, name, category, unit) VALUES (1, 'Test', 'X', 'kg')")
    # one item, last two weeks: 100 then 115 -> 15% jump
    con.execute("INSERT INTO prices (item_id, date, price) VALUES (1, '2024-01-01', 100)")
    con.execute("INSERT INTO prices (item_id, date, price) VALUES (1, '2024-01-08', 115)")
    con.commit()
    n = compute_alerts(con, threshold=10.0)
    assert n == 1, f"expected 1 alert, got {n}"
    a = con.execute("SELECT * FROM alerts").fetchone()
    assert abs(a["pct_change"] - 15.0) < 0.01
    # a higher threshold should not trigger
    compute_alerts(con, threshold=20.0)
    assert con.execute("SELECT COUNT(*) AS c FROM alerts").fetchone()["c"] == 0
    con.close()
    print("test_alert_trigger   OK")


if __name__ == "__main__":
    tmp = tempfile.mkdtemp(prefix="pitp_")
    test_seed_and_query(tmp)
    test_alert_trigger(tmp)
    print("ALL TESTS PASSED")