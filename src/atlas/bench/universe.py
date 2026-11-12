"""universe.py - the bench corpus as a DECLARED FILTERED VIEW, and the reading boundary.

The author's ruling (``RW-20260801-bench-universe-ruled``, 2026-08-01): the bench corpus is a
declared filtered view over the whole snapshot - the snapshot itself stays the full record. The
exclusions are DATA, they are hashed into the task bundle's identity, and the FULL universe is
run as a control beside the filtered one so the exclusion is measured rather than hidden.

Two objects:

``UniverseSpec``  the exclusion list, with an id that is a hash of the list. Two specs with the
                  same exclusions are the same universe whatever they are called - except that
                  the name is hashed too, so a rename is visible rather than silent.
``SnapshotView``  ``(snapshot, segmentation, universe)`` resolved: the included node ids, the
                  included leaf spans in file order, and the ONLY legal way to turn a span into
                  text. Asking it for something the view excludes is ``UniverseViolation``, not
                  an empty string - a view that quietly serves what it excludes is not a view.

Three views are declared below, and the reason there are three rather than two is a measurement:
``RULED_ONLY`` is the author's ruling exactly, ``BENCH_FILTERED`` adds one DERIVED exclusion, and
``FULL_UNIVERSE`` excludes nothing. Running all three is what turns both exclusions into numbers.

A note on the glob syntax, because it changes which nodes are in the corpus. Patterns are matched
with ``fnmatch`` over the whole node id, where ``*`` DOES cross ``/``. So the ruling's
``corpus_stores/*/embeddings.json`` also excludes the one nested cache
(``corpus_stores/voice_corpus_cache/exemplar_passages/embeddings.json``). That is the ruling's
intent - derived vector caches, all of them - and it is written here because the alternative
reading would leave a 400 KB vector dump in a corpus the ruling says has none.

Node text is decoded once per node and held. At repo scale that is ~80 MB of str for the filtered
view - cheap against the alternative, which is re-decoding the same node for every span an arm
reads and making the cost numbers a function of read order.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from typing import Any

from ..errors import UniverseViolation
from ..ids import chash, hash_bytes
from ..schema import Span
from ..snapshot import SnapshotBundle


@dataclass(frozen=True)
class UniverseSpec:
    """Which of a snapshot's nodes the bench may see. The exclusions are the definition."""

    SCHEMA_VERSION = "bench-universe/1"

    name: str
    exclude_prefixes: tuple[str, ...] = ()
    exclude_globs: tuple[str, ...] = ()
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "name": self.name,
            "exclude_prefixes": list(self.exclude_prefixes),
            "exclude_globs": list(self.exclude_globs),
            "reason": self.reason,
        }

    def hashed_dict(self) -> dict[str, Any]:
        """The identity of a universe is its name and its exclusions. Prose is not identity."""
        d = self.to_dict()
        d.pop("reason", None)
        return d

    @property
    def universe_id(self) -> str:
        return chash(self.hashed_dict())

    def excludes(self, node_id: str) -> bool:
        if node_id.startswith(self.exclude_prefixes):
            return True
        return any(fnmatchcase(node_id, g) for g in self.exclude_globs)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "UniverseSpec":
        return cls(
            name=d["name"],
            exclude_prefixes=tuple(d.get("exclude_prefixes", ())),
            exclude_globs=tuple(d.get("exclude_globs", ())),
            reason=d.get("reason", ""),
        )


#: THE AUTHOR'S RULING, EXACTLY. Three families: vendored code, minified static bundles, derived
#: vector caches. ``atlas/stores/`` is already outside the snapshot (the exporter excludes it) and
#: is declared anyway, so the bench's universe reads as a complete statement rather than as a
#: delta against the exporter's. This spec is kept as its own view because the ground-truth
#: exclusion below is DERIVED and not his, and a derived exclusion that cannot be measured
#: against the ruled one is an unmeasured change to the corpus.
RULED_ONLY = UniverseSpec(
    name="ruled-only/1",
    exclude_prefixes=(
        "node_modules/",
        "src/laplace/static_shared/",
        "atlas/stores/",
    ),
    exclude_globs=(
        "corpus_stores/*/embeddings.json",
        "*.npz",
    ),
    reason=(
        "RW-20260801-bench-universe-ruled, exactly as ruled: vendored code, minified static "
        "bundles and derived vector caches are not record. Kept as a view of its own so the "
        "derived ground-truth exclusion can be measured against it rather than assumed."
    ),
)

