"""A bounded, read-only map of live builder/reviewer work.

The canonical evidence is append-only Atlas history; the live coordinate is a head-bound,
replaceable Atlas projection.  Publication creates one open row and a valid reverse-route reviewer
decision closes that same row.  Wake verifies every unresolved Git candidate and only a bounded
terminal tail, so completed work does not become permanent startup context.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from laplace.representation.atlas_bridge import chash
from laplace.representation.atlas_bridge import effective_region_lease_projection
from laplace.representation.atlas_bridge import LEGACY_UNTYPED_REVIEW_DECISIONS, LEGACY_UNTYPED_REVIEW_VERDICT_IDS

WORK_MAP_SCHEMA = "laplace.development-work-map/1"
_FROZEN_KEYS = ("frozen_commit", "frozen_tree", "frozen_diff_sha256")


def _utc_text(value: datetime) -> str:
    """Render the observation boundary carried by the exact shown state."""

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _delivery_projection(
    row: Mapping[str, Any], *, evidence_mode: str
) -> dict[str, Any]:
    """Expose receipt state without treating an asserted status as delivery proof."""

    if evidence_mode not in {"strict", "legacy-full-state"}:
        raise ValueError(f"unknown delivery evidence mode: {evidence_mode}")
    status = str(row.get("status", "unknown"))
    receipt_keys = (
        "last_pull_event_id", "acknowledgement_event_id", "reconstruction_handle"
    )
    strict_proof = all(row.get(key) for key in receipt_keys)
    no_receipt_fields = not any(key in row for key in receipt_keys)
    legacy_fold_proof = evidence_mode == "legacy-full-state" and no_receipt_fields
    return {
        "status": status,
        "delivered": status == "delivered" and (strict_proof or legacy_fold_proof),
        "evidence_mode": evidence_mode,
        "strict_proof_complete": strict_proof,
        "legacy_full_state_compatibility": legacy_fold_proof,
        "pull_event_id": row.get("last_pull_event_id"),
        "acknowledgement_event_id": row.get("acknowledgement_event_id"),
        "reconstruction_handle": row.get("reconstruction_handle"),
    }


def _source_links(
    *, commission: Mapping[str, Any], frozen: Mapping[str, str], verdict: Mapping[str, Any] | None
) -> list[dict[str, Any]]:
    """Name the bounded typed descents behind one visible work-map node."""

    commission_message = commission.get("message", {})
    links = [
        {
            "role": "commission",
            "kind": "fabric-message",
            "reference": commission_message.get("message_id"),
        },
        {
            "role": "commission-body",
            "kind": "atlas-custody",
            "reference": commission_message.get("body_handle"),
        },
        {
            "role": "candidate-commit",
            "kind": "git-commit",
            "reference": frozen.get("frozen_commit"),
        },
        {
            "role": "candidate-tree",
            "kind": "git-tree",
            "reference": frozen.get("frozen_tree"),
        },
        {
            "role": "candidate-diff",
            "kind": "content-digest",
            "reference": frozen.get("frozen_diff_sha256"),
        },
    ]
    if verdict is not None:
        links.extend([
            {
                "role": "verdict",
                "kind": "fabric-message",
                "reference": verdict.get("message_id"),
            },
            {
                "role": "verdict-body",
                "kind": "atlas-custody",
                "reference": verdict.get("body_handle"),
            },
        ])
    return [link for link in links if link.get("reference")]


def _git(
    root: Path, arguments: list[str], *, binary: bool = False
) -> subprocess.CompletedProcess[Any]:
    return subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=False,
        capture_output=True,
        text=not binary,
    )


def verify_git_candidate(root: Path, frozen: Mapping[str, str]) -> dict[str, Any]:
    """Verify the exact immutable candidate roots named by a commission."""

    commit = str(frozen["frozen_commit"])
    expected_tree = str(frozen["frozen_tree"])
    expected_diff = str(frozen["frozen_diff_sha256"])
    reasons: list[str] = []

    exists = _git(root, ["cat-file", "-e", f"{commit}^{{commit}}"])
    if exists.returncode != 0:
        return {
            "status": "INVALID",
            "reasons": ["frozen commit is absent from Git custody"],
            "actual_tree": None,
            "actual_diff_sha256": None,
            "relation_to_head": "MISSING",
        }

    tree_result = _git(root, ["rev-parse", f"{commit}^{{tree}}"])
    actual_tree = tree_result.stdout.strip() if tree_result.returncode == 0 else None
    if actual_tree != expected_tree:
        reasons.append("frozen tree disagrees with the candidate commit")

    diff_result = _git(root, ["show", "--format=", "--binary", commit], binary=True)
    actual_diff = (
        "sha256:" + hashlib.sha256(diff_result.stdout).hexdigest()
        if diff_result.returncode == 0
        else None
    )
    if actual_diff != expected_diff:
        reasons.append("frozen diff digest disagrees with the candidate commit")

    head_result = _git(root, ["rev-parse", "HEAD"])
    head = head_result.stdout.strip() if head_result.returncode == 0 else None
    if head == commit:
        relation = "HEAD"
    else:
        ancestor = _git(root, ["merge-base", "--is-ancestor", commit, "HEAD"])
        relation = "ANCESTOR" if ancestor.returncode == 0 else "DIVERGED"
        if relation == "DIVERGED":
            reasons.append("frozen commit is not an ancestor of current HEAD")

    return {
        "status": "VALID" if not reasons else "INVALID",
        "reasons": reasons,
        "actual_tree": actual_tree,
        "actual_diff_sha256": actual_diff,
        "relation_to_head": relation,
    }


def _message_rows(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    context = state["active_context"]
    rows: list[dict[str, Any]] = []
    for materialized in state.get("messages", {}).values():
        if (
            materialized.get("assumption") != context.get("assumption")
            or materialized.get("fibre") != context.get("fibre")
        ):
            continue
        message = materialized.get("message", {})
        rows.append({
            "message": message,
            "status": str(materialized.get("status", "unknown")),
        })
    return rows


def _exact_commission(row: Mapping[str, Any]) -> bool:
    message = row.get("message", {})
    roots = message.get("dependency_roots", {})
    return (
        str(message.get("message_type", "")).endswith("commission")
        and all(str(roots.get(key, "")) for key in _FROZEN_KEYS)
    )


def _resolve_verdict(
    row: Mapping[str, Any],
    *,
    frozen: Mapping[str, str],
    body_resolver: Callable[[str], str],
    route_valid: bool = True,
    route_errors: tuple[str, ...] = (),
    projected_decision: str | None = None,
    legacy_compatibility_verified: bool = False,
    delivery_evidence_mode: str = "strict",
) -> dict[str, Any]:
    message = row["message"]
    status = str(row["status"])
    base = {
        "message_id": message.get("message_id"),
        "message_type": message.get("message_type"),
        "cursor": message.get("cursor"),
        "status": status,
        "delivery": _delivery_projection(row, evidence_mode=delivery_evidence_mode),
        "body_handle": message.get("body_handle"),
        "decision": None,
        "evidence_status": "UNREAD",
        "binding_mode": None,
        "errors": [],
    }
    if status != "delivered" or not base["delivery"]["delivered"]:
        return base

    roots = message.get("dependency_roots", {})
    errors = list(route_errors)
    if not route_valid and not errors:
        errors.append("verdict route is not the reverse of its commission")
    errors.extend(
        f"verdict {key} disagrees with its commission"
        for key in _FROZEN_KEYS
        if str(roots.get(key, "")) != str(frozen[key])
    )

    projected = str(projected_decision or "").upper()
    declared = str(roots.get("review_decision", "")).upper()
    if projected in {"ACCEPT", "REJECT", "CONTEST"} and declared == projected:
        # The decision lives in the typed Fabric envelope and the delivered acknowledgement proves
        # the reviewer reconstructed its body.  The body is explanation, not a second decision
        # authority, so the O(delta) frontier never has to reopen it to decide currentness.
        return {
            **base,
            "decision": projected,
            "evidence_status": "VALID" if not errors else "INVALID",
            "binding_mode": "TYPED-DECISION+DEPENDENCY-ROOTS+DELIVERY-PROOF",
            "errors": errors,
        }

    if not legacy_compatibility_verified:
        if projected in {"ACCEPT", "REJECT", "CONTEST"}:
            errors.append("projected decision is absent from the typed verdict envelope")
        errors.append(
            "decisionless verdict is not verified legacy compatibility evidence"
        )
        return {
            **base,
            "evidence_status": "INVALID",
            "binding_mode": "UNVERIFIED-LEGACY-COMPATIBILITY",
            "errors": errors,
        }

    try:
        body = json.loads(body_resolver(str(message["body_handle"])))
    except Exception as exc:  # noqa: BLE001 - malformed review evidence stays loud
        errors.append(f"verdict body is not reconstructible JSON: {type(exc).__name__}: {exc}")
        body = {}

    decision = str(body.get("verdict", "")).upper()
    if decision not in {"ACCEPT", "REJECT", "CONTEST"}:
        errors.append("verdict body has no ACCEPT, REJECT or CONTEST decision")
        decision = None
    if projected in {"ACCEPT", "REJECT", "CONTEST"} and decision != projected:
        errors.append("legacy verdict body disagrees with its exact projected decision")
    body_frozen = body.get("frozen")
    body_key = {
        "frozen_commit": "commit",
        "frozen_tree": "tree",
        "frozen_diff_sha256": "diff_sha256",
    }
    if isinstance(body_frozen, Mapping):
        binding_mode = "BODY-FROZEN+DEPENDENCY-ROOTS"
        for key, nested in body_key.items():
            if str(body_frozen.get(nested, "")) != str(frozen[key]):
                errors.append(f"verdict body {nested} disagrees with its commission")
    else:
        # Historical exact-review verdicts put the immutable roots on the Fabric message and
        # named only the commit in their exact-scope body.  Preserve that bounded compatibility
        # without weakening new verdicts: all three dependency roots must already match above,
        # and the body must itself name the frozen commit it judges.
        binding_mode = "DEPENDENCY-ROOTS+EXACT-COMMIT-SCOPE"
        if str(frozen["frozen_commit"]) not in str(body.get("scope", "")):
            errors.append("legacy verdict scope does not name its frozen commit")

    return {
        **base,
        "decision": decision,
        "evidence_status": "VALID" if not errors else "INVALID",
        "binding_mode": binding_mode,
        "errors": errors,
    }


def _seat_projection(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for seat_id, occupancy in sorted((state.get("seat_occupancy") or {}).items()):
        join = occupancy.get("join") or {}
        binding = occupancy.get("binding") or {}
        rows.append({
            "seat_id": seat_id,
            "state": occupancy.get("state"),
            "routing_authority": bool(occupancy.get("routing_authority")),
            "function": join.get("function"),
            "provider_session_ref": binding.get("provider_session_ref") or join.get("holder_ref"),
            "join_event_id": occupancy.get("join_event_id"),
            "binding_event_id": occupancy.get("binding_event_id"),
            "defects": list(occupancy.get("defects") or []),
        })
    return rows


def _lease_projection(
    state: Mapping[str, Any], *, observed_at: datetime
) -> list[dict[str, Any]]:
    expected_observation = _utc_text(observed_at)
    frontier_observation = state.get("region_lease_authority_observed_at")
    carried_occupancies = state.get("seat_occupancy")
    if not isinstance(carried_occupancies, Mapping):
        carried_occupancies = None
    rows: list[dict[str, Any]] = []
    for lease_id, lease in sorted(state.get("region_leases", {}).items()):
        checkout = lease.get("checkout") or {}
        expires_at = checkout.get("expires_at")
        authority = lease.get("effective_authority") or {}
        effective_state = lease.get("effective_state")
        write_authority = lease.get("write_authority")
        derived = effective_region_lease_projection(
            lease,
            seat_occupancies=carried_occupancies,
            observed_at=expected_observation,
        )
        exact_authority = (
            frontier_observation == expected_observation
            and lease.get("authority_observed_at") == expected_observation
            and authority == derived["effective_authority"]
            and effective_state == derived["effective_state"]
            and write_authority is derived["write_authority"]
            and lease.get("lineage_state") == derived["lineage_state"]
            and effective_state in {"ACTIVE", "CLOSED", "EXPIRED", "DISPLACED", "UNKNOWN"}
            and write_authority is (effective_state == "ACTIVE")
        )
        if not exact_authority:
            effective_state = "UNKNOWN"
            write_authority = False
        rows.append({
            "lease_id": lease_id,
            "seat_id": checkout.get("seat_id"),
            "holder_ref": checkout.get("holder_ref"),
            "function": checkout.get("function"),
            "regions": list(checkout.get("regions") or []),
            "base_git_head": checkout.get("base_git_head"),
            "expires_at": expires_at,
            "effective_state": effective_state,
            "write_authority": write_authority,
            "authority_observed_at": expected_observation,
            "lineage_state": derived["lineage_state"],
        })
    return rows


def project_development_work_map_from_state(
    state: Mapping[str, Any],
    *,
    repo_root: Path,
    body_resolver: Callable[[str], str],
    candidate_verifier: Callable[[Path, Mapping[str, str]], Mapping[str, Any]] = verify_git_candidate,
    candidate_cap: int = 6,
    observed_at: datetime | None = None,
) -> dict[str, Any]:
    """Compatibility constructor for tests and old provider projections.

    Production wake uses :func:`project_development_work_map_from_frontier`; this path still makes
    the same authority decisions but necessarily scans the supplied historical snapshot.
    """

    if candidate_cap < 1:
        raise ValueError("candidate_cap must be at least one")
    when = observed_at or datetime.now(timezone.utc)
    observed_at_text = _utc_text(when)
    messages = _message_rows(state)
    commissions = sorted(
        (row for row in messages if _exact_commission(row)),
        key=lambda row: int(row["message"].get("cursor", 0)),
    )
    frontier_rows: list[dict[str, Any]] = []
    for commission in commissions:
        message = commission["message"]
        candidates = sorted(
            (
                row for row in messages
                if row["message"].get("dependency_roots", {}).get("commission")
                == message.get("message_id")
                and "verdict" in str(row["message"].get("message_type", ""))
            ),
            key=lambda row: int(row["message"].get("cursor", 0)),
        )
        verdict_row = candidates[-1] if candidates else None
        route_errors: list[str] = []
        if verdict_row is not None:
            verdict_message = verdict_row["message"]
            if verdict_message.get("sender_seat_id") != message.get("recipient_seat_id"):
                route_errors.append("verdict sender is not the commissioned reviewer")
            if verdict_message.get("recipient_seat_id") != message.get("sender_seat_id"):
                route_errors.append("verdict recipient is not the commissioning builder")
            if verdict_message.get("sender_seat_id") == message.get("sender_seat_id"):
                route_errors.append("builder cannot review its own publication")
            if int(verdict_message.get("cursor", 0)) <= int(message.get("cursor", 0)):
                route_errors.append("verdict does not follow its commission")
        frontier_rows.append({
            "commission": commission,
            "verdict": verdict_row,
            "review_decision": (
                None
                if verdict_row is None
                else (
                    verdict_row["message"].get("dependency_roots", {}).get("review_decision")
                    or LEGACY_UNTYPED_REVIEW_DECISIONS.get(
                        verdict_row["message"].get("message_id")
                    )
                )
            ),
            "route_valid": not route_errors,
            "route_errors": route_errors,
            "projection_terminal": False,
            "legacy_compatibility_verified": bool(
                verdict_row is not None
                and verdict_row["message"].get("message_id")
                in LEGACY_UNTYPED_REVIEW_VERDICT_IDS
                and not verdict_row["message"]
                .get("dependency_roots", {})
                .get("review_decision")
            ),
        })
    frontier = {
        "status": "CURRENT",
        "active_context": state["active_context"],
        "caused_by_event_cursor": int(state.get("event_count", 0)),
        "head_event_id": state.get("head_event_id"),
        "head_record_digest": state.get("head_record_digest"),
        "rows": frontier_rows,
        "projection_open_count": len(frontier_rows),
        "projection_terminal_count": 0,
        "omitted_projection_terminal_count": 0,
        "seat_occupancy": state.get("seat_occupancy", {}),
        "region_leases": {
            lease_id: effective_region_lease_projection(
                lease,
                seat_occupancies=state.get("seat_occupancy", {}),
                observed_at=observed_at_text,
            )
            for lease_id, lease in state.get("region_leases", {}).items()
        },
        "region_lease_authority_observed_at": observed_at_text,
        "read_metrics": {
            "rows_loaded": len(frontier_rows),
            "history_replayed": True,
            "provider_snapshot_materialized": True,
        },
    }
    return project_development_work_map_from_frontier(
        frontier,
        repo_root=repo_root,
        body_resolver=body_resolver,
        candidate_verifier=candidate_verifier,
        candidate_cap=candidate_cap,
        observed_at=when,
        delivery_evidence_mode="legacy-full-state",
    )


def project_development_work_map_from_frontier(
    frontier: Mapping[str, Any],
    *,
    repo_root: Path,
    body_resolver: Callable[[str], str],
    candidate_verifier: Callable[[Path, Mapping[str, str]], Mapping[str, Any]] = verify_git_candidate,
    candidate_cap: int = 6,
    observed_at: datetime | None = None,
    delivery_evidence_mode: str = "strict",
) -> dict[str, Any]:
    """Verify the compact live frontier and exact visible Git candidates."""

    if candidate_cap < 1:
        raise ValueError("candidate_cap must be at least one")
    if delivery_evidence_mode not in {"strict", "legacy-full-state"}:
        raise ValueError(f"unknown delivery evidence mode: {delivery_evidence_mode}")
    if frontier.get("status", "CURRENT") != "CURRENT":
        raise ValueError("development work map requires a CURRENT Atlas frontier")
    context = frontier.get("active_context") or {}
    if not context.get("assumption") or not context.get("fibre"):
        raise ValueError("development work map requires an exact assumption fibre")
    cursor = frontier.get("caused_by_event_cursor")
    if isinstance(cursor, bool) or not isinstance(cursor, int) or cursor < 0:
        raise ValueError("development work map requires a valid Atlas event cursor")
    if cursor and not frontier.get("head_event_id"):
        raise ValueError("development work map requires the exact Atlas head event")
    if cursor and not frontier.get("head_record_digest"):
        raise ValueError("development work map requires the exact Atlas head record digest")
    all_work: list[dict[str, Any]] = []
    for projected in frontier.get("rows", []):
        commission = projected["commission"]
        message = commission["message"]
        roots = message["dependency_roots"]
        frozen = {key: str(roots[key]) for key in _FROZEN_KEYS}
        verdict_row = projected.get("verdict")
        verdict = (
            _resolve_verdict(
                verdict_row,
                frozen=frozen,
                body_resolver=body_resolver,
                route_valid=bool(projected.get("route_valid", False)),
                route_errors=tuple(projected.get("route_errors") or ()),
                projected_decision=projected.get("review_decision"),
                legacy_compatibility_verified=bool(
                    projected.get("legacy_compatibility_verified", False)
                ),
                delivery_evidence_mode=delivery_evidence_mode,
            )
            if verdict_row is not None else None
        )
        candidate_evidence = dict(candidate_verifier(repo_root, frozen))
        commission_delivery = _delivery_projection(
            commission, evidence_mode=delivery_evidence_mode
        )
        if candidate_evidence.get("status") != "VALID":
            state_name = "INVALID-EVIDENCE"
        elif not commission_delivery["delivered"]:
            state_name = "COMMISSION-DELIVERY-UNPROVEN"
        elif verdict is None:
            state_name = "AWAITING-REVIEW"
        elif verdict["status"] != "delivered":
            state_name = "VERDICT-QUEUED"
        elif not verdict["delivery"]["delivered"]:
            state_name = "VERDICT-DELIVERY-UNPROVEN"
        elif verdict["evidence_status"] != "VALID":
            state_name = "INVALID-EVIDENCE"
        else:
            state_name = {
                "ACCEPT": "ACCEPTED",
                "REJECT": "REJECTED",
                "CONTEST": "CONTESTED",
            }[verdict["decision"]]
        terminal = state_name in {"ACCEPTED", "REJECTED", "CONTESTED"}
        commission_face = {
            "message_id": message.get("message_id"),
            "message_type": message.get("message_type"),
            "cursor": message.get("cursor"),
            "status": commission.get("status"),
            "body_handle": message.get("body_handle"),
            "dependency_roots": dict(roots),
            "builder_seat": message.get("sender_seat_id"),
            "reviewer_seat": message.get("recipient_seat_id"),
            "delivery": commission_delivery,
        }
        node = {
            "state": state_name,
            "publication_state": "CLOSED" if terminal else "PUBLISHED-PENDING-CLOSURE",
            "commission": commission_face,
            "frozen": frozen,
            "candidate_evidence": candidate_evidence,
            "verdict": verdict,
            "review_residue": {
                "count": int(projected.get("review_residue_count", 0)),
                "latest": projected.get("latest_review_residue"),
            },
            "projection_terminal": bool(projected.get("projection_terminal")),
        }
        node["source_links"] = _source_links(
            commission=commission,
            frozen=frozen,
            verdict=verdict,
        )
        node["node_handle"] = chash(node)
        all_work.append(node)

    terminal_states = {"ACCEPTED", "REJECTED", "CONTESTED"}
    open_work = [row for row in all_work if row["state"] not in terminal_states]
    closed_work = [row for row in all_work if row["state"] in terminal_states]
    selected_closed = closed_work[-candidate_cap:]
    work = sorted(
        [*open_work, *selected_closed],
        key=lambda row: int(row["commission"].get("cursor", 0)),
    )
    legacy_closed = sum(
        1 for row in closed_work if not row["projection_terminal"]
    )
    total_terminal = int(frontier.get("projection_terminal_count", 0)) + legacy_closed
    omitted_terminal = max(0, total_terminal - len(selected_closed))

    if observed_at is not None:
        when = observed_at
    else:
        carried_observation = frontier.get("region_lease_authority_observed_at")
        try:
            when = datetime.fromisoformat(str(carried_observation).replace("Z", "+00:00"))
            if when.tzinfo is None:
                raise ValueError("authority observation has no timezone")
        except (TypeError, ValueError):
            when = datetime.now(timezone.utc)
    observed_at_text = _utc_text(when)
    compact_state = {
        "seat_occupancy": frontier.get("seat_occupancy"),
        "region_leases": frontier.get("region_leases", {}),
        "region_lease_authority_observed_at": frontier.get(
            "region_lease_authority_observed_at"
        ),
    }
    leases = _lease_projection(compact_state, observed_at=when)
    active_leases = [row for row in leases if row["write_authority"]]
    read_metrics = dict(frontier.get("read_metrics") or {})
    read_metrics.update({
        "candidate_verifications": len(all_work),
        "legacy_untyped_closures": legacy_closed,
        "review_residue_count": sum(
            int(row["review_residue"]["count"]) for row in all_work
        ),
        "visible_rows": len(work),
    })
    source_coordinate = {
        "schema_version": "laplace.development-work-map-source/1",
        "assumption": context.get("assumption"),
        "fibre": context.get("fibre"),
        "event_cursor": cursor,
        "head_event_id": frontier.get("head_event_id"),
        "head_record_digest": frontier.get("head_record_digest"),
    }
    source_handle = chash(source_coordinate)
    omission_residual = {
        "status": "PRESENT" if omitted_terminal else "NONE",
        "omitted_open_candidates": 0,
        "omitted_terminal_candidates": omitted_terminal,
        "reason": (
            None
            if not omitted_terminal
            else "terminal history is a bounded tail; open work is never omitted"
        ),
        "continuation": (
            None
            if not omitted_terminal
            else {
                "action": "reconstruct with a larger explicit candidate_cap",
                "current_candidate_cap": candidate_cap,
            }
        ),
    }
    payload = {
        "schema_version": WORK_MAP_SCHEMA,
        "status": "CURRENT",
        "active_context": {
            "assumption": context.get("assumption"),
            "fibre": context.get("fibre"),
        },
        "caused_by_event_cursor": cursor,
        "head_event_id": frontier.get("head_event_id"),
        "head_record_digest": frontier.get("head_record_digest"),
        "observed_at": observed_at_text,
        "freshness": {
            "state": "CURRENT",
            "source_handle": source_handle,
            "coordinate": source_coordinate,
        },
        "latest_work_state": all_work[-1]["state"] if all_work else "NO-EXACT-CANDIDATE",
        "work": work,
        "open_candidate_count": len(open_work),
        "omitted_open_candidates": 0,
        "omitted_terminal_candidates": omitted_terminal,
        "omission_residual": omission_residual,
        "seat_occupancy": _seat_projection(compact_state),
        "leases": leases,
        "parallel_posture": (
            "LEASES-ACTIVE-CHECK-PATH-CONFLICTS" if active_leases else "NO-ACTIVE-WRITE-LEASES"
        ),
        "read_metrics": read_metrics,
        "fidelity_boundary": frontier.get("fidelity_boundary"),
        "proof_boundary": (
            "head-bound incremental Atlas frontier, exact visible hived message evidence, "
            "and exact visible Git roots; typed reviewer decisions close only after "
            "reverse-route delivered custody proof; the terminal aggregate remains the named "
            "CR-review-frontier-terminal-aggregate-without-authoritative-root crutch"
        ),
        "read_only": True,
        "delivery_evidence_mode": delivery_evidence_mode,
    }
    return {**payload, "shown_handle": chash(payload)}


__all__ = [
    "WORK_MAP_SCHEMA",
    "project_development_work_map_from_frontier",
    "project_development_work_map_from_state",
    "verify_git_candidate",
]
