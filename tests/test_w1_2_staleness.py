"""W1.2 — THE STALENESS CONTRACT.

``GET /shared/staleness[?corpus=]`` returns, per DERIVED READ the surfaces consume
(nodemap, plan→prose, router cache, metric, voice store), a uniform verdict
``{present,fresh,reason,producer,built_ts,fix,degraded}``; the shared ``.hy-stale``
atom renders it; a surface consuming an absent/stale read says so (DEGRADED plumbed);
and the endpoint NEVER fires a heavy rebuild (the PSU law — the ``fix`` field only
NAMES the gesture).

Two tiers, mirroring test_w1_1_nav.py: a STATIC FLOOR (grep/CSS-level, no browser —
the fail-closed proof the atom renders the three states distinctly) and the Python
read-model tests (each derived read reports honestly against a fabricated fixture; the
endpoint spawns no subprocess and calls no builder).
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from laplace.web import shared_ui

pytestmark = pytest.mark.unit

_STATIC = Path(__file__).resolve().parents[1] / "src" / "laplace" / "web" / "static_shared"
_SRC = Path(__file__).resolve().parents[1] / "src" / "laplace"

_SIX = {"present", "fresh", "reason", "producer", "built_ts", "fix"}


def _shell() -> str:
    return (_STATIC / "shell.js").read_text(encoding="utf-8")


def _css() -> str:
    return (_STATIC / "hymn.css").read_text(encoding="utf-8")


def _touch(p: Path, mtime: float) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x", encoding="utf-8")
    os.utime(p, (mtime, mtime))


def _assert_named(read: dict) -> None:
    """A degraded read must name its reason, producer, and fix — never a silent 0."""
    assert read["degraded"] is True
    assert read["fresh"] is False
    assert read["reason"], f"{read['id']}: a degraded read must carry a reason"
    assert read["producer"], f"{read['id']}: a degraded read must name its producer"
    assert read["fix"], f"{read['id']}: a degraded read must name the fix gesture"


# ---------------------------------------------------------------------------
# STATIC FLOOR — the atom renders present/absent/stale distinctly (no browser).
# ---------------------------------------------------------------------------


def test_atom_renders_three_distinct_states_in_shell():
    """hyStale branches on the THREE states distinctly — is-fresh / is-stale /
    is-absent — driven by present + fresh, and exposes the atom on HymnShell."""
    s = _shell()
    for cls in ("is-fresh", "is-stale", "is-absent"):
        assert cls in s, f"the atom must render the {cls} state"
    assert "!read.present ? \"absent\"" in s, "absent must be derived from present"
    assert "read.fresh ? \"fresh\" : \"stale\"" in s, "fresh vs stale must be derived from fresh"
    # the DEGRADED plumb: renderStale filters to degraded reads and shows the strip
    assert "function renderStale" in s and "r.degraded" in s
    assert "function fetchStale" in s and '/shared/staleness' in s
    # the atom is on the shared API for every surface to consume
    for api in ("hyStale: hyStale", "renderStale: renderStale", "fetchStale: fetchStale"):
        assert api in s, f"HymnShell must expose {api}"


def test_atom_never_fires_a_rebuild_from_the_banner():
    """The atom NAMES the fix (text), it does not POST — firing stays a deliberate
    gesture. The strip must not issue a write from render."""
    s = _shell()
    # the fix is rendered as a label, never a fetch/POST inside the atom
    atom = s.split("function hyStale")[1].split("function renderStale")[0]
    assert "fetch(" not in atom and "method:" not in atom, "the atom must not fire a request"
    assert "hy-stale-fix" in atom, "the fix must be shown as a named gesture"


def test_atom_css_has_three_distinct_state_rules():
    """The CSS gives is-fresh / is-stale / is-absent visibly distinct treatments, and
    the strip is hidden until something is degraded (.on)."""
    css = _css()
    assert ".hy-stale-strip{" in css and ".hy-stale-strip.on{" in css
    assert ".hy-stale.is-stale{" in css
    assert ".hy-stale.is-absent{" in css
    assert ".hy-stale.is-fresh{" in css
    # the two degraded states carry different badge colours (warn vs bad)
    assert ".hy-stale.is-stale .hy-stale-badge{background:var(--warn)}" in css
    assert ".hy-stale.is-absent .hy-stale-badge{background:var(--bad)}" in css


# ---------------------------------------------------------------------------
# READ-MODEL — each derived read reports honestly against a fabricated fixture.
# ---------------------------------------------------------------------------


def test_every_read_has_the_six_field_shape():
    """Every read carries exactly the contract fields plus the render helpers
    (id/label/scope) and the derived degraded flag."""
    out = shared_ui.staleness("", repo_root=Path("/nonexistent_repo_root_xyz"))
    assert out["reads"], "the global reads always ride"
    for r in out["reads"]:
        assert _SIX <= set(r), f"{r.get('id')} missing contract fields"
        assert {"id", "label", "scope", "degraded"} <= set(r)


def test_router_cache_absent_and_stale(tmp_path):
    # absent → degraded, named
    _assert_named(shared_ui.read_router_cache(tmp_path))
    # stale → the graded network is newer than the cache
    from laplace.representation import embed_router as er
    from laplace.engine.keeper import GRADED_LOCAL
    _touch(tmp_path / er.CACHE_FILE, 1000)
    _touch(tmp_path / GRADED_LOCAL, 2000)
    stale = shared_ui.read_router_cache(tmp_path)
    assert stale["present"] is True
    _assert_named(stale)
    # fresh → the cache is at least as new as its source
    _touch(tmp_path / er.CACHE_FILE, 3000)
    fresh = shared_ui.read_router_cache(tmp_path)
    assert fresh["present"] is True and fresh["fresh"] is True and fresh["degraded"] is False
    assert fresh["reason"] is None and fresh["built_ts"]


def test_metric_absent_and_stale(tmp_path):
    from laplace.representation import embed_router as er
    _assert_named(shared_ui.read_metric(tmp_path))
    _touch(tmp_path / er.METRIC_FILE, 1000)
    _touch(tmp_path / er.CACHE_FILE, 2000)
    _assert_named(shared_ui.read_metric(tmp_path))
    _touch(tmp_path / er.METRIC_FILE, 3000)
    assert shared_ui.read_metric(tmp_path)["fresh"] is True


def test_voice_store_absent_and_out_of_sync(tmp_path):
    _assert_named(shared_ui.read_voice_store(tmp_path))
    store = tmp_path / "corpus_stores" / "voice_corpus_cache" / "exemplar_passages"
    store.mkdir(parents=True)
    # one passage present, but its content hash is NOT in the embeddings items → out of sync
    (store / "passages.jsonl").write_text(
        json.dumps({"passage_id": "p1", "sha256": "abc123"}) + "\n", encoding="utf-8")
    (store / "embeddings.json").write_text(
        json.dumps({"backend": "hash", "dim": 3, "items": {}}), encoding="utf-8")
    out = shared_ui.read_voice_store(tmp_path)
    assert out["present"] is True
    _assert_named(out)
    assert "unembedded" in out["reason"]
    # now embed it → fresh
    (store / "embeddings.json").write_text(
        json.dumps({"backend": "hash", "dim": 3, "items": {"abc123": [0.0, 0.0, 0.0]}}),
        encoding="utf-8")
    assert shared_ui.read_voice_store(tmp_path)["fresh"] is True


def test_nodemap_absent_unresolved_and_fingerprint_mismatch(tmp_path):
    # md=None (unresolved corpus) → honest absent
    _assert_named(shared_ui.read_nodemap(None))
    # present-but-stale: a nodemap whose source fingerprint no longer matches the tree
    (tmp_path / "main.tex").write_text("\\documentclass{article}\\begin{document}x\\end{document}",
                                       encoding="utf-8")
    (tmp_path / "main.nodemap.json").write_text(
        json.dumps({"source_fingerprint": "deadbeef_not_the_tree", "entries": {},
                    "coverage": 0.0, "built": "2020-01-01T00:00:00Z"}), encoding="utf-8")
    out = shared_ui.read_nodemap(tmp_path)
    assert out["present"] is True
    _assert_named(out)
    assert out["built_ts"] == "2020-01-01T00:00:00Z"


def test_plan_prose_absent_stale_and_fresh():
    # report None (corpus unresolved) → absent
    _assert_named(shared_ui.read_plan_prose(None))
    # a dirty section → stale, named with the count
    stale = shared_ui.read_plan_prose(
        [{"id": "S1", "dirty": True}, {"id": "S2", "dirty": False}], target_mtime="2026-07-14T00:00:00Z")
    assert stale["present"] is True
    _assert_named(stale)
    assert "1 section" in stale["reason"]
    assert stale["built_ts"] == "2026-07-14T00:00:00Z"
    # no dirty sections → present + fresh
    fresh = shared_ui.read_plan_prose([{"id": "S1", "dirty": False}])
    assert fresh["present"] is True and fresh["fresh"] is True and fresh["degraded"] is False


# ---------------------------------------------------------------------------
# THE PSU LAW — the endpoint fires no subprocess and no builder.
# ---------------------------------------------------------------------------


def test_endpoint_never_triggers_a_rebuild(monkeypatch):
    """A GET /shared/staleness must be PURE READS: no subprocess, and none of the heavy
    builders (nodemap build, storyboard/review rebuild, the embedding router) may run."""
    def _boom(*a, **k):
        raise AssertionError("staleness fired a heavy rebuild — it must be pure reads")

    monkeypatch.setattr(subprocess, "run", _boom)
    monkeypatch.setattr(subprocess, "Popen", _boom)
    from laplace.pipeline import nodemap as nm
    from laplace.manuscript import storyboard as sb
    from laplace.manuscript import review_surface as rv
    from laplace.representation import embed_router as er
    monkeypatch.setattr(nm, "build_nodemap", _boom)
    monkeypatch.setattr(sb, "rebuild", _boom)
    monkeypatch.setattr(rv, "rebuild", _boom)
    monkeypatch.setattr(er, "route", _boom)

    # global-only (no corpus) against the live repo — must return, spawn nothing
    out = shared_ui.staleness("")
    assert out["reads"] and {r["id"] for r in out["reads"]} >= {"router_cache", "metric", "voice_store"}
    # with a corpus, the per-corpus reads join and STILL nothing heavy fires
    out2 = shared_ui.staleness("eigenengine")
    ids = {r["id"] for r in out2["reads"]}
    assert {"nodemap", "plan_prose"} <= ids


def test_route_returns_json(monkeypatch):
    """The /shared/staleness route returns a 200 JSON payload with the reads + a
    degraded count; the scanner already dispatches /shared/* here."""
    res = shared_ui.handle("/shared/staleness", {})
    assert res is not None
    status, ctype, body = res
    assert status == 200 and "application/json" in ctype
    payload = json.loads(body)
    assert "reads" in payload and "degraded" in payload
    assert payload["degraded"] == sum(1 for r in payload["reads"] if r["degraded"])


# ---------------------------------------------------------------------------
# /analytics — the contradiction cell split.
# ---------------------------------------------------------------------------


def test_analytics_rounds_split_flags_the_contradiction():
    """The rollup exposes rounds as a SPLIT read-model — claimed (registry) vs ledger
    (assembler) vs econ-only — and flags the contradiction, instead of one number."""
    from laplace.web import analytics
    status, ctype, body = analytics.handle("/analytics/data", {}, "GET", b"")
    assert status == 200
    projects = json.loads(body)["projects"]
    assert projects
    for p in projects:
        s = p["rounds_split"]
        assert {"claimed", "ledger", "captured", "econ_only", "contradiction"} == set(s)
        # the flag is the honest join: it fires exactly when the two counts disagree
        assert s["contradiction"] == (s["claimed"] != s["ledger"])
        # backcompat: the flat count still rides for existing consumers
        assert p["rounds_n"] == s["claimed"]


def test_analytics_html_renders_the_split_and_the_stale_strip():
    """The page renders the split cell (roundsCell) and carries the DEGRADED strip that
    consumes /shared/staleness through the shared atom."""
    html = (_SRC / "web" / "analytics.html").read_text(encoding="utf-8")
    assert "function roundsCell" in html and "rounds_split" in html
    assert "contra" in html and "claimed" in html
    # the DEGRADED plumb: the strip element + the atom consumption
    assert 'class="hy-stale-strip" id="an-stale"' in html
    assert "HymnShell.fetchStale" in html and "HymnShell.renderStale" in html
