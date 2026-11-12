"""Evidence and failure boundaries only; fake carriers are not product acceptance."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from laplace.pipeline import workflow as W

SOURCE = Path(__file__).resolve().parents[1]


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / "node.py").write_text("VALUE = 1\n")
    subprocess.run(["git", "add", "node.py"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                    "commit", "-qm", "fixture"], cwd=root, check=True)
    monkeypatch.delenv("LAPLACE_CUSTODY_LIVE", raising=False)
    spec = W._load(SOURCE / "profiles/workflows/build-review-synthesize.json")
    directory = W.create_run(root, spec, node="node.py", goal="change VALUE to 2 and independently check it",
                             model="fixture-provider-model", effort="high", state=tmp_path / "state",
                             write_paths=["node.py"])
    return root, directory


def carrier(calls, *, fault=None):
    def execute(prompt, context):
        sid = context["stage"]
        calls.append(sid)
        assert "EXACT RECONSTRUCTED NODE" in prompt
        assert "scripts/reconstruct_node.py node.py" in prompt
        root = Path(context["root"])
        if sid == "build":
            (root / "node.py").write_text("VALUE = 2\n")
            if fault == "interrupted":
                raise KeyboardInterrupt("fixture interruption after effect")
            if fault == "escaped":
                (root / "unrelated.py").write_text("unexpected = True\n")
        dependencies = context["dependencies"]
        unpaid = any(d["status"] != "RETURNED" or (d.get("result") or {}).get("decision") not in {"complete", "accept"}
                     for d in dependencies)
        decision = "complete" if sid == "build" else "accept"
        if sid == "adversary" and fault == "contest":
            decision = "contest"
        if sid == "synthesis" and unpaid:
            decision = "incomplete"
        value = {"decision": decision, "summary": "Fixture response; not a real-model acceptance claim.",
                 "evidence": ["node.py exact source inspected"],
                 "residuals": ["fixture unresolved evidence"] if decision in {"contest", "incomplete"} else [],
                 "consumed": [{"stage": d["stage"], "receipt_handle": d["receipt_handle"]} for d in dependencies]}
        if sid == "adversary" and fault == "dependency":
            value["consumed"][0]["receipt_handle"] = "sha256:" + "0" * 64
        if sid == "synthesis" and fault == "launder":
            value["decision"] = "accept"
        result = {"exit_code": 0, "turn_completed": True, "thread_id": "fixture-" + sid,
                  "raw_return": json.dumps(value), "commands": [{"command": "fixture source check", "exit_code": 0}],
                  "error": ""}
        if sid == "adversary":
            if fault in {"nonzero", "launder"}:
                result["exit_code"] = 7
            if fault == "malformed":
                result["raw_return"] = "{broken"
            if fault == "empty":
                value["evidence"] = []
                result["raw_return"] = json.dumps(value)
            if fault == "no_observation":
                result["commands"] = []
            if fault == "same_context":
                result["thread_id"] = "fixture-build"
        return result
    return execute


def test_real_compiler_return_chain_and_exact_resume(workspace):
    root, directory = workspace
    calls = []
    first = W.run_workflow(directory, executor=carrier(calls), stop_after="build")
    assert first["status"] == "PENDING" and not first["accepted"]
    assert calls == ["build"]
    result = W.run_workflow(directory, executor=carrier(calls))
    assert calls == ["build", "adversary", "synthesis"]
    assert result["status"] == "COMPLETED" and result["accepted"]
    assert len({r["provider_context"] for r in result["stages"]}) == 3
    receipt = W._load(directory / "build/receipt.json")
    assert receipt["execution"]["model"] == "fixture-provider-model"
    assert "model" not in receipt["authored_policy"]
    assert receipt["authored_policy"]["source"]
    assert receipt["packet_model_stamp"] == "opus"
    assert receipt["effects"]["node.py"]["before"] != receipt["effects"]["node.py"]["after"]
    W.run_workflow(directory, executor=lambda *_: pytest.fail("completed work replayed"))
    assert not list(directory.rglob("*prompt*"))
    records = [json.loads(line) for line in (root / W.LEDGER).read_text().splitlines()]
    assert len([r for r in records if r.get("record") == "dispatch" and r.get("phase") == "return"]) == 3
    for record in records:
        if record.get("record") == "workflow" and record.get("phase") == "result":
            assert W._file_hash(root / record["result_path"]) == record["result_handle"]


@pytest.mark.parametrize("fault", ["malformed", "nonzero", "dependency", "same_context", "empty", "no_observation", "launder"])
def test_bad_judgement_never_becomes_success(workspace, fault):
    _, directory = workspace
    result = W.run_workflow(directory, executor=carrier([], fault=fault))
    assert result["status"] == "INCOMPLETE" and not result["accepted"]
    assert result["stages"][1]["status"] == "FAILED"
    if fault == "launder":
        assert "SYNTHESIS-CANNOT-ACCEPT" in result["stages"][-1]["error"]
    else:
        assert result["stages"][-1]["result"]["decision"] == "incomplete"


def test_contested_judge_survives_synthesis(workspace):
    _, directory = workspace
    result = W.run_workflow(directory, executor=carrier([], fault="contest"))
    assert result["status"] == "CONTESTED" and not result["accepted"]
    assert result["stages"][1]["result"]["decision"] == "contest"
    assert result["stages"][-1]["result"]["residuals"]


@pytest.mark.parametrize("fault", ["artifact", "return", "receipt", "manifest"])
def test_resume_refuses_moved_evidence(workspace, fault):
    root, directory = workspace
    W.run_workflow(directory, executor=carrier([]), stop_after="build")
    if fault == "artifact":
        (root / "node.py").write_text("VALUE = 999\n")
    elif fault == "return":
        (directory / "build/return.json").write_text("{}")
    elif fault == "receipt":
        doc = W._load(directory / "build/receipt.json")
        doc["provider_context"] = "fabricated"
        (directory / "build/receipt.json").write_text(json.dumps(doc))
    else:
        doc = W._load(directory / "run.json")
        doc["goal"] = "different instruction"
        (directory / "run.json").write_text(json.dumps(doc))
    with pytest.raises(W.WorkflowRefused):
        W.run_workflow(directory, executor=lambda *_: pytest.fail("moved evidence dispatched"))


def test_interrupted_writer_preserved_and_never_replayed(workspace):
    root, directory = workspace
    with pytest.raises(KeyboardInterrupt):
        W.run_workflow(directory, executor=carrier([], fault="interrupted"))
    result = W.inspect_run(directory)
    assert result["status"] == "INTERRUPTED" and not result["accepted"]
    assert (root / "node.py").read_text() == "VALUE = 2\n"
    with pytest.raises(W.WorkflowRefused, match="INTERRUPTED"):
        W.run_workflow(directory, executor=lambda *_: pytest.fail("uncertain writer replayed"))


def test_new_evidence_is_recorded_and_available_to_review(workspace):
    root, directory = workspace
    result = W.run_workflow(directory, executor=carrier([], fault="escaped"))
    assert result["accepted"]
    build = result["stages"][0]
    assert "unrelated.py" in build["observed_changed_paths"]
    assert build["artifacts_after"]["unrelated.py"] == W._file_hash(root / "unrelated.py")
    assert result["stages"][1]["status"] == "RETURNED"


def test_duplicate_json_and_bad_graph_refused():
    with pytest.raises(W.WorkflowRefused, match="DUPLICATE"):
        json.loads('{"id":"a","id":"b"}', object_pairs_hook=W._unique)
    spec = W._load(SOURCE / "profiles/workflows/build-review-synthesize.json")
    spec["stages"][-1]["depends_on"] = ["adversary"]
    with pytest.raises(W.WorkflowRefused, match="EVERY-STAGE"):
        W.validate_spec(spec)


def test_recent_workflows_is_bounded_recorded_evidence_not_activity(tmp_path, monkeypatch):
    ledger = tmp_path / W.LEDGER
    ledger.parent.mkdir()
    finished = "WORKFLOW-20260919T142914Z-ed9b81c0156c"
    started = "WORKFLOW-20260919T152914Z-ed9b81c0156d"
    result_ref = f"evidence/WORKFLOWS/{finished}/results/observed.json"
    rows = [
        {"record": "workflow", "id": finished, "phase": "result", "status": "COMPLETED",
         "accepted": True, "result_path": result_ref, "result_handle": "sha256:" + "a" * 64},
        {"record": "workflow-stage", "id": started + ":build", "workflow_id": started,
         "phase": "start", "status": "STARTED", "stage": "build"},
    ]
    # An omitted old giant record must not force a full read or hide the intact tail.
    ledger.write_bytes(b'{"old":"' + b"x" * 4000 + b'"}\n' + b"\n".join(W.canonical(r) for r in rows) + b"\n")
    monkeypatch.setattr(W, "_records", lambda *_: pytest.fail("full ledger replay"))
    monkeypatch.setattr(W, "inspect_run", lambda *_: pytest.fail("deep status on doorway"))
    monkeypatch.setattr(W, "_load", lambda *_: pytest.fail("artifact bodies opened"))
    before = ledger.read_bytes()
    projection = W.recent_workflows(tmp_path, tail_bytes=1024)
    assert projection["status"] == "PARTIAL" and projection["older_workflows"] == "UNKNOWN"
    assert projection["observation"]["bytes_read"] <= 1024
    assert projection["revalidated"] is False and projection["activity"].startswith("UNKNOWN")
    assert [r["status"] for r in projection["workflows"]] == ["RECORDED-START", "RECORDED-COMPLETED"]
    result = projection["workflows"][1]
    assert result["recorded_accepted"] is True and result["result_ref"]["path"] == result_ref
    assert result["status_command"].endswith(f"status evidence/WORKFLOWS/{finished}")
    assert ledger.read_bytes() == before


def test_recent_workflows_names_missing_and_damaged_tail(tmp_path):
    assert W.recent_workflows(tmp_path)["status"] == "ABSENT"
    assert not list(tmp_path.iterdir())
    ledger = tmp_path / W.LEDGER
    ledger.parent.mkdir()
    ledger.write_bytes(b"not-json\n{\"unfinished\":")
    projection = W.recent_workflows(tmp_path)
    assert projection["status"] == "PARTIAL" and projection["malformed_rows"] == 1
    assert projection["incomplete_tail"] and projection["workflows"] == []


def test_gpu_host_mode_is_explicit_and_does_not_write_home(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    shim = root / "scripts/sandbox/bwrap"
    shim.parent.mkdir(parents=True)
    shim.write_bytes((SOURCE / "scripts/sandbox/bwrap").read_bytes())
    shim.chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    (home / "keep").write_text("unchanged")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: pytest.fail("HOME consulted by sandbox profile")))
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("CODEX_BWRAP_SHIM_LOG", str(home / "forbidden-log"))
    for name in ("LAPLACE_REQUIRE_GPU", "LAPLACE_NO_SPECTRAL", "LAPLACE_NO_SPECTRAL_GPU", "LAPLACE_EMBED_NO_GPU"):
        monkeypatch.delenv(name, raising=False)
    context = {"root": str(root), "state": str(tmp_path / "explicit-state"), "sandbox": "read-only"}
    plain = W.codex_sandbox_profile(context)
    assert plain["exec_args"] == ["-s", "danger-full-access", "-c", 'shell_environment_policy.inherit="all"']
    assert plain["env"]["PATH"] == "/usr/bin" and "LAPLACE_REQUIRE_GPU" not in plain["env"]
    gpu = W.codex_sandbox_profile({**context, "require_gpu": True})
    assert gpu["exec_args"] == ["-s", "danger-full-access", "-c", 'shell_environment_policy.inherit="all"']
    assert gpu["env"]["PATH"] == "/usr/bin"
    assert gpu["env"]["LAPLACE_REQUIRE_GPU"] == "1"
    assert gpu["env"]["LAPLACE_STATE"] == context["state"]
    assert "CODEX_BWRAP_SHIM_LOG" not in gpu["env"]
    assert gpu["evidence"]["shim"] is None
    assert gpu["evidence"]["filesystem_scope"] == "user-accessible host"
    assert gpu["evidence"]["gpu_execution"] == "NOT-PROVED-BY-CAPABILITY"
    assert list(home.iterdir()) == [home / "keep"]
    assert (home / "keep").read_text() == "unchanged"
