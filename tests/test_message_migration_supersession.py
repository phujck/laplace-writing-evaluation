from __future__ import annotations

import pytest
from atlas.errors import StateTransitionRefused

from laplace.representation import atlas_bridge as bridge

PROVIDER = "codex"
MODEL = "gpt-5"
EXPIRES = "2026-08-28T18:00:00Z"
CURRENT_ASSUMPTION = "stage-zero-lifecycle-migration"
CURRENT_FIBRE = "v2-recovery"
RECONSTRUCTION_CORRELATION = "synthetic-legacy-bundle-reconstruction"


def _bootstrap() -> None:
    bridge.lifecycle(
        action="cold-wake",
        receipt_id="cold:message-migration-recovery",
        provider=PROVIDER,
        model=MODEL,
    )
    for seat_id, role in (
        ("codex-seat", "provider"),
        ("ego-seat", "ego"),
        ("superego-seat", "superego"),
        ("interface-seat", "provider"),
        ("gerard-seat", "author"),
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
        assumption="historical-atlas-rebuild",
        fibre="legacy-obligations",
        provider=PROVIDER,
        model=MODEL,
        confidence=1.0,
    )


def _verified_identity(seat_id: str, thread_id: str) -> dict[str, object]:
    return {
        "schema_version": "laplace.provider-session-identity/1",
        "state": "VERIFIED",
        "provider_session_ref": f"codex:{thread_id}",
        "requested_holder_ref": None,
        "provider": "codex",
        "identity_kind": "codex-thread-watcher-binding",
        "watcher_seat_id": seat_id,
        "watcher_target_thread_id": thread_id,
        "watcher_lease_generation": f"lease:{thread_id}:1",
        "watcher_pid": 42,
        "reason": None,
    }


def _inject_immutable_history(packet: tuple[object, ...]) -> None:
    """Plant only an already-committed legacy prefix, then rebuild its projection."""

    store = bridge._store()
    with store._connect() as connection:
        tip = connection.execute(
            "SELECT sequence, record_digest FROM events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        sequence = 0 if tip is None else int(tip["sequence"])
        previous = "sha256:" + ("0" * 64) if tip is None else str(tip["record_digest"])
        connection.execute("BEGIN IMMEDIATE")
        for historical_event in packet:
            sequence += 1
            stored = bridge.StoredEvent.create(sequence, previous, historical_event)
            handle = store.hive.put(bridge.canonical_json(historical_event.to_dict()).encode())
            store._insert_event_v2(connection, stored, handle)
            previous = stored.record_digest
        connection.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES ('authoritative_head_digest', ?)",
            (previous,),
        )
        connection.commit()
    bridge._store_at.cache_clear()
    bridge._read_store_at.cache_clear()
    bridge.ConceptricStore(store.root)


