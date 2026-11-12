"""Pinned Linux desktop launcher for the human-facing Eigen carrier.

This is deliberately narrower than :mod:`laplace.desktop.offline_launcher`.  The
offline launcher remains the historical manuscript-review entry point.  A
desktop application icon, however, must never attach the author to an
uninspectable listener, an historical checkout, or a page which merely answers
HTTP while serving the wrong contract.

The installed launcher therefore proves three things before opening a window:

* the configured checkout is clean and is either the exact installed commit or
  an explicitly allowed descendant of it;
* the systemd user service is rooted in that checkout and its live process
  carries the exact source coordinate it imported;
* ``/front/model`` answers with the expected carrier schema.

There is no development/test-server fallback.  A failed proof is a loud,
actionable refusal and leaves any foreign service untouched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

CONFIG_SCHEMA = "laplace.desktop-front-launch/1"
SERVICE_SCHEMA = "laplace.desktop-front-service/1"
MODEL_SCHEMA = "laplace.aisthesis-front-model/1"
DEFAULT_SERVICE = "eigen-front.service"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8770
_HEX40 = re.compile(r"^[0-9a-f]{40}$")


class LaunchRefusal(RuntimeError):
    """A typed desktop-launch refusal with an operator-facing repair."""

    def __init__(self, code: str, detail: str, remedy: str) -> None:
        self.code = code
        self.detail = detail
        self.remedy = remedy
        super().__init__(f"{code}: {detail}")

    def render(self) -> str:
        return f"EIGEN FRONT REFUSED [{self.code}]\n{self.detail}\n\nFix: {self.remedy}"


@dataclass(frozen=True)
class CheckoutCoordinate:
    checkout: Path
    commit: str
    tree: str
    expected_commit: str
    expected_tree: str
    relation: str
    contract_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "checkout": str(self.checkout),
            "commit": self.commit,
            "tree": self.tree,
            "expected_commit": self.expected_commit,
            "expected_tree": self.expected_tree,
            "relation": self.relation,
            "contract_sha256": self.contract_sha256,
        }


@dataclass(frozen=True)
class ServiceIdentity:
    pid: int
    checkout: Path
    commit: str
    tree: str
    model_schema: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "pid": self.pid,
            "checkout": str(self.checkout),
            "commit": self.commit,
            "tree": self.tree,
            "model_schema": self.model_schema,
        }


def _default_config_path() -> Path:
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return config_home / "eigen" / "front-launch.json"


def _run(
    argv: Sequence[str],
    *,
    cwd: Path | None = None,
    timeout: float = 10.0,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(argv),
            cwd=str(cwd) if cwd else None,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=check,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise LaunchRefusal(
            "COMMAND-FAILED",
            f"{' '.join(argv)} could not be executed: {type(exc).__name__}: {exc}",
            "verify the published checkout and the systemd user session, then reinstall the Eigen launcher",
        ) from exc


def _git(checkout: Path, *args: str, check: bool = True) -> str:
    proc = _run(("git", "-C", str(checkout), *args), timeout=15.0)
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "git returned no detail").strip()
        raise LaunchRefusal(
            "CHECKOUT-GIT-REFUSED",
            detail,
            f"repair or reinstall from the intended published checkout: {checkout}",
        )
    return proc.stdout.strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_config(path: Path | str | None = None) -> dict[str, Any]:
    target = Path(path) if path else _default_config_path()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LaunchRefusal(
            "CONFIG-UNAVAILABLE",
            f"launcher configuration {target} is unreadable: {type(exc).__name__}: {exc}",
            "run scripts/install_front_launcher.py --install from the published checkout",
        ) from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != CONFIG_SCHEMA:
        raise LaunchRefusal(
            "CONFIG-SCHEMA-MISMATCH",
            f"{target} is not {CONFIG_SCHEMA}",
            "reinstall the launcher from the current published checkout",
        )
    payload["_config_path"] = str(target.resolve())
    return payload


def _required_string(config: Mapping[str, Any], key: str) -> str:
    value = str(config.get(key, "")).strip()
    if not value:
        raise LaunchRefusal(
            "CONFIG-INCOMPLETE",
            f"required configuration field {key!r} is absent",
            "reinstall the launcher to regenerate its complete pinned configuration",
        )
    return value


def verify_checkout(config: Mapping[str, Any], *, require_clean: bool = True) -> CheckoutCoordinate:
    checkout = Path(_required_string(config, "checkout")).expanduser()
    if not checkout.is_absolute():
        raise LaunchRefusal(
            "CHECKOUT-NOT-ABSOLUTE",
            f"configured checkout is relative: {checkout}",
            "reinstall with an absolute --checkout path",
        )
    checkout = checkout.resolve()
    required = (
        checkout / "src" / "laplace" / "web" / "scanner.py",
        checkout / "src" / "laplace" / "engine" / "front_carrier.py",
        checkout / "contract" / "surfaces" / "front.yaml",
    )
    absent = [str(path) for path in required if not path.is_file()]
    if absent:
        raise LaunchRefusal(
            "CHECKOUT-INCOMPLETE",
            "configured checkout is missing the published carrier files: " + ", ".join(absent),
            "point the launcher at the complete published Laplace checkout and reinstall",
        )

    expected_commit = _required_string(config, "expected_commit")
    expected_tree = _required_string(config, "expected_tree")
    if not _HEX40.fullmatch(expected_commit) or not _HEX40.fullmatch(expected_tree):
        raise LaunchRefusal(
            "CONFIG-COORDINATE-MALFORMED",
            "expected_commit and expected_tree must be full 40-character Git object ids",
            "reinstall from a verified published checkout",
        )

    commit = _git(checkout, "rev-parse", "HEAD")
    tree = _git(checkout, "rev-parse", "HEAD^{tree}")
    allow_descendant = config.get("allow_descendant") is True
    if commit == expected_commit:
        if tree != expected_tree:
            raise LaunchRefusal(
                "CHECKOUT-TREE-MISMATCH",
                f"HEAD is {commit}, but its tree is {tree}; expected {expected_tree}",
                "repair Git object integrity before opening Eigen",
            )
        relation = "EXACT"
    elif allow_descendant:
        relation_probe = _run(
            ("git", "-C", str(checkout), "merge-base", "--is-ancestor", expected_commit, commit),
            timeout=15.0,
        )
        if relation_probe.returncode != 0:
            raise LaunchRefusal(
                "CHECKOUT-NOT-ALLOWED-DESCENDANT",
                f"current HEAD {commit} is not a descendant of installed base {expected_commit}",
                "reinstall from the intended published line; do not force the launcher across histories",
            )
        relation = "DESCENDANT"
    else:
        raise LaunchRefusal(
            "CHECKOUT-MOVED",
            f"configured exact commit is {expected_commit}, but checkout HEAD is {commit}",
            "reinstall after the intended publication, or explicitly install with --allow-descendant",
        )

    if require_clean:
        dirty = _git(checkout, "status", "--porcelain", "--untracked-files=all")
        if dirty:
            preview = "\n".join(dirty.splitlines()[:12])
            raise LaunchRefusal(
                "CHECKOUT-DIRTY",
                f"the desktop face is pinned to published bytes, but this checkout has local changes:\n{preview}",
                "use a clean published checkout; preserve development work in its own worktree",
            )

    contract = required[2]
    contract_sha = _sha256(contract)
    expected_contract = str(config.get("expected_contract_sha256", "")).strip()
    if relation == "EXACT" and expected_contract and contract_sha != expected_contract:
        raise LaunchRefusal(
            "FRONT-CONTRACT-MOVED",
            f"front.yaml SHA-256 is {contract_sha}, expected {expected_contract}",
            "restore the published bytes or reinstall from the intended publication",
        )
    try:
        contract_text = contract.read_text(encoding="utf-8")
    except OSError as exc:
        raise LaunchRefusal(
            "FRONT-CONTRACT-UNREADABLE",
            f"cannot read {contract}: {exc}",
            "repair the checkout and reinstall",
        ) from exc
    expected_schema = str(config.get("expected_model_schema", MODEL_SCHEMA))
    if expected_schema not in contract_text:
        raise LaunchRefusal(
            "FRONT-CONTRACT-INCOMPATIBLE",
            f"{contract} does not declare {expected_schema}",
            "use a checkout containing the next-generation carrier contract",
        )
    return CheckoutCoordinate(
        checkout=checkout,
        commit=commit,
        tree=tree,
        expected_commit=expected_commit,
        expected_tree=expected_tree,
        relation=relation,
        contract_sha256=contract_sha,
    )


def _parse_systemctl_show(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key] = value
    return result


def systemctl_show(service: str) -> dict[str, str]:
    proc = _run(
        (
            "systemctl",
            "--user",
            "show",
            service,
            "--property=LoadState",
            "--property=ActiveState",
            "--property=SubState",
            "--property=MainPID",
            "--property=WorkingDirectory",
            "--property=ExecStart",
            "--property=FragmentPath",
        ),
        timeout=10.0,
    )
    if proc.returncode != 0:
        raise LaunchRefusal(
            "SERVICE-UNAVAILABLE",
            (proc.stderr or proc.stdout or f"systemctl could not inspect {service}").strip(),
            "run scripts/install_front_launcher.py --install, then try the Eigen icon again",
        )
    return _parse_systemctl_show(proc.stdout)


def _validate_unit(config: Mapping[str, Any], coordinate: CheckoutCoordinate, unit: Mapping[str, str]) -> None:
    service = _required_string(config, "service")
    if unit.get("LoadState") != "loaded":
        raise LaunchRefusal(
            "SERVICE-NOT-INSTALLED",
            f"systemd user service {service} is not loaded ({unit.get('LoadState', 'UNKNOWN')})",
            "run scripts/install_front_launcher.py --install and systemctl --user daemon-reload",
        )
    working_directory = Path(unit.get("WorkingDirectory") or "/").resolve()
    if working_directory != coordinate.checkout:
        raise LaunchRefusal(
            "SERVICE-WRONG-CHECKOUT",
            f"{service} uses {working_directory}; launcher is pinned to {coordinate.checkout}",
            "reinstall the service from the intended published checkout; the foreign service was left untouched",
        )
    exec_start = unit.get("ExecStart", "")
    launcher_path = str(coordinate.checkout / "src" / "laplace" / "desktop" / "desktop_front.py")
    if launcher_path not in exec_start or " serve " not in f" {exec_start} ":
        raise LaunchRefusal(
            "SERVICE-WRONG-COMMAND",
            f"{service} is not the pinned Eigen front service: {exec_start or '(empty ExecStart)'}",
            "reinstall the generated service; no existing listener was stopped",
        )
    required_tokens = (
        "--checkout",
        str(coordinate.checkout),
        "--expected-commit",
        coordinate.expected_commit,
        "--expected-tree",
        coordinate.expected_tree,
        "--expected-contract-sha256",
        str(config.get("expected_contract_sha256", "")),
        "--expected-model-schema",
        str(config.get("expected_model_schema", MODEL_SCHEMA)),
        "--host",
        str(config.get("host", DEFAULT_HOST)),
        "--port",
        str(int(config.get("port", DEFAULT_PORT))),
    )
    missing = [token for token in required_tokens if token and token not in exec_start]
    descendant_flag = "--allow-descendant" in exec_start
    if missing or descendant_flag != (config.get("allow_descendant") is True):
        detail = f"missing configured token(s): {missing}" if missing else "descendant policy differs"
        raise LaunchRefusal(
            "SERVICE-CONFIG-DISAGREEMENT",
            f"{service} does not match the pinned launcher configuration ({detail})",
            "reinstall the generated service; the existing service was left untouched",
        )


def _read_process_identity(pid: int) -> ServiceIdentity:
    if pid <= 0:
        raise LaunchRefusal(
            "SERVICE-NO-PROCESS",
            "systemd reports no live MainPID for the Eigen front service",
            "inspect journalctl --user -u eigen-front.service -n 80",
        )
    proc = Path("/proc") / str(pid)
    try:
        cwd = (proc / "cwd").resolve(strict=True)
        raw_env = (proc / "environ").read_bytes()
    except OSError as exc:
        raise LaunchRefusal(
            "SERVICE-IDENTITY-UNREADABLE",
            f"cannot inspect live service pid {pid}: {exc}",
            "do not reuse an unverified listener; inspect the systemd user journal",
        ) from exc
    env: dict[str, str] = {}
    for entry in raw_env.split(b"\0"):
        if b"=" not in entry:
            continue
        key, value = entry.split(b"=", 1)
        env[key.decode("utf-8", "replace")] = value.decode("utf-8", "replace")
    try:
        declared_checkout = Path(env["LAPLACE_DESKTOP_CHECKOUT"]).resolve()
        commit = env["LAPLACE_DESKTOP_SOURCE_COMMIT"]
        tree = env["LAPLACE_DESKTOP_SOURCE_TREE"]
        schema = env["LAPLACE_DESKTOP_MODEL_SCHEMA"]
        service_schema = env["LAPLACE_DESKTOP_SERVICE_SCHEMA"]
    except KeyError as exc:
        raise LaunchRefusal(
            "SERVICE-IDENTITY-MISSING",
            f"pid {pid} lacks the pinned desktop-service identity field {exc.args[0]}",
            "reinstall and restart the Eigen front service; do not reuse the historical scanner",
        ) from exc
    if service_schema != SERVICE_SCHEMA:
        raise LaunchRefusal(
            "SERVICE-SCHEMA-MISMATCH",
            f"pid {pid} carries {service_schema}, expected {SERVICE_SCHEMA}",
            "reinstall the current Eigen front service",
        )
    if declared_checkout != cwd:
        raise LaunchRefusal(
            "SERVICE-IDENTITY-DISAGREEMENT",
            f"pid {pid} declares {declared_checkout}, but runs from {cwd}",
            "stop and inspect the service; its live identity is internally inconsistent",
        )
    return ServiceIdentity(pid=pid, checkout=cwd, commit=commit, tree=tree, model_schema=schema)


def _systemctl_action(service: str, action: str) -> None:
    proc = _run(("systemctl", "--user", action, service), timeout=20.0)
    if proc.returncode != 0:
        raise LaunchRefusal(
            "SERVICE-ACT-FAILED",
            (proc.stderr or proc.stdout or f"systemctl {action} {service} failed").strip(),
            f"inspect journalctl --user -u {service} -n 80",
        )


def _identity_matches(
    identity: ServiceIdentity,
    coordinate: CheckoutCoordinate,
    expected_schema: str,
) -> bool:
    return (
        identity.checkout == coordinate.checkout
        and identity.commit == coordinate.commit
        and identity.tree == coordinate.tree
        and identity.model_schema == expected_schema
    )


def ensure_service(
    config: Mapping[str, Any],
    coordinate: CheckoutCoordinate,
    *,
    show: Callable[[str], dict[str, str]] = systemctl_show,
    action: Callable[[str, str], None] = _systemctl_action,
    identity_reader: Callable[[int], ServiceIdentity] = _read_process_identity,
    timeout: float = 20.0,
) -> tuple[str, ServiceIdentity]:
    service = _required_string(config, "service")
    expected_schema = str(config.get("expected_model_schema", MODEL_SCHEMA))
    unit = show(service)
    _validate_unit(config, coordinate, unit)
    active = unit.get("ActiveState") == "active" and int(unit.get("MainPID") or 0) > 0
    disposition = "REUSED"
    if active:
        identity = identity_reader(int(unit["MainPID"]))
        if identity.checkout != coordinate.checkout:
            raise LaunchRefusal(
                "LIVE-SERVICE-WRONG-CHECKOUT",
                f"pid {identity.pid} runs from {identity.checkout}, expected {coordinate.checkout}",
                "reinstall the intended service; the foreign process was left untouched",
            )
        if not _identity_matches(identity, coordinate, expected_schema):
            action(service, "restart")
            disposition = "RESTARTED-STALE"
    else:
        action(service, "start")
        disposition = "STARTED-COLD"

    deadline = time.monotonic() + timeout
    last = unit
    while time.monotonic() < deadline:
        last = show(service)
        if last.get("ActiveState") == "active" and int(last.get("MainPID") or 0) > 0:
            identity = identity_reader(int(last["MainPID"]))
            if not _identity_matches(identity, coordinate, expected_schema):
                raise LaunchRefusal(
                    "LIVE-SERVICE-COORDINATE-MISMATCH",
                    f"service identity is {identity.as_dict()}, checkout is {coordinate.as_dict()}",
                    "inspect the installed unit and service journal; the browser was not opened",
                )
            return disposition, identity
        time.sleep(0.15)
    raise LaunchRefusal(
        "COLD-START-SERVICE-TIMEOUT",
        f"{service} did not become active within {timeout:.1f}s (last state {dict(last)})",
        f"inspect journalctl --user -u {service} -n 80",
    )


def _front_model_url(config: Mapping[str, Any]) -> str:
    host = str(config.get("host", DEFAULT_HOST))
    port = int(config.get("port", DEFAULT_PORT))
    query = urllib.parse.urlencode({"lens": "now", "viewport": "wide"})
    return f"http://{host}:{port}/front/model?{query}"


def wait_for_front_model(
    config: Mapping[str, Any],
    *,
    timeout: float | None = None,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    expected_schema = str(config.get("expected_model_schema", MODEL_SCHEMA))
    wait = float(timeout if timeout is not None else config.get("startup_timeout_seconds", 30.0))
    deadline = time.monotonic() + wait
    url = _front_model_url(config)
    last_error = "no response"
    while time.monotonic() < deadline:
        try:
            request = urllib.request.Request(url, headers={"Accept": "application/json"})
            with opener(request, timeout=min(2.0, max(0.1, deadline - time.monotonic()))) as response:
                status = int(getattr(response, "status", 0))
                raw = response.read()
            if status != 200:
                last_error = f"HTTP {status}: {raw[:240].decode('utf-8', 'replace')}"
            else:
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise LaunchRefusal(
                        "FRONT-MODEL-NOT-JSON",
                        f"{url} returned invalid JSON: {exc}",
                        "inspect the Eigen service; the port may be serving another application",
                    ) from exc
                if not isinstance(payload, dict) or payload.get("schema_version") != expected_schema:
                    actual = payload.get("schema_version") if isinstance(payload, dict) else type(payload).__name__
                    raise LaunchRefusal(
                        "FRONT-MODEL-WRONG-CONTRACT",
                        f"{url} returned {actual!r}, expected {expected_schema!r}",
                        "stop the wrong service or reinstall the pinned Eigen front unit",
                    )
                if not isinstance(payload.get("shown_state"), dict):
                    raise LaunchRefusal(
                        "FRONT-MODEL-INCOMPLETE",
                        f"{url} returned the schema name without a shown_state",
                        "inspect the published carrier; do not open a partial model",
                    )
                return payload
        except LaunchRefusal:
            raise
        except urllib.error.HTTPError as exc:
            try:
                body = exc.read(240).decode("utf-8", "replace")
            except OSError:
                body = ""
            last_error = f"HTTP {exc.code}: {body}"
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        time.sleep(0.2)
    service = str(config.get("service", DEFAULT_SERVICE))
    raise LaunchRefusal(
        "COLD-START-FRONT-TIMEOUT",
        f"the verified service never produced {expected_schema} within {wait:.1f}s; last result: {last_error}",
        f"inspect journalctl --user -u {service} -n 80; the browser was not opened",
    )


def _browser_command(config: Mapping[str, Any], url: str) -> list[str]:
    configured = config.get("browser_command")
    if not isinstance(configured, list) or not configured or not all(isinstance(x, str) for x in configured):
        raise LaunchRefusal(
            "BROWSER-COMMAND-MISSING",
            "launcher configuration has no executable browser_command list",
            "reinstall the launcher so the available desktop browser is recorded explicitly",
        )
    command = [item.replace("{url}", url) for item in configured]
    executable = command[0]
    if "/" in executable:
        exists = Path(executable).is_file()
    else:
        exists = shutil.which(executable) is not None
    if not exists:
        raise LaunchRefusal(
            "BROWSER-UNAVAILABLE",
            f"configured browser executable is absent: {executable}",
            "install that browser or reinstall the launcher to select another desktop opener",
        )
    return command


def open_browser(config: Mapping[str, Any]) -> int:
    host = str(config.get("host", DEFAULT_HOST))
    port = int(config.get("port", DEFAULT_PORT))
    url = f"http://{host}:{port}/front"
    command = _browser_command(config, url)
    try:
        proc = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        raise LaunchRefusal(
            "BROWSER-START-FAILED",
            f"could not start {' '.join(command)}: {exc}",
            "verify the configured browser command, then retry the Eigen icon",
        ) from exc
    return proc.pid


def launch_front(
    config: Mapping[str, Any],
    *,
    no_browser: bool = False,
    show: Callable[[str], dict[str, str]] = systemctl_show,
    action: Callable[[str, str], None] = _systemctl_action,
    identity_reader: Callable[[int], ServiceIdentity] = _read_process_identity,
    model_waiter: Callable[[Mapping[str, Any]], dict[str, Any]] = wait_for_front_model,
    browser_opener: Callable[[Mapping[str, Any]], int] = open_browser,
) -> dict[str, Any]:
    started = time.monotonic()
    coordinate = verify_checkout(config)
    disposition, identity = ensure_service(
        config,
        coordinate,
        show=show,
        action=action,
        identity_reader=identity_reader,
    )
    model = model_waiter(config)
    browser_pid = None if no_browser else browser_opener(config)
    return {
        "schema_version": "laplace.desktop-front-launch-receipt/1",
        "status": "OPENED" if browser_pid is not None else "READY",
        "service_disposition": disposition,
        "coordinate": coordinate.as_dict(),
        "service_identity": identity.as_dict(),
        "model_schema": model["schema_version"],
        "shown_handle": model.get("shown_state", {}).get("shown_handle"),
        "browser_pid": browser_pid,
        "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
    }


def _state_log(config: Mapping[str, Any] | None) -> Path:
    configured = str((config or {}).get("state_log", "")).strip()
    if configured:
        return Path(configured).expanduser()
    state_home = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return state_home / "eigen" / "front-launch.log"


def _record_failure(message: str, config: Mapping[str, Any] | None = None) -> Path:
    path = _state_log(config)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        with path.open("a", encoding="utf-8") as stream:
            stream.write(f"{stamp}\n{message}\n\n")
    except OSError:
        pass
    return path


def _notify_failure(message: str, log_path: Path) -> None:
    body = f"{message}\n\nFull receipt: {log_path}"
    zenity = shutil.which("zenity")
    notify = shutil.which("notify-send")
    try:
        if zenity:
            subprocess.run(
                [zenity, "--error", "--title=Eigen could not open", f"--text={body}"],
                timeout=120,
                check=False,
            )
        elif notify:
            subprocess.run(
                [notify, "--urgency=critical", "--expire-time=0", "Eigen could not open", body],
                timeout=10,
                check=False,
            )
    except (OSError, subprocess.SubprocessError):
        pass


def _serve(args: argparse.Namespace) -> int:
    config = {
        "schema_version": CONFIG_SCHEMA,
        "checkout": args.checkout,
        "expected_commit": args.expected_commit,
        "expected_tree": args.expected_tree,
        "expected_contract_sha256": args.expected_contract_sha256,
        "expected_model_schema": args.expected_model_schema,
        "allow_descendant": bool(args.allow_descendant),
    }
    coordinate = verify_checkout(config)
    env = dict(os.environ)
    env.update(
        {
            "PYTHONPATH": os.pathsep.join(
                (
                    str(coordinate.checkout / "src"),
                )
            ),
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "LAPLACE_DESKTOP_SERVICE_SCHEMA": SERVICE_SCHEMA,
            "LAPLACE_DESKTOP_CHECKOUT": str(coordinate.checkout),
            "LAPLACE_DESKTOP_SOURCE_COMMIT": coordinate.commit,
            "LAPLACE_DESKTOP_SOURCE_TREE": coordinate.tree,
            "LAPLACE_DESKTOP_MODEL_SCHEMA": args.expected_model_schema,
        }
    )
    os.chdir(coordinate.checkout)
    argv = [
        "/usr/bin/python3",
        "-m",
        "laplace.web.scanner",
        "--host",
        args.host,
        "--port",
        str(args.port),
    ]
    os.execve(argv[0], argv, env)
    return 127  # pragma: no cover - execve either replaces the process or raises


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eigen-front",
        description="Open only the verified, published next-generation Eigen front carrier.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    opening = sub.add_parser("open", help="verify checkout + service + model, then open /front")
    opening.add_argument("--config", type=Path, default=None)
    opening.add_argument("--no-browser", action="store_true")
    probing = sub.add_parser("probe", help="run the same proof without opening a browser")
    probing.add_argument("--config", type=Path, default=None)
    serving = sub.add_parser("serve", help="systemd-only scanner process entry")
    serving.add_argument("--checkout", required=True)
    serving.add_argument("--expected-commit", required=True)
    serving.add_argument("--expected-tree", required=True)
    serving.add_argument("--expected-contract-sha256", required=True)
    serving.add_argument("--expected-model-schema", default=MODEL_SCHEMA)
    serving.add_argument("--allow-descendant", action="store_true")
    serving.add_argument("--host", default=DEFAULT_HOST)
    serving.add_argument("--port", type=int, default=DEFAULT_PORT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "serve":
        try:
            return _serve(args)
        except LaunchRefusal as refusal:
            print(refusal.render(), file=sys.stderr, flush=True)
            return 2

    config: dict[str, Any] | None = None
    try:
        config = load_config(args.config)
        receipt = launch_front(
            config,
            no_browser=(getattr(args, "no_browser", False) or args.command == "probe"),
        )
        print(json.dumps(receipt, indent=2, sort_keys=True), flush=True)
        return 0
    except LaunchRefusal as refusal:
        rendered = refusal.render()
        log_path = _record_failure(rendered, config)
        print(f"{rendered}\n\nReceipt: {log_path}", file=sys.stderr, flush=True)
        _notify_failure(rendered, log_path)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
