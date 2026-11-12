from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "runtime_surface.py"
SNAPSHOT = REPO / "runtime_surface.json"

SPEC = importlib.util.spec_from_file_location("runtime_surface", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
runtime_surface = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime_surface)


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _paths(rows: list[dict[str, object]]) -> set[str]:
    return {str(row["path"]) for row in rows}


def test_committed_runtime_surface_is_current_and_self_authenticating() -> None:
    expected = runtime_surface.render_snapshot(runtime_surface.build_snapshot(REPO))
    assert SNAPSHOT.read_bytes() == expected

    document = json.loads(expected)
    claimed = document.pop("snapshot_digest")
    actual = f"sha256:{hashlib.sha256(_canonical_bytes(document)).hexdigest()}"
    assert claimed == actual
    assert str(REPO) not in expected.decode("utf-8")


def test_key_lifecycle_and_embedding_surfaces_are_represented() -> None:
    document = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    evidence = document["inferred_evidence"]

    projects = {row["name"]: row for row in evidence["python_projects"]}
    laplace_entrypoints = {
        row["name"]: row["target"] for row in projects["laplace-engine"]["entrypoints"]
    }
    assert laplace_entrypoints["laplace-wake"] == "laplace.engine.wake:main"

    main_paths = _paths(evidence["active_python_main_surfaces"])
    assert {
        "scripts/reembed.py",
        "scripts/runtime_surface.py",
        "scripts/seat_fabric.py",
        "scripts/wake.py",
    } <= main_paths

    hook_events = {(row["source"], row["event"]) for row in evidence["hook_registrations"]}
    assert (".codex/hooks.json", "SessionStart") in hook_events
    assert (".codex/hooks.json", "UserPromptSubmit") in hook_events

    service_commands = {row["command"] for row in evidence["service_exec_surfaces"]}
    assert any("laplace.representation.atlas_watcher" in command for command in service_commands)
    assert any("laplace.web.scanner" in command for command in service_commands)

    localstate_names = {row["name"] for row in evidence["localstate_entries"]}
    assert {"embed-cuda", "embed-model-vendor", "gpu-stack", "self-embeddings"} <= (
        localstate_names
    )

    artifact_paths = _paths(evidence["tracked_embedding_model_artifacts"])
    assert {
        ".metric_M.npz",
        ".self_embeddings.json",
        "models/fastembed/fast-bge-small-en-v1.5.tar.gz",
    } <= artifact_paths

    embedding_paths = _paths(evidence["embedding_provider_files"])
    assert "src/laplace/representation/embed_router.py" in embedding_paths
    assert "src/laplace/engine/startup_mail_gate.py" in embedding_paths

    subprocess_paths = _paths(evidence["subprocess_launch_files"])
    assert ".codex/hooks/session-start.mjs" in subprocess_paths
    assert "src/laplace/representation/codex_seat_watcher.py" in subprocess_paths
