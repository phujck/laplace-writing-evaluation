"""Mechanical freshness verification for the Atlas recovery coordinate.

The coordinate is a compact bootstrap, not a new oracle.  This module compares each of its
authority axes against the live authority that owns that axis and distinguishes three outcomes:

``CURRENT-FOR-RECOVERY``
    the exact version still names the observed recovery frontier;
``SUPERSESSION-REQUIRED``
    the old frontier is a verified ancestor, but custody must not move until a new version records
    the delta; and
``INVALID``
    an immutable claim, ancestry proof, or exact historical Atlas token does not hold.

System health is reported separately.  A perfectly current recovery coordinate may honestly say
that the system itself remains in RECOVERY because the semantic fold, blueprint, Fabric debt, or
worktree is not yet clean.
"""
from __future__ import annotations
from laplace.core.checkout import source_tree

import hashlib
import json
import sqlite3
import subprocess
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

REPO_ROOT = source_tree()
DEFAULT_COORDINATE = (
    REPO_ROOT
    / "atlas"
    / "packets"
    / "recovery"
    / "RECOVERY-COORDINATE-CURRENT.json"
)
SEMANTIC_FOLD_PATHS = (".meaning_tree.json", ".self_graded.json")
_AUTHORITY_SOURCE_PREFIXES = ("src/", "scripts/", "tests/", "atlas/tests/")   # src/ covers src/atlas (R2)
_AUTHORITY_SOURCE_PATHS = {
    ".codex/config.toml",
    "AGENTS.md",
    "EIGEN_PROTOCOL.md",
    "HANDOFF.md",
    "TECHNICAL_GUIDE.md",
    "pyproject.toml",
}
_RUNTIME_DERIVED_PATHS = {
    ".closure_meter.jsonl",
    ".escalate_briefs.json",
    ".fallback_events.jsonl",
    ".learned_keywords.json",
    ".meaning_tree.json",
    ".metric_M.npz",
    ".reembed_timing.jsonl",
    ".residue.jsonl",
    ".self_embeddings.json",
    ".self_graded.json",
    ".self_record_floor.jsonl",
    ".upfold_triggers.jsonl",
    ".wire_proposals.jsonl",
    ".wire_verdicts.jsonl",
    "SELF_GRADED_INDEX.md",
    "SELF_SHARD_INDEX.md",
    "THE_DESK.md",
    "contract/journal.jsonl",
    "corpus_friction/suite_runs.jsonl",
}
_AUTHORITY_INTEGRITY_BOUNDARY = "CHECKSUMMED-CRUTCH"
_AUTHORITY_CRUTCH_ID = "CR-C2A-CHECKSUMMED-LIVE-AUTHORITY-20260828"
_AUTHORITY_TAIL_LIMIT = 64
_AUTHORITY_ATTEMPTS = 2
RUNTIME_RECOVERY_POINT_SCHEMA = "laplace.runtime-recovery-point/1"
RUNTIME_CUSTODY_V2_SCHEMA = "laplace.runtime-atlas-custody/2"


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def canonical_payload_digest(document: Mapping[str, Any]) -> str:
    """Implement the coordinate's jq-sorted digest contract without invoking jq."""

    payload = dict(document)
    payload.pop("coordinate_payload_digest", None)
    encoded = (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
        "utf-8"
    )
    return _sha256(encoded)


def _canonical_receipt_digest(document: Mapping[str, Any]) -> str:
    payload = dict(document)
    payload.pop("receipt_payload_digest", None)
    encoded = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    return _sha256(encoded)


