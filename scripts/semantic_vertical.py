#!/usr/bin/env python3
"""Capture the canonical operational sources consumed by a full vertical semantic fold."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from laplace.representation.embedding_health import build_manifest, build_reachability_witnesses
from laplace.representation.semantic_vertical import capture  # noqa: E402
from laplace.engine.turn_reconstruction import build_heads  # noqa: E402


def _profiles(values: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for value in values:
        function, separator, handle = value.partition("=")
        if not separator or not function or not handle.startswith("sha256:"):
            raise ValueError("--profile must be function=sha256:...")
        out[function] = handle
    if set(out) != {"ego", "aisthesis", "superego"}:
        raise ValueError("exactly ego, aisthesis and superego profiles are required")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--profile", action="append", default=[])
    parser.add_argument("--goal-context", required=True)
    parser.add_argument("--source-tuple-json", required=True)
    parser.add_argument("--finalize", action="store_true")
    parser.add_argument("--cadence-json", default="")
    args = parser.parse_args(argv)
    profiles = _profiles(args.profile)
    repo_root = Path(args.repo_root)
    if args.finalize:
        cadence = (
            json.loads(Path(args.cadence_json).read_text(encoding="utf-8"))
            if args.cadence_json
            else {
                "schema_version": "laplace.semantic-fold-cadence-plan/1",
                "mode": "automatic-isolated-successor",
                "deduplicated": True,
            }
        )
        witnesses = build_reachability_witnesses(repo_root)
        manifest = build_manifest(repo_root, witnesses=witnesses, cadence=cadence)
        print(json.dumps(
            {"manifest": manifest, "witnesses": witnesses},
            ensure_ascii=False, sort_keys=True, indent=2,
        ))
        return 0
    source_tuple = json.loads(
        Path(args.source_tuple_json).read_text(encoding="utf-8")
    )
    coverage = capture(
        repo_root, profile_handles=profiles, source_tuple=source_tuple
    )
    goal_context = json.loads(Path(args.goal_context).read_text(encoding="utf-8"))
    heads = build_heads(
        repo_root,
        profile_handles=profiles,
        goal_context=goal_context,
        seat_generations=coverage.get("seat_generations") or {},
    )
    print(json.dumps(
        {"coverage": coverage, "seat_context_heads": heads},
        ensure_ascii=False, sort_keys=True, indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
