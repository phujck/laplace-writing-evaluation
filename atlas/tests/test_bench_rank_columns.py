"""test_bench_rank_columns.py - the Phase 3 rank columns are ADDITIVE, and that is what is tested.

Both Phase 2 verdict rows asked for a rank-aware criterion with the *frozen correctness definition
unchanged*. "Unchanged" is a claim about code that is easy to make and easy to break, so the first
test here is the negative one: adding the columns moves no ``correct`` value and no cost number.

The rest pin the semantics, because the two columns are easy to confuse:

  ``ground_truth_rank``  where the EVIDENCE first appears in the served list.
  ``first_hit_rank``     where the ANSWER first COMPLETES - the shortest satisfying prefix.

They differ exactly when a task needs several atoms that live in different spans, which is the
case the character-offset column (``first_hit_offset``) cannot distinguish at all.
"""

from __future__ import annotations

import pytest
from bench_fixture import build_bundle, open_bundle

from atlas.bench.cost import ModelCounter, SpanReader
from atlas.bench.freeze import anchor_task
from atlas.bench.runner import rank_columns
from atlas.bench.scoring import score
from atlas.bench.universe import BENCH_FILTERED, SnapshotView


@pytest.fixture()
def view(tmp_path):
    return SnapshotView(open_bundle(build_bundle(tmp_path / "snap")), BENCH_FILTERED)


def _task(view, atoms=None, window=None):
    return anchor_task(
        view, task_id="T1", task_class="current-aim",
        question="What is the next move?",
        atoms=atoms or ["run the widget sweep"], window=window,
        source="HANDOFF.md", truth_date="2026-08-01")


def _span_holding(view, needle: str):
    for span in view.leaf_spans:
        if needle.casefold() in view.span_text(span).casefold():
            return span
    raise AssertionError(f"no span holds {needle!r}")


def _span_without(view, needle: str):
    for span in view.leaf_spans:
        if needle.casefold() not in view.span_text(span).casefold():
            return span
    raise AssertionError("every span holds the needle")


# --- the additive property -------------------------------------------------

def test_an_unranked_arm_gets_null_and_never_zero(view):
    """A fixed read set has no ranking; reporting 0 or 1 would invent one."""
    assert rank_columns(view, _task(view), []) == (None, None)


def test_the_columns_do_not_touch_the_frozen_scorer(view):
    """The scorer's verdict over the same text is identical whether or not ranks are computed."""
    task = _task(view)
    span = _span_holding(view, "run the widget sweep")
    text = view.span_text(span)
    before = score(text, task.atoms, task.window)
    rank_columns(view, task, [span.span_id])
    assert score(text, task.atoms, task.window) == before


def test_computing_ranks_charges_no_bytes_to_the_arm(view):
    """The rank pass reads the VIEW, never the SpanReader - otherwise it would move every cost."""
    task = _task(view)
    reader = SpanReader(view)
    span = _span_holding(view, "run the widget sweep")
    reader.read_span(span)
    touched_before = reader.snapshot_counters()["tokens_touched"]
    rank_columns(view, task, [s.span_id for s in view.leaf_spans[:10]])
    assert reader.snapshot_counters()["tokens_touched"] == touched_before


# --- the semantics ---------------------------------------------------------

def test_evidence_at_rank_one_is_rank_one(view):
    task = _task(view)
    hit = _span_holding(view, "run the widget sweep")
    assert rank_columns(view, task, [hit.span_id]) == (1, 1)


def test_evidence_below_a_miss_reports_its_real_rank(view):
    task = _task(view)
    miss = _span_without(view, "run the widget sweep")
    hit = _span_holding(view, "run the widget sweep")
    gt, first = rank_columns(view, task, [miss.span_id, hit.span_id])
    assert (gt, first) == (2, 2)


def test_the_two_columns_separate_when_atoms_live_in_different_spans(view):
    """Evidence appears at rank 1; the answer only COMPLETES once the second atom arrives."""
    first_atom, second_atom = "run the widget sweep", "the old aim was to polish the gadget"
    task = _task(view, atoms=[first_atom, second_atom])
    a = _span_holding(view, first_atom)
    b = _span_holding(view, second_atom)
    assert a.span_id != b.span_id
    gt, first = rank_columns(view, task, [a.span_id, b.span_id])
    assert gt == 1, "the first atom is served at rank 1"
    assert first == 2, "the task does not complete until rank 2"


def test_evidence_never_served_is_null_for_ground_truth_rank(view):
    task = _task(view)
    misses = [_span_without(view, "run the widget sweep").span_id]
    assert rank_columns(view, task, misses) == (None, None)


def test_supplied_texts_are_authoritative_for_non_span_arms(view):
    """RAPTOR ranks cluster summaries and the incumbent ranks nodes: neither is a view span.

    Without the supplied-text channel both would be scored against empty strings and reported as
    never retrieving their own evidence - an instrument bug that would read as a result.
    """
    task = _task(view)
    ids = ["raptor:r.0", "raptor:r.1"]
    assert rank_columns(view, task, ids) == (None, None), "unresolvable ids carry no evidence"
    gt, first = rank_columns(view, task, ids,
                             ["nothing relevant here", "the plan is to run the widget sweep"])
    assert (gt, first) == (2, 2)


