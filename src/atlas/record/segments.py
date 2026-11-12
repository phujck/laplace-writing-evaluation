"""segments.py - what ingestion BUILT, kept. The record's per-item segments and their ledger.

The author, 2026-09-21 night: "Surely the point of ingestion is to create the structure
reconstruction can use. _why_ throw it away?" Until this module there was no ``save`` and no
``load`` anywhere in ``atlas.record``: ``ItemCache`` was a Python dict that died with the
process, so "reads material once" and O(diff) were only ever true INSIDE one run. This module is
the missing half, and it is deliberately small:

* a SEGMENT is the host image of exactly one item's contribution to the record - its spans, its
  typed rows, its relation instances - serialised deterministically. Its bytes are a pure
  function of ``(the item's bytes, the extractor roster hash, the dataset declaration hash)``
  and of nothing else: every string dictionary inside it is rebuilt over the surfaces that item
  uses, every span ordinal is an index into the item's own spans, and every relation endpoint is
  ``(declared kind index, the item's own local ordinal)``. Ingest two items in either order and
  the two segment keys are the same, which is the one property that makes the store a cache.
* a MANIFEST is one appended row per item, thin, in arrival order: the item's content hash, the
  roster and declaration hashes, its segment key, what it contributed, and what it supersedes.
* the STORE is ``atlas.store.CompressedHive`` and ``append_jsonl`` - the store's own FORM,
  leaning on none of its authority, seat or custody machinery (the bootstrap), so that adopting
  this record later is the same content addresses rather than a translation.

WHAT IS NOT PERSISTED, on purpose. The device tensors, the CSR adjacencies and the anchor
postings are PROJECTIONS (B.6). They are rebuilt by ``open_record`` from the segments, by
concatenating the host images and making ONE host-to-device copy per table; persisting them
would store the same content three times, which is the storage cost the author refused. The
identity a projection is checked against is ``content_digests``, which reads the record through
its own identities - row fields, witness ADDRESSES, relation endpoints by kind and local
ordinal - and therefore does not depend on which ordinals a given run happened to assign.

GATES WITHOUT WASTE. What is true by construction is proved once in a fixture test
(``atlas/tests/test_record_persistence.py``: the same two items in both orders give the same
segment keys) and never checked again at run time. The two run-time gates are cheap, run at
mint, and run on the diff only: every row's witness span lies inside the item's own spans, and
every relation instance an item owns has both endpoints among that item's own rows. Their cost
is timed and is a field of the receipt.
"""

from __future__ import annotations

import json
import struct
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import torch

from ..ids import canonical_json, chash, hash_bytes
from ..store import CompressedHive, append_jsonl, write_atomic
from .content_blob import ContentBlob, ContentBlobStore
from .declaration import DatasetDeclaration
from .device import peak_device_bytes, require_device, reset_peak_device_bytes
from .errors import MalformedSource
from .ingestion import Ingestion, ItemMark

__all__ = [
    "SEGMENT_FORMAT", "MANIFEST_ROW_SCHEMA", "STORE_META_SCHEMA",
    "Segment", "SegmentStore", "IngestReceipt", "OpenReceipt", "OpenedRecord",
    "cut_segments", "store_ingestion", "open_record", "adopt_deferred", "content_digests",
    "segment_for_item",
]

SEGMENT_FORMAT = "atlas.record.segment/1"
MANIFEST_ROW_SCHEMA = "atlas.record.manifest-row/1"
STORE_META_SCHEMA = "atlas.record.segment-store/1"

_MAGIC = b"ATLASSEG"
_HEADER_LENGTH = struct.Struct("<I")


# --------------------------------------------------------------------------- serialisation
def _pack(arrays: Mapping[str, np.ndarray]) -> tuple[list[dict[str, Any]], bytes]:
    """Arrays -> (sorted entry table, one payload). Little-endian, no pickle. O(total bytes)."""
    entries: list[dict[str, Any]] = []
    blocks: list[bytes] = []
    offset = 0
    for name in sorted(arrays):
        array = np.ascontiguousarray(arrays[name])
        array = array.astype(array.dtype.newbyteorder("<"), copy=False)
        raw = array.tobytes()
        entries.append({"name": name, "dtype": array.dtype.str, "shape": list(array.shape),
                        "offset": offset, "nbytes": len(raw)})
        blocks.append(raw)
        offset += len(raw)
    return entries, b"".join(blocks)


def _unpack(entries: Sequence[Mapping[str, Any]], payload: bytes) -> dict[str, np.ndarray]:
    out: dict[str, np.ndarray] = {}
    for entry in entries:
        dtype = np.dtype(entry["dtype"])
        count = int(np.prod(entry["shape"])) if entry["shape"] else 0
        block = np.frombuffer(payload, dtype=dtype, count=count, offset=int(entry["offset"]))
        out[entry["name"]] = block.reshape(tuple(entry["shape"]))
    return out


@dataclass(frozen=True, slots=True)
class Segment:
    """One item's persisted contribution: a header and its arrays, exactly as they were cut."""

    header: dict[str, Any]
    arrays: dict[str, np.ndarray]

    @classmethod
    def encode(cls, header: Mapping[str, Any], arrays: Mapping[str, np.ndarray]) -> bytes:
        entries, payload = _pack(arrays)
        body = dict(header)
        body["arrays"] = entries
        head = canonical_json(body).encode("utf-8")
        return _MAGIC + _HEADER_LENGTH.pack(len(head)) + head + payload

    @classmethod
    def decode(cls, data: bytes) -> "Segment":
        if data[:len(_MAGIC)] != _MAGIC:
            raise MalformedSource("not a record segment", magic=repr(data[:len(_MAGIC)]))
        start = len(_MAGIC) + _HEADER_LENGTH.size
        size = _HEADER_LENGTH.unpack(data[len(_MAGIC):start])[0]
        header = json.loads(data[start:start + size].decode("utf-8"))
        return cls(header=header, arrays=_unpack(header["arrays"], data[start + size:]))


# --------------------------------------------------------------------------- receipts
@dataclass(frozen=True, slots=True)
class IngestReceipt:
    """What one ingest-and-store cost and what it left on disk. Every field is counted work."""

    dataset_id: str
    items: int
    cache_hits: int
    cache_misses: int
    extractions: int
    item_parses: int
    extraction_seconds: float
    load_seconds: float
    cut_seconds: float
    write_seconds: float
    gate_seconds: float
    segments_written: int
    segments_total: int
    manifest_rows_appended: int
    source_bytes: int
    persisted_bytes: int
    bytes_written: int
    device_bytes: int
    peak_device_bytes: int
    rows: int
    relations: int
    spans: int
    # What the content pass built and cut into these segments, per declared axis. Empty when no
    # axis is declared, which is every store written before this packet.
    content: dict[str, Any] = field(default_factory=dict)

    @property
    def persisted_bytes_per_source_byte(self) -> float:
        return self.persisted_bytes / self.source_bytes if self.source_bytes else 0.0

    @property
    def device_bytes_per_source_byte(self) -> float:
        return self.device_bytes / self.source_bytes if self.source_bytes else 0.0

    def as_dict(self) -> dict[str, Any]:
        out = {name: getattr(self, name) for name in self.__slots__}
        out["persisted_bytes_per_source_byte"] = self.persisted_bytes_per_source_byte
        out["device_bytes_per_source_byte"] = self.device_bytes_per_source_byte
        return out


