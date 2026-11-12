"""test_bench_runner.py - determinism, the freeze-before-run ordering, and the planted control.

Gate (c): the same bundle run twice produces identical rows modulo latency. The exempt fields are
named in one place (``runner._deterministic_rows``) and this test is what holds that list honest -
if a nondeterministic field is added and not exempted, the row digests split and this fails.

Also here: the ordering proof that makes "pre-registered" mechanical. A run whose bundle was
frozen AFTER the run started refuses outright, because a prediction table registered after the
outcome is not a prediction and no amount of prose fixes that.
"""

from __future__ import annotations

import dataclasses
import json

import pytest
from bench_fixture import build_bundle, open_bundle

from atlas.bench.arms import Bm25Arm, FlatReadArm, GrepSkilledArm
from atlas.bench.freeze import anchor_task, freeze_bundle
from atlas.bench.runner import run_bundle, write_run
from atlas.bench.universe import BENCH_FILTERED, FULL_UNIVERSE, PlantedSpan, SnapshotView
from atlas.errors import ProtocolViolation, SummaryDisagreement
from atlas.ids import chash


@pytest.fixture()
def view(tmp_path):
    return SnapshotView(open_bundle(build_bundle(tmp_path / "snap")), BENCH_FILTERED)


@pytest.fixture()
def bundle(view):
    tasks = [
        anchor_task(view, "T1", "current-aim",
                    "What is the next move and what ordering does it impose?",
                    ["run the widget sweep", "correctness comes before cost"], None,
                    "HANDOFF.md", "2026-08-01"),
        anchor_task(view, "T2", "standing-law",
                    "May a derivable fork be decided without asking the author?",
                    ["derive it, decide it, and record it"], None,
                    "STANDING_LAW.md", "2026-08-01"),
        anchor_task(view, "T3", "topic-descent",
                    "What agreement did the descent reach at beam 8?",
                    ["0.835"], None, "evidence/agree.md", "2026-08-01"),
    ]
    return freeze_bundle(view, "sha256:" + "a" * 64, tasks)


def _arms():
    return [FlatReadArm("B"), FlatReadArm("B+"), GrepSkilledArm(), Bm25Arm(k=3)]


def test_a_run_produces_one_row_per_task_per_arm(view, bundle):
    result = run_bundle(bundle, view, _arms(), "seg")
    assert len(result.rows) == len(bundle.tasks) * 4
    assert {r["arm"] for r in result.rows} == {"flat_read:B", "flat_read:B+", "grep_skilled",
                                               "bm25"}


def test_two_runs_are_identical_modulo_latency(view, bundle):
    """GATE (c). The row digest excludes latency and nothing else."""
    a = run_bundle(bundle, view, _arms(), "seg")
    b = run_bundle(bundle, view, _arms(), "seg")
    assert a.manifest["rows_digest"] == b.manifest["rows_digest"]
    for ra, rb in zip(a.rows, b.rows, strict=True):
        stripped_a = {k: v for k, v in ra.items() if k != "latency_ms"}
        stripped_b = {k: v for k, v in rb.items() if k != "latency_ms"}
        assert stripped_a == stripped_b


def test_the_latency_field_is_the_only_exempt_field(view, bundle):
    """If a nondeterministic field is added without exemption, the digests split."""
    from atlas.bench.runner import _deterministic_rows
    result = run_bundle(bundle, view, _arms(), "seg")
    stripped = _deterministic_rows(result.rows)
    assert all("latency_ms" not in r for r in stripped)
    assert chash(stripped) == result.manifest["rows_digest"]


def test_a_bundle_frozen_after_the_run_started_refuses(view, bundle):
    future = dataclasses.replace(bundle, frozen_ts="2099-01-01T00:00:00+00:00")
    future = dataclasses.replace(future, bundle_id=future.computed_id())
    with pytest.raises(ProtocolViolation) as exc:
        run_bundle(future, view, _arms(), "seg")
    assert "frozen before this run" in exc.value.message


def test_correctness_is_computed_and_the_manifest_is_unjudged(view, bundle):
    result = run_bundle(bundle, view, _arms(), "seg")
    assert result.manifest["verdict"] == "UNJUDGED"
    assert result.manifest["verdict_row"] is None
    law = [r for r in result.rows if r["task"] == "T2"]
    assert {r["arm"] for r in law if r["correct"]} >= {"flat_read:B+"}
    assert not any(r["correct"] for r in law if r["arm"] == "flat_read:B"), (
        "STANDING_LAW.md is not in the quoted set, so arm B cannot answer a standing-law question")


