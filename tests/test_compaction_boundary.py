from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from laplace.engine import compaction_boundary as boundary
from laplace.representation.semantic_vertical import digest_bytes


def _event(path: Path, name: str = "PreCompact") -> dict[str, str]:
    return {
        "cwd": str(path.parent),
        "hook_event_name": name,
        "model": "gpt-5",
        "session_id": "thread-ego",
        "transcript_path": str(path),
        "trigger": "auto",
        "turn_id": "turn-9",
    }


def _delta(body: bytes) -> dict:
    return {
        "delta_handle": "sha256:" + "1" * 64,
        "delta_custody_handle": "sha256:" + "2" * 64,
        "global_fold_receipt_handle": "sha256:" + "3" * 64,
        "transcript_handle": digest_bytes(body),
        "transcript_bytes": len(body),
        "suffix_handle": digest_bytes(body),
        "suffix_offset": 0,
        "suffix_bytes": len(body),
        "n_deferred": 0,
        "up_receipt_handle": "sha256:" + "4" * 64,
        "typed_descent": {
            "kind": "atlas-custody", "reference": digest_bytes(body), "source": "",
        },
        "deduplicated": False,
    }


def test_real_codex_compaction_hooks_are_registered() -> None:
    config = json.loads(Path(".codex/hooks.json").read_text(encoding="utf-8"))
    hooks = config["hooks"]
    assert {"PreCompact", "PostCompact"}.issubset(hooks)
    for name in ("PreCompact", "PostCompact"):
        command = hooks[name][0]["hooks"][0]
        assert command["command"].endswith("scripts/compaction_boundary.py\"")
        assert command["timeout"] == 120


