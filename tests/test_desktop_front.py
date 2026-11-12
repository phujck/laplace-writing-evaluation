from __future__ import annotations

import json
import os
import socket
import subprocess
from pathlib import Path

import pytest

from laplace.desktop import desktop_front


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def _make_checkout(tmp_path: Path, *, fake_scanner: bool = False) -> Path:
    root = tmp_path / "laplace"
    for package in ("web", "engine", "desktop"):
        (root / "src" / "laplace" / package).mkdir(parents=True)
    (root / "contract" / "surfaces").mkdir(parents=True)
    (root / "src" / "laplace" / "__init__.py").write_text("", encoding="utf-8")
    scanner = "# published scanner fixture\n"
    if fake_scanner:
        scanner = '''
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/front/model"):
            data = json.dumps({
                "schema_version": "laplace.aisthesis-front-model/1",
                "shown_state": {"shown_handle": "shown:test"},
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if self.path == "/front":
            data = b"Eigen"
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self.send_error(404)

    def log_message(self, *args):
        pass

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()

if __name__ == "__main__":
    main()
'''.lstrip()
    (root / "src" / "laplace" / "web" / "scanner.py").write_text(scanner, encoding="utf-8")
    (root / "src" / "laplace" / "engine" / "front_carrier.py").write_text(
        'MODEL_SCHEMA = "laplace.aisthesis-front-model/1"\n', encoding="utf-8"
    )
    (root / "contract" / "surfaces" / "front.yaml").write_text(
        "surface: front\nmodel: laplace.aisthesis-front-model/1\n", encoding="utf-8"
    )
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)
    return root


def _config(root: Path, *, allow_descendant: bool = False) -> dict:
    contract = root / "contract" / "surfaces" / "front.yaml"
    return {
        "schema_version": desktop_front.CONFIG_SCHEMA,
        "checkout": str(root),
        "expected_commit": _git(root, "rev-parse", "HEAD"),
        "expected_tree": _git(root, "rev-parse", "HEAD^{tree}"),
        "expected_contract_sha256": desktop_front._sha256(contract),
        "expected_model_schema": desktop_front.MODEL_SCHEMA,
        "allow_descendant": allow_descendant,
        "service": desktop_front.DEFAULT_SERVICE,
        "host": "127.0.0.1",
        "port": 8770,
        "browser_command": ["/bin/true", "{url}"],
    }


def _unit(root: Path, *, active: bool, pid: int = 0) -> dict[str, str]:
    launcher = root / "src" / "laplace" / "desktop" / "desktop_front.py"
    commit = _git(root, "rev-parse", "HEAD")
    tree = _git(root, "rev-parse", "HEAD^{tree}")
    contract = desktop_front._sha256(root / "contract" / "surfaces" / "front.yaml")
    return {
        "LoadState": "loaded",
        "ActiveState": "active" if active else "inactive",
        "SubState": "running" if active else "dead",
        "MainPID": str(pid),
        "WorkingDirectory": str(root),
        "ExecStart": (
            f"/usr/bin/python3 {launcher} serve --checkout {root} "
            f"--expected-commit {commit} --expected-tree {tree} "
            f"--expected-contract-sha256 {contract} "
            f"--expected-model-schema {desktop_front.MODEL_SCHEMA} "
            "--host 127.0.0.1 --port 8770"
        ),
        "FragmentPath": "/tmp/eigen-front.service",
    }


def _identity(root: Path, config: dict, pid: int = 41) -> desktop_front.ServiceIdentity:
    return desktop_front.ServiceIdentity(
        pid=pid,
        checkout=root,
        commit=_git(root, "rev-parse", "HEAD"),
        tree=_git(root, "rev-parse", "HEAD^{tree}"),
        model_schema=config["expected_model_schema"],
    )


def test_exact_clean_checkout_is_admitted(tmp_path: Path) -> None:
    root = _make_checkout(tmp_path)
    coordinate = desktop_front.verify_checkout(_config(root))
    assert coordinate.relation == "EXACT"
    assert coordinate.checkout == root.resolve()


