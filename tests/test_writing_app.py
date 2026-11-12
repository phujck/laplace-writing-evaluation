from __future__ import annotations

import json
import importlib.util
from pathlib import Path
import socket
import sys
import shutil
import pytest

from laplace.desktop import writing_app
from laplace.core import runtime as core_runtime
from laplace.core import checkout


def _project(tmp_path: Path) -> None:
    # Managed fixtures carry the real declared entrance; portable fixtures use
    # writing_server instead of inventing a missing-profile compatibility path.
    root=Path(__file__).resolve().parents[1]
    for relative in ("runtime_profiles.toml","scripts/laplace-python","scripts/laplace_python.py",
                     "src/laplace/core/runtime.py"):
        target=tmp_path/relative;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(root/relative,target)
    # copy2 keeps the source mode; a read-only staged checkout may not carry the executable bit.
    # Mark only this disposable copied launcher executable, never the checkout it was copied from.
    launcher=tmp_path/"scripts/laplace-python";launcher.chmod(launcher.stat().st_mode|0o755)
    (tmp_path/"src/laplace/desktop").mkdir(parents=True,exist_ok=True)
    (tmp_path/".synthetic-managed-unit-fixture").touch()
    for relative in ("src/laplace/web/scanner.py", "src/laplace/web/authoring.py", "src/laplace/pipeline/authoring.py"):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(relative, encoding="utf-8")


@pytest.fixture(autouse=True)
def _mock_runtime_probe_only_for_mock_process_fixtures(monkeypatch):
    original=writing_app._validate_managed_runtime
    def validate(root,**kwargs):
        if (Path(root)/".synthetic-managed-unit-fixture").exists():
            return core_runtime.selection_basis(root)
        return original(root,**kwargs)
    monkeypatch.setattr(writing_app,"_validate_managed_runtime",validate)



def _fixture_health(root, *, state=None, pid=None, **fields):
    record=writing_app._read(state) if state is not None else None
    producer=pid if pid is not None else (record or {}).get('pid',81)
    return {'source':str(root),'runtime':'writing','pid':producer,'active_turns':0,
            'source_start':writing_app.source_snapshot(root),
            'runtime_selection_start':core_runtime.selection_basis(root),
            'runtime_start':core_runtime.receipt(),**fields}

def test_source_identity_changes_when_authoring_runtime_changes(tmp_path):
    _project(tmp_path)
    first = writing_app.source_identity(tmp_path)
    (tmp_path / "src/laplace/pipeline/authoring.py").write_text("changed", encoding="utf-8")
    assert writing_app.source_identity(tmp_path) != first


def test_status_and_stop_refuse_reused_pid(tmp_path, monkeypatch):
    _project(tmp_path)
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"schema_version": writing_app.STATE_SCHEMA, "pid": 77, "start_tick": "old",
                                 "repo_root": str(tmp_path), "source_identity": writing_app.source_identity(tmp_path)}), encoding="utf-8")
    monkeypatch.setattr(writing_app, "_start_tick", lambda pid: "new")
    monkeypatch.setattr(writing_app, "health", lambda *a, **k: None)
    killed = []
    monkeypatch.setattr(writing_app.os, "kill", lambda *args: killed.append(args))
    assert writing_app.status(root=tmp_path, state=state)["status"] == "stale-process"
    assert writing_app.stop(root=tmp_path, state=state)["status"] == "stale-process"
    assert killed == []


def test_ensure_reuses_one_healthy_receipted_server(tmp_path, monkeypatch):
    _project(tmp_path)
    state = tmp_path / "state.json"
    monkeypatch.setattr(writing_app, "_start_tick", lambda pid: "tick")
    health = _fixture_health(tmp_path, state=state, active_turns=0)
    calls = []
    monkeypatch.setattr(writing_app, "_listener_present", lambda *args: False)

    class Process:
        pid = 81
        returncode = None
        def poll(self): return None
        def terminate(self): pass
        def wait(self, timeout=None): pass

    monkeypatch.setattr(writing_app, "health", lambda *a, **k: health if calls else None)
    monkeypatch.setattr(writing_app, "_start_server", lambda *a, **k: calls.append("start") or Process())
    first = writing_app.ensure_server(root=tmp_path, state=state)
    second = writing_app.ensure_server(root=tmp_path, state=state)
    assert first["disposition"] == "started"
    assert second["disposition"] == "reused"
    assert calls == ["start"]


def test_invalid_update_keeps_healthy_workspace_running(tmp_path, monkeypatch):
    _project(tmp_path)
    state = tmp_path / "state.json"
    record = {"schema_version": writing_app.STATE_SCHEMA, "pid": 81, "start_tick": "tick",
              "repo_root": str(tmp_path), "source_identity": writing_app.source_identity(tmp_path)}
    state.write_text(json.dumps(record))
    (tmp_path / "src/laplace/web/authoring_surface.py").write_text("if True:\nnot_indented = True\n")
    monkeypatch.setattr(writing_app, "_start_tick", lambda pid: "tick")
    monkeypatch.setattr(writing_app, "health", lambda *a, **k: _fixture_health(tmp_path, state=state, active_turns=0))
    monkeypatch.setattr(writing_app, "_terminate_owned", lambda *a: pytest.fail("healthy workspace was stopped"))
    monkeypatch.setattr(writing_app, "_start_server", lambda *a: pytest.fail("invalid update was started"))

    result = writing_app.ensure_server(root=tmp_path, state=state)

    assert result["disposition"] == "update-unavailable"
    assert "authoring_surface.py:2" in result["update_error"]
    assert result["health"]["runtime"] == "writing"
    assert json.loads(state.read_text()) == record


