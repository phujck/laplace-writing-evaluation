"""Tests for meaning_upfold's INCREMENTAL fold (his W4 steer: changed nodes re-embed, touched
lineages re-fold, a full spectral rebuild ONLY on a structural move).

Contracts: a bounded add attaches to the nearest concept centroid without re-splitting, and untouched
clusters stay byte-identical; the returned node-dict shape matches a full rebuild's; the full-rebuild
fallback fires on >20% churn, a version/backend mismatch and a lens-shape change - but NOT on either
half of trigger (d), where a LEAF_MAX breach is cured by a scoped re-split (2026-08-20) and an emptied
cluster is dropped in place (2026-08-21); the no-embedder degrade returns empty exactly as
cluster_residue does; and running the incremental fold twice on the same state yields an identical tree
(determinism).

A deterministic in-process FakeBackend (NOT the hash router, which cluster_residue rejects) stands in for
bge-small so the clustering is fixed and offline - the same monkeypatch-the-backend idiom the router tests
use, on the ``embed_router.get_backend`` entry both paths read at call time."""

from __future__ import annotations

import hashlib

import pytest

from laplace.representation import device_policy, embed_router
from laplace.engine import meaning_upfold


class FakeBackend:
    """Three orthogonal families (alpha/beta/gamma) -> three clean concept clusters. Deterministic:
    the same text always embeds to the same unit vector, so the fold is reproducible."""

    name = "fake:test-v1"
    FAMILIES = {"alpha": 0, "beta": 1, "gamma": 2}
    dim = 6

    def _vec(self, text: str) -> list[float]:
        base = [0.0] * self.dim
        fam = 0
        for k, idx in self.FAMILIES.items():
            if k in text:
                fam = idx
                base[idx] = 1.0
                break
        h = int(hashlib.sha1(text.encode("utf-8")).hexdigest(), 16)
        base[(fam + 3) % self.dim] += (h % 100) / 1000.0          # tiny deterministic intra-family jitter
        n = sum(x * x for x in base) ** 0.5
        return [x / n for x in base] if n else base

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def query(self, text: str) -> list[float]:
        return self._vec(text)


def _leaf(kind, keywords, sealed=False, essence="x"):
    return {"kind": kind, "essence": essence, "keywords": keywords, "sealed": sealed}


def _residue(sizes: dict[str, int]) -> dict[str, dict]:
    r: dict[str, dict] = {}
    for fam, n in sizes.items():
        for i in range(n):
            r[f"{fam}/{fam}_{i}.md"] = _leaf("md", [fam, f"{fam}{i}"], essence=fam)
    return r


def _members_by_cluster(parent_map: dict, cluster_nodes: dict) -> dict[str, set]:
    out: dict[str, set] = {cid: set() for cid in cluster_nodes}
    for nid, p in parent_map.items():
        if p in out:
            out[p].add(nid)
    return out


@pytest.fixture()
def backend(monkeypatch):
    fb = FakeBackend()
    monkeypatch.setattr(embed_router, "get_backend", lambda: fb)
    # LAPLACE_ALLOW_SPECTRAL is a no-op since his 2026-08-20 PSU-restrictions-scrubbed ruling (deps
    # alone now gate _spectral_allowed - see the spectral-gate tests below), kept set here only so
    # this fixture reads the same regardless of which contract era a test was written against; the
    # deny-path tests below explicitly set LAPLACE_NO_SPECTRAL to exercise the DENY path.
    monkeypatch.setenv("LAPLACE_ALLOW_SPECTRAL", "1")
    return fb


def _cold(repo, residue, lens_hash="L0"):
    """The cold path (prev None) = full rebuild; persists the tree, returns (pm, cn, loaded tree)."""
    pm, cn = meaning_upfold.cluster_residue_incremental(repo, residue, None, lens_hash=lens_hash)
    return pm, cn, meaning_upfold.load_tree(repo)


# --- the bounded add: nearest centroid, no re-split, untouched clusters byte-identical ---

def test_incremental_add_attaches_to_nearest_and_preserves_untouched(tmp_path, backend):
    residue = _residue({"alpha": 8, "beta": 8, "gamma": 8})
    _pm0, _cn0, tree0 = _cold(tmp_path, residue)
    before = {cid: set(c["members"]) for cid, c in tree0["clusters"].items()}

    residue["alpha/alpha_new.md"] = _leaf("md", ["alpha", "alphaNEW"], essence="alpha")
    pm, cn = meaning_upfold.cluster_residue_incremental(tmp_path, residue, tree0, lens_hash="L0")

    parent = pm["alpha/alpha_new.md"]
    assert parent in cn                                          # attached to a concept cluster, not root
    joined = _members_by_cluster(pm, cn)[parent]
    assert all(m.split("/")[0] == "alpha" for m in joined)       # nearest centroid = the alpha family

    after = _members_by_cluster(pm, cn)
    for cid, mem in before.items():
        if cid == parent:
            continue
        assert after[cid] == mem                                 # every untouched cluster: membership unchanged


