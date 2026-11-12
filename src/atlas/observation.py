"""Pure content-bearing observation over a verified immutable snapshot.

This module bridges exact snapshot spans to semantic inputs without writing Atlas state.  An atom
is emitted only when its source bytes, span, generation and UTF-8 content agree.  Everything else
is a named fog row; absence is never promoted into content.
"""

from __future__ import annotations

import json
import os
import resource
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .errors import ContentHashMismatch, SnapshotIncomplete, StateTransitionRefused
from .ids import chash, hash_bytes
from .schema import NOT_READ, REFS_ONLY, SegmentationGeneration, SemanticAtom
from .snapshot import SnapshotBundle
from .store import sha256_file


@dataclass(frozen=True)
class ObservationFog:
    """One disjoint source region that cannot lawfully become a semantic atom."""

    node_id: str
    path: str
    span_id: str | None
    start: int | None
    end: int | None
    reason: str
    byte_count: int
    detail: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "observation-fog/1",
            "node_id": self.node_id,
            "path": self.path,
            "span_id": self.span_id,
            "start": self.start,
            "end": self.end,
            "reason": self.reason,
            "byte_count": self.byte_count,
            "detail": dict(self.detail),
        }


@dataclass(frozen=True)
class SemanticObservationReceipt:
    snapshot_id: str
    generation_id: str
    atom_count: int
    fog_count: int
    observable_bytes: int
    atom_bytes: int
    fog_bytes: int
    unobservable_bytes: int
    atom_root: str
    fog_root: str
    governance_root: str
    build_wall_ms: float
    build_cpu_ms: float
    rss_before_kib: int
    rss_after_kib: int
    rss_delta_kib: int
    process_high_water_kib: int
    indexed_lookup: str = "O(1)-after-one-build"
    synthetics_genesis: str = "UNPAID-observation-protocol-O-only"

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


