"""GET /project/doc — the GENERAL manuscript-doc route (W-brief-door, 2026-07-23).

His ruling (banked RW-20260723-154721-984120, verbatim): "I can't read the brief...
it's a shame the read the brief doesn't hook in. I'm also worried that this option
has been made bespoke rather than a mechanical consequence." The old
``pipeline_surface._brief_door`` emitted a ``file://`` deep-link — dead from an http
page in every browser. The fix: ONE read-only route, scanner.py's
``GET /project/doc?corpus=<name>|dir=<repo-relative>&path=<manuscript-relative>``,
that ``_brief_door`` now points at — the SAME resolver (``review_surface.manuscript_dir``)
every review-family route already uses, so the door is a mechanical consequence of
that resolver, never a bespoke construction.

Contract exercised here:
  * the manuscript dir resolves via ``dir=`` (repo-relative, mirrors
    ``review_surface.manuscript_dir``'s own dual corpus/dir signature) or ``corpus=``;
  * the served path is STRICTLY fenced inside the manuscript dir — an escape (``..``
    or an absolute path) 403s, never silently clamped;
  * only whitelisted text-like extensions render (md/txt/json/yaml/yml/tex/log);
    anything else 404s even when the file exists on disk (no accidental binary serve);
  * ``.md`` renders as ``text/markdown``, the rest as ``text/plain`` — both readable
    inline in a browser tab, never downloaded;
  * no directory listing (a bare dir path 404s, never enumerates);
  * end-to-end: ``pipeline_surface._brief_door``'s own href, fired at this route,
    actually resolves the brief's real content — the "hook in" his ruling named.
"""
from __future__ import annotations

import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from laplace.web import pipeline_surface as ps
from laplace.web import scanner

pytestmark = pytest.mark.unit


def _serve(monkeypatch, repo_root):
    """A scanner HTTP server whose repo root is pinned to ``repo_root`` — the same
    idiom ``test_feedback_actor_law.py`` uses (``monkeypatch.setattr(scanner,
    "_repo_root", ...)``), so ``review_surface.manuscript_dir``'s ``dir=`` resolution
    (which delegates back through ``scanner._repo_root``) lands inside the tmp tree."""
    monkeypatch.setattr(scanner, "_repo_root", lambda: repo_root)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), scanner.make_handler())
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd, port


def _get(url: str):
    """Returns (status, content_type, body_bytes); never raises on a non-2xx status —
    the fence/whitelist clauses below assert on 403/404 bodies too."""
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", ""), e.read()


@pytest.fixture
def manuscript(tmp_path):
    """``<tmp_path>/manuscript/`` with a real brief, a nested one, a non-text asset,
    and a sibling doc OUTSIDE the manuscript dir (but still inside the repo root) —
    the exact shape that proves containment is fenced to the MANUSCRIPT dir, not
    merely the repo root."""
    md = tmp_path / "manuscript"
    (md / "reprojection").mkdir(parents=True)
    (md / "reprojection" / "gen4_brief.md").write_text(
        "# gen-4 brief\n\nthe next generation, in plain words.\n", encoding="utf-8")
    (md / "notes.txt").write_text("plain notes\n", encoding="utf-8")
    (md / "figure.png").write_bytes(b"\x89PNG\r\n\x1a\nnot text")
    (tmp_path / "sibling_outside.md").write_text("outside the manuscript dir\n",
                                                  encoding="utf-8")
    return tmp_path, md


# --------------------------------------------------------------------------- #
# the fence: an escape (.. or an absolute path) 403s, never a silent clamp
# --------------------------------------------------------------------------- #

def test_escape_attempt_403s(manuscript, monkeypatch):
    tmp_path, _md = manuscript
    httpd, port = _serve(monkeypatch, tmp_path)
    try:
        # a doc that is real, on disk, INSIDE the repo root, but OUTSIDE the
        # manuscript dir — proves the fence is the manuscript dir, not the repo root.
        status, _ct, body = _get(
            f"http://127.0.0.1:{port}/project/doc?dir=manuscript&path=../sibling_outside.md")
        assert status == 403, body
    finally:
        httpd.shutdown()


def test_absolute_path_escape_403s(manuscript, monkeypatch):
    tmp_path, _md = manuscript
    httpd, port = _serve(monkeypatch, tmp_path)
    try:
        status, _ct, body = _get(
            f"http://127.0.0.1:{port}/project/doc?dir=manuscript&path=/etc/passwd")
        assert status == 403, body
    finally:
        httpd.shutdown()


# --------------------------------------------------------------------------- #
# a real brief 200s, with a content-type that RENDERS (never downloads)
# --------------------------------------------------------------------------- #

