"""W4.3 — pdf.js native text layer; the PNG/pdftoppm serving path retires.

The stage's fail-closed contract, one leg per claim:

1. THE PNG SERVING ROUTES ARE RETIRED (pure) — ``/projection/page`` and
   ``/projection/pages`` answer 410 (the W0.3 retirement idiom) regardless of the
   file= param, naming the surviving pdf routes. There is no page-image serving path
   left; the viewer rasterises the pdf in-browser with pdf.js.

2. THE POPPLER TEXT-LAYER SERVING ROUTE IS RETIRED (pure) — ``/projection/textlayer``
   answers 410 naming the pdf.js native text layer. No serving route shells out to
   poppler ``pdftotext -bbox`` anymore.

3. NO SERVING-PATH POPPLER/PDFTOPPM INVOCATION SURVIVES (grep-guard, W0.1 idiom) —
   the request router ``handle()`` reaches neither ``render_pages`` nor ``text_layer``
   nor the words ``pdftoppm`` / ``poppler`` on any branch. (Those functions survive as
   importable OFFLINE tooling for the frozen export scripts + the lock reader — they
   just are not reachable from the serving surface.)

4. THE VIEWER WIRES THE NATIVE TEXT LAYER (static) — the html builds ``.pgtext`` from
   pdf.js ``getTextContent`` (``buildTextLayer(w, page)`` + ``PDFJS.Util.transform``)
   and no longer fetches ``/projection/textlayer`` or the retired PNG routes, and the
   PNG fallback (``loadPagesPng``) is gone.

5. THE VENDORED pdf.js EXPOSES THE NATIVE TEXT LAYER (static) — the module exports
   ``TextLayer`` + ``Util`` and carries ``getTextContent`` (the API the viewer drives).

6. THE OVERLAY / NODEMAP PATH IS UNREGRESSED (pure + static) — the review surface
   still renders from pdf.js + the nodemap (never page PNGs): ``/review/nodemap``
   returns its verdict, and review_surface.html imports pdf.js, draws the overlay, and
   never consumed the retired PNG routes.

7. TEXT SELECTABLE FROM pdf.js (headless; skips without latexmk/Chromium) — a compiled
   fixture rendered in review mode shows a ``.pgtext`` layer in the DOM carrying REAL
   strings from the pdf, the strings are selectable, and NONE of the retired routes are
   requested.

Windows discipline: pathlib throughout; latexmk resolves per the local-tex-path law, so
a box without it (or without Chromium) skips honestly rather than failing.
"""

from __future__ import annotations

import inspect
import json
import shutil
import subprocess
import threading
import urllib.parse
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from laplace.manuscript import projection_viewer as pv

pytestmark = pytest.mark.unit

_WHITEPAPER = "synthetics papers/subset-sum-itqde/manuscript/whitepaper/main.tex"
# W2: projection_viewer.html + review_surface.html CONSOLIDATED into the ONE artefact
# surface (artefact.html) whose reader behaviour lives in the shared module
# static_shared/artefact-panes.mjs — the pdf.js native text layer re-housed there. These
# leg-4/6 clauses (the text-layer wiring) re-aim at the module + the surface's html.
_SRC = Path(pv.__file__).resolve().parents[1] / "web"   # the served page and its static assets (laplace/web)
_HTML = (_SRC / "artefact.html").read_text(encoding="utf-8")
_PANES = (_SRC / "static_shared" / "artefact-panes.mjs").read_text(encoding="utf-8")
_PDFJS = _SRC / "static_shared" / "pdfjs" / "pdf.min.mjs"


# ---------------------------------------------------------------------------
# 1 + 2.  the retirements answer 410 (the W0.3 idiom)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("route", ["/projection/page", "/projection/pages"])
def test_png_serving_route_retired_410(route):
    for probe in ["src/laplace/web/scanner.py", _WHITEPAPER, "../outside.png", ""]:
        status, ctype, body = pv.handle(route, {"file": [probe]}, "GET", b"")
        assert status == 410, (route, probe)
        assert "json" in ctype
        payload = json.loads(body)
        assert payload["retired"] == "W4.3"
        assert "pdf.js" in payload["reason"]
        assert "/projection/pdf" in payload["use"]


