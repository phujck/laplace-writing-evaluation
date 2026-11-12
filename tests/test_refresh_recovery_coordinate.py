from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from atlas.ids import chash

from laplace.representation import recovery_coordinate as RECOVERY
from laplace.representation.recovery_coordinate import canonical_payload_digest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "refresh_recovery_coordinate_test", ROOT / "scripts" / "refresh_recovery_coordinate.py"
)
assert SPEC and SPEC.loader
REFRESH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REFRESH)

VERIFY_SPEC = importlib.util.spec_from_file_location(
    "verify_recovery_coordinate_test", ROOT / "scripts" / "verify_recovery_coordinate.py"
)
assert VERIFY_SPEC and VERIFY_SPEC.loader
VERIFY = importlib.util.module_from_spec(VERIFY_SPEC)
VERIFY_SPEC.loader.exec_module(VERIFY)


def _verification() -> dict:
    return {
        "coordinate_state": "SUPERSESSION-REQUIRED",
        "system_state": "RECOVERY",
        "supersession_axes": ["git"],
        "hard_reds": [],
        "coordinate": {"recorded_payload_digest": "sha256:old"},
        "git": {
            "current_head": "a" * 40,
            "status_nul_sha256": "sha256:status",
            "tracked_diff_sha256": "sha256:diff",
            "staged_diff_sha256": "sha256:staged",
            "dirty_paths": ["user.txt"],
        },
        "runtime_atlas": {
            "live": {"cursor": 9, "head_event_id": "event:9", "head_record_digest": "digest:9"},
            "active_context": {"assumption": "one", "fibre": "s2"},
        },
        "semantic_fold": {
            "folded_git_head": "f" * 40,
            "current_git_head": "a" * 40,
            "commits_behind": 3,
            "status": "STALE",
        },
        "blueprint": {
            "generation_id": "generation:1",
            "pour_handle": "pour:1",
            "current": False,
            "moved_source_roots": ["src/x.py"],
            "counts": {"clauses": 1},
        },
        "fabric_debt": {
            "total": 2,
            "message_ids_sha256": "sha256:messages",
            "expanded_source_message_ids": ["a"],
            "by_seat": {
                "ego-seat": {
                    "count": 2,
                    "queued": 1,
                    "pulled": 1,
                    "message_ids": ["a", "b"],
                }
            },
        },
    }


def _live_contact(session: str = "codex:new-superego") -> dict:
    return {
        "schema_version": "atlas.recovery-live-contact/1",
        "derived_from": {
            "schema_version": "atlas.conceptric-drift-token/1",
            "cursor": 12,
            "head_event_id": "event:12",
            "head_record_digest": "digest:12",
        },
        "required_seats": ["superego-seat"],
        "seats": {
            "superego-seat": {
                "state": "BOUND",
                "routing_authority": True,
                "mail_state": "MAIL_READY",
                "function": "superego",
                "provider_session_ref": session,
                "join_event_id": "join:12",
                "binding_event_id": "binding:12",
            }
        },
        "claim_boundary": "Atlas occupancy evidence only",
    }


def test_successor_is_compact_digest_bound_and_carries_recovery_reds(monkeypatch) -> None:
    monkeypatch.setattr(REFRESH, "_git_tree_from_verification", lambda _git: "t" * 40)
    previous = {
        "coordinate_id": "coordinate:one",
        "coordinate_version": 2,
        "digest_contract": "contract",
        "carried_contract": {"path": "v1.json", "payload_digest": "sha256:v1"},
        "stage_frontier": {"next_act": "ATLAS-S2"},
        "active_goal": "heal",
        "live_contact": {"judge": "delivered"},
        "authority": {"reference_only": True},
        "fabric_debt": {"expanded_identity_source": {"path": "v1.json"}},
    }
    result = REFRESH.build_successor(
        previous,
        _verification(),
        previous_path="v2.json",
        output_path="atlas/packets/recovery/current.json",
        packaging_paths=[],
        created_at="2026-08-26T00:00:00Z",
        live_contact=_live_contact(),
    )
    assert result["coordinate_version"] == 3
    assert result["supersedes"]["path"] == "v2.json"
    assert result["freshness_vector"]["semantic_fold"]["status"] == "STALE"
    assert result["fabric_debt"]["total"] == 2
    assert result["fabric_debt"]["status"] == "NONTERMINAL"
    assert result["fabric_debt"]["identity_delta"] == {
        "added_message_ids": ["b"],
        "resolved_message_ids": [],
    }
    assert result["freshness_vector"]["git"]["allowed_descendant_paths"] == [
        "atlas/packets/recovery/current.json"
    ]
    assert result["live_contact"] == _live_contact()
    assert "claude" not in str(result["live_contact"]).lower()
    assert result["coordinate_payload_digest"] == canonical_payload_digest(result)