def test_real_brief_200s_as_markdown(manuscript, monkeypatch):
    tmp_path, _md = manuscript
    httpd, port = _serve(monkeypatch, tmp_path)
    try:
        status, ctype, body = _get(
            f"http://127.0.0.1:{port}/project/doc?dir=manuscript&path=reprojection/gen4_brief.md")
        assert status == 200, body
        assert ctype.startswith("text/markdown")
        assert "charset=utf-8" in ctype
        assert b"gen-4 brief" in body
    finally:
        httpd.shutdown()


def test_real_txt_doc_200s_as_plain_text(manuscript, monkeypatch):
    tmp_path, _md = manuscript
    httpd, port = _serve(monkeypatch, tmp_path)
    try:
        status, ctype, body = _get(
            f"http://127.0.0.1:{port}/project/doc?dir=manuscript&path=notes.txt")
        assert status == 200, body
        assert ctype.startswith("text/plain")
        assert b"plain notes" in body
    finally:
        httpd.shutdown()


def test_corpus_param_also_resolves(manuscript, monkeypatch):
    """``corpus=`` (the WO's headline contract) resolves through the SAME
    ``review_surface.manuscript_dir`` the ``dir=`` clauses above exercise."""
    tmp_path, md = manuscript
    from laplace.manuscript import review_surface as rs
    monkeypatch.setattr(rs, "manuscript_dir",
                         lambda corpus, dir_param="": md if corpus == "proj" else None)
    httpd, port = _serve(monkeypatch, tmp_path)
    try:
        status, ctype, body = _get(
            f"http://127.0.0.1:{port}/project/doc?corpus=proj&path=notes.txt")
        assert status == 200, body
        assert ctype.startswith("text/plain")
        assert b"plain notes" in body
        # an unregistered corpus name resolves to nothing — honest 404, no listing
        status, _ct, body = _get(
            f"http://127.0.0.1:{port}/project/doc?corpus=nope&path=notes.txt")
        assert status == 404, body
    finally:
        httpd.shutdown()


# --------------------------------------------------------------------------- #
# the whitelist: a non-text extension 404s even though the file is real
# --------------------------------------------------------------------------- #

def test_non_whitelisted_extension_404s_even_though_the_file_exists(manuscript, monkeypatch):
    tmp_path, md = manuscript
    assert (md / "figure.png").is_file()          # the file genuinely exists on disk
    httpd, port = _serve(monkeypatch, tmp_path)
    try:
        status, _ct, body = _get(
            f"http://127.0.0.1:{port}/project/doc?dir=manuscript&path=figure.png")
        assert status == 404, body
    finally:
        httpd.shutdown()


def test_missing_file_404s(manuscript, monkeypatch):
    tmp_path, _md = manuscript
    httpd, port = _serve(monkeypatch, tmp_path)
    try:
        status, _ct, body = _get(
            f"http://127.0.0.1:{port}/project/doc?dir=manuscript&path=reprojection/nope.md")
        assert status == 404, body
    finally:
        httpd.shutdown()


def test_unknown_dir_404s_no_directory_listing(manuscript, monkeypatch):
    """No ``dir=``/``corpus=`` at all, or a bare directory path (no ``path=``) —
    both honest-404, never an enumeration of what's inside."""
    tmp_path, _md = manuscript
    httpd, port = _serve(monkeypatch, tmp_path)
    try:
        status, _ct, body = _get(f"http://127.0.0.1:{port}/project/doc?path=notes.txt")
        assert status == 404, body
        status, _ct, body = _get(f"http://127.0.0.1:{port}/project/doc?dir=manuscript")
        assert status == 404, body
    finally:
        httpd.shutdown()


# --------------------------------------------------------------------------- #
# END-TO-END: the door _brief_door hands out actually resolves — the "hook in"
# his ruling named. This is the wiring proof, not just the route in isolation.
# --------------------------------------------------------------------------- #

def test_brief_door_href_actually_resolves_through_the_route(manuscript, monkeypatch):
    tmp_path, md = manuscript
    monkeypatch.setattr(scanner, "_repo_root", lambda: tmp_path)
    door = ps._brief_door(md, "reprojection/gen4_brief.md")
    assert door is not None
    assert door["href"].startswith("/project/doc?"), \
        "the brief must be the general route, not a bespoke file:// link"

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), scanner.make_handler())
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        status, ctype, body = _get(f"http://127.0.0.1:{port}{door['href']}")
        assert status == 200, (door["href"], body)
        assert ctype.startswith("text/markdown")
        assert b"gen-4 brief" in body
    finally:
        httpd.shutdown()
