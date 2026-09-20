"""
shot.py (dev helper)
--------------------
Boot the real server, render the dashboard in headless Chrome, verify key
content is present in the DOM, and save a screenshot you can look at.

Requires Google Chrome (found automatically). Only used for visual QA.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]
PORT = 5124
BASE = f"http://127.0.0.1:{PORT}"


def find_chrome():
    for c in CHROME_CANDIDATES:
        if os.path.exists(c):
            return c
    return shutil.which("chrome") or shutil.which("chromium") or shutil.which("msedge")


def wait_server(proc, timeout=20):
    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(BASE + "/", timeout=2)
            return True
        except Exception:
            if proc.poll() is not None:
                return False
            time.sleep(0.4)
    return False


def main():
    chrome = find_chrome()
    if not chrome:
        print("NO_CHROME")
        return 0
    env = dict(os.environ)
    env["PORT"] = str(PORT)
    here = os.path.dirname(os.path.abspath(__file__))
    server = subprocess.Popen(
        [sys.executable, "app.py"],
        cwd=here,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    prof = tempfile.mkdtemp(prefix="chrome_")
    try:
        if not wait_server(server):
            print("SERVER_FAILED_TO_BOOT")
            return 1
        # 1) DOM check via --dump-dom
        dom = subprocess.run(
            [
                chrome,
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                f"--user-data-dir={prof}",
                "--dump-dom",
                BASE + "/",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
        )
        html = dom.stdout
        checks = {
            "basket KPI": "Basket change" in html,
            "items KPI": "Items in view" in html,
            "riser KPI": "Biggest riser" in html,
            "faller KPI": "Biggest faller" in html,
            "info line populated": "items \u00b7" in html,
            "trend canvas": "trendCanvas" in html,
            "item lines built": "Wheat flour (atta)" in html,
            "chart drew (aria-label)": "aria-label" in html,
            # Both states are valid: alert chips when jumps exist, the "No
            # alerts" empty state otherwise (alerts are computed by the ingest
            # job, so a freshly seeded DB legitimately has none).
            "alerts panel rendered": ("alert-chip" in html) or ("No alerts" in html),
            "category chips": "category-chip" in html,
            "search box present": 'id="search"' in html,
            "live pill present": 'id="livePill"' in html,
            "no error state": "Something went wrong" not in html,
            "no leftover skeletons": "skeleton" not in html,
        }
        for k, ok in checks.items():
            print(("OK " if ok else "MISSING ") + k)

        # 2) screenshot. Static mode (``?nolive=1``) is required: the dashboard
        #    otherwise holds an open SSE connection and a headless browser never
        #    reaches "network idle", so --screenshot would hang until timeout.
        shot = os.path.join(here, "dashboard.png")
        try:
            subprocess.run(
                [
                    chrome,
                    "--headless=new",
                    "--disable-gpu",
                    "--no-sandbox",
                    f"--user-data-dir={prof}",
                    "--window-size=1280,1900",
                    "--virtual-time-budget=9000",
                    f"--screenshot={shot}",
                    BASE + "/?nolive=1",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=90,
            )
        except subprocess.TimeoutExpired:
            print(
                "SCREENSHOT_TIMEOUT (Chrome never settled; try a smaller "
                "--virtual-time-budget or check that ?nolive=1 is supported)"
            )
            return 1
        if os.path.exists(shot):
            print(f"SCREENSHOT {shot} ({os.path.getsize(shot)} bytes)")
        else:
            print("SCREENSHOT FAILED (no file written)")
            return 1
        return 0
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except Exception:
            server.kill()
        shutil.rmtree(prof, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
