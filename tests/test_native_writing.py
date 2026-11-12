from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import threading

import pytest

from laplace.desktop import native_writing as native
from laplace.writing import turn_admission
from laplace.web import authoring as authoring_surface, research_surface
from laplace.research import formal_surface
from laplace.writing import turn_jobs
from laplace.research import research_runs   # the owner the code path reads (research family R1)
from laplace.core import checkout


def test_import_is_toolkit_lazy_and_backend_uses_pinned_wrapper(tmp_path):
    assert "gi" not in native.__dict__
    root = tmp_path / "repo"; root.mkdir()
    state = tmp_path / "state.json"

    command = native.backend_command(root, state, "127.0.0.1", 8771, "--no-open")

    assert command == [str(root / "scripts/laplace-python"), "-m", "laplace.desktop.writing_app",
                       "--repo-root", str(root), "--state", str(state),
                       "--host", "127.0.0.1", "--port", "8771", "--no-open"]
    assert not any("chrome" in item.lower() or "firefox" in item.lower() for item in command)
    with pytest.raises(ValueError, match="loopback"):
        native.backend_command(root, state, "example.com", 8771, "--status")
    with pytest.raises(ValueError, match="action"):
        native.backend_command(root, state, "127.0.0.1", 8771, "--launch-browser")


def test_backend_requires_successful_object_status(monkeypatch, tmp_path):
    class Result:
        returncode = 0
        stdout = '{"status":"running"}'
        stderr = ""

    monkeypatch.setattr(native.subprocess, "run", lambda *args, **kwargs: Result())
    assert native.backend(tmp_path, tmp_path / "state", "127.0.0.1", 8771,
                          "--status") == {"status": "running"}
    Result.stdout = "[]"
    with pytest.raises(RuntimeError, match="invalid status"):
        native.backend(tmp_path, tmp_path / "state", "127.0.0.1", 8771, "--status")
    Result.returncode, Result.stderr = 2, "owned backend refused"
    with pytest.raises(RuntimeError, match="owned backend refused"):
        native.backend(tmp_path, tmp_path / "state", "127.0.0.1", 8771, "--stop")


def test_application_identity_navigation_and_busy_state_are_bounded(tmp_path):
    first = native.application_id(tmp_path, tmp_path / "state-a")
    assert first == native.application_id(tmp_path, tmp_path / "state-a")
    assert first != native.application_id(tmp_path, tmp_path / "state-b")
    assert first.startswith("org.laplace.Writing.p")

    origin = "http://127.0.0.1:8771"
    assert native.local_uri(origin + "/project?workspace=writing", origin)
    assert not native.local_uri("http://127.0.0.1:8772/project", origin)
    assert not native.local_uri("https://example.org/paper", origin)
    assert not native.local_uri("file:///tmp/paper.pdf", origin)
    assert not native.local_uri("http://127.0.0.1:bad/project", origin)
    reason = native.busy_reason({"health": {
        "active_turns": 1, "active_previews": 2, "active_builds": 1,
        "active_runs": 1, "active_proof_checks": 2,"active_mutations":1}}, downloads=3)
    assert reason == ("1 live session, 2 document previews, 1 PDF build, "
                      "1 numerical producer run, 2 formal proof checks, 1 project update, 3 downloads")
    assert native.busy_reason({"health": {}}, downloads=0) == ""


