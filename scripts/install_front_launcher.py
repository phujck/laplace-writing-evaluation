#!/usr/bin/env python3
"""Render/install the pinned Eigen desktop front launcher.

The default is a dry run.  ``--install`` is an explicit operator act; tests and
ordinary repository work never write into the desktop or systemd user dirs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from laplace.desktop import desktop_front  # noqa: E402


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _systemd_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _systemd_directory(value: str) -> str:
    """Render WorkingDirectory as a systemd path, whose quotes are literal."""

    path = Path(value)
    if not path.is_absolute() or any(char in value for char in "\r\n"):
        raise ValueError("systemd working directory must be one absolute line")
    return value.replace("%", "%%").replace(" ", "\\x20")


def _desktop_quote(value: str) -> str:
    # Desktop Entry Exec quoting is not shell quoting.  Backslash and quote are
    # the only characters needing protection inside a double-quoted argument.
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _browser_command(explicit: str | None = None) -> list[str]:
    if explicit:
        executable = shutil.which(explicit) if "/" not in explicit else explicit
        if not executable or not Path(executable).is_file():
            raise desktop_front.LaunchRefusal(
                "BROWSER-UNAVAILABLE",
                f"requested browser executable is absent: {explicit}",
                "install it or omit --browser to select an available desktop browser",
            )
        name = Path(executable).name
        return [str(executable), "--app={url}"] if name in {"google-chrome", "chromium", "chromium-browser"} else [str(executable), "{url}"]
    for candidate in ("google-chrome", "chromium", "chromium-browser"):
        executable = shutil.which(candidate)
        if executable:
            return [executable, "--app={url}"]
    opener = shutil.which("xdg-open")
    if opener:
        return [opener, "{url}"]
    raise desktop_front.LaunchRefusal(
        "BROWSER-UNAVAILABLE",
        "no google-chrome, chromium, chromium-browser or xdg-open was found",
        "install a desktop browser before installing the Eigen launcher",
    )


def render_bundle(
    *,
    checkout: Path,
    config_path: Path,
    service_path: Path,
    desktop_path: Path,
    state_log: Path,
    service: str,
    host: str,
    port: int,
    allow_descendant: bool,
    browser_command: list[str],
) -> dict[str, Any]:
    checkout = checkout.resolve()
    seed = {
        "checkout": str(checkout),
        "expected_commit": subprocess.check_output(
            ["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True
        ).strip(),
        "expected_tree": subprocess.check_output(
            ["git", "-C", str(checkout), "rev-parse", "HEAD^{tree}"], text=True
        ).strip(),
        "allow_descendant": allow_descendant,
        "expected_contract_sha256": desktop_front._sha256(
            checkout / "contract" / "surfaces" / "front.yaml"
        ),
        "expected_model_schema": desktop_front.MODEL_SCHEMA,
        "host": host,
        "port": port,
        "service": service,
        "browser_command": browser_command,
        "startup_timeout_seconds": 30.0,
        "state_log": str(state_log),
    }
    config = {"schema_version": desktop_front.CONFIG_SCHEMA, **seed}
    # Reuse the product verifier before rendering any destination bytes.
    desktop_front.verify_checkout(config)

    launcher = checkout / "src" / "laplace" / "desktop" / "desktop_front.py"
    serve_args = [
        "/usr/bin/python3",
        str(launcher),
        "serve",
        "--checkout",
        str(checkout),
        "--expected-commit",
        seed["expected_commit"],
        "--expected-tree",
        seed["expected_tree"],
        "--expected-contract-sha256",
        seed["expected_contract_sha256"],
        "--expected-model-schema",
        seed["expected_model_schema"],
        "--host",
        host,
        "--port",
        str(port),
    ]
    if allow_descendant:
        serve_args.append("--allow-descendant")
    service_text = "\n".join(
        (
            "[Unit]",
            "Description=Eigen front — verified next-generation carrier",
            "After=default.target",
            "",
            "[Service]",
            "Type=simple",
            f"WorkingDirectory={_systemd_directory(str(checkout))}",
            "ExecStart=" + " ".join(_systemd_quote(arg) for arg in serve_args),
            "Restart=on-failure",
            "RestartSec=3",
            "",
            "[Install]",
            "WantedBy=default.target",
            "",
        )
    )
    desktop_exec = [
        "/usr/bin/python3",
        str(launcher),
        "open",
        "--config",
        str(config_path),
    ]
    desktop_text = "\n".join(
        (
            "[Desktop Entry]",
            "Version=1.0",
            "Type=Application",
            "Name=Eigen",
            "GenericName=Eigen causal workspace",
            "Comment=Open the verified next-generation Eigen front carrier",
            "Exec=" + " ".join(_desktop_quote(arg) for arg in desktop_exec),
            "Icon=applications-science",
            "Terminal=false",
            "Categories=Development;Science;",
            "StartupNotify=true",
            "StartupWMClass=Eigen",
            "",
        )
    )
    config_bytes = (json.dumps(config, indent=2, sort_keys=True) + "\n").encode("utf-8")
    service_bytes = service_text.encode("utf-8")
    desktop_bytes = desktop_text.encode("utf-8")
    return {
        "schema_version": "laplace.desktop-front-install-plan/1",
        "mode": "DESCENDANT" if allow_descendant else "EXACT",
        "checkout": str(checkout),
        "expected_commit": seed["expected_commit"],
        "expected_tree": seed["expected_tree"],
        "expected_contract_sha256": seed["expected_contract_sha256"],
        "launch_command": " ".join(shlex.quote(arg) for arg in desktop_exec),
        "probe_command": " ".join(
            shlex.quote(arg)
            for arg in (
                "/usr/bin/python3",
                str(launcher),
                "probe",
                "--config",
                str(config_path),
            )
        ),
        "files": [
            {
                "path": str(config_path),
                "mode": "0600",
                "bytes": len(config_bytes),
                "sha256": _sha256_bytes(config_bytes),
                "content": config_bytes.decode("utf-8"),
            },
            {
                "path": str(service_path),
                "mode": "0644",
                "bytes": len(service_bytes),
                "sha256": _sha256_bytes(service_bytes),
                "content": service_text,
            },
            {
                "path": str(desktop_path),
                "mode": "0644",
                "bytes": len(desktop_bytes),
                "sha256": _sha256_bytes(desktop_bytes),
                "content": desktop_text,
            },
        ],
    }


def _atomic_write(path: Path, content: str, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temp.chmod(mode)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def install(plan: dict[str, Any]) -> None:
    for item in plan["files"]:
        _atomic_write(Path(item["path"]), item["content"], int(item["mode"], 8))
    proc = subprocess.run(
        ["systemctl", "--user", "daemon-reload"],
        text=True,
        capture_output=True,
        timeout=20,
    )
    if proc.returncode != 0:
        raise desktop_front.LaunchRefusal(
            "SYSTEMD-RELOAD-FAILED",
            (proc.stderr or proc.stdout or "systemctl returned no detail").strip(),
            "run systemctl --user daemon-reload, then invoke the printed probe command",
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Dry-run or install the coordinate-pinned Eigen desktop launcher."
    )
    parser.add_argument("--checkout", type=Path, default=REPO_ROOT)
    parser.add_argument("--allow-descendant", action="store_true")
    parser.add_argument("--host", default=desktop_front.DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=desktop_front.DEFAULT_PORT)
    parser.add_argument("--service", default=desktop_front.DEFAULT_SERVICE)
    parser.add_argument("--browser", default=None)
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    state_home = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    parser.add_argument("--config-dir", type=Path, default=config_home / "eigen")
    parser.add_argument("--applications-dir", type=Path, default=data_home / "applications")
    parser.add_argument("--systemd-user-dir", type=Path, default=config_home / "systemd" / "user")
    parser.add_argument("--state-dir", type=Path, default=state_home / "eigen")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--install", action="store_true", help="write files and daemon-reload")
    mode.add_argument("--dry-run", action="store_true", help="print exact plan only (default)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config_path = args.config_dir.expanduser() / "front-launch.json"
        plan = render_bundle(
            checkout=args.checkout.expanduser(),
            config_path=config_path,
            service_path=args.systemd_user_dir.expanduser() / args.service,
            desktop_path=args.applications_dir.expanduser() / "eigen-front.desktop",
            state_log=args.state_dir.expanduser() / "front-launch.log",
            service=args.service,
            host=args.host,
            port=args.port,
            allow_descendant=args.allow_descendant,
            browser_command=_browser_command(args.browser),
        )
        if args.install:
            install(plan)
            plan = {**plan, "installed": True}
        else:
            plan = {**plan, "installed": False, "dry_run": True}
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0
    except (desktop_front.LaunchRefusal, OSError, subprocess.SubprocessError) as exc:
        if isinstance(exc, desktop_front.LaunchRefusal):
            message = exc.render()
        else:
            message = f"EIGEN FRONT INSTALL REFUSED\n{type(exc).__name__}: {exc}"
        print(message, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
