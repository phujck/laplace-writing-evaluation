"""Versioning (laplace.core.versioning): pure-Python git for owned paths - every mutation Dulwich, no daemon,
no fsmonitor. Callers name the exact paths they own; nothing here pushes or reaches a remote.

The engine used to shell ``git.exe`` and capture its output through an OS pipe.
On Windows that deadlocked: Claude Code's background ``git-fsmonitor--daemon``
inherited the pipe's write handle, so the read never saw EOF and the call hung
past its own timeout - ``laplace_assess`` froze for ~30 minutes at a time.

Dulwich removes the entire class of bug by construction: versioning itself
starts no git process, opens no pipe and needs no daemon, so nothing can be
inherited and nothing can hang. One qualification: a Dulwich commit runs the
repository's own pre-commit, commit-msg and post-commit hooks when they are
installed (an absent hook starts nothing). The engine's own repositories carry
none; a caller versioning a repository with hooks gets those hook processes. Every canon mutation - a lifecycle write, a forged skill, a rollback -
versions through here, and always will: the mutation surface is Dulwich-only
by invariant (``test_engine_git_mutations_are_pure_python``).

ONE read-only query, ``log_paths_since``, additionally carries a subprocess
fast path (the audit's F2: the Dulwich walker is ~8.6x slower than the ``git
log`` the same repo already shells elsewhere). It is fenced by the INVARIANT
GUARD - the thing the first landing was missing and the revert was right about:

* read-only, and reachable from no mutation function;
* fsmonitor and the untracked cache are forced OFF on that one invocation, so
  no daemon exists to inherit the pipe that deadlocked Windows;
* ``stdin`` is ``/dev/null`` and the call is timeout-bounded;
* EVERY failure - a poisoned ``subprocess.run``, a missing git, a timeout, a
  non-zero rc, undecodable output - falls back to the Dulwich walker, so the
  module remains functionally pure-python end to end with no git binary at all;
* ``LAPLACE_GIT_PURE_PYTHON=1`` disables the fast path outright.

The engine only ever commits a small set of canon files and never merges, so
the surface is deliberately tiny: ``ensure_repo``, ``commit``, ``commit_all``,
``head_sha``, ``log_paths_since``, and a path-scoped ``revert``. Pushing to a
remote stays out of this hot path (an explicit, occasional action), so Dulwich's
network/auth surface is never touched here.
"""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from dulwich import porcelain
from dulwich.repo import Repo

# A stable author so the canon history is legibly the engine's own.
_AUTHOR = b"Laplace Engine <laplace@localhost>"


def _b(s: str | bytes) -> bytes:
    return s.encode("utf-8") if isinstance(s, str) else s


def _abspaths(root: Path, paths) -> list[str]:
    out = []
    for p in paths:
        pp = Path(p)
        out.append(str(pp if pp.is_absolute() else (root / pp)))
    return out


def ensure_repo(root) -> Repo:
    """Open the git repo at ``root``, initialising one if absent."""
    root = Path(root)
    if (root / ".git").exists():
        return Repo(str(root))
    root.mkdir(parents=True, exist_ok=True)
    return porcelain.init(str(root))


def commit(root, paths, message: str) -> str | None:
    """Stage ``paths`` and commit. Returns the new sha, or None if nothing staged.

    Mirrors the old ``git add <paths> && git diff --cached --quiet || git commit``:
    if staging produced no change against HEAD, there is nothing to commit.
    """
    root = Path(root)
    repo = ensure_repo(root)
    porcelain.add(repo, paths=_abspaths(root, paths))
    # untracked_files="no" (F3, WO-20260820-the-full-self-audit): this call only
    # ever reads st.staged below, which porcelain.status computes via
    # get_tree_changes — entirely independent of the untracked_files argument, so
    # this is a same-semantics, zero-new-import, ~90-100x-faster read (it skips
    # dulwich's pure-Python get_untracked_paths walk of the WHOLE working tree,
    # ~29k files including a gitignored multi-GB .venv, to answer a question only
    # about the paths already staged above).
    st = porcelain.status(repo, untracked_files="no")
    if not any(st.staged.values()):
        return None
    sha = porcelain.commit(
        repo, message=_b(message), author=_AUTHOR, committer=_AUTHOR, sign=False
    )
    return sha.decode() if isinstance(sha, (bytes, bytearray)) else str(sha)


