"""faces.py - THE JOIN: a persisted graded tree, a persisted record, and one range reduction.

This module is the twelve lines the J1 synthesis had to write inside its own driver in order to
measure anything (``evidence/ATLAS_PROGRAMME/waves/J1-join/synthesis/synthesis_checks.py``,
``_ranked_column``), made production code and given a consumer. The synthesis' own verdict on
why that is the whole shape of this wave: "That the synthesis had to author the join in order to
measure it is the proof that the join is missing and is small."

What it joins:

  ``record/segments.py``     ``open_record`` gives the typed columns back with no parse, no
                             extraction and no source read (its OpenReceipt says so).
  ``grading/tree.py``        ``load_tree`` gives every component's whole node table back with no
                             re-grading (the bytes ARE the tree), including each component's
                             ``row_global`` - the permutation that turns a record column into a
                             LEAF-ORDER column, which is the only thing a reduction needs.
  ``grading/ranges.py``      every carrier of A.34, computed as ONE batched reduction over a
                             frontier of contiguous ranges - never a face stored on a node, and
                             never one call per node.

THE FRONTIER ALWAYS TILES. A frontier here is a cut level of one lens's whole refinement: every
component's current ranges, concatenated in component-major order, which is CONTIGUOUS by
construction because a node's children tile the node and the components tile the rank space. So
one ``frontier_boundaries`` call describes the whole level and each reduction is ONE device call
for the level, whatever its F - which is the batching boundary ``face.py`` said the deletion of
the per-node Python fold was waiting for. A descent replaces the OPEN ranges by their children
and keeps the decided ones exactly as they are, so the tiling is preserved at every level and no
range is ever visited twice.

Complexity, M the lens's bound rows, F the frontier's ranges, V a column's vocabulary:
``load_persisted_lens`` O(M + N) host-to-device copies, one per array per component;
``ranked_column`` O(M) (one scatter, one gather); ``frontier_face`` and ``admits_over_frontier``
one bucketize plus one scatter per call, O(M + F*V) dense or O(nnz + F) sparse.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import torch

from ..grading import face as F
from ..grading import ranges as R
from ..grading.lens import LensRefusal
from ..record.columns import NULL_OF
from ..record.identity import IDENTITY_WORDS, ordinals_of_identity
from ..store import CompressedHive

__all__ = ["LoadedLens", "load_persisted_lens", "ranked_column", "RankedColumns",
           "leaf_label_of_rank", "frontier_face", "admits_over_frontier", "FrontierFace",
           "coarse_counts_over_frontier"]


@dataclass(frozen=True, slots=True)
class LoadedLens:
    """One lens's whole persisted refinement, in ONE flat node table, read from the hive.

    Absolute rank space: a node's ``lo``/``hi`` index ``rank_global`` directly, so one frontier
    can span every component of the lens and one reduction call serves the whole level.
    """

    lens_id: str
    dataset_id: str
    lens_hash: str
    rank_global: torch.Tensor          # int64 [M] record row ordinal of each rank position
    component_of_rank: torch.Tensor    # int64 [M]
    component_ptr: torch.Tensor        # int64 [C + 1] rank offsets of the components
    node_component: torch.Tensor       # int64 [N]
    lo: torch.Tensor                   # int64 [N] absolute
    hi: torch.Tensor                   # int64 [N] absolute
    parent: torch.Tensor               # int64 [N] absolute, -1 at a root
    left: torch.Tensor                 # int64 [N] absolute, -1 at a leaf
    right: torch.Tensor                # int64 [N]
    depth: torch.Tensor                # int64 [N]
    closure: torch.Tensor              # float64 [N] measured ||D_b||
    task_residual: torch.Tensor        # float64 [N] sqrt(L_f) with the register
    observable: torch.Tensor           # float64 [N] A.11's bare per-value residual
    mass: torch.Tensor                 # float64 [N] the node's reference mass within its component
    rank: torch.Tensor                 # int64 [N]
    priced_rank: torch.Tensor          # int64 [N]
    capacity_rank: torch.Tensor        # int64 [N]
    resolved: torch.Tensor             # bool [N]
    stop: torch.Tensor                 # bool [N]
    roots: torch.Tensor                # int64 [C] the depth-0 node of each component
    component_address: tuple[str, ...]  # the hive content address of each component's blob
    unbound_rows: torch.Tensor         # int64 [U] declared carrier rows the lens could not seat
    executed: dict[str, Any]           # counters of the work the load actually did
    # THE UNIVERSE AND THE REFERENCE MEASURE, BOTH CONSTANTS OF THE OPENED LENS. ``rank_all`` is
    # the concatenation below, computed once at load instead of once per property access (it was
    # read three times inside every read and again by every control, which is one allocation and
    # one copy of [M + U] int64 per question per caller). ``rank_pi`` is B.19's reference measure
    # of each rank position, written into the component's blob at persist time, so the lateral
    # residual of two lenses is a function of two LOADED lenses and needs no rebuild.
    rank_all: torch.Tensor | None = None       # int64 [M + U]
    rank_pi: torch.Tensor | None = None        # float64 [M]

    @property
    def rows(self) -> int:
        return int(self.rank_global.numel())

    @property
    def rank_global_all(self) -> torch.Tensor:
        """The read's whole universe: the lens's rank order, then the rows it could not seat.

        A ranked column is gathered over THIS, so positions ``[0, M)`` are the tree's ranges
        (every reduction reads only that span, which ``ranges.py`` explicitly allows for a
        longer column) and positions ``[M, M + U)`` are the unseated rows - which no range can
        decide and which the read therefore always opens. Built ONCE at load (``rank_all``);
        O(M + U) only for a lens constructed without it.
        """
        if self.rank_all is not None:
            return self.rank_all
        return torch.cat([self.rank_global, self.unbound_rows])

    @property
    def unbound(self) -> int:
        return int(self.unbound_rows.numel())

    @property
    def nodes(self) -> int:
        return int(self.lo.numel())

    @property
    def components(self) -> int:
        return int(self.component_ptr.numel()) - 1


def _as(array: Any, dtype: torch.dtype, device: torch.device) -> torch.Tensor:
    return torch.as_tensor(array, dtype=dtype, device=device)


def load_persisted_lens(manifest: Mapping[str, Any], hive: CompressedHive,
                        device: torch.device, identities: torch.Tensor) -> LoadedLens:
    """Read a lens back from the hive into ONE flat node table. Nothing is re-graded or re-cut.

    THE ROWS ARE NAMED BY IDENTITY, NOT BY ORDINAL. ``identities`` is THIS process's record
    identity column indexed by global ordinal (``TypedRowStore.identity_by_global``); every
    persisted rank position carries the B.2 identity it was written with, and the join back
    onto this record is one sort and two ``searchsorted`` calls per lens
    (``record.identity.ordinals_of_identity``). An identity this record does not hold is -1 and
    the load REFUSES BY NAME - which is the whole point: before this, the tree stored global
    ordinals, a reopen reassigned them, and the read silently answered from a different and
    smaller row set (qasper 966 -> 953 rows, 224 of 966 ordinals shared).

    ``tree.load_tree`` returns one dict per component with LOCAL node indices and
    component-local ``lo``/``hi``; this relinks them into absolute rank space with one offset
    per component and concatenates the arrays, so the read walks one table instead of a Python
    object per component. The hive verifies every blob against its own content address on the
    way in (``CompressedHive.get``), which is the only check performed here.

    Complexity: O(N + M) with one host-to-device copy per array per component. Counters of the
    work executed ride on the returned object.
    """
    from ..grading.tree import load_tree

    components = load_tree(dict(manifest), hive)
    # ONE HOST-TO-DEVICE COPY PER ARRAY PER LENS, not one per array per COMPONENT. Measured
    # 2026-09-22 by ``distil.py profile`` of the warm front door: 25,060 ``torch.as_tensor``
    # calls with a device argument, 1.51 s of a 7.1 s run and the profile's top entry by a
    # factor of five - one per (component, array) over 1,193 components of the declared draw,
    # each one a separate synchronous copy. The pieces are built on the HOST here and ``cat``
    # makes the single copy, which is the charter's own rule ("ONE TENSOR PER COLUMN PER BATCH")
    # applied to the object the read opens.
    host = torch.device("cpu")
    pieces: list[dict[str, torch.Tensor]] = []
    rank_offset = 0
    node_offset = 0
    rank_ptr = [0]
    blob_bytes = 0
    pi_persisted = bool(components)
    for index, component in enumerate(components):  # loop-ok: one blob per persisted component - the declared unit of persistence and of change
        arrays = component["arrays"]
        rows = int(component["header"]["rows"])
        local_nodes = int(component["header"]["nodes"])
        blob_bytes += int(sum(int(a.nbytes) for a in arrays.values()
                              if hasattr(a, "nbytes")))

        def link(name: str) -> torch.Tensor:
            values = _as(arrays[name], torch.int64, host)
            return torch.where(values >= 0, values + node_offset,
                              torch.full_like(values, -1))

        pieces.append({
            "rank_identity": _as(arrays["row_identity"], torch.int64, host),
            "rank_written_as": _as(arrays["row_global"], torch.int64, host),
            "component_of_rank": torch.full((rows,), index, dtype=torch.int64, device=host),
            "node_component": torch.full((local_nodes,), index, dtype=torch.int64,
                                          device=host),
            "lo": _as(arrays["lo"], torch.int64, host) + rank_offset,
            "hi": _as(arrays["hi"], torch.int64, host) + rank_offset,
            "parent": link("parent"), "left": link("left"), "right": link("right"),
            "depth": _as(arrays["depth"], torch.int64, host),
            "closure": _as(arrays["closure"], torch.float64, host),
            "task_residual": _as(arrays["task_residual"], torch.float64, host),
            "observable": _as(arrays["observable"], torch.float64, host),
            "mass": _as(arrays["mass"], torch.float64, host),
            "rank": _as(arrays["rank"], torch.int64, host),
            "priced_rank": _as(arrays["priced_rank"], torch.int64, host),
            "capacity_rank": _as(arrays["capacity_rank"], torch.int64, host),
            "resolved": _as(arrays["resolved"], torch.bool, host),
            "stop": _as(arrays["stop"], torch.bool, host),
            # B.19's reference measure per rank position, as the build wrote it. A blob cut
            # before this column existed simply has no reference measure to give back, and the
            # lens then reports ``rank_pi`` as absent rather than inventing one.
            "rank_pi": _as(arrays["row_pi"], torch.float64, host)
            if "row_pi" in arrays else torch.zeros(rows, dtype=torch.float64, device=host),
        })
        pi_persisted = pi_persisted and ("row_pi" in arrays)
        rank_offset += rows
        node_offset += local_nodes
        rank_ptr.append(rank_offset)

    def cat(name: str) -> torch.Tensor:
        """Every component's piece of one array, concatenated on the HOST and copied ONCE."""
        return torch.cat([piece[name] for piece in pieces]).to(device)  # loop-ok: one entry per component, concatenated once per array

    depth = cat("depth")
    header = components[0]["header"] if components else {}

    # --- the join: every persisted rank position, and every unseated row, by IDENTITY
    written_as = cat("rank_written_as") if pieces else torch.zeros(0, dtype=torch.int64,
                                                                  device=device)
    rank_identity = (cat("rank_identity") if pieces
                     else torch.zeros((0, IDENTITY_WORDS), dtype=torch.int64, device=device))
    rank_identity = rank_identity.to(device)
    unbound_identity = _as(list(manifest.get("unbound_identity", ())), torch.int64,
                           device).reshape(-1, IDENTITY_WORDS)
    needles = torch.cat([rank_identity, unbound_identity])
    resolved, ambiguous = ordinals_of_identity(identities, needles)
    unresolved = int((resolved < 0).sum())
    if unresolved or ambiguous:
        raise LensRefusal("PERSISTED-TREE-ROW-IDENTITY-NOT-IN-RECORD",
                          lens_id=str(header.get("lens_id", "")),
                          rows=int(needles.shape[0]), unresolved=unresolved,
                          first_word_collisions=ambiguous)
    rank_global = resolved[:rank_identity.shape[0]]
    unbound_rows = resolved[rank_identity.shape[0]:]
    ordinals_reproduced = bool(int((rank_global == written_as).sum()) == rank_global.numel())

    return LoadedLens(
        lens_id=str(header.get("lens_id", manifest.get("lens_id", ""))),
        dataset_id=str(header.get("dataset_id", manifest.get("dataset_id", ""))),
        lens_hash=str(header.get("lens_hash", manifest.get("lens_hash", ""))),
        rank_global=rank_global, component_of_rank=cat("component_of_rank"),
        component_ptr=_as(rank_ptr, torch.int64, device),
        node_component=cat("node_component"), lo=cat("lo"), hi=cat("hi"),
        parent=cat("parent"), left=cat("left"), right=cat("right"), depth=depth,
        closure=cat("closure"), task_residual=cat("task_residual"),
        observable=cat("observable"), mass=cat("mass"), rank=cat("rank"),
        priced_rank=cat("priced_rank"), capacity_rank=cat("capacity_rank"),
        resolved=cat("resolved"), stop=cat("stop"),
        roots=torch.nonzero(depth == 0, as_tuple=False).flatten(),
        component_address=tuple(str(entry["address"])
                                for entry in manifest["components"]),  # loop-ok: the manifest's own component list
        unbound_rows=unbound_rows,
        rank_all=torch.cat([rank_global, unbound_rows]),
        rank_pi=(cat("rank_pi") if pi_persisted else None),
        executed={"components_read": len(components),
                  "reference_measure_persisted": pi_persisted,
                  "nodes_read": int(depth.numel()),
                  "rows_read": int(rank_offset),
                  "rows_the_lens_could_not_seat": int(manifest.get("unbound_row_count", 0)),
                  "array_bytes_read": int(blob_bytes),
                  "rows_resolved_by_identity": int(rank_global.numel()),
                  "rows_whose_ordinal_was_reproduced": int((rank_global == written_as).sum()),
                  "ordinals_reproduced": ordinals_reproduced,
                  "components_regraded": 0,
                  "components_recut": 0})


