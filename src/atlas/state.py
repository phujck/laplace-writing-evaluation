"""Pure transition and replay for the one Atlas conceptric state machine."""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Iterable, Mapping

from .errors import StateTransitionRefused
from .history import (
    AcknowledgementDisposition,
    ActPhase,
    AssumptionSelection,
    AtlasEvent,
    BootstrapCrutch,
    ConceptricEdge,
    ConceptricObject,
    CorpusAct,
    DeliveryState,
    EventKind,
    GradeAxis,
    GradeAxisContract,
    JoinReceipt,
    LeaseCheckinOutcome,
    LeaseDeclarationKind,
    LifecyclePhase,
    LifecycleTransition,
    MaterializedReconstruction,
    MessageAcknowledgement,
    MessageExpiry,
    MessageForkPreservation,
    MessageMigrationRecoveryEntry,
    MessageMigrationSupersession,
    MessagePull,
    MessageSupersession,
    MoveDirection,
    Movement,
    PermissionDecision,
    PermissionRequest,
    RegionCheckin,
    RegionCheckout,
    RegionPublicationAuthorization,
    RegionPublicationFinalized,
    RegionPublicationPrepared,
    RegionPublicationSignoff,
    ReplEvaluation,
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
)
from .ids import chash
from .updown_history import (
    EXACT_MEMBER_COVERAGE,
    GOAL_CLOSURE_PROBE_SET_KIND,
    DownActReceipt,
    GoalClosureObservation,
    GoalClosureProbeSet,
    GoalClosureStatus,
    UpActReceipt,
    derived_cluster_id,
)

PROVIDER_SCHEMA = "atlas.conceptric-provider.v1"
BRIDGE_API_VERSION = "atlas.seat-bridge.v1"
BRIDGE_OPERATIONS = (
    "append",
    "replay",
    "materialize",
    "send",
    "pull",
    "ack",
    "preserve-message-fork",
    "supersede-message",
    "recover-legacy-message-bundle",
    "record-revision",
    "revision-frontier",
    "status",
    "join-seat",
    "checkout-region",
    "checkin-region",
    "publish-region",
    "sign-publication",
    "request-permission",
    "decide-permission",
    "wake",
    "cold-wake",
    "sew-up",
    "sleep",
    "register-watcher",
    "poll-watcher",
)

PRESERVE_FORK_AUTHORITY_EVENT_ID = (
    "sha256:725e70052924deaa2ce7bee88e6aec26c22462cc4378a0663c4ed4e131e2b5e4"
)
PRESERVE_FORK_AUTHORITY_MESSAGE_ID = (
    "message:d3dd704049bd1bd68e06f6ceba55e989e05fa86ebb5963323491368da65134e8"
)
PRESERVE_FORK_AUTHOR_RULING_REF = "direct:gerard-20260827-exclude-claude-add-later-and-start"
PRESERVE_FORK_TARGET_MESSAGE_ID = (
    "message:9fa1c38ef567333433960fcb6b4c1fc99b4fde2a5c30da3365c6ca0d8194da90"
)

MESSAGE_MIGRATION_RECOVERY_CAPSULE_HANDLE = (
    "sha256:241d2ba48342309cd1cc265515b98e6695296167aa5b4405b5ca8ee803ce960b"
)

CONTROL_AXIS_CONTRACT = GradeAxisContract(
    "axis-contract:atlas-control-topology/1",
    "atlas-control-topology",
    (
        "fabric",
        "context",
        "seat",
        "message",
        "reconstruction",
        "content",
        "acknowledgement",
        "event",
        "watcher",
        "session",
        "subscription",
        "authority",
        "repository-path",
    ),
)


def _parsed_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _regions_overlap(left: str, right: str) -> bool:
    return left == right or left.startswith(right + "/") or right.startswith(left + "/")


def _path_in_regions(path: str, regions: tuple[str, ...]) -> bool:
    return any(path == region or path.startswith(region + "/") for region in regions)


def _exact_vector(value: object, *, field_name: str) -> tuple[float, ...]:
    if not isinstance(value, list) or not value:
        raise StateTransitionRefused(
            "banked routing vector must be a non-empty JSON array",
            field=field_name,
        )
    if any(
        not isinstance(item, (int, float))
        or isinstance(item, bool)
        or not math.isfinite(float(item))
        for item in value
    ):
        raise StateTransitionRefused(
            "banked routing vector must contain only finite numbers",
            field=field_name,
        )
    return tuple(float(item) for item in value)


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right):
        raise StateTransitionRefused("banked routing vectors have inconsistent dimensions")
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left)) or 1.0
    right_norm = math.sqrt(sum(value * value for value in right)) or 1.0
    return numerator / (left_norm * right_norm)


def _vectors_equal(left: tuple[float, ...], right: tuple[float, ...]) -> bool:
    return len(left) == len(right) and all(
        math.isclose(a, b, rel_tol=0.0, abs_tol=1e-12) for a, b in zip(left, right, strict=True)
    )


@dataclass(frozen=True)
class SeatState:
    role: str
    status: SeatStatus
    charter_ref: str
    holder_ref: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "status": self.status.value,
            "charter_ref": self.charter_ref,
            "holder_ref": self.holder_ref,
        }


@dataclass(frozen=True)
class SeatOccupancy:
    """Latest proved join for one chair; observational until routing cut-over."""

    join: SeatJoinReceipt
    join_event_id: str
    joined_at: str
    joined_cursor: int
    binding: SeatOccupancyBinding | None = None
    binding_event_id: str | None = None
    bound_at: str | None = None
    pending_predecessor_binding_event_id: str | None = None
    retired_binding_event_ids: tuple[str, ...] = ()

    @property
    def routing_authority(self) -> bool:
        return (
            self.binding is not None
            and self.binding_event_id is not None
            and self.binding.join_event_id == self.join_event_id
            and self.binding.provider_session_ref == self.join.holder_ref
            and self.binding.function == self.join.function
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": "BOUND" if self.routing_authority else "OBSERVED",
            "routing_authority": self.routing_authority,
            "join": self.join.to_dict(),
            "join_event_id": self.join_event_id,
            "joined_at": self.joined_at,
            "joined_cursor": self.joined_cursor,
            "binding": None if self.binding is None else self.binding.to_dict(),
            "binding_event_id": self.binding_event_id,
            "bound_at": self.bound_at,
            "current_provider_identity_generation": (
                None if self.binding is None else self.binding.provider_identity_generation
            ),
            "pending_predecessor_binding_event_id": (self.pending_predecessor_binding_event_id),
            "retired_binding_event_ids": list(self.retired_binding_event_ids),
            "function_matches_registration": (self.join.function == self.join.registered_role),
            "holder_matches_registration": (
                self.join.holder_ref == self.join.registered_holder_ref
            ),
            "principal_matches_registration": (
                self.binding is not None
                and self.binding.registered_principal_ref == self.join.registered_holder_ref
            ),
            "defects": list(self.join.defects),
        }


def _publication_signoff_matches_occupancy(
    signoff: RegionPublicationSignoff, occupancy: SeatOccupancy | None
) -> bool:
    return (
        occupancy is not None
        and occupancy.routing_authority
        and occupancy.binding is not None
        and occupancy.join.holder_ref == signoff.signer_holder_ref
        and occupancy.join.function == signoff.signer_function
        and occupancy.join_event_id == signoff.signer_join_event_id
        and occupancy.binding_event_id == signoff.signer_binding_event_id
        and occupancy.binding.provider_identity_generation
        == signoff.signer_provider_identity_generation
        and occupancy.join.provider_identity_generation
        == signoff.signer_provider_identity_generation
    )


@dataclass(frozen=True)
class RegionPublicationSignoffState:
    signoff: RegionPublicationSignoff
    event_id: str
    signed_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "signoff": self.signoff.to_dict(),
            "event_id": self.event_id,
            "signed_at": self.signed_at,
        }


@dataclass(frozen=True)
class RegionPublicationState:
    prepared: RegionPublicationPrepared
    prepared_event_id: str
    prepared_at: str
    signoffs: tuple[RegionPublicationSignoffState, ...] = ()
    authorization: RegionPublicationAuthorization | None = None
    authorized_event_id: str | None = None
    authorized_at: str | None = None
    finalized: RegionPublicationFinalized | None = None
    finalized_event_id: str | None = None
    finalized_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": (
                "FINALIZED"
                if self.finalized is not None
                else "AUTHORIZED"
                if self.authorization is not None
                else "SIGNED"
                if self.signoffs
                else "PREPARED"
            ),
            "prepared": self.prepared.to_dict(),
            "prepared_event_id": self.prepared_event_id,
            "prepared_at": self.prepared_at,
            "signoffs": [item.to_dict() for item in self.signoffs],
            "authorization": (
                None if self.authorization is None else self.authorization.to_dict()
            ),
            "authorized_event_id": self.authorized_event_id,
            "authorized_at": self.authorized_at,
            "finalized": None if self.finalized is None else self.finalized.to_dict(),
            "finalized_event_id": self.finalized_event_id,
            "finalized_at": self.finalized_at,
        }


@dataclass(frozen=True)
class RegionLeaseState:
    checkout: RegionCheckout
    checkout_event_id: str
    checked_out_at: str
    checkout_join_event_id: str
    checkout_binding_event_id: str
    checkout_provider_identity_generation: str | None
    checkin: RegionCheckin | None = None
    checkin_event_id: str | None = None
    checked_in_at: str | None = None
    publication: RegionPublicationState | None = None

    def held_at(self, as_of: str) -> bool:
        return self.checkin is None and _parsed_time(self.checkout.expires_at) > _parsed_time(as_of)

    def matches_occupancy(self, occupancy: SeatOccupancy | None) -> bool:
        """Keep repository authority bound to the exact occupancy that acquired it."""

        return (
            occupancy is not None
            and occupancy.routing_authority
            and occupancy.binding is not None
            and occupancy.join.holder_ref == self.checkout.holder_ref
            and occupancy.join.function == self.checkout.function
            and occupancy.join_event_id == self.checkout_join_event_id
            and occupancy.binding_event_id == self.checkout_binding_event_id
            and occupancy.join.provider_identity_generation
            == self.checkout_provider_identity_generation
            and occupancy.binding.provider_identity_generation
            == self.checkout_provider_identity_generation
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": "CLOSED" if self.checkin is not None else "HELD-UNTIL-EXPIRY",
            "authority": "conditional-until-expiry" if self.checkin is None else "none",
            "checkout": self.checkout.to_dict(),
            "checkout_event_id": self.checkout_event_id,
            "checked_out_at": self.checked_out_at,
            "checkout_authority": {
                "schema_version": "region-checkout-authority-lineage/1",
                "join_event_id": self.checkout_join_event_id,
                "binding_event_id": self.checkout_binding_event_id,
                "provider_identity_generation": (
                    self.checkout_provider_identity_generation
                ),
            },
            "checkin": None if self.checkin is None else self.checkin.to_dict(),
            "checkin_event_id": self.checkin_event_id,
            "checked_in_at": self.checked_in_at,
            "publication": None if self.publication is None else self.publication.to_dict(),
        }


def effective_region_lease_projection(
    lease: RegionLeaseState | Mapping[str, Any],
    *,
    seat_occupancies: Mapping[str, SeatOccupancy | Mapping[str, Any]] | None,
    observed_at: str | None,
) -> dict[str, Any]:
    """Project current write authority without rewriting historical lease evidence.

    Authority is a function of three exact inputs: the immutable checkout/checkin fold, the
    current occupancy lineage for its seat, and the caller's observation time. Any missing or
    malformed input fails closed as ``UNKNOWN``. Passing ``None`` for ``seat_occupancies`` means
    current lineage evidence is unavailable; an empty mapping proves there is no occupancy.
    """

    historical = lease.to_dict() if isinstance(lease, RegionLeaseState) else dict(lease)
    checkout = historical.get("checkout")
    checkout_authority = historical.get("checkout_authority")
    closed = "checkin" in historical and historical.get("checkin") is not None

    observation: datetime | None = None
    expiry: datetime | None = None
    if isinstance(observed_at, str) and observed_at:
        try:
            observation = _parsed_time(observed_at)
            if observation.tzinfo is None:
                observation = None
        except (TypeError, ValueError):
            observation = None
    if isinstance(checkout, Mapping):
        expires_at = checkout.get("expires_at")
        if isinstance(expires_at, str) and expires_at:
            try:
                expiry = _parsed_time(expires_at)
                if expiry.tzinfo is None:
                    expiry = None
            except (TypeError, ValueError):
                expiry = None

    lineage_state = "UNKNOWN"
    lineage_reason = "current occupancy lineage evidence is unavailable or malformed"
    if isinstance(checkout, Mapping) and isinstance(checkout_authority, Mapping):
        seat_id = checkout.get("seat_id")
        expected = (
            checkout.get("holder_ref"),
            checkout.get("function"),
            checkout_authority.get("join_event_id"),
            checkout_authority.get("binding_event_id"),
            checkout_authority.get("provider_identity_generation"),
        )
        expected_complete = (
            isinstance(seat_id, str)
            and bool(seat_id)
            and checkout_authority.get("schema_version")
            == "region-checkout-authority-lineage/1"
            and all(isinstance(value, str) and bool(value) for value in expected)
        )
        if expected_complete and seat_occupancies is not None:
            occupancy = seat_occupancies.get(seat_id)
            if occupancy is None:
                lineage_state = "MISMATCH"
                lineage_reason = "the checkout seat has no current occupancy"
            else:
                occupancy_row = (
                    occupancy.to_dict() if isinstance(occupancy, SeatOccupancy) else occupancy
                )
                if isinstance(occupancy_row, Mapping):
                    join = occupancy_row.get("join")
                    binding = occupancy_row.get("binding")
                    if occupancy_row.get("routing_authority") is False:
                        lineage_state = "MISMATCH"
                        lineage_reason = "the current occupancy has no routing authority"
                    elif isinstance(join, Mapping) and isinstance(binding, Mapping):
                        actual = (
                            join.get("holder_ref"),
                            join.get("function"),
                            occupancy_row.get("join_event_id"),
                            occupancy_row.get("binding_event_id"),
                            binding.get("provider_identity_generation"),
                        )
                        join_generation = join.get("provider_identity_generation")
                        actual_complete = (
                            occupancy_row.get("routing_authority") is True
                            and all(
                                isinstance(value, str) and bool(value)
                                for value in (*actual, join_generation)
                            )
                        )
                        if actual_complete:
                            lineage_state = (
                                "MATCH"
                                if actual == expected and join_generation == expected[-1]
                                else "MISMATCH"
                            )
                            lineage_reason = (
                                "current occupancy exactly matches checkout lineage"
                                if lineage_state == "MATCH"
                                else "current occupancy differs from checkout lineage"
                            )

    if closed:
        effective_state = "CLOSED"
    elif observation is not None and expiry is not None and expiry <= observation:
        effective_state = "EXPIRED"
    elif lineage_state == "MISMATCH":
        effective_state = "DISPLACED"
    elif (
        observation is None
        or expiry is None
        or lineage_state != "MATCH"
        or "checkin" not in historical
    ):
        effective_state = "UNKNOWN"
    else:
        effective_state = "ACTIVE"

    write_authority = effective_state == "ACTIVE"
    authority = {
        "schema_version": "atlas.region-lease-effective-authority/1",
        "state": effective_state,
        "write_authority": write_authority,
        "observed_at": observed_at,
        "lineage_state": lineage_state,
        "lineage_reason": lineage_reason,
    }
    return {
        **historical,
        "effective_state": effective_state,
        "write_authority": write_authority,
        "authority_observed_at": observed_at,
        "lineage_state": lineage_state,
        "effective_authority": authority,
    }


def bootstrap_crutch_retirement(
    state: "ConceptricState",
    crutch: BootstrapCrutch,
) -> dict[str, Any]:
    """Evaluate the one typed retirement grammar from folded lease history."""

    successful = tuple(
        lease_id
        for lease_id, lease in sorted(state.region_leases.items())
        if lease.checkout.declaration_kind == LeaseDeclarationKind.NATIVE
        and lease.checkin is not None
        and lease.checkin.outcome in {LeaseCheckinOutcome.COMMITTED, LeaseCheckinOutcome.NOOP}
    )
    required = crutch.required_native_checkins
    retired = len(successful) >= required
    return {
        "schema_version": "bootstrap-crutch-retirement/1",
        "crutch_id": crutch.crutch_id,
        "state": "RETIRED" if retired else "ACTIVE",
        "observed_native_successes": len(successful),
        "required_native_successes": required,
        "evidence_lease_ids": list(successful),
        "decision": "refuse-new-bootstrap-checkout" if retired else "bootstrap-still-allowed",
    }


@dataclass(frozen=True)
class TransactionState:
    preview_event_id: str
    phase: ActPhase

    def to_dict(self) -> dict[str, str]:
        return {"preview_event_id": self.preview_event_id, "phase": self.phase.value}


@dataclass(frozen=True)
class MessageState:
    message: SeatMessage
    sent_event_id: str
    assumption: str
    fibre: str
    status: DeliveryState
    last_pull_event_id: str | None = None
    acknowledgement_event_id: str | None = None
    reconstruction_handle: str | None = None
    preserve_fork_event_id: str | None = None
    preserve_fork: MessageForkPreservation | None = None
    preserve_fork_source_status: DeliveryState | None = None
    preserve_fork_actor_seat_id: str | None = None
    preserve_fork_actor_function: str | None = None
    preserve_fork_binding_event_id: str | None = None
    preserve_fork_assumption: str | None = None
    preserve_fork_fibre: str | None = None
    supersession_event_id: str | None = None
    replacement_message_ids: tuple[str, ...] = ()
    supersession_note: str | None = None
    supersession_provider_session_ref: str | None = None
    supersession_provider_identity_proof_handle: str | None = None
    supersession_provider_identity_generation: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "message": self.message.to_dict(),
            "sent_event_id": self.sent_event_id,
            "assumption": self.assumption,
            "fibre": self.fibre,
            "status": self.status.value,
            "last_pull_event_id": self.last_pull_event_id,
            "acknowledgement_event_id": self.acknowledgement_event_id,
            "reconstruction_handle": self.reconstruction_handle,
            "preserve_fork_event_id": self.preserve_fork_event_id,
            "preserve_fork": (None if self.preserve_fork is None else self.preserve_fork.to_dict()),
            "preserve_fork_source_status": (
                None
                if self.preserve_fork_source_status is None
                else self.preserve_fork_source_status.value
            ),
            "preserve_fork_actor_seat_id": self.preserve_fork_actor_seat_id,
            "preserve_fork_actor_function": self.preserve_fork_actor_function,
            "preserve_fork_binding_event_id": self.preserve_fork_binding_event_id,
            "preserve_fork_frontier": (
                None
                if self.preserve_fork_assumption is None
                else {
                    "assumption": self.preserve_fork_assumption,
                    "fibre": self.preserve_fork_fibre,
                }
            ),
            "supersession_event_id": self.supersession_event_id,
            "replacement_message_ids": list(self.replacement_message_ids),
            "superseded_by": list(self.replacement_message_ids),
            "supersession_note": self.supersession_note,
            "supersession_provider_session_ref": (self.supersession_provider_session_ref),
            "supersession_provider_identity_proof_handle": (
                self.supersession_provider_identity_proof_handle
            ),
            "supersession_provider_identity_generation": (
                self.supersession_provider_identity_generation
            ),
            "delivered": self.status == DeliveryState.DELIVERED,
            "quarantined": self.status == DeliveryState.QUARANTINED,
        }


