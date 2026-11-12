from __future__ import annotations

import importlib.util
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

from laplace.representation import atlas_bridge

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "seat_fabric_publication_under_test", ROOT / "scripts" / "seat_fabric.py"
)
seat_fabric = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(seat_fabric)


def test_public_publish_door_is_only_the_accepted_thin_finalizer() -> None:
    source = inspect.getsource(atlas_bridge.publish_regions)
    ref_source = inspect.getsource(atlas_bridge._git_update_ref_once)

    assert "P0-PUBLICATION-DISABLED-PREPARE-FINALIZE-REQUIRED" not in source
    assert "_git_stage_regions" not in source
    assert "_git_commit_leased_candidate" not in source
    assert "finalize_region_publication" in source
    assert "push" not in source
    assert "push" not in ref_source


def test_cli_routes_exact_prepared_publication_faces(monkeypatch, capsys) -> None:
    calls: list[tuple[str, dict]] = []

    def face(name):
        def invoke(**kwargs):
            calls.append((name, kwargs))
            return {"schema_version": "test/1", "state": "AUTHORIZED"}

        return invoke

    monkeypatch.setattr(
        seat_fabric,
        "_bridge",
        lambda: SimpleNamespace(
            prepare_region_publication=face("prepare"),
            sign_region_publication=face("sign"),
            authorize_region_publication=face("authorize"),
            finalize_region_publication=face("finalize"),
            recover_region_publication=face("recover"),
            region_publication=face("status"),
        ),
    )
    common = ["--lease", "region-lease:x", "--publication", "region-publication:y"]
    recovery = [*common, "--recovery-root", "sha256:" + "a" * 64]
    sign = [
        *recovery,
        "--candidate-commit",
        "1" * 40,
        "--candidate-tree",
        "2" * 40,
        "--patch-handle",
        "sha256:" + "3" * 64,
        "--custody-handle",
        "sha256:" + "4" * 64,
        "--affected-frontier-root",
        "sha256:" + "5" * 64,
        "--rehearsal-evidence-root",
        "sha256:" + "6" * 64,
        "--forward-closure-root",
        "sha256:" + "7" * 64,
        "--seat",
        "sensorium-seat",
        "--holder-ref",
        "codex:thread-interface",
        "--function",
        "sensorium",
        "--role-profile-handle",
        "sha256:" + "b" * 64,
        "--reconstruction-handle",
        "sha256:" + "c" * 64,
        "--predicate-result",
        "PASS",
        "--expires",
        "2036-08-27T12:00:00Z",
    ]

    assert seat_fabric.main(["sign-publication", *sign]) == 0
    assert seat_fabric.main(["authorize-publication", *recovery]) == 0
    assert seat_fabric.main(["finalize-publication", *recovery]) == 0
    assert seat_fabric.main(["recover-publication", *recovery]) == 0
    assert seat_fabric.main(["publication-status", *common]) == 0
    assert [name for name, _kwargs in calls] == [
        "sign",
        "authorize",
        "finalize",
        "recover",
        "status",
    ]
    assert json.loads(capsys.readouterr().out.split("}\n")[0] + "}")["state"] == "AUTHORIZED"
