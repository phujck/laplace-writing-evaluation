"""Scoped fixture tests for scripts/sweep_deprecated_skills.py.

Builds a tiny synthetic canon (its own skills/, index.yaml, lifecycle.yaml) and
a tiny synthetic git repo, so the real production canon is never touched.
Covers: plan (dry-run touches nothing) / apply (moves the qualifying skill,
reversibly, and drops it from Canon.skills / available_refs by construction) /
skip-recently-deprecated (too few dream windows elapsed) / skip-still-used
(usage event after the deprecation timestamp) / the git-blame fallback path
for a skill deprecated with no lifecycle entry at all.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from laplace.pipeline.canon import Canon  # noqa: E402


def _load_sweep():
    spec = importlib.util.spec_from_file_location(
        "sweep_deprecated_skills", ROOT / "scripts" / "sweep_deprecated_skills.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("sweep_deprecated_skills", mod)
    spec.loader.exec_module(mod)
    return mod


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _write_skill(root: Path, name: str) -> None:
    d = root / "skills" / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(f"# {name}\n\nA fixture skill.\n", encoding="utf-8")


def _git(repo: Path, *args: str) -> None:
    # TZ=UTC: the env is scrubbed, so a GIT_*_DATE would otherwise be resolved
    # against /etc/localtime and shear on a non-UTC box (back-dated commits below).
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t.com",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t.com",
                        "TZ": "UTC",
                        "PATH": "/usr/bin:/bin"})


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q")


def build_fixture(tmp_path: Path):
    """canon root = tmp_path/repo/canon; also a real git repo at tmp_path/repo
    so the git-blame fallback path is exercisable."""
    repo = tmp_path / "repo"
    canon_dir = repo / "canon"
    (canon_dir / "skills").mkdir(parents=True)
    (canon_dir / "wiki").mkdir(parents=True)
    _init_repo(repo)

    now = datetime.now(timezone.utc)
    old_ts = _iso(now - timedelta(days=90))

    # dead_long_enough: lifecycle-deprecated 90 days ago, never used -> qualifies
    _write_skill(canon_dir, "dead_long_enough")
    # fresh_dead: lifecycle-deprecated yesterday -> too recent, skipped
    _write_skill(canon_dir, "fresh_dead")
    # still_used: lifecycle-deprecated 90 days ago but fired since -> skipped
    _write_skill(canon_dir, "still_used")
    # manifest_only_dead: no lifecycle entry; deprecated by a manifest edit only,
    # found via git-blame on index.yaml
    _write_skill(canon_dir, "manifest_only_dead")
    # kept: not deprecated at all, control
    _write_skill(canon_dir, "kept")

    index = {
        "version": 1, "wiki": {}, "domains": {},
        "skills": {
            "dead_long_enough": {"status": "experimental"},
            "fresh_dead": {"status": "experimental"},
            "still_used": {"status": "experimental"},
            "manifest_only_dead": {"status": "experimental"},
            "kept": {"status": "experimental"},
        },
    }
    (canon_dir / "index.yaml").write_text(yaml.safe_dump(index), encoding="utf-8")
    (repo / "canon" / ".gitignore").write_text("", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "seed fixture canon")

    # Edit manifest_only_dead's manifest line to deprecated, in its own commit,
    # 90 days back-dated so the git-blame fallback returns an old timestamp.
    text = (canon_dir / "index.yaml").read_text(encoding="utf-8")
    text = text.replace(
        "manifest_only_dead:\n    status: experimental",
        "manifest_only_dead:\n    status: deprecated",
    )
    (canon_dir / "index.yaml").write_text(text, encoding="utf-8")
    old_date = (now - timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    subprocess.run(
        ["git", "commit", "-q", "-am", "deprecate manifest_only_dead"],
        cwd=repo, check=True, capture_output=True,
        env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t.com",
             "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t.com",
             # old_date carries an explicit +00:00; TZ=UTC is the belt to that brace
             "GIT_AUTHOR_DATE": old_date, "GIT_COMMITTER_DATE": old_date,
             "TZ": "UTC",
             "PATH": "/usr/bin:/bin"},
    )

    lifecycle = {
        "skills": {
            "dead_long_enough": {
                "status": "deprecated",
                "history": [{"at": old_ts, "from": "experimental", "to": "deprecated",
                            "reason": "offered, never used"}],
            },
            "fresh_dead": {
                "status": "deprecated",
                "history": [{"at": _iso(now - timedelta(days=1)), "from": "experimental",
                            "to": "deprecated", "reason": "offered, never used"}],
            },
            "still_used": {
                "status": "deprecated",
                "history": [{"at": old_ts, "from": "experimental", "to": "deprecated",
                            "reason": "offered, never used"}],
            },
        }
    }
    (canon_dir / "lifecycle.yaml").write_text(yaml.safe_dump(lifecycle), encoding="utf-8")
    return repo, canon_dir, old_ts, now


def _seed_telemetry(monkeypatch, tmp_path: Path, events: list[dict]):
    state = tmp_path / "state"
    state.mkdir(exist_ok=True)
    monkeypatch.setenv("LAPLACE_STATE", str(state))
    monkeypatch.setenv("LAPLACE_SESSION", "fixturesess")
    from laplace.engine import telemetry
    telemetry.clear()
    for ev in events:
        # write raw so we control `ts` exactly (log() stamps ts=now)
        pass
    if events:
        path = telemetry.telemetry_path()
        import json
        with path.open("w", encoding="utf-8") as fh:
            for ev in events:
                fh.write(json.dumps(ev) + "\n")
    return telemetry


def test_dry_run_moves_nothing_and_reports_correct_plan(tmp_path, monkeypatch):
    repo, canon_dir, old_ts, now = build_fixture(tmp_path)
    _seed_telemetry(monkeypatch, tmp_path, [])  # no telemetry at all: elapsed-days fallback

    mod = _load_sweep()
    canon = Canon.load(canon_dir)
    plans = mod.build_plan(canon, repo, min_windows=3)
    by_name = {p.name: p for p in plans}

    assert set(by_name) == {"dead_long_enough", "fresh_dead", "still_used", "manifest_only_dead"}
    assert by_name["dead_long_enough"].qualifies is True
    assert by_name["dead_long_enough"].since_source == "lifecycle-history"
    assert by_name["fresh_dead"].qualifies is False
    assert "too recent" in by_name["fresh_dead"].reason
    assert by_name["still_used"].qualifies is True  # no usage seeded yet in this test
    assert by_name["manifest_only_dead"].since_source == "git-blame"
    assert by_name["manifest_only_dead"].qualifies is True

    # dry-run (the default CLI path) must not touch the filesystem
    rc = mod.main(["--root", str(canon_dir), "--repo-root", str(repo)])
    assert rc == 0
    for name in by_name:
        assert (canon_dir / "skills" / name).is_dir()
    assert not (canon_dir / "skills" / "_archive").exists() or \
        not any((canon_dir / "skills" / "_archive").iterdir())


def test_skip_recently_deprecated(tmp_path, monkeypatch):
    repo, canon_dir, old_ts, now = build_fixture(tmp_path)
    _seed_telemetry(monkeypatch, tmp_path, [])

    mod = _load_sweep()
    canon = Canon.load(canon_dir)
    plans = mod.build_plan(canon, repo, min_windows=3)
    fresh = next(p for p in plans if p.name == "fresh_dead")
    assert fresh.qualifies is False
    assert fresh.windows_elapsed < 3

    moved = mod.apply_plan(plans)
    assert "fresh_dead" not in {p.name for p in moved}
    assert (canon_dir / "skills" / "fresh_dead").is_dir()  # untouched


def test_skip_skill_used_since_deprecation(tmp_path, monkeypatch):
    repo, canon_dir, old_ts, now = build_fixture(tmp_path)
    _seed_telemetry(monkeypatch, tmp_path, [
        {"ts": _iso(now - timedelta(days=10)), "seq": 1, "phase": "execute",
         "skill": "still_used", "kind": "protocol"},
    ])

    mod = _load_sweep()
    canon = Canon.load(canon_dir)
    plans = mod.build_plan(canon, repo, min_windows=3)
    used = next(p for p in plans if p.name == "still_used")
    assert used.qualifies is False
    assert used.usage_since == 1
    assert "still exercised" in used.reason


def test_apply_moves_qualifying_skill_and_drops_from_available_refs(tmp_path, monkeypatch):
    repo, canon_dir, old_ts, now = build_fixture(tmp_path)
    _seed_telemetry(monkeypatch, tmp_path, [
        {"ts": _iso(now - timedelta(days=10)), "seq": 1, "phase": "execute",
         "skill": "still_used", "kind": "protocol"},
    ])

    mod = _load_sweep()
    before = Canon.load(canon_dir)
    assert "dead_long_enough" in before.skills
    refs_before = [f"canon://skills/{n}" for n in before.skills]

    rc = mod.main(["--root", str(canon_dir), "--repo-root", str(repo), "--apply"])
    assert rc == 0

    # moved: gone from the live tree, present in _archive
    assert not (canon_dir / "skills" / "dead_long_enough").exists()
    assert (canon_dir / "skills" / "_archive" / "dead_long_enough" / "SKILL.md").is_file()
    assert not (canon_dir / "skills" / "manifest_only_dead").exists()
    assert (canon_dir / "skills" / "_archive" / "manifest_only_dead").is_dir()

    # too-recent and still-used skills are untouched
    assert (canon_dir / "skills" / "fresh_dead").is_dir()
    assert (canon_dir / "skills" / "still_used").is_dir()
    assert (canon_dir / "skills" / "kept").is_dir()

    after = Canon.load(canon_dir)
    assert "dead_long_enough" not in after.skills
    assert "manifest_only_dead" not in after.skills
    refs_after = [f"canon://skills/{n}" for n in after.skills]
    assert len(refs_after) == len(refs_before) - 2
    assert "canon://skills/dead_long_enough" not in refs_after
    assert "canon://skills/dead_long_enough" in refs_before

    # reversible: the move is a plain filesystem relocation, so reversing it is
    # too (in the real flow the orchestrator commits the move, and a revert of
    # that commit - or another plain move back - restores the skill exactly).
    import shutil
    shutil.move(str(canon_dir / "skills" / "_archive" / "dead_long_enough"),
               str(canon_dir / "skills" / "dead_long_enough"))
    assert (canon_dir / "skills" / "dead_long_enough" / "SKILL.md").is_file()
