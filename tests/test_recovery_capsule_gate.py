from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from laplace.representation import atlas_bridge
from laplace.representation import recovery_capsule_gate as recovery_gate
from laplace.representation.recovery_capsule_gate import CAPSULE_HANDLE, CORRECT_BLUEPRINT_MESSAGE, CORRECTION_MESSAGE, DESIGN_WRONG_HANDLE, HISTORICAL_LEASES, MALFORMED_MESSAGE_ROOT, MESSAGE_CONTRACT, PROJECTION_PATH, SCREENSHOT_HANDLES, RecoveryCapsuleRefusal, SnapshotEvidence, _verify_preservation_files, _verify_projection, _verify_repository, _verify_snapshot_contract, rehearse_bit_flip_recovery

ROOT = Path(__file__).resolve().parents[1]
PREPARATORY_MESSAGE = "message:14b560ca5bb3d82c704c321c7324c2ab6bb51aef42d19dc8e3ec13142bb438d6"


def _projection() -> dict:
    return json.loads((ROOT / PROJECTION_PATH).read_text(encoding="utf-8"))


def _snapshot_evidence(projection: dict) -> SnapshotEvidence:
    messages = {}
    present = set(SCREENSHOT_HANDLES)
    for message_id, contract in MESSAGE_CONTRACT.items():
        body_handle = str(contract["body_handle"])
        present.add(body_handle)
        messages[message_id] = {
            "missing": False,
            "body_handle": body_handle,
            "status": contract["status"],
            "reconstruction_handle": contract["reconstruction_handle"],
            "acknowledgement_event_id": contract["acknowledgement_event_id"],
            "dependency_roots": {},
            "proof_event_ids": ["sha256:proof"],
            "proof_valid": True,
        }
    messages[CORRECTION_MESSAGE]["dependency_roots"] = {
        "malformed_root": MALFORMED_MESSAGE_ROOT,
        "correct_root": CORRECT_BLUEPRINT_MESSAGE,
    }
    messages[PREPARATORY_MESSAGE]["dependency_roots"] = {
        "declared_blueprint_amendment": MALFORMED_MESSAGE_ROOT,
        "candidate_blueprint_amendment": CORRECT_BLUEPRINT_MESSAGE,
        "interface_merge": DESIGN_WRONG_HANDLE,
    }
    leases = {
        lease_id: {
            "holder_ref": expected["holder_ref"],
            "checkout_event_id": expected["checkout_event_id"],
        }
        for lease_id, expected in HISTORICAL_LEASES.items()
    }
    nonterminal = tuple(
        sorted(
            (row["message_id"], row["status"])
            for row in projection["expected_snapshot_nonterminal_messages"]
        )
    )
    return SnapshotEvidence(
        receipt=dict(projection["runtime_custody"]),
        messages=messages,
        leases=leases,
        nonterminal_messages=nonterminal,
        present_blob_handles=frozenset(present),
        snapshot_unchanged=True,
    )


def test_repository_capsule_tail_and_role_projection_are_exact() -> None:
    repository = _verify_repository(ROOT)
    preservation = _verify_preservation_files(ROOT)
    projection, role_receipts = _verify_projection(ROOT)

    assert repository["sensorium_commit"].startswith("79d0ad5c")
    assert preservation["capsule_handle"] == CAPSULE_HANDLE
    assert preservation["tail_row_count"] == 48
    assert projection["sensorium_candidate"]["accepted"] is False
    assert set(role_receipts) == {"ego", "sensorium", "superego"}
    assert len(set(role_receipts.values())) == 3


def test_snapshot_contract_accepts_exact_preservation_and_terminal_refusal() -> None:
    projection = _projection()
    receipt = _verify_snapshot_contract(_snapshot_evidence(projection), projection)

    assert receipt["capsule_message_count"] == 10
    assert receipt["snapshot_unchanged"] is True
    assert receipt["projection_relation"] == "exact-generation"
    assert set(receipt["screenshot_handles"]) == set(SCREENSHOT_HANDLES)


