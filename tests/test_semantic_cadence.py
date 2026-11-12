from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from laplace.representation import embedding_health, semantic_cadence


def _tuple(commit: str) -> dict:
    return {
        "schema_version": "laplace.semantic-fold-source-tuple/1",
        "git": {"commit": commit, "tree": f"tree-{commit}"},
        "profile_handles": {
            "ego": "sha256:ego",
            "aisthesis": "sha256:ais",
            "superego": "sha256:sup",
        },
        "source_tuple_handle": f"sha256:{commit}",
    }


def _running_state(generation: str, *, pending: dict | None = None) -> dict:
    state = {
        "schema_version": semantic_cadence.CADENCE_SCHEMA,
        "status": "RUNNING",
        "generation": generation,
        "desired_source": {"commit": "active", "tree": "tree-active"},
        "pid": os.getpid(),
        "process_start_token": semantic_cadence.process_start_token(),
        "last_success": None,
        "last_refusal": None,
        "orphan_reconciliations": 0,
    }
    if pending is not None:
        state["pending"] = pending
        state["pending_generation"] = pending["generation"]
    return state


def test_semantic_atlas_token_ignores_operational_motion() -> None:
    first = {
        "drift_token": {
            "schema_version": "atlas.conceptric-drift-token/1",
            "cursor": 1,
            "head_event_id": "sha256:event-a",
            "head_record_digest": "sha256:record-a",
        },
        "effective_checkpoint_digest": "sha256:checkpoint-a",
        "authority_roots": {
            "development_review_root": "sha256:development",
            "provider_session_root": "sha256:provider-a",
            "region_lease_root": "sha256:lease-a",
            "seat_mail_frontier_root": "sha256:mail-a",
            "seat_occupancy_root": "sha256:occupancy-a",
        },
        "integrity_boundary": "CHECKSUMMED-CRUTCH",
    }
    second = json.loads(json.dumps(first))
    second["authority_roots"].update(
        provider_session_root="sha256:provider-b",
        region_lease_root="sha256:lease-b",
        seat_mail_frontier_root="sha256:mail-b",
        seat_occupancy_root="sha256:occupancy-b",
    )
    second["drift_token"]["cursor"] = 2
    second["effective_checkpoint_digest"] = "sha256:checkpoint-b"
    first_tuple = {
        "schema_version": "laplace.semantic-fold-source-tuple/2",
        "atlas": semantic_cadence._semantic_atlas_token(first),
        "git": {"commit": "source", "tree": "tree"},
    }
    second_tuple = {
        **first_tuple,
        "atlas": semantic_cadence._semantic_atlas_token(second),
    }
    assert first_tuple["atlas"] != second_tuple["atlas"]
    assert semantic_cadence.semantic_generation(first_tuple) == semantic_cadence.semantic_generation(
        second_tuple
    )
    second["authority_roots"]["development_review_root"] = "sha256:development-b"
    second_tuple["atlas"] = semantic_cadence._semantic_atlas_token(second)
    assert semantic_cadence.semantic_generation(first_tuple) != semantic_cadence.semantic_generation(
        second_tuple
    )


def test_semantic_identity_ignores_derived_head_handle_but_not_profile_meaning() -> None:
    first = {
        "schema_version": "laplace.semantic-fold-source-tuple/2",
        "git": {"commit": "source", "tree": "tree"},
        "atlas": {
            "schema_version": "laplace.semantic-atlas-currentness-token/2",
            "semantic_roots": {"development_review_root": "sha256:development"},
            "integrity_boundary": "CHECKSUMMED-CRUTCH",
            "operational_roots": "observed separately",
        },
        "profile_heads_handle": "sha256:derived-before",
        "profile_heads": {
            "ego": {
                "profile_handle": "sha256:ego",
                "goal_digest": "sha256:goal",
                "phase_policy_handle": "sha256:phase",
            }
        },
    }
    derived_move = json.loads(json.dumps(first))
    derived_move["profile_heads_handle"] = "sha256:derived-after"
    assert semantic_cadence.semantic_generation(first) == semantic_cadence.semantic_generation(
        derived_move
    )
    meaning_move = json.loads(json.dumps(derived_move))
    meaning_move["profile_heads"]["ego"]["goal_digest"] = "sha256:new-goal"
    assert semantic_cadence.semantic_generation(first) != semantic_cadence.semantic_generation(
        meaning_move
    )


