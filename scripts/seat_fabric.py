"""seat_fabric.py - the provider-neutral face of the M0 seat fabric.

One thin CLI over the one write door (src/laplace/representation/atlas_bridge.py -> ConceptricStore.append).
It owns NO state: no cache, no config, no cursor of its own - the durable cursor lives in the
conceptric and advances only through a banked pull. Every output changes a decision:
  inbox  -> "do I pull now"        (read-only glow; the wake-side cure for silent queues)
  obligations -> queued + pulled nonterminal truth from canonical Atlas, across fibres
  watch  -> "do I attend now"      (read-only poll; one line per newly visible message)
  pull   -> "which of these now"   (GRADED: one line per message under a budget, bodies by descent)
  body   -> "this one, in full"    (read-only body descent; never a delivery claim)
  drain  -> pull + re-arm, one act (the watcher lifecycle's own verb)
  ack / supersede / send           (the fabric verbs, banked through the bridge)

THE PULL IS A SERVE, NOT A DUMP (WO-20260824-fabric-pull-is-a-serve). It used to print every
pending body verbatim - 14 at once at the founding wake - the flat frame over N messages, no
attention grades, no omission residual. A seat's context window is an attention-state fibre
exactly like his, so the same conjugate-serve law applies: grade first, descend on judgment,
and NAME what the budget displaced. The banked act underneath is untouched: pull still advances
the durable cursor for every pending message, so displacement is a SERVE truncation and the
output says so in as many words - a displaced message is pulled, not still queued.

RETIREMENT CONDITION (named at birth so this cannot fossilize as a forever-step): this script
dies the day either (a) every provider session reaches the laplace_seat_* verbs over its own
live MCP surface, or (b) the Phase-4 object-and-edge substrate re-founds the fabric and its
read faces. Whichever lands first supersedes this file; it must not survive its warrant.
It is wired into session-start hooks as a PRINTED LINE ONLY - it never gates a session.

Runtime law: /usr/bin/python3 (system + user site). The bridge refuses venv interpreters.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from laplace.representation.atlas_bridge import AtlasError  # noqa: E402

from laplace.representation.seat_fabric_grade import DEFAULT_PREVIEW_CHARS, DEFAULT_PULL_BUDGET
from laplace.representation.seat_fabric_grade import GRADE_SCHEMA as _GRADE_SCHEMA  # noqa: E402
from laplace.representation.seat_fabric_grade import expiry_from as _expiry_from  # noqa: E402
from laplace.representation.seat_fabric_grade import grade_pull as _shared_grade_pull  # noqa: E402

PROVIDER_DEFAULT = "cli"
MODEL_DEFAULT = "seat-fabric-cli"
GRADE_SCHEMA = _GRADE_SCHEMA  # public compatibility for programmatic CLI consumers
PY = "/usr/bin/python3"
WATCHER = "scripts/fabric_watch.py"
EXACT_MESSAGE_ID = re.compile(r"message:[0-9a-f]{64}\Z")
CUSTODY_BATCH_SCHEMA = "laplace.fabric-custody-batch/1"
CUSTODY_PHASE_SCHEMA = "laplace.fabric-custody-phase/1"
COLD_STORE_CRUTCH = "CR-C1-COLD-STORE-CONSTRUCTION"


def _bridge():
    from laplace.representation import atlas_bridge as ab

    return ab


def _provider_state():
    return _bridge().snapshot()["provider"]


def _pending_for(state: dict, seat_id: str) -> list[dict]:
    """Queued messages addressed to the seat, beyond its durable cursor in the ACTIVE
    assumption+fibre. Pure read - mirrors state.pending_messages without banking a pull."""
    ctx = state["active_context"]
    cursor = 0
    for row in state.get("seat_cursors", {}).get(seat_id, []):
        if row["assumption"] == ctx["assumption"] and row["fibre"] == ctx["fibre"]:
            cursor = max(cursor, row["cursor"])
    out = []
    for m in state.get("messages", {}).values():
        msg = m["message"]
        if (
            m["status"] == "queued"
            and msg["recipient_seat_id"] == seat_id
            and m["assumption"] == ctx["assumption"]
            and m["fibre"] == ctx["fibre"]
            and msg["cursor"] > cursor
        ):
            out.append(m)
    return sorted(out, key=lambda m: m["message"]["cursor"])


def resolve_message_id(reference: str) -> str:
    """Resolve one exact or unique-prefix message id through the provider face."""

    raw = reference.strip()
    if not raw:
        raise ValueError("message reference cannot be empty")
    # Canonical ids are self-delimiting. Atlas still proves existence and authority in the
    # called verb; replaying the provider projection here adds no authority. Prefixes retain
    # the existing provider lookup and ambiguity refusal.
    if EXACT_MESSAGE_ID.fullmatch(raw):
        return raw
    messages = _provider_state().get("messages", {})
    if raw in messages:
        return raw
    candidates = [
        message_id
        for message_id in messages
        if message_id.startswith(raw)
        or message_id.removeprefix("message:").startswith(raw.removeprefix("message:"))
    ]
    if not candidates:
        raise ValueError(f"message reference does not resolve: {reference}")
    if len(candidates) != 1:
        raise ValueError(
            f"message reference is ambiguous: {reference} -> {len(candidates)} candidates"
        )
    return candidates[0]


def _canonical_handle(value: dict) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _delivered(status: object) -> bool:
    if not isinstance(status, dict):
        return False
    if status.get("delivered") is True:
        return True
    nested = status.get("status")
    if isinstance(nested, dict):
        return nested.get("delivered") is True or nested.get("status") == "delivered"
    return nested == "delivered"


def _prime_custody_stores(bridge) -> dict:
    """Construct each cached bridge store once and name C1's remaining carrying cost."""

    rows_by_face: dict[str, int] = {}
    for name in ("_read_store", "_store"):
        getter = getattr(bridge, name, None)
        if callable(getter):
            rows_by_face[name.removeprefix("_")] = int(
                getter().current_state().event_count
            )
    return {
        "store_constructions": len(rows_by_face),
        "replayed_rows": sum(rows_by_face.values()),
        "replayed_rows_by_face": rows_by_face,
        "measurement": (
            "exact event_count observed after each cold cached store construction"
            if rows_by_face
            else "unavailable from bridge test double"
        ),
    }