@dataclass(frozen=True, slots=True)
class OpenReceipt:
    """What opening a persisted record cost, and the two counters the claim rests on."""

    dataset_id: str
    items: int
    extractions: int
    parses: int
    source_reads: int
    hive_gets: int
    hive_bytes: int
    host_to_device_copies: int
    read_seconds: float
    project_seconds: float
    anchor_seconds: float
    gate_seconds: float
    device_bytes: int
    peak_device_bytes: int
    rows: int
    relations: int
    spans: int
    # THE COMPACTNESS RECEIPT ON THE PATH A JUDGE ACTUALLY RUNS (J2's carried residual: these
    # two read 0 on every warm run, so the one lane graded in bytes per source byte had no
    # instrument through the door). Neither costs a source read: ``source_bytes`` is the size
    # of the blobs the hive registered at open, ``persisted_bytes`` is what the store holds on
    # disk, and the ratio is the same quantity ``IngestReceipt`` reports on the cold path.
    source_bytes: int = 0
    persisted_bytes: int = 0
    digests: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__slots__}

    def persisted_bytes_per_source_byte(self) -> float | None:
        return self.persisted_bytes / self.source_bytes if self.source_bytes else None


@dataclass(frozen=True, slots=True)
class OpenedRecord:
    ingestion: Ingestion
    receipt: OpenReceipt


# --------------------------------------------------------------------------- the blob store
class _HiveBlobStore(ContentBlobStore):
    """A blob store whose bytes live in the hive: registered at open, read only when asked.

    Opening a record must not read the source and must not decompress a blob it is not asked
    for - the projection is built from segments alone. So a handle is REGISTERED here with its
    size and media type, and the bytes are fetched from the hive (which re-hashes them against
    the key, so a corrupted blob refuses) the first time a witness address is actually read.
    """

    def __init__(self, hive: CompressedHive) -> None:
        super().__init__()
        self._hive = hive
        self._declared: dict[str, tuple[str, int]] = {}
        self.blob_reads = 0

    def register(self, handle: str, media_type: str, size: int) -> None:
        self._declared[handle] = (media_type, int(size))

    def __contains__(self, handle: str) -> bool:
        return handle in self._declared or super().__contains__(handle)

    def __len__(self) -> int:
        return len(self._declared)

    def handles(self) -> tuple[str, ...]:
        return tuple(self._declared)

    def total_bytes(self) -> int:
        return sum(size for _, size in self._declared.values())

    def blob(self, handle: str) -> ContentBlob:
        declared = self._declared.get(handle)
        if declared is None:
            return super().blob(handle)
        if not super().__contains__(handle):
            self.blob_reads += 1
            data = self._hive.get(handle)          # re-hashed against the key by the hive
            self._blobs[handle] = ContentBlob(handle, declared[0], len(data),
                                              "", _data=data)
        return self._blobs[handle]


