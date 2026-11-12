from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from atlas.errors import HistoryChainMismatch, SchemaFieldMissing, StateTransitionRefused
from atlas.history import (
    AcknowledgementDisposition,
    ActPhase,
    AssumptionSelection,
    AtlasEvent,
    BootstrapCrutch,
    BoundaryRef,
    ConceptricEdge,
    ConceptricObject,
    CorpusAct,
    EventKind,
    GradeAxis,
    GradeAxisContract,
    JoinReceipt,
    LeaseCheckinOutcome,
    LeaseDeclarationKind,
    LifecycleAction,
    LifecyclePhase,
    LifecycleTransition,
    MaterializedReconstruction,
    MessageAcknowledgement,
    MessageExpiry,
    MessageForkPreservation,
    MessagePull,
    MessageSupersession,
    MoveDirection,
    Movement,
    PermissionDecision,
    PermissionOutcome,
    PermissionRequest,
    ProducerRef,
    RegionCheckin,
    RegionCheckout,
    RegionForwardClosure,
    RegionPublicationAuthorization,
    RegionPublicationFinalized,
    RegionPublicationPrepared,
    RegionPublicationSignoff,
    ReplEvaluation,
    ReplOperation,
    Residual,
    ResidualStatus,
    RevisionAct,
    SeatAction,
    SeatJoinReceipt,
    SeatMessage,
    SeatOccupancyBinding,
    SeatRole,
    SeatStatus,
    SeatTransition,
    SourceRef,
    TransportReceipt,
    Validity,
    WatchCheckpoint,
    WatcherRegistration,
    WatchSourceKind,
    WatchStatus,
    region_forward_closure_consumption_root,
    region_forward_closure_finalized_projection,
    region_publication_affected_frontier_root,
)
from atlas.ids import chash
from atlas.runtime import collect_runtime_receipt
from atlas.state import (
    BRIDGE_OPERATIONS,
    CONTROL_AXIS_CONTRACT,
    PROVIDER_SCHEMA,
    ConceptricState,
    RegionLeaseState,
    apply_event,
    bootstrap_crutch_retirement,
    effective_region_lease_projection,
    replay,
)
from atlas.store import BlobStore, ConceptricStore

ROOT = Path(__file__).resolve().parents[2]
SOURCE = SourceRef("test-source", "sha256:" + ("a" * 64), "test://source")
RESIDUAL = Residual(
    ResidualStatus.WITHIN_BOUND,
    0.0,
    0.1,
    "fraction",
    "bounded test residual",
)
PRODUCER = ProducerRef("test-provider", "deterministic", "system-test")
RUNTIME = collect_runtime_receipt(ROOT, observed_at="2026-08-24T12:00:00Z")


def event(
    kind: EventKind,
    payload: dict,
    *,
    subject: str | None = None,
    assumption: str | None = None,
    fibre: str | None = None,
    validity: Validity = Validity.VALID,
    runtime=RUNTIME,
    causation_ids: tuple[str, ...] = (),
    actor: SeatRole = SeatRole.EGO,
    provenance: tuple[SourceRef, ...] = (SOURCE,),
) -> AtlasEvent:
    return AtlasEvent.create(
        occurred_at="2026-08-24T12:00:00Z",
        kind=kind,
        producer=SeatRole.EGO,
        actor=actor,
        subject=subject or kind.value,
        assumption=assumption,
        fibre=fibre,
        correlation_id="correlation-1",
        causation_ids=causation_ids,
        provenance=provenance,
        residual=RESIDUAL,
        runtime=runtime,
        producer_ref=PRODUCER,
        validity=validity,
        payload=payload,
    )


def legacy_supersession_payload(
    supersession: MessageSupersession,
) -> dict[str, object]:
    """Encode the immutable v1 reducer fixture without granting it current write authority."""

    payload = supersession.to_dict()
    payload["schema_version"] = MessageSupersession.LEGACY_V1_SCHEMA_VERSION
    for key in (
        "provider_session_ref",
        "provider_identity_proof_handle",
        "provider_identity_generation",
    ):
        payload.pop(key)
    return payload


def lifecycle(action: LifecycleAction, receipt_id: str) -> AtlasEvent:
    endpoints = {
        LifecycleAction.WAKE: (LifecyclePhase.SLEEPING, LifecyclePhase.AWAKE),
        LifecycleAction.COLD_WAKE: (LifecyclePhase.SLEEPING, LifecyclePhase.AWAKE),
        LifecycleAction.SEW_UP: (LifecyclePhase.AWAKE, LifecyclePhase.SEWING_UP),
        LifecycleAction.SLEEP: (LifecyclePhase.SEWING_UP, LifecyclePhase.SLEEPING),
    }
    start, end = endpoints[action]
    return event(
        EventKind.LIFECYCLE,
        LifecycleTransition(action, start, end, receipt_id).to_dict(),
        subject=f"lifecycle:{receipt_id}",
    )


def seat(seat_id: str, role: SeatRole) -> AtlasEvent:
    return event(
        EventKind.SEAT,
        SeatTransition(
            seat_id,
            role,
            SeatAction.FOUND,
            None,
            SeatStatus.ACTIVE,
            f"charter:{role.value}",
            f"holder:{seat_id}:1",
        ).to_dict(),
        subject=f"seat:{seat_id}",
    )


def awake_state(*, with_seats: bool = False) -> ConceptricState:
    state = apply_event(ConceptricState(), lifecycle(LifecycleAction.COLD_WAKE, "cold-1"))
    if with_seats:
        state = apply_event(state, seat("ego-seat", SeatRole.EGO))
        state = apply_event(state, seat("provider-seat", SeatRole.PROVIDER))
    return state


def select_assumption(state: ConceptricState) -> ConceptricState:
    selection = AssumptionSelection("lawful-assumption", "fibre-a", 0.9, ("alternative",))
    return apply_event(
        state,
        event(
            EventKind.ASSUMPTION,
            selection.to_dict(),
            assumption=selection.assumption,
            fibre=selection.fibre,
        ),
    )


def declare_source_detail_axis(state: ConceptricState) -> ConceptricState:
    contract = GradeAxisContract(
        "axis-contract:source-detail/1",
        "source-detail",
        ("handle", 1, 2, "source-bytes"),
    )
    return apply_event(
        state,
        event(EventKind.GRADE_AXIS, contract.to_dict(), subject=contract.contract_id),
    )


def watcher(
    state: ConceptricState,
    *,
    watcher_id: str = "watcher-1",
    target_seat_id: str = "provider-seat",
    one_shot: bool = True,
    expires_at: str = "2026-08-24T14:00:00Z",
) -> tuple[WatcherRegistration, AtlasEvent]:
    registration = WatcherRegistration(
        watcher_id,
        "ego-seat",
        target_seat_id,
        WatchSourceKind.CONCEPTRIC_EVENTS,
        {"event_kind": EventKind.OBSERVATION.value},
        "watch-trigger",
        one_shot,
        1.0,
        state.event_count,
        expires_at,
    )
    return registration, event(
        EventKind.WATCHER,
        registration.to_dict(),
        assumption="lawful-assumption",
        fibre="fibre-a",
        actor=SeatRole.EGO,
    )


def watcher_message(
    state: ConceptricState,
    *,
    message_id: str = "message:watcher-1",
    sender_seat_id: str = "ego-seat",
    recipient_seat_id: str = "provider-seat",
    message_type: str = "watch-trigger",
    cause: str,
) -> AtlasEvent:
    message = SeatMessage(
        message_id,
        sender_seat_id,
        recipient_seat_id,
        message_type,
        "handle:watch-result",
        {"matched-event": cause},
        f"idempotency:{message_id}",
        state.event_count + 1,
        "2026-08-24T14:00:00Z",
    )
    sender_role = state.seats[sender_seat_id].role
    return event(
        EventKind.MESSAGE,
        message.to_dict(),
        assumption="lawful-assumption",
        fibre="fibre-a",
        actor=SeatRole(sender_role),
        causation_ids=(cause,),
    )


def test_lifecycle_and_seat_succession_are_first_class() -> None:
    wake = lifecycle(LifecycleAction.WAKE, "wake-1")
    founded = seat("ego-seat", SeatRole.EGO)
    relay = event(
        EventKind.SEAT,
        SeatTransition(
            "ego-seat",
            SeatRole.EGO,
            SeatAction.RELAY,
            SeatStatus.ACTIVE,
            SeatStatus.RELAYING,
            "charter:ego",
            "holder:ego-seat:1",
        ).to_dict(),
    )
    activate = event(
        EventKind.SEAT,
        SeatTransition(
            "ego-seat",
            SeatRole.EGO,
            SeatAction.ACTIVATE,
            SeatStatus.RELAYING,
            SeatStatus.ACTIVE,
            "charter:ego",
            "holder:ego-seat:2",
        ).to_dict(),
    )
    sewed = lifecycle(LifecycleAction.SEW_UP, "sew-1")
    slept = lifecycle(LifecycleAction.SLEEP, "sleep-1")

    state = replay((wake, founded, relay, activate, sewed, slept))

    assert state.lifecycle == LifecyclePhase.SLEEPING
    assert state.seats["ego-seat"].status == SeatStatus.ACTIVE
    assert state.seats["ego-seat"].holder_ref == "holder:ego-seat:2"
    with pytest.raises(StateTransitionRefused, match="sleeping conceptric"):
        apply_event(state, founded)


def test_seat_join_records_observational_occupancy_without_rewriting_registration() -> None:
    state = select_assumption(awake_state(with_seats=True))
    proof_handle = "sha256:" + ("b" * 64)
    joined = SeatJoinReceipt(
        seat_id="provider-seat",
        holder_ref="codex:thread-interface",
        function=SeatRole.SENSORIUM,
        registered_role=SeatRole.PROVIDER,
        registered_holder_ref="holder:provider-seat:1",
        mail_state="MAIL_READY",
        information_proof_handle=proof_handle,
        information_cursor=state.event_count,
        delivered_message_ids=(),
        reconstruction_event_ids=(),
        defects=("FUNCTION_MISMATCH:registered=provider:claimed=sensorium",),
    )
    joined_event = event(
        EventKind.SEAT_JOIN,
        joined.to_dict(),
        subject="seat:provider-seat:occupancy",
        assumption="lawful-assumption",
        fibre="fibre-a",
        actor=SeatRole.SENSORIUM,
        provenance=(SourceRef("gate-proof", proof_handle, f"blob:{proof_handle}"),),
    )

    state = apply_event(state, joined_event)
    snapshot = state.provider_snapshot()

    assert snapshot["seats"]["provider-seat"]["holder_ref"] == "holder:provider-seat:1"
    occupancy = snapshot["seat_occupancy"]["provider-seat"]
    assert occupancy["state"] == "OBSERVED"
    assert occupancy["routing_authority"] is False
    assert occupancy["join"]["holder_ref"] == "codex:thread-interface"
    assert occupancy["function_matches_registration"] is False
    assert occupancy["holder_matches_registration"] is False


def test_seat_join_cannot_claim_a_future_information_cursor() -> None:
    state = select_assumption(awake_state(with_seats=True))
    proof_handle = "sha256:" + ("b" * 64)
    joined = SeatJoinReceipt(
        seat_id="provider-seat",
        holder_ref="holder:provider-seat:1",
        function=SeatRole.PROVIDER,
        registered_role=SeatRole.PROVIDER,
        registered_holder_ref="holder:provider-seat:1",
        mail_state="MAIL_READY",
        information_proof_handle=proof_handle,
        information_cursor=state.event_count + 1,
        delivered_message_ids=(),
        reconstruction_event_ids=(),
    )
    with pytest.raises(StateTransitionRefused, match="ahead of Atlas"):
        apply_event(
            state,
            event(
                EventKind.SEAT_JOIN,
                joined.to_dict(),
                subject="seat:provider-seat:occupancy",
                assumption="lawful-assumption",
                fibre="fibre-a",
                actor=SeatRole.PROVIDER,
                provenance=(SourceRef("gate-proof", proof_handle, f"blob:{proof_handle}"),),
            ),
        )


def _joined_provider_state() -> tuple[ConceptricState, AtlasEvent, AtlasEvent]:
    state = select_assumption(awake_state(with_seats=True))
    proof_handle = "sha256:" + ("b" * 64)
    joined = SeatJoinReceipt(
        seat_id="provider-seat",
        holder_ref="codex:thread-interface",
        function=SeatRole.PROVIDER,
        registered_role=SeatRole.PROVIDER,
        registered_holder_ref="holder:provider-seat:1",
        mail_state="MAIL_READY",
        information_proof_handle=proof_handle,
        information_cursor=state.event_count,
        delivered_message_ids=(),
        reconstruction_event_ids=(),
        provider_identity_generation="lease:thread-interface:1",
    )
    joined_event = event(
        EventKind.SEAT_JOIN,
        joined.to_dict(),
        subject="seat:provider-seat:occupancy",
        assumption="lawful-assumption",
        fibre="fibre-a",
        actor=SeatRole.PROVIDER,
        provenance=(SourceRef("gate-proof", proof_handle, f"blob:{proof_handle}"),),
    )
    state = apply_event(state, joined_event)
    binding = SeatOccupancyBinding(
        seat_id="provider-seat",
        registered_seat_event_id=state.seat_registration_event_ids["provider-seat"],
        join_event_id=joined_event.event_id,
        registered_principal_ref="holder:provider-seat:1",
        provider_session_ref="codex:thread-interface",
        function=SeatRole.PROVIDER,
        provider_identity_proof_handle=proof_handle,
        provider_identity_generation="lease:thread-interface:1",
    )
    binding_event = event(
        EventKind.SEAT_OCCUPANCY_BINDING,
        binding.to_dict(),
        subject="seat:provider-seat:binding",
        assumption="lawful-assumption",
        fibre="fibre-a",
        actor=SeatRole.PROVIDER,
        causation_ids=(
            state.seat_registration_event_ids["provider-seat"],
            joined_event.event_id,
        ),
        provenance=(SourceRef("gate-proof", proof_handle, f"blob:{proof_handle}"),),
    )
    return apply_event(state, binding_event), joined_event, binding_event


def test_legacy_v1_seat_join_replays_without_inventing_a_watcher_generation() -> None:
    current = SeatJoinReceipt(
        seat_id="provider-seat",
        holder_ref="codex:legacy-task",
        function=SeatRole.PROVIDER,
        registered_role=SeatRole.PROVIDER,
        registered_holder_ref="holder:provider-seat:1",
        mail_state="MAIL_READY",
        information_proof_handle="sha256:" + ("a" * 64),
        information_cursor=7,
        delivered_message_ids=(),
        reconstruction_event_ids=(),
    ).to_dict()
    current["schema_version"] = "seat-join-receipt/1"
    current.pop("provider_identity_generation")

    migrated = SeatJoinReceipt.from_dict(current).to_dict()

    assert migrated["schema_version"] == "seat-join-receipt/2"
    assert migrated["provider_identity_generation"] is None


def test_legacy_v1_occupancy_binding_replays_into_current_projection() -> None:
    raw = {
        "schema_version": "seat-occupancy-binding/1",
        "binding_id": "seat-binding:legacy",
        "seat_id": "provider-seat",
        "registered_seat_event_id": "event:registration",
        "join_event_id": "event:join",
        "registered_principal_ref": "logical:provider-seat",
        "provider_session_ref": "codex:legacy-task",
        "function": "provider",
        "provider": "codex",
        "provider_identity_kind": "codex-thread-watcher-binding",
        "provider_identity_proof_handle": "sha256:" + ("a" * 64),
        "validity": "active-until-superseded",
    }

    migrated = SeatOccupancyBinding.from_dict(raw).to_dict()

    assert migrated["schema_version"] == "seat-occupancy-binding/4"
    assert set(migrated) == {
        "schema_version",
        "seat_id",
        "registered_seat_event_id",
        "join_event_id",
        "registered_principal_ref",
        "provider_session_ref",
        "function",
        "provider_identity_proof_handle",
        "provider_identity_generation",
        "predecessor_binding_event_id",
        "retired_provider_identity_generation",
    }
    assert migrated["provider_identity_generation"] is None
    assert migrated["predecessor_binding_event_id"] is None
    assert migrated["retired_provider_identity_generation"] is None