def test_dirty_checkout_refuses_before_service_contact(tmp_path: Path) -> None:
    root = _make_checkout(tmp_path)
    config = _config(root)
    (root / "src" / "laplace" / "web" / "scanner.py").write_text("# moved\n", encoding="utf-8")
    with pytest.raises(desktop_front.LaunchRefusal, match="CHECKOUT-DIRTY"):
        desktop_front.verify_checkout(config)


def test_descendant_is_only_admitted_when_explicit(tmp_path: Path) -> None:
    root = _make_checkout(tmp_path)
    strict = _config(root)
    permissive = {**strict, "allow_descendant": True}
    (root / "descendant.txt").write_text("next\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "descendant"], check=True)
    with pytest.raises(desktop_front.LaunchRefusal, match="CHECKOUT-MOVED"):
        desktop_front.verify_checkout(strict)
    assert desktop_front.verify_checkout(permissive).relation == "DESCENDANT"


def test_wrong_service_checkout_refuses_without_action(tmp_path: Path) -> None:
    root = _make_checkout(tmp_path)
    config = _config(root)
    coordinate = desktop_front.verify_checkout(config)
    wrong = {**_unit(root, active=True, pid=12), "WorkingDirectory": str(tmp_path / "other")}
    actions: list[tuple[str, str]] = []
    with pytest.raises(desktop_front.LaunchRefusal, match="SERVICE-WRONG-CHECKOUT"):
        desktop_front.ensure_service(
            config,
            coordinate,
            show=lambda _service: wrong,
            action=lambda service, verb: actions.append((service, verb)),
            identity_reader=lambda _pid: _identity(root, config),
        )
    assert actions == []


def test_service_unit_must_match_pinned_config_not_merely_the_checkout(tmp_path: Path) -> None:
    root = _make_checkout(tmp_path)
    config = _config(root)
    coordinate = desktop_front.verify_checkout(config)
    wrong = _unit(root, active=False)
    wrong["ExecStart"] = wrong["ExecStart"].replace(config["expected_commit"], "f" * 40)
    actions: list[tuple[str, str]] = []
    with pytest.raises(desktop_front.LaunchRefusal, match="SERVICE-CONFIG-DISAGREEMENT"):
        desktop_front.ensure_service(
            config,
            coordinate,
            show=lambda _service: wrong,
            action=lambda service, verb: actions.append((service, verb)),
            identity_reader=lambda _pid: _identity(root, config),
        )
    assert actions == []


def test_cold_service_starts_then_proves_live_identity(tmp_path: Path) -> None:
    root = _make_checkout(tmp_path)
    config = _config(root)
    coordinate = desktop_front.verify_checkout(config)
    active = False
    actions: list[tuple[str, str]] = []

    def show(_service: str) -> dict[str, str]:
        return _unit(root, active=active, pid=41 if active else 0)

    def action(service: str, verb: str) -> None:
        nonlocal active
        actions.append((service, verb))
        active = True

    disposition, identity = desktop_front.ensure_service(
        config,
        coordinate,
        show=show,
        action=action,
        identity_reader=lambda pid: _identity(root, config, pid),
        timeout=1.0,
    )
    assert disposition == "STARTED-COLD"
    assert identity.commit == coordinate.commit
    assert actions == [(desktop_front.DEFAULT_SERVICE, "start")]


def test_stale_same_checkout_service_is_restarted(tmp_path: Path) -> None:
    root = _make_checkout(tmp_path)
    config = _config(root)
    coordinate = desktop_front.verify_checkout(config)
    restarted = False

    def identity(_pid: int) -> desktop_front.ServiceIdentity:
        return desktop_front.ServiceIdentity(
            pid=41,
            checkout=root.resolve(),
            commit=coordinate.commit if restarted else "0" * 40,
            tree=coordinate.tree,
            model_schema=desktop_front.MODEL_SCHEMA,
        )

    def action(_service: str, verb: str) -> None:
        nonlocal restarted
        assert verb == "restart"
        restarted = True

    disposition, _ = desktop_front.ensure_service(
        config,
        coordinate,
        show=lambda _service: _unit(root, active=True, pid=41),
        action=action,
        identity_reader=identity,
        timeout=1.0,
    )
    assert disposition == "RESTARTED-STALE"
    assert restarted is True


class _Response:
    def __init__(self, payload: dict, status: int = 200) -> None:
        self.status = status
        self._data = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return self._data


def test_live_model_requires_exact_carrier_schema_and_shown_state() -> None:
    config = {"expected_model_schema": desktop_front.MODEL_SCHEMA, "port": 8770}
    payload = desktop_front.wait_for_front_model(
        config,
        timeout=0.1,
        opener=lambda *_args, **_kwargs: _Response(
            {"schema_version": desktop_front.MODEL_SCHEMA, "shown_state": {"shown_handle": "shown:1"}}
        ),
    )
    assert payload["shown_state"]["shown_handle"] == "shown:1"


def test_wrong_live_model_is_a_terminal_refusal() -> None:
    config = {"expected_model_schema": desktop_front.MODEL_SCHEMA, "port": 8770}
    with pytest.raises(desktop_front.LaunchRefusal, match="FRONT-MODEL-WRONG-CONTRACT"):
        desktop_front.wait_for_front_model(
            config,
            timeout=0.1,
            opener=lambda *_args, **_kwargs: _Response(
                {"schema_version": "historical.dashboard/1", "shown_state": {}}
            ),
        )


def test_launch_receipt_binds_checkout_service_and_model(tmp_path: Path) -> None:
    root = _make_checkout(tmp_path)
    config = _config(root)
    identity = _identity(root, config)
    receipt = desktop_front.launch_front(
        config,
        no_browser=True,
        show=lambda _service: _unit(root, active=True, pid=identity.pid),
        action=lambda *_args: pytest.fail("fresh service must be reused"),
        identity_reader=lambda _pid: identity,
        model_waiter=lambda _config: {
            "schema_version": desktop_front.MODEL_SCHEMA,
            "shown_state": {"shown_handle": "shown:test"},
        },
    )
    assert receipt["status"] == "READY"
    assert receipt["service_disposition"] == "REUSED"
    assert receipt["shown_handle"] == "shown:test"


def test_probe_entry_never_requires_open_only_no_browser_argument(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    observed: list[bool] = []
    monkeypatch.setattr(desktop_front, "load_config", lambda _path: {"config": "test"})
    monkeypatch.setattr(
        desktop_front,
        "launch_front",
        lambda _config, *, no_browser: observed.append(no_browser) or {"status": "READY"},
    )

    assert desktop_front.main(["probe"]) == 0
    assert observed == [True]
    assert json.loads(capsys.readouterr().out) == {"status": "READY"}


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def test_serve_entry_execs_pinned_checkout_and_exposes_identity(tmp_path: Path) -> None:
    root = _make_checkout(tmp_path, fake_scanner=True)
    config = _config(root)
    port = _free_port()
    launcher = Path(desktop_front.__file__).resolve()
    command = [
        "/usr/bin/python3",
        str(launcher),
        "serve",
        "--checkout",
        str(root),
        "--expected-commit",
        config["expected_commit"],
        "--expected-tree",
        config["expected_tree"],
        "--expected-contract-sha256",
        config["expected_contract_sha256"],
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        live_config = {**config, "port": port, "startup_timeout_seconds": 3.0}
        payload = desktop_front.wait_for_front_model(live_config, timeout=3.0)
        identity = desktop_front._read_process_identity(proc.pid)
        assert payload["shown_state"]["shown_handle"] == "shown:test"
        assert identity.checkout == root.resolve()
        assert identity.commit == config["expected_commit"]
        assert identity.tree == config["expected_tree"]
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)


def test_serve_entry_refuses_moved_exact_checkout_before_bind(tmp_path: Path) -> None:
    root = _make_checkout(tmp_path, fake_scanner=True)
    config = _config(root)
    (root / "next.txt").write_text("next\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "next"], check=True)
    launcher = Path(desktop_front.__file__).resolve()
    result = subprocess.run(
        [
            "/usr/bin/python3",
            str(launcher),
            "serve",
            "--checkout",
            str(root),
            "--expected-commit",
            config["expected_commit"],
            "--expected-tree",
            config["expected_tree"],
            "--expected-contract-sha256",
            config["expected_contract_sha256"],
            "--port",
            str(_free_port()),
        ],
        text=True,
        capture_output=True,
        timeout=10,
        env={**os.environ, "PYTHONPATH": ""},
    )
    assert result.returncode == 2
    assert "CHECKOUT-MOVED" in result.stderr
