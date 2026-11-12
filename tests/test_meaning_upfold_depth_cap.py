"""Direct-leaf mass, depth-floor boundaries, and the read-only JSON consumer."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from laplace.engine import meaning_upfold as mu


@pytest.fixture
def tree():
    clusters = {f"c{i}": {"members": []} for i in range(1, 8)}
    parents = {f"c{i}": f"c{i-1}" if i > 1 else "root" for i in range(1, 8)}
    leaves = {"singleton": "hash"}
    parents["singleton"] = "root"
    for depth, n in ((2, 10), (3, 11), (6, 12), (7, 13)):
        cid = f"c{depth}"
        for i in range(n):
            leaf = f"leaf{depth}-{i}"
            leaves[leaf] = "hash"
            parents[leaf] = cid
            clusters[cid]["members"].append(leaf)
    return {"clusters": clusters, "parent_map": parents, "leaf_sha": leaves, "root_id": "root"}


def test_direct_mass_and_depth_boundaries(tree):
    before = copy.deepcopy(tree)
    assert mu.depth_cap_figure(tree) == {
        "schema_version": "laplace.depth-cap-figure/1",
        "dial_set_id": mu.dials.current("engine-fold")["dial_set_id"],
        "leaf_max": 10, "max_depth": 6, "clusters": 7,
        "corpus_members": 47, "cluster_direct_members": 46, "root_direct_members": 1,
        "declined_count": 0,
        "over_cap_clusters": 3, "over_cap_at_depth_floor": 2,
        "over_cap_beyond_depth_floor": 1, "over_cap_members": 36,
        "depth_floor_members": 25, "over_cap_corpus_fraction": 36 / 47,
        "depth_floor_corpus_fraction": 25 / 47,
    }
    assert tree == before


def test_empty_tree():
    result = mu.depth_cap_figure({"clusters": {}, "parent_map": {}, "leaf_sha": {}, "root_id": ""})
    assert result["corpus_members"] == result["over_cap_corpus_fraction"] == 0


@pytest.mark.parametrize("fault", ["cycle", "missing_parent", "duplicate", "wrong_parent", "unassigned"])
def test_invalid_tree_is_not_a_figure(tree, fault):
    if fault == "cycle":
        tree["parent_map"]["c1"] = "c7"
    elif fault == "missing_parent":
        del tree["parent_map"]["c4"]
    elif fault == "duplicate":
        tree["clusters"]["c3"]["members"] *= 2
    elif fault == "wrong_parent":
        tree["parent_map"]["leaf3-0"] = "c6"
    else:
        tree["leaf_sha"]["missing"] = "hash"
    with pytest.raises(ValueError, match="depth-cap-figure"):
        mu.depth_cap_figure(tree)


def test_cli_consumes_snapshot_without_writing(tmp_path, tree, capsys):
    path = tmp_path / mu.TREE_FILE
    raw = json.dumps(tree).encode()
    path.write_bytes(raw)
    stat = path.stat()
    assert mu._main(["--depth-cap-figure", "--repo-root", str(tmp_path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["over_cap_members"] == 36
    assert result["tree_sha256"] == hashlib.sha256(raw).hexdigest()
    assert path.read_bytes() == raw
    assert path.stat().st_mtime_ns == stat.st_mtime_ns
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("raw", [None, "{", "{}"])
def test_cli_refuses_missing_or_malformed_tree(tmp_path, capsys, raw):
    if raw is not None:
        (tmp_path / mu.TREE_FILE).write_text(raw)
    assert mu._main(["--depth-cap-figure", "--repo-root", str(tmp_path)]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "INVALID_TREE"


@pytest.fixture(autouse=True)
def _genesis_dials_for_fold_tests(tmp_path_factory, monkeypatch):
    from laplace.pipeline import dial_profiles as dials
    root = tmp_path_factory.mktemp("fold-dials")
    monkeypatch.setenv("LAPLACE_DIALS_ROOT", str(root))
    dials.pour_genesis(root)


@pytest.fixture
def sweep_tree(tmp_path, monkeypatch):
    import numpy as np
    from test_meaning_upfold_incremental import FakeBackend, _leaf
    from laplace.representation import embed_router
    backend = FakeBackend()
    monkeypatch.setattr(embed_router, "get_backend", lambda: backend)
    residue, clusters, parents = {}, {}, {}
    for cid, n in (("small", 12), ("largest", 30), ("middle", 20)):
        members = [f"{cid}/{i}" for i in range(n)]
        residue.update({m: _leaf("md", [cid], essence=m) for m in members})
        clusters[cid] = dict(members=members, label=cid, sealed=False, centroid=[1., 0.])
        parents[cid] = ""
        parents.update({m: cid for m in members})
    sha = {m: mu._text_sha(backend.name, mu._embeddable_text(tmp_path, m, leaf, embed_router.TEXT_CAP))
           for m, leaf in residue.items()}
    tree = dict(version=backend.name, clusters=clusters, parent_map=parents, leaf_sha=sha,
                root_id="", lens_hash="L0", lens_pairs=[])
    vectors = np.asarray([[1., i / 100.] for i in range(len(residue))])
    monkeypatch.setattr(mu, "_embed", lambda *args: vectors)
    return residue, tree


def test_sweep_largest_first_budget_and_unchanged_decline(tmp_path, monkeypatch, sweep_tree):
    from laplace.engine import residue as ledger
    import numpy as np
    residue, tree = sweep_tree
    mu.dials.set_value("engine-fold", "repair_sweep_per_deposit", "2", by="test", why="budget")
    calls = []
    def decline(block, level=1):
        calls.append(len(block))
        return 2, np.zeros(len(block), dtype=int)
    monkeypatch.setattr(mu, "_best_split", decline)
    mu.cluster_residue_incremental(tmp_path, residue, tree, lens_hash="L0")
    assert calls == [30, 20]
    first = mu.load_tree(tmp_path)
    assert first["parent_map"] == tree["parent_map"]
    rows = [r for r in ledger.read_rows(tmp_path) if r["kind"] == "overflow"]
    assert [r["ids"] for r in rows] == [["largest"], ["middle"]]
    assert all(r["detail"]["reason"] == "chosen_k_collapsed" for r in rows)
    assert mu.depth_cap_figure(first)["declined_count"] == 2
    mu.cluster_residue_incremental(tmp_path, residue, first, lens_hash="L0")
    assert calls == [30, 20, 12]  # unchanged declines survive persisted-tree reload
    assert len([r for r in ledger.read_rows(tmp_path) if r["kind"] == "overflow"]) == 3
    residue["largest/0"]["essence"] = "changed member content"
    mu.cluster_residue_incremental(tmp_path, residue, mu.load_tree(tmp_path), lens_hash="L0")
    assert calls == [30, 20, 12, 30]


def test_sweep_zero_budget_leaves_untouched_overflow(tmp_path, monkeypatch, sweep_tree):
    residue, tree = sweep_tree
    mu.dials.set_value("engine-fold", "repair_sweep_per_deposit", "0", by="test", why="disabled")
    monkeypatch.setattr(mu, "_best_split", lambda *a, **k: pytest.fail("zero budget attempted split"))
    mu.cluster_residue_incremental(tmp_path, residue, tree, lens_hash="L0")
    assert mu.load_tree(tmp_path) == tree


@pytest.mark.parametrize("reason", ["indistinguishable_members", "silhouette_refused"])
def test_cut_declines_are_typed_at_their_own_cluster(tmp_path, monkeypatch, sweep_tree, reason):
    import numpy as np
    from laplace.engine import residue as ledger
    residue, tree = sweep_tree
    if reason == "indistinguishable_members":
        monkeypatch.setattr(mu, "_embed", lambda *a: np.ones((len(residue), 2)))
        monkeypatch.setattr(mu, "_best_split", lambda *a, **k: pytest.fail("indistinguishable split"))
    else:
        monkeypatch.setattr(mu, "_best_split", lambda block, level=1: (1, np.zeros(len(block))))
    mu.cluster_residue_incremental(tmp_path, residue, tree, lens_hash="L0")
    rows = [r for r in ledger.read_rows(tmp_path) if r["kind"] == "overflow"]
    assert len(rows) == 3 and all(r["detail"]["reason"] == reason for r in rows)
    assert mu.depth_cap_figure(mu.load_tree(tmp_path))["declined_count"] == 3


def test_deposit_figure_lands_once_in_each_timing_row(tmp_path, monkeypatch, tree):
    import importlib.util
    spec = importlib.util.spec_from_file_location("sweep_reembed", Path(__file__).resolve().parents[1] / "scripts/reembed.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path = tmp_path / ".reembed_timing.jsonl"
    monkeypatch.setattr(module, "TIMING_LOG", path)
    expected = mu.depth_cap_figure(tree)
    module._bank_timing_record({"mode": "incremental", "phases": {"meaning_upfold": 0.5}}, tree)
    module._bank_timing_record({"mode": "incremental", "phases": {"meaning_upfold": 0.3}}, tree)
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(rows) == 2
    assert all(r["depth_cap_figure"] == expected for r in rows)
    assert {"clusters", "over_cap_clusters", "over_cap_members", "over_cap_at_depth_floor",
            "declined_count", "dial_set_id"} <= rows[0]["depth_cap_figure"].keys()