def _plant_historical_codex_occupancy() -> None:
    state = bridge._store().current_state()
    identity = _verified_identity("codex-seat", "historical-codex")
    proof = {
        "schema_version": "laplace.startup-mail-gate/1",
        "seat_id": "codex-seat",
        "goal": "replay the immutable v1 codex occupancy",
        "state": "MAIL_READY",
        "observed_at": "2026-08-27T12:00:00+00:00",
        "delivered": [],
        "provider_identity": identity,
    }
    proof_handle = bridge._blobs().put((bridge.canonical_json(proof) + "\n").encode())
    join = bridge.SeatJoinReceipt(
        seat_id="codex-seat",
        holder_ref="codex:historical-codex",
        function=bridge.SeatRole.PROVIDER,
        registered_role=bridge.SeatRole.PROVIDER,
        registered_holder_ref="holder:codex-seat:1",
        mail_state="MAIL_READY",
        information_proof_handle=proof_handle,
        information_cursor=state.event_count,
        delivered_message_ids=(),
        reconstruction_event_ids=(),
    )
    join_payload = join.to_dict()
    join_payload["schema_version"] = bridge.SeatJoinReceipt.LEGACY_V1_SCHEMA_VERSION
    join_payload.pop("provider_identity_generation")
    join_event = bridge._event(
        bridge.EventKind.SEAT_JOIN,
        join_payload,
        actor=bridge.SeatRole.PROVIDER,
        subject="seat:codex-seat:occupancy",
        provider=PROVIDER,
        model=MODEL,
        correlation_id="historical-codex-join",
        assumption=state.active_assumption,
        fibre=state.active_fibre,
        causation_ids=(state.head_event_id,),
        body_handle=proof_handle,
        note="immutable historical codex join fixture",
    )
    binding = bridge.SeatOccupancyBinding(
        seat_id="codex-seat",
        registered_seat_event_id=state.seat_registration_event_ids["codex-seat"],
        join_event_id=join_event.event_id,
        registered_principal_ref="holder:codex-seat:1",
        provider_session_ref="codex:historical-codex",
        function=bridge.SeatRole.PROVIDER,
        provider_identity_proof_handle=proof_handle,
    )
    binding_payload = binding.to_dict()
    binding_payload["schema_version"] = bridge.SeatOccupancyBinding.LEGACY_V3_SCHEMA_VERSION
    binding_event = bridge._event(
        bridge.EventKind.SEAT_OCCUPANCY_BINDING,
        binding_payload,
        actor=bridge.SeatRole.PROVIDER,
        subject="seat:codex-seat:binding",
        provider=PROVIDER,
        model=MODEL,
        correlation_id="historical-codex-binding",
        assumption=state.active_assumption,
        fibre=state.active_fibre,
        causation_ids=(
            state.seat_registration_event_ids["codex-seat"],
            join_event.event_id,
        ),
        body_handle=proof_handle,
        note="immutable historical codex binding fixture",
    )
    _inject_immutable_history((join_event, binding_event))


def _deliver(message_id: str, seat_id: str, goal: str) -> dict[str, object]:
    proof = bridge.reconstruct(
        message_id=message_id,
        seat_id=seat_id,
        goal=goal,
        provider=PROVIDER,
        model=MODEL,
    )
    return bridge.acknowledge(
        message_id=message_id,
        seat_id=seat_id,
        disposition="accepted",
        note="exact body reconstructed",
        reconstruction_event_id=proof["reconstruction_event_id"],
        reconstruction_handle=proof["reconstruction_handle"],
        provider=PROVIDER,
        model=MODEL,
    )


def _send_and_deliver_commission(
    *,
    commission: dict[str, str],
    idempotency_key: str,
) -> dict[str, object]:
    text = bridge.canonical_json(commission)
    author_turn = {
        "schema_version": "laplace.author-turn/1",
        "row": {
            "schema_version": "laplace.author-turn/1",
            "record": "talk",
            "id": f"TALK-SYNTHETIC-{idempotency_key}",
            "actor": "gerard",
            "about": None,
            "to": "superego-seat",
            "audience": "superego-seat",
            "recipient_seat_ids": ["superego-seat"],
            "text": text,
            "via": "front-door",
            "ts": "2026-08-28T14:00:00+00:00",
        },
    }
    author_turn_handle = bridge.put_custody(bridge.canonical_json(author_turn).encode("utf-8"))
    sent = bridge.send(
        sender_seat_id="gerard-seat",
        recipient_seat_id="superego-seat",
        message_type="conversation-turn",
        body=text,
        dependency_roots={"author_turn": author_turn_handle},
        idempotency_key=idempotency_key,
        expires_at=EXPIRES,
        provider=PROVIDER,
        model=MODEL,
    )
    bridge.pull(
        seat_id="superego-seat",
        as_of="2026-08-28T15:00:00Z",
        provider=PROVIDER,
        model=MODEL,
    )
    return _deliver(
        sent["message_id"],
        "superego-seat",
        "reconstruct the exact author recovery commission",
    )


