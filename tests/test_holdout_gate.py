"""test_holdout_gate.py - the shared gate-then-ship organ, exercised on synthetic pickers: a
picker that genuinely ranks/predicts the truth PASSES against the seeded-random baseline, a
degenerate one FAILS, and the honest-refusal paths (too little holdout, single-class truth)
never produce a vacuous numeric pass. Mirrors ``tests/test_metric_distill.py``'s synthetic
style for the one precedent this module generalises.
"""

from __future__ import annotations

import pytest

pytest.importorskip("numpy")

from laplace.pipeline.holdout_gate import holdout_gate


def _truth_fn(i: int) -> str:
    return f"cand-{i}"


def test_good_ranking_picker_passes():
    """(a) a pick_fn that genuinely ranks the true candidate highest PASSES."""
    items = list(range(30))

    def pick_fn(i: int) -> dict[str, float]:
        return {f"cand-{i}": 1.0, "decoy-a": 0.1, "decoy-b": 0.05}

    result = holdout_gate(items, pick_fn=pick_fn, truth_fn=_truth_fn, seed=1)
    assert result["mode"] == "auc"
    assert result["score"] == 1.0                      # true candidate always ranked #1
    assert result["score"] > result["baseline"]
    assert result["passed"] is True
    assert result["n_holdout"] == 3 and result["n_train"] == 27


def test_degenerate_ranking_picker_fails():
    """(b) a picker anti-correlated with truth (always ranks the truth LAST) FAILS against
    the seeded-random baseline."""
    items = list(range(30))

    def pick_fn(i: int) -> dict[str, float]:
        return {f"cand-{i}": 0.0, "decoy-a": 1.0, "decoy-b": 0.5}

    result = holdout_gate(items, pick_fn=pick_fn, truth_fn=_truth_fn, seed=1)
    assert result["mode"] == "auc"
    assert result["score"] == 0.0                       # true candidate always ranked last
    assert result["score"] <= result["baseline"]
    assert result["passed"] is False


def test_good_top1_picker_passes():
    """top1 mode: a pick_fn that returns a single hard (correct) pick beats the random
    baseline drawn from the training label pool."""
    items = list(range(40))

    def pick_fn(i: int) -> str:
        return f"cand-{i}"                              # always exactly right

    result = holdout_gate(items, pick_fn=pick_fn, truth_fn=_truth_fn, seed=3)
    assert result["mode"] == "top1"
    assert result["score"] == 1.0
    assert result["passed"] is True


def test_insufficient_holdout_too_small():
    """(c) too few items for a meaningful holdout -> passed=False, mode='insufficient',
    never a numeric score."""
    items = [0, 1]

    def pick_fn(i: int) -> dict[str, float]:
        return {f"cand-{i}": 1.0}

    result = holdout_gate(items, pick_fn=pick_fn, truth_fn=_truth_fn,
                           holdout_fraction=0.5, seed=1)
    assert result["mode"] == "insufficient"
    assert result["passed"] is False
    assert result["score"] is None
    assert result["baseline"] is None
    assert result["n_holdout"] < 3


def test_determinism_same_verdict_twice():
    """(d) two runs on identical inputs produce the identical verdict dict."""
    items = list(range(40))

    def pick_fn(i: int) -> dict[str, float]:
        return {f"cand-{i}": (i % 5) / 5.0, "decoy": 0.4}

    a = holdout_gate(items, pick_fn=pick_fn, truth_fn=_truth_fn, seed=42)
    b = holdout_gate(items, pick_fn=pick_fn, truth_fn=_truth_fn, seed=42)
    assert a == b


def test_single_class_truth_never_passes():
    """(e) every held-out item shares the SAME truth - nothing to discriminate against, so
    even a "perfect" picker must not get a vacuous pass."""
    items = list(range(20))

    def truth_fn(i: int) -> str:
        return "only-candidate"

    def pick_fn(i: int) -> dict[str, float]:
        return {"only-candidate": 1.0, "decoy": 0.0}    # "perfect" on the one class

    result = holdout_gate(items, pick_fn=pick_fn, truth_fn=truth_fn, seed=1)
    assert result["mode"] == "insufficient"
    assert result["passed"] is False
    assert result["score"] is None
