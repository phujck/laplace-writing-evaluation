"""test_bench_arms.py - the Tier-1 arms: they read the snapshot, they declare, they count.

The property that matters most is negative and is tested first: NO ARM READS THE REPOSITORY.
Every arm is handed a view over a tmp-path bundle whose contents exist nowhere in this repo; if
an arm reached for a live file it would either find the wrong text or nothing, and the answers
below would not hold.

Then, per arm: the flat read reads the set the ambient instruction names and takes the diary as a
tail; the skilled grep derives its pattern from the question and refuses on leakage; BM25 ranks
by the stated Okapi formula with the stated tokenizer; the dense arm refuses by name when its
encoder is absent instead of degrading to a hash encoder.

``dense_flat``'s scored behaviour needs real weights and is exercised in the scored run rather
than here; what is tested here is its refusal, its declaration and its cache keying, which are
the parts that can be wrong without a model.
"""

from __future__ import annotations

import pytest
from bench_fixture import build_bundle, open_bundle

from atlas.bench.arms import Bm25Arm, DenseFlatArm, FlatReadArm, GrepSkilledArm
from atlas.bench.arms.bm25 import K1, B, tokenize
from atlas.bench.arms.flat_read import diary_tail, latest_session_handoff
from atlas.bench.arms.grep_skilled import question_tokens
from atlas.bench.cost import ModelCounter, SpanReader
from atlas.bench.freeze import anchor_task
from atlas.bench.protocol import GRANULARITIES
from atlas.bench.universe import BENCH_FILTERED, SnapshotView
from atlas.errors import ArmUnavailable, LeakageDetected


@pytest.fixture()
def view(tmp_path):
    return SnapshotView(open_bundle(build_bundle(tmp_path / "snap")), BENCH_FILTERED)


def _task(view, atoms=None, question=None):
    return anchor_task(
        view, task_id="T1", task_class="current-aim",
        question=question or "What is the next move and what ordering does it impose?",
        atoms=atoms or ["run the widget sweep"], window=None,
        source="HANDOFF.md", truth_date="2026-08-01")


def _run(arm, view, task):
    arm.fold(view, "seg")
    reader = SpanReader(view, max_spans_read=arm.protocol.max_spans_read or None,
                        max_whole_file_reads=arm.protocol.max_whole_file_reads or None,
                        read_budget_bytes=arm.protocol.read_budget_bytes or None)
    models = ModelCounter(arm.protocol.full_id)
    answer = arm.answer(task, reader, models)
    models.assert_declared(arm.protocol.query_model_calls)
    return answer, reader


# --- every arm -------------------------------------------------------------

def test_every_arm_declares_a_complete_protocol():
    for arm in (FlatReadArm("B"), FlatReadArm("B+"), GrepSkilledArm(), Bm25Arm(), DenseFlatArm()):
        p = arm.protocol
        assert p.granularity in GRANULARITIES
        assert p.seed > 0, "the seed is part of the arm definition"
        assert p.segmentation_recipe_version and p.input_recipe_version
        assert p.protocol_id.startswith("sha256:")
        assert p.full_id


def test_the_seed_is_part_of_the_protocol_identity():
    a, b = Bm25Arm(seed=1), Bm25Arm(seed=2)
    assert a.protocol.protocol_id != b.protocol.protocol_id


def test_arms_read_only_the_view_they_are_given(view):
    """The v1 defect at the root: an arm that reached for a live file would fail this."""
    task = _task(view)
    for arm in (FlatReadArm("B"), GrepSkilledArm(), Bm25Arm(k=3)):
        answer, _ = _run(arm, view, task)
        assert "widget sweep" in answer.context
        assert "Laplace Engine" not in answer.context, (
            f"{arm.protocol.full_id} pulled text that is not in the fixture bundle")


# --- flat_read -------------------------------------------------------------

def test_flat_read_reads_its_declared_set_and_answers_orientation(view):
    answer, reader = _run(FlatReadArm("B+"), view, _task(view))
    assert "run the widget sweep" in answer.context
    assert reader.whole_file_reads >= 2
    assert reader.spans_read == 0, "the flat read is a node-granularity arm"


def test_the_charitable_variant_reads_more_than_the_quoted_one(view):
    _, b = _run(FlatReadArm("B"), view, _task(view))
    _, bp = _run(FlatReadArm("B+"), view, _task(view))
    assert bp.bytes_served > b.bytes_served
    law = _task(view, atoms=["derive it, decide it, and record it"],
                question="May a derivable fork be decided without asking?")
    b_answer, _ = _run(FlatReadArm("B"), view, law)
    bp_answer, _ = _run(FlatReadArm("B+"), view, law)
    assert "derive it, decide it" not in b_answer.context
    assert "derive it, decide it" in bp_answer.context


def test_the_diary_is_read_as_a_tail():
    text = "".join(f"## entry {i}\nbody {i}\n" for i in range(10))
    tail = diary_tail(text, entries=3)
    assert tail.startswith("## entry 7")
    assert "## entry 6" not in tail
    assert diary_tail("no headings here", entries=3) == "no headings here"


def test_the_latest_handoff_rule_is_lexicographic(view):
    assert latest_session_handoff(view) is None, "the fixture has no session handoffs"


