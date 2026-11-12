"""The cross-program technique resolver, pinned (technique_lens.py).

The clustering itself rides the bge embedder (clean-roomed live by ``scripts/technique_cluster.py``);
these tests pin the MECHANICS that must hold regardless of the geometry - the grouping/gating, the
shared-atom coupling, the ring-UP stamp, and the lifted move-edges - by INJECTING a clustering
(``_labels``) so the test runs offline and deterministic, exactly as the network's HashBackend lets
the descent tests run without a model.

Fixture: two tiny regraded ladders (two authors). The injected clustering fuses one rung from each
into a cross-program technique; a same-theme pair is left for the >=2-theme gate to reject; one file
carries a `move` for the transfer-edge lift.
"""
from __future__ import annotations

import json

from laplace.engine import technique_lens

_GEN_A1 = {"label": "Feedback control alpha", "essence": "feedback program",
           "moves": [{"from": "Feedback control alpha", "to": "State preparation alpha",
                      "paper": "W1", "why": "the paper carried feedback into state prep"}],
           "rungs": [{"name": "lyapunov-feedback", "essence": "lyapunov measurement feedback",
                      "papers": ["W1"]}]}
_GEN_A2 = {"label": "State preparation alpha", "essence": "state prep program", "moves": [],
           "rungs": [{"name": "state-prep-x", "essence": "x prep", "papers": ["W2"]},
                     {"name": "state-prep-y", "essence": "y prep", "papers": ["W3"]}]}
_GEN_B1 = {"label": "Feedback control beta", "essence": "feedback program (other author)",
           "moves": [],
           "rungs": [{"name": "lyapunov-feedback-beta", "essence": "lyapunov feedback again",
                      "papers": ["W9"]}]}


def _write(repo):
    d = repo / "collaborator_corpus" / "_structural"
    d.mkdir(parents=True)
    (d / "aatkins_regraded.json").write_text(
        json.dumps({"_key": "aatkins", "generators": [_GEN_A1, _GEN_A2]}), encoding="utf-8")
    (d / "bbecker_regraded.json").write_text(
        json.dumps({"_key": "bbecker", "generators": [_GEN_B1]}), encoding="utf-8")


def _build_net(repo):
    """A synthetic network holding every rung + theme (generator) node, so the overlay has live
    endpoints to fuse and to lift moves between."""
    records = technique_lens._rung_instances(repo)
    rid = {meta["name"]: r for r, meta in records}            # name -> rung node id
    theme = {meta["name"]: meta["theme_id"] for r, meta in records}
    nodes = {"": {"id": "", "grade": 9, "parent": None, "leaf": False, "members": []}}
    reach: dict = {}
    lenses: dict = {}
    for r, meta in records:                                    # rung nodes
        nodes[r] = {"id": r, "grade": 1, "parent": meta["theme_id"], "leaf": True, "members": []}
        reach[r] = set()
        lenses[r] = ["physics"]
    for tid in set(theme.values()):                           # theme (generator) nodes - for moves
        nodes[tid] = {"id": tid, "grade": 2, "parent": "", "leaf": False, "members": []}
        reach[tid] = set()
        lenses[tid] = ["physics"]
    return nodes, reach, lenses, rid, theme


def test_cross_program_fuse_and_couple(tmp_path):
    """A cluster spanning two themes fuses into one technique:// apex; the shared atom lands in every
    member's reach (the coupling); each member rings UP via `techniques`."""
    _write(tmp_path)
    nodes, reach, lenses, rid, theme = _build_net(tmp_path)
    labels = {rid["lyapunov-feedback"]: 0, rid["lyapunov-feedback-beta"]: 0,
              rid["state-prep-x"]: 2, rid["state-prep-y"]: 2}
    techs = technique_lens.technique_overlay(tmp_path, nodes, reach, lenses, _labels=labels)

    assert len(techs) == 1                                    # one cross-program technique
    t = techs[0]
    apex = t["technique_id"]
    assert apex.startswith("technique://")
    assert t["cross_author"] is True
    assert set(t["members"]) == {rid["lyapunov-feedback"], rid["lyapunov-feedback-beta"]}
    # the apex node + its badge
    assert nodes[apex]["technique_apex"] is True
    assert lenses[apex][0] == "technique"
    assert apex in nodes[""]["members"]                       # hung under the root, a hot hub
    # every member rings UP and shares the coupling atom
    for nm in ("lyapunov-feedback", "lyapunov-feedback-beta"):
        assert nodes[rid[nm]]["techniques"] == [apex]
        assert any(x.startswith("technique::") for x in reach[rid[nm]])
    # the apex's reach is the union + the atom (a broad pull surfaces it)
    assert any(x.startswith("technique::") for x in reach[apex])


def test_single_theme_cluster_is_not_a_technique(tmp_path):
    """The >=2-theme gate: two rungs of the SAME program are not a transferable technique, so they
    are left un-fused (no apex, no uplink) - high precision, like identity_lens's >=2-lens gate."""
    _write(tmp_path)
    nodes, reach, lenses, rid, theme = _build_net(tmp_path)
    labels = {rid["lyapunov-feedback"]: 0, rid["lyapunov-feedback-beta"]: 0,
              rid["state-prep-x"]: 2, rid["state-prep-y"]: 2}
    technique_lens.technique_overlay(tmp_path, nodes, reach, lenses, _labels=labels)

    for nm in ("state-prep-x", "state-prep-y"):
        assert "techniques" not in nodes[rid[nm]]             # same theme -> never fused
    assert not any(n.startswith("technique://") and
                   rid["state-prep-x"] in nodes[n].get("members", []) for n in nodes)


