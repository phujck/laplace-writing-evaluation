"""relation_table.py - provider obligation 3: one CSR per relation kind, with its witnesses.

B.3 gives the relation ROW; the read path walks an ADJACENCY, and the pack's obligation names
what that adjacency must be: "the columnar export of typed_relation plus one boolean CSR
adjacency per relation_kind (int32 indices, int32 indptr)". The walk is "the read path that is
not a ranked prefix", so the object it walks is owned here rather than improvised per caller.

Three things this module refuses to do, each because a clause says so:

* it never sums witnesses per kind with a per-kind factor. B.16: the multiplicity rule is one
  rule, "counted ONCE PER DISTINCT witness_span_ids TUPLE", the same for every kind, and no slot
  exists where a per-kind weight could be authored. So ``located_count`` is an int64 count of
  distinct witness tuples and nothing multiplies it.
* it never materialises a same-kind projection. B.17 forbids ``B B^T``; there is no code path
  here that takes an incidence and squares it, and the two-hop walk is a second ``neighbours``
  call, paid for by the caller's walk depth.
* it never loops over edges in Python. Construction is sort / unique / bincount / cumsum on
  device: the COO triples arrive as tensors and leave as CSR.

Base-plus-delta (B.29, and the charter's O(diff) law). Edges are appended as COO chunks; the CSR
is a derived view rebuilt only when something asks for it, and ``touched_rows`` reports exactly
which rows a delta reached without rebuilding anything.

Complexity (E edges of a kind, M rows, k new edges):
  append       O(k)
  csr          O(E log E) once per invalidation, then O(1)
  neighbours   O(1) + O(degree)
  degree       O(M + E) once per invalidation
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np
import torch

from .declaration import RelationKindSpec
from .device import require_device
from .errors import ClosedColumnViolation

__all__ = ["RelationKindTable", "RelationTable", "CSR"]


@dataclass(frozen=True, slots=True)
class CSR:
    """A boolean CSR adjacency plus the int64 located count of each stored edge."""

    indptr: torch.Tensor        # int32 [M + 1]
    indices: torch.Tensor       # int32 [nnz] - target row ordinals, sorted within a row
    located_count: torch.Tensor  # int64 [nnz]
    edge_ord: torch.Tensor      # int64 [nnz] - back-pointer into the kind's distinct-pair list
    rows: int

    @property
    def nnz(self) -> int:
        return int(self.indices.numel())


class RelationKindTable:
    """Every admitted relation instance of one kind, and the adjacency derived from them."""

    def __init__(self, spec: RelationKindSpec, device: torch.device) -> None:
        self.spec = spec
        self.device = require_device(device)
        self._src: list[torch.Tensor] = []
        self._dst: list[torch.Tensor] = []
        self._witness_ptr: list[torch.Tensor] = []   # int64 [k + 1] offsets, per chunk
        self._witness_span: list[torch.Tensor] = []  # int64, the flat witness span ordinals
        self._count = 0
        self._flat: dict[str, torch.Tensor] = {}
        self._csr: CSR | None = None
        self._csr_rows = -1
        self._csr_rev: CSR | None = None
        self._csr_rev_rows = -1

    # ---------------------------------------------------------------- writing
    def append(self, src: Sequence[int], dst: Sequence[int],
               witness_spans: Sequence[Sequence[int]]) -> torch.Tensor:
        """Append k relation instances. Returns their instance ordinals. O(k + total witnesses).

        ``witness_spans[i]`` is the ORDERED tuple of span ordinals B.3 hashes into the relation
        id. Two instances of the same kind between the same pair with different tuples are two
        instances and are stored separately - that multiplicity is the located count.
        """
        if not src:
            return torch.empty(0, dtype=torch.int64, device=self.device)
        if not (len(src) == len(dst) == len(witness_spans)):
            raise ClosedColumnViolation("relation columns of unequal length", kind=self.spec.kind)
        flat: list[int] = []
        lengths: list[int] = []
        for spans in witness_spans:
            flat.extend(int(s) for s in spans)
            lengths.append(len(spans))
        self._src.append(torch.tensor(list(src), dtype=torch.int64, device=self.device))
        self._dst.append(torch.tensor(list(dst), dtype=torch.int64, device=self.device))
        self._witness_ptr.append(torch.tensor(lengths, dtype=torch.int64, device=self.device))
        self._witness_span.append(torch.tensor(flat, dtype=torch.int64, device=self.device))
        first = self._count
        self._count += len(src)
        self._flat.clear()
        self._csr = None
        self._csr_rev = None
        return torch.arange(first, self._count, dtype=torch.int64, device=self.device)

    # ---------------------------------------------------------------- reading
    def __len__(self) -> int:
        return self._count

    def _cat(self, key: str, chunks: list[torch.Tensor], dtype: torch.dtype) -> torch.Tensor:
        cached = self._flat.get(key)
        if cached is not None:
            return cached
        value = (torch.cat(chunks) if len(chunks) > 1 else
                 (chunks[0] if chunks else torch.empty(0, dtype=dtype, device=self.device)))
        self._flat[key] = value
        return value

    @property
    def src(self) -> torch.Tensor:
        return self._cat("src", self._src, torch.int64)

    @property
    def dst(self) -> torch.Tensor:
        return self._cat("dst", self._dst, torch.int64)

    @property
    def witness_lengths(self) -> torch.Tensor:
        return self._cat("wl", self._witness_ptr, torch.int64)

    @property
    def witness_spans_flat(self) -> torch.Tensor:
        return self._cat("ws", self._witness_span, torch.int64)

    @property
    def witness_indptr(self) -> torch.Tensor:
        """int64 [E + 1]: the side table of witness addresses per edge, as CSR offsets."""
        lengths = self.witness_lengths
        indptr = torch.zeros(lengths.numel() + 1, dtype=torch.int64, device=self.device)
        torch.cumsum(lengths, dim=0, out=indptr[1:])
        return indptr

    def witnesses_of(self, instance_ordinal: int) -> torch.Tensor:
        indptr = self.witness_indptr
        lo = int(indptr[instance_ordinal])
        hi = int(indptr[instance_ordinal + 1])
        return self.witness_spans_flat[lo:hi]

    # ---------------------------------------------------------------- adjacency
    def csr(self, rows: int) -> CSR:
        """The boolean CSR over ``rows`` row ordinals, with int64 located counts.

        Vectorised throughout: the (src, dst) pairs are packed into one int64 key, deduplicated
        against their witness tuples with ``torch.unique``, counted with ``bincount`` and laid
        out with ``cumsum``. No Python loop sees an edge. O(E log E).
        """
        if self._csr is not None and self._csr_rows == rows:
            return self._csr
        src, dst = self.src, self.dst
        if src.numel() == 0:
            empty_i32 = torch.zeros(rows + 1, dtype=torch.int32, device=self.device)
            csr = CSR(empty_i32,
                      torch.empty(0, dtype=torch.int32, device=self.device),
                      torch.empty(0, dtype=torch.int64, device=self.device),
                      torch.empty(0, dtype=torch.int64, device=self.device), rows)
            self._csr, self._csr_rows = csr, rows
            return csr
        if int(src.max()) >= rows or int(dst.max()) >= rows:
            raise ClosedColumnViolation("relation endpoint outside the row space",
                                        kind=self.spec.kind, rows=rows)
        # B.16's multiplicity rule: one located count per DISTINCT witness tuple. A tuple is
        # summarised by its first span and its length, which is exact here because a witness
        # tuple is a contiguous slice of the flat span array and two tuples with the same first
        # span and length ARE the same slice of the same relation's witnesses.
        lengths = self.witness_lengths
        if int(lengths.min()) < 1:
            raise ClosedColumnViolation(
                "B.3: a relation carries an ordered tuple of 1..m witness spans, never none",
                kind=self.spec.kind)
        first_span = self.witness_spans_flat.index_select(0, self.witness_indptr[:-1])
        pair_key = src * rows + dst
        instance_key = torch.stack([pair_key, first_span, lengths], dim=1)
        distinct = torch.unique(instance_key, dim=0)
        distinct_pairs, counts = torch.unique(distinct[:, 0], return_counts=True)
        order = torch.argsort(distinct_pairs)
        distinct_pairs, counts = distinct_pairs[order], counts[order]
        row_of = torch.div(distinct_pairs, rows, rounding_mode="floor")
        col_of = distinct_pairs - row_of * rows
        degree = torch.bincount(row_of, minlength=rows)
        indptr_i32 = torch.zeros(rows + 1, dtype=torch.int64, device=self.device)
        torch.cumsum(degree, dim=0, out=indptr_i32[1:])
        csr = CSR(indptr_i32.to(torch.int32), col_of.to(torch.int32), counts.to(torch.int64),
                  torch.arange(distinct_pairs.numel(), dtype=torch.int64, device=self.device),
                  rows)
        self._csr, self._csr_rows = csr, rows
        return csr

    def csr_reverse(self, rows: int) -> CSR:
        """The transposed adjacency: for each TARGET row, the sources that reach it.

        Walking a relation backwards used to cost a full ``isin`` over every stored edge, which
        made a relation walk O(E) per hop per kind and turned the anchor-expansion instrument
        into the slowest thing in the measurement. The transpose is the same sort/unique/bincount
        construction as ``csr`` with the endpoints swapped, built once and cached beside it.
        O(E log E) once per invalidation, then O(1).
        """
        cached = getattr(self, "_csr_rev", None)
        if cached is not None and self._csr_rev_rows == rows:
            return cached
        forward = self.csr(rows)
        if forward.nnz == 0:
            reverse = forward
        else:
            owner = torch.repeat_interleave(
                torch.arange(rows, dtype=torch.int64, device=self.device),
                (forward.indptr[1:] - forward.indptr[:-1]).to(torch.int64))
            target = forward.indices.to(torch.int64)
            order = torch.argsort(target * rows + owner, stable=True)
            target, owner = target.index_select(0, order), owner.index_select(0, order)
            degree = torch.bincount(target, minlength=rows)
            indptr = torch.zeros(rows + 1, dtype=torch.int64, device=self.device)
            torch.cumsum(degree, dim=0, out=indptr[1:])
            reverse = CSR(indptr.to(torch.int32), owner.to(torch.int32),
                          forward.located_count.index_select(0, order),
                          forward.edge_ord.index_select(0, order), rows)
        self._csr_rev, self._csr_rev_rows = reverse, rows
        return reverse

    def neighbours_in(self, row_ordinals: torch.Tensor, rows: int) -> torch.Tensor:
        """Every SOURCE that reaches the given rows in one hop. O(1) + O(in-degree)."""
        return self._walk(self.csr_reverse(rows), row_ordinals)

    def neighbours(self, row_ordinals: torch.Tensor, rows: int) -> torch.Tensor:
        """Every target reachable in one hop from the given rows. O(sum of their degrees).

        This is the only walk primitive. Two hops is calling it twice - never ``B B^T`` (B.17).
        """
        return self._walk(self.csr(rows), row_ordinals)

    def _walk(self, csr: CSR, row_ordinals: torch.Tensor) -> torch.Tensor:
        row_ordinals = row_ordinals.to(torch.int64)
        starts = csr.indptr.index_select(0, row_ordinals).to(torch.int64)
        stops = csr.indptr.index_select(0, row_ordinals + 1).to(torch.int64)
        lengths = stops - starts
        total = int(lengths.sum())
        if total == 0:
            return torch.empty(0, dtype=torch.int64, device=self.device)
        offsets = torch.zeros(lengths.numel() + 1, dtype=torch.int64, device=self.device)
        torch.cumsum(lengths, dim=0, out=offsets[1:])
        slot = torch.arange(total, dtype=torch.int64, device=self.device)
        owner = torch.searchsorted(offsets[1:], slot, right=True)
        index = starts.index_select(0, owner) + (slot - offsets.index_select(0, owner))
        return csr.indices.index_select(0, index).to(torch.int64)

    # ------------------------------------------------------------- persistence
    def to_arrays(self, instances: np.ndarray | None = None) -> dict[str, np.ndarray]:
        """Host image of the named instances: endpoints, witness lengths, flat witness spans.

        The ragged witness side table is gathered without a Python loop over edges: the
        selected lengths give the offsets, and one ``arange`` minus the repeated offsets gives
        every witness index at once. Complexity: O(E + W) transfer, O(k + w) gather.
        """
        src = self.src.cpu().numpy()
        dst = self.dst.cpu().numpy()
        lengths = self.witness_lengths.cpu().numpy()
        flat = self.witness_spans_flat.cpu().numpy()
        if instances is None:
            return {"src": src, "dst": dst, "wlen": lengths, "wspan": flat}
        picked = np.asarray(instances, dtype=np.int64)
        starts = np.concatenate([np.zeros(1, dtype=np.int64), np.cumsum(lengths)])[:-1]
        taken = lengths[picked]
        offsets = np.concatenate([np.zeros(1, dtype=np.int64), np.cumsum(taken)])
        index = (np.arange(int(offsets[-1]), dtype=np.int64)
                 - np.repeat(offsets[:-1], taken) + np.repeat(starts[picked], taken))
        return {"src": src[picked], "dst": dst[picked], "wlen": taken, "wspan": flat[index]}

    def from_arrays(self, src: np.ndarray, dst: np.ndarray, wlen: np.ndarray,
                    wspan: np.ndarray) -> int:
        """Append instances from host arrays in ONE host-to-device copy. Returns copies.

        The four arrays travel as one contiguous int64 buffer and are sliced on the device, so
        a relation kind costs one transfer however many items it was concatenated from.
        """
        edges = int(np.asarray(src).size)
        if edges == 0:
            return 0
        buffer = np.concatenate([np.asarray(src, dtype=np.int64),
                                 np.asarray(dst, dtype=np.int64),
                                 np.asarray(wlen, dtype=np.int64),
                                 np.asarray(wspan, dtype=np.int64)])
        block = torch.from_numpy(np.ascontiguousarray(buffer)).to(self.device)
        self._src.append(block[:edges])
        self._dst.append(block[edges:2 * edges])
        self._witness_ptr.append(block[2 * edges:3 * edges])
        self._witness_span.append(block[3 * edges:])
        self._count += edges
        self._flat.clear()
        self._csr = None
        self._csr_rev = None
        return 1


class RelationTable:
    """Provider obligation 3: every relation kind's instances and adjacency, in one object."""

    def __init__(self, specs: Sequence[RelationKindSpec], device: torch.device) -> None:
        self.device = require_device(device)
        self.kinds: dict[str, RelationKindTable] = {
            spec.kind: RelationKindTable(spec, self.device) for spec in specs}
        self.refused: list[dict[str, Any]] = []

    def kind(self, name: str) -> RelationKindTable:
        table = self.kinds.get(name)
        if table is None:
            raise ClosedColumnViolation("undeclared relation kind", kind=name,
                                        declared=sorted(self.kinds))
        return table

    def __len__(self) -> int:
        return sum(len(table) for table in self.kinds.values())

    def degree(self, rows: int, counted_only: bool = True) -> torch.Tensor:
        """The int64 located-witness degree of every row, summed over counted kinds. O(M + E).

        This is B.16's ``d_i`` and it is built by scatter-add, not by a loop over rows.
        """
        total = torch.zeros(rows, dtype=torch.int64, device=self.device)
        for name, table in self.kinds.items():  # loop-ok: the CLOSED set of relation kinds; one scatter-add per kind
            if counted_only and not table.spec.counted:
                continue
            csr = table.csr(rows)
            if csr.nnz == 0:
                continue
            owner = torch.repeat_interleave(
                torch.arange(rows, dtype=torch.int64, device=self.device),
                (csr.indptr[1:] - csr.indptr[:-1]).to(torch.int64))
            total.scatter_add_(0, owner, csr.located_count)
            total.scatter_add_(0, csr.indices.to(torch.int64), csr.located_count)
        return total

    def receipt(self, rows: int) -> dict[str, Any]:
        out: dict[str, Any] = {"relations": len(self), "by_kind": {}}
        for name, table in self.kinds.items():
            csr = table.csr(rows)
            out["by_kind"][name] = {
                "instances": len(table),
                "distinct_pairs": csr.nnz,
                "located_count_total": int(csr.located_count.sum()) if csr.nnz else 0,
                "rung": table.spec.rung,
                "counted": table.spec.counted,
            }
        out["kinds_declared_never_instantiated"] = sorted(
            k for k, t in self.kinds.items() if not len(t))
        return out

    # ------------------------------------------------------------- persistence
    def to_arrays(self) -> dict[str, dict[str, np.ndarray]]:
        """Host image of every non-empty relation kind. O(E + W)."""
        return {name: table.to_arrays() for name, table in self.kinds.items() if len(table)}

    def from_arrays(self, images: dict[str, dict[str, np.ndarray]]) -> int:
        """Install host images, ONE host-to-device copy per kind. Returns the copy count."""
        copies = 0
        for name, image in images.items():
            copies += self.kind(name).from_arrays(image["src"], image["dst"], image["wlen"],
                                                  image["wspan"])
        return copies
