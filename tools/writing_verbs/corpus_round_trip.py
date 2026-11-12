#!/usr/bin/env python3
"""Measure the dispatch against the recorded corpus: is the round trip the identity?

``to_owner_call(from_owner_call(op, payload)) == (op, payload)`` for every replayable row
is the whole parity argument of this lane: an owner that receives the same pair cannot
behave differently.  This prints the partition instead of asserting one number, so a gap is
a named row and not a mood.

Usage: scripts/laplace-python tools/writing_verbs/corpus_round_trip.py [--corpus DIR] [--json OUT]
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
TREE = HERE.parents[2]
sys.path.insert(0, str(TREE / "src"))
from laplace.native import verbs as v   # noqa: E402

DEFAULT_CORPUS = Path("/home/phujck/VScodeProjects/laplace/evidence/"
                      "WRITING_RECONCILIATION_2026-10-02/harness/corpus")


def rows(corpus: Path):
    for name in ("failures", "reads", "writes", "arrival"):
        path = corpus / (name + ".jsonl")
        for line in path.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                row["_source"] = name
                yield row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    ap.add_argument("--json", default="")
    args = ap.parse_args()
    corpus = Path(args.corpus)
    total = replayable = 0
    kinds = collections.Counter()
    by_operation = collections.Counter()
    verb_door = collections.Counter()
    failures = []
    doors = collections.Counter()
    verbs = collections.Counter()
    altitudes = collections.Counter()
    for row in rows(corpus):
        total += 1
        if row.get("replayable", True) is False:
            continue
        replayable += 1
        operation = row.get("operation") or ""
        payload = row.get("payload") or {}
        doors[row.get("door")] += 1
        if row.get("door") != "tool":
            kinds["http-door (not a tool operation)"] += 1
            continue
        got = v.classify(operation, payload, project=row.get("project") or "")
        if got.route is None:
            kinds["unmapped"] += 1
            by_operation[operation] += 1
            failures.append({"id": row.get("id"), "operation": operation,
                             "why": got.reason, "kind": "unmapped"})
            continue
        verbs[got.route.verb] += 1
        altitudes[got.route.altitude] += 1
        if got.exact:
            kinds["exact"] += 1
        else:
            kinds["round-trip not exact"] += 1
            by_operation[operation] += 1
            failures.append({"id": row.get("id"), "operation": operation,
                             "why": got.reason, "kind": "not-exact",
                             "route": got.route.operation + "".join(
                                 " " + k + "=" + x for k, x in got.route.lift)})
        verb_door["reachable" if got.verb_door else "shim-only"] += 1
        if not got.verb_door:
            failures.append({"id": row.get("id"), "operation": operation,
                             "kind": "verb-door", "why": got.verb_door_reason})
    out = {"corpus_rows": total, "replayable": replayable, "doors": dict(doors),
           "round_trip": dict(kinds), "verb_door": dict(verb_door),
           "by_operation_when_not_exact": dict(by_operation),
           "verbs_used": dict(verbs), "altitudes_used": dict(altitudes),
           "routes": len(v.ROUTES), "pairs": len(v.BY_PAIR),
           "generated_from": v.GENERATED_FROM}
    print(json.dumps(out, indent=1))
    worst = [f for f in failures if f["kind"] != "verb-door"][:25]
    if worst:
        print("\nrows whose round trip is not the identity (first 25):")
        for row in worst:
            print(" ", json.dumps(row))
    shim = [f for f in failures if f["kind"] == "verb-door"]
    if shim:
        print("\nrows reachable only through their old name: %d" % len(shim))
        for row in sorted({(f["operation"], f["why"]) for f in shim}):
            print(" ", row[0], "--", row[1][:150])
    if args.json:
        Path(args.json).write_text(json.dumps({"summary": out, "rows": failures}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
