from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from atlas.errors import SchemaFieldMissing, StateTransitionRefused
from atlas.history import (
    AtlasEvent,
    ConceptricObject,
    EventKind,
    LifecycleAction,
    LifecyclePhase,
    LifecycleTransition,
    ProducerRef,
    Residual,
    ResidualStatus,
    SeatRole,
    SourceRef,
    Validity,
)
from atlas.migration import (
    ATLAS_MIGRATION_STAGES,
    STAGE_OBJECT_KIND,
    MigrationEventContext,
    MigrationLedger,
    MigrationStage,
    MigrationStatus,
    _stage_object,
    migration_stage_event,
    replay_migration,
)
from atlas.runtime import collect_runtime_receipt
from atlas.store import ConceptricStore

ROOT = Path(__file__).resolve().parents[2]
SOURCE = SourceRef(
    "atlas-migration-test",
    "sha256:" + ("d" * 64),
    "test://atlas-migration",
)
RESIDUAL = Residual(
    ResidualStatus.WITHIN_BOUND,
    0.0,
    0.0,
    "schema-violations",
    "strict migration-state test",
)
RUNTIME = collect_runtime_receipt(ROOT, observed_at="2026-08-24T18:00:00Z")
PRODUCER = ProducerRef("pytest", "deterministic", "test")
CONTEXT = MigrationEventContext(
    occurred_at="2026-08-24T18:00:00Z",
    correlation_id="migration-test",
    provenance=(SOURCE,),
    residual=RESIDUAL,
    runtime=RUNTIME,
    producer_ref=PRODUCER,
)
AUTHOR_CONTEXT = replace(CONTEXT, actor=SeatRole.AUTHOR)


def _wake() -> AtlasEvent:
    return AtlasEvent.create(
        occurred_at=CONTEXT.occurred_at,
        kind=EventKind.LIFECYCLE,
        producer=SeatRole.SYSTEM,
        actor=SeatRole.SYSTEM,
        subject="lifecycle:migration-test",
        assumption=None,
        fibre=None,
        correlation_id=CONTEXT.correlation_id,
        causation_ids=(),
        provenance=(SOURCE,),
        residual=RESIDUAL,
        runtime=RUNTIME,
        producer_ref=PRODUCER,
        validity=Validity.VALID,
        payload=LifecycleTransition(
            LifecycleAction.COLD_WAKE,
            LifecyclePhase.SLEEPING,
            LifecyclePhase.AWAKE,
            "cold:migration-test",
        ).to_dict(),
    )


def _store(path: Path) -> ConceptricStore:
    store = ConceptricStore(path)
    store.append(_wake())
    return store


def test_stage_schema_requires_the_discriminator() -> None:
    raw = MigrationStage("ATLAS-S0").to_dict()
    del raw["record"]
    with pytest.raises(SchemaFieldMissing) as caught:
        MigrationStage.from_dict(raw)
    assert caught.value.detail["fields"] == ["record"]


def test_legacy_v1_stage_remains_identity_verifiable_after_v2_status_field(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path / "conceptric")
    stage = MigrationStage("ATLAS-S0")
    legacy_item = _stage_object(
        stage,
        (SOURCE,),
        schema_version=MigrationStage.LEGACY_SCHEMA_VERSION,
    )
    legacy_event = AtlasEvent.create(
        occurred_at=CONTEXT.occurred_at,
        kind=EventKind.OBJECT,
        producer=SeatRole.EGO,
        actor=SeatRole.EGO,
        subject="migration-stage:ATLAS-S0:r0",
        assumption=None,
        fibre=None,
        correlation_id=CONTEXT.correlation_id,
        causation_ids=(),
        provenance=(SOURCE,),
        residual=RESIDUAL,
        runtime=RUNTIME,
        producer_ref=PRODUCER,
        validity=Validity.VALID,
        payload=legacy_item.to_dict(),
    )
    store.append(legacy_event)

    replayed = replay_migration(store)
    assert replayed.stages["ATLAS-S0"] == stage
    assert legacy_item.attributes["schema_version"] == "atlas-migration-stage/1"
    assert "status" not in legacy_item.attributes


