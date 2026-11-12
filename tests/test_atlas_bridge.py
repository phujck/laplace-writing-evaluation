from __future__ import annotations

import json
import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from atlas.errors import (
    BlobHashMismatch,
    BlobMissing,
    HistoryChainMismatch,
    StateTransitionRefused,
    StoreError,
    StoreLockTimeout,
)

from laplace.representation import atlas_bridge as bridge
from laplace.engine import front_feedback

PROVIDER = "codex"
MODEL = "gpt-5"
EXPIRES = "2026-08-24T18:00:00Z"


def _feedback_anchor() -> dict[str, object]:
    return {
        "semantic_anchor": "atlas-object:object:current-p0",
        "kind": "object",
        "label": "Current P0",
        "model_handle": "sha256:" + ("1" * 64),
        "shown_handle": "sha256:" + ("2" * 64),
        "selection": {
            "lens": "Continuity",
            "focus": "object:current-p0",
            "edge": None,
            "grade": "near",
            "exposition": "E3",
            "viewport": "wide",
        },
        "source": {"git_commit": "git:" + ("3" * 40)},
        "currentness": {"status": "CURRENT"},
        "route": {"work_family": "semantic-memory", "authority_effect": "none"},
    }


def test_front_feedback_adapter_appends_and_rehydrates_canonical_events() -> None:
    _bootstrap()
    before = bridge.drift_token()["cursor"]
    adapter = bridge.AtlasFrontFeedbackAdapter()
    command = front_feedback.create_command(
        command_id="feedback-command:one",
        actor="gerard",
        text="Keep this observation attached to the exact causal object.",
        anchor=_feedback_anchor(),
    )

    appended = front_feedback.execute(
        adapter,
        command,
        occurred_at="2026-08-28T14:00:00Z",
    )

    assert appended["ok"] is True
    assert appended["status"] == "APPENDED"
    assert appended["position_handle"].startswith("front-feedback-position:sha256:")
    assert appended["adapter_receipt"]["atlas"]["sequence"] == before + 1
    assert appended["authority_effect"] == "none"

    projection = front_feedback.read(
        bridge.AtlasFrontFeedbackAdapter(),
        anchor_catalog=[_feedback_anchor()],
        catalog_complete=True,
        visible_anchor_ids=["atlas-object:object:current-p0"],
    )
    assert projection["status"] == "CURRENT"
    assert projection["persistence"] == {
        "required_adapter_schema": front_feedback.ADAPTER_SCHEMA,
        "available": True,
        "status": "CURRENT",
        "authority_effect": "none",
    }
    assert len(projection["annotations"]) == 1
    annotation = projection["annotations"][0]
    assert annotation["text"] == command["text"]
    assert annotation["anchor_currentness"]["status"] == "CURRENT"
    assert annotation["anchor_currentness"]["visibility"] == "VISIBLE"


def test_front_feedback_adapter_cas_allows_only_one_concurrent_append() -> None:
    _bootstrap()
    before = bridge.drift_token()["cursor"]
    first = bridge.AtlasFrontFeedbackAdapter()
    second = bridge.AtlasFrontFeedbackAdapter()
    assert first.read_events() == ()
    assert second.read_events() == ()
    event_one = front_feedback._event_for(
        front_feedback.create_command(
            command_id="feedback-command:first",
            actor="gerard",
            text="First concurrent comment.",
            anchor=_feedback_anchor(),
        ),
        occurred_at="2026-08-28T14:00:00Z",
    )
    event_two = front_feedback._event_for(
        front_feedback.create_command(
            command_id="feedback-command:second",
            actor="gerard",
            text="Second concurrent comment.",
            anchor=_feedback_anchor(),
        ),
        occurred_at="2026-08-28T14:00:01Z",
    )

    accepted = first.append_event(event_one)
    refused = second.append_event(event_two)

    assert accepted["accepted"] is True
    assert refused["accepted"] is False
    assert "frontier moved" in refused["reason"]
    fresh = bridge.AtlasFrontFeedbackAdapter()
    assert tuple(event["command_id"] for event in fresh.read_events()) == (
        "feedback-command:first",
    )
    assert bridge.drift_token()["cursor"] == before + 1


def test_blueprint_completion_history_retains_exact_ledger_order_without_claiming_revision() -> None:
    first = SimpleNamespace(
        kind=bridge.EventKind.OBSERVATION,
        event_id="event:first",
        payload={
            "schema_version": "atlas.blueprint-generation/1",
            "generation_id": "sha256:" + "a" * 64,
        },
    )
    irrelevant = SimpleNamespace(
        kind=bridge.EventKind.LIFECYCLE,
        event_id="event:middle",
        payload={"schema_version": "lifecycle-transition/1"},
    )
    latest = SimpleNamespace(
        kind=bridge.EventKind.OBSERVATION,
        event_id="event:latest",
        payload={
            "schema_version": "atlas.blueprint-generation/5",
            "generation_id": "sha256:" + "b" * 64,
        },
    )

    assert bridge._blueprint_completion_history((first, irrelevant, latest)) == [
        {
            "generation_id": "sha256:" + "a" * 64,
            "completion_event_id": "event:first",
            "ledger_position": 1,
            "generation_schema": "atlas.blueprint-generation/1",
        },
        {
            "generation_id": "sha256:" + "b" * 64,
            "completion_event_id": "event:latest",
            "ledger_position": 3,
            "generation_schema": "atlas.blueprint-generation/5",
        },
    ]


def _bootstrap() -> None:
    bridge.lifecycle(
        action="cold-wake",
        receipt_id="cold:bridge-test",
        provider=PROVIDER,
        model=MODEL,
    )
    for seat_id, role in (
        ("codex-seat", "provider"),
        ("claude-seat", "provider"),
        ("ego-seat", "ego"),
        ("sensorium-seat", "sensorium"),
    ):
        bridge.seat_transition(
            seat_id=seat_id,
            role=role,
            action="found",
            charter_ref=f"charter:{role}",
            holder_ref=f"holder:{seat_id}:1",
            provider=PROVIDER,
            model=MODEL,
        )
    bridge.select_context(
        assumption="seat-fabric-is-one-conceptric",
        fibre="provider-exchange",
        provider=PROVIDER,
        model=MODEL,
        confidence=1.0,
    )


def _portable_grant_fixture(
    monkeypatch: pytest.MonkeyPatch,
    *,
    source: Path,
    destination: Path,
) -> str:
    receipt_raw = (source / "RECEIPT.json").read_bytes()
    receipt = json.loads(receipt_raw)
    receipt_sha256 = bridge.hash_bytes(receipt_raw)
    context = bridge.ConceptricStore.authority_context_evidence(
        destination, store_role="live-runtime-fabric"
    )
    coordinate_digest = "sha256:" + ("9" * 64)
    predecessor_root = "sha256:" + ("8" * 64)
    identity = {
        "schema_version": bridge.RUNTIME_ADOPTION_GRANT_SCHEMA,
        "source_snapshot_id": receipt["snapshot_id"],
        "source_receipt_sha256": receipt_sha256,
        "source_checkpoint_digest": receipt["source_checkpoint"]["checkpoint_digest"],
        "recovery_coordinate_payload_digest": coordinate_digest,
        "recovery_grant_anchor_root": "sha256:" + ("7" * 64),
        "destination_root": str(destination.resolve()),
        "destination_context_evidence_root": context["evidence_root"],
        "target_store_role": "live-runtime-fabric",
        "target_store_schema": bridge.CONCEPTRIC_DB_SCHEMA,
        "predecessor_adoption_root": predecessor_root,
    }
    grant_root = bridge.chash(identity)

    def committed_grant(**kwargs):
        expected = kwargs.get("expected_grant_root")
        if expected is not None and expected != grant_root:
            raise HistoryChainMismatch("portable adoption external grant root moved")
        return identity, coordinate_digest, {
            "point_root": "sha256:" + ("6" * 64),
            "predecessor_adoption_root": predecessor_root,
        }

    monkeypatch.setattr(bridge, "_committed_runtime_recovery_grant", committed_grant)
    return grant_root


def test_dependency_freshness_marks_a_git_ancestor_stale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old = "a" * 40
    live = "b" * 40
    monkeypatch.setattr(
        bridge,
        "_git_resolve_commit",
        lambda reference: live if reference == "HEAD" else (old if reference == old else None),
    )
    monkeypatch.setattr(bridge, "_git_is_ancestor", lambda left, right: (left, right) == (old, live))

    observed = bridge._dependency_freshness({"git_head": old, "contract": "opaque:v1"})

    assert observed["state"] == "REACHABLE-ANCESTOR"
    assert observed["roots"]["git_head"]["state"] == "STALE-ANCESTOR"
    assert observed["roots"]["git_head"]["live"] == live
    assert observed["roots"]["contract"]["state"] == "OPAQUE"


def test_send_stamps_dependency_freshness_and_status_recomputes_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bootstrap()
    calls = 0

    def observe(roots):
        nonlocal calls
        calls += 1
        state = "CURRENT" if calls == 1 else "STALE"
        return {
            "schema_version": "laplace.fabric-dependency-freshness/1",
            "observed_at": f"observation:{calls}",
            "state": state,
            "known_root_count": 1,
            "roots": {
                "git_head": {
                    "kind": "git-head",
                    "declared": roots["git_head"],
                    "live": "head:send" if calls == 1 else "head:later",
                    "state": state,
                }
            },
        }

    monkeypatch.setattr(bridge, "_dependency_freshness", observe)
    sent = bridge.send(
        sender_seat_id="codex-seat",
        recipient_seat_id="claude-seat",
        message_type="freshness-plant",
        body="bind one dependency",
        dependency_roots={"git_head": "head:send"},
        idempotency_key="freshness-plant:1",
        expires_at=EXPIRES,
        provider=PROVIDER,
        model=MODEL,
    )

    assert sent["dependency_freshness"]["send"]["state"] == "CURRENT"
    assert sent["dependency_freshness"]["current"]["state"] == "STALE"
    stored_roots = sent["status"]["message"]["dependency_roots"]
    assert bridge._DEPENDENCY_FRESHNESS_ROOT in stored_roots
    assert json.loads(stored_roots[bridge._DEPENDENCY_FRESHNESS_ROOT])["state"] == "CURRENT"

    current = bridge.status(message_id=sent["message_id"])["status"]
    assert current["dependency_freshness"]["send"]["state"] == "CURRENT"
    assert current["dependency_freshness"]["current"]["state"] == "STALE"


def test_caller_cannot_forge_dependency_freshness() -> None:
    _bootstrap()
    with pytest.raises(StateTransitionRefused, match="cannot be caller-authored"):
        bridge.send(
            sender_seat_id="codex-seat",
            recipient_seat_id="claude-seat",
            message_type="forged-freshness",
            body="forged observation",
            dependency_roots={bridge._DEPENDENCY_FRESHNESS_ROOT: "{}"},
            idempotency_key="forged-freshness:1",
            expires_at=EXPIRES,
            provider=PROVIDER,
            model=MODEL,
        )


def test_never_valid_coordinate_digest_is_unknown_not_superseded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import laplace.representation.recovery_coordinate as recovery

    monkeypatch.setattr(bridge, "_known_coordinate_payload_digests", lambda: {"sha256:known"})
    live_document = json.loads(recovery.DEFAULT_COORDINATE.read_text(encoding="utf-8"))
    live = recovery.canonical_payload_digest(live_document)
    forged = "sha256:" + ("0" * 64)
    assert forged != live

    observed = bridge._dependency_freshness({"coordinate_payload": forged})

    assert observed["roots"]["coordinate_payload"]["state"] == "UNKNOWN"
    assert observed["state"] == "PARTIAL"


def test_drift_token_is_a_read_only_compact_tip_not_a_replay_receipt() -> None:
    from atlas.store import ConceptricStore

    ConceptricStore(bridge.store_root())
    genesis = bridge.drift_token()
    assert genesis["cursor"] == 0
    assert genesis["head_event_id"] is None

    receipt = bridge.lifecycle(
        action="cold-wake",
        receipt_id="cold:drift-token-test",
        provider=PROVIDER,
        model=MODEL,
    )["receipt"]
    moved = bridge.drift_token()
    assert moved == {
        "schema_version": "atlas.conceptric-drift-token/1",
        "cursor": receipt["sequence"],
        "head_event_id": receipt["event_id"],
        "head_record_digest": receipt["record_digest"],
    }


def test_unverified_current_join_refuses_without_cutover_or_observational_occupancy() -> None:
    _bootstrap()
    proof = {
        "schema_version": "laplace.startup-mail-gate/1",
        "seat_id": "sensorium-seat",
        "goal": "reconstruct the conjugate interface coordinate",
        "state": "MAIL_READY",
        "observed_at": "2026-08-26T12:00:00+00:00",
        "delivered": [],
    }

    before = bridge.drift_token()
    with pytest.raises(StateTransitionRefused, match="join-and-binding packet"):
        bridge.seat_join(
            seat_id="sensorium-seat",
            holder_ref="codex:thread-interface",
            function="sensorium",
            information_proof=proof,
            provider=PROVIDER,
            model=MODEL,
        )

    assert bridge.drift_token() == before
    state = bridge._store().current_state()
    assert state.seat_lifecycle_cutover_event_id is None
    assert "sensorium-seat" not in state.seat_occupancies


def _verified_codex_identity(thread_id: str = "thread-interface") -> dict[str, object]:
    return {
        "schema_version": "laplace.provider-session-identity/1",
        "state": "VERIFIED",
        "provider_session_ref": f"codex:{thread_id}",
        "requested_holder_ref": None,
        "provider": "codex",
        "identity_kind": "codex-thread-watcher-binding",
        "watcher_seat_id": "sensorium-seat",
        "watcher_target_thread_id": thread_id,
        "watcher_lease_generation": f"lease:{thread_id}",
        "watcher_pid": 42,
        "reason": None,
    }


