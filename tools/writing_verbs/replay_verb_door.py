#!/usr/bin/env python3
"""The BOTH-WAYS replay: the recorded corpus through the old names and through the verb door.

    scripts/laplace-python tools/writing_verbs/replay_verb_door.py --out <dir>

The brief's test, in its own words: "replay.py parity over the whole corpus through BOTH the
old names and the new verbs (the same recorded call expressed both ways must produce identical
outcomes and bytes)".  ``harness/replay.py`` replays one door against two TREES; this replays
one TREE against two DOORS, in two sandboxes built from the same fixture, in the same order,
with the same four comparisons the oracle makes:

  class   read / applied / banked / refused
  home    the innermost owner frame that raised (``src/laplace/<file>.py:<line>``)
  homes   the set of project files the one call changed
  bytes   the normalised bytes of every file in the workspace afterwards

  - side ``names``  sends ``{"op": "execute", operation, payload}``  -> wt.execute
  - side ``verbs``  sends ``{"op": "request", verb, concept, target, expected, payload}``
                                                                     -> wt.request

The verb side's request is built from the recorded row by ``writing_verbs.from_owner_call``, the
shim direction: the row's guard values become ``expected`` tokens, its act-naming selector keys
are lifted out, and the rest is the payload.  So the two sides are the same recorded call
spelled the two ways.

The ``response`` comparison is NOT a parity kind here and the run says so: the verb door answers
in the grammar's receipt/refusal shape (GRAMMAR.md section 5), not in the legacy response shape,
which is the whole point of having a second door.  What must agree is the act: the class, the
owner frame, the files changed and the bytes on disk.

A route the verb door cannot reach (``Route.door == "shim"``, with ``Route.because``) is counted
as ``unreachable`` and never scored as parity -- the lane declares 24 such routes and the number
this run reaches is printed, so "both ways" is never claimed for a row that only went one way.

Exit 0 only when every scored row agrees on all four kinds.
"""
from __future__ import annotations

import argparse
import json
import selectors
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

HARNESS = Path("/home/phujck/VScodeProjects/laplace/evidence/"
               "WRITING_RECONCILIATION_2026-10-02/harness")
HERE = Path(__file__).resolve().parent
TREE = HERE.parents[1]
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(TREE / "src"))

import _harness                                                      # noqa: E402
import _netcache                                                     # noqa: E402
import replay as oracle                                              # noqa: E402
from _harness import (Side, build_fixture, changed_homes, copy_fixture,   # noqa: E402
                      fixture_turns, mint_turn, write_jsonl)

from laplace.native import verbs as v                               # noqa: E402


def call(side: Side, message: dict) -> dict:
    """One request on the worker's protocol, with the harness's own watchdog."""
    if side.worker is None or side.worker.stdin is None or side.worker.stdout is None:
        raise RuntimeError(f"{side.label}: worker not started")
    side.worker.stdin.write(json.dumps(message, ensure_ascii=False, default=str) + "\n")
    side.worker.stdin.flush()
    ready = selectors.DefaultSelector()
    ready.register(side.worker.stdout, selectors.EVENT_READ)
    try:
        if not ready.select(side.call_timeout):
            raise TimeoutError(f"{side.label}: no answer in {side.call_timeout:.0f}s for "
                               f"{message.get('operation') or message.get('concept')}; "
                               f"worker log tail:\n{side.worker_stderr(1200)}")
    finally:
        ready.close()
    line = side.worker.stdout.readline()
    if not line:
        raise RuntimeError(f"{side.label}: worker died: {side.worker_stderr()}")
    return json.loads(line)


