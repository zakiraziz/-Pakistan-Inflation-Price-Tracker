"""
core/live.py
------------
Real-time change notification for the dashboard.

A dashboard that only refreshes when someone clicks a button shows stale
numbers the moment the ingest job runs. This module provides the two primitives
the SSE endpoint needs in order to *push* updates instead:

1. **Change detection** - :func:`revision` fingerprints the approved price data
   (``count:latest_date:max_id``) in one index-friendly query, so a client can
   tell "nothing changed" from "reload the charts" without re-fetching every
   dataset.
2. **Fan-out** - one background watcher thread polls that fingerprint and wakes
   every listener blocked in :func:`wait`. Because listeners share a condition
   variable, the query cost stays O(1) whether one browser or one hundred are
   connected.

Writers that know they changed the data (ingest, approve, reject) call
:func:`bump` to wake listeners immediately; the watcher is the safety net for
writes performed by another process (a second web worker, or scheduler.py).
"""

from __future__ import annotations

import json
import threading
import time
from datetime import UTC, datetime

import db
import log

logger = log.get_logger("live")

#: Keep-alive period for an idle SSE stream (seconds).
HEARTBEAT_SECONDS = 10.0
#: How often the watcher re-reads the data fingerprint (seconds).
POLL_SECONDS = 2.0
#: Longest single block inside :func:`wait`, so shutdown/tests stay responsive.
_WAIT_SLICE = 0.5

_cond = threading.Condition()
_tick = 0
_revision: str | None = None
_watcher: threading.Thread | None = None
_start_lock = threading.Lock()


def _aggregate() -> dict | None:
    """Fresh counts plus the newest approved week, in a single cheap query."""
    try:
        con = db.connect()
    except Exception:  # pragma: no cover - defensive (DB not created yet)
        return None
    try:
        approved = db.STATUS_APPROVED
        row = con.execute(
            "SELECT (SELECT COUNT(*) FROM items) AS items,"
            " (SELECT COUNT(*) FROM prices WHERE status = ?) AS approved,"
            " (SELECT MAX(date) FROM prices WHERE status = ?) AS latest,"
            " (SELECT MAX(id) FROM prices WHERE status = ?) AS max_id,"
            " (SELECT COUNT(*) FROM prices WHERE status = ?) AS pending",
            (approved, approved, approved, db.STATUS_PENDING),
        ).fetchone()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("live fingerprint query failed: %s", exc)
        return None
    finally:
        con.close()
    return dict(row)


def _stamp(row: dict) -> str:
    """Fingerprint string for one aggregate row."""
    return "{c}:{d}:{m}".format(
        c=row.get("approved") or 0, d=row.get("latest") or "-", m=row.get("max_id") or 0
    )


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def revision() -> str:
    """Fingerprint of the current approved dataset (cached stamp if unreadable)."""
    global _revision
    row = _aggregate()
    if row is None:
        return _revision or "unknown"
    _revision = _stamp(row)
    return _revision


def tick() -> int:
    """Current change counter (monotonic for the process lifetime)."""
    with _cond:
        return _tick


def bump(reason: str = "") -> int:
    """Wake every waiting listener; call after a write has been committed."""
    global _tick
    with _cond:
        _tick += 1
        current = _tick
        _cond.notify_all()
    logger.info("live update signalled (%s)", reason or "data changed")
    return current


def wait(previous: int, timeout: float) -> int:
    """Block until the tick moves past ``previous``, or ``timeout`` elapses."""
    deadline = time.monotonic() + max(0.0, timeout)
    with _cond:
        while _tick == previous:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            _cond.wait(min(remaining, _WAIT_SLICE))
        return _tick


def snapshot() -> dict:
    """Small, always-fresh payload describing the live data revision."""
    row = _aggregate()
    if row is None:
        return {
            "server_time": _utc_now(),
            "revision": _revision or "unknown",
            "items": 0,
            "approved_points": 0,
            "pending_points": 0,
            "latest_date": None,
            "heartbeat_seconds": HEARTBEAT_SECONDS,
        }
    return {
        "server_time": _utc_now(),
        "revision": _stamp(row),
        "items": row["items"],
        "approved_points": row["approved"],
        "pending_points": row["pending"],
        "latest_date": row["latest"],
        "heartbeat_seconds": HEARTBEAT_SECONDS,
    }


def sse_frame(event: str, payload: dict) -> str:
    """Format one Server-Sent Events frame (``event:``/``data:`` + blank line).

    ``json.dumps`` never emits a raw newline, so every frame stays on-message
    for a ``text/event-stream`` parser.
    """
    return "event: {e}\ndata: {d}\n\n".format(
        e=event, d=json.dumps(payload, separators=(",", ":"), sort_keys=True)
    )


def _watch() -> None:  # pragma: no cover - timing loop, exercised via /api/stream
    """Poll the fingerprint and signal listeners when the data moves."""
    global _revision
    while True:
        time.sleep(POLL_SECONDS)
        row = _aggregate()
        if row is None:
            continue
        stamp = _stamp(row)
        if stamp != _revision:
            _revision = stamp
            bump("watcher detected new data")


def start_watcher() -> None:
    """Start the single background watcher thread (idempotent)."""
    global _revision, _watcher
    with _start_lock:
        if _watcher is not None and _watcher.is_alive():
            return
        if _revision is None:
            _revision = revision()
        _watcher = threading.Thread(target=_watch, name="live-watcher", daemon=True)
        _watcher.start()
        logger.info("live watcher started (polling every %ss)", POLL_SECONDS)
