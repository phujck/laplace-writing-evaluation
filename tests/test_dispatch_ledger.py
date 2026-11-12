"""Consume dispatch evidence and stage admission; no provider or GPU execution."""
import json
import os
import subprocess
import tempfile
from types import SimpleNamespace

import pytest

from laplace.representation import custody_mode, device_policy
from laplace.engine import descent
from laplace.pipeline import dispatch as D
from scripts import audit_dispatch_models as audit
from scripts import dispatch_codex as door


def stage_row(root, *, record="stage", **overrides):
    row = {"record": record, "id": "WO-STAGE-PROSE", "admitted_by": "fixture-gate",
           "first_act": "compile the section", "section_id": "S2", "project": "fixture", **overrides}
    path = root / (D.STAGE_STORES[0] if record == "stage" else D.STAGE_STORES[1])
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(row) + "\n")
    return row, path


@pytest.mark.parametrize("record", ["stage", "work-order"])
def test_stage_compiles_from_owning_row(tmp_path, monkeypatch, record):
    row, _ = stage_row(tmp_path, record=record)
    monkeypatch.setattr(custody_mode, "is_off", lambda *_: True)
    rec = D.reconstruct_stage(row["id"], "check stage", repo_root=tmp_path)
    packet = D.compile_dispatch(row["id"], "check stage", "derive", repo_root=tmp_path, reconstruction=rec)
    assert "error" not in packet, packet
    assert packet["reconstruction_admission"]["admission_result"]["status"] == "ADMITTED"
    assert packet["stage"] == {key: row[key] for key in ("id", "admitted_by", "first_act")}
    assert "fixture-gate" in packet["prompt"]
    admission = dict(packet["reconstruction_admission"])
    handle = admission.pop("receipt_handle")
    assert handle == D._sha256(D._canonical_json(admission))


@pytest.mark.parametrize("fault,reason", [
    ("missing", "STAGE_NOT_FOUND"), ("fields", "STAGE_ADMISSION_FIELDS_MISSING"),
    ("drift", "STAGE_SOURCE_DRIFT"), ("ambiguous", "STAGE_AMBIGUOUS")])
def test_stage_refuses_missing_or_changed_evidence(tmp_path, monkeypatch, fault, reason):
    row, path = stage_row(tmp_path, first_act=None if fault == "fields" else "compile")
    monkeypatch.setattr(custody_mode, "is_off", lambda *_: True)
    if fault == "missing":
        path.unlink()
    if fault == "ambiguous":
        stage_row(tmp_path, record="work-order")
    rec = D.reconstruct_stage(row["id"], "check", repo_root=tmp_path)
    if fault == "drift":
        path.write_text(json.dumps({**row, "first_act": "changed"}) + "\n")
    packet = D.compile_dispatch(row["id"], "check", "derive", repo_root=tmp_path, reconstruction=rec)
    assert packet["reconstruction_admission"]["admission_result"] == {"status": "REFUSED", "reason": reason}


def test_prose_stage_routes_to_section_and_project(tmp_path, monkeypatch):
    row, _ = stage_row(tmp_path)
    monkeypatch.setattr(custody_mode, "is_off", lambda *_: True)
    calls = []
    def core(target, goal, worker, project, root, **kwargs):
        calls.append((target, project))
        return {"error": "no narrative specification for section 'S2'"}
    monkeypatch.setattr(D, "_compile_dispatch_core", core)
    rec = D.reconstruct_stage(row["id"], "check", repo_root=tmp_path)
    packet = D.compile_dispatch(row["id"], "check", "prose", repo_root=tmp_path, reconstruction=rec)
    assert calls == [("S2", "fixture")]
    assert packet["reconstruction_admission"]["admission_result"]["status"] == "ADMITTED"
    assert "NODE_MISMATCH" not in packet["error"]


def returned_fixture(root):
    out = root / ".dispatch" / "fixture"
    out.mkdir(parents=True)
    (out / "prompt.md").write_text("prompt")
    (out / "return.md").write_text("observed return")
    (out / "codex.log").write_bytes(b"x" * 6000)
    row = {"record": "dispatch", "id": "CODEX-20260914T120000Z-fixture", "phase": "compile",
           "status": "COMPILED", "executor": "codex-cli", "model": "fixture", "codex_model": "fixture",
           "sandbox": "read-only", "packet_model_stamp": "opus", "prompt_handle": door._sha("prompt")}
    return row, out


