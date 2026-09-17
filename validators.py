"""
validators.py
-------------
Automated sanity checks for incoming price points.

Every scraped/ingested price is classified before it reaches the public index:
    approved  - passes sanity checks -> shown immediately
    pending   - looks implausible (e.g. a huge week-over-week jump) -> held
                for a human to review/approve, so bad scrapes never poison it
    rejected  - structurally invalid (non-positive / missing price)

Category-specific limits reflect reality: fresh produce (onion, potato)
legitimately swings much more week-to-week than fuel or electricity.
"""

from __future__ import annotations

import db

# Max allowed week-over-week swing (percent) before a point is held for review.
MAX_PCT_JUMP = {
    "Grocery": 20,
    "Fresh produce": 60,
    "Energy": 15,
    "Poultry": 20,
    "Dairy & protein": 18,
}
MAX_PCT_DROP = {
    "Grocery": 25,
    "Fresh produce": 45,
    "Energy": 20,
    "Poultry": 25,
    "Dairy & protein": 22,
}
DEFAULT_JUMP = 20.0
DEFAULT_DROP = 25.0


def category_limits(category: str):
    return (MAX_PCT_JUMP.get(category, DEFAULT_JUMP), MAX_PCT_DROP.get(category, DEFAULT_DROP))


def classify(category: str, price: float, prev_price: float | None = None):
    """Return (status, review_note) for a candidate price point."""
    if price is None or price <= 0:
        return db.STATUS_REJECTED, "empty or non-positive price"

    # no baseline -> nothing to compare; accept within sanity bounds
    if prev_price is None or prev_price <= 0:
        return db.STATUS_APPROVED, ""

    pct = (price - prev_price) / prev_price * 100.0
    max_jump, max_drop = category_limits(category)
    if pct > max_jump:
        return db.STATUS_PENDING, (f"suspicious +{pct:.1f}% week-over-week (max {max_jump:.0f}%)")
    if pct < -max_drop:
        return db.STATUS_PENDING, (f"suspicious {pct:.1f}% week-over-week (min -{max_drop:.0f}%)")
    return db.STATUS_APPROVED, ""
