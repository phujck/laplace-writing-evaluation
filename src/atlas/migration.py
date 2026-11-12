"""Durable migration-critical-path state carried by the canonical Atlas history.

This module is deliberately a schema and a small adapter, not another store.  Every declaration
and transition is a ``ConceptricObject`` inside an ``AtlasEvent`` appended through
``ConceptricStore.append``.  Replaying a fresh store therefore reconstructs the migration state
without consulting a campaign ledger, Markdown render, or process-local cache.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, ClassVar, Mapping

from .errors import SchemaFieldMissing, SchemaVersionMismatch, StateTransitionRefused
from .history import (
    AtlasEvent,
    ConceptricObject,
    EventKind,
    ProducerRef,
    Residual,
    ResidualStatus,
    RuntimeReceipt,
    SeatRole,
    SourceRef,
    Validity,
)
from .ids import chash
from .state import CONTROL_AXIS_CONTRACT
from .store import ConceptricStore, StoredEvent

ATLAS_MIGRATION_STAGES = tuple(f"ATLAS-S{number}" for number in range(6))
STAGE_RECORD_DISCRIMINATOR = "stage"
STAGE_OBJECT_KIND = "atlas-migration-stage-state"


class MigrationStatus(str, Enum):
    OPEN = "OPEN"
    MATERIAL = "MATERIAL"
    DONE_PENDING_WALK = "DONE-PENDING-WALK"
    ACCEPTED = "ACCEPTED"
    SUPERSEDED = "SUPERSEDED"


def _require_exact(raw: Mapping[str, Any], keys: tuple[str, ...], where: str) -> None:
    expected = {"schema_version", *keys}
    missing = sorted(expected - set(raw))
    extra = sorted(set(raw) - expected)
    if missing or extra:
        raise SchemaFieldMissing(
            f"{where} fields do not match its schema",
            fields=missing,
            unexpected=extra,
        )


@dataclass(frozen=True)
class MigrationStage:
    """One immutable observation of one fixed Atlas migration stage.

    ``material``, ``judged`` and ``walked`` are deliberately separate booleans.  In particular,
    a judge run cannot silently stand in for the author's walk, and a walk cannot manufacture a
    judge result.  Evidence may only accumulate across revisions.
    """

    SCHEMA_VERSION: ClassVar[str] = "atlas-migration-stage/2"
    LEGACY_SCHEMA_VERSION: ClassVar[str] = "atlas-migration-stage/1"

    stage_id: str
    revision: int = 0
    material: bool = False
    judged: bool = False
    walked: bool = False
    superseded_by: str | None = None

    def __post_init__(self) -> None:
        if self.stage_id not in ATLAS_MIGRATION_STAGES:
            raise StateTransitionRefused(
                "migration stage id is outside the fixed ATLAS-S0..S5 programme",
                stage_id=self.stage_id,
            )
        if isinstance(self.revision, bool) or not isinstance(self.revision, int) or self.revision < 0:
            raise StateTransitionRefused(
                "migration stage revision must be a non-negative integer",
                stage_id=self.stage_id,
                revision=self.revision,
            )
        for field_name in ("material", "judged", "walked"):
            if not isinstance(getattr(self, field_name), bool):
                raise StateTransitionRefused(
                    "migration evidence state must be boolean",
                    stage_id=self.stage_id,
                    field=field_name,
                )
        if self.superseded_by is not None:
            if self.superseded_by not in ATLAS_MIGRATION_STAGES:
                raise StateTransitionRefused(
                    "migration supersession must name a fixed Atlas stage",
                    stage_id=self.stage_id,
                    superseded_by=self.superseded_by,
                )
            if self.superseded_by == self.stage_id:
                raise StateTransitionRefused(
                    "migration stage cannot supersede itself", stage_id=self.stage_id
                )

    def to_dict(self, *, schema_version: str | None = None) -> dict[str, Any]:
        version = schema_version or self.SCHEMA_VERSION
        if version not in {self.LEGACY_SCHEMA_VERSION, self.SCHEMA_VERSION}:
            raise SchemaVersionMismatch(
                "MigrationStage cannot serialize an unknown schema version",
                expected=self.SCHEMA_VERSION,
                got=version,
            )
        result = {
            "schema_version": version,
            "record": STAGE_RECORD_DISCRIMINATOR,
            "stage_id": self.stage_id,
            "revision": self.revision,
            "material": self.material,
            "judged": self.judged,
            "walked": self.walked,
            "superseded_by": self.superseded_by,
        }
        if version == self.SCHEMA_VERSION:
            result["status"] = self.status.value
        return result

    @property
    def status(self) -> MigrationStatus:
        if self.superseded_by is not None:
            return MigrationStatus.SUPERSEDED
        if self.material and self.judged and self.walked:
            return MigrationStatus.ACCEPTED
        if self.material and self.judged:
            return MigrationStatus.DONE_PENDING_WALK
        if self.material:
            return MigrationStatus.MATERIAL
        return MigrationStatus.OPEN

    @property
    def ready_for_next(self) -> bool:
        """The programme may advance once material and judge agree; his walk stays his."""

        return self.material and self.judged

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "MigrationStage":
        version = raw.get("schema_version")
        if version not in {cls.LEGACY_SCHEMA_VERSION, cls.SCHEMA_VERSION}:
            raise SchemaVersionMismatch(
                "MigrationStage carries an unknown schema version",
                expected=cls.SCHEMA_VERSION,
                got=version,
            )
        keys = [
            "record",
            "stage_id",
            "revision",
            "material",
            "judged",
            "walked",
            "superseded_by",
        ]
        if version == cls.SCHEMA_VERSION:
            keys.append("status")
        _require_exact(
            raw,
            tuple(keys),
            "MigrationStage",
        )
        if raw["record"] != STAGE_RECORD_DISCRIMINATOR:
            raise StateTransitionRefused(
                "migration record discriminator is not 'stage'",
                got=raw["record"],
            )
        result = cls(
            stage_id=raw["stage_id"],
            revision=raw["revision"],
            material=raw["material"],
            judged=raw["judged"],
            walked=raw["walked"],
            superseded_by=raw["superseded_by"],
        )
        if version == cls.SCHEMA_VERSION and raw["status"] != result.status.value:
            raise StateTransitionRefused(
                "migration stage status contradicts its evidence axes",
                stage_id=result.stage_id,
                expected=result.status.value,
                got=raw["status"],
            )
        return result


@dataclass(frozen=True)
class MigrationEventContext:
    """The evidence-bearing envelope fields supplied by the acting seat."""

    occurred_at: str
    correlation_id: str
    provenance: tuple[SourceRef, ...]
    residual: Residual
    runtime: RuntimeReceipt
    producer_ref: ProducerRef
    producer: SeatRole = SeatRole.EGO
    actor: SeatRole = SeatRole.EGO


@dataclass(frozen=True)
class MigrationReplay:
    """A deterministic migration projection derived only from canonical events."""

    stages: Mapping[str, MigrationStage]
    event_ids: Mapping[str, str]

    def require_declared(self) -> None:
        missing = [stage_id for stage_id in ATLAS_MIGRATION_STAGES if stage_id not in self.stages]
        if missing:
            raise StateTransitionRefused(
                "canonical migration stage set is incomplete", stage_ids=missing
            )

    @property
    def next_stage(self) -> str | None:
        """First stage not ready for its successor, in the fixed programme order."""

        for stage_id in ATLAS_MIGRATION_STAGES:
            stage = self.stages.get(stage_id)
            if stage is None or not stage.ready_for_next:
                return stage_id
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "atlas-migration-replay/1",
            "next_stage": self.next_stage,
            "stages": {
                stage_id: stage.to_dict()
                for stage_id, stage in self.stages.items()
            },
            "event_ids": dict(self.event_ids),
        }


def _stage_object(
    stage: MigrationStage,
    provenance: tuple[SourceRef, ...],
    *,
    schema_version: str | None = None,
) -> ConceptricObject:
    record = stage.to_dict(schema_version=schema_version)
    digest = chash(record)
    return ConceptricObject(
        object_id=(
            f"migration-stage:{stage.stage_id}:r{stage.revision}:"
            f"{digest.removeprefix('sha256:')}"
        ),
        kind=STAGE_OBJECT_KIND,
        content_handle=digest,
        assumption=None,
        fibre=None,
        grade_contract_id=CONTROL_AXIS_CONTRACT.contract_id,
        grade_coordinate="fabric",
        provenance=provenance,
        attributes=record,
    )


def migration_stage_event(
    stage: MigrationStage,
    context: MigrationEventContext,
    *,
    previous_event_id: str | None,
) -> AtlasEvent:
    """Construct the sole canonical event form accepted by migration replay."""

    item = _stage_object(stage, context.provenance)
    return AtlasEvent.create(
        occurred_at=context.occurred_at,
        kind=EventKind.OBJECT,
        producer=context.producer,
        actor=context.actor,
        subject=f"migration-stage:{stage.stage_id}:r{stage.revision}",
        assumption=None,
        fibre=None,
        correlation_id=context.correlation_id,
        causation_ids=() if previous_event_id is None else (previous_event_id,),
        provenance=context.provenance,
        residual=context.residual,
        runtime=context.runtime,
        producer_ref=context.producer_ref,
        validity=Validity.VALID,
        payload=item.to_dict(),
    )


def replay_migration(store: ConceptricStore) -> MigrationReplay:
    """Replay strict stage records from the store's verified canonical event chain."""

    # ``events`` verifies the hash chain; ``replay`` additionally verifies that the normalized
    # graph is exactly the disposable projection of it.  Migration never trusts only one half.
    store.replay()
    stages: dict[str, MigrationStage] = {}
    event_ids: dict[str, str] = {}
    for event in store.events():
        if event.kind != EventKind.OBJECT or event.validity != Validity.VALID:
            continue
        item = ConceptricObject.from_dict(event.payload)
        if item.kind != STAGE_OBJECT_KIND:
            continue
        stage = MigrationStage.from_dict(item.attributes)
        expected_item = _stage_object(
            stage,
            event.provenance,
            schema_version=str(item.attributes["schema_version"]),
        )
        if item != expected_item:
            raise StateTransitionRefused(
                "migration stage object does not match its canonical identity",
                stage_id=stage.stage_id,
                object_id=item.object_id,
            )
        expected_subject = f"migration-stage:{stage.stage_id}:r{stage.revision}"
        if event.subject != expected_subject:
            raise StateTransitionRefused(
                "migration event subject contradicts its stage revision",
                stage_id=stage.stage_id,
                expected=expected_subject,
                got=event.subject,
            )
        previous = stages.get(stage.stage_id)
        previous_event_id = event_ids.get(stage.stage_id)
        if previous is None:
            if stage.revision != 0 or event.causation_ids:
                raise StateTransitionRefused(
                    "migration stage declaration must begin at revision zero without a cause",
                    stage_id=stage.stage_id,
                )
        else:
            if stage.revision != previous.revision + 1:
                raise StateTransitionRefused(
                    "migration stage revisions must be contiguous",
                    stage_id=stage.stage_id,
                    expected=previous.revision + 1,
                    got=stage.revision,
                )
            if event.causation_ids != (previous_event_id,):
                raise StateTransitionRefused(
                    "migration transition must causally cite the prior stage revision",
                    stage_id=stage.stage_id,
                    expected=previous_event_id,
                    got=list(event.causation_ids),
                )
            for field_name in ("material", "judged", "walked"):
                if getattr(previous, field_name) and not getattr(stage, field_name):
                    raise StateTransitionRefused(
                        "migration evidence cannot be withdrawn",
                        stage_id=stage.stage_id,
                        field=field_name,
                    )
            changed = tuple(
                field_name
                for field_name in ("material", "judged", "walked")
                if getattr(previous, field_name) != getattr(stage, field_name)
            )
            supersession_changed = previous.superseded_by != stage.superseded_by
            if not changed and not supersession_changed:
                raise StateTransitionRefused(
                    "migration transition cannot be a no-op revision",
                    stage_id=stage.stage_id,
                )
            if "walked" in changed and stage.walked and event.actor != SeatRole.AUTHOR:
                raise StateTransitionRefused(
                    "only the author may bank the migration walk",
                    stage_id=stage.stage_id,
                    actor=event.actor.value,
                )
            if (
                "judged" in changed
                and stage.judged
                and event.residual.status == ResidualStatus.UNKNOWN
            ):
                raise StateTransitionRefused(
                    "judged migration progress requires a measured residual",
                    stage_id=stage.stage_id,
                )
            stage_index = ATLAS_MIGRATION_STAGES.index(stage.stage_id)
            if "material" in changed and stage.material and stage_index > 0:
                prerequisite_id = ATLAS_MIGRATION_STAGES[stage_index - 1]
                prerequisite = stages.get(prerequisite_id)
                if prerequisite is None or not prerequisite.ready_for_next:
                    raise StateTransitionRefused(
                        "migration material cannot outrun the prior stage's judged gate",
                        stage_id=stage.stage_id,
                        prerequisite=prerequisite_id,
                    )
            if previous.superseded_by is not None and stage.superseded_by != previous.superseded_by:
                raise StateTransitionRefused(
                    "migration supersession cannot be withdrawn or redirected",
                    stage_id=stage.stage_id,
                    superseded_by=previous.superseded_by,
                )
        stages[stage.stage_id] = stage
        event_ids[stage.stage_id] = event.event_id
    return MigrationReplay(stages=stages, event_ids=event_ids)