def ranked_column(store: Any, kind: str, field: str,
                  rank_global: torch.Tensor) -> tuple[torch.Tensor, int, Any]:
    """One declared column of ONE row kind, laid out in the lens's LEAF ORDER.

    LIFTED from the J1 synthesis' driver (``synthesis_checks.py:50-61``), which is where the
    join was written in order to be measured. A rank position whose row is of another kind
    carries the column's own null sentinel, which is exactly what every reduction in
    ``ranges.py`` already excludes - so one column of one kind can be reduced over a frontier
    that covers rows of every kind, with no per-kind frontier and no filtering pass.

    Complexity: O(M), one scatter and one gather. Returns (ranked column, its null, its table).
    """
    table = store.table(kind)
    column = table.column(field)
    null = NULL_OF[column.dtype]
    full = torch.full((store.row_count,), null, dtype=column.dtype, device=column.device)
    full[table.global_ordinals] = column
    return R.gather_ranked(full, rank_global), null, table


def leaf_label_of_rank(lens: LoadedLens) -> torch.Tensor:
    """The LEAF each rank position sits in, as a label per position of the lens's rank order.

    The leaves tile the rank space, so ONE ``repeat_interleave`` over their own ranges labels
    every position and no Python loop touches a node or a row. This is the persisted-tree form
    of ``door._leaf_label_of_row``, which needed the in-memory ``GradedTree`` and therefore made
    the lateral residual - a headline number - unavailable on a door that OPENED its tree
    instead of building it. O(M), one gather. Returns int64 ``[M]``.
    """
    device = lens.lo.device
    leaves = torch.nonzero(lens.left < 0, as_tuple=False).flatten()
    lo = lens.lo.index_select(0, leaves)
    sizes = lens.hi.index_select(0, leaves) - lo
    label = torch.zeros(lens.rows, dtype=torch.int64, device=device)
    if not int(sizes.sum()):
        return label
    starts = torch.repeat_interleave(lo, sizes)
    ends = torch.cumsum(sizes, 0)
    offsets = (torch.arange(int(sizes.sum()), dtype=torch.int64, device=device)
               - torch.repeat_interleave(ends - sizes, sizes))
    label[starts + offsets] = torch.repeat_interleave(
        torch.arange(leaves.numel(), dtype=torch.int64, device=device), sizes)
    return label