def test_health_reports_supervised_runs_and_live_proof_checks(tmp_path, monkeypatch):
    from laplace.manuscript import manuscript_figure_preview
    monkeypatch.setenv("LAPLACE_WRITING_APP", "1")
    monkeypatch.setattr(checkout, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(research_runs, "active_runs", lambda root: [
        {"id": "run-one", "project": "fixture", "pid": 123}])
    monkeypatch.setattr(formal_surface, "active_checks", lambda: 2)
    monkeypatch.setattr(manuscript_figure_preview, "active_renders", lambda: 1)

    status, _, body = authoring_surface.handle("/authoring/health", {}, "GET", b"")
    health = json.loads(body)

    assert status == 200
    assert health["active_runs"] == 1
    assert health["active_proof_checks"] == 2
    assert health["active_previews"] >= 1
    assert health["active_work"]==[{"kind":"research-run","project":"fixture",
        "session_id":None,"turn_id":None,"run_id":"run-one",
        "label":"Research run run-one","provider":None}]
    assert health["active_work_omitted"]==0
    assert health["schema_version"] == "laplace.writing-health/2"


def test_window_state_restores_only_local_uri_and_clamps_geometry(tmp_path):
    state = tmp_path / "writing.json"
    origin = "http://127.0.0.1:8771"
    native.write_ui_state(state, 5000, 20, origin + "/walk?corpus=p", origin)
    restored = native.read_ui_state(state, origin)
    assert restored == {"width": 3000, "height": 500,
                        "uri": origin + "/project?workspace=writing&view=manuscript&corpus=p"}

    native.write_ui_state(state, 1100, 700, "https://example.org", origin)
    restored = native.read_ui_state(state, origin)
    assert restored["uri"] == origin + "/project?workspace=writing"
    native.ui_state_path(state).write_text("not json")
    assert native.read_ui_state(state, origin) == {
        "width": 1280, "height": 900,
        "uri": origin + "/project?workspace=writing"}


def test_connection_recovery_is_single_flight_bounded_and_manually_retryable():
    gate = native.RecoveryGate()
    assert gate.begin(0, failed=True)
    assert not gate.begin(3, manual=True)
    gate.finish()
    assert not gate.begin(1, failed=True)
    assert gate.begin(3, failed=True)
    gate.finish()
    assert not gate.begin(6, failed=True)
    assert gate.begin(6, manual=True, failed=True)
    gate.finish(); gate.ready()
    assert gate.begin(9, failed=True)

def test_backend_recovery_does_not_reload_a_healthy_page():
    assert not native.should_reload({'started': True})
    assert native.should_reload({'started': True}, failed_page=True)
    assert native.should_reload({'started': False}, requested=True)

def test_healthy_focus_check_does_not_reconnect_the_conversation():
    reused = {'status': 'running', 'started': False, 'disposition': 'reused'}
    assert not native.should_notify_reconnected(reused)
    assert native.should_notify_reconnected(reused, failed=True)
    assert native.should_notify_reconnected({'started': True})
    assert not native.should_notify_reconnected({'started': True}, reloaded=True)
    assert not native.should_notify_reconnected(reused, failed=True, reloaded=True)

def test_direct_open_graph_back_state():
    assert not native.back_enabled(False, False)

def test_native_bridge_declares_connection_and_reconnect_events():
    source = Path(native.__file__).read_text()
    assert 'laplace-workspace-connection' in source
    assert 'laplace-workspace-reconnected' in source
    assert 'ensure_connection(failed=True)' in source
    assert native.back_enabled(True, False)
    assert not native.back_enabled(False, False)


def test_viewer_graphics_compatibility_is_scoped_and_overridable():
    assert native.rendering_mode({'XDG_SESSION_TYPE':'x11'}, True) == 'software'
    assert native.rendering_mode({'XDG_SESSION_TYPE':'wayland'}, True) == 'auto'
    assert native.rendering_mode({'XDG_SESSION_TYPE':'x11'}, False) == 'auto'
    assert native.rendering_mode({'XDG_SESSION_TYPE':'x11','LAPLACE_WRITING_RENDERER':'accelerated'}, True) == 'accelerated'
    with pytest.raises(ValueError, match='RENDERER'):
        native.rendering_mode({'LAPLACE_WRITING_RENDERER':'invalid'}, True)


@pytest.mark.skipif(not Path("/usr/bin/python3").is_file(), reason="the OS toolkit interpreter is absent")
def test_launcher_native_command_starts_under_isolated_os_python_from_any_directory(tmp_path):
    # The exact command the managed app launches, run by the OS interpreter (-I -B) from an unrelated directory with
    # no display: the direct script must bootstrap without Laplace on its path. --help exits inside argparse, before
    # any toolkit, backend or state is touched.
    from laplace.desktop import writing_app
    command = writing_app.native_command(state=tmp_path / "state.json") + ["--help"]
    elsewhere = tmp_path / "elsewhere"; elsewhere.mkdir()
    result = subprocess.run(command, cwd=elsewhere, capture_output=True, text=True, timeout=15,
                            env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "COLUMNS": "4096"})

    assert command[:3] == ["/usr/bin/python3", "-I", "-B"]
    assert result.returncode == 0, result.stderr
    assert result.stderr == "" and result.stdout.startswith("usage:")
    assert native.SOURCE_TREE == checkout.source_tree()
    assert "(default: %s)" % checkout.source_tree() in result.stdout


