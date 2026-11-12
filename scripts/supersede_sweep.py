#!/usr/bin/env python3
"""supersede_sweep.py — the retrospective half of the proxy: when a verdict SUPERSEDES
a prior marker (the seal, a with-veto draft, an old F-ruling), where in the durable
corpus does the SUPERSEDED text still stand unstamped?

A reporter by default. For a ruling (or ``--all``), it takes the verdict's
``supersedes_markers`` (defaulting to its ``supersedes`` ids), greps the root ``*.md``
durable corpus for each marker as a literal string, and emits a worklist of the citations
that are NOT stamped. A site is "stamped" if its own line or the line directly above/below
carries the word ``SUPERSEDED``. PASS when zero unstamped citations remain, WARN otherwise.

AUDIT_2026-07-15 §B3: advisory-only (rc always 0) meant an unstamped citation could stand
forever without ever moving an exit code. Two new, additive flags close that gap without
touching the plain-invocation behaviour, which stays byte-identical:

  --gate  turns the report into a real pass/fail signal: rc=1 if any unstamped citation of
          a superseded marker remains, rc=0 when clean. Prints one extra summary line naming
          the unstamped count and the affected files, and the VERDICT sentinel itself reads
          FAIL (not WARN) when args.gate is set and citations remain — WARN stays reserved
          for the plain advisory read. Selection defaults to ``--all`` when neither
          ``--ruling`` nor ``--all`` is given (the close gate calls bare ``--gate``).
  --fix   writes the missing SUPERSEDED stamp next to each unstamped citation, IN PLACE — a
          new line inserted directly after the citing line, in the exact form ``_stamped()``
          already recognizes, so a --fix'd file passes the very next --gate. Prints each file
          it touches. May run alone or combined with --gate; also defaults selection to
          ``--all`` when neither ``--ruling`` nor ``--all`` is given. Fixing the durable
          corpus automatically from the close gate is explicitly NOT wired — that stays his
          decision (banked in the audit); --fix is opt-in, run by hand.

Neither flag: today's advisory behaviour, byte-identical — rc is always 0. The last line is
the sentinel (scripts/paper_gates.py convention):
    VERDICT=PASS unstamped=0
    VERDICT=WARN unstamped=<n> sites=<file:line,...>
    VERDICT=FAIL unstamped=<n> sites=<file:line,...>   (only when --gate and citations remain)
so a truncated read (tail -1) still carries the whole verdict.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from laplace.engine.author_proxy import load_verdicts  # noqa: E402

# subtrees that are not the LIVE durable surface — history / sessions / the soul
_EXCLUDE_DIRS = {"archive", "sessions", "soul"}
_STAMP = "SUPERSEDED"


def _durable_md(repo: Path) -> list[Path]:
    """Root-level ``*.md`` — the live durable corpus (excludes archive/, sessions/,
    soul/ by construction, since a root glob never descends into them). Dated
    SESSION_HANDOFF_*.md are banked trace, true-when-written — never sweep targets."""
    return [p for p in sorted(repo.glob("*.md"))
            if not (_EXCLUDE_DIRS & set(p.parts))
            and not p.name.startswith("SESSION_HANDOFF_")]


def _markers_for(rec: dict) -> list[str]:
    markers = rec.get("supersedes_markers") or rec.get("supersedes") or []
    return [str(m) for m in markers if str(m).strip()]


def _stamped(lines: list[str], i: int) -> bool:
    """A citation is stamped if its line or an immediate neighbour names SUPERSEDED,
    or the line itself cites a banked verdict id (PV-…) — a closure row that quotes
    the old posture beside its ruling is self-superseding, not an unstamped claim."""
    if "PV-20" in lines[i]:
        return True
    for j in (i - 1, i, i + 1):
        if 0 <= j < len(lines) and _STAMP in lines[j]:
            return True
    return False


def sweep(repo: Path, records: list[dict]) -> list[dict]:
    """The unstamped citations across all selected records' markers.
    Each hit: {file, line, marker, excerpt, rec_id} — rec_id is the id of the (first)
    verdict whose markers name this citation, carried along so --fix can stamp a
    meaningful attribution rather than a bare token."""
    corpus = [(p, p.read_text(encoding="utf-8", errors="replace").splitlines())
              for p in _durable_md(repo)]
    markers: list[str] = []
    marker_to_rec: dict[str, str] = {}
    for rec in records:
        rid = str(rec.get("id") or "")
        for m in _markers_for(rec):
            if m not in markers:
                markers.append(m)
                marker_to_rec[m] = rid

    hits: list[dict] = []
    for path, lines in corpus:
        for i, line in enumerate(lines):
            for m in markers:
                if m in line and not _stamped(lines, i):
                    hits.append({
                        "file": path.name,
                        "line": i + 1,
                        "marker": m,
                        "excerpt": line.strip()[:160],
                        "rec_id": marker_to_rec.get(m, ""),
                    })
    return hits


def _fix_stamp_line(hit: dict) -> str:
    """The stamp text --fix writes: carries the literal ``SUPERSEDED`` token _stamped()
    matches, plus the marker and (when known) the ruling that supersedes it — the same
    attribution the hand-stamped house convention carries (see e.g. HANDOFF.md's
    ``SUPERSEDED 2026-07-12: … PV-20260712-f11-the-unseal`` stamps)."""
    who = f" by {hit['rec_id']}" if hit.get("rec_id") else ""
    return f"**SUPERSEDED**{who} — supersedes `{hit['marker']}` (stamped by supersede_sweep --fix)"


def apply_fix(repo: Path, hits: list[dict]) -> list[str]:
    """Write the missing SUPERSEDED stamp next to each unstamped citation, IN PLACE: one new
    line inserted directly after the citing line, so ``_stamped()`` sees it as an immediate
    neighbour (``i+1``) on the very next sweep. Inserts bottom-up per file so earlier line
    numbers in the same file stay valid as later ones shift. Returns the sorted list of file
    names actually touched."""
    by_file: dict[str, list[dict]] = {}
    for h in hits:
        by_file.setdefault(h["file"], []).append(h)

    touched: list[str] = []
    for fname, file_hits in sorted(by_file.items()):
        path = repo / fname
        text = path.read_text(encoding="utf-8", errors="replace")
        trailing_nl = text.endswith("\n")
        lines = text.splitlines()
        for h in sorted(file_hits, key=lambda x: x["line"], reverse=True):
            idx = h["line"] - 1  # 0-based line index of the citation
            lines.insert(idx + 1, _fix_stamp_line(h))
        new_text = "\n".join(lines) + ("\n" if trailing_nl else "")
        path.write_text(new_text, encoding="utf-8")
        touched.append(fname)
    return touched


def _select(all_records: list[dict], ruling_id: str | None, do_all: bool) -> list[dict]:
    if do_all:
        return [r for r in all_records if _markers_for(r)]
    return [r for r in all_records if r.get("id") == ruling_id]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Report where a superseded marker still stands unstamped in the durable "
            "corpus. Pure reporter by default (rc always 0). --gate turns the report "
            "into a pass/fail signal (rc=1 on any unstamped citation). --fix writes "
            "the missing stamp in place. Neither flag: today's advisory behaviour, "
            "byte-identical."
        )
    )
    parser.add_argument("--repo", default=".", help="repo root (default: cwd)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--ruling", help="a single verdict id (PV-…)")
    group.add_argument("--all", action="store_true",
                       help="sweep every verdict that supersedes something")
    parser.add_argument(
        "--gate", action="store_true",
        help=(
            "rc=1 if any unstamped citation of a superseded marker remains, rc=0 "
            "when clean (advisory v1's rc-always-0 becomes a real close gate only "
            "under this flag). Selection defaults to --all when neither --ruling "
            "nor --all is given."
        ),
    )
    parser.add_argument(
        "--fix", action="store_true",
        help=(
            "write the missing SUPERSEDED stamp next to each unstamped citation, in "
            "place, so a --fix'd file passes the very next --gate. May run alone or "
            "combined with --gate. Selection defaults to --all when neither --ruling "
            "nor --all is given."
        ),
    )
    args = parser.parse_args(argv)

    if not args.ruling and not args.all:
        if args.gate or args.fix:
            args.all = True
        else:
            parser.error(
                "one of --ruling or --all is required "
                "(or pass --gate/--fix, which default the sweep to --all)"
            )

    repo = Path(args.repo).resolve()
    records = load_verdicts(repo)
    selected = _select(records, args.ruling, args.all)

    if not selected:
        which = "--all" if args.all else f"id {args.ruling!r}"
        print(f"supersede_sweep — no verdict with supersede markers matched {which}")
        print("VERDICT=PASS unstamped=0")
        return 0

    hits = sweep(repo, selected)

    print(f"supersede_sweep — {repo}")
    for rec in selected:
        print(f"  ruling {rec.get('id')} supersedes {_markers_for(rec)}")
    if hits:
        print(f"{'FILE:LINE'.ljust(28)}  MARKER  ·  EXCERPT")
        for h in hits:
            loc = f"{h['file']}:{h['line']}"
            print(f"{loc.ljust(28)}  {h['marker']}  ·  {h['excerpt']}")

    if args.fix and hits:
        touched = apply_fix(repo, hits)
        for fname in touched:
            print(f"--fix: stamped {fname}")
        hits = sweep(repo, selected)  # re-sweep: confirm the fix actually cured every citation

    if args.gate:
        files = sorted({h["file"] for h in hits})
        print(
            f"--gate: {len(hits)} unstamped citation(s)"
            + (f" across {len(files)} file(s): {', '.join(files)}" if files else " — clean")
        )

    if not hits:
        print("VERDICT=PASS unstamped=0")
    else:
        sites = ",".join(f"{h['file']}:{h['line']}" for h in hits)
        tier = "FAIL" if args.gate else "WARN"
        print(f"VERDICT={tier} unstamped={len(hits)} sites={sites}")

    return 1 if (args.gate and hits) else 0


if __name__ == "__main__":
    sys.exit(main())
