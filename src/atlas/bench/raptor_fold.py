"""raptor_fold.py - building the RAPTOR tree and the prompts, and ingesting what came back.

RAPTOR (Sarthi et al., 2024) folds a corpus bottom-up: cluster the leaves, write a summary of each
cluster with a language model, cluster the summaries, summarize those, and at query time search a
COLLAPSED TREE - every summary and every leaf in one flat pool - rather than descending. This
module builds that structure over a frozen snapshot view and records what it cost.

WHAT IS FAITHFUL, AND WHAT IS AT-BUDGET. The version axis says ``raptor-at-budget/1`` and the
compromise is stated here rather than discovered by a reader:

  * FAITHFUL: bottom-up construction; a summary per cluster at every level; summaries embedded
    into the same space as the leaves; retrieval over the collapsed tree (summaries + leaves in
    one cosine pool) at the SAME k and read protocol as ``dense_flat``, so the comparison isolates
    the structure and not the budget.
  * AT BUDGET: the paper builds a tree over a few thousand chunks and summarizes every cluster.
    This view has 68,502 leaf spans. A faithful tree over it is tens of thousands of model calls,
    which is not a bill this session can pay honestly, so the TOTAL SUMMARY BUDGET is declared in
    advance (``TARGET_SUMMARIES``) and the clusters are correspondingly larger than the paper's -
    hundreds of spans per leaf cluster rather than a handful. That is a real difference and it
    cuts against RAPTOR: a summary of 228 spans is thinner evidence than a summary of 8. The
    number is declared so the reader can discount the result rather than be surprised by it.
  * PARITY CLASS, STATED: RAPTOR's published result used GPT-3.5-class summarizers. This uses
    claude sonnet, dispatched with an explicit model stamp. Parity-class, not identical; a
    stronger summarizer is a point in RAPTOR's favour here, not against it.

CLUSTER MEMBERSHIP IS NOT RE-EMBEDDED. The leaf vectors are the ones ``dense_flat`` already built
and banked (``atlas/stores/projections/<generation>/``), read by content hash exactly as that arm
reads them. RAPTOR pays for its summaries and for embedding those summaries, and it pays nothing
for the leaf geometry, because that geometry is already a banked artifact of another arm. Charging
it twice would inflate RAPTOR's fold bill and flatter every other arm.

THE SEAL, and the fingerprint expectation stated rather than assumed. Every character that
reaches a prompt comes from ``SnapshotView.span_text`` over ``view.leaf_spans``. A ``SnapshotView``
admits only nodes with ``not n.sealed and n.content_blob is not None``, so sealed nodes have no
spans in the view and cannot contribute a representative; ``_assert_unsealed_sources`` re-checks
that property against the bundle for every span actually used, so the guarantee is exercised on
the real inputs rather than argued from the type. The summaries are therefore derived text over
unsealed record, and banking them commits no sealed content - which is what makes
``summaries.jsonl`` a committable artifact.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from ..errors import ArmUnavailable
from ..ids import chash
from .cluster import BRANCH_MAX, SAMPLE_CAP, best_split
from .universe import SnapshotView

#: Identity of this fold recipe. ``at-budget`` is load-bearing - see the module docstring.
RAPTOR_RECIPE_VERSION = "raptor-at-budget/1"

#: THE DECLARED TOTAL SUMMARY BUDGET. Every non-root cluster gets exactly one summary, so this is
#: also the number of model-written texts the fold produces. Registered before the fold ran.
TARGET_SUMMARIES = 300

#: Levels below the root. The paper recurses until one cluster remains; at this budget three
#: levels already make the top-level clusters ~11,000 spans, and a fourth would summarize
#: summaries of summaries of summaries with nothing left to distinguish them.
MAX_DEPTH = 3

#: THE BRANCH BAND, and it is the second half of "at-budget". MEASURED FIRST: on this corpus the
#: unconstrained silhouette sweep over K in [2, 8] chooses K=2 at EVERY level, which at depth 3
#: yields 2 + 4 + 8 = 14 summaries - two orders of magnitude under the declared budget and far
#: coarser than anything RAPTOR describes. Dense text geometry has no clean elbow, so silhouette
#: reads the coarsest cut as the best one all the way down.
#:
#: The band's FLOOR is therefore arithmetic, not taste: three levels at branch b give b + b^2 + b^3
#: summaries, and b=6 gives 258, the smallest branch that clears the declared 250 floor. The
#: CEILING is the engine's own BRANCH_MAX. Silhouette still chooses - it chooses within [6, 8] -
#: and ``Split.unconstrained_k`` records what it would have chosen unbanded, so the size of this
#: override is a number in the fold record rather than a claim in a comment.
BRANCH_MIN = 6

#: A cluster smaller than this is not split further - a split of 12 spans into 8 clusters spends
#: eight summaries to say what one says.
MIN_SPLIT_SIZE = 24

#: How many members represent a cluster in its prompt, and how much of each. 12 x 700 chars is
#: ~8 KB of evidence per summary: enough for a summarizer to find the cluster's subject, bounded
#: enough that the fold's token bill stays a number rather than an estimate.
REPRESENTATIVES = 12
REPRESENTATIVE_CHARS = 700

#: Summaries per dispatched agent. The brief's band is 20-40; 25 puts the whole fold in 12
#: dispatches, each a prompt of ~100 KB, which is comfortably inside a single agent's context.
BATCH_SIZE = 25

#: The one legal summarizer stamp for this arm. EXPLICIT, never inherited (the dispatch-model law:
#: dispatched agents are opus-level or less). ``scripts/audit_dispatch_models.py`` enforces the
#: ceiling over the workflow scripts; this constant is the atlas-side literal it corresponds to.
SUMMARY_MODEL = "sonnet"

DEFAULT_STORE = Path(__file__).resolve().parents[3] / "atlas" / "stores" / "raptor"   # the container's stores (R2)


@dataclass
class Cluster:
    """One node of the RAPTOR tree. ``members`` are row indices into the view's leaf-span list."""

    cluster_id: str
    level: int
    parent_id: str | None
    members: np.ndarray
    children: list[str] = field(default_factory=list)
    silhouette: float | None = None
    split_k: int | None = None
    unconstrained_k: int | None = None
    representative_span_ids: list[str] = field(default_factory=list)

    @property
    def size(self) -> int:
        return int(len(self.members))

    def to_record(self) -> dict[str, Any]:
        return {
            "cluster_id": self.cluster_id, "level": self.level, "parent_id": self.parent_id,
            "size": self.size, "children": list(self.children),
            "silhouette": (None if self.silhouette is None else round(self.silhouette, 6)),
            "split_k": self.split_k,
            "unconstrained_k": self.unconstrained_k,
            "representative_span_ids": list(self.representative_span_ids),
        }


