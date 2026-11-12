#!/usr/bin/env python3
"""Every banked row's (verb, concept, altitude) is the ONE table's, or this exits non-zero.

    scripts/laplace-python tools/writing_verbs/banked_vocabulary.py \
        --talk <a sandbox>/contract/talk.jsonl [--talk ...] --out <dir>

The friction report's measurement: "the banked row carries the operation name, not the verb or
altitude" (writing_tools.py:959-971, :1000-1006).  The dispatch lane put the grain on the row;
the brief of this synthesis says the vocabulary it carries must be the table's.  That is a
checkable statement about real rows, so this checks it against real rows: every banked
`writing-tool-read` / `writing-tool-action` row that carries a grain must carry

  * a `verb` among the grammar's nine,
  * a `concept` the route table declares, with the altitude the concept's own `@` names, and
  * a (verb, concept) pair the table declares for the operation the row names.

A row with `dispatch: "unmapped"` is counted, not failed: that is the table saying it has no
row for that call, which is the honest answer and is what the `dispatch_reason` records.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE / "src"))

from laplace.core import grammar as g                   # noqa: E402
from laplace.native import verbs as v             # noqa: E402

KINDS = {"writing-tool-read", "writing-tool-action"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--talk", action="append", required=True)
    ap.add_argument("--out")
    args = ap.parse_args()

    rows: list[dict] = []
    for name in args.talk:
        path = Path(name)
        rows += [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                 if line.strip()]
    report = {"files": args.talk, "rows": len(rows), "writing_tool_rows": 0, "with_grain": 0,
              "unmapped": 0, "no_grain": 0, "turn_bound": 0, "no_turn": 0,
              "verbs": {}, "altitudes": {}, "concepts": 0, "offenders": []}
    verbs: Counter = Counter()
    altitudes: Counter = Counter()
    concepts: set[str] = set()
    declared = {(route.verb, route.concept) for route in v.ROUTES}
    for row in rows:
        if str(row.get("record")) not in KINDS:
            continue
        report["writing_tool_rows"] += 1
        if row.get("turn_id") is None:
            report["no_turn"] += 1
        else:
            report["turn_bound"] += 1
        if row.get("dispatch") == "unmapped":
            report["unmapped"] += 1
            continue
        if not row.get("verb"):
            report["no_grain"] += 1
            continue
        report["with_grain"] += 1
        verb, concept, altitude = row.get("verb"), row.get("concept"), row.get("altitude")
        operation = str(row.get("operation") or "")
        problems = []
        if verb not in g.VERBS:
            problems.append("verb is not one of the nine")
        if concept not in {route.concept for route in v.ROUTES}:
            problems.append("concept is not in the table")
        elif altitude != str(concept).split("@")[1]:
            problems.append("altitude is not the concept's own")
        if (verb, concept) not in declared:
            problems.append("(verb, concept) is not a declared pair")
        elif operation and (verb, concept) not in set(v.pairs_for(operation)):
            problems.append("the pair is not one of the acts of %r" % operation)
        if problems:
            report["offenders"].append({"id": row.get("id"), "operation": operation,
                                        "verb": verb, "concept": concept,
                                        "altitude": altitude, "problems": problems})
        verbs[str(verb)] += 1
        altitudes[str(altitude)] += 1
        concepts.add(str(concept))
    report["verbs"] = dict(sorted(verbs.items()))
    report["altitudes"] = dict(sorted(altitudes.items()))
    report["concepts"] = len(concepts)
    report["concept_list"] = sorted(concepts)
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "banked_vocabulary.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({key: report[key] for key in
                      ("rows", "writing_tool_rows", "with_grain", "unmapped", "no_grain",
                       "turn_bound", "no_turn", "verbs", "altitudes", "concepts")},
                     ensure_ascii=False, indent=1))
    print("offenders (a grain the table does not declare): %d" % len(report["offenders"]))
    for row in report["offenders"][:10]:
        print("  ", json.dumps(row, ensure_ascii=False))
    print("THE BANKED VOCABULARY IS THE TABLE'S" if not report["offenders"]
          else "A BANKED ROW CARRIES A GRAIN THE TABLE DOES NOT DECLARE")
    return 1 if report["offenders"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
