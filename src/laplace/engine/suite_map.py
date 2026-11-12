"""The suite-level conjugate of inherit-on-clean — test what moved, inherit the rest.

His ask, verbatim (2026-08-20, WO-20260820-test-what-moved): *"the test suite - 4800
seconds or whatever it was is truly unsustainable. Surely that can be made more
efficient. Again, why test what hasn't moved?"*

The wake already refuses this class of re-derivation at session grade — *clean tree ⇒
inherit the banked green; on contradiction verify SCOPED, the changed test shard, not
`pytest -q`* (EIGEN_PROTOCOL Part A, `process_health.probe`). This module is the same law at
**shard grade**, for the close's in-close suite step: the close runs only the test files
whose sources moved since the last banked green and inherits green for the rest.

**The two edge types.** A test file reaches a repo path two ways, and both are derived
mechanically — never hand-listed:

1. **import edges** — static AST import resolution, transitively closed over first-party
   files (``src/`` for laplace and atlas, ``scripts/``, ``tests/`` helpers). A test that
   imports ``laplace.sewup`` depends on everything ``laplace.sewup`` imports.
2. **path literals** — every string constant, in the test *and in its transitive source
   closure*, that names a repo path, directory, or glob. This is the edge that catches
   what imports cannot see: a test that reads ``corpus_friction/work_orders.jsonl``, a
   test that subprocess-runs ``scripts/reembed.py``, a canon check that walks ``*.md``.
   A moved data file is matched against these literals, so the repo-scanning tests fire
   on any moved document and the other 290 test files do not.

**Fail-open is the floor, never silence.** A moved path that matches neither edge type is
*unclassified*, and an unclassified path forces the FULL suite. So does anything in the
always-full set (any ``conftest.py``, the test fixtures, the pytest config, and this
module and its own driver — the selector may never exempt itself from proving itself).
Under-selection is the only failure mode that matters here; every uncertainty resolves
toward running more, and the reason is printed rather than swallowed.

**The induction.** A green run banks ``head`` into ``corpus_friction/suite_runs.jsonl``.
The next run's delta is measured from there, so an unbroken chain of impacted-greens
carries the same warrant as one full green *given selector soundness* — which is exactly
why ``chain_depth`` rides every row: the depth of induction is a measured number, and a
jubilee (``--full``) resets it to zero on demand.
"""

from __future__ import annotations

import ast
import fnmatch
import hashlib
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

#: The banked map. A derived artifact — delete it and the next call rebuilds it.
MAP_REL = "corpus_friction/suite_map.json"
#: The per-run instrument. Append-only typed rows: mode, wall time, shard count, verdict.
RUNS_REL = "corpus_friction/suite_runs.jsonl"

#: v2 banks the GRAPH (direct edges + own literals), not the closure. v1 banked the
#: transitive closure per test and measured 9.3 MB with a median 138 sources / 1109
#: literals per test — saturated, because this codebase's import graph genuinely is
#: (analytics → shared_ui → ladder → altitude is a real four-hop chain, not an artifact).
#: The closure is the same either way; deriving it at selection time costs milliseconds
#: and keeps the banked artifact small enough to read.
#: v3 splits import edges into hard (module scope) and lazy (function-local) and bounds
#: how many lazy edges one dependency path may cross — see :func:`_tests_reaching` for the
#: measurement that set the bound.
SCHEMA_VERSION = 3

#: How many function-local imports one dependency path may cross. 0 = module-level only
#: (fastest, under-selects conditional paths); 1 = the default; a large number = the
#: saturated graph, which is sound and useless. Override per call in `_tests_reaching`.
LAZY_HOPS = 1

#: Above this share of the suite, an "impacted" run is the full walk with the paperwork of
#: a partial one — and a partial run is forbidden from reporting a banked red as cleared.
#: MEASURED over the last 16 real commits: selections land between 37% and 77% of the test
#: files, so the tail of that distribution is worth promoting to an honest jubilee.
FULL_THRESHOLD = 0.75

#: The jubilee cadence: after this many consecutive impacted-greens, the close runs the
#: FULL suite whether or not anything unclassified moved. The selector's soundness rests
#: on a static approximation; this bounds how long any single under-selection can hide.
JUBILEE_EVERY = 8

#: Where first-party code lives. (dotted-root, path-root, is_package_root)
_PKG_ROOTS = (("src", True), ("scripts", False), ("tests", False))   # src holds laplace and atlas (R2)
#: Directories the map walks for test files.
_TEST_ROOTS = ("tests", "atlas/tests")

