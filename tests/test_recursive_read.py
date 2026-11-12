"""Tests for recursive_read - the descent beside the flat cache (recursive embedding, phase 1).

Two shards in one file:

GEOMETRY (no embedder, no corpus). The tree is HAND-BUILT here rather than folded through
``meaning_upfold.cluster_residue``: the spectral fold needs the optional ``analysis`` extra
(scikit-learn + scipy), and the descent's contracts - which clusters get expanded, which leaves get
materialized, what the LRU evicts, what each degrade refuses on - have nothing to do with how the
tree was clustered. Building the dict directly makes those contracts testable on any box and lets a
test construct the broken trees a fold would never emit (a dead branch, a zero centroid, a leaf
whose source has vanished). A deterministic ``StubBackend`` stands in for bge-small.

INTEGRATION (real embedder, real tree, real oracle). One test, skipped with a reason when fastembed,
``.meaning_tree.json`` or the gitignored residue-vector store is absent. It asserts the thing
the whole design rests on: re-embedding a leaf from its source reproduces the vector the deposit
banked, so the descent and the brute-force oracle are scoring in ONE geometry.

The loud-degrade list is the point of the first shard - every one of them was a silent
``return {}, {}`` in the organ this one grew beside.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pytest

from laplace.engine import meaning_upfold, recursive_read
from laplace.engine.recursive_read import RecursiveReadError

pytest.importorskip("numpy", reason="recursive_read scores with numpy (a declared base dep)")

VERSION = "stub:recursive-read-v1"


# ---------------------------------------------------------------------------
# the stub geometry
# ---------------------------------------------------------------------------

class StubBackend:
    """Four keyword families on orthogonal axes, plus a small deterministic jitter so no two leaves
    tie exactly. Not the hash router (which the open path refuses by name)."""

    name = VERSION
    FAMILIES = ("alpha", "beta", "gamma", "delta")
    dim = 8

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        fam = 0
        for i, key in enumerate(self.FAMILIES):
            if key in text:
                fam, v[i] = i, 1.0
                break
        h = int(hashlib.sha1(text.encode("utf-8")).hexdigest(), 16)
        v[4 + (fam % 4)] += (h % 100) / 500.0
        n = math.sqrt(sum(x * x for x in v))
        return [x / n for x in v] if n else v

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def query(self, text: str) -> list[float]:
        return self._vec(text)


def _unit(vecs: list[list[float]]) -> list[float]:
    acc = [sum(col) / len(vecs) for col in zip(*vecs, strict=True)]
    n = math.sqrt(sum(x * x for x in acc))
    return [x / n for x in acc] if n else acc


@pytest.fixture()
def corpus() -> dict[str, str]:
    """40 leaves, 10 per family. name -> its source text."""
    return {f"{fam}/doc_{i:02d}.md": f"{fam} document {i} topic{i % 3}"
            for fam in StubBackend.FAMILIES for i in range(10)}


@pytest.fixture()
def tree(corpus) -> dict:
    """A two-level tree: root -> one PURE-BRANCH cluster per family pair -> a leaf cluster per
    family (5 leaves each). The pure-branch level banks no centroid, so every descent exercises the
    derive-by-upfold path as well as the banked one."""
    backend = StubBackend()
    clusters: dict[str, dict] = {}
    parent_map: dict[str, str] = {}
    for pair_i, pair in enumerate((("alpha", "beta"), ("gamma", "delta"))):
        branch = f"concept::branch{pair_i}"
        clusters[branch] = {"members": [], "label": f"branch {pair_i}",
                            "centroid": None, "sealed": False}       # pure branch: derived at read
        parent_map[branch] = ""
        for fam in pair:
            names = sorted(n for n in corpus if n.startswith(fam + "/"))
            for half, chunk in enumerate((names[:5], names[5:])):
                cid = f"concept::{fam}{half}"
                vecs = backend.embed([corpus[n] for n in chunk])
                clusters[cid] = {"members": list(chunk), "label": f"{fam} {half}",
                                 "centroid": _unit(vecs), "sealed": False}
                parent_map[cid] = branch
                for n in chunk:
                    parent_map[n] = cid
    leaf_sha = {n: meaning_upfold._text_sha(VERSION, t) for n, t in corpus.items()}
    return {"version": VERSION, "root_id": "", "lens_hash": "stub", "lens_pairs": [],
            "clusters": clusters, "parent_map": parent_map, "leaf_sha": leaf_sha}


@pytest.fixture()
def source(corpus):
    """The leaf-source callable, and a record of which leaves it was actually asked for."""
    asked: list[str] = []

    def fn(name: str) -> str:
        asked.append(name)
        if name not in corpus:
            raise RecursiveReadError("leaf-source-unreadable", f"no source for {name!r}")
        return corpus[name]

    fn.asked = asked                                                  # type: ignore[attr-defined]
    return fn


@pytest.fixture()
def dsc(tmp_path, tree, source):
    return recursive_read.open_descender(
        tmp_path, backend=StubBackend(), leaf_source=source, tree=tree, allow_test_backend=True)


def _brute(corpus: dict[str, str], query: str, k: int) -> list[str]:
    b = StubBackend()
    qv = b.query(query)
    scored = [(sum(a * c for a, c in zip(qv, b.query(t), strict=True)), n)
              for n, t in corpus.items()]
    return [n for _s, n in sorted(scored, key=lambda p: (-p[0], p[1]))[:k]]


# ---------------------------------------------------------------------------
# the descent: it ranks, it prunes, it materializes lazily
# ---------------------------------------------------------------------------

def test_descent_ranks_and_agrees_with_brute_force_on_a_clean_geometry(dsc, corpus):
    """With a wide enough beam the descent recovers the brute-force top-k exactly - the descent is
    a pruning strategy over the same cosine, never a different scoring function."""
    packet = dsc.descend("alpha query", k=5, beam=8)
    got = [h["id"] for h in packet["hits"]]
    assert got == _brute(corpus, "alpha query", 5)
    assert all(h["id"].startswith("alpha/") for h in packet["hits"])
    assert packet["hits"] == sorted(packet["hits"], key=lambda h: -h["score"])


def test_only_visited_clusters_leaves_are_materialized(dsc, source, corpus):
    """The design's whole claim: embedding cost tracks the descent path, not the corpus. A narrow
    beam must leave most of the corpus untouched - and untouched means the leaf source was never
    even ASKED, not merely that the answer excluded it."""
    packet = dsc.descend("alpha query", k=5, beam=1)
    assert packet["materialized"] < len(corpus) / 2
    assert len(set(source.asked)) == packet["materialized"]
    assert not any(n.startswith("gamma/") for n in source.asked)
    assert packet["n_visited_clusters"] < packet["n_clusters_total"]


def test_wider_beam_materializes_more_and_never_loses_agreement(dsc, corpus):
    seen = []
    for beam in (1, 2, 4, 8):
        packet = dsc.descend("beta document 3", k=5, beam=beam)
        got = [h["id"] for h in packet["hits"]]
        overlap = len(set(got) & set(_brute(corpus, "beta document 3", 5))) / 5
        seen.append((packet["materialized"], overlap))
    assert [m for m, _ in seen] == sorted(m for m, _ in seen)
    assert seen[-1][1] >= seen[0][1]
    assert seen[-1][1] == 1.0


def test_descent_reports_its_path_and_geometry(dsc):
    packet = dsc.descend("gamma query", k=3, beam=4)
    hit = packet["hits"][0]
    assert hit["path"][0] == hit["cluster"]
    assert hit["path"][-1].startswith("concept::branch")            # up to the top, root excluded
    assert packet["geometry"]["beam"] == 4 and packet["geometry"]["k"] == 3
    assert packet["axis"] == "semantic" and packet["tree_version"] == VERSION


def test_pure_branch_centroids_are_derived_and_reported(dsc):
    """A cluster with children but no direct leaves banks centroid None (that is how
    _build_tree_from_full writes it - 354 of the 1,982 clusters in the live tree). The read path
    derives it from the children and SAYS it derived it."""
    packet = dsc.descend("delta query", k=3, beam=4)
    assert packet["derived_centroids"], "the pure-branch centroids must be derived, not skipped"
    assert all(c.startswith("concept::branch") for c in packet["derived_centroids"])
    cen = dsc.centroid("concept::branch0")
    assert abs(float((cen * cen).sum()) - 1.0) < 1e-9                 # derivation renormalizes


# ---------------------------------------------------------------------------
# the transient cache: bounded, evicting, dropped after the descent
# ---------------------------------------------------------------------------

def test_cache_is_capped_and_counts_its_evictions(tmp_path, tree, source):
    d = recursive_read.open_descender(tmp_path, backend=StubBackend(), leaf_source=source,
                                      tree=tree, allow_test_backend=True, cache_cap=4)
    d.descend("alpha query", k=5, beam=8, evict_after=False)
    assert len(d._vec_cache) <= 4
    assert d.evictions > 0


def test_evict_after_drops_everything_the_descent_materialized(dsc):
    dsc.descend("alpha query", k=5, beam=8, evict_after=True)
    assert len(dsc._vec_cache) == 0
    dsc.descend("alpha query", k=5, beam=8, evict_after=False)
    assert len(dsc._vec_cache) > 0


def test_warm_cache_skips_the_embedder_second_time(tmp_path, tree, source):
    d = recursive_read.open_descender(tmp_path, backend=StubBackend(), leaf_source=source,
                                      tree=tree, allow_test_backend=True)
    d.descend("alpha query", k=5, beam=8, evict_after=False)
    first = len(source.asked)
    d.descend("alpha query", k=5, beam=8, evict_after=False)
    assert len(source.asked) == first, "a warm cache must not re-derive leaf sources"


# ---------------------------------------------------------------------------
# staleness - the content hash against the tree's banked leaf_sha
# ---------------------------------------------------------------------------

def test_stale_leaf_is_reembedded_and_named(dsc, tree, capsys):
    tree["leaf_sha"]["alpha/doc_00.md"] = "0" * 40                    # the source moved under the fold
    packet = dsc.descend("alpha query", k=5, beam=8)
    assert packet["stale"] == ["alpha/doc_00.md"]
    assert "hashed stale" in capsys.readouterr().out
    assert "alpha/doc_00.md" in [h["id"] for h in packet["hits"]]     # re-embedded, still rankable


def test_strict_staleness_refuses(dsc, tree):
    tree["leaf_sha"]["alpha/doc_00.md"] = "0" * 40
    with pytest.raises(RecursiveReadError) as exc:
        dsc.descend("alpha query", k=5, beam=8, strict_staleness=True)
    assert exc.value.reason == "leaf-stale"


def test_clean_corpus_reports_no_staleness(dsc):
    assert dsc.descend("alpha query", k=5, beam=8)["stale"] == []


# ---------------------------------------------------------------------------
# THE TOP OF THE MAP - the tree-only half (no embedder, no floats, no flat cache)
# ---------------------------------------------------------------------------

def _bank(tmp_path, tree):
    (tmp_path / meaning_upfold.TREE_FILE).write_text(json.dumps(tree), encoding="utf-8")
    return tmp_path


def test_shape_load_drops_the_floats_it_will_never_score_with(tmp_path, tree):
    """The shape load exists because the wake pays for it: the live tree is 19 MB and every one of
    its 625k centroid coordinates is geometry the top-of-map does not use. ``parse_float`` drops
    them and the hook keeps only the BOOLEAN "is a centroid banked here" - which is the one thing a
    handle reports. A shape is therefore NOT descendable, by construction."""
    shape = recursive_read.load_tree_shape(_bank(tmp_path, tree))
    assert "lens_pairs" not in shape
    assert shape["clusters"]["concept::alpha0"]["centroid"] is True     # banked -> True, not floats
    assert shape["clusters"]["concept::branch0"]["centroid"] is False   # pure branch banks None
    assert set(shape["leaf_sha"]) == set(tree["leaf_sha"])              # structure survives whole


def test_top_of_map_covers_the_corpus_and_needs_no_embedder(tmp_path, tree, monkeypatch):
    """The handles are a COVER by leaf mass, not a sample: every leaf sits under exactly one of
    them, so the block's ``covers`` line is an accounting, not a claim. And no backend is ever
    asked for - ``get_backend`` here would load a model at the doorway."""
    from laplace.representation import embed_router

    def _never(*_a, **_k):
        raise AssertionError("the top of the map must never load an embedder")

    monkeypatch.setattr(embed_router, "get_backend", _never)
    block = recursive_read.top_of_map(_bank(tmp_path, tree), handles=8)
    assert block["path"] == "recursive" and block["axis"] == "semantic"
    assert block["embedder"] == VERSION and block["leaves"] == len(tree["leaf_sha"])
    assert sum(h["leaves"] for h in block["top"]) == len(tree["leaf_sha"])
    assert block["covers"].startswith(f"{len(tree['leaf_sha'])}/{len(tree['leaf_sha'])}")
    assert block["top"] == sorted(block["top"], key=lambda h: -h["leaves"])
    assert all(h["centroid"] in ("banked", "derived") for h in block["top"])


def test_top_of_map_splits_by_mass_rather_than_stopping_at_a_thin_root(tmp_path, tree):
    """The live root has two children holding 6,712 and 5,587 leaves - a "root's children" map
    would be two rows that say nothing. Splitting the heaviest expandable handle until the width
    is reached is what makes the top a MAP; a narrower request keeps a coarser one."""
    root = _bank(tmp_path, tree)
    wide = recursive_read.top_of_map(root, handles=8)["top"]
    narrow = recursive_read.top_of_map(root, handles=1)["top"]
    assert len(wide) > len(narrow) == 2                      # the fixture's root has two children
    assert max(h["depth"] for h in wide) > max(h["depth"] for h in narrow)
    assert sum(h["leaves"] for h in narrow) == len(tree["leaf_sha"])   # coarser, still a cover


def test_top_of_map_names_the_fold_horizon(tmp_path, tree):
    """WAKE_RATE_BENCH_2026-08-20 (REPORT_v2.md §5, T18): a claim-evidence question about a
    bundle banked hours earlier is unreachable by descent at every rate - descent only reaches
    what the last fold folded in, and nothing in the payload said so. ``top_of_map`` now
    carries ``fold_horizon``: without a git repo (this fixture) it degrades loudly rather than
    silently, never raising and never a missing key."""
    block = recursive_read.top_of_map(_bank(tmp_path, tree))
    fh = block["fold_horizon"]
    assert set(fh) == {"folded_at", "head_at_fold", "head_now", "warning"}
    assert fh["folded_at"] == "unknown" and fh["head_at_fold"] == "unknown"
    assert fh["warning"]  # named, not silently absent, when there is no git history to read


def test_fold_horizon_states_head_at_fold_and_warns_when_head_has_moved(tmp_path, tree):
    """Inside a real git repo: the fold time and HEAD-at-fold come from the tree file's own
    git history, and the warning fires exactly when a later commit has moved HEAD past the
    fold - the fixed point the bench's T18 finding named."""
    import subprocess

    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    _bank(tmp_path, tree)
    git("add", meaning_upfold.TREE_FILE)
    git("commit", "-q", "-m", "fold")
    fold_head = subprocess.run(["git", "log", "-1", "--format=%h"], cwd=tmp_path,
                               capture_output=True, text=True).stdout.strip()

    at_fold = recursive_read.top_of_map(tmp_path)["fold_horizon"]
    assert at_fold["head_at_fold"] == at_fold["head_now"] == fold_head
    assert at_fold["warning"] is None                       # HEAD has not moved since the fold

    (tmp_path / "unrelated.txt").write_text("x", encoding="utf-8")
    git("add", "unrelated.txt")
    git("commit", "-q", "-m", "unrelated")

    moved = recursive_read.top_of_map(tmp_path)["fold_horizon"]
    assert moved["head_at_fold"] == fold_head
    assert moved["head_now"] != fold_head
    assert moved["warning"] and fold_head in moved["warning"] and "moved since" in moved["warning"]


