#!/usr/bin/python3
"""THE PROBE, thin CLI — measure a fresh session's accumulation and bank one row.

The instrument is the organ ``laplace.engine.probe``; this file only parses argv and prints.

    /usr/bin/python3 scripts/probe_fresh_session.py [--repo PATH] [--tag TAG]
                                                    [--repeat N] [--no-bank] [--json]
                                                    [--prune [--apply]]

It MEASURES; it never gates. Exit is 0 whenever the probe itself ran, whatever the
phases did — a phase's rc is a column of the row, not a verdict of this process.
The only nonzero exits are the probe failing to run at all (usage, clone failure).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from laplace.engine import probe as P  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=str(ROOT), help="tree to clone cold (default: this repo)")
    ap.add_argument("--tag", default=None, help="free-text label banked on the row")
    ap.add_argument("--repeat", type=int, default=1,
                    help="run the phase sequence in N INDEPENDENT COLD CLONES (one "
                         "scratch subdir each); the row gains a cold-vs-cold "
                         "per-column min/max/mean spread")
    ap.add_argument("--no-bank", action="store_true", help="print the row, append nothing")
    ap.add_argument("--json", action="store_true", help="print the row as JSON, not a summary")
    ap.add_argument("--timeout", type=int, default=P.DEFAULT_TIMEOUT_S,
                    help="the single generous subprocess bound, banked on the row")
    ap.add_argument("--scratch-root", default=None,
                    help="where the disposable clone is made (default: the system temp root)")
    ap.add_argument("--prune", action="store_true",
                    help="content-keyed retention over the store (latest per "
                         "head+tag+interpreter, plus every referenced id); prints the plan")
    ap.add_argument("--apply", action="store_true", help="with --prune: rewrite the store")
    args = ap.parse_args(argv)

    if args.prune:
        plan = P.prune(args.repo, apply=args.apply)
        print(json.dumps(plan, indent=1) if args.json else
              f"prune rows={plan['rows']} kept={plan['kept']} dropped={plan['dropped']} "
              f"by_reference={len(plan['kept_by_reference'])} applied={plan['applied']}")
        return 0

    row = P.probe_run(args.repo, tag=args.tag, repeat=args.repeat,
                      timeout=args.timeout, scratch_root=args.scratch_root)
    if not args.no_bank:
        P.bank(row, root=args.repo)   # bank() stamps row["banked_via"] before writing
    print(json.dumps(row, ensure_ascii=False, indent=1) if args.json else P.summarize(row))
    if not args.no_bank:
        print(f"  banked -> {Path(args.repo).resolve() / P.STORE} "
              f"via {row.get('banked_via')}")
    return 1 if row.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
