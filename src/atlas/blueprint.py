"""Self-host the Atlas blueprint on the Atlas and reconstruct it through its own route.

The blueprint generation is the completion marker.  A half-pour may leave immutable events in
history, but it is never selected as current until this module has also resolved every declared
idea->implementation binding and banked the generation event.  Reconstruction starts from the
latest complete generation, traverses its persisted spectral frames, reports source currency,
returns exact clause spans plus implementation links, and materializes the dependency frontier.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, replace, field, asdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from .encoders.base import Encoder, EncoderRuntimeEvidence, EncoderSpec, check_contract
from .errors import StateTransitionRefused
from .history import (
    AtlasEvent,
    ConceptricEdge,
    ConceptricObject,
    EventKind,
    GradeAxis,
    MaterializedReconstruction,
    MoveDirection,
    Residual,
    ResidualStatus,
    SourceRef,
    TransportReceipt,
    Validity,
)
from .ids import chash, hash_bytes
from .routing import RawCosineRouter, RouteCandidate, RoutingContext, RoutingOperator
from .segment import segment_bytes
from .spectral_pour import (
    BankedSpectralPour,
    PourLeaf,
    PourMetadata,
    SpectralPourContract,
    bank_spectral_pour,
)
from .store import ConceptricStore

BLUEPRINT_GENERATION_SCHEMA = "atlas.blueprint-generation/6"
PREVIOUS_BLUEPRINT_GENERATION_SCHEMA = "atlas.blueprint-generation/5"
LEGACY_BLUEPRINT_GENERATION_SCHEMA = "atlas.blueprint-generation/4"
GENESIS_GENERATION = "atlas:generation:genesis"
POUR_RECEIPT_SCHEMA = "atlas.blueprint-pour-receipt/1"
BLUEPRINT_ROUTE_SCHEMA = "atlas.blueprint-route/4"
RETRIEVAL_LAW = "atlas-blueprint-fibre-local-operator-descent/4"
BLUEPRINT_EMBEDDING_BATCH_POLICY = "singleton-content/1"
PROOF_STATES = {"planted-proved", "scale-validated", "conjecture", "refused"}


def _require(condition: bool, message: str, **fields: object) -> None:
    if not condition:
        raise StateTransitionRefused(message, **fields)


class GenerationParentRefused(StateTransitionRefused):
    reason = "generation-parent-refused"


@dataclass
class PourCosts:
    """Independent dimensions; source/dependency bytes and clause-row visits only.

    Wall time ends after generation banking and the row diff, before receipt publication. Bytes
    exclude store/runtime/model I/O; supplied source bytes count when consumed. Calls
    count embed invocations; vectors count their returned rows. Records count current
    clauses processed plus parent clauses inspected for the diff, including unchanged
    rows. This is a full pour, not a claim of incremental encoding or physical I/O.
    """

    wall_seconds: float = 0.0
    bytes_read: int = 0
    encoder_calls: int = 0
    records_touched: int = 0
    vectors_built: int = 0

    def read(self, path: Path) -> bytes:
        data = path.read_bytes()
        self.bytes_read += len(data)
        return data


def generation_rows_diff(
    before: Sequence[Mapping[str, Any]], after: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Join stable logical row ids; compare content handles, never source-root hashes."""
    old = {str(row["logical_id"]): str(row["content_handle"]) for row in before}
    new = {str(row["logical_id"]): str(row["content_handle"]) for row in after}
    _require(len(old) == len(before) and len(new) == len(after),
             "generation diff has duplicate logical row ids")
    ids = {
        "added": sorted(new.keys() - old.keys()),
        "removed": sorted(old.keys() - new.keys()),
        "changed": sorted(key for key in old.keys() & new.keys() if old[key] != new[key]),
    }
    return {kind: {"count": len(keys), "ids": keys, "rows": [
        {"logical_id": key, "before_content_handle": old.get(key),
         "after_content_handle": new.get(key)} for key in keys
    ]} for kind, keys in ids.items()}


@dataclass(frozen=True)
class PourReceipt:
    generation_id: str
    parent_generation: str
    costs: Mapping[str, float | int]
    moved_rows: Mapping[str, Any]
    commit_sha: str | None = None
    schema_version: str = POUR_RECEIPT_SCHEMA
    measurement_scope: str = (
        "wall: pour entry through generation bank and row diff, excludes receipt publication; "
        "bytes: source and dependency reads, excludes store/model/runtime I/O; "
        "encoder_calls: embed invocations; vectors_built: returned embedding rows; "
        "records_touched: current clauses processed plus parent clauses diffed"
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _verified_encoder_runtime(
    spec: EncoderSpec,
    evidence: EncoderRuntimeEvidence | None,
) -> EncoderRuntimeEvidence:
    _require(evidence is not None,
             "encoder runtime has no measured provider evidence",
             encoder_spec_id=spec.spec_id)
    assert evidence is not None
    _require(evidence.encoder_spec_id == spec.spec_id,
             "encoder runtime evidence names a different specification")
    _require(evidence.metric == spec.determinism_metric,
             "encoder runtime evidence uses a different drift metric")
    _require(evidence.tolerance == spec.determinism_tolerance,
             "encoder runtime evidence uses a different tolerance")
    _require(evidence.within_tolerance,
             "encoder provider drift exceeds the declared tolerance",
             observed=evidence.observed_max_drift,
             tolerance=evidence.tolerance,
             providers=evidence.providers)
    return evidence


@dataclass(frozen=True)
class DesignDocument:
    path: str
    role: str
    document_id: str | None = None
    kind: str = "source"
    row_id_field: str | None = None


@dataclass(frozen=True)
class ImplementationBinding:
    clause_anchor: str
    implementation_path: str
    implementation_kind: str
    proof_state: str
    evidence_handles: tuple[str, ...]
    builder: str
    judge: str | None
    implementation_scope: str = "entire-clause"
    operator_roles: tuple[str, ...] = ()
    required_finding_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require(bool(self.clause_anchor.strip()), "implementation binding anchor is empty")
        _require(bool(self.implementation_path.strip()), "implementation binding path is empty")
        _require(bool(self.implementation_scope.strip()), "implementation binding scope is empty")
        _require(self.proof_state in PROOF_STATES, "implementation proof state is unknown")
        _require(bool(self.evidence_handles), "implementation binding needs evidence handles")
        _require(
            not self.operator_roles or bool(self.required_finding_ids),
            "operator binding has no required finding links (DERIVATION_GAP)",
        )
        if self.proof_state in {"planted-proved", "scale-validated"}:
            _require(bool(self.judge), "proved implementation binding needs a judge")
            _require(self.builder != self.judge, "implementation builder cannot judge its proof")


@dataclass(frozen=True)
class EvidenceFinding:
    finding_id: str
    evidence_path: str
    file_digest: str
    line_start: int
    line_end: int
    evidence_needle: str
    statement: str
    relation: str
    evidence_state: str
    operator_roles: tuple[str, ...]
    proof_scope: str
    design_role: str
    dependency_handles: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field in (
            "finding_id",
            "evidence_path",
            "file_digest",
            "evidence_needle",
            "statement",
            "relation",
            "evidence_state",
            "proof_scope",
            "design_role",
        ):
            _require(bool(str(getattr(self, field)).strip()), f"finding {field} is empty")
        _require(self.line_start >= 1 and self.line_end >= self.line_start,
                 "finding line span is invalid")
        _require(bool(self.operator_roles), "finding needs at least one operator role")
        _require(
            re.fullmatch(r"sha256:[0-9a-f]{64}", self.file_digest) is not None,
            "finding file digest is not a canonical sha256 handle",
        )


@dataclass(frozen=True)
class BlueprintGeneration:
    generation_id: str
    schema_version: str
    pour_handle: str
    pour_observation_event_id: str
    encoder_id: str
    embedding_batch_policy: str
    assumption: str
    entry_role: str
    role_fibres: Mapping[str, str]
    fibre_pours: Mapping[str, Mapping[str, str]]
    source_roots: Mapping[str, str]
    clauses: tuple[Mapping[str, Any], ...]
    clusters: tuple[Mapping[str, Any], ...]
    bindings: tuple[Mapping[str, Any], ...]
    findings: tuple[Mapping[str, Any], ...]
    lens_id: str | None = None
    encoder_spec: Mapping[str, Any] | None = None
    encoder_runtime_evidence: Mapping[str, Any] | None = None
    parent_generation: str | None = None
    receipt: PourReceipt | None = field(default=None, compare=True)

    def __post_init__(self) -> None:
        if self.schema_version == BLUEPRINT_GENERATION_SCHEMA:
            if not isinstance(self.parent_generation, str) or not (
                self.parent_generation == GENESIS_GENERATION
                or re.fullmatch(r"sha256:[0-9a-f]{64}", self.parent_generation)
            ):
                raise GenerationParentRefused("generation requires a parent_generation")

    def hashed_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            **({"parent_generation": self.parent_generation}
               if self.schema_version == BLUEPRINT_GENERATION_SCHEMA else {}),
            "pour_handle": self.pour_handle,
            "pour_observation_event_id": self.pour_observation_event_id,
            "encoder_id": self.encoder_id,
            "embedding_batch_policy": self.embedding_batch_policy,
            "assumption": self.assumption,
            "entry_role": self.entry_role,
            "role_fibres": dict(sorted(self.role_fibres.items())),
            "fibre_pours": {
                role: dict(sorted(receipt.items()))
                for role, receipt in sorted(self.fibre_pours.items())
            },
            "source_roots": dict(sorted(self.source_roots.items())),
            "clauses": [dict(item) for item in self.clauses],
            "clusters": [dict(item) for item in self.clusters],
            "bindings": [dict(item) for item in self.bindings],
            "findings": [dict(item) for item in self.findings],
            **({
                "lens_id": self.lens_id,
                "encoder_spec": dict(self.encoder_spec or {}),
                "encoder_runtime_evidence": dict(self.encoder_runtime_evidence or {}),
            } if self.schema_version in {
                BLUEPRINT_GENERATION_SCHEMA, PREVIOUS_BLUEPRINT_GENERATION_SCHEMA,
            } else {}),
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.hashed_dict(), "generation_id": self.generation_id,
                **({"receipt": self.receipt.to_dict()} if self.receipt else {})}

    @classmethod
    def create(cls, **fields: Any) -> "BlueprintGeneration":
        fields.setdefault("schema_version", BLUEPRINT_GENERATION_SCHEMA)
        draft = cls(generation_id="", **fields)
        return cls(generation_id=chash(draft.hashed_dict()), **fields)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "BlueprintGeneration":
        schema_version = str(raw.get("schema_version", ""))
        _require(schema_version in {
            BLUEPRINT_GENERATION_SCHEMA, PREVIOUS_BLUEPRINT_GENERATION_SCHEMA,
            LEGACY_BLUEPRINT_GENERATION_SCHEMA,
        },
                 "blueprint generation schema is unknown")
        result = cls(
            generation_id=str(raw["generation_id"]),
            schema_version=schema_version,
            parent_generation=raw.get("parent_generation"),
            receipt=PourReceipt(**raw["receipt"]) if raw.get("receipt") else None,
            pour_handle=str(raw["pour_handle"]),
            pour_observation_event_id=str(raw["pour_observation_event_id"]),
            encoder_id=str(raw["encoder_id"]),
            embedding_batch_policy=str(raw["embedding_batch_policy"]),
            assumption=str(raw["assumption"]),
            entry_role=str(raw["entry_role"]),
            role_fibres=dict(raw["role_fibres"]),
            fibre_pours={
                role: dict(receipt) for role, receipt in raw["fibre_pours"].items()
            },
            source_roots=dict(raw["source_roots"]),
            clauses=tuple(dict(item) for item in raw["clauses"]),
            clusters=tuple(dict(item) for item in raw["clusters"]),
            bindings=tuple(dict(item) for item in raw["bindings"]),
            findings=tuple(dict(item) for item in raw["findings"]),
            lens_id=str(raw["lens_id"]) if "lens_id" in raw else None,
            encoder_spec=dict(raw["encoder_spec"]) if "encoder_spec" in raw else None,
            encoder_runtime_evidence=(
                dict(raw["encoder_runtime_evidence"])
                if "encoder_runtime_evidence" in raw else None
            ),
        )
        if schema_version in {BLUEPRINT_GENERATION_SCHEMA, PREVIOUS_BLUEPRINT_GENERATION_SCHEMA}:
            _require(
                result.lens_id is not None
                and result.encoder_spec is not None
                and result.encoder_runtime_evidence is not None,
                "current blueprint generation omits its lens, encoder specification, or runtime "
                "evidence",
            )
            assert result.encoder_spec is not None
            assert result.encoder_runtime_evidence is not None
            parsed_spec = EncoderSpec.from_dict(dict(result.encoder_spec))
            _require(parsed_spec.encoder_id == result.encoder_id,
                     "blueprint generation encoder id contradicts its specification")
            _verified_encoder_runtime(
                parsed_spec,
                EncoderRuntimeEvidence.from_dict(dict(result.encoder_runtime_evidence)),
            )
        _require(result.generation_id == chash(result.hashed_dict()),
                 "blueprint generation id does not verify")
        return result


