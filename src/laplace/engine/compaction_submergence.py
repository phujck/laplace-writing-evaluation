"""Content-addressed, function-specialized continuation across compaction.

The profile is not a second context store.  ``seal_precompact`` places one canonical JSON
object in Atlas's existing blob custody and returns its handle.  A cold successor must present
that handle and prove the small set of roots the function actually consumed before the wake
door enables any provider integration.

An unrelated dirty path or Atlas event is deliberately not a consumed root.  This is the first
submergence: the expensive recovery-coordinate verifier is paid while sealing, then bypassed on
an unchanged cold continuation.  Git HEAD/tree, the selected region leases, active assumption
fibre, function seat binding, and development-review root remain exact refusal boundaries.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from laplace.representation.atlas_bridge import chash

PROFILE_SCHEMA = "laplace.function-successor-profile/1"
SEAL_SCHEMA = "laplace.precompact-profile-seal/1"
COLD_SCHEMA = "laplace.cold-successor-authorization/1"
CONTINUATION_SCHEMA = "laplace.continuation-admission/1"
PROFILE_HANDLE_ENV = "LAPLACE_SUCCESSOR_PROFILE_HANDLE"
FUNCTION_ENV = "LAPLACE_FUNCTION"
GENERATION_ENV = "LAPLACE_SEAT_GENERATION"
CEREMONY_SUSPENSION_PATH = Path(
    "/home/phujck/SystemCheckpoints/2026-08-28/"
    "DEVELOPMENT-AUTHORITY-CEREMONY-SUSPENSION.json"
)
CEREMONY_SUSPENSION_SHA256 = (
    "sha256:ac7e3be888f2f31d90d01cb4e466da09a36940daf9f548f5737d8521ae64df7f"
)
CEREMONY_SUSPENSION_BYTES = 5281
CEREMONY_SUSPENSION_SCHEMA = "laplace.development-authority-ceremony-suspension/1"
GOAL_CONTEXT_SCHEMA = "laplace.three-seat-goals-and-context/1"
HIERARCHY_DERIVATION_PATH = Path(
    "/home/phujck/SystemCheckpoints/2026-08-28/"
    "HIERARCHY-PHASE-CADENCE-DERIVATION.json"
)
HIERARCHY_DERIVATION_HANDLE = (
    "sha256:818e36cd1127a6f57c47202a4f5feb1dcc551b527e24cf946e469ba2e6575f5a"
)
HIERARCHY_DERIVATION_BYTES = 6704
REGULARIZATION_RULING_PATH = Path(
    "/home/phujck/SystemCheckpoints/2026-08-28/"
    "POST-PUBLICATION-SEMANTIC-LIFECYCLE-REGULARIZATION-RULING.json"
)
REGULARIZATION_RULING_HANDLE = (
    "sha256:f4402722879368e9448282b3045352677945daaf86c1fa77d2752fcf2cc5de29"
)
REGULARIZATION_RULING_BYTES = 4982
REGULARIZATION_DESIGN_PATH = Path(
    "/home/phujck/SystemCheckpoints/2026-08-28/"
    "SUPEREGO-DESIGN-SEMANTIC-LIFECYCLE-REGULARIZER.md"
)
REGULARIZATION_DESIGN_HANDLE = (
    "sha256:defd086c388e347c7ecfc081f8fa714d26cc11ad56e03c1f461a11634cec8f7f"
)
REGULARIZATION_DESIGN_BYTES = 13998

# Exact reconstructed roots of the integrated commission.  They are source coordinates, not a
# copied work map, and remain common across every function profile.
INTEGRATED_ROOTS: dict[str, str] = {
    "WO-20260827-typed-compaction-continuation": (
        "sha256:2056357a36f5e3c26659623c8535ed63983793db4fece1f6ec7d96afa466befa"
    ),
    "WO-20260827-function-specialized-reconstruction-context": (
        "sha256:9bb8b8e508efce8f73b9ef5a08d738c4daaebd19992bf3fa7181f6acdc5ca8eb"
    ),
    "WO-20260827-mutable-development-graph-organ-submergence": (
        "sha256:0ed9abf98e8eff5e6fda764d79b33116de2c09831417a9dc68e06d823b55c13d"
    ),
    "WO-20260827-attention-accumulator-and-polling-retirement": (
        "sha256:7248093299714172daaace1efd2267c769f5231a80d34482f35b825bd5052573"
    ),
    "WO-20260827-crutch-retirement-account": (
        "sha256:867ca528b66d67ee6af4b435539b3abd4501aa05d389b0eac030d47a4c9f3029"
    ),
    "WO-20260827-store-growth-budget-retention-and-reclaim": (
        "sha256:c227c6011216d8574d5359429c75ad2d3c82e6f288fe1c26e2f552d5ac7eac52"
    ),
    "WO-20260827-synthetics-inertial-phase": (
        "sha256:38394c43c684dcb19e203b078ae319cca03ed4dedbe07cde7c13af092ed3cf47"
    ),
    "WO-20260827-hierarchical-inertia-error-evolution": (
        "sha256:3860f3b7bde9bdb6574a7185f07eca8fa0fa9300ebd3aac65a2629081e009200"
    ),
    "RUL-20260828-post-publication-semantic-lifecycle-regularization": (
        "sha256:f4402722879368e9448282b3045352677945daaf86c1fa77d2752fcf2cc5de29"
    ),
    "DESIGN-20260828-semantic-lifecycle-regularizer": REGULARIZATION_DESIGN_HANDLE,
}

_INERTIA_FIELDS = (
    "coordination_layer_count",
    "author_command_to_productive_act_ms",
    "reconstructions",
    "subprocesses",
    "tokens",
    "review_cycles",
    "uniquely_caught_faults",
)


class ContinuationRefused(RuntimeError):
    """A cold successor did not prove the exact profile it was given."""

    def __init__(self, reason: str, *, divergence: Mapping[str, Any] | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.divergence = dict(divergence or {})


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode(
        "utf-8"
    )


def load_ceremony_suspension(
    path: Path | str = CEREMONY_SUSPENSION_PATH,
) -> dict[str, Any]:
    """Load Gerard's exact suspension once; validation adds no confirmation/meta-gate."""

    source = Path(path)
    data = source.read_bytes()
    handle = "sha256:" + hashlib.sha256(data).hexdigest()
    if len(data) != CEREMONY_SUSPENSION_BYTES or handle != CEREMONY_SUSPENSION_SHA256:
        raise ContinuationRefused(
            "development-authority ceremony suspension failed exact custody validation",
            divergence={
                "path": str(source),
                "expected_bytes": CEREMONY_SUSPENSION_BYTES,
                "observed_bytes": len(data),
                "expected_handle": CEREMONY_SUSPENSION_SHA256,
                "observed_handle": handle,
            },
        )
    try:
        record = json.loads(data)
    except json.JSONDecodeError as exc:
        raise ContinuationRefused("ceremony suspension is not valid JSON") from exc
    required = {
        "author_ruling",
        "scope",
        "suspended_as_blocking_preconditions",
        "hard_stops_retained",
        "reintroduction_predicate",
    }
    if (
        not isinstance(record, dict)
        or record.get("schema_version") != CEREMONY_SUSPENSION_SCHEMA
        or record.get("status") != "ACTIVE"
        or not required.issubset(record)
    ):
        raise ContinuationRefused("ceremony suspension typed contract is incomplete or inactive")
    return {"path": str(source), "content_handle": handle, "bytes": len(data), "record": record}


