"""
services/insights.py
--------------------
A transparent, rule-based "what changed and why" engine.

Two principles the pages must never break:

1. **Calculated facts** come straight from the stored data and are labelled as
   such ("calculated from the N weekly observations in this window").
2. **Possible contributing factors** are *category-level context* only. They are
   generic, clearly worded as possibilities, and never presented as a cause
   established by this dataset. No causal claim is invented from a price move.

Adding an AI layer later means adding one more labelled section - the
fact/context separation is already in the data model.
"""

from __future__ import annotations

import db

import services.readmodels as rm

# Category-level context. Deliberately generic and hedged: this is the kind of
# thing an economist would list as *candidate* explanations, not a finding.
CONTEXT_FACTORS = {
    "Fresh produce": [
        "Seasonal supply cycles (harvest vs. off-season availability)",
        "Transport and cold-chain costs between farm and urban market",
        "Weather affecting a specific growing region",
    ],
    "Grocery": [
        "Import prices and exchange-rate pass-through",
        "Global commodity prices for the underlying grain or oil",
        "Retail supply arrangements and stock levels",
    ],
    "Energy": [
        "Government-administered price notifications and levies",
        "International crude or LNG prices",
        "Exchange-rate movement on imported fuel",
    ],
    "Poultry": [
        "Feed (maize/soybean) costs and bird-flu outbreaks",
        "Seasonal demand peaks (weddings, Ramadan, winter)",
    ],
    "Dairy & protein": [
        "Feed costs and seasonal milk yield",
        "Transport/refrigeration costs",
        "Festival and Ramadan demand",
    ],
}

DEFAULT_FACTORS = [
    "General inflation and exchange-rate pass-through",
    "Transport and distribution costs",
    "Market-level supply and demand conditions",
]


def context_for(category: str) -> list:
    """Possible contributing factors for a category (never a proven cause)."""
    return CONTEXT_FACTORS.get(category, DEFAULT_FACTORS)


def _money(value) -> str:
    return f"{value:,.2f}" if value is not None else "-"


def item_insight(view: dict, views: list, threshold: float) -> dict:
    """One narrative card for an item, built only from its calculated stats."""
    pct = view["pct"]
    direction = "increased" if pct >= 0 else "decreased"
    rank = next(i + 1 for i, v in enumerate(views) if v["slug"] == view["slug"])
    facts = [
        f"Current price: Rs {_money(view['last'])} {view['unit']}",
        f"Price at the start of the window: Rs {_money(view['first'])} "
        f"{view['unit']}",
        f"Change over the window: {pct:+.2f}% "
        f"({len(views)}-item basket, {view['weeks']} weekly observations)",
        f"Rank by change: {rank} of {len(views)} tracked items",
        f"Trend over the last 4 weeks vs the previous 4: {view['trend']}",
        f"Weekly volatility (std dev of weekly moves): "
        f"{view['volatility']:.2f}%",
        f"Contribution to the basket move: {view['contribution_pct']:+.2f} "
        f"percentage points",
    ]
    if view.get("last_change_pct") is not None:
        facts.append(
            f"Newest week-over-week move: {view['last_change_pct']:+.2f}%"
        )
    if view["zscore"] is not None:
        facts.append(
            f"Unusualness of that move vs this item's own history: "
            f"z = {view['zscore']:+.2f}"
        )

    notes = []
    if abs(pct) >= threshold:
        notes.append(
            f"This move is at or beyond the alert threshold of "
            f"{threshold:g}% for a single week."
        )
    if view["consecutive"] >= 3:
        notes.append(
            f"Price rose in each of the last {view['consecutive']} weeks "
            f"(a run, not a single spike)."
        )
    if view["trend"] == "Rising" and pct > 0:
        notes.append("Both the window and the recent trend point the same way.")
    if view["trend"] == "Falling" and pct > 0:
        notes.append(
            "The rise happened earlier in the window and has since eased - "
            "the recent trend is falling."
        )

    severity = "high" if abs(pct) >= max(threshold, 5) else (
        "medium" if abs(pct) >= threshold / 2 else "low"
    )
    return {
        "kind": "mover",
        "severity": severity,
        "item": view["name"],
        "slug": view["slug"],
        "category": view["category"],
        "unit": view["unit"],
        "title": f"{view['name']} {direction} {abs(pct):.1f}%",
        "direction": "up" if pct >= 0 else "down",
        "pct": pct,
        "current": view["last"],
        "previous": view["first"],
        "trend": view["trend"],
        "facts": facts,
        "notes": notes,
        "context": context_for(view["category"]),
        "link": f"/item/{view['slug']}",
    }


