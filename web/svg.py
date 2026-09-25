"""
web/svg.py
----------
Dependency-free SVG charts, rendered on the server.

Why hand-rolled SVG instead of a charting library on these pages:

* **It always renders.** The dashboard pulls Chart.js from a CDN; if that CDN
  is blocked the chart area stays empty. A server-rendered SVG cannot fail.
* **No first-paint flash.** The markup arrives with the page.
* **Accessible and printable.** Each chart is an ``img``-role SVG with text
  labels, so screen readers and Ctrl-P both work.

Colours come from the Okabe-Ito colorblind-safe qualitative palette.
"""

from __future__ import annotations

import html

PALETTE = [
    "#0072b2",  # blue
    "#d55e00",  # vermillion
    "#009e73",  # bluish green
    "#cc79a7",  # reddish purple
    "#e69f00",  # orange
    "#56b4e9",  # sky blue
    "#8c6d31",  # brown
    "#6a3d9a",  # violet
]

UP = "#c2410c"
DOWN = "#009e73"


def color_for(index: int) -> str:
    """Stable series colour by index."""
    return PALETTE[index % len(PALETTE)]


def _bounds(values):
    lo, hi = min(values), max(values)
    if lo == hi:
        pad = abs(lo) * 0.05 or 1.0
        return lo - pad, hi + pad
    pad = (hi - lo) * 0.08
    return lo - pad, hi + pad


def chart(series, dates=None, width=860, height=260, pad_left=62, pad_right=18,
          pad_top=16, pad_bottom=34, label="Price chart", value_prefix="Rs ",
          value_suffix="", y_tick=4):
    """Multi-series line chart.

    ``series`` is an ordered list of ``{"name": str, "values": [float]}`` with
    optional ``"color"``. All value lists must be the same length as ``dates``.
    Returns an SVG string, or a friendly notice when there is nothing to draw.
    """
    series = [s for s in series if s.get("values")]
    if not series:
        return (
            '<p class="chart-empty">No approved observations in this window. '
            "Widen the date range to see a chart.</p>"
        )
    points = [v for s in series for v in s["values"]]
    if len(points) < 2:
        return (
            '<p class="chart-empty">Only one observation in this window - '
            "pick a longer date range to see a trend.</p>"
        )
    dates = list(dates or [])
    lo, hi = _bounds(points)
    span = (hi - lo) or 1.0
    inner_w = width - pad_left - pad_right
    inner_h = height - pad_top - pad_bottom

    def x_at(i, count):
        return pad_left + (inner_w * i / (count - 1) if count > 1 else inner_w / 2)

    def y_at(value):
        return pad_top + inner_h * (1 - (value - lo) / span)

    parts = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{html.escape(label)}" preserveAspectRatio="none">',
        f"<title>{html.escape(label)}</title>",
    ]
    for t in range(y_tick + 1):
        value = hi - span * t / y_tick
        y = y_at(value)
        parts.append(
            f'<line x1="{pad_left}" y1="{y:.1f}" x2="{width - pad_right}" '
            f'y2="{y:.1f}" class="grid"/>'
        )
        parts.append(
            f'<text x="{pad_left - 8}" y="{y + 4:.1f}" class="axis y" '
            f'text-anchor="end">{value:,.0f}</text>'
        )
    for index, s in enumerate(series):
        color = s.get("color") or color_for(index)
        coords = [
            (x_at(i, len(s["values"])), y_at(v)) for i, v in enumerate(s["values"])
        ]
        path = " ".join(
            ("M" if i == 0 else "L") + f"{x:.1f},{y:.1f}"
            for i, (x, y) in enumerate(coords)
        )
        name = html.escape(str(s["name"]))
        parts.append(
            f'<path d="{path}" class="series" fill="none" stroke="{color}" '
            f'stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round">'
            f"<title>{name}</title></path>"
        )
        last_x, last_y = coords[-1]
        caption = f"{name}: {value_prefix}{s['values'][-1]:,.2f}{value_suffix}"
        parts.append(
            f'<circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="3.2" fill="{color}">'
            f"<title>{html.escape(caption)}</title></circle>"
        )
    for i in sorted({0, len(dates) // 2, len(dates) - 1}) if dates else []:
        if i >= len(dates):
            continue
        anchor = "middle"
        if i == 0:
            anchor = "start"
        elif i == len(dates) - 1:
            anchor = "end"
        parts.append(
            f'<text x="{x_at(i, len(dates)):.1f}" y="{height - 12}" '
            f'class="axis x" text-anchor="{anchor}">{html.escape(str(dates[i]))}'
            f"</text>"
        )
    parts.append("</svg>")
    return "".join(parts)


def sparkline(values, width=120, height=28, color="#0072b2", label="trend"):
    """Tiny inline trend line for table rows (never raises)."""
    if not values or len(values) < 2:
        return '<span class="spark-empty" aria-hidden="true">&#8212;</span>'
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    step = width / (len(values) - 1)
    coords = [
        (i * step, height - 2 - (v - lo) / span * (height - 6))
        for i, v in enumerate(values)
    ]
    path = " ".join(
        ("M" if i == 0 else "L") + f"{x:.1f},{y:.1f}"
        for i, (x, y) in enumerate(coords)
    )
    return (
        f'<svg class="spark" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{html.escape(label)}" width="{width}" height="{height}">'
        f'<path d="{path}" fill="none" stroke="{color}" stroke-width="1.6" '
        f'stroke-linejoin="round"></path></svg>'
    )


def bars(rows, width=860, row_height=24, label_w=200, value_suffix="%",
         label="Comparison chart"):
    """Horizontal bar chart: ``rows`` = [(label, value, color)]."""
    if not rows:
        return '<p class="chart-empty">Nothing to compare in this window.</p>'
    peak = max(abs(v) for _, v, _ in rows) or 1.0
    height = row_height * len(rows) + 8
    bar_w = width - label_w - 74
    parts = [
        f'<svg class="chart bars" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{html.escape(label)}"><title>{html.escape(label)}</title>'
    ]
    for i, (name, value, color) in enumerate(rows):
        y = i * row_height + 4
        w = max(2.0, bar_w * abs(value) / peak)
        parts.append(
            f'<text x="{label_w - 8}" y="{y + row_height / 2 + 4:.1f}" '
            f'class="axis bar-label" text-anchor="end">'
            f"{html.escape(str(name))}</text>"
        )
        parts.append(
            f'<rect x="{label_w}" y="{y + 3:.1f}" width="{w:.1f}" '
            f'height="{row_height - 8}" rx="3" fill="{color}"></rect>'
        )
        parts.append(
            f'<text x="{label_w + w + 6:.1f}" y="{y + row_height / 2 + 4:.1f}" '
            f'class="axis bar-value">{value:+,.1f}{value_suffix}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def change_color(value) -> str:
    """Colour for a signed percentage (rises = warm, falls = cool green)."""
    if value is None:
        return "#78877e"
    return UP if value > 0 else (DOWN if value < 0 else "#78877e")
