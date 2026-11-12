"""Incremental metric consumer tests, including real CUDA arithmetic on synthetic wire."""
import json

import numpy as np
import pytest

from laplace.pipeline import dial_profiles as dials
from laplace.representation import metric_distill as md


def test_changed_retired_and_replayed_pairs():
    old = [("a", "b"), ("a", "c"), ("b", "d"), ("d", "e")]
    now = [("a", "c"), ("b", "d"), ("d", "e"), ("e", "f")]
    changed, replay, retired = md.pair_delta(now, old, ["a"], 1.0, 7)
    assert changed == [("a", "c"), ("e", "f")]
    assert replay == [("b", "d"), ("d", "e")]
    assert retired == [("a", "b")]
    assert ("a", "b") not in changed + replay


def test_producer_accumulates_without_a_banked_metric(tmp_path):
    md.record_embedding_changes(tmp_path, ["a", "b"])
    state = md.record_embedding_changes(tmp_path, ["b", "c"])
    assert state["banked"] is None
    assert state["pending"] == {"a": 1, "b": 2, "c": 1}
    verdict = md.distill(tmp_path, {}, {}, changed_ids=[])
    assert verdict["status"] == "CURE-B-BASELINE-001"
    assert md.record_embedding_changes(tmp_path, [])["pending"] == state["pending"]


def _fixture(monkeypatch):
    vecs = {str(i): np.eye(4, dtype="float32")[i % 4] for i in range(12)}
    pairs = [(str(i), str(i + 1)) for i in range(11)]
    evaluation = {"ids": ["0", "1", "2"], "pairs": [["0", "1"]],
                  "X": np.eye(4, dtype="float32"), "table": np.array([[0, 1, 2]], dtype="int32")}
    calls = []
    def fit(v, p, **kw):
        calls.append((p, kw))
        return {"M": np.eye(4, dtype="float32") * (1 + len(calls) / 100),
                "evaluation": kw.get("evaluation") or evaluation, "auc_identity": 0.5,
                "auc_trained": 0.99, "device": "gpu", "n_train": len(p),
                "n_held": 1, "spectrum": {"top": [1.01], "bottom": [1.01]}, "drift": 0.02}
    monkeypatch.setattr(md, "train", fit)
    monkeypatch.setattr(md, "wire_pairs", lambda *a: pairs)
    monkeypatch.setattr(md, "hello_gate", lambda *a: {"found": 5, "total": 5, "pass": True})
    return vecs, pairs, calls


def _reusable_generation(tmp_path, monkeypatch, *, render_artifacts=None):
    vecs, pairs, calls = _fixture(monkeypatch)
    for name in (".self_embeddings.json", ".self_graded.json", ".meaning_tree.json"):
        (tmp_path / name).write_text(json.dumps({"fixture": name}))
    first = md.distill(tmp_path, {}, vecs, full_metric=True, render_artifacts=render_artifacts)
    assert first["shipped"]
    return vecs, pairs, calls, first


