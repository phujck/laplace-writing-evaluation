"""Acceptance tests for the enforced startup mail gate.

HIS DIRECTIVE, fabric #1067: "Acceptance tests are mandatory, not prose." Each
test below PLANTS the failure it is named for. A gate that cannot be shown
failing is a report, not a gate (WO-20260824-s3-close-is-not-a-gate).

Every test binds a scratch LAPLACE_STATE. None may bind a live production
writer — that is itself one of his acceptance conditions, and it is asserted
mechanically in ``test_no_test_can_bind_a_live_production_writer``.
"""

from __future__ import annotations

import json

import pytest

from laplace.engine import startup_mail_gate as G


@pytest.fixture(autouse=True)
def _scratch_state(tmp_path, monkeypatch):
    monkeypatch.setenv("LAPLACE_STATE", str(tmp_path / "_state"))
    return tmp_path


def _payload(*, pending, seat="claude-seat", watcher_seat="claude-seat",
             watcher_status="ACTIVE", fabric=True):
    fab = {
        "status": "PENDING" if pending else "CLEAR",
        "pending_count": len(pending),
        "pending": [{"message_id": m, "recipient_seat_id": seat} for m in pending],
        "watcher": {"status": watcher_status, "seat_id": watcher_seat,
                    "target_thread_id": "thread-1"},
    }
    return {"seat_fabric": fab} if fabric else {}


class _Fabric:
    """A scripted seat_fabric: every verb answers from planted state."""

    def __init__(self, *, bodies, ack_delivers=True, reconstruct_ok=True, displace=(),
                 initial_status=None, other_context=()):
        self.bodies = dict(bodies)
        self.ack_delivers = ack_delivers
        self.reconstruct_ok = reconstruct_ok
        self.displace = list(displace)
        self.pulls: list[int] = []
        self.acked: list[str] = []
        self.reconstructed: list[str] = []
        self.custody_batches: list[list[str]] = []
        self.statuses = dict(initial_status or {})
        self.other_context = set(other_context)

    def __call__(self, args, root, timeout=240.0):
        verb = args[0]
        if verb == "pull":
            budget = int(args[args.index("--budget") + 1])
            self.pulls.append(budget)
            unknown = [m for m in self.bodies
                       if self.statuses.get(m) == "queued" and self.bodies.get(m) is None]
            if unknown:
                return 0, {
                    "status": "BLOCKED-UNKNOWN-CONTENT",
                    "messages": [],
                    "cursor_advanced": False,
                    "unknown_content": [
                        {"message_id": mid, "content_state": "UNKNOWN", "reason": "BlobMissing"}
                        for mid in unknown
                    ],
                }, ""
            served = [m for m in self.bodies
                      if self.statuses.get(m) == "queued" and m not in self.displace]
            for mid in served:
                self.statuses[mid] = "pulled"
            return 0, {"messages": [{"message_id": m} for m in served],
                       "displaced_count": len(self.displace),
                       "displaced_message_ids": self.displace}, ""
        if verb == "custody-batch":
            mids = [args[index + 1] for index, value in enumerate(args) if value == "--message"]
            self.custody_batches.append(mids)
            rows = []
            for mid in mids:
                if self.statuses.get(mid) == "delivered":
                    rows.append({
                        "message_id": mid, "state": "ALREADY_DELIVERED", "delivered": True,
                    })
                    continue
                self.reconstructed.append(mid)
                if not self.reconstruct_ok or self.bodies.get(mid) is None:
                    rows.append({
                        "message_id": mid, "state": "UNKNOWN", "content_state": "UNKNOWN",
                        "delivered": False, "reason": "store-blob-missing",
                    })
                    continue
                proof = {
                    "body_handle": f"sha256:body-{mid}",
                    "reconstruction_event_id": f"sha256:ev-{mid}",
                    "reconstruction_handle": f"sha256:rh-{mid}",
                }
                self.acked.append(mid)
                if self.ack_delivers:
                    self.statuses[mid] = "delivered"
                rows.append({
                    "message_id": mid,
                    "state": "DELIVERED" if self.ack_delivers else "REFUSED",
                    "delivered": self.ack_delivers,
                    **proof,
                })
            receipt = G._expected_custody_phase(
                seat_id=args[args.index("--seat") + 1],
                goal=args[args.index("--goal") + 1],
                message_ids=mids,
                rows=rows,
            )
            return 0, {
                "schema_version": "laplace.fabric-custody-batch/1",
                "seat_id": args[args.index("--seat") + 1],
                "message_ids": mids,
                "batch_size": len(mids),
                "rows": rows,
                "phase_receipt": receipt,
                "measurements": {
                    "process_count": 1,
                    "store_constructions": 2,
                    "replayed_rows": 200,
                    "wall_seconds": 0.01,
                    "cpu_seconds": 0.01,
                    "batch_size": len(mids),
                },
                "residual": {"crutch": "CR-C1-COLD-STORE-CONSTRUCTION"},
            }, ""
        if verb == "reconstruct":
            mid = args[args.index("--message") + 1]
            self.reconstructed.append(mid)
            if not self.reconstruct_ok or self.bodies.get(mid) is None:
                return 2, None, "store-blob-missing"
            return 0, {"body_handle": f"sha256:body-{mid}",
                       "reconstruction_event_id": f"sha256:ev-{mid}",
                       "reconstruction_handle": f"sha256:rh-{mid}"}, ""
        if verb == "ack":
            mid = args[args.index("--message") + 1]
            self.acked.append(mid)
            if self.ack_delivers:
                self.statuses[mid] = "delivered"
            return 0, {"delivered": self.ack_delivers}, ""
        if verb == "status":
            mid = args[args.index("--message") + 1]
            delivered = self.statuses.get(mid) == "delivered"
            return 0, {"message_id": mid, "delivered": delivered}, ""
        if verb == "obligations":
            rows = []
            for cursor, (mid, status) in enumerate(self.statuses.items(), 1):
                if status not in {"queued", "pulled"}:
                    continue
                context_matches = mid not in self.other_context
                rows.append({
                    "message_id": mid,
                    "cursor": cursor,
                    "recipient_seat_id": args[args.index("--seat") + 1],
                    "status": status,
                    "context_matches": context_matches,
                    "content_state": "READABLE" if self.bodies.get(mid) is not None else "UNKNOWN",
                    "content_error": None if self.bodies.get(mid) is not None else "BlobMissing",
                    "assumption": "one" if context_matches else "old",
                    "fibre": "current" if context_matches else "old",
                })
            return 0, {
                "seat_id": args[args.index("--seat") + 1],
                "obligations": rows,
                "counts": {
                    "total": len(rows),
                    "queued": sum(row["status"] == "queued" for row in rows),
                    "pulled": sum(row["status"] == "pulled" for row in rows),
                    "other_context": sum(not row["context_matches"] for row in rows),
                },
            }, ""
        raise AssertionError(f"unscripted verb {verb}")


