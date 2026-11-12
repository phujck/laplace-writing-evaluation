"""Wave 0 — THE UNIVERSAL ATOMS in the shared chrome.

Four atoms built ONCE so every rostered surface inherits them (ARMING_2026-07-15
§1 L1/L2, mocks/REDLINES_2026-07-16 D15/D16):

  L1  the context header (shell.js injectContext + hymn.css .hy-context)
  D15 the arrival echo    (shell.js + store.mjs origin stamp + hymn.css .hy-from)
  L2  the hover family    (hymn.css — one labelled block, the cursor affordance +
                           the one missing hover .dk-chip)
  D16 rule in place       (shell.js hyRule.attach + hymn.css .rule-chip/.rule-cap/
                           .rule-banked, wired to the friction ledger door)

Grep-clause tests in the idiom of test_shared_model.py: the atoms live in source, the
new hymn.css families carry ZERO new color literals (the one-palette law), and the D16
bank targets a REAL POST route (evidence, not a wish).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[1]
_STATIC = _REPO / "src" / "laplace" / "web" / "static_shared"
_SHELL = _STATIC / "shell.js"
_STORE = _STATIC / "store.mjs"
_HYMN = _STATIC / "hymn.css"
_SCANNER = _REPO / "src" / "laplace" / "web" / "scanner.py"


def _strip_js_comments(text: str) -> str:
    """Drop JS block/line comments so a MENTION of an atom in prose never reads as code."""
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"(?m)//.*$", " ", text)
    return text


def _color_literals(text: str) -> list[str]:
    """hex / rgb(a) / hsl(a) literals — the same pragmatic grep test_shared_model uses."""
    return re.findall(r"#[0-9a-fA-F]{3,8}\b", text) + re.findall(r"\b(?:rgb|rgba|hsl|hsla)\(", text)


def _decl_bodies(css: str, selector_re: str) -> list[str]:
    """Every ``{...}`` declaration body whose selector matches ``selector_re``."""
    return re.findall(selector_re + r"[^{}]*\{([^}]*)\}", css)


# ── L1 · the context header atom is in source ────────────────────────────────

def test_shell_carries_the_l1_context_header():
    code = _strip_js_comments(_SHELL.read_text(encoding="utf-8"))
    assert "function injectContext" in code, "the L1 header injection fn is missing"
    assert "hy-context" in code, "the header renders no .hy-context host"
    assert "hy-ctx-surface" in code and "hy-ctx-proj" in code and "hy-ctx-sel" in code, \
        "the header must name surface · project · selection (L1)"
    assert "all projects" in code, "no project in view must render the honest scope (R1)"
    assert 'dataset.l1' in code and '"own"' in code, \
        "the atom must skip a page that hand-authors its own line (data-l1=own)"


# ── D15 · the arrival echo atom is in source (shell + store) ─────────────────

def test_shell_carries_the_d15_arrival_echo():
    code = _strip_js_comments(_SHELL.read_text(encoding="utf-8"))
    assert "function renderEcho" in code, "the echo renderer is missing"
    assert "hy-from" in code and "hy-fromwrap" in code, "the echo renders no .hy-from door"
    assert "hymn.origin" in code, "the shell must read/stamp the origin key"
    assert "readOrigin" in code and "stampOrigin" in code, "origin read/stamp is missing"
    assert "pagehide" in code, "the origin must be stamped on the way out (pagehide)"


def test_store_carries_the_origin_stamp():
    code = _strip_js_comments(_STORE.read_text(encoding="utf-8"))
    assert "stampOrigin" in code and "readOrigin" in code, \
        "store.mjs must own the canonical origin stamp/read (D15)"
    assert "ORIGIN_KEY" in code, "store.mjs must define the shared origin key"
    # the model stays intact — the mechanical bar leans on these
    assert "fetchJSON" in code and "export default" in code


# ── D16 · rule in place is in source, wired to a REAL door ───────────────────

def test_shell_carries_the_d16_rule_in_place():
    code = _strip_js_comments(_SHELL.read_text(encoding="utf-8"))
    assert "hyRule" in code and "attach:" in code, "hyRule.attach is missing"
    assert "rule-chip" in code and "rule-cap" in code and "rule-bank" in code, \
        "the capture (chip · textarea · bank) is missing"
    assert "banked ✓" in code, "a 2xx bank must render banked ✓ <id>"
    # his words are never lost on failure: the error path does NOT clear the textarea
    assert "your words are kept" in code or "ruleMsg(cap" in code, \
        "a failed bank must keep his text"


def test_d16_banks_to_a_real_friction_door():
    """The D16 bank POSTs to /corpus/friction — the ONE sanctioned gate for friction/fork
    records (scanner.py do_POST → corpus_ingest.friction_add): typed, draft-only, never a
    bare append. The payload is friction_add-shaped (kind=fork, owning_layer, node), and it
    carries no author-identity literal (the public-bundle seal denylist must stay quiet)."""
    code = _strip_js_comments(_SHELL.read_text(encoding="utf-8"))
    assert '"/corpus/friction"' in code, "the D16 bank must target the friction door"
    assert '"fork"' in code and "owning_layer" in code, \
        "the bank payload must be friction_add-shaped (kind=fork, owning_layer)"
    assert "gerard" not in code.lower(), \
        "no author-identity literal in shared chrome (export_demo seal denylist)"
    # the door is real — POST-reachable in the scanner, through the sanctioned gate
    scanner = _SCANNER.read_text(encoding="utf-8")
    assert '"/corpus/friction"' in scanner, "/corpus/friction is not a served POST route"
    assert "friction_add" in scanner, "the door does not reach corpus_ingest.friction_add"


# ── the new hymn.css families carry ZERO new color literals (the one-palette law) ──

def test_hymn_atoms_declare_no_color_literals():
    css = _HYMN.read_text(encoding="utf-8")
    families = [
        r"\.hy-context\b", r"\.hy-from\b", r"\.hy-from-x\b", r"\.hy-fromwrap\b",
        r"\.rule-chip\b", r"\.rule-cap\b", r"\.rule-banked\b", r"\.hy-rulable\b",
        r"\.dk-chip:hover",
    ]
    seen = 0
    for sel in families:
        bodies = _decl_bodies(css, sel)
        assert bodies, f"the {sel} family is missing from hymn.css"
        seen += len(bodies)
        for body in bodies:
            lits = _color_literals(body)
            assert not lits, f"{sel} leaked color literals (§6.1 one-palette): {lits}"
    assert seen >= 20, "the atom families under-matched — the grep is not seeing them"


def test_hymn_l2_hover_family_fills_the_gap():
    """L2 · the visible-affordance family single-sources the cursor across the clickable
    classes and fills the ONE clickable that lacked a hover (.dk-chip)."""
    css = _HYMN.read_text(encoding="utf-8")
    assert ".dk-chip:hover" in css, "L2 must add the missing .dk-chip hover state"
    # the cursor family names the clickable component classes in one place
    cursor_block = re.search(r"cursor:pointer\}", css)
    assert cursor_block, "the L2 cursor-affordance family is missing"
    for cls in [".hy-card.is-clickable", ".hy-door", ".dk-card", ".dk-chip",
                ".hy-echip", ".hy-rail-toggle"]:
        assert cls in css, f"the L2 family omits {cls}"


# ── the atoms are SERVED, not just on disk ───────────────────────────────────

def test_atoms_are_served():
    from laplace.web import shared_ui
    st, ctype, body = shared_ui.handle("/shared/shell.js", {})
    assert st == 200 and "javascript" in ctype
    text = body.decode("utf-8")
    assert "injectContext" in text and "hyRule" in text and "renderEcho" in text
    st, ctype, body = shared_ui.handle("/shared/hymn.css", {})
    assert st == 200 and "css" in ctype
    css = body.decode("utf-8")
    assert ".hy-context" in css and ".hy-from" in css and ".rule-chip" in css
