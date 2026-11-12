"""toy.py - the shared toy corpus of the ATLAS-P1 contract, ingested as a conceptric level 0.

The fixture (``evidence/ATLAS_PROGRAMME/lane_c/toy_corpus.py``) is the row inventory every
lane-C clause executes against, and this packet's bar is exact: the tables built here must equal
it. ``atlas/tests/test_record_toy_fixture.py`` asserts that in both directions - every declared
field of every row, the anchor postings against ``MENTIONS``, the walk edges against
``RELATIONS`` - so a drift in either direction is a failing test rather than a discrepancy
someone notices later.

THE BLOB. The fixture gives eight turn TEXTS and no bytes. A span needs bytes, so this module
declares one: ``toy-chat-blob@v1`` is the eight turns of ``SPAN_ORDER`` joined by a single
newline, UTF-8. That is a declaration, not a guess, and it is part of the dataset declaration's
hash: change the joiner and every span id changes, which is the property B.1 is for.

WHAT RUNG (a) CANNOT EXTRACT HERE - and it is most of the interesting part. The fixture supplies
rows that are ALREADY typed: predicate, subject/object, polarity, kind, claim_id, the validity
interval. Parsing them out of the fixture module is a pure parse, so they are admitted at rung
(a) by B.7's letter. Parsing them out of the eight sentences would not be: "I adopted a cat
named Miso last week" yields predicate=adopt, subject=self, entity=Miso and a week-precision
event date only through extraction that rung (a) does not have. What this module therefore
demonstrates on the toy is the STORE and the CHECK, not extraction: the witness predicate
verifies that every surface the row claims is actually located in the bytes of the turn it names
as its witness, and a row whose surface is absent is refused. That is the honest boundary, and
the LongMemEval measurement is where it gets a number.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping

import torch

from ..declaration import (RUNG_A, AliasRow, DatasetDeclaration, FieldAliasTable, FieldSpec,
                           ContentCarrier, RelationKindSpec, RowKindSpec,
                           SurfaceSetSchema)
from ..content import declared_axes
from ..ingestion import Ingestion, item_cache_key
from ..joins import anchor_expand, typed_field_pairs
from ..json_spans import SEG_VERSION, SEGMENTER_ID

__all__ = ["FIXTURE_PATH", "load_fixture", "declaration", "ingest", "ToyIngest", "BLOB_JOINER"]

FIXTURE_PATH = Path(__file__).resolve().parents[4] / "evidence" / "ATLAS_PROGRAMME" / \
    "lane_c" / "toy_corpus.py"

# The declared blob construction. One newline between turns; nothing else is added.
BLOB_JOINER = b"\n"
BLOB_MEDIA_TYPE = "text/plain; charset=utf-8"
EXTRACTOR_ID = "toy-fixture-parse@v1"

# The four closed vocabularies the fixture's "Value dictionaries" section declares in full.
SPEAKER = ("user", "assistant")
KIND = ("event", "state", "intent", "preference", "assertion", "correction", "question")
POLARITY = ("asserted", "negated", "hypothetical", "attributed")
DATE_PRECISION = ("none", "day", "week", "month", "year")

# The fixture's own column list, minus the two that are not FIELDS in this layer: row_id is
# B.2's chash and span_id is the witness address, and neither may be a hashed field of itself.
_DICT_COLUMNS = ("session_id", "predicate", "subject", "object", "entity", "place",
                 "attributed_to", "claim_id", "jurisdiction", "source_id")
_DATE_COLUMNS = ("valid_from", "valid_to", "event_date")

ANCHOR_COLUMNS = ("subject", "object", "entity", "place")
MUST_APPEAR = ANCHOR_COLUMNS

# Surface set schema, obligation 6: who 'self' is, per speaker. E.0 refuses without this, and a
# guess here would silently change the node set the generator is indexed by.
PRINCIPAL_SURFACES = {
    "toy_row": {
        "speaker=user": ("I", "me", "my", "mine", "myself", "we", "us", "our", "ours"),
        "speaker=assistant": ("you", "your", "yours"),
    }
}


def load_fixture() -> ModuleType:
    """Import the fixture module from its evidence path (it is data, not an installed package)."""
    spec = importlib.util.spec_from_file_location("atlas_record_toy_fixture", FIXTURE_PATH)
    module = importlib.util.module_from_spec(spec)          # type: ignore[arg-type]
    spec.loader.exec_module(module)                         # type: ignore[union-attr]
    return module


# THE CONTENT-BEARING ROW KIND OF THE FIXTURE: "one argument span, as the fixture declares it"
# (the reconciliation). A toy row's own WITNESS span is the turn that asserts it, which is the
# text the fixture wrote, so the carrier names no column and reads the witness directly.
CONTENT_CARRIERS = (ContentCarrier("toy_row", "", "utf8"),)


def declaration(*, content: Mapping[str, Any] | None = None) -> DatasetDeclaration:
    """B.5's dataset declaration for the toy corpus, frozen and content-addressed."""
    fields = [
        FieldSpec("session_id", "dict_utf8", RUNG_A, doc="the session the turn belongs to"),
        FieldSpec("ordinal", "int64", RUNG_A, doc="the turn's index within its session"),
        FieldSpec("speaker", "enum", RUNG_A, SPEAKER, doc="the declared role of the turn"),
        FieldSpec("kind", "enum", RUNG_A, KIND),
        FieldSpec("predicate", "dict_utf8", RUNG_A),
        FieldSpec("subject", "dict_utf8", RUNG_A),
        FieldSpec("object", "dict_utf8", RUNG_A),
        FieldSpec("entity", "dict_utf8", RUNG_A),
        FieldSpec("place", "dict_utf8", RUNG_A),
        FieldSpec("polarity", "enum", RUNG_A, POLARITY),
        FieldSpec("attributed_to", "dict_utf8", RUNG_A),
        FieldSpec("claim_id", "dict_utf8", RUNG_A),
        FieldSpec("jurisdiction", "dict_utf8", RUNG_A),
        FieldSpec("valid_from", "date", RUNG_A, doc="lower bound of the state's validity"),
        FieldSpec("valid_to", "date", RUNG_A, doc="upper bound; null reads as +infinity"),
        FieldSpec("event_date", "date", RUNG_A, doc="lower bound of the event interval"),
        FieldSpec("date_precision", "enum", RUNG_A, DATE_PRECISION,
                  doc="width of the event interval; the upper bound is derived from it"),
        FieldSpec("source_id", "dict_utf8", RUNG_A),
    ]
    row_kind = RowKindSpec(
        "toy_row", tuple(fields), time_field="event_date",
        witness_predicate_id="surfaces_located@v1", anchor_fields=ANCHOR_COLUMNS,
        doc="one typed row of the shared toy corpus; its witness is the turn that asserts it")
    relations = (
        RelationKindSpec("meet", ("toy_row",), ("toy_row",), "argument_link@v1", RUNG_A,
                         doc="the fixture's walk rule: an edge to every row naming an argument"),
        RelationKindSpec("corrects", ("toy_row",), ("toy_row",), "typed_field_predicate@v1",
                         RUNG_A, counted=False,
                         doc="a negated claim against the asserted claim it overturns"),
    )
    aliases = tuple(
        AliasRow(surface, "row_field", "subject=self", "lane B / packet I1", "2026-09-21",
                 scope="toy_row", condition=condition)
        for condition, surfaces in PRINCIPAL_SURFACES["toy_row"].items()
        for surface in surfaces)
    # The ablation switch; ``content=None`` is the OFF position (see longmem.declaration).
    _recipe, _axes = declared_axes(content, CONTENT_CARRIERS, SEG_VERSION)
    return DatasetDeclaration(
        dataset_id="atlas-toy-corpus",
        row_kinds=(row_kind,),
        relation_kinds=relations,
        alias_table=FieldAliasTable("toy-aliases@v1", aliases),
        surface_set=SurfaceSetSchema(
            "toy-surfaces@v1",
            anchor_columns={"toy_row": ANCHOR_COLUMNS},
            principal_surfaces=PRINCIPAL_SURFACES,
            must_appear_columns={"toy_row": MUST_APPEAR},
            principals=("self",)),
        segmenter_id=SEGMENTER_ID, seg_version=SEG_VERSION,
        segmentation=_recipe, content_axes=_axes,
        blob_glob="evidence/ATLAS_PROGRAMME/lane_c/toy_corpus.py")


