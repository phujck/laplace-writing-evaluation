"""Standalone Linux writing application using the installed GTK/WebKit runtime.

Run with system Python for GI. The research engine always runs through the
repository's pinned Python wrapper; no scientific packages enter this process.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import signal
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit, parse_qs, urlencode

# The OS toolkit interpreter runs this file directly (`-I`, no Laplace on sys.path), so it imports nothing from
# Laplace: the checkout is named from this file's own location, the same tree laplace.core.checkout.source_tree()
# names (src/laplace/desktop/native_writing.py -> the directory holding src/).
SOURCE_TREE = Path(__file__).resolve().parents[3]


def managed_selection(root, state=None, *, workspace_root=None, engine_state=None, session_workspaces=None):
    """Use the code owner's stdlib selector even under OS Python -I (no Laplace import)."""
    resolver = runpy.run_path(str(Path(root) / 'src/laplace/desktop/managed_homes.py'))['resolve']
    return resolver(root, state=state, workspace_root=workspace_root,
                    engine_state=engine_state, session_workspaces=session_workspaces)


def viewer_identity(root, homes, host, port):
    return runpy.run_path(str(Path(root) / 'src/laplace/desktop/managed_homes.py'))['viewer_identity'](homes, host, port)


def backend_command(root, state, host, port, action, *, workspace_root=None,
                    engine_state=None, session_workspaces=None):
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("The desktop research engine must use loopback.")
    if action not in {"--no-open", "--reconnect", "--update", "--status", "--stop"}:
        raise ValueError("Unknown desktop engine action.")
    if workspace_root is None and (engine_state is not None or session_workspaces is not None):
        raise ValueError('Engine/session selection requires explicit --workspace-root')
    selected = managed_selection(root, state, workspace_root=workspace_root,
        engine_state=engine_state, session_workspaces=session_workspaces) if workspace_root is not None else None
    if selected:
        root, state = selected['code_root'], selected['receipt']
    command = [str(Path(root) / "scripts/laplace-python"), "-m", "laplace.desktop.writing_app",
            "--repo-root", str(root), "--state", str(state), "--host", host,
            "--port", str(int(port))]
    if selected:
        for flag, key in (('--workspace-root','workspace_root'),('--engine-state','engine_state'),('--session-workspaces','session_workspaces')):
            command.extend((flag, selected[key]))
    return command + [action]


def backend(root, state, host, port, action, **locations):
    result = subprocess.run(backend_command(root, state, host, port, action, **locations),
                            cwd=root, capture_output=True, text=True, timeout=25)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip() or "The research engine could not start.")
    value = json.loads(result.stdout)
    if not isinstance(value, dict):
        raise RuntimeError("The research engine returned an invalid status payload.")
    if locations.get('workspace_root') is not None:
        expected = managed_selection(root, state, **locations)
        observed = value.get('managed_homes') or {}
        if any(observed.get(key) != expected[key] for key in (
                'separate','code_root','workspace_root','receipt','engine_state',
                'session_workspaces','native_profile')):
            raise RuntimeError('The research engine returned another managed home selection; this window was not retargeted.')
        live = value.get('health')
        if (value.get('status') == 'selection-mismatch' or value.get('health_attribution_unproven')
                or live is not None and any((live.get('managed_homes') or {}).get(key) != expected[key]
                    for key in ('code_root','workspace_root','receipt','engine_state','session_workspaces'))):
            raise RuntimeError('The observed service does not belong to this workspace; this window was not retargeted.')
    return value


def application_id(root, state, *, workspace_root=None, engine_state=None,
                   session_workspaces=None, host='127.0.0.1', port=8771):
    if workspace_root is not None:
        homes = managed_selection(root, state, workspace_root=workspace_root,
            engine_state=engine_state, session_workspaces=session_workspaces)
        return viewer_identity(root, homes, host, port)
    identity = str(Path(root).resolve()) + "\0" + str(Path(state).resolve())
    return "org.laplace.Writing.p" + hashlib.sha256(identity.encode()).hexdigest()[:16]


def local_uri(uri, origin):
    try:
        candidate, expected = urlsplit(uri), urlsplit(origin)
        return (candidate.scheme, candidate.hostname, candidate.port) == (expected.scheme, expected.hostname, expected.port)
    except ValueError:
        return False


