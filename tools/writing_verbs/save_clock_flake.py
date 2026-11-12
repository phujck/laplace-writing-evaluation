"""The one mismatch of gate run 3, shown to be the harness's save-clock defect and not a
behaviour difference of the merged tree.

    scripts/laplace-python tools/writing_verbs/save_clock_flake.py \
        --rows <evidence>/parity-shipped-run3/rows.jsonl

The oracle masks the editor's clock-named save directory in file CONTENTS
(`harness/_harness.py:87`: `save-\\d{4}-\\d{2}-\\d{2}_\\d{6}-\\d+` -> `<SAVE>`) but keys its
snapshot on the RAW relative path (`_harness.py:255` yields `str(path.relative_to(self.root))`,
`:265` keys `self._digest[rel]`, `:280-281` diffs by key) and `editor_saves` is not in
SNAPSHOT_SKIP_DIRS (`_harness.py:186`).  The owner that names the directory from the wall clock
is `src/laplace/projection_viewer.py:699`.  So when the two sides' `POST /review/adjudicate`
lands either side of a UTC second boundary, the two maps carry different KEYS for the same
files and the oracle reports `homes` and `bytes`.

This script applies the harness's OWN content rule to the keys and prints whether the two
sides then agree.  It reads only the banked row, changes nothing, and does not touch the
harness.  The harness lane's round-2 judge named this defect with the same row id; this is an
independent reproduction on a third tree.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SAVE = re.compile(r"save-\d{4}-\d{2}-\d{2}_\d{6}-\d+")      # _harness.py:87, verbatim


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", required=True)
    parser.add_argument("--row", default="ARRIVAL-033-E5-adjudicate")
    args = parser.parse_args()
    rows = [json.loads(line) for line in Path(args.rows).read_text().splitlines()
            if line.strip()]
    found = [r for r in rows if r["id"] == args.row]
    if not found:
        print("row %r not in %s -- this run did not hit the flake" % (args.row, args.rows))
        return 0
    row = found[0]
    old, new = row["old"], row["new"]
    print("row       ", row["id"], row["operation"], "door", row["door"])
    print("classes   ", old["class"], "/", new["class"], "  (equal:", old["class"] == new["class"], ")")
    print("diffs     ", row["diffs"], " unallowed", row["unallowed"])
    print("bytes paths")
    for path in row["bytes_paths"]:
        print("   ", path)
    raw_old, raw_new = set(old["homes"]), set(new["homes"])
    print("homes, RAW keys           equal:", raw_old == raw_new)
    print("  only old:", sorted(raw_old - raw_new))
    print("  only new:", sorted(raw_new - raw_old))
    masked_old = {SAVE.sub("<SAVE>", p) for p in raw_old}
    masked_new = {SAVE.sub("<SAVE>", p) for p in raw_new}
    print("homes, keys through the harness's OWN content rule   equal:",
          masked_old == masked_new)
    print("  only old:", sorted(masked_old - masked_new))
    print("  only new:", sorted(masked_new - masked_old))
    masked_bytes = {SAVE.sub("<SAVE>", p) for p in row["bytes_paths"]}
    print("the %d divergent paths collapse to %d masked names: %s"
          % (len(row["bytes_paths"]), len(masked_bytes), sorted(masked_bytes)))
    every_divergent_path_is_a_save = all("editor_saves" in p for p in row["bytes_paths"])
    print("every divergent path is under editor_saves:", every_divergent_path_is_a_save)
    verdict = (old["class"] == new["class"] and masked_old == masked_new
               and every_divergent_path_is_a_save)
    print()
    print("VERDICT:", "the mismatch is the clock-named directory and nothing else"
          if verdict else "there is a difference the save-clock does not explain -- READ IT")
    return 0 if verdict else 1


if __name__ == "__main__":
    raise SystemExit(main())
