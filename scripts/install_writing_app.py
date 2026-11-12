#!/usr/bin/env python3
"""Install or remove the per-user Writing App desktop entry.

It has no systemd unit and no autostart entry: the desktop click invokes the
on-demand, loopback-only launcher.  The installer is deliberately separate
from the older Eigen front launcher and never changes that launcher's files.
"""
from __future__ import annotations

import argparse
import os
import shlex
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from laplace.desktop import writing_app  # noqa: E402
from laplace.desktop import managed_homes  # noqa: E402


def _desktop_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _atomic_write(path: Path, content: str, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def svg() -> str:
    return """<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"64\" height=\"64\" viewBox=\"0 0 64 64\">
<rect width=\"64\" height=\"64\" rx=\"12\" fill=\"#243447\"/><path d=\"M17 14h30v36H17z\" fill=\"#f7f1e3\"/>
<path d=\"M24 25h16M24 32h16M24 39h11\" stroke=\"#243447\" stroke-width=\"3\" stroke-linecap=\"round\"/>
<path d=\"M41 39l8-8 3 3-8 8-5 1z\" fill=\"#e67e22\"/></svg>\n"""


def render(*, checkout: Path, desktop_path: Path, icon_path: Path, workspace_root=None,
           state=None, engine_state=None, session_workspaces=None) -> dict[str, Any]:
    checkout = checkout.resolve()
    launcher = checkout / "src" / "laplace" / "desktop" / "writing_app.py"
    if not launcher.is_file():
        raise ValueError(f"Writing App module not found: {launcher}")
    # A desktop process has no checkout cwd/PYTHONPATH. The repository wrapper
    # selects the pinned runtime and source paths itself, including after updates.
    command = [str(checkout / "scripts" / "laplace-python"), "-m", "laplace.desktop.writing_app", "--repo-root", str(checkout)]
    homes = None
    if workspace_root is not None:
        homes = managed_homes.resolve(checkout, state=state, workspace_root=workspace_root,
            engine_state=engine_state, session_workspaces=session_workspaces)
        for flag, key in (('--workspace-root','workspace_root'),('--state','receipt'),
                          ('--engine-state','engine_state'),('--session-workspaces','session_workspaces')):
            command.extend((flag, homes[key]))
    elif engine_state is not None or session_workspaces is not None:
        raise ValueError('Engine/session selection requires explicit --workspace-root')
    elif state is not None:
        command.extend(('--state', str(Path(state).expanduser().resolve())))
    desktop = "\n".join((
        "[Desktop Entry]", "Version=1.0", "Type=Application", "Name=Laplace Writing App",
        "GenericName=Research and manuscript development", "Comment=Standalone research, evidence and writing workspace",
        "Exec=" + " ".join(_desktop_quote(item) for item in command), "Icon=laplace-writing",
        "Terminal=false", "Categories=Office;Science;Development;", "StartupNotify=true",
        "StartupWMClass=LaplaceWritingApp", "",))
    return {"schema_version": "laplace.writing-app-install/1", "checkout": str(checkout),
            **({'managed_homes': homes} if homes else {}),
            "launch_command": " ".join(shlex.quote(item) for item in command), "files": [
                {"path": str(desktop_path), "content": desktop, "mode": "0644"},
                {"path": str(icon_path), "content": svg(), "mode": "0644"},
            ]}


def install(plan: dict[str, Any]) -> None:
    for item in plan["files"]:
        _atomic_write(Path(item["path"]), item["content"], int(item["mode"], 8))


def uninstall(desktop_path: Path, icon_path: Path) -> dict[str, bool]:
    result = {}
    for path in (desktop_path, icon_path):
        existed = path.exists()
        path.unlink(missing_ok=True)
        result[str(path)] = existed
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install the per-user Laplace Writing App launcher.")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--install", action="store_true")
    action.add_argument("--uninstall", action="store_true")
    parser.add_argument("--checkout", type=Path, default=REPO_ROOT)
    parser.add_argument("--workspace-root", type=Path, help="existing data workspace; never executable source")
    parser.add_argument("--state", type=Path, help="managed receipt file")
    parser.add_argument("--engine-state", type=Path, help="engine state directory (with --workspace-root)")
    parser.add_argument("--session-workspaces", type=Path, help="provider cwd directory (with --workspace-root)")
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    parser.add_argument("--applications-dir", type=Path, default=data_home / "applications")
    parser.add_argument("--icons-dir", type=Path, default=data_home / "icons" / "hicolor" / "scalable" / "apps")
    args = parser.parse_args(argv)
    desktop_path = args.applications_dir.expanduser() / "laplace-writing-app.desktop"
    icon_path = args.icons_dir.expanduser() / "laplace-writing.svg"
    try:
        if args.uninstall:
            result: dict[str, Any] = {"uninstalled": uninstall(desktop_path, icon_path)}
        else:
            result = render(checkout=args.checkout.expanduser(), desktop_path=desktop_path, icon_path=icon_path,
                workspace_root=args.workspace_root, state=args.state, engine_state=args.engine_state,
                session_workspaces=args.session_workspaces)
            install(result)
            result["installed"] = True
        print(__import__("json").dumps(result, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError) as exc:
        print(f"WRITING APP INSTALL REFUSED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
