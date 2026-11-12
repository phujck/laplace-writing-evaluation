"""longmem.py - LongMemEval-S: sessions, turns, speakers and dates at rung (a); entities,
quantities, events and state claims at rung (b).

B.33 names exactly what rung (a) gets here and this module builds exactly that and stops:
``session`` rows with the date parsed "by a declared rule that strips the parenthesised weekday
before dateutil", ``turn`` rows with the declared role as a speaker enum and the content as a
BYTE SPAN rather than a copy, and the ``in_session`` / ``follows`` relations the container's own
ordering states. Everything B.33 assigns to rung (b) - entities, mentions, events with resolved
relative dates, state claims - is built by ``declaration('ab')`` / ``ingest(rungs='ab')`` and by
nothing else, so the rung-(a) store packet I1 measured can still be produced byte-identically
and the residue that justifies rung (b) is a RE-RUN rather than a quotation.

WHAT RUNG (a) CANNOT EXTRACT HERE, precisely - the measured licence for rung (b):

1. No entity exists. Nothing in the container names 'Miso' or 'my sister' as an object, so the
   anchor vocabulary at rung (a) is exactly {session ids, question ids} - identifiers a question
   never utters. A question therefore resolves ZERO anchors, and the only typed conditions it can
   raise are on the declared columns: speaker, session date, turn ordinal.
2. No event and no claim. There is no predicate, no polarity, no subject/object, so there is no
   ``corrects`` and no state interval; a knowledge-update question has nothing typed to fold.
3. No date inside a turn. Session dates are container fields and are rung (a); '"last March"'
   inside a turn's content is rung (b) by B.8 and is not read here.
4. No cross-session link. ``in_session`` and ``follows`` are the only relations available, and
   both are intra-session, so the relation walk cannot leave the session it starts in - which is
   why the multi-session question types are unreachable at rung (a) by construction, not by
   accident.

STREAMING. The file is 277 MB and is never materialised: ``json_spans.iter_array_items`` yields
one case's raw bytes at a time and those bytes become that case's blob (B.33: "one haystack is
one blob"). Only the requested number of haystacks is ever held.

GOLD IS NOT IN THE RECORD. ``answer``, ``answer_session_ids`` and the per-turn ``has_answer``
annotations are evaluator data. They are read by ``read_gold`` into a separate object and never
enter a row, a relation or an anchor - the discipline ``qasper_data.py`` already keeps by writing
gold.json apart from sources.json, kept here for the same reason: a store that has seen the gold
cannot measure anything about reaching it.
"""

from __future__ import annotations

import datetime as _dt
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

import torch

from .. import extract
from .. import propose
from ..declaration import (RUNG_A, RUNG_B, RUNG_C, DatasetDeclaration, FieldAliasTable, FieldSpec,
                           ContentCarrier, RelationKindSpec, RowKindSpec,
                           SurfaceSetSchema)
from ..content import declared_axes
from ..ingestion import Ingestion
from ..json_spans import SEG_VERSION, SEGMENTER_ID, iter_array_items, scan_value
from ..witness import register_parser

__all__ = ["DATASET_PATH", "declaration", "ingest", "read_gold", "GoldIndex",
           "parse_session_date", "QUESTION_TYPES", "scan_value", "EXTRACTOR_ID",
           "EXTRACTOR_ID_B", "SELF_SUBJECT", "BLOB_MEDIA_TYPE"]

DATASET_PATH = Path(__file__).resolve().parents[4] / "synthetics papers" / \
    "corpus-as-a-state" / "reconstruction" / "extension" / ".cache" / "longmemeval" / \
    "longmemeval_s_cleaned.json"

BLOB_MEDIA_TYPE = "application/json"
EXTRACTOR_ID = "longmem-rung-a@v1"

# The official six, verbatim from reconstruction/extension/longmem_data.py:24-31. Not re-derived
# and not extended: an enum vocabulary is declared in full (B.5) and this is the declaration.
QUESTION_TYPES = ("single-session-user", "single-session-assistant",
                  "single-session-preference", "multi-session", "temporal-reasoning",
                  "knowledge-update")
SPEAKERS = ("user", "assistant")

# B.33's declared date rule, written out: strip the parenthesised weekday, then parse. The
# remaining form is fixed-width ('2023/05/20 02:21'), so strptime IS the parse - dateutil would
# add a dependency and a guessing mode for a grammar the container never varies.
_WEEKDAY = re.compile(r"\s*\([A-Za-z]{3}\)\s*")
_DATE_FORMAT = "%Y/%m/%d %H:%M"


def parse_session_date(surface: str) -> _dt.datetime:
    """'2023/05/20 (Sat) 02:21' -> datetime(2023, 5, 20, 2, 21). Declared rule, no inference."""
    return _dt.datetime.strptime(_WEEKDAY.sub(" ", surface).strip(), _DATE_FORMAT)


register_parser("longmem_session_date@v1", parse_session_date)


# THE CONTENT-BEARING ROW KINDS OF THIS DATASET, and the declared decoder of each one's text.
# The reconciliation's per-dataset leaf: "one TURN of one session ... it must carry, in addition,
# one unit vector per declared encoder axis and its token set", and a turn's text is the JSON
# string node ``content_span`` addresses, quotes and escapes included - so the decoder is the one
# ``extract.locator_for_json_string`` implements and the leaf ranges come back as BLOB BYTES.
CONTENT_CARRIERS = (ContentCarrier("turn", "content_span", "json_string"),)