def _install(monkeypatch, payload, fabric, *, live_process=False):
    """Bind every ambient input.

    ``live_watcher_process`` shells out to pgrep, so without this the
    wrong-seat test would pass or fail depending on whether a watcher happens
    to be armed on the box at the time - a test whose verdict comes from
    ambient state rather than from the plant. That is the census-fixture
    defect, and it is not allowed to live in the gate's own acceptance suite.
    """
    for message in ((payload or {}).get("seat_fabric") or {}).get("pending", []):
        mid = str(message.get("message_id"))
        if mid in fabric.bodies:
            fabric.statuses.setdefault(mid, "queued")
    monkeypatch.setattr(
        G,
        "wake_payload",
        lambda root, engine=False, seat_id=None: (0, payload, ""),
    )
    monkeypatch.setattr(G, "_run", fabric)
    monkeypatch.setattr(G, "live_watcher_process",
                        lambda seat_id: {"proved_by": "process" if live_process else None,
                                         "matched": bool(live_process)})


def test_wake_subprocess_receives_the_assigned_logical_seat(monkeypatch, tmp_path):
    captured = {}

    class Result:
        returncode = 0
        stdout = "{}"
        stderr = ""

    def run(args, **kwargs):
        captured["args"] = args
        captured["env"] = kwargs["env"]
        return Result()

    monkeypatch.setattr(G.subprocess, "run", run)

    rc, payload, _err = G.wake_payload(
        tmp_path, engine=True, seat_id="superego-seat"
    )

    assert rc == 0 and payload == {}
    assert captured["env"]["LAPLACE_SEAT_ID"] == "superego-seat"
    assert captured["args"][-1] == "--engine"


# -- his acceptance conditions, one test each ------------------------------

def test_planted_three_message_startup_reconstructs_and_acks_all_three(monkeypatch, tmp_path):
    ids = ["message:aaa", "message:bbb", "message:ccc"]
    fab = _Fabric(bodies={m: b"body" for m in ids})
    _install(monkeypatch, _payload(pending=ids), fab)
    rec = G.run_gate(tmp_path, "claude-seat", "goal")
    assert rec["state"] == "MAIL_READY", rec
    assert sorted(fab.reconstructed) == sorted(ids)
    assert sorted(fab.acked) == sorted(ids)
    assert fab.custody_batches == [ids], "all message custody must share one subprocess"
    assert rec["custody_phases"][0]["measurements"]["process_count"] == 1
    for row in rec["delivered"]:
        assert row["body_handle"] and row["reconstruction_event_id"] and row["reconstruction_handle"]