class MigrationLedger:
    """Small write/read API over the one canonical ``ConceptricStore``."""

    def __init__(self, store: ConceptricStore) -> None:
        self.store = store

    def replay(self, *, require_complete: bool = True) -> MigrationReplay:
        result = replay_migration(self.store)
        if require_complete:
            result.require_declared()
        return result

    def declare_all(self, context: MigrationEventContext) -> MigrationReplay:
        """Declare exactly ATLAS-S0..S5; safe to call again after a complete declaration."""

        current = replay_migration(self.store)
        for stage_id in ATLAS_MIGRATION_STAGES:
            if stage_id in current.stages:
                continue
            event = migration_stage_event(
                MigrationStage(stage_id), context, previous_event_id=None
            )
            self.store.append(event)
        return self.replay()

    def set_progress(
        self,
        stage_id: str,
        context: MigrationEventContext,
        *,
        material: bool | None = None,
        judged: bool | None = None,
        walked: bool | None = None,
    ) -> StoredEvent:
        """Append one revision while leaving every unspecified evidence axis unchanged."""

        current = self.replay()
        if stage_id not in current.stages:
            raise StateTransitionRefused(
                "migration progress requires a declared fixed stage", stage_id=stage_id
            )
        prior = current.stages[stage_id]
        updated = replace(
            prior,
            revision=prior.revision + 1,
            material=prior.material if material is None else material,
            judged=prior.judged if judged is None else judged,
            walked=prior.walked if walked is None else walked,
        )
        for field_name in ("material", "judged", "walked"):
            if getattr(prior, field_name) and not getattr(updated, field_name):
                raise StateTransitionRefused(
                    "migration evidence cannot be withdrawn",
                    stage_id=stage_id,
                    field=field_name,
                )
        changed = tuple(
            field_name
            for field_name in ("material", "judged", "walked")
            if getattr(prior, field_name) != getattr(updated, field_name)
        )
        if not changed:
            raise StateTransitionRefused(
                "migration progress cannot append a no-op revision",
                stage_id=stage_id,
            )
        if "walked" in changed and updated.walked and context.actor != SeatRole.AUTHOR:
            raise StateTransitionRefused(
                "only the author may bank the migration walk",
                stage_id=stage_id,
                actor=context.actor.value,
            )
        if "judged" in changed and updated.judged and context.residual.status.value == "unknown":
            raise StateTransitionRefused(
                "judged migration progress requires a measured residual",
                stage_id=stage_id,
            )
        stage_index = ATLAS_MIGRATION_STAGES.index(stage_id)
        if "material" in changed and updated.material and stage_index > 0:
            prerequisite_id = ATLAS_MIGRATION_STAGES[stage_index - 1]
            prerequisite = current.stages[prerequisite_id]
            if not prerequisite.ready_for_next:
                raise StateTransitionRefused(
                    "migration material cannot outrun the prior stage's judged gate",
                    stage_id=stage_id,
                    prerequisite=prerequisite_id,
                    prerequisite_status=prerequisite.status.value,
                )
        event = migration_stage_event(
            updated,
            context,
            previous_event_id=current.event_ids[stage_id],
        )
        return self.store.append(event)

    def supersede(
        self,
        stage_id: str,
        superseded_by: str,
        context: MigrationEventContext,
    ) -> StoredEvent:
        """Append an explicit, immutable replacement relation for one declared stage."""

        current = self.replay()
        if stage_id not in current.stages:
            raise StateTransitionRefused(
                "migration supersession requires a declared fixed stage", stage_id=stage_id
            )
        prior = current.stages[stage_id]
        if prior.superseded_by == superseded_by:
            raise StateTransitionRefused(
                "migration supersession is already banked",
                stage_id=stage_id,
                superseded_by=superseded_by,
            )
        if prior.superseded_by is not None and prior.superseded_by != superseded_by:
            raise StateTransitionRefused(
                "migration supersession cannot be redirected",
                stage_id=stage_id,
                superseded_by=prior.superseded_by,
            )
        updated = replace(
            prior,
            revision=prior.revision + 1,
            superseded_by=superseded_by,
        )
        event = migration_stage_event(
            updated,
            context,
            previous_event_id=current.event_ids[stage_id],
        )
        return self.store.append(event)


__all__ = [
    "ATLAS_MIGRATION_STAGES",
    "MigrationEventContext",
    "MigrationLedger",
    "MigrationReplay",
    "MigrationStage",
    "MigrationStatus",
    "STAGE_OBJECT_KIND",
    "STAGE_RECORD_DISCRIMINATOR",
    "migration_stage_event",
    "replay_migration",
]
