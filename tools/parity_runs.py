#!/usr/bin/env python3
"""One line per banked parity run: commit, rows, verdict, seconds, kinds.

    scripts/laplace-python tools/parity_runs.py <parity dir> [<parity dir> ...]
"""

from __future__ import annotations

import json
import pathlib
import sys


def main(argv: list[str]) -> int:
    for raw in argv:
        path = pathlib.Path(raw) / "parity.json"
        if not path.is_file():
            print("%-30s MISSING" % raw)
            continue
        d = json.loads(path.read_text(encoding="utf-8"))
        rows = sum(v["rows"] for v in d["by_source"].values())
        print("%-10s new=%s old=%s rows=%d parity=%s unallowed=%s seconds=%.0f kinds=%s"
              % (pathlib.Path(raw).parent.name, d["new"]["head"][:8], d["old"]["head"][:8],
                 rows, d["parity"], d["rows_unallowed"], d["seconds"],
                 d["difference_by_kind"]))
        print("           by_source=%s by_door=%s"
              % ({k: (v["rows"], v["parity"]) for k, v in d["by_source"].items()},
                 {k: (v["rows"], v["parity"]) for k, v in d["by_door"].items()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
