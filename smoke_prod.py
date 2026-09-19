"""
smoke_prod.py
-------------
Real-host smoke test: point it at a deployed instance and verify the things a
production URL must actually do. Implements the post-deploy checklist:

* health/readiness (``/healthz``, ``/readyz``) — tolerant of a cold free-tier
  instance via ``--wait``
* public reads (``/``, ``/api/metrics``, ``/api/series``) -> 200 with real data
* admin protection: no token -> 401/403, wrong token -> 401, right token -> 200
* security headers (CSP, nosniff, frame options, HSTS on https)
* ``text/event-stream`` on ``/api/stream`` (buffering disabled)
* rate-limit headers and the JSON error envelope

Usage
-----
    python smoke_prod.py https://my-service.onrender.com
    python smoke_prod.py https://my-service.onrender.com --token "$ADMIN_TOKEN"
    ADMIN_TOKEN=... python smoke_prod.py https://my-service.onrender.com --no-write

Exit code is 0 only when every check passes, so it can gate a release or run in
CI against a preview environment. ``--no-write`` skips the one mutating check
(``POST /ingest/next``), which is idempotent per week but does write.
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

PASS, FAIL, WARN = "PASS", "FAIL", "WARN"


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str]] = []

    def add(self, state: str, name: str, detail: str = "") -> None:
        self.rows.append((state, name, detail))
        mark = {PASS: "ok  ", FAIL: "FAIL", WARN: "warn"}[state]
        line = f"  [{mark}] {name}"
        if detail:
            line += f"  ({detail})"
        print(line, flush=True)

    def ok(self, name: str, detail: str = "") -> None:
        self.add(PASS, name, detail)

    def fail(self, name: str, detail: str = "") -> None:
        self.add(FAIL, name, detail)

    def warn(self, name: str, detail: str = "") -> None:
        self.add(WARN, name, detail)

    @property
    def failures(self) -> list[tuple[str, str, str]]:
        return [r for r in self.rows if r[0] == FAIL]

    @property
    def warnings(self) -> list[tuple[str, str, str]]:
        return [r for r in self.rows if r[0] == WARN]


def request(
    base: str,
    path: str,
    method: str = "GET",
    token: str | None = None,
    body: dict | None = None,
    timeout: float = 15.0,
):
    """Return (status, headers, body_text) and never raise for 4xx/5xx."""
    url = base + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("X-Admin-Token", token)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode("utf-8", "replace")
    except Exception as exc:  # connection refused, DNS, TLS...
        return 0, {}, f"{type(exc).__name__}: {exc}"


def as_json(text: str):
    try:
        return json.loads(text)
    except Exception:
        return None


def wait_for_health(base: str, report: Report, wait: float) -> bool:
    """Poll /healthz so a sleeping free-tier instance can wake up."""
    deadline = time.time() + max(0.0, wait)
    attempt = 0
    while True:
        attempt += 1
        status, _, text = request(base, "/healthz", timeout=20.0)
        if status == 200:
            if attempt > 1:
                report.ok("service woke up", f"after {attempt} attempt(s)")
            return True
        if time.time() >= deadline:
            report.fail("/healthz reachable", f"status={status} {text[:160]}")
            return False
        time.sleep(3)


def check_sse(base: str, report: Report, timeout: float) -> None:
    """Verify the stream headers *and* that a first frame arrives."""
    parts = urllib.parse.urlsplit(base)
    cls = http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
    conn = cls(parts.netloc, timeout=timeout)
    try:
        conn.request("GET", "/api/stream", headers={"Accept": "text/event-stream"})
        resp = conn.getresponse()
        headers = {k.lower(): v for k, v in resp.getheaders()}
        ctype = headers.get("content-type", "")
        if resp.status != 200 or "text/event-stream" not in ctype:
            report.fail("/api/stream headers", f"status={resp.status} content-type={ctype!r}")
            return
        report.ok("/api/stream headers", ctype)
        if "no-store" not in headers.get("cache-control", ""):
            report.warn("/api/stream Cache-Control", f"got {headers.get('cache-control')!r}")
        if headers.get("x-accel-buffering") != "no":
            report.warn(
                "/api/stream X-Accel-Buffering", f"got {headers.get('x-accel-buffering')!r}"
            )

        # the server pushes a snapshot frame immediately; read it without hanging
        if conn.sock is not None:
            conn.sock.settimeout(min(8.0, timeout))
        try:
            frame = resp.read(64)
        except TimeoutError:
            frame = b""
        if frame:
            report.ok("/api/stream first frame", frame[:40].decode("utf-8", "replace").strip())
        else:
            report.warn("/api/stream first frame", "no frame within timeout")
    except Exception as exc:
        report.fail("/api/stream", f"{type(exc).__name__}: {exc}")
    finally:
        conn.close()


def main() -> int:
    ap = argparse.ArgumentParser(description="Smoke-test a deployed instance.")
    ap.add_argument("url", help="base URL, e.g. https://my-service.onrender.com")
    ap.add_argument(
        "--token",
        default=os.environ.get("ADMIN_TOKEN", ""),
        help="admin token (defaults to $ADMIN_TOKEN)",
    )
    ap.add_argument(
        "--wait", type=float, default=60.0, help="seconds to wait for a cold instance (default 60)"
    )
    ap.add_argument("--timeout", type=float, default=15.0, help="per-request timeout")
    ap.add_argument(
        "--no-write", action="store_true", help="skip POST /ingest/next (the only mutating check)"
    )
    args = ap.parse_args()

    base = args.url.rstrip("/")
    if not base.startswith(("http://", "https://")):
        base = "https://" + base
    is_https = base.startswith("https://")
    token = (args.token or "").strip()

    print(f"\nSmoke-testing {base}")
    print(f"admin token: {'provided' if token else 'not provided'}\n")
    report = Report()

    if not wait_for_health(base, report, args.wait):
        return 1

    # ---- health & readiness ----
    status, _, text = request(base, "/healthz", timeout=args.timeout)
    data = as_json(text) or {}
    if status == 200 and data.get("status") == "ok":
        report.ok("/healthz", f"items={data.get('items')} approved={data.get('approved_points')}")
    else:
        report.fail("/healthz", f"status={status} body={text[:160]}")
    if not data.get("approved_points"):
        report.fail("/healthz has approved data", "approved_points is 0 — did boot.py seed?")

    status, _, text = request(base, "/readyz", timeout=args.timeout)
    ready = as_json(text) or {}
    if status == 200 and ready.get("status") == "ready":
        report.ok("/readyz", f"approved={ready.get('approved_points')}")
    else:
        report.fail("/readyz", f"status={status} body={text[:160]}")

    # ---- public reads ----
    status, _, text = request(base, "/", timeout=args.timeout)
    if status == 200 and "Pakistan Inflation" in text:
        report.ok("GET /", f"{len(text)} bytes")
    else:
        report.fail("GET /", f"status={status}")

    status, _, text = request(base, "/api/metrics?start=2025-07-01", timeout=args.timeout)
    metrics = as_json(text) or {}
    if status == 200 and metrics.get("count"):
        report.ok("/api/metrics", f"count={metrics['count']} basket={metrics.get('basket_pct')}")
    else:
        report.fail("/api/metrics", f"status={status} body={text[:160]}")

    status, _, text = request(base, "/api/series?start=2026-01-01", timeout=args.timeout)
    series = as_json(text)
    if status == 200 and isinstance(series, list) and series:
        report.ok("/api/series", f"{len(series)} rows")
    else:
        report.fail("/api/series", f"status={status} body={text[:160]}")

    status, _, text = request(base, "/api/series.csv?items=1,2", timeout=args.timeout)
    if status == 200 and text.startswith("item,date,price"):
        report.ok("/api/series.csv", "valid header")
    else:
        report.fail("/api/series.csv", f"status={status} body={text[:80]}")

    # ---- error envelope ----
    status, _, text = request(base, "/api/does-not-exist", timeout=args.timeout)
    err = (as_json(text) or {}).get("error", {})
    if status == 404 and err.get("code") == 404:
        report.ok("404 JSON envelope", err.get("message", "")[:40])
    else:
        report.fail("404 JSON envelope", f"status={status} body={text[:120]}")

    # ---- security headers ----
    _, headers, _ = request(base, "/", timeout=args.timeout)
    lowered = {k.lower(): v for k, v in headers.items()}
    for header in ("content-security-policy", "x-content-type-options", "x-frame-options"):
        if lowered.get(header):
            report.ok(f"header {header}", lowered[header][:40])
        else:
            report.fail(f"header {header}", "missing")
    if is_https:
        hsts = lowered.get("strict-transport-security")
        if hsts:
            report.ok("header strict-transport-security", hsts)
        else:
            report.fail("header strict-transport-security", "missing on https (FORCE_HTTPS?)")
    else:
        report.warn("https", "target is http:// — HSTS not applicable")

    # ---- rate limiting ----
    status, headers, _ = request(base, "/api/items", timeout=args.timeout)
    lowered = {k.lower(): v for k, v in headers.items()}
    if lowered.get("x-ratelimit-limit"):
        report.ok(
            "rate-limit headers",
            f"limit={lowered['x-ratelimit-limit']} remaining={lowered.get('x-ratelimit-remaining')}",
        )
    else:
        report.fail("rate-limit headers", "X-RateLimit-Limit missing")
    if status != 200:
        report.fail("/api/items", f"status={status}")

    # ---- SSE ----
    check_sse(base, report, args.timeout)

    # ---- admin protection ----
    status, _, text = request(base, "/api/admin/pending", timeout=args.timeout)
    if status in (401, 403):
        report.ok("/api/admin/pending requires auth", f"status={status} (public is blocked)")
    elif status == 200:
        report.fail("/api/admin/pending is PUBLIC", "anyone can read the review queue")
    else:
        report.fail("/api/admin/pending", f"unexpected status={status}")

    if token:
        status, _, _ = request(
            base, "/api/admin/pending", token="definitely-wrong", timeout=args.timeout
        )
        if status == 401:
            report.ok("wrong token rejected", "status=401")
        else:
            report.fail("wrong token rejected", f"expected 401, got {status}")

        status, _, text = request(base, "/api/admin/pending", token=token, timeout=args.timeout)
        if status == 200:
            report.ok("valid token accepted (GET)", f"{len(as_json(text) or [])} pending")
        else:
            report.fail("valid token accepted (GET)", f"status={status} body={text[:120]}")

        if args.no_write:
            report.warn("POST /ingest/next", "skipped (--no-write)")
        else:
            status, _, text = request(
                base,
                "/ingest/next",
                method="POST",
                token=token,
                body={"auto_approve": True},
                timeout=30.0,
            )
            payload = as_json(text) or {}
            if status == 200 and "inserted" in payload:
                report.ok(
                    "valid token accepted (POST /ingest/next)",
                    f"inserted={payload['inserted']} week={payload.get('for_week')}",
                )
            else:
                report.fail(
                    "valid token accepted (POST /ingest/next)",
                    f"status={status} body={text[:120]}",
                )
    else:
        status, _, _ = request(
            base, "/ingest/next", method="POST", body={"auto_approve": True}, timeout=args.timeout
        )
        if status in (401, 403):
            report.ok("write blocked without token", f"status={status}")
        else:
            report.fail("write blocked without token", f"expected 401/403, got {status}")
        report.warn("token checks skipped", "no --token/$ADMIN_TOKEN supplied")

    # ---- summary ----
    print(f"\n{'=' * 62}")
    print(
        f"  {len(report.rows) - len(report.failures) - len(report.warnings)} passed, "
        f"{len(report.failures)} failed, {len(report.warnings)} warning(s)"
    )
    if report.failures:
        print("\n  Failures:")
        for _, name, detail in report.failures:
            print(f"    - {name}: {detail}")
        print("\n  DEPLOYMENT NOT VERIFIED")
        return 1
    print("\n  DEPLOYMENT VERIFIED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
