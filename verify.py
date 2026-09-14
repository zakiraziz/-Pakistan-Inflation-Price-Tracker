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

# ============================== BOOT
server = boot()
if server is None:
    print("SERVER DID NOT START"); sys.exit(1)
print("Server ready.\n"); time.sleep(0.5)

# ============================== /api/items
d, e = get_json("/api/items")
check("GET /api/items 200", d is not None, e or "")
if d:
    check("items: count==11", len(d)==11, str(len(d)))
    ids = sorted(i["id"] for i in d)
    check("items: ids 1..11", ids==list(range(1,12)), str(ids))
    req = {"id","name","category","unit"}
    check("items: every row has id/name/category/unit",
          all(req <= set(r.keys()) for r in d))
    names = [r["name"] for r in d]
    check("items includes Wheat flour", any("Wheat" in n for n in names))
    check("items includes Sugar", any("Sugar" in n for n in names))

# ============================== /api/series
qs = urllib.parse.urlencode({"start":"2025-07-01","end":"2026-01-01","items":"1,2"})
d, e = get_json(f"/api/series?{qs}")
check("GET /api/series 200", d is not None, e or "")
if d:
    check("series: list", isinstance(d, list))
    check("series: has rows", len(d)>0)
    check("series: name/date/price", all({"name","date","price"}<=set(r.keys()) for r in d))
    check("series: price numeric", all(isinstance(r["price"],(int,float)) for r in d))

# ============================== /api/index
d, e = get_json("/api/index?start=2025-07-01&end=2026-01-01")
check("GET /api/index 200", d is not None, e or "")
if d:
    check("index: list", isinstance(d, list))
    check("index: non-empty", len(d)>0)
    check("index: first==100", d[0]["index"]==100)
    check("index: last>100", d[-1]["index"]>100)
    check("index: has date", "date" in d[0])

# ============================== /api/metrics
d, e = get_json("/api/metrics?start=2025-07-01&end=2026-01-01")
check("GET /api/metrics 200", d is not None, e or "")
if d:
    for k in ["count","weeks","basket_pct","start_total","end_total",
              "first_date","last_date","biggest_riser","biggest_faller"]:
        check(f"metrics: has {k}", k in d)
    check("metrics: basket_pct!=0", d.get("basket_pct",0)!=0)
    check("metrics: riser has name/pct", d.get("biggest_riser") and {"name","pct"}<=set(d["biggest_riser"].keys()))
    check("metrics: faller has name/pct", d.get("biggest_faller") and {"name","pct"}<=set(d["biggest_faller"].keys()))

# ============================== /api/pivot
d, e = get_json("/api/pivot?start=2025-07-01&end=2026-01-01")
check("GET /api/pivot 200", d is not None, e or "")
if d:
    check("pivot: dates list", isinstance(d.get("dates"), list))
    check("pivot: items list", isinstance(d.get("items"), list))
    check("pivot: items non-empty", len(d.get("items",[]))>0)
    if d["items"]:
        it = d["items"][0]
        for f in ["name","category","unit","first","last","pct","prices"]:
            check(f"pivot.item: has {f}", f in it)
        check("pivot.item: prices list", isinstance(it.get("prices"), list))

    d, e = get_json("/api/pivot?start=2025-07-01&end=2026-01-01&compare=true")
    check("GET /api/pivot?compare=true 200", d is not None, e or "")
    if d and d["items"]:
        check("pivot compare: delta field", "delta" in d["items"][0])

# ============================== /api/alerts
for thr in (5,10):
    d, e = get_json(f"/api/alerts?threshold={thr}&start=2025-07-01&end=2026-01-01")
    check(f"GET /api/alerts?threshold={thr} 200", d is not None, e or "")
    if d is not None:
        check(f"alerts thr{thr}: list", isinstance(d, list))
        if d:
            a = d[0]
            for f in ["name","category","date","price","prev_price","pct"]:
                check(f"alert row: has {f}", f in a)

# ============================== dashboard HTML
st, body, ct = get("/")
check("GET / 200", st==200, f"status={st}")
html = body.decode("utf-8", errors="replace")
hl = html.lower()
htags = [
    ("title mentions Pakistan", "pakistan" in hl),
    ("uses Inter font", "Inter" in html),
    ("loads Chart.js", "chart.js" in html or "Chart" in html),
    ("refs /static/style.css", "/static/style.css" in html),
    ("refs /static/helpers.js", "/static/helpers.js" in html),
    ("refs /static/app.js", "/static/app.js" in html),
    ("links /methodology", "/methodology" in html),
]
for desc, ok in htags:
    check("HTML: "+desc, ok)
for nid in ["updatedBadge","updateNow","kpis","view","alertsPanel",
            "apply","export","search","threshold","start","end",
            "categoryFilters","itemList","infoLine","toast"]:
    check(f"HTML: has el#{nid}", f'id="{nid}"' in html)
check("HTML: tablist", 'role="tablist"' in html)
check("HTML: Trends tab", 'data-view="trends"' in html)
check("HTML: Compare tab", 'data-view="compare"' in html)
check("HTML: Data tab", 'data-view="data"' in html)
for months in ("3","6","12"):
    check(f"HTML: {months}M preset", f'data-months="{months}"' in html)
check("HTML: All preset", 'data-all="1"' in html)
for icon in ("M21 15v4a2 2","M21 12a9 9 0 1 1-2.64","M22 7l-8.5 8.5"):
    check(f"HTML: SVG icon {icon[:12]}…", icon in html)

# ============================== /methodology
st, body, ct = get("/methodology")
check("GET /methodology 200", st==200, f"status={st}")
if st==200:
    html = body.decode("utf-8", errors="replace")
    check("methodology: substantive (>400 chars)", len(html)>400)

