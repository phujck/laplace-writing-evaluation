#!/usr/bin/env python3
"""Emit the lane's two tables as evidence: the dispatch table and the shim list.

Both are RENDERS of writing_verbs.ROUTES, which is itself a render of the grammar packet's
mapping.csv.  Nothing here is typed by hand, so nothing here can disagree with the module.

Usage: scripts/laplace-python tools/writing_verbs/emit_tables.py --out <dir>
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

TREE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TREE / "src"))
from laplace.core import grammar as g                      # noqa: E402
from laplace.native import verbs as v                # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    with (out / "dispatch.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["verb", "concept", "altitude", "old name", "selector lifted",
                         "guards (name:home:form)", "owner call", "site", "door", "because"])
        for route in sorted(v.ROUTES, key=lambda r: (r.verb, r.concept, r.operation)):
            writer.writerow([
                route.verb, route.concept, route.altitude, route.operation,
                " ".join(k + "=" + x for k, x in route.lift),
                " ".join("%s:%s:%s%s" % (n, h or "-", f, "?" if o else "")
                         for n, h, f, o in route.guards),
                route.owner, route.site, route.door, route.because])

    with (out / "shims.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["old operation", "old verb", "verb", "concept",
                         "guard -> home", "expiry"])
        for (old, old_verb), shim in sorted(v.SHIMS.items()):
            writer.writerow([old, old_verb, shim.verb, shim.concept,
                             " ".join("%s->%s" % (k, x) for k, x in
                                      sorted(shim.guard_to_home.items())),
                             shim.expiry])

    # THE ONE TABLE'S TWO FACES, from the one source: what the dispatch routes on and what
    # help publishes, side by side per operation.  If these two columns could disagree there
    # would be two tables; they are the same call.
    from laplace.native import declarations as d       # noqa: E402
    import laplace.native.declared                     # noqa: E402,F401
    import laplace.web.writing_declared_http                # noqa: E402,F401
    with (out / "acts.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["operation", "primary?", "act (dispatch)", "altitude",
                         "old spelling", "door", "help line (contract)", "handler",
                         "primary chosen by"])
        for operation in sorted(d.DECLARATIONS) + sorted(d.HTTP_DECLARATIONS):
            declaration = (d.DECLARATIONS.get(operation)
                           or d.HTTP_DECLARATIONS.get(operation))
            if operation in d.DECLARATIONS:
                lines = d.help_payload(operation, permitted=True,
                                       with_tokens=False)["acts"]
            else:
                lines = ["%s %s <- %s" % (declaration.verb, declaration.concept, operation)]
            primary = v.PRIMARY_ACT.get(operation, ("", "", ""))
            for route, line in zip(v.routes_for(operation), lines):
                writer.writerow([
                    operation,
                    "yes" if (route.verb, route.concept) == (primary[0], primary[1]) else "",
                    route.verb + " " + route.concept, route.altitude,
                    v.old_spelling(route), route.door, line, route.site, primary[2]])

    with (out / "http.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["route", "name", "verb", "concept", "site", "owner", "expiry"])
        for route in v.HTTP_ROUTES:
            writer.writerow([route.route, route.operation, route.verb, route.concept,
                             route.site, route.owner, route.expiry])

    counts = {
        "routes": len(v.ROUTES),
        "http_routes": len(v.HTTP_ROUTES),
        "declarations_reading_this_table": len(d.DECLARATIONS) + len(d.HTTP_DECLARATIONS),
        "primary_act_chosen_by": {how: sum(1 for row in v.PRIMARY_ACT.values()
                                           if row[2] == how)
                                  for how in sorted({row[2] for row in
                                                     v.PRIMARY_ACT.values()})},
        "site_how": {how: sum(1 for value in v.SITE_HOW.values() if value == how)
                     for how in sorted(set(v.SITE_HOW.values()))},
        "old_operation_names": len({r.operation for r in v.ROUTES}),
        "shims": len(v.SHIMS),
        "verbs": sorted({r.verb for r in v.ROUTES}),
        "pairs": len({(r.verb, r.concept) for r in v.ROUTES}),
        "concepts": len({r.concept for r in v.ROUTES}),
        "altitudes_reached": sorted({r.altitude for r in v.ROUTES}),
        "altitudes_declared": list(g.ALTITUDES),
        "routes_with_a_guard": sum(1 for r in v.ROUTES if r.guards),
        "guard_names": len({n for r in v.ROUTES for n, _h, _f, _o in r.guards}),
        "guard_homes": len({h for r in v.ROUTES for _n, h, _f, _o in r.guards if h}),
        "guard_forms": {form: sum(1 for r in v.ROUTES for _n, _h, f, _o in r.guards
                                  if f == form) for form in v.FORMS},
        "verb_door_routes": sum(1 for r in v.ROUTES if r.door == "both"),
        "shim_only_routes": sum(1 for r in v.ROUTES if r.door == "shim"),
        "routes_without_an_owner_citation": sorted({r.operation for r in v.ROUTES
                                                    if not r.site}),
        "aliases": sorted({r.alias_of for r in v.ROUTES if r.alias_of}),
        "generated_from": v.GENERATED_FROM,
        "verbs_by_altitude": {},
    }
    for route in v.ROUTES:
        counts["verbs_by_altitude"].setdefault(route.altitude, set()).add(route.verb)
    counts["verbs_by_altitude"] = {k: sorted(x) for k, x in
                                   sorted(counts["verbs_by_altitude"].items())}
    (out / "dispatch_counts.json").write_text(json.dumps(counts, indent=1))
    print(json.dumps(counts, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
