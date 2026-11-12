"""Bounded Codex provider-queue control for ephemeral Atlas attention.

The provider queue is not a ledger and never owns work.  Atlas owns every
message and disposition.  This module uses the supported app-server queue API
only to add, inspect, and retire replaceable attention prompts.  Every prompt it
owns is scoped by one logical seat, one physical task lease generation, and one
opaque wake token.

The deliberately small API closes two failure modes:

* a process crash after enqueue is recovered by a stable client message id and
  list-before-add, rather than by blindly adding another prompt; and
* a cold replacement retires only recognisable Eigen watcher submissions.  It
  never deletes arbitrary queued user input.
"""

from __future__ import annotations

import hashlib
import json
import os
import select
import shutil
import subprocess
import time
import uuid
from collections.abc import Mapping
from contextlib import AbstractContextManager
from typing import Any

QUEUE_RECEIPT_SCHEMA = "laplace.provider-attention-queue-receipt/1"
QUEUE_PRECOMMIT_SCHEMA = "laplace.provider-attention-queue-precommit/1"
QUEUE_RETIREMENT_SCHEMA = "laplace.provider-attention-retirement/1"
_CLIENT_NAMESPACE = uuid.UUID("3fc26e74-c048-5f4c-a60d-38d2ccc40a5a")
_WATCHER_PREFIX = "[Eigen Fabric watcher]"


class ProviderQueueError(RuntimeError):
    """The replaceable provider projection could not be proved or changed."""


def _codex_binary(explicit: str | None = None) -> str:
    candidate = explicit or os.environ.get("LAPLACE_CODEX_BIN") or shutil.which("codex")
    if not candidate:
        raise ProviderQueueError("codex CLI is not available for provider queue control")
    return str(candidate)


def attention_client_message_id(wake_token: Mapping[str, Any]) -> str:
    """Return one stable provider id for an exact seat/task/token generation."""

    required = ("seat_id", "thread_id", "lease_generation", "token")
    if any(not str(wake_token.get(name) or "") for name in required):
        raise ProviderQueueError("wake token lacks its complete provider attention scope")
    scoped = "|".join(str(wake_token[name]) for name in required)
    return str(uuid.uuid5(_CLIENT_NAMESPACE, scoped))


def _text_of(submission: Mapping[str, Any]) -> str:
    chunks = []
    for item in submission.get("input", []):
        if isinstance(item, Mapping) and item.get("type") == "text":
            chunks.append(str(item.get("text") or ""))
    return "\n".join(chunks)


def is_attention_shaped_submission(submission: Mapping[str, Any]) -> bool:
    """Recognise watcher-shaped text without treating its human body as ownership."""

    prompt = _text_of(submission)
    return bool(
        prompt.startswith(_WATCHER_PREFIX) and "laplace.provider-attention-contract/" in prompt
    )


def _submission_face(submission: Mapping[str, Any]) -> dict[str, Any]:
    """Return evidence without copying provider prompt bodies into another store."""

    prompt = _text_of(submission)
    return {
        "queued_submission_id": str(submission.get("id") or ""),
        "client_user_message_id": str(submission.get("clientUserMessageId") or ""),
        "prompt_digest": "sha256:" + hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "attention_shaped": is_attention_shaped_submission(submission),
    }