def commit_all(root, message: str) -> str | None:
    """Stage every tracked-or-new file under ``root`` (excluding .git) and commit."""
    root = Path(root)
    repo = ensure_repo(root)
    files = [str(p) for p in root.rglob("*") if p.is_file() and ".git" not in p.parts]
    if files:
        porcelain.add(repo, paths=files)
    sha = porcelain.commit(
        repo, message=_b(message), author=_AUTHOR, committer=_AUTHOR, sign=False
    )
    return sha.decode() if isinstance(sha, (bytes, bytearray)) else str(sha)


def head_sha(root) -> str | None:
    """The current HEAD sha, or None if the repo has no commits / does not exist."""
    try:
        return Repo(str(Path(root))).head().decode()
    except Exception:  # noqa: BLE001 - any repo/HEAD problem is "unknown"
        return None


def _parse_since(since: str | None) -> int:
    """ISO timestamp -> epoch seconds. None / unparseable -> 24h ago (a safe default)."""
    if since:
        try:
            dt = datetime.fromisoformat(since)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp())
        except ValueError:
            pass
    return int(datetime.now(timezone.utc).timestamp()) - 86400


def _log_paths_since_dulwich(root: Path, cutoff: int) -> set[str] | None:
    """The pure-dulwich walk. Always correct, ~8.6x slower than ``git log``; it
    is both the fallback and the parity oracle for the subprocess fast path."""
    try:
        repo = Repo(str(root))
    except Exception:  # noqa: BLE001
        return None
    try:
        head = repo.head()
    except KeyError:
        return set()  # no commits yet
    paths: set[str] = set()
    try:
        for entry in repo.get_walker(include=[head], since=cutoff):
            commit_obj = entry.commit
            if len(commit_obj.parents) < 1:
                continue  # --min-parents=1: skip the root commit
            changes = entry.changes()
            for ch in changes:
                for c in (ch if isinstance(ch, list) else [ch]):  # merges -> list of lists
                    for te in (c.new, c.old):
                        if te is not None and te.path:
                            paths.add(te.path.decode("utf-8", "replace").replace("\\", "/"))
    except Exception:  # noqa: BLE001 - a history read problem is "unknown"
        return None
    return paths


# The one shelled invocation in this module, and the flags that make it safe.
# fsmonitor/untrackedCache OFF: no daemon exists to inherit the pipe (the whole
# reason this module went pure-python). quotePath=false: raw UTF-8 path bytes
# instead of octal escapes. --no-renames: dulwich reports both sides of a rename
# as changed paths, so rename detection would break exact-set parity.
_GIT_READ_CONFIG = (
    "-c", "core.fsmonitor=false",
    "-c", "core.untrackedCache=false",
    "-c", "core.quotePath=false",
    "-c", "gc.auto=0",
)


