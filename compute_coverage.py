import os
import subprocess
import sys
import time
import urllib.request

cwd = "c:/Users/zakir/Desktop/Pakistan Inflation  Price Tracker/-Pakistan-Inflation-Price-Tracker"

# Start server
print("Starting server...")
proc = subprocess.Popen(
    [sys.executable, "app.py"], cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)

# Wait for it

server_ready = False
for _ in range(20):
    time.sleep(1)
    try:
        with urllib.request.urlopen("http://127.0.0.1:5010/healthz", timeout=2) as r:
            if r.status == 200:
                server_ready = True
                break
    except Exception:
        pass

if not server_ready:
    print("ERROR: server did not start")
    proc.kill()
    sys.exit(1)

print("Server ready.")

# Run pytest with coverage
os.chdir(cwd)
env = os.environ.copy()
env["FLASK_ENV"] = "production"
cmd = [
    sys.executable,
    "-m",
    "pytest",
    "tests/",
    "-v",
    "--tb=short",
    "--cov=app",
    "--cov=db",
    "--cov=alert",
    "--cov=validators",
    "--cov=ingest",
    "--cov=core",
    "--cov-report=term-missing",
    "--cov-fail-under=80",
]

print("\nRunning pytest with coverage...\n")
p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
print(p.stdout)
if p.stderr:
    print("STDERR:", p.stderr[:2000])
print("Pytest exit code:", p.returncode)

# Kill server
proc.terminate()
try:
    proc.wait(timeout=5)
except Exception:
    proc.kill()

sys.exit(p.returncode)