def test_successful_generation_validation_does_not_hash_receipt_locator(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = _tuple("source")
    outer = {
        "receipt_object": "git-object",
        "source_commit": "source",
        "source_tuple": source,
        "source_tuple_handle": source["source_tuple_handle"],
    }
    monkeypatch.setattr(embedding_health, "_read_outer_receipt", lambda *_: dict(outer))

    def validate(_root: Path, *, output_commit: str, outer_receipt: dict) -> dict:
        assert output_commit == "fold"
        assert "receipt_object" not in outer_receipt
        return {"status": "VALIDATED"}

    monkeypatch.setattr(embedding_health, "validate_fold_candidate", validate)
    state = {
        "source_tuple": source,
        "last_success": {
            "semantic_fold_receipt_object": "git-object",
            "output_commit": "fold",
        },
    }
    assert semantic_cadence._successful_generation_valid(tmp_path, state, source)


def test_running_generation_keeps_only_newest_pending(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    state_root = tmp_path / "state"
    monkeypatch.setenv("LAPLACE_SEMANTIC_STATE_ROOT", str(state_root))
    semantic_cadence._write(
        state_root / "cadence.json", _running_state("sha256:active")
    )
    monkeypatch.setattr(
        semantic_cadence,
        "_source_tuple",
        lambda _root, *, source_commit, source_tree: _tuple(source_commit),
    )
    monkeypatch.setattr(
        semantic_cadence,
        "pinned_side_refs",
        lambda _root, *, source_commit: {
            "semantic_fold": "fold",
            "semantic_fold_receipt": "receipt",
            "prior_source_commit": "base",
            "prior_receipt_handle": "sha256:receipt",
        },
    )
    monkeypatch.setattr(
        semantic_cadence.subprocess,
        "Popen",
        lambda *_args, **_kwargs: pytest.fail("a second producer was launched"),
    )
    first = semantic_cadence.enqueue(
        tmp_path, source_commit="next-a", source_tree="tree-next-a"
    )
    second = semantic_cadence.enqueue(
        tmp_path, source_commit="next-b", source_tree="tree-next-b"
    )
    assert first["pending_generation"] == semantic_cadence.semantic_generation(_tuple("next-a"))
    assert second["pending_generation"] == semantic_cadence.semantic_generation(_tuple("next-b"))
    assert semantic_cadence.read_state()["generation"] == "sha256:active"
    assert semantic_cadence.read_state()["pending"]["desired_source"]["commit"] == "next-b"


def test_finish_exposes_pending_once_and_clears_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    state_root = tmp_path / "state"
    monkeypatch.setenv("LAPLACE_SEMANTIC_STATE_ROOT", str(state_root))
    pending = {
        "generation": "sha256:next",
        "desired_source": {"commit": "next", "tree": "tree-next"},
    }
    semantic_cadence._write(
        state_root / "cadence.json", _running_state("sha256:active", pending=pending)
    )
    terminal = semantic_cadence.finish_generation(
        "sha256:active", status="SUCCEEDED", receipt={"output_commit": "fold"}
    )
    assert terminal["next_pending"] == pending
    disk = semantic_cadence.read_state()
    assert disk["status"] == "SUCCEEDED"
    assert "pending" not in disk
    assert "pending_generation" not in disk


def test_finish_promotes_pending_with_the_just_published_side_refs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    state_root = tmp_path / "state"
    monkeypatch.setenv("LAPLACE_SEMANTIC_STATE_ROOT", str(state_root))
    monkeypatch.setenv("LAPLACE_DISABLE_SEMANTIC_CADENCE", "1")
    pending = {
        "generation": "sha256:next",
        "desired_source": {"commit": "next", "tree": "tree-next"},
        "source_tuple": _tuple("next"),
        "side_refs": {"semantic_fold": "stale-fold"},
        "repository_generation": {"commit": "next", "tree": "tree-next"},
        "profile_handles": {},
        "goal_context_path": "goal.json",
        "queued_monotonic_ns": 1,
        "observed_at": "then",
    }
    semantic_cadence._write(
        state_root / "cadence.json", _running_state("sha256:active", pending=pending)
    )
    fresh = {
        "semantic_fold": "just-published-fold",
        "semantic_fold_receipt": "just-published-receipt",
        "prior_source_commit": "active-source",
        "prior_receipt_handle": "sha256:receipt",
    }
    monkeypatch.setattr(
        semantic_cadence,
        "pinned_side_refs",
        lambda _root, *, source_commit: dict(fresh),
    )
    promoted = semantic_cadence.finish_generation(
        "sha256:active",
        status="SUCCEEDED",
        receipt={"output_commit": "just-published-fold"},
        repo_root=tmp_path,
    )
    assert promoted["status"] == "QUEUED"
    assert promoted["side_refs"] == fresh
    assert promoted["previous_terminal_status"] == "SUCCEEDED"
    disk = semantic_cadence.read_state()
    assert disk["generation"] == "sha256:next"
    assert disk["side_refs"] == fresh


def test_incremental_receipt_requires_exact_trigger_and_cache() -> None:
    receipt = {
        "mode": "incremental",
        "full_requested": False,
        "device": {
            "required": True,
            "embedding_backend": "gpu",
            "embedding_providers": ["CUDAExecutionProvider"],
        },
        "embedding_counts": {"cached": 10, "deferred": 0, "total": 10},
        "trigger_receipt": {
            "gate": "rung-12a",
            "deposit_act_id": "act",
            "events": [{"kind": "delta_measured"}, {"kind": "incremental_applied"}],
        },
    }
    embedding_health._validate_deposit_receipt(receipt)
    receipt["embedding_counts"]["cached"] = 0
    with pytest.raises(RuntimeError, match="no reused cached embedding"):
        embedding_health._validate_deposit_receipt(receipt)


def test_full_rebuild_receipt_is_valid_when_requested_or_when_demanded_and_allowed() -> None:
    base = {
        "mode": "full-rebuild",
        "device": {"required": True, "embedding_backend": "gpu", "embedding_providers": ["CUDAExecutionProvider"]},
        "embedding_counts": {"cached": 0, "deferred": 0, "total": 10},
    }
    embedding_health._validate_deposit_receipt({**base, "full_requested": True})
    demanded = {"gate": "rung-12a", "deposit_act_id": "act",
                "events": [{"kind": "delta_measured"}, {"kind": "full_rebuild_demanded", "reason": "churn 27% > 20%", "allowed": True}]}
    embedding_health._validate_deposit_receipt({**base, "full_requested": False, "trigger_receipt": demanded})
    with pytest.raises(RuntimeError, match="neither requested"):
        embedding_health._validate_deposit_receipt({**base, "full_requested": False})
    not_allowed = {**demanded, "events": [{"kind": "full_rebuild_demanded", "reason": "churn 27% > 20%", "allowed": False}]}
    with pytest.raises(RuntimeError, match="neither requested"):
        embedding_health._validate_deposit_receipt({**base, "full_requested": False, "trigger_receipt": not_allowed})


def test_pinned_side_refs_use_prior_source_not_prior_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        semantic_cadence,
        "_git_ref",
        lambda _root, ref: "fold" if ref.endswith("semantic-fold") else "receipt",
    )
    monkeypatch.setattr(
        embedding_health,
        "_read_outer_receipt",
        lambda *_: {
            "output_commit": "fold",
            "source_commit": "prior-source",
            "receipt_handle": "sha256:receipt",
        },
    )
    monkeypatch.setattr(
        semantic_cadence.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0),
    )
    assert semantic_cadence.pinned_side_refs(
        tmp_path, source_commit="new-source"
    )["prior_source_commit"] == "prior-source"


