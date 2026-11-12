"""Local, lightweight launcher for the standalone Writing App.

This is intentionally not a second server.  It owns only an on-demand scanner
process started with ``--writing`` on loopback port 8771. The native GTK shell
owns its lifetime. The PID receipt includes a Linux start tick and source digest, so a
reused PID or a changed checkout is reported as stale rather than reaped.
"""
from __future__ import annotations
from laplace.core.checkout import source_tree

import argparse
import contextlib
import contextvars
import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterator, Mapping
from laplace.core import runtime as core_runtime
from laplace.desktop import managed_homes

_HOMES = contextvars.ContextVar("writing_managed_homes", default=None)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8771
DEFAULT_PATH = "/project?workspace=writing"
HEALTH_PATH = "/authoring/health"
STATE_SCHEMA = "laplace.writing-app-state/1"
_ACTIVE_HEALTH_FIELDS = ("active_turns", "active_previews", "active_builds",
                         "active_runs", "active_proof_checks", "active_mutations")


class WritingAppError(RuntimeError):
    pass


def repo_root(value: Path | str | None = None) -> Path:
    return Path(value).resolve() if value else source_tree()


def state_path(value: Path | str | None = None) -> Path:
    return managed_homes.receipt_path(value)


def host_selection(root=None, state=None, *, workspace_root=None, engine_state=None, session_workspaces=None):
    """The one host selection; direct native loads the same stdlib-only owner."""
    try:
        return managed_homes.resolve(repo_root(root), state=state, workspace_root=workspace_root,
                                     engine_state=engine_state, session_workspaces=session_workspaces)
    except ValueError as exc:
        raise WritingAppError(str(exc)) from exc


def _receipt_matches(record, homes=None):
    homes = homes if homes is not None else _HOMES.get()
    recorded = record.get('managed_homes')
    if homes is None:
        return not (isinstance(recorded, dict) and recorded.get('separate'))
    keys = ('code_root', 'workspace_root', 'receipt', 'engine_state', 'session_workspaces')
    return (isinstance(recorded, dict) and recorded.get('separate') is True
            and all(recorded.get(key) == homes[key] and record.get(key) == homes[key] for key in keys if key != 'receipt')
            and recorded.get('receipt') == homes['receipt'])


def _health_matches(live, homes, record):
    observed = live.get('managed_homes') if isinstance(live, dict) else None
    return (isinstance(observed, dict) and all(observed.get(key) == homes[key] for key in
            ('code_root', 'workspace_root', 'receipt', 'engine_state', 'session_workspaces'))
            and all(live.get(key) == homes[key] for key in ('code_root', 'workspace_root', 'engine_state', 'session_workspaces'))
            and (live.get('source_start') or {}).get('root') == homes['code_root']
            and (live.get('workspace_start') or {}).get('root') == homes['workspace_root']
            and ('workspace_start' not in record or live.get('workspace_start') == record['workspace_start'])
            and live.get('pid') == record.get('pid') and type(live.get('pid')) is int
            and str(live.get('source')) == homes['workspace_root'])


def _invoke(function, *, root=None, state=None, workspace_root=None, engine_state=None, session_workspaces=None, **kwargs):
    active = _HOMES.get()
    if (active is not None and workspace_root is None and engine_state is None and session_workspaces is None
            and repo_root(root) == Path(active['code_root']) and state_path(state).resolve() == Path(active['receipt'])):
        homes = active
    else:
        homes = host_selection(root, state, workspace_root=workspace_root, engine_state=engine_state,
                               session_workspaces=session_workspaces)
    token = _HOMES.set(homes if homes['separate'] else None)
    try:
        value = function(root=Path(homes['code_root']), state=Path(homes['receipt']), **kwargs)
        return {**value, 'managed_homes': homes} if homes['separate'] and isinstance(value, dict) else value
    finally:
        _HOMES.reset(token)



@contextlib.contextmanager
def _lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with lock_path.open("a+", encoding="utf-8") as stream:
        import fcntl
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _read(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError):
        return {"invalid": True}
    return data if isinstance(data, dict) else {"invalid": True}


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".writing-app-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _audit_lifecycle(target: Path, event: str, **detail: Any) -> None:
    """Append bounded service provenance without affecting lifecycle outcomes."""
    try:
        parent = os.getppid()
        try:
            parent_argv = [part.decode("utf-8", errors="replace") for part in
                           (Path("/proc") / str(parent) / "cmdline").read_bytes().split(b"\0") if part]
        except OSError:
            parent_argv = []
        row = {"schema_version":"laplace.writing-lifecycle/1",
               "ts":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
               "event":event,"caller_pid":os.getpid(),"parent_pid":parent,
               "caller_argv":sys.argv[:16],"parent_argv":parent_argv[:16],**detail}
        path = target.with_name(target.stem + "-lifecycle.jsonl")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, sort_keys=True, default=str) + "\n")
            stream.flush();os.fsync(stream.fileno())
    except OSError:
        pass


def _start_tick(pid: int) -> str | None:
    """Linux process start time, paired with PID before any termination action."""
    try:
        # comm may contain spaces/parentheses, so field 22 begins after its final `)`.
        stat = (Path("/proc") / str(pid) / "stat").read_text(encoding="utf-8")
        fields = stat.rsplit(")", 1)[1].strip().split()
        return fields[19]  # field 22, after the two initial pid/comm fields
    except (OSError, IndexError):
        return None


