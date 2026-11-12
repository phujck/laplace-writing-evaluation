"""Bounded process work: manifest one-liners under one platform qualification, and the optional call watchdog.

MANIFEST ONE-LINERS (the localstate.json law). The derived-state manifest's ``check``/``rebuild`` commands are
canonically POSIX (``test -f``, ``sh scripts/...``, ``.venv/bin/python``). On POSIX they run through the default
shell unchanged. On Windows they MUST NOT hit cmd.exe (where ``test``, ``[``, ``command -v`` and ``find`` all fail,
so every check reports STALE/MISSING and every printed fix is unrunnable — the 2026-07-14 local-walk finding): they
run through Git Bash (``sh.exe``) with the venv interpreter rewritten to the Windows ``Scripts/`` layout. Windows
handling is retained as written; this repository's evidence observes POSIX only.

ONE renderer (``normalize_cmd``) and ONE executor (``run_manifest_cmd``), shared by every consumer
(scripts/ensure_state.py, the offline launcher's offers, the dashboard chips), so a check cannot pass in one surface
and fail in another. The command shown is the command that runs: both are decided for the directory the command
runs in (``cwd``), never the caller's process directory, and the executed result carries the rendered command.

THE WATCHDOG (``guard``) is OFF by default (2026-06-08, the author's call): the fault it was built for — a Windows
git fsmonitor pipe deadlock — is gone (versioning is Dulwich, laplace.core.versioning) and every backing call is
inner-bounded, so an outer cap only abandons slow legitimate work. ``LAPLACE_WATCHDOG=on`` restores the cap. A
watchdog timeout means the CALLER stopped waiting: the work keeps running detached, and nothing is cancelled or
rolled back.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Callable


def _sh_exe() -> str | None:
    """Git Bash's ``sh`` on Windows; ``None`` on POSIX (shell=True is already sh)."""
    if os.name != "nt":
        return None
    for cand in ("sh.exe", "bash.exe"):
        p = shutil.which(cand)
        if p:
            return p
    # Git's default install locations, for a box where Git bin/ is not on PATH.
    for guess in (r"C:\Program Files\Git\bin\sh.exe",
                  r"C:\Program Files (x86)\Git\bin\sh.exe"):
        if Path(guess).is_file():
            return guess
    return None


def normalize_cmd(cmd: str, cwd: Path | str | None = None) -> str:
    """The manifest command as THIS platform runs it in ``cwd`` — and the exact string a human should be shown to
    copy-paste there. POSIX: unchanged, unless ``cwd`` has no ``.venv`` (the venv retirement, his ruling
    2026-08-21, evidence/VENV_RETIREMENT_2026-08-21/), when the venv interpreter becomes the live one. Windows: the
    venv interpreter rewritten to the ``Scripts/`` layout (forward slashes — valid in PowerShell and Git Bash).
    ``cwd`` None means the current directory."""
    if os.name == "nt":
        cmd = cmd.replace(".venv/bin/python", ".venv/Scripts/python.exe")
    elif ".venv/bin/python" in cmd and not (Path(cwd) if cwd is not None else Path(".")).joinpath(".venv/bin/python").exists():
        cmd = cmd.replace(".venv/bin/python", sys.executable or "python3")
    return cmd


def run_manifest_cmd(cmd: str, cwd, timeout: int = 600) -> subprocess.CompletedProcess:
    """Run one manifest one-liner in ``cwd`` with POSIX semantics on every platform, under the canonical env
    (PYTHONUTF8=1 — a child python printing box-drawing output must never die on cp1252). The result's ``args`` is
    what was executed; ``rendered`` is the command string ``normalize_cmd(cmd, cwd)`` shows."""
    rendered = normalize_cmd(cmd, cwd)
    env = {**os.environ, "PYTHONUTF8": "1"}
    sh = _sh_exe()
    if sh:
        proc = subprocess.run([sh, "-c", rendered], cwd=str(cwd), env=env,
                              capture_output=True, text=True, timeout=timeout)
    else:
        proc = subprocess.run(rendered, shell=True, cwd=str(cwd), env=env,
                              capture_output=True, text=True, timeout=timeout)
    proc.rendered = rendered
    return proc


_ENABLED = os.environ.get("LAPLACE_WATCHDOG", "off").strip().lower() in {"on", "1", "true", "yes"}


def guard(name: str, timeout: float, thunk: Callable[[], Any]) -> Any:
    """Run ``thunk``, optionally under a wall-clock cap on the caller's wait. Return its value, or a timeout dict.

    With the watchdog OFF (the default), the thunk runs INLINE: its value is returned and its exceptions propagate
    unchanged, with no cap. With it ON, the thunk runs on a daemon worker; when the wait passes ``timeout`` the
    caller receives a structured timeout dict while the worker continues, uncancelled.
    """
    if not _ENABLED:
        return thunk()
    box: dict[str, Any] = {}
    done = threading.Event()

    def _run() -> None:
        try:
            box["value"] = thunk()
        except BaseException as exc:  # noqa: BLE001 - re-raised on the caller thread
            box["error"] = exc
        finally:
            done.set()

    worker = threading.Thread(target=_run, name=f"laplace-{name}", daemon=True)
    worker.start()

    if not done.wait(timeout):
        return {
            "error": f"{name} exceeded its {timeout:.0f}s watchdog; the caller stopped waiting",
            "timed_out": True,
            "cancelled": False,
            "hint": (
                "The work was not cancelled or rolled back: it continues on a detached thread under its own "
                "inner bounds, and any effect it makes still lands. Inspect its owner's receipts before retrying. "
                "If this recurs, check for a wedged git or git-fsmonitor--daemon process holding a pipe open."
            ),
        }

    if "error" in box:
        raise box["error"]
    return box["value"]