@dataclass(frozen=True)
class BlueprintReconstruction:
    generation_id: str
    materialization_id: str
    cache_hit: bool
    traversed_cluster_ids: tuple[str, ...]
    rejected_cluster_ids: tuple[str, ...]
    results: tuple[Mapping[str, Any], ...]
    coverage: float
    dependency_frontier: Mapping[str, str]
    source_currency: Mapping[str, Any]


def _event(
    metadata: PourMetadata,
    kind: EventKind,
    payload: Mapping[str, object],
    *,
    subject: str,
    assumption: str | None,
    fibre: str | None,
    residual: Residual,
    provenance: tuple[SourceRef, ...] | None = None,
    causation_ids: tuple[str, ...] = (),
) -> AtlasEvent:
    return AtlasEvent.create(
        occurred_at=metadata.occurred_at,
        kind=kind,
        producer=metadata.producer,
        actor=metadata.actor,
        subject=subject,
        assumption=assumption,
        fibre=fibre,
        correlation_id=metadata.correlation_id,
        causation_ids=causation_ids,
        provenance=provenance or metadata.provenance,
        residual=residual,
        runtime=metadata.runtime,
        producer_ref=metadata.producer_ref,
        validity=Validity.VALID,
        payload=dict(payload),
    )


def _control_residual(detail: str) -> Residual:
    return Residual(ResidualStatus.UNKNOWN, None, None, "not-applicable", detail)


def _bank_subject_versions(
    store: ConceptricStore,
    leaves: Sequence[PourLeaf],
    contract: SpectralPourContract,
    poured: BankedSpectralPour,
    metadata: PourMetadata,
) -> tuple[dict[str, str], dict[str, str], tuple[str, ...]]:
    """Join immutable content versions to stable, path-independent design subjects."""

    state = store.replay()
    events: list[AtlasEvent] = []
    event_ids: list[str] = []
    edge_ids: dict[str, str] = {}
    subject_ids: dict[str, str] = {}
    newly_declared_subjects: dict[str, str] = {}
    for leaf in leaves:
        subject_handle = str(leaf.attributes["subject_handle"])
        subject_id = "design-subject:" + chash({
            "subject_handle": subject_handle,
            "assumption": contract.assumption,
            "fibre": contract.fibre,
        }).split(":", 1)[-1]
        subject_ids[leaf.logical_id] = subject_id
        subject_source = SourceRef(
            subject_id,
            subject_handle,
            f"atlas-subject:{subject_id}",
        )
        if subject_id not in state.graph_objects and subject_id not in newly_declared_subjects:
            subject = ConceptricObject(
                subject_id,
                "design-subject",
                subject_handle,
                contract.assumption,
                contract.fibre,
                contract.grade_contract.contract_id,
                "leaf",
                (subject_source,),
                {
                    "document_id": leaf.attributes["document_id"],
                    "section_id": leaf.attributes["section_id"],
                    "ordinal": int(leaf.logical_id.rsplit("::", 1)[-1]),
                    "source_kind": leaf.attributes.get("source_kind", "source"),
                    **({"typed_row_id": leaf.attributes["typed_row_id"],
                        "typed_row_id_field": leaf.attributes["typed_row_id_field"]}
                       if "typed_row_id" in leaf.attributes else {}),
                },
            )
            declared = _event(
                metadata,
                EventKind.OBJECT,
                subject.to_dict(),
                subject=subject_id,
                assumption=contract.assumption,
                fibre=contract.fibre,
                residual=_control_residual("stable design subject declaration"),
                provenance=(subject_source,),
                causation_ids=(poured.observation_event_id,),
            )
            events.append(declared)
            event_ids.append(declared.event_id)
            newly_declared_subjects[subject_id] = declared.event_id
        edge_handle = chash({
            "schema_version": "atlas.design-version-edge/1",
            "subject_id": subject_id,
            "version_object_id": leaf.object_id,
            "content_handle": leaf.content_handle,
            "assumption": contract.assumption,
            "fibre": contract.fibre,
        })
        edge_id = "edge:version-of:" + edge_handle.split(":", 1)[-1]
        edge_ids[leaf.logical_id] = edge_id
        if edge_id in state.graph_edges:
            continue
        source = SourceRef(
            f"design-version:{leaf.logical_id}",
            str(leaf.attributes["source_hash"]),
            str(leaf.attributes["source_path"]),
        )
        edge = ConceptricEdge(
            edge_id,
            "version-of",
            leaf.object_id,
            subject_id,
            MoveDirection.CONJUGATE,
            contract.assumption,
            contract.fibre,
            "stable-subject-immutable-version/1",
            GradeAxis(
                contract.grade_contract.contract_id,
                contract.grade_contract.axis,
                "leaf",
                "leaf",
            ),
            (source, subject_source),
            _control_residual("immutable content version resolves one stable design subject"),
            leaf.content_handle,
        )
        edge_event = _event(
            metadata,
            EventKind.EDGE,
            edge.to_dict(),
            subject=edge_id,
            assumption=contract.assumption,
            fibre=contract.fibre,
            residual=edge.residual,
            provenance=edge.provenance,
            causation_ids=(
                poured.observation_event_id,
                *((newly_declared_subjects[subject_id],)
                  if subject_id in newly_declared_subjects else ()),
            ),
        )
        events.append(edge_event)
        event_ids.append(edge_event.event_id)
    if events:
        store.append_many(events)
    return subject_ids, edge_ids, tuple(event_ids)


def _role_fibre(base_fibre: str, role: str) -> str:
    return f"{base_fibre}::jurisdiction::{role}"


def _role_contract(
    contract: SpectralPourContract,
    role: str,
    leaf_count: int,
) -> SpectralPourContract:
    _require(leaf_count >= 1, "blueprint jurisdiction has no clauses", role=role)
    return replace(
        contract,
        fibre=_role_fibre(contract.fibre, role),
        cluster_count=min(contract.cluster_count, leaf_count),
    )


def _transport_to(
    store: ConceptricStore,
    target_assumption: str,
    target_fibre: str,
    metadata: PourMetadata,
    *,
    operator: str,
    loss_or_obstruction: str,
) -> str | None:
    """Move the singleton write context explicitly; the context edge remains in Atlas."""

    state = store.replay()
    if state.active_assumption is None:
        return None
    if (state.active_assumption, state.active_fibre) == (target_assumption, target_fibre):
        return None
    transport_id = "transport:" + chash({
        "from_assumption": state.active_assumption,
        "from_fibre": state.active_fibre,
        "to_assumption": target_assumption,
        "to_fibre": target_fibre,
        "operator": operator,
        "loss_or_obstruction": loss_or_obstruction,
        "from_head": state.head_event_id,
    }).removeprefix("sha256:")
    receipt = TransportReceipt(
        transport_id,
        state.active_assumption,
        target_assumption,
        state.active_fibre or "",
        target_fibre,
        operator,
        loss_or_obstruction,
    )
    transported = _event(
        metadata,
        EventKind.TRANSPORT,
        receipt.to_dict(),
        subject=transport_id,
        assumption=target_assumption,
        fibre=target_fibre,
        residual=_control_residual(loss_or_obstruction),
        causation_ids=((state.head_event_id,) if state.head_event_id else ()),
    )
    store.append(transported)
    return transported.event_id