def load_goal_context(
    path: Path | str,
    *,
    expected_handle: str,
    expected_bytes: int,
) -> dict[str, Any]:
    """Verify one complete semantic compilation without rewriting or paraphrasing it."""

    source = Path(path)
    data = source.read_bytes()
    handle = "sha256:" + hashlib.sha256(data).hexdigest()
    if len(data) != expected_bytes or handle != expected_handle:
        raise ContinuationRefused(
            "three-seat goal context failed exact custody validation",
            divergence={
                "path": str(source),
                "expected_bytes": expected_bytes,
                "observed_bytes": len(data),
                "expected_handle": expected_handle,
                "observed_handle": handle,
            },
        )
    try:
        record = json.loads(data)
    except json.JSONDecodeError as exc:
        raise ContinuationRefused("three-seat goal context is not valid JSON") from exc
    required_seats = {"ego", "aisthesis", "superego"}
    seats = record.get("seats") if isinstance(record, Mapping) else None
    orchestration = record.get("orchestration_account") if isinstance(record, Mapping) else None
    if (
        not isinstance(record, dict)
        or record.get("schema_version") != GOAL_CONTEXT_SCHEMA
        or record.get("status") != "ACTIVE"
        or not isinstance(record.get("common_kernel"), list)
        or not isinstance(record.get("priority_frontier"), list)
        or not isinstance(record.get("long_horizon"), list)
        or not isinstance(seats, Mapping)
        or not required_seats.issubset(seats)
        or not isinstance(orchestration, Mapping)
        or not required_seats.issubset(orchestration)
    ):
        raise ContinuationRefused("three-seat goal context typed contract is incomplete or inactive")
    return {
        "path": str(source),
        "content_handle": handle,
        "bytes": len(data),
        "body": data,
        "record": record,
    }


def consume_hierarchy_derivation(
    *,
    semantic_fold_handle: str | None,
    path: Path | str = HIERARCHY_DERIVATION_PATH,
) -> dict[str, Any]:
    """Distil the fresh hierarchy phase controller without putting its body in hot context."""

    source = Path(path)
    try:
        data = source.read_bytes()
        handle = "sha256:" + hashlib.sha256(data).hexdigest()
        if len(data) != HIERARCHY_DERIVATION_BYTES or handle != HIERARCHY_DERIVATION_HANDLE:
            raise ValueError("exact source bytes moved")
        record = json.loads(data)
        if (
            record.get("schema_version")
            != "laplace.hierarchy-phase-cadence-derivation/1"
            or record.get("status") != "FRESH-DERIVATION-FROM-QUARANTINED-SOURCE"
        ):
            raise ValueError("typed fresh-derivation contract moved")
        controller = record["phase_controller"]
        viable = record["fresh_operational_derivation"]["viable_modular_phase"]
        policy = {
            "schema_version": "laplace.hierarchy-phase-operating-policy/1",
            "source_handle": handle,
            "minimum_sufficient_hierarchy": viable["condition"],
            "measured_protective_yield": controller["add_a_layer_only_when"],
            "local_failure_fix_forward": controller["local_failure_rule"],
            "review_synthesis": controller["review_rule"],
            "irreversible_boundary_concentration": controller[
                "irreversible_boundary_rule"
            ],
            "scaffold_retirement": controller["submerge_or_retire_a_layer_when"],
            "telemetry_required": record["telemetry_required"],
            "historical_manuscript_status": record["source_qualification"][
                "historical_status"
            ],
            "hot_context": "DISTILLED-POLICY-ONLY; exact source reachable by custody handle",
            "forward_links": {
                "source": handle,
                "successor_fold": semantic_fold_handle
                or "PENDING-EXACT-S-TO-F-SUCCESSOR",
            },
        }
        policy_handle = chash(policy)
        receipt = {
            "schema_version": "laplace.hierarchy-phase-policy-consumption/1",
            "status": "CONSUMED",
            "source_handle": handle,
            "policy_handle": policy_handle,
            "affected_profile_fields": [
                "common_kernel.phase_policy_handle",
                "phase_controller",
                "measured_costs",
                "submergence",
            ],
            "forward_links": policy["forward_links"],
            "authority_effect": "none",
        }
        receipt["receipt_handle"] = chash(receipt)
        return {"status": "CONSUMED", "policy": policy, "receipt": receipt}
    except Exception as exc:  # noqa: BLE001 - missing policy is typed fog, not hidden fallback
        body = {
            "schema_version": "laplace.hierarchy-phase-policy-consumption/1",
            "status": "UNKNOWN",
            "source_handle": HIERARCHY_DERIVATION_HANDLE,
            "reason": f"{type(exc).__name__}: {exc}",
            "fog": True,
            "authority_effect": "none",
        }
        body["receipt_handle"] = chash(body)
        return {"status": "UNKNOWN", "policy": None, "receipt": body}