def test_owned_source_upgrade_waits_for_retired_listener_before_start(tmp_path,monkeypatch):
    _project(tmp_path);state=tmp_path/'state.json'
    state.write_text(json.dumps({'schema_version':writing_app.STATE_SCHEMA,'pid':77,
        'start_tick':'old-tick','repo_root':str(tmp_path),'source_identity':'old-source',
        'host':'127.0.0.1','port':18871}))
    live=_fixture_health(tmp_path, state=state, active_turns=0, active_previews=0, active_builds=0, active_runs=0, active_proof_checks=0)
    listeners=iter([True,True,False]);events=[]
    class Process:
        pid=81;returncode=None
        def poll(self):return None
    monkeypatch.setattr(writing_app,'_start_tick',lambda pid:'old-tick' if pid==77 else 'new-tick')
    monkeypatch.setattr(writing_app,'health',lambda *a,**k:_fixture_health(tmp_path,state=state,active_turns=0,active_previews=0,active_builds=0,active_runs=0,active_proof_checks=0))
    monkeypatch.setattr(writing_app,'_terminate_owned',lambda *a:events.append('retired-owned'))
    monkeypatch.setattr(writing_app,'_listener_present',lambda *a:next(listeners))
    monkeypatch.setattr(writing_app.time,'sleep',lambda value:events.append(('wait',value)))
    monkeypatch.setattr(writing_app,'_start_server',lambda *a,**k:events.append('started') or Process())

    result=writing_app.ensure_server(root=tmp_path,state=state,port=18871)

    assert result['status']=='running' and result['started'] is True
    assert events[0]=='retired-owned' and events[-1]=='started'
    assert any(isinstance(event,tuple) and event[0]=='wait' for event in events)


def test_owned_upgrade_still_refuses_listener_that_does_not_release(tmp_path,monkeypatch):
    _project(tmp_path);state=tmp_path/'state.json'
    state.write_text(json.dumps({'schema_version':writing_app.STATE_SCHEMA,'pid':77,
        'start_tick':'tick','repo_root':str(tmp_path),'source_identity':'old-source'}))
    monkeypatch.setattr(writing_app,'_start_tick',lambda pid:'tick')
    monkeypatch.setattr(writing_app,'health',lambda *a,**k:_fixture_health(tmp_path, state=state, active_turns=0))
    monkeypatch.setattr(writing_app,'_terminate_owned',lambda *a:None)
    monkeypatch.setattr(writing_app,'_listener_present',lambda *a:True)
    monkeypatch.setattr(writing_app,'_wait_owned_listener_release',lambda *a,**k:False)
    monkeypatch.setattr(writing_app,'_start_server',lambda *a,**k:pytest.fail('persistent listener was replaced'))

    with pytest.raises(writing_app.WritingAppError,match='port is occupied'):
        writing_app.ensure_server(root=tmp_path,state=state)


def test_real_owned_upgrade_releases_fixture_port_and_restarts(tmp_path):
    root=Path(__file__).resolve().parents[1];state=tmp_path/'managed-state.json'
    with socket.socket() as probe:
        probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
    first=None;second=None
    try:
        first=writing_app.ensure_server(root=root,state=state,port=port,timeout=8)
        old_pid=first['record']['pid'];record=json.loads(state.read_text())
        record['source_identity']='sha256:fixture-stale-source';state.write_text(json.dumps(record))
        second=writing_app.ensure_server(root=root,state=state,port=port,timeout=8)
        assert second['status']=='running' and second['started'] is True
        assert second['record']['pid']!=old_pid
        assert writing_app.status(root=root,state=state,port=port)['status']=='running'
    finally:
        if state.is_file():writing_app.stop(root=root,state=state)


def test_native_backend_start_update_and_reconnect_preserve_process_receipt(tmp_path, monkeypatch):
    """Exercise the desktop's real subprocess door, not only HTTP readiness."""
    import importlib.util
    from urllib.request import urlopen

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("native_reconnect_fixture", root / "src/laplace/desktop/native_writing.py")
    native = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(native)
    state = tmp_path / "desktop-state.json"
    monkeypatch.setenv("LAPLACE_STATE", str(tmp_path / "runtime-state"))
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    def desktop(action):
        return native.backend(root, state, "127.0.0.1", port, action)

    def assert_receipted(value):
        record = json.loads(state.read_text())
        assert value["health"]["pid"] == record["pid"]
        assert record["start_tick"] == writing_app._start_tick(record["pid"])
        assert record["frontend_bundle"] == value["health"]["frontend_bundle"]
        return record["pid"]

    try:
        first = desktop("--reconnect")
        first_pid = assert_receipted(first)
        assert first["started"] is True
        again = desktop("--reconnect")
        assert assert_receipted(again) == first_pid and again["started"] is False

        # A source update must go through the same owner that reconnect consults.
        record = json.loads(state.read_text())
        record["source_identity"] = "fixture-prior-source"
        state.write_text(json.dumps(record))
        passive = desktop("--reconnect")
        assert passive["disposition"] == "reused-current-runtime"
        assert assert_receipted(passive) == first_pid
        updated = desktop("--update")
        new_pid = assert_receipted(updated)
        assert updated["status"] == "running" and new_pid != first_pid

        reopened = desktop("--reconnect")
        assert reopened["status"] == "running" and reopened["started"] is False
        assert assert_receipted(reopened) == new_pid
        with urlopen(writing_app.url(port=port), timeout=5) as response:
            assert response.status == 200 and b"Research" in response.read()
    finally:
        if state.is_file():
            writing_app.stop(root=root, state=state)