def runtime_recovery_point_from_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Derive the historical point carried by a later committed coordinate."""

    if receipt.get("schema_version") != RUNTIME_CUSTODY_V2_SCHEMA:
        raise ValueError("runtime recovery point requires a custody capsule v2 receipt")
    if receipt.get("authenticated") is not False or receipt.get(
        "integrity_boundary"
    ) != "CHECKSUMMED-CRUTCH":
        raise ValueError("runtime recovery point source overstates authentication")
    receipt_digest = _canonical_receipt_digest(receipt)
    if receipt.get("receipt_payload_digest") != receipt_digest:
        raise ValueError("runtime recovery point source receipt digest does not verify")
    required_maps = {
        name: receipt.get(name)
        for name in ("custody_roots", "source_checkpoint", "source_authority_context", "source_git")
    }
    if any(not isinstance(value, Mapping) for value in required_maps.values()):
        raise ValueError("runtime recovery point source provenance is incomplete")
    point = {
        "schema_version": RUNTIME_RECOVERY_POINT_SCHEMA,
        "status": "HISTORICAL-CHECKSUMMED",
        "authenticated": False,
        "integrity_boundary": "CHECKSUMMED-CRUTCH",
        "source_snapshot_id": receipt.get("snapshot_id"),
        "source_receipt_digest": receipt_digest,
        "source_ledger_sha256": (receipt.get("ledger") or {}).get("sha256"),
        "source_custody_roots": dict(required_maps["custody_roots"]),
        "source_checkpoint": dict(required_maps["source_checkpoint"]),
        "source_authority_context_root": required_maps[
            "source_authority_context"
        ].get("evidence_root"),
        "source_git": dict(required_maps["source_git"]),
        "source_recovery_coordinate_payload_digest": receipt.get(
            "recovery_coordinate_payload_digest"
        ),
        "whole_directory_rollback_without_external_anchor": "UNPAID",
    }
    for field in (
        "source_snapshot_id",
        "source_receipt_digest",
        "source_ledger_sha256",
        "source_authority_context_root",
        "source_recovery_coordinate_payload_digest",
    ):
        if not str(point.get(field) or "").startswith("sha256:"):
            raise ValueError(f"runtime recovery point omits {field}")
    point["predecessor_adoption_root"] = _canonical_chash(
        {
            "schema_version": "laplace.portable-adoption-lineage/1",
            "source_snapshot_id": point["source_snapshot_id"],
            "source_checkpoint_digest": point["source_checkpoint"].get(
                "checkpoint_digest"
            ),
            "predecessor": None,
        }
    )
    point["point_root"] = _canonical_chash(point)
    return point


def runtime_recovery_point_from_capsule(path: Path | str) -> dict[str, Any]:
    root = Path(path).expanduser().resolve()
    try:
        receipt = json.loads((root / "RECEIPT.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("runtime recovery capsule receipt is absent or malformed") from exc
    return runtime_recovery_point_from_receipt(receipt)


def verify_runtime_recovery_point(
    point: Mapping[str, Any],
    capsule_path: Path | str,
) -> dict[str, Any]:
    """Offline-verify one capsule against the coordinate-carried historical point."""

    from laplace.representation import atlas_bridge

    if point.get("schema_version") != RUNTIME_RECOVERY_POINT_SCHEMA:
        raise ValueError("runtime recovery point schema is unknown")
    supplied = dict(point)
    point_root = supplied.pop("point_root", None)
    if _canonical_chash(supplied) != point_root:
        raise ValueError("runtime recovery point root does not verify")
    verified = atlas_bridge.verify_runtime_custody(capsule_path)
    receipt = json.loads(
        (Path(capsule_path).expanduser().resolve() / "RECEIPT.json").read_text(
            encoding="utf-8"
        )
    )
    expected = runtime_recovery_point_from_receipt(receipt)
    if dict(point) != expected:
        raise ValueError("runtime recovery point disagrees with the custody capsule")
    return {
        "schema_version": "laplace.runtime-recovery-point-verification/1",
        "status": "EXACT",
        "read_only": True,
        "authenticated": False,
        "integrity_boundary": "CHECKSUMMED-CRUTCH",
        "point_root": point_root,
        "source_snapshot_id": verified["snapshot_id"],
        "source_receipt_digest": expected["source_receipt_digest"],
        "source_checkpoint_digest": expected["source_checkpoint"]["checkpoint_digest"],
        "whole_directory_rollback_without_external_anchor": "UNPAID",
    }


def _verify_runtime_recovery_coordinate_claim(
    document: Mapping[str, Any],
) -> dict[str, Any]:
    point = document.get("runtime_recovery_point")
    grant = document.get("runtime_recovery_grant")
    if point is None and grant is None:
        return {"status": "ABSENT", "historical_point": False}
    if not isinstance(point, Mapping) or not isinstance(grant, Mapping):
        return {"status": "INVALID", "reason": "point and grant must appear together"}
    point_body = dict(point)
    point_root = point_body.pop("point_root", None)
    if point.get("schema_version") != RUNTIME_RECOVERY_POINT_SCHEMA or _canonical_chash(
        point_body
    ) != point_root:
        return {"status": "INVALID", "reason": "runtime recovery point root mismatch"}
    grant_body = dict(grant)
    grant_root = grant_body.pop("grant_anchor_root", None)
    if (
        grant.get("schema_version") != "laplace.runtime-recovery-coordinate-grant/1"
        or _canonical_chash(grant_body) != grant_root
        or grant.get("point_root") != point_root
        or grant.get("source_snapshot_id") != point.get("source_snapshot_id")
        or grant.get("source_checkpoint_digest")
        != (point.get("source_checkpoint") or {}).get("checkpoint_digest")
    ):
        return {"status": "INVALID", "reason": "runtime recovery grant root mismatch"}
    return {
        "status": "EXACT",
        "historical_point": True,
        "point_root": point_root,
        "grant_anchor_root": grant_root,
        "authenticated": False,
        "integrity_boundary": "CHECKSUMMED-CRUTCH",
    }


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    completed = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, check=False
    )
    if check and completed.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed: "
            f"{completed.stderr.decode('utf-8', errors='replace').strip()}"
        )
    return completed


def _dirty_paths(root: Path) -> tuple[list[str], bytes]:
    raw = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all").stdout
    fields = raw.split(b"\0")
    paths: set[str] = set()
    index = 0
    while index < len(fields):
        field = fields[index]
        index += 1
        if not field:
            continue
        status = field[:2].decode("ascii", errors="replace")
        path = field[3:].decode("utf-8", errors="surrogateescape")
        paths.add(path)
        if status[:1] in {"R", "C"} and index < len(fields) and fields[index]:
            paths.add(fields[index].decode("utf-8", errors="surrogateescape"))
            index += 1
    return sorted(paths), raw


def _hash_lines(values: Iterable[str]) -> str:
    ordered = list(values)
    return _sha256((("\n".join(ordered) + "\n") if ordered else "").encode("utf-8"))


def _authority_source_path(path: str) -> bool:
    return path in _AUTHORITY_SOURCE_PATHS or path.startswith(_AUTHORITY_SOURCE_PREFIXES)


def _dirty_path_class(path: str) -> str:
    """Classify worktree movement without accepting authority from the coordinate.

    The recovery coordinate is an observation, so none of its fields may turn an arbitrary
    dirty path into an allowed one.  Engine-written state is nonblocking by a predicate owned
    by this verifier; source/authority and unknown paths remain hard custody reds.
    """

    if _authority_source_path(path):
        return "AUTHORITY-SOURCE"
    if path in _RUNTIME_DERIVED_PATHS:
        return "RUNTIME-DERIVED"
    if (
        path.startswith("atlas/stores/")
        and path.endswith(("conceptric.sqlite3-shm", "conceptric.sqlite3-wal"))
    ):
        return "RUNTIME-SQLITE-SIDECAR"
    return "UNCLASSIFIED"


def _committed_file_exact(root: Path, relative_path: str) -> bool:
    if not relative_path:
        return False
    tracked = _git(root, "cat-file", "-e", f"HEAD:{relative_path}", check=False)
    if tracked.returncode != 0:
        return False
    committed = _git(root, "show", f"HEAD:{relative_path}", check=False)
    try:
        live = (root / relative_path).read_bytes()
    except OSError:
        return False
    return committed.returncode == 0 and committed.stdout == live


def _verify_allowlist_chain(document: Mapping[str, Any], root: Path) -> dict[str, Any]:
    """Prove dirty-path permission only narrows along committed immutable predecessors."""

    current_allowed = set(
        str(path)
        for path in ((document.get("freshness_vector") or {}).get("git") or {}).get(
            "restored_preexisting_dirty_paths", ()
        )
    )
    reference = document.get("supersedes") or None
    steps: list[dict[str, Any]] = []
    seen: set[str] = set()
    error = None
    for _depth in range(16):
        if not reference:
            break
        path_text = str(reference.get("path") or "")
        digest = str(reference.get("payload_digest") or "")
        if not path_text or path_text in seen:
            error = "supersession chain is missing a path or contains a cycle"
            break
        seen.add(path_text)
        try:
            path = (root / path_text).resolve()
            path.relative_to(root)
            prior = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            error = f"superseded coordinate is unreadable: {type(exc).__name__}: {exc}"
            break
        actual = canonical_payload_digest(prior)
        if not digest or actual != digest:
            error = "superseded coordinate digest does not match its immutable reference"
            break
        if not _committed_file_exact(root, path_text):
            error = "superseded coordinate is not exact against the committed Git blob"
            break
        prior_allowed = set(
            str(item)
            for item in ((prior.get("freshness_vector") or {}).get("git") or {}).get(
                "restored_preexisting_dirty_paths", ()
            )
        )
        widened = sorted(current_allowed - prior_allowed)
        steps.append({
            "path": path_text,
            "payload_digest": digest,
            "allowed_dirty_count": len(prior_allowed),
            "widened_by_successor": widened,
        })
        if widened:
            error = "recovery coordinate widened its predecessor's dirty-path authority"
            break
        current_allowed = prior_allowed
        reference = prior.get("supersedes") or None
    else:
        error = "supersession chain exceeds the bounded verification depth"
    return {
        "status": "INVALID" if error else ("CHAINED" if steps else "FOUNDING-ANCHOR"),
        "steps": steps,
        "error": error,
    }


def _find_direct_successors(
    root: Path,
    coordinate_relative: str,
    coordinate_digest: str,
) -> dict[str, Any]:
    """Reverse the committed supersession edge without inventing a second registry.

    The forward edge remains authoritative.  This bounded directory scan merely lets a cold
    reader who lands on an immutable older artifact discover that a committed successor names
    its exact path and payload digest.
    """

    packet_dir = (root / coordinate_relative).parent
    valid: list[dict[str, str]] = []
    invalid: list[dict[str, str]] = []
    for candidate_path in sorted(packet_dir.glob("RECOVERY-COORDINATE*.json")):
        try:
            candidate_relative = candidate_path.resolve().relative_to(root).as_posix()
        except ValueError:
            continue
        if candidate_relative == coordinate_relative:
            continue
        try:
            candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        reference = candidate.get("supersedes") or {}
        if str(reference.get("path") or "") != coordinate_relative:
            continue
        if not _committed_file_exact(root, candidate_relative):
            invalid.append({"path": candidate_relative, "reason": "successor-not-committed-exact"})
            continue
        candidate_recorded = str(candidate.get("coordinate_payload_digest") or "")
        candidate_actual = canonical_payload_digest(candidate)
        if not candidate_recorded or candidate_recorded != candidate_actual:
            invalid.append({"path": candidate_relative, "reason": "successor-payload-invalid"})
            continue
        if str(reference.get("payload_digest") or "") != coordinate_digest:
            invalid.append({"path": candidate_relative, "reason": "predecessor-digest-mismatch"})
            continue
        valid.append({
            "path": candidate_relative,
            "payload_digest": candidate_recorded,
            "coordinate_id": str(candidate.get("coordinate_id") or ""),
            "coordinate_version": str(candidate.get("coordinate_version") or ""),
        })
    if invalid or len(valid) > 1:
        status = "INVALID"
    elif valid:
        status = "SUPERSEDED"
    else:
        status = "CURRENT-CANDIDATE"
    return {
        "status": status,
        "successors": valid,
        "invalid_claims": invalid,
        "bounded_scan": packet_dir.relative_to(root).as_posix(),
    }


def _verify_git(
    root: Path,
    expected: Mapping[str, Any],
    *,
    coordinate_path: str | None = None,
) -> dict[str, Any]:
    base = str(expected.get("head") or "")
    current = _git(root, "rev-parse", "HEAD").stdout.decode().strip()
    base_exists = bool(base) and _git(root, "cat-file", "-e", f"{base}^{{commit}}", check=False).returncode == 0
    ancestor = (
        base_exists
        and _git(root, "merge-base", "--is-ancestor", base, current, check=False).returncode == 0
    )
    declared_allowed_descendant = sorted(
        str(path) for path in expected.get("allowed_descendant_paths", ())
    )
    # A coordinate cannot declare source or its own verifier to be "packaging". The only
    # mechanically safe suffix is the exact coordinate blob being verified.
    allowed_descendant = [coordinate_path] if coordinate_path else declared_allowed_descendant
    committed_delta_paths: list[str] = []
    if ancestor and current != base:
        raw_delta = _git(root, "diff", "--name-only", "-z", f"{base}..{current}").stdout
        committed_delta_paths = sorted(
            path.decode("utf-8", errors="surrogateescape")
            for path in raw_delta.split(b"\0")
            if path
        )
    packaged = bool(committed_delta_paths) and set(committed_delta_paths).issubset(
        set(allowed_descendant)
    )
    relation = (
        "SAME"
        if current == base
        else ("PACKAGED" if ancestor and packaged else ("DESCENDANT" if ancestor else "DIVERGED"))
    )
    base_tree = None
    if base_exists:
        base_tree = _git(root, "rev-parse", f"{base}^{{tree}}").stdout.decode().strip()
    expected_tree = str(expected.get("tree") or "")
    dirty_paths, raw_status = _dirty_paths(root)
    allowed_dirty = sorted(str(path) for path in expected.get("restored_preexisting_dirty_paths", ()))
    dirty_classes = {path: _dirty_path_class(path) for path in dirty_paths}
    runtime_dirty = sorted(
        path for path, path_class in dirty_classes.items() if path_class.startswith("RUNTIME-")
    )
    # The recorded list is historical evidence only.  It cannot confer permission.  Unknown
    # dirt therefore remains blocking even when a candidate writes its name into the list.
    new_dirty = sorted(
        path for path, path_class in dirty_classes.items() if path_class == "UNCLASSIFIED"
    )
    missing_preexisting = sorted(set(allowed_dirty) - set(dirty_paths))
    authority_source_dirty = sorted(
        path for path, path_class in dirty_classes.items() if path_class == "AUTHORITY-SOURCE"
    )
    tracked_diff = _git(root, "diff", "--binary").stdout
    staged_diff = _git(root, "diff", "--cached", "--binary").stdout
    return {
        "base_head": base,
        "current_head": current,
        "relation": relation,
        "committed_delta_paths": committed_delta_paths,
        "allowed_descendant_paths": allowed_descendant,
        "declared_allowed_descendant_paths": declared_allowed_descendant,
        "base_tree_expected": expected_tree,
        "base_tree_actual": base_tree,
        "base_tree_exact": bool(expected_tree) and base_tree == expected_tree,
        "dirty_paths": dirty_paths,
        "dirty_path_classes": dirty_classes,
        "runtime_derived_dirty_paths": runtime_dirty,
        "allowed_preexisting_dirty_paths": allowed_dirty,
        "new_dirty_paths": new_dirty,
        "missing_preexisting_dirty_paths": missing_preexisting,
        "authority_source_dirty_paths": authority_source_dirty,
        "coordinate_committed_exact": (
            _committed_file_exact(root, coordinate_path) if coordinate_path else None
        ),
        "status_nul_sha256": _sha256(raw_status),
        "status_shape_exact": _sha256(raw_status)
        == str(expected.get("status_nul_sha256_before_coordinate") or ""),
        "tracked_diff_sha256": _sha256(tracked_diff),
        "tracked_diff_exact": _sha256(tracked_diff)
        == str(expected.get("tracked_diff_sha256_before_coordinate") or ""),
        "staged_diff_sha256": _sha256(staged_diff),
        "staged_diff_exact": _sha256(staged_diff)
        == str(expected.get("staged_diff_sha256_before_coordinate") or ""),
    }


def _canonical_chash(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return _sha256(encoded)


def _authority_tip(checkpoint: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "atlas.conceptric-drift-token/1",
        "cursor": int(checkpoint.get("cursor") or 0),
        "head_event_id": checkpoint.get("head_event_id"),
        "head_record_digest": checkpoint.get("head_record_digest"),
    }


def _checked_authority_epoch(epoch: Mapping[str, Any]) -> dict[str, Any]:
    """Refuse every authority face weaker than the bounded C2a checkpoint contract."""

    if epoch.get("status") != "CURRENT":
        raise ValueError("canonical authority epoch is not CURRENT")
    integrity = epoch.get("integrity_boundary") or {}
    if integrity.get("status") != _AUTHORITY_INTEGRITY_BOUNDARY:
        raise ValueError("canonical authority epoch has the wrong integrity boundary")
    crutch = epoch.get("crutch") or {}
    if crutch.get("crutch_id") != _AUTHORITY_CRUTCH_ID:
        raise ValueError("canonical authority epoch has the wrong rollback crutch")
    rollback = epoch.get("rollback") or {}
    if rollback.get("status") != "CRUTCH" or not rollback.get("predicate"):
        raise ValueError("canonical authority epoch omits its stopped-writer rollback predicate")

    checkpoint_raw = epoch.get("effective_checkpoint")
    checkpoint = dict(checkpoint_raw) if isinstance(checkpoint_raw, Mapping) else {}
    try:
        checkpoint_cursor = int(checkpoint["cursor"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("canonical authority epoch omits its effective cursor") from exc
    if checkpoint_cursor < 0:
        raise ValueError("canonical authority epoch omits its effective cursor")
    if not str(checkpoint.get("head_event_id") or "").startswith("sha256:"):
        raise ValueError("canonical authority epoch omits its effective event head")
    if not str(checkpoint.get("head_record_digest") or "").startswith("sha256:"):
        raise ValueError("canonical authority epoch omits its effective record head")
    expected_digest = _canonical_chash(checkpoint)
    if epoch.get("effective_checkpoint_digest") != expected_digest:
        raise ValueError("canonical authority effective checkpoint digest does not verify")
    stored_checkpoint = epoch.get("checkpoint")
    if not isinstance(stored_checkpoint, Mapping):
        raise ValueError("canonical authority epoch omits its checkpoint")
    if epoch.get("checkpoint_digest") != _canonical_chash(stored_checkpoint):
        raise ValueError("canonical authority checkpoint digest does not verify")
    if dict(stored_checkpoint) != checkpoint:
        raise ValueError("canonical authority checkpoint and effective checkpoint disagree")

    authority = checkpoint.get("authority")
    if not isinstance(authority, Mapping) or any(
        key not in authority for key in ("active_context", "seat_occupancy", "recipient_mail")
    ):
        raise ValueError("canonical authority checkpoint omits a required live-authority root")
    metrics = epoch.get("read_metrics") or {}
    if metrics.get("global_history_replayed") is not False:
        raise ValueError("canonical authority epoch replayed global history")
    suffix_rows = int(metrics.get("suffix_rows_loaded") or 0)
    tail_limit = int(metrics.get("authority_tail_limit") or 0)
    if not (
        0 <= suffix_rows <= tail_limit
        and tail_limit == _AUTHORITY_TAIL_LIMIT
    ):
        raise ValueError("canonical authority suffix exceeds the C2a verification bound")
    return checkpoint


def _verify_runtime(
    expected: Mapping[str, Any], authority_epoch: Mapping[str, Any]
) -> dict[str, Any]:
    from laplace.representation import atlas_bridge

    checkpoint = _checked_authority_epoch(authority_epoch)
    live = _authority_tip(checkpoint)
    expected_cursor = int(expected.get("cursor") or 0)
    database = atlas_bridge.store_root() / "conceptric.sqlite3"
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    try:
        row = connection.execute(
            "SELECT event_id, record_digest FROM events WHERE sequence = ?", (expected_cursor,)
        ).fetchone()
    finally:
        connection.close()
    historical_exact = bool(row) and (
        str(row["event_id"]) == str(expected.get("head_event_id") or "")
        and str(row["record_digest"]) == str(expected.get("head_record_digest") or "")
    )
    live_cursor = int(live.get("cursor") or 0)
    if live_cursor < expected_cursor:
        relation = "REGRESSED"
    elif not historical_exact:
        relation = "DIVERGED"
    elif live_cursor == expected_cursor:
        relation = "SAME"
    else:
        relation = "DESCENDANT"
    context = dict(checkpoint["authority"].get("active_context") or {})
    return {
        "expected": dict(expected),
        "live": live,
        "relation": relation,
        "historical_token_exact": historical_exact,
        "active_context": context,
        "active_fibre_changed": context.get("fibre") != expected.get("active_fibre"),
    }


def _canonical_map_digest(value: Mapping[str, Any]) -> str:
    return _sha256(
        (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode(
            "utf-8"
        )
    )


def _file_digest(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _semantic_leaf_projection(leaf: Mapping[str, Any]) -> dict[str, Any]:
    projection = {
        "kind": leaf.get("kind", "file"),
        "essence": leaf.get("essence", ""),
        "keywords": list(leaf.get("keywords") or ()),
        "sealed": bool(leaf.get("sealed", False)),
    }
    if leaf.get("projection"):
        projection["projection"] = dict(leaf["projection"])
    if leaf.get("status"):
        projection["status"] = leaf["status"]
    return projection


def _graded_leaf_projection(node: Mapping[str, Any]) -> dict[str, Any]:
    route = node.get("route_handle") or node
    projection = {
        "kind": node.get("kind", "file"),
        "essence": route.get("essence", ""),
        "keywords": list(route.get("keywords") or ()),
        "sealed": bool(route.get("sealed", False)),
    }
    if node.get("projection"):
        projection["projection"] = dict(node["projection"])
    if node.get("status"):
        projection["status"] = node["status"]
    return projection


def _semantic_post_lock(root: Path) -> dict[str, Any]:
    """Reconstruct the fold dependency frontier and lock it to its served artifacts.

    This is the first forward-facing closure seam: it judges the inputs the semantic operator
    actually consumes, rather than the last Git commit that happened to touch its output files.
    The predecessor half of the transition remains declared bootstrap debt until deposits bank
    typed pre/post acts (``CR-semantic-fold-post-lock-without-predecessor``).
    """

    from laplace.engine import keeper, meaning_upfold
    from laplace.representation.embed_router import TEXT_CAP

    tree_path = root / ".meaning_tree.json"
    graded_path = root / ".self_graded.json"
    try:
        tree = json.loads(tree_path.read_text(encoding="utf-8"))
        graded = json.loads(graded_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        return {
            "schema_version": "laplace.semantic-post-lock/1",
            "status": "INVALID",
            "reason": f"semantic artifact cannot be decoded: {type(exc).__name__}: {exc}",
        }
    if not isinstance(tree, dict) or not isinstance(graded, dict):
        return {
            "schema_version": "laplace.semantic-post-lock/1",
            "status": "INVALID",
            "reason": "semantic artifacts are not object maps",
        }

    leaves, _lens_parent, residue, lens_hash, lens_pairs = keeper.semantic_input_frame(root)
    backend_name = str(tree.get("version") or "")
    if not backend_name:
        return {
            "schema_version": "laplace.semantic-post-lock/1",
            "status": "INVALID",
            "reason": "meaning tree omits its embedding basis",
        }
    current_residue_sha = {
        name: meaning_upfold._text_sha(
            backend_name,
            meaning_upfold._embeddable_text(root, name, residue[name], TEXT_CAP),
        )
        for name in sorted(residue)
    }
    recorded_residue_sha = tree.get("leaf_sha") or {}
    current_leaf_projection = {
        name: _semantic_leaf_projection(leaves[name]) for name in sorted(leaves)
    }
    stored_input_ids = {
        name
        for name, node in graded.items()
        if not name.startswith("concept::")
        and isinstance(node, Mapping)
        and (node.get("leaf") is True or bool(node.get("route_handle")))
    }
    stored_leaf_projection = {
        name: _graded_leaf_projection(graded[name])
        for name in sorted(stored_input_ids)
    }
    current_ids = set(current_leaf_projection)
    missing_ids = sorted(current_ids - stored_input_ids)
    stale_ids = sorted(stored_input_ids - current_ids)
    changed_ids = sorted(
        name
        for name in current_ids & stored_input_ids
        if current_leaf_projection[name] != stored_leaf_projection[name]
    )
    meaning_added = sorted(set(current_residue_sha) - set(recorded_residue_sha))
    meaning_removed = sorted(set(recorded_residue_sha) - set(current_residue_sha))
    meaning_changed = sorted(
        name
        for name in set(current_residue_sha) & set(recorded_residue_sha)
        if current_residue_sha[name] != recorded_residue_sha[name]
    )
    lens_exact = (
        tree.get("lens_hash") == lens_hash
        and list(tree.get("lens_pairs") or ()) == lens_pairs
    )
    handles_exact = not (missing_ids or stale_ids or changed_ids)
    meaning_exact = not (meaning_added or meaning_removed or meaning_changed)
    input_frontier = {
        "leaf_count": len(current_leaf_projection),
        "leaf_projection_digest": _canonical_map_digest(current_leaf_projection),
        "residue_count": len(current_residue_sha),
        "residue_leaf_sha_digest": _canonical_map_digest(current_residue_sha),
        "lens_hash": lens_hash,
        "lens_pair_count": len(lens_pairs),
    }
    post_artifacts = {
        "meaning_tree_sha256": _file_digest(tree_path),
        "self_graded_sha256": _file_digest(graded_path),
    }
    post_lock = _canonical_map_digest(
        {"input_frontier": input_frontier, "post_artifacts": post_artifacts}
    )
    return {
        "schema_version": "laplace.semantic-post-lock/1",
        "status": "CURRENT" if meaning_exact and lens_exact and handles_exact else "STALE",
        "post_lock": post_lock,
        "input_frontier": input_frontier,
        "post_artifacts": post_artifacts,
        "meaning_leaf_frontier_exact": meaning_exact,
        "lens_membership_exact": lens_exact,
        "graded_leaf_handles_exact": handles_exact,
        "delta": {
            "meaning_added": meaning_added[:20],
            "meaning_removed": meaning_removed[:20],
            "meaning_changed": meaning_changed[:20],
            "graded_missing": missing_ids[:20],
            "graded_stale": stale_ids[:20],
            "graded_changed": changed_ids[:20],
            "truncated": any(
                len(items) > 20
                for items in (
                    meaning_added,
                    meaning_removed,
                    meaning_changed,
                    missing_ids,
                    stale_ids,
                    changed_ids,
                )
            ),
        },
        "claim_boundary": (
            "exact current input frontier and post artifacts; predecessor transition act not yet banked"
        ),
    }


def _verify_semantic(root: Path, expected: Mapping[str, Any]) -> dict[str, Any]:
    folded = _git(root, "log", "-1", "--format=%H", "--", *SEMANTIC_FOLD_PATHS).stdout.decode().strip()
    current = _git(root, "rev-parse", "HEAD").stdout.decode().strip()
    ancestor = bool(folded) and _git(
        root, "merge-base", "--is-ancestor", folded, current, check=False
    ).returncode == 0
    behind = None
    if ancestor:
        behind = int(_git(root, "rev-list", "--count", f"{folded}..{current}").stdout)
    live_lock = _semantic_post_lock(root)
    recorded_lock = str(expected.get("post_lock") or "")
    lock_exact = bool(recorded_lock) and recorded_lock == live_lock.get("post_lock")
    if live_lock.get("status") == "INVALID":
        status = "DIVERGED"
    elif live_lock.get("status") == "STALE":
        status = "STALE"
    else:
        status = "CURRENT"
    return {
        "folded_git_head": folded or None,
        "recorded_folded_git_head": expected.get("folded_git_head"),
        "fold_origin_exact": lock_exact,
        "current_git_head": current,
        "fold_is_ancestor": ancestor,
        "commits_behind": behind,
        "status": status,
        "post_lock": live_lock.get("post_lock"),
        "recorded_post_lock": recorded_lock or None,
        "post_lock_exact": lock_exact,
        "frontier": live_lock,
        "git_provenance_only": True,
    }


def _verify_blueprint(expected: Mapping[str, Any]) -> dict[str, Any]:
    from laplace.representation import atlas_bridge

    projection = atlas_bridge.blueprint_projection(materialization_limit=0, result_limit=1)
    generation_id = str(projection.get("generation_id") or "")
    recorded_generation_id = str(expected.get("generation_id") or "")
    completion_history = tuple(projection.get("generation_completion_history") or ())
    historical_generation_ids = [
        str(row.get("generation_id") or "") for row in completion_history
    ]
    current_completion = completion_history[-1] if completion_history else None
    recorded_completion = next(
        (
            row
            for row in reversed(completion_history)
            if str(row.get("generation_id") or "") == recorded_generation_id
        ),
        None,
    )
    completion_history_exact = bool(completion_history) and (
        historical_generation_ids[-1] == generation_id
    )
    if recorded_generation_id == generation_id and completion_history_exact:
        generation_relation = "SAME"
    elif recorded_generation_id in historical_generation_ids and completion_history_exact:
        # Temporal order is a declared scaffold, not a substitute for explicit RevisionAct
        # topology.  See CR-blueprint-generation-append-order-currentness.
        generation_relation = "DESCENDANT"
    else:
        generation_relation = "DIVERGED"
    moved_paths = sorted(str(row.get("path")) for row in projection.get("moved_source_roots", ()))
    recorded_paths = sorted(str(path) for path in expected.get("moved_source_roots", ()))
    return {
        "generation_id": generation_id,
        "recorded_generation_id": recorded_generation_id,
        "generation_exact": generation_relation == "SAME",
        "generation_relation": generation_relation,
        "completion_history_exact": completion_history_exact,
        "completion_history_count": len(completion_history),
        "recorded_completion": recorded_completion,
        "current_completion": current_completion,
        "generation_relation_basis": "append-only-completion-order-scaffold",
        "pour_handle": projection.get("pour_handle"),
        "recorded_pour_handle": expected.get("pour_handle"),
        "pour_exact": projection.get("pour_handle") == expected.get("pour_handle"),
        "current": projection.get("current") is True,
        "recorded_current": expected.get("current_against_worktree") is True,
        "moved_source_roots": moved_paths,
        "recorded_moved_source_roots": recorded_paths,
        "moved_root_set_exact": moved_paths == recorded_paths,
        "counts": projection.get("counts"),
    }


def _contact_event_errors(
    event: Mapping[str, Any] | None,
    *,
    event_kind: str,
    seat_id: str,
    contact: Mapping[str, Any],
) -> list[str]:
    """Verify one occupancy event against the contact fields it is claimed to prove."""

    if not event:
        return [f"{event_kind} event does not resolve in canonical Atlas history"]
    errors: list[str] = []
    if event.get("kind") != event_kind:
        errors.append(f"event kind is {event.get('kind')}, not {event_kind}")
    payload = event.get("payload") or {}
    expected_subject = (
        f"seat:{seat_id}:binding"
        if event_kind == "seat.occupancy-bound"
        else f"seat:{seat_id}:occupancy"
    )
    if event.get("subject") != expected_subject:
        errors.append("event subject belongs to another seat or transition")
    if event.get("actor") != contact.get("function"):
        errors.append("event actor disagrees with the contact function")
    if payload.get("seat_id") != seat_id:
        errors.append("event payload belongs to another logical seat")
    if payload.get("function") != contact.get("function"):
        errors.append("event payload function disagrees with the contact")
    if event_kind == "seat.occupancy-bound":
        comparisons = {
            "provider_session_ref": "provider_session_ref",
            "registered_principal_ref": "registered_principal_ref",
            "provider_identity_proof_handle": "provider_identity_proof_handle",
            "join_event_id": "join_event_id",
        }
        for payload_field, contact_field in comparisons.items():
            if payload.get(payload_field) != contact.get(contact_field):
                errors.append(f"binding payload disagrees on {payload_field}")
        if contact.get("join_event_id") not in (event.get("causation_ids") or ()):
            errors.append("binding event does not causally carry the claimed join")
    else:
        comparisons = {
            "holder_ref": "provider_session_ref",
            "registered_holder_ref": "registered_principal_ref",
            "information_proof_handle": "provider_identity_proof_handle",
            "mail_state": "mail_state",
        }
        for payload_field, contact_field in comparisons.items():
            if payload.get(payload_field) != contact.get(contact_field):
                errors.append(f"join payload disagrees on {payload_field}")
    return errors


def _verify_live_contact(
    expected: Mapping[str, Any],
    *,
    authority_epoch: Mapping[str, Any] | None = None,
    derived_from_verification: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compare a recovery contact projection with the latest exact Atlas occupancy.

    The pre-v5 coordinate carried prose handshake claims.  That shape is not corruption, but it
    can never be current: it is a one-way migration input whose axis must be superseded.  Typed
    successors bind every required logical seat to the current occupancy event and detect later
    replacement without confusing lawful succession with divergence.
    """

    if expected.get("schema_version") != "atlas.recovery-live-contact/1":
        return {
            "status": "LEGACY-UNVERIFIABLE",
            "relation": "UNKNOWN",
            "current": False,
            "reason": "live contact predates typed occupancy projection",
            "recorded": dict(expected),
            "seats": {},
        }

    from laplace.representation import atlas_bridge

    required_seats = tuple(str(item) for item in expected.get("required_seats") or ())
    recorded_seats = expected.get("seats") or {}
    if not required_seats or sorted(recorded_seats) != sorted(required_seats):
        return {
            "status": "INVALID",
            "relation": "DIVERGED",
            "current": False,
            "reason": "typed live contact does not exactly cover its required seats",
            "recorded": dict(expected),
            "seats": {},
        }
    derived_from = expected.get("derived_from") or {}
    if authority_epoch is None:
        raise ValueError("typed live contact requires one shared canonical authority epoch")
    checkpoint = _checked_authority_epoch(authority_epoch)
    derived = (
        dict(derived_from_verification)
        if derived_from_verification is not None
        else _verify_runtime(derived_from, authority_epoch)
        if derived_from
        else {"historical_token_exact": False, "relation": "DIVERGED"}
    )
    if (
        not derived_from
        or not derived.get("historical_token_exact")
        or derived.get("relation") not in {"SAME", "DESCENDANT"}
    ):
        return {
            "status": "INVALID",
            "relation": "DIVERGED",
            "current": False,
            "reason": "typed live contact does not descend from an exact historical Atlas token",
            "recorded": dict(expected),
            "derived_from_verification": derived,
            "seats": {},
        }

    occupancy = checkpoint["authority"].get("seat_occupancy") or {}
    event_ids: list[str] = []
    for seat_id in required_seats:
        recorded = recorded_seats.get(seat_id) or {}
        current = occupancy.get(seat_id) or {}
        event_ids.extend(
            str(event_id)
            for event_id in (
                recorded.get("join_event_id"),
                recorded.get("binding_event_id"),
                current.get("join_event_id"),
                current.get("binding_event_id"),
            )
            if event_id
        )
    event_ids = list(dict.fromkeys(event_ids))
    history = atlas_bridge.event_history_projection(event_ids)
    history_events = history.get("events") or {}
    derived_cursor = int(derived_from.get("cursor") or 0)
    seats: dict[str, dict[str, Any]] = {}
    relations: list[str] = []
    compared_fields = (
        "function",
        "provider_session_ref",
        "registered_principal_ref",
        "provider_identity_proof_handle",
    )
    for seat_id in required_seats:
        recorded = recorded_seats.get(seat_id) or {}
        current = occupancy.get(seat_id) or {}
        current_join = current.get("join") or {}
        binding = current.get("binding") or {}
        recorded_binding_event = str(recorded.get("binding_event_id") or "")
        current_binding_event = str(current.get("binding_event_id") or "")
        recorded_join_event = str(recorded.get("join_event_id") or "")
        current_join_event = str(current.get("join_event_id") or "")
        recorded_binding_row = history_events.get(recorded_binding_event)
        recorded_join_row = history_events.get(recorded_join_event)
        current_contact = {
            "function": binding.get("function"),
            "provider_session_ref": binding.get("provider_session_ref"),
            "registered_principal_ref": binding.get("registered_principal_ref"),
            "provider_identity_proof_handle": binding.get(
                "provider_identity_proof_handle"
            ),
            "mail_state": current_join.get("mail_state"),
            "join_event_id": current_join_event,
        }
        history_errors = _contact_event_errors(
            recorded_binding_row,
            event_kind="seat.occupancy-bound",
            seat_id=seat_id,
            contact=recorded,
        ) + _contact_event_errors(
            recorded_join_row,
            event_kind="seat.joined",
            seat_id=seat_id,
            contact=recorded,
        )
        recorded_binding_sequence = int((recorded_binding_row or {}).get("sequence") or 0)
        recorded_join_sequence = int((recorded_join_row or {}).get("sequence") or 0)
        if recorded_join_sequence >= recorded_binding_sequence:
            history_errors.append("recorded join is not causally before its binding")
        if recorded_binding_sequence > derived_cursor:
            history_errors.append("recorded binding lies after the contact's derived_from token")
        if (
            recorded.get("state") != "BOUND"
            or recorded.get("routing_authority") is not True
            or recorded.get("mail_state") != "MAIL_READY"
        ):
            relation = "DIVERGED"
            reason = "recorded contact carries an invalid bound/routing/mail claim"
        elif not recorded_binding_event:
            relation = "DIVERGED"
            reason = "recorded contact omits its exact binding event"
        elif history_errors:
            relation = "DIVERGED"
            reason = "recorded predecessor contact is not exact canonical Atlas history"
        elif (
            current.get("state") != "BOUND"
            or current.get("routing_authority") is not True
            or not binding
        ):
            relation = "UNAVAILABLE"
            reason = "required seat is no longer bound with routing authority"
        else:
            current_history_errors = _contact_event_errors(
                history_events.get(current_binding_event),
                event_kind="seat.occupancy-bound",
                seat_id=seat_id,
                contact=current_contact,
            ) + _contact_event_errors(
                history_events.get(current_join_event),
                event_kind="seat.joined",
                seat_id=seat_id,
                contact=current_contact,
            )
            current_binding_sequence = int(
                (history_events.get(current_binding_event) or {}).get("sequence") or 0
            )
            if current_binding_event != recorded_binding_event:
                if current_binding_sequence <= recorded_binding_sequence:
                    current_history_errors.append(
                        "replacement binding is not later than the recorded binding"
                    )
                if current_history_errors:
                    relation = "DIVERGED"
                    reason = "current replacement is not exact later Atlas occupancy history"
                else:
                    relation = "DESCENDANT"
                    reason = "required seat has a later exact lawful occupancy binding"
            elif current_history_errors:
                relation = "DIVERGED"
                reason = "current occupancy projection contradicts its exact Atlas events"
            else:
                relation = "SAME"
                reason = "recorded contact is the latest exact occupancy binding"
            if current_binding_event == recorded_binding_event:
                mismatched = [
                    field
                    for field in compared_fields
                    if recorded.get(field) != binding.get(field)
                ]
                if recorded.get("join_event_id") != current.get("join_event_id"):
                    mismatched.append("join_event_id")
                if recorded.get("mail_state") != current_join.get("mail_state"):
                    mismatched.append("mail_state")
                if mismatched:
                    relation = "DIVERGED"
                    reason = "same binding event resolves to different contact fields"
        relations.append(relation)
        seats[seat_id] = {
            "relation": relation,
            "reason": reason,
            "recorded_binding_event_id": recorded_binding_event or None,
            "current_binding_event_id": current_binding_event or None,
            "recorded_provider_session_ref": recorded.get("provider_session_ref"),
            "current_provider_session_ref": binding.get("provider_session_ref"),
            "recorded_history_errors": history_errors,
        }
    if "DIVERGED" in relations:
        status, relation = "INVALID", "DIVERGED"
    elif "UNAVAILABLE" in relations:
        status, relation = "CHANGED", "UNAVAILABLE"
    elif "DESCENDANT" in relations:
        status, relation = "CHANGED", "DESCENDANT"
    else:
        status, relation = "SAME", "SAME"
    result = {
        "status": status,
        "relation": relation,
        "current": status == "SAME",
        "required_seats": list(required_seats),
        "seats": seats,
        "derived_from_verification": derived,
        "history_projection": {
            "requested_event_ids": history.get("requested_event_ids"),
            "missing_event_ids": history.get("missing_event_ids"),
            "proof_boundary": history.get("proof_boundary"),
        },
        "claim_boundary": expected.get("claim_boundary"),
        "observation_tip": _authority_tip(checkpoint),
    }
    return result


