"""Bounded host observations, not a service launcher or a capability verdict.

Only same-user processes, a fixed unit list, and named launcher declarations are
inspected. Command lines are used for exact executable/module identification but
never returned; prompts, generic environment values and device state stay out.
"""
from __future__ import annotations
from laplace.core.checkout import repo_root as _repo_root   # the serving checkout, as the scanner resolved it

import json
import os
import shlex
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

UNITS = ("eigen-face.service", "eigen-front.service", "laplace-atlas-watcher.service",
         "otter-ingest.path", "otter-ingest.service")
STATE_ENV = ("LAPLACE_STATE", "LAPLACE_EIGEN_STATE", "LAPLACE_ROOT")
MODULES = {
    "laplace.web.scanner": "scanner", "laplace.representation.atlas_watcher": "atlas-watcher",
    "laplace.representation.codex_seat_watcher": "provider-attention-watcher",
    "laplace.desktop.offline_launcher": "launcher", "laplace.engine.keeper": "upfold",
}
SCRIPTS = {
    "wake.py": "opening", "reconstruct_node.py": "reconstruction",
    "sewup.py": "close", "reembed.py": "upfold", "runtime_truth.py": "runtime-observer",
    "ingest_otter.py": "otter-ingestion", "ensure_state.py": "state-check",
    "workflow.py": "workflow-coordinator",
}
HOSTS = {"codex": "codex-shared-host", "codex-code-mode-host": "codex-tool-host",
         "ChatGPT": "codex-desktop", "claude": "claude-session",
         "claude-desktop": "claude-desktop"}


def _read(path: Path, limit: int = 16384) -> bytes:
    with path.open("rb") as stream:
        return stream.read(limit)


def _link(path: Path) -> str | None:
    try:
        return os.readlink(path)
    except OSError:
        return None


def _target(args: list[str]) -> tuple[str | None, str | None]:
    """Identify Python's execution target without searching code/prompt arguments."""
    index = 1
    while index < len(args) and args[index] in {"-I", "-B", "-S", "-u", "-s", "-E"}:
        index += 1
    if index >= len(args):
        return None, None
    target = args[index]
    if target == "-m":
        return (args[index + 1], None) if index + 1 < len(args) else (None, None)
    if target.startswith("-"):
        return None, None
    if Path(target).name == "laplace_python.py" and Path(target).parent.name == "scripts":
        # The wrapper's own target follows the same Python-style interface.
        nested, _ = _target([args[0], *args[index + 1:]])
        return nested, str(Path(target).parent.parent) if Path(target).is_absolute() else None
    return target, None


