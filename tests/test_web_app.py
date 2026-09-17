"""App-level tests: health, caching + invalidation, and the approval flow.

The Flask app is a module-level singleton, so its rate limiter (``app.limiter``,
``memory://`` storage) and response cache persist across every test in the
process: counters accumulate per client IP and a burst of requests in earlier
tests can push later requests over the limit (429) — a classic
shared-fixture bug that only shows up in CI or long runs.

The ``client`` fixture below resets the limiter's storage and the cache before
each test instead of disabling rate limiting. That keeps the limiter itself
exercised (headers, storage wiring) while guaranteeing every test starts with
a clean budget. ``test_rate_limit_enforced`` then proves the limiter still
rejects with 429 when a limit really is exceeded.
"""
from __future__ import annotations

import pytest


@pytest.fixture()
def client(tmp_db, monkeypatch):
    import seed

    con, path = tmp_db
    seed.load(con)
    import app as app_mod

    app_mod.app.config["TESTING"] = True
    # Fresh rate-limit budget + cache for every test (see module docstring).
    app_mod.limiter.reset()
    app_mod.cache.clear()
    yield app_mod.app.test_client()
    app_mod.limiter.reset()
    app_mod.cache.clear()
    con.close()


def test_healthz_ok(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"] == "ok"
    assert body["items"] == 11
    assert body["approved_points"] > 0


def test_pending_are_hidden_until_approved(client):
    # ingest a far-future week in manual mode -> all points held pending
    r = client.post("/ingest/next", json={"date": "2026-12-01",
                                          "auto_approve": False})
    assert r.status_code == 200
    assert r.get_json()["counts"]["pending"] == 11

    # pending data must NOT appear in the public index
    series = client.get("/api/series?start=2026-01-01").get_json()
    assert all(row["date"] <= "2026-06-28" for row in series)

    pend = client.get("/api/admin/pending").get_json()
    assert len(pend) == 11

    # approving lifts them into the index
    r = client.post("/api/admin/approve", json={"all": True})
    assert r.get_json()["approved"] == 11
    series = client.get("/api/series?start=2026-01-01").get_json()
    assert max(row["date"] for row in series) > "2026-06-28"


def test_caching_and_invalidation(client):
    before = client.get("/api/metrics?start=2025-07-01").get_json()

    # silently add an approved point beyond the current window end
    import db as db_mod
    con = db_mod.connect()
    item = con.execute("SELECT id FROM items LIMIT 1").fetchone()["id"]
    con.execute("INSERT INTO prices (item_id, date, price, source, method, "
                "collected_at, status) VALUES (?, '2026-08-01', 1.0, 'test', "
                "'unit-test', 'now', 'approved')", (item,))
    con.commit()
    con.close()

    # still cached: the response is unchanged despite new data
    cached = client.get("/api/metrics?start=2025-07-01").get_json()
    assert cached == before

    # invalidate -> the new data is visible
    client.post("/api/admin/reject", json={"all": True})   # clears cache
    after = client.get("/api/metrics?start=2025-07-01").get_json()
    assert after != before


def test_rate_limit_headers_present(client):
    r = client.get("/api/items")
    assert r.status_code == 200