#!/usr/bin/env python3
"""Verify the exact Atlas recovery coordinate against its live authority axes."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from laplace.representation.recovery_coordinate import DEFAULT_COORDINATE, canonical_payload_digest, verify_coordinate, verify_runtime_recovery_point


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("coordinate", nargs="?", default=str(DEFAULT_COORDINATE))
    parser.add_argument(
        "--offline-capsule",
        help="verify one custody capsule against the coordinate-carried recovery point",
    )
    parser.add_argument(
        "--offline-point",
        help="optional JSON file containing the exact runtime_recovery_point object",
    )
    parser.add_argument(
        "--skip-blueprint",
        action="store_true",
        help="omit the expensive blueprint projection; result cannot certify current custody",
    )
    args = parser.parse_args()
    if args.offline_point and not args.offline_capsule:
        parser.error("--offline-point requires --offline-capsule")
    if args.offline_capsule:
        coordinate = json.loads(Path(args.coordinate).read_text(encoding="utf-8"))
        if canonical_payload_digest(coordinate) != coordinate.get("coordinate_payload_digest"):
            raise ValueError("offline recovery coordinate payload digest does not verify")
        point = (
            json.loads(Path(args.offline_point).read_text(encoding="utf-8"))
            if args.offline_point
            else coordinate.get("runtime_recovery_point")
        )
        if not isinstance(point, dict):
            raise ValueError("offline recovery coordinate has no runtime_recovery_point")
        result = verify_runtime_recovery_point(point, args.offline_capsule)
        result["coordinate_payload_digest"] = coordinate["coordinate_payload_digest"]
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 0
    result = verify_coordinate(args.coordinate, include_blueprint=not args.skip_blueprint)
    print(json.dumps(result, ensure_ascii=False, indent=1))
    if result["coordinate_state"] == "CURRENT-FOR-RECOVERY":
        return 0
    return 2 if result["coordinate_state"] in {
        "SUPERSESSION-REQUIRED", "SUPERSEDED"
    } else 1


def cli() -> int:
    try:
        return main()
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(json.dumps({
            "schema_version": "atlas.recovery-coordinate-refusal/1",
            "coordinate_state": "INVALID",
            "custody_allowed": False,
            "refused": True,
            "residue": {
                "code": "COORDINATE_SOURCE_REFUSED",
                "message": str(exc),
                "exception_type": type(exc).__name__,
            },
        }, ensure_ascii=False, indent=1))
        return 1


if __name__ == "__main__":
    raise SystemExit(cli())