def test_successor_carries_exact_runtime_recovery_point_and_mints_external_anchor(
    monkeypatch,
) -> None:
    monkeypatch.setattr(REFRESH, "_git_tree_from_verification", lambda _git: "t" * 40)
    point = {
        "schema_version": "laplace.runtime-recovery-point/1",
        "status": "HISTORICAL-CHECKSUMMED",
        "authenticated": False,
        "integrity_boundary": "CHECKSUMMED-CRUTCH",
        "source_snapshot_id": "sha256:" + ("1" * 64),
        "source_receipt_digest": "sha256:" + ("2" * 64),
        "source_ledger_sha256": "sha256:" + ("3" * 64),
        "source_custody_roots": {},
        "source_checkpoint": {"checkpoint_digest": "sha256:" + ("4" * 64)},
        "source_authority_context_root": "sha256:" + ("5" * 64),
        "source_git": {"commit": "a" * 40, "tree": "b" * 40},
        "source_recovery_coordinate_payload_digest": "sha256:" + ("6" * 64),
        "whole_directory_rollback_without_external_anchor": "UNPAID",
        "predecessor_adoption_root": "sha256:" + ("7" * 64),
    }
    point["point_root"] = REFRESH._chash(point)
    previous = {
        "coordinate_id": "coordinate:portable",
        "coordinate_version": 3,
        "digest_contract": "contract",
        "stage_frontier": {},
        "active_goal": "recover",
        "authority": {"reference_only": True},
    }

    result = REFRESH.build_successor(
        previous,
        _verification(),
        previous_path="v3.json",
        output_path="atlas/packets/recovery/current.json",
        packaging_paths=[],
        created_at="2026-08-28T05:00:00Z",
        live_contact=_live_contact(),
        runtime_recovery_point=point,
    )

    assert result["runtime_recovery_point"] == point
    grant = result["runtime_recovery_grant"]
    grant_body = dict(grant)
    grant_root = grant_body.pop("grant_anchor_root")
    assert grant_root == REFRESH._chash(grant_body)
    assert grant["point_root"] == point["point_root"]
    assert grant["predecessor_coordinate_payload_digest"] == "sha256:old"
    assert result["coordinate_payload_digest"] == canonical_payload_digest(result)


def test_runtime_point_and_grant_share_atlas_compact_object_identity(
    monkeypatch,
) -> None:
    receipt = {
        "schema_version": "laplace.runtime-atlas-custody/2",
        "authenticated": False,
        "integrity_boundary": "CHECKSUMMED-CRUTCH",
        "snapshot_id": "sha256:" + ("1" * 64),
        "ledger": {"sha256": "sha256:" + ("2" * 64)},
        "custody_roots": {"ledger": "sha256:" + ("2" * 64)},
        "source_checkpoint": {
            "checkpoint_digest": "sha256:" + ("3" * 64),
            "cursor": 7,
            "head_event_id": "sha256:" + ("4" * 64),
            "head_record_digest": "sha256:" + ("5" * 64),
        },
        "source_authority_context": {
            "evidence_root": "sha256:" + ("6" * 64),
        },
        "source_git": {"commit": "a" * 40, "tree": "b" * 40},
        "recovery_coordinate_payload_digest": "sha256:" + ("7" * 64),
    }
    receipt["receipt_payload_digest"] = RECOVERY._canonical_receipt_digest(receipt)
    point = RECOVERY.runtime_recovery_point_from_receipt(receipt)
    point_body = dict(point)
    point_root = point_body.pop("point_root")
    assert point_root == chash(point_body)
    assert point["predecessor_adoption_root"] == chash(
        {
            "schema_version": "laplace.portable-adoption-lineage/1",
            "source_snapshot_id": point["source_snapshot_id"],
            "source_checkpoint_digest": point["source_checkpoint"][
                "checkpoint_digest"
            ],
            "predecessor": None,
        }
    )

    monkeypatch.setattr(REFRESH, "_git_tree_from_verification", lambda _git: "t" * 40)
    successor = REFRESH.build_successor(
        {
            "coordinate_id": "coordinate:portable-cross-module",
            "coordinate_version": 12,
            "digest_contract": "contract",
            "stage_frontier": {},
            "active_goal": "recover",
            "authority": {"reference_only": True},
        },
        _verification(),
        previous_path="v12.json",
        output_path="atlas/packets/recovery/current.json",
        packaging_paths=[],
        created_at="2026-08-28T06:00:00Z",
        live_contact=_live_contact(),
        runtime_recovery_point=point,
    )
    assert RECOVERY._verify_runtime_recovery_coordinate_claim(successor)["status"] == "EXACT"
    grant_body = dict(successor["runtime_recovery_grant"])
    grant_root = grant_body.pop("grant_anchor_root")
    assert grant_root == chash(grant_body)

    newline_root = RECOVERY._canonical_map_digest(point_body)
    assert newline_root != point_root
    malformed = dict(point)
    malformed["point_root"] = newline_root
    with pytest.raises(ValueError, match="runtime recovery point root does not verify"):
        REFRESH.build_successor(
            {
                "coordinate_id": "coordinate:portable-cross-module",
                "coordinate_version": 12,
                "digest_contract": "contract",
                "stage_frontier": {},
                "active_goal": "recover",
                "authority": {"reference_only": True},
            },
            _verification(),
            previous_path="v12.json",
            output_path="atlas/packets/recovery/current.json",
            packaging_paths=[],
            created_at="2026-08-28T06:00:00Z",
            live_contact=_live_contact(),
            runtime_recovery_point=malformed,
        )
    refused = RECOVERY._verify_runtime_recovery_coordinate_claim(
        {
            "runtime_recovery_point": malformed,
            "runtime_recovery_grant": successor["runtime_recovery_grant"],
        }
    )
    assert refused == {
        "status": "INVALID",
        "reason": "runtime recovery point root mismatch",
    }


