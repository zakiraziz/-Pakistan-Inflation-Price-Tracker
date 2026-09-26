"""Token parity and colour contrast across the layers that carry the palette.

Three files hold the same colours in three forms and nothing in the app links
them together, so they can drift silently:

* ``static/style.css``  — the source of truth (custom properties)
* ``web/svg.py``        — Python constants for the server-rendered SVG charts
* ``static/helpers.js`` — constants for the Chart.js / sparkline layer

These tests fail when a mirror drifts, and they hold the stylesheet to the
promise written in its own comments: every colour used for *text* clears WCAG AA
(4.5:1) against every surface text can land on, and the fill-only tokens — which
cannot reach 4.5:1 — are never used to colour text.
"""

from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
STYLE_CSS = ROOT / "static" / "style.css"
PAGES_CSS = ROOT / "static" / "pages.css"
HELPERS_JS = ROOT / "static" / "helpers.js"

#: The surfaces text actually sits on: white cards, the page body, tinted chips.
SURFACES = ("--surface", "--bg", "--surface-2")

#: Tokens used to colour text — each must clear 4.5:1 on every surface above.
TEXT_TOKENS = (
    "--ink",
    "--muted",
    "--faint",
    "--accent",
    "--accent-strong",
    "--up",
    "--down-ink",
)

#: Tokens that only fill or stroke a graphic. WCAG 1.4.11 asks 3:1 for non-text,
#: which these meet; they cannot reach 4.5:1, so they must never colour text.
FILL_ONLY_TOKENS = ("--down", "--warn")


def _tokens() -> dict:
    """Every ``--name: #rrggbb`` custom property declared in ``style.css``."""
    css = STYLE_CSS.read_text(encoding="utf-8")
    found: dict = {}
    for name, value in re.findall(r"(--[\w-]+)\s*:\s*(#[0-9a-fA-F]{6})\b", css):
        found.setdefault(name, value.lower())
    return found


