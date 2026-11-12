#!/usr/bin/env python3
"""Render the provider-neutral seat fabric from the canonical ConceptricStore."""

from __future__ import annotations

import argparse
import json
import sys

from atlas.errors import AtlasError

from .journal_face import project_store, render_seat_fabric_text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", required=True, help="canonical ConceptricStore root")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--require-green", action="store_true")
    args = parser.parse_args(argv)
    try:
        projection = project_store(args.store)
    except (AtlasError, OSError, ValueError) as exc:
        print(f"sensorium provider projection refused: {exc}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps(projection, sort_keys=True, separators=(",", ":")))
    else:
        print(render_seat_fabric_text(projection), end="")
    return 1 if args.require_green and projection["status"] != "GREEN" else 0


if __name__ == "__main__":
    raise SystemExit(main())
