"""Scratch: dump every Flask route in app.py (and its decorators) for inspection."""
import re

src = open("app.py", encoding="utf-8").read()
lines = src.splitlines()
for i, line in enumerate(lines, 1):
    s = line.strip()
    if s.startswith("@app.route") or s.startswith("@app.errorhandler") or s.startswith("@limiter.limit"):
        print(f"{i:>4}: {s}")