def declaration(rungs: str = "a", *, content: Mapping[str, Any] | None = None) -> DatasetDeclaration:
    """B.5's declaration for LongMemEval-S. ``rungs='a'`` is the parse-only store.

    A rung-(b) kind is declared only when this ingestion will fill it, because B.35 counts a
    declared-but-never-instantiated kind as a coverage hole. The two declarations have different
    declaration hashes, so the before/after arms of the F2 measurement are told apart by their
    receipts rather than by a label - and the rung-(a) arm is byte-identical to the one packet I1
    measured, which is what lets "0 questions resolved an anchor" be re-run rather than quoted.
    """
    question = RowKindSpec(
        "question",
        (FieldSpec("question_id", "dict_utf8", RUNG_A),
         FieldSpec("question_type", "enum", RUNG_A, QUESTION_TYPES),
         FieldSpec("question_date", "timestamp", RUNG_A,
                   doc="the declared time the question is asked; B.33's question_date"),
         FieldSpec("question_date_surface", "dict_utf8", RUNG_A,
                   doc="the located surface the typed date is parsed from"),
         FieldSpec("text_span", "span_ref", RUNG_A, doc="byte range of the question string")),
        time_field="question_date", witness_predicate_id="json_member_equals@v1",
        anchor_fields=("question_id",))
    session = RowKindSpec(
        "session",
        (FieldSpec("question_id", "dict_utf8", RUNG_A, doc="the haystack this session is in"),
         FieldSpec("session_id", "dict_utf8", RUNG_A),
         FieldSpec("session_index", "int64", RUNG_A),
         FieldSpec("session_date", "timestamp", RUNG_A),
         FieldSpec("session_date_surface", "dict_utf8", RUNG_A)),
        time_field="session_date", witness_predicate_id="surfaces_located@v1",
        anchor_fields=("session_id",))
    turn = RowKindSpec(
        "turn",
        (FieldSpec("question_id", "dict_utf8", RUNG_A),
         FieldSpec("session_index", "int64", RUNG_A),
         FieldSpec("turn_index", "int64", RUNG_A),
         FieldSpec("speaker", "enum", RUNG_A, SPEAKERS, doc="the container's declared role"),
         # THE DATE A QUESTION CAN STATE, ON THE ROW IT CONDITIONS. Before this column the
         # carrier carried no date at all: ``session_date`` lived on the SESSION row and the
         # turn row is what every content question conditions, so a benchmark question that
         # says "in May" had no declared column to become a condition on and the compiler
         # refused it (demonstrated: evidence/ATLAS_PROGRAMME/waves/P3-the-read/
         # date_condition_refusal.json, the failing command before this line existed). The
         # value is the CONTAINER's own declared date, copied from the session row this turn
         # is in - not parsed from the turn, which would be rung (b) by B.8 - and the session
         # row is its witness: the same bytes, already located, already checked by
         # surfaces_located@v1 on that row. It is NOT the turn's ``time_field``: a turn has no
         # declared time of its own, and making a container's date the row's own time would
         # silently re-base every relative date rung (b) resolves inside the turn.
         FieldSpec("session_date", "timestamp", RUNG_A,
                   doc="the declared date of the session this turn is in, witnessed by that "
                       "session row; the condition column a dated question states (A.12)"),
         FieldSpec("content_span", "span_ref", RUNG_A,
                   doc="byte range of the turn's content; the row stores no copy (B.1)")),
        witness_predicate_id="json_member_equals@v1")
    relations = (
        RelationKindSpec("in_session", ("turn",), ("session",), "typed_field_predicate@v1",
                         RUNG_A, doc="containment, from the container's own parallel arrays"),
        RelationKindSpec("follows", ("turn",), ("turn",), "typed_field_predicate@v1", RUNG_A,
                         doc="the container's turn order, one edge per consecutive pair"),
        RelationKindSpec("in_jurisdiction", ("session",), ("question",),
                         "typed_field_predicate@v1", RUNG_A, counted=False,
                         doc="which haystack a session belongs to"),
        RelationKindSpec("supersedes_blob", ("question",), ("question",),
                         "typed_field_predicate@v1", RUNG_A, counted=False,
                         doc="B.31: a changed haystack is a NEW blob; the old one is marked "
                             "superseded by this edge, never edited or removed"),
    )
    row_kinds: tuple[RowKindSpec, ...] = (question, session, turn)
    anchor_columns: dict[str, tuple[str, ...]] = {"question": ("question_id",),
                                                  "session": ("session_id",)}
    must_appear: dict[str, tuple[str, ...]] = {
        "session": ("session_id", "session_date_surface")}
    if "b" in rungs:
        entity = RowKindSpec(
            "entity",
            (FieldSpec("question_id", "dict_utf8", RUNG_A),
             FieldSpec("surface", "dict_utf8", RUNG_B)),
            witness_predicate_id="surfaces_located@v1", anchor_fields=("surface",))
        quantity = RowKindSpec(
            "quantity",
            (FieldSpec("question_id", "dict_utf8", RUNG_A),
             FieldSpec("value_surface", "dict_utf8", RUNG_B),
             FieldSpec("value_scaled", "int64", RUNG_B),
             FieldSpec("value_scale", "int64", RUNG_B),
             FieldSpec("unit_surface", "dict_utf8", RUNG_B)),
            witness_predicate_id="surfaces_located@v1")
        event = RowKindSpec(
            "event",
            (FieldSpec("question_id", "dict_utf8", RUNG_A),
             FieldSpec("session_index", "int64", RUNG_A),
             FieldSpec("date_surface", "dict_utf8", RUNG_B),
             FieldSpec("event_date", "timestamp", RUNG_B,
                       doc="relative surfaces resolved against the row's session date (B.33)"),
             FieldSpec("date_precision", "enum", RUNG_B, extract.DATE_PRECISION),
             FieldSpec("relative", "bool", RUNG_B)),
            time_field="event_date", witness_predicate_id="surfaces_located@v1")
        state_claim = RowKindSpec(
            "state_claim",
            (FieldSpec("question_id", "dict_utf8", RUNG_A),
             FieldSpec("session_index", "int64", RUNG_A),
             FieldSpec("subject", "dict_utf8", RUNG_B, doc="the declared principal of the turn"),
             FieldSpec("attribute", "dict_utf8", RUNG_B),
             FieldSpec("value", "dict_utf8", RUNG_B),
             FieldSpec("polarity", "enum", RUNG_B, extract.POLARITY),
             FieldSpec("claimed_at", "timestamp", RUNG_B,
                       doc="the session date the claim was made on")),
            time_field="claimed_at", witness_predicate_id="surfaces_located@v1")
        row_kinds = row_kinds + (entity, quantity, event, state_claim)
        relations = relations + (
            RelationKindSpec("mentions", ("entity", "quantity"), ("turn",), "spans_nest@v1",
                             RUNG_B, doc="the carrier's surface is located inside this turn"),
            RelationKindSpec("about", ("event", "state_claim"), ("turn",), "spans_nest@v1",
                             RUNG_B, doc="the claim or date expression is located in this turn"),
            RelationKindSpec("same_entity", ("entity",), ("entity",), "argument_link@v1",
                             RUNG_B, symmetric=True,
                             doc="the shorter surface is a token subsequence of the longer, "
                                 "both entities of the SAME haystack (B.29 item-locality)"),
            RelationKindSpec("precedes", ("event",), ("event",), "typed_field_predicate@v1",
                             RUNG_B, doc="the source event's resolved date is the earlier one"),
            RelationKindSpec("supersedes", ("state_claim",), ("state_claim",),
                             "typed_field_predicate@v1", RUNG_B,
                             doc="a later value of the SAME subject and attribute"),
        )
        anchor_columns["entity"] = ("surface",)
        must_appear.update({"entity": ("surface",), "quantity": ("value_surface",),
                            "event": ("date_surface",),
                            "state_claim": ("attribute", "value")})
    # THE ABLATION SWITCH, read off the declared draw row this call was given. ``content=None``
    # is the OFF position: the recipe and the axes are absent, they add no key to the hashed
    # field set, and this declaration is byte-identical to the one every earlier wave measured.
    _recipe, _axes = declared_axes(content, CONTENT_CARRIERS, SEG_VERSION)
    return DatasetDeclaration(
        dataset_id=f"longmemeval-s-rung-{rungs}",
        row_kinds=row_kinds,
        relation_kinds=relations,
        alias_table=FieldAliasTable("longmem-aliases@v1", ()),
        surface_set=SurfaceSetSchema(
            f"longmem-surfaces@{rungs}",
            anchor_columns=anchor_columns,
            must_appear_columns=must_appear,
            principal_surfaces={},
            principals=()),
        segmenter_id=SEGMENTER_ID, seg_version=SEG_VERSION,
        segmentation=_recipe, content_axes=_axes,
        blob_glob=str(DATASET_PATH))


