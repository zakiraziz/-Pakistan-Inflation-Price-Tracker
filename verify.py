"""Verify the Pakistan Inflation / Price Tracker end-to-end.

Boots the real Flask server (app.py) and then:

  1. probes every read API + HTML route and validates the JSON shape
  2. checks the dashboard shell for the elements app.js wires up
  3. measures CSS coverage of the dashboard's class names (style.css)
  4. checks every helper app.js calls is actually defined in helpers.js
  5. exercises POST /ingest/next (auto_approve) and re-reads /healthz

Everything is appended to verify_results.txt and echoed to stdout.
Exit code 0 = every check passed, 2 = at least one failure, 1 = no server.

    python verify.py
"""

import builtins
import contextlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
BASE_URL = "http://127.0.0.1:5010"

_PASS = 0
_FAIL = 0
_FAIL_LIST = []


def ok(desc, cond, note=""):
    """Record one check (echoed to stdout and appended to verify_results.txt)."""
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        log("  OK   " + desc)
    else:
        _FAIL += 1
        _FAIL_LIST.append((desc, note))
        log("  FAIL " + desc + ("  :: " + note if note else ""))


def get(path, timeout=8):
    """GET a path on the running server -> (status, body_bytes, content_type)."""
    try:
        with urllib.request.urlopen(BASE_URL + path, timeout=timeout) as r:
            return r.status, r.read(), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), exc.headers.get("Content-Type", "")
    except Exception as exc:
        return None, str(exc).encode(), ""


def get_json(path, timeout=8):
    """GET a path and decode JSON -> (obj, error_string)."""
    status, raw, _ = get(path, timeout)
    if status != 200:
        return None, "status=" + str(status)
    try:
        return json.loads(raw.decode("utf-8")), None
    except Exception as exc:
        return None, "json:" + str(exc)


def q(**kw):
    """Build a query string, dropping empty values."""
    return "?" + urllib.parse.urlencode({k: str(v) for k, v in kw.items() if v not in (None, "")})


def boot_server(timeout=40):
    """Start app.py and wait for /healthz to answer. Returns the Popen or None."""
    log_path = BASE_DIR / "verify_server.log"
    # The access log goes to a file, never an unread PIPE: Werkzeug logs every
    # request, and a full OS pipe (~4KB on Windows) deadlocks the server.
    with log_path.open("w", encoding="utf-8") as server_log:
        proc = subprocess.Popen(
            [sys.executable, str(BASE_DIR / "app.py")],
            cwd=str(BASE_DIR),
            stdout=server_log,
            stderr=subprocess.STDOUT,
            env={**os.environ, "FLASK_DEBUG": "0"},
        )
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(1)
        if proc.poll() is not None:  # crashed on boot
            return None
        status, _, _ = get("/healthz", timeout=3)
        if status == 200:
            return proc
    proc.kill()
    with contextlib.suppress(Exception):
        proc.wait(timeout=5)
    return None


# =========================================================================
#  MAIN
# =========================================================================
_LOG = BASE_DIR / "verify_results.txt"
_LOG.write_text("", encoding="utf-8")  # every run starts from a clean log


def log(*a, **k):
    """Print to stdout and append to verify_results.txt."""
    k.setdefault("flush", True)
    msg = " ".join(str(x) for x in a)
    with _LOG.open("a", encoding="utf-8") as fh:
        fh.write(msg + "\n")
    real_print(msg)


real_print = builtins.print
builtins.print = log

server = boot_server()
if server is None:
    log("SERVER DID NOT START - see verify_server.log")
    sys.exit(1)

log("Server ready.\n")
time.sleep(0.5)

START = "2023-01-01"  # full seeded range
RECENT = "2026-01-01"  # recent window

log("--- liveness / readiness ---")
j, e = get_json("/healthz")
ok("GET /healthz 200", j is not None, e)
if j:
    ok("healthz.status == ok", j.get("status") == "ok", str(j.get("status")))
    ok("healthz.items == 11", j.get("items") == 11, str(j.get("items")))
    ok("healthz.approved_points > 0", j.get("approved_points", 0) > 0)
    ok("healthz.latest_date present", bool(j.get("latest_date")))
    ok("healthz.pending_points >= 0", j.get("pending_points", 0) >= 0)
    ok("healthz.uptime_seconds > 0", j.get("uptime_seconds", 0) > 0)
    APPROVED_BEFORE = j.get("approved_points", 0)
else:
    APPROVED_BEFORE = None

