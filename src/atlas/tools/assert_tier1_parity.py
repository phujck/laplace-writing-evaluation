"""assert_tier1_parity - the Phase 3 run's Tier-1 arms must land on their BANKED Phase 2 verdicts.

    PYTHONPATH=src python3 -m atlas.tools.assert_tier1_parity \\
        --phase2 atlas/bench/runs/2026-08-01/bench-filtered \\
        --phase3 atlas/bench/runs/2026-08-01-phase3/bench-filtered

TWO CLAIMS AT ONCE, which is why this exists as its own command.

1. DETERMINISM. The Phase 2 judge asked that the determinism re-run stay in the habit of every
   run. Re-running the same five arms over the same frozen bundle months or minutes later must
   reproduce the same rows; if it does not, the instrument is measuring the clock.

2. THE RANK COLUMNS ARE ADDITIVE. Phase 3 adds ``ground_truth_rank`` and ``first_hit_rank`` to
   every row. That means ``rows_digest`` CANNOT match by construction - a new field changes the
   hash - so a digest comparison would either fail meaninglessly or tempt someone to exclude the
   new fields from the digest, which would put them permanently outside the tamper check. Instead
   the comparison is PER FIELD over the fields the two runs share. A Phase 3 row must agree with
   its Phase 2 row on every one of them, and the new columns are exactly the difference.

The banked Phase 2 run directory is READ-ONLY here and is never rewritten: those rows are judged
(``SEV-20260801-atlas-phase2-r2``) and immutable.

Exit 0 when every shared field of every Tier-1 row agrees. Exit 1 naming the first disagreements,
because a determinism failure that prints a summary is a determinism failure nobody reads.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ..bench.arms import TIER_1
from ..store import read_jsonl

#: Wall-clock by nature; exempt from the comparison exactly as the determinism gate exempts it.
WALL_CLOCK_FIELDS = ("latency_ms",)

#: The Phase 3 additions. Their PRESENCE is asserted; their values have no Phase 2 counterpart.
PHASE_3_FIELDS = ("ground_truth_rank", "first_hit_rank")


def load(run_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = list(read_jsonl(Path(run_dir) / "rows.jsonl"))
    manifest = json.loads((Path(run_dir) / "manifest.json").read_text(encoding="utf-8"))
    return rows, manifest


def compare(phase2: list[dict[str, Any]], phase3: list[dict[str, Any]]
            ) -> tuple[list[str], dict[str, Any]]:
    """Per-field comparison over the Tier-1 rows the two runs share. Returns (problems, stats)."""
    problems: list[str] = []
    index2 = {(r["task"], r["arm"]): r for r in phase2}
    index3 = {(r["task"], r["arm"]): r for r in phase3}
    tier1_keys = sorted(k for k in index2 if k[1] in TIER_1)

    missing = [k for k in tier1_keys if k not in index3]
    for key in missing:
        problems.append(f"MISSING from phase 3: task={key[0]} arm={key[1]}")

    compared_rows = 0
    compared_fields = 0
    for key in tier1_keys:
        if key not in index3:
            continue
        a, b = index2[key], index3[key]
        compared_rows += 1
        for field in sorted(set(a) & set(b)):
            if field in WALL_CLOCK_FIELDS:
                continue
            compared_fields += 1
            if a[field] != b[field]:
                problems.append(
                    f"DISAGREES task={key[0]} arm={key[1]} field={field}: "
                    f"phase2={a[field]!r} phase3={b[field]!r}")
        for field in PHASE_3_FIELDS:
            if field not in b:
                problems.append(f"phase 3 row lacks the additive column {field}: "
                                f"task={key[0]} arm={key[1]}")
        extra = sorted(set(b) - set(a) - set(PHASE_3_FIELDS))
        if extra:
            problems.append(f"UNDECLARED new field(s) on task={key[0]} arm={key[1]}: {extra}")

    correctness2 = {arm: sum(1 for r in phase2 if r["arm"] == arm and r["correct"])
                    for arm in TIER_1}
    correctness3 = {arm: sum(1 for r in phase3 if r["arm"] == arm and r["correct"])
                    for arm in TIER_1}
    for arm in TIER_1:
        if correctness2[arm] != correctness3[arm]:
            problems.append(f"CORRECT-COUNT MOVED for {arm}: "
                            f"phase2={correctness2[arm]} phase3={correctness3[arm]}")
    return problems, {
        "tier1_rows_compared": compared_rows,
        "fields_compared": compared_fields,
        "phase2_correct": correctness2,
        "phase3_correct": correctness3,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="assert the Phase 3 Tier-1 rows reproduce the banked Phase 2 verdicts")
    ap.add_argument("--phase2", type=Path, required=True)
    ap.add_argument("--phase3", type=Path, required=True)
    args = ap.parse_args(argv)

    rows2, man2 = load(args.phase2)
    rows3, man3 = load(args.phase3)
    if man2["bundle_id"] != man3["bundle_id"]:
        print(f"REFUSED the two runs are over different bundles: "
              f"{man2['bundle_id']} vs {man3['bundle_id']}", file=sys.stderr)
        return 1
    if man2["universe"]["name"] != man3["universe"]["name"]:
        print(f"REFUSED the two runs are over different universes: "
              f"{man2['universe']['name']} vs {man3['universe']['name']}", file=sys.stderr)
        return 1

    problems, stats = compare(rows2, rows3)
    print(f"# Tier-1 determinism parity: phase 2 {args.phase2} -> phase 3 {args.phase3}")
    print(f"  bundle          {man2['bundle_id']}")
    print(f"  universe        {man2['universe']['name']}")
    print(f"  rows compared   {stats['tier1_rows_compared']} "
          f"({stats['fields_compared']} shared field comparisons, "
          f"exempt: {', '.join(WALL_CLOCK_FIELDS)})")
    for arm in TIER_1:
        mark = "OK " if stats["phase2_correct"][arm] == stats["phase3_correct"][arm] else "MOVED"
        print(f"  {mark} {arm:<16} banked {stats['phase2_correct'][arm]:>2}/21  "
              f"re-run {stats['phase3_correct'][arm]:>2}/21")
    print(f"  phase 3 adds    {', '.join(PHASE_3_FIELDS)} (additive; no phase 2 counterpart)")
    if problems:
        print(f"\nPARITY VIOLATED ({len(problems)}):", file=sys.stderr)
        for line in problems[:40]:
            print(f"  {line}", file=sys.stderr)
        return 1
    print("\nPARITY GREEN - every shared field of every Tier-1 row is identical to the banked "
          "Phase 2 run, and the only difference is the two additive rank columns.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