def test_top_of_map_refuses_loudly_without_a_tree(tmp_path):
    with pytest.raises(RecursiveReadError) as exc:
        recursive_read.top_of_map(tmp_path)
    assert exc.value.reason == "tree-absent"


def test_top_of_map_refuses_an_unreadable_tree(tmp_path):
    (tmp_path / meaning_upfold.TREE_FILE).write_text("{not json", encoding="utf-8")
    with pytest.raises(RecursiveReadError) as exc:
        recursive_read.top_of_map(tmp_path)
    assert exc.value.reason == "tree-unreadable"


def test_query_descent_state_is_probed_without_loading_a_model(monkeypatch):
    """``find_spec`` resolves the import path and stops - it does not execute fastembed, build an
    ONNX session, or reach the network. The wake is offline law; a reachability probe is the most
    the block may spend, and the refusal string is the one the block publishes."""
    import importlib.util

    from laplace.representation import embed_router
    monkeypatch.setattr(embed_router, "_BACKEND", None, raising=False)
    real = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec",
                        lambda n, *a, **k: None if n == "fastembed" else real(n, *a, **k))
    assert recursive_read._query_descent_state() == (
        "embedder-absent (descent needs fastembed; orientation runs tree-only)")
    monkeypatch.setattr(embed_router, "_BACKEND", object(), raising=False)
    assert recursive_read._query_descent_state() == "available"   # warm in-process wins


