from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest
from atlas.errors import StateTransitionRefused, StoreError

from laplace.representation import atlas_bridge as bridge

MIGRATION_BASELINE_EVENT_COUNT = 3095
MIGRATION_BASELINE_HEAD = "sha256:741a0c90ac13d2b8b51226be8bab79ed525146dea75b88f1d1a7854a5e391f4a"
STALE_REPLACEMENT_ID = "message:d0417206217235cf9f5357ba0a8aecf31914d9c00847953a7a99b954fdb1fb4f"
CLAUDE_ID = "message:9fa1c38ef567333433960fcb6b4c1fc99b4fde2a5c30da3365c6ca0d8194da90"
LEGACY_CODEX_IDS = (
    "message:180c1392d67774ac03bd74e5fee3ecf5cc177a8bb96ce679cb475fa33ffad27d",
    "message:8d18bfccc6b4758e3f91d7e438333b33a702e45f223eecbd1d0be2be3ee12f7f",
    "message:44c3dfce932e8176ac618b1c1222890dd62cbaf234ef83e4ebea77c8ab80bcd6",
    "message:4b4efea3be4f1b2fcaab8e77c4b4fe4bf142c020557bc3d01795f9e4dc9e4bbd",
    "message:296a39087282b7d439a079cd6935ddf625f169a81c80f505545265003f1916e8",
    "message:c948e31d39e4bd807d067a47b12cf2a03148ac51109e48534797b4794e28d446",
)
EXPIRES = "2026-08-30T00:00:00Z"


