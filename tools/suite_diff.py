"""Which test failures are this lane's, and which were already there.

    scripts/laplace-python tools/suite_diff.py --mine <tests.out> --base <tests.out> \
        --out <dir>

The suite is not green at the base commit: 215 of 7,251 tests fail at `706a8204`. A
lane that reports "the suite has 214 failures" has said nothing; what matters is the
SET DIFFERENCE, and that is what this computes, by test id, from the two `-q` runs.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

FAILED = re.compile(r"^(?:FAILED|ERROR) (\S+)")


def ids(path: Path) -> set[str]:
    return {match.group(1) for line in path.read_text(encoding="utf-8").splitlines()
            if (match := FAILED.match(line))}


def totals(path: Path) -> str:
    for line in reversed(path.read_text(encoding="utf-8").splitlines()):
        if " passed" in line or " failed" in line:
            return line.strip()
    return ""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mine", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    mine, base = ids(Path(args.mine)), ids(Path(args.base))
    new = sorted(mine - base)
    fixed = sorted(base - mine)
    payload = {
        "mine_totals": totals(Path(args.mine)),
        "base_totals": totals(Path(args.base)),
        "mine_failures": len(mine), "base_failures": len(base),
        "new_failures_introduced_by_this_lane": new,
        "failures_this_lane_removed": fixed,
        "shared_pre_existing_failures": len(mine & base),
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "suite_diff.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                                        encoding="utf-8")
    print("mine:", payload["mine_totals"])
    print("base:", payload["base_totals"])
    print("pre-existing failures present in both: %d" % payload["shared_pre_existing_failures"])
    print("NEW failures this lane introduces: %d" % len(new))
    for test in new:
        print("   +", test)
    print("failures this lane removes: %d" % len(fixed))
    for test in fixed[:12]:
        print("   -", test)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
