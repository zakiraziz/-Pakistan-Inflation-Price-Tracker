"""
analyze.py
----------
Compute headline numbers from the seeded database. These are used to write an
accurate, data-grounded economics explainer.

Usage:
    python analyze.py
"""

from __future__ import annotations

import db


def main():
    con = db.connect()
    items = db.get_items(con)

    total_start = 0.0
    total_end = 0.0
    n = len(items)
    lines = []
    for r in items:
        pxs = con.execute(
            "SELECT price FROM prices WHERE item_id = ? ORDER BY date", (r["id"],)
        ).fetchall()
        first = pxs[0]["price"]
        last = pxs[-1]["price"]
        total_start += first
        total_end += last
        pct = (last - first) / first * 100
        lines.append((r["name"], r["category"], first, last, pct))

    years = 3.5
    basket_pct = (total_end - total_start) / total_start * 100
    annual = ((total_end / total_start) ** (1 / years) - 1) * 100

    print(f"items tracked      : {n}")
    print(f"basket start total : Rs {total_start:.2f}")
    print(f"basket end total   : Rs {total_end:.2f}")
    print(f"overall basket pct : {basket_pct:.1f}% over ~{years} yrs")
    print(f"avg annualised     : {annual:.1f}% p.a.")
    print()
    print("per item (first -> latest):")
    for name, cat, first_p, last_p, pct in lines:
        print(f"  {name:<22} {cat:<16} {first_p:>8.2f} -> {last_p:>8.2f}  ({pct:+.1f}%)")
    con.close()


if __name__ == "__main__":
    main()
