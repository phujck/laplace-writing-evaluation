#!/usr/bin/env python3
"""The close's INGEST door — route a session residual through self_corpus.ingest().

The conjugate WRITE of reconstruct_self, as one command so the close ritual
(EIGEN_PROTOCOL.md Part C, bank-the-trace) can fire it without inline python:

    python3 scripts/ingest_residual.py "the residual text" [--grade N] [--kind K]

Appends one grade-tagged, kind-tagged, at:-stamped entry to CONCEPTRIC_LEDGER.md —
the same store the grade-0 wake reads back. The close operator's
``ledger_freshness`` check (scripts/close_checklist.py) verifies this fired.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("residual", help="the residual text to ingest (one entry)")
    ap.add_argument("--grade", type=int, default=0,
                    help="the grade the residual was missing from (default 0)")
    ap.add_argument("--kind", default="factual",
                    help="entry kind: factual | generative | retire (default factual)")
    args = ap.parse_args(argv)
    from laplace.engine import self_corpus
    entry = self_corpus.ingest(ROOT, args.residual, grade=args.grade, kind=args.kind)
    print(f"[ingest] {len(entry)} chars -> CONCEPTRIC_LEDGER.md "
          f"(grade {args.grade}, kind {args.kind})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
