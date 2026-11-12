from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

from laplace.desktop import desktop_front

INSTALLER_PATH = Path(__file__).resolve().parents[1] / "scripts" / "install_front_launcher.py"


def _load_installer():
    spec = importlib.util.spec_from_file_location("install_front_launcher", INSTALLER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _checkout(tmp_path: Path) -> Path:
    root = tmp_path / "published"
    for package in ("web", "engine", "desktop"):
        (root / "src" / "laplace" / package).mkdir(parents=True)
    (root / "contract" / "surfaces").mkdir(parents=True)
    (root / "src" / "laplace" / "web" / "scanner.py").write_text("# scanner\n", encoding="utf-8")
    (root / "src" / "laplace" / "engine" / "front_carrier.py").write_text(
        f'MODEL_SCHEMA = "{desktop_front.MODEL_SCHEMA}"\n', encoding="utf-8"
    )
    (root / "src" / "laplace" / "desktop" / "desktop_front.py").write_text("# launcher\n", encoding="utf-8")
    (root / "contract" / "surfaces" / "front.yaml").write_text(
        f"surface: front\nmodel: {desktop_front.MODEL_SCHEMA}\n", encoding="utf-8"
    )
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "published"], check=True)
    return root


def test_rendered_bundle_pins_checkout_service_and_front_contract(tmp_path: Path) -> None:
    installer = _load_installer()
    root = _checkout(tmp_path)
    plan = installer.render_bundle(
        checkout=root,
        config_path=tmp_path / "config" / "front-launch.json",
        service_path=tmp_path / "systemd" / "eigen-front.service",
        desktop_path=tmp_path / "applications" / "eigen-front.desktop",
        state_log=tmp_path / "state" / "front-launch.log",
        service="eigen-front.service",
        host="127.0.0.1",
        port=8770,
        allow_descendant=False,
        browser_command=["/bin/true", "{url}"],
    )
    config = json.loads(plan["files"][0]["content"])
    unit = plan["files"][1]["content"]
    desktop = plan["files"][2]["content"]
    assert config["expected_commit"] == subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    assert config["allow_descendant"] is False
    assert desktop_front.MODEL_SCHEMA in config["expected_model_schema"]
    assert f"WorkingDirectory={root}" in unit
    assert 'WorkingDirectory="' not in unit
    assert f'"{root / "src/laplace/desktop/desktop_front.py"}" "serve"' in unit
    assert " open " in f" {plan['launch_command']} "
    assert " probe " in f" {plan['probe_command']} "
    assert " open " not in f" {plan['probe_command']} "
    assert "Terminal=false" in desktop


def test_cli_defaults_to_dry_run_and_writes_nothing(tmp_path: Path) -> None:
    root = _checkout(tmp_path)
    config_dir = tmp_path / "config"
    apps = tmp_path / "apps"
    systemd = tmp_path / "systemd"
    result = subprocess.run(
        [
            "/usr/bin/python3",
            str(INSTALLER_PATH),
            "--checkout",
            str(root),
            "--browser",
            "/bin/true",
            "--config-dir",
            str(config_dir),
            "--applications-dir",
            str(apps),
            "--systemd-user-dir",
            str(systemd),
            "--state-dir",
            str(tmp_path / "state"),
        ],
        text=True,
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan["dry_run"] is True
    assert plan["installed"] is False
    assert not config_dir.exists()
    assert not apps.exists()
    assert not systemd.exists()


def test_install_writes_exact_three_files_then_reloads_systemd(tmp_path: Path, monkeypatch) -> None:
    installer = _load_installer()
    root = _checkout(tmp_path)
    paths = {
        "config_path": tmp_path / "config" / "front-launch.json",
        "service_path": tmp_path / "systemd" / "eigen-front.service",
        "desktop_path": tmp_path / "apps" / "eigen-front.desktop",
    }
    plan = installer.render_bundle(
        checkout=root,
        **paths,
        state_log=tmp_path / "state" / "front-launch.log",
        service="eigen-front.service",
        host="127.0.0.1",
        port=8770,
        allow_descendant=True,
        browser_command=["/bin/true", "{url}"],
    )
    calls: list[list[str]] = []

    def fake_run(argv, **_kwargs):
        calls.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(installer.subprocess, "run", fake_run)
    installer.install(plan)
    for item in plan["files"]:
        path = Path(item["path"])
        assert path.read_text(encoding="utf-8") == item["content"]
        assert desktop_front._sha256(path) == item["sha256"]
    assert calls == [["systemctl", "--user", "daemon-reload"]]


def test_installer_refuses_dirty_configured_checkout(tmp_path: Path) -> None:
    root = _checkout(tmp_path)
    (root / "untracked.py").write_text("# dirt\n", encoding="utf-8")
    result = subprocess.run(
        [
            "/usr/bin/python3",
            str(INSTALLER_PATH),
            "--checkout",
            str(root),
            "--browser",
            "/bin/true",
            "--dry-run",
        ],
        text=True,
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == 2
    assert "CHECKOUT-DIRTY" in result.stderr
