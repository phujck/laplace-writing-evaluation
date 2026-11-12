"""WAVE F · R6 — NO SERVED ROUTE CARRIES A MOCK-ONLY ARTIFACT.

REDLINES_2026-07-16 R6 (his behalf): *"the D-tags are mock-only. Obvious, but
assert it mechanically in the fleet (Wave F) so a redline tag can never leak onto a
served surface."* The mocks (``mocks/*.html``, PR #72) carry the review scaffold — the
in-situ **D-tags** (``data-d="D1"`` … ``data-d="D16"``, ``class="rl-tag"``) and the
**redline box** (``rl-box``/``rl-tab``/``rl-row``/``rl-tags-off`` …). None of that is a
served surface: it is the reviewer's overlay, and it must never reach a page the scanner
serves or a shared JS/CSS module a served page pulls.

Two teeth (deliverable #2, the grep half; the rendered-DOM half rides
``tests/waveF_seal.playwright.mjs``):

  1. **the served route bodies** — every rostered route's live HTML (fetched from the
     real scanner, the palette-test harness) carries ZERO mock-only tokens;
  2. **the shared/served SOURCE tree** — every ``.html/.js/.mjs/.css`` under
     ``src/laplace`` (the templates + the shared shell/store/panes + hymn.css, minus the
     vendored ``pdfjs``/``katex`` blobs) carries ZERO mock-only tokens.

Proven to BITE on the real positive control (``mocks/artefact.html`` carries the tags)
and on a planted tmp string — so the day a redline tag is copied from a mock into a
served template, this clause already fails. The mocks themselves are NOT under
``src/laplace`` and are never served, so they are out of scope by construction.
"""
from __future__ import annotations

import http.client
import re
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[1]
_SRC = _REPO / "src" / "laplace"
_MOCKS = _REPO / "mocks"

# ── the mock-only artifact grammar ────────────────────────────────────────────
# Each pattern is a token that exists ONLY to serve the review overlay: the in-situ
# D-tags (the decision markers + their jump attribute) and the redline box chrome.
# Matched in CLASS / SELECTOR / ATTRIBUTE context so a chance substring in minified
# vendor code (e.g. "rl-decode") cannot false-positive.
_RL_CLASSES = ("tag", "box", "tab", "head", "title", "row", "chk", "txt",
               "fix", "foot", "master", "list", "sub")
_MOCK_ARTIFACT_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("D-tag attribute (data-d)", re.compile(r'data-d\s*=\s*"D\d')),
    ("redline-row attribute (data-drow)", re.compile(r'data-drow\s*=\s*"')),
    ("redline body toggler (rl-tags-off)", re.compile(r'\brl-tags-off\b')),
    ("redline box id (rlBox/rlTab)", re.compile(r'\bid\s*=\s*"rl(?:Box|Tab)\b')),
    # rl-* used as an HTML class, a JS className, or a CSS selector — never a bare substr
    ("redline box class (rl-*)",
     re.compile(r'(?:class\s*=\s*"[^"]*\b|className[^"]*"[^"]*\b|\.)'
                r'rl-(?:' + "|".join(_RL_CLASSES) + r')\b')),
]

# vendored blobs are not ours and are never a mock surface — excluded by path
_VENDORED = ("pdfjs", "katex")
_SCANNED_SUFFIXES = (".html", ".js", ".mjs", ".css")


def _served_source_files() -> list[Path]:
    """Every served/shared source file under ``src/laplace`` (templates + shell/store/
    panes + hymn.css), minus the vendored viewer blobs. This is the concrete file set a
    served route's HTML/JS is authored from."""
    out: list[Path] = []
    for p in sorted(_SRC.rglob("*")):
        if not p.is_file() or p.suffix not in _SCANNED_SUFFIXES:
            continue
        if any(v in p.parts for v in _VENDORED) or ".min." in p.name:
            continue
        out.append(p)
    return out


def _hits(text: str) -> list[str]:
    """Every mock-artifact pattern that matches ``text``, by human name (deduped)."""
    return [name for name, pat in _MOCK_ARTIFACT_PATTERNS if pat.search(text)]


# ── the roster + live-server harness (the palette-test idiom) ─────────────────

def _roster_paths() -> list[dict]:
    from laplace.web import shared_ui
    return shared_ui.views_roster()["views"]


@pytest.fixture(scope="module")
def server():
    from laplace.web import scanner
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), scanner.make_handler())
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1]
    httpd.shutdown()


def _get_body(port: int, path: str) -> str:
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    try:
        c.request("GET", path)
        r = c.getresponse()
        return r.read().decode("utf-8", "replace")
    finally:
        c.close()


# ═══════════════════════════════════════════════════════════════════════════
# the teeth — the grammar BITES on the real mock + a planted string
# ═══════════════════════════════════════════════════════════════════════════

def test_the_grammar_bites_the_real_mock_control():
    """``mocks/artefact.html`` (the review overlay, PR #72) carries the D-tags + the
    redline box — so the grammar is proven live, not a no-op that passes vacuously."""
    mock = _MOCKS / "artefact.html"
    assert mock.is_file(), "the positive-control mock is missing — cannot prove teeth"
    hits = _hits(mock.read_text(encoding="utf-8"))
    assert "D-tag attribute (data-d)" in hits, \
        f"the grammar failed to detect the mock's own D-tags (hits={hits})"
    assert "redline box class (rl-*)" in hits, \
        f"the grammar failed to detect the mock's own redline box (hits={hits})"


def test_the_grammar_bites_a_planted_string():
    """A planted redline tag is caught — the drift-proof form (a no-op check would let a
    real leak through for the wrong reason)."""
    planted = '<span class="rl-tag" data-d="D3" title="D3 — see REDLINES">D3</span>'
    assert _hits(planted), "the grammar missed a planted D-tag — it has no teeth"


# ═══════════════════════════════════════════════════════════════════════════
# R6 — no served route body, no served source file, carries a mock-only artifact
# ═══════════════════════════════════════════════════════════════════════════

def test_no_served_route_body_carries_a_mock_artifact(server):
    """Every rostered route's LIVE served HTML is clean of the mock overlay."""
    dirty: list[tuple[str, str, list[str]]] = []
    for v in _roster_paths():
        body = _get_body(server, v["path"])
        hits = _hits(body)
        if hits:
            dirty.append((v["id"], v["path"], hits))
    assert not dirty, f"served route bodies carrying mock-only artifacts (R6): {dirty}"


def test_no_served_source_file_carries_a_mock_artifact():
    """Every served/shared SOURCE file under src/laplace is clean of the mock overlay —
    so a redline tag cannot hide in a template, a shared pane, or hymn.css and only
    surface under some code path the live-body sweep did not exercise."""
    files = _served_source_files()
    assert files, "the served-source enumeration found nothing — the sweep is vacuous"
    dirty: list[tuple[str, list[str]]] = []
    for p in files:
        hits = _hits(p.read_text(encoding="utf-8", errors="replace"))
        if hits:
            dirty.append((str(p.relative_to(_REPO)), hits))
    assert not dirty, f"served source files carrying mock-only artifacts (R6): {dirty}"


def test_the_enumeration_actually_covers_the_shared_chrome():
    """A green above is real coverage: the served-source set MUST contain the shared
    chrome (shell.js, hymn.css) and the surface templates — the exact files a leak would
    ride. A degenerate/empty set could pass the sweep for the wrong reason."""
    names = {p.name for p in _served_source_files()}
    for must in ("shell.js", "hymn.css", "desk.html", "conceptric.html"):
        assert must in names, f"the served-source enumeration lost {must!r} — coverage regressed"