def test_all_fixed_stage_identities_survive_fresh_store_replay(tmp_path: Path) -> None:
    root = tmp_path / "conceptric"
    ledger = MigrationLedger(_store(root))
    declared = ledger.declare_all(CONTEXT)

    assert tuple(declared.stages) == ATLAS_MIGRATION_STAGES
    assert all(stage.revision == 0 for stage in declared.stages.values())
    assert all(not stage.material for stage in declared.stages.values())
    assert all(stage.status == MigrationStatus.OPEN for stage in declared.stages.values())
    assert declared.next_stage == "ATLAS-S0"

    # A new store instance has no process-local migration state to inherit.
    fresh = MigrationLedger(ConceptricStore(root)).replay()
    assert fresh == declared
    assert len(ConceptricStore(root).events()) == 1 + len(ATLAS_MIGRATION_STAGES)


def test_material_judged_and_walked_are_independent_durable_axes(tmp_path: Path) -> None:
    root = tmp_path / "conceptric"
    ledger = MigrationLedger(_store(root))
    ledger.declare_all(CONTEXT)
    ledger.set_progress("ATLAS-S0", CONTEXT, material=True)
    with pytest.raises(StateTransitionRefused, match="only the author"):
        ledger.set_progress("ATLAS-S0", CONTEXT, walked=True)
    ledger.set_progress("ATLAS-S0", AUTHOR_CONTEXT, walked=True)

    first = MigrationLedger(ConceptricStore(root)).replay().stages["ATLAS-S0"]
    assert (first.material, first.judged, first.walked) == (True, False, True)
    assert first.revision == 2

    ledger.set_progress("ATLAS-S0", CONTEXT, judged=True)
    final = MigrationLedger(ConceptricStore(root)).replay().stages["ATLAS-S0"]
    assert (final.material, final.judged, final.walked) == (True, True, True)
    assert final.revision == 3
    assert final.status == MigrationStatus.ACCEPTED


def test_done_pending_walk_advances_programme_without_claiming_authors_walk(
    tmp_path: Path,
) -> None:
    ledger = MigrationLedger(_store(tmp_path / "conceptric"))
    ledger.declare_all(CONTEXT)

    with pytest.raises(StateTransitionRefused, match="cannot outrun"):
        ledger.set_progress("ATLAS-S1", CONTEXT, material=True)
    ledger.set_progress("ATLAS-S0", CONTEXT, material=True)
    ledger.set_progress("ATLAS-S0", CONTEXT, judged=True)
    replayed = ledger.replay()

    assert replayed.stages["ATLAS-S0"].status == MigrationStatus.DONE_PENDING_WALK
    assert replayed.stages["ATLAS-S0"].walked is False
    assert replayed.next_stage == "ATLAS-S1"
    ledger.set_progress("ATLAS-S1", CONTEXT, material=True)


def test_progress_refuses_noop_revision(tmp_path: Path) -> None:
    store = _store(tmp_path / "conceptric")
    ledger = MigrationLedger(store)
    ledger.declare_all(CONTEXT)
    before = len(store.events())

    with pytest.raises(StateTransitionRefused, match="no-op"):
        ledger.set_progress("ATLAS-S0", CONTEXT)
    assert len(store.events()) == before


def test_supersession_is_explicit_immutable_and_replayed(tmp_path: Path) -> None:
    root = tmp_path / "conceptric"
    ledger = MigrationLedger(_store(root))
    ledger.declare_all(CONTEXT)
    prior_event_id = ledger.replay().event_ids["ATLAS-S0"]
    supersession = ledger.supersede("ATLAS-S0", "ATLAS-S1", CONTEXT)

    fresh = MigrationLedger(ConceptricStore(root)).replay()
    assert fresh.stages["ATLAS-S0"].superseded_by == "ATLAS-S1"
    assert supersession.event.causation_ids == (prior_event_id,)
    assert supersession.event.event_id == fresh.event_ids["ATLAS-S0"]
    with pytest.raises(StateTransitionRefused, match="cannot be redirected"):
        ledger.supersede("ATLAS-S0", "ATLAS-S2", CONTEXT)


def test_progress_refuses_to_erase_landed_evidence_before_append(tmp_path: Path) -> None:
    store = _store(tmp_path / "conceptric")
    ledger = MigrationLedger(store)
    ledger.declare_all(CONTEXT)
    ledger.set_progress("ATLAS-S0", CONTEXT, judged=True)
    before = len(store.events())

    with pytest.raises(StateTransitionRefused, match="cannot be withdrawn"):
        ledger.set_progress("ATLAS-S0", CONTEXT, judged=False)
    assert len(store.events()) == before


