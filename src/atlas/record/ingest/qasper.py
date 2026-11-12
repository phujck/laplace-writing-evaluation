"""qasper.py - B.34: scientific papers, through the same declaration machinery as B.33.

One paper is one blob. Rung (a) is a pure parse of QASPER's own explicit tree - sections,
paragraphs, the abstract, the table and figure captions - and rung (b) adds the citation,
entity and quantity rows that give a question something typed to anchor to.

WHY THIS IS NOT "SHARD THE PAPER INTO PASSAGES". The named failure is a fixed-size chunker with
the section headers relabelled as a hierarchy. Nothing here cuts a paragraph: the container
states where every paragraph begins and ends and the row records that byte range. What the rows
carry beyond the text is the part that matters - a table is a ROW with a label a mask can test,
a citation is a ROW with a located marker, an entity is a ROW an anchor resolves to - and the
relations between them are minted from located co-occurrence inside a witness span, never from a
similarity. A query can therefore say "paragraphs of the section that Table 1 belongs to, which
cite BIBREF7" and get an answer by walking three typed relations, which is exactly the class of
question a cosine ranking cannot express.

THE ITEM BOUNDARY IS THE PAPER, and every counted relation kind declared below is item-local in
B.29's sense: both endpoints of every edge lie inside the same paper, so the touched count of an
inserted paper is its own rows and nothing else. ``same_entity`` is minted only between two
entity rows of the SAME paper for exactly this reason; cross-paper identity is the anchor
index's job (C.3), not an edge's, and an edge whose witness tuple straddled two papers would
break B.29's byte-computable bound - measured in the packet report rather than asserted.

GOLD IS NOT IN THE RECORD. ``qas[*].answers`` - evidence, answer types, annotation ids - never
enters a row, a relation or an anchor. Only ``question_id`` and the question text are ingested,
the same boundary ``qasper_data.py`` keeps between ``sources.json`` and ``gold.json``. The gold
side lives in ``atlas.bench.gold_spans`` and is joined to these rows by unit id in ``gold_rows``.

Complexity: O(bytes) host parse, extraction and witness check; O(R log R) device work for the
relations, where R is the number of rows. Memory: one paper's bytes at a time.
"""

from __future__ import annotations

import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

import torch

from .. import extract, propose
from ..declaration import (RUNG_A, RUNG_B, RUNG_C, DatasetDeclaration, FieldAliasTable, FieldSpec,
                           ContentCarrier, RelationKindSpec, RowKindSpec,
                           SurfaceSetSchema)
from ..content import declared_axes
from ..ingestion import Ingestion
from ..json_spans import SEG_VERSION, SEGMENTER_ID, iter_object_members, scan_value

__all__ = ["ARCHIVES", "SPLIT_MEMBER", "declaration", "ingest", "iter_papers", "unit_id_of_row",
           "EXTRACTOR_ID_A", "EXTRACTOR_ID_B", "BLOB_MEDIA_TYPE", "FLOAT_KINDS",
           "ABSTRACT_SECTION_INDEX", "PaperItem", "available"]

EXTENSION = Path(__file__).resolve().parents[4] / "synthetics papers" / "corpus-as-a-state" / \
    "reconstruction" / "extension"
ARCHIVES = {
    "train": EXTENSION / "cache" / "qasper-train-dev-v0.3.tgz",
    "dev": EXTENSION / "cache" / "qasper-train-dev-v0.3.tgz",
    "test": EXTENSION / "cache" / "qasper-test-and-evaluator-v0.3.tgz",
}
SPLIT_MEMBER = {split: f"qasper-{split}-v0.3.json" for split in ARCHIVES}

BLOB_MEDIA_TYPE = "application/json"
EXTRACTOR_ID_A = "qasper-rung-a@v1"
EXTRACTOR_ID_B = "qasper-rung-b@v1"

# The abstract is a paragraph of the paper that sits outside ``full_text``'s section list. It is
# given its own section at index -1 rather than shifting every ``full_text`` index by one,
# because ``s{i}`` is the id space the established gold map and ``qasper_data.py`` already use
# and a shift would silently re-address every gold evidence paragraph.
ABSTRACT_SECTION_INDEX = -1

FLOAT_KINDS = ("table", "figure")
# The caption's own declared label grammar, widened from "Table 1"/"Figure 4" to the forms the
# corpus actually uses after they were MEASURED: "TABLE I", "Fig. 2", "Tab. 3". With this
# grammar 1,928 of the 1,929 captions in the dev split carry a label (the one refusal is
# "Figure A.4", an appendix number the grammar does not admit and does not guess at).
import regex as _regex                                                    # noqa: E402
_LABEL = _regex.compile(
    r"^\s*(?P<kind>Table|TABLE|Tab|TAB|Figure|FIGURE|Fig|FIG)\.?[  ]+"
    r"(?P<number>\p{Nd}+|[IVXLC]+)\b", _regex.UNICODE)
_LABEL_KIND = {"table": "table", "tab": "table", "figure": "figure", "fig": "figure"}


def available(split: str = "dev") -> bool:
    """Is the split's archive on disk? Used by tests to skip by name rather than fail."""
    return ARCHIVES[split].is_file()


# --------------------------------------------------------------------------- declaration
# THE CONTENT-BEARING ROW KINDS OF THIS DATASET. The reconciliation's leaf here is "one PARAGRAPH
# of one section of one paper", and the two float kinds carry the caption text the gold map also
# addresses ("FLOAT SELECTED: " captions, bench/gold_spans.py), so they are content-bearing by
# the same test. Every one of them is a JSON string node in the paper's own blob.
CONTENT_CARRIERS = (ContentCarrier("paragraph", "text_span", "json_string"),
                    ContentCarrier("table", "caption_span", "json_string"),
                    ContentCarrier("figure", "caption_span", "json_string"))


