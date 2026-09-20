"""
test_web.py
-----------
Bootstrap the REAL Flask server on a free port, then hit every page and API
route over HTTP and assert they all work. This catches boot errors and runtime
issues that the unit tests miss.

    python test_web.py        (from the project root, after seed.py)
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

import model

N_ITEMS = len(model.ITEMS)

PORT = 5123
BASE = f"http://127.0.0.1:{PORT}"

# routes -> expected HTTP status
ROUTES = {
    "/": 200,
    "/static/style.css": 200,
    "/static/helpers.js": 200,
    "/static/app.js": 200,
    "/static/explainer.html": 200,
    "/api/items": 200,
    "/api/series?start=2026-01-01": 200,
    "/api/series?start=2026-01-01&end=2026-03-01&items=1,2": 200,
    "/api/index?start=2026-01-01": 200,
    "/api/metrics?start=2023-01-01": 200,
    "/api/pivot?start=2023-01-01": 200,
    "/api/pivot?start=2026-01-01&items=1,2,3": 200,
    "/api/inflation?start=2023-01-01": 200,
    "/api/inflation?start=2026-01-01": 200,
    "/api/series.csv?items=1,2": 200,
    "/api/alerts?threshold=20": 200,
    "/api/alerts?threshold=5&start=2026-01-01": 200,
}


def http_get(path, timeout=6):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return r.status, r.read()


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def main():
    env = dict(os.environ)
    env["PORT"] = str(PORT)
    root = os.path.dirname(os.path.abspath(__file__))
    # Werkzeug logs every request. Streaming that into an UNREAD pipe fills the
    # OS pipe buffer (~4KB on Windows) and then deadlocks the server mid-run,
    # so send the access log to a file we can also read if boot fails.
    log_path = os.path.join(root, "test_web_server.log")
    with open(log_path, "w", encoding="utf-8") as server_log:
        proc = subprocess.Popen(
            [sys.executable, "app.py"],
            cwd=root,
            env=env,
            stdout=server_log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            # wait for boot
            start = time.time()
            ready = False
            while time.time() - start < 20:
                try:
                    st, _ = http_get("/", timeout=2)
                    if st == 200:
                        ready = True
                        break
                except Exception:
                    if proc.poll() is not None:
                        break
                    time.sleep(0.4)
            if not ready:
                proc.kill()
                with open(log_path, encoding="utf-8") as fh:
                    raise SystemExit("SERVER FAILED TO BOOT:\n" + fh.read())

            for path, code in ROUTES.items():
                if code == 999:
                    continue
                st, body = http_get(path)
                assert st == code, f"{path} -> {st} (expected {code})"
                print(f"OK {path} -> {st}")

            # dashboard HTML content markers
            _, html = http_get("/")
            html = html.decode("utf-8")
            for marker in [
                "helpers.js",
                "app.js",
                'id="kpis"',
                'id="view"',
                'id="alertsPanel"',
                'id="itemList"',
                'id="categoryFilters"',
                'id="search"',
                'class="tab"',
                'id="updateNow"',
            ]:
                assert marker in html, "missing marker: " + marker
            print("OK dashboard HTML contains all key UI elements")

            # JSON validity + basic shape of a few endpoints
            _, items = http_get("/api/items")
            data = json.loads(items)
            assert len(data) == N_ITEMS, len(data)
            print(f"OK /api/items -> {len(data)} items")

            _, series = http_get("/api/series?start=2026-01-01")
            sdata = json.loads(series)
            assert sdata and all(k in sdata[0] for k in ("name", "date", "price"))
            print(f"OK /api/series -> {len(sdata)} rows, fields good")

            _, idx = http_get("/api/index?start=2023-01-01")
            idata = json.loads(idx)
            assert idata and idata[0]["index"] == 100.0
            print(f"OK /api/index -> starts at 100, ends at {idata[-1]['index']}")

            _, met = http_get("/api/metrics?start=2023-01-01")
            m = json.loads(met)
            assert m["count"] == N_ITEMS and m["biggest_riser"]["pct"] > 0
            print(f"OK /api/metrics -> count={m['count']} riser={m['biggest_riser']}")

            _, piv = http_get("/api/pivot?start=2023-01-01")
            p = json.loads(piv)
            assert p["dates"] and len(p["items"]) == N_ITEMS
            assert len(p["items"][0]["prices"]) == len(p["dates"])
            assert p["index"][0] == 100.0
            print(
                f"OK /api/pivot -> {len(p['items'])} items x "
                f"{len(p['dates'])} dates, index 100 to {p['index'][-1]}"
            )

            _, inf = http_get("/api/inflation?start=2023-01-01")
            iv = json.loads(inf)
            assert iv["annualized_pct"] is not None and iv["weeks"] >= 2
            print(
                f"OK /api/inflation -> annualized={iv['annualized_pct']}% " f"YoY={iv['yoy_pct']}%"
            )

            _, csvb = http_get("/api/series.csv?items=1")
            assert csvb.startswith(b"item,date,price")
            print("OK /api/series.csv -> valid header + rows")

            print("\nALL WEB CHECKS PASSED")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()


if __name__ == "__main__":
    main()