# --------------------------------------------------------------------------- gold (evaluator)
@dataclass(frozen=True, slots=True)
class GoldIndex:
    """Evaluator-only annotations. Never read by ingestion, never stored in the record."""

    answer_sessions: dict[str, tuple[str, ...]]
    gold_turns: dict[str, tuple[tuple[int, int], ...]]      # question_id -> (session_ix, turn_ix)
    answers: dict[str, str]


def read_gold(path: Path = DATASET_PATH, *, limit: int | None = None) -> GoldIndex:
    """Read the gold annotations into a separate object, by the same streaming scan."""
    answer_sessions: dict[str, tuple[str, ...]] = {}
    gold_turns: dict[str, list[tuple[int, int]]] = {}
    answers: dict[str, str] = {}
    for _, _, raw in iter_array_items(Path(path), limit=limit):
        case, _ = scan_value(raw, 0, 0)
        question_id = case.member("question_id").text
        answer_sessions[question_id] = tuple(
            item.text for item in (case.member("answer_session_ids").items or ()))
        answers[question_id] = str(case.member("answer").value)
        found: list[tuple[int, int]] = []
        for session_index, session in enumerate(case.member("haystack_sessions").items or ()):
            for turn_index, turn in enumerate(session.items or ()):
                flag = turn.get("has_answer")
                if flag is not None and flag.value is True:
                    found.append((session_index, turn_index))
        gold_turns[question_id] = found
    return GoldIndex(answer_sessions, {k: tuple(v) for k, v in gold_turns.items()}, answers)


# --------------------------------------------------------------------------- ingestion
def _item_key(raw: bytes, extractor_id: str, declaration_hash: str) -> str:
    """B.28 as amended, imported lazily to keep ``diff`` importable from here without a cycle."""
    from ..diff import item_bytes_cache_key
    return item_bytes_cache_key(raw, extractor_id, declaration_hash)


def _cases(path: Path, limit: int | None) -> Iterator[tuple[bytes, Any]]:
    for _, _, raw in iter_array_items(path, limit=limit):
        node, _ = scan_value(raw, 0, 0)
        yield raw, node


def ingest(path: Path = DATASET_PATH, *, histories: int | None = None, rungs: str = "a",
           device: torch.device | str | None = None, segments: Any = None,
           proposer: propose.ProposerIdentity | None = None,
           proposal_cache: Path | str | None = None,
           content: Mapping[str, Any] | None = None) -> Ingestion:
    """Ingest ``histories`` haystacks. One haystack is one blob (B.33).

    ``rungs='a'`` is the parse-only store packet I1 measured; ``rungs='ab'`` adds the entity,
    quantity, event and state-claim rows of B.33's rung (b) and the relations they earn;
    ``rungs='abc'`` adds B.33's rung (c) - the light-tier proposer of ``record.propose``, asked
    ONCE per item about that item's MEASURED residue (the turns rung (b) minted nothing from) and
    admitted only where the bytes locate what it proposed.

    Rung (c) FAILS CLOSED. ``rungs`` naming 'c' without a reachable proposer raises rather than
    quietly producing a rung-(ab) store under a rung-(abc) declaration: a store that says it was
    proposed on and was not is the silent fallback the charter forbids.

    ``segments`` is a ``record.segments.SegmentStore``. When one is given, the per-item cache is
    backed by it, so a haystack whose bytes were ingested in ANY earlier run is adopted from its
    segment instead of being parsed and extracted again - the loop below never calls
    ``scan_value`` for such an item. The adopted items are installed after the live ones so the
    relation pass sees only rows it must build edges for; the adopted rows bring their own.

    Complexity: O(bytes) host parse, extraction and witness check; O(R log R) device work for
    the relations, where R is the number of rows. Memory: one case's bytes at a time on the host.
    """
    declared = declaration(rungs, content=content)
    ingestion = Ingestion(declared, device)
    store = ingestion.store
    store.share_dictionary("question_id", [k.kind for k in declared.row_kinds])
    if segments is not None:
        ingestion.cache.attach(segments.cache_index())
    if "c" in rungs and proposer is None:
        raise propose.ProposerUnreachable(
            "rungs names 'c' but no proposer identity was given", {"rungs": rungs})
    # THE PROPOSER'S IDENTITY IS IN B.28's EXTRACTOR ID, not beside it: the per-item cache key is
    # computed from this string, so an item proposed on by THIS proposer is adopted from its
    # segment on every later run and no second ingest calls a model, while a changed prompt,
    # schema, model or tier is a different id and re-proposes.
    extractor_for_the_key = (EXTRACTOR_ID if proposer is None or "c" not in rungs
                             else f"{EXTRACTOR_ID}+{proposer.extractor_id('longmem')}")
    cache_dir = (Path(proposal_cache) if proposal_cache is not None
                 else (Path(segments.root) / "proposals" if segments is not None else None))
    rung_c = _RungC(proposer, cache_dir) if "c" in rungs else None

    with ingestion.measure("parse_and_rows"):
        declaration_hash = declared.declaration_hash
        for _, _, raw in iter_array_items(Path(path), limit=histories):
            # B.28 as amended: the per-item cache is keyed on the ITEM's own content hash, and a
            # batch ingest is a batch of item inserts - so it fills the cache exactly as a single
            # append does. Without this the cache is empty after a load and the "a second batch
            # re-mints nothing" guarantee holds only for items that arrived one at a time.
            key = _item_key(raw, extractor_for_the_key, declaration_hash)
            found = ingestion.cache.get(key)
            if found is not None and "segment_key" in found:
                ingestion.blobs.put_bytes(raw, BLOB_MEDIA_TYPE)
                ingestion.defer_segment(key, found["segment_key"])
                continue
            case, _ = scan_value(raw, 0, 0)
            handle = ingestion.blobs.put_bytes(raw, BLOB_MEDIA_TYPE)
            before = store.row_count
            with ingestion.item(key, item_bytes=raw, blob_handles=(handle,),
                                extracts="b" in rungs):
                _ingest_case(ingestion, handle, case, rungs, rung_c)
            ingestion.cache.put(key, {"rows": store.row_count - before})
    with ingestion.measure("relations"):
        _build_relations(ingestion)
        if "b" in rungs:
            _build_rung_b_relations(ingestion)
    if rung_c is not None:
        rung_c.verify_proposed_relations(ingestion)
        ingestion.counters.update(rung_c.counters())
    ingestion.pending_edges.clear()
    if segments is not None:
        from ..segments import adopt_deferred, store_ingestion
        adopt_deferred(ingestion, segments)
        # The store is read AND written by the same call: what this run had to mint is cut into
        # segments and appended to the ledger now, so the next run adopts it instead of
        # extracting it again. Idempotent - an item already in the store writes nothing.
        ingestion.persistence = store_ingestion(
            segments, ingestion, extractor_roster_hash=extract.extractor_roster_hash())
    with ingestion.measure("anchors"):
        ingestion.build_anchors(rung=RUNG_B if "b" in rungs else RUNG_A)
    ingestion.counters["turns"] = len(store.table("turn"))
    ingestion.counters["sessions"] = len(store.table("session"))
    ingestion.counters["questions"] = len(store.table("question"))
    return ingestion


