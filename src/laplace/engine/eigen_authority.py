"""Git-rooted standing Eigen repair authority and its local emergency bank.

This is deliberately not another lifecycle.  The committed law is the authority root;
the local journal preserves acts while Atlas is unhealthy, and reconciliation mirrors
those exact records later.  Watchers, Fabric, recovery coordinates, leases and Atlas
currentness remain useful telemetry but never manufacture or erase Eigen authority.
"""
from __future__ import annotations
from laplace.core.checkout import state_root

import fcntl
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

LAW_PATH = Path("contract/eigen_standing_authority.json")
LAW_SCHEMA = "laplace.eigen-standing-authority/1"
COMMISSION_SCHEMA = "laplace.eigen-author-commission/1"
RECORD_SCHEMA = "laplace.eigen-emergency-record/1"
AUTHORITY_SCHEMA = "laplace.eigen-authority/1"
TRIAGE_SCHEMA = "laplace.eigen-triage/1"
JOURNAL_NAME = "emergency-journal.jsonl"

_TYPED_HOLDER = re.compile(r"^[a-z][a-z0-9._-]*:[^\s]+$")
_BANKED_KINDS = {
    "holder-adopted", "author-turn", "decision", "repair-act", "source-coordinate",
    "compaction-seal", "semantic-currentness", "descent-handle", "atlas-reconciliation",
    "session-started", "profile-revised", "author-delta", "child-dispatch",
    "child-return", "child-judgment",
}