def _inline_fabric_ids(document: Mapping[str, Any]) -> list[str]:
    return sorted(
        str(message_id)
        for seat in (document.get("by_seat") or {}).values()
        for message_id in (seat.get("message_ids") or ())
    )


def _expanded_fabric_ids(
    expected: Mapping[str, Any], root: Path
) -> tuple[list[str], list[str], str, str | None]:
    """Resolve the coordinate's exact debt identities without consulting live Fabric.

    The founding coordinate carries the expanded set inline. Compact successors carry an
    immutable source plus an exact add/remove delta. Legacy digest-only successors remain
    verifiable by count and set digest, but cannot name individual movement.
    """

    inline = _inline_fabric_ids(expected)
    if inline:
        return inline, inline, "inline-expanded-ids", None
    source_ref = expected.get("expanded_identity_source") or {}
    source_name = str(source_ref.get("path") or "")
    source_digest = str(source_ref.get("payload_digest") or "")
    if not source_name:
        return [], [], "count-and-set-digest", None
    try:
        source_path = (root / source_name).resolve()
        source_path.relative_to(root)
        source = json.loads(source_path.read_text(encoding="utf-8"))
        actual = canonical_payload_digest(source)
        if not source_digest or actual != source_digest:
            raise ValueError("expanded identity source digest mismatch")
        base = _inline_fabric_ids(source.get("fabric_debt") or {})
        if not base and int((source.get("fabric_debt") or {}).get("total") or 0):
            raise ValueError("expanded identity source does not contain its message ids")
        delta = expected.get("identity_delta") or {}
        added = {str(mid) for mid in (delta.get("added_message_ids") or ())}
        resolved = {str(mid) for mid in (delta.get("resolved_message_ids") or ())}
        if added & resolved:
            raise ValueError("fabric identity delta both adds and resolves the same id")
        identities = sorted((set(base) - resolved) | added)
        return identities, base, "expanded-source-plus-delta", None
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [], [], "expanded-source-invalid", f"{type(exc).__name__}: {exc}"