def fold_generation(view: SnapshotView, segmentation_id: str, projection_generation_id: str,
                    seed: int, target_summaries: int = TARGET_SUMMARIES,
                    max_depth: int = MAX_DEPTH) -> dict[str, Any]:
    """Every axis the fold depends on, in one record whose hash is the fold id.

    The UNIVERSE is part of this id, unlike the dense projection's - and the difference is the
    point. A vector is a property of one span and is shared across views; a TREE is a property of
    the SET of spans, so a tree folded over a view that contains the answer key is a different
    tree, with summaries that may quote it. Keying the fold by universe is what stops a control
    view's summaries from ever serving the headline.
    """
    return {
        "kind": "raptor-fold-generation/1",
        "recipe_version": RAPTOR_RECIPE_VERSION,
        "snapshot_id": view.snapshot_id,
        "segmentation_id": segmentation_id,
        "universe_id": view.universe_id,
        "universe": view.universe.name,
        "projection_generation_id": projection_generation_id,
        "seed": seed,
        "target_summaries": target_summaries,
        "max_depth": max_depth,
        "branch_max": BRANCH_MAX,
        "branch_min": BRANCH_MIN,
        "sample_cap": SAMPLE_CAP,
        "min_split_size": MIN_SPLIT_SIZE,
        "representatives": REPRESENTATIVES,
        "representative_chars": REPRESENTATIVE_CHARS,
        "summary_model": SUMMARY_MODEL,
    }


