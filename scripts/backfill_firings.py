"""Backfill the spine's learned feed from existing telemetry - closing the loop without
waiting for organic fires (2026-07-12: diagnosed that ``scanner_firings.jsonl``, the file
``spine.learned_top`` reads, was gated behind a live scanner dev-server that is rarely
running - see ``spine.record_firing`` and ``scanner._bank_firing`` for the fix to the writer
going forward). Every real fire ALREADY banks durably to telemetry, unconditionally and
in-process, via ``telemetry.reconstruction(target=goal, nodes=[...])`` - regardless of
whether the scanner's HTTP ``/fire`` ring ever saw it. This script replays those events
through ``spine.record_firing`` (the one writer), converting ``target`` -> ``goal`` and
``activated`` -> ``fired`` so the learned half is not starting from zero the moment the
writer is fixed.

Idempotent: dedupes on ``(ts, goal)`` against what is already in the firings feed, so
re-running after new telemetry accrues (or after a previous partial run) only appends what
is genuinely new - never a second copy of an event already backfilled.

  python scripts/backfill_firings.py [--dry-run] [--repo-root PATH]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from laplace.engine import spine, telemetry  # noqa: E402


def _candidates() -> list[dict]:
    """Every telemetry event that carries a goal (``target``) and the nodes it fired
    (``activated``) - the shape a firing needs, regardless of which caller banked it
    (``scanner``, ``scanner-ring``, ``eigen``, ``shard``, ...). Events missing either
    field carry no reconstructable goal->nodes binding, so they are skipped, not guessed."""
    out = []
    for ev in telemetry.events():
        if ev.get("phase") != "reconstruction":
            continue
        goal = ev.get("target", "")
        nodes = ev.get("activated", [])
        if not goal or not nodes:
            continue
        out.append(ev)
    return out


def backfill(repo_root: Path, *, dry_run: bool = False) -> dict:
    """Replay telemetry into the firings feed. Returns counts: scanned candidates, already
    present (skipped), newly written. ``dry_run`` computes the same counts without writing."""
    existing = spine._firings(repo_root)                       # noqa: SLF001 - same package, the reader
    seen = {(fr.get("ts", ""), fr.get("goal", "")) for fr in existing}

    candidates = _candidates()
    written = 0
    skipped = 0
    for ev in candidates:
        key = (ev.get("ts", ""), ev.get("target", ""))
        if key in seen:
            skipped += 1
            continue
        seen.add(key)                                          # guards dupes within this run too
        fired = [{"id": nid} for nid in ev.get("activated", []) if nid]
        if not dry_run:
            spine.record_firing(repo_root, ev["target"], fired, ts=ev.get("ts"),
                                extra={"backfilled": True, "caller": ev.get("caller", "")})
        written += 1

    return {"scanned": len(candidates), "already_present": skipped, "written": written}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", default=str(ROOT))
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be written without touching the firings file")
    a = ap.parse_args()

    repo_root = Path(a.repo_root)
    result = backfill(repo_root, dry_run=a.dry_run)
    label = "would write" if a.dry_run else "written"
    print(f"telemetry events scanned (goal+nodes): {result['scanned']}")
    print(f"already in firings feed (skipped):     {result['already_present']}")
    print(f"{label}: {result['written']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
