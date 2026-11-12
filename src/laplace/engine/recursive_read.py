"""recursive_read.py - the read-path over the banked concept tree, beside the flat vector cache.

Phase 1 of recursive embedding (his trigger, 2026-07-28: the flat cache crossed GitHub's 100 MB
limit - "that's the signal that we should figure out recursive embedding, because right now it's
storing the whole map"). A STRANGLER organ: nothing here writes, nothing here changes
``meaning_upfold``'s deposit path, and the residue-vector store stays exactly where it is and
stays authoritative. This module only READS, and the flat store is the oracle it is scored against
(``scripts/recursive_read_harness.py``). That store became the ``.meaning_vectors.f32.npy`` +
``.meaning_vectors.index.json`` sidecar pair on 2026-08-20 (MV-1); nothing on this path changed,
because nothing on this path ever opened it.

What it does. ``.meaning_tree.json`` already banks a unit centroid on every leaf-bearing cluster
(1,628 of 1,982 at the 07-28 fold; the other 354 are pure-branch and derive theirs here). A query
descends that tree by cosine against centroids, expanding ``beam`` clusters per level, and
materializes leaf vectors ONLY inside the clusters the descent actually visits - re-embedding each
one from its source text, checking the content hash against the tree's banked ``leaf_sha``, holding
it in a bounded LRU, and dropping it when the descent ends. Embedding cost is proportional to the
descent path, not to the corpus. The tree (~19 MB, committed) is the only persisted vector store
the path needs; the 101 MB of leaf floats are not read at all.

What it does not do. No write path, no deposit change, no storage migration - phase 1 is a read
and a harness. Leaf scores are the PLAIN cosine the brute-force path uses, never a path-inherited
heat (``embed_router.route`` inherits heat down the descent; that is a different scoring function
and would make an agreement number meaningless). The descent decides WHICH leaves get scored; it
does not change HOW they score. So overlap against the oracle measures exactly one thing: what the
pruning costs.

LOUD DEGRADES. Every unavailability raises ``RecursiveReadError`` with a named ``reason``. The
07-24 regression was a silent ``return {}, {}`` - three deposits with zero concept nodes and no
line printed - and that class is the named enemy here. In particular an embedder whose name does
not match the tree's banked ``version`` REFUSES; it does not quietly re-embed the corpus into a
second geometry. ``meaning_upfold``'s own silent degrades were made loud in the same commit.

The axis is named (``axis="semantic"``, the bge-small fold) per the fibred-upfold input: this is
one section, not the map. A second axis is a second tree, read by the same descent.

BANKED AGREEMENT, 2026-07-28 (real corpus: 1,982 clusters, 12,299 leaves; 40 queries; k=10;
seed 20260728). Full run and method in ``evidence/RECURSIVE_READ_2026-07-28_agreement.md``:

    beam   overlap@10   top1    score deficit   leaves materialized   wall-clock/query
      2       0.477     0.500      +0.0167             18.3               0.46 s
      4       0.645     0.850      +0.0087             38.6               1.45 s
      8       0.835     0.950      +0.0037            100.9               1.44 s
     16       0.932     1.000      +0.0010            225.9               2.62 s
    brute      1.000    1.000      +0.0000         12,295                 0.015 s

"score deficit" is mean(oracle top-k cosine) - mean(recursive top-k cosine): what the misses cost
in the geometry, which overlap@k alone cannot say. Kendall tau is 1.000 at every beam and carries
no information here - both paths score by the same plain cosine, so a recovered leaf is always in
the oracle's relative order. It is measured anyway, as the tripwire that would fire if the descent
ever started scoring differently.

THE truthful READING. At beam 8 the descent recovers 83.5% of the oracle's top-10, and its own best
leaf IS the oracle's best leaf on 95% of queries, having touched 101 of 12,295 vectors - 0.8% of the
corpus. The score deficit at that width is +0.0037 cosine, so the leaves it does return are very
nearly as good as the ones it missed. What phase 1 buys is the STORED map (101 MB of leaf floats
stop being needed at read time; the ~19 MB tree suffices) and the vectors touched per query. What it
does not buy is latency: 1.4 s/query against 15 ms, because re-embedding is slower than a matmul
over floats already on disk. Trading 100x latency for 120x fewer resident vectors is the phase-1
bargain, and it is a bargain only where the corpus does not fit.

DEFAULT BEAM is 4 - not a finding, a default. It is the lowest width whose top1 is already 0.85,
and the caller is expected to raise it (the geometry is a per-call argument, exactly as
``embed_router.route``'s is).
"""
from __future__ import annotations

import json
import subprocess
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable

from laplace.engine import meaning_upfold

DEFAULT_BEAM = 4           # internal clusters expanded per level (see the banked sweep above)
DEFAULT_K = 10             # leaves returned
# THE CANONICAL ROOTS - the corpus a derivative tree is derived FROM (see SELECT_POLICY).
CANONICAL_ROOTS = ("published_corpus/", "life_corpus/", "concept_corpus/",
                   "corpus_stores/", "collaborator_corpus/")