def test_textlayer_serving_route_retired_410():
    for probe in [_WHITEPAPER, "", "../outside.pdf"]:
        status, ctype, body = pv.handle("/projection/textlayer", {"file": [probe]},
                                        "GET", b"")
        assert status == 410, probe
        payload = json.loads(body)
        assert payload["retired"] == "W4.3"
        assert "pdf.js" in payload["reason"]


def test_surviving_pdf_routes_are_not_retired():
    """The routes pdf.js DEPENDS ON stay live: /projection/pdf (bytes) and
    /projection/pdfinfo (metadata) must not be swept up in the retirement."""
    for route in ("/projection/pdf", "/projection/pdfinfo"):
        status, _, body = pv.handle(route, {"file": [_WHITEPAPER]}, "GET", b"")
        assert status != 410, route
        # a real compiled whitepaper is on the tree, so these resolve; but even if not,
        # the point is they are NOT retired — anything but 410 proves the route lives.


# ---------------------------------------------------------------------------
# 3.  grep-guard — no serving-path poppler/pdftoppm invocation survives
# ---------------------------------------------------------------------------

def test_no_serving_path_poppler_invocation():
    """FAIL-CLOSED: the request router reaches no raster/poppler producer on any branch.
    render_pages / text_layer / _poppler_pdftotext survive as offline tooling, but the
    serving surface (handle) must not name them, nor pdftoppm / poppler / pdftotext."""
    src = inspect.getsource(pv.handle)
    for forbidden in ("render_pages", "text_layer", "pdftoppm", "poppler",
                      "pdftotext", "_pages_dir", "_PAGES_DIRNAME"):
        assert forbidden not in src, (
            f"the serving router still reaches {forbidden!r} — the PNG/poppler path "
            "leaked back into a route")


# ---------------------------------------------------------------------------
# 4.  the viewer wires the native text layer, drops the retired fetches
# ---------------------------------------------------------------------------

def test_viewer_wires_pdfjs_native_text_layer():
    # the artefact reader builds the text layer from pdf.js, not poppler word boxes — the
    # native-text-layer idiom, re-housed into the shared pane module (W2).
    assert "getTextContent" in _PANES, "the reader does not read pdf.js getTextContent"
    assert "Util.transform" in _PANES, "no viewport-space transform for the text layer"
    assert "buildTextLayer" in _PANES, "buildTextLayer is not driven from the pdf.js page"
    assert '"pgtext"' in _PANES and "pgtext" in _HTML, "the .pgtext native text layer is missing"


def test_viewer_drops_the_retired_serving_paths():
    # no fetch of the retired routes, no PNG fallback path, no poppler text-layer fetch
    for gone in ("/projection/textlayer", "/projection/pages",
                 "/projection/page?file=", "loadPagesPng", "startPageQueue"):
        assert gone not in _PANES and gone not in _HTML, \
            f"the reader still references the retired {gone!r}"


# ---------------------------------------------------------------------------
# 5.  the vendored pdf.js exposes the native text layer
# ---------------------------------------------------------------------------

def test_vendored_pdfjs_exposes_native_text_layer():
    assert _PDFJS.is_file(), "pdf.js is not vendored under static_shared/pdfjs"
    blob = _PDFJS.read_text(encoding="utf-8", errors="replace")
    # the export table carries the native text-layer machinery the viewer drives
    assert "TextLayer" in blob and "Util" in blob and "getTextContent" in blob


# ---------------------------------------------------------------------------
# 6.  the overlay / nodemap path is unregressed (never depended on page PNGs)
# ---------------------------------------------------------------------------

