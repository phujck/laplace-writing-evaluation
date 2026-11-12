"""export_verify - verify a snapshot bundle and print its seal report.

    python -m atlas.tools.export_verify <snapshot_dir> [--no-blob-bytes]

Exits nonzero on ANY refusal, printing the named reason. This is the command a gate runs, so
it never summarises a failure as a warning: the first violation ends the run and the exit code
carries it.

With blob checking on (the default) every stored blob is re-hashed against the key it is filed
under, which is the byte-exact round-trip check. ``--no-blob-bytes`` checks presence only, for
a fast structural pass over a large bundle.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from ..errors import AtlasError
from ..snapshot import load_snapshot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="verify a snapshot bundle")
    parser.add_argument("snapshot_dir", type=Path)
    parser.add_argument("--no-blob-bytes", action="store_true",
                        help="check blob presence only, do not re-hash their bytes")
    args = parser.parse_args(argv)

    started = time.perf_counter()
    try:
        bundle = load_snapshot(args.snapshot_dir)
        report = bundle.verify(check_blob_bytes=not args.no_blob_bytes)
    except AtlasError as exc:
        print(f"REFUSED {exc}", file=sys.stderr)
        return 1
    elapsed = time.perf_counter() - started

    man = bundle.manifest
    print(f"snapshot_id             {man.snapshot_id}")
    print(f"commit_sha              {man.commit_sha}")
    print(f"created_ts              {man.created_ts}   (recorded, never hashed)")
    print(f"nodes                   {man.node_count} "
          f"({man.text_node_count} text, {man.sealed_node_count} sealed, "
          f"{man.asset_node_count} asset)")
    print(f"content_bytes           {man.total_content_bytes}")
    print(f"nodes_sha256            {man.nodes_sha256}")
    print(f"tree_dirty              {man.tree_dirty} ({man.dirty_node_count} nodes) "
          f"{man.dirty_nodes_hash}")
    if man.tree_dirty:
        print("                        NOT rebuildable from commit_sha alone; the delta is "
              "named by dirty_nodes_hash")
    print("-- seal report --")
    # Width is computed, not guessed: the laundered-leak keys are long enough to collide with
    # a fixed column and a report read as evidence must not run its keys into its values.
    width = max((len(k) for k in report), default=0) + 2
    for key in sorted(report):
        value = report[key]
        if key == "sealed_path_ref_top":
            print(f"{key:<{width}}{len(value)} nodes, highest first:")
            for item in value:
                print(f"{'':<{width}}  {item['refs']:>6}  {item['node_id']}")
            continue
        print(f"{key:<{width}}{value}")
    if bundle.has_spans():
        seg = bundle.segmentation()
        if seg:
            print("-- segmentation --")
            for key in ("generation_id", "target_tokens", "hard_cap_tokens", "span_count",
                        "leaf_span_count", "coverage", "oversize_spans"):
                print(f"{key:<24}{seg.get(key)}")
    else:
        print("spans                   (none - run atlas.tools.build_spans)")
    print(f"VERIFIED in {elapsed:.2f}s "
          f"({'blob bytes re-hashed' if not args.no_blob_bytes else 'blob presence only'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