# THE RULED FRONTIER POLICY (2026-08-20, WO-20260820-synthetics-outrank-their-sources). Set by
# measurement, not taste: seventeen policies over 25 paper queries + 8 derivative-tree controls,
# `evidence/DESCENT_PROVENANCE_2026-08-20/sweep.json`. The winner lands 23 of 25 papers' own family
# (incumbent 18), regresses none, and costs 38.9 leaves materialized per query against 27.0.
# The weight's working band is measured 0.06-0.10 - below it the recovery decays (0.05 -> 20/25),
# at 0.11 the cure INVERTS and a synthetics project stops being reachable under its own query -
# and 0.08 is that band's midpoint, chosen for margin on both sides rather than for a best number.
# Overridable per Descender (``d.select_policy``) and per call (``descend(..., select_policy=...)``);
# ``{"mode": "beam"}`` restores the incumbent exactly.
SELECT_POLICY: dict[str, Any] = {"mode": "canonical_boost", "weight": 0.08}
DEFAULT_CACHE_CAP = 4096   # materialized leaf vectors held at once (~6 MB at 384 float32)
SEMANTIC_AXIS = "semantic"  # the axis .meaning_tree.json folds along (bge-small); one section, not the map
TOP_HANDLES = 8            # target width of the wake's top-of-map (see ``top_of_map``; may overshoot once)


class RecursiveReadError(RuntimeError):
    """A named refusal on the read path. ``reason`` is a stable slug; the message says what and where.

    Never caught-and-emptied inside this module: the whole point of phase 1 is that a degrade on the
    recursive path is visible at the call site, not a quietly shorter answer."""

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(f"recursive read refused ({reason}): {detail}")
        self.reason = reason
        self.detail = detail


def _emit(msg: str) -> None:
    """One plain line - the module's print voice, matching meaning_upfold's."""
    print(f"recursive read: {msg}")


# ---------------------------------------------------------------------------
# The top of the map - the tree-only read the wake takes (no embedder, no floats)
#
# His order 2026-07-28: "the recursive embedding can take over the wake." The wake path never
# read the flat cache to begin with (nothing did outside meaning_upfold's own deposit and the
# harness's oracle) - it carried NO semantic surface at all, which is the thing the design's
# recursive-embedding addendum names: "the wake thickens hierarchically: grade 0 needs only the
# top centroids". So the takeover is additive: grade 0 now carries the top of the banked map,
# read from ``.meaning_tree.json`` and nothing else.
#
# THE WAKE'S Offline law is absolute, so this half of the organ is separated from the descent by
# construction: no embedder, no model load, no network, no numpy, and no leaf vector. It reads
# the tree's SHAPE - labels, parentage, leaf counts - which is exactly the "top centroids" layer
# with the geometry left on disk. A query still needs the embedder; ``top_of_map`` says so in the
# block rather than pretending, and points at ``descend`` as the call that fires it.
# ---------------------------------------------------------------------------

_SHAPE_DROP = ("lens_pairs",)   # the fold's lens-membership list: 12,299 strings the shape never reads


def load_tree_shape(repo_root: Path | str) -> dict[str, Any]:
    """The banked tree's STRUCTURE, loaded without its floats. Refuses loudly, like every read here.

    The full parse of the live 19 MB tree costs 0.28 s and 29 MB resident, and 100% of that weight
    is geometry the wake does not use: ``parse_float`` drops every centroid coordinate on the floor
    and an ``object_pairs_hook`` drops ``lens_pairs`` outright and collapses each ``centroid`` to the
    BOOLEAN "is one banked here" - measured 0.12 s / 7 MB, the whole cost the wake pays for its
    semantic block. No new derived cache: the tree is read straight, just not into floats.

    The returned dict is deliberately NOT a descendable tree - its centroids are bools. Never hand
    it to ``open_descender``/``Descender``; that path opens the tree itself (``meaning_upfold.load_tree``)."""
    root = Path(repo_root)
    path = root / meaning_upfold.TREE_FILE
    if not path.is_file():
        raise RecursiveReadError(
            "tree-absent",
            f"{path} is missing - there is no banked concept tree, so there is no map to sit on top "
            f"of. Run the deposit (keeper.build_self) to fold one")

    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        return {k: (bool(v) if k == "centroid" else v) for k, v in pairs if k not in _SHAPE_DROP}

    try:
        shape = json.loads(path.read_bytes(), object_pairs_hook=hook, parse_float=lambda _s: None)
    except (OSError, json.JSONDecodeError) as exc:
        raise RecursiveReadError("tree-unreadable", f"{path}: {exc}") from exc
    missing = [key for key in ("clusters", "parent_map", "leaf_sha", "version") if key not in shape]
    if missing:
        raise RecursiveReadError(
            "tree-malformed",
            f"the concept tree is missing {', '.join(missing)} - it is not a map this path can read")
    if not shape["clusters"]:
        raise RecursiveReadError("tree-empty", "the concept tree banks zero clusters - no map to show")
    return shape


def _query_descent_state() -> str:
    """Can a query descend from this process? Probed WITHOUT loading the model.

    ``importlib.util.find_spec`` only resolves the import path - it does not execute fastembed, does
    not build an ONNX session, and cannot reach the network. That matters: the wake is offline law,
    and ``embed_router.get_backend()`` here would spend seconds and try to fetch weights. So the
    block declares reachability, not a loaded model; the first ``descend`` is what actually loads it
    (and refuses by name if the live embedder disagrees with the tree's ``version``)."""
    import importlib.util

    from laplace.representation import embed_router
    if embed_router._BACKEND is not None:            # already warm in this process - the strongest signal
        return "available"
    try:
        found = importlib.util.find_spec("fastembed") is not None
    except (ImportError, ValueError):                # a broken/partial install resolves to absent
        found = False
    return "available" if found else (
        "embedder-absent (descent needs fastembed; orientation runs tree-only)")


