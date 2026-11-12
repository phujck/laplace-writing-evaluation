"""W6.3 — THE CROSS-SESSION INVARIANT: every derived read names producer + freshness.

Two tiers.

TIER 1 — THE CENSUS ASSERT (unit, always runs, no browser). The W1.2 staleness
registry (``shared_ui.staleness``) is THE census of the derived reads the surfaces
consume. This tier proves EVERY registry row carries all four W6.3 fields
({producer, built_ts, fresh, fix}) — plus the render helpers — and that the one read
that had ESCAPED the census (the banked graded self-tree the map/conceptric serve
through ``conceptric.load_network``) is now folded in, so no derived read the serving
path consumes degrades unnamed.

TIER 2 — THE STRIP-AND-DRIVE (slow; skips only when no Chromium build is present).
Copies the repo tree to tmp MINUS the derived/tracked caches (the audit's rebuildable
class — localstate.json's entries + the tracked router/metric/self-graph caches; the
untracked ones, voice-store / nodemaps / embed extract, are already absent from a
git-archive tree), boots the scanner against the stripped tree, and drives every roster
surface headless proving:
  (i)  NO SILENT DEGRADE — every roster surface renders (never blank, never a page
       error), and every panel wired to the staleness atom shows the ``.hy-stale`` atom
       naming producer + fix for each stripped read;
  (ii) NO UNPROMPTED REBUILD — the drive fires ZERO write requests (POST/PUT/DELETE/
       PATCH), ZERO heavy builders, ZERO rebuild subprocess, and NOT ONE stripped cache
       file reappears (the offer law: the fix is NAMED, never fired).
"""
from __future__ import annotations

import re
import shutil
import subprocess
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from laplace.web import shared_ui

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[1]

# the four fields W6.3 requires on EVERY derived read, plus the render/derived helpers.
_FOUR = {"producer", "built_ts", "fresh", "fix"}
_ALL = _FOUR | {"id", "label", "scope", "present", "reason", "degraded"}

# the tracked derived caches (the rebuildable class). git archive already omits the
# untracked members (voice-store, per-corpus nodemaps, the embed-model extract), so
# stripping these completes the "rebuildable class removed" tree.
_STRIP = [
    ".self_graded.json", ".self_embeddings.json", ".metric_M.npz",
    # the residue-vector store: the legacy monolith AND the 2026-08-20 sidecar pair that replaced
    # it (MV-1). All three are gitignored, so git archive already omits them and these entries are
    # belt-and-braces - but the family MUST be named in full here, or a rename silently turns this
    # row into a no-op and the strip-and-drive stops testing this artifact's graceful degrade.
    ".meaning_vectors.json", ".meaning_vectors.f32.npy", ".meaning_vectors.index.json",
    ".meaning_tree.json",
    "eigenengine/manuscript/rounds", "paper_falqon/manuscript/rounds",
]

_CORPUS = "eigenengine"

# ═══════════════════════════════════════════════════════════════════════════
# TIER 1 — THE CENSUS ASSERT (no browser).
# ═══════════════════════════════════════════════════════════════════════════


def _all_reads() -> list[dict]:
    """Every census row, global AND per-corpus, against the LIVE repo."""
    reads = list(shared_ui.staleness("")["reads"])
    reads += list(shared_ui.staleness(_CORPUS)["reads"])
    return reads


def test_every_census_row_carries_the_four_fields():
    """The fail-closed census assert: every staleness-registry row carries
    {producer, built_ts, fresh, fix} — a producer and a fix that are NON-EMPTY strings,
    a boolean fresh, and the built_ts key present (a value or an honest None)."""
    reads = _all_reads()
    assert reads, "the census must return derived reads"
    for r in reads:
        assert _ALL <= set(r), f"{r.get('id')} missing census fields: {_ALL - set(r)}"
        assert isinstance(r["producer"], str) and r["producer"].strip(), \
            f"{r['id']}: producer must be a non-empty string"
        assert isinstance(r["fix"], str) and r["fix"].strip(), \
            f"{r['id']}: fix must name a gesture"
        assert isinstance(r["fresh"], bool), f"{r['id']}: fresh must be a bool"
        assert "built_ts" in r, f"{r['id']}: built_ts key must be present"


def test_a_degraded_row_names_producer_and_fix_never_a_silent_zero():
    """The invariant's teeth: a stripped (absent) read reports degraded and NAMES its
    reason, producer, and fix — never a silent 0. Checked against a bare tmp root where
    every global read is absent."""
    for r in shared_ui.staleness("", repo_root=Path("/nonexistent_w63_root_xyz"))["reads"]:
        assert r["degraded"] is True and r["fresh"] is False
        assert r["reason"], f"{r['id']}: a degraded read must carry a reason"
        assert r["producer"], f"{r['id']}: a degraded read must name its producer"
        assert r["fix"], f"{r['id']}: a degraded read must name the fix"