class ToyIngest:
    """An ingestion plus the fixture-local names needed to compare against the fixture."""

    __slots__ = ("ingestion", "local_row_ids", "span_names", "fixture")

    def __init__(self, ingestion: Ingestion, local_row_ids: tuple[str, ...],
                 span_names: tuple[str, ...], fixture: ModuleType) -> None:
        self.ingestion = ingestion
        self.local_row_ids = local_row_ids      # r1..r8b in mint order; NOT stored in the record
        self.span_names = span_names            # t1..t8 in span-ordinal order
        self.fixture = fixture


def _witness_options(declaration_: DatasetDeclaration) -> dict[str, Any]:
    surface_set = declaration_.surface_set
    return {"must_appear": surface_set.must_appear_columns["toy_row"],
            "principals": surface_set.principals,
            "principal_surfaces": surface_set.principal_surfaces["toy_row"],
            "condition_field": "speaker"}


def ingest(device: torch.device | str | None = None, *,
           extra_rows: list[dict[str, Any]] | None = None,
           content: Mapping[str, Any] | None = None) -> ToyIngest:
    """Ingest the toy corpus at rung (a). Complexity: O(rows * columns) plus O(blob bytes).

    ``extra_rows`` plants additional candidate rows (used by the fail-closed test); they go
    through the same admission as every other row and are refused on the same terms.
    """
    fixture = load_fixture()
    declared = declaration(content=content)
    ingestion = Ingestion(declared, device)

    # ---- blob and spans: the bytes every span addresses.
    texts = [fixture.SPAN_TEXT[name] for name in fixture.SPAN_ORDER]
    blob = BLOB_JOINER.join(t.encode("utf-8") for t in texts)
    handle = ingestion.blobs.put_bytes(blob, BLOB_MEDIA_TYPE)
    ranges, cursor = [], 0
    for text in texts:
        size = len(text.encode("utf-8"))
        ranges.append((cursor, cursor + size))
        cursor += size + len(BLOB_JOINER)
    # THE TOY'S BLOB IS ONE ITEM (B.28). Every span, row and relation of the fixture is minted
    # inside this mark, so ``segments.store_ingestion`` cuts exactly one segment for the corpus
    # and a second run of the front door OPENS it - extractions 0, parses 0, source_reads 0 -
    # instead of re-minting the fixture. The item is the WHOLE blob and not a line of it because
    # the fixture's walk relations join rows witnessed by different spans, and
    # ``segments.cut_segments`` refuses (MalformedSource, "relation instances cross item
    # boundaries") any cut a relation crosses: the unit of persistence is the unit no declared
    # relation spans, which for a ten-row fixture with a walk lens is the corpus.
    key = item_cache_key(handle, (0, len(blob)), EXTRACTOR_ID, declared.declaration_hash)
    with ingestion.item(key, item_bytes=blob, blob_handles=(handle,), extracts=False):
        span_ords = ingestion.add_spans(handle, ranges)
        span_of_name = {name: int(span_ords[i]) for i, name in enumerate(fixture.SPAN_ORDER)}

        # ---- rows: the fixture's own column list, minus row_id and span_id.
        columns = [f.name for f in declared.row_kind("toy_row").fields]
        candidates = list(fixture.ROWS) + list(extra_rows or [])
        records = [{name: row[name] for name in columns} for row in candidates]
        witnesses = [span_of_name[row["span_id"]] for row in candidates]
        with ingestion.measure("rows"):
            admission = ingestion.store.append_rows(
                "toy_row", records, witnesses, rung=RUNG_A, extractor_id=EXTRACTOR_ID,
                witness_options=_witness_options(declared))
        admitted_names = tuple(candidates[position]["row_id"]
                               for position in admission.positions)

        # ---- anchors: postings from the declared anchor columns. Built before the walk, because
        # the walk rule is defined in terms of "every row that names this argument" - postings.
        with ingestion.measure("anchors"):
            index = ingestion.build_anchors(rung=RUNG_A)

        table = ingestion.store.table("toy_row")
        # ---- walk relations: for every row whose predicate is a declared walk kind, one edge
        # per argument slot to every row the anchor index resolves it to. Fully vectorised.
        with ingestion.measure("relations"):
            for kind in fixture.WALK_KINDS:
                slots = fixture.ARGUMENT_SLOTS[kind]
                predicate_code = table.surface_code("predicate", kind)
                if predicate_code is None:
                    continue
                sources = torch.nonzero(table.column("predicate") == predicate_code,
                                        as_tuple=False).flatten()
                if sources.numel() == 0:
                    continue
                for slot in slots:                    # a closed declared set, not a row loop
                    surfaces = _surface_ordinals(table, index, slot, sources)
                    keep = surfaces >= 0
                    src_rows = table.global_ordinals.index_select(0, sources[keep])
                    src, dst = anchor_expand(index, src_rows, surfaces[keep])
                    if src.numel() == 0:
                        continue
                    _append_walk(ingestion, kind, table, src, dst, slot, declared)
            _append_corrects(ingestion, table, declared)

    local_ids = admitted_names
    return ToyIngest(ingestion, local_ids, tuple(fixture.SPAN_ORDER), fixture)