#: Moved paths that force the full suite outright. Globs, repo-relative posix.
#: `conftest.py` and the fixture tree change collection itself; the pytest config changes
#: what is collected at all; the selector's own machinery must never select itself out of
#: the run that would catch its bugs.
ALWAYS_FULL = (
    "**/conftest.py",
    "conftest.py",
    "tests/fixtures/**",
    "atlas/tests/fixtures/**",
    "pyproject.toml",
    "pytest.ini",
    "setup.cfg",
    "tox.ini",
    "src/laplace/engine/suite_map.py",
    "scripts/suite_select.py",
    "tests/test_suite_map.py",
)

#: A string constant is a candidate path literal when it looks like one. Whitespace and
#: over-long strings are prose, not paths.
_MAX_LITERAL = 160


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# the walk


def _iter_py(root: Path, rel: str):
    base = root / rel
    if not base.is_dir():
        return
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames
                       if d not in {"__pycache__", ".git", ".venv", "node_modules"}]
        for fn in filenames:
            if fn.endswith(".py"):
                yield Path(dirpath) / fn


def _relposix(root: Path, p: Path) -> str:
    return p.resolve().relative_to(root.resolve()).as_posix()


def fingerprint(root: Path) -> str:
    """A cheap identity for the code the map was built from.

    (relpath, size, mtime_ns) over every first-party ``.py``. Rebuild is ~1s, so the
    fingerprint exists to make *not* rebuilding safe, not to avoid an expensive job.
    """
    h = hashlib.sha256()
    seen: list[str] = []
    for rel, _ in _PKG_ROOTS:
        for p in _iter_py(root, rel):
            seen.append(_relposix(root, p))
    for rel in _TEST_ROOTS:
        for p in _iter_py(root, rel):
            seen.append(_relposix(root, p))
    for r in sorted(set(seen)):
        st = (root / r).stat()
        h.update(f"{r}\0{st.st_size}\0{st.st_mtime_ns}\n".encode())
    return "sha256:" + h.hexdigest()[:32]


def _module_index(root: Path) -> dict[str, str]:
    """dotted module name -> repo-relative file. First root wins on collision."""
    index: dict[str, str] = {}
    for rel, is_pkg_root in _PKG_ROOTS:
        base = root / rel
        if not base.is_dir():
            continue
        for p in _iter_py(root, rel):
            r = _relposix(root, p)
            parts = Path(r[len(rel) + 1:]).with_suffix("").parts if is_pkg_root else None
            if is_pkg_root:
                if parts and parts[-1] == "__init__":
                    parts = parts[:-1]
                if not parts:
                    continue
                dotted = ".".join(parts)
            else:
                # scripts/ and tests/ are not packages: tests reach them by bare stem
                # (sys.path insert) and, for tests/, by the `tests.` dotted form too.
                dotted = Path(r).stem
                index.setdefault(rel.replace("/", ".") + "." + Path(r[len(rel) + 1:])
                                 .with_suffix("").as_posix().replace("/", "."), r)
            index.setdefault(dotted, r)
    return index


#: Characters that mean the string is a regex, a URL, or an absolute/foreign path — never
#: a repo-relative one. (A regex literal reached the filesystem before this filter existed:
#: `'/root/\\.ccr/[^\\s`\'\\")]+'` was stat'ed and raised PermissionError.)
_NOT_A_REPO_PATH = ("\\", "[", "]", "(", ")", "{", "}", "|", "^", "$", "+", "%", "<", ">",
                    "`", '"', "'", "\x00")


def _looks_like_path(s: str, top_dirs: set[str]) -> bool:
    if not s or len(s) > _MAX_LITERAL or any(c.isspace() for c in s):
        return False
    if "://" in s or s.startswith("/") or s.startswith("~") or s.startswith("-"):
        return False
    if any(c in s for c in _NOT_A_REPO_PATH):
        return False
    if "*" in s or "?" in s:
        # An information-free glob ('*', '**', '**/*', '*.*') is applied to whatever
        # directory the caller computed at runtime; it names no path, so matching every
        # moved path against it is noise, not conservatism. MEASURED: keeping them put
        # ~250 of 311 test files in every selection, including for a path no test knows.
        return any(len(seg.replace("*", "").replace("?", "")) >= 2
                   for seg in s.split("/"))
    if "/" in s:
        return True
    stem, dot, ext = s.rpartition(".")
    if dot and stem and 1 <= len(ext) <= 6 and ext.isalnum() and not ext.isdigit():
        return True
    return s in top_dirs