def _log_paths_since_subprocess(root: Path, cutoff: int) -> set[str] | None:
    """The ~8.6x read-only fast path. None means "could not answer" - NEVER an
    empty answer - so the caller always falls through to Dulwich rather than
    mistaking an unavailable git for a repo where nothing moved.

    Read-only by construction: ``git log``, no index write, no ref write, no
    mutation function reaches this. Any exception at all is a fallback."""
    if os.environ.get("LAPLACE_GIT_PURE_PYTHON", "").strip() not in ("", "0"):
        return None  # the kill switch: dulwich-only, no child process
    since_iso = datetime.fromtimestamp(cutoff, timezone.utc).isoformat()
    try:
        out = subprocess.run(
            ["git", *_GIT_READ_CONFIG, "log", f"--since={since_iso}",
             "--min-parents=1", "--name-only", "--no-renames", "--format=", "-z"],
            cwd=str(root), capture_output=True, timeout=60,
            stdin=subprocess.DEVNULL,
        )
    except Exception:  # noqa: BLE001 - deliberately total; see the module's guard
        # Every way git can be absent or hostile reads the same: no answer, fall
        # back. The invariant test poisons subprocess.run with a bare
        # AssertionError and this must swallow that too.
        return None
    if out.returncode != 0:
        return None
    paths: set[str] = set()
    for rec in out.stdout.split(b"\0"):
        if not rec:
            continue  # the empty commit header --format= leaves between entries
        paths.add(rec.decode("utf-8", "replace").replace("\\", "/"))
    return paths


def log_paths_since(root, since: str | None) -> set[str] | None:
    """Repo-relative paths changed by non-root commits since ``since``.

    Replaces ``git log --since --min-parents=1 --name-only --format=``. Returns
    None when git is unavailable (caller falls back to "no grace"), an empty set
    when the repo has no qualifying commits.

    Reads through the guarded ``git log`` fast path when one is available and
    falls back to the Dulwich walker on any failure whatsoever - see the module
    docstring's INVARIANT GUARD. The two are parity-tested
    (``test_log_paths_since_subprocess_matches_dulwich``).
    """
    root = Path(root)
    if not (root / ".git").exists():
        return None
    cutoff = _parse_since(since)
    fast = _log_paths_since_subprocess(root, cutoff)
    if fast is not None:
        return fast
    return _log_paths_since_dulwich(root, cutoff)


def _resolve_ref(repo: Repo, ref: str):
    if ref in ("HEAD", b"HEAD"):
        return repo.head()
    rb = ref.encode() if isinstance(ref, str) else ref
    if rb in repo.object_store:
        return rb
    try:
        return repo.refs[rb]
    except KeyError:
        for sha in repo.object_store:  # short-sha fallback (canon repos are small)
            if sha.startswith(rb):
                return sha
        raise KeyError(ref)


def revert(root, ref: str) -> tuple[bool, str]:
    """Path-scoped inverse-restore of one commit, then commit "Revert <ref>".

    Dulwich has no porcelain revert. The engine never merges and only ever
    commits a small file set, so reverting is exact: for every path the target
    commit changed, restore the parent's version (or delete a file the commit
    added), then record the inverse as a new commit. Returns (ok, sha-or-error).
    """
    from dulwich.diff_tree import tree_changes
    from dulwich.object_store import tree_lookup_path

    root = Path(root)
    try:
        repo = Repo(str(root))
        cid = _resolve_ref(repo, ref)
        commit_obj = repo[cid]
        if not commit_obj.parents:
            return False, "cannot revert the root commit"
        parent = repo[commit_obj.parents[0]]
        touched: list[str] = []
        for ch in tree_changes(repo.object_store, parent.tree, commit_obj.tree):
            pe = ch.new if (ch.new and ch.new.path) else ch.old
            if pe is None or not pe.path:
                continue
            fp = root / pe.path.decode("utf-8", "replace")
            try:
                _mode, blob_sha = tree_lookup_path(repo.get_object, parent.tree, pe.path)
                fp.parent.mkdir(parents=True, exist_ok=True)
                fp.write_bytes(repo[blob_sha].data)
            except KeyError:
                if fp.exists():
                    fp.unlink()  # the commit added it; the inverse removes it
            touched.append(str(fp))
        if touched:
            porcelain.add(repo, paths=touched)
        sha = porcelain.commit(
            repo, message=_b(f"Revert {ref}"), author=_AUTHOR, committer=_AUTHOR, sign=False
        )
        return True, (sha.decode() if isinstance(sha, (bytes, bytearray)) else str(sha))
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
