"""Shared fixtures for Laplace Engine tests.

verify.verify / run_backing now log telemetry, so every test must run against an
isolated state dir - never the user's real ~/.mcp-gerard/laplace.
"""

import json
import os
from pathlib import Path

import pytest

# Process-lifetime test identity.  Unlike PYTEST_CURRENT_TEST this does not disappear after
# fixture teardown while a daemon thread is still alive.  The Atlas write door uses it to make
# the live provider store unreachable from this process even during that teardown tail.
os.environ["LAPLACE_TEST_PROCESS"] = "1"


def pytest_sessionstart(session):
    # The Atlas suite's legacy bare helper import must bind before engine test
    # modules prepend tests/ to sys.path. Collection itself uses importlib names.
    import importlib

    importlib.import_module("test_blueprint")


@pytest.fixture(autouse=True)
def _custody_live_under_test(monkeypatch):
    """THE CUSTODY SWITCH (his ruling 2026-09-14, laplace.representation.custody_mode): the repository's live
    row may say OFF, but every existing test asserts the custody-ON law as written - the close's
    custody gate, the provider wake's key order, the dispatch admission's authority proof. So the
    suite forces the live paths by default and tests the OFF path explicitly, on its own
    fixtures, in tests/test_custody_mode.py (which clears this variable itself)."""
    monkeypatch.setenv("LAPLACE_CUSTODY_LIVE", "1")


@pytest.fixture(autouse=True)
def _isolate_laplace_state(tmp_path, monkeypatch):
    monkeypatch.setenv("LAPLACE_STATE", str(tmp_path / "_lap_state"))
    # THE FALLBACK CENSUS STORE IS STATE TOO (census 2026-08-21). device_policy appends a typed
    # row for every CPU landing in a ruled-GPU organ, and until now the suite wrote those rows
    # into the REPO's .fallback_events.jsonl: test_metric_distill (4/run) and
    # test_meaning_upfold_incremental (1/run) never set LAPLACE_ROOT, so 72 of the store's first
    # 95 rows described monkeypatched fixtures, not this machine. Tests that assert ON the
    # recorder set LAPLACE_ROOT/LAPLACE_FALLBACK_LOG themselves and still win - monkeypatch.setenv
    # inside a test overrides this one.
    monkeypatch.setenv("LAPLACE_FALLBACK_LOG", str(tmp_path / "_fallback_events.jsonl"))
    # AND THE REQUIRE FLAG IS NOT THE SUITE'S BUSINESS (2026-08-21, the Enforce lane).
    # LAPLACE_REQUIRE_GPU=1 is now this box's DEFAULT for engine runs - the session-start hook
    # declares it into CLAUDE_ENV_FILE, so every Bash-tool shell, pytest included, inherits it.
    # A test's device landing is a FIXTURE, never evidence about this machine (the same reasoning
    # that put `synthetic` in the row's provenance): tests routinely monkeypatch cupy or the CUDA
    # provider away to exercise the fallback path, and under an inherited require flag each of
    # those becomes a DeviceRequired refusal - the suite would fail for describing a CPU landing
    # rather than for suffering one. So the flag is stripped for every test and the tests that
    # actually assert on refusal set it themselves (test_meaning_upfold_incremental.py's
    # monkeypatch.setenv still wins over this delenv, exactly as with the two stores above).
    # This is what makes the local default safe BY CONSTRUCTION rather than safe by today's luck.
    monkeypatch.delenv("LAPLACE_REQUIRE_GPU", raising=False)
    # THE ISOLATION DOOR EXTENDS TO PROCESS-SPAWNED INSTALLERS (FIND-SE-008, 2026-08-23).
    # A test ran `uv run` with cwd at repo root and one dropped --no-project flag; uv
    # discovered pyproject.toml and built a real 208M .venv THROUGH the isolation door
    # into the real root - gitignored, so every clean-tree instrument certified over it.
    # Target-dir isolation, not just env vars: any project-mode uv a test spawns builds
    # its environment in the test's own tmp, never the repo. Tests that assert on venv
    # placement set this themselves and still win (monkeypatch precedence, as above).
    monkeypatch.setenv("UV_PROJECT_ENVIRONMENT", str(tmp_path / "_uv_env"))
    yield


@pytest.fixture
def register_project(monkeypatch):
    """THE REGISTRY-LEVEL FIXTURE DOOR: register a throwaway conceptric under a tmp
    root by writing the same ``registry_projects.json`` row the New Project door
    writes. Returns the row's repo-relative tex_root.

    Until 2026-08-04 a fixture corpus was registered by monkeypatching a hardcoded
    module-level corpus dict, which registered it for EVERY root at once and so never
    needed a root binding. A data row registers a project for the root that CARRIES the
    file, which is what the code under test now reads — so ``bind_root`` (default) also
    points ``registry._repo_root`` at that root, since ``registry.resolve`` takes no
    root argument and would otherwise answer from the real repo.

    ``main_tex`` writes a stub at ``<tex_root>/main.tex`` when the test needs the
    project to be OPENABLE (``resolve_corpus``'s gate); registration alone does not
    create one, exactly as the real door's scaffold must.
    """
    def _register(root: Path | str, name: str, tex_root: str | None = None,
                  main_tex: str | None = None, bind_root: bool = True) -> str:
        root = Path(root)
        f = root / "registry_projects.json"
        try:
            rows = json.loads(f.read_text(encoding="utf-8"))["projects"]
        except (OSError, ValueError, KeyError, TypeError):
            rows = []
        rel = tex_root if tex_root is not None else f"synthetics papers/{name}/manuscript/tex"
        rows.append({"name": name, "kind": "conceptric", "tex_root": rel,
                     "created_by": "test-fixture"})
        root.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"projects": rows}), encoding="utf-8")
        if main_tex is not None:
            d = root / rel
            d.mkdir(parents=True, exist_ok=True)
            (d / "main.tex").write_text(main_tex, encoding="utf-8")
        if bind_root:
            from laplace.pipeline import registry
            monkeypatch.setattr(registry, "_repo_root", lambda: root)
        return rel
    return _register


def pytest_collection_modifyitems(config, items):
    """xdist grouping (2026-08-21): the isolation audit's rows are the single source.
    Every test in a needs-serialization file is pinned to one worker via xdist_group
    (its shared store's name), so `-n auto --dist loadgroup` keeps loadfile's guarantee
    exactly where it is needed and spreads the ~300 safe files test-by-test. No per-file
    marker edits — the audit rows (tests/xdist_isolation_audit.json) stay the one truth,
    and tests/test_xdist_isolation.py fails when a new repo-root-writing test appears
    unmarked there."""
    audit = Path(__file__).parent / "xdist_isolation_audit.json"
    try:
        rows = json.loads(audit.read_text(encoding="utf-8")).get("rows") or []
    except Exception:
        return
    groups = {r["file"]: r["xdist_group"] for r in rows
              if isinstance(r, dict) and r.get("file") and r.get("xdist_group")}
    if not groups:
        return
    root = Path(__file__).resolve().parent.parent
    for item in items:
        try:
            rel = str(Path(str(item.fspath)).resolve().relative_to(root))
        except Exception:
            continue
        g = groups.get(rel)
        if g:
            item.add_marker(pytest.mark.xdist_group(name=g))