def test_incremental_node_dict_shape_matches_full(tmp_path, backend):
    residue = _residue({"alpha": 8, "beta": 8, "gamma": 8})
    _pm0, _cn0, tree0 = _cold(tmp_path, residue)
    residue["alpha/alpha_new.md"] = _leaf("md", ["alpha", "alphaNEW"], essence="alpha")

    _pm_i, cn_i = meaning_upfold.cluster_residue_incremental(tmp_path, residue, tree0, lens_hash="L0")
    _pm_f, cn_f = meaning_upfold.cluster_residue(tmp_path, residue)      # a fresh full rebuild, same residue

    keyset = {"kind", "essence", "keywords", "sealed", "leaf"}
    for node in cn_i.values():
        assert set(node) == keyset and node["kind"] == "concept" and node["leaf"] is True
        assert node["keywords"] == node["essence"].split()
    # the full rebuild's concept nodes carry the identical dict shape
    assert all(set(n) == keyset for n in cn_f.values())


# --- the full-rebuild triggers ---

def test_churn_over_fraction_forces_full(tmp_path, backend, monkeypatch):
    residue = _residue({"alpha": 8, "beta": 8, "gamma": 8})
    _pm0, _cn0, tree0 = _cold(tmp_path, residue)

    calls = {"n": 0}
    real = meaning_upfold.cluster_residue

    def spy(*a, **k):
        calls["n"] += 1
        return real(*a, **k)

    monkeypatch.setattr(meaning_upfold, "cluster_residue", spy)
    # change 6 of 24 leaves = 25% > 20%
    for i in range(6):
        residue[f"alpha/alpha_{i}.md"] = _leaf("md", ["alpha", f"CH{i}"], essence="alpha")
    meaning_upfold.cluster_residue_incremental(tmp_path, residue, tree0, lens_hash="L0")
    assert calls["n"] == 1                                       # the spectral full path fired


def test_version_mismatch_forces_full(tmp_path, backend, monkeypatch):
    residue = _residue({"alpha": 8, "beta": 8, "gamma": 8})
    _pm0, _cn0, tree0 = _cold(tmp_path, residue)
    tree0["version"] = "fake:some-other-model"                   # backend the tree was built under differs

    calls = {"n": 0}
    real = meaning_upfold.cluster_residue
    monkeypatch.setattr(meaning_upfold, "cluster_residue",
                        lambda *a, **k: (calls.__setitem__("n", calls["n"] + 1) or real(*a, **k)))
    meaning_upfold.cluster_residue_incremental(tmp_path, residue, tree0, lens_hash="L0")
    assert calls["n"] == 1


def test_lens_shape_change_forces_full(tmp_path, backend, monkeypatch):
    residue = _residue({"alpha": 8, "beta": 8, "gamma": 8})
    _pm0, _cn0, tree0 = _cold(tmp_path, residue, lens_hash="L0")

    calls = {"n": 0}
    real = meaning_upfold.cluster_residue
    monkeypatch.setattr(meaning_upfold, "cluster_residue",
                        lambda *a, **k: (calls.__setitem__("n", calls["n"] + 1) or real(*a, **k)))
    # same residue, but the caller signals a different lens membership shape
    meaning_upfold.cluster_residue_incremental(tmp_path, residue, tree0, lens_hash="L1")
    assert calls["n"] == 1


def test_lens_drift_within_fraction_proceeds_incrementally(tmp_path, backend, monkeypatch):
    # the first in-anger close's finding: a close mints a lens-claimed handoff file -> a few new
    # pairs; that is metabolism, not a structural move, and must NOT force the spectral full path.
    residue = _residue({"alpha": 8, "beta": 8, "gamma": 8})
    pairs0 = [f"lens/{i}\x00aspect" for i in range(100)]
    pm0, cn0 = meaning_upfold.cluster_residue_incremental(
        tmp_path, residue, None, lens_hash="L0", lens_pairs=pairs0)
    tree0 = meaning_upfold.load_tree(tmp_path)
    assert tree0["lens_pairs"] == pairs0                          # the pairs bank with the tree

    calls = {"n": 0}
    real = meaning_upfold.cluster_residue
    monkeypatch.setattr(meaning_upfold, "cluster_residue",
                        lambda *a, **k: (calls.__setitem__("n", calls["n"] + 1) or real(*a, **k)))
    pairs1 = pairs0 + ["lens/handoff-new\x00aspect"]              # 1% drift << 20%
    pm1, cn1 = meaning_upfold.cluster_residue_incremental(
        tmp_path, residue, tree0, lens_hash="L1", lens_pairs=pairs1)
    assert calls["n"] == 0                                        # NO spectral full rebuild
    assert cn1                                                    # the incremental tree returned
    assert meaning_upfold.load_tree(tmp_path)["lens_pairs"] == pairs1   # drifted pairs re-banked


def test_lens_reshuffle_over_fraction_forces_full(tmp_path, backend, monkeypatch):
    residue = _residue({"alpha": 8, "beta": 8, "gamma": 8})
    pairs0 = [f"lens/{i}\x00aspect" for i in range(100)]
    meaning_upfold.cluster_residue_incremental(
        tmp_path, residue, None, lens_hash="L0", lens_pairs=pairs0)
    tree0 = meaning_upfold.load_tree(tmp_path)

    calls = {"n": 0}
    real = meaning_upfold.cluster_residue
    monkeypatch.setattr(meaning_upfold, "cluster_residue",
                        lambda *a, **k: (calls.__setitem__("n", calls["n"] + 1) or real(*a, **k)))
    pairs1 = [f"lens/{i}\x00OTHER" for i in range(100)]           # 200% symmetric difference
    meaning_upfold.cluster_residue_incremental(
        tmp_path, residue, tree0, lens_hash="L1", lens_pairs=pairs1)
    assert calls["n"] == 1                                        # a genuine reshuffle -> spectral full path


