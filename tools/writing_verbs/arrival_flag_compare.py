#!/usr/bin/env python3
"""Compare the two banked arrival runs key by key, and say which keys the harness compares.

WHY THIS EXISTS.  Round 3 rejected the word "byte-identical" in the report's section 8.9:
the two banked artefacts are not identical, so the report's own evidence contradicted the
word it chose.  The true claim is narrower and the harness states it in code --- `arrival.py`
declares EXACT_KEYS, "the numbers that reproduce exactly, and are therefore compared
exactly", and INDICATIVE_KEYS, "printed and NOT compared", with a comment recording that
four runs of ONE UNCHANGED TREE gave five different `chars_received` values.  So the
comparison this script prints is the comparison `arrival.py --compare` makes, and the
indicative deltas are printed beside it as deltas rather than hidden.

It also prints the commit each run was taken at and the `git diff --stat ... -- src` between
them, because two runs at two commits are not a flag comparison unless the trees agree.

    scripts/laplace-python tools/writing_verbs/arrival_flag_compare.py \
        --off <evidence>/arrival.json --on <evidence>/arrival_flag_on.json
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
TREE = HERE.parent.parent
ARRIVAL = pathlib.Path("/home/phujck/VScodeProjects/laplace/evidence/"
                       "WRITING_RECONCILIATION_2026-10-02/harness/arrival.py")


def harness_keys() -> tuple[tuple[str, ...], tuple[str, ...]]:
    """EXACT_KEYS and INDICATIVE_KEYS, read out of the harness script, not retyped."""
    namespace: dict = {}
    source = ARRIVAL.read_text(encoding="utf-8")
    for name in ("EXACT_KEYS", "INDICATIVE_KEYS"):
        start = source.index(name + " = (")
        end = source.index(")", start) + 1
        exec(compile(source[start:end], "<arrival>", "exec"), namespace)  # noqa: S102
    return namespace["EXACT_KEYS"], namespace["INDICATIVE_KEYS"]


def git(*args: str) -> str:
    done = subprocess.run(["git", *args], capture_output=True, text=True,
                          cwd=str(TREE), check=False)
    return (done.stdout or done.stderr).rstrip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--off", required=True)
    parser.add_argument("--on", required=True)
    args = parser.parse_args()

    off = json.loads(pathlib.Path(args.off).read_text())
    on = json.loads(pathlib.Path(args.on).read_text())
    exact, indicative = harness_keys()

    print("# the two arrival runs, and the commit each was taken at")
    print("  flag OFF  %s  head %s" % (pathlib.Path(args.off).name, off["head"]))
    print("  flag ON   %s  head %s" % (pathlib.Path(args.on).name, on["head"]))
    print("  the two are NOT the same commit, so the tree difference between them:")
    stat = git("diff", "--stat", off["head"], on["head"], "--", "src")
    for line in (stat or "(no difference under src)").splitlines():
        print("    " + line)
    print("  and to this branch's head:")
    print("    HEAD = %s" % git("rev-parse", "HEAD"))
    for line in (git("diff", "--stat", on["head"], "HEAD", "--", "src")
                 or "(no difference under src)").splitlines():
        print("    " + line)

    print()
    print("# THE COMPARED NUMBERS (arrival.py EXACT_KEYS) --- what --compare checks")
    width = max(len(k) for k in exact + indicative) + 1
    same = True
    for key in exact:
        a, b = off["score"].get(key), on["score"].get(key)
        mark = "same" if a == b else "DIFFERENT"
        same = same and a == b
        print("  %s %12s -> %12s   %s" % (key.ljust(width), a, b, mark))
    for key in ("refusals", "refused_steps"):
        if key == "refused_steps":
            a, b = off["score"].get(key), on["score"].get(key)
            print("  %s %s" % ("refused_steps (order)".ljust(width),
                              "identical list" if a == b else "DIFFERENT"))
    print("  owner_code_reads      %s -> %s" % (off.get("owner_code_reads"),
                                                on.get("owner_code_reads")))
    print("  VERDICT: identical in every number arrival.py compares: %s" % same)

    print()
    print("# THE INDICATIVE NUMBERS (arrival.py INDICATIVE_KEYS) --- printed, never compared")
    print("  arrival.py:67-73 is the declaration; :89-95 records that four runs of an")
    print("  UNCHANGED tree gave chars_received 264,562 / 264,561 / 264,586 / 264,258.")
    for key in indicative:
        a, b = off["score"].get(key), on["score"].get(key)
        if a == b:
            continue
        print("  %s %12s -> %12s   delta %+d" % (key.ljust(width), a, b, (b or 0) - (a or 0)))
    for key in ("largest_masking", "largest_help"):
        a, b = off.get(key), on.get(key)
        if a == b:
            continue
        print("  %s differs, and ONLY in `raw`: the masked (`pinned`) count is equal" % key)
        for x, y in zip(a or [], b or []):
            if x == y:
                continue
            print("      step %-20s raw %d -> %d (delta %+d)   pinned %d -> %d  %s"
                  % (x.get("step"), x.get("raw"), y.get("raw"),
                     (y.get("raw") or 0) - (x.get("raw") or 0),
                     x.get("pinned"), y.get("pinned"),
                     "SAME" if x.get("pinned") == y.get("pinned") else "DIFFERENT"))
        print("      -> arrival.py:89-102 names these two steps as where the raw drift is")
        print("         concentrated, and the pinned counts are what the compared score uses.")

    print()
    print("# the artefacts themselves")
    for name, path in (("arrival.json", args.off), ("arrival_flag_on.json", args.on)):
        print("  %-22s %d bytes" % (name, pathlib.Path(path).stat().st_size))
    print("  byte-identical as FILES: %s   <- the word the report must not use"
          % (pathlib.Path(args.off).read_bytes() == pathlib.Path(args.on).read_bytes()))
    return 0 if same else 1


if __name__ == "__main__":
    sys.exit(main())
