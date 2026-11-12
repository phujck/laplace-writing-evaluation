"""snapshot.py - loading, verifying and iterating a RecordSnapshot bundle.

A bundle is five things on disk:

    manifest.json      the RecordSnapshot record (schema.py)
    nodes.jsonl        one SnapshotNode per row, in node_id order
    blobs/             content-addressed source bytes (store.BlobStore)
    seal_report.json   the two counts the soul seal is measured by
    spans.jsonl        optional, written later by atlas.tools.build_spans

``verify`` is the whole point of this module. Bundles TRAVEL - into benchmarks, into
comparators, eventually out of this repository - so the seal is enforced on read as well as on
write, and the read side does not trust the bundle's own declarations. The sealed prefixes
checked here are the constants below, not ``manifest.sealed_prefixes``: a bundle that shipped
an empty prefix list would otherwise verify its own leak clean.

Every refusal is named (errors.py). ``verify`` collects nothing and returns nothing on success;
it raises on the first violation with the node or span that caused it in the detail mapping.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import (
    BlobMissing,
    ContentHashMismatch,
    CoverageViolation,
    NestingViolation,
    SealedRead,
    SealViolation,
    SnapshotIdMismatch,
    SnapshotIncomplete,
    SnapshotRegenerationRefused,
    StoreError,
)
from .ids import hash_bytes
from .schema import NOT_READ, REFS_ONLY, RecordSnapshot, SnapshotNode, Span
from .store import BlobStore, read_jsonl, sha256_file

# The refs-only floor, hard-coded on the read side. Mirrors self_shard._SEALED_PREFIXES on the
# laplace side by AGREEMENT, not by import - the seal carries no code. If the engine ever adds a
# sealed zone, this tuple is the second site that must move, and a bundle exported with a wider
# engine-side list still verifies (its extra nodes simply arrive sealed).
SOUL_PREFIXES = ("soul/", "soul_corpus/sealed/")

MANIFEST_NAME = "manifest.json"
NODES_NAME = "nodes.jsonl"
SPANS_NAME = "spans.jsonl"
SEAL_REPORT_NAME = "seal_report.json"
SEGMENTATION_NAME = "segmentation.json"
BLOBS_DIR = "blobs"


def is_soul_path(path: str) -> bool:
    """True for a path inside a sealed zone. Content of these never enters a bundle."""
    return path.startswith(SOUL_PREFIXES)


@dataclass(frozen=True)
class ExportSnapshot(RecordSnapshot):
    """Exporter v3 provenance retained by the bundle reader, including in its identity.

    The base record remains the legacy schema. This extension is local to the snapshot
    transport so legacy records keep their exact identities and other schema users do not
    need to learn exporter ancestry.
    """

    parent_snapshot: str | None = None
    diff_counts: dict[str, int] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {**super().to_dict(), "parent_snapshot": self.parent_snapshot,
                "diff_counts": self.diff_counts}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ExportSnapshot":
        base = RecordSnapshot.from_dict(raw)
        parent = raw.get("parent_snapshot")
        counts = raw.get("diff_counts")
        if ("parent_snapshot" not in raw or (parent is not None and
                (not isinstance(parent, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", parent)))
                or not isinstance(counts, dict)
                or set(counts) != {"added", "modified", "deleted", "seal_affected"}
                or any(type(n) is not int or n < 0 for n in counts.values())):
            raise SnapshotIncomplete("invalid incremental export provenance")
        return cls(**vars(base), parent_snapshot=parent, diff_counts=dict(counts))


class SnapshotBundle:
    """One bundle on disk. Construction reads only the manifest; rows stream on demand."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.manifest_path = self.root / MANIFEST_NAME
        self.nodes_path = self.root / NODES_NAME
        self.spans_path = self.root / SPANS_NAME
        self.seal_report_path = self.root / SEAL_REPORT_NAME
        self.blobs = BlobStore(self.root / BLOBS_DIR)
        self._manifest: RecordSnapshot | None = None
        self._nodes: dict[str, SnapshotNode] | None = None
        self._spans: dict[str, Span] | None = None
        self._node_bytes: dict[str, bytes] = {}
        self.cache_refusals: dict[str, str] = {}

    # --- loading ----------------------------------------------------------

    @property
    def manifest(self) -> RecordSnapshot:
        if self._manifest is None:
            if not self.manifest_path.is_file():
                raise SnapshotIncomplete("bundle has no manifest", path=str(self.manifest_path))
            try:
                raw = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise SnapshotIncomplete(
                    "manifest unreadable", path=str(self.manifest_path), error=str(exc)
                ) from exc
            self._manifest = (ExportSnapshot.from_dict(raw)
                              if raw.get("exporter_version") == "3"
                              else RecordSnapshot.from_dict(raw))
        return self._manifest

    @property
    def seal_report(self) -> dict[str, Any]:
        if not self.seal_report_path.is_file():
            raise SnapshotIncomplete("bundle has no seal report", path=str(self.seal_report_path))
        try:
            return json.loads(self.seal_report_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise SnapshotIncomplete(
                "seal report unreadable", path=str(self.seal_report_path), error=str(exc)
            ) from exc

    def iter_nodes(self) -> Iterator[SnapshotNode]:
        if not self.nodes_path.is_file():
            raise SnapshotIncomplete("bundle has no nodes file", path=str(self.nodes_path))
        for row in read_jsonl(self.nodes_path):
            yield SnapshotNode.from_dict(row)

    @property
    def nodes(self) -> dict[str, SnapshotNode]:
        """All nodes by id, materialized once. ~12.5k rows at repo scale - cheap to hold."""
        if self._nodes is None:
            self._nodes = {n.node_id: n for n in self.iter_nodes()}
        return self._nodes

    def has_spans(self) -> bool:
        return self.spans_path.is_file()

    def iter_spans(self) -> Iterator[Span]:
        if not self.spans_path.is_file():
            raise SnapshotIncomplete(
                "bundle has no spans file - run atlas.tools.build_spans first",
                path=str(self.spans_path),
            )
        for row in read_jsonl(self.spans_path):
            yield Span.from_dict(row)

    @property
    def spans(self) -> dict[str, Span]:
        """All spans by exact id, materialized once; duplicate identities refuse."""
        if self._spans is None:
            indexed: dict[str, Span] = {}
            for span in self.iter_spans():
                if span.span_id in indexed:
                    raise SnapshotIncomplete("bundle carries duplicate span identity", span_id=span.span_id)
                indexed[span.span_id] = span
            self._spans = indexed
        return self._spans

    def segmentation(self) -> dict[str, Any] | None:
        p = self.root / SEGMENTATION_NAME
        if not p.is_file():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise SnapshotIncomplete(
                "segmentation record unreadable", path=str(p), error=str(exc)
            ) from exc

    # --- reading ----------------------------------------------------------

    def read_node_bytes(self, node_id: str) -> bytes:
        """The immutable source bytes of one node. Sealed and unread nodes REFUSE, by name."""
        if node_id in self._node_bytes:
            return self._node_bytes[node_id]
        node = self.nodes.get(node_id)
        if node is None:
            raise SnapshotIncomplete("no such node in bundle", node_id=node_id)
        if node.sealed or is_soul_path(node.path) or node.content_hash == REFS_ONLY:
            raise SealedRead("sealed node has no content in a bundle, by construction",
                             node_id=node_id)
        if node.content_blob is None:
            raise SealedRead("node was not read at export", node_id=node_id,
                             read_policy=node.read_policy)
        if node.content_blob != node.content_hash:
            raise ContentHashMismatch("blob key and content hash disagree", node_id=node_id)
        try:
            data = self.blobs.get(node.content_blob)
        except BlobMissing:
            data = self._regenerate(node)
        if hash_bytes(data) != node.content_hash:
            raise ContentHashMismatch("node bytes disagree with content_hash", node_id=node_id)
        self._node_bytes[node_id] = data
        return data

    def _regenerate(self, node: SnapshotNode) -> bytes:
        """Recover only pinned Git bytes, never the mutable worktree or a remote."""
        man = self.manifest
        detail = dict(door="SnapshotBundle.read_node_bytes", node_id=node.node_id,
                      commit_sha=man.commit_sha, source_repo=man.source_repo)
        if man.tree_dirty is not False:
            raise SnapshotRegenerationRefused(
                "dirty snapshot is not exactly regenerable; restore its original blobs or export a clean snapshot",
                cause="dirty-tree", **detail)
        if not re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", man.commit_sha):
            raise SnapshotRegenerationRefused("restore a manifest with a full pinned commit id",
                                              cause="invalid-commit", **detail)
        if man.pinned_commit is not None and man.pinned_commit != man.commit_sha:
            raise SnapshotRegenerationRefused("dataset pin differs from snapshot commit",
                                              cause="pin-mismatch", **detail)
        path = Path(node.path)
        if path.is_absolute() or ".." in path.parts or node.path.startswith(":"):
            raise SnapshotRegenerationRefused("restore a repository-relative source path",
                                              cause="invalid-path", **detail)
        # Exporter v2 spells source_repo as 'laplace'. Resolve that logical name against
        # ancestors of the bundle/package/cwd; explicit local repository paths also travel.
        source = Path(man.source_repo)
        candidates = [source] if source.is_absolute() else []
        for base in (self.root.resolve(), Path(__file__).resolve().parent, Path.cwd()):
            for parent in (base, *base.parents):
                if not (parent / ".git").exists():
                    continue
                if man.source_repo == "." or parent.name == man.source_repo:
                    candidates.append(parent)
                elif man.manifest_handle is not None and man.source_repo not in ("", ".."):
                    # Legacy dataset bundles used the dataset id as source_repo. Resolve it
                    # only through the matching content-addressed registration, never a guess.
                    from .ids import chash
                    for registration in (parent / "atlas/datasets").glob("*.json"):
                        try:
                            raw = json.loads(registration.read_bytes())
                            core = raw["core"]
                            if (raw["manifest_handle"] == man.manifest_handle
                                    and chash({"schema_version": raw["schema_version"], "core": core}) == man.manifest_handle
                                    and core["dataset_id"] == man.source_repo
                                    and core["pinned_commit"] == man.pinned_commit
                                    and core.get("source_repo", ".") == "."):
                                candidates.append(parent)
                                break
                        except (OSError, ValueError, KeyError, TypeError):
                            continue
        failures = []
        for repo in dict.fromkeys(candidates):
            try:
                result = subprocess.run(
                    ["git", "-C", str(repo), "show", f"{man.commit_sha}:{node.path}"],
                    capture_output=True, timeout=30, check=False,
                    env={**os.environ, "GIT_NO_LAZY_FETCH": "1"},
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                failures.append(type(exc).__name__)
                continue
            if result.returncode:
                failures.append(result.stderr.decode("utf-8", errors="replace")[:300])
                continue
            data = result.stdout
            actual = hash_bytes(data)
            if actual != node.content_hash:
                raise ContentHashMismatch("regenerated Git bytes disagree with content_hash",
                                          actual=actual, declared=node.content_hash, **detail)
            try:
                self.blobs.put(data)
            except (StoreError, OSError) as exc:
                # A read-only cold reader can still receive verified bytes. Expose the
                # disk-cache omission; the in-process cache remains available.
                self.cache_refusals[node.node_id] = str(exc)
            return data
        raise SnapshotRegenerationRefused(
            "source Git or pinned path is unreachable; restore original blobs or make source_repo's pinned Git reachable",
            cause="git-unreachable", attempts=failures, **detail)

    def read_span(self, span_id: str) -> Span:
        span = self.spans.get(span_id)
        if span is None:
            raise SnapshotIncomplete("no such span in bundle", span_id=span_id)
        return span

    def read_span_bytes(self, span_id: str) -> bytes:
        """Return one exact verified source slice; never normalize or reserialize it."""
        return self.read_carried_span_bytes(self.read_span(span_id))

    def read_carried_span_bytes(self, span: Span) -> bytes:
        """Read a carried span without constructing the optional all-span lookup index."""
        node = self.nodes.get(span.node_id)
        if node is None:
            raise SnapshotIncomplete(
                "span source node is absent", span_id=span.span_id, node_id=span.node_id
            )
        if node.sealed or node.content_hash == REFS_ONLY:
            raise SealedRead("sealed node span cannot carry content", span_id=span.span_id)
        if node.content_hash != span.source_content_hash:
            raise ContentHashMismatch(
                "span source hash disagrees with its node", span_id=span.span_id,
                declared=span.source_content_hash, actual=node.content_hash,
            )
        data = self.read_node_bytes(node.node_id)
        if span.start < 0 or span.end <= span.start or span.end > len(data):
            raise CoverageViolation(
                "span byte range is outside its source", span_id=span.span_id,
                start=span.start, end=span.end, size=len(data),
            )
        return data[span.start:span.end]

    # --- verification -----------------------------------------------------

    def verify(self, check_blob_bytes: bool = True) -> dict[str, Any]:
        """Refuse a bundle that is not exactly what its manifest and its seal report claim.

        Returns the seal report on success so a caller can print it. Raises on the first
        violation. ``check_blob_bytes`` re-hashes every stored blob; leaving it on is the
        byte-exact round-trip check and costs one sha256 pass over the stored bytes.
        """
        man = self.manifest

        # 1. the id is the hash of its own hashed fields (created_ts and the id excluded).
        computed = man.computed_id()
        if computed != man.snapshot_id:
            raise SnapshotIdMismatch("manifest id is not the hash of the manifest",
                                     declared=man.snapshot_id, computed=computed)

        # 2. the sidecars are the ones the id was computed over.
        for path, declared, label in (
            (self.nodes_path, man.nodes_sha256, "nodes.jsonl"),
            (self.seal_report_path, man.seal_report_sha256, "seal_report.json"),
        ):
            if not path.is_file():
                raise SnapshotIncomplete(f"bundle has no {label}", path=str(path))
            actual = sha256_file(path)
            if actual != declared:
                raise ContentHashMismatch(f"{label} does not match the manifest",
                                          declared=declared, actual=actual)

        # 3. every node: policy consistent, seal absolute, blob bytes match their hash.
        seen = 0
        sealed_seen = 0
        for node in self.iter_nodes():
            seen += 1
            soul = is_soul_path(node.path)
            if soul and not node.sealed:
                raise SealViolation("a soul path entered the bundle unsealed",
                                    node_id=node.node_id)
            if node.sealed or soul:
                sealed_seen += 1
                if node.content_blob is not None:
                    raise SealViolation("a sealed node carries content",
                                        node_id=node.node_id, blob=node.content_blob)
                if node.content_hash != REFS_ONLY:
                    raise SealViolation("a sealed node carries a content hash",
                                        node_id=node.node_id, content_hash=node.content_hash)
                continue
            if node.read_policy == "asset-not-read":
                if node.content_blob is not None or node.content_hash != NOT_READ:
                    raise ContentHashMismatch("an unread asset carries content",
                                              node_id=node.node_id)
                continue
            if node.content_blob is None:
                raise ContentHashMismatch("a text node carries no blob", node_id=node.node_id)
            if node.content_blob != node.content_hash:
                raise ContentHashMismatch("blob key and content hash disagree",
                                          node_id=node.node_id, key=node.content_blob,
                                          content_hash=node.content_hash)
            if check_blob_bytes:
                data = self.read_node_bytes(node.node_id)  # verified cache or pinned Git bytes
                if len(data) != node.size_bytes:
                    raise ContentHashMismatch("stored size disagrees with the record",
                                              node_id=node.node_id, stored=len(data),
                                              declared=node.size_bytes)
            elif man.tree_dirty and not self.blobs.has(node.content_blob):
                raise ContentHashMismatch("blob named by a node is absent",
                                          node_id=node.node_id, key=node.content_blob)
        if seen != man.node_count:
            raise SnapshotIncomplete("node count disagrees with the manifest",
                                     rows=seen, declared=man.node_count)

        # 4. the seal report's two counts, recomputed rather than believed.
        report = self.seal_report
        for key in ("soul_paths_with_content", "sealed_spans"):
            if key not in report:
                raise SealViolation("seal report is missing a required count", missing=key)
            if int(report[key]) != 0:
                raise SealViolation("seal report is nonzero", count=key, value=report[key])
        if int(report.get("sealed_nodes", -1)) != sealed_seen:
            raise SealViolation("seal report sealed-node count disagrees with the rows",
                                declared=report.get("sealed_nodes"), counted=sealed_seen)

        # 5. spans, when the bundle carries them: no span over a sealed node, ids reproduce,
        #    parents contain their children, leaves partition every segmented node.
        if self.has_spans():
            self._verify_spans()
        return report

    def _verify_spans(self) -> None:
        nodes = self.nodes
        by_node: dict[str, list[tuple[int, int]]] = {}
        ranges: dict[str, tuple[int, int]] = {}
        parents: list[tuple[str, str, int, int]] = []
        for span in self.iter_spans():
            node = nodes.get(span.node_id)
            if node is None:
                raise NestingViolation("span names a node that is not in the bundle",
                                       span_id=span.span_id, node_id=span.node_id)
            if node.sealed:
                raise SealViolation("a span was cut over a sealed node",
                                    span_id=span.span_id, node_id=span.node_id)
            if node.content_hash != span.source_content_hash:
                raise ContentHashMismatch("span sources a hash the node does not carry",
                                          span_id=span.span_id, node_id=span.node_id)
            recomputed = Span.compute_id(span.source_content_hash, span.start, span.end,
                                         span.segmenter_id, span.seg_version)
            if recomputed != span.span_id:
                raise ContentHashMismatch("span id is not the hash of its own fields",
                                          declared=span.span_id, computed=recomputed)
            ranges[span.span_id] = (span.start, span.end)
            if span.parent_span is not None:
                parents.append((span.span_id, span.parent_span, span.start, span.end))
            if span.is_leaf:
                by_node.setdefault(span.node_id, []).append((span.start, span.end))

        for child, parent, start, end in parents:
            if parent not in ranges:
                raise NestingViolation("span names a parent that is not in the bundle",
                                       span_id=child, parent_span=parent)
            p_start, p_end = ranges[parent]
            if start < p_start or end > p_end:
                raise NestingViolation("parent span does not contain its child",
                                       span_id=child, parent_span=parent,
                                       child=(start, end), parent_range=(p_start, p_end))

        # Iterate the NODE set, not the spans. Walking the spans can only catch a node whose
        # spans are wrong; it cannot catch a node whose spans are absent, and an omitted node is
        # exactly the silent truncation the coverage law exists to make impossible. Every
        # unsealed text node with bytes must appear.
        for node in nodes.values():
            if node.sealed or node.content_blob is None or node.size_bytes == 0:
                continue
            spans = by_node.get(node.node_id)
            if not spans:
                raise CoverageViolation("node has bytes but no leaf spans in the bundle",
                                        node_id=node.node_id, size=node.size_bytes)
            spans.sort()
            pos = 0
            for start, end in spans:
                if start != pos:
                    raise CoverageViolation("leaf spans do not partition the node",
                                            node_id=node.node_id, expected_start=pos, got=start)
                pos = end
            if pos != node.size_bytes:
                raise CoverageViolation("leaf spans do not reach the end of the node",
                                        node_id=node.node_id, covered=pos, size=node.size_bytes)


def load_snapshot(root: Path) -> SnapshotBundle:
    """Open a bundle. Reads the manifest eagerly so a wrong path fails here, not three calls on."""
    bundle = SnapshotBundle(root)
    _ = bundle.manifest
    return bundle
