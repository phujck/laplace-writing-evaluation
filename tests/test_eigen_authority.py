from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from laplace.engine import eigen_authority as eigen

FIRST_TASK = "01a048e8-7c53-7430-95ee-5df7b2aaefcc"
FIRST_HOLDER = f"codex:{FIRST_TASK}"


def _run(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, text=True, capture_output=True
    ).stdout.strip()


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "contract").mkdir(parents=True)
    source = Path("contract/eigen_standing_authority.json")
    shutil.copy2(source, root / source)
    _run(root, "init")
    _run(root, "config", "user.email", "eigen@example.invalid")
    _run(root, "config", "user.name", "Eigen test")
    _run(root, "add", source.as_posix())
    _run(root, "commit", "-m", "bank standing law")
    return root


def _transcript(tmp_path: Path, text: str = "Gerard says triage the system") -> Path:
    path = tmp_path / ("rollout-" + str(abs(hash(text))) + ".jsonl")
    rows = [
        {"role": "user", "text": text},
        {"role": "assistant", "text": "I will inventory first and clear no bytes."},
        {"type": "tool", "payload": "raw tool bytes stay inert"},
        {"type": "fabric", "body": "optional transport chatter stays inert"},
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def _adopt(repo: Path, tmp_path: Path) -> dict:
    return eigen.adopt(
        repo,
        holder_ref=FIRST_HOLDER,
        task_id=FIRST_TASK,
        transcript_path=_transcript(tmp_path),
    )


def test_first_adoption_seals_exact_transcript_and_is_idempotent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = _repo(tmp_path)
    monkeypatch.setenv("LAPLACE_EIGEN_STATE", str(tmp_path / "state"))
    transcript = _transcript(tmp_path)

    first = eigen.adopt(
        repo, holder_ref=FIRST_HOLDER, task_id=FIRST_TASK, transcript_path=transcript
    )
    repeated = eigen.adopt(
        repo, holder_ref=FIRST_HOLDER, task_id=FIRST_TASK, transcript_path=transcript
    )

    assert first["status"] == "ADOPTED"
    assert repeated["deduplicated"] is True
    assert repeated["record_handle"] == first["record_handle"]
    assert first["first_goal"] == "TRIAGE-ONLY"
    assert first["transcript"]["content_handle"].startswith("sha256:")
    assert Path(first["transcript"]["custody_path"]).read_bytes() == transcript.read_bytes()
    authority = eigen.observe_authority(repo, holder_ref=FIRST_HOLDER)
    assert authority["status"] == "AUTHORIZED"
    assert authority["compaction_seal_handle"] == first["compaction_seal_handle"]
    assert authority["profile_handle"] == first["profile_handle"]
    assert authority["fabric_required"] is False
    assert len(eigen.read_journal()["rows"]) == 1


def test_authority_localizes_broken_subsystems_and_guards_irreversible_acts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = _repo(tmp_path)
    monkeypatch.setenv("LAPLACE_EIGEN_STATE", str(tmp_path / "state"))
    _adopt(repo, tmp_path)
    telemetry = {
        "watcher": "STALE",
        "recovery": "SUPERSESSION-REQUIRED",
        "lease": "MISSING",
        "atlas": "UNAVAILABLE",
        "fabric": "UNAVAILABLE",
    }

    authority = eigen.observe_authority(repo, holder_ref=FIRST_HOLDER, telemetry=telemetry)
    assert authority["status"] == "AUTHORIZED"
    assert authority["telemetry"] == telemetry
    assert eigen.check_operation(
        repo, holder_ref=FIRST_HOLDER, operation="repair-atlas-reader"
    )["allowed"] is True
    for operation in ("remote-push", "publication", "deletion", "destructive-history-rewrite"):
        decision = eigen.check_operation(repo, holder_ref=FIRST_HOLDER, operation=operation)
        assert decision["status"] == "REFUSED"
        assert decision["allowed"] is False
    assert eigen.observe_authority(repo, holder_ref="codex:not-eigen")["status"] == "REFUSED"


def test_provider_neutral_successor_replaces_predecessor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = _repo(tmp_path)
    monkeypatch.setenv("LAPLACE_EIGEN_STATE", str(tmp_path / "state"))
    _adopt(repo, tmp_path)
    source = eigen.load_law(repo)
    successor = "claude:session-successor"
    commission = {
        "schema_version": eigen.COMMISSION_SCHEMA,
        "status": "ACTIVE",
        "action": "REPLACE",
        "author": "Gerard",
        "seat_id": "eigen-seat",
        "function": "eigen",
        "holder_ref": successor,
        "replaces_holder_ref": FIRST_HOLDER,
        "source_law_handle": source["source_law_handle"],
        "reason": "direct successor commission for the permanent Eigen role",
    }
    commission_path = tmp_path / "commission.json"
    commission_path.write_text(json.dumps(commission), encoding="utf-8")

    adopted = eigen.adopt(
        repo,
        holder_ref=successor,
        task_id="session-successor",
        transcript_path=_transcript(tmp_path, "successor triage only"),
        commission_path=commission_path,
    )

    assert adopted["status"] == "ADOPTED"
    assert eigen.observe_authority(repo, holder_ref=successor)["status"] == "AUTHORIZED"
    assert eigen.observe_authority(repo, holder_ref=FIRST_HOLDER)["status"] == "REFUSED"


def test_emergency_journal_reconciles_exactly_and_atlas_failure_is_deferred(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = _repo(tmp_path)
    monkeypatch.setenv("LAPLACE_EIGEN_STATE", str(tmp_path / "state"))
    _adopt(repo, tmp_path)
    eigen.bank(
        repo,
        kind="repair-act",
        act_id="repair:one",
        holder_ref=FIRST_HOLDER,
        reason="bounded local repair",
        payload={"path": "src/laplace/example.py", "authority_effect": "local"},
    )
    deferred = eigen.reconcile(
        repo,
        holder_ref=FIRST_HOLDER,
        mirror=lambda _row: (_ for _ in ()).throw(OSError("Atlas unreadable")),
    )
    assert deferred["status"] == "DEFERRED"
    assert deferred["authority_status"] == "AUTHORIZED"

    seen: list[str] = []

    def mirror(row: dict) -> dict:
        seen.append(row["record_handle"])
        return {"status": "MIRRORED", "event_id": "sha256:" + "a" * 64}

    done = eigen.reconcile(repo, holder_ref=FIRST_HOLDER, mirror=mirror)
    assert done["status"] == "RECONCILED"
    assert done["unreconciled"] == 0
    assert len(seen) == 2
    repeated = eigen.reconcile(repo, holder_ref=FIRST_HOLDER, mirror=mirror)
    assert repeated["mirrored"] == []
    assert len(seen) == 2


def test_bounded_storage_triage_never_descends_large_roots(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "many"
    root.mkdir()
    for index in range(2_000):
        path = root / f"object-{index}"
        with path.open("wb") as stream:
            stream.truncate(32 * 1024 * 1024)
    monkeypatch.setenv("LAPLACE_STATE", str(tmp_path / "state"))
    monkeypatch.setattr(os, "walk", lambda *_a, **_k: (_ for _ in ()).throw(
        AssertionError("bounded triage descended the tree")
    ))

    face = eigen._storage_face(root)

    assert face["scan_law"].startswith("root/manifest first")
    assert face["roots"][0]["budget"] == {
        "directory_entries_read": 0, "content_bytes_read": 0,
    }
    assert face["roots"][0]["tree_bytes"] is None


def test_git_law_missing_or_dirty_refuses(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / eigen.LAW_PATH).write_text("{}", encoding="utf-8")
    result = eigen.observe_authority(repo, holder_ref=FIRST_HOLDER)
    assert result["status"] == "REFUSED"
    assert "dirty or differs" in result["reason"]


def test_wake_surfaces_authority_when_every_optional_subsystem_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from laplace.engine import compaction_submergence, self_corpus, turn_reconstruction, wake
    from laplace.representation import embedding_health
    from laplace.web import scanner

    repo = _repo(tmp_path)
    monkeypatch.setenv("LAPLACE_EIGEN_STATE", str(tmp_path / "state"))
    monkeypatch.setenv("CODEX_THREAD_ID", FIRST_TASK)
    _adopt(repo, tmp_path)

    def broken(*_args, **_kwargs):
        raise RuntimeError("localized dependency failure")

    monkeypatch.setattr(embedding_health, "read_health", broken)
    monkeypatch.setattr(turn_reconstruction, "reconstruct_turn", broken)
    monkeypatch.setattr(compaction_submergence, "wake_preflight_from_environment", broken)
    monkeypatch.setattr(wake, "seat_fabric_glow", broken)
    monkeypatch.setattr(wake, "recovery_coordinate_glow", broken)
    monkeypatch.setattr(wake, "development_work_map_glow", broken)
    monkeypatch.setattr(wake, "_semantic_block", broken)
    monkeypatch.setattr(scanner, "probe", broken)
    monkeypatch.setattr(self_corpus, "reconstruct_self", broken)

    payload = wake.wake_payload(repo, grade=0)

    assert next(iter(payload)) == "eigen_authority"
    assert payload["eigen_authority"]["status"] == "AUTHORIZED"
    assert payload["seat_fabric"]["status"] == "UNKNOWN"
    assert payload["recovery_coordinate"]["status"] == "UNKNOWN"
    assert payload["turn_reconstruction"]["status"] == "UNKNOWN"


def test_startup_is_mail_ready_without_fabric_watcher_recovery_or_atlas(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from laplace.engine import startup_mail_gate

    repo = _repo(tmp_path)
    monkeypatch.setenv("LAPLACE_EIGEN_STATE", str(tmp_path / "state"))
    _adopt(repo, tmp_path)
    monkeypatch.setattr(
        startup_mail_gate,
        "wake_payload",
        lambda *_args, **_kwargs: (2, None, "Fabric, watcher, recovery and Atlas unavailable"),
    )

    result = startup_mail_gate.run_gate(
        repo,
        "eigen-seat",
        "triage only",
        holder_ref=FIRST_HOLDER,
        function="eigen",
        record_join=True,
    )

    assert result["state"] == "MAIL_READY"
    assert result["eigen_authority"]["status"] == "AUTHORIZED"
    assert result["join"] == "NOT-REQUIRED-STANDING-ROLE"
    assert result["mail"] == {"status": "OPTIONAL", "obligations": 0, "delivery_claim": False}


def test_design_reconciliation_orders_live_map_defect_before_cleanup(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    result = eigen._design_reconciliation(
        repo,
        authority={"status": "AUTHORIZED", "profile_handle": "sha256:p", "compaction_seal_handle": "sha256:s"},
        atlas={"status": "CURRENT", "checkpoint": "sha256:c", "active_leases": []},
        semantic={"status": "CURRENT", "artifact_root": "sha256:a", "side_refs": {}},
        fabric={"projection": {"status": "UNAVAILABLE"}},
        product_refusals=[{"id": "UI-PRODUCT-REFUSED-20260828"}],
    )

    assert [row["order"] for row in result["ordered_organs"]] == list(range(1, 8))
    live_map = result["ordered_organs"][2]
    assert live_map["verdict"] == "CONTRADICTED"
    assert "causal join" in live_map["replacement_or_reopening_predicate"]
    assert result["mutations"] == []