def _verify_fabric(
    expected: Mapping[str, Any],
    repo_root: Path | str = REPO_ROOT,
    *,
    authority_epoch: Mapping[str, Any],
) -> dict[str, Any]:
    checkpoint = _checked_authority_epoch(authority_epoch)
    recipients = checkpoint["authority"].get("recipient_mail") or {}
    by_seat: dict[str, list[tuple[int, str, str]]] = {}
    for recipient_seat, recipient in recipients.items():
        for message_id, record in (recipient.get("pending") or {}).items():
            message = record.get("message") or {}
            seat = str(message.get("recipient_seat_id") or "")
            message_state = str(record.get("status") or "")
            if (
                str(message.get("message_id") or "") != str(message_id)
                or seat != str(recipient_seat)
                or message_state not in {"queued", "pulled"}
            ):
                raise ValueError("canonical recipient-mail checkpoint contains an invalid row")
            by_seat.setdefault(seat, []).append(
                (int(message.get("cursor") or 0), str(message_id), message_state)
            )
    ids = sorted(message_id for rows in by_seat.values() for _cursor, message_id, _state in rows)
    recorded_ids, expanded_source_ids, comparison, source_error = _expanded_fabric_ids(
        expected, Path(repo_root).resolve()
    )
    current_digest = _hash_lines(ids)
    recorded_digest = str(expected.get("all_message_ids_sorted_sha256") or "")
    has_expanded_ids = comparison in {"inline-expanded-ids", "expanded-source-plus-delta"}
    same = source_error is None and (
        ids == recorded_ids if has_expanded_ids else (
            len(ids) == int(expected.get("total") or 0)
            and bool(recorded_digest)
            and current_digest == recorded_digest
        )
    )
    seat_projection = {}
    for seat, rows in sorted(by_seat.items()):
        ordered_rows = sorted(rows)
        ordered = [message_id for _cursor, message_id, _state in ordered_rows]
        seat_projection[seat] = {
            "count": len(ordered),
            "queued": sum(state == "queued" for _cursor, _mid, state in ordered_rows),
            "pulled": sum(state == "pulled" for _cursor, _mid, state in ordered_rows),
            "message_ids": ordered,
        }
    return {
        "status": "SOURCE-INVALID" if source_error else ("SAME" if same else "CHANGED"),
        "total": len(ids),
        "recorded_total": expected.get("total"),
        "message_ids_sha256": current_digest,
        "recorded_message_ids_sha256": recorded_digest or None,
        "comparison": comparison,
        "recorded_message_ids": recorded_ids,
        "expanded_source_message_ids": expanded_source_ids,
        "identity_source_error": source_error,
        "added": sorted(set(ids) - set(recorded_ids)) if has_expanded_ids else None,
        "resolved_or_changed": (
            sorted(set(recorded_ids) - set(ids)) if has_expanded_ids else None
        ),
        "by_seat": seat_projection,
    }


