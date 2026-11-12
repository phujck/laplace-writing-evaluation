"""test_bench_stats.py - the bootstrap is seeded, paired, and refuses to speak about n=3.

Three properties are worth a test and the third is the one that matters:

  1. it is DETERMINISTIC at a seed - a CI that moves between runs is not a CI;
  2. it is PAIRED - the same resampled task set reaches every arm in a replicate, which is what
     makes a pairwise difference interval mean anything;
  3. it refuses to be used per class - the module exposes an annotation string for n=3 cells
     rather than a number, and the summary prints that string.
"""

from __future__ import annotations

from atlas.bench.stats import (
    DEFAULT_RESAMPLES,
    DEFAULT_SEED,
    PER_CLASS_ANNOTATION,
    bootstrap_totals,
)


def _rows(pattern: dict[str, list[int]]) -> list[dict]:
    """``{arm: [0/1 per task]}`` -> bench rows, so a test states its data as a truth table."""
    out = []
    for arm, flags in pattern.items():
        for i, flag in enumerate(flags):
            out.append({"arm": arm, "task": f"T{i:02d}", "class": "c", "correct": bool(flag)})
    return out


def test_the_bootstrap_is_deterministic_at_a_seed():
    rows = _rows({"a": [1, 0, 1, 1, 0, 1, 0, 1], "b": [0, 0, 1, 0, 1, 0, 0, 1]})
    first = bootstrap_totals(rows, resamples=500, seed=7)
    second = bootstrap_totals(rows, resamples=500, seed=7)
    assert first == second


def test_a_different_seed_is_a_different_measurement():
    rows = _rows({"a": [1, 0, 1, 1, 0, 1, 0, 1], "b": [0, 0, 1, 0, 1, 0, 0, 1]})
    assert (bootstrap_totals(rows, resamples=500, seed=7)
            != bootstrap_totals(rows, resamples=500, seed=8))


def test_the_seed_and_resample_count_travel_in_the_record():
    record = bootstrap_totals(_rows({"a": [1, 0, 1]}))
    assert record["seed"] == DEFAULT_SEED
    assert record["resamples"] == DEFAULT_RESAMPLES


def test_the_observed_count_is_the_real_count_not_a_resampled_one():
    rows = _rows({"a": [1, 1, 1, 0, 0]})
    record = bootstrap_totals(rows, resamples=200, seed=1)
    assert record["per_arm"]["a"]["observed_correct"] == 3
    assert record["per_arm"]["a"]["total_tasks"] == 5


def test_the_interval_brackets_the_observation():
    rows = _rows({"a": [1, 1, 1, 0, 1, 1, 0, 1, 1, 1]})
    cell = bootstrap_totals(rows, resamples=2000, seed=3)["per_arm"]["a"]
    assert cell["ci_low"] <= cell["observed_correct"] <= cell["ci_high"]


def test_a_perfect_arm_has_a_degenerate_interval():
    """Every resample of an all-correct arm is all-correct; the interval is the point."""
    cell = bootstrap_totals(_rows({"a": [1] * 12}), resamples=500, seed=5)["per_arm"]["a"]
    assert (cell["ci_low"], cell["ci_high"]) == (12, 12)


def test_the_resample_is_paired_across_arms():
    """Two IDENTICAL arms must have a difference interval of exactly zero.

    This is the property pairing buys and the one an unpaired bootstrap fails: resampling each
    arm independently would produce a spread of differences between two arms that are the same
    arm, and every pairwise claim built on it would be inflated noise.
    """
    flags = [1, 0, 1, 1, 0, 0, 1, 0, 1, 1]
    record = bootstrap_totals(_rows({"a": flags, "b": list(flags)}), resamples=1000, seed=11)
    pair = record["pairwise"][0]
    assert pair["observed_difference"] == 0
    assert (pair["ci_low"], pair["ci_high"]) == (0, 0)
    assert pair["excludes_zero"] is False


def test_a_dominating_arm_separates_and_a_close_one_does_not():
    dominant = bootstrap_totals(
        _rows({"a": [1] * 20 + [0], "b": [0] * 20 + [1]}), resamples=2000, seed=2)
    assert dominant["pairwise"][0]["excludes_zero"] is True
    close = bootstrap_totals(
        _rows({"a": [1, 1, 0, 0, 1, 0], "b": [1, 0, 0, 0, 1, 0]}), resamples=2000, seed=2)
    assert close["pairwise"][0]["excludes_zero"] is False


def test_every_arm_pair_appears_exactly_once():
    record = bootstrap_totals(_rows({"a": [1, 0], "b": [0, 1], "c": [1, 1]}),
                              resamples=100, seed=1)
    pairs = {(p["arm_a"], p["arm_b"]) for p in record["pairwise"]}
    assert pairs == {("a", "b"), ("a", "c"), ("b", "c")}
    assert len(record["pairwise"]) == 3


def test_the_per_class_annotation_is_prose_and_not_a_number():
    assert PER_CLASS_ANNOTATION == "n=3, not separable"
    assert bootstrap_totals(_rows({"a": [1, 0, 1]}))["per_class_note"] == PER_CLASS_ANNOTATION