def build_tree(X: np.ndarray, seed: int, target_summaries: int = TARGET_SUMMARIES,
               max_depth: int = MAX_DEPTH) -> dict[str, Cluster]:
    """Recursive silhouette-spectral splitting under a HARD total-summary budget.

    Expansion is LARGEST-FIRST: at each step the biggest splittable cluster is split. That makes
    the budget bind where it buys the most - a 20,000-span cluster summarized as one paragraph is
    the fold's worst node - and it makes the tree's shape a function of the geometry and the seed
    rather than of a traversal order. Ties break on cluster id, which is a path, so the whole
    construction is deterministic.

    The budget is a CAP on the number of non-root clusters. Expansion stops when the next split
    would exceed it, so the fold never overspends the declared bill, and the achieved count is
    recorded rather than assumed to equal the target.
    """
    root = Cluster(cluster_id="r", level=0, parent_id=None,
                   members=np.arange(len(X), dtype=np.int64))
    clusters: dict[str, Cluster] = {"r": root}
    created = 0

    exhausted: set[str] = set()
    while True:
        candidates = [c for c in clusters.values()
                      if c.level < max_depth and not c.children
                      and c.size >= MIN_SPLIT_SIZE
                      and c.cluster_id not in exhausted]
        if not candidates:
            break
        candidates.sort(key=lambda c: (-c.size, c.cluster_id))
        target = candidates[0]
        split = best_split(X[target.members], seed=seed + target.level * 1000 + len(clusters),
                           branch_min=BRANCH_MIN)
        groups = [target.members[split.labels == j] for j in range(split.k)]
        groups = [g for g in groups if len(g)]
        if len(groups) < 2:
            # A cluster the split cannot separate is retired from candidacy by name, never by
            # mutating its level - a level is where a node IS, and moving it to dodge a loop
            # would corrupt the record the summaries are written against.
            exhausted.add(target.cluster_id)
            continue
        if created + len(groups) > target_summaries:
            # The budget binds. Retire this candidate and try the next-largest, which may be
            # small enough to fit - so the budget is SPENT rather than abandoned at the first
            # cluster too big for the remainder.
            exhausted.add(target.cluster_id)
            continue
        target.silhouette = split.silhouette
        target.split_k = int(split.k)
        target.unconstrained_k = int(split.unconstrained_k)
        for j, members in enumerate(groups):
            child_id = f"{target.cluster_id}.{j}"
            clusters[child_id] = Cluster(cluster_id=child_id, level=target.level + 1,
                                         parent_id=target.cluster_id, members=members)
            target.children.append(child_id)
            created += 1
    return clusters


def _assert_unsealed_sources(view: SnapshotView, span_ids: list[str]) -> None:
    """Re-check the seal on the spans that actually reach a prompt. Structural, then exercised.

    ``SnapshotView`` cannot admit a sealed node, so this can only fail if that invariant broke.
    That is exactly why it is checked here: the prompts leave the process and the summaries are
    banked, so this is the last place the guarantee is cheap to make and the first place its
    failure would be permanent.
    """
    for span_id in span_ids:
        span = view.span_by_id(span_id)
        if span is None:
            raise ArmUnavailable("a representative span is not in the view", span_id=span_id)
        node = view.bundle.nodes.get(span.node_id)
        if node is None or node.sealed or node.content_blob is None:
            raise ArmUnavailable(
                "a representative span resolves to a sealed or contentless node - a prompt would "
                "carry sealed material out of the process",
                span_id=span_id, node_id=span.node_id,
            )


def representatives(view: SnapshotView, X: np.ndarray, cluster: Cluster,
                    count: int = REPRESENTATIVES) -> list[tuple[str, str]]:
    """The ``count`` members closest to the cluster centroid, as ``(span_id, text)``.

    Centroid-nearest rather than random: a summary written from a random sample of a 10,000-span
    cluster describes the corpus, and a summary that describes the corpus retrieves nothing.
    """
    members = cluster.members
    sub = np.asarray(X[members], dtype=np.float32)
    centroid = sub.mean(axis=0)
    norm = float(np.linalg.norm(centroid))
    centroid = centroid / norm if norm > 1e-12 else centroid
    sims = sub @ centroid
    order = np.argsort(-sims, kind="stable")[:count]
    out: list[tuple[str, str]] = []
    for i in order:
        span = view.leaf_spans[int(members[int(i)])]
        text = view.span_text(span)[:REPRESENTATIVE_CHARS]
        out.append((span.span_id, text))
    return out


