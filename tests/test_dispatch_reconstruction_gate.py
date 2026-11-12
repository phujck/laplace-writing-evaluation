from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from laplace.pipeline import dispatch

NODE = "atlas-object:work-order"
GOAL = "compile exact work"
CURRENT_ROOT = "sha256:" + "a" * 64
AUTHORITY_ROOT = "sha256:" + "d" * 64
DRIFT = {"cursor": 3127, "head": "sha256:" + "b" * 64}


@pytest.fixture(autouse=True)
def _exact_turn_reconstruction(monkeypatch: pytest.MonkeyPatch) -> None:
    from laplace.engine import turn_reconstruction

    continuation = {
        "schema_version": "laplace.continuation-admission/1",
        "status": "ADMITTED",
        "substantive_work_allowed": True,
        "decision_handle": "sha256:" + "a" * 64,
    }
    monkeypatch.setattr(
        turn_reconstruction,
        "reconstruct_turn",
        lambda *_args, **_kwargs: {
            "schema_version": "laplace.turn-reconstruction/1",
            "status": "ADMITTED",
            "profile_handle": "sha256:" + "e" * 64,
            "semantic_fold_health_handle": "sha256:" + "c" * 64,
            "claims_with_unknown_context": False,
            "selected": [{
                "kind": "atlas-custody",
                "reference": "sha256:" + "e" * 64,
                "content_status": "COMPLETE",
            }],
            "continuation_decision": continuation,
            "receipt_handle": "sha256:" + "f" * 64,
        },
    )


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _reconstruction() -> dict[str, Any]:
    content = "the exact reconstructed object\n"
    proof: dict[str, Any] = {
        "schema_version": "laplace.typed-descent/1",
        "kind": "atlas-object",
        "reference": NODE,
        "goal": GOAL,
        "content_status": "COMPLETE",
        "content": content,
        "content_handle": _sha256(content.encode()),
        "read_only": True,
        "transition_claim": "none",
        "authority_write": "none",
        "current_root": CURRENT_ROOT,
        "authority_root": AUTHORITY_ROOT,
        "drift_token": DRIFT,
        "integrity_boundary": "CHECKSUMMED-CRUTCH",
    }
    claim = dispatch._reconstruction_claim(proof, node=NODE, goal=GOAL)
    proof["reconstruction_receipt"] = claim
    proof["reconstruction_receipt_handle"] = _sha256(_canonical(claim))
    return proof


def _current_jit(**_kwargs: Any) -> dict[str, Any]:
    return {
        "status": "CURRENT",
        "current_root": CURRENT_ROOT,
        "authority_root": AUTHORITY_ROOT,
        "drift_token": DRIFT,
        "suffix_events": 64,
        "dirty": False,
        "ambiguous": False,
        "moved": False,
        "read_only": True,
        "transition_claim": "none",
        "authority_write": "none",
    }


def _reason(result: dict[str, Any]) -> str:
    return result["reconstruction_admission"]["admission_result"]["reason"]


def test_missing_reconstruction_refuses_before_jit_core_fence_or_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        dispatch,
        "_jit_dispatch_authority",
        lambda *_args, **_kwargs: calls.append("jit"),
    )
    monkeypatch.setattr(
        dispatch,
        "_compile_dispatch_core",
        lambda *_args, **_kwargs: calls.append("core"),
    )
    monkeypatch.setattr(
        dispatch,
        "_fence_advisory",
        lambda *_args, **_kwargs: calls.append("fence"),
    )

    got = dispatch.compile_dispatch(NODE, GOAL, worker="derive")

    assert _reason(got) == "MISSING_RECONSTRUCTION"
    assert calls == []
    assert got["reconstruction_admission"]["d2"]["status"] == "OPEN"


@pytest.mark.parametrize(
    ("alter", "reason"),
    [
        (lambda p: p.update(reference="other"), "NODE_MISMATCH"),
        (lambda p: p.update(goal="other"), "GOAL_MISMATCH"),
        (lambda p: p.update(kind="repository-file"), "KIND_MISMATCH"),
        (lambda p: p.update(content_status="BUDGET"), "RECONSTRUCTION_BUDGET"),
        (lambda p: p.update(content_status="TRUNCATED"), "RECONSTRUCTION_TRUNCATED"),
        (lambda p: p.update(content_status="REFUSED"), "RECONSTRUCTION_REFUSED"),
        (lambda p: p.update(content="altered"), "CONTENT_HANDLE_MISMATCH"),
        (lambda p: p.update(read_only=False), "READ_AUTHORITY_MISMATCH"),
        (lambda p: p.update(transition_claim="delivery"), "READ_AUTHORITY_MISMATCH"),
        (lambda p: p.update(authority_write="telemetry"), "READ_AUTHORITY_MISMATCH"),
        (lambda p: p.update(current_root="not-a-root"), "MALFORMED_AUTHORITY_PROOF"),
        (
            lambda p: p.update(integrity_boundary="AUTHENTICATED"),
            "INTEGRITY_BOUNDARY_MISMATCH",
        ),
        (
            lambda p: p.update(reconstruction_receipt_handle="sha256:" + "0" * 64),
            "RECEIPT_HANDLE_MISMATCH",
        ),
    ],
)
def test_reconstruction_faults_refuse_without_invoking_core(
    monkeypatch: pytest.MonkeyPatch,
    alter: Any,
    reason: str,
) -> None:
    proof = _reconstruction()
    alter(proof)
    core_calls: list[bool] = []
    monkeypatch.setattr(dispatch, "_jit_dispatch_authority", _current_jit)
    monkeypatch.setattr(
        dispatch,
        "_compile_dispatch_core",
        lambda *_args, **_kwargs: core_calls.append(True),
    )

    got = dispatch.compile_dispatch(NODE, GOAL, worker="derive", reconstruction=proof)

    assert _reason(got) == reason
    assert core_calls == []


