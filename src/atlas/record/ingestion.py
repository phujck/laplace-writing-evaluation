"""ingestion.py - level 0 of the conceptric, assembled, plus B.28's cache and B.29's touched set.

An ``Ingestion`` holds the five things every later piece reads: the blob store, the span table,
the typed row store, the relation table and the anchor index. It is built by a dataset module
under ``atlas.record.ingest`` and is the only object those modules return.

O(diff), which is the whole reason the parts are append-only. Inserting one item touches, in
B.29's words: its own spans, rows and relations; the carrier neighbourhood N(x); the degree of
each row in N(x); the component labels those rows carry; and the sections whose members meet the
touched set (sections are lane A's, so this layer reports the set rather than re-testing). The
realised touched count is ``1 + |N(x)|`` and it is COUNTED here rather than asserted.

An unchanged input re-mints nothing, and that is a property of two mechanisms rather than a
promise: the blob store is content-addressed, so the same bytes return the same handle without a
second write; and the per-item extraction cache is keyed on
``chash({source_content_hash, item_span, extractor_id, dataset_declaration_hash})`` - B.28's key
exactly, with no generation id, no fibre id, no corpus-level hash and no clock, which is what
makes the hit byte-identical rather than merely likely.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator, Mapping, Sequence

import numpy as np
import torch

from ..ids import chash, hash_bytes
from .anchor_index import AnchorIndex
from .content_blob import ContentBlobStore
from .declaration import DatasetDeclaration
from .device import peak_device_bytes, require_device, reset_peak_device_bytes
from .relation_table import RelationTable
from .spans import SpanTable
from .typed_row_store import TypedRowStore
from .witness import WitnessCandidate, check_candidates

__all__ = ["Ingestion", "TouchedSet", "ItemCache", "ItemMark", "item_cache_key"]


def item_cache_key(source_content_hash: str, item_span: tuple[int, int], extractor_id: str,
                   dataset_declaration_hash: str) -> str:
    """B.28's per-item cache key, with exactly B.28's field set and nothing else."""
    return chash({"source_content_hash": source_content_hash,
                  "item_span": [int(item_span[0]), int(item_span[1])],
                  "extractor_id": extractor_id,
                  "dataset_declaration_hash": dataset_declaration_hash})


class ItemCache:
    """The per-item content-addressed extraction cache. A hit returns the item's rows verbatim.

    THE CACHE IS THE SEGMENT STORE. ``attach`` gives this cache the persisted index
    ``item_cache_key -> segment key`` (``record.segments.SegmentStore.cache_index``), so a hit
    survives the process that produced it: an item whose bytes have been ingested before is
    answered from its segment and is never parsed or extracted again. Without the backing the
    cache is what it always was - a dict that dies with the process, which is why every run
    before this one re-ingested everything.
    """

    def __init__(self, backing: Mapping[str, str] | None = None) -> None:
        self._entries: dict[str, Any] = {}
        self._backing: Mapping[str, str] = backing or {}
        self.hits = 0
        self.misses = 0

    def attach(self, backing: Mapping[str, str]) -> None:
        """Back this cache with a persisted ``item_cache_key -> segment key`` index. O(1)."""
        self._backing = backing

    def get(self, key: str) -> Any | None:
        found = self._entries.get(key)
        if found is None:
            segment = self._backing.get(key)
            found = None if segment is None else {"segment_key": segment}
        if found is None:
            self.misses += 1
        else:
            self.hits += 1
        return found

    def put(self, key: str, value: Any) -> None:
        self._entries[key] = value

    def __len__(self) -> int:
        return len(self._entries)


@dataclass(frozen=True, slots=True)
class ItemMark:
    """Exactly what ONE item put into this ingestion: its blob, its spans, its rows.

    Every part of the record is append-only, so an item's contribution is a contiguous RANGE in
    each table rather than a set of ordinals - which is what makes cutting a per-item segment a
    slice and not a search. The mark is recorded by ``Ingestion.item`` around the ingester's own
    per-item call, and is the only new thing an ingester has to say.
    """

    item_cache_key: str
    item_content_hash: str
    item_span: tuple[int, int]
    blob_handles: tuple[str, ...]
    span_range: tuple[int, int]
    row_ranges: tuple[tuple[str, int, int], ...]     # (kind, local lo, local hi)
    extracted: bool

    def as_dict(self) -> dict[str, Any]:
        return {"item_cache_key": self.item_cache_key,
                "item_content_hash": self.item_content_hash,
                "item_span": list(self.item_span), "blobs": list(self.blob_handles),
                "spans": self.span_range[1] - self.span_range[0],
                "rows": sum(hi - lo for _, lo, hi in self.row_ranges),
                "extracted": self.extracted}


@dataclass(slots=True)
class TouchedSet:
    """B.29: exactly what one diff touched. Empty means the input was unchanged."""

    blobs: tuple[str, ...] = ()
    span_ordinals: tuple[int, ...] = ()
    row_ordinals: tuple[int, ...] = ()
    neighbour_ordinals: tuple[int, ...] = ()
    edges: dict[str, int] = field(default_factory=dict)
    posting_surfaces: tuple[str, ...] = ()
    cache_hit: bool = False

    @property
    def touched_count(self) -> int:
        """``1 + |N(x)|`` for a single item, per B.29's realised count."""
        return len(self.row_ordinals) + len(self.neighbour_ordinals)

    def to_dict(self) -> dict[str, Any]:
        return {"blobs": list(self.blobs), "spans": len(self.span_ordinals),
                "rows": len(self.row_ordinals), "neighbours": len(self.neighbour_ordinals),
                "edges": dict(self.edges), "postings": len(self.posting_surfaces),
                "touched_count": self.touched_count, "cache_hit": self.cache_hit,
                "row_ordinals": list(self.row_ordinals),
                "posting_surfaces": list(self.posting_surfaces)}