j, e = get_json("/readyz")
ok("GET /readyz 200", j is not None, e)
if j:
    ok("readyz.status == ready", j.get("status") == "ready", str(j.get("status")))
    ok("readyz.approved_points > 0", j.get("approved_points", 0) > 0)

log("\n--- dashboard + static assets ---")
for path in [
    "/",
    "/static/style.css",
    "/static/helpers.js",
    "/static/app.js",
    "/static/explainer.html",
]:
    status, raw, _ = get(path)
    ok("GET " + path + " 200", status == 200, "status=" + str(status))

log("\n--- /api/items ---")
j, e = get_json("/api/items")
ok("GET /api/items 200", j is not None, e)
if j:
    ok("api/items is list", isinstance(j, list))
    ok("api/items count == 11", len(j) == 11, str(len(j)))
    ids = sorted(i.get("id") for i in j)
    ok("api/items ids == 1..11", ids == list(range(1, 12)), str(ids))
    ok(
        "api/items fields name/category/unit",
        all({"name", "category", "unit"} <= set(i) for i in j),
    )
    names = [i["name"] for i in j]
    ok("api/items includes Wheat flour", any("flour" in n.lower() for n in names))
    ok("api/items includes Sugar", any("Sugar" in n for n in names))

log("\n--- /api/series ---")
j, e = get_json("/api/series" + q(start=RECENT))
ok("GET /api/series?start=2026-01-01 200", j is not None, e)
if j:
    ok("api/series non-empty list", isinstance(j, list) and len(j) > 0)
    ok("api/series rows have name/date/price", all({"name", "date", "price"} <= set(r) for r in j))
    ok("api/series price is numeric", all(isinstance(r["price"], (int, float)) for r in j))

j, e = get_json("/api/series" + q(start=RECENT, end="2026-03-01", items="1,2"))
ok("GET /api/series (windowed, items=1,2) 200", j is not None, e)
if j:
    ok("api/series windowed has rows", len(j) > 0)
    ok("api/series windowed respects end date", all(r["date"] <= "2026-03-01" for r in j))
log("\n--- /api/index ---")
j, e = get_json("/api/index" + q(start=START))
ok("GET /api/index?start=2023-01-01 200", j is not None, e)
if j:
    ok("api/index non-empty", isinstance(j, list) and len(j) > 0)
    ok(
        "api/index normalised to 100 at window start",
        j[0].get("index") == 100.0,
        str(j[0].get("index")),
    )
    ok("api/index ends above 100", j[-1].get("index", 0) > 100, str(j[-1].get("index")))
    ok("api/index rows have date+index", all({"date", "index"} <= set(r) for r in j))
    ok("api/index is monotonic in date", [r["date"] for r in j] == sorted(r["date"] for r in j))

log("\n--- /api/metrics ---")
j, e = get_json("/api/metrics" + q(start=START))
ok("GET /api/metrics?start=2023-01-01 200", j is not None, e)
if j:
    for field in [
        "count",
        "weeks",
        "first_date",
        "last_date",
        "basket_pct",
        "start_total",
        "end_total",
        "biggest_riser",
        "biggest_faller",
    ]:
        ok("metrics has " + field, field in j)
    ok("metrics.count == 11", j.get("count") == 11, str(j.get("count")))
    ok("metrics.weeks >= 2", j.get("weeks", 0) >= 2, str(j.get("weeks")))
    ok("metrics.basket_pct != 0", j.get("basket_pct", 0) != 0)
    ok("metrics.end_total > start_total", j.get("end_total", 0) > j.get("start_total", 0))
    riser = j.get("biggest_riser") or {}
    faller = j.get("biggest_faller") or {}
    ok("metrics.biggest_riser has name+pct", {"name", "pct"} <= set(riser))
    ok("metrics.biggest_riser pct > 0", riser.get("pct", 0) > 0, str(riser.get("pct")))
    ok("metrics.biggest_faller has name+pct", {"name", "pct"} <= set(faller))
    ok("metrics.biggest_riser pct >= faller pct", riser.get("pct", 0) >= faller.get("pct", 0))

log("\n--- /api/pivot ---")
j, e = get_json("/api/pivot" + q(start=START))
ok("GET /api/pivot?start=2023-01-01 200", j is not None, e)
if j:
    ok("pivot.dates non-empty", len(j.get("dates", [])) > 0)
    ok("pivot.items == 11", len(j.get("items", [])) == 11, str(len(j.get("items", []))))
    ok("pivot.index starts at 100", j.get("index", [None])[0] == 100.0)
    if j.get("items"):
        it = j["items"][0]
        for field in ["name", "category", "unit", "first", "last", "pct", "prices"]:
            ok("pivot.item has " + field, field in it)
        ok(
            "pivot.item.prices aligned with dates",
            len(it.get("prices", [])) == len(j.get("dates", [])),
        )
        ok("pivot.item.last == prices[-1]", it.get("last") == it.get("prices", [None])[-1])

