"""typed_row_store.py - provider obligation 2: one columnar table per row kind.

The default this replaces, named in the packet so it can be refused out loud: "a list of Python
dicts per passage with an embedding attached, or a pandas/NetworkX object". Neither can carry a
closed column list, neither puts the typed fields where a mask can act on them at GPU speed, and
both invite a new column the moment a question does not compile. What is here instead:

* ONE table per declared row kind, its column list FROZEN by the dataset declaration (B.5);
* every column an integer tensor on the device - int64 ids and time keys, int8/int16 enum codes,
  int32 dictionary codes - and no Python object anywhere in the numeric path;
* every row carrying ``witness_span``, ``producing_rung`` and ``extractor``, so B.2's "a span
  witnesses it", B.11's rung ledger and B.4's re-verification are properties of the store rather
  than of a convention;
* append RESERVES in a growing buffer, so adding one turn to a million-row table costs one
  row to write and nothing to read back (B.29); a reader is a view, never a concatenation.

Row identity is B.2's ``chash({kind, fields, witness_span_id})`` over DECODED values, minted on
demand for the rows a caller names. The store's dense ordinals are a local addressing scheme and
never an identity: they are assigned in mint order across all kinds, which is what keeps them
stable under append and therefore usable as CSR indices.

Complexity summary (N rows in a table, c declared columns, k rows in a batch):
  append_rows          O(k * c) host encode + O(k) device writes + O(witness bytes) checking
  column / witness     O(1) - a view of the column's reserving buffer
  row_ids(ordinals)    O(|ordinals| * c)
  duplicate_rows       O(N c log N) on device
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import torch

from ..ids import chash
from .columns import NULL_OF, decode_column, encode_column
from .content_blob import ContentBlobStore
from .declaration import DatasetDeclaration, RowKindSpec
from .device import require_device
from .errors import ClosedColumnViolation
from .identity import IDENTITY_NULL, IDENTITY_WORDS, words_of_ids
from .spans import SpanTable, _Growable
from .witness import WitnessCandidate, check_candidates

__all__ = ["TypedTable", "TypedRowStore", "Admission", "RefusedProposal"]

_DICT_NULL = NULL_OF[torch.int32]


@dataclass(frozen=True, slots=True)
class RefusedProposal:
    """B.4's refused proposal: counted, addressed, never stored and never retried looser."""

    kind: str
    extractor_id: str
    rung: int
    witness_span_ord: int
    predicate_id: str
    fields: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class Admission:
    """What one append admitted and what it refused."""

    kind: str
    global_ordinals: torch.Tensor
    local_ordinals: torch.Tensor
    refused: tuple[RefusedProposal, ...] = ()
    positions: tuple[int, ...] = ()      # which offered candidates were admitted, in order

    @property
    def admitted(self) -> int:
        return int(self.global_ordinals.numel())


class _Dictionary:
    """A growing surface dictionary for one dict_utf8 column. Codes are append-only."""

    __slots__ = ("surfaces", "index")

    def __init__(self) -> None:
        self.surfaces: list[str] = []
        self.index: dict[str, int] = {}

    def intern(self, values: Sequence[Any]) -> list[int]:
        codes: list[int] = []
        index, surfaces = self.index, self.surfaces
        for value in values:
            if value is None:
                codes.append(_DICT_NULL)
                continue
            text = str(value)
            code = index.get(text)
            if code is None:
                code = len(surfaces)
                surfaces.append(text)
                index[text] = code
            codes.append(code)
        return codes

    def code_of(self, surface: str) -> int | None:
        return self.index.get(surface)


