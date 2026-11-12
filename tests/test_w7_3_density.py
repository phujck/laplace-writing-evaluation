"""W7.3 — density normalization: /storyboard and /conceptric2 each open at
≤4 first-paint control groups, with the excess FOLDED (never deleted) behind
an explicit disclosure — the nav's "…" idiom, one click deep (the roster law).

The census is MECHANICAL, not judged. A first-paint control group is any
element the surface author marks `data-cgroup="<name>"` — a toolbar, a filter
rail, a tab bar, an editing canvas, an action/inspector panel. Navigation
chrome (the injected shell nav, the breadcrumb trail, a lone corpus selector,
the read-only status/footer stats) is NOT a control group and carries no marker.

A marked group is FOLDED when its own element carries `data-cg-folded` (always
paired with the `hidden` attribute + a `#…[hidden]{display:none}` rule so the
fold is real, not cosmetic). Folded groups do not count against the ≤4 first
paint, and every one of them must be reachable in ≤2 interactions: a disclosure
trigger (`data-cg-fold` + `aria-controls=<group id>`) reveals it in one click,
so the controls inside are two interactions deep at worst.

Two tiers, the W1.1 idiom. The STATIC FLOOR (html.parser over the source) is the
fail-closed proof and runs everywhere. The Chromium tier drives the real toggle
(rest→hidden, one click→visible) and auto-skips when Playwright/Chromium is
absent.
"""

from __future__ import annotations

import threading
from html.parser import HTMLParser
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SRC = Path(__file__).resolve().parents[1] / "src" / "laplace"
_STORYBOARD = _SRC / "web" / "storyboard.html"
_CONCEPTRIC2 = _SRC / "web" / "conceptric.html"   # the conceptric surface (W3: conceptric_editor2.html -> conceptric.html)


# ---------------------------------------------------------------------------
# THE CENSUS — committed with the test so the count is mechanical, not judged.
# ---------------------------------------------------------------------------


