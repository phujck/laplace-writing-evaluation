from __future__ import annotations

from pathlib import Path

from laplace.engine import turn_reconstruction as turn

NEW = "sha256:" + "1" * 64
OLD = "sha256:" + "2" * 64
MANIFEST = "sha256:" + "3" * 64
FOLD_RECEIPT = "sha256:" + "a" * 64
POSTCOMPACT = "sha256:" + "b" * 64
TRANSCRIPT = "sha256:" + "c" * 64


def _heads(profile: str = NEW) -> dict:
    return {
        "schema_version": turn.HEADS_SCHEMA,
        "heads_handle": "sha256:" + "4" * 64,
        "phase_policy_consumption": {
            "status": "CONSUMED",
            "policy_handle": "sha256:" + "9" * 64,
        },
        "profiles": {
            "ego": {
                "function": "ego",
                "seat_id": "ego-seat",
                "task_id": "thread-ego",
                "profile_handle": profile,
                "generation": "generation:1",
                "routes": [
                    {
                        "purpose": "current-goals",
                        "kind": "atlas-custody",
                        "reference": profile,
                        "source": "",
                        "budget": 20_000,
                    }
                ],
            }
        },
    }


def _health(profile: str = NEW) -> dict:
    return {
        "schema_version": "laplace.embedding-health/1",
        "status": "CURRENT",
        "profile_handles": {"ego": profile},
        "current_source": {"commit": "a" * 40, "tree": "b" * 40},
        "side_ref_fold": {"status": "CURRENT",
            "source_commit": "9" * 40,
            "output_commit": "a" * 40,
            "manifest_handle": MANIFEST,
            "coverage_handle": "sha256:" + "5" * 64,
            "semantic_horizon": {"nodes": 100},
        },
        "up_down": {"receipt_handle": FOLD_RECEIPT, "register_generation": "r:1"},
        "artifacts": {"root": "sha256:" + "6" * 64},
    }


def _install(monkeypatch, *, profile: str = NEW) -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(turn, "load_heads", lambda _root: _heads(profile))
    monkeypatch.setattr(turn, "read_health", lambda _root: _health())
    monkeypatch.setattr("laplace.engine.compaction_boundary.active_profile", lambda _thread: None)
    monkeypatch.setattr(
        turn,
        "_git_dirty_custody",
        lambda _root: {"paths": [], "count": 0, "invalidation_root": "sha256:" + "7" * 64},
    )

    def descend(**kwargs):
        calls.append((kwargs["kind"], kwargs["reference"]))
        return {
            "content_status": "COMPLETE",
            "content_handle": "sha256:" + "8" * 64,
            "content": "P0 P1 P2 latest disagreement next actions",
            "content_next_offset": None,
            "read_only": True,
        }

    monkeypatch.setattr(turn.descent, "descend", descend)
    monkeypatch.setattr("laplace.representation.semantic_cadence.record_consumption", lambda **_kwargs: {})
    monkeypatch.setattr("laplace.representation.semantic_cadence.read_state", lambda: {"generation": "g:1"})
    return calls


def test_post_compaction_prompt_descends_fresh_profile_and_not_old_in_context_profile(
    monkeypatch, tmp_path: Path
) -> None:
    calls = _install(monkeypatch)

    got = turn.reconstruct_turn(
        tmp_path,
        event_name="UserPromptSubmit",
        prompt="after total context loss continue the current work",
        thread_id="thread-ego",
    )

    assert got["status"] == "ADMITTED"
    assert got["profile_handle"] == NEW
    assert OLD not in got["selected_nodes"]
    assert ("atlas-custody", NEW) in calls
    assert "P0 P1 P2" in got["selected"][0]["content"]


def test_stale_old_profile_cannot_pass_against_current_fold(monkeypatch, tmp_path: Path) -> None:
    _install(monkeypatch, profile=OLD)

    got = turn.reconstruct_turn(
        tmp_path,
        event_name="SessionStart",
        prompt="",
        thread_id="thread-ego",
    )

    assert got["status"] == "UNKNOWN"
    assert got["selected"] == []
    assert "stale against the shared fold" in got["fog"][0]["reason"]


def test_consumed_fabric_watcher_message_is_inert_after_compaction(
    monkeypatch, tmp_path: Path
) -> None:
    calls = _install(monkeypatch)
    consumed = "message:" + "a" * 64

    got = turn.reconstruct_turn(
        tmp_path,
        event_name="UserPromptSubmit",
        prompt=f"[Eigen Fabric watcher] old checkpoint message {consumed}",
        thread_id="thread-ego",
        attention_projection={"status": "CLEAR", "pending": []},
    )

    assert got["status"] == "ADMITTED"
    assert all(reference != consumed for _kind, reference in calls)
    assert consumed not in got["selected_nodes"]


def test_current_pending_fabric_message_is_descended_once(monkeypatch, tmp_path: Path) -> None:
    calls = _install(monkeypatch)
    pending = "message:" + "b" * 64

    turn.reconstruct_turn(
        tmp_path,
        event_name="UserPromptSubmit",
        prompt="[Eigen Fabric watcher] opaque token",
        thread_id="thread-ego",
        attention_projection={
            "status": "PENDING",
            "pending": [{"message_id": pending, "state": "queued"}],
        },
    )

    assert calls.count(("fabric-message", pending)) == 1


def test_warm_turn_overhead_is_measured_below_target_with_cached_faces(
    monkeypatch, tmp_path: Path
) -> None:
    _install(monkeypatch)

    got = turn.reconstruct_turn(
        tmp_path,
        event_name="UserPromptSubmit",
        prompt="ordinary current work",
        thread_id="thread-ego",
    )

    assert got["performance"]["target_ms"] == 50
    assert got["performance"]["elapsed_ms"] < 50
    body = {key: value for key, value in got.items() if key != "receipt_handle"}
    assert turn.digest(body) == got["receipt_handle"]


def test_postcompact_turn_uses_sealed_profile_and_transcript_delta_not_old_head(
    monkeypatch, tmp_path: Path
) -> None:
    calls = _install(monkeypatch)
    monkeypatch.setattr(
        "laplace.engine.compaction_boundary.active_profile",
        lambda _thread: {
            "function": "ego",
            "seat_id": "ego-seat",
            "generation": "generation:1",
            "profile_handle": POSTCOMPACT,
            "boundary_handle": "sha256:" + "d" * 64,
            "semantic_fold_health_handle": MANIFEST,
            "semantic_fold_receipt_handle": FOLD_RECEIPT,
            "transcript_delta": {
                "delta_handle": "sha256:" + "e" * 64,
                "typed_descent": {
                    "kind": "atlas-custody",
                    "reference": TRANSCRIPT,
                    "source": "",
                },
                "suffix_bytes": 128,
            },
        },
    )

    got = turn.reconstruct_turn(
        tmp_path,
        event_name="UserPromptSubmit",
        prompt="continue after total model-context loss",
        thread_id="thread-ego",
    )

    assert got["status"] == "ADMITTED"
    assert got["profile_handle"] == POSTCOMPACT
    assert ("atlas-custody", POSTCOMPACT) in calls
    assert ("atlas-custody", TRANSCRIPT) in calls
    assert ("atlas-custody", NEW) not in calls
    assert got["transcript_delta_handle"] == "sha256:" + "e" * 64
