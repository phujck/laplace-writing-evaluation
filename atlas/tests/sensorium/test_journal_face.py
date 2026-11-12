from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ATLAS_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = ATLAS_ROOT.parent
ATLAS_SRC = ATLAS_ROOT / "src"
sys.path.insert(0, str(ATLAS_SRC))

from atlas.history import (  # noqa: E402
    AcknowledgementDisposition,
    AssumptionSelection,
    AtlasEvent,
    ConceptricObject,
    EventKind,
    LifecycleAction,
    LifecyclePhase,
    LifecycleTransition,
    MessageAcknowledgement,
    MessageExpiry,
    MessagePull,
    PermissionDecision,
    PermissionOutcome,
    PermissionRequest,
    ProducerRef,
    ReplEvaluation,
    ReplOperation,
    Residual,
    ResidualStatus,
    SeatAction,
    SeatMessage,
    SeatRole,
    SeatStatus,
    SeatTransition,
    SourceRef,
    Validity,
    WatchCheckpoint,
    WatcherRegistration,
    WatchSourceKind,
    WatchStatus,
)
from atlas.migration import (  # noqa: E402
    ATLAS_MIGRATION_STAGES,
    STAGE_OBJECT_KIND,
    MigrationEventContext,
    MigrationLedger,
    MigrationStage,
)
from atlas.runtime import collect_runtime_receipt  # noqa: E402
from atlas.sensorium.journal_face import (  # noqa: E402
    project_store,
    render_seat_fabric_text,
)
from atlas.store import BlobStore, ConceptricStore  # noqa: E402

DIGEST = "sha256:" + "a" * 64
SOURCE = SourceRef("sensorium-test", DIGEST, "test://sensorium")
PRODUCER = ProducerRef("test-provider", "deterministic", "system-test")
RESIDUAL = Residual(
    ResidualStatus.WITHIN_BOUND,
    0.0,
    0.1,
    "fraction",
    "bounded test residual",
)
RUNTIME = collect_runtime_receipt(REPO_ROOT, observed_at="2026-08-24T12:00:00Z")
ASSUMPTION = "seat-fabric-proof"
FIBRE = "provider-exchange"
MIGRATION_CONTEXT = MigrationEventContext(
    occurred_at="2026-08-24T12:00:00Z",
    correlation_id="correlation:sensorium-migration",
    provenance=(SOURCE,),
    residual=RESIDUAL,
    runtime=RUNTIME,
    producer_ref=PRODUCER,
)


def event(
    kind: EventKind,
    payload: dict,
    *,
    subject: str | None = None,
    causation_ids: tuple[str, ...] = (),
    validity: Validity = Validity.VALID,
    residual: Residual = RESIDUAL,
    assumption: str | None = None,
    fibre: str | None = None,
    actor: SeatRole = SeatRole.EGO,
) -> AtlasEvent:
    return AtlasEvent.create(
        occurred_at="2026-08-24T12:00:00Z",
        kind=kind,
        producer=SeatRole.EGO,
        actor=actor,
        subject=subject or kind.value,
        assumption=assumption,
        fibre=fibre,
        correlation_id="correlation:sensorium",
        causation_ids=causation_ids,
        provenance=(SOURCE,),
        residual=residual,
        runtime=RUNTIME,
        producer_ref=PRODUCER,
        validity=validity,
        payload=payload,
    )


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
            f"holder:{seat_id}",
        ).to_dict(),
        subject=f"seat:{seat_id}",
    )


def bootstrap(store: ConceptricStore, *extra_seats: str) -> None:
    store.append(lifecycle(LifecycleAction.COLD_WAKE, "cold:sensorium-test"))
    store.append(seat("ego-seat", SeatRole.EGO))
    store.append(seat("sensorium-seat", SeatRole.SENSORIUM))
    for seat_id in extra_seats:
        store.append(seat(seat_id, SeatRole.PROVIDER))
    selected = AssumptionSelection(ASSUMPTION, FIBRE, 1.0, ())
    store.append(
        event(
            EventKind.ASSUMPTION,
            selected.to_dict(),
            assumption=ASSUMPTION,
            fibre=FIBRE,
        )
    )


