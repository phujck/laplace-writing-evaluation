"""QASPER at B.34, the rung-(b) extractors, and the corrected anchor instrument.

Every test that needs a corpus is skipped BY NAME when its archive is absent, so a clone without
the QASPER or LongMemEval caches reports skips rather than a green suite that checked nothing.

What these assert, in one line each: that the extractors address real bytes; that a paragraph row
is the container's paragraph and not a chunk; that the gold map is named and complete; that a
resolved anchor now WALKS (the I1 deficiency); that the cache, the duplicate scan and
``supersedes_blob`` do what the amended clauses say, including under a planted bypass.
"""

from __future__ import annotations

import datetime as dt
import json

import pytest
import torch

from atlas.record import diff, extract, measure
from atlas.record.ingest import longmem, qasper
from atlas.record.json_spans import iter_array_items, iter_object_members

cuda = pytest.mark.skipif(not torch.cuda.is_available(),
                          reason="the record layer's numeric core is CUDA-only by policy")
have_qasper = pytest.mark.skipif(not qasper.available("dev"), reason="QASPER archive absent")
have_longmem = pytest.mark.skipif(not longmem.DATASET_PATH.is_file(),
                                  reason="LongMemEval-S cache absent")


@pytest.fixture(scope="module")
def papers():
    return qasper.ingest("dev", papers=4, rungs="ab")


@pytest.fixture(scope="module")
def papers_rung_a():
    return qasper.ingest("dev", papers=4, rungs="a")


# --------------------------------------------------------------------- the extractors
def test_extract_offsets_address_their_own_surface():
    text = ("We build on GE-FL BIBREF0 . Ana Silva and Silva joined New York University. "
            "It used 3.5 GiB and 45% of 1,200 tokens.")
    markers = extract.reference_markers(text)
    for located, kind in markers:
        assert text[located.start:located.end] == located.surface
        assert kind in extract.REFERENCE_KINDS
    for located in extract.proper_nouns(text, [(m.start, m.end) for m, _ in markers]):
        assert text[located.start:located.end] == located.surface
    for quantity in extract.quantities(text):
        assert text[quantity.located.start:quantity.located.end] == quantity.located.surface


def test_extract_proper_noun_refuses_a_sentence_initial_singleton_but_keeps_a_run():
    found = {located.surface for located in proper("The cat sat. New York is large. Ana ran.")}
    assert "The" not in found and "Ana" not in found, (
        "a single capitalised token at a sentence start is explained by the sentence")
    assert "New York" in found, "a multi-token run is a name wherever it stands"


def proper(text):
    return extract.proper_nouns(text)


def test_extract_quantity_is_an_exact_decimal_not_a_float():
    quantities = {q.located.surface: (q.value_scaled, q.value_scale, q.unit_surface)
                  for q in extract.quantities("3.5 GiB, 45%, 1,200 tokens, -0.25 s")}
    assert quantities["3.5 GiB"] == (35, 1, "GiB")
    assert quantities["45%"] == (45, 0, "%")
    assert quantities["1,200 tokens"] == (1200, 0, "tokens")
    assert quantities["-0.25 s"] == (-25, 2, "s")


def test_extract_relative_date_resolves_against_the_row_not_the_clock():
    reference = dt.datetime(2023, 5, 20)
    found = {e.located.surface: e.resolved.date()
             for e in extract.temporal_expressions("3 weeks ago, and on March 4, 2021",
                                                   reference)}
    assert found["3 weeks ago"] == dt.date(2023, 4, 29)
    assert found["March 4, 2021"] == dt.date(2021, 3, 4)
    later = extract.temporal_expressions("3 weeks ago", dt.datetime(2024, 5, 20))
    assert later[0].resolved.date() == dt.date(2024, 4, 29), (
        "the same bytes resolve differently only because the ROW's date differs")


def test_extract_state_claim_carries_polarity():
    claims = extract.state_claims("My sister is Ana. My cat is not Miso.")
    assert [(c.attribute, c.value, c.polarity) for c in claims] == [
        ("sister", "Ana", "asserted"), ("cat", "Miso", "negated")]


def test_extract_alias_rule_is_a_token_subsequence_not_a_similarity():
    assert extract.alias_pairs(["Ana Silva", "Silva", "New York University", "Sylva"]) == [
        ("Silva", "Ana Silva")]


