#!/usr/bin/env python3
"""What the whole-system parity run's differences are, and how many are NOT `response`.

HARNESS.md states the oracle's rule as "no bytes, class, home or homes difference is ever
ignored anywhere", and the HEAD allow list obeys it: only `response`.  The two pairwise
syntheses did not: they allow `home`, `homes` and `bytes` on named rows, each attributed by
their own instruments (raise-site line drift, the gate moving from one owner to another, one
banked digest spelling).  The whole-system allow list is their union, so it inherits those
allowances, and that is worth a number rather than a sentence.  This prints the shape of a
banked run: rows with any difference, rows unallowed, and the count per kind with the number
of rows that carry a kind OTHER than `response`.

    scripts/laplace-python tools/parity_shape.py --run <parity dir>
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True, help="the replay --out directory")
    args = ap.parse_args(argv)
    run = pathlib.Path(args.run)
    summary = json.loads((run / "parity.json").read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in
            (run / "rows.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]

    print("old %s" % summary["old"])
    print("new %s" % summary["new"])
    print("seconds %s   parity %s   rows_unallowed %s   rows_with_any_difference %s"
          % (summary["seconds"], summary["parity"], summary["rows_unallowed"],
             summary["rows_with_any_difference"]))
    print("difference_by_kind %s" % (summary["difference_by_kind"],))
    print("by_source %s" % (summary["by_source"],))
    print("by_door %s" % (summary["by_door"],))
    print("payload_less_skipped %s" % (summary["payload_less_skipped"],))
    print("bytes_divergent_paths_total %s" % summary.get("bytes_divergent_paths_total"))
    print("bytes_divergent_paths %s" % (summary.get("bytes_divergent_paths") or [])[:8])

    kinds, beyond_response, per_kind_rows = {}, [], {}
    for row in rows:
        diffs = row.get("diffs") or row.get("kinds") or []
        if isinstance(diffs, dict):
            diffs = sorted(diffs)
        for kind in diffs:
            kinds[kind] = kinds.get(kind, 0) + 1
            per_kind_rows.setdefault(kind, []).append(row.get("id") or row.get("row"))
        if any(kind != "response" for kind in diffs):
            beyond_response.append((row.get("id") or row.get("row"), sorted(diffs)))
    print()
    print("rows.jsonl: %d rows, %d with any difference" % (len(rows), sum(1 for r in rows
          if (r.get("diffs") or r.get("kinds")))))
    print("kind counts from rows.jsonl: %s" % (kinds,))
    print("rows carrying a kind other than `response`: %d" % len(beyond_response))
    for name, diffs in beyond_response[:12]:
        print("   %-52s %s" % (name, diffs))
    if len(beyond_response) > 12:
        print("   ... and %d more" % (len(beyond_response) - 12))
    print()
    print("THE STRICT READING: with no allowance at all this run would report %d rows "
          "differing, %d of them on a kind the HEAD list never allows."
          % (sum(1 for r in rows if (r.get("diffs") or r.get("kinds"))), len(beyond_response)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
