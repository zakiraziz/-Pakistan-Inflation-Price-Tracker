"""Full inventory + integrity check for the Pakistan Inflation Price Tracker."""
import os
import sys
import sqlite3

ROOT = os.path.dirname(os.path.abspath(__file__))

EXPECTED_FILES = [
    # top-level
    "app.py",
    "db.py",
    "model.py",
    "seed.py",
    "scheduler.py",
    "job.py",
    "alert.py",
    "analyze.py",
    "log.py",
    "validators.py",
    "gen.py",
    "configure.py",
    "compute_coverage.py",
    "run_verify.py",
    "verify.py",
    "write_verify.py",
    "shot.py",
    ".env.example",
    ".env",
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "Makefile",
    "README.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "LICENSE",
    ".editorconfig",
    ".pre-commit-config.yaml",
    "CACHEDIR.TAG",
    ".gitignore",
    # core package
    "core/__init__.py",
    "core/config.py",
    "core/live.py",
    "core/security.py",
    # ingest package
    "ingest/__init__.py",
    "ingest/pipeline.py",
    "ingest/sources.py",
    # static
    "static/index.html",
    "static/app.js",
    "static/helpers.js",
    "static/live.js",
    "static/style.css",
    "static/favicon.svg",
    "static/methodology.html",
    "static/explainer.html",
    # tests
    "tests/__init__.py",
    "tests/conftest.py",
    "tests/test_api.py",
    "tests/test_api_surfaces.py",
    "tests/test_core.py",
    "tests/test_ingest.py",
    "tests/test_live.py",
    "tests/test_validators.py",
    "tests/test_web_app.py",
    # data
    "data/inflation.db",
]

MISSING = []
for rel in EXPECTED_FILES:
    full = os.path.join(ROOT, rel)
    if os.path.isfile(full):
        pass
    else:
        MISSING.append(rel)

print("=== FILE INVENTORY ===")
if MISSING:
    print(f"MISSING ({len(MISSING)}):")
    for m in MISSING:
        print(f"  ✗ {m}")
else:
    print("All expected files present.")


print()
print("=== DATABASE INTEGRITY ===")
db_path = os.path.join(ROOT, "data", "inflation.db")
try:
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r[0] for r in cur.fetchall()]
    print(f"Tables: {tables}")

    cur.execute("SELECT COUNT(*) FROM items")
    print(f"Items: {cur.fetchone()[0]}")

    cur.execute("SELECT COUNT(*) FROM prices WHERE status = 'approved'")
    print(f"Approved prices: {cur.fetchone()[0]}")

    cur.execute("SELECT COUNT(*) FROM prices WHERE status = 'pending'")
    print(f"Pending prices: {cur.fetchone()[0]}")

    cur.execute("SELECT COUNT(*) FROM prices WHERE status = 'rejected'")
    print(f"Rejected prices: {cur.fetchone()[0]}")

    cur.execute("SELECT MAX(date) FROM prices WHERE status = 'approved'")
    print(f"Latest approved date: {cur.fetchone()[0]}")

    cur.execute("SELECT MIN(date) FROM prices WHERE status = 'approved'")
    print(f"Earliest approved date: {cur.fetchone()[0]}")

    # spot-check: each item has at least 20 approved points
    cur.execute("SELECT i.name, COUNT(p.id) FROM items i LEFT JOIN prices p ON p.item_id = i.id AND p.status = 'approved' GROUP BY i.id")
    print("\nPer-item approved counts:")
    for name, cnt in cur.fetchall():
        flag = "" if cnt >= 20 else "  ← LOW"
        print(f"  {name}: {cnt}{flag}")

    con.close()
except Exception as e:
    print(f"DB ERROR: {e}")


print()
print("=== PYTHON PACKAGE HEALTH ===")
for pkg_init in ["core/__init__.py", "ingest/__init__.py", "tests/__init__.py"]:
    full = os.path.join(ROOT, pkg_init)
    if os.path.isfile(full):
        size = os.path.getsize(full)
        print(f"  OK  {pkg_init} ({size} bytes)")
    else:
        print(f"  MISSING  {pkg_init}")


print()
print("=== STATIC ASSET SIZES ===")
for name in ["index.html", "app.js", "helpers.js", "live.js", "style.css",
             "favicon.svg", "methodology.html", "explainer.html"]:
    full = os.path.join(ROOT, "static", name)
    if os.path.isfile(full):
        size = os.path.getsize(full)
        print(f"  OK  {name}: {size} bytes")
    else:
        print(f"  MISSING  {name}")


print()
print("=== CONFIG VALIDATION ===")
core_config = os.path.join(ROOT, "core", "config.py")
if os.path.isfile(core_config):
    with open(core_config) as f:
        src = f.read()
    checks = {
        "has from_env": "from_env" in src,
        "has SimpleCache default": "SimpleCache" in src,
        "has memory:// default": "memory://" in src,
        "has port 5010 default": "5010" in src,
        "has 300 per minute default": "300 per minute" in src,
        "has 60 per minute write": "60 per minute" in src,
    }
    for label, ok in checks.items():
        print(f"  {'OK' if ok else 'FAIL'}  config: {label}")
else:
    print("  MISSING  core/config.py")


print()
print("=== SUMMARY ===")
issues = []
if MISSING:
    issues.append(f"Missing files: {len(MISSING)}")
if os.path.isfile(db_path):
    try:
        con = sqlite3.connect(db_path)
        cur = con.cursor()
        cur.execute("SELECT COUNT(*) FROM prices WHERE status = 'approved'")
        cnt = cur.fetchone()[0]
        if cnt < 100:
            issues.append(f"Only {cnt} approved prices (expected 100+)")
        con.close()
    except Exception as e:
        issues.append(f"DB read error: {e}")

if issues:
    print("ISSUES:")
    for i in issues:
        print(f"  ✗ {i}")
else:
    print("Everything looks healthy.")