def declaration(rungs: str = "ab", *, content: Mapping[str, Any] | None = None) -> DatasetDeclaration:
    """B.5's declaration for QASPER. ``rungs='a'`` declares the parse-only store.

    A rung-(b) kind is declared ONLY when this ingestion will fill it, because B.35 counts a
    declared-but-never-instantiated kind as a coverage hole. The two declarations therefore have
    two different declaration hashes, which is what lets the before/after arms of the measurement
    be told apart by their receipts rather than by a label.
    """
    paper = RowKindSpec(
        "paper",
        (FieldSpec("paper_id", "dict_utf8", RUNG_A),
         FieldSpec("title", "dict_utf8", RUNG_A),
         FieldSpec("title_span", "span_ref", RUNG_A)),
        witness_predicate_id="json_member_equals@v1", anchor_fields=("paper_id",))
    section = RowKindSpec(
        "section",
        (FieldSpec("paper_id", "dict_utf8", RUNG_A),
         FieldSpec("section_index", "int64", RUNG_A),
         FieldSpec("section_name", "dict_utf8", RUNG_A),
         FieldSpec("header_span", "span_ref", RUNG_A,
                   doc="byte range of the section_name string; null for the abstract")),
        witness_predicate_id="surfaces_located@v1", anchor_fields=("section_name",))
    paragraph = RowKindSpec(
        "paragraph",
        (FieldSpec("paper_id", "dict_utf8", RUNG_A),
         FieldSpec("section_index", "int64", RUNG_A),
         FieldSpec("paragraph_index", "int64", RUNG_A),
         FieldSpec("text_span", "span_ref", RUNG_A,
                   doc="byte range of the paragraph string; the row stores no copy (B.1)")),
        witness_predicate_id="span_in_witness@v1")
    question = RowKindSpec(
        "question",
        (FieldSpec("question_id", "dict_utf8", RUNG_A),
         FieldSpec("paper_id", "dict_utf8", RUNG_A),
         FieldSpec("text_span", "span_ref", RUNG_A)),
        witness_predicate_id="json_member_equals@v1", anchor_fields=("question_id",))
    table = RowKindSpec(
        "table",
        (FieldSpec("paper_id", "dict_utf8", RUNG_A),
         FieldSpec("float_index", "int64", RUNG_A, doc="position in figures_and_tables"),
         FieldSpec("label", "dict_utf8", RUNG_A, doc="the caption's own located label surface"),
         FieldSpec("float_number", "dict_utf8", RUNG_A, doc="the label's number, as written"),
         FieldSpec("caption_span", "span_ref", RUNG_A)),
        witness_predicate_id="surfaces_located@v1", anchor_fields=("label",))
    figure = RowKindSpec(
        "figure", table.fields, witness_predicate_id="surfaces_located@v1",
        anchor_fields=("label",))
    row_kinds: tuple[RowKindSpec, ...] = (paper, section, paragraph, question, table, figure)

    relations: tuple[RelationKindSpec, ...] = (
        RelationKindSpec("in_section", ("paragraph",), ("section",), "typed_field_predicate@v1",
                         RUNG_A, doc="containment, from the container's own section tree"),
        RelationKindSpec("follows", ("paragraph",), ("paragraph",), "typed_field_predicate@v1",
                         RUNG_A, doc="the container's paragraph order inside one section"),
        RelationKindSpec("in_jurisdiction", ("section", "question", "table", "figure"),
                         ("paper",), "typed_field_predicate@v1", RUNG_A, counted=False,
                         doc="which paper a row belongs to"),
        RelationKindSpec("supersedes_blob", ("paper",), ("paper",), "typed_field_predicate@v1",
                         RUNG_A, counted=False,
                         doc="B.31: a changed paper is a NEW blob; the old one is marked "
                             "superseded by this edge, never edited or removed"),
    )
    if "b" in rungs:
        citation = RowKindSpec(
            "citation",
            (FieldSpec("paper_id", "dict_utf8", RUNG_A),
             FieldSpec("marker", "dict_utf8", RUNG_B),
             FieldSpec("reference_kind", "enum", RUNG_B, extract.REFERENCE_KINDS)),
            witness_predicate_id="surfaces_located@v1", anchor_fields=("marker",))
        entity = RowKindSpec(
            "entity",
            (FieldSpec("paper_id", "dict_utf8", RUNG_A),
             FieldSpec("surface", "dict_utf8", RUNG_B)),
            witness_predicate_id="surfaces_located@v1", anchor_fields=("surface",))
        quantity = RowKindSpec(
            "quantity",
            (FieldSpec("paper_id", "dict_utf8", RUNG_A),
             FieldSpec("value_surface", "dict_utf8", RUNG_B),
             FieldSpec("value_scaled", "int64", RUNG_B,
                       doc="the decimal's digits; value = value_scaled / 10**value_scale"),
             FieldSpec("value_scale", "int64", RUNG_B),
             FieldSpec("unit_surface", "dict_utf8", RUNG_B)),
            witness_predicate_id="surfaces_located@v1")
        row_kinds = row_kinds + (citation, entity, quantity)
        relations = relations + (
            # table_of / figure_of are rung (b), not rung (a): the container states a float's
            # caption but NEVER which section it belongs to, so the link exists only where the
            # float's own label is LOCATED in a paragraph - an extraction, not a parse.
            RelationKindSpec("table_of", ("table",), ("section",), "argument_link@v1", RUNG_B,
                             doc="the table's own label is located in a paragraph of that "
                                 "section"),
            RelationKindSpec("figure_of", ("figure",), ("section",), "argument_link@v1", RUNG_B,
                             doc="the figure's own label is located in a paragraph of that "
                                 "section"),
            RelationKindSpec("cites", ("paragraph",), ("citation",), "spans_nest@v1", RUNG_B,
                             doc="the citation's marker is located inside this paragraph"),
            RelationKindSpec("mentions", ("entity", "quantity"), ("paragraph",),
                             "spans_nest@v1", RUNG_B,
                             doc="the carrier's surface is located inside this paragraph"),
            RelationKindSpec("same_entity", ("entity",), ("entity",), "argument_link@v1",
                             RUNG_B, symmetric=True,
                             doc="the shorter surface is a token subsequence of the longer, "
                                 "both entities of the SAME paper (B.29 item-locality)"),
        )
    anchor_columns: dict[str, tuple[str, ...]] = {
        "paper": ("paper_id",), "question": ("question_id",), "section": ("section_name",),
        "table": ("label",), "figure": ("label",)}
    if "b" in rungs:
        anchor_columns.update({"entity": ("surface",), "citation": ("marker",)})
    # The ablation switch; ``content=None`` is the OFF position (see longmem.declaration).
    _recipe, _axes = declared_axes(content, CONTENT_CARRIERS, SEG_VERSION)
    return DatasetDeclaration(
        dataset_id=f"qasper-v0.3-rung-{rungs}",
        row_kinds=row_kinds, relation_kinds=relations,
        alias_table=FieldAliasTable("qasper-aliases@v1", ()),
        surface_set=SurfaceSetSchema(
            f"qasper-surfaces@{rungs}",
            anchor_columns=anchor_columns,
            must_appear_columns={"section": ("section_name",), "table": ("label",),
                                 "figure": ("label",), "entity": ("surface",),
                                 "citation": ("marker",),
                                 "quantity": ("value_surface",)},
            principal_surfaces={}, principals=()),
        segmenter_id=SEGMENTER_ID, seg_version=SEG_VERSION,
        segmentation=_recipe, content_axes=_axes,
        blob_glob=str(ARCHIVES["dev"]))