def test_moves_lift_to_conjectural_transfer_edges(tmp_path):
    """The generators' `moves` become directed theme->theme transfer edges: a conjectural shared
    atom on both ends (surfaces on ideation, not recall) + a `transfers` / `transferred_into`
    render handle carrying the author's own `why`."""
    _write(tmp_path)
    nodes, reach, lenses, rid, theme = _build_net(tmp_path)
    technique_lens.technique_overlay(tmp_path, nodes, reach, lenses, _labels={})

    src = theme["lyapunov-feedback"]                          # gen "Feedback control alpha"
    dst = theme["state-prep-x"]                               # gen "State preparation alpha"
    assert nodes[src]["transfers"] == [{"to": dst, "paper": "W1",
                                        "why": "the paper carried feedback into state prep"}]
    assert nodes[dst]["transferred_into"] == [{"from": src, "paper": "W1"}]
    # the conjectural atom couples the two themes (and ONLY conjecturally)
    shared = reach[src] & reach[dst]
    assert shared and all(x.startswith(technique_lens.CONJECTURE_PREFIX) for x in shared)


def _count_calls(monkeypatch, X=object()):
    """Stub the two expensive halves of the resolve path (the 9MB vector read and the sklearn
    clustering) and count how often each is actually entered."""
    calls = {"embed": 0, "cluster": 0}

    def fake_embed(repo_root, names, texts, get_backend):
        calls["embed"] += 1
        return X

    def fake_cluster(x, tau):
        calls["cluster"] += 1
        return [0, 0, 1]

    monkeypatch.setattr(technique_lens, "_embed", fake_embed)
    monkeypatch.setattr(technique_lens, "_cluster", fake_cluster)
    return calls


def test_label_cache_hit_skips_embed_and_cluster(tmp_path, monkeypatch):
    """The clustering verdict is content-hash cached: an unmoved corpus re-reads the labels instead
    of re-reading the vectors and re-importing/re-running sklearn - and returns the SAME labels, so
    every coupling downstream of the overlay is byte-identical."""
    calls = _count_calls(monkeypatch)
    rids, texts = ["r1", "r2", "r3"], ["alpha", "beta", "gamma"]
    first = technique_lens._labels_cached(tmp_path, rids, texts, 0.3, lambda: None)
    assert (calls["embed"], calls["cluster"]) == (1, 1)
    assert (tmp_path / technique_lens.LABEL_CACHE_FILE).is_file()

    second = technique_lens._labels_cached(tmp_path, rids, texts, 0.3, lambda: None)
    assert second == first
    assert (calls["embed"], calls["cluster"]) == (1, 1)         # nothing re-cut


def test_label_cache_misses_when_anything_moves(tmp_path, monkeypatch):
    """A changed rung text, a changed rung id, a re-tuned tau, or a corrupt cache all MISS - the
    cache can only ever skip work the corpus has not invalidated."""
    calls = _count_calls(monkeypatch)
    rids, texts = ["r1", "r2", "r3"], ["alpha", "beta", "gamma"]
    technique_lens._labels_cached(tmp_path, rids, texts, 0.3, lambda: None)

    technique_lens._labels_cached(tmp_path, rids, ["alpha", "beta", "DELTA"], 0.3, lambda: None)
    assert calls["cluster"] == 2                                # text moved
    technique_lens._labels_cached(tmp_path, ["r1", "r2", "r9"], texts, 0.3, lambda: None)
    assert calls["cluster"] == 3                                # id moved
    technique_lens._labels_cached(tmp_path, rids, texts, 0.42, lambda: None)
    assert calls["cluster"] == 4                                # the knob moved

    (tmp_path / technique_lens.LABEL_CACHE_FILE).write_text("{not json", encoding="utf-8")
    assert technique_lens._labels_cached(tmp_path, rids, texts, 0.42, lambda: None) == [0, 0, 1]
    assert calls["cluster"] == 5                                # a corrupt cache is a miss


def test_label_cache_absent_embedder_carries_no_layer(tmp_path, monkeypatch):
    """An unavailable embedder still carries no technique layer (and writes no cache) - the
    graceful-degradation contract is unchanged by the cache."""
    monkeypatch.setattr(technique_lens, "_embed", lambda *a, **k: None)
    assert technique_lens._labels_cached(tmp_path, ["r1"], ["alpha"], 0.3, lambda: None) is None
    assert not (tmp_path / technique_lens.LABEL_CACHE_FILE).exists()


def test_empty_without_embedder_or_data(tmp_path):
    """No regraded ladders -> the resolver returns empty and the overlay is a no-op (the build
    carries no technique layer, never breaks) - the graceful-degradation contract meaning_upfold
    and identity_lens both keep."""
    (tmp_path / "collaborator_corpus" / "_structural").mkdir(parents=True)
    nodes: dict = {"": {"id": "", "grade": 1, "parent": None, "members": []}}
    assert technique_lens.technique_overlay(tmp_path, nodes, {}, {}) == []
    assert technique_lens.resolve(tmp_path, nodes, {}, {}) == []
