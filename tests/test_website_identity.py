"""The website-identity pin — his catch made mechanical (2026-07-22 night).

He glanced at one png and spotted a palette that was not his website's. The
route law (test_palette_per_route.py) proves every served page rides hymn.css,
but nothing pinned hymn itself to HIS palette — the sheet could drift to any
scheme and every floor would stay green. This clause closes that hole: the
:root tokens of the one hymn sheet must equal the banked identity below,
byte-for-byte on the hex, or the floor fails before his eye is ever needed.

The banked identity is the author's own front door (gmccaul.co.uk, fetched
live 2026-07-22 and ruled standing): deep-night ground, warm gold as the one
working ink, sky-blue as the judgment voice, Lora/Outfit/JetBrains Mono
vendored. Changing these values is HIS call; a contractor pass that touches
them must arrive with his ruling, not a green suite.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_HYMN = Path(__file__).resolve().parents[1] / "src" / "laplace" / "web" / "static_shared" / "hymn.css"

# the banked identity — his website's own values, exact
_PINNED = {
    "bg": "#0a0e1a",
    "panel": "#111827",
    "ink": "#e8e6e3",
    "ink2": "#9ca3af",
    "dim": "#6b7280",
    "accent": "#c9a96e",
    "gold-light": "#dfc599",
    "keystone": "#7eb8da",
    "bad": "#c0392b",
    "teal": "#a89a7a",
}
_PINNED_FONT_LEADS = {
    "serif": '"Lora"',
    "display": '"Outfit"',
    "mono": '"JetBrains Mono"',
}

_ROOT_RE = re.compile(r":root\s*\{([^}]*)\}", re.S)
_TOKEN_RE = re.compile(r"--([A-Za-z0-9_-]+)\s*:\s*([^;]+?)\s*;")


def _root_tokens() -> dict[str, str]:
    css = _HYMN.read_text(encoding="utf-8")
    out: dict[str, str] = {}
    for block in _ROOT_RE.findall(css):
        for name, val in _TOKEN_RE.findall(block):
            out[name] = re.sub(r"\s+", "", val)
    return out


def test_hymn_carries_his_palette_exactly():
    tokens = _root_tokens()
    wrong = {
        name: (tokens.get(name), want)
        for name, want in _PINNED.items()
        if tokens.get(name, "").lower() != want.lower()
    }
    assert not wrong, (
        "hymn.css has drifted off the banked website identity — "
        + "; ".join(f"--{n} is {got!r}, his site says {want!r}" for n, (got, want) in wrong.items())
        + ". These values are his call; bring his ruling, not an edit."
    )


def test_hymn_leads_with_his_faces():
    tokens = _root_tokens()
    for name, lead in _PINNED_FONT_LEADS.items():
        got = tokens.get(name, "")
        assert got.replace(" ", "").startswith(lead.replace(" ", "")), (
            f"--{name} must lead with {lead} (his site's face); hymn says {got!r}"
        )


def test_fonts_are_vendored_not_cdn():
    css = _HYMN.read_text(encoding="utf-8")
    assert "fonts.googleapis" not in css and "fonts.gstatic" not in css and "use.typekit" not in css, (
        "hymn.css reaches a font CDN — the faces are vendored under /shared/fonts, offline like katex"
    )
    for face in ("lora", "outfit", "jetbrains"):
        assert re.search(rf"url\(/shared/fonts/{face}[^)]*\.woff2\)", css), (
            f"the {face} face must load from the vendored /shared/fonts/ path"
        )