# ---------------------------------------------------------------------------
# THE LOUD DEGRADES - each one was a silent empty return in the organ beside this
# ---------------------------------------------------------------------------

def test_absent_tree_refuses(tmp_path):
    with pytest.raises(RecursiveReadError) as exc:
        recursive_read.open_descender(tmp_path, backend=StubBackend(), allow_test_backend=True)
    assert exc.value.reason == "tree-absent"


def test_unreadable_tree_refuses(tmp_path):
    (tmp_path / meaning_upfold.TREE_FILE).write_text("{not json", encoding="utf-8")
    with pytest.raises(RecursiveReadError) as exc:
        recursive_read.open_descender(tmp_path, backend=StubBackend(), allow_test_backend=True)
    assert exc.value.reason == "tree-unreadable"


@pytest.mark.parametrize("drop", ["clusters", "parent_map", "leaf_sha", "version"])
def test_malformed_tree_refuses_naming_the_missing_key(tmp_path, tree, source, drop):
    broken = {k: v for k, v in tree.items() if k != drop}
    with pytest.raises(RecursiveReadError) as exc:
        recursive_read.open_descender(tmp_path, backend=StubBackend(), leaf_source=source,
                                      tree=broken, allow_test_backend=True)
    assert exc.value.reason == "tree-malformed"
    assert drop in exc.value.detail


