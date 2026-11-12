"""memory_parity.py - the harness-memory <-> repo parity gate (2026-08-20 audit, AP-17).

The per-machine harness memory channel (~/.claude/projects/<repo-slug>/memory/) holds
Gerard's hammered working laws as small feedback-frontmatter files, read ambiently at
session start on THIS box. It sits outside git entirely - a box wipe loses it with no
recovery path (AP-17's own measurement: zero bytes of the channel were tracked before
this audit). The audit found it also drifts in both directions at once: files exist in
the channel with no backing row in proxy_verdicts.jsonl (AP-15 - a fresh box could not
even reconstruct WHERE these laws came from), and rows get minted in the ledger that
never get rendered into the channel (AP-16 - a law he stated survives only as a row a
human never sees ambiently again).

This script is the mechanical check for both directions. It is REPORT-ONLY BY DESIGN
(his own audit's binding constraint, carried from the AP-16/AP-17 verifier's cure
objection): the channel is per-machine BY DESIGN, so this checker must never overwrite
a box's local channel edits - it only reports gaps. Draining a superseded ruling from
the channel, or rendering a fresh one into it, stays a human/fixer act performed with
the render conventions below; this gate just tells you where the two sides disagree.

Matching a memory file to a ledger row (either direction) accepts any of:
  (a) the file's frontmatter `name:` equals the row id's slug (the part after
      `PV-<timestamp>Z-`) - the convention every row minted this audit follows;
  (b) the file's body cites the row's exact id verbatim (a "Repo-side row: ..." line,
      the convention this audit's renders use);
  (c) the row's own `unlocks`/`ruling`/`evidence` text names `memory/<file>.md`
      verbatim (the convention the pilot-night rows use, e.g. orchestrate-synthesize-
      refill's "mirrors memory/orchestrate-synthesize-refill.md").
A row may also declare itself intentionally unrendered via a truthy `channel_skip`
field (a short reason string) - not yet used by any row, but supported so a future
row need not show up as a false gap. Likewise a memory file may mark itself
channel-only by containing the literal marker "CHANNEL-ONLY:" followed by a reason.

CLI:
    scripts/laplace-python scripts/memory_parity.py --legacy-audit                 # both directions, 14-day window
    scripts/laplace-python scripts/memory_parity.py --legacy-audit --days 30        # widen the reverse-direction window
    scripts/laplace-python scripts/memory_parity.py --legacy-audit --memory-dir X   # override channel location

Last line is always greppable::

    memory-parity: VERDICT=PASS gaps=[]
    memory-parity: VERDICT=FAIL gaps=[forward:claim-the-ideation-loop,reverse:PV-...]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]
LEDGER = REPO / "proxy_verdicts.jsonl"

_ID_RE = re.compile(r"^PV-\d{8}T\d{6}Z-(?P<slug>[a-z0-9][a-z0-9-]*)$")
_ID_TOKEN_RE = re.compile(r"PV-\d{8}T\d{6}Z-[a-z0-9][a-z0-9-]*")
_FRONTMATTER_NAME_RE = re.compile(r"^name:\s*(\S.*?)\s*$", re.MULTILINE)
_RENDER_KINDS = ("author-law", "author-ruling")


def _default_memory_dir() -> Path:
    """The per-machine channel location: ~/.claude/projects/<repo-path-slugged>/memory.

    Claude Code's own convention (unwritten anywhere in this repo before this audit -
    AP-17's own measurement: no script computes this path today): the project's own
    directory name under ~/.claude/projects is the repo's absolute path with every
    '/' replaced by '-'. Computed, never hardcoded, so it survives a repo move.
    """
    slug = str(REPO).replace("/", "-")
    return Path.home() / ".claude" / "projects" / slug / "memory"


def _load_ledger_rows(ledger: Path) -> tuple[list[dict], list[str]]:
    """Returns (rows, parse_errors). Never raises - a gate reports, it doesn't crash."""
    rows: list[dict] = []
    errors: list[str] = []
    if not ledger.is_file():
        errors.append(f"{ledger} does not exist")
        return rows, errors
    for i, line in enumerate(ledger.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            errors.append(f"{ledger.name}:{i} unparseable: {exc}")
    return rows, errors


class Note:
    def __init__(self, path: Path):
        self.path = path
        self.filename = path.name
        self.text = path.read_text(encoding="utf-8", errors="replace")
        m = _FRONTMATTER_NAME_RE.search(self.text)
        self.name = m.group(1) if m else path.stem
        self.channel_only_reason: Optional[str] = None
        for line in self.text.splitlines():
            if "CHANNEL-ONLY:" in line.upper():
                self.channel_only_reason = line.strip()
                break

    def cited_row_ids(self) -> set[str]:
        return set(_ID_TOKEN_RE.findall(self.text))


def _load_notes(memory_dir: Path) -> list[Note]:
    if not memory_dir.is_dir():
        return []
    notes = []
    for p in sorted(memory_dir.glob("*.md")):
        if p.name == "MEMORY.md":
            continue  # the index, not a note - it is a render OF the notes below
        notes.append(Note(p))
    return notes


def _row_slug(row_id: str) -> Optional[str]:
    m = _ID_RE.match(row_id)
    return m.group("slug") if m else None


def _note_backs_forward(note: Note, rows_by_id: dict[str, dict], slugs: dict[str, str]) -> Optional[str]:
    """Returns the backing row id if `note` (a memory file) has a repo row, else None."""
    for row_id, slug in slugs.items():
        if slug == note.name:
            return row_id
    cited = note.cited_row_ids() & rows_by_id.keys()
    if cited:
        return sorted(cited)[0]
    return None


def _row_backs_reverse(row: dict, notes: list[Note]) -> Optional[str]:
    """Returns the backing note filename if `row` (a ledger row) has a channel render."""
    row_id = row.get("id", "")
    slug = _row_slug(row_id)
    for note in notes:
        if slug is not None and note.name == slug:
            return note.filename
    if row_id and any(row_id in note.text for note in notes):
        return next(note.filename for note in notes if row_id in note.text)
    haystack = " ".join(
        str(row.get(k, "")) for k in ("unlocks", "ruling", "evidence")
    )
    for note in notes:
        if f"memory/{note.filename}" in haystack:
            return note.filename
    return None


def _parse_date(s: str) -> Optional[date]:
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def legacy_audit() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--memory-dir", type=Path, default=None,
                     help="override the channel directory (default: computed from repo path)")
    ap.add_argument("--ledger", type=Path, default=LEDGER,
                     help="override proxy_verdicts.jsonl path")
    ap.add_argument("--days", type=int, default=14,
                     help="reverse-direction window in days, anchored on the newest row date (default 14)")
    ap.add_argument("--now", type=str, default=None,
                     help="override the anchor date (YYYY-MM-DD) for --days; default is the ledger's own newest row date")
    args = ap.parse_args()

    memory_dir = args.memory_dir or _default_memory_dir()
    rows, parse_errors = _load_ledger_rows(args.ledger)
    for err in parse_errors:
        print(f"  LEDGER-ERROR  {err}")

    rows_by_id = {r["id"]: r for r in rows if "id" in r}
    slugs = {rid: s for rid, r in rows_by_id.items() if (s := _row_slug(rid)) is not None}
    notes = _load_notes(memory_dir)

    print(f"channel dir: {memory_dir} ({'present' if memory_dir.is_dir() else 'ABSENT'})")
    print(f"ledger:      {args.ledger} ({len(rows)} rows)")
    print(f"notes:       {len(notes)} file(s) (excluding MEMORY.md)")
    print()

    gaps: list[str] = []

    # ---- forward: memory -> repo -----------------------------------------
    print("-- forward (every memory file names a backing row, or is channel-only) --")
    if not notes:
        print("  (no notes found - channel absent or empty on this box)")
    for note in sorted(notes, key=lambda n: n.filename):
        backer = _note_backs_forward(note, rows_by_id, slugs)
        if backer:
            print(f"  OK    {note.filename:<40}  <- {backer}")
        elif note.channel_only_reason:
            print(f"  OK    {note.filename:<40}  channel-only: {note.channel_only_reason}")
        else:
            print(f"  GAP   {note.filename:<40}  no backing row and no channel-only marker")
            gaps.append(f"forward:{note.name}")

    # ---- reverse: repo -> memory -------------------------------------------
    print()
    anchor: Optional[date]
    if args.now:
        anchor = _parse_date(args.now)
    else:
        dated = [d for r in rows if (d := _parse_date(r.get("date", "")))]
        anchor = max(dated) if dated else None
    window_start = anchor - timedelta(days=args.days) if anchor else None
    print(f"-- reverse (every author-law/author-ruling row in the last {args.days}d has a render "
          f"or explicit skip) --")
    if anchor is None:
        print("  (no dated rows in the ledger - cannot anchor the window, skipping reverse check)")
    else:
        print(f"   anchor={anchor.isoformat()} window_start={window_start.isoformat()}")
        candidates = [
            r for r in rows
            if r.get("kind") in _RENDER_KINDS
            and (d := _parse_date(r.get("date", ""))) is not None
            and d >= window_start
        ]
        if not candidates:
            print("  (no author-law/author-ruling rows in the window)")
        for row in sorted(candidates, key=lambda r: r.get("id", "")):
            row_id = row.get("id", "?")
            skip = row.get("channel_skip")
            backer = _row_backs_reverse(row, notes)
            if backer:
                print(f"  OK    {row_id:<55}  -> memory/{backer}")
            elif skip:
                print(f"  OK    {row_id:<55}  channel_skip: {skip}")
            else:
                print(f"  GAP   {row_id:<55}  no channel render and no channel_skip")
                gaps.append(f"reverse:{row_id}")

    print()
    verdict = "FAIL" if gaps else "PASS"
    print(f"memory-parity: VERDICT={verdict} gaps=[{','.join(gaps)}]")
    return 1 if gaps else 0


def main() -> int:
    if "--legacy-audit" in sys.argv:
        sys.argv.remove("--legacy-audit")
        return legacy_audit()
    if len(sys.argv) > 1:
        raise SystemExit("legacy name/reference audit options require --legacy-audit")
    from laplace.engine.session_memory import projection
    result = projection(REPO, compact=True)
    summary = {key: result[key] for key in ("status", "generation", "views", "unreconciled_rulings", "read_cost")}
    print(json.dumps(summary, indent=1))
    return int(result["status"] != "CURRENT" or "STALE" in result["views"].values())


if __name__ == "__main__":
    sys.exit(main())