_EXPLICIT_SECTION_ID = re.compile(r"^([A-Za-z0-9]+(?:-[A-Za-z0-9]+)+)\b")


def _document_id(document: DesignDocument) -> str:
    return document.document_id or f"path-bound:{document.path}"


def _section_id(trail: Sequence[str]) -> str:
    heading = str(trail[-1]).strip() if trail else "document-root"
    explicit = _EXPLICIT_SECTION_ID.match(heading)
    if explicit:
        return explicit.group(1).casefold()
    normalized = " ".join(heading.casefold().split())
    return "heading:" + chash({"heading": normalized}).split(":", 1)[-1]


def _logical_id(document_id: str, section_id: str, ordinal: int) -> str:
    return f"design:{document_id}::{section_id}::{ordinal}"


def _typed_row_identity(document: DesignDocument, text: str, span: Any) -> tuple[str, int, str]:
    """Derive a path-independent subject coordinate from one declared JSONL row key."""
    _require(document.kind == "typed-row", "typed row identity used for a non-row document")
    _require(span.segmenter_id == "structured-jsonl/1", "typed row source bypassed JsonlSegmenter",
             path=document.path, segmenter_id=span.segmenter_id)
    _require(document.row_id_field is not None, "typed row document lacks row id field",
             path=document.path)
    try:
        row = json.loads(text)
    except json.JSONDecodeError as exc:
        raise StateTransitionRefused("typed JSONL row is not valid JSON", path=document.path,
                                     start=span.start, end=span.end) from exc
    _require(isinstance(row, dict), "typed JSONL row must be an object", path=document.path,
             start=span.start, end=span.end)
    key = row.get(document.row_id_field)
    _require(isinstance(key, (str, int)) and bool(str(key).strip()),
             "typed JSONL row has no stable identity", path=document.path,
             field=document.row_id_field, start=span.start, end=span.end)
    stable_key = str(key)
    section_id = "row:" + chash({"row_id_field": document.row_id_field, "row_id": stable_key}).split(":", 1)[1]
    return section_id, 0, stable_key


def _design_leaves(
    repo_root: Path,
    documents: Sequence[DesignDocument],
    encoder: Encoder,
    contract: SpectralPourContract,
    *, source_contents: Mapping[str, bytes] | None = None,
    segmentation: Mapping[str, Any] | None = None,
    segmentation_report: dict[str, Any] | None = None,
    costs: PourCosts | None = None,
) -> tuple[tuple[PourLeaf, ...], dict[str, str]]:
    pending: list[tuple[str, str, bytes, Any, str, dict[str, str]]] = []
    roots: dict[str, str] = {}
    for document in documents:
        path = repo_root / document.path
        data = path.read_bytes() if source_contents is None else source_contents[document.path]
        if costs is not None:
            costs.bytes_read += len(data)
        source_hash = hash_bytes(data)
        roots[document.path] = source_hash
        segmented = segment_bytes(
            f"design-source:{document.path}", document.path, source_hash, data,
            **dict(segmentation or {}),
        )
        if segmentation_report is not None:
            from .segment.base import check_coverage
            segmentation_report.setdefault("files", []).append({
                "path": document.path, "bytes": len(data),
                "covered_bytes": check_coverage(document.path, len(data), segmented.spans),
                "spans": len(segmented.spans),
                "leaves": sum(span.is_leaf for span in segmented.spans),
                "structure_violations": 0,
                "oversize": [{"path": document.path, **row} for row in segmented.oversize],
                "misses": segmented.misses,
            })
        document_id = _document_id(document)
        ordinals: dict[str, int] = {}
        typed_row_ids: set[str] = set()
        for span in (item for item in segmented.spans if item.is_leaf):
            trail = tuple(span.trail)
            text = data[span.start:span.end].decode("utf-8", errors="replace")
            if document.kind == "typed-row":
                section_id, ordinal, typed_row_id = _typed_row_identity(document, text, span)
                _require(typed_row_id not in typed_row_ids, "typed JSONL source has duplicate stable identity",
                         path=document.path, field=document.row_id_field, row_id=typed_row_id)
                typed_row_ids.add(typed_row_id)
            else:
                section_id = _section_id(trail)
                ordinal = ordinals.get(section_id, 0)
                ordinals[section_id] = ordinal + 1
                typed_row_id = None
            logical_id = _logical_id(document_id, section_id, ordinal)
            subject_handle = chash({
                "schema_version": "atlas.design-subject/1",
                "document_id": document_id,
                "section_id": section_id,
                "ordinal": ordinal,
            })
            exact_byte_hash = hash_bytes(data[span.start:span.end])
            content_handle = chash({
                "schema_version": "atlas.design-content-version/1",
                "subject_handle": subject_handle,
                "exact_byte_hash": exact_byte_hash,
                "segmenter_id": span.segmenter_id,
                "seg_version": span.seg_version,
            })
            pending.append((logical_id, document.role, data, span, text, {
                "document_id": document_id,
                "section_id": section_id,
                "subject_handle": subject_handle,
                "content_handle": content_handle,
                "exact_byte_hash": exact_byte_hash,
                "embedding_batch_policy": BLUEPRINT_EMBEDDING_BATCH_POLICY,
                **({"typed_row_id": typed_row_id, "typed_row_id_field": document.row_id_field}
                   if typed_row_id is not None else {}),
            }))
    if source_contents is not None and callable(getattr(encoder, "token_lengths", None)):
        token_counts = encoder.token_lengths([item[4] for item in pending])
        oversize = [{"path": item[3].node_id.removeprefix("design-source:"),
                     "start": item[3].start, "end": item[3].end, "tokens": count}
                    for item, count in zip(pending, token_counts, strict=True)
                    if count > encoder.max_tokens]
        _require(not oversize, "dataset leaves exceed the declared encoder window",
                 issue="ENCODER-WINDOW-EXCEEDED", owner="dataset-segmentation",
                 cap=encoder.max_tokens, oversize=oversize)
        if segmentation_report is not None:
            segmentation_report["encoder_window"] = {
                "cap_tokens": encoder.max_tokens,
                "maximum_tokens_including_special": max(token_counts, default=0),
                "oversize": oversize,
            }
    # ONNX float output is measurably padding/batch dependent.  Singleton content batches make
    # an unchanged clause independent of sibling insertion without quantizing away fidelity.
    vectors = []
    for item in pending:
        if costs is not None:
            costs.encoder_calls += 1
        batch = encoder.embed([item[4]])
        if costs is not None:
            costs.vectors_built += len(batch)
        _require(len(batch) == 1, "singleton embedding returned a different row count")
        vectors.append(batch[0])
    if costs is not None:
        costs.records_touched += len(pending)
    check_contract(encoder, vectors)
    leaves: list[PourLeaf] = []
    for (logical_id, role, _data, span, text, identity), vector in zip(
        pending, vectors, strict=True
    ):
        object_id = "design-clause:" + chash({
            "schema_version": "atlas.design-clause-occurrence/3",
            "subject_handle": identity["subject_handle"],
            "content_handle": identity["content_handle"],
            "design_role": role,
            "assumption": contract.assumption,
            "fibre": _role_fibre(contract.fibre, role),
            "grade_contract_id": contract.grade_contract.contract_id,
            "metric_version": contract.metric_version,
            "lens_id": contract.lens_id,
            "encoder_spec_id": contract.encoder_spec.spec_id,
            "encoder_version": contract.encoder_version,
            "embedding_batch_policy": BLUEPRINT_EMBEDDING_BATCH_POLICY,
        }).split(":", 1)[-1]
        leaves.append(PourLeaf(
            logical_id,
            object_id,
            identity["content_handle"],
            text,
            tuple(vector),
            (span.source_content_hash, identity["content_handle"]),
            {
                "source_path": span.node_id.removeprefix("design-source:"),
                "source_hash": span.source_content_hash,
                "start": span.start,
                "end": span.end,
                "trail": list(span.trail),
                "design_role": role,
                **identity,
                "segmenter_id": span.segmenter_id,
                "seg_version": span.seg_version,
            },
        ))
    _require(bool(leaves), "blueprint segmentation produced no leaves")
    return tuple(leaves), roots


def _bankable_leaf(leaf: PourLeaf) -> PourLeaf:
    """Strip source-location custody from an immutable semantic occurrence.

    Exact paths, document roots and byte spans live on the completed generation.  Keeping them
    on the semantic object would make an unchanged clause contradict itself whenever a sibling
    edit changes the enclosing document hash.
    """

    invariant_keys = (
        "document_id",
        "section_id",
        "subject_handle",
        "content_handle",
        "exact_byte_hash",
        "design_role",
        "segmenter_id",
        "seg_version",
        "embedding_batch_policy",
        "source_kind",
        "typed_row_id",
        "typed_row_id_field",
    )
    return replace(
        leaf,
        source_chain=(
            str(leaf.attributes["exact_byte_hash"]),
            leaf.content_handle,
        ),
        attributes={key: leaf.attributes[key] for key in invariant_keys if key in leaf.attributes},
    )


def _placement_metadata(
    metadata: PourMetadata, contract: SpectralPourContract
) -> PourMetadata:
    """Give reusable semantic objects stable provenance, independent of a pour manifest."""

    contract_handle = contract.contract_handle
    return replace(
        metadata,
        provenance=(
            SourceRef(
                "atlas:blueprint-placement-contract",
                contract_handle,
                f"atlas-contract:{contract_handle}",
            ),
        ),
    )


def _resolve_clause(
    leaves: Sequence[PourLeaf], anchor: str
) -> PourLeaf:
    needle = anchor.casefold()
    structural = [
        leaf for leaf in leaves
        if leaf.attributes.get("trail")
        and str(leaf.attributes["trail"][-1]).casefold().startswith(needle)
    ]
    if structural:
        defining = [
            leaf for leaf in structural
            if leaf.text.lstrip().startswith("#")
            and needle in leaf.text.splitlines()[0].casefold()
        ]
        _require(
            len(defining) == 1,
            "implementation heading anchor must resolve one defining clause",
            anchor=anchor,
            matches=len(defining),
        )
        return defining[0]
    matches = [
        leaf for leaf in leaves
        if needle in (leaf.logical_id + "\n" + leaf.text).casefold()
    ]
    _require(len(matches) == 1, "implementation anchor must resolve exactly one design clause",
             anchor=anchor, matches=len(matches))
    return matches[0]


