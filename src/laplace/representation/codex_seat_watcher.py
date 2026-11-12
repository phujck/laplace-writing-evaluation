"""Bind the durable Atlas seat inbox to the currently waking Codex task.

Atlas owns messages and the only durable delivery cursor. This module owns no
canonical message state: it is an ephemeral projector which notices newly queued
mail and uses the receipted Codex app-server queue API to queue one opaque wake token into
the task named by ``CODEX_THREAD_ID``. The token carries no message identity or
delivery authority. Its explicit consumption reconciles Atlas before the slot is
re-armed, so a long turn receives at most one ordinary prompt no matter how many
messages arrive. Every canonical wake rebinds the singleton projector, so old
tasks cannot compete for one seat inbox.
"""
from __future__ import annotations
from laplace.core.checkout import source_tree

import argparse
import contextlib
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_SEAT_ID = "codex-seat"
SEAT_ID = DEFAULT_SEAT_ID  # compatibility for callers that inspect the default chair
PY = "/usr/bin/python3"
DEFAULT_INTERVAL = 5.0
_RUNTIME_NAME = "laplace-codex-seat-watcher"
_MIN_INFORMATION_FRESHNESS_SECONDS = 15.0
_MAX_ACTIVE_INTERVAL_SECONDS = 10.0
WAKE_TOKEN_SCHEMA = "laplace.codex-fabric-wake-token/3"
CONSUMPTION_SCHEMA = "laplace.codex-fabric-wake-consumption/3"
ATTENTION_CONTRACT_SCHEMA = "laplace.provider-attention-contract/2"


def _implementation_paths(repo_root: Path | None = None) -> tuple[Path, ...]:
    """Name every source file whose committed bytes authorize a watcher generation."""

    root = source_tree() if repo_root is None else Path(repo_root)
    paths = [
        root / ".codex" / "hooks.json",
        root / ".codex" / "hooks" / "attention-boundary.mjs",
        root / ".codex" / "hooks" / "session-start.mjs",
        root / "scripts" / "attention_boundary.py",
        root / "scripts" / "provider_queue_gate.py",
        root / "scripts" / "seat_fabric.py",
        root / "scripts" / "wake.py",
        root / "src" / "laplace" / "representation" / "attention.py",
        root / "src" / "laplace" / "representation" / "codex_seat_watcher.py",
        root / "src" / "laplace" / "representation" / "provider_queue.py",
        root / "src" / "laplace" / "representation" / "atlas_bridge.py",
        root / "src" / "laplace" / "representation" / "recovery_coordinate.py",
        root / "src" / "laplace" / "engine" / "startup_mail_gate.py",
        root / "src" / "laplace" / "engine" / "wake.py",
    ]
    paths.extend(sorted((root / "src" / "atlas").rglob("*.py")))
    return tuple(paths)


