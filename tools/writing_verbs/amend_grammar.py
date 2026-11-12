#!/usr/bin/env python3
"""The amendment this synthesis owes the grammar packet, as a command and not a request.

    scripts/laplace-python tools/writing_verbs/amend_grammar.py --merged . --out <dir>

GRAMMAR.md §8 says a lane must not edit the installed `grammar.py` in place --- "two lanes
with two grammar.py files is the 20-names defect with a new spelling" --- and says to send
the addition back to the packet's directory WITH THE MEASUREMENT THAT DEMANDS IT.  This is
that measurement, executable.

What demands it: the grammar cites `src/laplace/native/contracts.py` at eight lines and
`src/laplace/native/tools.py` at twenty-three, and this synthesis moved both files.
`writing_contracts.py` went from 632 lines to 128 when the generated-contract lane made the
contract a renderer, so eight citations point past its end --- which is why
`tests/test_grammar.py::test_the_cited_lines_are_the_lines_they_claim` fails in the merged
tree on `('note', 'writing_contracts.py', '433', 128)`.  `writing_tools.py` grew by 20 lines
in two places, so ten of the twenty-three `writing_tools.py` citations name a line that holds
a different statement, and one (`:211`, the `help` unknown-field set) names a statement the
contract lane replaced outright.

This writes an AMENDED copy of the grammar packet's files into `--out`, applying:

  1. the eight `writing_contracts.py:<n>` citations -> the address that holds the same fact
     today, from `tools/citation_migration.py`'s table (which verifies every row by reading
     the resolved line and checking it BEGINS with the key the row names), and
  2. every `writing_tools.py:<n>` citation -> its diff-aligned line in the merged tree, by
     the rule in `tools/writing_verbs/reanchor.py` (alignment, never a text search:
     `'except ValueError:'` occurs twice in the merged file).

It changes nothing in the live tree and nothing in this worktree's installed module.  The
proof that the amendment is right is the run deposited beside it: install the amended module
into a throwaway worktree of the merged commit and the suite is 46 passed, against 45 passed
and 1 failed with the packet's current bytes.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

FILES = ("grammar.py", "map_verbs.py", "mapping.csv", "GRAMMAR.md", "obtain_census.py",
         "by_census.py", "test_grammar.py", "home_census.py", "home_census.json")
CITING = ("grammar.py", "map_verbs.py", "GRAMMAR.md", "test_grammar.py")


def alignment(old: list[str], new: list[str]) -> dict[int, int]:
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
    ap.add_argument("--merged", default=".", help="the merged worktree (the new addresses)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--grammar", default="/home/phujck/VScodeProjects/laplace/evidence/"
                                         "WRITING_RECONCILIATION_2026-10-02/grammar")
    ap.add_argument("--base", default="706a8204")
    ap.add_argument("--table", default="/home/phujck/VScodeProjects/laplace/evidence/"
                                       "WRITING_RECONCILIATION_2026-10-02/wave1/"
                                       "synth-contract-dispatch/citations/"
                                       "citation_migration.json")
    args = ap.parse_args(argv)
    merged, out, grammar = (Path(args.merged).resolve(), Path(args.out).resolve(),
                            Path(args.grammar).resolve())
    out.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        if (grammar / name).is_file():
            shutil.copy2(grammar / name, out / name)

    table = json.loads(Path(args.table).read_text(encoding="utf-8"))
    moves = {row["cited"].rpartition(":")[2]: row for row in table["rows"]
             if not row["exists_today"] and row["now"]}
    assert moves, "the citation table has no resolved stale rows"

    base_tools = subprocess.run(["git", "show", args.base + ":src/laplace/native/tools.py"],
                                cwd=merged, capture_output=True, text=True, check=True).stdout
    aligned = alignment(base_tools.split("\n"),
                        (merged / "src/laplace/native/tools.py").read_text(
                            encoding="utf-8").split("\n"))

    report = {"grammar": str(grammar), "merged": str(merged), "base": args.base,
              "writing_contracts_rewrites": [], "writing_tools_rewrites": [],
              "writing_tools_unresolved": []}
    for name in CITING:
        path = out / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")

        def contracts(match: "re.Match[str]") -> str:
            row = moves.get(match.group(1))
            if row is None:
                return match.group(0)
            report["writing_contracts_rewrites"].append(
                {"file": name, "from": "src/laplace/native/contracts.py:" + match.group(1),
                 "to": row["now"], "why": row["why"]})
            return row["now"]
        text = re.sub(r"(?:src/laplace/)?writing_contracts\.py:(\d+)", contracts, text)

        def tools(match: "re.Match[str]") -> str:
            number = int(match.group(1))
            to = aligned.get(number)
            if to is None:
                report["writing_tools_unresolved"].append(
                    {"file": name, "citation": "writing_tools.py:%d" % number,
                     "base_line": base_tools.split("\n")[number - 1].strip()[:110],
                     "why": "the merged tree replaced this statement; a reader needs the new "
                            "fact, not a new line number"})
                return match.group(0)
            if to != number:
                report["writing_tools_rewrites"].append(
                    {"file": name, "from": "writing_tools.py:%d" % number,
                     "to": "writing_tools.py:%d" % to,
                     "statement": base_tools.split("\n")[number - 1].strip()[:110]})
            return match.group(0).replace(":%d" % number, ":%d" % to)
        text = re.sub(r"writing_tools\.py:(\d+)", tools, text)
        path.write_text(text, encoding="utf-8")

    (out / "AMENDMENT.json").write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                        encoding="utf-8")
    print("amended files in %s" % out)
    print("writing_contracts.py citations rewritten: %d"
          % len(report["writing_contracts_rewrites"]))
    for row in report["writing_contracts_rewrites"]:
        print("  %-16s %s -> %s" % (row["file"], row["from"], row["to"]))
    print("writing_tools.py citations re-anchored: %d" % len(report["writing_tools_rewrites"]))
    for row in report["writing_tools_rewrites"][:40]:
        print("  %-16s %s -> %s  %s"
              % (row["file"], row["from"], row["to"], row["statement"][:60]))
    print("writing_tools.py citations with no aligned line: %d"
          % len(report["writing_tools_unresolved"]))
    for row in report["writing_tools_unresolved"]:
        print("  %-16s %s  was: %s" % (row["file"], row["citation"], row["base_line"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
