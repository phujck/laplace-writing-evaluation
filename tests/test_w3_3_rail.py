"""W3.3 — THE VERSION RAIL, reachable from /review, /artefact (standing), /analytics.

The stage contract (fail-closed):
  * THE FIRST-PAINT LAW (the W2.4 network idiom): the rail fetches ``/shared/versions``
    on OPEN, NEVER at first paint. The fetch lives ENTIRELY in the shell's ``openRail``
    (the one shared implementation); none of the three surfaces fetches it, and the
    deltas-first ≤16KB first paint on /review is untouched.
  * OPEN => rows render with WORKING deep-links: a round into ``/review`` at the round,
    a release PDF through the ``/projection`` viewer, a snapshot's paths as the detail —
    every constructed href is a LIVE route, never a dead link.
  * EMPTY project => the HONEST empty state, never a spinner-forever: a never-run project
    reads never-run, an emptied ``versions/`` dir reads present-but-empty, a failed read
    reads "unavailable" — and every branch replaces the loading line (no stuck spinner).
  * ONE implementation, THREE consumers: the shared ``.hy-rail-toggle`` idiom raises the
    same rail from /review (tray toggle), /artefact (standing), /analytics (history
    cells deep-link in — F10: consuming, not folding).

Two tiers, the test_w1_1_nav idiom. The STATIC FLOOR (grep/CSS over the source) is the
fail-closed proof and runs everywhere; a NODE tier evaluates the real ``railHref`` deep-
link builder extracted from the shell (node is present); the Chromium tier drives the
real renderer and auto-skips without Playwright.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_STATIC = _ROOT / "src" / "laplace" / "web" / "static_shared"
_SRC = _ROOT / "src" / "laplace"

# W2: review_surface.html consolidated into the artefact surface, which carries a STANDING
# rail (a distinct contract — it fetches versions at first paint by design, tested by the
# W2 parity harness). The LAZY-DRAWER law below covers the two surviving drawer surfaces.
_SURFACES = ["analytics.html"]  # W5: guide.html died; /artefact carries the STANDING rail (below)


def _shell() -> str:
    return (_STATIC / "shell.js").read_text(encoding="utf-8")


def _css() -> str:
    return (_STATIC / "hymn.css").read_text(encoding="utf-8")


def _surface(name: str) -> str:
    return (_SRC / name).read_text(encoding="utf-8")


def _slice(text: str, start_marker: str, end_marker: str) -> str:
    i = text.index(start_marker)
    j = text.index(end_marker, i + len(start_marker))
    return text[i:j]


def _brace_body(text: str, sig: str) -> str:
    """The ``{...}`` body of a function found by its signature (brace-matched)."""
    i = text.index(sig)
    b = text.index("{", i)
    depth, k = 0, b
    while k < len(text):
        c = text[k]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[i:k + 1]
        k += 1
    raise AssertionError(f"unbalanced braces after {sig!r}")


# ---------------------------------------------------------------------------
# 1. THE FIRST-PAINT LAW — the rail fetch is absent at first paint (all three).
# ---------------------------------------------------------------------------

def test_no_surface_fetches_versions_at_first_paint():
    """No surface fetches ``/shared/versions`` itself — the fetch lives only in the
    shell's openRail, so opening any of the three surfaces touches none of it."""
    for name in _SURFACES:
        s = _surface(name)
        assert "/shared/versions" not in s, (
            f"{name} references /shared/versions directly — the rail fetch must live in "
            "the shell (openRail), never on the surface, or first paint can regress")


def test_versions_fetch_is_openrail_only():
    """The ONE ``/shared/versions`` fetch in the shell is inside openRail — NOT in
    build() (which runs at DOMContentLoaded, i.e. first paint)."""
    s = _shell()
    assert s.count('fetch("/shared/versions') == 1, "exactly one versions fetch, in openRail"
    open_body = _brace_body(s, "async function openRail(opts)")
    assert 'fetch("/shared/versions' in open_body, "the versions fetch must be in openRail"
    build_body = _brace_body(s, "async function build()")
    assert "/shared/versions" not in build_body, (
        "build() runs at first paint — it must never touch the versions fetch")