def test_a_window_constrained_task_completes_only_inside_the_window(view):
    """``first_hit_rank`` inherits the frozen scorer's window, rather than reimplementing it."""
    atoms = ["run the widget sweep", "the old aim was to polish the gadget"]
    a = _span_holding(view, atoms[0])
    b = _span_holding(view, atoms[1])
    wide = _task(view, atoms=atoms, window=None)
    assert rank_columns(view, wide, [a.span_id, b.span_id])[1] == 2
    tight = _task(view, atoms=atoms, window=5)
    assert rank_columns(view, tight, [a.span_id, b.span_id])[1] is None


def test_rows_carry_both_columns_for_every_arm(view):
    """The row schema is the contract the summary reads; a missing key is a silent null."""
    from atlas.bench.arms import Bm25Arm
    from atlas.bench.freeze import freeze_bundle
    from atlas.bench.runner import run_bundle

    task = _task(view)
    bundle = freeze_bundle(view, "sha256:" + "a" * 64, [task])
    arm = Bm25Arm(k=3, seed=1)
    result = run_bundle(bundle, view, [arm], segmentation_id="seg", verify=False)
    for row in result.rows:
        assert "ground_truth_rank" in row
        assert "first_hit_rank" in row


def test_the_rank_columns_are_inside_the_determinism_digest(view):
    """A digest that ignored the new columns would let them drift without anything noticing."""
    from atlas.bench.runner import _deterministic_rows

    row = {"task": "T1", "arm": "a", "correct": True, "latency_ms": 1.0,
           "ground_truth_rank": 3, "first_hit_rank": 4}
    stripped = _deterministic_rows([row])[0]
    assert stripped["ground_truth_rank"] == 3
    assert stripped["first_hit_rank"] == 4
    assert "latency_ms" not in stripped


def test_the_counting_reader_is_untouched_by_a_model_counter(view):
    """Guard against the rank pass acquiring a model call by accident."""
    models = ModelCounter("test")
    rank_columns(view, _task(view), [s.span_id for s in view.leaf_spans[:5]])
    models.assert_declared(0)


# --- the served-rank TABLE: three states, and the uneven-denominator repair ----
#
# The Phase 3 judge (SEV-20260801-atlas-phase3-r1, D2) found the first version of this table
# comparing a 17-item served list against 10-item ones under a column headed "evidence in top-k".
# The repair is display-only - no scored row may move - so it is tested at the summary layer,
# over synthetic rows, where the three states can each be constructed exactly.

def _row(arm, task, correct=False, gt=None, hit=None, retrieved=()):
    return {"arm": arm, "task": task, "class": "c", "correct": correct,
            "ground_truth_rank": gt, "first_hit_rank": hit, "retrieved": list(retrieved)}


def test_an_arm_that_returns_no_list_is_unranked():
    from atlas.bench.summary import served_ranks

    cell = served_ranks([_row("flat", "T1"), _row("flat", "T2")])["flat"]
    assert cell["rank_state"] == "unranked"
    assert cell["ranks"] is False
    assert cell["served_len_median"] == 0


def test_an_arm_that_ranks_and_resolves_is_instrumented():
    from atlas.bench.summary import served_ranks

    rows = [_row("bm25", "T1", True, gt=1, hit=1, retrieved="abcdefghij"),
            _row("bm25", "T2", False, gt=None, hit=None, retrieved="abcdefghij")]
    cell = served_ranks(rows)["bm25"]
    assert cell["rank_state"] == "instrumented"
    assert cell["served_len_median"] == 10
    assert cell["gt_at_1"] == 1
    assert cell["gt_never"] == 1


def test_an_arm_that_ranks_but_never_resolves_is_uninstrumented_not_a_miss():
    """grep_skilled's case: a non-empty list, every rank null. That is the HARNESS, not the arm.

    Reporting it as "the evidence never appeared" would publish a property of the instrument as a
    measured property of the arm, which is the exact error class the judge caught one level up.
    """
    from atlas.bench.summary import served_ranks

    rows = [_row("grep", "T1", False, gt=None, hit=None, retrieved=["a.md", "b.md"]),
            _row("grep", "T2", True, gt=None, hit=None, retrieved=["c.md"])]
    cell = served_ranks(rows)["grep"]
    assert cell["rank_state"] == "uninstrumented"
    assert cell["ranks"] is True, "it DOES rank - it returns a list"
    assert cell["gt_never"] is None, "a null denominator, never a count that reads as a miss"


def test_the_served_length_spread_is_reported_when_it_varies():
    """The incumbent's two-round union: a longer list than k, and the table has to say so."""
    from atlas.bench.summary import served_ranks

    rows = [_row("inc", "T1", True, gt=1, hit=1, retrieved=list(range(17))),
            _row("inc", "T2", False, gt=None, hit=None, retrieved=list(range(10))),
            _row("inc", "T3", False, gt=None, hit=None, retrieved=list(range(14)))]
    cell = served_ranks(rows)["inc"]
    assert (cell["served_len_min"], cell["served_len_max"]) == (10, 17)
    assert cell["served_len_median"] == 14


def test_the_rendered_table_names_the_served_length_and_drops_top_k():
    """The column heading itself is the defect the judge named; pin it against the source.

    Asserting on ``render``'s source rather than on a rendered table keeps this test free of a
    banked run directory, and it makes a future rename a deliberate act rather than a silent one.
    """
    import inspect

    from atlas.bench import summary

    src = inspect.getsource(summary.render)
    assert "evidence in the served list" in src
    assert "served list length (median)" in src
    assert "evidence in top-k" not in src, "the uneven-denominator heading must not come back"
