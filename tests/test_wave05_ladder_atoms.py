"""WAVE 0.5 — THE LADDER: the atom grep-floor + the text-law strings denylist.

A cheap mechanical floor that fails when a load-bearing wire is deleted or renamed, and
a denylist unit test over every user-visible string literal the ladder renders (the text
law, §3b: a purposeless string is a build-failing defect). This file's SERVER rows are
owned by the server packet; the CLIENT rows (shell.js / hymn.css / assets-panes) are
appended by the client packet — see the boundary marker below.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SRC = Path(__file__).resolve().parent.parent / "src" / "laplace"
LADDER = SRC / "web" / "ladder.py"
SHARED_UI = SRC / "web" / "shared_ui.py"


# ═══════════════════════════════════════════════════════════════════════════
# SERVER ROWS.
# ═══════════════════════════════════════════════════════════════════════════
def test_shared_ui_serves_ladder():
    src = SHARED_UI.read_text(encoding="utf-8")
    assert 'name == "ladder"' in src, "shared_ui.handle no longer routes /shared/ladder"
    assert "ladder.ladder_payload(" in src, "the route no longer calls ladder_payload"
    # the fence is BEFORE the disk touch: registry.resolve gates the 404.
    route = src[src.index('name == "ladder"'):]
    assert route.index("registry.resolve(corpus)") < route.index("ladder.ladder_payload("), \
        "the corpus must be registry-fenced BEFORE the payload touches disk"


def test_ladder_imports_the_altitude_helpers():
    """The no-drift grep: the ladder resolves its target through the EXTRACTED altitude
    core, never a re-derived copy. Delete the import or a helper call and this fails."""
    src = LADDER.read_text(encoding="utf-8")
    assert "from laplace.engine import altitude" in src
    for helper in ("detect_anchor", "section_nodes", "anchor_node_ids", "owning_section"):
        assert f"altitude.{helper}" in src, f"ladder no longer rides altitude.{helper}"


def test_rung_labels_are_the_fixed_vocabulary():
    from laplace.web import ladder
    assert ladder._RUNG_ORDER == ("concept", "argument", "prose", "evidence",
                                  "judgment", "machine")


# ── the text-law strings denylist over ladder.py's user-visible literals ─────
def _user_visible_literals(path: Path) -> list[str]:
    """Every user-visible string literal in the module: string constants that read as a
    rendered phrase (carry a space), minus docstrings and machine strings (routes, mime
    types, query fragments, single identifiers). The denylist runs over THESE."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                docstrings.add(id(body[0].value))
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            s = node.value
            if " " not in s.strip():                 # a single token (rung id, route, mime)
                continue
            if s.strip().startswith("/") or "://" in s or "?" in s or "&" in s:
                continue                             # a route / query fragment (a real door)
            if re.search(r"%[0-9A-Za-z]", s):        # a %-format / mime string
                continue
            out.append(s)
    return out


def test_ladder_strings_pass_the_denylist():
    literals = _user_visible_literals(LADDER)
    assert literals, "no user-visible ladder strings extracted — the audit found nothing to check"
    # the cheap slop class the denylist catches (the text law's mechanical teeth).
    denylist = [
        "!", "...", "welcome", "awesome", "simply", "just click", "oops",
        "try again", "powered by", "please wait", "great", "easy", "nice work",
    ]
    offenders: list[tuple[str, str]] = []
    for s in literals:
        low = s.lower()
        for bad in denylist:
            if bad in low:
                offenders.append((bad, s))
    assert not offenders, f"slop strings in ladder.py: {offenders}"


def test_ladder_absence_strings_carry_fact_and_fix():
    """Every absence the ladder can render is THE fact + THE fix + THE door (the text law:
    an absence names its fix and stops). Exercised over the honest-empty corpus + an
    unknown target so all absence branches fire."""
    from laplace.web import ladder
    seen = 0
    for corpus, target, hint in (("paper_eigen", "", ""),
                                 ("subset-sum-itqde", "def:does-not-exist", "node")):
        out = ladder.ladder_payload(corpus, target, hint)
        for r in out["rungs"]:
            if r["present"]:
                continue
            a = r["absent"]
            assert a["reason"].strip() and a["fix"].strip() and a["fix_href"].strip()
            assert not a["reason"].endswith("!") and "..." not in a["reason"]
            seen += 1
    assert seen >= 4, "expected several absence branches to fire across the two panels"


