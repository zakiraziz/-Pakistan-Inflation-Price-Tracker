"""Generate verify.py to avoid PowerShell quoting issues."""
from pathlib import Path

parts: list[str] = []

parts.append('"""Verify the Pakistan Inflation / Price Tracker.\n'
             '\n'
             'Boots the Flask server, hits every API and HTML endpoint over HTTP,\n'
             'checks the dashboard DOM for the elements app.js expects, and reports PASS/FAIL.\n'
             'Run with:  python verify.py\n'
             '"""')

parts.append("import builtins")
parts.append("import json")
parts.append("import os")
parts.append("import subprocess")
parts.append("import sys")
parts.append("import time")
parts.append("import urllib.parse")
parts.append("import urllib.request")
parts.append("from pathlib import Path")

parts.append("")
parts.append("BASE_DIR = Path(__file__).resolve().parent")
parts.append('BASE_URL = "http://127.0.0.1:5010"')
parts.append("")
parts.append("_PASS = 0")
parts.append("_FAIL = 0")
parts.append("_FAIL_LIST: list[tuple[str, str]] = []")
parts.append("")
parts.append("")
parts.append("def ok(desc: str, cond: bool, note: str = \"\"):")
parts.append("    global _PASS, _FAIL")
parts.append("    if cond:")
parts.append("        _PASS += 1")
parts.append("        real_print(f\"  OK   {desc}\")")
parts.append("    else:")
parts.append("        _FAIL += 1")
parts.append("        _FAIL_LIST.append((desc, note))")
parts.append("        real_print(f\"  FAIL {desc}\" + (f\"  :: {note}\" if note else \"\"))")
parts.append("")
parts.append("")
parts.append("def get(path: str, timeout: int = 8):")
parts.append("    try:")
parts.append("        with urllib.request.urlopen(BASE_URL + path, timeout=timeout) as r:")
parts.append("            return r.status, r.read(), r.headers.get('Content-Type', '')")
parts.append("    except Exception as exc:  # noqa: BLE001")
parts.append("        return None, str(exc).encode(), ''")
parts.append("")
parts.append("")
parts.append("def get_json(path: str, timeout: int = 8):")
parts.append("    status, raw, _ = get(path, timeout)")
parts.append("    if status != 200:")
parts.append("        return None, f'status={status}'")
parts.append("    try:")
parts.append("        return json.loads(raw.decode('utf-8')), None")
parts.append("    except Exception as exc:")
parts.append("        return None, f'json:{exc}'")
parts.append("")
parts.append("")
parts.append("def boot_server(timeout: int = 30):")
parts.append("    proc = subprocess.Popen(")
parts.append("        [sys.executable, str(BASE_DIR / 'app.py')],")
parts.append("        cwd=str(BASE_DIR),")
parts.append("        stdout=subprocess.DEVNULL,")
parts.append("        stderr=subprocess.DEVNULL,")
parts.append("        env={**os.environ, 'FLASK_DEBUG': '0'},")
parts.append("    )")
parts.append("    deadline = time.time() + timeout")
parts.append("    while time.time() < deadline:")
parts.append("        time.sleep(1)")
parts.append("        if proc.poll() is not None:")
parts.append("            return None")
parts.append("        try:")
parts.append("            if get('/healthz', timeout=2)[0] == 200:")
parts.append("                return proc")
parts.append("        except Exception:")
parts.append("            pass")
parts.append("    proc.kill()")
parts.append("    try:")
parts.append("        proc.wait(timeout=5)")
parts.append("    except Exception:")
parts.append("        pass")
parts.append("    return None")
parts.append("")
parts.append("")
parts.append("# =========================================================================")
parts.append("#  MAIN")
parts.append("# =========================================================================")
parts.append("_LOG = BASE_DIR / 'verify_results.txt'")
parts.append("_logfh = open(str(_LOG), 'w', encoding='utf-8')")
parts.append("")
parts.append("def log(*a, **k):")
parts.append("    k.setdefault('flush', True)")
parts.append("    s = ' '.join(str(x) for x in a)")
parts.append("    _logfh.write(s + '\\n')")
parts.append("    _logfh.flush()")
parts.append("    real_print(s)")
parts.append("")
parts.append("real_print = builtins.print")
parts.append("builtins.print = log")
parts.append("")
parts.append("server = boot_server()")
parts.append("if server is None:")
parts.append("    log('SERVER DID NOT START'); _logfh.close(); sys.exit(1)")
parts.append("log('Server ready.'); time.sleep(0.5)")
parts.append("")

# ---- helpers for API + HTML checks ----
parts.append("R = '2025-07-01'\n"
             "E = '2026-01-01'\n"
             "def Q(**kw):\n"
             "    return '?' + urllib.parse.urlencode({k: v for k, v in kw.items() if v is not None})\n"
             "\n"
             "def html_get(path):\n"
             "    st, raw, ct = get(path)\n"
             "    if st != 200:\n"
             "        return None, None, f'status={st}'\n"
             "    return raw.decode('utf-8', errors='replace'), ct, None\n"
             "\n"
             "def check_dom(html, ids):\n"
             "    return [(_id, (_id in html and f'id=\"{_id}\"' in html)) for _id in ids]\n"
             "\n"
             "def check_includes(html, needles):\n"
             "    return [(n, (n in html)) for n in needles]\n"
             "\n")

Path('verify.py').write_text('\n'.join(parts), encoding='utf-8')
print('Part A written:', len(parts), 'fragments')