# --------------------------------------------------------------------------- streaming
@dataclass(frozen=True, slots=True)
class PaperItem:
    """One paper: its id, its raw bytes and the byte offset those bytes start at in the split."""

    paper_id: str
    raw: bytes
    base: int


def iter_papers(split: str = "dev", *, limit: int | None = None,
                paper_ids: Sequence[str] | None = None) -> Iterator[PaperItem]:
    """Stream papers out of the official archive without unpacking it. O(split bytes)."""
    wanted = None if paper_ids is None else set(paper_ids)
    emitted = 0
    with tarfile.open(ARCHIVES[split]) as archive:
        stream = archive.extractfile(SPLIT_MEMBER[split])
        assert stream is not None
        for paper_id, start, end, raw in iter_object_members(stream):
            if wanted is not None and paper_id not in wanted:
                continue
            yield PaperItem(paper_id, raw, start)
            emitted += 1
            if limit is not None and emitted >= limit:
                return


# --------------------------------------------------------------------------- ingestion
def ingest(split: str = "dev", *, papers: int | None = None,
           paper_ids: Sequence[str] | None = None, rungs: str = "ab",
           device: torch.device | str | None = None, segments: Any = None,
           proposer: propose.ProposerIdentity | None = None,
           proposal_cache: Path | str | None = None,
           content: Mapping[str, Any] | None = None) -> Ingestion:
    """Ingest ``papers`` QASPER papers at the requested rungs. One paper is one blob (B.34).

    ``rungs='ab'`` is the parse-plus-extractors store; ``rungs='abc'`` adds B.33's third rung -
    the light-tier proposer of ``record.propose``, asked ONCE per paper about that paper's
    MEASURED residue (the paragraphs the three rung-(b) grammars minted nothing from) under
    QASPER's own view of the closed grammar (``propose.QASPER_GRAMMAR``: entity and quantity
    rows, same_entity relations, a (section, paragraph) container address), and admitted only
    where this paper's bytes locate what was proposed.

    Rung (c) FAILS CLOSED, exactly as in ``longmem.ingest``: ``rungs`` naming 'c' without a
    reachable proposer raises rather than quietly producing a rung-(ab) store under a rung-(abc)
    declaration.

    ``segments`` is a ``record.segments.SegmentStore``: a paper whose bytes are already in it is
    adopted from its segment and ``_ingest_paper`` - the whole parse and extraction of that
    paper - is never called. See ``longmem.ingest`` for the ordering rule.
    """
    declared = declaration(rungs, content=content)
    ingestion = Ingestion(declared, device)
    store = ingestion.store
    store.share_dictionary("paper_id", [k.kind for k in declared.row_kinds])
    ingestion.counters["rungs"] = 1 if "b" in rungs else 0
    if segments is not None:
        ingestion.cache.attach(segments.cache_index())
    if "c" in rungs and proposer is None:
        raise propose.ProposerUnreachable(
            "rungs names 'c' but no proposer identity was given", {"rungs": rungs})
    # THE PROPOSER'S IDENTITY IS IN B.28's EXTRACTOR ID, not beside it (longmem.ingest:299-300 does
    # the same for its own id): the per-item cache key is computed from this string, so a paper
    # proposed on by THIS proposer is adopted from its segment on every later run and no second
    # ingest calls a model, while a changed prompt, schema, grammar view, model or tier is a
    # different id and re-proposes.
    extractor_for_the_key = (EXTRACTOR_ID_A if proposer is None or "c" not in rungs
                             else f"{EXTRACTOR_ID_A}+{proposer.extractor_id('qasper')}")
    cache_dir = (Path(proposal_cache) if proposal_cache is not None
                 else (Path(segments.root) / "proposals" if segments is not None else None))
    rung_c = _RungC(proposer, cache_dir) if "c" in rungs else None

    with ingestion.measure("parse_and_rows"):
        declaration_hash = declared.declaration_hash
        from ..diff import item_bytes_cache_key
        for item in iter_papers(split, limit=papers, paper_ids=paper_ids):
            # B.28 as amended: a batch ingest is a batch of item inserts and fills the per-item
            # cache the same way a single append does (see longmem.ingest for the reason).
            key = item_bytes_cache_key(item.raw, extractor_for_the_key, declaration_hash)
            found = ingestion.cache.get(key)
            if found is not None and "segment_key" in found:
                ingestion.blobs.put_bytes(item.raw, BLOB_MEDIA_TYPE)
                ingestion.defer_segment(key, found["segment_key"])
                continue
            handle = ingestion.blobs.put_bytes(item.raw, BLOB_MEDIA_TYPE)
            before = store.row_count
            with ingestion.item(key, item_bytes=item.raw, blob_handles=(handle,),
                                extracts="b" in rungs):
                _ingest_paper(ingestion, handle, item, rungs, rung_c)
            ingestion.cache.put(key, {"rows": store.row_count - before})
    with ingestion.measure("relations"):
        _build_relations(ingestion, rungs)
    if rung_c is not None:
        rung_c.verify_proposed_relations(ingestion)
        ingestion.counters.update(rung_c.counters())
    ingestion.pending_edges.clear()
    ingestion.pending_labels.clear()
    if segments is not None:
        from ..segments import adopt_deferred, store_ingestion
        adopt_deferred(ingestion, segments)
        # Read AND written by the same call; see ``longmem.ingest`` for the reason.
        ingestion.persistence = store_ingestion(
            segments, ingestion, extractor_roster_hash=extract.extractor_roster_hash())
    with ingestion.measure("anchors"):
        ingestion.build_anchors(rung=RUNG_B if "b" in rungs else RUNG_A)
    for kind in declared.row_kinds:
        ingestion.counters[f"rows_{kind.kind}"] = len(store.table(kind.kind))
    return ingestion


