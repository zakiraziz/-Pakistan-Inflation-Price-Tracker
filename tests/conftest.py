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
    """Flask test client wired to the isolated seeded database.

    The app is a module-level singleton, so its rate limiter (``memory://``
    storage) and response cache persist across every test in the process.
    Resetting both here gives each test a clean budget instead of disabling
    rate limiting — the limiter itself stays exercised.
    """
    import app as app_mod

    app_mod.app.config["TESTING"] = True
    app_mod.limiter.reset()
    app_mod.cache.clear()
    with app_mod.app.test_client() as c:
        yield c
    app_mod.limiter.reset()
    app_mod.cache.clear()