def basket_insight(views: list) -> dict:
    """The headline narrative: what the basket did and how broad the move was."""
    summary = rm.basket_summary(views)
    if not views:
        return {
            "kind": "basket",
            "severity": "low",
            "title": "No data in this window",
            "facts": [],
            "notes": ["Widen the date range to bring observations back in."],
            "context": [],
            "link": "/data",
        }
    pct = summary["pct"]
    direction = "rose" if pct >= 0 else "fell"
    return {
        "kind": "basket",
        "severity": "high" if abs(pct) >= 15 else ("medium" if abs(pct) >= 5 else "low"),
        "title": f"Basket cost {direction} {abs(pct):.1f}% over the window",
        "direction": "up" if pct >= 0 else "down",
        "pct": pct,
        "facts": [
            f"Basket cost moved from Rs {rm.fmt_money(summary['start_total'])} "
            f"to Rs {rm.fmt_money(summary['end_total'])}",
            f"That is {pct:+.2f}% across {summary['weeks']} weekly observations",
            f"Annualised from weekly data: {summary['annualized']:+.2f}% "
            f"(the same rate carried over a year, not a forecast)",
            f"{summary['sharing_rises']} tracked items rose over the window",
            f"Average weekly volatility across items: {summary['volatility']:.2f}%",
        ],
        "notes": [
            "Equal-weight basket: every item counts the same, so this is a "
            "cost-of-living style measure, not the official CPI.",
            "Annualising is arithmetic on the weeks you selected, not a "
            "prediction of the next twelve months.",
        ],
        "context": [],
        "link": "/methodology",
    }


def breach_insights(views: list, threshold: float) -> list:
    """Items whose newest week-over-week move crossed the threshold."""
    out = []
    for v in views:
        move = v.get("last_change_pct") or 0.0
        if abs(move) >= threshold and len(v["series"]) >= 2:
            direction = "jumped" if move > 0 else "dropped"
            out.append(
                {
                    "kind": "breach",
                    "severity": "high",
                    "item": v["name"],
                    "slug": v["slug"],
                    "unit": v["unit"],
                    "title": f"{v['name']} {direction} {abs(move):.1f}% in one week",
                    "direction": "up" if move > 0 else "down",
                    "pct": move,
                    "facts": [
                        f"Newest observation: Rs {rm.fmt_money(v['last'])} "
                        f"{v['unit']}",
                        f"Previous week: Rs {rm.fmt_money(v['series'][-2])} "
                        f"{v['unit']}",
                        f"One-week move: {move:+.2f}% (threshold {threshold:g}%)",
                    ],
                    "notes": [
                        "Crossing the threshold is a signal to look, not "
                        "proof of a cause."
                    ],
                    "context": context_for(v["category"]),
                    "link": f"/item/{v['slug']}",
                }
            )
    out.sort(key=lambda i: -abs(i["pct"]))
    return out


def unusual_insights(views: list, limit: int = 5) -> list:
    """Moves that are unusual *for that item* (|z| >= 2 on its own history)."""
    out = []
    for v in views:
        z = v.get("zscore")
        if z is not None and abs(z) >= 2:
            move = v.get("last_change_pct") or 0.0
            out.append(
                {
                    "kind": "unusual",
                    "severity": "medium",
                    "item": v["name"],
                    "slug": v["slug"],
                    "unit": v["unit"],
                    "title": f"{v['name']}: unusual week-over-week move",
                    "direction": "up" if move >= 0 else "down",
                    "pct": move,
                    "facts": [
                        f"Newest weekly move: {move:+.2f}%",
                        f"Distance from this item's own average weekly move, in "
                        f"standard deviations: z = {z:+.2f}",
                        f"Typical weekly move for this item: "
                        f"±{v['volatility']:.2f}%",
                    ],
                    "notes": [
                        "Calculated against this item's own history only: "
                        "another item could move as far without being unusual "
                        "for it."
                    ],
                    "context": context_for(v["category"]),
                    "link": f"/item/{v['slug']}",
                }
            )
    out.sort(key=lambda i: -abs(i["pct"]))
    return out[:limit]


def build(con, start: str = "", end: str = "", ids=None, threshold: float = 5.0,
          limit: int = 6) -> dict:
    """Full insight payload: headline, movers, breaches and oddities."""
    views = rm.item_views(con, start, end, ids)
    risers, fallers = rm.top_movers(views, limit)
    return {
        "window": {
            "start": start or (views[0]["dates"][0] if views else ""),
            "end": end or (views[0]["dates"][-1] if views else ""),
            "items": len(views),
            "weeks": max([v["weeks"] for v in views], default=0),
            "threshold": threshold,
        },
        "basket": basket_insight(views),
        "risers": [item_insight(v, views, threshold) for v in risers],
        "fallers": [item_insight(v, views, threshold) for v in fallers],
        "breaches": breach_insights(views, threshold),
        "unusual": unusual_insights(views),
        "method": (
            "Facts are calculated from approved weekly observations in the "
            "selected window. 'Possible contributing factors' are "
            "category-level context and are not established by this dataset."
        ),
    }


def for_item(con, item: dict, start: str = "", end: str = "", threshold: float = 5.0):
    """Insight cards for a single item (used by the drill-down page)."""
    views = rm.item_views(con, start, end, [item["id"]])
    if not views:
        return None
    view = views[0]
    cards = [item_insight(view, views, threshold)]
    cards.extend(breach_insights(views, threshold))
    cards.extend(unusual_insights(views, limit=1))
    return {"view": view, "cards": cards}


def items_without_data(con) -> list:
    """Tracked items that currently have no approved observations at all."""
    missing = []
    for item in rm.all_items(con):
        count = con.execute(
            "SELECT COUNT(*) AS c FROM prices WHERE item_id = ? AND status = ?",
            (item["id"], db.STATUS_APPROVED),
        ).fetchone()["c"]
        if count == 0:
            missing.append(item)
    return missing
