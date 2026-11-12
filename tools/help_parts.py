"""Where the characters of a generated help response go, by part.

    scripts/laplace-python tools/help_parts.py --project synthetics-foundations --root .

So that "help got smaller" is never a claim about one number: the parts are printed
and they sum to the total the same instrument (tools/measure_help.py) reports.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default="")
    parser.add_argument("--root", default="")
    args = parser.parse_args(argv)
    sys.path.insert(0, str(Path("src").resolve()))
    from laplace.writing import reads
    from laplace.native.declarations import help_payload

    def size(value) -> int:
        return len(json.dumps(value, ensure_ascii=False, default=str))

    parts: dict[str, int] = {}
    total = 0
    for operation in sorted(reads.READS | reads.WRITES):
        action = help_payload(operation, permitted=True, project=args.project,
                             root=args.root or None)
        total += size(action)
        for key, value in action.items():
            parts[key] = parts.get(key, 0) + size({key: value}) - 2
    print(json.dumps({"action_total": total,
                      "by_part": dict(sorted(parts.items(), key=lambda kv: -kv[1]))},
                     indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