def _processes(root: Path, proc: Path, *, uid: int, caller_pid: int,
               max_entries: int, max_matches: int) -> dict:
    rows, errors = [], 0
    visited, truncated = 0, False
    try:
        entries = os.scandir(proc)
    except OSError as exc:
        return {"status": "UNAVAILABLE", "reason": type(exc).__name__, "items": []}
    with entries:
        for entry in entries:
            if not entry.name.isdecimal():
                continue
            visited += 1
            if visited > max_entries:
                truncated = True
                break
            path, pid = Path(entry.path), int(entry.name)
            try:
                if entry.stat(follow_symlinks=False).st_uid != uid:
                    continue
                exe, cwd = _link(path / "exe"), _link(path / "cwd")
                name = Path(exe).name if exe else _read(path / "comm", 128).decode(errors="replace").strip()
                python = name.startswith("python") or name in {"pypy", "pypy3"}
                in_checkout = cwd == str(root) or bool(cwd and cwd.startswith(str(root) + "/"))
                # Shell/Python work in this checkout can belong to a sibling agent.
                candidate = pid == caller_pid or name in HOSTS or python or (in_checkout and name in {"bash", "sh", "pytest"})
                if not candidate:
                    continue
                # Host/shell arguments may carry prompts; their executable/cwd is enough.
                args = _read(path / "cmdline", 32768).decode(errors="replace").split("\0") if python else []
                target, source = _target(args) if python else (None, None)
                role = HOSTS.get(name)
                if name == "codex":
                    # Inspect only the executable's verb and -C binding; never return argv.
                    host_args = _read(path / "cmdline", 32768).decode(errors="replace").split("\0")
                    verb = host_args[1] if len(host_args) > 1 else ""
                    role = "codex-shared-host" if verb == "app-server" else "codex-provider"
                    if verb == "exec":
                        role = "codex-workflow-worker"
                        if "-C" in host_args and host_args.index("-C") + 1 < len(host_args):
                            source = host_args[host_args.index("-C") + 1]
                if target in MODULES:
                    role = MODULES[target]
                elif target and Path(target).name in SCRIPTS:
                    target_path = Path(target)
                    if not target_path.is_absolute() and cwd:
                        target_path = Path(cwd) / target_path
                    if target_path.parent.name == "scripts":
                        role = SCRIPTS[target_path.name]
                        source = source or str(target_path.parent.parent)
                if not role and not (pid == caller_pid or in_checkout):
                    continue
                role = role or ("caller" if pid == caller_pid else "transient-tool-purpose-unverified")
                stat = _read(path / "stat", 4096).decode().rsplit(")", 1)[1].split()
                environment = {}
                for value in _read(path / "environ", 65536).split(b"\0"):
                    key, _, value = value.partition(b"=")
                    if key.decode(errors="replace") in STATE_ENV:
                        environment[key.decode()] = value.decode(errors="replace")
                rows.append({
                    "pid": pid, "parent_pid": int(stat[1]), "role": role,
                    "is_caller": pid == caller_pid, "executable": exe, "cwd": cwd,
                    "execution_target": target,
                    "source_root_declared_by_command": source,
                    "state_environment": environment,
                    "imported_source_and_state_verified": False,
                    "task_attribution": ("shared host; individual tasks unknown" if role in {"codex-shared-host", "codex-tool-host", "codex-desktop"} else
                                         "provider process; task identity unknown" if name in HOSTS else
                                         "unknown; may be this task or a sibling"),
                    "cpu_seconds_total": round((int(stat[11]) + int(stat[12])) / os.sysconf("SC_CLK_TCK"), 3),
                    "rss_bytes": int(stat[21]) * os.sysconf("SC_PAGE_SIZE"),
                })
                if len(rows) >= max_matches:
                    truncated = True
                    break
            except (OSError, ValueError, IndexError):
                errors += 1  # A process may exit between directory and file reads.
    return {"status": "PARTIAL" if truncated or errors else "OBSERVED",
            "items": sorted(rows, key=lambda row: row["pid"]),
            "entries_examined": min(visited, max_entries), "truncated": truncated,
            "unreadable_or_exited": errors,
            "scope": "same UID at observation time; absence is not a permanent no-work claim"}


def _services(run) -> dict:
    properties = ("Id", "LoadState", "ActiveState", "SubState", "UnitFileState",
                  "MainPID", "FragmentPath", "WorkingDirectory")
    command = ["systemctl", "--user", "show", *UNITS, "--no-pager",
               "--property=" + ",".join(properties)]
    try:
        result = run(command, capture_output=True, text=True, timeout=0.8, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "UNAVAILABLE", "reason": type(exc).__name__, "items": []}
    parsed = {}
    for block in result.stdout.split("\n\n"):
        row = dict(line.split("=", 1) for line in block.splitlines() if "=" in line)
        if row.get("Id") in UNITS:
            parsed[row["Id"]] = {key: row[key] for key in properties if key in row}
    rows = [parsed.get(unit, {"Id": unit, "LoadState": "UNKNOWN"}) for unit in UNITS]
    return {"status": "OBSERVED" if result.returncode == 0 and len(parsed) == len(UNITS) else "PARTIAL",
            "returncode": result.returncode, "items": rows,
            "meaning": "configured service state only; no service started or capability tested"}


def _declarations(root: Path, home: Path) -> dict:
    """Only named config facts; never execute a unit, shell expansion or launcher."""
    result = {"front_launcher": {"status": "ABSENT"}, "units": []}
    config = home / ".config/eigen/front-launch.json"
    if config.exists():
        try:
            value = json.loads(_read(config, 131072))
            result["front_launcher"] = {
                "status": "OBSERVED", "path": str(config),
                **{key: value.get(key) for key in ("checkout", "expected_commit", "allow_descendant", "service", "port")},
                "checkout_matches_observed_root": value.get("checkout") == str(root),
                "meaning": "dormant declaration, not proof of a running process",
            }
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            result["front_launcher"] = {"status": "UNAVAILABLE", "reason": type(exc).__name__, "path": str(config)}
    paths = [home / ".config/systemd/user" / unit for unit in UNITS]
    paths += [root / "src/laplace/desktop/deploy" / unit for unit in UNITS[:3]]
    paths += [root / "systemd/eigen-face.service"]
    for path in paths:
        if not path.exists() and not path.is_symlink():
            continue
        row = {"path": str(path), "status": "DECLARED"}
        if path.is_symlink():
            row.update({"symlink_target": str(path.resolve()), "status": "MASKED" if str(path.resolve()) == "/dev/null" else "SYMLINK"})
        else:
            try:
                for line in _read(path, 32768).decode(errors="replace").splitlines():
                    if line.startswith("WorkingDirectory="):
                        row["working_directory"] = line.partition("=")[2]
                    elif line.startswith("ExecStart="):
                        args = shlex.split(line.partition("=")[2])
                        executable = args[0] if args else None
                        row["declared_executable"] = executable
                        row["uses_laplace_wrapper"] = bool(executable and executable.endswith("/scripts/laplace-python"))
            except (OSError, ValueError) as exc:
                row.update(status="UNAVAILABLE", reason=type(exc).__name__)
        result["units"].append(row)
    return result


