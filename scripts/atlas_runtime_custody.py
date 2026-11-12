#!/usr/bin/env python3
"""Explicit custody door for the live Atlas seat fabric.

Nothing runs without a destination or an existing snapshot to verify.  Export uses SQLite's
online backup API, carries exact content-addressed bodies and event hives, reconstructs the copy,
and atomically publishes it only after verification.  A second filesystem is reported as such;
the tool never guesses that a path is off-machine.

    /usr/bin/python3 scripts/atlas_runtime_custody.py --export /chosen/snapshot/path
    /usr/bin/python3 scripts/atlas_runtime_custody.py --verify /chosen/snapshot/path
    /usr/bin/python3 scripts/atlas_runtime_custody.py --adopt-writable /chosen/snapshot/path \
        --destination /canonical/runtime/path --recovery-coordinate /committed/coordinate.json \
        --expected-snapshot-id sha256:... --expected-grant-root sha256:...
    /usr/bin/python3 scripts/atlas_runtime_custody.py --verify-writable /chosen/snapshot/path \
        --expected-snapshot-id sha256:...
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from laplace.representation import atlas_bridge  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--export", metavar="DESTINATION")
    action.add_argument("--verify", metavar="SNAPSHOT")
    action.add_argument("--adopt-writable", metavar="SNAPSHOT")
    action.add_argument("--verify-writable", metavar="SNAPSHOT")
    action.add_argument("--derive-grant", metavar="SNAPSHOT")
    parser.add_argument("--expected-snapshot-id")
    parser.add_argument("--expected-grant-root")
    parser.add_argument("--destination")
    parser.add_argument("--recovery-coordinate")
    parser.add_argument(
        "--admit-declared-historical-unavailable",
        action="store_true",
        help=(
            "during export only, admit the exact tracked legacy terminal-REFUSED "
            "message-body residual set"
        ),
    )
    args = parser.parse_args()

    if args.export:
        if args.expected_snapshot_id:
            parser.error("export mints the snapshot id; it cannot accept an expected id")
        result = atlas_bridge.export_runtime_custody(
            destination=args.export,
            admit_declared_historical_unavailable=(
                args.admit_declared_historical_unavailable
            ),
        )
    elif args.verify:
        if args.admit_declared_historical_unavailable:
            parser.error("residual admission is an explicit export act, not a verify switch")
        result = atlas_bridge.verify_runtime_custody(args.verify)
        if (
            args.expected_snapshot_id is not None
            and result["snapshot_id"] != args.expected_snapshot_id
        ):
            parser.error("verified snapshot id disagrees with --expected-snapshot-id")
    elif args.derive_grant:
        if not args.destination or not args.recovery_coordinate:
            parser.error("grant derivation requires --destination and --recovery-coordinate")
        result = atlas_bridge.runtime_custody_adoption_grant(
            args.derive_grant,
            destination=args.destination,
            recovery_coordinate=args.recovery_coordinate,
        )
    else:
        if args.admit_declared_historical_unavailable:
            parser.error("residual admission is an explicit export act")
        if not args.expected_snapshot_id or not args.expected_grant_root:
            parser.error(
                "writable adoption and verification require --expected-snapshot-id and "
                "--expected-grant-root"
            )
        if args.adopt_writable:
            if not args.destination or not args.recovery_coordinate:
                parser.error(
                    "writable adoption requires --destination and --recovery-coordinate"
                )
            result = atlas_bridge.adopt_runtime_custody(
                args.adopt_writable,
                destination=args.destination,
                recovery_coordinate=args.recovery_coordinate,
                expected_snapshot_id=args.expected_snapshot_id,
                expected_grant_root=args.expected_grant_root,
            )
        else:
            result = atlas_bridge.verify_writable_runtime_custody(
                args.verify_writable,
                expected_snapshot_id=args.expected_snapshot_id,
                expected_grant_root=args.expected_grant_root,
            )
    print(json.dumps(result, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
