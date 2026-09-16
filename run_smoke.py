"""End-to-end smoke test for Pakistan Inflation Price Tracker."""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

APP_DIR = r"c:\Users\zakir\Desktop\Pakistan Inflation  Price Tracker\-Pakistan-Inflation-Price-Tracker"
BASE = "http://127.0.0.1:5010"

# Find the real python executable - sys.executable may point to a broken symlink,
# so we resolve via sys.prefix which is always correct.
REAL_PYTHON = os.path.join(sys.prefix, "bin", "python.exe")
if not os.path.isfile(REAL_PYTHON):
    # Fallback: scan .venv/bin for python.exe
    for name in ("python.exe", "python3.exe", "python3.11.exe", "python3.12.exe", "python3.13.exe", "python3.14.exe"):
        candidate = os.path.join(sys.prefix, "bin", name)
        if os.path.isfile(candidate) and os.path.getsize(candidate) > 1000000:
            REAL_PYTHON = candidate
            break
if not os.path.isfile(REAL_PYTHON):
    raise RuntimeError(f"Cannot find real python executable in {sys.prefix}/bin/")

passed = 0
failed = 0


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
        return e.code, e.read().decode()[:300]
    except Exception as e:
        return 0, str(e)


def get_text(url):
    try:
        r = urllib.request.urlopen(url, timeout=10)
        return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]
    except Exception as e:
        return 0, str(e)


def post_json(url, data):
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        r = urllib.request.urlopen(req, timeout=15)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]
    except Exception as e:
        return 0, str(e)


def wait_for_server(timeout=30):
    for i in range(timeout):
        time.sleep(1)
        s, d = get_json(f"{BASE}/healthz")
        if s == 200:
            print(f"  Server ready after {i+1}s")
            return True
    return False


def start_server():
    # Kill any existing process on port 5010 (don't kill all python.exe!)
    try:
        subprocess.run(
            ["powershell", "-Command",
             "(Get-NetTCPConnection -LocalPort 5010 -ErrorAction SilentlyContinue).OwningProcess | "
             "ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except Exception:
        pass
    time.sleep(1)
    # Use REAL_PYTHON which we resolved at module load time
    proc = subprocess.Popen(
        [REAL_PYTHON, "app.py"],
        cwd=APP_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc


def stop_server(proc):
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        pass


if __name__ == "__main__":
    print("=" * 60)
    print("  Pakistan Inflation Price Tracker - E2E Smoke Test")
    print("=" * 60)
    print()

    # Phase 1: Start server
    print("Phase 1: Starting server...")
    server_proc = start_server()
    if not wait_for_server():
        print("FAIL: Server did not start within 30s")
        sys.exit(1)
    print()

    # Phase 2: Health endpoints
    print("Phase 2: Health endpoints")
    s, d = get_json(f"{BASE}/healthz")
    check("GET /healthz 200", s == 200, f"status={s}")
    if s == 200:
        check("healthz.status == ok", d.get("status") == "ok", f"got={d.get('status')}")
        check("healthz.items == 11", d.get("items") == 11, f"got={d.get('items')}")
        check("healthz.approved_points > 0", d.get("approved_points", 0) > 0, f"got={d.get('approved_points')}")

    s, d = get_json(f"{BASE}/api/live")
    check("GET /api/live 200", s == 200)
    if s == 200:
        check("/api/live has revision", "revision" in d)
        check("/api/live has server_time", "server_time" in d)
        check("/api/live has items", "items" in d)
    print()

    # Phase 3: Data APIs
    print("Phase 3: Data APIs")
    s, d = get_json(f"{BASE}/api/series?start=2026-01-01&end=2026-06-30")
    check("GET /api/series 200", s == 200)
    if s == 200:
        check("/api/series is list", isinstance(d, list))
        check("/api/series count > 0", len(d) > 0, f"got={len(d)}")

    s, d = get_json(f"{BASE}/api/index")
    check("GET /api/index 200", s == 200)
    if s == 200:
        check("/api/index is list", isinstance(d, list), f"type={type(d).__name__}")
        check("/api/index non-empty", len(d) > 0, f"got={len(d)}")
        if d:
            check("/api/index has date", "date" in d[0])
            check("/api/index has index", "index" in d[0])

    s, d = get_json(f"{BASE}/api/inflation?start=2023-01-01&end=2026-06-30")
    check("GET /api/inflation 200", s == 200)
    if s == 200:
        check("/api/inflation has basket_pct", "basket_pct" in d)
        check("/api/inflation has annualized_pct", "annualized_pct" in d)
        check("/api/inflation has yoy_pct", "yoy_pct" in d)

    s, d = get_json(f"{BASE}/api/alerts?threshold=5")
    check("GET /api/alerts 200", s == 200)
    if s == 200:
        check("/api/alerts is list", isinstance(d, list))

    s, text = get_text(f"{BASE}/api/series.csv?start=2026-01-01")
    check("GET /api/series.csv 200", s == 200, f"status={s}")
    if s == 200:
        check("/api/series.csv has header", "item,date,price" in text, f"first 100 chars={text[:100]!r}")

    s, d = get_json(f"{BASE}/api/pivot?start=2026-01-01")
    check("GET /api/pivot 200", s == 200)
    if s == 200:
        check("/api/pivot has dates", "dates" in d)
        check("/api/pivot has items", "items" in d)
        check("/api/pivot has index", "index" in d)

    s, d = get_json(f"{BASE}/api/metrics?start=2025-07-01")
    check("GET /api/metrics 200", s == 200)
    if s == 200:
        check("/api/metrics has count", "count" in d)
        check("/api/metrics has basket_pct", "basket_pct" in d)
    print()

    # Phase 4: Admin APIs
    print("Phase 4: Admin APIs")
    s, d = get_json(f"{BASE}/api/admin/pending")
    check("GET /api/admin/pending 200", s == 200)
    print()

    # Phase 5: Pages & static assets
    print("Phase 5: Pages & static assets")
    s, text = get_text(f"{BASE}/")
    check("GET / dashboard 200", s == 200)
    if s == 200:
        check("Dashboard has title", "Pakistan Inflation" in text)
        check("Dashboard has app.js", "app.js" in text)
        check("Dashboard has live.js", "live.js" in text)
        check("Dashboard has Chart.js", "chart.js" in text.lower())

    s, text = get_text(f"{BASE}/methodology")
    check("GET /methodology 200", s == 200)

    for name in ["app.js", "helpers.js", "live.js", "style.css", "favicon.svg"]:
        s, text = get_text(f"{BASE}/static/{name}")
        check(f"GET /static/{name} 200", s == 200, f"bytes={len(text) if text else 0}")

    s, text = get_text(f"{BASE}/static/explainer.html")
    check("GET /static/explainer.html 200", s == 200)
    print()

    # Phase 6: Ingest flow
    print("Phase 6: Ingest flow")
    s, d = post_json(f"{BASE}/ingest/next", {"auto_approve": True})
    check("POST /ingest/next 200", s == 200, f"got={s}")
    if s == 200:
        check("ingest has inserted", "inserted" in d)
        check("ingest has for_week", "for_week" in d)

    s, d = get_json(f"{BASE}/healthz")
    check("healthz still ok after ingest", s == 200 and d.get("status") == "ok")
    print()

    # Summary
    print("=" * 60)
    print(f"  RESULT: {passed} passed, {failed} failed")
    print("=" * 60)
    stop_server(server_proc)
    sys.exit(0 if failed == 0 else 1)


