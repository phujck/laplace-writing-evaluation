#!/usr/bin/env python3
"""device_proof.py - the hand device-proof runner that CANNOT forge the census.

WO-20260821-proof-rows-forge-the-census, cure (b) - house discipline made mechanical:
``device_policy._provenance`` already marks suite rows ``synthetic`` (C4's cure), but a
HAND proof - ``python3 -c`` under a deliberately broken interpreter, the Enforce lane's
case B - writes a row byte-indistinguishable from a production run that genuinely lost
its device (proc '-c', synthetic false). One such row sits in .fallback_events.jsonl:96
(2026-08-21T05:46:54, fold-spectral, cupy missing), named in the order and in
evidence/REQUIRE_GPU_DEFAULT_2026-08-21/RUN.md section 6 so censuses subtract it.

This wrapper is the door: EVERY hand device proof runs through it, and it ALWAYS forces
``LAPLACE_FALLBACK_LOG`` to a sink - the proof's fallback rows land beside the proof
(printed in the report, keepable as evidence) and structurally CANNOT reach the repo's
census store. The same isolation door tests/conftest.py holds for the suite, held here
for the hand. A proof run without this wrapper is the defect class, not a proof.

Usage:
    python3 scripts/device_proof.py -- <command ...>
    python3 scripts/device_proof.py --sink /path/to/sink.jsonl -- <command ...>

Prints one JSON report {command, exit, sink, rows} and exits with the command's code.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main(argv: list[str]) -> int:
    sink: str | None = None
    if argv and argv[0] == "--sink":
        sink = argv[1]
        argv = argv[2:]
    if not argv or argv[0] != "--":
        print(__doc__, file=sys.stderr)
        return 2
    cmd = argv[1:]
    if not cmd:
        print("device_proof: no command after --", file=sys.stderr)
        return 2
    if sink is None:
        fd, sink = tempfile.mkstemp(prefix="device_proof_", suffix=".jsonl")
        os.close(fd)
    sink_path = Path(sink).resolve()

    env = dict(os.environ)
    env["LAPLACE_FALLBACK_LOG"] = str(sink_path)   # the door: always, no opt-out
    r = subprocess.run(cmd, env=env)

    rows: list[dict] = []
    try:
        for line in sink_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    rows.append({"unparseable": line[:200]})
    except OSError:
        pass
    print(json.dumps({"command": cmd, "exit": r.returncode,
                      "sink": str(sink_path), "rows": rows}, indent=1))
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