@pytest.mark.parametrize("changed_source", [False, True])
def test_transient_health_failure_rechecks_without_interrupting_work(tmp_path, monkeypatch, changed_source):
    _project(tmp_path)
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"schema_version": writing_app.STATE_SCHEMA,
        "pid": 81, "start_tick": "tick", "repo_root": str(tmp_path),
        "source_identity": "prior" if changed_source else writing_app.source_identity(tmp_path), "runtime_selection_start":core_runtime.selection_basis(tmp_path)}))
    healthy = _fixture_health(tmp_path, state=state, active_turns=1)
    observations = iter([None, healthy])
    monkeypatch.setattr(writing_app, "_start_tick", lambda pid: "tick")
    monkeypatch.setattr(writing_app, "health", lambda *a, **k: next(observations))
    monkeypatch.setattr(writing_app.time, "sleep", lambda _: None)
    monkeypatch.setattr(writing_app, "_terminate_owned", lambda *a: pytest.fail("active work was stopped"))
    monkeypatch.setattr(writing_app, "_start_server", lambda *a: pytest.fail("active work was replaced"))

    result = writing_app.ensure_server(root=tmp_path, state=state)

    assert result["disposition"] == ("upgrade-after-active-work" if changed_source else "reused")
    assert result["health"]["active_turns"] == 1


def test_health_allows_slow_managed_endpoint_with_bounded_default_timeout(monkeypatch):
    """The managed probe tolerates the observed sub-second health response."""
    calls = []
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self):
            return json.dumps({"source": "/workspace", "runtime": "writing", "active_turns": 0}).encode()
    def open_url(request_url, timeout):
        calls.append((request_url, timeout))
        return Response()
    monkeypatch.setattr(writing_app.urllib.request, "urlopen", open_url)

    assert writing_app.health() == {"source": "/workspace", "runtime": "writing", "active_turns": 0}
    assert calls == [(writing_app.health_url(), 1.0)]


def test_slow_owned_health_with_active_work_defers_upgrade(tmp_path, monkeypatch):
    _project(tmp_path)
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"schema_version": writing_app.STATE_SCHEMA,
        "pid": 81, "start_tick": "tick", "repo_root": str(tmp_path),
        "source_identity": "prior"}))
    calls = []
    def probe(*args, **kwargs):
        calls.append(kwargs.get("timeout"))
        return (_fixture_health(tmp_path, state=state, active_turns=1)
                if kwargs.get("timeout") == 3.0 else None)
    monkeypatch.setattr(writing_app, "health", probe)
    monkeypatch.setattr(writing_app, "_start_tick", lambda pid: "tick")
    monkeypatch.setattr(writing_app.time, "sleep", lambda _: None)
    monkeypatch.setattr(writing_app, "_terminate_owned", lambda *a: pytest.fail("active work was stopped"))

    result = writing_app.ensure_server(root=tmp_path, state=state)

    assert result["disposition"] == "upgrade-after-active-work"
    assert 3.0 in calls


def test_failed_start_retains_diagnostic_log_and_reports_cause(tmp_path, monkeypatch):
    _project(tmp_path)
    state = tmp_path / "state.json"
    class FailedProcess:
        pid = 81
        returncode = 1
        def poll(self): return 1
    def start(root, host, port, log_path,*args):
        log_path.write_text("ImportError: required runtime component is unavailable\n")
        return FailedProcess()
    monkeypatch.setattr(writing_app, "_start_server", start)
    monkeypatch.setattr(writing_app, "_start_tick", lambda pid: "tick")
    monkeypatch.setattr(writing_app, "health", lambda *a, **k: None)
    monkeypatch.setattr(writing_app, "_listener_present", lambda *a: False)

    with pytest.raises(writing_app.WritingAppError, match="ImportError: required runtime"):
        writing_app.ensure_server(root=tmp_path, state=state)
    assert "ImportError" in state.with_suffix(".log").read_text()
    assert not state.exists()


@pytest.mark.parametrize("observed_tick", [None, "reused-by-another-process"])
def test_ensure_recovers_same_checkout_dead_or_reused_pid_without_signalling(
        tmp_path, monkeypatch, observed_tick):
    _project(tmp_path)
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"schema_version": writing_app.STATE_SCHEMA,
        "pid": 77, "start_tick": "old", "repo_root": str(tmp_path),
        "source_identity": "old-source", "host": "127.0.0.1", "port": 8771}))
    calls, signals = [], []

    class Process:
        pid = 81
        returncode = None
        def poll(self): return None
        def terminate(self): pass
        def wait(self, timeout=None): pass

    monkeypatch.setattr(writing_app, "_start_tick",
                        lambda pid: "new-process" if pid == 81 else observed_tick)
    monkeypatch.setattr(writing_app, "_listener_present", lambda *args: False)
    monkeypatch.setattr(writing_app, "_start_server",
                        lambda *args: calls.append("start") or Process())
    monkeypatch.setattr(writing_app, "health", lambda *args, **kwargs: (_fixture_health(tmp_path, state=state, active_turns=0)
        if calls else None))
    monkeypatch.setattr(writing_app.os, "kill", lambda *args: signals.append(args))

    result = writing_app.ensure_server(root=tmp_path, state=state)

    assert result["status"] == "running" and result["started"] is True
    assert calls == ["start"] and signals == []
    assert json.loads(state.read_text())["pid"] == 81