def test_forged_custody_phase_handle_refuses_even_when_rows_look_delivered(monkeypatch, tmp_path):
    mid = "message:" + "a" * 64

    class _ForgedReceipt(_Fabric):
        def __call__(self, args, root, timeout=240.0):
            rc, payload, error = super().__call__(args, root, timeout)
            if args[0] == "custody-batch":
                payload["phase_receipt"]["handle"] = "sha256:" + "0" * 64
            return rc, payload, error

    fab = _ForgedReceipt(bodies={mid: b"body"})
    _install(monkeypatch, _payload(pending=[mid]), fab)

    rec = G.run_gate(tmp_path, "claude-seat", "goal")

    assert rec["state"] == "MAIL_REFUSED"
    assert rec["failed_step"] == "3-custody-batch"
    assert "disagrees" in rec["why"]


def test_reordered_custody_phase_refuses_exact_batch_identity(monkeypatch, tmp_path):
    ids = ["message:" + char * 64 for char in ("a", "b")]

    class _ReorderedReceipt(_Fabric):
        def __call__(self, args, root, timeout=240.0):
            rc, payload, error = super().__call__(args, root, timeout)
            if args[0] == "custody-batch":
                payload["message_ids"] = list(reversed(payload["message_ids"]))
            return rc, payload, error

    fab = _ReorderedReceipt(bodies={mid: b"body" for mid in ids})
    _install(monkeypatch, _payload(pending=ids), fab)

    rec = G.run_gate(tmp_path, "claude-seat", "goal")

    assert rec["state"] == "MAIL_REFUSED"
    assert rec["failed_step"] == "3-custody-batch"
    assert rec["requested_message_ids"] == ids
    assert rec["observed_message_ids"] == list(reversed(ids))


def test_interruption_after_pull_resumes_the_exact_unacked_ids(monkeypatch, tmp_path):
    """A kill between pull and ack must not lose the message: the cursor moved."""
    ids = ["message:aaa", "message:bbb"]
    led = G.ledger_path("claude-seat")
    led.parent.mkdir(parents=True, exist_ok=True)
    led.write_text(json.dumps({"schema_version": "laplace.startup-mail-ledger/1",
                               "seat_id": "claude-seat",
                               "in_flight": {i: {"delivered": False} for i in ids}}))
    # the wake shows NOTHING pending - the cursor already advanced past them
    fab = _Fabric(bodies={m: b"body" for m in ids},
                  initial_status={m: "pulled" for m in ids})
    _install(monkeypatch, _payload(pending=[]), fab)
    rec = G.run_gate(tmp_path, "claude-seat", "goal")
    assert rec["resume_candidates"] == ids
    assert sorted(fab.acked) == sorted(ids), "resumed ids must be acknowledged before new work"
    assert rec["state"] == "MAIL_READY"


def test_wrong_seat_watcher_fails(monkeypatch, tmp_path):
    """Projection names another seat AND no live process carries mine -> refuse."""
    fab = _Fabric(bodies={})
    _install(monkeypatch, _payload(pending=[], watcher_seat="interface-seat"), fab,
             live_process=False)
    rec = G.run_gate(tmp_path, "claude-seat", "goal")
    assert rec["state"] == "MAIL_REFUSED"
    assert rec["failed_step"] == "6-watcher"
    assert "interface-seat" in rec["why"]
    assert "--seat claude-seat" in rec["rearm_required"]


def test_a_live_harness_watcher_proves_the_seat_when_the_projection_cannot(monkeypatch, tmp_path):
    """seat_fabric.watcher is codex's SINGLETON projector; every other seat arms a
    harness task that registers nothing there. Checking only the projection would
    refuse every non-codex seat forever - found on the gate's first live run."""
    fab = _Fabric(bodies={})
    _install(monkeypatch, _payload(pending=[], watcher_seat="codex-seat"), fab,
             live_process=True)
    rec = G.run_gate(tmp_path, "claude-seat", "goal")
    assert rec["state"] == "MAIL_READY"
    assert rec["watcher"]["proved_by"] == "process"
    assert rec["watcher"]["projection_matches"] is False


def test_delivered_is_read_at_whichever_depth_the_transport_reports_it(monkeypatch, tmp_path):
    """The status verb nests {"status": {"delivered": true}}. Reading the top level
    returns None and reports a DELIVERED message as refused - a false red the gate
    produced against the live fabric on its first run."""
    assert G._delivered_of({"status": {"delivered": True}}) is True
    assert G._delivered_of({"status": {"status": "delivered"}}) is True
    assert G._delivered_of({"delivered": True}) is True
    assert G._delivered_of({"status": {"delivered": False}}) is False
    assert G._delivered_of({}) is False
    assert G._delivered_of(None) is False