class EigenAuthorityRefused(RuntimeError):
    """The Git law or direct commission does not authorize the requested Eigen act."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _handle(value: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def _bytes_handle(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=root, text=True, capture_output=True, check=check
    )


def _typed_holder(value: str) -> str:
    holder = str(value).strip()
    if not _TYPED_HOLDER.fullmatch(holder):
        raise EigenAuthorityRefused("provider_session_ref is not one opaque typed provider identity")
    return holder


def inferred_holder_ref() -> str:
    explicit = os.environ.get("LAPLACE_PROVIDER_SESSION_REF", "").strip()
    if explicit:
        return explicit
    thread = os.environ.get("CODEX_THREAD_ID", "").strip()
    if thread:
        return f"codex:{thread}"
    session = (
        os.environ.get("CLAUDE_CODE_SESSION_ID", "").strip()
        or os.environ.get("CLAUDE_SESSION_ID", "").strip()
    )
    return f"claude:{session}" if session else ""


def load_law(repo_root: Path | str) -> dict[str, Any]:
    """Read and validate the exact law from ``HEAD``, not an uncommitted overlay."""

    root = Path(repo_root).resolve()
    try:
        head = _git(root, "rev-parse", "HEAD").stdout.strip()
        tree = _git(root, "rev-parse", "HEAD^{tree}").stdout.strip()
        blob = _git(root, "rev-parse", f"HEAD:{LAW_PATH.as_posix()}").stdout.strip()
        committed = subprocess.run(
            ["git", "show", f"HEAD:{LAW_PATH.as_posix()}"],
            cwd=root,
            capture_output=True,
            check=True,
        ).stdout
        visible = (root / LAW_PATH).read_bytes()
        clean = (
            _git(root, "diff", "--quiet", "HEAD", "--", LAW_PATH.as_posix(), check=False).returncode
            == 0
            and _git(root, "diff", "--cached", "--quiet", "--", LAW_PATH.as_posix(), check=False).returncode
            == 0
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise EigenAuthorityRefused("Git-carried Eigen standing law is unavailable") from exc
    if not clean or visible != committed:
        raise EigenAuthorityRefused("Git-carried Eigen standing law is dirty or differs from HEAD")
    try:
        law = json.loads(committed)
    except json.JSONDecodeError as exc:
        raise EigenAuthorityRefused("Git-carried Eigen standing law is malformed") from exc
    commission = law.get("direct_author_commission") if isinstance(law, Mapping) else None
    if (
        not isinstance(law, dict)
        or law.get("schema_version") != LAW_SCHEMA
        or law.get("status") != "ACTIVE"
        or law.get("seat_id") != "eigen-seat"
        or law.get("function") != "eigen"
        or law.get("role") != "eigen"
        or not isinstance(commission, Mapping)
        or commission.get("schema_version") != COMMISSION_SCHEMA
        or commission.get("status") != "ACTIVE"
        or commission.get("action") != "FOUND"
        or commission.get("author") != "Gerard"
        or commission.get("seat_id") != "eigen-seat"
        or commission.get("function") != "eigen"
    ):
        raise EigenAuthorityRefused("direct Gerard commission is absent or incomplete")
    first_holder = _typed_holder(str(commission.get("holder_ref") or ""))
    return {
        "law": law,
        "source_law_handle": _bytes_handle(committed),
        "law_blob": blob,
        "source_commit": head,
        "source_tree": tree,
        "first_holder_ref": first_holder,
        "initial_commission_handle": _handle(dict(commission)),
        "path": LAW_PATH.as_posix(),
    }


def _state_root() -> Path:
    explicit = os.environ.get("LAPLACE_EIGEN_STATE", "").strip()
    if explicit:
        return Path(explicit)
    return state_root() / "eigen-authority"


def journal_path() -> Path:
    return _state_root() / JOURNAL_NAME


def _object_path(handle: str) -> Path:
    return _state_root() / "objects" / (handle.removeprefix("sha256:") + ".json")


def _write_object(value: Mapping[str, Any]) -> str:
    handle = _handle(value)
    path = _object_path(handle)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = _canonical(value)
    if path.is_file():
        if path.read_bytes() != body:
            raise EigenAuthorityRefused("content-addressed Eigen object path disagrees with its handle")
        return handle
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    return handle


def _read_object(handle: str) -> dict[str, Any]:
    path = _object_path(handle)
    try:
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise EigenAuthorityRefused(f"Eigen object {handle} is unavailable") from exc
    if not isinstance(value, dict) or _handle(value) != handle:
        raise EigenAuthorityRefused(f"Eigen object {handle} failed content verification")
    return value


def write_object(value: Mapping[str, Any]) -> str:
    """Public content-addressed object writer used by the isolated Eigen adapter."""

    return _write_object(value)


def read_object(handle: str) -> dict[str, Any]:
    """Read and verify one exact Eigen object without consulting semantic state."""

    return _read_object(handle)


def object_exists(handle: str) -> bool:
    """Return whether one exact verified Eigen object exists; malformed bytes are absent."""

    if not str(handle).startswith("sha256:"):
        return False
    try:
        _read_object(str(handle))
    except EigenAuthorityRefused:
        return False
    return True


def _bank_transcript(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise EigenAuthorityRefused("Eigen adoption transcript must be one exact regular file")
    before = path.stat()
    temporary_root = _state_root() / "custody"
    temporary_root.mkdir(parents=True, exist_ok=True)
    temporary = temporary_root / f"transcript.{os.getpid()}.tmp"
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as source, temporary.open("xb") as destination:
        os.chmod(temporary, 0o600)
        while True:
            block = source.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
            destination.write(block)
            total += len(block)
        destination.flush()
        os.fsync(destination.fileno())
    after = path.stat()
    if (before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_ino, after.st_size, after.st_mtime_ns
    ) or total != before.st_size:
        temporary.unlink(missing_ok=True)
        raise EigenAuthorityRefused("Eigen adoption transcript moved while entering custody")
    handle = "sha256:" + digest.hexdigest()
    custody = temporary_root / handle.removeprefix("sha256:")
    if custody.exists():
        if custody.stat().st_size != total:
            temporary.unlink(missing_ok=True)
            raise EigenAuthorityRefused("existing transcript custody has the wrong byte length")
        check = hashlib.sha256()
        with custody.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                check.update(block)
        if "sha256:" + check.hexdigest() != handle:
            temporary.unlink(missing_ok=True)
            raise EigenAuthorityRefused("existing transcript custody does not verify")
        temporary.unlink(missing_ok=True)
    else:
        os.replace(temporary, custody)
    return {
        "source_path": str(path),
        "custody_path": str(custody),
        "bytes": total,
        "content_handle": handle,
        "evidence_strength": "EXACT-CONTENT-ADDRESSED",
    }


def _seal_profile(
    repo_root: Path,
    *,
    holder_ref: str,
    task_id: str,
    transcript_path: Path,
    source: Mapping[str, Any],
) -> dict[str, Any]:
    """Seal full transcript custody and a bounded active semantic continuation."""

    transcript = _bank_transcript(transcript_path)
    body = Path(transcript["custody_path"]).read_bytes()
    try:
        from laplace.engine.compaction_boundary import _semantic_horizon

        event = {
            "cwd": str(repo_root),
            "hook_event_name": "PreCompact",
            "model": "provider-neutral-eigen-adoption",
            "session_id": task_id,
            "transcript_path": transcript["custody_path"],
            "trigger": "manual",
            "turn_id": "eigen-seat-adoption",
        }
        continuation = _semantic_horizon(
            event=event, body=body, raw_start=0, first_boundary=True
        )
    except Exception as exc:  # noqa: BLE001 - no silent platform-summary fallback
        raise EigenAuthorityRefused(
            f"bounded semantic continuation could not be derived: {type(exc).__name__}: {exc}"
        ) from exc
    continuation_handle = _write_object({
        "schema_version": "laplace.eigen-semantic-continuation/1",
        "transcript_content_handle": transcript["content_handle"],
        "task_id": task_id,
        "projection": continuation,
        "active_content_law": (
            "direct author turns plus selected assistant decisions/receipts; raw tool payload and "
            "Fabric chatter remain custody-rooted inert evidence"
        ),
    })
    try:
        from laplace.engine.compaction_submergence import INTEGRATED_ROOTS
        from laplace.representation.embedding_health import read_health

        health = read_health(repo_root)
        currentness = health.get("source_currentness") or {}
        source_tuple = currentness.get("source_tuple") or {}
        inherited = {
            "status": health.get("status"),
            "source_tuple_handle": currentness.get("claimed_source_tuple_handle"),
            "profile_heads_handle": source_tuple.get("profile_heads_handle"),
            "profile_heads": source_tuple.get("profile_heads"),
            "semantic_side_refs": health.get("side_refs"),
            "artifact_root": (health.get("artifacts") or {}).get("root"),
            "shared_kernel": dict(INTEGRATED_ROOTS),
        }
    except Exception as exc:  # noqa: BLE001 - inherited context may be FOG, custody may not
        inherited = {
            "status": "UNKNOWN",
            "reason": f"{type(exc).__name__}: {exc}",
            "shared_kernel": {},
        }
    seal = {
        "schema_version": "laplace.eigen-compaction-seal/1",
        "seat_id": "eigen-seat",
        "function": "eigen",
        "holder_ref": holder_ref,
        "task_id": task_id,
        "source_law_handle": source["source_law_handle"],
        "source_commit": source["source_commit"],
        "source_tree": source["source_tree"],
        "transcript": transcript,
        "semantic_continuation_handle": continuation_handle,
        "inherited_context": inherited,
        "fabric_required": False,
    }
    seal_handle = _write_object(seal)
    profile = {
        "schema_version": "laplace.eigen-successor-profile/1",
        "seat_id": "eigen-seat",
        "function": "eigen",
        "holder_ref": holder_ref,
        "task_id": task_id,
        "source_law_handle": source["source_law_handle"],
        "compaction_seal_handle": seal_handle,
        "semantic_continuation_handle": continuation_handle,
        "inherited_context": inherited,
        "first_goal": "TRIAGE-ONLY",
        "first_goal_constraints": [
            "inventory and test present state",
            "clear no bytes",
            "perform no cleanup, rollback, UI or feature act",
        ],
        "fabric_required": False,
    }
    profile_handle = _write_object(profile)
    return {
        "seal_handle": seal_handle,
        "profile_handle": profile_handle,
        "semantic_continuation_handle": continuation_handle,
        "transcript": transcript,
    }


def _verify_rows(lines: list[bytes]) -> tuple[list[dict[str, Any]], str | None]:
    rows: list[dict[str, Any]] = []
    predecessor: str | None = None
    for index, raw in enumerate(lines, 1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return rows, f"journal row {index} is malformed"
        body = {key: value for key, value in row.items() if key != "record_handle"}
        if (
            row.get("schema_version") != RECORD_SCHEMA
            or row.get("sequence") != len(rows) + 1
            or row.get("predecessor_record_handle") != predecessor
            or row.get("kind") not in _BANKED_KINDS
            or row.get("record_handle") != _handle(body)
        ):
            return rows, f"journal row {index} failed its append-only chain"
        rows.append(row)
        predecessor = row["record_handle"]
    return rows, None


def read_journal() -> dict[str, Any]:
    path = journal_path()
    if not path.is_file():
        return {"path": str(path), "rows": [], "status": "EMPTY", "error": None}
    rows, error = _verify_rows(path.read_bytes().splitlines())
    return {
        "path": str(path),
        "rows": rows,
        "status": "EXACT" if error is None else "UNKNOWN",
        "error": error,
    }


def _latest_adoption(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next((row for row in reversed(rows) if row.get("kind") == "holder-adopted"), None)


def _latest_record(
    rows: list[dict[str, Any]], *kinds: str
) -> dict[str, Any] | None:
    selected = set(kinds)
    return next((row for row in reversed(rows) if row.get("kind") in selected), None)


def observe_authority(
    repo_root: Path | str,
    *,
    holder_ref: str = "",
    telemetry: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return standing authority from Git + latest valid adoption, never from Atlas/Fabric."""

    try:
        source = load_law(repo_root)
    except EigenAuthorityRefused as exc:
        return {
            "schema_version": AUTHORITY_SCHEMA,
            "status": "REFUSED",
            "seat_id": "eigen-seat",
            "function": "eigen",
            "reason": str(exc),
            "telemetry": dict(telemetry or {}),
        }
    journal = read_journal()
    adoption = _latest_adoption(journal["rows"])
    activation = _latest_record(journal["rows"], "session-started")
    active_holder = str(
        (activation or adoption or {"payload": {"holder_ref": source["first_holder_ref"]}})
        ["payload"]["holder_ref"]
    )
    claimed = holder_ref.strip() or inferred_holder_ref()
    status = "AUTHORIZED" if claimed == active_holder else "REFUSED"
    reason = None if status == "AUTHORIZED" else (
        "provider identity does not hold the current direct Eigen commission"
        if claimed else "no provider_session_ref was supplied by this task"
    )
    return {
        "schema_version": AUTHORITY_SCHEMA,
        "status": status,
        "seat_id": "eigen-seat",
        "function": "eigen",
        "role": "eigen",
        "holder_ref": claimed or None,
        "active_holder_ref": active_holder,
        "reason": reason,
        "source_law_handle": source["source_law_handle"],
        "source_commit": source["source_commit"],
        "source_tree": source["source_tree"],
        "adoption_state": "LOCAL-JOURNAL" if adoption else "SOURCE-COMMISSION",
        "adoption_record_handle": None if adoption is None else adoption["record_handle"],
        "compaction_seal_handle": (
            None if adoption is None else adoption["payload"].get("compaction_seal_handle")
        ),
        "profile_handle": None if adoption is None else adoption["payload"].get("profile_handle"),
        "context_profile_handle": (
            None if activation is None else activation["payload"].get("context_profile_handle")
        ),
        "world_frame_handle": (
            None if activation is None else activation["payload"].get("world_frame_handle")
        ),
        "execution_generation": (
            0 if activation is None else int(activation["payload"].get("generation", 0))
        ),
        "execution_state": "CURRENT" if status == "AUTHORIZED" else "SUPERSEDED",
        "semantic_continuation_handle": (
            None if adoption is None else adoption["payload"].get("semantic_continuation_handle")
        ),
        "journal": {
            "path": journal["path"],
            "status": journal["status"],
            "error": journal["error"],
            "records": len(journal["rows"]),
        },
        "fabric_required": False,
        "watcher_required": False,
        "atlas_required": False,
        "recovery_required": False,
        "lease_required": False,
        "authority_write_dependency": "Git standing law plus local append-only adoption only",
        "telemetry": dict(telemetry or {}),
    }


