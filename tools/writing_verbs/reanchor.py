#!/usr/bin/env python3
"""Re-anchor every ``src/laplace/<file>.py:<line>`` citation a merge moved.

    scripts/laplace-python tools/writing_verbs/reanchor.py --base <ref> \
        --cited src/laplace/native/tools.py --in <file> [--in <file> ...] [--apply]

WHY THIS EXISTS, AND WHY IT IS AN ORGAN AND NOT A HAND PASS.  Both lanes this synthesis
merges cite `src/laplace/native/tools.py` by line -- 339 citations in
`src/laplace/native/declared.py` (one per declaration handler and one per rule door) and
151 in `src/laplace/native/verbs.py` -- and both lanes EDITED that file: the contract lane
added 15 lines inside the `help` branch, the dispatch lane added 10 at the top of `execute`
and 64 before `failure_response`.  So after the merge every citation written on one branch
is wrong by the other branch's insertions, in both directions, and the two tables are wrong
by DIFFERENT amounts: at the merge commit `structure_change`'s route said
`writing_tools.py:408` while its declaration said `:423`, and `:423` is the line that holds
`if operation == "structure_change":`.

The repair is mechanical and must be: a citation names a STATEMENT, so the new address is
the line of this tree that holds the same statement the base tree held at the old address.
The map from old line to new line is a line DIFF ALIGNMENT of the two versions of the cited
file (`difflib.SequenceMatcher` over the two line lists), not a text search.  A text search
is not enough and the measurement says so: `'except ValueError:'` occurs twice in the merged
`writing_tools.py` and `'if operation == "repository":'` twice, so twelve citations came back
"candidates [974, 1019]" with no way to choose, while the alignment maps each one to the
block it is actually inside.  A citation that falls inside a block the merge replaced or
deleted has no aligned line, and that is reported as unresolved rather than guessed;
`--apply` leaves those alone.

`--check` exits non-zero if any citation in the `--in` files no longer holds the statement
the base tree held there, so a later edit to the cited file cannot silently rot them again.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]


def base_lines(ref: str, path: str, tree: Path) -> list[str]:
    out = subprocess.run(["git", "show", "%s:%s" % (ref, path)], cwd=tree, check=True,
                         capture_output=True, text=True).stdout
    return out.split("\n")


def alignment(old: list[str], new: list[str]) -> dict[int, int]:
    """{old line number -> new line number} for every line the two versions share.

    Built from `difflib.SequenceMatcher`'s equal blocks, so a line that occurs twice is
    mapped by its POSITION in the file and not by its text; a line inside a replaced or
    deleted block is absent from the map and its citations are reported, never guessed.
    """
    import difflib
    out: dict[int, int] = {}
    matcher = difflib.SequenceMatcher(None, [line.rstrip() for line in old],
                                     [line.rstrip() for line in new], autojunk=False)
    for a, b, size in matcher.get_matching_blocks():
        for step in range(size):
            out[a + step + 1] = b + step + 1
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", default=".")
    ap.add_argument("--base", required=True, help="the ref the citations were written against")
    ap.add_argument("--cited", default="src/laplace/native/tools.py",
                    help="the file whose line numbers moved")
    ap.add_argument("--in", dest="inputs", action="append", required=True,
                    help="a file holding citations; repeatable")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if any citation does not hold the base statement")
    args = ap.parse_args(argv)
    tree = Path(args.tree).resolve()
    old = base_lines(args.base, args.cited, tree)
    new = (tree / args.cited).read_text(encoding="utf-8").split("\n")
    aligned = alignment(old, new)
    pattern = re.compile(re.escape(args.cited.split("/")[-1]) + r":(\d+)")

    moved = kept = unresolved = 0
    rows: list[tuple[str, int, int, str]] = []
    problems: list[tuple[str, int, str, list[int]]] = []
    for name in args.inputs:
        path = tree / name
        text = path.read_text(encoding="utf-8")
        out: list[str] = []
        last = 0
        for match in pattern.finditer(text):
            number = int(match.group(1))
            statement = old[number - 1].strip() if 0 < number <= len(old) else ""
            to = aligned.get(number)
            out.append(text[last:match.start(1)])
            last = match.end(1)
            if to == number:
                kept += 1
                out.append(str(number))
                continue
            if to is not None:
                moved += 1
                rows.append((name, number, to, statement[:90]))
                out.append(str(to))
                continue
            unresolved += 1
            problems.append((name, number, statement[:90],
                             [n for n, line in enumerate(new, 1)
                              if statement and line.strip() == statement]))
            out.append(str(number))
        out.append(text[last:])
        rewritten = "".join(out)
        if args.apply and rewritten != text:
            path.write_text(rewritten, encoding="utf-8")

    for name, number, to, statement in rows:
        print("MOVED  %s  %s:%d -> :%d  %s" % (name, args.cited, number, to, statement))
    for name, number, statement, here in problems:
        print("UNRESOLVED %s  %s:%d  %r  candidates %r"
              % (name, args.cited, number, statement, here))
    print("citations: %d already right, %d moved, %d unresolved (base %s, cited %s)"
          % (kept, moved, unresolved, args.base, args.cited))
    if args.check:
        return 1 if (moved or unresolved) else 0
    return 1 if unresolved else 0


if __name__ == "__main__":
    sys.exit(main())
