"""anchor_index.py - provider obligation 4: surface form -> resolved ROW IDS, built at ingest.

C.3's sentence is the whole design: "an anchor is a resolved typed row id, never a lexical
occurrence at query time". Seven C clauses consume this index and no clause builds it, and the
pack names its absence as "exactly the route back to dense anchoring" - because a read path with
no anchors has nothing to start a walk from and falls back to similarity.

So the index is built HERE, at rungs (a)/(b), out of the DECLARED surface set:

* ``anchor_columns`` per row kind names which typed columns carry surfaces. On the toy those are
  subject / object / entity / place, which is why the postings come out equal to the fixture's
  ``MENTIONS`` without a single string being matched against a question.
* the field alias table folds declared aliases onto their target surface BEFORE the postings are
  built, so 'I' and 'we' resolve to the same principal row set and a question never resolves an
  alias at read time.
* a posting is (surface, row ordinal, the row's witness span), deduplicated: one surface names a
  row ONCE however many of its columns carry that surface. The witness is what makes a posting
  checkable - the packet's "every row and every edge is re-verified against the bytes".

Construction is vectorised: the surface codes are already integer columns, so the whole index is
a gather, a mask, a ``torch.unique`` and a ``cumsum``. Nothing here reads a string per row.

Complexity (N rows, a anchor columns, P postings, V surfaces):
  build      O(N a log(N a)) on device
  postings   O(1) + O(df)
  resolve    O(log V) host lookup
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import torch

from .columns import NULL_OF
from .declaration import DatasetDeclaration
from .device import require_device
from .errors import UnknownSurface
from .typed_row_store import TypedRowStore

__all__ = ["AnchorIndex"]


@dataclass(frozen=True, slots=True)
class Postings:
    """The posting list of one surface: row ordinals and the witness span of each."""

    surface: str
    row_ordinals: torch.Tensor      # int32, sorted
    witness_spans: torch.Tensor     # int64, aligned with row_ordinals

    @property
    def document_frequency(self) -> int:
        return int(self.row_ordinals.numel())


class AnchorIndex:
    """Sorted surface vocabulary -> CSR postings of int32 row ids, with a witness per posting."""

    def __init__(self, vocabulary: tuple[str, ...], indptr: torch.Tensor, indices: torch.Tensor,
                 witness: torch.Tensor, document_frequency: torch.Tensor,
                 rung: int, device: torch.device) -> None:
        self.vocabulary = vocabulary
        self.indptr = indptr                     # int32 [V + 1]
        self.indices = indices                   # int32 [P] - GLOBAL row ordinals
        self.witness = witness                   # int64 [P]
        self.document_frequency = document_frequency   # int32 [V]
        self.rung = rung
        self.device = device
        self._surface_ord = {surface: i for i, surface in enumerate(vocabulary)}
        # Base-plus-delta (the charter's O(diff) law). An append lands in the delta - new
        # surfaces take ordinals after the base vocabulary and new postings are held as COO -
        # so adding one item costs that item, not a rebuild of P postings. ``compact`` folds
        # the delta back into a sorted base when someone wants the compact form.
        self._delta_vocabulary: list[str] = []
        self._delta: torch.Tensor = torch.empty((0, 3), dtype=torch.int64, device=device)

    # ---------------------------------------------------------------- building
    @classmethod
    def build(cls, store: TypedRowStore, declaration: DatasetDeclaration, *,
              rung: int = 0) -> "AnchorIndex":
        """Build the index from the declared surface set. Complexity: O(N a log(N a))."""
        device = require_device(store.device)
        surface_set = declaration.surface_set
        alias_of: dict[str, str] = {row.surface: row.target_name
                                    for row in declaration.alias_table.rows
                                    if row.target_kind == "surface"}
        anchor_columns = {kind: columns for kind, columns in surface_set.anchor_columns.items()
                          if len(store.table(kind))}

        # Pass 1: the vocabulary, SORTED, as the obligation requires. A discovery-ordered
        # vocabulary would make the index's layout depend on the order items happened to arrive.
        collected: set[str] = set()
        for kind, columns in anchor_columns.items():
            table = store.table(kind)
            for column in columns:
                collected.update(alias_of.get(s, s) for s in table.vocabulary(column))
        surfaces = tuple(sorted(collected))
        surface_ord = {surface: i for i, surface in enumerate(surfaces)}

        # Pass 2: the postings, entirely on device.
        triples: list[torch.Tensor] = []
        for kind, columns in anchor_columns.items():
            table = store.table(kind)
            row_ords = table.global_ordinals
            witness = table.witness_span
            for column in columns:
                vocabulary = table.vocabulary(column)
                if not vocabulary:
                    continue
                codes = table.column(column)
                null = NULL_OF[codes.dtype]
                # code -> surface ordinal as a dense int64 lookup, so the map is one gather.
                lookup = torch.tensor([surface_ord[alias_of.get(s, s)] for s in vocabulary],
                                      dtype=torch.int64, device=device)
                keep = codes != null
                if not bool(keep.any()):
                    continue
                selected = codes[keep].to(torch.int64)
                triples.append(torch.stack([lookup.index_select(0, selected),
                                            row_ords[keep], witness[keep]], dim=1))

        vocabulary_size = len(surfaces)
        if not triples:
            zero = torch.zeros(vocabulary_size + 1, dtype=torch.int32, device=device)
            return cls(surfaces, zero,
                       torch.empty(0, dtype=torch.int32, device=device),
                       torch.empty(0, dtype=torch.int64, device=device),
                       torch.zeros(vocabulary_size, dtype=torch.int32, device=device),
                       rung, device)
        stacked = torch.cat(triples, dim=0)
        # An anchor is a resolved ROW: one posting per (surface, row), whichever column named it.
        # unique(dim=0) sorts lexicographically, which lays the postings out in CSR order for free.
        distinct = torch.unique(stacked[:, :2], dim=0)
        witness_by_pair = torch.zeros(distinct.shape[0], dtype=torch.int64, device=device)
        # One witness per surviving pair, chosen by ``amin`` rather than by whichever scatter
        # landed last: a posting's witness is the LOWEST-ordinal span that named the row, which
        # is deterministic and so survives a rebuild byte-identically (B.6).
        key_all = stacked[:, 0] * (store.row_count + 1) + stacked[:, 1]
        key_distinct = distinct[:, 0] * (store.row_count + 1) + distinct[:, 1]
        slot = torch.searchsorted(key_distinct, key_all)
        witness_by_pair.scatter_reduce_(0, slot, stacked[:, 2], reduce="amin",
                                        include_self=False)
        degree = torch.bincount(distinct[:, 0], minlength=vocabulary_size)
        indptr = torch.zeros(vocabulary_size + 1, dtype=torch.int64, device=device)
        torch.cumsum(degree, dim=0, out=indptr[1:])
        return cls(surfaces, indptr.to(torch.int32), distinct[:, 1].to(torch.int32),
                   witness_by_pair, degree.to(torch.int32), rung, device)

    # ---------------------------------------------------------------- reading
    def __len__(self) -> int:
        return len(self.vocabulary)

    @property
    def posting_count(self) -> int:
        return int(self.indices.numel())

    def surface_ordinal(self, surface: str) -> int:
        found = self._surface_ord.get(surface)
        if found is None:
            raise UnknownSurface("surface is not in the anchor vocabulary", surface=surface,
                                 vocabulary_size=len(self.vocabulary))
        return found

    def ordinal_of(self, surface: str, default: int = -1) -> int:
        """The surface's ordinal, or ``default`` if it is not in the vocabulary. O(1)."""
        return self._surface_ord.get(surface, default)

    def extend(self, store: TypedRowStore, row_ordinals: torch.Tensor) -> tuple[str, ...]:
        """Add postings for newly minted rows only. Returns the surfaces whose lists changed.

        Complexity: O(k * a) for k new rows - independent of the P postings already held, which
        is what makes an append O(diff) rather than a rebuild.
        """
        if row_ordinals.numel() == 0:
            return ()
        declaration = store.declaration
        alias_of = {row.surface: row.target_name for row in declaration.alias_table.rows
                    if row.target_kind == "surface"}
        wanted = set(row_ordinals.tolist())
        triples: list[torch.Tensor] = []
        touched: set[str] = set()
        for kind, columns in declaration.surface_set.anchor_columns.items():
            table = store.table(kind)
            if not len(table):
                continue
            mask = torch.isin(table.global_ordinals, row_ordinals)
            if not bool(mask.any()):
                continue
            rows = table.global_ordinals[mask]
            witness = table.witness_span[mask]
            for column in columns:
                codes = table.column(column)[mask]
                null = NULL_OF[codes.dtype]
                vocabulary = table.vocabulary(column)
                keep = codes != null
                if not bool(keep.any()):
                    continue
                surfaces = [alias_of.get(vocabulary[c], vocabulary[c])
                            for c in codes[keep].tolist()]
                ordinals = [self._ordinal_for_append(s) for s in surfaces]
                touched.update(surfaces)
                triples.append(torch.stack([
                    torch.tensor(ordinals, dtype=torch.int64, device=self.device),
                    rows[keep], witness[keep]], dim=1))
        _ = wanted
        if triples:
            self._delta = torch.cat([self._delta] + triples, dim=0)
        return tuple(sorted(touched))

    def _ordinal_for_append(self, surface: str) -> int:
        found = self._surface_ord.get(surface)
        if found is not None:
            return found
        ordinal = len(self.vocabulary) + len(self._delta_vocabulary)
        self._delta_vocabulary.append(surface)
        self._surface_ord[surface] = ordinal
        return ordinal

    @property
    def delta_postings(self) -> int:
        return int(self._delta.shape[0])

    def compact(self) -> dict[str, int]:
        """Fold the append delta back into the sorted base, so ``resolve`` returns to the CSR.

        ``extend`` is O(diff) and leaves the appended postings as a COO delta; while that delta
        is non-empty ``resolve`` must take the per-surface merge path, which costs O(k * delta)
        instead of one gather. Compaction is the deliberate, measured rebuild that buys the fast
        path back: it is NEVER called by ``extend`` (that would make every append a whole-index
        rebuild, the charter's forbidden move 7), and it is a no-op on an index with no delta.

        The base ordinals are preserved and the delta's new surfaces keep the ordinals ``extend``
        already handed out, so nothing that holds a surface ordinal is invalidated. Returns what
        moved. Complexity: O((P + delta) log (P + delta)) on device.
        """
        moved = {"delta_postings_folded": self.delta_postings,
                 "surfaces_before": len(self.vocabulary),
                 "postings_before": self.posting_count}
        if not self._delta_vocabulary and self.delta_postings == 0:
            moved.update({"surfaces_after": len(self.vocabulary),
                          "postings_after": self.posting_count, "rebuilt": 0})
            return moved
        vocabulary = self.vocabulary + tuple(self._delta_vocabulary)
        size = len(vocabulary)
        base_rows = self.indices.to(torch.int64)
        owner = torch.repeat_interleave(
            torch.arange(len(self.vocabulary), dtype=torch.int64, device=self.device),
            (self.indptr[1:] - self.indptr[:-1]).to(torch.int64))
        stacked = torch.cat([
            torch.stack([owner, base_rows, self.witness], dim=1), self._delta], dim=0)
        # One posting per (surface, row) - C.3's rule - with the lowest-ordinal witness, the same
        # deterministic choice ``build`` makes, so a compacted index equals a rebuilt one.
        pairs = torch.unique(stacked[:, :2], dim=0)
        width = int(pairs[:, 1].max()) + 1 if pairs.numel() else 1
        key_all = stacked[:, 0] * width + stacked[:, 1]
        key_pairs = pairs[:, 0] * width + pairs[:, 1]
        slot = torch.searchsorted(key_pairs, key_all)
        witness = torch.zeros(pairs.shape[0], dtype=torch.int64, device=self.device)
        witness.scatter_reduce_(0, slot, stacked[:, 2], reduce="amin", include_self=False)
        degree = torch.bincount(pairs[:, 0], minlength=size)
        indptr = torch.zeros(size + 1, dtype=torch.int64, device=self.device)
        torch.cumsum(degree, dim=0, out=indptr[1:])
        self.vocabulary = vocabulary
        self.indptr = indptr.to(torch.int32)
        self.indices = pairs[:, 1].to(torch.int32)
        self.witness = witness
        self.document_frequency = degree.to(torch.int32)
        self._delta_vocabulary = []
        self._delta = torch.empty((0, 3), dtype=torch.int64, device=self.device)
        self._surface_ord = {surface: i for i, surface in enumerate(vocabulary)}
        moved.update({"surfaces_after": size, "postings_after": self.posting_count,
                      "rebuilt": 1})
        return moved

    def postings(self, surface: str) -> Postings:
        """The resolved row ids a surface anchors to, base plus delta. O(df)."""
        ordinal = self.surface_ordinal(surface)
        if ordinal < len(self.vocabulary):
            lo, hi = int(self.indptr[ordinal]), int(self.indptr[ordinal + 1])
            rows, witness = self.indices[lo:hi].to(torch.int64), self.witness[lo:hi]
        else:
            rows = torch.empty(0, dtype=torch.int64, device=self.device)
            witness = torch.empty(0, dtype=torch.int64, device=self.device)
        if self.delta_postings:
            hit = self._delta[:, 0] == ordinal
            if bool(hit.any()):
                pairs = torch.cat([torch.stack([rows, witness], dim=1), self._delta[hit, 1:]],
                                  dim=0)
                pairs = torch.unique(pairs, dim=0)          # sorted by row, then by witness
                first = torch.ones(pairs.shape[0], dtype=torch.bool, device=self.device)
                first[1:] = pairs[1:, 0] != pairs[:-1, 0]   # one posting per resolved row (C.3)
                rows, witness = pairs[first, 0], pairs[first, 1]
        return Postings(surface, rows.to(torch.int32), witness)

    def resolve(self, surfaces: Sequence[str]) -> torch.Tensor:
        """Union of the postings of several surfaces, as sorted int64 row ordinals.

        Vectorised over the requested surfaces: one gather, one unique. O(sum df + k log k).
        """
        ordinals = [self._surface_ord[s] for s in surfaces if s in self._surface_ord]
        if not ordinals:
            return torch.empty(0, dtype=torch.int64, device=self.device)
        if self.delta_postings:
            # With an uncompacted delta the CSR is not the whole index; take the per-surface
            # path, which merges base and delta, rather than reading a stale layout.
            found = [self.postings(s).row_ordinals.to(torch.int64) for s in surfaces
                     if s in self._surface_ord]
            return torch.unique(torch.cat(found)) if found else \
                torch.empty(0, dtype=torch.int64, device=self.device)
        index = torch.tensor(ordinals, dtype=torch.int64, device=self.device)
        starts = self.indptr.index_select(0, index).to(torch.int64)
        stops = self.indptr.index_select(0, index + 1).to(torch.int64)
        lengths = stops - starts
        total = int(lengths.sum())
        if total == 0:
            return torch.empty(0, dtype=torch.int64, device=self.device)
        offsets = torch.zeros(lengths.numel() + 1, dtype=torch.int64, device=self.device)
        torch.cumsum(lengths, dim=0, out=offsets[1:])
        slot = torch.arange(total, dtype=torch.int64, device=self.device)
        owner = torch.searchsorted(offsets[1:], slot, right=True)
        flat = starts.index_select(0, owner) + (slot - offsets.index_select(0, owner))
        return torch.unique(self.indices.index_select(0, flat).to(torch.int64))

    def as_mapping(self) -> dict[str, list[int]]:
        """Postings as plain lists - for comparison against a fixture, never for numerics."""
        indptr = self.indptr.tolist()
        indices = self.indices.tolist()
        return {surface: indices[indptr[i]:indptr[i + 1]]
                for i, surface in enumerate(self.vocabulary)}

    def receipt(self) -> dict[str, int]:
        return {"surfaces": len(self.vocabulary), "postings": self.posting_count,
                "rung": self.rung,
                "max_document_frequency": int(self.document_frequency.max())
                if len(self.vocabulary) else 0}