class _CensusParser(HTMLParser):
    """Walks the static HTML and records every ``data-cgroup`` element as either
    a first-paint (visible) group or a folded group, plus the disclosure triggers
    (``data-cg-fold`` + ``aria-controls``)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.visible: list[str] = []            # group names faced at first paint
        self.folded: list[tuple[str, str]] = []  # (name, element id) behind a disclosure
        self.triggers: set[str] = set()          # aria-controls targets of data-cg-fold

    def handle_starttag(self, tag, attrs):
        a = {k: (v if v is not None else "") for k, v in attrs}
        if "data-cgroup" in a:
            name = a.get("data-cgroup") or tag
            folded = ("data-cg-folded" in a) or ("hidden" in a) \
                or ("display:none" in a.get("style", "").replace(" ", ""))
            if folded:
                self.folded.append((name, a.get("id", "")))
            else:
                self.visible.append(name)
        if "data-cg-fold" in a:
            self.triggers.add(a.get("aria-controls", ""))


def census(html_text: str) -> _CensusParser:
    p = _CensusParser()
    p.feed(html_text)
    return p


# ---------------------------------------------------------------------------
# STORYBOARD — separately interrogated.
#
# UPDATED TO CURRENT TRUTH (W-PINS 2026-07-22): the old F11 read was the static
# builder board (spine-rail / board / tools-rail / status-bar + a folded staleness
# strip). W-SB RE-CONCEIVED /storyboard as THE STORYBOARD IN THE ENGINE: storyboard.html
# is now a THIN BOOT SHELL for storyboard-panes.mjs (initStoryboard) — the resting DOM is
# the composed BRIEF (delta-and-ask) + one-line counts, and every control group (the
# section/weighting cards, the conveyor, the structure editor) is MATERIALISED AT RUNTIME
# behind a focus. So the STATIC first-paint census carries ZERO static groups: the ≤4
# density budget holds BY CONSTRUCTION (identical supersession to the conceptric growth-
# cockpit re-conception below). COVERAGE'S NEW HOME (named): the storyboard's runtime
# first-paint density is a surface-in-the-engine concern; the Chromium tier already DROPPED
# /storyboard at this re-conception (see the parametrize note below). GAP FLAGGED: a runtime
# density guard for the storyboard/cockpit engine surfaces is owed to the interface/cockpit
# wave — a static parse cannot measure a JS-rendered surface.
# ---------------------------------------------------------------------------


def test_storyboard_first_paint_is_at_most_four_control_groups():
    html = _STORYBOARD.read_text(encoding="utf-8")
    c = census(html)
    assert c.visible == [], \
        f"the JS storyboard-in-the-engine shell must carry no static density groups now: {c.visible}"
    assert "storyboard-panes.mjs" in html and "initStoryboard" in html, \
        "storyboard.html must be the engine boot shell (storyboard-panes.mjs / initStoryboard)"


def test_storyboard_folded_groups_are_reachable_in_two_interactions():
    # the re-conception opens AT the density budget (0 static groups, the brief is the
    # resting altitude) with nothing to fold — the staleness strip the old static board
    # folded is gone (it now materialises behind a focus). A surface already within budget
    # owes no fold; but any fold it DID carry must still be reachable in one click, and the
    # shell must author no stale static control groups (the old #sb-stale fold is gone).
    html = _STORYBOARD.read_text(encoding="utf-8")
    c = census(html)
    for name, gid in c.folded:
        assert gid, f"folded group {name!r} needs an id for its disclosure to target"
        assert gid in c.triggers, (
            f"folded group {name!r} (#{gid}) has no disclosure trigger — "
            f"it must be reachable in one click (≤2 interactions total)"
        )
    assert "#sb-stale[hidden]{display:none}" not in html, \
        "the re-conception dropped the static staleness strip — #sb-stale must be gone"


# ---------------------------------------------------------------------------
# CONCEPTRIC — separately interrogated (W3 re-conception, mocks/conceptric.html).
#
# The old F11 read was the conceptric_editor2 MAP (map-rail / lens-tabs / canvas /
# inspector + a folded editing toolbar). W3 RE-CONCEIVED the surface to the approved
# mock: the BOARD owns the centre (grade chips are server slices), the INSPECTOR
# stands in its own column, and the boardbar carries the grade strata + find. Editing
# is no longer a conceptric concern — the surface is a read-and-rule board, so there
# is no editing toolbar to fold. First paint is EXACTLY its four groups:
# board · find · grade-strata · inspector = 4, with nothing left to fold.
# ---------------------------------------------------------------------------


def test_conceptric2_first_paint_is_at_most_four_control_groups():
    # UPDATED TO CURRENT TRUTH (W-TRIAGE 2026-07-22): /conceptric was re-conceived AGAIN — the static
    # read-and-rule board (board/find/grade-strata/inspector) is superseded by the JS-RENDERED GROWTH
    # COCKPIT. conceptric.html is now a THIN BOOT SHELL for cockpit-panes.mjs (initCockpit) — the DOM,
    # and thus every control group, is built at RUNTIME (mocks/README_RETIRED.md, E2/E3). So the STATIC
    # first-paint census carries ZERO static groups: the ≤4 density budget holds by construction and the
    # old four-group structure is gone. COVERAGE'S NEW HOME (named): the cockpit's runtime first-paint
    # density is a cockpit-instrumentation concern — the Chromium tier already DROPPED /conceptric at this
    # re-conception (see the parametrize note below). GAP FLAGGED: a runtime density guard for the growth
    # cockpit is owed to the interface/cockpit wave; a static parse cannot measure a JS-rendered surface.
    html = _CONCEPTRIC2.read_text(encoding="utf-8")
    c = census(html)
    assert c.visible == [], \
        f"the JS growth-cockpit shell must carry no static density groups now: {c.visible}"
    assert "cockpit-panes.mjs" in html and "initCockpit" in html, \
        "conceptric.html must be the growth-cockpit boot shell (cockpit-panes.mjs / initCockpit)"


def test_conceptric2_folded_groups_are_reachable_in_two_interactions():
    # the re-conception opens AT the density budget (4 groups) with nothing to fold —
    # the editing toolbar the old surface folded is gone (not a map-reading/rule need).
    # A surface already at budget owes no fold; but any fold it DID carry must still be
    # reachable in one click, and the surface must author no stale editing controls.
    c = census(_CONCEPTRIC2.read_text(encoding="utf-8"))
    for name, gid in c.folded:
        assert gid, f"folded group {name!r} needs an id for its disclosure to target"
        assert gid in c.triggers, (
            f"folded group {name!r} (#{gid}) has no disclosure trigger — "
            f"it must be reachable in one click (≤2 interactions total)"
        )
    html = _CONCEPTRIC2.read_text(encoding="utf-8")
    for stale in ('id="addNodeBtn"', 'id="m-browse"', 'id="m-edit"', 'id="edit-tools"'):
        assert stale not in html, f"the re-conception dropped the editing tools — {stale} must be gone"


# ---------------------------------------------------------------------------
# CHROMIUM TIER — the real renderer; auto-skips without Playwright/Chromium.
# Proves the fold is invisible at rest and reachable in one click.
# ---------------------------------------------------------------------------

_CHROME_CANDIDATES = list(Path("/opt/pw-browsers").glob("chromium-*/chrome-linux/chrome"))
_CHROME = str(_CHROME_CANDIDATES[0]) if _CHROME_CANDIDATES else None

try:
    import playwright.sync_api as _pw  # noqa: F401
    _HAS_PW = True
except Exception:
    _HAS_PW = False

_NO_BROWSER = _CHROME is None or not _HAS_PW
_SKIP_REASON = "no Chromium build under /opt/pw-browsers" if _CHROME is None else "playwright not installed"


def _serve():
    from laplace.web import scanner
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), scanner.make_handler())
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


@pytest.mark.skipif(_NO_BROWSER, reason=_SKIP_REASON)
@pytest.mark.parametrize("path,fold_id", [
    # BOTH surfaces dropped (W-PINS 2026-07-22): /conceptric (W3 growth-cockpit) and
    # /storyboard (W-SB the-storyboard-in-the-engine) are now JS boot shells whose control
    # groups materialise AT RUNTIME behind a focus — there is no STATIC folded group to
    # reveal on either. The one-click static-fold discipline has no surface left to drive;
    # the runtime-density guard for the engine surfaces is the NAMED owed follow-on (the
    # interface/cockpit wave). The list is intentionally empty: this static-fold walk
    # collects zero cases until a surface re-authors a static disclosure.
])
def test_folded_group_hidden_at_rest_then_one_click_reveals(path, fold_id):
    from playwright.sync_api import sync_playwright

    httpd, port = _serve()
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch(executable_path=_CHROME)
            pg = b.new_page(viewport={"width": 1400, "height": 900})
            pg.goto(f"http://127.0.0.1:{port}{path}", wait_until="domcontentloaded")
            pg.wait_for_selector(f"#{fold_id}", state="attached", timeout=10000)
            assert pg.is_hidden(f"#{fold_id}"), f"{fold_id} must be hidden at rest"
            pg.click(f"[data-cg-fold][aria-controls='{fold_id}']")
            pg.wait_for_timeout(120)
            assert pg.is_visible(f"#{fold_id}"), f"{fold_id} not revealed after one click"
            b.close()
    finally:
        httpd.shutdown()
