"""
db.py
-----
SQLite connection + schema helpers.

SQLite is used (rather than Postgres) so the project has zero external-server
dependency and runs anywhere — which makes the data pipeline reproducible.
The schema mirrors what a Postgres deployment would look like.
"""
from __future__ import annotations

import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "inflation.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id       INTEGER PRIMARY KEY,
    name     TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,
    unit     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS prices (
    id      INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES items(id),
    date    TEXT NOT NULL,            -- ISO yyyy-mm-dd
    price   REAL NOT NULL,
    UNIQUE (item_id, date)
);

CREATE INDEX IF NOT EXISTS idx_prices_item_date ON prices(item_id, date);

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
"""


def connect(path: str = DB_PATH) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_db(path: str = DB_PATH) -> sqlite3.Connection:
    con = connect(path)
    con.executescript(SCHEMA)
    con.commit()
    return con


def get_items(con: sqlite3.Connection) -> list:
    return con.execute("SELECT * FROM items ORDER BY category, name").fetchall()


def get_item_map(con: sqlite3.Connection) -> dict:
    """Map lowercase item-name -> row, for quick lookups by string."""
    return {r["name"]: r for r in get_items(con)}