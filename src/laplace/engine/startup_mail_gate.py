"""The enforced startup mail gate — MAIL_READY or a refusal, never advice.

HIS DIRECTIVE, 2026-08-25 (fabric #1067, assigned to claude-seat): "Replace
advice-only startup with this enforced sequence... NO substantive tool, edit,
verdict, dispatch, or priority claim may run before MAIL_READY."

WHAT WENT WRONG THAT THIS EXISTS TO STOP, in his words: a seat "propagated a
stale subagent drain result without rerunning it, left 17/19 inbound messages
unacknowledged, and labelled Gerard-authored UNKNOWN bodies poison/forged. This
is not merely Fabric jank; it is a failure to execute the transport contract."

THE THREE SEPARATIONS THE OLD STARTUP BLURRED, and each is a distinct step here:

    CURSOR ADVANCE IS NOT READING.
    DRAINING IS NOT RECONSTRUCTION.
    RECONSTRUCTION IS NOT ACKNOWLEDGEMENT.

A watcher nudge is never delivery. A subagent report is a candidate, never a
transport fact.

WHY ATLAS IS THE LEDGER (step 5): a process killed between pull and acknowledgement
leaves messages whose cursor has advanced, so they will never be served by a later
pull. The canonical message state nevertheless remains PULLED and nonterminal.
Startup enumerates those exact Atlas rows across every fibre and resumes them before
new work. The old side file remains only as a disposable compatibility mirror; it
cannot create work, hide work, or override canonical state.

WHY MISSING CONTENT IS NEVER "POISON" (step 8, his ruling): authority and content
readability are ORTHOGONAL. An author-originated envelope whose blob is missing
remains an AUTHOR ACT whose content is UNKNOWN. It is not forged, it is not
poison, and it licenses no retraction. This module carries that vocabulary in
code so a reader cannot reach for the other one.

RETIREMENT: this organ dies when the transport itself refuses to advance a cursor
over a message that was never reconstructed — at that point the ledger has no
work to do and the gate is a tautology.
"""

from __future__ import annotations
from laplace.core.checkout import state_root

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

PY = "/usr/bin/python3"

#: the vocabulary a missing body is allowed to use. His ruling, fabric #1049/#1067.
UNKNOWN_CONTENT_STATE = "UNKNOWN"
#: the vocabulary it is NEVER allowed to use, asserted so a grep finds this note.
FORBIDDEN_CONTENT_VOCABULARY = ("poison", "forged", "forgery", "retract")

_TERMINAL = ("MAIL_READY", "MAIL_REFUSED")
COLD_STORE_CRUTCH = "CR-C1-COLD-STORE-CONSTRUCTION"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def inferred_holder_ref() -> str:
    """Return the provider's exact task/session identity, never a logical-seat label."""

    thread_id = os.environ.get("CODEX_THREAD_ID", "").strip()
    if thread_id:
        return f"codex:{thread_id}"
    # Claude Code exports CLAUDE_CODE_SESSION_ID on the live hook surface.  Retain the older
    # CLAUDE_SESSION_ID spelling as a compatibility fallback for direct/legacy launchers, but
    # never require a live provider to invent the variable our own hook documentation named.
    session_id = (
        os.environ.get("CLAUDE_CODE_SESSION_ID", "").strip()
        or os.environ.get("CLAUDE_SESSION_ID", "").strip()
    )
    if session_id:
        return f"claude:{session_id}"
    return ""


