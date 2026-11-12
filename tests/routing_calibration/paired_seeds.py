"""The paired feature-set comparison over MANY random splits, with the counts pooled.

Why this script exists.  The first draft of this lane reported the paired
`homes`-vs-`names` comparison from ONE split (seed 20261002, 5 folds): 9 discordant
rows to 0, exact two-sided McNemar p = 0.0039, and called it "strictly dominates".
The lane's own falsification recipe said a re-run at a different seed should not move
the direction.  An independent judge ran it, and the strong words did not survive:
seed 13 gave 7 vs 1 (p = 0.070), seed 99 gave 7 vs 0 (p = 0.016), seed 7 at 10 folds
gave 4 vs 1 (p = 0.375).  The accuracy gap the claim rested on --- 9 rows on 540 ---
is inside the fold-to-fold spread the same report prints (0.3519 to 0.4630).  One
split is not evidence about a 2%-wide effect on 540 rows.

So the measurement is repeated.  For each of N seeds this runs the whole three-way
procedure (train fits the head, calibrate fits the isotonic map, test is reported) for
every feature set, and accumulates the paired discordant counts over every
(seed, row) pair.  Three statements come out, and they say different things:

* **pooled** --- discordant counts summed over N x 540 paired decisions, with the
  exact two-sided binomial.  This is the sharpest number and it is ANTI-CONSERVATIVE:
  the splits reuse the same 540 rows, so the paired decisions are not independent and
  the nominal p is smaller than a true p would be.  It is reported as a pooled count
  with that caveat attached, never as a significance claim on its own.
* **per-split sign** --- in how many of the N splits the discordant count favoured A.
  A direction that is real shows up here; a direction that was one lucky split does
  not.  The binomial here is over splits, which share rows, so it carries the same
  caveat --- but "20 of 20 splits leaned the same way" is a statement a reader can
  check against the printed per-split table, which is the point.
* **accuracy spread** --- the per-split accuracy difference, mean, sd and range, set
  beside the fold-to-fold spread of a single split, so a reader can see directly
  whether the effect is larger than the noise it is being read out of.

    scripts/laplace-python tests/routing_calibration/paired_seeds.py \
        --labels <labels.json> --out <dir> --seeds 20 --folds 5
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import statistics
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "src"))
sys.path.insert(0, str(HERE))

import calibrate                                    # noqa: E402
from laplace.native import routing                         # noqa: E402

PAIRS = (("homes", "names"), ("homes", "noguard"), ("homes", "homes+shapes"))


def exact_two_sided(only_a: int, only_b: int) -> float:
    """The exact two-sided binomial on the discordant pairs; 1.0 when there are none."""
    n = only_a + only_b
    if n == 0:
        return 1.0
    high = max(only_a, only_b)
    tail = sum(math.comb(n, k) for k in range(high, n + 1))
    return min(1.0, 2.0 * tail / (2 ** n))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", default=str(HERE / "labels.json"))
    parser.add_argument("--out", required=True)
    parser.add_argument("--seeds", type=int, default=20)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--first-seed", type=int, default=20261002)
    args = parser.parse_args()

    data = json.loads(Path(args.labels).read_text())
    d1_rows = data["d1"]
    costs: dict[str, int] = {}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    # The seeds are the lane's original one, the three the judge used, then a
    # deterministic arithmetic walk, so the four already-published splits are IN the
    # pool rather than replaced by a fresh set that happens to agree.
    seeds = [args.first_seed, 13, 99, 7]
    step = 1_000_003
    while len(seeds) < args.seeds:
        candidate = args.first_seed + step * (len(seeds) - 3)
        if candidate not in seeds:
            seeds.append(candidate)
    seeds = seeds[:args.seeds]

    per_split: list[dict] = []
    pooled = {name: {"a": 0, "b": 0, "paired": 0} for name in PAIRS}
    for index, seed in enumerate(seeds):
        folds = args.folds
        correct: dict[str, dict[str, bool]] = {}
        accuracy: dict[str, float] = {}
        fold_accuracies: dict[str, list[float]] = {}
        for feature_set in routing.FEATURE_SETS:
            result = calibrate.run_d1(d1_rows, seed=seed, folds=folds,
                                      feature_set=feature_set, costs=costs)
            correct[feature_set] = {r["id"]: r["correct"] for r in result["rows"]}
            accuracy[feature_set] = result["accuracy"]["accuracy"]
            fold_accuracies[feature_set] = [f["accuracy"]["accuracy"] for f in result["folds"]]
        row = {"seed": seed, "folds": folds, "accuracy": accuracy,
               "fold_accuracies": fold_accuracies, "paired": {}}
        for name in PAIRS:
            a_name, b_name = name
            a, b = correct[a_name], correct[b_name]
            shared = sorted(set(a) & set(b))
            only_a = sum(1 for i in shared if a[i] and not b[i])
            only_b = sum(1 for i in shared if b[i] and not a[i])
            row["paired"]["%s vs %s" % name] = {
                "a_only_right": only_a, "b_only_right": only_b,
                "discordant": only_a + only_b, "n_paired": len(shared),
                "p_two_sided_exact": round(exact_two_sided(only_a, only_b), 5)}
            pooled[name]["a"] += only_a
            pooled[name]["b"] += only_b
            pooled[name]["paired"] += len(shared)
        per_split.append(row)
        print("  split %2d/%d seed %-10d folds %d  %s"
              % (index + 1, len(seeds), seed, folds,
                 "  ".join("%s %d/%d p=%.4f" % (k, v["a_only_right"], v["b_only_right"],
                                                v["p_two_sided_exact"])
                           for k, v in row["paired"].items())), flush=True)

    summary = {"seeds": seeds, "folds": args.folds, "n_rows": len(d1_rows),
               "per_split": per_split, "pooled": {}}
    for name in PAIRS:
        a_name, b_name = name
        counts = pooled[name]
        splits = [s["paired"]["%s vs %s" % name] for s in per_split]
        a_favoured = sum(1 for s in splits if s["a_only_right"] > s["b_only_right"])
        b_favoured = sum(1 for s in splits if s["b_only_right"] > s["a_only_right"])
        ties = len(splits) - a_favoured - b_favoured
        significant = sum(1 for s in splits if s["p_two_sided_exact"] < 0.05)
        deltas = [s["accuracy"][a_name] - s["accuracy"][b_name] for s in per_split]
        summary["pooled"]["%s vs %s" % name] = {
            "a_only_right": counts["a"], "b_only_right": counts["b"],
            "discordant": counts["a"] + counts["b"], "n_paired_decisions": counts["paired"],
            "p_two_sided_exact_NOT_INDEPENDENT": round(exact_two_sided(counts["a"], counts["b"]), 8),
            "splits_favouring_a": a_favoured, "splits_favouring_b": b_favoured,
            "splits_tied": ties, "splits_individually_significant_at_0.05": significant,
            "n_splits": len(splits),
            "accuracy_delta_mean": round(statistics.fmean(deltas), 5),
            "accuracy_delta_sd": round(statistics.stdev(deltas), 5) if len(deltas) > 1 else 0.0,
            "accuracy_delta_min": round(min(deltas), 5),
            "accuracy_delta_max": round(max(deltas), 5),
            "splits_with_a_more_accurate": sum(1 for d in deltas if d > 0)}
    # the noise the effect is read out of: the fold-to-fold spread of `homes` itself
    all_folds = [a for s in per_split for a in s["fold_accuracies"]["homes"]]
    summary["homes_fold_accuracy"] = {
        "n_folds": len(all_folds), "min": round(min(all_folds), 4),
        "max": round(max(all_folds), 4), "mean": round(statistics.fmean(all_folds), 4),
        "sd": round(statistics.stdev(all_folds), 4)}
    (out / "paired_seeds.json").write_text(json.dumps(summary, indent=1, sort_keys=True))

    print("\npooled over %d splits x %d rows (the splits REUSE the same rows, so the "
          "pooled p is anti-conservative and is a count, not a significance claim):"
          % (len(seeds), len(d1_rows)))
    for key, value in summary["pooled"].items():
        print("  %-22s %4d vs %-4d of %6d paired decisions, pooled exact p=%.3g"
              % (key, value["a_only_right"], value["b_only_right"],
                 value["n_paired_decisions"], value["p_two_sided_exact_NOT_INDEPENDENT"]))
        print("    %21s %d/%d splits lean to the first, %d to the second, %d tied; "
              "%d of %d individually significant at 0.05"
              % ("", value["splits_favouring_a"], value["n_splits"],
                 value["splits_favouring_b"], value["splits_tied"],
                 value["splits_individually_significant_at_0.05"], value["n_splits"]))
        print("    %21s accuracy delta mean %+.4f sd %.4f range %+.4f..%+.4f, "
              "first more accurate in %d/%d splits"
              % ("", value["accuracy_delta_mean"], value["accuracy_delta_sd"],
                 value["accuracy_delta_min"], value["accuracy_delta_max"],
                 value["splits_with_a_more_accurate"], value["n_splits"]))
    print("the noise: `homes` per-fold accuracy over %d folds, %.4f..%.4f, sd %.4f"
          % (summary["homes_fold_accuracy"]["n_folds"], summary["homes_fold_accuracy"]["min"],
             summary["homes_fold_accuracy"]["max"], summary["homes_fold_accuracy"]["sd"]))
    print("written", out / "paired_seeds.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