def test_ensure_never_replaces_stale_receipt_when_port_has_unmatched_listener(
        tmp_path, monkeypatch):
    _project(tmp_path)
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"schema_version": writing_app.STATE_SCHEMA,
        "pid": 77, "start_tick": "old", "repo_root": str(tmp_path),
        "source_identity": "old-source", "host": "127.0.0.1", "port": 8771}))
    monkeypatch.setattr(writing_app, "_start_tick", lambda pid: None)
    monkeypatch.setattr(writing_app, "health", lambda *args, **kwargs: None)
    monkeypatch.setattr(writing_app, "_listener_present", lambda *args: True)
    starts = []
    monkeypatch.setattr(writing_app, "_start_server", lambda *args: starts.append(args))

    with pytest.raises(writing_app.WritingAppError, match="listener"):
        writing_app.ensure_server(root=tmp_path, state=state)

    assert state.is_file() and starts == []


def test_health_refuses_general_scanner_runtime(monkeypatch):
    class Response:
        status = 200
        def read(self): return b'{"source":"x","runtime":"scanner","active_turns":0}'
        def __enter__(self): return self
        def __exit__(self, *args): return False
    monkeypatch.setattr(writing_app.urllib.request, "urlopen", lambda *a, **k: Response())
    assert writing_app.health() is None


def test_default_launcher_is_native_and_service_only_mode_stays_explicit(tmp_path, monkeypatch):
    _project(tmp_path)
    state = tmp_path / "state.json"
    command = writing_app.native_command(tmp_path, state, "127.0.0.1", 8771)
    assert command[:3] == ["/usr/bin/python3", "-I", "-B"]
    assert command[3].endswith("src/laplace/desktop/native_writing.py")
    assert not any("chrome" in item.lower() or "firefox" in item.lower() for item in command)
    calls = []
    monkeypatch.setattr(writing_app.os, "execv", lambda executable, argv: calls.append(argv))
    assert writing_app.main(["--repo-root", str(tmp_path), "--state", str(state)]) == 0
    assert calls == [command]

    monkeypatch.setattr(writing_app, "ensure_server", lambda **kwargs: {
        "status": "running", "started": True})
    assert writing_app.main(["--repo-root", str(tmp_path), "--state", str(state),
                             "--no-open"]) == 0
    assert calls == [command]


def test_busy_backend_refuses_last_window_stop_without_signalling(tmp_path, monkeypatch):
    _project(tmp_path)
    state = tmp_path / "state.json"
    record = {"schema_version": writing_app.STATE_SCHEMA, "pid": 77, "start_tick": "tick",
              "repo_root": str(tmp_path), "source_identity": writing_app.source_identity(tmp_path),
              "host": "127.0.0.1", "port": 8771}
    state.write_text(json.dumps(record))
    monkeypatch.setattr(writing_app, "_start_tick", lambda pid: "tick")
    monkeypatch.setattr(writing_app, "health", lambda *args, **kwargs: _fixture_health(tmp_path, state=state, active_turns=1, active_previews=0, active_builds=0))
    signals = []
    monkeypatch.setattr(writing_app.os, "kill", lambda *args: signals.append(args))

    result = writing_app.stop(root=tmp_path, state=state)

    assert result["status"] == "busy" and result["stopped"] is False
    assert state.is_file() and signals == []


def test_owned_engine_stop_refuses_unknown_health_without_signalling(tmp_path,monkeypatch):
    _project(tmp_path);state=tmp_path/'state.json'
    record={'schema_version':writing_app.STATE_SCHEMA,'pid':77,'start_tick':'tick',
            'repo_root':str(tmp_path),'source_identity':writing_app.source_identity(tmp_path),
            'host':'127.0.0.1','port':8771}
    state.write_text(json.dumps(record));signals=[]
    monkeypatch.setattr(writing_app,'_start_tick',lambda pid:'tick')
    monkeypatch.setattr(writing_app,'health',lambda *args,**kwargs:None)
    monkeypatch.setattr(writing_app.os,'kill',lambda *args:signals.append(args))
    result=writing_app.stop(root=tmp_path,state=state)
    assert result['status']=='unknown-health' and result['stopped'] is False
    assert signals==[] and state.is_file()


def test_exact_native_viewer_parent_is_distinguished_from_operator_cli(tmp_path,monkeypatch):
    root=tmp_path/'repo';_project(root);native=root/'src/laplace/desktop/native_writing.py';native.write_text('# native')
    state=tmp_path/'state.json';proc=tmp_path/'proc';parent=proc/'77';parent.mkdir(parents=True)
    executable=Path(sys.executable).resolve();(parent/'exe').symlink_to(executable)
    argv=[str(executable),'-I','-B',str(native.resolve()),'--repo-root',str(root.resolve()),
          '--state',str(state.resolve()),'--host','127.0.0.1','--port','8771']
    (parent/'cmdline').write_bytes(b'\0'.join(item.encode() for item in argv)+b'\0')
    monkeypatch.setattr(writing_app.os,'getppid',lambda:77)
    record={'host':'127.0.0.1','port':8771}
    assert writing_app._native_viewer_parent(record,root.resolve(),state,_proc_root=proc)
    assert not writing_app._native_viewer_parent({**record,'port':8772},root.resolve(),state,_proc_root=proc)


