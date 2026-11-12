"""re_anchor - the decay DETECTOR: classify a frozen bundle's atoms against a newer snapshot.

    python -m atlas.tools.re_anchor <new_snapshot_dir> --bundle atlas/bench/tasks/<hex>/tasks.json

Design §6's same-day mode. Headline claims come from FROZEN mode over a shared snapshot; this is
the drift monitor, and the decay rate it reports is itself a published number. Every atom is
classified against the newer snapshot:

    stable       the anchor span still exists with the same content hash and still holds the atom
    re-anchored  the atom moved, and a span in the new snapshot holds it
    decayed      the atom is not in the new snapshot at all

Nothing is re-scored. The frozen bundle is not modified and no new bundle is minted here: a
frozen result quietly re-scored against moved ground truth is the exact defect this whole phase
exists to remove.

WHAT THIS MODE CAN AND CANNOT SHOW IN ONE SESSION. The Phase 2 gate as written wants NONZERO
decay over a week of repository movement, on the reasoning that zero decay would mean the
re-anchoring is hiding the defect it exists to catch. A week is not available inside one session,
and this tool cannot manufacture one. What it does show is same-session drift - the snapshot
re-exported after the session's own edits exist - and the detector's ability to CLASSIFY a moved
atom as decayed is proved separately and mechanically, by a fixture test that rewrites a
paragraph and asserts the verdict (``atlas/tests/test_bench_freeze.py``). The honest statement is
that the detector is proved and the week of drift is owed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..bench.freeze import re_anchor
from ..bench.task import BenchTaskBundle
from ..bench.universe import BENCH_FILTERED, FULL_UNIVERSE, RULED_ONLY, SnapshotView
from ..errors import AtlasError
from ..snapshot import load_snapshot
from ..store import write_atomic

UNIVERSES = {"bench-filtered": BENCH_FILTERED, "ruled-only": RULED_ONLY,
             "full": FULL_UNIVERSE}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="re-anchor a frozen bundle against a newer snapshot")
    ap.add_argument("new_snapshot_dir", type=Path)
    ap.add_argument("--bundle", type=Path, required=True)
    ap.add_argument("--universe", default="bench-filtered", choices=sorted(UNIVERSES))
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)

    try:
        bundle = BenchTaskBundle.from_dict(json.loads(args.bundle.read_text(encoding="utf-8")))
        view = SnapshotView(load_snapshot(args.new_snapshot_dir), UNIVERSES[args.universe])
        report = re_anchor(bundle, view)
    except AtlasError as exc:
        print(f"REFUSED {exc}", file=sys.stderr)
        return 1

    counts = report["counts"]
    total = sum(counts.values())
    print(f"bundle            {report['bundle_id']}")
    print(f"frozen snapshot   {report['frozen_snapshot']}")
    print(f"new snapshot      {report['new_snapshot']}")
    print(f"universe          {report['universe']}")
    print(f"tasks             {total}")
    for key in ("stable", "re-anchored", "decayed"):
        share = (counts[key] / total * 100) if total else 0.0
        print(f"  {key:<12} {counts[key]:>3}  ({share:.1f}%)")
    moved = [t["task_id"] for t in report["tasks"] if t["status"] != "stable"]
    if moved:
        print(f"moved             {', '.join(moved)}")
    if args.out:
        write_atomic(args.out, (json.dumps(report, sort_keys=True, indent=2) + "\n")
                     .encode("utf-8"))
        print(f"banked            {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