j, e = get_json("/api/pivot" + q(start=RECENT, items="1,2,3"))
ok("GET /api/pivot (items=1,2,3) 200", j is not None, e)
if j:
    ok(
        "pivot honours items filter (3 items)",
        len(j.get("items", [])) == 3,
        str(len(j.get("items", []))),
    )

log("\n--- /api/inflation ---")
j, e = get_json("/api/inflation" + q(start=START))
ok("GET /api/inflation?start=2023-01-01 200", j is not None, e)
if j:
    ok("inflation.weeks >= 2", j.get("weeks", 0) >= 2, str(j.get("weeks")))
    ok("inflation.annualized_pct present", j.get("annualized_pct") is not None)
    ok("inflation.yoy_pct present", j.get("yoy_pct") is not None)
    ok("inflation.annualized_pct > 0", (j.get("annualized_pct") or 0) > 0)

log("\n--- /api/alerts ---")
j, e = get_json("/api/alerts" + q(threshold=20))
ok("GET /api/alerts?threshold=20 200", j is not None, e)
if j is not None:
    ok("api/alerts returns a list", isinstance(j, list))
    ok(
        "api/alerts rows have required fields",
        all({"name", "category", "date", "price", "prev_price", "pct"} <= set(r) for r in j),
    )
    ok("api/alerts respects threshold", all(r.get("pct", 0) >= 20 for r in j))

j, e = get_json("/api/alerts" + q(threshold=5, start=RECENT))
ok("GET /api/alerts?threshold=5&start=2026-01-01 200", j is not None, e)
if j is not None:
    ok("api/alerts windowed respects start", all(r.get("date", "") >= RECENT for r in j))

log("\n--- /api/series.csv ---")
status, raw, ctype = get("/api/series.csv" + q(items="1,2"))
ok("GET /api/series.csv 200", status == 200, "status=" + str(status))
ok("csv content-type is text/csv", "csv" in (ctype or "").lower(), str(ctype))
if status == 200:
    text = raw.decode("utf-8", errors="replace")
    ok(
        "csv header is item,date,price",
        text.startswith("item,date,price"),
        text.splitlines()[0] if text.splitlines() else "",
    )
    ok("csv has data rows", len(text.splitlines()) > 1, str(len(text.splitlines())) + " lines")

log("\n--- /methodology ---")
status, raw, _ = get("/methodology")
ok("GET /methodology 200", status == 200, "status=" + str(status))
if status == 200:
    meth = raw.decode("utf-8", errors="replace")
    ok("methodology page is non-trivial", len(meth) > 500, str(len(meth)) + " chars")
    ok(
        "methodology mentions the basket/index",
        "basket" in meth.lower() and "index" in meth.lower(),
    )
# =========================================================================
#  DASHBOARD SHELL  (static/index.html + style.css + helpers.js integration)
# =========================================================================
log("\n--- dashboard shell (index.html served at /) ---")
status, raw, _ = get("/")
ok("GET / 200", status == 200, "status=" + str(status))
html = raw.decode("utf-8", errors="replace") if status == 200 else ""

for marker in [
    'id="kpis"',
    'id="view"',
    'id="alertsPanel"',
    'id="itemList"',
    'id="categoryFilters"',
    'id="search"',
    'id="threshold"',
    'id="start"',
    'id="end"',
    'id="apply"',
    'id="export"',
    'id="updateNow"',
    'id="updatedBadge"',
    'id="toast"',
    'id="infoLine"',
    'role="tablist"',
    'class="tab"',
    'class="hero"',
    'class="presets"',
    'class="kpi"',
    "/static/helpers.js",
    "/static/app.js",
    "/static/style.css",
    "chart.js",
    "Inter",
]:
    ok("index.html contains " + marker, marker in html)

index_html = (BASE_DIR / "static" / "index.html").read_text(encoding="utf-8")
style_css = (BASE_DIR / "static" / "style.css").read_text(encoding="utf-8")
helpers_js = (BASE_DIR / "static" / "helpers.js").read_text(encoding="utf-8")
app_js = (BASE_DIR / "static" / "app.js").read_text(encoding="utf-8")

# ---- CSS coverage: every class used in the shell must be styled ----------
IDENT = re.compile(r"^[A-Za-z_][\w-]*$")

