#!/usr/bin/env python3
"""Does every refusal the scripted arrival still hits carry a resolver?

The campaign's arrival target is "zero out-of-band facts, zero refusals that lack a
resolver".  `arrival.py` counts refusals and out-of-band facts but cannot score the CURE: the
published sequence predates `needed`, never retries with it, and holds each step's
`out_of_band` sentence as a LITERAL argument written by the sequence's author
(evidence/WRITING_FRICTION_2026-10-01/wave1/arrival-replay/replay_arrival.py:142 stores it,
:150 counts it, :207 takes it as a keyword), so a fact the door now states still counts
against the score.  This reads the arrival's own banked refusal bodies and asks the question
the score cannot: does the body carry the resolver, and does it name the read each value
comes from?

    scripts/laplace-python tools/arrival_resolvers.py --run <arrival --out dir> [--out f.json]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys


# WHY EACH OF THE SEVEN STILL REFUSES, and where its resolver is if it has one.  Every line
# here was located by grepping the sentence the arrival recorded, in this tree.
CLASSES = {
    "A1-create-no-header": (
        "header", "src/laplace/writing_declared_http.py:59 declares it; scanner.py refuses",
        "none: a missing header is not a stale value, and the declaration now states the rule"),
    "A2-create-bare": (
        "required-field", "src/laplace/writing_projects.py:228",
        "none needed: this refusal already names what it wants (title and kind)"),
    "C2-initialize-top-revision": (
        "identity", "src/laplace/project_structure.py:903-908 identity_doors.gate",
        "ON THE EXCEPTION: structure_change raises, so the resolver travels on "
        "IdentityRefused and is formatted by writing_tools.failure_response -- proved by "
        "tests/test_identity_doors.py::test_the_tool_door_serves_the_cure_and_no_retry_"
        "instruction, which asserts refused.needed.expected == [the token]"),
    "D3-add-object-structure-revision": (
        "identity", "src/laplace/concepts_surface.py:887-890 identity_doors.gate",
        "IN THE BODY on the HTTP door (concepts_surface.py:895-896 splices it); on the tool "
        "door the same exception carries it"),
    "E2-apply-revision": (
        "turn", "src/laplace/writing_tools.py:227",
        "none: a door that only exists inside a provider turn cannot be entered with a "
        "fresher token; the declaration's turn_bound/turn_door states it instead"),
    "E4-adjudicate-no-corpus": (
        "scope", "src/laplace/projection_viewer.py:413 (unknown corpus)",
        "none: the corpus is the project name, a scope fact, not a value to refresh"),
    "F4-adjudicate-headings-blank-guard": (
        "byte-guard above the gate", "src/laplace/review_surface.py:1800",
        "none: the validator runs before the identity gate, so no home is compared"),
}


def resolver_of(body) -> dict:
    """Whatever this response offers a caller to retry with, however it is nested."""
    if not isinstance(body, dict):
        return {}
    for key in ("refused", "refusal", None):
        node = body.get(key) if key else body
        if not isinstance(node, dict):
            continue
        needed = node.get("needed")
        if isinstance(needed, dict) and (needed.get("expected") or needed.get("unresolved")):
            return {"where": ((key + ".") if key else "") + "needed",
                    "expected": needed.get("expected") or [],
                    "unresolved": needed.get("unresolved") or [],
                    "homes": node.get("homes") or []}
    return {}


def said_of(body) -> str:
    if not isinstance(body, dict):
        return ""
    node = body.get("refused") if isinstance(body.get("refused"), dict) else {}
    for value in (node.get("said"), body.get("error"), body.get("said"),
                  body.get("message")):
        if isinstance(value, str) and value:
            return value
    return ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True, help="the arrival --out directory")
    ap.add_argument("--out", default="")
    args = ap.parse_args(argv)

    run = pathlib.Path(args.run)
    report = json.loads((run / "arrival.json").read_text(encoding="utf-8"))
    refused_steps = list(report["score"]["refused_steps"])
    steps = [json.loads(line) for line in
             (run / "steps.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]

    rows, with_resolver, without = [], [], []
    for step in steps:
        if step.get("step") not in refused_steps:
            continue
        body_file = step.get("body_file") or ""
        body = {}
        if body_file and (run / body_file).is_file():
            try:
                body = json.loads((run / body_file).read_text(encoding="utf-8"))
            except Exception:
                body = {}
        if not body:
            try:
                body = json.loads(step.get("response") or "{}")
            except Exception:
                body = {}
        found = resolver_of(body)
        rows.append({"step": step["step"], "door": step.get("door"),
                     "operation": step.get("operation"), "status": step.get("status"),
                     "said": said_of(body)[:200], "resolver": found,
                     "out_of_band_literal": step.get("out_of_band") or ""})
        (with_resolver if found else without).append(step["step"])

    print("refused steps scored by arrival.py: %d" % len(refused_steps))
    print("refused steps found in steps.jsonl: %d" % len(rows))
    print("  carry a resolver: %d  %r" % (len(with_resolver), with_resolver))
    print("  carry none:       %d  %r" % (len(without), without))
    print()
    for row in rows:
        print("%-9s %-34s %-22s %s" % ("RESOLVER" if row["resolver"] else "none",
                                       row["step"], str(row["operation"])[:22],
                                       row["said"][:60]))
        if row["resolver"]:
            print("          %s: expected=%d unresolved=%d homes=%d  %r"
                  % (row["resolver"]["where"], len(row["resolver"]["expected"]),
                     len(row["resolver"]["unresolved"]), len(row["resolver"]["homes"]),
                     (row["resolver"]["expected"] or row["resolver"]["unresolved"])[:1]))
    print()
    print("WHY, by class (the line was located by grepping the recorded sentence in this tree):")
    identity = []
    for row in rows:
        kind, where, resolver = CLASSES.get(row["step"], ("?", "?", "?"))
        if kind == "identity":
            identity.append(row["step"])
        print("  %-34s %-26s %s" % (row["step"], kind, where))
        print("      resolver: %s" % resolver)
    print()
    print("identity refusals among the seven: %d %r" % (len(identity), identity))
    print("the other %d are a header rule, a required field, a turn rule, a scope error and a "
          "byte guard above the gate -- none of them is a value a token can refresh."
          % (len(rows) - len(identity)))
    if args.out:
        pathlib.Path(args.out).write_text(
            json.dumps({"refused": rows, "with_resolver": with_resolver,
                        "without_resolver": without, "classes": CLASSES,
                        "identity_refusals": identity,
                        "out_of_band_list": report["out_of_band_list"]}, indent=1) + "\n",
            encoding="utf-8")
        print("\nwritten to", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
