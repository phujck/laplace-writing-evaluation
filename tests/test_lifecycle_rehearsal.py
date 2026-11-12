from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from laplace.engine.lifecycle_rehearsal import EVIDENCE_SCHEMA, PREREQUISITES, RehearsalRefused, run_faithful_lifecycle_rehearsal, validate_rehearsal_isolation

FIXTURE = Path(__file__).parent / "fixtures/lifecycle_rehearsal/provider_history.jsonl"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout.strip()


def _candidate(tmp_path: Path) -> tuple[Path, str, str, dict[str, Path]]:
    repo = tmp_path / "candidate"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "Lifecycle Rehearsal")
    _git(repo, "config", "user.email", "rehearsal@example.invalid")
    (repo / "engine.txt").write_text("candidate\n", encoding="utf-8")
    _git(repo, "add", "engine.txt")
    _git(repo, "commit", "-q", "-m", "candidate")
    protected: dict[str, Path] = {}
    for name in ("atlas", "blueprint", "provider", "watcher"):
        root = tmp_path / f"protected-{name}"
        root.mkdir()
        (root / "state.bin").write_bytes((name + "-state").encode())
        protected[name] = root
    return repo, _git(repo, "rev-parse", "HEAD"), _git(repo, "rev-parse", "HEAD^{tree}"), protected


def _run(tmp_path: Path, *, fixture: Path = FIXTURE) -> dict:
    repo, commit, tree, protected = _candidate(tmp_path)
    return run_faithful_lifecycle_rehearsal(
        repo_root=repo,
        candidate_commit=commit,
        candidate_tree=tree,
        provider_history_path=fixture,
        canonical_atlas_root=protected["atlas"],
        blueprint_root=protected["blueprint"],
        live_provider_root=protected["provider"],
        live_watcher_root=protected["watcher"],
    )


def test_rehearsal_is_deterministic_authority_free_and_honest(tmp_path: Path) -> None:
    repo, commit, tree, protected = _candidate(tmp_path)
    arguments = {
        "repo_root": repo,
        "candidate_commit": commit,
        "candidate_tree": tree,
        "provider_history_path": FIXTURE,
        "canonical_atlas_root": protected["atlas"],
        "blueprint_root": protected["blueprint"],
        "live_provider_root": protected["provider"],
        "live_watcher_root": protected["watcher"],
    }
    first = run_faithful_lifecycle_rehearsal(**arguments)
    second = run_faithful_lifecycle_rehearsal(**arguments)

    assert first["schema_version"] == EVIDENCE_SCHEMA
    assert first["publication_authority"] is False
    assert first["verdict"] == "CONTEST"
    assert first["verdict_reason"] == "CANONICAL-PREREQUISITES-REMAIN-OPEN"
    assert first["prerequisite_states"] == {node: "OPEN" for node in PREREQUISITES}
    assert set(first["plants"]) == {
        "cold-committed-tree",
        "retired-generation-replay",
        "checkpoint-compaction-orderings",
        "delayed-historical-duplicate",
    }
    assert {plant["status"] for plant in first["plants"].values()} == {"EVIDENCED"}
    assert first["semantic_trace_root"] == second["semantic_trace_root"]
    assert first["evidence_root"] == second["evidence_root"]
    assert first["timings"] != second["timings"]
    assert first["budgets"]["provider_invocations"] == 0
    assert first["isolation"]["network"] == "DISABLED"
    assert first["source_before_after_equal"] is True
    assert first["protected_before_after_equal"] is True


def test_rehearsal_refuses_writable_alias_of_protected_root(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    with pytest.raises(RehearsalRefused, match="WRITABLE-ROOT-ALIASES") as caught:
        validate_rehearsal_isolation(
            writable_roots={"output": source / "generated"},
            protected_roots={"source": source},
        )
    assert caught.value.reason == "WRITABLE-ROOT-ALIASES-PROTECTED-ROOT"


def test_failed_fixture_is_refused_not_promoted_to_pass(tmp_path: Path) -> None:
    broken = tmp_path / "broken.jsonl"
    rows = [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines()]
    rows[-1]["result"] = "REDELIVERED"
    broken.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n")
    evidence = _run(tmp_path / "run", fixture=broken)
    assert evidence["verdict"] == "CONTEST"
    assert evidence["verdict_reason"] == "PLANT-REFUSAL"
    assert evidence["failed_plants"] == ["delayed-historical-duplicate"]
    assert evidence["plants"]["delayed-historical-duplicate"]["status"] == "REFUSED"


def test_candidate_coordinate_mismatch_refuses_before_rehearsal(tmp_path: Path) -> None:
    repo, commit, tree, protected = _candidate(tmp_path)
    with pytest.raises(RehearsalRefused) as caught:
        run_faithful_lifecycle_rehearsal(
            repo_root=repo,
            candidate_commit=commit,
            candidate_tree="0" * 40,
            provider_history_path=FIXTURE,
            canonical_atlas_root=protected["atlas"],
            blueprint_root=protected["blueprint"],
            live_provider_root=protected["provider"],
            live_watcher_root=protected["watcher"],
        )
    assert caught.value.reason == "CANDIDATE-COORDINATE-MISMATCH"
