"""D1 (wave J1-join): the status path resolves a Claude-wave run instead of refusing.

A Claude wave is carried by the harness, not by codex_execute/create_run: its run
directory under evidence/WORKFLOWS/<run_id>/ never gets a run.json manifest, only the
rows scripts/distil.py wave-rows banks into contract/dispatches.jsonl. Before this
packet, W.inspect_run (and so `scripts/workflow.py status`) answered such a run with
REFUSED FileNotFoundError run.json - measured 2026-09-21 on
WORKFLOW-20260921T192651Z-e873e9b054be. These tests build that exact shape by hand
(no engine-carried run.json, only ledger rows and a deposited result file) and check
the fallback reports FROM THE ROW: it re-hashes the file, never invents a manifest,
and never reports the run as verified beyond what it re-hashed.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from laplace.pipeline import workflow as W

RUN_ID = "WORKFLOW-20260921T192651Z-e873e9b054be"


def _sha(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _wave_workspace(tmp_path):
    root = tmp_path / "repo"
    (root / "evidence" / "WORKFLOWS" / RUN_ID).mkdir(parents=True)
    (root / "contract").mkdir()
    run_dir = root / "evidence" / "WORKFLOWS" / RUN_ID
    return root, run_dir


def _deposit_result(run_dir: Path, payload: dict) -> tuple[str, str]:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    result_path = run_dir / "returns.json"
    result_path.write_bytes(raw)
    relative = f"evidence/WORKFLOWS/{RUN_ID}/returns.json"
    return relative, _sha(raw)


def _bank_workflow_row(root: Path, **fields) -> None:
    row = {"record": "workflow", "id": RUN_ID, "phase": "result",
           "status": "COMPLETED", "accepted": True,
           "packets_accepted": ["D1"], "packets_not_accepted": [],
           "dispatch_ids": [f"{RUN_ID}:build:d1"], "judged_verdict_ids": ["JV-20260921-j1-join-d1"],
           "wave": "j1-join", "ts": "2026-09-21T19:26:51Z"}
    row.update(fields)
    with (root / W.LEDGER).open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def test_no_run_json_resolves_from_the_ledgers_last_workflow_row(tmp_path):
    root, run_dir = _wave_workspace(tmp_path)
    relative, handle = _deposit_result(run_dir, {"returns": ["fixture packet return"]})
    _bank_workflow_row(root, result_path=relative, result_handle=handle)

    result = W.inspect_run(run_dir)

    assert result["manifest"] == "ABSENT"
    assert result["status"] == "RECORDED-COMPLETED"
    assert result["accepted"] is True
    assert result["result_ref"] == {"path": relative, "handle": handle}
    assert result["packets_accepted"] == ["D1"]
    assert result["packets_not_accepted"] == []
    assert result["dispatch_row_ids"] == [f"{RUN_ID}:build:d1"]
    assert result["judged_verdict_row_ids"] == ["JV-20260921-j1-join-d1"]
    # Never invents a manifest, never verifies a stage it never read.
    assert "stages" not in result


def test_engine_carried_run_with_a_real_manifest_is_unchanged(tmp_path, monkeypatch):
    import subprocess

    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / "node.py").write_text("VALUE = 1\n")
    subprocess.run(["git", "add", "node.py"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                    "commit", "-qm", "fixture"], cwd=root, check=True)
    monkeypatch.delenv("LAPLACE_CUSTODY_LIVE", raising=False)
    spec = W._load(Path(__file__).resolve().parents[1] / "profiles/workflows/build-review-synthesize.json")
    directory = W.create_run(root, spec, node="node.py", goal="change VALUE to 2",
                             model="fixture-provider-model", effort="high", state=tmp_path / "state",
                             write_paths=["node.py"])

    assert (directory / "run.json").is_file()
    result = W.inspect_run(directory)

    # The engine-carried path never falls into the ledger branch: PENDING (no stage receipts
    # yet), a real per-stage status list, and no ledger-only fields.
    assert result["status"] == "PENDING"
    assert result["stages"]
    assert "manifest" not in result
    assert "result_ref" not in result


def test_ledger_row_result_handle_mismatch_refuses_not_invents(tmp_path):
    root, run_dir = _wave_workspace(tmp_path)
    relative, handle = _deposit_result(run_dir, {"returns": ["fixture packet return"]})
    _bank_workflow_row(root, result_path=relative, result_handle="sha256:" + "0" * 64)

    with pytest.raises(W.WorkflowRefused, match="RESULT-HANDLE-MISMATCH"):
        W.inspect_run(run_dir)


def test_ledger_row_result_path_outside_run_dir_is_not_lifted(tmp_path):
    root, run_dir = _wave_workspace(tmp_path)
    other = root / "evidence" / "WORKFLOWS" / "WORKFLOW-20260921T000000Z-000000000000"
    other.mkdir(parents=True)
    raw = json.dumps({"returns": []}, sort_keys=True).encode("utf-8")
    (other / "returns.json").write_bytes(raw)
    # A row naming a path outside THIS run's own evidence/WORKFLOWS/<run_id>/ directory - the
    # containment rule at workflow.py's _contained_ref (formerly inlined at :617-620) must not be
    # widened to reach it.
    _bank_workflow_row(root, result_path=f"evidence/WORKFLOWS/{other.name}/returns.json", result_handle=_sha(raw))

    with pytest.raises(W.WorkflowRefused, match="NOT-CONTAINED"):
        W.inspect_run(run_dir)


def test_no_ledger_row_at_all_still_refuses_cleanly(tmp_path):
    root, run_dir = _wave_workspace(tmp_path)
    (root / W.LEDGER).write_text("")

    with pytest.raises(W.WorkflowRefused, match="NO-LEDGER-WORKFLOW-ROW"):
        W.inspect_run(run_dir)


def test_last_workflow_row_wins_over_an_earlier_one(tmp_path):
    root, run_dir = _wave_workspace(tmp_path)
    stale_relative, stale_handle = "evidence/WORKFLOWS/does/not/matter.json", "sha256:" + "1" * 64
    _bank_workflow_row(root, status="INCOMPLETE", accepted=False,
                       result_path=stale_relative, result_handle=stale_handle,
                       packets_accepted=[], packets_not_accepted=["D1"])
    relative, handle = _deposit_result(run_dir, {"returns": ["second, corrected pass"]})
    _bank_workflow_row(root, status="COMPLETED", accepted=True,
                       result_path=relative, result_handle=handle,
                       packets_accepted=["D1"], packets_not_accepted=[])

    result = W.inspect_run(run_dir)

    assert result["status"] == "RECORDED-COMPLETED"
    assert result["accepted"] is True
    assert result["packets_accepted"] == ["D1"]