def test_same_holder_binding_renewal_retires_only_the_exact_predecessor() -> None:
    state, _first_join, first_binding_event = _joined_provider_state()
    first = state.seat_occupancies["provider-seat"]
    proof_handle = "sha256:" + ("c" * 64)
    joined = replace(
        first.join,
        information_proof_handle=proof_handle,
        information_cursor=state.event_count,
        provider_identity_generation="lease:thread-interface:2",
    )
    join_event = event(
        EventKind.SEAT_JOIN,
        joined.to_dict(),
        subject="seat:provider-seat:occupancy",
        assumption="lawful-assumption",
        fibre="fibre-a",
        actor=SeatRole.PROVIDER,
        causation_ids=(first_binding_event.event_id,),
        provenance=(SourceRef("gate-proof", proof_handle, f"blob:{proof_handle}"),),
    )
    state = apply_event(state, join_event)
    assert (
        state.seat_occupancies["provider-seat"].pending_predecessor_binding_event_id
        == first_binding_event.event_id
    )

    successor = SeatOccupancyBinding(
        seat_id="provider-seat",
        registered_seat_event_id=state.seat_registration_event_ids["provider-seat"],
        join_event_id=join_event.event_id,
        registered_principal_ref="holder:provider-seat:1",
        provider_session_ref="codex:thread-interface",
        function=SeatRole.PROVIDER,
        provider_identity_proof_handle=proof_handle,
        provider_identity_generation="lease:thread-interface:2",
        predecessor_binding_event_id=first_binding_event.event_id,
        retired_provider_identity_generation="lease:thread-interface:1",
    )
    successor_event = event(
        EventKind.SEAT_OCCUPANCY_BINDING,
        successor.to_dict(),
        subject="seat:provider-seat:binding",
        assumption="lawful-assumption",
        fibre="fibre-a",
        actor=SeatRole.PROVIDER,
        causation_ids=(
            state.seat_registration_event_ids["provider-seat"],
            join_event.event_id,
            first_binding_event.event_id,
        ),
        provenance=(SourceRef("gate-proof", proof_handle, f"blob:{proof_handle}"),),
    )
    state = apply_event(state, successor_event)
    occupancy = state.seat_occupancies["provider-seat"]

    assert occupancy.routing_authority is True
    assert occupancy.binding_event_id == successor_event.event_id
    assert occupancy.retired_binding_event_ids == (first_binding_event.event_id,)
    assert state.retired_seat_binding_event_ids == (first_binding_event.event_id,)
    assert state.retired_seat_binding_generations == {
        first_binding_event.event_id: "lease:thread-interface:1"
    }
    assert state.provider_snapshot()["seat_binding_lineage"]["provider-seat"] == {
        "current_binding_event_id": successor_event.event_id,
        "current_provider_identity_generation": "lease:thread-interface:2",
        "retired_predecessors": [
            {
                "binding_event_id": first_binding_event.event_id,
                "provider_identity_generation": "lease:thread-interface:1",
            }
        ],
    }

    replayed_proof_handle = "sha256:" + ("e" * 64)
    replayed_join = replace(
        occupancy.join,
        information_proof_handle=replayed_proof_handle,
        information_cursor=state.event_count,
        provider_identity_generation="lease:thread-interface:1",
    )
    replayed_join_event = event(
        EventKind.SEAT_JOIN,
        replayed_join.to_dict(),
        subject="seat:provider-seat:occupancy",
        assumption="lawful-assumption",
        fibre="fibre-a",
        actor=SeatRole.PROVIDER,
        causation_ids=(successor_event.event_id,),
        provenance=(
            SourceRef(
                "gate-proof",
                replayed_proof_handle,
                f"blob:{replayed_proof_handle}",
            ),
        ),
    )
    replayed_join_state = apply_event(state, replayed_join_event)
    replayed_binding = SeatOccupancyBinding(
        seat_id="provider-seat",
        registered_seat_event_id=state.seat_registration_event_ids["provider-seat"],
        join_event_id=replayed_join_event.event_id,
        registered_principal_ref="holder:provider-seat:1",
        provider_session_ref="codex:thread-interface",
        function=SeatRole.PROVIDER,
        provider_identity_proof_handle=replayed_proof_handle,
        provider_identity_generation="lease:thread-interface:1",
        predecessor_binding_event_id=successor_event.event_id,
        retired_provider_identity_generation="lease:thread-interface:2",
    )
    replayed_binding_event = event(
        EventKind.SEAT_OCCUPANCY_BINDING,
        replayed_binding.to_dict(),
        subject="seat:provider-seat:binding",
        assumption="lawful-assumption",
        fibre="fibre-a",
        actor=SeatRole.PROVIDER,
        causation_ids=(
            state.seat_registration_event_ids["provider-seat"],
            replayed_join_event.event_id,
            successor_event.event_id,
        ),
        provenance=(
            SourceRef(
                "gate-proof",
                replayed_proof_handle,
                f"blob:{replayed_proof_handle}",
            ),
        ),
    )
    with pytest.raises(
        StateTransitionRefused,
        match="retired watcher identity generation",
    ):
        apply_event(replayed_join_state, replayed_binding_event)

    relabelled_binding = replace(
        replayed_binding,
        provider_identity_generation="lease:thread-interface:3",
    )
    relabelled_binding_event = event(
        EventKind.SEAT_OCCUPANCY_BINDING,
        relabelled_binding.to_dict(),
        subject="seat:provider-seat:binding",
        assumption="lawful-assumption",
        fibre="fibre-a",
        actor=SeatRole.PROVIDER,
        causation_ids=(
            state.seat_registration_event_ids["provider-seat"],
            replayed_join_event.event_id,
            successor_event.event_id,
        ),
        provenance=(
            SourceRef(
                "gate-proof",
                replayed_proof_handle,
                f"blob:{replayed_proof_handle}",
            ),
        ),
    )
    with pytest.raises(
        StateTransitionRefused,
        match="watcher generation contradicts the joined identity proof",
    ):
        apply_event(replayed_join_state, relabelled_binding_event)


def test_same_holder_renewal_refuses_missing_or_ambiguous_predecessor() -> None:
    state, _first_join, first_binding_event = _joined_provider_state()
    current = state.seat_occupancies["provider-seat"]
    proof_handle = "sha256:" + ("c" * 64)
    joined = replace(
        current.join,
        information_proof_handle=proof_handle,
        information_cursor=state.event_count,
        provider_identity_generation="lease:thread-interface:2",
    )

    with pytest.raises(StateTransitionRefused, match="causally name the current binding"):
        apply_event(
            state,
            event(
                EventKind.SEAT_JOIN,
                joined.to_dict(),
                subject="seat:provider-seat:occupancy",
                assumption="lawful-assumption",
                fibre="fibre-a",
                actor=SeatRole.PROVIDER,
                provenance=(SourceRef("gate-proof", proof_handle, f"blob:{proof_handle}"),),
            ),
        )

    second_join_event = event(
        EventKind.SEAT_JOIN,
        joined.to_dict(),
        subject="seat:provider-seat:occupancy",
        assumption="lawful-assumption",
        fibre="fibre-a",
        actor=SeatRole.PROVIDER,
        causation_ids=(first_binding_event.event_id,),
        provenance=(SourceRef("gate-proof", proof_handle, f"blob:{proof_handle}"),),
    )
    renewed = apply_event(state, second_join_event)
    second_binding = SeatOccupancyBinding(
        seat_id="provider-seat",
        registered_seat_event_id=renewed.seat_registration_event_ids["provider-seat"],
        join_event_id=second_join_event.event_id,
        registered_principal_ref="holder:provider-seat:1",
        provider_session_ref="codex:thread-interface",
        function=SeatRole.PROVIDER,
        provider_identity_proof_handle=proof_handle,
        provider_identity_generation="lease:thread-interface:2",
        predecessor_binding_event_id=first_binding_event.event_id,
        retired_provider_identity_generation="lease:thread-interface:1",
    )
    second_binding_event = event(
        EventKind.SEAT_OCCUPANCY_BINDING,
        second_binding.to_dict(),
        subject="seat:provider-seat:binding",
        assumption="lawful-assumption",
        fibre="fibre-a",
        actor=SeatRole.PROVIDER,
        causation_ids=(
            renewed.seat_registration_event_ids["provider-seat"],
            second_join_event.event_id,
            first_binding_event.event_id,
        ),
        provenance=(SourceRef("gate-proof", proof_handle, f"blob:{proof_handle}"),),
    )
    renewed = apply_event(renewed, second_binding_event)
    third_proof_handle = "sha256:" + ("d" * 64)
    third_join = replace(
        joined,
        information_proof_handle=third_proof_handle,
        information_cursor=renewed.event_count,
        provider_identity_generation="lease:thread-interface:3",
    )
    with pytest.raises(StateTransitionRefused, match="ambiguous predecessor"):
        apply_event(
            renewed,
            event(
                EventKind.SEAT_JOIN,
                third_join.to_dict(),
                subject="seat:provider-seat:occupancy",
                assumption="lawful-assumption",
                fibre="fibre-a",
                actor=SeatRole.PROVIDER,
                causation_ids=(
                    first_binding_event.event_id,
                    second_binding_event.event_id,
                ),
                provenance=(
                    SourceRef(
                        "gate-proof",
                        third_proof_handle,
                        f"blob:{third_proof_handle}",
                    ),
                ),
            ),
        )


def test_current_join_prepares_exact_cross_holder_handover_without_granting_authority() -> None:
    state, _first_join, first_binding_event = _joined_provider_state()
    current = state.seat_occupancies["provider-seat"]
    replacement_proof = "sha256:" + ("d" * 64)
    replacement = replace(
        current.join,
        holder_ref="codex:different-thread",
        information_proof_handle=replacement_proof,
        information_cursor=state.event_count,
        provider_identity_generation="lease:different-thread:1",
    )
    replacement_event = event(
        EventKind.SEAT_JOIN,
        replacement.to_dict(),
        subject="seat:provider-seat:occupancy",
        assumption="lawful-assumption",
        fibre="fibre-a",
        actor=SeatRole.PROVIDER,
        causation_ids=(first_binding_event.event_id,),
        provenance=(
            SourceRef(
                "gate-proof",
                replacement_proof,
                f"blob:{replacement_proof}",
            ),
        ),
    )

    prepared = apply_event(state, replacement_event)
    occupancy = prepared.seat_occupancies["provider-seat"]

    assert occupancy.join.holder_ref == "codex:different-thread"
    assert occupancy.routing_authority is False
    assert occupancy.pending_predecessor_binding_event_id == first_binding_event.event_id
    assert occupancy.retired_binding_event_ids == current.retired_binding_event_ids

    missing_predecessor = replace(
        replacement,
        information_proof_handle="sha256:" + ("f" * 64),
    )
    with pytest.raises(
        StateTransitionRefused,
        match="causally name the current binding",
    ):
        apply_event(
            state,
            event(
                EventKind.SEAT_JOIN,
                missing_predecessor.to_dict(),
                subject="seat:provider-seat:occupancy",
                assumption="lawful-assumption",
                fibre="fibre-a",
                actor=SeatRole.PROVIDER,
                provenance=(
                    SourceRef(
                        "gate-proof",
                        missing_predecessor.information_proof_handle,
                        f"blob:{missing_predecessor.information_proof_handle}",
                    ),
                ),
            ),
        )


def test_first_current_join_makes_every_other_legacy_occupancy_and_lease_historical() -> None:
    state = select_assumption(awake_state(with_seats=True))
    legacy_proof = "sha256:" + ("a" * 64)
    legacy_join = SeatJoinReceipt(
        seat_id="provider-seat",
        holder_ref="codex:legacy-provider",
        function=SeatRole.PROVIDER,
        registered_role=SeatRole.PROVIDER,
        registered_holder_ref="holder:provider-seat:1",
        mail_state="MAIL_READY",
        information_proof_handle=legacy_proof,
        information_cursor=state.event_count,
        delivered_message_ids=(),
        reconstruction_event_ids=(),
    ).to_dict()
    legacy_join["schema_version"] = SeatJoinReceipt.LEGACY_V1_SCHEMA_VERSION
    legacy_join.pop("provider_identity_generation")
    legacy_join_event = event(
        EventKind.SEAT_JOIN,
        legacy_join,
        subject="seat:provider-seat:occupancy",
        assumption="lawful-assumption",
        fibre="fibre-a",
        actor=SeatRole.PROVIDER,
        provenance=(SourceRef("gate-proof", legacy_proof, f"blob:{legacy_proof}"),),
    )
    state = apply_event(state, legacy_join_event)
    legacy_binding = SeatOccupancyBinding(
        seat_id="provider-seat",
        registered_seat_event_id=state.seat_registration_event_ids["provider-seat"],
        join_event_id=legacy_join_event.event_id,
        registered_principal_ref="holder:provider-seat:1",
        provider_session_ref="codex:legacy-provider",
        function=SeatRole.PROVIDER,
        provider_identity_proof_handle=legacy_proof,
    ).to_dict()
    legacy_binding["schema_version"] = SeatOccupancyBinding.LEGACY_V3_SCHEMA_VERSION
    legacy_binding_event = event(
        EventKind.SEAT_OCCUPANCY_BINDING,
        legacy_binding,
        subject="seat:provider-seat:binding",
        assumption="lawful-assumption",
        fibre="fibre-a",
        actor=SeatRole.PROVIDER,
        causation_ids=(
            state.seat_registration_event_ids["provider-seat"],
            legacy_join_event.event_id,
        ),
        provenance=(SourceRef("gate-proof", legacy_proof, f"blob:{legacy_proof}"),),
    )
    state = apply_event(state, legacy_binding_event)
    checkout = RegionCheckout(
        lease_id="lease:legacy-provider",
        act_id="legacy-provider-act",
        seat_id="provider-seat",
        holder_ref="codex:legacy-provider",
        function=SeatRole.PROVIDER,
        regions=("src/laplace",),
        base_git_head="a" * 40,
        expires_at="2036-08-27T18:00:00Z",
        declaration_kind=LeaseDeclarationKind.NATIVE,
        declaration_ref="journal:legacy-provider-act",
    )
    checkout_event = event(
        EventKind.REGION_CHECKOUT,
        checkout.to_dict(),
        subject="lease:lease:legacy-provider",
        assumption="lawful-assumption",
        fibre="fibre-a",
        actor=SeatRole.PROVIDER,
        causation_ids=(legacy_join_event.event_id, legacy_binding_event.event_id),
    )
    state = apply_event(state, checkout_event)

    current_proof = "sha256:" + ("b" * 64)
    current_join = SeatJoinReceipt(
        seat_id="ego-seat",
        holder_ref="codex:current-ego",
        function=SeatRole.EGO,
        registered_role=SeatRole.EGO,
        registered_holder_ref="holder:ego-seat:1",
        mail_state="MAIL_READY",
        information_proof_handle=current_proof,
        information_cursor=state.event_count,
        delivered_message_ids=(),
        reconstruction_event_ids=(),
        provider_identity_generation="lease:current-ego:1",
    )
    current_join_event = event(
        EventKind.SEAT_JOIN,
        current_join.to_dict(),
        subject="seat:ego-seat:occupancy",
        assumption="lawful-assumption",
        fibre="fibre-a",
        actor=SeatRole.EGO,
        provenance=(SourceRef("gate-proof", current_proof, f"blob:{current_proof}"),),
    )
    state = apply_event(state, current_join_event)

    assert state.seat_lifecycle_cutover_event_id == current_join_event.event_id
    assert set(state.seat_occupancies) == {"ego-seat"}
    assert set(state.seat_lifecycle_invalidated_legacy_occupancies) == {"provider-seat"}
    invalidated = state.seat_lifecycle_invalidated_legacy_occupancies["provider-seat"]
    assert invalidated.join_event_id == legacy_join_event.event_id
    assert invalidated.binding_event_id == legacy_binding_event.event_id
    cutover_projection = state.provider_snapshot()["seat_lifecycle_cutover"]
    assert cutover_projection["invalidated_legacy_occupancies_root"].startswith("sha256:")
    assert (
        cutover_projection["invalidated_legacy_occupancies"]["provider-seat"]["state"]
        == "HISTORICAL-INVALIDATED"
    )
    assert (
        cutover_projection["invalidated_legacy_occupancies"]["provider-seat"]["routing_authority"]
        is False
    )
    assert "lease:legacy-provider" in state.region_leases

    abandoned = RegionCheckin(
        lease_id="lease:legacy-provider",
        seat_id="provider-seat",
        holder_ref="codex:legacy-provider",
        function=SeatRole.PROVIDER,
        outcome=LeaseCheckinOutcome.ABANDONED,
        base_git_head="a" * 40,
        result_git_head="a" * 40,
        committed_paths=(),
        dirty_paths=(),
        evidence={"migration": "historical-only"},
    )
    with pytest.raises(StateTransitionRefused, match="latest seat occupancy"):
        apply_event(
            state,
            event(
                EventKind.REGION_CHECKIN,
                abandoned.to_dict(),
                subject="lease:lease:legacy-provider",
                assumption="lawful-assumption",
                fibre="fibre-a",
                actor=SeatRole.PROVIDER,
                causation_ids=(checkout_event.event_id, legacy_binding_event.event_id),
            ),
        )


def test_region_checkout_is_scoped_to_joined_holder_and_exact_checkin() -> None:
    state, joined_event, binding_event = _joined_provider_state()
    checkout = RegionCheckout(
        lease_id="lease-interface-1",
        act_id="act-interface-1",
        seat_id="provider-seat",
        holder_ref="codex:thread-interface",
        function=SeatRole.PROVIDER,
        regions=("src/laplace/conjugate_interface.py", "tests/conjugate-interface"),
        base_git_head="a" * 40,
        expires_at="2026-08-24T13:00:00Z",
        declaration_kind=LeaseDeclarationKind.NATIVE,
        declaration_ref="journal:act-interface-1",
    )
    checkout_event = event(
        EventKind.REGION_CHECKOUT,
        checkout.to_dict(),
        subject="lease:lease-interface-1",
        assumption="lawful-assumption",
        fibre="fibre-a",
        actor=SeatRole.PROVIDER,
        causation_ids=(joined_event.event_id, binding_event.event_id),
    )
    state = apply_event(state, checkout_event)

    visible = state.provider_snapshot()["region_leases"]["lease-interface-1"]
    assert visible["state"] == "HELD-UNTIL-EXPIRY"
    assert visible["checkout_authority"] == {
        "schema_version": "region-checkout-authority-lineage/1",
        "join_event_id": joined_event.event_id,
        "binding_event_id": binding_event.event_id,
        "provider_identity_generation": "lease:thread-interface:1",
    }
    assert visible["checkout"]["regions"] == [
        "src/laplace/conjugate_interface.py",
        "tests/conjugate-interface",
    ]
    assert any(edge.relation == "holds-region-authority" for edge in state.graph_edges.values())

    checkin = RegionCheckin(
        lease_id="lease-interface-1",
        seat_id="provider-seat",
        holder_ref="codex:thread-interface",
        function=SeatRole.PROVIDER,
        outcome=LeaseCheckinOutcome.COMMITTED,
        base_git_head="a" * 40,
        result_git_head="c" * 40,
        committed_paths=("src/laplace/conjugate_interface.py",),
        dirty_paths=(),
        evidence={"git_worktree_proof": "sha256:" + ("d" * 64)},
    )
    checked_in = event(
        EventKind.REGION_CHECKIN,
        checkin.to_dict(),
        subject="lease:lease-interface-1",
        assumption="lawful-assumption",
        fibre="fibre-a",
        actor=SeatRole.PROVIDER,
        causation_ids=(checkout_event.event_id, binding_event.event_id),
    )
    state = apply_event(state, checked_in)

    assert state.region_leases["lease-interface-1"].checkin == checkin
    assert state.provider_snapshot()["region_leases"]["lease-interface-1"]["state"] == "CLOSED"