def persistent_store_files(root: Path) -> tuple[Path, ...]:
    """Exclude SQLite's connection-scoped WAL/SHM files from projection artefact checks."""

    return tuple(
        sorted(
            path
            for path in root.iterdir()
            if not path.name.endswith(("-wal", "-shm"))
        )
    )


def send(
    store: ConceptricStore,
    *,
    message_id: str,
    recipient: str,
    message_type: str,
    expires_at: str = "2026-08-24T14:00:00Z",
    causation_ids: tuple[str, ...] = (),
) -> AtlasEvent:
    cursor = store.replay().event_count + 1
    body_handle = BlobStore(store.root / "blobs").put(
        f"sensorium fixture body for {message_id}".encode("utf-8")
    )
    message = SeatMessage(
        message_id,
        "ego-seat",
        recipient,
        message_type,
        body_handle,
        {"record": DIGEST},
        f"idempotency:{message_id}",
        cursor,
        expires_at,
    )
    sent = event(
        EventKind.MESSAGE,
        message.to_dict(),
        subject=f"message:{message_id}",
        causation_ids=causation_ids,
        assumption=ASSUMPTION,
        fibre=FIBRE,
    )
    store.append(sent)
    return sent


def pull(store: ConceptricStore, seat_id: str, *, as_of: str) -> AtlasEvent:
    state = store.replay()
    after = state.cursor_for(seat_id)
    pending = store.pending_messages(seat_id, after_cursor=after, as_of=as_of)
    payload = MessagePull(
        seat_id,
        after,
        state.event_count,
        as_of,
        tuple(item["message_id"] for item in pending),
    )
    pulled = event(
        EventKind.MESSAGE_PULL,
        payload.to_dict(),
        subject=f"pull:{seat_id}",
        assumption=ASSUMPTION,
        fibre=FIBRE,
        actor=SeatRole.PROVIDER,
    )
    store.append(pulled)
    return pulled