def test_unavailable_fabric_fails_closed(monkeypatch, tmp_path):
    fab = _Fabric(bodies={})
    _install(monkeypatch, _payload(pending=[], fabric=False), fab)
    rec = G.run_gate(tmp_path, "claude-seat", "goal")
    assert rec["state"] == "MAIL_REFUSED"
    assert rec["failed_step"] == "1-fabric"


def test_budget_cannot_displace_mail(monkeypatch, tmp_path):
    ids = [f"message:{i:03d}" for i in range(9)]
    fab = _Fabric(bodies={m: b"b" for m in ids}, displace=["message:008"])
    _install(monkeypatch, _payload(pending=ids), fab)
    rec = G.run_gate(tmp_path, "claude-seat", "goal")
    assert rec["state"] == "MAIL_REFUSED"
    assert rec["failed_step"] == "2-displacement"
    assert fab.pulls == [9], "one pull, budget >= exact pending count"


def test_stale_nudge_causes_no_duplicate_pull_or_ack(monkeypatch, tmp_path):
    ids = ["message:aaa"]
    fab = _Fabric(bodies={m: b"b" for m in ids})
    _install(monkeypatch, _payload(pending=ids), fab)
    first = G.run_gate(tmp_path, "claude-seat", "goal")
    assert first["state"] == "MAIL_READY"
    # a stale nudge fires again with nothing actually pending
    fab2 = _Fabric(bodies={m: b"b" for m in ids})
    _install(monkeypatch, _payload(pending=[]), fab2)
    second = G.run_gate(tmp_path, "claude-seat", "goal")
    assert second["state"] == "MAIL_READY"
    assert fab2.acked == [], "an already-delivered id must not be re-acked"
    assert fab2.pulls == [], "a stale nudge must not bank a second pull"


def test_one_missing_body_stays_an_authored_unknown_and_siblings_stay_visible(monkeypatch, tmp_path):
    """His ruling: authority and readability are orthogonal. Never poison, never forged."""
    ids = ["message:good1", "message:missing", "message:good2"]
    bodies = {"message:good1": b"b", "message:missing": None, "message:good2": b"b"}
    fab = _Fabric(bodies=bodies)
    _install(monkeypatch, _payload(pending=ids), fab)
    rec = G.run_gate(tmp_path, "claude-seat", "goal")
    unknown = {u["message_id"] for u in rec["unknown_content"]}
    assert unknown == {"message:missing"}
    assert rec["unknown_content"][0]["content_state"] == "UNKNOWN"
    delivered = {d["message_id"] for d in rec["delivered"]}
    assert delivered == set(), "content preflight must not move the cursor over readable siblings"
    assert all(fab.statuses[mid] == "queued" for mid in ids), "the whole epoch remains visible"
    assert rec["state"] == "MAIL_REFUSED"
    assert rec["failed_step"] == "2-pull-content"
    blob = json.dumps(rec).lower()
    for word in G.FORBIDDEN_CONTENT_VOCABULARY:
        assert word not in blob, f"missing content must never be described as {word!r}"


def test_no_test_can_bind_a_live_production_writer(tmp_path, monkeypatch):
    monkeypatch.setenv("LAPLACE_STATE", str(tmp_path / "_state"))
    p = G.ledger_path("claude-seat")
    assert str(tmp_path) in str(p)
    assert ".mcp-gerard" not in str(p)


def test_reconstruction_proof_is_required_before_any_ack(monkeypatch, tmp_path):
    """Reconstruction is not acknowledgement: no proof, no ack."""
    ids = ["message:aaa"]
    fab = _Fabric(bodies={m: b"b" for m in ids}, reconstruct_ok=False)
    _install(monkeypatch, _payload(pending=ids), fab)
    rec = G.run_gate(tmp_path, "claude-seat", "goal")
    assert fab.acked == [], "an ack without reconstruction proof must never be sent"
    assert rec["unknown_content"] and rec["unknown_content"][0]["content_state"] == "UNKNOWN"


def test_ack_that_does_not_deliver_refuses_mail_ready(monkeypatch, tmp_path):
    """Step 4: re-read exact status and REQUIRE delivered=true."""
    ids = ["message:aaa"]
    fab = _Fabric(bodies={m: b"b" for m in ids}, ack_delivers=False)
    _install(monkeypatch, _payload(pending=ids), fab)
    rec = G.run_gate(tmp_path, "claude-seat", "goal")
    assert rec["state"] == "MAIL_REFUSED"
    assert rec["failed_step"] == "4-acknowledge"
    assert rec["undelivered"] == ids


