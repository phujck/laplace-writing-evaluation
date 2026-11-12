"""Scoped tests for scripts/reembed.py's phase-timer deposit (Weld B0).

Cheap unit: monkeypatch the heavy calls (keeper.build_self, keeper.write_tree_local,
drain_proposals.cmd_mechanical, self_shard.write_index/load_index) to no-ops and assert
main() writes a timing record to .reembed_timing.jsonl with every phase key + the mode.
Mirrors tests/test_sewup.py's importlib-by-path idiom for loading a scripts/ module.
"""
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "reembed.py"

spec = importlib.util.spec_from_file_location("reembed", SCRIPT)
reembed = importlib.util.module_from_spec(spec)
sys.modules["reembed"] = reembed
spec.loader.exec_module(reembed)  # type: ignore[union-attr]


# The node shape keeper.grade_stats actually reads (leaf / grade / members / id). It used to be
# {"grade": n} alone, which was enough while main() only counted grades; since
# WO-20260817-skeleton-rides-deposit the deposit ALSO writes the committed coarse skeleton
# (keeper.write_skeleton over keeper.grade_stats), so the stub nodes must be shaped like real ones.
FAKE_NODES = {
    "a": {"id": "a", "grade": 0, "leaf": True, "members": []},
    "b": {"id": "b", "grade": 1, "leaf": False, "members": ["a", "c"]},
    "c": {"id": "c", "grade": 0, "leaf": True, "members": []},
}

# The RAW file shards build_self hands back through `shards_out` - the flat self_shard shape, not
# the graded one. The dedup under test is that the re-index gets THESE, rather than re-deriving.
FAKE_SHARDS = {
    "a.md": {"name": "a.md", "kind": "md", "essence": "a", "keywords": ["a"],
             "spine_count": 0, "lines": 1, "edges": [], "sealed": False},
}
_WRITE_INDEX_CALLS: list = []


def _write_meaning_sidecar(repo_root):
    from laplace.engine.meaning_upfold import write_sidecar
    write_sidecar(repo_root, "fixture", {"a": ("content-a", [1.0, 0.0])})


def _stub_heavy_calls(monkeypatch):
    """Replace every heavy/side-effecting call reembed.main([]) makes with a cheap no-op,
    but keep them real enough that keeper.build_self's timings dict still gets populated
    (that's the thing under test in scripts/reembed.py's phase-timer wrap)."""

    def fake_build_self(repo_root, timings=None, shards_out=None, force_full=False):
        (repo_root / ".meaning_tree.json").write_text("{}")
        (repo_root / ".self_record_floor.jsonl").write_text("")
        # A zero-embedding return represents an existing basis, not a missing one.
        (repo_root / ".self_embeddings.json").write_text("{}")
        _write_meaning_sidecar(repo_root)
        if shards_out is not None:
            # the raw file shards build_self hands back so the re-index below reuses them instead
            # of re-deriving the whole tree (the phase-3 dedup, 2026-08-20)
            shards_out.update(FAKE_SHARDS)
        if timings is not None:
            timings["shard_repo"] = 0.001
            timings["lens_leaves"] = 0.001
            timings["meaning_upfold"] = 0.001
            timings["build_tree"] = 0.001
        return FAKE_NODES

    monkeypatch.setattr("laplace.engine.keeper.build_self", fake_build_self)
    monkeypatch.setattr("laplace.engine.meaning_upfold.load_tree", lambda root: {"clusters": {}, "parent_map": {}, "leaf_sha": {}, "root_id": ""})
    monkeypatch.setattr("laplace.engine.conceptric.load_network", lambda root: {"nodes": {}})
    monkeypatch.setattr("laplace.representation.embed_router.get_backend", lambda: object())
    def fake_embeddings(root, *args, **kwargs):
        (root / ".self_embeddings.json").write_text("{}")
        return {"n_embedded": 0, "n_cached": 0, "n_total": 0, "vectors": {}, "changed_ids": []}
    def fake_metric(root, *args, **kwargs):
        for name in (".metric_M.npz", ".metric_M.receipt.json", ".metric_pairs.json"):
            (root / name).write_text("fixture")
        return {"shipped": True}
    monkeypatch.setattr("laplace.representation.embed_router.ensure_embeddings", fake_embeddings)
    monkeypatch.setattr("laplace.representation.metric_distill.distill", fake_metric)
    monkeypatch.setattr(reembed, "_trigger_receipt_for_act", lambda _root, _act: None)
    def fake_write_tree(repo_root, nodes, *, destination=None):
        out = Path(destination) if destination is not None else Path(repo_root) / ".self_graded.json"
        out.write_text(json.dumps(nodes), encoding="utf-8")
        return out
    monkeypatch.setattr("laplace.engine.keeper.write_tree_local", fake_write_tree)
    # BOTH halves of the committed projection pair are stubbed (WO-20260817-skeleton-rides-
    # deposit): the deposit now writes SELF_GRADED_INDEX.md alongside .self_graded.json, and a
    # unit test of the phase timers must not rewrite the real repo's committed skeleton.
    def fake_write_skeleton(repo_root, nodes, stats, **kwargs):
        out = Path(kwargs.get("destination") or Path(repo_root) / "SELF_GRADED_INDEX.md")
        out.write_text("skeleton\n", encoding="utf-8")
        return out
    monkeypatch.setattr("laplace.engine.keeper.write_skeleton", fake_write_skeleton)

    class _FakeDrainProposals:
        @staticmethod
        def cmd_mechanical(*, net=None):
            return 0

    monkeypatch.setitem(sys.modules, "drain_proposals", _FakeDrainProposals)

    # write_index now takes the shards the deposit already computed (default kept for standalone
    # callers). The stub RECORDS what it was handed, so the dedup is asserted, not assumed.
    def fake_write_index(repo_root, shards=None):
        from laplace.engine import self_shard
        _WRITE_INDEX_CALLS.append(shards)
        out = Path(repo_root) / self_shard._INDEX
        out.write_text("index\n", encoding="utf-8")
        return out

    _WRITE_INDEX_CALLS.clear()
    monkeypatch.setattr("laplace.engine.self_shard.write_index", fake_write_index)
    monkeypatch.setattr("laplace.engine.self_shard.load_index", lambda repo_root: {"x": 1, "y": 2})

    # Spectral-deps preflight must pass through to the timed body. reembed.main([]) does a bare
    # `import scipy` / `import sklearn` for its narration line - stub them in sys.modules so this
    # test doesn't depend on the `analysis` extra being installed in whatever env runs it. The
    # env vars below are now inert no-ops (his 2026-08-20 PSU-restrictions-scrubbed ruling retired
    # the LAPLACE_ALLOW_SPECTRAL / CLAUDE_CODE_REMOTE opt-in gate; meaning_upfold._spectral_allowed
    # is deps-only now) - kept set here as a harmless no-op rather than pulled, since this test
    # doesn't otherwise care about the spectral gate itself.
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    monkeypatch.delenv("LAPLACE_ALLOW_SPECTRAL", raising=False)
    for modname in ("scipy", "sklearn"):
        if modname not in sys.modules:
            monkeypatch.setitem(sys.modules, modname, types.ModuleType(modname))


