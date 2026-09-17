"""Full diagnostic: check every module, DB state, and run the server + tests."""

import os
import sqlite3
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))


def check(label, fn):
    try:
        result = fn()
        if result is not None:
            print(f"  OK  {label}: {result}")
        else:
            print(f"  OK  {label}")
        return True
    except Exception as e:
        print(f"  FAIL {label}: {type(e).__name__}: {e}")
        return False


print("=== 1. MODULE IMPORTS ===")
checks = []
checks.append(check("app", lambda: __import__("app")))
checks.append(check("db", lambda: __import__("db")))
checks.append(check("model", lambda: __import__("model")))
checks.append(check("seed", lambda: __import__("seed")))
checks.append(check("scheduler", lambda: __import__("scheduler")))
checks.append(check("job", lambda: __import__("job")))
checks.append(check("alert", lambda: __import__("alert")))
checks.append(check("core.config", lambda: __import__("core.config")))
checks.append(check("core.live", lambda: __import__("core.live")))
checks.append(check("core.security", lambda: __import__("core.security")))
checks.append(check("ingest.pipeline", lambda: __import__("ingest.pipeline")))
checks.append(check("ingest.sources", lambda: __import__("ingest.sources")))
checks.append(check("validators", lambda: __import__("validators")))
checks.append(check("log", lambda: __import__("log")))
checks.append(check("analyze", lambda: __import__("analyze")))
print(f"  => {sum(checks)}/{len(checks)} modules import cleanly")

print()
print("=== 2. DATABASE STATE ===")
db_path = os.path.join(ROOT, "data", "inflation.db")
if not os.path.isfile(db_path):
    print(f"  FAIL  DB file missing: {db_path}")
else:
    con = sqlite3.connect(db_path)
    try:
        tables = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        print(f"  OK  tables: {[t[0] for t in tables]}")
        for tbl in ["items", "prices", "alerts", "ingestions"]:
            cnt = con.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
            print(f"  OK  {tbl}: {cnt} rows")
        items = con.execute("SELECT id, name, category, unit FROM items ORDER BY id").fetchall()
        print(f"  OK  items ({len(items)}):")
        for i in items:
            print(f"      #{i[0]} {i[1]} ({i[2]}) {i[3]}")
        approved = con.execute("SELECT COUNT(*) FROM prices WHERE status='approved'").fetchone()[0]
        print(f"  OK  approved prices: {approved}")
        latest = con.execute("SELECT MAX(date) FROM prices WHERE status='approved'").fetchone()[0]
        earliest = con.execute("SELECT MIN(date) FROM prices WHERE status='approved'").fetchone()[0]
        print(f"  OK  date range: {earliest} -> {latest}")
        # Per-item check
        per_item = con.execute(
            "SELECT i.name, COUNT(p.id) FROM items i "
            "LEFT JOIN prices p ON p.item_id=i.id AND p.status='approved' "
            "GROUP BY i.id ORDER BY i.id"
        ).fetchall()
        print("  OK  per-item approved counts:")
        for name, cnt in per_item:
            flag = "  <-- LOW" if cnt < 20 else ""
            print(f"      {name}: {cnt}{flag}")
    finally:
        con.close()

print()
print("=== 3. SERVER BOOT TEST ===")
env = os.environ.copy()
env["FLASK_DEBUG"] = "0"
try:
    proc = subprocess.Popen(
        [sys.executable, "app.py"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
    )
    import time

    time.sleep(4)
    if proc.poll() is not None:
        out = proc.stdout.read(2000).decode("utf-8", errors="replace")
        print(f"  FAIL  Server exited during boot: {out!r}")
    else:
        print(f"  OK  Server running (PID {proc.pid})")
        # Hit healthz
        try:
            import urllib.request

            r = urllib.request.urlopen("http://127.0.0.1:5010/healthz", timeout=5)
            data = r.read().decode()
            print(f"  OK  /healthz: {data[:200]}")
        except Exception as e:
            print(f"  FAIL  /healthz: {e}")
        proc.terminate()
        proc.wait(timeout=5)
except Exception as e:
    print(f"  FAIL  server test: {e}")

print()
print("=== 4. PYTEST SUITE ===")
try:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr[:500])
    lines = result.stdout.strip().splitlines()
    summary = [ln for ln in lines if "passed" in ln or "failed" in ln or "error" in ln.lower()]
    print("  =>", summary[-1] if summary else "(no summary found)")
except Exception as e:
    print(f"  FAIL  pytest: {e}")

print()
print("=== 5. SCRATCH ARTIFACTS ===")
for name in os.listdir(ROOT):
    if (
        name.startswith("fresh")
        or name.startswith("rl_test")
        or name.startswith("server_live")
        or name.startswith("test_web")
        or name == "verify_results.txt"
        or name == "verify_server.log"
        or name == "_render_check.js"
        or name.startswith("dom")
        or name == "tail.b64"
        or name == "test_pipeline.py"
    ):
        full = os.path.join(ROOT, name)
        size = os.path.getsize(full)
        print(f"  NOTE  scratch artifact: {name} ({size} bytes)")
print("  (these are expected to be cleaned by .gitignore)")
