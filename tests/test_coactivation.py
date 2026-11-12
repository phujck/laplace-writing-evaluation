"""Tests for coactivation (Component 1 analyser) - telemetry of use -> the reclustering signal.

Contracts: a co-fire set is recorded GRADE-TAGGED; cofire splits same-grade pairs (intra, the reclustering
signal) from cross-grade pairs (inter, the link signal); repeated same-grade co-fire surfaces as a
recluster candidate; observed (dynamic) coupling counts co-fires; and the keeper ring's trace yields a
grade-tagged activated set that records and reads back end-to-end. Each test isolates telemetry to a tmp
state dir via LAPLACE_STATE, so the analyser reads only its own events."""

from __future__ import annotations

from laplace.engine import coactivation, keeper, keeper_ring


def _leaf(keywords, grade_kw="q"):
    return {"kind": "py", "essence": "e", "keywords": keywords, "sealed": False}


def test_cofire_splits_inter_and_intra_grade(tmp_path, monkeypatch):
    monkeypatch.setenv("LAPLACE_STATE", str(tmp_path))
    coactivation.record([("a", 1), ("b", 1), ("c", 2)])     # a,b same grade; c a grade up
    cf = coactivation.cofire()
    assert cf["intra"][("a", "b")] == 1                     # same grade -> intra (reclustering signal)
    assert cf["inter"][("a", "c")] == 1                     # different grade -> inter (link signal)
    assert cf["inter"][("b", "c")] == 1
    assert ("a", "c") not in cf["intra"]


def test_recluster_candidates_surface_repeated_sibling_cofire(tmp_path, monkeypatch):
    monkeypatch.setenv("LAPLACE_STATE", str(tmp_path))
    for _ in range(3):
        coactivation.record([("x", 1), ("y", 1), ("z", 2)])
    cand = coactivation.recluster_candidates(min_count=2)
    recl = {(c["a"], c["b"]) for c in cand["recluster"]}
    assert ("x", "y") in recl                               # same-grade, co-fired 3x -> recluster
    strong = {(c["a"], c["b"]) for c in cand["strengthen"]}
    assert ("x", "z") in strong and ("y", "z") in strong    # cross-grade links -> strengthen
    assert cand["events_read"] == 3


def test_observed_coupling_is_dynamic_cofire_count(tmp_path, monkeypatch):
    monkeypatch.setenv("LAPLACE_STATE", str(tmp_path))
    coactivation.record([("p", 1), ("q", 1)])
    coactivation.record([("p", 1), ("q", 1)])
    assert coactivation.observed_coupling("p", "q") == 2    # co-fired twice in use
    assert coactivation.observed_coupling("p", "absent") == 0


def test_record_dedupes_within_one_reconstruction(tmp_path, monkeypatch):
    monkeypatch.setenv("LAPLACE_STATE", str(tmp_path))
    coactivation.record([("a", 1), ("a", 1), ("b", 1)])     # a recurs in one call -> co-fires once
    assert coactivation.cofire()["intra"][("a", "b")] == 1
    assert coactivation.record([]) is None                  # nothing fired -> nothing banked


def test_ring_trace_is_grade_tagged_and_records_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("LAPLACE_STATE", str(tmp_path))
    leaves = {"a/x.py": _leaf(["q"]), "a/y.py": _leaf(["q"]), "b/z.py": _leaf(["other"])}
    nodes = keeper.build_tree(leaves)
    tr: dict = {}
    keeper_ring.reconstruct(nodes, "", "q", trace=tr)
    assert tr["activated"] and all(len(t) == 2 for t in tr["activated"])    # (id, grade) pairs
    assert len({g for _id, g in tr["activated"]}) >= 2                      # several grades fired
    ev = coactivation.record(tr["activated"], caller="eigen", goal="q")
    assert ev is not None and ev["phase"] == "coactivation"
    assert coactivation.recluster_candidates(min_count=1)["events_read"] == 1