def _ingest_paper(ingestion: Ingestion, handle: str, item: PaperItem, rungs: str,
                  rung_c: "_RungC | None" = None) -> None:
    """Rows of one paper. The paper's bytes are scanned once and never held after this call."""
    # base=0: the BLOB is the paper's own bytes, so every span is an offset into the paper, not
    # into the split file it was streamed out of. ``item.base`` is kept for provenance only.
    node, _ = scan_value(item.raw, 0, 0)
    paper_id = item.paper_id
    store = ingestion.store

    title = node.member("title")
    paper_span = int(ingestion.add_spans(handle, [(node.start, node.end)])[0])
    title_span = int(ingestion.add_spans(handle, [(title.start, title.end)])[0])
    store.append_rows(
        "paper", [{"paper_id": paper_id, "title": title.text, "title_span": title_span}],
        [paper_span], rung=RUNG_A, extractor_id=EXTRACTOR_ID_A,
        witness_options={"members": {"title": ("title",)},
                         "spans_at": {"title_span": ("title",)}})

    # ---- sections and paragraphs (rung a, a pure parse of the container's own tree)
    section_records: list[dict[str, Any]] = []
    section_witness: list[tuple[int, int]] = []
    paragraph_nodes: list[tuple[int, int, Any]] = []      # (section_index, paragraph_index, node)

    abstract = node.get("abstract")
    if abstract is not None and str(abstract.value or "").strip():
        key_node = node.members["abstract"][0]            # type: ignore[index]
        section_records.append({"paper_id": paper_id, "section_index": ABSTRACT_SECTION_INDEX,
                                "section_name": "Abstract", "header_span": None})
        section_witness.append((key_node.start, abstract.end))
        paragraph_nodes.append((ABSTRACT_SECTION_INDEX, 0, abstract))

    header_ranges: dict[int, tuple[int, int]] = {}
    for section_index, section in enumerate(node.member("full_text").items or ()):
        name_node = section.get("section_name")
        name = str(name_node.value) if name_node is not None and name_node.kind == "string" else ""
        if name.strip():
            header_ranges[section_index] = (name_node.start, name_node.end)
        section_records.append({"paper_id": paper_id, "section_index": section_index,
                                "section_name": name or f"section {section_index}",
                                "header_span": None})
        section_witness.append((section.start, section.end))
        for paragraph_index, paragraph in enumerate(section.member("paragraphs").items or ()):
            if str(paragraph.value or "").strip():
                paragraph_nodes.append((section_index, paragraph_index, paragraph))

    header_spans = ingestion.add_spans(
        handle, [header_ranges[i] for i in sorted(header_ranges)]).tolist()
    header_of = dict(zip(sorted(header_ranges), header_spans))
    for record in section_records:
        record["header_span"] = header_of.get(int(record["section_index"]))
    section_span_ords = ingestion.add_spans(handle, section_witness)
    store.append_rows("section", section_records, section_span_ords.tolist(), rung=RUNG_A,
                      extractor_id=EXTRACTOR_ID_A,
                      witness_options={"must_appear": ("section_name",),
                                       "decode_escapes": True})

    paragraph_spans = ingestion.add_spans(
        handle, [(n.start, n.end) for _, _, n in paragraph_nodes]).tolist()
    store.append_rows(
        "paragraph",
        [{"paper_id": paper_id, "section_index": si, "paragraph_index": pi,
          "text_span": span} for (si, pi, _), span in zip(paragraph_nodes, paragraph_spans)],
        paragraph_spans, rung=RUNG_A, extractor_id=EXTRACTOR_ID_A,
        witness_options={"spans": ("text_span",), "decodes_as": "json_string"})

    # ---- tables and figures (rung a: the caption is the container's own, the label is its
    #      first line's declared grammar - not a model's reading of the picture)
    floats: dict[str, list[dict[str, Any]]] = {"table": [], "figure": []}
    float_witness: dict[str, list[int]] = {"table": [], "figure": []}
    float_labels: list[tuple[str, str, int]] = []         # (kind, label, float_index)
    entries = node.get("figures_and_tables")
    for float_index, entry in enumerate((entries.items if entries is not None else ()) or ()):
        caption = entry.get("caption")
        if caption is None or caption.kind != "string":
            continue
        match = _LABEL.match(caption.text)
        if match is None:
            ingestion.coverage["not_admitted"].append(
                {"paper_id": paper_id, "float_index": float_index,
                 "reason": "caption carries no declared Table/Figure label"})
            continue
        kind = _LABEL_KIND[match.group("kind").lower()]
        # The label is the caption's OWN surface, not a canonical rewrite of it: the witness
        # check re-reads the caption bytes, and "Figure 1" is not located in "Fig. 1: ...".
        label = match.group(0).strip()
        span = int(ingestion.add_spans(handle, [(caption.start, caption.end)])[0])
        floats[kind].append({"paper_id": paper_id, "float_index": float_index,
                             "label": label, "float_number": match.group("number"),
                             "caption_span": span})
        float_witness[kind].append(span)
        float_labels.append((kind, label, float_index))
    for kind in FLOAT_KINDS:
        if floats[kind]:
            store.append_rows(kind, floats[kind], float_witness[kind], rung=RUNG_A,
                              extractor_id=EXTRACTOR_ID_A,
                              witness_options={"must_appear": ("label",), "decode_escapes": True})

    # ---- questions (rung a). Only the id and the text; the answers never leave the source.
    question_records, question_witness = [], []
    for qa in node.member("qas").items or ():
        text = qa.member("question")
        question_records.append({
            "question_id": qa.member("question_id").text, "paper_id": paper_id,
            "text_span": int(ingestion.add_spans(handle, [(text.start, text.end)])[0])})
        question_witness.append((qa.start, qa.end))
    if question_records:
        store.append_rows(
            "question", question_records,
            ingestion.add_spans(handle, question_witness).tolist(), rung=RUNG_A,
            extractor_id=EXTRACTOR_ID_A,
            witness_options={"members": {"question_id": ("question_id",)},
                             "spans_at": {"text_span": ("question",)}})

    if "b" not in rungs:
        ingestion.counters["paragraph_nodes"] = ingestion.counters.get("paragraph_nodes", 0) + \
            len(paragraph_nodes)
        return

    # ---- rung (b): citations, entities, quantities, all located inside this paper's bytes
    produced, paragraphs, locators, minted = _extract_paper(
        ingestion, handle, paper_id, paragraph_nodes, paragraph_spans, float_labels)
    if rung_c is not None:
        rung_c.propose_for_item(ingestion, handle, paper_id, produced, paragraphs, locators,
                                minted)


