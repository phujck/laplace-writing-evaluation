"""tests/test_xdist_isolation.py — the guard on the parallel-suite row-source.

WHY THIS EXISTS. ``WO-20260820-suite-runs-on-one-core`` wants the close's suite step
(``scripts/sewup.py:188``) run under ``pytest -n auto``. Its GATE, verbatim: *"a
test-isolation pass first - any test writing a repo-root store races under -n;
store_lock covers .self_embeddings.json, the others are unaudited."* That pass ran and
banked its verdict per test FILE in ``tests/xdist_isolation_audit.json`` — the typed
row-source a later grouping step (``--dist loadgroup`` + an ``xdist_group`` mark per
contended store) consumes.

WHAT THIS GUARD DOES. Rows go stale the moment the tree moves. A test file added after
the audit that writes a repo-root store would slip into a parallel run unclassified and
race silently — the exact failure the gate was raised to prevent. So: any test file
carrying a repo-root-write SIGNATURE, or naming one of the live-writer tokens the audit
found, must carry a row. It is a STATIC scan (AST, no execution, ~1.5s); it never runs
the suite it guards.

WHAT IT CANNOT SEE. The static tier catches direct repo-anchored writes, ``chdir``, raw
``os.environ`` mutation, and the named live-writer call tokens. It does NOT see a NEW
indirect write path — a test reaching a src function that writes a repo-root store
under a name this file has never heard of. That class is caught only by re-running the
empirical write trace named in the audit's ``method.empirical`` field. This guard says
so rather than pretending otherwise.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
AUDIT_PATH = REPO / "tests" / "xdist_isolation_audit.json"

#: write verbs on a path expression anchored at the LIVE repo root
_PATH_WRITES = {"write_text", "write_bytes", "mkdir", "touch", "unlink", "rename",
                "replace", "rmdir", "symlink_to", "hardlink_to", "chmod", "open"}
_OS_WRITES = {"remove", "unlink", "rename", "replace", "mkdir", "makedirs", "rmdir",
              "truncate"}
_SHUTIL_WRITES = {"rmtree", "copy", "copy2", "copyfile", "copytree", "move"}
#: ops whose DESTINATION (arg 1) is the write, not the source (arg 0)
_TWO_ARG = {"copy", "copy2", "copyfile", "copytree", "move", "rename", "replace"}


@pytest.fixture(scope="module")
def audit() -> dict:
    if not AUDIT_PATH.is_file():
        pytest.fail(f"the row-source is gone: {AUDIT_PATH} — the -n gate has no audit")
    return json.loads(AUDIT_PATH.read_text(encoding="utf-8"))


def _test_files() -> list[Path]:
    return sorted(list((REPO / "tests").glob("test_*.py"))
                  + list((REPO / "atlas" / "tests").glob("test_*.py")))


def _rel(p: Path) -> str:
    return p.relative_to(REPO).as_posix()


def _is_live_root(src: str) -> bool:
    """Does this expression text resolve to the LIVE repo root (not a tmp fixture)?"""
    if "Path(__file__)" not in src:
        return False
    return (".parents[1]" in src or ".parents[2]" in src
            or ".parent.parent" in src or ".parents[0]" in src)


def _head(node):
    """the leftmost Name of a path chain — ``a / 'b' / 'c'``, ``a.b``, ``a[0]``."""
    cur, hops = node, 0
    while hops < 40:
        hops += 1
        if isinstance(cur, ast.BinOp) and isinstance(cur.op, ast.Div):
            cur = cur.left
        elif isinstance(cur, (ast.Attribute, ast.Subscript)):
            cur = cur.value
        elif isinstance(cur, ast.Call):
            cur = cur.func
        else:
            break
    return cur.id if isinstance(cur, ast.Name) else None


def signatures(path: Path) -> list[tuple[int, str, str]]:
    """(line, kind, source-line) for every repo-root-write signature in one test file.

    Deliberately over-inclusive: a name bound ANYWHERE in the file to a live-root
    expression taints that name file-wide. A false positive costs one audit row saying
    so; a false negative costs a silent race under ``-n``.
    """
    try:
        src = path.read_text(encoding="utf-8-sig", errors="replace")
        tree = ast.parse(src)
    except (OSError, SyntaxError, ValueError) as exc:
        return [(0, "unparseable", f"{type(exc).__name__}: {exc}")]
    lines = src.splitlines()
    anchors = {t.id
               for n in ast.walk(tree) if isinstance(n, ast.Assign)
               and _is_live_root(ast.unparse(n.value))
               for t in n.targets if isinstance(t, ast.Name)}
    hits: list[tuple[int, str, str]] = []

    def ev(ln: int) -> str:
        return lines[ln - 1].strip()[:160] if 0 < ln <= len(lines) else ""

    def anchored(node) -> bool:
        return _is_live_root(ast.unparse(node)) or _head(node) in anchors

    for n in ast.walk(tree):
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Subscript) and ast.unparse(t.value) in ("os.environ",
                                                                             "environ"):
                    hits.append((n.lineno, "env-raw", ev(n.lineno)))
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        if isinstance(f, ast.Attribute) and f.attr == "chdir":
            hits.append((n.lineno, "chdir", ev(n.lineno)))
        if isinstance(f, ast.Attribute) and f.attr in ("putenv", "setdefault") \
                and ast.unparse(f.value) in ("os", "os.environ", "environ"):
            hits.append((n.lineno, "env-raw", ev(n.lineno)))
        if isinstance(f, ast.Attribute) and f.attr in _PATH_WRITES and anchored(f.value):
            hits.append((n.lineno, f"Path.{f.attr}", ev(n.lineno)))
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
            mod, fn = f.value.id, f.attr
            if (mod == "os" and fn in _OS_WRITES) or (mod == "shutil" and fn in _SHUTIL_WRITES):
                cand = n.args[1:2] if (fn in _TWO_ARG and len(n.args) > 1) else n.args[:1]
                if cand and anchored(cand[0]):
                    hits.append((n.lineno, f"{mod}.{fn}", ev(n.lineno)))
        if isinstance(f, ast.Name) and f.id == "open" and len(n.args) >= 2:
            m = n.args[1]
            mode = m.value if isinstance(m, ast.Constant) and isinstance(m.value, str) else ""
            if any(c in mode for c in "wax+") and anchored(n.args[0]):
                hits.append((n.lineno, f"open:{mode}", ev(n.lineno)))
    out, seen = [], set()
    for h in sorted(hits):
        if (h[0], h[1]) not in seen:
            seen.add((h[0], h[1]))
            out.append(h)
    return out


# ---------------------------------------------------------------------------
# the guard
# ---------------------------------------------------------------------------

def test_the_audit_is_a_well_formed_row_source(audit):
    """Rows are truth — so the row-source's own shape is asserted, not assumed."""
    for key in ("schema", "ts", "method", "counts", "verdicts", "rows",
                "signature_triggers", "live_writer_tokens"):
        assert key in audit, f"xdist_isolation_audit.json is missing {key!r}"
    legal = set(audit["verdicts"])
    assert legal, "the audit declares no legal verdicts"
    seen = set()
    for r in audit["rows"]:
        for key in ("file", "verdict", "stores", "evidence", "note"):
            assert key in r, f"row {r.get('file')!r} is missing {key!r}"
        assert r["verdict"] in legal, f"{r['file']}: illegal verdict {r['verdict']!r}"
        assert r["file"] not in seen, f"duplicate row for {r['file']}"
        seen.add(r["file"])
        if r["verdict"] == "needs-serialization":
            assert r["stores"], f"{r['file']} needs serialization but names no store"
            assert r["evidence"], f"{r['file']} needs serialization but cites no evidence"
    n = audit["counts"]
    assert n.get("files_total") == len(audit["rows"]), \
        f"counts.files_total {n.get('files_total')} != {len(audit['rows'])} rows"


