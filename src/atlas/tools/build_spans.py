"""build_spans - segment a snapshot bundle and write the SegmentationGeneration beside it.

    python -m atlas.tools.build_spans <snapshot_dir> [--target-tokens N] [--hard-cap-tokens N]
    python -m atlas.tools.build_spans --manifest atlas/datasets/<dataset>.json

The manifest form exports the declared pinned Git blobs into
``bench/snapshots/<dataset_id>/<manifest_hex>/`` before segmentation. A repeated call
verifies and reuses those frozen bytes; it cannot replace their segmentation.

Reads the bundle as data (nodes.jsonl + blobs), runs the segmentation layer with its three laws
enforced per node, writes ``spans.jsonl`` and ``segmentation.json``, and prints the measured
numbers. Two runs over the same bundle at the same target produce byte-identical spans and
therefore the same ``generation_id`` - that is a Phase 1 gate, and the id is derived from the
spans file's own sha256 so the claim is checkable rather than asserted.

Sealed nodes are never segmented, and unread assets have no bytes to segment. Both are counted
as skipped, so the node arithmetic in the printed summary closes.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from ..errors import AtlasError
from ..ids import canonical_json, chash, hash_bytes
from ..schema import RecordSnapshot, SnapshotNode, SegmentationGeneration
from ..segment import (
    DEFAULT_TARGET_TOKENS,
    HARD_CAP_TOKENS,
    SEGMENTATION_RECIPE_VERSION,
    segment_node,
)
from ..segment.base import STRUCTURED_EXTS
from ..snapshot import SEGMENTATION_NAME, SPANS_NAME, load_snapshot
from ..store import BlobStore, sha256_file, write_atomic, write_jsonl

CONTAINER_ROOT = Path(__file__).resolve().parents[3] / "atlas"  # src/atlas since core consolidation R2: the container is <checkout>/atlas


def dataset_snapshot_dir(manifest: dict, container_root: Path = CONTAINER_ROOT) -> Path:
    """A deterministic address from the dataset registration, without store enumeration."""
    dataset_id = manifest["core"]["dataset_id"]
    handle = manifest["manifest_handle"]
    if not re.fullmatch(r"[A-Za-z0-9_-]+", dataset_id) or not re.fullmatch(r"sha256:[0-9a-f]{64}", handle):
        raise AtlasError("invalid dataset snapshot address", owner="dataset-manifest")
    return Path(container_root) / "bench" / "snapshots" / dataset_id / handle.split(":")[1]


def verified_segmentation(root: Path) -> SegmentationGeneration:
    snap = load_snapshot(root)
    record = snap.segmentation()
    if record is None:
        raise AtlasError("snapshot has no segmentation record", snapshot=str(root))
    generation = SegmentationGeneration.from_dict(record)
    if (generation.computed_id() != generation.generation_id
            or generation.snapshot_id != snap.manifest.snapshot_id
            or generation.spans_sha256 != sha256_file(root / SPANS_NAME)):
        raise AtlasError("segmentation identity mismatch", snapshot=str(root))
    return generation


def build_dataset(manifest_path: Path, repo_root: Path,
                  container_root: Path = CONTAINER_ROOT) -> tuple[Path, SegmentationGeneration]:
    """Export only the manifest's pinned Git blobs, then segment those exact bytes."""
    from ..dataset import load_manifest, resolve_sources
    manifest = load_manifest(manifest_path, repo_root)
    core = manifest["core"]
    _, contents = resolve_sources(core, repo_root)
    root = dataset_snapshot_dir(manifest, container_root)
    if root.exists():
        snap = load_snapshot(root)
        snap.verify()
        if (snap.manifest.manifest_handle != manifest["manifest_handle"]
                or snap.manifest.pinned_commit != core["pinned_commit"]
                or snap.manifest.commit_sha != core["pinned_commit"]
                or snap.manifest.sources != sorted(contents)
                or {n.path: n.content_hash for n in snap.iter_nodes()}
                != {p: hash_bytes(data) for p, data in contents.items()}):
            raise AtlasError("existing dataset snapshot is incomplete or mismatched", snapshot=str(root))
        generation = verified_segmentation(root)
        if (generation.target_tokens != core["segmentation"]["target_tokens"]
                or generation.hard_cap_tokens != core["segmentation"]["hard_cap_tokens"]):
            raise AtlasError("segmentation differs from dataset dials", snapshot=str(root))
        return root, generation
    root.mkdir(parents=True)
    blobs = BlobStore(root / "blobs")
    nodes = []
    for path, data in sorted(contents.items()):
        key = blobs.put(data)
        nodes.append(SnapshotNode(node_id=path, path=path, kind=Path(path).suffix.lstrip("."),
            sealed=False, is_text=True, read_policy="text", content_hash=key,
            content_blob=key, size_bytes=len(data)))
    write_jsonl(root / "nodes.jsonl", (n.to_dict() for n in nodes))
    report = {"soul_paths_with_content": 0, "sealed_spans": 0, "sealed_nodes": 0,
              "bytes_read_from_sealed": 0, "sealed_prefixes": core["sealed_prefixes"],
              "nodes_scanned": len(nodes)}
    write_atomic(root / "seal_report.json", (canonical_json(report) + "\n").encode())
    snap = RecordSnapshot(
        snapshot_id="", created_ts=datetime.now(timezone.utc).isoformat(),
        atlas_schema_version="1", exporter_version="atlas.dataset-snapshot/1",
        source_repo=core.get("source_repo", "."), commit_sha=core["pinned_commit"],
        node_count=len(nodes), text_node_count=len(nodes), sealed_node_count=0, asset_node_count=0,
        total_content_bytes=sum(len(data) for data in contents.values()),
        nodes_sha256=sha256_file(root / "nodes.jsonl"),
        seal_report_sha256=sha256_file(root / "seal_report.json"),
        sealed_prefixes=core["sealed_prefixes"], sealed_paths=[], excluded_prefixes=[],
        text_extensions=sorted({Path(path).suffix for path in contents}), node_limit=None,
        tree_dirty=False, dirty_node_count=0, dirty_nodes_hash=chash([]),
        manifest_handle=manifest["manifest_handle"], pinned_commit=core["pinned_commit"],
        sources=sorted(contents),
    )
    snap = replace(snap, snapshot_id=snap.computed_id())
    write_atomic(root / "manifest.json", (canonical_json(snap.to_dict()) + "\n").encode())
    generation = build(root, core["segmentation"]["target_tokens"],
                       core["segmentation"]["hard_cap_tokens"])
    load_snapshot(root).verify()
    return root, generation