@dataclass(frozen=True)
class ConceptricState:
    """A deterministic fold of typed events; no field is written outside ``apply_event``."""

    lifecycle: LifecyclePhase = LifecyclePhase.SLEEPING
    seats: Mapping[str, SeatState] = field(default_factory=dict)
    seat_registration_event_ids: Mapping[str, str] = field(default_factory=dict)
    seat_joins: Mapping[str, SeatJoinReceipt] = field(default_factory=dict)
    seat_occupancies: Mapping[str, SeatOccupancy] = field(default_factory=dict)
    seat_bindings: Mapping[str, SeatOccupancyBinding] = field(default_factory=dict)
    seat_lifecycle_cutover_event_id: str | None = None
    seat_lifecycle_invalidated_legacy_occupancies: Mapping[str, SeatOccupancy] = field(
        default_factory=dict
    )
    retired_seat_binding_event_ids: tuple[str, ...] = ()
    retired_seat_binding_generations: Mapping[str, str] = field(default_factory=dict)
    region_leases: Mapping[str, RegionLeaseState] = field(default_factory=dict)
    active_assumption: str | None = None
    active_fibre: str | None = None
    transports: Mapping[str, TransportReceipt] = field(default_factory=dict)
    movements: Mapping[str, Movement] = field(default_factory=dict)
    joins: Mapping[str, JoinReceipt] = field(default_factory=dict)
    up_acts: Mapping[str, UpActReceipt] = field(default_factory=dict)
    up_events: Mapping[str, str] = field(default_factory=dict)
    down_acts: Mapping[str, DownActReceipt] = field(default_factory=dict)
    observation_events: Mapping[str, AtlasEvent] = field(default_factory=dict)
    goal_closure_probe_sets: Mapping[str, GoalClosureProbeSet] = field(default_factory=dict)
    goal_closure_probe_events: Mapping[str, str] = field(default_factory=dict)
    grade_axis_contracts: Mapping[str, GradeAxisContract] = field(
        default_factory=lambda: {CONTROL_AXIS_CONTRACT.contract_id: CONTROL_AXIS_CONTRACT}
    )
    graph_objects: Mapping[str, ConceptricObject] = field(default_factory=dict)
    graph_edges: Mapping[str, ConceptricEdge] = field(default_factory=dict)
    materializations: Mapping[str, MaterializedReconstruction] = field(default_factory=dict)
    materialization_events: Mapping[str, AtlasEvent] = field(default_factory=dict)
    transactions: Mapping[str, TransactionState] = field(default_factory=dict)
    corpus_heads: Mapping[str, str] = field(default_factory=dict)
    messages: Mapping[str, MessageState] = field(default_factory=dict)
    message_migration_supersessions: Mapping[str, MessageMigrationSupersession] = field(
        default_factory=dict
    )
    message_idempotency: Mapping[str, str] = field(default_factory=dict)
    revision_acts: Mapping[str, RevisionAct] = field(default_factory=dict)
    revision_contexts: Mapping[str, tuple[str, str]] = field(default_factory=dict)
    seat_cursors: Mapping[tuple[str, str, str], int] = field(default_factory=dict)
    permission_requests: Mapping[str, PermissionRequest] = field(default_factory=dict)
    permission_decisions: Mapping[str, PermissionDecision] = field(default_factory=dict)
    repl_evaluations: Mapping[str, ReplEvaluation] = field(default_factory=dict)
    repl_contexts: Mapping[str, tuple[str, str, str]] = field(default_factory=dict)
    watchers: Mapping[str, WatcherRegistration] = field(default_factory=dict)
    watcher_contexts: Mapping[str, tuple[str, str]] = field(default_factory=dict)
    watcher_checkpoints: Mapping[str, WatchCheckpoint] = field(default_factory=dict)
    event_ids: tuple[str, ...] = ()
    head_event_id: str | None = None
    event_count: int = 0

    def provider_snapshot(self, *, observed_at: str | None = None) -> dict[str, Any]:
        """Frozen read model consumed by MCP, CLI, notebook and Sensorium adapters."""

        invalidated_legacy_occupancies = {
            seat_id: {
                **occupancy.to_dict(),
                "state": "HISTORICAL-INVALIDATED",
                "routing_authority": False,
            }
            for seat_id, occupancy in sorted(
                self.seat_lifecycle_invalidated_legacy_occupancies.items()
            )
        }
        invalidated_legacy_occupancies_root = (
            None
            if self.seat_lifecycle_cutover_event_id is None
            else chash(
                {
                    "schema_version": ("atlas.seat-lifecycle-invalidated-legacy-occupancies/1"),
                    "cutover_event_id": self.seat_lifecycle_cutover_event_id,
                    "occupancies": invalidated_legacy_occupancies,
                }
            )
        )

        return {
            "schema_version": PROVIDER_SCHEMA,
            "bridge_api": {
                "schema_version": BRIDGE_API_VERSION,
                "operations": list(BRIDGE_OPERATIONS),
                "write_door": "ConceptricStore.append(AtlasEvent)",
                "delivery_rule": (
                    "delivered iff an accepted acknowledgement causally joins the send to a "
                    "same-seat, same-fibre typed reconstruction evaluation that consumed the "
                    "message body and produced the acknowledged handle"
                ),
            },
            "head_event_id": self.head_event_id,
            "event_count": self.event_count,
            "lifecycle": self.lifecycle.value,
            "seats": {key: value.to_dict() for key, value in sorted(self.seats.items())},
            "seat_registration_event_ids": dict(sorted(self.seat_registration_event_ids.items())),
            "seat_occupancy": {
                key: value.to_dict() for key, value in sorted(self.seat_occupancies.items())
            },
            "seat_lifecycle_cutover": {
                "current_schema": SeatJoinReceipt.SCHEMA_VERSION,
                "event_id": self.seat_lifecycle_cutover_event_id,
                "state": (
                    "CURRENT"
                    if self.seat_lifecycle_cutover_event_id is not None
                    else "LEGACY-PREFIX"
                ),
                "invalidated_legacy_occupancies": invalidated_legacy_occupancies,
                "invalidated_legacy_occupancies_root": (invalidated_legacy_occupancies_root),
            },
            "seat_binding_lineage": {
                seat_id: {
                    "current_binding_event_id": occupancy.binding_event_id,
                    "current_provider_identity_generation": (
                        None
                        if occupancy.binding is None
                        else occupancy.binding.provider_identity_generation
                    ),
                    "retired_predecessors": [
                        {
                            "binding_event_id": binding_event_id,
                            "provider_identity_generation": (
                                self.retired_seat_binding_generations.get(binding_event_id)
                            ),
                        }
                        for binding_event_id in occupancy.retired_binding_event_ids
                    ],
                }
                for seat_id, occupancy in sorted(self.seat_occupancies.items())
            },
            "region_leases": {
                key: {
                    **effective_region_lease_projection(
                        value,
                        seat_occupancies=self.seat_occupancies,
                        observed_at=observed_at,
                    ),
                    **(
                        {
                            "bootstrap_crutch_retirement": bootstrap_crutch_retirement(
                                self,
                                value.checkout.bootstrap_crutch,
                            )
                        }
                        if value.checkout.bootstrap_crutch is not None
                        else {}
                    ),
                }
                for key, value in sorted(self.region_leases.items())
            },
            "region_lease_authority_observed_at": observed_at,
            "active_context": {
                "assumption": self.active_assumption,
                "fibre": self.active_fibre,
            },
            "corpus_heads": dict(sorted(self.corpus_heads.items())),
            "materializations": {
                key: value.to_dict() for key, value in sorted(self.materializations.items())
            },
            "up_acts": {key: value.to_dict() for key, value in sorted(self.up_acts.items())},
            "up_events": dict(sorted(self.up_events.items())),
            "down_acts": {key: value.to_dict() for key, value in sorted(self.down_acts.items())},
            "grade_axis_contracts": {
                key: value.to_dict() for key, value in sorted(self.grade_axis_contracts.items())
            },
            "graph": {
                "schema_version": "atlas.conceptric-graph.v1",
                "object_count": len(self.graph_objects),
                "edge_count": len(self.graph_edges),
                "objects": {
                    key: value.to_dict() for key, value in sorted(self.graph_objects.items())
                },
                "edges": {key: value.to_dict() for key, value in sorted(self.graph_edges.items())},
            },
            "messages": {key: value.to_dict() for key, value in sorted(self.messages.items())},
            "message_migration_supersessions": {
                key: value.to_dict()
                for key, value in sorted(self.message_migration_supersessions.items())
            },
            "revision_spaces": [
                self.revision_topology(assumption, fibre)
                for assumption, fibre in sorted(set(self.revision_contexts.values()))
            ],
            "seat_cursors": {
                seat_id: [
                    {
                        "assumption": assumption,
                        "fibre": fibre,
                        "cursor": cursor,
                    }
                    for (stored_seat, assumption, fibre), cursor in sorted(
                        self.seat_cursors.items()
                    )
                    if stored_seat == seat_id
                ]
                for seat_id in sorted({key[0] for key in self.seat_cursors})
            },
            "permissions": {
                key: {
                    "request": request.to_dict(),
                    "decision": (
                        None
                        if key not in self.permission_decisions
                        else self.permission_decisions[key].to_dict()
                    ),
                }
                for key, request in sorted(self.permission_requests.items())
            },
            "reconstruction_proofs": {
                event_id: {
                    "evaluation": evaluation.to_dict(),
                    "assumption": self.repl_contexts[event_id][0],
                    "fibre": self.repl_contexts[event_id][1],
                    "actor": self.repl_contexts[event_id][2],
                }
                for event_id, evaluation in sorted(self.repl_evaluations.items())
                if evaluation.operation.value == "reconstruct"
            },
            "watchers": {
                watcher_id: {
                    "registration": registration.to_dict(),
                    "assumption": self.watcher_contexts[watcher_id][0],
                    "fibre": self.watcher_contexts[watcher_id][1],
                    "checkpoint": (
                        None
                        if watcher_id not in self.watcher_checkpoints
                        else self.watcher_checkpoints[watcher_id].to_dict()
                    ),
                }
                for watcher_id, registration in sorted(self.watchers.items())
            },
        }

    def pending_messages(
        self, seat_id: str, *, after_cursor: int, as_of: str
    ) -> tuple[SeatMessage, ...]:
        """Pure cursor query. Pulling is authoritative only once its result is appended."""

        now = _parsed_time(as_of)
        return tuple(
            record.message
            for record in sorted(self.messages.values(), key=lambda item: item.message.cursor)
            if record.message.recipient_seat_id == seat_id
            and record.message.cursor > after_cursor
            and record.status in {DeliveryState.QUEUED, DeliveryState.PULLED}
            and (record.assumption, record.fibre) == (self.active_assumption, self.active_fibre)
            and _parsed_time(record.message.expires_at) > now
        )

    def cursor_for(self, seat_id: str) -> int:
        """The durable global-history position for this seat in the active fibre."""

        if self.active_assumption is None or self.active_fibre is None:
            return 0
        return self.seat_cursors.get((seat_id, self.active_assumption, self.active_fibre), 0)

    def revision_topology(self, assumption: str, fibre: str) -> dict[str, Any]:
        """Derive both directions and the live frontier from n-ary revision acts."""

        acts = {
            revision_id: act
            for revision_id, act in self.revision_acts.items()
            if self.revision_contexts[revision_id] == (assumption, fibre)
        }
        successors: dict[str, set[str]] = {}
        predecessors: dict[str, set[str]] = {}
        consumed: set[str] = set()
        produced: set[str] = set()
        for act in acts.values():
            consumed.update(act.supersedes)
            produced.update(act.produces)
            for source in act.supersedes:
                successors.setdefault(source, set()).update(act.produces)
            for target in act.produces:
                predecessors.setdefault(target, set()).update(act.supersedes)
        nodes = consumed | produced
        roots = nodes - produced
        frontier = nodes - consumed
        return {
            "schema_version": "atlas.revision-space/1",
            "assumption": assumption,
            "fibre": fibre,
            "acts": {revision_id: act.to_dict() for revision_id, act in sorted(acts.items())},
            "successors": {node: sorted(values) for node, values in sorted(successors.items())},
            "predecessors": {node: sorted(values) for node, values in sorted(predecessors.items())},
            "roots": sorted(roots),
            "live_frontier": sorted(frontier),
        }

    def revision_frontier(self, node_ref: str, *, assumption: str, fibre: str) -> dict[str, Any]:
        """Resolve one historical node to its exact fibre-local live frontier."""

        topology = self.revision_topology(assumption, fibre)
        successors = topology["successors"]
        known = set(topology["roots"]) | set(topology["live_frontier"])
        known.update(successors)
        known.update(topology["predecessors"])
        if node_ref not in known:
            return {
                "schema_version": "atlas.revision-frontier/1",
                "node_ref": node_ref,
                "assumption": assumption,
                "fibre": fibre,
                "status": "UNKNOWN",
                "frontier": [],
                "visited": [],
            }
        pending = [node_ref]
        visited: set[str] = set()
        frontier: set[str] = set()
        while pending:
            current = pending.pop()
            if current in visited:
                # A legitimate merge reaches the same descendant through several ancestors.
                # Cycles are refused at the append door; revisiting a fully derived node here is
                # convergence, not evidence of a cycle.
                continue
            visited.add(current)
            next_nodes = successors.get(current, [])
            if next_nodes:
                pending.extend(reversed(next_nodes))
            else:
                frontier.add(current)
        return {
            "schema_version": "atlas.revision-frontier/1",
            "node_ref": node_ref,
            "assumption": assumption,
            "fibre": fibre,
            "status": "CURRENT" if frontier == {node_ref} else "SUPERSEDED",
            "frontier": sorted(frontier),
            "visited": sorted(visited),
        }


def _with_event(state: ConceptricState, event: AtlasEvent, **changes: Any) -> ConceptricState:
    return replace(
        state,
        event_ids=(*state.event_ids, event.event_id),
        head_event_id=event.event_id,
        event_count=state.event_count + 1,
        **changes,
    )


def _require_context(state: ConceptricState, assumption: str, fibre: str) -> None:
    if (assumption, fibre) != (state.active_assumption, state.active_fibre):
        raise StateTransitionRefused(
            "event does not inhabit the active assumption fibre",
            active_assumption=state.active_assumption,
            active_fibre=state.active_fibre,
            event_assumption=assumption,
            event_fibre=fibre,
        )


def _revision_adjacency(state: ConceptricState, assumption: str, fibre: str) -> dict[str, set[str]]:
    adjacency: dict[str, set[str]] = {}
    for revision_id, act in state.revision_acts.items():
        if state.revision_contexts[revision_id] != (assumption, fibre):
            continue
        for source in act.supersedes:
            adjacency.setdefault(source, set()).update(act.produces)
    return adjacency


def _revision_reaches(adjacency: Mapping[str, set[str]], start: str, target: str) -> bool:
    pending = [start]
    visited: set[str] = set()
    while pending:
        current = pending.pop()
        if current == target:
            return True
        if current in visited:
            continue
        visited.add(current)
        pending.extend(adjacency.get(current, ()))
    return False


def _revision_node_object_id(assumption: str, fibre: str, node_ref: str) -> str:
    return "revision-node:" + chash(
        {"assumption": assumption, "fibre": fibre, "node_ref": node_ref}
    ).removeprefix("sha256:")


def _require_seat(state: ConceptricState, seat_id: str) -> SeatState:
    seat = state.seats.get(seat_id)
    if seat is None or seat.status == SeatStatus.CLOSED:
        raise StateTransitionRefused("logical seat is not live", seat_id=seat_id)
    return seat


def _content_handle(value: str) -> str:
    """Return a content address without pretending an external handle names local bytes."""

    if value.startswith("sha256:") and len(value) == 71:
        return value
    return chash({"external_handle": value})


def _handle_provenance(handle: str) -> tuple[SourceRef, ...]:
    digest = _content_handle(handle)
    return (SourceRef("content-address", digest, f"handle:{handle}"),)


def _control_grade(source: str | int, target: str | int) -> GradeAxis:
    return GradeAxis(
        CONTROL_AXIS_CONTRACT.contract_id,
        CONTROL_AXIS_CONTRACT.axis,
        source,
        target,
    )


def _axis_positions(
    state: ConceptricState, grade_axis: GradeAxis
) -> tuple[GradeAxisContract, int, int]:
    contract = state.grade_axis_contracts.get(grade_axis.contract_id)
    if contract is None:
        raise StateTransitionRefused("graph or movement cites unknown grade-axis contract")
    if grade_axis.axis != contract.axis:
        raise StateTransitionRefused("grade axis contradicts its ordering contract")
    try:
        source_grade = contract.coarse_to_fine.index(grade_axis.from_coordinate)
        target_grade = contract.coarse_to_fine.index(grade_axis.to_coordinate)
    except ValueError as exc:
        raise StateTransitionRefused(
            "grade coordinate is absent from its ordering contract"
        ) from exc
    return contract, source_grade, target_grade


def _verify_direction(direction: MoveDirection, source_grade: int, target_grade: int) -> None:
    if direction == MoveDirection.DOWN and target_grade <= source_grade:
        raise StateTransitionRefused(
            "down direction must move toward a strictly finer contracted grade"
        )
    if direction == MoveDirection.UP and target_grade >= source_grade:
        raise StateTransitionRefused(
            "up direction must move toward a strictly coarser contracted grade"
        )
    if direction in {MoveDirection.LATERAL, MoveDirection.CONJUGATE} and (
        target_grade != source_grade
    ):
        raise StateTransitionRefused(
            "lateral and conjugate directions must preserve contracted grade"
        )


def _with_graph_object(state: ConceptricState, item: ConceptricObject) -> ConceptricState:
    contract = state.grade_axis_contracts.get(item.grade_contract_id)
    if contract is None:
        raise StateTransitionRefused("object cites unknown grade-axis contract")
    if item.grade_coordinate not in contract.coarse_to_fine:
        raise StateTransitionRefused("object grade is absent from its ordering contract")
    existing = state.graph_objects.get(item.object_id)
    if existing is not None:
        if existing != item:
            raise StateTransitionRefused(
                "object id already resolves to different immutable content",
                object_id=item.object_id,
            )
        return state
    objects = dict(state.graph_objects)
    objects[item.object_id] = item
    return replace(state, graph_objects=objects)


def _with_graph_edge(state: ConceptricState, edge: ConceptricEdge) -> ConceptricState:
    source = state.graph_objects.get(edge.source_object_id)
    target = state.graph_objects.get(edge.target_object_id)
    missing = [
        object_id
        for object_id, item in (
            (edge.source_object_id, source),
            (edge.target_object_id, target),
        )
        if item is None
    ]
    if missing:
        raise StateTransitionRefused(
            "conceptric edge endpoint does not resolve", object_ids=missing
        )
    assert source is not None and target is not None
    _contract, source_grade, target_grade = _axis_positions(state, edge.grade_axis)
    if (
        source.grade_contract_id != edge.grade_axis.contract_id
        or target.grade_contract_id != edge.grade_axis.contract_id
        or source.grade_coordinate != edge.grade_axis.from_coordinate
        or target.grade_coordinate != edge.grade_axis.to_coordinate
    ):
        raise StateTransitionRefused("edge grade does not match its resolved endpoint grades")
    _verify_direction(edge.direction, source_grade, target_grade)
    contextual_endpoints = {
        (item.assumption, item.fibre) for item in (source, target) if item.assumption is not None
    }
    if edge.assumption is None:
        if edge.direction == MoveDirection.TRANSPORT:
            raise StateTransitionRefused("transport edge must declare its destination fibre")
    elif edge.direction == MoveDirection.TRANSPORT:
        transport = state.transports.get(str(edge.transport_id))
        if transport is None:
            raise StateTransitionRefused("edge cites unknown fibre transport")
        expected = {
            (transport.from_assumption, transport.from_fibre),
            (transport.to_assumption, transport.to_fibre),
        }
        if contextual_endpoints != expected or (edge.assumption, edge.fibre) != (
            transport.to_assumption,
            transport.to_fibre,
        ):
            raise StateTransitionRefused("edge endpoints contradict transport receipt")
    elif contextual_endpoints - {(edge.assumption, edge.fibre)}:
        raise StateTransitionRefused("edge cannot silently cross assumption fibres")
    existing = state.graph_edges.get(edge.edge_id)
    if existing is not None:
        if existing != edge:
            raise StateTransitionRefused(
                "edge id already resolves to different topology", edge_id=edge.edge_id
            )
        return state
    edges = dict(state.graph_edges)
    edges[edge.edge_id] = edge
    return replace(state, graph_edges=edges)


def _object(
    event: AtlasEvent,
    *,
    object_id: str,
    kind: str,
    content_handle: str,
    coordinate: str | int,
    contextual: bool,
    attributes: Mapping[str, Any],
    grade_contract_id: str = CONTROL_AXIS_CONTRACT.contract_id,
) -> ConceptricObject:
    return ConceptricObject(
        object_id,
        kind,
        _content_handle(content_handle),
        event.assumption if contextual else None,
        event.fibre if contextual else None,
        grade_contract_id,
        coordinate,
        event.provenance,
        dict(attributes),
    )


def _with_context_object(
    state: ConceptricState,
    event: AtlasEvent,
    assumption: str,
    fibre: str,
) -> tuple[ConceptricState, str]:
    """Declare one stable context subject without versioning it by observing provenance."""

    identity = {"assumption": assumption, "fibre": fibre}
    object_id = "context:" + chash(identity).removeprefix("sha256:")
    candidate = _object(
        event,
        object_id=object_id,
        kind="assumption-fibre",
        content_handle=chash(identity),
        coordinate="context",
        contextual=True,
        attributes=identity,
    )
    existing = state.graph_objects.get(object_id)
    if existing is None:
        return _with_graph_object(state, candidate), object_id
    # The first declaration's exact provenance remains custody for the stable subject.  A later
    # transport observes the same context from a different source root; that provenance belongs
    # to the transport edge/event, not to a new immutable version of the context object.
    if existing != replace(candidate, provenance=existing.provenance):
        raise StateTransitionRefused(
            "stable context id contradicts its semantic identity", object_id=object_id
        )
    return state, object_id


def _edge(
    state: ConceptricState,
    event: AtlasEvent,
    *,
    relation: str,
    source_object_id: str,
    target_object_id: str,
    direction: MoveDirection,
    operator: str,
    contextual: bool,
    transport_id: str | None = None,
) -> ConceptricEdge:
    source = state.graph_objects[source_object_id]
    target = state.graph_objects[target_object_id]
    identity = {
        "relation": relation,
        "source": source_object_id,
        "target": target_object_id,
        "direction": direction.value,
        "assumption": event.assumption if contextual else None,
        "fibre": event.fibre if contextual else None,
        "operator": operator,
        "generation": event.event_id,
        "transport_id": transport_id,
    }
    return ConceptricEdge(
        "edge:" + chash(identity).removeprefix("sha256:"),
        relation,
        source_object_id,
        target_object_id,
        direction,
        event.assumption if contextual else None,
        event.fibre if contextual else None,
        operator,
        GradeAxis(
            source.grade_contract_id,
            state.grade_axis_contracts[source.grade_contract_id].axis,
            source.grade_coordinate,
            target.grade_coordinate,
        ),
        event.provenance,
        event.residual,
        event.event_id,
        transport_id,
    )


def _connect(
    state: ConceptricState,
    event: AtlasEvent,
    *,
    relation: str,
    source_object_id: str,
    target_object_id: str,
    direction: MoveDirection = MoveDirection.OUTWARD,
    operator: str = "typed-history-projection",
    contextual: bool = False,
    transport_id: str | None = None,
) -> ConceptricState:
    return _with_graph_edge(
        state,
        _edge(
            state,
            event,
            relation=relation,
            source_object_id=source_object_id,
            target_object_id=target_object_id,
            direction=direction,
            operator=operator,
            contextual=contextual,
            transport_id=transport_id,
        ),
    )


def _event_object_id(event_id: str) -> str:
    return f"event:{event_id}"


def _source_object_id(source_id: str, digest: str) -> str:
    return "source:" + chash({"source_id": source_id, "digest": digest}).removeprefix("sha256:")


def _graphize_event(state: ConceptricState, event: AtlasEvent) -> ConceptricState:
    """Deposit the universal event/provenance topology before its typed specialization."""

    event_object_id = _event_object_id(event.event_id)
    state = _with_graph_object(
        state,
        _object(
            event,
            object_id=event_object_id,
            kind="atlas-event",
            content_handle=event.event_id,
            coordinate="event",
            contextual=event.assumption is not None,
            attributes={
                "event_id": event.event_id,
                "event_kind": event.kind.value,
                "subject": event.subject,
                "validity": event.validity.value,
            },
        ),
    )
    for source_ref in event.provenance:
        source_object_id = _source_object_id(source_ref.source_id, source_ref.digest)
        state = _with_graph_object(
            state,
            ConceptricObject(
                source_object_id,
                "provenance-source",
                _content_handle(source_ref.digest),
                None,
                None,
                CONTROL_AXIS_CONTRACT.contract_id,
                "content",
                (source_ref,),
                {"source_id": source_ref.source_id, "locator": source_ref.locator},
            ),
        )
        state = _connect(
            state,
            event,
            relation="provenance-of",
            source_object_id=source_object_id,
            target_object_id=event_object_id,
        )
    for cause in event.causation_ids:
        cause_object_id = _event_object_id(cause)
        if cause_object_id not in state.graph_objects:
            raise StateTransitionRefused(
                "causation edge cannot resolve its event object", event_id=cause
            )
        state = _connect(
            state,
            event,
            relation="causes",
            source_object_id=cause_object_id,
            target_object_id=event_object_id,
            direction=MoveDirection.LINEAGE,
        )
    return state


def _message_reconstruction_event_id(
    state: ConceptricState,
    acknowledgement_event_id: str,
) -> str:
    acknowledgement_object_id = f"acknowledgement:{acknowledgement_event_id}"
    proved_by = {
        edge.source_object_id.removeprefix("reconstruction:")
        for edge in state.graph_edges.values()
        if edge.relation == "proved-by"
        and edge.target_object_id == acknowledgement_object_id
        and edge.source_object_id.startswith("reconstruction:")
    }
    if len(proved_by) != 1:
        raise StateTransitionRefused(
            "delivered replacement must resolve one exact reconstruction event",
            acknowledgement_event_id=acknowledgement_event_id,
            reconstruction_event_ids=sorted(proved_by),
        )
    return next(iter(proved_by))