def custody_batch(
    *,
    seat_id: str,
    message_ids: tuple[str, ...],
    goal: str,
    provider: str,
    model: str,
) -> dict:
    """Reconstruct and acknowledge one already-pulled exact-ID batch in this process."""

    exact_ids = tuple(mid.strip() for mid in message_ids)
    if not exact_ids:
        raise ValueError("custody batch requires at least one exact message id")
    if len(set(exact_ids)) != len(exact_ids):
        raise ValueError("custody batch refuses duplicate message ids before any effect")
    malformed = [mid for mid in exact_ids if not EXACT_MESSAGE_ID.fullmatch(mid)]
    if malformed:
        raise ValueError(
            "custody batch accepts canonical message:<sha256> ids only; "
            f"refused {malformed!r} before any effect"
        )

    began_wall = time.perf_counter()
    began_cpu = time.process_time()
    bridge = _bridge()
    cold = _prime_custody_stores(bridge)
    rows: list[dict] = []
    statuses: dict[str, dict] = {}
    identity_errors: dict[str, str] = {}
    for message_id in exact_ids:
        try:
            statuses[message_id] = bridge.status(message_id=message_id)
        except (AttributeError, KeyError) as exc:
            # atlas_bridge.status historically dereferences the absent record before it can
            # return a typed unknown-id row. Translate only that narrow lookup failure here;
            # Atlas, I/O, custody, and history faults still propagate and fail the command.
            identity_errors[message_id] = (
                "canonical Atlas status does not contain this exact id: "
                f"{type(exc).__name__}"
            )
    for message_id, observed in statuses.items():
        status = observed.get("status") if isinstance(observed, dict) else None
        message = status.get("message") if isinstance(status, dict) else None
        recipient = message.get("recipient_seat_id") if isinstance(message, dict) else None
        if not isinstance(status, dict):
            identity_errors[message_id] = "canonical Atlas status does not contain this exact id"
        elif recipient != seat_id:
            identity_errors[message_id] = (
                "canonical message recipient does not match the exact custody seat"
            )
    if identity_errors:
        # Validate the whole batch before the first REPL/ACK effect. One mixed or unknown id
        # cannot smuggle a partial custody phase across a seat boundary.
        for message_id in exact_ids:
            rows.append(
                {
                    "message_id": message_id,
                    "state": "REFUSED",
                    "delivered": False,
                    "reason": identity_errors.get(
                        message_id,
                        "batch identity preflight refused another exact id before any effect",
                    ),
                }
            )
    for message_id in exact_ids:
        if identity_errors:
            break
        before = statuses[message_id]
        if _delivered(before):
            rows.append(
                {
                    "message_id": message_id,
                    "state": "ALREADY_DELIVERED",
                    "delivered": True,
                    "status": before.get("status"),
                }
            )
            continue
        try:
            reconstruction = bridge.reconstruct(
                message_id=message_id,
                seat_id=seat_id,
                goal=goal,
                provider=provider,
                model=model,
            )
        except AtlasError as exc:
            reason = str(getattr(exc, "reason", type(exc).__name__))
            body_failure = "BLOB" in reason.upper() or "BODY" in reason.upper()
            rows.append(
                {
                    "message_id": message_id,
                    "state": "UNKNOWN" if body_failure else "REFUSED",
                    "content_state": "UNKNOWN" if body_failure else None,
                    "delivered": False,
                    "reason": str(exc),
                    "residue": {
                        "code": reason.upper().replace("-", "_"),
                        "detail": dict(getattr(exc, "detail", {}) or {}),
                    },
                }
            )
            continue
        proof = {
            "body_handle": reconstruction.get("body_handle"),
            "reconstruction_event_id": reconstruction.get("reconstruction_event_id"),
            "reconstruction_handle": reconstruction.get("reconstruction_handle"),
        }
        if not all(proof.values()):
            rows.append(
                {
                    "message_id": message_id,
                    "state": "UNKNOWN",
                    "content_state": "UNKNOWN",
                    "delivered": False,
                    "reason": "reconstruction returned an incomplete typed proof",
                    "proof": proof,
                }
            )
            continue
        try:
            acknowledgement = bridge.acknowledge(
                message_id=message_id,
                seat_id=seat_id,
                disposition="accepted",
                note=goal,
                provider=provider,
                model=model,
                reconstruction_event_id=str(proof["reconstruction_event_id"]),
                reconstruction_handle=str(proof["reconstruction_handle"]),
            )
            after = bridge.status(message_id=message_id)
        except AtlasError as exc:
            reason = str(getattr(exc, "reason", type(exc).__name__))
            rows.append(
                {
                    "message_id": message_id,
                    "state": "REFUSED",
                    "delivered": False,
                    **proof,
                    "reason": str(exc),
                    "residue": {
                        "code": reason.upper().replace("-", "_"),
                        "detail": dict(getattr(exc, "detail", {}) or {}),
                    },
                }
            )
            continue
        delivered = _delivered(after) or _delivered(acknowledgement)
        rows.append(
            {
                "message_id": message_id,
                "state": "DELIVERED" if delivered else "REFUSED",
                "delivered": delivered,
                **proof,
                "acknowledgement_receipt": acknowledgement.get("receipt"),
                "status": after.get("status"),
                **({} if delivered else {"reason": "accepted acknowledgement did not deliver"}),
            }
        )

    semantic_receipt = {
        "schema_version": CUSTODY_PHASE_SCHEMA,
        "phase": "pulled-message-custody",
        "seat_id": seat_id,
        "goal_handle": "sha256:" + hashlib.sha256(goal.encode("utf-8")).hexdigest(),
        "message_ids": list(exact_ids),
        "batch_size": len(exact_ids),
        "ordered_semantics": [
            "exact-status-preflight",
            "typed-reconstruction",
            "accepted-acknowledgement",
            "exact-delivery-confirmation",
        ],
        "results": [dict(row) for row in rows],
    }
    phase_receipt = {**semantic_receipt, "handle": _canonical_handle(semantic_receipt)}
    read_rows = int(cold.get("replayed_rows_by_face", {}).get("read_store", 0))
    write_rows = int(cold.get("replayed_rows_by_face", {}).get("store", 0))
    baseline_replayed_rows = (
        len(exact_ids) * ((4 * read_rows) + (2 * write_rows))
        if read_rows and write_rows
        else None
    )
    after = {
        "process_count": 1,
        "store_constructions": cold["store_constructions"],
        "replayed_rows": cold["replayed_rows"],
        "replayed_rows_by_face": cold["replayed_rows_by_face"],
        "wall_seconds": time.perf_counter() - began_wall,
        "cpu_seconds": time.process_time() - began_cpu,
        "pid": os.getpid(),
    }
    return {
        "schema_version": CUSTODY_BATCH_SCHEMA,
        "seat_id": seat_id,
        "message_ids": list(exact_ids),
        "batch_size": len(exact_ids),
        "rows": rows,
        "phase_receipt": phase_receipt,
        "measurements": {
            "batch_size": len(exact_ids),
            "before": {
                "process_count": 4 * len(exact_ids),
                "store_constructions": 6 * len(exact_ids),
                "replayed_rows": baseline_replayed_rows,
                "formula": (
                    "per message: four CLI processes; every exact-id resolver constructs a "
                    "read store, while reconstruct and acknowledge each also construct a "
                    "write store (4 read + 2 write cold history verifications)"
                ),
            },
            "after": after,
            # Flat fields remain for existing receipt consumers during the C1 transition.
            "process_count": after["process_count"],
            "store_constructions": after["store_constructions"],
            "replayed_rows": after["replayed_rows"],
            "replayed_rows_by_face": after["replayed_rows_by_face"],
            "wall_seconds": after["wall_seconds"],
            "cpu_seconds": after["cpu_seconds"],
            "pid": after["pid"],
            "measurement": cold["measurement"],
        },
        "delivery_claim": "only rows individually confirmed delivered claim delivery",
        "residual": {
            "crutch": COLD_STORE_CRUTCH,
            "covered_defect": "repeated subprocess and full-history store construction per message",
            "remaining_defect": "cold read/write store construction still verifies full history",
            "retire_when": "C2 authenticated checkpoint and bounded suffix verification is exact",
        },
    }


