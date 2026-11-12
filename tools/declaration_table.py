"""The declaration table, and the accounting of what the migration carried.

    scripts/laplace-python tools/declaration_table.py --out <dir>

Writes `declaration_table.csv` (one row per operation: verb, concept, altitude, the
homes it guards, rule counts by kind, the handler line, help size before and after) and
`accounting.json` (every clause of the base commit's contract table, counted by where
it went).  Every figure the report quotes about this lane comes from here, so no number
in it is typed by hand.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "src"))

from laplace.core import grammar as g                                   # noqa: E402
from laplace.native import declarations as d                      # noqa: E402
from laplace.writing import reads
from laplace.native.declarations import DECLARATIONS, clauses      # noqa: E402

FIXTURE = HERE / "tests/grammar_spec/head_contract_prose.json"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--before", default="")
    parser.add_argument("--after", default="")
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    def sizes(path):
        if not path:
            return {}
        return {row["operation"]: int(row["chars"])
                for row in csv.DictReader(Path(path).open(encoding="utf-8"))}

    before, after = sizes(args.before), sizes(args.after)
    rows = []
    kinds = collections.Counter()
    for operation in sorted(DECLARATIONS):
        declaration = DECLARATIONS[operation]
        per_kind = collections.Counter(rule.kind for rule in declaration.rules)
        kinds.update(per_kind)
        rows.append({
            "operation": operation,
            "verb": declaration.verb,
            "concept": declaration.concept,
            "altitude": declaration.altitude,
            "also_pairs": len(declaration.also),
            "homes": "|".join(declaration.homes),
            "identity_rules": per_kind["identity"],
            "other_rules": sum(per_kind.values()) - per_kind["identity"],
            "effects": len(declaration.effects),
            "variants": len(d.variants(operation)),
            "turn_bound": declaration.turn_bound,
            "handler": declaration.handler,
            "help_before": before.get(operation, ""),
            "help_after": after.get(operation, ""),
        })
    with (out / "declaration_table.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    contracts = json.loads(FIXTURE.read_text(encoding="utf-8"))["contracts"]
    counted = collections.Counter()
    for operation, contract in contracts.items():
        declaration = DECLARATIONS[operation]
        said = {rule.says for rule in declaration.rules}
        summary = clauses(contract.get("summary") or "")
        if summary:
            counted["summary clauses"] += len(summary)
            counted["summary -> does"] += 1
            counted["summary -> rule"] += sum(1 for c in summary[1:] if c in said)
        for text in contract.get("preconditions") or []:
            parts = clauses(text)
            counted["precondition strings"] += 1
            counted["precondition clauses"] += len(parts)
            counted["precondition -> rule"] += sum(1 for c in parts if c in said)
        for key, held in (("outputs", declaration.outputs),
                          ("recoverable_errors", declaration.recoverable),
                          ("errors", declaration.errors)):
            for text in contract.get(key) or []:
                parts = clauses(text)
                counted["%s clauses" % key] += len(parts)
                counted["%s carried" % key] += sum(1 for c in parts if c in held)
        for key in ("next_steps", "recovery", "scope_rules", "source_locator_recipe"):
            if key in contract:
                counted["extra %s carried" % key] += int(key in declaration.extras)
        counted["example deleted"] += int("example" in contract)
        counted["examples deleted"] += int("examples" in contract)

    homes = collections.Counter()
    for declaration in DECLARATIONS.values():
        for raw in declaration.homes:
            homes[raw.rstrip("?")] += 1
    accounting = {
        "operations": len(DECLARATIONS),
        "http_doors": len(d.HTTP_DECLARATIONS),
        "rules_by_kind": dict(sorted(kinds.items(), key=lambda kv: -kv[1])),
        "rules_total": sum(kinds.values()),
        "clauses": dict(sorted(counted.items())),
        "operations_guarding_a_home": sum(1 for x in DECLARATIONS.values() if x.homes),
        "home_kinds_guarded": len(homes),
        "home_kinds_guarded_by_operations": dict(sorted(homes.items(),
                                                        key=lambda kv: -kv[1])),
        "declared_pairs": len({pair for x in DECLARATIONS.values() for pair in x.pairs}),
        "verbs_used": sorted({x.verb for x in DECLARATIONS.values()}),
        "verbs_in_the_alphabet": list(g.VERBS),
        "operations_in_tree": len(reads.READS | reads.WRITES),
    }
    if before and after:
        ops = [k for k in before if not k.startswith("(")]
        accounting["help_total_before"] = sum(before[k] for k in ops)
        accounting["help_total_after"] = sum(after[k] for k in ops)
        accounting["help_catalogue_before"] = before["(catalogue: help with no operation)"]
        accounting["help_catalogue_after"] = after["(catalogue: help with no operation)"]
        accounting["help_grew"] = sum(1 for k in ops if after[k] > before[k])
        accounting["help_shrank"] = sum(1 for k in ops if after[k] < before[k])
    (out / "accounting.json").write_text(json.dumps(accounting, ensure_ascii=False, indent=1),
                                         encoding="utf-8")
    print(json.dumps(accounting, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
