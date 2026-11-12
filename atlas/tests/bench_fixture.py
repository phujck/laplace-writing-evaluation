"""bench_fixture.py - a tiny real snapshot for the bench tests, built the way the exporter builds.

Not a mock. The bench tests run against a genuine bundle written with the atlas hashing law and
segmented by the real segmentation layer, because the defects worth catching - an anchor that
does not resolve, a span whose content hash moved, a view that serves an excluded node - only
exist when the objects are the real ones.

Small on purpose: four text nodes, one sealed node, one node inside the excluded universe. That
is enough for coverage, exclusion, anchoring, decay and determinism, and it runs in milliseconds.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from atlas.ids import canonical_json, hash_bytes
from atlas.schema import REFS_ONLY, RecordSnapshot, SnapshotNode
from atlas.segment import segment_bytes
from atlas.snapshot import load_snapshot
from atlas.store import BlobStore, sha256_file, write_atomic, write_jsonl

#: Long enough to cut into several leaf spans at the 384-token target - a one-span fixture would
#: make the span-level anchoring and the span content hash indistinguishable from node-level work,
#: which is the whole thing under test.
_FILLER = "\n\n".join(
    f"Paragraph {i} of the handoff body, kept here so the segmenter has something to cut. "
    "It says nothing an answer atom depends on."
    for i in range(40)
)
DOC = (
    "# Handoff\n\n"
    "## NEXT AIM\n\n"
    "The next move is to run the widget sweep, and correctness comes before cost.\n\n"
    "## body\n\n"
    f"{_FILLER}\n\n"
    "## superseded\n\n"
    "The old aim was to polish the gadget.\n"
)
LAW = "# Law\n\nderive it, decide it, and record it.\n\nA claim of delivery names its run.\n"
EVID = ("# Evidence\n\nThe agreement at beam 8 was 0.835 and the descent touched "
        "0.8% of the corpus.\n")
VENDOR = "# vendored\n\nthe widget sweep is mentioned here too, in excluded territory.\n"


def build_bundle(root: Path, doc: str = DOC) -> Path:
    """Write a verifiable bundle with spans and a segmentation record beside it."""
    files = {
        "HANDOFF.md": doc.encode("utf-8"),
        "STANDING_LAW.md": LAW.encode("utf-8"),
        "evidence/agree.md": EVID.encode("utf-8"),
        "node_modules/vendor.md": VENDOR.encode("utf-8"),
    }
    root.mkdir(parents=True, exist_ok=True)
    store = BlobStore(root / "blobs")
    nodes: list[SnapshotNode] = []
    for path, data in files.items():
        key = hash_bytes(data)
        store.put(data)
        nodes.append(SnapshotNode(node_id=path, path=path, kind="md", sealed=False, is_text=True,
                                  read_policy="text", content_hash=key, content_blob=key,
                                  size_bytes=len(data)))
    nodes.append(SnapshotNode(node_id="soul/private.md", path="soul/private.md", kind="soul",
                              sealed=True, is_text=False, read_policy="sealed-refs-only",
                              content_hash=REFS_ONLY, content_blob=None, size_bytes=0))
    nodes.sort(key=lambda n: n.node_id)
    write_jsonl(root / "nodes.jsonl", [n.to_dict() for n in nodes])

    spans = []
    for path, data in files.items():
        result = segment_bytes(path, path, hash_bytes(data), data, 384, 512)
        spans.extend(result.spans)
    write_jsonl(root / "spans.jsonl", [s.to_dict() for s in spans])

    report = {"soul_paths_with_content": 0, "sealed_spans": 0, "sealed_nodes": 1,
              "bytes_read_from_sealed": 0, "sealed_prefixes": ["soul/"],
              "nodes_scanned": len(nodes)}
    write_atomic(root / "seal_report.json", (canonical_json(report) + "\n").encode("utf-8"))

    man = RecordSnapshot(
        snapshot_id="", created_ts="2026-08-01T00:00:00+00:00", atlas_schema_version="1",
        exporter_version="1", source_repo="laplace", commit_sha="deadbeef",
        node_count=len(nodes), text_node_count=len(files), sealed_node_count=1,
        asset_node_count=0, total_content_bytes=sum(len(d) for d in files.values()),
        nodes_sha256=sha256_file(root / "nodes.jsonl"),
        seal_report_sha256=sha256_file(root / "seal_report.json"),
        sealed_prefixes=["soul/"], sealed_paths=[], excluded_prefixes=["atlas/stores/"],
        text_extensions=[".md"], node_limit=None, tree_dirty=False,
        dirty_node_count=0, dirty_nodes_hash="sha256:" + "5" * 64,
    )
    man = dataclasses.replace(man, snapshot_id=man.computed_id())
    write_atomic(root / "manifest.json",
                 (json.dumps(man.to_dict(), sort_keys=True, indent=2) + "\n").encode("utf-8"))
    write_atomic(root / "segmentation.json", (json.dumps({
        "generation_id": "sha256:" + "a" * 64, "snapshot_id": man.snapshot_id,
    }) + "\n").encode("utf-8"))
    return root


def open_bundle(root: Path):
    return load_snapshot(root)