def source_snapshot(root: Path | str | None = None) -> dict[str, Any]:
    """Covered disk inputs, not a claim about all already-imported code bytes.

    Generator recipes and history are separate consumers. This serving basis
    covers both packages and runtime profiles actually shipped with the workspace.
    """
    base = repo_root(root)
    digest = hashlib.sha256()
    sources = [p for package in ("src/laplace", "src/atlas")
               for p in (base / package).rglob("*")
               if p.is_file() and p.suffix in {".py", ".mjs", ".js", ".css", ".html", ".json"}]
    sources += list((base / "profiles/typography").glob("*.json"))
    sources += list((base / "profiles/workflows").glob("*.json"))
    if (base / "profiles/visual_style.json").is_file(): sources.append(base / "profiles/visual_style.json")
    total_bytes = 0
    for relative in sorted(str(p.relative_to(base)) for p in sources):
        path = base / relative
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        try:
            raw = path.read_bytes()
            total_bytes += len(raw)
            digest.update(raw)
        except OSError:
            digest.update(b"MISSING")
        digest.update(b"\0")
    return {"schema_version":"laplace.writing-source-basis/1", "identity":digest.hexdigest(),
            "basis":"covered-disk-inputs", "root":str(base), "files":len(sources),
            "bytes":total_bytes, "coverage":["src/laplace", "src/atlas",
                "profiles/typography", "profiles/workflows", "profiles/visual_style.json"],
            "loaded_code_asserted":False}


def source_identity(root: Path | str | None = None) -> str:
    return source_snapshot(root)["identity"]


def url(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, path: str = DEFAULT_PATH) -> str:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise WritingAppError("Writing App only binds and opens loopback hosts")
    return f"http://{host}:{int(port)}{path}"


