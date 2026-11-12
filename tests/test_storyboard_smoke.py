"""A read-only in-browser render smoke for the storyboard — REALIGNED to the live board.

The lesson banked twice on the projection viewer: endpoint-green is not enough, the
blank-page/zero-area class only shows under a real renderer. This drives the board in
Chromium and asserts it actually PAINTS. Read-only — it never writes the plan, so it
needs no restore and is safe in CI.

REALIGNED 2026-08-21 (WO-20260810-stale-browser-smokes). The design this smoke was
written against — a strip-over-void board owning the centre, section COLUMNS
(``.sb-col``) at rest with ``.chip`` cards inside them, collapsed columns expanded by
clicking a column head — was retired by W-SB (2026-07-22, "the storyboard joined the
one instrument"): the resting DOM is now a COMPOSED BRIEF (``#eng-root`` /
``.eng-brief``) whose section rows are ``.sbb-sec``, and the object-sets MATERIALISE
on demand behind the ``.sb-count[data-materialize]`` counts, rendering into
``#sb-mat``. Measured on the live tree at realignment (subset-sum-itqde): 11 section
rows at rest, two materialise counts (findings · run), the findings count opening 24
``.sb-card`` cards. The three assertions survive the redesign unchanged in SPIRIT —
the brief paints, its rows have real area, and the interaction that reveals the
objects actually renders them — so this is a realignment, not a new claim. The full
engine grammar (delta-and-ask altitude, the counts law, grounding-in-place, pin /
return) is walk-proven in ``tests/engine_storyboard.playwright.mjs`` and
``tests/wave4_storyboard.playwright.mjs``; this stays the cheap always-collected
pytest guard that the surface is not blank.

Auto-skips when Playwright or a Chromium build is unavailable (resolved through
``tests/browser_fence.py``, never a hardcoded container path), so it never breaks a
headless CI without a browser.
"""

from __future__ import annotations

import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

playwright = pytest.importorskip("playwright.sync_api")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import browser_fence as _bf  # noqa: E402

_CHROME = _bf.CHROME

_CORPUS = "subset-sum-itqde"


def _corpus_available() -> bool:
    from pathlib import Path as _P

    from laplace.research import corpus_ingest as ci
    return _CORPUS in ci.registered_corpora(_P(__file__).resolve().parents[1])


@pytest.mark.skipif(_CHROME is None, reason=_bf.NO_CHROME_REASON)
def test_storyboard_board_renders_in_browser():
    if not _corpus_available():
        pytest.skip(f"corpus {_CORPUS} not registered in this checkout")
    from laplace.web import scanner

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), scanner.make_handler())
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_address[1]
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            b = pw.chromium.launch(executable_path=_CHROME)
            pg = b.new_page(viewport={"width": 1400, "height": 900})
            bad = []
            pg.on("response", lambda r: bad.append(r.url)
                  if r.status >= 400 and not r.url.endswith("/favicon.ico") else None)
            pg.on("pageerror", lambda e: bad.append("PAGEERROR:" + str(e)))
            pg.goto(f"http://127.0.0.1:{port}/storyboard?corpus={_CORPUS}",
                    wait_until="networkidle")
            # the composed brief is the resting surface (W-SB), not a column board
            pg.wait_for_selector("#eng-root .eng-brief", timeout=10000)
            pg.wait_for_selector(".eng-brief .sbb-sec", timeout=10000)

            secs = pg.query_selector_all(".eng-brief .sbb-sec")
            sec_box = next((_bb for s in secs if (_bb := s.bounding_box())), None)
            # the object-sets rest UNMATERIALISED behind their counts; the real
            # interaction is opening one (the analogue of the old column expand).
            counts = pg.query_selector_all(".sb-count[data-materialize]")
            cards_before = pg.query_selector_all("#sb-mat .sb-card")
            counts[0].click()
            pg.wait_for_selector("#sb-mat .sb-card", timeout=10000)
            cards = pg.query_selector_all("#sb-mat .sb-card")
            card_box = next((_bb for c in cards if (_bb := c.bounding_box())), None)
            b.close()

            assert len(secs) >= 1, "no section rows rendered in the brief"
            assert sec_box and sec_box["width"] > 2 and sec_box["height"] > 2, \
                f"section row has zero area: {sec_box}"
            assert counts, "no materialise counts rendered on the brief"
            assert not cards_before, \
                f"object cards must not ship at rest (delta-and-ask), got {len(cards_before)}"
            assert len(cards) > 10, f"too few cards materialised: {len(cards)}"
            # the blank-page guard: a materialised card must occupy real area
            assert card_box and card_box["width"] > 2 and card_box["height"] > 2, \
                f"card has zero area: {card_box}"
            assert not bad, f"unexpected failed requests / page errors: {bad}"
    finally:
        httpd.shutdown()