@pytest.mark.skipif(not Path("/usr/bin/python3").is_file() or not os.environ.get("DISPLAY"),
                    reason="system GTK display is unavailable")
def test_installed_system_runtime_probe_has_webkit_and_needs_no_browser(tmp_path):
    script = Path(native.__file__).resolve()
    result = subprocess.run([
        "/usr/bin/python3", "-I", "-B", str(script),
        "--repo-root", str(Path(__file__).resolve().parents[1]),
        "--state", str(tmp_path / "state.json"), "--check-runtime"],
        capture_output=True, text=True, timeout=15)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["runtime"] == "GTK + WebKitGTK"
    assert payload["gtk"] == 3 and payload["display_available"] is True
    assert payload["browser_required"] is False
    assert tuple(map(int, payload["webkit"].split("."))) >= (2, 40, 0)


def test_saved_graph_entry_migrates_to_recursive_workspace():
    origin='http://127.0.0.1:8771'
    assert native.workspace_uri(origin+'/conceptric?corpus=p&node=def%3Ax',origin)==origin+'/project?workspace=writing&view=structure&corpus=p&structure=concept&node=def%3Ax'
    assert native.workspace_uri(origin+'/project?corpus=p',origin)==origin+'/project?corpus=p'


def test_focus_and_navigation_reconnect_without_deploying_source_edits(tmp_path):
    assert native.connection_action()=='--reconnect'
    assert native.connection_action(manual=True)=='--reconnect', 'Projects navigation is not an update request'
    assert native.connection_action(reload=True)=='--reconnect', 'automatic load-failure recovery is not an update request'
    assert native.connection_action(manual=True,reload=True)=='--update'
    command=native.backend_command(tmp_path,tmp_path/'state','127.0.0.1',8771,native.connection_action())
    assert command[-1]=='--reconnect'


def test_turn_construction_is_visible_to_lifecycle_health(monkeypatch,tmp_path):
    entered=threading.Event();release=threading.Event()
    def constructing(root,payload,**_admission):
        entered.set();assert release.wait(2);return {'turn_id':'WT-ready'}
    monkeypatch.setattr(turn_admission, '_start_turn',constructing)
    worker=threading.Thread(target=lambda:turn_admission.start_turn(tmp_path,{
        "project":"fixture","session_id":"WS-live","provider":"codex",
        "text":"Continue the bounded correction."}))
    worker.start();assert entered.wait(1)
    assert turn_jobs.active_turn_count()==1
    assert turn_jobs.active_work_projection()[0]==[{
        "kind":"turn-start","project":"fixture","session_id":"WS-live","turn_id":None,"work_id":None,
        "label":"Continue the bounded correction.","provider":"codex"}]
    release.set();worker.join(2)
    assert turn_jobs.active_turn_count()==0


def test_active_work_navigation_uses_exact_project_and_conversation_without_supplied_urls():
    from urllib.parse import urlsplit, parse_qs
    value = {'health': {'active_work': [
        {'kind': 'turn', 'project': 'book & notes', 'session_id': 'WS-exact',
         'label': 'Finish chapter two', 'provider': 'claude', 'url': 'https://untrusted.invalid/'},
        {'kind': 'run', 'project': 'book', 'run_id': 'run-exact'},
        {'label': 'No project identity'}]}}
    links = native.active_work_links(value, 'http://127.0.0.1:8771')
    assert len(links) == 2
    assert links[0]['label'] == 'book & notes · Finish chapter two · claude'
    assert links[0]['action'] == 'Open conversation'
    assert parse_qs(urlsplit(links[0]['uri']).query) == {
        'workspace': ['writing'], 'corpus': ['book & notes'], 'view': ['overview'],
        'conversation': ['open'], 'session': ['WS-exact']}
    assert links[1]['action'] == 'Open project'
    assert 'view=research' in links[1]['uri']


