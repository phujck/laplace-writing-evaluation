#!/usr/bin/env python3
"""Run the lane's own calibration at several seeds and report the held-out cost rule's
verdict per feature set at each one.

WHY THIS EXISTS.  Round 2's judge said "no reported threshold is measured on the rows
that chose it", and the fix was to choose tau on a held-out CALIBRATE block.  That cures
half of the complaint.  The other half is that the SPLIT itself was never varied: the
three-way split in `calibrate.three_way` is `random.Random(seed).shuffle(order)`, so one
seed is one split, and the sentence section 7.3's decision was argued against --
"`homes+shapes` is the only feature set whose held-out cost is under a turn" -- is a
property of that one split, reported as a property of the feature sets.

So: run the whole calibration at N seeds, and print, per feature set, the held-out
realised wrong-route cost and whether it is under one turn, at every seed.  What survives
every seed is a statement about the feature sets; what moves with the seed is a statement
about the split and must be reported as one.

    scripts/laplace-python tools/writing_verbs/calibration_seed_sweep.py \
        --labels <...>/labels.json --costs <...>/costs.json \
        --out /tmp/... --seeds 20261002,7,991,20260101,42,20251231

Nothing here re-implements the calibration: it shells `calibrate.py` once per seed, with
that seed's report banked under `--out/seed-<n>/report.json`, so every number printed can
be read back out of a file this script did not write.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
TREE = HERE.parent.parent
CALIBRATE = TREE / "tests" / "routing_calibration" / "calibrate.py"
PYTHON = TREE / "scripts" / "laplace-python"


def one_seed(seed: int, labels: str, costs: str, out: pathlib.Path) -> dict:
    """Run calibrate.py at `seed`; return its report. The report file is kept."""
    target = out / ("seed-%d" % seed)
    target.mkdir(parents=True, exist_ok=True)
    report = target / "report.json"
    if not report.is_file():
        completed = subprocess.run(
            [str(PYTHON), str(CALIBRATE), "--labels", labels, "--costs", costs,
             "--out", str(target), "--seed", str(seed)],
            capture_output=True, text=True, cwd=str(TREE), check=False)
        if completed.returncode != 0 or not report.is_file():
            sys.stderr.write(completed.stdout[-3000:] + completed.stderr[-3000:])
            raise SystemExit("calibrate.py failed at seed %d" % seed)
    return json.loads(report.read_text())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", required=True)
    parser.add_argument("--costs", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--seeds", default="20261002,7,991,20260101,42,20251231")
    args = parser.parse_args()

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]

    reports = {seed: one_seed(seed, args.labels, args.costs, out) for seed in seeds}
    turn = reports[seeds[0]]["turn_chars"]
    sets = sorted(reports[seeds[0]]["d1"]["by_feature_set"])

    print("# the held-out cost rule across %d splits (one seed = one three-way split)" % len(seeds))
    print("# calibrate.three_way: random.Random(seed).shuffle(order); turn_chars = %d" % turn)
    print("# every number below is read back out of <out>/seed-<n>/report.json")
    print()
    width = max(len(s) for s in sets) + 1
    print("D1 held-out realised wrong-route cost, characters (* = under one turn)")
    print("  " + "feature set".ljust(width) + "".join(("%14s" % ("seed " + str(s))) for s in seeds)
          + "%14s" % "under a turn")
    for name in sets:
        cells, hits = [], 0
        for seed in seeds:
            held = reports[seed]["d1"]["by_feature_set"][name]["sweep_held_out"]
            under = held["realised_cost_under_one_turn"]
            hits += 1 if under else 0
            cells.append("%13s%s" % ("{:,}".format(held["realised_cost_chars"]),
                                     "*" if under else " "))
        print("  " + name.ljust(width) + "".join(cells) + "%14s" % ("%d/%d" % (hits, len(seeds))))

    print()
    print("per-seed: which feature sets pass the cost rule")
    for seed in seeds:
        passing = [n for n in sets
                   if reports[seed]["d1"]["by_feature_set"][n]["sweep_held_out"]
                   ["realised_cost_under_one_turn"]]
        print("  seed %-9d %d of %d pass: %s" % (seed, len(passing), len(sets),
                                                 ", ".join(passing) or "NONE"))

    print()
    print("spread per feature set (min / median / max over the %d splits)" % len(seeds))
    for name in sets:
        costs = [reports[seed]["d1"]["by_feature_set"][name]["sweep_held_out"]
                 ["realised_cost_chars"] for seed in seeds]
        print("  %s min %s  median %s  max %s  (%.1f to %.1f turns)"
              % (name.ljust(width), "{:,}".format(min(costs)),
                 "{:,}".format(int(statistics.median(costs))), "{:,}".format(max(costs)),
                 min(costs) / turn, max(costs) / turn))

    print()
    print("D1 accuracy and the precision when acting, held out, same splits")
    for name in sets:
        accs = [reports[seed]["d1"]["by_feature_set"][name]["accuracy"]["accuracy"]
                for seed in seeds]
        precs = [reports[seed]["d1"]["by_feature_set"][name]["sweep_held_out"]
                 ["precision_when_acting"] for seed in seeds]
        print("  %s accuracy %.4f-%.4f   precision when acting %.4f-%.4f"
              % (name.ljust(width), min(accs), max(accs), min(precs), max(precs)))

    print()
    print("the paired vocabulary comparison, same splits (homes vs each, discordant pairs)")
    for seed in seeds:
        paired = reports[seed]["d1"].get("paired") or []
        parts = ["%s vs %s %d-%d p=%.5f"
                 % (row["a"], row["b"], row["a_only_right"], row["b_only_right"],
                    row["p_two_sided_exact"]) for row in paired]
        print("  seed %-9d %s" % (seed, "; ".join(parts) if parts else "(no paired block)"))

    print()
    print("D4, held out, same splits")
    for seed in seeds:
        held = reports[seed]["d4"]["sweep_held_out"]
        print("  seed %-9d accuracy %.4f  acted %3d  wrong %2d  precision %.4f  cost %9s  under a turn %s"
              % (seed, reports[seed]["d4"]["accuracy"]["accuracy"], held["acted"], held["wrong"],
                 held["precision_when_acting"], "{:,}".format(held["realised_cost_chars"]),
                 held["realised_cost_under_one_turn"]))

    print()
    print("VERDICT lines, for the report to quote:")
    for name in sets:
        hits = sum(1 for seed in seeds
                   if reports[seed]["d1"]["by_feature_set"][name]["sweep_held_out"]
                   ["realised_cost_under_one_turn"])
        if hits == 0:
            print("  %s NEVER gets under one turn out of sample (0 of %d splits)"
                  % (name, len(seeds)))
        elif hits == len(seeds):
            print("  %s is under one turn out of sample at EVERY split (%d of %d)"
                  % (name, hits, len(seeds)))
        else:
            print("  %s is under one turn at %d of %d splits -- a property of the split, "
                  "not of the feature set" % (name, hits, len(seeds)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
