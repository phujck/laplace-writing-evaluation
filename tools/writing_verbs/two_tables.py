#!/usr/bin/env python3
"""The measurement that justifies deleting one of the two tables, taken AT THE MERGE COMMIT.

    scripts/laplace-python tools/writing_verbs/two_tables.py --tree <a worktree at the merge> \
        --out <dir>

Run against a tree where both tables still exist (the merge commit, before this synthesis's
first commit), it answers the two questions a reader should ask before a deletion:

  * do they agree?  --- per operation, the declaration's own `verb`/`concept`/`also` against
    the route table's pairs, and the declaration's own `handler` against the route's `site`.
  * where do they disagree, and is the disagreement a drift or a difference of opinion?

Measured at `5682c4b2`: 73 of 73 operations agree on all 104 pairs, and 63 of 73 disagree
about the dispatch line --- not because either lane was careless, but because each lane's
citations were written against its own copy of `src/laplace/native/tools.py` and the merge
moved both.  A second copy that agrees is still a second copy; this is what it looks like the
hour it stops agreeing.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", required=True)
    ap.add_argument("--out")
    args = ap.parse_args()
    tree = Path(args.tree).resolve()
    sys.path.insert(0, str(tree / "src"))
    from laplace.native import verbs as v
    from laplace.native import declarations as d
    import laplace.native.declared                     # noqa: F401
    import laplace.web.writing_declared_http                # noqa: F401

    lines = (tree / "src/laplace/native/tools.py").read_text(encoding="utf-8").split("\n")

    def at(citation: str) -> str:
        where, _, number = str(citation or "").rpartition(":")
        if not number.isdigit() or not where.endswith("writing_tools.py"):
            return ""
        index = int(number) - 1
        return lines[index].strip()[:100] if 0 <= index < len(lines) else "<past the end>"

    by_operation: dict[str, list] = collections.defaultdict(list)
    for route in v.ROUTES:
        by_operation[route.operation].append(route)

    report = {"tree": str(tree), "routes": len(v.ROUTES),
              "declarations": len(d.DECLARATIONS), "http_declarations": len(d.HTTP_DECLARATIONS),
              "pairs_in_the_route_table": len({(r.verb, r.concept) for r in v.ROUTES}),
              "operations_whose_pairs_agree": 0, "operations_whose_pairs_differ": [],
              "operations_whose_dispatch_line_agrees": 0,
              "operations_whose_dispatch_line_differs": [],
              "declarations_citing_a_validation_guard": []}
    for operation, declaration in sorted(d.DECLARATIONS.items()):
        routes = by_operation.get(operation, [])
        route_pairs = {(r.verb, r.concept) for r in routes}
        declared_pairs = set(declaration.pairs)
        if route_pairs == declared_pairs:
            report["operations_whose_pairs_agree"] += 1
        else:
            report["operations_whose_pairs_differ"].append(
                {"operation": operation, "declared_only": sorted(declared_pairs - route_pairs),
                 "routed_only": sorted(route_pairs - declared_pairs)})
        sites = {r.site for r in routes if r.site}
        site = sorted(sites)[0] if len(sites) == 1 else ""
        if site == declaration.handler:
            report["operations_whose_dispatch_line_agrees"] += 1
        else:
            report["operations_whose_dispatch_line_differs"].append(
                {"operation": operation, "route_site": site or sorted(sites),
                 "route_site_holds": at(site), "declaration_handler": declaration.handler,
                 "declaration_handler_holds": at(declaration.handler)})
        if declaration.handler.endswith(":213") or "operation in {" in at(declaration.handler):
            report["declarations_citing_a_validation_guard"].append(
                {"operation": operation, "handler": declaration.handler,
                 "holds": at(declaration.handler)})
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "two_tables.json").write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                             encoding="utf-8")
    print(json.dumps({key: (value if not isinstance(value, list) else len(value))
                      for key, value in report.items()}, ensure_ascii=False, indent=1))
    for row in report["operations_whose_dispatch_line_differs"][:6]:
        print("  LINE %-26s route %s (%s) | declaration %s (%s)"
              % (row["operation"], row["route_site"], row["route_site_holds"][:40],
                 row["declaration_handler"], row["declaration_handler_holds"][:40]))
    for row in report["declarations_citing_a_validation_guard"][:12]:
        print("  GUARD %-26s %s  %s" % (row["operation"], row["handler"], row["holds"][:60]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