def test_invalid_coordinate_cannot_found_a_successor() -> None:
    verification = _verification()
    verification["coordinate_state"] = "INVALID"
    try:
        REFRESH.build_successor(
            {"coordinate_id": "x"},
            verification,
            previous_path="old.json",
            output_path="atlas/packets/recovery/current.json",
            packaging_paths=[],
            created_at="now",
            live_contact=_live_contact(),
        )
    except ValueError as exc:
        assert "INVALID" in str(exc)
    else:
        raise AssertionError("INVALID coordinate unexpectedly founded a successor")


def test_historical_superseded_coordinate_cannot_found_a_fork() -> None:
    verification = _verification()
    verification["coordinate_state"] = "SUPERSEDED"
    try:
        REFRESH.build_successor(
            {"coordinate_id": "x"},
            verification,
            previous_path="old.json",
            output_path="atlas/packets/recovery/current.json",
            packaging_paths=[],
            created_at="now",
            live_contact=_live_contact(),
        )
    except ValueError as exc:
        assert "SUPERSEDED" in str(exc)
    else:
        raise AssertionError("SUPERSEDED coordinate unexpectedly founded a fork")


def test_mutable_alias_requires_an_exact_committed_immutable_predecessor(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(REFRESH, "ROOT", tmp_path)
    packet = tmp_path / "atlas" / "packets" / "recovery"
    packet.mkdir(parents=True)
    alias = packet / "RECOVERY-COORDINATE-CURRENT.json"
    previous = {
        "coordinate_version": 5,
        "created_at": "2026-08-26T12:00:00Z",
    }
    alias.write_text(json.dumps(previous), encoding="utf-8")
    archive = packet / "RECOVERY-COORDINATE-20260826-v5.json"

    with pytest.raises(ValueError, match="cannot supersede itself"):
        REFRESH._resolve_predecessor_path(alias, alias, previous)

    archive.write_bytes(alias.read_bytes())
    monkeypatch.setattr(REFRESH, "_committed_file_exact", lambda _path: False)
    with pytest.raises(ValueError, match="not exact against its committed Git blob"):
        REFRESH._resolve_predecessor_path(alias, alias, previous)

    monkeypatch.setattr(REFRESH, "_committed_file_exact", lambda _path: True)
    assert REFRESH._resolve_predecessor_path(alias, alias, previous) == archive

    archive.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="disagrees with the current alias"):
        REFRESH._resolve_predecessor_path(alias, alias, previous)