class SemanticObservation:
    """Immutable atom/fog projection with exact indexed addresses."""

    def __init__(
        self,
        atoms: tuple[SemanticAtom, ...],
        fog: tuple[ObservationFog, ...],
        receipt: SemanticObservationReceipt,
    ) -> None:
        self.atoms = atoms
        self.fog = fog
        self.receipt = receipt
        self._by_atom = {atom.atom_id: index for index, atom in enumerate(atoms)}
        self._by_span = {atom.span_id: index for index, atom in enumerate(atoms)}
        governance: dict[tuple[str, str], int | tuple[int, ...]] = {}
        for index, atom in enumerate(atoms):
            if atom.governance_ref is not None:
                key = (atom.governance_ref["record"], atom.governance_ref["id"])
                prior = governance.get(key)
                if prior is None:
                    governance[key] = index
                elif isinstance(prior, int):
                    governance[key] = (prior, index)
                else:
                    governance[key] = (*prior, index)
        self._by_governance = governance
        if len(self._by_atom) != len(atoms) or len(self._by_span) != len(atoms):
            raise StateTransitionRefused("semantic observation carries duplicate atom/span identity")

    @classmethod
    def build(
        cls, bundle: SnapshotBundle, generation: SegmentationGeneration
    ) -> "SemanticObservation":
        rss_before = _current_rss_kib()
        wall_start = time.perf_counter()
        cpu_start = time.process_time()
        bundle.verify()
        if generation.generation_id != generation.computed_id():
            raise ContentHashMismatch("segmentation generation id does not reproduce")
        if generation.snapshot_id != bundle.manifest.snapshot_id:
            raise ContentHashMismatch("segmentation generation names another snapshot")
        carried = bundle.segmentation()
        if carried is None or SegmentationGeneration.from_dict(carried) != generation:
            raise ContentHashMismatch("bundle does not carry the exact segmentation generation")
        if sha256_file(bundle.spans_path) != generation.spans_sha256:
            raise ContentHashMismatch("spans sidecar does not match segmentation generation")
        if generation.coverage != 1.0 or generation.structure_violations or generation.sealed_spans:
            raise StateTransitionRefused("segmentation generation is not observation-ready")

        atoms: list[SemanticAtom] = []
        fog: list[ObservationFog] = []
        atom_bytes = 0
        fog_bytes = 0
        unobservable_bytes = 0

        for node in bundle.nodes.values():
            if node.sealed or node.content_hash == REFS_ONLY:
                fog.append(ObservationFog(
                    node.node_id, node.path, None, None, None, "sealed-refs-only", 0,
                    {"source_size": node.size_bytes},
                ))
                unobservable_bytes += node.size_bytes
            elif node.content_hash == NOT_READ or node.content_blob is None:
                fog.append(ObservationFog(
                    node.node_id, node.path, None, None, None, "asset-not-read", 0,
                    {"source_size": node.size_bytes},
                ))
                unobservable_bytes += node.size_bytes

        for span in bundle.iter_spans():
            if not span.is_leaf:
                continue
            node = bundle.nodes[span.node_id]
            raw = bundle.read_carried_span_bytes(span)
            reason: str | None = None
            detail: dict[str, Any] = {}
            governance_ref: dict[str, str] | None = None
            if span.meta.get("oversize_reason"):
                reason = "oversize-span"
                detail = {"oversize_reason": span.meta["oversize_reason"]}
            try:
                content = raw.decode("utf-8", errors="strict")
            except UnicodeDecodeError as exc:
                content = ""
                reason = "invalid-utf8"
                detail = {"start": exc.start, "end": exc.end}
            if reason is None and span.kind == "jsonl_row":
                stripped = content.strip()
                if not stripped:
                    reason = "blank-jsonl-row"
                else:
                    try:
                        record = json.loads(stripped)
                    except (TypeError, ValueError) as exc:
                        reason = "invalid-jsonl-row"
                        detail = {"error": str(exc)}
                    else:
                        if isinstance(record, dict):
                            has_record = "record" in record
                            has_id = "id" in record
                            if has_record or has_id:
                                if (
                                    type(record.get("record")) is str and record["record"]
                                    and type(record.get("id")) is str and record["id"]
                                ):
                                    governance_ref = {"record": record["record"], "id": record["id"]}
                                else:
                                    reason = "malformed-governance-ref"
            if reason is not None:
                fog.append(ObservationFog(
                    node.node_id, node.path, span.span_id, span.start, span.end,
                    reason, len(raw), detail,
                ))
                fog_bytes += len(raw)
                continue
            handle = hash_bytes(raw)
            atom = SemanticAtom.create(
                snapshot_id=bundle.manifest.snapshot_id,
                generation_id=generation.generation_id,
                node_id=node.node_id,
                path=node.path,
                span_id=span.span_id,
                start=span.start,
                end=span.end,
                source_content_hash=node.content_hash,
                content_handle=handle,
                content_utf8=content,
                kind=span.kind,
                trail=tuple(span.trail),
                meta=dict(span.meta),
                governance_ref=governance_ref,
            )
            if hash_bytes(atom.content_utf8.encode("utf-8")) != atom.content_handle:
                raise ContentHashMismatch("semantic atom content does not round-trip to source bytes")
            atoms.append(atom)
            atom_bytes += len(raw)

        observable_bytes = sum(
            node.size_bytes for node in bundle.nodes.values()
            if not node.sealed and node.content_blob is not None and node.content_hash not in {REFS_ONLY, NOT_READ}
        )
        if atom_bytes + fog_bytes != observable_bytes:
            raise StateTransitionRefused(
                "semantic atom and fog bytes do not partition observable source",
                atoms=atom_bytes, fog=fog_bytes, observable=observable_bytes,
            )
        atoms.sort(key=lambda item: item.atom_id)
        fog.sort(key=lambda item: (item.node_id, item.start or -1, item.reason))
        governance_rows = sorted(
            (atom.governance_ref["record"], atom.governance_ref["id"], atom.atom_id)
            for atom in atoms if atom.governance_ref is not None
        )
        receipt = SemanticObservationReceipt(
            snapshot_id=bundle.manifest.snapshot_id,
            generation_id=generation.generation_id,
            atom_count=len(atoms), fog_count=len(fog), observable_bytes=observable_bytes,
            atom_bytes=atom_bytes, fog_bytes=fog_bytes, unobservable_bytes=unobservable_bytes,
            atom_root=chash([atom.atom_id for atom in atoms]),
            fog_root=chash([item.to_dict() for item in fog]),
            governance_root=chash(governance_rows),
            build_wall_ms=round((time.perf_counter() - wall_start) * 1000.0, 3),
            build_cpu_ms=round((time.process_time() - cpu_start) * 1000.0, 3),
            rss_before_kib=rss_before,
            rss_after_kib=0,
            rss_delta_kib=0,
            process_high_water_kib=0,
        )
        observation = cls(tuple(atoms), tuple(fog), receipt)
        rss_after = _current_rss_kib()
        observation.receipt = replace(
            observation.receipt,
            build_wall_ms=round((time.perf_counter() - wall_start) * 1000.0, 3),
            build_cpu_ms=round((time.process_time() - cpu_start) * 1000.0, 3),
            rss_after_kib=rss_after,
            rss_delta_kib=max(0, rss_after - rss_before),
            process_high_water_kib=int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
        )
        return observation

    def atom(self, atom_id: str) -> SemanticAtom:
        try:
            return self.atoms[self._by_atom[atom_id]]
        except KeyError as exc:
            raise SnapshotIncomplete("semantic atom is absent", atom_id=atom_id) from exc

    def span(self, span_id: str) -> SemanticAtom:
        try:
            return self.atoms[self._by_span[span_id]]
        except KeyError as exc:
            raise SnapshotIncomplete("semantic span is absent or fogged", span_id=span_id) from exc

    def governance(self, record: str, item_id: str) -> SemanticAtom:
        match = self._by_governance.get((record, item_id))
        if match is None:
            raise SnapshotIncomplete("governance observation is absent", record=record, id=item_id)
        if isinstance(match, tuple):
            raise StateTransitionRefused(
                "governance observation is ambiguous", record=record, id=item_id,
                matching_atoms=[self.atoms[index].atom_id for index in match],
            )
        return self.atoms[match]


def _current_rss_kib() -> int:
    """Resident pages now, distinct from the process-lifetime high-water metric."""
    try:
        fields = (Path("/proc/self/statm").read_text(encoding="ascii").split())
        return int(fields[1]) * int(os.sysconf("SC_PAGE_SIZE")) // 1024
    except (OSError, ValueError, IndexError):
        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)


__all__ = [
    "ObservationFog", "SemanticObservation", "SemanticObservationReceipt",
]