def _join_sensorium(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    identity = _verified_codex_identity()
    monkeypatch.setattr(
        bridge,
        "_live_provider_identity_attestation",
        lambda seat_id: identity if seat_id == "sensorium-seat" else {},
    )
    return bridge.seat_join(
        seat_id="sensorium-seat",
        holder_ref="codex:thread-interface",
        function="sensorium",
        information_proof={
            "schema_version": "laplace.startup-mail-gate/1",
            "seat_id": "sensorium-seat",
            "goal": "build the conjugate interface",
            "state": "MAIL_READY",
            "observed_at": "2026-08-26T12:00:00+00:00",
            "delivered": [],
            "provider_identity": identity,
        },
        provider=PROVIDER,
        model=MODEL,
    )


def _direct_renewal_packet(
    *,
    proof_handle: str,
    provider_identity_generation: str,
) -> tuple[object, object]:
    state = bridge._store().current_state()
    occupancy = state.seat_occupancies["sensorium-seat"]
    assert occupancy.binding is not None
    assert occupancy.binding_event_id is not None
    joined = replace(
        occupancy.join,
        information_proof_handle=proof_handle,
        information_cursor=state.event_count,
        provider_identity_generation=provider_identity_generation,
    )
    join_event = bridge._event(
        bridge.EventKind.SEAT_JOIN,
        joined.to_dict(),
        actor=bridge.SeatRole.SENSORIUM,
        subject="seat:sensorium-seat:occupancy",
        provider=PROVIDER,
        model=MODEL,
        correlation_id="direct-provider-proof-renewal",
        assumption=state.active_assumption,
        fibre=state.active_fibre,
        causation_ids=tuple(
            dict.fromkeys(
                event_id
                for event_id in (state.head_event_id, occupancy.binding_event_id)
                if event_id is not None
            )
        ),
        body_handle=proof_handle,
        note="direct provider proof renewal test packet",
    )
    binding = bridge.SeatOccupancyBinding(
        seat_id="sensorium-seat",
        registered_seat_event_id=state.seat_registration_event_ids["sensorium-seat"],
        join_event_id=join_event.event_id,
        registered_principal_ref=occupancy.binding.registered_principal_ref,
        provider_session_ref=occupancy.join.holder_ref,
        function=bridge.SeatRole.SENSORIUM,
        provider_identity_proof_handle=proof_handle,
        provider_identity_generation=provider_identity_generation,
        predecessor_binding_event_id=occupancy.binding_event_id,
        retired_provider_identity_generation=(
            occupancy.binding.provider_identity_generation
        ),
    )
    binding_event = bridge._event(
        bridge.EventKind.SEAT_OCCUPANCY_BINDING,
        binding.to_dict(),
        actor=bridge.SeatRole.SENSORIUM,
        subject="seat:sensorium-seat:binding",
        provider=PROVIDER,
        model=MODEL,
        correlation_id="direct-provider-proof-renewal-binding",
        assumption=state.active_assumption,
        fibre=state.active_fibre,
        causation_ids=(
            state.seat_registration_event_ids["sensorium-seat"],
            join_event.event_id,
            occupancy.binding_event_id,
        ),
        body_handle=proof_handle,
        note="direct provider proof renewal binding test packet",
    )
    return join_event, binding_event


def _inject_immutable_history(
    store: object,
    packet: tuple[object, ...],
    *,
    rebuild_projection: bool = True,
) -> None:
    """Plant an already-committed legacy prefix without passing it through a v2 writer.

    The lifecycle cutover must replay old bytes but must never mint them.  This helper models
    the former writer's completed append by inserting fully hashed rows and immutable hive
    chunks, then lets the current store rebuild only its disposable projection.
    """

    with store._connect() as connection:
        tip = connection.execute(
            "SELECT sequence, record_digest FROM events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        sequence = 0 if tip is None else int(tip["sequence"])
        previous = (
            "sha256:" + ("0" * 64)
            if tip is None
            else str(tip["record_digest"])
        )
        connection.execute("BEGIN IMMEDIATE")
        for historical_event in packet:
            sequence += 1
            stored = bridge.StoredEvent.create(sequence, previous, historical_event)
            handle = store.hive.put(
                bridge.canonical_json(historical_event.to_dict()).encode()
            )
            store._insert_event_v2(connection, stored, handle)
            previous = stored.record_digest
        connection.execute(
            "INSERT OR REPLACE INTO meta(key, value) "
            "VALUES ('authoritative_head_digest', ?)",
            (previous,),
        )
        connection.commit()
    bridge._store_at.cache_clear()
    bridge._read_store_at.cache_clear()
    if rebuild_projection:
        bridge.ConceptricStore(store.root)


def _legacy_v1_join_payload(joined: object) -> dict[str, object]:
    raw = joined.to_dict()
    raw["schema_version"] = bridge.SeatJoinReceipt.LEGACY_V1_SCHEMA_VERSION
    raw.pop("provider_identity_generation")
    return raw


def _legacy_v3_binding_payload(binding: object) -> dict[str, object]:
    raw = binding.to_dict()
    raw["schema_version"] = bridge.SeatOccupancyBinding.LEGACY_V3_SCHEMA_VERSION
    return raw


def test_legacy_v1_cross_holder_prefix_replays_full_and_bounded_but_cannot_be_minted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bootstrap()
    store = bridge._store()
    state = store.current_state()
    registration_event_id = state.seat_registration_event_ids["sensorium-seat"]

    def proof(thread_id: str, generation: str) -> tuple[dict[str, object], str]:
        identity = _verified_codex_identity(thread_id)
        identity["watcher_lease_generation"] = generation
        document = {
            "schema_version": "laplace.startup-mail-gate/1",
            "seat_id": "sensorium-seat",
            "goal": "replay the immutable v1 provider lifecycle prefix",
            "state": "MAIL_READY",
            "observed_at": "2026-08-27T12:00:00+00:00",
            "delivered": [],
            "provider_identity": identity,
        }
        handle = bridge._blobs().put(
            (bridge.canonical_json(document) + "\n").encode()
        )
        return document, handle

    _a_proof, a_handle = proof("legacy-a", "lease:legacy-a:1")
    a_join = bridge.SeatJoinReceipt(
        seat_id="sensorium-seat",
        holder_ref="codex:legacy-a",
        function=bridge.SeatRole.SENSORIUM,
        registered_role=bridge.SeatRole.SENSORIUM,
        registered_holder_ref="holder:sensorium-seat:1",
        mail_state="MAIL_READY",
        information_proof_handle=a_handle,
        information_cursor=state.event_count,
        delivered_message_ids=(),
        reconstruction_event_ids=(),
    )
    a_join_event = bridge._event(
        bridge.EventKind.SEAT_JOIN,
        _legacy_v1_join_payload(a_join),
        actor=bridge.SeatRole.SENSORIUM,
        subject="seat:sensorium-seat:occupancy",
        provider=PROVIDER,
        model=MODEL,
        correlation_id="historical-v1-a-join",
        assumption=state.active_assumption,
        fibre=state.active_fibre,
        causation_ids=(state.head_event_id,),
        body_handle=a_handle,
        note="historical v1 A join fixture",
    )
    a_binding = bridge.SeatOccupancyBinding(
        seat_id="sensorium-seat",
        registered_seat_event_id=registration_event_id,
        join_event_id=a_join_event.event_id,
        registered_principal_ref="holder:sensorium-seat:1",
        provider_session_ref="codex:legacy-a",
        function=bridge.SeatRole.SENSORIUM,
        provider_identity_proof_handle=a_handle,
    )
    a_binding_event = bridge._event(
        bridge.EventKind.SEAT_OCCUPANCY_BINDING,
        _legacy_v3_binding_payload(a_binding),
        actor=bridge.SeatRole.SENSORIUM,
        subject="seat:sensorium-seat:binding",
        provider=PROVIDER,
        model=MODEL,
        correlation_id="historical-v1-a-binding",
        assumption=state.active_assumption,
        fibre=state.active_fibre,
        causation_ids=(registration_event_id, a_join_event.event_id),
        body_handle=a_handle,
        note="historical v3 A binding fixture",
    )

    _b_proof, b_handle = proof("legacy-b", "lease:legacy-b:1")
    b_join = replace(
        a_join,
        holder_ref="codex:legacy-b",
        information_proof_handle=b_handle,
        information_cursor=state.event_count + 2,
    )
    b_join_event = bridge._event(
        bridge.EventKind.SEAT_JOIN,
        _legacy_v1_join_payload(b_join),
        actor=bridge.SeatRole.SENSORIUM,
        subject="seat:sensorium-seat:occupancy",
        provider=PROVIDER,
        model=MODEL,
        correlation_id="historical-v1-b-join",
        assumption=state.active_assumption,
        fibre=state.active_fibre,
        causation_ids=(a_binding_event.event_id,),
        body_handle=b_handle,
        note="historical v1 B join fixture",
    )
    b_binding = replace(
        a_binding,
        join_event_id=b_join_event.event_id,
        provider_session_ref="codex:legacy-b",
        provider_identity_proof_handle=b_handle,
    )
    b_binding_event = bridge._event(
        bridge.EventKind.SEAT_OCCUPANCY_BINDING,
        _legacy_v3_binding_payload(b_binding),
        actor=bridge.SeatRole.SENSORIUM,
        subject="seat:sensorium-seat:binding",
        provider=PROVIDER,
        model=MODEL,
        correlation_id="historical-v1-b-binding",
        assumption=state.active_assumption,
        fibre=state.active_fibre,
        causation_ids=(registration_event_id, b_join_event.event_id),
        body_handle=b_handle,
        note="historical v3 B binding fixture",
    )
    _inject_immutable_history(
        store,
        (a_join_event, a_binding_event, b_join_event, b_binding_event),
    )

    cold = bridge.ConceptricStore(store.root)
    replayed = cold.replay()
    occupancy = replayed.seat_occupancies["sensorium-seat"]
    assert occupancy.join.holder_ref == "codex:legacy-b"
    assert occupancy.routing_authority is True
    assert occupancy.retired_binding_event_ids == ()
    assert replayed.seat_lifecycle_cutover_event_id is None
    assert bridge.provider_seat_binding(
        provider_session_ref="codex:legacy-a"
    )["status"] == "UNBOUND"
    assert bridge.provider_seat_binding(
        provider_session_ref="codex:legacy-b"
    )["status"] == "BOUND"

    event_count = replayed.event_count
    assert cold.append(a_join_event).event.event_id == a_join_event.event_id
    assert cold.current_state().event_count == event_count

    new_legacy_join = bridge._event(
        bridge.EventKind.SEAT_JOIN,
        _legacy_v1_join_payload(
            replace(
                b_join,
                holder_ref="codex:forged-legacy-c",
                information_cursor=event_count,
            )
        ),
        actor=bridge.SeatRole.SENSORIUM,
        subject="seat:sensorium-seat:occupancy",
        provider=PROVIDER,
        model=MODEL,
        correlation_id="forged-new-v1-join",
        assumption=state.active_assumption,
        fibre=state.active_fibre,
        causation_ids=(b_binding_event.event_id,),
        body_handle=b_handle,
        note="forged new legacy join fixture",
    )
    with pytest.raises(StateTransitionRefused, match="new legacy seat joins"):
        cold.append(new_legacy_join)

    new_legacy_binding = bridge._event(
        bridge.EventKind.SEAT_OCCUPANCY_BINDING,
        _legacy_v3_binding_payload(b_binding),
        actor=bridge.SeatRole.SENSORIUM,
        subject="seat:sensorium-seat:binding",
        provider=PROVIDER,
        model=MODEL,
        correlation_id="forged-new-v3-binding",
        assumption=state.active_assumption,
        fibre=state.active_fibre,
        causation_ids=(registration_event_id, b_join_event.event_id),
        body_handle=b_handle,
        note="forged new legacy binding fixture",
    )
    with pytest.raises(StateTransitionRefused, match="new legacy seat bindings"):
        cold.append(new_legacy_binding)
    assert cold.current_state().event_count == event_count

    successor_identity = _verified_codex_identity("current-c")
    successor_identity["watcher_lease_generation"] = "lease:current-c:1"
    monkeypatch.setattr(
        bridge,
        "_live_provider_identity_attestation",
        lambda seat_id: (
            dict(successor_identity) if seat_id == "sensorium-seat" else {}
        ),
    )
    current_handover = bridge.seat_join(
        seat_id="sensorium-seat",
        holder_ref="codex:current-c",
        function="sensorium",
        information_proof={
            "schema_version": "laplace.startup-mail-gate/1",
            "seat_id": "sensorium-seat",
            "goal": "cross the v1 to v2 lifecycle cutover",
            "state": "MAIL_READY",
            "observed_at": "2026-08-27T12:30:00+00:00",
            "delivered": [],
            "provider_identity": successor_identity,
        },
        provider=PROVIDER,
        model=MODEL,
    )
    current_state = bridge._store().replay()
    assert current_handover["holder_replaced"] is True
    assert current_handover["predecessor_binding_event_id"] == b_binding_event.event_id
    assert current_handover["retired_provider_identity_generation"] == (
        "lease:legacy-b:1"
    )
    assert current_state.seat_lifecycle_cutover_event_id == (
        current_handover["receipt"]["event_id"]
    )
    assert bridge.provider_seat_binding(
        provider_session_ref="codex:legacy-b"
    )["status"] == "UNBOUND"
    assert bridge.provider_seat_binding(
        provider_session_ref="codex:current-c"
    )["status"] == "BOUND"

    # A copied or older writer cannot hide a legacy suffix behind a valid v2 handover.  Plant
    # the immutable bytes as though such a writer had raced the cutover; both the full fold and
    # the recipient-bounded routing fold must reject the non-monotone chain.
    poisoned_store = bridge._store()
    _inject_immutable_history(
        poisoned_store,
        (new_legacy_join,),
        rebuild_projection=False,
    )
    with pytest.raises(
        StateTransitionRefused,
        match="legacy seat join appears after the lifecycle cutover",
    ):
        poisoned_store.replay()
    with poisoned_store._connect() as ledger:
        with pytest.raises(
            HistoryChainMismatch,
            match="legacy join after cutover",
        ):
            bridge.ConceptricStore._authoritative_provider_seat_bindings(
                poisoned_store.root,
                ledger,
                provider_session_ref="codex:current-c",
            )


def test_current_handover_join_cannot_commit_without_its_matching_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bootstrap()
    _join_sensorium(monkeypatch)
    identity = _verified_codex_identity()
    identity["watcher_lease_generation"] = "lease:thread-interface:2"
    proof = {
        "schema_version": "laplace.startup-mail-gate/1",
        "seat_id": "sensorium-seat",
        "goal": "prove current handover packet closure",
        "state": "MAIL_READY",
        "observed_at": "2026-08-27T12:00:00+00:00",
        "delivered": [],
        "provider_identity": identity,
    }
    proof_handle = bridge._blobs().put(
        (bridge.canonical_json(proof) + "\n").encode()
    )
    join_event, binding_event = _direct_renewal_packet(
        proof_handle=proof_handle,
        provider_identity_generation="lease:thread-interface:2",
    )
    store = bridge._store()
    before = store.current_state()

    with pytest.raises(
        StateTransitionRefused,
        match="join-and-binding packet",
    ):
        store.append(join_event)
    assert store.current_state() == before

    stored = store.append_many((join_event, binding_event))
    assert [row.event.event_id for row in stored] == [
        join_event.event_id,
        binding_event.event_id,
    ]
    assert store.current_state().seat_occupancies["sensorium-seat"].routing_authority


def test_first_current_cutover_join_cannot_commit_without_its_matching_binding() -> None:
    _bootstrap()
    store = bridge._store()
    state = store.current_state()
    assert state.seat_lifecycle_cutover_event_id is None
    assert "ego-seat" not in state.seat_occupancies

    identity = _verified_codex_identity("first-ego")
    identity["provider_session_ref"] = "codex:first-ego"
    identity["watcher_seat_id"] = "ego-seat"
    identity["watcher_lease_generation"] = "lease:first-ego:1"
    proof = {
        "schema_version": "laplace.startup-mail-gate/1",
        "seat_id": "ego-seat",
        "goal": "prove the first v2 cutover is one closed lifecycle packet",
        "state": "MAIL_READY",
        "observed_at": "2026-08-27T12:00:00+00:00",
        "delivered": [],
        "provider_identity": identity,
    }
    proof_handle = bridge._blobs().put(
        (bridge.canonical_json(proof) + "\n").encode()
    )
    joined = bridge.SeatJoinReceipt(
        seat_id="ego-seat",
        holder_ref="codex:first-ego",
        function=bridge.SeatRole.EGO,
        registered_role=bridge.SeatRole.EGO,
        registered_holder_ref="holder:ego-seat:1",
        mail_state="MAIL_READY",
        information_proof_handle=proof_handle,
        information_cursor=state.event_count,
        delivered_message_ids=(),
        reconstruction_event_ids=(),
        provider_identity_generation="lease:first-ego:1",
    )
    join_event = bridge._event(
        bridge.EventKind.SEAT_JOIN,
        joined.to_dict(),
        actor=bridge.SeatRole.EGO,
        subject="seat:ego-seat:occupancy",
        provider=PROVIDER,
        model=MODEL,
        correlation_id="first-v2-cutover-join",
        assumption=state.active_assumption,
        fibre=state.active_fibre,
        causation_ids=(state.head_event_id,),
        body_handle=proof_handle,
        note="first current lifecycle join",
    )
    binding = bridge.SeatOccupancyBinding(
        registered_seat_event_id=state.seat_registration_event_ids["ego-seat"],
        join_event_id=join_event.event_id,
        registered_principal_ref="holder:ego-seat:1",
        provider_session_ref="codex:first-ego",
        provider_identity_proof_handle=proof_handle,
        seat_id="ego-seat",
        function=bridge.SeatRole.EGO,
        provider_identity_generation="lease:first-ego:1",
    )
    binding_event = bridge._event(
        bridge.EventKind.SEAT_OCCUPANCY_BINDING,
        binding.to_dict(),
        actor=bridge.SeatRole.EGO,
        subject="seat:ego-seat:binding",
        provider=PROVIDER,
        model=MODEL,
        correlation_id="first-v2-cutover-binding",
        assumption=state.active_assumption,
        fibre=state.active_fibre,
        causation_ids=(
            state.seat_registration_event_ids["ego-seat"],
            join_event.event_id,
        ),
        body_handle=proof_handle,
        note="first current lifecycle binding",
    )

    before = bridge.drift_token()
    with pytest.raises(
        StateTransitionRefused,
        match="join-and-binding packet",
    ):
        store.append(join_event)
    assert bridge.drift_token() == before
    refused = store.current_state()
    assert refused.seat_lifecycle_cutover_event_id is None
    assert "ego-seat" not in refused.seat_occupancies

    stored = store.append_many((join_event, binding_event))
    assert [row.event.event_id for row in stored] == [
        join_event.event_id,
        binding_event.event_id,
    ]
    accepted = store.current_state()
    assert accepted.seat_lifecycle_cutover_event_id == join_event.event_id
    assert accepted.seat_occupancies["ego-seat"].routing_authority


def test_same_holder_watcher_generation_renews_exact_binding_and_replays_cold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bootstrap()
    first_identity = _verified_codex_identity()
    first_identity["watcher_lease_generation"] = "lease:thread-interface:1"
    live_identity = dict(first_identity)
    monkeypatch.setattr(
        bridge,
        "_live_provider_identity_attestation",
        lambda seat_id: dict(live_identity) if seat_id == "sensorium-seat" else {},
    )

    def join(identity: dict[str, object]) -> dict[str, object]:
        return bridge.seat_join(
            seat_id="sensorium-seat",
            holder_ref="codex:thread-interface",
            function="sensorium",
            information_proof={
                "schema_version": "laplace.startup-mail-gate/1",
                "seat_id": "sensorium-seat",
                "goal": "renew the current watcher generation",
                "state": "MAIL_READY",
                "observed_at": "2026-08-27T12:00:00+00:00",
                "delivered": [],
                "provider_identity": identity,
            },
            provider=PROVIDER,
            model=MODEL,
        )

    first = join(first_identity)
    first_binding_event_id = first["binding_receipt"]["event_id"]
    before = bridge.snapshot()["provider"]
    logical_principal = before["seats"]["sensorium-seat"]["holder_ref"]
    queued = bridge.send(
        sender_seat_id="codex-seat",
        recipient_seat_id="sensorium-seat",
        message_type="mail-frontier-plant",
        body="must survive binding renewal unchanged",
        dependency_roots={"plant": "same-holder-renewal"},
        idempotency_key="same-holder-renewal:mail-frontier",
        expires_at=EXPIRES,
        provider=PROVIDER,
        model=MODEL,
    )
    before_mail = bridge.status(message_id=queued["message_id"])["status"]

    second_identity = dict(first_identity)
    second_identity["watcher_lease_generation"] = "lease:thread-interface:2"
    live_identity.clear()
    live_identity.update(second_identity)
    renewed = join(second_identity)

    assert renewed["renewed"] is True
    assert renewed["predecessor_binding_event_id"] == first_binding_event_id
    assert renewed["retired_provider_identity_generation"] == (
        "lease:thread-interface:1"
    )
    assert renewed["provider_identity_generation"] == "lease:thread-interface:2"
    assert renewed["occupancy"]["routing_authority"] is True
    assert renewed["occupancy"]["retired_binding_event_ids"] == [
        first_binding_event_id
    ]
    assert renewed["occupancy"]["current_provider_identity_generation"] == (
        "lease:thread-interface:2"
    )

    events = {event.event_id: event for event in bridge._store().events()}
    successor_join = events[renewed["receipt"]["event_id"]]
    successor_binding = events[renewed["binding_receipt"]["event_id"]]
    assert successor_join.payload["provider_identity_generation"] == (
        "lease:thread-interface:2"
    )
    assert first_binding_event_id in successor_join.causation_ids
    assert {
        first_binding_event_id,
        successor_join.event_id,
    }.issubset(successor_binding.causation_ids)

    after_mail = bridge.status(message_id=queued["message_id"])["status"]
    assert after_mail["status"] == before_mail["status"] == "queued"
    assert after_mail["message"] == before_mail["message"]
    assert after_mail["acknowledgement_event_id"] is None
    after = bridge.snapshot()["provider"]
    assert after["seats"]["sensorium-seat"]["holder_ref"] == logical_principal
    lineage = after["seat_binding_lineage"]["sensorium-seat"]
    assert lineage["current_binding_event_id"] == renewed["binding_receipt"]["event_id"]
    assert lineage["retired_predecessors"] == [
        {
            "binding_event_id": first_binding_event_id,
            "provider_identity_generation": "lease:thread-interface:1",
        }
    ]
    bounded = bridge.provider_seat_binding(
        provider_session_ref="codex:thread-interface"
    )
    assert bounded["status"] == "BOUND"
    assert bounded["occupancy"] == renewed["occupancy"]

    event_count = after["event_count"]
    repeated = join(second_identity)
    assert repeated["idempotent"] is True
    assert repeated["provider_identity_generation"] == "lease:thread-interface:2"
    assert bridge.snapshot()["provider"]["event_count"] == event_count

    replayed = bridge._store().replay().provider_snapshot()
    assert replayed["seat_occupancy"]["sensorium-seat"] == renewed["occupancy"]
    assert replayed["seat_binding_lineage"]["sensorium-seat"] == lineage
    assert replayed["messages"][queued["message_id"]]["status"] == "queued"


def test_generation_renewal_is_atomic_across_the_join_binding_crash_seam(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bootstrap()
    first_identity = _verified_codex_identity()
    first_identity["watcher_lease_generation"] = "lease:thread-interface:1"
    live_identity = dict(first_identity)
    monkeypatch.setattr(
        bridge,
        "_live_provider_identity_attestation",
        lambda seat_id: dict(live_identity) if seat_id == "sensorium-seat" else {},
    )

    def join(identity: dict[str, object]) -> dict[str, object]:
        return bridge.seat_join(
            seat_id="sensorium-seat",
            holder_ref="codex:thread-interface",
            function="sensorium",
            information_proof={
                "schema_version": "laplace.startup-mail-gate/1",
                "seat_id": "sensorium-seat",
                "goal": "prove atomic watcher generation renewal",
                "state": "MAIL_READY",
                "observed_at": "2026-08-27T12:00:00+00:00",
                "delivered": [],
                "provider_identity": identity,
            },
            provider=PROVIDER,
            model=MODEL,
        )

    first = join(first_identity)
    first_binding_event_id = first["binding_receipt"]["event_id"]
    before = bridge.snapshot()["provider"]
    store = bridge._store()
    original_insert = store._insert_event_v2

    def fail_before_binding_insert(connection, stored, event_handle):
        if stored.event.kind == bridge.EventKind.SEAT_OCCUPANCY_BINDING:
            raise RuntimeError("planted crash between renewal join and binding")
        original_insert(connection, stored, event_handle)

    monkeypatch.setattr(
        type(store),
        "_insert_event_v2",
        staticmethod(fail_before_binding_insert),
    )
    second_identity = dict(first_identity)
    second_identity["watcher_lease_generation"] = "lease:thread-interface:2"
    live_identity.clear()
    live_identity.update(second_identity)

    with pytest.raises(RuntimeError, match="planted crash"):
        join(second_identity)

    after_crash = bridge.snapshot()["provider"]
    assert after_crash["event_count"] == before["event_count"]
    assert after_crash["seat_occupancy"]["sensorium-seat"] == (
        before["seat_occupancy"]["sensorium-seat"]
    )
    assert after_crash["seat_binding_lineage"]["sensorium-seat"] == {
        "current_binding_event_id": first_binding_event_id,
        "current_provider_identity_generation": "lease:thread-interface:1",
        "retired_predecessors": [],
    }

    monkeypatch.setattr(
        type(store),
        "_insert_event_v2",
        staticmethod(original_insert),
    )
    successor = join(second_identity)
    assert successor["renewed"] is True
    assert successor["predecessor_binding_event_id"] == first_binding_event_id
    assert successor["occupancy"]["retired_binding_event_ids"] == [
        first_binding_event_id
    ]
    assert bridge._store().replay().provider_snapshot()["seat_binding_lineage"][
        "sensorium-seat"
    ]["retired_predecessors"] == [
        {
            "binding_event_id": first_binding_event_id,
            "provider_identity_generation": "lease:thread-interface:1",
        }
    ]


def test_cross_holder_handover_insert_fault_leaves_predecessor_authoritative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bootstrap()
    first_identity = _verified_codex_identity("thread-a")
    first_identity["watcher_lease_generation"] = "lease:thread-a:1"
    live_identity = dict(first_identity)
    monkeypatch.setattr(
        bridge,
        "_live_provider_identity_attestation",
        lambda seat_id: dict(live_identity) if seat_id == "sensorium-seat" else {},
    )

    def join(identity: dict[str, object]) -> dict[str, object]:
        return bridge.seat_join(
            seat_id="sensorium-seat",
            holder_ref=str(identity["provider_session_ref"]),
            function="sensorium",
            information_proof={
                "schema_version": "laplace.startup-mail-gate/1",
                "seat_id": "sensorium-seat",
                "goal": "prove cross-holder handover transaction closure",
                "state": "MAIL_READY",
                "observed_at": "2026-08-27T12:00:00+00:00",
                "delivered": [],
                "provider_identity": identity,
            },
            provider=PROVIDER,
            model=MODEL,
        )

    first = join(first_identity)
    before = bridge.snapshot()["provider"]
    before_tip = bridge.drift_token()
    store = bridge._store()
    original_insert = store._insert_event_v2

    def fail_before_successor_binding(connection, stored, event_handle):
        if stored.event.kind == bridge.EventKind.SEAT_OCCUPANCY_BINDING:
            raise RuntimeError("planted crash between cross-holder join and binding")
        original_insert(connection, stored, event_handle)

    monkeypatch.setattr(
        type(store),
        "_insert_event_v2",
        staticmethod(fail_before_successor_binding),
    )
    successor_identity = _verified_codex_identity("thread-b")
    successor_identity["watcher_lease_generation"] = "lease:thread-b:1"
    live_identity.clear()
    live_identity.update(successor_identity)

    with pytest.raises(RuntimeError, match="cross-holder join and binding"):
        join(successor_identity)

    after_crash = bridge.snapshot()["provider"]
    assert bridge.drift_token() == before_tip
    assert after_crash["event_count"] == before["event_count"]
    assert after_crash["seat_occupancy"]["sensorium-seat"] == (
        before["seat_occupancy"]["sensorium-seat"]
    )
    assert bridge.provider_seat_binding(
        provider_session_ref="codex:thread-a"
    )["status"] == "BOUND"
    assert bridge.provider_seat_binding(
        provider_session_ref="codex:thread-b"
    )["status"] == "UNBOUND"

    monkeypatch.setattr(
        type(store),
        "_insert_event_v2",
        staticmethod(original_insert),
    )
    successor = join(successor_identity)
    assert successor["holder_replaced"] is True
    assert successor["predecessor_binding_event_id"] == first["binding_receipt"][
        "event_id"
    ]
    assert bridge.provider_seat_binding(
        provider_session_ref="codex:thread-a"
    )["status"] == "UNBOUND"
    assert bridge.provider_seat_binding(
        provider_session_ref="codex:thread-b"
    )["status"] == "BOUND"


def test_verified_identity_can_bind_after_unverified_observation_refuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bootstrap()
    observational_proof = {
        "schema_version": "laplace.startup-mail-gate/1",
        "seat_id": "sensorium-seat",
        "goal": "observe before the watcher is authenticated",
        "state": "MAIL_READY",
        "observed_at": "2026-08-27T12:00:00+00:00",
        "delivered": [],
    }
    before = bridge.drift_token()
    with pytest.raises(StateTransitionRefused, match="join-and-binding packet"):
        bridge.seat_join(
            seat_id="sensorium-seat",
            holder_ref="codex:thread-interface",
            function="sensorium",
            information_proof=observational_proof,
            provider=PROVIDER,
            model=MODEL,
        )
    assert bridge.drift_token() == before
    assert "sensorium-seat" not in bridge._store().current_state().seat_occupancies

    identity = _verified_codex_identity()
    identity["watcher_lease_generation"] = "lease:thread-interface:1"
    monkeypatch.setattr(
        bridge,
        "_live_provider_identity_attestation",
        lambda seat_id: identity if seat_id == "sensorium-seat" else {},
    )
    acquired = bridge.seat_join(
        seat_id="sensorium-seat",
        holder_ref="codex:thread-interface",
        function="sensorium",
        information_proof={
            **observational_proof,
            "goal": "bind the now-authenticated watcher",
            "provider_identity": identity,
        },
        provider=PROVIDER,
        model=MODEL,
    )

    assert acquired["renewed"] is False
    assert acquired["predecessor_binding_event_id"] is None
    assert acquired["retired_provider_identity_generation"] is None
    assert acquired["occupancy"]["state"] == "BOUND"
    assert acquired["occupancy"]["routing_authority"] is True
    assert acquired["occupancy"]["retired_binding_event_ids"] == []
    assert bridge._store().replay().provider_snapshot()["seat_binding_lineage"][
        "sensorium-seat"
    ]["retired_predecessors"] == []


def test_same_holder_generation_renewal_refuses_matching_retired_generation_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bootstrap()
    first_identity = _verified_codex_identity()
    first_identity["watcher_lease_generation"] = "lease:thread-interface:1"
    live_identity = dict(first_identity)
    monkeypatch.setattr(
        bridge,
        "_live_provider_identity_attestation",
        lambda seat_id: dict(live_identity) if seat_id == "sensorium-seat" else {},
    )

    def join(identity: dict[str, object]) -> dict[str, object]:
        return bridge.seat_join(
            seat_id="sensorium-seat",
            holder_ref="codex:thread-interface",
            function="sensorium",
            information_proof={
                "schema_version": "laplace.startup-mail-gate/1",
                "seat_id": "sensorium-seat",
                "goal": "refuse replay of a retired watcher generation",
                "state": "MAIL_READY",
                "observed_at": "2026-08-27T12:00:00+00:00",
                "delivered": [],
                "provider_identity": identity,
            },
            provider=PROVIDER,
            model=MODEL,
        )

    first = join(first_identity)
    first_binding_event_id = first["binding_receipt"]["event_id"]
    second_identity = dict(first_identity)
    second_identity["watcher_lease_generation"] = "lease:thread-interface:2"
    live_identity.clear()
    live_identity.update(second_identity)
    second = join(second_identity)
    second_binding_event_id = second["binding_receipt"]["event_id"]
    before = bridge.snapshot()["provider"]

    live_identity.clear()
    live_identity.update(first_identity)
    with pytest.raises(
        StateTransitionRefused,
        match="retired watcher identity generation",
    ):
        join(first_identity)

    after = bridge.snapshot()["provider"]
    assert after["event_count"] == before["event_count"]
    assert after["seat_occupancy"]["sensorium-seat"] == (
        before["seat_occupancy"]["sensorium-seat"]
    )
    assert after["seat_binding_lineage"]["sensorium-seat"] == {
        "current_binding_event_id": second_binding_event_id,
        "current_provider_identity_generation": "lease:thread-interface:2",
        "retired_predecessors": [
            {
                "binding_event_id": first_binding_event_id,
                "provider_identity_generation": "lease:thread-interface:1",
            }
        ],
    }
    replayed = bridge._store().replay().provider_snapshot()
    assert replayed["seat_occupancy"]["sensorium-seat"] == (
        before["seat_occupancy"]["sensorium-seat"]
    )
    assert replayed["seat_binding_lineage"]["sensorium-seat"] == (
        after["seat_binding_lineage"]["sensorium-seat"]
    )


def test_typed_a1_a2_b1_handover_retires_lineage_and_refuses_generation_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bootstrap()
    live_identity: dict[str, object] = {}
    monkeypatch.setattr(
        bridge,
        "_live_provider_identity_attestation",
        lambda seat_id: dict(live_identity) if seat_id == "sensorium-seat" else {},
    )

    def join(thread_id: str, generation: str) -> dict[str, object]:
        identity = _verified_codex_identity(thread_id)
        identity["watcher_lease_generation"] = generation
        live_identity.clear()
        live_identity.update(identity)
        return bridge.seat_join(
            seat_id="sensorium-seat",
            holder_ref=f"codex:{thread_id}",
            function="sensorium",
            information_proof={
                "schema_version": "laplace.startup-mail-gate/1",
                "seat_id": "sensorium-seat",
                "goal": "perform one typed provider-holder handover",
                "state": "MAIL_READY",
                "observed_at": "2026-08-27T12:00:00+00:00",
                "delivered": [],
                "provider_identity": identity,
            },
            provider=PROVIDER,
            model=MODEL,
        )

    first = join("thread-a", "lease:thread-a:1")
    second = join("thread-a", "lease:thread-a:2")
    third = join("thread-b", "lease:thread-b:1")
    after = bridge.snapshot()["provider"]

    assert third["renewed"] is True
    assert third["holder_replaced"] is True
    assert third["predecessor_binding_event_id"] == second["binding_receipt"][
        "event_id"
    ]
    assert third["retired_provider_identity_generation"] == "lease:thread-a:2"
    assert third["occupancy"]["join"]["holder_ref"] == "codex:thread-b"
    assert third["occupancy"]["retired_binding_event_ids"] == [
        first["binding_receipt"]["event_id"],
        second["binding_receipt"]["event_id"],
    ]
    assert bridge.provider_seat_binding(
        provider_session_ref="codex:thread-a"
    )["status"] == "UNBOUND"
    assert bridge.provider_seat_binding(
        provider_session_ref="codex:thread-b"
    )["status"] == "BOUND"

    for retired_generation in ("lease:thread-a:1", "lease:thread-a:2"):
        with pytest.raises(
            StateTransitionRefused,
            match="retired watcher identity generation",
        ):
            join("thread-a", retired_generation)

    repeated = join("thread-b", "lease:thread-b:1")
    assert repeated["idempotent"] is True
    assert bridge.snapshot()["provider"]["event_count"] == after["event_count"]
    replayed = bridge._store().replay().provider_snapshot()
    assert replayed["seat_occupancy"]["sensorium-seat"] == (
        after["seat_occupancy"]["sensorium-seat"]
    )
    assert replayed["seat_occupancy"]["sensorium-seat"]["binding_event_id"] == (
        third["binding_receipt"]["event_id"]
    )

    state = bridge._store().current_state()
    occupancy = state.seat_occupancies["sensorium-seat"]
    assert occupancy.binding is not None
    assert occupancy.binding_event_id is not None
    replay_join = replace(
        occupancy.join,
        holder_ref="codex:thread-a",
        information_proof_handle=first["information_proof_handle"],
        information_cursor=state.event_count,
        provider_identity_generation="lease:thread-a:1",
    )
    replay_join_event = bridge._event(
        bridge.EventKind.SEAT_JOIN,
        replay_join.to_dict(),
        actor=bridge.SeatRole.SENSORIUM,
        subject="seat:sensorium-seat:occupancy",
        provider=PROVIDER,
        model=MODEL,
        correlation_id="poisoned-retired-generation-join",
        assumption=state.active_assumption,
        fibre=state.active_fibre,
        causation_ids=(occupancy.binding_event_id,),
        body_handle=first["information_proof_handle"],
        note="adversarial retired generation replay join",
    )
    replay_binding = bridge.SeatOccupancyBinding(
        seat_id="sensorium-seat",
        registered_seat_event_id=state.seat_registration_event_ids["sensorium-seat"],
        join_event_id=replay_join_event.event_id,
        registered_principal_ref=occupancy.binding.registered_principal_ref,
        provider_session_ref="codex:thread-a",
        function=bridge.SeatRole.SENSORIUM,
        provider_identity_proof_handle=first["information_proof_handle"],
        provider_identity_generation="lease:thread-a:1",
        predecessor_binding_event_id=occupancy.binding_event_id,
        retired_provider_identity_generation="lease:thread-b:1",
    )
    replay_binding_event = bridge._event(
        bridge.EventKind.SEAT_OCCUPANCY_BINDING,
        replay_binding.to_dict(),
        actor=bridge.SeatRole.SENSORIUM,
        subject="seat:sensorium-seat:binding",
        provider=PROVIDER,
        model=MODEL,
        correlation_id="poisoned-retired-generation-binding",
        assumption=state.active_assumption,
        fibre=state.active_fibre,
        causation_ids=(
            state.seat_registration_event_ids["sensorium-seat"],
            replay_join_event.event_id,
            occupancy.binding_event_id,
        ),
        body_handle=first["information_proof_handle"],
        note="adversarial retired generation replay binding",
    )
    poisoned_store = bridge._store()
    _inject_immutable_history(
        poisoned_store,
        (replay_join_event, replay_binding_event),
        rebuild_projection=False,
    )
    with pytest.raises(
        StateTransitionRefused,
        match="retired watcher identity generation",
    ):
        poisoned_store.replay()
    with poisoned_store._connect() as ledger:
        with pytest.raises(
            HistoryChainMismatch,
            match="replays a retired watcher generation",
        ):
            bridge.ConceptricStore._authoritative_provider_seat_bindings(
                poisoned_store.root,
                ledger,
                provider_session_ref="codex:thread-a",
            )


def test_direct_packet_cannot_relabel_a_retired_proof_as_a_fresh_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bootstrap()
    first_identity = _verified_codex_identity()
    first_identity["watcher_lease_generation"] = "lease:thread-interface:1"
    live_identity = dict(first_identity)
    monkeypatch.setattr(
        bridge,
        "_live_provider_identity_attestation",
        lambda seat_id: dict(live_identity) if seat_id == "sensorium-seat" else {},
    )

    def join(identity: dict[str, object]) -> dict[str, object]:
        return bridge.seat_join(
            seat_id="sensorium-seat",
            holder_ref="codex:thread-interface",
            function="sensorium",
            information_proof={
                "schema_version": "laplace.startup-mail-gate/1",
                "seat_id": "sensorium-seat",
                "goal": "bind provider generation to its exact proof body",
                "state": "MAIL_READY",
                "observed_at": "2026-08-27T12:00:00+00:00",
                "delivered": [],
                "provider_identity": identity,
            },
            provider=PROVIDER,
            model=MODEL,
        )

    first = join(first_identity)
    second_identity = dict(first_identity)
    second_identity["watcher_lease_generation"] = "lease:thread-interface:2"
    live_identity.clear()
    live_identity.update(second_identity)
    join(second_identity)
    before = bridge.snapshot()["provider"]
    packet = _direct_renewal_packet(
        proof_handle=first["information_proof_handle"],
        provider_identity_generation="lease:thread-interface:3",
    )

    with pytest.raises(
        StateTransitionRefused,
        match="provider identity proof contradicts the typed join",
    ):
        bridge._store().append_many(packet)

    after = bridge.snapshot()["provider"]
    assert after["event_count"] == before["event_count"]
    assert after["seat_occupancy"]["sensorium-seat"] == (
        before["seat_occupancy"]["sensorium-seat"]
    )
    assert bridge._store().replay().provider_snapshot()["seat_occupancy"][
        "sensorium-seat"
    ] == before["seat_occupancy"]["sensorium-seat"]


@pytest.mark.parametrize(
    ("attack", "error"),
    (
        ("missing", "unavailable or corrupt"),
        ("corrupt", "unavailable or corrupt"),
        ("wrong-seat", "information proof contradicts the typed join"),
        ("wrong-holder", "provider identity proof contradicts the typed join"),
        ("wrong-target", "provider identity proof contradicts the typed join"),
        ("observational", "provider identity proof contradicts the typed join"),
    ),
)
def test_canonical_store_refuses_unbound_provider_identity_proof_bodies(
    monkeypatch: pytest.MonkeyPatch,
    attack: str,
    error: str,
) -> None:
    _bootstrap()
    first_identity = _verified_codex_identity()
    first_identity["watcher_lease_generation"] = "lease:thread-interface:1"
    monkeypatch.setattr(
        bridge,
        "_live_provider_identity_attestation",
        lambda seat_id: dict(first_identity) if seat_id == "sensorium-seat" else {},
    )
    _join_sensorium(monkeypatch)
    successor_identity = dict(first_identity)
    successor_identity["watcher_lease_generation"] = "lease:thread-interface:2"
    proof = {
        "schema_version": "laplace.startup-mail-gate/1",
        "seat_id": "sensorium-seat",
        "goal": "reject an unbound provider identity proof body",
        "state": "MAIL_READY",
        "observed_at": "2026-08-27T12:00:00+00:00",
        "delivered": [],
        "provider_identity": successor_identity,
    }
    if attack == "wrong-seat":
        proof["seat_id"] = "superego-seat"
    elif attack == "wrong-holder":
        successor_identity["provider_session_ref"] = "codex:other-thread"
    elif attack == "wrong-target":
        successor_identity["watcher_target_thread_id"] = "other-thread"
    elif attack == "observational":
        successor_identity["state"] = "OBSERVATIONAL"

    if attack == "missing":
        proof_handle = "sha256:" + ("f" * 64)
    else:
        proof_handle = bridge._blobs().put(
            (bridge.canonical_json(proof) + "\n").encode("utf-8")
        )
        if attack == "corrupt":
            bridge._blobs().key_path(proof_handle).write_bytes(b"corrupt")
    before = bridge.snapshot()["provider"]
    packet = _direct_renewal_packet(
        proof_handle=proof_handle,
        provider_identity_generation="lease:thread-interface:2",
    )

    with pytest.raises(StateTransitionRefused, match=error):
        bridge._store().append_many(packet)

    after = bridge.snapshot()["provider"]
    assert after["event_count"] == before["event_count"]
    assert after["seat_occupancy"]["sensorium-seat"] == (
        before["seat_occupancy"]["sensorium-seat"]
    )
    assert bridge._store().replay().provider_snapshot()["seat_occupancy"][
        "sensorium-seat"
    ] == before["seat_occupancy"]["sensorium-seat"]


@pytest.mark.parametrize(
    ("attack", "error"),
    (
        ("observational", "live VERIFIED current watcher identity"),
        ("holder-mismatch", "live VERIFIED current watcher identity"),
        ("function-mismatch", "cannot change function"),
        ("seat-mismatch", "live VERIFIED current watcher identity"),
        ("stale-generation", "live VERIFIED current watcher identity"),
        ("absent-watcher", "live VERIFIED current watcher identity"),
        ("copied-proof", "live VERIFIED current watcher identity"),
        ("cross-task-replay", "live VERIFIED current watcher identity"),
        ("persistent-unverified", "live VERIFIED current watcher identity"),
    ),
)
def test_same_holder_generation_renewal_refuses_hostile_identity_plants(
    monkeypatch: pytest.MonkeyPatch,
    attack: str,
    error: str,
) -> None:
    _bootstrap()
    first_identity = _verified_codex_identity()
    first_identity["watcher_lease_generation"] = "lease:thread-interface:1"
    live_identity = dict(first_identity)
    monkeypatch.setattr(
        bridge,
        "_live_provider_identity_attestation",
        lambda seat_id: dict(live_identity) if seat_id == "sensorium-seat" else {},
    )

    def proof(identity: dict[str, object]) -> dict[str, object]:
        return {
            "schema_version": "laplace.startup-mail-gate/1",
            "seat_id": "sensorium-seat",
            "goal": "hostile renewal plant",
            "state": "MAIL_READY",
            "observed_at": "2026-08-27T12:00:00+00:00",
            "delivered": [],
            "provider_identity": identity,
        }

    bridge.seat_join(
        seat_id="sensorium-seat",
        holder_ref="codex:thread-interface",
        function="sensorium",
        information_proof=proof(first_identity),
        provider=PROVIDER,
        model=MODEL,
    )
    before = bridge.snapshot()["provider"]
    candidate = dict(first_identity)
    candidate["watcher_lease_generation"] = "lease:thread-interface:2"
    live_identity.clear()
    live_identity.update(candidate)
    function = "sensorium"

    if attack == "observational":
        candidate["state"] = "OBSERVATIONAL"
        live_identity["state"] = "OBSERVATIONAL"
    elif attack == "holder-mismatch":
        candidate["provider_session_ref"] = "codex:other-thread"
        live_identity["provider_session_ref"] = "codex:other-thread"
    elif attack == "function-mismatch":
        function = "ego"
    elif attack == "seat-mismatch":
        candidate["watcher_seat_id"] = "superego-seat"
        live_identity["watcher_seat_id"] = "superego-seat"
    elif attack == "stale-generation":
        candidate["watcher_lease_generation"] = "lease:thread-interface:1"
    elif attack == "absent-watcher":
        live_identity.clear()
    elif attack == "copied-proof":
        candidate["watcher_target_thread_id"] = "copied-thread"
    elif attack == "cross-task-replay":
        candidate = _verified_codex_identity("other-thread")
        candidate["watcher_seat_id"] = "sensorium-seat"
        candidate["watcher_lease_generation"] = "lease:other-thread:2"
        live_identity.clear()
        live_identity.update(candidate)
    elif attack == "persistent-unverified":
        live_identity.update(
            state="UNVERIFIED",
            watcher_status="STALE",
            watcher_interval_seconds=0.5,
        )
        monkeypatch.setattr(bridge.time, "sleep", lambda seconds: None)

    with pytest.raises(StateTransitionRefused, match=error):
        bridge.seat_join(
            seat_id="sensorium-seat",
            holder_ref="codex:thread-interface",
            function=function,
            information_proof=proof(candidate),
            provider=PROVIDER,
            model=MODEL,
        )

    after = bridge.snapshot()["provider"]
    assert after["event_count"] == before["event_count"]
    assert after["seat_occupancy"]["sensorium-seat"] == (
        before["seat_occupancy"]["sensorium-seat"]
    )


def test_provider_session_binding_is_exact_head_bound_and_snapshot_free(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bootstrap()
    _join_sensorium(monkeypatch)
    monkeypatch.setattr(
        bridge,
        "snapshot",
        lambda: (_ for _ in ()).throw(AssertionError("global snapshot forbidden")),
    )

    binding = bridge.provider_seat_binding(
        provider_session_ref="codex:thread-interface"
    )

    assert binding["status"] == "BOUND"
    assert binding["seat_id"] == "sensorium-seat"
    assert binding["matching_seats"] == ["sensorium-seat"]
    assert binding["read_metrics"]["rows_loaded"] == 1
    assert binding["read_metrics"]["history_replayed"] is False
    assert binding["read_metrics"]["provider_snapshot_materialized"] is False


def test_provider_session_binding_moves_with_authoritative_seat_rebind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bootstrap()
    _join_sensorium(monkeypatch)
    replacement_identity = _verified_codex_identity("thread-interface-2")
    monkeypatch.setattr(
        bridge,
        "_live_provider_identity_attestation",
        lambda _seat_id: replacement_identity,
    )
    bridge.seat_join(
        seat_id="sensorium-seat",
        holder_ref="codex:thread-interface-2",
        function="sensorium",
        information_proof={
            "schema_version": "laplace.startup-mail-gate/1",
            "seat_id": "sensorium-seat",
            "goal": "continue the conjugate interface",
            "state": "MAIL_READY",
            "observed_at": "2026-08-26T12:30:00+00:00",
            "delivered": [],
            "provider_identity": replacement_identity,
        },
        provider=PROVIDER,
        model=MODEL,
    )

    assert bridge.provider_seat_binding(
        provider_session_ref="codex:thread-interface"
    )["status"] == "UNBOUND"
    replacement = bridge.provider_seat_binding(
        provider_session_ref="codex:thread-interface-2"
    )
    assert replacement["status"] == "BOUND"
    assert replacement["seat_id"] == "sensorium-seat"


def test_provider_session_binding_refuses_a_deleted_projection_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bootstrap()
    _join_sensorium(monkeypatch)
    store = bridge._store()
    with store._connect_projection() as projection:
        projection.execute(
            "DELETE FROM provider_session_seat_projection "
            "WHERE provider_session_ref = ?",
            ("codex:thread-interface",),
        )
        projection.commit()

    with pytest.raises(
        HistoryChainMismatch,
        match="disagrees with canonical seat lifecycle",
    ):
        bridge.provider_seat_binding(
            provider_session_ref="codex:thread-interface"
        )


def test_seat_close_revokes_predecessor_provider_routing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bootstrap()
    _join_sensorium(monkeypatch)
    bridge.seat_transition(
        seat_id="sensorium-seat",
        role="sensorium",
        action="close",
        charter_ref="charter:sensorium",
        holder_ref="holder:sensorium-seat:1",
        provider=PROVIDER,
        model=MODEL,
    )

    binding = bridge.provider_seat_binding(
        provider_session_ref="codex:thread-interface"
    )
    state = bridge._store().current_state()

    assert binding["status"] == "UNBOUND"
    assert "sensorium-seat" not in state.seat_occupancies


def test_relay_and_activate_require_a_fresh_join_before_routing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bootstrap()
    _join_sensorium(monkeypatch)
    bridge.seat_transition(
        seat_id="sensorium-seat",
        role="sensorium",
        action="relay",
        charter_ref="charter:sensorium",
        holder_ref="holder:sensorium-seat:1",
        provider=PROVIDER,
        model=MODEL,
    )
    bridge.seat_transition(
        seat_id="sensorium-seat",
        role="sensorium",
        action="activate",
        charter_ref="charter:sensorium",
        holder_ref="holder:sensorium-seat:2",
        provider=PROVIDER,
        model=MODEL,
    )

    predecessor = bridge.provider_seat_binding(
        provider_session_ref="codex:thread-interface"
    )

    assert predecessor["status"] == "UNBOUND"
    assert "sensorium-seat" not in bridge._store().current_state().seat_occupancies


def test_region_checkout_and_git_backed_checkin_share_atlas_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bootstrap()
    joined = _join_sensorium(monkeypatch)
    assert joined["binding_receipt"]["kind"] == "seat.occupancy-bound"
    assert joined["occupancy"]["routing_authority"] is True
    heads = iter(("a" * 40, "b" * 40))
    monkeypatch.setattr(bridge, "_git_head", lambda: next(heads))
    monkeypatch.setattr(bridge, "_git_dirty_paths", lambda: ())
    monkeypatch.setattr(
        bridge,
        "_git_changed_paths",
        lambda base, result: ("src/laplace/conjugate_interface.py",),
    )
    monkeypatch.setattr(bridge, "_git_is_ancestor", lambda base, result: True)
    monkeypatch.setattr(
        bridge,
        "_git_holder_attribution",
        lambda **kwargs: {
            "schema_version": "laplace.git-holder-attribution/1",
            "lease_id": kwargs["lease_id"],
            "holder_ref": kwargs["holder_ref"],
            "attributed_commits": ["b" * 40],
            "attributed_paths": ["src/laplace/conjugate_interface.py"],
            "unattributed_paths": [],
            "required_trailers": {
                "Laplace-Lease": kwargs["lease_id"],
                "Laplace-Holder": kwargs["holder_ref"],
            },
        },
    )

    checked_out = bridge.checkout_regions(
        seat_id="sensorium-seat",
        holder_ref="codex:thread-interface",
        function="sensorium",
        act_id="interface-act-1",
        regions=("src/laplace/conjugate_interface.py",),
        expires_at="2036-08-27T12:00:00Z",
        declaration_kind="native",
        declaration_ref="contract/journal.jsonl#interface-act-1",
        bootstrap_crutch=None,
        provider=PROVIDER,
        model=MODEL,
    )
    lease_id = checked_out["lease"]["checkout"]["lease_id"]

    assert checked_out["receipt"]["kind"] == "region.checked-out"
    assert bridge.region_leases(as_of="2026-08-26T12:00:00Z")["active"] == [lease_id]

    checked_in = bridge.checkin_regions(
        lease_id=lease_id,
        seat_id="sensorium-seat",
        holder_ref="codex:thread-interface",
        function="sensorium",
        outcome="committed",
        evidence={"focused_tests": "sha256:" + ("f" * 64)},
        provider=PROVIDER,
        model=MODEL,
    )

    assert checked_in["receipt"]["kind"] == "region.checked-in"
    assert checked_in["lease"]["state"] == "CLOSED"
    assert checked_in["lease"]["checkin"]["committed_paths"] == [
        "src/laplace/conjugate_interface.py"
    ]
    assert bridge.region_leases(as_of="2026-08-26T12:00:00Z")["active"] == []


def test_region_projection_without_state_is_unknown_and_non_authoritative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bootstrap()
    _join_sensorium(monkeypatch)
    monkeypatch.setattr(bridge, "_git_head", lambda: "a" * 40)
    monkeypatch.setattr(bridge, "_git_dirty_paths", lambda: ())
    checkout = bridge.checkout_regions(
        seat_id="sensorium-seat",
        holder_ref="codex:thread-interface",
        function="sensorium",
        act_id="unknown-without-current-state",
        regions=("src/laplace/conjugate_interface.py",),
        expires_at="2036-08-27T12:00:00Z",
        declaration_kind="native",
        declaration_ref="test:unknown-without-current-state",
        bootstrap_crutch=None,
        provider=PROVIDER,
        model=MODEL,
    )
    lease_id = checkout["lease"]["checkout"]["lease_id"]
    lease = bridge._store().current_state().region_leases[lease_id]

    projected = bridge._project_region_lease(
        lease,
        "2026-08-28T04:00:00Z",
        state=None,
    )

    assert projected["effective_state"] == "UNKNOWN"
    assert projected["write_authority"] is False
    assert projected["lineage_state"] == "UNKNOWN"


def test_holder_attributed_commit_cannot_escape_its_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bootstrap()
    _join_sensorium(monkeypatch)
    heads = iter(("a" * 40, "b" * 40))
    monkeypatch.setattr(bridge, "_git_head", lambda: next(heads))
    monkeypatch.setattr(bridge, "_git_dirty_paths", lambda: ())
    monkeypatch.setattr(bridge, "_git_is_ancestor", lambda base, result: True)
    monkeypatch.setattr(
        bridge,
        "_git_changed_paths",
        lambda base, result: ("README.md", "src/laplace/conjugate_interface.py"),
    )
    checkout = bridge.checkout_regions(
        seat_id="sensorium-seat",
        holder_ref="codex:thread-interface",
        function="sensorium",
        act_id="mixed-scope-commit",
        regions=("src/laplace/conjugate_interface.py",),
        expires_at="2036-08-27T12:00:00Z",
        declaration_kind="native",
        declaration_ref="test:mixed-scope-commit",
        bootstrap_crutch=None,
        provider=PROVIDER,
        model=MODEL,
    )
    lease_id = checkout["lease"]["checkout"]["lease_id"]
    monkeypatch.setattr(bridge, "_git_commits_between", lambda base, result: ("b" * 40,))
    monkeypatch.setattr(
        bridge,
        "_git_commit_paths",
        lambda commit: ("README.md", "src/laplace/conjugate_interface.py"),
    )
    monkeypatch.setattr(
        bridge,
        "_git_commit_message",
        lambda commit: (
            "interface candidate\n\n"
            f"Laplace-Lease: {lease_id}\n"
            "Laplace-Holder: codex:thread-interface\n"
        ),
    )

    with pytest.raises(StateTransitionRefused, match="escapes its leased scope"):
        bridge.checkin_regions(
            lease_id=lease_id,
            seat_id="sensorium-seat",
            holder_ref="codex:thread-interface",
            function="sensorium",
            outcome="committed",
            evidence={"focused_tests": "sha256:" + ("f" * 64)},
            provider=PROVIDER,
            model=MODEL,
        )


def test_merge_commit_paths_are_visible_to_holder_attribution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "base.txt").write_text("base\n", encoding="utf-8")
    _commit_all(repo, "base")
    main_branch = subprocess.run(
        ["git", "branch", "--show-current"], cwd=repo, check=True,
        capture_output=True, text=True,
    ).stdout.strip()

    subprocess.run(["git", "checkout", "-qb", "side"], cwd=repo, check=True)
    (repo / "side.txt").write_text("side\n", encoding="utf-8")
    _commit_all(repo, "side")
    subprocess.run(["git", "checkout", "-q", main_branch], cwd=repo, check=True)
    (repo / "main.txt").write_text("main\n", encoding="utf-8")
    _commit_all(repo, "main")
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True,
        capture_output=True, text=True,
    ).stdout.strip()

    subprocess.run(
        ["git", "merge", "--no-ff", "--no-commit", "side"], cwd=repo, check=True,
        capture_output=True,
    )
    interface = repo / "src" / "laplace" / "conjugate_interface.py"
    interface.parent.mkdir(parents=True)
    interface.write_text("merge-result edit\n", encoding="utf-8")
    _commit_all(repo, "merge without lease trailers")
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    monkeypatch.setattr(bridge, "REPO_ROOT", repo)

    assert "src/laplace/conjugate_interface.py" in bridge._git_commit_paths(result)
    attribution = bridge._git_holder_attribution(
        base=base,
        result=result,
        lease_id="region-lease:merge",
        holder_ref="codex:thread-interface",
        regions=("src/laplace/conjugate_interface.py",),
    )
    assert attribution["unattributed_paths"] == [
        "src/laplace/conjugate_interface.py"
    ]


def _publication_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, str]:
    repo = tmp_path / "publication-repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Atlas Test"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "atlas@example.invalid"],
        cwd=repo,
        check=True,
    )
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    _commit_all(repo, "base")
    monkeypatch.setattr(bridge, "REPO_ROOT", repo)
    _bootstrap()
    bridge.seat_transition(
        seat_id="superego-seat",
        role="superego",
        action="found",
        charter_ref="charter:superego",
        holder_ref="holder:superego-seat:1",
        provider=PROVIDER,
        model=MODEL,
    )
    signers = (
        ("ego-seat", "ego", "codex:thread-ego", "a"),
        ("sensorium-seat", "sensorium", "codex:thread-interface", "b"),
        ("superego-seat", "superego", "codex:thread-superego", "c"),
    )
    identities = {
        seat_id: {
            "schema_version": "laplace.provider-session-identity/1",
            "state": "VERIFIED",
            "provider_session_ref": holder_ref,
            "requested_holder_ref": None,
            "provider": "codex",
            "identity_kind": "codex-thread-watcher-binding",
            "watcher_seat_id": seat_id,
            "watcher_target_thread_id": holder_ref.removeprefix("codex:"),
            "watcher_lease_generation": "sha256:" + generation * 64,
            "watcher_pid": 42,
            "reason": None,
        }
        for seat_id, _function, holder_ref, generation in signers
    }
    monkeypatch.setattr(
        bridge,
        "_live_provider_identity_attestation",
        lambda seat_id: dict(identities.get(seat_id, {})),
    )
    for seat_id, function, holder_ref, _generation in signers:
        bridge.seat_join(
            seat_id=seat_id,
            holder_ref=holder_ref,
            function=function,
            information_proof={
                "schema_version": "laplace.startup-mail-gate/1",
                "seat_id": seat_id,
                "goal": "judge the exact local-ref publication",
                "state": "MAIL_READY",
                "observed_at": "2026-08-26T12:00:00+00:00",
                "delivered": [],
                "provider_identity": identities[seat_id],
            },
            provider=PROVIDER,
            model=MODEL,
        )
    checkout = bridge.checkout_regions(
        seat_id="sensorium-seat",
        holder_ref="codex:thread-interface",
        function="sensorium",
        act_id="publish-interface-act",
        regions=("src/laplace/conjugate_interface.py",),
        expires_at="2036-08-27T12:00:00Z",
        declaration_kind="native",
        declaration_ref="test:publish-interface-act",
        bootstrap_crutch=None,
        provider=PROVIDER,
        model=MODEL,
    )
    return repo, checkout["lease"]["checkout"]["lease_id"]