def as_request(row: dict, *, root=None) -> dict | None:
    """The recorded call, expressed the new way.  ``None`` when no route names the act."""
    operation = str(row.get("operation") or "")
    payload = row.get("payload") or {}
    project = str(row.get("project") or "")
    try:
        route, request = v.from_owner_call(operation, payload, project=project,
                                           by=str(payload.get("by") or ""), root=root)
    except Exception:
        return None
    return {"op": "request", "project": project, "mode": row.get("mode") or "work",
            "verb": request.verb, "concept": request.concept, "target": request.target,
            "expected": list(request.expected), "payload": request.payload, "by": request.by,
            "route_door": route.door, "route_because": route.because,
            # The route's FULL old spelling: its operation AND ITS WHOLE SELECTOR, not only the
            # selector pairs that are lifted out of the payload.  `route.selector` is the field
            # that identifies the route (`Route.key` is `(verb, concept, selector)`), and a
            # retirement ledger keyed on anything less retires a route on a sibling's evidence:
            # `read stage@project` is four routes discriminated by `view`, all with an empty
            # `lift`, so a lift-only spelling collapsed them into one key.
            "old_spelling": route.operation + "".join(" " + k + "=" + val
                                                      for k, val in route.selector),
            "old_selector": [list(pair) for pair in route.selector],
            "old_lift": [list(pair) for pair in route.lift],
            "with_turn": bool(row.get("needs_turn"))}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", default=str(TREE))
    ap.add_argument("--corpus", default=str(HARNESS / "corpus"))
    ap.add_argument("--sources", default="failures,reads,writes,arrival")
    ap.add_argument("--work", default="/tmp/claude-1000/recon-verb-door")
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--netcache", help="shared external-answer cache (default <work>/netcache)")
    ap.add_argument("--netcache-mode", default="rw", choices=("rw", "ro", "off"))
    ap.add_argument("--reuse-fixture", action="store_true")
    ap.add_argument("--allow", help="JSON allow list of expected differences, in the oracle's "
                                   "own shape; evaluated by replay.allowed, imported from the "
                                   "harness rather than reimplemented")
    ap.add_argument("--show", type=int, default=12)
    args = ap.parse_args()

    tree = Path(args.tree).resolve()
    work = Path(args.work).resolve()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    sources = [s for s in args.sources.split(",") if s]
    allow = json.loads(Path(args.allow).read_text()) if args.allow else {}

    rows = [row for row in oracle.load_corpus(Path(args.corpus).resolve(), sources, args.limit)
            if row.get("door") == "tool" and not oracle.payload_less(row)]
    projects = sorted({str(r.get("project") or "") for r in rows if r.get("project")})
    # THE REGISTRY IS AN OBJECT, NOT A LIST.  `registry_projects.json` has two top-level keys,
    # `projects` and `projects_note`, so `p in json.loads(...)` compared a project id against
    # those two strings and was always False: the fixture held NO projects and every row died at
    # the first gate.  Selected the way the oracle selects (`harness/replay.py:294-296`), which
    # is the one correct reading of this file in the harness.
    registry = json.loads((tree / "registry_projects.json").read_text()) \
        if (tree / "registry_projects.json").is_file() else {}
    known = {entry.get("name") for entry in registry.get("projects", [])}
    fixture_projects = [p for p in projects if p in known]
    absent = [p for p in projects if p not in known]
    template = work / "fixture"
    if args.reuse_fixture and template.is_dir():
        manifest = json.loads((template / ".fixture.json").read_text())
    else:
        manifest = build_fixture(tree, template, fixture_projects)
    turns = fixture_turns(fixture_projects)

    head = subprocess.run(["git", "-C", str(tree), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    print(f"tree {tree}  {head[:12]}")
    print(f"fixture: {manifest['files']} files, {manifest['bytes'] / 1e6:.1f} MB, "
          f"projects {manifest['projects']}")
    if absent:
        print(f"corpus projects the registry does not know, left out of the fixture: {absent}")
    print(f"corpus {len(rows)} tool rows from {sources} (payload-less write rows left out, "
          f"as the oracle leaves them out)")

    netcache = (None if args.netcache_mode == "off"
                else Path(args.netcache or (work / "netcache")).resolve())
    if netcache:
        netcache.mkdir(parents=True, exist_ok=True)
        print(f"netcache {netcache} ({args.netcache_mode}): "
              f"{_netcache.summarise(netcache).get('records', 0)} records on entry")

    ports = _harness.free_ports(2)
    sides: dict[str, Side] = {}
    for label, port in (("names", ports[0]), ("verbs", ports[1])):
        sandbox = work / f"sandbox-{label}"
        copy_fixture(template, sandbox)
        mint_turn(sandbox, fixture_projects)
        sides[label] = Side(label, tree, sandbox, port=port, state=work / f"state-{label}",
                            serve=False, turns=turns, netcache=netcache,
                            netcache_mode=args.netcache_mode)
    sides["names"].add_peer_roots(sides["verbs"])
    sides["verbs"].add_peer_roots(sides["names"])

    t0 = time.time()
    records: list[dict] = []
    counts: Counter = Counter()
    by_kind: Counter = Counter()
    class_pairs: Counter = Counter()
    refusal_homes: Counter = Counter()
    by_source: dict[str, Counter] = defaultdict(Counter)
    try:
        # BOTH SIDES RUN THE SAME WORKER, and that is not a convenience.  `_harness.Side.start`
        # launches `HERE/_worker.py`; this lane's worker speaks the harness protocol plus
        # {"op": "request"}, with the `execute` branch copied from the harness's worker
        # verbatim.  Running the harness worker on one side and the lane worker on the other
        # was MEASURED to split the differential on a file no door wrote: the owner records
        # its own argv in contract/journal.jsonl ("record": "act"), so two worker script paths
        # are a byte difference in a project file (harness/_harness.py:479-483 records the same
        # lesson about --label).  One worker, two doors, identical argv.
        _harness.HERE = HERE
        for side in sides.values():
            side.start()
        _harness.HERE = HARNESS

        base = {label: side.snap.take() for label, side in sides.items()}
        if base["names"] != base["verbs"]:
            differing = changed_homes(base["names"], base["verbs"])
            print(f"FIXTURE NOT IDENTICAL before any call: {len(differing)} paths differ")
            for rel in differing[:20]:
                print("   ", rel)
            return 3
        print(f"baseline identical on both sides: {len(base['names'])} files")

        snaps = dict(base)
        divergent: set[str] = set()
        for index, row in enumerate(rows, 1):
            row = {**row, "needs_turn": True}
            spelled = as_request(row, root=sides["verbs"].sandbox)
            name_msg = {"op": "execute", "project": row.get("project") or "",
                        "mode": row.get("mode") or "work",
                        "operation": row.get("operation") or "",
                        "payload": row.get("payload") or {}, "with_turn": True}
            # A row the verb door cannot express is still APPLIED ON BOTH SIDES, through its
            # old name, so the two sandboxes stay in lockstep for every later row.  Skipping
            # it on one side only would make every subsequent comparison meaningless.  It is
            # recorded as unscored, with the reason the route itself carries.
            why = None
            if spelled is None:
                counts["no_route"] += 1
                why = "no route: the recorded call names no act"
            elif spelled["route_door"] == "shim":
                counts["unreachable"] += 1
                why = ("the verb door cannot reach this route: " + spelled["route_because"])
            if why is not None:
                for label, side in sides.items():
                    call(side, name_msg)
                    snaps[label] = side.snap.take()
                records.append({"n": index, "id": row.get("id"), "source": row.get("source"),
                                "operation": row.get("operation"), "scored": False,
                                "verb": (spelled or {}).get("verb"),
                                "concept": (spelled or {}).get("concept"),
                                "old_spelling": (spelled or {}).get("old_spelling"),
                                "applied_through": "the old name, on both sides",
                                "why": why})
                continue
            results, afters, homes = {}, {}, {}
            results["names"] = call(sides["names"], name_msg)
            afters["names"] = sides["names"].snap.take()
            homes["names"] = changed_homes(snaps["names"], afters["names"])
            snaps["names"] = afters["names"]
            results["verbs"] = call(sides["verbs"], {k: val for k, val in spelled.items()
                                                     if k not in ("route_door",
                                                                  "route_because")})
            afters["verbs"] = sides["verbs"].snap.take()
            homes["verbs"] = changed_homes(snaps["verbs"], afters["verbs"])
            snaps["verbs"] = afters["verbs"]

            if results["verbs"].get("class") == "unreachable":
                # choose() refused to guess between two routes sharing the pair, so nothing ran
                # on the verb side.  THE NAMES SIDE HAS ALREADY RUN -- it is called above -- so
                # this branch used to leave the names sandbox one banked row ahead for the rest
                # of the run.  Measured 2026-10-02: that desynchronisation is what made
                # contract/journal.jsonl divergent at the next row to flush an act, and the
                # oracle reported it as that row's `bytes` difference.  So the row is replayed
                # on the VERB SIDE TOO, through its old name, exactly as the unreachable branch
                # above does, and lockstep is restored before the next row is scored.
                counts["ambiguous"] += 1
                call(sides["verbs"], name_msg)
                for label, side in sides.items():
                    snaps[label] = side.snap.take()
                records.append({"n": index, "id": row.get("id"), "source": row.get("source"),
                                "operation": row.get("operation"), "scored": False,
                                "verb": spelled["verb"], "concept": spelled["concept"],
                                "old_spelling": spelled["old_spelling"],
                                "applied_through": "the old name, on both sides",
                                "why": "choose() refused to guess: "
                                       + (results["verbs"].get("error") or "")[:200]})
                continue

            diffs = []
            if results["names"].get("class") != results["verbs"].get("class"):
                diffs.append("class")
            if (results["names"].get("home") or "") != (results["verbs"].get("home") or ""):
                diffs.append("home")
            if homes["names"] != homes["verbs"]:
                diffs.append("homes")
            differ_now = set(changed_homes(afters["names"], afters["verbs"]))
            new_divergent = sorted(differ_now - divergent)
            divergent |= differ_now
            if new_divergent:
                diffs.append("bytes")
            counts["scored"] += 1
            for kind in diffs:
                by_kind[kind] += 1
            # An allowed difference is still a difference and still counted and printed; what
            # the allow list decides is the EXIT, the way harness/replay.py:54 defines it.  The
            # allowance is evaluated by the oracle's own `allowed`, not a second copy of it.
            unallowed = [kind for kind in diffs if not oracle.allowed(allow, row, kind)]
            # WHAT THE SCORED ROWS ACTUALLY EXERCISED.  A run can agree on every kind and still
            # be worth nothing if every row refused at the first gate -- which is exactly what
            # the project-less fixture produced.  The histogram is part of the verdict so the
            # reader sees the population, not only the agreement.
            class_pairs[(str(results["names"].get("class")),
                         str(results["verbs"].get("class")))] += 1
            if results["names"].get("home"):
                refusal_homes[str(results["names"].get("home"))] += 1
            by_source[str(row.get("source"))]["rows"] += 1
            if diffs:
                by_source[str(row.get("source"))]["mismatch"] += 1
                counts["mismatch"] += 1
                if unallowed:
                    counts["unallowed"] += 1
            else:
                by_source[str(row.get("source"))]["parity"] += 1
                counts["parity"] += 1
            record = {"n": index, "id": row.get("id"), "source": row.get("source"),
                      "operation": row.get("operation"), "scored": True,
                      "verb": spelled["verb"], "concept": spelled["concept"],
                      "old_spelling": spelled["old_spelling"],
                      "old_selector": spelled["old_selector"],
                      "target": spelled["target"], "expected": spelled["expected"],
                      "names": {"class": results["names"].get("class"),
                                "home": results["names"].get("home"),
                                "error": (results["names"].get("error") or "")[:300],
                                "homes": homes["names"]},
                      "verbs": {"class": results["verbs"].get("class"),
                                "home": results["verbs"].get("home"),
                                "error": (results["verbs"].get("error") or "")[:300],
                                "homes": homes["verbs"],
                                "banked_row": results["verbs"].get("banked_row"),
                                "needed": results["verbs"].get("needed")},
                      "diffs": diffs, "unallowed": unallowed,
                      "new_divergent_paths": new_divergent}
            records.append(record)
            if diffs and counts["mismatch"] <= args.show:
                print(f"  MISMATCH {index} {row.get('id')} {row.get('operation')} "
                      f"-> {spelled['verb']} {spelled['concept']}  {diffs}")
                print(f"    names {record['names']['class']} {record['names']['home']} "
                      f"{record['names']['error'][:160]}")
                print(f"    verbs {record['verbs']['class']} {record['verbs']['home']} "
                      f"{record['verbs']['error'][:160]}")
            if index % 50 == 0:
                print(f"  {index}/{len(rows)}  {time.time() - t0:.0f}s  "
                      f"parity {counts['parity']}  mismatch {counts['mismatch']}  "
                      f"unreachable {counts['unreachable']}", flush=True)
    finally:
        for side in sides.values():
            side.stop()

    verdict = {
        "parity": counts["unallowed"] == 0 and counts["scored"] > 0,
        "parity_strict_no_allowance": counts["mismatch"] == 0 and counts["scored"] > 0,
        "allow": str(Path(args.allow).resolve()) if args.allow else None,
        "rows_unallowed": counts["unallowed"],
        "tree": str(tree), "head": head,
        "doors": {"names": "writing_tools.execute by operation name",
                  "verbs": "writing_tools.request with a grammar.Request"},
        "rows_in_corpus": len(rows),
        "rows_scored": counts["scored"], "rows_parity": counts["parity"],
        "rows_mismatch": counts["mismatch"],
        "rows_unreachable_from_verb_door": counts["unreachable"],
        "rows_ambiguous_at_the_verb_door": counts["ambiguous"],
        "rows_no_route": counts["no_route"],
        "difference_by_kind": dict(by_kind),
        "outcome_class_pairs_names_verbs": {f"{a} / {b}": n
                                            for (a, b), n in sorted(class_pairs.items())},
        "refusal_homes_top": dict(refusal_homes.most_common(12)),
        "by_source": {k: dict(c) for k, c in sorted(by_source.items())},
        "divergent_paths": sorted(divergent),
        "seconds": round(time.time() - t0, 1),
        "sources": sources,
        "response_compared": False,
        "response_note": ("the verb door answers in the grammar's receipt/refusal shape "
                          "(GRAMMAR.md section 5), not the legacy response shape, so the "
                          "response body is not a parity kind for this run; class, home, "
                          "homes and bytes are"),
    }
    write_jsonl(out / "rows.jsonl", records)
    (out / "parity.json").write_text(json.dumps(verdict, indent=1, sort_keys=True) + "\n")
    print(json.dumps(verdict, indent=1, sort_keys=True))
    print("PARITY THROUGH BOTH DOORS"
          + (f" ({counts['mismatch']} allowed difference(s))" if counts["mismatch"] else "")
          if verdict["parity"] else
          f"NO PARITY: {counts['unallowed']} unallowed of {counts['mismatch']} rows that differ")
    return 0 if verdict["parity"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
