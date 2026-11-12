#!/usr/bin/env python3
"""The set difference between two pytest -q runs: which tests this branch broke or fixed.

A count is not an attribution.  The wide suite has hundreds of pre-existing failures at the
campaign base, so the only honest statement about it is the set difference against a run of the
SAME suite at `706a8204`.

    scripts/laplace-python tools/suite_delta_whole.py --base <log> --branch <log> [--out f.txt]
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

LINE = re.compile(r"^(?:FAILED|ERROR) (\S+)")
TAIL = re.compile(r"^(?:=+ )?(\d+ (?:failed|passed).*?)(?: =+)?$")


def parse(path: pathlib.Path) -> tuple[set[str], str]:
    names, summary = set(), ""
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        got = LINE.match(line.strip())
        if got:
            names.add(got.group(1).split(" - ")[0])
        if re.search(r"\b\d+ (passed|failed)\b", line) and ("=" in line or "," in line):
            summary = line.strip(" =")
    return names, summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--branch", required=True)
    ap.add_argument("--out", default="")
    args = ap.parse_args(argv)

    base, base_summary = parse(pathlib.Path(args.base))
    branch, branch_summary = parse(pathlib.Path(args.branch))
    new = sorted(branch - base)
    fixed = sorted(base - branch)
    lines = [
        "base   %s" % args.base,
        "       %s" % base_summary,
        "       failing/erroring test ids: %d" % len(base),
        "branch %s" % args.branch,
        "       %s" % branch_summary,
        "       failing/erroring test ids: %d" % len(branch),
        "",
        "FAILING ON THE BRANCH AND NOT AT THE BASE: %d" % len(new),
    ]
    lines += ["   %s" % name for name in new]
    lines += ["", "FIXED BY THE BRANCH (failed at the base, passes here): %d" % len(fixed)]
    lines += ["   %s" % name for name in fixed[:40]]
    if len(fixed) > 40:
        lines += ["   ... and %d more" % (len(fixed) - 40)]
    text = "\n".join(lines) + "\n"
    print(text)
    if args.out:
        pathlib.Path(args.out).write_text(text, encoding="utf-8")
        print("written to", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