def test_an_already_delivered_id_is_not_reconstructed_into_a_false_unknown(monkeypatch, tmp_path):
    """A resumed id may already be terminal. Re-reconstructing it refuses, and filing
    that refusal as UNKNOWN invents an unknown where the transport holds a known -
    found live, on two ids the gate's own ledger was carrying."""
    ids = ["message:done"]
    led = G.ledger_path("claude-seat")
    led.parent.mkdir(parents=True, exist_ok=True)
    led.write_text(json.dumps({"schema_version": "laplace.startup-mail-ledger/1",
                               "seat_id": "claude-seat",
                               "in_flight": {"message:done": {"delivered": False}}}))

    class _AlreadyDelivered(_Fabric):
        def __call__(self, args, root, timeout=240.0):
            if args[0] == "custody-batch":
                for index, value in enumerate(args):
                    if value == "--message":
                        self.statuses[args[index + 1]] = "delivered"
            if args[0] == "status":
                self.statuses[args[2]] = "delivered"
                return 0, {"message_id": args[2], "status": {"delivered": True,
                                                             "status": "delivered"}}, ""
            return super().__call__(args, root, timeout)

    fab = _AlreadyDelivered(
        bodies={"message:done": None},
        initial_status={"message:done": "pulled"},
    )   # the canonical row exists, but the concurrent terminal act wins before descent
    _install(monkeypatch, _payload(pending=[]), fab, live_process=True)
    rec = G.run_gate(tmp_path, "claude-seat", "goal")
    assert rec["already_delivered"] == ids
    assert rec["unknown_content"] == [], "a delivered id must never be filed as UNKNOWN"
    assert fab.reconstructed == [], "a delivered id must not be reconstructed again"
    assert rec["state"] == "MAIL_READY"


def test_stale_side_ledger_row_cannot_create_phantom_work(monkeypatch, tmp_path):
    """The compatibility file is a mirror, never authority over Atlas."""
    led = G.ledger_path("claude-seat")
    led.parent.mkdir(parents=True, exist_ok=True)
    led.write_text(json.dumps({
        "schema_version": "laplace.startup-mail-ledger/1",
        "seat_id": "claude-seat",
        "in_flight": {"message:phantom": {"delivered": False}},
    }))
    fab = _Fabric(bodies={"message:phantom": b"stale-side-copy"})
    _install(monkeypatch, _payload(pending=[]), fab, live_process=True)

    rec = G.run_gate(tmp_path, "claude-seat", "goal")

    assert rec["state"] == "MAIL_READY"
    assert rec["side_ledger_stale"] == ["message:phantom"]
    assert rec["resume_candidates"] == []
    assert fab.pulls == [] and fab.reconstructed == [] and fab.acked == []
    assert json.loads(led.read_text())["in_flight"] == {}


def test_nonterminal_obligation_on_another_fibre_refuses_explicitly(monkeypatch, tmp_path):
    """Context transport must never make old unacknowledged mail disappear."""
    mid = "message:old-fibre"
    fab = _Fabric(
        bodies={mid: b"old meaning"},
        initial_status={mid: "pulled"},
        other_context={mid},
    )
    _install(monkeypatch, _payload(pending=[]), fab, live_process=True)

    rec = G.run_gate(tmp_path, "claude-seat", "goal")

    assert rec["state"] == "MAIL_REFUSED"
    assert rec["failed_step"] == "2-context-obligations"
    assert [row["message_id"] for row in rec["other_context_obligations"]] == [mid]
    assert fab.reconstructed == [] and fab.acked == []


def test_canonical_face_cannot_leak_another_recipients_mail(monkeypatch, tmp_path):
    """A provider projection bug must fail closed before any pull or acknowledgement."""
    mid = "message:mine"

    class _LeakingFace(_Fabric):
        def __call__(self, args, root, timeout=240.0):
            rc, payload, error = super().__call__(args, root, timeout)
            if args[0] == "obligations" and payload["obligations"]:
                payload["obligations"][0]["recipient_seat_id"] = "interface-seat"
            return rc, payload, error

    fab = _LeakingFace(bodies={mid: b"mine"}, initial_status={mid: "queued"})
    _install(monkeypatch, _payload(pending=[]), fab, live_process=True)

    rec = G.run_gate(tmp_path, "claude-seat", "goal")

    assert rec["state"] == "MAIL_REFUSED"
    assert rec["failed_step"] == "2-obligations"
    assert "another recipient" in rec["why"]
    assert fab.pulls == [] and fab.acked == []


def test_message_arriving_during_gate_is_drained_in_a_second_epoch(monkeypatch, tmp_path):
    """A single empty recheck is not assumed when a new canonical cursor appears."""
    first, late = "message:first", "message:late"

    class _Arrival(_Fabric):
        obligation_calls = 0

        def __call__(self, args, root, timeout=240.0):
            if args[0] == "obligations":
                self.obligation_calls += 1
                # call 1 enumerates queued first; call 2 sees it pulled; call 3 is the
                # post-ack clear check. Plant a distinct cursor epoch at that seam.
                if self.obligation_calls == 3:
                    self.statuses[late] = "queued"
            return super().__call__(args, root, timeout)

    fab = _Arrival(bodies={first: b"first", late: b"late"})
    _install(monkeypatch, _payload(pending=[first]), fab, live_process=True)

    rec = G.run_gate(tmp_path, "claude-seat", "goal")

    assert rec["state"] == "MAIL_READY", rec
    assert fab.pulls == [1, 1]
    assert fab.reconstructed == [first, late]
    assert fab.acked == [first, late]
    assert [row["served"] for row in rec["pull_rounds"]] == [[first], [late]]


