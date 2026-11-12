"""The rung-(c) admission audit: what the bytes admit, and what they refuse BY NAME.

Every candidate in this file is PLANTED by the test, never produced by a model. That is the whole
point: the question a test can answer without a model is whether the mechanical half of rung (c)
actually refuses what it claims to refuse, and it is answered by handing it the four failures a
model makes - a surface that is not in the bytes, a container that does not exist, a paraphrase,
and a typed claim whose parts are not in its own clause - beside the one it gets right.

Nothing here is a measurement of the rung. A measurement needs the model.

Run: scripts/laplace-python -m pytest atlas/tests/test_j4_rung_c_admission.py \
         --basetemp=/tmp/pytest-j4-rung-c -q
"""
from __future__ import annotations

import json

import pytest

from atlas.record import propose


TURN_TEXT = ("I finally adopted the tabby from the shelter on Baker Street. "
             "My blood pressure is 120/80 these days and my cat is Pepper.")


def _containers():
    turn = propose.ResidueTurn(session_index=2, turn_index=3, text=TURN_TEXT, start=0,
                               end=len(TURN_TEXT))
    return {(2, 3): turn}


def _report_for(rows, already=frozenset()):
    report = propose.AdmissionReport()
    located = propose.locate_candidates(rows, _containers(), already, report)
    return located, report


def test_a_copied_surface_is_located_and_its_span_is_computed_from_the_bytes():
    located, report = _report_for([
        {"kind": "entity", "surface": "Baker Street", "session_index": 2, "turn_index": 3}])
    assert report.refusals == {}
    assert len(located) == 1
    candidate = located[0]
    assert TURN_TEXT[candidate.start:candidate.end] == "Baker Street"


def test_a_surface_the_bytes_do_not_contain_is_refused_by_name():
    # The model's most common failure: a plausible paraphrase of what the turn says.
    located, report = _report_for([
        {"kind": "entity", "surface": "Baker St.", "session_index": 2, "turn_index": 3},
        {"kind": "entity", "surface": "the animal shelter", "session_index": 2, "turn_index": 3}])
    assert located == []
    assert report.refusals == {"surface_not_located_in_container": 2}


def test_a_container_the_item_does_not_declare_is_refused_by_name():
    located, report = _report_for([
        {"kind": "entity", "surface": "Baker Street", "session_index": 9, "turn_index": 9}])
    assert located == []
    assert report.refusals == {"container_not_declared": 1}


def test_a_kind_outside_the_closed_grammar_is_refused():
    located, report = _report_for([
        {"kind": "relationship", "surface": "Baker Street", "session_index": 2, "turn_index": 3}])
    assert located == []
    assert report.refusals == {"unknown_row_kind": 1}


def test_a_claim_whose_parts_are_not_in_its_own_clause_is_refused():
    good = {"kind": "state_claim", "surface": "my cat is Pepper", "session_index": 2,
            "turn_index": 3, "attribute": "cat", "value": "Pepper", "polarity": "asserted"}
    # Same located clause, but the value is a fact the model brought with it.
    invented = dict(good, value="a tabby")
    located, report = _report_for([good, invented])
    assert [c.surface for c in located] == ["my cat is Pepper"]
    assert report.refusals == {"state_claim_parts_not_in_its_own_surface": 1}
    assert located[0].fields == {"attribute": "cat", "value": "Pepper", "polarity": "asserted"}


def test_a_surface_rung_b_already_minted_is_refused_rather_than_duplicated():
    located, report = _report_for(
        [{"kind": "entity", "surface": "Baker Street", "session_index": 2, "turn_index": 3}],
        already=frozenset({("entity", "Baker Street")}))
    assert located == []
    assert report.refusals == {"already_minted_at_rung_b": 1}


def test_the_residue_is_the_turns_rung_b_minted_nothing_from():
    turns = [propose.ResidueTurn(0, 0, "aaa", 0, 3), propose.ResidueTurn(0, 1, "bbbb", 3, 7)]
    residue, census = propose.residue_of_item(turns, frozenset({(0, 0)}))
    assert [t.turn_index for t in residue] == [1]
    assert census == {"turns": 2, "turns_with_a_rung_b_row": 1, "residue_turns": 1,
                      "residue_characters": 4, "characters": 7}