def test_author_commissioned_recovery_is_derived_atomic_and_non_delivering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bootstrap()
    old_messages = tuple(
        bridge.send(
            sender_seat_id="codex-seat",
            recipient_seat_id="ego-seat",
            message_type="legacy-cross-fibre-obligation",
            body=f"historical obligation {index}",
            dependency_roots={"legacy_fibre": "atlas-rebuild"},
            idempotency_key=f"message-migration:old:{index}",
            expires_at=EXPIRES,
            provider=PROVIDER,
            model=MODEL,
        )
        for index in range(1, 4)
    )
    bridge.pull(
        seat_id="ego-seat",
        as_of="2026-08-28T12:00:00Z",
        provider=PROVIDER,
        model=MODEL,
    )
    bridge.transport_context(
        assumption=CURRENT_ASSUMPTION,
        fibre=CURRENT_FIBRE,
        operator="clean-stage-zero-transport",
        loss_or_obstruction="old envelopes retain their historical fibre",
        provider=PROVIDER,
        model=MODEL,
    )
    for old in old_messages:
        trace = bridge.begin_typed_descent(
            kind="fabric-message",
            reference=old["message_id"],
            source="atlas-message-ledger",
            goal="reconstruct one exact legacy obligation into the current consolidation",
            seat_id="ego-seat",
            provider=PROVIDER,
            model=MODEL,
            correlation_id=RECONSTRUCTION_CORRELATION,
        )
        bridge.finish_typed_descent(
            trace,
            result_handle=old["body_handle"],
            provenance={
                "message_id": old["message_id"],
                "body_handle": old["body_handle"],
            },
        )
    omitted = bridge.send(
        sender_seat_id="codex-seat",
        recipient_seat_id="ego-seat",
        message_type="legacy-bundle-incomplete-consolidation",
        body="This deliberately omits one eligible historical obligation.",
        dependency_roots={
            "source_1": old_messages[0]["body_handle"],
            "source_2": old_messages[1]["body_handle"],
            "reconstruction_correlation": RECONSTRUCTION_CORRELATION,
        },
        idempotency_key="message-migration:omitted-replacement",
        expires_at=EXPIRES,
        provider=PROVIDER,
        model=MODEL,
    )
    bridge.pull(
        seat_id="ego-seat",
        as_of="2026-08-28T12:20:00Z",
        provider=PROVIDER,
        model=MODEL,
    )
    _deliver(
        omitted["message_id"],
        "ego-seat",
        "reconstruct the deliberately incomplete consolidation",
    )
    with pytest.raises(StateTransitionRefused, match="do not exhaust"):
        bridge.derive_message_migration_recovery_entries(
            bridge._store().current_state(),
            replacement_message_id=omitted["message_id"],
        )
    replacement = bridge.send(
        sender_seat_id="codex-seat",
        recipient_seat_id="ego-seat",
        message_type="legacy-bundle-current-fibre-consolidation",
        body="The exact old obligations are consolidated without claiming old delivery.",
        dependency_roots={
            "source_1": old_messages[0]["body_handle"],
            "source_2": old_messages[1]["body_handle"],
            "source_3": old_messages[2]["body_handle"],
            "reconstruction_correlation": RECONSTRUCTION_CORRELATION,
        },
        idempotency_key="message-migration:replacement",
        expires_at=EXPIRES,
        provider=PROVIDER,
        model=MODEL,
    )
    bridge.pull(
        seat_id="ego-seat",
        as_of="2026-08-28T12:30:00Z",
        provider=PROVIDER,
        model=MODEL,
    )
    _deliver(
        replacement["message_id"],
        "ego-seat",
        "reconstruct the exact current-fibre consolidation",
    )

    _plant_historical_codex_occupancy()
    superego_identity = _verified_identity("superego-seat", "superego-migration")
    monkeypatch.setattr(
        bridge,
        "_live_provider_identity_attestation",
        lambda seat_id: superego_identity if seat_id == "superego-seat" else {},
    )
    joined = bridge.seat_join(
        seat_id="superego-seat",
        holder_ref="codex:superego-migration",
        function="superego",
        information_proof={
            "schema_version": "laplace.startup-mail-gate/1",
            "seat_id": "superego-seat",
            "goal": "adjudicate only the exact commissioned migration recovery",
            "state": "MAIL_READY",
            "observed_at": "2026-08-28T13:00:00+00:00",
            "delivered": [],
            "provider_identity": superego_identity,
        },
        provider=PROVIDER,
        model=MODEL,
    )
    assert joined["occupancy"]["routing_authority"] is True
    cutover_state = bridge._store().current_state()
    assert "codex-seat" not in cutover_state.seat_occupancies
    assert (
        cutover_state.seat_lifecycle_invalidated_legacy_occupancies["codex-seat"].join.holder_ref
        == "codex:historical-codex"
    )

    entries, correlation, _reconstruction_event_id = (
        bridge.derive_message_migration_recovery_entries(
            cutover_state,
            replacement_message_id=replacement["message_id"],
        )
    )
    manifest = {
        "schema_version": bridge.MessageMigrationSupersession.MANIFEST_SCHEMA_VERSION,
        "replacement_message_id": replacement["message_id"],
        "replacement_body_handle": replacement["body_handle"],
        "reconstruction_correlation": correlation,
        "entries": [entry.to_dict() for entry in entries],
    }
    manifest_root = bridge.chash(manifest)
    commission = {
        "schema_version": bridge.MessageMigrationSupersession.COMMISSION_SCHEMA_VERSION,
        "authorized_act": bridge.MessageMigrationSupersession.SCHEMA_VERSION,
        "migration_root": bridge.MESSAGE_MIGRATION_RECOVERY_CAPSULE_HANDLE,
        "replacement_message": replacement["message_id"],
        "replacement_body": replacement["body_handle"],
        "recovery_manifest": manifest_root,
    }

    bridge.transport_context(
        assumption=CURRENT_ASSUMPTION,
        fibre="wrong-authority-fibre",
        operator="adversarial-commission-transport",
        loss_or_obstruction="prove that a valid author turn in another fibre grants no authority",
        provider=PROVIDER,
        model=MODEL,
    )
    wrong_fibre_authority = _send_and_deliver_commission(
        commission=commission,
        idempotency_key="message-migration:wrong-fibre-commission",
    )
    bridge.transport_context(
        assumption=CURRENT_ASSUMPTION,
        fibre=CURRENT_FIBRE,
        operator="return-to-exact-recovery-fibre",
        loss_or_obstruction="the foreign-fibre commission remains visible but non-authoritative",
        provider=PROVIDER,
        model=MODEL,
    )
    stable = bridge.drift_token()
    with pytest.raises(StateTransitionRefused, match="current-fibre Gerard author turn"):
        bridge.recover_legacy_message_bundle(
            actor_seat_id="superego-seat",
            replacement_message_id=replacement["message_id"],
            authority_acknowledgement_event_id=wrong_fibre_authority["receipt"]["event_id"],
            provider=PROVIDER,
            model=MODEL,
        )
    assert bridge.drift_token() == stable

    wrong_authority = _send_and_deliver_commission(
        commission={**commission, "recovery_manifest": "sha256:" + "0" * 64},
        idempotency_key="message-migration:wrong-commission",
    )
    stable = bridge.drift_token()
    with pytest.raises(StateTransitionRefused, match="exact recovery coordinate"):
        bridge.recover_legacy_message_bundle(
            actor_seat_id="superego-seat",
            replacement_message_id=replacement["message_id"],
            authority_acknowledgement_event_id=wrong_authority["receipt"]["event_id"],
            provider=PROVIDER,
            model=MODEL,
        )
    assert bridge.drift_token() == stable
    assert all(
        bridge.status(message_id=old["message_id"])["status"]["status"] == "pulled"
        for old in old_messages
    )

    authority = _send_and_deliver_commission(
        commission=commission,
        idempotency_key="message-migration:exact-commission",
    )
    direct_state = bridge._store().current_state()
    direct_authority = next(
        record
        for record in direct_state.messages.values()
        if record.acknowledgement_event_id == authority["receipt"]["event_id"]
    )
    direct_occupancy = direct_state.seat_occupancies["superego-seat"]
    direct_identity = bridge._authenticated_provider_identity(
        store=bridge._store(),
        seat_id="superego-seat",
        occupancy=direct_occupancy,
    )
    direct_recovery = bridge.MessageMigrationSupersession(
        transition_id=("message-migration-supersession:" + manifest_root.removeprefix("sha256:")),
        entries=entries,
        reconstruction_correlation=correlation,
        replacement_message_id=replacement["message_id"],
        replacement_body_handle=replacement["body_handle"],
        recovery_manifest_root=manifest_root,
        lifecycle_cutover_event_id=direct_state.seat_lifecycle_cutover_event_id,
        recovery_capsule_handle=bridge.MESSAGE_MIGRATION_RECOVERY_CAPSULE_HANDLE,
        author_turn_handle=direct_authority.message.dependency_roots["author_turn"],
        commission_handle=bridge.chash(commission),
        authority_message_id=direct_authority.message.message_id,
        authority_body_handle=direct_authority.message.body_handle,
        authority_acknowledgement_event_id=authority["receipt"]["event_id"],
        operator_seat_id="superego-seat",
        operator_provider_session_ref=direct_identity["provider_session_ref"],
        operator_provider_identity_proof_handle=direct_identity["provider_identity_proof_handle"],
        operator_provider_identity_generation=direct_identity["provider_identity_generation"],
        note="retire the exact derived legacy bundle without claiming delivery",
    )
    direct_event = bridge._event(
        bridge.EventKind.MESSAGE_MIGRATION_SUPERSESSION,
        direct_recovery.to_dict(),
        actor=bridge.SeatRole.SUPEREGO,
        subject=direct_recovery.transition_id,
        provider=PROVIDER,
        model=MODEL,
        correlation_id="direct-store-door-attack",
        assumption=CURRENT_ASSUMPTION,
        fibre=CURRENT_FIBRE,
        body_handle=direct_identity["provider_identity_proof_handle"],
        evidence_handles=(
            bridge.MESSAGE_MIGRATION_RECOVERY_CAPSULE_HANDLE,
            direct_recovery.author_turn_handle,
            direct_recovery.authority_body_handle,
        ),
        note="direct append must not bypass source-bearing evidence validation",
    )
    stable = bridge.drift_token()
    with pytest.raises(StateTransitionRefused, match="evidence is unavailable or corrupt"):
        bridge._store().append(direct_event)
    assert bridge.drift_token() == stable

    before_recovery = bridge.drift_token()
    recovered = bridge.recover_legacy_message_bundle(
        actor_seat_id="superego-seat",
        replacement_message_id=replacement["message_id"],
        authority_acknowledgement_event_id=authority["receipt"]["event_id"],
        provider=PROVIDER,
        model=MODEL,
    )
    assert recovered["receipt"]["sequence"] == before_recovery["cursor"] + 1
    assert recovered["receipt"]["kind"] == "seat.message-migration-superseded"
    assert recovered["recovery_manifest_root"] == manifest_root
    assert recovered["manifest"] == manifest
    assert recovered["delivery_claimed"] is False
    assert recovered["message_ids"] == [old["message_id"] for old in old_messages]
    recovery_event_id = recovered["receipt"]["event_id"]
    for old in old_messages:
        status = recovered["statuses"][old["message_id"]]
        assert status["status"] == "superseded"
        assert status["delivered"] is False
        assert status["acknowledgement_event_id"] is None
        assert status["supersession_event_id"] == recovery_event_id
        assert status["replacement_message_ids"] == [replacement["message_id"]]

    after_recovery = bridge.drift_token()
    repeated = bridge.recover_legacy_message_bundle(
        actor_seat_id="superego-seat",
        replacement_message_id=replacement["message_id"],
        authority_acknowledgement_event_id=authority["receipt"]["event_id"],
        provider=PROVIDER,
        model=MODEL,
    )
    assert repeated["idempotent"] is True
    assert repeated["receipt"]["event_id"] == recovery_event_id
    assert bridge.drift_token() == after_recovery

    monkeypatch.setattr(
        bridge,
        "_live_provider_identity_attestation",
        lambda _seat_id: {},
    )
    with pytest.raises(StateTransitionRefused, match="does not authenticate"):
        bridge.recover_legacy_message_bundle(
            actor_seat_id="superego-seat",
            replacement_message_id=replacement["message_id"],
            authority_acknowledgement_event_id=authority["receipt"]["event_id"],
            provider=PROVIDER,
            model=MODEL,
        )
    assert bridge.drift_token() == after_recovery

    cold = bridge.ConceptricStore(bridge.store_root()).replay()
    assert cold.message_migration_supersessions[manifest_root].authority_message_id
    assert all(
        cold.messages[old["message_id"]].status.value == "superseded"
        and cold.messages[old["message_id"]].acknowledgement_event_id is None
        for old in old_messages
    )
    assert bridge.mail_obligations(seat_id="ego-seat")["obligations"] == []