def test_the_escaped_self_graph_is_folded_into_the_census():
    """The one read that had escaped: the banked graded self-tree the roster surfaces
    consume through conceptric.load_network. It now rides the GLOBAL census, degraded
    when absent (naming keeper as producer + the close-deposit fix), fresh when present."""
    ids = {r["id"] for r in shared_ui.staleness("")["reads"]}
    assert "self_graph" in ids, "the graded self-tree must be in the census (W6.3)"
    absent = shared_ui.read_self_graph(Path("/nonexistent_w63_root_xyz"))
    assert absent["degraded"] is True and "keeper" in absent["producer"] and absent["fix"]


def test_the_census_names_the_serving_derived_reads():
    """A guard on census completeness: the global reads are exactly the derived caches
    the serving path consumes without a per-surface freshness idiom of its own, and the
    per-corpus reads join when a corpus is named. A NEW derived read a surface starts
    consuming must be added here (this is the census W6.3 makes the single source)."""
    glob = {r["id"] for r in shared_ui.staleness("")["reads"]}
    assert glob == {"self_graph", "router_cache", "metric", "voice_store"}
    corp = {r["id"] for r in shared_ui.staleness(_CORPUS)["reads"]}
    assert {"nodemap", "plan_prose"} <= corp


# ═══════════════════════════════════════════════════════════════════════════
# TIER 2 — THE STRIP-AND-DRIVE (slow; boots the scanner against a stripped tree).
#
# The PRIMARY drive (``test_strip_and_drive``) is HEADLESS over stdlib HTTP — no
# browser — so it RUNS in any CI (including this box, where Playwright is not in the
# venv). It boots the scanner against the stripped tree, GETs every roster surface +
# the staleness contract, and proves (i) no surface blanks/crashes, every stripped read
# is reported DEGRADED and NAMED (producer + fix), and the atom-wired surfaces carry the
# wiring that renders it; (ii) the offer law — the GET drive fires zero heavy builders,
# zero rebuild subprocess, and not one stripped cache reappears. A SECONDARY drive
# (``test_strip_and_drive_renders_in_browser``) adds the client-render proof under
# Chromium — it skips (with reason) when no browser/Playwright is present.
# ═══════════════════════════════════════════════════════════════════════════

_CHROME_CANDIDATES = (list(Path("/opt/pw-browsers").glob("chromium-*/chrome-linux/chrome"))
                      + list(Path("/opt/pw-browsers").glob("chromium-*/chrome-linux64/chrome")))
_CHROME = str(_CHROME_CANDIDATES[0]) if _CHROME_CANDIDATES else None

# every roster surface (shared_ui._VIEWS), with the URL to drive it at. W6: the standalone
# /dials PAGE folded into /pipeline (dials.html deleted, the bare route 301s) — the roster
# row is "pipeline" now, driven at /pipeline; the redirect + the still-live /dials/* wire
# endpoints are proven separately below (test_strip_and_drive), not as a roster GET.
_ROSTER = [
    ("map", "/map"),
    ("conceptric", f"/conceptric?corpus={_CORPUS}"),
    ("storyboard", f"/storyboard?corpus={_CORPUS}"),
    # W2: projection + review consolidated into the ONE artefact surface.
    ("artefact", f"/artefact?corpus={_CORPUS}"),
    ("pipeline", "/pipeline"),
    ("desk", "/desk"),
    ("analytics", "/analytics"),
    ("altitude", f"/altitude?corpus={_CORPUS}"),
]

# the panels wired to the SHARED staleness atom (they must show a stripped read named).
# W5: /guide died — its global staleness strip died with it (the alarm walls became
# per-card offer chips + surface ⓘ states; conception §3). /analytics still renders the
# GLOBAL reads (incl. the folded-in self_graph), so its strip turns on and names
# producer + fix. (map/conceptric/pipeline/altitude/desk do not consume the shared atom;
# projection carries its own per-surface .hy-stale rows — this tier proves they never
# blank/crash and never rebuild, which is their W6.3 obligation.)
_ATOM_SURFACES = {"analytics"}

# rebuild commands that must NEVER fire from a pure GET drive (the offer law).
_REBUILD_RE = re.compile(
    r"latexmk|pdflatex|laplace\.keeper|metric_distill|reembed|ensure_state|"
    r"voice_corpus_ingest|build_nodemap")


def _build_stripped_tree(dst: Path) -> None:
    """A faithful cold clone MINUS the rebuildable class: a tracked-only snapshot
    (git archive already omits the untracked caches — voice-store, per-corpus nodemaps,
    the embed extract) with the tracked derived caches then removed."""
    dst.mkdir(parents=True, exist_ok=True)
    subprocess.run(f"git -C {_REPO} archive HEAD | tar -x -C {dst}",
                   shell=True, check=True)
    for rel in _STRIP:
        p = dst / rel
        if p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()