def test_region_lease_effective_projection_requires_exact_lineage_and_time() -> None:
    state, joined_event, binding_event = _joined_provider_state()
    checkout = RegionCheckout(
        lease_id="lease-effective-authority",
        act_id="act-effective-authority",
        seat_id="provider-seat",
        holder_ref="codex:thread-interface",
        function=SeatRole.PROVIDER,
        regions=("src/effective-authority",),
        base_git_head="a" * 40,
        expires_at="2036-08-24T13:00:00Z",
        declaration_kind=LeaseDeclarationKind.NATIVE,
        declaration_ref="test:effective-authority",
    )
    checkout_event = event(
        EventKind.REGION_CHECKOUT,
        checkout.to_dict(),
        subject="lease:lease-effective-authority",
        assumption="lawful-assumption",
        fibre="fibre-a",
        actor=SeatRole.PROVIDER,
        causation_ids=(joined_event.event_id, binding_event.event_id),
    )
    state = apply_event(state, checkout_event)
    lease = state.region_leases[checkout.lease_id]

    active = effective_region_lease_projection(
        lease,
        seat_occupancies=state.seat_occupancies,
        observed_at="2026-08-28T04:00:00Z",
    )
    assert active["effective_state"] == "ACTIVE"
    assert active["write_authority"] is True
    assert active["lineage_state"] == "MATCH"

    missing_time = effective_region_lease_projection(
        lease,
        seat_occupancies=state.seat_occupancies,
        observed_at=None,
    )
    missing_lineage = effective_region_lease_projection(
        lease,
        seat_occupancies=None,
        observed_at="2026-08-28T04:00:00Z",
    )
    assert (missing_time["effective_state"], missing_time["write_authority"]) == (
        "UNKNOWN",
        False,
    )
    assert (missing_lineage["effective_state"], missing_lineage["write_authority"]) == (
        "UNKNOWN",
        False,
    )

    historical = lease.to_dict()
    missing_seal = effective_region_lease_projection(
        {**historical, "checkout_authority": {}},
        seat_occupancies=state.seat_occupancies,
        observed_at="2026-08-28T04:00:00Z",
    )
    wrong_seal = effective_region_lease_projection(
        {
            **historical,
            "checkout_authority": {
                **historical["checkout_authority"],
                "schema_version": "region-checkout-authority-lineage/forged",
            },
        },
        seat_occupancies=state.seat_occupancies,
        observed_at="2026-08-28T04:00:00Z",
    )
    assert (missing_seal["effective_state"], missing_seal["write_authority"]) == (
        "UNKNOWN",
        False,
    )
    assert (wrong_seal["effective_state"], wrong_seal["write_authority"]) == (
        "UNKNOWN",
        False,
    )

    occupancy = state.seat_occupancies["provider-seat"]
    displaced = effective_region_lease_projection(
        lease,
        seat_occupancies={
            "provider-seat": replace(
                occupancy,
                binding_event_id="sha256:" + ("d" * 64),
            )
        },
        observed_at="2026-08-28T04:00:00Z",
    )
    expired = effective_region_lease_projection(
        lease,
        seat_occupancies=state.seat_occupancies,
        observed_at="2037-08-28T04:00:00Z",
    )
    assert (displaced["effective_state"], displaced["write_authority"]) == (
        "DISPLACED",
        False,
    )
    empty_occupancy = effective_region_lease_projection(
        lease,
        seat_occupancies={},
        observed_at="2026-08-28T04:00:00Z",
    )
    assert (empty_occupancy["effective_state"], empty_occupancy["write_authority"]) == (
        "DISPLACED",
        False,
    )
    assert (expired["effective_state"], expired["write_authority"]) == (
        "EXPIRED",
        False,
    )


def test_revision_act_derives_split_merge_frontier_and_refuses_ambiguity_or_cycles() -> None:
    state = select_assumption(awake_state())
    split = RevisionAct(
        "split-a",
        ("source:A",),
        ("source:B", "source:C"),
        "one source split into two independently live successors",
    )
    state = apply_event(
        state,
        event(
            EventKind.REVISION,
            split.to_dict(),
            subject="revision:split-a",
            assumption="lawful-assumption",
            fibre="fibre-a",
        ),
    )
    after_split = state.revision_frontier(
        "source:A", assumption="lawful-assumption", fibre="fibre-a"
    )
    assert after_split["status"] == "SUPERSEDED"
    assert after_split["frontier"] == ["source:B", "source:C"]

    merge = RevisionAct(
        "merge-b-c",
        ("source:B", "source:C"),
        ("source:D",),
        "the split successors converge into one current source",
    )
    state = apply_event(
        state,
        event(
            EventKind.REVISION,
            merge.to_dict(),
            subject="revision:merge-b-c",
            assumption="lawful-assumption",
            fibre="fibre-a",
        ),
    )
    topology = state.revision_topology("lawful-assumption", "fibre-a")
    assert topology["predecessors"]["source:D"] == ["source:B", "source:C"]
    assert topology["live_frontier"] == ["source:D"]
    assert state.revision_frontier("source:A", assumption="lawful-assumption", fibre="fibre-a")[
        "frontier"
    ] == ["source:D"]

    duplicate_producer = RevisionAct(
        "ambiguous-d", ("source:X",), ("source:D",), "second producer is ambiguous"
    )
    with pytest.raises(StateTransitionRefused, match="ambiguous producer"):
        apply_event(
            state,
            event(
                EventKind.REVISION,
                duplicate_producer.to_dict(),
                subject="revision:ambiguous-d",
                assumption="lawful-assumption",
                fibre="fibre-a",
            ),
        )

    cycle = RevisionAct("cycle-d-a", ("source:D",), ("source:A",), "would close a lineage cycle")
    with pytest.raises(StateTransitionRefused, match="create a cycle"):
        apply_event(
            state,
            event(
                EventKind.REVISION,
                cycle.to_dict(),
                subject="revision:cycle-d-a",
                assumption="lawful-assumption",
                fibre="fibre-a",
            ),
        )

    transport = TransportReceipt(
        "revision-transport",
        "lawful-assumption",
        "other-assumption",
        "fibre-a",
        "fibre-b",
        "declared-translation",
        "the produced source must be transported into a new identity before revision",
    )
    foreign_state = apply_event(
        state,
        event(
            EventKind.TRANSPORT,
            transport.to_dict(),
            assumption="other-assumption",
            fibre="fibre-b",
        ),
    )
    cross_fibre = RevisionAct(
        "cross-fibre-d", ("source:D",), ("source:E",), "silently crosses fibres"
    )
    with pytest.raises(StateTransitionRefused, match="produced in another fibre"):
        apply_event(
            foreign_state,
            event(
                EventKind.REVISION,
                cross_fibre.to_dict(),
                subject="revision:cross-fibre-d",
                assumption="other-assumption",
                fibre="fibre-b",
            ),
        )


def test_region_checkout_refuses_overlap_and_holder_drift() -> None:
    state, joined_event, binding_event = _joined_provider_state()
    first = RegionCheckout(
        "lease-1",
        "act-1",
        "provider-seat",
        "codex:thread-interface",
        SeatRole.PROVIDER,
        ("src/laplace",),
        "a" * 40,
        "2026-08-24T13:00:00Z",
        LeaseDeclarationKind.NATIVE,
        "journal:act-1",
    )
    state = apply_event(
        state,
        event(
            EventKind.REGION_CHECKOUT,
            first.to_dict(),
            subject="lease:lease-1",
            assumption="lawful-assumption",
            fibre="fibre-a",
            actor=SeatRole.PROVIDER,
            causation_ids=(joined_event.event_id, binding_event.event_id),
        ),
    )
    overlap = RegionCheckout(
        "lease-2",
        "act-2",
        "provider-seat",
        "codex:thread-interface",
        SeatRole.PROVIDER,
        ("src/laplace/startup_mail_gate.py",),
        "a" * 40,
        "2026-08-24T13:00:00Z",
        LeaseDeclarationKind.NATIVE,
        "journal:act-2",
    )
    with pytest.raises(StateTransitionRefused, match="overlaps a live lease"):
        apply_event(
            state,
            event(
                EventKind.REGION_CHECKOUT,
                overlap.to_dict(),
                subject="lease:lease-2",
                assumption="lawful-assumption",
                fibre="fibre-a",
                actor=SeatRole.PROVIDER,
                causation_ids=(joined_event.event_id, binding_event.event_id),
            ),
        )

    drifted = replace(
        overlap,
        lease_id="lease-3",
        holder_ref="codex:different-thread",
        regions=("README.md",),
    )
    with pytest.raises(StateTransitionRefused, match="latest seat occupancy"):
        apply_event(
            state,
            event(
                EventKind.REGION_CHECKOUT,
                drifted.to_dict(),
                subject="lease:lease-3",
                assumption="lawful-assumption",
                fibre="fibre-a",
                actor=SeatRole.PROVIDER,
                causation_ids=(joined_event.event_id, binding_event.event_id),
            ),
        )


def test_region_checkin_refuses_displaced_holder_but_allows_outside_scope_head_move() -> None:
    state, joined_event, binding_event = _joined_provider_state()
    checkout = RegionCheckout(
        "lease-noop",
        "act-noop",
        "provider-seat",
        "codex:thread-interface",
        SeatRole.PROVIDER,
        ("src/laplace/conjugate_interface.py",),
        "a" * 40,
        "2026-08-24T13:00:00Z",
        LeaseDeclarationKind.NATIVE,
        "journal:act-noop",
    )
    checkout_event = event(
        EventKind.REGION_CHECKOUT,
        checkout.to_dict(),
        subject="lease:lease-noop",
        assumption="lawful-assumption",
        fibre="fibre-a",
        actor=SeatRole.PROVIDER,
        causation_ids=(joined_event.event_id, binding_event.event_id),
    )
    state = apply_event(state, checkout_event)
    noop = RegionCheckin(
        "lease-noop",
        "provider-seat",
        "codex:thread-interface",
        SeatRole.PROVIDER,
        LeaseCheckinOutcome.NOOP,
        "a" * 40,
        "b" * 40,
        (),
        (),
        {"git_worktree_proof": "sha256:" + ("d" * 64)},
    )
    # A concurrent commit outside the region may move HEAD without making this holder's
    # scoped no-op false.
    apply_event(
        state,
        event(
            EventKind.REGION_CHECKIN,
            noop.to_dict(),
            subject="lease:lease-noop",
            assumption="lawful-assumption",
            fibre="fibre-a",
            actor=SeatRole.PROVIDER,
            causation_ids=(checkout_event.event_id, binding_event.event_id),
        ),
    )

    displaced = SeatJoinReceipt(
        seat_id="provider-seat",
        holder_ref="codex:new-interface-thread",
        function=SeatRole.PROVIDER,
        registered_role=SeatRole.PROVIDER,
        registered_holder_ref="holder:provider-seat:1",
        mail_state="MAIL_READY",
        information_proof_handle="sha256:" + ("e" * 64),
        information_cursor=state.event_count,
        delivered_message_ids=(),
        reconstruction_event_ids=(),
        defects=(),
        provider_identity_generation="lease:new-interface-thread:1",
    )
    displaced_event = event(
        EventKind.SEAT_JOIN,
        displaced.to_dict(),
        subject="seat:provider-seat:occupancy",
        assumption="lawful-assumption",
        fibre="fibre-a",
        actor=SeatRole.PROVIDER,
        causation_ids=(binding_event.event_id,),
        provenance=(
            SourceRef(
                "gate-proof",
                displaced.information_proof_handle,
                f"blob:{displaced.information_proof_handle}",
            ),
        ),
    )
    state = apply_event(state, displaced_event)
    displaced_binding = SeatOccupancyBinding(
        seat_id="provider-seat",
        registered_seat_event_id=state.seat_registration_event_ids["provider-seat"],
        join_event_id=displaced_event.event_id,
        registered_principal_ref="holder:provider-seat:1",
        provider_session_ref="codex:new-interface-thread",
        function=SeatRole.PROVIDER,
        provider_identity_proof_handle=displaced.information_proof_handle,
        provider_identity_generation="lease:new-interface-thread:1",
        predecessor_binding_event_id=binding_event.event_id,
        retired_provider_identity_generation="lease:thread-interface:1",
    )
    displaced_binding_event = event(
        EventKind.SEAT_OCCUPANCY_BINDING,
        displaced_binding.to_dict(),
        subject="seat:provider-seat:binding",
        assumption="lawful-assumption",
        fibre="fibre-a",
        actor=SeatRole.PROVIDER,
        causation_ids=(
            state.seat_registration_event_ids["provider-seat"],
            displaced_event.event_id,
            binding_event.event_id,
        ),
        provenance=(
            SourceRef(
                "gate-proof",
                displaced.information_proof_handle,
                f"blob:{displaced.information_proof_handle}",
            ),
        ),
    )
    state = apply_event(state, displaced_binding_event)
    assert state.seat_occupancies["provider-seat"].routing_authority is True
    with pytest.raises(StateTransitionRefused, match="latest seat occupancy"):
        apply_event(
            state,
            event(
                EventKind.REGION_CHECKIN,
                noop.to_dict(),
                subject="lease:lease-noop",
                assumption="lawful-assumption",
                fibre="fibre-a",
                actor=SeatRole.PROVIDER,
                causation_ids=(checkout_event.event_id,),
            ),
        )


def test_bootstrap_checkout_declares_covered_dirt_and_retirement_at_birth() -> None:
    crutch = BootstrapCrutch(
        "CR-bootstrap-lease-snapshot",
        "cold-start snapshot of journal-declared in-flight regions",
        "pre-lease acts already exist when native Atlas checkout begins",
        "every live act emits native checkout and matching checkin",
        "native-successful-checkins>=3",
        "ego",
    )
    checkout = RegionCheckout(
        "lease-bootstrap",
        "legacy-act",
        "provider-seat",
        "codex:thread-interface",
        SeatRole.SENSORIUM,
        ("src/laplace/startup_mail_gate.py",),
        "a" * 40,
        "2026-08-24T13:00:00Z",
        LeaseDeclarationKind.JOURNAL_BOOTSTRAP,
        "contract/journal.jsonl#legacy-act",
        ("src/laplace/startup_mail_gate.py",),
        crutch,
    )

    assert checkout.bootstrap_crutch == crutch
    assert checkout.preexisting_dirty_paths == ("src/laplace/startup_mail_gate.py",)
    with pytest.raises(StateTransitionRefused, match="cannot launder"):
        replace(checkout, declaration_kind=LeaseDeclarationKind.NATIVE, bootstrap_crutch=None)


def test_bootstrap_retirement_trigger_is_mechanical_and_refuses_new_crutch() -> None:
    with pytest.raises(StateTransitionRefused, match="mechanically evaluable"):
        BootstrapCrutch(
            "CR-decorative",
            "gap",
            "now",
            "native",
            "when we feel ready",
            "ego",
        )

    crutch = BootstrapCrutch(
        "CR-bootstrap-lease-snapshot",
        "cold-start journal lease snapshot",
        "pre-lease act is already in flight",
        "native checkout before mutation",
        "native-successful-checkins>=3",
        "ego",
    )
    leases: dict[str, RegionLeaseState] = {}
    for index in range(3):
        lease_id = f"native-success-{index}"
        checkout = RegionCheckout(
            lease_id,
            f"act-{index}",
            "provider-seat",
            "codex:thread-interface",
            SeatRole.PROVIDER,
            (f"src/native-{index}",),
            "a" * 40,
            "2026-08-24T13:00:00Z",
            LeaseDeclarationKind.NATIVE,
            f"journal:act-{index}",
        )
        checkin = RegionCheckin(
            lease_id,
            "provider-seat",
            "codex:thread-interface",
            SeatRole.PROVIDER,
            LeaseCheckinOutcome.NOOP,
            "a" * 40,
            "a" * 40,
            (),
            (),
            {"git_worktree_proof": "sha256:" + (str(index) * 64)},
        )
        leases[lease_id] = RegionLeaseState(
            checkout=checkout,
            checkout_event_id=f"event:checkout:{index}",
            checked_out_at="2026-08-24T12:00:00Z",
            checkout_join_event_id=f"event:join:{index}",
            checkout_binding_event_id=f"event:binding:{index}",
            checkout_provider_identity_generation=f"generation:{index}",
            checkin=checkin,
            checkin_event_id=f"event:checkin:{index}",
            checked_in_at="2026-08-24T12:01:00Z",
        )

    retirement = bootstrap_crutch_retirement(
        replace(ConceptricState(), region_leases=leases),
        crutch,
    )
    assert retirement["state"] == "RETIRED"
    assert retirement["observed_native_successes"] == 3
    assert retirement["decision"] == "refuse-new-bootstrap-checkout"

    state, joined_event, binding_event = _joined_provider_state()
    state = replace(state, region_leases=leases)
    bootstrapped = RegionCheckout(
        "retired-bootstrap",
        "legacy-act",
        "provider-seat",
        "codex:thread-interface",
        SeatRole.PROVIDER,
        ("src/legacy",),
        "a" * 40,
        "2026-08-24T13:00:00Z",
        LeaseDeclarationKind.JOURNAL_BOOTSTRAP,
        "journal:legacy-act",
        ("src/legacy",),
        crutch,
    )
    with pytest.raises(StateTransitionRefused, match="retirement trigger is satisfied"):
        apply_event(
            state,
            event(
                EventKind.REGION_CHECKOUT,
                bootstrapped.to_dict(),
                subject="lease:retired-bootstrap",
                assumption="lawful-assumption",
                fibre="fibre-a",
                actor=SeatRole.PROVIDER,
                causation_ids=(joined_event.event_id, binding_event.event_id),
            ),
        )