def test_precompact_binds_exact_event_transcript_and_sealed_profile(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    transcript = tmp_path / "rollout.jsonl"
    body = b'{"role":"user","text":"new distinction"}\n'
    transcript.write_bytes(body)
    monkeypatch.setenv("LAPLACE_COMPACTION_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setattr(
        boundary, "_identity",
        lambda _session: {"seat_id": "ego-seat", "function": "ego", "generation": "g:1"},
    )
    monkeypatch.setattr(boundary, "_lease_ids", lambda _seat: ())
    monkeypatch.setattr(
        boundary, "_transcript_delta",
        lambda _root, **_kwargs: _delta(body),
    )
    monkeypatch.setattr(
        boundary,
        "seal_precompact",
        lambda **kwargs: {
            "status": "SEALED",
            "profile_handle": "sha256:" + "5" * 64,
            "semantic_fold_health_handle": "sha256:" + "6" * 64,
            "semantic_fold_receipt_handle": "sha256:" + "3" * 64,
            "compaction_boundary": kwargs["compaction_boundary"],
        },
    )

    result = boundary.precompact(tmp_path, _event(transcript))

    assert result["status"] == "SEALED"
    assert result["boundary"]["transcript"]["content_handle"] == digest_bytes(body)
    assert result["boundary"]["transcript_custody_handle"] == digest_bytes(body)
    assert result["boundary"]["semantic_delta"]["n_deferred"] == 0
    sealed = boundary.active_profile("thread-ego")
    assert sealed is not None
    assert sealed["profile_handle"] == "sha256:" + "5" * 64


def test_precompact_refuses_transcript_byte_movement_during_seal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    transcript = tmp_path / "rollout.jsonl"
    body = b"before"
    transcript.write_bytes(body)
    monkeypatch.setenv("LAPLACE_COMPACTION_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setattr(
        boundary, "_identity",
        lambda _session: {"seat_id": "ego-seat", "function": "ego", "generation": "g:1"},
    )
    monkeypatch.setattr(boundary, "_lease_ids", lambda _seat: ())
    monkeypatch.setattr(
        boundary, "_transcript_delta", lambda _root, **_kwargs: _delta(body)
    )

    def moved(**_kwargs):
        transcript.write_bytes(b"after")
        return {"status": "SEALED", "profile_handle": "sha256:" + "5" * 64}

    monkeypatch.setattr(boundary, "seal_precompact", moved)
    with pytest.raises(RuntimeError, match="transcript bytes moved"):
        boundary.precompact(tmp_path, _event(transcript))


def test_repeated_unchanged_precompact_boundary_deduplicates_before_embedding(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    body = b"already banked author distinction"
    full_handle = digest_bytes(body)
    prior = {**_delta(body), "delta_handle": "sha256:" + "7" * 64}
    monkeypatch.setattr(boundary.atlas_bridge, "put_custody", digest_bytes)
    monkeypatch.setattr(boundary.atlas_bridge, "custody_has", lambda _handle: True)
    monkeypatch.setattr(
        boundary.atlas_bridge,
        "custody_body",
        lambda **_kwargs: {"text": body.decode("utf-8")},
    )
    monkeypatch.setattr(
        "laplace.representation.embed_router.get_backend",
        lambda: (_ for _ in ()).throw(AssertionError("unchanged boundary re-embedded")),
    )
    result = boundary._transcript_delta(
        tmp_path,
        event=_event(tmp_path / "rollout.jsonl"),
        transcript={"content_handle": full_handle},
        body=body,
        predecessor={
            "transcript_bytes": len(body),
            "transcript_handle": full_handle,
            "transcript_delta": prior,
        },
    )
    assert result["deduplicated"] is True
    assert result["delta_handle"] == prior["delta_handle"]


def test_moved_transcript_cannot_reuse_predecessor_boundary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    before = b"first author text"
    moved = b"different author text"
    monkeypatch.setattr(boundary.atlas_bridge, "put_custody", digest_bytes)
    monkeypatch.setattr(boundary.atlas_bridge, "custody_has", lambda _handle: True)
    monkeypatch.setattr(
        boundary.atlas_bridge,
        "custody_body",
        lambda **_kwargs: {"text": before.decode("utf-8")},
    )
    with pytest.raises(RuntimeError, match="moved before its predecessor boundary"):
        boundary._transcript_delta(
            tmp_path,
            event=_event(tmp_path / "rollout.jsonl"),
            transcript={"content_handle": digest_bytes(moved)},
            body=moved,
            predecessor={
                "transcript_bytes": len(before),
                "transcript_handle": digest_bytes(before),
                "transcript_delta": _delta(before),
            },
        )


def _jsonl(*rows: dict) -> bytes:
    return b"".join(
        json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
        for row in rows
    )


def test_first_horizon_banks_meaning_not_multi_megabyte_tool_rollout() -> None:
    compacted = {
        "type": "compacted",
        "ordinal": 7,
        "payload": {
            "window_id": "window-7",
            "replacement_history": [
                {
                    "type": "message", "id": "author-1", "role": "user",
                    "content": [{"type": "input_text", "text": "cadence is a standing law"}],
                },
                {
                    "type": "message", "id": "coord-1", "role": "user",
                    "content": [{
                        "type": "input_text",
                        "text": "<codex_delegation><input>already consumed</input></codex_delegation>",
                    }],
                },
            ],
        },
    }
    assistant = {
        "type": "response_item", "ordinal": 8,
        "payload": {
            "type": "message", "id": "assistant-1", "role": "assistant",
            "content": [{"type": "output_text", "text": "I chose the bounded fix-forward."}],
        },
    }
    browser_author = {
        "type": "response_item", "ordinal": 9,
        "payload": {
            "type": "message", "id": "author-2", "role": "user",
            "content": [{
                "type": "input_text",
                "text": "<in-app-browser-context>ambient</in-app-browser-context>\n"
                "## My request:\nMake the fold live and universal.",
            }],
        },
    }
    huge_tool = {
        "type": "response_item", "ordinal": 10,
        "payload": {
            "type": "custom_tool_call_output", "id": "tool-1", "output": "x" * 2_100_000,
        },
    }
    body = _jsonl(
        {"type": "turn_context", "payload": {"turn_id": "turn-9"}},
        compacted, assistant, browser_author, huge_tool,
    )
    assert len(body) > boundary._SEMANTIC_TEXT_LIMIT

    horizon = boundary._semantic_horizon(
        event=_event(Path("rollout.jsonl")), body=body, raw_start=0, first_boundary=True
    )

    assert horizon["status"] == "COMPLETE"
    assert horizon["source_boundary"]["kind"] == "latest-compacted-replacement-history"
    assert horizon["author_turn_count"] == 2
    assert horizon["assistant_decision_count"] == 1
    assert horizon["semantic_bytes"] < 2_000
    assert "cadence is a standing law" in horizon["semantic_text"]
    assert "Make the fold live and universal." in horizon["semantic_text"]
    assert "ambient" not in horizon["semantic_text"]
    assert "already consumed" not in horizon["semantic_text"]
    assert horizon["inert_aggregates"]["consumed-task-coordination"]["count"] == 1
    assert horizon["inert_aggregates"]["rollout-response_item"]["bytes"] > 2_000_000


def test_successor_horizon_starts_at_exact_predecessor_byte_boundary() -> None:
    prefix = _jsonl({
        "type": "response_item", "ordinal": 1,
        "payload": {
            "type": "message", "id": "old-author", "role": "user",
            "content": [{"type": "input_text", "text": "already sealed"}],
        },
    })
    suffix = _jsonl({
        "type": "response_item", "ordinal": 2,
        "payload": {
            "type": "message", "id": "new-author", "role": "user",
            "content": [{"type": "input_text", "text": "new distinction"}],
        },
    })

    horizon = boundary._semantic_horizon(
        event=_event(Path("rollout.jsonl")), body=prefix + suffix,
        raw_start=len(prefix), first_boundary=False,
    )

    assert horizon["source_boundary"]["kind"] == "predecessor-byte-boundary"
    assert horizon["source_boundary"]["semantic_start"] == len(prefix)
    assert "new distinction" in horizon["semantic_text"]
    assert "already sealed" not in horizon["semantic_text"]


def test_transcript_delta_custodies_raw_rollout_but_upfolds_semantic_horizon(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    body = _jsonl(
        {"type": "turn_context", "payload": {"turn_id": "turn-9"}},
        {
            "type": "response_item", "ordinal": 2,
            "payload": {
                "type": "message", "id": "author", "role": "user",
                "content": [{"type": "input_text", "text": "preserve this distinction"}],
            },
        },
        {
            "type": "response_item", "ordinal": 3,
            "payload": {"type": "custom_tool_call_output", "id": "tool", "output": "noise"},
        },
    )
    blobs: dict[str, bytes] = {}

    def put(data: bytes) -> str:
        handle = digest_bytes(data)
        blobs[handle] = data
        return handle

    monkeypatch.setattr(boundary.atlas_bridge, "put_custody", put)
    monkeypatch.setattr(boundary.atlas_bridge, "custody_has", lambda handle: handle in blobs)
    monkeypatch.setattr(
        "laplace.representation.embed_router.get_backend",
        lambda: SimpleNamespace(
            name="test-semantic", gpu=False, providers=("fixture",),
            embed=lambda chunks: [[1.0, 0.0] for _chunk in chunks],
        ),
    )
    monkeypatch.setattr(
        boundary, "read_health",
        lambda _root: {
            "status": "CURRENT",
            "side_ref_fold": {"status": "CURRENT","output_commit": "a" * 40, "manifest_handle": "sha256:" + "a" * 64},
            "up_down": {"receipt_handle": "sha256:" + "b" * 64},
        },
    )

    result = boundary._transcript_delta(
        tmp_path,
        event=_event(tmp_path / "rollout.jsonl"),
        transcript={"content_handle": digest_bytes(body)},
        body=body,
        predecessor=None,
    )

    assert result["transcript_handle"] == digest_bytes(body)
    assert result["suffix_handle"] == digest_bytes(body)
    assert result["semantic_horizon_handle"] != result["suffix_handle"]
    horizon = json.loads(blobs[result["semantic_horizon_handle"]])
    assert horizon["author_turn_count"] == 1
    assert "preserve this distinction" in horizon["semantic_text"]
    delta = json.loads(blobs[result["delta_custody_handle"]])
    assert delta["typed_descent"]["reference"] == result["semantic_horizon_handle"]
    assert delta["transcript"]["raw_suffix_custody_handle"] == result["suffix_handle"]
