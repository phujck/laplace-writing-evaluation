"""LongMemEval and the engine's own ledgers at rung (a), the status fold, and O(diff).

These tests read the real files. Each is skipped by name when its source is absent, so a clone
without the 277 MB LongMemEval cache reports a skip rather than a green suite that checked
nothing.
"""

from __future__ import annotations

import pytest
import torch

from atlas.record import diff
from atlas.record.ingest import engine_rows, longmem
from atlas.record.json_spans import iter_array_items

cuda = pytest.mark.skipif(not torch.cuda.is_available(),
                          reason="the record layer's numeric core is CUDA-only by policy")
have_longmem = pytest.mark.skipif(not longmem.DATASET_PATH.is_file(),
                                  reason="LongMemEval-S cache absent")
have_ledgers = pytest.mark.skipif(not engine_rows.WORK_ORDERS_PATH.is_file(),
                                  reason="engine ledgers absent")


@pytest.fixture(scope="module")
def longmem_small():
    return longmem.ingest(histories=3)


@pytest.fixture(scope="module")
def ledgers():
    return engine_rows.ingest()


# --------------------------------------------------------------------------- LongMemEval
@cuda
@have_longmem
def test_record_longmem_declared_date_rule_strips_the_weekday():
    import datetime as dt
    assert longmem.parse_session_date("2023/05/20 (Sat) 02:21") == dt.datetime(2023, 5, 20,
                                                                               2, 21)


@cuda
@have_longmem
def test_record_longmem_turn_content_is_a_span_not_a_copy(longmem_small):
    turns = longmem_small.store.table("turn")
    assert len(turns) > 0
    assert "content" not in turns.spec.columns, "B.1: the row stores no copy of its text"
    span_ord = int(turns.column("content_span")[0])
    handle, start, end = longmem_small.spans.address(span_ord)
    raw = longmem_small.blobs.read(handle, start, end)
    assert raw.startswith(b'"') and raw.endswith(b'"'), "the span addresses the JSON string"


@cuda
@have_longmem
def test_record_longmem_rung_a_anchors_are_identifiers_only(longmem_small):
    """The measurement's premise, asserted: no entity exists at rung (a)."""
    vocabulary = set(longmem_small.anchors.vocabulary)
    sessions = set(longmem_small.store.table("session").decode("session_id"))
    questions = set(longmem_small.store.table("question").decode("question_id"))
    assert vocabulary == sessions | questions, (
        "at rung (a) the anchor vocabulary is exactly the container's identifiers")


@cuda
@have_longmem
def test_record_longmem_relations_are_intra_session_only(longmem_small):
    store = longmem_small.store
    turns = store.table("turn")
    follows = longmem_small.relations.kind("follows")
    local = store.local_of_global("turn")
    session_index = turns.column("session_index")
    src = session_index.index_select(0, local.index_select(0, follows.src))
    dst = session_index.index_select(0, local.index_select(0, follows.dst))
    assert bool((src == dst).all()), "follows never leaves the session it starts in"
    assert len(longmem_small.relations.kind("in_session")) == len(turns), (
        "every turn is in exactly one session")


@cuda
@have_longmem
def test_record_longmem_gold_never_enters_the_record(longmem_small):
    for kind, table in longmem_small.store.tables.items():
        columns = set(table.spec.columns)
        assert not columns & {"answer", "answer_session_ids", "has_answer"}, (
            f"{kind} carries a gold field; the evaluator's data is not in the record")


# --------------------------------------------------------------------------- engine ledgers
@cuda
@have_ledgers
def test_record_engine_rows_enum_vocabularies_are_measured_not_hand_set():
    vocabularies = engine_rows.measure_vocabularies()
    assert len(vocabularies.work_order_status) > 1
    assert vocabularies.work_order_status == tuple(sorted(vocabularies.work_order_status))
    assert all(h.startswith("sha256:") for h in vocabularies.measured_from), (
        "the vocabulary's provenance is the blobs it was measured from")


@cuda
@have_ledgers
def test_record_engine_rows_unresolvable_link_becomes_a_row_not_a_dropped_link(ledgers):
    dangling = ledgers.store.table("dangling_reference")
    assert len(dangling) > 0, "B.32: an unresolvable value becomes a dangling_reference ROW"
    fields = set(dangling.spec.columns)
    assert {"owner_id", "field", "raw_value"} <= fields
    counted = sum(ledgers.coverage["dangling_by_field"].values())
    assert counted == len(dangling), "every dangling row is counted in the coverage statement"
    assert ledgers.coverage["absent_by_field"], (
        "B.35: an absent link is counted separately from a dangling one")