def test_no_test_file_carries_an_unaudited_write_signature(audit):
    """THE GATE. A new test that writes the live tree must be classified before -n.

    A row of ANY verdict discharges this — including ``safe-parallel`` with a note
    saying the signature is a false positive. What is forbidden is a signature nobody
    has looked at.
    """
    rows = {r["file"] for r in audit["rows"]}
    triggers = tuple(audit["signature_triggers"])
    unaudited = {}
    for p in _test_files():
        rel = _rel(p)
        if rel in rows:
            continue                       # already classified — the scan can skip it
        src = p.read_text(encoding="utf-8-sig", errors="replace")
        if not any(t in src for t in triggers):
            continue                       # cannot produce a signature under these rules
        sig = signatures(p)
        if sig:
            unaudited[rel] = [f"{ln}:{kind} {text}" for ln, kind, text in sig[:4]]
    assert not unaudited, (
        "test file(s) carry a repo-root-write signature and have NO row in "
        "tests/xdist_isolation_audit.json — they would race under `pytest -n`:\n"
        + "\n".join(f"  {f}\n    " + "\n    ".join(v) for f, v in sorted(unaudited.items()))
        + "\n\nClassify each one (safe-parallel / needs-serialization) and add its row. "
          "Re-derive with the empirical trace named in the audit's method.empirical "
          "when the write is INDIRECT (through a src call), not textual.")


def test_no_test_file_reaches_a_known_live_writer_unaudited(audit):
    """The indirect tier: the call tokens the empirical trace caught writing live state.

    Textual, not semantic — a token appearing in a docstring counts. That is deliberate:
    the cost of a spurious row is one line; the cost of a missed one is a flaky close.
    """
    rows = {r["file"] for r in audit["rows"]}
    tokens = audit["live_writer_tokens"]
    offenders = {}
    for p in _test_files():
        rel = _rel(p)
        if rel in rows:
            continue
        src = p.read_text(encoding="utf-8-sig", errors="replace")
        hit = sorted(t for t in tokens if t in src)
        if hit:
            offenders[rel] = hit
    assert not offenders, (
        "test file(s) name a KNOWN live-repo writer and have no row in "
        "tests/xdist_isolation_audit.json:\n"
        + "\n".join(f"  {f}: {', '.join(v)}" for f, v in sorted(offenders.items())))


def test_no_audit_row_names_a_vanished_file(audit):
    """A stale row is a render pretending to be a row — it would pin a group that no
    longer exists and quietly under-serialize the run."""
    gone = [r["file"] for r in audit["rows"] if not (REPO / r["file"]).is_file()]
    assert not gone, ("xdist_isolation_audit.json rows name file(s) that no longer "
                      f"exist — drop the rows: {gone}")