@pytest.fixture
def timing_log(tmp_path, monkeypatch):
    log = tmp_path / ".reembed_timing.jsonl"
    monkeypatch.setattr(reembed, "TIMING_LOG", log)
    monkeypatch.setattr(reembed, "ROOT", tmp_path)
    return log


def test_main_writes_timing_record_with_all_phase_keys(monkeypatch, timing_log):
    _stub_heavy_calls(monkeypatch)

    rc = reembed.main([])

    assert rc == 0
    assert timing_log.is_file()
    lines = timing_log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])

    assert record["mode"] == "unproven"
    assert record["trigger_receipt"] is None
    assert record["runtime"]["environment"] == "standalone"
    assert {"spectral_backend", "embedding_backend", "embedding_result", "required"} \
        <= record["device"].keys()
    assert record["nodes"] == len(FAKE_NODES)
    assert isinstance(record["total"], (int, float))
    assert record["total"] >= 0
    assert "ts" in record and record["ts"]

    expected_phase_keys = {
        "shard_repo", "lens_leaves", "meaning_upfold", "build_tree",
        "write_tree_local", "wire", "index", "embed", "metric_distill", "publish",
    }
    assert expected_phase_keys <= record["phases"].keys()
    for key in expected_phase_keys:
        assert isinstance(record["phases"][key], (int, float))
        assert record["phases"][key] >= 0


def test_reindex_reuses_the_shards_build_self_already_computed(monkeypatch, timing_log):
    """The phase-3 dedup: the re-index is handed build_self's own raw shards, never left to
    re-derive them. Before this, `write_index(ROOT)` fell to its shards=None default and walked +
    re-sharded the whole tree a second time - the same 8-22 s answer computed twice per deposit.

    The `or None` in the call site matters: an EMPTY dict (nothing built) must still fall through
    to the default, so a caller that somehow got no shards re-derives rather than writing an empty
    index over the committed one."""
    _stub_heavy_calls(monkeypatch)

    assert reembed.main([]) == 0

    assert len(_WRITE_INDEX_CALLS) == 1
    assert _WRITE_INDEX_CALLS[0] == FAKE_SHARDS       # threaded through, not re-derived
    assert _WRITE_INDEX_CALLS[0] is not None


def test_main_appends_a_record_per_run(monkeypatch, timing_log):
    _stub_heavy_calls(monkeypatch)

    reembed.main([])
    reembed.main([])

    lines = timing_log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    for line in lines:
        record = json.loads(line)
        assert record["mode"] == "unproven"


# --- Gate A: the wire step is skipped when the frontier is empty (his ruling 2026-07-13) ---

_WIRE_FILES = [".wire_proposals.jsonl", ".wire_verdicts.jsonl",
               ".learned_keywords.json", ".escalate_briefs.json"]


def _snapshot(paths):
    return {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in paths}


def _drain_spy(monkeypatch, calls):
    class _Spy:
        @staticmethod
        def cmd_mechanical(*, net=None):
            calls["n"] += 1
            return 0
    monkeypatch.setitem(sys.modules, "drain_proposals", _Spy)


