import subprocess, time, sys, urllib.request, json

proc = subprocess.Popen(
    [sys.executable, 'app.py'],
    cwd='c:/Users/zakir/Desktop/Pakistan Inflation  Price Tracker/-Pakistan-Inflation-Price-Tracker',
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)

print('Starting server...')
for i in range(12):
    time.sleep(1)
    try:
        r = urllib.request.urlopen('http://127.0.0.1:5010/healthz', timeout=2)
        if r.status == 200:
            print('SERVER UP after', i+1, 's')
            break
    except Exception:
        pass
else:
    print('SERVER DID NOT START')
    proc.kill()
    sys.exit(1)

# Fetch dashboard
try:
    with urllib.request.urlopen('http://127.0.0.1:5010/', timeout=5) as r:
        html = r.read().decode('utf-8', errors='replace')
    print('Fetched dashboard, length:', len(html))
except Exception as e:
    print('Failed to fetch dashboard:', e)
    html = ''

print('\n--- HTML element checks ---')
checks = [
    ('kpi-label', 'kpi-label'),
    ('kpi-value', 'kpi-value'),
    ('kpi-sub', 'kpi-sub'),
    ('updatedBadge id', 'updatedBadge'),
    ('toast class', 'toast'),
    ('alert-chip class', 'alert-chip'),
    ('alert-top class', 'alert-top'),
    ('al-name class', 'al-name'),
    ('al-pct class', 'al-pct'),
    ('search input', 'id="search"'),
    ('threshold input', 'id="threshold"'),
    ('updateNow btn', 'id="updateNow"'),
    ('preset buttons', 'preset'),
    ('apply btn', 'id="apply"'),
    ('export btn', 'id="export"'),
    ('categoryFilters', 'categoryFilters'),
    ('itemList', 'itemList'),
    ('infoLine', 'infoLine'),
    ('tablist role', 'tablist'),
    ('Inter font', 'Inter'),
    ('chart.js CDN', 'chart.js'),
    ('helpers.js ref', 'helpers.js'),
    ('app.js ref', 'app.js'),
]

all_ok = True
for name, needle in checks:
    ok = needle in html
    status = 'OK' if ok else 'MISSING'
    if not ok:
        all_ok = False
    print('  ' + status + ': ' + name)

if all_ok:
    print('\nAll element checks passed!')
else:
    print('\nSome checks failed.')

# Healthz check
try:
    r = urllib.request.urlopen('http://127.0.0.1:5010/healthz', timeout=3)
    data = json.loads(r.read().decode())
    print('\nHealthz:')
    print('  status:', data.get('status'))
    print('  approved_points:', data.get('approved_points'))
    print('  latest_date:', data.get('latest_date'))
    print('  pending_points:', data.get('pending_points'))
except Exception as e:
    print('\nHealthz check failed:', e)

proc.terminate()
try:
    proc.wait(timeout=5)
except Exception:
    proc.kill()

print('\nDONE')
