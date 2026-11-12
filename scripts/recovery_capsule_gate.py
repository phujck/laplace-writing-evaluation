#!/usr/bin/env python3
"""Verify the stage-zero Superego/Sensorium recovery capsule without live mutation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from laplace.representation.recovery_capsule_gate import rehearse_bit_flip_recovery, run_recovery_capsule_gate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, help="explicit immutable runtime custody")
    parser.add_argument(
        "--repo-root",
        default=str(ROOT),
        help="isolated migration worktree containing the recovery inputs",
    )
    parser.add_argument(
        "--rehearse-bit-flips-from",
        metavar="INDEPENDENT_CUSTODY",
        help="after a ready gate, plant blob/hive flips only in disposable copies",
    )
    args = parser.parse_args()
    result = run_recovery_capsule_gate(
        repo_root=Path(args.repo_root).resolve(),
        snapshot_root=Path(args.snapshot).resolve(),
    )
    if result.get("state") == "RECOVERY_CAPSULE_READY" and args.rehearse_bit_flips_from:
        try:
            result["bit_flip_rehearsal"] = rehearse_bit_flip_recovery(
                snapshot_root=Path(args.snapshot).resolve(),
                independent_custody_root=Path(args.rehearse_bit_flips_from).resolve(),
            )
        except Exception as exc:
            result = {
                "schema_version": "laplace.recovery-capsule-gate/1",
                "state": "RECOVERY_CAPSULE_REFUSED",
                "read_only": True,
                "refusal": {
                    "code": "BIT_FLIP_REHEARSAL_REFUSED",
                    "detail": str(exc),
                    "evidence": {"exception": type(exc).__name__},
                },
            }
    print(json.dumps(result, indent=1, sort_keys=True))
    return 0 if result.get("state") == "RECOVERY_CAPSULE_READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