@pytest.fixture
def desktop_close(monkeypatch, tmp_path, request):
    """Drive the real inner application without a GTK window or engine process."""
    from types import SimpleNamespace as NS
    dialogs = []
    class Application:
        def __init__(self, **kwargs): self.exited = False; self.application_kwargs = kwargs
        def run(self, argv): return self
        def quit(self): self.exited = True
    class Button:
        @classmethod
        def new_with_label(cls, label): return cls()
        def set_tooltip_text(self, text): pass
        def connect(self, *args): pass
        def get_child(self): return NS(set_line_wrap=lambda value: None, set_max_width_chars=lambda value: None)
    class Scroll:
        def set_policy(self, *args): pass
        def set_max_content_height(self, value): pass
        def set_propagate_natural_height(self, value): pass
        def add(self, child): pass
    class Dialog:
        def __init__(self, **kwargs): self.kwargs = kwargs; self.buttons = []; dialogs.append(self)
        def format_secondary_text(self, text): self.detail = text
        def add_button(self, text, value): self.buttons.append((text, value))
        def set_default_response(self, value): self.default = value
        def get_content_area(self): return NS(pack_start=lambda *args: None)
        def show_all(self): pass
        def run(self): return app.dialog_response
        def destroy(self): pass
    gtk = NS(Application=Application, MessageDialog=Dialog, Button=Button,
             ScrolledWindow=Scroll, PolicyType=NS(NEVER=0,AUTOMATIC=1),
             Box=lambda **kwargs: NS(pack_start=lambda *args: None), Orientation=NS(VERTICAL=1),
             Label=lambda **kwargs: NS(),
             MessageType=NS(INFO=1), ButtonsType=NS(NONE=0), ResponseType=NS(CANCEL=-6, ACCEPT=-3))
    glib = NS(PRIORITY_DEFAULT=0, unix_signal_add=lambda *args: None)
    monkeypatch.setattr(native, 'load_toolkit', lambda: (None, NS(ApplicationFlags=NS(DEFAULT_FLAGS=0)), glib, gtk, None))
    separate = getattr(request, 'param', {}).get('separate', False)
    locations = {}
    root = tmp_path
    if separate:
        root = checkout.source_tree()
        workspace = tmp_path / 'data'; workspace.mkdir()
        (workspace / 'registry_projects.json').write_text('{"projects": []}')
        (workspace / 'profiles').mkdir()
        locations = {'workspace_root': workspace, 'engine_state': tmp_path / 'engine',
                     'session_workspaces': tmp_path / 'sessions'}
    state = tmp_path / 'viewer.json'
    app = native.run(root, state, **locations)
    app.test_locations, app.test_root, app.test_state = locations, root, state
    app.presentations = []
    app.window = NS(get_size=lambda: (1200, 800), destroy=lambda: None, present=lambda: app.presentations.append('present'))
    app.loaded_uris = []; app.try_close_count = 0
    def try_close(): app.try_close_count += 1
    app.view = NS(try_close=try_close, get_uri=lambda: 'http://127.0.0.1:8771/project?corpus=book', load_uri=app.loaded_uris.append)
    app.started = True; app.starting = False; app.dialog_response = -6; app.actions = []; app.messages = []; app.dialogs = dialogs; app.backend_calls = []
    app.notices = []
    app.notice = NS(set_text=app.notices.append, show=lambda: None, hide=lambda: None)
    app.retry_button = NS(show=lambda: None, hide=lambda: None)
    app.view.evaluate_javascript = lambda *args: None
    app.message = lambda title, detail: app.messages.append((title, detail))
    app.health = {'health': {}}
    def backend(*args, **kwargs):
        app.actions.append(args[-1]); app.backend_calls.append((args,kwargs))
        if not separate: assert args[-1] == '--status'
        return app.health
    monkeypatch.setattr(native, 'backend', backend)
    def background(work, finish):
        try: value = work()
        except Exception as error: finish(None, str(error))
        else: finish(value, None)
    app.background = background
    return app


def test_idle_close_obeys_webkit_unsaved_guard_then_only_detaches(desktop_close):
    app = desktop_close
    assert app.request_close() is True
    assert app.try_close_count == 1
    assert app.actions == [] and not app.exited  # WebKit may refuse close.
    app.check_close()  # Only the WebKit close event reaches this point.
    assert app.exited and app.window is None
    assert app.actions == ['--status'] and app.dialogs == []
    app.close_status({'health': {}}, None)  # An obsolete completion is harmless.