def workspace_uri(uri, origin):
    """Upgrade saved entry points without reopening a retired front end."""
    if not local_uri(uri, origin):
        return origin + "/project?workspace=writing"
    parsed = urlsplit(uri)
    legacy = {"/walk": "manuscript", "/artefact": "manuscript",
              "/conceptric": "structure", "/storyboard": "structure",
              "/assets": "presentation", "/references": "research"}
    if parsed.path not in legacy:
        return uri
    query = parse_qs(parsed.query)
    project = (query.get("corpus") or query.get("project") or [""])[0]
    params = {"workspace": "writing", "view": legacy[parsed.path]}
    if project:
        params["corpus"] = project
    if parsed.path == "/conceptric":
        params["structure"] = "concept"
        if query.get("node"):
            params["node"] = query["node"][0]
    return origin + "/project?" + urlencode(params)


def busy_reason(result, downloads=0):
    health = result.get("health") or {}
    work = [("live session", health.get("active_turns", 0)),
            ("document preview", health.get("active_previews", 0)),
            ("PDF build", health.get("active_builds", 0)),
            ("numerical producer run", health.get("active_runs", 0)),
            ("formal proof check", health.get("active_proof_checks", 0)),
            ("project update", health.get("active_mutations", 0)),
            ("download", downloads)]
    return ", ".join(f"{count} {label}{'s' if count != 1 else ''}" for label, count in work if count)


def active_work_links(result, origin):
    """Navigation from the health owner's bounded identities, never supplied URLs."""
    rows = []
    for item in (result.get("health") or {}).get("active_work", [])[:16]:
        if not isinstance(item, dict):
            continue
        project = item.get("project")
        if not isinstance(project, str) or not project or len(project) > 200:
            continue
        session = item.get("session_id")
        params = {"workspace": "writing", "corpus": project}
        if isinstance(session, str) and session and len(session) <= 200:
            params.update(view="overview", conversation="open", session=session)
        else:
            params["view"] = "research" if item.get("kind") in {"run", "research-run"} else "overview"
        label = " ".join(str(item.get("label") or item.get("request_label") or
                             item.get("run_id") or "Work in progress").split())[:180]
        provider = " ".join(str(item.get("provider") or "").split())[:40]
        rows.append({"label": f"{project} · {label}" + (f" · {provider}" if provider else ""),
                     "action": "Open conversation" if "session" in params else "Open project",
                     "uri": origin + "/project?" + urlencode(params)})
    return rows

def should_reload(result, *, failed_page=False, requested=False):
    """Never discard a healthy loaded WebKit page merely because recovery started it."""
    return bool(failed_page or requested)

def should_notify_reconnected(result, *, failed=False, reloaded=False):
    """A healthy focus check must not reset the live conversation controls."""
    return not reloaded and bool(failed or result.get('started'))


def connection_action(*, manual=False, reload=False):
    """Focus/navigation may reconnect; only an explicit reload requests an update."""
    return '--update' if manual and reload else '--reconnect'

def back_enabled(graph_back, history_back): return bool(graph_back or history_back)


def ui_state_path(state, *, homes=None):
    if homes and homes['separate']:
        return Path(homes['native_profile']) / 'window.json'
    return Path(state).with_name(Path(state).stem + "-window.json")


def read_ui_state(state, origin, *, homes=None):
    try:
        value = json.loads(ui_state_path(state, homes=homes).read_text())
        return {"width": max(700, min(3000, int(value.get("width", 1280)))),
                "height": max(500, min(2200, int(value.get("height", 900)))),
                "uri": workspace_uri(str(value.get("uri", "")), origin)}
    except (OSError, ValueError, TypeError):
        return {"width": 1280, "height": 900, "uri": origin + "/project?workspace=writing"}


def write_ui_state(state, width, height, uri, origin, *, homes=None):
    target = ui_state_path(state, homes=homes)
    target.parent.mkdir(parents=True, exist_ok=True)
    value = {"width": width, "height": height,
             "uri": uri if local_uri(uri, origin) else origin + "/project?workspace=writing"}
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(value) + "\n")
    temporary.replace(target)


def acquire_native_profile(homes):
    """Keep an existing viewer/profile untouched, including across code locations."""
    import fcntl
    profile = Path(homes['native_profile'])
    profile.mkdir(parents=True, exist_ok=True)
    handle = (profile / 'viewer.lock').open('a+b')
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise RuntimeError('This workspace native profile is already in use. Close its window before reopening from another code location.') from exc
    return handle


