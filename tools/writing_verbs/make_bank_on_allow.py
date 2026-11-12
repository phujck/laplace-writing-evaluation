#!/usr/bin/env python3
"""Build the lane's allow list for the SHIPPED configuration, by checking each row.

    scripts/laplace-python tools/writing_verbs/make_bank_on_allow.py \
        --rows <parity-bank-on/rows.jsonl> --base <allow.gate.json> --out <allow.bank-on.json>

The configuration that ships banks a writing-tool row on EVERY caller path
(``writing_verbs.bank_every_path``, src/laplace/writing_verbs.py:1593-1595: the dial defaults to
on).  The campaign's base tree banks nothing on a path with no provider turn -- both banking
branches at ``706a8204`` are guarded by ``if turn_id and ...`` -- so on every such row the new
side changes two files the old side does not.  That is a ``homes`` difference by construction.

AN ALLOW ENTRY IS NOT A LIST OF ROWS THAT DIFFERED.  Each candidate row is CHECKED here, and a
row that fails any check is left unallowed so the gate still fails on it:

  1. the outcome class agrees,
  2. the raising owner frame agrees,
  3. nothing the old side changed is missing on the new side,
  4. the new side's extra files are a subset of exactly two paths -- ``contract/talk.jsonl``
     (the act ledger: writing_tools.py:1035-1047, the third banking branch) and
     ``contract/journal.jsonl`` (the act row the same ``journal.bank_row`` call appends),
  5. a ``bytes`` entry is granted only when every newly divergent path is one of those two,
  6. a ``response`` entry is granted only to a read OF THAT LEDGER whose answer grew from an
     empty list to a non-empty one -- the record this lane adds, read back by the door that
     reads it.

The output carries the reason and the lines, per kind, so a reader of the allow file never has
to come back here to learn what was excused.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

LEDGER = {"contract/talk.jsonl", "contract/journal.jsonl"}

REASON = {
    "homes": ("THE SHIPPED CONFIGURATION'S ONE FOOTPRINT. The new side banks a writing-tool "
              "row on a caller path with no provider turn; the base tree banks nothing there "
              "(both branches at 706a8204 are `if turn_id and ...`). So the new side changes "
              "contract/talk.jsonl -- the act ledger -- and contract/journal.jsonl, the act "
              "row the same journal.bank_row call appends, and the old side changes neither. "
              "The dial that governs it is src/laplace/writing_verbs.py:1593-1595 and the "
              "branch is src/laplace/writing_tools.py:1035-1047. CHECKED per row: same class, "
              "same owner frame, nothing missing on the new side, and the extra files are "
              "those two and no others."),
    "bytes": ("The two ledger files above, and no third path. Once a row has written a row the "
              "base tree did not, those two files differ in their bytes for the rest of the "
              "run; the oracle attributes a `bytes` difference to the FIRST row that makes a "
              "path divergent, so this is granted to that row alone."),
    "response": ("A READ OF THE LEDGER THIS LANE FILLS. `author_history` answers out of the act "
                 "ledger, so once the ledger records a non-turn caller's act the read returns "
                 "it: the old side answers `items: []` and the new side answers the acts. That "
                 "is the deliverable being visible, not a changed read -- the friction report's "
                 "`the system's failure record is a census of one provider's turns`. Granted "
                 "only where the old answer's items list is empty and the new one's is not."),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", required=True)
    ap.add_argument("--parity", required=True,
                    help="the run's parity.json: a `bytes` entry needs the WHOLE run's "
                         "divergent-path set to be inside the ledger, which only that file has")
    ap.add_argument("--base", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    rows = [json.loads(line) for line in Path(args.rows).read_text().splitlines()
            if line.strip()]
    allow = json.loads(Path(args.base).read_text())
    verdict = json.loads(Path(args.parity).read_text())
    run_paths = set(verdict.get("bytes_divergent_paths") or [])
    run_bytes_ok = bool(run_paths) and run_paths <= LEDGER
    granted: dict[str, list[str]] = {}
    refused: list[dict] = []
    for row in rows:
        if not row.get("unallowed"):
            continue
        ident = str(row.get("id"))
        old, new = row.get("old") or {}, row.get("new") or {}
        old_homes, new_homes = set(old.get("homes") or []), set(new.get("homes") or [])
        checks = {
            "class agrees": old.get("class") == new.get("class"),
            "owner frame agrees": (old.get("home") or "") == (new.get("home") or ""),
            "nothing missing on the new side": not (old_homes - new_homes),
            "extra files are the ledger only": (new_homes - old_homes) <= LEDGER,
        }
        if not all(checks.values()):
            refused.append({"id": ident, "failed": [k for k, ok in checks.items() if not ok],
                            "old": old, "new": new})
            continue
        kinds = []
        if "homes" in row["unallowed"]:
            kinds.append("homes")
        if "bytes" in row["unallowed"]:
            # The row records only how many paths were divergent by then; the PATHS are
            # the run's, and the run must have no divergent path outside the ledger.
            if run_bytes_ok:
                kinds.append("bytes")
            else:
                refused.append({"id": ident, "failed": ["the run has a divergent path outside "
                                                        "the ledger"],
                                "paths": sorted(run_paths)})
        if "response" in row["unallowed"]:
            diff = row.get("response_difference") or {}
            grew = ('"items": []' in str(diff.get("old") or "")
                    and '"items": [{' in str(diff.get("new") or ""))
            if str(row.get("operation")) == "author_history" and grew:
                kinds.append("response")
            else:
                refused.append({"id": ident, "failed": ["response is not a ledger read growing "
                                                        "from an empty list"],
                                "operation": row.get("operation")})
        if kinds:
            granted[ident] = sorted(set(granted.get(ident, [])) | set(kinds))
    allow.setdefault("rows", {})
    for ident, kinds in granted.items():
        allow["rows"][ident] = sorted(set(allow["rows"].get(ident, [])) | set(kinds))
    allow["note"] = (str(allow.get("note") or "")
                     + "\n\nFOURTH ENTRY GROUP, added by tools/writing_verbs/make_bank_on_allow.py "
                       "for the configuration that SHIPS (the bank-every-path dial at its "
                       "default). " + REASON["homes"] + " " + REASON["bytes"] + " "
                     + REASON["response"]
                     + " Every row listed here was checked by that script; a row that failed a "
                       "check is NOT listed and the gate still fails on it.")
    allow["bank_on_entries"] = {"rows": granted, "reasons": REASON,
                                "run_divergent_paths": sorted(run_paths),
                                "checked_by": "tools/writing_verbs/make_bank_on_allow.py",
                                "refused": refused}
    Path(args.out).write_text(json.dumps(allow, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"granted_rows": len(granted),
                      "by_kind": {kind: sum(1 for ks in granted.values() if kind in ks)
                                  for kind in ("homes", "bytes", "response")},
                      "refused": refused, "out": args.out}, indent=1))
    return 1 if refused else 0


if __name__ == "__main__":
    raise SystemExit(main())