class TypedTable:
    """One row kind's columnar table: frozen columns, append-only chunks, on device."""

    def __init__(self, spec: RowKindSpec, device: torch.device) -> None:
        self.spec = spec
        self.device = device
        # One reserving buffer per column (record/spans.py:_Growable), not a list of chunks: a
        # reader is then a view rather than a concatenation of everything already stored, which
        # is what keeps the cost of appending one item independent of the store's size.
        self._chunks: dict[str, _Growable] = {
            name: _Growable(device,
                            dtype=torch.int32 if spec.field(name).type == "dict_utf8" else None)
            for name in spec.columns}
        self._dicts: dict[str, _Dictionary] = {
            f.name: _Dictionary() for f in spec.fields if f.type == "dict_utf8"}
        self._witness = _Growable(device, dtype=torch.int64)
        self._rung = _Growable(device, dtype=torch.int8)
        self._extractor = _Growable(device, dtype=torch.int32)
        self._global = _Growable(device, dtype=torch.int64)
        # B.2's identity as a FIXED-WIDTH COLUMN, minted once when the row is admitted
        # (record/identity.py). It is what the persisted tree addresses rows by and what an
        # answer's handles gather, so no read ever re-hashes a row.
        self._identity = _Growable(device, width=IDENTITY_WORDS, dtype=torch.int64)
        self._extractor_dict = _Dictionary()
        self._count = 0

    # ---------------------------------------------------------------- writing
    def _encode(self, name: str, values: Sequence[Any]) -> torch.Tensor:
        spec = self.spec.field(name)
        if spec.type == "dict_utf8":
            return torch.tensor(self._dicts[name].intern(values), dtype=torch.int32,
                                device=self.device)
        return encode_column(values, spec.type, vocabulary=spec.vocabulary,
                             device=self.device, name=name)

    def append(self, records: Sequence[Mapping[str, Any]], witness_span_ords: Sequence[int],
               rung: int, extractor_id: str, global_base: int) -> tuple[torch.Tensor,
                                                                        torch.Tensor]:
        """Append k rows. Returns (global ordinals, local ordinals). O(k * columns)."""
        if len(records) != len(witness_span_ords):
            raise ClosedColumnViolation("every row needs exactly one witness span",
                                        kind=self.spec.kind, rows=len(records),
                                        witnesses=len(witness_span_ords))
        if not records:
            empty = torch.empty(0, dtype=torch.int64, device=self.device)
            return empty, empty
        declared = set(self.spec.columns)
        unexpected = set().union(*(record.keys() for record in records)) - declared
        if unexpected:
            raise ClosedColumnViolation("field outside the closed column list",
                                        kind=self.spec.kind, unexpected=sorted(unexpected),
                                        columns=list(self.spec.columns))
        for name in self.spec.columns:  # loop-ok: the kind's closed column list
            column = [record.get(name) for record in records]
            self._chunks[name].append(self._encode(name, column))
        self._witness.append(torch.tensor(list(witness_span_ords), dtype=torch.int64,
                                          device=self.device))
        n = len(records)
        self._rung.append(torch.full((n,), rung, dtype=torch.int8, device=self.device))
        self._extractor.append(torch.tensor(
            self._extractor_dict.intern([extractor_id] * n), dtype=torch.int32,
            device=self.device))
        first = self._count
        self._count += n
        globals_ = torch.arange(global_base, global_base + n, dtype=torch.int64,
                                device=self.device)
        self._global.append(globals_)
        return globals_, torch.arange(first, self._count, dtype=torch.int64, device=self.device)

    # ---------------------------------------------------------------- reading
    def __len__(self) -> int:
        return self._count

    def column(self, name: str) -> torch.Tensor:
        """The integer tensor of one declared column. Refuses a column outside the list.

        A VIEW of the column's reserving buffer: O(1), no concatenation however many appends
        the table has taken.
        """
        if name not in self._chunks:
            raise ClosedColumnViolation("column outside the closed column list",
                                        kind=self.spec.kind, column=name,
                                        columns=list(self.spec.columns))
        buffer = self._chunks[name]
        if buffer.dtype is None:
            buffer.dtype = torch.int64
        return buffer.view

    @property
    def witness_span(self) -> torch.Tensor:
        return self._witness.view

    @property
    def producing_rung(self) -> torch.Tensor:
        return self._rung.view

    @property
    def extractor_code(self) -> torch.Tensor:
        return self._extractor.view

    @property
    def identity(self) -> torch.Tensor:
        """B.2's identity of every row, int64 ``[n, 4]``, minted at ingestion. O(1), a view."""
        return self._identity.view

    def set_identity(self, words: torch.Tensor) -> None:
        """Append the identity words of the rows just admitted. One device copy. O(k)."""
        self._identity.append(words)
        if len(self._identity) != self._count:
            raise ClosedColumnViolation("the identity column and the row count disagree",
                                        kind=self.spec.kind, rows=self._count,
                                        identities=len(self._identity))

    @property
    def global_ordinals(self) -> torch.Tensor:
        return self._global.view

    def vocabulary(self, name: str) -> tuple[str, ...]:
        """The decode vocabulary of a coded column: the declared enum, or the grown dictionary."""
        spec = self.spec.field(name)
        if spec.type == "enum":
            return spec.vocabulary or ()
        if spec.type == "dict_utf8":
            return tuple(self._dicts[name].surfaces)
        return ()

    def surface_code(self, name: str, surface: str) -> int | None:
        """The code a surface holds in this column, or None. O(1)."""
        spec = self.spec.field(name)
        if spec.type == "dict_utf8":
            return self._dicts[name].code_of(surface)
        if spec.type == "enum" and spec.vocabulary and surface in spec.vocabulary:
            return spec.vocabulary.index(surface)
        return None

    def decode(self, name: str) -> list[Any]:
        """The column's declared values, exactly as they were admitted. O(N)."""
        spec = self.spec.field(name)
        return decode_column(self.column(name), spec.type, self.vocabulary(name))

    def rows(self, ordinals: Iterable[int] | None = None) -> list[dict[str, Any]]:
        """Decoded rows as dicts - for serialisation, comparison and tests, never numerics.

        Only the named rows are decoded (O(|ordinals| x columns)); decoding every column of the
        whole table to pick twenty rows out of it is what this used to do.
        """
        if ordinals is None:
            columns = {name: self.decode(name) for name in self.spec.columns}
            return [{name: columns[name][i] for name in self.spec.columns}
                    for i in range(self._count)]
        indices = list(ordinals)
        selector = torch.tensor(indices, dtype=torch.int64, device=self.device)
        picked = {}
        for name in self.spec.columns:  # loop-ok: the kind's closed column list
            spec = self.spec.field(name)
            picked[name] = decode_column(self.column(name).index_select(0, selector),
                                         spec.type, self.vocabulary(name))
        return [{name: picked[name][position] for name in self.spec.columns}
                for position in range(len(indices))]

    def content_key_matrix(self) -> torch.Tensor:
        """[N, c+1] int64 of every column plus the witness - B.2's identity, vectorised."""
        parts = [self.column(name).to(torch.int64).unsqueeze(1) for name in self.spec.columns]
        parts.append(self.witness_span.unsqueeze(1))
        return torch.cat(parts, dim=1) if parts else torch.empty((self._count, 0),
                                                                 dtype=torch.int64,
                                                                 device=self.device)

    def duplicate_rows(self, span_addresses: torch.Tensor | None = None) -> int:
        """How many rows are not distinct under B.2's identity. O(N c log N) on device.

        ``span_addresses`` is the span table's [n, 3] (blob_ord, start, end) view. It MUST be
        passed to get B.2's identity: the witness column holds a local span ORDINAL, and two
        appends of the same bytes take two ordinals for one address, so a key built on the
        ordinal reports zero duplicates for a store that holds the same row twice. That is
        exactly the bypass this diagnostic exists to catch, so the ordinal form is kept only for
        the callers that already had it and the address form is what ``Ingestion`` uses.
        """
        if self._count == 0:
            return 0
        key = self.content_key_matrix()
        if span_addresses is not None:
            key = torch.cat([key[:, :-1],
                             span_addresses.index_select(0, self.witness_span)], dim=1)
        unique = torch.unique(key, dim=0)
        return self._count - int(unique.shape[0])

    # ------------------------------------------------------------- persistence
    def to_arrays(self, start: int = 0, stop: int | None = None) -> dict[str, Any]:
        """Host image of local rows ``[start, stop)``, with ITEM-LOCAL dictionaries.

        Every surface dictionary in the image is rebuilt over the surfaces this slice actually
        uses, in first-appearance order inside the slice. That is the property that makes a
        per-item slice a pure function of the item: the store's dictionary grows with whatever
        arrived before, and a code taken from it would carry the arrival order into the bytes.
        Global codes are assigned again when the projection is built (``record.segments``).

        Complexity: O(n c) host work, one device->host transfer per column.
        """
        stop = self._count if stop is None else stop
        columns: dict[str, np.ndarray] = {}
        dicts: dict[str, list[str]] = {}
        for name in self.spec.columns:  # loop-ok: the kind's DECLARED columns, one whole-column copy each
            values = self.column(name)[start:stop].cpu().numpy()
            if self.spec.field(name).type == "dict_utf8":
                values, surfaces = _localise(values, self._dicts[name].surfaces, _DICT_NULL)
                dicts[name] = surfaces
            columns[name] = np.ascontiguousarray(values)
        extractor, extractor_ids = _localise(
            self.extractor_code[start:stop].cpu().numpy(), self._extractor_dict.surfaces,
            _DICT_NULL)
        return {
            "kind": self.spec.kind,
            "count": int(stop - start),
            "columns": columns,
            "witness": np.ascontiguousarray(self.witness_span[start:stop].cpu().numpy()),
            "rung": np.ascontiguousarray(self.producing_rung[start:stop].cpu().numpy()),
            "extractor": np.ascontiguousarray(extractor),
            # B.2's identity rides in the image, so a segment carries it and no path downstream
            # re-mints it. It is item-local in nothing: a hash of the row's own content.
            "identity": np.ascontiguousarray(self.identity[start:stop].cpu().numpy()),
            "dicts": dicts,
            "extractor_ids": extractor_ids,
        }

    def from_arrays(self, image: Mapping[str, Any], global_base: int,
                    globals_: np.ndarray | None = None) -> int:
        """Append the host image as ONE chunk with ONE host-to-device copy. Returns copies.

        Every column, the witness, the rung and the extractor code travel in a single int64
        host buffer and are split and cast back to their declared dtypes ON THE DEVICE, so the
        number of transfers is one per TABLE and not one per column or one per item. The
        image's item-local dictionaries are interned into this table's dictionary here, which
        is where a global code is assigned.

        Complexity: O(n c) host, one transfer of 8(c+3)n bytes.
        """
        n = int(image["count"])
        if n == 0:
            return 0
        names = list(self.spec.columns)
        parts: list[np.ndarray] = []
        for name in names:
            values = np.asarray(image["columns"][name])
            if self.spec.field(name).type == "dict_utf8":
                values = _reintern(values, image["dicts"][name], self._dicts[name], _DICT_NULL)
            parts.append(values.astype(np.int64, copy=False))
        parts.append(np.asarray(image["witness"]).astype(np.int64, copy=False))
        parts.append(np.asarray(image["rung"]).astype(np.int64, copy=False))
        parts.append(_reintern(np.asarray(image["extractor"]), list(image["extractor_ids"]),
                               self._extractor_dict, _DICT_NULL).astype(np.int64, copy=False))
        identity = np.asarray(image["identity"]).astype(np.int64, copy=False)
        if identity.shape != (n, IDENTITY_WORDS):
            raise ClosedColumnViolation("a segment carries no B.2 identity column",
                                        kind=self.spec.kind, rows=n,
                                        shape=list(identity.shape))
        # The identity's four words travel in the SAME host buffer as the columns, so the
        # transfer count is still exactly one per table.
        parts.append(identity[:, 0])
        parts.append(identity[:, 1])
        parts.append(identity[:, 2])
        parts.append(identity[:, 3])
        parts.append((np.arange(global_base, global_base + n, dtype=np.int64)
                      if globals_ is None
                      else np.asarray(globals_).astype(np.int64, copy=False)))
        buffer = np.stack(parts, axis=1)
        device_block = torch.from_numpy(np.ascontiguousarray(buffer)).to(self.device)
        for position, name in enumerate(names):  # loop-ok: the kind's closed column list
            spec = self.spec.field(name)
            dtype = (torch.int32 if spec.type == "dict_utf8"
                     else _dtype_of_column(spec, device_block[:, position]))
            self._chunks[name].append(device_block[:, position].to(dtype))
        self._witness.append(device_block[:, len(names)])
        self._rung.append(device_block[:, len(names) + 1].to(torch.int8))
        self._extractor.append(device_block[:, len(names) + 2].to(torch.int32))
        identity_at = len(names) + 3
        self._identity.append(device_block[:, identity_at:identity_at + IDENTITY_WORDS])
        self._global.append(device_block[:, identity_at + IDENTITY_WORDS])
        self._count += n
        return 1