def load_toolkit():
    import gi
    gi.require_version("Gdk", "3.0")
    gi.require_version("Gtk", "3.0")
    gi.require_version("WebKit2", "4.1")
    from gi.repository import Gdk, Gio, GLib, Gtk, WebKit2
    return Gdk, Gio, GLib, Gtk, WebKit2


def rendering_mode(environ=None, nvidia_present=None):
    """Keep the compatibility choice local to this viewer, not the GPU engine."""
    env = os.environ if environ is None else environ
    selected = env.get("LAPLACE_WRITING_RENDERER", "auto")
    if selected not in {"auto", "software", "accelerated"}:
        raise ValueError("LAPLACE_WRITING_RENDERER must be auto, software or accelerated")
    nvidia = Path('/proc/driver/nvidia/version').exists() if nvidia_present is None else nvidia_present
    if selected == 'auto' and env.get('XDG_SESSION_TYPE') == 'x11' and nvidia:
        return 'software'
    return selected


class RecoveryGate:
    """Single-flight, bounded automatic recovery; manual retry starts a new attempt."""
    def __init__(self):
        self.running = False
        self.attempts = 0
        self.last_start = -100.0

    def begin(self, now, *, manual=False, failed=False):
        if self.running or (not manual and now - self.last_start < 2):
            return False
        if failed and not manual and self.attempts >= 2:
            return False
        if manual:
            self.attempts = 0
        if failed:
            self.attempts += 1
        self.running = True
        self.last_start = now
        return True

    def finish(self):
        self.running = False

    def ready(self):
        self.attempts = 0


