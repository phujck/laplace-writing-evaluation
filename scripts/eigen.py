"""Provider-neutral standing Eigen authority, emergency bank, and bounded triage."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from laplace.engine import eigen_authority as eigen  # noqa: E402
from laplace.core.runtime import require_system_runtime  # noqa: E402

require_system_runtime(ROOT)


def _holder(value: str) -> str:
    return value.strip() or eigen.inferred_holder_ref()


def _payload(args: argparse.Namespace) -> dict:
    if args.payload_file:
        value = json.loads(Path(args.payload_file).read_bytes())
    elif args.payload_json:
        value = json.loads(args.payload_json)
    else:
        value = {}
    if not isinstance(value, dict):
        raise eigen.EigenAuthorityRefused("bank payload must be one JSON object")
    return value


def _transcript(value: str, task_id: str) -> str:
    if value != "auto":
        return value
    session_root = Path.home() / ".codex" / "sessions"
    matches = sorted(session_root.glob(f"*/*/*/*{task_id}*.jsonl"))
    if len(matches) != 1:
        raise eigen.EigenAuthorityRefused(
            f"automatic transcript discovery requires exactly one task match; found {len(matches)}"
        )
    return str(matches[0])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT))
    sub = parser.add_subparsers(dest="command", required=True)

    authority = sub.add_parser("authority")
    authority.add_argument("--holder", default="")

    adopt = sub.add_parser("adopt")
    adopt.add_argument("--holder", default="")
    adopt.add_argument("--task-id", required=True)
    adopt.add_argument("--transcript", default="auto")
    adopt.add_argument("--commission-file")

    bank = sub.add_parser("bank")
    bank.add_argument("--holder", default="")
    bank.add_argument("--kind", required=True)
    bank.add_argument("--act-id", required=True)
    bank.add_argument("--reason", required=True)
    bank.add_argument("--payload-file")
    bank.add_argument("--payload-json")

    reconcile = sub.add_parser("reconcile")
    reconcile.add_argument("--holder", default="")

    triage = sub.add_parser("triage")
    triage.add_argument("--holder", default="")

    check = sub.add_parser("check-act")
    check.add_argument("--holder", default="")
    check.add_argument("--operation", required=True)

    sub.add_parser("journal")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    try:
        if args.command == "authority":
            result = eigen.observe_authority(root, holder_ref=_holder(args.holder))
        elif args.command == "adopt":
            result = eigen.adopt(
                root,
                holder_ref=_holder(args.holder),
                task_id=args.task_id,
                transcript_path=_transcript(args.transcript, args.task_id),
                commission_path=args.commission_file,
            )
        elif args.command == "bank":
            result = eigen.bank(
                root,
                kind=args.kind,
                act_id=args.act_id,
                holder_ref=_holder(args.holder),
                reason=args.reason,
                payload=_payload(args),
            )
        elif args.command == "reconcile":
            result = eigen.reconcile(root, holder_ref=_holder(args.holder))
        elif args.command == "triage":
            result = eigen.triage(root, holder_ref=_holder(args.holder))
        elif args.command == "check-act":
            result = eigen.check_operation(
                root, holder_ref=_holder(args.holder), operation=args.operation
            )
        else:
            result = eigen.read_journal()
    except eigen.EigenAuthorityRefused as exc:
        result = {
            "schema_version": "laplace.eigen-cli-refusal/1",
            "status": "REFUSED",
            "reason": str(exc),
        }
    print(json.dumps(result, sort_keys=True, indent=1))
    return 0 if result.get("status") not in {"REFUSED", "UNKNOWN"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
