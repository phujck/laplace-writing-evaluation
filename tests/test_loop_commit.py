"""B5 in-loop durability — loop_commit.py banks each accepted incumbent to the
CURRENT git branch, AUGMENTING the git-independent snapshot store.

The contract under test:
  (a) an accept-shaped call on a dirty manuscript dir -> exactly ONE commit whose
      tree carries the manuscript bytes;
  (b) a second call on a now-clean tree -> exit 0, NO new commit (no-op accept);
  (c) a real git error (no committer identity, with staged changes) -> NONZERO
      exit + a loud stderr message;
  (d) a push failure (no remote configured) -> exit 0 with a "push-failed" note.

Every case runs against a SCRATCH git repo under tmp_path — never the session repo.
"""
import subprocess
import sys
from pathlib import Path

import pytest

LOOP_COMMIT = str(Path(__file__).resolve().parents[1]
                  / ".claude" / "workflows" / "loop_commit.py")


def _git(repo: Path, *args: str, **env) -> subprocess.CompletedProcess:
    # TZ=UTC so any GIT_*_DATE passed through **env resolves absolutely rather than
    # against /etc/localtime (the tz shear that bit the evidence-bundle fixture).
    import os
    e = {**os.environ, "TZ": "UTC", **env}
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, check=False, env=e)


def _run(repo: Path, *args: str) -> subprocess.CompletedProcess:
    """Invoke loop_commit.py with cwd=repo (the loop invokes it from the root)."""
    return subprocess.run([sys.executable, LOOP_COMMIT, *args],
                          cwd=str(repo), capture_output=True, text=True, check=False)


def _init_repo(tmp_path: Path, *, identity: bool = True) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "work")
    if identity:
        _git(repo, "config", "user.email", "eigen@laplace.test")
        _git(repo, "config", "user.name", "Eigen Test")
    # a first commit so HEAD is a born branch (a realistic mid-run tree).
    (repo / "README").write_text("seed\n")
    _git(repo, "add", "-A")
    if identity:
        _git(repo, "commit", "-q", "-m", "seed")
    return repo


def _count_commits(repo: Path) -> int:
    r = _git(repo, "rev-list", "--count", "HEAD")
    return int(r.stdout.strip()) if r.returncode == 0 else 0


# --- (a) accept-shaped call on a dirty dir -> exactly one commit with the bytes -

def test_dirty_dir_commits_manuscript_bytes(tmp_path):
    repo = _init_repo(tmp_path)
    man = repo / "manuscript"
    man.mkdir()
    (man / "main.tex").write_text("\\documentclass{article}\\begin{document}hi\\end{document}\n")
    before = _count_commits(repo)

    res = _run(repo, "manuscript", "r3")
    assert res.returncode == 0, res.stderr
    assert _count_commits(repo) == before + 1, "exactly one round commit"

    # the commit message is the tagged round label
    msg = _git(repo, "log", "-1", "--pretty=%s").stdout.strip()
    assert msg == "loop: r3 accepted incumbent"

    # the committed tree carries the manuscript bytes
    show = _git(repo, "show", "HEAD:manuscript/main.tex")
    assert show.returncode == 0
    assert "documentclass" in show.stdout
    # working tree is clean for that path after the commit
    assert _git(repo, "status", "--porcelain", "manuscript").stdout.strip() == ""


# --- (b) second call on a clean tree -> exit 0, no new commit ------------------

def test_clean_tree_is_noop(tmp_path):
    repo = _init_repo(tmp_path)
    man = repo / "manuscript"
    man.mkdir()
    (man / "main.tex").write_text("body\n")
    assert _run(repo, "manuscript", "r1").returncode == 0
    after_first = _count_commits(repo)

    res = _run(repo, "manuscript", "r2")   # nothing changed
    assert res.returncode == 0
    assert "nothing-to-commit" in res.stdout
    assert _count_commits(repo) == after_first, "no new commit on a clean tree"


# --- (c) real git error (no identity, with staged changes) -> nonzero + loud --

def test_missing_identity_is_hard_error(tmp_path):
    repo = _init_repo(tmp_path, identity=False)
    man = repo / "manuscript"
    man.mkdir()
    (man / "main.tex").write_text("body\n")

    # force git to have no usable identity even from a global/system config
    res = _run_no_identity(repo, "manuscript", "r1")
    assert res.returncode != 0, "a commit with no identity must fail hard"
    assert "loop_commit: ERROR" in res.stderr
    assert "git commit failed" in res.stderr


def _run_no_identity(repo: Path, *args: str) -> subprocess.CompletedProcess:
    import os
    env = {**os.environ,
           "GIT_CONFIG_GLOBAL": str(repo / ".no-global"),
           "GIT_CONFIG_SYSTEM": str(repo / ".no-system"),
           "GIT_AUTHOR_NAME": "", "GIT_AUTHOR_EMAIL": "",
           "GIT_COMMITTER_NAME": "", "GIT_COMMITTER_EMAIL": "",
           "EMAIL": "", "GIT_AUTHOR_DATE": "", "GIT_COMMITTER_DATE": ""}
    return subprocess.run([sys.executable, LOOP_COMMIT, *args],
                          cwd=str(repo), capture_output=True, text=True,
                          check=False, env=env)


# --- (c') detached HEAD -> nonzero + loud (not on a branch) --------------------

def test_detached_head_is_hard_error(tmp_path):
    repo = _init_repo(tmp_path)
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "checkout", "-q", head)     # detach
    man = repo / "manuscript"
    man.mkdir()
    (man / "main.tex").write_text("body\n")

    res = _run(repo, "manuscript", "r1")
    assert res.returncode != 0
    assert "loop_commit: ERROR" in res.stderr
    assert "detached HEAD" in res.stderr or "not on a branch" in res.stderr


# --- (d) push failure (no remote) -> exit 0 with a push-failed note ------------

def test_push_failure_is_a_warning(tmp_path):
    repo = _init_repo(tmp_path)
    man = repo / "manuscript"
    man.mkdir()
    (man / "main.tex").write_text("body\n")
    before = _count_commits(repo)

    res = _run(repo, "manuscript", "r1")   # no remote -> push fails
    assert res.returncode == 0, res.stderr
    assert "push-failed" in res.stdout
    assert _count_commits(repo) == before + 1, "the local commit still landed"


def test_prestaged_unrelated_file_is_not_swept(tmp_path):
    """The judge's sweep probe, banked: a file someone else staged must not ride
    a round commit — the commit is pathspec-scoped to the manuscript dir."""
    repo = _init_repo(tmp_path)
    ms = repo / "manuscript"
    ms.mkdir()
    (ms / "main.tex").write_text("\\documentclass{article}\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "seed")
    # someone else stages an unrelated file; the manuscript then goes dirty
    (repo / "notes_unrelated.txt").write_text("scratch\n", encoding="utf-8")
    _git(repo, "add", "notes_unrelated.txt")
    (ms / "main.tex").write_text("\\documentclass{article}\n% round edit\n",
                                 encoding="utf-8")
    r = _run(repo, "manuscript", "r9")
    assert r.returncode == 0
    names = _git(repo, "show", "HEAD", "--name-only", "--format=").stdout
    assert "manuscript/main.tex" in names
    assert "notes_unrelated.txt" not in names            # not swept
    staged = _git(repo, "diff", "--cached", "--name-only").stdout
    assert "notes_unrelated.txt" in staged               # still staged for its owner