# ═══════════════════════════════════════════════════════════════════════════
# CLIENT ROWS — appended by the client packet (shell.js openLadder / hy-ladder /
# aria / capture-phase Escape / export; hymn.css .hy-ladder family zero color
# literals + z 4001; assets-panes reads ?asset=; doors are real <a in renderLadder).
# ═══════════════════════════════════════════════════════════════════════════
STATIC = SRC / "web" / "static_shared"
SHELL = STATIC / "shell.js"
HYMN = STATIC / "hymn.css"
ASSETS_PANES = STATIC / "assets-panes.mjs"
STORE = STATIC / "store.mjs"


def _shell() -> str:
    return SHELL.read_text(encoding="utf-8")


def _ladder_region(src: str) -> str:
    """The shell.js ladder component, fenced by the START/END markers — the strings-audit
    and the doors-are-real-<a> checks run over THIS slice, not the whole file."""
    a = src.index("LADDER-COMPONENT-START")
    b = src.index("LADDER-COMPONENT-END")
    assert a < b, "the ladder component markers are missing or out of order"
    return src[a:b]


def test_shell_exports_openLadder():
    src = _shell()
    assert "function openLadder(" in src, "the openLadder entry is missing"
    assert "openLadder:" in src, "HymnShell no longer exports openLadder"


def test_shell_trigger_is_a_real_button_with_aria_and_caret():
    """The selection token is a real <button aria-haspopup='listbox'> + caret; the project
    token same (kind=project); the scope token stays inert (an is-scope <span>)."""
    src = _shell()
    assert "hy-ctx-ladder" in src and "is-ladder" in src
    assert "aria-haspopup='listbox'" in src, "the trigger must announce the listbox popup"
    assert "hy-ctx-caret" in src, "the trigger must carry a caret"
    assert "data-role='project'" in src and "data-role='sel'" in src, \
        "both the project token and the selection token must be ladder triggers"
    assert "hy-ctx-proj is-scope" in src, "the all-projects scope token must stay inert"


def test_shell_popover_capture_phase_escape_and_aria():
    """The anchored .hy-ladder popover: role=listbox rungs, aria-activedescendant, and a
    CAPTURE-PHASE keydown (3rd arg true) so Escape closes the ladder before the rail."""
    src = _shell()
    region = _ladder_region(src)
    assert "hy-ladder" in region
    assert "role='listbox'" in region, "the rungs container must be a listbox"
    assert "aria-activedescendant" in region, "the active rung must be announced"
    assert 'addEventListener("keydown"' in region and "}, true);" in region, \
        "the ladder keydown must be wired in the CAPTURE phase (3rd arg true)"
    assert "stopPropagation" in region, "Escape must stopPropagation so the rail never sees it"


def test_shell_ladder_lazy_fetch_cache_key_and_live_url():
    src = _shell()
    region = _ladder_region(src)
    assert "AbortController" in region, "the fetch must be abortable (10s timeout)"
    assert "10000" in region, "the timeout must be 10s"
    assert 'kind + "\\0"' in region or '"\\0" + (target' in region, \
        "the cache must be keyed corpus\\0kind\\0target"
    assert "LADDER_CACHE" in region
    assert "new URLSearchParams(location.search)" in region, \
        "the trigger must read the LIVE URL at click (SPA store.set picked up free)"
    assert "refreshSelToken" in src, "the stale-token repair must exist"
    assert 'window.addEventListener("popstate"' in region, \
        "refreshSelToken must fire on popstate"


def test_shell_ladder_doors_are_real_anchors():
    """Honesty: the present-rung door AND the absent-rung fix door are real <a> — a walked
    rung IS a navigation (pagehide → origin stamp → the arrival echo)."""
    region = _ladder_region(_shell())
    assert "<a class='hy-ladder-rung'" in region, "the present-rung door must be a real <a>"
    assert "<a class='hy-ladder-fix'" in region, "the absent-rung fix must be a real <a>"


def test_shell_judgment_fix_fires_the_rule_mouth_not_a_dead_link():
    """The judgment absent-fix RULES the target — it fires the head ✎ (POST /corpus/friction
    via hyRule), never a GET-navigation to /corpus/friction (that route dumps JSON and banks
    nothing). So it renders as a rule button wired to the .rule-chip, not a nav <a>."""
    region = _ladder_region(_shell())
    assert 'r.id === "judgment"' in region, "the judgment fix must be special-cased"
    assert "hy-ladder-fix is-rule" in region, "the judgment fix must be a rule button, not a nav <a>"
    assert ".rule-chip" in region and "chip.click()" in region, \
        "the judgment fix must fire the head ✎, never navigate to the /corpus/friction dump"


def test_shell_ladder_head_banks_ladder_forks_via_friction():
    """D16: the ✎ on the panel head banks ladder:<target> forks through /corpus/friction."""
    region = _ladder_region(_shell())
    assert 'node: "ladder:"' in region, "the head ✎ must bank a ladder:<target> fork node"
    assert "hyRule.attach" in region, "the head must raise the D16 rule mouth"


