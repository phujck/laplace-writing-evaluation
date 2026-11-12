"""propagate.py — print the minimal propagation report for a project.

Thin CLI over ``laplace.pipeline.propagate.propagate`` (P3): dirty sections
classified cheap/expensive, the typed worklist DAG, comment routing and the
minimum dispatch set. Pure read — nothing is written; dispatch (P4) executes.

    python scripts/propagate.py <project> [--since <mark>] [--no-feedback]

``<project>`` defaults through the registry (active project, else the corpus
whose friction ledger moved most recently). ``--since`` takes either a byte
offset (a transaction/freeze mark) or an L1 record id — see
``changeset_since``; omit it to skip the change-set leg.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from laplace.pipeline import propagate as prop  # noqa: E402
from laplace.pipeline import registry           # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Minimal propagation report (pure read).")
    ap.add_argument("project", nargs="?", default=None,
                    help="registered project name (default: the active project)")
    ap.add_argument("--since", default=None,
                    help="L1 mark: byte offset or record id (omit = no change-set leg)")
    ap.add_argument("--no-feedback", action="store_true",
                    help="skip the intake/feedback ledger")
    args = ap.parse_args(argv)
    project = args.project or registry.default_project()
    try:
        report = prop.propagate(project, since=args.since,
                                feedback=not args.no_feedback)
    except ValueError as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