class RankedColumns:
    """EVERY ranked column of one (record, lens), gathered ONCE when the lens is opened.

    THE RULE THIS IMPLEMENTS, verbatim from the wave's brief: "anything that depends only on
    (record, lens, declared axes) is computed at ingestion or on first use and persisted or
    cached for the run; a read or a question touches only what depends on the question." A
    ranked column is exactly such a thing - it is the record's column laid out in the lens's own
    leaf order - and it was being rebuilt inside every ``read()``, every ``admission_axes`` and
    every ``direct_answer``, so one question paid the O(M) scatter-and-gather up to three times
    and the next question paid it all again.

    What is held here: the declared columns (keyed by row kind and column name), the
    row-kind membership masks (``torch.isin`` over the universe, likewise a constant of the
    lens), and the DERIVED anchor-reached columns - which do depend on a question, and are
    therefore keyed by that question and built once for all of its readers rather than once per
    reader.

    Complexity: O(K * M) once at open for K declared columns, then O(1) per lookup.
    """

    __slots__ = ("store", "universe", "_declared", "_mine", "_derived",
                 "built_at_open", "built_after_open", "derived_built", "lookups")

    def __init__(self, store: Any, lens: LoadedLens) -> None:
        self.store = store
        self.universe = lens.rank_global_all
        self._declared: dict[tuple[str, str], tuple[torch.Tensor, int, Any]] = {}
        self._mine: dict[str, torch.Tensor] = {}
        self._derived: dict[str, tuple[torch.Tensor, int, Any]] = {}
        self.built_at_open = 0
        self.built_after_open = 0
        self.derived_built = 0
        self.lookups = 0

    def open_every_declared_column(self) -> dict[str, Any]:
        """Gather every declared column of every kind the record holds, and every kind mask.

        This is the whole of the (record, lens) work, done at the stage that opens the lens. A
        question that asks for a column therefore finds it; the read's own
        ``ranked_columns_built`` counter is the number it had to build itself, and it is zero.
        """
        for kind, table in self.store.tables.items():  # loop-ok: the declaration's own row kinds
            if not len(table):
                continue
            self._mine[kind] = torch.isin(self.universe, table.global_ordinals)
            for name in table.spec.columns:  # loop-ok: that kind's own declared columns
                self._declared[(kind, name)] = ranked_column(self.store, kind, name,
                                                             self.universe)
                self.built_at_open += 1
        return {"ranked_columns_gathered_at_open": self.built_at_open,
                "row_kind_masks_built_at_open": len(self._mine),
                "positions": int(self.universe.numel())}

    def get(self, kind: str, column: str) -> tuple[torch.Tensor, int, Any]:
        """One declared column in the lens's leaf order. A gather at open, a lookup here."""
        self.lookups += 1
        held = self._declared.get((kind, column))
        if held is None:
            held = ranked_column(self.store, kind, column, self.universe)
            self._declared[(kind, column)] = held
            self.built_after_open += 1
        return held

    def mine(self, kind: str) -> torch.Tensor:
        """The mask "this rank position holds a row OF THIS KIND" - a constant of the lens."""
        held = self._mine.get(kind)
        if held is None:
            held = torch.isin(self.universe, self.store.table(kind).global_ordinals)
            self._mine[kind] = held
            self.built_after_open += 1
        return held

    def anchor_reached(self, key: str, kind: str,
                       reached: torch.Tensor) -> tuple[torch.Tensor, int, Any]:
        """The derived ANCHOR-REACHED column of one question, built once for all its readers.

        A two-code column with the null sentinel on rows of another kind, so a frontier reduces
        it exactly like a declared enum and nothing downstream knows it was derived. It depends
        on the question's own resolved anchor set, which is why it is keyed by the question and
        not gathered at open. O(M log M), one ``isin``.
        """
        held = self._derived.get(key)
        if held is None:
            table = self.store.table(kind)
            mine = self.mine(kind)
            hit = torch.isin(self.universe, reached.to(self.universe.device))
            column = torch.where(mine, hit.to(torch.int8),
                                 torch.full(hit.shape, -1, dtype=torch.int8,
                                            device=self.universe.device))
            held = (column, -1, table)
            self._derived[key] = held
            self.derived_built += 1
        return held


