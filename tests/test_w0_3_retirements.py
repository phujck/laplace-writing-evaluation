"""W0.3 — the retirements, fail-closed.

Each retired route returns EXACTLY its ruled status (301 with the correct
Location, or 410 GONE naming /projection); /network/* SURVIVES (200); no
surviving template still links a retired path; the content-negotiation branch
on bare /guide is dead (the page, not the legacy NAVIGATOR_GUIDE JSON).
"""
from __future__ import annotations

import http.client
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import pytest

from laplace.web import scanner


@pytest.fixture()
def tree(tmp_path, monkeypatch):
    (tmp_path / "src" / "laplace").mkdir(parents=True)
    (tmp_path / "src" / "laplace" / "alpha.py").write_text(
        '"""alpha - the doorway."""\ndef open_door():\n    return 1\n', encoding="utf-8")
    (tmp_path / "NOTES.md").write_text("# Notes\n\nSee [[alpha]].\n", encoding="utf-8")
    (tmp_path / "soul").mkdir()
    (tmp_path / "soul" / "0001.md").write_text("# private\n\nseal.\n", encoding="utf-8")
    monkeypatch.setattr(scanner, "_repo_root", lambda: tmp_path)
    scanner._GRAPH_CACHE.clear()
    scanner._TREE_CACHE.clear()
    return tmp_path


@pytest.fixture()
def server(tree):
    scanner._FIRINGS = scanner._FiringLog()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), scanner.make_handler())
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()


def _raw(base: str, path: str):
    """One request, redirects NOT followed — return (status, headers, body)."""
    u = urlparse(base)
    conn = http.client.HTTPConnection(u.hostname, u.port, timeout=15)
    conn.request("GET", path)
    r = conn.getresponse()
    body = r.read().decode("utf-8", "replace")
    hdrs = {k.lower(): v for k, v in r.getheaders()}
    conn.close()
    return r.status, hdrs, body


def test_navigator_redirects_301_to_altitude(server):
    status, hdrs, _ = _raw(server, "/navigator")
    assert status == 301
    assert hdrs.get("location") == "/altitude"


def test_conceptric2_redirects_301_to_conceptric(server):
    # W3 inverted the redirect: /conceptric is now THE surface page; the old /conceptric2
    # route is the retirement stub, 301'ing to /conceptric so deep-links still land.
    status, hdrs, _ = _raw(server, "/conceptric2")
    assert status == 301
    assert hdrs.get("location") == "/conceptric"


def test_conceptric_serves_the_surface_200(server):
    status, _, body = _raw(server, "/conceptric")
    assert status == 200
    # UPDATED TO CURRENT TRUTH (his fifth ruling, 2026-07-23: "the conceptric map is defined
    # by its links" — the drawn graph chart LEADS at /conceptric, conceptric-panes.mjs; the
    # growth cockpit survives whole at /conceptric/cockpit, doored from the map, L5).
    assert "conceptric-panes.mjs" in body


def test_conceptric_cockpit_survives_at_its_door(server):
    status, _, body = _raw(server, "/conceptric/cockpit")
    assert status == 200
    assert "cockpit-panes.mjs" in body


def test_editor_is_410_gone_naming_projection(server):
    status, _, body = _raw(server, "/editor")
    assert status == 410
    assert "/projection" in body


def test_network_survives_200(server):
    # RETIRED (W5 chrome-census kill; contract/tombstones.yaml "GET /network/"): the whole
    # /network/* family was killed as zero-consumer — scanner.py answers it 410 Gone, and the
    # self-model network is now served by /graph, /grades, /ring (the Map surface). What was
    # once "/network/meta survives 200" is updated to lock the ruled retirement: the family
    # answers 410, never 200.
    status, _, _ = _raw(server, "/network/meta")
    assert status == 410


# W5: the /guide page died (its desk rehoused to /desk; census W5). The legacy
# content-negotiation retirement it once guarded is moot — bare /guide now 404s.


def test_no_surviving_template_or_js_links_a_retired_path():
    root = Path(scanner.__file__).resolve().parent
    retired = ("/navigator", "/editor")
    offenders = []
    for f in list(root.glob("*.html")) + list((root / "static_shared").glob("*.js")):
        text = f.read_text(encoding="utf-8", errors="replace")
        for tok in retired:
            # a link/href, not a mere substring of /conceptric2 etc.
            if f'"{tok}"' in text or f"'{tok}'" in text or f"={tok}" in text \
                    or f"href={tok}" in text or f'href="{tok}"' in text:
                offenders.append((f.name, tok))
    # the retired conceptric route is now /conceptric2 (W3 inversion): match it exactly.
    # /conceptric (no trailing 2) is the LIVE surface page — surfaces legitimately link it.
    for f in list(root.glob("*.html")) + list((root / "static_shared").glob("*.js")):
        text = f.read_text(encoding="utf-8", errors="replace")
        for q in ('"/conceptric2"', "'/conceptric2'", 'href="/conceptric2"'):
            if q in text:
                offenders.append((f.name, "/conceptric2"))
    assert not offenders, f"surviving surface links a retired path: {offenders}"


def test_retired_templates_are_deleted():
    root = Path(scanner.__file__).resolve().parent
    for gone in ("scanner_navigator.html", "manuscript_editor.html", "conceptric_editor.html"):
        assert not (root / gone).exists(), f"retired template still on disk: {gone}"


# W5: the guide STAGES retired-path guard retired WITH the STAGES table (the /guide
# explainer died). The desk's own deep-links avoid retired paths — every desk href
# resolves to a live scanner route (tests/test_guide.py::test_desk_no_row_href_is_a_dead_anchor).
