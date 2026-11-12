"""W1.1 — ONE nav, shared by every surface. SUPERSEDED IN PLACE (2026-07-22,
the final authorship): the grouped strip + "…" disclosure died into THE JOURNEY —
the shell renders the process spine (Home · Grow → Shape → Read · Judge →
Machine · Desk) from GET /shared/journey, each stage wearing a live,
server-composed state word, with the former "More" rows living on as DOORS
carried by their stages' hover/focus cards. The laws this file held carry
forward in their new form:

  * the FULL roster stays reachable in ≤2 interactions (a stage is one click;
    a door is hover/focus-open then click) — proven against the journey's own
    coverage law (every roster row appears exactly once as a stage or a door);
  * the 375px law holds — the journey wraps, stage cards are out of flow and
    hidden at rest, and an OPEN card anchors to the right edge;
  * the brand chip is HOME and the Desk stage carries the badge slot;
  * ONE nav — per-page cross-surface nav variants stay dead.

Two tiers, same idiom as before: a STATIC floor (grep-level, fail-closed) and a
Chromium tier that drives the real renderer, auto-skipping without a browser.
"""

from __future__ import annotations

import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_STATIC = Path(__file__).resolve().parents[1] / "src" / "laplace" / "web" / "static_shared"
_SRC = Path(__file__).resolve().parents[1] / "src" / "laplace"


# ---------------------------------------------------------------------------
# STATIC FLOOR — no browser needed; the fail-closed proof of the contract.
# ---------------------------------------------------------------------------


def _shell() -> str:
    return (_STATIC / "shell.js").read_text(encoding="utf-8")


def _css() -> str:
    return (_STATIC / "hymn.css").read_text(encoding="utf-8")


def test_journey_covers_the_full_roster_exactly_once():
    """THE COVERAGE LAW: every roster row appears exactly once in the journey —
    as a stage or as a door. A row left out is unreachable from the nav; a row
    doubled reads as two places. This is the ≤2-interactions law's server half."""
    from laplace.web import shared_ui

    roster_ids = {v["id"] for v in shared_ui.views_roster()["views"]}
    seen: list[str] = []
    for st in shared_ui.journey_payload(None)["stages"]:
        seen.append(st["view"])
        for d in st["doors"]:
            if d.get("view"):
                seen.append(d["view"])
    assert sorted(seen) == sorted(set(seen)), f"journey names a view twice: {seen}"
    assert set(seen) == roster_ids, (
        f"journey coverage broken — missing {roster_ids - set(seen)}, "
        f"phantom {set(seen) - roster_ids}")


def test_journey_words_are_composed_server_side():
    """The composition law at the nav: with a live project the stages carry
    server-composed state words (plain outcome phrases, never client-derived);
    with no corpus the same spine renders with no state claims."""
    from laplace.web import shared_ui

    bare = shared_ui.journey_payload(None)
    assert bare["live"] is False
    assert all(st["word"] is None for st in bare["stages"])
    # an unknown corpus is a spine without claims, never a dead nav
    unknown = shared_ui.journey_payload("no-such-project-name")
    assert unknown["live"] is False


def test_shell_renders_the_journey_not_a_hardcoded_roster():
    """The nav is driven by the fetched journey (plus the roster floor when the
    journey read fails) — no hardcoded surface list, no resurrected disclosure."""
    s = _shell()
    assert 'fetch("/shared/journey"' in s, "nav must fetch the composed journey"
    assert 'fetch("/shared/views")' in s, "the roster floor must still be fetched"
    assert "const VIEWS = [" not in s, "no hardcoded roster literal"
    assert "journeyHTML" in s and "stageEl" in s
    # the disclosure is dead — the journey's stage cards carry the doors now
    assert "hy-more-btn" not in s and "wireDisclosure" not in s
    # every stage card carries its doors + the you-are-here mark
    assert "sc-door" in s and "sc-here" in s


def test_brand_chip_is_home():
    """The brand chip is a LINK home (→ /, every paper at a glance), carrying
    the corpus, not a dead <span>."""
    s = _shell()
    assert "class='hy-mark' href=" in s, "brand chip must be an anchor"
    assert 'viewHref("/")' in s, "brand chip points home to /"
    assert "wireBrand" in s, "brand must carry the corpus at click time"
    assert "#hy-shell .hy-mark{" in _css()
    assert "cursor:default" not in _css().split("hy-mark")[1][:200]


