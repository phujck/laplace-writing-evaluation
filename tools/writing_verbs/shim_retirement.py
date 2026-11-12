#!/usr/bin/env python3
"""Evaluate every shim's expiry condition against a deposited both-ways replay.

    scripts/laplace-python tools/writing_verbs/shim_retirement.py --rows <rows.jsonl> [--out D]

An expiry that no instrument tests is an expiry in form with no measurable condition.  Each
``Route.expiry`` names this tool and the run it reads; this is the tool.  For every route in
``writing_verbs.ROUTES`` (the count is printed, not typed here: it moved with the editor's
doors and a typed count in a docstring is the drift this campaign is subtracting) it answers
one of three things, and nothing else:

  RETIRABLE     a recorded row of this route travelled through ``writing_tools.request()`` and
                agreed with the same row through its old name on class, home, homes and bytes.
                The old name can be deleted and that call still works.
  HELD-UNREACHABLE  the route's own ``because``: two or more routes share its
                (verb, concept) and no payload key chooses between them, so the verb door
                cannot express it and the old name is the only spelling there is.
  HELD-UNEXERCISED  the verb door can reach it, but no row of the recorded corpus exercises
                it, so nothing has been measured.  This is not a defect of the dispatch; it is
                what the corpus holds, and a shim is not deleted on an argument.

The three counts are the retirement ledger.  Exit 0 always: this reports, it does not gate.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
TREE = HERE.parents[1]
sys.path.insert(0, str(TREE / "src"))

from laplace.native import verbs as v                              # noqa: E402

DEFAULT_ROWS = ("/home/phujck/VScodeProjects/laplace/evidence/WRITING_RECONCILIATION_2026-10-02/"
                "wave1/altitude-dispatch/parity-verb-door/rows.jsonl")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", default=DEFAULT_ROWS)
    ap.add_argument("--out")
    args = ap.parse_args()
    path = Path(args.rows)
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()] \
        if path.is_file() else []
    if not rows:
        print("no replay rows at %s -- run tools/writing_verbs/run_verb_door.sh first" % path)
        return 0

    # A route is proved by a row that was SCORED (both doors ran it) and had no difference.
    proved: Counter = Counter()
    for row in rows:
        if not row.get("scored") or row.get("diffs"):
            continue
        # Keyed on the route's operation AND ITS WHOLE SELECTOR, which is what identifies a
        # route (`Route.key` is `(verb, concept, selector)`).  Keying on the LIFTED pairs alone
        # was still the old bug for every route the selector discriminates and the lift does
        # not: `read stage@project` is four routes differing only in `view`, with an empty lift,
        # so they collapsed to one key and all four were retired on whichever row arrived.
        proved[(str(row.get("verb")), str(row.get("concept")),
                str(row.get("old_spelling") or row.get("operation")))] += 1

    verdicts = []
    counts: Counter = Counter()
    keys_seen: Counter = Counter()
    for route in v.ROUTES:
        spelling = route.operation + "".join(" " + k + "=" + val for k, val in route.selector)
        key = (route.verb, route.concept, spelling)
        keys_seen[key] += 1
        if proved.get(key):
            state, why = "RETIRABLE", "%d recorded row(s) of this route agreed both ways" % (
                proved[key],)
        elif route.door == "shim":
            state, why = "HELD-UNREACHABLE", route.because
        else:
            state, why = ("HELD-UNEXERCISED",
                          "the verb door reaches it; no row of the recorded corpus exercises "
                          "this (verb, concept, selector)")
        counts[state] += 1
        verdicts.append({"verb": route.verb, "concept": route.concept,
                         "operation": route.operation, "old_spelling": spelling,
                         "door": route.door, "state": state, "why": why,
                         "expiry": route.expiry})

    # THE HTTP DOORS AND THE GATE'S OWN DOORS (WRITING-CONSOLIDATION-W1).  This ledger walked
    # `ROUTES` --- the TOOL door --- and nothing else, so the editor's doors could carry a
    # well-formed expiry that no instrument ever read.  An expiry no instrument tests is an
    # expiry in form with no measurable condition, which is this tool's own first sentence.  Both
    # other registries are walked now: the HTTP rows of the same table, and
    # `identity_doors.DOORS`, where each door's old guard spelling lives.  Neither can be
    # RETIRABLE on this corpus --- no recorded row of it travels through the HTTP door's verb
    # spelling --- so they report HELD-UNEXERCISED with the reason, and the expiry each one
    # carries is PRINTED, so a reader sees the date and the parity run rather than trusting that
    # `Shim.__post_init__` refused an empty one.
    from laplace.core import identity_doors as idd                            # noqa: PLC0415
    doors = []
    for route in v.HTTP_ROUTES:
        doors.append({"registry": "writing_verbs.HTTP_ROUTES", "name": route.operation,
                      "verb": route.verb, "concept": route.concept, "route": route.route,
                      "state": "HELD-UNEXERCISED",
                      "why": "the recorded corpus replays this route under its own HTTP name; "
                             "no row of it carries the grammar's `concept`, so the verb "
                             "spelling is not exercised by this run",
                      "expiry": route.expiry})
    for key, shim in sorted(idd.DOORS.items()):
        doors.append({"registry": "identity_doors.DOORS", "name": key,
                      "verb": shim.verb, "concept": shim.concept,
                      "old_spelling": "%s %s" % (shim.old_operation, shim.old_verb),
                      "guards": dict(shim.guard_to_home),
                      "state": "HELD-UNEXERCISED" if shim.guard_to_home else "NO-OLD-NAME",
                      "why": (idd.NO_OLD_NAME.get(key)
                              or "the old guard name is still accepted; parity through "
                                 "`expected` alone has not been measured"),
                      "expiry": shim.expiry})
    bad_expiry = [d["name"] for d in doors
                  if not re.search(r"\b20\d\d-\d\d-\d\d\b", str(d["expiry"]))
                  or "parity" not in str(d["expiry"]).lower()]

    # The key must be one-to-one with the route, or a proof lands on a sibling's row.  Printed,
    # and shared keys named, so the instrument states its own soundness instead of assuming it.
    shared = {" ".join(k): n for k, n in sorted(keys_seen.items()) if n > 1}
    summary = {"rows_read": len(rows), "routes": len(v.ROUTES),
               "distinct_keys": len(keys_seen), "keys_shared_by_more_than_one_route": shared,
               "run": str(path), "counts": dict(counts),
               "http_doors": len(v.HTTP_ROUTES), "gate_doors": len(idd.DOORS),
               "doors_without_a_dated_parity_expiry": bad_expiry,
               "door_states": dict(Counter(d["state"] for d in doors))}
    print(json.dumps(summary, indent=1, sort_keys=True))
    for state in ("RETIRABLE", "HELD-UNREACHABLE", "HELD-UNEXERCISED"):
        names = sorted({f"{d['verb']} {d['concept']}  <- {d['old_spelling']}"
                        for d in verdicts if d["state"] == state})
        print(f"\n{state}  ({len(names)} of {len(verdicts)})")
        for name in names:
            print("   ", name)
    print("\nTHE OTHER TWO REGISTRIES (%d HTTP doors, %d gate doors). Neither is RETIRABLE on "
          "this corpus; each expiry is printed so the date and the parity run are read, not "
          "assumed." % (len(v.HTTP_ROUTES), len(idd.DOORS)))
    for door in doors:
        print("    %-26s %-34s %s" % (door["name"], door["verb"] + " " + door["concept"],
                                      door["state"]))
    print("\n    expiries, verbatim:")
    for expiry in sorted({str(d["expiry"]) for d in doors}):
        print("      -", expiry)
    if bad_expiry:
        print("\n    NO DATED PARITY EXPIRY: %r" % (bad_expiry,))
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "shim_retirement.json").write_text(
            json.dumps({"summary": summary, "routes": verdicts, "doors": doors},
                       indent=1) + "\n")
        print("\nwritten", out / "shim_retirement.json")
    return 1 if bad_expiry else 0


if __name__ == "__main__":
    raise SystemExit(main())