#: THE GROUND-TRUTH FAMILY - a DERIVED exclusion, recorded here as a decision, not smuggled.
#:
#: Measured 2026-08-01 during the Phase 2 shake-out run: ``scripts/reconstruction_bench_tasks.json``
#: is the v1 benchmark's ANSWER KEY - it pairs each question with its must-atoms - and it sits in
#: the corpus at an ordinary path. BM25 retrieved spans of that file as its top hits on twelve of
#: twenty-one tasks and read the answers straight out of it. A score obtained that way measures
#: "can this arm find the answer key", not "can this arm reconstruct the record", and every arm
#: that reaches the file inherits the same defect.
#:
#: The exclusion is derived per the fork law (derive it, decide it, record it): it follows from
#: banked evidence rather than from taste, and the alternative - serving a number known to be
#: contaminated - is not available. It is NOT the author's ruling, so it does not go in
#: RULED_ONLY, and the two views are run side by side so the size of the contamination is a
#: measured number in the results table.
#:
#: The v1 EVIDENCE bundle is deliberately NOT excluded: ``evidence/reconstruction_bench_2026-07-28/``
#: carries findings in prose - it is where the corrected multiple actually lives, and one task's
#: correct answer is that prose. Its ``rows.json`` was checked and carries no atoms. Excluding
#: genuine record because it sits near an answer key would be the over-reach this list avoids.
GROUND_TRUTH_PREFIXES = ("atlas/bench/tasks/", "atlas/tests/fixtures/")
GROUND_TRUTH_PATHS = ("scripts/reconstruction_bench_tasks.json",)

BENCH_FILTERED = UniverseSpec(
    name="bench-filtered/2",
    exclude_prefixes=RULED_ONLY.exclude_prefixes + GROUND_TRUTH_PREFIXES,
    exclude_globs=RULED_ONLY.exclude_globs + GROUND_TRUTH_PATHS,
    reason=(
        "RW-20260801-bench-universe-ruled's three families, plus the DERIVED fourth family: the "
        "benchmark's own ground truth. Measured contamination, not a precaution - see "
        "GROUND_TRUTH_PATHS. Run beside ruled-only/1 and full/1 so both exclusions are measured."
    ),
)

#: The control. A view is (snapshot, universe); the FULL universe is a view like any other, with
#: an empty exclusion list, so the control run uses the same code path and not a special case.
FULL_UNIVERSE = UniverseSpec(
    name="full/1",
    exclude_prefixes=(),
    exclude_globs=(),
    reason="the full-universe control: every unsealed span of the snapshot, exclusions empty.",
)


@dataclass
class PlantedSpan:
    """A synthetic span injected into a COPY of a view - never into the snapshot.

    The planted-bad control (design §6). ``text`` carries a plausible-but-WRONG answer to a named
    task; if an arm retrieves it at rank <= k on that task's question, that is a scored false
    positive. ``planted_id`` starts with ``planted:`` so no reader can mistake it for a span
    hash of the record.
    """

    planted_id: str
    node_id: str
    text: str
    targets_task: str
    wrong_atoms: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "planted_id": self.planted_id, "node_id": self.node_id, "text": self.text,
            "targets_task": self.targets_task, "wrong_atoms": list(self.wrong_atoms),
        }