# ── the shell.js ladder strings denylist (the text law, §3b) ─────────────────
def _js_literals(text: str) -> list[str]:
    """The string-literal CONTENTS in a JS slice, extracted by a comment-aware scanner:
    // and /* */ comments are skipped FIRST (their prose apostrophes and em-dashes are not
    strings), so the denylist runs over rendered strings only — a `!==` operator or a
    comment's "rail's" never masquerades as a slop literal."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
        elif c in "'\"`":
            quote, i, buf = c, i + 1, []
            while i < n:
                ch = text[i]
                if ch == "\\":
                    buf.append(text[i:i + 2]); i += 2; continue
                if ch == quote:
                    i += 1; break
                buf.append(ch); i += 1
            out.append("".join(buf))
        else:
            i += 1
    return out


def test_shell_ladder_strings_pass_the_denylist():
    literals = _js_literals(_ladder_region(_shell()))
    assert literals, "no ladder-component strings extracted — the audit found nothing"
    denylist = ["!", "...", "welcome", "awesome", "simply", "just click", "oops",
                "try again", "powered by", "please wait", "great", "easy", "nice work"]
    offenders: list[tuple[str, str]] = []
    for s in literals:
        low = s.lower()
        for bad in denylist:
            if bad in low:
                offenders.append((bad, s))
    assert not offenders, f"slop strings in the shell.js ladder component: {offenders}"


# ── hymn.css: the .hy-ladder family (zero color literals, z 4001, 375px clamp) ─
def _color_literals(text: str) -> list[str]:
    return (re.findall(r"#[0-9a-fA-F]{3,8}\b", text) +
            re.findall(r"\b(?:rgb|rgba|hsl|hsla)\(", text))


def _ladder_css(css: str) -> str:
    return css[css.index("THE LADDER (W0.5)"):]


def test_hymn_ladder_family_is_var_only():
    css = HYMN.read_text(encoding="utf-8")
    fam = _ladder_css(css)
    assert "z-index:4001" in fam, "the popover must sit at z 4001 (below the rail)"
    lits = _color_literals(fam)
    assert not lits, f"the .hy-ladder family must be vars-only — color literals found: {lits}"
    assert "var(--hy-pop-shadow)" in fam, "the popover depth must ride the shadow var"


def test_hymn_ladder_375_right_edge_clamp():
    fam = _ladder_css(HYMN.read_text(encoding="utf-8"))
    assert "@media" in fam and "max-width:400px" in fam and ".hy-ladder" in fam, \
        "the narrow-viewport clamp (375px thumb test) is missing from the .hy-ladder family"


def test_assets_panes_reads_asset_param_on_boot():
    # W-ASSETS re-homed the ?asset= deep-link behind the one instrument: applyEntry reads the
    # param on boot and openAsset PINS the target (reallocates), superseding the old
    # focusFromParams+scrollIntoView repair (which lived in the pre-engine roster).
    src = ASSETS_PANES.read_text(encoding="utf-8")
    assert "applyEntry" in src, "the ?asset= focus-on-boot entry (applyEntry) is missing"
    assert 'get("asset")' in src or 'field("asset")' in src, "applyEntry must read ?asset="
    assert "openAsset(asset" in src, "the named asset must be opened (pre-pinned) on boot"


def test_store_asset_joins_selection_keys():
    src = STORE.read_text(encoding="utf-8")
    m = re.search(r"const SELECTION_KEYS = \[([^\]]*)\]", src)
    assert m, "SELECTION_KEYS array not found"
    assert '"asset"' in m.group(1), "asset must join SELECTION_KEYS (the evidence-door round-trip)"


def test_store_aisthesis_lens_and_edge_share_url_model_without_default_fetch():
    src = STORE.read_text(encoding="utf-8")
    m = re.search(r"const SELECTION_KEYS = \[([^\]]*)\]", src)
    assert m, "SELECTION_KEYS array not found"
    keys = re.findall(r'"([^"\n]+)"', m.group(1))
    assert keys[-2:] == ["lens", "edge"], \
        "Aisthesis lens and edge must be shared URL selection keys"
    assert 'const inject = opts.inject || ["corpus"]' in src, \
        "lens/edge must never join default fetch injection"
    assert 'for (const k of ["node", "version", "section", "beat", "round"])' in src, \
        "lens/edge must not change firstSelection precedence"
    assert 'EDGE_COMPATIBLE_LENSES = new Set(["evidence-descent"])' in src
    assert "if (!EDGE_COMPATIBLE_LENSES.has(requestedLens)) next.edge = null" in src, \
        "an incompatible lens switch must clear edge inside the same store transition"
