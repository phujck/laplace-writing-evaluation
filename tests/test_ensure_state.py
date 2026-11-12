"""Tests for scripts/ensure_state.py -- the manifest-driven generalisation of
ensure_voice_store.sh / ensure_tex.sh: read localstate.json, run each entry's
`check`, rebuild from committed raw on a miss, and land the fail-loud
VERDICT=PASS|FAIL missing=[...] sentinel as the last line.

Uses a TMP FIXTURE manifest (never the real localstate.json / real repo state)
so these are fast, hermetic, and prove the DECISION logic: check-pass skips
rebuild, check-fail triggers rebuild, --dry-run runs nothing, and the sentinel
+ return code land correctly in both the all-pass and still-missing cases.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "ensure_state.py"


def _load_ensure_state_module():
    spec = importlib.util.spec_from_file_location("ensure_state_mod", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_manifest(root: Path, entries: list[dict]) -> Path:
    p = root / "localstate.json"
    p.write_text(json.dumps({"version": 1, "entries": entries}), encoding="utf-8")
    return p


def _run(root: Path, manifest: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--manifest", str(manifest), "--root", str(root), *extra],
        capture_output=True, text=True, timeout=60,
    )


def _sentinel(stdout: str) -> str:
    return stdout.rstrip("\n").splitlines()[-1]


def test_check_pass_skips_rebuild(tmp_path):
    marker = tmp_path / "rebuilt.marker"
    entries = [{
        "name": "already-fresh",
        "cost": "cheap",
        "check": "true",  # always passes -> rebuild must never run
        "rebuild": f"touch {marker}",
    }]
    manifest = _write_manifest(tmp_path, entries)

    proc = _run(tmp_path, manifest)

    assert proc.returncode == 0
    assert not marker.exists(), "rebuild ran even though check passed"
    assert "skip (check passed)" in proc.stdout
    assert _sentinel(proc.stdout) == "VERDICT=PASS missing=[]"


def test_check_fail_triggers_rebuild(tmp_path):
    target = tmp_path / "derived.txt"
    entries = [{
        "name": "needs-rebuild",
        "cost": "cheap",
        "check": f"test -f {target}",
        "rebuild": f"echo hello > {target}",
    }]
    manifest = _write_manifest(tmp_path, entries)

    assert not target.exists()
    proc = _run(tmp_path, manifest)

    assert proc.returncode == 0
    assert target.exists() and target.read_text().strip() == "hello"
    assert "rebuilding:" in proc.stdout
    assert _sentinel(proc.stdout) == "VERDICT=PASS missing=[]"


def test_dry_run_runs_nothing(tmp_path):
    target = tmp_path / "should_not_exist.txt"
    entries = [{
        "name": "needs-rebuild",
        "cost": "cheap",
        "check": f"test -f {target}",
        "rebuild": f"echo hello > {target}",
    }]
    manifest = _write_manifest(tmp_path, entries)

    proc = _run(tmp_path, manifest, "--dry-run")

    assert not target.exists(), "--dry-run must never invoke rebuild"
    assert "would rebuild:" in proc.stdout
    # dry-run leaves the entry unresolved -> it is honestly reported missing
    assert proc.returncode == 1
    assert _sentinel(proc.stdout) == "VERDICT=FAIL missing=[needs-rebuild]"


def test_rebuild_that_does_not_fix_it_stays_missing_and_fails_loud(tmp_path):
    # rebuild command is a no-op relative to what check demands -> still missing after.
    entries = [{
        "name": "unfixable",
        "cost": "cheap",
        "check": "test -f nonexistent-forever.txt",
        "rebuild": "true",
    }]
    manifest = _write_manifest(tmp_path, entries)

    proc = _run(tmp_path, manifest)

    assert proc.returncode == 1
    assert "recheck: rc=1" in proc.stdout
    assert _sentinel(proc.stdout) == "VERDICT=FAIL missing=[unfixable]"


def test_cheap_only_and_only_filters(tmp_path):
    entries = [
        {"name": "cheap-one", "cost": "cheap", "check": "true", "rebuild": "true"},
        {"name": "expensive-one", "cost": "expensive", "check": "false", "rebuild": "false"},
    ]
    manifest = _write_manifest(tmp_path, entries)

    proc = _run(tmp_path, manifest, "--cheap-only")

    assert proc.returncode == 0
    assert "expensive-one" not in proc.stdout.replace("selected=1", "")  # not processed
    assert "selected=1" in proc.stdout
    assert _sentinel(proc.stdout) == "VERDICT=PASS missing=[]"

    proc2 = _run(tmp_path, manifest, "--only", "expensive-one")
    assert proc2.returncode == 1
    assert "selected=1" in proc2.stdout
    assert _sentinel(proc2.stdout) == "VERDICT=FAIL missing=[expensive-one]"


def test_unknown_only_name_errors(tmp_path):
    entries = [{"name": "real-one", "cost": "cheap", "check": "true", "rebuild": "true"}]
    manifest = _write_manifest(tmp_path, entries)

    proc = _run(tmp_path, manifest, "--only", "not-a-real-entry")

    assert proc.returncode != 0
    assert "unknown entry name" in (proc.stdout + proc.stderr)


def test_output_is_bounded(tmp_path):
    entries = [{
        "name": "chatty",
        "cost": "cheap",
        "check": "python3 -c \"print('x' * 20000)\"; exit 1",
        "rebuild": "true",
    }]
    manifest = _write_manifest(tmp_path, entries)

    proc = _run(tmp_path, manifest)

    assert "truncated" in proc.stdout
    assert len(proc.stdout) < 20000  # capped per-entry, not passed through raw


# ---------------------------------------------------------------------------
# W6.2 / audit_2026-07-14 Part 2 #4: a rebuild that depends on the vendored
# embedder must FAIL LOUD when that dependency is missing -- never silently die.
# ---------------------------------------------------------------------------

def test_dependency_failure_blocks_rebuild_and_fails_loud(tmp_path):
    """When a depended-on entry does not end check-passing, the dependent's rebuild is REFUSED
    (never attempted) and a loud, greppable banner naming the dependency lands on stderr."""
    dep_marker = tmp_path / "dep_rebuilt.marker"
    child_marker = tmp_path / "child_rebuilt.marker"
    entries = [
        {  # the dependent comes FIRST in the manifest -> the ordering must still gate it
            "name": "voice-store",
            "cost": "expensive",
            "depends_on": ["embed-model-vendor"],
            "check": "false",                        # always needs a rebuild
            "rebuild": f"touch {child_marker}",      # must NEVER run while the dep is missing
        },
        {
            "name": "embed-model-vendor",
            "cost": "cheap",
            "check": "false",                        # the dependency is MISSING
            "rebuild": f"touch {dep_marker}; exit 1",  # rebuild also fails -> stays missing
        },
    ]
    manifest = _write_manifest(tmp_path, entries)

    proc = _run(tmp_path, manifest)

    assert proc.returncode != 0
    assert not child_marker.exists(), "dependent rebuild ran despite the failed dependency"
    assert "DEPENDENCY FAILURE" in proc.stderr
    assert "embed-model-vendor" in proc.stderr
    assert "BLOCKED" in proc.stdout
    # both the dependency and the blocked dependent are reported missing
    sentinel = _sentinel(proc.stdout)
    assert sentinel.startswith("VERDICT=FAIL")
    assert "voice-store" in sentinel and "embed-model-vendor" in sentinel


def test_dependency_present_allows_rebuild(tmp_path):
    """When the dependency ends check-passing, the dependent rebuilds normally (no false block)."""
    child_marker = tmp_path / "child_rebuilt.marker"
    entries = [
        {
            "name": "voice-store",
            "cost": "expensive",
            "depends_on": ["embed-model-vendor"],
            "check": f"test -f {child_marker}",       # fails first, passes after rebuild
            "rebuild": f"touch {child_marker}",
        },
        {
            "name": "embed-model-vendor",
            "cost": "cheap",
            "check": "true",                          # dependency present
            "rebuild": "true",
        },
    ]
    manifest = _write_manifest(tmp_path, entries)

    proc = _run(tmp_path, manifest)

    assert proc.returncode == 0
    assert child_marker.exists(), "dependent rebuild was blocked despite a present dependency"
    assert "DEPENDENCY FAILURE" not in proc.stderr
    assert _sentinel(proc.stdout) == "VERDICT=PASS missing=[]"


def test_dependency_gate_fires_under_narrowed_only_selection(tmp_path):
    """--only voice-store: the dependency (embed-model-vendor) is not selected, but is evaluated
    check-only so the loud gate still fires when it is missing."""
    child_marker = tmp_path / "child_rebuilt.marker"
    entries = [
        {
            "name": "voice-store",
            "cost": "expensive",
            "depends_on": ["embed-model-vendor"],
            "check": "false",
            "rebuild": f"touch {child_marker}",
        },
        {
            "name": "embed-model-vendor",
            "cost": "cheap",
            "check": "false",                          # missing
            "rebuild": "true",
        },
    ]
    manifest = _write_manifest(tmp_path, entries)

    proc = _run(tmp_path, manifest, "--only", "voice-store")

    assert proc.returncode != 0
    assert not child_marker.exists()
    assert "DEPENDENCY FAILURE" in proc.stderr
    assert "check-only, not selected" in proc.stdout


def test_unknown_depends_on_is_rejected(tmp_path):
    entries = [{
        "name": "x", "cost": "cheap", "check": "true", "rebuild": "true",
        "depends_on": ["nope"],
    }]
    manifest = _write_manifest(tmp_path, entries)

    proc = _run(tmp_path, manifest)

    assert proc.returncode != 0
    assert "depends_on names unknown" in (proc.stdout + proc.stderr)


# ---------------------------------------------------------------------------
# W6.1: the REAL localstate.json validates, and its per-project entries are
# expensive (so the launcher's --cheap-only OFFERS them, never fires them).
# ---------------------------------------------------------------------------

def test_real_manifest_validates_every_entry():
    """The shipped localstate.json loads cleanly: every entry has name+check+rebuild+cost, cost
    is cheap|expensive, and every depends_on names a real entry (load_manifest is the validator)."""
    es = _load_ensure_state_module()
    entries = es.load_manifest(REPO / "localstate.json")
    names = {e["name"] for e in entries}
    for e in entries:
        for key in ("name", "check", "rebuild", "cost"):
            assert key in e, f"entry {e.get('name')!r} missing {key!r}"
        assert e["cost"] in ("cheap", "expensive")
        for d in e.get("depends_on", []) or []:
            assert d in names, f"{e['name']!r} depends_on unknown {d!r}"


def test_real_manifest_has_per_project_entries_all_expensive():
    """The W6.1 per-project derived-state entries (nodemap-* / rounds-*) are present and EVERY
    one is cost=expensive -- the property that makes the launcher OFFER them instead of firing
    them under --cheap-only (the PSU law)."""
    es = _load_ensure_state_module()
    by_name = {e["name"]: e for e in es.load_manifest(REPO / "localstate.json")}
    for name in ("nodemap-eigenengine", "nodemap-paper_falqon",
                 "rounds-eigenengine", "rounds-paper_falqon"):
        assert name in by_name, f"missing per-project entry {name!r}"
        assert by_name[name]["cost"] == "expensive", f"{name!r} must be expensive to be offered-not-fired"


def test_cheap_only_fires_only_cheap_a_fake_expensive_proves_the_gate(tmp_path):
    """The gate at the REBUILD level: a cheap entry whose check fails IS rebuilt (marker appears);
    a fake expensive entry whose check fails is NOT even selected, so its rebuild NEVER runs
    (marker never appears) -- the exact guarantee the launcher relies on."""
    cheap_marker = tmp_path / "cheap.marker"
    expensive_marker = tmp_path / "expensive.marker"
    entries = [
        {"name": "cheap-one", "cost": "cheap",
         "check": f"test -f {cheap_marker}", "rebuild": f"touch {cheap_marker}"},
        {"name": "fake-expensive", "cost": "expensive",
         "check": "false", "rebuild": f"touch {expensive_marker}"},
    ]
    manifest = _write_manifest(tmp_path, entries)

    proc = _run(tmp_path, manifest, "--cheap-only")

    assert proc.returncode == 0
    assert cheap_marker.exists(), "cheap rebuild did not fire under --cheap-only"
    assert not expensive_marker.exists(), "expensive rebuild fired under --cheap-only (gate broken)"
    assert "selected=1" in proc.stdout
    assert _sentinel(proc.stdout) == "VERDICT=PASS missing=[]"
