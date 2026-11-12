"""Deduplicated shared semantic-fold cadence and out-of-fold consumption receipts."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping

from laplace.representation.semantic_vertical import canonical_bytes, digest

CADENCE_SCHEMA = "laplace.semantic-fold-cadence/1"
CONSUMPTION_SCHEMA = "laplace.semantic-fold-consumption/1"
GOAL_CONTEXT_PATH = Path(
    "/home/phujck/SystemCheckpoints/2026-08-28/THREE-SEAT-GOALS-AND-CONTEXT.json"
)
GOAL_CONTEXT_HANDLE = (
    "sha256:2991526a880b125269e3f95c35e7013797d23a51ee3e8841c8e8f45653111818"
)


def _state_root() -> Path:
    explicit = os.environ.get("LAPLACE_SEMANTIC_STATE_ROOT", "").strip()
    return Path(explicit) if explicit else Path.home() / ".mcp-gerard" / "laplace" / "semantic"


def _read(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(canonical_bytes(value) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


@contextmanager
def _cadence_lock() -> Iterator[None]:
    """Serialize queue ownership without turning a health read into a write."""

    path = _state_root() / "cadence.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def worktree_changed_paths(repo_root: Path | str) -> set[str]:
    """Return exact changed files instead of collapsed untracked directories."""

    result = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=Path(repo_root), check=True, capture_output=True, text=True,
    )
    return {line[3:] for line in result.stdout.splitlines() if line}


def _observed_at() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def process_start_token(pid: int | None = None) -> str | None:
    """Bind process identity to kernel boot and start ticks, not reusable PID alone."""

    selected = os.getpid() if pid is None else pid
    if not isinstance(selected, int) or isinstance(selected, bool) or selected <= 0:
        return None
    try:
        boot_id = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
        stat = Path(f"/proc/{selected}/stat").read_text(encoding="ascii")
        # The command name is parenthesized and may contain spaces. Fields after its final
        # right parenthesis begin with field 3; process starttime is field 22.
        tail = stat[stat.rfind(")") + 2 :].split()
        start_ticks = tail[19]
    except (OSError, IndexError, ValueError):
        return None
    return digest({"boot_id": boot_id, "pid": selected, "start_ticks": start_ticks})


def _alive(pid: Any, start_token: Any = None) -> bool:
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return start_token is None or process_start_token(pid) == start_token


def read_state() -> dict[str, Any]:
    """Pure cadence observation: never reconcile, enqueue, or write from a health read."""

    path = _state_root() / "cadence.json"
    if not path.is_file():
        return {
            "schema_version": CADENCE_SCHEMA,
            "status": "IDLE",
            "generation": None,
            "desired_source": None,
            "last_success": None,
            "last_refusal": None,
            "orphan_reconciliations": 0,
        }
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {
            "schema_version": CADENCE_SCHEMA,
            "status": "UNKNOWN",
            "reason": f"malformed cadence state: {type(exc).__name__}: {exc}",
            "generation": None,
            "desired_source": None,
        }
    if not isinstance(value, dict) or value.get("schema_version") != CADENCE_SCHEMA:
        return {
            "schema_version": CADENCE_SCHEMA,
            "status": "UNKNOWN",
            "reason": "cadence state has a missing or unknown schema",
            "generation": None,
            "desired_source": None,
        }
    if value.get("status") == "RUNNING" and not _alive(
        value.get("pid"), value.get("process_start_token")
    ):
        return {
            **value,
            "status": "ORPHANED",
            "reason": "producer identity is no longer live; explicit reconciliation required",
        }
    return value


def reconcile_state() -> dict[str, Any]:
    """Explicitly claim an orphan for retry; callers opt into this state mutation."""

    value = read_state()
    if value.get("status") != "ORPHANED":
        return value
    reconciled = {
        **value,
        "status": "QUEUED",
        "pid": None,
        "process_start_token": None,
        "orphan_reconciliations": int(value.get("orphan_reconciliations", 0)) + 1,
        "last_refusal": {
            "reason": "orphaned semantic producer explicitly reconciled to the queue",
            "generation": value.get("generation"),
        },
    }
    reconciled.pop("reason", None)
    _write(_state_root() / "cadence.json", reconciled)
    return reconciled


def _exact_file_handle(path: Path, expected: str, *, name: str) -> str:
    try:
        observed = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise RuntimeError(f"semantic cadence {name} custody is unavailable: {exc}") from exc
    if observed != expected:
        raise RuntimeError(
            f"semantic cadence {name} custody moved: expected {expected}, observed {observed}"
        )
    return observed


def current_atlas_observation(root: Path | str) -> dict[str, Any]:
    """Read the exact live Atlas face without making volatile traffic semantic identity."""

    root = Path(root).resolve()
    from laplace.representation import atlas_bridge

    drift = atlas_bridge.drift_token()
    epoch = atlas_bridge.authority_epoch()
    if epoch.get("status") != "CURRENT":
        raise RuntimeError(
            f"semantic cadence authority checkpoint is {epoch.get('status') or 'UNKNOWN'}"
        )
    checkpoint = epoch.get("effective_checkpoint")
    if not isinstance(checkpoint, Mapping):
        raise RuntimeError("semantic cadence authority checkpoint body is unavailable")
    exact_tip = {
        "cursor": int(checkpoint["cursor"]),
        "head_event_id": str(checkpoint["head_event_id"]),
        "head_record_digest": str(checkpoint["head_record_digest"]),
    }
    observed_tip = {
        "cursor": int(drift["cursor"]),
        "head_event_id": str(drift["head_event_id"]),
        "head_record_digest": str(drift["head_record_digest"]),
    }
    if exact_tip != observed_tip:
        raise RuntimeError("semantic cadence compact Atlas tip moved during source capture")
    authority = checkpoint.get("authority")
    if not isinstance(authority, Mapping):
        raise RuntimeError("semantic cadence authority roots are unavailable")
    authority_roots = {
        key: str(authority[key])
        for key in (
            "development_review_root",
            "provider_session_root",
            "region_lease_root",
            "seat_mail_frontier_root",
            "seat_occupancy_root",
        )
    }
    body = {
        "schema_version": "laplace.semantic-atlas-observation/1",
        "drift_token": {"schema_version": drift["schema_version"], **observed_tip},
        "effective_checkpoint_digest": str(epoch["effective_checkpoint_digest"]),
        "authority_roots": authority_roots,
        "integrity_boundary": str(
            (epoch.get("integrity_boundary") or {}).get("status") or "UNKNOWN"
        ),
    }
    body["observation_handle"] = digest(body)
    return body


def _semantic_atlas_token(observation: Mapping[str, Any]) -> dict[str, Any]:
    """Compile only roots whose movement changes semantic reconstruction.

    Seat renewals, message delivery, and leases remain visible in the observation face, but they
    do not invalidate 264 MB of semantic artifacts.  Development-review movement and an integrity
    boundary change remain strict fold inputs.
    """

    roots = observation.get("authority_roots")
    if not isinstance(roots, Mapping):
        raise RuntimeError("semantic cadence Atlas observation lacks authority roots")
    body = {
        "schema_version": "laplace.semantic-atlas-currentness-token/2",
        "drift_token": dict(observation["drift_token"]),
        "effective_checkpoint_digest": str(observation["effective_checkpoint_digest"]),
        "authority_roots": dict(roots),
        "semantic_roots": {
            "development_review_root": str(roots["development_review_root"]),
        },
        "integrity_boundary": str(observation.get("integrity_boundary") or "UNKNOWN"),
        "operational_roots": (
            "observed separately; provider, mail, occupancy, lease and cursor motion do not "
            "invalidate semantic artifacts"
        ),
    }
    body["token_handle"] = digest(body)
    return body


def semantic_source_identity(source_tuple: Mapping[str, Any]) -> dict[str, Any]:
    """Return the strict semantic preimage, excluding operational and derived motion.

    ``semantic/seat_context_heads.json`` is rebuilt by the fold from the profile handles, goal
    digests, phase policy, routes, and live seat generations. Its aggregate handle is therefore an
    output observation, not an independent source input: including it makes every fold stale on
    the move it authored. The normalized profile-head fields remain strict below.
    """

    body = {
        key: value
        for key, value in source_tuple.items()
        if key != "source_tuple_handle"
    }
    if source_tuple.get("schema_version") != "laplace.semantic-fold-source-tuple/2":
        return body
    body.pop("profile_heads_handle", None)
    atlas = source_tuple.get("atlas")
    if not isinstance(atlas, Mapping):
        raise RuntimeError("semantic source tuple lacks its Atlas token")
    body["atlas"] = {
        "schema_version": "laplace.semantic-atlas-currentness-token/2",
        "semantic_roots": dict(atlas.get("semantic_roots") or {}),
        "integrity_boundary": str(atlas.get("integrity_boundary") or "UNKNOWN"),
        "operational_roots": atlas.get("operational_roots"),
    }
    return body


def semantic_generation(source_tuple: Mapping[str, Any]) -> str:
    return digest(semantic_source_identity(source_tuple))


def current_source_tuple(
    root: Path | str,
    *,
    source_commit: str,
    source_tree: str,
    atlas_observation: Mapping[str, Any] | None = None,
    source_kernel_inputs: list[dict] | None = None,
) -> dict[str, Any]:
    """Return the complete bounded source-currentness token used by S and hot health.

    This is deliberately not a provider snapshot.  Atlas contributes its compact tip plus the
    already-verified effective authority checkpoint; profile and policy inputs are small
    content-addressed heads.  Any unavailable proof refuses instead of silently producing a
    generation which could remain CURRENT after live authority moved.
    """

    root = Path(root).resolve()
    from laplace.engine.compaction_submergence import CEREMONY_SUSPENSION_PATH, CEREMONY_SUSPENSION_SHA256, INTEGRATED_ROOTS
    from laplace.representation.semantic_vertical import COVERAGE_SCHEMA, DIRECT_COORDINATION_HANDLE, DIRECT_COORDINATION_PATH, HIERARCHY_DERIVATION_HANDLE, HIERARCHY_DERIVATION_PATH, REGULARIZATION_DESIGN_HANDLE, REGULARIZATION_DESIGN_PATH, REGULARIZATION_RULING_HANDLE, REGULARIZATION_RULING_PATH, REQUIRED_CLASSES
    from laplace.engine.turn_reconstruction import load_heads

    heads = load_heads(root)
    profile_heads = {
        function: {
            "profile_handle": str(row["profile_handle"]),
            "goal_digest": str(row["goal_digest"]),
            "phase_policy_handle": str(row["phase_policy_handle"]),
        }
        for function, row in sorted((heads.get("profiles") or {}).items())
        if isinstance(row, Mapping)
    }
    if set(profile_heads) != {"ego", "aisthesis", "superego"}:
        raise RuntimeError("semantic cadence source tuple lacks all three profile handles")
    goal_handle = _exact_file_handle(
        GOAL_CONTEXT_PATH,
        GOAL_CONTEXT_HANDLE,
        name="goal-context",
    )
    atlas = _semantic_atlas_token(
        atlas_observation if atlas_observation is not None else current_atlas_observation(root)
    )
    policy_custody = {
        "ceremony_suspension": _exact_file_handle(
            CEREMONY_SUSPENSION_PATH,
            CEREMONY_SUSPENSION_SHA256,
            name="ceremony-suspension",
        ),
        "direct_coordination": _exact_file_handle(
            DIRECT_COORDINATION_PATH,
            DIRECT_COORDINATION_HANDLE,
            name="direct-coordination",
        ),
        "hierarchy_derivation": _exact_file_handle(
            HIERARCHY_DERIVATION_PATH,
            HIERARCHY_DERIVATION_HANDLE,
            name="hierarchy-derivation",
        ),
        "regularization_ruling": _exact_file_handle(
            REGULARIZATION_RULING_PATH,
            REGULARIZATION_RULING_HANDLE,
            name="regularization-ruling",
        ),
        "regularization_design": _exact_file_handle(
            REGULARIZATION_DESIGN_PATH,
            REGULARIZATION_DESIGN_HANDLE,
            name="regularization-design",
        ),
    }
    body = {
        "schema_version": "laplace.semantic-fold-source-tuple/2",
        "git": {"commit": source_commit, "tree": source_tree},
        "atlas": atlas,
        "coverage_contract": {
            "schema_version": COVERAGE_SCHEMA,
            "required_classes": list(REQUIRED_CLASSES),
        },
        "profile_heads_handle": str(heads["heads_handle"]),
        "profile_heads": profile_heads,
        "profile_handles": {
            function: row["profile_handle"]
            for function, row in sorted(profile_heads.items())
        },
        "goal_context_handle": goal_handle,
        "policy_roots": {
            **dict(sorted(INTEGRATED_ROOTS.items())),
            **policy_custody,
        },
        "builder": {
            "entry": "scripts/semantic_cadence.py --worker",
            "law_generation": "canonical-up-down-outer-receipt/1",
            "required_gpu": True,
        },
    }
    from laplace.engine import source_kernel_input as source_kernel
    selected = source_kernel.input_frame(root, source_kernel_inputs)
    if selected['receipts']:
        body['source_kernel'] = {'basis': selected['basis'], 'receipts': selected['receipts']}
    body["source_tuple_handle"] = digest(body)
    return body


def _source_tuple(root: Path, *, source_commit: str, source_tree: str) -> dict[str, Any]:
    """Compatibility spelling retained for the cadence enqueue implementation."""

    return current_source_tuple(
        root, source_commit=source_commit, source_tree=source_tree
    )


def _successful_generation_valid(
    root: Path, state: Mapping[str, Any], source_tuple: Mapping[str, Any]
) -> bool:
    receipt = state.get("last_success") or {}
    try:
        from laplace.representation.embedding_health import _read_outer_receipt, validate_fold_candidate

        outer = _read_outer_receipt(root, str(receipt["semantic_fold_receipt_object"]))
        candidate = {key: value for key, value in outer.items() if key != "receipt_object"}
        validation = validate_fold_candidate(
            root, output_commit=str(receipt["output_commit"]), outer_receipt=candidate
        )
        carried_tuple = outer.get("source_tuple")
        state_tuple = state.get("source_tuple")
        return (
            validation.get("status") == "VALIDATED"
            and outer.get("source_commit") == source_tuple["git"]["commit"]
            and isinstance(carried_tuple, Mapping)
            and isinstance(state_tuple, Mapping)
            and semantic_source_identity(carried_tuple)
            == semantic_source_identity(source_tuple)
            and semantic_source_identity(state_tuple)
            == semantic_source_identity(source_tuple)
        )
    except Exception:
        return False


def _git_ref(root: Path, ref: str) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", ref], cwd=root, capture_output=True, text=True
    )
    return result.stdout.strip() or None if result.returncode == 0 else None


def pinned_side_refs(root: Path, *, source_commit: str) -> dict[str, Any]:
    """Pin the exact prior F/receipt pair used for reuse and the later atomic CAS."""

    from laplace.representation.embedding_health import SEMANTIC_FOLD_RECEIPT_REF, SEMANTIC_FOLD_REF, _read_outer_receipt

    fold = _git_ref(root, SEMANTIC_FOLD_REF)
    receipt_object = _git_ref(root, SEMANTIC_FOLD_RECEIPT_REF)
    if bool(fold) != bool(receipt_object):
        raise RuntimeError("semantic fold side refs are incomplete")
    if not fold:
        return {
            "semantic_fold": None,
            "semantic_fold_receipt": None,
            "prior_source_commit": None,
            "prior_receipt_handle": None,
        }
    receipt = _read_outer_receipt(root, receipt_object)
    if receipt.get("output_commit") != fold:
        raise RuntimeError("semantic fold ref contradicts its exact receipt")
    prior_source = str(receipt.get("source_commit") or "")
    if not prior_source or subprocess.run(
        ["git", "merge-base", "--is-ancestor", prior_source, source_commit], cwd=root
    ).returncode != 0:
        raise RuntimeError("requested source does not descend from the prior semantic source")
    return {
        "semantic_fold": fold,
        "semantic_fold_receipt": receipt_object,
        "prior_source_commit": prior_source,
        "prior_receipt_handle": receipt["receipt_handle"],
    }


def _queued_value(
    *,
    state: Mapping[str, Any],
    source_commit: str,
    source_tree: str,
    source_tuple: Mapping[str, Any],
    side_refs: Mapping[str, Any],
) -> dict[str, Any]:
    generation = semantic_generation(source_tuple)
    return {
        "schema_version": CADENCE_SCHEMA,
        "status": "QUEUED",
        "generation": generation,
        "desired_source": {"commit": source_commit, "tree": source_tree},
        "source_tuple": dict(source_tuple),
        "side_refs": dict(side_refs),
        "pid": None,
        "process_start_token": None,
        "observed_at": _observed_at(),
        "repository_generation": {"commit": source_commit, "tree": source_tree},
        "profile_handles": dict(source_tuple["profile_handles"]),
        "goal_context_path": str(GOAL_CONTEXT_PATH),
        "queued_monotonic_ns": time.monotonic_ns(),
        "last_success": state.get("last_success"),
        "last_refusal": state.get("last_refusal"),
        "orphan_reconciliations": int(state.get("orphan_reconciliations", 0)),
        "deduplicated": False,
    }


_PRODUCER_LOG_RE = re.compile(r"^producer-[0-9a-f]{16}\.log$")


def _prune_producer_logs(keep: Path) -> int:
    """Cap the producer logs at the LIVE generation. Returns the count removed.

    These logs have exactly one writer (the Popen below) and no reader anywhere: the only
    reference is the ``log_path`` key this function's caller writes into ``cadence.json``, and
    nothing in the tree ever reads that key back. Left uncapped they accumulate one file per
    generation forever - 23 files / 2.6 MB when the internals lane measured them
    (semantic-producer-logs-have-no-reader-and-no-retention). The retention is the generation,
    so it is enforced here at the one seam that mints them rather than by a sweeper script.

    Deliberately narrow: only the exact ``producer-<16 hex>.log`` shape, only in the state root,
    and never ``cadence.json`` (``semantic_cadence.py:118`` reads that one) or any sibling.
    """
    removed = 0
    keep = keep.resolve()
    try:
        entries = list(_state_root().iterdir())
    except OSError:
        return 0
    for entry in entries:
        if not _PRODUCER_LOG_RE.match(entry.name) or entry.resolve() == keep:
            continue
        try:
            entry.unlink()
            removed += 1
        except OSError:
            continue  # a retention sweep is never worth a launch
    return removed


def _launch_locked(root: Path, value: Mapping[str, Any]) -> dict[str, Any]:
    generation = str(value["generation"])
    _write(_state_root() / "cadence.json", value)
    if os.environ.get("LAPLACE_DISABLE_SEMANTIC_CADENCE") == "1":
        return dict(value)
    log_path = _state_root() / f"producer-{generation.removeprefix('sha256:')[:16]}.log"
    _prune_producer_logs(log_path)
    with log_path.open("ab") as log:
        process = subprocess.Popen(
            [
                "/usr/bin/python3", str(root / "scripts" / "semantic_cadence.py"),
                "--worker", "--repo-root", str(root), "--generation", generation,
            ],
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env={**os.environ, "LAPLACE_REQUIRE_GPU": "1"},
        )
    running = {
        **dict(value),
        "status": "RUNNING",
        "pid": process.pid,
        "process_start_token": process_start_token(process.pid),
        "log_path": str(log_path),
    }
    _write(_state_root() / "cadence.json", running)
    return running


def enqueue(repo_root: Path | str, *, source_commit: str, source_tree: str) -> dict[str, Any]:
    """Deduplicate one frozen source coordinate and launch at most one producer process."""

    root = Path(repo_root).resolve()
    source_tuple = _source_tuple(
        root, source_commit=source_commit, source_tree=source_tree
    )
    generation = semantic_generation(source_tuple)
    side_refs = pinned_side_refs(root, source_commit=source_commit)
    with _cadence_lock():
        state = reconcile_state()
        if state.get("generation") == generation and state.get("status") == "RUNNING":
            return {**state, "deduplicated": True}
        if (
            state.get("generation") == generation
            and state.get("status") == "SUCCEEDED"
            and _successful_generation_valid(root, state, source_tuple)
        ):
            return {**state, "deduplicated": True}
        value = _queued_value(
            state=state,
            source_commit=source_commit,
            source_tree=source_tree,
            source_tuple=source_tuple,
            side_refs=side_refs,
        )
        if state.get("status") == "RUNNING":
            pending = {
                key: value[key]
                for key in (
                    "generation", "desired_source", "source_tuple", "side_refs",
                    "repository_generation", "profile_handles", "goal_context_path",
                    "queued_monotonic_ns", "observed_at",
                )
            }
            queued = {**state, "pending": pending, "pending_generation": generation}
            _write(_state_root() / "cadence.json", queued)
            return {**queued, "pending_queued": True, "deduplicated": False}
        return _launch_locked(root, value)


def finish_generation(
    generation: str,
    *,
    status: str,
    receipt: Mapping[str, Any],
    repo_root: Path | str | None = None,
) -> dict[str, Any]:
    """Finish the current producer and atomically promote its newest pending source.

    A source requested while a producer is running cannot pin the prior semantic side refs yet:
    the active producer is precisely the act that will move them. Promotion therefore pins the
    just-published pair under the same producer lock, then launches at most one successor.
    """

    with _cadence_lock():
        state = read_state()
        if state.get("generation") != generation:
            raise RuntimeError("semantic cadence generation moved before completion")
        if status not in {"SUCCEEDED", "REFUSED"}:
            raise ValueError("semantic cadence terminal status must be SUCCEEDED or REFUSED")
        field = "last_success" if status == "SUCCEEDED" else "last_refusal"
        pending = state.get("pending") if isinstance(state.get("pending"), Mapping) else None
        value = {
            **state,
            "status": status,
            "pid": None,
            "process_start_token": None,
            field: dict(receipt),
            "completed_at": _observed_at(),
        }
        value.pop("pending", None)
        value.pop("pending_generation", None)
        if pending and repo_root is not None:
            root = Path(repo_root).resolve()
            desired = pending.get("desired_source") or {}
            try:
                side_refs = pinned_side_refs(
                    root, source_commit=str(desired["commit"])
                )
                successor = {
                    **value,
                    **dict(pending),
                    "schema_version": CADENCE_SCHEMA,
                    "status": "QUEUED",
                    "side_refs": side_refs,
                    "pid": None,
                    "process_start_token": None,
                    "last_success": value.get("last_success"),
                    "last_refusal": value.get("last_refusal"),
                    "deduplicated": False,
                }
                promoted = _launch_locked(root, successor)
                return {
                    **promoted,
                    "previous_terminal_status": status,
                    "next_pending": dict(pending),
                }
            except Exception as exc:  # preserve the completed fold and pending request
                value["pending"] = dict(pending)
                value["pending_generation"] = pending.get("generation")
                value["pending_refusal"] = f"{type(exc).__name__}: {exc}"
        _write(_state_root() / "cadence.json", value)
        return {**value, "next_pending": dict(pending) if pending else None}


def record_consumption(
    *,
    kind: str,
    source_commit: str | None,
    output_commit: str | None,
    manifest_handle: str | None,
    artifact_root: str | None,
    process_generation: str | None,
    result: Mapping[str, Any],
    repository_generation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Record only the latest exact receipt per consumer; never mutate the immutable F."""

    path = _state_root() / "consumption.json"
    state = _read(path)
    latest = dict(state.get("latest") or {})
    body = {
        "kind": kind,
        "source_commit": source_commit,
        "output_commit": output_commit,
        "manifest_handle": manifest_handle,
        "artifact_root": artifact_root,
        "process_generation": process_generation,
        "process": {
            "pid": os.getpid(),
            "start_token": process_start_token(),
        },
        "observed_at": _observed_at(),
        "repository_generation": dict(repository_generation or {}),
        "fold_generation": {
            "source_commit": source_commit,
            "output_commit": output_commit,
            "manifest_handle": manifest_handle,
        },
        "result": dict(result),
    }
    body["receipt_handle"] = digest(body)
    latest[kind] = body
    value = {
        "schema_version": CONSUMPTION_SCHEMA,
        "latest": latest,
        "counts": {
            **dict(state.get("counts") or {}),
            kind: int((state.get("counts") or {}).get(kind, 0)) + 1,
        },
    }
    _write(path, value)
    return body


def read_consumption() -> dict[str, Any]:
    value = _read(_state_root() / "consumption.json")
    return value if value.get("schema_version") == CONSUMPTION_SCHEMA else {
        "schema_version": CONSUMPTION_SCHEMA, "latest": {}, "counts": {}
    }


__all__ = [
    "CADENCE_SCHEMA", "CONSUMPTION_SCHEMA", "GOAL_CONTEXT_HANDLE",
    "GOAL_CONTEXT_PATH", "enqueue", "finish_generation",
    "read_consumption", "read_state", "reconcile_state",
    "current_atlas_observation", "current_source_tuple", "pinned_side_refs",
    "process_start_token", "record_consumption", "semantic_generation",
    "semantic_source_identity",
]
