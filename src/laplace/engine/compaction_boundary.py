"""Actual Codex PreCompact/PostCompact boundary for semantic continuation.

The platform events are the producer boundary.  SessionStart is only redundant recovery.  A
PreCompact event binds the exact transcript and canonical seat lineage, then either seals a
profile against a CURRENT zero-deferred S-to-F fold or explicitly holds compaction while one
deduplicated fold is queued.  PostCompact consumes only that exact seal.
"""
from __future__ import annotations

import io
import json
import os
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Mapping

from laplace.representation import atlas_bridge
from laplace.engine.compaction_submergence import reconstruct_cold_successor, seal_precompact
from laplace.representation.embedding_health import read_health
from laplace.representation.semantic_vertical import canonical_bytes, digest, digest_bytes

BOUNDARY_SCHEMA = "laplace.codex-compaction-boundary/1"
STATE_SCHEMA = "laplace.codex-compaction-seals/1"
GOAL_CONTEXT_PATH = Path(
    "/home/phujck/SystemCheckpoints/2026-08-28/THREE-SEAT-GOALS-AND-CONTEXT.json"
)
GOAL_CONTEXT_HANDLE = (
    "sha256:2991526a880b125269e3f95c35e7013797d23a51ee3e8841c8e8f45653111818"
)
GOAL_CONTEXT_BYTES = 12_821
_FUNCTION_FOR_SEAT = {
    "ego-seat": "ego",
    "sensorium-seat": "sensorium",
    "superego-seat": "superego",
}
_REQUIRED_FIELDS = (
    "cwd", "hook_event_name", "model", "session_id", "transcript_path", "trigger", "turn_id",
)
_SEMANTIC_CHUNK_CHARS = 8_000
_SEMANTIC_CHUNK_LIMIT = 256
_SEMANTIC_TEXT_LIMIT = _SEMANTIC_CHUNK_CHARS * _SEMANTIC_CHUNK_LIMIT
_SEMANTIC_RECORD_LIMIT = 512
_SEMANTIC_RECORD_TEXT_LIMIT = 96_000


def _state_path() -> Path:
    explicit = os.environ.get("LAPLACE_COMPACTION_STATE_ROOT", "").strip()
    root = Path(explicit) if explicit else Path.home() / ".mcp-gerard" / "laplace" / "semantic"
    return root / "compaction-seals.json"


def _read_state() -> dict[str, Any]:
    path = _state_path()
    if not path.is_file():
        return {"schema_version": STATE_SCHEMA, "sessions": {}}
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != STATE_SCHEMA or not isinstance(value.get("sessions"), dict):
        raise RuntimeError("compaction seal cache is malformed")
    return value


def _write_state(value: Mapping[str, Any]) -> None:
    path = _state_path()
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


def _event(raw: Mapping[str, Any], expected: str) -> dict[str, str]:
    missing = [field for field in _REQUIRED_FIELDS if not isinstance(raw.get(field), str) or not raw[field]]
    if missing:
        raise RuntimeError(f"{expected} input omits exact fields: {missing}")
    event = {field: str(raw[field]) for field in _REQUIRED_FIELDS}
    if event["hook_event_name"] != expected:
        raise RuntimeError(f"compaction hook expected {expected}, got {event['hook_event_name']!r}")
    if event["trigger"] not in {"manual", "auto"}:
        raise RuntimeError("compaction trigger must be manual or auto")
    return event


def _transcript(event: Mapping[str, str]) -> tuple[dict[str, Any], bytes]:
    path = Path(event["transcript_path"])
    if not path.is_file() or path.is_symlink():
        raise RuntimeError("compaction transcript must be one exact regular file")
    body = path.read_bytes()
    return {
        "path": str(path),
        "resolved_path": str(path.resolve()),
        "bytes": len(body),
        "content_handle": digest_bytes(body),
    }, body