def test_desk_stage_carries_the_badge_slot():
    """The desk badge slot lives on the Desk STAGE (its count belongs to its
    place on the journey) and renders as NO badge for absent/0 counts."""
    s = _shell()
    assert "id='hy-desk-badge'" in s or 'id="hy-desk-badge"' in s
    assert "setDeskBadge" in s
    assert "setDeskBadge: setDeskBadge" in s, "the setter must be on the HymnShell API"
    assert "v <= 0" in s and "b.hidden = true" in s
    assert "#hy-shell .hy-badge" in _css()
    # the badge slot is minted inside the desk stage element, not the mark
    assert "hy-desk-word" in s, "the desk stage speaks its count as a phrase too"


def test_journey_obeys_the_375_law_in_css():
    """The 375px law, CSS-level: the journey WRAPS (never horizontal-scrolls);
    the stage cards are out of flow (absolute), hidden at rest, and anchor to
    the right edge on narrow viewports so an OPEN card never forces overflow."""
    css = _css()
    row = css.split("#hy-shell .hy-journey{")[1].split("}")[0]
    assert "flex-wrap:wrap" in row, "the journey must wrap, not overflow"
    card = css.split("#hy-shell .hy-stage-card{")[1].split("}")[0]
    assert "position:absolute" in card, "the stage card is out of flow"
    assert "visibility:hidden" in card, "the stage card is hidden at rest"
    flat = css.replace("\n", "")
    assert "#hy-shell .hy-stage-card{right:0;left:auto" in flat, \
        "narrow viewports anchor the open card to the right edge"


def test_per_page_nav_variants_are_killed():
    """ONE nav: the surfaces that carried their own cross-surface nav strips no
    longer do — the shell is the single roster."""
    scanner_app = (_SRC / "web" / "scanner_app.html").read_text(encoding="utf-8")
    assert 'id="surfnav"' not in scanner_app, "the map page's #surfnav must be gone"
    assert 'href="/dials"' not in scanner_app and 'href="/analytics"' not in scanner_app

    conceptric = (_SRC / "web" / "conceptric.html").read_text(encoding="utf-8")
    assert 'class="nav-link"' not in conceptric, "conceptric's per-page nav-link must be gone"


# ---------------------------------------------------------------------------
# CHROMIUM TIER — the real renderer; auto-skips without Playwright/Chromium.
# ---------------------------------------------------------------------------

_CHROME_CANDIDATES = list(Path("/opt/pw-browsers").glob("chromium-*/chrome-linux/chrome"))
_CHROME = str(_CHROME_CANDIDATES[0]) if _CHROME_CANDIDATES else None

try:  # playwright may be absent even when a Chromium build is present
    import playwright.sync_api as _pw  # noqa: F401
    _HAS_PW = True
except Exception:
    _HAS_PW = False

_NO_BROWSER = _CHROME is None or not _HAS_PW
_SKIP_REASON = "no Chromium build under /opt/pw-browsers" if _CHROME is None else "playwright not installed"

# surfaces that serve their HTML regardless of corpus data — safe on any tree.
_SURFACES = ["/", "/desk", "/pipeline"]


def _serve():
    from laplace.web import scanner
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), scanner.make_handler())
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


# the nav "fingerprint" = the ordered (data-view, path) pairs across stages and
# doors — identical across surfaces means ONE nav. The you-are-here classes are
# deliberately excluded (they are per-surface by design).
_FINGERPRINT_JS = """() => {
  const nav = document.querySelector('#hy-shell .hy-journey');
  if(!nav) return null;
  const links = [...nav.querySelectorAll('a[data-path]')].map(a => ({
    view: a.dataset.view || null,
    path: a.dataset.path,
    stage: a.classList.contains('hy-stage'),
  }));
  return {links};
}"""


