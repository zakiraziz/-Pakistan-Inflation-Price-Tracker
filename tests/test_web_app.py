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

import app as app_mod

# Registered at import (collection) time: Flask forbids adding routes after the
# app has handled its first request, and the app singleton is shared by every
# test in the process. The route is a throwaway probe used only by
# test_rate_limit_enforced and is harmless otherwise.
if not any(r.rule == "/api/_ratelimit-probe" for r in app_mod.app.url_map.iter_rules()):

    @app_mod.app.route("/api/_ratelimit-probe")
    @app_mod.limiter.limit("2 per minute")
    def _ratelimit_probe():  # pragma: no cover - trivial handler
        return {"ok": True}


@pytest.fixture()
def client(tmp_db):
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
    r = client.post("/ingest/next", json={"date": "2026-12-01", "auto_approve": False})
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
    con.execute(
        "INSERT INTO prices (item_id, date, price, source, method, "
        "collected_at, status) VALUES (?, '2026-08-01', 1.0, 'test', "
        "'unit-test', 'now', 'approved')",
        (item,),
    )
    con.commit()
    con.close()

    # still cached: the response is unchanged despite new data
    cached = client.get("/api/metrics?start=2025-07-01").get_json()
    assert cached == before

    # invalidate -> the new data is visible
    client.post("/api/admin/reject", json={"all": True})  # clears cache
    after = client.get("/api/metrics?start=2025-07-01").get_json()
    assert after != before


def test_rate_limit_headers_present(client):
    r = client.get("/api/items")
    assert r.status_code == 200
    # Flask-Limiter reports the active budget on every response.
    assert "X-RateLimit-Limit" in r.headers


def test_rate_limit_enforced(client):
    """Negative control: the limiter must 429 once a budget is exhausted.

    Uses the ``/api/_ratelimit-probe`` route (registered at import time with a
    deliberately tight "2 per minute" limit — see the module head). Proves the
    limiter is active after the fixture resets, and that ``core/security.py``
    returns the structured JSON 429 envelope.
    """
    import app as app_mod

    assert client.get("/api/_ratelimit-probe").status_code == 200
    assert client.get("/api/_ratelimit-probe").status_code == 200

    exhausted = client.get("/api/_ratelimit-probe")
    assert exhausted.status_code == 429
    assert "Retry-After" in exhausted.headers
    body = exhausted.get_json()
    assert body["error"]["code"] == 429
    assert "Slow down" in body["error"]["message"]

    # A fresh reset restores the budget (the same guarantee every test gets).
    app_mod.limiter.reset()
    assert client.get("/api/_ratelimit-probe").status_code == 200