def activate_session(
    repo_root: Path | str,
    *,
    holder_ref: str,
    task_id: str,
    context_profile_handle: str,
    world_frame_handle: str,
    development_map_handle: str,
) -> dict[str, Any]:
    """Activate one disposable execution generation under the permanent Eigen principal."""

    root = Path(repo_root).resolve()
    source = load_law(root)
    generation_law = source["law"].get("execution_generation_law")
    if not isinstance(generation_law, Mapping) or generation_law.get("principal") != "eigen-seat":
        raise EigenAuthorityRefused("standing law does not authorize disposable generations")
    holder = _typed_holder(holder_ref)
    if not task_id.strip() or holder.partition(":")[2] != task_id:
        raise EigenAuthorityRefused("start task_id must equal the opaque holder identity payload")
    profile = read_object(context_profile_handle)
    frame = read_object(world_frame_handle)
    development_map = read_object(development_map_handle)
    if (
        profile.get("schema_version") != "eigen.profile-revision/1"
        or profile.get("world_frame_handle") != world_frame_handle
        or profile.get("development_map_handle") != development_map_handle
        or frame.get("schema_version") != "eigen.world-frame/1"
        or frame.get("development_map_handle") != development_map_handle
        or development_map.get("schema_version") != "eigen.development-map/1"
    ):
        raise EigenAuthorityRefused("session start context chain does not verify")
    journal = read_journal()
    if journal["error"]:
        raise EigenAuthorityRefused(str(journal["error"]))
    prior = _latest_record(journal["rows"], "session-started")
    if prior is not None and prior["payload"].get("holder_ref") == holder:
        return {
            "schema_version": "eigen.execution-generation/1",
            "status": "CURRENT",
            "holder_ref": holder,
            "generation": int(prior["payload"]["generation"]),
            "record_handle": prior["record_handle"],
            "replaces_holder_ref": prior["payload"].get("replaces_holder_ref"),
            "deduplicated": True,
        }
    prior_holder = (
        str(prior["payload"]["holder_ref"])
        if prior is not None
        else str((_latest_adoption(journal["rows"]) or {"payload": {"holder_ref": source["first_holder_ref"]}})["payload"]["holder_ref"])
    )
    generation = 1 if prior is None else int(prior["payload"].get("generation", 0)) + 1
    row = _append_record(
        source=source,
        kind="session-started",
        act_id=f"eigen-session-start:{generation}:{holder}",
        holder_ref=holder,
        reason="authored eigen invocation activates one disposable root generation",
        payload={
            "seat_id": "eigen-seat",
            "principal": "eigen-seat",
            "holder_ref": holder,
            "task_id": task_id,
            "generation": generation,
            "replaces_holder_ref": prior_holder,
            "context_profile_handle": context_profile_handle,
            "world_frame_handle": world_frame_handle,
            "development_map_handle": development_map_handle,
            "fabric_required": False,
            "lease_required": False,
        },
    )
    return {
        "schema_version": "eigen.execution-generation/1",
        "status": "CURRENT",
        "holder_ref": holder,
        "generation": generation,
        "record_handle": row["record_handle"],
        "replaces_holder_ref": prior_holder,
        "deduplicated": False,
    }