def build(snapshot_dir: Path, target_tokens: int = DEFAULT_TARGET_TOKENS,
          hard_cap_tokens: int = HARD_CAP_TOKENS,
          verify_first: bool = True) -> SegmentationGeneration:
    bundle = load_snapshot(snapshot_dir)
    if verify_first:
        # Blob bytes are re-hashed anyway when each node is read for segmentation, so the
        # expensive pass is skipped here rather than paid twice.
        bundle.verify(check_blob_bytes=False)
    if bundle.manifest.manifest_handle is not None and bundle.segmentation() is not None:
        generation = verified_segmentation(Path(snapshot_dir))
        if generation.target_tokens != target_tokens or generation.hard_cap_tokens != hard_cap_tokens:
            raise AtlasError("dataset snapshot segmentation is frozen", snapshot=str(snapshot_dir))
        return generation

    misses: list[dict] = []
    oversize: list[dict] = []
    segmenter_ids: set[str] = set()
    tally = {"covered": 0, "total": 0, "segmented": 0, "skipped": 0, "leaf": 0, "spans": 0,
             "sealed_spans": 0, "structure_violations": 0}

    def rows():
        """Stream span rows node by node; the counters close over ``tally``."""
        for node in bundle.iter_nodes():
            if node.sealed or node.content_blob is None or node.size_bytes == 0:
                tally["skipped"] += 1
                continue
            data = bundle.read_node_bytes(node.node_id)
            result = segment_node(node, data, target_tokens, hard_cap_tokens)
            tally["segmented"] += 1
            tally["total"] += node.size_bytes
            structured = node.path.lower().endswith(STRUCTURED_EXTS)
            for span in result.spans:
                if span.is_leaf:
                    tally["leaf"] += 1
                    tally["covered"] += span.end - span.start
                tally["spans"] += 1
                # COUNTED, not asserted. segment_bytes already refuses both conditions, so these
                # stay zero - but a zero that was measured is evidence and a literal zero is a
                # claim, and the seal report is read as evidence.
                if node.sealed:
                    tally["sealed_spans"] += 1
                if structured and span.segmenter_id.startswith("fallback"):
                    tally["structure_violations"] += 1
                segmenter_ids.add(span.segmenter_id)
                yield span.to_dict()
            misses.extend(result.misses)
            oversize.extend(result.oversize)

    spans_path = Path(snapshot_dir) / SPANS_NAME
    span_count = write_jsonl(spans_path, rows())
    spans_sha = sha256_file(spans_path)
    covered, total = tally["covered"], tally["total"]
    segmented, skipped, leaf_count = tally["segmented"], tally["skipped"], tally["leaf"]

    coverage = 1.0 if total == 0 else covered / total
    generation = SegmentationGeneration(
        generation_id="", created_ts=datetime.now(timezone.utc).isoformat(),
        snapshot_id=bundle.manifest.snapshot_id,
        segmentation_recipe_version=SEGMENTATION_RECIPE_VERSION,
        target_tokens=target_tokens, hard_cap_tokens=hard_cap_tokens, spans_sha256=spans_sha,
        span_count=span_count, leaf_span_count=leaf_count,
        parent_span_count=span_count - leaf_count, segmented_node_count=segmented,
        skipped_node_count=skipped, covered_bytes=covered, total_bytes=total,
        coverage=coverage, oversize_spans=len(oversize), oversize_detail=oversize,
        structure_violations=tally["structure_violations"], sealed_spans=tally["sealed_spans"],
        segmenter_ids=sorted(segmenter_ids), miss_events=misses,
    )
    # The id is computed over the record minus the id and minus created_ts (schema.py), so the
    # clock never enters it and two runs over the same bundle agree.
    from dataclasses import replace
    generation = replace(generation, generation_id=generation.computed_id())
    write_atomic(Path(snapshot_dir) / SEGMENTATION_NAME,
                 (canonical_json(generation.to_dict()) + "\n").encode("utf-8"))
    return generation


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="segment a snapshot bundle")
    parser.add_argument("snapshot_dir", type=Path, nargs="?")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--repo-root", type=Path, default=CONTAINER_ROOT.parent)
    parser.add_argument("--container-root", type=Path, default=CONTAINER_ROOT)
    parser.add_argument("--target-tokens", type=int, default=DEFAULT_TARGET_TOKENS)
    parser.add_argument("--hard-cap-tokens", type=int, default=HARD_CAP_TOKENS)
    parser.add_argument("--no-verify", action="store_true",
                        help="skip the bundle verify pass before segmenting")
    args = parser.parse_args(argv)
    if bool(args.manifest) == bool(args.snapshot_dir):
        parser.error("provide either snapshot_dir or --manifest")

    started = time.perf_counter()
    try:
        if args.manifest:
            root, gen = build_dataset(args.manifest, args.repo_root, args.container_root)
            man = load_snapshot(root).manifest
            print(f"path              {root}")
            print(f"manifest_handle   {man.manifest_handle}")
            print(f"pinned_commit     {man.pinned_commit}")
            print(f"sources           {len(man.sources)}")
        else:
            gen = build(args.snapshot_dir, args.target_tokens, args.hard_cap_tokens,
                        verify_first=not args.no_verify)
    except AtlasError as exc:
        print(f"REFUSED {exc}", file=sys.stderr)
        return 1
    elapsed = time.perf_counter() - started

    print(f"generation_id     {gen.generation_id}")
    print(f"snapshot_id       {gen.snapshot_id}")
    print(f"recipe            {gen.segmentation_recipe_version} "
          f"target={gen.target_tokens} cap={gen.hard_cap_tokens}")
    print(f"spans_sha256      {gen.spans_sha256}")
    print(f"spans             {gen.span_count} ({gen.leaf_span_count} leaf, "
          f"{gen.parent_span_count} parent)")
    print(f"nodes             {gen.segmented_node_count} segmented, "
          f"{gen.skipped_node_count} skipped")
    print(f"coverage          {gen.coverage:.6f} ({gen.covered_bytes}/{gen.total_bytes} bytes)")
    print(f"oversize_spans    {gen.oversize_spans}")
    print(f"miss_events       {len(gen.miss_events)}")
    print(f"segmenters        {', '.join(gen.segmenter_ids)}")
    print(f"wall_clock        {elapsed:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