class TypedRowStore:
    """Provider obligation 2: the columnar export of B.2's typed rows, one table per kind."""

    def __init__(self, declaration: DatasetDeclaration, blobs: ContentBlobStore,
                 spans: SpanTable, device: torch.device | str | None = None) -> None:
        self.declaration = declaration
        self.blobs = blobs
        self.spans = spans
        self.device = require_device(device if device is not None else spans.device)
        self.tables: dict[str, TypedTable] = {
            spec.kind: TypedTable(spec, self.device) for spec in declaration.row_kinds}
        self.refused: list[RefusedProposal] = []
        self._next_global = 0
        self._kind_of_global: list[tuple[int, str]] = []     # (global_base, kind), mint order

    # ---------------------------------------------------------------- writing
    def append_rows(self, kind: str, records: Sequence[Mapping[str, Any]],
                    witness_span_ords: Sequence[int], *, rung: int, extractor_id: str,
                    witness_options: Mapping[str, Any] | None = None) -> Admission:
        """Check every candidate against its witness bytes, then admit the ones that pass.

        Fail-closed is here and nowhere else: a False verdict removes the row from the batch,
        records a ``RefusedProposal`` and moves on. Complexity: O(k*c) host encode plus the
        predicate's O(witness bytes).
        """
        spec = self.declaration.row_kind(kind)
        predicate_id = spec.witness_predicate_id
        candidates = [WitnessCandidate(fields=record, spans=(int(span),))
                      for record, span in zip(records, witness_span_ords)]
        verdicts = check_candidates(predicate_id, self.blobs, self.spans, candidates,
                                    witness_options)
        admitted_records, admitted_spans, refused, positions = [], [], [], []
        for position, (candidate, verdict) in enumerate(zip(candidates, verdicts)):
            if verdict:
                admitted_records.append(candidate.fields)
                admitted_spans.append(candidate.spans[0])
                positions.append(position)
            else:
                refused.append(RefusedProposal(kind, extractor_id, rung, candidate.spans[0],
                                               predicate_id, dict(candidate.fields)))
        self.refused.extend(refused)
        table = self.tables[kind]
        base = self._next_global
        first_local = len(table)
        globals_, locals_ = table.append(admitted_records, admitted_spans, rung, extractor_id,
                                         base)
        if admitted_records:
            # THE MINT, AND THE ONLY ONE (record/identity.py): B.2's identity is a function of
            # the row's own kind, fields and witness, so it is computed here, once, when the
            # row is admitted - never again by a read. ``row_ids`` is the single definition of
            # that hash and it is called on this batch alone, so the cost is O(k c) in the rows
            # arriving and not O(N) in the store.
            words = words_of_ids(self.row_ids(kind, range(first_local, len(table))))
            table.set_identity(torch.as_tensor(words, dtype=torch.int64, device=self.device))
            self._kind_of_global.append((base, kind))
            self._next_global += len(admitted_records)
        return Admission(kind, globals_, locals_, tuple(refused), tuple(positions))

    def identity_by_global(self) -> torch.Tensor:
        """The record's identity column indexed by GLOBAL ORDINAL, int64 ``[row_count, 4]``.

        One scatter per declared row kind. This is what the persisted tree's rank order is
        written in and what ``identity.ordinals_of_identity`` joins against on a reopen.
        Complexity: O(N), no host transfer.
        """
        out = torch.full((max(self._next_global, 1), IDENTITY_WORDS), IDENTITY_NULL,
                         dtype=torch.int64, device=self.device)
        for _kind, table in self.tables.items():  # loop-ok: the DECLARED row kinds, one whole-column scatter each
            if not len(table):
                continue
            out[table.global_ordinals] = table.identity
        return out[:self._next_global] if self._next_global else out[:0]

    # ---------------------------------------------------------------- reading
    def __len__(self) -> int:
        return self._next_global

    def share_dictionary(self, column: str, kinds: Sequence[str]) -> None:
        """Make several kinds encode one column through ONE dictionary.

        Without this, ``question_id`` on a turn and on a session are two dictionaries and their
        codes are incomparable, so a join between the kinds would have to go through strings -
        a per-row host loop in the middle of the numeric path. Sharing the dictionary makes the
        join an integer comparison. It must be called before the first append of those kinds.
        """
        shared = self.tables[kinds[0]]._dicts[column]
        for kind in kinds[1:]:
            table = self.tables[kind]
            if len(table):
                raise ClosedColumnViolation("dictionaries are shared before the first append",
                                            kind=kind, column=column, rows=len(table))
            table._dicts[column] = shared

    def table(self, kind: str) -> TypedTable:
        table = self.tables.get(kind)
        if table is None:
            raise ClosedColumnViolation("undeclared row kind", kind=kind,
                                        declared=sorted(self.tables))
        return table

    @property
    def row_count(self) -> int:
        return self._next_global

    def local_of_global(self, kind: str) -> torch.Tensor:
        """A dense map from this kind's global ordinals to its local ones. O(N)."""
        table = self.table(kind)
        mapping = torch.full((self._next_global,), -1, dtype=torch.int64, device=self.device)
        mapping[table.global_ordinals] = torch.arange(len(table), dtype=torch.int64,
                                                      device=self.device)
        return mapping

    def kind_of_row(self, global_ordinal: int) -> str:
        """Which kind a global ordinal belongs to. O(number of appends)."""
        found = None
        for base, kind in self._kind_of_global:
            if base <= global_ordinal:
                found = kind
            else:
                break
        if found is None:
            raise ClosedColumnViolation("global ordinal outside the store",
                                        ordinal=global_ordinal, rows=self._next_global)
        return found

    def row_id(self, kind: str, local_ordinal: int) -> str:
        """B.2: ``chash({kind, fields, witness_span_id})`` for one row."""
        return self.row_ids(kind, [local_ordinal])[0]

    def row_ids(self, kind: str, local_ordinals: Sequence[int] | None = None) -> list[str]:
        """B.2 identities for the named rows. Complexity: O(|ordinals| * columns).

        A ``span_ref`` FIELD is hashed as the ADDRESS it names - (content handle, start, end) -
        and never as the ordinal that happens to name it here. MEASURED 2026-09-22: a span
        ordinal is a per-process addressing scheme, and the persisted record stores each item's
        DISTINCT witnessed byte ranges (62,644 against an ingestion's 90,341 at 10 LongMemEval
        haystacks), so opening the record in a second process renumbers every one of them. With
        the ordinal in the hash, 5,186 of 33,373 rows - every row of a kind that declares a
        span_ref field - changed identity across the process boundary while the record's content
        digest was equal: the same turn read ``content_span`` 605 in one process and 56 in the
        other. B.2 says a row is its kind, its FIELDS and its witness, and a field that means a
        byte range is that byte range; ``content_digests`` already reads the column this way
        (segments.py:944-948) and ``duplicate_rows`` was re-keyed from the ordinal to the
        address in F2 for the same reason.
        """
        table = self.table(kind)
        indices = list(range(len(table))) if local_ordinals is None else list(local_ordinals)
        decoded = table.rows(indices)
        selector = torch.tensor(indices, dtype=torch.int64, device=self.device)
        witness = table.witness_span.index_select(0, selector)
        span_ids = self.spans.span_ids(witness)
        for name in table.spec.columns:  # loop-ok: the kind's closed column list
            if table.spec.field(name).type != "span_ref":
                continue
            column = table.column(name).index_select(0, selector)
            live = column >= 0
            addresses = self.spans.addresses(column[live])
            positions = torch.nonzero(live).flatten().tolist()
            for position, address in zip(positions, addresses):  # loop-ok: the named rows
                decoded[position][name] = [address[0], int(address[1]), int(address[2])]
        return [chash({"kind": kind, "fields": _canonical(fields), "witness_span_id": span_id})
                for fields, span_id in zip(decoded, span_ids)]

    # ---------------------------------------------------------------- receipts
    def rung_counts(self) -> dict[str, dict[str, int]]:
        """B.11's rung ledger: rows by producing rung, per kind. O(N)."""
        report: dict[str, dict[str, int]] = {}
        for kind, table in self.tables.items():
            if not len(table):
                continue
            rung = table.producing_rung
            report[kind] = {f"rung_{name}": int((rung == code).sum())
                            for code, name in ((0, "a"), (1, "b"), (2, "c"))}
            report[kind]["rows"] = len(table)
        return report

    def receipt(self) -> dict[str, Any]:
        return {
            "dataset_id": self.declaration.dataset_id,
            "dataset_declaration_hash": self.declaration.declaration_hash,
            "rows": self._next_global,
            "rows_by_kind": {k: len(t) for k, t in self.tables.items()},
            "by_rung": self.rung_counts(),
            "refused_proposals": len(self.refused),
            "refused_by_predicate": _counted(r.predicate_id for r in self.refused),
            "refused_by_kind": _counted(r.kind for r in self.refused),
            "kinds_declared_never_instantiated": sorted(
                k for k, t in self.tables.items() if not len(t)),
        }

    # ------------------------------------------------------------- persistence
    def shared_dictionary_groups(self) -> list[dict[str, Any]]:
        """Which kinds encode one column through ONE dictionary object (``share_dictionary``).

        Sharing is a property of the live objects, not of the declaration, so it has to be
        recorded or a re-opened store would give ``question_id`` a private dictionary per kind
        and every cross-kind join would go back through strings. O(kinds * columns).
        """
        groups: dict[str, dict[int, list[str]]] = {}
        for kind, table in self.tables.items():
            for column, dictionary in table._dicts.items():
                groups.setdefault(column, {}).setdefault(id(dictionary), []).append(kind)
        out: list[dict[str, Any]] = []
        for column, by_object in sorted(groups.items()):
            for members in by_object.values():
                if len(members) > 1:
                    out.append({"column": column, "kinds": sorted(members)})
        return out

    def to_arrays(self) -> dict[str, Any]:
        """Host image of every non-empty table, plus the dictionary sharing. O(N c)."""
        return {"kinds": [t.to_arrays() for t in self.tables.values() if len(t)],
                "shared": self.shared_dictionary_groups()}

    def from_arrays(self, images: Sequence[Mapping[str, Any]], *,
                    shared: Sequence[Mapping[str, Any]] = ()) -> int:
        """Install per-kind host images. ONE host-to-device copy per kind; returns the count.

        ORDINALS ARE REPRODUCED, NOT REASSIGNED (J2's escalated defect). An image that carries
        a ``global`` array is installed AT THOSE ORDINALS - the ones the ingestion that built
        the record assigned and persisted in its manifest rows - so a record opened in a second
        process holds the same layout as the one that stored it. An image without that array
        (a whole-store round trip inside one process) still gets the old contiguous block per
        kind. ``row_count`` is then one past the largest ordinal installed, which is what every
        dense ``[row_count]`` map is sized by. Complexity: O(N c).
        """
        for entry in shared:
            kinds = [k for k in entry["kinds"] if k in self.tables]
            if len(kinds) > 1 and all(not len(self.tables[k]) for k in kinds):
                self.share_dictionary(entry["column"], kinds)
        copies = 0
        for image in images:
            table = self.table(image["kind"])
            base = self._next_global
            given = image.get("global")
            copies += table.from_arrays(image, base, given)
            if int(image["count"]):
                start = base if given is None else int(np.asarray(given).min())
                stop = (base + int(image["count"]) if given is None
                        else int(np.asarray(given).max()) + 1)
                self._kind_of_global.append((start, image["kind"]))
                self._next_global = max(self._next_global, stop)
        self._kind_of_global.sort()
        return copies