def _proof_residual(binding: ImplementationBinding) -> Residual:
    if binding.proof_state in {"planted-proved", "scale-validated"}:
        return Residual(
            ResidualStatus.WITHIN_BOUND, 0.0, 0.0, "implementation-proof-gap",
            binding.proof_state,
        )
    if binding.proof_state == "refused":
        return Residual(
            ResidualStatus.EXCEEDS_BOUND, 1.0, 0.0, "implementation-proof-gap",
            binding.proof_state,
        )
    return Residual(
        ResidualStatus.UNKNOWN, None, None, "implementation-proof-gap",
        binding.proof_state,
    )


def _add_file_dependency(
    repo_root: Path,
    roots: dict[str, str],
    reference: str,
    declared_digest: str | None = None,
    costs: PourCosts | None = None,
) -> None:
    """Add a path-like provenance/evidence reference to generation freshness custody."""

    path_text = reference.split("::", 1)[0].split("#", 1)[0]
    if not path_text or "://" in path_text:
        return
    target = repo_root / path_text
    if not target.is_file():
        return
    actual = hash_bytes(costs.read(target) if costs is not None else target.read_bytes())
    expected = declared_digest
    if expected is None and "#sha256:" in reference:
        expected = "sha256:" + reference.split("#sha256:", 1)[1]
    if expected is not None:
        _require(
            actual == expected,
            "declared evidence digest contradicts its file",
            path=path_text,
            expected=expected,
            actual=actual,
        )
    roots[path_text] = actual


def _line_byte_span(data: bytes, line_start: int, line_end: int) -> tuple[int, int]:
    lines = data.splitlines(keepends=True)
    _require(line_end <= len(lines), "finding line span exceeds evidence file",
             line_end=line_end, line_count=len(lines))
    start = sum(len(line) for line in lines[:line_start - 1])
    end = sum(len(line) for line in lines[:line_end])
    return start, end


def _finding_residual(finding: EvidenceFinding) -> Residual:
    if finding.evidence_state == "refuted":
        return Residual(
            ResidualStatus.EXCEEDS_BOUND,
            1.0,
            0.0,
            "evidence-claim",
            f"refuted within scope: {finding.proof_scope}",
        )
    return Residual(
        ResidualStatus.WITHIN_BOUND,
        0.0,
        0.0,
        "evidence-link",
        f"{finding.evidence_state}; evidence constrains but does not confer authority: "
        f"{finding.proof_scope}",
    )