def test_active_close_can_stay_navigate_to_exact_session_or_detach(desktop_close):
    app = desktop_close
    app.health = {'health': {'active_turns': 1, 'active_work': [
        {'kind': 'turn', 'project': 'book', 'session_id': 'WS-active', 'label': 'Review chapter'}]}}
    app.check_close()
    assert not app.exited and not app.closing
    assert 'keeps the research engine and its work running' in app.dialogs[-1].detail
    assert ('Close window (keep running)', -3) in app.dialogs[-1].buttons
    app.dialog_response = 1000; app.check_close()
    assert not app.exited and 'session=WS-active' in app.loaded_uris[-1]
    app.dialog_response = -3; app.check_close()
    assert app.exited and app.actions == ['--status'] * 3


def test_unknown_engine_state_does_not_trap_the_viewer(desktop_close):
    app = desktop_close; app.dialog_response = -3; app.closing = True
    app.close_status(None, 'Status request timed out')
    assert app.exited and app.actions == []
    assert 'Status request timed out' in app.dialogs[-1].detail


def test_window_owned_downloads_remain_guarded_before_and_after_status(desktop_close):
    app = desktop_close; app.downloads.add('download')
    app.check_close()
    assert not app.exited and app.actions == []
    app.closing = True; app.close_status({'health': {}}, None)
    assert not app.exited and not app.closing
    assert len(app.messages) == 2


@pytest.mark.parametrize('uri,kind,gesture,launch_error,expected_default,expected_launches', [
    ('http://127.0.0.1:8771/project?node=res%3Aclaim', 'navigation', True, False, True, 0),
    ('http://127.0.0.1:8771/project?node=res%3Aclaim', 'new-window', True, False, False, 1),
    ('http://127.0.0.1:8771/project?node=res%3Aclaim', 'new-window', False, False, False, 0),
    ('http://127.0.0.1:8771/project?node=res%3Aclaim', 'new-window', True, True, False, 1),
    ('file:///tmp/private.tex', 'new-window', True, False, False, 0),
    ('javascript:alert(1)', 'new-window', True, False, False, 0),
    ('https://example.org/paper', 'navigation', True, False, False, 1),
    ('mailto:reader@example.org', 'new-window', True, False, False, 1),
    ('https://example.org/paper', 'navigation', False, False, False, 0),
])
def test_actual_navigation_policy_preserves_embedded_view_for_separate_links(
        uri, kind, gesture, launch_error, expected_default, expected_launches):
    # Execute the real nested callback without starting GTK or an application.
    import ast
    from types import SimpleNamespace
    from urllib.parse import urlsplit
    tree = ast.parse(Path(native.__file__).read_text())
    callback = next(node for node in ast.walk(tree)
                    if isinstance(node, ast.FunctionDef) and node.name == 'decide_policy')
    launches, loads, notices, ignored = [], [], [], []
    class HandlerError(Exception):
        pass
    def launch(target, context):
        launches.append((target, context))
        if launch_error:
            raise HandlerError('No registered browser')
    policy = SimpleNamespace(NAVIGATION_ACTION='navigation', NEW_WINDOW_ACTION='new-window')
    namespace = {'WebKit2':SimpleNamespace(PolicyDecisionType=policy),
        'local_uri':native.local_uri, 'origin':'http://127.0.0.1:8771',
        'Gio':SimpleNamespace(AppInfo=SimpleNamespace(launch_default_for_uri=launch)),
        'GLib':SimpleNamespace(Error=HandlerError), 'urlsplit':urlsplit}
    exec(compile(ast.Module(body=[callback], type_ignores=[]), native.__file__, 'exec'), namespace)
    action = SimpleNamespace(get_request=lambda:SimpleNamespace(get_uri=lambda:uri),
                             is_user_gesture=lambda:gesture)
    decision = SimpleNamespace(get_navigation_action=lambda:action,
                               ignore=lambda:ignored.append(True))
    view = SimpleNamespace(load_uri=lambda target:loads.append(target))
    result = namespace['decide_policy'](SimpleNamespace(message=lambda *args:notices.append(args)),
                                        view, decision, kind)
    assert result is (not expected_default)
    assert len(launches) == expected_launches
    if launches:
        assert launches == [(uri, None)]
    assert loads == []  # A failed/no-gesture separate link never falls back into this view.
    assert ignored == ([] if expected_default else [True])
    assert notices == ([('Could not open this link', 'No registered browser')] if launch_error else [])