SYSTEM_INSTRUCTION = (
    "You are a corpus summarizer inside a retrieval benchmark. You will be given several "
    "CLUSTERS of related text excerpts drawn from a software project's records. For EACH "
    "cluster, write one dense paragraph of 60-110 words that states what that cluster is ABOUT: "
    "the specific subjects, named artifacts, identifiers, file names, dates and claims that "
    "distinguish it from the rest of the corpus. Write for retrieval, not for a reader: prefer "
    "concrete nouns and names over connective prose, never write 'this cluster contains', and "
    "never invent content that is not in the excerpts. "
    "Return ONLY a JSON array, no prose before or after, no markdown fence, of objects with "
    "exactly two keys: \"cluster_id\" (copied verbatim) and \"summary\" (your paragraph). "
    "Return one object per cluster given, in the order given."
)


def build_prompt(items: list[dict[str, Any]]) -> str:
    """One batch's prompt: the instruction, then each cluster's evidence under its id."""
    parts = [SYSTEM_INSTRUCTION, ""]
    for item in items:
        parts.append(f"=== CLUSTER {item['cluster_id']} "
                     f"(level {item['level']}, {item['size']} members) ===")
        for chunk in item["evidence"]:
            parts.append(chunk.strip())
            parts.append("---")
        parts.append("")
    parts.append(f"Return the JSON array now, with exactly {len(items)} objects.")
    return "\n".join(parts)


def summarization_order(clusters: dict[str, Cluster]) -> list[list[str]]:
    """Cluster ids grouped into LEVELS, deepest first - the bottom-up construction order.

    A cluster with children is summarized from its children's summaries, so its children must
    already exist. Grouping by level and walking deepest-first is the coarsest schedule that
    respects that, and it is what lets a whole level's batches be dispatched concurrently.
    """
    by_level: dict[int, list[str]] = {}
    for cid, cluster in clusters.items():
        if cluster.parent_id is None:
            continue                      # the root is the corpus; it gets no summary
        by_level.setdefault(cluster.level, []).append(cid)
    return [sorted(by_level[level]) for level in sorted(by_level, reverse=True)]


def batch_items(view: SnapshotView, X: np.ndarray, clusters: dict[str, Cluster],
                cluster_ids: list[str], summaries: dict[str, str]) -> list[dict[str, Any]]:
    """Evidence for one level's clusters: children's summaries if any, else member spans."""
    items: list[dict[str, Any]] = []
    for cid in cluster_ids:
        cluster = clusters[cid]
        if cluster.children:
            evidence = [f"[child {child}] {summaries[child]}" for child in cluster.children
                        if child in summaries]
        else:
            reps = representatives(view, X, cluster)
            _assert_unsealed_sources(view, [span_id for span_id, _ in reps])
            cluster.representative_span_ids = [span_id for span_id, _ in reps]
            evidence = [text for _, text in reps]
        items.append({"cluster_id": cid, "level": cluster.level, "size": cluster.size,
                      "evidence": evidence})
    return items


def fold_id_of(generation: dict[str, Any]) -> str:
    return chash(generation)


def store_dir(fold_id: str, store_root: Path | None = None) -> Path:
    root = Path(store_root) if store_root else DEFAULT_STORE
    return root / fold_id.split(":", 1)[-1]


def load_fold(fold_dir: Path) -> dict[str, Any]:
    """Load a banked fold: manifest + summaries. Raises rather than degrading to an empty tree."""
    fold_dir = Path(fold_dir)
    manifest_path, summaries_path = fold_dir / "manifest.json", fold_dir / "summaries.jsonl"
    if not manifest_path.is_file() or not summaries_path.is_file():
        raise ArmUnavailable(
            "the RAPTOR fold is not banked at this path - run atlas.tools.raptor_fold first. "
            "The arm never folds implicitly: a fold is a model bill, and a bill that can be "
            "incurred by running a benchmark is a bill nobody counted",
            fold_dir=str(fold_dir),
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in
            summaries_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {"manifest": manifest, "summaries": rows}