def test_legacy_native_viewer_close_keeps_owned_daemon_running(tmp_path,monkeypatch):
    _project(tmp_path);state=tmp_path/'state.json'
    record={'schema_version':writing_app.STATE_SCHEMA,'pid':77,'start_tick':'tick',
            'repo_root':str(tmp_path),'source_identity':writing_app.source_identity(tmp_path),
            'host':'127.0.0.1','port':8771}
    state.write_text(json.dumps(record));signals=[]
    monkeypatch.setattr(writing_app,'_start_tick',lambda pid:'tick')
    monkeypatch.setattr(writing_app,'_native_viewer_parent',lambda *args:True)
    monkeypatch.setattr(writing_app,'health',lambda *args,**kwargs:pytest.fail('viewer close probed daemon health'))
    monkeypatch.setattr(writing_app.os,'kill',lambda *args:signals.append(args))
    result=writing_app.stop(root=tmp_path,state=state)
    assert result=={'status':'viewer-detached','disposition':'keep-running','stopped':False,'pid':77}
    assert signals==[] and state.is_file()


@pytest.mark.parametrize("active_field", ["active_runs", "active_proof_checks"])
def test_owned_engine_stop_waits_for_external_producer_or_proof_terminal_state(
        tmp_path, monkeypatch, active_field):
    _project(tmp_path)
    state = tmp_path / "state.json"
    record = {"schema_version": writing_app.STATE_SCHEMA, "pid": 77,
              "start_tick": "tick", "repo_root": str(tmp_path),
              "source_identity": writing_app.source_identity(tmp_path),
              "host": "127.0.0.1", "port": 8771}
    state.write_text(json.dumps(record))
    monkeypatch.setattr(writing_app, "_start_tick", lambda pid: "tick")
    work = _fixture_health(tmp_path, state=state, active_turns=0, active_previews=0, active_builds=0, active_runs=0, active_proof_checks=0)
    work[active_field] = 1
    monkeypatch.setattr(writing_app, "health", lambda *args, **kwargs: dict(work))
    signals = []
    monkeypatch.setattr(writing_app.os, "kill", lambda *args: signals.append(args))

    blocked = writing_app.stop(root=tmp_path, state=state)
    assert blocked["status"] == "busy" and signals == [] and state.is_file()

    work[active_field] = 0
    monkeypatch.setattr(writing_app, "_terminate_owned", lambda *args: signals.append("stopped"))
    stopped = writing_app.stop(root=tmp_path, state=state)
    assert stopped["status"] == "stopped" and signals == ["stopped"]
    assert not state.exists()