def observe(repo_root: Path | str, *, proc_root: Path | str = "/proc",
            home: Path | None = None, run=None, max_entries: int = 4096,
            max_matches: int = 48) -> dict:
    """Observe without importing the engine, opening stores, contacting a device or writing."""
    started = time.monotonic()
    root = Path(repo_root).resolve()
    return {
        "schema": "laplace.process-health/1", "observed_at": datetime.now(timezone.utc).isoformat(),
        "source_root": str(root),
        "processes": _processes(root, Path(proc_root), uid=os.getuid(), caller_pid=os.getpid(),
                                max_entries=max_entries, max_matches=max_matches),
        "services": _services(run or subprocess.run),
        "launch_declarations": _declarations(root, home or Path.home()),
        "device_execution": "NOT_TESTED", "store_health": "NOT_TESTED",
        "elapsed_seconds": round(time.monotonic() - started, 4),
    }


# ---- moved from laplace.web.scanner (2026-10-21, core native/physical closure)
_HEAVY_IGNORED_DIAL_MB = 50   # the declared dial (FIND-SE-008): an ignored top-level dir over this is LOUD


# declared standing residents, named exempt never silent: walk tooling + the suite's own
# cache residue (also keeps tool names out of the probe's argv - the wake's no-pytest
# guard reads spawned command strings).
_HEAVY_IGNORED_RESIDENTS = {"node_modules", ".pytest_cache", "__pycache__", ".ruff_cache", ".mypy_cache"}


