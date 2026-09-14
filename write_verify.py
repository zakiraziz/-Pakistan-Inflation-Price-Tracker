"""Write verify.py to disk (avoids PowerShell quoting issues)."""
from pathlib import Path

content = r'''"""End-to-end verification: boot server, hit every route, check CSS coverage."""
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

'''

Path("verify.py").write_text(content, encoding="utf-8")
print("Wrote verify.py stub:", len(content), "bytes")
