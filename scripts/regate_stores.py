#!/usr/bin/env python3
"""regate_stores.py — the GATE-ONLY caller for the corpus stores, and their freshness check.

The merge drivers (``merge_four_lens_residue.py``, ``merge_paragraph_plan_residue.py``) re-derive
the ROWS as well as the gate: running one to refresh a verdict would consume residue that is no
longer on disk and destroy the folded result. This caller re-runs the GATE alone — rows and
committed embeddings are read, never rewritten — and stamps the verdict with the store fingerprint
it measured, so the next re-mint makes it visibly STALE instead of quietly wrong.

Usage:
    .venv/bin/python scripts/regate_stores.py            # CHECK: freshness of every store verdict
    .venv/bin/python scripts/regate_stores.py --rewrite   # RE-DERIVE the gate verdicts + stamp

Exit code 1 on --check when any verdict is STALE or UNSTAMPED (SUPERSEDED is a declared retirement,
not an open red).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from laplace.pipeline import store_gate_freshness as F  # noqa: E402

CORPUS_STORES = _REPO_ROOT / "corpus_stores"

#: store -> the gate class its ``gate_verdict.json`` scores (the FAITHFUL model-read class).
REGATEABLE = {
    "section_architecture": "normalized_job",
    "paragraph_plan": "normalized_role",
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rewrite", action="store_true",
                    help="re-derive the gate verdicts against the current store and stamp them")
    ap.add_argument("--stores", nargs="*", default=sorted(REGATEABLE),
                    help="stores to act on (default: every re-gateable store)")
    args = ap.parse_args()

    rc = 0
    for store in args.stores:
        store_dir = CORPUS_STORES / store
        if not store_dir.is_dir():
            print(f"  {store:24} NO SUCH STORE")
            rc = 1
            continue
        if args.rewrite:
            v = F.rewrite_gate_verdict(store_dir, REGATEABLE[store])
            g = v["gate"]
            print(f"  {store:24} REGATED  eligible={v['n_eligible']} classes={v['n_classes']}  "
                  f"score={g['score']} base={g['baseline']} -> "
                  f"{'PASS' if g['passed'] else 'REFUSED'}  wired_in={v['wired_in']}  "
                  f"gated_at={v['gated_at']}")
            prev = v["regated"]["previous_gate"]
            if prev:
                print(f"  {'':24}   previous: score={prev.get('score')} base={prev.get('baseline')} "
                      f"passed={prev.get('passed')}")
        for row in F.store_freshness(store_dir):
            mark = "" if row["status"] == F.FRESH else "  <-- "
            print(f"  {store:24} {row['verdict']:32} {row['status']:10} "
                  f"gated_at={row['gated_at']}{mark}{'; '.join(row['drift'])[:160]}")
            if row["status"] in (F.STALE, F.UNSTAMPED):
                rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