def test_assumption_change_requires_explicit_transport() -> None:
    state = select_assumption(awake_state())
    silent = AssumptionSelection("other", "fibre-b", None, ())
    with pytest.raises(StateTransitionRefused, match="explicit fibre transport"):
        apply_event(
            state,
            event(
                EventKind.ASSUMPTION,
                silent.to_dict(),
                assumption="other",
                fibre="fibre-b",
            ),
        )

    transport = TransportReceipt(
        "transport-1",
        "lawful-assumption",
        "other",
        "fibre-a",
        "fibre-b",
        "declared-analogy",
        "terminology changes; proof obligations preserved",
    )
    state = apply_event(
        state,
        event(
            EventKind.TRANSPORT,
            transport.to_dict(),
            assumption="other",
            fibre="fibre-b",
        ),
    )
    assert (state.active_assumption, state.active_fibre) == ("other", "fibre-b")
    assert state.transports["transport-1"] == transport


def test_transport_can_revisit_a_stable_context_from_new_provenance() -> None:
    state = select_assumption(awake_state())
    outward = TransportReceipt(
        "transport-out",
        "lawful-assumption",
        "other",
        "fibre-a",
        "fibre-b",
        "declared-analogy",
        "outward",
    )
    state = apply_event(
        state,
        event(
            EventKind.TRANSPORT,
            outward.to_dict(),
            assumption="other",
            fibre="fibre-b",
            provenance=(SourceRef("outward", "sha256:" + "b" * 64, "test://out"),),
        ),
    )
    returning = TransportReceipt(
        "transport-return",
        "other",
        "lawful-assumption",
        "fibre-b",
        "fibre-a",
        "declared-return",
        "return",
    )
    state = apply_event(
        state,
        event(
            EventKind.TRANSPORT,
            returning.to_dict(),
            assumption="lawful-assumption",
            fibre="fibre-a",
            provenance=(SourceRef("return", "sha256:" + "c" * 64, "test://return"),),
        ),
    )

    assert (state.active_assumption, state.active_fibre) == (
        "lawful-assumption",
        "fibre-a",
    )
    assert state.transports["transport-return"] == returning


def test_multi_directional_move_preserves_axis_provenance_and_residual() -> None:
    state = declare_source_detail_axis(select_assumption(awake_state()))
    source = BoundaryRef("handle:root", "node-1", "lawful-assumption", "fibre-a")
    target = BoundaryRef("handle:detail", "node-2", "lawful-assumption", "fibre-a")
    movement = Movement(
        "move-1",
        MoveDirection.DOWN,
        "find the sufficient source detail",
        "graded-descent",
        source,
        target,
        GradeAxis("axis-contract:source-detail/1", "source-detail", "handle", 2),
        (SOURCE,),
        RESIDUAL,
        True,
        None,
    )
    state = apply_event(
        state,
        event(
            EventKind.MOVE,
            movement.to_dict(),
            assumption="lawful-assumption",
            fibre="fibre-a",
        ),
    )
    assert state.movements["move-1"].grade_axis.axis == "source-detail"
    assert state.movements["move-1"].direction == MoveDirection.DOWN


def test_sufficiency_requires_a_measured_within_bound_residual() -> None:
    unknown = Residual(
        ResidualStatus.UNKNOWN,
        None,
        None,
        "fraction",
        "not measured",
    )
    with pytest.raises(StateTransitionRefused, match="measured within-bound"):
        Movement(
            "move:unknown-arrival",
            MoveDirection.DOWN,
            "claim full resolution",
            "graded-descent",
            BoundaryRef("handle:root", "node-1", "lawful-assumption", "fibre-a"),
            BoundaryRef("handle:leaf", "node-2", "lawful-assumption", "fibre-a"),
            GradeAxis(
                "axis-contract:source-detail/1",
                "source-detail",
                "handle",
                "source-bytes",
            ),
            (SOURCE,),
            unknown,
            True,
            None,
        )


def test_direction_is_verified_against_the_named_axis_contract() -> None:
    state = declare_source_detail_axis(select_assumption(awake_state()))
    backwards = Movement(
        "move:backwards-down",
        MoveDirection.DOWN,
        "attempt mislabeled descent",
        "graded-descent",
        BoundaryRef("handle:fine", "node-2", "lawful-assumption", "fibre-a"),
        BoundaryRef("handle:coarse", "node-1", "lawful-assumption", "fibre-a"),
        GradeAxis("axis-contract:source-detail/1", "source-detail", 2, "handle"),
        (SOURCE,),
        RESIDUAL,
        True,
        None,
    )
    with pytest.raises(StateTransitionRefused, match="strictly finer"):
        apply_event(
            state,
            event(
                EventKind.MOVE,
                backwards.to_dict(),
                assumption="lawful-assumption",
                fibre="fibre-a",
            ),
        )


def test_join_and_materialization_are_assumption_indexed() -> None:
    state = select_assumption(awake_state())
    join = JoinReceipt(
        "join-1",
        "node-1",
        "lawful-assumption",
        "fibre-a",
        "semantic-spectral-join",
        "handle:semantic",
        "handle:spectral",
        (SOURCE,),
        RESIDUAL,
    )
    state = apply_event(
        state,
        event(
            EventKind.JOIN,
            join.to_dict(),
            assumption="lawful-assumption",
            fibre="fibre-a",
        ),
    )
    materialized = MaterializedReconstruction(
        "materialization-1",
        "show the joined faces",
        "lawful-assumption",
        "fibre-a",
        "goal-conditioned-sufficient-descent/1",
        {"record": "sha256:" + ("b" * 64)},
        "handle:root",
        (),
        ("handle:semantic", "handle:spectral"),
        {"node-1": "sha256:" + ("c" * 64)},
        RESIDUAL,
        1.0,
    )
    state = apply_event(
        state,
        event(
            EventKind.MATERIALIZATION,
            materialized.to_dict(),
            assumption="lawful-assumption",
            fibre="fibre-a",
        ),
    )
    other = replace(materialized, assumption="other")
    assert materialized.cache_key != other.cache_key
    assert state.materializations[materialized.cache_key] == materialized


def test_all_corpus_domains_share_preview_commit_state_machine() -> None:
    state = awake_state()
    for domain in ("document", "pipeline", "sensorium-projection"):
        preview = CorpusAct(
            f"{domain}-preview",
            domain,
            "prepare",
            f"handle:{domain}",
            ActPhase.PREVIEW,
            {"source": "handle:root"},
            {"diff": f"handle:{domain}:diff"},
            f"transaction:{domain}",
        )
        preview_event = event(EventKind.CORPUS_ACT, preview.to_dict(), subject=preview.act_id)
        state = apply_event(state, preview_event)
        commit = CorpusAct(
            f"{domain}-commit",
            domain,
            "prepare",
            f"handle:{domain}",
            ActPhase.COMMIT,
            {"source": "handle:root"},
            {"result": f"handle:{domain}:result"},
            f"transaction:{domain}",
            preview_event.event_id,
        )
        state = apply_event(
            state, event(EventKind.CORPUS_ACT, commit.to_dict(), subject=commit.act_id)
        )
    assert set(state.corpus_heads) == {"document", "pipeline", "sensorium-projection"}


def test_event_id_is_semantic_not_clock_identity() -> None:
    evaluation = ReplEvaluation(
        "evaluation-1",
        ReplOperation.FOCUS,
        ("handle:root",),
        {"record": "sha256:" + ("e" * 64)},
        {},
        ("handle:focus",),
        "main",
        None,
    )
    first = event(EventKind.REPL, evaluation.to_dict())
    later_runtime = replace(
        RUNTIME,
        receipt_id="receipt-later",
        observed_at="2026-08-24T13:00:00Z",
    )
    second = event(
        EventKind.REPL,
        evaluation.to_dict(),
        runtime=later_runtime,
    )
    second = replace(second, occurred_at="2026-08-24T13:00:00Z")
    assert first.event_id == second.event_id


def test_repl_protocol_is_handle_led_typed_and_persistent() -> None:
    state = awake_state()
    expected = {
        "focus",
        "declare-assumption",
        "switch-assumption",
        "move",
        "reconstruct",
        "inspect-semantic",
        "inspect-spectral",
        "join",
        "transport",
        "compare",
        "diff",
        "explain-provenance",
        "pin",
        "materialize",
        "branch",
        "checkpoint",
        "act-preview",
        "act-commit",
        "act-rollback",
    }
    assert {operation.value for operation in ReplOperation} == expected
    evaluation = ReplEvaluation(
        "evaluation-focus",
        ReplOperation.FOCUS,
        ("handle:root",),
        {"record": "sha256:" + ("e" * 64)},
        {"goal": "find sufficient detail"},
        ("handle:focus",),
        "main",
        "checkpoint:before-focus",
    )
    evaluated = event(EventKind.REPL, evaluation.to_dict())
    state = apply_event(state, evaluated)
    assert state.corpus_heads["repl:main"] == evaluated.event_id
    with pytest.raises(StateTransitionRefused, match="cannot claim read-only"):
        ReplEvaluation(
            "evaluation-commit",
            ReplOperation.ACT_COMMIT,
            ("handle:preview",),
            {"record": "sha256:" + ("e" * 64)},
            {},
            ("handle:result",),
            "main",
            None,
        )


def test_store_is_one_idempotent_write_door_and_replays_deterministically(tmp_path: Path) -> None:
    store = ConceptricStore(tmp_path / "history")
    wake = lifecycle(LifecycleAction.COLD_WAKE, "cold-store")
    first = store.append(wake)
    duplicate = store.append(replace(wake, occurred_at="2026-08-24T13:00:00Z"))
    store.append(seat("ego-seat", SeatRole.EGO))

    assert duplicate.sequence == first.sequence == 1
    assert len(store.events()) == 2
    assert store.materialize() == store.replay()
    assert store.provider_snapshot()["head_event_id"] == store.replay().head_event_id


def test_conceptric_objects_and_edges_resolve_endpoints_and_grades() -> None:
    state = awake_state()
    source = ConceptricObject(
        "object:seat-like",
        "test-object",
        "sha256:" + ("1" * 64),
        None,
        None,
        CONTROL_AXIS_CONTRACT.contract_id,
        "seat",
        (SOURCE,),
        {"label": "source"},
    )
    target = ConceptricObject(
        "object:content-like",
        "test-object",
        "sha256:" + ("2" * 64),
        None,
        None,
        CONTROL_AXIS_CONTRACT.contract_id,
        "content",
        (SOURCE,),
        {"label": "target"},
    )
    state = apply_event(state, event(EventKind.OBJECT, source.to_dict()))
    dangling = ConceptricEdge(
        "edge:dangling",
        "contains",
        source.object_id,
        target.object_id,
        MoveDirection.DOWN,
        None,
        None,
        "test-descent",
        GradeAxis(
            CONTROL_AXIS_CONTRACT.contract_id,
            CONTROL_AXIS_CONTRACT.axis,
            "seat",
            "content",
        ),
        (SOURCE,),
        RESIDUAL,
        "sha256:" + ("3" * 64),
    )
    with pytest.raises(StateTransitionRefused, match="endpoint does not resolve"):
        apply_event(state, event(EventKind.EDGE, dangling.to_dict()))

    state = apply_event(state, event(EventKind.OBJECT, target.to_dict()))
    state = apply_event(state, event(EventKind.EDGE, dangling.to_dict()))
    assert state.graph_edges[dangling.edge_id] == dangling
    assert all(
        edge.source_object_id in state.graph_objects
        and edge.target_object_id in state.graph_objects
        for edge in state.graph_edges.values()
    )

    false_grade = replace(
        dangling,
        edge_id="edge:false-grade",
        grade_axis=GradeAxis(
            CONTROL_AXIS_CONTRACT.contract_id,
            CONTROL_AXIS_CONTRACT.axis,
            "seat",
            "message",
        ),
    )
    with pytest.raises(StateTransitionRefused, match="resolved endpoint grades"):
        apply_event(state, event(EventKind.EDGE, false_grade.to_dict()))


def test_existing_seat_events_are_the_first_dogfooded_graph_region() -> None:
    state = select_assumption(awake_state(with_seats=True))
    message = SeatMessage(
        "message:graph-proof",
        "ego-seat",
        "provider-seat",
        "reconstruct",
        "sha256:" + ("4" * 64),
        {"body": "sha256:" + ("4" * 64)},
        "idempotency:graph-proof",
        state.event_count + 1,
        "2026-08-25T14:00:00Z",
    )
    state = apply_event(
        state,
        event(
            EventKind.MESSAGE,
            message.to_dict(),
            assumption="lawful-assumption",
            fibre="fibre-a",
            actor=SeatRole.EGO,
        ),
    )
    graph = state.provider_snapshot()["graph"]
    assert message.message_id in graph["objects"]
    assert f"content:{message.body_handle}" in graph["objects"]
    relations = {edge["relation"] for edge in graph["edges"].values()}
    assert {"sends", "addressed-to", "has-body"} <= relations
    assert all(
        edge["source_object_id"] in graph["objects"]
        and edge["target_object_id"] in graph["objects"]
        for edge in graph["edges"].values()
    )


def test_store_refuses_tampered_chain(tmp_path: Path) -> None:
    store = ConceptricStore(tmp_path / "history")
    store.append(lifecycle(LifecycleAction.COLD_WAKE, "cold-tamper"))
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE events SET record_digest = ? WHERE sequence = 1",
            ("sha256:" + ("f" * 64),),
        )
    with pytest.raises(HistoryChainMismatch):
        store.replay()


def test_provider_seat_bus_send_pull_ack_and_status() -> None:
    state = select_assumption(awake_state(with_seats=True))
    message = SeatMessage(
        "message-1",
        "ego-seat",
        "provider-seat",
        "reconstruct",
        "handle:task",
        {"record": "sha256:" + ("d" * 64)},
        "idempotency-1",
        state.event_count + 1,
        "2026-08-24T14:00:00Z",
    )
    state = apply_event(
        state,
        event(
            EventKind.MESSAGE,
            message.to_dict(),
            assumption="lawful-assumption",
            fibre="fibre-a",
            actor=SeatRole.EGO,
        ),
    )
    pull = MessagePull(
        "provider-seat",
        0,
        state.event_count,
        "2026-08-24T12:30:00Z",
        ("message-1",),
    )
    state = apply_event(
        state,
        event(
            EventKind.MESSAGE_PULL,
            pull.to_dict(),
            assumption="lawful-assumption",
            fibre="fibre-a",
            actor=SeatRole.PROVIDER,
        ),
    )
    reconstruction_evaluation = ReplEvaluation(
        "evaluation-reconstruct",
        ReplOperation.RECONSTRUCT,
        ("handle:task",),
        {"record": "sha256:" + ("d" * 64)},
        {"goal": "reconstruct provider task", "message_id": "message-1"},
        ("handle:reconstruction",),
        "provider-seat",
        None,
    )
    reconstruction = event(
        EventKind.REPL,
        reconstruction_evaluation.to_dict(),
        subject="reconstruction-proof",
        assumption="lawful-assumption",
        fibre="fibre-a",
        actor=SeatRole.PROVIDER,
    )
    with pytest.raises(StateTransitionRefused, match="send and current pull"):
        apply_event(state, reconstruction)
    reconstruction = event(
        EventKind.REPL,
        reconstruction_evaluation.to_dict(),
        subject="reconstruction-proof",
        assumption="lawful-assumption",
        fibre="fibre-a",
        actor=SeatRole.PROVIDER,
        causation_ids=(
            state.messages["message-1"].sent_event_id,
            state.messages["message-1"].last_pull_event_id,
        ),
    )
    state = apply_event(state, reconstruction)
    reconstruction_causes = {
        edge.source_object_id.removeprefix("event:")
        for edge in state.graph_edges.values()
        if edge.relation == "causes" and edge.target_object_id == f"event:{reconstruction.event_id}"
    }
    assert reconstruction_causes == {
        state.messages["message-1"].sent_event_id,
        state.messages["message-1"].last_pull_event_id,
    }
    acknowledgement = MessageAcknowledgement(
        "message-1",
        "provider-seat",
        AcknowledgementDisposition.ACCEPTED,
        "handle:reconstruction",
        reconstruction.event_id,
        "goal-conditioned frame accepted",
    )
    state = apply_event(
        state,
        event(
            EventKind.MESSAGE_ACK,
            acknowledgement.to_dict(),
            causation_ids=(
                state.messages["message-1"].sent_event_id,
                reconstruction.event_id,
            ),
            assumption="lawful-assumption",
            fibre="fibre-a",
            actor=SeatRole.PROVIDER,
        ),
    )

    status = state.provider_snapshot()["messages"]["message-1"]
    assert status["delivered"] is True
    assert status["status"] == "delivered"
    assert state.cursor_for("provider-seat") == message.cursor