# -- codex's repair directive: PID+seat is necessary but INSUFFICIENT ------
# "a planted queued message must either cause observed_cursor/information_state
#  to advance or the canonical exact inbox/drain path must remain armed;
#  ACTIVE-but-faulting and non-acquired spare-lock clean exit must REFUSE."

def _wedged_payload(*, pending, observed_cursor, ceiling, info_state="caught-up",
                    watcher_seat="claude-seat"):
    return {"seat_fabric": {
        "status": "PENDING" if pending else "CLEAR",
        "pending_count": len(pending),
        "pending": [{"message_id": m, "recipient_seat_id": "claude-seat"} for m in pending],
        "pending_cursor_ceiling": ceiling,
        "watcher": {"status": "ACTIVE", "seat_id": watcher_seat,
                    "observed_cursor": observed_cursor,
                    "information_state": info_state,
                    "target_thread_id": "t"}}}


def test_active_but_faulting_watcher_refuses(monkeypatch, tmp_path):
    """codex_seat_watcher.py:295 derives ACTIVE from _pid_alive alone, so a wedged
    singleton reports ACTIVE and 'caught-up' while real mail sits unread. A liveness
    claim is not an information claim: the cursor must corroborate it."""
    ids = ["message:stuck"]
    # the message is pending, the watcher is ACTIVE and bound and claims caught-up,
    # but its cursor is behind the ceiling and the drain moves nothing.
    # Wake carries a stale nudge but Atlas has no canonical obligation, so the drain
    # cannot be credited with moving information on behalf of the wedged watcher.
    fab = _Fabric(bodies={})
    _install(monkeypatch, _wedged_payload(pending=ids, observed_cursor=900, ceiling=1000),
             fab, live_process=True)
    rec = G.run_gate(tmp_path, "claude-seat", "goal")
    assert rec["state"] == "MAIL_REFUSED"
    assert rec["failed_step"] == "6-information"
    info = rec["information_proof"]
    assert info["informed"] is False
    assert info["cursor_current"] is False
    assert info["claims_caught_up_without_cursor"] is True, \
        "the wedged singleton's own 'caught-up' string must be called out"
    assert "liveness claim, not an information claim" in rec["why"]


def test_non_acquired_spare_lock_clean_exit_refuses(monkeypatch, tmp_path):
    """codex_seat_watcher.py:425-428 treats a non-acquired lifetime lock as a clean
    exit (rc 0). A spare that never became canonical must not read as armed: it is
    a live PID bound to the seat that will never observe anything."""
    ids = ["message:queued"]
    fab = _Fabric(bodies={})
    # the spare published NO cursor at all - it never became canonical
    _install(monkeypatch, _wedged_payload(pending=ids, observed_cursor=None, ceiling=1000,
                                          info_state=""), fab, live_process=True)
    rec = G.run_gate(tmp_path, "claude-seat", "goal")
    assert rec["state"] == "MAIL_REFUSED"
    assert rec["failed_step"] == "6-information"
    assert rec["information_proof"]["observed_cursor"] is None
    assert rec["information_proof"]["proved_by"] is None


def test_cursor_that_reaches_the_ceiling_is_a_real_proof(monkeypatch, tmp_path):
    """The positive control: the same wedged shape, cursor caught up, must PASS -
    otherwise the two refusals above prove nothing."""
    fab = _Fabric(bodies={})
    _install(monkeypatch, _wedged_payload(pending=[], observed_cursor=1000, ceiling=1000),
             fab, live_process=True)
    rec = G.run_gate(tmp_path, "claude-seat", "goal")
    assert rec["state"] == "MAIL_READY"
    assert rec["information_proof"]["proved_by"] == "watcher-cursor-current"


def test_a_drain_that_moved_mail_is_a_real_proof(monkeypatch, tmp_path):
    """The harness-watcher case: fabric_watch publishes no cursor, so the proof is
    that THIS run's canonical drain path actually moved mail."""
    ids = ["message:aaa"]
    fab = _Fabric(bodies={m: b"b" for m in ids})
    _install(monkeypatch, _wedged_payload(pending=ids, observed_cursor=None, ceiling=1000,
                                          info_state=""), fab, live_process=True)
    rec = G.run_gate(tmp_path, "claude-seat", "goal")
    assert rec["state"] == "MAIL_READY"
    assert rec["information_proof"]["proved_by"] == "drain-path-moved-mail"