def test_empty_tree_refuses(tmp_path, tree, source):
    tree["clusters"] = {}
    with pytest.raises(RecursiveReadError) as exc:
        recursive_read.open_descender(tmp_path, backend=StubBackend(), leaf_source=source,
                                      tree=tree, allow_test_backend=True)
    assert exc.value.reason == "tree-empty"


def test_absent_embedder_refuses(tmp_path, tree, source, monkeypatch):
    from laplace.representation import embed_router
    monkeypatch.setattr(embed_router, "get_backend", lambda: None)
    with pytest.raises(RecursiveReadError) as exc:
        recursive_read.open_descender(tmp_path, leaf_source=source, tree=tree)
    assert exc.value.reason == "embedder-unavailable"


def test_hash_backend_refuses(tmp_path, tree, source):
    from laplace.representation.embed_router import HashBackend
    with pytest.raises(RecursiveReadError) as exc:
        recursive_read.open_descender(tmp_path, backend=HashBackend(), leaf_source=source, tree=tree)
    assert exc.value.reason == "embedder-not-semantic"


def test_embedder_mismatch_refuses_rather_than_reembedding(tmp_path, tree, source):
    """The named enemy: a different model would put the re-embedded leaves in a different geometry
    than the centroids they are scored against, and the descent would still return ten confident
    rows. It refuses instead."""
    other = StubBackend()
    other.name = "fastembed:some-other-model"
    with pytest.raises(RecursiveReadError) as exc:
        recursive_read.open_descender(tmp_path, backend=other, leaf_source=source, tree=tree,
                                      allow_test_backend=True)
    assert exc.value.reason == "embedder-mismatch"
    assert VERSION in exc.value.detail and "some-other-model" in exc.value.detail