def test_v2_copied_runtime_stays_read_only_without_external_grant(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source-runtime"
    monkeypatch.setattr(bridge, "store_root", lambda: source)
    bridge._store_at.cache_clear()
    bridge._read_store_at.cache_clear()
    bridge.lifecycle(
        action="cold-wake",
        receipt_id="cold:stage-zero-portable-source",
        provider="codex",
        model="stage-zero-portable-recovery-test",
    )
    capsule = tmp_path / "capsule"
    exported = bridge.export_runtime_custody(destination=capsule)
    source_before = bridge._runtime_capsule_layout(capsule)
    copied = tmp_path / "ordinary-copy"
    shutil.copytree(capsule, copied)

    monkeypatch.setattr(bridge, "store_root", lambda: copied)
    bridge._store_at.cache_clear()
    bridge._read_store_at.cache_clear()
    with pytest.raises(StoreError, match="capsule v2 is read-only"):
        bridge._store()

    assert bridge.verify_runtime_custody(capsule)["snapshot_id"] == exported["snapshot_id"]
    assert bridge._runtime_capsule_layout(capsule) == source_before


def _custody_source() -> Path:
    raw = os.environ.get("LAPLACE_STAGE_ZERO_CUSTODY")
    if not raw:
        pytest.skip("set LAPLACE_STAGE_ZERO_CUSTODY to the immutable copied-live snapshot")
    source = Path(raw).resolve()
    if not (source / "RECEIPT.json").is_file():
        pytest.skip(f"copied-live custody is absent: {source}")
    return source


def _identity(seat_id: str, task_id: str) -> dict[str, object]:
    return {
        "schema_version": "laplace.provider-session-identity/1",
        "state": "VERIFIED",
        "provider_session_ref": f"codex:{task_id}",
        "requested_holder_ref": None,
        "provider": "codex",
        "identity_kind": "codex-thread-watcher-binding",
        "watcher_seat_id": seat_id,
        "watcher_target_thread_id": task_id,
        "watcher_lease_generation": f"lease:{task_id}:1",
        "watcher_pid": 42002,
        "reason": None,
    }


def _deliver(message_id: str, seat_id: str, goal: str) -> dict[str, object]:
    proof = bridge.reconstruct(
        message_id=message_id,
        seat_id=seat_id,
        goal=goal,
        provider="codex",
        model="stage-zero-copied-runtime-rehearsal",
    )
    return bridge.acknowledge(
        message_id=message_id,
        seat_id=seat_id,
        disposition="accepted",
        note="exact copied-live body reconstructed",
        reconstruction_event_id=proof["reconstruction_event_id"],
        reconstruction_handle=proof["reconstruction_handle"],
        provider="codex",
        model="stage-zero-copied-runtime-rehearsal",
    )


def _commission(commission: dict[str, str], key: str) -> dict[str, object]:
    text = bridge.canonical_json(commission)
    author_turn = {
        "schema_version": "laplace.author-turn/1",
        "row": {
            "schema_version": "laplace.author-turn/1",
            "record": "talk",
            "id": f"TALK-STAGE-ZERO-{key}",
            "actor": "gerard",
            "about": "v1 to v2 stage-zero recovery",
            "to": "superego-seat",
            "audience": "superego-seat",
            "recipient_seat_ids": ["superego-seat"],
            "text": text,
            "via": "front-door",
            "ts": "2026-08-27T18:00:00+00:00",
        },
    }
    author_turn_handle = bridge.put_custody(bridge.canonical_json(author_turn).encode("utf-8"))
    sent = bridge.send(
        sender_seat_id="gerard-seat",
        recipient_seat_id="superego-seat",
        message_type="conversation-turn",
        body=text,
        dependency_roots={"author_turn": author_turn_handle},
        idempotency_key=f"stage-zero-copied-runtime:{key}",
        expires_at=EXPIRES,
        provider="front-door",
        model="author-relay",
    )
    pulled = bridge.pull(
        seat_id="superego-seat",
        as_of="2026-08-29T00:00:00Z",
        provider="codex",
        model="stage-zero-copied-runtime-rehearsal",
    )
    assert sent["message_id"] in {message["message_id"] for message in pulled["messages"]}
    return _deliver(
        sent["message_id"],
        "superego-seat",
        "reconstruct the exact canonical Gerard migration commission",
    )


def test_copied_live_atomic_recovery_closes_without_touching_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _custody_source()
    receipt_bytes = (source / "RECEIPT.json").read_bytes()
    receipt = json.loads(receipt_bytes)
    assert receipt["schema_version"] == bridge.RUNTIME_CUSTODY_SCHEMA
    assert receipt["event_count"] >= MIGRATION_BASELINE_EVENT_COUNT
    source_ledger_before = bridge.hash_bytes((source / "conceptric.sqlite3").read_bytes())

    target = tmp_path / "copied-live-runtime"
    shutil.copytree(source, target)
    (target / ".atlas-test-root").touch()
    monkeypatch.setattr(bridge, "store_root", lambda: target)
    bridge._store_at.cache_clear()
    bridge._read_store_at.cache_clear()

    baseline = bridge._store().current_state()
    baseline_events = bridge._store().events()
    assert baseline.event_count == receipt["event_count"]
    assert baseline.head_event_id == receipt["head_event_id"]
    assert baseline_events[MIGRATION_BASELINE_EVENT_COUNT - 1].event_id == MIGRATION_BASELINE_HEAD
    stale_replacement = baseline.messages[STALE_REPLACEMENT_ID]
    assert stale_replacement.status.value == "queued"
    assert stale_replacement.message.expires_at == "2026-08-27T15:00:00Z"
    assert all(baseline.messages[mid].status.value == "pulled" for mid in LEGACY_CODEX_IDS)
    assert baseline.messages[CLAUDE_ID].status.value == "pulled"

    task_id = "01a044ed-bc5d-7b43-9092-6c82600e5d06"
    identities = {"codex-seat": _identity("codex-seat", task_id)}
    identities["codex-seat"]["watcher_lease_generation"] = (
        "sha256:1dbb214f577e9a9471279779c5a1ab08deeeb762a61ca968777e4c1a6d480433"
    )
    transient_identity = {
        **identities["codex-seat"],
        "state": "UNVERIFIED",
        "watcher_status": "STALE",
        "watcher_action": "watcher information checkpoint is outside its freshness bound",
        "watcher_interval_seconds": 0.5,
        "reason": "live watcher checkpoint is stale",
    }
    codex_transition = [transient_identity, identities["codex-seat"]]

    def live_identity(seat_id: str) -> dict[str, object]:
        if seat_id == "codex-seat" and codex_transition:
            return codex_transition.pop(0)
        return identities.get(seat_id, {})

    monkeypatch.setattr(
        bridge,
        "_live_provider_identity_attestation",
        live_identity,
    )
    monkeypatch.setattr(bridge.time, "sleep", lambda seconds: None)
    codex_joined = bridge.seat_join(
        seat_id="codex-seat",
        holder_ref=f"codex:{task_id}",
        function="provider",
        information_proof={
            "schema_version": "laplace.startup-mail-gate/1",
            "seat_id": "codex-seat",
            "goal": "perform only the copied-live stage-zero migration prelude",
            "state": "MAIL_READY",
            "observed_at": "2026-08-27T17:40:00+00:00",
            "delivered": [],
            "provider_identity": identities["codex-seat"],
        },
        provider="codex",
        model="stage-zero-copied-runtime-rehearsal",
    )
    assert codex_joined["occupancy"]["routing_authority"] is True
    attestation = codex_joined["provider_identity_attestation"]
    assert attestation["stabilization_attempted"] is True
    assert [row["state"] for row in attestation["observations"]] == [
        "UNVERIFIED",
        "VERIFIED",
    ]
    cutover = bridge._store().current_state()
    assert set(cutover.seat_occupancies) == {"codex-seat"}
    assert set(cutover.seat_lifecycle_invalidated_legacy_occupancies) == {
        "claude-seat",
        "codex-seat",
        "sensorium-seat",
        "superego-seat",
    }

    replacement = bridge.reissue_stage_zero_migration_replacement(
        provider="codex",
        model="stage-zero-copied-runtime-rehearsal",
    )
    assert replacement["idempotent"] is False
    assert replacement["receipt"]["kind"] == "seat.message-sent"
    replacement_id = replacement["message_id"]
    assert replacement_id == bridge.STAGE_ZERO_REISSUE_MESSAGE_ID
    pulled = bridge.pull(
        seat_id="ego-seat",
        as_of="2026-08-28T00:00:00Z",
        provider="codex",
        model="stage-zero-copied-runtime-rehearsal",
    )
    assert [message["message_id"] for message in pulled["messages"]] == [replacement_id]
    _deliver(
        replacement_id,
        "ego-seat",
        "reconstruct the exact fresh six-message current-fibre consolidation",
    )
    superseded_stale = bridge.supersede_message(
        message_id=STALE_REPLACEMENT_ID,
        sender_seat_id="codex-seat",
        replacement_message_ids=(replacement_id,),
        note="the 15:00 envelope expired before migration and was exactly reissued",
        provider="codex",
        model="stage-zero-copied-runtime-rehearsal",
    )
    assert superseded_stale["status"]["status"] == "superseded"
    pre_authority = bridge._store().current_state()
    entries, correlation, _reconstruction = bridge.derive_message_migration_recovery_entries(
        pre_authority,
        replacement_message_id=replacement_id,
    )
    manifest = {
        "schema_version": bridge.MessageMigrationSupersession.MANIFEST_SCHEMA_VERSION,
        "replacement_message_id": replacement_id,
        "replacement_body_handle": pre_authority.messages[replacement_id].message.body_handle,
        "reconstruction_correlation": correlation,
        "entries": [entry.to_dict() for entry in entries],
    }
    assert tuple(entry.message_id for entry in entries) == LEGACY_CODEX_IDS
    manifest_root = bridge.chash(manifest)

    identities["superego-seat"] = _identity("superego-seat", "stage-zero-superego-rehearsal")
    joined = bridge.seat_join(
        seat_id="superego-seat",
        holder_ref="codex:stage-zero-superego-rehearsal",
        function="superego",
        information_proof={
            "schema_version": "laplace.startup-mail-gate/1",
            "seat_id": "superego-seat",
            "goal": "adjudicate the isolated stage-zero recovery only",
            "state": "MAIL_READY",
            "observed_at": "2026-08-27T17:50:00+00:00",
            "delivered": [],
            "provider_identity": identities["superego-seat"],
        },
        provider="codex",
        model="stage-zero-copied-runtime-rehearsal",
    )
    assert joined["occupancy"]["routing_authority"] is True
    adjudication_state = bridge._store().current_state()
    assert set(adjudication_state.seat_occupancies) == {"codex-seat", "superego-seat"}

    commission = {
        "schema_version": bridge.MessageMigrationSupersession.COMMISSION_SCHEMA_VERSION,
        "authorized_act": bridge.MessageMigrationSupersession.SCHEMA_VERSION,
        "migration_root": bridge.MESSAGE_MIGRATION_RECOVERY_CAPSULE_HANDLE,
        "replacement_message": replacement_id,
        "replacement_body": adjudication_state.messages[replacement_id].message.body_handle,
        "recovery_manifest": manifest_root,
    }
    wrong = _commission(
        {**commission, "recovery_manifest": "sha256:" + "0" * 64},
        "wrong-commission",
    )
    stable = bridge.drift_token()
    with pytest.raises(StateTransitionRefused, match="exact recovery coordinate"):
        bridge.recover_legacy_message_bundle(
            actor_seat_id="superego-seat",
            replacement_message_id=replacement_id,
            authority_acknowledgement_event_id=wrong["receipt"]["event_id"],
            provider="codex",
            model="stage-zero-copied-runtime-rehearsal",
        )
    assert bridge.drift_token() == stable

    authority = _commission(commission, "exact-commission")
    store = bridge._store()
    original_insert = type(store)._insert_event_v2

    def fail_before_recovery_insert(connection: object, stored: object, handle: str) -> None:
        if stored.event.kind == bridge.EventKind.MESSAGE_MIGRATION_SUPERSESSION:
            raise RuntimeError("planted crash before atomic migration recovery insert")
        original_insert(connection, stored, handle)

    monkeypatch.setattr(type(store), "_insert_event_v2", staticmethod(fail_before_recovery_insert))
    before_crash = bridge.drift_token()
    with pytest.raises(RuntimeError, match="planted crash"):
        bridge.recover_legacy_message_bundle(
            actor_seat_id="superego-seat",
            replacement_message_id=replacement_id,
            authority_acknowledgement_event_id=authority["receipt"]["event_id"],
            provider="codex",
            model="stage-zero-copied-runtime-rehearsal",
        )
    assert bridge.drift_token() == before_crash
    assert all(
        bridge.status(message_id=mid)["status"]["status"] == "pulled" for mid in LEGACY_CODEX_IDS
    )
    monkeypatch.setattr(type(store), "_insert_event_v2", staticmethod(original_insert))

    recovered = bridge.recover_legacy_message_bundle(
        actor_seat_id="superego-seat",
        replacement_message_id=replacement_id,
        authority_acknowledgement_event_id=authority["receipt"]["event_id"],
        provider="codex",
        model="stage-zero-copied-runtime-rehearsal",
    )
    assert recovered["recovery_manifest_root"] == manifest_root
    assert recovered["message_ids"] == list(LEGACY_CODEX_IDS)
    assert recovered["delivery_claimed"] is False

    claude = bridge._store().current_state().messages[CLAUDE_ID]
    preserved = bridge.preserve_message_fork(
        seat_id="superego-seat",
        message_id=CLAUDE_ID,
        original_sender_seat_id=claude.message.sender_seat_id,
        recipient_seat_id=claude.message.recipient_seat_id,
        body_handle=claude.message.body_handle,
        author_ruling_ref=bridge.PRESERVE_FORK_AUTHOR_RULING_REF,
        authority_event_id=bridge.PRESERVE_FORK_AUTHORITY_EVENT_ID,
        reason="Gerard ruled that Claude is excluded from the stage-zero restart",
        reopen_condition="Gerard explicitly commissions Claude's later v2 admission",
        provider="codex",
        model="stage-zero-copied-runtime-rehearsal",
    )
    assert preserved["status"]["status"] == "quarantined"

    final_tip = bridge.drift_token()
    reissued_again = bridge.reissue_stage_zero_migration_replacement(
        provider="codex",
        model="stage-zero-copied-runtime-rehearsal",
    )
    assert reissued_again["idempotent"] is True
    assert reissued_again["message_id"] == replacement_id
    repeated = bridge.recover_legacy_message_bundle(
        actor_seat_id="superego-seat",
        replacement_message_id=replacement_id,
        authority_acknowledgement_event_id=authority["receipt"]["event_id"],
        provider="codex",
        model="stage-zero-copied-runtime-rehearsal",
    )
    assert repeated["idempotent"] is True
    assert bridge.drift_token() == final_tip

    cold = bridge.ConceptricStore(
        target,
        read_only=True,
        expected_store_role="live-runtime-fabric",
    ).current_state()
    assert cold.messages[STALE_REPLACEMENT_ID].status.value == "superseded"
    assert cold.messages[replacement_id].status.value == "delivered"
    assert cold.messages[CLAUDE_ID].status.value == "quarantined"
    assert all(cold.messages[mid].status.value == "superseded" for mid in LEGACY_CODEX_IDS)
    assert bridge.mail_obligations(seat_id="ego-seat")["obligations"] == []
    assert bridge.mail_obligations(seat_id="superego-seat")["obligations"] == []

    reachability = bridge._store().hive_reachability()
    assert reachability["status"] == "exact"
    assert len(reachability["orphan_handles"]) == 1
    assert (source / "RECEIPT.json").read_bytes() == receipt_bytes
    assert bridge.hash_bytes((source / "conceptric.sqlite3").read_bytes()) == source_ledger_before
    print(
        bridge.canonical_json(
            {
                "schema_version": "laplace.stage-zero-copied-runtime-rehearsal/1",
                "status": "PASS",
                "source_snapshot": receipt["snapshot_id"],
                "source_head": receipt["head_event_id"],
                "migration_baseline_head": MIGRATION_BASELINE_HEAD,
                "cutover_join": codex_joined["receipt"],
                "fresh_replacement_message_id": replacement_id,
                "fresh_replacement_body_handle": replacement["body_handle"],
                "stale_replacement_supersession": superseded_stale["receipt"],
                "recovery_manifest_root": manifest_root,
                "superego_join": joined["receipt"],
                "superego_binding": joined["binding_receipt"],
                "atomic_recovery": recovered["receipt"],
                "claude_preservation": preserved["receipt"],
                "final_tip": final_tip,
                "orphan_handles": reachability["orphan_handles"],
                "orphan_handles_root": reachability["orphan_handles_root"],
                "source_unchanged": True,
            }
        )
    )
