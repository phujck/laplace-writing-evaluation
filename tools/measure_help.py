"""Measure every help response, the way the friction report measured it.

    scripts/laplace-python tools/measure_help.py --src <a src directory> --out <dir>

`--src` is the `src` directory to import `laplace` from, so the same instrument can
be pointed at a checkout of the base commit and at this worktree.  The figure is
`len(json.dumps(response, ensure_ascii=False))` of the response a caller receives
for `help {operation}` and for the bare `help {}`, which is the measurement
`evidence/WRITING_FRICTION_2026-10-01/wave1/context-economy/help_sizes.csv` carries
(its `chars` column; `json_chars` differs only where a response holds a non-string
key).  Reproducing 220,767 and 13,179 on the base commit is how the instrument is
shown to be the published one rather than a similar one.

`--project` MATTERS AND ONLY ON THE DECLARED SIDE.  The base `exact_contract` takes
no project, so its figure is project-independent; the declared `help_payload` mints
the live token of every guarded home into `expected`, so a named project adds
characters to the new column alone.  A before/after comparison must therefore state
the project per column: measured here, the 73 declared responses are 140,764
characters with `--project ''` and 143,496 with `--project synthetics-foundations`,
a 2,732-character difference that is entirely minted tokens.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import tempfile
from pathlib import Path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--project", default="")
    parser.add_argument("--root", default="")
    parser.add_argument("--label", default="")
    args = parser.parse_args(argv)

    sys.path.insert(0, str(Path(args.src).resolve()))
    from laplace.native import tools as wt
    from laplace.writing import reads
    from laplace.writing import operating as writing_operating

    mode = "work"
    contract = writing_operating.tool_contract()
    permitted = set(contract["role_permissions"][mode])
    rows = []

    def size(value) -> int:
        return len(json.dumps(value, ensure_ascii=False, default=str))

    # TWO CALL PATHS, chosen once by what the tree actually has, not per operation.
    # A declared tree is measured through the public tool wrapper in a disposable root,
    # so this instrument cannot drift from the keys or bytes a caller receives and cannot
    # bank a diagnostic read into the selected project. Historical trees without the
    # declaration owner retain their compact-catalogue fallback.
    try:
        from laplace.native.declarations import help_payload
        declared = True
    except ImportError:
        help_payload = None
        declared = False

    if declared:
        with tempfile.TemporaryDirectory(prefix="laplace-measure-help-") as scratch:
            bare = wt.execute(Path(scratch), args.project, mode, "help", {})
        bare_label = "(index: help with no operation)"
    else:
        from laplace.native.contracts import compact_catalogue
        bare = {"schema_version": writing_operating.VERSION, "digest": contract["digest"],
                "catalogue": compact_catalogue(sorted(permitted))}
        bare_label = "(catalogue: help with no operation)"
    rows.append({"operation": bare_label, "chars": size(bare)})

    # They are deliberately separate: the base tree's `exact_contract` takes
    # `owner_contract` and returns the owner's schema embedded, and `writing_tools`
    # returns the SAME object beside it as `requested_payload_contract` --- the
    # duplicate.  The declared tree has neither: the parameter was removed with the
    # duplicate (`src/laplace/writing_contracts.py:103`), so this file is the only
    # place the old name survives and it survives only on the base side.
    def declared_response(operation: str, action_only=False):
        action = help_payload(operation, permitted=operation in permitted,
                              project=args.project, root=args.root or None)
        return ({"schema_version": writing_operating.VERSION,
                 "digest": contract["digest"], "requested_operation": operation,
                 "action": action}, action)

    def base_response(operation: str):
        from laplace.native.contracts import exact_contract
        owner = contract["operation_payload_contracts"].get(operation)
        action = exact_contract(operation, permitted=operation in permitted,
                                owner_contract=owner)      # base signature only
        return ({"schema_version": writing_operating.VERSION,
                 "digest": contract["digest"], "requested_operation": operation,
                 "requested_payload_contract": owner, "action": action}, action)

    for operation in sorted(reads.READS | reads.WRITES):
        response, action = (declared_response(operation) if declared
                            else base_response(operation))
        rows.append({"operation": operation, "chars": size(response),
                     "action_chars": size(action)})

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    name = args.label or "help_sizes"
    with (out / (name + ".csv")).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["operation", "chars", "action_chars"])
        writer.writeheader()
        for row in rows:
            writer.writerow({"operation": row["operation"], "chars": row["chars"],
                             "action_chars": row.get("action_chars", "")})
    operations = [row for row in rows if not row["operation"].startswith("(")]
    total = sum(row["chars"] for row in operations)
    summary = {"src": str(Path(args.src).resolve()), "project": args.project,
               "operations": len(operations), "total_chars_73": total,
               "mean_chars": round(total / len(operations), 1),
               "bare_projection": "public-help-index" if declared else "historical-catalogue",
               "bare_keys": sorted(bare), "bare_chars": rows[0]["chars"],
               "total_all_responses": total + rows[0]["chars"],
               "largest": sorted(((row["chars"], row["operation"]) for row in operations),
                                 reverse=True)[:6]}
    (out / (name + ".json")).write_text(json.dumps(summary, ensure_ascii=False, indent=1),
                                        encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