def _append_only_evidence(*, appended_kinds: tuple[str, ...]) -> tuple[dict, SnapshotEvidence]:
    projection = _projection()
    evidence = _snapshot_evidence(projection)
    baseline = projection["runtime_custody"]
    count = int(baseline["event_count"])
    actual_count = count + len(appended_kinds)
    event_ids = ["sha256:historical"] * actual_count
    record_digests = ["sha256:historical-record"] * actual_count
    event_kinds = ["historical"] * count + list(appended_kinds)
    event_ids[count - 1] = baseline["head_event_id"]
    record_digests[count - 1] = baseline["head_record_digest"]
    actual_receipt = {
        **evidence.receipt,
        "snapshot_id": "sha256:" + "e" * 64,
        "event_count": actual_count,
        "head_event_id": "sha256:" + "f" * 64,
        "head_record_digest": "sha256:" + "a" * 64,
    }
    return projection, replace(
        evidence,
        receipt=actual_receipt,
        event_ids=tuple(event_ids),
        event_record_digests=tuple(record_digests),
        event_kinds=tuple(event_kinds),
    )


def test_snapshot_contract_accepts_reconstruction_only_append_after_exact_anchor() -> None:
    projection, evidence = _append_only_evidence(
        appended_kinds=("reconstruction.moved", "reconstruction.materialized")
    )

    receipt = _verify_snapshot_contract(evidence, projection)

    assert receipt["projection_relation"] == "append-only-reconstruction-extension"
    assert receipt["projection_baseline"] == projection["runtime_custody"]


def test_snapshot_contract_refuses_lifecycle_event_after_projection() -> None:
    projection, evidence = _append_only_evidence(appended_kinds=("seat.joined",))

    with pytest.raises(RecoveryCapsuleRefusal) as caught:
        _verify_snapshot_contract(evidence, projection)

    assert caught.value.code == "RUNTIME_CUSTODY_POST_PROJECTION_EVENT_REFUSED"


def test_snapshot_contract_refuses_requeued_compensation() -> None:
    projection = _projection()
    evidence = _snapshot_evidence(projection)
    messages = {key: dict(value) for key, value in evidence.messages.items()}
    commission = "message:58f006fd96d2e72f21aa892c4135df868f23cc7142fb493ed572ca9e511a9ba2"
    messages[commission]["status"] = "queued"
    changed = SnapshotEvidence(
        receipt=evidence.receipt,
        messages=messages,
        leases=evidence.leases,
        nonterminal_messages=evidence.nonterminal_messages,
        present_blob_handles=evidence.present_blob_handles,
        snapshot_unchanged=True,
    )

    with pytest.raises(RecoveryCapsuleRefusal) as caught:
        _verify_snapshot_contract(changed, projection)

    assert caught.value.code == "CAPSULE_MESSAGE_STATE_MISMATCH"


def test_snapshot_contract_refuses_unexpected_nonterminal_message() -> None:
    projection = _projection()
    evidence = _snapshot_evidence(projection)
    changed = SnapshotEvidence(
        receipt=evidence.receipt,
        messages=evidence.messages,
        leases=evidence.leases,
        nonterminal_messages=(*evidence.nonterminal_messages, ("message:unexpected", "queued")),
        present_blob_handles=evidence.present_blob_handles,
        snapshot_unchanged=True,
    )

    with pytest.raises(RecoveryCapsuleRefusal) as caught:
        _verify_snapshot_contract(changed, projection)

    assert caught.value.code == "UNEXPECTED_NONTERMINAL_MESSAGE"


def test_projection_refuses_silent_sensorium_acceptance(tmp_path: Path) -> None:
    projection = _projection()
    projection["sensorium_candidate"]["accepted"] = True
    target = tmp_path / PROJECTION_PATH
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(projection), encoding="utf-8")

    with pytest.raises(RecoveryCapsuleRefusal) as caught:
        _verify_projection(tmp_path)

    assert caught.value.code == "SENSORIUM_CANDIDATE_SILENTLY_ACCEPTED"