def consume_regularization_ruling(*, semantic_fold_handle: str | None) -> dict[str, Any]:
    """Compile Gerard's exact publication boundary into the successor profile."""

    try:
        data = REGULARIZATION_RULING_PATH.read_bytes()
        handle = "sha256:" + hashlib.sha256(data).hexdigest()
        if handle != REGULARIZATION_RULING_HANDLE or len(data) != REGULARIZATION_RULING_BYTES:
            raise ValueError("exact author-ruling bytes moved")
        record = json.loads(data)
        if (
            record.get("schema_version") != "laplace.author-development-ruling/1"
            or record.get("status") != "ACTIVE"
            or record.get("id")
            != "RUL-20260828-post-publication-semantic-lifecycle-regularization"
        ):
            raise ValueError("author-ruling contract is inactive or malformed")
        outside = record["outside_view_acceptance"]
        design = REGULARIZATION_DESIGN_PATH.read_bytes()
        design_handle = "sha256:" + hashlib.sha256(design).hexdigest()
        if (
            design_handle != REGULARIZATION_DESIGN_HANDLE
            or len(design) != REGULARIZATION_DESIGN_BYTES
        ):
            raise ValueError("exact Superego implementation design bytes moved")
        policy = {
            "schema_version": "laplace.semantic-lifecycle-regularization-policy/1",
            "source_handle": handle,
            "design_handle": design_handle,
            "priority": record["priority"],
            "publication_order": record["publication_order"],
            "outside_view": {
                "premise": outside["premise"],
                "measure": outside["measure"],
                "fix_forward": outside["success"],
                "submerge_rule": outside["submerge_rule"],
                "observability": outside["observability"],
            },
            "operating_law": {
                "source_to_fold": "exact S -> artifact-only F",
                "up_down": "one compact batch receipt plus exact DOWN index",
                "admission": "one shared operator; tools/providers require ADMITTED",
                "fabric": "restore canonical fast path after stable source and fold",
            },
            "forward_links": {
                "source": handle,
                "successor_fold": semantic_fold_handle
                or "PENDING-EXACT-S-TO-F-SUCCESSOR",
            },
            "hot_context": "DISTILLED-POLICY-ONLY",
        }
        policy["policy_handle"] = chash(policy)
        receipt = {
            "schema_version": "laplace.semantic-lifecycle-ruling-consumption/1",
            "status": "CONSUMED",
            "source_handle": handle,
            "design_handle": design_handle,
            "policy_handle": policy["policy_handle"],
            "successor_fold": policy["forward_links"]["successor_fold"],
            "affected_profile_fields": [
                "common_kernel.regularization_policy_handle",
                "shared_semantic_memory",
                "measured_costs",
                "submergence",
            ],
            "authority_effect": "none",
        }
        receipt["receipt_handle"] = chash(receipt)
        return {"status": "CONSUMED", "policy": policy, "receipt": receipt}
    except Exception as exc:  # noqa: BLE001 - exact missing source is explicit fog
        body = {
            "schema_version": "laplace.semantic-lifecycle-ruling-consumption/1",
            "status": "UNKNOWN",
            "source_handle": REGULARIZATION_RULING_HANDLE,
            "reason": f"{type(exc).__name__}: {exc}",
            "fog": True,
            "authority_effect": "none",
        }
        body["receipt_handle"] = chash(body)
        return {"status": "UNKNOWN", "policy": None, "receipt": body}


