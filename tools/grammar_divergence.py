"""Where does the INSTALLED grammar differ from the campaign's, and by how much?

`GRAMMAR.md` section 8 INSTALL copies seven files into a lane's worktree and prescribes three
textual substitutions in `test_grammar.py` (the tree path, the spec directory and the import).
So "byte-identical to the campaign's" is the wrong question for that one file: the right one is
whether anything diverges BEYOND what INSTALL itself prescribes.  The whole-system report's
section 1 states the answer, and this prints it, so the claim is a command rather than a memory.

    scripts/laplace-python tools/grammar_divergence.py        # exit 0; two files diverge

Banked beside the whole-system report as `wave1/synth-whole/grammar_divergence.out`.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
CAMPAIGN = pathlib.Path(
    "/home/phujck/VScodeProjects/laplace/evidence/WRITING_RECONCILIATION_2026-10-02/grammar")

#: published path in the lane's worktree <- file in the campaign's grammar directory
INSTALLED = {
    "src/laplace/core/grammar.py": "grammar.py",
    "tests/grammar_spec/grammar.py": "grammar.py",
    "tests/grammar_spec/map_verbs.py": "map_verbs.py",
    "tests/grammar_spec/mapping.csv": "mapping.csv",
    "tests/grammar_spec/GRAMMAR.md": "GRAMMAR.md",
    "tests/grammar_spec/obtain_census.py": "obtain_census.py",
    "tests/grammar_spec/by_census.py": "by_census.py",
    "tests/test_grammar.py": "test_grammar.py",
}

#: INSTALL step 3, verbatim from GRAMMAR.md section 8: the substitutions the install itself
#: performs on the copied suite.  A difference these produce is not a divergence.
PRESCRIBED = (
    ('TREE = Path("/home/phujck/VScodeProjects/laplace")',
     "TREE = Path(__file__).resolve().parents[1]"),
    ("GRAMMAR_DIR = HERE", 'GRAMMAR_DIR = HERE / "grammar_spec"'),
    ("sys.path.insert(0, str(GRAMMAR_DIR))\n\nimport grammar as g",
     "sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))\n\n"
     "from laplace.core import grammar as g"),
)


def changed_lines(left: str, right: str) -> int:
    """Lines that differ, counted by GNU `diff` itself: `diff a b | grep -c '^[<>]'`.

    Not `difflib`: on this very pair `difflib.unified_diff` finds a 74-line alignment where
    GNU `diff` finds 72, and two numbers for one measurement is the thing this campaign is
    about.  The report quotes the number a reader gets from `diff`, so this calls `diff`.
    """
    with tempfile.TemporaryDirectory() as work:
        a, b = pathlib.Path(work) / "a", pathlib.Path(work) / "b"
        a.write_text(left, encoding="utf-8")
        b.write_text(right, encoding="utf-8")
        done = subprocess.run(["diff", str(a), str(b)], capture_output=True, text=True)
    return sum(1 for line in done.stdout.splitlines() if line[:1] in ("<", ">"))


def main() -> int:
    rows = []
    for published, source in sorted(INSTALLED.items()):
        campaign = (CAMPAIGN / source).read_bytes()
        here = (ROOT / published).read_bytes()
        row = {"file": published, "campaign_source": source,
               "same_bytes": campaign == here}
        if not row["same_bytes"]:
            left = campaign.decode("utf-8", "replace")
            right = here.decode("utf-8", "replace")
            row["changed_lines"] = changed_lines(left, right)
            after = left
            for old, new in PRESCRIBED:
                after = after.replace(old, new)
            row["changed_lines_beyond_INSTALL"] = changed_lines(after, right)
            row["prescribed_substitutions_applied"] = sum(
                1 for old, _ in PRESCRIBED if old in left and old not in right)
            row["expiry_constants_added"] = sorted(
                set(re.findall(r"^([A-Z][A-Z_]*EXPIRY) = ", right, re.M))
                - set(re.findall(r"^([A-Z][A-Z_]*EXPIRY) = ", left, re.M)))
        rows.append(row)
    print("%-38s %-10s %8s %8s" % ("file", "bytes", "changed", "beyond"))
    for row in rows:
        print("%-38s %-10s %8s %8s"
              % (row["file"], "SAME" if row["same_bytes"] else "DIFF",
                 row.get("changed_lines", ""), row.get("changed_lines_beyond_INSTALL", "")))
    diverged = [row for row in rows if not row["same_bytes"]]
    print("\nfiles that diverge: %d of %d" % (len(diverged), len(rows)))
    for row in diverged:
        print("  %s: %d changed lines, %d beyond INSTALL's own substitutions, expiry "
              "constants added %r"
              % (row["file"], row["changed_lines"], row["changed_lines_beyond_INSTALL"],
                 row["expiry_constants_added"]))
    print(json.dumps(rows, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