def _breach_setup(tmp_path, monkeypatch):
    """A 10-member leaf cluster (== LEAF_MAX) plus one more leaf: the (d2) breach, with churn well
    under the 20% fraction so nothing ELSE could be the trigger. Returns
    ``(residue, tree0, before, calls)`` where ``calls`` counts full rebuilds."""
    residue = _residue({"alpha": 10, "beta": 10, "gamma": 4})
    _pm0, _cn0, tree0 = _cold(tmp_path, residue)
    before = {cid: set(c["members"]) for cid, c in tree0["clusters"].items()}
    calls = {"n": 0}
    real = meaning_upfold.cluster_residue
    monkeypatch.setattr(meaning_upfold, "cluster_residue",
                        lambda *a, **k: (calls.__setitem__("n", calls["n"] + 1) or real(*a, **k)))
    residue["alpha/alpha_extra.md"] = _leaf("md", ["alpha", "extra"], essence="alpha")
    assert (1 / len(residue)) < 0.20                            # churn alone would NOT trigger
    return residue, tree0, before, calls


def test_cluster_breach_is_cured_in_scope_not_by_a_global_rebuild(tmp_path, backend, monkeypatch):
    """THE CONTRACT INVERTED, 2026-08-20 (this test previously asserted ``calls["n"] == 1``).

    Trigger (d2) used to demand a full spectral rebuild of the WHOLE residue because one cluster
    had accreted past LEAF_MAX. That was a global sledgehammer for a local overflow - and worse, one
    that cannot fix it: the overflow that actually fires this trigger comes from the MAX_DEPTH cap,
    which a full rebuild reproduces exactly. The cure now runs where the defect is."""
    residue, tree0, _before, calls = _breach_setup(tmp_path, monkeypatch)
    pm, cn = meaning_upfold.cluster_residue_incremental(tmp_path, residue, tree0, lens_hash="L0")
    assert calls["n"] == 0                                       # NO global rebuild
    tree = meaning_upfold.load_tree(tmp_path)
    # the overflow is gone: every cluster's DIRECT leaf members are back within the bound
    assert all(len(c["members"]) <= meaning_upfold.dials.value("engine-fold", "leaf_max") for c in tree["clusters"].values())
    # ...and the new leaf is still placed in a concept cluster, not dropped to the root
    assert pm["alpha/alpha_extra.md"] in cn


def test_scoped_resplit_preserves_the_leaf_partition_and_the_mass(tmp_path, backend, monkeypatch):
    """Tree validity after the re-split: every residue leaf has exactly one parent, every cluster
    parent resolves, and no leaf is duplicated or lost."""
    residue, tree0, _before, _calls = _breach_setup(tmp_path, monkeypatch)
    pm, cn = meaning_upfold.cluster_residue_incremental(tmp_path, residue, tree0, lens_hash="L0")
    tree = meaning_upfold.load_tree(tmp_path)
    clusters, parent_map = tree["clusters"], tree["parent_map"]

    leaves = [nid for nid in parent_map if nid in residue]
    assert set(leaves) == set(residue)                            # partition: every leaf, once
    assert len(leaves) == len(residue)
    banked = [m for c in clusters.values() for m in c["members"]]
    assert len(banked) == len(set(banked))                        # no leaf banked twice
    assert set(banked) <= set(residue)
    # mass conserved: banked direct members + leaves parked at the root == the whole residue
    at_root = [nid for nid in leaves if parent_map[nid] not in clusters]
    assert len(banked) + len(at_root) == len(residue)
    # every cluster's parent resolves to another cluster or to the root
    for cid in clusters:
        assert parent_map[cid] in clusters or parent_map[cid] == tree.get("root_id", "")
    # and the returned pair still agrees with itself
    assert set(cn) == set(clusters)
    assert all(pm[nid] == parent_map[nid] for nid in leaves)


def test_scoped_resplit_churn_is_scoped(tmp_path, backend, monkeypatch):
    """The whole point of scoping: clusters outside the re-split subtree keep their ids AND their
    membership, byte for byte. Only the overflowed cluster's own subtree mints new ids."""
    residue, tree0, before, _calls = _breach_setup(tmp_path, monkeypatch)
    meaning_upfold.cluster_residue_incremental(tmp_path, residue, tree0, lens_hash="L0")
    tree = meaning_upfold.load_tree(tmp_path)
    after = {cid: set(c["members"]) for cid, c in tree["clusters"].items()}

    minted = set(after) - set(before)
    assert minted                                                 # the re-split DID mint children
    survived = set(before) & set(after)
    assert survived == set(before)                                # nothing outside was destroyed
    # the resplit cluster is the one whose membership moved; every OTHER survivor is untouched
    moved = {cid for cid in survived if after[cid] != before[cid]}
    assert len(moved) == 1, f"churn escaped its scope: {moved}"
    resplit = moved.pop()
    assert all(tree["parent_map"][m] == resplit for m in minted)  # minted ids hang off it


def test_scoped_resplit_tree_still_descends(tmp_path, backend, monkeypatch):
    """A tree that no reader can descend is not a tree. The re-split subtree must open and answer."""
    import json

    from laplace.engine import recursive_read
    residue, tree0, _before, _calls = _breach_setup(tmp_path, monkeypatch)
    meaning_upfold.cluster_residue_incremental(tmp_path, residue, tree0, lens_hash="L0")
    # the read path recomputes leaf text from the banked shard, so give it one
    (tmp_path / ".self_graded.json").write_text(json.dumps(residue), encoding="utf-8")
    dsc = recursive_read.open_descender(tmp_path, backend=backend, allow_test_backend=True)
    hit = dsc.descend("alpha")
    assert hit["hits"], "the descent returned nothing over the re-split tree"
    assert any(str(h["id"]).startswith("alpha/") for h in hit["hits"])
    assert hit["n_visited_clusters"] >= 1
    # the descent must be able to walk INTO the re-split subtree, not merely around it
    assert all(isinstance(h["path"], list) for h in hit["hits"])