def admit_continuation(
    *,
    function: str,
    seat_id: str,
    generation: str | None,
    goal_digest: str,
    profile_handle: str | None,
    expected_profile_handle: str | None,
    semantic_health: Mapping[str, Any],
    typed_descents: Sequence[Mapping[str, Any]],
    fog: Sequence[Mapping[str, Any]],
    watcher_state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the one content-addressed continuation decision consumed by every adapter."""

    reasons: list[str] = []
    status = "ADMITTED"
    if not profile_handle or profile_handle != expected_profile_handle:
        status = "REFUSED"
        reasons.append("PROFILE-MOVED-OR-MISSING")
    if (semantic_health.get("side_ref_fold") or {}).get("status", "UNKNOWN") != "CURRENT":
        status = "UNKNOWN" if status != "REFUSED" else status
        reasons.append("SEMANTIC-S-TO-F-NOT-CURRENT")
    if fog:
        status = "FOG" if status == "ADMITTED" else status
        reasons.append("TYPED-DESCENT-FOG")
    complete = [
        row for row in typed_descents
        if row.get("content_status") == "COMPLETE" and row.get("content_handle")
    ]
    if not complete:
        status = "FOG" if status == "ADMITTED" else status
        reasons.append("NO-COMPLETE-TYPED-CONTEXT")
    telemetry_dark = [
        row for row in typed_descents
        if str((row.get("descent_telemetry") or {}).get("status", "")).startswith(
            "UNAVAILABLE"
        )
    ]
    if telemetry_dark:
        status = "UNKNOWN" if status != "REFUSED" else status
        reasons.append("DESCENT-TELEMETRY-UNAVAILABLE")
    body = {
        "schema_version": CONTINUATION_SCHEMA,
        "status": status,
        "function": function,
        "seat_id": seat_id,
        "generation": generation,
        "goal_digest": goal_digest,
        "profile_handle": profile_handle,
        "semantic_fold_handle": (semantic_health.get("side_ref_fold") or {}).get(
            "manifest_handle"
        ),
        "semantic_fold_receipt_handle": (semantic_health.get("up_down") or {}).get(
            "receipt_handle"
        ),
        "semantic_register_generation": (semantic_health.get("up_down") or {}).get(
            "register_generation"
        ),
        "semantic_source": semantic_health.get("current_source"),
        "selected": [
            {
                "kind": row.get("kind"),
                "reference": row.get("reference"),
                "content_status": row.get("content_status"),
                "content_handle": row.get("content_handle"),
                "current_root": row.get("current_root"),
            }
            for row in typed_descents
        ],
        "fog": [dict(row) for row in fog],
        "watcher_state": dict(watcher_state or {"status": "NOT-AN-ATTENTION-TURN"}),
        "reasons": reasons,
        "substantive_work_allowed": status == "ADMITTED",
        "human_conversation_allowed": True,
        "authority_effect": "none",
    }
    body["decision_handle"] = chash(body)
    return body


def _git_coordinate(repo_root: Path) -> dict[str, str]:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD", "HEAD^{tree}"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    values = result.stdout.splitlines()
    if len(values) != 2:
        raise ContinuationRefused("git did not return an exact HEAD/tree coordinate")
    return {"head": values[0], "tree": values[1]}


def _consumed_regions(lease_rows: Mapping[str, Any]) -> tuple[str, ...]:
    regions: list[str] = []
    for row in lease_rows.values():
        if not isinstance(row, Mapping):
            continue
        face = _lease_face(row)
        raw = face.get("regions")
        if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
            regions.extend(str(item) for item in raw)
    return tuple(sorted(set(regions)))


def _path_roots(repo_root: Path, lease_rows: Mapping[str, Any]) -> dict[str, Any]:
    """Hash only selected lease paths; unrelated dirt never becomes false currentness."""

    root = repo_root.resolve()
    result: dict[str, Any] = {}
    for region in _consumed_regions(lease_rows):
        candidate = (root / region).resolve()
        try:
            relative = candidate.relative_to(root).as_posix()
        except ValueError as exc:
            raise ContinuationRefused(
                "selected lease contains a path outside the repository",
                divergence={"region": region},
            ) from exc
        if not candidate.exists() and not candidate.is_symlink():
            result[relative] = {"kind": "missing", "content_handle": None}
        elif candidate.is_symlink():
            target = os.readlink(candidate)
            result[relative] = {
                "kind": "symlink",
                "content_handle": "sha256:" + hashlib.sha256(target.encode()).hexdigest(),
            }
        elif candidate.is_file():
            result[relative] = {
                "kind": "file",
                "content_handle": "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest(),
            }
        elif candidate.is_dir():
            entries = [
                {
                    "path": child.relative_to(root).as_posix(),
                    "content_handle": "sha256:" + hashlib.sha256(child.read_bytes()).hexdigest(),
                }
                for child in sorted(path for path in candidate.rglob("*") if path.is_file())
            ]
            result[relative] = {"kind": "directory", "content_handle": chash(entries)}
        else:
            raise ContinuationRefused(
                "selected lease path has an unsupported filesystem kind",
                divergence={"region": relative},
            )
    return result


def _effective_authority(epoch: Mapping[str, Any]) -> Mapping[str, Any]:
    if epoch.get("status") != "CURRENT":
        raise ContinuationRefused(
            "Atlas authority checkpoint is not CURRENT",
            divergence={"authority_status": epoch.get("status")},
        )
    checkpoint = epoch.get("effective_checkpoint") or epoch.get("checkpoint")
    if not isinstance(checkpoint, Mapping) or not isinstance(checkpoint.get("authority"), Mapping):
        raise ContinuationRefused("Atlas authority checkpoint omits its exact authority projection")
    return checkpoint["authority"]


def _lease_face(row: Mapping[str, Any]) -> Mapping[str, Any]:
    checkout = row.get("checkout")
    if isinstance(checkout, Mapping):
        return checkout
    return row


def _function_roots(
    authority: Mapping[str, Any],
    *,
    function: str,
    seat_id: str,
    lease_ids: Sequence[str],
) -> dict[str, Any]:
    leases = authority.get("region_leases")
    if not isinstance(leases, Mapping):
        raise ContinuationRefused("Atlas authority checkpoint omits region leases")
    selected: dict[str, Any] = {}
    for lease_id in sorted(set(lease_ids)):
        row = leases.get(lease_id)
        if not isinstance(row, Mapping):
            raise ContinuationRefused(
                "selected region lease is absent",
                divergence={"lease_id": lease_id},
            )
        face = _lease_face(row)
        if face.get("function") != function:
            raise ContinuationRefused(
                "selected region lease belongs to another function",
                divergence={
                    "lease_id": lease_id,
                    "expected_function": function,
                    "observed_function": face.get("function"),
                },
            )
        selected[lease_id] = dict(row)

    occupancy = authority.get("seat_occupancy")
    seat_face = occupancy.get(seat_id) if isinstance(occupancy, Mapping) else None
    recipient_mail = authority.get("recipient_mail")
    mail_face = recipient_mail.get(seat_id) if isinstance(recipient_mail, Mapping) else None
    roots = {
        "active_context": chash(authority.get("active_context")),
        "development_review": authority.get("development_review_root"),
        "function_seat": None if seat_face is None else chash(seat_face),
        "function_mail": chash(mail_face),
        "selected_leases": chash(selected),
    }
    return {"values": roots, "selected_lease_rows": selected}


def _recent_outcomes(work_map: Mapping[str, Any], *, cap: int = 8) -> list[dict[str, Any]]:
    outcomes: list[dict[str, Any]] = []
    for row in work_map.get("work") or []:
        if not isinstance(row, Mapping):
            continue
        commission = row.get("commission") or {}
        verdict = row.get("verdict") or {}
        residue = row.get("review_residue") or {}
        outcomes.append(
            {
                "state": row.get("state"),
                "publication_state": row.get("publication_state"),
                "node_handle": row.get("node_handle"),
                "commission_id": commission.get("message_id"),
                "commission_body": commission.get("body_handle"),
                "verdict_id": verdict.get("message_id"),
                "verdict_body": verdict.get("body_handle"),
                "decision": verdict.get("decision"),
                "residual_count": residue.get("count", 0),
            }
        )
    return outcomes[-cap:]


def _residuals(
    recovery: Mapping[str, Any], work_map: Mapping[str, Any], extra: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    residuals = [dict(item) for item in extra]
    if recovery.get("custody_allowed") is not True:
        residuals.append(
            {
                "kind": "recovery-coordinate",
                "status": recovery.get("coordinate_state", recovery.get("status")),
                "system_state": recovery.get("system_state"),
                "effect": "publication/custody remains refused; local reversible work may continue",
            }
        )
    omission = work_map.get("omission_residual")
    if isinstance(omission, Mapping) and omission.get("status") not in {None, "NONE"}:
        residuals.append({"kind": "development-work-map-omission", **dict(omission)})
    return residuals


def compile_profile(
    *,
    repo_root: Path | str,
    function: str,
    seat_id: str,
    generation: str,
    lease_ids: Sequence[str],
    authority_epoch: Mapping[str, Any],
    recovery_coordinate: Mapping[str, Any],
    work_map: Mapping[str, Any],
    inertia: Mapping[str, int | float],
    extra_obligations: Sequence[str] = (),
    extra_residuals: Sequence[Mapping[str, Any]] = (),
    source_collection_ms: float = 0.0,
    ceremony_suspension: Mapping[str, Any] | None = None,
    goal_context: Mapping[str, Any] | None = None,
    semantic_health: Mapping[str, Any] | None = None,
    compaction_boundary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compile one minimal, immutable profile from already-observed canonical faces."""

    function = function.strip().lower()
    if function not in {"ego", "sensorium", "superego"}:
        raise ContinuationRefused(
            "function profile must be ego, sensorium, or superego; generic provider fallback refused"
        )
    if not seat_id.strip() or not generation.strip():
        raise ContinuationRefused("function profile requires exact seat and generation")
    missing_metrics = sorted(set(_INERTIA_FIELDS) - set(inertia))
    if missing_metrics:
        raise ContinuationRefused(
            "hierarchical-inertia budget is incomplete",
            divergence={"missing_metrics": missing_metrics},
        )

    authority = _effective_authority(authority_epoch)
    function_roots = _function_roots(
        authority,
        function=function,
        seat_id=seat_id,
        lease_ids=lease_ids,
    )
    git = _git_coordinate(Path(repo_root).resolve())
    consumed_paths = _path_roots(
        Path(repo_root).resolve(), function_roots["selected_lease_rows"]
    )
    obligations = [
        {"id": key, "content_handle": value} for key, value in sorted(INTEGRATED_ROOTS.items())
    ]
    obligations.extend(
        {"id": obligation, "content_handle": chash({"obligation": obligation})}
        for obligation in sorted(set(extra_obligations))
    )
    suspension_record = (
        ceremony_suspension.get("record")
        if isinstance(ceremony_suspension, Mapping)
        else None
    )
    goal_record = goal_context.get("record") if isinstance(goal_context, Mapping) else None
    if semantic_health is None:
        from laplace.representation.embedding_health import read_health

        semantic_health = read_health(Path(repo_root).resolve())
    phase = consume_hierarchy_derivation(
        semantic_fold_handle=(semantic_health.get("side_ref_fold") or {}).get("manifest_handle")
    )
    regularization = consume_regularization_ruling(
        semantic_fold_handle=(semantic_health.get("side_ref_fold") or {}).get("manifest_handle")
    )
    goal_key = "aisthesis" if function == "sensorium" else function
    if isinstance(goal_record, Mapping):
        seats = goal_record.get("seats")
        orchestration = goal_record.get("orchestration_account")
        if not isinstance(seats, Mapping) or not isinstance(seats.get(goal_key), Mapping):
            raise ContinuationRefused(
                "three-seat goal context omits the exact function overlay",
                divergence={"function": function, "overlay": goal_key},
            )
        if not isinstance(orchestration, Mapping) or goal_key not in orchestration:
            raise ContinuationRefused(
                "three-seat goal context omits the function orchestration account",
                divergence={"function": function, "overlay": goal_key},
            )
    return {
        "schema_version": PROFILE_SCHEMA,
        "function": function,
        "seat_id": seat_id,
        "generation": generation,
        "common_kernel": {
            "schema_version": "laplace.compaction-invariant-kernel/1",
            "reconstruction_roots": dict(sorted(INTEGRATED_ROOTS.items())),
            "continuation_law": "checkpoint -> act -> observe exact consumed-root divergence",
            "repair_law": "one smallest implicated-region fix-forward; no lifecycle restart",
            "phase_policy_handle": (phase.get("policy") or {}).get("policy_handle")
            or (phase.get("receipt") or {}).get("policy_handle"),
            "regularization_policy_handle": (
                regularization.get("policy") or {}
            ).get("policy_handle"),
        },
        "authority_ceremony_suspension": None
        if not isinstance(suspension_record, Mapping)
        else {
            "source": {
                key: ceremony_suspension[key]
                for key in ("path", "content_handle", "bytes")
            },
            "status": suspension_record["status"],
            "exact_instruction": suspension_record["author_ruling"],
            "interpreted_scope": {
                "function": function,
                "lane": (suspension_record.get("active_lanes") or {}).get(function),
                "paths": _consumed_regions(function_roots["selected_lease_rows"]),
                "published_base": (suspension_record.get("scope") or {}).get(
                    "published_base"
                ),
            },
            "procedural_gates_bypassed": list(
                suspension_record["suspended_as_blocking_preconditions"]
            ),
            "retained_hard_stops": list(suspension_record["hard_stops_retained"]),
            "reintroduction_default": (
                suspension_record["reintroduction_predicate"]["default_if_unproven"]
            ),
            "reintroduction_earliest_boundary": (
                suspension_record["reintroduction_predicate"]["earliest_boundary"]
            ),
            "mode": "RECORD-ONLY; no meta-gate",
        },
        "goal_context": None
        if not isinstance(goal_record, Mapping)
        else {
            "source": {
                key: goal_context[key]
                for key in ("path", "content_handle", "bytes")
            },
            "semantic_audit": goal_record["semantic_audit"],
            "priority_frontier": goal_record["priority_frontier"],
            "common_kernel": goal_record["common_kernel"],
            "seat_overlay": goal_record["seats"][goal_key],
            "long_horizon": goal_record["long_horizon"],
            "orchestration_account": goal_record["orchestration_account"][goal_key],
        },
        "shared_semantic_memory": {
            "schema_version": semantic_health.get("schema_version"),
            "status": (semantic_health.get("side_ref_fold") or {}).get("status", "UNKNOWN"),
            "shared": semantic_health.get("shared"),
            "health_handle": (semantic_health.get("side_ref_fold") or {}).get("manifest_handle"),
            "coverage_handle": (semantic_health.get("side_ref_fold") or {}).get("coverage_handle"),
            "semantic_horizon": (semantic_health.get("side_ref_fold") or {}).get("semantic_horizon"),
            "semantic_fold_receipt_handle": (
                semantic_health.get("up_down") or {}
            ).get("receipt_handle"),
            "semantic_register_generation": (
                semantic_health.get("up_down") or {}
            ).get("register_generation"),
            "last_wake": (semantic_health.get("consumption") or {}).get("last_wake"),
            "last_descent": (semantic_health.get("consumption") or {}).get("last_descent"),
            "moved_effect": "semantic claims UNKNOWN; unrelated reversible work remains enabled",
        },
        "phase_controller": phase,
        "regularization_policy": regularization,
        "compaction_boundary": None
        if compaction_boundary is None else dict(compaction_boundary),
        "current_frontier": {
            "git": git,
            "consumed_paths": consumed_paths,
            "authority_consumed_roots": function_roots["values"],
            "recovery_coordinate": dict(recovery_coordinate),
            "development_work_map_source": {
                key: work_map.get(key)
                for key in (
                    "schema_version",
                    "status",
                    "active_context",
                    "freshness",
                    "head_event_id",
                    "head_record_digest",
                )
            },
        },
        "exact_obligations": obligations,
        "residuals": _residuals(recovery_coordinate, work_map, extra_residuals),
        "leases": function_roots["selected_lease_rows"],
        "recent_outcomes": _recent_outcomes(work_map),
        "measured_costs": {
            **{key: inertia[key] for key in _INERTIA_FIELDS},
            "source_collection_ms": round(float(source_collection_ms), 3),
        },
        "submergence": {
            "retired_live_scaffold": "postcompact-recovery-coordinate-revalidation",
            "bypass_predicate": "profile-consumed Git and Atlas roots are unchanged",
            "history_preserved_by": "exact recovery projection in this Atlas custody blob",
            "independent_threat_model": None,
            "measured_positive_yield": "reported by cold authorization elapsed_ms",
        },
        "sealed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def seal_precompact(
    *,
    repo_root: Path | str,
    function: str,
    seat_id: str,
    generation: str,
    lease_ids: Sequence[str],
    inertia: Mapping[str, int | float],
    extra_obligations: Sequence[str] = (),
    extra_residuals: Sequence[Mapping[str, Any]] = (),
    goal_context_path: Path | str | None = None,
    goal_context_handle: str | None = None,
    goal_context_bytes: int | None = None,
    compaction_boundary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Observe canonical sources once and seal their function-specialized successor profile."""

    from laplace.representation import atlas_bridge
    from laplace.engine import wake

    started = time.perf_counter_ns()
    suspension = load_ceremony_suspension()
    goal_context = None
    supplied_goal_fields = (
        goal_context_path is not None,
        goal_context_handle is not None,
        goal_context_bytes is not None,
    )
    if any(supplied_goal_fields) and not all(supplied_goal_fields):
        raise ContinuationRefused(
            "goal context path, handle, and byte count must be supplied together"
        )
    if all(supplied_goal_fields):
        goal_context = load_goal_context(
            goal_context_path,
            expected_handle=str(goal_context_handle),
            expected_bytes=int(goal_context_bytes),
        )
        stored_goal_handle = atlas_bridge.put_custody(goal_context["body"])
        if stored_goal_handle != goal_context["content_handle"]:
            raise ContinuationRefused("Atlas custody contradicted the exact goal context handle")
    from laplace.representation.embedding_health import read_health

    semantic_health = read_health(Path(repo_root).resolve())
    latest_counts = (semantic_health.get("latest_receipt") or {}).get(
        "embedding_counts"
    ) or {}
    semantic_current = (
        (semantic_health.get("side_ref_fold") or {}).get("status", "UNKNOWN") == "CURRENT"
        and int(latest_counts.get("deferred", -1)) == 0
        and bool((semantic_health.get("up_down") or {}).get("receipt_handle"))
    )
    if not semantic_current:
        coordinate = _git_coordinate(Path(repo_root).resolve())
        dirty = subprocess.run(
            ["git", "status", "--porcelain"], cwd=repo_root,
            capture_output=True, text=True, check=True,
        ).stdout.splitlines()
        delta = {
            "schema_version": "laplace.precompact-semantic-delta/1",
            "status": "BANKED-NOT-YET-ADMITTED",
            "function": function,
            "seat_id": seat_id,
            "generation": generation,
            "source_coordinate": coordinate,
            "dirty_paths": sorted(line[3:] for line in dirty if line),
            "goal_context_handle": None if goal_context is None else goal_context["content_handle"],
            "extra_obligations": list(extra_obligations),
            "extra_residuals": [dict(row) for row in extra_residuals],
            "compaction_boundary": None
            if compaction_boundary is None else dict(compaction_boundary),
            "predecessor_fold": semantic_health.get("side_ref_fold"),
            "reason": semantic_health.get("reason")
            or "semantic fold is not CURRENT with zero deferred and compact receipt",
            "authority_effect": "none",
        }
        delta_body = _canonical_bytes(delta)
        delta_handle = atlas_bridge.put_custody(delta_body)
        cadence: Mapping[str, Any]
        if dirty:
            cadence = {
                "status": "WAITING-FOR-CLEAN-S",
                "reason": "current author/session delta is banked but not a committed source S",
            }
        else:
            from laplace.representation.semantic_cadence import enqueue

            cadence = enqueue(
                repo_root,
                source_commit=coordinate["head"],
                source_tree=coordinate["tree"],
            )
        return {
            "schema_version": SEAL_SCHEMA,
            "status": "FOG",
            "event": "PreCompact",
            "tools_enabled": False,
            "profile_handle": None,
            "delta_capsule_handle": delta_handle,
            "semantic_health": semantic_health,
            "cadence": dict(cadence),
            "continuation": "join the one deduplicated S-to-F fold, then seal against exact F",
        }
    authority = atlas_bridge.authority_epoch()
    recovery = wake.recovery_coordinate_glow(repo_root)
    work_map = wake.development_work_map_glow(repo_root)
    collected_ms = (time.perf_counter_ns() - started) / 1_000_000
    profile = compile_profile(
        repo_root=repo_root,
        function=function,
        seat_id=seat_id,
        generation=generation,
        lease_ids=lease_ids,
        authority_epoch=authority,
        recovery_coordinate=recovery,
        work_map=work_map,
        inertia=inertia,
        extra_obligations=extra_obligations,
        extra_residuals=extra_residuals,
        source_collection_ms=collected_ms,
        ceremony_suspension=suspension,
        goal_context=goal_context,
        semantic_health=semantic_health,
        compaction_boundary=compaction_boundary,
    )
    body = _canonical_bytes(profile)
    handle = atlas_bridge.put_custody(body)
    if handle != "sha256:" + hashlib.sha256(body).hexdigest():
        raise ContinuationRefused("Atlas custody returned a contradictory profile handle")
    after_git = _git_coordinate(Path(repo_root).resolve())
    before_git = profile["current_frontier"]["git"]
    if after_git != before_git:
        raise ContinuationRefused(
            "profile-consumed Git coordinate moved during PreCompact seal",
            divergence={"before": before_git, "after": after_git},
        )
    ceremony = profile["authority_ceremony_suspension"]
    return {
        "schema_version": SEAL_SCHEMA,
        "status": "SEALED",
        "event": "PreCompact",
        "profile_handle": handle,
        "profile_digest": handle,
        "profile_bytes": len(body),
        "semantic_fold_health_handle": profile["shared_semantic_memory"]["health_handle"],
        "semantic_fold_receipt_handle": profile["shared_semantic_memory"][
            "semantic_fold_receipt_handle"
        ],
        "function": function,
        "seat_id": seat_id,
        "generation": generation,
        "continuation_environment": {
            PROFILE_HANDLE_ENV: handle,
            FUNCTION_ENV: function,
            "LAPLACE_SEAT_ID": seat_id,
            GENERATION_ENV: generation,
        },
        "measured_costs": profile["measured_costs"],
        "retired_live_scaffold": profile["submergence"]["retired_live_scaffold"],
        "goal_context_handle": (
            None if goal_context is None else goal_context["content_handle"]
        ),
        "compaction_boundary": None
        if compaction_boundary is None else dict(compaction_boundary),
        "record_only_authority_receipt": {
            "source": ceremony["source"],
            "exact_instruction": ceremony["exact_instruction"],
            "interpreted_scope": ceremony["interpreted_scope"],
            "procedural_gates_bypassed": ceremony["procedural_gates_bypassed"],
            "before_coordinate": before_git,
            "observed_result": {"profile_handle": handle, "status": "SEALED"},
            "after_coordinate": after_git,
            "concrete_error": None,
            "retained_hard_stops": ceremony["retained_hard_stops"],
            "reintroduction_default": ceremony["reintroduction_default"],
            "reintroduction_earliest_boundary": ceremony[
                "reintroduction_earliest_boundary"
            ],
        },
    }


def _load_profile(handle: str) -> dict[str, Any]:
    from laplace.representation import atlas_bridge

    body = atlas_bridge.custody_body(handle=handle)
    text = body.get("text")
    if not isinstance(text, str):
        raise ContinuationRefused("successor profile is not canonical UTF-8 JSON")
    try:
        profile = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ContinuationRefused("successor profile is not valid JSON") from exc
    if not isinstance(profile, dict) or profile.get("schema_version") != PROFILE_SCHEMA:
        raise ContinuationRefused("successor profile schema is unknown")
    if _canonical_bytes(profile).decode("utf-8") != text:
        raise ContinuationRefused("successor profile is not canonical JSON")
    return profile


def _reconstruct_compaction_delta(
    profile: Mapping[str, Any],
    *,
    semantic_health: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Cold-descend the exact transcript suffix sealed into a real PreCompact profile."""

    from laplace.representation import atlas_bridge
    from laplace.engine import descent
    from laplace.representation.semantic_vertical import digest, digest_bytes

    boundary = profile.get("compaction_boundary")
    if boundary is None:
        return None
    if not isinstance(boundary, Mapping) or boundary.get("event") != "PreCompact":
        raise ContinuationRefused("sealed compaction boundary is malformed")
    summary = boundary.get("semantic_delta")
    if not isinstance(summary, Mapping):
        raise ContinuationRefused("sealed PreCompact profile omits its transcript semantic delta")
    custody_handle = summary.get("delta_custody_handle")
    if not isinstance(custody_handle, str):
        raise ContinuationRefused("sealed transcript delta omits exact Atlas custody")
    custody = atlas_bridge.custody_body(handle=custody_handle)
    text = custody.get("text")
    if not isinstance(text, str) or digest_bytes(text.encode("utf-8")) != custody_handle:
        raise ContinuationRefused("sealed transcript delta custody bytes moved")
    try:
        delta = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ContinuationRefused("sealed transcript delta is not canonical JSON") from exc
    carried = delta.pop("delta_handle", None) if isinstance(delta, dict) else None
    if (
        not isinstance(delta, dict)
        or delta.get("schema_version") != "laplace.precompact-semantic-delta/1"
        or delta.get("status") != "COMPLETE"
        or digest(delta) != carried
        or carried != summary.get("delta_handle")
        or int(delta.get("n_deferred", -1)) != 0
    ):
        raise ContinuationRefused("sealed transcript semantic delta is malformed or incomplete")
    fold = semantic_health.get("side_ref_fold") or {}
    up_down = semantic_health.get("up_down") or {}
    global_fold = delta.get("global_F") or {}
    if (
        (semantic_health.get("side_ref_fold") or {}).get("status", "UNKNOWN") != "CURRENT"
        or global_fold.get("output_commit") != fold.get("output_commit")
        or global_fold.get("manifest_handle") != fold.get("manifest_handle")
        or global_fold.get("semantic_fold_receipt_handle") != up_down.get("receipt_handle")
        or summary.get("global_fold_receipt_handle") != up_down.get("receipt_handle")
    ):
        raise ContinuationRefused("transcript delta names a predecessor global semantic fold")
    route = delta.get("typed_descent")
    transcript = delta.get("transcript") or {}
    semantic_custody = (
        transcript.get("semantic_horizon_custody_handle")
        or transcript.get("suffix_custody_handle")
    )
    if (
        not isinstance(route, Mapping)
        or route.get("kind") != "atlas-custody"
        or route.get("reference") != semantic_custody
        or route != summary.get("typed_descent")
    ):
        raise ContinuationRefused("transcript delta typed descent route moved")
    descended = descent.descend(
        kind="atlas-custody",
        reference=str(route["reference"]),
        source="",
        goal="reconstruct the exact bounded author/session semantic horizon",
        content_budget=max(1, int(
            transcript.get("semantic_bytes") or transcript.get("suffix_bytes") or 0
        )),
        record_telemetry=False,
    )
    if (
        descended.get("content_status") != "COMPLETE"
        or descended.get("content_handle") != route["reference"]
    ):
        raise ContinuationRefused("cold successor could not exactly descend transcript custody")
    return {
        "schema_version": "laplace.postcompact-transcript-reconstruction/1",
        "status": "COMPLETE",
        "delta_handle": carried,
        "delta_custody_handle": custody_handle,
        "author_turn_handle": delta.get("author_turn_handle"),
        "up_receipt_handle": delta.get("up_receipt_handle"),
        "typed_descent": dict(route),
        "content_handle": descended.get("content_handle"),
        "content": descended.get("content"),
        "global_fold_receipt_handle": up_down.get("receipt_handle"),
        "authority_effect": "none",
    }


def reconstruct_cold_successor(
    *,
    repo_root: Path | str,
    profile_handle: str,
    function: str,
    seat_id: str,
    generation: str,
) -> dict[str, Any]:
    """Authorize a cold successor iff every root this function consumed is unchanged."""

    from laplace.representation import atlas_bridge

    started = time.perf_counter_ns()
    profile = _load_profile(profile_handle)
    expected_identity = {
        "function": function.strip().lower(),
        "seat_id": seat_id,
        "generation": generation,
    }
    identity_divergence = {
        key: {"sealed": profile.get(key), "current": value}
        for key, value in expected_identity.items()
        if profile.get(key) != value
    }
    if identity_divergence:
        raise ContinuationRefused(
            "cold successor identity contradicts sealed function profile",
            divergence=identity_divergence,
        )

    sealed_frontier = profile.get("current_frontier") or {}
    sealed_git = sealed_frontier.get("git") or {}
    current_git = _git_coordinate(Path(repo_root).resolve())
    current_authority = _effective_authority(atlas_bridge.authority_epoch())
    current_function = _function_roots(
        current_authority,
        function=function,
        seat_id=seat_id,
        lease_ids=tuple((profile.get("leases") or {}).keys()),
    )
    current_function_roots = current_function["values"]
    current_paths = _path_roots(
        Path(repo_root).resolve(), current_function["selected_lease_rows"]
    )
    divergence: dict[str, Any] = {}
    sealed_paths = sealed_frontier.get("consumed_paths")
    if current_paths != sealed_paths:
        divergence["consumed_paths"] = {"sealed": sealed_paths, "current": current_paths}
    sealed_roots = sealed_frontier.get("authority_consumed_roots")
    if current_function_roots != sealed_roots:
        divergence["authority_consumed_roots"] = {
            "sealed": sealed_roots,
            "current": current_function_roots,
        }
    if divergence:
        raise ContinuationRefused(
            "cold successor consumed roots moved after PreCompact",
            divergence=divergence,
        )

    elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
    from laplace.representation.embedding_health import read_health

    semantic_health = read_health(Path(repo_root).resolve())
    sealed_semantic = profile.get("shared_semantic_memory") or {}
    current_semantic_handle = (semantic_health.get("side_ref_fold") or {}).get("manifest_handle")
    current_fold_receipt = (semantic_health.get("up_down") or {}).get("receipt_handle")
    semantic_context_status = "CURRENT" if (
        (semantic_health.get("side_ref_fold") or {}).get("status", "UNKNOWN") == "CURRENT"
        and current_semantic_handle == sealed_semantic.get("health_handle")
        and current_fold_receipt == sealed_semantic.get("semantic_fold_receipt_handle")
        and int(((semantic_health.get("latest_receipt") or {}).get(
            "embedding_counts"
        ) or {}).get("deferred", -1)) == 0
    ) else "UNKNOWN"
    if semantic_context_status != "CURRENT":
        return {
            "schema_version": COLD_SCHEMA,
            "status": "UNKNOWN",
            "event": "PostCompact",
            "profile_handle": profile_handle,
            "function": function,
            "seat_id": seat_id,
            "generation": generation,
            "tools_enabled": False,
            "semantic_context_status": semantic_context_status,
            "shared_semantic_memory": semantic_health,
            "reason": "sealed profile names a predecessor or incomplete semantic fold",
        }
    try:
        transcript_delta = _reconstruct_compaction_delta(
            profile, semantic_health=semantic_health
        )
    except ContinuationRefused as exc:
        return {
            "schema_version": COLD_SCHEMA,
            "status": "UNKNOWN",
            "event": "PostCompact",
            "profile_handle": profile_handle,
            "function": function,
            "seat_id": seat_id,
            "generation": generation,
            "tools_enabled": False,
            "semantic_context_status": "FOG",
            "shared_semantic_memory": semantic_health,
            "reason": exc.reason,
            "divergence": exc.divergence,
        }
    return {
        "schema_version": COLD_SCHEMA,
        "status": "AUTHORIZED",
        "event": "PostCompact",
        "profile_handle": profile_handle,
        "profile_digest": profile_handle,
        "function": function,
        "seat_id": seat_id,
        "generation": generation,
        "tools_enabled": True,
        "exact_profile": profile,
        "semantic_context_status": semantic_context_status,
        "shared_semantic_memory": semantic_health,
        "transcript_delta_reconstruction": transcript_delta,
        "observation": {
            "divergence": {},
            "git": {"sealed": sealed_git, "current": current_git},
            "unrelated_dirty_paths": "not-a-consumed-root",
            "unrelated_git_descendants": "permitted when consumed path roots are unchanged",
            "unrelated_atlas_events": "permitted when consumed authority roots are unchanged",
        },
        "performance": {
            "elapsed_ms": round(elapsed_ms, 3),
            "subprocesses": 1,
            "recovery_coordinate_verifier_runs": 0,
            "retired_live_scaffold": "postcompact-recovery-coordinate-revalidation",
        },
    }


def wake_preflight_from_environment(repo_root: Path | str) -> dict[str, Any]:
    """Run before watcher/provider integration; absence preserves the ordinary wake path."""

    handle = os.environ.get(PROFILE_HANDLE_ENV, "").strip()
    if not handle:
        return {
            "schema_version": COLD_SCHEMA,
            "status": "NOT_REQUESTED",
            "tools_enabled": True,
        }
    function = os.environ.get(FUNCTION_ENV, "").strip()
    seat_id = os.environ.get("LAPLACE_SEAT_ID", "").strip()
    generation = os.environ.get(GENERATION_ENV, "").strip()
    if not all((function, seat_id, generation)):
        raise ContinuationRefused(
            "sealed cold continuation requires LAPLACE_FUNCTION, LAPLACE_SEAT_ID, and "
            "LAPLACE_SEAT_GENERATION before tools enable"
        )
    return reconstruct_cold_successor(
        repo_root=repo_root,
        profile_handle=handle,
        function=function,
        seat_id=seat_id,
        generation=generation,
    )


__all__ = [
    "COLD_SCHEMA",
    "ContinuationRefused",
    "FUNCTION_ENV",
    "GENERATION_ENV",
    "GOAL_CONTEXT_SCHEMA",
    "HIERARCHY_DERIVATION_HANDLE",
    "INTEGRATED_ROOTS",
    "CEREMONY_SUSPENSION_SHA256",
    "PROFILE_HANDLE_ENV",
    "PROFILE_SCHEMA",
    "admit_continuation",
    "compile_profile",
    "consume_hierarchy_derivation",
    "consume_regularization_ruling",
    "load_ceremony_suspension",
    "load_goal_context",
    "reconstruct_cold_successor",
    "seal_precompact",
    "wake_preflight_from_environment",
]