def test_extract_locator_maps_escaped_and_non_ascii_characters_to_their_bytes():
    raw = json.dumps('café "x" \\ \U0001f600 end').encode("utf-8")
    locator = extract.locator_for_json_string(raw, 0)
    assert locator.text == 'café "x" \\ \U0001f600 end'
    for index, character in enumerate(locator.text):
        start, end = locator.span(index, index + 1)
        assert 0 < start < end <= len(raw)
        decoded = json.loads('"' + raw[start:end].decode("utf-8", "replace") + '"')
        assert decoded == character


# --------------------------------------------------------------------- the object streamer
@cuda
@have_qasper
def test_record_qasper_object_stream_offsets_are_exact():
    import tarfile

    with tarfile.open(qasper.ARCHIVES["dev"]) as archive:
        data = archive.extractfile(qasper.SPLIT_MEMBER["dev"]).read()
    whole = json.loads(data)
    with tarfile.open(qasper.ARCHIVES["dev"]) as archive:
        stream = archive.extractfile(qasper.SPLIT_MEMBER["dev"])
        for paper_id, start, end, raw in iter_object_members(stream, limit=5):
            assert data[start:end] == raw, "the yielded bytes are the file's own bytes"
            assert json.loads(raw.decode("utf-8")) == whole[paper_id]