def _fold_horizon(repo_root: Path) -> dict[str, Any]:
    """When the descendable map was last folded, and whether HEAD has moved since.

    WAKE_RATE_BENCH_2026-08-20 (REPORT_v2.md §5, T18): a claim-evidence question about a
    bundle banked hours earlier is unreachable by descent at EVERY rate, on both channels,
    at two descent widths (beam 8/16) - not a rate failure, a fold-cadence one. "Today's
    own evidence is not yet reachable by descent... a bundle banked hours ago is not in the
    folded map... The wake's ability to answer 'what backs this claim' has a horizon of one
    fold, and nothing in the payload says so." This closes that gap: cheap (one `git log`
    against the tree file's own history, no network, no embedder), and named rather than
    silently absent on any git failure - the same law ``top_of_map`` follows for a missing
    tree."""
    repo_root = Path(repo_root)

    def git(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=repo_root, capture_output=True,
                              text=True, timeout=5).stdout.strip()

    try:
        fold_line = git("log", "-1", "--format=%h %cI", "--", meaning_upfold.TREE_FILE)
        head_now = git("log", "-1", "--format=%h")
        if not fold_line or not head_now:
            return {"folded_at": "unknown", "head_at_fold": "unknown", "head_now": head_now or "unknown",
                    "warning": "no git history for the tree file - fold horizon unknown"}
        head_at_fold, folded_at = fold_line.split(" ", 1)
        warning = (None if head_at_fold == head_now else
                   f"HEAD has moved since the last fold ({head_at_fold} -> {head_now}) - descent "
                   f"reaches only what {head_at_fold} folded in; anything banked after that fold "
                   f"(evidence, rows, new work) is not yet in the descendable map")
        return {"folded_at": folded_at, "head_at_fold": head_at_fold, "head_now": head_now,
                "warning": warning}
    except Exception as exc:  # noqa: BLE001 - named, never silent (top_of_map's own law)
        return {"folded_at": "unknown", "head_at_fold": "unknown", "head_now": "unknown",
                "warning": f"fold-horizon probe failed ({type(exc).__name__}: {exc})"}


def top_of_map(repo_root: Path | str, handles: int = TOP_HANDLES) -> dict[str, Any]:
    """The wake's semantic block: the top of the banked map as label handles, tree-only.

    The handles are chosen by LEAF MASS, not by a fixed depth: start at the root's cluster children
    and repeatedly split the heaviest expandable one until the frontier reaches ``handles``. The live
    root has only two children (6,712 and 5,587 leaves), so a fixed "root's children" would be a
    two-row map that says nothing; splitting by mass gives a real coarse cover at a chosen resolution.
    The last split is taken whole rather than half-applied, so the width may overshoot ``handles``
    once - a partial split would leave leaves under no handle, and a cover that lies about its
    coverage is worse than a slightly wider one. ``covers`` reports the leaves actually under the
    handles against the corpus total, so an incomplete cover (a cluster holding direct leaves AND
    children, split here) is visible rather than assumed.

    Every handle names whether its centroid is BANKED or DERIVED - the same distinction ``descend``
    reports - because a derived centroid is a real approximation the descent leans on.

    Raises ``RecursiveReadError`` when there is no readable tree. The caller decides whether that is
    fatal; ``wake`` turns it into a loud block, never a missing key."""
    t0 = time.perf_counter()
    shape = load_tree_shape(repo_root)
    clusters: dict[str, dict] = shape["clusters"]
    root_id: str = shape.get("root_id", "")

    cluster_children: dict[str, list[str]] = {}
    leaf_children: dict[str, list[str]] = {}
    for child, parent in shape["parent_map"].items():
        bucket = cluster_children if child in clusters else leaf_children
        bucket.setdefault(parent, []).append(child)

    counts: dict[str, int] = {}

    def leaf_count(cid: str) -> int:
        cached = counts.get(cid)
        if cached is not None:
            return cached
        n = len(leaf_children.get(cid, ()))
        for kid in cluster_children.get(cid, ()):
            n += leaf_count(kid)
        counts[cid] = n
        return n

    depth = {cid: 1 for cid in cluster_children.get(root_id, ())}
    frontier = list(depth)
    while len(frontier) < max(1, handles):
        splittable = [cid for cid in frontier if cluster_children.get(cid)]
        if not splittable:
            break                                   # the top IS the whole map; nothing left to split
        big = max(splittable, key=lambda cid: (leaf_count(cid), cid))
        frontier.remove(big)
        for kid in cluster_children[big]:
            depth[kid] = depth[big] + 1
            frontier.append(kid)

    frontier.sort(key=lambda cid: (-leaf_count(cid), cid))
    top = [{"id": cid,
            "label": clusters[cid].get("label") or "(unlabelled)",
            "leaves": leaf_count(cid),
            "children": len(cluster_children.get(cid, ())),
            "depth": depth.get(cid, 1),
            "centroid": "banked" if clusters[cid].get("centroid") else "derived"}
           for cid in frontier]
    covered = sum(h["leaves"] for h in top)
    total = len(shape["leaf_sha"])
    return {
        "path": "recursive",
        "axis": SEMANTIC_AXIS,
        "clusters": len(clusters),
        "leaves": total,
        "embedder": shape["version"],
        "query_descent": _query_descent_state(),
        "top": top,
        "covers": f"{covered}/{total} leaves under the handles above",
        "read": (f"{meaning_upfold.TREE_FILE} only - centroids and lens pairs left unparsed; "
                 f"the residue-vector store ({meaning_upfold.VEC_FILE} + {meaning_upfold.IDX_FILE}, "
                 f"and the legacy {meaning_upfold.CACHE_FILE}) is NOT opened on this path"),
        "descend": ("recursive_read.descend(repo_root, '<query>', beam=4) - descends these centroids "
                    "and materializes leaf vectors only along the path it takes"),
        "fold_horizon": _fold_horizon(repo_root),
        "seconds": round(time.perf_counter() - t0, 3),
    }