class SnapshotView:
    """One (snapshot, universe) pair, resolved. The only legal source of text for an arm."""

    def __init__(self, bundle: SnapshotBundle, universe: UniverseSpec,
                 planted: list[PlantedSpan] | None = None) -> None:
        self.bundle = bundle
        self.universe = universe
        self.planted = list(planted or [])
        self._node_bytes: dict[str, bytes] = {}
        self._node_text: dict[str, str] = {}
        self._norm_node: dict[str, str] = {}
        self._planted_by_id = {p.planted_id: p for p in self.planted}

        self.node_ids: list[str] = sorted(
            n.node_id for n in bundle.nodes.values()
            if not n.sealed and n.content_blob is not None and not universe.excludes(n.node_id)
        )
        self._included = set(self.node_ids)

        spans: list[Span] = []
        by_node: dict[str, list[Span]] = {}
        if bundle.has_spans():
            for span in bundle.iter_spans():
                if span.is_leaf and span.node_id in self._included:
                    spans.append(span)
                    by_node.setdefault(span.node_id, []).append(span)
        self.leaf_spans: list[Span] = spans
        self._span_by_id = {s.span_id: s for s in spans}
        self._spans_by_node = by_node

    # --- identity ---------------------------------------------------------

    @property
    def snapshot_id(self) -> str:
        return self.bundle.manifest.snapshot_id

    @property
    def universe_id(self) -> str:
        return self.universe.universe_id

    def stats(self) -> dict[str, Any]:
        """What the view actually resolved to. Reported in every run manifest."""
        total_nodes = sum(1 for n in self.bundle.nodes.values()
                          if not n.sealed and n.content_blob is not None)
        return {
            "universe": self.universe.name,
            "universe_id": self.universe_id,
            "text_nodes_in_snapshot": total_nodes,
            "nodes_included": len(self.node_ids),
            "nodes_excluded": total_nodes - len(self.node_ids),
            "leaf_spans_included": len(self.leaf_spans),
            "leaf_bytes_included": sum(s.end - s.start for s in self.leaf_spans),
            "planted_spans": len(self.planted),
        }

    # --- reading ----------------------------------------------------------

    def node_bytes(self, node_id: str) -> bytes:
        """The immutable bytes of one included node, cached. An excluded node refuses by name.

        Cached deliberately. ``SnapshotBundle.read_node_bytes`` re-reads the blob and re-hashes it
        on every call - correct for a verify pass and ruinous for a bench that reads the same node
        for tens of thousands of spans. The verify still happens: once, on the first read.
        """
        if node_id not in self._included:
            raise UniverseViolation("node is outside the declared view",
                                    node_id=node_id, universe=self.universe.name)
        cached = self._node_bytes.get(node_id)
        if cached is None:
            cached = self.bundle.read_node_bytes(node_id)
            self._node_bytes[node_id] = cached
        return cached

    def node_text(self, node_id: str) -> str:
        """The decoded bytes of one included node. An excluded node is a named refusal."""
        cached = self._node_text.get(node_id)
        if cached is None:
            cached = self.node_bytes(node_id).decode("utf-8", errors="replace")
            self._node_text[node_id] = cached
        return cached

    def normalized_node_text(self, node_id: str) -> str:
        """The node's text through the shared normalizer, cached. Used to LOCATE atoms cheaply.

        Anchoring an atom means finding the leaf span that holds it, and scanning every span of a
        68,000-span view for every atom would normalize the corpus dozens of times over. Locating
        the candidate NODES first, then scanning only their spans, gives the same answer for one
        normalization pass. It cannot give a different one: a span's text is a substring of its
        node's, and the normalizer is applied to both.
        """
        cached = self._norm_node.get(node_id)
        if cached is None:
            from .scoring import normalize
            cached = normalize(self.node_text(node_id))
            self._norm_node[node_id] = cached
        return cached

    def span_text(self, span: Span) -> str:
        """The text of one leaf span. Byte offsets index the node's BYTES, so slice bytes."""
        planted = self._planted_by_id.get(span.span_id)
        if planted is not None:
            return planted.text
        return self.span_bytes(span).decode("utf-8", errors="replace")

    def span_bytes(self, span: Span) -> bytes:
        planted = self._planted_by_id.get(span.span_id)
        if planted is not None:
            return planted.text.encode("utf-8")
        if span.node_id not in self._included:
            raise UniverseViolation("span is outside the declared view",
                                    span_id=span.span_id, node_id=span.node_id,
                                    universe=self.universe.name)
        return self.node_bytes(span.node_id)[span.start:span.end]

    def span_content_hash(self, span: Span) -> str:
        """The hash of THIS SPAN'S bytes - the anchor identity, and the decay detector.

        Distinct from ``Span.source_content_hash``, which hashes the whole node. A task anchored
        to a span content hash detects a change to the span's own text even when the file around
        it is otherwise unrecognisable.
        """
        return hash_bytes(self.span_bytes(span))

    def span_by_id(self, span_id: str) -> Span | None:
        return self._span_by_id.get(span_id)

    def spans_of_node(self, node_id: str) -> list[Span]:
        return list(self._spans_by_node.get(node_id, ()))

    def has_node(self, node_id: str) -> bool:
        return node_id in self._included


def with_planted(view: SnapshotView, planted: list[PlantedSpan]) -> SnapshotView:
    """A COPY of ``view`` carrying synthetic spans. The snapshot on disk is never touched.

    The planted spans are appended to the leaf-span list with synthetic ``Span`` records whose
    ids are the planted ids. They belong to a node id that is already in the view, so nothing
    downstream has to special-case their provenance - only their id says they are synthetic.
    """
    copy = SnapshotView(view.bundle, view.universe, planted=planted)
    synthetic: list[Span] = []
    for p in planted:
        synthetic.append(Span(
            span_id=p.planted_id, node_id=p.node_id,
            source_content_hash="planted", segmenter_id="planted/1", seg_version="planted/1",
            start=0, end=len(p.text.encode("utf-8")),
            est_tokens=(len(p.text.encode("utf-8")) + 3) // 4,
            is_leaf=True, parent_span=None, kind="planted",
            trail=["planted-bad control"], meta={"targets_task": p.targets_task},
        ))
    copy.leaf_spans = copy.leaf_spans + synthetic
    copy._span_by_id.update({s.span_id: s for s in synthetic})
    return copy