def test_exact_empty_increment_reuses_fit_but_recalls_and_rebinds_staged_render(tmp_path, monkeypatch):
    # store_after observes the old render; render_artifacts owns the completed publication.
    published_render = b'{"published":1}'
    vecs, _, calls, first = _reusable_generation(
        tmp_path, monkeypatch,
        render_artifacts={".self_graded.json": md._digest(published_render)},
    )
    (tmp_path / ".self_graded.json").write_bytes(published_render)
    paths = (tmp_path / md.METRIC_FILE, md._pairs_path(tmp_path))
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in paths}
    with np.load(paths[0], allow_pickle=False) as artifact:
        prior_M = artifact["M"]
    recall = []
    def check(root, net, candidate):
        np.testing.assert_array_equal(candidate, prior_M)
        recall.append(candidate)
        return {"found": 5, "total": 5, "pass": True}
    monkeypatch.setattr(md, "hello_gate", check)
    monkeypatch.setattr(md, "train", lambda *a, **kw: pytest.fail("unchanged fit must not run"))
    monkeypatch.setattr(md, "_bank_pairs", lambda *a, **kw: pytest.fail("unchanged pairs must not rewrite"))
    next_render = {".self_graded.json": md._digest(b'{"next-staged":2}')}

    reused = md.distill(tmp_path, {}, vecs, changed_ids=[], render_artifacts=next_render)

    assert reused["shipped"] and reused["fit_reused"] and len(recall) == 1
    assert reused["device"] == "not-run" and reused["reused_fit_device"] == "gpu"
    assert reused["reused_from_metric"] == first["metric_hash"]
    assert reused["evaluation_hash"] == first["evaluation_hash"]
    assert reused["render_artifacts"] == next_render
    assert len(calls) == 1
    assert {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in paths} == before
    state = json.loads(md._receipt_path(tmp_path).read_text())
    assert state["banked"]["pairs_handle"] == md._digest(paths[1].read_bytes())
    assert not state["pending"]


@pytest.mark.parametrize("moved", ["basis", "tree", "render", "dial", "pending", "pair-added", "pair-retired"])
def test_empty_increment_reuse_requires_all_dependencies_unchanged(tmp_path, monkeypatch, moved):
    vecs, pairs, calls, _ = _reusable_generation(tmp_path, monkeypatch)
    changed_ids = []
    if moved in {"basis", "tree", "render"}:
        filename = {"basis": ".self_embeddings.json", "tree": ".meaning_tree.json",
                    "render": ".self_graded.json"}[moved]
        (tmp_path / filename).write_text('{"changed":true}')
    elif moved == "dial":
        current = md.dials.current("engine-metric")
        monkeypatch.setattr(md.dials, "current", lambda _kind: {**current, "dial_set_id": "changed"})
    elif moved == "pending":
        md.record_embedding_changes(tmp_path, ["3"])
    elif moved == "pair-added":
        pairs.append(("0", "2"))
    else:
        pairs.pop()
    result = md.distill(tmp_path, {}, vecs, changed_ids=changed_ids)
    assert not result["fit_reused"]
    assert len(calls) == 2


def test_empty_increment_reuse_cannot_inherit_prior_recall_success(tmp_path, monkeypatch):
    vecs, _, calls, _ = _reusable_generation(tmp_path, monkeypatch)
    monkeypatch.setattr(md, "hello_gate", lambda *a: {"found": 4, "total": 5, "pass": False})
    paths = (tmp_path / md.METRIC_FILE, md._pairs_path(tmp_path))
    before = {path: path.read_bytes() for path in paths}
    result = md.distill(tmp_path, {}, vecs, changed_ids=[])
    assert result["fit_reused"] and not result["shipped"]
    assert result["status"] == "CURE-B-HELLO-001" and len(calls) == 1
    assert {path: path.read_bytes() for path in paths} == before


@pytest.mark.parametrize("moved", ["basis", "accounting", "dial"])
def test_empty_increment_reuse_refuses_concurrent_mutation_after_recall(tmp_path, monkeypatch, moved):
    vecs, _, calls, _ = _reusable_generation(tmp_path, monkeypatch)
    current = md.dials.current("engine-metric")
    def mutate(root, net, candidate):
        if moved == "basis":
            (root / ".self_embeddings.json").write_text('{"new-producer":true}')
        elif moved == "accounting":
            md.record_embedding_changes(root, ["3"])
        else:
            monkeypatch.setattr(md.dials, "current", lambda _kind: {**current, "dial_set_id": "new-producer"})
        return {"found": 5, "total": 5, "pass": True}
    monkeypatch.setattr(md, "hello_gate", mutate)
    result = md.distill(tmp_path, {}, vecs, changed_ids=[])
    assert result["fit_reused"] and not result["shipped"]
    assert result["status"] == "CURE-B-CONCURRENT-001" and len(calls) == 1
    if moved == "accounting":
        assert md.record_embedding_changes(tmp_path, [])["pending"] == {"3": 1}