def test_the_grammar_is_closed_and_a_free_text_fact_cannot_be_expressed():
    row_properties = propose.PROPOSAL_SCHEMA["properties"]["rows"]["items"]
    assert row_properties["additionalProperties"] is False
    assert set(row_properties["properties"]) == {
        "kind", "surface", "session_index", "turn_index", "attribute", "value", "polarity"}
    # No weight, confidence, importance or free-text field anywhere in the grammar.
    text = json.dumps(propose.PROPOSAL_SCHEMA)
    for forbidden in ("weight", "confidence", "importance", "score", "fact", "summary"):
        assert forbidden not in text


@pytest.mark.parametrize("response", [
    {"rows": []},                                                   # missing 'relations'
    {"rows": [], "relations": [], "notes": "I also think..."},       # an extra member
    {"rows": [{"kind": "belief", "surface": "x", "session_index": 0, "turn_index": 0}],
     "relations": []},                                              # a kind outside the enum
    {"rows": [{"kind": "entity", "surface": "x", "session_index": "two", "turn_index": 0}],
     "relations": []},                                              # a container that is not int
])
def test_a_response_outside_the_closed_grammar_is_refused_not_repaired(response):
    assert propose._matches(response, propose.PROPOSAL_SCHEMA) is False


def test_the_proposer_identity_is_in_the_extractor_id_so_a_changed_prompt_re_proposes():
    one = propose.light_tier_proposer()
    other = propose.ProposerIdentity(
        client_version=one.client_version, tier=one.tier, model=one.model,
        prompt_template_hash="sha256:changed", schema_hash=one.schema_hash,
        timeout_seconds=one.timeout_seconds)
    assert one.extractor_id("longmem") != other.extractor_id("longmem")
    assert one.extractor_id("longmem") == propose.light_tier_proposer().extractor_id("longmem")


def test_the_per_item_cache_key_carries_the_proposer_so_a_second_ingest_calls_no_model():
    """B.28's key, with the proposer folded into its extractor id (ingest/longmem.py:293)."""
    from atlas.record.diff import item_bytes_cache_key
    raw = b'{"question_id": "q1"}'
    declaration_hash = "sha256:declaration"
    plain = item_bytes_cache_key(raw, "longmem-rung-a@v1", declaration_hash)
    proposer = propose.light_tier_proposer()
    composite = f"longmem-rung-a@v1+{proposer.extractor_id('longmem')}"
    with_proposer = item_bytes_cache_key(raw, composite, declaration_hash)
    # A rung-(abc) item is a DIFFERENT cache entry from the same bytes at rung (ab) ...
    assert with_proposer != plain
    # ... and the same item under the same proposer is the same entry, so the segment answers it
    # and the model is never called twice for one item.
    assert with_proposer == item_bytes_cache_key(raw, composite, declaration_hash)


def test_the_request_itself_is_content_addressed_on_prompt_schema_model_and_version():
    identity = propose.light_tier_proposer()
    one = propose.request_key("turns A", identity)
    assert one == propose.request_key("turns A", identity)
    assert one != propose.request_key("turns B", identity)


# --------------------------------------------------------------------------------------------
# THE SECOND DATASET VIEW (continuation 1): QASPER, whose container is a paragraph and whose
# declaration carries neither state_claim rows nor supersedes/precedes/about relations.
# --------------------------------------------------------------------------------------------
QASPER_PARAGRAPH = ("We evaluate on the Penn Treebank and report an F1 of 92.4 % on the test "
                    "split, following Collins (1997).")


def _qasper_containers():
    paragraph = propose.ResidueTurn(session_index=3, turn_index=1, text=QASPER_PARAGRAPH,
                                    start=0, end=len(QASPER_PARAGRAPH))
    return {(3, 1): paragraph}


def _qasper_report_for(rows, already=frozenset()):
    report = propose.AdmissionReport()
    located = propose.locate_candidates(rows, _qasper_containers(), already, report,
                                        propose.QASPER_GRAMMAR)
    return located, report