def test_shared_broadcast_body_reconstructs_as_two_independent_deliveries() -> None:
    state = awake_state(with_seats=True)
    state = apply_event(state, seat("claude-seat", SeatRole.SUPEREGO))
    state = select_assumption(state)
    body_handle = "sha256:" + ("b" * 64)
    messages = (
        SeatMessage(
            "message:broadcast-ego",
            "claude-seat",
            "ego-seat",
            "broadcast",
            body_handle,
            {"body": body_handle},
            "idempotency:broadcast-ego",
            state.event_count + 1,
            "2026-08-25T14:00:00Z",
        ),
        SeatMessage(
            "message:broadcast-provider",
            "claude-seat",
            "provider-seat",
            "broadcast",
            body_handle,
            {"body": body_handle},
            "idempotency:broadcast-provider",
            state.event_count + 2,
            "2026-08-25T14:00:00Z",
        ),
    )
    for message in messages:
        state = apply_event(
            state,
            event(
                EventKind.MESSAGE,
                message.to_dict(),
                assumption="lawful-assumption",
                fibre="fibre-a",
                actor=SeatRole.SUPEREGO,
            ),
        )

    for message, role in zip(messages, (SeatRole.EGO, SeatRole.PROVIDER), strict=True):
        pull = MessagePull(
            message.recipient_seat_id,
            0,
            state.event_count,
            "2026-08-24T12:30:00Z",
            (message.message_id,),
        )
        state = apply_event(
            state,
            event(
                EventKind.MESSAGE_PULL,
                pull.to_dict(),
                assumption="lawful-assumption",
                fibre="fibre-a",
                actor=role,
            ),
        )
        record = state.messages[message.message_id]
        reconstruction_handle = f"handle:reconstruction:{message.recipient_seat_id}"
        evaluation = ReplEvaluation(
            f"evaluation:{message.recipient_seat_id}",
            ReplOperation.RECONSTRUCT,
            (body_handle,),
            {"body": body_handle},
            {"goal": "reconstruct broadcast", "message_id": message.message_id},
            (reconstruction_handle,),
            message.recipient_seat_id,
            None,
        )
        reconstruction = event(
            EventKind.REPL,
            evaluation.to_dict(),
            assumption="lawful-assumption",
            fibre="fibre-a",
            actor=role,
            causation_ids=(record.sent_event_id, record.last_pull_event_id),
        )
        state = apply_event(state, reconstruction)
        acknowledgement = MessageAcknowledgement(
            message.message_id,
            message.recipient_seat_id,
            AcknowledgementDisposition.ACCEPTED,
            reconstruction_handle,
            reconstruction.event_id,
            "broadcast delivery independently reconstructed",
        )
        state = apply_event(
            state,
            event(
                EventKind.MESSAGE_ACK,
                acknowledgement.to_dict(),
                assumption="lawful-assumption",
                fibre="fibre-a",
                actor=role,
                causation_ids=(record.sent_event_id, reconstruction.event_id),
            ),
        )

    assert all(
        state.messages[message.message_id].status.value == "delivered" for message in messages
    )


def test_reconstruction_proof_cannot_cross_same_body_deliveries() -> None:
    state = select_assumption(awake_state(with_seats=True))
    body_handle = "sha256:" + ("c" * 64)
    messages: list[SeatMessage] = []
    for suffix in ("first", "second"):
        message = SeatMessage(
            f"message:same-body-{suffix}",
            "ego-seat",
            "provider-seat",
            "reconstruct",
            body_handle,
            {"body": body_handle},
            f"idempotency:same-body-{suffix}",
            state.event_count + 1,
            "2026-08-25T14:00:00Z",
        )
        state = apply_event(
            state,
            event(
                EventKind.MESSAGE,
                message.to_dict(),
                assumption="lawful-assumption",
                fibre="fibre-a",
                actor=SeatRole.EGO,
            ),
        )
        messages.append(message)
    pull = MessagePull(
        "provider-seat",
        0,
        state.event_count,
        "2026-08-24T12:30:00Z",
        tuple(message.message_id for message in messages),
    )
    state = apply_event(
        state,
        event(
            EventKind.MESSAGE_PULL,
            pull.to_dict(),
            assumption="lawful-assumption",
            fibre="fibre-a",
            actor=SeatRole.PROVIDER,
        ),
    )
    first = state.messages[messages[0].message_id]
    evaluation = ReplEvaluation(
        "evaluation:same-body-first",
        ReplOperation.RECONSTRUCT,
        (body_handle,),
        {"body": body_handle},
        {"goal": "first delivery", "message_id": messages[0].message_id},
        ("handle:reconstruction:first",),
        "provider-seat",
        None,
    )
    reconstruction = event(
        EventKind.REPL,
        evaluation.to_dict(),
        assumption="lawful-assumption",
        fibre="fibre-a",
        actor=SeatRole.PROVIDER,
        causation_ids=(first.sent_event_id, first.last_pull_event_id),
    )
    state = apply_event(state, reconstruction)
    second = state.messages[messages[1].message_id]
    wrong_ack = MessageAcknowledgement(
        messages[1].message_id,
        "provider-seat",
        AcknowledgementDisposition.ACCEPTED,
        "handle:reconstruction:first",
        reconstruction.event_id,
        "must not cross delivery identity",
    )
    with pytest.raises(StateTransitionRefused, match="different message delivery"):
        apply_event(
            state,
            event(
                EventKind.MESSAGE_ACK,
                wrong_ack.to_dict(),
                assumption="lawful-assumption",
                fibre="fibre-a",
                actor=SeatRole.PROVIDER,
                causation_ids=(second.sent_event_id, reconstruction.event_id),
            ),
        )


def test_ack_without_reconstruction_never_counts_as_delivery() -> None:
    with pytest.raises(StateTransitionRefused, match="reconstruction proof"):
        MessageAcknowledgement(
            "message-1",
            "provider-seat",
            AcknowledgementDisposition.ACCEPTED,
            None,
            None,
            "accepted without proof",
        )


def test_preserve_fork_is_typed_quarantine_not_delivery_or_acknowledgement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = select_assumption(awake_state(with_seats=True))
    superego_registration = seat("superego-seat", SeatRole.SUPEREGO)
    state = apply_event(state, superego_registration)
    proof_handle = "sha256:" + ("c" * 64)
    joined = SeatJoinReceipt(
        seat_id="superego-seat",
        holder_ref="codex:superego",
        function=SeatRole.SUPEREGO,
        registered_role=SeatRole.SUPEREGO,
        registered_holder_ref="holder:superego-seat:1",
        mail_state="MAIL_READY",
        information_proof_handle=proof_handle,
        information_cursor=state.event_count,
        delivered_message_ids=(),
        reconstruction_event_ids=(),
        provider_identity_generation="lease:superego:1",
    )
    join_event = event(
        EventKind.SEAT_JOIN,
        joined.to_dict(),
        subject="seat:superego-seat:occupancy",
        assumption="lawful-assumption",
        fibre="fibre-a",
        actor=SeatRole.SUPEREGO,
        provenance=(SourceRef("gate-proof", proof_handle, f"blob:{proof_handle}"),),
    )
    state = apply_event(state, join_event)
    binding = SeatOccupancyBinding(
        seat_id="superego-seat",
        registered_seat_event_id=state.seat_registration_event_ids["superego-seat"],
        join_event_id=join_event.event_id,
        registered_principal_ref="holder:superego-seat:1",
        provider_session_ref="codex:superego",
        function=SeatRole.SUPEREGO,
        provider_identity_proof_handle=proof_handle,
        provider_identity_generation="lease:superego:1",
    )
    binding_event = event(
        EventKind.SEAT_OCCUPANCY_BINDING,
        binding.to_dict(),
        subject="seat:superego-seat:binding",
        assumption="lawful-assumption",
        fibre="fibre-a",
        actor=SeatRole.SUPEREGO,
        causation_ids=(superego_registration.event_id, join_event.event_id),
        provenance=(SourceRef("gate-proof", proof_handle, f"blob:{proof_handle}"),),
    )
    state = apply_event(state, binding_event)

    authority_message = SeatMessage(
        "message:authority",
        "ego-seat",
        "superego-seat",
        "author-ruling",
        "sha256:" + ("d" * 64),
        {
            "author_ruling": "gerard:three-seats-now",
            "legacy_claude_obligation": "message:foreign-fork",
        },
        "idempotency:authority",
        state.event_count + 1,
        "2026-08-24T14:00:00Z",
    )
    authority_send = event(
        EventKind.MESSAGE,
        authority_message.to_dict(),
        assumption="lawful-assumption",
        fibre="fibre-a",
        actor=SeatRole.EGO,
    )
    state = apply_event(state, authority_send)
    authority_pull = event(
        EventKind.MESSAGE_PULL,
        MessagePull(
            "superego-seat",
            0,
            state.event_count,
            "2026-08-24T12:30:00Z",
            (authority_message.message_id,),
        ).to_dict(),
        assumption="lawful-assumption",
        fibre="fibre-a",
        actor=SeatRole.SUPEREGO,
    )
    state = apply_event(state, authority_pull)
    authority_reconstruction = event(
        EventKind.REPL,
        ReplEvaluation(
            "evaluation:authority-ruling",
            ReplOperation.RECONSTRUCT,
            (authority_message.body_handle,),
            {"body": authority_message.body_handle},
            {
                "goal": "reconstruct exact author ruling",
                "message_id": authority_message.message_id,
            },
            ("handle:authority-ruling",),
            "superego-seat",
            None,
        ).to_dict(),
        assumption="lawful-assumption",
        fibre="fibre-a",
        actor=SeatRole.SUPEREGO,
        causation_ids=(authority_send.event_id, authority_pull.event_id),
    )
    state = apply_event(state, authority_reconstruction)
    authority_acknowledgement = MessageAcknowledgement(
        authority_message.message_id,
        "superego-seat",
        AcknowledgementDisposition.ACCEPTED,
        "handle:authority-ruling",
        authority_reconstruction.event_id,
        "the exact author ruling was reconstructed",
    )
    authority_event = event(
        EventKind.MESSAGE_ACK,
        authority_acknowledgement.to_dict(),
        assumption="lawful-assumption",
        fibre="fibre-a",
        actor=SeatRole.SUPEREGO,
        causation_ids=(authority_send.event_id, authority_reconstruction.event_id),
    )
    state = apply_event(state, authority_event)

    target = SeatMessage(
        "message:foreign-fork",
        "ego-seat",
        "provider-seat",
        "legacy-obligation",
        "sha256:" + ("e" * 64),
        {"body": "sha256:" + ("e" * 64)},
        "idempotency:foreign-fork",
        state.event_count + 1,
        "2026-08-24T14:00:00Z",
    )
    target_send = event(
        EventKind.MESSAGE,
        target.to_dict(),
        assumption="lawful-assumption",
        fibre="fibre-a",
        actor=SeatRole.EGO,
    )
    state = apply_event(state, target_send)
    import atlas.state as atlas_state

    monkeypatch.setattr(atlas_state, "PRESERVE_FORK_TARGET_MESSAGE_ID", target.message_id)
    monkeypatch.setattr(
        atlas_state,
        "PRESERVE_FORK_AUTHOR_RULING_REF",
        "gerard:three-seats-now",
    )
    monkeypatch.setattr(
        atlas_state,
        "PRESERVE_FORK_AUTHORITY_EVENT_ID",
        authority_event.event_id,
    )
    monkeypatch.setattr(
        atlas_state,
        "PRESERVE_FORK_AUTHORITY_MESSAGE_ID",
        authority_message.message_id,
    )
    caller_proof_handle = "sha256:" + ("f" * 64)
    preservation = MessageForkPreservation(
        message_id=target.message_id,
        original_sender_seat_id="ego-seat",
        recipient_seat_id="provider-seat",
        body_handle=target.body_handle,
        author_ruling_ref="gerard:three-seats-now",
        authority_event_id=authority_event.event_id,
        reason="the fourth seat is intentionally deferred",
        reopen_condition="authenticated original sender delivers an exact replacement",
        actor_provider_session_ref="codex:superego",
        actor_provider_identity_proof_handle=caller_proof_handle,
        actor_provider_identity_generation="generation:superego",
    )
    assert MessageForkPreservation.from_dict(preservation.to_dict()) == preservation
    preserve_event = event(
        EventKind.MESSAGE_PRESERVE_FORK,
        preservation.to_dict(),
        subject=f"preserve-fork:{target.message_id}",
        assumption="lawful-assumption",
        fibre="fibre-a",
        actor=SeatRole.SUPEREGO,
        causation_ids=(
            target_send.event_id,
            authority_event.event_id,
            join_event.event_id,
            binding_event.event_id,
        ),
        provenance=(
            SourceRef(
                "provider-identity",
                caller_proof_handle,
                f"blob:{caller_proof_handle}",
            ),
        ),
    )
    with pytest.raises(StateTransitionRefused, match="actor must be Superego"):
        apply_event(
            state,
            event(
                EventKind.MESSAGE_PRESERVE_FORK,
                preservation.to_dict(),
                subject=f"preserve-fork:{target.message_id}",
                assumption="lawful-assumption",
                fibre="fibre-a",
                actor=SeatRole.PROVIDER,
                causation_ids=preserve_event.causation_ids,
                provenance=preserve_event.provenance,
            ),
        )

    state = apply_event(state, preserve_event)
    status = state.provider_snapshot()["messages"][target.message_id]
    assert status["status"] == "quarantined"
    assert status["delivered"] is False
    assert status["quarantined"] is True
    assert status["acknowledgement_event_id"] is None
    assert status["reconstruction_handle"] is None
    assert status["preserve_fork_event_id"] == preserve_event.event_id
    assert status["preserve_fork"] == preservation.to_dict()
    assert status["preserve_fork_source_status"] == "queued"
    assert (
        state.pending_messages("provider-seat", after_cursor=0, as_of="2026-08-24T12:30:00Z") == ()
    )


def test_delivered_current_fibre_reissue_supersedes_stale_mail_without_delivery_claim() -> None:
    state = select_assumption(awake_state(with_seats=True))
    stale = SeatMessage(
        "message:stale",
        "ego-seat",
        "provider-seat",
        "coordinate-attack",
        "handle:stale",
        {"body": "handle:stale"},
        "idempotency:stale",
        state.event_count + 1,
        "2026-08-25T14:00:00Z",
    )
    state = apply_event(
        state,
        event(
            EventKind.MESSAGE,
            stale.to_dict(),
            assumption="lawful-assumption",
            fibre="fibre-a",
            actor=SeatRole.EGO,
        ),
    )
    transport = TransportReceipt(
        "transport:mail-reissue",
        "lawful-assumption",
        "current-assumption",
        "fibre-a",
        "fibre-b",
        "explicit-reissue",
        "stale verdict is re-derived rather than silently crossed",
    )
    state = apply_event(
        state,
        event(
            EventKind.TRANSPORT,
            transport.to_dict(),
            assumption="current-assumption",
            fibre="fibre-b",
        ),
    )
    replacement = SeatMessage(
        "message:replacement",
        "ego-seat",
        "provider-seat",
        "coordinate-attack-reissued",
        "handle:replacement",
        {"body": "handle:replacement"},
        "idempotency:replacement",
        state.event_count + 1,
        "2026-08-25T14:00:00Z",
    )
    state = apply_event(
        state,
        event(
            EventKind.MESSAGE,
            replacement.to_dict(),
            assumption="current-assumption",
            fibre="fibre-b",
            actor=SeatRole.EGO,
        ),
    )
    supersession = MessageSupersession(
        stale.message_id,
        "ego-seat",
        (replacement.message_id,),
        "the current-fibre reconstruction preserves the live finding",
    )
    with pytest.raises(StateTransitionRefused, match="delivered reconstruction proof"):
        apply_event(
            state,
            event(
                EventKind.MESSAGE_SUPERSESSION,
                legacy_supersession_payload(supersession),
                assumption="current-assumption",
                fibre="fibre-b",
                actor=SeatRole.EGO,
                causation_ids=(state.messages[stale.message_id].sent_event_id,),
            ),
        )

    pull = MessagePull(
        "provider-seat",
        0,
        state.event_count,
        "2026-08-24T12:30:00Z",
        (replacement.message_id,),
    )
    state = apply_event(
        state,
        event(
            EventKind.MESSAGE_PULL,
            pull.to_dict(),
            assumption="current-assumption",
            fibre="fibre-b",
            actor=SeatRole.PROVIDER,
        ),
    )
    replacement_record = state.messages[replacement.message_id]
    reconstruction = event(
        EventKind.REPL,
        ReplEvaluation(
            "evaluation:replacement",
            ReplOperation.RECONSTRUCT,
            (replacement.body_handle,),
            {"body": replacement.body_handle},
            {"goal": "recover current finding", "message_id": replacement.message_id},
            ("handle:replacement-reconstruction",),
            "provider-seat",
            None,
        ).to_dict(),
        assumption="current-assumption",
        fibre="fibre-b",
        actor=SeatRole.PROVIDER,
        causation_ids=(
            replacement_record.sent_event_id,
            replacement_record.last_pull_event_id,
        ),
    )
    state = apply_event(state, reconstruction)
    acknowledgement = event(
        EventKind.MESSAGE_ACK,
        MessageAcknowledgement(
            replacement.message_id,
            "provider-seat",
            AcknowledgementDisposition.ACCEPTED,
            "handle:replacement-reconstruction",
            reconstruction.event_id,
            "current-fibre replacement reconstructed",
        ).to_dict(),
        assumption="current-assumption",
        fibre="fibre-b",
        actor=SeatRole.PROVIDER,
        causation_ids=(replacement_record.sent_event_id, reconstruction.event_id),
    )
    state = apply_event(state, acknowledgement)
    with pytest.raises(StateTransitionRefused, match="causally bind"):
        apply_event(
            state,
            event(
                EventKind.MESSAGE_SUPERSESSION,
                legacy_supersession_payload(supersession),
                assumption="current-assumption",
                fibre="fibre-b",
                actor=SeatRole.EGO,
                causation_ids=(state.messages[stale.message_id].sent_event_id,),
            ),
        )

    supersession_event = event(
        EventKind.MESSAGE_SUPERSESSION,
        legacy_supersession_payload(supersession),
        assumption="current-assumption",
        fibre="fibre-b",
        actor=SeatRole.EGO,
        causation_ids=(
            state.messages[stale.message_id].sent_event_id,
            state.messages[replacement.message_id].sent_event_id,
            acknowledgement.event_id,
        ),
    )
    state = apply_event(state, supersession_event)
    status = state.provider_snapshot()["messages"][stale.message_id]
    assert status["status"] == "superseded"
    assert status["delivered"] is False
    assert status["supersession_event_id"] == supersession_event.event_id
    assert status["replacement_message_ids"] == [replacement.message_id]
    assert status["superseded_by"] == [replacement.message_id]
    assert status["supersession_note"] == supersession.note
    assert (
        state.pending_messages("provider-seat", after_cursor=0, as_of="2026-08-24T12:30:00Z") == ()
    )
    assert any(
        edge.relation == "superseded-by"
        and edge.source_object_id == stale.message_id
        and edge.target_object_id == replacement.message_id
        for edge in state.graph_edges.values()
    )