def test_each_surface_raises_the_rail_via_the_shell_on_a_click():
    """Each surface opens the rail through ``HymnShell.openRail`` — wired to a click
    handler, never called at module top level (so the open gesture, not load, fetches)."""
    for name in _SURFACES:
        s = _surface(name)
        assert "HymnShell.openRail" in s or "HymnShell && HymnShell.openRail" in s, (
            f"{name} must raise the shared rail via HymnShell.openRail")
        # the open call sits inside an addEventListener("click", …) — a user gesture
        assert 'addEventListener("click"' in s or "addEventListener('click'" in s, (
            f"{name} must wire openRail to a click, not run it at first paint")


# ---------------------------------------------------------------------------
# 2. OPEN => rows render with WORKING deep-links (the real railHref, node-eval'd).
# ---------------------------------------------------------------------------

_NODE = shutil.which("node")


@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_railhref_builds_live_deeplinks(tmp_path):
    """The REAL deep-link builder (extracted from the shell), W2-consolidated: EVERY kind
    (snapshot / round / release) that carries a viewable artefact (pdf/tex) opens in the ONE
    artefact surface at its revision (?version=<id>) — never the retired /review / /projection;
    a row with no viewable artefact → null (paths-as-detail, not a dead link); no corpus → null."""
    railhref = _brace_body(_shell(), "function railHref(row, c)")
    harness = (
        "const ec = encodeURIComponent;\n"
        + railhref + "\n"
        + "const out = {\n"
        + '  round_no_pdf: railHref({kind:"round", id:"r5", paths:["m/rounds/harnessed/mech_r5.json"]}, "eig"),\n'
        + '  round_no_corpus: railHref({kind:"round", id:"r5", paths:["m/x.pdf"]}, ""),\n'
        + '  release: railHref({kind:"release", id:"b", paths:["m/paper-2026-01-01-r5.pdf"]}, "eig"),\n'
        + '  release_no_pdf: railHref({kind:"release", id:"b", paths:["m/release/finalize.json"]}, "eig"),\n'
        + '  snap_dir: railHref({kind:"snapshot", id:"v1", paths:["m/versions/v1"]}, "eig"),\n'
        + '  snap_tex: railHref({kind:"snapshot", id:"v1", paths:["m/versions/v1/main.tex"]}, "eig"),\n'
        + "};\n"
        + "process.stdout.write(JSON.stringify(out));\n"
    )
    js = tmp_path / "railhref.mjs"
    js.write_text(harness, encoding="utf-8")
    res = subprocess.run([_NODE, str(js)], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout)
    assert out["round_no_pdf"] is None             # a round's evidence json is not viewable → detail
    assert out["round_no_corpus"] is None          # never a corpus=&-empty link
    assert out["release"] == "/artefact?corpus=eig&version=b"
    assert out["release_no_pdf"] is None            # no viewable artefact → paths-as-detail
    assert out["snap_dir"] is None                  # dir-only snapshot → detail, not a dead link
    assert out["snap_tex"] == "/artefact?corpus=eig&version=v1"


def test_deeplink_targets_are_live_scanner_routes():
    """The route the rail deep-links into is REAL: /artefact is dispatched by the scanner
    (a row must never point at a 404). W2: the rail targets the ONE artefact surface."""
    scanner = (_SRC / "web" / "scanner.py").read_text(encoding="utf-8")
    assert 'u.path == "/artefact"' in scanner or 'u.path.startswith("/artefact/")' in scanner


def test_rail_renders_a_grouped_timeline_with_open_links():
    """The rail groups rows snapshot/round/release and renders each with an evidence
    action (an 'open ↗' anchor when it has a live href, else a 'detail' span)."""
    s = _shell()
    groups = _slice(s, "const RAIL_GROUPS = [", "];")
    for kind in ("snapshot", "round", "release"):
        assert f'kind: "{kind}"' in groups, f"the timeline must group {kind}"
    row = _brace_body(s, "function railRowEl(row, c)")
    assert "hy-rail-open" in row and "open ↗" in row, "rows with a route render an open link"
    assert "hy-rail-detail" in row, "rows without a route render an honest detail, not a dead link"
    render = _brace_body(s, "function renderRail(body, payload, c)")
    assert "rows.filter(r => r.kind === g.kind)" in render, "grouped by kind"