def _extract_paper(ingestion: Ingestion, handle: str, paper_id: str,
                   paragraph_nodes: list[tuple[int, int, Any]], paragraph_spans: list[int],
                   float_labels: list[tuple[str, str, int]]
                   ) -> tuple[frozenset[tuple[int, int]], list[propose.ResidueTurn],
                              dict[tuple[int, int], Any], frozenset[tuple[str, str]]]:
    """The per-item rung-(b) pass. Pure in this paper's bytes; no store lookup, no corpus stat.

    Returns the four things rung (c) needs and nothing it could infer (the same four
    ``longmem._extract_case`` returns): the set of ``(section_index, paragraph_index)`` this pass
    minted at least one ROW from - the complement is B.33's MEASURED residue - the paragraphs
    themselves, the JSON locator of each, so a proposed surface is addressed through the same
    escape-aware map a grammar's is, and what this pass already minted, so rung (c) adds rather
    than duplicates. A located float LABEL does not count as produced: it mints a relation, not a
    row, so a paragraph whose only rung-(b) output is a "Table 2" occurrence still carries no
    typed row of its own and is residue by the content limit.
    """
    store = ingestion.store
    marker_rows: dict[tuple[str, str], list[tuple[int, int]]] = {}
    entity_rows: dict[str, list[tuple[int, int]]] = {}
    quantity_records: list[dict[str, Any]] = []
    quantity_ranges: list[tuple[int, int]] = []
    produced: set[tuple[int, int]] = set()
    paragraphs: list[propose.ResidueTurn] = []
    locators: dict[tuple[int, int], Any] = {}

    for (section_index, paragraph_index, node), _span in zip(paragraph_nodes, paragraph_spans):
        raw = ingestion.blobs.read(handle, node.start, node.end)
        try:
            locator = extract.locator_for_json_string(raw, node.start)
        except ValueError as exc:                      # addressing refused: item stays unindexed
            ingestion.coverage["not_admitted"].append(
                {"paper_id": paper_id, "section_index": section_index, "reason": str(exc)})
            continue
        text = locator.text
        where = (section_index, paragraph_index)
        paragraphs.append(propose.ResidueTurn(section_index, paragraph_index, text,
                                              node.start, node.end))
        locators[where] = locator
        markers = extract.reference_markers(text)
        for located, kind in markers:
            produced.add(where)
            marker_rows.setdefault((located.surface, kind), []).append(
                locator.span(located.start, located.end))
        for located in extract.proper_nouns(text, [(l.start, l.end) for l, _ in markers]):
            produced.add(where)
            entity_rows.setdefault(located.surface, []).append(
                locator.span(located.start, located.end))
        for quantity in extract.quantities(text):
            produced.add(where)
            quantity_records.append({
                "paper_id": paper_id, "value_surface": quantity.located.surface.strip(),
                "value_scaled": quantity.value_scaled, "value_scale": quantity.value_scale,
                "unit_surface": quantity.unit_surface})
            quantity_ranges.append(locator.span(quantity.located.start, quantity.located.end))
        for float_kind, label, _float_index in float_labels:
            index = text.find(label)
            while index >= 0:
                ingestion.pending_labels.append(
                    (paper_id, float_kind, label, section_index, paragraph_index, handle,
                     locator.span(index, index + len(label))))
                index = text.find(label, index + len(label))

    # citation rows: one per (marker, kind) of this paper; every occurrence is an edge instance.
    citation_records, citation_witness, citation_occurrences = [], [], []
    for (marker, kind), occurrences in sorted(marker_rows.items()):
        citation_records.append({"paper_id": paper_id, "marker": marker,
                                 "reference_kind": kind})
        citation_witness.append(int(ingestion.add_spans(handle, [occurrences[0]])[0]))
        citation_occurrences.append(occurrences)
    if citation_records:
        admission = store.append_rows(
            "citation", citation_records, citation_witness, rung=RUNG_B,
            extractor_id=EXTRACTOR_ID_B,
            witness_options={"must_appear": ("marker",), "decode_escapes": True})
        _pending(ingestion, "cites", admission, citation_occurrences, handle)

    entity_records, entity_witness, entity_occurrences = [], [], []
    for surface, occurrences in sorted(entity_rows.items()):
        entity_records.append({"paper_id": paper_id, "surface": surface})
        entity_witness.append(int(ingestion.add_spans(handle, [occurrences[0]])[0]))
        entity_occurrences.append(occurrences)
    if entity_records:
        admission = store.append_rows(
            "entity", entity_records, entity_witness, rung=RUNG_B,
            extractor_id=EXTRACTOR_ID_B,
            witness_options={"must_appear": ("surface",), "decode_escapes": True})
        _pending(ingestion, "mentions", admission, entity_occurrences, handle)

    if quantity_records:
        quantity_spans = ingestion.add_spans(handle, quantity_ranges).tolist()
        admission = store.append_rows(
            "quantity", quantity_records, quantity_spans, rung=RUNG_B,
            extractor_id=EXTRACTOR_ID_B,
            witness_options={"must_appear": ("value_surface",), "decode_escapes": True})
        _pending(ingestion, "mentions", admission, [[r] for r in quantity_ranges], handle)

    # WHAT RUNG (b) ALREADY HOLDS FOR THIS PAPER, so rung (c) adds rather than duplicates. Built
    # from the records already in hand, so it costs one pass over this paper's own rows.
    minted: set[tuple[str, str]] = {("entity", surface) for surface in entity_rows}
    minted |= {("quantity", record["value_surface"]) for record in quantity_records}
    return frozenset(produced), paragraphs, locators, frozenset(minted)


def _pending(ingestion: Ingestion, relation: str, admission: Any,
             occurrences: list[list[tuple[int, int]]], handle: str) -> None:
    """Record the located occurrences of ADMITTED rows so the relation pass can mint edges.

    ``admission.positions`` is the index of each admitted row among the offered candidates, so a
    refused proposal (B.4) drops its occurrences with it rather than sliding every later row's
    edges onto the wrong carrier.
    """
    bucket = ingestion.pending_edges.setdefault(relation, [])
    for row_ordinal, position in zip(admission.global_ordinals.tolist(), admission.positions):
        bucket.append((handle, int(row_ordinal), occurrences[position]))


