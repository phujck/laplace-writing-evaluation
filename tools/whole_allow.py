#!/usr/bin/env python3
"""The whole-system allow list: the union of the three pairwise syntheses' own lists.

The campaign's merge condition is that the whole oracle passes, and `replay.py`'s allow list
is the one place a lane says which differences its change causes.  This lane adds NOTHING: it
unions the three lists the pairwise stages measured and banked, records which lane each entry
came from, and refuses to introduce a kind none of them allowed.  The three sources (each of
which already contains `harness/baseline/allow.head.json`):

  identity x contract   wave1/synth-identity-contract/allow.measured.json
  contract x dispatch   wave1/synth-contract-dispatch/allow.json
  dispatch x jev        the `allow` embedded in wave1/synth-dispatch-jev/parity-shipped-run5/parity.json

    scripts/laplace-python tools/whole_allow.py --out <dir>
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

WAVE = pathlib.Path("/home/phujck/VScodeProjects/laplace/evidence/"
                    "WRITING_RECONCILIATION_2026-10-02/wave1")
HEAD = pathlib.Path("/home/phujck/VScodeProjects/laplace/evidence/"
                    "WRITING_RECONCILIATION_2026-10-02/harness/baseline/allow.head.json")

SOURCES = {
    "identity x contract": ("file", WAVE / "synth-identity-contract/allow.measured.json"),
    "contract x dispatch": ("file", WAVE / "synth-contract-dispatch/allow.json"),
    "dispatch x jev": ("parity", WAVE / "synth-dispatch-jev/parity-shipped-run5/parity.json"),
    "the head list every lane inherits": ("file", HEAD),
}


def load(kind: str, path: pathlib.Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload["allow"] if kind == "parity" else payload


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    merged: dict = {"kinds": [], "sources": {}, "operations": {}, "rows": {}}
    provenance: dict = {"operations": {}, "rows": {}, "sources": {}}
    for lane, (kind, path) in SOURCES.items():
        allow = load(kind, path)
        assert not allow.get("kinds"), (lane, "a blanket kind allowance", allow["kinds"])
        for bucket in ("sources", "operations", "rows"):
            for key, kinds in (allow.get(bucket) or {}).items():
                into = merged[bucket].setdefault(key, [])
                for one in kinds:
                    if one not in into:
                        into.append(one)
                provenance[bucket].setdefault(key, []).append(lane)
    for bucket in ("sources", "operations", "rows"):
        for key in merged[bucket]:
            merged[bucket][key] = sorted(merged[bucket][key])

    kinds_allowed = sorted({one for bucket in ("sources", "operations", "rows")
                            for kinds in merged[bucket].values() for one in kinds})
    merged["note"] = (
        "THE WHOLE-SYSTEM ALLOW LIST, built by tools/whole_allow.py as the UNION of the three "
        "pairwise syntheses' own banked lists (each of which already contains "
        "harness/baseline/allow.head.json).  This stage adds no entry of its own and no new "
        "kind: " + ", ".join(kinds_allowed) + " are exactly the kinds the pairwise stages "
        "measured, every one of them attributed in their reports to a named line.  `kinds` is "
        "empty, so no difference is ever ignored globally.  Provenance per entry is in "
        "allow.provenance.json beside this file."
    )

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "allow.whole.json").write_text(
        json.dumps(merged, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    (out / "allow.provenance.json").write_text(
        json.dumps(provenance, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print("sources   %d" % len(merged["sources"]), merged["sources"])
    print("operations %d" % len(merged["operations"]))
    print("rows      %d" % len(merged["rows"]))
    print("kinds allowed anywhere:", kinds_allowed)
    print("entries named by more than one lane: %d"
          % sum(1 for bucket in ("sources", "operations", "rows")
                for lanes in provenance[bucket].values() if len(lanes) > 1))
    print("written to", out / "allow.whole.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