def ignored_heavyweights() -> list[dict]:
    """FIND-SE-008's sweep: the box must not lie through the ignore file. A 208M
    suite-built ``.venv`` sat at repo root while probe, --relay-ready and the
    porcelain sweep all certified clean - gitignored mass is invisible to every
    porcelain instrument. So: any ``.venv`` at repo root is a LOUD finding always
    (on this box a venv appearing is never a shrug - installs are hand acts), and
    any other top-level gitignored directory over the declared dial is named.
    Residents are exempt BY NAME above. Cost: one git check-ignore + du only on
    non-resident ignored dirs (normally zero)."""
    root = _repo_root()
    findings: list[dict] = []
    try:
        dirs = [p.name for p in Path(root).iterdir()
                if p.is_dir() and p.name != ".git" and p.name not in _HEAVY_IGNORED_RESIDENTS]
        if not dirs:
            return findings
        r = subprocess.run(["git", "check-ignore", "--", *dirs], cwd=str(root),
                           capture_output=True, text=True, timeout=10)
        cap = _HEAVY_IGNORED_DIAL_MB * 1024 * 1024
        def _size_floor(top: Path) -> tuple[int, bool]:
            """In-process bounded walk (the probe spawns git ONLY - the no-pytest guard
            reads spawned argv): total bytes, early-stopped once the dial is crossed.
            Returns (bytes_seen, crossed)."""
            total = 0
            stack = [top]
            while stack:
                d = stack.pop()
                try:
                    with os.scandir(d) as it:
                        for e in it:
                            try:
                                if e.is_dir(follow_symlinks=False):
                                    stack.append(Path(e.path))
                                elif e.is_file(follow_symlinks=False):
                                    total += e.stat(follow_symlinks=False).st_size
                                    if total >= cap:
                                        return total, True
                            except OSError:
                                continue
                except OSError:
                    continue
            return total, False
        for name in (n for n in r.stdout.splitlines() if n.strip()):
            if name in _HEAVY_IGNORED_RESIDENTS:
                continue
            is_venv = name == ".venv" or name.endswith(".venv")
            size, crossed = _size_floor(Path(root) / name)
            if is_venv or crossed:
                findings.append({"dir": name,
                                 "size_mb": (size // (1024 * 1024)) if not crossed
                                            else _HEAVY_IGNORED_DIAL_MB,
                                 "size_is_floor": crossed,
                                 "why": ("a venv at repo root is never a shrug (installs are "
                                         "hand acts; FIND-SE-008)" if is_venv else
                                         f"ignored dir over the {_HEAVY_IGNORED_DIAL_MB}MB dial")})
    except Exception as exc:  # noqa: BLE001 - the sweep degrades LOUD as a finding, never silently
        findings.append({"dir": "?", "size_mb": None,
                         "why": f"ignored-heavyweight sweep failed: {type(exc).__name__}: {exc}"[:160]})
    return findings


def probe() -> dict:
    """The hello's live probe as one warm GET: git facts + the at-grade inherit verdict shape.
    Subprocess git inside the warm process (~50ms), never a fresh PowerShell.

    A git fact is earned or it is absent, never assumed. This verdict is what the wake uses to skip
    verification, so a git that died (no git on PATH, a foreign root, a locked index, the timeout,
    any nonzero rc) must not read as a clean tree - it did, because ``_git`` returned "" for both
    that and a genuine empty answer. A failed call now returns ``None`` and rides as
    ``probe_failed``/``probe_health`` under a verdict that forbids inheriting; so does an empty
    ``branch``/``head``, which live git never prints. Keys are additive: every field the old dict
    carried is still there and still the same type."""
    import subprocess

    failures: list[str] = []

    def _git(*args: str) -> str | None:
        """The stdout of one git fact, or ``None`` - not obtained, reason banked in ``failures``."""
        label = "git " + " ".join(args)
        try:
            r = subprocess.run(["git", *args], cwd=str(_repo_root()), capture_output=True,
                               text=True, timeout=10, encoding="utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001 - the failure is named, never swallowed
            failures.append(f"{label}: {type(exc).__name__}: {exc}"[:160])
            return None
        if r.returncode != 0:
            why = ((r.stderr or "").strip().splitlines() or [""])[0]
            failures.append(f"{label}: rc={r.returncode} {why}".strip()[:160])
            return None
        # rstrip, not strip: porcelain's leading XY column is load-bearing (" M path"), and a
        # full strip ate the first line's status char, so dirty_files[0] lost a letter of its path.
        return (r.stdout or "").rstrip()

    status = _git("status", "--porcelain")
    git_root = _git("rev-parse", "--show-toplevel")
    source_root = Path(_repo_root()).resolve()
    if git_root is not None and (
        not git_root or Path(git_root).resolve() != source_root
    ):
        failures.append(f"Git root {git_root!r} does not match source root {source_root}")
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    head = _git("rev-parse", "--short", "HEAD")
    last_commit = _git("log", "-1", "--pretty=%h %s")
    # detached HEAD prints the literal "HEAD" and a live branch is never blank, so blank means
    # the fact did not arrive even though git exited 0.
    for name, val in (("branch", branch), ("head", head)):
        if val is not None and not val:
            failures.append(f"git returned an empty {name} (rc=0 but no fact)")
    dirty = [ln for ln in (status or "").splitlines() if ln.strip()]
    heavy = ignored_heavyweights()
    if failures:
        verdict = ("GIT PROBE FAILED (" + "; ".join(failures[:3]) + ") - the tree state is "
                   "UNKNOWN; do NOT inherit the banked green, verify SCOPED")
    elif heavy:
        verdict = ("IGNORED-HEAVYWEIGHT on the tree ("
                   + ", ".join(f"{h['dir']}={h['size_mb']}MB" for h in heavy)
                   + ") - the ignore file is hiding mass; adjudicate it before trusting clean")
    elif dirty:
        verdict = "tree moved - verify SCOPED (the changed shard, never the flat suite)"
    else:
        verdict = ("clean tree - no source delta; prior evidence applies only within its "
                   "recorded scope, and this probe runs no tests")
    return {"source_root": str(source_root), "git_root": git_root,
            "branch": branch or "", "head": head or "", "last_commit": (last_commit or "")[:200],
            "dirty": len(dirty), "dirty_files": [ln[3:] for ln in dirty][:20],
            "ignored_heavyweights": heavy,
            "probe_failed": bool(failures),
            "probe_health": {"ok": not failures, "failures": failures},
            "verdict": verdict}