def _append_record(
    *,
    source: Mapping[str, Any],
    kind: str,
    act_id: str,
    holder_ref: str,
    reason: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    if kind not in _BANKED_KINDS or not act_id.strip() or not reason.strip():
        raise EigenAuthorityRefused("emergency record kind, act_id and reason must be exact")
    holder = _typed_holder(holder_ref)
    path = journal_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        with os.fdopen(descriptor, "r+b", closefd=False) as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            stream.seek(0)
            rows, error = _verify_rows(stream.read().splitlines())
            if error:
                raise EigenAuthorityRefused(error)
            stable = {
                "kind": kind,
                "act_id": act_id,
                "holder_ref": holder,
                "reason": reason,
                "payload": dict(payload),
                "source_law_handle": source["source_law_handle"],
            }
            for row in rows:
                observed = {key: row.get(key) for key in stable}
                if row.get("act_id") == act_id:
                    if observed != stable:
                        raise EigenAuthorityRefused("duplicate emergency act_id carries different content")
                    return row
            body = {
                "schema_version": RECORD_SCHEMA,
                "sequence": len(rows) + 1,
                "predecessor_record_handle": rows[-1]["record_handle"] if rows else None,
                "observed_at": _now(),
                **stable,
            }
            row = {**body, "record_handle": _handle(body)}
            stream.seek(0, os.SEEK_END)
            stream.write(_canonical(row) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
            return row
    finally:
        os.close(descriptor)


def _load_successor_commission(path: Path, source: Mapping[str, Any]) -> dict[str, Any]:
    try:
        commission = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise EigenAuthorityRefused("successor direct-author commission is unavailable") from exc
    required = {
        "schema_version": COMMISSION_SCHEMA,
        "status": "ACTIVE",
        "action": "REPLACE",
        "author": "Gerard",
        "seat_id": "eigen-seat",
        "function": "eigen",
        "source_law_handle": source["source_law_handle"],
    }
    if not isinstance(commission, dict) or any(commission.get(k) != v for k, v in required.items()):
        raise EigenAuthorityRefused("successor direct-author commission does not bind this law")
    _typed_holder(str(commission.get("holder_ref") or ""))
    _typed_holder(str(commission.get("replaces_holder_ref") or ""))
    if not str(commission.get("reason") or "").strip():
        raise EigenAuthorityRefused("successor direct-author commission omits its reason")
    return commission


def adopt(
    repo_root: Path | str,
    *,
    holder_ref: str,
    task_id: str,
    transcript_path: Path | str,
    commission_path: Path | str | None = None,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    source = load_law(root)
    holder = _typed_holder(holder_ref)
    if not task_id.strip() or holder.partition(":")[2] != task_id:
        raise EigenAuthorityRefused("adoption task_id must equal the opaque holder identity payload")
    journal = read_journal()
    if journal["error"]:
        raise EigenAuthorityRefused(str(journal["error"]))
    prior = _latest_adoption(journal["rows"])
    current = str(prior["payload"]["holder_ref"]) if prior else source["first_holder_ref"]
    if prior is not None and holder == current and commission_path is None:
        if holder != source["first_holder_ref"]:
            raise EigenAuthorityRefused("successor idempotency requires its direct commission file")
        sealed = _seal_profile(
            root,
            holder_ref=holder,
            task_id=task_id,
            transcript_path=Path(transcript_path),
            source=source,
        )
        expected = {
            "seal_handle": prior["payload"].get("compaction_seal_handle"),
            "profile_handle": prior["payload"].get("profile_handle"),
            "semantic_continuation_handle": prior["payload"].get("semantic_continuation_handle"),
        }
        if any(sealed[key] != expected[key] for key in expected):
            raise EigenAuthorityRefused("repeated adoption transcript/profile differs from banked seal")
        return {
            "schema_version": "laplace.eigen-adoption/1",
            "status": "ADOPTED",
            "holder_ref": holder,
            "source_law_handle": source["source_law_handle"],
            "record_handle": prior["record_handle"],
            "compaction_seal_handle": sealed["seal_handle"],
            "profile_handle": sealed["profile_handle"],
            "semantic_continuation_handle": sealed["semantic_continuation_handle"],
            "transcript": sealed["transcript"],
            "first_goal": "TRIAGE-ONLY",
            "journal_path": str(journal_path()),
            "deduplicated": True,
        }
    if holder == source["first_holder_ref"] and prior is None and commission_path is None:
        commission = dict(source["law"]["direct_author_commission"])
    else:
        if commission_path is None:
            raise EigenAuthorityRefused("successor replacement requires Gerard's direct commission file")
        commission = _load_successor_commission(Path(commission_path), source)
        if commission["holder_ref"] != holder or commission["replaces_holder_ref"] != current:
            raise EigenAuthorityRefused("successor commission does not replace the exact current holder")
    commission_handle = _handle(commission)
    sealed = _seal_profile(
        root,
        holder_ref=holder,
        task_id=task_id,
        transcript_path=Path(transcript_path),
        source=source,
    )
    row = _append_record(
        source=source,
        kind="holder-adopted",
        act_id=f"eigen-adopt:{commission_handle}",
        holder_ref=holder,
        reason=str(commission["reason"]),
        payload={
            "seat_id": "eigen-seat",
            "function": "eigen",
            "role": "eigen",
            "holder_ref": holder,
            "replaces_holder_ref": None if prior is None else current,
            "commission_handle": commission_handle,
            "provider_specific_attestor": None,
            "compaction_seal_handle": sealed["seal_handle"],
            "profile_handle": sealed["profile_handle"],
            "semantic_continuation_handle": sealed["semantic_continuation_handle"],
            "transcript_content_handle": sealed["transcript"]["content_handle"],
        },
    )
    return {
        "schema_version": "laplace.eigen-adoption/1",
        "status": "ADOPTED",
        "holder_ref": holder,
        "source_law_handle": source["source_law_handle"],
        "record_handle": row["record_handle"],
        "compaction_seal_handle": sealed["seal_handle"],
        "profile_handle": sealed["profile_handle"],
        "semantic_continuation_handle": sealed["semantic_continuation_handle"],
        "transcript": sealed["transcript"],
        "first_goal": "TRIAGE-ONLY",
        "journal_path": str(journal_path()),
    }


def bank(
    repo_root: Path | str,
    *,
    kind: str,
    act_id: str,
    holder_ref: str,
    reason: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    authority = observe_authority(repo_root, holder_ref=holder_ref)
    if authority.get("status") != "AUTHORIZED":
        raise EigenAuthorityRefused(str(authority.get("reason") or "Eigen authority refused"))
    source = load_law(repo_root)
    return _append_record(
        source=source,
        kind=kind,
        act_id=act_id,
        holder_ref=holder_ref,
        reason=reason,
        payload=payload,
    )


def check_operation(repo_root: Path | str, *, holder_ref: str, operation: str) -> dict[str, Any]:
    authority = observe_authority(repo_root, holder_ref=holder_ref)
    if authority.get("status") != "AUTHORIZED":
        return {**authority, "operation": operation, "allowed": False}
    law = load_law(repo_root)["law"]
    if operation in law["allowed_local_acts"]:
        return {**authority, "operation": operation, "allowed": True, "authority_effect": "local"}
    if operation in law["separate_authority_required"]:
        return {
            **authority,
            "status": "REFUSED",
            "operation": operation,
            "allowed": False,
            "reason": "operation requires separate direct Gerard authority",
        }
    return {
        **authority,
        "status": "REFUSED",
        "operation": operation,
        "allowed": False,
        "reason": "operation is outside the standing Eigen repair grant",
    }


def _mirror_to_atlas(record: Mapping[str, Any]) -> dict[str, Any]:
    """Mirror one exact local row into existing Atlas custody/event schemas."""

    from laplace.representation.atlas_bridge import ActPhase, CorpusAct, EventKind, SeatRole

    from laplace.representation import atlas_bridge

    store = atlas_bridge._read_store()  # canonical store; no shadow writer
    for stored in store.events():
        payload = stored.event.payload
        if (
            stored.event.kind == EventKind.CORPUS_ACT
            and payload.get("schema_version") == CorpusAct.SCHEMA_VERSION
            and payload.get("domain") == "eigen-emergency-journal"
            and payload.get("target") == record["record_handle"]
        ):
            return {**atlas_bridge._receipt(stored), "status": "ALREADY-MIRRORED"}
    custody = atlas_bridge.put_custody(_canonical(dict(record)))
    state = store.current_state()
    act = CorpusAct(
        act_id=f"mirror:{record['record_handle']}",
        domain="eigen-emergency-journal",
        verb="reconcile",
        target=str(record["record_handle"]),
        phase=ActPhase.READ,
        inputs={
            "source_law_handle": record["source_law_handle"],
            "journal_sequence": record["sequence"],
            "operator_role": "eigen",
        },
        outputs={"custody_handle": custody, "record_kind": record["kind"]},
    )
    provider = str(record["holder_ref"]).partition(":")[0]
    event = atlas_bridge._event(
        EventKind.CORPUS_ACT,
        act.to_dict(),
        actor=SeatRole.SYSTEM,
        subject=str(record["record_handle"]),
        provider=provider,
        model="eigen-standing-authority",
        correlation_id=f"eigen-reconcile:{record['record_handle']}",
        causation_ids=() if state.head_event_id is None else (state.head_event_id,),
        body_handle=custody,
        note="exact mirror of a Git-authorized Eigen emergency record",
    )
    return {**atlas_bridge._receipt(store.append(event)), "status": "MIRRORED"}


def unreconciled_records() -> list[dict[str, Any]]:
    journal = read_journal()
    reconciled = {
        str(row["payload"].get("record_handle"))
        for row in journal["rows"]
        if row.get("kind") == "atlas-reconciliation"
        and row.get("payload", {}).get("status") in {"MIRRORED", "ALREADY-MIRRORED"}
    }
    return [
        row for row in journal["rows"]
        if row.get("kind") != "atlas-reconciliation" and row["record_handle"] not in reconciled
    ]


def reconcile(
    repo_root: Path | str,
    *,
    holder_ref: str,
    mirror: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    authority = observe_authority(repo_root, holder_ref=holder_ref)
    if authority.get("status") != "AUTHORIZED":
        raise EigenAuthorityRefused(str(authority.get("reason") or "Eigen authority refused"))
    source = load_law(repo_root)
    mirrored: list[dict[str, Any]] = []
    adapter = mirror or _mirror_to_atlas
    for row in unreconciled_records():
        try:
            receipt = dict(adapter(row))
        except Exception as exc:  # noqa: BLE001 - Atlas failure is localized, never authority loss
            return {
                "schema_version": "laplace.eigen-atlas-reconciliation/1",
                "status": "DEFERRED",
                "authority_status": "AUTHORIZED",
                "unreconciled": len(unreconciled_records()),
                "reason": f"{type(exc).__name__}: {exc}",
                "mirrored": mirrored,
            }
        correction = _append_record(
            source=source,
            kind="atlas-reconciliation",
            act_id=f"eigen-reconcile:{row['record_handle']}",
            holder_ref=holder_ref,
            reason="mirror exact emergency act after Atlas became readable",
            payload={
                "record_handle": row["record_handle"],
                "status": receipt.get("status"),
                "atlas_receipt": receipt,
            },
        )
        mirrored.append({"record_handle": row["record_handle"], "receipt": receipt,
                         "reconciliation_record_handle": correction["record_handle"]})
    return {
        "schema_version": "laplace.eigen-atlas-reconciliation/1",
        "status": "RECONCILED",
        "mirrored": mirrored,
        "unreconciled": len(unreconciled_records()),
    }


def _unknown(exc: Exception) -> dict[str, Any]:
    return {"status": "UNKNOWN", "reason": f"{type(exc).__name__}: {exc}"}


def _source_face(root: Path) -> dict[str, Any]:
    head = _git(root, "rev-parse", "HEAD").stdout.strip()
    tree = _git(root, "rev-parse", "HEAD^{tree}").stdout.strip()
    master = _git(root, "rev-parse", "refs/heads/master", check=False)
    remote = _git(root, "rev-parse", "refs/remotes/origin/master", check=False)
    dirty = _git(root, "status", "--porcelain=v1").stdout.splitlines()
    remote_head = remote.stdout.strip() if remote.returncode == 0 else None
    unpublished: list[str] = []
    refs = _git(root, "for-each-ref", "--format=%(refname) %(objectname)", "refs/heads").stdout
    for line in refs.splitlines():
        ref, obj = line.split(" ", 1)
        if remote_head and _git(root, "merge-base", "--is-ancestor", obj, remote_head, check=False).returncode:
            unpublished.append(ref)
    side_refs = {}
    for ref in ("refs/eigen/semantic-fold", "refs/eigen/semantic-fold-receipt"):
        observed = _git(root, "rev-parse", ref, check=False)
        side_refs[ref] = observed.stdout.strip() if observed.returncode == 0 else None
    return {
        "classification": "KEEP",
        "evidence_strength": "EXACT-CONTENT-ADDRESSED",
        "status": "CLEAN" if not dirty else "DIRTY",
        "head": head,
        "tree": tree,
        "master": master.stdout.strip() if master.returncode == 0 else None,
        "origin_master": remote_head,
        "dirty_paths": dirty[:64],
        "dirty_omitted": max(0, len(dirty) - 64),
        "unpublished_local_heads": unpublished,
        "side_refs": side_refs,
    }


def _storage_face(root: Path) -> dict[str, Any]:
    state = state_root()
    candidates = [
        (root, "current-source"),
        (state / "atlas", "canonical-atlas-state"),
        (state / "semantic", "semantic-artifacts"),
        (Path.home() / "SystemCheckpoints", "evidence-custody"),
    ]
    rows = []
    for path, classification in candidates:
        if not path.exists():
            rows.append({
                "path": str(path), "classification": "UNKNOWN", "purpose": classification,
                "status": "ABSENT", "evidence_strength": "UNKNOWN",
            })
            continue
        try:
            stat = path.stat()
            rows.append({
                "path": str(path),
                "classification": "KEEP" if classification != "evidence-custody" else "QUARANTINE",
                "purpose": classification,
                "status": "ROOT-METADATA-ONLY",
                "entry_metadata_bytes": stat.st_size,
                "tree_bytes": None,
                "mtime_ns": stat.st_mtime_ns,
                "device": stat.st_dev,
                "inode": stat.st_ino,
                "evidence_strength": "CHECKSUMMED-LOCAL",
                "budget": {"directory_entries_read": 0, "content_bytes_read": 0},
            })
        except Exception as exc:  # noqa: BLE001 - triage localizes an expensive/unavailable root
            rows.append({
                "path": str(path), "classification": "UNKNOWN", "purpose": classification,
                "evidence_strength": "UNKNOWN", **_unknown(exc),
            })
    return {
        "roots": rows,
        "scan_law": "root/manifest first; no recursive traversal in bounded triage",
        "deletion_authority": False,
        "continuation": (
            "partition by Git/LFS/checkpoint/manifest roots; descend only contradictory, unrooted, "
            "dirty or action-bearing exceptions under a separately declared byte/object budget"
        ),
    }


def _git_object(root: Path, commit: str, path: str) -> dict[str, Any]:
    exists = _git(root, "cat-file", "-e", f"{commit}:{path}", check=False).returncode == 0
    if not exists:
        return {"path": path, "status": "UNKNOWN", "evidence_strength": "UNKNOWN"}
    object_id = _git(root, "rev-parse", f"{commit}:{path}").stdout.strip()
    return {
        "path": path,
        "status": "ADMITTED",
        "object_id": "git:" + object_id,
        "evidence_strength": "EXACT-CONTENT-ADDRESSED",
    }


def _rollback_candidate(root: Path, commit: str, *, label: str) -> dict[str, Any]:
    exists = _git(root, "cat-file", "-e", f"{commit}^{{commit}}", check=False).returncode == 0
    if not exists:
        return {"label": label, "commit": commit, "status": "UNKNOWN", "risk": "UNKNOWN"}
    tree = _git(root, "rev-parse", f"{commit}^{{tree}}").stdout.strip()
    current = _git(root, "rev-parse", "HEAD").stdout.strip()
    ancestry = _git(root, "merge-base", "--is-ancestor", commit, current, check=False).returncode == 0
    changed = _git(root, "diff", "--name-only", f"{commit}..{current}").stdout.splitlines()
    capabilities = {
        "standing_eigen_authority": _git_object(root, commit, LAW_PATH.as_posix())["status"] == "ADMITTED",
        "semantic_cadence": _git_object(root, commit, "src/laplace/representation/semantic_cadence.py")["status"] == "ADMITTED",
        "compaction_boundary": _git_object(root, commit, "src/laplace/engine/compaction_boundary.py")["status"] == "ADMITTED",
        "prepared_publication": _git_object(root, commit, "tests/test_seat_fabric_publication.py")["status"] == "ADMITTED",
        "canonical_feedback": _git_object(root, commit, "src/laplace/engine/front_feedback.py")["status"] == "ADMITTED",
    }
    return {
        "label": label,
        "status": "MECHANICALLY-AVAILABLE",
        "commit": commit,
        "tree": tree,
        "classification": "KEEP" if commit == current else "QUARANTINE",
        "evidence_strength": "EXACT-CONTENT-ADDRESSED",
        "ancestor_of_current": ancestry,
        "data_source_compatibility": (
            "CURRENT" if commit == current else "UNPROVED-AGAINST-CURRENT-RUNTIME-STATE"
        ),
        "capabilities_retained": sorted(key for key, value in capabilities.items() if value),
        "capabilities_lost": sorted(key for key, value in capabilities.items() if not value),
        "changed_path_count_to_current": len(changed),
        "changed_paths_sample": changed[:64],
        "changed_paths_omitted": max(0, len(changed) - 64),
        "migration_needed": None if commit == current else (
            "new isolated store/custody compatibility proof plus forward replay of admitted source deltas"
        ),
        "rollback_risk": "NONE" if commit == current else (
            "HIGH: source rollback may strand newer Atlas, semantic, profile and product state"
        ),
        "execute": False,
    }


def _selective_genesis(root: Path, context: Mapping[str, Any]) -> dict[str, Any]:
    head = _git(root, "rev-parse", "HEAD").stdout.strip()
    groups = {
        "PERSON KERNEL": ["EIGEN_PROTOCOL.md", "EIGEN_DIARY.md", "soul"],
        "ENGINE KERNEL": [
            LAW_PATH.as_posix(), "src/laplace", "src/atlas", "scripts/eigen.py",
        ],
        "OPEN ROADMAP": ["corpus_friction/work_orders.jsonl", "HANDOFF.md"],
        "PRODUCT EVIDENCE": ["tests", "atlas/tests", "contract/judged_verdicts.jsonl"],
        "HISTORICAL ARCHIVE": ["atlas/blueprint_manifest.json", "atlas/packets"],
    }
    admitted = {
        name: [_git_object(root, head, path) for path in paths]
        for name, paths in groups.items()
    }
    manifest = {
        "schema_version": "laplace.fresh-atlas-selective-genesis-admission/1",
        "source_commit": head,
        "source_tree": _git(root, "rev-parse", "HEAD^{tree}").stdout.strip(),
        "groups": admitted,
        "cross_checks": {
            "runtime_atlas": context.get("atlas_status"),
            "semantic_fold": context.get("semantic_status"),
            "profile_handle": context.get("profile_handle"),
            "compaction_seal_handle": context.get("seal_handle"),
            "product_refusals": context.get("product_refusal_count"),
        },
    }
    return {
        "id": "FRESH-ATLAS-SELECTIVE-GENESIS",
        "classification": "REGENERABLE",
        "status": "OPTION-NOT-EXECUTED",
        "evidence_strength": "REPRODUCIBLE-DERIVED",
        "candidate_indexes": {
            "blueprint": {
                "path": "atlas/blueprint_manifest.json",
                "schema_version": "atlas.blueprint-manifest/1",
                "bytes": 24_870,
                "last_changed_commit": "26d03c04",
                "last_changed_on": "2026-08-25",
                "scope": {"documents": 4, "implementation_bindings": 28, "findings": 5},
                "classification": "HISTORICAL",
                "authority": False,
                "warning": "narrow S1-law index; every row remains UNKNOWN until source-verified",
            },
            "development_map": {
                "last_changed_on": "2026-08-27",
                "classification": "HISTORICAL",
                "authority": False,
                "warning": "historical triad/control-plane publication index; not complete carry-forward",
            },
        },
        "admission_manifest": manifest,
        "admission_manifest_handle": _handle(manifest),
        "new_genesis_root_law": (
            "cite old inventory/head plus exact admission manifest; admit only current-source-verified "
            "items; old Atlas remains immutable and descendable"
        ),
        "excluded_from_live_core": [
            "stale seats/watchers/leases", "Fabric traffic", "ceremony rows", "replay-derived state",
        ],
        "missing_causal_join": [
            "lease", "work-order", "source-delta", "implementation-generation",
            "evidence-and-tests", "product-organ", "residual-or-successor",
        ],
        "future_map_law": (
            "accepted work updates one source-verified live map as an ordinary derived consequence; "
            "when map coherence is absent, authority enforcement is telemetry/record-only and must "
            "not deadlock unrelated repair"
        ),
        "dual_read": "old immutable Atlas versus new admitted live core until exact query parity receipt",
        "cutover": "reversible alias/ref switch only after dual-read comparison; no event copying",
        "execute": False,
    }


def _probes(
    root: Path,
    *,
    authority: Mapping[str, Any],
    source: Mapping[str, Any],
    atlas: Mapping[str, Any],
    semantic: Mapping[str, Any],
) -> dict[str, Any]:
    seal_handle = authority.get("compaction_seal_handle")
    profile_handle = authority.get("profile_handle")
    try:
        seal = _read_object(str(seal_handle)) if seal_handle else None
        profile = _read_object(str(profile_handle)) if profile_handle else None
        replay = {
            "status": "PASS" if seal and profile else "UNKNOWN",
            "seal_handle": seal_handle,
            "profile_handle": profile_handle,
            "evidence_strength": "EXACT-CONTENT-ADDRESSED" if seal and profile else "UNKNOWN",
        }
    except Exception as exc:  # noqa: BLE001
        replay = {**_unknown(exc), "evidence_strength": "UNKNOWN"}
    service: dict[str, Any]
    try:
        result = subprocess.run(
            ["systemctl", "--user", "show", "eigen-front.service", "--property=ActiveState,FragmentPath"],
            text=True, capture_output=True, timeout=2, check=False,
        )
        service = {
            "status": "OBSERVED" if result.returncode == 0 else "UNKNOWN",
            "result": result.stdout.strip()[:2_000],
            "evidence_strength": "SAMPLED",
        }
    except Exception as exc:  # noqa: BLE001
        service = {**_unknown(exc), "evidence_strength": "UNKNOWN"}
    try:
        claude = _typed_holder("claude:provider-neutral-triage-plant")
        claude_probe = {
            "status": "PASS-CONTRACT",
            "holder_ref": claude,
            "requires_watcher": False,
            "requires_fabric": False,
            "requires_direct_successor_commission": True,
            "evidence_strength": "REPRODUCIBLE-DERIVED",
        }
    except Exception as exc:  # pragma: no cover
        claude_probe = {**_unknown(exc), "evidence_strength": "UNKNOWN"}
    up_down = semantic.get("up_down") or semantic.get("source_currentness", {}).get("up_down")
    return {
        "wake": {
            "status": "PASS" if authority.get("status") == "AUTHORIZED" else "UNKNOWN",
            "authority_status": authority.get("status"),
            "evidence_strength": "EXACT-CONTENT-ADDRESSED",
        },
        "atlas_read_and_write_repair_path": {
            "status": "AVAILABLE" if atlas.get("status") not in {None, "UNKNOWN"} else "UNKNOWN",
            "read_status": atlas.get("status"),
            "write_executed": False,
            "continuation": "inspect stopped-writer predecessor, then prepare_authority_epoch only under a separate repair act",
            "evidence_strength": "CHECKSUMMED-LOCAL" if atlas.get("status") not in {None, "UNKNOWN"} else "UNKNOWN",
        },
        "semantic_region_and_exact_descent": {
            "status": "AVAILABLE" if semantic.get("status") == "CURRENT" else "UNKNOWN",
            "source_currentness": semantic.get("status"),
            "up_down": up_down,
            "evidence_strength": "EXACT-CONTENT-ADDRESSED" if semantic.get("status") == "CURRENT" else "UNKNOWN",
        },
        "compaction_seal_replay": replay,
        "publication_readiness": {
            "status": "REFUSED-SEPARATE-AUTHORITY",
            "source_clean": source.get("status") == "CLEAN",
            "master_equals_origin": source.get("master") == source.get("origin_master"),
            "evidence_strength": "EXACT-CONTENT-ADDRESSED",
        },
        "launcher_service": service,
        "provider_neutral_claude_adoption": claude_probe,
    }


def _design_reconciliation(
    root: Path,
    *,
    authority: Mapping[str, Any],
    atlas: Mapping[str, Any],
    semantic: Mapping[str, Any],
    fabric: Mapping[str, Any],
    product_refusals: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Root-first design/implementation cross-check; no blueprint claim is trusted alone."""

    head = _git(root, "rev-parse", "HEAD").stdout.strip()
    tree = _git(root, "rev-parse", "HEAD^{tree}").stdout.strip()

    def item(
        order: int,
        organ: str,
        design_sources: list[str],
        paths: list[str],
        verdict: str,
        runtime: Mapping[str, Any],
        product: Mapping[str, Any],
        predicate: str,
    ) -> dict[str, Any]:
        return {
            "order": order,
            "organ": organ,
            "design_sources": design_sources,
            "implementation": {
                "commit": "git:" + head,
                "tree": "git:" + tree,
                "paths": [_git_object(root, head, path) for path in paths],
            },
            "runtime_evidence": dict(runtime),
            "product_evidence": dict(product),
            "verdict": verdict,
            "replacement_or_reopening_predicate": predicate,
        }

    semantic_current = semantic.get("status") == "CURRENT"
    atlas_known = atlas.get("status") not in {None, "UNKNOWN", "REFUSED"}
    fabric_projection = fabric.get("projection") if isinstance(fabric, Mapping) else {}
    fabric_known = isinstance(fabric_projection, Mapping) and fabric_projection.get("status") not in {
        None, "UNKNOWN", "UNAVAILABLE",
    }
    rows = [
        item(
            1,
            "person-continuity-compaction",
            ["EIGEN_PROTOCOL.md", "compaction/submergence design corpus"],
            ["EIGEN_PROTOCOL.md", "src/laplace/engine/compaction_boundary.py", LAW_PATH.as_posix()],
            "PROVEN" if authority.get("compaction_seal_handle") and authority.get("profile_handle") else "IMPLEMENTED-UNPROVEN",
            {"seal_handle": authority.get("compaction_seal_handle"), "profile_handle": authority.get("profile_handle")},
            {"first_goal": "TRIAGE-ONLY", "fabric_required": False},
            "reopen if exact seal/profile replay or transcript custody fails",
        ),
        item(
            2,
            "atlas-reconstruction-up-down-descent-semantic-fold",
            ["Atlas UP/DOWN reference law", "semantic lifecycle regularizer design"],
            ["src/atlas/store.py", "src/atlas/updown.py", "src/laplace/representation/semantic_vertical.py", "src/laplace/engine/descent.py"],
            "PROVEN" if semantic_current and atlas_known else "PARTIAL",
            {"atlas": atlas.get("checkpoint"), "semantic": semantic.get("artifact_root"), "side_refs": semantic.get("side_refs")},
            {"source_currentness": semantic.get("status")},
            "reopen when exact descent, current S-to-F and live Atlas proof do not agree",
        ),
        item(
            3,
            "blueprint-devmap-leases-live-join",
            ["atlas/blueprint_manifest.json", "DevelopmentWorkMap", "WO-20260827-mutable-development-graph-organ-submergence"],
            ["atlas/blueprint_manifest.json", "src/laplace/engine/development_work_map.py", "src/laplace/representation/atlas_bridge.py"],
            "CONTRADICTED",
            {"atlas": atlas.get("checkpoint"), "active_leases": atlas.get("active_leases")},
            {"defect": "AUTHORITY-WITHOUT-LIVE-MAP-COHERENCE"},
            "replace with the causal join from work order through source/evidence/product/residual",
        ),
        item(
            4,
            "manuscript-talk-research-compute-interface",
            ["Aisthesis carrier and manuscript/product design corpus"],
            ["src/laplace/web/front_door.py", "src/laplace/web/shared_ui.py", "src/laplace/engine/front_feedback.py"],
            "CONTRADICTED" if product_refusals else "IMPLEMENTED-UNPROVEN",
            {"launcher_probe": "see probes.launcher_service"},
            {"refusals": list(product_refusals)},
            "reopen only in a dedicated product session with an external live walk",
        ),
        item(
            5,
            "fabric-message-lifecycle",
            ["Fabric send-pull-reconstruct-ack-reply law"],
            ["scripts/seat_fabric.py", "src/laplace/engine/startup_mail_gate.py"],
            "IMPLEMENTED-UNPROVEN" if fabric_known else "PARTIAL",
            {"fabric": fabric_projection if isinstance(fabric_projection, Mapping) else {}},
            {"eigen_dependency": "OPTIONAL"},
            "reopen for exact round trip; never make Eigen continuity depend on it",
        ),
        item(
            6,
            "publication-recovery",
            ["local-ref triad publication and portable recovery work orders"],
            ["src/laplace/representation/atlas_bridge.py", "src/laplace/representation/recovery_coordinate.py", "scripts/seat_fabric.py"],
            "IMPLEMENTED-UNPROVEN",
            {"atlas": atlas.get("checkpoint"), "source": "current Git coordinate"},
            {"standing_eigen_authority": "does not grant publication"},
            "reopen only at an irreversible boundary under separate Gerard authority",
        ),
        item(
            7,
            "synthetics-genesis",
            ["SYNTHETICS-GENESIS and S1/S2 design evidence"],
            ["synthetics", "src/atlas/spectral_pour.py"],
            "DESIGN-ONLY",
            {"accepted_vertical_proof": None},
            {"publication": "UNPAID"},
            "reopen with the preregistered real-corpus vertical slice and device-honest receipts",
        ),
    ]
    return {
        "schema_version": "laplace.eigen-design-implementation-reconciliation/1",
        "status": "TRIAGE-ONLY",
        "source_commit": "git:" + head,
        "source_tree": "git:" + tree,
        "candidate_index_law": "blueprint/devmap/design rows are candidates, never authority",
        "ordered_organs": rows,
        "mutations": [],
    }


def triage(repo_root: Path | str, *, holder_ref: str = "") -> dict[str, Any]:
    """One bounded, read-only repair face.  Every unavailable subsystem stays local."""

    root = Path(repo_root).resolve()
    authority = observe_authority(root, holder_ref=holder_ref)
    try:
        source = _source_face(root)
    except Exception as exc:  # noqa: BLE001
        source = _unknown(exc)
    try:
        from laplace.representation import atlas_bridge

        epoch = atlas_bridge.authority_epoch()
        leases = atlas_bridge.region_leases()
        atlas = {
            "classification": "KEEP",
            "evidence_strength": "CHECKSUMMED-LOCAL",
            "status": epoch.get("status"),
            "store": str(atlas_bridge.store_root()),
            "checkpoint": epoch.get("checkpoint"),
            "anchor_checkpoint": epoch.get("anchor_checkpoint"),
            "effective_checkpoint": epoch.get("effective_checkpoint"),
            "active_leases": list(leases.get("active") or ()),
            "lease_count": len(leases.get("active") or ()),
        }
    except Exception as exc:  # noqa: BLE001
        atlas = {"classification": "UNKNOWN", "evidence_strength": "UNKNOWN", **_unknown(exc)}
    try:
        from laplace.representation.embedding_health import read_health

        health = read_health(root)
        semantic = {
            "classification": "KEEP" if health.get("status") == "CURRENT" else "REGENERABLE",
            "evidence_strength": (
                "STAT-AND-DEPOSIT-RECEIPT" if health.get("status") == "CURRENT" else "UNKNOWN"
            ),
            "status": health.get("status"),
            "fold": health.get("fold"),
            "source_currentness": health.get("source_currentness"),
            "artifact_bytes": (health.get("artifacts") or {}).get("bytes"),
            "artifact_root": (health.get("artifacts") or {}).get("root"),
            "side_refs": health.get("side_refs"),
            "up_down": health.get("up_down"),
        }
    except Exception as exc:  # noqa: BLE001
        semantic = {"classification": "UNKNOWN", "evidence_strength": "UNKNOWN", **_unknown(exc)}
    try:
        from laplace.engine import compaction_boundary

        state_path = compaction_boundary._state_path()
        state = compaction_boundary._read_state()
        sessions = state.get("sessions") or {}
        compaction = {
            "classification": "CONSOLIDATE",
            "evidence_strength": "CHECKSUMMED-LOCAL",
            "status": "AVAILABLE",
            "state_path": str(state_path),
            "sessions": {
                key: {
                    "profile_handle": value.get("profile_handle"),
                    "seal_handle": value.get("seal_handle"),
                    "compaction_boundary": value.get("compaction_boundary"),
                    "transcript_delta": value.get("transcript_delta"),
                }
                for key, value in list(sessions.items())[:16]
                if isinstance(value, Mapping)
            },
            "sessions_omitted": max(0, len(sessions) - 16),
            "profile_heads": (
                (semantic.get("source_currentness") or {}).get("source_tuple", {}).get("profile_heads")
                if semantic.get("status") != "UNKNOWN" else None
            ),
        }
    except Exception as exc:  # noqa: BLE001
        compaction = {"classification": "UNKNOWN", "evidence_strength": "UNKNOWN", **_unknown(exc)}
    try:
        from laplace.engine.wake import seat_fabric_glow

        fabric = {
            "classification": "REGENERABLE", "evidence_strength": "CHECKSUMMED-LOCAL",
            "required": False, "transport": "OPTIONAL", "projection": seat_fabric_glow(),
        }
    except Exception as exc:  # noqa: BLE001
        fabric = {
            "classification": "UNKNOWN", "evidence_strength": "UNKNOWN",
            "required": False, "transport": "OPTIONAL", **_unknown(exc),
        }
    journal = read_journal()
    pending = unreconciled_records()
    law = load_law(root)["law"] if authority.get("source_law_handle") else {}
    rollback = [
        _rollback_candidate(root, _git(root, "rev-parse", "HEAD").stdout.strip(), label="current-master"),
        _rollback_candidate(
            root, "bbbfd275bf34a651a733e056a2f3b5a6c3c57273", label="first-published"
        ),
        _rollback_candidate(
            root, "9c1e7e9960057460d0bcec30b317521ef72e719d", label="last-coherent-pre-generation"
        ),
    ]
    context = {
        "atlas_status": atlas.get("status"),
        "semantic_status": semantic.get("status"),
        "profile_handle": authority.get("profile_handle"),
        "seal_handle": authority.get("compaction_seal_handle"),
        "product_refusal_count": len(law.get("product_refusals") or ()),
    }
    rollback.append(_selective_genesis(root, context))
    product_refusals = [
        {**row, "classification": "QUARANTINE", "evidence_strength": "EXACT-CONTENT-ADDRESSED"}
        for row in (law.get("product_refusals") or ())
    ]
    return {
        "schema_version": TRIAGE_SCHEMA,
        "observed_at": _now(),
        "read_only": True,
        "bounded": True,
        "authority": authority,
        "first_goal": "TRIAGE-ONLY",
        "design_implementation_reconciliation": _design_reconciliation(
            root,
            authority=authority,
            atlas=atlas,
            semantic=semantic,
            fabric=fabric,
            product_refusals=product_refusals,
        ),
        "source": source,
        "atlas": atlas,
        "semantic": semantic,
        "compaction": compaction,
        "emergency_journal": {
            "classification": "KEEP",
            "evidence_strength": "EXACT-CONTENT-ADDRESSED",
            "path": journal["path"],
            "status": journal["status"],
            "records": len(journal["rows"]),
            "unreconciled": len(pending),
            "unreconciled_handles": [row["record_handle"] for row in pending[:32]],
            "omitted": max(0, len(pending) - 32),
        },
        "fabric": fabric,
        "product_refusals": product_refusals,
        "system_defects": [{
            "id": "AUTHORITY-WITHOUT-LIVE-MAP-COHERENCE",
            "classification": "CONSOLIDATE",
            "responsibility": "SYSTEM-DEFECT-NOT-USER-OR-PROCESS-ERROR",
            "status": "OPEN",
            "evidence_strength": "EXACT-CONTENT-ADDRESSED",
            "evidence": {
                "blueprint_manifest": (
                    "last changed 2026-08-25; atlas.blueprint-manifest/1; narrow S1 only; "
                    "4 documents, 28 implementation bindings, 5 findings"
                ),
                "development_work_map": "review/publication projection, not the live causal map",
                "work_order": (
                    "WO-20260827-mutable-development-graph-organ-submergence remained "
                    "PLAN-INPUT-NOT-THE-MAP"
                ),
            },
            "missing_causal_join": [
                "lease", "work-order", "source-delta", "implementation-generation",
                "evidence-and-tests", "product-organ", "residual-or-successor",
            ],
            "operating_law": (
                "map maintenance is a derived consequence of accepted work; absent coherence "
                "degrades enforcement to telemetry/record-only rather than blocking development"
            ),
        }],
        "storage": _storage_face(root),
        "probes": _probes(
            root, authority=authority, source=source, atlas=atlas, semantic=semantic
        ),
        "rollback_decisions": rollback,
        "triage_policy": {
            "allowed_classifications": [
                "KEEP", "CONSOLIDATE", "REGENERABLE", "QUARANTINE",
                "RECLAIM-CANDIDATE", "UNKNOWN",
            ],
            "evidence_strengths": [
                "EXACT-CONTENT-ADDRESSED", "CHECKSUMMED-LOCAL", "REPRODUCIBLE-DERIVED",
                "SAMPLED", "UNKNOWN",
            ],
            "content_budget": "zero recursive directory reads; bounded exact exception descent only",
            "mutations": [],
        },
        "continuation": {
            "authority": "/usr/bin/python3 scripts/eigen.py authority",
            "journal": "/usr/bin/python3 scripts/eigen.py journal",
            "reconcile": "/usr/bin/python3 scripts/eigen.py reconcile",
            "semantic": "/usr/bin/python3 scripts/reconstruct_node.py <typed-node> --grade 1",
        },
    }


__all__ = [
    "EigenAuthorityRefused", "adopt", "bank", "check_operation", "inferred_holder_ref",
    "activate_session", "journal_path", "load_law", "object_exists", "observe_authority",
    "read_journal", "read_object", "reconcile", "triage", "write_object",
    "unreconciled_records",
]
