"""Scratch: numbered dump of app.py for inspection."""
import io

lines = open("app.py", encoding="utf-8").read().splitlines()
with io.open("_app_dump.txt", "w", encoding="utf-8") as fh:
    for i, line in enumerate(lines, 1):
        fh.write(f"{i:>4}| {line}\n")
print("wrote", len(lines), "lines")
