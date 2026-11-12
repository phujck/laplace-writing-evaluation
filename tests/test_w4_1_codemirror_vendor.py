"""W4.1 — the vendored CodeMirror 6 bundle (the offline law).

Two fail-closed guards, mirroring the KaTeX/pdf.js precedent:

1. THE ROUTE + BYTES (pure, always runs): the bundle exists as a tracked file,
   serves 200 with the right JS MIME through the ONE ``/shared/*`` route, carries
   real bundled content, and its LICENSE ships beside it. Traversal is fenced.

2. THE HEADLESS MOUNT (skips without Playwright/Chromium, as the sibling smokes
   do): the bundle is imported same-origin from the live server, an EditorView is
   mounted with TeX content, and the editor PAINTS with zero console/page errors.
   Endpoint-green is not enough — the blank-page class only shows under a real
   renderer (the lesson banked on the projection viewer and the storyboard).

NOTHING in the viewer surface loads this bundle yet (W4.2 consumes it); this
stage only proves the bundle parses and CM6 mounts headless.
"""

from __future__ import annotations

import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_VENDOR = (
    Path(__file__).resolve().parent.parent
    / "src" / "laplace" / "web" / "static_shared" / "vendor" / "codemirror"
)
_BUNDLE = _VENDOR / "codemirror.bundle.mjs"
_BUNDLE_ROUTE = "/shared/vendor/codemirror/codemirror.bundle.mjs"


# --- 1. THE ROUTE + BYTES ---------------------------------------------------

def test_bundle_file_present_and_licensed():
    assert _BUNDLE.is_file(), "the CM6 bundle must be a tracked file on disk"
    assert (_VENDOR / "LICENSE").is_file(), "the bundle's LICENSE must ship beside it"
    assert (_VENDOR / "VENDORED.md").is_file(), "provenance note must ship beside it"
    # a real bundle, not a stub: CM6 minified is hundreds of KB.
    assert _BUNDLE.stat().st_size > 100_000, "bundle looks truncated/stubbed"
    text = _BUNDLE.read_text(encoding="utf-8")
    # the curated exports 4.2 relies on must survive the bundle.
    for name in ("EditorView", "EditorState", "stex", "baseSetup", "shellDark"):
        assert name in text, f"export {name!r} missing from the bundle"


def test_bundle_serves_200_with_js_mime():
    from laplace.web import shared_ui

    status, ctype, body = shared_ui.handle(_BUNDLE_ROUTE, {})
    assert status == 200
    assert ctype == "text/javascript; charset=utf-8"
    assert body == _BUNDLE.read_bytes()
    assert len(body) > 100_000


def test_bundle_route_fences_traversal():
    from laplace.web import shared_ui

    # a name that would escape static_shared must 404 (the allowlist IS the fence).
    status, _ctype, _body = shared_ui.handle(
        "/shared/vendor/codemirror/../../scanner.py", {}
    )
    assert status == 404


# --- 2. THE HEADLESS MOUNT --------------------------------------------------

_CHROME_CANDIDATES = list(Path("/opt/pw-browsers").glob("chromium-*/chrome-linux/chrome"))
_CHROME = str(_CHROME_CANDIDATES[0]) if _CHROME_CANDIDATES else None

# A minimal same-origin page that imports the vendored bundle and mounts an
# editor with TeX content. Injected AFTER navigating to a served surface so the
# ESM import is same-origin (a data:/about:blank origin can't import http://).
_MOUNT_JS = r"""
async () => {
  const mod = await import("/shared/vendor/codemirror/codemirror.bundle.mjs");
  const { EditorState, EditorView, baseSetup, stexLanguage, shellDark } = mod;
  const host = document.createElement("div");
  host.id = "cm-smoke-host";
  document.body.appendChild(host);
  const doc = "\\documentclass{article}\n\\begin{document}\n"
    + "\\section{Spectral surface}\n"
    + "The generating surface $Z_\\tau(s)$ gives $\\partial_s \\log Z_\\tau(s)"
    + " = \\langle X \\rangle_s$.\n\\end{document}";
  const view = new EditorView({
    parent: host,
    state: EditorState.create({ doc, extensions: [baseSetup, stexLanguage, shellDark] }),
  });
  window.__cm = view;
  const el = document.querySelector(".cm-editor");
  const box = el.getBoundingClientRect();
  return {
    area: box.width * box.height,
    lines: document.querySelectorAll(".cm-line").length,
    docLen: view.state.doc.length,
  };
}
"""


@pytest.mark.skipif(_CHROME is None, reason="no Chromium build under /opt/pw-browsers")
def test_codemirror_mounts_headless_no_errors():
    pytest.importorskip("playwright.sync_api")
    from laplace.web import scanner

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), scanner.make_handler())
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_address[1]
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            b = pw.chromium.launch(executable_path=_CHROME)
            pg = b.new_page(viewport={"width": 1000, "height": 700})
            errors: list[str] = []
            # ConsoleMessage.text/.type are PROPERTIES in this Playwright build;
            # the favicon.ico 404 console error is browser noise, not a bundle error.
            # resource-load console errors carry no URL; the response listener
            # below is the authoritative HTTP-error detector (favicon-filtered) —
            # keep only console errors that are NOT resource-load duplicates.
            pg.on("console", lambda m: errors.append("CONSOLE:" + m.text)
                  if m.type == "error"
                  and "Failed to load resource" not in m.text else None)
            pg.on("pageerror", lambda e: errors.append("PAGEERROR:" + str(e)))
            pg.on("response", lambda r: errors.append(f"HTTP{r.status}:{r.url}")
                  if r.status >= 400 and not r.url.endswith("/favicon.ico") else None)
            # navigate to a real served surface so the import is same-origin.
            pg.goto(f"http://127.0.0.1:{port}/dials", wait_until="domcontentloaded")
            info = pg.evaluate(_MOUNT_JS)
            pg.wait_for_selector("#cm-smoke-host .cm-editor", timeout=10000)
            b.close()
    finally:
        httpd.shutdown()

    assert not errors, f"console/http errors during CM6 mount: {errors}"
    assert info["area"] > 0, "the editor mounted but painted zero area (blank)"
    assert info["lines"] >= 3, f"expected the TeX doc to render >=3 lines, got {info['lines']}"
    assert info["docLen"] > 50, "the TeX document did not load into the editor state"