def test_dead_branch_centroid_refuses(tmp_path, tree, source):
    tree["clusters"]["concept::dead"] = {"members": [], "label": "dead", "centroid": None,
                                         "sealed": False}
    tree["parent_map"]["concept::dead"] = ""
    d = recursive_read.open_descender(tmp_path, backend=StubBackend(), leaf_source=source,
                                      tree=tree, allow_test_backend=True)
    with pytest.raises(RecursiveReadError) as exc:
        d.descend("alpha query", k=5, beam=8)
    assert exc.value.reason == "centroid-missing"


def test_zero_centroid_refuses(tmp_path, tree, source):
    tree["clusters"]["concept::alpha0"]["centroid"] = [0.0] * StubBackend.dim
    d = recursive_read.open_descender(tmp_path, backend=StubBackend(), leaf_source=source,
                                      tree=tree, allow_test_backend=True)
    with pytest.raises(RecursiveReadError) as exc:
        d.descend("alpha query", k=5, beam=8)
    assert exc.value.reason == "centroid-malformed"


def test_wrong_dimension_centroid_refuses(tmp_path, tree, source):
    tree["clusters"]["concept::alpha0"]["centroid"] = [1.0, 0.0, 0.0]
    d = recursive_read.open_descender(tmp_path, backend=StubBackend(), leaf_source=source,
                                      tree=tree, allow_test_backend=True)
    with pytest.raises(RecursiveReadError) as exc:
        d.descend("alpha query", k=5, beam=8)
    assert exc.value.reason == "dimension-mismatch"


