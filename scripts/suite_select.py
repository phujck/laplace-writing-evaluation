"""The close's suite selector, on the command line — what would the next close run?

    python scripts/suite_select.py                  # the plan for the live delta
    python scripts/suite_select.py --json           # the same, machine-readable
    python scripts/suite_select.py --since <ref>    # measure from an explicit commit
    python scripts/suite_select.py --rebuild        # force the map to rebuild, timed
    python scripts/suite_select.py --full           # the jubilee (prints FULL and why)
    python scripts/suite_select.py --runs           # the banked instrument rows

The plan is advisory here; `scripts/sewup.py` step_suite is where it becomes the run.
Exit 0 always — this reports, it does not gate.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main(argv: list[str]) -> int:
    from laplace.engine import suite_map as sm

    if "--runs" in argv:
        p = ROOT / sm.RUNS_REL
        print(p.read_text(encoding="utf-8") if p.is_file() else f"no rows yet at {sm.RUNS_REL}")
        return 0

    since = None
    if "--since" in argv:
        since = argv[argv.index("--since") + 1]

    pl = sm.plan(ROOT, since=since, force_full="--full" in argv, rebuild="--rebuild" in argv)

    if "--json" in argv:
        print(json.dumps(pl, indent=1))
        return 0

    c = pl["map_counts"]
    print(f"map: {pl['map_state']} — {c['tests']} test files, {c['first_party_files']} "
          f"first-party files, {c.get('hard_edges')} hard + {c.get('lazy_edges')} lazy "
          f"import edges, {c['literals']} path literals")
    print(f"since: {pl['since']}  head: {pl['head']}  chain_depth: {pl['chain_depth']}  "
          f"moved: {pl['moved']}")
    print(f"MODE: {pl['mode'].upper()}")
    if pl["mode"] == "full":
        for r in pl["full_reasons"][:20]:
            print(f"  full because  {r}")
        extra = len(pl["full_reasons"]) - 20
        if extra > 0:
            print(f"  ... +{extra} more reasons")
    else:
        print(f"  {len(pl['selected'])} shard(s) selected:")
        for t in pl["selected"]:
            print(f"    {t}   <- {pl['reasons'][t][0]}")
    if pl["uncovered"]:
        print(f"  uncovered (first-party code no test reaches): {len(pl['uncovered'])}")
        for u in pl["uncovered"][:10]:
            print(f"    {u}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
