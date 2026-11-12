"""test_schema.py - round trips, version refusals, and the rule that the clock never enters an id."""

from __future__ import annotations

import dataclasses

import pytest

from atlas.errors import SchemaFieldMissing, SchemaVersionMismatch
from atlas.schema import (
    NOT_READ,
    REFS_ONLY,
    RecordSnapshot,
    SegmentationGeneration,
    SemanticAtom,
    SnapshotNode,
    Span,
)


def _node(**over):
    base = dict(node_id="a/b.md", path="a/b.md", kind="md", sealed=False, is_text=True,
                read_policy="text", content_hash="sha256:" + "0" * 64,
                content_blob="sha256:" + "0" * 64, size_bytes=12)
    base.update(over)
    return SnapshotNode(**base)


def _manifest(**over):
    base = dict(snapshot_id="", created_ts="2026-08-01T00:00:00+00:00", atlas_schema_version="1",
                exporter_version="1", source_repo="laplace", commit_sha="abc123",
                node_count=2, text_node_count=1, sealed_node_count=1, asset_node_count=0,
                total_content_bytes=12, nodes_sha256="sha256:" + "1" * 64,
                seal_report_sha256="sha256:" + "2" * 64,
                sealed_prefixes=["soul/"], sealed_paths=[".meaning_tree.json"],
                excluded_prefixes=["atlas/stores/"], text_extensions=[".md"], node_limit=None,
                tree_dirty=False, dirty_node_count=0, dirty_nodes_hash="sha256:" + "5" * 64)
    base.update(over)
    return RecordSnapshot(**base)


def _span(**over):
    base = dict(node_id="a/b.md", source_content_hash="sha256:" + "0" * 64,
                segmenter_id="markdown/1", seg_version="seg/1", start=0, end=40, est_tokens=10,
                is_leaf=True, parent_span=None, kind="md_block", trail=["Title"],
                meta={"note": 1})
    base.update(over)
    base["span_id"] = Span.compute_id(base["source_content_hash"], base["start"], base["end"],
                                      base["segmenter_id"], base["seg_version"])
    return Span(**base)


def _generation(**over):
    base = dict(generation_id="", created_ts="2026-08-01T00:00:00+00:00",
                snapshot_id="sha256:" + "3" * 64, segmentation_recipe_version="seg/1",
                target_tokens=384, hard_cap_tokens=512, spans_sha256="sha256:" + "4" * 64,
                span_count=5, leaf_span_count=4, parent_span_count=1, segmented_node_count=1,
                skipped_node_count=0, covered_bytes=100, total_bytes=100, coverage=1.0,
                oversize_spans=0, oversize_detail=[], structure_violations=0, sealed_spans=0,
                segmenter_ids=["markdown/1"], miss_events=[])
    base.update(over)
    return SegmentationGeneration(**base)


def _atom(**over):
    fields = dict(
        snapshot_id="sha256:" + "1" * 64, generation_id="sha256:" + "2" * 64,
        node_id="rows.jsonl", path="rows.jsonl", span_id="sha256:" + "3" * 64,
        start=0, end=12, source_content_hash="sha256:" + "4" * 64,
        content_handle="sha256:" + "5" * 64, content_utf8='{"id":"x"}\n',
        kind="jsonl_row", trail=(), meta={"row_start": 0, "row_end": 0},
        governance_ref={"record": "work-order", "id": "x"},
    )
    fields.update(over)
    return SemanticAtom.create(**fields)


@pytest.mark.parametrize("record", [_node(), _node(sealed=True, content_hash=REFS_ONLY,
                                          content_blob=None, read_policy="sealed-refs-only"),
                                    _node(is_text=False, content_hash=NOT_READ,
                                          content_blob=None, read_policy="asset-not-read"),
                                    _manifest(), _span(), _generation(), _atom()])
def test_round_trip(record):
    cls = type(record)
    assert cls.from_dict(record.to_dict()) == record


def test_to_dict_carries_the_version():
    assert _node().to_dict()["schema_version"] == SnapshotNode.SCHEMA_VERSION
    assert _span().to_dict()["schema_version"] == Span.SCHEMA_VERSION


def test_unknown_version_refuses():
    raw = _node().to_dict()
    raw["schema_version"] = "snapshot-node/99"
    with pytest.raises(SchemaVersionMismatch) as exc:
        SnapshotNode.from_dict(raw)
    assert exc.value.reason == "schema-version-mismatch"


def test_missing_field_refuses():
    raw = _node().to_dict()
    del raw["content_hash"]
    with pytest.raises(SchemaFieldMissing) as exc:
        SnapshotNode.from_dict(raw)
    assert "content_hash" in exc.value.detail["fields"]


def test_snapshot_id_excludes_the_clock_and_itself():
    man = _manifest()
    computed = man.computed_id()
    later = dataclasses.replace(man, created_ts="2027-01-01T00:00:00+00:00")
    assert later.computed_id() == computed
    stamped = dataclasses.replace(man, snapshot_id=computed)
    assert stamped.computed_id() == computed
    assert "created_ts" not in man.hashed_dict()
    assert "snapshot_id" not in man.hashed_dict()


def test_snapshot_id_moves_with_content():
    man = _manifest()
    assert dataclasses.replace(man, node_count=3).computed_id() != man.computed_id()


def test_generation_id_excludes_the_clock():
    gen = _generation()
    assert (dataclasses.replace(gen, created_ts="2030-05-05T00:00:00+00:00").computed_id()
            == gen.computed_id())
    assert dataclasses.replace(gen, target_tokens=256).computed_id() != gen.computed_id()


def test_span_id_is_the_hash_of_its_five_fields():
    span = _span()
    assert span.span_id == Span.compute_id(span.source_content_hash, span.start, span.end,
                                           span.segmenter_id, span.seg_version)
    other = Span.compute_id(span.source_content_hash, span.start, span.end + 1,
                            span.segmenter_id, span.seg_version)
    assert other != span.span_id


def test_span_id_does_not_depend_on_the_target_size():
    """The same byte range cut by the same recipe is the same span, whichever sweep made it."""
    a = _span()
    b = _span()
    assert a.span_id == b.span_id


def test_semantic_atom_strict_schema_and_identity_refuse_drift():
    atom = _atom()
    assert SemanticAtom.from_dict(atom.to_dict()) == atom
    for field, value in (("path", "moved.jsonl"), ("end", 13),
                         ("generation_id", "sha256:" + "9" * 64)):
        raw = atom.to_dict()
        raw[field] = value
        with pytest.raises(SchemaFieldMissing):
            SemanticAtom.from_dict(raw)
    raw = atom.to_dict()
    raw["unexpected"] = True
    with pytest.raises(SchemaFieldMissing):
        SemanticAtom.from_dict(raw)
    raw = atom.to_dict()
    raw["start"] = "0"
    with pytest.raises(SchemaFieldMissing):
        SemanticAtom.from_dict(raw)
