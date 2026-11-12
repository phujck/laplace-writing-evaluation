"""One instrument for every rule-and-guard number this synthesis reports.

Round 4 of this packet existed partly because three numbers for two facts were printed from
three ad-hoc commands: the gate gap was 14 in one output and 15 in another (the first iterated
only the tool registry), and the `shape` count was 188 in one residual, 193 in a section and
195 in a census (the last counted the HTTP declarations' rules too).  So the counts have one
producer, it says which population each number is over, and it reconciles the gate gap itself.

Run: scripts/laplace-python tools/rule_census.py --out <dir>
  --out writes <dir>/rule_census.out and <dir>/gate_gap.out from the SAME measurement.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

TREE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TREE / "src"))

from laplace.core import grammar as g  # noqa: E402
from laplace.core import identity_doors as idd  # noqa: E402
from laplace.native import declarations as wdl  # noqa: E402
from laplace.native import declared as writing_declared  # noqa: E402,F401
from laplace.web import writing_declared_http  # noqa: E402,F401


def gate_pairs() -> dict[tuple[str, str], str]:
    """(operation, guard) -> the gate key that routes it.

    A gate key is the OPERATION plus, for two doors, the half of it being guarded
    (`section_change plan`).  The HTTP declarations name their operation by route
    (`review/adjudicate`), and the gate keys the tool operation the route calls, so the two
    spellings are reconciled explicitly below rather than counted as a gap.
    """
    out: dict[tuple[str, str], str] = {}
    for key, shim in idd.DOORS.items():
        operation = key.split()[0]
        for guard in shim.guard_to_home:
            out[(operation, guard)] = key
    return out


# The HTTP route whose declaration names its own operation, and the tool operation whose gate
# key routes it.  `/review/adjudicate` POST calls `review_surface.adjudicate`
# (src/laplace/review_surface.py:3508 -> :1394), and that function is where the gate is called
# (:1873, key `apply_revision`), so the pair is routed; only the NAME differs.
SAME_DOOR_UNDER_TWO_NAMES = {("review/adjudicate", "before"): ("apply_revision", "before")}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    tool_rules = [rule for dec in wdl.DECLARATIONS.values() for rule in dec.rules]
    http_rules = [rule for dec in wdl.HTTP_DECLARATIONS.values() for rule in dec.rules]
    census: list[str] = []
    census.append("declarations: tool %d  http %d"
                  % (len(wdl.DECLARATIONS), len(wdl.HTTP_DECLARATIONS)))
    census.append("TOOL-DOOR rules: %d  by kind %s"
                  % (len(tool_rules), dict(sorted(Counter(r.kind for r in tool_rules).items()))))
    census.append("HTTP-DOOR rules: %d  by kind %s"
                  % (len(http_rules), dict(sorted(Counter(r.kind for r in http_rules).items()))))
    census.append("ALL rules: %d  by kind %s"
                  % (len(tool_rules) + len(http_rules),
                     dict(sorted(Counter(r.kind for r in tool_rules + http_rules).items()))))
    identity = [r for r in tool_rules + http_rules if r.kind == "identity"]
    census.append("identity rules: %d  distinct (op,field,home): %d"
                  % (len(identity),
                     len({(op, r.field, r.home)
                          for reg in (wdl.DECLARATIONS, wdl.HTTP_DECLARATIONS)
                          for op, dec in reg.items() for r in dec.rules
                          if r.kind == "identity"})))
    homes = Counter(r.home for r in identity)
    census.append("homes named by an identity rule: %d %s" % (len(homes), dict(homes.most_common())))
    census.append("handlers resolved: %d distinct lines over %d operations"
                  % (len({dec.handler for dec in wdl.DECLARATIONS.values()}),
                     len(wdl.DECLARATIONS)))
    census.append("shims: %d gate keys in identity_doors; %d registered in the grammar"
                  % (len(idd.DOORS), len(g.SHIMS)))
    census.append("shim expiries: %s" % sorted({shim.expiry for shim in g.SHIMS.values()}))

    gate = gate_pairs()
    contract: dict[tuple[str, str], str] = {}
    for registry, label in ((wdl.DECLARATIONS, "tool"), (wdl.HTTP_DECLARATIONS, "http")):
        for operation, declaration in registry.items():
            for rule in declaration.rules:
                if rule.kind == "identity" and rule.field:
                    contract[(operation, rule.field)] = label
    both = sorted(set(gate) & set(contract))
    gate_only = sorted(set(gate) - set(contract))
    raw_contract_only = sorted(set(contract) - set(gate))
    aliased = [pair for pair in raw_contract_only if pair in SAME_DOOR_UNDER_TWO_NAMES]
    contract_only = [pair for pair in raw_contract_only if pair not in SAME_DOOR_UNDER_TWO_NAMES]

    gap: list[str] = []
    gap.append("gate (operation, guard) pairs: %d" % len(gate))
    gap.append("contract (operation, field) identity pairs: %d  (tool %d, http %d)"
               % (len(contract), sum(1 for v in contract.values() if v == "tool"),
                  sum(1 for v in contract.values() if v == "http")))
    gap.append("declared AND routed through the gate: %d" % len(both))
    gap.append("routed but not declared: %d %s" % (len(gate_only), gate_only))
    gap.append("declared but not routed through the gate: %d" % len(contract_only))
    for operation, field in contract_only:
        homes_named = sorted({r.home for reg in (wdl.DECLARATIONS, wdl.HTTP_DECLARATIONS)
                              for op, dec in reg.items() if op == operation
                              for r in dec.rules
                              if r.kind == "identity" and r.field == field})
        gap.append("   %-26s %-26s %s" % (operation, field, homes_named))
    gap.append("the same door under two names (counted as ROUTED, not as a gap): %d" % len(aliased))
    for pair in aliased:
        gap.append("   %s %s  is routed by the gate key %r: %s"
                   % (pair[0], pair[1], gate.get(SAME_DOOR_UNDER_TWO_NAMES[pair], "?"),
                      "POST /review/adjudicate calls review_surface.adjudicate "
                      "(src/laplace/review_surface.py:3508 -> :1394), which calls the gate "
                      "at :1873"))
    gap.append("gate keys: %s" % sorted(idd.DOORS))

    text = "\n".join(census) + "\n\n" + "\n".join(gap) + "\n"
    print(text, end="")
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "rule_census.out").write_text(text, encoding="utf-8")
        (out / "gate_gap.out").write_text("\n".join(gap) + "\n", encoding="utf-8")
        print("wrote %s/rule_census.out and %s/gate_gap.out" % (out, out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
