"""holdout_gate.py - the shared gate-then-ship organ: a candidate-picker ships only if it beats
a dumb baseline on data it never trained on.

Generalises the one precedent this discipline lived in until now: ``metric_distill.py``'s
``main`` saves the trained metric M ONLY if the held-out AUC beats the identity baseline
(``metric_distill.py`` ~lines 20-22, ``HOLDOUT = 0.1``). That gate was inline and bespoke to
one artefact (a bilinear metric). This module lifts the law out so any picker can wire into
it: AUDIT_2026-07-15_the-pipeline-workflow-audit.md's stage-stores context names the need
directly - the stage-stores run needs this as a shared organ because "a store that can't pick
the right exemplar for a held-out section does not wire in" (see the audit's stage-stores
readiness verdict, and its §A4 fan-out-width finding for the surrounding fan-out-discipline
gap this session is closing).

THE LAW, stated once so every caller inherits it rather than re-deriving it:

  * **Gate-then-ship.** ``passed`` is ``score > baseline`` STRICTLY - a tie does not ship,
    exactly as ``metric_distill`` requires ``auc_trained`` to strictly exceed ``auc_identity``.
    The refusal IS the result: a caller that ignores ``passed`` and ships anyway has left this
    organ, not used it.
  * **Determinism.** No wall-clock, no unseeded randomness anywhere in this module - the
    train/holdout split and the default baseline's randomness are both drawn from ``seed``
    alone, so the same ``(items, pick_fn, truth_fn, seed)`` produces the SAME verdict forever.
    The verdict banks into records; a gate that could disagree with its own past self is not
    a gate.
  * **Stated refusal.** A holdout too small to mean anything (``n_holdout < 3``) or a holdout
    with no discriminative power (every held-out truth is the same candidate - there is
    nothing to rank against) never produces a numeric pass. Both return
    ``{mode: "insufficient", passed: False, score: None, baseline: None}`` - never a vacuous
    pass dressed as a real number.

Two scoring modes, chosen from the SHAPE of ``pick_fn``'s own return value (never a caller
flag - the picker's contract determines what can plainly be measured):

  * **``mode="auc"``** - ``pick_fn(item)`` returns a *scored ranking* over a candidate set (a
    ``dict {candidate: score}`` or an iterable of ``(candidate, score)`` pairs). The score is a
    pairwise ranking AUC: for each held-out item, the empirical win-rate of the true
    candidate's score against every OTHER candidate returned for that item (ties count as half
    a win, the standard AUC convention; a true candidate missing from the ranking loses every
    comparison for that item - a picker that doesn't even surface the truth does not get
    partial credit). This is the direct generalisation of ``metric_distill.auc``'s
    sampled-negative win-rate, made exhaustive since per-item candidate pools here are
    typically small (a handful of exemplars), not a full corpus.
  * **``mode="top1"``** - ``pick_fn(item)`` returns a single hard pick (no scores at all).
    There is no ranking to compute a probability over, so AUC is ill-posed by construction;
    the plain measure is top-1 accuracy - the fraction of held-out items where the pick
    equals ``truth_fn(item)``.

Both modes are scored identically for the baseline (same shape contract, same held-out set),
so ``score`` and ``baseline`` are always directly comparable numbers in ``[0, 1]``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Callable, Optional

SEED = 7                  # deterministic: same items + same seed -> same verdict, forever
HOLDOUT_FRACTION = 0.1    # default fraction of items held out for the gate
MIN_HOLDOUT = 3            # below this, a verdict would be numerically vacuous - refuse


def _is_scored_ranking(value: Any) -> bool:
    """True if ``value`` is a ranking pick_fn/baseline_fn can return in ``auc`` mode: a mapping
    of candidate -> score, or a (possibly empty) sequence of ``(candidate, score)`` pairs. A
    bare scalar/hashable pick (str, int, tuple-as-id, ...) is NOT a ranking - that is the
    ``top1`` contract instead."""
    if isinstance(value, Mapping):
        return True
    if isinstance(value, (list, tuple)):
        return all(isinstance(p, (list, tuple)) and len(p) == 2 for p in value)
    return False


def _to_score_map(ranking: Any) -> dict[Any, float]:
    if isinstance(ranking, Mapping):
        return dict(ranking)
    return {c: s for c, s in ranking}


def _pairwise_auc(true_id: Any, score_map: dict[Any, float]) -> Optional[tuple[float, int]]:
    """(wins, trials) for one held-out item's ranking, or None if the item contributes no
    trials (no other candidates to compare the truth against)."""
    others = [c for c in score_map if c != true_id]
    if not others:
        return None
    t_score = score_map.get(true_id)
    if t_score is None:
        return 0.0, len(others)          # truth wasn't even surfaced - every comparison lost
    wins = 0.0
    for c in others:
        s = score_map[c]
        if t_score > s:
            wins += 1.0
        elif t_score == s:
            wins += 0.5
    return wins, len(others)


def holdout_gate(
    items: Any,
    *,
    pick_fn: Callable[[Any], Any],
    truth_fn: Callable[[Any], Any],
    holdout_fraction: float = HOLDOUT_FRACTION,
    seed: int = SEED,
    baseline_fn: Optional[Callable[[Any], Any]] = None,
) -> dict[str, Any]:
    """Gate a candidate-picker on held-out data. Returns
    ``{score, baseline, passed, n_holdout, n_train, mode}`` - the report IS the result; the
    caller ships only on ``passed`` (never on ``score`` alone - that is the whole point of a
    baseline).

    ``items`` - the full pool of cases to split (each one whatever ``pick_fn``/``truth_fn``
    expect: a section, a query, an exemplar slot, ...).
    ``pick_fn(item)`` - the picker under test. Either a scored ranking (``dict`` or
    ``[(candidate, score), ...]``, selects ``mode="auc"``) or a single hard pick (any hashable,
    selects ``mode="top1"``). Called ONCE per held-out item, never on the training split (this
    gate scores generalisation, it does not train anything itself).
    ``truth_fn(item)`` - the correct candidate for ``item``.
    ``baseline_fn(item)`` - the dumb baseline, same return contract as ``pick_fn`` for the
    detected mode. Defaults to None, in which case a seeded-random baseline is used - the
    generic analogue of ``metric_distill``'s identity (M=I) baseline: a picker with no real
    signal, evaluated the exact same way as the real one so the comparison is fair. In
    ``auc`` mode it scores the SAME candidates ``pick_fn`` returned with i.i.d. random floats;
    in ``top1`` mode it draws uniformly from the candidate labels seen in the TRAINING split
    (never from held-out truths - the baseline must not peek at what it's being scored against).

    The split is deterministic: items are seeded-permuted by ``seed`` and the first
    ``round(len(items) * holdout_fraction)`` (at least 1 when items exist) become the held-out
    set. Determinism law: no other randomness anywhere in this function is unseeded.
    """
    import numpy as np

    items = list(items)
    n = len(items)
    rng = np.random.default_rng(seed)
    order = rng.permutation(n) if n else np.array([], dtype=int)
    n_holdout = min(n, max(1, int(round(n * holdout_fraction)))) if n else 0
    held_idx = order[:n_holdout]
    train_idx = order[n_holdout:]
    held = [items[i] for i in held_idx]
    train = [items[i] for i in train_idx]
    n_train = len(train)

    def _insufficient() -> dict[str, Any]:
        return {"score": None, "baseline": None, "passed": False,
                "n_holdout": len(held), "n_train": n_train, "mode": "insufficient"}

    if len(held) < MIN_HOLDOUT:
        return _insufficient()

    truths = [truth_fn(i) for i in held]
    if len(set(truths)) < 2:
        # single-class truth: nothing to rank/discriminate against - a "pass" here would be
        # vacuous (even a picker that always answers the one class looks perfect).
        return _insufficient()

    rankings = [pick_fn(i) for i in held]
    mode = "auc" if _is_scored_ranking(rankings[0]) else "top1"
    rng_baseline = np.random.default_rng([seed, 1])   # independent stream from the split rng

    if mode == "auc":
        wins = trials = 0.0
        b_wins = b_trials = 0.0
        for item, ranking, true_id in zip(held, rankings, truths):
            score_map = _to_score_map(ranking)
            contrib = _pairwise_auc(true_id, score_map)
            if contrib is not None:
                w, t = contrib
                wins += w
                trials += t
            if baseline_fn is not None:
                b_map = _to_score_map(baseline_fn(item))
            else:
                b_map = {c: float(rng_baseline.random()) for c in score_map}
            b_contrib = _pairwise_auc(true_id, b_map)
            if b_contrib is not None:
                bw, bt = b_contrib
                b_wins += bw
                b_trials += bt
        if trials == 0 or b_trials == 0:
            # every held-out item's candidate pool was too thin to compare against (e.g. every
            # ranking is a singleton) - AUC is ill-posed here too; refuse rather than fabricate.
            return _insufficient()
        score = wins / trials
        baseline = b_wins / b_trials
    else:
        train_labels = (sorted({truth_fn(i) for i in train}, key=repr) if train
                         else sorted(set(truths), key=repr))
        hits = 0
        b_hits = 0
        for item, pick, true_id in zip(held, rankings, truths):
            hits += 1 if pick == true_id else 0
            b_pick = baseline_fn(item) if baseline_fn is not None else rng_baseline.choice(train_labels)
            b_hits += 1 if b_pick == true_id else 0
        score = hits / len(held)
        baseline = b_hits / len(held)

    return {"score": round(float(score), 6), "baseline": round(float(baseline), 6),
            "passed": bool(score > baseline), "n_holdout": len(held), "n_train": n_train,
            "mode": mode}
