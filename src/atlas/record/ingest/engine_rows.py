"""engine_rows.py - the engine's own typed jsonl rows (B.32), and the latest-wins status fold.

B.32 fixes the shape: "the whole file is the blob, one JSON object per line is one item, and its
span is that line's byte range"; the declared fields are typed; ``supersedes``, ``target``,
``corrects``, ``retracts`` and ``absorbs`` become typed relations witnessed by the pair of line
spans; "an unresolvable value becomes a ``dangling_reference`` ROW ... never a dropped link".

THE ENUM VOCABULARIES ARE MEASURED, NOT HAND-SET. B.5 requires an enum's vocabulary "in full",
and B.32 wants status and kind typed as enums. The engine's ledgers have no authored codebook:
the measured vocabulary is 48 statuses, 36 work-order kinds, 19 record types, 20 verdict kinds
and 8 confidences (the command is in the packet report). Writing those out as a literal list
would be exactly forbidden move 1 - a hand-set vocabulary in construction code. So
``measure_vocabularies`` derives them by a declared pure function of the admitted blobs' bytes,
once, before the declaration is frozen; the vocabulary then enters the declaration hash, and a
value outside it later FAILS CLOSED rather than being quietly added. Provenance is the function
plus the blobs' content hashes, both of which the receipt carries.

THE FOLD. Status is written repeatedly across lines - a resolution or amendment names the work
order it concerns in ``target`` - so the current status of a work order is a fold over the lines
that target it. The rule, in the packet's words, is latest-wins "in which the explicit supersedes
link beats the timestamp": a row's SUPERSESSION RANK (its longest chain of explicit
``supersedes`` edges) is the primary key, the timestamp is the secondary and the line ordinal the
tertiary tiebreak. Conflicts are flagged, never silently resolved:

* a ``supersedes`` edge whose superseder is OLDER than what it supersedes - the two signals
  disagree, the link wins, and the disagreement is recorded;
* two rows that tie on the whole order key with different statuses;
* a ``supersedes`` cycle, which no rank can order.

A row with no timestamp sorts earliest, declared rather than assumed: a line that does not say
when it was written cannot claim to be the most recent thing said.

The fold is a PROJECTION (B.6): it references record rows and is never written back into them.
"""

from __future__ import annotations

import datetime as _dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import torch

from ...ids import chash
from ..declaration import (RUNG_A, DatasetDeclaration, FieldAliasTable, FieldSpec,
                           ContentCarrier, RelationKindSpec, RowKindSpec,
                           SurfaceSetSchema)
from ..content import declared_axes
from ..ingestion import Ingestion, item_cache_key
from ..json_spans import SEG_VERSION, SEGMENTER_ID, iter_jsonl_lines
from ..witness import register_parser

__all__ = ["WORK_ORDERS_PATH", "VERDICTS_PATH", "measure_vocabularies", "declaration", "ingest",
           "StatusFold", "LINK_FIELDS"]

_REPO = Path(__file__).resolve().parents[4]
WORK_ORDERS_PATH = _REPO / "corpus_friction" / "work_orders.jsonl"
VERDICTS_PATH = _REPO / "proxy_verdicts.jsonl"

BLOB_MEDIA_TYPE = "application/x-ndjson"
EXTRACTOR_ID = "engine-jsonl-rung-a@v1"

# B.32's five link fields, and the relation kind each becomes.
LINK_FIELDS = {"supersedes": "supersedes", "target": "targets", "corrects": "corrects",
               "retracts": "retracts", "absorbs": "absorbs"}

_WORK_ORDER_SCALARS = ("id", "by", "source", "owner", "lane", "severity", "cost_class",
                       "corpus", "project", "action")
_VERDICT_SCALARS = ("id", "by", "source", "judge")


def _iso_datetime(value: Any) -> _dt.datetime:
    return _dt.datetime.fromisoformat(str(value))


def _iso_date(value: Any) -> _dt.date:
    return _dt.date.fromisoformat(str(value))


register_parser("iso_datetime@v1", _iso_datetime)
register_parser("iso_date@v1", _iso_date)