def _ingest_case(ingestion: Ingestion, handle: str, case: Any, rungs: str = "a",
                 rung_c: "_RungC | None" = None) -> None:
    declared = ingestion.declaration
    question_id = case.member("question_id").text
    date_node = case.member("question_date")
    question_span = int(ingestion.add_spans(handle, [(case.start, case.end)])[0])
    text_span = int(ingestion.add_spans(
        handle, [(case.member("question").start, case.member("question").end)])[0])
    ingestion.store.append_rows(
        "question",
        [{"question_id": question_id,
          "question_type": case.member("question_type").text,
          "question_date": parse_session_date(date_node.text),
          "question_date_surface": date_node.text,
          "text_span": text_span}],
        [question_span], rung=RUNG_A, extractor_id=EXTRACTOR_ID,
        witness_options={"members": {"question_id": ("question_id",),
                                     "question_type": ("question_type",),
                                     "question_date": ("question_date",)},
                         "coerce": {"question_date": "longmem_session_date@v1"},
                         "spans_at": {"text_span": ("question",)}})

    ids = case.member("haystack_session_ids").items or ()
    dates = case.member("haystack_dates").items or ()
    sessions = case.member("haystack_sessions").items or ()
    if not (len(ids) == len(dates) == len(sessions)):
        ingestion.coverage["not_admitted"].append(
            {"question_id": question_id, "reason": "parallel history fields of unequal length"})
        return

    # One witness per session row: the smallest contiguous range containing the session's own id
    # and its own date. Both surfaces are inside it, so surfaces_located@v1 can check the row
    # against bytes without re-reading the whole 500 KB haystack for each of its 50 sessions.
    session_records, session_spans = [], []
    for index, (id_node, date_node_i) in enumerate(zip(ids, dates)):
        lo = min(id_node.start, date_node_i.start)
        hi = max(id_node.end, date_node_i.end)
        session_records.append({
            "question_id": question_id, "session_id": id_node.text, "session_index": index,
            "session_date": parse_session_date(date_node_i.text),
            "session_date_surface": date_node_i.text})
        session_spans.append((lo, hi))
    span_ords = ingestion.add_spans(handle, session_spans)
    ingestion.store.append_rows(
        "session", session_records, span_ords.tolist(), rung=RUNG_A, extractor_id=EXTRACTOR_ID,
        witness_options={"must_appear":
                         declared.surface_set.must_appear_columns["session"]})

    turn_records, turn_ranges, content_ranges = [], [], []
    for session_index, session in enumerate(sessions):
        # the container's own declared date, already parsed once for the session row above; the
        # turn carries it as a CONDITION column and the session row remains its witness
        session_date = session_records[session_index]["session_date"]
        for turn_index, turn in enumerate(session.items or ()):
            content = turn.member("content")
            turn_ranges.append((turn.start, turn.end))
            content_ranges.append((content.start, content.end))
            turn_records.append({"question_id": question_id, "session_index": session_index,
                                 "turn_index": turn_index,
                                 "speaker": turn.member("role").text,
                                 "session_date": session_date, "content_span": None})
    if not turn_records:
        return
    turn_spans = ingestion.add_spans(handle, turn_ranges)
    content_spans = ingestion.add_spans(handle, content_ranges)
    for record, content_span in zip(turn_records, content_spans.tolist()):
        record["content_span"] = int(content_span)
    ingestion.store.append_rows(
        "turn", turn_records, turn_spans.tolist(), rung=RUNG_A, extractor_id=EXTRACTOR_ID,
        witness_options={"members": {"speaker": ("role",)},
                         "spans_at": {"content_span": ("content",)}})
    if "b" in rungs:
        produced, turns, locators, minted = _extract_case(ingestion, handle, question_id,
                                                          sessions, session_records)
        if rung_c is not None:
            rung_c.propose_for_item(ingestion, handle, question_id, produced, turns, locators,
                                    session_records, minted)


# --------------------------------------------------------------------------- rung (b)
EXTRACTOR_ID_B = "longmem-rung-b@v1"
# B.33's rung (b) subject. The claim grammar is possessive ("my sister is..."), so the subject is
# the turn's declared principal and the declaration says what that word is; nothing is inferred.
SELF_SUBJECT = "self"


