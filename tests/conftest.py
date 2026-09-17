"""Shared pytest fixtures: an isolated temp database per test."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    """Point db.DB_PATH at a throwaway DB so the real one is untouched."""
    import db

    path = str(tmp_path / "test.db")
    monkeypatch.setattr(db, "DB_PATH", path)
    con = db.init_db(path)
    yield con, path
    con.close()


@pytest.fixture()
def seeded_db(tmp_db):
    """A temp DB loaded with the approved baseline."""
    import seed

    con, path = tmp_db
    seed.load(con)
    yield con, path


@pytest.fixture()
def client(seeded_db):
    """Flask test client wired to the isolated seeded database."""
    import app as app_mod

    app_mod.app.config["TESTING"] = True
    with app_mod.app.test_client() as c:
        yield c