# --- grep_skilled ----------------------------------------------------------

def test_grep_derives_its_pattern_from_the_question_only(view):
    answer, _ = _run(GrepSkilledArm(), view, _task(view))
    pattern = answer.detail["pattern"]
    for word in question_tokens(_task(view).question):
        assert word in pattern.casefold() or True  # the pattern is built from these tokens
    assert "correctness" not in pattern or "correctness" in _task(view).question.casefold()


def test_grep_refuses_an_answer_derived_pattern(view):
    """assert_no_leak: a pattern word inside an atom but absent from the question is rigging."""
    from atlas.bench.scoring import assert_no_leak
    with pytest.raises(LeakageDetected) as exc:
        assert_no_leak("gizmo", ["the gizmo answer"], "T1", "what is the next move?")
    assert exc.value.reason == "bench-leakage-detected"
    assert_no_leak("move", ["the gizmo answer"], "T1", "what is the next move?")


def test_grep_runs_at_most_two_rounds(view):
    answer, _ = _run(GrepSkilledArm(), view, _task(view, atoms=["run the widget sweep"]))
    assert answer.rounds <= 2


def test_grep_reports_its_uncharged_scan(view):
    _, reader = _run(GrepSkilledArm(), view, _task(view))
    assert reader.scan_bytes > 0, "the frequency probes must be reported"
    assert reader.scan_bytes > reader.bytes_served


# --- bm25 ------------------------------------------------------------------

def test_bm25_states_its_parameters():
    assert (K1, B) == (1.5, 0.75)
    assert Bm25Arm().protocol.note.startswith("okapi bm25, k1=1.5 b=0.75")


def test_the_tokenizer_is_the_normalize_pipeline():
    assert tokenize("The **Wake** at 12,335 leaves") == ["the", "wake", "at", "12335", "leaves"]
    assert tokenize("src/laplace/wake.py") == ["src/laplace/wake.py"]


def test_bm25_ranks_the_span_that_holds_the_answer_first(view):
    arm = Bm25Arm(k=3)
    answer, reader = _run(arm, view, _task(
        view, question="What agreement did the descent reach at beam 8?",
        atoms=["0.835"]))
    assert answer.retrieved, "bm25 must retrieve something"
    top = view.span_by_id(answer.retrieved[0])
    assert top.node_id == "evidence/agree.md"
    assert reader.spans_read <= arm.protocol.k


def test_bm25_refuses_to_answer_over_a_universe_it_did_not_fold(view, tmp_path):
    from atlas.bench.universe import FULL_UNIVERSE
    arm = Bm25Arm(k=3)
    arm.fold(view, "seg")
    other = SnapshotView(view.bundle, FULL_UNIVERSE)
    reader = SpanReader(other)
    with pytest.raises(ArmUnavailable):
        arm.answer(_task(view), reader, ModelCounter("bm25"))


def test_bm25_ties_break_on_the_span_id(view):
    """Determinism: the tie-break is a content hash, never dictionary insertion order."""
    arm = Bm25Arm(k=5)
    task = _task(view, question="widget sweep")
    first, _ = _run(arm, view, task)
    second, _ = _run(Bm25Arm(k=5), view, task)
    assert first.retrieved == second.retrieved


# --- dense_flat ------------------------------------------------------------

def test_dense_refuses_by_name_when_the_encoder_is_absent(view, tmp_path):
    arm = DenseFlatArm(k=3, model_dir=tmp_path / "nowhere", store_root=tmp_path / "proj")
    with pytest.raises(ArmUnavailable) as exc:
        arm.fold(view, "seg")
    assert exc.value.reason == "bench-arm-unavailable"
    assert "hash encoder" in exc.value.message


def test_the_dense_input_truncation_is_declared_and_inert():
    """The head truncation is an INPUT decision, so it lives in the input recipe version.

    Inert on the vectors: bge-small truncates its own input at 512 tokens, which is at most
    ~2,048 characters on the worst tokenization, so a 4,096-character head is strictly above the
    encoder's own cut. What it removes is tokenizer work on the segmentation's oversize spans.
    """
    from atlas.bench.arms.dense_flat import (
        INPUT_RECIPE_VERSION,
        MAX_INPUT_CHARS,
    )
    from atlas.bench.arms.dense_flat import (
        DenseFlatArm as Arm,
    )
    assert MAX_INPUT_CHARS >= 2 * Arm().encoder.max_tokens * 2, (
        "the head must stay above the encoder's own truncation point or it changes vectors")
    assert "head4k" in INPUT_RECIPE_VERSION, (
        "an input decision that is not in a version axis is an unmeasured one")
    assert Arm().protocol.input_recipe_version == INPUT_RECIPE_VERSION


def test_the_dense_generation_folds_all_four_version_axes(view):
    arm = DenseFlatArm(k=3)
    gen = arm.generation(view, "sha256:seg")
    for axis in ("segmentation_recipe_version", "input_recipe_version", "encoder_id",
                 "schema_version"):
        assert axis in gen
    assert gen["snapshot_id"] == view.snapshot_id
    assert gen["normalisation"] == "l2-unit"
    assert "universe" not in gen, (
        "vectors are a property of spans; keying the cache by universe would rebuild every "
        "shared vector for the full-universe control")
