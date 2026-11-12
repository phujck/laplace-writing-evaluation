"""W0.3 — THE SHARED CLIENT MODEL (store.mjs) + the out-of-model-fetch clause.

store.mjs is the ONE client model: {project, selection, decision}, URL-canonical, with
``fetchJSON`` as the single fetch gateway. THE STANDING CLAUSE that keeps it the one
door: a rebuilt surface must route ALL network through the model — no raw ``fetch(`` /
``XMLHttpRequest`` / ``EventSource(`` lives on a surface, only ``store.fetchJSON``.

The ``REBUILT_SURFACES`` roster starts EMPTY (nothing is rebuilt against the model yet —
surfaces arrive W1+). Each wave that rebuilds a surface against the model appends its
HTML here, and this clause then forbids a raw network call escaping the model in it.
The clause MACHINERY is proven now — run on store.mjs itself (which legitimately holds
the gateway ``fetch``, so the detector must SEE it) and on a planted violation in a tmp
file (never the repo) — so the day the roster grows, the gate already has teeth.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[1]
_SRC = _REPO / "src" / "laplace" / "web"   # the served pages and their static assets
_STATIC = _SRC / "static_shared"

#: THE ROSTER — HTML surfaces rebuilt against the model. W1 landed the dashboard; W2 landed
#: the ARTEFACT surface; W3 lands the CONCEPTRIC surface (the STOCK as graded descent, the
#: AUDIT, the QUARRY); W4 lands the STORYBOARD surface (the board as the acting centre —
#: section cards that expand in place, the rank strip, the residue tray, the coverage
#: inverse, the run panel, the restructure door), built ON the shared model (store.fetchJSON
#: only — its pane behaviour lives in the shared module static_shared/storyboard-panes.mjs,
#: which imports store.mjs). Each later wave appends its own.
REBUILT_SURFACES: list[str] = ["dashboard.html", "artefact.html", "conceptric.html",
                               "storyboard.html", "desk.html",   # W5: THE DESK COCKPIT
                               "pipeline.html",  # W6: THE PIPELINE SURFACE (dials in place)
                               "assets.html"]  # W7: THE ASSET SURFACE (asset CARD + COCKPIT)

#: the raw network idioms a rebuilt surface must NOT contain — every one belongs behind
#: ``store.fetchJSON``. ``fetch\s*\(`` deliberately does NOT match ``fetchJSON(`` (the
#: model's own method), so routing THROUGH the model never trips the clause.
_NETWORK_RE = re.compile(r"\bfetch\s*\(|\bXMLHttpRequest\b|\bEventSource\s*\(")


def _strip_comments(text: str) -> str:
    """Drop JS block/line comments and HTML comments so a mere MENTION of ``fetch(`` in
    prose (a JSDoc contract, a note) never reads as a real call."""
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)     # /* block */
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)    # <!-- html -->
    text = re.sub(r"(?m)//.*$", " ", text)                 # // line
    return text


def raw_network_calls(text: str) -> list[str]:
    """Every raw network idiom in ``text`` (comments already stripped by the caller) —
    the clause detector. Empty ⇒ all network is routed through the model."""
    return _NETWORK_RE.findall(text)


# ── THE CLAUSE over the roster (empty today; teeth proven below) ──────────────

def test_rebuilt_surfaces_route_all_network_through_the_model():
    """Every rostered rebuilt surface makes NO raw network call — all of it routes
    through ``store.fetchJSON``. Vacuously true while the roster is empty; the day a
    surface is appended, a raw ``fetch(`` in it fails HERE."""
    for name in REBUILT_SURFACES:
        p = _SRC / name
        assert p.is_file(), f"rostered surface {name!r} is missing"
        hits = raw_network_calls(_strip_comments(p.read_text(encoding="utf-8")))
        assert not hits, f"{name} makes raw network calls outside the model: {hits}"


#: a rebuilt surface's own <style> is not its only colour source — the visual §6.2
#: relocation (W3+) moved each surface's component atoms + their injected CSS into a
#: companion pane module (static_shared/<name>-panes.mjs, e.g. storyboard-panes.mjs's
#: COMPONENT_CSS template literal, injected via injectStyle()). The one-palette clause
#: (§6.1) binds a surface's WHOLE rendered page, so it must reach that module too.
#: Derived MECHANICALLY from each surface's own `import ... from "/shared/X-panes.mjs"`
#: (not hand-maintained) — a surface with no companion module (its behaviour, if any,
#: stays fully inline) is simply absent, already covered by the <style> grep above.
_COMPANION_MODULE_RE = re.compile(r'from\s*["\']/shared/([\w-]+-panes\.mjs)["\']')


def _companion_module(html: str) -> str | None:
    m = _COMPANION_MODULE_RE.search(html)
    return m.group(1) if m else None


def _color_literals(text: str) -> list[str]:
    """hex/rgb(a)/hsl(a) literals anywhere in ``text`` — the same pragmatic grep the
    <style>-only check uses, reused over a whole module file (its injected CSS lives in
    a JS template literal, not a <style> tag, so there is no tag to scope to)."""
    # an HTML numeric character reference (&#8630; = ↶, a glyph) is not a CSS color — the
    # negative lookbehind on '&' keeps the grep from false-flagging the digits of an entity
    # as a hex literal (a real color like `#c9a96e` is preceded by ':'/space, never '&').
    hexes = re.findall(r"(?<!&)#[0-9a-fA-F]{3,8}\b", text)
    funcs = re.findall(r"\b(?:rgb|rgba|hsl|hsla)\(", text)
    return hexes + funcs


def test_rebuilt_surfaces_obey_the_one_palette_clause():
    """THE ONE-PALETTE CLAUSE (visual conception §6.1, binding from W1): every rebuilt
    surface LINKS hymn.css (the one palette) and declares NO color literals in its own
    <style> — state colors come from hymn variables/component classes, so the palette
    cannot re-fork per surface. Rides this roster, so every wave's surface is bound.

    Extended (visual §6.1 clause extension): the grep also reaches each surface's
    companion pane module — a color literal smuggled into an injected CSS template
    literal (artefact-panes.mjs, conceptric-panes.mjs, storyboard-panes.mjs) forks the
    palette exactly as surely as one in the HTML's own <style>, just one hop later."""
    for name in REBUILT_SURFACES:
        p = _SRC / name
        html = p.read_text(encoding="utf-8")
        assert '/shared/hymn.css' in html, f"{name} must link the one palette sheet"
        for style in re.findall(r"<style[^>]*>(.*?)</style>", html, flags=re.S):
            hits = _color_literals(style)
            assert not hits, \
                f"{name}: color literals leaked into its <style> (§6.1): {hits}"
        module = _companion_module(html)
        if module is None:
            continue
        mod_path = _STATIC / module
        assert mod_path.is_file(), f"{name} imports companion module {module!r} which is missing"
        mod_hits = _color_literals(_strip_comments(mod_path.read_text(encoding="utf-8")))
        assert not mod_hits, \
            f"{module}: color literals leaked into its injected CSS (§6.1): {mod_hits}"
    # the shared runtime module is imported by panes, not by any html — the companion
    # derivation never reaches it, so it is bound here by name (the e23 adversary's
    # finding: its literals were latent to the non-transitive grep).
    for shared in ("engine.mjs",):
        sp = _STATIC / shared
        assert sp.is_file(), f"shared runtime module {shared!r} is missing"
        hits = _color_literals(_strip_comments(sp.read_text(encoding="utf-8")))
        assert not hits, \
            f"{shared}: color literals leaked into its injected CSS (§6.1): {hits}"


def test_the_one_palette_clause_reaches_all_companion_modules():
    """The mechanical derivation actually finds a companion module for every rebuilt
    surface that has one, proving the module-reaching arm of the extension is not
    vacuously skipping everything (a bug that would pass the roster for the wrong
    reason — mirrors ``test_the_clause_sees_the_gateway_in_store_mjs`` below)."""
    found = {name: _companion_module((_SRC / name).read_text(encoding="utf-8"))
             for name in REBUILT_SURFACES}
    assert found["artefact.html"] == "artefact-panes.mjs"
    # the E2+E3 wave repointed /conceptric at the cockpit pane (the engine's first
    # real surface); the retired map pane stays served at /conceptric/map.
    assert found["conceptric.html"] == "cockpit-panes.mjs"
    assert found["storyboard.html"] == "storyboard-panes.mjs"
    # W-DASH lifted the dashboard's brief+inventory pane logic out of dashboard.html into a
    # companion module (dashboard-panes.mjs) so the entry stays a thin brief shell under its
    # 16KB first-paint law — the one-palette clause now legitimately reaches it (its injected
    # CSS is grepped for a smuggled colour literal exactly like the other panes'). The prior
    # "None" (behaviour fully inline) no longer holds and is retired to the new truth.
    assert found["dashboard.html"] == "dashboard-panes.mjs"


def test_the_one_palette_clause_catches_a_planted_module_violation(tmp_path):
    """A planted color literal in a companion module's INJECTED CSS (a COMPONENT_CSS-
    style template literal, not a <style> tag) is caught by the §6.1 clause extension —
    proven in a TMP file, never the repo, mirroring the existing planted-violation idiom
    used for the network clause."""
    bad = tmp_path / "bad-panes.mjs"
    bad.write_text(
        'const COMPONENT_CSS = `\n'
        '.chip{border-left-color:#ff00aa}\n'
        '.warn{background:rgba(255,0,0,.4)}\n'
        '`;\n'
        'export function injectStyle() {}\n', encoding="utf-8")
    hits = _color_literals(_strip_comments(bad.read_text(encoding="utf-8")))
    assert len(hits) >= 2, f"the clause missed a planted module violation: {hits}"


def test_the_clause_sees_the_gateway_in_store_mjs():
    """The one legitimate home of ``fetch`` is store.mjs (the gateway) — the detector
    SEES it, proving the clause actually detects (a no-op detector would pass the roster
    check for the wrong reason)."""
    store_txt = _strip_comments((_STATIC / "store.mjs").read_text(encoding="utf-8"))
    hits = raw_network_calls(store_txt)
    assert hits, "the clause detector failed to see the gateway fetch in store.mjs"
    # …but store.mjs is NOT a rostered surface — the model is exempt by not being on it.
    assert "store.mjs" not in REBUILT_SURFACES


def test_the_clause_catches_a_planted_violation(tmp_path):
    """A planted raw-network surface in a TMP file (never the repo) is caught by the
    clause — fetch, XMLHttpRequest and EventSource all trip it."""
    bad = tmp_path / "bad_surface.html"
    bad.write_text(
        '<script>\n'
        '  const a = fetch("/data").then(r => r.json());\n'
        '  const x = new XMLHttpRequest();\n'
        '  const s = new EventSource("/events");\n'
        '</script>\n', encoding="utf-8")
    hits = raw_network_calls(_strip_comments(bad.read_text(encoding="utf-8")))
    assert len(hits) >= 3, f"the clause missed a planted violation: {hits}"


def test_routing_through_the_model_does_not_trip_the_clause(tmp_path):
    """A surface that routes through the model (``store.fetchJSON``) is CLEAN — the
    clause forbids raw network, not model-routed network (a false positive here would
    make the standing gate unusable)."""
    good = tmp_path / "good_surface.html"
    good.write_text(
        '<script type="module">\n'
        '  import store from "/shared/store.mjs";\n'
        '  const data = await store.fetchJSON("/shared/versions");\n'
        '  store.set({node: "S1"});\n'
        '</script>\n', encoding="utf-8")
    hits = raw_network_calls(_strip_comments(good.read_text(encoding="utf-8")))
    assert not hits, f"model-routed network wrongly tripped the clause: {hits}"


# ── the model is served (the one shared_ui allowlist edit that is mine) ───────

def test_store_mjs_is_allowlisted_and_served():
    """store.mjs is on the shared-asset allowlist and serves as ESM — the smoke page +
    the store_model harness load it from ``/shared/store.mjs``."""
    from laplace.web import shared_ui
    assert "store.mjs" in shared_ui._ASSETS
    st, ctype, body = shared_ui.handle("/shared/store.mjs", {})
    assert st == 200 and "javascript" in ctype
    body = body.decode("utf-8")
    assert "fetchJSON" in body and "export default" in body
