"""Foreground, checkout-bound browser Writing server.

This portable entrypoint never manages a daemon, opens GTK, selects a private
runtime, or falls back to the author's shared state directory.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

_configured_default: str | None = None


def _workspace_base(platform: str, home: Path, environ) -> Path:
    if platform == "win32":
        return Path(environ.get("LOCALAPPDATA") or home / "AppData" / "Local") / "Laplace"
    if platform == "darwin":
        return home / "Library" / "Application Support" / "Laplace"
    return Path(environ.get("XDG_DATA_HOME") or home / ".local" / "share") / "laplace"


def default_session_workspaces(checkout: Path, state: Path) -> Path:
    from laplace.desktop.managed_homes import default_session_workspaces as shared_default
    return shared_default(checkout, state)


def configure(root: Path | str, state: Path | str | None = None,
              session_workspaces: Path | str | None = None) -> tuple[Path,Path]:
    global _configured_default
    checkout=Path(root).expanduser().resolve()
    if not (checkout/"registry_projects.json").is_file():
        raise ValueError("Writing workspace requires registry_projects.json")
    if not (checkout/"profiles").is_dir():
        raise ValueError("Writing workspace requires profiles/")
    state_root=(Path(state).expanduser().resolve() if state is not None
                else checkout/".laplace-state")
    state_root.mkdir(parents=True,exist_ok=True)
    selected = session_workspaces or os.environ.get("LAPLACE_SESSION_WORKSPACES")
    # A deliberate reconfigure in one process must not mistake our last generated
    # default for a caller override, then share two checkouts' provider cwd.
    if session_workspaces is None and selected == _configured_default:
        selected = None
    workspace_root = (Path(selected).expanduser().resolve() if selected
                      else default_session_workspaces(checkout, state_root).resolve())
    _configured_default = str(workspace_root) if not selected else None
    os.environ.update(LAPLACE_REPO_ROOT=str(checkout),LAPLACE_STATE=str(state_root),
                      LAPLACE_SESSION_WORKSPACES=str(workspace_root),
                      LAPLACE_WRITING_APP="1",LAPLACE_NO_PREWARM="1")
    # A foreground server has no managed-daemon drain/stop receipt. Never inherit
    # another checkout's launcher lock, especially a POSIX-only lock on Windows.
    os.environ.pop("LAPLACE_WRITING_STATE", None)
    os.environ.pop("LAPLACE_WRITING_EXPECTED_SOURCE", None)
    os.environ.pop("LAPLACE_WRITING_EXPECTED_SELECTION", None)
    for key in ("LAPLACE_MANAGED_HOMES", "LAPLACE_WRITING_CODE_ROOT", "LAPLACE_WRITING_EXPECTED_WORKSPACE"):
        os.environ.pop(key, None)
    return checkout,state_root


def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(description="Foreground browser-only Laplace Writing server")
    parser.add_argument("--root",type=Path,default=Path.cwd(),help="exported Writing workspace checkout")
    parser.add_argument("--state",type=Path,
                        help="explicit isolated runtime state root (default ROOT/.laplace-state)")
    parser.add_argument("--session-workspaces", type=Path,
                        help="persistent provider cwd root; defaults to per-checkout platform user data. "
                             "LAPLACE_SESSION_WORKSPACES also selects it. Project instructions in "
                             "this directory or its ancestors still refuse provider turns.")
    parser.add_argument("--host",default="127.0.0.1")
    parser.add_argument("--port",type=int,default=8771)
    args=parser.parse_args(argv)
    try:root,_state=configure(args.root,args.state,args.session_workspaces)
    except (OSError,ValueError) as exc:parser.error(str(exc))
    from laplace.web import scanner
    scanner.serve(args.port,args.host,writing=True,repo_root=root)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
