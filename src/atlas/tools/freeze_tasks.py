"""freeze_tasks - anchor a task source to a snapshot and mint the frozen bundle.

    python -m atlas.tools.freeze_tasks <snapshot_dir> --source atlas/bench/tasks/source_<date>.json

Reads the task DEFINITIONS as data, locates every atom inside a leaf span of the declared view,
and writes ``atlas/bench/tasks/<bundle_hex>/`` carrying ``tasks.json`` (the frozen bundle, with
anchors) and ``predictions.json`` (the pre-registered prediction table, copied verbatim from the
source and hashed).

The freeze happens BEFORE any scored run, and the ordering is provable rather than asserted: the
bundle records ``frozen_ts``, the run records ``started_ts``, and ``runner.run_bundle`` refuses
outright if the second is not after the first. A prediction table registered after the outcome is
not a prediction, and the ordering claim is the only thing that distinguishes them.

Nothing here degrades. An atom that does not resolve stops the mint with the task and the atom
named; the fix is to re-derive the task against the current record and say so in the source's
``re_derived_from``, which is a visible diff, not a quiet edit.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ..bench.freeze import anchor_task, freeze_bundle
from ..bench.task import BenchTask
from ..bench.universe import BENCH_FILTERED, FULL_UNIVERSE, RULED_ONLY, SnapshotView
from ..errors import AtlasError
from ..ids import hash_bytes
from ..snapshot import load_snapshot
from ..store import write_atomic
from .build_spans import verified_segmentation

DEFAULT_TASKS_DIR = Path(__file__).resolve().parents[3] / "atlas" / "bench" / "tasks"   # the container's bench data (R2)
UNIVERSES = {"bench-filtered": BENCH_FILTERED, "ruled-only": RULED_ONLY,
             "full": FULL_UNIVERSE}


def build(snapshot_dir: Path, source_path: Path, out_root: Path,
          universe_name: str = "bench-filtered") -> dict[str, Any]:
    source = json.loads(Path(source_path).read_text(encoding="utf-8"))
    bundle_dir_source = Path(source_path)
    universe = UNIVERSES[universe_name]

    snap = load_snapshot(snapshot_dir)
    snap.verify()
    segmentation = snap.segmentation()
    if segmentation is None:
        raise AtlasError("snapshot has no segmentation record - run atlas.tools.build_spans first",
                         snapshot=str(snapshot_dir))
    verified_segmentation(Path(snapshot_dir))
    view = SnapshotView(snap, universe)

    tasks = []
    for spec in source["tasks"]:
        if "anchors" in spec:
            tasks.append(BenchTask.from_dict(spec))
            continue
        tasks.append(anchor_task(
            view, task_id=spec["task_id"], task_class=spec["task_class"],
            question=spec["question"], atoms=spec["atoms"], window=spec["window"],
            source=spec["source"], truth_date=spec["truth_date"],
            intent=spec.get("intent", ""), re_derived=bool(spec.get("re_derived", False)),
            re_derived_from=spec.get("re_derived_from"),
            prefer_nodes=tuple(spec.get("prefer_nodes", ())),
        ))

    # The contamination scan runs INSIDE freeze_bundle (it is a mint gate, not a report); the
    # dict is passed so its record can be banked in freeze.json without a second pass.
    contamination: dict[str, Any] = {}
    bundle = freeze_bundle(
        view, segmentation_id=segmentation["generation_id"], tasks=tasks,
        notes=source.get("note", ""), planted=source.get("planted", []),
        contamination_scan=contamination,
    )
    out_dir = Path(out_root) / bundle.bundle_id.split(":", 1)[-1][:16]
    if out_dir.exists():
        raise AtlasError("frozen bundle directory already exists", path=str(out_dir))
    out_dir.mkdir(parents=True, exist_ok=True)

    tasks_bytes = (json.dumps(bundle.to_dict(), sort_keys=True, indent=1, ensure_ascii=False)
                   + "\n").encode("utf-8")
    write_atomic(out_dir / "tasks.json", tasks_bytes)

    predictions = dict(source["predictions"])
    predictions["registered_before"] = f"the first scored run of bundle {bundle.bundle_id}"
    predictions["bundle_id"] = bundle.bundle_id
    predictions["frozen_ts"] = bundle.frozen_ts
    pred_bytes = (json.dumps(predictions, sort_keys=True, indent=1, ensure_ascii=False)
                  + "\n").encode("utf-8")
    write_atomic(out_dir / "predictions.json", pred_bytes)

    write_atomic(out_dir / "freeze.json", (json.dumps({
        "bundle_id": bundle.bundle_id,
        "frozen_ts": bundle.frozen_ts,
        "snapshot_id": bundle.snapshot_id,
        "segmentation_id": bundle.segmentation_id,
        "universe": universe.to_dict(),
        "source": str(bundle_dir_source),
        "source_sha256": hash_bytes(Path(source_path).read_bytes()),
        "tasks_sha256": hash_bytes(tasks_bytes),
        "predictions_sha256": hash_bytes(pred_bytes),
        "view_stats": view.stats(),
        "task_count": len(tasks),
        "sampling": source.get("sampling", {"kind": "unspecified"}),
        "manifest_handle": snap.manifest.manifest_handle,
        "pinned_commit": snap.manifest.pinned_commit,
        "class_count": len(bundle.classes),
        "re_derived_count": sum(1 for t in tasks if t.re_derived),
        "contamination_scan": contamination,
    }, sort_keys=True, indent=2) + "\n").encode("utf-8"))

    return {"bundle": bundle, "path": out_dir, "view": view,
            "contamination": contamination}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="freeze a bench task bundle against a snapshot")
    ap.add_argument("snapshot_dir", type=Path)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--out-root", type=Path, default=DEFAULT_TASKS_DIR)
    ap.add_argument("--universe", default="bench-filtered", choices=sorted(UNIVERSES))
    args = ap.parse_args(argv)

    try:
        out = build(args.snapshot_dir, args.source, args.out_root, args.universe)
    except AtlasError as exc:
        print(f"REFUSED {exc}", file=sys.stderr)
        return 1
    bundle = out["bundle"]
    print(f"bundle_id         {bundle.bundle_id}")
    print(f"path              {out['path']}")
    print(f"frozen_ts         {bundle.frozen_ts}")
    print(f"snapshot_id       {bundle.snapshot_id}")
    print(f"segmentation_id   {bundle.segmentation_id}")
    print(f"universe          {bundle.universe['name']}")
    print(f"tasks             {len(bundle.tasks)} in {len(bundle.classes)} classes "
          f"({sum(1 for t in bundle.tasks if t.re_derived)} re-derived)")
    print(f"anchors           {sum(len(t.anchors) for t in bundle.tasks)}")
    receipt = json.loads((out["path"] / "freeze.json").read_text())
    print(f"predictions_sha256 {receipt['predictions_sha256']}")
    print(f"sampling          {json.dumps(receipt['sampling'], sort_keys=True)}")
    scan = out["contamination"]
    if not scan.get("applicable"):
        print(f"contamination     NOT APPLICABLE ({scan.get('nodes_scanned')} nodes < "
              f"{scan.get('min_nodes_for_density')} floor) - density needs a corpus")
    else:
        top = (scan.get("top") or [{}])[0]
        print(f"contamination     clean at share {scan['outlier_pair_share']:.2f}; densest node "
              f"{top.get('node_id')} {top.get('pairs')} pairs / {top.get('tasks')} tasks "
              f"(share {top.get('pair_share')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