# --------------------------------------------------------------------------- rung (c)
class _RungC:
    """B.33's third rung, in place inside this ingester: propose on the residue, admit by bytes.

    The mirror of ``longmem._RungC``, over QASPER's own objects: the item is a PAPER, the
    container is a PARAGRAPH, and the view of the closed grammar is ``propose.QASPER_GRAMMAR`` -
    entity and quantity rows and same_entity relations, which is exactly what this dataset's
    declaration carries. Everything that is not dataset-specific (the residue selector, the
    prompt, the content-addressed request, the strict response check, the mechanical location of
    a surface and the refusal vocabulary) is the shared organ in ``record.propose``; what lives
    here is only the shape of a QASPER row and the relation index this dataset's ids need.

    One instance per ingestion. It holds no corpus statistic: everything it decides about a paper
    is decided from that paper's own bytes and that paper's own rung-(b) output, so B.29's
    item-locality and B.28's per-item cache survive the widening.

    Complexity: one subprocess per paper with a non-empty residue, O(residue bytes) to locate,
    O(k) to admit k candidates, and one vectorised membership test for the proposed relations.
    """

    def __init__(self, proposer: propose.ProposerIdentity, cache_dir: Path | None) -> None:
        self.proposer = proposer
        self.grammar = propose.QASPER_GRAMMAR
        self.extractor_id = proposer.extractor_id("qasper")
        self.cache_dir = cache_dir or (Path(tempfile.gettempdir()) / "atlas-rung-c-proposals")
        self.report = propose.AdmissionReport()
        self.census = {"items": 0, "items_with_a_residue": 0, "paragraphs": 0,
                       "paragraphs_with_a_rung_b_row": 0, "residue_paragraphs": 0,
                       "residue_characters": 0, "characters": 0}
        self.cost = {"calls": 0, "cache_hits": 0, "seconds": 0.0, "prompt_chars": 0,
                     "input_tokens": 0, "output_tokens": 0}
        self.proposed_relations: list[dict[str, Any]] = []

    # The shared census names its fields after the first dataset that had them; this dataset's
    # receipt says paragraphs, because that is what was counted.
    _CENSUS_FIELDS = (("paragraphs", "turns"),
                      ("paragraphs_with_a_rung_b_row", "turns_with_a_rung_b_row"),
                      ("residue_paragraphs", "residue_turns"),
                      ("residue_characters", "residue_characters"),
                      ("characters", "characters"))

    def propose_for_item(self, ingestion: Ingestion, handle: str, paper_id: str,
                         produced: frozenset[tuple[int, int]],
                         paragraphs: Sequence[propose.ResidueTurn],
                         locators: dict[tuple[int, int], Any],
                         minted: frozenset[tuple[str, str]] = frozenset()) -> None:
        """Ask about this paper's residue once, then admit what the bytes admit."""
        residue, census = propose.residue_of_item(paragraphs, produced)
        self.census["items"] += 1
        for mine, theirs in self._CENSUS_FIELDS:        # loop-ok: the census' own five fields
            self.census[mine] += int(census[theirs])
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
        containers = {(p.session_index, p.turn_index): p for p in residue}  # loop-ok: this paper's residue
        candidates = propose.locate_candidates(response.get("rows", ()), containers, minted,
                                               self.report, self.grammar)
        self._admit(ingestion, handle, paper_id, candidates, locators)
        for relation in response.get("relations", ()):   # loop-ok: this paper's own proposals
            self.report.proposed_relations += 1
            kind = str(relation.get("kind", ""))
            if kind not in self.grammar.relation_kinds:
                self.report.refuse("unknown_relation_kind")
                continue
            self.proposed_relations.append(
                {"kind": kind, "paper_id": paper_id,
                 "source_surface": str(relation.get("source_surface", "")),
                 "target_surface": str(relation.get("target_surface", ""))})

    def _admit(self, ingestion: Ingestion, handle: str, paper_id: str,
               candidates: Sequence[propose.Candidate],
               locators: dict[tuple[int, int], Any]) -> None:
        """Type each located candidate by the DECLARED grammar, then let the store's predicate rule.

        A proposed quantity is typed by running the rung-(b) quantity grammar over the
        candidate's OWN located surface: the model says WHERE to look, the declared extractor
        says what the value, the scale and the unit ARE. So no typed field in this record was
        ever asserted by a model, and a surface the grammar cannot type is refused by name.
        """
        batches: dict[str, tuple[list[dict[str, Any]], list[tuple[int, int]]]] = {}
        for candidate in candidates:                    # loop-ok: this paper's located candidates
            locator = locators.get((candidate.session_index, candidate.turn_index))
            if locator is None:
                self.report.refuse("container_not_declared")
                continue
            if candidate.kind == "entity":
                record: dict[str, Any] = {"paper_id": paper_id, "surface": candidate.surface}
            else:
                parsed = extract.quantities(candidate.surface)
                if len(parsed) != 1:
                    self.report.refuse("quantity_not_typed_by_the_declared_grammar")
                    continue
                record = {"paper_id": paper_id,
                          "value_surface": parsed[0].located.surface.strip(),
                          "value_scaled": parsed[0].value_scaled,
                          "value_scale": parsed[0].value_scale,
                          "unit_surface": parsed[0].unit_surface}
            records, ranges = batches.setdefault(candidate.kind, ([], []))
            records.append(record)
            ranges.append(locator.span(candidate.start, candidate.end))
        must_appear = {"entity": ("surface",), "quantity": ("value_surface",)}
        for kind, (records, ranges) in sorted(batches.items()):  # loop-ok: the two proposable kinds
            spans = ingestion.add_spans(handle, ranges).tolist()
            admission = ingestion.store.append_rows(
                kind, records, spans, rung=RUNG_C, extractor_id=self.extractor_id,
                witness_options={"must_appear": must_appear[kind], "decode_escapes": True})
            admitted = len(admission.positions)
            self.report.admit(kind, admitted)
            if admitted < len(records):
                self.report.refuse("witness_predicate_refused", len(records) - admitted)
            # The same staging the rung-(b) rows use, so a proposed row's mentions edge is minted
            # by _located_relations from a LOCATED occurrence inside a paragraph, never asserted.
            _pending(ingestion, "mentions", admission,
                     [[r] for r in ranges], handle)  # loop-ok: this batch's own located ranges

    def verify_proposed_relations(self, ingestion: Ingestion) -> None:
        """A proposed relation is admitted only if the DECLARED rule minted it anyway.

        The model never adds an edge and never weighs one. Its same_entity proposals are checked
        against the edges ``_same_entity`` produced from the declared alias rule, so an edge in
        this record is always a mechanical consequence of located bytes. Both orders are tested
        because the kind is declared symmetric. Complexity: O(proposals) lookups plus one packed
        membership test.
        """
        if not self.proposed_relations:
            return
        rows = max(ingestion.store.row_count, 1)
        index: dict[tuple[str, str], int] = {}
        table = ingestion.store.table("entity")
        if len(table):
            index.update(zip(zip(table.decode("paper_id"), table.decode("surface")),
                             table.global_ordinals.tolist()))
        edges = ingestion.relations.kind("same_entity")
        minted = (edges.src.to(torch.int64) * rows + edges.dst.to(torch.int64) if len(edges)
                  else torch.empty(0, dtype=torch.int64, device=ingestion.device))
        forward: list[int] = []
        backward: list[int] = []
        for proposal in self.proposed_relations:         # loop-ok: the proposals of this run
            src = index.get((proposal["paper_id"], proposal["source_surface"]))
            dst = index.get((proposal["paper_id"], proposal["target_surface"]))
            if src is None or dst is None:
                self.report.refuse("relation_endpoint_not_admitted")
                continue
            forward.append(int(src) * rows + int(dst))
            backward.append(int(dst) * rows + int(src))
        if not forward:
            return
        probe = torch.tensor(forward, dtype=torch.int64, device=ingestion.device)
        mirror = torch.tensor(backward, dtype=torch.int64, device=ingestion.device)
        present = torch.isin(probe, minted) | torch.isin(mirror, minted)
        admitted = int(present.sum().item())
        self.report.admit_relation("same_entity", admitted)
        if admitted < len(forward):
            self.report.refuse("relation_predicate_refused", len(forward) - admitted)

    def counters(self) -> dict[str, Any]:
        """The rung's whole receipt: the residue it was licensed by, what it cost, what it added."""
        calls = max(self.cost["calls"], 1)
        return {"rung_c": {
            "proposer": self.proposer.as_dict(),
            "grammar": {"dataset": self.grammar.dataset, "id": self.grammar.grammar_id,
                        "row_kinds": list(self.grammar.row_kinds),
                        "relation_kinds": list(self.grammar.relation_kinds),
                        "container": [self.grammar.outer_member, self.grammar.inner_member]},
            "residue_measured_before_the_rung": dict(self.census),
            "cost": {**self.cost,
                     "seconds_per_item": self.cost["seconds"] / calls,
                     "input_tokens_per_item": self.cost["input_tokens"] / calls,
                     "output_tokens_per_item": self.cost["output_tokens"] / calls},
            "admission": self.report.as_dict()}}


