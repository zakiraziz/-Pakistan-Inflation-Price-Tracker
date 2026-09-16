"""Real-time layer: change detection, listener fan-out, and the SSE endpoint.

Covers core/live.py (the revision fingerprint and the wait/bump fan-out that
makes a push cheaper than a poll) plus the two endpoints that expose it:
GET /api/live for the polling fallback and GET /api/stream for Server-Sent
Events.
"""
from __future__ import annotations

import threading
import time

import pytest


@pytest.fixture()
def client(seeded_db):
    import app as app_mod
    app_mod.app.config["TESTING"] = True
    with app_mod.app.test_client() as c:
        yield c


def _insert(con, status, day):
    """Stage one price point straight in the DB (no HTTP, no ingest job)."""
    con.execute(
        "INSERT INTO prices (item_id, date, price, source, method, collected_at, "
        "status) VALUES (1, ?, 999.0, 'test', 'live-test', 'now', ?)",
        (day, status),
    )
    con.commit()


def _wait_in_thread(tick, timeout):
    from core import live

    live.wait(tick, timeout)


def test_live_snapshot_shape(client):
    body = client.get("/api/live").get_json()
    assert body["approved_points"] > 0
    assert body["items"] > 0
    assert body["latest_date"]
    assert body["heartbeat_seconds"] > 0
    assert body["server_time"].endswith("Z")
    assert body["revision"].count(":") == 2


def test_revision_moves_only_when_approved_data_changes(seeded_db):
    """The fingerprint is what lets a client skip work for an unchanged week."""
    import db as db_mod
    from core import live

    con, _ = seeded_db
    before = live.revision()
    assert live.revision() == before                     # stable when idle

    _insert(con, db_mod.STATUS_PENDING, "2026-12-27")
    assert live.revision() == before                     # staged != published

    _insert(con, db_mod.STATUS_APPROVED, "2026-12-20")
    assert live.revision() != before                     # published data moved


def test_bump_wakes_every_waiter():
    from core import live

    seen = live.tick()
    threads = [threading.Thread(target=_wait_in_thread, args=(seen, 5.0))
               for _ in range(3)]
    for t in threads:
        t.start()
    time.sleep(0.05)
    live.bump("unit test")
    for t in threads:
        t.join(timeout=5)
        assert not t.is_alive(), "a listener was left hanging"
    assert live.tick() > seen


def test_wait_times_out_when_nothing_changes(seeded_db):
    from core import live

    live.revision()                    # sync the watcher's baseline first
    seen = live.tick()
    start = time.monotonic()
    assert live.wait(seen, 0.3) == seen
    assert time.monotonic() - start >= 0.25


def test_sse_frame_is_well_formed():
    from core import live

    frame = live.sse_frame("update", {"revision": "1:2:3"})
    assert frame.startswith("event: update\n")
    assert "data: {" in frame
    assert frame.endswith("\n\n")
    assert "\n\n" not in frame[:-2]        # no stray blank line inside a frame