def _bank_findings(
    store: ConceptricStore,
    repo_root: Path,
    findings: Sequence[EvidenceFinding],
    binding_rows: Sequence[Mapping[str, Any]],
    role_contracts: Mapping[str, SpectralPourContract],
    entry_contract: SpectralPourContract,
    source_roots: dict[str, str],
    metadata: PourMetadata,
    costs: PourCosts | None = None,
) -> tuple[tuple[Mapping[str, Any], ...], tuple[str, ...]]:
    """Bank exact evidence spans and require every declared operator proposal to link them."""

    by_id = {finding.finding_id: finding for finding in findings}
    _require(len(by_id) == len(findings), "finding ids must be unique")
    for row in binding_rows:
        operator_roles = set(row.get("operator_roles", ()))
        required = tuple(row.get("required_finding_ids", ()))
        if operator_roles:
            _require(bool(required), "operator proposal has a DERIVATION_GAP",
                     implementation=row.get("implementation_path"))
        for finding_id in required:
            finding = by_id.get(str(finding_id))
            _require(finding is not None, "required evidence finding is absent (DERIVATION_GAP)",
                     finding_id=finding_id,
                     implementation=row.get("implementation_path"))
            assert finding is not None
            _require(finding.design_role == row.get("design_role"),
                     "required finding inhabits a different design jurisdiction",
                     finding_id=finding_id)
            _require(bool(operator_roles & set(finding.operator_roles)),
                     "required finding does not constrain the proposal's operator role",
                     finding_id=finding_id,
                     operator_roles=sorted(operator_roles))

    rows: list[Mapping[str, Any]] = []
    event_ids: list[str] = []
    for role in sorted({finding.design_role for finding in findings}):
        _require(role in role_contracts, "finding names an unknown design role", role=role)
        contract = role_contracts[role]
        _transport_to(
            store,
            contract.assumption,
            contract.fibre,
            metadata,
            operator="blueprint-bank-evidence-in-jurisdiction/1",
            loss_or_obstruction="evidence constrains proposals only inside its declared role",
        )
        state = store.replay()
        events: list[AtlasEvent] = []
        pending_objects: set[str] = set()
        pending_edges: set[str] = set()
        for finding in (item for item in findings if item.design_role == role):
            evidence_path = repo_root / finding.evidence_path
            data = costs.read(evidence_path) if costs is not None else evidence_path.read_bytes()
            actual_file_digest = hash_bytes(data)
            _require(actual_file_digest == finding.file_digest,
                     "finding evidence digest contradicts its file",
                     finding_id=finding.finding_id,
                     expected=finding.file_digest,
                     actual=actual_file_digest)
            source_roots[finding.evidence_path] = actual_file_digest
            for dependency in finding.dependency_handles:
                _add_file_dependency(repo_root, source_roots, dependency, costs=costs)
            start, end = _line_byte_span(data, finding.line_start, finding.line_end)
            span = data[start:end]
            span_text = span.decode("utf-8", errors="replace")
            _require(finding.evidence_needle in span_text,
                     "finding needle is absent from its exact evidence span",
                     finding_id=finding.finding_id)
            exact_byte_hash = hash_bytes(span)
            # A finding id is the mutable/coarse handle; the evidence version is immutable.
            # The former v1 handle omitted dependency roots and source placement, so updating a
            # scissors script could resolve the same object id to different provenance and make
            # an otherwise valid second-generation pour impossible.  Bind every field carried by
            # the version object, then join that version to a stable subject below.
            finding_handle = chash({
                "schema_version": "atlas.evidence-finding/2",
                "finding_id": finding.finding_id,
                "evidence_path": finding.evidence_path,
                "file_digest": actual_file_digest,
                "start": start,
                "end": end,
                "line_start": finding.line_start,
                "line_end": finding.line_end,
                "exact_byte_hash": exact_byte_hash,
                "statement": finding.statement,
                "relation": finding.relation,
                "evidence_state": finding.evidence_state,
                "operator_roles": list(finding.operator_roles),
                "proof_scope": finding.proof_scope,
                "design_role": role,
                "dependency_handles": list(finding.dependency_handles),
            })
            finding_object_id = "evidence-finding:" + finding_handle.split(":", 1)[-1]
            finding_source = SourceRef(
                f"evidence-finding:{finding.finding_id}",
                exact_byte_hash,
                f"{finding.evidence_path}#bytes={start}:{end}",
            )
            finding_subject_handle = chash({
                "schema_version": "atlas.evidence-finding-subject/1",
                "finding_id": finding.finding_id,
                "assumption": contract.assumption,
                "fibre": contract.fibre,
            })
            finding_subject_id = (
                "evidence-finding-subject:"
                + finding_subject_handle.split(":", 1)[-1]
            )
            finding_subject_source = SourceRef(
                finding_subject_id,
                finding_subject_handle,
                f"atlas-subject:{finding_subject_id}",
            )
            finding_subject = ConceptricObject(
                finding_subject_id,
                "evidence-finding-subject",
                finding_subject_handle,
                contract.assumption,
                contract.fibre,
                contract.grade_contract.contract_id,
                "leaf",
                (finding_subject_source,),
                {"finding_id": finding.finding_id, "design_role": role},
            )
            existing_subject = state.graph_objects.get(finding_subject_id)
            if existing_subject is not None:
                _require(
                    existing_subject == finding_subject,
                    "finding subject id resolves to a different jurisdiction",
                )
            elif finding_subject_id not in pending_objects:
                declared = _event(
                    metadata,
                    EventKind.OBJECT,
                    finding_subject.to_dict(),
                    subject=finding_subject_id,
                    assumption=contract.assumption,
                    fibre=contract.fibre,
                    residual=_control_residual("stable evidence-finding subject declaration"),
                    provenance=(finding_subject_source,),
                )
                events.append(declared)
                event_ids.append(declared.event_id)
                pending_objects.add(finding_subject_id)
            finding_object = ConceptricObject(
                finding_object_id,
                "evidence-finding",
                finding_handle,
                contract.assumption,
                contract.fibre,
                contract.grade_contract.contract_id,
                "leaf",
                (finding_source,),
                {
                    "finding_id": finding.finding_id,
                    "source_path": finding.evidence_path,
                    "source_hash": actual_file_digest,
                    "start": start,
                    "end": end,
                    "line_start": finding.line_start,
                    "line_end": finding.line_end,
                    "exact_byte_hash": exact_byte_hash,
                    "statement": finding.statement,
                    "relation": finding.relation,
                    "evidence_state": finding.evidence_state,
                    "operator_roles": list(finding.operator_roles),
                    "proof_scope": finding.proof_scope,
                    "design_role": role,
                    "dependency_handles": list(finding.dependency_handles),
                },
            )
            existing_finding = state.graph_objects.get(finding_object_id)
            if existing_finding is not None:
                _require(existing_finding == finding_object,
                         "finding object id resolves to different evidence")
            elif finding_object_id not in pending_objects:
                declared = _event(
                    metadata,
                    EventKind.OBJECT,
                    finding_object.to_dict(),
                    subject=finding_object_id,
                    assumption=contract.assumption,
                    fibre=contract.fibre,
                    residual=_finding_residual(finding),
                    provenance=(finding_source,),
                )
                events.append(declared)
                event_ids.append(declared.event_id)
                pending_objects.add(finding_object_id)

            version_handle = chash({
                "schema_version": "atlas.evidence-finding-version-edge/1",
                "subject_id": finding_subject_id,
                "version_object_id": finding_object_id,
                "finding_handle": finding_handle,
                "assumption": contract.assumption,
                "fibre": contract.fibre,
            })
            version_edge_id = (
                "edge:evidence-version-of:" + version_handle.split(":", 1)[-1]
            )
            version_edge = ConceptricEdge(
                version_edge_id,
                "version-of",
                finding_object_id,
                finding_subject_id,
                MoveDirection.CONJUGATE,
                contract.assumption,
                contract.fibre,
                "stable-subject-immutable-evidence-version/1",
                GradeAxis(
                    contract.grade_contract.contract_id,
                    contract.grade_contract.axis,
                    "leaf",
                    "leaf",
                ),
                (finding_source, finding_subject_source),
                _control_residual(
                    "immutable evidence version resolves one stable finding subject"
                ),
                finding_handle,
            )
            if version_edge_id not in state.graph_edges and version_edge_id not in pending_edges:
                version_event = _event(
                    metadata,
                    EventKind.EDGE,
                    version_edge.to_dict(),
                    subject=version_edge_id,
                    assumption=contract.assumption,
                    fibre=contract.fibre,
                    residual=version_edge.residual,
                    provenance=version_edge.provenance,
                )
                events.append(version_event)
                event_ids.append(version_event.event_id)
                pending_edges.add(version_edge_id)

            role_edge_ids: list[str] = []
            for operator_role in finding.operator_roles:
                role_handle = chash({
                    "schema_version": "atlas.operator-role/2",
                    "operator_role": operator_role,
                    "assumption": contract.assumption,
                    "fibre": contract.fibre,
                    "grade_contract_id": contract.grade_contract.contract_id,
                    "lens_id": contract.lens_id,
                    "vector_space_id": contract.vector_space_id,
                    "spectral_pour_contract": contract.contract_handle,
                })
                role_object_id = "operator-role:" + role_handle.split(":", 1)[-1]
                role_source = SourceRef(
                    "atlas:blueprint-placement-contract",
                    contract.contract_handle,
                    f"atlas-contract:{contract.contract_handle}",
                )
                role_object = ConceptricObject(
                    role_object_id,
                    "operator-role",
                    role_handle,
                    contract.assumption,
                    contract.fibre,
                    contract.grade_contract.contract_id,
                    "leaf",
                    (role_source,),
                    {"operator_role": operator_role, "design_role": role},
                )
                existing_role = state.graph_objects.get(role_object_id)
                if existing_role is not None:
                    _require(existing_role == role_object,
                             "operator role id resolves to different context")
                elif role_object_id not in pending_objects:
                    declared = _event(
                        metadata,
                        EventKind.OBJECT,
                        role_object.to_dict(),
                        subject=role_object_id,
                        assumption=contract.assumption,
                        fibre=contract.fibre,
                        residual=_control_residual("typed operator role declaration"),
                        provenance=(role_source,),
                    )
                    events.append(declared)
                    event_ids.append(declared.event_id)
                    pending_objects.add(role_object_id)
                role_edge_handle = chash({
                    "finding": finding_object_id,
                    "operator_role": role_object_id,
                    "relation": finding.relation,
                })
                role_edge_id = "edge:evidence-role:" + role_edge_handle.split(":", 1)[-1]
                role_edge = ConceptricEdge(
                    role_edge_id,
                    finding.relation,
                    finding_object_id,
                    role_object_id,
                    MoveDirection.CONJUGATE,
                    contract.assumption,
                    contract.fibre,
                    "evidence-to-operator-role/1",
                    GradeAxis(
                        contract.grade_contract.contract_id,
                        contract.grade_contract.axis,
                        "leaf",
                        "leaf",
                    ),
                    (finding_source, role_source),
                    _finding_residual(finding),
                    role_edge_handle,
                )
                if role_edge_id not in state.graph_edges and role_edge_id not in pending_edges:
                    edge_event = _event(
                        metadata,
                        EventKind.EDGE,
                        role_edge.to_dict(),
                        subject=role_edge_id,
                        assumption=contract.assumption,
                        fibre=contract.fibre,
                        residual=role_edge.residual,
                        provenance=role_edge.provenance,
                    )
                    events.append(edge_event)
                    event_ids.append(edge_event.event_id)
                    pending_edges.add(role_edge_id)
                role_edge_ids.append(role_edge_id)

            derivation_edge_ids: list[str] = []
            for binding in binding_rows:
                if finding.finding_id not in binding.get("required_finding_ids", ()):
                    continue
                implementation_source = SourceRef(
                    f"implementation:{binding['implementation_path']}",
                    str(binding["implementation_hash"]),
                    str(binding["implementation_path"]),
                )
                derivation_handle = chash({
                    "implementation": binding["implementation_object_id"],
                    "finding": finding_object_id,
                    "operator_roles": list(binding.get("operator_roles", ())),
                })
                derivation_edge_id = (
                    "edge:derives-from-evidence:" + derivation_handle.split(":", 1)[-1]
                )
                derivation_edge = ConceptricEdge(
                    derivation_edge_id,
                    "derives-from-evidence",
                    str(binding["implementation_object_id"]),
                    finding_object_id,
                    MoveDirection.CONJUGATE,
                    contract.assumption,
                    contract.fibre,
                    "implementation-evidence-derivation/1",
                    GradeAxis(
                        contract.grade_contract.contract_id,
                        contract.grade_contract.axis,
                        "leaf",
                        "leaf",
                    ),
                    (implementation_source, finding_source),
                    _control_residual(
                        "derivation is linked; implementation correctness remains separately judged"
                    ),
                    derivation_handle,
                )
                if derivation_edge_id not in state.graph_edges and \
                        derivation_edge_id not in pending_edges:
                    edge_event = _event(
                        metadata,
                        EventKind.EDGE,
                        derivation_edge.to_dict(),
                        subject=derivation_edge_id,
                        assumption=contract.assumption,
                        fibre=contract.fibre,
                        residual=derivation_edge.residual,
                        provenance=derivation_edge.provenance,
                    )
                    events.append(edge_event)
                    event_ids.append(edge_event.event_id)
                    pending_edges.add(derivation_edge_id)
                derivation_edge_ids.append(derivation_edge_id)
            rows.append({
                "finding_id": finding.finding_id,
                "finding_handle": finding_handle,
                "subject_id": finding_subject_id,
                "object_id": finding_object_id,
                "version_edge_id": version_edge_id,
                "source_path": finding.evidence_path,
                "source_hash": actual_file_digest,
                "start": start,
                "end": end,
                "line_start": finding.line_start,
                "line_end": finding.line_end,
                "exact_byte_hash": exact_byte_hash,
                "statement": finding.statement,
                "relation": finding.relation,
                "evidence_state": finding.evidence_state,
                "operator_roles": list(finding.operator_roles),
                "proof_scope": finding.proof_scope,
                "design_role": role,
                "dependency_handles": list(finding.dependency_handles),
                "operator_role_edge_ids": role_edge_ids,
                "derivation_edge_ids": derivation_edge_ids,
            })
        if events:
            store.append_many(events)
        if contract.fibre != entry_contract.fibre:
            _transport_to(
                store,
                entry_contract.assumption,
                entry_contract.fibre,
                metadata,
                operator="blueprint-return-after-evidence/1",
                loss_or_obstruction="return from evidence jurisdiction",
            )
    return tuple(rows), tuple(event_ids)