def _extract_case(ingestion: Ingestion, handle: str, question_id: str, sessions: Any,
                  session_records: list[dict[str, Any]]
                  ) -> tuple[frozenset[tuple[int, int]], list[propose.ResidueTurn],
                             dict[tuple[int, int], Any]]:
    """The per-item rung-(b) pass over one haystack. Pure in this haystack's bytes.

    Nothing here reads the store, another haystack or a corpus statistic, so B.28's per-item
    cache stays byte-identical across corpora and the touched set of an inserted haystack is
    still its own rows (B.29).

    Returns the three things rung (c) needs and nothing it could infer: the set of
    ``(session_index, turn_index)`` this pass minted at least one row from - the complement is
    B.33's MEASURED residue - the turns themselves, and the JSON locator of each turn, so that a
    proposed surface is addressed through the same escape-aware map a grammar's is.
    """
    store = ingestion.store
    entity_rows: dict[str, list[tuple[int, int]]] = {}
    quantity_records, quantity_ranges = [], []
    event_records, event_ranges = [], []
    claim_records, claim_ranges = [], []
    produced: set[tuple[int, int]] = set()
    turns: list[propose.ResidueTurn] = []
    locators: dict[tuple[int, int], Any] = {}

    for session_index, session in enumerate(sessions):
        reference = session_records[session_index]["session_date"]
        for turn_index, turn in enumerate(session.items or ()):
            content = turn.member("content")
            raw = ingestion.blobs.read(handle, content.start, content.end)
            try:
                locator = extract.locator_for_json_string(raw, content.start)
            except ValueError as exc:
                ingestion.coverage["not_admitted"].append(
                    {"question_id": question_id, "session_index": session_index,
                     "reason": str(exc)})
                continue
            text = locator.text
            where = (session_index, turn_index)
            turns.append(propose.ResidueTurn(session_index, turn_index, text,
                                             content.start, content.end))
            locators[where] = locator
            for located in extract.proper_nouns(text):
                produced.add(where)
                entity_rows.setdefault(located.surface, []).append(
                    locator.span(located.start, located.end))
            for quantity in extract.quantities(text):
                produced.add(where)
                quantity_records.append({
                    "question_id": question_id,
                    "value_surface": quantity.located.surface.strip(),
                    "value_scaled": quantity.value_scaled,
                    "value_scale": quantity.value_scale,
                    "unit_surface": quantity.unit_surface})
                quantity_ranges.append(locator.span(quantity.located.start,
                                                    quantity.located.end))
            for expression in extract.temporal_expressions(text, reference):
                produced.add(where)
                event_records.append({
                    "question_id": question_id, "session_index": session_index,
                    "date_surface": expression.located.surface,
                    "event_date": expression.resolved,
                    "date_precision": expression.precision,
                    "relative": expression.relative})
                event_ranges.append(locator.span(expression.located.start,
                                                 expression.located.end))
            for claim in extract.state_claims(text):
                produced.add(where)
                claim_records.append({
                    "question_id": question_id, "session_index": session_index,
                    "subject": SELF_SUBJECT, "attribute": claim.attribute,
                    "value": claim.value, "polarity": claim.polarity,
                    "claimed_at": reference})
                claim_ranges.append(locator.span(claim.located.start, claim.located.end))

    entity_records, entity_witness, entity_occurrences = [], [], []
    for surface, occurrences in sorted(entity_rows.items()):
        entity_records.append({"question_id": question_id, "surface": surface})
        entity_witness.append(int(ingestion.add_spans(handle, [occurrences[0]])[0]))
        entity_occurrences.append(occurrences)
    if entity_records:
        admission = store.append_rows(
            "entity", entity_records, entity_witness, rung=RUNG_B,
            extractor_id=EXTRACTOR_ID_B,
            witness_options={"must_appear": ("surface",), "decode_escapes": True})
        _stage(ingestion, "mentions", admission, entity_occurrences, handle)

    for kind, records, ranges, relation, must in (
            ("quantity", quantity_records, quantity_ranges, "mentions", ("value_surface",)),
            ("event", event_records, event_ranges, "about", ("date_surface",)),
            ("state_claim", claim_records, claim_ranges, "about", ("attribute", "value"))):
        if not records:
            continue
        spans = ingestion.add_spans(handle, ranges).tolist()
        admission = store.append_rows(
            kind, records, spans, rung=RUNG_B, extractor_id=EXTRACTOR_ID_B,
            witness_options={"must_appear": must, "decode_escapes": True})
        _stage(ingestion, relation, admission, [[r] for r in ranges], handle)
    # WHAT RUNG (b) ALREADY HOLDS FOR THIS ITEM, so rung (c) adds rather than duplicates. Built
    # from the records already in hand, so it costs one pass over this item's own rows.
    minted: set[tuple[str, str]] = {("entity", surface) for surface in entity_rows}
    minted |= {("quantity", record["value_surface"]) for record in quantity_records}
    minted |= {("event", record["date_surface"]) for record in event_records}
    minted |= {("state_claim", record["value"]) for record in claim_records}
    return frozenset(produced), turns, locators, frozenset(minted)


def _stage(ingestion: Ingestion, relation: str, admission: Any,
           occurrences: list[list[tuple[int, int]]], handle: str) -> None:
    """Stage the located occurrences of ADMITTED rows for the relation pass (B.4 fail-closed)."""
    bucket = ingestion.pending_edges.setdefault(relation, [])
    for row_ordinal, position in zip(admission.global_ordinals.tolist(), admission.positions):
        bucket.append((handle, int(row_ordinal), occurrences[position]))