def _surface_ordinals(table: Any, index: Any, column: str,
                      rows: torch.Tensor) -> torch.Tensor:
    """Anchor-vocabulary ordinal of each named row's value in ``column``; -1 where null."""
    vocabulary = table.vocabulary(column)
    device = table.device
    lookup = torch.tensor([index.ordinal_of(s) for s in vocabulary],
                          dtype=torch.int64, device=device)
    codes = table.column(column).index_select(0, rows).to(torch.int64)
    null = codes < 0
    safe = codes.clamp(min=0)
    out = lookup.index_select(0, safe)
    out[null] = -1
    return out


def _append_walk(ingestion: Ingestion, kind: str, table: Any, src: torch.Tensor,
                 dst: torch.Tensor, slot: str, declared: DatasetDeclaration) -> None:
    """Admit the walk edges of one argument slot, each checked against the source's bytes."""
    local = ingestion.store.local_of_global("toy_row")
    src_local = local.index_select(0, src)
    dst_local = local.index_select(0, dst)
    witness = table.witness_span.index_select(0, src_local)
    arguments = table.decode(slot)
    speakers = table.decode("speaker")
    anchor_values = [set() for _ in range(len(table))]
    for column in declared.surface_set.anchor_columns["toy_row"]:
        for position, value in enumerate(table.decode(column)):
            if value is not None:
                anchor_values[position].add(value)
    src_list, dst_list = src_local.tolist(), dst_local.tolist()
    contexts = [{"argument": arguments[s], "target_surfaces": tuple(anchor_values[d]),
                 "condition": f"speaker={speakers[s]}"}
                for s, d in zip(src_list, dst_list)]
    witness_list = witness.tolist()
    ingestion.append_relations(
        kind, src.tolist(), dst.tolist(),
        [(int(w),) for w in witness_list],  # loop-ok: the walk edges of C.25's frozen ten-row fixture, unpacked once
        contexts=contexts, extractor_id=EXTRACTOR_ID,
        witness_options={"principals": declared.surface_set.principals,
                         "principal_surfaces": declared.surface_set.principal_surfaces["toy_row"]})


