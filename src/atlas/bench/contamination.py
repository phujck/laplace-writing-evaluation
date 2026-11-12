"""contamination.py - the atom-density scan, run at FREEZE time so an answer key costs nothing.

WHY THIS EXISTS, and it is a repair rather than a precaution. The Phase 2 shake-out run measured
BM25 taking spans of ``scripts/reconstruction_bench_tasks.json`` - the v1 benchmark's own ANSWER
KEY, a file that pairs every question with its must-atoms - as its top hits on twelve of
twenty-one tasks, for a headline of 18/21 that measured "can this arm find the answer key". The
contamination was found by hand, late, after a scored run existed; the sealed judge then had to
re-derive it independently over all 4,385 nodes to confirm it was the ONLY one. Both verdict rows
(``SEV-20260801-atlas-phase2-r1``, ``-r2``) inherit the same instruction to Phase 3: bank that
scan as a freeze-time check. This is that bank. It is seconds, and it runs before a bundle mints.

WHAT IT MEASURES. For every unsealed text node in a view, the number of distinct
``(task_id, atom_index)`` pairs whose atom appears in that node's text, through the SAME bench
normalizer the scorer uses. Not a heuristic about filenames, not a path convention: the same
substring test that decides correctness, asked of the corpus instead of an arm's context.

THE RULE, AND ITS CALIBRATION - stated with the numbers rather than as a bare constant.

    measured on this bundle (21 tasks, 40 atom-task pairs, bench v2 bundle 1f6e1e43):

        scripts/reconstruction_bench_tasks.json   20 pairs / 11 tasks   = 0.500 of all pairs
        HANDOFF.md  (the legitimate maximum)      16 pairs /  9 tasks   = 0.400 of all pairs

    ``OUTLIER_PAIR_SHARE = 0.45`` sits between them. It is expressed as a SHARE of the bundle's
    total atom-task pairs rather than as a raw count, so it does not silently change meaning when
    a bundle gains tasks.

    THE MARGIN IS ONE PAIR WIDE ON EACH SIDE AND THAT IS SAID OUT LOUD. 18 pairs would trip;
    17 would not. A threshold calibrated on two points is a TRIPWIRE, not a proof, and this module
    never claims otherwise: density cannot tell an answer key from a genuinely central document by
    arithmetic alone - ``HANDOFF.md`` is *supposed* to carry many of the answers, because the
    questions are about the record and it is the record's live entry. What the tripwire buys is
    that a node of answer-key density cannot enter a scored corpus SILENTLY. The refusal names the
    node and the author or the judge rules on it; the ruling becomes a universe exclusion, which
    is data, and the exclusion is then measured against the ruled-only view like every other.

WHY THE VIEW AND NOT THE SNAPSHOT. A node the universe already excludes is not in the view, so it
cannot contaminate an arm and it cannot trip this check - which is exactly the "unless that node
is in the universe exclusions" carve-out, obtained structurally rather than by a second list that
could drift from the first. The consequence is a check a reader can run for themselves and see
work both ways: over ``bench-filtered/2`` this bundle passes, and over ``ruled-only/1`` - the
author's ruling, which does not exclude the answer key - it REFUSES and names the file.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ..errors import ContaminationDetected
from .scoring import atom_members, normalize
from .universe import SnapshotView

#: Identity of this check, folded into the freeze record so a bundle says which rule cleared it.
CONTAMINATION_VERSION = "atom-density/1"

#: The declared outlier threshold, as a share of the bundle's total (task, atom) pairs. Calibrated
#: on the two measured points named in the module docstring: 0.500 (the v1 answer key) against
#: 0.400 (the legitimate maximum). See that docstring for the one-pair margin, which is the honest
#: width of a threshold fitted to two observations.
OUTLIER_PAIR_SHARE = 0.45

#: THE APPLICABILITY FLOOR, and it is not a bypass - it is what stops the check from lying.
#:
#: Density is a statement about a node RELATIVE TO A CORPUS. On the four-node test fixture the one
#: document holding the atoms carries 100% of the pairs and is not contaminated by anything; it is
#: simply the only document there is. A share computed over a handful of nodes is not a share, so
#: below this floor the scan reports ``applicable: false`` and mints - it does not silently pass.
#: The freeze record carries that flag, so "the check did not run" is visible rather than absent.
#: The real corpus is 4,237 nodes in the headline view, two orders of magnitude above the floor.
MIN_NODES_FOR_DENSITY = 64


@dataclass(frozen=True)
class DensityRow:
    """One node's measured atom density. ``pairs`` is the number the threshold reads."""

    node_id: str
    pairs: int
    tasks: int
    task_ids: tuple[str, ...]
    pair_share: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id, "pairs": self.pairs, "tasks": self.tasks,
            "task_ids": list(self.task_ids), "pair_share": round(self.pair_share, 6),
        }