def _parse(path: Path) -> ast.AST | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8", errors="replace"), str(path))
    except (OSError, SyntaxError):
        return None


def _imports_and_literals(tree: ast.AST, rel: str, top_dirs: set[str]
                          ) -> tuple[list[tuple[str, str | None]],
                                     list[tuple[str, str | None]], set[str]]:
    """(hard imports, lazy imports, path-looking string constants).

    **hard** = module scope: executed the moment the module is imported, so the
    dependency is unconditional. **lazy** = inside a function or method body: executed
    only on the code path that calls it — the house's own deliberate style (the bloat
    ruling's "imports go lazy"), and the reason the naive graph saturates.
    """
    scoped: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for sub in ast.walk(node):
                if isinstance(sub, (ast.Import, ast.ImportFrom)):
                    scoped.add(id(sub))
    hard: list[tuple[str, str | None]] = []
    lazy: list[tuple[str, str | None]] = []
    lits: set[str] = set()
    pkg_parts = Path(rel).parent.as_posix().split("/")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            bucket = lazy if id(node) in scoped else hard
            if isinstance(node, ast.Import):
                for a in node.names:
                    bucket.append((a.name, None))
            else:
                mod = node.module or ""
                if node.level:
                    # relative import: climb the package path of the importing file
                    base = pkg_parts[:len(pkg_parts) - (node.level - 1)] if node.level > 1 \
                        else pkg_parts
                    mod = ".".join([p for p in base if p] + ([mod] if mod else []))
                for a in node.names:
                    bucket.append((mod, a.name))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if _looks_like_path(node.value, top_dirs):
                lits.add(node.value)
    return hard, lazy, lits


def _resolve(dotted: str, name: str | None, index: dict[str, str]) -> list[str]:
    """A dotted import -> the first-party files it can name (0, 1, or 2)."""
    hits: list[str] = []
    cands = [dotted] if dotted else []
    if dotted and name:
        cands.insert(0, f"{dotted}.{name}")  # `from pkg import submodule`
    for c in cands:
        parts = c.split(".")
        while parts:
            key = ".".join(parts)
            if key in index:
                hits.append(index[key])
                break
            parts.pop()
    return hits