# ---------------------------------------------------------------------------
# the leaf source - what a leaf's vector is recomputed FROM
# ---------------------------------------------------------------------------

class SelfGradedLeafSource:
    """The default leaf-text provider: the banked self-shard (``.self_graded.json``), read through
    ``meaning_upfold._embeddable_text`` - the SAME derivation the deposit embedded, so a re-embed
    reproduces the banked vector exactly (measured: cosine 1.000000 over a 64-leaf sample, 07-28).

    A sealed leaf's content is read here in-process for the vector only, exactly as at fold time;
    it is never returned to a caller, never cached as text, never labelled. The seal holds.

    A real file which also serves as an internal node carries ``route_handle``: the exact
    pre-ascent essence/keywords the semantic fold embedded.  The public serving handle remains
    enriched with child terms, while this reader reproduces the route geometry rather than hashing
    a different representation and falsely reporting a fresh deposit stale.

    A leaf absent from the shard raises rather than returning "" - an empty text embeds to a real
    vector that scores like a real leaf, which is the silent degrade in its purest form."""

    def __init__(self, repo_root: Path | str) -> None:
        self.repo_root = Path(repo_root)
        path = self.repo_root / ".self_graded.json"
        if not path.is_file():
            raise RecursiveReadError(
                "leaf-source-absent",
                f"{path} is missing - the read path recomputes leaf vectors from the banked "
                f"self-shard's essence/keywords; without it no leaf can be materialized")
        try:
            self._nodes: dict[str, dict] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RecursiveReadError("leaf-source-unreadable", f"{path}: {exc}") from exc

    def __call__(self, name: str) -> str:
        node = self._nodes.get(name)
        if node is None:
            raise RecursiveReadError(
                "leaf-source-unreadable",
                f"leaf {name!r} is in the tree but not in .self_graded.json - its source text "
                f"cannot be recovered, so its vector cannot be materialized")
        from laplace.representation.embed_router import TEXT_CAP
        route_handle = node.get("route_handle")
        if isinstance(route_handle, dict):
            node = route_handle
        return meaning_upfold._embeddable_text(self.repo_root, name, node, TEXT_CAP)


LeafSource = Callable[[str], str]


# ---------------------------------------------------------------------------
# the descender
# ---------------------------------------------------------------------------

