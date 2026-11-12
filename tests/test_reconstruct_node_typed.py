from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "reconstruct_node_typed_test", ROOT / "scripts" / "reconstruct_node.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_only_unambiguous_id_grammars_bypass_semantic_routing() -> None:
    assert MODULE.typed_target("WO-20260825-x", None, None) == (
        "ledger-row",
        "work_orders",
    )
    assert MODULE.typed_target("message:abc", None, None) == ("fabric-message", "")
    assert MODULE.typed_target("design-clause:abc", None, None) == ("blueprint", "")
    assert MODULE.typed_target("ATLAS-S2", None, None) == ("campaign-stage", "")
    assert MODULE.typed_target("M-interface-zero-context-law", None, None) == (
        "ledger-row",
        "methods",
    )
    assert MODULE.typed_target("sha256:" + "0" * 64, None, None) is None
    assert MODULE.typed_target("region-lease:abc", None, None) == ("atlas-object", "")
    assert MODULE.typed_target("lease:region-lease:abc", None, None) == (
        "atlas-object",
        "",
    )
    assert MODULE.typed_target("seat:codex-seat", None, None) == ("atlas-object", "")
    assert MODULE.typed_target("event:sha256:" + "1" * 64, None, None) == (
        "atlas-object",
        "",
    )
    assert MODULE.typed_target("anything", "ledger-row", "promises") == (
        "ledger-row",
        "promises",
    )
    assert MODULE.typed_target("DESIGN_2099-missing.md", None, None) == (
        "repository-file",
        "",
    )
    assert MODULE.typed_target(
        "atlas/packets/recovery/RECOVERY-COORDINATE-20260826.json", None, None
    ) == ("repository-file", "")


def test_canonical_atlas_object_claim_never_falls_through_to_semantic_routing(
    monkeypatch, capsys
) -> None:
    semantic_called = False

    def semantic_bomb(*_args, **_kwargs):
        nonlocal semantic_called
        semantic_called = True
        raise AssertionError("canonical Atlas object reached semantic routing")

    def refuse(**kwargs):
        raise MODULE.D.DescentRefused(
            "missing exact object",
            residue={
                "schema_version": "laplace.engine.descent-residue/1",
                "code": "NOT_FOUND",
                "reference": kwargs["reference"],
            },
        )

    monkeypatch.setattr(MODULE.C, "load_network", semantic_bomb)
    monkeypatch.setattr(MODULE.D, "descend", refuse)
    monkeypatch.setattr(
        sys,
        "argv",
        ["reconstruct_node.py", "region-lease:missing", "--fuzzy"],
    )

    assert MODULE.main() == 1
    result = json.loads(capsys.readouterr().out)
    assert result["kind"] == "atlas-object"
    assert result["residue"]["code"] == "NOT_FOUND"
    assert semantic_called is False