def test_scoped_resplit_is_deterministic(tmp_path, backend, monkeypatch):
    """Same breach, same tree, twice - the re-split must mint the same ids (they are membership
    derived, so this is the property that keeps the embedding cache from churning)."""
    residue, tree0, _before, _calls = _breach_setup(tmp_path, monkeypatch)
    pm1, cn1 = meaning_upfold.cluster_residue_incremental(tmp_path, residue, dict(tree0), lens_hash="L0")
    pm2, cn2 = meaning_upfold.cluster_residue_incremental(tmp_path, residue, dict(tree0), lens_hash="L0")
    assert set(cn1) == set(cn2)
    assert pm1 == pm2


def test_depth_capped_overflow_declines_loudly_instead_of_rebuilding(tmp_path, backend, monkeypatch,
                                                                     capsys):
    """A cluster already at MAX_DEPTH has nowhere to put its overflow. The old code paid for a full
    rebuild that would land in the same place; the new code says so and declines - which is what
    makes the depth cap visible as the real defect rather than hiding it behind a 400-second no-op."""
    residue, tree0, _before, calls = _breach_setup(tmp_path, monkeypatch)
    meaning_upfold.dials.set_value("engine-fold", "max_depth", "0", by="test", why="depth cap fixture")          # every cluster is 'at the cap'
    meaning_upfold.cluster_residue_incremental(tmp_path, residue, tree0, lens_hash="L0")
    out = capsys.readouterr().out
    assert calls["n"] == 0                                        # still no global rebuild
    assert "scoped re-split DECLINED" in out
    assert "MAX_DEPTH" in out and "overflow STANDS" in out


def _emptied_setup(tmp_path, monkeypatch):
    """A whole small cluster removed (4 of 24 = 16.7% < 20%), so (d1) fires and the churn trigger
    does not. Returns (residue, tree0, before, calls) with cluster_residue counted."""
    residue = _residue({"alpha": 10, "beta": 10, "gamma": 4})
    _pm0, _cn0, tree0 = _cold(tmp_path, residue)
    before = {cid: dict(c) for cid, c in tree0["clusters"].items()}
    calls = {"n": 0}
    real = meaning_upfold.cluster_residue
    monkeypatch.setattr(meaning_upfold, "cluster_residue",
                        lambda *a, **k: (calls.__setitem__("n", calls["n"] + 1) or real(*a, **k)))
    for i in range(4):
        residue.pop(f"gamma/gamma_{i}.md")
    assert (4 / (len(residue) + 4)) < 0.20                       # not the churn trigger
    return residue, tree0, before, calls


def test_cluster_empty_is_dropped_in_place_not_by_a_global_rebuild(tmp_path, backend, monkeypatch,
                                                                   capsys):
    """THE CONTRACT INVERTED, 2026-08-21 (this test previously asserted ``calls["n"] == 1``).

    (d1) demanded a full spectral rebuild because one cluster lost its last leaf - the same category
    error (d2) carried until 2026-08-20, and with the same amplification: the re-partition re-mints
    cluster ids, and those ids rode every descendant's embedded text. The emptied cluster now leaves
    the tree where it stands."""
    residue, tree0, _before, calls = _emptied_setup(tmp_path, monkeypatch)
    pm, cn = meaning_upfold.cluster_residue_incremental(tmp_path, residue, tree0, lens_hash="L0")
    assert calls["n"] == 0                                       # NO global rebuild
    assert "dropped in place" in capsys.readouterr().out
    tree = meaning_upfold.load_tree(tmp_path)
    # no member-less, childless cluster survives, in the return OR on disk
    parents = set(tree["parent_map"].values())
    assert not [cid for cid, c in tree["clusters"].items()
                if not c["members"] and cid not in parents]
    assert set(cn) == set(tree["clusters"])                      # the return matches what persisted
    # every surviving leaf still resolves to a cluster that exists
    assert all(pm[nm] in cn for nm in residue)
    assert not (set(pm.values()) - set(cn) - {""})               # no parent points at a dropped id


def test_emptied_cluster_drop_leaves_the_rest_of_the_tree_identical(tmp_path, backend, monkeypatch):
    """The churn is bounded to the hole: every cluster that did not lose a member keeps its id, its
    members and its label byte-for-byte - which is the whole point of not re-partitioning."""
    residue, tree0, before, _calls = _emptied_setup(tmp_path, monkeypatch)
    meaning_upfold.cluster_residue_incremental(tmp_path, residue, tree0, lens_hash="L0")
    tree = meaning_upfold.load_tree(tmp_path)
    gone = set(before) - set(tree["clusters"])
    assert gone                                                  # the emptied cluster(s) left
    for cid, c in tree["clusters"].items():
        assert before[cid]["members"] == c["members"]
        assert before[cid]["label"] == c["label"]


# --- degrade + determinism ---