def test_the_qasper_view_addresses_a_paragraph_and_locates_a_copied_surface():
    located, report = _qasper_report_for([
        {"kind": "entity", "surface": "Penn Treebank", "section_index": 3, "paragraph_index": 1}])
    assert report.refusals == {}
    assert QASPER_PARAGRAPH[located[0].start:located[0].end] == "Penn Treebank"


def test_a_kind_inside_the_closed_grammar_but_outside_this_dataset_is_refused_by_its_own_name():
    # state_claim IS a proposable kind; QASPER's declaration does not carry it, and the refusal
    # says which of the two failures it was.
    located, report = _qasper_report_for([
        {"kind": "state_claim", "surface": "We evaluate on the Penn Treebank",
         "section_index": 3, "paragraph_index": 1, "attribute": "x", "value": "y",
         "polarity": "asserted"},
        {"kind": "belief", "surface": "Penn Treebank", "section_index": 3, "paragraph_index": 1}])
    assert located == []
    assert report.refusals == {"kind_not_declared_by_this_dataset": 1, "unknown_row_kind": 1}


def test_the_qasper_container_words_are_the_dataset_s_own_everywhere():
    grammar = propose.QASPER_GRAMMAR
    assert (grammar.outer_member, grammar.inner_member) == ("section_index", "paragraph_index")
    row_item = grammar.schema()["properties"]["rows"]["items"]
    assert set(row_item["properties"]) == {"kind", "surface", "section_index", "paragraph_index"}
    assert row_item["properties"]["kind"]["enum"] == ["entity", "quantity"]
    relation_enum = grammar.schema()["properties"]["relations"]["items"]["properties"]["kind"]
    assert relation_enum["enum"] == ["same_entity"]
    template = grammar.template()
    assert "paragraph_index" in template and "session" not in template
    # The LongMemEval view is untouched by the second one.
    assert propose.PROPOSAL_SCHEMA == propose.LONGMEM_GRAMMAR.schema()


def test_the_two_views_are_two_proposers_so_neither_adopts_the_other_s_segments():
    longmem_side = propose.light_tier_proposer(propose.LONGMEM_GRAMMAR)
    qasper_side = propose.light_tier_proposer(propose.QASPER_GRAMMAR)
    assert longmem_side.identity_hash != qasper_side.identity_hash
    assert longmem_side.extractor_id("longmem") != qasper_side.extractor_id("qasper")
    assert propose.request_key("p", longmem_side) != propose.request_key("p", qasper_side)


def test_a_view_outside_the_closed_grammar_cannot_be_declared():
    with pytest.raises(ValueError):
        propose.ProposalGrammar(dataset="x", outer="a", inner="b", row_kinds=("belief",),
                                relation_kinds=())
    with pytest.raises(ValueError):
        propose.ProposalGrammar(dataset="x", outer="a", inner="b", row_kinds=("entity",),
                                relation_kinds=("causes",))


def test_the_qasper_ingester_folds_the_proposer_into_its_own_extractor_id():
    """B.28's key on the QASPER side (ingest/qasper.py: extractor_for_the_key)."""
    from atlas.record.diff import item_bytes_cache_key
    from atlas.record.ingest import qasper

    proposer = propose.light_tier_proposer(propose.QASPER_GRAMMAR)
    raw = b'{"title": "a paper"}'
    plain = item_bytes_cache_key(raw, qasper.EXTRACTOR_ID_A, "sha256:declaration")
    composite = f"{qasper.EXTRACTOR_ID_A}+{proposer.extractor_id('qasper')}"
    with_proposer = item_bytes_cache_key(raw, composite, "sha256:declaration")
    assert with_proposer != plain
    assert with_proposer == item_bytes_cache_key(raw, composite, "sha256:declaration")


def test_the_qasper_ingester_fails_closed_when_the_rung_is_declared_with_no_proposer():
    from atlas.record.ingest import qasper
    with pytest.raises(propose.ProposerUnreachable):
        qasper.ingest(papers=1, rungs="abc", proposer=None)


def test_the_module_registers_no_witness_predicate_of_its_own():
    # The admission predicates are the ones that were already there; a rung that could add one
    # that trusts the model is the failure this rung exists to avoid.
    from atlas.record import witness
    before = set(witness.PREDICATES)
    import importlib
    importlib.reload(propose)
    assert set(witness.PREDICATES) == before