def test_recovery_refuses_materialization_created_after_its_replacement() -> None:
    _bootstrap()
    old = bridge.send(
        sender_seat_id="codex-seat",
        recipient_seat_id="ego-seat",
        message_type="legacy-cross-fibre-obligation",
        body="historical obligation reconstructed too late",
        dependency_roots={"legacy_fibre": "atlas-rebuild"},
        idempotency_key="message-migration:late-proof:old",
        expires_at=EXPIRES,
        provider=PROVIDER,
        model=MODEL,
    )
    bridge.pull(
        seat_id="ego-seat",
        as_of="2026-08-28T12:00:00Z",
        provider=PROVIDER,
        model=MODEL,
    )
    bridge.transport_context(
        assumption=CURRENT_ASSUMPTION,
        fibre=CURRENT_FIBRE,
        operator="clean-stage-zero-transport",
        loss_or_obstruction="retain the historical envelope while testing proof order",
        provider=PROVIDER,
        model=MODEL,
    )
    correlation = "synthetic-late-materialization"
    replacement = bridge.send(
        sender_seat_id="codex-seat",
        recipient_seat_id="ego-seat",
        message_type="legacy-bundle-current-fibre-consolidation",
        body="This replacement was sent before its alleged source reconstruction.",
        dependency_roots={
            "source_1": old["body_handle"],
            "reconstruction_correlation": correlation,
        },
        idempotency_key="message-migration:late-proof:replacement",
        expires_at=EXPIRES,
        provider=PROVIDER,
        model=MODEL,
    )
    bridge.pull(
        seat_id="ego-seat",
        as_of="2026-08-28T12:30:00Z",
        provider=PROVIDER,
        model=MODEL,
    )
    _deliver(
        replacement["message_id"],
        "ego-seat",
        "reconstruct the premature consolidation",
    )
    trace = bridge.begin_typed_descent(
        kind="fabric-message",
        reference=old["message_id"],
        source="atlas-message-ledger",
        goal="create the deliberately late source proof",
        seat_id="ego-seat",
        provider=PROVIDER,
        model=MODEL,
        correlation_id=correlation,
    )
    bridge.finish_typed_descent(
        trace,
        result_handle=old["body_handle"],
        provenance={
            "message_id": old["message_id"],
            "body_handle": old["body_handle"],
        },
    )
    with pytest.raises(
        StateTransitionRefused, match="send before materialization before replacement"
    ):
        bridge.derive_message_migration_recovery_entries(
            bridge._store().current_state(),
            replacement_message_id=replacement["message_id"],
        )