@pytest.mark.parametrize("event,expected", [
    (None, "RETURNED"), ("cpu", "RETURNED-WITH-FALLBACK"),
    ("disabled", "RETURNED-WITH-FALLBACK"), ("malformed", "RETURNED-FALLBACK-UNVERIFIED")])
def test_return_banks_and_moves_evidence(tmp_path, monkeypatch, event, expected):
    monkeypatch.setattr(door, "ROOT", tmp_path)
    row, out = returned_fixture(tmp_path)
    door._bank(row, out)
    start = door._time_value("2026-09-14T12:00:00Z")
    if event:
        raw = "broken" if event == "malformed" else json.dumps(
            {"ts": "2026-09-14T12:00:01+00:00", "choice": event, "dialed": True})
        (tmp_path / ".fallback_events.jsonl").write_text(raw + "\n")
    door._finish_return(row, out, start=start, end=start + 2, exit_code=0, keep_log=False)
    assert row["status"] == expected
    dest = tmp_path / "evidence/DISPATCH_2026-09-14" / row["id"]
    assert (dest / "return.md").read_text() == "observed return"
    assert (dest / "prompt.md").read_text() == "prompt"
    assert not (out / "return.md").exists() and not (out / "prompt.md").exists()
    assert row["return_handle"] == door._sha("observed return")
    assert (out / "codex.log").stat().st_size == 4096
    ledger = [json.loads(line) for line in (tmp_path / door.LEDGER).read_text().splitlines()]
    assert [r["phase"] for r in ledger] == ["compile", "return"]
    assert ledger[-1] == row


