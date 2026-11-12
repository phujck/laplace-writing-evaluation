"""Evergreen root-seat context: a profile routes exact typed descent on every turn.

This is deliberately read-only and non-authorizing.  The cached head is only a routing map; the
content injected into a turn is freshly descended from its typed sources.  A stale/missing route
is FOG/UNKNOWN and is never replaced with a filename read, fuzzy match, or platform summary.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from laplace.engine import descent
from laplace.representation.embedding_health import read_health
from laplace.representation.semantic_cadence import process_start_token
from laplace.representation.semantic_vertical import canonical_bytes, digest

TURN_SCHEMA = "laplace.turn-reconstruction/1"
HEADS_SCHEMA = "laplace.evergreen-seat-context-heads/1"
HEADS_PATH = Path("semantic/seat_context_heads.json")
_FUNCTION_FOR_SEAT = {
    "ego-seat": "ego",
    "sensorium-seat": "aisthesis",
    "superego-seat": "superego",
}
_SEAT_FOR_FUNCTION = {value: key for key, value in _FUNCTION_FOR_SEAT.items()}
_EXACT_HANDLE = re.compile(
    r"(?<![A-Za-z0-9_.-])(?:WO-[A-Za-z0-9_.:-]+|message:[A-Za-z0-9]+|"
    r"(?:seat|region-lease|publication|recovery|revision|corpus|fabric|custody):[A-Za-z0-9_.:-]+)"
)


def _observed_at() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _head_body(value: Mapping[str, Any]) -> bytes:
    return canonical_bytes(value)


def build_heads(
    repo_root: Path | str,
    *,
    profile_handles: Mapping[str, str],
    goal_context: Mapping[str, Any],
    seat_generations: Mapping[str, str | None] | None = None,
) -> dict[str, Any]:
    """Write one shared content-addressed routing projection for all three functions."""

    root = Path(repo_root).resolve()
    seats = goal_context.get("seats") or {}
    generations = dict(seat_generations or {})
    from laplace.engine.compaction_submergence import consume_hierarchy_derivation

    phase = consume_hierarchy_derivation(semantic_fold_handle=None)
    profiles: dict[str, Any] = {}
    for function in ("ego", "aisthesis", "superego"):
        overlay = seats.get(function) or {}
        profiles[function] = {
            "function": function,
            "seat_id": _SEAT_FOR_FUNCTION[function],
            "task_id": overlay.get("task"),
            "generation": generations.get(_SEAT_FOR_FUNCTION[function]),
            "profile_handle": profile_handles[function],
            "phase_policy_handle": (phase.get("receipt") or {}).get("policy_handle"),
            "coordination_custody_handle": (
                "sha256:d8af14c3b8703b2d271597f2b1b9764f6f523d9d86c189dc450225eb90cf8407"
            ),
            "goal_digest": digest({
                "goal": overlay.get("goal"),
                "current_outcome": overlay.get("current_outcome"),
                "priority_frontier": goal_context.get("priority_frontier"),
            }),
            "routes": [
                {
                    "purpose": "complete-seat-goal-and-next-actions",
                    "kind": "atlas-custody",
                    "reference": profile_handles[function],
                    "source": "",
                    "budget": 20_000,
                },
                {
                    "purpose": "current-P0-P1-P2-development-frontier",
                    "kind": "ledger-row",
                    "reference": "OP-DEVELOPMENT-WORK-MAP",
                    "source": "semantic_operational_sources",
                    "budget": 8_000,
                },
                {
                    "purpose": "latest-disagreement-refusal-and-fog",
                    "kind": "ledger-row",
                    "reference": "OP-EXPLICIT-OMISSIONS-REFUSALS",
                    "source": "semantic_operational_sources",
                    "budget": 8_000,
                },
                {
                    "purpose": "active-custody-root",
                    "kind": "ledger-row",
                    "reference": "OP-CUSTODY-INVENTORY",
                    "source": "semantic_operational_sources",
                    "budget": 4_000,
                },
                {
                    "purpose": "semantic-fold-forward-link-and-health",
                    "kind": "repository-file",
                    "reference": ".semantic_fold_manifest.json",
                    "source": "",
                    "budget": 12_000,
                },
            ],
        }
    body = {
        "schema_version": HEADS_SCHEMA,
        "shared": True,
        "source_goal_context_handle": digest(goal_context),
        "profiles": profiles,
        "selection_law": (
            "profile routes plus exact author-turn handles only; watcher prompts select only "
            "the current canonical pending frontier; fuzzy and platform-summary fallback forbidden"
        ),
        "authority_effect": "none",
        "phase_policy_consumption": phase["receipt"],
    }
    body["heads_handle"] = digest(body)
    path = root / HEADS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_head_body(body) + b"\n")
    return body


def load_heads(repo_root: Path | str) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    value = json.loads((root / HEADS_PATH).read_text(encoding="utf-8"))
    carried = value.pop("heads_handle", None)
    if value.get("schema_version") != HEADS_SCHEMA or digest(value) != carried:
        raise RuntimeError("evergreen seat context heads are malformed or moved")
    return {**value, "heads_handle": carried}


def _function(heads: Mapping[str, Any], *, function: str, seat_id: str, thread_id: str) -> str:
    candidate = function.strip().lower()
    if candidate == "sensorium":
        candidate = "aisthesis"
    if candidate in _SEAT_FOR_FUNCTION:
        return candidate
    if seat_id in _FUNCTION_FOR_SEAT:
        return _FUNCTION_FOR_SEAT[seat_id]
    matches = [
        key for key, value in (heads.get("profiles") or {}).items()
        if isinstance(value, Mapping) and value.get("task_id") == thread_id
    ]
    if len(matches) == 1:
        return str(matches[0])
    raise RuntimeError("root-seat function cannot be resolved exactly")


def _git_dirty_custody(root: Path) -> dict[str, Any]:
    """Return a bounded invalidation token, not a full-worktree byte rehash.

    Exact byte custody is paid at fold capture/freeze.  The hot hook needs only to prove whether
    that coordinate's affected path set moved; hashing every dirty UI artifact on every prompt is
    itself the compaction/scaffold failure this organ retires.
    """
    result = subprocess.run(
        ["git", "status", "--porcelain=v2", "-z", "--untracked-files=normal"],
        cwd=root, capture_output=True, check=True,
    )
    rows = []
    for item in result.stdout.split(b"\0"):
        if not item:
            continue
        text = item.decode("utf-8", errors="strict")
        fields = text.split(" ")
        relative = fields[-1]
        rows.append({"record": fields[0], "path": relative, "invalidation": text})
    rows.sort(key=lambda row: row["path"])
    return {
        "paths": [{"record": row["record"], "path": row["path"]} for row in rows],
        "count": len(rows),
        "invalidation_root": digest(rows),
        "byte_custody": "deferred to explicit fold capture/freeze",
    }


def _prompt_handles(prompt: str) -> list[str]:
    return list(dict.fromkeys(match.group(0).rstrip(".,;)") for match in _EXACT_HANDLE.finditer(prompt)))


def _typed_route(reference: str) -> dict[str, str] | None:
    return descent.normalize_target(reference)


def _merge_hook_context(base: Mapping[str, Any], turn: Mapping[str, Any]) -> dict[str, Any]:
    turn_text = "TURN RECONSTRUCTION:\n" + json.dumps(
        turn, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    if base.get("decision") == "block":
        return dict(base)
    output = dict(base.get("hookSpecificOutput") or {})
    prior = output.get("additionalContext")
    output["hookEventName"] = output.get("hookEventName") or "UserPromptSubmit"
    output["additionalContext"] = f"{prior}\n\n{turn_text}" if prior else turn_text
    return {**{key: value for key, value in base.items() if key != "hookSpecificOutput"},
            "hookSpecificOutput": output}


def reconstruct_turn(
    repo_root: Path | str,
    *,
    event_name: str,
    prompt: str,
    function: str = "",
    seat_id: str = "",
    thread_id: str = "",
    attention_projection: Mapping[str, Any] | None = None,
    required_routes: Sequence[Mapping[str, Any]] = (),
    record_observation: bool = False,
) -> dict[str, Any]:
    """Perform the bounded typed descents for one substantive root-seat boundary."""

    started = time.perf_counter_ns()
    root = Path(repo_root).resolve()
    # THE CUSTODY SWITCH (his ruling 2026-09-14, laplace.representation.custody_mode): no root seat is
    # resolved while the mode is OFF, so a wake never returns FOG for want of a seat.
    from laplace.representation import custody_mode
    if custody_mode.is_off(root):
        return {
            "schema_version": "laplace.turn-reconstruction/1",
            "status": "CUSTODY-OFF",
            "event": event_name,
            "selected": [],
            "fog": [],
            "read_only": True,
            "authority_effect": "none",
            "canonical_authority_write": "none",
            "local_telemetry_effect": "none; custody mode OFF",
            "custody_mode": custody_mode.read(root),
            "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "performance": {"elapsed_ms": round((time.perf_counter_ns() - started) / 1e6, 3),
                            "descent_count": 0},
        }
    fog: list[dict[str, Any]] = []
    try:
        heads = load_heads(root)
        resolved_function = _function(
            heads, function=function, seat_id=seat_id, thread_id=thread_id
        )
        head = (heads.get("profiles") or {}).get(resolved_function)
        if not isinstance(head, Mapping):
            raise RuntimeError("evergreen context omits the resolved function profile")
        head = dict(head)
        health = read_health(root)
        phase_receipt = heads.get("phase_policy_consumption") or {}
        if phase_receipt.get("status") != "CONSUMED":
            fog.append({
                "purpose": "hierarchy-phase-policy",
                "status": "FOG",
                "reason": "fresh hierarchy phase derivation is not consumed",
            })
        expected_profile = (health.get("profile_handles") or {}).get(resolved_function)
        active_compaction = None
        if thread_id:
            from laplace.engine.compaction_boundary import active_profile

            active_compaction = active_profile(thread_id)
        if isinstance(active_compaction, Mapping):
            active_function = str(active_compaction.get("function") or "")
            if active_function == "sensorium":
                active_function = "aisthesis"
            fold = health.get("side_ref_fold") or {}
            up_down = health.get("up_down") or {}
            if (
                active_function != resolved_function
                or active_compaction.get("seat_id") != head.get("seat_id")
                or active_compaction.get("semantic_fold_health_handle")
                != fold.get("manifest_handle")
                or active_compaction.get("semantic_fold_receipt_handle")
                != up_down.get("receipt_handle")
            ):
                raise RuntimeError(
                    "sealed PostCompact profile is stale against the current seat or fold"
                )
            expected_profile = str(active_compaction["profile_handle"])
            old_profile = head.get("profile_handle")
            head["profile_handle"] = expected_profile
            head["generation"] = active_compaction.get("generation")
            head["routes"] = [
                route
                for route in head.get("routes") or ()
                if not (
                    route.get("kind") == "atlas-custody"
                    and route.get("reference") == old_profile
                )
            ]
            head["routes"].insert(0, {
                "purpose": "sealed-postcompact-function-profile",
                "kind": "atlas-custody",
                "reference": expected_profile,
                "source": "",
                "budget": 20_000,
            })
            transcript_delta = active_compaction.get("transcript_delta")
            if isinstance(transcript_delta, Mapping):
                route = transcript_delta.get("typed_descent")
                if isinstance(route, Mapping):
                    head["routes"].append({
                        "purpose": "sealed-postcompact-transcript-delta",
                        "kind": route.get("kind"),
                        "reference": route.get("reference"),
                        "source": route.get("source") or "",
                        "budget": max(1, int(
                            transcript_delta.get("semantic_bytes")
                            or transcript_delta.get("suffix_bytes")
                            or 8_000
                        )),
                    })
        if expected_profile != head.get("profile_handle"):
            raise RuntimeError(
                "evergreen function profile is stale against the shared fold health"
            )
        routes = [dict(route) for route in head.get("routes") or ()]
        routes.extend(dict(route) for route in required_routes)
        watcher = prompt.startswith("[Eigen Fabric watcher]")
        if watcher:
            # The old bug was born here: an old watcher prompt reselected an already-consumed
            # message after compaction.  Only the freshly projected pending frontier may add a
            # Fabric route; opaque prompt bytes are never parsed as work.
            pending = [
                item for item in (attention_projection or {}).get("pending") or []
                if isinstance(item, Mapping)
                and str(item.get("message_id", "")).startswith("message:")
            ]
            if len(pending) == 1:
                item = pending[0]
                routes.append({
                        "purpose": "current-pending-fabric-message",
                        "kind": "fabric-message",
                        "reference": item["message_id"],
                        "source": "",
                        "budget": 12_000,
                })
            elif len(pending) > 1:
                fog.append({
                    "purpose": "current-pending-fabric-message",
                    "status": "FOG",
                    "reason": "multiple pending Fabric candidates require explicit selection",
                    "candidate_message_ids": [item["message_id"] for item in pending],
                })
        else:
            for reference in _prompt_handles(prompt):
                typed = _typed_route(reference)
                if typed is not None:
                    routes.append({
                        "purpose": "author-turn-selected-handle",
                        "kind": typed["kind"],
                        "reference": reference,
                        "source": typed["source"],
                        "fold": typed["fold"],
                        "budget": 12_000,
                    })
        unique: dict[tuple[str, str, str], dict[str, Any]] = {}
        for route in routes:
            key = (str(route["kind"]), str(route["reference"]), str(route.get("source") or ""))
            unique.setdefault(key, route)
        selected = []
        for route in unique.values():
            try:
                result = descent.descend(
                    kind=str(route["kind"]),
                    reference=str(route["reference"]),
                    source=str(route.get("source") or ""),
                    fold=str(route.get("fold") or ""),
                    goal=prompt,
                    seat_id=str(head["seat_id"]),
                    content_budget=int(route.get("budget", 8_000)),
                    record_telemetry=False,
                )
                selected.append({
                    "purpose": route["purpose"],
                    "kind": route["kind"],
                    "reference": route["reference"],
                    "source": route.get("source") or "",
                    "fold": route.get("fold") or "",
                    "content_status": result.get("content_status"),
                    "content_handle": result.get("content_handle"),
                    "content": result.get("content"),
                    "content_next_offset": result.get("content_next_offset"),
                    "current_root": result.get("current_root"),
                    "authority_root": result.get("authority_root"),
                    "descent_telemetry": result.get("telemetry"),
                    "read_only": True,
                })
            except Exception as exc:  # noqa: BLE001 - a missing route is explicit FOG
                fog.append({
                    "purpose": route["purpose"],
                    "kind": route["kind"],
                    "reference": route["reference"],
                    "status": "FOG",
                    "reason": f"{type(exc).__name__}: {exc}",
                })
        health_status = (health.get("side_ref_fold") or {}).get("status", "UNKNOWN")
        dirty = _git_dirty_custody(root)
        goal_digest = digest({"goal_utf8": prompt})
        from laplace.engine.compaction_submergence import admit_continuation

        continuation = admit_continuation(
            function=resolved_function,
            seat_id=str(head["seat_id"]),
            generation=str(head.get("generation") or "") or None,
            goal_digest=goal_digest,
            profile_handle=str(head.get("profile_handle") or "") or None,
            expected_profile_handle=expected_profile,
            semantic_health=health,
            typed_descents=selected,
            fog=fog,
            watcher_state=attention_projection,
        )
        body = {
            "schema_version": TURN_SCHEMA,
            "status": continuation["status"],
            "event": event_name,
            "seat_id": head["seat_id"],
            "function": resolved_function,
            "goal_author_turn_digest": goal_digest,
            "profile_handle": head["profile_handle"],
            "profile_heads_handle": heads["heads_handle"],
            "compaction_boundary_handle": None
            if not isinstance(active_compaction, Mapping)
            else active_compaction.get("boundary_handle"),
            "transcript_delta_handle": None
            if not isinstance(active_compaction, Mapping)
            else (active_compaction.get("transcript_delta") or {}).get("delta_handle"),
            "semantic_fold_health_handle": (health.get("side_ref_fold") or {}).get("manifest_handle"),
            "semantic_fold_receipt_handle": (health.get("up_down") or {}).get(
                "receipt_handle"
            ),
            "semantic_register_generation": (health.get("up_down") or {}).get(
                "register_generation"
            ),
            "semantic_health_status": health_status,
            "semantic_horizon": (health.get("side_ref_fold") or {}).get("semantic_horizon"),
            "source_roots": {
                "current_source": health.get("current_source"),
                "coverage": (health.get("side_ref_fold") or {}).get("coverage_handle"),
                "dirty_custody": dirty,
            },
            "selected": selected,
            "selected_nodes": [row["reference"] for row in selected],
            "selected_edges": [
                row for row in selected if row["kind"] == "atlas-object"
            ],
            "fog": fog,
            "continuation_decision": continuation,
            "fallback": "FORBIDDEN: no platform-summary, filename, or fuzzy substitution",
            "claims_with_unknown_context": continuation["status"] != "ADMITTED",
            "read_only": True,
            "authority_effect": "none",
            "canonical_authority_write": "none",
            "local_telemetry_effect": (
                "best-effort bounded latest-consumption receipt outside immutable fold"
            ),
            "observed_at": _observed_at(),
            "process": {
                "pid": os.getpid(),
                "start_token": process_start_token(),
            },
        }
        body["performance"] = {
            "elapsed_ms": round((time.perf_counter_ns() - started) / 1_000_000, 3),
            "descent_count": len(selected) + len(fog),
            "target_ms": 50,
        }
        body["receipt_handle"] = digest(body)
        try:
            from laplace.representation.semantic_cadence import read_state, record_consumption

            fold = health.get("side_ref_fold") or {}
            if record_observation:
                record_consumption(
                    kind="turn-descent",
                    source_commit=fold.get("source_commit"),
                    output_commit=fold.get("output_commit"),
                    manifest_handle=fold.get("manifest_handle"),
                    artifact_root=(health.get("artifacts") or {}).get("root"),
                    process_generation=read_state().get("generation"),
                    repository_generation=health.get("current_source") or {},
                    result={
                        "status": body["status"],
                        "receipt_handle": body["receipt_handle"],
                        "selected_nodes": body["selected_nodes"],
                        "fog_count": len(body["fog"]),
                    },
                )
        except Exception:
            pass  # the read-only turn survives a local observation-receipt fault
        return body
    except Exception as exc:  # noqa: BLE001 - context failure warns; it does not block a prompt
        body = {
            "schema_version": TURN_SCHEMA,
            "status": "UNKNOWN",
            "event": event_name,
            "goal_author_turn_digest": digest({"goal_utf8": prompt}),
            "selected": [],
            "fog": [{"status": "FOG", "reason": f"{type(exc).__name__}: {exc}"}],
            "fallback": "FORBIDDEN: no platform-summary, filename, or fuzzy substitution",
            "claims_with_unknown_context": True,
            "read_only": True,
            "authority_effect": "none",
            "canonical_authority_write": "none",
            "local_telemetry_effect": "none; reconstruction failed before telemetry",
            "observed_at": _observed_at(),
            "process": {
                "pid": os.getpid(),
                "start_token": process_start_token(),
            },
        }
        body["performance"] = {
            "elapsed_ms": round((time.perf_counter_ns() - started) / 1_000_000, 3),
            "descent_count": 0,
            "target_ms": 50,
        }
        body["receipt_handle"] = digest(body)
        return body


def hook_response(base: Mapping[str, Any], turn: Mapping[str, Any]) -> dict[str, Any]:
    return _merge_hook_context(base, turn)


__all__ = [
    "HEADS_PATH", "HEADS_SCHEMA", "TURN_SCHEMA", "build_heads", "hook_response",
    "load_heads", "reconstruct_turn",
]