def _expiry_note(msg: dict) -> str:
    return _expiry_from(str((msg.get("message") or {}).get("expires_at") or ""))


def cmd_inbox(args) -> int:
    state = _provider_state()
    seats = [args.seat] if args.seat else sorted(state.get("seats", {}))
    quiet = True
    for seat in seats:
        pending = _pending_for(state, seat)
        if not pending and args.seat is None:
            continue
        quiet = False
        if not pending:
            print(f"[seat-fabric] {seat}: inbox empty")
            continue
        worst = min(
            (_expiry_note(m) for m in pending),
            key=lambda n: 0 if "EXPIRED" in n else 1 if n.startswith("RED") else 2,
        )
        print(
            f"[seat-fabric] {seat}: {len(pending)} pending ({worst}) - "
            f"drain with: {PY} scripts/seat_fabric.py drain --seat {seat}"
        )
        for m in pending:
            msg = m["message"]
            print(
                f"[seat-fabric]   {msg['message_id'][:28]}  {msg['sender_seat_id']} "
                f"-> {seat}  {msg['message_type']}  [{_expiry_note(m)}]"
            )
    if quiet:
        print(f"[seat-fabric] all seat inboxes empty (fibre: {state['active_context']['fibre']})")
    return 0


def cmd_watch(args) -> int:
    if args.seat == "codex-seat" and not args.once:
        from laplace.representation import codex_seat_watcher

        singleton = codex_seat_watcher.projection()
        if singleton.get("status") == "ACTIVE":
            print(
                "[seat-fabric] codex-seat manual watch retired: the wake-bound singleton "
                f"PID {singleton.get('pid')} owns this task's nudge path",
                flush=True,
            )
            return 0
    seen: set[str] = set()
    first = True
    observed_token: dict | None = None
    pending: list[dict] = []
    while True:
        try:
            observation = _bridge().provider_observation(previous_token=observed_token)
            if observation["changed"]:
                observed_token = observation["drift_token"]
                pending = _pending_for(observation["provider"], args.seat)
            for m in pending:
                mid = m["message"]["message_id"]
                if mid not in seen:
                    seen.add(mid)
                    if not first or args.replay:
                        msg = m["message"]
                        print(
                            f"NEW for {args.seat}: {mid} {msg['sender_seat_id']} "
                            f"{msg['message_type']} [{_expiry_note(m)}]",
                            flush=True,
                        )
        except Exception as exc:  # noqa: BLE001 - a watcher must survive transient store races
            print(f"watch WARN: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        if args.once:
            return 0
        first = False
        time.sleep(args.interval)


def descend_command(message_id: str) -> str:
    return f"{PY} scripts/seat_fabric.py body --message {message_id}"


def grade_pull(
    envelope: dict,
    *,
    budget: int = DEFAULT_PULL_BUDGET,
    preview_chars: int = DEFAULT_PREVIEW_CHARS,
    descend: tuple[str, ...] = (),
    full: bool = False,
) -> dict:
    """CLI projection of the one shared graded-pull contract."""

    return _shared_grade_pull(
        envelope,
        budget=budget,
        preview_chars=preview_chars,
        descend=descend,
        full=full,
        descend_for=descend_command,
    )


def render_grade(graded: dict) -> list[str]:
    """The human/agent face of a graded pull: header, one line per served message, displacement."""
    if graded.get("status") == "BLOCKED-UNKNOWN-CONTENT":
        lines = [
            f"[seat-fabric] BLOCKED for {graded.get('seat_id')}: cursor stayed at "
            f"{graded.get('after_cursor')}; no pull event was banked; "
            f"{len(graded.get('unknown_content') or [])} unreadable envelope(s)"
        ]
        for item in graded.get("unknown_content") or []:
            lines.append(
                f"[seat-fabric]   UNKNOWN #{item.get('cursor')} {item.get('message_id')} "
                f"body={str(item.get('body_handle'))[:20]} reason={item.get('reason')}"
            )
        lines.append(
            "[seat-fabric] good mail remains QUEUED; recover the named UNKNOWN body or obtain "
            "an explicit author disposition before retrying"
        )
        return lines
    lines = [
        f"[seat-fabric] pull graded for {graded.get('seat_id')}: "
        f"served {graded.get('served_count')}/{graded.get('pulled_count')} "
        f"(budget {graded.get('pull_budget')}), cursor {graded.get('after_cursor')} -> "
        f"{graded.get('result_cursor')}"
    ]
    lines += [f"[seat-fabric]   {line}" for line in graded.get("grade_lines", [])]
    displaced = list(graded.get("displaced_message_ids") or [])
    if displaced:
        # the ids get their own lines: a run-on wall of 70-char handles is a named residual
        # nobody can read, which is only half a cure.
        lines.append(
            f"[seat-fabric] DISPLACED {len(displaced)} of {graded.get('pulled_count')} by the "
            f"pull budget ({graded.get('pull_budget')}) - they ARE PULLED (this pull's banked "
            f"cursor advance covered them; they will not return on the next pull). Descend:"
        )
        lines += [f"[seat-fabric]     {mid}" for mid in displaced]
    if graded.get("pulled_count"):
        lines.append(f"[seat-fabric] descend: {graded.get('descend_hint')}")
    return lines


def _graded_pull(args) -> dict:
    envelope = _bridge().pull(seat_id=args.seat, as_of="", provider=args.provider, model=args.model)
    return grade_pull(
        envelope,
        budget=args.budget,
        preview_chars=args.preview_chars,
        descend=tuple(args.message or ()),
        full=bool(args.full),
    )


def cmd_pull(args) -> int:
    graded = _graded_pull(args)
    if args.lines:
        print("\n".join(render_grade(graded)))
    else:
        print(json.dumps(graded, indent=1, default=str))
    return 1 if graded.get("status") == "BLOCKED-UNKNOWN-CONTENT" else 0


def rearm_block(seat_id: str) -> dict:
    """What re-arming the mid-session watcher costs, named in the drain's own act.

    A harness-tracked background task can only be created by the SESSION (that exit is the
    whole nudge mechanism), so drain does not spawn a blind daemon that could never wake
    anyone. It carries the exact command instead, in the same breath as the drain, and the
    watcher's own fire message carries the drain command back - so neither half of the loop
    depends on anybody remembering the other.
    """
    if seat_id == "codex-seat":
        return {
            "watcher": "laplace.representation.codex_seat_watcher",
            "seat_id": seat_id,
            "command": None,
            "run_as": "wake-bound singleton tied to CODEX_THREAD_ID",
            "armed_by_this_verb": False,
            "rearm_required": False,
            "why": (
                "the canonical Codex wake owns one persistent nudge projector; drain moves "
                "Atlas and that singleton observes the new causal tip automatically"
            ),
        }
    return {
        "watcher": WATCHER,
        "seat_id": seat_id,
        "command": f"{PY} {WATCHER} --seat {seat_id}",
        "run_as": "harness-tracked background task (its EXIT is the mid-session nudge)",
        "armed_by_this_verb": False,
        "rearm_required": True,
        "why": (
            "only the session can create a harness-tracked task; a detached watcher would "
            "exit into nobody. drain names the arm rather than faking it."
        ),
    }


def cmd_drain(args) -> int:
    """Drain-and-re-arm: one act for the whole watcher lifecycle turn.

    Draining NEVER acks. Reconstruction and acknowledgement stay judgment verbs owned by the
    seat; this verb only advances the durable cursor (the pull) and hands back the arm.
    """
    graded = _graded_pull(args)
    graded["rearm"] = rearm_block(args.seat)
    graded["acked"] = False
    graded["next_judgment"] = (
        f"{PY} scripts/seat_fabric.py reconstruct --seat {args.seat} --message <id> --goal <goal>"
        f"   then ack; draining is not acknowledging"
    )
    if graded["rearm"].get("rearm_required"):
        arm_line = f"[seat-fabric] RE-ARM NOW (background task): {graded['rearm']['command']}"
    else:
        arm_line = "[seat-fabric] watcher remains structurally armed; no manual re-arm"
    if args.lines:
        print("\n".join(render_grade(graded) + [arm_line]))
    else:
        print(json.dumps(graded, indent=1, default=str))
        print(arm_line, file=sys.stderr)  # stdout stays one parseable envelope
    return 1 if graded.get("status") == "BLOCKED-UNKNOWN-CONTENT" else 0


def cmd_body(args) -> int:
    """Read-only body descent for ONE message - the per-message half of the graded pull."""
    r = _bridge().message_body(message_id=resolve_message_id(args.message))
    if args.raw:
        print(r["body"])
    else:
        print(json.dumps(r, indent=1, default=str))
    return 0


def cmd_ack(args) -> int:
    r = _bridge().acknowledge(
        message_id=resolve_message_id(args.message),
        seat_id=args.seat,
        disposition=args.disposition,
        note=args.note,
        provider=args.provider,
        model=args.model,
        reconstruction_event_id=args.recon_event,
        reconstruction_handle=args.recon_handle,
    )
    print(json.dumps(r, indent=1, default=str))
    return 0


def cmd_supersede(args) -> int:
    r = _bridge().supersede_message(
        message_id=resolve_message_id(args.message),
        sender_seat_id=args.sender,
        replacement_message_ids=tuple(
            resolve_message_id(reference) for reference in args.replacement
        ),
        note=args.note,
        provider=args.provider,
        model=args.model,
    )
    print(json.dumps(r, indent=1, default=str))
    return 0


def cmd_reissue_stage_zero_replacement(args) -> int:
    r = _bridge().reissue_stage_zero_migration_replacement(
        provider=args.provider,
        model=args.model,
    )
    print(json.dumps(r, indent=1, default=str))
    return 0


def cmd_preserve_fork(args) -> int:
    r = _bridge().preserve_message_fork(
        seat_id=args.seat,
        message_id=resolve_message_id(args.message),
        original_sender_seat_id=args.sender,
        recipient_seat_id=args.recipient,
        body_handle=args.body_handle,
        author_ruling_ref=args.ruling_ref,
        authority_event_id=args.authority_event,
        reason=args.reason,
        reopen_condition=args.reopen_condition,
        provider=args.provider,
        model=args.model,
    )
    print(json.dumps(r, indent=1, default=str))
    return 0


def cmd_recover_legacy_bundle(args) -> int:
    r = _bridge().recover_legacy_message_bundle(
        actor_seat_id=args.seat,
        replacement_message_id=resolve_message_id(args.replacement),
        authority_acknowledgement_event_id=args.authority_ack,
        provider=args.provider,
        model=args.model,
    )
    print(json.dumps(r, indent=1, default=str))
    return 0


def cmd_reconstruct(args) -> int:
    r = _bridge().reconstruct(
        message_id=resolve_message_id(args.message),
        seat_id=args.seat,
        goal=args.goal,
        provider=args.provider,
        model=args.model,
    )
    print(json.dumps(r, indent=1, default=str))
    return 0


def cmd_custody_batch(args) -> int:
    result = custody_batch(
        seat_id=args.seat,
        message_ids=tuple(args.message),
        goal=args.goal,
        provider=args.provider,
        model=args.model,
    )
    print(json.dumps(result, indent=1, default=str))
    return 1 if any(
        row.get("state") in {"UNKNOWN", "REFUSED"} for row in result["rows"]
    ) else 0


def cmd_status(args) -> int:
    r = _bridge().status(message_id=resolve_message_id(args.message))
    print(json.dumps(r, indent=1, default=str))
    return 0


def cmd_obligations(args) -> int:
    r = _bridge().mail_obligations(seat_id=args.seat)
    print(json.dumps(r, indent=1, default=str))
    return 0


def cmd_snapshot(_args) -> int:
    print(json.dumps(_provider_state(), indent=1, default=str))
    return 0


def cmd_messages(args) -> int:
    rows = []
    for message_id, record in sorted(
        _provider_state().get("messages", {}).items(),
        key=lambda item: item[1]["message"]["cursor"],
    ):
        message = record["message"]
        if args.seat and args.seat not in {message["sender_seat_id"], message["recipient_seat_id"]}:
            continue
        if args.status and record["status"] != args.status:
            continue
        rows.append(
            {
                "message_id": message_id,
                "cursor": message["cursor"],
                "sender": message["sender_seat_id"],
                "recipient": message["recipient_seat_id"],
                "message_type": message["message_type"],
                "status": record["status"],
                "body_handle": message["body_handle"],
                "superseded_by": list(record.get("superseded_by") or []),
                "supersession_note": record.get("supersession_note"),
                "supersession_event_id": record.get("supersession_event_id"),
            }
        )
    print(
        json.dumps(
            {
                "schema_version": "laplace.fabric-message-index/1",
                "count": len(rows),
                "messages": rows,
                "read_only": True,
            },
            indent=1,
            default=str,
        )
    )
    return 0


def cmd_leases(args) -> int:
    print(json.dumps(_bridge().region_leases(as_of=args.as_of), indent=1, default=str))
    return 0


def cmd_checkout(args) -> int:
    crutch = None
    if args.crutch_file:
        crutch = json.loads(Path(args.crutch_file).read_text(encoding="utf-8"))
    result = _bridge().checkout_regions(
        seat_id=args.seat,
        holder_ref=args.holder_ref,
        function=args.function,
        act_id=args.act_id,
        regions=tuple(args.region),
        expires_at=args.expires,
        declaration_kind=args.declaration_kind,
        declaration_ref=args.declaration_ref,
        bootstrap_crutch=crutch,
        provider=args.provider,
        model=args.model,
    )
    print(json.dumps(result, indent=1, default=str))
    return 0


def cmd_checkin(args) -> int:
    evidence = _named_dependencies(list(args.evidence), option="--evidence")
    result = _bridge().checkin_regions(
        lease_id=args.lease,
        seat_id=args.seat,
        holder_ref=args.holder_ref,
        function=args.function,
        outcome=args.outcome,
        evidence=evidence,
        provider=args.provider,
        model=args.model,
    )
    print(json.dumps(result, indent=1, default=str))
    return 0


def cmd_publish(args) -> int:
    evidence = _named_dependencies(list(args.evidence), option="--evidence")
    message = (
        Path(args.message_file).read_text(encoding="utf-8") if args.message_file else args.message
    )
    result = _bridge().publish_regions(
        lease_id=args.lease,
        seat_id=args.seat,
        holder_ref=args.holder_ref,
        function=args.function,
        message=message,
        evidence=evidence,
        provider=args.provider,
        model=args.model,
    )
    print(json.dumps(result, indent=1, default=str))
    return 0


def cmd_publication_status(args) -> int:
    result = _bridge().region_publication(
        lease_id=args.lease,
        publication_id=args.publication,
        as_of=args.as_of,
    )
    print(json.dumps(result, indent=1, default=str))
    return 0 if result["state"] in {"PREPARED", "SIGNED", "AUTHORIZED", "FINALIZED"} else 1


def cmd_prepare_publication(args) -> int:
    evidence = _named_dependencies(list(args.evidence), option="--evidence")
    message = (
        Path(args.message_file).read_text(encoding="utf-8") if args.message_file else args.message
    )
    result = _bridge().prepare_region_publication(
        lease_id=args.lease,
        seat_id=args.seat,
        holder_ref=args.holder_ref,
        function=args.function,
        base_ref=args.base_ref,
        affected_frontier_root=args.affected_frontier_root,
        rehearsal_evidence_root=args.rehearsal_evidence_root,
        forward_closure_root=args.forward_closure_root,
        message=message,
        evidence=evidence,
        provider=args.provider,
        model=args.model,
    )
    print(json.dumps(result, indent=1, default=str))
    return 0


def cmd_sign_publication(args) -> int:
    result = _bridge().sign_region_publication(
        lease_id=args.lease,
        publication_id=args.publication,
        expected_recovery_root=args.recovery_root,
        expected_candidate_commit=args.candidate_commit,
        expected_candidate_tree=args.candidate_tree,
        expected_patch_handle=args.patch_handle,
        expected_custody_handle=args.custody_handle,
        expected_affected_frontier_root=args.affected_frontier_root,
        expected_rehearsal_evidence_root=args.rehearsal_evidence_root,
        expected_forward_closure_root=args.forward_closure_root,
        seat_id=args.seat,
        holder_ref=args.holder_ref,
        function=args.function,
        role_profile_handle=args.role_profile_handle,
        reconstruction_handle=args.reconstruction_handle,
        predicate_result=args.predicate_result,
        expires_at=args.expires,
        provider=args.provider,
        model=args.model,
    )
    print(json.dumps(result, indent=1, default=str))
    return 0


def cmd_authorize_publication(args) -> int:
    result = _bridge().authorize_region_publication(
        lease_id=args.lease,
        publication_id=args.publication,
        expected_recovery_root=args.recovery_root,
        provider=args.provider,
        model=args.model,
    )
    print(json.dumps(result, indent=1, default=str))
    return 0


def cmd_finalize_publication(args) -> int:
    result = _bridge().finalize_region_publication(
        lease_id=args.lease,
        publication_id=args.publication,
        expected_recovery_root=args.recovery_root,
        provider=args.provider,
        model=args.model,
    )
    print(json.dumps(result, indent=1, default=str))
    return 0


def cmd_recover_publication(args) -> int:
    result = _bridge().recover_region_publication(
        lease_id=args.lease,
        publication_id=args.publication,
        expected_recovery_root=args.recovery_root,
        provider=args.provider,
        model=args.model,
    )
    print(json.dumps(result, indent=1, default=str))
    return 0


def _named_dependencies(values: list[str], *, option: str) -> dict[str, str]:
    roots: dict[str, str] = {}
    for raw in values:
        name, separator, value = raw.partition("=")
        name = name.strip()
        value = value.strip()
        if not separator or not name or not value:
            raise ValueError(f"{option} requires a non-empty name=value")
        if name == "body":
            raise ValueError("the body dependency root is owned by the exact message body")
        if name in roots:
            raise ValueError(f"duplicate dependency root name: {name}")
        roots[name] = value
    return roots


def cmd_send(args) -> int:
    body = Path(args.body_file).read_text(encoding="utf-8") if args.body_file else args.body
    if not body:
        print("send refused: empty body (--body or --body-file)", file=sys.stderr)
        return 2
    try:
        roots = _named_dependencies(list(args.root), option="--root")
        root_files = _named_dependencies(list(args.root_file), option="--root-file")
        overlap = sorted(set(roots).intersection(root_files))
        if overlap:
            raise ValueError(f"duplicate dependency root name: {overlap[0]}")
        bridge = _bridge()
        for name, raw_path in root_files.items():
            roots[name] = bridge.put_custody(Path(raw_path).read_bytes())
    except (OSError, ValueError) as exc:
        print(f"send refused: {exc}", file=sys.stderr)
        return 2
    r = bridge.send(
        sender_seat_id=args.sender,
        recipient_seat_id=args.to,
        message_type=args.type,
        body=body,
        dependency_roots=roots,
        idempotency_key=args.key,
        expires_at=args.expires,
        provider=args.provider,
        model=args.model,
    )
    print(json.dumps(r, indent=1, default=str))
    return 0


def cmd_consume_wake(args) -> int:
    """Receipt one opaque app wake token, then reconcile canonical Atlas read-only."""

    from laplace.representation.codex_seat_watcher import consume_wake_token

    result = consume_wake_token(
        seat_id=args.seat,
        thread_id=args.thread,
        token=args.token,
    )
    print(json.dumps(result, indent=1, default=str))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--provider", default=PROVIDER_DEFAULT)
    p.add_argument("--model", default=MODEL_DEFAULT)
    sub = p.add_subparsers(dest="cmd")

    s = sub.add_parser("inbox")
    s.add_argument("--seat", default=None)
    w = sub.add_parser("watch")
    w.add_argument("--seat", required=True)
    w.add_argument("--interval", type=int, default=30)
    w.add_argument("--once", action="store_true")
    w.add_argument(
        "--replay", action="store_true", help="also emit messages already pending at start"
    )
    for name, help_text in (
        ("pull", "graded pull: one line per message under a budget, bodies by descent"),
        ("drain", "graded pull + the watcher re-arm, one act (never acks)"),
    ):
        g = sub.add_parser(name, help=help_text)
        g.add_argument("--seat", required=True)
        g.add_argument(
            "--budget",
            type=int,
            default=DEFAULT_PULL_BUDGET,
            help="max messages served in this grade; 0 = no budget (displacement is always named)",
        )
        g.add_argument(
            "--preview-chars",
            type=int,
            default=DEFAULT_PREVIEW_CHARS,
            dest="preview_chars",
            help="body preview width in the grade line",
        )
        g.add_argument(
            "--message",
            action="append",
            default=[],
            help="descend: carry this message's FULL body; repeatable",
        )
        g.add_argument(
            "--full",
            action="store_true",
            help="descend into every message (the old flood, now explicit)",
        )
        g.add_argument(
            "--lines",
            action="store_true",
            help="print the grade lines instead of the JSON envelope",
        )
    bd = sub.add_parser("body", help="read-only full body for one message (no delivery claim)")
    bd.add_argument("--message", required=True)
    bd.add_argument("--raw", action="store_true", help="print the body text alone")
    rc = sub.add_parser("reconstruct")
    rc.add_argument("--seat", required=True)
    rc.add_argument("--message", required=True)
    rc.add_argument("--goal", required=True)
    cb = sub.add_parser(
        "custody-batch",
        help="one-process exact-ID reconstruction + acknowledgement phase for pulled mail",
    )
    cb.add_argument("--seat", required=True)
    cb.add_argument("--message", action="append", required=True)
    cb.add_argument("--goal", required=True)
    a = sub.add_parser("ack")
    a.add_argument("--seat", required=True)
    a.add_argument("--message", required=True)
    a.add_argument("--disposition", required=True, choices=["accepted", "refused"])
    a.add_argument("--note", default="")
    a.add_argument("--recon-event", default=None)
    a.add_argument("--recon-handle", default=None)
    su = sub.add_parser(
        "supersede",
        help="retire undelivered historical mail through delivered current-fibre replacements",
    )
    su.add_argument("--message", required=True)
    su.add_argument("--sender", required=True)
    su.add_argument("--replacement", action="append", required=True)
    su.add_argument("--note", required=True)
    sub.add_parser(
        "reissue-stage-zero-replacement",
        help=(
            "authenticated exact reissue of the frozen expired d041 migration envelope; "
            "accepts no caller-authored coordinate"
        ),
    )
    pf = sub.add_parser(
        "preserve-fork",
        help="quarantine one author-ruled cross-fibre obligation without delivery",
    )
    pf.add_argument("--seat", required=True)
    pf.add_argument("--message", required=True)
    pf.add_argument("--sender", required=True)
    pf.add_argument("--recipient", required=True)
    pf.add_argument("--body-handle", required=True)
    pf.add_argument("--ruling-ref", required=True)
    pf.add_argument("--authority-event", required=True)
    pf.add_argument("--reason", required=True)
    pf.add_argument("--reopen-condition", required=True)
    mr = sub.add_parser(
        "recover-legacy-bundle",
        help=(
            "atomically retire the complete replacement-derived v1 bundle under the exact "
            "Gerard author-turn commission reconstructed by current v2 Superego"
        ),
    )
    mr.add_argument("--seat", required=True, choices=("superego-seat",))
    mr.add_argument("--replacement", required=True)
    mr.add_argument("--authority-ack", required=True)
    st = sub.add_parser("status")
    st.add_argument("--message", required=True)
    ob = sub.add_parser(
        "obligations",
        help="read-only queued + pulled nonterminal obligations, recipient-scoped across fibres",
    )
    ob.add_argument("--seat", required=True)
    sub.add_parser("snapshot", help="read-only complete provider projection")
    mi = sub.add_parser(
        "messages", help="read-only message index; the supported prefix-resolution source"
    )
    mi.add_argument("--seat", default="")
    mi.add_argument(
        "--status",
        default="",
        choices=(
            "",
            "queued",
            "pulled",
            "delivered",
            "refused",
            "quarantined",
            "expired",
            "superseded",
        ),
    )
    ls = sub.add_parser("leases", help="read-only effective repository-region authority")
    ls.add_argument("--as-of", default="")
    co = sub.add_parser("checkout", help="acquire exact repository regions for a joined holder")
    co.add_argument("--seat", required=True)
    co.add_argument("--holder-ref", required=True)
    co.add_argument(
        "--function", required=True, choices=("ego", "superego", "sensorium", "provider")
    )
    co.add_argument("--act-id", required=True)
    co.add_argument("--region", action="append", required=True)
    co.add_argument("--expires", required=True)
    co.add_argument("--declaration-kind", default="native", choices=("native", "journal-bootstrap"))
    co.add_argument("--declaration-ref", required=True)
    co.add_argument("--crutch-file", default="")
    ci = sub.add_parser("checkin", help="close one lease with exact Git/worktree evidence")
    ci.add_argument("--lease", required=True)
    ci.add_argument("--seat", required=True)
    ci.add_argument("--holder-ref", required=True)
    ci.add_argument(
        "--function", required=True, choices=("ego", "superego", "sensorium", "provider")
    )
    ci.add_argument(
        "--outcome", required=True, choices=("committed", "noop", "abandoned", "failed")
    )
    ci.add_argument(
        "--evidence",
        action="append",
        default=[],
        help="named evidence root as name=value; repeatable",
    )
    pu = sub.add_parser(
        "publish",
        help="commit only one live lease's provisional edits and close it through Atlas",
    )
    pu.add_argument("--lease", required=True)
    pu.add_argument("--seat", required=True)
    pu.add_argument("--holder-ref", required=True)
    pu.add_argument(
        "--function", required=True, choices=("ego", "superego", "sensorium", "provider")
    )
    pu.add_argument("--message", default="")
    pu.add_argument("--message-file", default="")
    pu.add_argument(
        "--evidence",
        action="append",
        required=True,
        help="named verification root as name=value; repeatable",
    )
    ps = sub.add_parser("publication-status", help="read one exact prepared publication saga")
    ps.add_argument("--lease", required=True)
    ps.add_argument("--publication", required=True)
    ps.add_argument("--as-of", default="")
    pp = sub.add_parser(
        "prepare-publication",
        help="build an unreachable private-index candidate and durable recovery record",
    )
    pp.add_argument("--lease", required=True)
    pp.add_argument("--seat", required=True)
    pp.add_argument("--holder-ref", required=True)
    pp.add_argument(
        "--function", required=True, choices=("ego", "superego", "sensorium", "provider")
    )
    pp.add_argument("--base-ref", required=True)
    pp.add_argument("--affected-frontier-root", required=True)
    pp.add_argument("--rehearsal-evidence-root", required=True)
    pp.add_argument("--forward-closure-root", required=True)
    pp.add_argument("--message", default="")
    pp.add_argument("--message-file", default="")
    pp.add_argument("--evidence", action="append", required=True)
    sp = sub.add_parser(
        "sign-publication",
        help="append one current role PASS over an exact prepared local-ref candidate",
    )
    sp.add_argument("--lease", required=True)
    sp.add_argument("--publication", required=True)
    sp.add_argument("--recovery-root", required=True)
    sp.add_argument("--candidate-commit", required=True)
    sp.add_argument("--candidate-tree", required=True)
    sp.add_argument("--patch-handle", required=True)
    sp.add_argument("--custody-handle", required=True)
    sp.add_argument("--affected-frontier-root", required=True)
    sp.add_argument("--rehearsal-evidence-root", required=True)
    sp.add_argument("--forward-closure-root", required=True)
    sp.add_argument("--seat", required=True)
    sp.add_argument("--holder-ref", required=True)
    sp.add_argument(
        "--function", required=True, choices=("ego", "sensorium", "superego")
    )
    sp.add_argument("--role-profile-handle", required=True)
    sp.add_argument("--reconstruction-handle", required=True)
    sp.add_argument("--predicate-result", required=True, choices=("PASS",))
    sp.add_argument("--expires", required=True)
    for command, help_text in (
        ("authorize-publication", "durably authorize one exact update-ref CAS"),
        ("finalize-publication", "perform the authorized CAS and atomic checkin"),
        ("recover-publication", "recover one authorized publication after a crash"),
    ):
        parser = sub.add_parser(command, help=help_text)
        parser.add_argument("--lease", required=True)
        parser.add_argument("--publication", required=True)
        parser.add_argument("--recovery-root", required=True)
    sd = sub.add_parser("send")
    sd.add_argument("--sender", required=True)
    sd.add_argument("--to", required=True)
    sd.add_argument("--type", required=True)
    sd.add_argument("--key", required=True)
    sd.add_argument("--body", default="")
    sd.add_argument("--body-file", default="")
    sd.add_argument("--expires", required=True)
    sd.add_argument(
        "--root", action="append", default=[], help="dependency root as name=value; repeatable"
    )
    sd.add_argument(
        "--root-file",
        action="append",
        default=[],
        help=(
            "supporting file as name=path; bytes are banked in Atlas custody and the "
            "dependency root carries the resulting content handle; repeatable"
        ),
    )
    cw = sub.add_parser(
        "consume-wake",
        help="consume one opaque Codex wake token and reconcile Atlas (never delivery)",
    )
    cw.add_argument("--seat", required=True)
    cw.add_argument("--thread", required=True)
    cw.add_argument("--token", required=True)

    args = p.parse_args(argv)
    fn = {
        "inbox": cmd_inbox,
        "watch": cmd_watch,
        "pull": cmd_pull,
        "drain": cmd_drain,
        "body": cmd_body,
        "reconstruct": cmd_reconstruct,
        "custody-batch": cmd_custody_batch,
        "ack": cmd_ack,
        "supersede": cmd_supersede,
        "reissue-stage-zero-replacement": cmd_reissue_stage_zero_replacement,
        "preserve-fork": cmd_preserve_fork,
        "recover-legacy-bundle": cmd_recover_legacy_bundle,
        "status": cmd_status,
        "obligations": cmd_obligations,
        "snapshot": cmd_snapshot,
        "messages": cmd_messages,
        "leases": cmd_leases,
        "checkout": cmd_checkout,
        "checkin": cmd_checkin,
        "publish": cmd_publish,
        "publication-status": cmd_publication_status,
        "prepare-publication": cmd_prepare_publication,
        "sign-publication": cmd_sign_publication,
        "authorize-publication": cmd_authorize_publication,
        "finalize-publication": cmd_finalize_publication,
        "recover-publication": cmd_recover_publication,
        "send": cmd_send,
        "consume-wake": cmd_consume_wake,
    }.get(args.cmd or "inbox", cmd_inbox)
    if args.cmd is None:
        args.seat = None
    return fn(args)


def cli(argv=None) -> int:
    """Process boundary: lawful refusals stay machine-readable and traceback-free."""

    try:
        return main(argv)
    except (AtlasError, ValueError, OSError) as exc:
        print(
            json.dumps(
                {
                    "schema_version": "laplace.cli-refusal/1",
                    "refused": True,
                    "residue": {
                        "code": str(getattr(exc, "reason", "cli-refused"))
                        .upper()
                        .replace("-", "_"),
                        "message": str(exc),
                        "detail": dict(getattr(exc, "detail", {}) or {}),
                    },
                },
                indent=1,
                default=str,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(cli())