def test_time_window_excludes_other_fallbacks(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text("\n".join(json.dumps({"ts": ts, "choice": choice, "dialed": dialed}) for ts, choice, dialed in (
        ("2026-09-14T11:00:00Z", "cpu", True), ("2026-09-14T13:00:00Z", "cpu", True),
        ("2026-09-14T12:00:01Z", "cpu", False), ("2026-09-14T12:00:01Z", "gpu", True))))
    start = door._time_value("2026-09-14T12:00:00Z")
    assert door._fallbacks(start, start + 2, path)["rows"] == []


def test_backfill_preserves_ids_timestamps_and_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(door, "ROOT", tmp_path)
    row, out = returned_fixture(tmp_path)
    row.update(record="codex-dispatch", ts="20260914T120000Z", goal="WORK ORDER WO-fixture: test")
    (out / "row.json").write_text(json.dumps(row))
    result = door.backfill(out.parent)
    assert result["banked"] == 1
    ledger_row = json.loads((tmp_path / door.LEDGER).read_text())
    assert ledger_row["id"] == row["id"]
    assert ledger_row["ts_claimed"] == ledger_row["dispatched_at"] == row["ts"]
    assert ledger_row["edges"] == [{"rel": "grounds", "target": "WO-fixture"}]
    assert door.backfill(out.parent)["skipped"] == 1


def test_audit_uses_ledger_with_empty_dispatch_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(door, "ROOT", tmp_path)
    row, out = returned_fixture(tmp_path)
    door._bank(row)
    for path in out.iterdir():
        path.unlink()
    out.rmdir()
    report = audit.scan(tmp_path)
    assert report.dispatch_rows == 1 and report.violations == []
    # A stale/broken ignored run directory is not an audit input.
    out.mkdir()
    (out / "row.json").write_text("malformed")
    assert audit.scan(tmp_path) == report


@pytest.mark.parametrize("name", door.OPT_OUTS)
def test_fence_refuses_opt_out_mapping(name):
    with pytest.raises(RuntimeError, match="DISPATCH-FENCE-OPT-OUT"):
        door.check_fence_environment({name: "1"})


def test_runtime_fence_refuses_mutation_and_dialed_cpu(monkeypatch):
    # Register restoration before the runtime installs its hooks. No environment
    # knob is set; the guarded write raises before reaching the backing mapping.
    monkeypatch.setattr(os._Environ, "__setitem__", os._Environ.__setitem__)
    monkeypatch.setattr(os, "putenv", os.putenv)
    recorded = []
    monkeypatch.setattr(device_policy, "record_fallback", lambda *args, **kwargs: recorded.append(args))
    runtime = {}
    exec(door.RUNTIME_FENCE, runtime)
    for name in door.OPT_OUTS:
        with pytest.raises(RuntimeError, match="DISPATCH-FENCE-OPT-OUT"):
            runtime["_guarded_setitem"]({}, name, "1")
    with pytest.raises(device_policy.DeviceRequired, match="DISPATCH-FENCE-FALLBACK"):
        device_policy.record_fallback("fixture", "cpu", "explicit opt-out", dialed=True)
    assert len(recorded) == 1


def test_runtime_guard_handle_is_checked(tmp_path):
    packet = {"prompt": "fixture"}
    door._fence_packet(packet)
    packet["execution_fence"]["runtime_handle"] = "changed"
    with pytest.raises(RuntimeError, match="DISPATCH-FENCE-HANDLE-MISMATCH"):
        door._install_runtime_fence(tmp_path, packet, {})


def test_sitecustomize_loaded_by_executor_python(tmp_path):
    packet = {"prompt": "fixture"}
    door._fence_packet(packet)
    env = door._dispatch_env()
    assert all(name not in env for name in door.OPT_OUTS)
    door._install_runtime_fence(tmp_path, packet, env)
    # Invoke the installed check without setting an engine knob. The preceding
    # assertions prove startup installed both the environment and device hooks.
    code = ("import os; from laplace.representation import device_policy; "
            "assert os._Environ.__setitem__.__name__ == '_guarded_setitem'; "
            "assert device_policy.record_fallback.__name__ == '_guarded_fallback'; "
            "import sitecustomize; sitecustomize._check('LAPLACE_NO_SPECTRAL', '1')")
    proc = subprocess.run(["/usr/bin/python3", "-c", code], cwd=tmp_path, env=env,
                          text=True, capture_output=True)
    assert proc.returncode != 0
    assert "DISPATCH-FENCE-OPT-OUT: LAPLACE_NO_SPECTRAL" in proc.stderr


@pytest.mark.parametrize("exit_code,error,missing", [(1, "", False), (None, "TimeoutExpired", False), (0, "", True)])
def test_failed_or_missing_return_cannot_pass(tmp_path, monkeypatch, exit_code, error, missing):
    monkeypatch.setattr(door, "ROOT", tmp_path)
    row, out = returned_fixture(tmp_path)
    if missing:
        (out / "return.md").unlink()
    door._finish_return(row, out, start=0, end=2, exit_code=exit_code, keep_log=True, error=error)
    assert row["status"] == "FAILED"
    assert row["exit"] == exit_code


def test_main_banks_both_phases_with_simulated_provider(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(door, "ROOT", tmp_path)
    monkeypatch.setattr(descent, "__file__", str(tmp_path / "src/laplace/engine/descent.py"))
    monkeypatch.setattr(custody_mode, "is_off", lambda *_: True)
    monkeypatch.setattr(custody_mode, "read", lambda *_: {"mode": "OFF", "id": "fixture"})
    monkeypatch.setattr(door, "_install_gpu_shim", lambda: "fixture")
    monkeypatch.setattr(door, "_gpu_probe", lambda *_: {"visible": True, "detail": "fixture"})
    monkeypatch.setattr(door, "_dispatch_env", lambda: {})
    calls = []
    def provider(cmd, **kwargs):
        calls.append(cmd)
        assert "EXECUTION-FENCE" in kwargs["input"]
        assert "/runtime" in kwargs["env"]["PYTHONPATH"]
        from pathlib import Path
        Path(cmd[cmd.index("-o") + 1]).write_text("fixture return")
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(door.subprocess, "run", provider)
    (tmp_path / "node.md").write_text("Exact fixture.")
    assert door.main(["node.md", "WORK ORDER WO-fixture: verify", "--run", "--model", "fixture"]) == 0
    row = json.loads(capsys.readouterr().out)
    ledger = [json.loads(line) for line in (tmp_path / door.LEDGER).read_text().splitlines()]
    assert len(calls) == 1 and [r["phase"] for r in ledger] == ["compile", "return"]
    assert (tmp_path / row["return_path"]).read_text() == "fixture return"
    assert row["return_path"].startswith("evidence/DISPATCH_")
    assert row["edges"] == [{"rel": "grounds", "target": "WO-fixture"}]


def test_dispatch_codex_contract_consumes_fenced_ledger(tmp_path, monkeypatch):
    from laplace.pipeline.contracts_verify import dispatch_codex_contract
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    assert dispatch_codex_contract()["pass"] is True