def test_atlas_object_descent_returns_complete_exact_bounded_content(
    monkeypatch,
) -> None:
    value = {
        "schema_version": "conceptric-object/1",
        "object_id": "seat:codex-seat",
        "kind": "logical-seat",
    }
    content = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    content_handle = "sha256:" + __import__("hashlib").sha256(content.encode()).hexdigest()
    monkeypatch.setattr(
        MODULE.D.atlas_bridge,
        "atlas_object",
        lambda **_kwargs: {
            "value": value,
            "content": content,
            "content_handle": content_handle,
            "media_type": "application/json",
            "provenance": {"store": "fixture"},
            "current_root": "sha256:" + "2" * 64,
            "current_root_components": {"schema_version": "atlas.atlas-object-current-root/1"},
            "authority_root": "sha256:" + "3" * 64,
            "authority_root_kind": "atlas.keyed-graph-object-proof/1",
            "drift_token": {"cursor": 7, "head_event_id": "event:7"},
            "current": True,
            "clean": True,
            "authenticated": False,
            "integrity_boundary": "CHECKSUMMED-CRUTCH",
            "authority_suffix_count": 0,
            "authority_suffix_limit": 64,
            "read_metrics": {
                "keyed_object_rows_loaded": 1,
                "global_history_replayed": False,
            },
            "fidelity_boundary": {"status": "CHECKSUMMED-CRUTCH"},
        },
    )

    result = MODULE.D.descend(
        kind="atlas-object",
        reference="seat:codex-seat",
        goal="dispatch exact seat",
        content_budget=4096,
        record_telemetry=False,
    )

    assert result["content_status"] == "COMPLETE"
    assert result["content"] == content
    assert result["content_handle"] == content_handle
    assert result["current_root"] == "sha256:" + "2" * 64
    assert result["integrity_boundary"] == "CHECKSUMMED-CRUTCH"
    assert result["authenticated"] is False
    assert result["current"] is True
    assert result["clean"] is True
    assert result["authority_suffix_count"] == 0
    assert result["authority_suffix_limit"] == 64
    assert result["goal"] == "dispatch exact seat"
    assert result["reconstruction_receipt"] == {
        "schema_version": "laplace.dispatch-reconstruction-claim/1",
        "kind": "atlas-object",
        "node": "seat:codex-seat",
        "goal_utf8": "dispatch exact seat",
        "content_status": "COMPLETE",
        "content_handle": content_handle,
        "read_only": True,
        "transition_claim": "none",
        "authority_write": "none",
        "current_root": "sha256:" + "2" * 64,
        "authority_root": "sha256:" + "3" * 64,
        "drift_token": {"cursor": 7, "head_event_id": "event:7"},
        "integrity_boundary": "CHECKSUMMED-CRUTCH",
    }
    encoded_receipt = json.dumps(
        result["reconstruction_receipt"],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    assert result["reconstruction_receipt_handle"] == (
        "sha256:" + __import__("hashlib").sha256(encoded_receipt).hexdigest()
    )
    assert result["read_only"] is True
    assert result["transition_claim"] == "none"
    assert result["authority_write"] == "none"


def test_mandatory_typed_cli_is_non_mutating_unless_telemetry_is_explicit(
    monkeypatch, capsys
) -> None:
    calls = []

    def descend(**kwargs):
        calls.append(kwargs)
        return {
            "schema_version": "laplace.typed-descent/1",
            "kind": kwargs["kind"],
            "reference": kwargs["reference"],
            "read_only": not kwargs["record_telemetry"],
        }

    monkeypatch.setattr(MODULE.D, "descend", descend)
    monkeypatch.setattr(sys, "argv", ["reconstruct_node.py", "HANDOFF.md"])
    assert MODULE.main() == 0
    assert calls[-1]["record_telemetry"] is False
    assert json.loads(capsys.readouterr().out)["read_only"] is True

    monkeypatch.setattr(
        sys,
        "argv",
        ["reconstruct_node.py", "HANDOFF.md", "--record-telemetry"],
    )
    assert MODULE.main() == 0
    assert calls[-1]["record_telemetry"] is True
    assert json.loads(capsys.readouterr().out)["read_only"] is False


def test_filename_like_miss_refuses_instead_of_fuzzy_routing() -> None:
    completed = subprocess.run(
        [
            "/usr/bin/python3",
            "scripts/reconstruct_node.py",
            "SYNTHESIS_2099-this-file-does-not-exist.md",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 1, completed.stderr
    result = json.loads(completed.stdout)
    assert result["kind"] == "repository-file"
    assert result["refused"] is True
    assert result["residue"]["code"] == "NOT_FOUND"
    assert "resolved_from" not in result


def test_human_name_fuzziness_is_explicit() -> None:
    net = {
        "nodes": {
            "src/laplace/render_manuscript.py": {
                "keywords": ["render", "manuscript"],
            }
        }
    }
    refused = MODULE.semantic_reconstruction(net, "render_manuscript", allow_fuzzy=False, grade=1)
    assert refused["resolution_mode"] == "exact-refusal"
    assert refused["did_you_mean"][0]["id"] == "src/laplace/render_manuscript.py"

    original = MODULE.C.reconstruct_node
    try:
        MODULE.C.reconstruct_node = lambda *_args, **_kwargs: {
            "id": "src/laplace/render_manuscript.py",
            "resolved_from": "render_manuscript",
        }
        resolved = MODULE.semantic_reconstruction(
            net, "render_manuscript", allow_fuzzy=True, grade=1
        )
    finally:
        MODULE.C.reconstruct_node = original
    assert resolved["resolution_mode"] == "explicit-fuzzy-human-name"


def test_ambiguous_human_name_returns_semantic_frame_then_exact_descents() -> None:
    net = {
        "nodes": {
            "src/laplace/seat_fabric.py": {"keywords": ["seat", "fabric"]},
            "docs/seat-fabric.md": {"keywords": ["seat", "fabric"]},
        }
    }
    original_reconstruct = MODULE.C.reconstruct_node
    original_fire = MODULE.C.fire_by_grade
    try:
        MODULE.C.reconstruct_node = lambda *_args, **_kwargs: {
            "error": "unknown node: seat fabric",
            "did_you_mean": [],
        }
        MODULE.C.fire_by_grade = lambda *_args, **_kwargs: {
            "router": "fixture-semantic",
            "geometry": {"beam": 2},
            "hits": [
                {
                    "recovered": "src/laplace/seat_fabric.py",
                    "score": 1.0,
                    "salience": 1.0,
                    "essence": "the canonical Fabric face",
                    "why": {"channel": "both"},
                    "path": [{"id": "mind://"}, {"id": "src/laplace/seat_fabric.py"}],
                },
                {
                    "recovered": "docs/seat-fabric.md",
                    "score": 0.9,
                    "salience": 0.9,
                    "essence": "design context",
                    "why": {"channel": "geometric"},
                    "path": [{"id": "mind://"}, {"id": "docs/seat-fabric.md"}],
                },
            ],
        }
        frame = MODULE.semantic_reconstruction(net, "seat fabric", allow_fuzzy=True, grade=1)
    finally:
        MODULE.C.reconstruct_node = original_reconstruct
        MODULE.C.fire_by_grade = original_fire

    assert frame["resolution_mode"] == "explicit-semantic-frame"
    assert frame["router"] == "fixture-semantic"
    assert [row["id"] for row in frame["candidates"]] == [
        "src/laplace/seat_fabric.py",
        "docs/seat-fabric.md",
    ]
    assert frame["selection"] is None
    assert frame["candidates"][0]["descend_exact"].endswith("src/laplace/seat_fabric.py")


def test_recovery_coordinate_exact_path_bypasses_stale_semantic_fold() -> None:
    completed = subprocess.run(
        [
            "/usr/bin/python3",
            "scripts/reconstruct_node.py",
            "atlas/packets/recovery/RECOVERY-COORDINATE-20260826.json",
            "--content-budget",
            "256",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["kind"] == "repository-file"
    assert result["reference"].endswith("RECOVERY-COORDINATE-20260826.json")
    assert result["provenance"]["resolution_mode"] == "exact-repository-file"
    assert result["content"].startswith("{\n")
    assert result["content_status"] == "TRUNCATED"
    assert "resolved_from" not in result


def test_mandatory_cli_entry_resolves_work_order_exactly() -> None:
    completed = subprocess.run(
        [
            "/usr/bin/python3",
            "scripts/reconstruct_node.py",
            "WO-20260825-wake-serve-contract",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["schema_version"] == "laplace.typed-descent/1"
    assert result["kind"] == "ledger-row"
    assert result["value"]["id"] == "WO-20260825-wake-serve-contract"
    assert result["provenance"]["path"] == "corpus_friction/work_orders.jsonl"


def test_campaign_stage_id_outranks_a_semantically_similar_filename() -> None:
    completed = subprocess.run(
        ["/usr/bin/python3", "scripts/reconstruct_node.py", "ATLAS-S2"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["kind"] == "campaign-stage"
    assert result["value"]["id"] == "ATLAS-S2"
    assert result["value"]["title"] == ("history migrated, every row adjudicated at its visit")
    assert result["provenance"]["path"] == "corpus_friction/campaign.jsonl"


def test_cli_refusal_keeps_blueprint_staleness_at_the_top_level(
    monkeypatch,
    capsys,
) -> None:
    moved = [{"path": "src/live.py", "expected": "old", "actual": "new"}]

    def refuse(**_kwargs):
        raise MODULE.D.DescentRefused(
            "blueprint generation is stale",
            generation_current=False,
            moved_source_roots=moved,
            moved_source_root_count=1,
        )

    monkeypatch.setattr(MODULE.D, "descend", refuse)
    monkeypatch.setattr(sys, "argv", ["reconstruct_node.py", "design-clause:abc"])
    assert MODULE.main() == 1
    result = json.loads(capsys.readouterr().out)
    assert result["refused"] is True and result["generation_current"] is False
    assert result["moved_source_roots"] == moved


def test_untyped_source_path_defaults_to_content_bearing_grade_one() -> None:
    completed = subprocess.run(
        [
            "/usr/bin/python3",
            "scripts/reconstruct_node.py",
            "src/laplace/engine/descent.py",
            "--content-budget",
            "96",
            "--width",
            "3",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["target_grade"] == 1
    assert result["handle"] == "src/laplace/engine/descent.py"
    assert result["content"].startswith('"""One typed read descent')
    assert result["content_status"] == "TRUNCATED"
    assert result["content_truncated"] is True
    assert result["content_omitted"] > 0
    assert result["content_next_offset"] > 0
    assert result["content_handle"].startswith("sha256:")


def test_unaffordable_source_descent_exits_budget_instead_of_success() -> None:
    completed = subprocess.run(
        [
            "/usr/bin/python3",
            "scripts/reconstruct_node.py",
            "src/laplace/engine/descent.py",
            "--content-budget",
            "0",
            "--width",
            "2",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 3, completed.stderr
    result = json.loads(completed.stdout)
    assert result["content_status"] == "BUDGET"
    assert result["content_residue"]["code"] == "BUDGET"
    assert result["content_handle"].startswith("sha256:")