class CodexProviderQueue(AbstractContextManager["CodexProviderQueue"]):
    """One short-lived JSON-RPC connection to the local Codex app-server."""

    def __init__(self, *, codex_bin: str | None = None, timeout: float = 10.0):
        self.codex_bin = _codex_binary(codex_bin)
        self.timeout = float(timeout)
        if self.timeout <= 0 or self.timeout > 30:
            raise ValueError("provider queue timeout must be in (0, 30] seconds")
        self._next_id = 1
        self._process: subprocess.Popen[str] | None = None

    def __enter__(self) -> "CodexProviderQueue":
        try:
            self._process = subprocess.Popen(
                [self.codex_bin, "app-server", "--stdio"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )
            self._request(
                "initialize",
                {
                    "clientInfo": {
                        "name": "laplace-provider-queue",
                        "title": "Laplace provider attention gate",
                        "version": "1",
                    },
                    "capabilities": {
                        "experimentalApi": True,
                        "optOutNotificationMethods": [],
                    },
                },
            )
        except Exception:
            self.__exit__()
            raise
        return self

    def __exit__(self, *_exc: object) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        if process.stdin is not None:
            try:
                process.stdin.close()
            except OSError:
                pass
        try:
            process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1.0)

    def _request(self, method: str, params: Mapping[str, Any]) -> dict[str, Any]:
        process = self._process
        if process is None or process.stdin is None or process.stdout is None:
            raise ProviderQueueError("provider queue client is not initialized")
        request_id = self._next_id
        self._next_id += 1
        request = {"id": request_id, "method": method, "params": dict(params)}
        try:
            process.stdin.write(json.dumps(request, separators=(",", ":")) + "\n")
            process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise ProviderQueueError(f"app-server request write failed: {exc}") from exc

        deadline = time.monotonic() + self.timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProviderQueueError(f"app-server request timed out: {method}")
            ready, _, _ = select.select([process.stdout], [], [], remaining)
            if not ready:
                raise ProviderQueueError(f"app-server request timed out: {method}")
            line = process.stdout.readline()
            if not line:
                code = process.poll()
                raise ProviderQueueError(f"app-server closed while handling {method} (exit={code})")
            try:
                response = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(response, dict) or response.get("id") != request_id:
                # Notifications and replies to no-longer-live calls carry no authority here.
                continue
            if "error" in response:
                raise ProviderQueueError(
                    f"app-server {method} refused: " + json.dumps(response["error"], sort_keys=True)
                )
            result = response.get("result")
            if not isinstance(result, dict):
                raise ProviderQueueError(f"app-server {method} returned no object result")
            return result

    def list(self, thread_id: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            params: dict[str, Any] = {"threadId": thread_id, "limit": 100}
            if cursor:
                params["cursor"] = cursor
            result = self._request("thread/queue/list", params)
            page = result.get("data")
            if not isinstance(page, list):
                raise ProviderQueueError("thread/queue/list returned no data array")
            rows.extend(row for row in page if isinstance(row, dict))
            cursor = result.get("nextCursor")
            if not cursor:
                return rows

    def add(self, *, thread_id: str, client_message_id: str, prompt: str) -> dict[str, Any]:
        result = self._request(
            "thread/queue/add",
            {
                "threadId": thread_id,
                "clientUserMessageId": client_message_id,
                "input": [{"type": "text", "text": prompt}],
            },
        )
        submission = result.get("queuedSubmission")
        if not isinstance(submission, dict) or not submission.get("id"):
            raise ProviderQueueError("thread/queue/add returned no queued submission")
        return submission

    def delete(self, *, thread_id: str, submission_id: str) -> bool:
        result = self._request(
            "thread/queue/delete",
            {
                "threadId": thread_id,
                "queuedSubmissionId": submission_id,
            },
        )
        return result.get("deleted") is True


def queue_attention(
    *,
    thread_id: str,
    wake_token: Mapping[str, Any],
    prompt: str,
    codex_bin: str | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """Idempotently queue one scoped attention prompt and return its exact receipt."""

    client_id = attention_client_message_id(wake_token)
    with CodexProviderQueue(codex_bin=codex_bin, timeout=timeout) as queue:
        matches = [
            row for row in queue.list(thread_id) if row.get("clientUserMessageId") == client_id
        ]
        if matches:
            if any(
                _text_of(row) != prompt or not is_attention_shaped_submission(row)
                for row in matches
            ):
                raise ProviderQueueError(
                    "provider client message id collides with a different prompt body"
                )
            submission = matches[0]
            duplicate_ids = []
            for duplicate in matches[1:]:
                duplicate_id = str(duplicate.get("id") or "")
                if not duplicate_id or not queue.delete(
                    thread_id=thread_id, submission_id=duplicate_id
                ):
                    raise ProviderQueueError(
                        "duplicate provider attention submission could not be retired"
                    )
                duplicate_ids.append(duplicate_id)
            created = False
        else:
            submission = queue.add(
                thread_id=thread_id,
                client_message_id=client_id,
                prompt=prompt,
            )
            if (
                submission.get("clientUserMessageId") != client_id
                or _text_of(submission) != prompt
                or not is_attention_shaped_submission(submission)
            ):
                raise ProviderQueueError(
                    "provider enqueue receipt does not bind the exact attention body"
                )
            duplicate_ids = []
            created = True
        surviving = [
            row for row in queue.list(thread_id)
            if row.get("clientUserMessageId") == client_id
        ]
        if (
            len(surviving) != 1
            or surviving[0].get("id") != submission.get("id")
            or _text_of(surviving[0]) != prompt
        ):
            raise ProviderQueueError(
                "provider queue does not contain exactly one body-bound attention submission"
            )
    return {
        "schema_version": QUEUE_RECEIPT_SCHEMA,
        "thread_id": thread_id,
        **_submission_face(submission),
        "owned_attention": True,
        "created": created,
        "retired_duplicate_submission_ids": duplicate_ids,
        "transport": "codex-app-server-thread-queue",
    }


def retire_attention(
    *,
    thread_id: str,
    client_message_id: str,
    prompt_digest: str,
    codex_bin: str | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """Delete one exact receipted watcher body; arbitrary user input remains untouched."""

    if not client_message_id:
        raise ValueError("provider attention retirement requires an exact client message id")
    if not prompt_digest.startswith("sha256:") or len(prompt_digest) != 71:
        raise ValueError("provider attention retirement requires an exact prompt digest")

    with CodexProviderQueue(codex_bin=codex_bin, timeout=timeout) as queue:
        rows = queue.list(thread_id)
        same_client = [
            row for row in rows if row.get("clientUserMessageId") == client_message_id
        ]
        conflicting = [
            row for row in same_client
            if _submission_face(row)["prompt_digest"] != prompt_digest
            or not is_attention_shaped_submission(row)
        ]
        if conflicting:
            raise ProviderQueueError(
                "provider client message id is bound to a different or unowned prompt body"
            )
        owned = [
            row
            for row in same_client
            if is_attention_shaped_submission(row)
            and _submission_face(row)["prompt_digest"] == prompt_digest
        ]
        retired = []
        for row in owned:
            submission_id = str(row.get("id") or "")
            if not submission_id or not queue.delete(
                thread_id=thread_id, submission_id=submission_id
            ):
                raise ProviderQueueError(
                    "owned provider attention submission could not be retired"
                )
            retired.append(_submission_face(row))
        remaining = queue.list(thread_id)
        survivors = [
            row for row in remaining
            if row.get("clientUserMessageId") == client_message_id
            and is_attention_shaped_submission(row)
            and _submission_face(row)["prompt_digest"] == prompt_digest
        ]
        if survivors:
            raise ProviderQueueError(
                "owned provider attention survived its retirement receipt"
            )
    return {
        "schema_version": QUEUE_RETIREMENT_SCHEMA,
        "thread_id": thread_id,
        "client_user_message_id": client_message_id,
        "prompt_digest": prompt_digest,
        "observed_submission_count": len(rows),
        "exact_submission_count": len(owned),
        "retired_submission_count": len(retired),
        "retired_submissions": retired,
        "remaining_submission_count": len(remaining),
        "nonmatching_submission_count": len(remaining),
        "arbitrary_user_input_policy": "PRESERVED",
    }


def audit_thread(
    *, thread_id: str, codex_bin: str | None = None, timeout: float = 10.0
) -> dict[str, Any]:
    """Read a bounded provider queue face without exposing prompt bodies."""

    with CodexProviderQueue(codex_bin=codex_bin, timeout=timeout) as queue:
        rows = queue.list(thread_id)
    return {
        "schema_version": "laplace.provider-attention-queue-audit/1",
        "thread_id": thread_id,
        "submission_count": len(rows),
        "submissions": [_submission_face(row) for row in rows],
    }