def _identity(session_id: str) -> dict[str, str]:
    binding = atlas_bridge.provider_seat_binding(provider_session_ref=f"codex:{session_id}")
    if binding.get("status") != "BOUND" or binding.get("matching_seats") not in (
        None, [binding.get("seat_id")], (binding.get("seat_id"),),
    ):
        raise RuntimeError("compaction boundary requires one unique canonical provider binding")
    seat_id = str(binding.get("seat_id") or "")
    function = _FUNCTION_FOR_SEAT.get(seat_id)
    occupancy = binding.get("occupancy")
    generation = occupancy.get("current_provider_identity_generation") if isinstance(
        occupancy, Mapping
    ) else None
    if not function or not isinstance(generation, str) or not generation:
        raise RuntimeError("compaction binding omits canonical function or generation")
    return {"seat_id": seat_id, "function": function, "generation": generation}


def _lease_ids(seat_id: str) -> tuple[str, ...]:
    projection = atlas_bridge.region_leases()
    rows = projection.get("leases") or {}
    selected = []
    for lease_id in projection.get("active") or ():
        row = rows.get(lease_id) or {}
        authority = row.get("checkout_authority") or {}
        if row.get("seat_id") == seat_id or authority.get("seat_id") == seat_id:
            selected.append(str(lease_id))
    return tuple(sorted(selected))


def active_profile(session_id: str) -> dict[str, Any] | None:
    row = (_read_state().get("sessions") or {}).get(session_id)
    return dict(row) if isinstance(row, Mapping) else None


def _content_text(message: Mapping[str, Any]) -> str:
    content = message.get("content")
    if not isinstance(content, list):
        return ""
    return "\n".join(
        str(item.get("text") or "")
        for item in content
        if isinstance(item, Mapping) and isinstance(item.get("text"), str)
    )


def _message_class(text: str) -> str:
    stripped = text.lstrip()
    if stripped.startswith("<codex_delegation>"):
        return "consumed-task-coordination"
    if stripped.startswith("[Eigen Fabric watcher]"):
        return "consumed-fabric-watcher"
    if stripped.startswith("<codex_internal_context"):
        return "platform-goal-context"
    if stripped.startswith("<recommended_plugins>"):
        return "platform-plugin-context"
    return "author-content"


def _author_text(text: str) -> str:
    """Remove ambient browser state while preserving the author's request text."""

    if "<in-app-browser-context" in text and "## My request:" in text:
        return text.split("## My request:", 1)[1].strip()
    return text


def _jsonl_rows(
    body: bytes, *, start: int = 0
) -> Iterator[tuple[int, int, dict[str, Any], bytes]]:
    """Decode exact JSONL rows without materialising ``splitlines()`` for huge logs."""

    if start < 0 or start > len(body):
        raise RuntimeError("transcript semantic horizon has an invalid byte boundary")
    if start and body[start - 1 : start] != b"\n":
        raise RuntimeError("transcript semantic horizon does not start at a JSONL boundary")
    stream = io.BytesIO(body)
    stream.seek(start)
    while True:
        offset = stream.tell()
        raw = stream.readline()
        if not raw:
            break
        try:
            value = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"compaction transcript row at byte {offset} is not exact JSONL"
            ) from exc
        if not isinstance(value, dict):
            raise RuntimeError(f"compaction transcript row at byte {offset} is not an object")
        yield offset, stream.tell(), value, raw