def _install_offer_law_sentinels(monkeypatch):
    """FAIL-CLOSED sentinels: any heavy rebuild from a GET aborts loudly, and every
    subprocess is recorded so a rebuild-class spawn is caught. Returns (fired, subp)."""
    from laplace.representation import embed_router as er
    from laplace.engine import keeper
    from laplace.manuscript import review_surface as rv
    from laplace.manuscript import storyboard as sb
    from laplace.pipeline import nodemap as nm

    fired: list[str] = []

    def _boom(name):
        def w(*a, **k):
            fired.append(name)
            raise AssertionError(f"W6.3: a GET fired the heavy builder {name} — offer law violated")
        return w

    monkeypatch.setattr(keeper, "build_self", _boom("keeper.build_self"))
    monkeypatch.setattr(nm, "build_nodemap", _boom("nodemap.build_nodemap"))
    monkeypatch.setattr(rv, "rebuild", _boom("review_surface.rebuild"))
    monkeypatch.setattr(sb, "rebuild", _boom("storyboard.rebuild"))
    monkeypatch.setattr(er, "route", _boom("embed_router.route"))

    subp: list[str] = []
    _orig_run, _orig_popen = subprocess.run, subprocess.Popen

    def _rec(orig):
        def w(*a, **k):
            argv = a[0] if a else k.get("args")
            subp.append(argv if isinstance(argv, str) else " ".join(map(str, argv or [])))
            return orig(*a, **k)
        return w

    monkeypatch.setattr(subprocess, "run", _rec(_orig_run))
    monkeypatch.setattr(subprocess, "Popen", _rec(_orig_popen))
    return fired, subp


def _boot(tree: Path, monkeypatch):
    from laplace.web import scanner
    monkeypatch.setattr(scanner, "_repo_root", lambda: tree)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), scanner.make_handler())
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def _assert_offer_law_held(fired, subp, tree):
    assert not fired, f"heavy builders fired from a GET drive: {fired}"
    rebuilds = [c for c in subp if _REBUILD_RE.search(c)]
    assert not rebuilds, f"the drive fired rebuild subprocess(es): {rebuilds}"
    reappeared = [rel for rel in _STRIP if (tree / rel).exists()]
    assert not reappeared, f"stripped caches were rebuilt during the drive: {reappeared}"


def test_strip_and_drive(tmp_path, monkeypatch):
    """THE STRIP-AND-DRIVE (headless, stdlib — runs everywhere). Strip the rebuildable
    class, boot the scanner against the stripped tree, drive every roster surface, and
    prove no silent degrade + no unprompted rebuild."""
    import http.client

    tree = tmp_path / "stripped"
    _build_stripped_tree(tree)
    for rel in _STRIP:
        assert not (tree / rel).exists(), f"strip failed: {rel} still present"

    fired, subp = _install_offer_law_sentinels(monkeypatch)
    httpd, port = _boot(tree, monkeypatch)

    def _get(path):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
        try:
            conn.request("GET", path)
            r = conn.getresponse()
            return r.status, r.getheader("Location"), r.read()
        finally:
            conn.close()

    try:
        # (i) EVERY roster surface renders — a 200 with a real HTML document, never a
        # blank body or a 5xx crash against the stripped tree.
        for name, path in _ROSTER:
            status, loc, body = _get(path)
            # a roster row that 301s to a LIVE successor is a live door — follow one hop
            # (W-TRIAGE 2026-07-22: the pipeline row keeps its /pipeline label but 301s to
            # /project, the ACTUAL cockpit page — contract/tombstones.yaml '/pipeline 301s HERE').
            if status in (301, 302) and loc:
                status, _loc2, body = _get(loc)
            assert status == 200, f"{name} ({path}) degraded to HTTP {status} on the stripped tree"
            low = body.lower()
            assert b"<!doctype html" in low or b"<html" in low, f"{name}: not an HTML document"
            assert len(body) > 500, f"{name}: blank/near-empty page ({len(body)} bytes)"

        # (i) W6: the standalone /dials PAGE folded into /pipeline — the bare route 301s
        # (never a silent 200/404) and names the successor in Location, even against the
        # stripped tree; /pipeline itself is proven live above via the roster loop.
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
        try:
            conn.request("GET", "/dials")
            r = conn.getresponse()
            assert r.status == 301, f"/dials degraded to HTTP {r.status} on the stripped tree"
            assert r.getheader("Location") == "/pipeline", \
                f"/dials redirected somewhere other than /pipeline: {r.getheader('Location')!r}"
            r.read()
        finally:
            conn.close()
        # the dials CONJUGATE's wire endpoints (state/op/undo) remain live — only the bare
        # page died, the write path dials_surface owns is untouched by the W6 fold.
        status, _l, body = _get("/dials/state")
        assert status == 200, f"/dials/state degraded to HTTP {status} on the stripped tree"
        import json as _json
        state = _json.loads(body)
        assert "profile" in state and "merged" in state, \
            "/dials/state must still answer with dials state on the stripped tree"

        # (i) THE STALENESS CONTRACT reports every stripped read DEGRADED and NAMED.
        import json
        for corpus in ("", _CORPUS):
            q = f"?corpus={corpus}" if corpus else ""
            status, _l, body = _get(f"/shared/staleness{q}")
            assert status == 200
            payload = json.loads(body)
            degraded = [r for r in payload["reads"] if r["degraded"]]
            assert degraded, f"staleness{q}: nothing reported degraded on a stripped tree"
            for r in degraded:
                assert r["producer"] and r["fix"] and r["reason"], \
                    f"{r['id']}: a degraded read must name producer + fix + reason, never a silent 0"
        # the folded-in self_graph is among the (global) degraded reads.
        gpayload = json.loads(_get("/shared/staleness")[2])
        sg = next(r for r in gpayload["reads"] if r["id"] == "self_graph")
        assert sg["degraded"] and "keeper" in sg["producer"]

        # (i) the atom-wired surfaces carry the wiring that RENDERS the degraded data
        # (the client render itself is proven by the browser drive below when present;
        # W1.2's static floor proves the atom paints the absent state and never POSTs).
        for name in _ATOM_SURFACES:
            path = dict(_ROSTER)[name]
            html = _get(path)[2].decode("utf-8", "replace")
            assert "hy-stale-strip" in html and "fetchStale" in html and "renderStale" in html, \
                f"{name}: not wired to consume the staleness atom"
    finally:
        httpd.shutdown()

    # (ii) THE OFFER LAW — a pure GET drive rebuilt nothing.
    _assert_offer_law_held(fired, subp, tree)