def _luminance(colour: str) -> float:
    """WCAG 2.x relative luminance of a ``#rrggbb`` colour."""

    def linear(channel: float) -> float:
        """sRGB channel → linear light (the WCAG transfer function)."""
        return channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4

    channels = [int(colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = [linear(channel) for channel in channels]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(fg: str, bg: str) -> float:
    bright, dark = sorted((_luminance(fg), _luminance(bg)), reverse=True)
    return (bright + 0.05) / (dark + 0.05)


def test_stylesheet_defines_the_tokens_these_tests_assume():
    tokens = _tokens()
    for name in TEXT_TOKENS + FILL_ONLY_TOKENS + SURFACES:
        assert name in tokens, f"{name} is not declared in static/style.css"


def test_svg_constants_mirror_the_stylesheet():
    from web import svg

    tokens = _tokens()
    assert svg.FAINT.lower() == tokens["--faint"]
    assert svg.UP.lower() == tokens["--up"]
    assert svg.DOWN.lower() == tokens["--down"]


def test_helpers_js_constants_mirror_the_stylesheet():
    """The chart layer draws with raw hex, so it can drift without a type error."""
    js = HELPERS_JS.read_text(encoding="utf-8")
    match = re.search(r'var UP = "(#[0-9a-fA-F]{6})", DOWN = "(#[0-9a-fA-F]{6})"', js)
    assert match, "helpers.js no longer declares UP/DOWN as this test reads them"
    tokens = _tokens()
    assert match.group(1).lower() == tokens["--up"]
    assert match.group(2).lower() == tokens["--down"]


@pytest.mark.parametrize("token", TEXT_TOKENS)
def test_text_tokens_clear_aa_on_every_surface(token):
    tokens = _tokens()
    for surface in SURFACES:
        ratio = _contrast(tokens[token], tokens[surface])
        assert ratio >= 4.5, (
            f"{token} on {surface} is {ratio:.2f}:1 — below the 4.5:1 minimum for "
            "normal-size text"
        )


@pytest.mark.parametrize("token", FILL_ONLY_TOKENS)
def test_fill_only_tokens_clear_the_non_text_minimum(token):
    """A bar, dot or series line only needs 3:1 against its backdrop."""
    tokens = _tokens()
    for surface in SURFACES:
        ratio = _contrast(tokens[token], tokens[surface])
        assert ratio >= 3.0, f"{token} on {surface} is {ratio:.2f}:1 — below 3:1"


def _text_colour_tokens(css: str) -> list:
    r"""Custom properties used to colour *text* — a heuristic, not a proof.

    ``(?<![-\w])`` keeps ``border-color:`` / ``background-color:`` out of the match,
    since those are not text colour. Interior whitespace and a var() fallback are
    tolerated. See the blind-spot test below: aliasing the token through another
    custom property defeats any regex and needs a real parser.
    """
    pattern = r"(?<![-\w])color\s*:\s*var\(\s*(--[\w-]+)\s*(?:,[^)]*)?\)"
    return re.findall(pattern, css)


@pytest.mark.parametrize(
    "css",
    [
        "a { color: var(--down); }",
        "a { color:var(--down) }",
        "a { color: var(  --down  ) }",
        "a { color: var(--down, #009e73); }",
    ],
)
def test_text_colour_detector_handles_the_obvious_spellings(css):
    """Pin the heuristic's reach so a refactor cannot quietly weaken the guard."""
    assert _text_colour_tokens(css) == ["--down"]


@pytest.mark.parametrize(
    "css", ["a { border-color: var(--down); }", "a { background-color: var(--down); }"]
)
def test_text_colour_detector_ignores_non_text_colour(css):
    assert _text_colour_tokens(css) == []


def test_text_colour_detector_blind_spot_is_documented():
    """Known limit: routing a fill colour through another token evades the regex.

    Nothing here parses CSS (no tinycss2 dependency), so the guard stays a
    heuristic. If the palette ever grows aliases, replace it with a parser rather
    than extending the pattern.
    """
    aliased = ":root { --kpi-neg: var(--down); } .kpi { color: var(--kpi-neg); }"
    # `--kpi-neg` is what gets detected, and it is not a fill-only token — so the
    # guard below would pass while the text rendered in the 3.0:1 fill green.
    assert _text_colour_tokens(aliased) == ["--kpi-neg"]
    assert [t for t in _text_colour_tokens(aliased) if t in FILL_ONLY_TOKENS] == []


@pytest.mark.parametrize("path", [STYLE_CSS, PAGES_CSS], ids=["style.css", "pages.css"])
def test_no_stylesheet_colours_text_with_a_fill_only_token(path):
    """``color: var(--down)`` was a real bug: 3.4:1 on white. Use --down-ink."""
    used = _text_colour_tokens(path.read_text(encoding="utf-8"))
    offenders = sorted({name for name in used if name in FILL_ONLY_TOKENS})
    assert not offenders, f"{path.name} colours text with {offenders}"


def test_palette_declares_a_light_color_scheme():
    """Light-only palette: without this, a dark-mode OS darkens form controls."""
    css = STYLE_CSS.read_text(encoding="utf-8")
    assert re.search(r"color-scheme:\s*light", css), (
        "static/style.css must declare color-scheme: light — the palette has no "
        "dark mode, and UA widgets would otherwise follow the OS"
    )


@pytest.mark.parametrize("path", [STYLE_CSS, PAGES_CSS], ids=["style.css", "pages.css"])
def test_stylesheets_have_balanced_braces(path):
    """A stray brace silently disables every rule after it in the file.

    This is the only structural check the suite makes. There is no stylelint or
    csstree pass, so a rule that is overridden elsewhere, or a declaration that
    is valid but a no-op, would still go unnoticed.
    """
    css = path.read_text(encoding="utf-8")
    assert css.count("{") == css.count("}"), f"{path.name} has unbalanced braces"


def _flatten(css: str) -> str:
    """Collapse whitespace so a snippet matches however the file is formatted."""
    return re.sub(r"\s+", " ", css)


#: Text meaning "price fell" must use the ink green; the bar representing the same
#: fall keeps the brighter fill green. Forbidding the wrong colour is not the same
#: as requiring the right one — deleting a declaration outright would pass the
#: guard above — so the pairings are pinned explicitly.
DOWN_TEXT_DECLARATIONS = {
    "style.css": (
        ".up { color: var(--up); }",
        ".down { color: var(--down-ink); }",
        ".kpi-value.down { color: var(--down-ink); }",
        "td.chg.down { color: var(--down-ink); }",
        ".catbar-val.down { color: var(--down-ink); }",
        # the bar itself is a graphic, so it keeps the brighter Okabe-Ito green
        ".catbar-fill.down { background: var(--down); }",
    ),
    "pages.css": (
        ".down { color: var(--down-ink); }",
        ".badge.down { color: var(--down-ink);",
    ),
}


@pytest.mark.parametrize("name", sorted(DOWN_TEXT_DECLARATIONS))
def test_down_ink_is_applied_where_text_needs_it(name):
    """Require the right colour, not just forbid the wrong one."""
    css = _flatten((ROOT / "static" / name).read_text(encoding="utf-8"))
    for declaration in DOWN_TEXT_DECLARATIONS[name]:
        assert _flatten(declaration) in css, f"static/{name} lost: {declaration}"
