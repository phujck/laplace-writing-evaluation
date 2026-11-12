"""Asset discovery reads the selected workspace, including through real HTTP."""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import time
from urllib.request import urlopen

from laplace.native import tools as writing_tools
from laplace.pipeline import asset_model, registry


REPO = Path(__file__).resolve().parents[1]
PROJECT = "asset-root-fixture"


def _workspace(root: Path, tag: str, *, figures: bool = True) -> Path:
    (root / "profiles").mkdir(parents=True)
    manuscript = root / "projects" / PROJECT / "manuscript"
    manuscript.mkdir(parents=True)
    (root / "registry_projects.json").write_text(json.dumps({"projects": [{
        "name": PROJECT, "kind": "conceptric",
        "project_dir": f"projects/{PROJECT}",
        "tex_root": f"projects/{PROJECT}/manuscript",
        "manuscript_dir": f"projects/{PROJECT}/manuscript",
        "document": {"root": "main.tex",
                     "manuscript_dir": f"projects/{PROJECT}/manuscript"},
    }]}), encoding="utf-8")
    (manuscript / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\nAsset root fixture.\n\\end{document}\n",
        encoding="utf-8")
    artefact = f"figures/generated/{tag}.pdf"
    (manuscript / "figure_manifest.json").write_text(json.dumps({"placed": [{
        "asset_id": f"figure:{tag}", "label": f"fig:{tag}",
        "promise": f"{tag} belongs to this workspace", "generator": "manuscript_spec.json",
        "artefact": artefact, "matched": True,
    }]}), encoding="utf-8")
    if figures:
        target = manuscript / artefact
        target.parent.mkdir(parents=True)
        target.write_bytes(("%PDF-" + tag).encode())
    return manuscript


def _producer(value: dict) -> str | None:
    return value["assets"][0]["asset_producer"]


def test_selected_workspace_wins_over_same_named_code_checkout(tmp_path, monkeypatch):
    workspace = tmp_path / "selected-workspace"
    poison = tmp_path / "code-checkout"
    _workspace(workspace, "selected")
    _workspace(poison, "poison")
    monkeypatch.setenv("LAPLACE_REPO_ROOT", str(workspace))
    # Reproduce an installed/source checkout that contains a conflicting project.
    # The pre-fix __file__.parents[3] implementation selects `poison` here.
    monkeypatch.setattr(
        asset_model, "__file__",
        str(poison / "src" / "laplace" / "pipeline" / "asset_model.py"))

    assert asset_model._repo_root() == workspace.resolve()
    assets = asset_model.enumerate_assets(PROJECT)
    assert [asset.id for asset in assets] == ["figure:selected"]
    assert all("poison" not in path for asset in assets
               for path in [asset.producer.path or "", *asset.rendered])

    public = writing_tools.execute(workspace, PROJECT, "work", "research", {})
    expected = f"projects/{PROJECT}/manuscript/figure_manifest.json"
    assert _producer(public) == expected
    assert public["figures"][0]["asset_producer"] == expected


def test_no_environment_keeps_registry_fallback(monkeypatch):
    monkeypatch.delenv("LAPLACE_REPO_ROOT", raising=False)
    assert asset_model._repo_root() == registry._repo_root()


def test_real_http_research_uses_selected_workspace_assets(tmp_path):
    workspace = tmp_path / "http-workspace"
    _workspace(workspace, "http-selected")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    env = dict(os.environ)
    env.pop("LAPLACE_REPO_ROOT", None)
    env.pop("LAPLACE_STATE", None)
    process = subprocess.Popen([
        str(REPO / "scripts" / "laplace-python"), "-m", "laplace.web.writing_server",
        "--root", str(workspace), "--state", str(tmp_path / "http-state"),
        "--host", "127.0.0.1", "--port", str(port),
    ], cwd=REPO, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        deadline = time.monotonic() + 15
        health = None
        while time.monotonic() < deadline:
            try:
                with urlopen(f"http://127.0.0.1:{port}/authoring/health", timeout=1) as response:
                    health = json.load(response)
                break
            except Exception:
                if process.poll() is not None:
                    break
                time.sleep(.05)
        assert health is not None, process.stdout.read() if process.poll() is not None else "no health"
        with urlopen(
                f"http://127.0.0.1:{port}/research/state?project={PROJECT}", timeout=3) as response:
            research = json.load(response)
        expected = f"projects/{PROJECT}/manuscript/figure_manifest.json"
        assert _producer(research) == expected
        assert research["figures"][0]["asset_producer"] == expected
    finally:
        process.terminate()
        process.wait(timeout=10)