def _semantic_horizon(
    *, event: Mapping[str, str], body: bytes, raw_start: int, first_boundary: bool
) -> dict[str, Any]:
    """Project bounded causal meaning from exact rollout custody.

    Rollout JSONL is evidence, not an embedding payload. Tool results, encrypted reasoning,
    telemetry, and already-consumed coordination can dominate megabytes while carrying no new
    author meaning. This projector keeps their exact identities and aggregate roots, but embeds
    only direct author text and visible assistant decisions. On the first boundary the newest
    Codex replacement history supplies the source-bearing author horizon; subsequent boundaries
    consume only bytes after the exact predecessor.
    """

    all_rows = _jsonl_rows(body)
    latest_compacted: tuple[int, int, dict[str, Any], bytes] | None = None
    turn_start: int | None = None
    for row in all_rows:
        offset, _end, value, _raw = row
        payload = value.get("payload")
        if value.get("type") == "compacted":
            latest_compacted = row
        if (
            turn_start is None
            and value.get("type") == "turn_context"
            and isinstance(payload, Mapping)
            and payload.get("turn_id") == event["turn_id"]
        ):
            turn_start = offset

    selected: list[dict[str, Any]] = []
    selected_text_bytes = 0
    inert_aggregate: dict[str, list[Any]] = {}

    def inert(kind: str, identity: str, raw: bytes, *, location: Mapping[str, Any]) -> None:
        row = {
            "kind": kind,
            "identity": identity,
            "content_handle": digest_bytes(raw),
            "bytes": len(raw),
            **dict(location),
        }
        inert_aggregate.setdefault(kind, []).append(
            (identity, row["content_handle"], len(raw))
        )

    def select(
        *, kind: str, identity: str, text: str, location: Mapping[str, Any]
    ) -> None:
        nonlocal selected_text_bytes
        original = text.encode("utf-8")
        normalized = _author_text(text) if kind == "author-turn" else text
        encoded = normalized.encode("utf-8")
        if not normalized.strip():
            return
        projected = selected_text_bytes + len(encoded) + len(kind) + len(identity) + 8
        if (
            len(selected) >= _SEMANTIC_RECORD_LIMIT
            or len(encoded) > _SEMANTIC_RECORD_TEXT_LIMIT
            or projected > _SEMANTIC_TEXT_LIMIT
        ):
            inert(
                "semantic-budget-omission", identity, original,
                location={**dict(location), "continuation": "exact-transcript-custody"},
            )
            return
        selected.append({
            "kind": kind,
            "identity": identity,
            "text": normalized,
            "source_text_handle": digest_bytes(original),
            "selected_text_handle": digest_bytes(encoded),
            "bytes": len(encoded),
            **dict(location),
        })
        selected_text_bytes = projected

    post_start = raw_start
    first_source = "predecessor-byte-boundary"
    if first_boundary:
        if latest_compacted is not None:
            offset, end, compacted, raw = latest_compacted
            post_start = end
            first_source = "latest-compacted-replacement-history"
            history = (compacted.get("payload") or {}).get("replacement_history") or ()
            for index, item in enumerate(history):
                if not isinstance(item, Mapping) or item.get("type") != "message":
                    if isinstance(item, Mapping):
                        inert(
                            "opaque-compaction-history", str(item.get("id") or index),
                            canonical_bytes(item),
                            location={"replacement_index": index, "byte_offset": offset},
                        )
                    continue
                text = _content_text(item)
                identity = str(item.get("id") or f"replacement:{index}")
                role = str(item.get("role") or "")
                message_class = _message_class(text)
                location = {"replacement_index": index, "byte_offset": offset}
                if role == "user" and message_class == "author-content":
                    select(kind="author-turn", identity=identity, text=text, location=location)
                elif role == "assistant":
                    select(
                        kind="assistant-decision", identity=identity, text=text,
                        location=location,
                    )
                else:
                    inert(
                        message_class if role == "user" else f"platform-{role or 'unknown'}-context",
                        identity, canonical_bytes(item), location=location,
                    )
            inert(
                "compaction-envelope",
                str((compacted.get("payload") or {}).get("window_id") or offset), raw,
                location={"byte_offset": offset},
            )
        else:
            post_start = turn_start if turn_start is not None else raw_start
            first_source = (
                "active-turn-byte-boundary" if turn_start is not None else "transcript-origin"
            )

    for offset, _end, value, raw in _jsonl_rows(body, start=post_start):
        row_type = str(value.get("type") or "unknown")
        payload = value.get("payload")
        identity = str(
            (payload or {}).get("id") if isinstance(payload, Mapping) else ""
        ) or f"ordinal:{value.get('ordinal', offset)}"
        location = {"byte_offset": offset, "ordinal": value.get("ordinal")}
        if (
            row_type == "response_item"
            and isinstance(payload, Mapping)
            and payload.get("type") == "message"
        ):
            text = _content_text(payload)
            role = str(payload.get("role") or "")
            message_class = _message_class(text)
            if role == "user" and message_class == "author-content":
                select(kind="author-turn", identity=identity, text=text, location=location)
            elif role == "assistant":
                select(kind="assistant-decision", identity=identity, text=text, location=location)
            else:
                inert(
                    message_class if role == "user" else f"platform-{role or 'unknown'}-context",
                    identity, raw, location=location,
                )
        elif row_type != "turn_context":
            inert(f"rollout-{row_type}", identity, raw, location=location)

    semantic_text = "\n\n".join(
        f"[{row['kind']} {row['identity']}]\n{row['text']}" for row in selected
    )
    if not semantic_text:
        semantic_text = (
            "No new direct author text or visible assistant decision. Exact rollout traffic is "
            "preserved as inert custody evidence."
        )
    semantic_raw = semantic_text.encode("utf-8")
    if len(semantic_raw) > _SEMANTIC_TEXT_LIMIT:
        raise RuntimeError("typed compaction semantic horizon exceeded its declared bound")
    aggregates = {
        kind: {
            "count": len(values),
            "bytes": sum(int(value[2]) for value in values),
            "root": digest(values),
        }
        for kind, values in sorted(inert_aggregate.items())
    }
    author = [row for row in selected if row["kind"] == "author-turn"]
    decisions = [row for row in selected if row["kind"] == "assistant-decision"]
    horizon = {
        "schema_version": "laplace.compaction-semantic-horizon/1",
        "status": "COMPLETE",
        "session_id": event["session_id"],
        "turn_id": event["turn_id"],
        "source_boundary": {
            "kind": first_source,
            "raw_start": raw_start,
            "semantic_start": post_start,
            "raw_end": len(body),
        },
        "selected": selected,
        "selected_count": len(selected),
        "author_turn_count": len(author),
        "assistant_decision_count": len(decisions),
        "inert_aggregates": aggregates,
        "semantic_text": semantic_text,
        "semantic_text_handle": digest_bytes(semantic_raw),
        "semantic_bytes": len(semantic_raw),
        "authority_effect": "custody only; no message replay or lifecycle authority",
    }
    horizon["horizon_handle"] = digest(horizon)
    return horizon