def total_pairs(tasks: list) -> int:
    """The denominator: one pair per (task, atom index) in the bundle. An any-of group is ONE."""
    return sum(len(t.atoms) for t in tasks)


def scan(view: SnapshotView, tasks: list) -> list[DensityRow]:
    """Score every node of ``view`` by how many (task, atom) pairs it carries. Densest first.

    Normalization happens once per node (``view.normalized_node_text`` caches it) and once per
    atom member, so the cost is one pass over the view's text - the "seconds, at mint" property
    that lets this run inside ``freeze_bundle`` rather than as a thing someone remembers to do.
    """
    denom = max(1, total_pairs(tasks))
    # Pre-normalize every atom member once: (task_id, atom_index, [normalized members]).
    wanted: list[tuple[str, int, list[str]]] = [
        (t.task_id, i, [normalize(m) for m in atom_members(atom)])
        for t in tasks for i, atom in enumerate(t.atoms)
    ]
    rows: list[DensityRow] = []
    for node_id in view.node_ids:
        hay = view.normalized_node_text(node_id)
        hit_tasks: list[str] = []
        pairs = 0
        for task_id, _index, members in wanted:
            if any(m in hay for m in members):
                pairs += 1
                if task_id not in hit_tasks:
                    hit_tasks.append(task_id)
        if pairs:
            rows.append(DensityRow(node_id=node_id, pairs=pairs, tasks=len(hit_tasks),
                                   task_ids=tuple(hit_tasks), pair_share=pairs / denom))
    # Densest first; node id breaks ties so the ordering is a property of the corpus.
    rows.sort(key=lambda r: (-r.pairs, r.node_id))
    return rows


def outliers(rows: list[DensityRow], threshold: float = OUTLIER_PAIR_SHARE) -> list[DensityRow]:
    """Every row at or above the declared share. Normally empty; normally the answer key when not."""
    return [r for r in rows if r.pair_share >= threshold]


def report(view: SnapshotView, tasks: list,
           threshold: float = OUTLIER_PAIR_SHARE) -> dict[str, Any]:
    """The whole scan as a record: the rule, the denominator, the top of the table, the verdict."""
    rows = scan(view, tasks)
    applicable = len(view.node_ids) >= MIN_NODES_FOR_DENSITY
    flagged = outliers(rows, threshold) if applicable else []
    return {
        "kind": "contamination-scan/1",
        "contamination_version": CONTAMINATION_VERSION,
        "universe": view.universe.name,
        "universe_id": view.universe_id,
        "snapshot_id": view.snapshot_id,
        "nodes_scanned": len(view.node_ids),
        "nodes_carrying_any_atom": len(rows),
        "total_task_atom_pairs": total_pairs(tasks),
        "outlier_pair_share": threshold,
        "applicable": applicable,
        "min_nodes_for_density": MIN_NODES_FOR_DENSITY,
        "top": [r.to_dict() for r in rows[:20]],
        "outliers": [r.to_dict() for r in flagged],
        "clean": applicable and not flagged,
    }