@cuda
@have_ledgers
def test_record_engine_rows_fail_closed_on_an_unparseable_typed_date(ledgers):
    receipt = ledgers.store.receipt()
    assert receipt["refused_proposals"] > 0
    assert receipt["refused_by_predicate"]["json_member_equals@v1"] == \
        receipt["refused_proposals"]
    assert ledgers.coverage["malformed_typed_field"], (
        "a member present but unparseable by its declared rule refuses the row")


@cuda
@have_ledgers
def test_record_engine_rows_status_fold_is_latest_wins_and_flags_conflicts(ledgers):
    fold = ledgers.fold
    assert len(fold.entity_ids) > 0
    assert len(fold.entity_ids) == len(fold.status) == len(fold.winner_row)
    kinds = {conflict["conflict"] for conflict in fold.conflicts}
    assert "supersedes-older-than-superseded" in kinds, (
        "the explicit supersedes link beats the timestamp, and the disagreement is flagged")
    work = ledgers.store.table("work_order")
    statuses = work.decode("status")
    globals_ = work.global_ordinals.tolist()
    for entity, status, winner in zip(fold.entity_ids, fold.status, fold.winner_row):
        assert statuses[globals_.index(winner)] == status, (
            f"the folded status of {entity} is the winning line's own status")


@cuda
@have_ledgers
def test_record_engine_rows_link_relations_carry_both_line_spans(ledgers):
    targets = ledgers.relations.kind("targets")
    assert len(targets) > 0
    witnesses = targets.witnesses_of(0)
    assert witnesses.numel() == 2, "B.32: the witness is the PAIR of line spans"


# --------------------------------------------------------------------------- O(diff)
@cuda
@have_longmem
def test_record_diff_unchanged_input_remints_nothing(longmem_small):
    raws = [raw for _, _, raw in iter_array_items(longmem.DATASET_PATH, limit=4)]
    before = (longmem_small.store.row_count, len(longmem_small.relations),
              len(longmem_small.spans), len(longmem_small.blobs))
    first = diff.apply_case(longmem_small, raws[3])
    assert not first.cache_hit and first.row_ordinals
    after = (longmem_small.store.row_count, len(longmem_small.relations),
             len(longmem_small.spans), len(longmem_small.blobs))
    second = diff.apply_case(longmem_small, raws[3])
    assert second.cache_hit and second.touched_count == 0
    assert second.blobs == () and second.edges == {} and second.posting_surfaces == ()
    assert after == (longmem_small.store.row_count, len(longmem_small.relations),
                     len(longmem_small.spans), len(longmem_small.blobs)), (
        "an unchanged input re-mints nothing: no blob, no span, no row, no edge")


@cuda
@have_longmem
def test_record_diff_touches_only_the_item_and_its_neighbourhood(longmem_small):
    raws = [raw for _, _, raw in iter_array_items(longmem.DATASET_PATH, limit=6)]
    before_rows = longmem_small.store.row_count
    touched = diff.apply_case(longmem_small, raws[4])
    assert min(touched.row_ordinals) >= before_rows, "no existing row is rewritten"
    assert touched.touched_count == len(touched.row_ordinals) + \
        len(touched.neighbour_ordinals), "B.29: touched_count is 1 + |N(x)| for the item"
    assert len(touched.blobs) == 1, "B.33: one haystack is one blob"
    overlap = set(touched.neighbour_ordinals) & set(touched.row_ordinals)
    assert not overlap, "N(x) excludes x itself"


@cuda
@have_longmem
def test_record_diff_change_locality_measures_both_cache_keys(longmem_small):
    raws = [raw for _, _, raw in iter_array_items(longmem.DATASET_PATH, limit=1)]
    measured = diff.measure_change_locality(longmem_small, raws[0],
                                            ("user", "One more thing."))
    # B.28 was AMENDED by packet F2/E1 to the key this test's second assertion already measured,
    # so the container-keyed count is reported under a name that says it is the superseded arm.
    assert measured["b28_container_keyed_hits_before_the_amendment"] == 0, (
        "the superseded key contained the container's hash, so an edited blob missed for "
        "every item - the defect the amendment removes")
    assert measured["item_keyed_hits"] == measured["items_in_changed_blob"] - 1, (
        "keyed on the item's own bytes, only the appended turn misses")