# --------------------------------------------------------------------- B.34 structure
@cuda
@have_qasper
def test_record_qasper_paragraph_rows_are_the_containers_paragraphs_not_chunks(papers):
    """The named failure is 'shard the paper into fixed-size passages'. This is the refutation."""
    store = papers.store
    paragraphs = store.table("paragraph")
    assert len(paragraphs) > 0
    assert "text" not in paragraphs.spec.columns, "B.1: the row stores no copy of its text"
    for local in (0, len(paragraphs) // 2, len(paragraphs) - 1):
        span_ord = int(paragraphs.column("text_span")[local])
        handle, start, end = papers.spans.address(span_ord)
        raw = papers.blobs.read(handle, start, end)
        assert raw.startswith(b'"') and raw.endswith(b'"')
    # Count against the source: one row per non-blank paragraph, plus one per non-blank abstract.
    expected = 0
    for item in qasper.iter_papers("dev", limit=4):
        node, _ = qasper.scan_value(item.raw, 0, 0)
        if str((node.get("abstract").value if node.get("abstract") else "") or "").strip():
            expected += 1
        for section in node.member("full_text").items or ():
            expected += sum(1 for p in (section.member("paragraphs").items or ())
                            if str(p.value or "").strip())
    assert len(paragraphs) == expected, "no paragraph was split and none was merged"


@cuda
@have_qasper
def test_record_qasper_floats_are_rows_with_labels_and_witnessed_edges(papers):
    tables, figures = papers.store.table("table"), papers.store.table("figure")
    assert len(tables) + len(figures) > 0
    for kind, table in (("table", tables), ("figure", figures)):
        if not len(table):
            continue
        for label, span_ord in zip(table.decode("label"), table.witness_span.tolist()):
            handle, start, end = papers.spans.address(int(span_ord))
            caption = papers.blobs.read(handle, start, end).decode("utf-8", "replace")
            assert label.split()[-1] in caption, f"{kind} label is located in its own caption"
    edges = papers.relations.kind("table_of")
    if len(edges):
        columns = papers.spans.columns
        for instance in range(min(len(edges), 5)):
            located, caption_span, paragraph_span = edges.witnesses_of(instance).tolist()[:3]
            low = columns[located].tolist()
            outer = columns[paragraph_span].tolist()
            assert low[0] == outer[0] and outer[1] <= low[1] and low[2] <= outer[2], (
                "the table's label is located INSIDE the paragraph that names it")
            assert caption_span >= 0


@cuda
@have_qasper
def test_record_qasper_cites_edges_are_located_inside_their_paragraph(papers):
    edges = papers.relations.kind("cites")
    assert len(edges) > 0
    columns = papers.spans.columns
    for instance in range(0, len(edges), max(len(edges) // 20, 1)):
        located, paragraph = edges.witnesses_of(instance).tolist()
        inner, outer = columns[located].tolist(), columns[paragraph].tolist()
        assert inner[0] == outer[0] and outer[1] <= inner[1] and inner[2] <= outer[2]


@cuda
@have_qasper
def test_record_qasper_gold_never_enters_the_record(papers):
    """Answers, evidence and annotation ids are evaluator data (B.34)."""
    kinds = set(papers.store.tables)
    assert not kinds & {"answer", "evidence", "annotation"}
    for table in papers.store.tables.values():
        assert "answer" not in table.spec.columns and "evidence" not in table.spec.columns
    raw = qasper_first_paper()
    evidence_texts = {e for q in raw["qas"] for a in q["answers"]
                      for e in a["answer"]["evidence"]}
    surfaces = set(papers.store.table("entity").decode("surface"))
    assert not (evidence_texts & surfaces)


def qasper_first_paper():
    item = next(iter(qasper.iter_papers("dev", limit=1)))
    return json.loads(item.raw.decode("utf-8"))


# --------------------------------------------------------------------- the gold map
@cuda
@have_qasper
def test_record_qasper_repaired_gold_map_runs_against_the_store_and_is_named(papers):
    repaired = measure.qasper_reach(papers, "dev", repaired=True)
    legacy = measure.qasper_reach(papers, "dev", repaired=False)
    assert repaired["gold_map"] == "repaired" and legacy["gold_map"] == "legacy"
    assert repaired["gold_requirements_unresolved"] == 0, (
        "the repaired map leaves nothing unresolved - the F1 headline, re-run here")
    assert legacy["gold_requirements_unresolved"] > 0, (
        "the legacy map does leave requirements unresolved; otherwise the repair is untested")
    assert repaired["gold_paragraph_row_coverage"] == 1.0, (
        "B.34: every gold evidence PARAGRAPH has a paragraph row")
    control = repaired["by_condition_class"]["all_paragraphs"]
    assert control["mean_reach"] == 1.0 and control["mean_cost"] == 1.0
    assert repaired["isolation"]["all_paragraphs"] == 0


# --------------------------------------------------------------------- the instrument
@cuda
@have_qasper
def test_record_anchor_expansion_walks_a_relation_with_a_planted_positive_control(papers):
    """The I1 deficiency, with its control: a resolved entity must REACH its paragraph."""
    entities = papers.store.table("entity")
    mentions = papers.relations.kind("mentions")
    assert len(mentions) > 0
    # Plant the control: take an entity that actually has a mention edge, and seed the walk with
    # exactly that entity's row. Depth 1 is then the only correct answer.
    seed = int(mentions.src[0])
    horizon = measure.declared_walk_horizon(papers.declaration, "paragraph")
    expansion = measure.anchor_expansion(
        papers, torch.tensor([seed], dtype=torch.int64, device=papers.device),
        "paragraph", horizon)
    assert expansion["resolved"] == 1
    assert expansion["reached_a_carrier"] is True, (
        "the corrected mask expands through the declared relations; the I1 mask could not")
    assert expansion["depth"] == 1
    assert expansion["carrier_local"].numel() >= 1
    local_of = papers.store.local_of_global("paragraph")
    expected = int(local_of[int(mentions.dst[0])])
    assert expected in set(expansion["carrier_local"].tolist())
    _ = entities


@cuda
@have_qasper
def test_record_anchor_expansion_fails_closed_on_zero_anchors(papers):
    empty = torch.empty(0, dtype=torch.int64, device=papers.device)
    expansion = measure.anchor_expansion(papers, empty, "paragraph", 3)
    assert expansion["resolved"] == 0 and expansion["carrier_local"].numel() == 0
    mask = measure._anchor_mask(
        torch.ones(len(papers.store.table("paragraph")), dtype=torch.bool,
                   device=papers.device), expansion)
    assert int(mask.sum()) == 0, "no anchors admit nothing - never everything"


@cuda
@have_qasper
def test_record_walk_horizon_is_derived_from_the_declaration_not_chosen(papers,
                                                                        papers_rung_a):
    assert measure.declared_walk_horizon(papers.declaration, "paragraph") == 3
    assert measure.declared_walk_horizon(papers_rung_a.declaration, "paragraph") == 3


@cuda
@have_longmem
def test_record_longmem_rung_b_resolves_names_where_rung_a_resolved_none():
    gold = longmem.read_gold(limit=3)
    before = measure.rung_a_reach(longmem.ingest(histories=3, rungs="a"), gold)
    after = measure.rung_a_reach(longmem.ingest(histories=3, rungs="ab"), gold)
    assert before["questions_resolving_at_least_one_anchor"] == 0, (
        "the measured residue that licences rung (b), re-run rather than quoted")
    assert after["questions_resolving_at_least_one_anchor"] > 0
    assert after["declared_walk_horizon"] == 2
    assert after["by_condition_class"]["anchor_resolved"]["mean_cost"] < 1.0, (
        "an anchor condition that admitted everything would be the control, not a result")


# --------------------------------------------------------------------- amended clauses
@cuda
@have_qasper
def test_record_qasper_insert_touches_only_its_own_rows(papers_rung_a):
    items = list(qasper.iter_papers("dev", limit=5))
    ingestion = qasper.ingest("dev", paper_ids=[i.paper_id for i in items[:4]], rungs="ab")
    before = ingestion.store.row_count
    touched = diff.apply_paper(ingestion, items[4].raw, items[4].paper_id)
    assert touched.cache_hit is False
    assert len(touched.neighbour_ordinals) == 0, "no row outside the new paper is an endpoint"
    owners = set()
    for table in ingestion.store.tables.values():
        if not len(table) or "paper_id" not in table.spec.columns:
            continue
        for local, value in enumerate(table.decode("paper_id")):
            if int(table.global_ordinals[local]) >= before:
                owners.add(value)
    assert owners == {items[4].paper_id}, "every row the insert minted is the new paper's"
    assert diff.apply_paper(ingestion, items[4].raw, items[4].paper_id).cache_hit is True


@cuda
@have_longmem
def test_record_amended_cache_key_survives_the_edit_it_exists_for():
    ingestion = longmem.ingest(histories=2, rungs="a")
    raws = [raw for _, _, raw in iter_array_items(longmem.DATASET_PATH, limit=2)]
    measured = diff.measure_change_locality(ingestion, raws[0], ("user", "A new turn."))
    assert measured["b28_container_keyed_hits_before_the_amendment"] == 0
    assert measured["item_keyed_hits"] == measured["items_in_changed_blob"] - 1, (
        "every item but the edited one hits the amended key")
    assert measured["supersedes_blob_edges_minted"] == 1
    edges = ingestion.relations.kind("supersedes_blob")
    assert len(edges) == 1, "B.31's relation is queryable, not a paragraph of prose"
    handles = {ingestion.spans.address(int(s))[0]
               for s in edges.witnesses_of(0).tolist()}
    assert len(handles) == 2, "the witness addresses the superseded and superseding blobs"


@cuda
@have_qasper
def test_record_duplicate_scan_is_zero_across_batches_and_bites_when_bypassed():
    items = list(qasper.iter_papers("dev", limit=3))
    ingestion = qasper.ingest("dev", paper_ids=[items[0].paper_id, items[1].paper_id],
                              rungs="ab")
    measured = diff.measure_cross_batch_duplicates(
        ingestion, [items[0].raw], lambda ing, raw: diff.apply_paper(ing, raw,
                                                                     items[0].paper_id))
    assert measured["cache_hits_on_replay"] == 1
    assert measured["rows_added_by_the_replay"] == {}
    assert measured["duplicate_rows_total"] == 0
    planted = measured["planted_violation"]
    assert planted["rows_minted_again"] > 0
    assert planted["duplicate_rows_total_after_the_bypass"] > 0, (
        "the scan is the standing diagnostic only if it catches a bypassed cache")


@cuda
@have_longmem
def test_record_anchor_compaction_returns_resolve_to_the_csr_path():
    ingestion = longmem.ingest(histories=2, rungs="ab")
    raws = [raw for _, _, raw in iter_array_items(longmem.DATASET_PATH, limit=3)]
    touched = diff.apply_case(ingestion, raws[2])
    assert ingestion.anchors.delta_postings > 0, "an append leaves a delta; that is O(diff)"
    surfaces = list(touched.posting_surfaces)[:64]
    measured = diff.measure_compaction(ingestion, surfaces)
    assert measured["delta_postings_before"] > 0
    assert measured["delta_postings_after"] == 0
    assert measured["same_rows"] is True, "a faster path that answered differently is a bug"
    assert ingestion.anchors.resolve(surfaces).numel() == measured["rows_resolved"]


# --------------------------------------------------------------------- the ladder's floor
def test_record_extractors_call_no_model_and_no_network():
    source = (extract.__file__,)
    text = "".join(open(path, encoding="utf-8").read() for path in source)
    for forbidden in ("torch", "transformers", "sentence_transformers", "fastembed",
                      "requests", "urllib", "openai", "sklearn", "quantulum"):
        assert f"import {forbidden}" not in text, (
            f"rung (b) is deterministic extractors only; {forbidden} is not one")


# ------------------------------------------------- continuation 1: the four repaired claims
def test_extract_unit_surface_ends_where_the_grammar_ends_and_is_never_truncated():
    """The unit tail has no length bound, so the stored surface IS the located surface.

    The grammar's own rule decides where a unit ends - the first character outside letter /
    mark / '-' / '/', with a full stop only where a letter follows. An earlier ``{0,15}`` cap
    silently truncated a longer token into the row and into its witness span, which is a wrong
    address rather than a short one. This asserts the derivation the cap is removed in favour
    of, on the corpus's own long surfaces.
    """
    text = ("we ran 37.5 degreesCelsiusish and 12 microelectronvolts over 3 embedding/hidden "
            "units, 2,000 overlapping windows, 45% of 1.5 GiB.")
    tail = extract.regex.compile(r"[\p{L}\p{M}\-/]", extract.regex.UNICODE)
    for quantity in extract.quantities(text):
        located = quantity.located
        assert text[located.start:located.end] == located.surface
        assert located.surface.endswith(quantity.unit_surface)
        after = text[located.end:located.end + 1]
        assert not (quantity.unit_surface and after and tail.match(after)), (
            f"unit surface {quantity.unit_surface!r} was cut mid-token before {after!r}")
    surfaces = {q.unit_surface for q in extract.quantities(text)}
    assert "degreesCelsiusish" in surfaces and "microelectronvolts" in surfaces, (
        "a 17- and an 18-character unit surface survive whole; under {0,15} both were cut")


def test_extract_roster_hash_moves_when_a_grammar_moves():
    """The roster hash names the CONSTRUCTION, not just the list of extractor ids."""
    before = extract.extractor_roster_hash()
    original = extract._QUANTITY
    try:
        extract._QUANTITY = extract.regex.compile(original.pattern.replace(")*)", "){0,15})"),
                                                  extract.regex.UNICODE)
        assert extract.extractor_roster_hash() != before, (
            "a changed grammar must change the roster hash, or one id names two constructions")
    finally:
        extract._QUANTITY = original
    assert extract.extractor_roster_hash() == before


@have_qasper
def test_qasper_float_marker_survey_reproduces_the_demonstrations_numbers():
    """Impossibility demonstration 2 is a command in this repository, not a transcript.

    The survey deposited beside the packet report is imported and run here, so the four numbers
    the demonstration cites are covered by the packet's own test file.
    """
    import importlib.util
    from pathlib import Path

    path = (Path(__file__).resolve().parents[2] / "evidence" / "ATLAS_PROGRAMME" / "waves"
            / "F2-assembly" / "E1" / "float_marker_survey.py")
    spec = importlib.util.spec_from_file_location("float_marker_survey", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    totals = module.survey("dev")
    assert totals["papers"] == 281 and totals["papers_with_labelled"] == 275
    assert totals["captions"] == 1929 and totals["labelled_floats"] == 1928
    # Neither reading of k is an index into anything the split publishes.
    assert totals["combined_in_range"] == 3        # every marker k < len(figures_and_tables)
    assert totals["tab_in_range"] == 1             # every TABREF k < labelled tables
    assert totals["fig_in_range"] == 0             # every FIGREF k < labelled figures
    assert totals["label_located_verbatim"] == 230  # the only link that carries a witness


@cuda
@have_qasper
def test_grammar_residue_is_measured_on_the_rung_a_store_and_mints_nothing(papers_rung_a):
    """Charter L3: the need for EACH grammar is measured before its rows are used."""
    ingestion = papers_rung_a
    rows_before = ingestion.store.row_count
    edges_before = len(ingestion.relations)
    measured = measure.qasper_reach(ingestion, "dev", repaired=True)
    residue = measure.grammar_residue(
        ingestion, measured["_gold_rows"], kind="paragraph", text_column="text_span",
        isolated_question_ids=[])
    assert ingestion.store.row_count == rows_before, "the probe minted a row"
    assert len(ingestion.relations) == edges_before, "the probe minted a relation"
    assert residue["questions_scored"] > 0
    assert {block["extractor_id"] for block in residue["per_grammar"].values()} == {
        entry[0] for entry in extract.EXTRACTOR_ROSTER}, (
        "one residue per grammar of the roster, not one for the rung")
    for name, block in residue["per_grammar"].items():
        assert 0.0 <= block["share_of_scored_questions_whose_gold_carries_it"] <= 1.0
        assert block["questions_whose_gold_carries_it"] <= residue["questions_scored"]