dom_classes = set()
for m in re.finditer(r"""class\s*=\s*["']([^"']*)["']""", index_html):
    for tok in m.group(1).split():
        if IDENT.match(tok):
            dom_classes.add(tok)

css_classes = set()
for prelude in re.findall(r"([^{}]+)\{", style_css):
    for sel in prelude.split(","):
        for m in re.finditer(r"\.(-?[A-Za-z_][\w-]*)", sel):
            css_classes.add(m.group(1))

unstyled = sorted(c for c in dom_classes if c not in css_classes)
ratio = len(dom_classes) - len(unstyled)
log("\n--- CSS coverage (index.html classes -> style.css rules) ---")
ok("style.css defines >= 40 class selectors", len(css_classes) >= 40, str(len(css_classes)))
ok(
    "every index.html class has a style.css rule",
    not unstyled,
    "unstyled: " + ", ".join("." + c for c in unstyled),
)
styled_pct = round(100.0 * ratio / max(1, len(dom_classes)))
log(f"  INFO dashboard shell classes: {len(dom_classes)}, " f"styled: {ratio} ({styled_pct}%)")

# ---- helpers.js <-> app.js integration ----------------------------------
log("\n--- helpers.js / app.js integration ---")
defined = set(re.findall(r"function\s+(\w+)\s*\(", helpers_js))
called = set(re.findall(r"\b(\w+)\s*\(", app_js))
needed = sorted(defined & called)
ok("helpers.js defines functions", len(defined) >= 15, str(len(defined)))
ok("app.js calls at least 10 helpers", len(needed) >= 10, str(len(needed)))
ok(
    "helpers.js is loaded before app.js in index.html",
    index_html.find("/static/helpers.js") < index_html.find("/static/app.js"),
)
for name in [
    "renderSkeletons",
    "renderAlerts",
    "renderTrends",
    "renderCompare",
    "renderData",
    "renderError",
    "money",
    "pct",
    "pctCls",
    "esc",
    "monthsAgo",
    "thresholdVal",
    "destroyChart",
    "el",
    "toast",
]:
    ok("app.js -> helpers." + name, name in defined and name in called)
# =========================================================================
#  WRITE PATH  (POST /ingest/next)  -- idempotent, so safe to exercise
# =========================================================================
log("\n--- POST /ingest/next (auto_approve) ---")
try:
    payload = json.dumps({"auto_approve": True}).encode("utf-8")
    req = urllib.request.Request(
        BASE_URL + "/ingest/next",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        status, raw = resp.status, resp.read()
except urllib.error.HTTPError as exc:
    status, raw = exc.code, exc.read()
except Exception as exc:
    status, raw = None, str(exc).encode()

ok("POST /ingest/next -> 200", status == 200, "status=" + str(status))
if status == 200:
    try:
        body = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        body = None
        ok("ingest/next returns valid JSON", False, str(exc))
    if body is not None:
        ok("ingest/next returns valid JSON", True)
        for field in ["inserted", "for_week", "counts"]:
            ok("ingest/next has " + field, field in body)
        ok("ingest/next.inserted >= 0", body.get("inserted", -1) >= 0)
        ok(
            "ingest/next.counts has approved+pending",
            {"approved", "pending"} <= set(body.get("counts") or {}),
        )
        ok(
            "ingest/next.for_week is an ISO date",
            isinstance(body.get("for_week"), str) and len(body.get("for_week")) == 10,
            str(body.get("for_week")),
        )

log("\n--- post-ingest health ---")
j, e = get_json("/healthz")
ok("GET /healthz after ingest 200", j is not None, e)
if j:
    ok("healthz still reports ok", j.get("status") == "ok", str(j.get("status")))
    ok(
        "approved_points unchanged or higher",
        APPROVED_BEFORE is None or j.get("approved_points", 0) >= APPROVED_BEFORE,
        f"before={APPROVED_BEFORE} after={j.get('approved_points')}",
    )
    ok("healthz.items still 11", j.get("items") == 11, str(j.get("items")))

# =========================================================================
#  TEARDOWN + REPORT
# =========================================================================
server.terminate()
try:
    server.wait(timeout=10)
except Exception:
    server.kill()

log("")
log("=" * 62)
log(f"RESULT: {_PASS} passed, {_FAIL} failed")
if _FAIL_LIST:
    log("FAILURES:")
    for desc, note in _FAIL_LIST:
        log("  * " + desc + ("  :: " + note if note else ""))
else:
    log("All checks passed.")
log("=" * 62)

sys.exit(0 if _FAIL == 0 else 2)