def _dtype_of_column(spec: Any, _values: torch.Tensor) -> torch.dtype:
    """The declared dtype of a column, from ``columns._dtype_for`` so the two cannot drift."""
    from .columns import _dtype_for
    return _dtype_for(spec.type, spec.vocabulary)


def _localise(codes: np.ndarray, surfaces: Sequence[str], null: int) -> tuple[np.ndarray,
                                                                             list[str]]:
    """Re-code a slice against its OWN surfaces, in first-appearance order. O(n log n), no loop
    over rows: the distinct codes are found by ``np.unique`` and mapped by ``searchsorted``."""
    codes = np.asarray(codes)
    live = codes != null
    values = codes[live]
    out = codes.astype(np.int32, copy=True)
    if values.size == 0:
        return out, []
    _, first = np.unique(values, return_index=True)
    order = values[np.sort(first)]
    rank = np.argsort(order)
    out[live] = rank[np.searchsorted(order[rank], values)].astype(np.int32)
    return out, [str(surfaces[int(code)]) for code in order]


def _reintern(codes: np.ndarray, surfaces: Sequence[str], dictionary: _Dictionary,
              null: int) -> np.ndarray:
    """The inverse of ``_localise``: intern the image's own surfaces and remap its codes."""
    out = np.asarray(codes).astype(np.int64, copy=True)
    if not surfaces:
        return out
    mapping = np.array(dictionary.intern(list(surfaces)), dtype=np.int64)
    live = out != null
    out[live] = mapping[out[live]]
    return out


def _canonical(fields: Mapping[str, Any]) -> dict[str, Any]:
    """Field values in a form ``chash`` can serialise: dates as ISO text, everything else as is."""
    out: dict[str, Any] = {}
    for name, value in fields.items():
        out[name] = value.isoformat() if hasattr(value, "isoformat") else value
    return out


def _counted(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts
