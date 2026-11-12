"""Did the repair make LESS prose, or the same prose with addresses?

    scripts/laplace-python tools/prose_relocation.py --base-src <base src> --out <dir>

This tool exists because this lane claimed the former and the measurement says the
latter.  The claim under test was "the repair is not more prose; it is less".  Three
numbers decide it, and all three are computed here rather than argued:

1. **PROSE CHARS.**  The base table's prose is `summary` + every `preconditions`
   string.  The declared prose is every declaration's `does` + every `Rule.says`.
   Nothing else on either side is prose: schemas, outputs, enums and `expected` rows
   are data.
2. **VERBATIM RELOCATION.**  For each rule, is its `says` string a substring of that
   operation's own base prose?  A verbatim rule is prose that MOVED and acquired a
   field, a home and a line.  A non-verbatim one is prose that was rewritten.
3. **WHERE THE -77,271 CHARACTERS OF HELP ACTUALLY WENT.**  Per base operation, the
   size of the owner-contract duplicate (`requested_payload_contract` beside
   `action.owner_contract`), of the hand-written `example`/`examples` values, and of
   the rest.  The help total can only fall by what was deleted; if prose grew, the
   fall is attributable to the deletions and the bounding, and the report must say so.

`--base-src` is a `src` directory of the base commit, so the base response is built
by the base code and not reconstructed.  The base contract table is read from the git
blob through `migrate_declarations.contracts_at`, which refuses a blob that is this
packet's own projection.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "src"))
sys.path.insert(0, str(HERE / "tools"))

CAMPAIGN_BASE = "706a82047ae90ce79956cb25a4831973f61eec85"

BASE_PROBE = r'''
import json, sys
sys.path.insert(0, %(src)r)
from laplace.writing import operating as writing_operating
from laplace.native.contracts import exact_contract
from laplace.native import tools as wt
def size(v):
    return len(json.dumps(v, ensure_ascii=False, default=str))
contract = writing_operating.tool_contract()
permitted = set(contract["role_permissions"]["work"])
rows = {}
for op in sorted(wt.READS | wt.WRITES):
    owner = contract["operation_payload_contracts"].get(op)
    action = exact_contract(op, permitted=op in permitted, owner_contract=owner)
    response = {"schema_version": writing_operating.VERSION, "digest": contract["digest"],
                "requested_operation": op, "requested_payload_contract": owner,
                "action": action}
    dup = (size(owner) if owner is not None else 0) + (
        size(action["owner_contract"]) if isinstance(action, dict) and "owner_contract" in action else 0)
    ex = 0
    if isinstance(action, dict):
        for key in ("example", "examples"):
            if key in action:
                ex += size(action[key]) + len(key) + 4
    rows[op] = {"total": size(response), "duplicate": dup, "examples": ex}
print(json.dumps(rows))
'''


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-src", required=True)
    parser.add_argument("--base", default=CAMPAIGN_BASE)
    parser.add_argument("--out", required=True)
    parser.add_argument("--project", default="synthetics-foundations")
    args = parser.parse_args(argv)

    from migrate_declarations import contracts_at
    base = contracts_at(args.base)
    from laplace.native.declarations import DECLARATIONS

    # 1. prose characters, both sides
    prose_base = 0
    prose_now = 0
    base_prose_text = {}
    for operation, entry in base.items():
        preconditions = list(entry.get("preconditions") or [])
        summary = entry.get("summary") or ""
        prose_base += sum(len(s) for s in preconditions) + len(summary)
        base_prose_text[operation] = " || ".join(preconditions + [summary])
    for operation, declaration in DECLARATIONS.items():
        prose_now += len(declaration.does or "")
        prose_now += sum(len(rule.says or "") for rule in declaration.rules)

    # 2. verbatim relocation, by kind
    by_kind: dict[str, dict[str, int]] = {}
    rewritten = []
    for operation, declaration in DECLARATIONS.items():
        for rule in declaration.rules:
            says = (rule.says or "").strip().rstrip(".")
            bucket = by_kind.setdefault(rule.kind, {"rules": 0, "verbatim": 0})
            bucket["rules"] += 1
            if says and says in base_prose_text.get(operation, ""):
                bucket["verbatim"] += 1
            else:
                rewritten.append({"operation": operation, "kind": rule.kind,
                                  "field": rule.field, "says": says[:110]})
    rules_total = sum(b["rules"] for b in by_kind.values())
    verbatim_total = sum(b["verbatim"] for b in by_kind.values())

    # 3. where the help characters went
    probe = subprocess.run([sys.executable, "-c",
                            BASE_PROBE % {"src": str(Path(args.base_src).resolve())}],
                           capture_output=True, text=True)
    if probe.returncode != 0:
        raise SystemExit("base probe failed:\n" + probe.stderr[-2000:])
    base_sizes = json.loads(probe.stdout)
    duplicate = sum(row["duplicate"] for row in base_sizes.values())
    examples = sum(row["examples"] for row in base_sizes.values())
    base_total = sum(row["total"] for row in base_sizes.values())

    # the declared side, measured by the same response shape, under both projects:
    # the base `exact_contract` takes no project, so only this column moves.
    from laplace.writing import operating as writing_operating
    from laplace.native.declarations import help_payload
    contract = writing_operating.tool_contract()
    permitted = set(contract["role_permissions"]["work"])

    def declared_total(project: str) -> int:
        total = 0
        for operation in sorted(base):
            action = help_payload(operation, permitted=operation in permitted,
                                  project=project, root=str(HERE) if project else None)
            total += len(json.dumps(
                {"schema_version": writing_operating.VERSION, "digest": contract["digest"],
                 "requested_operation": operation, "action": action},
                ensure_ascii=False, default=str))
        return total

    declared_no_project = declared_total("")
    declared_with_project = declared_total(args.project)
    fall_no_project = base_total - declared_no_project
    fall_with_project = base_total - declared_with_project

    report = {
        "base": args.base,
        "base_src": str(Path(args.base_src).resolve()),
        "prose": {"base_summary_plus_preconditions": prose_base,
                  "declared_does_plus_rule_says": prose_now,
                  "delta": prose_now - prose_base,
                  "percent": round(100.0 * (prose_now - prose_base) / prose_base, 1)},
        "relocation": {"rules": rules_total, "verbatim_in_base_prose": verbatim_total,
                       "by_kind": by_kind,
                       "rewritten_examples": rewritten[:12]},
        "help_characters": {
            "base_total_73": base_total,
            "declared_total_73_no_project": declared_no_project,
            "declared_total_73_project": declared_with_project,
            "project": args.project,
            "minted_tokens_cost": declared_with_project - declared_no_project,
            "fall_no_project": fall_no_project,
            "fall_with_project": fall_with_project,
            "owner_contract_duplicate": duplicate,
            "hand_written_examples": examples,
            "two_deletions_together": duplicate + examples,
            "deletions_as_share_of_the_fall_percent": round(
                100.0 * (duplicate + examples) / fall_with_project, 1),
            "net_cost_of_what_the_lane_added": (duplicate + examples) - fall_with_project},
        "cap": {"chars": 159, "rules_over_cap": sum(
            1 for d in DECLARATIONS.values() for r in d.rules if len(r.says or "") > 159)},
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "prose_relocation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    print("PROSE          base(summary+preconditions) %d   declared(does+rule says) %d   %+d (%+.1f%%)"
          % (prose_base, prose_now, prose_now - prose_base, report["prose"]["percent"]))
    print("RELOCATION     rules %d   verbatim in that operation's own base prose %d"
          % (rules_total, verbatim_total))
    for kind in sorted(by_kind):
        print("    %-10s rules %3d  verbatim %3d"
              % (kind, by_kind[kind]["rules"], by_kind[kind]["verbatim"]))
    print("CAP            rules over 159 chars: %d" % report["cap"]["rules_over_cap"])
    print("HELP           base 73-operation total %d" % base_total)
    print("    declared %d with no project, %d with %s (minted tokens cost %+d)"
          % (declared_no_project, declared_with_project, args.project,
             declared_with_project - declared_no_project))
    print("    the fall: %d with the project, %d with none"
          % (fall_with_project, fall_no_project))
    print("    owner-contract duplicate %d   hand-written examples %d   together %d"
          % (duplicate, examples, duplicate + examples))
    print("    the two deletions are %.1f%% of the fall; everything this lane ADDED "
          "costs %+d back"
          % (100.0 * (duplicate + examples) / fall_with_project,
             (duplicate + examples) - fall_with_project))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
