"""Ingestion pipeline: provenance, validation staging, and idempotency."""

from __future__ import annotations

import db
from ingest.pipeline import ingest


def _seed_items(con):
    con.execute(
        "INSERT INTO items (id, name, category, unit) " "VALUES (1, 'Rice', 'Grocery', 'per kg')"
    )
    con.commit()


def test_provenance_is_recorded(tmp_db):
    con, _ = tmp_db
    _seed_items(con)
    points = [{"item": "Rice", "date": "2026-01-01", "price": 100.0, "method": "csv-import"}]
    counts = ingest(con, points, source_name="pbs-web", method="csv-import")

    row = con.execute("SELECT * FROM prices WHERE item_id = 1").fetchone()
    assert row["source"] == "pbs-web"
    assert row["method"] == "csv-import"
    assert row["collected_at"]  # timestamp recorded
    assert row["status"] == db.STATUS_APPROVED  # no baseline -> approved
    assert counts["approved"] == 1


def test_suspicious_point_is_held_pending_and_excluded(tmp_db):
    con, path = tmp_db
    _seed_items(con)
    base = [{"item": "Rice", "date": "2026-01-01", "price": 100.0, "method": "csv"}]
    ingest(con, base, source_name="csv", method="csv-import")
    spike = [{"item": "Rice", "date": "2026-01-08", "price": 300.0, "method": "csv"}]
    counts = ingest(con, spike, source_name="csv", method="csv-import")

    assert counts["pending"] == 1
    row = con.execute(
        "SELECT status, review_note FROM prices " "WHERE date = '2026-01-08'"
    ).fetchone()
    assert row["status"] == db.STATUS_PENDING
    assert "suspicious" in row["review_note"]

    # public queries only use approved data, so the bad point is invisible
    con.close()
    import app as app_mod

    rows = app_mod._series_between("2026-01-01", "2026-12-31", [1])
    assert len(rows) == 1 and rows[0]["price"] == 100.0


def test_ingest_is_idempotent(tmp_db):
    con, _ = tmp_db
    _seed_items(con)
    points = [{"item": "Rice", "date": "2026-01-01", "price": 100.0, "method": "csv"}]
    first = ingest(con, points, source_name="csv", method="csv-import")
    second = ingest(con, points, source_name="csv", method="csv-import")
    assert first["approved"] == 1
    assert second["skipped"] == 1 and second["approved"] == 0


def test_unknown_item_is_rejected(tmp_db):
    con, _ = tmp_db
    _seed_items(con)
    counts = ingest(
        con,
        [{"item": "Mystery", "date": "2026-01-01", "price": 10.0, "method": "csv"}],
        source_name="csv",
        method="csv-import",
    )
    assert counts["rejected"] == 1


def test_ingestion_is_audited(tmp_db):
    con, _ = tmp_db
    _seed_items(con)
    ingest(
        con,
        [{"item": "Rice", "date": "2026-01-01", "price": 100.0, "method": "csv"}],
        source_name="csv",
        method="csv-import",
    )
    audit = con.execute("SELECT * FROM ingestions").fetchall()
    assert len(audit) == 1
    assert audit[0]["points_total"] == 1
    assert audit[0]["points_approved"] == 1