class Descender:
    """One opened tree + one embedder, ready to answer queries by descent.

    Construction validates the tree and the embedder-vs-tree agreement ONCE and loudly; after that
    ``descend`` is the only call. The instance holds a bounded LRU of materialized leaf vectors -
    transient by construction, and by default dropped at the end of each descent (``evict_after``),
    so the resident cost of the read path is one descent's path, never the corpus."""

    def __init__(self, repo_root: Path | str, tree: dict[str, Any], backend: Any,
                 leaf_source: LeafSource, axis: str = SEMANTIC_AXIS,
                 cache_cap: int = DEFAULT_CACHE_CAP) -> None:
        import numpy as np

        self.repo_root = Path(repo_root)
        self.tree = tree
        self.backend = backend
        self.leaf_source = leaf_source
        self.axis = axis
        self.cache_cap = int(cache_cap)
        self._np = np

        self.clusters: dict[str, dict] = tree["clusters"]
        self.parent_map: dict[str, str] = tree["parent_map"]
        self.leaf_sha: dict[str, str] = tree["leaf_sha"]
        self.root_id: str = tree.get("root_id", "")

        # child index: parent -> (cluster children, leaf children). parent_map points the other way.
        self.cluster_children: dict[str, list[str]] = {}
        self.leaf_children: dict[str, list[str]] = {}
        for child, parent in self.parent_map.items():
            bucket = self.cluster_children if child in self.clusters else self.leaf_children
            bucket.setdefault(parent, []).append(child)
        for d in (self.cluster_children, self.leaf_children):
            for members in d.values():
                members.sort()

        self._centroid_cache: dict[str, Any] = {}
        self._leaf_counts: dict[str, int] = {}
        self._root_counts: dict[str, dict[str, int]] = {}
        self.select_policy: dict[str, Any] = dict(SELECT_POLICY)
        self._derived_centroids: set[str] = set()
        self._vec_cache: OrderedDict[str, Any] = OrderedDict()
        self.evictions = 0

    # -- centroids ---------------------------------------------------------

    def _leaf_count(self, cid: str) -> int:
        """Leaves at or below a cluster - the weight its centroid carries when a pure-branch parent
        upfolds its children. Memoized on the Descender, never written back into the caller's tree
        dict (``open_descender`` accepts one, and this path must not mutate it)."""
        cached = self._leaf_counts.get(cid)
        if cached is not None:
            return cached
        n = len(self.leaf_children.get(cid, ()))
        for kid in self.cluster_children.get(cid, ()):
            n += self._leaf_count(kid)
        self._leaf_counts[cid] = n
        return n

    # -- who lives under a cluster (the frontier policy's only input) -------

    def root_counts(self, cid: str) -> dict[str, int]:
        """``top-level path segment -> leaves under ``cid`` carrying it``, memoized.

        Read from the tree's own parentage - no source read, no vector, no store. It is what lets
        the frontier ask "is this branch nine tenths one derivative project?" without knowing
        anything about the query."""
        cached = self._root_counts.get(cid)
        if cached is not None:
            return cached
        counts: dict[str, int] = {}
        for leaf in self.leaf_children.get(cid, ()):
            root = leaf.split("/", 1)[0] + "/" if "/" in leaf else leaf
            counts[root] = counts.get(root, 0) + 1
        for kid in self.cluster_children.get(cid, ()):
            for root, n in self.root_counts(kid).items():
                counts[root] = counts.get(root, 0) + n
        self._root_counts[cid] = counts
        return counts

    def dominant_root(self, cid: str) -> str:
        counts = self.root_counts(cid)
        if not counts:
            return ""
        return max(sorted(counts), key=lambda r: counts[r])

    def canonical_share(self, cid: str) -> float:
        """Fraction of the leaves under ``cid`` that live in the canonical corpus."""
        counts = self.root_counts(cid)
        total = sum(counts.values())
        if not total:
            return 0.0
        return sum(n for r, n in counts.items() if r in CANONICAL_ROOTS) / total

    def select_frontier(self, level: list[tuple[float, str]], beam: int,
                        policy: dict[str, Any] | None = None) -> list[str]:
        """Choose which of a scored level's clusters the descent enters. ``level`` is already
        sorted best-first; the return is the kept cluster ids.

        THE INCUMBENT ("beam") is ``level[:beam]`` and is what every banked agreement number above
        was measured at. It has one measured failure mode, WO-20260820-synthetics-outrank-their-
        sources: the corpus is not uniform in provenance. 3,055 of 14,491 leaves live under one
        derivative root (``synthetics papers/``), 70 under ``published_corpus/``. A synthetics
        project seeded FROM a paper therefore fields dozens of near-duplicate branches against the
        paper's one, and a level-synchronous top-4 spends its whole width inside them: on the
        free-snacks anchor the paper's own branch scored 0.708 at level 4 against a 0.727 cut and
        was dropped, though the leaf it holds scores 0.771 against that very query - higher than
        eight of the ten hits that were returned instead. The pruning, not the geometry, lost it.

        The named alternatives and their measured numbers live in
        ``evidence/DESCENT_PROVENANCE_2026-08-20/``; ``SELECT_POLICY`` names the ruled default."""
        policy = self.select_policy if policy is None else policy
        mode = policy.get("mode", "beam")
        if mode == "beam" or beam >= len(level):
            return [cid for _s, cid in level[:beam]]
        if mode == "quota":
            # DIVERSITY, not preference: at most ``quota`` of the beam may come from any single
            # top-level root, remaining slots refilled in score order from the deferred.
            quota = int(policy.get("quota", 2))
            kept: list[str] = []
            deferred: list[str] = []
            taken: dict[str, int] = {}
            for _s, cid in level:
                root = self.dominant_root(cid)
                if taken.get(root, 0) >= quota:
                    deferred.append(cid)
                    continue
                taken[root] = taken.get(root, 0) + 1
                kept.append(cid)
                if len(kept) >= beam:
                    break
            for cid in deferred:
                if len(kept) >= beam:
                    break
                kept.append(cid)
            return kept
        if mode == "floor":
            # A FLOOR, not a boost: if the beam holds no branch carrying canonical leaves and the
            # level does, the best such branch takes the beam's last slot. Width unchanged.
            kept = [cid for _s, cid in level[:beam]]
            floor_n = int(policy.get("floor", 1))
            have = [cid for cid in kept if self.canonical_share(cid) > 0]
            if len(have) >= floor_n:
                return kept
            spare = [cid for _s, cid in level[beam:] if self.canonical_share(cid) > 0]
            need = min(floor_n - len(have), len(spare))
            if not need:
                return kept
            return kept[:beam - need] + spare[:need]
        if mode == "widen":
            # THE FLOOR THAT DISPLACES NOTHING: the beam is taken as the incumbent takes it, and
            # THEN up to ``floor`` extra branches are admitted - the best-scoring ones carrying
            # canonical leaves, if the beam holds none. A derivative tree can no longer starve its
            # own source out of the descent, and nothing the incumbent would have entered is
            # dropped, so a query aimed AT the derivative tree keeps every hit it had.
            kept = [cid for _s, cid in level[:beam]]
            floor_n = int(policy.get("floor", 1))
            if sum(1 for cid in kept if self.canonical_share(cid) > 0) >= floor_n:
                return kept
            extra = [cid for _s, cid in level[beam:] if self.canonical_share(cid) > 0]
            return kept + extra[:floor_n]
        if mode == "canonical_boost":
            # The re-rank the WO names as cure (b), at the frontier where it can act: a cluster's
            # centroid score is lifted by ``weight`` times its canonical share.
            weight = float(policy.get("weight", 0.05))
            lifted = sorted(((s + weight * self.canonical_share(cid), cid) for s, cid in level),
                            key=lambda p: (-p[0], p[1]))
            return [cid for _s, cid in lifted[:beam]]
        if mode == "epsilon":
            # Adaptive width: enter every branch within ``epsilon`` cosine of the level's best,
            # capped at ``max_beam``. Pays materialization for near-ties only.
            eps = float(policy.get("epsilon", 0.03))
            cap = int(policy.get("max_beam", 3 * beam))
            best = level[0][0]
            kept = [cid for s, cid in level if s >= best - eps][:cap]
            return kept if len(kept) >= beam else [cid for _s, cid in level[:beam]]
        raise RecursiveReadError("select-policy-unknown",
                                 f"frontier policy {mode!r} is not one this descent implements")

    def centroid(self, cid: str):
        """A cluster's centroid as a unit float64 vector.

        Banked when the cluster has direct leaf members (``_build_tree_from_full`` writes it). A
        PURE-BRANCH cluster - children but no direct leaves - banks ``None`` by construction, and
        its centroid is DERIVED here: the leaf-count-weighted mean of its children's centroids,
        renormalized. That is the vector up-operator the design names as the cheap one (a mean); it
        reads only the tree, never a leaf. Derivation is recorded (``derived_centroids`` in the
        result), not hidden - a derived centroid is a real approximation and the caller can see how
        many the descent leaned on.

        Raises when a centroid can be neither read nor derived, or is the wrong dimension."""
        hit = self._centroid_cache.get(cid)
        if hit is not None:
            return hit
        np = self._np
        node = self.clusters.get(cid)
        if node is None:
            raise RecursiveReadError("cluster-unknown",
                                     f"{cid!r} is named in the parent map but absent from clusters")
        banked = node.get("centroid")
        if banked:
            vec = np.asarray(banked, dtype=np.float64)
            if vec.ndim != 1 or not np.all(np.isfinite(vec)):
                raise RecursiveReadError(
                    "centroid-malformed",
                    f"cluster {cid} banks a centroid of shape {vec.shape} with non-finite entries")
            norm = float(np.linalg.norm(vec))
            if norm == 0.0:
                raise RecursiveReadError("centroid-malformed",
                                         f"cluster {cid} banks a zero centroid")
            vec = vec / norm
        else:
            kids = self.cluster_children.get(cid, ())
            if not kids:
                raise RecursiveReadError(
                    "centroid-missing",
                    f"cluster {cid} banks no centroid and has no cluster children to derive one "
                    f"from - it is a dead branch, and a descent cannot score it")
            rows, weights = [], []
            for kid in kids:
                child = self.centroid(kid)
                # a ragged level cannot be averaged: numpy would raise an inhomogeneous-shape
                # ValueError from inside the mean, naming nothing. Name the offending child instead.
                if rows and child.shape != rows[0].shape:
                    raise RecursiveReadError(
                        "dimension-mismatch",
                        f"cluster {cid} cannot derive a centroid: child {kid} is dim "
                        f"{child.shape[0]} but its sibling is dim {rows[0].shape[0]} - the tree "
                        f"mixes geometries")
                rows.append(child)
                weights.append(max(1, self._leaf_count(kid)))
            mat = np.asarray(rows, dtype=np.float64)
            w = np.asarray(weights, dtype=np.float64)
            vec = (mat * w[:, None]).sum(axis=0) / w.sum()
            norm = float(np.linalg.norm(vec))
            if norm == 0.0:
                raise RecursiveReadError(
                    "centroid-malformed",
                    f"cluster {cid}'s derived centroid is zero - its children cancel exactly")
            vec = vec / norm
            self._derived_centroids.add(cid)
        self._centroid_cache[cid] = vec
        return vec

    # -- leaf vectors ------------------------------------------------------

    def _cache_put(self, name: str, vec: Any) -> None:
        self._vec_cache[name] = vec
        self._vec_cache.move_to_end(name)
        while len(self._vec_cache) > self.cache_cap:
            self._vec_cache.popitem(last=False)
            self.evictions += 1

    def materialize(self, names: list[str], stale: list[str], strict_staleness: bool) -> dict[str, Any]:
        """Recompute the vectors for ``names``, batched through the embedder, LRU-cached.

        Each name's source text is re-derived and content-hashed with the SAME ``_text_sha`` the
        deposit keys its cache by; a hash that disagrees with the tree's banked ``leaf_sha`` means
        the source changed since the fold. That leaf is re-embedded from its CURRENT text (which is
        the correct answer - the tree's membership is stale, its text is not) and its name is
        appended to ``stale`` so the caller reports it. ``strict_staleness`` turns that into a
        refusal instead. Either way it is never silent."""
        np = self._np
        out: dict[str, Any] = {}
        todo: list[str] = []
        for name in names:
            hit = self._vec_cache.get(name)
            if hit is not None:
                self._vec_cache.move_to_end(name)
                out[name] = hit
            else:
                todo.append(name)
        if not todo:
            return out
        texts = [self.leaf_source(name) for name in todo]
        banked_name = self.tree["version"]
        for name, text in zip(todo, texts, strict=True):
            if meaning_upfold._text_sha(banked_name, text) != self.leaf_sha.get(name):
                if strict_staleness:
                    raise RecursiveReadError(
                        "leaf-stale",
                        f"leaf {name!r} hashes differently than the tree's banked leaf_sha - its "
                        f"source changed since the fold, so the tree's membership for it is stale")
                stale.append(name)
        try:
            vecs = self.backend.embed(texts)
        except Exception as exc:  # noqa: BLE001 - an embedder that dies mid-descent is a refusal
            raise RecursiveReadError(
                "embed-failed",
                f"the embedder raised while materializing {len(todo)} leaf vector(s): "
                f"{type(exc).__name__}: {exc}") from exc
        if len(vecs) != len(todo):
            raise RecursiveReadError(
                "embed-shape",
                f"asked the embedder for {len(todo)} vectors and got {len(vecs)}")
        for name, raw in zip(todo, vecs, strict=True):
            vec = np.asarray(raw, dtype=np.float64)
            norm = float(np.linalg.norm(vec))
            if norm == 0.0 or not np.all(np.isfinite(vec)):
                raise RecursiveReadError(
                    "leaf-vector-malformed",
                    f"leaf {name!r} embedded to a zero or non-finite vector")
            vec = vec / norm
            self._cache_put(name, vec)
            out[name] = vec
        return out

    # -- the descent -------------------------------------------------------

    def descend(self, query_text: str, k: int = DEFAULT_K, beam: int = DEFAULT_BEAM,
                strict_staleness: bool = False, evict_after: bool = True,
                fire: str | None = None,
                select_policy: dict[str, Any] | None = None) -> dict[str, Any]:
        """Descend the tree for ``query_text`` and return the top ``k`` leaves.

        ``fire`` is VESTIGIAL and accepted only so the four live callers keep parsing. It was the
        closure meter's fire-class declaration; the bank seam at the tail of this method was cut
        (internals lane seq 1, cause walk-banked-not-verdict) because the store had 2,301 dutiful
        + 158 unattributed + 0 need rows at 60,101,446 B and zero readers - the whole walk banked,
        never a verdict. Nothing reads this argument now; it goes when ``closure_meter.py`` itself
        is retired.

        Level-synchronous beam, the shape ``embed_router.route`` already uses: score the level's
        clusters by cosine against their centroids, expand the top ``beam``, materialize the direct
        leaf members of every expanded cluster, and take the expanded clusters' cluster-children as
        the next level. The root's own direct leaves (if any) are always materialized - they are
        level zero and have no handle above them to prune on.

        ``select_policy`` overrides the ruled frontier policy (``SELECT_POLICY``) for this one call;
        ``{"mode": "beam"}`` is the incumbent top-``beam`` and reproduces every agreement number in
        the module header. Which policy ran is recorded in ``geometry["select"]`` - the ONE key
        added to the packet since the byte-identity note below was written, added deliberately:
        two hits lists can now differ for a reason no other field records, and a routing change the
        packet cannot name is exactly the silent degrade this module exists to refuse.

        The returned dict is the packet: ``hits`` (name, score, the cluster it hangs under, the
        descent path to it), ``visited`` clusters in expansion order, ``materialized`` count,
        ``stale`` leaves, ``derived_centroids``, the geometry, and wall-clock. Nothing here is a
        summary of something richer that was thrown away - it is what the descent did.

        NO METER RIDES THIS TAIL. The closure meter (T1) used to append one ~24 KB row per
        descend to ``.closure_meter.jsonl``; that seam is gone. The packet returned here is
        byte-identical either way - which was always the claim, and is now structural rather than
        tested, because there is no longer a second writer to diverge from. Two live callers
        (``scripts/reconstruction_bench.py``, ``scripts/bench_incumbent_live.py``) ``json.dumps``
        this whole packet INTO the context they then score atoms against, so a single extra key
        here would still move a benchmark's numbers."""
        np = self._np
        if k < 1:
            raise RecursiveReadError("bad-k", f"k must be >= 1, got {k}")
        if beam < 1:
            raise RecursiveReadError("bad-beam", f"beam must be >= 1, got {beam}")
        policy = dict(self.select_policy if select_policy is None else select_policy)
        t0 = time.perf_counter()
        try:
            qraw = self.backend.query(query_text)
        except Exception as exc:  # noqa: BLE001
            raise RecursiveReadError("query-embed-failed",
                                     f"{type(exc).__name__}: {exc}") from exc
        qv = np.asarray(qraw, dtype=np.float64)
        norm = float(np.linalg.norm(qv))
        if norm == 0.0 or not np.all(np.isfinite(qv)):
            raise RecursiveReadError("query-vector-malformed",
                                     f"query {query_text[:60]!r} embedded to a zero/non-finite vector")
        qv = qv / norm

        stale: list[str] = []
        scores: dict[str, float] = {}
        came_from: dict[str, str] = {}
        visited: list[str] = []
        cluster_score: dict[str, float] = {}

        def take_leaves(cid: str) -> None:
            leaves = self.leaf_children.get(cid, ())
            if not leaves:
                return
            vecs = self.materialize(list(leaves), stale, strict_staleness)
            for name, vec in vecs.items():
                if vec.shape != qv.shape:
                    raise RecursiveReadError(
                        "dimension-mismatch",
                        f"leaf {name!r} is dim {vec.shape[0]} but the query is dim {qv.shape[0]}")
                scores[name] = float(qv @ vec)
                came_from[name] = cid

        # closure-meter bookkeeping ONLY (T1): level widths and the level each cluster was scored
        # at. Two local writes, read by nothing above; the routing below is untouched by them.
        level_sizes: list[int] = []
        level_of: dict[str, int] = {}

        take_leaves(self.root_id)
        frontier = list(self.cluster_children.get(self.root_id, ()))
        depth = 0
        while frontier:
            level_sizes.append(len(frontier))
            level = []
            for cid in frontier:
                level_of[cid] = depth + 1
                cen = self.centroid(cid)
                if cen.shape != qv.shape:
                    raise RecursiveReadError(
                        "dimension-mismatch",
                        f"cluster {cid} centroid is dim {cen.shape[0]} but the query is dim "
                        f"{qv.shape[0]} - the tree was folded with a different geometry")
                s = float(qv @ cen)
                cluster_score[cid] = s
                level.append((s, cid))
            level.sort(key=lambda p: (-p[0], p[1]))
            kept = self.select_frontier(level, beam, policy)
            nxt: list[str] = []
            for cid in kept:
                visited.append(cid)
                take_leaves(cid)
                nxt.extend(self.cluster_children.get(cid, ()))
            frontier = nxt
            depth += 1

        if not scores:
            raise RecursiveReadError(
                "descent-empty",
                f"the descent for {query_text[:60]!r} reached no leaves at all "
                f"(beam={beam}, {len(visited)} cluster(s) visited) - an empty answer is a failure, "
                f"not a short list")

        ranked = sorted(scores.items(), key=lambda p: (-p[1], p[0]))[:k]
        hits = [{"id": name, "score": round(score, 6), "cluster": came_from[name],
                 "path": self._path_of(came_from[name])} for name, score in ranked]
        materialized = len(scores)
        packet = {
            "query": query_text, "axis": self.axis, "backend": self.backend.name,
            "tree_version": self.tree["version"], "lens_hash": self.tree.get("lens_hash"),
            "hits": hits,
            "visited": visited,
            "n_visited_clusters": len(visited),
            "n_clusters_total": len(self.clusters),
            "materialized": materialized,
            "n_leaves_total": len(self.leaf_sha),
            "derived_centroids": sorted(self._derived_centroids & set(cluster_score)),
            "stale": sorted(set(stale)),
            "evictions": self.evictions,
            "geometry": {"beam": int(beam), "k": int(k), "depth": depth,
                         "cache_cap": self.cache_cap, "evict_after": bool(evict_after),
                         "select": policy},
            "seconds": round(time.perf_counter() - t0, 4),
        }
        if stale:
            _emit(f"{len(set(stale))} leaf/leaves hashed stale against the tree's leaf_sha and were "
                  f"re-embedded from current source: {', '.join(sorted(set(stale))[:3])}"
                  f"{' ...' if len(set(stale)) > 3 else ''}")
        if evict_after:
            self._vec_cache.clear()

        return packet

    def _path_of(self, cid: str) -> list[str]:
        chain = [cid]
        seen = {cid}
        while chain[-1] in self.parent_map:
            parent = self.parent_map[chain[-1]]
            if not parent or parent in seen:
                break
            chain.append(parent)
            seen.add(parent)
        return chain