def derive_message_migration_recovery_entries(
    state: ConceptricState,
    *,
    replacement_message_id: str,
) -> tuple[
    tuple[MessageMigrationRecoveryEntry, ...],
    str,
    str,
]:
    """Derive one exact legacy bundle from a delivered replacement's typed roots.

    The selector deliberately accepts no historical message ids.  The replacement declares an
    ordered ``source_N`` body frontier and one typed-descent correlation; every source must resolve
    bijectively to one earlier pulled foreign-context message and one exact materialization.
    """

    replacement = state.messages.get(replacement_message_id)
    if replacement is None:
        raise StateTransitionRefused(
            "migration recovery cites unknown replacement",
            replacement_message_id=replacement_message_id,
        )
    if replacement.status != DeliveryState.DELIVERED:
        raise StateTransitionRefused(
            "migration recovery replacement must have exact delivered reconstruction proof",
            status=replacement.status.value,
        )
    if replacement.acknowledgement_event_id is None:
        raise StateTransitionRefused(
            "migration recovery replacement lacks an acknowledgement event"
        )

    roots_by_index: dict[int, tuple[str, str]] = {}
    for key, handle in replacement.message.dependency_roots.items():
        prefix, separator, index_text = key.partition("_")
        if prefix != "source" or separator != "_" or not index_text.isdigit():
            continue
        index = int(index_text)
        if index < 1 or key != f"source_{index}" or index in roots_by_index:
            raise StateTransitionRefused(
                "migration recovery source roots are not canonically indexed",
                source_key=key,
            )
        roots_by_index[index] = (key, handle)
    expected_indexes = set(range(1, len(roots_by_index) + 1))
    if not roots_by_index or set(roots_by_index) != expected_indexes:
        raise StateTransitionRefused(
            "migration recovery source roots must be nonempty and contiguous",
            source_indexes=sorted(roots_by_index),
        )
    source_handles = [roots_by_index[index][1] for index in sorted(roots_by_index)]
    if len(set(source_handles)) != len(source_handles):
        raise StateTransitionRefused("migration recovery source body handles must be unique")

    correlation = replacement.message.dependency_roots.get("reconstruction_correlation")
    if not isinstance(correlation, str) or not correlation.strip():
        raise StateTransitionRefused(
            "migration recovery replacement lacks one reconstruction correlation"
        )

    # The replacement may not cherry-pick a convenient subset.  Its contiguous source frontier
    # must equal every eligible historical obligation in cursor order; an omitted extra row is a
    # refusal, not a residual silently left behind after an apparently successful migration.
    eligible = sorted(
        (
            candidate
            for candidate in state.messages.values()
            if candidate.message.sender_seat_id == replacement.message.sender_seat_id
            and candidate.message.recipient_seat_id == replacement.message.recipient_seat_id
            and candidate.message.cursor < replacement.message.cursor
            and candidate.status == DeliveryState.PULLED
            and (candidate.assumption, candidate.fibre)
            != (replacement.assumption, replacement.fibre)
        ),
        key=lambda candidate: candidate.message.cursor,
    )
    eligible_handles = [candidate.message.body_handle for candidate in eligible]
    if source_handles != eligible_handles:
        raise StateTransitionRefused(
            "migration recovery source roots do not exhaust the ordered historical bundle",
            declared=source_handles,
            eligible_message_ids=[candidate.message.message_id for candidate in eligible],
            eligible_body_handles=eligible_handles,
        )
    if len({candidate.message.message_id for candidate in eligible}) != len(eligible) or len(
        set(eligible_handles)
    ) != len(eligible_handles):
        raise StateTransitionRefused(
            "migration recovery historical bundle is not bijective",
            eligible_message_ids=[candidate.message.message_id for candidate in eligible],
            eligible_body_handles=eligible_handles,
        )

    correlated_materializations: dict[str, AtlasEvent] = {
        event_id: materialization_event
        for event_id, materialization_event in state.materialization_events.items()
        if materialization_event.correlation_id == correlation
    }
    if len(correlated_materializations) != len(source_handles):
        raise StateTransitionRefused(
            "migration recovery correlation does not resolve exactly the source frontier",
            expected=len(source_handles),
            got=len(correlated_materializations),
        )
    materializations_by_start: dict[str, list[tuple[str, MaterializedReconstruction]]] = {}
    for event_id, materialization_event in correlated_materializations.items():
        materialized = MaterializedReconstruction.from_dict(materialization_event.payload)
        materializations_by_start.setdefault(materialized.start_handle, []).append(
            (event_id, materialized)
        )

    positions = {event_id: index for index, event_id in enumerate(state.event_ids)}
    replacement_send_position = positions[replacement.sent_event_id]
    entries: list[MessageMigrationRecoveryEntry] = []
    for index, candidate in zip(sorted(roots_by_index), eligible, strict=True):
        source_key, body_handle = roots_by_index[index]
        materializations = materializations_by_start.get(candidate.message.message_id, [])
        if len(materializations) != 1:
            raise StateTransitionRefused(
                "migration recovery source lacks one exact typed materialization",
                message_id=candidate.message.message_id,
                materialization_event_ids=[row[0] for row in materializations],
            )
        materialization_event_id, materialized = materializations[0]
        if not (
            positions[candidate.sent_event_id]
            < positions[materialization_event_id]
            < replacement_send_position
        ):
            raise StateTransitionRefused(
                "migration recovery evidence must order send before materialization before replacement",
                message_id=candidate.message.message_id,
                sent_event_id=candidate.sent_event_id,
                materialization_event_id=materialization_event_id,
                replacement_sent_event_id=replacement.sent_event_id,
            )
        if (
            materialized.result_handles != (body_handle,)
            or materialized.coverage != 1.0
            or materialized.residual.status != ResidualStatus.WITHIN_BOUND
            or (materialized.assumption, materialized.fibre)
            != (replacement.assumption, replacement.fibre)
        ):
            raise StateTransitionRefused(
                "migration recovery materialization is not an exact complete source proof",
                message_id=candidate.message.message_id,
                materialization_event_id=materialization_event_id,
            )
        entries.append(
            MessageMigrationRecoveryEntry(
                source_key=source_key,
                message_id=candidate.message.message_id,
                body_handle=body_handle,
                materialization_event_id=materialization_event_id,
            )
        )

    reconstruction_event_id = _message_reconstruction_event_id(
        state,
        replacement.acknowledgement_event_id,
    )
    return tuple(entries), correlation, reconstruction_event_id


