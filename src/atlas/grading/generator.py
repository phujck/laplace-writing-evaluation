"""generator.py - B.16, B.18, B.19: the lens generator, from integer located witness counts.

Nothing here reads an embedding, a similarity or an authored real weight. The whole numeric
chain starts at ``RelationKindTable.csr``'s int64 ``located_count`` - the number of DISTINCT
witness tuples licensing a step - and stays integer until the single division B.18 names.

  A        symmetric int64, A_ij = the located witness count over the lens's counted relation
           kinds for the unordered pair {i, j}, summed over kinds (B.16), no self loops
  d_j      int64 column degree sum_i A_ij (B.16)
  G        G_ij = A_ij / d_j off diagonal, G_jj = -1 (B.18, ITEM-PACED: each item leaves at
           unit rate, so one unit of generator time is one item firing - lean L10)
  pi       pi_j = d_j / sum_k d_k on a connected carrier, DERIVED as the unique solution of
           G pi = 0 (B.19), never stipulated, never an encoder second moment

A.35(c) demands two things this module supplies, and refuses without: pi arrives with
provenance and is REFUSED if it was used to construct the generator being checked (the field
``pi_used_in_generator`` is False by construction and asserted by the tests, and the
stationarity assertion is the check that could not fire on a pi-built generator); and detailed
balance is asserted SEPARATELY from stationarity, because every whitened construction downstream
assumes it.

The whitened generator is the one object the spectral proposal and TEST 2 both act on:

  Gtilde = W^{-1/2} G W^{1/2} with W = diag(pi)
         = D^{-1/2} A D^{-1/2} - I                       (exactly, because pi ~ d)
  Ltilde = -Gtilde = I - D^{-1/2} A D^{-1/2}             (the normalised Laplacian, PSD)

That identity is why no float ever needs to be stored for the whitened operator: it is two
integer arrays and a square root. A.6's whitening and B.22's normalised Laplacian are the same
matrix here, and it is symmetric precisely because A is - which IS detailed balance.

Complexity (M carrier rows, E distinct pairs, K counted kinds):
  build            O(K E log E) on device, no Python loop over an edge or a row
  components       O(E * diameter) label propagation, vectorised per sweep
  peak memory      O(E) int64 plus O(M) - never an M x M object
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import torch

from ..record.ingestion import Ingestion
from .lens import LensDeclaration, LensRefusal

__all__ = ["LensGenerator", "ComponentGenerator", "build_lens_generator",
           "materialise_derived", "materialise_projected", "per_kind_edges", "carrier_field",
           "content_affinity_counts", "summed_generator_counts"]


def _binding_pairs(ingestion, bind_kind: str, local_of_global: torch.Tensor,
                   device: torch.device) -> tuple[torch.Tensor, torch.Tensor]:
    """Every instance of a declared BINDING relation, as (hub global row, carrier local row).

    The binding crosses the carrier by construction (``LensDeclaration.check_against`` refuses a
    projection whose bind kind does not), so exactly one endpoint of each stored instance is a
    carrier row and the other is the hub. Which side that is, is READ OFF THE STORED INSTANCES
    rather than declared a second time.

    Complexity: O(E) device work, one pass over the kind's CSR. No Python loop over an edge.
    """
    rows_total = ingestion.store.row_count
    table = ingestion.relations.kind(bind_kind)
    empty = torch.empty(0, dtype=torch.int64, device=device)
    if table is None or not len(table):
        return empty, empty
    csr = table.csr(rows_total)
    if csr.nnz == 0:
        return empty, empty
    degree = (csr.indptr[1:] - csr.indptr[:-1]).to(torch.int64)
    owner = torch.repeat_interleave(
        torch.arange(rows_total, dtype=torch.int64, device=device), degree)
    target = csr.indices.to(torch.int64)
    owner_local, target_local = local_of_global[owner], local_of_global[target]
    # one side on the carrier, the other off it: both orientations in one expression
    forward = (owner_local >= 0) & (target_local < 0)
    backward = (target_local >= 0) & (owner_local < 0)
    hub = torch.cat([target[forward], owner[backward]])
    carrier = torch.cat([owner_local[forward], target_local[backward]])
    return hub, carrier


def materialise_projected(ingestion, spec, local_of_global: torch.Tensor, device: torch.device
                          ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """A declared relation of the record PROJECTED onto the lens's carrier. Returns local pairs.

    Two shapes, both vectorised and both chains:

      through_kind is not None - each stored instance (a, b) of the through relation is carried to
      the carrier rows that bind a and b. ONE projected instance per stored instance per binding
      pair, so the count is a located witness count and never a similarity.

      through_kind is None - the hub is the link itself: the carrier rows sharing one hub are put
      in the store's own declared row order and CONSECUTIVE pairs are linked. N carrier rows in
      one container cost N - 1 edges, never N^2 (B.29's shape, ``_anchor_bound_chain``'s rule).

    Complexity: O(E log E) device work; the join expands by the binding degrees, which are
    reported in the receipt as ``projected_instances``. No Python loop over a row or an edge.
    """
    hub, carrier = _binding_pairs(ingestion, spec.bind_kind, local_of_global, device)
    empty = torch.empty(0, dtype=torch.int64, device=device)
    if not hub.numel():
        return empty, empty, empty
    order = torch.argsort(hub, stable=True)
    hub, carrier = hub[order], carrier[order]
    if spec.through_kind is None:
        # THE CHAIN THROUGH THE HUB: consecutive carrier rows of one hub, in declared row order.
        inner = torch.argsort(hub * (int(carrier.max()) + 2) + carrier, stable=True)
        hub_s, carrier_s = hub[inner], carrier[inner]
        same = (hub_s[1:] == hub_s[:-1]) & (carrier_s[1:] != carrier_s[:-1])
        src, dst = carrier_s[:-1][same], carrier_s[1:][same]
        return src, dst, torch.ones_like(src)
    rows_total = ingestion.store.row_count
    table = ingestion.relations.kind(spec.through_kind)
    if table is None or not len(table):
        return empty, empty, empty
    csr = table.csr(rows_total)
    if csr.nnz == 0:
        return empty, empty, empty
    degree = (csr.indptr[1:] - csr.indptr[:-1]).to(torch.int64)
    a_global = torch.repeat_interleave(
        torch.arange(rows_total, dtype=torch.int64, device=device), degree)
    b_global = csr.indices.to(torch.int64)
    value = csr.located_count.to(torch.int64)
    # the hub CSR: where each hub row's carrier bindings start, and how many there are
    start = torch.searchsorted(hub, a_global)
    count_a = torch.searchsorted(hub, a_global, right=True) - start
    start_b = torch.searchsorted(hub, b_global)
    count_b = torch.searchsorted(hub, b_global, right=True) - start_b
    live = (count_a > 0) & (count_b > 0)
    if not bool(live.any()):
        return empty, empty, empty
    start, count_a = start[live], count_a[live]
    start_b, count_b = start_b[live], count_b[live]
    value = value[live]
    total = count_a * count_b
    edge = torch.repeat_interleave(torch.arange(total.numel(), dtype=torch.int64, device=device),
                                   total)
    within = (torch.arange(int(total.sum()), dtype=torch.int64, device=device)
              - torch.repeat_interleave(torch.cumsum(total, 0) - total, total))
    left = carrier.index_select(0, start[edge] + torch.div(within, count_b[edge],
                                                           rounding_mode="floor"))
    right = carrier.index_select(0, start_b[edge] + within % count_b[edge])
    keep = left != right
    return left[keep], right[keep], value[edge][keep]


def _anchor_bound_chain(ingestion, spec) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """``same_anchor_across_items@v1``: C.3 cross-item binding through the anchor index.

    B.29 keeps every MINTED relation item-local: an edge between two items would carry a witness
    tuple straddling two blobs, which the predicate restriction excludes (F2 carried exactly that
    as a standing residual - "Cross-item identity is served by the anchor index (C.3). Any later
    fibre wanting a cross-item coreference RELATION must declare it uncounted"). So the binding
    is DERIVED BY THE LENS - a projection (B.6), never written back into the record - and it is
    witnessed by the two rows' own located surface spans, one on each side.

    The equivalence is the one C.3's anchor index resolves: two rows whose DECLARED ANCHOR
    COLUMN carries the same surface. It is read off the store's own dictionary code for that
    column rather than through a second index, and the declaration is checked - the group column
    must be a declared anchor column of the row kind, or the lens is refused by name, so no lens
    can quietly bind on a column the dataset never declared as an identity.

    The rows are grouped by that code, put in declared item order, and CONSECUTIVE pairs in
    DIFFERENT items are linked. A chain, never a clique: a surface occurring in N items costs
    N - 1 edges, not N^2, so a common name cannot make a dense block of the whole corpus. Rows
    whose surface is absent are named by their absence, never silently given an edge.

    Returns (source global ordinals, target global ordinals, witness span ordinals).
    Complexity: O(N log N) on device, one sort. No Python loop over a row or an edge.
    """
    device = ingestion.device
    anchors = ingestion.declaration.surface_set.anchor_columns
    for kind in spec.source_kinds:
        if spec.group_column not in anchors.get(kind, ()):
            raise LensRefusal("LENS-DERIVED-BINDS-ON-A-COLUMN-THAT-IS-NOT-AN-ANCHOR",
                              kind=spec.kind, row_kind=kind, column=spec.group_column)
    surface_parts, item_parts, row_parts, span_parts = [], [], [], []
    for kind in spec.source_kinds:
        table = ingestion.store.table(kind)
        if not len(table):
            continue
        surface_parts.append(table.column(spec.group_column).to(torch.int64))
        item_parts.append(table.column(spec.order_column).to(torch.int64))
        row_parts.append(table.global_ordinals)
        span_parts.append(table.witness_span.to(torch.int64))
    if not surface_parts:
        empty = torch.empty(0, dtype=torch.int64, device=device)
        return empty, empty, empty
    # the surface CODE is a dictionary code local to one row kind, so the kind is part of the
    # key exactly as ``materialise_derived`` does - two kinds' code 3 are not the same surface
    kind_code = torch.cat([torch.full_like(part, index)
                           for index, part in enumerate(surface_parts)])
    surface = torch.cat(surface_parts)
    item = torch.cat(item_parts)
    rows = torch.cat(row_parts)
    spans = torch.cat(span_parts)
    live = (surface >= 0) & (item >= 0)
    kind_code, surface, item, rows, spans = (kind_code[live], surface[live], item[live],
                                             rows[live], spans[live])
    if rows.numel() < 2:
        empty = torch.empty(0, dtype=torch.int64, device=device)
        return empty, empty, empty
    width = int(surface.max()) + 1
    key = kind_code * width + surface
    stride = int(item.max()) + 2
    order = torch.argsort(key * stride + (item + 1))
    key, item, rows, spans = key[order], item[order], rows[order], spans[order]
    # CROSS-item only: a pair inside one item is what the record already mints (mentions,
    # same_entity); this derived relation exists for the step the record cannot take.
    same = (key[1:] == key[:-1]) & (item[1:] != item[:-1])
    return rows[:-1][same], rows[1:][same], spans[:-1][same]


def materialise_derived(ingestion, spec) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """B.7 typed_field_predicate at rung (a): the derived relation's instances.

    ``same_anchor_across_items@v1``: the C.3 cross-item binding above.

    ``same_provenance_next@v1``: within each distinct value of the declared GROUP column, the
    rows of the declared source kinds are put in declared time order and CONSECUTIVE pairs are
    linked - one instance per pair, witnessed by the two rows' own witness spans. A chain, never
    a clique: the relation is linear in the rows, so a provenance lens costs O(N log N) and never
    materialises a same-author block of N^2 edges.

    Returns (source global ordinals, target global ordinals, witness span ordinals).
    Complexity: O(N log N) on device.
    """
    if spec.predicate_id == "same_anchor_across_items@v1":
        return _anchor_bound_chain(ingestion, spec)
    device = ingestion.device
    group_parts, order_parts, row_parts, span_parts = [], [], [], []
    for kind in spec.source_kinds:
        table = ingestion.store.table(kind)
        if not len(table):
            continue
        group_parts.append(table.column(spec.group_column).to(torch.int64))
        order_parts.append(table.column(spec.order_column).to(torch.int64))
        row_parts.append(table.global_ordinals)
        span_parts.append(table.witness_span.to(torch.int64))
    if not group_parts:
        empty = torch.empty(0, dtype=torch.int64, device=device)
        return empty, empty, empty
    # a group code is only comparable within one row kind's dictionary, so the kind is part of
    # the group key - two kinds' code 3 are not the same provenance
    kind_code = torch.cat([torch.full_like(part, index)
                           for index, part in enumerate(group_parts)])
    group = torch.cat(group_parts)
    order = torch.cat(order_parts)
    rows = torch.cat(row_parts)
    spans = torch.cat(span_parts)
    live = group >= 0
    kind_code, group, order, rows, spans = (kind_code[live], group[live], order[live],
                                            rows[live], spans[live])
    if rows.numel() < 2:
        empty = torch.empty(0, dtype=torch.int64, device=device)
        return empty, empty, empty
    width = int(group.max()) + 1
    key = kind_code * width + group
    sort = torch.argsort(key * (int(order.max()) + 2) + (order - int(order.min()) + 1))
    key, rows, spans = key[sort], rows[sort], spans[sort]
    same = key[1:] == key[:-1]
    src = rows[:-1][same]
    dst = rows[1:][same]
    witness = spans[:-1][same]
    return src, dst, witness


@dataclass(frozen=True, slots=True)
class ComponentGenerator:
    """One connected component of a lens's carrier: the only place B.19's pi is defined."""

    lens_id: str
    component: int
    global_rows: torch.Tensor      # int64 [n] - record row ordinals, ascending
    src: torch.Tensor              # int64 [nnz] - local, symmetric, no self loops
    dst: torch.Tensor              # int64 [nnz] - local
    count: torch.Tensor            # int64 [nnz] - B.16 located witness counts
    degree: torch.Tensor           # int64 [n]
    pi: torch.Tensor               # float64 [n], sums to 1 (B.19)
    device: torch.device

    @property
    def n(self) -> int:
        return int(self.global_rows.numel())

    @property
    def nnz(self) -> int:
        return int(self.src.numel())

    def whitened_laplacian_coo(self) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Ltilde = I - D^{-1/2} A D^{-1/2} as (rows, cols, values) float64. O(nnz)."""
        root = torch.sqrt(self.degree.to(torch.float64))
        off = -self.count.to(torch.float64) / (root[self.src] * root[self.dst])
        diag = torch.arange(self.n, dtype=torch.int64, device=self.device)
        rows = torch.cat([self.src, diag])
        cols = torch.cat([self.dst, diag])
        values = torch.cat([off, torch.ones(self.n, dtype=torch.float64, device=self.device)])
        return rows, cols, values

    def dense_generator(self) -> torch.Tensor:
        """G itself, dense float64 - only for the lifted kernel's small exact checks. O(n^2)."""
        gen = torch.zeros((self.n, self.n), dtype=torch.float64,  # dense-ok: the lifted kernel's small exact fixtures only - no build or read path calls this; the docstring states O(n^2) and the callers are the acceptance fixtures
                          device=self.device)
        gen[self.src, self.dst] = self.count.to(torch.float64) / self.degree.to(
            torch.float64)[self.dst]
        gen[torch.arange(self.n, device=self.device),
            torch.arange(self.n, device=self.device)] = -1.0
        return gen

    def stationarity_defect(self) -> float:
        """max |(G pi)_i| - A.35(c)'s check, which could not fire on a pi-built G. O(nnz)."""
        flow = torch.zeros(self.n, dtype=torch.float64, device=self.device)
        rate = self.count.to(torch.float64) / self.degree.to(torch.float64)[self.dst]
        flow.scatter_add_(0, self.src, rate * self.pi[self.dst])
        return float(torch.max(torch.abs(flow - self.pi)))

    def detailed_balance_defect(self) -> float:
        """max |pi_j G_ij - pi_i G_ji|, asserted SEPARATELY from stationarity (A.35(c))."""
        rate = self.count.to(torch.float64) / self.degree.to(torch.float64)[self.dst]
        forward = rate * self.pi[self.dst]
        back = torch.zeros_like(forward)
        key = self.src * self.n + self.dst
        rev = self.dst * self.n + self.src
        order = torch.argsort(key)
        position = torch.searchsorted(key[order], rev)
        back = forward[order][position.clamp(max=forward.numel() - 1)]
        return float(torch.max(torch.abs(forward - back)))


@dataclass(frozen=True, slots=True)
class LensGenerator:
    """A lens's whole carrier: every component, with the rows the lens could not seat."""

    lens: LensDeclaration
    components: tuple[ComponentGenerator, ...]
    carrier_global_rows: torch.Tensor          # int64 - every seated row, ascending
    isolated_global_rows: torch.Tensor         # int64 - degree 0 under this lens, named not hidden
    counts_by_kind: dict[str, int]
    pi_used_in_generator: bool = False
    pi_provenance: str = ("DERIVED by B.19 as the unique solution of G pi = 0 on each connected "
                          "component; pi_j = d_j / sum_k d_k with d the int64 located-witness "
                          "degree. Never stipulated, never an encoder second moment.")
    generator_provenance: str = ("B.18 item-paced G_ij = A_ij/d_j, G_jj = -1, built from "
                                 "RelationKindTable.csr located_count alone. No similarity, no "
                                 "authored real weight, no embedding reaches this matrix.")

    def receipt(self) -> dict[str, Any]:
        return {
            "lens_id": self.lens.lens_id,
            "lens_hash": self.lens.lens_hash(),
            "counted_relation_kinds": list(self.lens.counted_relation_kinds),
            "located_counts_by_kind": dict(sorted(self.counts_by_kind.items())),
            # THREE different numbers, never one serving for another: the rows of the declared
            # carrier KINDS, the rows of those that a counted witness reaches, and the rows the
            # lens drops at degree 0 because B.18 needs d_j > 0.
            "declared_carrier_rows": int(self.carrier_global_rows.numel()
                                         + self.isolated_global_rows.numel()),
            "carrier_rows_with_a_counted_witness": int(self.carrier_global_rows.numel()),
            "isolated_rows_named": int(self.isolated_global_rows.numel()),
            "components": len(self.components),
            "component_sizes": sorted((c.n for c in self.components), reverse=True)[:10],
            "largest_component_nnz": max((c.nnz for c in self.components), default=0),
            "pi_used_in_generator": self.pi_used_in_generator,
            "pi_provenance": self.pi_provenance,
            "generator_provenance": self.generator_provenance,
            "max_stationarity_defect": max((c.stationarity_defect()
                                            for c in self.components), default=0.0),
            "max_detailed_balance_defect": max((c.detailed_balance_defect()
                                                for c in self.components), default=0.0),
        }


def _carrier_rows(ingestion: Ingestion, lens: LensDeclaration) -> torch.Tensor:
    parts = [ingestion.store.table(kind).global_ordinals for kind in lens.carrier_row_kinds]
    return torch.sort(torch.cat(parts)).values


def _symmetric_counts(ingestion: Ingestion, lens: LensDeclaration,
                      local_of_global: torch.Tensor, device: torch.device
                      ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, dict[str, int]]:
    """B.16's A as coalesced symmetric COO. One pass per counted kind, no loop over an edge."""
    rows_total = ingestion.store.row_count
    src_parts: list[torch.Tensor] = []
    dst_parts: list[torch.Tensor] = []
    count_parts: list[torch.Tensor] = []
    by_kind: dict[str, int] = {}
    owner_of_row = torch.arange(rows_total, dtype=torch.int64, device=device)   # ONE column
    for kind in lens.counted_relation_kinds:  # loop-ok: the lens's DECLARED counted relation kinds - a closed set of at most the dataset declaration's kinds (7 today), never a row or an edge
        table = ingestion.relations.kind(kind)
        csr = table.csr(rows_total)
        if csr.nnz == 0:
            by_kind[kind] = 0
            continue
        degree = (csr.indptr[1:] - csr.indptr[:-1]).to(torch.int64)
        owner = torch.repeat_interleave(owner_of_row, degree)
        target = csr.indices.to(torch.int64)
        value = csr.located_count.to(torch.int64)
        a = local_of_global[owner]
        b = local_of_global[target]
        keep = (a >= 0) & (b >= 0) & (a != b)
        a, b, value = a[keep], b[keep], value[keep]
        by_kind[kind] = int(value.sum()) if value.numel() else 0
        # B.16 counts the unordered pair {i, j}: a stored (i -> j) and a stored (j -> i) are two
        # distinct admitted instances of that pair and both count.
        src_parts.append(torch.cat([a, b]))
        dst_parts.append(torch.cat([b, a]))
        count_parts.append(torch.cat([value, value]))
    for spec in lens.derived_relations:  # loop-ok: the lens's DECLARED derived relations - a closed set named in the declaration (at most one today), never a row or an edge
        g_src, g_dst, _ = materialise_derived(ingestion, spec)
        a, b = local_of_global[g_src], local_of_global[g_dst]
        keep = (a >= 0) & (b >= 0) & (a != b)
        a, b = a[keep], b[keep]
        by_kind[spec.kind] = int(a.numel())
        value = torch.ones_like(a)
        src_parts.append(torch.cat([a, b]))
        dst_parts.append(torch.cat([b, a]))
        count_parts.append(torch.cat([value, value]))
    for spec in lens.projected_relations:  # loop-ok: the lens's DECLARED projections - a closed set named in the declaration (at most five today), never a row or an edge
        a, b, value = materialise_projected(ingestion, spec, local_of_global, device)
        by_kind[spec.kind] = int(value.sum()) if value.numel() else 0
        if not a.numel():
            continue
        src_parts.append(torch.cat([a, b]))
        dst_parts.append(torch.cat([b, a]))
        count_parts.append(torch.cat([value, value]))
    if not src_parts:
        empty = torch.empty(0, dtype=torch.int64, device=device)
        return empty, empty, empty, by_kind
    src = torch.cat(src_parts)
    dst = torch.cat(dst_parts)
    value = torch.cat(count_parts)
    width = int(local_of_global.max()) + 1
    key = src * width + dst
    unique, inverse = torch.unique(key, sorted=True, return_inverse=True)
    summed = torch.zeros(unique.numel(), dtype=torch.int64, device=device)
    summed.index_add_(0, inverse, value)
    out_src = torch.div(unique, width, rounding_mode="floor")
    out_dst = unique - out_src * width
    return out_src, out_dst, summed, by_kind


def per_kind_edges(ingestion: Ingestion, lens: LensDeclaration,
                   local_of_global: torch.Tensor, device: torch.device
                   ) -> tuple[tuple[str, ...], torch.Tensor, torch.Tensor,
                              torch.Tensor, torch.Tensor]:
    """B.36's block sums need the DIRECTED per-kind instances, not the symmetrised sum.

    ``_symmetric_counts`` folds every counted kind into one undirected A because that is what
    B.16 weighs. The node table's ``cross`` field is a different object: the located witnesses
    between two ranges, per relation kind AND per direction. Returns
    (kind names, kind id, source local, target local, int64 located count), directed as stored.

    Complexity: O(K E) device work, one pass per counted kind. No Python loop over an edge.
    """
    rows_total = ingestion.store.row_count
    names: list[str] = []
    kind_parts, src_parts, dst_parts, count_parts = [], [], [], []
    owner_of_row = torch.arange(rows_total, dtype=torch.int64, device=device)   # ONE column
    for kind in lens.counted_relation_kinds:  # loop-ok: the lens's DECLARED counted relation kinds - a closed set of at most the dataset declaration's kinds (7 today), never a row or an edge
        table = ingestion.relations.kind(kind)
        csr = table.csr(rows_total)
        index = len(names)
        names.append(kind)
        if csr.nnz == 0:
            continue
        degree = (csr.indptr[1:] - csr.indptr[:-1]).to(torch.int64)
        owner = torch.repeat_interleave(owner_of_row, degree)
        a = local_of_global[owner]
        b = local_of_global[csr.indices.to(torch.int64)]
        keep = (a >= 0) & (b >= 0) & (a != b)
        if not bool(keep.any()):
            continue
        kind_parts.append(torch.full((int(keep.sum()),), index, dtype=torch.int64,
                                     device=device))
        src_parts.append(a[keep])
        dst_parts.append(b[keep])
        count_parts.append(csr.located_count.to(torch.int64)[keep])
    for spec in lens.derived_relations:  # loop-ok: the lens's DECLARED derived relations - a closed set named in the declaration (at most one today), never a row or an edge
        g_src, g_dst, _ = materialise_derived(ingestion, spec)
        a, b = local_of_global[g_src], local_of_global[g_dst]
        keep = (a >= 0) & (b >= 0) & (a != b)
        index = len(names)
        names.append(spec.kind)
        if not bool(keep.any()):
            continue
        kind_parts.append(torch.full((int(keep.sum()),), index, dtype=torch.int64,
                                     device=device))
        src_parts.append(a[keep])
        dst_parts.append(b[keep])
        count_parts.append(torch.ones(int(keep.sum()), dtype=torch.int64, device=device))
    for spec in lens.projected_relations:  # loop-ok: the lens's DECLARED projections, a closed set of the declaration's own kinds
        a, b, value = materialise_projected(ingestion, spec, local_of_global, device)
        index = len(names)
        names.append(spec.kind)
        if not a.numel():
            continue
        kind_parts.append(torch.full((a.numel(),), index, dtype=torch.int64, device=device))
        src_parts.append(a)
        dst_parts.append(b)
        count_parts.append(value)
    if not kind_parts:
        empty = torch.empty(0, dtype=torch.int64, device=device)
        return tuple(names), empty, empty, empty, empty
    return (tuple(names), torch.cat(kind_parts), torch.cat(src_parts), torch.cat(dst_parts),
            torch.cat(count_parts))


def summed_generator_counts(ingestion: Ingestion, lens: LensDeclaration,
                            local_of_global: torch.Tensor, device: torch.device
                            ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor,
                                       dict[str, int], dict[str, Any]]:
    """B.16's A for a lens whose observation map declares BOTH a field effect and typed edges.

    THE GENERATOR OF A FIBRE IS ALL OF ITS DECLARED OBSERVATIONS (section_execution_spec.md:20-27;
    the author, 2026-09-22 16:25). The two families are counted separately - the declared field
    effect by ``content_affinity_counts``, the declared and projected typed edges by
    ``_symmetric_counts`` - each is scaled to UNIT MAXIMUM EXIT RATE, they are summed at the
    declared 1:1 weight and the sum is re-quantised on the lattice of the smallest single-witness
    contribution. ``LensDeclaration.generator_family_sum_rule`` is that exchange rate written as a
    labelled assumption with its provenance and its expiry; this function is the arithmetic.

    The lens's DECLARED ARM selects which families are summed: "both" (default), "field" or
    "relations". An arm of one family is exactly the family's own counts, unscaled - so the
    "field" arm is bit for bit what this lens built before D4, and the "relations" arm is bit for
    bit what a relation lens builds.

    Returns (src local, dst local, int64 count, counts by kind, receipt).
    Complexity: the two families' own, plus one coalescing sort over their union.
    """
    arm = lens.generator_arm
    field_src = field_dst = field_count = None
    affinity_receipt: dict[str, Any] = {}
    by_kind: dict[str, int] = {}
    if lens.content_affinity is not None and arm in ("both", "field"):
        field_src, field_dst, field_count, field_kinds, affinity_receipt = \
            content_affinity_counts(ingestion, lens, local_of_global, device)
        by_kind.update(field_kinds)
    relation_src = relation_dst = relation_count = None
    if arm in ("both", "relations") and (lens.counted_relation_kinds or lens.derived_relations
                                         or lens.projected_relations):
        relation_src, relation_dst, relation_count, relation_kinds = _symmetric_counts(
            ingestion, lens, local_of_global, device)
        by_kind.update(relation_kinds)
    families = [("field", field_src, field_dst, field_count),
                ("relations", relation_src, relation_dst, relation_count)]
    live = [row for row in families if row[1] is not None and int(row[1].numel())]
    if not live:
        raise LensRefusal("LENS-GENERATOR-ARM-PRODUCED-NO-EDGE", lens=lens.lens_id, arm=arm)
    width = int(local_of_global.max()) + 1
    exit_rates: dict[str, float] = {}
    scales: dict[str, float] = {}
    if len(live) == 1:
        name, src, dst, count = live[0]
        degree = torch.zeros(width, dtype=torch.int64, device=device)
        degree.index_add_(0, dst, count)
        exit_rates[name] = float(degree.max())
        scales[name] = 1.0
        receipt = {"arm": arm, "families": [name], "family_exit_rates": exit_rates,
                   "family_scales": scales, "quantum": 1.0,
                   "exchange_rate": lens.generator_family_sum_rule,
                   "content_affinity": affinity_receipt,
                   "located_counts_by_kind": dict(sorted(by_kind.items()))}
        return src, dst, count, by_kind, receipt
    # kappa_f = the family's own MAXIMUM EXIT RATE, and the scale that takes it to one
    values = []
    for name, src, dst, count in live:  # loop-ok: the TWO declared generator families
        degree = torch.zeros(width, dtype=torch.int64, device=device)
        degree.index_add_(0, dst, count)
        kappa = float(degree.max())
        exit_rates[name] = kappa
        scales[name] = 1.0 / kappa if kappa > 0 else 1.0
        values.append(count.to(torch.float64) * scales[name])
    src = torch.cat([row[1] for row in live])
    dst = torch.cat([row[2] for row in live])
    value = torch.cat(values)
    quantum = min(scales.values())
    key = src * width + dst
    unique, inverse = torch.unique(key, sorted=True, return_inverse=True)
    summed = torch.zeros(unique.numel(), dtype=torch.float64, device=device)
    summed.index_add_(0, inverse, value)
    count = torch.round(summed / quantum).to(torch.int64).clamp(min=1)
    out_src = torch.div(unique, width, rounding_mode="floor")
    out_dst = unique - out_src * width
    receipt = {
        "arm": arm, "families": [row[0] for row in live],
        "family_exit_rates": exit_rates, "family_scales": scales, "quantum": quantum,
        "exchange_rate": lens.generator_family_sum_rule,
        "content_affinity": affinity_receipt,
        "located_counts_by_kind": dict(sorted(by_kind.items())),
        "undirected_pairs_after_the_sum": int(unique.numel()) // 2,
        # each family arrives already coalesced by pair, so what the coalescing removes is
        # exactly the pairs BOTH families witness - the measured overlap of the two currencies
        "directed_pairs_carried_by_both_families": int(key.numel()) - int(unique.numel()),
        "pi_derived_from": ("the SUMMED degree d_j = sum_i A_ij over both families (B.19), never "
                            "one family's own; ``pi_used_in_generator`` stays False"),
    }
    return out_src, out_dst, count, by_kind, receipt


def carrier_field(ingestion: Ingestion, lens: LensDeclaration,
                  local_of_global: torch.Tensor, device: torch.device
                  ) -> tuple[torch.Tensor, torch.Tensor, float]:
    """The carrier's OWN field value per row: the mean of its leaves' stored unit vectors.

    D.1: the encoder is the measurement interface and the leaf is where it measures (P1). A
    carrier row's field value is therefore an observation DERIVED from its own leaves and from
    nothing else - no second encode, no query, no corpus-wide statistic. Rows with no leaf are
    left at zero and are named by their absence, exactly as B.18 names a row with no witness.

    Returns (field [M, d] float32 unit rows, has_field [M] bool, eps_max of the stored form).
    Complexity: O(L d) device, one scatter over the leaves. No per-leaf Python.
    """
    affinity = lens.content_affinity
    assert affinity is not None
    axes = [spec for spec in ingestion.declaration.content_axes
            if spec.axis == affinity.axis]       # loop-ok: the declared content axes (1 today)
    if not axes:
        raise LensRefusal("LENS-CONTENT-AXIS-UNDECLARED", lens=lens.lens_id, axis=affinity.axis)
    spec = axes[0]
    table = ingestion.content
    if table is None or not len(table):
        raise LensRefusal("LENS-CONTENT-AXIS-NOT-BUILT", lens=lens.lens_id, axis=affinity.axis)
    from ..record.content import axis_matrix

    rows = torch.from_numpy(np.ascontiguousarray(axis_matrix(table, spec))).to(device)
    carrier_global = torch.from_numpy(np.ascontiguousarray(table.carrier_row)).to(device)
    local = local_of_global.index_select(0, carrier_global)
    keep = local >= 0
    m = int(local_of_global.max()) + 1
    field = torch.zeros((m, int(rows.shape[1])), dtype=torch.float32, device=device)
    field.index_add_(0, local[keep], rows[keep])
    norm = field.norm(dim=1)
    has_field = norm > 0
    field = field / norm.clamp(min=1e-12)[:, None]
    eps = table.axes.get(spec.axis, {}).get("eps")
    eps_max = float(eps.max()) if eps is not None and eps.size else 0.0
    return field, has_field, eps_max


def _jurisdiction_key(ingestion: Ingestion, lens: LensDeclaration,
                      local_of_global: torch.Tensor, device: torch.device) -> torch.Tensor:
    """The declared SOURCE JURISDICTION code of every carrier row. O(M). Never a Python loop."""
    affinity = lens.content_affinity
    assert affinity is not None
    m = int(local_of_global.max()) + 1
    key = torch.full((m,), -1, dtype=torch.int64, device=device)
    for index, kind in enumerate(lens.carrier_row_kinds):  # loop-ok: the lens's DECLARED carrier row kinds, a closed set of at most the declaration's kinds
        table = ingestion.store.table(kind)
        if not len(table):
            continue
        local = local_of_global.index_select(0, table.global_ordinals)
        code = table.column(affinity.jurisdiction_column).to(torch.int64)
        live = local >= 0
        key[local[live]] = index * (int(code.max()) + 2) + code[live]
    return key


def content_affinity_counts(ingestion: Ingestion, lens: LensDeclaration,
                            local_of_global: torch.Tensor, device: torch.device
                            ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor,
                                       dict[str, int], dict[str, Any]]:
    """B.16's A for a VECTOR lens: the declared field effect, sparse, batched, never N x N.

    ``ContentAffinity`` states the construction and why it is not the score. Here is the shape:
    the carrier is put in DECLARED JURISDICTION order, the inner products are taken in blocks of
    rows against the column window their jurisdictions occupy (so the largest object ever formed
    is one block by one window, bounded by the declared dense share), each row keeps its k =
    ceil(ln n) nearest neighbours inside its own jurisdiction, sigma is the k-th neighbour
    distance, and the symmetric effect is quantised to int64 quanta of the stored form's own eps.

    Complexity: O(sum_j n_j^2 d / blocks) device work with n_j the jurisdiction sizes - linear in
    the corpus for a fixed container size and never quadratic in it. Peak: one block window.
    """
    from .blocks import DENSE_SHARE_BYTES        # imported here: blocks imports this module

    affinity = lens.content_affinity
    assert affinity is not None
    field, has_field, eps_max = carrier_field(ingestion, lens, local_of_global, device)
    key = _jurisdiction_key(ingestion, lens, local_of_global, device)
    live = has_field & (key >= 0)
    rows_live = torch.nonzero(live, as_tuple=False).flatten()
    if rows_live.numel() < 2:
        raise LensRefusal("LENS-CONTENT-CARRIER-EMPTY", lens=lens.lens_id)
    order = rows_live[torch.argsort(key[rows_live], stable=True)]
    jsorted = key[order]
    n = int(order.numel())
    x = field.index_select(0, order)
    start_of = torch.searchsorted(jsorted, jsorted, right=False)
    end_of = torch.searchsorted(jsorted, jsorted, right=True)
    size_of = (end_of - start_of).to(torch.float64)
    # k = ceil(ln n_j), the connectivity threshold, read off the record's own sizes
    k_of = torch.ceil(torch.log(size_of.clamp(min=2.0))).to(torch.int64).clamp(min=1)
    k_of = torch.minimum(k_of, (end_of - start_of - 1).clamp(min=1))
    widest = int((end_of - start_of).max())
    # THE BLOCK IS SIZED BY THE WINDOW IT IMPLIES, not by the largest jurisdiction. Rows are in
    # jurisdiction order, so a block of B rows touches a column window of at most B + 2 * widest
    # columns; the product B * (B + 2 * widest) is what the device pays, and it is solved for B
    # against a QUARTER of the declared dense share because the masked top-k holds about four
    # tensors of that shape at once. MEASURED: sizing B by ``share // widest`` alone made B = n
    # on LongMemEval, the window the whole carrier, and the product 9.25 GiB on a 3.68 GiB card.
    elements = max(1, (DENSE_SHARE_BYTES // 4) // 4)
    block = max(1, min(n, int(math.sqrt(widest * widest + elements)) - widest))

    src_parts, dst_parts, dist_parts = [], [], []
    sigma = torch.zeros(n, dtype=torch.float32, device=device)
    for start in range(0, n, block):  # loop-ok: RESOURCE blocks of the jurisdiction-ordered carrier, bounded by the declared dense share - never a step per row or per pair
        stop = min(n, start + block)
        lo = int(start_of[start:stop].min())
        hi = int(end_of[start:stop].max())
        scores = x[start:stop] @ x[lo:hi].T
        columns = torch.arange(lo, hi, dtype=torch.int64, device=device)
        rows_here = torch.arange(start, stop, dtype=torch.int64, device=device)
        valid = ((jsorted[start:stop, None] == jsorted[None, lo:hi])
                 & (rows_here[:, None] != columns[None, :]))
        scores = torch.where(valid, scores, torch.full_like(scores, -2.0))
        del valid
        take = int(min(int(k_of[start:stop].max()), hi - lo))
        best, index = torch.topk(scores, take, dim=1)
        del scores
        rank = torch.arange(take, dtype=torch.int64, device=device)[None, :]
        keep = (rank < k_of[start:stop, None]) & (best > -2.0)
        dist2 = (2.0 - 2.0 * best).clamp(min=0.0)
        last = (k_of[start:stop] - 1).clamp(min=0, max=take - 1)
        sigma[start:stop] = torch.sqrt(dist2.gather(1, last[:, None]).flatten()).clamp(min=1e-6)
        src_parts.append(rows_here[:, None].expand_as(index)[keep])
        dst_parts.append((index + lo)[keep])
        dist_parts.append(dist2[keep])
    src = torch.cat(src_parts)
    dst = torch.cat(dst_parts)
    dist2 = torch.cat(dist_parts)
    # the UNDIRECTED pair, once: the effect's formula is symmetric, so the edge set is the union
    low = torch.minimum(src, dst)
    high = torch.maximum(src, dst)
    pair = torch.unique(low * n + high, sorted=True)
    a_src = torch.div(pair, n, rounding_mode="floor")
    a_dst = pair - a_src * n
    # re-read the distance on the unique pairs, from the field itself (one gather, no lookup)
    delta = (2.0 - 2.0 * (x.index_select(0, a_src) * x.index_select(0, a_dst)).sum(1)
             ).clamp(min=0.0).to(torch.float64)
    effect = torch.exp(-delta / (sigma.index_select(0, a_src).to(torch.float64)
                                 * sigma.index_select(0, a_dst).to(torch.float64)))
    quantum = max(2.0 * eps_max, float(np.finfo(np.float32).eps))
    count = torch.round(effect / quantum).to(torch.int64).clamp(min=1)
    out_src = order.index_select(0, torch.cat([a_src, a_dst]))
    out_dst = order.index_select(0, torch.cat([a_dst, a_src]))
    out_count = torch.cat([count, count])
    receipt = {
        "axis": affinity.axis,
        "jurisdiction_column": affinity.jurisdiction_column,
        "jurisdictions": int(torch.unique(jsorted).numel()),
        "carrier_rows_with_a_field": n,
        "carrier_rows_without_a_field": int((~has_field).sum()),
        "neighbours_k_min": int(k_of.min()), "neighbours_k_max": int(k_of.max()),
        "largest_jurisdiction": widest, "row_block": block,
        "undirected_edges": int(pair.numel()),
        "quantum": quantum, "eps_max_of_the_stored_form": eps_max,
        "effect_min": float(effect.min()) if effect.numel() else 0.0,
        "effect_max": float(effect.max()) if effect.numel() else 0.0,
        "sigma_min": float(sigma.min()), "sigma_max": float(sigma.max()),
        # the line ruling R-3 names, held as a NUMBER: if the effect were the score wearing a
        # second hat, the effect would be a monotone function of the inner product and this
        # rank correlation would be exactly 1. sigma is local, so it is not.
        "effect_vs_inner_product_rank_correlation": _rank_correlation(effect, -delta),
        "generator_model": ("section_execution_spec: symmetric nonnegative zero-diagonal "
                            "affinity A and a positive reference give G_yx = A_yx/(kappa pi_x); "
                            "here kappa pi is B.18's own item-paced d_j, so pi stays DERIVED."),
    }
    return out_src, out_dst, out_count, {affinity.axis: int(out_count.sum())}, receipt


def _rank_correlation(left: torch.Tensor, right: torch.Tensor) -> float:
    """Spearman rank correlation of two equal-length tensors. O(n log n), no pair loop."""
    if left.numel() < 2:
        return 0.0
    n = int(left.numel())
    rank_left = torch.empty(n, dtype=torch.float64, device=left.device)
    rank_right = torch.empty(n, dtype=torch.float64, device=left.device)
    index = torch.arange(n, dtype=torch.float64, device=left.device)
    rank_left[torch.argsort(left)] = index
    rank_right[torch.argsort(right)] = index
    a = rank_left - rank_left.mean()
    b = rank_right - rank_right.mean()
    denom = float(a.norm() * b.norm())
    return float((a * b).sum() / denom) if denom > 0 else 0.0


def _components(src: torch.Tensor, dst: torch.Tensor, n: int,
                device: torch.device) -> torch.Tensor:
    """Connected components by scatter-min label propagation. O(nnz * diameter), vectorised."""
    label = torch.arange(n, dtype=torch.int64, device=device)
    for _ in range(n + 1):
        proposal = label.clone()
        proposal.scatter_reduce_(0, src, label[dst], reduce="amin", include_self=True)
        proposal = proposal[proposal]          # path compression through the current labels
        if bool(torch.equal(proposal, label)):
            return label
        label = proposal
    raise RuntimeError("component labelling did not converge")   # pragma: no cover


def build_lens_generator(ingestion: Ingestion, lens: LensDeclaration) -> LensGenerator:
    """B.16 -> B.18 -> B.19 for one lens over one ingested record.

    Complexity: O(K E log E) device work, O(E) device memory. No M x M object is formed.
    """
    lens.check_against(ingestion.declaration)
    device = ingestion.device
    carrier = _carrier_rows(ingestion, lens)
    local_of_global = torch.full((ingestion.store.row_count,), -1, dtype=torch.int64,
                                 device=device)
    local_of_global[carrier] = torch.arange(carrier.numel(), dtype=torch.int64, device=device)
    src, dst, count, by_kind = _symmetric_counts(ingestion, lens, local_of_global, device)
    n = int(carrier.numel())
    degree = torch.zeros(n, dtype=torch.int64, device=device)
    if count.numel():
        degree.index_add_(0, dst, count)
    seated = degree > 0
    if not bool(seated.any()):
        raise LensRefusal("LENS-CARRIER-HAS-NO-COUNTED-WITNESS", lens=lens.lens_id)
    isolated = carrier[~seated]

    # Re-index onto the seated rows only: B.18 requires d_j > 0, so a row no counted relation
    # witnesses is NOT silently given mass - it is named in ``isolated_global_rows``.
    reindex = torch.full((n,), -1, dtype=torch.int64, device=device)
    reindex[seated] = torch.arange(int(seated.sum()), dtype=torch.int64, device=device)
    keep = seated[src] & seated[dst]
    src, dst, count = reindex[src[keep]], reindex[dst[keep]], count[keep]
    seated_rows = carrier[seated]
    m = int(seated_rows.numel())
    degree = torch.zeros(m, dtype=torch.int64, device=device)
    degree.index_add_(0, dst, count)

    labels = _components(src, dst, m, device)
    unique_labels, component_of = torch.unique(labels, sorted=True, return_inverse=True)
    component_count = int(unique_labels.numel())

    # THE COMPONENT SLICES ARE BUILT ONCE, NOT PER COMPONENT. The old body scanned the whole
    # carrier and the whole edge list for every component (a mask over m rows, a mask over the
    # edges, and an m-wide local index tensor allocated each time), so a lens of C components
    # paid C * (m + E) - 1,482 * (16,632 + 57,636) at LongMemEval-S. Two stable sorts group the
    # rows and the edges by component, the local indices and pi are computed for the whole
    # carrier at once, and the loop below only takes contiguous VIEWS. The pointers are copied
    # to the host ONCE, so no component costs a device synchronisation either.
    row_order = torch.argsort(component_of, stable=True)
    row_ptr = torch.zeros(component_count + 1, dtype=torch.int64, device=device)
    torch.cumsum(torch.bincount(component_of, minlength=component_count), 0, out=row_ptr[1:])
    local_of_row = torch.empty(m, dtype=torch.int64, device=device)
    local_of_row[row_order] = (torch.arange(m, dtype=torch.int64, device=device)
                               - row_ptr[component_of[row_order]])
    # every edge has both endpoints in one component, by construction of the labelling
    edge_component = component_of[src] if src.numel() else src
    edge_order = torch.argsort(edge_component, stable=True)
    edge_ptr = torch.zeros(component_count + 1, dtype=torch.int64, device=device)
    torch.cumsum(torch.bincount(edge_component, minlength=component_count), 0,
                 out=edge_ptr[1:])
    grouped_src = local_of_row[src[edge_order]]
    grouped_dst = local_of_row[dst[edge_order]]
    grouped_count = count[edge_order]
    grouped_rows = seated_rows[row_order]
    grouped_degree = degree[row_order]
    component_total = torch.zeros(component_count, dtype=torch.int64, device=device)
    component_total.index_add_(0, component_of, degree)
    grouped_pi = (grouped_degree.to(torch.float64)
                  / component_total[component_of[row_order]].to(torch.float64))
    row_bounds = row_ptr.tolist()
    edge_bounds = edge_ptr.tolist()
    components: list[ComponentGenerator] = []
    for index in range(component_count):  # loop-ok: one ComponentGenerator VIEW per component - every tensor above was built once for the whole carrier and the body only slices a contiguous range; no device work and no synchronisation per component
        r0, r1 = row_bounds[index], row_bounds[index + 1]
        e0, e1 = edge_bounds[index], edge_bounds[index + 1]
        components.append(ComponentGenerator(
            lens_id=lens.lens_id, component=index, global_rows=grouped_rows[r0:r1],
            src=grouped_src[e0:e1], dst=grouped_dst[e0:e1], count=grouped_count[e0:e1],
            degree=grouped_degree[r0:r1], pi=grouped_pi[r0:r1], device=device))
    return LensGenerator(lens=lens, components=tuple(components),
                         carrier_global_rows=seated_rows, isolated_global_rows=isolated,
                         counts_by_kind=by_kind)
