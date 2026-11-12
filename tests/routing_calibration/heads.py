"""Deposit the two advisor heads as JSONL, the shape the live seams read.

    scripts/laplace-python tests/routing_calibration/heads.py \
        --labels /tmp/jev-routing/labels.json --out <evidence>/heads

The seams in `src/laplace/native/tools.py` fit their head from a file named by
`LAPLACE_ROUTING_HEAD_D1` / `LAPLACE_ROUTING_HEAD_D4`, so the head a door uses is a
deposit a reader can inspect and refit, never a pickle and never training inside a
door.  Both files are the labelled rows themselves, which is what makes the advisor
auditable: the fit is reproducible from the rows and the rows are derived from the
corpus by `labels.py`.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", default="/tmp/jev-routing/labels.json")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    data = json.loads(Path(args.labels).read_text())
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    d1 = out / "d1.jsonl"
    d1.write_text("\n".join(json.dumps({"state": r["state"], "label": r["label"]},
                                       sort_keys=True) for r in data["d1"]) + "\n")
    d4 = out / "d4.jsonl"
    d4.write_text("\n".join(json.dumps({"error": r["error"], "label": r["label"]},
                                       sort_keys=True) for r in data["d4"]) + "\n")
    print("d1 head rows", len(data["d1"]), "->", d1)
    print("d4 head rows", len(data["d4"]), "->", d4)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
