#!/usr/bin/env python3
"""Audit or retire only Eigen-owned Codex provider attention submissions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from laplace.representation.codex_seat_watcher import retire_current_provider_attention  # noqa: E402
from laplace.representation.provider_queue import audit_thread  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    audit = subparsers.add_parser("audit")
    audit.add_argument("--thread", required=True)
    retire = subparsers.add_parser("retire")
    retire.add_argument("--thread", required=True)
    retire.add_argument("--seat", required=True)
    args = parser.parse_args(argv)

    if args.command == "audit":
        receipt = audit_thread(thread_id=args.thread)
    else:
        receipt = retire_current_provider_attention(
            seat_id=args.seat,
            thread_id=args.thread,
        )
    print(json.dumps(receipt, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