def _verify_authority_axes(
    document: Mapping[str, Any],
    *,
    repo_root: Path,
    max_attempts: int = _AUTHORITY_ATTEMPTS,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Read one C2a epoch per attempt and refuse a bundle assembled across tips."""

    from laplace.representation import atlas_bridge

    if max_attempts not in (1, 2):
        raise ValueError("authority observation supports one attempt and at most one retry")
    freshness = document.get("freshness_vector") or {}
    for attempt in range(1, max_attempts + 1):
        epoch = atlas_bridge.authority_epoch()
        checkpoint = _checked_authority_epoch(epoch)
        runtime = _verify_runtime(freshness.get("runtime_atlas") or {}, epoch)
        live_contact = _verify_live_contact(
            document.get("live_contact") or {},
            authority_epoch=epoch,
            derived_from_verification=runtime,
        )
        fabric = _verify_fabric(
            document.get("fabric_debt") or {},
            repo_root,
            authority_epoch=epoch,
        )
        before = _authority_tip(checkpoint)
        after = _authority_tip(atlas_bridge.drift_token())
        stable = before == after
        observation = {
            "status": "STABLE" if stable else "MOVED-DURING-OBSERVATION",
            "before": before,
            "after": after,
            "attempts": attempt,
            "checkpoint_digest": epoch["checkpoint_digest"],
            "effective_checkpoint_digest": epoch["effective_checkpoint_digest"],
            "read_metrics": dict(epoch["read_metrics"]),
            "rollback": dict(epoch["rollback"]),
            "integrity_boundary": dict(epoch["integrity_boundary"]),
            "crutch": dict(epoch["crutch"]),
        }
        if stable or attempt == max_attempts:
            if not stable and live_contact.get("relation") != "DIVERGED":
                live_contact.update({
                    "status": "CHANGED",
                    "relation": "MOVED-DURING-OBSERVATION",
                    "current": False,
                    "reason": (
                        "Atlas moved while the shared authority axes were assembled; no "
                        "shared-tip live-contact verdict is available"
                    ),
                })
            return runtime, live_contact, fabric, observation
    raise AssertionError("authority observation attempt loop did not return")


def verify_coordinate(
    path: Path | str = DEFAULT_COORDINATE,
    *,
    repo_root: Path | str = REPO_ROOT,
    include_blueprint: bool = True,
) -> dict[str, Any]:
    coordinate_path = Path(path).resolve()
    root = Path(repo_root).resolve()
    try:
        coordinate_relative = coordinate_path.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError("recovery coordinate must be inside the repository authority root") from exc
    document = json.loads(coordinate_path.read_text(encoding="utf-8"))
    recorded_digest = str(document.get("coordinate_payload_digest") or "")
    actual_digest = canonical_payload_digest(document)
    currentness = _find_direct_successors(root, coordinate_relative, actual_digest)
    freshness = document.get("freshness_vector") or {}
    git = _verify_git(root, freshness.get("git") or {}, coordinate_path=coordinate_relative)
    authority_chain = _verify_allowlist_chain(document, root)
    runtime_recovery = _verify_runtime_recovery_coordinate_claim(document)
    semantic = _verify_semantic(root, freshness.get("semantic_fold") or {})
    blueprint = (
        _verify_blueprint(freshness.get("blueprint") or {})
        if include_blueprint
        else {"status": "UNMEASURED", "reason": "--skip-blueprint"}
    )
    runtime, live_contact, fabric, authority_observation = _verify_authority_axes(
        document, repo_root=root
    )
    authority_stable = authority_observation["status"] == "STABLE"

    hard_reds: list[str] = []
    if actual_digest != recorded_digest:
        hard_reds.append("coordinate payload digest mismatch")
    if git["relation"] == "DIVERGED" or not git["base_tree_exact"]:
        hard_reds.append("Git base is not the recorded exact ancestor")
    if git["new_dirty_paths"]:
        hard_reds.append("worktree contains dirty paths absent from the recorded recovery set")
    if git["authority_source_dirty_paths"]:
        hard_reds.append("worktree contains dirty source or authority paths")
    if git["coordinate_committed_exact"] is not True:
        hard_reds.append("recovery coordinate is not exact against its committed Git blob")
    if authority_chain["status"] == "INVALID":
        hard_reds.append("recovery coordinate dirty-path authority chain is invalid")
    if currentness["status"] == "INVALID":
        hard_reds.append("recovery coordinate supersession currentness is ambiguous or invalid")
    if runtime_recovery["status"] == "INVALID":
        hard_reds.append("runtime recovery point or external grant is invalid")
    if runtime["relation"] in {"REGRESSED", "DIVERGED"}:
        hard_reds.append("live Atlas is not an exact descendant of the recorded runtime token")
    if semantic["status"] == "DIVERGED":
        hard_reds.append("semantic fold artifacts or dependency frontier are invalid")
    if include_blueprint and blueprint.get("generation_relation") == "DIVERGED":
        hard_reds.append("recorded blueprint generation is absent from exact completion history")
    if live_contact.get("relation") == "DIVERGED":
        hard_reds.append("recorded live contact contradicts its exact occupancy binding")
    if fabric.get("identity_source_error"):
        hard_reds.append("Fabric debt expanded identity source is invalid")
    if not authority_stable:
        hard_reds.append("Atlas moved while the recovery coordinate axes were assembled")

    moved_axes: list[str] = []
    if git["relation"] == "DESCENDANT":
        moved_axes.append("git")
    # The Fabric is alive: ordinary append-only traffic must not force a coordinate rewrite on
    # every event.  Historical-token exactness proves the suffix.  A context transport is the
    # semantic movement that requires a new coordinate.
    if runtime["active_fibre_changed"]:
        moved_axes.append("runtime_atlas")
    if not semantic["fold_origin_exact"]:
        moved_axes.append("semantic_fold")
    if include_blueprint and (
        blueprint.get("generation_relation") == "DESCENDANT"
        or blueprint.get("current") != blueprint.get("recorded_current")
        or not blueprint.get("moved_root_set_exact")
    ):
        moved_axes.append("blueprint")
    if live_contact.get("status") != "SAME":
        moved_axes.append("live_contact")
    if fabric["status"] != "SAME":
        moved_axes.append("fabric_debt")

    if hard_reds:
        live_axis_state = "INVALID"
    elif moved_axes:
        live_axis_state = "SUPERSESSION-REQUIRED"
    else:
        live_axis_state = "CURRENT-FOR-RECOVERY"
    coordinate_state = (
        "SUPERSEDED" if currentness["status"] == "SUPERSEDED" else live_axis_state
    )

    system_current = (
        not git["new_dirty_paths"]
        and not git["authority_source_dirty_paths"]
        and semantic["status"] == "CURRENT"
        and include_blueprint
        and blueprint.get("current") is True
        and live_contact.get("status") == "SAME"
        and fabric["total"] == 0
    )
    return {
        "schema_version": "atlas.recovery-coordinate-verification/1",
        "coordinate": {
            "path": coordinate_relative,
            "coordinate_id": document.get("coordinate_id"),
            "recorded_payload_digest": recorded_digest,
            "actual_payload_digest": actual_digest,
            "payload_integrity": actual_digest == recorded_digest,
        },
        "coordinate_state": coordinate_state,
        "live_axis_state": live_axis_state,
        "currentness": currentness,
        "system_state": "CURRENT" if system_current else "RECOVERY",
        "supersession_axes": sorted(set(moved_axes)),
        "hard_reds": hard_reds,
        "git": git,
        "authority_chain": authority_chain,
        "runtime_atlas": runtime,
        "runtime_recovery": runtime_recovery,
        "authority_observation": authority_observation,
        "semantic_fold": semantic,
        "blueprint": blueprint,
        "live_contact": live_contact,
        "fabric_debt": fabric,
        "custody_allowed": coordinate_state == "CURRENT-FOR-RECOVERY",
        "law": (
            "historical currentness, live-axis freshness, and system health are separate; "
            "a SUPERSEDED coordinate remains exact history but cannot grant custody, and any "
            "moved coordinate axis requires an explicit successor before custody moves"
        ),
    }
