#!/usr/bin/env python3
"""Re-evaluate a banked run's rows against an allow list, with the harness's own rule.

The gate run was made with the stock `allow.head.json`, so its one expected difference came
back as unallowed and `parity` is False in that file. Rather than claim an exit code from a
run that was not made, this re-applies `replay.allowed` -- the oracle's own function, imported
from the harness, not reimplemented -- to the deposited rows, and prints what the verdict is
under this lane's list. Every difference of every kind is counted, not only the one looked for.

Usage: scripts/laplace-python tools/writing_verbs/check_allow.py --rows <rows.jsonl>
           --allow <allow.gate.json> [--out verdict.json]
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

HARNESS = Path("/home/phujck/VScodeProjects/laplace/evidence/"
               "WRITING_RECONCILIATION_2026-10-02/harness")
sys.path.insert(0, str(HARNESS))
import replay as oracle                               # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", required=True)
    ap.add_argument("--allow", required=True)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    allow = json.loads(Path(args.allow).read_text())
    rows = [json.loads(line) for line in Path(args.rows).read_text().splitlines()
            if line.strip()]
    kinds = collections.Counter()
    unallowed = []
    paths = collections.Counter()
    for row in rows:
        for kind in (row.get("diffs") or []):
            kinds[kind] += 1
            if not oracle.allowed(allow, row, kind):
                unallowed.append({"id": row.get("id"), "operation": row.get("operation"),
                                  "source": row.get("source"), "kind": kind,
                                  "paths": row.get("bytes_paths")})
        for path in (row.get("bytes_paths") or []):
            paths[path] += 1
    verdict = {"rows": len(rows), "difference_by_kind": dict(kinds),
               "bytes_divergent_paths": dict(paths),
               "unallowed": unallowed, "unallowed_total": len(unallowed),
               "parity_under_this_allow_list": not unallowed,
               "allow_rows": sorted((allow.get("rows") or {}).items())[:40],
               "function": "replay.allowed, imported from the harness"}
    print(json.dumps({k: v for k, v in verdict.items() if k != "allow_rows"}, indent=1))
    if args.out:
        Path(args.out).write_text(json.dumps(verdict, indent=1))
    return 0 if not unallowed else 1


if __name__ == "__main__":
    sys.exit(main())
