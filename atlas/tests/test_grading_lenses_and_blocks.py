"""Tests THIS packet wrote for src/atlas/grading/. Run with a unique --basetemp.

    scripts/laplace-python -m pytest atlas/tests/test_grading_lenses_and_blocks.py \
        --basetemp=/tmp/pytest-grading-l1 -q

They are falsifiable rather than decorative: each one names the clause it carries, several
MUTATE the input and assert the verdict flips, and the refusals are asserted by NAME.
"""

from __future__ import annotations

import sys
from dataclasses import replace

import pytest
import torch

from atlas.grading import blocks as block_module
from atlas.grading.blocks import descend, evaluate_blocking, evaluate_cover
from atlas.grading.face import FaceRefusal, carrier_for_type
from fold_oracle import (fold_faces, fold_is_closed, leaf_face,  # the deleted A.34 fold,
                         scalar_survivors)                       # kept as the test oracle
from atlas.grading.generator import build_lens_generator
from atlas.grading.lens import LensDeclaration, LensRefusal, Question
from atlas.grading.lenses import engine_lenses, toy_lens
from atlas.grading.lifted import LiftViolation, forbidden_import_check, lift_receipt
from atlas.record.ingest import engine_rows, toy

pytestmark = pytest.mark.skipif(not torch.cuda.is_available(), reason="the numeric core is GPU")



# PACKET J2-INTEGRATION deleted ``grading/node.py`` (the per-node-face Conceptric path
# atlas.interface/2 supersedes: "no face is stored on a node") and ``grading/measure.py``
# (a measurement script, deleted into the front door's receipts). The tests of those two
# modules went with them - 20 of this file's tests: toy_graded, test_generator_is_integer_and_pi_is_derived, test_b16_two_routes_agree, test_dropping_one_witness_changes_the_generator, test_b36_is_a_cardinality_by_two_routes, test_no_real_weight_can_enter_s, test_up_down_are_identities_on_content_addresses, test_up_refuses_a_flat_bag, test_down_refuses_an_unresolvable_handle, test_the_node_carries_exactly_five_things, test_mutating_the_finer_graph_moves_the_address, test_known_answers_hold, test_the_mode_batch_schedule_does_not_change_the_accepted_set, test_membership_is_a_cover_and_nothing_is_left_uncovered, mention_fires, test_the_built_membership_is_a_membership_the_two_tests_accepted, test_a_refused_enlargement_is_named_with_its_test_column_and_margin, test_the_tagged_domain_reproduces_the_partition_test_exactly, test_every_declared_carrier_row_lands_in_exactly_one_named_bucket, test_a_zero_is_a_miss_when_an_unseated_row_satisfies_the_condition.
# What their A.33/B.36 content now needs is named in the packet report's residuals: the
# UP/DOWN identities on content addresses and "the node carries exactly five things" have
# to be re-asserted against the PERSISTED tree (grading/tree.py), which is a contract-side
# check the J2-CONTRACT packet owns, not a silent loss.
@pytest.fixture(scope="module")
@pytest.fixture(scope="module")
def engine():
    ingestion = engine_rows.ingest()
    return ingestion, engine_lenses(ingestion, ingestion.fold.supersession_depth)


# --------------------------------------------------------------------------- A.35
def test_a35b_modules_are_refused_by_name():
    assert forbidden_import_check()["verdict"] == "clean"
    receipt = lift_receipt()
    assert set(receipt["lifted"]) == {"section_calculus", "section_block_operator"}
    sys.modules["section_ingest"] = object()          # the cosine, smuggled in
    try:
        with pytest.raises(LiftViolation):
            forbidden_import_check()
    finally:
        del sys.modules["section_ingest"]


# --------------------------------------------------------------------------- B.16, B.18, B.19
def test_face_fold_rules_and_refusals():
    types = {"id": "dict_utf8", "status": "enum", "date": "date", "spans": "span_ref"}
    left = leaf_face({"id": "a", "status": "open", "date": "2026-01-01", "spans": ["s1"]}, types)
    right = leaf_face({"id": "a", "status": "done", "date": "2026-03-04", "spans": ["s2"]}, types)
    folded, drops = fold_faces([left, right])
    assert scalar_survivors(folded) == {"id": "a"}          # SCALAR survives as a singleton
    assert folded["date"] == {"carrier": "date", "lo": "2026-01-01", "hi": "2026-03-04"}
    assert folded["status"]["counts"] == {"done": 1, "open": 1}
    assert folded["spans"]["values"] == ["s1", "s2"]
    assert drops["scalar_fields_that_did_not_survive"] == []
    third = leaf_face({"id": "b", "status": "open", "date": "2025-01-01", "spans": []}, types)
    folded, drops = fold_faces([left, right, third])
    assert drops["scalar_fields_that_did_not_survive"][0]["field"] == "id"
    assert fold_is_closed([left, right, third], 2) is True
    with pytest.raises(FaceRefusal) as caught:
        fold_faces([])
    assert caught.value.refusal == "EMPTY-FOLD"
    with pytest.raises(FaceRefusal) as caught:
        leaf_face({"x": 1}, {"x": "float64"})
    assert caught.value.refusal == "FACE-FIELD-KIND-NOT-ADMITTED"
    with pytest.raises(FaceRefusal) as caught:
        leaf_face({}, {"id": "dict_utf8"})
    assert caught.value.refusal == "FACE-FIELD-MISSING"
    with pytest.raises(FaceRefusal) as caught:
        fold_faces([{"f": {"carrier": "scalar", "values": ["a"]}},
                    {"f": {"carrier": "date", "lo": "x", "hi": "x"}}])
    assert caught.value.refusal == "FACE-FIELD-KIND-CONFLICT"


