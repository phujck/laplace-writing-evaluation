"""The advisor's alphabet beside the dispatch table and the mapping, measured.

    scripts/laplace-python tools/writing_verbs/alphabet_census.py --out <dir>

Three sets that must be one set, printed with both differences so a reader never has to
take the equality on trust:

* `routing.ROUTE_OPTIONS`    -- what the advisor may suggest, now generated from the
                                dispatch table (`src/laplace/native/routing.py:route_options`);
* `writing_verbs.ROUTES`     -- what the verb door can route, `door == "both"` projection;
* `mapping.csv`              -- the one row source both generators read.

It also counts the shim-only pairs, which is the number that would make the three sets
differ if the dispatch ever carried a pair with no reachable route: today every pair with a
shim route also has a `door == "both"` route, so the shim-only count is 0 and the
projection loses nothing.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
TREE = HERE.parents[1]
sys.path.insert(0, str(TREE / "src"))

from laplace.core import grammar as g            # noqa: E402
from laplace.native import routing                 # noqa: E402
from laplace.native import verbs as v      # noqa: E402

MAPPING = TREE / "tests" / "grammar_spec" / "mapping.csv"


def mapping_pairs() -> set[tuple[str, str]]:
    with MAPPING.open(newline="", encoding="utf-8") as handle:
        return {(row["verb"].strip(), row["concept"].strip())
                for row in csv.DictReader(handle)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    advisor = set(routing.ROUTE_OPTIONS)
    both = {(r.verb, r.concept) for r in v.ROUTES if r.door == "both"}
    whole = {(r.verb, r.concept) for r in v.ROUTES}
    shim_only = whole - both
    declared = set(g.VERB_CONCEPTS)
    table = mapping_pairs()

    report = {
        "routes": len(v.ROUTES),
        "routes_door_both": sum(1 for r in v.ROUTES if r.door == "both"),
        "routes_door_shim": sum(1 for r in v.ROUTES if r.door != "both"),
        "pairs_in_routes": len(whole),
        "pairs_door_both": len(both),
        "pairs_shim_only": sorted(shim_only),
        "advisor_options": len(advisor),
        "grammar_declared_pairs": len(declared),
        "mapping_rows": sum(1 for _ in open(MAPPING, encoding="utf-8")) - 1,
        "mapping_pairs": len(table),
        "added_pairs_at_import": len(g.ADDED_PAIRS),
        "advisor_minus_dispatch": sorted(advisor - both),
        "dispatch_minus_advisor": sorted(both - advisor),
        "dispatch_minus_grammar": sorted(both - declared),
        "grammar_minus_dispatch": sorted(declared - both),
        "dispatch_minus_mapping": sorted(both - table),
        "mapping_minus_dispatch": sorted(table - both),
        "all_three_equal": advisor == both == declared == table,
        "alphabet_source": "writing_verbs.ROUTES door==both, union grammar.ADDED_PAIRS",
        "choice_ceiling": routing.CHOICE_CEILING,
        "options_fit_one_choice": routing.options_fit_one_choice(),
    }
    print(json.dumps(report, indent=1, sort_keys=True))
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "alphabet.json").write_text(json.dumps(report, indent=1, sort_keys=True))
        print("written", out / "alphabet.json")
    return 0 if report["all_three_equal"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