def test_no_embedder_degrades_like_cluster_residue(tmp_path, monkeypatch):
    monkeypatch.setattr(embed_router, "get_backend", lambda: None)
    residue = _residue({"alpha": 8, "beta": 8, "gamma": 8})
    inc = meaning_upfold.cluster_residue_incremental(tmp_path, residue, None, lens_hash="L0")
    full = meaning_upfold.cluster_residue(tmp_path, residue)
    assert inc == ({}, {}) == full                              # same empty degrade
    assert not (tmp_path / meaning_upfold.TREE_FILE).exists()   # nothing persisted on the degrade path


# --- the loud-failure fix (2026-07-28), owed since the 07-24 silent-degrade regression ---

@pytest.mark.parametrize("setup,needle", [
    (lambda mp: mp.setattr(embed_router, "get_backend", lambda: None),
     "no embedding backend"),
    (lambda mp: mp.setattr(embed_router, "get_backend", lambda: embed_router.HashBackend()),
     "hash backend carries no semantics"),
    (lambda mp: mp.setenv("LAPLACE_MAX_UPFOLD_N", "3"),
     "over the LAPLACE_MAX_UPFOLD_N cap"),
])
def test_degrade_to_empty_names_itself(tmp_path, monkeypatch, capsys, setup, needle):
    """The 07-24 regression was a SILENT ``return {}, {}``: three deposits shipped with zero concept
    nodes and nothing printed. Behaviour is unchanged (still empty, still graceful, the build never
    breaks) - but each degrade now says which unavailability caused it, on both entries."""
    setup(monkeypatch)
    residue = _residue({"alpha": 8, "beta": 8, "gamma": 8})
    assert meaning_upfold.cluster_residue(tmp_path, residue) == ({}, {})
    assert meaning_upfold.cluster_residue_incremental(
        tmp_path, residue, None, lens_hash="L0") == ({}, {})
    out = capsys.readouterr().out
    assert out.count("DEGRADED to the folder middle") == 2, out
    assert needle in out


def test_too_small_residue_degrade_names_itself(tmp_path, backend, capsys):
    residue = _residue({"alpha": 3})                            # under 2 * LEAF_MAX
    assert meaning_upfold.cluster_residue(tmp_path, residue) == ({}, {})
    out = capsys.readouterr().out
    assert "DEGRADED to the folder middle" in out and "under the 20 needed to split" in out


def test_incremental_is_deterministic(tmp_path, backend):
    residue = _residue({"alpha": 8, "beta": 8, "gamma": 8})
    _pm0, _cn0, tree0 = _cold(tmp_path, residue)
    residue["alpha/alpha_new.md"] = _leaf("md", ["alpha", "alphaNEW"], essence="alpha")

    r1 = meaning_upfold.cluster_residue_incremental(tmp_path, residue, tree0, lens_hash="L0")
    b1 = (tmp_path / meaning_upfold.TREE_FILE).read_text(encoding="utf-8")
    # same state (the SAME prev tree0, unmutated) -> identical output + identical persisted tree
    r2 = meaning_upfold.cluster_residue_incremental(tmp_path, residue, tree0, lens_hash="L0")
    b2 = (tmp_path / meaning_upfold.TREE_FILE).read_text(encoding="utf-8")
    assert r1 == r2
    assert b1 == b2


# --- Gate C: content-derived (stable, opaque) cluster ids (his root fix, 2026-07-13) ---

def test_full_rebuild_ids_are_content_derived_and_deterministic(tmp_path, backend):
    """Two independent full rebuilds of the SAME residue mint IDENTICAL cluster ids - the id is a
    sha1 over the founding membership, not an ordinal label re-minted per spectral run. Every id is
    an opaque hex handle; the human-readable text lives only in essence/keywords."""
    residue = _residue({"alpha": 8, "beta": 8, "gamma": 8})
    _pm1, cn1 = meaning_upfold.cluster_residue(tmp_path, residue)
    other = tmp_path / "second"
    other.mkdir()
    _pm2, cn2 = meaning_upfold.cluster_residue(other, residue)

    assert set(cn1) == set(cn2), "same membership -> identical cluster ids across independent rebuilds"
    assert cn1, "the fixture splits into concept clusters"

    # each id IS the content hash of its own founding membership (opaque, no ordinal structure)
    members_by_cid = _members_by_cluster(_pm1, cn1)
    for cid, members in members_by_cid.items():
        assert cid.startswith("concept::")
        suffix = cid[len("concept::"):]
        assert len(suffix) == 10 and all(c in "0123456789abcdef" for c in suffix), "opaque hex id"
        # a leaf-bearing (direct-member) cluster's id hashes its direct members (top-level parent="")
        # -> we can't recompute nested parents here, but the top clusters are reproducible:
    # determinism is the load-bearing claim: identical inputs -> identical id SET (already asserted)


def test_incremental_preserves_surviving_cluster_ids(tmp_path, backend):
    """A surviving cluster KEEPS its founding id as a member accretes (id = founding membership; only a
    genuine re-split mints new). +1 leaf on the incremental path leaves every prior cluster id intact."""
    residue = _residue({"alpha": 8, "beta": 8, "gamma": 8})
    _pm0, cn0, tree0 = _cold(tmp_path, residue)
    ids_before = set(cn0)

    residue["alpha/alpha_new.md"] = _leaf("md", ["alpha", "alphaNEW"], essence="alpha")
    _pm, cn = meaning_upfold.cluster_residue_incremental(tmp_path, residue, tree0, lens_hash="L0")

    assert set(cn) == ids_before, "the accreted cluster kept its id; no id churn on a bounded add"