# ============================== POST /ingest/next
payload = json.dumps({"auto_approve": True}).encode("utf-8")
req = urllib.request.Request(BASE+"/ingest/next", data=payload, method="POST",
    headers={"Content-Type":"application/json"})
try:
    with urllib.request.urlopen(req, timeout=10) as r:
        st = r.status; resp = json.loads(r.read().decode())
except Exception as e:
    st, resp = None, {"error": str(e)}
check("POST /ingest/next 200", st==200, f"status={st} resp={resp}")
if st==200:
    check("ingest: has inserted", "inserted" in resp)
    check("ingest: has for_week", "for_week" in resp)
    check("ingest: has counts", "counts" in resp)

# ============================== CSS coverage
css_path = BASE_DIR / "static" / "style.css"
check("style.css exists", css_path.exists())
if css_path.exists():
    css = css_path.read_text(encoding="utf-8")
    rules = set()
    for line in css.splitlines():
        s = line.strip()
        if s.startswith(".") and not s.startswith("/*") and "{" in s:
            rules.add(s.split("{")[0].split(":")[0].strip())
    css_vars = [l.strip() for l in css.splitlines() if l.strip().startswith("--")]
    varset = set()
    for v in css_vars:
        name = v.split(":")[0].strip()
        if name.startswith("--"):
            varset.add(name)
    expected_rules = [
        ".page",".hero",".logo",".brand",".sub",".hero-actions",

# ============================== shutdown + report
server.terminate()
try:
    server.wait(timeout=5)
except Exception:
    server.kill()
time.sleep(0.5)

print("\n" + "="*62)
print(f"  PASSED: {len(ok_list)}    FAILED: {len(fail_list)}")
print("="*62)
if fail_list:
    print("\nFailed checks:\n")
    for desc, detail in fail_list:
        print(f"  ✗  {desc}" + (f"  ({detail})" if detail else ""))
    sys.exit(1)
print("  ✔  EVERYTHING VERIFIED — frontend ↔ backend ↔ CSS all aligned.")
sys.exit(0)

        ".btn",".btn:hover",".btn:disabled",".btn-ghost",".btn-ghost:hover",
        ".kpi",".kpi:hover",".kpi-label",".kpi-value",".kpi-value.up",".kpi-value.down",".kpi-sub",
        ".info",
        ".tab",".tab.on",".tab.sel",".tab:hover",".tab:focus-visible",
        ".preset",".preset.on",".preset:hover",".preset:focus-visible",
        ".range",".thr",".grow-in",".grow-in:focus-visible",".num",".dash",".row2",
        ".card-line",".filters",".category-filters",".cat-filter",".cat-filter.on",
        ".cat-filter:hover",".cat-filter:focus-visible",".cat-filter .dot",
        ".item-list",".item",".item.selected",".item:hover",".item:focus-visible",
        ".item input",".item input:checked + .row",
        ".state",".state .icon",".state .title",".state p",
        ".skeleton",".skeleton::after",".sk-card",".sk-line",".sk-block",
        ".alerts",".alerts h2",".alerts .pill",".alert-top",".alert-top .icon",
        ".alert-chip",".alert-chip:hover",".alert-chip .al-name",".alert-chip .al-cat",
        ".alert-chip .al-date",".alert-chip .al-price",".alert-chip .al-pct",
        ".none",".errpage",".toast",".toast.show",
        "::-webkit-scrollbar","::-webkit-scrollbar-thumb","::-webkit-scrollbar-track",
        "@media (max-width: 720px)",":focus-visible",
    ]
    expected_vars = [
        "--s1","--s2","--s3","--s4","--s5","--s6","--s7",
        "--fs-xs","--fs-sm","--fs-md","--fs-lg","--fs-xl","--fs-2xl","--fs-3xl",
        "--fw-400","--fw-500","--fw-600","--fw-700",
        "--bg","--surface","--surface-2","--border","--border-strong",
        "--ink","--muted","--faint","--accent","--accent-strong","--accent-soft",
        "--up","--down","--danger-soft",
        "--r-sm","--r-md","--r-lg","--shadow","--t",
    ]
    for r in expected_rules:
        check(f"CSS rule: {r}", r in rules or r in css)
    for v in expected_vars:
        check(f"CSS var: {v}", v in varset)
    # colorblind-safe palette check
    check("CSS: --up and --down both defined (colorblind-safe)", "--up" in varset and "--down" in varset)

        check(f"alerts thr{thr}: list", isinstance(d, list))
        if d:
            a = d[0]
            for f in ["name","category","date","price","prev_price","pct"]:
                check(f"alert row: has {f}", f in a)

# ============================== /api/series.csv
st, body, ct = get("/api/series.csv?start=2025-07-01&end=2026-01-01")
check("GET /api/series.csv 200", st==200, f"status={st}")
check("series.csv: Content-Type csv", "csv" in (ct or "").lower(), f"ct={ct}")
if st==200:
    lines = [l for l in body.decode("utf-8").splitlines() if l.strip()]
    check("series.csv: has header", len(lines)>=1 and "date" in lines[0].lower())
    check("series.csv: has data rows", len(lines)>1)


# ============================== healthz / readyz
d, e = get_json("/healthz")
check("GET /healthz 200", d is not None, e or "")
if d:
    check("healthz: status==ok", d.get("status")=="ok")
    check("healthz: items==11", d.get("items")==11)
    check("healthz: approved_points>0", (d.get("approved_points") or 0)>0)
    check("healthz: latest_date present", bool(d.get("latest_date")))
d, e = get_json("/readyz")
check("GET /readyz 200", d is not None, e or "")
if d:
    check("readyz: status==ready", d.get("status")=="ready")
