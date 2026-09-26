"""Scratch: numbered dump of app.py for inspection."""

with open("app.py", encoding="utf-8") as fh:
    lines = fh.read().splitlines()

with open("_app_dump.txt", "w", encoding="utf-8") as fh:
    for i, line in enumerate(lines, 1):
        fh.write(f"{i:>4}| {line}\n")
print("wrote", len(lines), "lines")