def test_refused_predecessor_can_be_superseded_only_by_exact_delivered_reissue() -> None:
    def deliver(
        current: ConceptricState,
        message: SeatMessage,
        *,
        disposition: AcknowledgementDisposition,
        suffix: str,
    ) -> tuple[ConceptricState, AtlasEvent]:
        pull_event = event(
            EventKind.MESSAGE_PULL,
            MessagePull(
                "provider-seat",
                current.cursor_for("provider-seat"),
                current.event_count,
                "2026-08-24T12:30:00Z",
                (message.message_id,),
            ).to_dict(),
            assumption="lawful-assumption",
            fibre="fibre-a",
            actor=SeatRole.PROVIDER,
        )
        current = apply_event(current, pull_event)
        record = current.messages[message.message_id]
        reconstruction = event(
            EventKind.REPL,
            ReplEvaluation(
                f"evaluation:{suffix}",
                ReplOperation.RECONSTRUCT,
                (message.body_handle,),
                {"body": message.body_handle},
                {"goal": suffix, "message_id": message.message_id},
                (f"handle:reconstruction:{suffix}",),
                "provider-seat",
                None,
            ).to_dict(),
            assumption="lawful-assumption",
            fibre="fibre-a",
            actor=SeatRole.PROVIDER,
            causation_ids=(record.sent_event_id, record.last_pull_event_id),
        )
        current = apply_event(current, reconstruction)
        acknowledgement = event(
            EventKind.MESSAGE_ACK,
            MessageAcknowledgement(
                message.message_id,
                "provider-seat",
                disposition,
                (
                    f"handle:reconstruction:{suffix}"
                    if disposition == AcknowledgementDisposition.ACCEPTED
                    else None
                ),
                (
                    reconstruction.event_id
                    if disposition == AcknowledgementDisposition.ACCEPTED
                    else None
                ),
                suffix,
            ).to_dict(),
            assumption="lawful-assumption",
            fibre="fibre-a",
            actor=SeatRole.PROVIDER,
            causation_ids=(record.sent_event_id, reconstruction.event_id),
        )
        return apply_event(current, acknowledgement), acknowledgement

    state = select_assumption(awake_state(with_seats=True))
    old = SeatMessage(
        "message:refused-predecessor",
        "ego-seat",
        "provider-seat",
        "development-review-commission",
        "handle:old",
        {"body": "handle:old"},
        "idempotency:old",
        state.event_count + 1,
        "2026-08-25T14:00:00Z",
    )
    state = apply_event(
        state,
        event(
            EventKind.MESSAGE,
            old.to_dict(),
            assumption="lawful-assumption",
            fibre="fibre-a",
            actor=SeatRole.EGO,
        ),
    )
    state, _ = deliver(
        state,
        old,
        disposition=AcknowledgementDisposition.REFUSED,
        suffix="refused-predecessor",
    )
    with pytest.raises(StateTransitionRefused, match="requires a replacement"):
        MessageSupersession(
            old.message_id,
            "ego-seat",
            (),
            "an empty replacement set cannot manufacture terminality",
        )
    replacement = SeatMessage(
        "message:delivered-reissue",
        "ego-seat",
        "provider-seat",
        "development-review-commission",
        "handle:new",
        {"body": "handle:new"},
        "idempotency:new",
        state.event_count + 1,
        "2026-08-25T14:00:00Z",
    )
    state = apply_event(
        state,
        event(
            EventKind.MESSAGE,
            replacement.to_dict(),
            assumption="lawful-assumption",
            fibre="fibre-a",
            actor=SeatRole.EGO,
        ),
    )
    supersession = MessageSupersession(
        old.message_id,
        "ego-seat",
        (replacement.message_id,),
        "the refused malformed predecessor is replaced by exact current evidence",
    )
    with pytest.raises(StateTransitionRefused, match="delivered reconstruction proof"):
        apply_event(
            state,
            event(
                EventKind.MESSAGE_SUPERSESSION,
                legacy_supersession_payload(supersession),
                assumption="lawful-assumption",
                fibre="fibre-a",
                actor=SeatRole.EGO,
                causation_ids=(state.messages[old.message_id].sent_event_id,),
            ),
        )
    state, replacement_ack = deliver(
        state,
        replacement,
        disposition=AcknowledgementDisposition.ACCEPTED,
        suffix="delivered-reissue",
    )
    state = apply_event(
        state,
        event(
            EventKind.MESSAGE_SUPERSESSION,
            legacy_supersession_payload(supersession),
            assumption="lawful-assumption",
            fibre="fibre-a",
            actor=SeatRole.EGO,
            causation_ids=(
                state.messages[old.message_id].sent_event_id,
                state.messages[replacement.message_id].sent_event_id,
                replacement_ack.event_id,
            ),
        ),
    )
    assert state.messages[old.message_id].status.value == "superseded"
    assert state.messages[old.message_id].acknowledgement_event_id is not None
    assert state.messages[old.message_id].replacement_message_ids == (replacement.message_id,)


def test_expiry_and_idempotency_are_explicit() -> None:
    state = select_assumption(awake_state(with_seats=True))
    message = SeatMessage(
        "message-1",
        "ego-seat",
        "provider-seat",
        "judge",
        "handle:task",
        {"record": "sha256:" + ("d" * 64)},
        "same-key",
        state.event_count + 1,
        "2026-08-24T12:10:00Z",
    )
    state = apply_event(
        state,
        event(
            EventKind.MESSAGE,
            message.to_dict(),
            assumption="lawful-assumption",
            fibre="fibre-a",
        ),
    )
    collision = replace(message, message_id="message-2", cursor=state.event_count + 1)
    with pytest.raises(StateTransitionRefused, match="idempotency key"):
        apply_event(
            state,
            event(
                EventKind.MESSAGE,
                collision.to_dict(),
                assumption="lawful-assumption",
                fibre="fibre-a",
            ),
        )
    state = apply_event(
        state,
        event(
            EventKind.MESSAGE_EXPIRY,
            MessageExpiry("message-1", "2026-08-24T12:11:00Z").to_dict(),
            assumption="lawful-assumption",
            fibre="fibre-a",
            actor=SeatRole.SYSTEM,
        ),
    )
    assert state.provider_snapshot()["messages"]["message-1"]["status"] == "expired"
    assert state.provider_snapshot()["messages"]["message-1"]["delivered"] is False


def test_permission_request_and_decision_are_visible_history() -> None:
    state = select_assumption(awake_state(with_seats=True))
    request = PermissionRequest(
        "permission-1",
        "provider-seat",
        "write-document",
        "handle:document",
        "provider needs authority before transactional preview",
        "2026-08-24T14:00:00Z",
    )
    state = apply_event(
        state,
        event(
            EventKind.PERMISSION_REQUEST,
            request.to_dict(),
            assumption="lawful-assumption",
            fibre="fibre-a",
            actor=SeatRole.PROVIDER,
        ),
    )
    decision = PermissionDecision(
        "permission-1",
        "ego-seat",
        PermissionOutcome.GRANTED,
        "bounded to the named document handle",
    )
    state = apply_event(
        state,
        event(
            EventKind.PERMISSION_DECISION,
            decision.to_dict(),
            assumption="lawful-assumption",
            fibre="fibre-a",
            actor=SeatRole.EGO,
        ),
    )
    visible = state.provider_snapshot()["permissions"]["permission-1"]
    assert visible["decision"]["outcome"] == "granted"


def test_provider_snapshot_freezes_bridge_contract_without_second_store() -> None:
    snapshot = awake_state(with_seats=True).provider_snapshot()
    assert snapshot["schema_version"] == PROVIDER_SCHEMA
    assert snapshot["bridge_api"]["write_door"] == "ConceptricStore.append(AtlasEvent)"
    assert set(BRIDGE_OPERATIONS) >= {
        "send",
        "pull",
        "ack",
        "status",
        "wake",
        "cold-wake",
        "sew-up",
        "sleep",
    }


def test_watcher_registration_is_persistent_typed_topology() -> None:
    events = [
        lifecycle(LifecycleAction.COLD_WAKE, "cold-watcher-topology"),
        seat("ego-seat", SeatRole.EGO),
        seat("provider-seat", SeatRole.PROVIDER),
    ]
    state = replay(events)
    selection = AssumptionSelection("lawful-assumption", "fibre-a", 1.0, ())
    selected = event(
        EventKind.ASSUMPTION,
        selection.to_dict(),
        assumption="lawful-assumption",
        fibre="fibre-a",
    )
    events.append(selected)
    state = apply_event(state, selected)
    registration, registered = watcher(state)
    events.append(registered)

    state = replay(events)

    assert state.watchers[registration.watcher_id] == registration
    assert state.watcher_contexts[registration.watcher_id] == (
        "lawful-assumption",
        "fibre-a",
    )
    graph = state.provider_snapshot()["graph"]
    assert graph["objects"]["watcher:watcher-1"]["kind"] == "persistent-watcher"
    assert graph["objects"]["subscription:watcher-1"]["kind"] == "watch-subscription"
    topology = {
        (edge["relation"], edge["source_object_id"], edge["target_object_id"])
        for edge in graph["edges"].values()
    }
    assert (
        "subscribes-to",
        "watcher:watcher-1",
        "subscription:watcher-1",
    ) in topology
    assert (
        "dispatches-to",
        "watcher:watcher-1",
        "seat:provider-seat",
    ) in topology


def test_watcher_checkpoints_are_monotonic_and_replayable() -> None:
    state = select_assumption(awake_state(with_seats=True))
    registration, registered = watcher(state, one_shot=False)
    state = apply_event(state, registered)
    first = WatchCheckpoint(
        registration.watcher_id,
        registration.start_cursor,
        state.event_count,
        (),
        (),
        "2026-08-24T12:01:00Z",
        WatchStatus.ARMED,
        "no match in the first durable window",
    )
    first_event = event(
        EventKind.WATCH_CHECKPOINT,
        first.to_dict(),
        assumption="lawful-assumption",
        fibre="fibre-a",
        actor=SeatRole.EGO,
    )
    state = apply_event(state, first_event)
    stale = replace(
        first,
        after_cursor=registration.start_cursor,
        result_cursor=state.event_count,
        observed_at="2026-08-24T12:02:00Z",
    )
    with pytest.raises(StateTransitionRefused, match="durable cursor"):
        apply_event(
            state,
            event(
                EventKind.WATCH_CHECKPOINT,
                stale.to_dict(),
                assumption="lawful-assumption",
                fibre="fibre-a",
                actor=SeatRole.EGO,
            ),
        )

    second = replace(
        stale,
        after_cursor=first.result_cursor,
        result_cursor=state.event_count,
    )
    state = apply_event(
        state,
        event(
            EventKind.WATCH_CHECKPOINT,
            second.to_dict(),
            assumption="lawful-assumption",
            fibre="fibre-a",
            actor=SeatRole.EGO,
        ),
    )
    assert state.watcher_checkpoints[registration.watcher_id].result_cursor == second.result_cursor


def test_one_shot_watcher_dispatch_stays_queued_and_then_refuses() -> None:
    state = select_assumption(awake_state(with_seats=True))
    registration, registered = watcher(state)
    state = apply_event(state, registered)
    matched = event(
        EventKind.OBSERVATION,
        {"schema_version": "test-observation/1", "result": "matched"},
        assumption="lawful-assumption",
        fibre="fibre-a",
    )
    state = apply_event(state, matched)
    dispatched = watcher_message(state, cause=matched.event_id)
    state = apply_event(state, dispatched)
    message_id = SeatMessage.from_dict(dispatched.payload).message_id
    fired = WatchCheckpoint(
        registration.watcher_id,
        registration.start_cursor,
        state.event_count,
        (matched.event_id,),
        (message_id,),
        "2026-08-24T12:02:00Z",
        WatchStatus.FIRED,
        "one match dispatched once",
    )
    fired_event = event(
        EventKind.WATCH_CHECKPOINT,
        fired.to_dict(),
        assumption="lawful-assumption",
        fibre="fibre-a",
        actor=SeatRole.EGO,
    )
    state = apply_event(state, fired_event)
    status = state.provider_snapshot()["messages"][message_id]
    assert status["status"] == "queued"
    assert status["delivered"] is False
    checkpoint_object_id = next(
        object_id
        for object_id, item in state.graph_objects.items()
        if item.kind == "watch-checkpoint"
    )
    topology = {
        (edge.relation, edge.source_object_id, edge.target_object_id)
        for edge in state.graph_edges.values()
    }
    assert (
        "declares-watch-checkpoint",
        f"event:{fired_event.event_id}",
        checkpoint_object_id,
    ) in topology
    assert (
        "records-watch-match",
        checkpoint_object_id,
        f"event:{matched.event_id}",
    ) in topology

    again = WatchCheckpoint(
        registration.watcher_id,
        fired.result_cursor,
        state.event_count,
        (),
        (),
        "2026-08-24T12:03:00Z",
        WatchStatus.ARMED,
        "must not rearm after firing",
    )
    with pytest.raises(StateTransitionRefused, match="one-shot watcher already fired"):
        apply_event(
            state,
            event(
                EventKind.WATCH_CHECKPOINT,
                again.to_dict(),
                assumption="lawful-assumption",
                fibre="fibre-a",
                actor=SeatRole.EGO,
            ),
        )


def test_fired_watcher_requires_a_dispatch() -> None:
    with pytest.raises(
        StateTransitionRefused, match="fired watcher checkpoint requires a dispatch"
    ):
        WatchCheckpoint(
            "watcher-1",
            1,
            2,
            ("event:match",),
            (),
            "2026-08-24T12:02:00Z",
            WatchStatus.FIRED,
            "a match without dispatch cannot claim firing",
        )


@pytest.mark.parametrize(
    ("sender", "recipient", "message_type", "reason"),
    [
        ("ego-seat", "other-provider-seat", "watch-trigger", "target logical seat"),
        ("other-provider-seat", "provider-seat", "watch-trigger", "creating logical seat"),
        ("ego-seat", "provider-seat", "wrong-type", "registered message type"),
    ],
)
def test_watcher_dispatch_resolves_exact_registration(
    sender: str, recipient: str, message_type: str, reason: str
) -> None:
    state = select_assumption(awake_state(with_seats=True))
    state = apply_event(state, seat("other-provider-seat", SeatRole.PROVIDER))
    registration, registered = watcher(state)
    state = apply_event(state, registered)
    matched = event(
        EventKind.OBSERVATION,
        {"schema_version": "test-observation/1", "result": "matched"},
        assumption="lawful-assumption",
        fibre="fibre-a",
    )
    state = apply_event(state, matched)
    dispatched = watcher_message(
        state,
        sender_seat_id=sender,
        recipient_seat_id=recipient,
        message_type=message_type,
        cause=matched.event_id,
    )
    state = apply_event(state, dispatched)
    checkpoint = WatchCheckpoint(
        registration.watcher_id,
        registration.start_cursor,
        state.event_count,
        (matched.event_id,),
        (SeatMessage.from_dict(dispatched.payload).message_id,),
        "2026-08-24T12:02:00Z",
        WatchStatus.FIRED,
        "adversarial dispatch claim",
    )
    with pytest.raises(StateTransitionRefused, match=reason):
        apply_event(
            state,
            event(
                EventKind.WATCH_CHECKPOINT,
                checkpoint.to_dict(),
                assumption="lawful-assumption",
                fibre="fibre-a",
                actor=SeatRole.EGO,
            ),
        )


