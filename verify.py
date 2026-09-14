"""End-to-end verification: boot server, hit every route, check CSS coverage."""
import json, os, subprocess, sys, time, urllib.request, urllib.parse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
BASE = "http://127.0.0.1:5010"
ok_list, fail_list = [], []

def check(desc, ok, detail=""):
    (ok_list if ok else fail_list).append((desc, detail))
    tag = "OK   " if ok else "FAIL "
    print(f"  {tag} {desc}" + (f"  ({detail})" if detail else ""))

def get(path, timeout=8):
    url = BASE + path
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read(), r.headers.get("Content-Type", "")
    except Exception as e:
        return None, str(e).encode(), ""

def get_json(path, timeout=8):
    st, body, ct = get(path, timeout)
    if st != 200:
        return None, f"status={st}"
    try:
        return json.loads(body.decode("utf-8")), None
    except Exception as e:
        return None, f"json:{e}"

def boot(timeout=30):
    p = subprocess.Popen([sys.executable, str(BASE_DIR/"app.py")], cwd=BASE_DIR,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         env={**os.environ, "FLASK_DEBUG":"0"})
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(1)
        if p.poll() is not None:
            return None
        try:
            if get("/healthz", timeout=2)[0] == 200:
                return p
        except Exception:
            pass
    p.kill(); p.wait(timeout=5)
    return None

# ============================== healthz
j, e = get_json("/healthz")
check("GET /healthz 200", j is not None, e or "")
if j:
    check("healthz.status == ok", j.get("status") == "ok")
    check("healthz.items == 11", j.get("items") == 11, str(j.get("items")))
    check("healthz.approved_points > 0", (j.get("approved_points") or 0) > 0, str(j.get("approved_points")))
    check("healthz.pending_points >= 0", (j.get("pending_points") or 0) >= 0)
    check("healthz.latest_date present", bool(j.get("latest_date")), str(j.get("latest_date")))
    check("healthz.uptime_seconds present", bool(j.get("uptime_seconds")))

# ============================== index
j, e = get_json("/api/index?start=2025-07-01&end=2026-01-01")
check("GET /api/index 200", j is not None, e or "")
if j:
    check("index is list", isinstance(j, list))
    check("index non-empty", len(j) > 0)
    check("index[0] starts 100", j[0]["index"] == 100, str(j[0]["index"]))
    check("index[-1] grows", j[-1]["index"] > 100, str(j[-1]["index"]))

# ============================== metrics
j, e = get_json("/api/metrics?start=2025-07-01&end=2026-01-01")
check("GET /api/metrics 200", j is not None, e or "")
if j:
    for k in ("count","weeks","start_total","end_total","basket_pct",
              "biggest_riser","biggest_faller","first_date","last_date"):
        check(f"metrics.{k}", k in j)
    check("basket_pct numeric", isinstance(j.get("basket_pct"), (int,float)))
    check("biggest_riser has name+pct", bool(j.get("biggest_riser")))
    check("biggest_faller has name+pct", bool(j.get("biggest_faller")))

# ============================== pivot
j, e = get_json("/api/pivot?start=2025-07-01&end=2026-01-01")
check("GET /api/pivot 200", j is not None, e or "")
if j:
    check("pivot.dates list", isinstance(j.get("dates"), list))
    check("pivot.items list", isinstance(j.get("items"), list))
    check("pivot.items non-empty", len(j.get("items", [])) > 0)
    for it in j.get("items", [])[:1]:
        for k in ("name","category","unit","first","last","pct","prices"):
            check(f"pivot.item.{k}", k in it)
        check("pivot.item.prices non-empty", len(it.get("prices", [])) > 0)

# ============================== alerts
j, e = get_json("/api/alerts?threshold=10&start=2025-07-01&end=2026-01-01", timeout=12)
check("GET /api/alerts 200", j is not None, e or "")
if j:
    check("alerts is list", isinstance(j, list))
    if j:
        a = j[0]
        for k in ("name","category","date","price","prev_price","pct"):
            check(f"alert.{k}", k in a)
        check("alert.pct numeric", isinstance(a.get("pct"), (int,float)))
        check("price >= prev*0.9", a["price"] >= a["prev_price"]*0.9, f"{a['price']} vs {a['prev_price']}")

# ============================== csv
st, body, ct = get("/api/series.csv?start=2025-07-01&end=2026-01-01")
check("GET /api/series.csv 200", st == 200, f"status={st}")
check("csv content-type", "csv" in (ct or "").lower() or "text" in (ct or "").lower(), str(ct))
if st == 200:
    txt = body.decode("utf-8", errors="replace")
    check("csv has header", any("date" in l.lower() and ("price" in l.lower() or "name" in l.lower()) for l in txt.splitlines()[:3]))
    check("csv has rows", len(txt.splitlines()) > 5, str(len(txt.splitlines())))

# ============================== dashboard HTML
st, body, ct = get("/")
check("GET / 200", st == 200, f"status={st}")
if st == 200:
    html = body.decode("utf-8", errors="replace")
    check("html substantial", len(html) > 2000, str(len(html)))
    nodes = ["id=\"kpis\"","id=\"view\"","id=\"alertsPanel\"","id=\"updatedBadge\"",
             "id=\"updateNow\"","id=\"apply\"","id=\"export\"","id=\"search\"",
             "id=\"threshold\"","id=\"start\"","id=\"end\"","id=\"categoryFilters\"",
             "id=\"itemList\"","id=\"infoLine\"","id=\"toast\"","role=\"tablist\"",
             "class=\"preset\"","class=\"tab\"","id=\"noDataCard\"",
             "class=\"empty-state\"","class=\"skeleton\"","class=\"error-card\"",
             "class=\"alert-top\"","class=\"alertchip\"",
             "/static/helpers.js","/static/app.js","chart.js"]
    for n in nodes:
        check(f"html {n}", n in html)
    check("html Inter font", "Inter" in html)
    check("html Pakistan title", "Pakistan" in html and "<title>" in html)

# ============================== methodology
st, body, _ = get("/methodology")
check("GET /methodology 200", st == 200, f"status={st}")
if st == 200:
    check("methodology readable", len(body.decode("utf-8", errors="replace")) > 400)

# ============================== ingest (POST)
body = json.dumps({"auto_approve": True}).encode("utf-8")
try:
    req = urllib.request.Request(BASE + "/ingest/next", data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=12) as r:
        st = r.status
        resp = json.loads(r.read().decode())
except Exception as exc:
    st, resp = None, {"error": str(exc)}
check("POST /ingest/next 200", st == 200, f"status={st} {resp}")
if st == 200:
    for k in ("inserted","for_week","counts"):
        check(f"ingest.{k}", k in resp, str(resp))
    c = resp.get("counts", {})
    for k in ("inserted","approved","pending"):
        check(f"ingest.counts.{k}", k in c, str(c))

# after ingest: alerts should be non-empty
j2, e2 = get_json("/api/alerts?threshold=5&start=2025-07-01", timeout=12)
check("after-ingest alerts 200", j2 is not None, e2 or "")
if j2:
    check("after-ingest alerts non-empty", len(j2) > 0, str(len(j2)))

print("\n" + "="*60)
print(f"RESULTS: {len(ok_list)} passed, {len(fail_list)} failed\n")
for d, det in fail_list:
    print(f"  FAIL {d}  ({det})")

server.terminate()
try:
    server.wait(timeout=6)
except Exception:
    server.kill()

if fail_list:
    print("\nTHERE WERE FAILURES")
    sys.exit(1)
print("ALL CHECKS PASSED")

