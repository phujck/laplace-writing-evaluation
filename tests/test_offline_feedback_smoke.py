"""The claim-check for OFFLINE feedback capture — the seam must survive the two
things the author's setup guarantees: NO network (no orchestrator, no CDN) and
CONCURRENT writers (his own editor plus a drained remote inbox, or several
browser tabs on one Windows box).

Three legs, each the honest test of one claim:

1. **end-to-end over real HTTP** — a comment POSTed to ``/review/adjudicate``
   (verb=comment, actor-attributed) lands in ``feedback/feedback.jsonl`` with
   the right record shape, driven through the scanner's own ThreadingHTTPServer
   (the surface the author actually hits), NO orchestrator in the loop.

2. **concurrency** — N threads appending feedback at once all land, and every
   line json-parses (no torn/interleaved write). This is the lock's proof:
   ``ledger.append_jsonl`` serialises the append across writers.

3. **offline-guard** — every review/editor HTML page loads its assets from the
   vendored ``/shared`` tree, never an ``http(s)://`` CDN, so the pages render
   with no network. A grep-assert scoped to ``<script>`` / ``<link>`` tags (an
   ``xmlns`` namespace or a prose anchor is not an asset ref).

Windows discipline: pathlib throughout, no POSIX-only constructs.
"""

from __future__ import annotations

import json
import re
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from laplace.manuscript import manuscript_bridge
from laplace.web import scanner


_REPO_ROOT = Path(__file__).resolve().parents[1]
_HTML_DIR = _REPO_ROOT / "src" / "laplace"

# the review/editor surfaces the author drives offline. W0.3 retired
# scanner_navigator.html + manuscript_editor.html; W2 CONSOLIDATED review_surface.html +
# projection_viewer.html into the ONE artefact surface (artefact.html + its shared pane module).
_OFFLINE_PAGES = (
    "artefact.html",
    "conceptric.html",   # W3: conceptric_editor2.html -> conceptric.html (rebuilt on the model)
)


# ---------------------------------------------------------------------------
# 1. end to end over real HTTP — a comment lands in feedback.jsonl
# ---------------------------------------------------------------------------

def _post(url: str, body: dict) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


def test_comment_posts_land_in_feedback_ledger_over_http(tmp_path, monkeypatch):
    # the manuscript dir must resolve INSIDE the repo root; point the root at
    # tmp_path so the whole exchange stays in the sandbox (review_surface reads
    # scanner._repo_root fresh on each call, so the patch is honoured).
    monkeypatch.setattr(scanner, "_repo_root", lambda: tmp_path)
    md = tmp_path / "ms"
    md.mkdir(parents=True)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), scanner.make_handler())
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        res = _post(
            f"http://127.0.0.1:{port}/review/adjudicate",
            {"verb": "comment", "by": "gerard", "dir": "ms",
             "section": "intro", "comment": "the derivation skips a step here"},
        )
    finally:
        httpd.shutdown()

    assert res.get("ok") is True, res
    assert res.get("verb") == "comment"

    ledger = md / "feedback" / "feedback.jsonl"
    assert ledger.is_file(), "the POST must have created the feedback ledger"
    lines = [ln for ln in ledger.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["by"] == "gerard"
    assert rec["comment"] == "the derivation skips a step here"
    assert rec["node_id"] == "intro"
    assert rec["kind"] == "comment"
    assert rec["status"] == "open"


def test_adjudicate_refuses_unattributed_comment_over_http(tmp_path, monkeypatch):
    """The actor guard holds over the wire: an unattributed comment (no ``by``)
    is refused BEFORE any append — the offline door never mints a verdict for a
    caller that names no actor."""
    monkeypatch.setattr(scanner, "_repo_root", lambda: tmp_path)
    md = tmp_path / "ms"
    md.mkdir(parents=True)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), scanner.make_handler())
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/review/adjudicate",
            data=json.dumps({"verb": "comment", "dir": "ms",
                             "section": "intro", "comment": "no actor"}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with pytest.raises(urllib.error.HTTPError) as ei:
            urllib.request.urlopen(req, timeout=5)
        assert ei.value.code == 422
    finally:
        httpd.shutdown()

    assert not (md / "feedback" / "feedback.jsonl").is_file()


# ---------------------------------------------------------------------------
# 2. concurrency — N writers, every line whole
# ---------------------------------------------------------------------------

def test_concurrent_feedback_writers_all_land_intact(tmp_path):
    ledger = tmp_path / "feedback" / "feedback.jsonl"
    n = 16
    # a fat comment widens the write window: without the lock, interleaved
    # writes tear the line, so the json.loads below would fail.
    filler = "x" * 4096
    barrier = threading.Barrier(n)          # fire all writers at once
    errors: list[Exception] = []

    def _writer(i: int) -> None:
        try:
            barrier.wait()
            out = manuscript_bridge.feedback_add(
                tmp_path, "proj",
                {"node_id": f"node-{i}", "comment": f"{i}:{filler}", "by": "gerard"},
                ledger=ledger)
            assert out.get("ok") is True, out
        except Exception as exc:            # noqa: BLE001 — surfaced to the assert below
            errors.append(exc)

    threads = [threading.Thread(target=_writer, args=(i,)) for i in range(n)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()

    assert not errors, errors
    lines = [ln for ln in ledger.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == n, f"expected {n} records, got {len(lines)}"
    seen = set()
    for ln in lines:
        rec = json.loads(ln)               # every line must be whole JSON (no tear)
        seen.add(rec["node_id"])
    assert seen == {f"node-{i}" for i in range(n)}, "all 16 distinct writers must land"


# ---------------------------------------------------------------------------
# 3. offline-guard — no CDN asset refs in the surfaces
# ---------------------------------------------------------------------------

_TAG_RE = re.compile(r"<(?:script|link)\b[^>]*>", re.IGNORECASE)
_HTTP_ASSET_RE = re.compile(r"""(?:src|href)\s*=\s*["']https?://""", re.IGNORECASE)


@pytest.mark.parametrize("page", _OFFLINE_PAGES)
def test_surface_has_no_cdn_asset_refs(page):
    text = (_HTML_DIR / page).read_text(encoding="utf-8")
    offenders = [tag for tag in _TAG_RE.findall(text) if _HTTP_ASSET_RE.search(tag)]
    assert not offenders, (
        f"{page} loads assets from an http(s) CDN (must be vendored under "
        f"/shared): {offenders}")