# --------------------------------------------------------------------------- rung (c)
class _RungC:
    """B.33's third rung, in place inside this ingester: propose on the residue, admit by bytes.

    One instance per ingestion. It holds no corpus statistic: everything it decides about an item
    is decided from that item's own bytes and that item's own rung-(b) output, so B.29's
    item-locality and B.28's per-item cache are untouched by the widening.

    Complexity: one subprocess per item with a non-empty residue, O(residue bytes) to locate,
    O(k) to admit k candidates, and one vectorised membership test for the proposed relations.
    """

    def __init__(self, proposer: propose.ProposerIdentity, cache_dir: Path | None) -> None:
        self.proposer = proposer
        # THIS DATASET'S VIEW of the closed grammar: its container words (session, turn) and the
        # four row kinds and five relation kinds this declaration carries (propose.py's
        # LONGMEM_GRAMMAR). It is inside the proposer's identity, so a store built under it can
        # never adopt a segment proposed under another dataset's view.
        self.grammar = propose.LONGMEM_GRAMMAR
        self.extractor_id = proposer.extractor_id("longmem")
        self.cache_dir = cache_dir or (Path(tempfile.gettempdir()) / "atlas-rung-c-proposals")
        self.report = propose.AdmissionReport()
        self.census = {"items": 0, "items_with_a_residue": 0, "turns": 0,
                       "turns_with_a_rung_b_row": 0, "residue_turns": 0,
                       "residue_characters": 0, "characters": 0}
        self.cost = {"calls": 0, "cache_hits": 0, "seconds": 0.0, "prompt_chars": 0,
                     "input_tokens": 0, "output_tokens": 0}
        self.proposed_relations: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ per item
    def propose_for_item(self, ingestion: Ingestion, handle: str, question_id: str,
                         produced: frozenset[tuple[int, int]],
                         turns: Sequence[propose.ResidueTurn],
                         locators: dict[tuple[int, int], Any],
                         session_records: list[dict[str, Any]],
                         minted: frozenset[tuple[str, str]] = frozenset()) -> None:
        """Ask about this item's residue once, then admit what the bytes admit."""
        residue, census = propose.residue_of_item(turns, produced)
        self.census["items"] += 1
        for key in ("turns", "turns_with_a_rung_b_row", "residue_turns", "residue_characters",
                    "characters"):                    # loop-ok: the census' own five fields
            self.census[key] += int(census[key])
        if not residue:
            return
        self.census["items_with_a_residue"] += 1
        prompt = propose.proposal_prompt(self.grammar, residue)
        result = propose.call_light_tier(prompt, self.proposer, grammar=self.grammar,
                                         cache_dir=self.cache_dir)
        self.cost["calls"] += 1
        self.cost["cache_hits"] += 1 if result.get("cache_hit") else 0
        self.cost["seconds"] += float(result.get("seconds") or 0.0)
        self.cost["prompt_chars"] += int(result.get("prompt_chars") or 0)
        self.cost["input_tokens"] += int(result.get("input_tokens") or 0)
        self.cost["output_tokens"] += int(result.get("output_tokens") or 0)
        response = result["response"]
        containers = {(turn.session_index, turn.turn_index): turn for turn in residue}  # loop-ok: this item's residue turns
        candidates = propose.locate_candidates(response.get("rows", ()), containers, minted,
                                               self.report, self.grammar)
        self._admit(ingestion, handle, question_id, candidates, locators, session_records)
        for relation in response.get("relations", ()):   # loop-ok: this item's own proposals
            self.report.proposed_relations += 1
            kind = str(relation.get("kind", ""))
            if kind not in propose.PROPOSABLE_RELATION_KINDS:
                self.report.refuse("unknown_relation_kind")
                continue
            self.proposed_relations.append(
                {"kind": kind, "question_id": question_id,
                 "source_surface": str(relation.get("source_surface", "")),
                 "target_surface": str(relation.get("target_surface", ""))})

    def _admit(self, ingestion: Ingestion, handle: str, question_id: str,
               candidates: Sequence[propose.Candidate], locators: dict[tuple[int, int], Any],
               session_records: list[dict[str, Any]]) -> None:
        """Type each located candidate by the DECLARED grammar, then let the store's predicate rule.

        A proposed quantity or event is typed by running the rung-(b) grammar over the candidate's
        OWN located surface: the model says WHERE to look, the declared extractor says what the
        value and unit ARE. So no typed field in this record was ever asserted by a model, and a
        surface the grammar cannot type is refused by name rather than stored with a guess.
        """
        batches: dict[str, tuple[list[dict[str, Any]], list[tuple[int, int]]]] = {}
        for candidate in candidates:                    # loop-ok: this item's located candidates
            where = (candidate.session_index, candidate.turn_index)
            locator = locators.get(where)
            if locator is None:
                self.report.refuse("container_not_declared")
                continue
            reference = session_records[candidate.session_index]["session_date"]
            record: dict[str, Any] | None = None
            if candidate.kind == "entity":
                record = {"question_id": question_id, "surface": candidate.surface}
            elif candidate.kind == "quantity":
                parsed = extract.quantities(candidate.surface)
                if len(parsed) != 1:
                    self.report.refuse("quantity_not_typed_by_the_declared_grammar")
                    continue
                record = {"question_id": question_id,
                          "value_surface": parsed[0].located.surface.strip(),
                          "value_scaled": parsed[0].value_scaled,
                          "value_scale": parsed[0].value_scale,
                          "unit_surface": parsed[0].unit_surface}
            elif candidate.kind == "event":
                parsed_dates = extract.temporal_expressions(candidate.surface, reference)
                if len(parsed_dates) != 1:
                    self.report.refuse("event_not_typed_by_the_declared_grammar")
                    continue
                record = {"question_id": question_id, "session_index": candidate.session_index,
                          "date_surface": parsed_dates[0].located.surface,
                          "event_date": parsed_dates[0].resolved,
                          "date_precision": parsed_dates[0].precision,
                          "relative": parsed_dates[0].relative}
            else:
                record = {"question_id": question_id, "session_index": candidate.session_index,
                          "subject": SELF_SUBJECT, "attribute": candidate.fields["attribute"],
                          "value": candidate.fields["value"],
                          "polarity": candidate.fields["polarity"], "claimed_at": reference}
            records, ranges = batches.setdefault(candidate.kind, ([], []))
            records.append(record)
            ranges.append(locator.span(candidate.start, candidate.end))
        relation_of = {"entity": "mentions", "quantity": "mentions", "event": "about",
                       "state_claim": "about"}
        must_appear = {"entity": ("surface",), "quantity": ("value_surface",),
                       "event": ("date_surface",), "state_claim": ("attribute", "value")}
        for kind, (records, ranges) in sorted(batches.items()):  # loop-ok: the four proposable row kinds
            spans = ingestion.add_spans(handle, ranges).tolist()
            admission = ingestion.store.append_rows(
                kind, records, spans, rung=RUNG_C, extractor_id=self.extractor_id,
                witness_options={"must_appear": must_appear[kind], "decode_escapes": True})
            admitted = len(admission.positions)
            self.report.admit(kind, admitted)
            if admitted < len(records):
                self.report.refuse("witness_predicate_refused", len(records) - admitted)
            _stage(ingestion, relation_of[kind], admission,
                   [[r] for r in ranges], handle)  # loop-ok: this batch's own located ranges

    # ------------------------------------------------------------------ after the relation pass
    def verify_proposed_relations(self, ingestion: Ingestion) -> None:
        """A proposed relation is admitted only if the DECLARED rule minted it anyway.

        The model never adds an edge and never weighs one. Its relation proposals are checked
        against the edges the deterministic passes (``mint_located_edges``, the alias rule, the
        typed-time chain) produced, so an edge in this record is always a mechanical consequence
        of located bytes. Complexity: O(proposals) lookups plus one packed membership test.
        """
        if not self.proposed_relations:
            return
        rows = max(ingestion.store.row_count, 1)
        surface_column = {"entity": "surface", "quantity": "value_surface",
                          "event": "date_surface", "state_claim": "value"}
        index: dict[tuple[str, str, str], int] = {}
        for kind, column in surface_column.items():      # loop-ok: the four proposable row kinds
            table = ingestion.store.table(kind)
            if not len(table):
                continue
            owners, surfaces = table.decode("question_id"), table.decode(column)
            ordinals = table.global_ordinals.tolist()
            index.update(zip(zip([kind] * len(owners), owners, surfaces), ordinals))
        minted: dict[str, torch.Tensor] = {}
        for kind in propose.PROPOSABLE_RELATION_KINDS:   # loop-ok: the five proposable relation kinds
            table = ingestion.relations.kind(kind)
            minted[kind] = (table.src.to(torch.int64) * rows + table.dst.to(torch.int64)
                            if len(table) else torch.empty(0, dtype=torch.int64,
                                                           device=ingestion.device))
        endpoint_kinds = {"mentions": ("entity", "turn"), "about": ("event", "turn"),
                          "same_entity": ("entity", "entity"),
                          "supersedes": ("state_claim", "state_claim"),
                          "precedes": ("event", "event")}
        keys: list[int] = []
        kinds: list[str] = []
        for proposal in self.proposed_relations:         # loop-ok: the proposals of this run
            source_kind, target_kind = endpoint_kinds[proposal["kind"]]
            src = index.get((source_kind, proposal["question_id"], proposal["source_surface"]))
            dst = index.get((target_kind, proposal["question_id"], proposal["target_surface"]))
            if src is None or dst is None:
                self.report.refuse("relation_endpoint_not_admitted")
                continue
            keys.append(int(src) * rows + int(dst))
            kinds.append(proposal["kind"])
        if not keys:
            return
        probe = torch.tensor(keys, dtype=torch.int64, device=ingestion.device)
        for kind in sorted(set(kinds)):                  # loop-ok: the five proposable relation kinds
            mask = torch.tensor([k == kind for k in kinds], device=ingestion.device)  # loop-ok: one pass over this run's proposals
            present = torch.isin(probe[mask], minted[kind])
            admitted = int(present.sum().item())
            self.report.admit_relation(kind, admitted)
            if admitted < int(mask.sum().item()):
                self.report.refuse("relation_predicate_refused",
                                   int(mask.sum().item()) - admitted)

    def counters(self) -> dict[str, Any]:
        """The rung's whole receipt: the residue it was licensed by, what it cost, what it added."""
        calls = max(self.cost["calls"], 1)
        return {"rung_c": {
            "proposer": self.proposer.as_dict(),
            "residue_measured_before_the_rung": dict(self.census),
            "cost": {**self.cost,
                     "seconds_per_item": self.cost["seconds"] / calls,
                     "input_tokens_per_item": self.cost["input_tokens"] / calls,
                     "output_tokens_per_item": self.cost["output_tokens"] / calls},
            "admission": self.report.as_dict()}}