def test_missing_leaf_source_refuses(dsc, tree):
    tree["clusters"]["concept::alpha0"]["members"].append("alpha/vanished.md")
    tree["parent_map"]["alpha/vanished.md"] = "concept::alpha0"
    tree["leaf_sha"]["alpha/vanished.md"] = "0" * 40
    d = recursive_read.open_descender(dsc.repo_root, backend=StubBackend(),
                                      leaf_source=dsc.leaf_source, tree=tree,
                                      allow_test_backend=True)
    with pytest.raises(RecursiveReadError) as exc:
        d.descend("alpha query", k=5, beam=8)
    assert exc.value.reason == "leaf-source-unreadable"


def test_self_graded_leaf_source_refuses_when_the_shard_is_absent(tmp_path):
    with pytest.raises(RecursiveReadError) as exc:
        recursive_read.SelfGradedLeafSource(tmp_path)
    assert exc.value.reason == "leaf-source-absent"


def test_self_graded_leaf_source_refuses_an_unknown_leaf(tmp_path):
    (tmp_path / ".self_graded.json").write_text(json.dumps({"a.md": {"essence": "a"}}),
                                                encoding="utf-8")
    src = recursive_read.SelfGradedLeafSource(tmp_path)
    with pytest.raises(RecursiveReadError) as exc:
        src("nowhere.md")
    assert exc.value.reason == "leaf-source-unreadable"


def test_self_graded_leaf_source_uses_the_pre_ascent_route_handle(tmp_path):
    """An authored file may also be an internal serving node.  Child terms enrich that public
    handle, but descent must reproduce the original handle the semantic fold actually embedded."""
    node = {
        "essence": "served essence",
        "keywords": ["own", "promoted-child-term"],
        "sealed": False,
        "route_handle": {
            "essence": "served essence",
            "keywords": ["own"],
            "sealed": False,
        },
    }
    (tmp_path / ".self_graded.json").write_text(json.dumps({"theme.md": node}), encoding="utf-8")
    src = recursive_read.SelfGradedLeafSource(tmp_path)
    assert src("theme.md") == "theme | served essence | own"


def test_empty_descent_refuses(tmp_path, source):
    """A tree of pure branches reaches no leaf. An empty answer is a failure, not a short list."""
    leafless = {"version": VERSION, "root_id": "", "clusters": {}, "parent_map": {}, "leaf_sha": {}}
    leafless["clusters"] = {"concept::a": {"members": [], "label": "a", "centroid": [1.0] + [0.0] * 7,
                                           "sealed": False}}
    leafless["parent_map"] = {"concept::a": ""}
    d = recursive_read.open_descender(tmp_path, backend=StubBackend(), leaf_source=source,
                                      tree=leafless, allow_test_backend=True)
    with pytest.raises(RecursiveReadError) as exc:
        d.descend("alpha query", k=5, beam=8)
    assert exc.value.reason == "descent-empty"


def test_broken_embedder_mid_descent_refuses(tmp_path, tree, source):
    class Dying(StubBackend):
        def embed(self, texts):
            raise RuntimeError("onnx session closed")

    d = recursive_read.open_descender(tmp_path, backend=Dying(), leaf_source=source, tree=tree,
                                      allow_test_backend=True)
    with pytest.raises(RecursiveReadError) as exc:
        d.descend("alpha query", k=5, beam=8)
    assert exc.value.reason == "embed-failed"


def test_unknown_axis_refuses(tmp_path, tree, source):
    with pytest.raises(RecursiveReadError) as exc:
        recursive_read.open_descender(tmp_path, backend=StubBackend(), leaf_source=source,
                                      tree=tree, axis="structural", allow_test_backend=True)
    assert exc.value.reason == "axis-unknown"


@pytest.mark.parametrize("kwargs,reason", [({"k": 0}, "bad-k"), ({"beam": 0}, "bad-beam")])
def test_degenerate_geometry_refuses(dsc, kwargs, reason):
    with pytest.raises(RecursiveReadError) as exc:
        dsc.descend("alpha query", **kwargs)
    assert exc.value.reason == reason