@dataclass(frozen=True, slots=True)
class FrontierFace:
    """The face of EVERY range of one frontier, for one declared column, as a reduction.

    Exactly A.34's four carriers, with the multiplicity the old fold threw away for every
    carrier but ``kind``. ``form`` says which of ``ranges.py``'s reductions produced it, which
    is ``face.RANGE_REDUCTION_OF`` made executable instead of a map of names.
    """

    kind: str                        # the row kind whose column this is
    field: str
    arrow_type: str
    carrier: str                     # A.34's carrier: scalar | set | date | kind
    form: str                        # the reduction that computed it
    ranges: int
    declares: torch.Tensor           # int64 [F] carrier rows in the range that declare the field
    counts: torch.Tensor | None      # int64 [F, V] dense (kind/set at a declared small width)
    sparse: tuple[torch.Tensor, torch.Tensor, torch.Tensor] | None  # (range, code, count)
    hull: tuple[torch.Tensor, torch.Tensor, torch.Tensor] | None    # (lo, hi, declares)
    survives: torch.Tensor | None    # bool [F] a SCALAR that is a singleton over the range
    receipt: R.ReductionReceipt

    def as_summary(self) -> dict[str, Any]:
        return {"kind": self.kind, "field": self.field, "arrow_type": self.arrow_type,
                "carrier": self.carrier, "form": self.form, "ranges": self.ranges,
                "declares_total": int(self.declares.sum()),
                "nnz": (int(self.sparse[0].numel()) if self.sparse is not None else None),
                "dense_cells": (int(self.counts.numel()) if self.counts is not None else None),
                "survivors": (int(self.survives.sum()) if self.survives is not None else None),
                "seconds": self.receipt.seconds,
                "peak_device_bytes": self.receipt.peak_device_bytes}