class Ingestion:
    """Level 0 of the conceptric for one dataset: blobs, spans, rows, relations, anchors."""

    def __init__(self, declaration: DatasetDeclaration,
                 device: torch.device | str | None = None) -> None:
        self.declaration = declaration
        self.device = require_device(device)
        self.blobs = ContentBlobStore()
        self.spans = SpanTable(declaration.segmenter_id, declaration.seg_version, self.device)
        self.store = TypedRowStore(declaration, self.blobs, self.spans, self.device)
        self.relations = RelationTable(declaration.relation_kinds, self.device)
        self.anchors: AnchorIndex | None = None
        self.cache = ItemCache()
        self.timings: dict[str, float] = {}
        self.counters: dict[str, int] = {}
        self.coverage: dict[str, Any] = {"not_admitted": [], "dangling_by_field": {},
                                         "absent_by_field": {}}
        # Staging for edges whose witness is a LOCATED occurrence rather than a declared field:
        # the extraction pass records where each admitted row's surface was found, and the
        # relation pass turns those ranges into edges once every row of the item exists. Held on
        # the ingestion rather than in a module global so two ingestions never share a buffer.
        self.pending_edges: dict[str, list[tuple[str, int, list[tuple[int, int]]]]] = {}
        self.pending_labels: list[tuple[Any, ...]] = []
        # What this ingestion can persist and what it can skip: one mark per item actually
        # parsed, and one deferral per item answered from the segment store instead.
        self.item_marks: list[ItemMark] = []
        self.deferred_segments: list[tuple[str, str]] = []      # (item cache key, segment key)
        # THE CONTENT LEAVES, when the declaration declares an axis (``record.content``). It is
        # NOT a typed row table and never becomes one: B.6 forbids a record row to carry an
        # embedding, so the vectors and the token codes sit beside the rows, addressed by the
        # span they observe and pointing DOWN at the carrier row. ``None`` is the ablation's OFF
        # position and is what every declaration without a content axis leaves here.
        self.content: Any = None
        self.persistence: Any = None       # the IngestReceipt, when this ingest had a store
        self.counters["item_parses"] = 0
        self.counters["extractions"] = 0
        self.counters["segment_hits"] = 0
        # The allocator's high-water mark is per PROCESS, so an ingestion built after another
        # one inherits its peak and reports a number no work of its own produced (measured
        # 2026-09-22: a 20-paper QASPER ingest reported 605,995,008 peak bytes because a
        # 100-haystack LongMemEval ingest had run first in the same process). The mark is zeroed
        # here, BEFORE anything is built, so every receipt's peak is this ingestion's own.
        reset_peak_device_bytes(self.device)

    # ---------------------------------------------------------------- items
    @contextmanager
    def item(self, item_cache_key: str, *, item_bytes: bytes,
             blob_handles: Sequence[str], extracts: bool = False) -> Iterator[None]:
        """Record what one item contributes, around the ingester's own per-item call.

        The two counters it keeps are the ones the persistence receipt is judged on: an item
        parsed and (when the rung is on) an item extracted. A run that reports zero of both and
        a complete store read the store instead of the source. Complexity: O(kinds).
        """
        before_spans = len(self.spans)
        before_rows = {kind: len(table) for kind, table in self.store.tables.items()}
        self.counters["item_parses"] += 1
        if extracts:
            self.counters["extractions"] += 1
        try:
            yield
        finally:
            self.item_marks.append(ItemMark(
                item_cache_key=item_cache_key,
                item_content_hash=hash_bytes(item_bytes),
                item_span=(0, len(item_bytes)),
                blob_handles=tuple(blob_handles),
                span_range=(before_spans, len(self.spans)),
                row_ranges=tuple((kind, before_rows[kind], len(table))
                                 for kind, table in self.store.tables.items()
                                 if len(table) > before_rows[kind]),
                extracted=extracts))

    def defer_segment(self, item_cache_key: str, segment_key: str) -> None:
        """This item is already in the segment store: it is adopted, never parsed. O(1)."""
        self.deferred_segments.append((item_cache_key, segment_key))
        self.counters["segment_hits"] += 1

    # ---------------------------------------------------------------- building
    def add_span(self, content_handle: str, start: int, end: int) -> int:
        blob_ord = self.spans.blob_ordinal(content_handle)
        return int(self.spans.append([blob_ord], [start], [end])[0])

    def add_spans(self, content_handle: str, ranges: Sequence[tuple[int, int]]) -> torch.Tensor:
        blob_ord = self.spans.blob_ordinal(content_handle)
        return self.spans.append([blob_ord] * len(ranges), [r[0] for r in ranges],
                                 [r[1] for r in ranges])

    def append_relations(self, kind: str, src: Sequence[int], dst: Sequence[int],
                         witness_spans: Sequence[Sequence[int]], *,
                         contexts: Sequence[Mapping[str, Any]] | None = None,
                         witness_options: Mapping[str, Any] | None = None,
                         extractor_id: str = "") -> torch.Tensor:
        """Check every proposed edge against its witness, then admit the ones that pass (B.4).

        Same fail-closed rule as a row: a False verdict is a refused proposal in the receipt,
        never a weaker edge. Complexity: O(k) plus the predicate's O(witness bytes).
        """
        spec = self.declaration.relation_kind(kind)
        contexts = contexts if contexts is not None else [{}] * len(src)
        candidates = [WitnessCandidate(fields={}, spans=tuple(int(s) for s in spans),
                                       context=context)
                      for spans, context in zip(witness_spans, contexts)]
        verdicts = check_candidates(spec.witness_predicate_id, self.blobs, self.spans,
                                    candidates, witness_options)
        keep_src, keep_dst, keep_spans = [], [], []
        for i, verdict in enumerate(verdicts):
            if verdict:
                keep_src.append(int(src[i]))
                keep_dst.append(int(dst[i]))
                keep_spans.append(tuple(int(s) for s in witness_spans[i]))
            else:
                self.relations.refused.append({
                    "kind": kind, "extractor_id": extractor_id, "rung": spec.rung,
                    "predicate_id": spec.witness_predicate_id,
                    "src": int(src[i]), "dst": int(dst[i])})
        return self.relations.kind(kind).append(keep_src, keep_dst, keep_spans)

    def build_anchors(self, rung: int = 0) -> AnchorIndex:
        started = time.perf_counter()
        self.anchors = AnchorIndex.build(self.store, self.declaration, rung=rung)
        self.timings["anchor_index_s"] = time.perf_counter() - started
        return self.anchors

    # ---------------------------------------------------------------- diffing
    def neighbourhood(self, row_ordinals: Sequence[int]) -> torch.Tensor:
        """N(x): every row reachable in one hop over any counted relation kind. O(sum degrees)."""
        if not len(row_ordinals):
            return torch.empty(0, dtype=torch.int64, device=self.device)
        seeds = torch.tensor(list(row_ordinals), dtype=torch.int64, device=self.device)
        rows = max(self.store.row_count, 1)
        found = [torch.empty(0, dtype=torch.int64, device=self.device)]
        for table in self.relations.kinds.values():       # closed set of kinds, not of edges
            if len(table) == 0:
                continue
            found.append(table.neighbours(seeds, rows))
            found.append(table.neighbours_in(seeds, rows))
        reached = torch.unique(torch.cat(found))
        return reached[~torch.isin(reached, seeds)]

    def mint_located_edges(self, relation: str, container_kind: str, *,
                           carrier_is_source: bool = True, extractor_id: str = "") -> int:
        """Turn the staged located ranges of ``relation`` into edges against container rows.

        A rung-(b) carrier - an entity, a quantity, a citation, an event - is minted from a
        surface LOCATED at a byte range, and the edge it earns is to the container row whose own
        byte range contains that address. Finding that container is a containment lookup, done
        here by bisection over one sorted interval table per blob rather than by a scan over
        containers per occurrence: O(k log C) for k occurrences and C containers.

        The witness tuple of every minted edge is (the located range, the container's witness),
        so ``spans_nest@v1`` re-reads the addresses and refuses an edge whose surface does not
        actually lie inside the container it claims. Returns the number of edges offered.

        The bisection is ONE ``np.searchsorted`` per blob over that blob's sorted container
        table, and the accepted occurrences of a blob become spans in ONE append. The earlier
        form asked the same question per occurrence: measured 2026-09-22 on three LongMemEval
        haystacks, ``SpanTable.append`` was entered 20,857 times - two device allocations each -
        and the profiler put 20.8% of the whole ingest inside per-element tensor construction.
        The containment rule and its tie-break (among containers with the same start, the one
        with the largest end, then the largest local ordinal) are the sort key here, unchanged.
        """
        pending = self.pending_edges.get(relation, [])
        if not pending:
            return 0
        table = self.store.table(container_kind)
        if not len(table):
            return 0

        # --- the containers, as ONE host image, sorted by (blob, start, end, local ordinal)
        columns = self.spans.columns.cpu().numpy()
        witness = table.witness_span.cpu().numpy().astype(np.int64, copy=False)
        global_ordinals = table.global_ordinals.cpu().numpy().astype(np.int64, copy=False)
        c_blob, c_lo, c_hi = columns[witness, 0], columns[witness, 1], columns[witness, 2]
        c_local = np.arange(witness.size, dtype=np.int64)
        c_order = np.lexsort((c_local, c_hi, c_lo, c_blob))
        c_blob, c_lo, c_hi, c_local = (c_blob[c_order], c_lo[c_order],
                                       c_hi[c_order], c_local[c_order])

        # --- the staged occurrences, flattened once: one row per located range
        blob_of_handle = {handle: self.spans.blob_ordinal(handle)
                          for handle, _, _ in pending}
        flat = [(blob_of_handle[handle], start, end, row_ordinal)
                for handle, row_ordinal, ranges in pending for start, end in ranges]
        if not flat:
            return 0
        occurrence = np.array(flat, dtype=np.int64)
        occ_blob, occ_lo, occ_hi, occ_carrier = (occurrence[:, 0], occurrence[:, 1],
                                                 occurrence[:, 2], occurrence[:, 3])
        o_order = np.argsort(occ_blob, kind="stable")
        o_blob = occ_blob[o_order]

        taken_occurrences: list[np.ndarray] = []
        taken_containers: list[np.ndarray] = []
        taken_located: list[np.ndarray] = []
        for blob in np.unique(o_blob):  # loop-ok: one step per BLOB (one item's bytes); whole-array inside
            o0 = int(np.searchsorted(o_blob, blob, "left"))
            o1 = int(np.searchsorted(o_blob, blob, "right"))
            c0 = int(np.searchsorted(c_blob, blob, "left"))
            c1 = int(np.searchsorted(c_blob, blob, "right"))
            if c1 <= c0:
                continue
            here = o_order[o0:o1]
            index = np.searchsorted(c_lo[c0:c1], occ_lo[here], side="right") - 1
            inside = index >= 0
            container = c0 + np.where(inside, index, 0)
            inside &= (c_lo[container] <= occ_lo[here]) & (occ_hi[here] <= c_hi[container])
            here, container = here[inside], container[inside]
            if not here.size:
                continue
            ordinals = self.add_spans(self.spans.handle(int(blob)),
                                      list(zip(occ_lo[here].tolist(), occ_hi[here].tolist())))
            taken_occurrences.append(here)
            taken_containers.append(container)
            taken_located.append(ordinals.cpu().numpy())
        if not taken_occurrences:
            return 0

        occurrences = np.concatenate(taken_occurrences)
        containers = np.concatenate(taken_containers)
        located = np.concatenate(taken_located)
        carrier = occ_carrier[occurrences]
        container_rows = global_ordinals[c_local[containers]]
        source = carrier if carrier_is_source else container_rows
        target = container_rows if carrier_is_source else carrier
        self.append_relations(
            relation, source.tolist(), target.tolist(),
            list(zip(located.tolist(), witness[c_local[containers]].tolist())),
            extractor_id=extractor_id, witness_options={"relation": "inside"})
        return int(occurrences.size)

    def bound_B_of_x(self, item_local_endpoints: int, kind: str) -> int:
        """B.29's byte-computable bound ``B(x) = 1 + L(x) + S(kind(x))``.

        ``item_local_endpoints`` is L(x): the number of distinct endpoints of the relation
        instances the per-item extraction emits for x, ALL of whose witness spans lie inside x's
        own item span - counted over x's bytes alone, with no store lookup. ``S(kind)`` is the
        declared structural arity of the kind under the segmenter, read off the DECLARATION
        rather than chosen: it is the number of declared relation kinds whose source kind is
        ``kind`` and whose witness predicate is structural. Complexity: O(declared kinds).
        """
        structural = sum(1 for spec in self.declaration.relation_kinds
                         if kind in spec.source_kinds
                         and spec.witness_predicate_id in ("spans_nest@v1",
                                                           "typed_field_predicate@v1"))
        return 1 + int(item_local_endpoints) + structural

    def duplicate_rows(self) -> dict[str, int]:
        """B.2's identity, checked across the WHOLE store rather than within one batch.

        The standing diagnostic named in the amended B.28: the per-item cache is the guarantee
        that two batches do not mint the same row twice, and this scan is what catches a store
        in which that guarantee was bypassed. Complexity: O(N c log N) on device, per kind.
        """
        addresses = self.spans.columns
        return {kind: table.duplicate_rows(addresses)
                for kind, table in self.store.tables.items() if len(table)}

    # ---------------------------------------------------------------- receipts
    def record_head_hash(self) -> str:
        """B.27's record head: the hash of the ordered list of admitted source content hashes."""
        return chash(list(self.blobs.handles()))

    def generation_id(self, parent: str | None = None, extractor_roster_hash: str = "",
                      fibre_declaration_hashes: Sequence[str] = ()) -> str:
        """B.27's parent-named content-addressed generation id, with exactly its field set."""
        return chash({
            "parent_generation_id": parent,
            "dataset_declaration_hash": self.declaration.declaration_hash,
            "fibre_declaration_hashes": list(fibre_declaration_hashes),
            "extractor_roster_hash": extractor_roster_hash,
            "segmenter_id": self.declaration.segmenter_id,
            "seg_version": self.declaration.seg_version,
            "record_head_hash": self.record_head_hash(),
        })

    def receipt(self, parent: str | None = None) -> dict[str, Any]:
        """The generation receipt (B.27) and coverage statement (B.35) this layer can fill."""
        rows = max(self.store.row_count, 1)
        return {
            "generation_id": self.generation_id(parent),
            "parent_generation_id": parent,
            "record_head_hash": self.record_head_hash(),
            "blobs": len(self.blobs),
            "blob_bytes": self.blobs.total_bytes(),
            "spans": len(self.spans),
            "store": self.store.receipt(),
            "relations": self.relations.receipt(rows),
            "anchors": self.anchors.receipt() if self.anchors is not None else None,
            "cache": {"entries": len(self.cache), "hits": self.cache.hits,
                      "misses": self.cache.misses},
            "coverage": self.coverage,
            "timings_s": dict(self.timings),
            "counters": dict(self.counters),
        }

    # ---------------------------------------------------------------- measuring
    def measure(self, label: str) -> "_Measure":
        return _Measure(self, label)


class _Measure:
    """A timer that starts BEFORE the expensive step and records peak device memory with it."""

    def __init__(self, ingestion: Ingestion, label: str) -> None:
        self.ingestion = ingestion
        self.label = label

    def __enter__(self) -> "_Measure":
        reset_peak_device_bytes(self.ingestion.device)
        torch.cuda.synchronize(self.ingestion.device)
        self.started = time.perf_counter()
        return self

    def __exit__(self, *exc: Any) -> None:
        torch.cuda.synchronize(self.ingestion.device)
        self.ingestion.timings[f"{self.label}_s"] = time.perf_counter() - self.started
        self.ingestion.counters[f"{self.label}_peak_device_bytes"] = peak_device_bytes(
            self.ingestion.device)


def counted(mapping: Mapping[str, int], key: str, amount: int = 1) -> None:
    mapping[key] = mapping.get(key, 0) + amount