_CORRECTS_JOIN = {
    "key": "claim_id",
    "equal_fields": ("claim_id", "predicate", "subject", "object", "session_id"),
    "source_values": {"polarity": "negated"},
    "target_values": {"polarity": "asserted"},
    "order_field": "ordinal",
}


def _append_corrects(ingestion: Ingestion, table: Any, declared: DatasetDeclaration) -> None:
    """``corrects``: a declared pure function of declared fields (B.7's typed_field_predicate).

    The join key is ``claim_id``; the pairs are expanded exactly by ``typed_field_pairs`` and
    filtered on device by the declared equalities, polarities and ordinal order. The witness is
    the NEGATING row's span - the bytes in which the correction is actually made - which is what
    the fixture records for ``('corrects','r8','r7','t8',1)``.
    """
    if not len(table):
        return
    left, right = typed_field_pairs(table.column(_CORRECTS_JOIN["key"]).to(torch.int64))
    if left.numel() == 0:
        return
    keep = torch.ones_like(left, dtype=torch.bool)
    for column in _CORRECTS_JOIN["equal_fields"]:
        values = table.column(column).to(torch.int64)
        keep &= values.index_select(0, left) == values.index_select(0, right)
    polarity = table.column("polarity").to(torch.int64)
    negated = table.surface_code("polarity", _CORRECTS_JOIN["source_values"]["polarity"])
    asserted = table.surface_code("polarity", _CORRECTS_JOIN["target_values"]["polarity"])
    keep &= polarity.index_select(0, left) == negated
    keep &= polarity.index_select(0, right) == asserted
    ordinal = table.column(_CORRECTS_JOIN["order_field"]).to(torch.int64)
    keep &= ordinal.index_select(0, left) > ordinal.index_select(0, right)
    left, right = left[keep], right[keep]
    if left.numel() == 0:
        return
    rows = table.rows()
    pairs = list(zip(left.tolist(), right.tolist()))
    contexts = [{"source_fields": rows[s], "target_fields": rows[t]}
                for s, t in pairs]  # loop-ok: the corrects pairs of C.25's frozen ten-row fixture, unpacked once
    witness = table.witness_span.index_select(0, left)
    witness_list = witness.tolist()
    globals_ = table.global_ordinals
    ingestion.append_relations(
        "corrects", globals_.index_select(0, left).tolist(),
        globals_.index_select(0, right).tolist(),
        [(int(w),) for w in witness_list],  # loop-ok: the same fixture pairs, unpacked once
        contexts=contexts, extractor_id=EXTRACTOR_ID,
        witness_options={"equal_fields": _CORRECTS_JOIN["equal_fields"],
                         "source_values": _CORRECTS_JOIN["source_values"],
                         "target_values": _CORRECTS_JOIN["target_values"],
                         "order_field": _CORRECTS_JOIN["order_field"]})
