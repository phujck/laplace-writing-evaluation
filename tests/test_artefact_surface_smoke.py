"""A read-only in-browser render smoke for THE ARTEFACT SURFACE (the W2 consolidation).

Successor to ``tests/test_review_surface_smoke.py``, retired 2026-08-21 under
WO-20260810-stale-browser-smokes. What the retired module drove and why it could not
be realigned in place:

  * It drove ``/review`` as a PAGE. Since the W2 consolidation (scanner: "/projection
    + /review folded into the ONE artefact surface"), ``/review`` and ``/projection``
    301 to ``/artefact``; only their ``/review/*`` + ``/projection/*`` DATA producers
    survive, re-housed behind the artefact panes.
  * Every selector it waited on is gone from the tree: ``.pgwrap`` (now ``.art-page``
    / ``canvas.pgcv``), ``.strow[data-stratum]`` / ``.cbadge`` / ``.ncard`` / ``.fnd``
    (the deltas-first tray strata), ``.subq`` (the escalation queue), ``.dismaudit
    .darow`` + ``.da-overrule`` (the dismissal audit and its two-step mass-revoke),
    ``#stale``, ``#prov``, ``#runbook``, ``.atab``. Not one of those class names
    survives anywhere under ``src/``.
  * Its whole fixture design is unreachable: both retired tests built a throwaway
    manuscript under the repo root and addressed it with ``dir=``. The artefact
    surface resolves ONLY through the project registry (``/artefact/context?corpus=``);
    ``dir=`` is not a door there. Measured live: ``/review?dir=…&corpus=nope`` lands on
    ``/artefact`` and states "could not resolve this project … 404: no project for that
    corpus (or none active)". Carrying the fixtures over would have meant minting a
    registered fixture PROJECT — a new design, not a selector rename.

The claims the retired module made are covered on the live surface by
``tests/wave2_artefact.playwright.mjs`` (the reader answers, the nodemap join, the
tray's counts, the dismissed fold's overrule — driven as outcomes against real
corpora) and ``tests/j5artefact_tray.playwright.mjs``; the pdf.js text layer and the
retired PNG/poppler serving routes stay proven in ``tests/test_w4_3_pdfjs_text_layer.py``.
What did NOT survive anywhere pytest collects is the cheap always-on guard those
smokes existed for — the ORIGINAL lesson, banked twice on the projection viewer:
endpoint-green is not enough, the blank-page / zero-area class only shows under a real
renderer. That guard is what this module keeps, on the surface that actually exists.

Read-only: it drives GET paths only and writes nothing into the tree. Auto-skips
without Playwright, without a Chromium build (resolved through
``tests/browser_fence.py``, never a hardcoded container path), and without the corpus.
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
    from laplace.research import corpus_ingest as ci
    return _CORPUS in ci.registered_corpora(Path(__file__).resolve().parents[1])


def _serve():
    from laplace.web import scanner
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), scanner.make_handler())
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


@pytest.mark.skipif(_CHROME is None, reason=_bf.NO_CHROME_REASON)
def test_artefact_reader_paints_through_the_review_deeplink():
    """The blank-page guard on the live surface, entered through the RETIRED door: a
    ``/review?corpus=`` deep link (the address every banked link still carries) must
    301 onto ``/artefact`` and the real artefact must PAINT — pdf.js canvases with
    real area inside ``.art-page``, the header naming the revision, no page errors and
    no failed requests."""
    if not _corpus_available():
        pytest.skip(f"corpus {_CORPUS} not registered in this checkout")
    from playwright.sync_api import sync_playwright

    httpd, port = _serve()
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch(executable_path=_CHROME)
            pg = b.new_page(viewport={"width": 1400, "height": 900})
            bad = []
            pg.on("response", lambda r: bad.append((r.status, r.url))
                  if r.status >= 400 and not r.url.endswith("/favicon.ico") else None)
            pg.on("pageerror", lambda e: bad.append(("PAGEERROR", str(e))))
            pg.goto(f"http://127.0.0.1:{port}/review?corpus={_CORPUS}",
                    wait_until="networkidle")
            landed = pg.url
            # the artefact rasterises in-browser (pdf.js), never a served PNG
            pg.wait_for_selector(".art-page canvas.pgcv", timeout=30000)
            canvases = pg.query_selector_all(".art-page canvas.pgcv")
            box = next((_bb for c in canvases if (_bb := c.bounding_box())), None)
            rev = pg.query_selector("#art-rev")
            rev_txt = rev.inner_text().strip() if rev else ""
            msg = pg.query_selector("#art-reader .art-msg")
            msg_txt = msg.inner_text() if msg else ""
            b.close()

            assert "/artefact" in landed, \
                f"the /review deep link must land on the artefact surface, got {landed!r}"
            assert canvases, "no pdf.js page canvas rendered"
            assert box and box["width"] > 40 and box["height"] > 40, \
                f"page canvas has no real area: {box}"
            assert rev_txt, "the header did not name the artefact revision"
            assert not msg_txt, f"the reader stated a failure instead of painting: {msg_txt!r}"
            assert not bad, f"unexpected failed requests / page errors: {bad}"
    finally:
        httpd.shutdown()


@pytest.mark.skipif(_CHROME is None, reason=_bf.NO_CHROME_REASON)
def test_artefact_states_itself_when_the_project_does_not_resolve():
    """The honest-degradation half, and the tombstone for the retired ``dir=`` fixture
    door: an address the surface cannot resolve (an unregistered corpus — the shape the
    old fixture manuscripts used) renders a stated reason IN THE READER, never a blank
    page and never a silent partial paint."""
    from playwright.sync_api import sync_playwright

    httpd, port = _serve()
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch(executable_path=_CHROME)
            pg = b.new_page(viewport={"width": 1400, "height": 900})
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{port}/artefact"
                    f"?dir=.review_smoke_fixture&corpus=.review_smoke_fixture",
                    wait_until="networkidle")
            pg.wait_for_selector("#art-reader .art-msg", timeout=15000)
            msg = pg.query_selector("#art-reader .art-msg").inner_text()
            canvases = pg.query_selector_all(".art-page canvas.pgcv")
            b.close()

            assert "could not resolve this project" in msg.lower(), \
                f"the unresolved address must state itself, got {msg!r}"
            assert not canvases, "an unresolved project must paint no page"
            assert not errs, f"unexpected page errors: {errs}"
    finally:
        httpd.shutdown()