@pytest.mark.skipif(_NO_BROWSER, reason=_SKIP_REASON)
def test_every_surface_serves_the_same_journey():
    """DOM-level: the injected journey (stages + doors) is identical across
    surfaces — the one-nav invariant, proven in the real renderer."""
    from playwright.sync_api import sync_playwright

    httpd, port = _serve()
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch(executable_path=_CHROME)
            pg = b.new_page(viewport={"width": 1400, "height": 900})
            prints = []
            for path in _SURFACES:
                pg.goto(f"http://127.0.0.1:{port}{path}", wait_until="networkidle")
                pg.wait_for_selector("#hy-shell .hy-journey a[data-path]", timeout=10000)
                prints.append((path, pg.evaluate(_FINGERPRINT_JS)))
            b.close()
    finally:
        httpd.shutdown()

    ref_path, ref = prints[0]
    assert ref and ref["links"], f"no journey rendered on {ref_path}"
    for path, fp in prints[1:]:
        assert fp == ref, f"journey on {path} differs from {ref_path}:\n{fp}\nvs\n{ref}"


@pytest.mark.skipif(_NO_BROWSER, reason=_SKIP_REASON)
def test_full_roster_reachable_in_two_interactions():
    """Every roster row is reachable in ≤2 interactions: stages are visible
    links (1 click); doors are hidden at rest and become visible after ONE
    hover/focus of their stage (reveal + click = 2)."""
    from laplace.web import shared_ui
    from playwright.sync_api import sync_playwright

    journey = shared_ui.journey_payload(None)["stages"]
    httpd, port = _serve()
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch(executable_path=_CHROME)
            pg = b.new_page(viewport={"width": 1400, "height": 900})
            pg.goto(f"http://127.0.0.1:{port}/desk", wait_until="networkidle")
            pg.wait_for_selector("#hy-shell .hy-journey a[data-path]", timeout=10000)

            def visible(sel):
                el = pg.query_selector(sel)
                if el is None:
                    return None
                bb = el.bounding_box()
                return bool(bb and bb["width"] > 2 and bb["height"] > 2) and \
                    pg.evaluate("el => getComputedStyle(el).visibility !== 'hidden'", el)

            for st in journey:
                sel = f"#hy-shell .hy-stage[data-view='{st['view']}']"
                assert visible(sel) is True, f"stage {st['id']} not directly visible"
                doors = [d for d in st["doors"] if d.get("view")]
                if not doors:
                    continue
                for d in doors:
                    dsel = f"#hy-shell .sc-door[data-view='{d['view']}']"
                    assert visible(dsel) is not True, \
                        f"door {d['view']} visible before its stage reveals"
                pg.hover(sel)
                pg.wait_for_timeout(450)   # the reveal transition delay
                for d in doors:
                    dsel = f"#hy-shell .sc-door[data-view='{d['view']}']"
                    assert visible(dsel) is True, \
                        f"door {d['view']} not reachable after one hover"
            b.close()
    finally:
        httpd.shutdown()


@pytest.mark.skipif(_NO_BROWSER, reason=_SKIP_REASON)
def test_no_horizontal_overflow_at_375px():
    """The 375px law, in the renderer: no horizontal scroll on any surface at
    375px — at rest AND with a stage card revealed."""
    from playwright.sync_api import sync_playwright

    httpd, port = _serve()
    overflows = []
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch(executable_path=_CHROME)
            pg = b.new_page(viewport={"width": 375, "height": 720})
            for path in _SURFACES:
                pg.goto(f"http://127.0.0.1:{port}{path}", wait_until="networkidle")
                pg.wait_for_selector("#hy-shell .hy-journey a[data-path]", timeout=10000)
                w = pg.evaluate("() => document.documentElement.scrollWidth")
                cw = pg.evaluate("() => document.documentElement.clientWidth")
                if w > cw:
                    overflows.append((path, "rest", w, cw))
                # with a stage card revealed (the widest card is a doored stage)
                pg.hover("#hy-shell .hy-stage[data-view='artefact']")
                pg.wait_for_timeout(450)
                w2 = pg.evaluate("() => document.documentElement.scrollWidth")
                cw2 = pg.evaluate("() => document.documentElement.clientWidth")
                if w2 > cw2:
                    overflows.append((path, "card-open", w2, cw2))
            b.close()
    finally:
        httpd.shutdown()
    assert not overflows, f"horizontal overflow at 375px: {overflows}"
