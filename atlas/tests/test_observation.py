from __future__ import annotations

import dataclasses
import json
import os
import subprocess
from pathlib import Path

import pytest

from atlas.errors import BlobHashMismatch, ContentHashMismatch, StateTransitionRefused
from atlas.ids import canonical_json, hash_bytes
from atlas.observation import SemanticObservation
from atlas.schema import RecordSnapshot, SegmentationGeneration, SnapshotNode
from atlas.segment import segment_bytes
from atlas.snapshot import load_snapshot
from atlas.store import BlobStore, sha256_file, write_atomic, write_jsonl


def _observed_bundle(root: Path, body: bytes) -> tuple[Path, SegmentationGeneration]:
    root.mkdir(parents=True, exist_ok=True)
    content_hash = BlobStore(root / "blobs").put(body)
    node = SnapshotNode(
        node_id="governance.jsonl", path="governance.jsonl", kind="jsonl", sealed=False,
        is_text=True, read_policy="text", content_hash=content_hash,
        content_blob=content_hash, size_bytes=len(body),
    )
    write_jsonl(root / "nodes.jsonl", [node.to_dict()])
    seal = {
        "soul_paths_with_content": 0, "sealed_spans": 0, "sealed_nodes": 0,
        "bytes_read_from_sealed": 0, "sealed_prefixes": ["soul/"], "nodes_scanned": 1,
    }
    write_atomic(root / "seal_report.json", (canonical_json(seal) + "\n").encode())
    manifest = RecordSnapshot(
        snapshot_id="", created_ts="2026-08-28T00:00:00Z", atlas_schema_version="1",
        exporter_version="observation-test/1", source_repo="test", commit_sha="fixed",
        node_count=1, text_node_count=1, sealed_node_count=0, asset_node_count=0,
        total_content_bytes=len(body), nodes_sha256=sha256_file(root / "nodes.jsonl"),
        seal_report_sha256=sha256_file(root / "seal_report.json"), sealed_prefixes=["soul/"],
        sealed_paths=[], excluded_prefixes=[], text_extensions=[".jsonl"], node_limit=None,
        tree_dirty=False, dirty_node_count=0, dirty_nodes_hash=hash_bytes(b""),
    )
    manifest = dataclasses.replace(manifest, snapshot_id=manifest.computed_id())
    write_atomic(root / "manifest.json", (canonical_json(manifest.to_dict()) + "\n").encode())
    segmented = segment_bytes(
        node.node_id, node.path, node.content_hash, body, target_tokens=384,
        hard_cap_tokens=512,
    )
    write_jsonl(root / "spans.jsonl", (span.to_dict() for span in segmented.spans))
    generation = SegmentationGeneration(
        generation_id="", created_ts="2026-08-28T00:00:00Z",
        snapshot_id=manifest.snapshot_id, segmentation_recipe_version="seg/1",
        target_tokens=384, hard_cap_tokens=512,
        spans_sha256=sha256_file(root / "spans.jsonl"), span_count=len(segmented.spans),
        leaf_span_count=sum(span.is_leaf for span in segmented.spans),
        parent_span_count=sum(not span.is_leaf for span in segmented.spans),
        segmented_node_count=1, skipped_node_count=0, covered_bytes=len(body),
        total_bytes=len(body), coverage=1.0, oversize_spans=len(segmented.oversize),
        oversize_detail=list(segmented.oversize), structure_violations=0, sealed_spans=0,
        segmenter_ids=["structured-jsonl/1"], miss_events=list(segmented.misses),
    )
    generation = dataclasses.replace(generation, generation_id=generation.computed_id())
    write_atomic(root / "segmentation.json", (canonical_json(generation.to_dict()) + "\n").encode())
    return root, generation


def test_governance_rows_are_exact_atoms_and_fault_bytes_are_disjoint(tmp_path: Path) -> None:
    body = (
        b'{"record":"finding","id":"F-1","what":"one"}\n'
        b'{"record":"finding","id":"F-1","what":"duplicate"}\n'
        b'{"plain":"semantic content"}\n'
        b'\n'
        b'not-json\n'
        b'{"record":"finding"}\n'
    )
    root, generation = _observed_bundle(tmp_path / "observation", body)
    observation = SemanticObservation.build(load_snapshot(root), generation)

    assert observation.receipt.atom_count == 3
    assert {item.reason for item in observation.fog} == {
        "blank-jsonl-row", "invalid-jsonl-row", "malformed-governance-ref",
    }
    assert observation.receipt.atom_bytes + observation.receipt.fog_bytes == len(body)
    for atom in observation.atoms:
        assert load_snapshot(root).read_span_bytes(atom.span_id) == atom.content_utf8.encode()
        assert hash_bytes(atom.content_utf8.encode()) == atom.content_handle
        assert observation.atom(atom.atom_id) == atom
        assert observation.span(atom.span_id) == atom
    with pytest.raises(StateTransitionRefused, match="ambiguous"):
        observation.governance("finding", "F-1")