def _publication_roots() -> dict:
    affected_roots = {"semantic.frontier": "sha256:" + "d" * 64}
    return {
        "affected_roots": affected_roots,
        "rehearsal_evidence_root": "sha256:" + "e" * 64,
    }


class _MemoryPublicationBlobs:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}

    def put(self, value: bytes) -> str:
        handle = bridge.hash_bytes(value)
        self.values[handle] = value
        return handle


def _private_checkout(*, base_git_head: str) -> bridge.RegionCheckout:
    return bridge.RegionCheckout(
        lease_id="region-lease:ancestry-repair",
        act_id="test-private-index-ancestry",
        seat_id="ego-seat",
        holder_ref="codex:test-ego",
        function=bridge.SeatRole.EGO,
        regions=("src/laplace/conjugate_interface.py",),
        base_git_head=base_git_head,
        expires_at="2036-08-27T12:00:00Z",
        declaration_kind=bridge.LeaseDeclarationKind.NATIVE,
        declaration_ref="test:ancestry-repair",
    )


def _private_publication_repo(tmp_path: Path) -> tuple[Path, str, str]:
    repo = tmp_path / "private-index-ancestry"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Atlas Test"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "atlas@example.invalid"], cwd=repo, check=True
    )
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    _commit_all(repo, "base")
    base_ref = subprocess.run(
        ["git", "symbolic-ref", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return repo, base_ref, base


def _build_private_candidate(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    checkout_head: str,
    base_ref: str,
) -> tuple[dict, _MemoryPublicationBlobs]:
    monkeypatch.setattr(bridge, "REPO_ROOT", repo)
    blobs = _MemoryPublicationBlobs()
    monkeypatch.setattr(bridge, "_blobs", lambda: blobs)
    candidate = bridge._private_index_candidate(
        checkout=_private_checkout(base_git_head=checkout_head),
        base_ref=base_ref,
        message="Preserve accepted ancestry",
        evidence={"focused": "sha256:" + "a" * 64},
    )
    return candidate, blobs


def test_private_index_candidate_preserves_38_commit_descendant_and_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, base_ref, expected_old = _private_publication_repo(tmp_path)
    subprocess.run(["git", "checkout", "--detach", "-q"], cwd=repo, check=True)
    accepted = repo / "accepted" / "history.txt"
    accepted.parent.mkdir()
    for number in range(1, 39):
        accepted.write_text(f"accepted {number}\n", encoding="utf-8")
        _commit_all(repo, f"accepted descendant {number}")
    checkout_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    target = repo / "src" / "laplace" / "conjugate_interface.py"
    target.parent.mkdir(parents=True)
    target.write_text("candidate\n", encoding="utf-8")
    monkeypatch.setattr(bridge, "REPO_ROOT", repo)
    index_before = bridge._main_index_receipt()

    candidate, blobs = _build_private_candidate(
        repo, monkeypatch, checkout_head=checkout_head, base_ref=base_ref
    )

    assert candidate["expected_old"] == expected_old
    assert candidate["candidate_parent"] == checkout_head
    assert candidate["private_index_recipe"]["candidate_parent"] == checkout_head
    assert candidate["committed_paths"] == ["src/laplace/conjugate_interface.py"]
    assert bridge._git_is_ancestor(expected_old, candidate["candidate_commit"])
    parent = subprocess.run(
        ["git", "rev-parse", f"{candidate['candidate_commit']}^"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert parent == checkout_head
    assert subprocess.run(
        ["git", "show", f"{candidate['candidate_commit']}:accepted/history.txt"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout == "accepted 38\n"
    assert b"accepted/history.txt" not in blobs.values[candidate["patch_handle"]]
    assert bridge._main_index_receipt() == index_before


def test_private_index_candidate_uses_target_ahead_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, base_ref, checkout_head = _private_publication_repo(tmp_path)
    accepted = repo / "accepted.txt"
    for number in range(1, 4):
        accepted.write_text(f"target ahead {number}\n", encoding="utf-8")
        _commit_all(repo, f"target ahead {number}")
    expected_old = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    target = repo / "src" / "laplace" / "conjugate_interface.py"
    target.parent.mkdir(parents=True)
    target.write_text("candidate\n", encoding="utf-8")

    candidate, _blobs = _build_private_candidate(
        repo, monkeypatch, checkout_head=checkout_head, base_ref=base_ref
    )

    assert candidate["expected_old"] == expected_old
    assert candidate["candidate_parent"] == expected_old
    assert subprocess.run(
        ["git", "rev-parse", f"{candidate['candidate_commit']}^"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip() == expected_old
    assert bridge._git_is_ancestor(expected_old, candidate["candidate_commit"])


def test_private_index_candidate_refuses_divergence_and_ref_races(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, base_ref, base = _private_publication_repo(tmp_path)
    subprocess.run(["git", "checkout", "-qb", "side"], cwd=repo, check=True)
    (repo / "side.txt").write_text("side\n", encoding="utf-8")
    _commit_all(repo, "side")
    side = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    main_name = base_ref.removeprefix("refs/heads/")
    subprocess.run(["git", "checkout", "-q", main_name], cwd=repo, check=True)
    (repo / "main.txt").write_text("main\n", encoding="utf-8")
    _commit_all(repo, "main")
    expected_old = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    target = repo / "src" / "laplace" / "conjugate_interface.py"
    target.parent.mkdir(parents=True)
    target.write_text("candidate\n", encoding="utf-8")
    monkeypatch.setattr(bridge, "REPO_ROOT", repo)
    blobs = _MemoryPublicationBlobs()
    monkeypatch.setattr(bridge, "_blobs", lambda: blobs)
    with pytest.raises(StateTransitionRefused, match="diverged"):
        bridge._private_index_candidate(
            checkout=_private_checkout(base_git_head=side),
            base_ref=base_ref,
            message="Refuse sibling ancestry",
            evidence={"focused": "sha256:" + "b" * 64},
        )

    candidate = bridge._private_index_candidate(
        checkout=_private_checkout(base_git_head=expected_old),
        base_ref=base_ref,
        message="Fence ref races",
        evidence={"focused": "sha256:" + "c" * 64},
    )
    index_before = bridge._main_index_receipt()
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "forward race"], cwd=repo, check=True
    )
    forward = bridge._git_ref_oid(base_ref)
    with pytest.raises(StateTransitionRefused, match="moved outside"):
        bridge._git_update_ref_once(
            base_ref=base_ref,
            expected_old=candidate["expected_old"],
            candidate_commit=candidate["candidate_commit"],
        )
    assert bridge._git_ref_oid(base_ref) == forward
    subprocess.run(
        ["git", "update-ref", "--no-deref", base_ref, base, forward], cwd=repo, check=True
    )
    with pytest.raises(StateTransitionRefused, match="moved outside"):
        bridge._git_update_ref_once(
            base_ref=base_ref,
            expected_old=candidate["expected_old"],
            candidate_commit=candidate["candidate_commit"],
        )
    assert bridge._git_ref_oid(base_ref) == base
    assert bridge._main_index_receipt() == index_before


def _sign_publication_triad(lease_id: str, prepared: dict) -> list[dict]:
    results = []
    for seat_id, holder_ref, function, profile, reconstruction in (
        ("ego-seat", "codex:thread-ego", "ego", "1", "4"),
        (
            "sensorium-seat",
            "codex:thread-interface",
            "sensorium",
            "2",
            "5",
        ),
        (
            "superego-seat",
            "codex:thread-superego",
            "superego",
            "3",
            "6",
        ),
    ):
        results.append(
            _sign_publication_role(
                lease_id,
                prepared,
                seat_id=seat_id,
                holder_ref=holder_ref,
                function=function,
                profile=profile,
                reconstruction=reconstruction,
            )
        )
    return results


def _sign_publication_role(
    lease_id: str,
    prepared: dict,
    *,
    seat_id: str,
    holder_ref: str,
    function: str,
    profile: str,
    reconstruction: str,
    expires_at: str = "2036-08-27T12:00:00Z",
    **expected_overrides: str,
) -> dict:
    expected = {
        "expected_candidate_commit": prepared["candidate_commit"],
        "expected_candidate_tree": prepared["candidate_tree"],
        "expected_patch_handle": prepared["patch_handle"],
        "expected_custody_handle": prepared["custody_handle"],
        "expected_affected_frontier_root": prepared["affected_frontier_root"],
        "expected_rehearsal_evidence_root": prepared["rehearsal_evidence_root"],
        "expected_forward_closure_root": prepared["forward_closure_root"],
        **expected_overrides,
    }
    return bridge.sign_region_publication(
        lease_id=lease_id,
        publication_id=prepared["publication_id"],
        expected_recovery_root=prepared["recovery_root"],
        seat_id=seat_id,
        holder_ref=holder_ref,
        function=function,
        role_profile_handle="sha256:" + profile * 64,
        reconstruction_handle="sha256:" + reconstruction * 64,
        predicate_result="PASS",
        expires_at=expires_at,
        provider=PROVIDER,
        model=MODEL,
        **expected,
    )


def _prepare_publication_for_signing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    message: str = "Triad local-ref candidate",
) -> tuple[Path, str, dict]:
    repo, lease_id = _publication_checkout(tmp_path, monkeypatch)
    target = repo / "src" / "laplace" / "conjugate_interface.py"
    target.parent.mkdir(parents=True)
    target.write_text("triad local-ref candidate\n", encoding="utf-8")
    base_ref = subprocess.run(
        ["git", "symbolic-ref", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    prepared = bridge.prepare_region_publication(
        lease_id=lease_id,
        seat_id="sensorium-seat",
        holder_ref="codex:thread-interface",
        function="sensorium",
        base_ref=base_ref,
        **_publication_roots(),
        message=message,
        evidence={"focused": "sha256:" + "9" * 64},
        provider=PROVIDER,
        model=MODEL,
    )["publication"]["prepared"]
    return repo, lease_id, prepared


def test_publish_regions_is_thin_and_refuses_without_prepared_triad(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _repo, lease_id = _publication_checkout(tmp_path, monkeypatch)
    before = bridge.drift_token()
    monkeypatch.setattr(
        bridge,
        "_git_update_ref_once",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("thin finalizer reached Git without triad authority")
        ),
    )
    with pytest.raises(StateTransitionRefused, match="PREPARED, triad-SIGNED, and AUTHORIZED"):
        bridge.publish_regions(
            lease_id=lease_id,
            seat_id="sensorium-seat",
            holder_ref="codex:thread-interface",
            function="sensorium",
            message="must not publish",
            evidence={"focused_tests": "sha256:" + ("f" * 64)},
            provider=PROVIDER,
            model=MODEL,
        )
    assert bridge.drift_token() == before


def test_triad_signoff_refuses_wrong_order_bytes_duplicate_and_two_of_three(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repo, lease_id, prepared = _prepare_publication_for_signing(tmp_path, monkeypatch)
    before = bridge.drift_token()
    with pytest.raises(StateTransitionRefused, match="Ego then Aisthesis then Superego"):
        _sign_publication_role(
            lease_id,
            prepared,
            seat_id="sensorium-seat",
            holder_ref="codex:thread-interface",
            function="sensorium",
            profile="2",
            reconstruction="5",
        )
    with pytest.raises(StateTransitionRefused, match="different candidate or frontier"):
        _sign_publication_role(
            lease_id,
            prepared,
            seat_id="ego-seat",
            holder_ref="codex:thread-ego",
            function="ego",
            profile="1",
            reconstruction="4",
            expected_patch_handle="sha256:" + "0" * 64,
        )
    assert bridge.drift_token() == before

    first = _sign_publication_role(
        lease_id,
        prepared,
        seat_id="ego-seat",
        holder_ref="codex:thread-ego",
        function="ego",
        profile="1",
        reconstruction="4",
    )
    replay = _sign_publication_role(
        lease_id,
        prepared,
        seat_id="ego-seat",
        holder_ref="codex:thread-ego",
        function="ego",
        profile="1",
        reconstruction="4",
    )
    assert first["idempotent"] is False
    assert replay["idempotent"] is True
    with pytest.raises(StateTransitionRefused, match="role already signed different bytes"):
        _sign_publication_role(
            lease_id,
            prepared,
            seat_id="ego-seat",
            holder_ref="codex:thread-ego",
            function="ego",
            profile="7",
            reconstruction="4",
        )
    with pytest.raises(StateTransitionRefused, match="identity is not currently bound"):
        _sign_publication_role(
            lease_id,
            prepared,
            seat_id="ego-seat",
            holder_ref="codex:thread-ego",
            function="sensorium",
            profile="2",
            reconstruction="5",
        )
    with pytest.raises(StateTransitionRefused, match="exact triad"):
        bridge.authorize_region_publication(
            lease_id=lease_id,
            publication_id=prepared["publication_id"],
            expected_recovery_root=prepared["recovery_root"],
            provider=PROVIDER,
            model=MODEL,
        )
    _sign_publication_role(
        lease_id,
        prepared,
        seat_id="sensorium-seat",
        holder_ref="codex:thread-interface",
        function="sensorium",
        profile="2",
        reconstruction="5",
    )
    with pytest.raises(StateTransitionRefused, match="exact triad"):
        bridge.authorize_region_publication(
            lease_id=lease_id,
            publication_id=prepared["publication_id"],
            expected_recovery_root=prepared["recovery_root"],
            provider=PROVIDER,
            model=MODEL,
        )


def test_triad_refuses_expired_signer_and_superego_non_consumption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repo, lease_id, prepared = _prepare_publication_for_signing(tmp_path, monkeypatch)
    before = bridge.drift_token()
    with pytest.raises(StateTransitionRefused, match="signoff is expired"):
        _sign_publication_role(
            lease_id,
            prepared,
            seat_id="ego-seat",
            holder_ref="codex:thread-ego",
            function="ego",
            profile="1",
            reconstruction="4",
            expires_at="2020-01-01T00:00:00Z",
        )
    assert bridge.drift_token() == before
    _sign_publication_role(
        lease_id,
        prepared,
        seat_id="ego-seat",
        holder_ref="codex:thread-ego",
        function="ego",
        profile="1",
        reconstruction="4",
    )
    _sign_publication_role(
        lease_id,
        prepared,
        seat_id="sensorium-seat",
        holder_ref="codex:thread-interface",
        function="sensorium",
        profile="2",
        reconstruction="5",
    )
    original_event = bridge._event

    def forge_superego_consumption(kind, payload, **kwargs):
        if kind == bridge.EventKind.REGION_PUBLICATION_SIGNED:
            forged = dict(payload)
            forged["consumed_signoff_event_ids"] = [
                "sha256:" + "7" * 64,
                "sha256:" + "8" * 64,
            ]
            identity = dict(forged)
            identity.pop("signoff_root")
            forged["signoff_root"] = bridge.chash(identity)
            return original_event(kind, forged, **kwargs)
        return original_event(kind, payload, **kwargs)

    monkeypatch.setattr(bridge, "_event", forge_superego_consumption)
    before_superego = bridge.drift_token()
    with pytest.raises(StateTransitionRefused, match="does not consume the exact prior"):
        _sign_publication_role(
            lease_id,
            prepared,
            seat_id="superego-seat",
            holder_ref="codex:thread-superego",
            function="superego",
            profile="3",
            reconstruction="6",
        )
    assert bridge.drift_token() == before_superego


def test_authorization_refuses_replaced_signer_before_any_ref_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repo, lease_id, prepared = _prepare_publication_for_signing(tmp_path, monkeypatch)
    _sign_publication_role(
        lease_id,
        prepared,
        seat_id="ego-seat",
        holder_ref="codex:thread-ego",
        function="ego",
        profile="1",
        reconstruction="4",
    )
    _sign_publication_role(
        lease_id,
        prepared,
        seat_id="sensorium-seat",
        holder_ref="codex:thread-interface",
        function="sensorium",
        profile="2",
        reconstruction="5",
    )
    replacement = {
        "schema_version": "laplace.provider-session-identity/1",
        "state": "VERIFIED",
        "provider_session_ref": "codex:thread-interface",
        "requested_holder_ref": None,
        "provider": "codex",
        "identity_kind": "codex-thread-watcher-binding",
        "watcher_seat_id": "sensorium-seat",
        "watcher_target_thread_id": "thread-interface",
        "watcher_lease_generation": "sha256:" + "0" * 64,
        "watcher_pid": 84,
        "reason": None,
    }
    monkeypatch.setattr(
        bridge,
        "_live_provider_identity_attestation",
        lambda seat_id: replacement if seat_id == "sensorium-seat" else {},
    )
    bridge.seat_join(
        seat_id="sensorium-seat",
        holder_ref="codex:thread-interface",
        function="sensorium",
        information_proof={
            "schema_version": "laplace.startup-mail-gate/1",
            "seat_id": "sensorium-seat",
            "goal": "renew signer identity",
            "state": "MAIL_READY",
            "observed_at": "2026-08-26T12:00:00+00:00",
            "delivered": [],
            "provider_identity": replacement,
        },
        provider=PROVIDER,
        model=MODEL,
    )
    _sign_publication_role(
        lease_id,
        prepared,
        seat_id="superego-seat",
        holder_ref="codex:thread-superego",
        function="superego",
        profile="3",
        reconstruction="6",
    )
    before = bridge.drift_token()
    with pytest.raises(StateTransitionRefused, match="replaced before authorization"):
        bridge.authorize_region_publication(
            lease_id=lease_id,
            publication_id=prepared["publication_id"],
            expected_recovery_root=prepared["recovery_root"],
            provider=PROVIDER,
            model=MODEL,
        )
    assert bridge.drift_token() == before


def test_prepared_publication_private_index_authorize_cas_finalize(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, lease_id = _publication_checkout(tmp_path, monkeypatch)
    target = repo / "src" / "laplace" / "conjugate_interface.py"
    target.parent.mkdir(parents=True)
    target.write_text("prepared publication\n", encoding="utf-8")
    base_ref = subprocess.run(
        ["git", "symbolic-ref", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    expected_old = bridge._git_ref_oid(base_ref)
    index_before = bridge._main_index_receipt()

    prepared_result = bridge.prepare_region_publication(
        lease_id=lease_id,
        seat_id="sensorium-seat",
        holder_ref="codex:thread-interface",
        function="sensorium",
        base_ref=base_ref,
        **_publication_roots(),
        message="Prepare exact publication",
        evidence={"focused": "sha256:" + "a" * 64},
        provider=PROVIDER,
        model=MODEL,
    )
    saga = prepared_result["publication"]
    prepared = saga["prepared"]
    hook = bridge.RegionForwardClosure.from_dict(prepared["forward_closure"])
    assert prepared["affected_frontier_root"] == bridge.region_publication_affected_frontier_root(
        hook.affected_roots
    )
    assert prepared["forward_closure_root"] == hook.forward_closure_root
    assert bridge._git_ref_oid(base_ref) == expected_old
    assert bridge._main_index_receipt() == index_before
    assert saga["state"] == "PREPARED"

    signoffs = _sign_publication_triad(lease_id, prepared)
    assert [item["signoff"]["signoff"]["predicate_domain"] for item in signoffs] == [
        "ego",
        "aisthesis",
        "superego",
    ]
    authorized = bridge.authorize_region_publication(
        lease_id=lease_id,
        publication_id=prepared["publication_id"],
        expected_recovery_root=prepared["recovery_root"],
        provider=PROVIDER,
        model=MODEL,
    )
    assert authorized["publication"]["state"] == "AUTHORIZED"
    assert bridge._git_ref_oid(base_ref) == expected_old

    finalized = bridge.publish_regions(
        lease_id=lease_id,
        seat_id="sensorium-seat",
        holder_ref="codex:thread-interface",
        function="sensorium",
        message="Prepare exact publication",
        evidence={"focused": "sha256:" + "a" * 64},
        provider=PROVIDER,
        model=MODEL,
    )
    assert finalized["publication"]["state"] == "FINALIZED"
    assert bridge._git_ref_oid(base_ref) == prepared["candidate_commit"]
    assert bridge._main_index_receipt() == index_before
    finalized_payload = finalized["publication"]["finalized"]
    assert finalized_payload["forward_closure_consumption_root"] == (
        bridge.region_forward_closure_consumption_root(
            forward_closure_root=hook.forward_closure_root,
            authorized_event_id=finalized_payload["authorized_event_id"],
            finalized_projection_digest=hook.finalized_projection_digest,
        )
    )
    replay = bridge.publish_regions(
        lease_id=lease_id,
        seat_id="sensorium-seat",
        holder_ref="codex:thread-interface",
        function="sensorium",
        message="Prepare exact publication",
        evidence={"focused": "sha256:" + "a" * 64},
        provider=PROVIDER,
        model=MODEL,
    )
    assert replay["idempotent"] is True
    hot = bridge._store().current_state().region_leases[lease_id].publication.to_dict()
    bridge._store_at.cache_clear()
    cold = bridge._store().current_state().region_leases[lease_id].publication.to_dict()
    assert cold == hot
    status = bridge.region_publication(
        lease_id=lease_id,
        publication_id=prepared["publication_id"],
    )
    assert status["state"] == "FINALIZED"
    assert status["read_metrics"]["keyed_object_rows_loaded"] == 1
    assert status["read_metrics"]["global_history_replayed"] is False
    assert status["integrity_boundary"] == "CHECKSUMMED-CRUTCH"


def _prepare_authorized_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, str, dict]:
    repo, lease_id = _publication_checkout(tmp_path, monkeypatch)
    target = repo / "src" / "laplace" / "conjugate_interface.py"
    target.parent.mkdir(parents=True)
    target.write_text("recoverable candidate\n", encoding="utf-8")
    base_ref = subprocess.run(
        ["git", "symbolic-ref", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    prepared = bridge.prepare_region_publication(
        lease_id=lease_id,
        seat_id="sensorium-seat",
        holder_ref="codex:thread-interface",
        function="sensorium",
        base_ref=base_ref,
        **_publication_roots(),
        message="Recover exact publication",
        evidence={"focused": "sha256:" + "b" * 64},
        provider=PROVIDER,
        model=MODEL,
    )["publication"]["prepared"]
    _sign_publication_triad(lease_id, prepared)
    bridge.authorize_region_publication(
        lease_id=lease_id,
        publication_id=prepared["publication_id"],
        expected_recovery_root=prepared["recovery_root"],
        provider=PROVIDER,
        model=MODEL,
    )
    return repo, lease_id, prepared


def test_publication_recovery_closes_both_crash_boundaries_and_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, lease_id, prepared = _prepare_authorized_publication(tmp_path, monkeypatch)

    recovered = bridge.recover_region_publication(
        lease_id=lease_id,
        publication_id=prepared["publication_id"],
        expected_recovery_root=prepared["recovery_root"],
        provider=PROVIDER,
        model=MODEL,
    )
    assert recovered["publication"]["state"] == "FINALIZED"
    replayed = bridge.recover_region_publication(
        lease_id=lease_id,
        publication_id=prepared["publication_id"],
        expected_recovery_root=prepared["recovery_root"],
        provider=PROVIDER,
        model=MODEL,
    )
    assert replayed["idempotent"] is True


def test_publication_recovery_after_cas_needs_no_worktree_or_private_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, lease_id, prepared = _prepare_authorized_publication(tmp_path, monkeypatch)
    assert bridge._git_update_ref_once(
        base_ref=prepared["base_ref"],
        expected_old=prepared["expected_old"],
        candidate_commit=prepared["candidate_commit"],
    ) == "CAS-APPLIED"
    shutil.rmtree(repo / "src")
    after_cas = bridge.recover_region_publication(
        lease_id=lease_id,
        publication_id=prepared["publication_id"],
        expected_recovery_root=prepared["recovery_root"],
        provider=PROVIDER,
        model=MODEL,
    )
    assert after_cas["publication"]["state"] == "FINALIZED"


def test_publication_recovery_refuses_ref_movement_without_consuming_authorization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, lease_id, prepared = _prepare_authorized_publication(tmp_path, monkeypatch)
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "concurrent ref movement"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    moved = bridge._git_ref_oid(prepared["base_ref"])

    status = bridge.region_publication(
        lease_id=lease_id,
        publication_id=prepared["publication_id"],
    )
    assert status["state"] == "REFUSED"
    with pytest.raises(StateTransitionRefused, match="recovery refuses"):
        bridge.recover_region_publication(
            lease_id=lease_id,
            publication_id=prepared["publication_id"],
            expected_recovery_root=prepared["recovery_root"],
            provider=PROVIDER,
            model=MODEL,
        )
    assert bridge._git_ref_oid(prepared["base_ref"]) == moved


@pytest.mark.parametrize("plant", ("consumption", "affected-root", "related-head", "expiry"))
def test_forward_closure_refuses_in_locked_dry_fold_before_cas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, plant: str
) -> None:
    _repo, lease_id, prepared = _prepare_authorized_publication(tmp_path, monkeypatch)
    if plant == "related-head":
        bridge.seat_transition(
            seat_id="unrelated-audit-seat",
            role="provider",
            action="found",
            charter_ref="charter:unrelated-audit",
            holder_ref="holder:unrelated-audit",
            provider=PROVIDER,
            model=MODEL,
        )
    elif plant == "expiry":
        monkeypatch.setattr(bridge, "_now", lambda: "2037-08-27T12:00:00Z")
    else:
        original_event = bridge._event

        def forged_event(kind, payload, **kwargs):
            if kind == bridge.EventKind.REGION_PUBLICATION_FINALIZED:
                forged = json.loads(json.dumps(payload))
                field = (
                    "forward_closure_consumption_root"
                    if plant == "consumption"
                    else "affected_frontier_root"
                )
                forged[field] = "sha256:" + "0" * 64
                return original_event(kind, forged, **kwargs)
            return original_event(kind, payload, **kwargs)

        monkeypatch.setattr(bridge, "_event", forged_event)

    cas_calls = 0

    def sentinel_cas(**_kwargs):
        nonlocal cas_calls
        cas_calls += 1
        raise AssertionError("ref CAS was reached before forward-closure refusal")

    monkeypatch.setattr(bridge, "_git_update_ref_once", sentinel_cas)
    before = bridge.drift_token()
    with pytest.raises(StateTransitionRefused):
        bridge.finalize_region_publication(
            lease_id=lease_id,
            publication_id=prepared["publication_id"],
            expected_recovery_root=prepared["recovery_root"],
            provider=PROVIDER,
            model=MODEL,
        )
    assert cas_calls == 0
    assert bridge.drift_token() == before


def test_publication_is_local_head_only_and_finalized_ref_rollback_is_visible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, lease_id = _publication_checkout(tmp_path, monkeypatch)
    target = repo / "src" / "laplace" / "conjugate_interface.py"
    target.parent.mkdir(parents=True)
    target.write_text("local-ref candidate\n", encoding="utf-8")
    before = bridge.drift_token()
    with pytest.raises(StateTransitionRefused, match="exact refs/heads"):
        bridge.prepare_region_publication(
            lease_id=lease_id,
            seat_id="sensorium-seat",
            holder_ref="codex:thread-interface",
            function="sensorium",
            base_ref="refs/remotes/origin/main",
            **_publication_roots(),
            message="Refuse remote publication",
            evidence={"focused": "sha256:" + "e" * 64},
            provider=PROVIDER,
            model=MODEL,
        )
    assert bridge.drift_token() == before

    base_ref = subprocess.run(
        ["git", "symbolic-ref", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    prepared = bridge.prepare_region_publication(
        lease_id=lease_id,
        seat_id="sensorium-seat",
        holder_ref="codex:thread-interface",
        function="sensorium",
        base_ref=base_ref,
        **_publication_roots(),
        message="Detect finalized rollback",
        evidence={"focused": "sha256:" + "e" * 64},
        provider=PROVIDER,
        model=MODEL,
    )["publication"]["prepared"]
    _sign_publication_triad(lease_id, prepared)
    bridge.authorize_region_publication(
        lease_id=lease_id,
        publication_id=prepared["publication_id"],
        expected_recovery_root=prepared["recovery_root"],
        provider=PROVIDER,
        model=MODEL,
    )
    bridge.finalize_region_publication(
        lease_id=lease_id,
        publication_id=prepared["publication_id"],
        expected_recovery_root=prepared["recovery_root"],
        provider=PROVIDER,
        model=MODEL,
    )
    subprocess.run(
        [
            "git",
            "update-ref",
            "--no-deref",
            base_ref,
            prepared["expected_old"],
            prepared["candidate_commit"],
        ],
        cwd=repo,
        check=True,
    )
    status = bridge.region_publication(
        lease_id=lease_id,
        publication_id=prepared["publication_id"],
    )
    assert status["state"] == "REFUSED"
    assert status["reason"] == "finalized ref was rolled back or moved"


def test_publish_regions_runs_forward_transition_before_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from laplace.representation import codex_seat_watcher

    repo, lease_id = _publication_checkout(tmp_path, monkeypatch)
    interface = repo / "src" / "laplace" / "conjugate_interface.py"
    interface.parent.mkdir(parents=True)
    interface.write_text("forward-locked candidate\n", encoding="utf-8")
    order = []
    monkeypatch.setattr(
        codex_seat_watcher,
        "publication_transition",
        lambda paths: order.append(("transition", tuple(paths))) or {
            "schema_version": "laplace.watcher-publication-transition/1",
            "status": "READY-NOT-ACTIVE",
        },
    )
    with pytest.raises(
        StateTransitionRefused,
        match="PREPARED, triad-SIGNED, and AUTHORIZED",
    ):
        bridge.publish_regions(
            lease_id=lease_id,
            seat_id="sensorium-seat",
            holder_ref="codex:thread-interface",
            function="sensorium",
            message="Publish behind the forward transition",
            evidence={"focused_tests": "sha256:" + "f" * 64},
            provider=PROVIDER,
            model=MODEL,
        )

    assert order == []


def test_publish_regions_refuses_a_preexisting_staged_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, lease_id = _publication_checkout(tmp_path, monkeypatch)
    interface = repo / "src" / "laplace" / "conjugate_interface.py"
    interface.parent.mkdir(parents=True)
    interface.write_text("candidate\n", encoding="utf-8")
    (repo / "README.md").write_text("staged outside work\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
    before = bridge._git_head()

    with pytest.raises(
        StateTransitionRefused,
        match="PREPARED, triad-SIGNED, and AUTHORIZED",
    ):
        bridge.publish_regions(
            lease_id=lease_id,
            seat_id="sensorium-seat",
            holder_ref="codex:thread-interface",
            function="sensorium",
            message="must refuse",
            evidence={"independent_verdict": "message:attack-accepted"},
            provider=PROVIDER,
            model=MODEL,
        )

    assert bridge._git_head() == before


def test_publish_regions_disables_hooks_that_could_replace_measured_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, lease_id = _publication_checkout(tmp_path, monkeypatch)
    interface = repo / "src" / "laplace" / "conjugate_interface.py"
    interface.parent.mkdir(parents=True)
    interface.write_text("caller candidate\n", encoding="utf-8")
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text(
        "#!/bin/sh\n"
        "printf 'hook-replaced candidate\\n' > src/laplace/conjugate_interface.py\n"
        "git add src/laplace/conjugate_interface.py\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)

    before = bridge._git_head()
    with pytest.raises(
        StateTransitionRefused,
        match="PREPARED, triad-SIGNED, and AUTHORIZED",
    ):
        bridge.publish_regions(
            lease_id=lease_id,
            seat_id="sensorium-seat",
            holder_ref="codex:thread-interface",
            function="sensorium",
            message="Publish the measured caller candidate",
            evidence={"independent_verdict": "message:attack-accepted"},
            provider=PROVIDER,
            model=MODEL,
        )

    assert bridge._git_head() == before
    assert interface.read_text(encoding="utf-8") == "caller candidate\n"


def test_region_checkout_fails_at_outer_door_without_exact_live_occupant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bootstrap()
    git_read = False

    def head() -> str:
        nonlocal git_read
        git_read = True
        return "a" * 40

    monkeypatch.setattr(bridge, "_git_head", head)
    kwargs = dict(
        seat_id="sensorium-seat",
        holder_ref="codex:fabricated",
        function="sensorium",
        act_id="interface-act-refused",
        regions=("src/laplace/conjugate_interface.py",),
        expires_at="2036-08-27T12:00:00Z",
        declaration_kind="native",
        declaration_ref="contract/journal.jsonl#interface-act-refused",
        bootstrap_crutch=None,
        provider=PROVIDER,
        model=MODEL,
    )
    with pytest.raises(StateTransitionRefused, match="proved seat join"):
        bridge.checkout_regions(**kwargs)
    assert git_read is False

    _join_sensorium(monkeypatch)
    with pytest.raises(StateTransitionRefused, match="holder disagrees"):
        bridge.checkout_regions(**kwargs)
    assert git_read is False

    kwargs["holder_ref"] = "codex:thread-interface"
    kwargs["function"] = "ego"
    with pytest.raises(StateTransitionRefused, match="function disagrees"):
        bridge.checkout_regions(**kwargs)
    assert git_read is False


def test_region_noop_checkin_survives_concurrent_commit_outside_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bootstrap()
    _join_sensorium(monkeypatch)
    heads = iter(("a" * 40, "b" * 40))
    monkeypatch.setattr(bridge, "_git_head", lambda: next(heads))
    monkeypatch.setattr(bridge, "_git_dirty_paths", lambda: ())
    monkeypatch.setattr(
        bridge,
        "_git_changed_paths",
        lambda base, result: ("README.md",),
    )
    monkeypatch.setattr(bridge, "_git_is_ancestor", lambda base, result: True)
    monkeypatch.setattr(
        bridge,
        "_git_holder_attribution",
        lambda **kwargs: {
            "schema_version": "laplace.git-holder-attribution/1",
            "lease_id": kwargs["lease_id"],
            "holder_ref": kwargs["holder_ref"],
            "attributed_commits": [],
            "attributed_paths": [],
            "unattributed_paths": [],
            "required_trailers": {
                "Laplace-Lease": kwargs["lease_id"],
                "Laplace-Holder": kwargs["holder_ref"],
            },
        },
    )
    checkout = bridge.checkout_regions(
        seat_id="sensorium-seat",
        holder_ref="codex:thread-interface",
        function="sensorium",
        act_id="interface-noop",
        regions=("src/laplace/conjugate_interface.py",),
        expires_at="2036-08-27T12:00:00Z",
        declaration_kind="native",
        declaration_ref="contract/journal.jsonl#interface-noop",
        bootstrap_crutch=None,
        provider=PROVIDER,
        model=MODEL,
    )
    result = bridge.checkin_regions(
        lease_id=checkout["lease"]["checkout"]["lease_id"],
        seat_id="sensorium-seat",
        holder_ref="codex:thread-interface",
        function="sensorium",
        outcome="noop",
        evidence={"focused_tests": "sha256:" + ("f" * 64)},
        provider=PROVIDER,
        model=MODEL,
    )
    assert result["lease"]["checkin"]["outcome"] == "noop"
    assert result["lease"]["checkin"]["base_git_head"] == "a" * 40
    assert result["lease"]["checkin"]["result_git_head"] == "b" * 40
    proof = bridge.custody_body(handle=result["evidence_handle"])["text"]
    assert '"concurrent_paths_outside_scope":["README.md"]' in proof


def test_rejoin_supersedes_old_binding_and_refuses_old_checkin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bootstrap()
    first = _join_sensorium(monkeypatch)
    heads = iter(("a" * 40, "b" * 40))
    monkeypatch.setattr(bridge, "_git_head", lambda: next(heads))
    monkeypatch.setattr(bridge, "_git_dirty_paths", lambda: ())
    monkeypatch.setattr(bridge, "_git_changed_paths", lambda base, result: ())
    checkout = bridge.checkout_regions(
        seat_id="sensorium-seat",
        holder_ref="codex:thread-interface",
        function="sensorium",
        act_id="interface-displaced",
        regions=("src/laplace/conjugate_interface.py",),
        expires_at="2036-08-27T12:00:00Z",
        declaration_kind="native",
        declaration_ref="contract/journal.jsonl#interface-displaced",
        bootstrap_crutch=None,
        provider=PROVIDER,
        model=MODEL,
    )
    second_identity = _verified_codex_identity("thread-interface-2")
    monkeypatch.setattr(
        bridge,
        "_live_provider_identity_attestation",
        lambda seat_id: second_identity,
    )
    second = bridge.seat_join(
        seat_id="sensorium-seat",
        holder_ref="codex:thread-interface-2",
        function="sensorium",
        information_proof={
            "schema_version": "laplace.startup-mail-gate/1",
            "seat_id": "sensorium-seat",
            "goal": "continue the conjugate interface",
            "state": "MAIL_READY",
            "observed_at": "2026-08-26T12:30:00+00:00",
            "delivered": [],
            "provider_identity": second_identity,
        },
        provider=PROVIDER,
        model=MODEL,
    )

    assert first["occupancy"]["binding_event_id"] != second["occupancy"]["binding_event_id"]
    assert second["occupancy"]["routing_authority"] is True
    with pytest.raises(StateTransitionRefused, match="latest seat occupancy"):
        bridge.checkin_regions(
            lease_id=checkout["lease"]["checkout"]["lease_id"],
            seat_id="sensorium-seat",
            holder_ref="codex:thread-interface",
            function="sensorium",
            outcome="noop",
            evidence={"focused_tests": "sha256:" + ("f" * 64)},
            provider=PROVIDER,
            model=MODEL,
        )


def test_same_holder_fresh_generation_permanently_displaces_old_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bootstrap()
    _join_sensorium(monkeypatch)
    monkeypatch.setattr(bridge, "_git_head", lambda: "a" * 40)
    monkeypatch.setattr(bridge, "_git_dirty_paths", lambda: ())
    checkout_kwargs = dict(
        seat_id="sensorium-seat",
        holder_ref="codex:thread-interface",
        function="sensorium",
        act_id="interface-generation-one",
        regions=("src/laplace/conjugate_interface.py",),
        expires_at="2036-08-27T12:00:00Z",
        declaration_kind="native",
        declaration_ref="test:interface-generation-one",
        bootstrap_crutch=None,
        provider=PROVIDER,
        model=MODEL,
    )
    first = bridge.checkout_regions(**checkout_kwargs)
    first_id = first["lease"]["checkout"]["lease_id"]
    first_checkout = first["lease"]["checkout"]

    identity = _verified_codex_identity()
    identity["watcher_lease_generation"] = "lease:thread-interface:2"
    proof = {
        "schema_version": "laplace.startup-mail-gate/1",
        "seat_id": "sensorium-seat",
        "goal": "renew the same task under a fresh provider generation",
        "state": "MAIL_READY",
        "observed_at": "2026-08-27T12:30:00+00:00",
        "delivered": [],
        "provider_identity": identity,
    }
    proof_handle = bridge._blobs().put(
        (bridge.canonical_json(proof) + "\n").encode("utf-8")
    )
    packet = _direct_renewal_packet(
        proof_handle=proof_handle,
        provider_identity_generation="lease:thread-interface:2",
    )
    bridge._store().append_many(packet)

    hot = bridge.region_leases(as_of="2026-08-27T13:00:00Z")["leases"][first_id]
    assert hot["checkout"] == first_checkout
    assert hot["effective_state"] == "DISPLACED"
    assert hot["write_authority"] is False
    with pytest.raises(StateTransitionRefused, match="closed, or displaced"):
        bridge.checkout_regions(**checkout_kwargs)
    with pytest.raises(StateTransitionRefused, match="latest seat occupancy lineage"):
        bridge.checkin_regions(
            lease_id=first_id,
            seat_id="sensorium-seat",
            holder_ref="codex:thread-interface",
            function="sensorium",
            outcome="noop",
            evidence={"focused_tests": "sha256:" + ("f" * 64)},
            provider=PROVIDER,
            model=MODEL,
        )
    with pytest.raises(
        StateTransitionRefused,
        match="PREPARED, triad-SIGNED, and AUTHORIZED",
    ):
        bridge.publish_regions(
            lease_id=first_id,
            seat_id="sensorium-seat",
            holder_ref="codex:thread-interface",
            function="sensorium",
            message="must refuse before Git access",
            evidence={"focused_tests": "sha256:" + ("f" * 64)},
            provider=PROVIDER,
            model=MODEL,
        )

    successor = bridge.checkout_regions(
        **{
            **checkout_kwargs,
            "act_id": "interface-generation-two",
            "declaration_ref": "test:interface-generation-two",
        }
    )
    assert successor["lease"]["effective_state"] == "ACTIVE"
    assert successor["lease"]["write_authority"] is True

    cold = bridge._store().replay()
    cold_first = bridge._project_region_lease(
        cold.region_leases[first_id],
        "2026-08-27T13:00:00Z",
        state=cold,
    )
    assert cold_first["checkout"] == first_checkout
    assert cold_first["effective_state"] == "DISPLACED"
    assert cold_first["write_authority"] is False


def test_expired_checkout_replay_cannot_revive_authority_after_replacement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bootstrap()
    _join_sensorium(monkeypatch)
    now = ["2026-08-26T12:00:00Z"]
    monkeypatch.setattr(bridge, "_now", lambda: now[0])
    monkeypatch.setattr(bridge, "_git_head", lambda: "a" * 40)
    monkeypatch.setattr(bridge, "_git_dirty_paths", lambda: ())
    kwargs = dict(
        seat_id="sensorium-seat",
        holder_ref="codex:thread-interface",
        function="sensorium",
        act_id="expiring-interface-act",
        regions=("src/laplace/conjugate_interface.py",),
        expires_at="2026-08-26T13:00:00Z",
        declaration_kind="native",
        declaration_ref="contract/journal.jsonl#expiring-interface-act",
        bootstrap_crutch=None,
        provider=PROVIDER,
        model=MODEL,
    )
    expired = bridge.checkout_regions(**kwargs)
    now[0] = "2026-08-26T14:00:00Z"
    replacement = bridge.checkout_regions(
        **{
            **kwargs,
            "act_id": "replacement-interface-act",
            "expires_at": "2026-08-26T16:00:00Z",
            "declaration_ref": "contract/journal.jsonl#replacement-interface-act",
        }
    )

    assert replacement["lease"]["write_authority"] is True
    with pytest.raises(StateTransitionRefused, match="cannot revive"):
        bridge.checkout_regions(**kwargs)
    expired_id = expired["lease"]["checkout"]["lease_id"]
    served = bridge.region_leases(as_of=now[0])["leases"][expired_id]
    assert served["effective_state"] == "EXPIRED"
    assert served["write_authority"] is False


def test_checkout_refuses_prohibited_roots_before_git_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bootstrap()
    _join_sensorium(monkeypatch)
    git_read = False

    def head() -> str:
        nonlocal git_read
        git_read = True
        return "a" * 40

    monkeypatch.setattr(bridge, "_git_head", head)
    for region in (".git", ".git/objects", "soul", "soul/private"):
        with pytest.raises(StateTransitionRefused, match="no delegated seat may mutate"):
            bridge.checkout_regions(
                seat_id="sensorium-seat",
                holder_ref="codex:thread-interface",
                function="sensorium",
                act_id=f"prohibited-{region}",
                regions=(region,),
                expires_at="2036-08-27T12:00:00Z",
                declaration_kind="native",
                declaration_ref=f"test:{region}",
                bootstrap_crutch=None,
                provider=PROVIDER,
                model=MODEL,
            )
    assert git_read is False


def test_successful_checkin_requires_ancestry_before_delta_attribution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bootstrap()
    _join_sensorium(monkeypatch)
    heads = iter(("a" * 40, "b" * 40))
    monkeypatch.setattr(bridge, "_git_head", lambda: next(heads))
    monkeypatch.setattr(bridge, "_git_dirty_paths", lambda: ())
    monkeypatch.setattr(bridge, "_git_is_ancestor", lambda base, result: False)
    attribution_called = False

    def attribution(**kwargs):
        nonlocal attribution_called
        attribution_called = True
        return {}

    monkeypatch.setattr(bridge, "_git_holder_attribution", attribution)
    checkout = bridge.checkout_regions(
        seat_id="sensorium-seat",
        holder_ref="codex:thread-interface",
        function="sensorium",
        act_id="non-ancestor-checkin",
        regions=("src/laplace/conjugate_interface.py",),
        expires_at="2036-08-27T12:00:00Z",
        declaration_kind="native",
        declaration_ref="test:non-ancestor",
        bootstrap_crutch=None,
        provider=PROVIDER,
        model=MODEL,
    )

    with pytest.raises(StateTransitionRefused, match="requires result HEAD to descend"):
        bridge.checkin_regions(
            lease_id=checkout["lease"]["checkout"]["lease_id"],
            seat_id="sensorium-seat",
            holder_ref="codex:thread-interface",
            function="sensorium",
            outcome="committed",
            evidence={"focused_tests": "sha256:" + ("f" * 64)},
            provider=PROVIDER,
            model=MODEL,
        )
    assert attribution_called is False


def test_checkin_refuses_unattributed_in_scope_git_delta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bootstrap()
    _join_sensorium(monkeypatch)
    heads = iter(("a" * 40, "b" * 40))
    monkeypatch.setattr(bridge, "_git_head", lambda: next(heads))
    monkeypatch.setattr(bridge, "_git_dirty_paths", lambda: ())
    monkeypatch.setattr(bridge, "_git_is_ancestor", lambda base, result: True)
    monkeypatch.setattr(
        bridge,
        "_git_changed_paths",
        lambda base, result: ("src/laplace/conjugate_interface.py",),
    )
    monkeypatch.setattr(
        bridge,
        "_git_holder_attribution",
        lambda **kwargs: {
            "schema_version": "laplace.git-holder-attribution/1",
            "lease_id": kwargs["lease_id"],
            "holder_ref": kwargs["holder_ref"],
            "attributed_commits": [],
            "attributed_paths": [],
            "unattributed_paths": ["src/laplace/conjugate_interface.py"],
            "required_trailers": {
                "Laplace-Lease": kwargs["lease_id"],
                "Laplace-Holder": kwargs["holder_ref"],
            },
        },
    )
    checkout = bridge.checkout_regions(
        seat_id="sensorium-seat",
        holder_ref="codex:thread-interface",
        function="sensorium",
        act_id="unattributed-checkin",
        regions=("src/laplace/conjugate_interface.py",),
        expires_at="2036-08-27T12:00:00Z",
        declaration_kind="native",
        declaration_ref="test:unattributed",
        bootstrap_crutch=None,
        provider=PROVIDER,
        model=MODEL,
    )

    with pytest.raises(StateTransitionRefused, match="not attributable"):
        bridge.checkin_regions(
            lease_id=checkout["lease"]["checkout"]["lease_id"],
            seat_id="sensorium-seat",
            holder_ref="codex:thread-interface",
            function="sensorium",
            outcome="committed",
            evidence={"focused_tests": "sha256:" + ("f" * 64)},
            provider=PROVIDER,
            model=MODEL,
        )


def test_native_checkout_refuses_dirt_but_bootstrap_names_it_and_its_retirement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bootstrap()
    _join_sensorium(monkeypatch)
    monkeypatch.setattr(bridge, "_git_head", lambda: "a" * 40)
    monkeypatch.setattr(
        bridge,
        "_git_dirty_paths",
        lambda: ("src/laplace/conjugate_interface.py",),
    )
    kwargs = dict(
        seat_id="sensorium-seat",
        holder_ref="codex:thread-interface",
        function="sensorium",
        act_id="interface-act-bootstrap",
        regions=("src/laplace/conjugate_interface.py",),
        expires_at="2036-08-27T12:00:00Z",
        declaration_ref="contract/journal.jsonl#interface-act-bootstrap",
        provider=PROVIDER,
        model=MODEL,
    )

    with pytest.raises(StateTransitionRefused, match="pre-existing worktree dirt"):
        bridge.checkout_regions(
            **kwargs,
            declaration_kind="native",
            bootstrap_crutch=None,
        )

    bootstrapped = bridge.checkout_regions(
        **kwargs,
        declaration_kind="journal-bootstrap",
        bootstrap_crutch={
            "schema_version": "bootstrap-crutch/1",
            "crutch_id": "CR-bootstrap-lease-snapshot",
            "what": "cold-start journal lease snapshot",
            "why_now": "pre-lease act is already in flight",
            "must_become": "native checkout before mutation",
            "retirement_trigger": "native-successful-checkins>=3",
            "owner": "ego",
        },
    )

    checkout = bootstrapped["lease"]["checkout"]
    assert checkout["preexisting_dirty_paths"] == [
        "src/laplace/conjugate_interface.py"
    ]
    assert checkout["bootstrap_crutch"]["retirement_trigger"] == (
        "native-successful-checkins>=3"
    )


def test_provider_observation_skips_materialization_until_tip_moves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = {
        "schema_version": "atlas.conceptric-drift-token/1",
        "cursor": 7,
        "head_event_id": "event:7",
        "head_record_digest": "digest:7",
    }
    monkeypatch.setattr(bridge, "drift_token", lambda: dict(token))

    class RefuseMaterialization:
        @staticmethod
        def provider_snapshot():
            raise AssertionError("an unchanged watcher poll must not materialize Atlas")

    monkeypatch.setattr(bridge, "_read_store", lambda: RefuseMaterialization())

    observed = bridge.provider_observation(previous_token=token)

    assert observed["changed"] is False
    assert observed["provider"] is None
    assert observed["materialization_attempts"] == 0


def test_provider_observation_retries_if_writer_crosses_materialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tokens = iter([
        {"cursor": 7, "head_event_id": "event:7", "head_record_digest": "digest:7"},
        {"cursor": 8, "head_event_id": "event:8", "head_record_digest": "digest:8"},
        {"cursor": 8, "head_event_id": "event:8", "head_record_digest": "digest:8"},
    ])
    monkeypatch.setattr(bridge, "drift_token", lambda: next(tokens))
    snapshots = iter([{"head": 7}, {"head": 8}])

    class MovingStore:
        @staticmethod
        def provider_snapshot():
            return next(snapshots)

    monkeypatch.setattr(bridge, "_read_store", lambda: MovingStore())

    observed = bridge.provider_observation()

    assert observed["changed"] is True
    assert observed["provider"] == {"head": 8}
    assert observed["drift_token"]["cursor"] == 8
    assert observed["materialization_attempts"] == 2


def test_provider_observation_refuses_a_projection_while_tip_never_stabilizes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cursor = 0

    def moving_token():
        nonlocal cursor
        cursor += 1
        return {
            "cursor": cursor,
            "head_event_id": f"event:{cursor}",
            "head_record_digest": f"digest:{cursor}",
        }

    class MovingStore:
        @staticmethod
        def provider_snapshot():
            return {"must": "not escape under a moving token"}

    monkeypatch.setattr(bridge, "drift_token", moving_token)
    monkeypatch.setattr(bridge, "_read_store", lambda: MovingStore())

    with pytest.raises(StoreError, match="no stable projection was cached"):
        bridge.provider_observation(max_attempts=2)


def test_seat_mail_observation_ignores_unrelated_atlas_drift() -> None:
    _bootstrap()
    sent = bridge.send(
        sender_seat_id="claude-seat",
        recipient_seat_id="codex-seat",
        message_type="recipient-local-delta",
        body="Only this recipient frontier should move.",
        dependency_roots={"contract": "atlas.seat-mail-frontier.v1"},
        idempotency_key="recipient-local-delta:1",
        expires_at=EXPIRES,
        provider=PROVIDER,
        model=MODEL,
    )

    first = bridge.seat_mail_observation(
        seat_id="codex-seat", previous_mail_token=None
    )
    bridge.send(
        sender_seat_id="codex-seat",
        recipient_seat_id="claude-seat",
        message_type="other-recipient-delta",
        body="This must not move the codex-seat frontier.",
        dependency_roots={"contract": "atlas.seat-mail-frontier.v1"},
        idempotency_key="other-recipient-delta:1",
        expires_at=EXPIRES,
        provider=PROVIDER,
        model=MODEL,
    )
    second = bridge.seat_mail_observation(
        seat_id="codex-seat", previous_mail_token=first["mail_token"]
    )

    assert first["changed"] is True
    assert [row["message_id"] for row in first["pending_messages"]] == [
        sent["message_id"]
    ]
    assert first["read_metrics"]["provider_snapshot_materialized"] is False
    assert second["changed"] is False
    assert second["pending_messages"] is None
    assert second["read_metrics"]["rows_loaded"] == 0
    assert second["drift_token"]["cursor"] > first["drift_token"]["cursor"]
    assert second["mail_token"] == first["mail_token"]


def test_seat_mail_observation_retains_pulled_nonterminal_obligation() -> None:
    _bootstrap()
    bridge.send(
        sender_seat_id="claude-seat",
        recipient_seat_id="codex-seat",
        message_type="recipient-local-pull",
        body="Pulling this should empty only the codex frontier.",
        dependency_roots={"contract": "atlas.seat-mail-frontier.v1"},
        idempotency_key="recipient-local-pull:1",
        expires_at=EXPIRES,
        provider=PROVIDER,
        model=MODEL,
    )
    before = bridge.seat_mail_observation(
        seat_id="codex-seat", previous_mail_token=None
    )

    bridge.pull(
        seat_id="codex-seat",
        as_of="2026-08-24T15:00:00Z",
        provider=PROVIDER,
        model=MODEL,
    )
    after = bridge.seat_mail_observation(
        seat_id="codex-seat", previous_mail_token=before["mail_token"]
    )

    assert after["changed"] is True
    assert after["mail_token"] != before["mail_token"]
    assert len(after["pending_messages"]) == 1
    assert after["pending_messages"][0]["status"] == "pulled"
    assert after["pending_count"] == 1
    assert after["pending_tip_cursor"] == before["pending_tip_cursor"]


def test_seat_mail_observation_ignores_disposable_projection_poison() -> None:
    _bootstrap()
    bridge.send(
        sender_seat_id="claude-seat",
        recipient_seat_id="codex-seat",
        message_type="mail-projection-poison",
        body="The read path must refuse a forged projection receipt.",
        dependency_roots={"contract": "atlas.seat-mail-frontier.v1"},
        idempotency_key="mail-projection-poison:1",
        expires_at=EXPIRES,
        provider=PROVIDER,
        model=MODEL,
    )
    store = bridge._store()
    with store._connect_projection() as projection:
        projection.execute(
            "UPDATE meta SET value = ? WHERE key = 'seat_mail_head_digest'",
            ("sha256:" + "0" * 64,),
        )
        projection.commit()

    observed = bridge.seat_mail_observation(
        seat_id="codex-seat", previous_mail_token=None
    )
    assert observed["status"] == "CURRENT"
    assert observed["pending_count"] == 1
    assert observed["fidelity_boundary"]["status"] == "CHECKSUMMED-CRUTCH"


def test_authority_epoch_exposes_stopped_writer_predecessor_and_candidate() -> None:
    _bootstrap()

    fast = bridge.authority_epoch()
    deep = bridge.inspect_authority_epoch()

    assert fast["integrity_boundary"]["status"] == "CHECKSUMMED-CRUTCH"
    assert deep["status"] == "EXACT"
    assert deep["integrity_boundary"] == "CHECKSUMMED-CRUTCH"
    assert deep["verified_predecessor"] == fast["anchor_checkpoint_digest"]
    assert deep["candidate_checkpoint_digest"] == fast["effective_checkpoint_digest"]
    assert deep["event_append"] is False


def test_exact_region_lease_and_graph_object_share_current_c2a_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repo, lease_id = _publication_checkout(tmp_path, monkeypatch)

    lease = bridge.atlas_object(reference=lease_id)
    graph = bridge.atlas_object(reference=f"lease:{lease_id}")
    verified = bridge.verify_atlas_object_current_root(
        reference=lease_id,
        expected_current_root=lease["current_root"],
    )

    assert lease["reference_kind"] == "region-lease"
    assert lease["integrity_boundary"] == "CHECKSUMMED-CRUTCH"
    assert lease["authenticated"] is False
    assert lease["current"] is True
    assert lease["clean"] is True
    assert lease["value"]["checkout"]["lease_id"] == lease_id
    assert lease["authority_root_kind"] == "atlas.keyed-region-lease-proof/1"
    assert lease["read_metrics"]["projection_rows_loaded"] == 1
    assert lease["provenance"]["writer_authority_checkpoint_used"] is False
    assert lease["read_metrics"]["global_history_replayed"] is False
    assert lease["fidelity_boundary"]["sidecar_residual"] is None
    assert graph["reference_kind"] == "graph-object"
    assert graph["integrity_boundary"] == "CHECKSUMMED-CRUTCH"
    assert graph["authenticated"] is False
    assert graph["value"]["object_id"] == f"lease:{lease_id}"
    assert graph["value"]["kind"] == "repository-region-lease"
    assert graph["fidelity_boundary"]["sidecar_residual"] == (
        "sidecar-duplicate-nonleaf"
    )
    assert verified["status"] == "CURRENT"
    assert verified["integrity_boundary"] == "CHECKSUMMED-CRUTCH"
    assert verified["authenticated"] is False
    assert verified["current_root"] == lease["current_root"]
    assert verified["read_only"] is True
    assert verified["transition_claim"] == "none"
    assert verified["authority_write"] == "none"


def test_projection_transition_rebuilds_before_reader_without_moving_authority() -> None:
    _bootstrap()
    bridge.send(
        sender_seat_id="claude-seat",
        recipient_seat_id="codex-seat",
        message_type="schema-transition",
        body="The disposable projection may rebuild; the ledger must not move.",
        dependency_roots={"contract": "atlas.seat-mail-frontier.v1"},
        idempotency_key="schema-transition:1",
        expires_at=EXPIRES,
        provider=PROVIDER,
        model=MODEL,
    )
    store = bridge._store()
    before = bridge.drift_token()
    with store._connect_projection() as projection:
        projection.execute(
            "DELETE FROM meta WHERE key IN "
            "('seat_mail_projection_schema', 'seat_mail_head_digest')"
        )
        projection.commit()

    prepared = bridge.prepare_seat_mail_projection()
    after = bridge.drift_token()
    observed = bridge.seat_mail_observation(
        seat_id="codex-seat", previous_mail_token=None
    )

    assert prepared["status"] == "READY"
    assert prepared["reader_activation_allowed"] is True
    assert prepared["authority_write"] is False
    assert before == after
    assert observed["status"] == "CURRENT"


def test_projection_transition_repairs_a_forged_seat_revision_token() -> None:
    _bootstrap()
    bridge.send(
        sender_seat_id="claude-seat",
        recipient_seat_id="codex-seat",
        message_type="revision-token-poison",
        body="The recipient token must be reconstructed from exact event order.",
        dependency_roots={"contract": "atlas.seat-mail-frontier.v1"},
        idempotency_key="revision-token-poison:1",
        expires_at=EXPIRES,
        provider=PROVIDER,
        model=MODEL,
    )
    store = bridge._store()
    before = bridge.seat_mail_observation(
        seat_id="codex-seat", previous_mail_token=None
    )
    with store._connect() as ledger:
        planted = ledger.execute(
            "SELECT sequence, event_id FROM events WHERE sequence < ? "
            "ORDER BY sequence LIMIT 1",
            (before["mail_token"]["revision_cursor"],),
        ).fetchone()
    assert planted is not None
    with store._connect_projection() as projection:
        projection.execute(
            "UPDATE seat_mail_frontiers SET revision_cursor = ?, "
            "revision_event_id = ? WHERE seat_id = ?",
            (int(planted["sequence"]), str(planted["event_id"]), "codex-seat"),
        )
        projection.commit()

    prepared = bridge.prepare_seat_mail_projection()
    after = bridge.seat_mail_observation(
        seat_id="codex-seat", previous_mail_token=None
    )

    assert prepared["status"] == "READY"
    assert after["mail_token"] == before["mail_token"]


def test_two_seat_checkpoint_reconstruction_does_not_reactivate_attention(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from laplace.representation import codex_seat_watcher as watcher

    _bootstrap()
    current_digest = "sha256:checkpoint-current"

    def runtime_for(seat_id=watcher.DEFAULT_SEAT_ID):
        return tmp_path / "runtime" / seat_id

    monkeypatch.setattr(watcher, "_runtime_dir", runtime_for)
    seats = ("ego-seat", "superego-seat")
    tokens = {}
    for index, seat_id in enumerate(seats, start=1):
        root = runtime_for(seat_id)
        root.mkdir(parents=True)
        target = {
            "thread_id": f"thread-{seat_id}",
            "seat_id": seat_id,
            "bound_at": f"2026-08-26T12:00:0{index}+00:00",
            "baseline_pending_tip": 0,
            "baseline_pending_count": 0,
            "baseline_mail_revision": 0,
            "expected_interval_seconds": 5.0,
        }
        generation = watcher._lease_generation(target, seat_id)
        token = watcher._new_wake_token(
            seat_id=seat_id,
            thread_id=target["thread_id"],
            lease_generation=generation,
            pending_tip=1,
            mail_revision=1,
        )
        token["transport_state"] = "QUEUED_UNRECEIPTED"
        tokens[seat_id] = (target, token)
        (root / "target.json").write_text(json.dumps(target), encoding="utf-8")
        (root / "status.json").write_text(json.dumps({
            "thread_id": target["thread_id"],
            "seat_id": seat_id,
            "lease_generation": generation,
            "implementation_digest": current_digest,
            "covered_pending_tip": 0,
            "covered_mail_revision": 0,
            "wake_token": token,
        }), encoding="utf-8")

    def consume(seat_id):
        target, token = tokens[seat_id]
        return watcher.consume_wake_token(
            seat_id=seat_id,
            thread_id=target["thread_id"],
            token=token["token"],
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = dict(zip(seats, pool.map(consume, seats), strict=True))

    authority = {
        (
            receipt["authority_cursor"],
            receipt["head_event_id"],
            receipt["head_record_digest"],
        )
        for receipt in receipts.values()
    }
    assert len(authority) == 1
    assert all(receipt["pending_count"] == 0 for receipt in receipts.values())
    for seat_id in seats:
        target, token = tokens[seat_id]
        resumed = watcher._resumed_wake_state(
            target,
            {
                "thread_id": target["thread_id"],
                "lease_generation": watcher._lease_generation(target, seat_id),
                "implementation_digest": current_digest,
                "covered_pending_tip": 0,
                "covered_mail_revision": 0,
                "wake_token": token,
            },
            seat_id=seat_id,
            implementation_digest=current_digest,
            consumption=receipts[seat_id],
        )
        assert resumed == (None, 0, 0)

    old_prompt = (
        "[Eigen Fabric watcher] stale message:" + "a" * 64
    )
    assert watcher.classify_attention_prompt(old_prompt) == "LEGACY-INERT"
    for seat_id in seats:
        first = bridge.seat_mail_observation(
            seat_id=seat_id, previous_mail_token=None
        )
        idle = bridge.seat_mail_observation(
            seat_id=seat_id, previous_mail_token=first["mail_token"]
        )
        assert idle["changed"] is False
        assert idle["read_metrics"]["rows_loaded"] == 0
        assert idle["read_metrics"]["history_replayed"] is False
        assert idle["read_metrics"]["provider_snapshot_materialized"] is False
        assert idle["read_metrics"]["cpu_ns"] < 50_000_000


def test_message_send_uses_verified_current_state_without_full_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bootstrap()
    store = bridge._store()

    def refuse_full_replay():
        raise AssertionError("one bridge append must not replay the lifetime of the Atlas")

    monkeypatch.setattr(store, "replay", refuse_full_replay)
    sent = bridge.send(
        sender_seat_id="codex-seat",
        recipient_seat_id="claude-seat",
        message_type="cost-probe",
        body="The operational bridge folds only a verified causal suffix.",
        dependency_roots={"contract": "atlas.seat-bridge.v1"},
        idempotency_key="verified-current-state:1",
        expires_at=EXPIRES,
        provider=PROVIDER,
        model=MODEL,
    )

    assert sent["status"]["status"] == "queued"


def test_message_send_refuses_a_forged_body_dependency_root() -> None:
    _bootstrap()

    with pytest.raises(StateTransitionRefused, match="body dependency root disagrees"):
        bridge.send(
            sender_seat_id="codex-seat",
            recipient_seat_id="claude-seat",
            message_type="forged-body-root",
            body="the body and its root must be one object",
            dependency_roots={"body": "sha256:" + ("0" * 64)},
            idempotency_key="forged-body-root:1",
            expires_at=EXPIRES,
            provider=PROVIDER,
            model=MODEL,
        )


def test_message_send_keeps_append_proof_when_status_readback_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bootstrap()
    store = bridge._store()

    def fail_after_append(_message_id: str):
        raise RuntimeError("planted status read failure after durable append")

    monkeypatch.setattr(store, "message_status", fail_after_append)
    sent = bridge.send(
        sender_seat_id="codex-seat",
        recipient_seat_id="claude-seat",
        message_type="post-append-readback-attack",
        body="the append receipt must survive its neighbouring read failure",
        dependency_roots={"finding": "FIND-unreached-can-name-reached"},
        idempotency_key="post-append-readback-attack:1",
        expires_at=EXPIRES,
        provider=PROVIDER,
        model=MODEL,
    )

    assert sent["receipt"]["kind"] == "seat.message-sent"
    assert sent["status"] is None
    assert sent["status_observation"] == {
        "state": "unknown-after-append",
        "error": {
            "type": "RuntimeError",
            "message": "planted status read failure after durable append",
        },
        "append_proof": sent["receipt"]["event_id"],
    }
    assert sent["message_id"] in store.current_state().messages


def test_message_send_retries_only_named_preappend_lock_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[dict[str, object]] = []

    def contended_once(**arguments):
        attempts.append(arguments)
        if len(attempts) == 1:
            raise StoreLockTimeout("planted pre-append contention")
        return {"status": "queued", "idempotency_key": arguments["idempotency_key"]}

    monkeypatch.setattr(bridge, "_send_once", contended_once)
    sent = bridge.send(
        sender_seat_id="codex-seat",
        recipient_seat_id="claude-seat",
        message_type="contention-retry-proof",
        body="same bytes on both attempts",
        dependency_roots={"finding": "FIND-LOCK-CONTENTION"},
        idempotency_key="contention-retry:1",
        expires_at=EXPIRES,
        provider=PROVIDER,
        model=MODEL,
    )

    assert sent == {"status": "queued", "idempotency_key": "contention-retry:1"}
    assert len(attempts) == 2
    assert attempts[0] == attempts[1]

    attempts.clear()

    def ambiguous_store_failure(**arguments):
        attempts.append(arguments)
        raise StoreError("planted ambiguous failure")

    monkeypatch.setattr(bridge, "_send_once", ambiguous_store_failure)
    with pytest.raises(StoreError, match="ambiguous failure"):
        bridge.send(
            sender_seat_id="codex-seat",
            recipient_seat_id="claude-seat",
            message_type="must-not-retry",
            body="one attempt only",
            dependency_roots={},
            idempotency_key="contention-retry:2",
            expires_at=EXPIRES,
            provider=PROVIDER,
            model=MODEL,
        )
    assert len(attempts) == 1


def test_runtime_custody_export_reconstructs_without_mutating_live_authority(
    tmp_path: Path,
) -> None:
    _bootstrap()
    unattached = bridge.put_custody(b"an exact custody object awaiting a later edge")
    sent = bridge.send(
        sender_seat_id="codex-seat",
        recipient_seat_id="claude-seat",
        message_type="custody-export-test",
        body="the exported fabric must still resolve this exact body",
        dependency_roots={"unattached_custody": unattached},
        idempotency_key="runtime-custody-export:1",
        expires_at=EXPIRES,
        provider=PROVIDER,
        model=MODEL,
    )
    before = bridge.drift_token()
    destination = tmp_path / "chosen-custody" / "snapshot-1"

    exported = bridge.export_runtime_custody(destination=destination)

    assert bridge.drift_token() == before
    assert exported["status"] == "verified"
    assert exported["published"] is True
    assert exported["storage_separation"] == "same-filesystem-mitigation-only"
    assert exported["off_machine_state"].startswith("unknown")
    assert exported["event_count"] == before["cursor"]
    assert bridge.BlobStore(destination / "blobs").get(
        sent["body_handle"]
    ).decode() == "the exported fabric must still resolve this exact body"
    assert bridge.BlobStore(destination / "blobs").get(unattached).startswith(
        b"an exact custody object"
    )
    before_verify = sorted(
        path.relative_to(destination).as_posix()
        for path in destination.rglob("*")
        if path.is_file()
    )
    assert bridge.verify_runtime_custody(destination)["snapshot_id"] == exported[
        "snapshot_id"
    ]
    after_verify = sorted(
        path.relative_to(destination).as_posix()
        for path in destination.rglob("*")
        if path.is_file()
    )
    assert after_verify == before_verify
    assert not (destination / "conceptric.sqlite3-wal").exists()
    assert not (destination / "conceptric.sqlite3-shm").exists()
    with pytest.raises(Exception, match="never overwrite"):
        bridge.export_runtime_custody(destination=destination)
    bridge.BlobStore(destination / "blobs").key_path(sent["body_handle"]).write_bytes(
        b"poisoned after export"
    )
    with pytest.raises(BlobHashMismatch):
        bridge.verify_runtime_custody(destination)


def _write_runtime_body_residual_declaration(
    path: Path,
    rows: list[dict[str, object]],
) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": bridge.RUNTIME_MESSAGE_BODY_RESIDUAL_DECLARATION_SCHEMA,
                "authorization": {
                    "mode": "exact-frozen-legacy-set",
                    "author": "Gerard",
                    "ruling_date": "2026-08-27",
                    "ruling_task_id": "test:runtime-custody-residual",
                    "ruling": "Admit only this exact historical terminal-refusal fixture.",
                    "authorized_treatment": (
                        "No fabricated bytes or events; live completeness remains strict."
                    ),
                },
                "historical_unavailable": rows,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _refused_message_without_body(*, suffix: str) -> tuple[dict, dict[str, object]]:
    sent = bridge.send(
        sender_seat_id="codex-seat",
        recipient_seat_id="claude-seat",
        message_type="historical-custody-residual",
        body=f"irrecoverable historical test bytes {suffix}",
        dependency_roots={"fixture": suffix},
        idempotency_key=f"runtime-custody-residual:{suffix}",
        expires_at=EXPIRES,
        provider=PROVIDER,
        model=MODEL,
    )
    bridge.acknowledge(
        message_id=sent["message_id"],
        seat_id="claude-seat",
        disposition="refused",
        note="terminal legacy refusal before body loss",
        provider="claude",
        model="claude",
    )
    state = bridge._read_store().current_state()
    row = bridge._historical_unavailable_row(
        state=state,
        message_id=sent["message_id"],
    )
    bridge.BlobStore(bridge.store_root() / "blobs").key_path(
        sent["body_handle"]
    ).unlink()
    return sent, row


def test_runtime_custody_residual_is_exact_explicit_and_identity_bound(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bootstrap()
    sent, row = _refused_message_without_body(suffix="one")
    declaration = tmp_path / "declaration.json"
    _write_runtime_body_residual_declaration(declaration, [row])
    monkeypatch.setattr(
        bridge,
        "RUNTIME_CUSTODY_RESIDUAL_DECLARATION",
        declaration,
    )

    strict_destination = tmp_path / "strict-refusal"
    with pytest.raises(StoreError, match="missing message bodies"):
        bridge.export_runtime_custody(destination=strict_destination)
    assert not strict_destination.exists()

    destination = tmp_path / "declared-residual"
    exported = bridge.export_runtime_custody(
        destination=destination,
        admit_declared_historical_unavailable=True,
    )

    assert exported["historical_unavailable_message_count"] == 1
    receipt = json.loads((destination / "RECEIPT.json").read_text(encoding="utf-8"))
    residual = receipt["message_body_custody"]
    assert residual["historical_unavailable"] == [row]
    assert residual["authorization"]["mode"] == "exact-frozen-legacy-set"
    assert residual["complete_relation_root"] == exported[
        "complete_message_body_relation_root"
    ]
    assert not bridge.BlobStore(destination / "blobs").has(sent["body_handle"])
    assert bridge.verify_runtime_custody(destination)["snapshot_id"] == exported[
        "snapshot_id"
    ]

    copied_declaration = destination / bridge._RUNTIME_CUSTODY_RESIDUAL_NAME
    tampered = json.loads(copied_declaration.read_text(encoding="utf-8"))
    tampered["historical_unavailable"][0]["body_handle"] = "sha256:" + "f" * 64
    copied_declaration.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(StoreError, match="author-ratified set|subreceipt"):
        bridge.verify_runtime_custody(destination)


def test_runtime_custody_residual_refuses_an_undeclared_missing_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bootstrap()
    _first, declared = _refused_message_without_body(suffix="declared")
    _second, _undeclared = _refused_message_without_body(suffix="undeclared")
    declaration = tmp_path / "declaration.json"
    _write_runtime_body_residual_declaration(declaration, [declared])
    monkeypatch.setattr(
        bridge,
        "RUNTIME_CUSTODY_RESIDUAL_DECLARATION",
        declaration,
    )

    with pytest.raises(StoreError, match="do not equal the authorized legacy set"):
        bridge.export_runtime_custody(
            destination=tmp_path / "must-refuse",
            admit_declared_historical_unavailable=True,
        )


def test_runtime_custody_residual_never_admits_a_nonterminal_missing_body(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bootstrap()
    sent = bridge.send(
        sender_seat_id="codex-seat",
        recipient_seat_id="claude-seat",
        message_type="current-obligation",
        body="a live obligation cannot become historical residue",
        dependency_roots={"fixture": "nonterminal"},
        idempotency_key="runtime-custody-residual:nonterminal",
        expires_at=EXPIRES,
        provider=PROVIDER,
        model=MODEL,
    )
    state = bridge._read_store().current_state()
    row = bridge._historical_unavailable_row(
        state=state,
        message_id=sent["message_id"],
    )
    bridge.BlobStore(bridge.store_root() / "blobs").key_path(
        sent["body_handle"]
    ).unlink()
    declaration = tmp_path / "declaration.json"
    _write_runtime_body_residual_declaration(declaration, [row])
    monkeypatch.setattr(
        bridge,
        "RUNTIME_CUSTODY_RESIDUAL_DECLARATION",
        declaration,
    )

    with pytest.raises(StoreError, match="not terminal REFUSED"):
        bridge.export_runtime_custody(
            destination=tmp_path / "must-refuse-nonterminal",
            admit_declared_historical_unavailable=True,
        )


def test_runtime_custody_capture_refuses_blob_generation_movement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bootstrap()
    bridge.put_custody(b"stable generation witness")
    source_blobs = (bridge.store_root() / "blobs").resolve()
    original = bridge._canonical_blob_handles
    source_calls = 0

    def moving_manifest(root: Path):
        nonlocal source_calls
        result = original(root)
        if root.resolve() == source_blobs:
            source_calls += 1
            if source_calls == 2:
                return result[0] + ("sha256:" + "f" * 64,), result[1]
        return result

    monkeypatch.setattr(bridge, "_canonical_blob_handles", moving_manifest)
    destination = tmp_path / "moving-source"
    with pytest.raises(StoreError, match="source generation moved"):
        bridge.export_runtime_custody(destination=destination)
    assert not destination.exists()


def test_runtime_custody_v2_offline_point_and_filesystem_refusals(
    tmp_path: Path,
) -> None:
    from laplace.representation.recovery_coordinate import runtime_recovery_point_from_capsule, verify_runtime_recovery_point

    _bootstrap()
    capsule = tmp_path / "portable-capsule"
    exported = bridge.export_runtime_custody(destination=capsule)
    point = runtime_recovery_point_from_capsule(capsule)

    offline = verify_runtime_recovery_point(point, capsule)
    assert offline["status"] == "EXACT"
    assert offline["source_snapshot_id"] == exported["snapshot_id"]
    assert offline["authenticated"] is False

    extra = capsule / "not-allowlisted.txt"
    extra.write_text("unexpected", encoding="utf-8")
    with pytest.raises(StoreError, match="extra file"):
        bridge.verify_runtime_custody(capsule)
    extra.unlink()

    symlink = capsule / "blobs-link"
    symlink.symlink_to(capsule / "blobs", target_is_directory=True)
    with pytest.raises(StoreError, match="symlink"):
        bridge.verify_runtime_custody(capsule)
    symlink.unlink()

    hardlink = capsule / "hive-migration-receipt.json"
    os.link(capsule / "conceptric.sqlite3", hardlink)
    with pytest.raises(StoreError, match="hard-linked"):
        bridge.verify_runtime_custody(capsule)
    hardlink.unlink()

    wal = capsule / "conceptric.sqlite3-wal"
    wal.write_bytes(b"not a WAL")
    with pytest.raises(StoreError, match="SQLite sidecar"):
        bridge.verify_runtime_custody(capsule)
    wal.unlink()


def test_runtime_custody_committed_external_grant_and_crash_boundaries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laplace.representation import recovery_coordinate as recovery

    _bootstrap()
    capsule = tmp_path / "portable-source"
    exported = bridge.export_runtime_custody(destination=capsule)
    point = recovery.runtime_recovery_point_from_capsule(capsule)
    anchor = {
        "schema_version": "laplace.runtime-recovery-coordinate-grant/1",
        "point_root": point["point_root"],
        "source_snapshot_id": point["source_snapshot_id"],
        "source_checkpoint_digest": point["source_checkpoint"]["checkpoint_digest"],
        "predecessor_coordinate_payload_digest": point[
            "source_recovery_coordinate_payload_digest"
        ],
        "target_store_role": "live-runtime-fabric",
    }
    anchor["grant_anchor_root"] = bridge.chash(anchor)
    coordinate = {
        "schema_version": "atlas.recovery-coordinate/2",
        "runtime_recovery_point": point,
        "runtime_recovery_grant": anchor,
    }
    coordinate["coordinate_payload_digest"] = recovery.canonical_payload_digest(
        coordinate
    )
    coordinate_raw = (json.dumps(coordinate, indent=2, sort_keys=True) + "\n").encode()
    coordinate_repo = tmp_path / "coordinate-repo"
    coordinate_path = coordinate_repo / "recovery.json"
    coordinate_repo.mkdir()
    coordinate_path.write_bytes(coordinate_raw)
    subprocess.run(["git", "init", "-q"], cwd=coordinate_repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Portable Recovery Plant",
            "-c",
            "user.email=plant@example.invalid",
            "add",
            "recovery.json",
        ],
        cwd=coordinate_repo,
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Portable Recovery Plant",
            "-c",
            "user.email=plant@example.invalid",
            "commit",
            "-q",
            "-m",
            "Plant committed recovery coordinate",
        ],
        cwd=coordinate_repo,
        check=True,
    )
    monkeypatch.setattr(bridge, "REPO_ROOT", coordinate_repo)

    absent_target = tmp_path / "missing-coordinate-target"
    with pytest.raises(StoreError, match="absent or unreadable"):
        bridge.runtime_custody_adoption_grant(
            capsule,
            destination=absent_target,
            recovery_coordinate=coordinate_repo / "missing.json",
        )
    assert not absent_target.exists()

    stale_target = tmp_path / "stale-coordinate-target"
    coordinate_path.write_bytes(coordinate_raw + b" ")
    with pytest.raises(StoreError, match="not exact committed custody"):
        bridge.runtime_custody_adoption_grant(
            capsule,
            destination=stale_target,
            recovery_coordinate=coordinate_path,
        )
    assert not stale_target.exists()
    coordinate_path.write_bytes(coordinate_raw)

    wrong_target = tmp_path / "wrong-grant-target"
    wrong_grant = bridge.runtime_custody_adoption_grant(
        capsule,
        destination=wrong_target,
        recovery_coordinate=coordinate_path,
    )
    with pytest.raises(HistoryChainMismatch, match="external grant root moved"):
        bridge.adopt_runtime_custody(
            capsule,
            destination=wrong_target,
            recovery_coordinate=coordinate_path,
            expected_snapshot_id=exported["snapshot_id"],
            expected_grant_root="sha256:" + ("0" * 64),
        )
    assert wrong_grant["grant_root"] != "sha256:" + ("0" * 64)
    assert not wrong_target.exists()

    foreign_capsule = tmp_path / "foreign-receipt-format"
    shutil.copytree(capsule, foreign_capsule)
    foreign_receipt = foreign_capsule / "RECEIPT.json"
    foreign_receipt.write_bytes(foreign_receipt.read_bytes() + b" ")
    with pytest.raises(HistoryChainMismatch, match="external grant root moved"):
        bridge.adopt_runtime_custody(
            foreign_capsule,
            destination=wrong_target,
            recovery_coordinate=coordinate_path,
            expected_snapshot_id=exported["snapshot_id"],
            expected_grant_root=wrong_grant["grant_root"],
        )
    assert not wrong_target.exists()

    original_fault = bridge._portable_adoption_fault
    original_write_checkpoint = bridge.ConceptricStore._write_checkpoint

    moved_source_target = tmp_path / "moved-source" / "runtime"
    moved_source_grant = bridge.runtime_custody_adoption_grant(
        capsule,
        destination=moved_source_target,
        recovery_coordinate=coordinate_path,
    )
    source_receipt_path = capsule / "RECEIPT.json"
    source_receipt_raw = source_receipt_path.read_bytes()

    def move_source_during_copy(phase: str) -> None:
        if phase == "mid-copy":
            source_receipt_path.write_bytes(source_receipt_raw + b" ")

    monkeypatch.setattr(bridge, "_portable_adoption_fault", move_source_during_copy)
    with pytest.raises(HistoryChainMismatch, match="source moved during copy"):
        bridge.adopt_runtime_custody(
            capsule,
            destination=moved_source_target,
            recovery_coordinate=coordinate_path,
            expected_snapshot_id=exported["snapshot_id"],
            expected_grant_root=moved_source_grant["grant_root"],
        )
    source_receipt_path.write_bytes(source_receipt_raw)
    monkeypatch.setattr(bridge, "_portable_adoption_fault", original_fault)
    resumed_after_source_move = bridge.adopt_runtime_custody(
        capsule,
        destination=moved_source_target,
        recovery_coordinate=coordinate_path,
        expected_snapshot_id=exported["snapshot_id"],
        expected_grant_root=moved_source_grant["grant_root"],
    )
    assert resumed_after_source_move["status"] == "WRITABLE-RECOVERED"

    foreign_pending_target = tmp_path / "foreign-pending" / "runtime"
    foreign_pending_grant = bridge.runtime_custody_adoption_grant(
        capsule,
        destination=foreign_pending_target,
        recovery_coordinate=coordinate_path,
    )
    foreign_pending_target.parent.mkdir(parents=True)
    (foreign_pending_target.parent / ".runtime.adopt-foreign").mkdir()
    with pytest.raises(HistoryChainMismatch, match="pending different identity"):
        bridge.adopt_runtime_custody(
            capsule,
            destination=foreign_pending_target,
            recovery_coordinate=coordinate_path,
            expected_snapshot_id=exported["snapshot_id"],
            expected_grant_root=foreign_pending_grant["grant_root"],
        )
    assert not foreign_pending_target.exists()

    phases = (
        "before-copy",
        "mid-copy",
        "before-checkpoint-cas",
        "during-checkpoint-cas",
        "after-checkpoint-before-reseal",
        "after-reseal-before-rename",
        "after-rename",
    )
    for phase in phases:
        destination = tmp_path / f"crash-{phase}" / "runtime"
        grant = bridge.runtime_custody_adoption_grant(
            capsule,
            destination=destination,
            recovery_coordinate=coordinate_path,
        )
        tripped = False

        def fault(current: str, *, planted_phase: str = phase) -> None:
            nonlocal tripped
            if (
                planted_phase != "during-checkpoint-cas"
                and current == planted_phase
                and not tripped
            ):
                tripped = True
                raise RuntimeError(f"planted {planted_phase}")

        def write_checkpoint(
            connection,
            checkpoint,
            *,
            planted_phase: str = phase,
        ) -> None:
            nonlocal tripped
            if planted_phase == "during-checkpoint-cas" and not tripped:
                tripped = True
                raise RuntimeError(f"planted {planted_phase}")
            original_write_checkpoint(connection, checkpoint)

        monkeypatch.setattr(bridge, "_portable_adoption_fault", fault)
        monkeypatch.setattr(
            bridge.ConceptricStore,
            "_write_checkpoint",
            staticmethod(write_checkpoint),
        )
        with pytest.raises(RuntimeError, match=phase):
            bridge.adopt_runtime_custody(
                capsule,
                destination=destination,
                recovery_coordinate=coordinate_path,
                expected_snapshot_id=exported["snapshot_id"],
                expected_grant_root=grant["grant_root"],
            )
        monkeypatch.setattr(bridge, "_portable_adoption_fault", original_fault)
        monkeypatch.setattr(
            bridge.ConceptricStore,
            "_write_checkpoint",
            staticmethod(original_write_checkpoint),
        )
        resumed = bridge.adopt_runtime_custody(
            capsule,
            destination=destination,
            recovery_coordinate=coordinate_path,
            expected_snapshot_id=exported["snapshot_id"],
            expected_grant_root=grant["grant_root"],
        )
        assert resumed["status"] == "WRITABLE-RECOVERED"
        assert resumed["event_count"] == exported["event_count"]
        assert resumed["event_append"] is False


def test_runtime_custody_carries_seal_for_isolated_writable_admission(
    tmp_path: Path,
) -> None:
    _bootstrap()
    source_state = bridge._store().current_state()
    bridge._store().seal_custody(store_role="live-runtime-fabric")
    destination = tmp_path / "sealed-snapshot"

    bridge.export_runtime_custody(destination=destination)

    assert (destination / "hive-custody-receipt.json").is_file()
    assert bridge.verify_runtime_custody(destination)["event_count"] == (
        source_state.event_count
    )
    rehearsal = tmp_path / "writable-rehearsal"
    shutil.copytree(destination, rehearsal)
    with pytest.raises(StoreError, match="capsule v2 is read-only"):
        bridge.ConceptricStore(
            rehearsal,
            expected_store_role="live-runtime-fabric",
        )
    custody_receipt = destination / "hive-custody-receipt.json"
    custody_receipt.write_bytes(custody_receipt.read_bytes() + b" ")
    with pytest.raises(StoreError, match="co-resident custody evidence"):
        bridge.verify_runtime_custody(destination)


def test_runtime_custody_portable_adoption_recovers_one_writable_blank_machine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bootstrap()
    bridge._store().seal_custody(store_role="live-runtime-fabric")
    live_before = bridge.drift_token()
    capsule = tmp_path / "custody" / "runtime-atlas"
    destination = tmp_path / "blank-machine" / "runtime-atlas"
    exported = bridge.export_runtime_custody(destination=capsule)
    snapshot_id = exported["snapshot_id"]
    source_ledger = (capsule / "conceptric.sqlite3").read_bytes()
    grant_root = _portable_grant_fixture(
        monkeypatch, source=capsule, destination=destination
    )

    with pytest.raises(HistoryChainMismatch, match="snapshot id moved"):
        bridge.adopt_runtime_custody(
            capsule,
            destination=destination,
            recovery_coordinate="fixture-coordinate.json",
            expected_snapshot_id="sha256:" + ("0" * 64),
            expected_grant_root=grant_root,
        )
    assert (capsule / "conceptric.sqlite3").read_bytes() == source_ledger
    assert not destination.exists()
    assert bridge.drift_token() == live_before

    adopted = bridge.adopt_runtime_custody(
        capsule,
        destination=destination,
        recovery_coordinate="fixture-coordinate.json",
        expected_snapshot_id=snapshot_id,
        expected_grant_root=grant_root,
    )

    assert adopted["status"] == "WRITABLE-RECOVERED"
    assert adopted["snapshot_id"] == snapshot_id
    assert adopted["event_count"] == live_before["cursor"]
    assert adopted["head_event_id"] == live_before["head_event_id"]
    assert adopted["head_record_digest"] == live_before["head_record_digest"]
    assert adopted["event_append"] is False
    assert adopted["ledger_checkpoint_write"] is True
    assert adopted["fast_deep_equal"] is True
    assert adopted["integrity_boundary"] == "CHECKSUMMED-CRUTCH"
    assert bridge.drift_token() == live_before
    assert bridge.verify_runtime_custody(capsule)["snapshot_id"] == snapshot_id
    assert bridge.verify_writable_runtime_custody(
        destination,
        expected_snapshot_id=snapshot_id,
        expected_grant_root=grant_root,
    ) == {key: value for key, value in adopted.items() if key not in {
        "idempotent", "ledger_checkpoint_write", "writer_precondition"
    }}

    retried = bridge.adopt_runtime_custody(
        capsule,
        destination=destination,
        recovery_coordinate="fixture-coordinate.json",
        expected_snapshot_id=snapshot_id,
        expected_grant_root=grant_root,
    )
    assert retried["idempotent"] is True
    assert retried["ledger_checkpoint_write"] is False
    assert retried["checkpoint_digest"] == adopted["checkpoint_digest"]
    assert bridge.ConceptricStore(
        destination,
        expected_store_role="live-runtime-fabric",
        authority_context=bridge.ConceptricStore.authority_context_manifest(
            destination, store_role="live-runtime-fabric"
        ),
    ).current_state().event_count == live_before["cursor"]
    assert bridge.drift_token() == live_before

    target_before = bridge.ConceptricStore.read_drift_token(destination)
    monkeypatch.setattr(bridge, "store_root", lambda: destination)
    bridge._store_at.cache_clear()
    bridge._read_store_at.cache_clear()
    appended = bridge.lifecycle(
        action="sew-up",
        receipt_id="sew:portable-first-append",
        provider=PROVIDER,
        model=MODEL,
    )
    target_after = bridge.ConceptricStore.read_drift_token(destination)
    assert appended["receipt"]["sequence"] == target_before["cursor"] + 1
    assert target_after["cursor"] == target_before["cursor"] + 1


def test_runtime_custody_adoption_resumes_after_checkpoint_before_seal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bootstrap()
    live_before = bridge.drift_token()
    capsule = tmp_path / "custody-crash" / "runtime-atlas"
    destination = tmp_path / "blank-machine-crash" / "runtime-atlas"
    exported = bridge.export_runtime_custody(destination=capsule)
    assert not (capsule / "hive-custody-receipt.json").exists()
    grant_root = _portable_grant_fixture(
        monkeypatch, source=capsule, destination=destination
    )

    original_seal = bridge.ConceptricStore.seal_portable_authority_adoption

    def crash_after_checkpoint(cls, *args, **kwargs):
        raise RuntimeError("planted crash after checkpoint CAS")

    monkeypatch.setattr(
        bridge.ConceptricStore,
        "seal_portable_authority_adoption",
        classmethod(crash_after_checkpoint),
    )
    with pytest.raises(RuntimeError, match="planted crash"):
        bridge.adopt_runtime_custody(
            capsule,
            destination=destination,
            recovery_coordinate="fixture-coordinate.json",
            expected_snapshot_id=exported["snapshot_id"],
            expected_grant_root=grant_root,
        )
    pending = destination.with_name(
        f".{destination.name}.adopt-{grant_root.removeprefix('sha256:')[:16]}"
    )
    adoption = bridge.ConceptricStore.read_portable_authority_adoption(
        pending, expected_store_role="live-runtime-fabric"
    )
    assert adoption is not None
    assert bridge.ConceptricStore.read_drift_token(pending) == live_before
    assert not (pending / "hive-custody-receipt.json").exists()

    monkeypatch.setattr(
        bridge.ConceptricStore,
        "seal_portable_authority_adoption",
        original_seal,
    )
    resumed = bridge.adopt_runtime_custody(
        capsule,
        destination=destination,
        recovery_coordinate="fixture-coordinate.json",
        expected_snapshot_id=exported["snapshot_id"],
        expected_grant_root=grant_root,
    )
    assert resumed["status"] == "WRITABLE-RECOVERED"
    assert resumed["idempotent"] is True
    assert resumed["ledger_checkpoint_write"] is False
    assert (destination / "hive-custody-receipt.json").is_file()
    assert bridge.ConceptricStore.read_drift_token(destination) == live_before


def test_committed_legacy_runtime_custody_verifies_without_projection_upgrade() -> None:
    snapshot = (
        bridge.REPO_ROOT
        / "atlas"
        / "stores"
        / "runtime-custody"
        / "snapshot-20260825T165720Z"
    )

    verified = bridge.verify_runtime_custody(snapshot)

    assert verified["status"] == "verified"
    assert verified["event_count"] == 901
    assert verified["historical_unavailable_message_count"] == 0


def test_runtime_custody_refuses_a_destination_inside_live_authority() -> None:
    _bootstrap()

    with pytest.raises(Exception, match="cannot sit inside live authority"):
        bridge.export_runtime_custody(
            destination=bridge.store_root() / "not-a-backup"
        )


def _commit_staged(repo: Path, message: str) -> None:
    subprocess.run(
        [
            "git", "-c", "user.name=Atlas Test", "-c", "user.email=atlas@example.invalid",
            "commit", "-qm", message,
        ],
        cwd=repo,
        check=True,
    )


def _commit_all(repo: Path, message: str = "custody fixture") -> None:
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    _commit_staged(repo, message)


def test_blueprint_custody_requires_every_hived_authority_path_in_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    root = repo / "atlas" / "stores" / "blueprint"
    root.mkdir(parents=True)
    (repo / "atlas" / "blueprint_manifest.json").write_text(
        json.dumps({
            "schema_version": "atlas.blueprint-manifest/1",
            "store": "atlas/stores/blueprint",
        }),
        encoding="utf-8",
    )
    store = bridge.ConceptricStore(root)
    store.append(bridge._event(
        bridge.EventKind.LIFECYCLE,
        bridge.LifecycleTransition(
            bridge.LifecycleAction.COLD_WAKE,
            bridge.LifecyclePhase.SLEEPING,
            bridge.LifecyclePhase.AWAKE,
            "blueprint:git-custody:1",
        ).to_dict(),
        actor=bridge.SeatRole.SYSTEM,
        subject="blueprint:git-custody:1",
        provider=PROVIDER,
        model=MODEL,
        correlation_id="blueprint:git-custody:1",
        note="blueprint Git custody test",
    ))
    store.seal_custody(store_role="blueprint-generation")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(
        [
            "git", "add", "atlas/blueprint_manifest.json",
            "atlas/stores/blueprint/conceptric.sqlite3",
            "atlas/stores/blueprint/hive-custody-receipt.json",
            "atlas/stores/blueprint/hives/events",
        ],
        cwd=repo,
        check=True,
    )
    _commit_staged(repo, "custody fixture")
    monkeypatch.setattr(bridge, "REPO_ROOT", repo)

    projection = bridge.blueprint_custody_projection()

    assert projection["status"] == "sealed-hived-authority"
    assert projection["authoritative_path_count"] == 3
    assert projection["all_authority_tracked"] is True
    assert projection["authority_git_ref"] == "HEAD"
    assert projection["all_authority_head_bytes_exact"] is True
    assert projection["head_only_orphan_hives"] == 0
    assert projection["disposable_projection_tracked"] is False

    subprocess.run(
        ["git", "rm", "--cached", "atlas/stores/blueprint/hive-custody-receipt.json"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    _commit_staged(repo, "remove custody receipt from HEAD")
    # A complete index cannot stand in for what a clone of HEAD will receive.
    subprocess.run(
        ["git", "add", "atlas/stores/blueprint/hive-custody-receipt.json"],
        cwd=repo,
        check=True,
    )
    with pytest.raises(Exception, match="does not travel in the Git HEAD tree"):
        bridge.blueprint_custody_projection()


def test_blueprint_custody_proves_lfs_pointer_and_payload_instead_of_false_red(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    root = repo / "atlas" / "stores" / "blueprint"
    root.mkdir(parents=True)
    (repo / "atlas" / "blueprint_manifest.json").write_text(
        json.dumps({
            "schema_version": "atlas.blueprint-manifest/1",
            "store": "atlas/stores/blueprint",
        }),
        encoding="utf-8",
    )
    (repo / ".gitattributes").write_text(
        "atlas/stores/blueprint/conceptric.sqlite3 filter=lfs diff=lfs merge=lfs -text\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "lfs", "install", "--local"], cwd=repo, check=True,
                   capture_output=True)
    store = bridge.ConceptricStore(root)
    store.append(bridge._event(
        bridge.EventKind.LIFECYCLE,
        bridge.LifecycleTransition(
            bridge.LifecycleAction.COLD_WAKE,
            bridge.LifecyclePhase.SLEEPING,
            bridge.LifecyclePhase.AWAKE,
            "blueprint:lfs:1",
        ).to_dict(),
        actor=bridge.SeatRole.SYSTEM,
        subject="blueprint:lfs:1",
        provider=PROVIDER,
        model=MODEL,
        correlation_id="blueprint:lfs:1",
        note="LFS custody transport test",
    ))
    store.seal_custody(store_role="blueprint-generation")
    _commit_all(repo)
    monkeypatch.setattr(bridge, "REPO_ROOT", repo)

    projection = bridge.blueprint_custody_projection()

    assert projection["all_authority_head_representations_exact"] is True
    assert projection["all_authority_payloads_exact"] is True
    assert projection["authority_transport_counts"]["git-lfs"] == 1
    assert projection["authority_transport_counts"]["direct"] >= 2

    # A custody read must not refill local LFS storage and turn a bad clone into a green author
    # machine.  The committed pointer plus present working payload are sufficient to compare.
    lfs_objects = repo / ".git" / "lfs" / "objects"
    shutil.rmtree(lfs_objects)
    assert bridge.blueprint_custody_projection()["all_authority_payloads_exact"] is True
    assert not lfs_objects.exists()


def _indexed_blueprint_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo = tmp_path / "repo"
    root = repo / "atlas" / "stores" / "blueprint"
    root.mkdir(parents=True)
    (repo / "atlas" / "blueprint_manifest.json").write_text(
        json.dumps({
            "schema_version": "atlas.blueprint-manifest/1",
            "store": "atlas/stores/blueprint",
        }),
        encoding="utf-8",
    )
    store = bridge.ConceptricStore(root)
    store.append(bridge._event(
        bridge.EventKind.LIFECYCLE,
        bridge.LifecycleTransition(
            bridge.LifecycleAction.COLD_WAKE,
            bridge.LifecyclePhase.SLEEPING,
            bridge.LifecyclePhase.AWAKE,
            "blueprint:test",
        ).to_dict(),
        actor=bridge.SeatRole.SYSTEM,
        subject="blueprint:test",
        provider=PROVIDER,
        model=MODEL,
        correlation_id="blueprint:test",
        note="blueprint custody index test",
    ))
    store.seal_custody(store_role="blueprint-generation")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    _commit_all(repo)
    monkeypatch.setattr(bridge, "REPO_ROOT", repo)
    return repo, store


def test_blueprint_custody_refuses_working_bytes_that_differ_from_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, store = _indexed_blueprint_repo(tmp_path, monkeypatch)
    store.append(bridge._event(
        bridge.EventKind.LIFECYCLE,
        bridge.LifecycleTransition(
            bridge.LifecycleAction.SEW_UP,
            bridge.LifecyclePhase.AWAKE,
            bridge.LifecyclePhase.SEWING_UP,
            "blueprint:test:2",
        ).to_dict(),
        actor=bridge.SeatRole.SYSTEM,
        subject="blueprint:test:2",
        provider=PROVIDER,
        model=MODEL,
        correlation_id="blueprint:test:2",
        note="blueprint custody index drift test",
    ))
    store.seal_custody(store_role="blueprint-generation")
    # Make the new content chunk reachable from HEAD while leaving the changed ledger and seal
    # only in the working tree.  A proof keyed to the index would accept after `git add -A`;
    # a proof keyed to HEAD must still see that its committed authority is incoherent.
    subprocess.run(
        ["git", "add", str(store.hive_root.relative_to(repo))], cwd=repo, check=True
    )
    _commit_staged(repo, "partial authority commit")
    with pytest.raises(Exception, match="working payload disagrees with the Git HEAD tree"):
        bridge.blueprint_custody_projection()


def test_blueprint_custody_refuses_hive_orphans_that_exist_in_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, store = _indexed_blueprint_repo(tmp_path, monkeypatch)
    orphan = store.hive_root / "aa" / (("a" * 64) + ".zlib")
    orphan.parent.mkdir(parents=True, exist_ok=True)
    orphan.write_bytes(b"index-only orphan")
    _commit_all(repo, "plant committed orphan")
    orphan.unlink()

    with pytest.raises(Exception, match="Git HEAD tree carries blueprint hive chunks outside"):
        bridge.blueprint_custody_projection()


def test_send_binds_body_custody_and_event_store_before_an_environment_flip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _bootstrap()
    bound_root = bridge.store_root().resolve()
    moved_state = tmp_path / "state-after-put"
    real_blob_store = bridge.BlobStore

    class FlipAfterPut:
        def __init__(self, root: Path) -> None:
            self.delegate = real_blob_store(root)

        @property
        def root(self) -> Path:
            return self.delegate.root

        def put(self, data: bytes) -> str:
            handle = self.delegate.put(data)
            monkeypatch.setenv("LAPLACE_STATE", str(moved_state))
            return handle

        def get(self, handle: str) -> bytes:
            return self.delegate.get(handle)

    monkeypatch.setattr(bridge, "BlobStore", FlipAfterPut)
    sent = bridge.send(
        sender_seat_id="codex-seat",
        recipient_seat_id="claude-seat",
        message_type="root-binding-proof",
        body="body and envelope remain in one authority",
        dependency_roots={"contract": "atlas.seat-bridge.v1"},
        idempotency_key="root-binding-proof:1",
        expires_at=EXPIRES,
        provider=PROVIDER,
        model=MODEL,
    )

    assert real_blob_store(bound_root / "blobs").get(sent["body_handle"])
    assert not real_blob_store(
        moved_state / "atlas" / "conceptric" / "blobs"
    ).has(sent["body_handle"])
    from atlas.store import ConceptricStore

    assert ConceptricStore(bound_root, read_only=True).message_status(
        sent["message_id"]
    )["status"] == "queued"


def test_store_write_door_refuses_a_message_whose_body_is_absent() -> None:
    _bootstrap()
    state = bridge._store().current_state()
    missing = "sha256:" + "0" * 64
    message = bridge.SeatMessage(
        "message:direct-dangling-body",
        "codex-seat",
        "claude-seat",
        "planted-direct-append",
        missing,
        {"body": missing},
        "direct-dangling-body:1",
        state.event_count + 1,
        EXPIRES,
    )
    event = bridge._event(
        bridge.EventKind.MESSAGE,
        message.to_dict(),
        actor=bridge.SeatRole.PROVIDER,
        subject=message.message_id,
        provider=PROVIDER,
        model=MODEL,
        correlation_id="direct-dangling-body:1",
        assumption=state.active_assumption,
        fibre=state.active_fibre,
        body_handle=missing,
        note="plant a direct message append with no body",
    )

    with pytest.raises(BlobMissing, match="blob is not in the store"):
        bridge._store().append(event)


def test_poison_body_blocks_pull_without_burning_cursor_or_good_mail() -> None:
    _bootstrap()
    sent = []
    for index, body in enumerate(("good before", "poison", "good after"), start=1):
        sent.append(bridge.send(
            sender_seat_id="codex-seat",
            recipient_seat_id="claude-seat",
            message_type="poison-preflight",
            body=body,
            dependency_roots={"body-class": f"fixture:{index}"},
            idempotency_key=f"poison-preflight:{index}",
            expires_at=EXPIRES,
            provider=PROVIDER,
            model=MODEL,
        ))
    store = bridge._store()
    poisoned = bridge.BlobStore(store.root / "blobs").key_path(sent[1]["body_handle"])
    poisoned.unlink()
    before = store.current_state().cursor_for("claude-seat")

    pulled = bridge.pull(
        seat_id="claude-seat",
        as_of="2026-08-24T15:00:00Z",
        provider="claude",
        model="claude",
    )

    assert pulled["status"] == "BLOCKED-UNKNOWN-CONTENT"
    assert pulled["cursor_advanced"] is False
    assert pulled["after_cursor"] == pulled["result_cursor"] == before
    assert pulled["messages"] == []
    assert [item["message_id"] for item in pulled["unknown_content"]] == [
        sent[1]["message_id"]
    ]
    assert pulled["readable_message_ids"] == [
        sent[0]["message_id"], sent[2]["message_id"]
    ]
    state = store.current_state()
    assert state.cursor_for("claude-seat") == before
    assert all(state.messages[item["message_id"]].status.value == "queued" for item in sent)


def test_exchange_is_blob_backed_reconstructed_and_survives_cold_process() -> None:
    _bootstrap()
    sent = bridge.send(
        sender_seat_id="codex-seat",
        recipient_seat_id="claude-seat",
        message_type="reconstruct",
        body="Reconstruct the canonical seat-fabric handoff; do not infer a second store.",
        dependency_roots={"contract": "atlas.seat-bridge.v1"},
        idempotency_key="codex-to-claude:bridge-proof:1",
        expires_at=EXPIRES,
        provider=PROVIDER,
        model=MODEL,
    )
    assert sent["status"]["status"] == "queued"
    assert sent["status"]["delivered"] is False

    exact_body = bridge.message_body(message_id=sent["message_id"])
    assert exact_body["body_handle"] == sent["body_handle"]
    assert exact_body["storage_access"].startswith("sqlite mode=ro/query_only")
    assert bridge._read_store().read_only is True

    pulled = bridge.pull(
        seat_id="claude-seat",
        as_of="2026-08-24T15:00:00Z",
        provider="claude",
        model="claude",
    )
    assert [item["message_id"] for item in pulled["messages"]] == [sent["message_id"]]
    assert pulled["messages"][0]["body"].startswith("Reconstruct the canonical")
    assert bridge.status(message_id=sent["message_id"])["status"]["delivered"] is False

    proof = bridge.reconstruct(
        message_id=sent["message_id"],
        seat_id="claude-seat",
        goal="recover the exact provider handoff from its content-addressed handle",
        provider="claude",
        model="claude",
    )
    assert proof["body"] == pulled["messages"][0]["body"]
    accepted = bridge.acknowledge(
        message_id=sent["message_id"],
        seat_id="claude-seat",
        disposition="accepted",
        note="exact body reconstructed from the Atlas blob handle",
        reconstruction_event_id=proof["reconstruction_event_id"],
        reconstruction_handle=proof["reconstruction_handle"],
        provider="claude",
        model="claude",
    )
    assert accepted["status"]["status"] == "delivered"
    assert accepted["status"]["delivered"] is True

    bridge.lifecycle(
        action="sew-up",
        receipt_id="sew:bridge-test",
        provider=PROVIDER,
        model=MODEL,
    )
    bridge.lifecycle(
        action="sleep",
        receipt_id="sleep:bridge-test",
        provider=PROVIDER,
        model=MODEL,
    )

    code = """
import json
from laplace.representation import atlas_bridge as bridge
bridge.lifecycle(action='cold-wake', receipt_id='cold:after-process-death', provider='codex', model='gpt-5')
print(json.dumps(bridge.snapshot(), sort_keys=True))
"""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    completed = subprocess.run(
        ["/usr/bin/python3", "-c", code],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        check=False,
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stderr
    restarted = json.loads(completed.stdout)
    message = restarted["provider"]["messages"][sent["message_id"]]
    assert restarted["provider"]["lifecycle"] == "awake"
    assert message["status"] == "delivered"
    assert message["delivered"] is True

    from atlas.sensorium.journal_face import project_store

    projection = project_store(bridge.store_root())
    rendered = {item["message_id"]: item for item in projection["messages"]}
    assert rendered[sent["message_id"]]["delivered"] is True
    assert rendered[sent["message_id"]]["reconstruction_proof"][
        "verified_in_history"
    ]


def test_bridge_supersession_requires_current_sender_authority_and_keeps_old_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bootstrap()
    old = bridge.send(
        sender_seat_id="codex-seat",
        recipient_seat_id="claude-seat",
        message_type="stale-coordinate",
        body="old finding remains historical evidence",
        dependency_roots={"coordinate": "v1"},
        idempotency_key="supersession:old",
        expires_at=EXPIRES,
        provider=PROVIDER,
        model=MODEL,
    )
    replacement = bridge.send(
        sender_seat_id="codex-seat",
        recipient_seat_id="claude-seat",
        message_type="current-coordinate",
        body="finding re-derived on the current fibre",
        dependency_roots={"reissues": old["message_id"]},
        idempotency_key="supersession:replacement",
        expires_at=EXPIRES,
        provider=PROVIDER,
        model=MODEL,
    )
    with pytest.raises(StateTransitionRefused, match="routing-authoritative current sender"):
        bridge.supersede_message(
            message_id=old["message_id"],
            sender_seat_id="codex-seat",
            replacement_message_ids=(replacement["message_id"],),
            note="replacement must land first",
            provider=PROVIDER,
            model=MODEL,
        )

    sender_identity = _verified_codex_identity("supersession-thread")
    sender_identity["watcher_seat_id"] = "codex-seat"
    monkeypatch.setattr(
        bridge,
        "_live_provider_identity_attestation",
        lambda seat_id: sender_identity if seat_id == "codex-seat" else {},
    )
    joined = bridge.seat_join(
        seat_id="codex-seat",
        holder_ref="codex:supersession-thread",
        function="provider",
        information_proof={
            "schema_version": "laplace.startup-mail-gate/1",
            "seat_id": "codex-seat",
            "goal": "authenticate ordinary sender supersession",
            "state": "MAIL_READY",
            "observed_at": "2026-08-24T12:00:00+00:00",
            "delivered": [],
            "provider_identity": sender_identity,
        },
        provider=PROVIDER,
        model=MODEL,
    )
    assert joined["occupancy"]["routing_authority"] is True
    with pytest.raises(StateTransitionRefused, match="delivered reconstruction proof"):
        bridge.supersede_message(
            message_id=old["message_id"],
            sender_seat_id="codex-seat",
            replacement_message_ids=(replacement["message_id"],),
            note="replacement must land first",
            provider=PROVIDER,
            model=MODEL,
        )

    bridge.pull(
        seat_id="claude-seat",
        as_of="2026-08-24T15:00:00Z",
        provider="claude",
        model="claude",
    )
    proof = bridge.reconstruct(
        message_id=replacement["message_id"],
        seat_id="claude-seat",
        goal="recover the current-fibre replacement",
        provider="claude",
        model="claude",
    )
    bridge.acknowledge(
        message_id=replacement["message_id"],
        seat_id="claude-seat",
        disposition="accepted",
        note="replacement reconstructed",
        reconstruction_event_id=proof["reconstruction_event_id"],
        reconstruction_handle=proof["reconstruction_handle"],
        provider="claude",
        model="claude",
    )
    stale_identity = dict(sender_identity)
    stale_identity["watcher_lease_generation"] = "lease:stale-generation"
    monkeypatch.setattr(
        bridge,
        "_live_provider_identity_attestation",
        lambda seat_id: stale_identity if seat_id == "codex-seat" else {},
    )
    with pytest.raises(StateTransitionRefused, match="does not authenticate"):
        bridge.supersede_message(
            message_id=old["message_id"],
            sender_seat_id="codex-seat",
            replacement_message_ids=(replacement["message_id"],),
            note="stale generation must refuse",
            provider=PROVIDER,
            model=MODEL,
        )

    monkeypatch.setattr(
        bridge,
        "_live_provider_identity_attestation",
        lambda seat_id: sender_identity if seat_id == "codex-seat" else {},
    )
    result = bridge.supersede_message(
        message_id=old["message_id"],
        sender_seat_id="codex-seat",
        replacement_message_ids=(replacement["message_id"],),
        note="current reconstruction carries the live finding",
        provider=PROVIDER,
        model=MODEL,
    )
    assert result["receipt"]["kind"] == "seat.message-superseded"
    assert result["status"]["status"] == "superseded"
    assert result["status"]["delivered"] is False
    assert result["status"]["replacement_message_ids"] == [replacement["message_id"]]
    assert result["status"]["supersession_provider_session_ref"] == (
        "codex:supersession-thread"
    )
    assert result["status"]["supersession_provider_identity_generation"] == (
        "lease:supersession-thread"
    )
    assert result["status"]["supersession_provider_identity_proof_handle"]
    assert bridge.message_body(message_id=old["message_id"])["body"].startswith("old finding")

    repeated = bridge.supersede_message(
        message_id=old["message_id"],
        sender_seat_id="codex-seat",
        replacement_message_ids=(replacement["message_id"],),
        note="idempotent repeat",
        provider=PROVIDER,
        model=MODEL,
    )
    assert repeated["idempotent"] is True

    stable_tip = bridge.drift_token()
    monkeypatch.setattr(
        bridge,
        "_live_provider_identity_attestation",
        lambda _seat_id: {},
    )
    with pytest.raises(StateTransitionRefused, match="does not authenticate"):
        bridge.supersede_message(
            message_id=old["message_id"],
            sender_seat_id="codex-seat",
            replacement_message_ids=(replacement["message_id"],),
            note="idempotence is not unauthenticated write authority",
            provider=PROVIDER,
            model=MODEL,
        )
    assert bridge.drift_token() == stable_tip


def test_preserve_fork_quarantines_exact_obligation_and_reopens_only_after_sender_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bootstrap()
    bridge.seat_transition(
        seat_id="superego-seat",
        role="superego",
        action="found",
        charter_ref="charter:superego",
        holder_ref="holder:superego-seat:1",
        provider=PROVIDER,
        model=MODEL,
    )

    def bind(seat_id: str, function: str, thread_id: str) -> dict[str, object]:
        identity = _verified_codex_identity(thread_id)
        identity["watcher_seat_id"] = seat_id
        monkeypatch.setattr(
            bridge,
            "_live_provider_identity_attestation",
            lambda candidate: identity if candidate == seat_id else {},
        )
        return bridge.seat_join(
            seat_id=seat_id,
            holder_ref=f"codex:{thread_id}",
            function=function,
            information_proof={
                "schema_version": "laplace.startup-mail-gate/1",
                "seat_id": seat_id,
                "goal": "authenticate the exact preserve-fork operator",
                "state": "MAIL_READY",
                "observed_at": "2026-08-24T12:00:00+00:00",
                "delivered": [],
                "provider_identity": identity,
            },
            provider=PROVIDER,
            model=MODEL,
        )

    bind("superego-seat", "superego", "superego-thread")
    authority_message = bridge.send(
        sender_seat_id="codex-seat",
        recipient_seat_id="superego-seat",
        message_type="author-ruling",
        body="Preserve the exact foreign obligation as a reopenable fork.",
        dependency_roots={"ruling": "ruling:preserve-fork"},
        idempotency_key="preserve-fork:authority",
        expires_at=EXPIRES,
        provider=PROVIDER,
        model=MODEL,
    )
    bridge.pull(
        seat_id="superego-seat",
        as_of="2026-08-24T15:00:00Z",
        provider=PROVIDER,
        model=MODEL,
    )
    authority_proof = bridge.reconstruct(
        message_id=authority_message["message_id"],
        seat_id="superego-seat",
        goal="reconstruct the author's exact preserve-fork ruling",
        provider=PROVIDER,
        model=MODEL,
    )
    unrelated_authority = bridge.acknowledge(
        message_id=authority_message["message_id"],
        seat_id="superego-seat",
        disposition="accepted",
        note="author ruling reconstructed",
        reconstruction_event_id=authority_proof["reconstruction_event_id"],
        reconstruction_handle=authority_proof["reconstruction_handle"],
        provider=PROVIDER,
        model=MODEL,
    )

    target = bridge.send(
        sender_seat_id="claude-seat",
        recipient_seat_id="ego-seat",
        message_type="legacy-foreign-obligation",
        body="This body remains readable and historically undelivered.",
        dependency_roots={"fibre": "legacy"},
        idempotency_key="preserve-fork:target",
        expires_at=EXPIRES,
        provider="claude",
        model="claude",
    )
    other = bridge.send(
        sender_seat_id="codex-seat",
        recipient_seat_id="ego-seat",
        message_type="unrelated-obligation",
        body="This unrelated obligation must remain pending.",
        dependency_roots={"fibre": "legacy"},
        idempotency_key="preserve-fork:other",
        expires_at=EXPIRES,
        provider=PROVIDER,
        model=MODEL,
    )
    bridge.pull(
        seat_id="ego-seat",
        as_of="2026-08-24T15:00:00Z",
        provider=PROVIDER,
        model=MODEL,
    )
    before_body = bridge.message_body(message_id=target["message_id"])["body"]
    before = bridge.mail_obligations(seat_id="ego-seat")
    assert {row["message_id"] for row in before["obligations"]} == {
        target["message_id"],
        other["message_id"],
    }

    lawful_authority_message = bridge.send(
        sender_seat_id="codex-seat",
        recipient_seat_id="superego-seat",
        message_type="author-ruling-preserve-fork",
        body="Preserve this exact legacy Claude obligation until Claude returns.",
        dependency_roots={
            "author_ruling": "gerard:forget-claude-for-now",
            "legacy_claude_obligation": target["message_id"],
        },
        idempotency_key="preserve-fork:lawful-authority",
        expires_at=EXPIRES,
        provider=PROVIDER,
        model=MODEL,
    )
    bridge.pull(
        seat_id="superego-seat",
        as_of="2026-08-24T15:15:00Z",
        provider=PROVIDER,
        model=MODEL,
    )
    lawful_proof = bridge.reconstruct(
        message_id=lawful_authority_message["message_id"],
        seat_id="superego-seat",
        goal="reconstruct the exact target-bound author ruling",
        provider=PROVIDER,
        model=MODEL,
    )
    authority = bridge.acknowledge(
        message_id=lawful_authority_message["message_id"],
        seat_id="superego-seat",
        disposition="accepted",
        note="target-bound author ruling reconstructed",
        reconstruction_event_id=lawful_proof["reconstruction_event_id"],
        reconstruction_handle=lawful_proof["reconstruction_handle"],
        provider=PROVIDER,
        model=MODEL,
    )
    import atlas.state as atlas_state

    for module in (bridge, atlas_state):
        monkeypatch.setattr(
            module,
            "PRESERVE_FORK_TARGET_MESSAGE_ID",
            target["message_id"],
        )
        monkeypatch.setattr(
            module,
            "PRESERVE_FORK_AUTHOR_RULING_REF",
            "gerard:forget-claude-for-now",
        )
        monkeypatch.setattr(
            module,
            "PRESERVE_FORK_AUTHORITY_EVENT_ID",
            authority["receipt"]["event_id"],
        )
    monkeypatch.setattr(
        atlas_state,
        "PRESERVE_FORK_AUTHORITY_MESSAGE_ID",
        lawful_authority_message["message_id"],
    )

    pinned = {
        "seat_id": "superego-seat",
        "message_id": target["message_id"],
        "original_sender_seat_id": "claude-seat",
        "recipient_seat_id": "ego-seat",
        "body_handle": target["body_handle"],
        "author_ruling_ref": "gerard:forget-claude-for-now",
        "authority_event_id": authority["receipt"]["event_id"],
        "reason": "Claude is outside the current three-seat startup",
        "reopen_condition": "authenticated Claude returns with an exact delivered replacement",
        "provider": PROVIDER,
        "model": MODEL,
    }
    with pytest.raises(StateTransitionRefused, match="only superego-seat"):
        bridge.preserve_message_fork(**{**pinned, "seat_id": "codex-seat"})
    with pytest.raises(StateTransitionRefused, match="wrong authority event"):
        bridge.preserve_message_fork(
            **{
                **pinned,
                "authority_event_id": unrelated_authority["receipt"]["event_id"],
            }
        )
    with pytest.raises(StateTransitionRefused, match="body handle"):
        bridge.preserve_message_fork(**{**pinned, "body_handle": "sha256:" + "0" * 64})

    attacker_identity = _verified_codex_identity("attacker-thread")
    attacker_identity["watcher_seat_id"] = "superego-seat"
    monkeypatch.setattr(
        bridge,
        "_live_provider_identity_attestation",
        lambda seat_id: attacker_identity if seat_id == "superego-seat" else {},
    )
    with pytest.raises(StateTransitionRefused, match="does not authenticate"):
        bridge.preserve_message_fork(**pinned)
    superego_identity = _verified_codex_identity("superego-thread")
    superego_identity["watcher_seat_id"] = "superego-seat"
    monkeypatch.setattr(
        bridge,
        "_live_provider_identity_attestation",
        lambda seat_id: superego_identity if seat_id == "superego-seat" else {},
    )

    result = bridge.preserve_message_fork(**pinned)
    assert result["receipt"]["kind"] == "seat.message-fork-preserved"
    status = result["status"]
    assert status["status"] == "quarantined"
    assert status["delivered"] is False
    assert status["quarantined"] is True
    assert status["acknowledgement_event_id"] is None
    assert status["preserve_fork"]["authority_event_id"] == authority["receipt"]["event_id"]
    assert status["preserve_fork"]["author_ruling_ref"] == pinned["author_ruling_ref"]
    assert status["preserve_fork"]["reopen_condition"] == pinned["reopen_condition"]
    assert status["preserve_fork_source_status"] == "pulled"
    assert status["preserve_fork_actor_seat_id"] == "superego-seat"
    assert status["preserve_fork_actor_function"] == "superego"
    assert status["preserve_fork_binding_event_id"]
    assert status["preserve_fork"]["actor_provider_session_ref"] == (
        "codex:superego-thread"
    )
    assert status["preserve_fork"]["actor_provider_identity_proof_handle"]
    assert status["preserve_fork"]["actor_provider_identity_generation"] == (
        "lease:superego-thread"
    )
    assert status["preserve_fork_frontier"] == {
        "assumption": "seat-fabric-is-one-conceptric",
        "fibre": "provider-exchange",
    }
    assert bridge.message_body(message_id=target["message_id"])["body"] == before_body
    after = bridge.mail_obligations(seat_id="ego-seat")
    assert [row["message_id"] for row in after["obligations"]] == [other["message_id"]]

    repeated = bridge.preserve_message_fork(**pinned)
    assert repeated["idempotent"] is True
    assert repeated["receipt"]["event_id"] == result["receipt"]["event_id"]
    with pytest.raises(StateTransitionRefused, match="different pinned evidence"):
        bridge.preserve_message_fork(**{**pinned, "reason": "changed reason"})

    prebinding_replacement = bridge.send(
        sender_seat_id="claude-seat",
        recipient_seat_id="ego-seat",
        message_type="premature-replacement",
        body="Sent before the original sender is authenticated.",
        dependency_roots={"reissues": target["message_id"]},
        idempotency_key="preserve-fork:prebinding-replacement",
        expires_at=EXPIRES,
        provider="claude",
        model="claude",
    )
    bridge.pull(
        seat_id="ego-seat",
        as_of="2026-08-24T15:30:00Z",
        provider=PROVIDER,
        model=MODEL,
    )
    proof = bridge.reconstruct(
        message_id=prebinding_replacement["message_id"],
        seat_id="ego-seat",
        goal="reconstruct premature replacement",
        provider=PROVIDER,
        model=MODEL,
    )
    bridge.acknowledge(
        message_id=prebinding_replacement["message_id"],
        seat_id="ego-seat",
        disposition="accepted",
        note="bytes reconstructed, sender not yet authenticated",
        reconstruction_event_id=proof["reconstruction_event_id"],
        reconstruction_handle=proof["reconstruction_handle"],
        provider=PROVIDER,
        model=MODEL,
    )
    with pytest.raises(StateTransitionRefused, match="routing-authoritative current sender"):
        bridge.supersede_message(
            message_id=target["message_id"],
            sender_seat_id="claude-seat",
            replacement_message_ids=(prebinding_replacement["message_id"],),
            note="must refuse while Claude is unbound",
            provider="claude",
            model="claude",
        )

    bind("claude-seat", "provider", "claude-return")
    observational_identity = _verified_codex_identity("claude-return")
    observational_identity["watcher_seat_id"] = "claude-seat"
    observational_identity["state"] = "OBSERVATIONAL"
    monkeypatch.setattr(
        bridge,
        "_live_provider_identity_attestation",
        lambda seat_id: observational_identity if seat_id == "claude-seat" else {},
    )
    with pytest.raises(StateTransitionRefused, match="does not authenticate"):
        bridge.supersede_message(
            message_id=target["message_id"],
            sender_seat_id="claude-seat",
            replacement_message_ids=(prebinding_replacement["message_id"],),
            note="observational identity cannot reopen",
            provider="claude",
            model="claude",
        )
    stale_generation_identity = _verified_codex_identity("claude-return")
    stale_generation_identity["watcher_seat_id"] = "claude-seat"
    stale_generation_identity["watcher_lease_generation"] = "lease:stale-generation"
    monkeypatch.setattr(
        bridge,
        "_live_provider_identity_attestation",
        lambda seat_id: stale_generation_identity if seat_id == "claude-seat" else {},
    )
    with pytest.raises(StateTransitionRefused, match="does not authenticate"):
        bridge.supersede_message(
            message_id=target["message_id"],
            sender_seat_id="claude-seat",
            replacement_message_ids=(prebinding_replacement["message_id"],),
            note="stale watcher generation cannot reopen",
            provider="claude",
            model="claude",
        )
    claude_identity = _verified_codex_identity("claude-return")
    claude_identity["watcher_seat_id"] = "claude-seat"
    monkeypatch.setattr(
        bridge,
        "_live_provider_identity_attestation",
        lambda seat_id: claude_identity if seat_id == "claude-seat" else {},
    )
    with pytest.raises(StateTransitionRefused, match="sent after original-sender binding"):
        bridge.supersede_message(
            message_id=target["message_id"],
            sender_seat_id="claude-seat",
            replacement_message_ids=(prebinding_replacement["message_id"],),
            note="pre-binding replacement cannot reopen",
            provider="claude",
            model="claude",
        )
    replacement = bridge.send(
        sender_seat_id="claude-seat",
        recipient_seat_id="ego-seat",
        message_type="authenticated-replacement",
        body="A fresh current-fibre replacement sent after authenticated return.",
        dependency_roots={"reissues": target["message_id"]},
        idempotency_key="preserve-fork:authenticated-replacement",
        expires_at=EXPIRES,
        provider="claude",
        model="claude",
    )
    bridge.pull(
        seat_id="ego-seat",
        as_of="2026-08-24T16:00:00Z",
        provider=PROVIDER,
        model=MODEL,
    )
    proof = bridge.reconstruct(
        message_id=replacement["message_id"],
        seat_id="ego-seat",
        goal="reconstruct authenticated current-fibre replacement",
        provider=PROVIDER,
        model=MODEL,
    )
    bridge.acknowledge(
        message_id=replacement["message_id"],
        seat_id="ego-seat",
        disposition="accepted",
        note="authenticated replacement reconstructed",
        reconstruction_event_id=proof["reconstruction_event_id"],
        reconstruction_handle=proof["reconstruction_handle"],
        provider=PROVIDER,
        model=MODEL,
    )
    reopened = bridge.supersede_message(
        message_id=target["message_id"],
        sender_seat_id="claude-seat",
        replacement_message_ids=(replacement["message_id"],),
        note="authenticated delivered replacement reopens the quarantine",
        provider="claude",
        model="claude",
    )
    assert reopened["status"]["status"] == "superseded"
    assert reopened["status"]["delivered"] is False
    assert reopened["status"]["supersession_provider_session_ref"] == (
        "codex:claude-return"
    )
    assert reopened["status"]["supersession_provider_identity_proof_handle"]
    assert reopened["status"]["supersession_provider_identity_generation"] == (
        "lease:claude-return"
    )


def test_unproved_acceptance_never_masquerades_as_delivery() -> None:
    _bootstrap()
    sent = bridge.send(
        sender_seat_id="codex-seat",
        recipient_seat_id="claude-seat",
        message_type="reconstruct",
        body="This remains queued until reconstructed and acknowledged.",
        dependency_roots={"contract": "atlas.seat-bridge.v1"},
        idempotency_key="unproved:1",
        expires_at=EXPIRES,
        provider=PROVIDER,
        model=MODEL,
    )
    with pytest.raises(StateTransitionRefused, match="reconstruction proof"):
        bridge.acknowledge(
            message_id=sent["message_id"],
            seat_id="claude-seat",
            disposition="accepted",
            note="attempted acceptance without reconstruction",
            provider="claude",
            model="claude",
        )
    status = bridge.status(message_id=sent["message_id"])["status"]
    assert status["status"] == "queued"
    assert status["delivered"] is False


def test_fibre_local_cursor_does_not_skip_a_message_in_another_assumption() -> None:
    _bootstrap()
    sent = bridge.send(
        sender_seat_id="codex-seat",
        recipient_seat_id="claude-seat",
        message_type="reconstruct",
        body="This message belongs only to assumption A.",
        dependency_roots={"contract": "atlas.seat-bridge.v1"},
        idempotency_key="fibre-a:1",
        expires_at=EXPIRES,
        provider=PROVIDER,
        model=MODEL,
    )
    bridge.transport_context(
        assumption="counterfactual-seat-fabric",
        fibre="counterfactual-provider-exchange",
        operator="declared-counterfactual",
        loss_or_obstruction="message meanings do not cross automatically",
        provider=PROVIDER,
        model=MODEL,
    )
    other = bridge.pull(
        seat_id="claude-seat",
        as_of="2026-08-24T15:00:00Z",
        provider="claude",
        model="claude",
    )
    assert other["messages"] == []

    bridge.transport_context(
        assumption="seat-fabric-is-one-conceptric",
        fibre="provider-exchange",
        operator="return-to-declared-source-context",
        loss_or_obstruction="counterfactual context is not carried back",
        provider=PROVIDER,
        model=MODEL,
    )
    original = bridge.pull(
        seat_id="claude-seat",
        as_of="2026-08-24T15:00:00Z",
        provider="claude",
        model="claude",
    )
    assert [item["message_id"] for item in original["messages"]] == [sent["message_id"]]


def test_mail_obligations_are_recipient_scoped_and_survive_context_transport() -> None:
    _bootstrap()
    claude = bridge.send(
        sender_seat_id="codex-seat",
        recipient_seat_id="claude-seat",
        message_type="obligation-plant",
        body="pulled but not yet reconstructed",
        dependency_roots={"contract": "atlas.seat-bridge.v1"},
        idempotency_key="obligation-plant:claude",
        expires_at=EXPIRES,
        provider=PROVIDER,
        model=MODEL,
    )
    sensorium = bridge.send(
        sender_seat_id="codex-seat",
        recipient_seat_id="sensorium-seat",
        message_type="obligation-plant",
        body="queued for a different recipient",
        dependency_roots={"contract": "atlas.seat-bridge.v1"},
        idempotency_key="obligation-plant:sensorium",
        expires_at=EXPIRES,
        provider=PROVIDER,
        model=MODEL,
    )
    bridge.pull(
        seat_id="claude-seat",
        as_of="2026-08-24T15:00:00Z",
        provider="claude",
        model="claude",
    )

    claude_mail = bridge.mail_obligations(seat_id="claude-seat")
    sensorium_mail = bridge.mail_obligations(seat_id="sensorium-seat")

    assert [row["message_id"] for row in claude_mail["obligations"]] == [claude["message_id"]]
    assert claude_mail["obligations"][0]["status"] == "pulled"
    assert claude_mail["obligations"][0]["reconstructable_in_active_context"] is True
    assert [row["message_id"] for row in sensorium_mail["obligations"]] == [
        sensorium["message_id"]
    ]
    assert sensorium_mail["obligations"][0]["status"] == "queued"

    bridge.transport_context(
        assumption="counterfactual-seat-fabric",
        fibre="counterfactual-provider-exchange",
        operator="plant-context-transport",
        loss_or_obstruction="old mail remains an explicit nonterminal obligation",
        provider=PROVIDER,
        model=MODEL,
    )
    transported = bridge.mail_obligations(seat_id="claude-seat")
    row = transported["obligations"][0]
    assert row["message_id"] == claude["message_id"]
    assert row["context_matches"] is False
    assert row["reconstructable_in_active_context"] is False
    assert transported["counts"]["other_context"] == 1


def test_permission_is_visible_but_never_inferred() -> None:
    _bootstrap()
    requested = bridge.request_permission(
        request_id="permission:write-handoff",
        requester_seat_id="claude-seat",
        permission="write-handoff",
        target="handle:integration-handoff",
        rationale="the provider must not write until Ego grants the bounded act",
        expires_at=EXPIRES,
        provider="claude",
        model="claude",
    )
    pending = bridge.snapshot()["provider"]["permissions"][requested["request_id"]]
    assert pending["decision"] is None
    decided = bridge.decide_permission(
        request_id=requested["request_id"],
        decider_seat_id="ego-seat",
        outcome="granted",
        reason="bounded to the integration handoff handle",
        provider=PROVIDER,
        model=MODEL,
    )
    assert decided["permission"]["decision"]["outcome"] == "granted"


def test_durable_event_watcher_dispatches_a_queued_message_then_stops() -> None:
    _bootstrap()
    registration = bridge.register_watcher(
        watcher_id="watch:seat-message",
        created_by_seat_id="ego-seat",
        target_seat_id="sensorium-seat",
        source_kind="conceptric-events",
        selector={"event_kind": "seat.message-sent", "subject_prefix": "message:"},
        message_type="watch-trigger",
        one_shot=True,
        poll_interval_seconds=0.25,
        expires_at=EXPIRES,
        provider=PROVIDER,
        model=MODEL,
    )
    assert registration["watcher"]["checkpoint"] is None

    observed = bridge.send(
        sender_seat_id="codex-seat",
        recipient_seat_id="claude-seat",
        message_type="audit-input",
        body="The watcher sees this handle; it does not count it as delivered.",
        dependency_roots={"contract": "atlas.seat-bridge.v1"},
        idempotency_key="watch-observed:1",
        expires_at=EXPIRES,
        provider=PROVIDER,
        model=MODEL,
    )
    fired = bridge.watch_once(
        watcher_id="watch:seat-message",
        observed_at="2026-08-24T15:00:00Z",
    )
    trigger_id = fired["dispatch_message_ids"][0]
    assert fired["delivery_claimed"] is False
    assert bridge.status(message_id=trigger_id)["status"]["status"] == "queued"
    assert bridge.status(message_id=trigger_id)["status"]["delivered"] is False
    assert bridge.status(message_id=observed["message_id"])["status"]["delivered"] is False
    assert bridge.watch_once(watcher_id="watch:seat-message")["idempotent"] is True

    snapshot = bridge.snapshot()["provider"]
    relations = {edge["relation"] for edge in snapshot["graph"]["edges"].values()}
    assert {"subscribes-to", "dispatches-to", "dispatched-message"} <= relations
    assert any(item["kind"] == "provider-session-holder" for item in snapshot["graph"]["objects"].values())

    pulled = bridge.pull(
        seat_id="sensorium-seat",
        as_of="2026-08-24T15:01:00Z",
        provider=PROVIDER,
        model=MODEL,
    )
    assert [item["message_id"] for item in pulled["messages"]] == [trigger_id]
    proof = bridge.reconstruct(
        message_id=trigger_id,
        seat_id="sensorium-seat",
        goal="recover the watcher trigger from its handle",
        provider=PROVIDER,
        model=MODEL,
    )
    accepted = bridge.acknowledge(
        message_id=trigger_id,
        seat_id="sensorium-seat",
        disposition="accepted",
        note="watcher trigger reconstructed exactly",
        provider=PROVIDER,
        model=MODEL,
        reconstruction_event_id=proof["reconstruction_event_id"],
        reconstruction_handle=proof["reconstruction_handle"],
    )
    assert accepted["status"]["delivered"] is True


def test_filesystem_watcher_persists_metadata_not_file_content(tmp_path: Path) -> None:
    _bootstrap()
    watched = tmp_path / "provider-handoff.json"
    bridge.register_watcher(
        watcher_id="watch:handoff-path",
        created_by_seat_id="ego-seat",
        target_seat_id="sensorium-seat",
        source_kind="filesystem-path",
        selector={"path": str(watched)},
        message_type="handoff-landed",
        one_shot=True,
        poll_interval_seconds=0.25,
        expires_at=EXPIRES,
        provider=PROVIDER,
        model=MODEL,
    )
    armed = bridge.watch_once(
        watcher_id="watch:handoff-path", observed_at="2026-08-24T15:00:00Z"
    )
    assert armed["checkpoint"]["status"] == "armed"
    watched.write_text('{"private":"body is not the watcher state"}', encoding="utf-8")
    fired = bridge.watch_once(
        watcher_id="watch:handoff-path", observed_at="2026-08-24T15:01:00Z"
    )
    assert fired["checkpoint"]["status"] == "fired"
    assert len(fired["checkpoint"]["matched_handles"]) == 1
    assert "private" not in json.dumps(bridge.snapshot()["provider"]["watchers"])
