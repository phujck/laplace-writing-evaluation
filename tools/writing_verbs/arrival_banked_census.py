#!/usr/bin/env python3
"""The census of what the arrival BANKED, taken from a kept arrival sandbox's act ledger.

    scripts/laplace-python tools/writing_verbs/arrival_banked_census.py \
        --talk <arrival --keep work>/sandbox/contract/talk.jsonl --out <evidence>/arrival-head

The arrival (`harness/arrival.py`) scores what a new caller PAYS; this scores what the same run
LEFT BEHIND, which is this lane's deliverable: a `(verb, concept, altitude)` row on a caller path
that has no provider turn at all.  It was a hand-run census the first time and is a script now, so
the number in the report names the run and the commit it was taken at (the judge's third
deficiency: a measurement deposited without its commit is not a measurement a reader can re-take).
"""
from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--talk", required=True, help="the kept sandbox's contract/talk.jsonl")
    ap.add_argument("--tree", default=".", help="the tree whose HEAD the arrival ran")
    ap.add_argument("--out", help="directory to write arrival_banked_rows.json into")
    args = ap.parse_args()

    path = Path(args.talk).resolve()
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    kinds: Counter = Counter()
    verbs: Counter = Counter()
    altitudes: Counter = Counter()
    dispatch: Counter = Counter()
    concepts: set[str] = set()
    with_grain = turn_null = 0
    for row in rows:
        kinds[str(row.get("record"))] += 1
        if row.get("turn_id") is None:
            turn_null += 1
        if row.get("verb") and row.get("concept"):
            with_grain += 1
            verbs[str(row.get("verb"))] += 1
            altitudes[str(row.get("altitude"))] += 1
            dispatch[str(row.get("dispatch"))] += 1
            concepts.add(str(row.get("concept")))
    head = subprocess.run(["git", "-C", str(Path(args.tree).resolve()), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    report = {"rows": len(rows), "kinds": dict(kinds), "with_grain": with_grain,
              "turn_id_null": turn_null, "verbs": dict(verbs), "altitudes": dict(altitudes),
              "concepts": sorted(concepts), "dispatch": dict(dispatch),
              "head": head, "ledger": str(path),
              "without_grain_kinds": {k: n for k, n in sorted(kinds.items())
                                      if not any(r.get("verb") for r in rows
                                                 if r.get("record") == k)}}
    print(json.dumps(report, indent=1))
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "arrival_banked_rows.json").write_text(json.dumps(report, indent=1) + "\n")
        print("\nwritten", out / "arrival_banked_rows.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
