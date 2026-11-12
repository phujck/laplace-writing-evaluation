#!/usr/bin/env python3
"""Re-baseline the arrival for a lane whose help cost fell on purpose.

WHY THIS EXISTS.  ``harness/arrival.py`` compares every ``chars_`` figure at
``--chars-tolerance 0`` (harness/arrival.py:217-219) and raises its exit status
to 1 for any figure that moves (harness/arrival.py:322).  A lane whose WHOLE
DELIVERABLE is a smaller help answer therefore cannot exit 0 against the
baseline it was measured from, however correct it is: the acceptance rule is
"nothing moved", and something moved on purpose.

A tolerance hides the number.  This writes the new baseline instead: the same
file with the compared figures that MOVED replaced by the figures this tree
produced, every other compared figure asserted unchanged, and the diff printed
so the move is a reviewable number and not a slackened bound.  An arrival
compared against the file this writes exits 0 at ``--chars-tolerance 0``, so
"arrival acceptance" stays a check somebody can run and read.

    rebaseline_arrival.py --baseline <old.json> --run <arrival.json> \
        --out <new.json> --reason "<why these figures moved>"

It REFUSES to write when a non-chars compared figure moved (a refusal count, a
door count, a refused step): those are not a cost reduction, they are a
behaviour change, and no baseline of mine gets to absorb one.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# The harness's own list, quoted so a drift in it shows up as a KeyError here
# rather than as a figure this script forgot to compare.
EXACT_KEYS = ("door_calls_steady", "refusals", "out_of_band_facts", "help_calls",
              "help_chars", "chars_sent_steady", "chars_received_steady",
              "chars_total_steady")
INDICATIVE_KEYS = ("door_calls", "polls", "chars_sent", "chars_received", "chars_total",
                   "chars_sent_pinned", "chars_received_pinned", "chars_total_pinned")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--run", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--reason", required=True)
    args = ap.parse_args()

    base = json.loads(Path(args.baseline).read_text())
    run = json.loads(Path(args.run).read_text())
    old = base.get("score", base)
    new = run["score"]

    moved_chars, moved_other, same = [], [], []
    for key in EXACT_KEYS:
        if key not in old or key not in new:
            raise KeyError(f"{key} missing from baseline or run score")
        if old[key] == new[key]:
            same.append(key)
        elif key.startswith("chars_") or key == "help_chars":
            moved_chars.append((key, old[key], new[key]))
        else:
            moved_other.append((key, old[key], new[key]))

    old_steps = sorted(old.get("refused_steps") or [])
    new_steps = sorted(new.get("refused_steps") or [])
    if old_steps != new_steps:
        moved_other.append(("refused_steps", old_steps, new_steps))

    print(f"baseline {args.baseline}")
    print(f"run      {args.run}")
    for key, a, b in moved_chars:
        print(f"  MOVED   {key:22s} {a} -> {b}   ({b - a:+d})")
    for key in same:
        print(f"  same    {key:22s} {old[key]}")
    print(f"  same    refused_steps          {len(new_steps)} steps, identical")

    if moved_other:
        for key, a, b in moved_other:
            print(f"  REFUSED {key:22s} {a} -> {b}   not a character cost", file=sys.stderr)
        print("A compared figure that is not a character count moved. "
              "That is a behaviour change, not a cost reduction: no re-baseline.",
              file=sys.stderr)
        return 2

    if not moved_chars:
        print("nothing moved; the old baseline already accepts this tree")
        return 0

    out = dict(base)
    score = dict(old)
    for key, _a, b in moved_chars:
        score[key] = b
    for key in INDICATIVE_KEYS:
        if key in new:
            score[key] = new[key]
    score["refused_steps"] = new.get("refused_steps")
    out["score"] = score
    out["head"] = run.get("head")
    out["branch"] = run.get("branch")
    out["tree"] = run.get("tree")
    out["largest_help"] = run.get("largest_help")
    out["rebaselined"] = {
        "from": str(Path(args.baseline)),
        "from_head": base.get("head"),
        "reason": args.reason,
        "compared_figures_moved": [
            {"key": k, "was": a, "now": b, "delta": b - a} for k, a, b in moved_chars
        ],
        "compared_figures_unchanged": same + ["refused_steps"],
        "rule": ("every compared figure that is not a character count is asserted "
                 "unchanged by tools/writing_verbs/rebaseline_arrival.py, which "
                 "refuses to write when one of them moves"),
    }
    Path(args.out).write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
