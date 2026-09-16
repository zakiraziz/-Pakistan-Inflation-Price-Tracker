"""Comprehensive end-to-end verification script."""
import json, os, signal, subprocess, sys, time, urllib.error, urllib.request

APP_DIR = r"c:\Users\zakir\Desktop\Pakistan Inflation  Price Tracker\-Pakistan-Inflation-Price-Tracker"
passed = 0
failed = 0
warnings = 0


def check(name, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        print(f"  PASS {name}")
    else:
        failed += 1
        print(f"  FAIL {name}" + (f": {detail}" if detail else ""))


def get_json(url):
    try:
        r = urllib.request.urlopen(url, timeout=10)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:500]
    except Exception as e:
        return 0, str(e)


def get_text(url):
    try:
        r = urllib.request.urlopen(url, timeout=10)
        return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:500]
    except Exception as e:
        return 0, str(e)


def post_json(url, data):
    try:
        req = urllib.request.Request(
            url, data=json.dumps(data).encode(),
            headers={"Content-Type": "application/json"}, method="POST"
        )
        r = urllib.request.urlopen(req, timeout=15)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:500]
    except Exception as e:
        return 0, str(e)


# ── Phase 1: Database state ──────────────────────────────────────────────
print("=== PHASE 1: Database state ===")
db_path = os.path.join(APP_DIR, "data", "inflation.db")
check("DB file exists", os.path.exists(db_path), f"path={db_path}")
if os.path.exists(db_path):
    import sqlite3
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    rows = cur.execute("SELECT COUNT(*) AS c FROM items").fetchone()
    check("Items table has rows", rows["c"] > 0, f"count={rows['c']}")
    apr = cur.execute("SELECT COUNT(*) AS c FROM prices WHERE status='approved'").fetchone()["c"]
    pen = cur.execute("SELECT COUNT(*) AS c FROM prices WHERE status='pending'").fetchone()["c"]
    rej = cur.execute("SELECT COUNT(*) AS c FROM prices WHERE status='rejected'").fetchone()["c"]
    latest = cur.execute("SELECT MAX(date) AS d FROM prices WHERE status='approved'").fetchone()["d"]
    check("Approved points > 0", apr > 0, f"approved={apr}")
    check("Pending points >= 0", pen >= 0, f"pending={pen}")
    check("Has approved data", latest is not None, f"latest_date={latest}")
    con.close()
BASE = "http://127.0.0.1:5010"