def _build_rung_b_relations(ingestion: Ingestion, since: int = 0) -> None:
    """mentions, about, same_entity, precedes and supersedes - all inside one haystack."""
    ingestion.mint_located_edges("mentions", "turn", extractor_id=EXTRACTOR_ID_B)
    ingestion.mint_located_edges("about", "turn", extractor_id=EXTRACTOR_ID_B)
    _same_entity(ingestion, since)
    _ordered_pairs(ingestion, "precedes", "event", ("question_id",), "event_date", since)
    _ordered_pairs(ingestion, "supersedes", "state_claim",
                   ("question_id", "subject", "attribute"), "claimed_at", since)


def _same_entity(ingestion: Ingestion, since: int = 0) -> None:
    """The declared alias rule, applied inside ONE haystack (B.29 item-locality)."""
    entities = ingestion.store.table("entity")
    if not len(entities):
        return
    surfaces, owners = entities.decode("surface"), entities.decode("question_id")
    witness, globals_ = entities.witness_span.tolist(), entities.global_ordinals.tolist()
    by_case: dict[str, dict[str, int]] = {}
    for local, (owner, surface) in enumerate(zip(owners, surfaces)):
        if globals_[local] >= since:
            by_case.setdefault(owner, {})[surface] = local
    src, dst, spans, contexts = [], [], [], []
    for index in by_case.values():
        for short, long in extract.alias_pairs(index):
            src.append(globals_[index[long]])
            dst.append(globals_[index[short]])
            spans.append((witness[index[long]], witness[index[short]]))
            contexts.append({"argument": short, "target_surfaces": (short,)})
    if src:
        ingestion.append_relations("same_entity", src, dst, spans, contexts=contexts,
                                   extractor_id=EXTRACTOR_ID_B,
                                   witness_options={"principals": ()})


def _ordered_pairs(ingestion: Ingestion, relation: str, kind: str,
                   equal_fields: tuple[str, ...], order_field: str, since: int = 0) -> None:
    """Edges between consecutive rows of one group, ordered by a declared typed time.

    ``precedes`` and ``supersedes`` are both this shape: group by declared fields, sort by the
    typed time, join each row to the one before it. Consecutive rather than all-pairs, because
    all-pairs is quadratic in a group and carries no information the chain does not: B.36's
    block sum recovers the transitive count from the chain, and a quadratic edge set would make
    the generator's rates a function of group size rather than of located witnesses.

    Complexity: O(N log N) on device for N rows of the kind.
    """
    table = ingestion.store.table(kind)
    if len(table) < 2:
        return
    columns = [table.column(name).to(torch.int64) for name in equal_fields]
    key = columns[0]
    for column in columns[1:]:
        key = key * (int(column.max()) + 1) + column
    time_key = table.column(order_field).to(torch.int64)
    order = torch.argsort(key * (int(time_key.max()) - int(time_key.min()) + 1)
                          + (time_key - int(time_key.min())), stable=True)
    later, earlier = order[1:], order[:-1]
    same = key.index_select(0, later) == key.index_select(0, earlier)
    strictly_after = time_key.index_select(0, later) > time_key.index_select(0, earlier)
    new = table.global_ordinals >= since
    keep = same & strictly_after & new.index_select(0, later) & new.index_select(0, earlier)
    later, earlier = later[keep], earlier[keep]
    if later.numel() == 0:
        return
    decoded = {name: table.decode(name) for name in equal_fields}
    times = table.decode(order_field)
    source_is_later = relation == "supersedes"
    src_local, dst_local = (later, earlier) if source_is_later else (earlier, later)
    contexts = [{"source_fields": {**{n: decoded[n][s] for n in equal_fields},
                                   "at": times[s].isoformat()},
                 "target_fields": {**{n: decoded[n][d] for n in equal_fields},
                                   "at": times[d].isoformat()}}
                for s, d in zip(src_local.tolist(), dst_local.tolist())]
    ingestion.append_relations(
        relation,
        table.global_ordinals.index_select(0, src_local).tolist(),
        table.global_ordinals.index_select(0, dst_local).tolist(),
        [(int(a), int(b)) for a, b in zip(
            table.witness_span.index_select(0, src_local).tolist(),
            table.witness_span.index_select(0, dst_local).tolist())],
        contexts=contexts, extractor_id=EXTRACTOR_ID_B,
        witness_options={"equal_fields": equal_fields,
                         "order_field": "at" if source_is_later else None,
                         "reverse_order_field": None if source_is_later else "at"})