# --- the spectral gate: deps-only now (his 2026-08-20 PSU-restrictions-scrubbed ruling: local is a
# full compute home), the full spectral rebuild is gated on deps alone, the incremental fold never is ---

def test_spectral_allowed_true_with_deps_and_no_env_at_all(monkeypatch):
    """_spectral_allowed is deps-only: with scikit-learn + scipy importable (present in this env) it
    is True even with BOTH legacy env signals absent - the 2026-07-13 LAPLACE_ALLOW_SPECTRAL /
    CLAUDE_CODE_REMOTE opt-in requirement is retired, not merely relaxed. The legacy vars are now
    inert no-ops rather than switches."""
    monkeypatch.delenv("LAPLACE_ALLOW_SPECTRAL", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
    monkeypatch.delenv("LAPLACE_NO_SPECTRAL", raising=False)
    assert meaning_upfold._spectral_allowed() is True
    monkeypatch.setenv("LAPLACE_ALLOW_SPECTRAL", "1")          # legacy var: no longer load-bearing
    assert meaning_upfold._spectral_allowed() is True
    monkeypatch.delenv("LAPLACE_ALLOW_SPECTRAL", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")           # legacy var: no longer load-bearing
    assert meaning_upfold._spectral_allowed() is True


def test_spectral_allowed_explicit_deny_override(monkeypatch):
    """LAPLACE_NO_SPECTRAL is the one remaining trivial opt-out, independent of the legacy vars."""
    monkeypatch.delenv("LAPLACE_ALLOW_SPECTRAL", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
    monkeypatch.setenv("LAPLACE_NO_SPECTRAL", "1")
    assert meaning_upfold._spectral_allowed() is False


def _fallback_rows(monkeypatch, tmp_path):
    """Point the recorder at a private file and hand back a reader for it."""
    import json
    from laplace.representation import device_policy
    log = tmp_path / "fb.jsonl"
    monkeypatch.setenv(device_policy.LOG_OVERRIDE, str(log))
    monkeypatch.delenv(device_policy.REQUIRE_FLAG, raising=False)
    return lambda: [json.loads(x) for x in log.read_text().splitlines() if x.strip()] \
        if log.is_file() else []


def test_explicit_no_spectral_leaves_a_dialed_row(tmp_path, monkeypatch, capsys):
    """CENSUS C3: the deps-missing branch has recorded since his 2026-08-21 ruling, but the
    EXPLICIT opt-out returned in silence - the one landing an operator actually CHOSE was the one
    the store could not see. It is a row now, and ``dialed`` so it neither prints nor refuses."""
    rows = _fallback_rows(monkeypatch, tmp_path)
    monkeypatch.setenv("LAPLACE_NO_SPECTRAL", "1")
    assert meaning_upfold._spectral_allowed() is False
    r = rows()
    assert len(r) == 1 and r[0]["organ"] == "spectral-clustering"
    assert r[0]["dialed"] is True and "LAPLACE_NO_SPECTRAL" in r[0]["why"]
    assert "FALLBACK" not in capsys.readouterr().out      # dialed is lawful, and quiet


def test_fold_backend_marks_the_explicit_deny_as_dialed(tmp_path, monkeypatch):
    """CENSUS C1: ``_fold_backend`` passed no ``dialed`` at all, so LAPLACE_NO_SPECTRAL_GPU - an
    operator's explicit choice - was recorded as a degrade (two such rows in the store,
    2026-08-21T05:19:10). Under LAPLACE_REQUIRE_GPU that mis-marking makes the deny lever
    unusable on the very box the require flag exists for, so it is pinned here."""
    rows = _fallback_rows(monkeypatch, tmp_path)
    from laplace.representation import spectral_gpu
    monkeypatch.setenv(spectral_gpu.DENY_FLAG, "1")
    monkeypatch.setattr(meaning_upfold, "_gpu_fold", {})   # the verdict is memoised per process
    backend, why = meaning_upfold._fold_backend()
    assert backend == "cpu" and spectral_gpu.DENY_FLAG in why
    r = rows()
    assert len(r) == 1 and r[0]["organ"] == "fold-spectral" and r[0]["dialed"] is True

    # ...and the require flag now honours it rather than refusing a dialed choice
    monkeypatch.setenv("LAPLACE_REQUIRE_GPU", "1")
    monkeypatch.setattr(meaning_upfold, "_gpu_fold", {})
    assert meaning_upfold._fold_backend()[0] == "cpu"      # no DeviceRequired: it was asked for


def test_mid_fold_device_failure_leaves_a_typed_row(tmp_path, monkeypatch):
    """CENSUS C2: the WORST fallback the fold can take - the device was present, was chosen, and
    died with the rebuild already running - leaves its row and refuses under GPU-required law,
    without changing the backend verdict for every later cluster."""
    rows = _fallback_rows(monkeypatch, tmp_path)
    monkeypatch.setattr(meaning_upfold, "_gpu_fold", {"choice": ("gpu", ""), "announced": True})
    monkeypatch.setattr(meaning_upfold, "_fold_backend", lambda: ("gpu", ""))

    def _explode(_X, level=1):
        raise RuntimeError("cudaErrorLaunchFailure")
    monkeypatch.setattr(meaning_upfold, "_best_split_gpu", _explode)
    monkeypatch.setattr(meaning_upfold, "_best_split_dense",
                        lambda *a, **k: pytest.fail("GPU-required fold ran a CPU split"))
    monkeypatch.setenv("LAPLACE_FOLD_GPU_MIN_N", "1")
    monkeypatch.setenv("LAPLACE_REQUIRE_GPU", "1")

    with pytest.raises(device_policy.DeviceRequired, match="LAPLACE_REQUIRE_GPU"):
        meaning_upfold._best_split([[1.0, 0.0], [0.0, 1.0]])
    r = rows()
    assert len(r) == 1 and r[0]["organ"] == "fold-spectral" and r[0]["dialed"] is False
    assert "cudaErrorLaunchFailure" in r[0]["why"]
    assert meaning_upfold._gpu_fold["choice"] == ("gpu", "")


def test_spectral_allowed_false_when_analysis_deps_missing(monkeypatch):
    """Missing analysis deps still deny the spectral branch regardless of env (his ruling: "missing
    analysis deps only block the spectral branch, not the whole deposit")."""
    import builtins
    monkeypatch.delenv("LAPLACE_NO_SPECTRAL", raising=False)
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name in ("scipy", "sklearn"):
            raise ImportError(f"simulated missing {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert meaning_upfold._spectral_allowed() is False


def test_guard_denies_spectral_and_keeps_prior_tree(tmp_path, backend, monkeypatch, capsys):
    """A structural move DEMANDS a full rebuild, but spectral is denied (allow_spectral=False): the
    spectral cluster_residue is NOT called, the prior concept tree is returned stale-but-present, and
    the skip is named out loud."""
    residue = _residue({"alpha": 8, "beta": 8, "gamma": 8})
    _pm0, cn0, tree0 = _cold(tmp_path, residue)          # built WITH spectral (fixture grants it)
    prior_pm, prior_cn = meaning_upfold._tree_return(tree0)

    calls = {"n": 0}
    real = meaning_upfold.cluster_residue
    monkeypatch.setattr(meaning_upfold, "cluster_residue",
                        lambda *a, **k: (calls.__setitem__("n", calls["n"] + 1) or real(*a, **k)))
    # 25% churn would force a full rebuild - but deny it
    for i in range(6):
        residue[f"alpha/alpha_{i}.md"] = _leaf("md", ["alpha", f"CH{i}"], essence="alpha")
    pm, cn = meaning_upfold.cluster_residue_incremental(
        tmp_path, residue, tree0, lens_hash="L0", allow_spectral=False)

    assert calls["n"] == 0, "spectral rebuild must NOT run when denied"
    assert (pm, cn) == (prior_pm, prior_cn), "the prior tree is kept in place (stale but present)"
    out = capsys.readouterr().out
    assert "Full spectral rebuild skipped" in out and "keeping the prior concept tree" in out


def test_guard_allows_spectral_when_permitted(tmp_path, backend, monkeypatch):
    """The same structural trigger with allow_spectral=True runs the full spectral rebuild."""
    residue = _residue({"alpha": 8, "beta": 8, "gamma": 8})
    _pm0, _cn0, tree0 = _cold(tmp_path, residue)
    calls = {"n": 0}
    real = meaning_upfold.cluster_residue
    monkeypatch.setattr(meaning_upfold, "cluster_residue",
                        lambda *a, **k: (calls.__setitem__("n", calls["n"] + 1) or real(*a, **k)))
    for i in range(6):
        residue[f"alpha/alpha_{i}.md"] = _leaf("md", ["alpha", f"CH{i}"], essence="alpha")
    meaning_upfold.cluster_residue_incremental(
        tmp_path, residue, tree0, lens_hash="L0", allow_spectral=True)
    assert calls["n"] == 1


def test_guard_bounded_delta_runs_incremental_even_when_denied(tmp_path, backend, monkeypatch):
    """A bounded delta never demands spectral, so the incremental fold runs and completes even with
    spectral denied - the deposit is NOT gated, only the full-rebuild branch is."""
    residue = _residue({"alpha": 8, "beta": 8, "gamma": 8})
    _pm0, _cn0, tree0 = _cold(tmp_path, residue)
    calls = {"n": 0}
    real = meaning_upfold.cluster_residue
    monkeypatch.setattr(meaning_upfold, "cluster_residue",
                        lambda *a, **k: (calls.__setitem__("n", calls["n"] + 1) or real(*a, **k)))
    residue["alpha/alpha_new.md"] = _leaf("md", ["alpha", "alphaNEW"], essence="alpha")
    pm, cn = meaning_upfold.cluster_residue_incremental(
        tmp_path, residue, tree0, lens_hash="L0", allow_spectral=False)
    assert calls["n"] == 0, "no full rebuild for a bounded add"
    assert pm["alpha/alpha_new.md"] in cn, "the new leaf was folded incrementally"


def test_guard_env_none_allows_when_deps_present_and_no_deny(tmp_path, backend, monkeypatch):
    """allow_spectral=None (the default, build_self's call) resolves through _spectral_allowed: with
    both legacy env signals absent and no explicit deny, a demanded full rebuild now RUNS - local is
    a full compute home (his 2026-08-20 PSU-restrictions-scrubbed ruling), not a thing that needs
    opting into. This replaces the pre-2026-08-20 contract, where the same setup DENIED the rebuild."""
    monkeypatch.delenv("LAPLACE_ALLOW_SPECTRAL", raising=False)   # fixture set it; clear for this test
    monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
    monkeypatch.delenv("LAPLACE_NO_SPECTRAL", raising=False)
    residue = _residue({"alpha": 8, "beta": 8, "gamma": 8})
    _pm0, cn0 = meaning_upfold.cluster_residue_incremental(
        tmp_path, residue, None, lens_hash="L0", allow_spectral=True)
    tree0 = meaning_upfold.load_tree(tmp_path)

    calls = {"n": 0}
    real = meaning_upfold.cluster_residue
    monkeypatch.setattr(meaning_upfold, "cluster_residue",
                        lambda *a, **k: (calls.__setitem__("n", calls["n"] + 1) or real(*a, **k)))
    for i in range(6):
        residue[f"alpha/alpha_{i}.md"] = _leaf("md", ["alpha", f"CH{i}"], essence="alpha")
    pm, cn = meaning_upfold.cluster_residue_incremental(tmp_path, residue, tree0, lens_hash="L0")  # allow_spectral=None
    assert calls["n"] == 1, "spectral now runs by default with deps present and no explicit deny"
    assert pm["alpha/alpha_0.md"] in cn


def test_guard_env_none_denies_when_explicitly_denied(tmp_path, backend, monkeypatch):
    """allow_spectral=None with LAPLACE_NO_SPECTRAL set still denies and keeps the prior tree - the
    one remaining opt-out, independent of the (now inert) legacy env vars."""
    monkeypatch.delenv("LAPLACE_ALLOW_SPECTRAL", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
    monkeypatch.delenv("LAPLACE_NO_SPECTRAL", raising=False)
    residue = _residue({"alpha": 8, "beta": 8, "gamma": 8})
    _pm0, cn0 = meaning_upfold.cluster_residue_incremental(
        tmp_path, residue, None, lens_hash="L0", allow_spectral=True)
    tree0 = meaning_upfold.load_tree(tmp_path)
    prior = meaning_upfold._tree_return(tree0)

    monkeypatch.setenv("LAPLACE_NO_SPECTRAL", "1")
    calls = {"n": 0}
    real = meaning_upfold.cluster_residue
    monkeypatch.setattr(meaning_upfold, "cluster_residue",
                        lambda *a, **k: (calls.__setitem__("n", calls["n"] + 1) or real(*a, **k)))
    for i in range(6):
        residue[f"alpha/alpha_{i}.md"] = _leaf("md", ["alpha", f"CH{i}"], essence="alpha")
    pm, cn = meaning_upfold.cluster_residue_incremental(tmp_path, residue, tree0, lens_hash="L0")  # allow_spectral=None
    assert calls["n"] == 0
    assert (pm, cn) == prior


# ---------------------------------------------------------------------------
# the k-means thread cap (2026-08-20) - a TIME cure that must move no number
# ---------------------------------------------------------------------------

def test_blas_cap_limits_the_pools_and_restores_them():
    """``_blas_cap`` caps every BLAS/OpenMP pool to 6 inside the block and restores on exit.

    The measurement it encodes: the top split's k-means sweep (n=14,476, k=2..8) cost 8.683 s at
    the box's default 16 threads and 0.551 s at 6, with bit-identical partitions and silhouettes -
    the slowdown was synchronisation, not arithmetic."""
    threadpoolctl = pytest.importorskip("threadpoolctl")
    outside = [i["num_threads"] for i in threadpoolctl.threadpool_info()]
    if not outside:
        pytest.skip("no BLAS/OpenMP pool visible to threadpoolctl in this environment")
    with meaning_upfold._blas_cap():
        inside = [i["num_threads"] for i in threadpoolctl.threadpool_info()]
    assert inside and max(inside) <= meaning_upfold.dials.value("engine-fold", "kmeans_blas_threads")
    assert [i["num_threads"] for i in threadpoolctl.threadpool_info()] == outside


def test_the_spectral_sweep_runs_under_the_cap():
    """The cap is on the SWEEP, not merely defined beside it - the production split enters it."""
    entered = {"n": 0}
    real = meaning_upfold._blas_cap

    class _Recorder:
        def __enter__(self):
            entered["n"] += 1
            self._inner = real()
            return self._inner.__enter__()

        def __exit__(self, *exc):
            return self._inner.__exit__(*exc)

    import numpy as np
    rng = np.random.default_rng(0)
    X = rng.normal(size=(60, 8))
    X /= np.linalg.norm(X, axis=1, keepdims=True)

    orig, meaning_upfold._blas_cap = meaning_upfold._blas_cap, lambda: _Recorder()
    try:
        k, labels = meaning_upfold._best_split_gpu(X)
    finally:
        meaning_upfold._blas_cap = orig
    assert entered["n"] == 1
    assert 2 <= k <= meaning_upfold.dials.value("engine-fold", "branch_max") and len(labels) == 60


def test_the_cap_does_not_move_the_partition():
    """The contract half: capping the pools is a TIME change only. Same input, same seed, same
    n_init -> the same labels capped and uncapped. (n_init is the knob that is NOT free - the same
    dial measured n_init<=5 moving the partition, so it stays at the incumbent's 10.)"""
    import numpy as np
    rng = np.random.default_rng(7)
    M = rng.normal(size=(400, 4))
    capped = meaning_upfold._kmeans_as_incumbent(M, 3, len(M))
    with meaning_upfold._blas_cap():
        recapped = meaning_upfold._kmeans_as_incumbent(M, 3, len(M))
    assert list(capped) == list(recapped)


@pytest.fixture(autouse=True)
def _genesis_dials_for_fold_tests(tmp_path_factory, monkeypatch):
    from laplace.pipeline import dial_profiles as dials
    root = tmp_path_factory.mktemp("fold-dials")
    monkeypatch.setenv("LAPLACE_DIALS_ROOT", str(root))
    dials.pour_genesis(root)