def test_another_seats_healthy_cursor_never_proves_mine(monkeypatch, tmp_path):
    """seat_fabric.watcher is codex's SINGLETON. An unscoped cursor read credits
    codex's healthy watcher to whoever asks. Found on a live run of this amendment."""
    ids = ["message:mine"]
    fab = _Fabric(bodies={})
    _install(monkeypatch, _wedged_payload(pending=ids, observed_cursor=1000, ceiling=1000,
                                          watcher_seat="codex-seat"), fab, live_process=True)
    rec = G.run_gate(tmp_path, "claude-seat", "goal")
    info = rec["information_proof"]
    assert info["projection_is_mine"] is False
    assert info["cursor_current"] is False, "codex's cursor must not prove claude-seat"
    assert rec["state"] == "MAIL_REFUSED"
    assert rec["failed_step"] == "6-information"


def test_another_seats_backlog_never_blocks_mine(monkeypatch, tmp_path):
    """seat_fabric.pending_count is the ALL-SEATS diagnostic. Reading it makes any
    other seat's backlog look like this seat's, and the gate would refuse forever
    whenever anyone else had mail. Found on a live run."""
    payload = {"seat_fabric": {
        "status": "PENDING", "pending_count": 67,
        "pending": [{"message_id": "message:theirs", "recipient_seat_id": "interface-seat"}],
        "pending_cursor_ceiling": 1000,
        "watcher": {"status": "ACTIVE", "seat_id": "codex-seat", "observed_cursor": 1000,
                    "information_state": "caught-up", "target_thread_id": "t"}}}
    fab = _Fabric(bodies={})
    _install(monkeypatch, payload, fab, live_process=True)
    rec = G.run_gate(tmp_path, "claude-seat", "goal")
    info = rec["information_proof"]
    assert info["my_pending"] == 0
    assert info["nothing_to_move"] is True
    assert info["proved_by"] == "fabric-reports-zero-pending"
    assert rec["state"] == "MAIL_READY"


def test_mail_ready_banks_a_separate_observational_join(monkeypatch, tmp_path):
    from laplace.representation import atlas_bridge

    fab = _Fabric(bodies={})
    _install(monkeypatch, _payload(pending=[]), fab, live_process=True)
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "session-1")
    calls = []

    def join(**kwargs):
        calls.append(kwargs)
        return {
            "schema_version": "laplace.atlas-seat-bridge.v1",
            "receipt": {"kind": "seat.joined"},
            "occupancy": {"routing_authority": False},
        }

    monkeypatch.setattr(atlas_bridge, "seat_join", join)
    rec = G.run_gate(
        tmp_path,
        "claude-seat",
        "reconstruct the interface coordinate",
        record_join=True,
        holder_ref="claude:session-1",
        function="superego",
        provider="claude",
        model="judge",
    )

    assert rec["state"] == "MAIL_READY"
    assert rec["holder_ref"] == "claude:session-1"
    assert rec["function"] == "superego"
    assert rec["seat_join"]["receipt"]["kind"] == "seat.joined"
    assert calls[0]["holder_ref"] == "claude:session-1"
    assert calls[0]["function"] == "superego"
    assert calls[0]["information_proof"]["state"] == "MAIL_READY"
    assert calls[0]["information_proof"]["provider_identity"]["state"] == "OBSERVATIONAL"
    assert "seat_join" not in calls[0]["information_proof"]