def test_successor_cannot_bless_handoff_or_source_as_packaging() -> None:
    try:
        REFRESH.build_successor(
            {"coordinate_id": "x"},
            _verification(),
            previous_path="old.json",
            output_path="atlas/packets/recovery/current.json",
            packaging_paths=["HANDOFF.md", "src/laplace/representation/recovery_coordinate.py"],
            created_at="now",
            live_contact=_live_contact(),
        )
    except ValueError as exc:
        assert "cannot bless source or handoff" in str(exc)
    else:
        raise AssertionError("source movement was accepted as coordinate packaging")


def test_successor_refuses_missing_required_live_contact(monkeypatch) -> None:
    monkeypatch.setattr(REFRESH, "_git_tree_from_verification", lambda _git: "t" * 40)
    contact = _live_contact()
    contact["seats"] = {}
    try:
        REFRESH.build_successor(
            {"coordinate_id": "x"},
            _verification(),
            previous_path="old.json",
            output_path="atlas/packets/recovery/current.json",
            packaging_paths=[],
            created_at="now",
            live_contact=contact,
        )
    except ValueError as exc:
        assert "missing_required_seats" in str(exc)
    else:
        raise AssertionError("successor copied an absent live contact")


def test_live_contact_derives_only_exact_bound_routing_occupancy(monkeypatch) -> None:
    occupancy = {
        "state": "BOUND",
        "routing_authority": True,
        "join": {"mail_state": "MAIL_READY", "defects": []},
        "join_event_id": "join:new",
        "binding_event_id": "binding:new",
        "binding": {
            "function": "superego",
            "provider_session_ref": "codex:new",
            "registered_principal_ref": "logical:superego-seat",
            "provider_identity_proof_handle": "proof:new",
        },
        "defects": [],
    }

    class Bridge:
        @staticmethod
        def snapshot():
            return {"provider": {"seat_occupancy": {"superego-seat": occupancy}}}

        @staticmethod
        def drift_token():
            return {
                "schema_version": "atlas.conceptric-drift-token/1",
                "cursor": 20,
                "head_event_id": "event:20",
                "head_record_digest": "digest:20",
            }

    from laplace.representation import atlas_bridge

    monkeypatch.setattr(atlas_bridge, "snapshot", Bridge.snapshot)
    monkeypatch.setattr(atlas_bridge, "drift_token", Bridge.drift_token)
    result = REFRESH.derive_live_contact()

    assert result["seats"]["superego-seat"]["provider_session_ref"] == "codex:new"
    assert result["seats"]["superego-seat"]["binding_event_id"] == "binding:new"
    assert result["derived_from"]["cursor"] == 20


def test_live_contact_refuses_atlas_movement_during_projection(monkeypatch) -> None:
    occupancy = {
        "state": "BOUND",
        "routing_authority": True,
        "join": {"mail_state": "MAIL_READY", "defects": []},
        "join_event_id": "join:new",
        "binding_event_id": "binding:new",
        "binding": {
            "function": "superego",
            "provider_session_ref": "codex:new",
            "registered_principal_ref": "logical:superego-seat",
            "provider_identity_proof_handle": "proof:new",
        },
        "defects": [],
    }
    cursors = iter((20, 21))

    from laplace.representation import atlas_bridge

    monkeypatch.setattr(
        atlas_bridge,
        "snapshot",
        lambda: {"provider": {"seat_occupancy": {"superego-seat": occupancy}}},
    )
    monkeypatch.setattr(
        atlas_bridge,
        "drift_token",
        lambda: {"schema_version": "token/1", "cursor": next(cursors)},
    )
    try:
        REFRESH.derive_live_contact()
    except ValueError as exc:
        assert "moved while reconstructing" in str(exc)
    else:
        raise AssertionError("moving live contact projection was accepted")


def test_refresh_refusal_is_json_not_a_traceback(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        REFRESH, "main", lambda: (_ for _ in ()).throw(ValueError("INVALID cannot found successor"))
    )
    assert REFRESH.cli() == 1
    result = __import__("json").loads(capsys.readouterr().out)
    assert result["refused"] is True
    assert result["successor_written"] is False
    assert result["residue"]["code"] == "SUCCESSOR_MINT_REFUSED"


def test_verify_refusal_is_json_not_a_traceback(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        VERIFY, "main", lambda: (_ for _ in ()).throw(ValueError("outside authority root"))
    )
    assert VERIFY.cli() == 1
    result = __import__("json").loads(capsys.readouterr().out)
    assert result["coordinate_state"] == "INVALID"
    assert result["custody_allowed"] is False
    assert result["residue"]["code"] == "COORDINATE_SOURCE_REFUSED"