# ---------------------------------------------------------------------------
# opening - where every precondition is checked, once and loudly
# ---------------------------------------------------------------------------

def open_descender(repo_root: Path | str, backend: Any = None, leaf_source: LeafSource | None = None,
                   axis: str = SEMANTIC_AXIS, tree: dict[str, Any] | None = None,
                   cache_cap: int = DEFAULT_CACHE_CAP,
                   allow_test_backend: bool = False) -> Descender:
    """Open the banked concept tree for reading. Every precondition is a named refusal.

    ``allow_test_backend`` lets a deterministic in-process backend through the hash-router gate (the
    same seam ``tests/test_meaning_upfold_incremental.py`` uses); the embedder-vs-tree name check
    still applies, so a test backend needs a tree folded by that same test backend."""
    repo_root = Path(repo_root)
    if axis != SEMANTIC_AXIS:
        raise RecursiveReadError(
            "axis-unknown",
            f"axis {axis!r} has no banked tree - .meaning_tree.json is the {SEMANTIC_AXIS!r} "
            f"section (bge-small). A second axis is a second tree, not a flag on this one")
    if tree is None:
        tree_path = repo_root / meaning_upfold.TREE_FILE
        if not tree_path.is_file():
            raise RecursiveReadError(
                "tree-absent",
                f"{tree_path} is missing - there is no banked concept tree to descend. Run the "
                f"deposit (keeper.build_self) to fold one")
        tree = meaning_upfold.load_tree(repo_root)
        if tree is None:
            raise RecursiveReadError("tree-unreadable",
                                     f"{tree_path} exists but did not parse as JSON")
    missing = [key for key in ("clusters", "parent_map", "leaf_sha", "version")
               if key not in tree]
    if missing:
        raise RecursiveReadError(
            "tree-malformed",
            f"the concept tree is missing {', '.join(missing)} - it is not a tree this path can "
            f"descend")
    if not tree["clusters"]:
        raise RecursiveReadError("tree-empty",
                                 "the concept tree banks zero clusters - nothing to descend")

    if backend is None:
        from laplace.representation.embed_router import get_backend
        backend = get_backend()
    if backend is None:
        raise RecursiveReadError(
            "embedder-unavailable",
            "no embedding backend is available (fastembed absent, or the model could not load) - "
            "the read path recomputes leaf vectors and cannot run without one")
    name = getattr(backend, "name", "")
    if name.startswith("hash") and not allow_test_backend:
        raise RecursiveReadError(
            "embedder-not-semantic",
            f"the router returned {name!r} - the hash backend carries no semantics and must never "
            "be a routing fallback; a descent on it would rank noise")
    if name != tree["version"]:
        raise RecursiveReadError(
            "embedder-mismatch",
            f"the tree was folded by {tree['version']!r} but the live embedder is {name!r}. "
            "Re-embedding the leaves with a different model puts them in a different geometry than "
            "the centroids they are being scored against - this refuses rather than descends")

    if leaf_source is None:
        leaf_source = SelfGradedLeafSource(repo_root)
    return Descender(repo_root, tree, backend, leaf_source, axis=axis, cache_cap=cache_cap)


def descend(repo_root: Path | str, query_text: str, k: int = DEFAULT_K, beam: int = DEFAULT_BEAM,
            axis: str = SEMANTIC_AXIS, **kwargs: Any) -> dict[str, Any]:
    """One-shot convenience: open, descend, return the packet. Opening costs a ~19 MB JSON parse
    plus the model load, so a caller asking more than one question should hold a ``Descender``."""
    open_kwargs = {key: kwargs.pop(key) for key in
                   ("backend", "leaf_source", "tree", "cache_cap", "allow_test_backend")
                   if key in kwargs}
    dsc = open_descender(repo_root, axis=axis, **open_kwargs)
    return dsc.descend(query_text, k=k, beam=beam, **kwargs)