def test_wire_step_skipped_when_frontier_empty(monkeypatch, tmp_path):
    """Empty frontier -> cmd_mechanical NOT called, NO wire ledger touched (a spurious rewrite would
    trip close_beats' effect_meter mtime beat), and the timing record marks the skip."""
    _stub_heavy_calls(monkeypatch)
    monkeypatch.setattr(reembed, "ROOT", tmp_path)
    monkeypatch.setattr(reembed, "TIMING_LOG", tmp_path / ".reembed_timing.jsonl")

    wf = [tmp_path / n for n in _WIRE_FILES]
    for p in wf:
        p.write_text("SENTINEL\n", encoding="utf-8")
    snap = _snapshot(wf)

    monkeypatch.setattr("laplace.representation.embed_router.proposal_pairs", lambda root: [])
    calls = {"n": 0}
    _drain_spy(monkeypatch, calls)

    rc = reembed.main([])

    assert rc == 0
    assert calls["n"] == 0, "cmd_mechanical must not run on an empty frontier"
    assert _snapshot(wf) == snap, "no wire ledger may be touched on the skip"
    record = json.loads((tmp_path / ".reembed_timing.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert record.get("skipped") == ["wire"]
    assert record["phases"]["wire"] >= 0


def test_wire_step_runs_when_frontier_nonempty(monkeypatch, tmp_path):
    """Non-empty frontier -> cmd_mechanical runs exactly as before, and the record carries no skip mark."""
    _stub_heavy_calls(monkeypatch)
    monkeypatch.setattr(reembed, "ROOT", tmp_path)
    monkeypatch.setattr(reembed, "TIMING_LOG", tmp_path / ".reembed_timing.jsonl")

    monkeypatch.setattr("laplace.representation.embed_router.proposal_pairs",
                        lambda root: [{"query": "q", "id": "x", "cos": 0.6, "via": None}])
    calls = {"n": 0}
    _drain_spy(monkeypatch, calls)

    rc = reembed.main([])

    assert rc == 0
    assert calls["n"] == 1, "cmd_mechanical runs when there is a frontier to drain"
    record = json.loads((tmp_path / ".reembed_timing.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert "skipped" not in record


def test_empty_frontier_consumes_retained_judgments_after_projection_rollback(monkeypatch, tmp_path):
    from laplace.representation import embed_router as er
    _stub_heavy_calls(monkeypatch)
    monkeypatch.setattr(reembed, "ROOT", tmp_path)
    monkeypatch.setattr(reembed, "TIMING_LOG", tmp_path / ".reembed_timing.jsonl")
    monkeypatch.setattr(er, "proposal_pairs", lambda _root: [])
    cache = tmp_path / er.LEARNED_KEYWORDS_FILE
    cache.write_text('{}')
    verdicts = tmp_path / er.VERDICTS_FILE
    verdicts.write_text(json.dumps({"id": "a", "query": "retained discovery", "verdict": "wire"}) + "\n")
    import os
    os.utime(cache, ns=(1, 1))  # a restored predecessor, while its newer judgment survives
    before = verdicts.read_bytes()
    calls = {"n": 0}
    _drain_spy(monkeypatch, calls)
    assert reembed.main([]) == 0
    assert "discovery" in er.load_learned_keywords(tmp_path)["a"]
    assert verdicts.read_bytes() == before and calls["n"] == 0


# --- The deposit's own wire-drain ledgers are its outputs, not source moving under it ---

_PRIOR_VERDICT = {"query": "prior judged", "id": "z", "verdict": "noise", "method": "jury"}


class _FixtureEmbedder:
    """Deterministic local embedder: both frontier nodes sit on one axis, so the real gate wires
    "alpha beta" -> a (cos 1.0) and calls "gamma" -> b noise (cos 0.0)."""
    name = "fixture-embedder"

    def query(self, text):
        return {"alpha beta": [1.0, 0.0], "gamma": [0.0, 1.0]}[text]

    def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]


def _committed_checkout_with_a_frontier(root):
    """A real Git checkout whose committed wire ledgers hold two unjudged pairs and one prior verdict."""
    import subprocess
    (root / "notes.md").write_text("an authored source file\n", encoding="utf-8")
    (root / ".wire_proposals.jsonl").write_text("".join(json.dumps(p) + "\n" for p in (
        {"query": "alpha beta", "id": "a", "cos": 0.4, "ts": "2026-10-20T00:00:00+00:00"},
        {"query": "gamma", "id": "b", "cos": 0.4, "ts": "2026-10-20T00:00:00+00:00"})), encoding="utf-8")
    (root / ".wire_verdicts.jsonl").write_text(json.dumps(_PRIOR_VERDICT) + "\n", encoding="utf-8")
    git = ["git", "-C", str(root), "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid",
           "-c", "commit.gpgsign=false"]
    subprocess.run(git[:3] + ["init", "-q"], check=True)
    subprocess.run(git + ["add", "notes.md", ".wire_proposals.jsonl", ".wire_verdicts.jsonl"], check=True)
    subprocess.run(git + ["commit", "-q", "-m", "fixture"], check=True)


def _real_wire_drain(monkeypatch, root):
    """The real scripts/drain_proposals.py, with only its checkout root pointed at the fixture."""
    from laplace.representation import embed_router as er
    spec = importlib.util.spec_from_file_location("drain_proposals", ROOT / "scripts" / "drain_proposals.py")
    drain = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(drain)  # type: ignore[union-attr]
    monkeypatch.setattr(drain, "ROOT", root)
    monkeypatch.setattr(drain, "ESCALATE_FILE", root / ".escalate_briefs.json")
    monkeypatch.setitem(sys.modules, "drain_proposals", drain)
    monkeypatch.setattr(er, "get_backend", lambda: _FixtureEmbedder())
    # The timing row's fold extras are not under test: the GPU probe is heavy, and the fold dials live in the
    # engine state home, which an isolated run leaves empty.
    monkeypatch.setattr("laplace.engine.meaning_upfold._fold_backend", lambda: ("cpu", "fixture"))
    monkeypatch.setattr("laplace.engine.meaning_upfold.depth_cap_figure", lambda tree: {"fixture": True})
    return drain


def test_real_wire_drain_ledgers_do_not_block_publication_in_a_git_checkout(monkeypatch, tmp_path, capsys):
    from laplace.representation import embed_router as er
    _stub_heavy_calls(monkeypatch)
    monkeypatch.setattr(reembed, "ROOT", tmp_path)
    monkeypatch.setattr(reembed, "TIMING_LOG", tmp_path / ".reembed_timing.jsonl")
    _committed_checkout_with_a_frontier(tmp_path)
    _real_wire_drain(monkeypatch, tmp_path)

    assert reembed.main([]) == 0

    verdicts = [json.loads(line) for line in (tmp_path / er.VERDICTS_FILE).read_text().splitlines()]
    assert verdicts[0] == _PRIOR_VERDICT
    assert [(v["query"], v["id"], v["verdict"]) for v in verdicts[1:]] == [
        ("alpha beta", "a", "wire"), ("gamma", "b", "noise")]
    assert er.proposal_pairs(tmp_path) == []
    assert er.load_learned_keywords(tmp_path) == {"a": ["alpha", "beta"]}
    record = json.loads((tmp_path / ".reembed_timing.jsonl").read_text().splitlines()[-1])
    assert record["source_frontier_status"] == "OBSERVED" and record["source_frontier_unchanged"] is True
    assert {er.PROPOSALS_FILE, er.VERDICTS_FILE} <= set(record["touched_files"])
    publication = json.loads(capsys.readouterr().out.split("LAPLACE_PUBLICATION=")[-1])
    assert publication["published"] is True
    assert json.loads((tmp_path / ".self_graded.json").read_text()) == FAKE_NODES


@pytest.mark.parametrize("move", ["changed", "added"])
def test_genuine_source_moving_during_the_drain_still_refuses_and_keeps_new_judgments(
        monkeypatch, tmp_path, capsys, move):
    from laplace.representation import embed_router as er
    _stub_heavy_calls(monkeypatch)
    monkeypatch.setattr(reembed, "ROOT", tmp_path)
    monkeypatch.setattr(reembed, "TIMING_LOG", tmp_path / ".reembed_timing.jsonl")
    _committed_checkout_with_a_frontier(tmp_path)
    (tmp_path / ".self_graded.json").write_text('{"prior": "accepted render"}')
    drain = _real_wire_drain(monkeypatch, tmp_path)
    real = drain.cmd_mechanical
    moved = "notes.md" if move == "changed" else "new_note.md"

    def drain_while_an_author_writes(*, net=None):
        code = real(net=net)
        (tmp_path / moved).write_text("written by someone else during the deposit\n", encoding="utf-8")
        return code
    monkeypatch.setattr(drain, "cmd_mechanical", drain_while_an_author_writes)

    assert reembed.main([]) == 1

    record = json.loads((tmp_path / ".reembed_timing.jsonl").read_text().splitlines()[-1])
    assert record["source_frontier_unchanged"] is False
    publication = json.loads(capsys.readouterr().out.split("LAPLACE_PUBLICATION=")[-1])
    assert publication["published"] is False
    assert (tmp_path / ".self_graded.json").read_text() == '{"prior": "accepted render"}'
    verdicts = [json.loads(line) for line in (tmp_path / er.VERDICTS_FILE).read_text().splitlines()]
    assert verdicts[0] == _PRIOR_VERDICT and [v["verdict"] for v in verdicts[1:]] == ["wire", "noise"]
    assert er.proposal_pairs(tmp_path) == []


# --- WO-20260817-reembed-honest-no-backend: a capability failure is not a no-op ---

def test_no_backend_is_a_loud_nonzero_capability_failure(monkeypatch, tmp_path, capsys):
    """No embedding backend => BOTH halves of the one producer act are skipped. The deposit must
    say so in the banked record, on stderr, and in its rc — never bank the false reason 'basis
    unchanged - nothing re-embedded' (which claims the basis was looked at) and exit 0."""
    _stub_heavy_calls(monkeypatch)
    monkeypatch.setattr(reembed, "ROOT", tmp_path)
    monkeypatch.setattr(reembed, "TIMING_LOG", tmp_path / ".reembed_timing.jsonl")
    monkeypatch.setattr("laplace.representation.embed_router.proposal_pairs", lambda root: [])
    monkeypatch.setattr("laplace.engine.conceptric.load_network", lambda root: {"nodes": {}})
    monkeypatch.setattr("laplace.representation.embed_router.get_backend", lambda: None)
    _drain_spy(monkeypatch, {"n": 0})

    rc = reembed.main([])

    assert rc == 1, "a capability failure must be non-zero (parity with embed_router.main)"
    err = capsys.readouterr().err
    assert "NO EMBEDDING BACKEND" in err and "capability failure, not a no-op" in err
    record = json.loads((tmp_path / ".reembed_timing.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    # the record is still banked (the graded deposit above DID run) and names the real skip
    assert set(record["skipped"]) >= {"embed", "metric_distill"}
    assert record["metric_redistill"]["ran"] is False
    assert "capability failure, not a no-op" in record["metric_redistill"]["reason"]


def test_a_present_backend_keeps_the_deposit_green(monkeypatch, tmp_path):
    """An unchanged embedding count still enters the metric to consume link-only changes."""
    _stub_heavy_calls(monkeypatch)
    monkeypatch.setattr(reembed, "ROOT", tmp_path)
    monkeypatch.setattr(reembed, "TIMING_LOG", tmp_path / ".reembed_timing.jsonl")
    monkeypatch.setattr("laplace.representation.embed_router.proposal_pairs", lambda root: [])
    monkeypatch.setattr("laplace.engine.conceptric.load_network", lambda root: {"nodes": {}})
    monkeypatch.setattr("laplace.representation.embed_router.get_backend", lambda: object())
    monkeypatch.setattr("laplace.representation.embed_router.ensure_embeddings",
                        lambda root, net, backend, bulk=False: {"n_embedded": 0, "n_cached": 0,
                                                                "n_total": 0, "vectors": {}, "changed_ids": []})
    _drain_spy(monkeypatch, {"n": 0})

    assert reembed.main([]) == 0
    record = json.loads((tmp_path / ".reembed_timing.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert record["metric_redistill"]["ran"] is True
    assert record["metric_redistill"]["shipped"] is True
    assert "embed" not in record.get("skipped", [])


def test_embedding_failure_preserves_deposit_and_marks_counts_unknown(monkeypatch, tmp_path):
    _stub_heavy_calls(monkeypatch)
    monkeypatch.setattr(reembed, "ROOT", tmp_path)
    monkeypatch.setattr(reembed, "TIMING_LOG", tmp_path / ".reembed_timing.jsonl")
    monkeypatch.setattr("laplace.representation.embed_router.proposal_pairs", lambda root: [])
    monkeypatch.setattr("laplace.engine.conceptric.load_network", lambda root: {"nodes": {}})
    monkeypatch.setattr("laplace.representation.embed_router.get_backend", lambda: object())
    def fail_embeddings(*args, **kwargs):
        raise RuntimeError("allocator out of memory")
    monkeypatch.setattr("laplace.representation.embed_router.ensure_embeddings", fail_embeddings)
    _drain_spy(monkeypatch, {"n": 0})

    assert reembed.main([]) == 1
    record = json.loads((tmp_path / ".reembed_timing.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert record["embedding_counts"] == {"embedded": None, "cached": None, "deferred": None,
                                           "pruned": None, "total": None}
    assert record["metric_redistill"]["ran"] is False
    assert "embedding failed" in record["metric_redistill"]["reason"]
    assert "basis unchanged" not in record["metric_redistill"]["reason"]


def test_the_distill_is_handed_the_network_and_vectors_the_deposit_holds(monkeypatch, tmp_path):
    """WO-20260821-route-basis-memo C2a: the re-distill leg used to call metric_distill.main([]),
    which re-ran load_network and a full-fold ensure_embeddings — the two things this deposit had
    just finished, in this same process. It now calls distill(repo_root, net, vectors) with the
    OBJECTS it holds, so the scaffold is paid once. Pinned by identity, not by timing."""
    _stub_heavy_calls(monkeypatch)
    monkeypatch.setattr(reembed, "ROOT", tmp_path)
    monkeypatch.setattr(reembed, "TIMING_LOG", tmp_path / ".reembed_timing.jsonl")
    monkeypatch.setattr("laplace.representation.embed_router.proposal_pairs", lambda root: [])
    net = {"nodes": {"a": {}}}
    vectors = {"a": [0.0, 1.0]}
    monkeypatch.setattr("laplace.engine.conceptric.load_network", lambda root: net)
    monkeypatch.setattr("laplace.representation.embed_router.get_backend", lambda: object())
    monkeypatch.setattr("laplace.representation.embed_router.ensure_embeddings",
                        lambda root, net, backend, bulk=False: {"n_embedded": 3, "n_cached": 1,
                                                                "n_total": 4, "vectors": vectors, "changed_ids": ["a"]})
    seen: dict = {}
    from laplace.representation import metric_distill
    fixture_publication = metric_distill.distill
    def capture_distill(root, n, v, **kw):
        seen.update(root=root, net=n, vectors=v, **kw)
        return {**fixture_publication(root, n, v, **kw),
                "auc_identity": 0.5, "auc_trained": 0.9}
    monkeypatch.setattr("laplace.representation.metric_distill.distill", capture_distill)
    monkeypatch.setattr("laplace.representation.metric_distill.main",
                        lambda argv: pytest.fail("the deposit must not re-enter the CLI wrapper"))
    _drain_spy(monkeypatch, {"n": 0})

    assert reembed.main([]) == 0
    assert seen["changed_ids"] == ["a"] and seen["full_metric"] is False
    assert seen["net"] is net and seen["vectors"] is vectors and seen["root"] == tmp_path
    record = json.loads((tmp_path / ".reembed_timing.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert record["metric_redistill"]["ran"] is True and record["metric_redistill"]["shipped"] is True


def test_embedding_gpu_owner_is_released_before_metric_distill(monkeypatch,tmp_path):
    _stub_heavy_calls(monkeypatch)
    monkeypatch.setattr(reembed,"ROOT",tmp_path)
    monkeypatch.setattr(reembed,"TIMING_LOG",tmp_path/".reembed_timing.jsonl")
    monkeypatch.setattr("laplace.representation.embed_router.proposal_pairs",lambda root:[])
    monkeypatch.setattr("laplace.engine.conceptric.load_network",lambda root:{"nodes":{}})
    class Backend:
        gpu=True;providers=['CUDAExecutionProvider'];_why='fixture CUDA session'
    backend=Backend();released=[]
    monkeypatch.setattr("laplace.representation.embed_router.get_backend",lambda:backend)
    monkeypatch.setattr("laplace.representation.embed_router.ensure_embeddings",lambda *a,**kw:{
        "n_embedded":0,"n_cached":0,"n_total":0,"vectors":{},"changed_ids":[]})
    monkeypatch.setattr("laplace.representation.embed_router.release_backend",lambda value:
        released.append(value) or {"released":True,"gpu":True,"providers":value.providers})
    from laplace.representation import metric_distill
    real=metric_distill.distill
    def distill(*args,**kwargs):
        assert released==[backend]
        return real(*args,**kwargs)
    monkeypatch.setattr("laplace.representation.metric_distill.distill",distill)
    _drain_spy(monkeypatch,{"n":0})

    assert reembed.main([])==0
    row=json.loads((tmp_path/".reembed_timing.jsonl").read_text().splitlines()[-1])
    assert row["device"]["embedding_backend"]=="gpu"
    assert row["device"]["embedding_release"]["released"] is True


def test_metric_refusal_is_a_failed_deposit(monkeypatch, timing_log):
    _stub_heavy_calls(monkeypatch)
    monkeypatch.setattr("laplace.representation.metric_distill.distill", lambda *a, **kw:
                        {"shipped": False, "status": "CURE-B-AUC-002"})
    assert reembed.main([]) == 1
    record = json.loads(timing_log.read_text().splitlines()[-1])
    assert record["metric_redistill"]["status"] == "CURE-B-AUC-002"


def test_refusal_before_publish_leaves_all_three_renders_byte_and_mtime_identical(
        monkeypatch, tmp_path):
    _stub_heavy_calls(monkeypatch)
    monkeypatch.setattr(reembed, "ROOT", tmp_path)
    monkeypatch.setattr(reembed, "TIMING_LOG", tmp_path / ".reembed_timing.jsonl")
    monkeypatch.setattr("laplace.representation.metric_distill.distill",
                        lambda *a, **kw: {"shipped": False, "status": "PLANTED-REFUSAL"})
    renders = [tmp_path / name for name in reembed.RENDER_NAMES]
    for index, path in enumerate(renders):
        path.write_bytes(f"sentinel-{index}".encode())
    before = _snapshot(renders)

    assert reembed.main([]) == 1

    assert _snapshot(renders) == before
    assert not list(tmp_path.glob(".*.tmp")), "a refused transaction cleans every staged render"


def test_deposit_banks_one_act_cost_and_one_row_per_journal_step(monkeypatch, timing_log):
    from laplace.core.records import journal

    _stub_heavy_calls(monkeypatch)
    assert reembed.main([]) == 0

    rows = [json.loads(line) for line in Path(journal._cost_store(reembed.ROOT)).read_text().splitlines()]
    assert len(rows) == 1 + len(reembed.ACT_STEPS)
    act = next(row for row in rows if row["step"] == "act")
    assert act["act"] == "deposit" and act["status"] == "PASS"
    assert {"D", "M", "A", "K_t", "files", "bytes"} <= act["diff"].keys()
    assert {"rchar", "wchar", "read_bytes", "write_bytes"} <= act["io"].keys()
    assert act["bytes_read"] == act["io"]["read_bytes"]
    assert act["bytes_written"] == act["io"]["write_bytes"]
    assert {"shard_repo", "lens_leaves", "meaning_upfold", "build_tree",
            "write_tree_local", "wire", "index", "embed", "metric_distill", "publish"} \
        <= act["phases"].keys()
    assert act["receipt_bytes"] > 0 and act["receipt_seconds"] >= 0
    assert {row["step"] for row in rows if row["step"] != "act"} == set(reembed.ACT_STEPS)


def test_synthetic_over_ceiling_cost_makes_the_act_terminal_non_green(
        monkeypatch, timing_log):
    from laplace.core.records import journal

    _stub_heavy_calls(monkeypatch)
    monkeypatch.setenv("LAPLACE_ACT_COST_CEILING_SECONDS", "0")

    assert reembed.main([]) == 1

    cost = [json.loads(line) for line in Path(journal._cost_store(reembed.ROOT)).read_text().splitlines()][0]
    assert cost["status"] == "OVER_CEILING"
    ends = [json.loads(line) for line in Path(journal._store(reembed.ROOT)).read_text().splitlines()
            if json.loads(line).get("record") == "act_end"]
    assert ends[-1]["status"] == "fail"
    assert not (timing_log.parent / ".self_graded.json").exists(), "failed producer restored the absent prior publication"


# --- FIND-SB-4: the standalone deposit runs INSIDE the journal, like the close does ---

def test_the_deposit_opens_a_journal_act_around_every_phase(monkeypatch, tmp_path):
    """The graded SB-4 finding: this script wrote .self_graded.json, the committed skeleton, the
    shard index and a timing row while declaring NOTHING - a banking organ running outside the
    journal, so a kill mid-deposit was archaeology. Now every phase it already times is bracketed
    begin/done under one act, and `journal.recover()` sees a completed run."""
    from laplace.core.records import journal

    _stub_heavy_calls(monkeypatch)
    monkeypatch.setattr(reembed, "ROOT", tmp_path)
    monkeypatch.setattr(reembed, "TIMING_LOG", tmp_path / ".reembed_timing.jsonl")
    monkeypatch.setattr("laplace.representation.embed_router.proposal_pairs", lambda root: [])
    monkeypatch.setattr("laplace.engine.conceptric.load_network", lambda root: {"nodes": {}})
    monkeypatch.setattr("laplace.representation.embed_router.get_backend", lambda: object())
    monkeypatch.setattr("laplace.representation.embed_router.ensure_embeddings",
                        lambda root, net, backend, bulk=False: {"n_embedded": 0, "n_cached": 0,
                                                                "n_total": 0, "vectors": {}, "changed_ids": []})
    _drain_spy(monkeypatch, {"n": 0})

    assert reembed.main([]) == 0

    # the conftest LAPLACE_STATE isolation puts the journal in this test's own tmp store
    events = [json.loads(ln) for ln in
              Path(journal._store(reembed.ROOT)).read_text(encoding="utf-8").splitlines() if ln.strip()]
    acts = [e for e in events if e["record"] == "act" and e["act"] == "reembed-standalone"]
    assert len(acts) == 1, "one act per deposit run"
    aid = acts[0]["act_id"]
    assert acts[0]["manifest"] == reembed.ACT_STEPS      # intent declared BEFORE any store moved

    steps = [e for e in events if e["record"] == "step" and e["act_id"] == aid]
    begun = {e["name"] for e in steps if e["phase"] == "begin"}
    done = {e["name"] for e in steps if e["phase"] == "done"}
    assert begun == done == set(reembed.ACT_STEPS)
    # every begin precedes its own done: intent-then-execute, not a report written at the end
    for name in reembed.ACT_STEPS:
        b = next(i for i, e in enumerate(steps) if e["name"] == name and e["phase"] == "begin")
        d = next(i for i, e in enumerate(steps) if e["name"] == name and e["phase"] == "done")
        assert b < d, f"{name}: the done row must follow its begin"

    ends = [e for e in events if e["record"] == "act_end" and e["act_id"] == aid]
    assert len(ends) == 1 and ends[0]["status"] == "pass"
    assert not journal.recover(root=reembed.ROOT)["in_flight"], "a completed deposit leaves nothing in flight"


def test_the_no_backend_deposit_ends_its_act_fail(monkeypatch, tmp_path):
    """Parity with the rc (WO-20260817-reembed-honest-no-backend): a capability failure is not a
    green act. The act still ENDS - the graded deposit above really did bank - but it says fail."""
    from laplace.core.records import journal

    _stub_heavy_calls(monkeypatch)
    monkeypatch.setattr(reembed, "ROOT", tmp_path)
    monkeypatch.setattr(reembed, "TIMING_LOG", tmp_path / ".reembed_timing.jsonl")
    monkeypatch.setattr("laplace.representation.embed_router.proposal_pairs", lambda root: [])
    monkeypatch.setattr("laplace.engine.conceptric.load_network", lambda root: {"nodes": {}})
    monkeypatch.setattr("laplace.representation.embed_router.get_backend", lambda: None)
    _drain_spy(monkeypatch, {"n": 0})

    assert reembed.main([]) == 1

    events = [json.loads(ln) for ln in
              Path(journal._store(reembed.ROOT)).read_text(encoding="utf-8").splitlines() if ln.strip()]
    end = [e for e in events if e["record"] == "act_end"][-1]
    assert end["status"] == "fail"
    assert not journal.recover(root=reembed.ROOT)["in_flight"]


# --- WO-20260823-one-stamp-law: the banking seam owns the row's ts ---

def test_bank_row_stamps_true_utc_and_demotes_a_hand_ts(tmp_path):
    """The judge's ruling 3. Three dialects shared one last-wins ordering - journal true UTC-Z,
    THREAD_PROBES naive local, hand rows a local time wearing a false Z (30-120min AHEAD of the
    box, which is what broke SB-4's +/-2s kill derivation). bank_row now stamps ts itself; a hand
    stamp is not deleted, it is DEMOTED verbatim to ts_claimed where a lint can reach it."""
    from datetime import datetime, timezone

    from laplace.core.records import journal

    (tmp_path / "contract").mkdir()
    (tmp_path / "demo").mkdir()
    hand = "2026-08-23T21:30:00Z"        # the false-Z dialect, hours ahead of any real box

    before = datetime.now(timezone.utc)
    journal.bank_row("demo/rows.jsonl", {"id": "h1", "ts": hand, "text": "hand"}, root=tmp_path)
    journal.bank_row("demo/rows.jsonl", {"id": "n1", "text": "no ts"}, root=tmp_path)
    after = datetime.now(timezone.utc)

    rows = {r["id"]: r for r in
            (json.loads(ln) for ln in
             (tmp_path / "demo" / "rows.jsonl").read_text(encoding="utf-8").splitlines())}

    assert rows["h1"]["ts_claimed"] == hand, "the hand stamp survives, verbatim, as a claim"
    assert rows["h1"]["ts"] != hand, "but it is no longer the authoritative ts"
    for rid in ("h1", "n1"):
        stamped = datetime.strptime(rows[rid]["ts"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(
            tzinfo=timezone.utc)
        assert before <= stamped <= after, f"{rid}: ts is this box's true UTC at write time"
    assert "ts_claimed" not in rows["n1"], "no claim was made, so none is recorded"


def test_bank_row_does_not_mutate_the_caller_s_row(tmp_path):
    """The stamp lands on the BANKED copy. A caller that banks a dict it still holds (wake.py's
    gate verdicts, sewup's census rows) must not find its own object rewritten underneath it."""
    from laplace.core.records import journal

    (tmp_path / "contract").mkdir()
    (tmp_path / "demo").mkdir()
    row = {"id": "m1", "ts": "2026-08-23T21:30:00Z"}

    journal.bank_row("demo/rows.jsonl", row, root=tmp_path)

    assert row == {"id": "m1", "ts": "2026-08-23T21:30:00Z"}


def test_the_journal_s_own_rows_are_unchanged_in_form(tmp_path):
    """act/step/bank/act_end are already machine-stamped - they go through _append, not the bank
    path - so the one stamp law must leave them exactly as they were: true UTC-Z, no ts_claimed."""
    from laplace.core.records import journal

    (tmp_path / "contract").mkdir()
    (tmp_path / "demo").mkdir()

    aid = journal.act_begin("stamp-law-act", manifest=["one"], root=tmp_path)
    journal.step_begin(aid, 0, "one", root=tmp_path)
    journal.bank_row("demo/rows.jsonl", {"id": "x", "ts": "2026-08-23T21:30:00Z"},
                     act_id=aid, root=tmp_path)
    journal.step_done(aid, 0, "one", ok=True, root=tmp_path)
    journal.act_end(aid, "pass", root=tmp_path)

    events = [json.loads(ln) for ln in
              Path(journal._store(tmp_path)).read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert {e["record"] for e in events} == {"act", "step", "bank", "act_end"}
    for e in events:
        assert "ts_claimed" not in e, f"{e['record']} grew a claimed field it never needed"
        assert e["ts"].endswith("Z") and "T" in e["ts"]


def test_journal_act_declares_exact_authority_regions_for_atlas_checkout(tmp_path):
    from laplace.core.records import journal

    (tmp_path / "contract").mkdir()
    aid = journal.act_begin(
        "interface-build",
        manifest=["implement", "test", "checkin"],
        regions=["src/laplace/conjugate_interface.py", "tests/conjugate-interface"],
        root=tmp_path,
    )
    recovered = journal.recover(tmp_path)["in_flight"][aid]

    assert recovered["authority_regions"] == [
        "src/laplace/conjugate_interface.py",
        "tests/conjugate-interface",
    ]
    with pytest.raises(ValueError, match="repository-relative"):
        journal.act_begin("bad", ["work"], regions=["../escape"], root=tmp_path)


def test_help_opens_no_act_and_touches_no_store(monkeypatch, tmp_path):
    """The no-run door: asking what the deposit does must write nothing. `--help` returns before
    act_begin, so the journal store is not even created."""
    from laplace.core.records import journal

    monkeypatch.setattr(reembed, "TIMING_LOG", tmp_path / ".reembed_timing.jsonl")

    assert reembed.main(["--help"]) == 0

    assert not Path(journal._store()).exists(), "a no-run must not open an act"
    assert not (tmp_path / ".reembed_timing.jsonl").exists()


def test_publication_receipt_binds_exact_artifacts_and_authored_inputs(monkeypatch, tmp_path):
    from laplace.representation.embed_router import _file_digest
    names = reembed.REQUIRED_PUBLICATION_NAMES
    for name in names:
        (tmp_path / name).write_text("candidate:" + name)
    _write_meaning_sidecar(tmp_path)
    for name in ("HANDOFF.md", "SESSION_HANDOFF_test.md"):
        (tmp_path / name).write_text("authored:" + name)
    expected = {name: _file_digest(tmp_path / name)
                for name in ("HANDOFF.md", "SESSION_HANDOFF_test.md")}
    monkeypatch.setenv("LAPLACE_REEMBED_INPUTS_JSON", json.dumps(expected))
    assert reembed._source_inputs(tmp_path) == expected
    report = reembed._publication_record(tmp_path, published=True,
                                        input_signature={"sources": expected})
    assert report["published"] and report["input_signature"]["sources"] == expected
    assert report["artifacts"] == {name: _file_digest(tmp_path / name) for name in names}
    assert report["absent_artifacts"] == list(reembed.OPTIONAL_PUBLICATION_NAMES)
    (tmp_path / ".self_isometries.npz").write_bytes(b"carried optional frames")
    carried = reembed._publication_record(tmp_path, published=True)
    assert carried["artifacts"][".self_isometries.npz"] == _file_digest(tmp_path / ".self_isometries.npz")
    assert carried["absent_artifacts"] == [".learned_keywords.json", ".escalate_briefs.json"]
    (tmp_path / "HANDOFF.md").write_text("moved after checkpoint")
    with pytest.raises(ValueError, match="authored input changed"):
        reembed._source_inputs(tmp_path)
    (tmp_path / ".metric_pairs.json").unlink()
    with pytest.raises(ValueError, match="missing artifacts"):
        reembed._publication_record(tmp_path, published=True)
    assert reembed._publication_record(tmp_path, published=False)["artifacts"] == {}


@pytest.mark.parametrize("damage", ["matrix-bytes", "index-shape", "missing-matrix", "missing-index"])
def test_publication_refuses_torn_meaning_vector_pair(tmp_path, damage):
    for name in reembed.REQUIRED_PUBLICATION_NAMES:
        (tmp_path / name).write_text("candidate:" + name)
    _write_meaning_sidecar(tmp_path)
    matrix = tmp_path / ".meaning_vectors.f32.npy"
    index = tmp_path / ".meaning_vectors.index.json"
    if damage == "matrix-bytes":
        raw = bytearray(matrix.read_bytes())
        raw[-1] ^= 1
        matrix.write_bytes(raw)
    elif damage == "index-shape":
        raw = json.loads(index.read_text())
        raw["shape"] = [2, 2]
        index.write_text(json.dumps(raw))
    elif damage == "missing-matrix":
        matrix.unlink()
    else:
        index.unlink()
    with pytest.raises(ValueError, match="publication"):
        reembed._publication_record(tmp_path, published=True)


@pytest.mark.parametrize("raise_error", [False, True])
def test_failed_deposit_restores_complete_prior_generation_but_keeps_authored_tail(
        monkeypatch, timing_log, capsys, raise_error):
    import os
    root = timing_log.parent
    _stub_heavy_calls(monkeypatch)
    before = {}
    for index, name in enumerate(reembed.PUBLICATION_NAMES):
        path = root / name
        path.write_text("prior usable generation:" + name)
        os.utime(path, ns=(1_700_000_000_000_000_000 + index,) * 2)
        before[name] = (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode)
    (root / "HANDOFF.md").write_text("new authored checkpoint stays recoverable")

    def decline_after_advancement(*args, **kwargs):
        # Inject the failed producer after both the meaning tree and embedding producer ran.
        assert (root / ".meaning_tree.json").read_text() == "{}"
        assert (root / ".self_embeddings.json").read_text() == "{}"
        for name in reembed.PUBLICATION_NAMES:
            (root / name).write_text("advanced but not accepted:" + name)
        if raise_error:
            raise RuntimeError("injected producer interruption")
        return {"shipped": False, "status": "INJECTED-METRIC-REFUSAL"}

    monkeypatch.setattr("laplace.representation.metric_distill.distill", decline_after_advancement)
    assert reembed.main([]) == 1
    assert {name: ((root / name).read_bytes(), (root / name).stat().st_mtime_ns,
                   (root / name).stat().st_mode) for name in before} == before
    assert (root / "HANDOFF.md").read_text() == "new authored checkpoint stays recoverable"
    assert timing_log.is_file(), "failure timing remains while publication is restored"
    lines = capsys.readouterr().out.splitlines()
    publication = json.loads(next(line.removeprefix("LAPLACE_PUBLICATION=")
                                  for line in lines if line.startswith("LAPLACE_PUBLICATION=")))
    assert not publication["published"] and publication["artifacts"] == {}
    assert not list(root.glob(".reembed-rollback-*"))


def test_preserved_snapshot_can_restore_after_process_loss(tmp_path):
    original = tmp_path / ".self_embeddings.json"
    original.write_text("old basis")
    _write_meaning_sidecar(tmp_path)
    pair = (".meaning_vectors.f32.npy", ".meaning_vectors.index.json")
    pair_before = {name: (tmp_path / name).read_bytes() for name in pair}
    snapshot = reembed._snapshot_publication(tmp_path)
    manifest = json.loads((snapshot / "manifest.json").read_text())
    assert manifest["artifacts"][".self_embeddings.json"]["present"]
    original.write_text("interrupted candidate basis")
    (tmp_path / ".metric_pairs.json").write_text("new candidate")
    (tmp_path / ".meaning_vectors.f32.npy").write_bytes(b"interrupted candidate matrix")
    (tmp_path / ".self_isometries.npz").write_bytes(b"new unaccepted frames")
    restored = reembed.restore_publication_snapshot(snapshot, tmp_path)
    assert original.read_text() == "old basis"
    assert not (tmp_path / ".metric_pairs.json").exists()
    assert not (tmp_path / ".self_isometries.npz").exists()
    assert {name: (tmp_path / name).read_bytes() for name in pair} == pair_before
    assert restored["uncovered_artifacts"] == []
    assert snapshot.is_dir(), "manual restoration keeps the backup for inspection"


def test_legacy_crash_backup_restores_its_group_with_explicit_coverage_gap(tmp_path):
    snapshot = reembed._snapshot_publication(tmp_path)
    manifest_path = snapshot / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["artifacts"] = {name: manifest["artifacts"][name]
                             for name in reembed._LEGACY_PUBLICATION_NAMES}
    manifest_path.write_text(json.dumps(manifest))
    frames = tmp_path / ".self_isometries.npz"
    frames.write_bytes(b"not covered by the historical backup")
    restored = reembed.restore_publication_snapshot(snapshot, tmp_path)
    assert frames.read_bytes() == b"not covered by the historical backup"
    assert set(restored["uncovered_artifacts"]) == {
        ".meaning_vectors.f32.npy", ".meaning_vectors.index.json", ".self_isometries.npz",
        ".self_record_floor.jsonl", ".learned_keywords.json", ".escalate_briefs.json",
    }


def test_failed_wire_keeps_prior_fallback_projection_and_new_verdict_history(tmp_path, monkeypatch, capsys):
    from laplace.representation import embed_router

    monkeypatch.setattr(reembed, "ROOT", tmp_path)
    monkeypatch.setattr(reembed, "require_system_runtime", lambda _root: None)
    verdicts = tmp_path / embed_router.VERDICTS_FILE
    original = {"id": "prior-node", "query": "prior continuity", "verdict": "wire"}
    verdicts.write_text(json.dumps(original) + "\n")
    cache = tmp_path / embed_router.LEARNED_KEYWORDS_FILE
    before = embed_router.load_learned_keywords(tmp_path)
    assert before and not cache.exists(), "ordinary fallback reads remain write-free"

    def failed_producer(*_args, **_kwargs):
        assert cache.is_file() and embed_router.load_learned_keywords(tmp_path) == before
        embed_router.bank_verdicts(tmp_path, [
            {"id": "new-node", "query": "new candidate tokens", "verdict": "wire"},
        ])
        assert "new-node" in embed_router.load_learned_keywords(tmp_path)
        return 1

    monkeypatch.setattr(reembed, "_run_deposit", failed_producer)
    assert reembed.main([]) == 1
    assert embed_router.load_learned_keywords(tmp_path) == before
    assert "new-node" in embed_router.rebuild_learned_keywords(tmp_path, persist=False)
    assert [json.loads(line)["id"] for line in verdicts.read_text().splitlines()] == ["prior-node", "new-node"]
    report = json.loads(next(line.removeprefix("LAPLACE_PUBLICATION=")
                             for line in capsys.readouterr().out.splitlines()
                             if line.startswith("LAPLACE_PUBLICATION=")))
    assert not report["published"]
    prepared = report["prepared_projections"]
    assert len(prepared) == 1 and prepared[0]["prior_presence"] == "absent"
    assert prepared[0]["presence_changed"] is True
    assert prepared[0]["prepared_sha256"] == embed_router._file_digest(cache)
    assert "before wire judgments" in prepared[0]["semantic_equivalence"]


def test_wrong_runtime_refuses_before_creating_publication_backup(tmp_path, monkeypatch):
    from laplace.core.runtime import RuntimePolicyError
    monkeypatch.setattr(reembed, "ROOT", tmp_path)
    def wrong_runtime(root):
        assert root == reembed.SOURCE_ROOT
        assert list(tmp_path.iterdir()) == [], "runtime refusal must precede every publication write"
        raise RuntimePolicyError("wrong interpreter")
    monkeypatch.setattr(reembed, "require_system_runtime", wrong_runtime)
    with pytest.raises(RuntimePolicyError, match="wrong interpreter"):
        reembed.main([])
    assert list(tmp_path.iterdir()) == []


# --- RUL-20260823-essence-side-ratified condition (v): the fold's node-delta is a TRACKED NUMBER ---

def test_node_delta_is_null_on_the_first_row_and_a_difference_after(monkeypatch, timing_log):
    """The essence join perturbs the fold - a joined node's embedded text moves, so its content
    hash moves, so the partition can move - and the ruling's price for landing it was that the
    perturbation be measured and named PER FOLD. The key is always present: `null` when there is
    no prior row to difference against, an integer when there is."""
    _stub_heavy_calls(monkeypatch)

    assert reembed.main([]) == 0
    first = json.loads(timing_log.read_text(encoding="utf-8").splitlines()[0])
    assert "node_delta" in first, "the key rides every row, not only the ones with a predecessor"
    assert first["node_delta"] is None
    assert first["nodes"] == len(FAKE_NODES)

    assert reembed.main([]) == 0
    second = json.loads(timing_log.read_text(encoding="utf-8").splitlines()[1])
    assert second["node_delta"] == 0, "an unmoved network is a delta of zero, not a missing key"


def test_node_delta_differences_against_the_previous_row_not_itself(monkeypatch, timing_log):
    """The count is read BEFORE the append. A delta taken after would difference the row against
    itself and read 0 forever - the exact silent-zero this number exists to prevent."""
    _stub_heavy_calls(monkeypatch)
    timing_log.write_text(json.dumps({"ts": "t", "mode": "flat-baseline", "nodes": 10}) + "\n",
                          encoding="utf-8")

    assert reembed.main([]) == 0

    row = json.loads(timing_log.read_text(encoding="utf-8").splitlines()[-1])
    assert row["nodes"] == len(FAKE_NODES) == 3
    assert row["node_delta"] == 3 - 10 == -7


def test_the_previous_count_reader_survives_a_half_written_tail(tmp_path):
    """`.reembed_timing.jsonl` is append-only and a kill can leave a torn last line. A malformed
    line is skipped exactly as `digest_mint.load_rows` skips one - the reader falls back to the
    last row it could parse rather than going blind, or crashing the deposit at its final step
    after every store it guards has already been written.

    Read against the reader rather than through `main()` on purpose: a torn tail has no newline,
    so the append lands ON it and the resulting line is not the deposit's row to assert about.
    That is the writer's pre-existing shape, and it is not what this number is for."""
    log = tmp_path / ".reembed_timing.jsonl"

    assert reembed._previous_nodes(log) is None, "no file at all is a null delta, not a crash"
    log.write_text("", encoding="utf-8")
    assert reembed._previous_nodes(log) is None, "an empty log has no predecessor"

    log.write_text(json.dumps({"ts": "t", "nodes": 8}) + "\n" + '{"ts": "t", "nodes": 99',
                   encoding="utf-8")
    assert reembed._previous_nodes(log) == 8, "the torn tail is skipped, the row above is read"

    log.write_text(json.dumps({"ts": "t", "total": 1.0}) + "\n", encoding="utf-8")
    assert reembed._previous_nodes(log) is None, "a row with no count is not a count of zero"


def test_trigger_receipt_is_correlated_to_exact_deposit_act(tmp_path):
    """A swallowed append cannot license this act with the previous act's verdict."""
    from laplace.engine.meaning_upfold import TRIGGER_LOG_FILE

    path = tmp_path / TRIGGER_LOG_FILE
    old = {"gate": "rung-12a", "deposit_act_id": "old", "events": []}
    current = {"gate": "rung-12a", "deposit_act_id": "current",
               "events": [{"kind": "delta_measured"}]}
    path.write_text(json.dumps(old) + "\n" + json.dumps(current) + "\n", encoding="utf-8")

    assert reembed._trigger_receipt_for_act(tmp_path, "missing") is None
    assert reembed._trigger_receipt_for_act(tmp_path, "current") == current

    # Duplicate ids are corrupt/ambiguous and therefore cannot license a mode.
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(current) + "\n")
    assert reembed._trigger_receipt_for_act(tmp_path, "current") is None


def test_a_log_of_rows_without_the_key_still_yields_a_delta(monkeypatch, timing_log):
    """Every one of the 90 rows banked before this cure carries `nodes` but no `node_delta`, so
    the FIRST joined fold must still be able to difference against the fold before it - the
    baseline the ruling asks for is the pre-join network, and it is already on disk."""
    _stub_heavy_calls(monkeypatch)
    timing_log.write_text(
        "".join(json.dumps({"ts": "t", "mode": "flat-baseline", "nodes": n}) + "\n"
                for n in (22376, 22377)), encoding="utf-8")

    assert reembed.main([]) == 0

    row = json.loads(timing_log.read_text(encoding="utf-8").splitlines()[-1])
    assert row["node_delta"] == 3 - 22377


def test_restore_publication_route_never_reads_the_current_publication(monkeypatch, tmp_path):
    """7 November 2026: an interrupted deposit left artifacts that no longer matched their receipt, and
    `--restore-publication` (the printed recovery path) was unreachable because main read the current
    publication first and refused PUBLICATION_ARTIFACTS_CHANGED. The restore takes the lock and nothing else."""
    import contextlib
    from laplace.representation import source_publication as publication

    def refuse(*_args, **_kwargs):
        raise AssertionError("the restore route must not read the current publication")

    restored = {}
    monkeypatch.setattr(publication, "selections", refuse)
    monkeypatch.setattr(publication, "current", refuse)
    monkeypatch.setattr(publication, "assert_no_pending", lambda root: None)
    monkeypatch.setattr(publication, "publication_lock", lambda root: contextlib.nullcontext())
    monkeypatch.setattr(reembed, "require_system_runtime", lambda root: None)
    monkeypatch.setattr(reembed, "restore_publication_snapshot", lambda snapshot, root: restored.update(snapshot=snapshot) or {"artifacts": [], "uncovered_artifacts": []})
    snapshot = tmp_path / "snap"
    snapshot.mkdir()
    assert reembed.main(["--restore-publication", str(snapshot)]) == 0
    assert restored["snapshot"] == snapshot.resolve()