def test_review_overlay_renders_from_pdfjs_and_nodemap_not_pngs():
    # the artefact surface's annotate mode renders from pdf.js + the nodemap anchor layer;
    # it never consumed the retired PNG routes, so retiring them cannot dead-panel it
    assert "/shared/pdfjs/pdf.min.mjs" in _PANES
    assert "/review/nodemap" in _PANES                # the anchor truth (review_surface.nodemap_state)
    assert "art-anchor" in _PANES                     # the anchor layer (re-housed overlay idiom)
    assert "pdf_endpoint" in _PANES                   # the surviving /projection/pdf producer
    for gone in ("/projection/pages", "/projection/page?file=", "/projection/textlayer"):
        assert gone not in _PANES, f"the artefact surface referenced retired {gone!r}"


def test_review_nodemap_route_still_answers():
    """The W2.4 anchor path: /review/nodemap returns a structured verdict (present or an
    honest absent), never a 410/500 — the overlay's anchor truth is untouched by W4.3."""
    status, ctype, body = pv_review_handle("/review/nodemap",
                                           {"corpus": ["subset-sum-itqde"]})
    assert status in (200, 404), status          # 200 with a verdict, or honest unknown
    assert "json" in ctype
    payload = json.loads(body)
    if status == 200:
        assert "present" in payload               # the nodemap freshness verdict shape


def pv_review_handle(path, query):
    from laplace.manuscript import review_surface as rv
    from laplace.web import review_http
    return review_http.handle(path, query, "GET", b"")


# ---------------------------------------------------------------------------
# 7.  headless — the text layer exists in the DOM with real strings, selectable
# ---------------------------------------------------------------------------

_CHROME_CANDIDATES = list(Path("/opt/pw-browsers").glob("chromium-*/chrome-linux/chrome"))
_CHROME = str(_CHROME_CANDIDATES[0]) if _CHROME_CANDIDATES else None

_TL_JS = r"""
async () => {
  // wait up to ~15s for the pdf.js text layer to build in the artefact reader (read mode)
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline){
    if (document.querySelector(".pgtext span")) break;
    await new Promise(r => setTimeout(r, 150));
  }
  const spans = [...document.querySelectorAll(".pgtext span")];
  if (!spans.length) return {err: "no .pgtext spans built"};
  const text = spans.map(s => s.textContent).join(" ").trim();
  const canvasLoaded = !!document.querySelector("#art-reader canvas.pgcv");

  // selection: select the contents of a substantive span, prove the layer is selectable
  let selected = "";
  const target = spans.find(s => (s.textContent || "").trim().length > 3);
  if (target){
    const range = document.createRange();
    range.selectNodeContents(target);
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
    selected = sel.toString();
  }
  return {text, canvasLoaded, selected, nspans: spans.length};
}
"""


@pytest.mark.skipif(_CHROME is None,
                    reason="no Chromium build under /opt/pw-browsers")
def test_text_layer_selectable_from_pdfjs():
    """The native text layer, in the real renderer: opening the ARTEFACT surface on the real
    subset-sum whitepaper (its main.pdf is on the tree) builds a ``.pgtext`` layer carrying
    REAL selectable strings from the pdf — and requests NONE of the retired PNG/textlayer
    routes. Drives the consolidated reader, not the retired /projection review tab."""
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    from laplace.web import scanner
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), scanner.make_handler())
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_address[1]

    retired_hits: list[str] = []
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=_CHROME)
            pg = b.new_page(viewport={"width": 1100, "height": 900})
            pg.on("request", lambda r: retired_hits.append(r.url)
                  if ("/projection/pages" in r.url or "/projection/page?" in r.url
                      or "/projection/textlayer" in r.url) else None)
            pg.goto(f"http://127.0.0.1:{port}/artefact?corpus=subset-sum-itqde",
                    wait_until="domcontentloaded")
            info = pg.evaluate(_TL_JS)
            b.close()
    finally:
        httpd.shutdown()

    assert "err" not in info, info
    assert info["canvasLoaded"] is True, "the pdf.js canvas never rendered"
    assert info["nspans"] > 0, "the native text layer built no spans"
    assert len(info["text"]) > 20, f"pdf text missing from the layer: {info['text'][:200]!r}"
    assert len(info["selected"].strip()) > 0, f"selection returned nothing usable: {info['selected']!r}"
    # NONE of the retired routes were requested
    assert not retired_hits, f"the reader requested a retired route: {retired_hits}"