def _vocabulary_width(table: Any, field: str, arrow_type: str) -> int:
    """The column's declared code space: an enum's or dictionary's size, 2 for a bool, and the
    column's own value space for a raw int64 (which has no dictionary). O(1)."""
    if arrow_type == "bool":
        return 2
    vocabulary = table.vocabulary(field)
    if vocabulary:
        return int(len(vocabulary))
    return 0


def frontier_face(store: Any, lens: LoadedLens, kind: str, field: str,
                  boundaries: torch.Tensor, *, ranked: torch.Tensor | None = None,
                  device_budget_bytes: int | None = None) -> FrontierFace:
    """ONE call, ONE frontier, ONE column: the face of every range of the level at once.

    Which reduction is used is the carrier map (``face.carrier_for_type``, which now admits
    ``bool``) plus a DEVICE-BUDGET decision at call time, not a per-carrier branch: a KIND or a
    small-enum SET reduces through the dense ``kind_counts``; a row-scale SET (``span_ref``, one
    code per witnessed span) reduces through ``sparse_kind_counts``, because the dense ``[F, V]``
    table is the object the charter forbids by name at that width and ``kind_counts`` refuses it.
    A DATE reduces through ``date_hull`` on its integer day key - never a string comparison,
    which is the defect the deleted ``grading/measure.py`` carried ("2026-08-01" <
    "2026-08-01 01:24:03" refused 14 of 15 qualifying nodes).

    Complexity: one bucketize plus one scatter; O(M + F*V) dense, O(nnz + F log F) sparse.
    """
    table = store.table(kind)
    arrow_type = table.spec.field(field).type
    carrier = F.carrier_for_type(arrow_type)
    if ranked is None:
        ranked, null, table = ranked_column(store, kind, field, lens.rank_global)
    else:
        null = NULL_OF[ranked.dtype]
    ranges = int(boundaries.numel()) - 1
    width = _vocabulary_width(table, field, arrow_type)
    budget = (device_budget_bytes if device_budget_bytes is not None
              else R._dense_kind_counts_budget_bytes(ranked.device))
    rows = int(boundaries[-1]) - int(boundaries[0])

    if carrier in ("kind", "set"):
        dense_bytes = ranges * max(width, 1) * 8
        if width and dense_bytes <= budget:
            counts, receipt = R.measured("kind_counts", R.kind_counts, ranked, boundaries,
                                         width, null, _device=ranked.device, _rows=rows,
                                         _ranges=ranges)
            return FrontierFace(kind, field, arrow_type, carrier, "kind_counts", ranges,
                                R.declared_counts_from_kind_counts(counts), counts, None, None,
                                None, receipt)
        triple, receipt = R.measured("sparse_kind_counts", R.sparse_kind_counts, ranked,
                                     boundaries, null, _device=ranked.device, _rows=rows,
                                     _ranges=ranges)
        declares = R.sparse_declared_counts(triple[0], triple[2], ranges)
        return FrontierFace(kind, field, arrow_type, carrier, "sparse_kind_counts", ranges,
                            declares, None, triple, None, None, receipt)
    if carrier == "date":
        hull, receipt = R.measured("date_hull", R.date_hull, ranked, boundaries, null,
                                   _device=ranked.device, _rows=rows, _ranges=ranges)
        return FrontierFace(kind, field, arrow_type, carrier, "date_hull", ranges, hull[2],
                            None, None, hull, None, receipt)
    # SCALAR gets BOTH reductions, and this is the module docstring of ``ranges.py`` made
    # executable rather than quoted: "A.34 as implemented keeps multiplicity only for the
    # ``kind`` carrier ... read as a range reduction, a COUNT is a bincount of the column slice
    # and is therefore exact for EVERY carrier, not only enum". ``scalar_reduce`` gives the
    # SURVIVAL and the hull (A.34's named drop); the counts give the exact per-code multiplicity
    # an equality, a membership or a count threshold needs. Without the second one a scalar
    # column could only answer an equality by min == max == code, which is a strictly weaker
    # verdict: a range holding two values, one of them the wanted one, would come back OPEN
    # where the count says decided-in-part with an exact count.
    reduced, receipt = R.measured("scalar_reduce", R.scalar_reduce, ranked, boundaries, null,
                                  _device=ranked.device, _rows=rows, _ranges=ranges)
    lo, hi, survives, declares = reduced
    dense_bytes = ranges * max(width, 1) * 8
    if width and dense_bytes <= budget:
        counts, count_receipt = R.measured("kind_counts", R.kind_counts, ranked, boundaries,
                                           width, null, _device=ranked.device, _rows=rows,
                                           _ranges=ranges)
        return FrontierFace(kind, field, arrow_type, carrier, "scalar_reduce+kind_counts",
                            ranges, declares, counts, None, (lo, hi, declares), survives,
                            count_receipt)
    triple, count_receipt = R.measured("sparse_kind_counts", R.sparse_kind_counts, ranked,
                                       boundaries, null, _device=ranked.device, _rows=rows,
                                       _ranges=ranges)
    return FrontierFace(kind, field, arrow_type, carrier, "scalar_reduce+sparse_kind_counts",
                        ranges, declares, None, triple, (lo, hi, declares), survives,
                        count_receipt)