def build_map(root: str | Path) -> dict:
    """Derive the import graph + per-file path literals. Pure static analysis.

    Banks the GRAPH: for each first-party file, its *direct* first-party imports and its
    *own* path literals. The test → source closure is the reverse reachability of that
    graph, computed in :func:`select`.
    """
    root = Path(root).resolve()
    t0 = time.perf_counter()
    top_dirs = {p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")}
    index = _module_index(root)

    all_files: set[str] = set(index.values())
    for rel in _TEST_ROOTS:
        for p in _iter_py(root, rel):
            all_files.add(_relposix(root, p))

    files: dict[str, dict] = {}
    n_hard = n_lazy = 0
    lit_names: set[str] = set()
    for r in sorted(all_files):
        tree = _parse(root / r)
        if tree is None:
            files[r] = {"imp": [], "lazy": [], "lit": []}
            continue
        himps, limps, lits = _imports_and_literals(tree, r, top_dirs)

        def _deps(pairs) -> set[str]:
            out: set[str] = set()
            for mod, nm in pairs:
                for hit in _resolve(mod, nm, index):
                    if hit != r:  # noqa: B023 - r is the loop's current file, by design
                        out.add(hit)
            return out

        hard = _deps(himps)
        lazy = _deps(limps) - hard  # a hard edge subsumes a lazy one to the same file
        files[r] = {"imp": sorted(hard), "lazy": sorted(lazy), "lit": sorted(lits)}
        n_hard += len(hard)
        n_lazy += len(lazy)
        lit_names |= lits

    tests = sorted(f for f in all_files
                   if Path(f).name.startswith("test_")
                   and Path(f).parts[0] in {"tests", "atlas"})

    return {
        "kind": "suite-shard-map",
        "record": "suite_map",
        "version": SCHEMA_VERSION,
        "built_at": _now(),
        "build_s": round(time.perf_counter() - t0, 3),
        "fingerprint": fingerprint(root),
        "always_full": list(ALWAYS_FULL),
        "lazy_hops": LAZY_HOPS,
        "counts": {"tests": len(tests), "first_party_files": len(files),
                   "hard_edges": n_hard, "lazy_edges": n_lazy, "literals": len(lit_names)},
        "tests": tests,
        "files": files,
    }


def load_map(root: str | Path, *, rebuild: bool = False) -> tuple[dict, str]:
    """(map, why) — the banked map, rebuilt when stale, missing, or forced."""
    root = Path(root).resolve()
    path = root / MAP_REL
    if not rebuild and path.is_file():
        try:
            m = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            m = None
        if m and m.get("version") == SCHEMA_VERSION:
            if m.get("fingerprint") == fingerprint(root):
                return m, "banked (fingerprint matches)"
            why = "rebuilt (fingerprint moved)"
        else:
            why = "rebuilt (missing or wrong schema version)"
    else:
        why = "rebuilt (forced)" if rebuild else "rebuilt (no banked map)"
    m = build_map(root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(m, indent=1, sort_keys=False) + "\n", encoding="utf-8")
    except OSError:
        pass
    return m, why


# ---------------------------------------------------------------------------
# the moved set


def _git(root: Path, *args: str) -> tuple[str | None, str]:
    try:
        r = subprocess.run(["git", *args], cwd=str(root), capture_output=True, text=True,
                           timeout=30, encoding="utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001 - named, never swallowed
        return None, f"git {' '.join(args)}: {type(exc).__name__}: {exc}"[:200]
    if r.returncode != 0:
        why = ((r.stderr or "").strip().splitlines() or [""])[0]
        return None, f"git {' '.join(args)}: rc={r.returncode} {why}".strip()[:200]
    return (r.stdout or "").rstrip("\n"), ""


def head_sha(root: str | Path) -> str | None:
    out, _ = _git(Path(root), "rev-parse", "HEAD")
    return out or None


def moved_paths(root: str | Path, since: str | None) -> tuple[list[str] | None, list[str]]:
    """(repo-relative paths moved since ``since`` and in the working tree, failures).

    ``None`` for the paths means the delta is UNKNOWN — the caller must run the full
    suite. An unknown delta is never an empty delta.
    """
    root = Path(root).resolve()
    failures: list[str] = []
    paths: set[str] = set()
    if since:
        out, err = _git(root, "diff", "--name-only", f"{since}..HEAD")
        if out is None:
            failures.append(err)
        else:
            paths.update(x for x in out.splitlines() if x.strip())
    # `-uall`, never bare porcelain. Bare porcelain COLLAPSES an untracked directory to
    # one entry with a trailing slash (`evidence/AUDIT_2026-08-21/`), and that path form
    # is unclassifiable by construction — it matches no import edge and no path literal,
    # so it fail-opens to FULL. MEASURED: 13/13 banked suite_run rows were mode=full, and
    # every close that wrote an evidence directory paid the whole walk for files no test
    # can reach. Enumerating the directory's files restores the classifier's ability to
    # decide, and the fail-open floor still stands for whatever it genuinely cannot place.
    st, err = _git(root, "status", "--porcelain", "-uall")
    if st is None:
        failures.append(err)
    else:
        for ln in st.splitlines():
            if not ln.strip():
                continue
            body = ln[3:]
            if " -> " in body:  # rename: both sides moved
                a, _, b = body.partition(" -> ")
                paths.update({a.strip().strip('"'), b.strip().strip('"')})
            else:
                paths.add(body.strip().strip('"'))
    if failures:
        return None, failures
    return sorted(p.replace("\\", "/") for p in paths if p), failures


# ---------------------------------------------------------------------------
# the selector


def _is_repo_dir(root: Path, lit: str) -> bool:
    """Is this literal the name of a directory INSIDE the repo? Never escapes, never raises."""
    if lit.startswith("/") or lit.startswith("~") or ".." in lit.split("/"):
        return False
    try:
        p = (root / lit).resolve()
        return p.is_dir() and (p == root or root in p.parents)
    except OSError:
        return False


def _glob_hit(path: str, lit: str) -> bool:
    base = path.rsplit("/", 1)[-1]
    return (fnmatch.fnmatch(path, lit) or fnmatch.fnmatch(base, lit)
            or fnmatch.fnmatch(path, "*/" + lit.lstrip("/")))


def _literal_hit(path: str, lit: str, dir_literals: set[str]) -> bool:
    if "*" in lit or "?" in lit:
        return _glob_hit(path, lit)
    lit_n = lit.strip("./")
    if not lit_n:
        return False
    if path == lit_n or path.endswith("/" + lit_n):
        return True
    if lit_n in dir_literals:
        # A directory literal names the directory, not the tree under it. Matching every
        # descendant made `'src'` (a sys.path string in a widely-reached conftest) select
        # 246 of 311 test files for any moved file anywhere under src/. Direct children
        # only: deeper files are reached by the more specific literals and globs that the
        # code touching them actually carries.
        rest = path[len(lit_n) + 1:] if path.startswith(lit_n + "/") else None
        if rest is not None and "/" not in rest:
            return True
    return path.rsplit("/", 1)[-1] == lit_n


def _reverse(smap: dict) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """(hard, lazy) reverse edges: dep -> the files that import it directly."""
    rev_h: dict[str, set[str]] = {}
    rev_l: dict[str, set[str]] = {}
    for f, e in smap["files"].items():
        for d in e["imp"]:
            rev_h.setdefault(d, set()).add(f)
        for d in e.get("lazy", ()):
            rev_l.setdefault(d, set()).add(f)
    return rev_h, rev_l


def _tests_reaching(seeds, rev: tuple[dict[str, set[str]], dict[str, set[str]]],
                    tests: set[str], hops: int = None) -> set[str]:
    """Reverse-BFS to the test files that reach any of ``seeds``.

    Hard edges compose freely; a path may cross at most ``hops`` lazy edges. MEASURED on
    this repo (444 first-party source files, 311 test files): unbounded lazy composition
    puts 138 files in a mutual blob each reaching ~236 test files — the p90 reach is 236,
    i.e. the selector degenerates to the full suite. hops=1 gives p90 45, max 231; hops=0
    (module-level only) gives p90 6, max 149 but drops real conditional dependencies.
    hops=1 is the default: one deferred condition is a dependency worth honouring, a
    chain of them is a chain of conditions and the jubilee cadence is what covers it.
    """
    rev_h, rev_l = rev
    budget = LAZY_HOPS if hops is None else hops
    seen: set[tuple[str, int]] = set()
    stack = [(s, 0) for s in seeds]
    seen.update(stack)
    out: set[str] = set()
    while stack:
        cur, k = stack.pop()
        if cur in tests:
            out.add(cur)
        nxt = [(x, k) for x in rev_h.get(cur, ())]
        if k < budget:
            nxt += [(x, k + 1) for x in rev_l.get(cur, ())]
        for item in nxt:
            if item not in seen:
                seen.add(item)
                stack.append(item)
    return out


def select(root: str | Path, moved: list[str] | None, smap: dict,
           *, failures: list[str] | None = None) -> dict:
    """The plan: which test files this delta impacts, or FULL and why.

    Never returns a narrower set than the evidence supports. Every moved path lands in
    exactly one bucket, and every bucket that means "I do not know" points at FULL.
    """
    root = Path(root).resolve()
    tests: set[str] = set(smap["tests"])
    full_reasons: list[str] = list(failures or [])
    if moved is None:
        full_reasons.append("the moved-set is UNKNOWN (git delta unavailable)")
        return {"mode": "full", "selected": [], "reasons": {}, "full_reasons": full_reasons,
                "unclassified": [], "uncovered": [], "moved": 0}

    rev = _reverse(smap)
    hops = smap.get("lazy_hops", LAZY_HOPS)
    lit_owners: dict[str, set[str]] = {}
    for f, e in smap["files"].items():
        for lit in e["lit"]:
            lit_owners.setdefault(lit, set()).add(f)
    dir_literals = {lit for lit in lit_owners
                    if "*" not in lit and "?" not in lit and _is_repo_dir(root, lit)}

    selected: dict[str, list[str]] = {}
    unclassified: list[str] = []
    uncovered: list[str] = []

    def _take(ts, why: str) -> None:
        for t in ts:
            selected.setdefault(t, []).append(why)

    for p in moved:
        if any(fnmatch.fnmatch(p, g) for g in smap.get("always_full", ALWAYS_FULL)):
            full_reasons.append(f"{p}: always-full trigger")
            continue
        if p in tests:
            _take([p], "the test file itself moved")
            continue
        if Path(p).name.startswith("test_") and p.endswith(".py"):
            if Path(p).parts[0] in {"tests", "atlas"}:
                # a test file the banked map predates — it may collect anything
                full_reasons.append(f"{p}: a test file absent from the map (the map predates it)")
                continue
            # a test-NAMED file outside the collection roots (pyproject testpaths pins
            # pytest to tests/ and atlas/tests): banked evidence, not a suite member —
            # falls through to the ordinary classification chain below (2026-08-24, the
            # GENESIS_DISCRIMINATOR evidence files forcing every close to a 350s full).
        hit = False
        if p in smap["files"]:
            got = _tests_reaching([p], rev, tests, hops)
            if got:
                _take(got, f"imports {p} (transitively)")
                hit = True
        owners = {f for lit, fs in lit_owners.items()
                  if _literal_hit(p, lit, dir_literals) for f in fs}
        if owners:
            # Literal edges propagate on HARD imports only. A data-file dependency is
            # exercised only when the test actually runs the code that opens the path;
            # composing that with a chain of conditional (lazy) imports multiplies
            # conditions without adding reachable risk, and measured as the difference
            # between a usable selection and the whole suite.
            got = _tests_reaching(owners, rev, tests, 0)
            if got:
                _take(got, f"names the path {p}")
                hit = True
        if hit:
            continue
        if p.endswith(".py") and (p.startswith("src/")
                                  or p.startswith("scripts/") or p.startswith("evidence/")):
            # first-party code no test imports and no test names: nothing in the suite can
            # reach it. Honest, reported rather than hidden — and NOT a reason to go full.
            # evidence/ joins the roots (2026-08-24): pytest's testpaths cannot collect it,
            # the map never walks it, and the import/literal checks above already ran — a
            # banked evidence script nothing reaches must not force the full walk.
            uncovered.append(p)
            continue
        unclassified.append(p)

    for p in unclassified:
        full_reasons.append(f"{p}: unclassified — no import edge and no path literal (fail-open)")

    mode = "full" if full_reasons else "impacted"
    return {"mode": mode,
            "selected": sorted(selected) if mode == "impacted" else [],
            "reasons": {k: sorted(set(v))[:4] for k, v in sorted(selected.items())},
            "full_reasons": full_reasons,
            "unclassified": unclassified,
            "uncovered": uncovered,
            "moved": len(moved)}


# ---------------------------------------------------------------------------
# the run ledger (the instrument)


def last_green(root: str | Path) -> dict | None:
    """The most recent green suite row — the commit the next delta is measured from."""
    path = Path(root).resolve() / RUNS_REL
    if not path.is_file():
        return None
    best = None
    try:
        for ln in path.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                row = json.loads(ln)
            except ValueError:
                continue
            if row.get("record") == "suite_run" and row.get("verdict") == "green" \
                    and row.get("head"):
                best = row
    except OSError:
        return None
    return best


def append_run(root: str | Path, row: dict) -> None:
    path = Path(root).resolve() / RUNS_REL
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=False) + "\n")
    except OSError:
        pass