@pytest.mark.parametrize("corrupt", ["metric", "pairs", "evaluation"])
def test_empty_increment_reuse_requires_verified_lineage_and_evaluation(tmp_path, monkeypatch, corrupt):
    vecs, _, calls, _ = _reusable_generation(tmp_path, monkeypatch)
    path = tmp_path / md.METRIC_FILE
    expected = {"metric": "CURE-B-LINEAGE-001", "pairs": "CURE-B-PAIRS-001",
                "evaluation": "CURE-B-EVALUATION-001"}[corrupt]
    if corrupt == "metric":
        path.write_bytes(b"not the banked metric")
    elif corrupt == "pairs":
        md._pairs_path(tmp_path).write_text('{"active_pairs":[]}')
    else:
        with np.load(path, allow_pickle=False) as artifact:
            arrays = {key: artifact[key] for key in artifact.files}
        arrays["evaluation_X"][0, 0] += 0.25
        np.savez(path, **arrays)
        receipt = json.loads(md._receipt_path(tmp_path).read_text())
        receipt["banked"]["metric_hash"] = md._digest(path.read_bytes())
        md._receipt_path(tmp_path).write_text(json.dumps(receipt))
    result = md.distill(tmp_path, {}, vecs, changed_ids=[])
    assert not result["shipped"] and result["status"] == expected and len(calls) == 1


def test_lineage_pending_refusal_and_retirement(tmp_path, monkeypatch):
    vecs, pairs, calls = _fixture(monkeypatch)
    first = md.distill(tmp_path, {}, vecs, full_metric=True)
    assert first["shipped"] and first["parent"] == "GENESIS"
    prior = (tmp_path / md.METRIC_FILE).read_bytes()
    md.record_embedding_changes(tmp_path, ["2"])
    monkeypatch.setattr(md, "hello_gate", lambda *a: {"found": 4, "total": 5, "pass": False})
    bad = md.distill(tmp_path, {}, vecs, changed_ids=["3"])
    assert not bad["shipped"]
    assert (tmp_path / md.METRIC_FILE).read_bytes() == prior
    assert set(md.record_embedding_changes(tmp_path, [])["pending"]) == {"2", "3"}
    monkeypatch.setattr(md, "hello_gate", lambda *a: {"found": 5, "total": 5, "pass": True})
    retired = pairs.pop()
    second = md.distill(tmp_path, {}, vecs, changed_ids=["4"])
    assert second["shipped"] and second["parent"] == first["metric_hash"]
    assert second["changed_count"] == 3
    assert second["changed_ids_handle"] == md._digest(json.dumps(["2", "3", "4"]).encode())
    assert calls[-1][1]["initial_M"] is not None
    assert retired not in calls[-1][0]
    state = json.loads(md._receipt_path(tmp_path).read_text())
    assert not state["pending"] and len(state["history"]) == 2
    assert list(retired) not in md._read_pairs(tmp_path)["active_pairs"]
    assert first["evaluation_hash"] == second["evaluation_hash"]


def test_auc_regression_keeps_parent_and_pending(tmp_path, monkeypatch):
    vecs, pairs, calls = _fixture(monkeypatch)
    first = md.distill(tmp_path, {}, vecs, full_metric=True)
    fit = md.train
    def degraded(*args, **kw):
        return {**fit(*args, **kw), "auc_trained": 0.97}
    monkeypatch.setattr(md, "train", degraded)
    bad = md.distill(tmp_path, {}, vecs, changed_ids=["3"])
    assert bad["status"] == "CURE-B-AUC-002" and not bad["shipped"]
    state = md.record_embedding_changes(tmp_path, [])
    assert state["banked"]["metric_hash"] == first["metric_hash"]
    assert "3" in state["pending"]