def pour_blueprint(
    store: ConceptricStore,
    repo_root: Path,
    documents: Sequence[DesignDocument],
    bindings: Sequence[ImplementationBinding],
    encoder: Encoder,
    contract: SpectralPourContract,
    metadata: PourMetadata,
    *,
    parent_generation: str = GENESIS_GENERATION,
    entry_role: str | None = None,
    findings: Sequence[EvidenceFinding] = (),
    container_root: Path | None = None,
    dataset_roots: Mapping[str, Path] | None = None,
    source_contents: Mapping[str, bytes] | None = None,
    commit_sha: str | None = None,
    segmentation: Mapping[str, Any] | None = None,
    segmentation_report: dict[str, Any] | None = None,
) -> BlueprintGeneration:
    """Pour each jurisdiction; genesis is valid only for a store with no generation."""

    started = time.perf_counter()
    costs = PourCosts()
    previous = _current_blueprint_generation(store)
    expected_parent = previous.generation_id if previous is not None else GENESIS_GENERATION
    if parent_generation != expected_parent:
        raise GenerationParentRefused(
            "this dataset already has a generation" if previous else
            "first generation requires the genesis sentinel",
            expected_parent_generation=expected_parent, parent_generation=parent_generation,
        )
    repo_root = Path(repo_root)
    _require(contract.encoder_spec == encoder.spec,
             "blueprint encoder contradicts the spectral pour contract",
             contract_encoder_spec=contract.encoder_spec.spec_id,
             encoder_spec=encoder.spec.spec_id)
    _require(contract.encoder_spec.dim == encoder.dim,
             "blueprint encoder dimension contradicts the spectral pour contract",
             contract_dim=contract.encoder_spec.dim,
             encoder_dim=encoder.dim)
    encoder_runtime_evidence = _verified_encoder_runtime(
        contract.encoder_spec, metadata.encoder_runtime_evidence
    )
    leaves, source_roots = _design_leaves(
        repo_root, documents, encoder, contract, source_contents=source_contents,
        segmentation=segmentation, segmentation_report=segmentation_report, costs=costs,
    )
    for source in metadata.provenance:
        if source.locator is not None:
            _add_file_dependency(
                repo_root, source_roots, source.locator, source.digest, costs=costs,
            )
    by_role: dict[str, list[PourLeaf]] = {}
    for leaf in leaves:
        by_role.setdefault(str(leaf.attributes["design_role"]), []).append(leaf)
    roles = tuple(sorted(by_role))
    if entry_role is None:
        _require(len(roles) == 1,
                 "multi-jurisdiction blueprint must declare one governing entry role",
                 roles=list(roles))
        entry_role = roles[0]
    _require(entry_role in by_role, "blueprint entry role has no clauses", entry_role=entry_role)
    role_contracts = {
        role: _role_contract(contract, role, len(role_leaves))
        for role, role_leaves in by_role.items()
    }
    role_fibres = {role: item.fibre for role, item in role_contracts.items()}
    poured_by_role: dict[str, BankedSpectralPour] = {}
    subject_id_by_logical: dict[str, str] = {}
    version_edge_by_logical: dict[str, str] = {}
    subject_version_event_ids: list[str] = []

    entry_contract = role_contracts[entry_role]
    _transport_to(
        store,
        entry_contract.assumption,
        entry_contract.fibre,
        metadata,
        operator="blueprint-enter-governing-fibre/1",
        loss_or_obstruction=(
            "jurisdiction changes; semantic coordinates do not grant governing authority"
        ),
    )
    poured_by_role[entry_role] = bank_spectral_pour(
        store,
        entry_contract,
        tuple(_bankable_leaf(leaf) for leaf in by_role[entry_role]),
        _placement_metadata(metadata, entry_contract),
    )
    subjects, edges, event_ids = _bank_subject_versions(
        store,
        tuple(by_role[entry_role]),
        entry_contract,
        poured_by_role[entry_role],
        metadata,
    )
    subject_id_by_logical.update(subjects)
    version_edge_by_logical.update(edges)
    subject_version_event_ids.extend(event_ids)
    for role in (item for item in roles if item != entry_role):
        role_contract = role_contracts[role]
        _transport_to(
            store,
            role_contract.assumption,
            role_contract.fibre,
            metadata,
            operator="blueprint-cross-jurisdiction-ground/1",
            loss_or_obstruction=(
                f"transport from governing role {entry_role} to supporting role {role}; "
                "supporting evidence cannot overrule governing law"
            ),
        )
        poured_by_role[role] = bank_spectral_pour(
            store,
            role_contract,
            tuple(_bankable_leaf(leaf) for leaf in by_role[role]),
            _placement_metadata(metadata, role_contract),
        )
        subjects, edges, event_ids = _bank_subject_versions(
            store,
            tuple(by_role[role]),
            role_contract,
            poured_by_role[role],
            metadata,
        )
        subject_id_by_logical.update(subjects)
        version_edge_by_logical.update(edges)
        subject_version_event_ids.extend(event_ids)
        _transport_to(
            store,
            entry_contract.assumption,
            entry_contract.fibre,
            metadata,
            operator="blueprint-return-to-governing-fibre/1",
            loss_or_obstruction=(
                f"return from supporting role {role}; its evidence remains reachable "
                "but does not become governing law"
            ),
        )

    resolved_bindings = [(_resolve_clause(leaves, binding.clause_anchor), binding)
                         for binding in bindings]
    binding_rows: list[dict[str, Any]] = []
    binding_provenance: list[SourceRef] = list(metadata.provenance)
    binding_event_ids: list[str] = []
    for role in roles:
        role_bindings = [item for item in resolved_bindings
                         if item[0].attributes["design_role"] == role]
        if not role_bindings:
            continue
        role_contract = role_contracts[role]
        _transport_to(
            store,
            role_contract.assumption,
            role_contract.fibre,
            metadata,
            operator="blueprint-bind-in-clause-jurisdiction/1",
            loss_or_obstruction=(
                "implementation proof inhabits the jurisdiction of its target clause"
            ),
        )
        state = store.replay()
        events: list[AtlasEvent] = []
        implementation_events: dict[str, AtlasEvent] = {}
        for clause, binding in role_bindings:
            implementation = repo_root / binding.implementation_path
            implementation_hash = hash_bytes(costs.read(implementation))
            source_roots[binding.implementation_path] = implementation_hash
            for evidence_handle in binding.evidence_handles:
                _add_file_dependency(repo_root, source_roots, evidence_handle, costs=costs)
            implementation_source = SourceRef(
                f"implementation:{binding.implementation_path}",
                implementation_hash,
                binding.implementation_path,
            )
            binding_provenance.append(implementation_source)
            implementation_object_id = "implementation:" + chash({
                "path": binding.implementation_path,
                "source_hash": implementation_hash,
                "fibre": role_contract.fibre,
            }).split(":", 1)[-1]
            item = ConceptricObject(
                implementation_object_id,
                binding.implementation_kind,
                implementation_hash,
                role_contract.assumption,
                role_contract.fibre,
                role_contract.grade_contract.contract_id,
                "leaf",
                (implementation_source,),
                {
                    "source_path": binding.implementation_path,
                    "source_hash": implementation_hash,
                    "builder": binding.builder,
                    "design_role": role,
                },
            )
            if implementation_object_id not in state.graph_objects and \
                    implementation_object_id not in implementation_events:
                declared = _event(
                    metadata,
                    EventKind.OBJECT,
                    item.to_dict(),
                    subject=implementation_object_id,
                    assumption=role_contract.assumption,
                    fibre=role_contract.fibre,
                    residual=_control_residual("implementation source declaration"),
                    provenance=(implementation_source,),
                )
                implementation_events[implementation_object_id] = declared
                events.append(declared)
            binding_handle = chash({
                "clause_object_id": clause.object_id,
                "implementation_object_id": implementation_object_id,
                "proof_state": binding.proof_state,
                "evidence_handles": list(binding.evidence_handles),
                "builder": binding.builder,
                "judge": binding.judge,
                "implementation_scope": binding.implementation_scope,
                "operator_roles": list(binding.operator_roles),
                "required_finding_ids": list(binding.required_finding_ids),
            })
            edge = ConceptricEdge(
                "edge:implements:" + binding_handle.split(":", 1)[-1],
                "implements",
                implementation_object_id,
                clause.object_id,
                MoveDirection.CONJUGATE,
                role_contract.assumption,
                role_contract.fibre,
                "idea-implementation-binding/1",
                GradeAxis(
                    role_contract.grade_contract.contract_id,
                    role_contract.grade_contract.axis,
                    "leaf",
                    "leaf",
                ),
                (implementation_source, *metadata.provenance),
                _proof_residual(binding),
                binding_handle,
            )
            edge_event = _event(
                metadata,
                EventKind.EDGE,
                edge.to_dict(),
                subject=edge.edge_id,
                assumption=role_contract.assumption,
                fibre=role_contract.fibre,
                residual=edge.residual,
                provenance=edge.provenance,
                causation_ids=(
                    *((implementation_events[implementation_object_id].event_id,)
                      if implementation_object_id in implementation_events else ()),
                    poured_by_role[role].observation_event_id,
                ),
            )
            if edge.edge_id not in state.graph_edges:
                events.append(edge_event)
                binding_event_ids.append(edge_event.event_id)
            binding_rows.append({
                "binding_handle": binding_handle,
                "edge_id": edge.edge_id,
                "clause_logical_id": clause.logical_id,
                "clause_object_id": clause.object_id,
                "implementation_object_id": implementation_object_id,
                "implementation_path": binding.implementation_path,
                "implementation_hash": implementation_hash,
                "design_role": role,
                "fibre": role_contract.fibre,
                "proof_state": binding.proof_state,
                "evidence_handles": list(binding.evidence_handles),
                "builder": binding.builder,
                "judge": binding.judge,
                "implementation_scope": binding.implementation_scope,
                "operator_roles": list(binding.operator_roles),
                "required_finding_ids": list(binding.required_finding_ids),
            })
        if events:
            store.append_many(events)
        if role != entry_role:
            _transport_to(
                store,
                entry_contract.assumption,
                entry_contract.fibre,
                metadata,
                operator="blueprint-return-after-binding/1",
                loss_or_obstruction=(
                    f"return from implementation binding in supporting role {role}"
                ),
            )

    finding_rows, finding_event_ids = _bank_findings(
        store,
        repo_root,
        findings,
        binding_rows,
        role_contracts,
        entry_contract,
        source_roots,
        metadata,
        costs,
    )

    _transport_to(
        store,
        entry_contract.assumption,
        entry_contract.fibre,
        metadata,
        operator="blueprint-complete-in-governing-fibre/1",
        loss_or_obstruction="generation currentness is asserted only in its governing fibre",
    )

    clauses = tuple({
        "logical_id": leaf.logical_id,
        "object_id": leaf.object_id,
        "content_handle": leaf.content_handle,
        "subject_id": subject_id_by_logical[leaf.logical_id],
        "subject_handle": leaf.attributes["subject_handle"],
        "version_edge_id": version_edge_by_logical[leaf.logical_id],
        "exact_byte_hash": leaf.attributes["exact_byte_hash"],
        "source_path": leaf.attributes["source_path"],
        "source_hash": leaf.attributes["source_hash"],
        "start": leaf.attributes["start"],
        "end": leaf.attributes["end"],
        "trail": leaf.attributes["trail"],
        "source_kind": leaf.attributes.get("source_kind", "source"),
        **({"typed_row_id": leaf.attributes["typed_row_id"],
            "typed_row_id_field": leaf.attributes["typed_row_id_field"]}
           if "typed_row_id" in leaf.attributes else {}),
        "design_role": leaf.attributes["design_role"],
        "fibre": role_fibres[str(leaf.attributes["design_role"])],
    } for leaf in leaves)
    clusters = tuple(
        {
            "cluster_id": cluster.cluster_id,
            "design_role": role,
            "fibre": role_fibres[role],
            "member_logical_ids": list(cluster.member_logical_ids),
            "child_cluster_ids": [child.cluster_id for child in cluster.children],
            "depth": cluster.depth,
            "stop_reason": cluster.stop_reason,
            "coarse_object_id": poured.promotions[cluster.cluster_id].coarse_object_id,
            "spectral_object_id": poured.promotions[cluster.cluster_id].spectral_object_id,
            "semantic_object_id": poured.promotions[cluster.cluster_id].semantic_object_id,
            "node_handle": poured.promotions[cluster.cluster_id].node_handle,
            "promotion_event_id": poured.promotion_event_ids[cluster.cluster_id],
        }
        for role, poured in sorted(poured_by_role.items())
        for root in poured.receipt.placement
        for cluster in root.walk()
    )
    aggregate_pour_handle = chash({
        "schema_version": "atlas.blueprint-fibre-pours/1",
        "entry_role": entry_role,
        "pours": {
            role: poured.receipt.pour_handle
            for role, poured in sorted(poured_by_role.items())
        },
    })
    fibre_pours = {
        role: {
            "pour_handle": poured.receipt.pour_handle,
            "observation_event_id": poured.observation_event_id,
        }
        for role, poured in sorted(poured_by_role.items())
    }
    generation = BlueprintGeneration.create(
        parent_generation=parent_generation,
        pour_handle=aggregate_pour_handle,
        pour_observation_event_id=poured_by_role[entry_role].observation_event_id,
        encoder_id=encoder.encoder_id,
        lens_id=entry_contract.lens_id,
        encoder_spec=entry_contract.encoder_spec.to_dict(),
        encoder_runtime_evidence=encoder_runtime_evidence.to_dict(),
        embedding_batch_policy=BLUEPRINT_EMBEDDING_BATCH_POLICY,
        assumption=entry_contract.assumption,
        entry_role=entry_role,
        role_fibres=role_fibres,
        fibre_pours=fibre_pours,
        source_roots=_portable_source_roots(
            source_roots, repo_root, container_root or repo_root, dataset_roots or {},
        ),
        clauses=clauses,
        clusters=clusters,
        bindings=tuple(binding_rows),
        findings=finding_rows,
    )
    generation_event = _event(
        metadata,
        EventKind.OBSERVATION,
        generation.to_dict(),
        subject=generation.generation_id,
        assumption=entry_contract.assumption,
        fibre=entry_contract.fibre,
        residual=Residual(
            ResidualStatus.WITHIN_BOUND,
            0.0,
            0.0,
            "unresolved-implementation-binding-count",
            "every declared binding resolved before this generation became current",
        ),
        provenance=tuple(dict.fromkeys(binding_provenance)),
        causation_ids=(
            *tuple(poured.observation_event_id for poured in poured_by_role.values()),
            *tuple(subject_version_event_ids),
            *tuple(binding_event_ids),
            *tuple(finding_event_ids),
        ),
    )
    store.append(generation_event)
    old_rows = previous.clauses if previous is not None else ()
    moved_rows = generation_rows_diff(old_rows, generation.clauses)
    costs.records_touched += len(old_rows)
    costs.wall_seconds = time.perf_counter() - started
    receipt = PourReceipt(
        generation.generation_id,
        parent_generation,
        asdict(costs),
        moved_rows,
        commit_sha=commit_sha,
    )
    store.append(_event(
        metadata, EventKind.OBSERVATION, receipt.to_dict(),
        subject=generation.generation_id, assumption=entry_contract.assumption,
        fibre=entry_contract.fibre, residual=_control_residual("measured pour and row diff"),
        causation_ids=(generation_event.event_id,),
    ))
    return replace(generation, receipt=receipt)