def _build_relations_for_new_rows(ingestion: Ingestion, since: int) -> None:
    """Build only the relations of rows minted at or after global ordinal ``since`` (B.29).

    Both endpoints are restricted to the new range, not just the source. A diff item is
    self-contained - one haystack is one blob (B.33) - and a CHANGED item is a new blob whose
    rows repeat the old item's declared fields (B.31), so an unrestricted join would link the
    new turns to the superseded blob's rows and quietly merge two generations of the record.
    """
    _build_relations(ingestion, since=since)


def _build_relations(ingestion: Ingestion, since: int = 0) -> None:
    """The three rung-(a) relations, built by device joins over the shared integer keys."""
    store = ingestion.store
    turns, sessions, questions = (store.table("turn"), store.table("session"),
                                  store.table("question"))
    if not len(turns) or not len(sessions):
        return
    device = store.device
    turn_new = turns.global_ordinals >= since
    session_new = sessions.global_ordinals >= since

    # The join key carries the BLOB the row was read from, not only its declared fields. B.31
    # keeps a changed item's old rows as valid objects beside the new ones, so (question_id,
    # session_index) is NOT unique across generations; joining on it alone would wire a new
    # turn into the superseded haystack's session. The blob ordinal is read off each row's
    # witness address, so this costs one gather and no new column.
    blob_of_span = ingestion.spans.columns[:, 0]

    def blob_of(table_: Any) -> torch.Tensor:
        return blob_of_span.index_select(0, table_.witness_span)
    # Stride: one more than the largest session index actually admitted. Derived from the data,
    # not chosen - a fixed stride would be a literal and would break on a longer haystack.
    stride = int(sessions.column("session_index").max()) + 1
    qid_stride = max(int(sessions.column("question_id").max()) + 1, 1)

    session_key = ((blob_of(sessions) * qid_stride +
                    sessions.column("question_id").to(torch.int64)) * stride +
                   sessions.column("session_index").to(torch.int64))
    turn_key = ((blob_of(turns) * qid_stride +
                 turns.column("question_id").to(torch.int64)) * stride +
                turns.column("session_index").to(torch.int64))
    order = torch.argsort(session_key, stable=True)
    sorted_session_key = session_key.index_select(0, order)
    slot = torch.searchsorted(sorted_session_key, turn_key)
    valid = (slot < session_key.numel())
    slot = slot.clamp(max=max(session_key.numel() - 1, 0))
    matched = order.index_select(0, slot)
    valid &= session_key.index_select(0, matched) == turn_key
    valid &= turn_new & session_new.index_select(0, matched)

    turn_qid = turns.decode("question_id")
    turn_sess = turns.column("session_index").tolist()
    turn_ix = turns.column("turn_index").tolist()
    session_qid = sessions.decode("question_id")
    session_sess = sessions.column("session_index").tolist()

    src_local = torch.nonzero(valid, as_tuple=False).flatten()
    dst_local = matched.index_select(0, src_local)
    contexts = [{"source_fields": {"question_id": turn_qid[s],
                                   "session_index": turn_sess[s]},
                 "target_fields": {"question_id": session_qid[d],
                                   "session_index": session_sess[d]}}
                for s, d in zip(src_local.tolist(), dst_local.tolist())]
    ingestion.append_relations(
        "in_session",
        turns.global_ordinals.index_select(0, src_local).tolist(),
        sessions.global_ordinals.index_select(0, dst_local).tolist(),
        [(int(a), int(b)) for a, b in zip(
            turns.witness_span.index_select(0, src_local).tolist(),
            sessions.witness_span.index_select(0, dst_local).tolist())],
        contexts=contexts, extractor_id=EXTRACTOR_ID,
        witness_options={"equal_fields": ("question_id", "session_index")})

    # follows: consecutive turn_index within a (question, session) group. Sort once, pair the
    # adjacent entries whose group matches and whose index differs by one. No loop over turns.
    full_stride = int(turns.column("turn_index").max()) + 1
    full_key = turn_key * full_stride + turns.column("turn_index").to(torch.int64)
    order = torch.argsort(full_key, stable=True)
    left, right = order[1:], order[:-1]
    same_group = turn_key.index_select(0, left) == turn_key.index_select(0, right)
    step = turns.column("turn_index").to(torch.int64)
    consecutive = step.index_select(0, left) == step.index_select(0, right) + 1
    keep = same_group & consecutive & turn_new.index_select(0, left) \
        & turn_new.index_select(0, right)
    left, right = left[keep], right[keep]
    contexts = [{"source_fields": {"question_id": turn_qid[s], "session_index": turn_sess[s],
                                   "turn_index": turn_ix[s]},
                 "target_fields": {"question_id": turn_qid[d], "session_index": turn_sess[d],
                                   "turn_index": turn_ix[d]}}
                for s, d in zip(left.tolist(), right.tolist())]
    ingestion.append_relations(
        "follows",
        turns.global_ordinals.index_select(0, left).tolist(),
        turns.global_ordinals.index_select(0, right).tolist(),
        [(int(a), int(b)) for a, b in zip(
            turns.witness_span.index_select(0, left).tolist(),
            turns.witness_span.index_select(0, right).tolist())],
        contexts=contexts, extractor_id=EXTRACTOR_ID,
        witness_options={"equal_fields": ("question_id", "session_index"),
                         "successor_field": "turn_index"})

    if not len(questions):
        return
    question_qid = blob_of(questions) * qid_stride + \
        questions.column("question_id").to(torch.int64)
    order = torch.argsort(question_qid, stable=True)
    slot = torch.searchsorted(question_qid.index_select(0, order),
                              blob_of(sessions) * qid_stride +
                              sessions.column("question_id").to(torch.int64))
    slot = slot.clamp(max=max(question_qid.numel() - 1, 0))
    matched = order.index_select(0, slot)
    question_new = questions.global_ordinals >= since
    keep_session = session_new & question_new.index_select(0, matched)
    source_rows = torch.nonzero(keep_session, as_tuple=False).flatten()
    if source_rows.numel() == 0:
        return
    matched = matched.index_select(0, source_rows)
    question_qid_host = questions.decode("question_id")
    contexts = [{"source_fields": {"question_id": session_qid[s]},
                 "target_fields": {"question_id": question_qid_host[d]}}
                for s, d in zip(source_rows.tolist(), matched.tolist())]
    ingestion.append_relations(
        "in_jurisdiction",
        sessions.global_ordinals.index_select(0, source_rows).tolist(),
        questions.global_ordinals.index_select(0, matched).tolist(),
        [(int(a), int(b)) for a, b in zip(
            sessions.witness_span.index_select(0, source_rows).tolist(),
            questions.witness_span.index_select(0, matched).tolist())],
        contexts=contexts, extractor_id=EXTRACTOR_ID,
        witness_options={"equal_fields": ("question_id",)})
    _ = device