@pytest.mark.skipif(_CHROME is None, reason="no Chromium build under /opt/pw-browsers")
def test_strip_and_drive_renders_in_browser(tmp_path, monkeypatch):
    """The client-render proof: under Chromium, the atom-wired surfaces actually PAINT
    the ``.hy-stale`` atom naming producer + fix for each stripped read, and the drive
    fires ZERO write requests (POST/PUT/DELETE/PATCH) — the offer law, client-observed.
    Skips (with reason) when Playwright/Chromium is unavailable."""
    pw = pytest.importorskip("playwright.sync_api")

    tree = tmp_path / "stripped"
    _build_stripped_tree(tree)
    fired, subp = _install_offer_law_sentinels(monkeypatch)
    httpd, port = _boot(tree, monkeypatch)

    writes: list[str] = []
    bad: list[str] = []
    try:
        with pw.sync_playwright() as p:
            browser = p.chromium.launch(executable_path=_CHROME)
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            # the ONE exempted write: W2.4's visit stamp (POST /cockpit/state) is
            # by-design local UI state on an additive merge — the offer law this
            # gate enforces forbids unprompted REBUILDS, not the cockpit cursor.
            page.on("request", lambda r: writes.append(f"{r.method} {r.url}")
                    if r.method in ("POST", "PUT", "DELETE", "PATCH")
                    and not r.url.endswith("/cockpit/state") else None)
            page.on("response", lambda r: bad.append(f"{r.status} {r.url}")
                    if r.status >= 400 and not r.url.endswith("/favicon.ico") else None)
            page.on("pageerror", lambda e: bad.append("PAGEERROR: " + str(e)))

            for name, path in _ROSTER:
                page.goto(f"http://127.0.0.1:{port}{path}", wait_until="load", timeout=45000)
                page.wait_for_function("document.body && document.body.childElementCount > 0",
                                       timeout=15000)
                if name in _ATOM_SURFACES:
                    page.wait_for_selector(".hy-stale-strip.on .hy-stale.is-absent", timeout=15000)
                    strip_txt = page.eval_on_selector(".hy-stale-strip.on", "el => el.innerText")
                    assert "producer:" in strip_txt, f"{name}: no producer named on the strip"
                    assert "fix:" in strip_txt, f"{name}: no fix named on the strip"
                    assert page.query_selector(".hy-stale[data-read='self_graph'].is-absent"), \
                        f"{name}: the graded self-tree degrade is not shown"
            browser.close()
    finally:
        httpd.shutdown()

    assert not writes, f"the drive fired write requests (offer law): {writes}"
    assert not bad, f"a roster surface degraded silently (blank/crash/4xx/5xx): {bad}"
    _assert_offer_law_held(fired, subp, tree)