# ---------------------------------------------------------------------------
# 3. EMPTY project => the HONEST empty state, never a spinner-forever.
# ---------------------------------------------------------------------------

def test_empty_state_is_honest_and_distinct():
    """renderRail renders the F10 distinction: never-run vs present-but-empty vs a failed
    read — three DISTINCT honest messages, never a fabricated 'no history' it can't back."""
    render = _brace_body(_shell(), "function renderRail(body, payload, c)")
    assert "payload.never_run" in render, "never-run is a rendered branch"
    assert "snaps.present && snaps.empty" in render, "present-but-empty (emptied dir) is distinct"
    assert "unavailable" in render, "a failed/absent read reads 'unavailable', not 'none'"
    # every empty branch writes body.innerHTML — nothing is left as the loading line
    assert render.count("body.innerHTML") >= 3


def test_open_always_replaces_the_loading_line():
    """openRail sets the loading line, then ALWAYS calls renderRail after the fetch
    (success OR failure) — so the spinner is always replaced (never spins forever); and
    a failed read is NOT cached, so it retries on the next open."""
    body = _brace_body(_shell(), "async function openRail(opts)")
    li = body.index("hy-rail-loading")
    rr = body.index("renderRail(body, payload, c)")
    assert li < rr, "the loading line is set before the terminal renderRail"
    # renderRail is called at statement level after the try/catch, not only inside try
    tail = body[body.index("}catch(e){"):]
    assert "renderRail(body, payload, c)" in tail, "renderRail runs after the catch, unconditionally"
    assert "if(payload) RAIL_CACHE[c] = payload" in body, "failures must not cache (retry next open)"


# ---------------------------------------------------------------------------
# 4. ONE implementation, THREE consumers — the shared toggle idiom + the CSS drawer.
# ---------------------------------------------------------------------------

def test_artefact_has_the_standing_rail():
    """W2: the review surface's LAZY drawer folded into the ARTEFACT surface's STANDING
    rail — a distinct, richer contract: the collapsed strip (current version + count) is
    always visible, one click opens the full openable/diffable list, and the rows +
    revision count are rendered from /shared/versions by the shared pane module (through
    store.fetchJSON, at first paint — the standing-rail contract, not the lazy-drawer one)."""
    html = _surface("artefact.html")
    panes = (_STATIC / "artefact-panes.mjs").read_text(encoding="utf-8")
    assert 'id="art-rail-strip"' in html and 'id="art-rail"' in html, "the standing rail skeleton"
    assert "renderRailStrip" in panes and "renderRailFull" in panes, "collapsed strip + full list"
    assert 'store.fetchJSON("/shared/versions")' in panes, "the rail renders shared_ui.versions_join"
    assert "runDiff" in panes, "any two rows diff (text-layer / tex-source)"


# W5: the /guide project-band rail toggle retired with the /guide page. The rail's homes
# are now /review (tray toggle), /artefact (the STANDING rail, test_artefact_has_the_standing_rail
# above), and /analytics (history cross-link, below).


def test_analytics_history_cells_deeplink_in_not_fold():
    """/analytics keeps its own page and cross-links into the rail (F10 — consuming, not
    folding): the round header cells and a 'version history' link open the shared rail,
    the round headers focused at their round."""
    s = _surface("analytics.html")
    assert "an-rail-cell" in s and "an-rail-open" in s
    assert "HymnShell.openRail" in s
    assert 'data-round="r' in s, "round headers carry their round id for a focused deep-link"
    assert "focus:focus" in s, "a round header opens the rail focused at that round"
    # NOT folded: /analytics still serves its own page + its own data endpoint
    assert "/analytics/data" in s