def plan(root: str | Path, *, since: str | None = None, force_full: bool = False,
         rebuild: bool = False) -> dict:
    """The whole decision, one call: map + delta + selection + the induction depth."""
    root = Path(root).resolve()
    smap, why = load_map(root, rebuild=rebuild)
    prev = last_green(root)
    base = since or (prev or {}).get("head")
    chain = int((prev or {}).get("chain_depth", 0))
    if force_full:
        sel = {"mode": "full", "selected": [], "reasons": {},
               "full_reasons": ["--full: the jubilee was asked for"],
               "unclassified": [], "uncovered": [], "moved": 0}
        moved: list[str] | None = []
    elif not base:
        sel = {"mode": "full", "selected": [], "reasons": {},
               "full_reasons": ["no banked green to measure a delta from (first run)"],
               "unclassified": [], "uncovered": [], "moved": 0}
        moved = []
    elif chain >= JUBILEE_EVERY:
        sel = {"mode": "full", "selected": [], "reasons": {},
               "full_reasons": [f"jubilee cadence: {chain} consecutive impacted-greens "
                                f"(>= JUBILEE_EVERY={JUBILEE_EVERY}) — the chain of "
                                f"induction gets re-grounded"],
               "unclassified": [], "uncovered": [], "moved": 0}
        moved = []
    else:
        moved, failures = moved_paths(root, base)
        sel = select(root, moved, smap, failures=failures)
        n_tests = max(1, smap["counts"]["tests"])
        if sel["mode"] == "impacted" and len(sel["selected"]) / n_tests > FULL_THRESHOLD:
            sel = {**sel, "mode": "full", "would_have_selected": len(sel["selected"]),
                   "selected": [],
                   "full_reasons": [f"{len(sel['selected'])}/{n_tests} shards impacted "
                                    f"(> {FULL_THRESHOLD:.0%}) — run it as the jubilee it "
                                    f"already is, and keep the right to clear a banked red"]}
    return {"map_state": why, "map_counts": smap["counts"], "since": base,
            "chain_depth": chain, "head": head_sha(root),
            "moved_paths": moved if moved is not None else None, **sel}