def assert_no_outlier(view: SnapshotView, tasks: list,
                      threshold: float = OUTLIER_PAIR_SHARE) -> dict[str, Any]:
    """Refuse a view whose densest node reads as an answer key. Returns the scan record if clean.

    The refusal is deliberately loud and specific - it names the node, its pair count, its share
    and the tasks it answers - because the action it asks for is a RULING (exclude it, or rule
    that it is record), and a ruling needs the evidence in front of it.
    """
    record = report(view, tasks, threshold)
    if record["outliers"]:
        worst = record["outliers"][0]
        raise ContaminationDetected(
            "a node in this view carries answer-key density: it holds the atoms of more than the "
            "declared share of the bundle's tasks. Exclude it from the universe or rule that it "
            "is record - a scored run over it measures whether an arm can find the answer key",
            node_id=worst["node_id"], pairs=worst["pairs"], tasks=worst["tasks"],
            pair_share=worst["pair_share"], threshold=threshold,
            total_task_atom_pairs=record["total_task_atom_pairs"],
            universe=view.universe.name, outlier_count=len(record["outliers"]),
        )
    return record


# ---------------------------------------------------------------------------
# the CLI, for bundles that are already frozen
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    """``python -m atlas.bench.contamination <snapshot_dir> --bundle <tasks.json>``.

    Exposed as a CLI because the freeze-time check only protects bundles minted from now on, and
    the bundles already banked are exactly the ones whose contamination has to be checkable by a
    reader who did not run the freeze.
    """
    import argparse
    import sys
    from pathlib import Path

    from ..errors import AtlasError
    from ..snapshot import load_snapshot
    from ..store import write_atomic
    from .task import BenchTaskBundle
    from .universe import BENCH_FILTERED, FULL_UNIVERSE, RULED_ONLY

    universes = {"bench-filtered": BENCH_FILTERED, "ruled-only": RULED_ONLY,
                 "full": FULL_UNIVERSE}
    ap = argparse.ArgumentParser(description="atom-density contamination scan over a frozen bundle")
    ap.add_argument("snapshot_dir")
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--universe", default="bench-filtered",
                    choices=sorted(universes) + ["all"])
    ap.add_argument("--threshold", type=float, default=OUTLIER_PAIR_SHARE)
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--json", default=None, help="bank the full scan record here")
    args = ap.parse_args(argv)

    names = sorted(universes) if args.universe == "all" else [args.universe]
    try:
        bundle = BenchTaskBundle.from_dict(
            json.loads(Path(args.bundle).read_text(encoding="utf-8")))
        snap = load_snapshot(Path(args.snapshot_dir))
    except AtlasError as exc:
        print(f"REFUSED {exc}", file=sys.stderr)
        return 1

    records: dict[str, Any] = {}
    refused = 0
    for name in names:
        view = SnapshotView(snap, universes[name])
        record = report(view, bundle.tasks, args.threshold)
        records[name] = record
        print(f"=== {name} ({record['nodes_scanned']} nodes scanned, "
              f"{record['total_task_atom_pairs']} task-atom pairs, "
              f"threshold {args.threshold:.2f} share) ===")
        for row in record["top"][: args.top]:
            mark = "  OUTLIER" if row["pair_share"] >= args.threshold else ""
            print(f"  {row['pairs']:>3} pairs  {row['tasks']:>3} tasks  "
                  f"{row['pair_share']:.3f}  {row['node_id']}{mark}")
        if record["outliers"]:
            refused += 1
            print(f"  REFUSED: {len(record['outliers'])} outlier(s) - a bundle would not mint "
                  f"against this view")
        else:
            print("  clean: no node reaches the declared share")
    if args.json:
        write_atomic(Path(args.json),
                     (json.dumps(records, sort_keys=True, indent=2) + "\n").encode("utf-8"))
        print(f"banked {args.json}")
    return 1 if refused and args.universe != "all" else 0


if __name__ == "__main__":
    raise SystemExit(main())