def _current_blueprint_generation(store: ConceptricStore) -> BlueprintGeneration | None:
    receipts: dict[str, PourReceipt] = {}
    for event in reversed(store.events()):
        schema = event.payload.get("schema_version")
        if event.kind == EventKind.OBSERVATION and schema == POUR_RECEIPT_SCHEMA:
            receipt = PourReceipt(**event.payload)
            receipts.setdefault(receipt.generation_id, receipt)
        if event.kind == EventKind.OBSERVATION and isinstance(schema, str) and \
                schema.startswith("atlas.blueprint-generation/"):
            # An unknown newer completion marker must not make the reader fall back to an older
            # generation.  The latest claimed completion is either understood exactly or loud.
            generation = BlueprintGeneration.from_dict(event.payload)
            receipt = receipts.get(generation.generation_id)
            if generation.schema_version == BLUEPRINT_GENERATION_SCHEMA:
                _require(receipt is not None, "completed generation has no pour receipt")
                assert receipt is not None
                _require(receipt.parent_generation == generation.parent_generation,
                         "pour receipt contradicts generation parent")
                generation = replace(generation, receipt=receipt)
            return generation
    return None


def current_blueprint_generation(store: ConceptricStore) -> BlueprintGeneration:
    generation = _current_blueprint_generation(store)
    if generation is not None:
        return generation
    raise StateTransitionRefused("canonical Atlas store has no complete blueprint generation")


def _portable_source_roots(
    roots: Mapping[str, str],
    repo_root: Path,
    container_root: Path,
    dataset_roots: Mapping[str, Path],
) -> dict[str, str]:
    """Mint location-independent keys; external files need a declared dataset root.

    Only new completion markers use this spelling. Historical generations and their
    content hashes are never rewritten. The container wins over enclosing datasets;
    otherwise the most specific declared dataset root wins.
    """
    namespaces = [("container", Path(container_root).resolve())]
    for name in dataset_roots:
        _require(re.fullmatch(r"[A-Za-z0-9_.-]+", name) is not None,
                 "blueprint dataset root id is invalid", dataset_id=name)
    namespaces.extend(
        (f"dataset:{name}", root)
        for name, root in sorted(
            ((name, Path(root).resolve()) for name, root in dataset_roots.items()),
            key=lambda item: (-len(item[1].parts), item[0]),
        )
    )
    portable = {}
    for path, digest in roots.items():
        target = (repo_root / path).resolve()
        for namespace, root in namespaces:
            if target.is_relative_to(root):
                key = f"{namespace}://{target.relative_to(root).as_posix()}"
                _require(key not in portable or portable[key] == digest,
                         "blueprint source root key collision", path=key)
                portable[key] = digest
                break
        else:
            raise StateTransitionRefused(
                "blueprint source is outside declared roots; declare its dataset root",
                path=path,
            )
    return portable


def blueprint_source_currency(
    repo_root: Path,
    generation: BlueprintGeneration,
    *,
    container_root: Path | None = None,
    dataset_roots: Mapping[str, Path] | None = None,
) -> dict[str, Any]:
    """Advisory WORKTREE comparison, never a condition for serving banked bytes.

    Missing/unreadable sources mean the next pour is due. This does not verify a
    pinned commit. Legacy engine-relative keys are interpreted without rewriting
    the immutable generation; a detached container never guesses an engine parent.
    """
    repo_root = Path(repo_root)
    legacy_engine = any(path.startswith("atlas/") for path in generation.source_roots)
    embedded_legacy = legacy_engine and (repo_root / "atlas/src/atlas").is_dir()
    container = (Path(container_root) if container_root is not None else
                 repo_root / "atlas" if embedded_legacy else repo_root)
    datasets = (dataset_roots if dataset_roots is not None else
                {"engine": repo_root} if embedded_legacy else {})
    moved = []
    for path, expected in generation.source_roots.items():
        target = None
        if path.startswith("container://"):
            root, relative = container, path.removeprefix("container://")
        elif path.startswith("dataset:") and "://" in path:
            namespace, relative = path.split("://", 1)
            root = datasets.get(namespace.removeprefix("dataset:"))
        elif legacy_engine:
            if path.startswith("atlas/"):
                root, relative = container, path.removeprefix("atlas/")
            else:
                root, relative = datasets.get("engine"), path
        else:
            root, relative = repo_root, path
        if root is not None and not Path(relative).is_absolute() and ".." not in Path(relative).parts:
            target = Path(root) / relative
        try:
            actual = hash_bytes(target.read_bytes()) if target is not None else None
        except OSError:
            actual = None
        if actual != expected:
            moved.append({"path": path, "expected": expected, "actual": actual})
    return {"source_roots": "MOVED" if moved else "CURRENT", "moved": moved}


def _fresh(repo_root: Path, generation: BlueprintGeneration, **roots: Any) -> None:
    """Strict freshness guard for a write that consumes an existing generation."""
    currency = blueprint_source_currency(repo_root, generation, **roots)
    _require(not currency["moved"],
             "blueprint sources moved; re-pour dirty design before write",
             moved=currency["moved"])