@dataclass(frozen=True, slots=True)
class Vocabularies:
    """The measured enum vocabularies, with the blobs they were measured from."""

    work_order_status: tuple[str, ...]
    work_order_kind: tuple[str, ...]
    work_order_record: tuple[str, ...]
    verdict_kind: tuple[str, ...]
    verdict_confidence: tuple[str, ...]
    measured_from: tuple[str, ...]

    def provenance(self) -> dict[str, Any]:
        return {"function": "atlas.record.ingest.engine_rows.measure_vocabularies",
                "measured_from": list(self.measured_from),
                "sizes": {"work_order_status": len(self.work_order_status),
                          "work_order_kind": len(self.work_order_kind),
                          "work_order_record": len(self.work_order_record),
                          "verdict_kind": len(self.verdict_kind),
                          "verdict_confidence": len(self.verdict_confidence)}}


def measure_vocabularies(work_orders: Path = WORK_ORDERS_PATH,
                         verdicts: Path = VERDICTS_PATH) -> Vocabularies:
    """A declared pure function of the two files' bytes: the enum vocabularies, sorted.

    Complexity: O(bytes). Deterministic, no sampling, no threshold - every distinct string
    value of the named members is admitted to the vocabulary, so the vocabulary is the data.
    """
    from ..content_blob import ContentBlobStore
    store = ContentBlobStore()
    found: dict[str, set[str]] = {k: set() for k in
                                  ("wo_status", "wo_kind", "wo_record", "v_kind", "v_confidence")}
    handles = []
    for path, keys in ((work_orders, {"status": "wo_status", "kind": "wo_kind",
                                      "record": "wo_record"}),
                       (verdicts, {"kind": "v_kind", "confidence": "v_confidence"})):
        data = Path(path).read_bytes()
        handles.append(store.put_bytes(data, BLOB_MEDIA_TYPE))
        for start, end in iter_jsonl_lines(data):
            item = json.loads(data[start:end].decode("utf-8"))
            for member, bucket in keys.items():
                value = item.get(member)
                if isinstance(value, str):
                    found[bucket].add(value)
    return Vocabularies(tuple(sorted(found["wo_status"])), tuple(sorted(found["wo_kind"])),
                        tuple(sorted(found["wo_record"])), tuple(sorted(found["v_kind"])),
                        tuple(sorted(found["v_confidence"])), tuple(handles))


# THE CONTENT-BEARING ROW KINDS OF THE ENGINE'S OWN LEDGERS: "one typed row's text field (a
# ruling's body, a work order's statement)" (the reconciliation). ``line_span`` is the item's own
# byte range - one JSONL line - and it is read as UTF-8 exactly as the ledger wrote it.
CONTENT_CARRIERS = (ContentCarrier("work_order", "line_span", "utf8"),
                    ContentCarrier("verdict", "line_span", "utf8"))


