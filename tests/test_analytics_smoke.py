"""A read-only in-browser render smoke for the /analytics dashboard.

Endpoint-green is not enough (the lesson banked on the projection viewer and the
storyboard): the blank-page / zero-area class only shows under a real renderer.
This drives /analytics in Chromium against real repo data and asserts the project
table AND one per-project round-series panel actually PAINT. Read-only — it never
writes, so it needs no restore and is safe in CI.

Auto-skips when Playwright or a Chromium build is unavailable.
"""
from __future__ import annotations

import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

playwright = pytest.importorskip("playwright.sync_api")

# the pre-installed Chromium (PLAYWRIGHT_BROWSERS_PATH); pinned by build so the
# library's own version download is skipped - point executable_path at it.
_CHROME_CANDIDATES = list(Path("/opt/pw-browsers").glob("chromium-*/chrome-linux/chrome"))
_CHROME = str(_CHROME_CANDIDATES[0]) if _CHROME_CANDIDATES else None


@pytest.mark.skipif(_CHROME is None, reason="no Chromium build under /opt/pw-browsers")
def test_analytics_dashboard_renders_in_browser():
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
            pg.goto(f"http://127.0.0.1:{port}/analytics", wait_until="networkidle")

            # the cross-project table must paint at least one project row
            pg.wait_for_selector("tr.an-row", timeout=10000)
            rows = pg.query_selector_all("tr.an-row")

            # a round-bearing project must be clickable and open a painted round strip
            round_row = pg.query_selector("tr.an-row.has-rounds")
            assert round_row is not None, "no round-bearing project row to expand"
            round_row.click()
            pg.wait_for_selector("#an-panel.show table.an-strip .an-cell", timeout=10000)
            box = next((_bb for c in pg.query_selector_all(".an-strip .an-cell")
                        if (_bb := c.bounding_box())), None)
            b.close()

            assert len(rows) >= 1, "no project rows rendered"
            # the blank-page guard: a transition cell must occupy real area
            assert box and box["width"] > 2 and box["height"] > 2, f"cell has zero area: {box}"
            assert not bad, f"unexpected failed requests / page errors: {bad}"
    finally:
        httpd.shutdown()