def _bit_flip_fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    source = tmp_path / "source"
    independent = tmp_path / "independent"
    body_handle = str(
        MESSAGE_CONTRACT[
            "message:a4c130422e74d0e6caf0e162d8814bf9de66d447a238110185a8c6c6ce2f2f94"
        ]["body_handle"]
    ).removeprefix("sha256:")
    body_relative = Path("blobs") / body_handle[:2] / body_handle
    hive_relative = Path("hives/events/aa/fixture.zlib")
    for root in (source, independent):
        (root / body_relative).parent.mkdir(parents=True)
        (root / body_relative).write_bytes(b"message-body")
        (root / hive_relative).parent.mkdir(parents=True)
        (root / hive_relative).write_bytes(b"event-hive")
    return source, independent, body_relative, hive_relative


def test_bit_flip_rehearsal_refuses_same_filesystem_custody(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, independent, _body, _hive = _bit_flip_fixture(tmp_path)
    monkeypatch.setattr(recovery_gate, "_filesystem_device", lambda _path: 17)

    with pytest.raises(RecoveryCapsuleRefusal) as caught:
        rehearse_bit_flip_recovery(
            snapshot_root=source,
            independent_custody_root=independent,
        )

    assert caught.value.code == "INDEPENDENT_CUSTODY_SAME_FILESYSTEM"


def test_bit_flip_rehearsal_reverifies_both_unchanged_identities(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, independent, body_relative, hive_relative = _bit_flip_fixture(tmp_path)
    snapshot_id = "sha256:" + ("d" * 64)
    calls: list[Path] = []

    monkeypatch.setattr(
        recovery_gate,
        "_filesystem_device",
        lambda path: 17 if Path(path).name == "source" else 23,
    )
    monkeypatch.setattr(recovery_gate, "_first_hive_relative_path", lambda _root: hive_relative)

    def verify(root: Path) -> dict[str, str]:
        resolved = Path(root).resolve()
        calls.append(resolved)
        if (resolved / body_relative).read_bytes() != b"message-body":
            raise RuntimeError("message blob hash mismatch")
        if (resolved / hive_relative).read_bytes() != b"event-hive":
            raise RuntimeError("event hive hash mismatch")
        return {"snapshot_id": snapshot_id}

    monkeypatch.setattr(atlas_bridge, "verify_runtime_custody", verify)

    receipt = rehearse_bit_flip_recovery(
        snapshot_root=source,
        independent_custody_root=independent,
    )

    assert receipt["state"] == "BIT_FLIP_RECOVERY_READY"
    assert receipt["source_filesystem_device"] == 17
    assert receipt["independent_filesystem_device"] == 23
    assert receipt["final_source_snapshot_id"] == snapshot_id
    assert receipt["final_independent_snapshot_id"] == snapshot_id
    assert calls.count(source.resolve()) == 2
    assert calls.count(independent.resolve()) == 2


def test_bit_flip_rehearsal_refuses_final_source_identity_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, independent, body_relative, hive_relative = _bit_flip_fixture(tmp_path)
    snapshot_id = "sha256:" + ("d" * 64)
    source_verifications = 0

    monkeypatch.setattr(
        recovery_gate,
        "_filesystem_device",
        lambda path: 17 if Path(path).name == "source" else 23,
    )
    monkeypatch.setattr(recovery_gate, "_first_hive_relative_path", lambda _root: hive_relative)

    def verify(root: Path) -> dict[str, str]:
        nonlocal source_verifications
        resolved = Path(root).resolve()
        if (resolved / body_relative).read_bytes() != b"message-body":
            raise RuntimeError("message blob hash mismatch")
        if (resolved / hive_relative).read_bytes() != b"event-hive":
            raise RuntimeError("event hive hash mismatch")
        if resolved == source.resolve():
            source_verifications += 1
            if source_verifications == 2:
                return {"snapshot_id": "sha256:" + ("e" * 64)}
        return {"snapshot_id": snapshot_id}

    monkeypatch.setattr(atlas_bridge, "verify_runtime_custody", verify)

    with pytest.raises(RecoveryCapsuleRefusal) as caught:
        rehearse_bit_flip_recovery(
            snapshot_root=source,
            independent_custody_root=independent,
        )

    assert caught.value.code == "SOURCE_CUSTODY_IDENTITY_MOVED"