# ---------------------------------------------------------------------------
# the frontier policy: a derivative tree must not starve the corpus it derives FROM
#
# The measured disease (WO-20260820-synthetics-outrank-their-sources): provenance is not uniform in
# the corpus - one derivative root holds 3,055 leaves against published_corpus/'s 70 - so a
# level-synchronous top-beam spends its whole width inside the derivative project and drops the
# source paper's branch, though the source paper's LEAF outscores most of what came back. These
# tests rebuild that shape in miniature: five branches, four derivative, one canonical, the
# canonical one scoring just below the beam's cut.
# ---------------------------------------------------------------------------

class TableBackend:
    """Vectors by lookup, so a test can state the exact cosines the frontier has to choose between."""

    name = VERSION
    dim = 2

    def __init__(self, table: dict[str, list[float]]) -> None:
        self.table = table

    def _vec(self, text: str) -> list[float]:
        if text not in self.table:
            raise AssertionError(f"TableBackend has no vector for {text!r}")
        return self.table[text]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def query(self, text: str) -> list[float]:
        return self._vec(text)


def _cos(c: float) -> list[float]:
    return [c, math.sqrt(max(0.0, 1.0 - c * c))]


@pytest.fixture()
def provenance(tmp_path):
    """One canonical branch at cosine 0.90 against four derivative branches at 0.91-0.94, and the
    single best LEAF in the whole corpus (0.97) sitting inside the canonical one."""
    texts = {
        "published_corpus/tex/paper/v1.tex": "canonical leaf",
        "corpus_stores/spine_chain/paper.jsonl": "canonical store row",
    }
    table = {"canonical leaf": _cos(0.97), "canonical store row": _cos(0.80),
             "the paper's topic": [1.0, 0.0], "the derivative project's own build": _cos(0.10)}
    clusters = {"concept::canonical": {"members": sorted(texts), "label": "canonical",
                                       "centroid": _cos(0.90), "sealed": False}}
    parent_map = {"concept::canonical": ""}
    for name in texts:
        parent_map[name] = "concept::canonical"
    for i, c in enumerate((0.94, 0.93, 0.92, 0.91)):
        cid = f"concept::derivative{i}"
        clusters[cid] = {"members": [], "label": f"derivative {i}", "centroid": _cos(c),
                         "sealed": False}
        parent_map[cid] = ""
        for j in range(3):
            leaf = f"synthetics papers/project{i}/part_{j}.md"
            body = f"derivative {i} part {j}"
            texts[leaf] = body
            # every derivative leaf scores below the canonical one, and the project's OWN query
            # (a different vector) is the only thing that ranks them first.
            table[body] = _cos(0.88 - 0.01 * j)
            clusters[cid]["members"].append(leaf)
            parent_map[leaf] = cid
    tree = {"version": VERSION, "root_id": "", "lens_hash": "stub", "lens_pairs": [],
            "clusters": clusters, "parent_map": parent_map,
            "leaf_sha": {n: meaning_upfold._text_sha(VERSION, t) for n, t in texts.items()}}
    table["the derivative project's own build"] = _cos(0.10)
    backend = TableBackend(table)
    dsc = recursive_read.open_descender(tmp_path, backend=backend, leaf_source=texts.__getitem__,
                                        tree=tree, allow_test_backend=True)
    return dsc


def test_incumbent_beam_lets_the_derivative_trees_starve_the_source(provenance):
    """The regression itself, stated as a test: four derivative branches out-score the canonical one
    at the frontier, so the descent never materializes the leaf that would have won."""
    packet = provenance.descend("the paper's topic", k=5, beam=4,
                                select_policy={"mode": "beam"})
    got = [h["id"] for h in packet["hits"]]
    assert all(h.startswith("synthetics papers/") for h in got)
    assert not any(h.startswith("published_corpus/") for h in got)


def test_the_ruled_policy_recovers_the_source_without_evicting_the_derivative(provenance):
    """The cure's two halves in one assertion: the canonical branch is entered (its leaf is now the
    top hit) and the derivative branches the incumbent entered are entered still."""
    packet = provenance.descend("the paper's topic", k=5, beam=4)
    got = [h["id"] for h in packet["hits"]]
    assert got[0] == "published_corpus/tex/paper/v1.tex"
    assert any(h.startswith("synthetics papers/") for h in got)
    assert packet["geometry"]["select"] == recursive_read.SELECT_POLICY


def test_a_derivative_project_stays_reachable_under_its_own_query(provenance):
    """The cure must not simply invert the eating. Under a query aimed at the derivative build, the
    canonical branch's 0.08 lift is nowhere near enough to displace it."""
    packet = provenance.descend("the derivative project's own build", k=5, beam=4)
    got = [h["id"] for h in packet["hits"]]
    assert any(h.startswith("synthetics papers/") for h in got)


