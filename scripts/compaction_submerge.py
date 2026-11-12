#!/usr/bin/env python3
"""Seal a PreCompact successor profile or authorize its cold continuation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from laplace.engine.compaction_submergence import ContinuationRefused, reconstruct_cold_successor, seal_precompact


def _inertia(args: argparse.Namespace) -> dict[str, int | float]:
    return {
        "coordination_layer_count": args.coordination_layers,
        "author_command_to_productive_act_ms": args.author_latency_ms,
        "reconstructions": args.reconstructions,
        "subprocesses": args.subprocesses,
        "tokens": args.tokens,
        "review_cycles": args.review_cycles,
        "uniquely_caught_faults": args.uniquely_caught_faults,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="compaction-submerge")
    parser.add_argument("--repo-root", default=str(Path.cwd()))
    sub = parser.add_subparsers(dest="command", required=True)

    pre = sub.add_parser("precompact")
    pre.add_argument("--function", choices=("ego", "sensorium", "superego"), required=True)
    pre.add_argument("--seat", required=True)
    pre.add_argument("--generation", required=True)
    pre.add_argument("--lease", action="append", default=[], required=True)
    pre.add_argument("--obligation", action="append", default=[])
    pre.add_argument("--goal-context")
    pre.add_argument("--goal-context-handle")
    pre.add_argument("--goal-context-bytes", type=int)
    pre.add_argument("--coordination-layers", type=int, default=1)
    pre.add_argument("--author-latency-ms", type=float, default=0.0)
    pre.add_argument("--reconstructions", type=int, default=6)
    pre.add_argument("--subprocesses", type=int, default=1)
    pre.add_argument("--tokens", type=int, default=0)
    pre.add_argument("--review-cycles", type=int, default=0)
    pre.add_argument("--uniquely-caught-faults", type=int, default=0)

    cold = sub.add_parser("cold-successor")
    cold.add_argument("--profile", required=True)
    cold.add_argument("--function", choices=("ego", "sensorium", "superego"), required=True)
    cold.add_argument("--seat", required=True)
    cold.add_argument("--generation", required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "precompact":
            receipt = seal_precompact(
                repo_root=args.repo_root,
                function=args.function,
                seat_id=args.seat,
                generation=args.generation,
                lease_ids=args.lease,
                inertia=_inertia(args),
                extra_obligations=args.obligation,
                goal_context_path=args.goal_context,
                goal_context_handle=args.goal_context_handle,
                goal_context_bytes=args.goal_context_bytes,
            )
        else:
            receipt = reconstruct_cold_successor(
                repo_root=args.repo_root,
                profile_handle=args.profile,
                function=args.function,
                seat_id=args.seat,
                generation=args.generation,
            )
    except ContinuationRefused as exc:
        print(
            json.dumps(
                {
                    "schema_version": "laplace.cold-successor-refusal/1",
                    "status": "REFUSED",
                    "tools_enabled": False,
                    "reason": exc.reason,
                    "divergence": exc.divergence,
                },
                ensure_ascii=False,
                indent=1,
            )
        )
        return 2
    print(json.dumps(receipt, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