def test_replay_refuses_recognized_object_without_stage_discriminator(tmp_path: Path) -> None:
    store = _store(tmp_path / "conceptric")
    valid = MigrationStage("ATLAS-S0").to_dict()
    del valid["record"]
    malformed = ConceptricObject(
        object_id="migration-stage:malformed",
        kind=STAGE_OBJECT_KIND,
        content_handle="sha256:" + ("e" * 64),
        assumption=None,
        fibre=None,
        grade_contract_id="axis-contract:atlas-control-topology/1",
        grade_coordinate="fabric",
        provenance=(SOURCE,),
        attributes=valid,
    )
    store.append(
        AtlasEvent.create(
            occurred_at=CONTEXT.occurred_at,
            kind=EventKind.OBJECT,
            producer=SeatRole.EGO,
            actor=SeatRole.EGO,
            subject="migration-stage:malformed",
            assumption=None,
            fibre=None,
            correlation_id=CONTEXT.correlation_id,
            causation_ids=(),
            provenance=(SOURCE,),
            residual=RESIDUAL,
            runtime=RUNTIME,
            producer_ref=PRODUCER,
            validity=Validity.VALID,
            payload=malformed.to_dict(),
        )
    )

    with pytest.raises(SchemaFieldMissing) as caught:
        replay_migration(store)
    assert caught.value.detail["fields"] == ["record"]


def test_replay_refuses_a_forked_stage_lineage(tmp_path: Path) -> None:
    store = _store(tmp_path / "conceptric")
    ledger = MigrationLedger(store)
    ledger.declare_all(CONTEXT)
    declaration = ledger.replay().event_ids["ATLAS-S0"]
    first = ledger.set_progress("ATLAS-S0", CONTEXT, material=True)

    # A generic caller can append a well-formed object event, but migration replay will not
    # accept a second revision that branches from the declaration instead of the live revision.
    fork = migration_stage_event(
        MigrationStage("ATLAS-S0", revision=2, judged=True),
        replace(CONTEXT, correlation_id="migration-fork-test"),
        previous_event_id=declaration,
    )
    store.append(fork)
    assert first.event.event_id != fork.event_id
    with pytest.raises(StateTransitionRefused, match="causally cite"):
        replay_migration(store)


def test_replay_refuses_non_author_walk_even_when_ledger_is_bypassed(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path / "conceptric")
    ledger = MigrationLedger(store)
    current = ledger.declare_all(CONTEXT)
    forged = migration_stage_event(
        MigrationStage("ATLAS-S0", revision=1, walked=True),
        CONTEXT,
        previous_event_id=current.event_ids["ATLAS-S0"],
    )
    store.append(forged)

    with pytest.raises(StateTransitionRefused, match="only the author"):
        replay_migration(store)


def test_replay_refuses_unmeasured_judgment_even_when_ledger_is_bypassed(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path / "conceptric")
    ledger = MigrationLedger(store)
    current = ledger.declare_all(CONTEXT)
    unknown = replace(
        CONTEXT,
        residual=Residual(
            ResidualStatus.UNKNOWN,
            None,
            None,
            "migration-judgment",
            "not measured",
        ),
    )
    forged = migration_stage_event(
        MigrationStage("ATLAS-S0", revision=1, judged=True),
        unknown,
        previous_event_id=current.event_ids["ATLAS-S0"],
    )
    store.append(forged)

    with pytest.raises(StateTransitionRefused, match="measured residual"):
        replay_migration(store)


def test_replay_refuses_stage_material_that_outruns_prior_gate(tmp_path: Path) -> None:
    store = _store(tmp_path / "conceptric")
    ledger = MigrationLedger(store)
    current = ledger.declare_all(CONTEXT)
    forged = migration_stage_event(
        MigrationStage("ATLAS-S1", revision=1, material=True),
        CONTEXT,
        previous_event_id=current.event_ids["ATLAS-S1"],
    )
    store.append(forged)

    with pytest.raises(StateTransitionRefused, match="cannot outrun"):
        replay_migration(store)


def test_replay_refuses_noop_revision_even_when_ledger_is_bypassed(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path / "conceptric")
    ledger = MigrationLedger(store)
    current = ledger.declare_all(CONTEXT)
    forged = migration_stage_event(
        MigrationStage("ATLAS-S0", revision=1),
        CONTEXT,
        previous_event_id=current.event_ids["ATLAS-S0"],
    )
    store.append(forged)

    with pytest.raises(StateTransitionRefused, match="no-op"):
        replay_migration(store)