def declaration(vocabularies: Vocabularies, *, content: Mapping[str, Any] | None = None) -> DatasetDeclaration:
    """B.5's declaration for the engine's own ledgers, with the measured enums frozen in."""
    work_order = RowKindSpec(
        "work_order",
        tuple([FieldSpec(name, "dict_utf8", RUNG_A) for name in _WORK_ORDER_SCALARS] +
              [FieldSpec("ts", "timestamp", RUNG_A, doc="when the line was written"),
               FieldSpec("date", "date", RUNG_A, doc="the line's declared civil date"),
               FieldSpec("status", "enum", RUNG_A, vocabularies.work_order_status),
               FieldSpec("kind", "enum", RUNG_A, vocabularies.work_order_kind),
               FieldSpec("record", "enum", RUNG_A, vocabularies.work_order_record),
               FieldSpec("line_span", "span_ref", RUNG_A, doc="the item's own byte range")]),
        time_field="ts", witness_predicate_id="json_member_equals@v1", anchor_fields=("id",))
    verdict = RowKindSpec(
        "verdict",
        tuple([FieldSpec(name, "dict_utf8", RUNG_A) for name in _VERDICT_SCALARS] +
              [FieldSpec("ts", "timestamp", RUNG_A),
               FieldSpec("date", "date", RUNG_A),
               FieldSpec("kind", "enum", RUNG_A, vocabularies.verdict_kind),
               FieldSpec("confidence", "enum", RUNG_A, vocabularies.verdict_confidence),
               FieldSpec("line_span", "span_ref", RUNG_A)]),
        time_field="date", witness_predicate_id="json_member_equals@v1", anchor_fields=("id",))
    dangling = RowKindSpec(
        "dangling_reference",
        (FieldSpec("owner_id", "dict_utf8", RUNG_A),
         FieldSpec("field", "dict_utf8", RUNG_A),
         FieldSpec("raw_value", "dict_utf8", RUNG_A),
         FieldSpec("owner_kind", "dict_utf8", RUNG_A)),
        witness_predicate_id="surfaces_located@v1",
        doc="B.32: a non-empty link value that resolves to nothing is a ROW, never a dropped link")
    relations = tuple(
        RelationKindSpec(kind, ("work_order", "verdict"), ("work_order", "verdict"),
                         "link_member_equals@v1", RUNG_A,
                         counted=True,
                         doc=f"B.32's '{field}' link, witnessed by the pair of line spans")
        for field, kind in LINK_FIELDS.items())
    # The ablation switch; ``content=None`` is the OFF position (see longmem.declaration).
    _recipe, _axes = declared_axes(content, CONTENT_CARRIERS, SEG_VERSION)
    return DatasetDeclaration(
        dataset_id="engine-ledgers",
        row_kinds=(work_order, verdict, dangling),
        relation_kinds=relations,
        alias_table=FieldAliasTable("engine-aliases@v1", ()),
        surface_set=SurfaceSetSchema(
            "engine-surfaces@v1",
            anchor_columns={"work_order": ("id",), "verdict": ("id",)},
            must_appear_columns={"dangling_reference": ("raw_value",)},
            principal_surfaces={}, principals=()),
        segmenter_id=SEGMENTER_ID, seg_version=SEG_VERSION,
        segmentation=_recipe, content_axes=_axes,
        blob_glob="corpus_friction/work_orders.jsonl;proxy_verdicts.jsonl")


# --------------------------------------------------------------------------- the fold
@dataclass(frozen=True, slots=True)
class StatusFold:
    """The latest-wins status per entity, and every conflict the fold refused to hide."""

    entity_ids: tuple[str, ...]
    status: tuple[str | None, ...]
    winner_row: tuple[int, ...]                 # global row ordinal of the winning line
    conflicts: tuple[dict[str, Any], ...]
    supersession_depth: int

    def as_dict(self) -> dict[str, Any]:
        return {"entities": len(self.entity_ids), "conflicts": len(self.conflicts),
                "supersession_depth": self.supersession_depth,
                "status_histogram": _histogram(self.status)}


