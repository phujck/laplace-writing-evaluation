from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from laplace.representation import atlas_bridge
from laplace.engine import wake
from laplace.engine import compaction_submergence as organ
from laplace.representation.semantic_vertical import canonical_bytes, digest, digest_bytes

LEASE = "region-lease:ours"


def _authority(
    *,
    own_region: str = "src/laplace/engine/wake.py",
    disjoint: bool = False,
    ego_pending: int = 0,
) -> dict:
    leases = {
        LEASE: {
            "state": "ACTIVE",
            "authority": "write",
            "checkout": {
                "function": "ego",
                "seat_id": "ego-seat",
                "regions": [own_region],
            },
        }
    }
    if disjoint:
        leases["region-lease:aisthesis"] = {
            "state": "ACTIVE",
            "authority": "write",
            "checkout": {
                "function": "sensorium",
                "seat_id": "sensorium-seat",
                "regions": ["src/laplace/static/overlay.js"],
            },
        }
    authority = {
        "active_context": {"assumption": "a", "fibre": "f"},
        "development_review_root": "sha256:" + "1" * 64,
        "seat_occupancy": {
            "ego-seat": {"function": "ego", "generation": "generation:1"},
        },
        "recipient_mail": {
            "ego-seat": {"pending_count": ego_pending},
            **({"sensorium-seat": {"pending_count": 1}} if disjoint else {}),
        },
        "region_leases": leases,
        # These global accumulators move when Aisthesis checks out a disjoint region.  They are
        # intentionally not part of the ego function's consumed-root equality check.
        "region_lease_root": "sha256:" + ("3" if disjoint else "2") * 64,
    }
    return {
        "status": "CURRENT",
        "effective_checkpoint": {"authority": authority},
    }


def _recovery() -> dict:
    return {
        "schema_version": "laplace.engine.wake-recovery-coordinate/1",
        "status": "VERIFIED",
        "coordinate_state": "INVALID",
        "system_state": "RECOVERY",
        "custody_allowed": False,
        "actual_payload_digest": "sha256:" + "4" * 64,
    }


def _work_map() -> dict:
    return {
        "schema_version": "laplace.development-work-map/1",
        "status": "CURRENT",
        "active_context": {"assumption": "a", "fibre": "f"},
        "freshness": {"state": "CURRENT", "source_handle": "sha256:" + "5" * 64},
        "head_event_id": "sha256:" + "6" * 64,
        "head_record_digest": "sha256:" + "7" * 64,
        "omission_residual": {"status": "NONE"},
        "work": [
            {
                "state": "ACCEPTED",
                "publication_state": "CLOSED",
                "node_handle": "sha256:" + "8" * 64,
                "commission": {
                    "message_id": "message:commission",
                    "body_handle": "sha256:" + "9" * 64,
                },
                "verdict": {
                    "message_id": "message:verdict",
                    "body_handle": "sha256:" + "a" * 64,
                    "decision": "ACCEPT",
                },
                "review_residue": {"count": 0},
            }
        ],
    }


def _inertia() -> dict[str, int | float]:
    return {
        "coordination_layer_count": 1,
        "author_command_to_productive_act_ms": 12.0,
        "reconstructions": 6,
        "subprocesses": 1,
        "tokens": 100,
        "review_cycles": 0,
        "uniquely_caught_faults": 0,
    }


def _semantic_health() -> dict:
    return {
        "schema_version": "laplace.embedding-health/1",
        "status": "CURRENT",
        "shared": True,
        "side_ref_fold": {"status": "CURRENT",
            "manifest_handle": "sha256:" + "b" * 64,
            "coverage_handle": "sha256:" + "c" * 64,
            "semantic_horizon": {"nodes": 10},
            "output_commit": "f" * 40,
        },
        "up_down": {
            "receipt_handle": "sha256:" + "d" * 64,
            "register_generation": "sha256:" + "e" * 64,
        },
        "latest_receipt": {"embedding_counts": {"deferred": 0}},
        "consumption": {},
    }


def _profile(monkeypatch: pytest.MonkeyPatch, repo_root: Path = Path(".")) -> dict:
    monkeypatch.setattr(
        organ,
        "_git_coordinate",
        lambda _root: {"head": "b" * 40, "tree": "c" * 40},
    )
    monkeypatch.setattr("laplace.representation.embedding_health.read_health", lambda _root: _semantic_health())
    return organ.compile_profile(
        repo_root=repo_root,
        function="ego",
        seat_id="ego-seat",
        generation="generation:1",
        lease_ids=[LEASE],
        authority_epoch=_authority(),
        recovery_coordinate=_recovery(),
        work_map=_work_map(),
        inertia=_inertia(),
        source_collection_ms=20_000.0,
        semantic_health=_semantic_health(),
    )