def test_real_startup_gate_renews_then_hands_over_to_a_new_provider_task(
    monkeypatch,
    tmp_path,
    capsys,
):
    from laplace.representation import atlas_bridge, codex_seat_watcher

    atlas_bridge.lifecycle(
        action="cold-wake",
        receipt_id="cold:startup-generation-renewal",
        provider="codex",
        model="test",
    )
    atlas_bridge.seat_transition(
        seat_id="sensorium-seat",
        role="sensorium",
        action="found",
        charter_ref="charter:sensorium",
        holder_ref="logical:sensorium-seat",
        provider="codex",
        model="test",
    )
    atlas_bridge.select_context(
        assumption="seat-fabric-is-one-conceptric",
        fibre="provider-exchange",
        provider="codex",
        model="test",
        confidence=1.0,
    )
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-1")
    watcher = {
        "status": "ACTIVE",
        "seat_id": "sensorium-seat",
        "target_thread_id": "thread-1",
        "lease_generation": "lease:thread-1:1",
        "pid": 42,
        "interval_seconds": 0.5,
    }
    handover_samples = []

    def projection(seat_id):
        sample = dict(watcher)
        if sample["target_thread_id"] == "thread-2":
            handover_samples.append(len(handover_samples))
            if len(handover_samples) == 2:
                sample.update(
                    status="STALE",
                    action="watcher information checkpoint is outside its freshness bound",
                )
        return sample

    monkeypatch.setattr(codex_seat_watcher, "projection", projection)
    monkeypatch.setattr(
        atlas_bridge.time,
        "sleep",
        lambda seconds: None,
    )
    fabric = _Fabric(bodies={})
    _install(
        monkeypatch,
        _payload(
            pending=[],
            seat="sensorium-seat",
            watcher_seat="sensorium-seat",
        ),
        fabric,
        live_process=True,
    )

    def gate() -> dict[str, object]:
        return G.run_gate(
            tmp_path,
            "sensorium-seat",
            "renew through the real startup gate",
            record_join=True,
            holder_ref="codex:thread-1",
            function="sensorium",
            provider="codex",
            model="test",
        )

    first = gate()
    assert first["state"] == "MAIL_READY"
    first_binding = first["seat_join"]["binding_receipt"]["event_id"]

    watcher["lease_generation"] = "lease:thread-1:2"
    second = gate()
    assert second["state"] == "MAIL_READY", second
    assert second["seat_join"]["renewed"] is True
    assert second["seat_join"]["predecessor_binding_event_id"] == first_binding
    assert second["seat_join"]["provider_identity_generation"] == "lease:thread-1:2"
    assert second["seat_join"]["occupancy"]["retired_binding_event_ids"] == [
        first_binding
    ]
    second_binding = second["seat_join"]["binding_receipt"]["event_id"]

    event_count = atlas_bridge.snapshot()["provider"]["event_count"]
    repeated = gate()
    assert repeated["state"] == "MAIL_READY"
    assert repeated["seat_join"]["idempotent"] is True
    assert atlas_bridge.snapshot()["provider"]["event_count"] == event_count

    monkeypatch.setenv("CODEX_THREAD_ID", "thread-2")
    watcher["target_thread_id"] = "thread-2"
    watcher["lease_generation"] = "lease:thread-2:1"
    rc = G.main(
        [
            "--root",
            str(tmp_path),
            "--seat",
            "sensorium-seat",
            "--goal",
            "perform the typed provider holder handover",
            "--holder-ref",
            "codex:thread-2",
            "--function",
            "sensorium",
            "--provider",
            "codex",
            "--model",
            "test",
        ]
    )
    handover = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert handover["state"] == "MAIL_READY"
    assert handover_samples == [0, 1, 2]
    assert handover["seat_join"]["provider_identity_attestation"][
        "stabilization_attempted"
    ] is True
    assert handover["seat_join"]["holder_replaced"] is True
    assert handover["seat_join"]["predecessor_binding_event_id"] == second_binding
    assert handover["seat_join"]["retired_provider_identity_generation"] == (
        "lease:thread-1:2"
    )
    assert handover["seat_join"]["occupancy"]["retired_binding_event_ids"] == [
        first_binding,
        second_binding,
    ]
    provider = atlas_bridge.snapshot()["provider"]
    assert provider["event_count"] == event_count + 2
    assert provider["seat_occupancy"]["sensorium-seat"][
        "current_provider_identity_generation"
    ] == "lease:thread-2:1"
    assert atlas_bridge.provider_seat_binding(
        provider_session_ref="codex:thread-1"
    )["status"] == "UNBOUND"
    assert atlas_bridge.provider_seat_binding(
        provider_session_ref="codex:thread-2"
    )["status"] == "BOUND"


def test_caller_holder_override_cannot_author_provider_identity(monkeypatch, tmp_path):
    fab = _Fabric(bodies={})
    _install(monkeypatch, _payload(pending=[]), fab, live_process=True)
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "actual-session")

    rec = G.run_gate(
        tmp_path,
        "claude-seat",
        "goal",
        record_join=True,
        holder_ref="claude:caller-invention",
        function="superego",
    )

    assert rec["state"] == "MAIL_REFUSED"
    assert rec["failed_step"] == "9-seat-identity"
    assert rec["provider_identity"]["state"] == "REFUSED"


def test_mail_ready_without_session_identity_refuses_the_join(monkeypatch, tmp_path):
    fab = _Fabric(bodies={})
    _install(monkeypatch, _payload(pending=[]), fab, live_process=True)
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)

    rec = G.run_gate(
        tmp_path,
        "claude-seat",
        "goal",
        record_join=True,
        function="superego",
    )

    assert rec["state"] == "MAIL_REFUSED"
    assert rec["failed_step"] == "9-seat-identity"
    assert "no exact task or session identity" in rec["why"]


def test_claude_code_session_identity_is_the_live_holder_surface(monkeypatch):
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "live-claude-session")

    assert G.inferred_holder_ref() == "claude:live-claude-session"


def test_legacy_claude_session_identity_remains_a_fallback(monkeypatch):
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    monkeypatch.setenv("CLAUDE_SESSION_ID", "legacy-claude-session")

    assert G.inferred_holder_ref() == "claude:legacy-claude-session"