def reconstruct_blueprint(
    store: ConceptricStore,
    repo_root: Path,
    goal: str,
    encoder: Encoder,
    metadata: PourMetadata,
    *,
    top_k: int = 5,
    beam: int = 3,
    role: str | None = None,
    route_operator: RoutingOperator | None = None,
    container_root: Path | None = None,
    dataset_roots: Mapping[str, Path] | None = None,
) -> BlueprintReconstruction:
    """Descend one declared design jurisdiction and materialize its exact dependencies.

    The governing role is the only implicit entry.  Supporting or historical ground can be
    queried, but only by naming its role. A writable store banks the fibre transport
    and route receipt; a read-only store returns ranked results without changing write context.
    Semantic similarity is never allowed to confer authority by crossing the role boundary.
    """

    generation = current_blueprint_generation(store)
    _require(generation.encoder_id == encoder.encoder_id,
             "reconstruction encoder contradicts the current blueprint generation")
    if generation.schema_version in {BLUEPRINT_GENERATION_SCHEMA, PREVIOUS_BLUEPRINT_GENERATION_SCHEMA}:
        assert generation.encoder_spec is not None
        expected_spec = EncoderSpec.from_dict(dict(generation.encoder_spec))
        _require(expected_spec == encoder.spec,
                 "reconstruction encoder specification contradicts the current blueprint "
                 "generation",
                 generation_encoder_spec=expected_spec.spec_id,
                 encoder_spec=encoder.spec.spec_id)
        assert generation.encoder_runtime_evidence is not None
        _verified_encoder_runtime(
            expected_spec,
            EncoderRuntimeEvidence.from_dict(dict(generation.encoder_runtime_evidence)),
        )
        _verified_encoder_runtime(expected_spec, metadata.encoder_runtime_evidence)
        route_encoder_version = expected_spec.spec_id
    else:
        route_encoder_version = encoder.encoder_id
    source_currency = blueprint_source_currency(
        Path(repo_root), generation,
        container_root=container_root, dataset_roots=dataset_roots,
    )
    target_role = role or generation.entry_role
    _require(target_role in generation.role_fibres,
             "blueprint query role is not declared by the current generation",
             role=target_role, declared_roles=sorted(generation.role_fibres))
    target_fibre = generation.role_fibres[target_role]
    transport_event_id = None if store.read_only else _transport_to(
        store,
        generation.assumption,
        target_fibre,
        metadata,
        operator="blueprint-query-jurisdiction/1",
        loss_or_obstruction=(
            f"query enters design role {target_role}; evidence outside this role is omitted "
            "unless separately transported and reconstructed"
        ),
    )
    state = store.replay()
    query = encoder.query(goal)
    check_contract(encoder, [query])
    operator = route_operator or RawCosineRouter()
    role_clusters = tuple(
        cluster for cluster in generation.clusters
        if cluster["design_role"] == target_role
    )
    _require(bool(role_clusters), "blueprint query role has no spectral clusters",
             role=target_role)
    first_spectral = state.graph_objects[role_clusters[0]["spectral_object_id"]]
    grade_axis_contract_id = first_spectral.grade_contract_id
    _require(
        all(
            state.graph_objects[cluster["spectral_object_id"]].grade_contract_id
            == grade_axis_contract_id
            for cluster in role_clusters
        ),
        "blueprint role clusters contradict their grade-axis contract",
        role=target_role,
    )
    cluster_context = RoutingContext(
        generation.assumption,
        target_fibre,
        "cluster",
        grade_axis_contract_id,
        generation.lens_id or "legacy-unspecified",
        route_encoder_version,
    )
    leaf_context = RoutingContext(
        generation.assumption,
        target_fibre,
        "leaf",
        grade_axis_contract_id,
        generation.lens_id or "legacy-unspecified",
        route_encoder_version,
    )
    cluster_by_id = {str(cluster["cluster_id"]): cluster for cluster in role_clusters}
    cluster_scores = operator.rank(
        query,
        tuple(
            RouteCandidate(
                str(cluster["cluster_id"]),
                tuple(state.graph_objects[cluster["spectral_object_id"]].attributes["centroid"]),
            )
            for cluster in role_clusters
        ),
        cluster_context,
    )
    scored_clusters = [
        (score.score, cluster_by_id[score.candidate_id]) for score in cluster_scores
    ]
    keep = scored_clusters[:max(1, min(beam, len(scored_clusters)))]
    rejected = scored_clusters[len(keep):]
    role_clauses = tuple(
        clause for clause in generation.clauses
        if clause["design_role"] == target_role
    )
    clause_by_logical = {item["logical_id"]: item for item in role_clauses}
    candidate_items: dict[str, tuple[Mapping[str, Any], ConceptricObject]] = {}
    for _score, cluster in keep:
        for logical_id in cluster["member_logical_ids"]:
            clause = clause_by_logical[logical_id]
            item = state.graph_objects[clause["object_id"]]
            candidate_items[str(logical_id)] = (clause, item)
    leaf_scores = operator.rank(
        query,
        tuple(
            RouteCandidate(logical_id, tuple(item.attributes["vector"]))
            for logical_id, (_clause, item) in candidate_items.items()
        ),
        leaf_context,
    )
    candidate_rows = [
        (score.score, *candidate_items[score.candidate_id]) for score in leaf_scores
    ]
    selected = candidate_rows[:top_k]
    results: list[dict[str, Any]] = []
    binding_by_edge = {
        str(binding["edge_id"]): binding for binding in generation.bindings
    }
    finding_by_id = {
        str(finding["finding_id"]): finding for finding in generation.findings
    }
    for score, clause, item in selected:
        banked_text = item.attributes.get("text")
        _require(isinstance(banked_text, str),
                 "blueprint clause has no banked text; re-pour its owning design corpus",
                 object_id=item.object_id, source_path=clause["source_path"])
        implementation_links = []
        for edge in state.graph_edges.values():
            if edge.relation != "implements" or edge.target_object_id != clause["object_id"]:
                continue
            binding = binding_by_edge.get(edge.edge_id)
            if binding is None:
                # The graph is immutable history.  A reconstruction of one
                # generation may expose only the bindings completed by that
                # generation, even when an unchanged clause has historical
                # implementation versions incident on it.
                continue
            implementation = state.graph_objects[edge.source_object_id]
            required_finding_ids = tuple(binding.get("required_finding_ids", ()))
            implementation_links.append({
                "edge_id": edge.edge_id,
                "implementation_object_id": implementation.object_id,
                "implementation_path": implementation.attributes["source_path"],
                "implementation_hash": implementation.attributes["source_hash"],
                "proof_state": edge.residual.note,
                "evidence_state": edge.residual.status.value,
                "implementation_scope": binding.get(
                    "implementation_scope", "entire-clause"
                ),
                "operator_roles": list(binding.get("operator_roles", ())),
                "required_findings": [
                    {
                        "finding_id": finding_id,
                        "object_id": finding_by_id[finding_id]["object_id"],
                        "relation": finding_by_id[finding_id]["relation"],
                        "evidence_state": finding_by_id[finding_id]["evidence_state"],
                        "source_path": finding_by_id[finding_id]["source_path"],
                        "start": finding_by_id[finding_id]["start"],
                        "end": finding_by_id[finding_id]["end"],
                        "proof_scope": finding_by_id[finding_id]["proof_scope"],
                    }
                    for finding_id in required_finding_ids
                    if finding_id in finding_by_id
                ],
            })
        results.append({
            "score": score,
            "logical_id": clause["logical_id"],
            "subject_id": clause["subject_id"],
            "subject_handle": clause["subject_handle"],
            "version_edge_id": clause["version_edge_id"],
            "object_id": clause["object_id"],
            "content_handle": clause["content_handle"],
            "exact_byte_hash": clause["exact_byte_hash"],
            "source_path": clause["source_path"],
            "source_hash": clause["source_hash"],
            "start": clause["start"],
            "end": clause["end"],
            "trail": clause["trail"],
            "source_kind": clause.get("source_kind", "source"),
            **({"typed_row_id": clause["typed_row_id"],
                "typed_row_id_field": clause["typed_row_id_field"]}
               if "typed_row_id" in clause else {}),
            "design_role": clause["design_role"],
            "fibre": clause["fibre"],
            "text": banked_text,
            "implements": implementation_links,
        })
    coverage = len(candidate_rows) / len(role_clauses)
    result_handles = tuple(item[2].content_handle for item in selected)
    role_pour = generation.fibre_pours[target_role]
    operator_identity = (
        f"operator={operator.operator_version};metric={operator.metric_version};"
        f"encoder={route_encoder_version};lens={generation.lens_id or 'legacy-unspecified'};"
        f"batch_policy={generation.embedding_batch_policy}"
    )
    retrieval_law = f"{RETRIEVAL_LAW};{operator_identity}"
    materialization = MaterializedReconstruction(
        materialization_id=chash({
            "schema_version": "atlas.blueprint-materialization/1",
            "goal": goal,
            "generation_id": generation.generation_id,
            "retrieval_law": retrieval_law,
            "result_handles": list(result_handles),
        }),
        goal=goal,
        assumption=generation.assumption,
        fibre=target_fibre,
        retrieval_law=retrieval_law,
        corpus_roots=generation.source_roots,
        start_handle=role_pour["pour_handle"],
        # Cluster-selection receipts are observations, not typed reconstruction Movement
        # objects.  Do not launder their event ids into the movement ledger.
        movement_ids=(),
        result_handles=result_handles,
        dependency_frontier=generation.source_roots,
        residual=Residual(
            ResidualStatus.UNKNOWN,
            None,
            None,
            "goal-closure",
            "unplanted blueprint goal has ranked evidence but no oracle closure claim",
        ),
        coverage=coverage,
    )
    previous = state.materializations.get(materialization.cache_key)
    cache_hit = previous is not None and \
        previous.dependency_frontier == generation.source_roots and \
        previous.start_handle == role_pour["pour_handle"]
    if not cache_hit and not store.read_only:
        route_payload = {
            "schema_version": BLUEPRINT_ROUTE_SCHEMA,
            "materialization_id": materialization.materialization_id,
            "generation_id": generation.generation_id,
            "goal": goal,
            "encoder_id": encoder.encoder_id,
            "encoder_spec_id": route_encoder_version,
            "lens_id": generation.lens_id or "legacy-unspecified",
            "design_role": target_role,
            "fibre": target_fibre,
            "router": {
                "selection_pipeline": "centroid-then-leaf/1",
                "operator": operator.operator_version,
                "metric": operator.metric_version,
                "direction": operator.direction,
                "frame_usage": "not-used",
                "stages": [
                    operator.receipt(cluster_context).to_dict(),
                    operator.receipt(leaf_context).to_dict(),
                ],
            },
            "transport_event_id": transport_event_id,
            "traversed": [
                {"cluster_id": item[1]["cluster_id"], "score": item[0]} for item in keep
            ],
            "rejected": [
                {"cluster_id": item[1]["cluster_id"], "score": item[0]} for item in rejected
            ],
            "result_object_ids": [item[1]["object_id"] for item in selected],
            "dependency_frontier": dict(generation.source_roots),
            "source_currency": source_currency,
            "coverage": coverage,
        }
        route_event = _event(
            metadata,
            EventKind.OBSERVATION,
            route_payload,
            subject=f"route:{materialization.materialization_id}",
            assumption=materialization.assumption,
            fibre=materialization.fibre,
            residual=materialization.residual,
            causation_ids=(
                generation.pour_observation_event_id,
                *((transport_event_id,) if transport_event_id else ()),
            ),
        )
        materialization_event = _event(
            metadata,
            EventKind.MATERIALIZATION,
            materialization.to_dict(),
            subject=materialization.materialization_id,
            assumption=materialization.assumption,
            fibre=materialization.fibre,
            residual=materialization.residual,
            causation_ids=(route_event.event_id,),
        )
        store.append_many((route_event, materialization_event))
    elif cache_hit:
        materialization = previous
    return BlueprintReconstruction(
        generation.generation_id,
        materialization.materialization_id,
        cache_hit,
        tuple(item[1]["cluster_id"] for item in keep),
        tuple(item[1]["cluster_id"] for item in rejected),
        tuple(results),
        coverage,
        generation.source_roots,
        source_currency,
    )


__all__ = [
    "BlueprintGeneration",
    "BlueprintReconstruction",
    "DesignDocument",
    "ImplementationBinding",
    "current_blueprint_generation",
    "blueprint_source_currency",
    "pour_blueprint",
    "reconstruct_blueprint",
]
