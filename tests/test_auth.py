"""
Admin/write guard tests (``core/auth.py``).

The guard closes the "anyone on the internet can rewrite my data" hole:

- ``ADMIN_TOKEN`` unset -> only strict-loopback callers may write (test client
  and local development), everyone else gets 403.
- ``ADMIN_TOKEN`` set   -> the token is mandatory for protected routes, from any
  caller (401 without it, 200 with a correct ``X-Admin-Token``/Bearer).
- Public reads and probes are never affected.
"""

from __future__ import annotations

import pytest

REMOTE = {"REMOTE_ADDR": "203.0.113.9"}  # TEST-NET-3: definitely not loopback

PROTECTED_WRITES = ["/api/admin/approve", "/api/admin/reject", "/ingest/next"]
PUBLIC_READS = ["/healthz", "/readyz", "/api/items", "/api/series?start=2026-01-01"]


@pytest.fixture(autouse=True)
def no_admin_token(monkeypatch):
    """Default posture for these tests: no token configured."""
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("ADMIN_ALLOW_LOCAL", raising=False)


def test_loopback_writes_allowed_without_token(client):
    """Local development / test client keeps working (no token needed)."""
    assert client.post("/api/admin/approve", json={"all": True}).status_code == 200


def test_remote_writes_blocked_without_token(client):
    """A public caller cannot write when no token is configured."""
    for path in PROTECTED_WRITES:
        r = client.post(path, json={"all": True}, environ_base=REMOTE)
        assert r.status_code == 403, f"{path} -> {r.status_code}"
        body = r.get_json()
        assert body["error"]["code"] == 403
        assert "ADMIN_TOKEN" in body["error"]["hint"]


def test_remote_cannot_read_review_queue(client):
    """/api/admin/pending exposes unapproved data, so it is protected too."""
    r = client.get("/api/admin/pending", environ_base=REMOTE)
    assert r.status_code == 403


def test_public_reads_never_blocked_from_remote(client):
    for path in PUBLIC_READS:
        assert client.get(path, environ_base=REMOTE).status_code == 200, path


def test_token_required_when_configured(client, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "s3cret-token")

    # loopback is not exempt once a token exists — callers must present it
    missing = client.post("/api/admin/approve", json={"all": True})
    assert missing.status_code == 401
    assert missing.headers["WWW-Authenticate"].startswith("Bearer")
    assert missing.get_json()["error"]["code"] == 401

    wrong = client.post("/api/admin/approve", json={"all": True}, headers={"X-Admin-Token": "nope"})
    assert wrong.status_code == 401

    ok_header = client.post(
        "/api/admin/approve", json={"all": True}, headers={"X-Admin-Token": "s3cret-token"}
    )
    assert ok_header.status_code == 200
    assert ok_header.get_json()["approved"] == 0  # nothing pending in a fresh seed

    ok_bearer = client.post(
        "/ingest/next",
        json={"auto_approve": True},
        headers={"Authorization": "Bearer s3cret-token"},
        environ_base=REMOTE,  # token works from the public internet too
    )
    assert ok_bearer.status_code == 200
    assert ok_bearer.get_json()["inserted"] > 0


def test_admin_allow_local_zero_closes_loopback(client, monkeypatch):
    """ADMIN_ALLOW_LOCAL=0 (e.g. nginx on the same host) fails closed."""
    monkeypatch.setenv("ADMIN_ALLOW_LOCAL", "0")
    r = client.post("/api/admin/approve", json={"all": True})
    assert r.status_code == 403
    # ...while public reads keep working
    assert client.get("/api/items").status_code == 200
