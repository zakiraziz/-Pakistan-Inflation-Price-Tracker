"""Scratch: dump every Flask route in app.py (and its decorators) for inspection."""

ROUTE_DECORATORS = ("@app.route", "@app.errorhandler", "@limiter.limit")

with open("app.py", encoding="utf-8") as fh:
    src = fh.read()
lines = src.splitlines()
for i, line in enumerate(lines, 1):
    s = line.strip()
    if s.startswith(ROUTE_DECORATORS):
        print(f"{i:>4}: {s}")