def test_every_row_counts_zero_query_model_calls(view, bundle):
    result = run_bundle(bundle, view, _arms(), "seg")
    assert all(r["cost"]["query_model_calls"] == 0 for r in result.rows)


def test_the_full_universe_control_runs_the_same_bundle(view, bundle):
    full = SnapshotView(view.bundle, FULL_UNIVERSE)
    result = run_bundle(bundle, full, _arms(), "seg")
    assert result.manifest["universe"]["name"] == "full/1"
    assert result.manifest["bundle_id"] == bundle.bundle_id
    assert result.manifest["view_stats"]["nodes_included"] > view.stats()["nodes_included"]


def test_the_planted_control_reports_per_arm(view, bundle):
    planted = [PlantedSpan(
        planted_id="planted:t3", node_id="planted/wrong.md",
        text=("The agreement at beam 8 was 0.111 and the descent touched 9.9% of the corpus, "
              "which is the figure the cards carry."),
        targets_task="T3", wrong_atoms=["0.111"])]
    result = run_bundle(bundle, view, _arms(), "seg", planted=planted)
    assert result.planted_rows
    by_arm = {r["arm"]: r for r in result.planted_rows}
    assert set(by_arm) == {"flat_read:B", "flat_read:B+", "grep_skilled", "bm25"}
    for row in result.planted_rows:
        assert set(row) >= {"retrieved_rank", "false_positive_at_k", "wrong_answer_in_context",
                            "still_correct"}


def test_the_planted_control_reports_the_baseline_verdict_beside_the_planted_one(view, bundle):
    """The D1 repair: a flip must be a visible DELTA, not a baseline a reader has to look up.

    The first reading of this control claimed a plant flipped an arm from correct to incorrect;
    the judge cross-tabulated and found the arm had been incorrect without any plant. With
    ``was_correct`` beside ``still_correct`` and ``verdict_flipped`` derived from the pair, that
    misreading is structurally impossible.
    """
    planted = [PlantedSpan(
        planted_id="planted:t3", node_id="planted/wrong.md",
        text="The agreement at beam 8 was 0.111 and the descent touched 9.9% of the corpus.",
        targets_task="T3", wrong_atoms=["0.111"])]
    result = run_bundle(bundle, view, _arms(), "seg", planted=planted)
    base = {(r["task"], r["arm"]): bool(r["correct"]) for r in result.rows}
    for row in result.planted_rows:
        assert row["was_correct"] == base[(row["task"], row["arm"])]
        assert row["verdict_flipped"] == (row["was_correct"] != row["still_correct"])


def test_the_summary_refuses_rows_that_are_not_the_judged_rows(view, bundle, tmp_path):
    """The D2 repair: the digest binds EVERY row field, not the handful the aggregates read.

    A class relabel moves the correctness table while every per-arm cost aggregate stays put, so
    the cost assertions cannot see it. The rows_digest can.
    """
    from atlas.bench.summary import render

    result = run_bundle(bundle, view, _arms(), "seg")
    run_dir = tmp_path / "run"
    write_run(result, run_dir)
    render(run_dir)                                    # intact: no refusal

    rows = [json.loads(line) for line in (run_dir / "rows.jsonl").read_text().splitlines()]
    rows[0]["class"] = "a-class-nobody-registered"
    (run_dir / "rows.jsonl").write_text(
        "".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in rows))
    with pytest.raises(SummaryDisagreement) as exc:
        render(run_dir)
    assert exc.value.reason == "bench-summary-disagreement"
    assert "rows this manifest was written over" in exc.value.message


def test_the_summary_refuses_a_field_no_aggregate_reads(view, bundle, tmp_path):
    """tokens_context is read by no cost assertion at all - the digest is what covers it."""
    from atlas.bench.summary import render

    result = run_bundle(bundle, view, _arms(), "seg")
    run_dir = tmp_path / "run2"
    write_run(result, run_dir)
    rows = [json.loads(line) for line in (run_dir / "rows.jsonl").read_text().splitlines()]
    rows[0]["tokens_context"] = 1
    (run_dir / "rows.jsonl").write_text(
        "".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in rows))
    with pytest.raises(SummaryDisagreement):
        render(run_dir)


def test_a_run_banks_rows_manifest_and_reloads(view, bundle, tmp_path):
    result = run_bundle(bundle, view, _arms(), "seg")
    paths = write_run(result, tmp_path / "run")
    assert paths["rows"].is_file() and paths["manifest"].is_file()
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["bundle_id"] == bundle.bundle_id
    assert manifest["freeze_before_run"] is True
    assert len(manifest["arms"]) == 4
