#!/usr/bin/env python3
"""Build the next compact Atlas recovery-coordinate version from live authority.

The previous coordinate is verified first.  ``INVALID`` is a hard refusal; an exact ancestor in
``SUPERSESSION-REQUIRED`` is the normal input after an accepted source batch.  By default the next
document is printed to stdout.  ``--write`` atomically replaces ``--output`` for the operational
path; the caller still commits that one packaging delta so Git remains off-machine custody.  The
mutable ``CURRENT`` alias can never supersede itself: its exact predecessor must already be banked
at the deterministic immutable version path and committed before the alias may advance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from laplace.representation.recovery_coordinate import DEFAULT_COORDINATE, canonical_payload_digest, runtime_recovery_point_from_capsule, verify_coordinate


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _chash(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _rel(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _immutable_predecessor_path(alias: Path, previous: Mapping[str, Any]) -> Path:
    version = int(previous.get("coordinate_version") or 1)
    created = str(previous.get("created_at") or "")
    stamp = "".join(character for character in created[:10] if character.isdigit())
    if len(stamp) != 8:
        raise ValueError(
            "the mutable recovery alias has no YYYY-MM-DD created_at for immutable archival"
        )
    return alias.with_name(f"RECOVERY-COORDINATE-{stamp}-v{version}.json")


def _committed_file_exact(path: Path) -> bool:
    relative = _rel(path, ROOT)
    completed = subprocess.run(
        ["git", "show", f"HEAD:{relative}"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    return completed.returncode == 0 and completed.stdout == path.read_bytes()


def _resolve_predecessor_path(
    previous_path: Path,
    output_path: Path,
    previous: Mapping[str, Any],
) -> Path:
    if previous_path != output_path:
        return previous_path
    archive = _immutable_predecessor_path(previous_path, previous)
    if not archive.exists():
        raise ValueError(
            "the mutable recovery alias cannot supersede itself; first copy its exact bytes to "
            f"{_rel(archive, ROOT)}, commit that immutable predecessor, then rerun"
        )
    if archive.read_bytes() != previous_path.read_bytes():
        raise ValueError(
            "the deterministic immutable predecessor disagrees with the current alias: "
            f"{_rel(archive, ROOT)}"
        )
    if not _committed_file_exact(archive):
        raise ValueError(
            "the immutable predecessor is not exact against its committed Git blob; commit "
            f"{_rel(archive, ROOT)} before advancing the current alias"
        )
    return archive


def derive_live_contact(
    *, required_functions: Mapping[str, str] | None = None
) -> dict[str, Any]:
    """Reconstruct current logical-seat contact from Atlas, never predecessor prose.

    A seat registration alone is not live contact.  The face admits only the latest exact
    occupancy binding with routing authority and no join/binding defects.  Provider-task liveness
    remains bounded by the Atlas binding evidence; a later renewable occupancy lease can sharpen
    that boundary without changing the successor-closure rule.
    """

    from laplace.representation import atlas_bridge

    required = dict(required_functions or {"superego-seat": "superego"})
    token_before = atlas_bridge.drift_token()
    provider = atlas_bridge.snapshot()["provider"]
    occupancy = provider.get("seat_occupancy") or {}
    contacts: dict[str, dict[str, Any]] = {}
    refusals: dict[str, list[str]] = {}
    for seat_id, expected_function in required.items():
        face = occupancy.get(seat_id) or {}
        join = face.get("join") or {}
        binding = face.get("binding") or {}
        defects = [str(item) for item in (face.get("defects") or join.get("defects") or ())]
        reasons = []
        if face.get("state") != "BOUND":
            reasons.append("seat occupancy is not BOUND")
        if face.get("routing_authority") is not True:
            reasons.append("seat occupancy lacks routing authority")
        if not binding:
            reasons.append("seat occupancy has no exact binding")
        if join.get("mail_state") != "MAIL_READY":
            reasons.append(f"seat mail is not ready: {join.get('mail_state')}")
        if binding.get("function") != expected_function:
            reasons.append(
                f"seat function is not {expected_function}: {binding.get('function')}"
            )
        for field in (
            "provider_session_ref",
            "registered_principal_ref",
            "provider_identity_proof_handle",
        ):
            if not binding.get(field):
                reasons.append(f"seat binding omits {field}")
        for field in ("join_event_id", "binding_event_id"):
            if not face.get(field):
                reasons.append(f"seat occupancy omits {field}")
        if defects:
            reasons.extend(f"occupancy defect: {item}" for item in defects)
        if reasons:
            refusals[seat_id] = reasons
            continue
        contacts[seat_id] = {
            "state": "BOUND",
            "routing_authority": True,
            "function": binding.get("function"),
            "provider_session_ref": binding.get("provider_session_ref"),
            "registered_principal_ref": binding.get("registered_principal_ref"),
            "provider_identity_proof_handle": binding.get(
                "provider_identity_proof_handle"
            ),
            "mail_state": join.get("mail_state"),
            "join_event_id": face.get("join_event_id"),
            "binding_event_id": face.get("binding_event_id"),
        }
    if refusals:
        raise ValueError(
            "required live seat contact cannot be reconstructed: "
            + json.dumps(refusals, ensure_ascii=False, sort_keys=True)
        )
    token = atlas_bridge.drift_token()
    if token != token_before:
        raise ValueError(
            "live Atlas moved while reconstructing required seat contact; retry from one exact token"
        )
    return {
        "schema_version": "atlas.recovery-live-contact/1",
        "derived_from": {
            "schema_version": token.get("schema_version"),
            "cursor": token.get("cursor"),
            "head_event_id": token.get("head_event_id"),
            "head_record_digest": token.get("head_record_digest"),
        },
        "required_seats": sorted(required),
        "seats": contacts,
        "claim_boundary": (
            "current according to exact Atlas occupancy binding; provider-process heartbeat "
            "or renewable occupancy expiry is not yet proved"
        ),
    }


def build_successor(
    previous: Mapping[str, Any],
    verification: Mapping[str, Any],
    *,
    previous_path: str,
    output_path: str,
    packaging_paths: list[str],
    created_at: str,
    live_contact: Mapping[str, Any],
    runtime_recovery_point: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if verification.get("coordinate_state") in {"INVALID", "SUPERSEDED"}:
        raise ValueError(
            f"a {verification.get('coordinate_state')} recovery coordinate cannot found a successor"
        )
    coordinate = verification["coordinate"]
    git = verification["git"]
    runtime = verification["runtime_atlas"]
    semantic = verification["semantic_fold"]
    blueprint = verification["blueprint"]
    fabric = verification["fabric_debt"]
    if blueprint.get("status") == "UNMEASURED":
        raise ValueError("successor mint requires the blueprint axis to be measured")
    if not output_path.startswith("atlas/packets/recovery/") or not output_path.endswith(".json"):
        raise ValueError("recovery coordinate packaging is restricted to its packet directory")
    unexpected_packaging = sorted(set(packaging_paths) - {output_path})
    if unexpected_packaging:
        raise ValueError(
            "coordinate packaging cannot bless source or handoff movement: "
            + ", ".join(unexpected_packaging)
        )
    required_live_seats = tuple(
        str(item) for item in live_contact.get("required_seats") or ()
    )
    live_seats = live_contact.get("seats") or {}
    missing_live_seats = sorted(set(required_live_seats) - set(live_seats))
    malformed_live_seats = sorted(
        seat_id
        for seat_id in required_live_seats
        if (
            (live_seats.get(seat_id) or {}).get("state") != "BOUND"
            or (live_seats.get(seat_id) or {}).get("routing_authority") is not True
            or not (live_seats.get(seat_id) or {}).get("provider_session_ref")
            or not (live_seats.get(seat_id) or {}).get("join_event_id")
            or not (live_seats.get(seat_id) or {}).get("binding_event_id")
            or (live_seats.get(seat_id) or {}).get("mail_state") != "MAIL_READY"
        )
    )
    if (
        live_contact.get("schema_version") != "atlas.recovery-live-contact/1"
        or not required_live_seats
        or missing_live_seats
        or malformed_live_seats
    ):
        raise ValueError(
            "successor live contact is not an exact complete occupancy projection: "
            + json.dumps({
                "missing_required_seats": missing_live_seats,
                "malformed_live_seats": malformed_live_seats,
            }, sort_keys=True)
        )

    prior_version = int(previous.get("coordinate_version") or 1)
    expanded_source = (previous.get("fabric_debt") or {}).get("expanded_identity_source")
    if not expanded_source:
        expanded_source = {
            "path": previous_path,
            "payload_digest": coordinate["recorded_payload_digest"],
        }
    by_seat = {
        seat: {
            "count": int(face.get("count") or 0),
            "queued": int(face.get("queued") or 0),
            "pulled": int(face.get("pulled") or 0),
        }
        for seat, face in (fabric.get("by_seat") or {}).items()
    }
    current_ids = sorted(
        str(message_id)
        for face in (fabric.get("by_seat") or {}).values()
        for message_id in (face.get("message_ids") or ())
    )
    expanded_source_ids = sorted(fabric.get("expanded_source_message_ids") or ())
    recovery_point = dict(
        runtime_recovery_point or previous.get("runtime_recovery_point") or {}
    )
    recovery_grant = None
    if recovery_point:
        point_root = recovery_point.get("point_root")
        point_body = dict(recovery_point)
        point_body.pop("point_root", None)
        if point_root != _chash(point_body):
            raise ValueError("runtime recovery point root does not verify")
        recovery_grant = {
            "schema_version": "laplace.runtime-recovery-coordinate-grant/1",
            "point_root": point_root,
            "source_snapshot_id": recovery_point.get("source_snapshot_id"),
            "source_checkpoint_digest": (
                (recovery_point.get("source_checkpoint") or {}).get("checkpoint_digest")
            ),
            "predecessor_coordinate_payload_digest": coordinate[
                "recorded_payload_digest"
            ],
            "target_store_role": "live-runtime-fabric",
        }
        recovery_grant["grant_anchor_root"] = _chash(recovery_grant)
    document: dict[str, Any] = {
        "schema_version": "atlas.recovery-coordinate/2",
        "coordinate_id": previous["coordinate_id"],
        "coordinate_version": prior_version + 1,
        "created_at": created_at,
        "coordinate_payload_digest": "",
        "digest_contract": previous.get("digest_contract"),
        "supersedes": {
            "path": previous_path,
            "payload_digest": coordinate["recorded_payload_digest"],
        },
        "purpose": "Mechanically refreshed compact S2 recovery root.",
        "carried_contract": previous.get("carried_contract") or {
            "path": previous_path,
            "payload_digest": coordinate["recorded_payload_digest"],
            "law": "Static gates and authority boundaries are carried by exact digest.",
        },
        "stage_frontier": previous.get("stage_frontier"),
        "active_goal": previous.get("active_goal"),
        "freshness_vector": {
            "observed_at": created_at,
            "git": {
                "head": git["current_head"],
                "tree": _git_tree_from_verification(git),
                "allowed_descendant_paths": [output_path],
                "status_nul_sha256_before_coordinate": git["status_nul_sha256"],
                "tracked_diff_sha256_before_coordinate": git["tracked_diff_sha256"],
                "staged_diff_sha256_before_coordinate": git["staged_diff_sha256"],
                # Permission can narrow but never be minted from the live dirt it judges.
                "restored_preexisting_dirty_paths": list(
                    ((previous.get("freshness_vector") or {}).get("git") or {}).get(
                        "restored_preexisting_dirty_paths", ()
                    )
                ),
            },
            "runtime_atlas": {
                **runtime["live"],
                "active_assumption": runtime["active_context"].get("assumption"),
                "active_fibre": runtime["active_context"].get("fibre"),
                "warning": (
                    "Exact historical lower bound: a verified append-only suffix on the same "
                    "fibre is normal traffic; context transport requires supersession."
                ),
            },
            "semantic_fold": {
                "folded_git_head": semantic.get("folded_git_head"),
                "current_git_head": semantic.get("current_git_head"),
                "commits_behind": semantic.get("commits_behind"),
                "status": semantic.get("status"),
                "post_lock": semantic.get("post_lock"),
                "input_frontier": (semantic.get("frontier") or {}).get(
                    "input_frontier"
                ),
                "post_artifacts": (semantic.get("frontier") or {}).get(
                    "post_artifacts"
                ),
                "closure_model": "semantic-post-lock/1",
                "consequence": (
                    "Human-name routing cannot certify currentness while stale and must not "
                    "substitute for an exact reference. Git commit distance is provenance only; "
                    "currentness is the exact semantic dependency frontier locked to its outputs."
                ),
            },
            "blueprint": {
                "generation_id": blueprint.get("generation_id"),
                "pour_handle": blueprint.get("pour_handle"),
                "current_against_worktree": blueprint.get("current") is True,
                "moved_source_roots": blueprint.get("moved_source_roots") or [],
                "counts": blueprint.get("counts"),
                "ruling": (
                    "The generation remains authority inside its declared frontier; moved roots "
                    "are explicit blueprint-fidelity debt, never concealed by a cosmetic repour."
                ),
            },
        },
        "fabric_debt": {
            "snapshot_cursor": runtime["live"].get("cursor"),
            "status": "CLEAR" if int(fabric.get("total") or 0) == 0 else "NONTERMINAL",
            "total": int(fabric.get("total") or 0),
            "all_message_ids_sorted_sha256": fabric.get("message_ids_sha256"),
            "by_seat": by_seat,
            "expanded_identity_source": expanded_source,
            "identity_delta": {
                "added_message_ids": sorted(set(current_ids) - set(expanded_source_ids)),
                "resolved_message_ids": sorted(set(expanded_source_ids) - set(current_ids)),
            },
            "rule": (
                "Count plus exact sorted-set digest verifies the compact snapshot; the immutable "
                "expanded source plus exact delta reconstructs every identity before judgement."
            ),
        },
        "live_contact": dict(live_contact),
        "first_act_after_compaction_or_wake": [
            "Run `/usr/bin/python3 scripts/wake.py --grade 0` and treat prose as hypothesis.",
            f"Exact-resolve `{output_path}` and its superseded coordinate.",
            "Run `/usr/bin/python3 scripts/verify_recovery_coordinate.py`.",
            "Refuse writer custody unless coordinate_state is CURRENT-FOR-RECOVERY.",
            "Keep coordinate_state separate from system_state; a current coordinate may carry honest recovery reds.",
        ],
        "authority": previous.get("authority"),
        "source_verification": {
            "prior_coordinate_state": verification.get("coordinate_state"),
            "prior_system_state": verification.get("system_state"),
            "supersession_axes": verification.get("supersession_axes"),
            "hard_reds": verification.get("hard_reds"),
        },
    }
    if recovery_point:
        document["runtime_recovery_point"] = recovery_point
        document["runtime_recovery_grant"] = recovery_grant
    document["coordinate_payload_digest"] = canonical_payload_digest(document)
    return document


def _git_tree_from_verification(git: Mapping[str, Any]) -> str:
    import subprocess

    completed = subprocess.run(
        ["git", "rev-parse", f"{git['current_head']}^{{tree}}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--previous", default=str(DEFAULT_COORDINATE))
    parser.add_argument(
        "--output",
        default="atlas/packets/recovery/RECOVERY-COORDINATE-CURRENT.json",
    )
    parser.add_argument("--packaging-path", action="append", default=[])
    parser.add_argument(
        "--runtime-custody-capsule",
        help="offline-verified custody capsule v2 to bind as the historical recovery point",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    previous_path = Path(args.previous).resolve()
    output_path = (ROOT / args.output).resolve()
    previous = json.loads(previous_path.read_text(encoding="utf-8"))
    previous_path = _resolve_predecessor_path(previous_path, output_path, previous)
    previous = json.loads(previous_path.read_text(encoding="utf-8"))
    verification = verify_coordinate(previous_path)
    live_contact = derive_live_contact()
    document = build_successor(
        previous,
        verification,
        previous_path=_rel(previous_path, ROOT),
        output_path=_rel(output_path, ROOT),
        packaging_paths=list(args.packaging_path),
        created_at=_now(),
        live_contact=live_contact,
        runtime_recovery_point=(
            None
            if not args.runtime_custody_capsule
            else runtime_recovery_point_from_capsule(args.runtime_custody_capsule)
        ),
    )
    rendered = json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.write:
        _atomic_write(output_path, rendered)
    else:
        print(rendered, end="")
    return 0


def cli() -> int:
    try:
        return main()
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(json.dumps({
            "schema_version": "atlas.recovery-coordinate-refresh-refusal/1",
            "refused": True,
            "successor_written": False,
            "residue": {
                "code": "SUCCESSOR_MINT_REFUSED",
                "message": str(exc),
                "exception_type": type(exc).__name__,
            },
        }, ensure_ascii=False, indent=1))
        return 1


if __name__ == "__main__":
    raise SystemExit(cli())
