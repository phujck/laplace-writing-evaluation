"""tests_at_grade.py - run the test shard for what changed, not the whole suite.

The conjugate of verify-at-grade (``check_canon(focus=...)``) applied to the pytest suite: the
at-grade probe's DIRTY branch. ``git`` tells us what moved; we map each changed source module to
the tests that exercise it - its own ``test_<mod>.py`` *plus any test that imports it* (the
cross-cutting ripple, detected live so there is no stale map to rot) - and run only that shard.

A clean tree maps to an EMPTY shard: nothing moved, so nothing is re-derived (inherit the last
banked-green verdict - the conjugate of the close skipping re-verify when nothing was touched).
A changed source that maps to NO test is surfaced as an untested-change warning, never silently
passed (a silent gap reads as "covered" when it isn't).

A git that does not answer is not a clean tree. The inherit is licensed by "the absence of
change IS the verification", so it needs the absence to have actually been established; when
the git read fails there is no such fact, only an unread tree. That case is carried separately
(``git_unreadable``) and never inherits - ``--run`` says so and exits non-zero rather than
printing the banked-green line over an unverified working tree.

Build-ahead is the disease (F19); this is pulled by the first dirty localised change (N20).
"""

from __future__ import annotations
from laplace.core.checkout import source_tree

import re
import subprocess
from pathlib import Path

_SRC_RE = re.compile(r"^src/laplace/((?:\w+/)*\w+)\.py$")
_SCRIPT_RE = re.compile(r"^scripts/(\w+)\.py$")
_TEST_RE = re.compile(r"^tests/test_\w+\.py$")


def _git_changed(repo_root: Path) -> tuple[list[str] | None, str]:
    """Every path that differs from HEAD - staged, unstaged, and untracked (porcelain).

    Returns ``(paths, "")`` when git answered, and ``(None, reason)`` when it did not - a
    failed spawn, a timeout, or a non-zero rc. "git did not answer" is a different fact from
    "nothing changed", and returning ``[]`` for both is what let a dead git CLI (dubious
    ownership in a container, a lost PATH, a held index.lock) report as a clean tree and
    inherit a green nobody had earned. The reason is the caller's evidence, so it carries
    git's own stderr where there is one.

    ``-uall`` is load-bearing: bare porcelain COLLAPSES a wholly-untracked directory to a
    single ``dir/`` entry, so every module of a brand-new subpackage matched no source
    pattern and was neither sharded nor surfaced as an untested change - the silent gap
    this module exists to prevent, and worst exactly when the code is newest. It also makes
    this read agree with ``close_beats._dirty_paths``, which already passes the flag and
    documents itself as mirroring this one.
    """
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain", "-uall", "-z"], cwd=repo_root,
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as e:
        return None, f"git status did not run: {e!r}"
    if out.returncode != 0:
        detail = (out.stderr or out.stdout or "").strip().splitlines()
        return None, f"git status exited {out.returncode}: {detail[0] if detail else '(no output)'}"
    paths: list[str] = []
    for rec in out.stdout.split("\0"):
        if len(rec) > 3:
            # porcelain: 'XY <path>' (or 'XY <old> -> <new>' for renames)
            path = rec[3:]
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            paths.append(path.replace("\\", "/"))
    return paths, ""


def _tests_importing(repo_root: Path, module: str) -> list[str]:
    """Test files that import ``laplace.<module>`` - the cross-cutting ripple, detected live.
    ``module`` is the full dotted tail (``widget``, or ``pipeline.growth_adjudicator`` for a
    subpackage module), so the needle reaches subpackage imports the same way as flat ones.

    The third needle covers the FROM-PACKAGE form ``from laplace.pipeline import demand``,
    which names the module without ever spelling ``laplace.pipeline.demand``. Both dotted
    needles miss it, and it is the majority import style for subpackage organs: 19 modules
    across the subpackages reported a false untested-change gap while a test imported them
    all along. A gap that reads as "no test exists" when one does is the same silent pass
    the module forbids, one level down.
    """
    tests_dir = repo_root / "tests"
    if not tests_dir.is_dir():
        return []
    needle_a = f"laplace.{module}"
    needle_b = f"import {module}"
    parent, _, last = module.rpartition(".")
    # the import list is either parenthesised (possibly multi-line) or runs to end of line.
    from_pkg = re.compile(
        rf"from\s+laplace\.{re.escape(parent)}\s+import\s+(?:\(([^)]*)\)|([^\n]*))"
    ) if parent else None
    hits: list[str] = []
    for p in sorted(tests_dir.glob("test_*.py")):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if needle_a in text or re.search(rf"\b{re.escape(needle_b)}\b", text):
            hits.append(f"tests/{p.name}")
        elif from_pkg is not None and any(
            re.search(rf"\b{re.escape(last)}\b", m.group(1) or m.group(2) or "")
            for m in from_pkg.finditer(text)
        ):
            hits.append(f"tests/{p.name}")
    return hits