def test_installer_renders_a_per_user_entry_without_autostart(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts" / "install_writing_app.py"
    spec = importlib.util.spec_from_file_location("install_writing_app_test", script)
    assert spec and spec.loader
    install_writing_app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(install_writing_app)
    checkout = tmp_path / "checkout"
    launcher = checkout / "src/laplace/desktop/writing_app.py"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("# launcher", encoding="utf-8")
    plan = install_writing_app.render(checkout=checkout, desktop_path=tmp_path / "apps/app.desktop",
                                      icon_path=tmp_path / "icons/laplace-writing.svg")
    desktop = plan["files"][0]["content"]
    assert "laplace.desktop.writing_app" in desktop
    assert "chrome" not in desktop.lower() and "firefox" not in desktop.lower()
    assert "Autostart" not in desktop
    assert "--port" not in desktop  # launcher owns the managed default


def test_passive_reconnect_reuses_healthy_stale_source_without_preflight_or_replacement(tmp_path,monkeypatch):
    _project(tmp_path);state=tmp_path/'state.json'
    record={'schema_version':writing_app.STATE_SCHEMA,'pid':81,'start_tick':'tick','repo_root':str(tmp_path),'source_identity':writing_app.source_identity(tmp_path)}
    state.write_text(json.dumps(record));(tmp_path/'src/laplace/web/authoring.py').write_text('invalid in-progress source !')
    monkeypatch.setattr(writing_app,'_start_tick',lambda pid:'tick')
    monkeypatch.setattr(writing_app,'health',lambda *a,**k:_fixture_health(tmp_path, state=state, active_turns=0))
    monkeypatch.setattr(writing_app,'_validate_runtime_sources',lambda *a:pytest.fail('passive focus validated an unfinished update'))
    monkeypatch.setattr(writing_app,'_terminate_owned',lambda *a:pytest.fail('passive focus stopped the healthy runtime'))
    monkeypatch.setattr(writing_app,'_start_server',lambda *a,**k:pytest.fail('passive focus launched a new runtime'))
    result=writing_app.ensure_server(root=tmp_path,state=state,allow_update=False)
    assert result['disposition']=='reused-current-runtime' and result['started'] is False
    assert json.loads(state.read_text())==record


def test_reconnect_mode_still_recovers_an_absent_owned_service(tmp_path,monkeypatch):
    _project(tmp_path);state=tmp_path/'state.json';starts=[]
    monkeypatch.setattr(writing_app,'_start_tick',lambda pid:'tick')
    monkeypatch.setattr(writing_app,'_listener_present',lambda *a:False)
    monkeypatch.setattr(writing_app,'health',lambda *a,**k:_fixture_health(tmp_path, state=state) if starts else None)
    class Process:
        pid=91
        def poll(self):return None
    monkeypatch.setattr(writing_app,'_start_server',lambda *a,**k:starts.append('start') or Process())
    result=writing_app.ensure_server(root=tmp_path,state=state,allow_update=False)
    assert result['started'] is True and starts==['start']


def test_reconnect_cli_selects_passive_policy_without_changing_explicit_update(tmp_path,monkeypatch):
    calls=[]
    monkeypatch.setattr(writing_app,'ensure_server',lambda **kwargs:calls.append(kwargs) or {'status':'running','started':False})
    assert writing_app.main(['--repo-root',str(tmp_path),'--reconnect'])==0
    assert calls[-1]['allow_update'] is False
    assert writing_app.main(['--repo-root',str(tmp_path),'--no-open'])==0
    assert calls[-1]['allow_update'] is False
    assert writing_app.main(['--repo-root',str(tmp_path),'--update'])==0
    assert calls[-1]['allow_update'] is True


def test_atlas_source_changes_identity_and_bad_atlas_keeps_owned_process(tmp_path, monkeypatch):
    _project(tmp_path)
    atlas=tmp_path/'src/atlas/store.py';atlas.parent.mkdir(parents=True)
    atlas.write_text('VALUE=1\n')
    first=writing_app.source_identity(tmp_path)
    state=tmp_path/'state.json'
    state.write_text(json.dumps({'schema_version':writing_app.STATE_SCHEMA,'pid':81,'start_tick':'tick',
                                'repo_root':str(tmp_path),'source_identity':first}))
    monkeypatch.setattr(writing_app,'_start_tick',lambda pid:'tick')
    monkeypatch.setattr(writing_app,'health',lambda *a,**k:_fixture_health(tmp_path, state=state, active_turns=0))
    monkeypatch.setattr(writing_app,'_terminate_owned',lambda *a:pytest.fail('invalid Atlas retired healthy process'))
    atlas.write_text('if :\n')
    assert writing_app.status(root=tmp_path,state=state)['status']=='stale-source'
    result=writing_app.ensure_server(root=tmp_path,state=state)
    assert result['disposition']=='update-unavailable' and 'src/atlas/store.py' in result['update_error']


def test_source_move_during_validation_and_active_work_keep_owned_process(tmp_path, monkeypatch):
    _project(tmp_path);state=tmp_path/'state.json'
    state.write_text(json.dumps({'schema_version':writing_app.STATE_SCHEMA,'pid':81,'start_tick':'tick',
        'repo_root':str(tmp_path),'source_identity':'older'}))
    monkeypatch.setattr(writing_app,'_start_tick',lambda pid:'tick')
    monkeypatch.setattr(writing_app,'health',lambda *a,**k:_fixture_health(tmp_path, state=state, active_turns=1))
    monkeypatch.setattr(writing_app,'_terminate_owned',lambda *a:pytest.fail('busy/racing source retired old process'))
    assert writing_app.ensure_server(root=tmp_path,state=state)['disposition']=='upgrade-after-active-work'
    monkeypatch.setattr(writing_app,'health',lambda *a,**k:_fixture_health(tmp_path, state=state, active_turns=0))
    monkeypatch.setattr(writing_app,'_validate_runtime_sources',lambda root:(root/'src/laplace/new.py').write_text('CHANGED=1'))
    assert writing_app.ensure_server(root=tmp_path,state=state)['disposition']=='update-in-progress'


def test_health_start_basis_mismatch_is_not_current_runtime(tmp_path, monkeypatch):
    _project(tmp_path);state=tmp_path/'state.json';identity=writing_app.source_identity(tmp_path)
    state.write_text(json.dumps({'schema_version':writing_app.STATE_SCHEMA,'pid':81,'start_tick':'tick',
        'repo_root':str(tmp_path),'source_identity':identity}))
    monkeypatch.setattr(writing_app,'_start_tick',lambda pid:'tick')
    monkeypatch.setattr(writing_app,'health',lambda *a,**k:_fixture_health(tmp_path, state=state, active_turns=0, source_start={'identity': 'different-start'}))
    assert writing_app.status(root=tmp_path,state=state)['status']=='stale-runtime'


def test_actual_health_pid_and_selection_must_match_owned_receipt(tmp_path,monkeypatch):
    _project(tmp_path);state=tmp_path/'state.json'
    record={'schema_version':writing_app.STATE_SCHEMA,'pid':81,'start_tick':'tick','repo_root':str(tmp_path),
        'source_identity':writing_app.source_identity(tmp_path),
        'runtime_selection_start':core_runtime.selection_basis(tmp_path)}
    state.write_text(json.dumps(record))
    monkeypatch.setattr(writing_app,'_start_tick',lambda pid:'tick')
    monkeypatch.setattr(writing_app,'_terminate_owned',lambda *a:pytest.fail('ambiguous producer was killed'))
    for pid in (82,None):
        observed=_fixture_health(tmp_path,state=state);observed['pid']=pid
        monkeypatch.setattr(writing_app,'health',lambda *a,**k:observed)
        result=writing_app.status(root=tmp_path,state=state)
        assert result['health_attribution_unproven'] and result['status']=='stale-runtime'
        with pytest.raises(writing_app.WritingAppError,match='stale-runtime'):
            writing_app.ensure_server(root=tmp_path,state=state)
    observed=_fixture_health(tmp_path,state=state);observed['runtime_selection_start']={'identity':'different'}
    monkeypatch.setattr(writing_app,'health',lambda *a,**k:observed)
    assert writing_app.status(root=tmp_path,state=state)['runtime_selection_changed']
    observed.pop('runtime_start')
    assert writing_app.status(root=tmp_path,state=state)['runtime_selection_unproven']
    assert writing_app.ensure_server(root=tmp_path,state=state,allow_update=False)['disposition']=='reused-current-runtime'


def test_fresh_launch_requires_actual_pid_and_observation_fields(tmp_path,monkeypatch):
    _project(tmp_path);state=tmp_path/'state.json';calls=[]
    class Process:
        pid=81
        def poll(self):return None
    monkeypatch.setattr(writing_app,'_listener_present',lambda *a:False)
    monkeypatch.setattr(writing_app,'_start_tick',lambda pid:'tick')
    monkeypatch.setattr(writing_app,'_start_server',lambda *a: calls.append('spawn') or Process())
    for missing in ('pid','runtime_start','runtime_selection_start','source_start'):
        state.unlink(missing_ok=True);calls.clear()
        observed=_fixture_health(tmp_path,pid=81);observed.pop(missing)
        monkeypatch.setattr(writing_app,'health',lambda *a,**k:observed if calls else None)
        result=writing_app.ensure_server(root=tmp_path,state=state)
        assert result['disposition']=='startup-unproven' and not result['started']
        assert result['process_spawned'] is True
        assert 'runtime_selection_start' not in result['record']


def _stalled_fixture(tmp_path, monkeypatch, *, health_extra=None, active_work=None, events_answer=False, execution_turn='WT-stalled'):
    """A managed receipt for pid 77 at tick 'tick', health declaring one active turn, the turn's execution record running
    in that process, its session (with a native id) in the journal, and the turn's event stream not answering."""
    from laplace.writing import child_hosts, records as writing_records
    _project(tmp_path)
    state = tmp_path / 'state.json'
    record = {'schema_version': writing_app.STATE_SCHEMA, 'pid': 77, 'start_tick': 'tick', 'repo_root': str(tmp_path),
              'source_identity': writing_app.source_identity(tmp_path), 'host': '127.0.0.1', 'port': 8771}
    state.write_text(json.dumps(record))
    writing_records.bank(tmp_path, {'record': 'writing-session', 'id': 'WS-stalled', 'project': 'roadmap', 'provider': 'codex',
                                    'model': 'm', 'effort': 'medium', 'role': 'author', 'native_id': '01a15901-c5a8-7781-9cc6-9cf1de1ea37d'})
    child_hosts._update_child_execution(tmp_path, 'WS-stalled', {'session_id': 'WS-stalled', 'project': 'roadmap', 'state': 'RUNNING',
        'turn_id': execution_turn, 'host': {'pid': 77, 'created_at': 1.0}, 'provider_process': {'pid': 78, 'created_at': 2.0},
        'provider_processes': [{'pid': 78, 'created_at': 2.0}], 'provider_phase': 'codex-serving', 'provider_inference_started': True})
    alive = {'value': True}
    monkeypatch.setattr(writing_app, '_start_tick', lambda pid: 'tick' if alive['value'] and pid == 77 else None)
    work = active_work if active_work is not None else [{'kind': 'turn', 'project': 'roadmap', 'session_id': 'WS-stalled', 'turn_id': 'WT-stalled', 'provider': 'codex'}]
    monkeypatch.setattr(writing_app, 'health', lambda *a, **k: None if not alive['value'] else
                        _fixture_health(tmp_path, state=state, active_turns=1, active_work=work, active_work_omitted=0, **(health_extra or {})))
    monkeypatch.setattr(writing_app, '_turn_events_answer', lambda *a, **k: events_answer)
    monkeypatch.setattr(writing_app, '_listener_present', lambda host, port: alive['value'])
    signals = []
    def kill(pid, sig):
        signals.append((pid, sig)); alive['value'] = False
    monkeypatch.setattr(writing_app.os, 'kill', kill)
    return state, signals


def _recover(tmp_path, state, **overrides):
    arguments = dict(root=tmp_path, state=state, project='roadmap', session_id='WS-stalled', turn_id='WT-stalled',
                     expected_pid=77, expected_start_tick='tick', probe_seconds=0.1, exit_seconds=1.0)
    arguments.update(overrides)
    return writing_app.recover_stalled_turn(**arguments)


def _lifecycle(state):
    path = state.with_name(state.stem + '-lifecycle.jsonl')
    return [json.loads(line) for line in path.read_text().splitlines()] if path.is_file() else []


def test_the_managed_recovery_retires_only_the_exact_stalled_service_and_normal_stop_still_refuses(tmp_path, monkeypatch):
    """LF-R1: normal stop keeps refusing a busy service; the one managed recovery retires it only when the receipt,
    the health-declared single active turn, its running execution in that process and its unanswered event stream
    are exactly the named ones. Intent (with execution, provider and native facts) and outcome are audited, SIGTERM
    goes to that PID only after the receipt is re-proved, and the receipt is removed only after exit and listener
    release. No journal row is written."""
    import signal as signals_module
    from laplace.writing import records as writing_records
    state, signals = _stalled_fixture(tmp_path, monkeypatch)
    journal_before = (tmp_path / 'contract/talk.jsonl').read_bytes()
    assert writing_app.stop(root=tmp_path, state=state)['status'] == 'busy' and signals == [] and state.is_file()
    result = _recover(tmp_path, state)
    assert result['status'] == 'retired-stalled-service' and result['stopped'] is True
    assert signals == [(77, signals_module.SIGTERM)] and not state.exists()
    assert result['native_id'] == '01a15901-c5a8-7781-9cc6-9cf1de1ea37d' and result['execution']['provider_inference_started'] is True
    events = [row['event'] for row in _lifecycle(state)]
    assert events[-2:] == ['stalled-turn-recovery-intent', 'stalled-turn-recovery-retired'] and 'stop-refused-active-work' in events
    assert (tmp_path / 'contract/talk.jsonl').read_bytes() == journal_before


@pytest.mark.parametrize('case', ['changed-tick', 'other-active-work', 'other-turn-declared', 'events-answer', 'execution-other-turn'])
def test_the_managed_recovery_refuses_any_changed_scope_without_signalling(tmp_path, monkeypatch, case):
    fixture = {'other-active-work': {'health_extra': {'active_builds': 1}},
               'other-turn-declared': {'active_work': [{'kind': 'turn', 'project': 'roadmap', 'session_id': 'WS-stalled', 'turn_id': 'WT-other'}]},
               'events-answer': {'events_answer': True}, 'execution-other-turn': {'execution_turn': 'WT-other'}}.get(case, {})
    state, signals = _stalled_fixture(tmp_path, monkeypatch, **fixture)
    result = _recover(tmp_path, state, **({'expected_start_tick': 'other'} if case == 'changed-tick' else {}))
    assert result['status'] == 'refused' and result['stopped'] is False and result['reason']
    assert signals == [] and state.is_file() and _lifecycle(state)[-1]['event'] == 'stalled-turn-recovery-refused'


class _Clock:
    """Deterministic monotonic clock for the reconnect patience; other time functions are real."""
    def __init__(self):
        self.now = 1000.0
    def monotonic(self):
        return self.now
    def sleep(self, seconds):
        self.now += seconds
    def __getattr__(self, name):
        import time as real_time
        return getattr(real_time, name)


def _owned_unanswering(monkeypatch, *, answers_after=None, listener=True):
    # An exact-owned process whose health door has not answered yet; no runtime selection is consumed.
    clock, probes = _Clock(), []
    record = {"schema_version": writing_app.STATE_SCHEMA, "pid": 81, "start_tick": "tick"}
    def fake_status(**kwargs):
        probes.append(kwargs.get("_health_timeout"))
        if answers_after is not None and len(probes) > answers_after:
            return {"status": "running", "source_identity": "src", "health": {"runtime": "writing"}, "record": record}
        return {"status": "unhealthy", "source_identity": "src", "health": None, "record": record}
    monkeypatch.setattr(writing_app, "time", clock)
    monkeypatch.setattr(writing_app, "status", fake_status)
    monkeypatch.setattr(writing_app, "_owned", lambda record: True)
    monkeypatch.setattr(writing_app, "_listener_present", lambda host, port: listener)
    monkeypatch.setattr(writing_app, "_terminate_owned", lambda *a: pytest.fail("owned process was signalled"))
    monkeypatch.setattr(writing_app, "_start_server", lambda *a: pytest.fail("a replacement was started"))
    return clock, probes


def test_owned_listener_with_late_health_is_reused_within_the_reconnect_budget(tmp_path, monkeypatch):
    # Observed 7.7 s health exceeded the fixed 1+3+3 s probes and refused a live owned workspace.
    _project(tmp_path)
    clock, probes = _owned_unanswering(monkeypatch, answers_after=4)
    started = clock.now
    result = writing_app.ensure_server(root=tmp_path, state=tmp_path / "state.json", timeout=12.0, allow_update=False)
    assert result["status"] == "running" and result["disposition"] == "reused" and result["started"] is False
    assert len(probes) == 5 and probes[1:3] == [3.0, 3.0]
    assert clock.now - started <= 12.0


def test_owned_listener_that_never_answers_is_refused_after_the_budget_without_signal(tmp_path, monkeypatch):
    _project(tmp_path)
    clock, probes = _owned_unanswering(monkeypatch)
    started = clock.now
    with pytest.raises(writing_app.WritingAppError) as refused:
        writing_app.ensure_server(root=tmp_path, state=tmp_path / "state.json", timeout=12.0, allow_update=False)
    message = str(refused.value)
    assert "owned but unhealthy" in message and writing_app.HEALTH_PATH in message
    assert "it was not signalled" in message and "Retrying reconnect is safe" in message
    assert len(probes) > 3 and 12.0 <= clock.now - started <= 13.0


def test_owned_process_without_a_listener_keeps_the_original_three_probe_refusal(tmp_path, monkeypatch):
    _project(tmp_path)
    _clock, probes = _owned_unanswering(monkeypatch, listener=False)
    with pytest.raises(writing_app.WritingAppError, match="owned but unhealthy"):
        writing_app.ensure_server(root=tmp_path, state=tmp_path / "state.json", timeout=12.0, allow_update=False)
    assert probes == [None, 3.0, 3.0]
