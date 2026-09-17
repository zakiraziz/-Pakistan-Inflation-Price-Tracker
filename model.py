"""
model.py
--------
The single source of truth for the price data generator.

It defines a small "manual basket of goods" of items commonly tracked in
Pakistan's Consumer Price Index (CPI), and a fully deterministic function
that produces a plausible weekly price for any date.

Determinism matters: it makes the data pipeline *reproducible* — re-running
the seed produces byte-for-byte the same series.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------
# tuple layout:
#   (name, category, unit, anchor_pkr_on_start, growth_mult, seasonal_amp, seasonal_phase)
#
# anchor_pkr_on_start : the reference price in PKR on START_DATE (2023-01-01)
# growth_mult         : how much faster/slower this item inflates vs the base path
# seasonal_amp        : amplitude of the seasonal swing (fresh produce is volatile)
# seasonal_phase      : phase offset in radians for when the peak occurs
ITEMS = [
    ("Wheat flour (atta)", "Grocery", "per 20 kg bag", 1950, 1.00, 0.05, 0.00),
    ("Sugar", "Grocery", "per kg", 150, 1.15, 0.05, 1.50),
    ("Basmati rice", "Grocery", "per kg", 210, 1.00, 0.04, 0.80),
    ("Cooking oil", "Grocery", "per 5 L", 2400, 1.05, 0.04, 2.00),
    ("Onion", "Fresh produce", "per kg", 110, 1.00, 0.28, 0.50),
    ("Potato", "Fresh produce", "per kg", 60, 1.00, 0.20, 2.50),
    ("Chicken", "Poultry", "per kg", 560, 1.00, 0.08, 1.00),
    ("Eggs", "Dairy & protein", "per dozen", 340, 1.05, 0.06, 3.00),
    ("Fresh milk", "Dairy & protein", "per litre", 220, 1.02, 0.04, 1.20),
    ("Petrol (super)", "Energy", "per litre", 268, 1.10, 0.04, 0.30),
    ("Electricity", "Energy", "per kWh", 34, 1.25, 0.03, 2.30),
]

START_DATE = date(2023, 1, 1)
END_DATE = date(2026, 6, 30)

# number of days per weekly step
WEEK = 7


# ---------------------------------------------------------------------------
# Core growth path
# ---------------------------------------------------------------------------
def _base_monthly_rate(month_index: int) -> float:
    """Fractional monthly food-inflation rate for the 'month_index'-th month
    since START_DATE.

    This mirrors Pakistan's real trajectory: high food inflation in 2023
    (roughly 25-35% y/y for staples) that decelerates sharply as the baseline
    effects of price shocks pass.
        month_index 0 (Jan 2023) -> ~3.35%/mo  (~40% annualised)
        month_index 24 (Jan 2025) -> ~1.45%/mo (~17% annualised)
        month_index 36+ (2026)    -> ~0.5-0.7%/mo
    """
    return 0.030 * math.exp(-month_index / 28.0) + 0.0032


def _seasonal(month_index: int, amp: float, phase: float) -> float:
    """A deterministic seasonal multiplier (1.0 = no effect)."""
    return 1.0 + amp * math.sin(2.0 * math.pi * (month_index / 12.0) + phase)


def price_at(when: date, item) -> float:
    """Deterministic weekly price (PKR) for an item on ``when``.

    ``item`` is one tuple from ITEMS. The price compounds the monthly growth
    path up to ``when``'s month, then applies a seasonal factor.
    """
    name, category, unit, anchor, growth_mult, amp, phase = item

    months = (when.year - START_DATE.year) * 12 + (when.month - START_DATE.month)

    if months <= 0:
        base = anchor
        k = 0
    else:
        cumulative = 1.0
        for j in range(months):
            cumulative *= 1.0 + _base_monthly_rate(j) * growth_mult
        base = anchor * cumulative
        k = months

    return round(base * _seasonal(k, amp, phase), 2)


def weekly_dates(start: date = START_DATE, end: date = END_DATE):
    """Yield every 7 days from ``start`` up to and including ``end``."""
    d = start
    while d <= end:
        yield d
        d += timedelta(days=WEEK)


def index_by_name() -> dict:
    """Map item name -> ITEMS tuple (handy for the API)."""
    return {it[0]: it for it in ITEMS}