def provider_identity_proof(
    seat_id: str,
    *,
    requested_holder_ref: str = "",
) -> dict[str, Any]:
    """Derive provider-session identity from the live provider surface.

    ``--holder-ref`` is a consistency assertion, never an identity source.  Codex
    authority additionally requires this logical seat's watcher to be actively
    bound to the same task.  Claude currently has no equivalent independent
    attestor, so its exact environment identity may join observationally but
    cannot acquire routing authority.
    """

    derived = inferred_holder_ref()
    requested = requested_holder_ref.strip()
    if requested and requested != derived:
        return {
            "schema_version": "laplace.provider-session-identity/1",
            "state": "REFUSED",
            "provider_session_ref": derived or None,
            "requested_holder_ref": requested,
            "reason": "caller holder override disagrees with the provider-derived session",
        }
    if not derived:
        return {
            "schema_version": "laplace.provider-session-identity/1",
            "state": "UNAVAILABLE",
            "provider_session_ref": None,
            "requested_holder_ref": requested or None,
            "reason": "provider exported no exact task or session identity",
        }

    provider_name, _, provider_id = derived.partition(":")
    base = {
        "schema_version": "laplace.provider-session-identity/1",
        "provider_session_ref": derived,
        "requested_holder_ref": requested or None,
        "provider": provider_name,
    }
    if provider_name != "codex":
        return {
            **base,
            "state": "OBSERVATIONAL",
            "identity_kind": f"{provider_name}-environment-session",
            "reason": "no independent provider-specific task attestor is wired yet",
        }

    try:
        from laplace.representation import codex_seat_watcher

        watcher = codex_seat_watcher.projection(seat_id)
    except Exception as exc:  # noqa: BLE001 - absence of the attestor fails closed
        return {
            **base,
            "state": "UNVERIFIED",
            "identity_kind": "codex-thread-watcher-binding",
            "reason": f"Codex watcher attestation unavailable: {type(exc).__name__}: {exc}",
        }
    verified = (
        watcher.get("status") == "ACTIVE"
        and watcher.get("seat_id") == seat_id
        and watcher.get("target_thread_id") == provider_id
        and bool(watcher.get("lease_generation"))
    )
    return {
        **base,
        "state": "VERIFIED" if verified else "UNVERIFIED",
        "identity_kind": "codex-thread-watcher-binding",
        "watcher_seat_id": watcher.get("seat_id"),
        "watcher_target_thread_id": watcher.get("target_thread_id"),
        "watcher_lease_generation": watcher.get("lease_generation"),
        "watcher_pid": watcher.get("pid"),
        "watcher_status": watcher.get("status"),
        "watcher_action": watcher.get("action"),
        "watcher_bound_at": watcher.get("bound_at"),
        "watcher_checked_at": watcher.get("checked_at"),
        "watcher_interval_seconds": watcher.get("interval_seconds"),
        "watcher_observed_cursor": watcher.get("observed_cursor"),
        "watcher_authority_cursor": watcher.get("authority_cursor"),
        "watcher_authority_error": watcher.get("authority_error"),
        "watcher_information_state": watcher.get("information_state"),
        "watcher_last_error": watcher.get("last_error"),
        "watcher_implementation_error": watcher.get("implementation_error"),
        "reason": (
            None
            if verified
            else "live Codex watcher status "
            f"{watcher.get('status')!r}: {watcher.get('action') or 'identity is not active'}"
        ),
    }


def _state_dir() -> Path:
    return state_root()


def ledger_path(seat_id: str) -> Path:
    """One in-flight startup ledger per seat, keyed by message id (step 5)."""
    return _state_dir() / f"startup-mail-ledger.{seat_id}.json"


def _read_ledger(seat_id: str) -> dict[str, Any]:
    p = ledger_path(seat_id)
    if not p.is_file():
        return {"schema_version": "laplace.startup-mail-ledger/1", "seat_id": seat_id, "in_flight": {}}
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001 - a corrupt ledger must not wedge startup; it re-earns its rows
        return {"schema_version": "laplace.startup-mail-ledger/1", "seat_id": seat_id,
                "in_flight": {}, "prior_ledger_unreadable": True}


def _write_ledger(seat_id: str, led: dict[str, Any]) -> None:
    p = ledger_path(seat_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(led, indent=1, sort_keys=True))
    os.replace(tmp, p)


def _run(args: list[str], root: Path, timeout: float = 240.0) -> tuple[int, Any, str]:
    """Run a seat_fabric verb and return (rc, parsed-json-or-None, stderr)."""
    proc = subprocess.run([PY, "scripts/seat_fabric.py", *args], cwd=str(root),
                          capture_output=True, text=True, timeout=timeout)
    try:
        return proc.returncode, json.loads(proc.stdout), proc.stderr
    except Exception:  # noqa: BLE001 - a non-JSON body is itself the diagnosis
        return proc.returncode, None, (proc.stderr or proc.stdout)[-400:]


def _refuse(step: str, why: str, **extra: Any) -> dict[str, Any]:
    return {"schema_version": "laplace.startup-mail-gate/1", "state": "MAIL_REFUSED",
            "failed_step": step, "why": why, "observed_at": _now(), **extra}