def test_the_rail_is_one_shared_css_idiom():
    """The drawer + the shared toggle button are ONE CSS idiom (hymn.css), hidden at rest
    and shown by .open — one implementation the three surfaces consume."""
    css = _css()
    assert ".hy-rail-toggle" in css, "the shared toggle button style"
    assert ".hy-rail-back" in css and ".hy-rail{" in css, "the scrim + the drawer"
    drawer = _slice(css, ".hy-rail{", "}")
    assert "display:none" in drawer, "the drawer is hidden at rest (lazy — not first paint)"
    assert ".hy-rail.open{display:flex}" in css, ".open reveals it"


def test_shell_js_parses():
    """The edited shell parses — a broken rail would break every surface's shell."""
    if _NODE is None:
        pytest.skip("node not available")
    res = subprocess.run([_NODE, "--check", str(_STATIC / "shell.js")],
                         capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, res.stderr


# ---------------------------------------------------------------------------
# CHROMIUM TIER — the real renderer; auto-skips without Playwright/Chromium.
# ---------------------------------------------------------------------------

from browser_fence import (  # noqa: E402
    CHROME as _CHROME, NO_BROWSER as _NO_BROWSER, SKIP_REASON as _SKIP_REASON)


def _serve():
    from laplace.web import scanner
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), scanner.make_handler())
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


@pytest.mark.skipif(_NO_BROWSER, reason=_SKIP_REASON)
def test_first_paint_law_observed_in_the_real_renderer():
    """The first-paint law as the renderer actually shows it, on BOTH contracts.

    THE RE-FENCE (WO-20260810-w4-2-synctex-family). This test used to load /review
    and assert ZERO /shared/versions requests at first paint. That assertion has been
    false since the W2 consolidation and cannot be made true: /review (and /projection)
    now 301 to /artefact, and the artefact surface carries a STANDING rail that fetches
    versions at first paint BY DESIGN — this module's own header says so. It also
    clicked ``#rv-versions``, a toggle that died with review_surface.html. So the test
    was reading one surface's contract against another surface's law.

    What is observable, and is asserted here:
      * the DRAWER contract on /analytics (the surviving drawer surface, ``_SURFACES``):
        first paint issues NO /shared/versions request — the lazy law, observed rather
        than grepped.
      * the STANDING contract on /review→/artefact: EXACTLY ONE versions fetch at first
        paint (the rail is part of the surface, not a drawer), the rail toggle renders,
        and toggling it opens a rail that is not stuck on the loading line.
    """
    from playwright.sync_api import sync_playwright

    httpd, port = _serve()
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch(executable_path=_CHROME)

            # (a) THE DRAWER SURFACE — nothing at first paint.
            drawer = b.new_page(viewport={"width": 1400, "height": 900})
            dhits: list[str] = []
            drawer.on("request",
                      lambda r: dhits.append(r.url) if "/shared/versions" in r.url else None)
            drawer.goto(f"http://127.0.0.1:{port}/analytics", wait_until="networkidle")
            drawer.wait_for_timeout(400)
            assert not dhits, f"/analytics fetched versions at first paint: {dhits}"

            # (b) THE STANDING SURFACE — exactly one, and the rail is usable.
            pg = b.new_page(viewport={"width": 1400, "height": 900})
            hits: list[str] = []
            pg.on("request",
                  lambda r: hits.append(r.url) if "/shared/versions" in r.url else None)
            pg.goto(f"http://127.0.0.1:{port}/review", wait_until="networkidle")
            pg.wait_for_timeout(800)
            assert pg.url.split("?")[0].endswith("/artefact"), (
                f"/review must consolidate into the artefact surface, got {pg.url}")
            assert len(hits) == 1, (
                f"the standing rail reads versions ONCE at first paint, got {len(hits)}: {hits}")
            btn = pg.query_selector("#art-rail-toggle")
            assert btn is not None, "the standing rail toggle must render"
            btn.click()
            pg.wait_for_timeout(400)
            assert pg.query_selector("#art-main.rail-open") is not None, (
                "the rail must open on click")
            body = pg.inner_text("#art-rail")
            assert "loading version history" not in body, "the rail must not spin forever"
            b.close()
    finally:
        httpd.shutdown()