def apply_event(state: ConceptricState, event: AtlasEvent) -> ConceptricState:
    """Validate and apply exactly one event. This is the sole semantic transition door."""

    event.verify_id()
    missing_causes = sorted(set(event.causation_ids) - set(state.event_ids))
    if missing_causes:
        raise StateTransitionRefused("event cites unknown causes", causation_ids=missing_causes)
    state = _graphize_event(state, event)

    if event.kind == EventKind.LIFECYCLE:
        transition = LifecycleTransition.from_dict(event.payload)
        if transition.from_phase != state.lifecycle:
            raise StateTransitionRefused(
                "lifecycle event does not start at materialized phase",
                expected=state.lifecycle.value,
                got=transition.from_phase.value,
            )
        return _with_event(state, event, lifecycle=transition.to_phase)

    if state.lifecycle == LifecyclePhase.SLEEPING:
        raise StateTransitionRefused("sleeping conceptric accepts only wake or cold-wake")

    # Refusals and stale evaluations remain auditable but cannot mutate the materialized world.
    if event.validity in {Validity.REFUSED, Validity.STALE}:
        return _with_event(state, event)

    if event.kind == EventKind.OBJECT:
        item = ConceptricObject.from_dict(event.payload)
        if (event.assumption, event.fibre) != (item.assumption, item.fibre):
            raise StateTransitionRefused("object event context contradicts its object")
        state = _with_graph_object(state, item)
        if item.kind == GOAL_CLOSURE_PROBE_SET_KIND:
            probe_set = GoalClosureProbeSet.from_dict(item.attributes)
            if item.content_handle != probe_set.handle:
                raise StateTransitionRefused(
                    "goal closure probe-set object contradicts its content handle"
                )
            expected_id = f"goal-closure-probe-set:{probe_set.handle}"
            if item.object_id != expected_id:
                raise StateTransitionRefused(
                    "goal closure probe-set object contradicts its canonical identity",
                    expected=expected_id,
                    got=item.object_id,
                )
            if (probe_set.assumption, probe_set.fibre) != (
                item.assumption,
                item.fibre,
            ):
                raise StateTransitionRefused(
                    "goal closure probe set contradicts its object context"
                )
            probe_sets = dict(state.goal_closure_probe_sets)
            probe_events = dict(state.goal_closure_probe_events)
            if probe_set.handle in probe_sets:
                raise StateTransitionRefused("goal closure probe set is already declared")
            probe_sets[probe_set.handle] = probe_set
            probe_events[probe_set.handle] = event.event_id
            state = replace(
                state,
                goal_closure_probe_sets=probe_sets,
                goal_closure_probe_events=probe_events,
            )
        # The universal event object inhabits the control axis.  A domain object can inhabit
        # any declared grade axis, and ``ConceptricEdge`` intentionally permits only one named
        # ordering contract per edge.  Do not fabricate a cross-axis grade merely to draw a
        # declaration arrow: the event payload plus the object's provenance is the declaration
        # relation for non-control objects.  Same-axis control objects retain the graph edge.
        if item.grade_contract_id == CONTROL_AXIS_CONTRACT.contract_id:
            state = _connect(
                state,
                event,
                relation="declares-object",
                source_object_id=_event_object_id(event.event_id),
                target_object_id=item.object_id,
            )
        return _with_event(state, event)

    if event.kind == EventKind.EDGE:
        edge = ConceptricEdge.from_dict(event.payload)
        if (event.assumption, event.fibre) != (edge.assumption, edge.fibre):
            raise StateTransitionRefused("edge event context contradicts its edge")
        state = _with_graph_edge(state, edge)
        return _with_event(state, event)

    if event.kind == EventKind.SEAT:
        transition = SeatTransition.from_dict(event.payload)
        existing = state.seats.get(transition.seat_id)
        actual = None if existing is None else existing.status
        if transition.from_status != actual:
            raise StateTransitionRefused(
                "seat transition does not start at materialized status",
                seat_id=transition.seat_id,
                expected=None if actual is None else actual.value,
            )
        if existing is not None and existing.role != transition.role.value:
            raise StateTransitionRefused("logical seat role cannot change during succession")
        if (
            existing is not None
            and transition.action != SeatAction.ACTIVATE
            and transition.holder_ref != existing.holder_ref
        ):
            raise StateTransitionRefused("only activation may replace a logical seat holder")
        seats = dict(state.seats)
        seat_registration_event_ids = dict(state.seat_registration_event_ids)
        # Every chair transition supersedes the registration event named by an occupancy
        # binding.  Retaining that occupancy would let CLOSE, RELAY, or ACTIVATE leave a prior
        # provider session with routing authority.  The successor must reconstruct, join, and
        # bind again against the new registration event before it can route as this chair.
        seat_occupancies = dict(state.seat_occupancies)
        seat_occupancies.pop(transition.seat_id, None)
        seats[transition.seat_id] = SeatState(
            role=transition.role.value,
            status=transition.to_status,
            charter_ref=transition.charter_ref,
            holder_ref=transition.holder_ref,
        )
        seat_registration_event_ids[transition.seat_id] = event.event_id
        seat_object_id = f"seat:{transition.seat_id}"
        if seat_object_id not in state.graph_objects:
            state = _with_graph_object(
                state,
                _object(
                    event,
                    object_id=seat_object_id,
                    kind="logical-seat",
                    content_handle=chash(
                        {"seat_id": transition.seat_id, "role": transition.role.value}
                    ),
                    coordinate="seat",
                    contextual=False,
                    attributes={
                        "seat_id": transition.seat_id,
                        "role": transition.role.value,
                    },
                ),
            )
        state = _connect(
            state,
            event,
            relation="mutates-seat",
            source_object_id=_event_object_id(event.event_id),
            target_object_id=seat_object_id,
        )
        session_object_id = "session:" + chash({"holder_ref": transition.holder_ref}).removeprefix(
            "sha256:"
        )
        if session_object_id not in state.graph_objects:
            state = _with_graph_object(
                state,
                _object(
                    event,
                    object_id=session_object_id,
                    kind="provider-session-holder",
                    content_handle=chash({"holder_ref": transition.holder_ref}),
                    coordinate="session",
                    contextual=False,
                    attributes={"holder_ref": transition.holder_ref},
                ),
            )
        state = _connect(
            state,
            event,
            relation="holds-seat",
            source_object_id=session_object_id,
            target_object_id=seat_object_id,
            operator="logical-seat-succession",
        )
        return _with_event(
            state,
            event,
            seats=seats,
            seat_registration_event_ids=seat_registration_event_ids,
            seat_occupancies=seat_occupancies,
        )

    if event.kind == EventKind.SEAT_JOIN:
        join_schema = event.payload.get("schema_version")
        starts_lifecycle_cutover = (
            join_schema == SeatJoinReceipt.SCHEMA_VERSION
            and state.seat_lifecycle_cutover_event_id is None
        )
        if (
            join_schema == SeatJoinReceipt.LEGACY_V1_SCHEMA_VERSION
            and state.seat_lifecycle_cutover_event_id is not None
        ):
            raise StateTransitionRefused(
                "legacy seat join appears after the lifecycle cutover",
                cutover_event_id=state.seat_lifecycle_cutover_event_id,
            )
        joined = SeatJoinReceipt.from_dict(event.payload)
        registered = state.seats.get(joined.seat_id)
        predecessor_occupancy = state.seat_occupancies.get(joined.seat_id)
        if registered is None or registered.status == SeatStatus.CLOSED:
            raise StateTransitionRefused("only a registered live chair can be joined")
        if joined.registered_role.value != registered.role:
            raise StateTransitionRefused("seat join contradicts the registered chair role")
        if joined.registered_holder_ref != registered.holder_ref:
            raise StateTransitionRefused("seat join contradicts the registered holder snapshot")
        if event.actor != joined.function:
            raise StateTransitionRefused("seat join actor must be its claimed function")
        if event.subject != f"seat:{joined.seat_id}:occupancy":
            raise StateTransitionRefused("seat join subject must identify its occupancy")
        if (event.assumption, event.fibre) != (
            state.active_assumption,
            state.active_fibre,
        ):
            raise StateTransitionRefused("seat join must inhabit the active assumption fibre")
        if joined.information_cursor > state.event_count:
            raise StateTransitionRefused("seat join information cursor is ahead of Atlas")
        if not any(ref.digest == joined.information_proof_handle for ref in event.provenance):
            raise StateTransitionRefused("seat join does not carry its information proof")
        if not set(joined.reconstruction_event_ids).issubset(event.causation_ids):
            raise StateTransitionRefused(
                "seat join must causally carry each startup reconstruction proof"
            )

        pending_predecessor_binding_event_id = None
        retired_binding_event_ids: tuple[str, ...] = ()
        if predecessor_occupancy is not None and predecessor_occupancy.routing_authority:
            legacy_plain_replacement = (
                event.payload.get("schema_version") == SeatJoinReceipt.LEGACY_V1_SCHEMA_VERSION
                and predecessor_occupancy.join.holder_ref != joined.holder_ref
            )
            # Historical v1 joins replaced a provider holder without carrying a predecessor
            # edge.  Replaying that immutable prefix must preserve its original meaning, but the
            # current schema may never recreate the reset: it names the exact authoritative
            # binding and the following v4 binding retires it in the same append packet.
            if legacy_plain_replacement:
                pass
            else:
                if (
                    event.payload.get("schema_version") != SeatJoinReceipt.SCHEMA_VERSION
                    and predecessor_occupancy.join.holder_ref != joined.holder_ref
                ):
                    raise StateTransitionRefused(
                        "only historical v1 may replay an untyped provider holder replacement",
                        seat_id=joined.seat_id,
                        current_holder=predecessor_occupancy.join.holder_ref,
                        proposed_holder=joined.holder_ref,
                    )
                if (
                    event.payload.get("schema_version") == SeatJoinReceipt.SCHEMA_VERSION
                    and not joined.provider_identity_generation
                ):
                    raise StateTransitionRefused(
                        "current seat handover requires a typed successor watcher generation",
                        seat_id=joined.seat_id,
                    )
                if predecessor_occupancy.join.function != joined.function:
                    raise StateTransitionRefused("seat handover cannot change function")
                same_seat_binding_causes = {
                    cause
                    for cause in event.causation_ids
                    if cause in state.seat_bindings
                    and state.seat_bindings[cause].seat_id == joined.seat_id
                }
                expected_predecessor = predecessor_occupancy.binding_event_id
                assert expected_predecessor is not None
                if expected_predecessor not in same_seat_binding_causes:
                    raise StateTransitionRefused(
                        "current seat handover must causally name the current binding exactly",
                        expected_predecessor=expected_predecessor,
                    )
                if same_seat_binding_causes != {expected_predecessor}:
                    raise StateTransitionRefused(
                        "current seat handover has an ambiguous predecessor",
                        predecessor_binding_event_ids=sorted(same_seat_binding_causes),
                    )
                pending_predecessor_binding_event_id = expected_predecessor
                retired_binding_event_ids = predecessor_occupancy.retired_binding_event_ids

        joins = dict(state.seat_joins)
        joins[event.event_id] = joined
        # The first current-schema join is the one explicit v1 -> v2 authority boundary.
        # All prior occupancies remain immutable history, but none may survive that boundary as
        # reusable routing authority merely because its old binding still folds.  Preserve the
        # joined seat's exact predecessor above so its v4 binding can retire that lineage; every
        # other logical chair must independently reconstruct and bind under v2.
        occupancies = {} if starts_lifecycle_cutover else dict(state.seat_occupancies)
        occupancies[joined.seat_id] = SeatOccupancy(
            join=joined,
            join_event_id=event.event_id,
            joined_at=event.occurred_at,
            joined_cursor=state.event_count + 1,
            pending_predecessor_binding_event_id=(pending_predecessor_binding_event_id),
            retired_binding_event_ids=retired_binding_event_ids,
        )

        seat_object_id = f"seat:{joined.seat_id}"
        if seat_object_id not in state.graph_objects:
            raise StateTransitionRefused("seat join chair object does not resolve")
        session_object_id = "session:" + chash({"holder_ref": joined.holder_ref}).removeprefix(
            "sha256:"
        )
        if session_object_id not in state.graph_objects:
            state = _with_graph_object(
                state,
                _object(
                    event,
                    object_id=session_object_id,
                    kind="provider-session-occupant",
                    content_handle=chash(
                        {
                            "holder_ref": joined.holder_ref,
                            "function": joined.function.value,
                        }
                    ),
                    coordinate="session",
                    contextual=False,
                    attributes={
                        "holder_ref": joined.holder_ref,
                        "function": joined.function.value,
                    },
                ),
            )
        state = _connect(
            state,
            event,
            relation="observed-joining-seat",
            source_object_id=session_object_id,
            target_object_id=seat_object_id,
            operator="startup-mail-gate",
        )
        return _with_event(
            state,
            event,
            seat_joins=joins,
            seat_occupancies=occupancies,
            seat_lifecycle_cutover_event_id=(
                event.event_id
                if starts_lifecycle_cutover
                else state.seat_lifecycle_cutover_event_id
            ),
            seat_lifecycle_invalidated_legacy_occupancies=(
                dict(state.seat_occupancies)
                if starts_lifecycle_cutover
                else state.seat_lifecycle_invalidated_legacy_occupancies
            ),
        )

    if event.kind == EventKind.SEAT_OCCUPANCY_BINDING:
        if (
            event.payload.get("schema_version") != SeatOccupancyBinding.SCHEMA_VERSION
            and state.seat_lifecycle_cutover_event_id is not None
        ):
            raise StateTransitionRefused(
                "legacy seat binding appears after the lifecycle cutover",
                cutover_event_id=state.seat_lifecycle_cutover_event_id,
            )
        binding = SeatOccupancyBinding.from_dict(event.payload)
        registered = state.seats.get(binding.seat_id)
        occupancy = state.seat_occupancies.get(binding.seat_id)
        registration_event_id = state.seat_registration_event_ids.get(binding.seat_id)
        if registered is None or registered.status == SeatStatus.CLOSED:
            raise StateTransitionRefused("seat occupancy binding requires a registered live chair")
        if occupancy is None:
            raise StateTransitionRefused("seat occupancy binding requires the latest proved join")
        if binding.join_event_id != occupancy.join_event_id:
            raise StateTransitionRefused(
                "seat occupancy binding does not name the latest seat join"
            )
        if binding.registered_seat_event_id != registration_event_id:
            raise StateTransitionRefused(
                "seat occupancy binding does not name the latest seat registration"
            )
        if binding.registered_principal_ref != registered.holder_ref:
            raise StateTransitionRefused(
                "seat occupancy binding contradicts the registered logical principal"
            )
        if binding.provider_session_ref != occupancy.join.holder_ref:
            raise StateTransitionRefused(
                "seat occupancy binding contradicts the joined provider session"
            )
        if binding.function.value != registered.role or binding.function != occupancy.join.function:
            raise StateTransitionRefused(
                "seat occupancy binding function must equal the registered and joined role"
            )
        if binding.provider_identity_proof_handle != occupancy.join.information_proof_handle:
            raise StateTransitionRefused(
                "seat occupancy binding must carry the joined startup identity proof"
            )
        if event.actor != binding.function:
            raise StateTransitionRefused(
                "seat occupancy binding actor must be the registered function"
            )
        if event.subject != f"seat:{binding.seat_id}:binding":
            raise StateTransitionRefused(
                "seat occupancy binding subject must identify its logical chair"
            )
        if not {
            binding.join_event_id,
            binding.registered_seat_event_id,
        }.issubset(event.causation_ids):
            raise StateTransitionRefused(
                "seat occupancy binding must causally carry registration and join"
            )
        if not any(
            ref.digest == binding.provider_identity_proof_handle for ref in event.provenance
        ):
            raise StateTransitionRefused(
                "seat occupancy binding does not carry its provider identity proof"
            )

        legacy_binding = event.payload.get("schema_version") in {
            SeatOccupancyBinding.LEGACY_V1_SCHEMA_VERSION,
            SeatOccupancyBinding.LEGACY_V2_SCHEMA_VERSION,
            SeatOccupancyBinding.LEGACY_V3_SCHEMA_VERSION,
        }
        if not legacy_binding and not binding.provider_identity_generation:
            raise StateTransitionRefused(
                "seat occupancy binding requires the watcher identity generation"
            )
        if not legacy_binding:
            joined_generation = occupancy.join.provider_identity_generation
            if not joined_generation:
                raise StateTransitionRefused(
                    "seat occupancy binding requires a typed joined watcher generation"
                )
            if binding.provider_identity_generation != joined_generation:
                raise StateTransitionRefused(
                    "seat occupancy binding watcher generation contradicts the joined identity proof",
                    joined_provider_identity_generation=joined_generation,
                    binding_provider_identity_generation=(binding.provider_identity_generation),
                )

        predecessor_event_id = binding.predecessor_binding_event_id
        pending_predecessor = occupancy.pending_predecessor_binding_event_id
        retired_binding_event_ids = occupancy.retired_binding_event_ids
        retired_generations = dict(state.retired_seat_binding_generations)
        if predecessor_event_id is None:
            if pending_predecessor is not None:
                raise StateTransitionRefused(
                    "same-holder seat renewal binding omitted its exact predecessor"
                )
        else:
            if predecessor_event_id != pending_predecessor:
                raise StateTransitionRefused(
                    "seat binding renewal does not name the pending exact predecessor",
                    expected=pending_predecessor,
                    got=predecessor_event_id,
                )
            predecessor = state.seat_bindings.get(predecessor_event_id)
            if predecessor is None:
                raise StateTransitionRefused("seat binding renewal predecessor does not resolve")
            if predecessor_event_id in state.retired_seat_binding_event_ids:
                raise StateTransitionRefused("seat binding renewal predecessor is already retired")
            if (
                predecessor.seat_id != binding.seat_id
                or predecessor.registered_principal_ref != binding.registered_principal_ref
                or predecessor.function != binding.function
            ):
                raise StateTransitionRefused(
                    "seat binding renewal predecessor contradicts the successor identity"
                )
            if (
                predecessor.provider_session_ref != binding.provider_session_ref
                and event.payload.get("schema_version") != SeatOccupancyBinding.SCHEMA_VERSION
            ):
                raise StateTransitionRefused(
                    "only a current typed binding may hand over between provider holders"
                )
            if predecessor_event_id not in event.causation_ids:
                raise StateTransitionRefused(
                    "seat binding renewal must causally carry its exact predecessor"
                )
            replayed_retired_bindings = sorted(
                binding_event_id
                for binding_event_id in retired_binding_event_ids
                if state.retired_seat_binding_generations.get(binding_event_id)
                == binding.provider_identity_generation
            )
            if replayed_retired_bindings:
                raise StateTransitionRefused(
                    "seat binding renewal refuses a retired watcher identity generation",
                    provider_identity_generation=binding.provider_identity_generation,
                    retired_binding_event_ids=replayed_retired_bindings,
                )
            retired_generation = binding.retired_provider_identity_generation
            assert retired_generation is not None
            if (
                predecessor.provider_identity_generation is not None
                and predecessor.provider_identity_generation != retired_generation
            ):
                raise StateTransitionRefused(
                    "seat binding renewal retires the wrong predecessor generation"
                )
            retired_binding_event_ids = (
                *retired_binding_event_ids,
                predecessor_event_id,
            )
            retired_generations[predecessor_event_id] = retired_generation

        occupancies = dict(state.seat_occupancies)
        occupancies[binding.seat_id] = replace(
            occupancy,
            binding=binding,
            binding_event_id=event.event_id,
            bound_at=event.occurred_at,
            pending_predecessor_binding_event_id=None,
            retired_binding_event_ids=retired_binding_event_ids,
        )
        bindings = dict(state.seat_bindings)
        bindings[event.event_id] = binding
        state = _connect(
            state,
            event,
            relation="binds-provider-session",
            source_object_id="session:"
            + chash({"holder_ref": binding.provider_session_ref}).removeprefix("sha256:"),
            target_object_id=f"seat:{binding.seat_id}",
            operator="startup-provider-identity",
        )
        return _with_event(
            state,
            event,
            seat_occupancies=occupancies,
            seat_bindings=bindings,
            retired_seat_binding_event_ids=tuple(
                dict.fromkeys(
                    (
                        *state.retired_seat_binding_event_ids,
                        *retired_binding_event_ids,
                    )
                )
            ),
            retired_seat_binding_generations=retired_generations,
        )

    if event.kind == EventKind.REGION_CHECKOUT:
        checkout = RegionCheckout.from_dict(event.payload)
        _require_seat(state, checkout.seat_id)
        occupancy = state.seat_occupancies.get(checkout.seat_id)
        if occupancy is None:
            raise StateTransitionRefused("region checkout requires a proved seat join")
        if not occupancy.routing_authority:
            raise StateTransitionRefused(
                "region checkout requires an authoritative provider-session binding"
            )
        if (
            occupancy.join.holder_ref != checkout.holder_ref
            or occupancy.join.function != checkout.function
        ):
            raise StateTransitionRefused(
                "region checkout holder/function disagrees with latest seat occupancy"
            )
        if event.actor != checkout.function:
            raise StateTransitionRefused("region checkout actor must be its joined function")
        if event.subject != f"lease:{checkout.lease_id}":
            raise StateTransitionRefused("region checkout subject must identify its lease")
        _require_context(state, str(event.assumption), str(event.fibre))
        if _parsed_time(checkout.expires_at) <= _parsed_time(event.occurred_at):
            raise StateTransitionRefused("region checkout is already expired at introduction")
        if checkout.bootstrap_crutch is not None:
            retirement = bootstrap_crutch_retirement(state, checkout.bootstrap_crutch)
            if retirement["state"] == "RETIRED":
                raise StateTransitionRefused(
                    "bootstrap crutch retirement trigger is satisfied",
                    retirement=retirement,
                )
        if occupancy.join_event_id not in event.causation_ids:
            raise StateTransitionRefused("region checkout must causally carry its seat join")
        if occupancy.binding_event_id not in event.causation_ids:
            raise StateTransitionRefused(
                "region checkout must causally carry its occupancy binding"
            )
        if checkout.lease_id in state.region_leases:
            raise StateTransitionRefused("region checkout lease id already exists")
        for existing in state.region_leases.values():
            if not existing.held_at(event.occurred_at):
                continue
            existing_occupancy = state.seat_occupancies.get(existing.checkout.seat_id)
            if not existing.matches_occupancy(existing_occupancy):
                continue
            collision = next(
                (
                    (left, right)
                    for left in checkout.regions
                    for right in existing.checkout.regions
                    if _regions_overlap(left, right)
                ),
                None,
            )
            if collision is not None:
                raise StateTransitionRefused(
                    "region checkout overlaps a live lease",
                    requested=collision[0],
                    held=collision[1],
                    held_lease_id=existing.checkout.lease_id,
                    held_by=existing.checkout.holder_ref,
                )

        lease_object_id = f"lease:{checkout.lease_id}"
        state = _with_graph_object(
            state,
            _object(
                event,
                object_id=lease_object_id,
                kind="repository-region-lease",
                content_handle=chash(checkout.to_dict()),
                coordinate="authority",
                contextual=False,
                attributes={
                    "lease_id": checkout.lease_id,
                    "holder_ref": checkout.holder_ref,
                    "function": checkout.function.value,
                    "expires_at": checkout.expires_at,
                    "declaration_kind": checkout.declaration_kind.value,
                },
            ),
        )
        session_object_id = "session:" + chash({"holder_ref": checkout.holder_ref}).removeprefix(
            "sha256:"
        )
        state = _connect(
            state,
            event,
            relation="holds-region-authority",
            source_object_id=session_object_id,
            target_object_id=lease_object_id,
            operator="region-checkout",
        )
        for region in checkout.regions:
            region_object_id = "region:" + chash({"path": region}).removeprefix("sha256:")
            if region_object_id not in state.graph_objects:
                state = _with_graph_object(
                    state,
                    _object(
                        event,
                        object_id=region_object_id,
                        kind="repository-path-region",
                        content_handle=chash({"path": region}),
                        coordinate="repository-path",
                        contextual=False,
                        attributes={"path": region},
                    ),
                )
            state = _connect(
                state,
                event,
                relation="scopes-authority-over",
                source_object_id=lease_object_id,
                target_object_id=region_object_id,
                operator="region-checkout",
            )
        leases = dict(state.region_leases)
        leases[checkout.lease_id] = RegionLeaseState(
            checkout=checkout,
            checkout_event_id=event.event_id,
            checked_out_at=event.occurred_at,
            checkout_join_event_id=occupancy.join_event_id,
            checkout_binding_event_id=occupancy.binding_event_id,
            checkout_provider_identity_generation=(
                None
                if occupancy.binding is None
                else occupancy.binding.provider_identity_generation
            ),
        )
        return _with_event(state, event, region_leases=leases)

    if event.kind == EventKind.REGION_PUBLICATION_PREPARED:
        prepared = RegionPublicationPrepared.from_dict(event.payload)
        lease = state.region_leases.get(prepared.lease_id)
        if lease is None:
            raise StateTransitionRefused("publication prepare cites an unknown lease")
        if lease.checkin is not None or lease.publication is not None:
            raise StateTransitionRefused("publication prepare requires one open unused lease")
        checkout = lease.checkout
        occupancy = state.seat_occupancies.get(checkout.seat_id)
        if (
            prepared.seat_id != checkout.seat_id
            or prepared.holder_ref != checkout.holder_ref
            or prepared.function != checkout.function
            or prepared.checkout_event_id != lease.checkout_event_id
            or prepared.binding_event_id != lease.checkout_binding_event_id
            or prepared.provider_identity_generation
            != lease.checkout_provider_identity_generation
        ):
            raise StateTransitionRefused("publication prepare mismatches lease lineage")
        if not lease.held_at(event.occurred_at):
            raise StateTransitionRefused("publication prepare requires an unexpired lease")
        if not lease.matches_occupancy(occupancy):
            raise StateTransitionRefused("publication prepare authority is displaced")
        hook = prepared.forward_closure
        if hook.predecessor_event_id != state.head_event_id:
            raise StateTransitionRefused(
                "forward closure predecessor head mismatches the publication frontier"
            )
        if (
            hook.predecessor_frontier_root != prepared.affected_frontier_root
            or hook.expires_at != checkout.expires_at
        ):
            raise StateTransitionRefused(
                "forward closure mismatches the prepared publication frontier or lease"
            )
        expected_projection = region_forward_closure_finalized_projection(
            lease_id=prepared.lease_id,
            seat_id=prepared.seat_id,
            holder_ref=prepared.holder_ref,
            function=prepared.function,
            base_ref=prepared.base_ref,
            expected_old=prepared.expected_old,
            result_git_head=prepared.candidate_commit,
            candidate_tree=prepared.candidate_tree,
            patch_handle=prepared.patch_handle,
            custody_handle=prepared.custody_handle,
            affected_frontier_root=prepared.affected_frontier_root,
        )
        if (
            hook.finalized_projection_digest != chash(expected_projection)
            or prepared.forward_closure_root != hook.forward_closure_root
        ):
            raise StateTransitionRefused(
                "prepared publication forward closure does not rederive"
            )
        if event.actor != checkout.function:
            raise StateTransitionRefused("publication prepare actor must be its lease function")
        if event.subject != f"publication:{prepared.publication_id}":
            raise StateTransitionRefused("publication prepare subject mismatches its identity")
        _require_context(state, str(event.assumption), str(event.fibre))
        for required in (lease.checkout_event_id, lease.checkout_binding_event_id):
            if required not in event.causation_ids:
                raise StateTransitionRefused("publication prepare omits lease lineage causation")
        for path in prepared.committed_paths:
            if not _path_in_regions(path, checkout.regions):
                raise StateTransitionRefused(
                    "publication candidate escapes its leased scope", path=path
                )
        expected_publication_id = "region-publication:" + chash(
            prepared.identity_dict()
        ).removeprefix("sha256:")
        if prepared.publication_id != expected_publication_id:
            raise StateTransitionRefused("publication id does not match prepared custody")
        expected_recovery_root = chash(
            {
                "schema_version": "laplace.region-publication-recovery/1",
                "publication_id": prepared.publication_id,
                "prepared": prepared.identity_dict(),
            }
        )
        if prepared.recovery_root != expected_recovery_root:
            raise StateTransitionRefused("publication recovery root does not verify")
        leases = dict(state.region_leases)
        leases[prepared.lease_id] = replace(
            lease,
            publication=RegionPublicationState(
                prepared=prepared,
                prepared_event_id=event.event_id,
                prepared_at=event.occurred_at,
            ),
        )
        return _with_event(state, event, region_leases=leases)

    if event.kind == EventKind.REGION_PUBLICATION_SIGNED:
        signoff = RegionPublicationSignoff.from_dict(event.payload)
        lease = state.region_leases.get(signoff.lease_id)
        publication = None if lease is None else lease.publication
        if lease is None or publication is None:
            raise StateTransitionRefused("publication signoff cites no prepared saga")
        if publication.authorization is not None or publication.finalized is not None:
            raise StateTransitionRefused("publication signoff follows authorization")
        prepared = publication.prepared
        expected_function_order = (
            SeatRole.EGO,
            SeatRole.SENSORIUM,
            SeatRole.SUPEREGO,
        )
        if len(publication.signoffs) >= len(expected_function_order):
            raise StateTransitionRefused("publication already has the complete triad")
        expected_function = expected_function_order[len(publication.signoffs)]
        if signoff.signer_function != expected_function:
            raise StateTransitionRefused(
                "publication signoffs must be Ego then Aisthesis then Superego"
            )
        if signoff.signer_seat_id in {
            item.signoff.signer_seat_id for item in publication.signoffs
        }:
            raise StateTransitionRefused("one seat cannot sign two publication roles")
        exact = {
            "publication_id": prepared.publication_id,
            "lease_id": prepared.lease_id,
            "prepared_event_id": publication.prepared_event_id,
            "recovery_root": prepared.recovery_root,
            "candidate_commit": prepared.candidate_commit,
            "candidate_tree": prepared.candidate_tree,
            "patch_handle": prepared.patch_handle,
            "custody_handle": prepared.custody_handle,
            "affected_frontier_root": prepared.affected_frontier_root,
            "rehearsal_evidence_root": prepared.rehearsal_evidence_root,
            "forward_closure_root": prepared.forward_closure_root,
        }
        mismatches = {
            key: {"expected": value, "got": getattr(signoff, key)}
            for key, value in exact.items()
            if getattr(signoff, key) != value
        }
        if mismatches:
            raise StateTransitionRefused(
                "publication signoff mismatches prepared custody", mismatches=mismatches
            )
        occupancy = state.seat_occupancies.get(signoff.signer_seat_id)
        if not _publication_signoff_matches_occupancy(signoff, occupancy):
            raise StateTransitionRefused("publication signer lineage is not current")
        if _parsed_time(signoff.expires_at) <= _parsed_time(event.occurred_at):
            raise StateTransitionRefused("publication signoff is expired")
        if _parsed_time(signoff.expires_at) > _parsed_time(lease.checkout.expires_at):
            raise StateTransitionRefused("publication signoff exceeds its publication lease")
        prior_ids = tuple(item.event_id for item in publication.signoffs)
        expected_consumption = prior_ids if signoff.signer_function == SeatRole.SUPEREGO else ()
        if signoff.consumed_signoff_event_ids != expected_consumption:
            raise StateTransitionRefused(
                "Superego publication signoff does not consume the exact prior receipts"
            )
        if event.actor != signoff.signer_function:
            raise StateTransitionRefused("publication signoff actor mismatches its function")
        if event.subject != f"publication:{signoff.publication_id}":
            raise StateTransitionRefused("publication signoff subject mismatches")
        _require_context(state, str(event.assumption), str(event.fibre))
        required_causes = {
            publication.prepared_event_id,
            signoff.signer_binding_event_id,
            *signoff.consumed_signoff_event_ids,
        }
        if not required_causes.issubset(set(event.causation_ids)):
            raise StateTransitionRefused("publication signoff omits exact causation")
        leases = dict(state.region_leases)
        leases[signoff.lease_id] = replace(
            lease,
            publication=replace(
                publication,
                signoffs=(
                    *publication.signoffs,
                    RegionPublicationSignoffState(
                        signoff=signoff,
                        event_id=event.event_id,
                        signed_at=event.occurred_at,
                    ),
                ),
            ),
        )
        return _with_event(state, event, region_leases=leases)

    if event.kind == EventKind.REGION_PUBLICATION_AUTHORIZED:
        authorization = RegionPublicationAuthorization.from_dict(event.payload)
        lease = state.region_leases.get(authorization.lease_id)
        publication = None if lease is None else lease.publication
        if lease is None or publication is None:
            raise StateTransitionRefused("publication authorization cites no prepared saga")
        if publication.authorization is not None or publication.finalized is not None:
            raise StateTransitionRefused("publication authorization is already consumed")
        prepared = publication.prepared
        occupancy = state.seat_occupancies.get(lease.checkout.seat_id)
        if tuple(item.signoff.signer_function for item in publication.signoffs) != (
            SeatRole.EGO,
            SeatRole.SENSORIUM,
            SeatRole.SUPEREGO,
        ):
            raise StateTransitionRefused("publication authorization requires the exact triad")
        if len({item.signoff.signer_seat_id for item in publication.signoffs}) != 3:
            raise StateTransitionRefused("publication authorization requires distinct seats")
        for item in publication.signoffs:
            signer = item.signoff
            signer_occupancy = state.seat_occupancies.get(signer.signer_seat_id)
            if not _publication_signoff_matches_occupancy(signer, signer_occupancy):
                raise StateTransitionRefused("publication signer was replaced before authorization")
            if _parsed_time(signer.expires_at) <= _parsed_time(event.occurred_at):
                raise StateTransitionRefused("publication signoff expired before authorization")
        signoff_event_ids = tuple(item.event_id for item in publication.signoffs)
        signoff_roots = tuple(item.signoff.signoff_root for item in publication.signoffs)
        superego = publication.signoffs[-1].signoff
        if superego.consumed_signoff_event_ids != signoff_event_ids[:2]:
            raise StateTransitionRefused("Superego did not consume Ego and Aisthesis receipts")
        exact = {
            "publication_id": prepared.publication_id,
            "lease_id": prepared.lease_id,
            "prepared_event_id": publication.prepared_event_id,
            "recovery_root": prepared.recovery_root,
            "base_ref": prepared.base_ref,
            "expected_old": prepared.expected_old,
            "candidate_commit": prepared.candidate_commit,
            "affected_frontier_root": prepared.affected_frontier_root,
            "rehearsal_evidence_root": prepared.rehearsal_evidence_root,
            "forward_closure_root": prepared.forward_closure_root,
            "signoff_event_ids": signoff_event_ids,
            "signoff_roots": signoff_roots,
        }
        mismatches = {
            key: {"expected": value, "got": getattr(authorization, key)}
            for key, value in exact.items()
            if getattr(authorization, key) != value
        }
        if mismatches:
            raise StateTransitionRefused(
                "publication authorization mismatches prepared custody", mismatches=mismatches
            )
        if authorization.authorization_root != chash(authorization.identity_dict()):
            raise StateTransitionRefused("publication authorization root does not verify")
        if _parsed_time(authorization.expires_at) > min(
            _parsed_time(item.signoff.expires_at) for item in publication.signoffs
        ):
            raise StateTransitionRefused("publication authorization outlives a signoff")
        if _parsed_time(authorization.expires_at) <= _parsed_time(event.occurred_at):
            raise StateTransitionRefused("publication authorization is already expired")
        if _parsed_time(authorization.expires_at) > _parsed_time(
            prepared.forward_closure.expires_at
        ):
            raise StateTransitionRefused(
                "publication authorization outlives its forward closure"
            )
        if not lease.held_at(event.occurred_at):
            raise StateTransitionRefused("publication authorization requires an unexpired lease")
        if not lease.matches_occupancy(occupancy):
            raise StateTransitionRefused("publication authorization authority is displaced")
        if event.actor != lease.checkout.function:
            raise StateTransitionRefused("publication authorization actor is not its lease holder")
        if event.subject != f"publication:{authorization.publication_id}":
            raise StateTransitionRefused("publication authorization subject mismatches")
        _require_context(state, str(event.assumption), str(event.fibre))
        for required in (
            publication.prepared_event_id,
            lease.checkout_binding_event_id,
            *signoff_event_ids,
        ):
            if required not in event.causation_ids:
                raise StateTransitionRefused("publication authorization omits exact causation")
        leases = dict(state.region_leases)
        leases[authorization.lease_id] = replace(
            lease,
            publication=replace(
                publication,
                authorization=authorization,
                authorized_event_id=event.event_id,
                authorized_at=event.occurred_at,
            ),
        )
        return _with_event(state, event, region_leases=leases)

    if event.kind == EventKind.REGION_PUBLICATION_FINALIZED:
        finalized = RegionPublicationFinalized.from_dict(event.payload)
        lease = state.region_leases.get(finalized.lease_id)
        publication = None if lease is None else lease.publication
        if lease is None or publication is None or publication.authorization is None:
            raise StateTransitionRefused("publication finalize lacks durable authorization")
        if publication.finalized is not None:
            raise StateTransitionRefused("publication is already finalized")
        prepared = publication.prepared
        authorization = publication.authorization
        hook = prepared.forward_closure
        occupancy = state.seat_occupancies.get(lease.checkout.seat_id)
        if state.head_event_id != publication.authorized_event_id:
            raise StateTransitionRefused(
                "forward closure related head is not the current authorization"
            )
        if _parsed_time(authorization.expires_at) <= _parsed_time(event.occurred_at):
            raise StateTransitionRefused("publication authorization expired before CAS")
        if not lease.held_at(event.occurred_at):
            raise StateTransitionRefused("publication lease expired before CAS")
        for item in publication.signoffs:
            signer = item.signoff
            signer_occupancy = state.seat_occupancies.get(signer.signer_seat_id)
            if not _publication_signoff_matches_occupancy(signer, signer_occupancy):
                raise StateTransitionRefused("publication signer was replaced before CAS")
            if _parsed_time(signer.expires_at) <= _parsed_time(event.occurred_at):
                raise StateTransitionRefused("publication signoff expired before CAS")
        exact = {
            "publication_id": prepared.publication_id,
            "lease_id": prepared.lease_id,
            "prepared_event_id": publication.prepared_event_id,
            "authorized_event_id": publication.authorized_event_id,
            "recovery_root": prepared.recovery_root,
            "authorization_root": authorization.authorization_root,
            "base_ref": prepared.base_ref,
            "expected_old": prepared.expected_old,
            "result_git_head": prepared.candidate_commit,
            "candidate_tree": prepared.candidate_tree,
            "patch_handle": prepared.patch_handle,
            "custody_handle": prepared.custody_handle,
            "affected_frontier_root": prepared.affected_frontier_root,
            "forward_closure_root": prepared.forward_closure_root,
            "signoff_roots": authorization.signoff_roots,
        }
        mismatches = {
            key: {"expected": value, "got": getattr(finalized, key)}
            for key, value in exact.items()
            if getattr(finalized, key) != value
        }
        if mismatches:
            raise StateTransitionRefused(
                "publication finalize mismatches authorized custody", mismatches=mismatches
            )
        expected_projection = region_forward_closure_finalized_projection(
            lease_id=finalized.lease_id,
            seat_id=prepared.seat_id,
            holder_ref=prepared.holder_ref,
            function=prepared.function,
            base_ref=finalized.base_ref,
            expected_old=finalized.expected_old,
            result_git_head=finalized.result_git_head,
            candidate_tree=finalized.candidate_tree,
            patch_handle=finalized.patch_handle,
            custody_handle=finalized.custody_handle,
            affected_frontier_root=finalized.affected_frontier_root,
        )
        if hook.finalized_projection_digest != chash(expected_projection):
            raise StateTransitionRefused("forward closure does not rederive at consumption")
        expected_consumption_root = region_forward_closure_consumption_root(
            forward_closure_root=hook.forward_closure_root,
            authorized_event_id=str(publication.authorized_event_id),
            finalized_projection_digest=hook.finalized_projection_digest,
        )
        if finalized.forward_closure_consumption_root != expected_consumption_root:
            raise StateTransitionRefused(
                "forward closure consumption does not match its exact consumer"
            )
        if not lease.matches_occupancy(occupancy):
            raise StateTransitionRefused("publication finalize authority is displaced")
        if event.actor != lease.checkout.function:
            raise StateTransitionRefused("publication finalize actor is not its lease holder")
        if event.subject != f"publication:{finalized.publication_id}":
            raise StateTransitionRefused("publication finalize subject mismatches")
        _require_context(state, str(event.assumption), str(event.fibre))
        if publication.authorized_event_id not in event.causation_ids:
            raise StateTransitionRefused("publication finalize omits authorization causation")
        leases = dict(state.region_leases)
        leases[finalized.lease_id] = replace(
            lease,
            publication=replace(
                publication,
                finalized=finalized,
                finalized_event_id=event.event_id,
                finalized_at=event.occurred_at,
            ),
        )
        return _with_event(state, event, region_leases=leases)

    if event.kind == EventKind.REGION_CHECKIN:
        checkin = RegionCheckin.from_dict(event.payload)
        lease = state.region_leases.get(checkin.lease_id)
        if lease is None:
            raise StateTransitionRefused("region checkin cites an unknown lease")
        if lease.checkin is not None:
            raise StateTransitionRefused("region lease is already checked in")
        checkout = lease.checkout
        if (
            checkin.seat_id != checkout.seat_id
            or checkin.holder_ref != checkout.holder_ref
            or checkin.function != checkout.function
            or checkin.base_git_head != checkout.base_git_head
        ):
            raise StateTransitionRefused("region checkin does not match its checkout authority")
        occupancy = state.seat_occupancies.get(checkout.seat_id)
        if not lease.matches_occupancy(occupancy):
            raise StateTransitionRefused(
                "region checkin holder/function is no longer the latest seat occupancy lineage"
            )
        if event.actor != checkin.function:
            raise StateTransitionRefused("region checkin actor must be its lease function")
        if event.subject != f"lease:{checkin.lease_id}":
            raise StateTransitionRefused("region checkin subject must identify its lease")
        _require_context(state, str(event.assumption), str(event.fibre))
        if lease.checkout_event_id not in event.causation_ids:
            raise StateTransitionRefused("region checkin must causally close its checkout")
        if occupancy.binding_event_id not in event.causation_ids:
            raise StateTransitionRefused(
                "region checkin must causally carry the current occupancy binding"
            )
        for path in (*checkin.committed_paths, *checkin.dirty_paths):
            if not _path_in_regions(path, checkout.regions):
                raise StateTransitionRefused(
                    "region checkin evidence escapes its leased scope", path=path
                )
        if (
            lease.publication is not None
            and lease.publication.finalized is not None
            and checkin.outcome == LeaseCheckinOutcome.COMMITTED
        ):
            finalized = lease.publication.finalized
            if (
                checkin.result_git_head != finalized.result_git_head
                or tuple(checkin.committed_paths)
                != tuple(lease.publication.prepared.committed_paths)
                or lease.publication.finalized_event_id not in event.causation_ids
            ):
                raise StateTransitionRefused(
                    "publication checkin mismatches its atomic finalized record"
                )
        if checkin.outcome in {
            LeaseCheckinOutcome.COMMITTED,
            LeaseCheckinOutcome.NOOP,
        } and _parsed_time(event.occurred_at) > _parsed_time(checkout.expires_at) and not (
            lease.publication is not None
            and lease.publication.finalized is not None
            and checkin.outcome == LeaseCheckinOutcome.COMMITTED
        ):
            raise StateTransitionRefused("expired lease cannot claim a successful checkin")

        leases = dict(state.region_leases)
        leases[checkin.lease_id] = replace(
            lease,
            checkin=checkin,
            checkin_event_id=event.event_id,
            checked_in_at=event.occurred_at,
        )
        state = _connect(
            state,
            event,
            relation="closes-region-authority",
            source_object_id=_event_object_id(event.event_id),
            target_object_id=f"lease:{checkin.lease_id}",
            operator="region-checkin",
        )
        return _with_event(state, event, region_leases=leases)

    if event.kind == EventKind.ASSUMPTION:
        selection = AssumptionSelection.from_dict(event.payload)
        if state.active_assumption is not None and (
            selection.assumption,
            selection.fibre,
        ) != (state.active_assumption, state.active_fibre):
            raise StateTransitionRefused("assumption switch requires explicit fibre transport")
        if (event.assumption, event.fibre) != (selection.assumption, selection.fibre):
            raise StateTransitionRefused("event context contradicts selected assumption")
        state, context_object_id = _with_context_object(
            state, event, selection.assumption, selection.fibre
        )
        state = _connect(
            state,
            event,
            relation="selects-context",
            source_object_id=_event_object_id(event.event_id),
            target_object_id=context_object_id,
            contextual=True,
        )
        return _with_event(
            state,
            event,
            active_assumption=selection.assumption,
            active_fibre=selection.fibre,
        )

    if event.kind == EventKind.TRANSPORT:
        transport = TransportReceipt.from_dict(event.payload)
        _require_context(state, transport.from_assumption, transport.from_fibre)
        if (event.assumption, event.fibre) != (
            transport.to_assumption,
            transport.to_fibre,
        ):
            raise StateTransitionRefused("transport event must declare its destination context")
        if transport.transport_id in state.transports:
            raise StateTransitionRefused("transport id already exists")
        transports = dict(state.transports)
        transports[transport.transport_id] = transport
        state = replace(state, transports=transports)
        source_context_id = "context:" + chash(
            {
                "assumption": transport.from_assumption,
                "fibre": transport.from_fibre,
            }
        ).removeprefix("sha256:")
        target_context_id = "context:" + chash(
            {"assumption": transport.to_assumption, "fibre": transport.to_fibre}
        ).removeprefix("sha256:")
        if source_context_id not in state.graph_objects:
            raise StateTransitionRefused("transport source context object does not resolve")
        state, derived_target_context_id = _with_context_object(
            state, event, transport.to_assumption, transport.to_fibre
        )
        if derived_target_context_id != target_context_id:
            raise StateTransitionRefused("transport target context identity is not canonical")
        state = _connect(
            state,
            event,
            relation="transports-context",
            source_object_id=source_context_id,
            target_object_id=target_context_id,
            direction=MoveDirection.TRANSPORT,
            operator=transport.operator,
            contextual=True,
            transport_id=transport.transport_id,
        )
        return _with_event(
            state,
            event,
            active_assumption=transport.to_assumption,
            active_fibre=transport.to_fibre,
        )

    if event.kind == EventKind.GRADE_AXIS:
        contract = GradeAxisContract.from_dict(event.payload)
        if contract.contract_id in state.grade_axis_contracts:
            raise StateTransitionRefused("grade-axis contract id already exists")
        for existing in state.grade_axis_contracts.values():
            if existing.axis == contract.axis:
                raise StateTransitionRefused(
                    "grade axis already has a different active ordering contract",
                    axis=contract.axis,
                    active_contract_id=existing.contract_id,
                )
        contracts = dict(state.grade_axis_contracts)
        contracts[contract.contract_id] = contract
        return _with_event(state, event, grade_axis_contracts=contracts)

    if event.kind == EventKind.PROMOTION:
        promotion = UpActReceipt.from_dict(event.payload)
        _require_context(state, promotion.assumption, promotion.fibre)
        if (event.assumption, event.fibre) != (
            promotion.assumption,
            promotion.fibre,
        ):
            raise StateTransitionRefused("promotion event context contradicts its UP receipt")
        if event.subject != promotion.act_handle:
            raise StateTransitionRefused("promotion event subject must be its UP act handle")
        if promotion.act_handle in state.up_acts:
            raise StateTransitionRefused("UP act handle already exists")
        contract, source_grade, target_grade = _axis_positions(state, promotion.grade_axis)
        _verify_direction(MoveDirection.UP, source_grade, target_grade)
        if tuple(contract.coarse_to_fine) != promotion.coarse_to_fine:
            raise StateTransitionRefused(
                "UP receipt ordering contradicts its named grade-axis contract"
            )
        if event.residual.unit != "goal-closure":
            raise StateTransitionRefused(
                "promotion event residual must be goal closure, not spectral truncation"
            )
        closure = promotion.goal_closure
        if closure.status == GoalClosureStatus.UNMEASURED:
            if event.residual.status != ResidualStatus.UNKNOWN:
                raise StateTransitionRefused(
                    "unmeasured pure UP cannot claim measured goal closure"
                )
        else:
            if event.residual.status == ResidualStatus.UNKNOWN:
                raise StateTransitionRefused(
                    "measured goal closure cannot carry an unknown residual"
                )
            assert closure.probe_event_id is not None
            assert closure.probe_set_handle is not None
            assert closure.observation_handle is not None
            if closure.probe_event_id not in event.causation_ids:
                raise StateTransitionRefused(
                    "measured goal closure must causally cite its probe observation"
                )
            observation = state.observation_events.get(closure.probe_event_id)
            if observation is None:
                raise StateTransitionRefused(
                    "goal closure evidence must resolve to an observation event"
                )
            if chash(observation.payload) != closure.observation_handle:
                raise StateTransitionRefused(
                    "goal closure claim does not bind the exact observation payload"
                )
            observation_receipt = GoalClosureObservation.from_dict(observation.payload)
            if observation_receipt.probe_set_handle != closure.probe_set_handle:
                raise StateTransitionRefused("goal closure observation names a different probe set")
            if promotion.node_handle not in observation_receipt.promoted_handles:
                raise StateTransitionRefused(
                    "goal closure observation did not evaluate this promoted node"
                )
            if observation.residual != event.residual:
                raise StateTransitionRefused(
                    "promotion goal residual contradicts its closure observation"
                )
            probe_set = state.goal_closure_probe_sets.get(closure.probe_set_handle)
            if probe_set is None:
                raise StateTransitionRefused(
                    "goal closure probe-set content does not resolve in canonical history"
                )
            probe_event_id = state.goal_closure_probe_events[closure.probe_set_handle]
            if probe_event_id not in observation.causation_ids:
                raise StateTransitionRefused(
                    "goal closure observation must causally cite its banked probe set"
                )
            if (observation.assumption, observation.fibre) != (
                promotion.assumption,
                promotion.fibre,
            ):
                raise StateTransitionRefused(
                    "goal closure observation cannot cross an assumption fibre"
                )
            candidates = {
                candidate.node_handle: candidate for candidate in observation_receipt.candidates
            }
            promoted_candidate = candidates[promotion.node_handle]
            if promoted_candidate.members != promotion.members:
                raise StateTransitionRefused(
                    "goal closure routing candidate members contradict the promoted node"
                )
            if not _vectors_equal(promoted_candidate.centroid, promotion.centroid):
                raise StateTransitionRefused(
                    "goal closure routing candidate centroid contradicts the promoted node"
                )

            candidate_leaves: dict[
                str, tuple[tuple[str, tuple[float, ...], tuple[str, ...]], ...]
            ] = {}
            all_logical_ids: set[str] = set()
            all_member_objects: set[str] = set()
            for candidate in observation_receipt.candidates:
                resolved = []
                for member in candidate.members:
                    child = state.graph_objects.get(member.object_id)
                    if child is None:
                        raise StateTransitionRefused(
                            "goal closure routing member does not resolve",
                            object_id=member.object_id,
                        )
                    if child.content_handle != member.content_handle:
                        raise StateTransitionRefused(
                            "goal closure routing member contradicts its resolved content",
                            object_id=member.object_id,
                        )
                    if (child.assumption, child.fibre) != (
                        promotion.assumption,
                        promotion.fibre,
                    ):
                        raise StateTransitionRefused(
                            "goal closure routing member cannot cross an assumption fibre",
                            object_id=member.object_id,
                        )
                    if (
                        child.grade_contract_id != promotion.grade_axis.contract_id
                        or child.grade_coordinate != promotion.grade_axis.from_coordinate
                    ):
                        raise StateTransitionRefused(
                            "goal closure routing member is not at the promoted source grade",
                            object_id=member.object_id,
                        )
                    logical_id = child.attributes.get("logical_id")
                    if not isinstance(logical_id, str) or not logical_id.strip():
                        raise StateTransitionRefused(
                            "goal closure routing member lacks a banked logical identity",
                            object_id=member.object_id,
                        )
                    vector = _exact_vector(
                        child.attributes.get("vector"),
                        field_name=f"{member.object_id}.vector",
                    )
                    source_chain_raw = child.attributes.get("source_chain")
                    if (
                        not isinstance(source_chain_raw, list)
                        or not source_chain_raw
                        or not all(
                            isinstance(item, str) and item.strip() for item in source_chain_raw
                        )
                    ):
                        raise StateTransitionRefused(
                            "goal closure routing member lacks a complete banked source chain",
                            object_id=member.object_id,
                        )
                    if len(vector) != len(candidate.centroid):
                        raise StateTransitionRefused(
                            "goal closure routing member and centroid dimensions differ",
                            object_id=member.object_id,
                        )
                    if logical_id in all_logical_ids or member.object_id in all_member_objects:
                        raise StateTransitionRefused(
                            "goal closure routing candidates overlap",
                            object_id=member.object_id,
                            logical_id=logical_id,
                        )
                    all_logical_ids.add(logical_id)
                    all_member_objects.add(member.object_id)
                    resolved.append((logical_id, vector, tuple(source_chain_raw)))
                logical_ids = tuple(item[0] for item in resolved)
                if candidate.cluster_id != derived_cluster_id(logical_ids):
                    raise StateTransitionRefused(
                        "goal closure routing candidate identity is not derived from its members"
                    )
                derived_centroid = tuple(
                    sum(item[1][dimension] for item in resolved) / len(resolved)
                    for dimension in range(len(resolved[0][1]))
                )
                if not _vectors_equal(candidate.centroid, derived_centroid):
                    raise StateTransitionRefused(
                        "goal closure routing candidate centroid is not derived from its members"
                    )
                candidate_leaves[candidate.cluster_id] = tuple(resolved)

            if probe_set.coverage_contract != EXACT_MEMBER_COVERAGE:
                raise StateTransitionRefused(
                    "goal closure exam lacks exact candidate-member coverage"
                )
            probes = {probe.probe_id: probe for probe in probe_set.probes}
            answers = {answer.probe_id: answer for answer in observation_receipt.answers}
            if set(probes) != set(answers):
                raise StateTransitionRefused(
                    "goal closure answers do not cover the exact banked probe set"
                )
            expected_leaf_ids = [probe.expected_leaf_id for probe in probe_set.probes]
            if (
                len(expected_leaf_ids) != len(set(expected_leaf_ids))
                or set(expected_leaf_ids) != all_logical_ids
            ):
                raise StateTransitionRefused(
                    "goal closure exam must contain exactly one probe per routing candidate member"
                )
            for probe_id, probe in probes.items():
                answer = answers[probe_id]
                if any(
                    len(probe.query_vector) != len(candidate.centroid)
                    for candidate in observation_receipt.candidates
                ):
                    raise StateTransitionRefused(
                        "goal closure query and routing candidate dimensions differ",
                        probe_id=probe_id,
                    )
                selected_candidate = max(
                    observation_receipt.candidates,
                    key=lambda candidate: (
                        _cosine(probe.query_vector, candidate.centroid),
                        candidate.cluster_id,
                    ),
                )
                selected_leaf = max(
                    candidate_leaves[selected_candidate.cluster_id],
                    key=lambda item: (
                        _cosine(probe.query_vector, item[1]),
                        item[0],
                    ),
                )
                if (
                    answer.selected_leaf_id != selected_leaf[0]
                    or answer.source_chain != selected_leaf[2]
                ):
                    raise StateTransitionRefused(
                        "goal closure answer was not derived from banked routing inputs",
                        probe_id=probe_id,
                    )
                correct_leaf = answer.selected_leaf_id == probe.expected_leaf_id
                complete_chain = answer.source_chain == probe.expected_source_chain
                if (
                    answer.correct_leaf != correct_leaf
                    or answer.complete_source_chain != complete_chain
                    or answer.passed != (correct_leaf and complete_chain)
                ):
                    raise StateTransitionRefused(
                        "goal closure answer contradicts its banked ground truth",
                        probe_id=probe_id,
                    )
            measured_misses = sum(not answer.passed for answer in answers.values())
            measured_value = measured_misses / len(answers)
            if observation.residual.value is None or not math.isclose(
                observation.residual.value,
                measured_value,
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise StateTransitionRefused(
                    "goal closure residual does not equal the banked answer failures"
                )
            threshold = observation.residual.threshold
            assert threshold is not None
            if not 0.0 <= threshold <= 1.0:
                raise StateTransitionRefused("goal closure threshold must be a fraction in [0, 1]")
            expected_status = (
                ResidualStatus.WITHIN_BOUND
                if measured_value <= threshold
                else ResidualStatus.EXCEEDS_BOUND
            )
            if observation.residual.status != expected_status:
                raise StateTransitionRefused(
                    "goal closure residual status contradicts its value and threshold"
                )
            if not any(source.digest == closure.probe_set_handle for source in event.provenance):
                raise StateTransitionRefused(
                    "measured goal closure must carry its probe-set handle in provenance"
                )

        for member in promotion.members:
            child = state.graph_objects.get(member.object_id)
            if child is None:
                raise StateTransitionRefused(
                    "UP member object does not resolve", object_id=member.object_id
                )
            if child.content_handle != member.content_handle:
                raise StateTransitionRefused(
                    "UP member content handle contradicts its resolved object",
                    object_id=member.object_id,
                )
            if (child.assumption, child.fibre) != (
                promotion.assumption,
                promotion.fibre,
            ):
                raise StateTransitionRefused(
                    "UP member cannot silently cross an assumption fibre",
                    object_id=member.object_id,
                )
            if (
                child.grade_contract_id != promotion.grade_axis.contract_id
                or child.grade_coordinate != promotion.grade_axis.from_coordinate
            ):
                raise StateTransitionRefused(
                    "UP member is not at the declared source grade",
                    object_id=member.object_id,
                )

        coarse_attributes = {
            "act_handle": promotion.act_handle,
            "inputs_handle": promotion.inputs_handle,
            "metric_version": promotion.metric_version,
            "chi": promotion.chi,
            "phi": promotion.phi,
            "member_object_ids": [member.object_id for member in promotion.members],
            "member_handles": [member.content_handle for member in promotion.members],
            "representation_sufficient": promotion.representation_sufficient,
            "forced_descent": promotion.forced_descent,
            "truncation_residual": promotion.frame.truncation_residual,
            "goal_closure_claim": closure.to_dict(),
            "goal_closure_residual": event.residual.to_dict(),
        }
        state = _with_graph_object(
            state,
            ConceptricObject(
                promotion.coarse_object_id,
                "coarse-node",
                promotion.node_handle,
                promotion.assumption,
                promotion.fibre,
                promotion.grade_axis.contract_id,
                promotion.grade_axis.to_coordinate,
                event.provenance,
                coarse_attributes,
            ),
        )
        state = _with_graph_object(
            state,
            ConceptricObject(
                promotion.semantic_object_id,
                "semantic-representation",
                chash(
                    {
                        "face": promotion.semantic_face,
                        "sources": list(promotion.semantic_sources),
                    }
                ),
                promotion.assumption,
                promotion.fibre,
                promotion.grade_axis.contract_id,
                promotion.grade_axis.to_coordinate,
                event.provenance,
                {
                    "node_handle": promotion.node_handle,
                    "face": promotion.semantic_face,
                    "sources": list(promotion.semantic_sources),
                },
            ),
        )
        state = _with_graph_object(
            state,
            ConceptricObject(
                promotion.spectral_object_id,
                "spectral-representation",
                chash(
                    {
                        "frame": promotion.frame.to_dict(),
                        "centroid": list(promotion.centroid),
                    }
                ),
                promotion.assumption,
                promotion.fibre,
                promotion.grade_axis.contract_id,
                promotion.grade_axis.to_coordinate,
                event.provenance,
                {
                    "node_handle": promotion.node_handle,
                    "frame": promotion.frame.to_dict(),
                    "centroid": list(promotion.centroid),
                },
            ),
        )
        for face_id, relation in (
            (promotion.semantic_object_id, "semantic-face-of"),
            (promotion.spectral_object_id, "spectral-face-of"),
        ):
            state = _connect(
                state,
                event,
                relation=relation,
                source_object_id=face_id,
                target_object_id=promotion.coarse_object_id,
                direction=MoveDirection.CONJUGATE,
                operator="two-face-join",
                contextual=True,
            )
        for member in promotion.members:
            state = _connect(
                state,
                event,
                relation="up-member-of",
                source_object_id=member.object_id,
                target_object_id=promotion.coarse_object_id,
                direction=MoveDirection.UP,
                operator=promotion.metric_version,
                contextual=True,
            )
            state = _connect(
                state,
                event,
                relation="down-member-to",
                source_object_id=promotion.coarse_object_id,
                target_object_id=member.object_id,
                direction=MoveDirection.DOWN,
                operator=promotion.metric_version,
                contextual=True,
            )
        up_acts = dict(state.up_acts)
        up_acts[promotion.act_handle] = promotion
        up_events = dict(state.up_events)
        up_events[event.event_id] = promotion.act_handle
        return _with_event(
            state,
            event,
            up_acts=up_acts,
            up_events=up_events,
        )

    if event.kind == EventKind.PROLONGATION:
        prolongation = DownActReceipt.from_dict(event.payload)
        if event.subject != prolongation.act_handle:
            raise StateTransitionRefused("prolongation event subject must be its DOWN act handle")
        if prolongation.act_handle in state.down_acts:
            raise StateTransitionRefused("DOWN act handle already exists")
        if event.causation_ids != (prolongation.up_event_id,):
            raise StateTransitionRefused(
                "DOWN must causally cite exactly its corresponding UP event"
            )
        up_act_handle = state.up_events.get(prolongation.up_event_id)
        if up_act_handle is None:
            raise StateTransitionRefused("DOWN cites an event that is not a banked UP")
        promotion = state.up_acts[up_act_handle]
        _require_context(state, promotion.assumption, promotion.fibre)
        if (event.assumption, event.fibre) != (
            promotion.assumption,
            promotion.fibre,
        ):
            raise StateTransitionRefused("DOWN event context contradicts its corresponding UP")
        if (
            prolongation.up_act_handle != promotion.act_handle
            or prolongation.node_handle != promotion.node_handle
            or prolongation.coarse_object_id != promotion.coarse_object_id
            or prolongation.members != promotion.members
        ):
            raise StateTransitionRefused("DOWN receipt contradicts its corresponding UP receipt")
        coarse = state.graph_objects.get(prolongation.coarse_object_id)
        if coarse is None or coarse.content_handle != prolongation.node_handle:
            raise StateTransitionRefused("DOWN coarse node does not resolve exactly")
        for member in prolongation.members:
            child = state.graph_objects.get(member.object_id)
            if child is None or child.content_handle != member.content_handle:
                raise StateTransitionRefused(
                    "DOWN member does not resolve exactly", object_id=member.object_id
                )
        if prolongation.verified:
            if (
                event.residual.unit != "round-trip-relative-error"
                or event.residual.status == ResidualStatus.UNKNOWN
                or event.residual.value != prolongation.round_trip_residual
            ):
                raise StateTransitionRefused(
                    "verified DOWN must carry its measured round-trip residual"
                )
        elif (
            event.residual.unit != "round-trip-relative-error"
            or event.residual.status != ResidualStatus.UNKNOWN
        ):
            raise StateTransitionRefused("unverified DOWN residual must remain unknown")
        if any(
            len(vector) != len(promotion.centroid)
            for vector in prolongation.reconstructions.values()
        ):
            raise StateTransitionRefused(
                "DOWN reconstruction dimension contradicts its UP centroid"
            )
        down_acts = dict(state.down_acts)
        down_acts[prolongation.act_handle] = prolongation
        return _with_event(state, event, down_acts=down_acts)

    if event.kind == EventKind.MOVE:
        movement = Movement.from_dict(event.payload)
        if movement.movement_id in state.movements:
            raise StateTransitionRefused("movement id already exists")
        _contract, source_grade, target_grade = _axis_positions(state, movement.grade_axis)
        _verify_direction(movement.direction, source_grade, target_grade)
        if movement.transport_id is None:
            _require_context(state, movement.source.assumption, movement.source.fibre)
        else:
            transport = state.transports.get(movement.transport_id)
            if transport is None:
                raise StateTransitionRefused("movement cites unknown fibre transport")
            endpoints = (
                transport.from_assumption,
                transport.from_fibre,
                transport.to_assumption,
                transport.to_fibre,
            )
            moved = (
                movement.source.assumption,
                movement.source.fibre,
                movement.target.assumption,
                movement.target.fibre,
            )
            if endpoints != moved:
                raise StateTransitionRefused("movement endpoints contradict transport receipt")
            _require_context(state, movement.target.assumption, movement.target.fibre)
        if (event.assumption, event.fibre) != (
            movement.target.assumption,
            movement.target.fibre,
        ):
            raise StateTransitionRefused("movement event must inhabit its target context")
        source_object_id = "boundary:" + chash(movement.source.to_dict()).removeprefix("sha256:")
        target_object_id = "boundary:" + chash(movement.target.to_dict()).removeprefix("sha256:")
        state = _with_graph_object(
            state,
            ConceptricObject(
                source_object_id,
                "reconstruction-boundary",
                _content_handle(movement.source.handle),
                movement.source.assumption,
                movement.source.fibre,
                movement.grade_axis.contract_id,
                movement.grade_axis.from_coordinate,
                movement.provenance,
                {
                    "handle": movement.source.handle,
                    "node_id": movement.source.node_id,
                },
            ),
        )
        state = _with_graph_object(
            state,
            ConceptricObject(
                target_object_id,
                "reconstruction-boundary",
                _content_handle(movement.target.handle),
                movement.target.assumption,
                movement.target.fibre,
                movement.grade_axis.contract_id,
                movement.grade_axis.to_coordinate,
                movement.provenance,
                {
                    "handle": movement.target.handle,
                    "node_id": movement.target.node_id,
                },
            ),
        )
        state = _with_graph_edge(
            state,
            ConceptricEdge(
                f"edge:movement:{movement.movement_id}",
                "reconstruction-movement",
                source_object_id,
                target_object_id,
                movement.direction,
                event.assumption,
                event.fibre,
                movement.operator,
                movement.grade_axis,
                movement.provenance,
                movement.residual,
                event.event_id,
                movement.transport_id,
            ),
        )
        movements = dict(state.movements)
        movements[movement.movement_id] = movement
        return _with_event(state, event, movements=movements)

    if event.kind == EventKind.JOIN:
        join = JoinReceipt.from_dict(event.payload)
        _require_context(state, join.assumption, join.fibre)
        if (event.assumption, event.fibre) != (join.assumption, join.fibre):
            raise StateTransitionRefused("join event context contradicts join receipt")
        if event.residual != join.residual:
            raise StateTransitionRefused("join event residual contradicts join receipt")
        if join.join_id in state.joins:
            raise StateTransitionRefused("join id already exists")
        join_object_id = f"join:{join.join_id}"
        if join.strict:
            assert join.up_act_handle is not None
            assert join.semantic_object_id is not None
            assert join.spectral_object_id is not None
            promotion = state.up_acts.get(join.up_act_handle)
            if promotion is None:
                raise StateTransitionRefused("strict join must resolve its exact UP act")
            if (
                promotion.node_handle != join.node_id
                or promotion.assumption != join.assumption
                or promotion.fibre != join.fibre
            ):
                raise StateTransitionRefused(
                    "strict join context or node contradicts its exact UP act"
                )
            if (
                join.semantic_object_id != promotion.semantic_object_id
                or join.spectral_object_id != promotion.spectral_object_id
            ):
                raise StateTransitionRefused(
                    "strict join did not bind the exact faces created by its UP act"
                )
            semantic = state.graph_objects.get(join.semantic_object_id)
            spectral = state.graph_objects.get(join.spectral_object_id)
            if semantic is None or spectral is None:
                raise StateTransitionRefused("strict join face objects do not resolve")
            if (
                semantic.kind != "semantic-representation"
                or spectral.kind != "spectral-representation"
                or semantic.content_handle != join.semantic_handle
                or spectral.content_handle != join.spectral_handle
            ):
                raise StateTransitionRefused(
                    "strict join handles contradict their resolved UP face objects"
                )
            if (semantic.assumption, semantic.fibre) != (join.assumption, join.fibre) or (
                spectral.assumption,
                spectral.fibre,
            ) != (join.assumption, join.fibre):
                raise StateTransitionRefused("strict join faces crossed an assumption fibre")
            up_event_ids = tuple(
                event_id
                for event_id, act_handle in state.up_events.items()
                if act_handle == join.up_act_handle
            )
            if len(up_event_ids) != 1 or up_event_ids[0] not in event.causation_ids:
                raise StateTransitionRefused("strict join must causally cite its exact UP event")
            if event.subject != join.join_id:
                raise StateTransitionRefused("strict join event subject must be its derived id")
            if join.provenance != event.provenance:
                raise StateTransitionRefused(
                    "strict join provenance contradicts its event envelope"
                )
            semantic_object_id = join.semantic_object_id
            spectral_object_id = join.spectral_object_id
            state = _with_graph_object(
                state,
                _object(
                    event,
                    object_id=join_object_id,
                    kind="conjugate-join",
                    content_handle=chash(join.to_dict()),
                    coordinate=semantic.grade_coordinate,
                    contextual=True,
                    grade_contract_id=semantic.grade_contract_id,
                    attributes={
                        "node_id": join.node_id,
                        "join_id": join.join_id,
                        "up_act_handle": join.up_act_handle,
                    },
                ),
            )
        else:
            semantic_object_id = "representation:" + chash(
                {
                    "handle": join.semantic_handle,
                    "assumption": join.assumption,
                    "fibre": join.fibre,
                    "face": "semantic",
                }
            ).removeprefix("sha256:")
            spectral_object_id = "representation:" + chash(
                {
                    "handle": join.spectral_handle,
                    "assumption": join.assumption,
                    "fibre": join.fibre,
                    "face": "spectral",
                }
            ).removeprefix("sha256:")
            for object_id, kind, handle, attributes in (
                (
                    semantic_object_id,
                    "semantic-representation",
                    join.semantic_handle,
                    {"node_id": join.node_id, "face": "semantic"},
                ),
                (
                    spectral_object_id,
                    "spectral-representation",
                    join.spectral_handle,
                    {"node_id": join.node_id, "face": "spectral"},
                ),
                (
                    join_object_id,
                    "conjugate-join",
                    chash(join.to_dict()),
                    {"node_id": join.node_id, "join_id": join.join_id},
                ),
            ):
                state = _with_graph_object(
                    state,
                    _object(
                        event,
                        object_id=object_id,
                        kind=kind,
                        content_handle=handle,
                        coordinate="content",
                        contextual=True,
                        attributes=attributes,
                    ),
                )
        for source_object_id in (semantic_object_id, spectral_object_id):
            state = _connect(
                state,
                event,
                relation="conjugate-joins",
                source_object_id=source_object_id,
                target_object_id=join_object_id,
                direction=MoveDirection.CONJUGATE,
                operator=join.operator,
                contextual=True,
            )
        joins = dict(state.joins)
        joins[join.join_id] = join
        return _with_event(state, event, joins=joins)

    if event.kind == EventKind.MATERIALIZATION:
        materialized = MaterializedReconstruction.from_dict(event.payload)
        _require_context(state, materialized.assumption, materialized.fibre)
        if (event.assumption, event.fibre) != (
            materialized.assumption,
            materialized.fibre,
        ):
            raise StateTransitionRefused("materialization event context is contradictory")
        missing = sorted(set(materialized.movement_ids) - set(state.movements))
        if missing:
            raise StateTransitionRefused("materialization cites unknown movements", missing=missing)
        materializations = dict(state.materializations)
        materializations[materialized.cache_key] = materialized
        materialization_events = dict(state.materialization_events)
        materialization_events[event.event_id] = event
        return _with_event(
            state,
            event,
            materializations=materializations,
            materialization_events=materialization_events,
        )

    if event.kind == EventKind.CORPUS_ACT:
        act = CorpusAct.from_dict(event.payload)
        transactions = dict(state.transactions)
        if act.phase == ActPhase.PREVIEW:
            assert act.transaction_id is not None
            if act.transaction_id in transactions:
                raise StateTransitionRefused("transaction already has a preview")
            transactions[act.transaction_id] = TransactionState(event.event_id, act.phase)
        elif act.phase in {ActPhase.COMMIT, ActPhase.ROLLBACK}:
            assert act.transaction_id is not None
            pending = transactions.get(act.transaction_id)
            if pending is None or pending.phase != ActPhase.PREVIEW:
                raise StateTransitionRefused("transaction is not awaiting a decision")
            if act.preview_event_id != pending.preview_event_id:
                raise StateTransitionRefused("transaction cites the wrong preview")
            transactions[act.transaction_id] = TransactionState(pending.preview_event_id, act.phase)
        heads = dict(state.corpus_heads)
        if act.phase in {ActPhase.READ, ActPhase.COMMIT}:
            heads[act.domain] = event.event_id
        return _with_event(state, event, transactions=transactions, corpus_heads=heads)

    if event.kind == EventKind.MESSAGE:
        if event.assumption is None or event.fibre is None:
            raise StateTransitionRefused("seat message must declare its assumption fibre")
        _require_context(state, event.assumption, event.fibre)
        message = SeatMessage.from_dict(event.payload)
        sender = _require_seat(state, message.sender_seat_id)
        _require_seat(state, message.recipient_seat_id)
        if event.actor.value != sender.role:
            raise StateTransitionRefused(
                "message actor does not hold the sender's logical-seat role"
            )
        if message.cursor != state.event_count + 1:
            raise StateTransitionRefused(
                "message cursor must equal its durable history position",
                expected=state.event_count + 1,
                got=message.cursor,
            )
        if message.message_id in state.messages:
            raise StateTransitionRefused("message id already exists")
        prior = state.message_idempotency.get(message.idempotency_key)
        if prior is not None and prior != message.message_id:
            raise StateTransitionRefused(
                "idempotency key already names a different message", prior_message_id=prior
            )
        message_object_id = message.message_id
        body_object_id = f"content:{message.body_handle}"
        state = _with_graph_object(
            state,
            ConceptricObject(
                body_object_id,
                "content-blob",
                _content_handle(message.body_handle),
                None,
                None,
                CONTROL_AXIS_CONTRACT.contract_id,
                "content",
                _handle_provenance(message.body_handle),
                {"body_handle": message.body_handle},
            ),
        )
        state = _with_graph_object(
            state,
            _object(
                event,
                object_id=message_object_id,
                kind="seat-message",
                content_handle=chash(message.to_dict()),
                coordinate="message",
                contextual=True,
                attributes={
                    "message_id": message.message_id,
                    "message_type": message.message_type,
                    "sender_seat_id": message.sender_seat_id,
                    "recipient_seat_id": message.recipient_seat_id,
                },
            ),
        )
        state = _connect(
            state,
            event,
            relation="declares-message",
            source_object_id=_event_object_id(event.event_id),
            target_object_id=message_object_id,
            contextual=True,
        )
        state = _connect(
            state,
            event,
            relation="sends",
            source_object_id=f"seat:{message.sender_seat_id}",
            target_object_id=message_object_id,
            direction=MoveDirection.DOWN,
            operator="seat-send",
            contextual=True,
        )
        state = _connect(
            state,
            event,
            relation="addressed-to",
            source_object_id=message_object_id,
            target_object_id=f"seat:{message.recipient_seat_id}",
            direction=MoveDirection.UP,
            operator="seat-routing",
            contextual=True,
        )
        state = _connect(
            state,
            event,
            relation="has-body",
            source_object_id=message_object_id,
            target_object_id=body_object_id,
            direction=MoveDirection.DOWN,
            operator="content-address-resolution",
            contextual=True,
        )
        messages = dict(state.messages)
        messages[message.message_id] = MessageState(
            message,
            event.event_id,
            event.assumption,
            event.fibre,
            DeliveryState.QUEUED,
        )
        idempotency = dict(state.message_idempotency)
        idempotency[message.idempotency_key] = message.message_id
        return _with_event(state, event, messages=messages, message_idempotency=idempotency)

    if event.kind == EventKind.MESSAGE_PULL:
        if event.assumption is None or event.fibre is None:
            raise StateTransitionRefused("message pull must declare its assumption fibre")
        _require_context(state, event.assumption, event.fibre)
        pull = MessagePull.from_dict(event.payload)
        pulling_seat = _require_seat(state, pull.seat_id)
        if event.actor.value != pulling_seat.role:
            raise StateTransitionRefused("pull actor does not hold the logical-seat role")
        previous_cursor = state.cursor_for(pull.seat_id)
        if pull.after_cursor != previous_cursor:
            raise StateTransitionRefused(
                "pull must continue from the seat's durable cursor", expected=previous_cursor
            )
        if pull.result_cursor != state.event_count:
            raise StateTransitionRefused(
                "pull result cursor must name the evaluated history head",
                expected=state.event_count,
            )
        expected = tuple(
            item.message_id
            for item in state.pending_messages(
                pull.seat_id, after_cursor=pull.after_cursor, as_of=pull.as_of
            )
        )
        if pull.message_ids != expected:
            raise StateTransitionRefused(
                "pull result is not the deterministic pending-message view",
                expected=list(expected),
                got=list(pull.message_ids),
            )
        for message_id in pull.message_ids:
            state = _connect(
                state,
                event,
                relation="pulls-message",
                source_object_id=_event_object_id(event.event_id),
                target_object_id=message_id,
                operator="fibre-local-cursor-pull",
                contextual=True,
            )
        messages = dict(state.messages)
        for message_id in pull.message_ids:
            current = messages[message_id]
            messages[message_id] = replace(
                current, status=DeliveryState.PULLED, last_pull_event_id=event.event_id
            )
        cursors = dict(state.seat_cursors)
        cursors[(pull.seat_id, event.assumption, event.fibre)] = pull.result_cursor
        return _with_event(state, event, messages=messages, seat_cursors=cursors)

    if event.kind == EventKind.MESSAGE_ACK:
        if event.assumption is None or event.fibre is None:
            raise StateTransitionRefused(
                "message acknowledgement must declare its assumption fibre"
            )
        _require_context(state, event.assumption, event.fibre)
        acknowledgement = MessageAcknowledgement.from_dict(event.payload)
        record = state.messages.get(acknowledgement.message_id)
        if record is None:
            raise StateTransitionRefused("acknowledgement cites unknown message")
        if acknowledgement.seat_id != record.message.recipient_seat_id:
            raise StateTransitionRefused("only the recipient seat may acknowledge a message")
        acknowledging_seat = _require_seat(state, acknowledgement.seat_id)
        if event.actor.value != acknowledging_seat.role:
            raise StateTransitionRefused(
                "acknowledgement actor does not hold the recipient logical-seat role"
            )
        if (event.assumption, event.fibre) != (record.assumption, record.fibre):
            raise StateTransitionRefused(
                "acknowledgement cannot cross the message's assumption fibre"
            )
        if record.status in {
            DeliveryState.DELIVERED,
            DeliveryState.REFUSED,
            DeliveryState.QUARANTINED,
            DeliveryState.EXPIRED,
            DeliveryState.SUPERSEDED,
        }:
            raise StateTransitionRefused("message already reached a terminal status")
        if (
            acknowledgement.disposition == AcknowledgementDisposition.ACCEPTED
            and acknowledgement.reconstruction_event_id not in state.event_ids
        ):
            raise StateTransitionRefused("acknowledgement cites unknown reconstruction event")
        if acknowledgement.disposition == AcknowledgementDisposition.ACCEPTED:
            assert acknowledgement.reconstruction_event_id is not None
            reconstruction = state.repl_evaluations.get(acknowledgement.reconstruction_event_id)
            reconstruction_context = state.repl_contexts.get(
                acknowledgement.reconstruction_event_id
            )
            if reconstruction is None or reconstruction.operation.value != "reconstruct":
                raise StateTransitionRefused(
                    "accepted acknowledgement must cite a typed reconstruction evaluation"
                )
            if reconstruction.branch_id != acknowledgement.seat_id:
                raise StateTransitionRefused(
                    "reconstruction proof belongs to a different logical seat"
                )
            reconstructed_message_id = reconstruction.arguments.get("message_id")
            if (
                reconstructed_message_id is not None
                and reconstructed_message_id != acknowledgement.message_id
            ):
                raise StateTransitionRefused(
                    "reconstruction proof belongs to a different message delivery"
                )
            if record.message.body_handle not in reconstruction.input_handles:
                raise StateTransitionRefused(
                    "reconstruction proof did not consume the message body handle"
                )
            if acknowledgement.reconstruction_handle not in reconstruction.output_handles:
                raise StateTransitionRefused(
                    "acknowledgement handle is not an output of its reconstruction proof"
                )
            if reconstruction_context != (
                record.assumption,
                record.fibre,
                event.actor.value,
            ):
                raise StateTransitionRefused(
                    "reconstruction proof does not inhabit the recipient's assumption fibre"
                )
            required_causes = {
                record.sent_event_id,
                acknowledgement.reconstruction_event_id,
            }
            if not required_causes.issubset(event.causation_ids):
                raise StateTransitionRefused(
                    "delivered acknowledgement must causally join send and reconstruction",
                    required=sorted(required_causes),
                )
        acknowledgement_object_id = f"acknowledgement:{event.event_id}"
        state = _with_graph_object(
            state,
            _object(
                event,
                object_id=acknowledgement_object_id,
                kind="message-acknowledgement",
                content_handle=chash(acknowledgement.to_dict()),
                coordinate="acknowledgement",
                contextual=True,
                attributes={
                    "message_id": acknowledgement.message_id,
                    "seat_id": acknowledgement.seat_id,
                    "disposition": acknowledgement.disposition.value,
                },
            ),
        )
        state = _connect(
            state,
            event,
            relation="acknowledged-by",
            source_object_id=acknowledgement.message_id,
            target_object_id=acknowledgement_object_id,
            direction=MoveDirection.DOWN,
            operator="reconstruction-bearing-acknowledgement",
            contextual=True,
        )
        if acknowledgement.reconstruction_event_id is not None:
            state = _connect(
                state,
                event,
                relation="proved-by",
                source_object_id=(f"reconstruction:{acknowledgement.reconstruction_event_id}"),
                target_object_id=acknowledgement_object_id,
                direction=MoveDirection.DOWN,
                operator="reconstruction-bearing-acknowledgement",
                contextual=True,
            )
        state = _connect(
            state,
            event,
            relation="declares-acknowledgement",
            source_object_id=_event_object_id(event.event_id),
            target_object_id=acknowledgement_object_id,
            contextual=True,
        )
        status = (
            DeliveryState.DELIVERED
            if acknowledgement.disposition == AcknowledgementDisposition.ACCEPTED
            else DeliveryState.REFUSED
        )
        messages = dict(state.messages)
        messages[acknowledgement.message_id] = replace(
            record,
            status=status,
            acknowledgement_event_id=event.event_id,
            reconstruction_handle=acknowledgement.reconstruction_handle,
        )
        return _with_event(state, event, messages=messages)

    if event.kind == EventKind.MESSAGE_PRESERVE_FORK:
        if event.assumption is None or event.fibre is None:
            raise StateTransitionRefused("message fork preservation must declare its current fibre")
        _require_context(state, event.assumption, event.fibre)
        preservation = MessageForkPreservation.from_dict(event.payload)
        if event.subject != f"preserve-fork:{preservation.message_id}":
            raise StateTransitionRefused("fork preservation subject must identify its message")
        record = state.messages.get(preservation.message_id)
        if record is None:
            raise StateTransitionRefused("fork preservation cites unknown message")
        if record.status not in {DeliveryState.QUEUED, DeliveryState.PULLED}:
            raise StateTransitionRefused(
                "only a queued or pulled message can be preserved as a fork",
                status=record.status.value,
            )
        if preservation.original_sender_seat_id != record.message.sender_seat_id:
            raise StateTransitionRefused("fork preservation sender does not match message")
        if preservation.recipient_seat_id != record.message.recipient_seat_id:
            raise StateTransitionRefused("fork preservation recipient does not match message")
        if preservation.body_handle != record.message.body_handle:
            raise StateTransitionRefused("fork preservation body handle does not match message")
        if preservation.message_id != PRESERVE_FORK_TARGET_MESSAGE_ID:
            raise StateTransitionRefused("fork preservation target is not the author-ruled row")
        if preservation.author_ruling_ref != PRESERVE_FORK_AUTHOR_RULING_REF:
            raise StateTransitionRefused("fork preservation cites the wrong author ruling")
        if preservation.authority_event_id != PRESERVE_FORK_AUTHORITY_EVENT_ID:
            raise StateTransitionRefused("fork preservation cites the wrong authority event")

        operator_seat_id = "superego-seat"
        operator = _require_seat(state, operator_seat_id)
        occupancy = state.seat_occupancies.get(operator_seat_id)
        if operator.role != SeatRole.SUPEREGO.value:
            raise StateTransitionRefused("fork preservation requires the Superego seat")
        if occupancy is None or not occupancy.routing_authority:
            raise StateTransitionRefused(
                "fork preservation requires bound routing-authoritative Superego occupancy"
            )
        if occupancy.join.function != SeatRole.SUPEREGO:
            raise StateTransitionRefused("fork preservation requires the Superego function")
        if event.actor != SeatRole.SUPEREGO:
            raise StateTransitionRefused("fork preservation actor must be Superego")
        if preservation.actor_provider_session_ref != occupancy.join.holder_ref:
            raise StateTransitionRefused(
                "fork preservation caller session disagrees with Superego occupancy"
            )
        if not any(
            source.digest == preservation.actor_provider_identity_proof_handle
            for source in event.provenance
        ):
            raise StateTransitionRefused("fork preservation must carry its caller identity proof")

        authority_object = state.graph_objects.get(
            _event_object_id(preservation.authority_event_id)
        )
        if (
            authority_object is None
            or authority_object.attributes.get("event_kind") != EventKind.MESSAGE_ACK.value
        ):
            raise StateTransitionRefused(
                "fork preservation authority must be an existing acknowledgement event"
            )
        authority_acknowledgement = state.graph_objects.get(
            f"acknowledgement:{preservation.authority_event_id}"
        )
        if authority_acknowledgement is None:
            raise StateTransitionRefused(
                "fork preservation authority acknowledgement is not materialized"
            )
        authority_message_id = authority_acknowledgement.attributes.get("message_id")
        if authority_message_id != PRESERVE_FORK_AUTHORITY_MESSAGE_ID:
            raise StateTransitionRefused(
                "fork preservation authority belongs to the wrong ruling message"
            )
        authority_record = state.messages.get(str(authority_message_id))
        if (
            authority_record is None
            or authority_record.status != DeliveryState.DELIVERED
            or authority_record.acknowledgement_event_id != preservation.authority_event_id
            or authority_record.message.recipient_seat_id != operator_seat_id
            or authority_acknowledgement.attributes.get("seat_id") != operator_seat_id
            or authority_acknowledgement.attributes.get("disposition")
            != AcknowledgementDisposition.ACCEPTED.value
            or authority_record.message.dependency_roots.get("author_ruling")
            != preservation.author_ruling_ref
            or authority_record.message.dependency_roots.get("legacy_claude_obligation")
            != preservation.message_id
        ):
            raise StateTransitionRefused(
                "fork preservation authority does not bind the delivered ruling and target"
            )
        assert occupancy.binding_event_id is not None
        required_causes = {
            record.sent_event_id,
            preservation.authority_event_id,
            occupancy.join_event_id,
            occupancy.binding_event_id,
        }
        if not required_causes.issubset(event.causation_ids):
            raise StateTransitionRefused(
                "fork preservation must bind send, ruling authority, join and binding",
                required=sorted(required_causes),
            )

        preservation_object_id = f"message-preserve-fork:{event.event_id}"
        state = _with_graph_object(
            state,
            _object(
                event,
                object_id=preservation_object_id,
                kind="message-fork-preservation",
                content_handle=chash(preservation.to_dict()),
                coordinate="message",
                contextual=True,
                attributes={
                    **preservation.to_dict(),
                    "source_status": record.status.value,
                    "actor_seat_id": operator_seat_id,
                    "actor_function": occupancy.join.function.value,
                    "binding_event_id": occupancy.binding_event_id,
                    "provider_session_ref": (preservation.actor_provider_session_ref),
                    "provider_identity_proof_handle": (
                        preservation.actor_provider_identity_proof_handle
                    ),
                    "provider_identity_generation": (
                        preservation.actor_provider_identity_generation
                    ),
                },
            ),
        )
        state = _connect(
            state,
            event,
            relation="declares-message-preserve-fork",
            source_object_id=_event_object_id(event.event_id),
            target_object_id=preservation_object_id,
            contextual=True,
        )
        state = _connect(
            state,
            event,
            relation="preserves-fork",
            source_object_id=preservation_object_id,
            target_object_id=preservation.message_id,
            direction=MoveDirection.LINEAGE,
            operator="author-ruled-cross-fibre-quarantine",
            contextual=False,
        )
        state = _connect(
            state,
            event,
            relation="authorized-by",
            source_object_id=preservation_object_id,
            target_object_id=_event_object_id(preservation.authority_event_id),
            direction=MoveDirection.LINEAGE,
            operator="author-ruled-cross-fibre-quarantine",
            contextual=False,
        )
        messages = dict(state.messages)
        messages[preservation.message_id] = replace(
            record,
            status=DeliveryState.QUARANTINED,
            preserve_fork_event_id=event.event_id,
            preserve_fork=preservation,
            preserve_fork_source_status=record.status,
            preserve_fork_actor_seat_id=operator_seat_id,
            preserve_fork_actor_function=occupancy.join.function.value,
            preserve_fork_binding_event_id=occupancy.binding_event_id,
            preserve_fork_assumption=event.assumption,
            preserve_fork_fibre=event.fibre,
        )
        return _with_event(state, event, messages=messages)

    if event.kind == EventKind.MESSAGE_SUPERSESSION:
        if event.assumption is None or event.fibre is None:
            raise StateTransitionRefused("message supersession must declare its current fibre")
        _require_context(state, event.assumption, event.fibre)
        supersession_schema = event.payload.get("schema_version")
        legacy_supersession = supersession_schema in {
            MessageSupersession.LEGACY_V1_SCHEMA_VERSION,
            MessageSupersession.LEGACY_V2_SCHEMA_VERSION,
        }
        if legacy_supersession and state.seat_lifecycle_cutover_event_id is not None:
            raise StateTransitionRefused(
                "legacy message supersession appears after the lifecycle cutover",
                cutover_event_id=state.seat_lifecycle_cutover_event_id,
            )
        supersession = MessageSupersession.from_dict(event.payload)
        record = state.messages.get(supersession.message_id)
        if record is None:
            raise StateTransitionRefused("supersession cites unknown message")
        if record.message.sender_seat_id != supersession.sender_seat_id:
            raise StateTransitionRefused("only the original sender may supersede a message")
        sender = _require_seat(state, supersession.sender_seat_id)
        if event.actor.value != sender.role:
            raise StateTransitionRefused(
                "supersession actor does not hold the sender logical-seat role"
            )
        sender_occupancy = state.seat_occupancies.get(supersession.sender_seat_id)
        current_supersession = supersession_schema == MessageSupersession.SCHEMA_VERSION
        identity_required = current_supersession or record.status == DeliveryState.QUARANTINED
        if identity_required:
            if sender_occupancy is None or not sender_occupancy.routing_authority:
                raise StateTransitionRefused(
                    "message supersession requires authenticated original-sender occupancy"
                )
            if sender_occupancy.join.function.value != sender.role:
                raise StateTransitionRefused(
                    "message supersession function disagrees with original sender"
                )
            if sender_occupancy.binding is None:
                raise StateTransitionRefused(
                    "message supersession requires an authority-bearing sender binding"
                )
            assert sender_occupancy.binding_event_id is not None
            if supersession.provider_session_ref != sender_occupancy.join.holder_ref:
                raise StateTransitionRefused(
                    "message supersession caller is not the bound original sender"
                )
            if not any(
                source.digest == supersession.provider_identity_proof_handle
                for source in event.provenance
            ):
                raise StateTransitionRefused(
                    "message supersession must carry caller identity proof"
                )
            if not {
                sender_occupancy.join_event_id,
                sender_occupancy.binding_event_id,
            }.issubset(event.causation_ids):
                raise StateTransitionRefused(
                    "message supersession must bind original-sender join and binding"
                )
            if current_supersession:
                current_generation = sender_occupancy.join.provider_identity_generation
                if (
                    state.seat_lifecycle_cutover_event_id is None
                    or current_generation is None
                    or sender_occupancy.binding.provider_identity_generation != current_generation
                    or supersession.provider_identity_generation != current_generation
                ):
                    raise StateTransitionRefused(
                        "message supersession caller is not the exact current v2 provider generation"
                    )
        if record.status not in {
            DeliveryState.QUEUED,
            DeliveryState.PULLED,
            DeliveryState.REFUSED,
            DeliveryState.QUARANTINED,
        }:
            raise StateTransitionRefused("only a non-delivered message can be superseded")
        replacements: list[MessageState] = []
        for replacement_id in supersession.replacement_message_ids:
            replacement = state.messages.get(replacement_id)
            if replacement is None:
                raise StateTransitionRefused(
                    "supersession cites unknown replacement", replacement_id=replacement_id
                )
            if replacement.message.sender_seat_id != record.message.sender_seat_id:
                raise StateTransitionRefused(
                    "replacement belongs to a different sender", replacement_id=replacement_id
                )
            if replacement.message.recipient_seat_id != record.message.recipient_seat_id:
                raise StateTransitionRefused(
                    "replacement belongs to a different recipient", replacement_id=replacement_id
                )
            if (replacement.assumption, replacement.fibre) != (
                event.assumption,
                event.fibre,
            ):
                raise StateTransitionRefused(
                    "replacement must inhabit the supersession's current fibre",
                    replacement_id=replacement_id,
                )
            if replacement.status != DeliveryState.DELIVERED:
                raise StateTransitionRefused(
                    "replacement must have an exact delivered reconstruction proof",
                    replacement_id=replacement_id,
                    status=replacement.status.value,
                )
            if record.status == DeliveryState.QUARANTINED:
                assert sender_occupancy is not None
                assert sender_occupancy.binding_event_id is not None
                positions = {event_id: index for index, event_id in enumerate(state.event_ids)}
                if (
                    positions[replacement.sent_event_id]
                    <= positions[sender_occupancy.binding_event_id]
                ):
                    raise StateTransitionRefused(
                        "quarantined message replacement must be sent after original-sender binding",
                        replacement_id=replacement_id,
                    )
            replacements.append(replacement)

        required_causes = {record.sent_event_id}
        for replacement in replacements:
            required_causes.add(replacement.sent_event_id)
            assert replacement.acknowledgement_event_id is not None
            required_causes.add(replacement.acknowledgement_event_id)
        if not required_causes.issubset(event.causation_ids):
            raise StateTransitionRefused(
                "supersession must causally bind the old send and delivered replacements",
                required=sorted(required_causes),
            )

        supersession_object_id = f"message-supersession:{event.event_id}"
        state = _with_graph_object(
            state,
            _object(
                event,
                object_id=supersession_object_id,
                kind="message-supersession",
                content_handle=chash(supersession.to_dict()),
                # Currentness is a relation over the existing message grade, not a new
                # grade-axis schema version.  The superseded-by edge carries the distinction.
                coordinate="message",
                contextual=True,
                attributes={
                    "message_id": supersession.message_id,
                    "sender_seat_id": supersession.sender_seat_id,
                    "replacement_message_ids": list(supersession.replacement_message_ids),
                },
            ),
        )
        state = _connect(
            state,
            event,
            relation="declares-message-supersession",
            source_object_id=_event_object_id(event.event_id),
            target_object_id=supersession_object_id,
            contextual=True,
        )
        state = _connect(
            state,
            event,
            relation="retires-message",
            source_object_id=supersession_object_id,
            target_object_id=supersession.message_id,
            direction=MoveDirection.LINEAGE,
            operator="delivered-reissue-supersession",
            contextual=False,
        )
        for replacement_id in supersession.replacement_message_ids:
            state = _connect(
                state,
                event,
                relation="superseded-by",
                source_object_id=supersession.message_id,
                target_object_id=replacement_id,
                direction=MoveDirection.LINEAGE,
                operator="delivered-reissue-supersession",
                contextual=False,
            )
        messages = dict(state.messages)
        messages[supersession.message_id] = replace(
            record,
            status=DeliveryState.SUPERSEDED,
            supersession_event_id=event.event_id,
            replacement_message_ids=supersession.replacement_message_ids,
            supersession_note=supersession.note,
            supersession_provider_session_ref=supersession.provider_session_ref,
            supersession_provider_identity_proof_handle=(
                supersession.provider_identity_proof_handle
            ),
            supersession_provider_identity_generation=(supersession.provider_identity_generation),
        )
        return _with_event(state, event, messages=messages)

    if event.kind == EventKind.MESSAGE_MIGRATION_SUPERSESSION:
        if event.assumption is None or event.fibre is None:
            raise StateTransitionRefused(
                "message migration supersession must declare its current fibre"
            )
        _require_context(state, event.assumption, event.fibre)
        recovery = MessageMigrationSupersession.from_dict(event.payload)
        expected_transition_id = (
            "message-migration-supersession:"
            + recovery.recovery_manifest_root.removeprefix("sha256:")
        )
        if (
            recovery.transition_id != expected_transition_id
            or event.subject != expected_transition_id
        ):
            raise StateTransitionRefused(
                "message migration supersession identity must derive from its manifest"
            )
        if (
            state.seat_lifecycle_cutover_event_id is None
            or recovery.lifecycle_cutover_event_id != state.seat_lifecycle_cutover_event_id
        ):
            raise StateTransitionRefused(
                "message migration supersession requires the exact current v2 cutover"
            )
        if recovery.recovery_capsule_handle != MESSAGE_MIGRATION_RECOVERY_CAPSULE_HANDLE:
            raise StateTransitionRefused(
                "message migration supersession cites the wrong recovery capsule"
            )
        provenance_digests = {source.digest for source in event.provenance}
        if recovery.recovery_capsule_handle not in provenance_digests:
            raise StateTransitionRefused(
                "message migration supersession must carry the recovery capsule bytes"
            )
        if not {
            recovery.author_turn_handle,
            recovery.authority_body_handle,
            recovery.operator_provider_identity_proof_handle,
        }.issubset(provenance_digests):
            raise StateTransitionRefused(
                "message migration supersession must carry its author turn, commission body, "
                "and provider identity bytes"
            )

        operator = _require_seat(state, recovery.operator_seat_id)
        occupancy = state.seat_occupancies.get(recovery.operator_seat_id)
        if (
            recovery.operator_seat_id != "superego-seat"
            or operator.role != SeatRole.SUPEREGO.value
            or event.actor != SeatRole.SUPEREGO
            or occupancy is None
            or not occupancy.routing_authority
            or occupancy.join.function != SeatRole.SUPEREGO
            or occupancy.binding is None
            or occupancy.binding_event_id is None
        ):
            raise StateTransitionRefused(
                "message migration supersession requires current bound v2 Superego authority"
            )
        current_generation = occupancy.join.provider_identity_generation
        if (
            current_generation is None
            or occupancy.binding.provider_identity_generation != current_generation
            or recovery.operator_provider_identity_generation != current_generation
            or recovery.operator_provider_session_ref != occupancy.join.holder_ref
            or recovery.operator_provider_identity_proof_handle not in provenance_digests
        ):
            raise StateTransitionRefused(
                "message migration supersession caller is not the exact current Superego generation"
            )

        replacement = state.messages.get(recovery.replacement_message_id)
        if replacement is None:
            raise StateTransitionRefused("message migration supersession cites unknown replacement")
        if replacement.message.body_handle != recovery.replacement_body_handle or (
            replacement.assumption,
            replacement.fibre,
        ) != (event.assumption, event.fibre):
            raise StateTransitionRefused(
                "message migration supersession replacement body or fibre is contradictory"
            )
        derived_entries, correlation, replacement_reconstruction_event_id = (
            derive_message_migration_recovery_entries(
                state,
                replacement_message_id=recovery.replacement_message_id,
            )
        )
        if (
            recovery.entries != derived_entries
            or recovery.reconstruction_correlation != correlation
        ):
            raise StateTransitionRefused(
                "message migration supersession manifest does not equal the derived bundle"
            )

        historical_sender = replacement.message.sender_seat_id
        if historical_sender not in state.seat_lifecycle_invalidated_legacy_occupancies:
            raise StateTransitionRefused(
                "message migration supersession cannot prove invalidated historical sender authority",
                sender_seat_id=historical_sender,
            )
        current_sender = state.seat_occupancies.get(historical_sender)
        if current_sender is not None and (
            not current_sender.routing_authority
            or current_sender.binding is None
            or current_sender.binding_event_id is None
            or current_sender.join.provider_identity_generation is None
        ):
            raise StateTransitionRefused(
                "message migration supersession sees an unproved current sender occupancy",
                sender_seat_id=historical_sender,
            )

        authority = state.messages.get(recovery.authority_message_id)
        if (
            authority is None
            or authority.status != DeliveryState.DELIVERED
            or authority.message.sender_seat_id != "gerard-seat"
            or authority.message.recipient_seat_id != recovery.operator_seat_id
            or authority.message.message_type != "conversation-turn"
            or authority.message.body_handle != recovery.authority_body_handle
            or (authority.assumption, authority.fibre) != (event.assumption, event.fibre)
            or authority.acknowledgement_event_id != recovery.authority_acknowledgement_event_id
        ):
            raise StateTransitionRefused(
                "message migration supersession authority is not one delivered current-fibre "
                "Gerard author turn"
            )
        authority_roots = authority.message.dependency_roots
        if authority_roots.get("author_turn") != recovery.author_turn_handle:
            raise StateTransitionRefused(
                "message migration supersession authority does not bind its exact author turn"
            )
        authority_acknowledgement = state.graph_objects.get(
            f"acknowledgement:{recovery.authority_acknowledgement_event_id}"
        )
        if (
            authority_acknowledgement is None
            or authority_acknowledgement.attributes.get("seat_id") != recovery.operator_seat_id
            or authority_acknowledgement.attributes.get("disposition")
            != AcknowledgementDisposition.ACCEPTED.value
        ):
            raise StateTransitionRefused(
                "message migration supersession authority lacks accepted Superego reconstruction"
            )

        positions = {event_id: index for index, event_id in enumerate(state.event_ids)}
        cutover_position = positions[recovery.lifecycle_cutover_event_id]
        binding_position = positions[occupancy.binding_event_id]
        if (
            positions[authority.sent_event_id] <= binding_position
            or positions[recovery.authority_acknowledgement_event_id] <= binding_position
            or positions[authority.sent_event_id] <= positions[replacement.acknowledgement_event_id]
        ):
            raise StateTransitionRefused(
                "message migration supersession commission predates its current Superego "
                "binding or delivered replacement"
            )
        historical_event_ids = {
            *(entry.materialization_event_id for entry in recovery.entries),
            *(state.messages[entry.message_id].sent_event_id for entry in recovery.entries),
        }
        if any(positions[event_id] >= cutover_position for event_id in historical_event_ids):
            raise StateTransitionRefused(
                "message migration supersession evidence must be historical to the v2 cutover"
            )

        required_causes = {
            recovery.lifecycle_cutover_event_id,
            occupancy.join_event_id,
            occupancy.binding_event_id,
            authority.sent_event_id,
            recovery.authority_acknowledgement_event_id,
            replacement.sent_event_id,
            replacement.acknowledgement_event_id,
            replacement_reconstruction_event_id,
            *historical_event_ids,
        }
        if not required_causes.issubset(event.causation_ids):
            raise StateTransitionRefused(
                "message migration supersession must causally bind its complete recovery proof",
                required=sorted(required_causes),
            )

        recovery_object_id = f"message-migration-supersession:{event.event_id}"
        state = _with_graph_object(
            state,
            _object(
                event,
                object_id=recovery_object_id,
                kind="message-migration-supersession",
                content_handle=recovery.recovery_manifest_root,
                coordinate="message",
                contextual=True,
                attributes={
                    "transition_id": recovery.transition_id,
                    "recovery_manifest_root": recovery.recovery_manifest_root,
                    "replacement_message_id": recovery.replacement_message_id,
                    "operator_seat_id": recovery.operator_seat_id,
                    "message_ids": [entry.message_id for entry in recovery.entries],
                },
            ),
        )
        state = _connect(
            state,
            event,
            relation="declares-message-migration-supersession",
            source_object_id=_event_object_id(event.event_id),
            target_object_id=recovery_object_id,
            contextual=True,
        )
        messages = dict(state.messages)
        for entry in recovery.entries:
            record = messages[entry.message_id]
            state = _connect(
                state,
                event,
                relation="migration-superseded-by",
                source_object_id=entry.message_id,
                target_object_id=recovery.replacement_message_id,
                direction=MoveDirection.LINEAGE,
                operator="author-commissioned-v2-superego-recovery",
                contextual=False,
            )
            messages[entry.message_id] = replace(
                record,
                status=DeliveryState.SUPERSEDED,
                supersession_event_id=event.event_id,
                replacement_message_ids=(recovery.replacement_message_id,),
                supersession_note=recovery.note,
                supersession_provider_session_ref=(recovery.operator_provider_session_ref),
                supersession_provider_identity_proof_handle=(
                    recovery.operator_provider_identity_proof_handle
                ),
                supersession_provider_identity_generation=(
                    recovery.operator_provider_identity_generation
                ),
            )
        recoveries = dict(state.message_migration_supersessions)
        if recovery.recovery_manifest_root in recoveries:
            raise StateTransitionRefused("message migration supersession manifest already exists")
        recoveries[recovery.recovery_manifest_root] = recovery
        return _with_event(
            state,
            event,
            messages=messages,
            message_migration_supersessions=recoveries,
        )

    if event.kind == EventKind.REVISION:
        if event.assumption is None or event.fibre is None:
            raise StateTransitionRefused("revision act must declare an assumption fibre")
        _require_context(state, event.assumption, event.fibre)
        revision = RevisionAct.from_dict(event.payload)
        if event.subject != f"revision:{revision.revision_id}":
            raise StateTransitionRefused("revision event subject must identify its act")
        if revision.revision_id in state.revision_acts:
            raise StateTransitionRefused("revision id already exists")

        context = (event.assumption, event.fibre)
        same_context = [
            act
            for revision_id, act in state.revision_acts.items()
            if state.revision_contexts[revision_id] == context
        ]
        for prior in same_context:
            repeated_source = sorted(set(prior.supersedes).intersection(revision.supersedes))
            if repeated_source:
                raise StateTransitionRefused(
                    "revision source already belongs to another revision act",
                    node_refs=repeated_source,
                )
            repeated_product = sorted(set(prior.produces).intersection(revision.produces))
            if repeated_product:
                raise StateTransitionRefused(
                    "revision product has an ambiguous producer",
                    node_refs=repeated_product,
                )

        endpoints = set(revision.supersedes) | set(revision.produces)
        for revision_id, prior in state.revision_acts.items():
            prior_context = state.revision_contexts[revision_id]
            if prior_context == context:
                continue
            crossed = sorted(endpoints.intersection(prior.produces))
            if crossed:
                raise StateTransitionRefused(
                    "revision cannot consume or reproduce a node produced in another fibre",
                    node_refs=crossed,
                    produced_in={"assumption": prior_context[0], "fibre": prior_context[1]},
                )

        adjacency = _revision_adjacency(state, *context)
        for source in revision.supersedes:
            for target in revision.produces:
                if _revision_reaches(adjacency, target, source):
                    raise StateTransitionRefused(
                        "revision act would create a cycle",
                        source=source,
                        target=target,
                    )

        revision_object_id = f"revision-act:{revision.revision_id}"
        state = _with_graph_object(
            state,
            _object(
                event,
                object_id=revision_object_id,
                kind="source-revision-act",
                content_handle=chash(revision.to_dict()),
                coordinate="event",
                contextual=True,
                attributes=revision.to_dict(),
            ),
        )
        state = _connect(
            state,
            event,
            relation="declares-revision",
            source_object_id=_event_object_id(event.event_id),
            target_object_id=revision_object_id,
            direction=MoveDirection.LINEAGE,
            operator="typed-revision",
            contextual=True,
        )
        for relation, node_refs, source_is_node in (
            ("superseded-in", revision.supersedes, True),
            ("produces-revision", revision.produces, False),
        ):
            for node_ref in node_refs:
                resolved_object_id = node_ref if node_ref in state.graph_objects else None
                if resolved_object_id is not None:
                    resolved = state.graph_objects[resolved_object_id]
                    if (
                        resolved.assumption is not None
                        and (
                            resolved.assumption,
                            resolved.fibre,
                        )
                        != context
                    ):
                        raise StateTransitionRefused(
                            "revision endpoint resolves in another assumption fibre",
                            node_ref=node_ref,
                        )
                # Revision edges live on the control axis. A resolved source-detail
                # node needs an exact lineage reference, not an invalid cross-axis edge.
                if (
                    resolved_object_id is not None
                    and state.graph_objects[resolved_object_id].grade_contract_id
                    != CONTROL_AXIS_CONTRACT.contract_id
                ):
                    resolved_object_id = None
                if resolved_object_id is None:
                    resolved_object_id = _revision_node_object_id(*context, node_ref)
                    state = _with_graph_object(
                        state,
                        _object(
                            event,
                            object_id=resolved_object_id,
                            kind="revision-node",
                            content_handle=node_ref,
                            coordinate="content",
                            contextual=True,
                            attributes={"node_ref": node_ref},
                        ),
                    )
                state = _connect(
                    state,
                    event,
                    relation=relation,
                    source_object_id=(resolved_object_id if source_is_node else revision_object_id),
                    target_object_id=(revision_object_id if source_is_node else resolved_object_id),
                    direction=MoveDirection.LINEAGE,
                    operator="typed-revision",
                    contextual=True,
                )

        acts = dict(state.revision_acts)
        contexts = dict(state.revision_contexts)
        acts[revision.revision_id] = revision
        contexts[revision.revision_id] = context
        return _with_event(
            state,
            event,
            revision_acts=acts,
            revision_contexts=contexts,
        )

    if event.kind == EventKind.MESSAGE_EXPIRY:
        expiry = MessageExpiry.from_dict(event.payload)
        record = state.messages.get(expiry.message_id)
        if record is None:
            raise StateTransitionRefused("expiry cites unknown message")
        if (event.assumption, event.fibre) != (record.assumption, record.fibre):
            raise StateTransitionRefused("expiry must inhabit the message's assumption fibre")
        if record.status not in {DeliveryState.QUEUED, DeliveryState.PULLED}:
            raise StateTransitionRefused("only an undelivered message can expire")
        if _parsed_time(expiry.as_of) < _parsed_time(record.message.expires_at):
            raise StateTransitionRefused("message cannot expire before its declared deadline")
        messages = dict(state.messages)
        messages[expiry.message_id] = replace(record, status=DeliveryState.EXPIRED)
        return _with_event(state, event, messages=messages)

    if event.kind == EventKind.PERMISSION_REQUEST:
        request = PermissionRequest.from_dict(event.payload)
        requester = _require_seat(state, request.requester_seat_id)
        if event.actor.value != requester.role:
            raise StateTransitionRefused(
                "permission-request actor does not hold the requester logical-seat role"
            )
        if request.request_id in state.permission_requests:
            raise StateTransitionRefused("permission request id already exists")
        requests = dict(state.permission_requests)
        requests[request.request_id] = request
        return _with_event(state, event, permission_requests=requests)

    if event.kind == EventKind.PERMISSION_DECISION:
        decision = PermissionDecision.from_dict(event.payload)
        if decision.request_id not in state.permission_requests:
            raise StateTransitionRefused("decision cites unknown permission request")
        decider = _require_seat(state, decision.decider_seat_id)
        if event.actor.value != decider.role:
            raise StateTransitionRefused(
                "permission-decision actor does not hold the decider logical-seat role"
            )
        if decision.request_id in state.permission_decisions:
            raise StateTransitionRefused("permission request was already decided")
        decisions = dict(state.permission_decisions)
        decisions[decision.request_id] = decision
        return _with_event(state, event, permission_decisions=decisions)

    if event.kind == EventKind.WATCHER:
        registration = WatcherRegistration.from_dict(event.payload)
        if event.assumption is None or event.fibre is None:
            raise StateTransitionRefused("watcher must inhabit an assumption fibre")
        _require_context(state, event.assumption, event.fibre)
        creator = _require_seat(state, registration.created_by_seat_id)
        _require_seat(state, registration.target_seat_id)
        if event.actor.value != creator.role:
            raise StateTransitionRefused(
                "watcher actor does not hold its creating logical-seat role"
            )
        if registration.watcher_id in state.watchers:
            raise StateTransitionRefused("watcher id already exists")
        if registration.start_cursor > state.event_count:
            raise StateTransitionRefused("watcher start cursor is beyond the history head")
        if registration.source_kind == WatchSourceKind.CONCEPTRIC_EVENTS:
            allowed = {"event_kind", "subject_prefix", "correlation_id"}
            if set(registration.selector) - allowed:
                raise StateTransitionRefused("conceptric watcher selector is unsupported")
        elif "path" not in registration.selector:
            raise StateTransitionRefused("filesystem watcher must name a path")
        watcher_object_id = f"watcher:{registration.watcher_id}"
        subscription_object_id = f"subscription:{registration.watcher_id}"
        state = _with_graph_object(
            state,
            _object(
                event,
                object_id=watcher_object_id,
                kind="persistent-watcher",
                content_handle=chash(registration.to_dict()),
                coordinate="watcher",
                contextual=True,
                attributes={
                    "watcher_id": registration.watcher_id,
                    "one_shot": registration.one_shot,
                    "expires_at": registration.expires_at,
                },
            ),
        )
        state = _with_graph_object(
            state,
            _object(
                event,
                object_id=subscription_object_id,
                kind="watch-subscription",
                content_handle=chash(
                    {
                        "source_kind": registration.source_kind.value,
                        "selector": dict(registration.selector),
                    }
                ),
                coordinate="subscription",
                contextual=True,
                attributes={
                    "source_kind": registration.source_kind.value,
                    "selector": dict(registration.selector),
                },
            ),
        )
        state = _connect(
            state,
            event,
            relation="subscribes-to",
            source_object_id=watcher_object_id,
            target_object_id=subscription_object_id,
            direction=MoveDirection.DOWN,
            operator="durable-watch-subscription",
            contextual=True,
        )
        state = _connect(
            state,
            event,
            relation="dispatches-to",
            source_object_id=watcher_object_id,
            target_object_id=f"seat:{registration.target_seat_id}",
            direction=MoveDirection.UP,
            operator="logical-seat-dispatch",
            contextual=True,
        )
        state = _connect(
            state,
            event,
            relation="declares-watcher",
            source_object_id=_event_object_id(event.event_id),
            target_object_id=watcher_object_id,
            contextual=True,
        )
        watchers = dict(state.watchers)
        contexts = dict(state.watcher_contexts)
        watchers[registration.watcher_id] = registration
        contexts[registration.watcher_id] = (event.assumption, event.fibre)
        return _with_event(state, event, watchers=watchers, watcher_contexts=contexts)

    if event.kind == EventKind.WATCH_CHECKPOINT:
        checkpoint = WatchCheckpoint.from_dict(event.payload)
        registration = state.watchers.get(checkpoint.watcher_id)
        if registration is None:
            raise StateTransitionRefused("watcher checkpoint cites unknown watcher")
        creator = _require_seat(state, registration.created_by_seat_id)
        if event.actor.value != creator.role:
            raise StateTransitionRefused(
                "watcher checkpoint actor does not hold its creating logical-seat role"
            )
        context = state.watcher_contexts[checkpoint.watcher_id]
        if (event.assumption, event.fibre) != context:
            raise StateTransitionRefused("watcher checkpoint crossed assumption fibres")
        _require_context(state, *context)
        prior = state.watcher_checkpoints.get(checkpoint.watcher_id)
        expected_after = registration.start_cursor if prior is None else prior.result_cursor
        if checkpoint.after_cursor != expected_after:
            raise StateTransitionRefused(
                "watcher checkpoint does not continue its durable cursor",
                expected=expected_after,
            )
        # A checkpoint may cover its own event position (the row being applied is
        # ``state.event_count + 1``).  This prevents a watcher from waking forever on the
        # checkpoint it just wrote while keeping every matched/dispatch event pre-existing.
        if checkpoint.result_cursor > state.event_count + 1:
            raise StateTransitionRefused("watcher checkpoint exceeds the observed head")
        if prior is not None and registration.one_shot and prior.status == WatchStatus.FIRED:
            raise StateTransitionRefused("one-shot watcher already fired")
        if prior is not None and prior.status == WatchStatus.EXPIRED:
            raise StateTransitionRefused("watcher lease is terminal after expiry")
        if (
            _parsed_time(checkpoint.observed_at) >= _parsed_time(registration.expires_at)
            and checkpoint.status != WatchStatus.EXPIRED
        ):
            raise StateTransitionRefused("watcher lease expired before this checkpoint")
        positions = {event_id: index for index, event_id in enumerate(state.event_ids, 1)}
        if registration.source_kind == WatchSourceKind.CONCEPTRIC_EVENTS:
            for matched in checkpoint.matched_handles:
                position = positions.get(matched)
                if position is None or not (
                    checkpoint.after_cursor < position <= checkpoint.result_cursor
                ):
                    raise StateTransitionRefused(
                        "watcher matched event is outside its cursor window",
                        event_id=matched,
                    )
        for message_id in checkpoint.dispatch_message_ids:
            record = state.messages.get(message_id)
            if record is None or record.message.recipient_seat_id != registration.target_seat_id:
                raise StateTransitionRefused(
                    "watcher dispatch does not resolve to its target logical seat"
                )
            if record.message.sender_seat_id != registration.created_by_seat_id:
                raise StateTransitionRefused(
                    "watcher dispatch does not originate from its creating logical seat"
                )
            if record.message.message_type != registration.message_type:
                raise StateTransitionRefused(
                    "watcher dispatch does not use its registered message type"
                )
            if (record.assumption, record.fibre) != context:
                raise StateTransitionRefused(
                    "watcher dispatch crossed its registered assumption fibre"
                )
            position = positions.get(record.sent_event_id)
            if position is None or not (
                checkpoint.after_cursor < position <= checkpoint.result_cursor
            ):
                raise StateTransitionRefused(
                    "watcher dispatch message is outside its checkpoint cursor window"
                )
            if registration.source_kind == WatchSourceKind.CONCEPTRIC_EVENTS:
                causal_sources = {
                    edge.source_object_id.removeprefix("event:")
                    for edge in state.graph_edges.values()
                    if edge.relation == "causes"
                    and edge.target_object_id == _event_object_id(record.sent_event_id)
                }
                if not causal_sources.intersection(checkpoint.matched_handles):
                    raise StateTransitionRefused(
                        "event-watcher dispatch is not caused by a matched event"
                    )
        checkpoint_object_id = "watch-checkpoint:" + chash(checkpoint.to_dict()).removeprefix(
            "sha256:"
        )
        state = _with_graph_object(
            state,
            _object(
                event,
                object_id=checkpoint_object_id,
                kind="watch-checkpoint",
                content_handle=chash(checkpoint.to_dict()),
                coordinate="subscription",
                contextual=True,
                attributes=checkpoint.to_dict(),
            ),
        )
        state = _connect(
            state,
            event,
            relation="declares-watch-checkpoint",
            source_object_id=_event_object_id(event.event_id),
            target_object_id=checkpoint_object_id,
            direction=MoveDirection.DOWN,
            operator="durable-watch-checkpoint",
            contextual=True,
        )
        state = _connect(
            state,
            event,
            relation="checkpointed-at",
            source_object_id=f"watcher:{checkpoint.watcher_id}",
            target_object_id=checkpoint_object_id,
            direction=MoveDirection.DOWN,
            operator="durable-watch-cursor",
            contextual=True,
        )
        for matched_handle in checkpoint.matched_handles:
            if registration.source_kind == WatchSourceKind.CONCEPTRIC_EVENTS:
                matched_object_id = _event_object_id(matched_handle)
            else:
                matched_object_id = "filesystem-observation:" + chash(
                    {
                        "watcher_id": checkpoint.watcher_id,
                        "matched_handle": matched_handle,
                    }
                ).removeprefix("sha256:")
                state = _with_graph_object(
                    state,
                    _object(
                        event,
                        object_id=matched_object_id,
                        kind="filesystem-metadata-observation",
                        content_handle=_content_handle(matched_handle),
                        coordinate="event",
                        contextual=True,
                        attributes={"matched_handle": matched_handle},
                    ),
                )
            state = _connect(
                state,
                event,
                relation="records-watch-match",
                source_object_id=checkpoint_object_id,
                target_object_id=matched_object_id,
                direction=MoveDirection.UP,
                operator="durable-watch-match-resolution",
                contextual=True,
            )
        for message_id in checkpoint.dispatch_message_ids:
            state = _connect(
                state,
                event,
                relation="dispatched-message",
                source_object_id=checkpoint_object_id,
                target_object_id=message_id,
                direction=MoveDirection.UP,
                operator="watch-trigger-dispatch",
                contextual=True,
            )
        checkpoints = dict(state.watcher_checkpoints)
        checkpoints[checkpoint.watcher_id] = checkpoint
        return _with_event(state, event, watcher_checkpoints=checkpoints)

    if event.kind == EventKind.REPL:
        evaluation = ReplEvaluation.from_dict(event.payload)
        if evaluation.operation.value == "reconstruct":
            reconstructing_seat = _require_seat(state, evaluation.branch_id)
            if event.actor.value != reconstructing_seat.role:
                raise StateTransitionRefused(
                    "reconstruction actor does not hold the proof's logical-seat role"
                )
            reconstructed_message_id = evaluation.arguments.get("message_id")
            if reconstructed_message_id is not None:
                if not isinstance(reconstructed_message_id, str) or not reconstructed_message_id:
                    raise StateTransitionRefused(
                        "message reconstruction must name a non-empty delivery id"
                    )
                reconstructed_record = state.messages.get(reconstructed_message_id)
                if reconstructed_record is None:
                    raise StateTransitionRefused("message reconstruction cites an unknown delivery")
                if reconstructed_record.message.body_handle not in evaluation.input_handles:
                    raise StateTransitionRefused(
                        "message reconstruction did not consume its named delivery body"
                    )
                consumed_messages = (reconstructed_record,)
            else:
                # Backward-compatible fold for pre-delivery-keyed reconstruction events.  Body
                # identity is shared by broadcasts, so even the legacy path is scoped to the
                # reconstructing seat.  New bridge events always carry ``arguments.message_id``.
                consumed_messages = tuple(
                    record
                    for record in state.messages.values()
                    if record.message.recipient_seat_id == evaluation.branch_id
                    and record.message.body_handle in evaluation.input_handles
                )
            for record in consumed_messages:
                if record.message.recipient_seat_id != evaluation.branch_id:
                    raise StateTransitionRefused(
                        "message reconstruction belongs to a different logical seat"
                    )
                if record.status != DeliveryState.PULLED or record.last_pull_event_id is None:
                    raise StateTransitionRefused(
                        "message body must be pulled before reconstruction"
                    )
                if (event.assumption, event.fibre) != (record.assumption, record.fibre):
                    raise StateTransitionRefused(
                        "message reconstruction crossed its assumption fibre"
                    )
                required_causes = {
                    record.sent_event_id,
                    record.last_pull_event_id,
                }
                if not required_causes.issubset(event.causation_ids):
                    raise StateTransitionRefused(
                        "message reconstruction must causally join send and current pull",
                        required=sorted(required_causes),
                    )
            reconstruction_object_id = f"reconstruction:{event.event_id}"
            state = _with_graph_object(
                state,
                _object(
                    event,
                    object_id=reconstruction_object_id,
                    kind="typed-reconstruction",
                    content_handle=chash(evaluation.to_dict()),
                    coordinate="reconstruction",
                    contextual=True,
                    attributes={
                        "evaluation_id": evaluation.evaluation_id,
                        "branch_id": evaluation.branch_id,
                        "operation": evaluation.operation.value,
                    },
                ),
            )
            state = _connect(
                state,
                event,
                relation="declares-reconstruction",
                source_object_id=_event_object_id(event.event_id),
                target_object_id=reconstruction_object_id,
                contextual=True,
            )
            for handle in evaluation.input_handles:
                input_object_id = f"content:{handle}"
                if input_object_id not in state.graph_objects:
                    state = _with_graph_object(
                        state,
                        ConceptricObject(
                            input_object_id,
                            "content-handle",
                            _content_handle(handle),
                            None,
                            None,
                            CONTROL_AXIS_CONTRACT.contract_id,
                            "content",
                            _handle_provenance(handle),
                            {"handle": handle},
                        ),
                    )
                state = _connect(
                    state,
                    event,
                    relation="consumed-by",
                    source_object_id=input_object_id,
                    target_object_id=reconstruction_object_id,
                    direction=MoveDirection.UP,
                    operator="typed-reconstruction",
                    contextual=True,
                )
            for handle in evaluation.output_handles:
                output_object_id = "representation:" + chash(
                    {
                        "handle": handle,
                        "assumption": event.assumption,
                        "fibre": event.fibre,
                    }
                ).removeprefix("sha256:")
                state = _with_graph_object(
                    state,
                    _object(
                        event,
                        object_id=output_object_id,
                        kind="reconstruction-output",
                        content_handle=handle,
                        coordinate="content",
                        contextual=True,
                        attributes={"handle": handle},
                    ),
                )
                state = _connect(
                    state,
                    event,
                    relation="produces",
                    source_object_id=reconstruction_object_id,
                    target_object_id=output_object_id,
                    direction=MoveDirection.DOWN,
                    operator="typed-reconstruction",
                    contextual=True,
                )
        heads = dict(state.corpus_heads)
        heads[f"repl:{evaluation.branch_id}"] = event.event_id
        evaluations = dict(state.repl_evaluations)
        contexts = dict(state.repl_contexts)
        evaluations[event.event_id] = evaluation
        if event.assumption is None or event.fibre is None:
            if evaluation.operation.value == "reconstruct":
                raise StateTransitionRefused(
                    "typed reconstruction proof must declare its assumption fibre"
                )
        else:
            _require_context(state, event.assumption, event.fibre)
            contexts[event.event_id] = (
                event.assumption,
                event.fibre,
                event.actor.value,
            )
        return _with_event(
            state,
            event,
            corpus_heads=heads,
            repl_evaluations=evaluations,
            repl_contexts=contexts,
        )

    if event.kind == EventKind.OBSERVATION:
        observations = dict(state.observation_events)
        observations[event.event_id] = event
        state = replace(state, observation_events=observations)

    # Projections, decisions, promotion, rollback and observation are first-class events even
    # when their versioned payload is owned by another face.
    heads = dict(state.corpus_heads)
    heads[event.kind.value] = event.event_id
    return _with_event(state, event, corpus_heads=heads)


def replay(events: Iterable[AtlasEvent]) -> ConceptricState:
    state = ConceptricState()
    for event in events:
        state = apply_event(state, event)
    return state


def authority_checkpoint_projection(state: ConceptricState) -> dict[str, Any]:
    """Return the one pure live-authority projection checkpointed by the store.

    This deliberately excludes the unbounded graph and closed message history.  Exact historical
    evidence remains in the event/hive chain; the checkpoint carries only current routing,
    obligations, lease inputs and roots needed to reject displaced generations cheaply.
    """

    occupancy = {
        seat_id: value.to_dict() for seat_id, value in sorted(state.seat_occupancies.items())
    }
    providers: dict[str, dict[str, dict[str, Any]]] = {}
    for seat_id, value in sorted(state.seat_occupancies.items()):
        if value.routing_authority and value.binding is not None:
            providers.setdefault(value.binding.provider_session_ref, {})[seat_id] = value.to_dict()
    recipient_records: dict[str, list[dict[str, Any]]] = {}
    recipients: dict[str, dict[str, Any]] = {}
    for message_id, record in sorted(
        state.messages.items(), key=lambda item: item[1].message.cursor
    ):
        seat_id = record.message.recipient_seat_id
        visible_record = record.to_dict()
        recipient_records.setdefault(seat_id, []).append(visible_record)
        target = recipients.setdefault(seat_id, {"pending": {}})
        if record.status in {DeliveryState.QUEUED, DeliveryState.PULLED}:
            target["pending"][message_id] = visible_record
    for seat_id, records in sorted(recipient_records.items()):
        recipients[seat_id]["revision_cursor"] = max(
            int(record["message"]["cursor"]) for record in records
        )
        recipients[seat_id]["revision_event_id"] = chash(
            {
                "schema_version": "atlas.recipient-mail-accumulator/1",
                "seat_id": seat_id,
                "records": records,
            }
        )
    retired_generations = sorted(
        generation
        for generation in state.retired_seat_binding_generations.values()
        if generation
    )
    # A fixed-width membership filter is refusal-safe: false positives may reject a generation,
    # but no ancient retired generation can be accepted.  The exact lineage remains reconstructible.
    retired_bits = 0
    for generation in retired_generations:
        digest = bytes.fromhex(chash({"generation": generation}).removeprefix("sha256:"))
        for offset in (0, 2, 4, 6):
            retired_bits |= 1 << (int.from_bytes(digest[offset : offset + 2], "big") % 2048)
    pending_handles = sorted(
        {
            record.message.body_handle
            for record in state.messages.values()
            if record.status in {DeliveryState.QUEUED, DeliveryState.PULLED}
        }
    )
    development_rows = [
        record.to_dict()
        for record in sorted(state.messages.values(), key=lambda item: item.message.cursor)
        if record.message.message_type.endswith(("commission", "verdict"))
    ]
    seat_occupancy_root = chash(
        {"schema_version": "atlas.seat-occupancy-accumulator/1", "occupancy": occupancy}
    )
    provider_session_root = chash(
        {"schema_version": "atlas.provider-session-accumulator/1", "providers": providers}
    )
    region_leases = {
        lease_id: lease.to_dict() for lease_id, lease in sorted(state.region_leases.items())
    }
    region_lease_root = chash(
        {"schema_version": "atlas.region-lease-accumulator/1", "leases": region_leases}
    )
    return {
        "schema_version": "atlas.live-authority-projection/1",
        "active_context": {
            "assumption": state.active_assumption,
            "fibre": state.active_fibre,
        },
        "seat_occupancy": occupancy,
        "seat_occupancy_root": seat_occupancy_root,
        "provider_sessions": providers,
        "provider_session_root": provider_session_root,
        "recipient_mail": recipients,
        "region_leases": region_leases,
        "region_lease_root": region_lease_root,
        "development_review_root": chash(
            {"schema_version": "atlas.development-review-root/1", "rows": development_rows}
        ),
        "seat_mail_frontier_root": chash(
            {"schema_version": "atlas.seat-mail-frontier-root/1", "recipients": recipients}
        ),
        "retired_generation_membership": {
            "schema_version": "atlas.retired-generation-membership/1",
            "algorithm": "refusal-safe-bloom-2048x4",
            "bits_hex": retired_bits.to_bytes(256, "big").hex(),
            "root": chash(
                {
                    "schema_version": "atlas.retired-generation-membership/1",
                    "bits_hex": retired_bits.to_bytes(256, "big").hex(),
                }
            ),
        },
        "unresolved_obligation_handles": pending_handles,
        "synthetics_genesis_handles": sorted(
            event_id
            for kind, event_id in state.corpus_heads.items()
            if "synthetic" in kind.casefold()
        ),
    }


__all__ = [
    "BRIDGE_API_VERSION",
    "BRIDGE_OPERATIONS",
    "PROVIDER_SCHEMA",
    "ConceptricState",
    "MessageState",
    "RegionLeaseState",
    "RegionPublicationState",
    "SeatOccupancy",
    "SeatState",
    "TransactionState",
    "apply_event",
    "authority_checkpoint_projection",
    "bootstrap_crutch_retirement",
    "replay",
]