def _canonical_handle(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _expected_custody_phase(
    *, seat_id: str, goal: str, message_ids: list[str], rows: list[dict[str, Any]]
) -> dict[str, Any]:
    semantic = {
        "schema_version": "laplace.fabric-custody-phase/1",
        "phase": "pulled-message-custody",
        "seat_id": seat_id,
        "goal_handle": "sha256:" + hashlib.sha256(goal.encode("utf-8")).hexdigest(),
        "message_ids": message_ids,
        "batch_size": len(message_ids),
        "ordered_semantics": [
            "exact-status-preflight",
            "typed-reconstruction",
            "accepted-acknowledgement",
            "exact-delivery-confirmation",
        ],
        "results": [dict(row) for row in rows],
    }
    return {**semantic, "handle": _canonical_handle(semantic)}


# --------------------------------------------------------------------------
# step 1 — the wake, and the watcher binding it must assert
# --------------------------------------------------------------------------

def wake_payload(
    root: Path, engine: bool = False, *, seat_id: str = ""
) -> tuple[int, Any, str]:
    args = [PY, "scripts/wake.py", "--grade", "0"] + (["--engine"] if engine else [])
    env = dict(os.environ)
    if seat_id:
        env["LAPLACE_SEAT_ID"] = seat_id
    proc = subprocess.run(
        args,
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    try:
        return proc.returncode, json.loads(proc.stdout), proc.stderr
    except Exception:  # noqa: BLE001
        return proc.returncode, None, (proc.stderr or proc.stdout)[-400:]


def _delivered_of(stat: Any) -> bool:
    """True only if the transport itself says delivered, at whichever depth it says it."""
    if not isinstance(stat, dict):
        return False
    if stat.get("delivered") is True:
        return True
    inner = stat.get("status")
    if isinstance(inner, dict):
        return inner.get("delivered") is True or str(inner.get("status") or "") == "delivered"
    return str(inner or "") == "delivered"


def live_watcher_process(seat_id: str) -> dict[str, Any]:
    """Is a fabric_watch harness task alive AND bound to this seat?

    ``seat_fabric.watcher`` is codex's SINGLETON transport projector - it names
    codex-seat and nothing else registers there. Every other seat arms a
    harness-tracked ``fabric_watch.py --seat <id>`` which registers nothing in
    the fabric. Checking only the fabric projection therefore refuses every
    non-codex seat forever; checking only the process misses codex. Accept
    either, and say WHICH proved it.
    """
    try:
        out = subprocess.run(["pgrep", "-af", "fabric_watch"], capture_output=True,
                             text=True, timeout=20).stdout
    except Exception:  # noqa: BLE001 - no pgrep is "unproven", never "armed"
        return {"proved_by": None, "matched": False}
    want = f"--seat {seat_id}"
    for line in out.splitlines():
        if "fabric_watch" in line and want in line and "pgrep" not in line:
            return {"proved_by": "process", "matched": True, "line": line[:120]}
    return {"proved_by": None, "matched": False}


def watcher_information_proof(payload: dict[str, Any], seat_id: str,
                              drain_progressed: bool) -> dict[str, Any]:
    """Step 6, amended: LIVENESS IS NOT A PROOF. Information progress is.

    His seat and codex both hit the same wall from opposite sides: the
    atlas-watcher ran seven hours ACTIVE, polling and logging, blocked on a
    fibre mismatch, carrying ZERO information; and codex_seat_watcher derives
    ACTIVE from ``_pid_alive`` alone (codex_seat_watcher.py:295), so an
    ACTIVE-but-faulting singleton reports "caught-up" while real mail sits
    unread AND retires the only fallback (fabric_watch.py:76-86 gates solely on
    status == ACTIVE). A spare that fails to acquire the lifetime lock exits 0
    (:425-428) and looks like a clean success.

    So a PID bound to the right seat is NECESSARY AND INSUFFICIENT. MAIL_READY
    additionally requires evidence that mail can actually MOVE, which is either:

      A. the watcher's own observed_cursor is current with the pending epoch, or
      B. this run's canonical drain path itself moved mail (pulled, reconstructed
         and acknowledged, or confirmed already-terminal against the transport).

    B is what covers a harness-tracked ``fabric_watch`` task, which publishes no
    cursor of its own. Neither A nor B can be satisfied by a process that is
    merely alive.
    """
    fab = (payload or {}).get("seat_fabric") or {}
    w = fab.get("watcher") or {}
    ceiling = fab.get("pending_cursor_ceiling") or fab.get("caused_by_event_cursor")
    observed = w.get("observed_cursor")
    info_state = str(w.get("information_state") or "")

    # THE CURSOR ONLY PROVES THE SEAT IT BELONGS TO. seat_fabric.watcher is codex's
    # singleton, so an unscoped read credits codex's healthy cursor to whoever asks -
    # found on a live run of this very amendment, where a refused claude-seat still
    # reported cursor_current=True off codex's projection.
    projection_is_mine = str(w.get("seat_id") or "") == seat_id
    cursor_current = (
        projection_is_mine and observed is not None and ceiling is not None
        and int(observed) >= int(ceiling)
    )
    # "caught-up" is only trusted when a cursor corroborates it: the faulting
    # singleton reports exactly that string while wedged.
    claims_caught_up = info_state == "caught-up"
    # A fabric asserting ZERO pending for this seat is a POSITIVE statement about
    # the epoch, not an absence of one - distinct from "nothing was checked". The
    # vacuous case this must not become is a green derived from having asked
    # nothing; here the ceiling and the count both come from the live payload.
    # SCOPE IT TO THIS SEAT. seat_fabric.pending_count is the ALL-SEATS diagnostic
    # (the payload says scope: all-seats-diagnostic), so reading it makes any other
    # seat's backlog look like this seat's - the gate would then refuse forever
    # whenever anyone else had mail. Third time in this organ that a global field
    # was credited to a seat; count MY pending rows instead.
    mine_pending = [m for m in (fab.get("pending") or [])
                    if str(m.get("recipient_seat_id") or m.get("to") or "") == seat_id]
    nothing_to_move = not mine_pending
    proof = None
    if cursor_current:
        proof = "watcher-cursor-current"
    elif drain_progressed:
        proof = "drain-path-moved-mail"
    elif nothing_to_move:
        proof = "fabric-reports-zero-pending"
    return {
        "observed_cursor": observed, "pending_ceiling": ceiling,
        "projection_seat": w.get("seat_id"), "projection_is_mine": projection_is_mine,
        "information_state": info_state,
        "cursor_current": cursor_current,
        "claims_caught_up_without_cursor": claims_caught_up and not cursor_current,
        "drain_progressed": drain_progressed,
        "nothing_to_move": nothing_to_move, "my_pending": len(mine_pending),
        "informed": proof is not None,
        "proved_by": proof,
    }


def check_watcher(payload: dict[str, Any], seat_id: str) -> dict[str, Any]:
    """Step 1/6: the live watcher projection must name THIS seat.

    A watcher bound to another seat is worse than no watcher: it is arming that
    reports success while watching someone else's mailbox. That is what the bare
    hook command produced before fabric_watch required --seat.
    """
    fab = (payload or {}).get("seat_fabric") or {}
    w = fab.get("watcher") or {}
    status = str(w.get("status") or "")
    bound = str(w.get("seat_id") or "")
    proj_ok = status.upper() == "ACTIVE" and bound == seat_id
    proc = live_watcher_process(seat_id)
    return {"status": status, "seat_id": bound,
            "active": status.upper() == "ACTIVE",
            "projection_matches": proj_ok,
            "process_matches": bool(proc.get("matched")),
            "seat_matches": proj_ok or bool(proc.get("matched")),
            "proved_by": "fabric-projection" if proj_ok else proc.get("proved_by"),
            "target": w.get("target_thread_id") or w.get("target") or None}


# --------------------------------------------------------------------------
# step 2 — enumerate canonical ids, then ONE pull with a non-displacing budget
# --------------------------------------------------------------------------

def pending_ids(payload: dict[str, Any], seat_id: str) -> list[str]:
    fab = (payload or {}).get("seat_fabric") or {}
    return [str(m.get("message_id")) for m in (fab.get("pending") or [])
            if str(m.get("to") or m.get("recipient_seat_id") or "") == seat_id]


def pending_count(payload: dict[str, Any]) -> int:
    fab = (payload or {}).get("seat_fabric") or {}
    return int(fab.get("pending_count") or 0)


def canonical_obligations(root: Path, seat_id: str) -> tuple[dict[str, Any] | None, str]:
    """Read queued + pulled nonterminal truth from Atlas, never from the side ledger."""

    rc, result, error = _run(["obligations", "--seat", seat_id], root)
    if rc != 0 or not isinstance(result, dict):
        return None, f"canonical obligations unavailable (rc={rc}): {error}"
    if result.get("seat_id") != seat_id:
        return None, "canonical obligations returned a different recipient seat"
    rows = result.get("obligations")
    if not isinstance(rows, list):
        return None, "canonical obligations response omitted its obligation rows"
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or not str(row.get("message_id") or ""):
            return None, "canonical obligations returned a malformed message row"
        mid = str(row["message_id"])
        if mid in seen:
            return None, f"canonical obligations duplicated exact message id {mid}"
        seen.add(mid)
        if row.get("recipient_seat_id") != seat_id:
            return None, f"canonical obligations leaked another recipient into {seat_id}: {mid}"
        if row.get("status") not in {"queued", "pulled"}:
            return None, f"canonical obligations returned a terminal or unknown state for {mid}"
    return result, ""


# --------------------------------------------------------------------------
# the sequence
# --------------------------------------------------------------------------

def run_gate(root: Path, seat_id: str, goal: str, *, engine: bool = False,
             allow_wake_skip: bool = False, record_join: bool = False,
             holder_ref: str = "", function: str = "", provider: str = "",
             model: str = "") -> dict[str, Any]:
    """Steps 0-9. Returns a terminal MAIL_READY or MAIL_REFUSED record.

    Every acknowledgement carries body_handle + reconstruction_event_id +
    reconstruction_handle, and is followed by a status re-read asserting
    delivered=true. A refusal carries the same proof (step 4).
    """
    out: dict[str, Any] = {
        "schema_version": "laplace.startup-mail-gate/1",
        "seat_id": seat_id, "goal": goal, "began_at": _now(),
        "resumed": [], "pulled": [], "delivered": [], "already_delivered": [],
        "unknown_content": [], "refused": [], "custody_phases": [],
    }

    # Git-carried standing Eigen authority must survive the subsystems it repairs.
    # Fabric, watchers, recovery and Atlas are visible telemetry, never prerequisites.
    if seat_id == "eigen-seat" and function == "eigen":
        from laplace.engine.eigen_authority import observe_authority

        authority = observe_authority(root, holder_ref=holder_ref)
        out["eigen_authority"] = authority
        if authority.get("status") != "AUTHORIZED":
            return {
                **out,
                **_refuse(
                    "0-eigen-authority",
                    str(authority.get("reason") or "standing Eigen authority refused"),
                ),
            }
        try:
            rc, wake, wake_error = wake_payload(root, engine=engine, seat_id=seat_id)
            telemetry = wake if isinstance(wake, dict) else {
                "status": "UNKNOWN", "reason": wake_error or f"wake rc={rc}",
            }
        except Exception as exc:  # noqa: BLE001 - telemetry never erases standing authority
            telemetry = {"status": "UNKNOWN", "reason": f"{type(exc).__name__}: {exc}"}
        return {
            **out,
            "state": "MAIL_READY",
            "observed_at": _now(),
            "holder_ref": authority.get("holder_ref"),
            "function": "eigen",
            "mail": {"status": "OPTIONAL", "obligations": 0, "delivery_claim": False},
            "telemetry": telemetry,
            "join": "NOT-REQUIRED-STANDING-ROLE",
            "first_goal": "TRIAGE-ONLY",
        }

    # ---- compatibility mirror only. Canonical Atlas message states outrank this file.
    led = _read_ledger(seat_id)
    side_candidates = [mid for mid, row in (led.get("in_flight") or {}).items()
                       if not row.get("delivered")]
    out["side_ledger_candidates"] = side_candidates
    out["side_ledger_unreadable"] = bool(led.get("prior_ledger_unreadable"))

    # ---- step 1: the wake, and the fabric must be available
    rc, payload, err = wake_payload(root, engine=engine, seat_id=seat_id)
    if payload is None:
        if not allow_wake_skip:
            return {**out, **_refuse("1-wake", f"wake did not return a payload (rc={rc}): {err}")}
        payload = {}
    fab = (payload or {}).get("seat_fabric") or {}
    if not fab:
        return {**out, **_refuse("1-fabric", "seat_fabric is UNAVAILABLE in the wake payload; "
                                             "startup fails closed rather than proceeding blind")}
    out["fabric_status"] = fab.get("status")
    out["watcher"] = check_watcher(payload, seat_id)

    # ---- steps 2-5: Atlas is the crash ledger. Drain to a stable nonterminal snapshot.
    # A send racing this gate may create a new queued obligation after the first pull. Each round
    # re-enumerates canonical state and pulls only a genuinely new epoch; cursors make duplicate
    # pulls impossible. Eight moving epochs refuse loudly instead of claiming a quiescent inbox.
    out["wake_pending_count_all_seats"] = pending_count(payload)
    out["wake_pending_ids_for_seat"] = pending_ids(payload, seat_id)
    out["pull_rounds"] = []
    out["canonical_rounds"] = []
    processed: set[str] = set()
    led.setdefault("in_flight", {})

    for round_number in range(1, 9):
        obligations, error = canonical_obligations(root, seat_id)
        if obligations is None:
            return {**out, **_refuse("2-obligations", error)}
        rows = list(obligations["obligations"])
        out["canonical_rounds"].append({
            "round": round_number,
            "counts": obligations.get("counts"),
            "message_ids": [row.get("message_id") for row in rows],
        })
        foreign = [row for row in rows if not row.get("context_matches")]
        if foreign:
            return {**out, **_refuse(
                "2-context-obligations",
                "nonterminal mail belongs to another assumption fibre; startup cannot silently "
                "cross or erase it — explicit context transport/recovery is required",
                other_context_obligations=foreign,
            )}

        canonical_ids = {str(row["message_id"]) for row in rows}
        if round_number == 1:
            out["resume_candidates"] = sorted(
                str(row["message_id"]) for row in rows if row.get("status") == "pulled"
            )
            out["side_ledger_stale"] = sorted(set(side_candidates) - canonical_ids)
        for row in rows:
            mid = str(row["message_id"])
            led["in_flight"].setdefault(mid, {
                "canonical_status": row.get("status"), "delivered": False,
            })
        # Stale side-file rows no longer create phantom work. Keep only canonical obligations.
        led["in_flight"] = {
            mid: row for mid, row in led["in_flight"].items() if mid in canonical_ids
        }
        _write_ledger(seat_id, led)

        queued = [row for row in rows if row.get("status") == "queued"]
        if queued:
            budget = max(1, len(queued))
            led["last_pull_attempt"] = _now()
            _write_ledger(seat_id, led)
            rc, pull, err = _run(["pull", "--seat", seat_id, "--budget", str(budget)], root)
            if pull is None:
                return {**out, **_refuse("2-pull", f"pull returned no JSON (rc={rc}): {err}")}
            if pull.get("status") == "BLOCKED-UNKNOWN-CONTENT":
                out["unknown_content"].extend(pull.get("unknown_content") or [])
                return {**out, **_refuse(
                    "2-pull-content",
                    "canonical pull refused without advancing its cursor because content is UNKNOWN",
                    unknown_content=out["unknown_content"],
                )}
            if int(pull.get("displaced_count") or 0):
                return {**out, **_refuse(
                    "2-displacement",
                    "the pull displaced mail; budget must cover the exact queued epoch",
                    displaced=pull.get("displaced_message_ids"),
                )}
            served = [str(m.get("message_id")) for m in (pull.get("messages") or [])]
            out["pull_rounds"].append({
                "round": round_number, "budget": budget, "served": served,
            })
            out["pulled"] = sorted(set(out["pulled"]) | set(served))
            # Re-read canonical states before reconstruction; the pull itself is not reading.
            continue

        pulled_rows = [row for row in rows if row.get("status") == "pulled"]
        new_pulled = [row for row in pulled_rows if str(row["message_id"]) not in processed]
        if new_pulled:
            message_ids = [str(row["message_id"]) for row in new_pulled]
            out["pulled"] = sorted(set(out["pulled"]) | set(message_ids))
            command = ["custody-batch", "--seat", seat_id, "--goal", goal]
            for message_id in message_ids:
                command.extend(("--message", message_id))
            rc, batch, err = _run(command, root)
            if not isinstance(batch, dict):
                return {**out, **_refuse(
                    "3-custody-batch",
                    f"one-process custody batch returned no typed receipt (rc={rc}): {err}",
                )}
            batch_ids = [str(mid) for mid in (batch.get("message_ids") or [])]
            result_rows = list(batch.get("rows") or [])
            result_ids = [
                str(row.get("message_id")) if isinstance(row, dict) else ""
                for row in result_rows
            ]
            phase_receipt = batch.get("phase_receipt")
            residual = batch.get("residual")
            expected_phase = (
                _expected_custody_phase(
                    seat_id=seat_id,
                    goal=goal,
                    message_ids=message_ids,
                    rows=result_rows,
                )
                if all(isinstance(row, dict) for row in result_rows)
                else None
            )
            if (
                batch.get("schema_version") != "laplace.fabric-custody-batch/1"
                or batch.get("seat_id") != seat_id
                or batch.get("batch_size") != len(message_ids)
                or batch_ids != message_ids
                or result_ids != message_ids
                or len(set(result_ids)) != len(result_ids)
                or phase_receipt != expected_phase
                or not isinstance(residual, dict)
                or residual.get("crutch") != COLD_STORE_CRUTCH
            ):
                return {**out, **_refuse(
                    "3-custody-batch",
                    "custody batch receipt disagrees with the exact seat/message phase request",
                    requested_message_ids=message_ids,
                    observed_message_ids=batch_ids,
                )}
            out["custody_phases"].append({
                "receipt": phase_receipt,
                "measurements": batch.get("measurements"),
                "residual": residual,
            })
            for row in result_rows:
                mid = str(row["message_id"])
                state = str(row.get("state") or "")
                if state == "ALREADY_DELIVERED" and row.get("delivered") is True:
                    out["already_delivered"].append(mid)
                elif state == "DELIVERED" and row.get("delivered") is True:
                    proof = {
                        "body_handle": row.get("body_handle"),
                        "reconstruction_event_id": row.get("reconstruction_event_id"),
                        "reconstruction_handle": row.get("reconstruction_handle"),
                    }
                    if not all(proof.values()):
                        out["unknown_content"].append({
                            "message_id": mid,
                            "content_state": UNKNOWN_CONTENT_STATE,
                            "reason": "custody batch claimed delivery without complete proof",
                            "proof": proof,
                        })
                    else:
                        out["delivered"].append({
                            "message_id": mid, "delivered": True, **proof,
                        })
                elif state == "UNKNOWN":
                    out["unknown_content"].append({
                        "message_id": mid,
                        "content_state": UNKNOWN_CONTENT_STATE,
                        "reason": row.get("reason") or "canonical body is unreadable",
                        "authority": (
                            "unchanged; an author act with unreadable content remains an author act"
                        ),
                        "residue": row.get("residue"),
                    })
                else:
                    out["refused"].append({
                        "message_id": mid,
                        "delivered": False,
                        "body_handle": row.get("body_handle"),
                        "reconstruction_event_id": row.get("reconstruction_event_id"),
                        "reconstruction_handle": row.get("reconstruction_handle"),
                        "reason": row.get("reason") or "custody batch refused exact message",
                        "residue": row.get("residue"),
                    })
                processed.add(mid)

        if out["unknown_content"]:
            return {**out, **_refuse(
                "3-reconstruct",
                "nonterminal messages have UNKNOWN content; authority is preserved and MAIL_READY refuses",
                unknown_content=out["unknown_content"],
            )}
        if out["refused"]:
            return {**out, **_refuse(
                "4-acknowledge",
                "messages were pulled and reconstructed but not delivered",
                undelivered=[row["message_id"] for row in out["refused"]],
            )}

        # Re-read after every batch. Empty is a canonical positive claim for this instant; if a
        # sender raced us, the next round sees it and drains its distinct cursor epoch.
        after, error = canonical_obligations(root, seat_id)
        if after is None:
            return {**out, **_refuse("5-obligations-recheck", error)}
        remaining = list(after["obligations"])
        if not remaining:
            led["in_flight"] = {}
            led["last_canonical_clear"] = _now()
            _write_ledger(seat_id, led)
            break
    else:
        return {**out, **_refuse(
            "5-moving-inbox",
            "mail changed across eight canonical drain epochs; startup never observed a stable clear",
        )}

    # ---- step 4 terminal: an ack that did not deliver is a STEP 4 failure and must
    #      name itself. Letting step 6 report it would blame the watcher for a
    #      transport refusal the acknowledgement caused.
    if out["refused"]:
        return {**out, **_refuse("4-acknowledge",
                                 "messages were pulled and reconstructed but not delivered",
                                 undelivered=[r["message_id"] for r in out["refused"]])}

    # ---- step 6: bound AND informed. Liveness alone never reaches MAIL_READY.
    w = out["watcher"]
    drain_progressed = bool(out["delivered"] or out["already_delivered"])
    info = watcher_information_proof(payload, seat_id, drain_progressed)
    out["information_proof"] = info
    if w.get("seat_matches") and not info.get("informed"):
        out["rearm_required"] = f"{PY} scripts/fabric_watch.py --seat {seat_id}"
        return {**out, **_refuse(
            "6-information",
            "a watcher is bound to this seat but nothing proves mail can MOVE: "
            f"observed_cursor={info.get('observed_cursor')} against pending ceiling "
            f"{info.get('pending_ceiling')}, and this run's drain moved nothing. "
            "ACTIVE is a liveness claim, not an information claim"
            + (" - and the watcher asserts 'caught-up' with no cursor to corroborate it"
               if info.get("claims_caught_up_without_cursor") else ""),
            watcher=w, information_proof=info)}
    if not w.get("seat_matches"):
        out["rearm_required"] = f"{PY} scripts/fabric_watch.py --seat {seat_id}"
        return {**out, **_refuse("6-watcher",
                                 f"no watcher proves seat {seat_id!r}: the fabric projection names "
                                 f"{w.get('seat_id')!r} and no live fabric_watch process carries "
                                 f"--seat {seat_id}. Arming the wrong seat watches someone else's mailbox.",
                                 watcher=w)}

    # ---- step 9: terminal
    undelivered = [r["message_id"] for r in out["refused"]]
    state = "MAIL_READY" if not undelivered else "MAIL_REFUSED"
    out["state"] = state
    out["observed_at"] = _now()
    if undelivered:
        out["failed_step"] = "4-acknowledge"
        out["why"] = "messages were pulled and reconstructed but not delivered"
        out["undelivered"] = undelivered
    if state == "MAIL_READY" and record_join:
        identity = provider_identity_proof(
            seat_id,
            requested_holder_ref=holder_ref,
        )
        out["provider_identity"] = identity
        exact_holder = str(identity.get("provider_session_ref") or "")
        exact_function = function.strip()
        # Echo the effective identity at the operator boundary.  The nested occupancy remains
        # the durable proof, but a caller must not infer "no holder" from absent top-level fields.
        out["holder_ref"] = exact_holder or None
        out["function"] = exact_function or None
        if identity.get("state") in {"REFUSED", "UNAVAILABLE", "UNVERIFIED"}:
            return {
                **out,
                **_refuse(
                    "9-seat-identity",
                    str(identity.get("reason") or "provider-session identity was not proved"),
                    holder_ref=exact_holder or None,
                    function=exact_function or None,
                    provider_identity=identity,
                ),
            }
        if not exact_holder or not exact_function:
            return {
                **out,
                **_refuse(
                    "9-seat-identity",
                    "MAIL_READY proves the transport only; seat.joined additionally requires "
                    "an exact provider-session holder and a declared function",
                    holder_ref=exact_holder or None,
                    function=exact_function or None,
                ),
            }
        try:
            from laplace.representation import atlas_bridge

            out["seat_join"] = atlas_bridge.seat_join(
                seat_id=seat_id,
                holder_ref=exact_holder,
                function=exact_function,
                information_proof=dict(out),
                provider=provider.strip() or exact_holder.split(":", 1)[0],
                model=model.strip() or os.environ.get("LAPLACE_MODEL_ID", "unknown"),
            )
        except Exception as exc:  # noqa: BLE001 - a failed durable join must refuse startup
            refusal_detail = getattr(exc, "detail", None)
            structured_refusal = {
                "reason": str(getattr(exc, "reason", type(exc).__name__)),
                "detail": dict(refusal_detail) if isinstance(refusal_detail, Mapping) else {},
            }
            return {
                **out,
                **_refuse(
                    "10-seat-join",
                    f"MAIL_READY was earned but the durable seat.joined event refused: {exc}",
                    seat_join_refusal=structured_refusal,
                ),
            }
    return out


def main(argv: list[str] | None = None) -> int:
    import argparse
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--seat", required=True, help="the EXACT seat this session holds")
    p.add_argument("--goal", default="startup mail gate: reconstruct and acknowledge inbound mail")
    p.add_argument("--root", default=".")
    p.add_argument("--engine", action="store_true", help="worker/ambient projection of the wake")
    p.add_argument(
        "--holder-ref",
        default="",
        help=(
            "exact provider-session holder; inferred from CODEX_THREAD_ID/"
            "CLAUDE_CODE_SESSION_ID (legacy CLAUDE_SESSION_ID also accepted)"
        ),
    )
    p.add_argument(
        "--function",
        required=True,
        choices=("eigen", "ego", "superego", "sensorium", "author", "system", "provider"),
        help="function claimed by this occupant, separate from the seat address",
    )
    p.add_argument("--provider", default="")
    p.add_argument("--model", default="")
    a = p.parse_args(argv)
    rec = run_gate(
        Path(a.root).resolve(),
        a.seat,
        a.goal,
        engine=a.engine,
        record_join=True,
        holder_ref=a.holder_ref,
        function=a.function,
        provider=a.provider,
        model=a.model,
    )
    print(json.dumps(rec, indent=1, sort_keys=True))
    return 0 if rec.get("state") == "MAIL_READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