def run(root, state, host="127.0.0.1", port=8771, *, workspace_root=None,
        engine_state=None, session_workspaces=None):
    homes = managed_selection(root, state, workspace_root=workspace_root,
        engine_state=engine_state, session_workspaces=session_workspaces) if workspace_root is not None else None
    if workspace_root is None and (engine_state is not None or session_workspaces is not None):
        raise ValueError('Engine/session selection requires explicit --workspace-root')
    if homes:
        root, state = homes['code_root'], homes['receipt']
    identity = viewer_identity(root, homes, host, port) if homes else application_id(root, state)
    Gdk, Gio, GLib, Gtk, WebKit2 = load_toolkit()
    root, state = Path(root).resolve(), Path(state).resolve()
    locations = {key: homes[key] for key in ('workspace_root','engine_state','session_workspaces')} if homes else {}
    profile_lock = None
    def release_profile():
        nonlocal profile_lock
        if profile_lock is not None:
            profile_lock.close(); profile_lock = None
    def engine(action):
        nonlocal profile_lock
        if homes and profile_lock is None:
            profile_lock = acquire_native_profile(homes)
        return backend(root, state, host, port, action, **locations) if homes else backend(root, state, host, port, action)
    origin = f"http://{'['+host+']' if ':' in host else host}:{port}"
    settings = read_ui_state(state, origin, homes=homes)

    class WritingApplication(Gtk.Application):
        def __init__(self):
            super().__init__(application_id=identity, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
            self.window = None
            self.view = None
            self.started = False
            self.starting = True
            self.closing = False
            self.close_pending = False
            self.downloads = set()
            self.recovery = RecoveryGate()
            self.load_error = False
            self.graph_back = False
            self.update_notice = ""
            self.last_uri = settings['uri']

        def do_activate(self):
            if self.window:
                self.window.present()
                self.ensure_connection()
                return
            Gtk.Settings.get_default().set_property("gtk-application-prefer-dark-theme", True)
            self.window = Gtk.ApplicationWindow(application=self, title="Laplace Writing")
            self.window.set_wmclass("LaplaceWritingApp", "LaplaceWritingApp")
            self.window.set_icon_name("laplace-writing")
            self.window.set_default_size(settings["width"], settings["height"])
            self.window.connect("delete-event", self.request_close)
            self.window.connect('focus-in-event', lambda *_: self.ensure_connection() or False)
            header = Gtk.HeaderBar(title="Laplace Writing", subtitle="Research · evidence · manuscript")
            header.set_show_close_button(True)
            self.window.set_titlebar(header)
            self.back_button = Gtk.Button.new_from_icon_name("go-previous-symbolic", Gtk.IconSize.BUTTON)
            self.back_button.set_tooltip_text("Back")
            self.back_button.connect("clicked", self.go_back)
            header.pack_start(self.back_button)
            home = Gtk.Button.new_with_label("Projects")
            home.set_tooltip_text("Research and manuscript library")
            home.connect("clicked", lambda _: self.ensure_connection(manual=True, uri=origin + "/project?workspace=writing"))
            header.pack_start(home)
            refresh = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
            refresh.set_tooltip_text("Reload this workspace")
            refresh.connect("clicked", lambda _: self.ensure_connection(manual=True, reload=True))
            header.pack_end(refresh)
            self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            self.notice = Gtk.Label(label="Starting your research workspace…")
            self.notice.set_margin_top(5); self.notice.set_margin_bottom(5)
            self.box.pack_start(self.notice, False, False, 0)
            self.retry_button = Gtk.Button.new_with_label('Reconnect to workspace')
            self.retry_button.connect('clicked', lambda _: self.ensure_connection(manual=True, reload=True))
            self.box.pack_start(self.retry_button, False, False, 0)
            self.window.add(self.box)
            self.window.show_all()
            self.retry_button.hide()
            self.background(lambda: engine("--no-open"), self.engine_ready)

        def background(self, work, finish):
            def worker():
                try:
                    result, error = work(), None
                except Exception as exc:
                    result, error = None, str(exc)
                GLib.idle_add(finish, result, error)
            threading.Thread(target=worker, daemon=True).start()

        def engine_ready(self, result, error):
            self.starting = False
            if error:
                if self.close_pending:
                    self.window.destroy(); self.window = None; self.quit()
                    return False
                self.notice.set_text("The workspace could not start.")
                self.notice.set_text("Could not start the workspace: " + error)
                self.retry_button.show()
                return False
            self.started = True
            self.update_notice = result.get("update_error") or ""
            profile = Path(homes['native_profile']) if homes else state.parent / "writing-native"
            manager = WebKit2.WebsiteDataManager(base_data_directory=str(profile / "data"),
                                                 base_cache_directory=str(profile / "cache"))
            self.context = WebKit2.WebContext.new_with_website_data_manager(manager)
            self.context.set_cache_model(WebKit2.CacheModel.DOCUMENT_VIEWER)
            self.context.connect("download-started", self.download_started)
            self.manager = WebKit2.UserContentManager()
            self.manager.register_script_message_handler("laplaceNav")
            self.manager.register_script_message_handler("laplaceConnection")
            self.manager.connect("script-message-received::laplaceNav", self.navigation_message)
            self.manager.connect("script-message-received::laplaceConnection", self.connection_message)
            bridge = "window.addEventListener('laplace-workspace-navigation',e=>{const h=window.webkit&&window.webkit.messageHandlers&&window.webkit.messageHandlers.laplaceNav;if(h)h.postMessage(!!(e.detail&&e.detail.graphBack));});window.addEventListener('laplace-workspace-connection',e=>{const h=window.webkit&&window.webkit.messageHandlers&&window.webkit.messageHandlers.laplaceConnection;if(h)h.postMessage(!!(e.detail&&e.detail.available));});"
            self.manager.add_script(WebKit2.UserScript.new(bridge, WebKit2.UserContentInjectedFrames.TOP_FRAME,
                                                           WebKit2.UserScriptInjectionTime.START, [], []))
            # WebKitGTK 4.1 exposes these as construct properties; the combined
            # convenience constructor is not available on the installed typelib.
            self.view = WebKit2.WebView(web_context=self.context, user_content_manager=self.manager)
            web_settings = self.view.get_settings()
            renderer = rendering_mode()
            if renderer == 'software':
                web_settings.set_hardware_acceleration_policy(WebKit2.HardwareAccelerationPolicy.NEVER)
            elif renderer == 'accelerated':
                web_settings.set_hardware_acceleration_policy(WebKit2.HardwareAccelerationPolicy.ALWAYS)
            web_settings.set_enable_developer_extras(False)
            web_settings.set_media_playback_requires_user_gesture(True)
            self.view.connect("decide-policy", self.decide_policy)
            self.view.connect("load-changed", self.loaded)
            self.view.connect("load-failed", self.load_failed)
            self.view.connect("close", lambda _: self.check_close())
            self.view.connect("web-process-terminated", self.process_terminated)
            self.box.pack_start(self.view, True, True, 0)
            self.view.show()
            self.view.load_uri(settings["uri"])
            print(json.dumps({"desktop":"window-open", "pid":os.getpid(),
                              "engine_pid":result.get("record", {}).get("pid"),
                              "runtime":"GTK/WebKitGTK", "renderer":renderer, "browser_required":False}), flush=True)
            if self.close_pending:
                self.check_close()
            return False

        def loaded(self, view, event):
            self.back_button.set_sensitive(self.graph_back or view.can_go_back())
            if event == WebKit2.LoadEvent.STARTED:
                self.load_error = False
            if event == WebKit2.LoadEvent.FINISHED and not self.load_error:
                self.last_uri = view.get_uri()
                if self.update_notice:
                    self.notice.set_text(self.update_notice + ". The existing workspace is still running.")
                    self.notice.show()
                else:
                    self.notice.hide()
                self.retry_button.hide()
                self.window.set_title("Laplace Writing")
                print(json.dumps({"desktop":"view-loaded", "uri":view.get_uri(),
                                  "title":view.get_title()}), flush=True)
                self.report_readiness(view, view.get_uri(), 0)

        def navigation_message(self, _manager, message):
            try: self.graph_back = message.get_js_value().to_boolean()
            except GLib.Error: self.graph_back = False
            if self.view and self.back_button:
                self.back_button.set_sensitive(self.graph_back or self.view.can_go_back())

        def connection_message(self, _manager, message):
            try: available = message.get_js_value().to_boolean()
            except GLib.Error: available = False
            if not available:
                self.ensure_connection(failed=True)

        def go_back(self, *_):
            if not self.view: return
            script = "Boolean(window.laplaceWorkspace&&window.laplaceWorkspace.back&&window.laplaceWorkspace.back())"
            def finished(view, result, *_args):
                try: consumed = view.evaluate_javascript_finish(result).to_boolean()
                except GLib.Error: consumed = False
                if not consumed and view.can_go_back(): view.go_back()
                self.graph_back = bool(consumed)
                self.back_button.set_sensitive(self.graph_back or view.can_go_back())
            self.view.evaluate_javascript(script, -1, None, None, None, finished, None)

        def report_readiness(self, view, uri, attempt):
            # Bounded startup diagnostics distinguish loaded HTML from a working
            # asynchronous workspace. No ongoing polling or manuscript text log.
            if self.window is None or view.get_uri() != uri:
                return False
            script = """(()=>{const frame=document.querySelector('iframe[title="Manuscript reader and editor"]');
              const doc=frame?frame.contentDocument:document;const walk=doc&&doc.querySelector('#walk');
              const ready=frame?!!(walk&&walk.dataset.readyMs):!!(window.laplaceWorkspace||document.querySelector('.pw-library')||(window.walk&&window.walk.ready()));
              return JSON.stringify({ready,render_ms:walk?Number(walk.dataset.renderMs||0):null,ready_ms:walk?Number(walk.dataset.readyMs||0):null,blocks:walk?walk.querySelectorAll('.blk').length:0});})()"""
            def observed(view, result, *_):
                try:
                    observed_state = json.loads(view.evaluate_javascript_finish(result).to_string())
                    ready = observed_state.get("ready")
                except (GLib.Error, ValueError, TypeError):
                    ready = False
                if ready:
                    self.recovery.ready()
                    print(json.dumps({"desktop":"workspace-ready", "uri":uri, **observed_state}), flush=True)
                elif attempt < 100 and self.window is not None:
                    GLib.timeout_add(200, self.report_readiness, view, uri, attempt + 1)
            view.evaluate_javascript(script, -1, None, None, None, observed, None)
            return False

        def load_failed(self, view, event, uri, error):
            if error.matches(WebKit2.network_error_quark(), WebKit2.NetworkError.CANCELLED):
                return False
            self.load_error = True
            if local_uri(uri, origin):
                self.last_uri = uri
            self.notice.set_text("The local engine is unavailable. Reconnecting…")
            self.notice.show()
            self.retry_button.show()
            self.ensure_connection(failed=True, reload=True)
            return True  # keep the workspace; never replace it with a raw connection error

        def ensure_connection(self, *, manual=False, failed=False, reload=False, uri=None):
            if self.starting or self.closing or self.window is None:
                return False
            if not self.recovery.begin(time.monotonic(), manual=manual, failed=failed):
                return False
            if manual or failed:
                self.notice.set_text('Connecting to your local workspace…'); self.notice.show()
            def restored(result, error):
                self.recovery.finish()
                if self.window is None:
                    return False
                if error:
                    self.notice.set_text('Could not reconnect: ' + error)
                    self.notice.show(); self.retry_button.show()
                    return False
                self.recovery.ready()
                self.update_notice = result.get("update_error") or ""
                if self.view is None:
                    return self.engine_ready(result, None)
                reloaded = should_reload(result, failed_page=self.load_error, requested=bool(reload or uri))
                if reloaded:
                    self.view.load_uri(uri or self.last_uri)
                else:
                    if self.update_notice:
                        self.notice.set_text(self.update_notice + ". The existing workspace is still running.")
                        self.notice.show()
                    else:
                        self.notice.hide()
                    self.retry_button.hide()
                if should_notify_reconnected(result, failed=failed, reloaded=reloaded):
                    self.view.evaluate_javascript("window.dispatchEvent(new CustomEvent('laplace-workspace-reconnected'));", -1, None, None, None, None, None)
                print(json.dumps({'desktop':'engine-checked','disposition':result.get('disposition'),
                                  'reloaded':reloaded}),flush=True)
                return False
            action=connection_action(manual=manual,reload=reload)
            self.background(lambda: engine(action),restored)
            return False

        def process_terminated(self, *_):
            self.notice.set_text("The document view stopped. Your saved work is safe; use Reload to reopen it.")
            self.notice.show()

        def message(self, title, detail):
            dialog = Gtk.MessageDialog(transient_for=self.window, modal=True,
                message_type=Gtk.MessageType.INFO, buttons=Gtk.ButtonsType.CLOSE, text=title)
            dialog.format_secondary_text(detail)
            dialog.run(); dialog.destroy()

        def decide_policy(self, view, decision, kind):
            if kind not in (WebKit2.PolicyDecisionType.NAVIGATION_ACTION, WebKit2.PolicyDecisionType.NEW_WINDOW_ACTION):
                return False
            action = decision.get_navigation_action()
            uri = action.get_request().get_uri()
            if local_uri(uri, origin) and kind == WebKit2.PolicyDecisionType.NAVIGATION_ACTION:
                return False
            # Deliberate separate-window and literature links use the registered
            # system handler, preserving the embedded reader and its drafts.
            if action.is_user_gesture() and urlsplit(uri).scheme in {"http", "https", "mailto"}:
                try:
                    Gio.AppInfo.launch_default_for_uri(uri, None)
                except GLib.Error as exc:
                    self.message("Could not open this link", str(exc))
            decision.ignore()
            return True

        def download_started(self, context, download):
            self.downloads.add(download)
            download.connect("decide-destination", self.download_destination)
            download.connect("finished", lambda item: self.downloads.discard(item))
            download.connect("failed", lambda item, error: self.downloads.discard(item))

        def download_destination(self, download, suggested):
            chooser = Gtk.FileChooserNative.new("Save document", self.window,
                Gtk.FileChooserAction.SAVE, "Save", "Cancel")
            chooser.set_current_name(Path(suggested).name)
            chooser.set_do_overwrite_confirmation(True)
            folder = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD) or str(Path.home())
            chooser.set_current_folder(folder)
            if chooser.run() == Gtk.ResponseType.ACCEPT:
                download.set_allow_overwrite(True)
                download.set_destination(Path(chooser.get_filename()).as_uri())
            else:
                download.cancel()
            chooser.destroy()
            return True

        def request_close(self, *_):
            if self.closing:
                return True
            if self.view:
                # WebKit asks the existing beforeunload handler about unsaved
                # edits before emitting close. No draft is silently discarded.
                self.view.try_close()
            elif self.started:
                self.check_close()
            elif self.starting:
                self.close_pending = True
            else:
                self.window.destroy(); self.window = None; self.quit()
            return True

        def check_close(self):
            if self.closing or not self.window:
                return
            # Downloads belong to this WebKit process; engine work does not.
            if self.downloads:
                self.message("A download is still running", "Let the download finish before closing this window. Research work can continue with the window closed.")
                return
            self.closing = True
            self.background(lambda: engine("--status"), self.close_status)

        def close_status(self, result, error):
            if not self.window:
                return False
            if self.downloads:
                self.closing = False
                self.message("A download is still running", "Let the download finish before closing this window.")
                return False
            result = result or {}
            reason = busy_reason(result)
            if error or reason:
                self.close_work_dialog(result, error, reason)
            else:
                self.detach_window()
            return False

        def close_work_dialog(self, result, error, reason):
            dialog = Gtk.MessageDialog(transient_for=self.window, modal=True,
                message_type=Gtk.MessageType.INFO, buttons=Gtk.ButtonsType.NONE,
                text="Close this window and keep working?" if not error else "Close this window?")
            detail = (reason + "." if not error else "The engine status could not be checked: " + str(error))
            dialog.format_secondary_text(detail + "\nClosing only this window keeps the research engine and its work running. Reopen Writing to return.")
            dialog.add_button("Stay", Gtk.ResponseType.CANCEL)
            dialog.add_button("Close window (keep running)", Gtk.ResponseType.ACCEPT)
            dialog.set_default_response(Gtk.ResponseType.CANCEL)
            links = active_work_links(result, origin)
            if links:
                scroll = Gtk.ScrolledWindow()
                scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
                scroll.set_max_content_height(300)
                scroll.set_propagate_natural_height(True)
                rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
                scroll.add(rows)
                dialog.get_content_area().pack_start(scroll, True, True, 3)
            for index, row in enumerate(links):
                button = Gtk.Button.new_with_label(row['action'] + ": " + row['label'])
                button.set_tooltip_text(row['label'])
                button.get_child().set_line_wrap(True)
                button.get_child().set_max_width_chars(65)
                button.connect('clicked', lambda _button, response=1000 + index: dialog.response(response))
                rows.pack_start(button, False, False, 3)
            omitted = (result.get('health') or {}).get('active_work_omitted', 0)
            if omitted:
                dialog.get_content_area().pack_start(Gtk.Label(label=f"{omitted} more active items; reopen their projects to inspect."), False, False, 3)
            dialog.show_all()
            response = dialog.run()
            dialog.destroy()
            if response == Gtk.ResponseType.ACCEPT:
                self.detach_window()
            else:
                self.closing = False
                if isinstance(response, int) and 1000 <= response < 1000 + len(links) and self.view:
                    self.view.load_uri(links[response - 1000]['uri'])

        def detach_window(self):
            if not self.window:
                return False
            width, height = self.window.get_size()
            try:
                write_ui_state(state, width, height, self.view.get_uri() if self.view else origin, origin, homes=homes)
            except OSError as exc:
                print(json.dumps({"desktop": "window-state-error", "error": str(exc)}), file=sys.stderr, flush=True)
            self.window.destroy()
            self.window = None
            release_profile()
            print(json.dumps({"desktop":"closed", "engine_disposition":"keep-running"}), flush=True)
            self.quit()
            return False

    app = WritingApplication()
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, app.request_close)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, app.request_close)
    try:
        return app.run(["laplace-writing"])
    finally:
        release_profile()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Laplace standalone research and writing application")
    parser.add_argument("--repo-root", type=Path, default=SOURCE_TREE, help="checkout to serve (default: %(default)s)")
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--workspace-root", type=Path)
    parser.add_argument("--engine-state", type=Path)
    parser.add_argument("--session-workspaces", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8771)
    parser.add_argument("--check-runtime", action="store_true")
    args = parser.parse_args(argv)
    try:
        locations = {key:getattr(args,key) for key in ('workspace_root','engine_state','session_workspaces') if getattr(args,key) is not None}
        backend_command(args.repo_root, args.state, args.host, args.port, "--status", **locations)
        if args.check_runtime:
            Gdk, Gio, GLib, Gtk, WebKit2 = load_toolkit()
            print(json.dumps({"runtime":"GTK + WebKitGTK", "gtk": Gtk.get_major_version(),
                "webkit":".".join(str(getattr(WebKit2,"get_"+part+"_version")()) for part in ("major","minor","micro")),
                "display_available":bool(Gtk.init_check()[0]), "browser_required":False}))
            return 0
        return run(args.repo_root,args.state,args.host,args.port, **locations)
    except (ImportError, ValueError, OSError) as exc:
        print("Laplace desktop could not start: " + str(exc) +
              "\nRequires system python3-gi, gir1.2-gtk-3.0 and gir1.2-webkit2-4.1.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