def test_increment_requires_explicit_producer_accounting(tmp_path, monkeypatch):
    vecs, _, _ = _fixture(monkeypatch)
    assert md.distill(tmp_path, {}, vecs, full_metric=True)["shipped"]
    result = md.distill(tmp_path, {}, vecs)
    assert result["status"] == "CURE-B-INPUT-001"


def test_full_recovery_replaces_broken_sidecar_with_new_evaluation_and_preserves_evidence(tmp_path, monkeypatch):
    vecs, _, calls = _fixture(monkeypatch)
    (tmp_path / ".self_embeddings.json").write_text('{"basis":1}')
    assert md.distill(tmp_path, {}, vecs, full_metric=True)["shipped"]
    md._pairs_path(tmp_path).write_text('{"active_pairs":[],"evaluation_ids":["x"]}')
    old = {p.name: p.read_bytes() for p in
           (md._pairs_path(tmp_path), md._receipt_path(tmp_path), tmp_path / md.METRIC_FILE)}
    assert md.distill(tmp_path, {}, vecs, changed_ids=[])["status"] == "CURE-B-PAIRS-001"
    result = md.distill(tmp_path, {}, vecs, changed_ids=[], full_metric=True)
    assert result["shipped"]
    assert calls[-1][1]["evaluation"] is None and calls[-1][1]["initial_M"] is None
    preserved = tmp_path / result["prior_generation_preserved_at"]
    assert {name: (preserved / name).read_bytes() for name in old} == old
    from laplace.representation import embed_router
    from laplace.engine import taste_retrieval
    assert embed_router.metric_status(tmp_path)["state"] == "applied-fresh"
    assert taste_retrieval._metric_status(tmp_path, 4)[1]["state"] == "applied-fresh"
    # A moved basis is rejected by both consumers even when a caller preserves its mtime.
    import os
    basis = tmp_path / ".self_embeddings.json"
    stat = basis.stat()
    basis.write_text('{"basis":2}')
    os.utime(basis, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    with pytest.raises(embed_router.MetricGenerationMismatch):
        embed_router.load_metric(tmp_path)
    with pytest.raises(embed_router.MetricGenerationMismatch):
        taste_retrieval._metric_status(tmp_path, 4)


def test_candidate_recall_runs_before_metric_or_pairs_are_published(tmp_path, monkeypatch):
    vecs, _, _ = _fixture(monkeypatch)
    assert md.distill(tmp_path, {}, vecs, full_metric=True)["shipped"]
    old = {p.name: p.read_bytes() for p in (tmp_path / md.METRIC_FILE, md._pairs_path(tmp_path))}
    def reject(root, net, candidate):
        assert candidate.shape == (4, 4)
        assert {name: (root / name).read_bytes() for name in old} == old
        return {"found": 4, "total": 5, "pass": False}
    monkeypatch.setattr(md, "hello_gate", reject)
    result = md.distill(tmp_path, {}, vecs, changed_ids=[])
    assert result["status"] == "CURE-B-HELLO-001" and not result["shipped"]
    assert {name: (tmp_path / name).read_bytes() for name in old} == old


def test_pair_publication_failure_restores_whole_metric_generation(tmp_path, monkeypatch):
    vecs, _, _ = _fixture(monkeypatch)
    assert md.distill(tmp_path, {}, vecs, full_metric=True)["shipped"]
    paths = (tmp_path / md.METRIC_FILE, md._pairs_path(tmp_path), md._receipt_path(tmp_path))
    old = {path.name: path.read_bytes() for path in paths}
    bank = md._bank_pairs
    def fail_after_write(*args):
        bank(*args)
        raise OSError("planted interruption after pairs write")
    monkeypatch.setattr(md, "_bank_pairs", fail_after_write)
    result = md.distill(tmp_path, {}, vecs, changed_ids=[])
    assert result["status"] == "CURE-B-PUBLISH-001" and not result["shipped"]
    assert {path.name: path.read_bytes() for path in paths} == old


def test_gpu_required_never_calls_cpu(monkeypatch):
    monkeypatch.setattr(md, "fit_backend", lambda device: ("cpu", "probe failed"))
    monkeypatch.setattr(md, "_fit_cpu", lambda *a, **kw: pytest.fail("CPU fit must not run"))
    with pytest.raises(ValueError, match="CURE-B-GPU-001"):
        md.train({}, [], require_gpu=True)


def test_no_delta_preserves_gpu_metric_exactly():
    from test_metric_distill import _island_vecs
    vecs, pairs = _island_vecs()
    full = md.train(vecs, pairs, require_gpu=True)
    incremental = md.train(vecs, [], initial_M=full["M"], evaluation=full["evaluation"],
                           active_pairs=pairs, require_gpu=True)
    np.testing.assert_array_equal(incremental["M"], full["M"])
    assert incremental["auc_trained"] == full["auc_trained"]


def test_gpu_incremental_matches_full_synthetic_within_tolerance():
    # Two vocabulary islands coupled across the islands. Compare a warm delta/replay fit to a fresh full fit
    # on identical evaluation trials, including one changed endpoint vector.
    rng = np.random.default_rng(8)
    vecs = {}
    for i in range(24):
        v = np.zeros(64, dtype="float32")
        v[i % 2] = 1
        v += rng.normal(0, 0.01, 64).astype("float32")
        vecs[str(i)] = v / np.linalg.norm(v)
    pairs = sorted(tuple(sorted((str(i), str(j)))) for i in range(24) for j in range(i + 1, 24) if i % 2 != j % 2)
    first = md.train(vecs, pairs, require_gpu=True)
    vecs["0"] = vecs["0"] + np.float32(0.001)
    changed, replay, _ = md.pair_delta(pairs, pairs, ["0"], 0.1, 7)
    inc = md.train(vecs, changed + replay, initial_M=first["M"], evaluation=first["evaluation"],
                   active_pairs=pairs, require_gpu=True)
    full = md.train(vecs, pairs, evaluation=first["evaluation"], require_gpu=True)
    assert first["auc_trained"] > first["auc_identity"] and first["drift"] > 1
    np.testing.assert_allclose(inc["M"], full["M"], atol=0.03, rtol=0)
    assert abs(inc["auc_trained"] - full["auc_trained"]) <= 0.01


def test_explicit_successor_admits_replay_schema(tmp_path, monkeypatch):
    schema = dials.genesis()
    metric = next(row for row in schema if row["scope"] == "engine-metric")
    assert metric["dials"]["replay_fraction"]["value"] == 0.02
    # Model an actual older ledger: today's genesis already declares replay_fraction.
    del metric["dials"]["replay_fraction"]
    metric["dial_set_id"] = dials._hash(metric)
    with monkeypatch.context() as patch:
        patch.setattr(dials, "genesis", lambda: schema)
        dials.pour_genesis(tmp_path)
    before = dials.current("engine-metric", tmp_path)
    assert "replay_fraction" not in before["dials"]
    ledger = tmp_path / dials.STORE
    predecessor_bytes = ledger.read_bytes()
    dials.pour_genesis(tmp_path)
    assert ledger.read_bytes() == predecessor_bytes, "new declarations must not silently upgrade old scopes"
    row = dials.set_value("engine-metric", "replay_fraction", "0.02",
                          by="test", why="bounded replay", root=tmp_path)
    assert row["parent_dial_set"] == before["dial_set_id"]
    assert row["dials"]["replay_fraction"]["value"] == 0.02
    assert row["dials"]["replay_fraction"]["range"] == [0.0, 1.0]
    assert row["dials"]["replay_fraction"]["admitted_by"] == "test"
    assert ledger.read_bytes().startswith(predecessor_bytes)