def _histogram(values: Sequence[Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for value in values:
        key = "null" if value is None else str(value)
        out[key] = out.get(key, 0) + 1
    return out


def ingest(work_orders: Path = WORK_ORDERS_PATH, verdicts: Path = VERDICTS_PATH, *,
           device: torch.device | str | None = None,
           vocabularies: Vocabularies | None = None,
           content: Mapping[str, Any] | None = None) -> Ingestion:
    """Ingest both ledgers at rung (a), build the link relations and fold the status.

    Complexity: O(bytes) host parse and check; O(R log R + E) device work; the fold's rank
    relaxation is O(depth * E) with depth the longest explicit supersession chain, reported.
    """
    vocabularies = vocabularies or measure_vocabularies(work_orders, verdicts)
    declared = declaration(vocabularies, content=content)
    ingestion = Ingestion(declared, device)
    ingestion.counters["vocabulary_measured_from"] = len(vocabularies.measured_from)
    ingestion.coverage["enum_vocabularies"] = vocabularies.provenance()
    store = ingestion.store
    store.share_dictionary("id", ["work_order", "verdict"])

    links: list[tuple[str, str, int, str]] = []       # (field, raw target, source local, kind)
    unmapped: dict[str, int] = {}
    # THE TWO LEDGERS ARE ONE ITEM (B.28), and the cut is where no declared relation crosses it.
    # A work_order's link fields resolve against VERDICT rows and a verdict's against work_order
    # rows (``_build_links``), and ``_build_links`` additionally mints the B.32 dangling_reference
    # rows that some of those edges end on - so a per-LINE item and even a per-FILE item are both
    # refused by ``segments.cut_segments`` with MalformedSource "relation instances cross item
    # boundaries and cannot be cut into segments". Measured, not assumed: the demonstration is in
    # this packet's report and its test. Marking the pair as one item is what makes the second
    # run of the front door take ``open_record`` on the engine's own ledgers - extractions 0,
    # parses 0, source_reads 0 - instead of re-reading 3,645,617 source bytes every run.
    files = [(Path(work_orders).read_bytes(), "work_order"),
             (Path(verdicts).read_bytes(), "verdict")]
    handles = tuple(ingestion.blobs.put_bytes(data, BLOB_MEDIA_TYPE)
                    for data, _kind in files)  # loop-ok: the two declared ledger files
    both = b"".join(data for data, _kind in files)  # loop-ok: the two declared ledger files
    key = item_cache_key(chash({"blobs": list(handles)}), (0, len(both)), EXTRACTOR_ID,
                         declared.declaration_hash)
    with ingestion.item(key, item_bytes=both, blob_handles=handles, extracts=False):
        with ingestion.measure("parse_and_rows"):
            for (data, kind), handle in zip(files, handles):  # loop-ok: the two declared ledger files
                _ingest_file(ingestion, data, handle, kind, links, unmapped)
        ingestion.coverage["members_outside_declared_columns"] = dict(sorted(
            unmapped.items(), key=lambda kv: (-kv[1], kv[0]))[:40])
        ingestion.coverage["members_outside_declared_columns_total"] = len(unmapped)

        with ingestion.measure("relations"):
            _build_links(ingestion, links)
        with ingestion.measure("anchors"):
            ingestion.build_anchors(rung=RUNG_A)
    with ingestion.measure("status_fold"):
        ingestion.fold = _fold_status(ingestion)      # type: ignore[attr-defined]
    return ingestion


def _ingest_file(ingestion: Ingestion, data: bytes, handle: str, kind: str,
                 links: list[tuple[str, str, int, str]], unmapped: dict[str, int]) -> None:
    """One ledger file's lines, against a blob its caller has already put. O(bytes)."""
    spec = ingestion.declaration.row_kind(kind)
    columns = [f.name for f in spec.fields if f.name != "line_span"]
    ranges = list(iter_jsonl_lines(data))
    span_ords = ingestion.add_spans(handle, ranges)
    records: list[dict[str, Any]] = []
    file_links: list[tuple[str, str, int]] = []
    for position, (start, end) in enumerate(ranges):
        item = json.loads(data[start:end].decode("utf-8"))
        record: dict[str, Any] = {"line_span": int(span_ords[position])}
        for name in columns:
            value = item.get(name)
            if name in ("ts", "date"):
                # A surface the declared rule cannot parse is NOT quietly nulled: the field
                # stays null, the witness check then finds null against a non-null member and
                # REFUSES the row (B.4). The count is kept so the refusal has a reason.
                parser = _iso_datetime if name == "ts" else _iso_date
                record[name] = None
                if isinstance(value, str):
                    try:
                        record[name] = parser(value)
                    except ValueError:
                        key = f"{kind}.{name}"
                        ingestion.coverage.setdefault("malformed_typed_field", {})
                        ingestion.coverage["malformed_typed_field"][key] = \
                            ingestion.coverage["malformed_typed_field"].get(key, 0) + 1
            else:
                record[name] = value if isinstance(value, str) else None
        records.append(record)
        for member in item:
            if member not in columns and member not in LINK_FIELDS:
                unmapped[member] = unmapped.get(member, 0) + 1
        for field in LINK_FIELDS:
            value = item.get(field)
            if isinstance(value, str) and value:
                file_links.append((field, value, position))
            elif isinstance(value, list) and value:
                for entry in value:
                    if isinstance(entry, str) and entry:
                        file_links.append((field, entry, position))
            elif field in item:
                # B.35 counts an ABSENT link (empty string, empty list, null) separately from a
                # dangling one: a field that was never filled is not a broken reference.
                key = f"{kind}.{field}"
                ingestion.coverage["absent_by_field"][key] = \
                    ingestion.coverage["absent_by_field"].get(key, 0) + 1
    members = {name: (name,) for name in columns}
    admission = ingestion.store.append_rows(
        kind, records, span_ords.tolist(), rung=RUNG_A, extractor_id=EXTRACTOR_ID,
        witness_options={"members": members,
                         "coerce": {"ts": "iso_datetime@v1", "date": "iso_date@v1"}})
    # A line that was REFUSED has no row, so its links have no source. They are dropped with it
    # and counted: a link hanging off a row that does not exist would be a reference that cannot
    # be resolved, which the charter's last forbidden move rules out.
    local_of_line = {line: local for local, line in enumerate(admission.positions)}
    for field, raw, line in file_links:
        local = local_of_line.get(line)
        if local is None:
            key = f"{kind}.{field}"
            ingestion.coverage.setdefault("links_dropped_with_refused_row", {})
            ingestion.coverage["links_dropped_with_refused_row"][key] = \
                ingestion.coverage["links_dropped_with_refused_row"].get(key, 0) + 1
            continue
        links.append((field, raw, local, kind))


def _build_links(ingestion: Ingestion, links: Sequence[tuple[str, str, int, str]]) -> None:
    """Resolve every link value to a row, or mint the dangling_reference row B.32 demands."""
    store = ingestion.store
    tables = {kind: store.table(kind) for kind in ("work_order", "verdict")}
    id_dictionary = tables["work_order"]._dicts["id"]
    ids_by_kind = {kind: table.decode("id") for kind, table in tables.items()}
    globals_by_kind = {kind: table.global_ordinals.tolist()
                       for kind, table in tables.items()}  # loop-ok: the two declared row kinds - ONE whole-column host copy each
    spans_by_kind = {kind: table.witness_span.tolist()
                     for kind, table in tables.items()}  # loop-ok: the two declared row kinds - ONE whole-column host copy each

    # code -> global row ordinal, dense; and global ordinal -> line span, dense. Both are built
    # once so a link resolution is a lookup rather than a scan of the store.
    size = max(len(id_dictionary.surfaces), 1)
    row_of_code = torch.full((size,), -1, dtype=torch.int64, device=store.device)
    span_of_row = torch.full((store.row_count,), -1, dtype=torch.int64, device=store.device)
    duplicates: dict[str, int] = {}
    for kind, table in tables.items():
        codes = table.column("id").to(torch.int64)
        keep = codes >= 0
        selected, globals_ = codes[keep], table.global_ordinals[keep]
        clash = int((row_of_code.index_select(0, selected) >= 0).sum())
        _, counts = torch.unique(selected, return_counts=True)
        clash += int((counts - 1).sum())
        if clash:
            duplicates[kind] = clash
        row_of_code[selected] = globals_
        span_of_row[table.global_ordinals] = table.witness_span
    if duplicates:
        ingestion.coverage["duplicate_ids"] = duplicates
    span_of_row_host = span_of_row.tolist()
    row_of_code_host = row_of_code.tolist()

    by_kind: dict[str, dict[str, Any]] = {}
    dangling_records, dangling_spans = [], []
    for field, raw, position, kind in links:
        code = id_dictionary.code_of(raw)
        source_global = globals_by_kind[kind][position]
        source_span = spans_by_kind[kind][position]
        target = row_of_code_host[code] if code is not None and code < size else -1
        if target < 0:
            dangling_records.append({"owner_id": ids_by_kind[kind][position], "field": field,
                                     "raw_value": raw, "owner_kind": kind})
            dangling_spans.append(source_span)
            key = f"{kind}.{field}"
            ingestion.coverage["dangling_by_field"][key] = \
                ingestion.coverage["dangling_by_field"].get(key, 0) + 1
            continue
        bucket = by_kind.setdefault(LINK_FIELDS[field], {"src": [], "dst": [], "spans": [],
                                                         "ctx": [], "field": field})
        bucket["src"].append(source_global)
        bucket["dst"].append(target)
        bucket["spans"].append((source_span, span_of_row_host[target]))
        bucket["ctx"].append({"target_id": raw})
    for kind, bucket in by_kind.items():
        ingestion.append_relations(kind, bucket["src"], bucket["dst"], bucket["spans"],
                                   contexts=bucket["ctx"], extractor_id=EXTRACTOR_ID,
                                   witness_options={"link_field": bucket["field"]})
    if dangling_records:
        ingestion.store.append_rows(
            "dangling_reference", dangling_records, dangling_spans, rung=RUNG_A,
            extractor_id=EXTRACTOR_ID, witness_options={"must_appear": ("raw_value",)})


def _fold_status(ingestion: Ingestion) -> StatusFold:
    """Latest-wins over the status-bearing lines, supersedes beating the timestamp."""
    store = ingestion.store
    device = store.device
    work = store.table("work_order")
    if not len(work):
        return StatusFold((), (), (), (), 0)

    status = work.decode("status")
    ids = work.decode("id")
    ts = work.column("ts").to(torch.int64)
    rows = len(work)

    # The entity a line speaks about: its ``targets`` link if it has one, else itself.
    entity = list(ids)
    targets = ingestion.relations.kind("targets")
    if len(targets):
        local = store.local_of_global("work_order")
        src_local = local.index_select(0, targets.src)
        dst_local = local.index_select(0, targets.dst)
        # LAST NAMING EDGE WINS, exactly as the per-edge host loop did, but without one: the
        # loop's only effect was to overwrite a source's entity with the id of the last target
        # that HAS an id, so the same result is the last kept edge per source. Both endpoints
        # resolved, the target's id declared, one stable sort, one boundary mask, ONE unpack at
        # the end (the guard's own prescribed shape). O(E log E) device, O(distinct sources) host.
        declared_id = torch.tensor([value is not None for value in ids],  # loop-ok: the kind's own id column, one host pass
                                   dtype=torch.bool, device=device)
        keep = (src_local >= 0) & (dst_local >= 0)
        keep = keep & declared_id.index_select(0, dst_local.clamp(min=0))
        src_keep, dst_keep = src_local[keep], dst_local[keep]
        order = torch.argsort(src_keep, stable=True)
        src_sorted, dst_sorted = src_keep[order], dst_keep[order]
        last = torch.ones(src_sorted.numel(), dtype=torch.bool, device=device)
        if src_sorted.numel() > 1:
            last[:-1] = src_sorted[1:] != src_sorted[:-1]
        naming = list(zip(src_sorted[last].tolist(), dst_sorted[last].tolist()))
        for s, d in naming:  # loop-ok: one entry per work_order row that names a target, unpacked once before the loop
            entity[s] = ids[d]

    # Supersession rank: longest explicit chain. Relaxation over LEVELS, which is the one loop
    # shape the charter allows, and it counts its own iterations so a cycle is detected.
    rank = torch.zeros(rows, dtype=torch.int64, device=device)
    supersedes = ingestion.relations.kind("supersedes")
    depth = 0
    conflicts: list[dict[str, Any]] = []
    if len(supersedes):
        local = store.local_of_global("work_order")
        edge_src = local.index_select(0, supersedes.src)
        edge_dst = local.index_select(0, supersedes.dst)
        keep = (edge_src >= 0) & (edge_dst >= 0)
        edge_src, edge_dst = edge_src[keep], edge_dst[keep]
        for depth in range(1, rows + 1):
            proposed = rank.index_select(0, edge_dst) + 1
            updated = rank.clone()
            updated.scatter_reduce_(0, edge_src, proposed, reduce="amax", include_self=True)
            if bool(torch.equal(updated, rank)):
                depth -= 1
                break
            rank = updated
        else:
            conflicts.append({"conflict": "supersedes-cycle",
                              "detail": "rank relaxation did not converge within row count"})
        older = ts.index_select(0, edge_src) < ts.index_select(0, edge_dst)
        for position in torch.nonzero(older, as_tuple=False).flatten().tolist():  # loop-ok: the CONFLICTS the fold refuses to hide (a supersedes edge older than what it supersedes), never the rows
            conflicts.append({
                "conflict": "supersedes-older-than-superseded",
                "superseder": ids[int(edge_src[position])],
                "superseded": ids[int(edge_dst[position])],
                "resolution": "the explicit supersedes link wins over the timestamp (B.32)"})

    # The order key: (rank, timestamp, line ordinal), packed into one int64 with strides DERIVED
    # from the data rather than chosen. A null timestamp sorts earliest, declared.
    ordinal = torch.arange(rows, dtype=torch.int64, device=device)
    valid_ts = ts > torch.iinfo(torch.int64).min
    lo = int(ts[valid_ts].min()) if bool(valid_ts.any()) else 0
    ts_norm = torch.where(valid_ts, ts - lo, torch.zeros_like(ts))
    ts_stride = int(ts_norm.max()) + 1
    key = ((rank * ts_stride) + ts_norm) * rows + ordinal

    has_status = torch.tensor([s is not None for s in status], dtype=torch.bool, device=device)
    entity_of_row = [entity[i] if entity[i] is not None else ids[i] for i in range(rows)]
    unique_entities = sorted({e for i, e in enumerate(entity_of_row)
                              if e is not None and bool(has_status[i])})
    index_of = {name: i for i, name in enumerate(unique_entities)}
    if not unique_entities:
        return StatusFold((), (), (), tuple(conflicts), depth)
    group = torch.tensor([index_of.get(entity_of_row[i], -1) for i in range(rows)],
                         dtype=torch.int64, device=device)
    usable = has_status & (group >= 0)
    group_u, key_u = group[usable], key[usable]
    best = torch.full((len(unique_entities),), -1, dtype=torch.int64, device=device)
    best.scatter_reduce_(0, group_u, key_u, reduce="amax", include_self=True)
    order = torch.argsort(key)
    slot = torch.searchsorted(key.index_select(0, order), best)
    winner = order.index_select(0, slot.clamp(max=rows - 1))

    # A tie on the whole order key is impossible (the ordinal is unique), so a conflict is a tie
    # on (rank, timestamp) with different statuses: two lines claiming the last word at once.
    # Found by segment reductions, not by a loop over entities.
    tie_key = (rank * ts_stride) + ts_norm
    best_tie = torch.full((len(unique_entities),), -1, dtype=torch.int64, device=device)
    best_tie.scatter_reduce_(0, group_u, tie_key[usable], reduce="amax", include_self=True)
    attains = usable & (tie_key == best_tie.index_select(0, group.clamp(min=0)))
    status_code = work.column("status").to(torch.int64)
    lowest = torch.full((len(unique_entities),), torch.iinfo(torch.int64).max,
                        dtype=torch.int64, device=device)
    highest = torch.full((len(unique_entities),), torch.iinfo(torch.int64).min,
                         dtype=torch.int64, device=device)
    lowest.scatter_reduce_(0, group[attains], status_code[attains], reduce="amin",
                           include_self=True)
    highest.scatter_reduce_(0, group[attains], status_code[attains], reduce="amax",
                            include_self=True)
    for entity_index in torch.nonzero(lowest != highest, as_tuple=False).flatten().tolist():  # loop-ok: the entities whose latest status is TIED - a conflict list the fold refuses to hide, never the entities
        tied = torch.nonzero(attains & (group == entity_index), as_tuple=False).flatten().tolist()
        conflicts.append({"conflict": "tied-latest-status",
                          "entity": unique_entities[entity_index],
                          "statuses": sorted({status[i] for i in tied}),
                          "rows": [ids[i] for i in tied]})
    winner_rows = winner.tolist()
    return StatusFold(tuple(unique_entities),
                      tuple(status[i] for i in winner_rows),
                      tuple(int(work.global_ordinals[i]) for i in winner_rows),
                      tuple(conflicts), depth)


def fold_receipt(fold: StatusFold, ingestion: Ingestion) -> dict[str, Any]:
    return {"fold": fold.as_dict(),
            "fold_id": chash({"entities": list(fold.entity_ids),
                              "status": list(fold.status)}),
            "generation_id": ingestion.generation_id()}