# ── Phase 2: Start server ────────────────────────────────────────────────
print("\n=== PHASE 2: Start server ===")
server_proc = subprocess.Popen(
    [sys.executable, os.path.join(APP_DIR, "app.py")],

# ── Phase 3: Health & status endpoints ───────────────────────────────────
print("\n=== PHASE 3: Health & status ===")
s, d = get_json(f"{BASE}/healthz")
check("GET /healthz 200", s == 200, f"status={s} body={str(d)[:200]}")
if s == 200:
    check("healthz.status == ok", d.get("status") == "ok", f"got={d.get('status')}")
    check("healthz.items == 11", d.get("items") == 11, f"got={d.get('items')}")
    check("healthz.approved_points > 0", d.get("approved_points", 0) > 0, f"got={d.get('approved_points')}")
    check("healthz.pending_points >= 0", d.get("pending_points", -1) >= 0, f"got={d.get('pending_points')}")
    check("healthz.latest_date is set", d.get("latest_date") is not None, f"got={d.get('latest_date')}")
    check("healthz.uptime_seconds > 0", d.get("uptime_seconds", 0) > 0, f"got={d.get('uptime_seconds')}")

s, d = get_json(f"{BASE}/readyz")
check("GET /readyz 200", s == 200, f"status={s} body={str(d)[:200]}")
if s == 200:
    check("readyz.status == ready", d.get("status") == "ready", f"got={d.get('status')}")
    check("readyz.approved_points > 0", d.get("approved_points", 0) > 0, f"got={d.get('approved_points')}")

# ── Phase 4: Data API endpoints ──────────────────────────────────────────
print("\n=== PHASE 4: Data API endpoints ===")

s, d = get_json(f"{BASE}/api/items")
check("GET /api/items 200", s == 200, f"status={s}")
if s == 200:
    check("/api/items returns list", isinstance(d, list), f"type={type(d).__name__}")
    check("/api/items count == 11", len(d) == 11, f"count={len(d)}")
    if isinstance(d, list) and len(d) > 0:
        item = d[0]
        check("/api/items has id field", "id" in item, f"keys={list(item.keys())}")
        check("/api/items has name field", "name" in item, f"keys={list(item.keys())}")

s, d = get_json(f"{BASE}/api/live")
check("GET /api/live 200", s == 200, f"status={s}")
if s == 200:
    check("/api/live has revision", "revision" in d, f"keys={list(d.keys())}")
    check("/api/live has server_time", "server_time" in d, f"keys={list(d.keys())}")
    check("/api/live has approved_points", "approved_points" in d, f"keys={list(d.keys())}")
    check("/api/live.items == 11", d.get("items") == 11, f"got={d.get('items')}")

s, d = get_json(f"{BASE}/api/series?start=2026-01-01&end=2026-06-30")
check("GET /api/series 200", s == 200, f"status={s}")
if s == 200:
    check("/api/series returns list", isinstance(d, list), f"type={type(d).__name__}")
    check("/api/series count > 0", len(d) > 0, f"count={len(d)}")

s, d = get_json(f"{BASE}/api/metrics?start=2025-07-01")
check("GET /api/metrics 200", s == 200, f"status={s}")
if s == 200:
    check("/api/metrics has count", "count" in d, f"keys={list(d.keys())}")
    check("/api/metrics has basket_pct", "basket_pct" in d, f"keys={list(d.keys())}")
    check("/api/metrics has biggest_riser", "biggest_riser" in d, f"keys={list(d.keys())}")

# ── Phase 5: Pages & static assets ───────────────────────────────────────
print("\n=== PHASE 5: Pages & static assets ===")

s, text = get_text(f"{BASE}/")
check("GET / dashboard 200", s == 200, f"status={s}")
if s == 200:
    check("Dashboard contains title", "Pakistan Inflation" in text, f"title found={'Pakistan Inflation' in text}")
    check("Dashboard references app.js", "app.js" in text, f"app.js ref={'app.js' in text}")
    check("Dashboard references live.js", "live.js" in text, f"live.js ref={'live.js' in text}")
    check("Dashboard references Chart.js CDN", "chart.js" in text.lower(), f"chart.js ref={'chart.js' in text.lower()}")

s, text = get_text(f"{BASE}/methodology")
check("GET /methodology 200", s == 200, f"status={s}")
try:
    r = urllib.request.urlopen(f"{BASE}/api/stream", timeout=5)
    hdrs = dict(r.headers)
    check("SSE Content-Type is text/event-stream", "text/event-stream" in hdrs.get("Content-Type", ""), f"got={hdrs.get('Content-Type')}")
    check("SSE Cache-Control is no-store", "no-store" in hdrs.get("Cache-Control", ""), f"got={hdrs.get('Cache-Control')}")
    check("SSE Connection is keep-alive", hdrs.get("Connection", "").lower() == "keep-alive", f"got={hdrs.get('Connection')}")
    data = r.read(500)
    check("SSE returns data", len(data) > 0, f"bytes={len(data)}")
    if len(data) > 0:
        check("SSE data contains event", b"event:" in data or b"data:" in data, f"preview={data[:100]!r}")
    r.close()
except Exception as e:
    check("SSE stream accessible", False, str(e))

# ── Phase 9: Post-ingest health check ────────────────────────────────────
print("\n=== PHASE 9: Post-ingest health ===")
time.sleep(2)
s, d = get_json(f"{BASE}/healthz")
check("POST-ingest /healthz 200", s == 200, f"status={s}")
if s == 200:
    check("healthz still ok after ingest", d.get("status") == "ok", f"got={d.get('status')}")

# ── Phase 10: Test suite ──────────────────────────────────────────────────
print("\n=== PHASE 10: Pytest suite ===")
result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"],
    cwd=APP_DIR, capture_output=True, text=True, timeout=300,
)
for line in result.stdout.splitlines():
    if line.strip():
        print(f"  | {line}")
check("Test suite exit code 0", result.returncode == 0, f"exit={result.returncode} stderr={result.stderr[:300]}")

# ── Summary ───────────────────────────────────────────────────────────────
print(f"\n=== SUMMARY ===")
print(f"  PASSED: {passed}")
print(f"  FAILED: {failed}")
if server_proc:
    server_proc.terminate()
    server_proc.wait(timeout=5)
    print("  Server shut down")
sys.exit(0 if failed == 0 else 1)

