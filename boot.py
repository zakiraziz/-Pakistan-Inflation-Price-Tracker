"""
boot.py
-------
Boot-time bootstrap for hosts with an **ephemeral filesystem** (Render free
tier, most PaaS demos): make sure the database exists and has the approved
baseline before the web server starts.

Idempotent by design:
- schema missing            -> created by ``db.init_db()``
- schema present + populated -> nothing happens (existing data is kept, e.g.
                               on a persistent disk or after a cold restart)
- schema present but empty   -> seeded from ``seed.load()``

Run it as the start command before the server::

    python boot.py && python app.py
"""

from __future__ import annotations

import sqlite3

import db
import log

logger = log.get_logger("boot")


def ensure_data() -> str:
    """Guarantee a usable database; return what happened ('kept'|'seeded')."""
    con = db.init_db()  # creates schema if missing (no-op otherwise)
    try:
        try:
            n = con.execute("SELECT COUNT(*) AS c FROM items").fetchone()["c"]
        except sqlite3.OperationalError:  # pragma: no cover - defensive
            n = 0
        if n:
            logger.info("database already populated (%s items) — keeping it", n)
            return "kept"
        import seed

        seed.load(con)
        con.commit()
        approved = db.count_status(con, db.STATUS_APPROVED)
        logger.info("seeded baseline: %s approved price rows", approved)
        return "seeded"
    finally:
        con.close()


if __name__ == "__main__":
    print("boot: database", ensure_data())