# --------------------------------------------------------------------------- the store
class SegmentStore:
    """A thin ledger beside a verified compressed content hive. The store's FORM, not its rules.

    Layout, all of it independently readable::

        <root>/store.json      the dataset's declaration hash and dictionary sharing
        <root>/manifest.jsonl  one appended row per item, in arrival order
        <root>/hive/aa/<sha>.zlib   segments and item blobs, keyed by their uncompressed bytes
    """

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.hive = CompressedHive(self.root / "hive")
        self.manifest_path = self.root / "manifest.jsonl"
        self.meta_path = self.root / "store.json"

    # ------------------------------------------------------------------ meta
    def meta(self) -> dict[str, Any]:
        if not self.meta_path.is_file():
            return {}
        return json.loads(self.meta_path.read_text(encoding="utf-8"))

    def write_meta(self, meta: Mapping[str, Any]) -> None:
        write_atomic(self.meta_path, canonical_json(dict(meta)).encode("utf-8"))

    # ------------------------------------------------------------------ ledger
    def rows(self) -> list[dict[str, Any]]:
        """The manifest in arrival order. Complexity: O(items)."""
        if not self.manifest_path.is_file():
            return []
        with self.manifest_path.open("r", encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def cache_index(self) -> dict[str, str]:
        """B.28's key -> segment key: the extraction cache, as a persisted mapping. O(items)."""
        return {row["item_cache_key"]: row["segment_key"] for row in self.rows()}

    def append_rows(self, rows: Sequence[Mapping[str, Any]]) -> int:
        return append_jsonl(self.manifest_path, rows) if rows else 0

    # ------------------------------------------------------------------ bytes
    def put(self, data: bytes) -> tuple[str, int]:
        """Put bytes in the hive; return (key, bytes actually written). O(len(data))."""
        key = hash_bytes(data)
        if self.hive.has(key):
            return key, 0
        self.hive.put(data)
        return key, self.hive.key_path(key).stat().st_size

    def get(self, key: str) -> bytes:
        return self.hive.get(key)

    def persisted_bytes(self) -> int:
        return sum(path.stat().st_size for path in self.root.rglob("*") if path.is_file())


# --------------------------------------------------------------------------- cutting
class _SpanMap:
    """One item's spans, in a canonical order, and the map from global ordinals onto it.

    THE ORDER IS THE ADDRESS, and the set is the DISTINCT addresses - which is what the span
    table's own docstring says a span table holds ("one row per distinct byte range") and what
    the live append-only table does not enforce. Two things follow, and both are needed:

    * the image cannot depend on WHEN a span was minted, so cutting the same item inside a
      batch (where the located-edge spans of the relation pass arrive after every item's rows)
      and cutting it alone in a worker process (where they arrive inside it) give the same
      bytes. That equality is exactly what makes a process pool sound;
    * a byte range minted twice is stored once.

    A global ordinal outside the item is not silently mapped: the lookup checks that what it
    found is what it was asked for, which is the first of the two run-time gates.
    """

    __slots__ = ("addresses", "_sorted", "_local", "count")

    def __init__(self, candidates: np.ndarray, spans_host: np.ndarray) -> None:
        addresses = spans_host[candidates].astype(np.int64, copy=False)
        unique, inverse = np.unique(addresses, axis=0, return_inverse=True)
        order = np.argsort(candidates)
        self.addresses = unique
        self.count = int(unique.shape[0])
        self._sorted = candidates[order]
        self._local = inverse.reshape(-1)[order]

    def of(self, queries: np.ndarray) -> np.ndarray:
        """Global span ordinals -> this item's local span indices. Vectorised, O(k log n)."""
        if queries.size == 0:
            return np.zeros(0, dtype=np.int64)
        position = np.searchsorted(self._sorted, queries)
        if int(position.max()) >= self._sorted.size or not np.array_equal(
                self._sorted[np.minimum(position, self._sorted.size - 1)], queries):
            raise MalformedSource("a span referenced by this item is not one of its own",
                                  referenced=int(queries.size))
        return self._local[position]

    def of_column(self, column: np.ndarray) -> np.ndarray:
        """The same for a ``span_ref`` FIELD, whose null sentinel is negative and passes."""
        out = np.asarray(column).astype(np.int64, copy=True)
        live = out >= 0
        if live.any():
            out[live] = self.of(out[live])
        return out


def _shift_span_column(column: np.ndarray, offset: int) -> np.ndarray:
    """The inverse: item-local span indices back onto the projection's span table. O(n)."""
    out = np.asarray(column).astype(np.int64, copy=True)
    live = out >= 0
    out[live] = out[live] + offset
    return out


def cut_segments(ingestion: Ingestion, *, extractor_roster_hash: str,
                 ) -> tuple[list[tuple[ItemMark, bytes]], dict[str, Any]]:
    """Cut one segment per marked item. Returns the segments and the gate report.

    The whole attribution is done once for the ingestion and then sliced per item, so the cost
    is O(N + E) plus one lexsort per relation kind, never O(items * rows). The per-item work is
    numpy on host images; there is no Python loop over rows, edges or witnesses anywhere in it.
    """
    declaration = ingestion.declaration
    marks = ingestion.item_marks
    kind_order = {spec.kind: index for index, spec in enumerate(declaration.row_kinds)}
    kind_names = [spec.kind for spec in declaration.row_kinds]
    spans_host = ingestion.spans.columns.cpu().numpy()
    span_handles = ingestion.spans.handles()
    rows_total = ingestion.store.row_count

    # --- attribution: which item owns each row, and where in that item it sits
    gate_started = time.perf_counter()
    item_of_row = np.full(rows_total, -1, dtype=np.int64)
    kind_of_row = np.full(rows_total, -1, dtype=np.int64)
    local_of_row = np.full(rows_total, -1, dtype=np.int64)
    globals_by_kind = {kind: table.global_ordinals.cpu().numpy()
                       for kind, table in ingestion.store.tables.items() if len(table)}  # loop-ok: the DECLARED row kinds, one whole-column copy each
    for index, mark in enumerate(marks):  # loop-ok: one step per ITEM (the unit of persistence), never per row
        for kind, lo, hi in mark.row_ranges:  # loop-ok: this item's declared row kinds; the body is whole-array
            ordinals = globals_by_kind[kind][lo:hi]
            item_of_row[ordinals] = index
            kind_of_row[ordinals] = kind_order[kind]
            local_of_row[ordinals] = np.arange(hi - lo, dtype=np.int64)

    # --- attribution: which item owns each relation instance (both endpoints, fail closed)
    # A row that belongs to no mark was ADOPTED from a segment that already holds its edges:
    # it is skipped here, not cut again. An edge whose two endpoints disagree about their item
    # is the real defect - it would make a segment depend on what else is in the store - and it
    # refuses by name. This is the second of the two run-time gates, and it runs on the diff.
    relation_images: dict[str, dict[str, Any]] = {}
    already_stored = 0
    for name, table in ingestion.relations.kinds.items():  # loop-ok: the CLOSED set of relation kinds
        if not len(table):
            continue
        image = table.to_arrays()
        source_item = item_of_row[image["src"]]
        target_item = item_of_row[image["dst"]]
        mixed = source_item != target_item
        if mixed.any():
            raise MalformedSource(
                "relation instances cross item boundaries and cannot be cut into segments",
                kind=name, instances=int(mixed.sum()))
        owned = np.flatnonzero(source_item >= 0)
        already_stored += int(source_item.size - owned.size)
        order = owned[np.argsort(source_item[owned], kind="stable")]
        relation_images[name] = {"image": image, "item": source_item, "order": order,
                                 "bounds": np.searchsorted(source_item[order],
                                                           np.arange(len(marks) + 1))}
    gate_seconds = time.perf_counter() - gate_started

    # --- attribution: which item owns each CONTENT LEAF. A leaf belongs to the item that owns
    # its carrier row, so the attribution is one gather over the table already built above and
    # never a second pass over the corpus. A leaf whose carrier was ADOPTED from a segment is
    # skipped, exactly as an adopted item's relations are: its bytes are already on disk.
    content_image: dict[str, Any] | None = None
    content = getattr(ingestion, "content", None)
    if content is not None and len(content):
        item_of_leaf = item_of_row[content.carrier_row]
        owned = np.flatnonzero(item_of_leaf >= 0)
        order = owned[np.argsort(item_of_leaf[owned], kind="stable")]
        content_image = {"table": content, "order": order,
                         "bounds": np.searchsorted(item_of_leaf[order],
                                                   np.arange(len(marks) + 1)),
                         "already_stored": int(item_of_leaf.size - owned.size)}

    # --- THE ORDINAL LAYOUT, read off the ingestion that assigned it and persisted with the
    # item (J2's escalated defect: ``open_record`` reassigned ordinals kind-major while the
    # persisted tree addressed rows by the ingestion's item-major ones, so on every run after
    # the first the tree named different rows - qasper 966 -> 953). An item's rows occupy ONE
    # contiguous global block, because ``_next_global`` is a single counter and an item is
    # ingested whole; the block's base and the offset of each kind inside it are a fact about
    # this item, so they persist with it and the reopen reproduces them exactly.
    layouts: list[dict[str, Any]] = []
    for mark in marks:  # loop-ok: one step per ITEM; the body is whole-array per declared kind
        entries: list[list[Any]] = []
        for kind, lo, hi in mark.row_ranges:  # loop-ok: this item's declared row kinds
            if hi <= lo:
                continue
            entries.append([kind, int(globals_by_kind[kind][lo]), int(hi - lo)])
        base = min(entry[1] for entry in entries) if entries else -1  # loop-ok: this item's declared row kinds
        total = sum(entry[2] for entry in entries)  # loop-ok: this item's declared row kinds
        covered = np.zeros(max(total, 1), dtype=bool)
        for _kind, first, count in entries:  # loop-ok: this item's declared row kinds
            covered[first - base:first - base + count] = True
        if total and not bool(covered[:total].all()):
            raise MalformedSource(
                "an item's rows are not one contiguous block of global ordinals",
                item=mark.item_content_hash, base=base, rows=total)
        layouts.append({"global_base": base, "rows": total,
                        "kinds": [[kind, first - base, count]
                                  for kind, first, count in entries]})  # loop-ok: this item's declared row kinds

    out: list[tuple[ItemMark, bytes]] = []
    for index, mark in enumerate(marks):
        out.append((mark, _cut_one(ingestion, mark, index, spans_host, span_handles,
                                   kind_of_row, local_of_row, kind_names, relation_images,
                                   extractor_roster_hash, declaration, content_image)))
    report = {"gate_seconds": gate_seconds, "relations_already_stored": already_stored,
              "items": len(marks), "layouts": layouts,
              "content_leaves_cut": (0 if content_image is None
                                     else int(content_image["order"].size)),
              "content_leaves_already_stored": (0 if content_image is None
                                                else content_image["already_stored"])}
    return out, report


def _cut_one(ingestion: Ingestion, mark: ItemMark, index: int, spans_host: np.ndarray,
             span_handles: Sequence[str], kind_of_row: np.ndarray, local_of_row: np.ndarray,
             kind_names: Sequence[str], relation_images: Mapping[str, Any],
             extractor_roster_hash: str, declaration: DatasetDeclaration,
             content_image: Mapping[str, Any] | None = None) -> bytes:
    own_lo, own_hi = mark.span_range
    own_count = own_hi - own_lo

    # --- the edges this item owns, and the spans they witness from outside its own range
    edges: dict[str, dict[str, np.ndarray]] = {}
    used: list[np.ndarray] = []
    for name, packed in relation_images.items():  # loop-ok: the closed set of relation kinds; one slice per kind
        lo, hi = int(packed["bounds"][index]), int(packed["bounds"][index + 1])
        if hi <= lo:
            continue
        picked = packed["order"][lo:hi]
        image = packed["image"]
        starts = np.concatenate([np.zeros(1, dtype=np.int64), np.cumsum(image["wlen"])])[:-1]
        taken = image["wlen"][picked]
        offsets = np.concatenate([np.zeros(1, dtype=np.int64), np.cumsum(taken)])
        gather = (np.arange(int(offsets[-1]), dtype=np.int64)
                  - np.repeat(offsets[:-1], taken) + np.repeat(starts[picked], taken))
        witness = image["wspan"][gather]
        edges[name] = {"src": image["src"][picked], "dst": image["dst"][picked],
                       "wlen": taken, "wspan": witness}
        used.append(witness)

    # --- this item's CONTENT LEAVES. Their spans are minted after every item's rows (the
    # content pass runs once over the whole ingestion), so they sit outside the item's own span
    # RANGE while being entirely inside its own BYTES - the same situation an edge witness from
    # the relation pass is in, and handled by the same mechanism: they join the candidate set
    # that ``_SpanMap`` makes item-local.
    content_rows = np.zeros(0, dtype=np.int64)
    content_table = None
    if content_image is not None:
        bounds = content_image["bounds"]
        content_rows = content_image["order"][int(bounds[index]):int(bounds[index + 1])]
        content_table = content_image["table"]

    used_content = (content_table.span[content_rows]
                    if content_table is not None and content_rows.size
                    else np.zeros(0, dtype=np.int64))
    extra_globals = np.zeros(0, dtype=np.int64)
    if used or used_content.size:
        every = np.unique(np.concatenate(used + [used_content]))
        extra_globals = every[(every < own_lo) | (every >= own_hi)]
    candidates = np.arange(own_lo, own_hi, dtype=np.int64)
    if extra_globals.size:
        candidates = np.concatenate([candidates, extra_globals])
    span_map = _SpanMap(candidates, spans_host)

    # --- the span image: the item's distinct addresses, blob column made item-local
    block = np.array(span_map.addresses, dtype=np.int64, copy=True)
    blob_column = block[:, 0]
    _, first = np.unique(blob_column, return_index=True)
    blob_order = blob_column[np.sort(first)] if blob_column.size else np.zeros(0, dtype=np.int64)
    if blob_column.size:
        rank = np.argsort(blob_order)
        block[:, 0] = rank[np.searchsorted(blob_order[rank], blob_column)]
    handles = [span_handles[int(ordinal)] for ordinal in blob_order]

    arrays: dict[str, np.ndarray] = {"spans": block}
    header_rows: dict[str, Any] = {}
    witness_outside = 0
    for kind, lo, hi in mark.row_ranges:
        table = ingestion.store.table(kind)
        image = table.to_arrays(lo, hi)
        witness = np.asarray(image["witness"])
        witness_outside += int(((witness < own_lo) | (witness >= own_hi)).sum())
        local = span_map.of(witness)
        for name, column in image["columns"].items():
            if table.spec.field(name).type == "span_ref":
                column = span_map.of_column(column)
            arrays[f"rows.{kind}.{name}"] = column
        arrays[f"rows.{kind}.__witness"] = local
        arrays[f"rows.{kind}.__rung"] = image["rung"]
        arrays[f"rows.{kind}.__extractor"] = image["extractor"]
        # B.2's identity, minted once when the row was admitted and stored with it. Nothing
        # downstream - not the tree, not a read's handles - hashes a row again.
        arrays[f"rows.{kind}.__identity"] = image["identity"]
        header_rows[kind] = {"count": int(image["count"]),
                             "columns": list(image["columns"].keys()),
                             "dicts": image["dicts"],
                             "extractor_ids": image["extractor_ids"]}
    if witness_outside:
        raise MalformedSource("a row's witness span lies outside its own item",
                              item=mark.item_content_hash, rows=witness_outside)

    header_relations: dict[str, Any] = {}
    for name, packed in edges.items():  # loop-ok: the closed set of relation kinds; the body is one lexsort per kind
        endpoints = np.stack([kind_of_row[packed["src"]], local_of_row[packed["src"]],
                              kind_of_row[packed["dst"]], local_of_row[packed["dst"]]], axis=1)
        witness = span_map.of(packed["wspan"])
        lengths = packed["wlen"]
        offsets = np.concatenate([np.zeros(1, dtype=np.int64), np.cumsum(lengths)])
        width = int(lengths.max()) if lengths.size else 0
        padded = np.full((lengths.size, width), -1, dtype=np.int64)
        position = (np.arange(witness.size, dtype=np.int64)
                    - np.repeat(offsets[:-1], lengths))
        padded[np.repeat(np.arange(lengths.size, dtype=np.int64), lengths), position] = witness
        keys = [padded[:, column] for column in reversed(range(width))]
        keys.extend([lengths, endpoints[:, 3], endpoints[:, 2], endpoints[:, 1],
                     endpoints[:, 0]])
        order = np.lexsort(tuple(keys))
        sorted_lengths = lengths[order]
        sorted_offsets = np.concatenate([np.zeros(1, dtype=np.int64),
                                         np.cumsum(sorted_lengths)])
        gather = (np.arange(int(sorted_offsets[-1]), dtype=np.int64)
                  - np.repeat(sorted_offsets[:-1], sorted_lengths)
                  + np.repeat(offsets[:-1][order], sorted_lengths))
        arrays[f"rel.{name}.endpoints"] = endpoints[order]
        arrays[f"rel.{name}.wlen"] = sorted_lengths
        arrays[f"rel.{name}.wspan"] = witness[gather]
        header_relations[name] = {"count": int(lengths.size), "witnesses": int(witness.size)}

    header_content: dict[str, Any] = {}
    if content_table is not None and content_rows.size:
        from .content import content_arrays
        content_block, header_content = content_arrays(
            content_table, content_rows, span_map.of(content_table.span[content_rows]),
            local_of_row[content_table.carrier_row[content_rows]], declaration)
        arrays.update(content_block)

    blobs = [{"handle": handle, "media_type": ingestion.blobs.blob(handle).media_type,
              "size": ingestion.blobs.blob(handle).size} for handle in handles]
    header = {
        "format": SEGMENT_FORMAT,
        "dataset_id": declaration.dataset_id,
        "dataset_declaration_hash": declaration.declaration_hash,
        "extractor_roster_hash": extractor_roster_hash,
        "item_content_hash": mark.item_content_hash,
        "item_span": list(mark.item_span),
        "segmenter_id": declaration.segmenter_id,
        "seg_version": declaration.seg_version,
        "blobs": blobs,
        "span_count": int(block.shape[0]),
        "rows": header_rows,
        "relations": header_relations,
        "kind_index": list(kind_names),
    }
    if header_content:
        header["content"] = header_content
    return Segment.encode(header, arrays)


# --------------------------------------------------------------------------- storing
def store_ingestion(store: SegmentStore, ingestion: Ingestion, *,
                    extractor_roster_hash: str, source_bytes: int | None = None,
                    device_bytes: int | None = None) -> IngestReceipt:
    """Cut every marked item into a segment and put it, with its blob, in the store.

    Idempotent by content: a segment whose key is already in the manifest writes nothing and
    appends no row, which is what makes "an unchanged input re-mints nothing" true ACROSS runs
    and not only inside one. Complexity: O(N + E) to cut, O(persisted bytes) to write.

    THE CONTENT PASS RUNS HERE, and it has to run here rather than in the caller. MEASURED
    2026-09-22: with the pass in the front door, ``longmem.ingest`` had already called this
    function once (ingest/longmem.py:355) with no leaves built, so the door's second call cut a
    DIFFERENT segment for the same item and the manifest carried two rows per item - 20 rows for
    10 haystacks, 40 for 20 papers, with the same item cache key and two segment keys. Cutting
    the segment and building what the segment holds are one act, so they live in one function
    and every caller gets both. With no axis declared the call returns an empty table and this
    is the path J3 and J4 measured, unchanged.
    """
    content_receipt: dict[str, Any] = {}
    if ingestion.declaration.content_axes:
        from .content import build_content
        build = build_content(ingestion)
        ingestion.content = build.table
        content_receipt = build.receipt
    started = time.perf_counter()
    cut, gate = cut_segments(ingestion, extractor_roster_hash=extractor_roster_hash)
    cut_seconds = time.perf_counter() - started

    known = store.cache_index()
    existing_segments = set(known.values())
    # WHERE THIS RUN'S ITEMS SIT IN THE PERSISTED LAYOUT. The manifest, not a run, owns the
    # record's ordinals: every open reads the same bases and reproduces the same layout. On a
    # cold run the high-water mark is 0 and the persisted layout IS the run's own. On a MIXED
    # run (some items adopted from the store, some newly cut) the adopted rows are projected
    # after the new ones, so the run's in-memory ordinals are a third layout - and that is
    # exactly why the persisted tree addresses rows by their B.2 IDENTITY and not by an
    # ordinal. The new items are appended after everything the manifest already declares,
    # which keeps the declared blocks disjoint whatever order a run happened to build them in.
    existing_rows = store.rows()
    high_water = max([int(row.get("global_base", 0)) + int(row.get("rows", 0))
                      for row in existing_rows] or [0])  # loop-ok: the manifest's own rows, one arithmetic step each
    started = time.perf_counter()
    rows: list[dict[str, Any]] = []
    written = 0
    bytes_written = 0
    total_source = ingestion.blobs.total_bytes()
    layouts = gate["layouts"]
    live_bases = [int(layout["global_base"]) for layout in layouts if layout["rows"]]  # loop-ok: one step per item cut
    live_total = sum(int(layout["rows"]) for layout in layouts)  # loop-ok: one step per item cut
    shift = 0
    if live_bases:
        first = min(live_bases)
        if max(live_bases) - first >= live_total:
            raise MalformedSource(
                "SEGMENT-CUT-ITEMS-ARE-NOT-ONE-BLOCK: the items being stored do not occupy one "
                "contiguous run of global ordinals, so their persisted bases cannot be shifted "
                "onto the manifest's high-water mark as one block",
                first=first, last=max(live_bases), rows=live_total)
        shift = high_water - first
    for position, (mark, payload) in enumerate(cut):
        segment_key = hash_bytes(payload)
        layout = layouts[position]
        for handle in mark.blob_handles:
            blob = ingestion.blobs.blob(handle)
            _, added = store.put(blob.read())
            bytes_written += added
        if segment_key in existing_segments:
            continue
        _, added = store.put(payload)
        bytes_written += added
        written += 1
        header = Segment.decode(payload).header
        rows.append({
            "schema_version": MANIFEST_ROW_SCHEMA,
            "dataset_id": ingestion.declaration.dataset_id,
            "dataset_declaration_hash": ingestion.declaration.declaration_hash,
            "extractor_roster_hash": extractor_roster_hash,
            "item_content_hash": mark.item_content_hash,
            "item_span": list(mark.item_span),
            "item_cache_key": mark.item_cache_key,
            "segment_key": segment_key,
            "segment_bytes": len(payload),
            "blobs": [blob["handle"] for blob in header["blobs"]],
            "spans": header["span_count"],
            "rows": sum(entry["count"] for entry in header["rows"].values()),
            "relations": sum(entry["count"] for entry in header["relations"].values()),
            "supersedes": known.get(mark.item_cache_key),
            # The per-segment ordinal base and the offset of each kind inside the item's block.
            # ``open_record`` installs the item's rows AT these ordinals, which is what makes a
            # warm run address the same rows as the cold one that built the record.
            "global_base": int(layout["global_base"]) + shift,
            "row_layout": layout["kinds"],
        })
    ledger_before = store.manifest_path.stat().st_size if store.manifest_path.is_file() else 0
    appended = store.append_rows(rows)
    if appended:
        bytes_written += store.manifest_path.stat().st_size - ledger_before
    if not store.meta_path.is_file():
        store.write_meta({
            "schema_version": STORE_META_SCHEMA,
            "dataset_id": ingestion.declaration.dataset_id,
            "dataset_declaration_hash": ingestion.declaration.declaration_hash,
            "extractor_roster_hash": extractor_roster_hash,
            "segmenter_id": ingestion.declaration.segmenter_id,
            "seg_version": ingestion.declaration.seg_version,
            "shared_dictionaries": ingestion.store.shared_dictionary_groups(),
        })
    write_seconds = time.perf_counter() - started

    timings = ingestion.timings
    return IngestReceipt(
        dataset_id=ingestion.declaration.dataset_id,
        items=len(cut) + len(ingestion.deferred_segments),
        cache_hits=ingestion.cache.hits,
        cache_misses=ingestion.cache.misses,
        extractions=int(ingestion.counters.get("extractions", 0)),
        item_parses=int(ingestion.counters.get("item_parses", 0)),
        extraction_seconds=float(timings.get("parse_and_rows_s", 0.0)),
        load_seconds=float(timings.get("adopt_segments_s", 0.0)),
        cut_seconds=cut_seconds,
        write_seconds=write_seconds,
        gate_seconds=float(gate["gate_seconds"]),
        segments_written=written,
        segments_total=len(cut) + len(ingestion.deferred_segments),
        manifest_rows_appended=appended,
        source_bytes=source_bytes if source_bytes is not None else total_source,
        persisted_bytes=store.persisted_bytes(),
        bytes_written=bytes_written,
        device_bytes=device_bytes if device_bytes is not None else projection_bytes(ingestion),
        peak_device_bytes=peak_device_bytes(ingestion.device),
        rows=ingestion.store.row_count,
        relations=len(ingestion.relations),
        spans=len(ingestion.spans),
        content=content_receipt,
    )


# --------------------------------------------------------------------------- projecting
def _item_ordinals(layouts: Sequence[Mapping[str, Any]] | None, index: int,
                   kind: str) -> int | None:
    """The absolute global ordinal this item's rows of ``kind`` start at, or None. O(kinds)."""
    if layouts is None:
        return None
    layout = layouts[index]
    base = int(layout["global_base"])
    for name, offset, _count in layout["row_layout"]:  # loop-ok: this item's declared row kinds
        if name == kind:
            return base + int(offset)
    return None


def _project(ingestion: Ingestion, segments: Sequence[Segment], *,
             register: Any = None,
             layouts: Sequence[Mapping[str, Any]] | None = None) -> tuple[int, dict[str, Any]]:
    """Concatenate host images and install them: ONE host-to-device copy per table.

    Returns (copies, offsets). The per-item work is numpy concatenation; the device sees one
    transfer per span table, per row kind and per relation kind, whatever the item count.

    ``layouts`` is the per-segment ordinal layout the manifest persisted (``global_base`` and
    the offset of each kind inside the item's block). Given it, this installs every row AT the
    ordinal the ingestion assigned, so ORDINALS ARE REPRODUCED rather than reassigned - the
    defect that made a warm run answer from a different row set than the cold one. Without it
    the old kind-major assignment stands, which is still what a same-process round trip wants.

    Complexity: O(N c + E + W) host, O(tables) transfers.
    """
    declaration = ingestion.declaration
    handles: list[str] = list(ingestion.spans.handles())
    handle_index = {handle: position for position, handle in enumerate(handles)}
    span_blocks: list[np.ndarray] = []
    span_offset: list[int] = []
    running_spans = len(ingestion.spans)
    for segment in segments:
        span_offset.append(running_spans)
        block = np.array(segment.arrays["spans"], dtype=np.int64, copy=True)
        local: list[int] = []
        for blob in segment.header["blobs"]:
            handle = blob["handle"]
            if handle not in handle_index:
                handle_index[handle] = len(handles)
                handles.append(handle)
            local.append(handle_index[handle])
            if register is not None:
                register(handle, blob["media_type"], blob["size"])
        if block.shape[0]:
            block[:, 0] = np.array(local, dtype=np.int64)[block[:, 0]]
        span_blocks.append(block)
        running_spans += block.shape[0]
    spans = (np.concatenate(span_blocks) if span_blocks
             else np.zeros((0, 3), dtype=np.int64))
    copies = ingestion.spans.from_arrays(spans, handles)

    # --- rows: one merged image per kind, one copy per kind
    kind_base: dict[str, int] = {}
    kind_offset: dict[tuple[str, int], int] = {}
    kind_start: dict[tuple[str, int], int] = {}   # (kind, item) -> ABSOLUTE global ordinal
    images: list[dict[str, Any]] = []
    for spec in declaration.row_kinds:  # loop-ok: the declaration's own closed row-kind list; the body is whole-array over every item at once
        kind = spec.kind
        parts = [(index, segment) for index, segment in enumerate(segments)
                 if kind in segment.header["rows"]]
        if not parts:
            continue
        merged_columns: dict[str, list[np.ndarray]] = {name: [] for name in spec.columns}
        merged_dicts: dict[str, list[str]] = {}
        dict_index: dict[str, dict[str, int]] = {}
        extractor_ids: list[str] = []
        extractor_index: dict[str, int] = {}
        witness_parts, rung_parts, extractor_parts = [], [], []
        identity_parts: list[np.ndarray] = []
        starts: list[int] = []
        counts: list[int] = []
        running = 0
        for index, segment in parts:
            entry = segment.header["rows"][kind]
            kind_offset[(kind, index)] = running
            given = _item_ordinals(layouts, index, kind)
            if layouts is not None and given is None:
                raise MalformedSource("a manifest row carries no ordinal layout for a kind it "
                                      "stores", kind=kind, item=index)
            starts.append(running if given is None else given)
            counts.append(int(entry["count"]))
            running += int(entry["count"])
            for name in spec.columns:
                column = segment.arrays[f"rows.{kind}.{name}"]
                if name in entry["dicts"]:
                    target = merged_dicts.setdefault(name, [])
                    lookup = dict_index.setdefault(name, {})
                    mapping = np.array([_intern(target, lookup, surface)
                                        for surface in entry["dicts"][name]], dtype=np.int64)
                    column = _remap(column, mapping)
                elif spec.field(name).type == "span_ref":
                    column = _shift_span_column(column, span_offset[index])
                merged_columns[name].append(np.asarray(column))
            witness_parts.append(np.asarray(segment.arrays[f"rows.{kind}.__witness"])
                                 + span_offset[index])
            rung_parts.append(np.asarray(segment.arrays[f"rows.{kind}.__rung"]))
            mapping = np.array([_intern(extractor_ids, extractor_index, surface)
                                for surface in entry["extractor_ids"]], dtype=np.int64)
            extractor_parts.append(_remap(
                np.asarray(segment.arrays[f"rows.{kind}.__extractor"]), mapping))
            identity_parts.append(np.asarray(
                segment.arrays[f"rows.{kind}.__identity"], dtype=np.int64))
        # The merged image's global ordinals: one ``repeat`` of each item's absolute start
        # minus its offset in the concatenation, plus one ``arange``. No loop over a row.
        count_array = np.asarray(counts, dtype=np.int64)
        prefix = np.cumsum(count_array) - count_array
        assigned = (np.repeat(np.asarray(starts, dtype=np.int64) - prefix, count_array)
                    + np.arange(running, dtype=np.int64))
        images.append({
            "kind": kind, "count": running,
            "columns": {name: np.concatenate(blocks)
                        for name, blocks in merged_columns.items()},
            "witness": np.concatenate(witness_parts),
            "rung": np.concatenate(rung_parts),
            "extractor": np.concatenate(extractor_parts),
            "identity": np.concatenate(identity_parts),
            "global": assigned if layouts is not None else None,
            "item_starts": {index: int(start)
                            for (index, _s), start in zip(parts, starts)},
            "dicts": merged_dicts,
            "extractor_ids": extractor_ids,
        })
    for image in images:  # loop-ok: one entry per declared row kind
        kind_base[image["kind"]] = ingestion.store.row_count
        shift = 0 if layouts is not None else kind_base[image["kind"]]
        for index, start in image["item_starts"].items():  # loop-ok: the items that hold this kind; one dictionary entry each, no array work
            kind_start[(image["kind"], index)] = start + shift
        copies += ingestion.store.from_arrays([image])

    # --- relations: endpoints re-based onto the projection's own global ordinals
    kind_names = [spec.kind for spec in declaration.row_kinds]
    relation_images: dict[str, dict[str, np.ndarray]] = {}
    for spec in declaration.relation_kinds:
        name = spec.kind
        parts = [(index, segment) for index, segment in enumerate(segments)
                 if name in segment.header["relations"]]
        if not parts:
            continue
        src_parts, dst_parts, len_parts, span_parts = [], [], [], []
        for index, segment in parts:
            endpoints = np.asarray(segment.arrays[f"rel.{name}.endpoints"], dtype=np.int64)
            src_parts.append(_global_of(endpoints[:, 0], endpoints[:, 1], kind_names,
                                        kind_start, index))
            dst_parts.append(_global_of(endpoints[:, 2], endpoints[:, 3], kind_names,
                                        kind_start, index))
            len_parts.append(np.asarray(segment.arrays[f"rel.{name}.wlen"], dtype=np.int64))
            span_parts.append(np.asarray(segment.arrays[f"rel.{name}.wspan"], dtype=np.int64)
                              + span_offset[index])
        relation_images[name] = {"src": np.concatenate(src_parts),
                                 "dst": np.concatenate(dst_parts),
                                 "wlen": np.concatenate(len_parts),
                                 "wspan": np.concatenate(span_parts)}
    copies += ingestion.relations.from_arrays(relation_images)

    # --- the content leaves: spans re-based onto the projection's span table and carriers onto
    # its global row ordinals, through the SAME ``_global_of`` the relation endpoints use. One
    # concatenation per column over every item at once; no Python loop over a leaf.
    parts = [(index, segment) for index, segment in enumerate(segments)
             if segment.header.get("content")]
    if parts:
        from .content import ContentTable, concatenate, content_from_arrays
        blocks: list[ContentTable] = []
        for index, segment in parts:  # loop-ok: one step per ITEM that carries content leaves
            table = content_from_arrays(segment.arrays, segment.header["content"], declaration)
            table.span = table.span + span_offset[index]
            table.carrier_row = _global_of(table.carrier_kind, table.carrier_row, kind_names,
                                           kind_start, index)
            blocks.append(table)
        merged = concatenate(blocks, declaration)
        held = getattr(ingestion, "content", None)
        ingestion.content = (merged if held is None or not len(held)
                             else concatenate([held, merged], declaration))
    return copies, {"kind_base": kind_base, "span_offset": span_offset}


def _intern(surfaces: list[str], index: dict[str, int], surface: str) -> int:
    found = index.get(surface)
    if found is None:
        found = len(surfaces)
        surfaces.append(surface)
        index[surface] = found
    return found


def _remap(codes: np.ndarray, mapping: np.ndarray) -> np.ndarray:
    """Apply a code mapping, preserving the null sentinel. Vectorised, O(n)."""
    out = np.asarray(codes).astype(np.int64, copy=True)
    live = (out >= 0) & (out < mapping.size)
    out[live] = mapping[out[live]]
    return out


def _global_of(kinds: np.ndarray, locals_: np.ndarray, kind_names: Sequence[str],
               kind_start: Mapping[tuple[str, int], int], item: int) -> np.ndarray:
    """Item-local endpoints -> this projection's global row ordinals. Loop over KINDS only.

    ``kind_start`` is the ABSOLUTE ordinal this item's rows of that kind were installed at -
    the persisted one on a reopen, the projection's own on a same-process round trip - so an
    edge's endpoints follow the rows wherever the layout put them.
    """
    out = np.empty(kinds.size, dtype=np.int64)
    for code in np.unique(kinds):  # loop-ok: the declaration's closed row-kind list; the body is whole-array
        kind = kind_names[int(code)]
        mask = kinds == code
        out[mask] = kind_start[(kind, item)] + locals_[mask]
    return out


def projection_bytes(ingestion: Ingestion) -> int:
    """Device bytes the projection actually holds. Deterministic, allocator-free. O(tables)."""
    total = ingestion.spans.columns.numel() * 8
    for table in ingestion.store.tables.values():
        if not len(table):
            continue
        for name in table.spec.columns:
            column = table.column(name)
            total += column.numel() * column.element_size()
        total += (table.witness_span.numel() * 8
                  + table.producing_rung.numel()
                  + table.extractor_code.numel() * 4
                  + table.global_ordinals.numel() * 8)
    for table in ingestion.relations.kinds.values():
        if not len(table):
            continue
        total += (table.src.numel() + table.dst.numel() + table.witness_lengths.numel()
                  + table.witness_spans_flat.numel()) * 8
    return int(total)


def adopt_deferred(ingestion: Ingestion, store: SegmentStore) -> int:
    """Install the items this run answered from the segment store. Returns segments adopted.

    This is the whole warm path an ingester needs: items whose bytes were seen before are never
    parsed and never extracted, and their rows arrive through the same one-copy-per-table
    projection the cold open uses.
    """
    if not ingestion.deferred_segments:
        return 0
    started = time.perf_counter()
    segments = [Segment.decode(store.get(key)) for _, key in ingestion.deferred_segments]
    _project(ingestion, segments)
    ingestion.timings["adopt_segments_s"] = time.perf_counter() - started
    return len(segments)


def open_record(store: SegmentStore, declaration: DatasetDeclaration, *,
                device: torch.device | str | None = None, rung: int = 0,
                digests: bool = True) -> OpenedRecord:
    """Open what ingestion built, in any process: no source read, no parse, no extraction.

    Every number the claim rests on is a counter of executed work, not a literal:
    ``extractions`` and ``parses`` are read back from ``Ingestion.counters`` - the SAME two
    counters ``Ingestion.item()`` increments on the ingest path, so a parse or an extraction on
    this path would show up in them - and they are zero because this path never opens an item;
    ``source_reads`` is ``_HiveBlobStore.blob_reads`` (the blobs are registered, not read); and
    ``host_to_device_copies`` is counted by ``_project``, one per table. That the path CANNOT
    extract or parse is proved once in a fixture test
    (``test_open_calls_no_extractor_and_no_parser``, which poisons every grammar of the roster
    and the ingester's own per-item entry points and then opens the record) and is never
    re-checked at run time. Complexity: O(persisted bytes) to read,
    O(N c + E + W) host to concatenate, O(tables) transfers, plus the anchor index rebuild.

    ``digests`` is the ACCEPTANCE check, not a gate on the data path: it recomputes the whole
    record's content identities so an opened record can be compared with the one that was
    stored. It is O(N c log N) host work and it is priced separately in the receipt's
    ``gate_seconds``. It is on by default because that comparison is what this stage is judged
    on; a caller that is opening the record to answer a query passes ``digests=False`` and
    pays nothing for it. The hive's own re-hash of every chunk it hands over is NOT optional
    and is the only per-byte verification the open does.
    """
    meta = store.meta()
    if meta and meta.get("dataset_declaration_hash") != declaration.declaration_hash:
        raise MalformedSource("this store was built under a different dataset declaration",
                              stored=meta.get("dataset_declaration_hash"),
                              offered=declaration.declaration_hash)
    resolved = require_device(device)
    reset_peak_device_bytes(resolved)

    started = time.perf_counter()
    rows = store.rows()
    payloads = [store.get(row["segment_key"]) for row in rows]
    segments = [Segment.decode(payload) for payload in payloads]
    read_seconds = time.perf_counter() - started
    hive_bytes = sum(len(payload) for payload in payloads)

    ingestion = Ingestion(declaration, resolved)
    blobs = _HiveBlobStore(store.hive)
    ingestion.blobs = blobs
    ingestion.store.blobs = blobs

    missing = [index for index, row in enumerate(rows)
               if "global_base" not in row or "row_layout" not in row]  # loop-ok: the manifest's own rows, one membership test each
    if missing:
        raise MalformedSource(
            "SEGMENT-MANIFEST-HAS-NO-ORDINAL-LAYOUT: this store was written before the "
            "per-segment ordinal base was persisted, so its ordinals cannot be reproduced",
            dataset=declaration.dataset_id, rows_without_a_layout=len(missing))

    started = time.perf_counter()
    copies, _ = _project(ingestion, segments, register=blobs.register, layouts=rows)
    project_seconds = time.perf_counter() - started

    started = time.perf_counter()
    ingestion.build_anchors(rung=rung)
    anchor_seconds = time.perf_counter() - started

    gate_started = time.perf_counter()
    computed = content_digests(ingestion) if digests else {}
    gate_seconds = time.perf_counter() - gate_started

    receipt = OpenReceipt(
        dataset_id=declaration.dataset_id,
        items=len(segments),
        extractions=int(ingestion.counters.get("extractions", 0)),
        parses=int(ingestion.counters.get("item_parses", 0)),
        source_reads=blobs.blob_reads,
        hive_gets=len(payloads),
        hive_bytes=hive_bytes,
        host_to_device_copies=copies,
        read_seconds=read_seconds,
        project_seconds=project_seconds,
        anchor_seconds=anchor_seconds,
        gate_seconds=gate_seconds,
        device_bytes=projection_bytes(ingestion),
        peak_device_bytes=peak_device_bytes(resolved),
        rows=ingestion.store.row_count,
        relations=len(ingestion.relations),
        spans=len(ingestion.spans),
        source_bytes=blobs.total_bytes(),
        persisted_bytes=store.persisted_bytes(),
        digests=computed,
    )
    return OpenedRecord(ingestion=ingestion, receipt=receipt)


# --------------------------------------------------------------------------- identity
def content_digests(ingestion: Ingestion) -> dict[str, str]:
    """The record's content, hashed through its OWN identities rather than its ordinals.

    A span is its (blob handle, start, end); a row is its declared field values, its producing
    rung, its extractor and its witness ADDRESS; a relation instance is (source kind, source
    local ordinal, target kind, target local ordinal) with its witness addresses. Nothing here
    is a span ordinal, a global row ordinal, a dictionary code or an arrival order, so two
    processes that hold the same record agree even though neither's layout is the other's.
    Complexity: O(N c log N) host.
    """
    handles = sorted(ingestion.spans.handles())
    handle_rank = {handle: position for position, handle in enumerate(handles)}
    remap = np.array([handle_rank[handle] for handle in ingestion.spans.handles()],
                     dtype=np.int64)
    spans = ingestion.spans.columns.cpu().numpy().astype(np.int64, copy=True)
    if spans.shape[0]:
        spans[:, 0] = remap[spans[:, 0]]
    out: dict[str, str] = {}
    # The DISTINCT addresses: a persisted record stores a byte range once (``_SpanMap``), while
    # the live append-only table may hold it twice, and a span's multiplicity is not a fact
    # about the corpus. A span_ref field is likewise read as the address it names.
    if spans.shape[0]:
        distinct, address_id = np.unique(spans, axis=0, return_inverse=True)
        address_id = address_id.reshape(-1)
    else:
        distinct, address_id = spans, np.zeros(0, dtype=np.int64)
    out["spans"] = _digest_rows(distinct, ["blob", "start", "end"])

    kind_names = [spec.kind for spec in ingestion.declaration.row_kinds]
    kind_rank = {kind: position for position, kind in enumerate(kind_names)}
    local_of_global = np.full(max(ingestion.store.row_count, 1), -1, dtype=np.int64)
    kind_of_global = np.full(max(ingestion.store.row_count, 1), -1, dtype=np.int64)
    for kind, table in ingestion.store.tables.items():  # loop-ok: the declared row kinds
        if not len(table):
            continue
        ordinals = table.global_ordinals.cpu().numpy()
        local_of_global[ordinals] = np.arange(len(table), dtype=np.int64)
        kind_of_global[ordinals] = kind_rank[kind]
        image = table.to_arrays()
        parts = []
        vocabulary: list[str] = []
        for name in table.spec.columns:
            column = np.asarray(image["columns"][name]).astype(np.int64, copy=True)
            if name in image["dicts"]:
                column = _remap(column, _surface_rank(image["dicts"][name]))
                vocabulary.extend(sorted(image["dicts"][name]))
            elif table.spec.field(name).type == "span_ref":
                live = column >= 0
                column = column.copy()
                column[live] = address_id[column[live]]
            parts.append(column)
        witness = spans[np.asarray(image["witness"])]
        parts.append(np.asarray(image["rung"]).astype(np.int64, copy=False))
        parts.append(_remap(np.asarray(image["extractor"]).astype(np.int64),
                            _surface_rank(image["extractor_ids"])))
        matrix = np.concatenate([np.stack(parts, axis=1), witness], axis=1)
        out[f"rows.{kind}"] = chash({"columns": list(table.spec.columns),
                                     "vocabulary": vocabulary,
                                     "extractors": sorted(image["extractor_ids"]),
                                     "bytes": _digest_rows(matrix, [])})

    for name, table in ingestion.relations.kinds.items():  # loop-ok: the closed set of relation kinds
        if not len(table):
            continue
        image = table.to_arrays()
        lengths = image["wlen"]
        offsets = np.concatenate([np.zeros(1, dtype=np.int64), np.cumsum(lengths)])
        width = int(lengths.max()) if lengths.size else 0
        addresses = spans[image["wspan"]]
        # dense-ok: [edges, 3 * max witnesses per edge] - the second axis is the widest witness
        # list of ONE relation instance (a small constant of the grammar, not a count of edges
        # or of rows), so this is a ragged list padded to its own width, never an all-pairs
        # object. It is the identity gate's own layout and runs once per relation kind.
        padded = np.full((lengths.size, 3 * max(width, 1)), -1, dtype=np.int64)  # dense-ok: the widest witness list of ONE relation instance, a constant of the grammar
        position = (np.arange(image["wspan"].size, dtype=np.int64)
                    - np.repeat(offsets[:-1], lengths))
        owner = np.repeat(np.arange(lengths.size, dtype=np.int64), lengths)
        for axis in range(3):
            padded[owner, position * 3 + axis] = addresses[:, axis]
        matrix = np.concatenate([
            np.stack([kind_of_global[image["src"]], local_of_global[image["src"]],
                      kind_of_global[image["dst"]], local_of_global[image["dst"]],
                      lengths], axis=1), padded], axis=1)
        order = np.lexsort(tuple(matrix[:, column]
                                 for column in reversed(range(matrix.shape[1]))))
        out[f"relations.{name}"] = _digest_rows(matrix[order], [])

    # The content leaves, hashed through their own ADDRESSES for the same reason the rows are:
    # a warm open and the cold run that built the record assign different ordinals and must
    # still agree. With no axis declared this adds no key, so the record digest of a store
    # without content is the one it was before this packet.
    content = getattr(ingestion, "content", None)
    if content is not None and len(content):
        from .content import content_digest
        out.update(content_digest(content, spans, ingestion.declaration))
    out["record"] = chash({key: value for key, value in out.items()})
    return out


def _surface_rank(surfaces: Sequence[str]) -> np.ndarray:
    """code -> its rank in the SORTED surface list, so a code carries no interning order."""
    rank = np.empty(len(surfaces), dtype=np.int64)
    for position, index in enumerate(sorted(range(len(surfaces)), key=lambda i: surfaces[i])):
        rank[index] = position
    return rank


def _digest_rows(matrix: np.ndarray, columns: Sequence[str]) -> str:
    array = np.ascontiguousarray(matrix, dtype=np.int64)
    array = array.astype(array.dtype.newbyteorder("<"), copy=False)
    return chash({"columns": list(columns), "shape": list(array.shape),
                  "sha256": hash_bytes(array.tobytes())})


# --------------------------------------------------------------------------- one item alone
def segment_for_item(dataset: str, raw: bytes, *, rungs: str, extractor_roster_hash: str,
                     item_id: str | None = None,
                     device: torch.device | str | None = None) -> tuple[str, bytes]:
    """Cut ONE item's segment in isolation. Returns (item cache key, segment bytes).

    This is the unit that PROVES purity: an item is independent of every other item, so its
    segment cut alone must be byte-identical to the segment the batch ingest cuts for it, in
    either arrival order. Its consumer is the fixture test that proves must-achieve (1) once
    (``atlas/tests/test_record_persistence.py``); nothing on the ingest path calls it, because
    the batch path cuts the same segments from the store it is already building.

    WHY THERE IS NO PROCESS POOL HERE ANY MORE. A pool over this function was built and is
    WITHDRAWN, measured 2026-09-22 (the demonstration and its numbers:
    evidence/ATLAS_PROGRAMME/waves/J1-join/A1/pool_withdrawn.json). Cutting a segment means
    minting the record's own rows, and the record's rows live in device-resident typed tables
    whose identity, dictionary coding and witness check are device operations - so every child
    imported torch and initialised a CUDA context (1.13 GB resident per child), which is exactly
    what the charter forbids in an extraction worker, and four children cut 30 haystacks only
    1.05x faster than one. The single-process path got the speed-up instead, in the reservation
    that replaced the chunk lists (spans.py:_Growable).
    """
    from .diff import apply_case, apply_paper, item_bytes_cache_key
    from .ingest import longmem, qasper

    if dataset == "longmem":
        declaration = longmem.declaration(rungs)
        extractor_id = longmem.EXTRACTOR_ID
    elif dataset == "qasper":
        declaration = qasper.declaration(rungs)
        extractor_id = qasper.EXTRACTOR_ID_A
    else:
        raise MalformedSource("no such dataset for a single-item cut", dataset=dataset)

    ingestion = Ingestion(declaration, device)
    shared = "question_id" if dataset == "longmem" else "paper_id"
    ingestion.store.share_dictionary(shared, [spec.kind for spec in declaration.row_kinds])
    key = item_bytes_cache_key(raw, extractor_id, declaration.declaration_hash)
    with ingestion.item(key, item_bytes=raw, blob_handles=(hash_bytes(raw),),
                        extracts="b" in rungs):
        if dataset == "longmem":
            apply_case(ingestion, raw)
        else:
            apply_paper(ingestion, raw, str(item_id))
    cut, _ = cut_segments(ingestion, extractor_roster_hash=extractor_roster_hash)
    return key, cut[0][1]


# Front v2 observation views only; stored segment/manifest identities are untouched.



# The inert closed receipt contract; numeric execution remains owned here.
from ..receipt_diagnostics import ingest_receipt_parts, open_receipt_parts