@pytest.mark.parametrize(
    ("jit_change", "reason"),
    [
        ({"status": "NO-CHECKPOINT"}, "CHECKPOINT_UNAVAILABLE"),
        ({"suffix_events": 65}, "SUFFIX_LIMIT_EXCEEDED"),
        ({"dirty": True}, "AUTHORITY_DIRTY"),
        ({"ambiguous": True}, "AUTHORITY_AMBIGUOUS"),
        ({"moved": True}, "AUTHORITY_MOVED"),
        ({"current_root": "sha256:" + "c" * 64}, "CURRENT_ROOT_MISMATCH"),
        ({"authority_root": "sha256:" + "c" * 64}, "AUTHORITY_ROOT_MISMATCH"),
        ({"read_only": False}, "JIT_READ_AUTHORITY_MISMATCH"),
        ({"drift_token": {"cursor": 3128}}, "DRIFT_TOKEN_MISMATCH"),
    ],
)
def test_jit_authority_faults_refuse_before_core(
    monkeypatch: pytest.MonkeyPatch,
    jit_change: dict[str, Any],
    reason: str,
) -> None:
    jit = _current_jit()
    jit.update(jit_change)
    core_calls: list[bool] = []
    monkeypatch.setattr(dispatch, "_jit_dispatch_authority", lambda *_a, **_k: jit)
    monkeypatch.setattr(
        dispatch,
        "_compile_dispatch_core",
        lambda *_args, **_kwargs: core_calls.append(True),
    )

    got = dispatch.compile_dispatch(
        NODE, GOAL, worker="derive", reconstruction=_reconstruction()
    )

    assert _reason(got) == reason
    assert core_calls == []


def test_exact_admission_enters_core_once_and_phase_receipt_recomputes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    order: list[str] = []

    def jit(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        order.append("jit")
        assert _kwargs["expected_current_root"] == CURRENT_ROOT
        return _current_jit()

    def core(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        order.append("core")
        return {"error": "core-marker"}

    monkeypatch.setattr(dispatch, "_jit_dispatch_authority", jit)
    monkeypatch.setattr(dispatch, "_compile_dispatch_core", core)
    monkeypatch.setattr(
        dispatch,
        "_fence_advisory",
        lambda *_args, **_kwargs: pytest.fail("fence must not run after a core error"),
    )

    got = dispatch.compile_dispatch(
        NODE,
        GOAL,
        worker="derive",
        repo_root=tmp_path,
        reconstruction=_reconstruction(),
    )

    assert order == ["jit", "core"]
    phase = got["reconstruction_admission"]
    assert phase["admission_result"] == {"status": "ADMITTED", "reason": "EXACT"}
    assert phase["current_root"] == CURRENT_ROOT
    assert phase["authority_root"] == AUTHORITY_ROOT
    handle = phase.pop("receipt_handle")
    assert handle == _sha256(_canonical(phase))
    assert bytes.fromhex(phase["goal_bytes_hex"]).decode() == GOAL
    assert phase["d2"]["status"] == "OPEN"


@pytest.mark.parametrize("fault", ("unknown", "fog", "target", "fold"))
def test_turn_context_fault_refuses_before_final_jit_or_core(
    monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    from laplace.engine import turn_reconstruction

    turn = {
        "schema_version": "laplace.turn-reconstruction/1",
        "status": "ADMITTED",
        "profile_handle": "sha256:" + "e" * 64,
        "semantic_fold_health_handle": "sha256:" + "c" * 64,
        "claims_with_unknown_context": False,
        "selected": [{
            "kind": "atlas-custody", "reference": "sha256:" + "e" * 64,
            "content_status": "COMPLETE"
        }],
        "continuation_decision": {
            "schema_version": "laplace.continuation-admission/1",
            "status": "ADMITTED",
            "substantive_work_allowed": True,
            "decision_handle": "sha256:" + "a" * 64,
        },
    }
    if fault == "unknown":
        turn["status"] = "UNKNOWN"
    elif fault == "fog":
        turn["claims_with_unknown_context"] = True
    elif fault == "target":
        turn["selected"] = []
    else:
        turn["semantic_fold_health_handle"] = None
    monkeypatch.setattr(turn_reconstruction, "reconstruct_turn", lambda *_a, **_k: turn)
    calls: list[str] = []
    monkeypatch.setattr(dispatch, "_jit_dispatch_authority", lambda *_a, **_k: calls.append("jit"))
    monkeypatch.setattr(dispatch, "_compile_dispatch_core", lambda *_a, **_k: calls.append("core"))

    got = dispatch.compile_dispatch(
        NODE, GOAL, worker="derive", reconstruction=_reconstruction()
    )

    assert "turn reconstruction refused" in got["error"]
    assert calls == []