def test_worker_seeds_only_a_verified_enqueue_pinned_fold(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script_path = Path(__file__).parents[1] / "scripts" / "semantic_cadence.py"
    spec = importlib.util.spec_from_file_location("semantic_cadence_script", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    side_refs = {
        "semantic_fold": "fold",
        "semantic_fold_receipt": "receipt",
        "prior_source_commit": "prior",
        "prior_receipt_handle": "sha256:receipt",
    }
    monkeypatch.setattr(
        semantic_cadence,
        "pinned_side_refs",
        lambda *_args, **_kwargs: dict(side_refs),
    )
    monkeypatch.setattr(
        module,
        "_read_outer_receipt",
        lambda *_: {"receipt_handle": "sha256:receipt", "receipt_object": "receipt"},
    )
    monkeypatch.setattr(
        module,
        "validate_fold_candidate",
        lambda *_args, **_kwargs: {"status": "VALIDATED"},
    )
    commands: list[list[str]] = []
    monkeypatch.setattr(
        module,
        "_run",
        lambda command, **_kwargs: commands.append(command) or "",
    )
    result = module._seed_verified_prior_fold(
        tmp_path, tmp_path / "worktree", side_refs, source_commit="source"
    )
    assert result["state"] == "VERIFIED-SEEDED"
    assert commands[0][:3] == ["git", "restore", "--source=fold"]
    assert "--worktree" in commands[0]


@pytest.mark.parametrize("entry", ["--enqueue-current", "--worker"])
def test_retired_entry_refuses_without_starting_work(monkeypatch, capsys, entry) -> None:
    root = Path(__file__).parents[1]
    spec = importlib.util.spec_from_file_location("retired_cadence", root / "scripts/semantic_cadence.py")
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)

    def forbidden(*args, **kwargs):
        raise AssertionError("retired cadence must not start work or mutate state")

    monkeypatch.setattr(script.semantic_cadence, "enqueue", forbidden)
    monkeypatch.setattr(script.semantic_cadence, "finish_generation", forbidden)
    monkeypatch.setattr(script.subprocess, "run", forbidden)
    monkeypatch.setattr(script.sys, "argv", ["semantic_cadence.py", entry])
    assert script.main() == 2
    refusal = json.loads(capsys.readouterr().out)
    assert refusal["status"] == "REFUSED"
    assert refusal["reason_code"] == "SEMANTIC-SIDE-REF-CADENCE-RETIRED"
    assert refusal["authority_effect"] == "none"
    assert script._worker(root, "fixture")["reason_code"] == refusal["reason_code"]
