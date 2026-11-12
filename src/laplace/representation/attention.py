"""One bounded attention projection over Atlas mail and replaceable provider leases.

Atlas remains the sole message/cursor truth.  This module derives the small object consumed by
wake, provider hooks and the eventual conversation serve; it owns no cursor and writes nothing.
"""
from __future__ import annotations
from laplace.core.checkout import source_tree

import hashlib
import json
import shlex
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ATTENTION_SCHEMA = "laplace.representation.attention-epoch/1"
ACTIONABLE_STATES = {"queued", "pulled", "reconstructed"}


def _chash(value: object) -> str:
    """Bootstrap copy of the Atlas canonical hash law; checked by attention tests."""

    canonical = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _proofs_by_message(state: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    proofs: dict[str, list[dict[str, Any]]] = {}
    for event_id, raw in state.get("reconstruction_proofs", {}).items():
        evaluation = raw.get("evaluation", {})
        message_id = evaluation.get("arguments", {}).get("message_id")
        if not message_id:
            continue
        outputs = list(evaluation.get("output_handles", []))
        proofs.setdefault(str(message_id), []).append({
            "event_id": str(event_id),
            "output_handles": outputs,
        })
    return proofs


def project_attention_from_state(
    state: Mapping[str, Any],
    *,
    seat_id: str | None,
    watcher: Mapping[str, Any] | None = None,
    message_cap: int = 12,
) -> dict[str, Any]:
    """Derive an attention epoch from a provider snapshot without changing its cursor."""

    context = state["active_context"]
    assumption = str(context["assumption"])
    fibre = str(context["fibre"])
    cursors: dict[str, int] = {}
    for recipient, rows in state.get("seat_cursors", {}).items():
        cursors[str(recipient)] = max(
            (
                int(row.get("cursor", 0))
                for row in rows
                if row.get("assumption") == assumption and row.get("fibre") == fibre
            ),
            default=0,
        )
    proofs = _proofs_by_message(state)
    actionable: list[dict[str, Any]] = []
    terminal_counts: dict[str, int] = {}
    for materialized in state.get("messages", {}).values():
        message = materialized.get("message", {})
        recipient = str(message.get("recipient_seat_id", ""))
        if seat_id is not None and recipient != seat_id:
            continue
        if (
            materialized.get("assumption") != assumption
            or materialized.get("fibre") != fibre
        ):
            continue
        canonical_status = str(materialized.get("status", "unknown"))
        cursor = int(message.get("cursor", 0))
        if canonical_status == "queued" and cursor <= cursors.get(recipient, 0):
            # A cursor contradiction is never presented as actionable new mail.  The canonical
            # replay/store verifier owns the stronger integrity refusal.
            continue
        phase = canonical_status
        proof_rows = proofs.get(str(message.get("message_id")), [])
        if canonical_status == "pulled" and proof_rows:
            phase = "reconstructed"
        if phase not in ACTIONABLE_STATES:
            terminal_counts[canonical_status] = terminal_counts.get(canonical_status, 0) + 1
            continue
        actionable.append({
            "message_id": message.get("message_id"),
            "from": message.get("sender_seat_id"),
            "to": recipient,
            "type": message.get("message_type"),
            "cursor": cursor,
            "expires_at": message.get("expires_at"),
            "state": phase,
            "reconstruction_event_id": (
                proof_rows[-1]["event_id"] if proof_rows else None
            ),
            "reconstruction_handle": (
                proof_rows[-1]["output_handles"][0]
                if proof_rows and proof_rows[-1]["output_handles"] else None
            ),
        })
    actionable.sort(key=lambda row: (str(row["to"]), int(row["cursor"])))
    ids = [str(row["message_id"]) for row in actionable]
    cursors_in_epoch = [int(row["cursor"]) for row in actionable]
    watcher_row = dict(watcher or {})
    lease_generation = watcher_row.get("lease_generation")
    epoch_handle = _chash({
        "schema_version": ATTENTION_SCHEMA,
        "seat_id": seat_id,
        "active_context": {"assumption": assumption, "fibre": fibre},
        "pending_message_ids": ids,
        "lease_generation": lease_generation,
    })
    return {
        "schema_version": ATTENTION_SCHEMA,
        "epoch_handle": epoch_handle,
        "status": "PENDING" if actionable else "CLEAR",
        "posture": "needs-attention" if actionable else "quiet",
        "pending_count": len(actionable),
        "pending": actionable[:message_cap],
        "omitted": max(0, len(actionable) - message_cap),
        "pending_cursor_floor": min(cursors_in_epoch) if cursors_in_epoch else None,
        "pending_cursor_ceiling": max(cursors_in_epoch) if cursors_in_epoch else None,
        "seat_id": seat_id,
        "scope": "bound-seat" if seat_id else "all-seats-diagnostic",
        "active_context": {"assumption": assumption, "fibre": fibre},
        "caused_by_event_cursor": int(state.get("event_count", 0)),
        "head_event_id": state.get("head_event_id"),
        "terminal_counts": dict(sorted(terminal_counts.items())),
        "action": (
            f"{seat_id or 'recipient seats'} must complete pull, reconstruction and "
            "acknowledgement before unrelated work"
            if actionable else "none"
        ),
        "read_only": True,
        "watcher": watcher_row,
    }


def project_attention_from_mail_frontier(
    frontier: Mapping[str, Any],
    *,
    seat_id: str,
    watcher: Mapping[str, Any] | None = None,
    message_cap: int = 12,
) -> dict[str, Any]:
    """Derive wake attention from one head-bound recipient frontier.

    Unlike ``project_attention_from_state``, this path never materialises the global provider
    face.  The frontier is already verified against the canonical Atlas head and contains only
    the recipient's queued or pulled nonterminal obligations.
    """

    if frontier.get("status") != "CURRENT" or frontier.get("seat_id") != seat_id:
        raise ValueError("seat mail frontier is not current for the bound recipient")
    raw = frontier.get("pending_messages")
    if not isinstance(raw, list):
        raise ValueError("cold seat mail frontier must expose its nonterminal obligations")
    actionable = []
    for message in raw:
        status = str(message.get("status") or "")
        if status not in {"queued", "pulled"}:
            raise ValueError("seat mail frontier exposed a terminal obligation")
        actionable.append({
            "message_id": message.get("message_id"),
            "from": message.get("sender_seat_id"),
            "to": message.get("recipient_seat_id"),
            "type": message.get("message_type"),
            "cursor": int(message.get("cursor", 0)),
            "expires_at": message.get("expires_at"),
            "state": status,
            "reconstruction_event_id": None,
            "reconstruction_handle": None,
        })
    actionable.sort(key=lambda row: int(row["cursor"]))
    watcher_row = dict(watcher or {})
    drift = dict(frontier.get("drift_token") or {})
    epoch_handle = _chash({
        "schema_version": ATTENTION_SCHEMA,
        "seat_id": seat_id,
        "mail_token": dict(frontier.get("mail_token") or {}),
        "lease_generation": watcher_row.get("lease_generation"),
    })
    return {
        "schema_version": ATTENTION_SCHEMA,
        "epoch_handle": epoch_handle,
        "status": "PENDING" if actionable else "CLEAR",
        "posture": "needs-attention" if actionable else "quiet",
        "pending_count": len(actionable),
        "pending": actionable[:message_cap],
        "omitted": max(0, len(actionable) - message_cap),
        "pending_cursor_floor": (
            min(row["cursor"] for row in actionable) if actionable else None
        ),
        "pending_cursor_ceiling": (
            max(row["cursor"] for row in actionable) if actionable else None
        ),
        "seat_id": seat_id,
        "scope": "bound-seat",
        "active_context": None,
        "caused_by_event_cursor": int(drift.get("cursor", 0)),
        "head_event_id": drift.get("head_event_id"),
        "head_record_digest": drift.get("head_record_digest"),
        "mail_token": dict(frontier.get("mail_token") or {}),
        "terminal_counts": {},
        "action": (
            f"{seat_id} must verify exact status and complete the remaining pull, "
            "reconstruction and acknowledgement acts before unrelated work"
            if actionable
            else "none"
        ),
        "read_metrics": dict(frontier.get("read_metrics") or {}),
        "read_only": True,
        "watcher": watcher_row,
    }


def project_attention(
    *, seat_id: str | None, message_cap: int = 12, include_watcher: bool = True
) -> dict[str, Any]:
    """Read the live Atlas snapshot and current ephemeral transport lease."""

    from laplace.representation import atlas_bridge, codex_seat_watcher

    watcher = (
        codex_seat_watcher.projection(seat_id or codex_seat_watcher.DEFAULT_SEAT_ID)
        if include_watcher
        else {}
    )
    return project_attention_from_state(
        atlas_bridge.snapshot()["provider"],
        seat_id=seat_id,
        watcher=watcher,
        message_cap=message_cap,
    )


def _exact_recovery_command(command: str) -> bool:
    """Recognise one recovery capability, never a shell program containing one."""

    if not command.strip() or any(
        marker in command for marker in ("\n", "\r", "#", ";", "&", "|", "<", ">", "`", "$(")
    ):
        return False
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return False
    if len(tokens) < 3 or tokens[0] != "/usr/bin/python3":
        return False
    if tokens[1:3] == ["-m", "laplace.engine.startup_mail_gate"]:
        return True
    repo_root = source_tree()
    try:
        script = Path(tokens[1])
        resolved = (repo_root / script).resolve() if not script.is_absolute() else script.resolve()
    except (OSError, RuntimeError):
        return False
    if resolved == (repo_root / "scripts" / "wake.py").resolve():
        return tokens[2:] == ["--fabric"]
    if resolved != (repo_root / "scripts" / "seat_fabric.py").resolve():
        return False
    return tokens[2] in {
        "inbox",
        "pull",
        "body",
        "reconstruct",
        "ack",
        "status",
        "obligations",
        "consume-wake",
    }


def _is_fabric_act(event: Mapping[str, Any]) -> bool:
    tool_name = str(event.get("tool_name", ""))
    if tool_name in {
        "laplace_seat_pull",
        "laplace_seat_body",
        "laplace_seat_reconstruct",
        "laplace_seat_ack",
        "laplace_seat_status",
    }:
        return True
    tool_input = event.get("tool_input", {})
    command = str(tool_input.get("command", "")) if isinstance(tool_input, Mapping) else ""
    return _exact_recovery_command(command)


def hook_response(
    event: Mapping[str, Any], projection: Mapping[str, Any]
) -> dict[str, Any]:
    """Translate one attention epoch into Codex lifecycle-hook control output."""

    name = str(event.get("hook_event_name", ""))
    if projection.get("status") in {"LEGACY-PROMPT-INERT", "STALE-PROMPT-INERT"}:
        default_classification = (
            "LEGACY-INERT" if projection.get("status") == "LEGACY-PROMPT-INERT"
            else "STALE-INERT"
        )
        classification = str(
            projection.get("attention_classification") or default_classification
        )
        instruction = (
            f"ATLAS ATTENTION CLASSIFICATION: {classification}. This provider watcher prompt "
            "has no current seat/task lease authority and grants no work or delivery authority. "
            "Do not pull, acknowledge, change priority, send a reply, or restart a watcher "
            "because of it; reconstruct only the current canonical recipient frontier."
        )
        if name == "UserPromptSubmit":
            return {"decision": "block", "reason": instruction}
        return {
            "hookSpecificOutput": {
                "hookEventName": name or "UserPromptSubmit",
                "additionalContext": instruction,
            }
        }
    if projection.get("status") == "UNCLAIMED":
        instruction = (
            "ATLAS SEAT JOIN REQUIRED: this provider task has no exact bound logical seat. "
            "Run the assigned laplace.engine.startup_mail_gate command before substantive tools, edits, "
            "verdicts, or dispatches; a provider process is not itself a seat."
        )
        if name == "PreToolUse":
            if _is_fabric_act(event):
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "additionalContext": instruction,
                    }
                }
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": instruction,
                }
            }
        if name == "Stop":
            return {"decision": "block", "reason": instruction}
        return {
            "hookSpecificOutput": {
                "hookEventName": name or "UserPromptSubmit",
                "additionalContext": instruction,
            }
        }
    if projection.get("status") == "UNAVAILABLE":
        warning = (
            "Atlas attention state is UNAVAILABLE; do not infer an empty inbox. "
            + str(projection.get("reason", "unknown fault"))
        )
        if name == "PreToolUse":
            if _is_fabric_act(event):
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "additionalContext": warning,
                    }
                }
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": warning,
                }
            }
        if name == "Stop" and not event.get("stop_hook_active"):
            return {"decision": "block", "reason": warning}
        return {"systemMessage": warning}
    if projection.get("status") != "PENDING":
        return {}
    pending = projection.get("pending", [])
    summary = ", ".join(
        f"{row.get('message_id')}:{row.get('state')} from {row.get('from')} "
        f"({row.get('type')})"
        for row in pending
    )
    instruction = (
        "ATLAS ATTENTION BOUNDARY: canonical logical-seat work is pending: "
        f"{summary}. Verify exact status; complete pull -> typed reconstruction -> exact-proof "
        "acknowledgement before unrelated work. Never duplicate an act."
    )
    if name == "PreToolUse":
        if _is_fabric_act(event):
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "additionalContext": instruction,
                }
            }
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": instruction,
            }
        }
    if name == "PostToolUse":
        return {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": instruction,
            }
        }
    if name == "UserPromptSubmit":
        return {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": instruction,
            }
        }
    if name == "Stop":
        return {"decision": "block", "reason": instruction}
    return {"systemMessage": instruction}


__all__ = [
    "ATTENTION_SCHEMA",
    "hook_response",
    "project_attention",
    "project_attention_from_mail_frontier",
    "project_attention_from_state",
]
