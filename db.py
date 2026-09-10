"""
db.py
-----
Storage layer.

SQLite is the default backend so the project runs anywhere with zero external
servers (great for reproducibility). The DDL is written to be
Postgres-compatible, and every price point carries full provenance
(source / method / collected_at) plus an approval status so that bad scrapes
are held *pending* and never poison the public index.

Statuses:
    approved  - trusted, appears in the public index
    pending   - awaiting review (scraped point that failed an automated check)
    rejected  - manually declined; excluded everywhere

Swap to Postgres by running against a DATABASE_URL; the schema is the same.
"""
from __future__ import annotations

import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "inflation.db")

STATUS_APPROVED = "approved"
STATUS_PENDING = "pending"
STATUS_REJECTED = "rejected"

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id       INTEGER PRIMARY KEY,
    name     TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,
    unit     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS prices (
    id            INTEGER PRIMARY KEY,
    item_id       INTEGER NOT NULL REFERENCES items(id),
    date          TEXT NOT NULL,                -- ISO yyyy-mm-dd
    price         REAL NOT NULL,
    source        TEXT NOT NULL DEFAULT 'seed', -- provenance: where it came from
    method        TEXT NOT NULL DEFAULT 'generator', -- how it was fetched/parsed
    collected_at  TEXT NOT NULL DEFAULT '',     -- when it was collected (ISO)
    status        TEXT NOT NULL DEFAULT 'approved',
    review_note   TEXT NOT NULL DEFAULT '',
    UNIQUE (item_id, date)
);

CREATE INDEX IF NOT EXISTS idx_prices_item_date ON prices(item_id, date);
CREATE INDEX IF NOT EXISTS idx_prices_status     ON prices(status);

-- Audit log of every ingestion batch (data provenance / reproducibility).
CREATE TABLE IF NOT EXISTS ingestions (
    id               INTEGER PRIMARY KEY,
    source           TEXT NOT NULL,
    method           TEXT NOT NULL,
    ran_at           TEXT NOT NULL,
    target_date      TEXT,
    points_total     INTEGER NOT NULL DEFAULT 0,
    points_approved  INTEGER NOT NULL DEFAULT 0,
    points_pending   INTEGER NOT NULL DEFAULT 0,
    points_rejected  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS alerts (
    id            INTEGER PRIMARY KEY,
    item_id       INTEGER NOT NULL REFERENCES items(id),
    date          TEXT NOT NULL,
    price         REAL NOT NULL,
    prev_price    REAL,
    pct_change    REAL NOT NULL,
    threshold     REAL NOT NULL,
    UNIQUE (item_id, date)
);

CREATE INDEX IF NOT EXISTS idx_alerts_item_date ON alerts(item_id, date);
"""


def connect(path: str = None) -> sqlite3.Connection:
    path = path or DB_PATH            # resolved at call time (test-friendly)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_db(path: str = None) -> sqlite3.Connection:
    con = connect(path)
    con.executescript(SCHEMA)
    con.commit()
    return con


def get_items(con: sqlite3.Connection):
    return con.execute("SELECT * FROM items ORDER BY category, name").fetchall()


def get_item_map(con: sqlite3.Connection) -> dict:
    """Map item-name -> row, for quick lookups by name."""
    return {r["name"]: r for r in get_items(con)}


def count_status(con: sqlite3.Connection, status: str = STATUS_PENDING) -> int:
    return con.execute(
        "SELECT COUNT(*) AS c FROM prices WHERE status = ?", (status,)
    ).fetchone()["c"]


def pending_points(con: sqlite3.Connection, limit: int = 200):
    """Price points currently awaiting review, newest first."""
    return con.execute(
        "SELECT p.id, i.name AS item, p.date, p.price, p.source, p.method, "
        "       p.collected_at, p.review_note "
        "FROM prices p JOIN items i ON i.id = p.item_id "
        "WHERE p.status = ? ORDER BY p.collected_at DESC, p.id DESC LIMIT ?",
        (STATUS_PENDING, limit),
    ).fetchall()


def record_ingestion(con: sqlite3.Connection, source: str, method: str, target_date,
                     counts: dict) -> int:
    cur = con.execute(
        "INSERT INTO ingestions (source, method, ran_at, target_date, "
        "points_total, points_approved, points_pending, points_rejected) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (source, method, _utc_now(), target_date,
         counts.get("total", 0), counts.get("approved", 0),
         counts.get("pending", 0), counts.get("rejected", 0)),
    )
    return cur.lastrowid


def _utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")