if s == 200:
    check("Methodology page has content", len(text) > 100, f"bytes={len(text)}")

for name in ["app.js", "helpers.js", "live.js", "style.css", "favicon.svg"]:
    s, text = get_text(f"{BASE}/static/{name}")
    check(f"GET /static/{name} 200", s == 200, f"status={s} bytes={len(text) if text else 0}")

s, text = get_text(f"{BASE}/static/explainer.html")
check("GET /static/explainer.html 200", s == 200, f"status={s} bytes={len(text) if text else 0}")

# ── Phase 6: POST /ingest/next ───────────────────────────────────────────
print("\n=== PHASE 6: POST /ingest/next ===")
s, d = post_json(f"{BASE}/ingest/next", {"auto_approve": True})
check("POST /ingest/next 200/201", s in (200, 201), f"status={s} body={str(d)[:300]}")
if s in (200, 201):
    check("POST /ingest/next has inserted", "inserted" in d, f"keys={list(d.keys())}")
    check("POST /ingest/next has for_week", "for_week" in d, f"keys={list(d.keys())}")
    check("POST /ingest/next has counts", "counts" in d, f"keys={list(d.keys())}")

# ── Phase 7: Admin approve/reject ────────────────────────────────────────
print("\n=== PHASE 7: Admin approve/reject ===")
s, d = post_json(f"{BASE}/api/admin/approve", {"all": True})
check("POST /api/admin/approve 200", s == 200, f"status={s} body={str(d)[:200]}")
if s == 200:
    check("/api/admin/approve has approved", "approved" in d, f"keys={list(d.keys())}")

s, d = post_json(f"{BASE}/api/admin/reject", {"all": True})
check("POST /api/admin/reject 200", s == 200, f"status={s} body={str(d)[:200]}")
if s == 200:
    check("/api/admin/reject has rejected", "rejected" in d, f"keys={list(d.keys())}")

# ── Phase 8: SSE stream ──────────────────────────────────────────────────
print("\n=== PHASE 8: SSE stream ===")
    check("/api/metrics has biggest_faller", "biggest_faller" in d, f"keys={list(d.keys())}")

s, d = get_json(f"{BASE}/api/index")
check("GET /api/index 200", s == 200, f"status={s}")
if s == 200:
    check("/api/index has basket", "basket" in d, f"keys={list(d.keys())}")

s, d = get_json(f"{BASE}/api/pivot?start=2026-01-01")
check("GET /api/pivot 200", s == 200, f"status={s}")
if s == 200:
    check("/api/pivot has dates", "dates" in d, f"keys={list(d.keys())}")
    check("/api/pivot has items", "items" in d, f"keys={list(d.keys())}")
    check("/api/pivot has index", "index" in d, f"keys={list(d.keys())}")

s, d = get_json(f"{BASE}/api/inflation?start=2023-01-01&end=2026-06-30")
check("GET /api/inflation 200", s == 200, f"status={s}")
if s == 200:
    check("/api/inflation has basket_pct", "basket_pct" in d, f"keys={list(d.keys())}")
    check("/api/inflation has annualized_pct", "annualized_pct" in d, f"keys={list(d.keys())}")
    check("/api/inflation has yoy_pct", "yoy_pct" in d, f"keys={list(d.keys())}")

s, d = get_json(f"{BASE}/api/alerts?threshold=5")
check("GET /api/alerts 200", s == 200, f"status={s}")
if s == 200:
    check("/api/alerts returns list", isinstance(d, list), f"type={type(d).__name__}")

s, d = get_json(f"{BASE}/api/series.csv?start=2026-01-01")
check("GET /api/series.csv 200", s == 200, f"status={s}")
if s == 200:
    text = d if isinstance(d, str) else d.decode() if isinstance(d, bytes) else ""
    check("/api/series.csv has CSV header", "date" in text, f"first line preview")

s, d = get_json(f"{BASE}/api/admin/pending")
check("GET /api/admin/pending 200", s == 200, f"status={s}")
if s == 200:
    check("/api/admin/pending returns list", isinstance(d, list), f"type={type(d).__name__}")
    cwd=APP_DIR,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    preexec_fn=os.setsid,
)
print(f"  Server PID: {server_proc.pid}")
if not wait_for_server(timeout=30):
    check("Server responds to /healthz", False, "timed out after 30s")
    server_proc.terminate()
    sys.exit(1)
print()