def _tests_importing_script(repo_root: Path, name: str) -> list[str]:
    """Test files that load ``scripts/<name>.py`` via the ``spec_from_file_location`` loader
    idiom (see tests/test_deslop_gate.py) - the cross-cutting ripple for scripts, where there is
    no ``import`` statement to search for, only the loaded path's filename."""
    tests_dir = repo_root / "tests"
    if not tests_dir.is_dir():
        return []
    needle = f"{name}.py"
    hits: list[str] = []
    for p in sorted(tests_dir.glob("test_*.py")):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if needle in text:
            hits.append(f"tests/{p.name}")
    return hits


def test_shard(repo_root: Path | str, changed: list[str] | None = None) -> dict[str, object]:
    """Resolve the test shard for the changed set. Returns the tests to run, plus any changed
    source modules that resolved to no test (the untested-change warning).

    Resolution is PER PATH, never by growth of the shared shard: two changed modules covered
    by the same test file make the second one add nothing to the set, and reading that as
    "resolved to no test" reported a covered module as an untested gap. The gap list is only
    trustworthy if it means what it says, so each path is judged on its own hits.

    ``git_unreadable`` is non-empty only when the changed set had to be read from git and git
    did not answer; an explicit ``changed`` never consults git, so it never sets it. It blocks
    ``inherit`` on its own: an empty changed-set means "inherit the green" only when the tree
    was actually read and found clean.
    """
    repo_root = Path(repo_root)
    git_unreadable = ""
    if changed is None:
        found, git_unreadable = _git_changed(repo_root)
        changed = found if found is not None else []
    else:
        changed = [c.replace("\\", "/") for c in changed]

    shard: set[str] = set()
    untested: list[str] = []
    for rel in changed:
        if _TEST_RE.match(rel):
            if (repo_root / rel).exists():
                shard.add(rel)
            continue
        m = _SRC_RE.match(rel)
        if m:
            # dotted tail (widget, or pipeline.growth_adjudicator for a subpackage module);
            # own-test resolution is by the LAST segment, the importer needle is the full tail.
            dotted = m.group(1).replace("/", ".")
            last = dotted.rsplit(".", 1)[-1]
            hits = list(_tests_importing(repo_root, dotted))
            own = f"tests/test_{last}.py"
            if (repo_root / own).exists():
                hits.append(own)
            shard.update(hits)
            if not hits:
                untested.append(rel)
            continue
        m = _SCRIPT_RE.match(rel)
        if m:
            name = m.group(1)
            hits = list(_tests_importing_script(repo_root, name))
            own = f"tests/test_{name}.py"
            if (repo_root / own).exists():
                hits.append(own)
            shard.update(hits)
            if not hits:
                untested.append(rel)
            continue
        # docs / config / data - no test impact by convention

    return {
        "changed": changed,
        "shard": sorted(shard),
        "untested_changes": untested,
        # clean tree -> inherit last-green, run nothing; but only a tree we could READ
        "inherit": not changed and not git_unreadable,
        "git_unreadable": git_unreadable,
        "note": "the at-grade test shard: run only what the change touches. Empty changed -> "
                "inherit the banked-green verdict. untested_changes is a gap to close, not a pass. "
                "git_unreadable non-empty -> the tree was never read, so nothing is inherited.",
    }


def default_repo_root() -> Path:
    return source_tree()


def main(argv: list[str]) -> int:
    import json
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

    repo_root = default_repo_root()
    rep = test_shard(repo_root)

    if "--run" in argv:
        if rep["git_unreadable"]:
            # rc 2, distinct from the rc 1 of a real failure: the shard did not fail, it
            # never ran, and a caller reading the exit code must be able to tell.
            print(f"git unreadable - cannot inherit the banked green: {rep['git_unreadable']}")
            print("nothing was verified; re-run once git answers, or run the suite flat.")
            return 2
        if rep["inherit"]:
            print("clean tree - inheriting the last banked-green verdict (no tests run).")
            return 0
        if not rep["shard"]:
            print("changed, but no test shard resolved:", rep["untested_changes"])
            return 1 if rep["untested_changes"] else 0
        print(f"running {len(rep['shard'])} test file(s) at grade: {rep['shard']}")
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", *rep["shard"]], cwd=repo_root,
        )
        return proc.returncode

    print(json.dumps(rep, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main(sys.argv[1:]))
