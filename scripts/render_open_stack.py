"""Render OPEN_STACK.md's author-fork stratum as a projection of a typed store.

W2.3 (the-weld): the stack's live author-fork rows stop being hand-swept markdown
and become TYPED FORK RECORDS in a provenance store — the same move the CLAUDE.md
render made for the ambient breadcrumb (``scripts/render_claude_md.py``). A row a
close hand-edits is a row that drifts; the cure is to stop hand-editing the rows and
start rendering them from a ledger the desk already reads.

THE STORE — ``corpus_friction/open_stack_forks.jsonl`` (a SIBLING of the friction
ledgers, kept separate because the friction channel already carries its own
``kind:"fork"`` records; these are a different population — the author-fork STRATUM,
not a session-banked engine fork). One JSONL record per row, following the friction
ledger idiom. Two populations:

  * RENDER-OWNED (``stratum == 1``, ``render_owned == true``): the Stratum-1
    author-fork table. Fields mirror its columns 1:1 — ``id title opened recurrence
    status trigger`` — so the render is byte-exact and round-trips.
  * DESK-ONLY (``render_owned == false``): live 🔴 author-forks that live OUTSIDE the
    Stratum-1 table (F27 in Stratum 2; the FQ7 sweep-log bullet). The render leaves
    their markdown exactly where it sits (the spec keeps sweep logs + other strata as
    prose); the store mirrors them so the desk's fork class reads ONE store, not the
    markdown. ``context`` carries the desk row's one-line body.

WHAT THE RENDER OWNS — ONLY the Stratum-1 author-fork table (header, separator, data
rows), regenerated in place from the store. Every other byte of OPEN_STACK.md — the
header, the sweep logs, Strata 0/2, the cleared/killed log — is left untouched. The
render never invents a row and never changes a status: migration re-homes the data,
his verdicts stay his.

This renderer is PURE: stdlib only, deterministic, no LLM, no network.

CLI:
    python3 scripts/render_open_stack.py             # print render to stdout
    python3 scripts/render_open_stack.py --write     # write <repo>/OPEN_STACK.md
    python3 scripts/render_open_stack.py --check      # exit 0 iff committed == render
    python3 scripts/render_open_stack.py --migrate    # seed the store from the md ONCE
    python3 scripts/render_open_stack.py --migrate --force   # re-seed (overwrites store)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORE_REL = "corpus_friction/open_stack_forks.jsonl"

# The Stratum-1 author-fork table's fixed frame — the render owns exactly this block.
S1_HEADER = "| # | Fork | First raised | Recurred | Status | Trigger / note |"
S1_SEP = "|---|------|--------------|----------|--------|----------------|"
BANNER = (
    "<!-- RENDERED FROM corpus_friction/open_stack_forks.jsonl by "
    "scripts/render_open_stack.py — never hand-edit these rows; edit the store, then "
    "--write. Drift fails the close (render_open_stack.py --check). -->"
)

#: the live-status marker OPEN_STACK.md's legend assigns to 🔴 (mirrors desk._LIVE_MARKER).
_LIVE_MARKER = "\U0001f534"


# ---------------------------------------------------------------------------
# THE STORE
# ---------------------------------------------------------------------------
def load_forks(repo: Path) -> list[dict]:
    """Every record in the fork store; bad lines skipped, an absent store is []."""
    p = repo / STORE_REL
    out: list[dict] = []
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def _render_owned(forks: list[dict]) -> list[dict]:
    """The Stratum-1 table rows, in store order — the only rows the render emits."""
    return [f for f in forks
            if f.get("render_owned") and int(f.get("stratum") or 0) == 1]


# ---------------------------------------------------------------------------
# THE RENDER — regenerate the Stratum-1 table in place; touch nothing else.
# ---------------------------------------------------------------------------
def _row(fork: dict) -> str:
    cells = [str(fork.get(k, "")) for k in
             ("id", "title", "opened", "recurrence", "status", "trigger")]
    return "| " + " | ".join(cells) + " |"


def _render_block(forks: list[dict]) -> list[str]:
    block = [BANNER, S1_HEADER, S1_SEP]
    block.extend(_row(f) for f in _render_owned(forks))
    return block


def _s1_region(lines: list[str]) -> tuple[int, int]:
    """[start, end) line span the render owns: an optional leading BANNER, the S1
    header, its separator, and the contiguous ``|``-rows. Returns (-1, -1) if the
    header is not found (a malformed file is left untouched, never crashed)."""
    hdr = -1
    for i, ln in enumerate(lines):
        if ln.strip() == S1_HEADER:
            hdr = i
            break
    if hdr < 0:
        return -1, -1
    start = hdr
    if hdr > 0 and lines[hdr - 1].strip() == BANNER:
        start = hdr - 1
    # end: past the separator, consume every contiguous table row.
    end = hdr + 1
    if end < len(lines) and lines[end].strip().startswith("|"):
        end += 1  # the separator
    while end < len(lines) and lines[end].lstrip().startswith("|"):
        end += 1
    return start, end


def render(repo: Path) -> str:
    """OPEN_STACK.md with the Stratum-1 author-fork table regenerated from the store.
    Everything outside that one table is byte-identical to the committed file."""
    md = (repo / "OPEN_STACK.md").read_text(encoding="utf-8")
    trailing_nl = md.endswith("\n")
    lines = md.split("\n")
    if trailing_nl:
        lines = lines[:-1]  # drop the empty tail split produced
    start, end = _s1_region(lines)
    if start < 0:
        return md  # no table to own; leave the file exactly as-is
    forks = load_forks(repo)
    new_lines = lines[:start] + _render_block(forks) + lines[end:]
    out = "\n".join(new_lines)
    return out + "\n" if trailing_nl else out


def check(repo: Path) -> int:
    rendered = render(repo)
    current = (repo / "OPEN_STACK.md").read_text(encoding="utf-8")
    if current == rendered:
        return 0
    import difflib
    diff = difflib.unified_diff(
        current.splitlines(keepends=True),
        rendered.splitlines(keepends=True),
        fromfile="OPEN_STACK.md (committed)",
        tofile="OPEN_STACK.md (rendered)",
    )
    sys.stdout.writelines(diff)
    print("\nOPEN_STACK.md Stratum-1 table is stale or hand-edited — re-render: "
          "python3 scripts/render_open_stack.py --write")
    return 1


# ---------------------------------------------------------------------------
# MIGRATION — parse the current markdown into records, ONCE.
# ---------------------------------------------------------------------------
def _parse_s1_table(lines: list[str]) -> list[dict]:
    start, end = _s1_region(lines)
    if start < 0:
        return []
    recs: list[dict] = []
    for ln in lines[start:end]:
        s = ln.strip()
        if not s.startswith("| ") and not s.startswith("|F"):
            continue
        if s == S1_HEADER or set(s.replace("|", "").strip()) <= set("-: "):
            continue  # header or separator
        cells = [c.strip() for c in ln.split("|")][1:-1]
        if len(cells) != 6:
            continue
        fid, title, opened, recurrence, status, trigger = cells
        if not fid or fid == "#":
            continue
        recs.append({
            "id": fid, "kind": "open-stack-fork", "stratum": 1, "render_owned": True,
            "title": title, "opened": opened, "recurrence": recurrence,
            "status": status, "trigger": trigger,
        })
    return recs


def _parse_desk_only(lines: list[str]) -> list[dict]:
    """The 🔴 author-forks that live outside Stratum 1: F-rows in the Stratum-2 table
    and ``- **F…**`` sweep-log bullets carrying the live marker. Captured for the desk
    (render_owned=false); their markdown is left in place."""
    recs: list[dict] = []
    seen: set[str] = set()
    s1_start, s1_end = _s1_region(lines)
    for i, ln in enumerate(lines):
        if s1_start <= i < s1_end:
            continue  # already owned by the Stratum-1 render
        s = ln.lstrip()
        # Stratum-2 (and E-table) F-rows carrying the live marker.
        if s.startswith("| F") and ln.count("|") >= 3 and _LIVE_MARKER in ln:
            cells = [c.strip() for c in ln.split("|")][1:-1]
            if len(cells) < 5:
                continue
            fid = cells[0]
            if fid in seen:
                continue
            seen.add(fid)
            recs.append({
                "id": fid, "kind": "open-stack-fork", "stratum": 2,
                "render_owned": False, "title": cells[1], "status": _LIVE_MARKER,
                "context": ln.strip(),
            })
        # sweep-log bullet forks (- **FQ7 …🔴…**: …).
        elif s.startswith("- **") and _LIVE_MARKER in ln:
            body = s[len("- **"):]
            fid = (body.split()[0] if body.split() else "").strip("*:—-")
            if not fid or fid in seen:
                continue
            seen.add(fid)
            title = body.replace("**", "").split(":", 1)[0].strip()
            recs.append({
                "id": fid, "kind": "open-stack-fork", "stratum": "sweep-bullet",
                "render_owned": False, "title": title, "status": _LIVE_MARKER,
                "context": ln.strip(),
            })
    return recs


def migrate(repo: Path, force: bool = False) -> int:
    store = repo / STORE_REL
    if store.exists() and store.stat().st_size > 0 and not force:
        print(f"store already seeded: {store} (use --force to re-seed)")
        return 1
    lines = (repo / "OPEN_STACK.md").read_text(encoding="utf-8").split("\n")
    recs = _parse_s1_table(lines) + _parse_desk_only(lines)
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs),
        encoding="utf-8")
    n_owned = sum(1 for r in recs if r.get("render_owned"))
    print(f"wrote {len(recs)} records ({n_owned} render-owned Stratum-1, "
          f"{len(recs) - n_owned} desk-only) to {store}")
    return 0


def main(argv: list[str]) -> int:
    args = list(argv)
    if "--migrate" in args:
        return migrate(ROOT, force="--force" in args)
    arg = args[0] if args else ""
    if arg == "--write":
        (ROOT / "OPEN_STACK.md").write_text(render(ROOT), encoding="utf-8")
        print("wrote OPEN_STACK.md")
        return 0
    if arg == "--check":
        return check(ROOT)
    if arg in ("", "-", "--stdout"):
        sys.stdout.write(render(ROOT))
        return 0
    print(f"unknown arg: {arg!r}; use (none) | --write | --check | --migrate",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