def admits_over_frontier(condition: Mapping[str, Any],
                         face: FrontierFace) -> R.AdmitVerdict:
    """The verdict per range, from whichever reduction the column's width admitted.

    One function for both forms (B2's escalated deficiency 2: ``admits`` had no sparse path, so
    a row-scale SET carrier could not reach a verdict at real size at all). The declared==0 rule
    is ``ranges.admits``'s, identically for both, so a range where no carrier row declares the
    field is OPEN and never EXCLUDED. O(F) plus O(nnz) on the sparse path.
    """
    kind = condition["kind"]
    if kind in ("day", "day_interval"):
        if face.hull is None:
            raise R.RangeRefusal("ADMITS-CONDITION-KIND-NOT-ADMITTED", kind=kind,
                                 carrier=face.carrier, field=face.field)
        return R.admits(condition, hull=face.hull)
    if face.counts is not None:
        return R.admits(condition, counts=face.counts)
    if face.sparse is not None:
        return R.admits(condition, sparse=face.sparse, ranges=face.ranges)
    if face.carrier == "scalar" and kind == "equality":
        # A SCALAR range admits an equality exactly when it SURVIVES at the wanted code: min ==
        # max == code over the range. Same declared==0 rule, same three exclusive states.
        lo, hi, declares = face.hull                       # type: ignore[misc]
        code = int(condition["code"])
        has_any = declares > 0
        decided_in = has_any & (lo == code) & (hi == code)
        excluded = has_any & ((hi < code) | (lo > code))
        return R.AdmitVerdict(decided_in, excluded, ~decided_in & ~excluded, declares)
    raise R.RangeRefusal("ADMITS-CONDITION-KIND-NOT-ADMITTED", kind=kind, carrier=face.carrier,
                         field=face.field)


