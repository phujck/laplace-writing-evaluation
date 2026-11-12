"""W1.4 — THE LANDING (REDEFINED by W1: the dashboard is home).

W1 replaced the W1.4 landing redirect: the bare ``/`` route no longer 302s to ``/guide``
— it now SERVES THE DASHBOARD (the project-cards home, the New Project door). The
"landing" meta-surface is killed (conception §0e cause 3); ``/`` shows live project
state + doors. (W5: the desk MECHANISM rehoused to its own surface ``/desk`` — THE DESK
COCKPIT — and the ``/guide`` explainer died, so this file's former guide-page desk-band
clauses retired; the desk read-model + eager load are proven on /desk by test_guide.py +
tests/j5desk_cockpit.playwright.mjs.) Only the bare-``/`` behaviour matters here.

Two tiers: a TEMPLATE FLOOR (grep/DOM over the sources, no browser) and a live-server
tier (stdlib http.client) proving ``/`` serves the dashboard and the map is not orphaned.
"""
from __future__ import annotations

import http.client
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SRC = Path(__file__).resolve().parents[1] / "src" / "laplace"


# ---------------------------------------------------------------------------
# TEMPLATE FLOOR — band order + eager fetches, straight off guide.html.
# ---------------------------------------------------------------------------


def test_bare_root_serves_the_dashboard_not_a_redirect():
    """W1: the bare / route SERVES THE DASHBOARD (not a 302→/guide). The source proves
    the landing redirect is gone and the dashboard page is served in its place."""
    scanner = (_SRC / "web" / "scanner.py").read_text(encoding="utf-8")
    # the / branch no longer redirects to /guide; it serves the dashboard app bytes.
    root_branch = scanner.split('if u.path == "/":', 1)[1].split("elif u.path", 1)[0]
    assert "_redirect" not in root_branch, "the / landing redirect must be gone in W1"
    assert "_DASHBOARD_APP.read_bytes()" in root_branch, "bare / must serve the dashboard page"
    assert (_SRC / "web" / "dashboard.html").is_file(), "the dashboard surface must exist"








# ---------------------------------------------------------------------------
# LIVE SERVER — the redirect + the map kept alive (stdlib only, no browser).
# ---------------------------------------------------------------------------


def _serve():
    from laplace.web import scanner
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), scanner.make_handler())
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def _get(port: int, path: str) -> tuple[int, str, bytes]:
    """A raw GET that does NOT follow redirects → (status, Location, body-bytes)."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        body = resp.read()
        return resp.status, resp.getheader("Location") or "", body
    finally:
        conn.close()


def test_bare_root_serves_the_dashboard_live():
    """/ serves the dashboard page (200, real HTML) on a live server — no redirect. W-DASH
    re-baselined the surface to the composed BRIEF at rest: the entry is a thin shell that
    rests on the brief (``data-role="brief-prose"``) and rides the dashboard pane module; the
    card grid + New Project door now MATERIALISE behind one open (no longer static markers in
    the shell). The contract kept: 200, real HTML, built on the shared model."""
    httpd, port = _serve()
    try:
        status, _location, body = _get(port, "/")
        assert status == 200, f"bare / must serve the dashboard 200, got {status}"
        low = body.lower()
        assert b"<!doctype html" in low or b"<html" in low, "/ must serve an HTML page"
        # the resting altitude is the composed brief + its pane module (the inventory is
        # summonable, not resident) — the grid/New-Project door are materialised on open.
        assert b'data-role="brief-prose"' in body, "/ must rest on the composed brief"
        assert b"/shared/dashboard-panes.mjs" in body, "/ must ride the dashboard pane module"
        assert b"/shared/store.mjs" in body, "the dashboard must be built on the shared model"
    finally:
        httpd.shutdown()


def test_landing_did_not_orphan_the_map():
    """The map is not a dead door — the ROUTE stays live even after ACT5 ruled its nav ROW
    off the roster (shared_ui.py _VIEWS, 2026-07-21: the map is a view of the ENGINE, not a
    project's work, so it leaves the nav; the /map ROUTE keeps serving). So /map (plus the
    /index.html back-compat alias) still serves the brain scanner page (200) with no roster
    row pointing at it — a served survivor, not an orphan."""
    from laplace.web import shared_ui
    by_id = {v["id"]: v for v in shared_ui.views_roster()["views"]}
    assert "map" not in by_id, "ACT5 ruled the map row off the roster (nav is projects, not the engine)"

    httpd, port = _serve()
    try:
        for path in ("/map", "/index.html"):
            status, _, body = _get(port, path)
            assert status == 200, f"{path} must serve the brain scanner, got {status}"
            assert b"<!doctype html" in body.lower() or b"<html" in body.lower()
        # W5: the desk cockpit is its own live surface (the /guide explainer died).
        # W-DESK: the desk joined the one instrument — it now serves the engine root
        # (#eng-root, the focus runtime's mount), no longer the old #desk-rows queue.
        status, _, body = _get(port, "/desk")
        assert status == 200 and b'id="eng-root"' in body, "/desk must serve the desk cockpit page"
    finally:
        httpd.shutdown()