def test_expired_watcher_lease_cannot_fire_or_rearm() -> None:
    state = select_assumption(awake_state(with_seats=True))
    registration, registered = watcher(
        state,
        one_shot=False,
        expires_at="2026-08-24T12:10:00Z",
    )
    state = apply_event(state, registered)
    late_armed = WatchCheckpoint(
        registration.watcher_id,
        registration.start_cursor,
        state.event_count,
        (),
        (),
        "2026-08-24T12:11:00Z",
        WatchStatus.ARMED,
        "cannot remain armed after lease expiry",
    )
    with pytest.raises(StateTransitionRefused, match="watcher lease expired"):
        apply_event(
            state,
            event(
                EventKind.WATCH_CHECKPOINT,
                late_armed.to_dict(),
                assumption="lawful-assumption",
                fibre="fibre-a",
                actor=SeatRole.EGO,
            ),
        )
    expired = WatchCheckpoint(
        registration.watcher_id,
        registration.start_cursor,
        state.event_count,
        (),
        (),
        "2026-08-24T12:11:00Z",
        WatchStatus.EXPIRED,
        "watcher lease elapsed",
    )
    state = apply_event(
        state,
        event(
            EventKind.WATCH_CHECKPOINT,
            expired.to_dict(),
            assumption="lawful-assumption",
            fibre="fibre-a",
            actor=SeatRole.EGO,
        ),
    )
    rearmed = replace(
        expired,
        after_cursor=expired.result_cursor,
        result_cursor=state.event_count,
        observed_at="2026-08-24T12:12:00Z",
        status=WatchStatus.ARMED,
        note="must not revive an expired lease",
    )
    with pytest.raises(StateTransitionRefused, match="watcher lease is terminal"):
        apply_event(
            state,
            event(
                EventKind.WATCH_CHECKPOINT,
                rearmed.to_dict(),
                assumption="lawful-assumption",
                fibre="fibre-a",
                actor=SeatRole.EGO,
            ),
        )


def test_filesystem_watch_match_materializes_metadata_observation() -> None:
    state = select_assumption(awake_state(with_seats=True))
    registration = WatcherRegistration(
        "watcher-filesystem",
        "ego-seat",
        "provider-seat",
        WatchSourceKind.FILESYSTEM_PATH,
        {"path": "/bounded/input", "pattern": "*.json"},
        "watch-trigger",
        True,
        1.0,
        state.event_count,
        "2026-08-24T14:00:00Z",
    )
    state = apply_event(
        state,
        event(
            EventKind.WATCHER,
            registration.to_dict(),
            assumption="lawful-assumption",
            fibre="fibre-a",
            actor=SeatRole.EGO,
        ),
    )
    matched_handle = "sha256:" + ("9" * 64)
    message = SeatMessage(
        "message:filesystem-watch",
        "ego-seat",
        "provider-seat",
        "watch-trigger",
        "handle:filesystem-metadata",
        {"filesystem-observation": matched_handle},
        "idempotency:filesystem-watch",
        state.event_count + 1,
        "2026-08-24T14:00:00Z",
    )
    state = apply_event(
        state,
        event(
            EventKind.MESSAGE,
            message.to_dict(),
            assumption="lawful-assumption",
            fibre="fibre-a",
            actor=SeatRole.EGO,
        ),
    )
    checkpoint = WatchCheckpoint(
        registration.watcher_id,
        registration.start_cursor,
        state.event_count,
        (matched_handle,),
        (message.message_id,),
        "2026-08-24T12:02:00Z",
        WatchStatus.FIRED,
        "filesystem metadata changed",
    )
    state = apply_event(
        state,
        event(
            EventKind.WATCH_CHECKPOINT,
            checkpoint.to_dict(),
            assumption="lawful-assumption",
            fibre="fibre-a",
            actor=SeatRole.EGO,
        ),
    )
    observations = {
        object_id
        for object_id, item in state.graph_objects.items()
        if item.kind == "filesystem-metadata-observation"
        and item.attributes["matched_handle"] == matched_handle
    }
    assert len(observations) == 1
    observation_id = next(iter(observations))
    assert any(
        edge.relation == "records-watch-match" and edge.target_object_id == observation_id
        for edge in state.graph_edges.values()
    )


def test_provider_session_holder_replacement_preserves_logical_watcher_target() -> None:
    events: list[AtlasEvent] = []
    state = ConceptricState()

    def bank(item: AtlasEvent) -> None:
        nonlocal state
        events.append(item)
        state = apply_event(state, item)

    bank(lifecycle(LifecycleAction.COLD_WAKE, "cold-session-topology"))
    bank(seat("ego-seat", SeatRole.EGO))
    bank(seat("provider-seat", SeatRole.PROVIDER))
    selection = AssumptionSelection("lawful-assumption", "fibre-a", 1.0, ())
    bank(
        event(
            EventKind.ASSUMPTION,
            selection.to_dict(),
            assumption="lawful-assumption",
            fibre="fibre-a",
        )
    )
    _registration, registered = watcher(state)
    bank(registered)
    bank(
        event(
            EventKind.SEAT,
            SeatTransition(
                "provider-seat",
                SeatRole.PROVIDER,
                SeatAction.RELAY,
                SeatStatus.ACTIVE,
                SeatStatus.RELAYING,
                "charter:provider",
                "holder:provider-seat:1",
            ).to_dict(),
            actor=SeatRole.PROVIDER,
        )
    )
    bank(
        event(
            EventKind.SEAT,
            SeatTransition(
                "provider-seat",
                SeatRole.PROVIDER,
                SeatAction.ACTIVATE,
                SeatStatus.RELAYING,
                SeatStatus.ACTIVE,
                "charter:provider",
                "holder:provider-seat:2",
            ).to_dict(),
            actor=SeatRole.PROVIDER,
        )
    )

    restored = replay(events)
    assert restored == state
    assert restored.seats["provider-seat"].holder_ref == "holder:provider-seat:2"
    assert restored.watchers["watcher-1"].target_seat_id == "provider-seat"
    holder_objects = {
        item.attributes["holder_ref"]: object_id
        for object_id, item in restored.graph_objects.items()
        if item.kind == "provider-session-holder"
    }
    assert {
        "holder:provider-seat:1",
        "holder:provider-seat:2",
    } <= set(holder_objects)
    assert any(
        edge.relation == "dispatches-to"
        and edge.source_object_id == "watcher:watcher-1"
        and edge.target_object_id == "seat:provider-seat"
        for edge in restored.graph_edges.values()
    )


def _deliver_one_for_review_frontier(
    store: ConceptricStore,
    *,
    message_id: str,
    seat_id: str,
    role: SeatRole,
    suffix: str,
    pull_message_ids: tuple[str, ...] | None = None,
) -> None:
    state = store.current_state()
    after_cursor = state.cursor_for(seat_id)
    pending = state.pending_messages(
        seat_id, after_cursor=after_cursor, as_of="2026-08-24T12:30:00Z"
    )
    pulled_ids = pull_message_ids or (message_id,)
    assert tuple(item.message_id for item in pending) == pulled_ids
    store.append(
        event(
            EventKind.MESSAGE_PULL,
            MessagePull(
                seat_id,
                after_cursor,
                state.event_count,
                "2026-08-24T12:30:00Z",
                pulled_ids,
            ).to_dict(),
            assumption="lawful-assumption",
            fibre="fibre-a",
            actor=role,
        )
    )
    state = store.current_state()
    record = state.messages[message_id]
    reconstruction_handle = f"handle:review-frontier:{suffix}"
    evaluation = ReplEvaluation(
        f"evaluation:review-frontier:{suffix}",
        ReplOperation.RECONSTRUCT,
        (record.message.body_handle,),
        {"body": record.message.body_handle},
        {"goal": "reconstruct exact review act", "message_id": message_id},
        (reconstruction_handle,),
        seat_id,
        None,
    )
    reconstruction = event(
        EventKind.REPL,
        evaluation.to_dict(),
        assumption="lawful-assumption",
        fibre="fibre-a",
        actor=role,
        causation_ids=(record.sent_event_id, record.last_pull_event_id),
    )
    store.append(reconstruction)
    store.append(
        event(
            EventKind.MESSAGE_ACK,
            MessageAcknowledgement(
                message_id,
                seat_id,
                AcknowledgementDisposition.ACCEPTED,
                reconstruction_handle,
                reconstruction.event_id,
                "exact review act reconstructed",
            ).to_dict(),
            assumption="lawful-assumption",
            fibre="fibre-a",
            actor=role,
            causation_ids=(record.sent_event_id, reconstruction.event_id),
        )
    )


def _review_frontier_store(tmp_path: Path) -> ConceptricStore:
    store = ConceptricStore(tmp_path / "review-frontier")
    store.append(lifecycle(LifecycleAction.COLD_WAKE, "cold-review-frontier"))
    store.append(seat("ego-seat", SeatRole.EGO))
    store.append(seat("superego-seat", SeatRole.SUPEREGO))
    selection = AssumptionSelection("lawful-assumption", "fibre-a", 0.9, ())
    store.append(
        event(
            EventKind.ASSUMPTION,
            selection.to_dict(),
            assumption=selection.assumption,
            fibre=selection.fibre,
        )
    )
    return store


