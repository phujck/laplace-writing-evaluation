#!/usr/bin/env python3
"""Run one bounded authority-free lifecycle rehearsal."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from laplace.engine.lifecycle_rehearsal import RehearsalRefused, run_faithful_lifecycle_rehearsal


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--candidate-commit", required=True)
    parser.add_argument("--candidate-tree", required=True)
    parser.add_argument("--provider-history", required=True, type=Path)
    parser.add_argument("--canonical-atlas-root", required=True, type=Path)
    parser.add_argument("--blueprint-root", required=True, type=Path)
    parser.add_argument("--live-provider-root", required=True, type=Path)
    parser.add_argument("--live-watcher-root", required=True, type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        result = run_faithful_lifecycle_rehearsal(
            repo_root=args.repo_root,
            candidate_commit=args.candidate_commit,
            candidate_tree=args.candidate_tree,
            provider_history_path=args.provider_history,
            canonical_atlas_root=args.canonical_atlas_root,
            blueprint_root=args.blueprint_root,
            live_provider_root=args.live_provider_root,
            live_watcher_root=args.live_watcher_root,
        )
    except RehearsalRefused as exc:
        print(
            json.dumps(
                {
                    "schema_version": "laplace.faithful-lifecycle-rehearsal-refusal/1",
                    "status": "REFUSED",
                    "reason": exc.reason,
                    "evidence": exc.evidence,
                    "publication_authority": False,
                },
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