def _install_custody(monkeypatch: pytest.MonkeyPatch, profile: dict) -> str:
    text = organ._canonical_bytes(profile).decode("utf-8")
    handle = "sha256:" + hashlib.sha256(text.encode()).hexdigest()
    monkeypatch.setattr(
        atlas_bridge,
        "custody_body",
        lambda *, handle: {"content_handle": handle, "text": text},
    )
    return handle


def test_cold_successor_allows_disjoint_dirty_work_and_unconsumed_lease_event(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    consumed = tmp_path / "src/laplace/engine/wake.py"
    consumed.parent.mkdir(parents=True)
    consumed.write_text("sealed ego bytes")
    profile = _profile(monkeypatch, tmp_path)
    handle = _install_custody(monkeypatch, profile)
    # Aisthesis edits and commits an unrelated tracked file. Its checkout also appends an Atlas
    # lease event. Neither movement changes an ego-consumed path or function authority root.
    (tmp_path / "aisthesis-dirty.js").write_text("disjoint local work")
    monkeypatch.setattr(
        organ,
        "_git_coordinate",
        lambda _root: {"head": "d" * 40, "tree": "e" * 40},
    )
    monkeypatch.setattr(atlas_bridge, "authority_epoch", lambda: _authority(disjoint=True))

    receipt = organ.reconstruct_cold_successor(
        repo_root=tmp_path,
        profile_handle=handle,
        function="ego",
        seat_id="ego-seat",
        generation="generation:1",
    )

    assert receipt["status"] == "AUTHORIZED"
    assert receipt["tools_enabled"] is True
    assert receipt["observation"]["git"] == {
        "sealed": {"head": "b" * 40, "tree": "c" * 40},
        "current": {"head": "d" * 40, "tree": "e" * 40},
    }
    assert receipt["performance"]["recovery_coordinate_verifier_runs"] == 0
    assert receipt["performance"]["retired_live_scaffold"] == (
        "postcompact-recovery-coordinate-revalidation"
    )


def test_cold_successor_refuses_dirty_movement_inside_consumed_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    consumed = tmp_path / "src/laplace/engine/wake.py"
    consumed.parent.mkdir(parents=True)
    consumed.write_text("sealed ego bytes")
    profile = _profile(monkeypatch, tmp_path)
    handle = _install_custody(monkeypatch, profile)
    monkeypatch.setattr(atlas_bridge, "authority_epoch", _authority)
    consumed.write_text("moved after PreCompact")

    with pytest.raises(organ.ContinuationRefused, match="consumed roots moved") as refused:
        organ.reconstruct_cold_successor(
            repo_root=tmp_path,
            profile_handle=handle,
            function="ego",
            seat_id="ego-seat",
            generation="generation:1",
        )

    assert "consumed_paths" in refused.value.divergence


def test_cold_successor_refuses_same_function_mail_but_ignores_other_seat_mail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = _profile(monkeypatch)
    handle = _install_custody(monkeypatch, profile)
    monkeypatch.setattr(
        atlas_bridge,
        "authority_epoch",
        lambda: _authority(disjoint=True, ego_pending=1),
    )

    with pytest.raises(organ.ContinuationRefused, match="consumed roots moved") as refused:
        organ.reconstruct_cold_successor(
            repo_root=Path("."),
            profile_handle=handle,
            function="ego",
            seat_id="ego-seat",
            generation="generation:1",
        )

    roots = refused.value.divergence["authority_consumed_roots"]
    assert roots["sealed"]["function_mail"] != roots["current"]["function_mail"]


def test_cold_successor_refuses_exact_consumed_lease_movement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = _profile(monkeypatch)
    handle = _install_custody(monkeypatch, profile)
    monkeypatch.setattr(
        atlas_bridge,
        "authority_epoch",
        lambda: _authority(own_region="src/laplace/changed.py", disjoint=True),
    )

    with pytest.raises(organ.ContinuationRefused, match="consumed roots moved") as refused:
        organ.reconstruct_cold_successor(
            repo_root=Path("."),
            profile_handle=handle,
            function="ego",
            seat_id="ego-seat",
            generation="generation:1",
        )

    assert "authority_consumed_roots" in refused.value.divergence


def test_cold_successor_refuses_wrong_function_before_tools_enable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = _profile(monkeypatch)
    handle = _install_custody(monkeypatch, profile)

    with pytest.raises(organ.ContinuationRefused, match="identity contradicts"):
        organ.reconstruct_cold_successor(
            repo_root=Path("."),
            profile_handle=handle,
            function="sensorium",
            seat_id="ego-seat",
            generation="generation:1",
        )


def test_cold_postcompact_reconstructs_exact_transcript_delta_from_custody(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fold_receipt = "sha256:" + "1" * 64
    suffix_handle = "sha256:" + "2" * 64
    body = {
        "schema_version": "laplace.precompact-semantic-delta/1",
        "status": "COMPLETE",
        "global_F": {
            "status": "CURRENT",
            "output_commit": "a" * 40,
            "manifest_handle": "sha256:" + "3" * 64,
            "semantic_fold_receipt_handle": fold_receipt,
        },
        "session_id": "thread-ego",
        "turn_id": "turn-7",
        "transcript": {
            "suffix_custody_handle": suffix_handle,
            "suffix_bytes": 17,
        },
        "author_turn_handle": "sha256:" + "4" * 64,
        "typed_descent": {
            "kind": "atlas-custody", "reference": suffix_handle, "source": "",
        },
        "up_receipt_handle": "sha256:" + "5" * 64,
        "n_deferred": 0,
    }
    body["delta_handle"] = digest(body)
    raw = canonical_bytes(body)
    custody_handle = digest_bytes(raw)
    profile = {
        "compaction_boundary": {
            "event": "PreCompact",
            "semantic_delta": {
                "delta_handle": body["delta_handle"],
                "delta_custody_handle": custody_handle,
                "global_fold_receipt_handle": fold_receipt,
                "typed_descent": body["typed_descent"],
            },
        }
    }
    monkeypatch.setattr(
        atlas_bridge,
        "custody_body",
        lambda *, handle: {"content_handle": handle, "text": raw.decode("utf-8")},
    )
    monkeypatch.setattr(
        "laplace.engine.descent.descend",
        lambda **_kwargs: {
            "content_status": "COMPLETE",
            "content_handle": suffix_handle,
            "content": "one new distinction",
        },
    )
    health = {
        "status": "CURRENT",
        "side_ref_fold": {"status": "CURRENT","output_commit": "a" * 40, "manifest_handle": "sha256:" + "3" * 64},
        "up_down": {"receipt_handle": fold_receipt},
    }

    result = organ._reconstruct_compaction_delta(profile, semantic_health=health)

    assert result["status"] == "COMPLETE"
    assert result["content"] == "one new distinction"
    assert result["delta_handle"] == body["delta_handle"]


def test_cold_postcompact_refuses_moved_transcript_delta_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        atlas_bridge,
        "custody_body",
        lambda **_kwargs: {"text": '{"moved":true}'},
    )
    with pytest.raises(organ.ContinuationRefused, match="custody bytes moved"):
        organ._reconstruct_compaction_delta(
            {
                "compaction_boundary": {
                    "event": "PreCompact",
                    "semantic_delta": {
                        "delta_handle": "sha256:" + "1" * 64,
                        "delta_custody_handle": "sha256:" + "2" * 64,
                    },
                }
            },
            semantic_health={"status": "CURRENT"},
        )


def test_precompact_seals_canonical_profile_in_existing_atlas_custody(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(atlas_bridge, "authority_epoch", _authority)
    monkeypatch.setattr(wake, "recovery_coordinate_glow", lambda _root: _recovery())
    monkeypatch.setattr(wake, "development_work_map_glow", lambda _root: _work_map())
    monkeypatch.setattr("laplace.representation.embedding_health.read_health", lambda _root: _semantic_health())
    monkeypatch.setattr(
        organ,
        "_git_coordinate",
        lambda _root: {"head": "b" * 40, "tree": "c" * 40},
    )
    stored: list[bytes] = []

    def put(data: bytes) -> str:
        stored.append(data)
        return "sha256:" + hashlib.sha256(data).hexdigest()

    monkeypatch.setattr(atlas_bridge, "put_custody", put)
    receipt = organ.seal_precompact(
        repo_root=Path("."),
        function="ego",
        seat_id="ego-seat",
        generation="generation:1",
        lease_ids=[LEASE],
        inertia=_inertia(),
    )

    assert receipt["status"] == "SEALED"
    assert receipt["event"] == "PreCompact"
    assert len(stored) == 1
    decoded = json.loads(stored[0])
    assert decoded["common_kernel"]["reconstruction_roots"] == organ.INTEGRATED_ROOTS
    assert decoded["leases"][LEASE]["checkout"]["regions"] == ["src/laplace/engine/wake.py"]
    authority = receipt["record_only_authority_receipt"]
    assert authority["source"]["content_handle"] == organ.CEREMONY_SUSPENSION_SHA256
    assert authority["reintroduction_default"] == "REMAIN-SUBMERGED"
    assert authority["reintroduction_earliest_boundary"].startswith(
        "The next publication staging boundary"
    )
    assert authority["concrete_error"] is None
    assert "global worktree cleanliness when the requested paths are clean and disjoint" in (
        authority["procedural_gates_bypassed"]
    )


def test_complete_goal_context_compiles_exact_common_kernel_and_function_overlay(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    artifact = {
        "schema_version": organ.GOAL_CONTEXT_SCHEMA,
        "status": "ACTIVE",
        "semantic_audit": {"actionable_semantic_directives": 42},
        "priority_frontier": ["P0", "P1", "P2"],
        "common_kernel": [{"id": "C01", "instruction": "direct authority"}],
        "seats": {
            "ego": {"goal": "engine"},
            "aisthesis": {"goal": "interface"},
            "superego": {"goal": "global judgment"},
        },
        "long_horizon": ["Synthetics Genesis remains unpaid"],
        "orchestration_account": {
            "ego": "maker/adversary",
            "aisthesis": "live visual result",
            "superego": "global synthesis",
        },
    }
    source = tmp_path / "three-seat.json"
    data = json.dumps(artifact, separators=(",", ":"), sort_keys=True).encode()
    source.write_bytes(data)
    handle = "sha256:" + hashlib.sha256(data).hexdigest()
    loaded = organ.load_goal_context(
        source, expected_handle=handle, expected_bytes=len(data)
    )
    monkeypatch.setattr(
        organ,
        "_git_coordinate",
        lambda _root: {"head": "b" * 40, "tree": "c" * 40},
    )

    profile = organ.compile_profile(
        repo_root=tmp_path,
        function="sensorium",
        seat_id="sensorium-seat",
        generation="generation:1",
        lease_ids=[],
        authority_epoch=_authority(),
        recovery_coordinate=_recovery(),
        work_map=_work_map(),
        inertia=_inertia(),
        goal_context=loaded,
    )

    goal = profile["goal_context"]
    assert goal["source"]["content_handle"] == handle
    assert goal["semantic_audit"]["actionable_semantic_directives"] == 42
    assert goal["common_kernel"] == artifact["common_kernel"]
    assert goal["seat_overlay"] == artifact["seats"]["aisthesis"]
    assert goal["orchestration_account"] == "live visual result"
    phase = profile["phase_controller"]
    assert phase["status"] == "CONSUMED"
    assert phase["receipt"]["source_handle"] == organ.HIERARCHY_DERIVATION_HANDLE
    assert phase["policy"]["minimum_sufficient_hierarchy"] == (
        "The minimum sufficient hierarchy for stable work."
    )
    assert phase["policy"]["historical_manuscript_status"] == (
        "SUPERSEDED-AND-QUARANTINED-REFERENCE"
    )


def test_wake_cold_profile_preflight_precedes_watcher_and_bypasses_revalidation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    recovery = _recovery()

    def preflight(_root: Path) -> dict:
        events.append("preflight")
        return {
            "status": "AUTHORIZED",
            "exact_profile": {"current_frontier": {"recovery_coordinate": recovery}},
        }

    monkeypatch.setattr(organ, "wake_preflight_from_environment", preflight)
    monkeypatch.setattr(
        "laplace.representation.codex_seat_watcher.ensure_from_environment",
        lambda _root: events.append("watcher") or {"status": "ACTIVE"},
    )
    monkeypatch.setattr(wake, "seat_fabric_glow", lambda: {"status": "READY"})
    monkeypatch.setattr(
        wake,
        "recovery_coordinate_glow",
        lambda _root: pytest.fail("sealed cold continuation must bypass revalidation"),
    )
    monkeypatch.setattr(wake, "development_work_map_glow", lambda _root: _work_map())
    monkeypatch.setattr(wake, "_semantic_block", lambda _root: {})
    monkeypatch.setattr("laplace.engine.process_health.probe", lambda: {})
    monkeypatch.setattr("laplace.engine.self_corpus.reconstruct_self", lambda *_a, **_k: {})

    payload = wake.wake_payload(repo_root=Path("."), grade=0, mode="engine")

    assert events == ["preflight", "watcher"]
    assert payload["recovery_coordinate"] == recovery
    assert payload["successor_profile"]["status"] == "AUTHORIZED"
