"""Read-only conjugate projection of the single canonical ConceptricStore.

Sensorium owns no journal, cursor, message ledger, or projection cache. The store
verifies canonical rows, ``atlas.state.replay`` folds their events, and both faces
below render that same disposable state.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from atlas.errors import AtlasError
from atlas.history import AtlasEvent, EventKind, Validity
from atlas.migration import (
    ATLAS_MIGRATION_STAGES,
    MigrationReplay,
    replay_migration,
)
from atlas.state import BRIDGE_API_VERSION, PROVIDER_SCHEMA, replay
from atlas.store import ConceptricStore

PROJECTION_SCHEMA = "atlas.sensorium.seat-fabric-projection.v1"


class ProjectionContractRefused(ValueError):
    """The provider cannot be projected without inventing a second contract."""


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _array(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _sha256_handle(value: Any) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        return False
    digest = value.removeprefix("sha256:")
    return len(digest) == 64 and all(character in "0123456789abcdef" for character in digest)


def _event_index(events: Iterable[AtlasEvent]) -> dict[str, AtlasEvent]:
    return {event.event_id: event for event in events}


def _related_event(
    events: Iterable[AtlasEvent], kind: EventKind, field: str, value: str
) -> AtlasEvent | None:
    for event in events:
        if event.kind == kind and event.payload.get(field) == value:
            return event
    return None


def _causal_chains(events: tuple[AtlasEvent, ...]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for sequence, event in enumerate(events, start=1):
        missing = [cause for cause in event.causation_ids if cause not in seen]
        result.append(
            {
                "sequence": sequence,
                "event_id": event.event_id,
                "kind": event.kind.value,
                "subject": event.subject,
                "correlation_id": event.correlation_id,
                "causes": list(event.causation_ids),
                "state": "BROKEN" if missing else "ROOT" if not event.causation_ids else "LINKED",
                "missing_or_non_prior_causes": missing,
                "assumption": event.assumption,
                "fibre": event.fibre,
                "provenance": [item.to_dict() for item in event.provenance],
            }
        )
        seen.add(event.event_id)
    return result


def _residuals(events: tuple[AtlasEvent, ...]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for event in events:
        residual = event.residual.to_dict()
        loud = residual["status"] != "within_bound" or event.validity != Validity.VALID
        result.append(
            {
                "event_id": event.event_id,
                "kind": event.kind.value,
                "validity": event.validity.value,
                **residual,
                "loud": loud,
            }
        )
    return result


def _messages(
    snapshot: Mapping[str, Any], events: tuple[AtlasEvent, ...]
) -> list[dict[str, Any]]:
    by_id = _event_index(events)
    rendered: list[dict[str, Any]] = []
    for message_id, raw_record in sorted(_mapping(snapshot.get("messages")).items()):
        record = _mapping(raw_record)
        message = _mapping(record.get("message"))
        sent_event_id = record.get("sent_event_id")
        acknowledgement_event_id = record.get("acknowledgement_event_id")
        acknowledgement_event = (
            by_id.get(str(acknowledgement_event_id)) if acknowledgement_event_id else None
        )
        acknowledgement = (
            _mapping(acknowledgement_event.payload) if acknowledgement_event else {}
        )
        reconstruction_event_id = acknowledgement.get("reconstruction_event_id")
        reconstruction_event = (
            by_id.get(str(reconstruction_event_id)) if reconstruction_event_id else None
        )
        expiry_event = _related_event(
            events, EventKind.MESSAGE_EXPIRY, "message_id", str(message_id)
        )
        supersession_event_id = record.get("supersession_event_id")
        supersession_event = (
            by_id.get(str(supersession_event_id)) if supersession_event_id else None
        )
        decision_event = _related_event(
            events, EventKind.DECISION, "message_id", str(message_id)
        )
        ack_causes = acknowledgement_event.causation_ids if acknowledgement_event else ()
        accepted_ack = (
            acknowledgement.get("disposition") == "accepted"
            and reconstruction_event is not None
            and sent_event_id in ack_causes
            and reconstruction_event_id in ack_causes
        )
        delivered = bool(
            record.get("delivered")
            and record.get("status") == "delivered"
            and accepted_ack
        )
        decided = bool(
            delivered
            and decision_event is not None
            and decision_event.validity == Validity.VALID
            and sent_event_id in decision_event.causation_ids
            and acknowledgement_event_id in decision_event.causation_ids
        )
        rendered.append(
            {
                "message_id": message_id,
                "message_type": message.get("message_type"),
                "sender_seat_id": message.get("sender_seat_id"),
                "recipient_seat_id": message.get("recipient_seat_id"),
                "body_handle": message.get("body_handle"),
                "dependency_roots": _mapping(message.get("dependency_roots")),
                "expires_at": message.get("expires_at"),
                "provider_status": record.get("status"),
                "delivered": delivered,
                "decided": decided,
                "send_event_id": sent_event_id,
                "pull_event_id": record.get("last_pull_event_id"),
                "expiry_event_id": None if expiry_event is None else expiry_event.event_id,
                "supersession": {
                    "event_id": supersession_event_id,
                    "verified_in_history": supersession_event is not None,
                    "replacement_message_ids": list(
                        record.get("replacement_message_ids") or []
                    ),
                    "superseded_by": list(record.get("superseded_by") or []),
                    "note": record.get("supersession_note"),
                },
                "acknowledgement": {
                    "event_id": acknowledgement_event_id,
                    "disposition": acknowledgement.get("disposition"),
                    "note": acknowledgement.get("note"),
                    "accepted": bool(accepted_ack),
                },
                "reconstruction_proof": {
                    "handle": record.get("reconstruction_handle"),
                    "event_id": reconstruction_event_id,
                    "verified_in_history": reconstruction_event is not None,
                },
                "decision_event_id": None if decision_event is None else decision_event.event_id,
            }
        )
    return rendered


def _message_causal_chains(
    messages: Iterable[Mapping[str, Any]], events: tuple[AtlasEvent, ...]
) -> list[dict[str, Any]]:
    by_id = _event_index(events)
    result: list[dict[str, Any]] = []
    for message in messages:
        send_id = message.get("send_event_id")
        pull_id = message.get("pull_event_id")
        reconstruction_id = _mapping(message.get("reconstruction_proof")).get("event_id")
        acknowledgement_id = _mapping(message.get("acknowledgement")).get("event_id")
        expiry_id = message.get("expiry_event_id")
        supersession_id = _mapping(message.get("supersession")).get("event_id")
        decision_id = message.get("decision_event_id")
        stages: list[dict[str, Any]] = []
        for stage, event_id in (
            ("send", send_id),
            ("pull", pull_id),
            ("reconstruction", reconstruction_id),
            ("acknowledgement", acknowledgement_id),
            ("expiry", expiry_id),
            ("supersession", supersession_id),
            ("decision", decision_id),
        ):
            if not event_id:
                continue
            item = by_id.get(str(event_id))
            stages.append(
                {
                    "stage": stage,
                    "event_id": event_id,
                    "kind": None if item is None else item.kind.value,
                    "causes": [] if item is None else list(item.causation_ids),
                    "verified_in_history": item is not None,
                }
            )
        reconstruction = by_id.get(str(reconstruction_id)) if reconstruction_id else None
        acknowledgement = (
            by_id.get(str(acknowledgement_id)) if acknowledgement_id else None
        )
        full_exchange_chain = bool(
            message.get("delivered")
            and send_id
            and pull_id
            and reconstruction_id
            and acknowledgement_id
            and reconstruction is not None
            and send_id in reconstruction.causation_ids
            and pull_id in reconstruction.causation_ids
            and acknowledgement is not None
            and send_id in acknowledgement.causation_ids
            and reconstruction_id in acknowledgement.causation_ids
        )
        result.append(
            {
                "message_id": message.get("message_id"),
                "provider_status": message.get("provider_status"),
                "delivered": bool(message.get("delivered")),
                "canonical_delivery_proof": bool(
                    message.get("delivered")
                    and _mapping(message.get("acknowledgement")).get("accepted")
                ),
                "full_send_pull_reconstruction_ack_chain": full_exchange_chain,
                "stages": stages,
            }
        )
    return result


def _exchange_residuals(messages: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    codes = {
        "queued": "message-queued-awaiting-pull-reconstruction-ack",
        "pulled": "message-pulled-awaiting-reconstruction-ack",
        "refused": "message-refused-undelivered",
        "expired": "message-expired-undelivered",
        "superseded": "message-superseded-by-delivered-reissue",
    }
    result: list[dict[str, Any]] = []
    for message in messages:
        if message.get("delivered"):
            continue
        status = str(message.get("provider_status"))
        result.append(
            {
                "domain": "exchange",
                "code": codes.get(status, "message-not-delivered"),
                "message_id": message.get("message_id"),
                "provider_status": status,
                "delivered": False,
                "loud": True,
            }
        )
    return result


def _graph_topology(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    graph = _mapping(snapshot.get("graph"))
    objects = _mapping(graph.get("objects"))
    edges = _mapping(graph.get("edges"))
    unresolved = []
    for edge_id, raw_edge in sorted(edges.items()):
        edge = _mapping(raw_edge)
        missing = [
            endpoint
            for endpoint in (edge.get("source_object_id"), edge.get("target_object_id"))
            if endpoint not in objects
        ]
        if missing:
            unresolved.append({"edge_id": edge_id, "missing_object_ids": missing})
    non_content_addressed = [
        object_id
        for object_id, raw_object in sorted(objects.items())
        if not _sha256_handle(_mapping(raw_object).get("content_handle"))
    ]
    return {
        "schema_version": graph.get("schema_version"),
        "object_count": graph.get("object_count"),
        "edge_count": graph.get("edge_count"),
        "rendered_object_count": len(objects),
        "rendered_edge_count": len(edges),
        "content_addressed": not non_content_addressed,
        "non_content_addressed_object_ids": non_content_addressed,
        "unresolved_endpoints": unresolved,
        "topology_status": (
            "VERIFIED"
            if not non_content_addressed
            and not unresolved
            and graph.get("object_count") == len(objects)
            and graph.get("edge_count") == len(edges)
            else "BROKEN"
        ),
        "objects": dict(objects),
        "edges": dict(edges),
    }


def _provider_session_holders(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    graph = _mapping(snapshot.get("graph"))
    objects = _mapping(graph.get("objects"))
    edges = _mapping(graph.get("edges"))
    seats = _mapping(snapshot.get("seats"))
    held_seats: dict[str, set[str]] = defaultdict(set)
    for raw_edge in edges.values():
        edge = _mapping(raw_edge)
        if edge.get("relation") != "holds-seat":
            continue
        target = str(edge.get("target_object_id"))
        held_seats[str(edge.get("source_object_id"))].add(
            target.removeprefix("seat:")
        )
    result: list[dict[str, Any]] = []
    for object_id, raw_object in sorted(objects.items()):
        item = _mapping(raw_object)
        if item.get("kind") != "provider-session-holder":
            continue
        holder_ref = _mapping(item.get("attributes")).get("holder_ref")
        seat_ids = sorted(held_seats.get(str(object_id), []))
        current_seats = [
            seat_id
            for seat_id in seat_ids
            if _mapping(seats.get(seat_id)).get("holder_ref") == holder_ref
        ]
        result.append(
            {
                "session_object_id": object_id,
                "content_handle": item.get("content_handle"),
                "holder_ref": holder_ref,
                "held_seat_ids": seat_ids,
                "current_seat_ids": current_seats,
                "current": bool(current_seats),
            }
        )
    return result


def _watchers(
    snapshot: Mapping[str, Any],
    events: tuple[AtlasEvent, ...],
    messages: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    messages_by_id = {str(item.get("message_id")): item for item in messages}
    result: list[dict[str, Any]] = []
    for watcher_id, raw_watcher in sorted(_mapping(snapshot.get("watchers")).items()):
        watcher = _mapping(raw_watcher)
        checkpoint = _mapping(watcher.get("checkpoint"))
        registration_event = _related_event(
            events, EventKind.WATCHER, "watcher_id", str(watcher_id)
        )
        checkpoint_events = [
            item
            for item in events
            if item.kind == EventKind.WATCH_CHECKPOINT
            and item.payload.get("watcher_id") == watcher_id
        ]
        checkpoint_history = []
        dispatches = []
        seen_dispatches: set[str] = set()
        for checkpoint_event in checkpoint_events:
            checkpoint_payload = _mapping(checkpoint_event.payload)
            history_dispatches = []
            for message_id in _array(checkpoint_payload.get("dispatch_message_ids")):
                message = _mapping(messages_by_id.get(str(message_id)))
                dispatch = {
                    "message_id": message_id,
                    "provider_status": message.get("provider_status"),
                    "currently_delivered": bool(message.get("delivered")),
                    "delivery_requires_separate_accepted_ack": True,
                    "checkpoint_event_id": checkpoint_event.event_id,
                }
                history_dispatches.append(dispatch)
                if str(message_id) not in seen_dispatches:
                    dispatches.append(dispatch)
                    seen_dispatches.add(str(message_id))
            checkpoint_history.append(
                {
                    "event_id": checkpoint_event.event_id,
                    "checkpoint": dict(checkpoint_payload),
                    "dispatches": history_dispatches,
                }
            )
        result.append(
            {
                "watcher_id": watcher_id,
                "registration": dict(_mapping(watcher.get("registration"))),
                "assumption": watcher.get("assumption"),
                "fibre": watcher.get("fibre"),
                "registration_event_id": (
                    None if registration_event is None else registration_event.event_id
                ),
                "checkpoint": dict(checkpoint) if checkpoint else None,
                "checkpoint_event_id": (
                    None if not checkpoint_events else checkpoint_events[-1].event_id
                ),
                "checkpoint_history_event_ids": [
                    item.event_id for item in checkpoint_events
                ],
                "checkpoint_history": checkpoint_history,
                "dispatch_confers_delivery": False,
                "dispatches": dispatches,
            }
        )
    return result


def _watcher_residuals(watchers: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for watcher in watchers:
        for dispatch in _array(watcher.get("dispatches")):
            item = _mapping(dispatch)
            if item.get("currently_delivered"):
                continue
            result.append(
                {
                    "domain": "watcher",
                    "code": "watcher-dispatch-awaiting-reconstruction-ack",
                    "watcher_id": watcher.get("watcher_id"),
                    "message_id": item.get("message_id"),
                    "provider_status": item.get("provider_status"),
                    "delivered": False,
                    "loud": True,
                }
            )
    return result


def _permissions(
    snapshot: Mapping[str, Any], events: tuple[AtlasEvent, ...]
) -> list[dict[str, Any]]:
    rendered: list[dict[str, Any]] = []
    for request_id, raw_permission in sorted(_mapping(snapshot.get("permissions")).items()):
        permission = _mapping(raw_permission)
        request = _mapping(permission.get("request"))
        decision = _mapping(permission.get("decision"))
        request_event = _related_event(
            events, EventKind.PERMISSION_REQUEST, "request_id", str(request_id)
        )
        decision_event = _related_event(
            events, EventKind.PERMISSION_DECISION, "request_id", str(request_id)
        )
        rendered.append(
            {
                "request_id": request_id,
                "requester_seat_id": request.get("requester_seat_id"),
                "permission": request.get("permission"),
                "target": request.get("target"),
                "expires_at": request.get("expires_at"),
                "status": decision.get("outcome", "pending"),
                "decided": bool(decision),
                "decision": decision or None,
                "request_event_id": None if request_event is None else request_event.event_id,
                "decision_event_id": None if decision_event is None else decision_event.event_id,
            }
        )
    return rendered


def _lifecycle(events: tuple[AtlasEvent, ...], current: Any) -> dict[str, Any]:
    transitions = []
    for event in events:
        if event.kind != EventKind.LIFECYCLE:
            continue
        transitions.append(
            {
                "event_id": event.event_id,
                "occurred_at": event.occurred_at,
                "action": event.payload.get("action"),
                "from": event.payload.get("from"),
                "to": event.payload.get("to"),
                "receipt_id": event.payload.get("receipt_id"),
            }
        )
    return {"current": current, "transitions": transitions}


def _reconstruction_receipts(events: tuple[AtlasEvent, ...]) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    for event in events:
        is_reconstruction = event.kind in {
            EventKind.MOVE,
            EventKind.JOIN,
            EventKind.TRANSPORT,
            EventKind.MATERIALIZATION,
        } or (
            event.kind == EventKind.REPL and event.payload.get("operation") == "reconstruct"
        )
        if is_reconstruction:
            receipts.append(
                {
                    "event_id": event.event_id,
                    "kind": event.kind.value,
                    "subject": event.subject,
                    "assumption": event.assumption,
                    "fibre": event.fibre,
                    "payload": dict(event.payload),
                    "provenance": [item.to_dict() for item in event.provenance],
                    "residual": event.residual.to_dict(),
                    "validity": event.validity.value,
                }
            )
    return receipts


def _migration_projection(
    events: tuple[AtlasEvent, ...],
    migration: MigrationReplay | None,
    refusal: AtlasError | None,
) -> dict[str, Any]:
    """Expose migration state as handles, never as a second materialized ledger.

    ``replay_migration`` has already validated stage schemas and causal lineage against the
    canonical store.  A refused replay therefore exposes no stage claims: retaining a
    plausible-looking prefix beside a malformed tail would turn a loud refusal into false
    progress.
    """

    if refusal is not None:
        residual = {
            "domain": "migration",
            "code": "migration-replay-refused",
            "reason": refusal.reason,
            "message": refusal.message,
            "detail": dict(refusal.detail),
            "loud": True,
        }
        return {
            "status": "REFUSED",
            "programme": list(ATLAS_MIGRATION_STAGES),
            "stages": [],
            "axes": {axis: [] for axis in ("material", "judged", "walked")},
            "missing_stage_ids": list(ATLAS_MIGRATION_STAGES),
            "residuals": [residual],
        }

    stages = {} if migration is None else migration.stages
    event_ids = {} if migration is None else migration.event_ids
    events_by_id = _event_index(events)
    rendered: list[dict[str, Any]] = []
    residuals: list[dict[str, Any]] = []
    missing = [stage_id for stage_id in ATLAS_MIGRATION_STAGES if stage_id not in stages]
    if missing:
        residuals.append(
            {
                "domain": "migration",
                "code": "migration-stage-set-incomplete",
                "missing_stage_ids": missing,
                "loud": True,
            }
        )

    for stage_id in ATLAS_MIGRATION_STAGES:
        stage = stages.get(stage_id)
        if stage is None:
            continue
        event_id = event_ids.get(stage_id)
        event = events_by_id.get(str(event_id))
        if event is None:
            residuals.append(
                {
                    "domain": "migration",
                    "code": "migration-stage-event-handle-unresolved",
                    "stage_id": stage_id,
                    "event_id": event_id,
                    "loud": True,
                }
            )
            continue
        payload = _mapping(event.payload)
        rendered.append(
            {
                "stage_id": stage.stage_id,
                "revision": stage.revision,
                "material": stage.material,
                "judged": stage.judged,
                "walked": stage.walked,
                "superseded_by": stage.superseded_by,
                "event_handle": event.event_id,
                "object_id": payload.get("object_id"),
                "content_handle": payload.get("content_handle"),
                "causation_handles": list(event.causation_ids),
                "source_handles": [item.to_dict() for item in event.provenance],
            }
        )

    axes = {
        axis: [
            {
                "stage_id": item["stage_id"],
                "value": item[axis],
                "event_handle": item["event_handle"],
                "content_handle": item["content_handle"],
            }
            for item in rendered
        ]
        for axis in ("material", "judged", "walked")
    }
    return {
        "status": "INCOMPLETE" if residuals else "VERIFIED",
        "programme": list(ATLAS_MIGRATION_STAGES),
        "stages": rendered,
        "axes": axes,
        "missing_stage_ids": missing,
        "residuals": residuals,
    }


def build_seat_fabric(
    events: Iterable[AtlasEvent],
    *,
    store_ref: str,
    migration: MigrationReplay | None = None,
    migration_refusal: AtlasError | None = None,
) -> dict[str, Any]:
    """Fold verified canonical events into one disposable Sensorium projection."""

    records = tuple(events)
    state = replay(records)
    snapshot = state.provider_snapshot()
    if snapshot.get("schema_version") != PROVIDER_SCHEMA:
        raise ProjectionContractRefused("provider snapshot schema is not canonical")
    bridge = _mapping(snapshot.get("bridge_api"))
    if bridge.get("schema_version") != BRIDGE_API_VERSION:
        raise ProjectionContractRefused("seat bridge schema is not canonical")

    chains = _causal_chains(records)
    residuals = _residuals(records)
    messages = _messages(snapshot, records)
    message_causal_chains = _message_causal_chains(messages, records)
    exchange_residuals = _exchange_residuals(messages)
    graph_topology = _graph_topology(snapshot)
    session_holders = _provider_session_holders(snapshot)
    watchers = _watchers(snapshot, records, messages)
    watcher_residuals = _watcher_residuals(watchers)
    permissions = _permissions(snapshot, records)
    migration_projection = _migration_projection(
        records, migration, migration_refusal
    )
    jury_work = [item for item in messages if item.get("message_type") == "jury-work"]
    fibres: dict[tuple[str | None, str | None], list[str]] = defaultdict(list)
    for event in records:
        fibres[(event.assumption, event.fibre)].append(event.event_id)

    event_loud = [item for item in residuals if item["loud"]]
    topology_residuals = []
    if graph_topology["topology_status"] != "VERIFIED":
        topology_residuals.append(
            {
                "domain": "graph",
                "code": "conceptric-topology-not-verified",
                "unresolved_endpoints": graph_topology["unresolved_endpoints"],
                "non_content_addressed_object_ids": graph_topology[
                    "non_content_addressed_object_ids"
                ],
                "loud": True,
            }
        )
    migration_residuals = _array(migration_projection.get("residuals"))
    loud = [
        *event_loud,
        *exchange_residuals,
        *watcher_residuals,
        *topology_residuals,
        *migration_residuals,
    ]
    return {
        "schema_version": PROJECTION_SCHEMA,
        "status": "PARTIAL" if loud else "GREEN",
        "source": {
            "authority": PROVIDER_SCHEMA,
            "bridge_api": BRIDGE_API_VERSION,
            "store_ref": store_ref,
            "storage_backend": "sqlite",
            "database_ref": str(Path(store_ref) / "conceptric.sqlite3"),
            "event_count": snapshot.get("event_count"),
            "head_event_id": snapshot.get("head_event_id"),
        },
        "truth_audit": {
            "authoritative_store": "ConceptricStore",
            "write_door": bridge.get("write_door"),
            "projection_stores": 0,
            "sensorium_cursors": 0,
            "second_truth_detected": False,
        },
        "lifecycle": _lifecycle(records, snapshot.get("lifecycle")),
        "seats": _mapping(snapshot.get("seats")),
        "provider_session_holders": session_holders,
        "graph_topology": graph_topology,
        "active_context": _mapping(snapshot.get("active_context")),
        "assumption_fibres": [
            {"assumption": assumption, "fibre": fibre, "event_ids": event_ids}
            for (assumption, fibre), event_ids in sorted(
                fibres.items(), key=lambda item: (str(item[0][0]), str(item[0][1]))
            )
        ],
        "transports": [
            dict(event.payload) for event in records if event.kind == EventKind.TRANSPORT
        ],
        "reconstruction_receipts": _reconstruction_receipts(records),
        "causal_chains": chains,
        "messages": messages,
        "message_causal_chains": message_causal_chains,
        "jury_work": jury_work,
        "delivery_policy": bridge.get("delivery_rule"),
        "provider_seat_cursors": _mapping(snapshot.get("seat_cursors")),
        "permissions": permissions,
        "migration": migration_projection,
        "watchers": watchers,
        "residuals": residuals,
        "exchange_residuals": exchange_residuals,
        "watcher_residuals": watcher_residuals,
        "topology_residuals": topology_residuals,
        "migration_residuals": migration_residuals,
        "loud_residuals": loud,
    }


def project_store(path: str | Path) -> dict[str, Any]:
    """Read and verify the single ConceptricStore without writing any state."""

    store_root = Path(path)
    store = ConceptricStore(store_root)
    # Verify both the hash chain and its normalized graph projection before rendering.
    store.replay()
    migration: MigrationReplay | None = None
    migration_refusal: AtlasError | None = None
    try:
        migration = replay_migration(store)
    except AtlasError as exc:
        migration_refusal = exc
    return build_seat_fabric(
        store.events(),
        store_ref=str(store_root),
        migration=migration,
        migration_refusal=migration_refusal,
    )


def render_seat_fabric_text(projection: Mapping[str, Any]) -> str:
    """Render the JSON projection without adding facts absent from canonical events."""

    source = _mapping(projection.get("source"))
    lifecycle = _mapping(projection.get("lifecycle"))
    lines = [
        f"ATLAS SEAT FABRIC — {projection.get('status')}",
        (
            f"truth: {source.get('authority')} via {source.get('bridge_api')} "
            f"events={source.get('event_count')} head={source.get('head_event_id')}"
        ),
        (
            f"store: {source.get('store_ref')} "
            f"({source.get('storage_backend')}={source.get('database_ref')}; "
            "read-only projection; no Sensorium cursor)"
        ),
        "",
        "LIFECYCLE",
        f"current: {lifecycle.get('current')}",
        str(lifecycle.get("transitions", [])),
        "",
        "SEATS",
        str(projection.get("seats", {})),
        "",
        "PROVIDER SESSION HOLDERS",
        str(projection.get("provider_session_holders", [])),
        "",
        "CONTENT-ADDRESSED GRAPH TOPOLOGY",
        str(projection.get("graph_topology", {})),
        "",
        "CAUSAL CHAINS",
    ]
    for chain in _array(projection.get("causal_chains")):
        item = _mapping(chain)
        lines.append(
            f"{item.get('sequence')} {item.get('event_id')} {item.get('kind')} "
            f"<- {item.get('causes')} [{item.get('state')}]"
        )
    lines.extend(
        [
            "",
            "ASSUMPTION FIBRES / TRANSPORTS / RECONSTRUCTION",
            str(projection.get("active_context", {})),
            str(projection.get("assumption_fibres", [])),
            str(projection.get("transports", [])),
            str(projection.get("reconstruction_receipts", [])),
            "",
            "EXCHANGE",
            f"delivery policy: {projection.get('delivery_policy')}",
            f"provider seat cursors: {projection.get('provider_seat_cursors', {})}",
            str(projection.get("messages", [])),
            "",
            "MESSAGE CAUSAL CHAINS",
            str(projection.get("message_causal_chains", [])),
            "",
            "DURABLE WATCHERS / CHECKPOINTS",
            str(projection.get("watchers", [])),
            "",
            "JURY WORK",
            str(projection.get("jury_work", [])),
            "",
            "PERMISSIONS",
            str(projection.get("permissions", [])),
            "",
            "ATLAS MIGRATION — HANDLE-COMPLETE / DESCENT ON DEMAND",
            str(projection.get("migration", {})),
            "",
            "LOUD RESIDUALS",
            *[str(item) for item in _array(projection.get("loud_residuals"))],
        ]
    )
    return "\n".join(lines) + "\n"
