#!/usr/bin/env python3
"""Build this lane's allow list: the harness's own, plus ONE entry, from a measured run.

The entry is not chosen by hand. It is the first row of a previous run whose `bytes`
difference is the banked act ledger -- the lane's deliverable -- and nothing else is added.
If that run reports any other divergent path, this script refuses to write a list, because
an allow list assembled from a run it has not read is the thing the harness warns about.

Usage: scripts/laplace-python tools/writing_verbs/make_allow.py --rows <rows.jsonl>
           --out <allow.gate.json> [--path contract/talk.jsonl]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

HEAD = Path("/home/phujck/VScodeProjects/laplace/evidence/WRITING_RECONCILIATION_2026-10-02/"
            "harness/baseline/allow.head.json")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--path", default="contract/talk.jsonl")
    args = ap.parse_args()
    base = json.loads(HEAD.read_text())
    rows = [json.loads(line) for line in Path(args.rows).read_text().splitlines() if line.strip()]
    culprits = []
    other_paths = set()
    for row in rows:
        if "bytes" not in (row.get("differences") or row.get("diffs") or []):
            continue
        paths = row.get("bytes_differ_in") or row.get("bytes_paths") or []
        for path in paths:
            if path.endswith(args.path):
                culprits.append(row.get("id"))
            else:
                other_paths.add(path)
    if other_paths:
        print("REFUSING: the run also diverges in paths this entry is not about:",
              sorted(other_paths)[:8])
        return 1
    if not culprits:
        print("REFUSING: no row in this run reports a bytes difference in", args.path)
        return 1
    base.setdefault("rows", {})
    for ident in culprits:
        base["rows"][ident] = ["bytes"]
    base["note"] = (
        (base.get("note") or "") +
        " PLUS, for wave WRITING-RECONCILIATION-W1 packet altitude-dispatch: `bytes` on %d row(s) "
        "whose only divergent path is `%s`. Cause: the banked act row now carries verb, concept "
        "and altitude (src/laplace/writing_tools.py:986 and :1013), so the one file both sides "
        "write differs in its bytes while its row count and record kinds stay identical "
        "(176 rows and 4 kinds on both sides; evidence at wave1/altitude-dispatch/banked-row-diff/). "
        "Nothing else is allowed: no class, home or homes difference, and no other path."
        % (len(culprits), args.path))
    Path(args.out).write_text(json.dumps(base, indent=1))
    print("wrote", args.out, "rows allowed for bytes:", culprits)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