def test_canonical_share_is_read_off_the_tree_not_the_query(provenance):
    assert provenance.canonical_share("concept::canonical") == 1.0
    assert provenance.canonical_share("concept::derivative0") == 0.0
    assert provenance.root_counts("concept::derivative0") == {"synthetics papers/": 3}
    assert provenance.dominant_root("concept::canonical") in recursive_read.CANONICAL_ROOTS


@pytest.mark.parametrize("policy", [{"mode": "beam"}, {"mode": "quota", "quota": 1},
                                    {"mode": "floor", "floor": 1}, {"mode": "widen", "floor": 2},
                                    {"mode": "epsilon", "epsilon": 0.05, "max_beam": 8},
                                    {"mode": "canonical_boost", "weight": 0.08}])
def test_every_named_policy_still_answers(provenance, policy):
    """The losers stay implemented and runnable - they are the alternatives the ruling was made
    against, and a policy that cannot be re-run is not an alternative, it is a claim."""
    packet = provenance.descend("the paper's topic", k=5, beam=2, select_policy=policy)
    assert packet["hits"] and packet["geometry"]["select"] == policy


def test_unknown_frontier_policy_refuses_loudly(provenance):
    with pytest.raises(RecursiveReadError) as exc:
        provenance.descend("the paper's topic", k=5, beam=2,
                           select_policy={"mode": "vibes"})
    assert exc.value.reason == "select-policy-unknown"


def test_every_refusal_carries_a_reason_and_a_detail():
    err = RecursiveReadError("some-reason", "what and where")
    assert err.reason == "some-reason" and err.detail == "what and where"
    assert "recursive read refused (some-reason)" in str(err)


# ---------------------------------------------------------------------------
# integration: the real embedder, the real tree, the real oracle
# ---------------------------------------------------------------------------

REPO = Path(__file__).resolve().parents[1]
_HAVE_TREE = (REPO / meaning_upfold.TREE_FILE).is_file()
_VEC_PATH, _IDX_PATH = meaning_upfold.sidecar_paths(REPO)
# the store is the sidecar pair since 2026-08-20 (MV-1); the legacy monolith still counts while it
# survives the transition, because ``load_vectors`` reads either one.
_HAVE_CACHE = (_VEC_PATH.is_file() and _IDX_PATH.is_file()) or (REPO / meaning_upfold.CACHE_FILE).is_file()
_HAVE_SHARD = (REPO / ".self_graded.json").is_file()


@pytest.mark.skipif(not (_HAVE_TREE and _HAVE_CACHE and _HAVE_SHARD),
                    reason="needs the banked .meaning_tree.json + the gitignored residue-vector "
                           "store (.meaning_vectors.f32.npy + .index.json, or the legacy "
                           ".meaning_vectors.json) + .self_graded.json on this box")
def test_reembedding_a_leaf_reproduces_the_banked_vector():
    """The load-bearing assumption of the whole read path. If a re-embed did NOT reproduce the
    deposit's vector, the descent would be scoring materialized leaves in a geometry slightly
    different from the centroids above them, and the oracle comparison would be meaningless."""
    fastembed = pytest.importorskip("fastembed", reason="the real embedder is not installed here")
    assert fastembed is not None
    import numpy as np

    from laplace.representation.embed_router import get_backend
    backend = get_backend()
    if backend is None or backend.name.startswith("hash"):
        pytest.skip("the fastembed model could not load on this box")
    tree = meaning_upfold.load_tree(REPO)
    if backend.name != tree["version"]:
        pytest.skip(f"tree folded by {tree['version']}, live embedder is {backend.name}")
    _bk, banked_names, banked_mat = meaning_upfold.load_vectors(REPO)
    banked = {nm: i for i, nm in enumerate(banked_names)}
    src = recursive_read.SelfGradedLeafSource(REPO)
    names = [n for n in sorted(tree["leaf_sha"])[:400] if n in banked][:16]
    assert names, "no overlap between the tree's leaves and the vector store"
    fresh = backend.embed([src(n) for n in names])
    for name, vec in zip(names, fresh, strict=True):
        a = np.asarray(vec, dtype=np.float64)
        b = np.asarray(banked_mat[banked[name]], dtype=np.float64)
        a /= np.linalg.norm(a)
        b /= np.linalg.norm(b)
        assert float(a @ b) > 0.9999, f"{name} re-embedded into a different vector"
