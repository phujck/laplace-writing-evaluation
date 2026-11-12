#!/usr/bin/env python3
"""Change ONE row of the one table and show that the dispatch and help both move.

    scripts/laplace-python tools/writing_verbs/one_row.py --tree <a scratch worktree> \
        --out <dir> [--operation argument] [--verb place]

This is the judge's own test, run by the lane: "prove there is one table by changing one
declaration and watching both help and dispatch change".  It edits the ROW SOURCE ---
`tests/grammar_spec/mapping.csv` --- regenerates `src/laplace/writing_verbs.ROUTES` with
`gen_routes.py`, and then, in a FRESH interpreter (so nothing is cached from before the
edit), prints

  * what `writing_verbs.classify` puts in the banked row for the old operation name, and
  * what `writing_declarations.help_payload` publishes as the operation's verb, concept and
    acts,

before and after.  Both must move, and nothing else in the help response may.  It restores
the file at the end and verifies the restoration by digest, and it refuses to run in a tree
with uncommitted changes to either file, so it can never be the thing that changed a lane's
measured tree.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import subprocess
import sys
from pathlib import Path

PROBE = r"""
import json, sys
sys.path.insert(0, %r)
from laplace.native import verbs as v, declarations as d
import laplace.native.declared, laplace.web.writing_declared_http
operation = %r
help_payload = d.help_payload(operation, permitted=True, with_tokens=False)
act = v.classify(operation, {"project": "p"}, project="p")
print(json.dumps({"banked_row": act.row,
                  "help_verb": help_payload["verb"], "help_concept": help_payload["concept"],
                  "help_acts": help_payload["acts"],
                  "help_response": help_payload}, ensure_ascii=False, sort_keys=True))
"""


def probe(tree: Path, operation: str) -> dict:
    out = subprocess.run([sys.executable, "-c", PROBE % (str(tree / "src"), operation)],
                         cwd=tree, capture_output=True, text=True)
    if out.returncode:
        raise SystemExit("probe failed:\n" + out.stdout + out.stderr)
    return json.loads(out.stdout.strip().split("\n")[-1])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--operation", default="argument")
    ap.add_argument("--verb", default="place")
    args = ap.parse_args(argv)
    tree = Path(args.tree).resolve()
    mapping = tree / "tests" / "grammar_spec" / "mapping.csv"
    table = tree / "src" / "laplace" / "native" / "verbs.py"
    dirty = subprocess.run(["git", "status", "--porcelain", "--",
                            "tests/grammar_spec/mapping.csv", "src/laplace/native/verbs.py"],
                           cwd=tree, capture_output=True, text=True).stdout.strip()
    assert not dirty, "this tree already has changes to the row source or the table: " + dirty

    # BYTES for the restore, not text.  mapping.csv is the grammar packet's file and it
    # carries CRLF line endings; restoring it through `read_text`/`write_text` rewrote it
    # with LF and left the tree dirty by 156 bytes, which this tool exists not to do.
    before_mapping_bytes = mapping.read_bytes()
    before_table_bytes = table.read_bytes()
    before_mapping = before_mapping_bytes.decode("utf-8")
    before_table = table.read_text(encoding="utf-8")
    before = probe(tree, args.operation)

    rows = before_mapping.split("\n")
    hit = [index for index, line in enumerate(rows)
           if line.startswith(args.operation + "," + args.operation + ",")]
    assert len(hit) == 1, ("expected exactly one row for %s" % args.operation, hit)
    cells = rows[hit[0]].split(",")
    was_verb = cells[2]
    cells[2] = args.verb
    rows[hit[0]] = ",".join(cells)
    changed_row = (before_mapping.split("\n")[hit[0]], rows[hit[0]])
    mapping.write_bytes("\n".join(rows).encode("utf-8"))
    try:
        regen = subprocess.run([sys.executable, str(tree / "tools/writing_verbs/gen_routes.py"),
                                "--tree", str(tree)], cwd=tree, capture_output=True, text=True)
        assert regen.returncode == 0, regen.stdout + regen.stderr
        after = probe(tree, args.operation)
    finally:
        mapping.write_bytes(before_mapping_bytes)
        table.write_bytes(before_table_bytes)

    restored = (hashlib.sha256(mapping.read_bytes()).hexdigest()
                == hashlib.sha256(before_mapping_bytes).hexdigest()
                and hashlib.sha256(table.read_bytes()).hexdigest()
                == hashlib.sha256(before_table_bytes).hexdigest())

    moved_help = {key for key in set(before["help_response"]) | set(after["help_response"])
                  if before["help_response"].get(key) != after["help_response"].get(key)}
    report = {
        "tree": str(tree),
        "commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=tree, capture_output=True,
                                 text=True).stdout.strip(),
        "operation": args.operation, "row_before": changed_row[0], "row_after": changed_row[1],
        "verb_before": was_verb, "verb_after": args.verb,
        "dispatch_before": before["banked_row"], "dispatch_after": after["banked_row"],
        "help_before": {"verb": before["help_verb"], "concept": before["help_concept"],
                        "acts": before["help_acts"]},
        "help_after": {"verb": after["help_verb"], "concept": after["help_concept"],
                       "acts": after["help_acts"]},
        "help_keys_that_moved": sorted(moved_help),
        "dispatch_moved": before["banked_row"] != after["banked_row"],
        "help_moved": (before["help_verb"], before["help_acts"]) !=
                      (after["help_verb"], after["help_acts"]),
        "files_restored": restored,
        "help_diff": list(difflib.unified_diff(
            json.dumps(before["help_response"], indent=1, sort_keys=True).split("\n"),
            json.dumps(after["help_response"], indent=1, sort_keys=True).split("\n"),
            "help before", "help after", lineterm="", n=1)),
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "one_row.json").write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    for key in ("operation", "row_before", "row_after", "dispatch_before", "dispatch_after",
                "help_before", "help_after", "help_keys_that_moved", "dispatch_moved",
                "help_moved", "files_restored"):
        print("%-22s %s" % (key, json.dumps(report[key], ensure_ascii=False)))
    ok = report["dispatch_moved"] and report["help_moved"] and report["files_restored"]
    print("ONE TABLE:" if ok else "NOT ONE TABLE:",
          "one row changed moved both the dispatch and help" if ok else "see one_row.json")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