# --------------------------------------------------------------------------- relations
def _build_relations(ingestion: Ingestion, rungs: str, since: int = 0) -> None:
    """Every relation kind, built by device joins over the shared integer keys.

    ``since`` restricts BOTH endpoints to rows minted at or after that global ordinal, which is
    what makes a single-paper append O(diff): B.31 keeps a changed paper's old rows as valid
    objects beside the new ones, so an unrestricted join would wire the new paragraphs into the
    superseded paper's sections.
    """
    store = ingestion.store
    paragraphs, sections, papers = (store.table("paragraph"), store.table("section"),
                                    store.table("paper"))
    if not len(paragraphs) or not len(sections):
        return
    device = store.device
    blob_of_span = ingestion.spans.columns[:, 0]

    def blob_of(table: Any) -> torch.Tensor:
        return blob_of_span.index_select(0, table.witness_span)

    # The join key carries the BLOB, exactly as longmem does: a changed paper is a new blob whose
    # rows repeat the declared fields (B.31), and a key without the blob would wire the new
    # paragraphs into the superseded paper's sections.
    offset = int(-min(int(sections.column("section_index").min()), 0))
    stride = int(sections.column("section_index").max()) + offset + 1
    pid_stride = max(int(sections.column("paper_id").max()) + 1, 1)

    def section_key(table: Any) -> torch.Tensor:
        return ((blob_of(table) * pid_stride + table.column("paper_id").to(torch.int64)) * stride
                + table.column("section_index").to(torch.int64) + offset)

    key_sections = section_key(sections)
    key_paragraphs = section_key(paragraphs)
    order = torch.argsort(key_sections, stable=True)
    slot = torch.searchsorted(key_sections.index_select(0, order), key_paragraphs)
    slot = slot.clamp(max=max(key_sections.numel() - 1, 0))
    matched = order.index_select(0, slot)
    paragraph_new = paragraphs.global_ordinals >= since
    section_new = sections.global_ordinals >= since
    valid = key_sections.index_select(0, matched) == key_paragraphs
    valid &= paragraph_new & section_new.index_select(0, matched)

    paragraph_pid = paragraphs.decode("paper_id")
    paragraph_si = paragraphs.column("section_index").tolist()
    paragraph_pi = paragraphs.column("paragraph_index").tolist()
    section_pid = sections.decode("paper_id")
    section_si = sections.column("section_index").tolist()

    src_local = torch.nonzero(valid, as_tuple=False).flatten()
    dst_local = matched.index_select(0, src_local)
    ingestion.append_relations(
        "in_section",
        paragraphs.global_ordinals.index_select(0, src_local).tolist(),
        sections.global_ordinals.index_select(0, dst_local).tolist(),
        [(int(a), int(b)) for a, b in zip(
            paragraphs.witness_span.index_select(0, src_local).tolist(),
            sections.witness_span.index_select(0, dst_local).tolist())],
        contexts=[{"source_fields": {"paper_id": paragraph_pid[s],
                                     "section_index": paragraph_si[s]},
                   "target_fields": {"paper_id": section_pid[d],
                                     "section_index": section_si[d]}}
                  for s, d in zip(src_local.tolist(), dst_local.tolist())],
        extractor_id=EXTRACTOR_ID_A,
        witness_options={"equal_fields": ("paper_id", "section_index")})

    # follows: consecutive paragraph_index inside one (paper, section). Sort once, pair adjacent.
    full_stride = int(paragraphs.column("paragraph_index").max()) + 1
    full_key = key_paragraphs * full_stride + paragraphs.column("paragraph_index").to(torch.int64)
    order = torch.argsort(full_key, stable=True)
    left, right = order[1:], order[:-1]
    same = key_paragraphs.index_select(0, left) == key_paragraphs.index_select(0, right)
    step = paragraphs.column("paragraph_index").to(torch.int64)
    keep = same & (step.index_select(0, left) == step.index_select(0, right) + 1) \
        & paragraph_new.index_select(0, left) & paragraph_new.index_select(0, right)
    left, right = left[keep], right[keep]
    ingestion.append_relations(
        "follows",
        paragraphs.global_ordinals.index_select(0, left).tolist(),
        paragraphs.global_ordinals.index_select(0, right).tolist(),
        [(int(a), int(b)) for a, b in zip(
            paragraphs.witness_span.index_select(0, left).tolist(),
            paragraphs.witness_span.index_select(0, right).tolist())],
        contexts=[{"source_fields": {"paper_id": paragraph_pid[s], "section_index":
                                     paragraph_si[s], "paragraph_index": paragraph_pi[s]},
                   "target_fields": {"paper_id": paragraph_pid[d], "section_index":
                                     paragraph_si[d], "paragraph_index": paragraph_pi[d]}}
                  for s, d in zip(left.tolist(), right.tolist())],
        extractor_id=EXTRACTOR_ID_A,
        witness_options={"equal_fields": ("paper_id", "section_index"),
                         "successor_field": "paragraph_index"})

    _in_jurisdiction(ingestion, papers, blob_of, pid_stride, since)
    if "b" in rungs:
        _float_relations(ingestion, paragraphs, sections, key_paragraphs, key_sections)
        _located_relations(ingestion, paragraphs)
        _same_entity(ingestion, since)
    _ = device