def test_generation_or_source_movement_refuses_exactly(tmp_path: Path) -> None:
    root, generation = _observed_bundle(
        tmp_path / "movement", b'{"record":"finding","id":"F-1"}\n'
    )
    bundle = load_snapshot(root)
    moved = dataclasses.replace(generation, snapshot_id="sha256:" + "9" * 64)
    moved = dataclasses.replace(moved, generation_id=moved.computed_id())
    with pytest.raises(ContentHashMismatch):
        SemanticObservation.build(bundle, moved)

    key = bundle.nodes["governance.jsonl"].content_blob
    assert key is not None
    bundle.blobs.key_path(key).write_bytes(b"one-byte movement")
    with pytest.raises(BlobHashMismatch):
        SemanticObservation.build(load_snapshot(root), generation)


def test_100k_rows_build_one_index_and_report_bounded_lookup(tmp_path: Path) -> None:
    body = b"".join(
        canonical_json({
            "record": "finding", "id": f"F-{index:06d}",
            "what": "x" * 56,
        }).encode() + b"\n"
        for index in range(100_000)
    )
    assert len(body) >= 10_000_000
    root, generation = _observed_bundle(tmp_path / "scale", body)
    source_bytes = len(body)
    del body
    project_root = Path(__file__).resolve().parents[2]
    child = r'''
import json
import os
import resource
import sys
import time
from pathlib import Path


def current_rss_kib():
    fields = Path("/proc/self/statm").read_text(encoding="ascii").split()
    return int(fields[1]) * int(os.sysconf("SC_PAGE_SIZE")) // 1024


baseline_rss_kib = current_rss_kib()
baseline_high_water_kib = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
from atlas.observation import SemanticObservation
from atlas.schema import SegmentationGeneration
from atlas.snapshot import load_snapshot

root = Path(sys.argv[1])
generation = SegmentationGeneration.from_dict(
    json.loads((root / "segmentation.json").read_text(encoding="utf-8"))
)
bundle = load_snapshot(root)
observation = SemanticObservation.build(bundle, generation)
assert bundle._spans is None
started = time.perf_counter()
for index in range(0, 100_000, 10):
    atom = observation.governance("finding", f"F-{index:06d}")
    assert atom.governance_ref == {"record": "finding", "id": f"F-{index:06d}"}
lookup_ms = (time.perf_counter() - started) * 1000.0
peak_rss_kib = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
peak_growth_kib = max(0, peak_rss_kib - baseline_rss_kib)
receipt = observation.receipt.to_dict()
assert receipt["atom_count"] == 100_000
assert receipt["fog_count"] == 0
assert receipt["atom_bytes"] == 10_300_000
assert receipt["atom_root"] == "sha256:8733cb3ddb8f39e5130cc47e13ab5bda74e487ad4678bc28e0018f3fdef997bf"
assert receipt["fog_root"] == "sha256:4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
assert receipt["governance_root"] == "sha256:e0bdd59a7a834d0bff23f06489bddb3ab7b969ef114bf76e99db33d33916115f"
assert peak_growth_kib <= 256 * 1024
assert lookup_ms < max(2_000.0, receipt["build_wall_ms"])
print(json.dumps({
    **receipt,
    "fresh_child_baseline_rss_kib": baseline_rss_kib,
    "fresh_child_baseline_high_water_kib": baseline_high_water_kib,
    "fresh_child_peak_rss_kib": peak_rss_kib,
    "fresh_child_peak_growth_kib": peak_growth_kib,
    "lookup_10k_ms": round(lookup_ms, 3),
    "superseded_prior_same_process_rss_delta_kib": {
        "value": 182_380,
        "status": "INVALID-SUPERSEDED-NOT-A-BOUND",
    },
    "superseded_prior_process_high_water_kib": {
        "value": 1_831_768,
        "status": "INVALID-SUPERSEDED-NOT-A-BOUND",
    },
}))
'''
    result = subprocess.run(
        ["/usr/bin/python3", "-c", child, str(root)],
        cwd=project_root,
        env={
            **os.environ,
            "PYTHONPATH": f"{project_root / 'src'}",
        },
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    metrics = json.loads(result.stdout.strip().splitlines()[-1])
    assert metrics["atom_count"] == 100_000
    assert metrics["atom_bytes"] == source_bytes
    assert metrics["fresh_child_peak_growth_kib"] <= 256 * 1024
    assert metrics["superseded_prior_same_process_rss_delta_kib"]["status"] == (
        "INVALID-SUPERSEDED-NOT-A-BOUND"
    )
    assert metrics["superseded_prior_process_high_water_kib"]["status"] == (
        "INVALID-SUPERSEDED-NOT-A-BOUND"
    )
    print(json.dumps(metrics))