def health_url(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> str:
    return url(host, port, HEALTH_PATH)


def health(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, timeout: float = 1.0) -> dict[str, Any] | None:
    try:
        with urllib.request.urlopen(health_url(host, port), timeout=timeout) as response:
            if response.status != 200:
                return None
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    # The writer's runtime must say what sources and live work the app is serving.
    if not {"source", "runtime", "active_turns"}.issubset(payload) or payload.get("runtime") != "writing":
        return None
    return payload


def _owned(record: Mapping[str, Any]) -> bool:
    pid = record.get("pid")
    tick = record.get("start_tick")
    return isinstance(pid, int) and isinstance(tick, str) and tick == _start_tick(pid)


def _listener_present(host: str, port: int) -> bool:
    """Bounded port probe used only before claiming a missing managed listener."""
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    try:
        with socket.socket(family, socket.SOCK_STREAM) as stream:
            stream.settimeout(0.2)
            return stream.connect_ex((host, int(port))) == 0
    except OSError:
        # An unprobeable bind is not permission to replace it.
        return True


def _wait_owned_listener_release(host:str,port:int,timeout:float=2.0)->bool:
    """Wait only after this checkout proved and stopped its exact owned PID."""
    deadline=time.monotonic()+max(0.0,timeout)
    while _listener_present(host,port):
        remaining=deadline-time.monotonic()
        if remaining<=0:return False
        time.sleep(min(0.05,remaining))
    return True


def _has_active_work(payload: Mapping[str, Any] | None) -> bool:
    return bool(payload and any(payload.get(field) for field in _ACTIVE_HEALTH_FIELDS))


def _native_viewer_parent(record: Mapping[str, Any], root: Path, target: Path,
                          _proc_root: Path = Path("/proc")) -> bool:
    """Prove this stop request came from this checkout's native viewer."""
    parent = os.getppid();proc=_proc_root/str(parent)
    try:
        argv=[part.decode("utf-8",errors="replace") for part in
              (proc/"cmdline").read_bytes().split(b"\0") if part]
        executable=(proc/"exe").resolve()
    except OSError:
        return False
    if len(argv)<2 or Path(argv[0]).resolve()!=executable:
        return False
    script=str((root/"src/laplace/desktop/native_writing.py").resolve())
    if script not in argv:
        return False
    def option(name):
        try:return argv[argv.index(name)+1]
        except (ValueError,IndexError):return None
    try:
        same_root=Path(str(option("--repo-root"))).resolve()==root
        same_state=Path(str(option("--state"))).resolve()==target.resolve()
        same_port=int(str(option("--port")))==int(record.get("port",DEFAULT_PORT))
    except (OSError,TypeError,ValueError):
        return False
    homes = _HOMES.get()
    if homes:
        if any(option(flag) != homes[key] for flag, key in
               (('--workspace-root', 'workspace_root'), ('--engine-state', 'engine_state'), ('--session-workspaces', 'session_workspaces'))):
            return False
    return (same_root and same_state and same_port
            and option("--host")==str(record.get("host",DEFAULT_HOST)))


def _status(*, root: Path | str | None = None, state: Path | str | None = None,
           host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
           _health_timeout: float = 1.0) -> dict[str, Any]:
    """Return state without killing any process, including a stale owned one."""
    homes = _HOMES.get()
    source = source_identity(root)
    record = _read(state_path(state))
    live = health(host, port, timeout=_health_timeout)
    try:
        selected = core_runtime.selection_basis(repo_root(root))
    except core_runtime.RuntimePolicyError as error:
        return {"status":"runtime-unavailable", "source_identity":source,
                "health":live, "record":record, "runtime_selection_error":str(error)}
    if record is None:
        return {"status": "absent", "source_identity": source, "health": live}
    if record.get("invalid") or record.get("schema_version") != STATE_SCHEMA:
        return {"status": "invalid-state", "source_identity": source, "health": live}
    if not _receipt_matches(record):
        return {"status": "selection-mismatch", "source_identity": source, "health": live, "record": record}
    if not _owned(record):
        return {"status": "stale-process", "source_identity": source, "health": live, "record": record}
    if Path(str(record.get("repo_root") or "")).resolve() != repo_root(root):
        return {"status": "stale-runtime", "source_identity": source, "health": live, "record": record}
    if live is not None and (type(live.get("pid")) is not int or live["pid"] != record["pid"]):
        return {"status":"stale-runtime","health_attribution_unproven":True,
                "source_identity":source,"health":live,"record":record}
    if homes is not None and live is not None and not _health_matches(live, homes, record):
        return {"status": "selection-mismatch", "health_attribution_unproven": True, "source_identity": source, "health": live, "record": record}
    if record.get("source_identity") != source:
        return {"status": "stale-source", "source_identity": source, "health": live, "record": record}
    if live is None:
        return {"status": "unhealthy", "source_identity": source, "health": None, "record": record}
    try:
        served_root = Path(str(live.get("source") or "")).resolve()
    except OSError:
        served_root = Path("/")
    if served_root != (Path(homes["workspace_root"]) if homes else repo_root(root)):
        return {"status": "stale-runtime", "source_identity": source, "health": live, "record": record}
    consumed = record.get("runtime_selection_start")
    observed = live.get("runtime_start")
    producer_selection = live.get("runtime_selection_start")
    if not all(isinstance(value,dict) for value in (consumed,observed,producer_selection)):
        return {"status":"stale-runtime","runtime_selection_unproven":True,
                "source_identity":source,"health":live,"record":record}
    if (consumed.get("identity") != selected["identity"]
            or producer_selection.get("identity") != consumed.get("identity")
            or producer_selection.get("identity") != selected["identity"]
            or (observed.get("executable") != selected["resolved"]
                             or observed.get("version") != selected["expected_python"])):
        return {"status":"stale-runtime", "runtime_selection_changed":True,
                "runtime_selection":selected, "source_identity":source,"health":live,"record":record}
    start = live.get("source_start")
    if start and start.get("identity") != record.get("source_identity"):
        return {"status":"stale-runtime", "source_identity":source, "health":live, "record":record}
    return {"status": "running", "source_identity": source, "health": live, "record": record}


def _managed_environment(root: Path, receipt: Path, selection: dict, source: str) -> dict[str,str]:
    """Relevant declared inputs shared by the non-serving probe and launch."""
    environment = {**os.environ,"LAPLACE_WRITING_APP":"1","LAPLACE_NO_PREWARM":"1",
            "LAPLACE_WRITING_STATE":str(receipt),"LAPLACE_REPO_ROOT":str(root),
            "LAPLACE_WRITING_EXPECTED_SOURCE":source,
            "LAPLACE_WRITING_EXPECTED_SELECTION":selection["identity"]}
    homes = _HOMES.get()
    if homes:
        environment.update(LAPLACE_REPO_ROOT=homes['workspace_root'], LAPLACE_ROOT=homes['workspace_root'],
            LAPLACE_REEMBED_ROOT=homes['workspace_root'], LAPLACE_STATE=homes['engine_state'],
            LAPLACE_EIGEN_STATE=str(Path(homes['engine_state']) / 'eigen-authority'),
            LAPLACE_SESSION_WORKSPACES=homes['session_workspaces'],
            LAPLACE_MANAGED_HOMES=json.dumps(homes, sort_keys=True),
            LAPLACE_WRITING_CODE_ROOT=homes['code_root'])
        if selection.get('workspace_basis'):
            environment['LAPLACE_WRITING_EXPECTED_WORKSPACE'] = selection['workspace_basis']['identity']
    else:
        for key in ('LAPLACE_MANAGED_HOMES', 'LAPLACE_WRITING_CODE_ROOT', 'LAPLACE_WRITING_EXPECTED_WORKSPACE'):
            environment.pop(key, None)
    return environment


def _validate_managed_runtime(root: Path, *, state: Path | None = None, source: str | None = None) -> dict[str, Any]:
    """Validate the selected checkout entrance before retiring an owned server."""
    expected=core_runtime.selection_basis(root)
    homes = _HOMES.get()
    workspace_basis = managed_homes.workspace_snapshot(homes["workspace_root"]) if homes else None
    code=("import json,runpy; p=runpy.run_path("+repr(str(root/"src/laplace/core/runtime.py"))+
          "); from laplace.web import scanner,shared_ui,authoring as authoring_surface,research_surface,project_work_surface; "+
          "from laplace.research import references_surface,formal_surface,concepts as concepts_surface,visuals_surface; "+
          "from laplace.projects import library as writing_projects; from laplace.representation import atlas_bridge; "+
          "shared_ui.capture_asset_snapshot(); print(json.dumps(p['receipt']()))")
    try:
        result=subprocess.run(core_runtime.runtime_command(root,"-c",code),cwd=root,
                              env=_managed_environment(root,state or state_path(),expected,source or source_identity(root)),
                              capture_output=True,text=True,timeout=10)
        if result.returncode:
            raise WritingAppError("Selected managed runtime refused startup: "+result.stderr[-1600:])
        observed=json.loads(result.stdout)
    except (OSError,subprocess.TimeoutExpired,ValueError) as error:
        raise WritingAppError("Selected managed runtime could not be observed: "+str(error)) from error
    if (observed.get("executable") != expected["resolved"]
            or observed.get("version") != expected["expected_python"]
            or not observed.get("user_site_disabled")):
        raise WritingAppError("Selected managed runtime observation disagrees with its declaration")
    if core_runtime.selection_basis(root)["identity"] != expected["identity"]:
        raise WritingAppError("Managed runtime selection changed during validation")
    if homes and managed_homes.workspace_snapshot(homes['workspace_root']) != workspace_basis:
        raise WritingAppError('Workspace configuration changed during validation')
    return {**expected,"validated_runtime":observed,"validation_probe_calls":1,
            **({'workspace_basis': workspace_basis} if homes else {})}


def _validate_runtime_sources(root: Path) -> None:
    """Check syntax without importing modules or writing bytecode before replacement."""
    for path in sorted(p for package in ("src/laplace", "src/atlas")
                       for p in (root / package).rglob("*.py")):
        try:
            compile(path.read_bytes(), str(path), "exec", dont_inherit=True)
        except (SyntaxError, ValueError, OSError) as exc:
            line = getattr(exc, "lineno", None)
            location = str(path.relative_to(root)) + (f":{line}" if line else "")
            raise WritingAppError(f"Workspace update cannot load {location}: {getattr(exc, 'msg', str(exc))}") from exc


def _startup_log(target: Path) -> Path:
    return target.with_suffix(".log")


def _log_tail(path: Path, limit: int = 4000) -> str:
    try:
        with path.open("rb") as stream:
            stream.seek(0, os.SEEK_END)
            stream.seek(max(0, stream.tell() - limit))
            return stream.read(limit).decode("utf-8", errors="replace").strip()
    except OSError:
        return ""


def _start_server(root: Path, host: str, port: int, log_path: Path | None = None,
                  selection: dict | None = None, source: str | None = None,
                  receipt: Path | None = None) -> subprocess.Popen[str]:
    homes = _HOMES.get()
    workspace = homes["workspace_root"] if homes else str(root)
    command = core_runtime.runtime_command(root,"-m","laplace.web.scanner","--host",host,"--port",str(port),
                                            "--writing","--repo-root",workspace)
    log_path = log_path or _startup_log(state_path())
    environment = _managed_environment(root,receipt or state_path(),
                        selection or core_runtime.selection_basis(root),source or source_identity(root))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if log_path.exists() and log_path.stat().st_size > 2_000_000:
        os.replace(log_path, log_path.with_suffix(".previous.log"))
    with log_path.open("a", encoding="utf-8") as output:
        output.write(f"\nWorkspace start {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} · {root}\n")
        output.flush()
        return subprocess.Popen(command, cwd=root, env=environment, text=True, start_new_session=True,
                                stdout=output, stderr=subprocess.STDOUT)


def _ensure_server(*, root: Path | str | None = None, state: Path | str | None = None,
                  host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
                  timeout: float = 12.0, allow_update: bool = True) -> dict[str, Any]:
    """Start/reconnect an owned writing process; update source only when requested."""
    base, target = repo_root(root), state_path(state)
    with _lock(target):
        retired_owned=False
        validated_selection=None
        owned_health_wait=None
        before = status(root=base, state=target, host=host, port=port)
        launch_identity=before["source_identity"]
        if before.get("runtime_selection_error"):
            return {**before,"disposition":"update-unavailable","started":False,
                    "update_error":before["runtime_selection_error"]}
        if (before["status"] in {"unhealthy", "stale-source"} and not before.get("health")
                and _owned(before.get("record") or {})):
            # A single slow request must not become a refused replacement, or kill
            # work whose health could not yet be observed. Re-observe before acting.
            # Observed: the health door can answer in ~7.7 s while a long Work read
            # is in flight, beyond the fixed 1+3+3 s probes, so an exact-owned live
            # process was refused as unhealthy. While that owned process still holds
            # its listener, a late answer is a busy owner rather than a dead one:
            # keep observing within this call's own timeout budget. No signal is sent.
            wait_started = time.monotonic()
            patience = wait_started + max(0.0, float(timeout))
            attempt = 0
            while True:
                if attempt >= 2 and (time.monotonic() >= patience or not _listener_present(host, port)):
                    break
                time.sleep((0.1, 0.3)[attempt] if attempt < 2 else 0.1)
                probe = 3.0 if attempt < 2 else max(1.0, min(10.0, patience - time.monotonic()))
                attempt += 1
                before = status(root=base, state=target, host=host, port=port,
                                _health_timeout=probe)
                if before.get("health") or before["status"] not in {"unhealthy", "stale-source"}:
                    break
            owned_health_wait = (round(time.monotonic() - wait_started, 3), attempt)
        if before["status"] == "running":
            return {**before, "disposition": "reused", "started": False}
        if (before["status"] == "stale-source" or before.get("runtime_selection_changed")
                or before.get("runtime_selection_unproven")) and before.get("health"):
            live, record = before["health"], before["record"]
            if not allow_update:
                return {**before, "disposition": "reused-current-runtime", "started": False}
            if _has_active_work(live):
                return {**before, "disposition": "upgrade-after-active-work", "started": False}
            try:
                validated_selection = _validate_managed_runtime(base,state=target,source=launch_identity)
                _validate_runtime_sources(base)
                if (source_identity(base) != before["source_identity"]
                        or core_runtime.selection_basis(base)["identity"] != validated_selection["identity"]):
                    return {**before, "disposition": "update-in-progress", "started": False}
            except (WritingAppError,core_runtime.RuntimePolicyError) as exc:
                # Keep the healthy process. Invalid in-progress source is not a
                # reason to take the author's current workspace down.
                return {**before, "disposition": "update-unavailable", "started": False,
                        "update_error": str(exc)}
            _audit_lifecycle(target,"source-update-retire",pid=record.get("pid"),
                             policy="explicit-update" if allow_update else "passive")
            _terminate_owned(record, base)
            retired_owned=True
            target.unlink(missing_ok=True)
            before = {"status": "absent", "health": None}
        if before["status"] == "stale-process":
            record = before.get("record") or {}
            if Path(str(record.get("repo_root") or "")).resolve() != base:
                raise WritingAppError("Writing App refused a stale process receipt from another checkout")
            if before.get("health") is not None or _listener_present(host, port):
                raise WritingAppError("Writing App found a listener without a live matching process receipt and will not replace it")
            # This checkout owns the receipt, but its exact PID/start tick is
            # gone. Remove only the stale file; never signal a dead PID or an
            # unrelated process that reused the number.
            target.unlink(missing_ok=True)
            before = {"status": "absent", "health": None}
        if before["status"] == "absent" and before.get("health") is not None:
            raise WritingAppError("Writing App found an unmanaged writing listener and will not replace it")
        if before["status"] not in {"absent", "unhealthy"}:
            raise WritingAppError(f"Writing App refused to replace {before['status']}; use --status or --stop after inspection")
        if before["status"] == "unhealthy" and before.get("record") and _owned(before["record"]):
            # This is our proven process, but an unhealthy scanner could still be busy
            # shutting down. Refuse rather than guessing that it is safe to reap.
            waited = (f" Its exact PID {before['record'].get('pid')} did not answer {HEALTH_PATH} within "
                      f"{owned_health_wait[0]} s over {owned_health_wait[1] + 1} probes while its listener was "
                      "observed; it was not signalled. Retrying reconnect is safe and leaves it running."
                      if owned_health_wait else "")
            raise WritingAppError("Writing App has an owned but unhealthy process; use --stop after inspection." + waited)
        occupied=_listener_present(host,port)
        if occupied and retired_owned:
            occupied=not _wait_owned_listener_release(host,port)
        if occupied:
            raise WritingAppError("Writing App port is occupied by a listener that did not pass managed health checks")
        try:
            if validated_selection is None:
                validated_selection = _validate_managed_runtime(base,state=target,source=launch_identity)
                _validate_runtime_sources(base)
            launch_selection=validated_selection
            if (core_runtime.selection_basis(base)["identity"] != launch_selection["identity"]
                    or source_identity(base) != launch_identity):
                return {**before,"disposition":"update-in-progress","started":False}
        except (WritingAppError,core_runtime.RuntimePolicyError) as error:
            return {**before,"disposition":"update-unavailable","started":False,"update_error":str(error)}
        log_path = _startup_log(target)
        _audit_lifecycle(target,"start-request",policy="explicit-update" if allow_update else "passive",
                         prior_status=before.get("status"))
        process = _start_server(base, host, port, log_path, launch_selection, launch_identity,target)
        tick = _start_tick(process.pid)
        if tick is None:
            raise WritingAppError("Writing App could not verify its newly started process")
        record = {"schema_version": STATE_SCHEMA, "pid": process.pid, "start_tick": tick,
                  "repo_root": str(base), "source_identity": launch_identity,
                  "runtime_selection_expected":launch_selection,
                  "host": host, "port": int(port), "started_at": time.time(),
                  "log_path": str(log_path)}
        homes = _HOMES.get()
        if homes:
            record.update(managed_homes=homes, **{key: homes[key] for key in
                          ('code_root', 'workspace_root', 'engine_state', 'session_workspaces')})
        _write(target, record)
        _audit_lifecycle(target,"process-started",policy="explicit-update" if allow_update else "passive",
                         pid=process.pid,start_tick=tick,source_identity=record["source_identity"])
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            # This process was just started and is exact-owned.  Permit bounded
            # cold health imports to finish instead of stacking one-second probes
            # and then terminating a service which was already listening.
            live = health(host, port, timeout=min(3.0, max(1.0, deadline-time.monotonic())))
            if live is not None:
                if homes and not _health_matches(live, homes, record):
                    return {'status': 'selection-mismatch', 'disposition': 'startup-unproven',
                            'started': False, 'process_spawned': True, 'record': record, 'health': live}
                selected_start=live.get("runtime_selection_start")
                observed=live.get("runtime_start")
                start=live.get("source_start")
                if (not _owned(record) or type(live.get("pid")) is not int or live["pid"] != process.pid
                        or not all(isinstance(value,dict) for value in (selected_start,observed,start))):
                    return {"status":"stale-runtime","disposition":"startup-unproven",
                            "started":False,"process_spawned":True,"record":record,"health":live,
                            "source_identity":launch_identity}
                if (selected_start and selected_start.get("identity") != launch_selection["identity"]
                        or observed and (observed.get("executable") != launch_selection["resolved"]
                                         or observed.get("version") != launch_selection["expected_python"]
                                         or launch_selection.get("validated_runtime") and observed != launch_selection["validated_runtime"])):
                    return {"status":"stale-runtime","disposition":"update-in-progress",
                            "started":False,"process_spawned":True,"record":record,"health":live,"source_identity":source_identity(base)}
                if selected_start:
                    record["runtime_selection_start"]=selected_start
                if observed:
                    record["runtime_start"]=observed
                start = live.get("source_start")
                if start:
                    if start.get("identity") != launch_identity or source_identity(base) != launch_identity:
                        # Never upgrade a racing disk observation into currentness.
                        # Keep this exact-owned process inspectable; do not reap it.
                        return {"status":"stale-source", "disposition":"update-in-progress",
                                "started":False,"process_spawned":True, "record":record, "health":live,
                                "source_identity":source_identity(base)}
                    record["source_start"] = start
                    record["source_identity"] = start["identity"]
                    _write(target, record)
                if homes:
                    observed_workspace = live.get('workspace_start')
                    if observed_workspace != launch_selection.get('workspace_basis'):
                        return {'status': 'workspace-unproven', 'started': False, 'process_spawned': True,
                                'record': record, 'health': live}
                    record['workspace_start'] = observed_workspace
                if live.get("frontend_bundle"):
                    record["frontend_bundle"] = live["frontend_bundle"]
                    _write(target, record)
                _audit_lifecycle(target,"process-ready",pid=process.pid,
                                 frontend_bundle=live.get("frontend_bundle"))
                return {"status": "running", "disposition": "started", "started": True,
                        "record": record, "health": live, "source_identity": record["source_identity"]}
            if process.poll() is not None:
                target.unlink(missing_ok=True)
                detail = _log_tail(log_path)
                raise WritingAppError(f"Workspace service exited with {process.returncode}. "
                                      f"Startup log: {log_path}" + (f"\n{detail}" if detail else ""))
            time.sleep(0.1)
        # Safe cleanup only for the exact process we started and receipted.
        if _owned(record):
            _audit_lifecycle(target,"startup-timeout-retire",pid=process.pid,
                             timeout_seconds=timeout)
            process.terminate()
            process.wait(timeout=3)
        target.unlink(missing_ok=True)
        raise WritingAppError(f"Workspace service did not become ready. Startup log: {log_path}")


def _terminate_owned(record, root):
    if not _owned(record) or not _receipt_matches(record) or Path(str(record.get("repo_root") or "")).resolve() != repo_root(root):
        raise WritingAppError("The process receipt does not belong to this checkout.")
    os.kill(record["pid"], signal.SIGTERM)
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and _owned(record):
        try:
            fields = Path(f"/proc/{record['pid']}/stat").read_text().rsplit(")",1)[1].split()
            if fields[0] == "Z": break
        except OSError:
            break
        time.sleep(.05)


def _stop(*, root: Path | str | None = None, state: Path | str | None = None) -> dict[str, Any]:
    """Stop only a live process whose PID and start tick match our receipt."""
    target = state_path(state)
    with _lock(target):
        record = _read(target)
        if record is None:
            return {"status": "absent", "stopped": False}
        if record.get("schema_version") != STATE_SCHEMA or not _owned(record):
            return {"status": "stale-process", "stopped": False}
        if not _receipt_matches(record):
            return {"status": "selection-mismatch", "stopped": False}
        base=repo_root(root)
        if (Path(str(record.get("repo_root") or "")).resolve()==base
                and _native_viewer_parent(record,base,target)):
            _audit_lifecycle(target,"viewer-detached",pid=record.get("pid"))
            return {"status":"viewer-detached","disposition":"keep-running",
                    "stopped":False,"pid":record.get("pid")}
        live = health(record.get("host", DEFAULT_HOST), record.get("port", DEFAULT_PORT), timeout=3.0)
        if live is None:
            _audit_lifecycle(target,"stop-refused-unknown-health",pid=record.get("pid"))
            return {"status":"unknown-health", "stopped":False,
                    "reason":"The owned workspace did not answer health; inspect it before stopping."}
        homes = _HOMES.get()
        if homes and not _health_matches(live, homes, record):
            return {"status": "selection-mismatch", "stopped": False}
        if _has_active_work(live):
            _audit_lifecycle(target,"stop-refused-active-work",pid=record.get("pid"),
                             active={field:live.get(field,0) for field in _ACTIVE_HEALTH_FIELDS})
            return {"status":"busy", "stopped":False, "reason":"Finish or stop the active writing work first."}
        _audit_lifecycle(target,"stop-owned",pid=record.get("pid"))
        _terminate_owned(record, root)
        target.unlink(missing_ok=True)
        return {"status": "stopped", "stopped": True, "pid": record["pid"]}


def _turn_events_answer(host: str, port: int, turn_id: str, timeout: float) -> bool:
    """Whether the turn's own event stream sends response headers within ``timeout``. A served stream takes the journal
    fold lock briefly before its headers, so a stream that never answers while health does is the stalled state."""
    try:
        with urllib.request.urlopen(url(host, port, "/authoring/events?turn=" + urllib.parse.quote(turn_id, safe="")), timeout=timeout):
            return True
    except urllib.error.HTTPError:
        return True   # it answered (with a status), so the server is not stalled at the stream's first lock
    except (OSError, urllib.error.URLError):
        return False


def _recover_stalled_turn(*, root: Path | str | None = None, state: Path | str | None = None, project: str, session_id: str,
                         turn_id: str, expected_pid: int, expected_start_tick: str, probe_seconds: float = 5.0,
                         exit_seconds: float = 30.0) -> dict[str, Any]:
    """THE ONE MANAGED RECOVERY of a service whose single active turn is stalled (live freeze 2026-10-20). Normal
    stop/update keep refusing while work is active; this retires the managed service only when every fact is the one
    the caller named: this checkout's owned receipt with the expected PID and start tick, health declaring exactly
    that one active turn (project, session, turn) and no other active work, the turn's execution record running in
    that very process, its session present in that project, and the turn's own event stream not answering within
    ``probe_seconds`` while health does. The intent and the inspected facts (execution, provider processes, native
    id) are audited before the signal; the receipt is re-proved immediately before SIGTERM to that PID only; the
    outcome is audited after the process has exited and its listener is released. No record is written: the turn
    is settled afterwards by Stop on the reconnected service (turn_control.interrupt_turn), never here."""
    target = state_path(state)
    base = repo_root(root)
    detail = {"project": project, "session_id": session_id, "turn_id": turn_id,
              "expected_pid": expected_pid, "expected_start_tick": str(expected_start_tick)}
    with _lock(target):
        def refuse(reason: str, **facts: Any) -> dict[str, Any]:
            _audit_lifecycle(target, "stalled-turn-recovery-refused", reason=reason, **detail, **facts)
            return {"status": "refused", "stopped": False, "reason": reason, **facts}
        record = _read(target)
        if record is None:
            return refuse("There is no managed service receipt.")
        if record.get("schema_version") != STATE_SCHEMA or not _owned(record) or not _receipt_matches(record):
            return refuse("The managed receipt is stale or its process is not the recorded one.")
        if Path(str(record.get("repo_root") or "")).resolve() != base:
            return refuse("The managed receipt belongs to another checkout.")
        if record.get("pid") != expected_pid or record.get("start_tick") != str(expected_start_tick):
            return refuse("The managed receipt is not the expected service.", pid=record.get("pid"), start_tick=record.get("start_tick"))
        host, port = record.get("host", DEFAULT_HOST), record.get("port", DEFAULT_PORT)
        live = health(host, port, timeout=3.0)
        if live is None or live.get("pid") != record["pid"]:
            return refuse("Health did not answer from the managed process.")
        homes = _HOMES.get()
        if homes and not _health_matches(live, homes, record):
            return refuse("The managed service does not match the selected homes.")
        active = {field: live.get(field, 0) for field in _ACTIVE_HEALTH_FIELDS}
        work = live.get("active_work") or []
        declared = [(row.get("kind"), row.get("project"), row.get("session_id"), row.get("turn_id")) for row in work if isinstance(row, Mapping)]
        if (active != {**{field: 0 for field in _ACTIVE_HEALTH_FIELDS}, "active_turns": 1} or live.get("active_work_omitted")
                or declared != [("turn", project, session_id, turn_id)]):
            return refuse("Health does not declare exactly this one active turn and no other active work.", active=active, active_work=work)
        from laplace.writing import child_hosts, records as writing_records
        data_root = Path(_HOMES.get()["workspace_root"]) if _HOMES.get() else base
        execution = child_hosts._child_execution_record(data_root, session_id)
        if (execution.get("turn_id") != turn_id or execution.get("state") != "RUNNING" or execution.get("project") not in (None, project)
                or (execution.get("host") or {}).get("pid") != record["pid"]):
            return refuse("The turn's execution record is not this service's running turn.",
                          execution={key: execution.get(key) for key in ("turn_id", "state", "host", "project")})
        session = writing_records.fold_records(data_root)["sessions"].get(session_id) or {}
        if session.get("project") != project:
            return refuse("The session is not this project's session.")
        if _turn_events_answer(host, port, turn_id, probe_seconds):
            return refuse("The turn's event stream answers; stop the turn in the app instead.")
        facts = {"execution": {key: execution.get(key) for key in ("turn_id", "state", "host", "provider_process", "provider_processes",
                                                                   "provider_phase", "provider_inference_started")},
                 "native_id": session.get("native_id"), "health_active": active, "events_probe_seconds": probe_seconds}
        _audit_lifecycle(target, "stalled-turn-recovery-intent", pid=record["pid"], start_tick=record["start_tick"], **detail, **facts)
        current = _read(target)
        if current != record or not _owned(record) or not _receipt_matches(record):
            return refuse("The managed receipt changed before the signal.")
        os.kill(record["pid"], signal.SIGTERM)
        deadline = time.monotonic() + max(0.0, exit_seconds)
        while _owned(record) and time.monotonic() < deadline:
            time.sleep(0.05)
        exited = not _owned(record)
        released = exited and _wait_owned_listener_release(host, port, timeout=max(0.0, deadline - time.monotonic()) + 2.0)
        if not (exited and released):
            _audit_lifecycle(target, "stalled-turn-recovery-incomplete", pid=record["pid"], exited=exited, listener_released=released, **detail)
            return {"status": "signalled-not-exited", "stopped": False, "pid": record["pid"], "exited": exited, "listener_released": released}
        target.unlink(missing_ok=True)
        _audit_lifecycle(target, "stalled-turn-recovery-retired", pid=record["pid"], **detail, **facts)
        return {"status": "retired-stalled-service", "stopped": True, "pid": record["pid"], **detail, **facts,
                "next": "Reconnect the managed service, then Stop this turn so its owner settles it."}


def _native_command(root=None, state=None, host=DEFAULT_HOST, port=DEFAULT_PORT):
    """The OS toolkit and scientific runtime have deliberately separate interpreters."""
    base = repo_root(root)
    url(host, port)  # validate the same loopback boundary as the engine
    command = ["/usr/bin/python3", "-I", "-B", str(base / "src/laplace/desktop/native_writing.py"),
            "--repo-root", str(base), "--state", str(state_path(state)),
            "--host", host, "--port", str(port)]
    homes = _HOMES.get()
    if homes:
        for flag, key in (('--workspace-root', 'workspace_root'), ('--engine-state', 'engine_state'), ('--session-workspaces', 'session_workspaces')):
            command.extend((flag, homes[key]))
    return command


def status(*, root=None, state=None, host=DEFAULT_HOST, port=DEFAULT_PORT, _health_timeout=1.0,
           workspace_root=None, engine_state=None, session_workspaces=None):
    return _invoke(_status, root=root, state=state, host=host, port=port, _health_timeout=_health_timeout,
                   workspace_root=workspace_root, engine_state=engine_state, session_workspaces=session_workspaces)


def ensure_server(*, root=None, state=None, host=DEFAULT_HOST, port=DEFAULT_PORT, timeout=12.0, allow_update=True,
                  workspace_root=None, engine_state=None, session_workspaces=None):
    return _invoke(_ensure_server, root=root, state=state, host=host, port=port, timeout=timeout, allow_update=allow_update,
                   workspace_root=workspace_root, engine_state=engine_state, session_workspaces=session_workspaces)


def stop(*, root=None, state=None, workspace_root=None, engine_state=None, session_workspaces=None):
    return _invoke(_stop, root=root, state=state, workspace_root=workspace_root,
                   engine_state=engine_state, session_workspaces=session_workspaces)


def recover_stalled_turn(*, root=None, state=None, project, session_id, turn_id, expected_pid, expected_start_tick,
                         probe_seconds=5.0, exit_seconds=30.0, workspace_root=None, engine_state=None, session_workspaces=None):
    return _invoke(_recover_stalled_turn, root=root, state=state, project=project, session_id=session_id,
                   turn_id=turn_id, expected_pid=expected_pid, expected_start_tick=expected_start_tick,
                   probe_seconds=probe_seconds, exit_seconds=exit_seconds, workspace_root=workspace_root,
                   engine_state=engine_state, session_workspaces=session_workspaces)


def native_command(root=None, state=None, host=DEFAULT_HOST, port=DEFAULT_PORT, *, workspace_root=None,
                   engine_state=None, session_workspaces=None):
    return _invoke(_native_command, root=root, state=state, host=host, port=port, workspace_root=workspace_root,
                   engine_state=engine_state, session_workspaces=session_workspaces)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Open the local Laplace Writing App.")
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument("--state", type=Path, default=None)
    parser.add_argument("--workspace-root", type=Path)
    parser.add_argument("--engine-state", type=Path)
    parser.add_argument("--session-workspaces", type=Path)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--no-open", action="store_true", help="explicit service-only mode for diagnostics or browser QA")
    parser.add_argument("--reconnect", action="store_true", help="recover an absent service while preserving a healthy running version")
    parser.add_argument("--update", action="store_true", help="explicitly replace an idle managed service with current source")
    parser.add_argument("--recover-stalled-turn", metavar="TURN_ID", help="retire the managed service whose one active turn is stalled (all of --project, --session, --expected-pid, --expected-start-tick)")
    parser.add_argument("--project")
    parser.add_argument("--session")
    parser.add_argument("--expected-pid", type=int)
    parser.add_argument("--expected-start-tick")
    args = parser.parse_args(argv)
    if sum(bool(value) for value in (args.status,args.stop,args.no_open,args.reconnect,args.update,args.recover_stalled_turn)) > 1:
        parser.error("choose one service action")
    if args.recover_stalled_turn and not (args.project and args.session and args.expected_pid and args.expected_start_tick):
        parser.error("--recover-stalled-turn requires --project, --session, --expected-pid and --expected-start-tick")
    try:
        extra = {"workspace_root": args.workspace_root, "engine_state": args.engine_state, "session_workspaces": args.session_workspaces} if args.workspace_root is not None or args.engine_state is not None or args.session_workspaces is not None else {}
        if args.status:
            result = status(root=args.repo_root, state=args.state, host=args.host, port=args.port, **extra)
        elif args.stop:
            result = stop(root=args.repo_root, state=args.state, **extra)
        elif args.recover_stalled_turn:
            result = recover_stalled_turn(root=args.repo_root, state=args.state, project=args.project, session_id=args.session,
                                          turn_id=args.recover_stalled_turn, expected_pid=args.expected_pid,
                                          expected_start_tick=args.expected_start_tick, **extra)
        elif args.reconnect:
            result = ensure_server(root=args.repo_root, state=args.state, host=args.host,
                                   port=args.port, allow_update=False, **extra)
        elif args.update:
            result = ensure_server(root=args.repo_root, state=args.state, host=args.host,
                                   port=args.port, allow_update=True, **extra)
        elif args.no_open:
            result = ensure_server(root=args.repo_root, state=args.state, host=args.host,
                                   port=args.port, allow_update=False, **extra)
        else:
            # Gtk.Application presents an existing window on repeated activation;
            # it starts/checks the pinned backend only when creating its own window.
            command = native_command(args.repo_root, args.state, args.host, args.port, **extra)
            os.execv(command[0], command)  # no idle launcher interpreter alongside the app
            return 0
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0
    except (WritingAppError, OSError, subprocess.SubprocessError) as exc:
        print(f"WRITING APP REFUSED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