def test_development_review_frontier_projects_effective_region_authority(
    tmp_path: Path,
) -> None:
    store = _review_frontier_store(tmp_path)
    state = store.current_state()
    generation = "generation:frontier-ego:1"
    proof_body = {
        "schema_version": "laplace.startup-mail-gate/1",
        "state": "MAIL_READY",
        "seat_id": "ego-seat",
        "provider_identity": {
            "schema_version": "laplace.provider-session-identity/1",
            "state": "VERIFIED",
            "provider_session_ref": "codex:frontier-ego",
            "provider": "codex",
            "identity_kind": "codex-thread-watcher-binding",
            "watcher_seat_id": "ego-seat",
            "watcher_target_thread_id": "frontier-ego",
            "watcher_lease_generation": generation,
        },
    }
    proof_handle = BlobStore(store.root / "blobs").put(
        json.dumps(proof_body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    join = SeatJoinReceipt(
        seat_id="ego-seat",
        holder_ref="codex:frontier-ego",
        function=SeatRole.EGO,
        registered_role=SeatRole.EGO,
        registered_holder_ref="holder:ego-seat:1",
        mail_state="MAIL_READY",
        information_proof_handle=proof_handle,
        information_cursor=state.event_count,
        delivered_message_ids=(),
        reconstruction_event_ids=(),
        provider_identity_generation=generation,
    )
    join_event = event(
        EventKind.SEAT_JOIN,
        join.to_dict(),
        subject="seat:ego-seat:occupancy",
        assumption="lawful-assumption",
        fibre="fibre-a",
        actor=SeatRole.EGO,
        provenance=(SourceRef("gate-proof", proof_handle, f"blob:{proof_handle}"),),
    )
    binding = SeatOccupancyBinding(
        seat_id="ego-seat",
        registered_seat_event_id=state.seat_registration_event_ids["ego-seat"],
        join_event_id=join_event.event_id,
        registered_principal_ref="holder:ego-seat:1",
        provider_session_ref="codex:frontier-ego",
        function=SeatRole.EGO,
        provider_identity_proof_handle=proof_handle,
        provider_identity_generation=generation,
    )
    binding_event = event(
        EventKind.SEAT_OCCUPANCY_BINDING,
        binding.to_dict(),
        subject="seat:ego-seat:binding",
        assumption="lawful-assumption",
        fibre="fibre-a",
        actor=SeatRole.EGO,
        causation_ids=(
            state.seat_registration_event_ids["ego-seat"],
            join_event.event_id,
        ),
        provenance=(SourceRef("gate-proof", proof_handle, f"blob:{proof_handle}"),),
    )
    store.append_many((join_event, binding_event))
    checkout = RegionCheckout(
        lease_id="lease-frontier-authority",
        act_id="act-frontier-authority",
        seat_id="ego-seat",
        holder_ref="codex:frontier-ego",
        function=SeatRole.EGO,
        regions=("src/frontier-authority",),
        base_git_head="a" * 40,
        expires_at="2036-08-28T05:00:00Z",
        declaration_kind=LeaseDeclarationKind.NATIVE,
        declaration_ref="test:frontier-authority",
    )
    store.append(
        event(
            EventKind.REGION_CHECKOUT,
            checkout.to_dict(),
            subject="lease:lease-frontier-authority",
            assumption="lawful-assumption",
            fibre="fibre-a",
            actor=SeatRole.EGO,
            causation_ids=(join_event.event_id, binding_event.event_id),
        )
    )

    observed_at = "2026-08-28T04:00:00Z"
    frontier = ConceptricStore.read_development_review_frontier(
        store.root,
        observed_at=observed_at,
    )
    lease = frontier["region_leases"][checkout.lease_id]
    assert frontier["region_lease_authority_observed_at"] == observed_at
    assert lease["authority_observed_at"] == observed_at
    assert lease["effective_state"] == "ACTIVE"
    assert lease["write_authority"] is True
    assert lease["lineage_state"] == "MATCH"


def _review_body(store: ConceptricStore, label: str) -> str:
    return BlobStore(store.root / "blobs").put(label.encode("utf-8"))


def _publish_and_close_review(
    store: ConceptricStore, number: int, *, decision: str | None = "ACCEPT"
) -> None:
    state = store.current_state()
    frozen = {
        "frozen_commit": f"{number:040x}",
        "frozen_tree": f"{number + 1:040x}",
        "frozen_diff_sha256": "sha256:" + f"{number + 2:064x}",
    }
    commission_id = f"message:review-commission:{number}"
    commission = SeatMessage(
        commission_id,
        "ego-seat",
        "superego-seat",
        "development-review-commission",
        _review_body(store, f"commission body {number}"),
        frozen,
        f"idempotency:review-commission:{number}",
        state.event_count + 1,
        "2026-08-25T14:00:00Z",
    )
    store.append(
        event(
            EventKind.MESSAGE,
            commission.to_dict(),
            assumption="lawful-assumption",
            fibre="fibre-a",
            actor=SeatRole.EGO,
        )
    )
    _deliver_one_for_review_frontier(
        store,
        message_id=commission_id,
        seat_id="superego-seat",
        role=SeatRole.SUPEREGO,
        suffix=f"commission-{number}",
    )
    state = store.current_state()
    verdict_id = f"message:review-verdict:{number}"
    verdict = SeatMessage(
        verdict_id,
        "superego-seat",
        "ego-seat",
        "development-review-verdict",
        _review_body(store, f"verdict body {number}"),
        {
            **frozen,
            "commission": commission_id,
            **({} if decision is None else {"review_decision": decision}),
        },
        f"idempotency:review-verdict:{number}",
        state.event_count + 1,
        "2026-08-25T14:00:00Z",
    )
    store.append(
        event(
            EventKind.MESSAGE,
            verdict.to_dict(),
            assumption="lawful-assumption",
            fibre="fibre-a",
            actor=SeatRole.SUPEREGO,
        )
    )
    _deliver_one_for_review_frontier(
        store,
        message_id=verdict_id,
        seat_id="ego-seat",
        role=SeatRole.EGO,
        suffix=f"verdict-{number}",
    )


def test_incremental_review_frontier_replaces_open_publication_with_closure(
    tmp_path: Path,
) -> None:
    store = _review_frontier_store(tmp_path)
    state = store.current_state()
    frozen = {
        "frozen_commit": "a" * 40,
        "frozen_tree": "b" * 40,
        "frozen_diff_sha256": "sha256:" + "c" * 64,
    }
    commission = SeatMessage(
        "message:live-commission",
        "ego-seat",
        "superego-seat",
        "development-review-commission",
        _review_body(store, "live commission body"),
        frozen,
        "idempotency:live-commission",
        state.event_count + 1,
        "2026-08-25T14:00:00Z",
    )
    store.append(
        event(
            EventKind.MESSAGE,
            commission.to_dict(),
            assumption="lawful-assumption",
            fibre="fibre-a",
            actor=SeatRole.EGO,
        )
    )
    opened = ConceptricStore.read_development_review_frontier(store.root)
    assert opened["projection_open_count"] == 1
    assert opened["projection_terminal_count"] == 0
    assert opened["rows"][0]["verdict"] is None

    _deliver_one_for_review_frontier(
        store,
        message_id=commission.message_id,
        seat_id="superego-seat",
        role=SeatRole.SUPEREGO,
        suffix="live-commission",
    )
    state = store.current_state()
    verdict = SeatMessage(
        "message:live-verdict",
        "superego-seat",
        "ego-seat",
        "development-review-verdict",
        _review_body(store, "live verdict body"),
        {**frozen, "commission": commission.message_id, "review_decision": "CONTEST"},
        "idempotency:live-verdict",
        state.event_count + 1,
        "2026-08-25T14:00:00Z",
    )
    store.append(
        event(
            EventKind.MESSAGE,
            verdict.to_dict(),
            assumption="lawful-assumption",
            fibre="fibre-a",
            actor=SeatRole.SUPEREGO,
        )
    )
    queued = ConceptricStore.read_development_review_frontier(store.root)
    assert queued["projection_open_count"] == 1
    assert queued["rows"][0]["review_decision"] == "CONTEST"
    _deliver_one_for_review_frontier(
        store,
        message_id=verdict.message_id,
        seat_id="ego-seat",
        role=SeatRole.EGO,
        suffix="live-verdict",
    )
    closed = ConceptricStore.read_development_review_frontier(store.root)
    assert closed["projection_open_count"] == 0
    assert closed["projection_terminal_count"] == 1
    assert closed["rows"][0]["projection_terminal"] is True
    assert closed["read_metrics"]["history_replayed"] is False


def test_incremental_review_frontier_refuses_unchanged_head_semantic_poison(
    tmp_path: Path,
) -> None:
    store = _review_frontier_store(tmp_path)
    _publish_and_close_review(store, 1)
    clean = ConceptricStore.read_development_review_frontier(store.root)
    assert clean["rows"][0]["review_decision"] == "ACCEPT"

    with sqlite3.connect(store.projection_path) as connection:
        connection.execute(
            "UPDATE development_reviews SET review_decision = 'REJECT' "
            "WHERE commission_id = 'message:review-commission:1'"
        )

    with pytest.raises(HistoryChainMismatch, match="fidelity check failed"):
        ConceptricStore.read_development_review_frontier(store.root)


def test_incremental_review_frontier_refuses_nonlegacy_body_only_primary_swap(
    tmp_path: Path,
) -> None:
    store = _review_frontier_store(tmp_path)
    state = store.current_state()
    frozen = {
        "frozen_commit": "a" * 40,
        "frozen_tree": "b" * 40,
        "frozen_diff_sha256": "sha256:" + "c" * 64,
    }
    commission = SeatMessage(
        "message:legacy-swap-commission",
        "ego-seat",
        "superego-seat",
        "development-review-commission",
        _review_body(store, "legacy swap commission"),
        frozen,
        "idempotency:legacy-swap-commission",
        state.event_count + 1,
        "2026-08-25T14:00:00Z",
    )
    store.append(
        event(
            EventKind.MESSAGE,
            commission.to_dict(),
            assumption="lawful-assumption",
            fibre="fibre-a",
            actor=SeatRole.EGO,
        )
    )
    body = _review_body(
        store,
        json.dumps(
            {
                "verdict": "ACCEPT",
                "frozen": {
                    "commit": frozen["frozen_commit"],
                    "tree": frozen["frozen_tree"],
                    "diff_sha256": frozen["frozen_diff_sha256"],
                },
            }
        ),
    )
    for message_id in (
        "message:13b859bdec653046358bd1a005ebbf7ff4d822d7490a2cf8005462d288330ae3",
        "message:not-on-legacy-allowlist",
    ):
        state = store.current_state()
        verdict = SeatMessage(
            message_id,
            "superego-seat",
            "ego-seat",
            "development-review-verdict",
            body,
            {**frozen, "commission": commission.message_id},
            f"idempotency:{message_id}",
            state.event_count + 1,
            "2026-08-25T14:00:00Z",
        )
        store.append(
            event(
                EventKind.MESSAGE,
                verdict.to_dict(),
                assumption="lawful-assumption",
                fibre="fibre-a",
                actor=SeatRole.SUPEREGO,
            )
        )
        _deliver_one_for_review_frontier(
            store,
            message_id=message_id,
            seat_id="ego-seat",
            role=SeatRole.EGO,
            suffix=message_id.rsplit(":", 1)[-1],
        )

    clean = ConceptricStore.read_development_review_frontier(store.root)
    assert clean["rows"][0]["legacy_compatibility_verified"] is True
    with sqlite3.connect(store.projection_path) as connection:
        residue = connection.execute(
            "SELECT latest_residue_json FROM development_reviews WHERE commission_id = ?",
            (commission.message_id,),
        ).fetchone()[0]
        residue_message = json.loads(str(residue))["message"]
        connection.execute(
            "UPDATE development_reviews SET verdict_json = ? WHERE commission_id = ?",
            (
                json.dumps(residue_message, sort_keys=True, separators=(",", ":")),
                commission.message_id,
            ),
        )

    with pytest.raises(HistoryChainMismatch, match="legacy_compatibility"):
        ConceptricStore.read_development_review_frontier(store.root)


def test_superseded_commission_leaves_the_live_open_frontier(tmp_path: Path) -> None:
    store = _review_frontier_store(tmp_path)
    frozen = {
        "frozen_commit": "a" * 40,
        "frozen_tree": "b" * 40,
        "frozen_diff_sha256": "sha256:" + "c" * 64,
    }
    commissions = []
    for suffix in ("filtered", "replacement"):
        state = store.current_state()
        commission = SeatMessage(
            f"message:{suffix}-commission",
            "ego-seat",
            "superego-seat",
            "development-review-commission",
            _review_body(store, f"{suffix} commission"),
            frozen,
            f"idempotency:{suffix}-commission",
            state.event_count + 1,
            "2026-08-25T14:00:00Z",
        )
        store.append(
            event(
                EventKind.MESSAGE,
                commission.to_dict(),
                assumption="lawful-assumption",
                fibre="fibre-a",
                actor=SeatRole.EGO,
            )
        )
        commissions.append(commission)
    original, replacement = commissions
    _deliver_one_for_review_frontier(
        store,
        message_id=replacement.message_id,
        seat_id="superego-seat",
        role=SeatRole.SUPEREGO,
        suffix="replacement-commission",
        pull_message_ids=(original.message_id, replacement.message_id),
    )
    state = store.current_state()
    replacement_record = state.messages[replacement.message_id]
    store.append(
        event(
            EventKind.MESSAGE_SUPERSESSION,
            legacy_supersession_payload(
                MessageSupersession(
                    original.message_id,
                    "ego-seat",
                    (replacement.message_id,),
                    "replacement commission carries the same exact candidate roots",
                )
            ),
            assumption="lawful-assumption",
            fibre="fibre-a",
            actor=SeatRole.EGO,
            causation_ids=(
                state.messages[original.message_id].sent_event_id,
                replacement_record.sent_event_id,
                replacement_record.acknowledgement_event_id,
            ),
        )
    )

    frontier = ConceptricStore.read_development_review_frontier(store.root)
    assert frontier["projection_open_count"] == 1
    assert [row["commission"]["message"]["message_id"] for row in frontier["rows"]] == [
        replacement.message_id
    ]
    state = store.current_state()
    assert state.messages[original.message_id].status.value == "superseded"


def test_only_the_exact_legacy_body_only_verdicts_remain_primary_evidence(
    tmp_path: Path,
) -> None:
    store = _review_frontier_store(tmp_path)
    state = store.current_state()
    frozen = {
        "frozen_commit": "a" * 40,
        "frozen_tree": "b" * 40,
        "frozen_diff_sha256": "sha256:" + "c" * 64,
    }
    commission = SeatMessage(
        "message:legacy-commission",
        "ego-seat",
        "superego-seat",
        "development-review-commission",
        _review_body(store, "legacy commission"),
        frozen,
        "idempotency:legacy-commission",
        state.event_count + 1,
        "2026-08-25T14:00:00Z",
    )
    store.append(
        event(
            EventKind.MESSAGE,
            commission.to_dict(),
            assumption="lawful-assumption",
            fibre="fibre-a",
            actor=SeatRole.EGO,
        )
    )
    state = store.current_state()
    verdict = SeatMessage(
        "message:13b859bdec653046358bd1a005ebbf7ff4d822d7490a2cf8005462d288330ae3",
        "superego-seat",
        "ego-seat",
        "development-review-verdict",
        _review_body(store, "legacy verdict"),
        {**frozen, "commission": commission.message_id},
        "idempotency:legacy-verdict",
        state.event_count + 1,
        "2026-08-25T14:00:00Z",
    )
    store.append(
        event(
            EventKind.MESSAGE,
            verdict.to_dict(),
            assumption="lawful-assumption",
            fibre="fibre-a",
            actor=SeatRole.SUPEREGO,
        )
    )

    frontier = ConceptricStore.read_development_review_frontier(store.root)
    row = frontier["rows"][0]
    assert row["verdict"]["message"]["message_id"] == verdict.message_id
    assert row["review_decision"] == "REJECT"
    assert row["projection_terminal"] is False
    assert row["review_residue_count"] == 0


def test_unauthorized_later_verdict_is_visible_residue_not_a_reopened_closure(
    tmp_path: Path,
) -> None:
    store = _review_frontier_store(tmp_path)
    store.append(seat("interface-seat", SeatRole.SENSORIUM))
    _publish_and_close_review(store, 1)
    state = store.current_state()
    frozen = {
        "frozen_commit": f"{1:040x}",
        "frozen_tree": f"{2:040x}",
        "frozen_diff_sha256": "sha256:" + f"{3:064x}",
    }
    attempt = SeatMessage(
        "message:third-seat-verdict",
        "interface-seat",
        "ego-seat",
        "development-review-verdict",
        _review_body(store, "unauthorized third-seat verdict"),
        {
            **frozen,
            "commission": "message:review-commission:1",
            "review_decision": "REJECT",
        },
        "idempotency:third-seat-verdict",
        state.event_count + 1,
        "2026-08-25T14:00:00Z",
    )
    store.append(
        event(
            EventKind.MESSAGE,
            attempt.to_dict(),
            assumption="lawful-assumption",
            fibre="fibre-a",
            actor=SeatRole.SENSORIUM,
        )
    )
    _deliver_one_for_review_frontier(
        store,
        message_id=attempt.message_id,
        seat_id="ego-seat",
        role=SeatRole.EGO,
        suffix="third-seat-verdict",
    )

    frontier = ConceptricStore.read_development_review_frontier(store.root)
    row = frontier["rows"][0]
    assert frontier["projection_open_count"] == 0
    assert frontier["projection_terminal_count"] == 1
    assert row["review_decision"] == "ACCEPT"
    assert row["projection_terminal"] is True
    assert row["review_residue_count"] == 1
    assert row["latest_review_residue"]["message"]["message"]["message_id"] == (attempt.message_id)
    assert (
        "verdict sender is not the commissioned reviewer"
        in row["latest_review_residue"]["route_errors"]
    )


def test_incremental_review_frontier_reads_only_the_bounded_terminal_tail(
    tmp_path: Path,
) -> None:
    store = _review_frontier_store(tmp_path)
    for number in range(1, 8):
        _publish_and_close_review(store, number)

    frontier = ConceptricStore.read_development_review_frontier(store.root, terminal_cap=1)

    assert frontier["projection_open_count"] == 0
    assert frontier["projection_terminal_count"] == 7
    assert frontier["omitted_projection_terminal_count"] == 6
    assert frontier["read_metrics"]["rows_loaded"] == 1
    assert frontier["rows"][0]["commission"]["message"]["message_id"].endswith(":7")


def test_region_publication_records_are_exact_round_trips() -> None:
    affected_roots = {"semantic.frontier": "sha256:" + "0" * 64}
    affected_frontier_root = region_publication_affected_frontier_root(affected_roots)
    finalized_projection = region_forward_closure_finalized_projection(
        lease_id="region-lease:" + "2" * 64,
        seat_id="sensorium-seat",
        holder_ref="codex:thread",
        function=SeatRole.SENSORIUM,
        base_ref="refs/heads/main",
        expected_old="a" * 40,
        result_git_head="6" * 40,
        candidate_tree="7" * 40,
        patch_handle="sha256:" + "8" * 64,
        custody_handle="sha256:" + "9" * 64,
        affected_frontier_root=affected_frontier_root,
    )
    forward_closure = RegionForwardClosure.reserve(
        predecessor_event_id="sha256:" + "f" * 64,
        affected_roots=affected_roots,
        expires_at="2036-08-27T12:00:00Z",
        finalized_projection_digest=chash(finalized_projection),
    )
    prepared = RegionPublicationPrepared(
        publication_id="region-publication:" + "1" * 64,
        lease_id="region-lease:" + "2" * 64,
        seat_id="sensorium-seat",
        holder_ref="codex:thread",
        function=SeatRole.SENSORIUM,
        checkout_event_id="sha256:" + "3" * 64,
        binding_event_id="sha256:" + "4" * 64,
        provider_identity_generation="sha256:" + "5" * 64,
        candidate_commit="6" * 40,
        candidate_tree="7" * 40,
        committed_paths=("src/laplace/example.py",),
        patch_handle="sha256:" + "8" * 64,
        custody_handle="sha256:" + "9" * 64,
        affected_frontier_root=affected_frontier_root,
        rehearsal_evidence_root="sha256:" + "1" * 64,
        forward_closure=forward_closure,
        forward_closure_root=forward_closure.forward_closure_root,
        base_ref="refs/heads/main",
        expected_old="a" * 40,
        private_index_recipe={
            "schema_version": "laplace.private-git-index-recipe/1",
            "index_scope": "ephemeral-private",
        },
        recovery_root="sha256:" + "b" * 64,
        message="publish exact candidate",
        evidence={"focused": "sha256:" + "c" * 64},
    )
    signoff_identity = {
        "schema_version": RegionPublicationSignoff.SCHEMA_VERSION,
        "publication_id": prepared.publication_id,
        "lease_id": prepared.lease_id,
        "prepared_event_id": "sha256:" + "d" * 64,
        "recovery_root": prepared.recovery_root,
        "candidate_commit": prepared.candidate_commit,
        "candidate_tree": prepared.candidate_tree,
        "patch_handle": prepared.patch_handle,
        "custody_handle": prepared.custody_handle,
        "affected_frontier_root": prepared.affected_frontier_root,
        "rehearsal_evidence_root": prepared.rehearsal_evidence_root,
        "forward_closure_root": prepared.forward_closure_root,
        "signer_seat_id": "ego-seat",
        "signer_holder_ref": "codex:ego",
        "signer_function": "ego",
        "signer_join_event_id": "sha256:" + "3" * 64,
        "signer_binding_event_id": "sha256:" + "4" * 64,
        "signer_provider_identity_generation": "sha256:" + "5" * 64,
        "role_profile_handle": "sha256:" + "6" * 64,
        "reconstruction_handle": "sha256:" + "7" * 64,
        "predicate_result": "PASS",
        "predicate_domain": "ego",
        "expires_at": "2036-08-27T12:00:00Z",
        "consumed_signoff_event_ids": [],
    }
    signoff = RegionPublicationSignoff(
        signoff_root=chash(signoff_identity),
        signer_function=SeatRole.EGO,
        consumed_signoff_event_ids=(),
        **{
            key: value
            for key, value in signoff_identity.items()
            if key
            not in {"schema_version", "signer_function", "consumed_signoff_event_ids"}
        },
    )
    authorization_identity = {
        "schema_version": RegionPublicationAuthorization.SCHEMA_VERSION,
        "publication_id": prepared.publication_id,
        "lease_id": prepared.lease_id,
        "prepared_event_id": "sha256:" + "d" * 64,
        "recovery_root": prepared.recovery_root,
        "base_ref": prepared.base_ref,
        "expected_old": prepared.expected_old,
        "candidate_commit": prepared.candidate_commit,
        "affected_frontier_root": prepared.affected_frontier_root,
        "rehearsal_evidence_root": prepared.rehearsal_evidence_root,
        "forward_closure_root": prepared.forward_closure_root,
        "signoff_event_ids": ["sha256:" + value * 64 for value in "123"],
        "signoff_roots": ["sha256:" + value * 64 for value in "456"],
        "expires_at": "2036-08-27T12:00:00Z",
        "cas_permission": "UPDATE-REF-ONCE",
    }
    authorization = RegionPublicationAuthorization(
        authorization_root="sha256:" + "f" * 64,
        signoff_event_ids=tuple(authorization_identity["signoff_event_ids"]),
        signoff_roots=tuple(authorization_identity["signoff_roots"]),
        **{
            key: value
            for key, value in authorization_identity.items()
            if key not in {"schema_version", "signoff_event_ids", "signoff_roots"}
        },
    )
    finalized = RegionPublicationFinalized(
        publication_id=prepared.publication_id,
        lease_id=prepared.lease_id,
        prepared_event_id=authorization.prepared_event_id,
        authorized_event_id="sha256:" + "e" * 64,
        recovery_root=prepared.recovery_root,
        authorization_root=authorization.authorization_root,
        base_ref=prepared.base_ref,
        expected_old=prepared.expected_old,
        result_git_head=prepared.candidate_commit,
        candidate_tree=prepared.candidate_tree,
        patch_handle=prepared.patch_handle,
        custody_handle=prepared.custody_handle,
        affected_frontier_root=prepared.affected_frontier_root,
        forward_closure_root=prepared.forward_closure_root,
        forward_closure_consumption_root=region_forward_closure_consumption_root(
            forward_closure_root=prepared.forward_closure_root,
            authorized_event_id="sha256:" + "e" * 64,
            finalized_projection_digest=forward_closure.finalized_projection_digest,
        ),
        signoff_roots=authorization.signoff_roots,
    )

    assert RegionPublicationPrepared.from_dict(prepared.to_dict()) == prepared
    assert RegionPublicationSignoff.from_dict(signoff.to_dict()) == signoff
    assert RegionPublicationAuthorization.from_dict(authorization.to_dict()) == authorization
    assert RegionPublicationFinalized.from_dict(finalized.to_dict()) == finalized
    missing_hook = prepared.to_dict()
    missing_hook.pop("forward_closure")
    with pytest.raises(SchemaFieldMissing):
        RegionPublicationPrepared.from_dict(missing_hook)
    forged_hook = prepared.to_dict()
    forged_hook["forward_closure"]["forward_closure_root"] = "sha256:" + "0" * 64
    with pytest.raises(StateTransitionRefused, match="forward closure root does not verify"):
        RegionPublicationPrepared.from_dict(forged_hook)