def _in_jurisdiction(ingestion: Ingestion, papers: Any, blob_of: Any, pid_stride: int,
                     since: int = 0) -> None:
    """Every non-paper row points at its paper. Uncounted: it is provenance, not structure."""
    store = ingestion.store
    if not len(papers):
        return
    paper_key = blob_of(papers) * pid_stride + papers.column("paper_id").to(torch.int64)
    order = torch.argsort(paper_key, stable=True)
    sorted_key = paper_key.index_select(0, order)
    paper_pid = papers.decode("paper_id")
    for kind in ("section", "question", "table", "figure"):
        table = store.table(kind)
        if not len(table):
            continue
        key = blob_of(table) * pid_stride + table.column("paper_id").to(torch.int64)
        slot = torch.searchsorted(sorted_key, key).clamp(max=max(paper_key.numel() - 1, 0))
        matched = order.index_select(0, slot)
        keep = paper_key.index_select(0, matched) == key
        keep &= (table.global_ordinals >= since) & (
            (papers.global_ordinals >= since).index_select(0, matched))
        rows = torch.nonzero(keep, as_tuple=False).flatten()
        if rows.numel() == 0:
            continue
        matched = matched.index_select(0, rows)
        source_pid = table.decode("paper_id")
        ingestion.append_relations(
            "in_jurisdiction",
            table.global_ordinals.index_select(0, rows).tolist(),
            papers.global_ordinals.index_select(0, matched).tolist(),
            [(int(a), int(b)) for a, b in zip(
                table.witness_span.index_select(0, rows).tolist(),
                papers.witness_span.index_select(0, matched).tolist())],
            contexts=[{"source_fields": {"paper_id": source_pid[s]},
                       "target_fields": {"paper_id": paper_pid[d]}}
                      for s, d in zip(rows.tolist(), matched.tolist())],
            extractor_id=EXTRACTOR_ID_A, witness_options={"equal_fields": ("paper_id",)})


def _float_relations(ingestion: Ingestion, paragraphs: Any, sections: Any,
                     key_paragraphs: torch.Tensor, key_sections: torch.Tensor) -> None:
    """table_of / figure_of: the float's own label, located in a paragraph of that section.

    No guess is made about what ``TABREF3`` points at - QASPER's marker index is not the float's
    position and resolving it would be an invention. The edge is minted only where the float's
    OWN label ("Table 1") is located verbatim in a paragraph, which is a witness anyone can
    re-read. A float no paragraph names stays unlinked and is reported in the coverage statement.
    """
    store = ingestion.store
    pending = ingestion.pending_labels
    if not pending:
        return
    section_of_key = {int(k): i for i, k in enumerate(key_sections.tolist())}
    paragraph_keys = key_paragraphs.tolist()
    paragraph_at = {(pid, si, pi): local for local, (pid, si, pi) in enumerate(zip(
        paragraphs.decode("paper_id"), paragraphs.column("section_index").tolist(),
        paragraphs.column("paragraph_index").tolist()))}
    paragraph_witness = paragraphs.witness_span.tolist()
    for kind in FLOAT_KINDS:
        table = store.table(kind)
        if not len(table):
            continue
        label_of = {(pid, label): local for local, (pid, label)
                    in enumerate(zip(table.decode("paper_id"), table.decode("label")))}
        src, dst, witness, contexts = [], [], [], []
        seen: set[tuple[int, int]] = set()
        for paper_id, float_kind, label, si, pi, handle, span_range in pending:
            if float_kind != kind:
                continue
            local = label_of.get((paper_id, label))
            paragraph_local = paragraph_at.get((paper_id, si, pi))
            if local is None or paragraph_local is None:
                continue
            section_local = section_of_key.get(int(paragraph_keys[paragraph_local]))
            if section_local is None or (local, section_local) in seen:
                continue
            seen.add((local, section_local))
            located = int(ingestion.add_spans(handle, [span_range])[0])
            src.append(int(table.global_ordinals[local]))
            dst.append(int(sections.global_ordinals[section_local]))
            witness.append((located, int(table.witness_span[local]),
                            int(paragraph_witness[paragraph_local])))
            contexts.append({"argument": label, "target_surfaces": (label,)})
        if src:
            ingestion.append_relations(f"{kind}_of", src, dst, witness, contexts=contexts,
                                       extractor_id=EXTRACTOR_ID_A, witness_options={})


def _located_relations(ingestion: Ingestion, paragraphs: Any) -> None:
    """cites and mentions: a located occurrence inside a paragraph's own byte range."""
    _ = paragraphs
    ingestion.mint_located_edges("cites", "paragraph", carrier_is_source=False,
                                 extractor_id=EXTRACTOR_ID_B)
    ingestion.mint_located_edges("mentions", "paragraph", carrier_is_source=True,
                                 extractor_id=EXTRACTOR_ID_B)


def _same_entity(ingestion: Ingestion, since: int = 0) -> None:
    """The declared alias rule, applied inside ONE paper (B.29 item-locality)."""
    store = ingestion.store
    entities = store.table("entity")
    if not len(entities):
        return
    surfaces = entities.decode("surface")
    papers = entities.decode("paper_id")
    witness = entities.witness_span.tolist()
    globals_ = entities.global_ordinals.tolist()
    by_paper: dict[str, dict[str, int]] = {}
    for local, (paper_id, surface) in enumerate(zip(papers, surfaces)):
        if globals_[local] >= since:
            by_paper.setdefault(paper_id, {})[surface] = local
    src, dst, spans, contexts = [], [], [], []
    for paper_id, index in by_paper.items():
        for short, long in extract.alias_pairs(index):
            src.append(globals_[index[long]])
            dst.append(globals_[index[short]])
            spans.append((witness[index[long]], witness[index[short]]))
            contexts.append({"argument": short, "target_surfaces": (short,)})
    if src:
        ingestion.append_relations("same_entity", src, dst, spans, contexts=contexts,
                                   extractor_id=EXTRACTOR_ID_B, witness_options={})


# --------------------------------------------------------------------------- gold join
def unit_id_of_row(paper_id: str, kind: str, section_index: int, paragraph_index: int) -> str:
    """The id ``qasper_data.export_source_questions`` and ``gold_spans`` mint for this row.

    The record and the established gold map therefore name the SAME object, so a gold address can
    be joined to a row without either side re-deriving the other's identity.
    """
    if kind != "paragraph":
        raise ValueError(f"no unit id for kind {kind}")
    if section_index == ABSTRACT_SECTION_INDEX:
        return f"qasper:{paper_id}:abstract"
    return f"qasper:{paper_id}:s{section_index}:p{paragraph_index}"
