"""test_snapshot.py - what a bundle must be before it is allowed to travel.

Every refusal snapshot.verify can make has a test that triggers it: a tampered manifest, a
tampered nodes file, tampered blob bytes, a sealed node carrying content, a soul path carrying
content, a span cut over a sealed node, a nonzero seal report, a hole in the leaf partition, and
a parent span that does not contain its child. Plus the byte-exact round trip on a tmp fixture.

The fixture writes bundles exactly the way ``scripts/export_atlas_snapshot.py`` does, using the
atlas-side hashing functions - which is also how the two implementations of the hashing law are
held to agreement.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from atlas.errors import (
    BlobHashMismatch,
    ContentHashMismatch,
    CoverageViolation,
    NestingViolation,
    SealedRead,
    SealViolation,
    SnapshotIdMismatch,
    SnapshotIncomplete,
)
from atlas.ids import canonical_json, hash_bytes
from atlas.schema import NOT_READ, REFS_ONLY, RecordSnapshot, SnapshotNode, Span
from atlas.snapshot import load_snapshot
from atlas.store import BlobStore, sha256_file, write_atomic, write_jsonl

# ---------------------------------------------------------------------------
# the fixture writer
# ---------------------------------------------------------------------------

def text_node(path: str, data: bytes) -> SnapshotNode:
    key = hash_bytes(data)
    return SnapshotNode(node_id=path, path=path, kind=path.rsplit(".", 1)[-1], sealed=False,
                        is_text=True, read_policy="text", content_hash=key, content_blob=key,
                        size_bytes=len(data))


def sealed_node(path: str) -> SnapshotNode:
    return SnapshotNode(node_id=path, path=path, kind="soul", sealed=True, is_text=False,
                        read_policy="sealed-refs-only", content_hash=REFS_ONLY,
                        content_blob=None, size_bytes=0)


def asset_node(path: str, size: int = 99) -> SnapshotNode:
    return SnapshotNode(node_id=path, path=path, kind=path.rsplit(".", 1)[-1], sealed=False,
                        is_text=False, read_policy="asset-not-read", content_hash=NOT_READ,
                        content_blob=None, size_bytes=size)


def write_bundle(root: Path, nodes: list[SnapshotNode], blobs: dict[str, bytes],
                 spans: list[Span] | None = None,
                 seal_report: dict | None = None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    store = BlobStore(root / "blobs")
    for data in blobs.values():
        store.put(data)
    rows = sorted((n.to_dict() for n in nodes), key=lambda r: r["node_id"])
    write_jsonl(root / "nodes.jsonl", rows)
    if spans is not None:
        write_jsonl(root / "spans.jsonl", [s.to_dict() for s in spans])
    sealed_n = sum(1 for n in nodes if n.sealed)
    report = seal_report if seal_report is not None else {
        "soul_paths_with_content": 0, "sealed_spans": 0, "sealed_nodes": sealed_n,
        "bytes_read_from_sealed": 0, "sealed_prefixes": ["soul/"], "nodes_scanned": len(rows),
    }
    write_atomic(root / "seal_report.json", (canonical_json(report) + "\n").encode("utf-8"))
    man = RecordSnapshot(
        snapshot_id="", created_ts="2026-08-01T00:00:00+00:00", atlas_schema_version="1",
        exporter_version="1", source_repo="laplace", commit_sha="deadbeef",
        node_count=len(rows), text_node_count=sum(1 for n in nodes if n.read_policy == "text"),
        sealed_node_count=sealed_n,
        asset_node_count=sum(1 for n in nodes if n.read_policy == "asset-not-read"),
        total_content_bytes=sum(n.size_bytes for n in nodes if n.read_policy == "text"),
        nodes_sha256=sha256_file(root / "nodes.jsonl"),
        seal_report_sha256=sha256_file(root / "seal_report.json"),
        sealed_prefixes=["soul/"], sealed_paths=[], excluded_prefixes=["atlas/stores/"],
        text_extensions=[".md", ".py"], node_limit=None, tree_dirty=False,
        dirty_node_count=0, dirty_nodes_hash="sha256:" + "5" * 64,
    )
    man = dataclasses.replace(man, snapshot_id=man.computed_id())
    write_atomic(root / "manifest.json",
                 (json.dumps(man.to_dict(), sort_keys=True, indent=2) + "\n").encode("utf-8"))
    return root


@pytest.fixture()
def bundle(tmp_path):
    body = b"# Title\n\nsome content bytes\n"
    other = b"def f():\n    return 1\n"
    nodes = [text_node("a/doc.md", body), text_node("b/mod.py", other),
             sealed_node("soul/private.md"), asset_node("art/logo.png")]
    blobs = {hash_bytes(body): body, hash_bytes(other): other}
    return write_bundle(tmp_path / "snap", nodes, blobs)


# ---------------------------------------------------------------------------
# the clean path
# ---------------------------------------------------------------------------

def test_clean_bundle_verifies(bundle):
    report = load_snapshot(bundle).verify()
    assert report["soul_paths_with_content"] == 0
    assert report["sealed_spans"] == 0


def test_byte_exact_round_trip(bundle):
    snap = load_snapshot(bundle)
    assert snap.read_node_bytes("a/doc.md") == b"# Title\n\nsome content bytes\n"
    assert snap.read_node_bytes("b/mod.py") == b"def f():\n    return 1\n"


def test_exact_span_lookup_returns_source_slice_and_missing_refuses(tmp_path):
    body = b"first\nsecond\n"
    node = text_node("rows.jsonl", body)
    span = _leaf(node, 0, 6)
    root = write_bundle(tmp_path / "spans", [node], {node.content_hash: body}, [
        span, _leaf(node, 6, len(body)),
    ])
    snap = load_snapshot(root)
    snap.verify()
    assert snap.read_span(span.span_id) == span
    assert snap.read_span_bytes(span.span_id) == b"first\n"
    with pytest.raises(SnapshotIncomplete):
        snap.read_span_bytes("sha256:" + "f" * 64)


def test_reading_a_sealed_node_refuses(bundle):
    with pytest.raises(SealedRead) as exc:
        load_snapshot(bundle).read_node_bytes("soul/private.md")
    assert exc.value.reason == "snapshot-sealed-read"


def test_reading_an_unread_asset_refuses(bundle):
    with pytest.raises(SealedRead):
        load_snapshot(bundle).read_node_bytes("art/logo.png")


# ---------------------------------------------------------------------------
# tampering
# ---------------------------------------------------------------------------

def test_tampered_manifest_refuses(bundle):
    raw = json.loads((bundle / "manifest.json").read_text())
    raw["node_count"] = raw["node_count"] + 1
    (bundle / "manifest.json").write_text(json.dumps(raw))
    with pytest.raises(SnapshotIdMismatch) as exc:
        load_snapshot(bundle).verify()
    assert exc.value.reason == "snapshot-id-mismatch"


def test_tampered_nodes_file_refuses(bundle):
    path = bundle / "nodes.jsonl"
    path.write_bytes(path.read_bytes().replace(b"a/doc.md", b"a/DOC.md"))
    with pytest.raises(ContentHashMismatch):
        load_snapshot(bundle).verify()


def test_tampered_blob_bytes_refuses(bundle):
    snap = load_snapshot(bundle)
    key = snap.nodes["a/doc.md"].content_blob
    snap.blobs.key_path(key).write_bytes(b"different bytes entirely")
    with pytest.raises(BlobHashMismatch) as exc:
        load_snapshot(bundle).verify()
    assert exc.value.reason == "store-blob-hash-mismatch"


# ---------------------------------------------------------------------------
# the seal
# ---------------------------------------------------------------------------

def test_sealed_node_with_content_refuses(tmp_path):
    body = b"private"
    leaked = SnapshotNode(node_id="soul/x.md", path="soul/x.md", kind="soul", sealed=True,
                          is_text=True, read_policy="text", content_hash=hash_bytes(body),
                          content_blob=hash_bytes(body), size_bytes=len(body))
    root = write_bundle(tmp_path / "snap", [leaked], {hash_bytes(body): body})
    with pytest.raises(SealViolation) as exc:
        load_snapshot(root).verify()
    assert exc.value.reason == "snapshot-seal-violation"


def test_soul_path_unsealed_with_content_refuses(tmp_path):
    body = b"private"
    leaked = text_node("soul/entities/person.md", body)
    root = write_bundle(tmp_path / "snap", [leaked], {hash_bytes(body): body})
    with pytest.raises(SealViolation):
        load_snapshot(root).verify()


def test_second_sealed_zone_is_enforced_too(tmp_path):
    body = b"private"
    leaked = text_node("soul_corpus/sealed/dump.md", body)
    root = write_bundle(tmp_path / "snap", [leaked], {hash_bytes(body): body})
    with pytest.raises(SealViolation):
        load_snapshot(root).verify()


def test_nonzero_seal_report_refuses(tmp_path):
    body = b"ok"
    root = write_bundle(tmp_path / "snap", [text_node("a.md", body)], {hash_bytes(body): body},
                        seal_report={"soul_paths_with_content": 1, "sealed_spans": 0,
                                     "sealed_nodes": 0})
    with pytest.raises(SealViolation) as exc:
        load_snapshot(root).verify()
    assert exc.value.detail["count"] == "soul_paths_with_content"


def test_span_over_a_sealed_node_refuses(tmp_path):
    body = b"ok"
    nodes = [text_node("a.md", body), sealed_node("soul/p.md")]
    span = Span(span_id=Span.compute_id(REFS_ONLY, 0, 2, "markdown/1", "seg/1"),
                node_id="soul/p.md", source_content_hash=REFS_ONLY, segmenter_id="markdown/1",
                seg_version="seg/1", start=0, end=2, est_tokens=1, is_leaf=True,
                parent_span=None, kind="md_block")
    root = write_bundle(tmp_path / "snap", nodes, {hash_bytes(body): body}, spans=[span])
    with pytest.raises(SealViolation) as exc:
        load_snapshot(root).verify()
    assert "sealed" in exc.value.message


# ---------------------------------------------------------------------------
# spans
# ---------------------------------------------------------------------------

def _leaf(node: SnapshotNode, start: int, end: int, parent: str | None = None) -> Span:
    return Span(span_id=Span.compute_id(node.content_hash, start, end, "markdown/1", "seg/1"),
                node_id=node.node_id, source_content_hash=node.content_hash,
                segmenter_id="markdown/1", seg_version="seg/1", start=start, end=end,
                est_tokens=max(1, (end - start) // 4), is_leaf=True, parent_span=parent,
                kind="md_block")


def test_span_coverage_hole_refuses(tmp_path):
    body = b"0123456789"
    node = text_node("a.md", body)
    spans = [_leaf(node, 0, 4), _leaf(node, 6, 10)]           # bytes 4..6 uncovered
    root = write_bundle(tmp_path / "snap", [node], {hash_bytes(body): body}, spans=spans)
    with pytest.raises(CoverageViolation):
        load_snapshot(root).verify()


def test_span_partition_that_stops_short_refuses(tmp_path):
    body = b"0123456789"
    node = text_node("a.md", body)
    spans = [_leaf(node, 0, 6)]
    root = write_bundle(tmp_path / "snap", [node], {hash_bytes(body): body}, spans=spans)
    with pytest.raises(CoverageViolation):
        load_snapshot(root).verify()


def test_parent_not_containing_child_refuses(tmp_path):
    body = b"0123456789"
    node = text_node("a.md", body)
    parent = Span(span_id=Span.compute_id(node.content_hash, 0, 4, "markdown/1", "seg/1"),
                  node_id=node.node_id, source_content_hash=node.content_hash,
                  segmenter_id="markdown/1", seg_version="seg/1", start=0, end=4, est_tokens=1,
                  is_leaf=False, parent_span=None, kind="md_section")
    child = _leaf(node, 0, 10, parent=parent.span_id)
    root = write_bundle(tmp_path / "snap", [node], {hash_bytes(body): body},
                        spans=[parent, child])
    with pytest.raises(NestingViolation):
        load_snapshot(root).verify()


def test_node_with_bytes_but_no_spans_refuses(tmp_path):
    """The omitted node. Walking the spans cannot see it; walking the nodes can."""
    one, two = b"0123456789", b"abcdefghij"
    a, b = text_node("a.md", one), text_node("b.md", two)
    root = write_bundle(tmp_path / "snap", [a, b],
                        {hash_bytes(one): one, hash_bytes(two): two},
                        spans=[_leaf(a, 0, 10)])          # b.md has bytes and no spans at all
    with pytest.raises(CoverageViolation) as exc:
        load_snapshot(root).verify()
    assert exc.value.detail["node_id"] == "b.md"


def test_sealed_and_empty_nodes_need_no_spans(tmp_path):
    """The converse: nodes with nothing to segment are not expected in the span file."""
    body = b"0123456789"
    node = text_node("a.md", body)
    empty = text_node("empty.md", b"")
    root = write_bundle(tmp_path / "snap", [node, empty, sealed_node("soul/p.md")],
                        {hash_bytes(body): body, hash_bytes(b""): b""},
                        spans=[_leaf(node, 0, 10)])
    assert load_snapshot(root).verify()["sealed_spans"] == 0


def test_good_spans_verify(tmp_path):
    body = b"0123456789"
    node = text_node("a.md", body)
    spans = [_leaf(node, 0, 4), _leaf(node, 4, 10)]
    root = write_bundle(tmp_path / "snap", [node], {hash_bytes(body): body}, spans=spans)
    assert load_snapshot(root).verify()["sealed_spans"] == 0


def test_export_lineage_is_retained_and_identity_checked(tmp_path):
    from atlas.ids import chash
    from atlas.errors import SnapshotIdMismatch
    root = write_bundle(tmp_path / "lineage", [], {})
    path = root / "manifest.json"
    raw = json.loads(path.read_text())
    raw.update(exporter_version="3", parent_snapshot="sha256:" + "a" * 64,
               diff_counts=dict(added=1, modified=2, deleted=3, seal_affected=0))
    raw["snapshot_id"] = chash({k: v for k, v in raw.items() if k not in ("snapshot_id", "created_ts")})
    path.write_text(json.dumps(raw))
    bundle = load_snapshot(root)
    bundle.verify()
    assert bundle.manifest.to_dict() == raw
    raw["diff_counts"]["deleted"] = 4
    path.write_text(json.dumps(raw))
    with pytest.raises(SnapshotIdMismatch):
        load_snapshot(root).verify()