def _transcript_delta(
    root: Path,
    *,
    event: Mapping[str, str],
    transcript: Mapping[str, Any],
    body: bytes,
    predecessor: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Bank exact rollout custody and UP only its bounded typed causal horizon."""

    from laplace.representation.atlas_bridge import ChildLeaf, UpInputs, up
    from laplace.representation.atlas_bridge import UpActReceipt, bind_up_result

    from laplace.representation.embed_router import get_backend

    full_handle = atlas_bridge.put_custody(body)
    if full_handle != transcript["content_handle"] or not atlas_bridge.custody_has(full_handle):
        raise RuntimeError("Atlas custody contradicted the exact PreCompact transcript")
    prior_bytes = 0
    prior_full = None
    prior_delta = None
    if isinstance(predecessor, Mapping):
        prior_bytes = int(predecessor.get("transcript_bytes") or 0)
        prior_full = predecessor.get("transcript_handle")
        prior_delta = predecessor.get("transcript_delta")
    if prior_full:
        prior_body = atlas_bridge.custody_body(handle=str(prior_full)).get("text")
        if not isinstance(prior_body, str):
            raise RuntimeError("predecessor transcript custody is not exact UTF-8")
        prior_raw = prior_body.encode("utf-8")
        if len(prior_raw) != prior_bytes or not body.startswith(prior_raw):
            raise RuntimeError("PreCompact transcript moved before its predecessor boundary")
    if prior_full == full_handle and isinstance(prior_delta, Mapping):
        return {**dict(prior_delta), "deduplicated": True}

    raw_suffix = body[prior_bytes:]
    if not raw_suffix:
        raise RuntimeError("new PreCompact boundary has no exact suffix or reusable delta")
    raw_suffix_handle = atlas_bridge.put_custody(raw_suffix)
    if raw_suffix_handle != digest_bytes(raw_suffix):
        raise RuntimeError("Atlas custody contradicted the transcript suffix handle")
    horizon = _semantic_horizon(
        event=event,
        body=body,
        raw_start=prior_bytes,
        first_boundary=not bool(prior_full),
    )
    horizon_bytes = canonical_bytes(horizon)
    horizon_handle = atlas_bridge.put_custody(horizon_bytes)
    if horizon_handle != digest_bytes(horizon_bytes):
        raise RuntimeError("Atlas custody contradicted the semantic horizon")
    semantic_text = str(horizon["semantic_text"])
    backend = get_backend()
    if backend is None:
        raise RuntimeError("bounded PreCompact semantic embedder is unavailable")
    chunks = [
        semantic_text[offset : offset + _SEMANTIC_CHUNK_CHARS]
        for offset in range(0, len(semantic_text), _SEMANTIC_CHUNK_CHARS)
    ]
    if not chunks or len(chunks) > _SEMANTIC_CHUNK_LIMIT:
        raise RuntimeError("PreCompact transcript delta exceeds the bounded 256-chunk fold")
    vectors = backend.embed(chunks)
    if len(vectors) != len(chunks) or any(not vector for vector in vectors):
        raise RuntimeError("bounded PreCompact semantic embedding was deferred")
    children = []
    member_objects: dict[str, str] = {}
    for position, (text, vector) in enumerate(zip(chunks, vectors, strict=True)):
        chunk_bytes = text.encode("utf-8")
        chunk_handle = atlas_bridge.put_custody(chunk_bytes)
        if chunk_handle != digest_bytes(chunk_bytes):
            raise RuntimeError("Atlas custody contradicted a transcript-delta chunk")
        children.append(ChildLeaf(
            chunk_handle, text, tuple(float(value) for value in vector)
        ))
        member_objects[chunk_handle] = f"atlas-custody:{chunk_handle}#chunk-{position}"
    inputs = UpInputs(
        assumption="laplace.precompact-transcript-delta",
        fibre="author-session",
        axis="semantic-grade",
        from_grade="turn-suffix",
        to_grade="session-delta",
        metric_version=str(getattr(backend, "name", "UNKNOWN")),
        grade_contract_id="laplace.precompact-transcript-grade-axis/1",
        chi=min(8, len(children)),
        phi=1.0,
        coarse_to_fine=("session-delta", "turn-suffix"),
        children=tuple(children),
    )
    promotion = UpActReceipt.from_dict(
        bind_up_result(
            inputs,
            up(inputs),
            member_objects,
        ).to_dict()
    )
    health = read_health(root)
    fold = health.get("side_ref_fold") or {}
    body_row = {
        "schema_version": "laplace.precompact-semantic-delta/1",
        "status": "COMPLETE",
        "global_F": {
            "status": (health.get("side_ref_fold") or {}).get("status", "UNKNOWN"),
            "output_commit": fold.get("output_commit"),
            "manifest_handle": fold.get("manifest_handle"),
            "semantic_fold_receipt_handle": (health.get("up_down") or {}).get(
                "receipt_handle"
            ),
        },
        "session_id": event["session_id"],
        "turn_id": event["turn_id"],
        "transcript": {
            "full_custody_handle": full_handle,
            "predecessor_custody_handle": prior_full,
            "raw_suffix_custody_handle": raw_suffix_handle,
            "suffix_custody_handle": horizon_handle,
            "semantic_horizon_custody_handle": horizon_handle,
            "suffix_offset": prior_bytes,
            "suffix_bytes": len(raw_suffix),
            "raw_suffix_bytes": len(raw_suffix),
            "semantic_bytes": len(horizon_bytes),
            "chunk_handles": [child.handle for child in children],
            "full_bytes": len(body),
        },
        "semantic_horizon": {
            "horizon_handle": horizon["horizon_handle"],
            "custody_handle": horizon_handle,
            "semantic_text_handle": horizon["semantic_text_handle"],
            "selected_count": horizon["selected_count"],
            "author_turn_count": horizon["author_turn_count"],
            "assistant_decision_count": horizon["assistant_decision_count"],
            "inert_message_count": sum(
                int((horizon["inert_aggregates"].get(kind) or {}).get("count") or 0)
                for kind in ("consumed-task-coordination", "consumed-fabric-watcher")
            ),
            "inert_aggregates": horizon["inert_aggregates"],
            "source_boundary": horizon["source_boundary"],
        },
        "author_turn_handle": digest({
            "session_id": event["session_id"],
            "turn_id": event["turn_id"],
            "semantic_horizon_custody_handle": horizon_handle,
            "author_turn_count": horizon["author_turn_count"],
        }),
        "typed_descent": {
            "kind": "atlas-custody",
            "reference": horizon_handle,
            "source": "",
        },
        "up_receipt": promotion.to_dict(),
        "up_receipt_handle": digest(promotion.to_dict()),
        "embedding": {
            "backend": getattr(backend, "name", None),
            "gpu": getattr(backend, "gpu", None),
            "providers": list(getattr(backend, "providers", ()) or ()),
        },
        "n_deferred": 0,
        "absorption": "next global semantic cadence S-to-F fold",
        "authority_effect": "custody only; no lifecycle or publication authority",
    }
    body_row["delta_handle"] = digest(body_row)
    delta_bytes = canonical_bytes(body_row)
    delta_custody = atlas_bridge.put_custody(delta_bytes)
    if delta_custody != digest_bytes(delta_bytes):
        raise RuntimeError("Atlas custody contradicted the transcript semantic delta")
    return {
        "delta_handle": body_row["delta_handle"],
        "delta_custody_handle": delta_custody,
        "global_fold_receipt_handle": body_row["global_F"]["semantic_fold_receipt_handle"],
        "transcript_handle": full_handle,
        "transcript_bytes": len(body),
        "suffix_handle": raw_suffix_handle,
        "suffix_offset": prior_bytes,
        "suffix_bytes": len(raw_suffix),
        "semantic_horizon_handle": horizon_handle,
        "semantic_bytes": len(horizon_bytes),
        "semantic_selected_count": horizon["selected_count"],
        "semantic_author_turn_count": horizon["author_turn_count"],
        "semantic_assistant_decision_count": horizon["assistant_decision_count"],
        "n_deferred": 0,
        "up_receipt_handle": body_row["up_receipt_handle"],
        "typed_descent": body_row["typed_descent"],
        "deduplicated": False,
    }


def precompact(repo_root: Path | str, raw: Mapping[str, Any]) -> dict[str, Any]:
    started = time.perf_counter_ns()
    root = Path(repo_root).resolve()
    event = _event(raw, "PreCompact")
    transcript, before = _transcript(event)
    identity = _identity(event["session_id"])
    predecessor = active_profile(event["session_id"])
    transcript_delta = _transcript_delta(
        root,
        event=event,
        transcript=transcript,
        body=before,
        predecessor=predecessor,
    )
    boundary = {
        "schema_version": BOUNDARY_SCHEMA,
        "event": "PreCompact",
        "session_id": event["session_id"],
        "turn_id": event["turn_id"],
        "model": event["model"],
        "trigger": event["trigger"],
        "cwd": event["cwd"],
        "transcript": transcript,
        "transcript_custody_handle": transcript_delta["transcript_handle"],
        "predecessor_boundary_handle": None
        if predecessor is None else predecessor.get("boundary_handle"),
        "semantic_delta": transcript_delta,
        "identity": identity,
    }
    boundary["boundary_handle"] = digest(boundary)
    inertia = {
        "coordination_layer_count": 1,
        "author_command_to_productive_act_ms": 0,
        "reconstructions": 1,
        "subprocesses": 1,
        "tokens": max(1, int(transcript_delta.get("semantic_bytes") or 0) // 4),
        "review_cycles": 0,
        "uniquely_caught_faults": 0,
    }
    seal = seal_precompact(
        repo_root=root,
        function=identity["function"],
        seat_id=identity["seat_id"],
        generation=identity["generation"],
        lease_ids=_lease_ids(identity["seat_id"]),
        inertia=inertia,
        goal_context_path=GOAL_CONTEXT_PATH,
        goal_context_handle=GOAL_CONTEXT_HANDLE,
        goal_context_bytes=GOAL_CONTEXT_BYTES,
        compaction_boundary=boundary,
    )
    after = Path(event["transcript_path"]).read_bytes()
    if after != before:
        raise RuntimeError("compaction transcript bytes moved during PreCompact seal")
    result = {
        "schema_version": BOUNDARY_SCHEMA,
        "event": "PreCompact",
        "status": seal["status"],
        "boundary": boundary,
        "seal": seal,
        "elapsed_ms": round((time.perf_counter_ns() - started) / 1_000_000, 3),
    }
    result["receipt_handle"] = digest(result)
    if seal.get("status") == "SEALED":
        state = _read_state()
        sessions = dict(state["sessions"])
        sessions[event["session_id"]] = {
            "session_id": event["session_id"],
            "turn_id": event["turn_id"],
            "boundary_handle": boundary["boundary_handle"],
            "transcript_handle": transcript["content_handle"],
            "transcript_bytes": transcript["bytes"],
            "transcript_delta": transcript_delta,
            "profile_handle": seal["profile_handle"],
            "semantic_fold_health_handle": seal["semantic_fold_health_handle"],
            "semantic_fold_receipt_handle": seal["semantic_fold_receipt_handle"],
            **identity,
        }
        _write_state({"schema_version": STATE_SCHEMA, "sessions": sessions})
    return result


def postcompact(repo_root: Path | str, raw: Mapping[str, Any]) -> dict[str, Any]:
    started = time.perf_counter_ns()
    root = Path(repo_root).resolve()
    event = _event(raw, "PostCompact")
    row = active_profile(event["session_id"])
    if row is None:
        raise RuntimeError("PostCompact has no exact sealed PreCompact predecessor")
    if row.get("turn_id") != event["turn_id"]:
        raise RuntimeError("PostCompact turn identity moved from its exact seal")
    current = _identity(event["session_id"])
    for field in ("seat_id", "function", "generation"):
        if current[field] != row.get(field):
            raise RuntimeError(f"PostCompact canonical {field} moved from its exact seal")
    cold = reconstruct_cold_successor(
        repo_root=root,
        profile_handle=str(row["profile_handle"]),
        function=current["function"],
        seat_id=current["seat_id"],
        generation=current["generation"],
    )
    result = {
        "schema_version": BOUNDARY_SCHEMA,
        "event": "PostCompact",
        "status": "ADMITTED" if cold.get("status") == "AUTHORIZED" else cold.get("status"),
        "sealed": row,
        "cold_successor": cold,
        "tools_enabled": cold.get("status") == "AUTHORIZED",
        "human_conversation_allowed": True,
        "elapsed_ms": round((time.perf_counter_ns() - started) / 1_000_000, 3),
    }
    result["receipt_handle"] = digest(result)
    return result


__all__ = [
    "BOUNDARY_SCHEMA", "STATE_SCHEMA", "active_profile", "postcompact", "precompact",
]
