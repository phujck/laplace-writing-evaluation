"""THE PROBE — a fresh-session instrument that MEASURES accumulation and banks rows.

FIX SEQ 0 of the internals campaign (``evidence/INTERNALS_2026-09-16/fixlist.jsonl``).
Every later fix is judged by the columns this organ produces. His acceptance law:
*a fresh session must do what you expect and accumulate nothing* — measured, never
tests-green.

WHAT IT DOES NOT DO: it does not judge. There is not one hand-set numeric gate in
this module and there must never be one (his ruling: "these thresholds are stupid").
The only number the probe chooses is a single generous subprocess timeout, and that
number is itself banked as a column of every row so a reader can see what bounded it.
Retention is CONTENT-KEYED — :func:`prune` keeps the latest row per
``(head, tag, interpreter)`` plus every row some other store references — never a
numeric cap. Seq 9 (``hand-set-thresholds-as-gates``) is the only place allowed to
derive a refusing number, and it derives it FROM these rows.

THE MEASUREMENT, per phase, all of it a before/after difference:

* wall seconds, return code, stdout and stderr bytes
* bytes written inside the cold clone (work tree, ``.git`` as its own column, and
  ``.git/index`` as a third — index churn is measured, never excluded)
* files created in the clone (count + top paths)
* entries created under each watched temp root (``/tmp``, ``$TMPDIR``,
  ``/tmp/claude-1000``)
* processes left resident that were not there before (full ps diff, and the
  descendants-of-this-probe subset)
* ``git count-objects -v`` size / size-pack delta inside the clone
* whether a MEASUREMENT subprocess failed (``procs_snapshot_error``,
  ``git_objects_error``) — a probe that could not look must never bank a 0

WHAT ``--repeat N`` MEANS: N INDEPENDENT COLD CLONES, one scratch subdirectory each.
The banked ``spread`` is therefore a cold-vs-cold repeatability distribution
(``spread_temperature = "cold-cold"``), not a cold-then-warm sequence. Replaying the
phases inside one clone would measure the warm tree and must never be called a spread.

PHASES: the SessionStart hook (node), the wake (``scripts/wake.py --grade 0``), one
bounded read-only act (``scripts/reconstruct_node.py``), and the least-mutating close
invocation (see :data:`CLOSE_ARGV` / :data:`CLOSE_NOTE`).

INTERPRETER: every phase runs under ``/usr/bin/python3`` explicitly, and the row
carries ``which -a python3`` as seen BOTH by the stripped cold environment AND by the
user's login shell — two columns, because one-interpreter has not landed
(``~/.bashrc`` still puts a refused ``.venv`` first on PATH).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

SCHEMA = "laplace.engine.probe-run/1"

#: Where the rows live. Repo-relative; banked through the house seam when it imports.
STORE = "contract/probe_runs.jsonl"

#: The declared runtime. Never ``python3`` off PATH — that resolves to the refused .venv.
SYSTEM_PYTHON = "/usr/bin/python3"

#: The cold PATH. Not a threshold: it is the minimal system PATH, named so that no
#: shell rc file and no activated environment can reach into a measured phase.
MINIMAL_PATH = "/usr/local/bin:/usr/bin:/bin"

#: The ONE number this organ chooses, and it is banked on every row it produces
#: (``subprocess_timeout_s``) so it is never an invisible bound. Generous by design:
#: it exists to stop a hung phase from hanging the probe, not to judge a phase.
DEFAULT_TIMEOUT_S = 900

#: Every SUBSIDIARY subprocess bound, expressed as a fraction of the one number above
#: — never typed as seconds anywhere in this module. :func:`derive_bounds` turns them
#: into seconds against whatever ``timeout`` the caller passed, and the resulting
#: seconds are banked on the row as ``bounds``, so a reader of a row can see every
#: bound that was in force, not just the outer one.
BOUND_FRACTIONS = {
    "login_which": 1 / 15,    # `bash -lc which -a python3`
    "ps": 1 / 15,             # the process snapshot
    "git_objects": 2 / 15,    # `git count-objects -v`, twice per phase
    "git_plumbing": 2 / 3,    # rev-parse / status on the source tree
    "git_remote": 2 / 15,     # `git remote remove origin` in the clone
}


def derive_bounds(timeout: float = DEFAULT_TIMEOUT_S) -> dict[str, int]:
    """The subsidiary bounds in seconds, derived from the one banked timeout."""
    return {k: max(1, int(round(timeout * f))) for k, f in BOUND_FRACTIONS.items()}


#: Bounds in force when a helper is called without an explicit ``bounds`` mapping.
DEFAULT_BOUNDS = derive_bounds(DEFAULT_TIMEOUT_S)

#: How far the banked EVIDENCE lists are truncated. Not gates — they bound the size of
#: a row, not the verdict of a phase — but banked on every row (``evidence_caps``) for
#: the same reason the timeout is: a reader of a 5-entry ``_top`` list must be able to
#: tell truncation from completeness.
EVIDENCE_CAPS = {"top": 5, "tail_bytes": 400, "argv_chars": 120}

#: The least-mutating close invocation found in ``scripts/sewup.py`` (2026-09-16):
#: ``--dry-run`` makes every writing step report instead of write (sewup.py:63), and
#: ``--only`` skips the gate-liveness refusal (sewup.py:1881) and runs exactly one
#: step. ``handoff`` is the close's own render, which under ``--dry-run`` goes to
#: stdout and a scratch path OUTSIDE the repo. It runs inside the throwaway clone,
#: whose ``origin`` remote the probe removes, so nothing it could do reaches the
#: real tree. This is measured as the close phase; the full close is NOT run.
CLOSE_ARGV = ["scripts/sewup.py", "--dry-run", "--only", "handoff", "--no-bequest-prompt"]
CLOSE_NOTE = ("least-mutating close: --dry-run (writing steps report only) + --only handoff "
              "(one step, gate-liveness skipped), inside the disposable clone with origin "
              "removed. The real close is not run.")

#: Excluded from a CLONE-side snapshot: only git's transient lock, which exists for
#: milliseconds and whose presence in a snapshot is an artefact of when we looked.
#: ``.git/index`` is NOT here — it is measured and reported as its own column
#: (``git_index_bytes_written``); deleting it from the measurement made index churn
#: invisible inside the very tree the probe exists to watch. Nor is :data:`STORE`:
#: the probe never banks into the clone, so excluding it there bought nothing and
#: would have hidden a real write.
CLONE_EXCLUDE_RELPATHS = {".git/index.lock"}

#: Excluded from a SOURCE-TREE self-snapshot: the clone exclusions plus the probe's
#: own store, which the probe itself appends to and which would otherwise measure the
#: instrument rather than the tree.
SOURCE_EXCLUDE_RELPATHS = CLONE_EXCLUDE_RELPATHS | {STORE}

#: The relpath split out of the ``.git`` columns into its own.
GIT_INDEX_RELPATH = os.path.join(".git", "index")


# --------------------------------------------------------------------------- env

def cold_env(*, home: str | None = None, tmpdir: str | None = None,
             extra: dict[str, str] | None = None) -> dict[str, str]:
    """The stripped environment every phase runs under.

    Minimal PATH, HOME preserved, UTF-8 forced. Explicitly ABSENT: ``CLAUDE_ENV_FILE``
    (the hook's env-injection door), ``VIRTUAL_ENV``, ``PYTHONPATH``, ``PYTHONHOME``,
    and everything else the login shell carries — a phase measured under an inherited
    environment is measuring the session, not the repository.
    """
    env = {
        "PATH": MINIMAL_PATH,
        "HOME": home if home is not None else os.environ.get("HOME", "/root"),
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TERM": "dumb",
        "USER": os.environ.get("USER", ""),
        "LOGNAME": os.environ.get("LOGNAME", ""),
    }
    if tmpdir:
        env["TMPDIR"] = tmpdir
    if extra:
        env.update(extra)
    return {k: v for k, v in env.items() if v != ""}


def which_all(prog: str, env: dict[str, str]) -> list[str]:
    """``which -a`` as that env sees it, without a shell."""
    out: list[str] = []
    for part in env.get("PATH", "").split(os.pathsep):
        if not part:
            continue
        cand = Path(part) / prog
        if cand.is_file() and os.access(cand, os.X_OK):
            out.append(str(cand))
    return out


def which_all_login(prog: str = "python3", *,
                    bounds: dict[str, int] | None = None) -> list[str]:
    """``which -a`` as the USER'S LOGIN SHELL sees it — the other half of the
    interpreter column. This is the one place the probe deliberately does NOT strip
    the environment: the whole point is to record what a human shell would resolve.
    """
    bounds = bounds or DEFAULT_BOUNDS
    try:
        p = subprocess.run(["bash", "-lc", f"which -a {prog}"], capture_output=True,
                           text=True, timeout=bounds["login_which"])
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover - box-dependent
        return [f"<unavailable: {type(exc).__name__}>"]
    return [ln.strip() for ln in p.stdout.splitlines() if ln.strip()]


# ---------------------------------------------------------------- tree snapshots

def snapshot_tree(root: Path, exclude: set[str] | None = None) -> dict[str, tuple[int, int]]:
    """``{relpath: (size, mtime_ns)}`` for every regular file under ``root``.

    The default exclusion is the CLONE one (:data:`CLONE_EXCLUDE_RELPATHS`); pass
    :data:`SOURCE_EXCLUDE_RELPATHS` when snapshotting the probe's own source tree.
    """
    exclude = CLONE_EXCLUDE_RELPATHS if exclude is None else exclude
    out: dict[str, tuple[int, int]] = {}
    root = Path(root)
    for dirpath, _dirnames, filenames in os.walk(root, followlinks=False):
        for name in filenames:
            p = Path(dirpath) / name
            rel = os.path.relpath(p, root)
            if rel in exclude:
                continue
            try:
                st = p.lstat()
            except OSError:
                continue
            out[rel] = (st.st_size, st.st_mtime_ns)
    return out


def _split_git(snap: dict[str, tuple[int, int]]) -> tuple[dict, dict]:
    work, gitdir = {}, {}
    for rel, v in snap.items():
        (gitdir if rel == ".git" or rel.startswith(".git" + os.sep) else work)[rel] = v
    return work, gitdir


def _split_index(gitdir: dict[str, tuple[int, int]]) -> tuple[dict, dict]:
    """Split ``.git/index`` out of the ``.git`` snapshot so index churn is its own
    column instead of being deleted from the measurement."""
    rest = {k: v for k, v in gitdir.items() if k != GIT_INDEX_RELPATH}
    idx = {k: v for k, v in gitdir.items() if k == GIT_INDEX_RELPATH}
    return rest, idx


def is_bytecode_cache(rel: str) -> bool:
    """Interpreter bytecode, which a cold tree writes once and which no fix in this
    campaign is trying to remove. Split out as its OWN columns rather than filtered
    away: the first banked row showed __pycache__ is nearly all of a cold clone's
    written bytes, so a reader who cannot separate the two cannot see state growth
    at all. This is a content split, not a threshold.
    """
    return rel.endswith(".pyc") or ("__pycache__" + os.sep) in rel or rel.startswith("__pycache__" + os.sep)


def diff_tree(before: dict[str, tuple[int, int]], after: dict[str, tuple[int, int]],
              *, top: int = EVIDENCE_CAPS["top"]) -> dict[str, Any]:
    """What the phase wrote: created files at full size, modified files at the
    absolute size delta (a truncation is a write too), counted by size+mtime change.

    Every byte/file column has an ``_ex_cache`` twin that excludes interpreter
    bytecode — see :func:`is_bytecode_cache`.
    """
    created = [r for r in after if r not in before]
    modified = [r for r in after if r in before and after[r] != before[r]]
    deleted = [r for r in before if r not in after]

    def _bytes(cr, mo):
        return (sum(after[r][0] for r in cr)
                + sum(abs(after[r][0] - before[r][0]) for r in mo))

    cr_ex = [r for r in created if not is_bytecode_cache(r)]
    mo_ex = [r for r in modified if not is_bytecode_cache(r)]
    return {
        "files_created": len(created),
        "files_created_top": sorted(created, key=lambda r: -after[r][0])[:top],
        "files_modified": len(modified),
        "files_modified_top": sorted(modified)[:top],
        "files_deleted": len(deleted),
        "bytes_written": _bytes(created, modified),
        "files_created_ex_cache": len(cr_ex),
        "files_created_ex_cache_top": sorted(cr_ex, key=lambda r: -after[r][0])[:top],
        "files_modified_ex_cache": len(mo_ex),
        "files_modified_ex_cache_top": sorted(mo_ex)[:top],
        "bytes_written_ex_cache": _bytes(cr_ex, mo_ex),
    }


def snapshot_dirs(dirs: list[str]) -> dict[str, list[str]]:
    """Top-level entry names under each watched temp root (missing root -> empty)."""
    out: dict[str, list[str]] = {}
    for d in dirs:
        try:
            out[d] = sorted(os.listdir(d))
        except OSError:
            out[d] = []
    return out


def diff_dirs(before: dict[str, list[str]], after: dict[str, list[str]],
              *, top: int = EVIDENCE_CAPS["top"]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for d, aft in after.items():
        new = [n for n in aft if n not in set(before.get(d, []))]
        gone = [n for n in before.get(d, []) if n not in set(aft)]
        out[d] = {"entries_created": len(new), "entries_created_top": sorted(new)[:top],
                  "entries_removed": len(gone)}
    return out


# ----------------------------------------------------------------- process diffs

def snapshot_procs(*, bounds: dict[str, int] | None = None,
                   ps_argv: list[str] | None = None
                   ) -> tuple[dict[int, tuple[int, str]], str | None]:
    """``(table, error)`` where table is ``{pid: (ppid, args)}`` for every visible
    process, MINUS the ``ps`` that took the snapshot.

    Without that subtraction every phase reports exactly one phantom resident process
    — the after-snapshot's own ``ps``, which lists itself and has no counterpart in
    the before-snapshot. Measured and removed 2026-09-16, before the first banked row.

    The SECOND element is the point of the tuple: a failed ``ps`` used to return ``{}``,
    which the diff then rendered as "nothing left resident". A measurement that could
    not look must say so, and :func:`run_phase` banks it as ``procs_snapshot_error``.
    """
    bounds = bounds or DEFAULT_BOUNDS
    proc = None
    try:
        proc = subprocess.Popen(ps_argv or ["ps", "-eo", "pid=,ppid=,args="],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                text=True)
        stdout, _ = proc.communicate(timeout=bounds["ps"])
        own = proc.pid
        if proc.returncode != 0:
            return {}, f"ps rc={proc.returncode}"
    except subprocess.TimeoutExpired:
        if proc is not None:
            proc.kill()
            proc.communicate()
        return {}, f"TimeoutExpired after {bounds['ps']}s (derived from the banked bound)"
    except (OSError, subprocess.SubprocessError) as exc:
        return {}, f"{type(exc).__name__}: {exc}"
    out: dict[int, tuple[int, str]] = {}
    for line in stdout.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) < 3 or not parts[0].isdigit() or not parts[1].isdigit():
            continue
        pid = int(parts[0])
        if pid == own:
            continue
        out[pid] = (int(parts[1]), parts[2])
    return out, None


def _descends_from(pid: int, ancestor: int, table: dict[int, tuple[int, str]]) -> bool:
    seen: set[int] = set()
    cur = pid
    while cur in table and cur not in seen:
        seen.add(cur)
        ppid = table[cur][0]
        if ppid == ancestor:
            return True
        cur = ppid
    return False


def diff_procs(before: dict[int, tuple[int, str]], after: dict[int, tuple[int, str]],
               *, ancestor: int | None = None, top: int = EVIDENCE_CAPS["top"],
               argv_chars: int = EVIDENCE_CAPS["argv_chars"]) -> dict[str, Any]:
    """Processes resident after the phase that were not resident before.

    Both halves are columns: the full diff (which includes unrelated box activity and
    is therefore noisy but honest) and the subset whose ancestry reaches this probe
    (which is the phase's own leak).
    """
    new = [pid for pid in after if pid not in before]
    mine = [pid for pid in new if ancestor is not None
            and _descends_from(pid, ancestor, after)]
    return {
        "procs_left": len(new),
        "procs_left_top": [f"{pid} {after[pid][1][:argv_chars]}" for pid in sorted(new)[:top]],
        "procs_left_descendant": len(mine),
        "procs_left_descendant_top": [f"{pid} {after[pid][1][:argv_chars]}"
                                      for pid in sorted(mine)[:top]],
    }


# ------------------------------------------------------------------- git objects

def git_objects(repo: Path, env: dict[str, str] | None = None, *,
                bounds: dict[str, int] | None = None,
                argv: list[str] | None = None) -> tuple[dict[str, int], str | None]:
    """``(fields, error)`` — ``git count-objects -v`` as a dict of its integer fields
    (KiB for sizes), plus why it could not be taken.

    The error half exists because the old ``return {}`` made a failed count
    indistinguishable from an unchanged object store: :func:`diff_git` then banked
    every ``*_delta`` as 0. :func:`run_phase` banks it as ``git_objects_error``.
    """
    bounds = bounds or DEFAULT_BOUNDS
    try:
        p = subprocess.run(argv or ["git", "count-objects", "-v"], cwd=str(repo),
                           capture_output=True, text=True, timeout=bounds["git_objects"],
                           env=env or cold_env())
    except subprocess.TimeoutExpired:
        return {}, (f"TimeoutExpired after {bounds['git_objects']}s "
                    "(derived from the banked bound)")
    except (OSError, subprocess.SubprocessError) as exc:
        return {}, f"{type(exc).__name__}: {exc}"
    if p.returncode != 0:
        tail = p.stderr.strip()[-EVIDENCE_CAPS["tail_bytes"]:]
        return {}, f"git count-objects rc={p.returncode}: {tail}"
    out: dict[str, int] = {}
    for line in p.stdout.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            v = v.strip()
            if v.isdigit():
                out[k.strip().replace("-", "_")] = int(v)
    return out, None


def diff_git(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
    keys = set(before) | set(after)
    return {f"{k}_delta": after.get(k, 0) - before.get(k, 0) for k in sorted(keys)}


# ------------------------------------------------------------------------ phases

def _join_err(before: str | None, after: str | None) -> str | None:
    """One error column out of the before-snapshot and after-snapshot failures."""
    parts = [f"before: {before}" if before else "", f"after: {after}" if after else ""]
    joined = "; ".join(p for p in parts if p)
    return joined or None


def run_phase(name: str, argv: list[str], *, cwd: Path, env: dict[str, str],
              timeout: int, stdin: bytes | None = None,
              watch_dirs: list[str] | None = None,
              interpreter: str | None = None,
              bounds: dict[str, int] | None = None,
              caps: dict[str, int] | None = None) -> dict[str, Any]:
    """Run one phase between two full snapshots and return its measured row.

    ``bounds`` are the subsidiary subprocess bounds (:func:`derive_bounds`) and
    ``caps`` the evidence truncation caps (:data:`EVIDENCE_CAPS`); both are banked on
    the row by :func:`probe_run` so no number in this measurement is invisible.
    """
    watch_dirs = watch_dirs or []
    bounds = bounds or derive_bounds(timeout)
    caps = caps or EVIDENCE_CAPS
    top, tail_bytes = caps["top"], caps["tail_bytes"]
    tree_b = snapshot_tree(cwd)
    dirs_b = snapshot_dirs(watch_dirs)
    procs_b, procs_err_b = snapshot_procs(bounds=bounds)
    git_b, git_err_b = git_objects(cwd, env, bounds=bounds)

    t0 = time.monotonic()
    rc: int | None
    timed_out = False
    err: str | None = None
    out_b = err_b = 0
    try:
        p = subprocess.run(argv, cwd=str(cwd), env=env, input=stdin,
                           capture_output=True, text=False, timeout=timeout)
        rc = p.returncode
        out_b, err_b = len(p.stdout or b""), len(p.stderr or b"")
        tail = ((p.stderr or b"")[-tail_bytes:].decode("utf-8", "replace")
                if rc != 0 else None)
    except subprocess.TimeoutExpired as exc:
        rc, timed_out = None, True
        out_b = len(exc.stdout or b"")
        err_b = len(exc.stderr or b"")
        tail = f"TIMEOUT after {timeout}s (the probe's one banked bound)"
    except OSError as exc:
        rc, tail = None, f"{type(exc).__name__}: {exc}"
        err = tail
    wall = time.monotonic() - t0

    tree_a = snapshot_tree(cwd)
    work_b, gitd_b = _split_git(tree_b)
    work_a, gitd_a = _split_git(tree_a)
    gitd_b, idx_b = _split_index(gitd_b)
    gitd_a, idx_a = _split_index(gitd_a)
    work = diff_tree(work_b, work_a, top=top)
    gitd = diff_tree(gitd_b, gitd_a, top=top)
    idx = diff_tree(idx_b, idx_a, top=top)
    git_a, git_err_a = git_objects(cwd, env, bounds=bounds)
    gd = diff_git(git_b, git_a)
    procs_a, procs_err_a = snapshot_procs(bounds=bounds)
    procs = diff_procs(procs_b, procs_a, ancestor=os.getpid(), top=top,
                       argv_chars=caps["argv_chars"])
    tmp = diff_dirs(dirs_b, snapshot_dirs(watch_dirs), top=top)
    procs_err = _join_err(procs_err_b, procs_err_a)
    git_err = _join_err(git_err_b, git_err_a)
    return {
        "phase": name,
        "argv": argv,
        "interpreter": interpreter,
        "rc": rc,
        "timed_out": timed_out,
        "wall_s": round(wall, 4),
        "stdout_bytes": out_b,
        "stderr_bytes": err_b,
        "stdio_bytes": out_b + err_b,
        "error": err,
        "tail": tail,
        "clone_bytes_written": work["bytes_written"],
        "clone_files_created": work["files_created"],
        "clone_files_created_top": work["files_created_top"],
        "clone_files_modified": work["files_modified"],
        "clone_files_modified_top": work["files_modified_top"],
        "clone_files_deleted": work["files_deleted"],
        "clone_bytes_written_ex_cache": work["bytes_written_ex_cache"],
        "clone_files_created_ex_cache": work["files_created_ex_cache"],
        "clone_files_created_ex_cache_top": work["files_created_ex_cache_top"],
        "clone_files_modified_ex_cache": work["files_modified_ex_cache"],
        "clone_files_modified_ex_cache_top": work["files_modified_ex_cache_top"],
        "clone_git_bytes_written": gitd["bytes_written"],
        "clone_git_files_created": gitd["files_created"],
        "git_index_bytes_written": idx["bytes_written"],
        "git_index_files_created": idx["files_created"],
        "tmp": tmp,
        "procs": procs,
        # The leak columns the acceptance law is actually about, flattened onto the
        # phase so :data:`NUMERIC_COLUMNS` (and therefore ``spread``) can see them.
        "tmp_entries_created": sum(d.get("entries_created", 0) for d in tmp.values()),
        "procs_left": procs["procs_left"],
        "procs_left_descendant": procs["procs_left_descendant"],
        # A measurement that could not look is NEVER a zero: these say so.
        "procs_snapshot_error": procs_err,
        "git_objects_error": git_err,
        "git_count_objects_delta": {k: v for k, v in gd.items() if v},
        "git_size_kib_delta": gd.get("size_delta", 0),
        "git_size_pack_kib_delta": gd.get("size_pack_delta", 0),
    }


#: Numeric phase columns rolled into totals and (with ``--repeat``) into the spread.
#: The LEAK columns — tmp entries, processes left resident, files deleted, index churn
#: — belong here and not merely in ``totals``: they are what "accumulate nothing"
#: means, so a distribution that did not cover them covered everything except the
#: point.
NUMERIC_COLUMNS = ("wall_s", "stdout_bytes", "stderr_bytes", "stdio_bytes",
                   "clone_bytes_written", "clone_files_created", "clone_files_modified",
                   "clone_files_deleted",
                   "clone_bytes_written_ex_cache", "clone_files_created_ex_cache",
                   "clone_files_modified_ex_cache",
                   "clone_git_bytes_written", "clone_git_files_created",
                   "git_index_bytes_written", "git_index_files_created",
                   "git_size_kib_delta", "git_size_pack_kib_delta",
                   "tmp_entries_created", "procs_left", "procs_left_descendant")

#: Phase columns that name a FAILED measurement. Counted into totals so that "I could
#: not look" is visible at the top of a row instead of hiding behind a 0.
ERROR_COLUMNS = ("procs_snapshot_error", "git_objects_error")


def totals(phases: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {c: 0 for c in NUMERIC_COLUMNS}
    for ph in phases:
        for c in NUMERIC_COLUMNS:
            out[c] += ph.get(c) or 0
    out["wall_s"] = round(out["wall_s"], 4)
    out["phases_nonzero_rc"] = [ph["phase"] for ph in phases if ph.get("rc") != 0]
    for c in ERROR_COLUMNS:
        out[f"{c}s"] = [ph.get("phase") for ph in phases if ph.get(c)]
    out["measurement_errors"] = sum(len(out[f"{c}s"]) for c in ERROR_COLUMNS)
    return out


def spread(iterations: list[list[dict[str, Any]]]) -> dict[str, Any]:
    """Per-phase, per-column min/max/mean across the iterations of one probe run.

    Each iteration is its OWN cold clone (see :func:`probe_run`), so this is a
    cold-vs-cold repeatability distribution — the one seq 9 reads. The probe reports
    it; it never compares it to anything.
    """
    out: dict[str, Any] = {}
    names = [ph["phase"] for ph in iterations[0]]
    for i, name in enumerate(names):
        cols: dict[str, Any] = {}
        for c in NUMERIC_COLUMNS:
            vals = [(it[i].get(c) or 0) for it in iterations]
            cols[c] = {"min": min(vals), "max": max(vals),
                       "mean": round(sum(vals) / len(vals), 4), "n": len(vals)}
        out[name] = cols
    return out


# ------------------------------------------------------------------- the probe

def _git(args: list[str], cwd: Path | None = None, timeout: int | None = None,
         bounds: dict[str, int] | None = None) -> str:
    bounds = bounds or DEFAULT_BOUNDS
    p = subprocess.run(["git", *args], cwd=str(cwd) if cwd else None,
                       capture_output=True, text=True,
                       timeout=bounds["git_plumbing"] if timeout is None else timeout)
    return p.stdout.strip() if p.returncode == 0 else ""


def _watch_dirs() -> list[str]:
    cands = ["/tmp", os.environ.get("TMPDIR") or "", "/tmp/claude-1000"]
    seen, out = set(), []
    for c in cands:
        c = (c or "").rstrip("/") or c
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _one_iteration(clone: Path, env_base: dict[str, str], timeout: int,
                   watch: list[str], bounds: dict[str, int] | None = None,
                   caps: dict[str, int] | None = None) -> list[dict[str, Any]]:
    hook = clone / ".claude" / "hooks" / "session-start.mjs"
    common = {"timeout": timeout, "watch_dirs": watch, "bounds": bounds, "caps": caps}
    phases = [
        run_phase("session_start_hook", ["node", str(hook)], cwd=clone,
                  env=cold_env(extra={**env_base, "CLAUDE_PROJECT_DIR": str(clone)}),
                  stdin=b"{}", interpreter="node", **common),
        run_phase("wake_grade0", [SYSTEM_PYTHON, "scripts/wake.py", "--grade", "0"],
                  cwd=clone, env=cold_env(extra=env_base),
                  interpreter=SYSTEM_PYTHON, **common),
        run_phase("bounded_act_reconstruct_node",
                  [SYSTEM_PYTHON, "scripts/reconstruct_node.py", "src/laplace/engine/wake.py",
                   "--grade", "0"],
                  cwd=clone, env=cold_env(extra=env_base),
                  interpreter=SYSTEM_PYTHON, **common),
        run_phase("close_dry_run", [SYSTEM_PYTHON, *CLOSE_ARGV], cwd=clone,
                  env=cold_env(extra=env_base), interpreter=SYSTEM_PYTHON, **common),
    ]
    phases[-1]["note"] = CLOSE_NOTE
    return phases


def _cold_clone(repo: Path, dest: Path, *, timeout: int,
                bounds: dict[str, int], caps: dict[str, int]) -> dict[str, Any]:
    """One disposable ``git clone --local --no-hardlinks`` with ``origin`` removed.

    Every column it returns is banked per iteration: the clone's wall time and rc, the
    rc of the remote removal, and whether ``origin`` is actually gone — checked, never
    assumed. A clone whose origin survived is a clone that can reach the real tree,
    and the row must say so.
    """
    t0 = time.monotonic()
    cp = subprocess.run(["git", "clone", "--local", "--no-hardlinks",
                         str(repo), str(dest)],
                        capture_output=True, text=True, timeout=timeout)
    info: dict[str, Any] = {"clone": str(dest),
                            "clone_wall_s": round(time.monotonic() - t0, 4),
                            "clone_rc": cp.returncode,
                            "origin_removed": False,
                            "origin_remove_rc": None,
                            "remotes_after": None}
    if cp.returncode != 0:
        info["error"] = f"clone failed: {cp.stderr[-caps['tail_bytes']:]}"
        return info
    rp = subprocess.run(["git", "remote", "remove", "origin"], cwd=str(dest),
                        capture_output=True, text=True, timeout=bounds["git_remote"])
    info["origin_remove_rc"] = rp.returncode
    remotes = [ln.strip() for ln in
               _git(["remote"], dest, bounds=bounds).splitlines() if ln.strip()]
    info["remotes_after"] = remotes
    info["origin_removed"] = (rp.returncode == 0 and "origin" not in remotes)
    if not info["origin_removed"]:
        info["origin_remove_tail"] = rp.stderr.strip()[-caps["tail_bytes"]:]
    info["clone_head"] = _git(["rev-parse", "HEAD"], dest, bounds=bounds)
    return info


def probe_run(repo: Path | str = ".", *, tag: str | None = None, repeat: int = 1,
              timeout: int = DEFAULT_TIMEOUT_S,
              scratch_root: Path | str | None = None) -> dict[str, Any]:
    """Clone cold N times, measure every phase in each, and return ONE row. Removes
    its scratch tree.

    EACH ITERATION GETS ITS OWN CLONE, in its own scratch subdirectory: a
    ``git clone --local --no-hardlinks`` whose ``origin`` remote is removed (and the
    removal CHECKED) before any phase runs, so nothing a phase does can reach the
    source tree. That per-iteration clone is what makes ``spread`` a cold-vs-cold
    repeatability distribution; replaying the phases inside one clone would measure a
    warm tree on every iteration after the first and must not be called a spread.
    """
    repo = Path(repo).resolve()
    bounds = derive_bounds(timeout)
    caps = dict(EVIDENCE_CAPS)
    stdin_stamp = time.time()
    head = _git(["rev-parse", "HEAD"], repo, bounds=bounds)
    porcelain = _git(["status", "--porcelain"], repo, bounds=bounds)
    dirty = [ln for ln in porcelain.splitlines() if ln.strip()]
    watch = _watch_dirs()
    scratch = Path(tempfile.mkdtemp(prefix="laplace-probe-",
                                    dir=str(scratch_root) if scratch_root else None))
    row: dict[str, Any] = {
        "schema_version": SCHEMA,
        "record": "probe_run",
        "id": f"probe-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime(stdin_stamp))}-{uuid.uuid4().hex[:8]}",
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(stdin_stamp)),
        "tag": tag,
        "repo": str(repo),
        "head": head,
        "head_short": head[:12],
        "source_dirty": bool(dirty),
        "source_dirty_count": len(dirty),
        "scratch_root": str(scratch.parent),
        "scratch": str(scratch),
        "origin_removed": False,
        "subprocess_timeout_s": timeout,
        "bounds": bounds,
        "bound_fractions": dict(BOUND_FRACTIONS),
        "evidence_caps": caps,
        "repeat": repeat,
        "clone_per_iteration": True,
        "spread_temperature": "cold-cold",
        "watch_dirs": watch,
        "probe_interpreter": {"sys_executable": sys.executable,
                              "version": sys.version.split()[0],
                              "platform": sys.platform},
        "declared_interpreter": SYSTEM_PYTHON,
        "cold_path": MINIMAL_PATH,
        "host": {"nproc": os.cpu_count(),
                 "loadavg": list(os.getloadavg()),
                 "tmpdir_env": os.environ.get("TMPDIR")},
        "close_invocation": CLOSE_ARGV,
        "close_note": CLOSE_NOTE,
    }
    base_env: dict[str, str] = {}
    try:
        cenv = cold_env(extra=base_env)
        row["which_python3_cold"] = which_all("python3", cenv)
        row["which_python3_login"] = which_all_login("python3", bounds=bounds)
        row["which_node_cold"] = which_all("node", cenv)
        row["one_interpreter"] = (row["which_python3_cold"] == row["which_python3_login"])

        n = max(1, repeat)
        iterations: list[list[dict[str, Any]]] = []
        clones: list[dict[str, Any]] = []
        for i in range(n):
            clone = scratch / f"iter-{i}" / "clone"
            clone.parent.mkdir(parents=True, exist_ok=True)
            info = _cold_clone(repo, clone, timeout=timeout, bounds=bounds, caps=caps)
            info["iteration"] = i
            clones.append(info)
            if info["clone_rc"] != 0:
                row["clones"] = clones
                row["clone_wall_s"] = clones[0]["clone_wall_s"]
                row["clone_rc"] = info["clone_rc"]
                row["error"] = info.get("error")
                row["phases"], row["totals"] = [], {}
                return row
            iterations.append(_one_iteration(clone, base_env, timeout, watch,
                                             bounds=bounds, caps=caps))

        row["clones"] = clones
        row["clone_wall_s"] = clones[0]["clone_wall_s"]
        row["clone_wall_s_per_iteration"] = [c["clone_wall_s"] for c in clones]
        row["clone_rc"] = clones[0]["clone_rc"]
        row["clone_head"] = clones[0]["clone_head"]
        # Truthful, not assumed: every clone's origin removal was checked.
        row["origin_removed"] = all(c["origin_removed"] for c in clones)
        row["origin_remove_rc"] = [c["origin_remove_rc"] for c in clones]

        row["phases"] = iterations[0]
        row["totals"] = totals(iterations[0])
        row["spread"] = spread(iterations) if len(iterations) > 1 else None
        if len(iterations) > 1:
            row["totals_per_iteration"] = [totals(it) for it in iterations]
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        row["scratch_removed"] = not Path(scratch).exists()
    return row


# ------------------------------------------------------------------------ banking

def bank(row: dict[str, Any], *, root: Path | str | None = None,
         store: str = STORE) -> str:
    """Append the row through the house seam (:func:`laplace.core.records.journal.bank_row`),
    falling back to a durable plain append of the SAME shape if that seam cannot
    load under this interpreter. Returns which path was taken.

    The path is STAMPED ON THE ROW BEFORE it is serialized (``banked_via``). Stamping
    it afterwards — which is what the CLI used to do — left the store unable to say
    which durability path an append took, and the two paths are a materially
    different story.
    """
    r = Path(root or ".").resolve()
    try:
        from laplace.core.records.journal import bank_row  # local: the probe must run seam-less too
        row["banked_via"] = "journal.bank_row"
        bank_row(store, row, root=r)
        return "journal.bank_row"
    except Exception:  # noqa: BLE001 - the probe records; it never refuses to record
        row["banked_via"] = "plain_append"
        target = r / store
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        return "plain_append"


def read_rows(root: Path | str = ".", store: str = STORE) -> list[dict[str, Any]]:
    p = Path(root) / store
    if not p.exists():
        return []
    rows = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln:
            try:
                rows.append(json.loads(ln))
            except json.JSONDecodeError:
                continue
    return rows


#: Stores scanned for references to a probe row id. Content, not a count.
REFERENCE_SCAN = ("contract", "corpus_friction", "holdout", "evidence")

#: NOT evidence of a reader. The probe store is itself, and ``journal.jsonl`` is the
#: write-trace of the very append that created the row — counting either would make
#: every row permanently referenced and retention a no-op, which is how a store
#: reaches 60,101,446 B with zero readers.
REFERENCE_EXCLUDE = {"contract/journal.jsonl"}


def referenced_ids(root: Path | str, ids: set[str], store: str = STORE) -> set[str]:
    """Which of ``ids`` some OTHER store mentions. Retention is content-keyed: a row
    another store points at is never dropped, however old it is.
    """
    root = Path(root)
    found: set[str] = set()
    for d in REFERENCE_SCAN:
        base = root / d
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file() or p.suffix not in {".json", ".jsonl", ".md", ".txt", ".yaml"}:
                continue
            if os.path.relpath(p, root) in ({store} | REFERENCE_EXCLUDE):
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for i in ids - found:
                if i in text:
                    found.add(i)
    return found


def prune(root: Path | str = ".", *, store: str = STORE,
          apply: bool = False) -> dict[str, Any]:
    """CONTENT-KEYED retention — never a numeric cap.

    KEEP: the latest row per ``(head, tag, interpreter)`` key (ties, which the one
    stamp law makes common, break toward the later line in the file), plus every row
    whose ``id`` is referenced from another store. DROP: everything else. The key is the
    identity of the measurement; a second row under the same key is the same
    measurement repeated, and the newest one is the one that describes today's tree.
    """
    root = Path(root).resolve()
    rows = read_rows(root, store)
    keep_by_key: dict[tuple, dict[str, Any]] = {}
    for r in rows:
        key = (r.get("head"), r.get("tag"),
               (r.get("probe_interpreter") or {}).get("sys_executable"))
        prev = keep_by_key.get(key)
        if prev is None or str(r.get("ts", "")) >= str(prev.get("ts", "")):
            keep_by_key[key] = r
    keep_ids = {r.get("id") for r in keep_by_key.values()}
    all_ids = {r.get("id") for r in rows if r.get("id")}
    refs = referenced_ids(root, all_ids - keep_ids, store)
    keep_ids |= refs
    kept = [r for r in rows if r.get("id") in keep_ids]
    dropped = [r.get("id") for r in rows if r.get("id") not in keep_ids]
    if apply and dropped:
        target = root / store
        tmp = target.with_suffix(target.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            for r in kept:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        tmp.replace(target)
    return {"rows": len(rows), "kept": len(kept), "dropped": len(dropped),
            "dropped_ids": dropped, "kept_by_reference": sorted(refs), "applied": apply}


def summarize(row: dict[str, Any]) -> str:
    """One compact human line per phase plus totals. No verdict — there is none."""
    lines = [f"probe {row.get('id')} tag={row.get('tag')} head={row.get('head_short')} "
             f"dirty={row.get('source_dirty')} timeout={row.get('subprocess_timeout_s')}s"]
    lines.append(f"  interpreter cold={row.get('which_python3_cold')} "
                 f"login={row.get('which_python3_login')} one={row.get('one_interpreter')}")
    lines.append(f"  bounds={row.get('bounds')} caps={row.get('evidence_caps')} "
                 f"clones={row.get('repeat')} temperature={row.get('spread_temperature')} "
                 f"origin_removed={row.get('origin_removed')}")
    for ph in row.get("phases", []):
        tmpn = ph.get("tmp_entries_created",
                      sum(d.get("entries_created", 0) for d in ph["tmp"].values()))
        for col in ERROR_COLUMNS:
            if ph.get(col):
                lines.append(f"  !! {ph['phase']} {col}: {ph[col]}")
        lines.append(
            f"  {ph['phase']:<28} rc={ph['rc']!s:<5} {ph['wall_s']:>8.2f}s "
            f"out={ph['stdio_bytes']:>8}B wrote={ph['clone_bytes_written']:>9}B "
            f"(ex-cache {ph['clone_bytes_written_ex_cache']:>8}B/"
            f"{ph['clone_files_created_ex_cache']:>3}f) "
            f"new={ph['clone_files_created']:>4} git={ph['clone_git_bytes_written']:>9}B "
            f"pack={ph['git_size_pack_kib_delta']:>6}KiB tmp={tmpn:>3} "
            f"proc={ph['procs']['procs_left_descendant']}/{ph['procs']['procs_left']}")
    t = row.get("totals") or {}
    if t:
        lines.append(f"  TOTAL wall={t.get('wall_s')}s wrote={t.get('clone_bytes_written')}B "
                     f"ex-cache={t.get('clone_bytes_written_ex_cache')}B/"
                     f"{t.get('clone_files_created_ex_cache')}f "
                     f"git={t.get('clone_git_bytes_written')}B tmp={t.get('tmp_entries_created')} "
                     f"procs={t.get('procs_left_descendant')}/{t.get('procs_left')} "
                     f"index={t.get('git_index_bytes_written')}B "
                     f"nonzero_rc={t.get('phases_nonzero_rc')} "
                     f"measurement_errors={t.get('measurement_errors')}")
    return "\n".join(lines)