# --------------------------------------------------------------------------- the lens itself
def test_lens_refusals_by_name(engine):
    ingestion, lenses = engine
    entity = lenses["entity"]
    with pytest.raises(LensRefusal) as caught:
        replace(entity, counted_relation_kinds=("no_such_kind",)).check_against(
            ingestion.declaration)
    assert caught.value.refusal == "LENS-RELATION-KIND-UNDECLARED"
    with pytest.raises(LensRefusal) as caught:
        replace(entity, counted_relation_kinds=(), derived_relations=())
    assert caught.value.refusal == "LENS-NO-COUNTED-RELATION-KIND"
    with pytest.raises(LensRefusal) as caught:
        replace(entity, walk_horizon=0)
    assert caught.value.refusal == "LENS-WALK-HORIZON-NOT-POSITIVE"
    with pytest.raises(LensRefusal) as caught:
        replace(entity, questions=(Question("q", "t", "status", "work_order", 0.1, ""),))
    assert caught.value.refusal == "LENS-ANSWER-PRECISION-UNDERIVED"
    bad = replace(entity, questions=(
        Question("q", "t", "not_a_column", "work_order", 0.1, "derived"),))
    with pytest.raises(LensRefusal) as caught:
        bad.check_against(ingestion.declaration)
    assert caught.value.refusal == "LENS-ANSWER-COLUMN-UNDECLARED"


def test_three_lenses_over_one_record_differ(engine):
    """The point of the packet: the row kinds are the same, the gradings are not."""
    ingestion, lenses = engine
    carriers, hashes = {}, set()
    for name, lens in lenses.items():
        generator = build_lens_generator(ingestion, lens)
        carriers[name] = (int(generator.carrier_global_rows.numel()),
                          len(generator.components))
        hashes.add(lens.lens_hash())
    assert len(hashes) == 3
    assert len({value for value in carriers.values()}) == 3
    assert all(set(lens.carrier_row_kinds) == {"work_order", "verdict"}
               for lens in lenses.values())


# --------------------------------------------------------------------------- acceptance
def test_a_deliberately_impure_block_is_refused_with_its_column(engine):
    """Force the whole component into ONE block: TEST 1 must refuse it and name the column."""
    ingestion, lenses = engine
    lens = lenses["entity"]
    generator = build_lens_generator(ingestion, lens)
    component = max(generator.components, key=lambda c: c.n)
    columns = block_module.build_task_columns(ingestion, lens, component)
    tolerances = block_module.derive_tolerances(lens, columns)
    everything = torch.zeros(component.n, dtype=torch.int64, device=component.device)
    verdict = evaluate_blocking(component, everything, columns, tolerances)
    assert not bool(verdict.accepted[0])
    refusals = verdict.refusals(columns)
    assert refusals and refusals[0].test == "A.11-observable-adequacy"
    assert refusals[0].column in columns.names
    assert refusals[0].margin > 0


def test_singletons_pass_test_one_exactly(engine):
    ingestion, lenses = engine
    lens = lenses["entity"]
    generator = build_lens_generator(ingestion, lens)
    component = max(generator.components, key=lambda c: c.n)
    columns = block_module.build_task_columns(ingestion, lens, component)
    tolerances = block_module.derive_tolerances(lens, columns)
    atoms = torch.arange(component.n, dtype=torch.int64, device=component.device)
    verdict = evaluate_blocking(component, atoms, columns, tolerances)
    assert float(verdict.observable_worst.max()) < 1e-12
    assert bool(verdict.passes_observable.all())


def test_tolerances_are_derived_not_set(engine):
    ingestion, lenses = engine
    lens = lenses["entity"]
    generator = build_lens_generator(ingestion, lens)
    component = max(generator.components, key=lambda c: c.n)
    columns = block_module.build_task_columns(ingestion, lens, component)
    tolerances = block_module.derive_tolerances(lens, columns)
    assert 0.0 < tolerances.b_min <= 1.0
    assert abs(tolerances.chi2_max - (1.0 / tolerances.b_min - 1.0)) < 1e-9
    for index, name in enumerate(columns.names):
        kind, column = name.split(".", 1)
        expected = lens.precision_of(kind, column) / (tolerances.chi2_max ** 0.5)
        assert abs(float(tolerances.tau_observable[index]) - expected) < 1e-15
    assert tolerances.walk_horizon == lens.walk_horizon
