"""The host observer cannot turn process/config absence into engine acceptance."""
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

from laplace.engine import process_health as health


def process(proc, pid, exe, cwd, args, env=b"", parent=1):
    path = proc / str(pid)
    path.mkdir(parents=True)
    (path / "exe").symlink_to(exe)
    (path / "cwd").symlink_to(cwd)
    (path / "comm").write_text(Path(exe).name)
    (path / "cmdline").write_bytes(b"\0".join(arg.encode() for arg in args) + b"\0")
    (path / "environ").write_bytes(env)
    fields = ["0"] * 40
    fields[0], fields[1], fields[11], fields[12], fields[21] = "S", str(parent), "100", "50", "10"
    (path / "stat").write_text(f"{pid} (fixture) " + " ".join(fields))


def services(command, **kwargs):
    assert command[:3] == ["systemctl", "--user", "show"]
    assert kwargs["timeout"] <= 1
    return SimpleNamespace(returncode=0, stdout="\n\n".join(
        f"Id={unit}\nLoadState={'masked' if unit.startswith('eigen') else 'not-found'}\nActiveState=inactive\nMainPID=0"
        for unit in health.UNITS))


def test_no_prompt_or_generic_environment_exposure(tmp_path):
    root, proc = tmp_path / "repo", tmp_path / "proc"
    root.mkdir()
    process(proc, 10, "/usr/bin/python3", root,
            ["python3", "-c", "laplace.representation.atlas_watcher PROMPT_SECRET"],
            b"API_TOKEN=ENV_SECRET\0LAPLACE_STATE=/isolated/state\0")
    process(proc, 11, "/usr/bin/python3", tmp_path,
            ["python3", "-c", "laplace.web.scanner PROMPT_SECRET"])
    value = health.observe(root, proc_root=proc, home=tmp_path, run=services)
    items = value["processes"]["items"]
    assert [row["pid"] for row in items] == [10]
    assert items[0]["role"] == "transient-tool-purpose-unverified"
    assert items[0]["state_environment"] == {"LAPLACE_STATE": "/isolated/state"}
    assert not items[0]["imported_source_and_state_verified"]
    assert "SECRET" not in json.dumps(value)


def test_wrapper_and_shared_host_are_distinct(tmp_path):
    root, proc = tmp_path / "repo", tmp_path / "proc"
    root.mkdir()
    process(proc, 20, "/runtime/bin/python3.14", root,
            ["python3.14", "-I", "-B", str(root / "scripts/laplace_python.py"), "-m", "laplace.web.scanner"])
    process(proc, 21, "/usr/lib/chatgpt/resources/codex", tmp_path,
            ["codex", "app-server", "--prompt", "secret"], parent=5)
    value = health.observe(root, proc_root=proc, home=tmp_path, run=services)
    scanner, host = value["processes"]["items"]
    assert scanner["role"] == "scanner"
    assert scanner["source_root_declared_by_command"] == str(root)
    assert scanner["executable"] == "/runtime/bin/python3.14"
    assert host["role"] == "codex-shared-host"
    assert "individual tasks unknown" in host["task_attribution"]
    assert value["device_execution"] == "NOT_TESTED"


def test_caller_and_sibling_scripts_are_transient_work(tmp_path):
    root, proc = tmp_path / "repo", tmp_path / "proc"
    root.mkdir()
    process(proc, os.getpid(), "/usr/bin/python3", root, ["python3", "-"])
    process(proc, 23, "/runtime/bin/python3.14", root,
            ["python3.14", "-I", str(root / "scripts/laplace_python.py"), "scripts/reconstruct_node.py", "some-node"])
    value = health.observe(root, proc_root=proc, home=tmp_path, run=services)
    rows = {row["pid"]: row for row in value["processes"]["items"]}
    assert rows[os.getpid()]["is_caller"]
    assert rows[23]["role"] == "reconstruction"
    assert "sibling" in rows[23]["task_attribution"]


def test_services_observed_once_and_timeout_is_unknown(tmp_path):
    proc = tmp_path / "proc"
    proc.mkdir()
    calls = []
    def timeout(command, **kwargs):
        calls.append(command)
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])
    value = health.observe(tmp_path, proc_root=proc, home=tmp_path, run=timeout)
    assert len(calls) == 1
    assert value["services"]["status"] == "UNAVAILABLE"
    assert value["services"]["reason"] == "TimeoutExpired"
    assert value["processes"]["status"] == "OBSERVED"


def test_scan_cap_and_unavailable_proc_are_explicit(tmp_path):
    proc = tmp_path / "proc"
    process(proc, 30, "/usr/bin/python3", tmp_path, ["python3", "-"])
    process(proc, 31, "/usr/bin/python3", tmp_path, ["python3", "-"])
    value = health.observe(tmp_path, proc_root=proc, home=tmp_path, run=services, max_matches=1)
    assert value["processes"]["status"] == "PARTIAL"
    assert value["processes"]["truncated"]
    absent = health.observe(tmp_path, proc_root=tmp_path / "absent", home=tmp_path, run=services)
    assert absent["processes"]["status"] == "UNAVAILABLE"


def test_other_uid_and_unreported_services_are_never_certified(tmp_path):
    proc = tmp_path / "proc"
    process(proc, 35, "/usr/bin/python3", tmp_path, ["python3", "-"])
    rows = health._processes(tmp_path, proc, uid=os.getuid() + 1, caller_pid=35,
                             max_entries=10, max_matches=10)
    assert rows["items"] == []
    result = health._services(lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout=""))
    assert result["status"] == "PARTIAL"
    assert all(row["LoadState"] == "UNKNOWN" for row in result["items"])


def test_foreign_dormant_checkout_and_legacy_interpreter_are_only_declarations(tmp_path):
    config = tmp_path / ".config/eigen/front-launch.json"
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps({"checkout": "/old/laplace-live", "expected_commit": "abc",
                                  "browser_command": "PRIVATE_ARGUMENT"}))
    unit = tmp_path / ".config/systemd/user/otter-ingest.service"
    unit.parent.mkdir(parents=True)
    unit.write_text("[Service]\nWorkingDirectory=/main/laplace\nExecStart=/main/laplace/.venv/bin/python /main/laplace/scripts/ingest_otter.py --secret PRIVATE_ARGUMENT\n")
    (unit.parent / "eigen-face.service").symlink_to("/dev/null")
    proc = tmp_path / "proc"
    proc.mkdir()
    value = health.observe(tmp_path, proc_root=proc, home=tmp_path, run=services)
    declarations = value["launch_declarations"]
    assert not declarations["front_launcher"]["checkout_matches_observed_root"]
    otter = next(row for row in declarations["units"] if row["path"] == str(unit))
    assert not otter["uses_laplace_wrapper"]
    assert value["processes"]["items"] == []
    assert "PRIVATE_ARGUMENT" not in json.dumps(value)
