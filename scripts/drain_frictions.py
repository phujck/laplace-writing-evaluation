#!/usr/bin/env python3
"""drain_frictions.py — drain (never apply) the unified friction channel.

    drain_frictions.py [--ledger PATH] [--out DIR] [--migrate]

Reads ``corpus_friction/laplace_engine.jsonl`` (or ``--ledger``), routes every
open friction/fork record out one of the three exits (delegate to a manuscript
queue / draft ``evolutions_engine/<date>/FIX_PROPOSALS.md`` / draft an
OPEN_STACK row), emits the ledger digest ``<ledger>.digest.md`` (the fold
projection), flags evidence-less resolutions, prints a JSON summary
``{"drafted": [...], "escalated": [...], ...}`` and exits 0 (2 on a usage
error). DRAFT-ONLY: there is no apply flag — the author ratifies each
FIX_PROPOSALS section; the gate on an applied engine bite is SUITE + JUDGE, and
consumption is a later evidence-carrying resolution record, never written here.

``--migrate`` runs the §1b seed correction instead (supersede re-pours,
``where`` → ``target``, append-only) and prints its summary.

``--report`` runs the REPORT HALF ALONE — PURE, never writes (no digest, no
``FIX_PROPOSALS``; those are the drain's draft half, ratified by the author).
It prints a JSON reading: open/consumed friction counts on the ledger, plus the
tally of findings that exist SOLELY as raw FEEDBACK appends (loop-tier reader
replies that rode a manuscript ``feedback/feedback.jsonl`` without ever passing
through the structured pour door). This is the half the close ritual surfaces —
the reporter-law separation: the close reads, it never drains.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# repo-root on sys.path so ``laplace`` imports whether run as a script or -m
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from laplace.pipeline import friction_consumer as consumer  # noqa: E402
from laplace.pipeline.ledger import read_jsonl  # noqa: E402


# ---------------------------------------------------------------------------
# the REPORT half (pure — never writes; the half the close ritual surfaces)
# ---------------------------------------------------------------------------

def _feedback_raw_appends(root: Path) -> list[dict]:
    """Findings that exist SOLELY as raw FEEDBACK appends: entries in a
    manuscript feedback ledger (glob ``**/feedback/feedback.jsonl`` under
    ``root``) that never passed through the structured pour door. Every poured
    finding / adjudication row carries a ``record`` stamp; a raw loop-tier reply
    (``{where, issue, fix}``, or an unparseable scrawl) does not — that MISSING
    stamp is the discriminant. One entry per feedback ledger holding any, with
    its raw-append count. READ-ONLY."""
    out: list[dict] = []
    for fb in sorted(root.glob("**/feedback/feedback.jsonl")):
        raw = 0
        try:
            lines = fb.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for ln in lines:
            ln = ln.strip()
            if not ln:
                continue
            try:
                obj = json.loads(ln)
            except json.JSONDecodeError:
                raw += 1  # an unparseable scrawl is, a fortiori, not a poured row
                continue
            if isinstance(obj, dict) and not str(obj.get("record") or "").strip():
                raw += 1
        if raw:
            try:
                rel = str(fb.relative_to(root))
            except ValueError:
                rel = str(fb)
            out.append({"file": rel, "raw_appends": raw})
    return out


def report(ledger: Path | str, root: Path | str) -> dict:
    """The drain's REPORT half — PURE, never writes. open/consumed friction
    counts on ``ledger`` (via the friction_consumer pure query organs) + the
    raw-FEEDBACK-only finding tally across the manuscript feedback ledgers under
    ``root``. Tolerant of a missing ledger (reports 0 open / 0 consumed) so the
    close's drain beat is a self-contained reading, never a usage error."""
    ledger = Path(ledger)
    records = read_jsonl(ledger) if ledger.is_file() else []
    raw = _feedback_raw_appends(Path(root))
    return {
        "ledger": str(ledger),
        "ledger_found": ledger.is_file(),
        "open": len(consumer.open_frictions(records)),
        "consumed": len(consumer.consumed_frictions(records)),
        "feedback_raw_appends": raw,
        "feedback_raw_append_total": sum(e["raw_appends"] for e in raw),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="drain_frictions.py",
        description="Drain (never apply) the open friction/fork records of the "
                    "unified friction channel.")
    ap.add_argument("--ledger", default="",
                    help="the friction ledger (default: "
                         "corpus_friction/laplace_engine.jsonl)")
    ap.add_argument("--out", default="",
                    help="where evolutions_engine/ lands (default: the repo root)")
    ap.add_argument("--migrate", action="store_true",
                    help="run the seed migration (where→target supersede "
                         "re-pours) instead of the drain")
    ap.add_argument("--report", action="store_true",
                    help="run the REPORT half ALONE (pure, never writes): "
                         "open/consumed counts + the raw-FEEDBACK-only finding "
                         "tally, as JSON — the half the close ritual surfaces")
    ap.add_argument("--root", default="",
                    help="root to scan for feedback ledgers under --report "
                         "(default: the repo root)")
    try:
        args = ap.parse_args(argv)
    except SystemExit:
        return 2

    repo_root = Path(__file__).resolve().parents[1]
    ledger = Path(args.ledger) if args.ledger else (
        repo_root / "corpus_friction" / "laplace_engine.jsonl")

    if args.report:
        root = Path(args.root) if args.root else repo_root
        print(json.dumps(report(ledger, root), indent=2, ensure_ascii=False))
        return 0

    if not ledger.is_file():
        print(f"usage error: friction ledger not found: {ledger}", file=sys.stderr)
        return 2

    if args.migrate:
        summary = consumer.migrate_where_records(ledger)
    else:
        summary = consumer.drain(repo_root, ledger,
                                 Path(args.out) if args.out else None)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
