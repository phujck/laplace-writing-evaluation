"""schema.py - the Phase 1 record types: SnapshotNode, RecordSnapshot, Span, SegmentationGeneration.

Schemas are versioned, disposable projections over the immutable source, exactly like encoders
(DESIGN_2026-08-01_the-atlas.md §5). So every type carries its own ``SCHEMA_VERSION`` string and
every record serializes it; a reader that does not know a version REFUSES rather than guessing
which fields it can trust.

Two conventions the rest of the package depends on:

* ``to_dict`` emits every field, including the version. ``from_dict`` accepts exactly the
  fields it emits, refuses an unknown ``schema_version`` and refuses a missing required field.
  Round-tripping is therefore lossless, and a test pins that (``tests/test_schema.py``).
* ``hashed_dict`` drops the fields excluded from the record's identity: the id itself, and
  ``created_ts``. Wall-clock never enters an id (ids.py); the timestamp is kept beside the
  record as provenance, not as identity.

Only the Phase 1 subset lives here. NodeBundle, ResidualPacket, HierarchyNode, QueryPlan and
the edge ladder are §5 types that Phase 4+ lands; they are absent rather than stubbed, so
nothing imports an empty shape and pretends it is a contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .errors import SchemaFieldMissing, SchemaVersionMismatch
from .ids import chash

# A sealed node's content hash. Not a hash: the marker that no bytes were read, ever. It sits
# where a hash would sit so a reader cannot mistake absence for "not yet computed".
REFS_ONLY = "refs-only"

# A non-text asset (binary, archive, PDF) the exporter deliberately does not open, mirroring
# self_shard's name-only asset nodes. Distinct from REFS_ONLY: unsealed, merely unread.
NOT_READ = "not-read"

READ_POLICIES = ("text", "asset-not-read", "sealed-refs-only")


def _require(d: dict[str, Any], keys: tuple[str, ...], where: str) -> None:
    missing = [k for k in keys if k not in d]
    if missing:
        raise SchemaFieldMissing(f"{where} record is missing required fields", fields=missing)


def _check_version(d: dict[str, Any], expected: str, where: str) -> None:
    got = d.get("schema_version")
    if got != expected:
        raise SchemaVersionMismatch(
            f"{where} record carries a schema version this reader does not know",
            expected=expected, got=got,
        )


def _require_exact(d: dict[str, Any], keys: tuple[str, ...], where: str) -> None:
    expected = {"schema_version", *keys}
    missing = sorted(expected - set(d))
    extra = sorted(set(d) - expected)
    if missing or extra:
        raise SchemaFieldMissing(
            f"{where} fields do not match its schema", fields=missing, unexpected=extra
        )


# ---------------------------------------------------------------------------
# SnapshotNode - one repo object as it enters an immutable bundle
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SnapshotNode:
    """One node of the snapshot universe: a repo-relative path plus how its bytes were handled.

    ``node_id`` is the repo-relative path. Paths are stable identities inside one snapshot; a
    rename is a different node in a later snapshot, and the pair of snapshots is where that
    change is read (the freshness law, design §11 J10).

    Three mutually exclusive read policies, each visible in the record:
      ``sealed-refs-only``  - under a sealed prefix; bytes never read; ``content_hash`` is
                              REFS_ONLY and ``content_blob`` is None.
      ``asset-not-read``    - not a text extension; bytes never read; ``content_hash`` is
                              NOT_READ. ``size_bytes`` comes from stat, not from a read.
      ``text``              - bytes read, hashed, stored as a blob keyed by that hash.
    """

    SCHEMA_VERSION = "snapshot-node/1"

    node_id: str
    path: str
    kind: str
    sealed: bool
    is_text: bool
    read_policy: str
    content_hash: str
    content_blob: str | None
    size_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "node_id": self.node_id,
            "path": self.path,
            "kind": self.kind,
            "sealed": self.sealed,
            "is_text": self.is_text,
            "read_policy": self.read_policy,
            "content_hash": self.content_hash,
            "content_blob": self.content_blob,
            "size_bytes": self.size_bytes,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SnapshotNode":
        _check_version(d, cls.SCHEMA_VERSION, "SnapshotNode")
        _require(d, ("node_id", "path", "kind", "sealed", "is_text", "read_policy",
                     "content_hash", "content_blob", "size_bytes"), "SnapshotNode")
        return cls(
            node_id=d["node_id"], path=d["path"], kind=d["kind"], sealed=bool(d["sealed"]),
            is_text=bool(d["is_text"]), read_policy=d["read_policy"],
            content_hash=d["content_hash"], content_blob=d["content_blob"],
            size_bytes=int(d["size_bytes"]),
        )


# ---------------------------------------------------------------------------
# RecordSnapshot - the bundle manifest
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RecordSnapshot:
    """The manifest of one immutable bundle: what was captured, from where, and its own id.

    ``snapshot_id`` is ``chash`` over this record minus ``snapshot_id`` and ``created_ts`` - the
    identity is the content, not the moment of capture. ``nodes_sha256`` and
    ``seal_report_sha256`` fold the sidecar files into that identity, so a bundle whose
    nodes.jsonl was edited after export fails ``snapshot.verify`` on the id, not merely on a
    row.

    ``spans.jsonl`` is deliberately NOT folded in: segmentation is atlas-side work written after
    export by ``python -m atlas.tools.build_spans``, and its identity lives in the
    SegmentationGeneration record beside the bundle. The manifest is never mutated to record it.
    """

    SCHEMA_VERSION = "record-snapshot/1"

    snapshot_id: str
    created_ts: str
    atlas_schema_version: str
    exporter_version: str
    source_repo: str
    commit_sha: str
    node_count: int
    text_node_count: int
    sealed_node_count: int
    asset_node_count: int
    total_content_bytes: int
    nodes_sha256: str
    seal_report_sha256: str
    sealed_prefixes: list[str]
    sealed_paths: list[str]
    excluded_prefixes: list[str]
    text_extensions: list[str]
    node_limit: int | None
    tree_dirty: bool
    dirty_node_count: int
    dirty_nodes_hash: str
    # Optional dataset extent; omitted for legacy snapshots to preserve their identities.
    manifest_handle: str | None = None
    pinned_commit: str | None = None
    sources: list[str] | None = None

    #: Fields excluded from ``snapshot_id``. The id and the clock, nothing else.
    HASH_EXCLUDED = ("snapshot_id", "created_ts")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "snapshot_id": self.snapshot_id,
            "created_ts": self.created_ts,
            "atlas_schema_version": self.atlas_schema_version,
            "exporter_version": self.exporter_version,
            "source_repo": self.source_repo,
            "commit_sha": self.commit_sha,
            "node_count": self.node_count,
            "text_node_count": self.text_node_count,
            "sealed_node_count": self.sealed_node_count,
            "asset_node_count": self.asset_node_count,
            "total_content_bytes": self.total_content_bytes,
            "nodes_sha256": self.nodes_sha256,
            "seal_report_sha256": self.seal_report_sha256,
            "sealed_prefixes": list(self.sealed_prefixes),
            "sealed_paths": list(self.sealed_paths),
            "excluded_prefixes": list(self.excluded_prefixes),
            "text_extensions": list(self.text_extensions),
            "node_limit": self.node_limit,
            "tree_dirty": self.tree_dirty,
            "dirty_node_count": self.dirty_node_count,
            "dirty_nodes_hash": self.dirty_nodes_hash,
            **({"manifest_handle": self.manifest_handle,
                "pinned_commit": self.pinned_commit, "sources": self.sources}
               if self.manifest_handle is not None else {}),
        }

    def hashed_dict(self) -> dict[str, Any]:
        d = self.to_dict()
        for k in self.HASH_EXCLUDED:
            d.pop(k, None)
        return d

    def computed_id(self) -> str:
        return chash(self.hashed_dict())

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RecordSnapshot":
        _check_version(d, cls.SCHEMA_VERSION, "RecordSnapshot")
        _require(d, ("snapshot_id", "created_ts", "atlas_schema_version", "exporter_version",
                     "source_repo", "commit_sha", "node_count", "text_node_count",
                     "sealed_node_count", "asset_node_count", "total_content_bytes",
                     "nodes_sha256", "seal_report_sha256", "sealed_prefixes", "sealed_paths",
                     "excluded_prefixes", "text_extensions", "node_limit", "tree_dirty",
                     "dirty_node_count", "dirty_nodes_hash"), "RecordSnapshot")
        return cls(
            snapshot_id=d["snapshot_id"], created_ts=d["created_ts"],
            atlas_schema_version=d["atlas_schema_version"],
            exporter_version=d["exporter_version"], source_repo=d["source_repo"],
            commit_sha=d["commit_sha"], node_count=int(d["node_count"]),
            text_node_count=int(d["text_node_count"]),
            sealed_node_count=int(d["sealed_node_count"]),
            asset_node_count=int(d["asset_node_count"]),
            total_content_bytes=int(d["total_content_bytes"]),
            nodes_sha256=d["nodes_sha256"], seal_report_sha256=d["seal_report_sha256"],
            sealed_prefixes=list(d["sealed_prefixes"]),
            sealed_paths=list(d["sealed_paths"]),
            excluded_prefixes=list(d["excluded_prefixes"]),
            text_extensions=list(d["text_extensions"]),
            node_limit=d["node_limit"], tree_dirty=bool(d["tree_dirty"]),
            dirty_node_count=int(d["dirty_node_count"]),
            dirty_nodes_hash=d["dirty_nodes_hash"],
            manifest_handle=d.get("manifest_handle"), pinned_commit=d.get("pinned_commit"),
            sources=list(d["sources"]) if d.get("sources") is not None else None,
        )


# ---------------------------------------------------------------------------
# Span - the unit of retrieval
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Span:
    """A byte range of one immutable source, with the structural trail that produced it.

    ``span_id = chash(source_content_hash, start, end, segmenter_id, seg_version)`` exactly as
    design §5 fixes it. The target span size is NOT in the id on purpose: the same byte range
    cut by the same recipe is the same span whichever sweep produced it, so a sweep re-uses
    identities instead of minting parallel ones.

    Spans nest; LEAF spans partition. ``is_leaf`` marks the partition layer, and the coverage
    law binds leaves only - a parent span (a heading section over its subsections, a JSON object
    over its members) covers the same bytes again by design.

    ``est_tokens`` is bytes/4 rounded up - the repo's canonical estimate
    (``src/laplace/storyboard.py:1131``: "rough: chars/4 = input tokens"), rounded up so a
    nonempty span never estimates zero.

    ``meta`` carries what the type cannot: the key inventory of a JSON object, the reason a span
    is oversize, the overlap context offset of a fallback window.
    """

    SCHEMA_VERSION = "span/1"

    span_id: str
    node_id: str
    source_content_hash: str
    segmenter_id: str
    seg_version: str
    start: int
    end: int
    est_tokens: int
    is_leaf: bool
    parent_span: str | None
    kind: str
    trail: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def compute_id(source_content_hash: str, start: int, end: int,
                   segmenter_id: str, seg_version: str) -> str:
        return chash({
            "source_content_hash": source_content_hash,
            "start": start,
            "end": end,
            "segmenter_id": segmenter_id,
            "seg_version": seg_version,
        })

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "span_id": self.span_id,
            "node_id": self.node_id,
            "source_content_hash": self.source_content_hash,
            "segmenter_id": self.segmenter_id,
            "seg_version": self.seg_version,
            "start": self.start,
            "end": self.end,
            "est_tokens": self.est_tokens,
            "is_leaf": self.is_leaf,
            "parent_span": self.parent_span,
            "kind": self.kind,
            "trail": list(self.trail),
            "meta": dict(self.meta),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Span":
        _check_version(d, cls.SCHEMA_VERSION, "Span")
        _require(d, ("span_id", "node_id", "source_content_hash", "segmenter_id", "seg_version",
                     "start", "end", "est_tokens", "is_leaf", "parent_span", "kind", "trail",
                     "meta"), "Span")
        return cls(
            span_id=d["span_id"], node_id=d["node_id"],
            source_content_hash=d["source_content_hash"], segmenter_id=d["segmenter_id"],
            seg_version=d["seg_version"], start=int(d["start"]), end=int(d["end"]),
            est_tokens=int(d["est_tokens"]), is_leaf=bool(d["is_leaf"]),
            parent_span=d["parent_span"], kind=d["kind"], trail=list(d["trail"]),
            meta=dict(d["meta"]),
        )


# ---------------------------------------------------------------------------
# SemanticAtom - one exact, individually reachable content observation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SemanticAtom:
    """Exact UTF-8 content carried by one verified leaf span.

    The source bytes remain authoritative. ``content_utf8`` is accepted only when it round-trips
    byte-exactly and ``content_handle`` is the hash of those bytes.  Governance identity is an
    optional address into structured JSONL; it never replaces the atom/span address.
    """

    SCHEMA_VERSION = "semantic-atom/1"

    atom_id: str
    snapshot_id: str
    generation_id: str
    node_id: str
    path: str
    span_id: str
    start: int
    end: int
    source_content_hash: str
    content_handle: str
    content_utf8: str
    kind: str
    trail: tuple[str, ...]
    meta: dict[str, Any]
    governance_ref: dict[str, str] | None

    HASH_EXCLUDED = ("atom_id",)

    def __post_init__(self) -> None:
        string_fields = (
            self.snapshot_id, self.generation_id, self.node_id, self.path, self.span_id,
            self.source_content_hash, self.content_handle, self.kind,
        )
        if not all(type(value) is str and value for value in string_fields):
            raise SchemaFieldMissing("SemanticAtom string field is empty or not a string")
        if type(self.atom_id) is not str or type(self.content_utf8) is not str:
            raise SchemaFieldMissing("SemanticAtom identity/content type is invalid")
        if type(self.start) is not int or type(self.end) is not int or self.start < 0 or self.end <= self.start:
            raise SchemaFieldMissing("SemanticAtom byte range is invalid")
        if type(self.trail) is not tuple or not all(type(item) is str for item in self.trail):
            raise SchemaFieldMissing("SemanticAtom trail is invalid")
        if type(self.meta) is not dict:
            raise SchemaFieldMissing("SemanticAtom metadata is invalid")
        if self.governance_ref is not None:
            if type(self.governance_ref) is not dict or set(self.governance_ref) != {"record", "id"}:
                raise SchemaFieldMissing("SemanticAtom governance reference is invalid")
            if not all(type(value) is str and value for value in self.governance_ref.values()):
                raise SchemaFieldMissing("SemanticAtom governance reference is empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "atom_id": self.atom_id,
            "snapshot_id": self.snapshot_id,
            "generation_id": self.generation_id,
            "node_id": self.node_id,
            "path": self.path,
            "span_id": self.span_id,
            "start": self.start,
            "end": self.end,
            "source_content_hash": self.source_content_hash,
            "content_handle": self.content_handle,
            "content_utf8": self.content_utf8,
            "kind": self.kind,
            "trail": list(self.trail),
            "meta": dict(self.meta),
            "governance_ref": None if self.governance_ref is None else dict(self.governance_ref),
        }

    def hashed_dict(self) -> dict[str, Any]:
        body = self.to_dict()
        body.pop("atom_id")
        return body

    def computed_id(self) -> str:
        return chash(self.hashed_dict())

    @classmethod
    def create(cls, **fields: Any) -> "SemanticAtom":
        preimage = {
            "schema_version": cls.SCHEMA_VERSION,
            "snapshot_id": fields["snapshot_id"],
            "generation_id": fields["generation_id"],
            "node_id": fields["node_id"],
            "path": fields["path"],
            "span_id": fields["span_id"],
            "start": fields["start"],
            "end": fields["end"],
            "source_content_hash": fields["source_content_hash"],
            "content_handle": fields["content_handle"],
            "content_utf8": fields["content_utf8"],
            "kind": fields["kind"],
            "trail": list(fields["trail"]),
            "meta": dict(fields["meta"]),
            "governance_ref": (
                None if fields["governance_ref"] is None
                else dict(fields["governance_ref"])
            ),
        }
        return cls(atom_id=chash(preimage), **fields)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SemanticAtom":
        keys = (
            "atom_id", "snapshot_id", "generation_id", "node_id", "path", "span_id",
            "start", "end", "source_content_hash", "content_handle", "content_utf8", "kind",
            "trail", "meta", "governance_ref",
        )
        _check_version(d, cls.SCHEMA_VERSION, "SemanticAtom")
        _require_exact(d, keys, "SemanticAtom")
        if type(d["start"]) is not int or type(d["end"]) is not int:
            raise SchemaFieldMissing("SemanticAtom byte offsets must be exact integers")
        if type(d["trail"]) is not list or type(d["meta"]) is not dict:
            raise SchemaFieldMissing("SemanticAtom collection field type is invalid")
        item = cls(
            atom_id=d["atom_id"], snapshot_id=d["snapshot_id"],
            generation_id=d["generation_id"], node_id=d["node_id"], path=d["path"],
            span_id=d["span_id"], start=d["start"], end=d["end"],
            source_content_hash=d["source_content_hash"], content_handle=d["content_handle"],
            content_utf8=d["content_utf8"], kind=d["kind"], trail=tuple(d["trail"]),
            meta=dict(d["meta"]),
            governance_ref=(None if d["governance_ref"] is None else dict(d["governance_ref"])),
        )
        if item.atom_id != item.computed_id():
            raise SchemaFieldMissing("SemanticAtom id is not the hash of its exact fields")
        return item


# ---------------------------------------------------------------------------
# SegmentationGeneration - one run of the segmentation layer over one snapshot
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SegmentationGeneration:
    """The identity and the measured laws of one segmentation of one snapshot.

    ``generation_id`` folds the snapshot, the recipe version, the size dials and the sha256 of
    the spans file - so two runs producing byte-identical spans produce the same id, and a run
    that changed one cut cannot claim the old id. ``created_ts`` is recorded and excluded from
    the hash.

    The three laws are measured into this record, not asserted in prose: ``coverage`` (1.0 or
    the run refused), ``oversize_spans`` with ``oversize_detail`` naming each one, and
    ``structure_violations`` which is zero or the run refused.
    """

    SCHEMA_VERSION = "segmentation-generation/1"

    generation_id: str
    created_ts: str
    snapshot_id: str
    segmentation_recipe_version: str
    target_tokens: int
    hard_cap_tokens: int
    spans_sha256: str
    span_count: int
    leaf_span_count: int
    parent_span_count: int
    segmented_node_count: int
    skipped_node_count: int
    covered_bytes: int
    total_bytes: int
    coverage: float
    oversize_spans: int
    oversize_detail: list[dict[str, Any]]
    structure_violations: int
    sealed_spans: int
    segmenter_ids: list[str]
    miss_events: list[dict[str, Any]]

    HASH_EXCLUDED = ("generation_id", "created_ts")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "generation_id": self.generation_id,
            "created_ts": self.created_ts,
            "snapshot_id": self.snapshot_id,
            "segmentation_recipe_version": self.segmentation_recipe_version,
            "target_tokens": self.target_tokens,
            "hard_cap_tokens": self.hard_cap_tokens,
            "spans_sha256": self.spans_sha256,
            "span_count": self.span_count,
            "leaf_span_count": self.leaf_span_count,
            "parent_span_count": self.parent_span_count,
            "segmented_node_count": self.segmented_node_count,
            "skipped_node_count": self.skipped_node_count,
            "covered_bytes": self.covered_bytes,
            "total_bytes": self.total_bytes,
            "coverage": self.coverage,
            "oversize_spans": self.oversize_spans,
            "oversize_detail": list(self.oversize_detail),
            "structure_violations": self.structure_violations,
            "sealed_spans": self.sealed_spans,
            "segmenter_ids": list(self.segmenter_ids),
            "miss_events": list(self.miss_events),
        }

    def hashed_dict(self) -> dict[str, Any]:
        d = self.to_dict()
        for k in self.HASH_EXCLUDED:
            d.pop(k, None)
        return d

    def computed_id(self) -> str:
        return chash(self.hashed_dict())

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SegmentationGeneration":
        _check_version(d, cls.SCHEMA_VERSION, "SegmentationGeneration")
        _require(d, ("generation_id", "created_ts", "snapshot_id",
                     "segmentation_recipe_version", "target_tokens", "hard_cap_tokens",
                     "spans_sha256", "span_count", "leaf_span_count", "parent_span_count",
                     "segmented_node_count", "skipped_node_count", "covered_bytes",
                     "total_bytes", "coverage", "oversize_spans", "oversize_detail",
                     "structure_violations", "sealed_spans", "segmenter_ids", "miss_events"),
                 "SegmentationGeneration")
        return cls(
            generation_id=d["generation_id"], created_ts=d["created_ts"],
            snapshot_id=d["snapshot_id"],
            segmentation_recipe_version=d["segmentation_recipe_version"],
            target_tokens=int(d["target_tokens"]), hard_cap_tokens=int(d["hard_cap_tokens"]),
            spans_sha256=d["spans_sha256"], span_count=int(d["span_count"]),
            leaf_span_count=int(d["leaf_span_count"]),
            parent_span_count=int(d["parent_span_count"]),
            segmented_node_count=int(d["segmented_node_count"]),
            skipped_node_count=int(d["skipped_node_count"]),
            covered_bytes=int(d["covered_bytes"]), total_bytes=int(d["total_bytes"]),
            coverage=float(d["coverage"]), oversize_spans=int(d["oversize_spans"]),
            oversize_detail=list(d["oversize_detail"]),
            structure_violations=int(d["structure_violations"]),
            sealed_spans=int(d["sealed_spans"]), segmenter_ids=list(d["segmenter_ids"]),
            miss_events=list(d["miss_events"]),
        )