class ConceptricProviderFaceTests(unittest.TestCase):
    def test_migration_programme_is_handle_complete_across_fresh_projection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "conceptric"
            store = ConceptricStore(root)
            bootstrap(store)
            migration = MigrationLedger(store)
            migration.declare_all(MIGRATION_CONTEXT)
            migration.set_progress("ATLAS-S0", MIGRATION_CONTEXT, material=True)
            # the walk is HIS: walked=True is structurally reserved for SeatRole.AUTHOR
            # (the migration law, 2026-08-24) — the axes stay separately attributable,
            # material minted by the ego, the walk only ever by the author's own actor.
            migration.set_progress(
                "ATLAS-S0",
                dataclasses.replace(MIGRATION_CONTEXT, actor=SeatRole.AUTHOR),
                walked=True,
            )
            migration.supersede("ATLAS-S0", "ATLAS-S1", MIGRATION_CONTEXT)

            files_before = persistent_store_files(root)
            projection = project_store(root)
            self.assertEqual(files_before, persistent_store_files(root))
            rendered = projection["migration"]
            self.assertEqual(rendered["status"], "VERIFIED")
            self.assertEqual(
                [item["stage_id"] for item in rendered["stages"]],
                list(ATLAS_MIGRATION_STAGES),
            )
            first = rendered["stages"][0]
            self.assertTrue(first["material"])
            self.assertFalse(first["judged"])
            self.assertTrue(first["walked"])
            self.assertEqual(first["superseded_by"], "ATLAS-S1")
            self.assertTrue(first["event_handle"].startswith("sha256:"))
            self.assertTrue(first["content_handle"].startswith("sha256:"))
            self.assertEqual(first["source_handles"][0]["digest"], DIGEST)
            self.assertEqual(
                set(rendered["axes"]), {"material", "judged", "walked"}
            )
            self.assertEqual(
                rendered["axes"]["material"][0]["value"], True
            )
            self.assertEqual(
                rendered["axes"]["judged"][0]["value"], False
            )
            self.assertEqual(
                rendered["axes"]["walked"][0]["value"], True
            )
            self.assertEqual(projection["truth_audit"]["projection_stores"], 0)
            self.assertEqual(projection["truth_audit"]["sensorium_cursors"], 0)

            fresh = project_store(root)
            self.assertEqual(fresh["migration"], rendered)

    def test_missing_migration_stages_are_loud_and_never_imply_progress(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "conceptric"
            store = ConceptricStore(root)
            bootstrap(store)

            projection = project_store(root)
            migration = projection["migration"]
            self.assertEqual(migration["status"], "INCOMPLETE")
            self.assertEqual(migration["stages"], [])
            self.assertEqual(
                migration["missing_stage_ids"], list(ATLAS_MIGRATION_STAGES)
            )
            self.assertEqual(
                migration["residuals"][0]["code"],
                "migration-stage-set-incomplete",
            )
            self.assertEqual(projection["status"], "PARTIAL")

    def test_malformed_migration_stage_refuses_the_entire_migration_face(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "conceptric"
            store = ConceptricStore(root)
            bootstrap(store)
            attributes = MigrationStage("ATLAS-S0").to_dict()
            del attributes["record"]
            malformed = ConceptricObject(
                object_id="migration-stage:malformed",
                kind=STAGE_OBJECT_KIND,
                content_handle=DIGEST,
                assumption=None,
                fibre=None,
                grade_contract_id="axis-contract:atlas-control-topology/1",
                grade_coordinate="fabric",
                provenance=(SOURCE,),
                attributes=attributes,
            )
            store.append(
                event(
                    EventKind.OBJECT,
                    malformed.to_dict(),
                    subject="migration-stage:malformed",
                )
            )

            projection = project_store(root)
            migration = projection["migration"]
            self.assertEqual(migration["status"], "REFUSED")
            self.assertEqual(migration["stages"], [])
            self.assertEqual(migration["axes"]["material"], [])
            self.assertEqual(
                migration["residuals"][0]["code"], "migration-replay-refused"
            )
            self.assertEqual(
                migration["residuals"][0]["reason"], "schema-field-missing"
            )

    def test_renders_lifecycle_permissions_and_accepted_reconstruction_ack(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "conceptric"
            store = ConceptricStore(root)
            bootstrap(store, "provider-seat")

            request = PermissionRequest(
                "permission:judge",
                "provider-seat",
                "judge",
                "handle:jury-work",
                "jury needs bounded authority",
                "2026-08-24T14:00:00Z",
            )
            requested = event(
                EventKind.PERMISSION_REQUEST,
                request.to_dict(),
                assumption=ASSUMPTION,
                fibre=FIBRE,
                actor=SeatRole.PROVIDER,
            )
            store.append(requested)
            decision = PermissionDecision(
                request.request_id,
                "ego-seat",
                PermissionOutcome.GRANTED,
                "bounded to the named handle",
            )
            store.append(
                event(
                    EventKind.PERMISSION_DECISION,
                    decision.to_dict(),
                    causation_ids=(requested.event_id,),
                    assumption=ASSUMPTION,
                    fibre=FIBRE,
                    actor=SeatRole.EGO,
                )
            )

            sent = send(
                store,
                message_id="message:accepted",
                recipient="provider-seat",
                message_type="reconstruct",
            )
            pulled = pull(store, "provider-seat", as_of="2026-08-24T12:30:00Z")
            evaluation = ReplEvaluation(
                "evaluation:reconstruct",
                ReplOperation.RECONSTRUCT,
                (sent.payload["body_handle"],),
                {"record": DIGEST},
                {"goal": "reconstruct accepted work"},
                ("handle:reconstructed",),
                "provider-seat",
                None,
            )
            reconstructed = event(
                EventKind.REPL,
                evaluation.to_dict(),
                subject="reconstruction:accepted",
                causation_ids=(sent.event_id, pulled.event_id),
                assumption=ASSUMPTION,
                fibre=FIBRE,
                actor=SeatRole.PROVIDER,
            )
            store.append(reconstructed)
            acknowledgement = MessageAcknowledgement(
                "message:accepted",
                "provider-seat",
                AcknowledgementDisposition.ACCEPTED,
                "handle:reconstructed",
                reconstructed.event_id,
                "goal-conditioned reconstruction accepted",
            )
            store.append(
                event(
                    EventKind.MESSAGE_ACK,
                    acknowledgement.to_dict(),
                    causation_ids=(sent.event_id, reconstructed.event_id),
                    assumption=ASSUMPTION,
                    fibre=FIBRE,
                    actor=SeatRole.PROVIDER,
                )
            )

            # read-only means the PERSISTENT artifacts are untouched; SQLite's -wal/-shm
            # transients appear and vanish with checkpoints under full-suite ordering and
            # are not part of the store's durable identity (codex full-Atlas receipt,
            # 2026-08-24 — this assertion compared raw iterdir and flaked on them).
            def _persistent(paths):
                return tuple(sorted(p for p in paths
                                    if not p.name.endswith(("-wal", "-shm"))))

            files_before = _persistent(root.iterdir())
            projection = project_store(root)
            files_after = _persistent(root.iterdir())
            self.assertEqual(files_before, files_after)
            self.assertEqual(projection["source"]["authority"], "atlas.conceptric-provider.v1")
            self.assertEqual(projection["source"]["bridge_api"], "atlas.seat-bridge.v1")
            self.assertEqual(projection["source"]["storage_backend"], "sqlite")
            self.assertEqual(
                projection["source"]["database_ref"], str(root / "conceptric.sqlite3")
            )
            self.assertEqual(projection["truth_audit"]["projection_stores"], 0)
            self.assertEqual(projection["truth_audit"]["sensorium_cursors"], 0)
            self.assertFalse(projection["truth_audit"]["second_truth_detected"])
            self.assertEqual(projection["lifecycle"]["current"], "awake")
            self.assertEqual(projection["permissions"][0]["status"], "granted")
            graph = projection["graph_topology"]
            self.assertEqual(graph["schema_version"], "atlas.conceptric-graph.v1")
            self.assertEqual(graph["topology_status"], "VERIFIED")
            self.assertTrue(graph["content_addressed"])
            self.assertEqual(graph["unresolved_endpoints"], [])
            self.assertGreater(graph["object_count"], 0)
            self.assertGreater(graph["edge_count"], 0)
            sessions = projection["provider_session_holders"]
            self.assertTrue(any(item["current"] for item in sessions))
            self.assertTrue(
                any("provider-seat" in item["current_seat_ids"] for item in sessions)
            )
            message = projection["messages"][0]
            self.assertTrue(message["delivered"])
            self.assertTrue(message["acknowledgement"]["accepted"])
            self.assertTrue(message["reconstruction_proof"]["verified_in_history"])
            self.assertEqual(
                message["reconstruction_proof"]["event_id"], reconstructed.event_id
            )
            exchange_chain = projection["message_causal_chains"][0]
            self.assertTrue(exchange_chain["canonical_delivery_proof"])
            self.assertTrue(
                exchange_chain["full_send_pull_reconstruction_ack_chain"]
            )
            self.assertEqual(
                [item["stage"] for item in exchange_chain["stages"]],
                ["send", "pull", "reconstruction", "acknowledgement"],
            )
            completed = subprocess.run(
                [
                    "/usr/bin/python3",
                    "-m",
                    "atlas.sensorium",
                    "--store",
                    str(root),
                    "--format",
                    "json",
                ],
                cwd=REPO_ROOT,
                env={**os.environ, "PYTHONPATH": str(ATLAS_SRC)},
                check=False,
                text=True,
                capture_output=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            restarted = json.loads(completed.stdout)
            self.assertTrue(restarted["messages"][0]["delivered"])
            self.assertTrue(
                restarted["messages"][0]["reconstruction_proof"][
                    "verified_in_history"
                ]
            )

    def test_queued_unacknowledged_and_expired_jury_work_stay_undecided(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "conceptric"
            store = ConceptricStore(root)
            bootstrap(store, "queued-seat", "unacknowledged-seat", "expired-seat")
            send(
                store,
                message_id="jury:queued",
                recipient="queued-seat",
                message_type="jury-work",
            )
            send(
                store,
                message_id="jury:unacknowledged",
                recipient="unacknowledged-seat",
                message_type="jury-work",
            )
            pull(store, "unacknowledged-seat", as_of="2026-08-24T12:30:00Z")
            send(
                store,
                message_id="jury:expired",
                recipient="expired-seat",
                message_type="jury-work",
                expires_at="2026-08-24T12:10:00Z",
            )
            store.append(
                event(
                    EventKind.MESSAGE_EXPIRY,
                    MessageExpiry("jury:expired", "2026-08-24T12:11:00Z").to_dict(),
                    assumption=ASSUMPTION,
                    fibre=FIBRE,
                    actor=SeatRole.SYSTEM,
                )
            )

            projection = project_store(root)
            jury = {item["message_id"]: item for item in projection["jury_work"]}
            self.assertEqual(
                {key: item["provider_status"] for key, item in jury.items()},
                {
                    "jury:queued": "queued",
                    "jury:unacknowledged": "pulled",
                    "jury:expired": "expired",
                },
            )
            self.assertTrue(all(not item["delivered"] for item in jury.values()))
            self.assertTrue(all(not item["decided"] for item in jury.values()))
            self.assertEqual(projection["status"], "PARTIAL")
            exchange_codes = {
                item["code"] for item in projection["exchange_residuals"]
            }
            self.assertEqual(
                exchange_codes,
                {
                    "message-queued-awaiting-pull-reconstruction-ack",
                    "message-pulled-awaiting-reconstruction-ack",
                    "message-expired-undelivered",
                },
            )
            self.assertIsNotNone(jury["jury:unacknowledged"]["pull_event_id"])
            self.assertIsNotNone(jury["jury:expired"]["expiry_event_id"])
            kinds = {item["kind"] for item in projection["causal_chains"]}
            self.assertIn("seat.message-sent", kinds)
            self.assertIn("seat.messages-pulled", kinds)
            self.assertIn("seat.message-expired", kinds)

    def test_watcher_checkpoint_is_durable_dispatch_not_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "conceptric"
            store = ConceptricStore(root)
            bootstrap(store, "watch-target")
            start_cursor = store.replay().event_count
            registration = WatcherRegistration(
                "watcher:jury",
                "ego-seat",
                "watch-target",
                WatchSourceKind.CONCEPTRIC_EVENTS,
                {"event_kind": EventKind.OBSERVATION.value},
                "jury-work",
                False,
                1.0,
                start_cursor,
                "2026-08-24T14:00:00Z",
            )
            registered = event(
                EventKind.WATCHER,
                registration.to_dict(),
                subject="watcher:jury",
                assumption=ASSUMPTION,
                fibre=FIBRE,
            )
            store.append(registered)
            observed = event(
                EventKind.OBSERVATION,
                {"schema_version": "sensorium-watch-observation/1"},
                subject="observation:jury-ready",
                assumption=ASSUMPTION,
                fibre=FIBRE,
            )
            store.append(observed)
            sent = send(
                store,
                message_id="jury:watch-dispatch",
                recipient="watch-target",
                message_type="jury-work",
                causation_ids=(observed.event_id,),
            )
            checkpoint = WatchCheckpoint(
                registration.watcher_id,
                start_cursor,
                store.replay().event_count,
                (observed.event_id,),
                ("jury:watch-dispatch",),
                "2026-08-24T12:30:00Z",
                WatchStatus.FIRED,
                "matching event dispatched to the logical seat",
            )
            checkpointed = event(
                EventKind.WATCH_CHECKPOINT,
                checkpoint.to_dict(),
                subject="watch-checkpoint:jury",
                causation_ids=(registered.event_id, sent.event_id),
                assumption=ASSUMPTION,
                fibre=FIBRE,
                actor=SeatRole.EGO,
            )
            store.append(checkpointed)

            files_before = persistent_store_files(root)
            projection = project_store(root)
            self.assertEqual(files_before, persistent_store_files(root))
            watcher = projection["watchers"][0]
            self.assertEqual(watcher["registration_event_id"], registered.event_id)
            self.assertEqual(watcher["checkpoint_event_id"], checkpointed.event_id)
            self.assertEqual(watcher["checkpoint"]["status"], "fired")
            self.assertFalse(watcher["dispatch_confers_delivery"])
            dispatch = watcher["dispatches"][0]
            self.assertEqual(dispatch["provider_status"], "queued")
            self.assertFalse(dispatch["currently_delivered"])
            self.assertTrue(dispatch["delivery_requires_separate_accepted_ack"])
            message = projection["messages"][0]
            self.assertFalse(message["delivered"])
            self.assertFalse(message["decided"])
            self.assertIn(
                "watcher-dispatch-awaiting-reconstruction-ack",
                {item["code"] for item in projection["watcher_residuals"]},
            )
            graph = projection["graph_topology"]
            self.assertTrue(
                any(
                    item["kind"] == "persistent-watcher"
                    for item in graph["objects"].values()
                )
            )
            self.assertTrue(
                any(
                    item["relation"] == "dispatched-message"
                    for item in graph["edges"].values()
                )
            )

    def test_wake_sew_up_sleep_and_cold_reconstruction_are_visible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "conceptric"
            store = ConceptricStore(root)
            bootstrap(store)
            store.append(lifecycle(LifecycleAction.SEW_UP, "sew:sensorium-test"))
            store.append(lifecycle(LifecycleAction.SLEEP, "sleep:sensorium-test"))

            projection = project_store(root)
            self.assertEqual(projection["lifecycle"]["current"], "sleeping")
            self.assertEqual(
                [item["action"] for item in projection["lifecycle"]["transitions"]],
                ["cold-wake", "sew-up", "sleep"],
            )

    def test_unknown_residual_and_refused_event_are_loud(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "conceptric"
            store = ConceptricStore(root)
            bootstrap(store)
            unknown = Residual(
                ResidualStatus.UNKNOWN,
                None,
                0.1,
                "fraction",
                "jury decision contract remains unknown",
            )
            store.append(
                event(
                    EventKind.OBSERVATION,
                    {"schema_version": "sensorium-test-observation/1"},
                    validity=Validity.REFUSED,
                    residual=unknown,
                )
            )
            projection = project_store(root)
            self.assertEqual(projection["status"], "PARTIAL")
            event_residuals = [
                item
                for item in projection["loud_residuals"]
                if item.get("event_id") == projection["causal_chains"][-1]["event_id"]
            ]
            self.assertEqual(len(event_residuals), 1)
            self.assertEqual(event_residuals[0]["status"], "unknown")
            self.assertEqual(event_residuals[0]["validity"], "refused")

    def test_human_and_json_cli_faces_share_the_same_provider_head(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "conceptric"
            store = ConceptricStore(root)
            bootstrap(store, "jury-seat")
            send(
                store,
                message_id="jury:queued",
                recipient="jury-seat",
                message_type="jury-work",
            )
            projection = project_store(root)
            human = render_seat_fabric_text(projection)
            for marker in (
                "atlas.conceptric-provider.v1",
                "atlas.seat-bridge.v1",
                "sqlite=",
                "CAUSAL CHAINS",
                "CONTENT-ADDRESSED GRAPH TOPOLOGY",
                "PROVIDER SESSION HOLDERS",
                "EXCHANGE",
                "MESSAGE CAUSAL CHAINS",
                "DURABLE WATCHERS / CHECKPOINTS",
                "JURY WORK",
                "PERMISSIONS",
                "ATLAS MIGRATION — HANDLE-COMPLETE / DESCENT ON DEMAND",
                "no Sensorium cursor",
            ):
                self.assertIn(marker, human)
            command = [
                "/usr/bin/python3",
                "-m",
                "atlas.sensorium",
                "--store",
                str(root),
                "--format",
                "json",
            ]
            completed = subprocess.run(
                command,
                cwd=REPO_ROOT,
                env={**os.environ, "PYTHONPATH": str(ATLAS_SRC)},
                check=False,
                text=True,
                capture_output=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            rendered = json.loads(completed.stdout)
            self.assertEqual(
                rendered["source"]["head_event_id"],
                projection["source"]["head_event_id"],
            )
            self.assertFalse(rendered["jury_work"][0]["delivered"])
            self.assertFalse(rendered["jury_work"][0]["decided"])


if __name__ == "__main__":
    unittest.main()