def _activation_dirty_paths(repo_root: Path) -> tuple[str, ...]:
    """Return provisional runtime sources; an unprovable Git state fails closed.

    Publication prepares projections and retires old occupants before committing.  Requiring the
    whole imported reader path to be exact against Git is the forward half of that lock: a wake
    cannot advertise or execute a dirty generation that publication has not completed.
    """

    root = Path(repo_root).resolve()
    relative = []
    for path in _implementation_paths(root):
        try:
            relative.append(path.resolve().relative_to(root).as_posix())
        except ValueError:
            return ("<implementation-path-outside-repository>",)
    # The activation entrypoint itself is part of the permit even though the long-lived child
    # does not import it. A provisional bootstrap must not start an otherwise clean reader.
    relative.extend((
        ".codex/hooks.json",
        ".codex/hooks/attention-boundary.mjs",
        ".codex/hooks/session-start.mjs",
        "scripts/attention_boundary.py",
        "scripts/provider_queue_gate.py",
        "scripts/seat_fabric.py",
        "scripts/wake.py",
        "src/laplace/representation/attention.py",
        "src/laplace/representation/provider_queue.py",
        "src/laplace/representation/recovery_coordinate.py",
        "src/laplace/engine/startup_mail_gate.py",
        "src/laplace/engine/wake.py",
    ))
    completed = subprocess.run(
        [
            "git",
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
            "--",
            *sorted(set(relative)),
        ],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return ("<git-currentness-unavailable>",)
    dirty: set[str] = set()
    fields = completed.stdout.split(b"\0")
    index = 0
    while index < len(fields):
        field = fields[index]
        index += 1
        if not field:
            continue
        status = field[:2].decode("ascii", errors="replace")
        dirty.add(field[3:].decode("utf-8", errors="surrogateescape"))
        if status[:1] in {"R", "C"} and index < len(fields) and fields[index]:
            dirty.add(fields[index].decode("utf-8", errors="surrogateescape"))
            index += 1
    return tuple(sorted(dirty))


def _validated_seat_id(seat_id: str) -> str:
    value = seat_id.strip()
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
    if not value or any(ch not in allowed for ch in value):
        raise ValueError("logical seat id is absent or contains unsupported characters")
    return value


def _runtime_dir(seat_id: str = DEFAULT_SEAT_ID) -> Path:
    base = Path(os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir())
    seat_id = _validated_seat_id(seat_id)
    # Keep the founding codex-seat path stable while giving every additional chair its own
    # lifetime lock and target.  Atlas remains the only durable message cursor.
    suffix = "" if seat_id == DEFAULT_SEAT_ID else f"-{seat_id}"
    return base / f"{_RUNTIME_NAME}{suffix}"


def _paths(seat_id: str = DEFAULT_SEAT_ID) -> dict[str, Path]:
    root = _runtime_dir() if seat_id == DEFAULT_SEAT_ID else _runtime_dir(seat_id)
    return {
        "root": root,
        "ensure_lock": root / "ensure.lock",
        "lifetime_lock": root / "lifetime.lock",
        "pid": root / "watcher.pid",
        "target": root / "target.json",
        "status": root / "status.json",
        "consumption": root / "consumption.json",
    }


def _lease_generation(target: dict[str, Any] | None, seat_id: str) -> str | None:
    """Bind an ephemeral transport token to exactly one wake/task lease."""

    if not target:
        return None
    return "sha256:" + hashlib.sha256(json.dumps({
        "seat_id": seat_id,
        "thread_id": target.get("thread_id"),
        "bound_at": target.get("bound_at"),
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_name, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp_name)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


@contextlib.contextmanager
def _locked(path: Path, *, blocking: bool) -> Iterator[bool]:
    """Hold a small cross-process lock without adding a second state store."""

    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    handle = path.open("a+b")
    acquired = False
    try:
        if os.name == "nt":  # pragma: no cover - permanent host is Linux
            import msvcrt

            mode = msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK
            try:
                msvcrt.locking(handle.fileno(), mode, 1)
                acquired = True
            except OSError:
                acquired = False
        else:
            import fcntl

            flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
            try:
                fcntl.flock(handle.fileno(), flags)
                acquired = True
            except BlockingIOError:
                acquired = False
        yield acquired
    finally:
        if acquired:
            if os.name == "nt":  # pragma: no cover - permanent host is Linux
                import msvcrt

                handle.seek(0)
                with contextlib.suppress(OSError):
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def _parsed_timestamp(value: Any) -> float | None:
    """Return one UTC timestamp as epoch seconds; malformed status is no proof."""

    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _information_status(
    *,
    target: dict[str, Any] | None,
    status: dict[str, Any],
    pid: int,
    now: float | None = None,
    authority_cursor: int | None = None,
    seat_id: str = DEFAULT_SEAT_ID,
) -> tuple[str, str]:
    """Derive watcher state from scoped, fresh information rather than lifetime.

    A process can own the singleton lock forever while every Atlas read fails.  PID
    liveness is therefore only the first condition.  ``ACTIVE`` additionally proves
    that this exact process checked the inbox for the currently bound task, published
    a causal cursor, and did so recently without an error.  The manual watcher retires
    only on this derived state, so a wedged singleton cannot remove the fallback.
    """

    if not target:
        return "UNBOUND", "canonical Codex wake must bind CODEX_THREAD_ID"
    if target.get("seat_id") not in {None, seat_id} or status.get("seat_id") not in {
        None,
        seat_id,
    }:
        return "STALE", "watcher receipt belongs to a different logical seat"
    if not (_pid_alive(pid) and int(status.get("pid", 0) or 0) == pid):
        return "STALE", "canonical Codex wake must restart the inbox projector"
    target_thread = str(target.get("thread_id") or "")
    if not target_thread or str(status.get("thread_id") or "") != target_thread:
        return "STALE", "watcher receipt is not scoped to the currently bound task"
    if status.get("last_error") or status.get("information_state") == "fault":
        return "FAULT", "watcher is alive but its canonical Atlas observation failed"
    observed_cursor = status.get("observed_cursor")
    if type(observed_cursor) is not int or observed_cursor < 0:
        return "STARTING", "watcher owns the singleton but has not proved one Atlas observation"
    if authority_cursor is not None and observed_cursor != authority_cursor:
        return "LAGGING", "watcher receipt is behind the independently read Atlas authority tip"
    checked_at = _parsed_timestamp(status.get("checked_at"))
    if checked_at is None:
        return "STARTING", "watcher has no parseable information checkpoint"
    expected_interval = (target or {}).get("expected_interval_seconds")
    if type(expected_interval) not in {int, float}:
        return "STALE", "wake binding has no externally declared watcher interval"
    expected_interval = float(expected_interval)
    published_interval = status.get("interval_seconds")
    if type(published_interval) not in {int, float}:
        return "STALE", "watcher receipt has no numeric interval"
    if (
        expected_interval < 0.5
        or expected_interval > _MAX_ACTIVE_INTERVAL_SECONDS
        or float(published_interval) != expected_interval
    ):
        return "STALE", "watcher interval disagrees with the bounded wake authority"
    freshness = max(_MIN_INFORMATION_FRESHNESS_SECONDS, expected_interval * 3.0)
    age = (time.time() if now is None else float(now)) - checked_at
    if age < -freshness or age > freshness:
        return "STALE", "watcher information checkpoint is outside its freshness bound"
    information_state = str(status.get("information_state") or "")
    if information_state not in {"caught-up", "pending-nudge"}:
        return "STARTING", "watcher has not published a terminal information state"
    return "ACTIVE", "Fabric mail emits one scoped opaque wake token per unconsumed turn"


def _implementation_digest() -> str:
    """Bind the projector to its whole canonical Atlas read path, not one wrapper file.

    The long-lived process imports ``atlas_bridge`` and Atlas replay code once.  Hashing only this
    watcher left an ACTIVE process running old reader semantics after either dependency changed;
    a fresh wake succeeded while the watcher kept failing.  The Atlas package is small enough to
    bind whole, and this digest runs only at wake/startup rather than on each poll.
    """

    repo_root = source_tree()
    paths = _implementation_paths(repo_root)
    digest = hashlib.sha256()
    for path in paths:
        relative = path.resolve().relative_to(repo_root.resolve()).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def _stop_process(pid: int, *, timeout: float = 10.0) -> None:
    """Stop our stale singleton before replacing it; never run two seat projectors."""

    if not _pid_alive(pid):
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + timeout
    while _pid_alive(pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    if _pid_alive(pid):
        raise RuntimeError("stale Codex seat watcher did not stop after SIGTERM")


def _clear_atlas_store_cache() -> None:
    """Force the next failed watcher retry to cold-replay canonical Atlas state.

    The watcher is deliberately long-lived while the runtime store and reader code move beneath
    it.  A cached incremental materialization can therefore refuse even though a fresh process
    reconstructs cleanly.  Cache state is disposable; Atlas remains the sole message cursor.
    """

    from laplace.representation import atlas_bridge

    atlas_bridge._store_at.cache_clear()
    atlas_bridge._read_store_at.cache_clear()


def _prepare_projection_transition() -> dict[str, Any]:
    """Complete the disposable schema transition without activating a reader."""

    from laplace.representation import atlas_bridge

    return atlas_bridge.prepare_seat_mail_projection()


def _retire_provider_attention_for_token(
    *, wake_token: Mapping[str, Any] | None, thread_id: str
) -> dict[str, Any]:
    """Retire only the exact body committed by one outstanding token receipt."""

    if not isinstance(wake_token, Mapping):
        return {
            "status": "NO-OUTSTANDING-TOKEN",
            "thread_id": thread_id,
            "arbitrary_user_input_policy": "PRESERVED",
        }
    from laplace.representation import provider_queue

    provider_submission = wake_token.get("provider_submission")
    try:
        expected_client_id = provider_queue.attention_client_message_id(wake_token)
    except provider_queue.ProviderQueueError as exc:
        expected_client_id = None
        scope_error = str(exc)
    else:
        scope_error = None
    prompt_digest = str(
        (provider_submission or {}).get("prompt_digest")
        if isinstance(provider_submission, Mapping)
        else ""
    )
    if (
        scope_error
        or not isinstance(provider_submission, Mapping)
        or provider_submission.get("schema_version")
        not in {provider_queue.QUEUE_PRECOMMIT_SCHEMA, provider_queue.QUEUE_RECEIPT_SCHEMA}
        or provider_submission.get("thread_id") != thread_id
        or provider_submission.get("client_user_message_id") != expected_client_id
        or provider_submission.get("owned_attention") is not True
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", prompt_digest)
    ):
        return {
            "status": "LEGACY-RESIDUE-NOT-DELETED",
            "thread_id": thread_id,
            "reason": scope_error or "outstanding token has no exact provider body commitment",
            "arbitrary_user_input_policy": "PRESERVED",
        }
    return provider_queue.retire_attention(
        thread_id=thread_id,
        client_message_id=expected_client_id,
        prompt_digest=prompt_digest,
    )


def retire_current_provider_attention(*, seat_id: str, thread_id: str) -> dict[str, Any]:
    """Retire the exact current token receipt; CLI callers cannot supply deletion identity."""

    seat_id = _validated_seat_id(seat_id)
    paths = _paths(seat_id)
    target = _read_json(paths["target"])
    status = _read_json(paths["status"]) or {}
    if not target or target.get("thread_id") != thread_id:
        raise ValueError("physical task is not the current provider-attention lease")
    return _retire_provider_attention_for_token(
        wake_token=status.get("wake_token"),
        thread_id=thread_id,
    )


def _runtime_seat_ids() -> tuple[str, ...]:
    """Discover only local ephemeral watcher occupants; Atlas remains the seat authority."""

    default = _runtime_dir(DEFAULT_SEAT_ID)
    seats = {DEFAULT_SEAT_ID}
    prefix = _RUNTIME_NAME + "-"
    for candidate in default.parent.glob(_RUNTIME_NAME + "-*"):
        if candidate.is_dir() and candidate.name.startswith(prefix):
            with contextlib.suppress(ValueError):
                seats.add(_validated_seat_id(candidate.name[len(prefix):]))
    return tuple(sorted(seats))


def publication_transition(changed_paths: Sequence[str]) -> dict[str, Any]:
    """Prepare dependent projections and retire old occupants before publication checkin."""

    normalized = tuple(sorted({str(path) for path in changed_paths}))
    if (
        os.environ.get("LAPLACE_TEST_PROCESS") == "1"
        and os.environ.get("LAPLACE_TEST_WATCHER_TRANSITION") != "1"
    ):
        return {
            "schema_version": "laplace.watcher-publication-transition/1",
            "status": "TEST-ISOLATED",
            "changed_paths": list(normalized),
            "runtime_activation": "FORBIDDEN-TEST-PROCESS",
        }
    relevant = tuple(
        path
        for path in normalized
        if path in {
            ".codex/hooks.json",
            ".codex/hooks/attention-boundary.mjs",
            ".codex/hooks/session-start.mjs",
            "scripts/attention_boundary.py",
            "scripts/provider_queue_gate.py",
            "scripts/seat_fabric.py",
            "src/laplace/representation/codex_seat_watcher.py",
            "src/laplace/representation/atlas_bridge.py",
            "src/laplace/representation/attention.py",
            "src/laplace/representation/provider_queue.py",
            "src/laplace/representation/recovery_coordinate.py",
            "src/laplace/engine/startup_mail_gate.py",
            "src/laplace/engine/wake.py",
            "scripts/wake.py",
        }
        or path.startswith("src/atlas/")
    )
    if not relevant:
        return {
            "schema_version": "laplace.watcher-publication-transition/1",
            "status": "NOT-REQUIRED",
            "changed_paths": list(normalized),
            "runtime_activation": "UNCHANGED",
        }

    current_digest = _implementation_digest()
    retired = []
    provider_retirements = []
    for seat_id in _runtime_seat_ids():
        paths = _paths(seat_id)
        target = _read_json(paths["target"]) or {}
        try:
            pid = int(paths["pid"].read_text(encoding="utf-8").strip())
        except (FileNotFoundError, OSError, ValueError):
            pid = 0
        status = _read_json(paths["status"]) or {}
        if _pid_alive(pid):
            _stop_process(pid)
            retired.append({
                "seat_id": seat_id,
                "pid": pid,
                "loaded_implementation_digest": status.get("implementation_digest"),
            })
        thread_id = str(target.get("thread_id") or "")
        if thread_id:
            provider_retirements.append(_retire_provider_attention_for_token(
                wake_token=status.get("wake_token"),
                thread_id=thread_id,
            ))
        _write_json(paths["status"], {
            **status,
            "pid": 0,
            "information_state": "retired-before-projection-migration",
            "transition_state": "RETIRED-BEFORE-PROJECTION-MIGRATION",
            "replacement_implementation_digest": current_digest,
            "last_error": None,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "wake_token": None,
        })
        paths["pid"].write_text("0", encoding="utf-8")
    # No reader which imported the old schema remains alive. Only now may the disposable
    # projection migrate; a failure leaves every occupant stopped and publication uncommitted.
    prepared = _prepare_projection_transition()
    return {
        "schema_version": "laplace.watcher-publication-transition/1",
        "status": "READY-NOT-ACTIVE",
        "changed_paths": list(normalized),
        "dependent_paths": list(relevant),
        "projection_transition": prepared,
        "implementation_digest": current_digest,
        "retired_runtime_occupants": retired,
        "provider_queue_retirements": provider_retirements,
        "runtime_activation": "WITHHELD-UNTIL-EXPLICIT-ENSURE",
        "steady_state_contract": "recipient-local O(delta); no provider snapshot",
    }


def _pending_from_provider(
    state: dict[str, Any], seat_id: str = DEFAULT_SEAT_ID
) -> list[dict[str, Any]]:
    """Project one logical seat's pending mail across assumption/fibre partitions."""

    cursors = {
        (row.get("assumption"), row.get("fibre")): int(row.get("cursor", 0))
        for row in state.get("seat_cursors", {}).get(seat_id, [])
    }
    pending: list[dict[str, Any]] = []
    for materialized in state.get("messages", {}).values():
        message = materialized.get("message", {})
        context = (materialized.get("assumption"), materialized.get("fibre"))
        if (
            materialized.get("status") == "queued"
            and message.get("recipient_seat_id") == seat_id
            and int(message.get("cursor", 0)) > cursors.get(context, 0)
        ):
            pending.append(message)
    return sorted(pending, key=lambda message: int(message.get("cursor", 0)))


def _pending_for_codex(seat_id: str = DEFAULT_SEAT_ID) -> list[dict[str, Any]]:
    """Cold/read-once face retained for wake baseline capture and diagnostics."""

    from laplace.representation import atlas_bridge

    observation = atlas_bridge.seat_mail_observation(
        seat_id=seat_id, previous_mail_token=None
    )
    pending = observation.get("pending_messages")
    if not isinstance(pending, list):
        raise RuntimeError("cold seat-mail observation did not expose pending rows")
    return pending


def _pending_baseline(
    seat_id: str = DEFAULT_SEAT_ID,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Capture one task lease's canonical pending face and recipient revision together."""

    from laplace.representation import atlas_bridge

    observation = atlas_bridge.seat_mail_observation(
        seat_id=seat_id, previous_mail_token=None
    )
    pending = observation.get("pending_messages")
    mail_token = observation.get("mail_token")
    if not isinstance(pending, list) or not isinstance(mail_token, dict):
        raise RuntimeError("cold seat-mail observation did not expose its complete baseline")
    _mail_revision(mail_token)
    return pending, mail_token


def _pending_observation(
    previous_token: dict[str, Any] | None,
    seat_id: str = DEFAULT_SEAT_ID,
) -> tuple[dict[str, Any], list[dict[str, Any]] | None]:
    """Observe one seat token; load its pending rows only after recipient-local drift."""

    from laplace.representation import atlas_bridge

    observation = atlas_bridge.seat_mail_observation(
        seat_id=seat_id,
        previous_mail_token=previous_token,
    )
    pending = observation.get("pending_messages") if observation["changed"] else None
    if pending is not None and not isinstance(pending, list):
        raise RuntimeError("changed seat-mail observation did not expose pending rows")
    return observation, pending


def _pending_tip(messages: Sequence[dict[str, Any]]) -> int:
    """Return only the causal high-water mark; never retain a shadow message ledger."""

    return max((int(message.get("cursor", 0)) for message in messages), default=0)


def _mail_revision(mail_token: dict[str, Any] | None) -> int:
    """Return the recipient-local revision which covers status as well as message identity."""

    if not isinstance(mail_token, dict):
        return 0
    revision = mail_token.get("revision_cursor")
    if type(revision) is not int or revision < 0:
        raise RuntimeError("seat-mail token has no valid recipient revision")
    return revision


def _new_wake_token(
    *,
    seat_id: str,
    thread_id: str,
    lease_generation: str,
    pending_tip: int,
    mail_revision: int,
) -> dict[str, Any]:
    prepared_at = datetime.now(timezone.utc).isoformat()
    token = "wake:" + hashlib.sha256(json.dumps({
        "seat_id": seat_id,
        "thread_id": thread_id,
        "lease_generation": lease_generation,
        "pending_tip_at_prepare": pending_tip,
        "mail_revision_at_prepare": mail_revision,
        "prepared_at": prepared_at,
        "nonce": time.time_ns(),
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return {
        "schema_version": WAKE_TOKEN_SCHEMA,
        "token": token,
        "seat_id": seat_id,
        "thread_id": thread_id,
        "lease_generation": lease_generation,
        "pending_tip_at_prepare": pending_tip,
        "mail_revision_at_prepare": mail_revision,
        "prepared_at": prepared_at,
        "transport_state": "PREPARED_UNRECEIPTED",
        "transport_attempts": 0,
    }


def _resume_transport_token(
    wake_token: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Resume one unreceipted transport attempt without inventing exactly-once proof."""

    if not wake_token:
        return None
    resumed = dict(wake_token)
    if (
        resumed.get("transport_state") == "AMBIGUOUS_UNRECEIPTED"
        and int(resumed.get("transport_attempts", 0) or 0) < 3
    ):
        resumed["transport_state"] = "PREPARED_UNRECEIPTED"
        resumed["restart_retry"] = True
    return resumed


def _dispatch_wake_token(
    wake_token: dict[str, Any],
    *,
    prompt: str,
    persist_prepared: Callable[[], None],
    persist_receipted: Callable[[], None],
    queue: Callable[[], dict[str, Any]],
) -> None:
    """Persist an exact body precommit before enqueue, then its exact receipt."""

    from laplace.representation import provider_queue

    wake_token["transport_attempts"] = int(
        wake_token.get("transport_attempts", 0) or 0
    ) + 1
    wake_token["last_attempt_started_at"] = datetime.now(timezone.utc).isoformat()
    wake_token["transport_state"] = "PREPARED_UNRECEIPTED"
    expected_client_id = provider_queue.attention_client_message_id(wake_token)
    expected_prompt_digest = "sha256:" + hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    wake_token["provider_submission"] = {
        "schema_version": provider_queue.QUEUE_PRECOMMIT_SCHEMA,
        "thread_id": wake_token.get("thread_id"),
        "queued_submission_id": None,
        "client_user_message_id": expected_client_id,
        "prompt_digest": expected_prompt_digest,
        "owned_attention": True,
        "transport": "codex-app-server-thread-queue-precommit",
    }
    persist_prepared()
    try:
        receipt = queue()
    except Exception:
        wake_token["transport_state"] = "AMBIGUOUS_UNRECEIPTED"
        raise
    prompt_digest = str((receipt or {}).get("prompt_digest") or "")
    if (
        not isinstance(receipt, dict)
        or receipt.get("schema_version") != provider_queue.QUEUE_RECEIPT_SCHEMA
        or not receipt.get("queued_submission_id")
        or receipt.get("thread_id") != wake_token.get("thread_id")
        or receipt.get("client_user_message_id") != expected_client_id
        or receipt.get("owned_attention") is not True
        or prompt_digest != expected_prompt_digest
    ):
        wake_token["transport_state"] = "AMBIGUOUS_UNRECEIPTED"
        raise RuntimeError("provider attention enqueue returned no exact body-bound receipt")
    wake_token["provider_submission"] = receipt
    wake_token["transport_state"] = "QUEUED_RECEIPTED"
    wake_token["queued_at"] = datetime.now(timezone.utc).isoformat()
    persist_receipted()


def _should_issue_wake(
    pending: Sequence[dict[str, Any]],
    *,
    current_mail_revision: int,
    covered_mail_revision: int,
    wake_token: dict[str, Any] | None,
) -> bool:
    """Re-arm on a recipient state transition, including queued-to-pulled movement."""

    return bool(
        pending
        and wake_token is None
        and current_mail_revision > covered_mail_revision
    )


def _attention_prompt(
    *,
    thread_id: str,
    wake_token: dict[str, Any],
    seat_id: str = DEFAULT_SEAT_ID,
) -> str:
    token = str(wake_token["token"])
    consume = (
        f"{PY} scripts/seat_fabric.py consume-wake --seat {seat_id} "
        f"--thread {thread_id} --token {token}"
    )
    return (
        f"[Eigen Fabric watcher] One opaque Fabric attention token is outstanding for "
        f"{seat_id} on this task under {ATTENTION_CONTRACT_SCHEMA}: {token}. "
        "It carries no message IDs, bodies, cursor advance, "
        "or delivery claim, and a delayed duplicate may execute after canonical state changed. "
        f"Consume and canonically reconcile it first with exactly: {consume}. Then inspect the "
        "returned current pending face; pull only genuinely queued mail, reconstruct it through "
        "typed evaluation, and acknowledge only with the exact reconstruction proof."
    )


def _queue_nudge(
    *,
    thread_id: str,
    wake_token: dict[str, Any],
    codex_bin: str,
    seat_id: str = DEFAULT_SEAT_ID,
    prompt: str | None = None,
) -> dict[str, Any]:
    prompt = prompt or _attention_prompt(
        thread_id=thread_id,
        seat_id=seat_id,
        wake_token=wake_token,
    )
    from laplace.representation import provider_queue

    return provider_queue.queue_attention(
        thread_id=thread_id,
        wake_token=wake_token,
        prompt=prompt,
        codex_bin=codex_bin,
        timeout=20,
    )


def classify_attention_prompt(prompt: str) -> str:
    """Make pre-token watcher prompts mechanically inert after reconstruction."""

    if not prompt.startswith("[Eigen Fabric watcher]"):
        return "NOT-WATCHER-ATTENTION"
    tokens = re.findall(r"wake:[0-9a-f]{64}", prompt)
    if (
        ATTENTION_CONTRACT_SCHEMA in prompt
        and len(set(tokens)) == 1
        and "message:" not in prompt
    ):
        return "OPAQUE-TOKEN-CANDIDATE"
    return "LEGACY-INERT"


def attention_prompt_currentness(
    prompt: str, *, seat_id: str, thread_id: str
) -> dict[str, Any]:
    """Prove a token-shaped prompt against the live replaceable lease."""

    classification = classify_attention_prompt(prompt)
    if classification == "NOT-WATCHER-ATTENTION":
        return {"state": "NOT-WATCHER-ATTENTION", "actionable": None}
    if classification == "LEGACY-INERT":
        return {"state": "LEGACY-INERT", "actionable": False}
    from laplace.representation import provider_queue

    token = sorted(set(re.findall(r"wake:[0-9a-f]{64}", prompt)))[0]
    seat_id = _validated_seat_id(seat_id)
    paths = _paths(seat_id)
    target = _read_json(paths["target"])
    status = _read_json(paths["status"]) or {}
    generation = _lease_generation(target, seat_id)
    outstanding = status.get("wake_token")
    receipt = _read_json(paths["consumption"])
    scope = {
        "token": token,
        "seat_id": seat_id,
        "thread_id": thread_id,
        "lease_generation": generation,
    }
    reasons = []
    if not target or target.get("thread_id") != thread_id:
        reasons.append("physical task is not the current seat lease")
    if not isinstance(outstanding, dict) or any(
        outstanding.get(name) != value for name, value in scope.items()
    ):
        reasons.append("token is not the exact outstanding lease token")
    if isinstance(outstanding, dict) and outstanding.get("schema_version") != WAKE_TOKEN_SCHEMA:
        reasons.append("token schema is not current")
    provider_submission = (
        outstanding.get("provider_submission") if isinstance(outstanding, dict) else None
    )
    actual_prompt_digest = "sha256:" + hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    expected_client_id = (
        provider_queue.attention_client_message_id(outstanding)
        if isinstance(outstanding, dict)
        else None
    )
    precommit = (
        isinstance(provider_submission, dict)
        and provider_submission.get("schema_version") == provider_queue.QUEUE_PRECOMMIT_SCHEMA
        and outstanding.get("transport_state")
        in {"PREPARED_UNRECEIPTED", "AMBIGUOUS_UNRECEIPTED"}
        and not provider_submission.get("queued_submission_id")
    ) if isinstance(outstanding, dict) else False
    receipted = (
        isinstance(provider_submission, dict)
        and provider_submission.get("schema_version") == provider_queue.QUEUE_RECEIPT_SCHEMA
        and outstanding.get("transport_state") == "QUEUED_RECEIPTED"
        and bool(provider_submission.get("queued_submission_id"))
    ) if isinstance(outstanding, dict) else False
    if (
        not isinstance(provider_submission, dict)
        or not (precommit or receipted)
        or provider_submission.get("thread_id") != thread_id
        or provider_submission.get("client_user_message_id") != expected_client_id
        or provider_submission.get("owned_attention") is not True
        or provider_submission.get("prompt_digest") != actual_prompt_digest
    ):
        reasons.append("provider prompt body does not match its exact queued receipt")
    if _matching_consumption(receipt, scope):
        reasons.append("token is already consumed")
    if projection(seat_id).get("status") != "ACTIVE":
        reasons.append("watcher generation is not ACTIVE")
    return {
        "state": "STALE-INERT" if reasons else "CURRENT",
        "actionable": not reasons,
        "seat_id": seat_id,
        "thread_id": thread_id,
        "lease_generation": generation,
        "token": token,
        "reasons": reasons,
    }


def _resumed_wake_state(
    target: dict[str, Any] | None,
    prior_status: dict[str, Any],
    *,
    seat_id: str,
    implementation_digest: str,
    consumption: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, int, int]:
    """Resume only a current, unconsumed token on the exact same task lease."""

    thread_id = str((target or {}).get("thread_id", ""))
    generation = _lease_generation(target, seat_id)
    baseline_tip = int((target or {}).get("baseline_pending_tip", 0) or 0)
    baseline_revision = int((target or {}).get("baseline_mail_revision", 0) or 0)
    if (
        prior_status.get("thread_id") != thread_id
        or prior_status.get("lease_generation") != generation
        or prior_status.get("implementation_digest") != implementation_digest
    ):
        return None, baseline_tip, baseline_revision
    token = prior_status.get("wake_token")
    if not isinstance(token, dict) or (
        token.get("schema_version") != WAKE_TOKEN_SCHEMA
        or type(token.get("mail_revision_at_prepare")) is not int
        or token.get("mail_revision_at_prepare", -1) < 0
        or token.get("seat_id") != seat_id
        or token.get("thread_id") != thread_id
        or token.get("lease_generation") != generation
    ):
        token = None
    covered = max(
        baseline_tip, int(prior_status.get("covered_pending_tip", 0) or 0)
    )
    covered_revision = max(
        baseline_revision, int(prior_status.get("covered_mail_revision", 0) or 0)
    )
    if _matching_consumption(consumption, token):
        covered = max(covered, int(consumption.get("pending_tip_cursor", 0) or 0))
        covered_revision = max(
            covered_revision,
            int(consumption.get("mail_revision_cursor", 0) or 0),
        )
        token = None
    return token, covered, covered_revision


def _matching_consumption(
    receipt: dict[str, Any] | None,
    wake_token: dict[str, Any] | None,
) -> bool:
    return bool(
        receipt
        and wake_token
        and receipt.get("schema_version") == CONSUMPTION_SCHEMA
        and receipt.get("token") == wake_token.get("token")
        and receipt.get("seat_id") == wake_token.get("seat_id")
        and receipt.get("thread_id") == wake_token.get("thread_id")
        and receipt.get("lease_generation") == wake_token.get("lease_generation")
        and receipt.get("canonical_reconciled") is True
    )


def _canonical_retirement_receipt(
    *,
    wake_token: dict[str, Any] | None,
    pending: Sequence[dict[str, Any]],
    covered_pending_tip: int,
    current_mail_revision: int,
    covered_mail_revision: int,
    observation: dict[str, Any],
    seat_id: str,
    thread_id: str,
    lease_generation: str | None,
) -> dict[str, Any] | None:
    """Retire stale attention when canonical obligations are absent/already covered."""

    if wake_token is None or (
        pending and current_mail_revision > covered_mail_revision
    ):
        return None
    drift = dict(observation["drift_token"])
    return {
        "schema_version": CONSUMPTION_SCHEMA,
        "token": wake_token["token"],
        "seat_id": seat_id,
        "thread_id": thread_id,
        "lease_generation": lease_generation,
        "consumed_at": datetime.now(timezone.utc).isoformat(),
        "canonical_reconciled": True,
        "authority_cursor": drift.get("cursor"),
        "head_event_id": drift.get("head_event_id"),
        "head_record_digest": drift.get("head_record_digest"),
        "pending_count": len(pending),
        "pending_tip_cursor": _pending_tip(pending),
        "covered_pending_tip_cursor": covered_pending_tip,
        "mail_revision_cursor": current_mail_revision,
        "mail_token": dict(observation["mail_token"]),
        "delivery_claim": "none",
        "attention_state": "RETIRED-BY-CANONICAL-RECONCILIATION",
        "retirement_reason": (
            "canonical obligations are terminal, absent, or already covered"
        ),
    }


def consume_wake_token(
    *, seat_id: str, thread_id: str, token: str
) -> dict[str, Any]:
    """Consume one ephemeral token and reconcile the canonical Atlas inbox.

    This is not a pull, reconstruction, acknowledgement, or second delivery ledger. The
    receipt stores only task scope and the causal/pending high-water marks needed to safely
    re-arm the unreceipted app transport.
    """

    seat_id = _validated_seat_id(seat_id)
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
    if not thread_id or any(ch not in allowed for ch in thread_id):
        raise ValueError("thread id is absent or contains unsupported characters")
    if not token.startswith("wake:"):
        raise ValueError("wake token is malformed")
    paths = _paths(seat_id)
    with _locked(paths["ensure_lock"], blocking=True):
        target = _read_json(paths["target"])
        status = _read_json(paths["status"]) or {}
        generation = _lease_generation(target, seat_id)
        expected_scope = {
            "seat_id": seat_id,
            "thread_id": thread_id,
            "lease_generation": generation,
        }
        if not target or target.get("thread_id") != thread_id:
            raise ValueError("wake token belongs to a stale or unbound task")
        prior_receipt = _read_json(paths["consumption"])
        token_face = {"token": token, **expected_scope}
        if _matching_consumption(prior_receipt, token_face):
            cleanup = prior_receipt.get("provider_queue_cleanup")
            if not isinstance(cleanup, dict):
                try:
                    cleanup = _retire_provider_attention_for_token(
                        wake_token=status.get("wake_token"),
                        thread_id=thread_id,
                    )
                except Exception as exc:  # canonical consumption stays authoritative
                    cleanup = {
                        "status": "UNAVAILABLE",
                        "reason": f"{type(exc).__name__}: {exc}",
                    }
            return {**prior_receipt, "provider_queue_cleanup": cleanup, "idempotent": True}
        outstanding = status.get("wake_token")
        if not isinstance(outstanding, dict) or any(
            outstanding.get(name) != value for name, value in {
                "token": token,
                **expected_scope,
            }.items()
        ):
            raise ValueError("wake token is not outstanding for this seat/task lease")

        from laplace.representation import atlas_bridge

        observation = atlas_bridge.seat_mail_observation(
            seat_id=seat_id, previous_mail_token=None
        )
        pending = observation.get("pending_messages")
        if not isinstance(pending, list):
            raise RuntimeError("canonical reconciliation did not expose seat mail")
        drift = dict(observation["drift_token"])
        mail_token = dict(observation["mail_token"])
        mail_revision = _mail_revision(mail_token)
        receipt = {
            "schema_version": CONSUMPTION_SCHEMA,
            "token": token,
            **expected_scope,
            "consumed_at": datetime.now(timezone.utc).isoformat(),
            "canonical_reconciled": True,
            "authority_cursor": drift.get("cursor"),
            "head_event_id": drift.get("head_event_id"),
            "head_record_digest": drift.get("head_record_digest"),
            "pending_count": len(pending),
            "pending_tip_cursor": _pending_tip(pending),
            "mail_revision_cursor": mail_revision,
            "mail_token": mail_token,
            "delivery_claim": "none",
            "message_cursor_owner": "Atlas seat fabric",
            "transport_semantics": "provider-receipted idempotent attention; Atlas remains canonical",
            "action": (
                f"inspect canonical pending mail with {PY} scripts/seat_fabric.py "
                f"inbox --seat {seat_id}; pull/reconstruct/ack remain separate exact acts"
            ),
        }
        _write_json(paths["consumption"], receipt)
        try:
            cleanup = _retire_provider_attention_for_token(
                wake_token=outstanding,
                thread_id=thread_id,
            )
        except Exception as exc:  # the hook makes any survivor inert
            cleanup = {"status": "UNAVAILABLE", "reason": f"{type(exc).__name__}: {exc}"}
        receipt["provider_queue_cleanup"] = cleanup
        _write_json(paths["consumption"], receipt)
        return {**receipt, "idempotent": False}


def _authority_cursor() -> int:
    """Read the compact Atlas tip independently of the worker's status receipt."""

    from laplace.representation import atlas_bridge

    cursor = atlas_bridge.drift_token().get("cursor")
    if type(cursor) is not int or cursor < 0:
        raise RuntimeError("Atlas authority tip has no valid cursor")
    return cursor


def projection(seat_id: str = DEFAULT_SEAT_ID) -> dict[str, Any]:
    """Read the wake-facing watcher projection; absence is never reported as active."""

    seat_id = _validated_seat_id(seat_id)
    paths = _paths(seat_id)
    target = _read_json(paths["target"])
    status = _read_json(paths["status"]) or {}
    try:
        pid = int(paths["pid"].read_text(encoding="utf-8").strip())
    except (FileNotFoundError, OSError, ValueError):
        pid = 0
    authority_cursor: int | None = None
    authority_error: str | None = None
    try:
        authority_cursor = _authority_cursor()
    except Exception as exc:  # noqa: BLE001 - a failed independent proof is visible health
        authority_error = f"{type(exc).__name__}: {exc}"
    state, action = _information_status(
        target=target,
        status=status,
        pid=pid,
        authority_cursor=authority_cursor,
        seat_id=seat_id,
    )
    current_implementation_digest: str | None = None
    implementation_error: str | None = None
    try:
        current_implementation_digest = _implementation_digest()
    except Exception as exc:  # noqa: BLE001 - currentness must fail closed
        implementation_error = f"{type(exc).__name__}: {exc}"
    loaded_implementation_digest = status.get("implementation_digest")
    if implementation_error is not None:
        state = "FAULT"
        action = "watcher current implementation digest could not be computed"
    elif (
        _pid_alive(pid)
        and loaded_implementation_digest != current_implementation_digest
    ):
        state = "STALE-IMPLEMENTATION"
        action = (
            "stop or replace the stale watcher before reader authority can be ACTIVE"
        )
    if authority_error is not None and state == "ACTIVE":
        state = "FAULT"
        action = "wake could not independently read the Atlas authority tip"
    if status.get("transition_state") == "ACTIVATION-WITHHELD-DIRTY-IMPLEMENTATION":
        state = "WITHHELD"
        action = (
            "watcher-critical source is provisional; publish the forward transition before "
            "runtime activation"
        )
    lease_generation = _lease_generation(target, seat_id)
    wake_token = status.get("wake_token")
    return {
        "status": state,
        "transport": "codex app-server thread/queue",
        "seat_id": seat_id,
        "target_thread_id": target.get("thread_id") if target else None,
        "lease_generation": lease_generation,
        "bound_at": target.get("bound_at") if target else None,
        "pid": pid or None,
        "interval_seconds": status.get("interval_seconds", DEFAULT_INTERVAL),
        "checked_at": status.get("checked_at"),
        "last_nudge_at": status.get("last_nudge_at"),
        "wake_token": wake_token if isinstance(wake_token, dict) else None,
        "outstanding_wake_token": isinstance(wake_token, dict),
        "covered_pending_tip": status.get("covered_pending_tip", 0),
        "covered_mail_revision": status.get("covered_mail_revision", 0),
        "observed_mail_token": status.get("observed_mail_token"),
        "last_consumed_token": status.get("last_consumed_token"),
        "last_consumed_at": status.get("last_consumed_at"),
        "last_nudge_count": status.get("last_nudge_count", 0),
        "last_error": status.get("last_error"),
        "observation_mode": status.get("observation_mode"),
        "observed_cursor": status.get("observed_cursor"),
        "authority_cursor": authority_cursor,
        "authority_error": authority_error,
        "materialization_count": status.get("materialization_count", 0),
        "idle_poll_count": status.get("idle_poll_count", 0),
        "last_materialized_at": status.get("last_materialized_at"),
        "last_information_at": status.get("last_information_at"),
        "information_state": status.get("information_state", "unknown"),
        "loaded_implementation_digest": loaded_implementation_digest,
        "current_implementation_digest": current_implementation_digest,
        "implementation_error": implementation_error,
        "transport_semantics": "provider-receipted idempotent attention; Atlas remains canonical",
        "attention_contract": {
            "schema_version": ATTENTION_CONTRACT_SCHEMA,
            "required_prompt": "opaque-token-scoped-to-seat-task-lease-generation",
            "legacy_id_bearing_prompt": "INERT",
            "checkpoint_rule": (
                "reconcile canonical seat obligations before resuming or issuing attention"
            ),
        },
        "efficiency": {
            "idle_poll_count": status.get("idle_poll_count", 0),
            "materialization_count": status.get("materialization_count", 0),
            "turn_displacement_prompt_bound": 1,
            "outstanding_prompt_slots": 1 if isinstance(wake_token, dict) else 0,
            "transport_ambiguity_count": status.get("transport_ambiguity_count", 0),
        },
        "action": action,
        "message_cursor_owner": "Atlas seat fabric",
    }


def ensure(
    *,
    thread_id: str,
    repo_root: Path,
    interval: float = DEFAULT_INTERVAL,
    seat_id: str = DEFAULT_SEAT_ID,
) -> dict[str, Any]:
    """Bind one logical seat's singleton watcher to ``thread_id``."""

    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
    if not thread_id or any(ch not in allowed for ch in thread_id):
        raise ValueError("CODEX_THREAD_ID is absent or contains unsupported characters")
    seat_id = _validated_seat_id(seat_id)
    interval = float(interval)
    if interval < 0.5 or interval > _MAX_ACTIVE_INTERVAL_SECONDS:
        raise ValueError(
            f"watcher interval must be between 0.5 and {_MAX_ACTIVE_INTERVAL_SECONDS:g} seconds"
        )
    paths = _paths(seat_id)
    paths["root"].mkdir(parents=True, exist_ok=True, mode=0o700)
    with _locked(paths["ensure_lock"], blocking=True):
        prior_target = _read_json(paths["target"])
        try:
            prior_pid = int(paths["pid"].read_text(encoding="utf-8").strip())
        except (FileNotFoundError, OSError, ValueError):
            prior_pid = 0
        prior_status = _read_json(paths["status"]) or {}
        current_digest = _implementation_digest()
        dirty_implementation = _activation_dirty_paths(repo_root)
        if dirty_implementation:
            # A wake during a provisional source transition is a retirement act, never an
            # activation. Any already queued opaque token will fail consumption because it is no
            # longer the status receipt's outstanding token.
            if _pid_alive(prior_pid):
                _stop_process(prior_pid)
            try:
                provider_retirement = _retire_provider_attention_for_token(
                    wake_token=prior_status.get("wake_token"),
                    thread_id=str((prior_target or {}).get("thread_id") or thread_id),
                )
            except Exception as exc:
                provider_retirement = {
                    "status": "UNAVAILABLE",
                    "reason": f"{type(exc).__name__}: {exc}",
                }
            paths["pid"].write_text("0", encoding="utf-8")
            _write_json(paths["status"], {
                **prior_status,
                "pid": 0,
                "seat_id": seat_id,
                "implementation_digest": current_digest,
                "information_state": "retired-provisional-implementation",
                "transition_state": "ACTIVATION-WITHHELD-DIRTY-IMPLEMENTATION",
                "activation_dirty_paths": list(dirty_implementation),
                "last_error": None,
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "provider_queue_retirement": provider_retirement,
                "wake_token": None,
            })
            return projection() if seat_id == DEFAULT_SEAT_ID else projection(seat_id)
        prior_health, _prior_action = _information_status(
            target=prior_target,
            status=prior_status,
            pid=prior_pid,
            seat_id=seat_id,
        )
        if _pid_alive(prior_pid) and (
            (prior_target or {}).get("thread_id") != thread_id
            or prior_status.get("implementation_digest") != current_digest
            or prior_health in {"FAULT", "STALE"}
        ):
            # Retirement precedes every schema read.  An old process may not remain ACTIVE while
            # new projection code attempts to interpret an undeployed schema.
            _stop_process(prior_pid)
            prior_pid = 0

        projection_transition: dict[str, Any] | None = None
        replacement_required = not _pid_alive(prior_pid)
        if replacement_required:
            try:
                projection_transition = _prepare_projection_transition()
            except Exception as exc:  # noqa: BLE001 - activation must fail closed
                failure = f"{type(exc).__name__}: {exc}"
                paths["pid"].write_text("0", encoding="utf-8")
                _write_json(paths["status"], {
                    "pid": 0,
                    "thread_id": (prior_target or {}).get("thread_id"),
                    "seat_id": seat_id,
                    "implementation_digest": current_digest,
                    "information_state": "fault",
                    "transition_state": "PROJECTION-PREPARATION-FAILED",
                    "last_error": failure,
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                })
                return projection() if seat_id == DEFAULT_SEAT_ID else projection(seat_id)
        if replacement_required:
            try:
                provider_retirements = []
                prior_thread = str((prior_target or {}).get("thread_id") or "")
                if prior_thread:
                    provider_retirements.append(_retire_provider_attention_for_token(
                        wake_token=prior_status.get("wake_token"),
                        thread_id=prior_thread,
                    ))
            except Exception as exc:  # reader activation fails closed
                failure = f"{type(exc).__name__}: {exc}"
                paths["pid"].write_text("0", encoding="utf-8")
                _write_json(paths["status"], {
                    **prior_status,
                    "pid": 0,
                    "thread_id": (prior_target or {}).get("thread_id"),
                    "seat_id": seat_id,
                    "implementation_digest": current_digest,
                    "information_state": "fault",
                    "transition_state": "PROVIDER-QUEUE-RETIREMENT-FAILED",
                    "last_error": failure,
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                    "wake_token": None,
                })
                return projection() if seat_id == DEFAULT_SEAT_ID else projection(seat_id)
            # Capture the baseline at WAKE time, not on the watcher's first pass. A
            # store reconstruction can be slow; mail arriving after wake but before
            # that first pass is new and must still nudge the task.
            baseline, baseline_mail_token = _pending_baseline(seat_id)
            target = {
                "thread_id": thread_id,
                "seat_id": seat_id,
                "repo_root": str(repo_root.resolve()),
                "bound_at": datetime.now(timezone.utc).isoformat(),
                "baseline_pending_tip": _pending_tip(baseline),
                "baseline_pending_count": len(baseline),
                "baseline_mail_revision": _mail_revision(baseline_mail_token),
                "baseline_mail_token": baseline_mail_token,
                "expected_interval_seconds": interval,
                "projection_transition": projection_transition,
                "provider_queue_retirements": provider_retirements,
            }
            _write_json(paths["target"], target)
        elif (
            prior_target.get("expected_interval_seconds") != interval
            or "baseline_pending_tip" not in prior_target
            or "baseline_mail_revision" not in prior_target
            or "baseline_pending_ids" in prior_target
        ):
            target = dict(prior_target)
            target["expected_interval_seconds"] = interval
            if "baseline_pending_tip" not in target:
                baseline = _pending_for_codex(seat_id)
                target["baseline_pending_tip"] = _pending_tip(baseline)
                target["baseline_pending_count"] = len(baseline)
            if "baseline_mail_revision" not in target:
                # An old target has no proof that its current recipient revision was already
                # covered. Start conservatively at genesis: current nonterminal obligations may
                # produce one opaque reconciliation token, while terminal history stays absent.
                target["baseline_mail_revision"] = 0
                target["baseline_mail_token"] = None
            target.pop("baseline_pending_ids", None)
            if projection_transition is not None:
                target["projection_transition"] = projection_transition
            _write_json(paths["target"], target)
        try:
            pid = int(paths["pid"].read_text(encoding="utf-8").strip())
        except (FileNotFoundError, OSError, ValueError):
            pid = 0
        status = _read_json(paths["status"]) or {}
        health, _health_action = _information_status(
            target=_read_json(paths["target"]),
            status=status,
            pid=pid,
            seat_id=seat_id,
        )
        if _pid_alive(pid) and (
            status.get("implementation_digest") != _implementation_digest()
            or health in {"FAULT", "STALE"}
        ):
            # A watcher can live across many commits.  Rebinding must also bind its imported code;
            # otherwise an ACTIVE process may retry forever with a reader implementation that no
            # longer matches the one a fresh canonical wake just used successfully.  Likewise,
            # lifetime cannot preserve a faulting/stale projector: restart is the automatic cure,
            # while its outstanding nudge ids remain in the status receipt for resumption.
            _stop_process(pid)
            pid = 0
        if not _pid_alive(pid):
            env = dict(os.environ)
            source_root = str(repo_root.resolve() / "src")
            prior = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = source_root + (os.pathsep + prior if prior else "")
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "laplace.representation.codex_seat_watcher",
                    "--serve",
                    "--interval",
                    str(interval),
                    "--seat",
                    seat_id,
                ],
                cwd=repo_root,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            # ACTIVE requires the child's own INFORMATION receipt. A parent-written PID
            # and even the child's startup receipt prove only lifetime; wait until the
            # child has completed one scoped Atlas observation or exposed its fault.
            deadline = time.monotonic() + 7.0
            while time.monotonic() < deadline:
                projected = (
                    projection()
                    if seat_id == DEFAULT_SEAT_ID
                    else projection(seat_id)
                )
                state = str(projected.get("status") or "FAULT")
                if state == "ACTIVE":
                    break
                if process.poll() is not None:
                    break
                time.sleep(0.05)
    return projection() if seat_id == DEFAULT_SEAT_ID else projection(seat_id)


def ensure_from_environment(repo_root: Path) -> dict[str, Any]:
    """Wake conjugate: bind on Codex, state explicitly why no binding happened elsewhere."""

    if os.environ.get("LAPLACE_TEST_PROCESS") == "1":
        return {
            "status": "DISABLED-TEST-PROCESS",
            "action": "a test process may inspect a fixture watcher but cannot rebind the singleton",
        }
    if os.environ.get("LAPLACE_NO_SEAT_WATCHER") == "1":
        return {"status": "DISABLED", "action": "remove LAPLACE_NO_SEAT_WATCHER to restore nudges"}
    thread_id = os.environ.get("CODEX_THREAD_ID", "")
    if not thread_id:
        return {"status": "NOT_CODEX", "action": "provider has no CODEX_THREAD_ID"}
    explicit_seat_id = os.environ.get("LAPLACE_SEAT_ID", "").strip()
    from laplace.representation import atlas_bridge

    provider_session_ref = f"codex:{thread_id}"
    binding = atlas_bridge.provider_seat_binding(
        provider_session_ref=provider_session_ref
    )
    if binding.get("status") == "BOUND":
        canonical_seat_id = str(binding["seat_id"])
        if explicit_seat_id and explicit_seat_id != canonical_seat_id:
            return {
                "status": "BINDING-CONFLICT",
                "action": "remove the stale explicit seat before watcher activation",
                "provider_session_ref": provider_session_ref,
                "explicit_seat_id": explicit_seat_id,
                "canonical_seat_id": canonical_seat_id,
            }
        seat_id = canonical_seat_id
    elif binding.get("status") == "UNBOUND" and explicit_seat_id:
        # Bootstrap seam: the assigned startup gate may establish the first binding. Once the
        # provider task is bound, the branch above makes Atlas authoritative forever after.
        seat_id = explicit_seat_id
    else:
        return {
            "status": "UNBOUND" if binding.get("status") == "UNBOUND" else "BINDING-CONFLICT",
            "action": "complete or repair the assigned startup mail gate before watcher activation",
            "provider_session_ref": provider_session_ref,
            "binding_status": binding.get("status"),
        }
    return ensure(thread_id=thread_id, repo_root=repo_root, seat_id=seat_id)


def _serve(interval: float, seat_id: str = DEFAULT_SEAT_ID) -> int:
    seat_id = _validated_seat_id(seat_id)
    paths = _paths(seat_id)
    with _locked(paths["lifetime_lock"], blocking=True) as acquired:
        if not acquired:
            # A spare that never owned the singleton did no work.  A clean exit is a
            # false success signal to supervisors and startup gates.
            return 75
        paths["pid"].write_text(str(os.getpid()), encoding="utf-8")
        stopped = threading.Event()

        def stop(_signum: int, _frame: object) -> None:
            stopped.set()

        signal.signal(signal.SIGINT, stop)
        signal.signal(signal.SIGTERM, stop)
        prior_status = _read_json(paths["status"]) or {}
        initial_target = _read_json(paths["target"])
        initial_thread = str((initial_target or {}).get("thread_id", ""))
        bound_thread = initial_thread
        bound_generation = _lease_generation(initial_target, seat_id)
        implementation_digest = _implementation_digest()
        wake_token, covered_pending_tip, covered_mail_revision = _resumed_wake_state(
            initial_target,
            prior_status,
            seat_id=seat_id,
            implementation_digest=implementation_digest,
            consumption=_read_json(paths["consumption"]),
        )
        # A replacement retries the same token and stable provider client id. List-before-add
        # receipts a crash-window survivor; canonical consumption makes a delivered survivor inert.
        wake_token = _resume_transport_token(wake_token)
        last_nudge_at = prior_status.get("last_nudge_at")
        last_nudge_count = int(prior_status.get("last_nudge_count", 0) or 0)
        last_consumed_token = prior_status.get("last_consumed_token")
        last_consumed_at = prior_status.get("last_consumed_at")
        transport_ambiguity_count = int(
            prior_status.get("transport_ambiguity_count", 0) or 0
        )
        canonical_retirement_count = int(
            prior_status.get("canonical_retirement_count", 0) or 0
        )
        last_error: str | None = None
        observed_token: dict[str, Any] | None = None
        observed_mail_token: dict[str, Any] | None = None
        current_pending: list[dict[str, Any]] = []
        materialization_count = 0
        rows_loaded = 0
        observation_cpu_ns = 0
        idle_poll_count = 0
        last_materialized_at: str | None = None
        last_information_at = prior_status.get("last_information_at")
        started_at = datetime.now(timezone.utc).isoformat()

        def publish_status(*, information_state: str, checked_at: str | None) -> None:
            _write_json(paths["status"], {
                "pid": os.getpid(),
                "thread_id": bound_thread or None,
                "seat_id": seat_id,
                "lease_generation": bound_generation,
                "implementation_digest": implementation_digest,
                "interval_seconds": interval,
                "last_nudge_at": last_nudge_at,
                "wake_token": wake_token,
                "covered_pending_tip": covered_pending_tip,
                "covered_mail_revision": covered_mail_revision,
                "observed_mail_token": observed_mail_token,
                "last_consumed_token": last_consumed_token,
                "last_consumed_at": last_consumed_at,
                "last_nudge_count": last_nudge_count,
                "last_error": last_error,
                "checked_at": checked_at,
                "started_at": started_at,
                "observation_mode": "drift-token-gated-single-wake-token",
                "observed_cursor": (
                    None if observed_token is None else observed_token.get("cursor")
                ),
                "materialization_count": materialization_count,
                "provider_snapshot_materialization_count": 0,
                "seat_mail_rows_loaded": rows_loaded,
                "seat_mail_observation_cpu_ns": observation_cpu_ns,
                "idle_poll_count": idle_poll_count,
                "last_materialized_at": last_materialized_at,
                "last_information_at": last_information_at,
                "information_state": information_state,
                "transport_semantics": (
                    "provider-receipted idempotent attention; Atlas remains canonical"
                ),
                "transport_ambiguity_count": transport_ambiguity_count,
                "canonical_retirement_count": canonical_retirement_count,
            })

        # Startup receipt precedes the potentially expensive Atlas reconstruction.
        # Wake may say ACTIVE only after this child, not its parent, owns the lifetime lock.
        publish_status(information_state="starting", checked_at=None)
        while not stopped.is_set():
            target = _read_json(paths["target"])
            thread_id = str((target or {}).get("thread_id", ""))
            generation = _lease_generation(target, seat_id)
            try:
                if thread_id != bound_thread or generation != bound_generation:
                    bound_thread = thread_id
                    bound_generation = generation
                    wake_token = None
                    covered_pending_tip = int(
                        (target or {}).get("baseline_pending_tip", 0) or 0
                    )
                    covered_mail_revision = int(
                        (target or {}).get("baseline_mail_revision", 0) or 0
                    )
                observation, changed_pending = _pending_observation(
                    observed_mail_token, seat_id
                )
                observed_token = dict(observation["drift_token"])
                observed_mail_token = dict(observation["mail_token"])
                current_mail_revision = _mail_revision(observed_mail_token)
                metrics = observation.get("read_metrics") or {}
                rows_loaded += int(metrics.get("rows_loaded", 0) or 0)
                observation_cpu_ns += int(metrics.get("cpu_ns", 0) or 0)
                if changed_pending is not None:
                    prior_tip = _pending_tip(current_pending)
                    current_pending = changed_pending
                    materialization_count += 1
                    idle_poll_count = 0
                    last_materialized_at = datetime.now(timezone.utc).isoformat()
                    if _pending_tip(current_pending) != prior_tip:
                        last_information_at = last_materialized_at
                else:
                    idle_poll_count += 1
                pending = current_pending
                consumption = _read_json(paths["consumption"])
                if _matching_consumption(consumption, wake_token):
                    covered_pending_tip = max(
                        covered_pending_tip,
                        int(consumption.get("pending_tip_cursor", 0) or 0),
                    )
                    covered_mail_revision = max(
                        covered_mail_revision,
                        int(consumption.get("mail_revision_cursor", 0) or 0),
                    )
                    last_consumed_token = wake_token.get("token")
                    last_consumed_at = consumption.get("consumed_at")
                    wake_token = None
                else:
                    retired = _canonical_retirement_receipt(
                        wake_token=wake_token,
                        pending=pending,
                        covered_pending_tip=covered_pending_tip,
                        current_mail_revision=current_mail_revision,
                        covered_mail_revision=covered_mail_revision,
                        observation=observation,
                        seat_id=seat_id,
                        thread_id=bound_thread,
                        lease_generation=bound_generation,
                    )
                    if retired is not None:
                        consumption = retired
                        _write_json(paths["consumption"], consumption)
                        try:
                            cleanup = _retire_provider_attention_for_token(
                                wake_token=wake_token,
                                thread_id=bound_thread,
                            )
                        except Exception as exc:  # the prompt hook still fences the token
                            cleanup = {
                                "status": "UNAVAILABLE",
                                "reason": f"{type(exc).__name__}: {exc}",
                            }
                        consumption["provider_queue_cleanup"] = cleanup
                        _write_json(paths["consumption"], consumption)
                        last_consumed_token = wake_token["token"]
                        last_consumed_at = consumption["consumed_at"]
                        covered_pending_tip = max(
                            covered_pending_tip,
                            int(consumption.get("pending_tip_cursor", 0) or 0),
                        )
                        covered_mail_revision = max(
                            covered_mail_revision,
                            int(consumption.get("mail_revision_cursor", 0) or 0),
                        )
                        canonical_retirement_count += 1
                        wake_token = None

                if thread_id and _should_issue_wake(
                    pending,
                    current_mail_revision=current_mail_revision,
                    covered_mail_revision=covered_mail_revision,
                    wake_token=wake_token,
                ):
                    if not bound_generation:
                        raise RuntimeError("bound watcher task has no wake lease generation")
                    wake_token = _new_wake_token(
                        seat_id=seat_id,
                        thread_id=thread_id,
                        lease_generation=bound_generation,
                        pending_tip=_pending_tip(pending),
                        mail_revision=current_mail_revision,
                    )

                if (
                    thread_id
                    and wake_token
                    and wake_token.get("transport_state") == "PREPARED_UNRECEIPTED"
                ):
                    codex_bin = shutil.which("codex")
                    if not codex_bin:
                        raise RuntimeError("codex CLI is not on PATH")
                    prompt = _attention_prompt(
                        thread_id=thread_id,
                        seat_id=seat_id,
                        wake_token=wake_token,
                    )
                    try:
                        _dispatch_wake_token(
                            wake_token,
                            prompt=prompt,
                            persist_prepared=lambda: publish_status(
                                information_state="pending-nudge",
                                checked_at=datetime.now(timezone.utc).isoformat(),
                            ),
                            persist_receipted=lambda: publish_status(
                                information_state="pending-nudge",
                                checked_at=datetime.now(timezone.utc).isoformat(),
                            ),
                            queue=lambda thread_id=thread_id,
                            wake_token=wake_token, codex_bin=codex_bin,
                            prompt=prompt: _queue_nudge(
                                thread_id=thread_id,
                                seat_id=seat_id,
                                wake_token=wake_token,
                                codex_bin=codex_bin,
                                prompt=prompt,
                            ),
                        )
                    except Exception:
                        transport_ambiguity_count += 1
                        raise
                    last_nudge_at = wake_token["queued_at"]
                    last_nudge_count = 1
                last_error = None
            except Exception as exc:  # noqa: BLE001 - watcher survives and exposes the fault
                last_error = f"{type(exc).__name__}: {exc}"
                _clear_atlas_store_cache()
            information_state = (
                "fault" if last_error else "pending-nudge" if wake_token else "caught-up"
            )
            publish_status(
                information_state=information_state,
                checked_at=datetime.now(timezone.utc).isoformat(),
            )
            stopped.wait(interval)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL)
    parser.add_argument("--seat", default=DEFAULT_SEAT_ID)
    args = parser.parse_args(argv)
    if not args.serve:
        parser.error("this module is started by the canonical wake; use --serve only for diagnostics")
    if args.interval < 0.5 or args.interval > _MAX_ACTIVE_INTERVAL_SECONDS:
        parser.error(
            f"--interval must be between 0.5 and {_MAX_ACTIVE_INTERVAL_SECONDS:g} seconds"
        )
    return _serve(args.interval, args.seat)


if __name__ == "__main__":  # pragma: no cover - exercised as a real detached process
    raise SystemExit(main())