def coarse_counts_over_frontier(lens: LoadedLens, relation_table: Any,
                                boundaries: torch.Tensor, *,
                                dense: bool = False) -> dict[str, Any]:
    """B.36's block sum between the ranges of this frontier, for ONE relation kind.

    Sparse by default - the ``(src_range, dst_range, count)`` triple, O(nnz) - with the dense
    ``[F, F]`` form available behind ``ranges.coarse_relation_counts``' own declared device
    budget and its named refusal. This is the coarse graph AT A GRADE, which is what the front
    door needs and what nothing had ever asked for (which is why the dense allocation was never
    exercised at a real F).

    Complexity: O(E log E) device ops, O(nnz) device bytes.
    """
    device = lens.rank_global.device
    rows = int(lens.rank_global.max()) + 2 if lens.rows else 2
    rank_of = torch.full((rows,), -1, dtype=torch.int64, device=device)
    rank_of[lens.rank_global] = torch.arange(lens.rows, dtype=torch.int64, device=device)
    # B.36 sums LOCATED WITNESSES, not edges: the weight of an instance is the number of
    # witness addresses it carries (``witness_lengths``), which is the multiplicity F1's two
    # carried losses are about - an edge table that keeps one witness per (law, pair) counts
    # edges, and the coarse count is then wrong by exactly the multiplicity it dropped.
    src = relation_table.src
    dst = relation_table.dst
    weight = relation_table.witness_lengths.to(torch.int64)
    out: dict[str, Any] = {"instances": int(src.numel()),
                           "ranges": int(boundaries.numel()) - 1}
    triple, receipt = R.measured("sparse_relation_counts", R.sparse_relation_counts, rank_of,
                                 src, dst, weight, boundaries, _device=device,
                                 _rows=int(src.numel()), _ranges=out["ranges"])
    out["sparse"] = {"pairs": int(triple[0].numel()), "total": int(triple[2].sum()),
                     "seconds": receipt.seconds,
                     "peak_device_bytes": receipt.peak_device_bytes}
    out["triple"] = triple
    if dense:
        matrix, dense_receipt = R.measured("coarse_relation_counts", R.coarse_relation_counts,
                                           rank_of, src, dst, weight, boundaries,
                                           _device=device, _rows=int(src.numel()),
                                           _ranges=out["ranges"])
        out["dense"] = {"cells": int(matrix.numel()), "total": int(matrix.sum()),
                        "seconds": dense_receipt.seconds,
                        "peak_device_bytes": dense_receipt.peak_device_bytes}
        out["dense_matrix"] = matrix
    return out


# Explicit front opening/reduction metadata, not arbitrary seconds-named fields.



# The inert closed receipt contract; numeric execution remains owned here.
from ..receipt_diagnostics import opening_execution_parts, coarse_counts_parts
