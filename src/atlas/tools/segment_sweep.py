"""segment_sweep - the span-size sweep. Measures, prints, writes nothing.

    python -m atlas.tools.segment_sweep <snapshot_dir> [--sizes 256,384,512] [--limit N]

For each target span size it reports, over the chosen slice of the snapshot: span count,
coverage, oversize count, p50/p90 leaf span tokens, and - only when a real encoder is actually
available - embedding wall-clock over a bounded sample of spans.

What this sweep can and cannot decide. It measures the SHAPE of the segmentation: how many
spans a size produces, how the span-size distribution sits against the encoder window, and what
it costs to embed them. It cannot say which size retrieves better; that read needs the bench and
its tasks, which is Phase 2's work. The output says so, so nobody quotes a span count as a
quality number.

The encoder timing arm is skipped LOUDLY when the model is not reachable - a printed line
naming what was missing, never a silently absent row.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from ..errors import AtlasError
from ..segment import HARD_CAP_TOKENS, SWEEP_TARGETS, segment_node
from ..snapshot import load_snapshot

#: How many spans the optional encoder arm embeds. Bounded so the sweep stays a sweep.
ENCODER_SAMPLE = 64


def _percentile(sorted_values: list[int], q: float) -> int:
    if not sorted_values:
        return 0
    idx = min(len(sorted_values) - 1, int(q * len(sorted_values)))
    return sorted_values[idx]


def sweep(snapshot_dir: Path, sizes: list[int], limit: int | None,
          hard_cap_tokens: int = HARD_CAP_TOKENS) -> tuple[list[dict], list[str]]:
    bundle = load_snapshot(snapshot_dir)
    nodes = [n for n in bundle.iter_nodes()
             if not n.sealed and n.content_blob is not None and n.size_bytes > 0]
    if limit is not None:
        nodes = nodes[:limit]

    rows: list[dict] = []
    sample_texts: list[str] = []
    for target in sizes:
        started = time.perf_counter()
        span_count = leaf_count = oversize = covered = total = 0
        tokens: list[int] = []
        reasons: dict[str, int] = {}
        misses: dict[str, int] = {}
        for node in nodes:
            data = bundle.blobs.get(node.content_blob)
            result = segment_node(node, data, target, hard_cap_tokens)
            span_count += len(result.spans)
            total += node.size_bytes
            for span in result.spans:
                if not span.is_leaf:
                    continue
                leaf_count += 1
                covered += span.end - span.start
                tokens.append(span.est_tokens)
                if len(sample_texts) < ENCODER_SAMPLE and target == sizes[0]:
                    sample_texts.append(data[span.start:span.end]
                                        .decode("utf-8", errors="replace"))
            oversize += len(result.oversize)
            for item in result.oversize:
                reasons[item["reason"]] = reasons.get(item["reason"], 0) + 1
            for item in result.misses:
                misses[item["reason"]] = misses.get(item["reason"], 0) + 1
        tokens.sort()
        rows.append({
            "target": target, "spans": span_count, "leaf_spans": leaf_count,
            "coverage": 1.0 if total == 0 else covered / total,
            "oversize": oversize, "p50": _percentile(tokens, 0.5),
            "p90": _percentile(tokens, 0.9), "seconds": time.perf_counter() - started,
            "oversize_reasons": reasons, "miss_reasons": misses,
        })
    return rows, sample_texts


def _encoder_arm(sample: list[str]) -> tuple[str, float | None]:
    """Time the real encoder over a bounded sample, or name exactly why it was skipped."""
    from ..encoders.bge_onnx import MODEL_DIR_ENV, BgeOnnxEncoder, resolve_model_dir
    if resolve_model_dir(None) is None:
        return (f"SKIPPED: no model directory ({MODEL_DIR_ENV} unset or has no "
                f"model_optimized.onnx)"), None
    import importlib.util
    if importlib.util.find_spec("fastembed") is None:
        return "SKIPPED: fastembed is not importable in this process", None
    encoder = BgeOnnxEncoder(threads=int(os.environ.get("LAPLACE_EMBED_THREADS", "0") or 0))
    try:
        started = time.perf_counter()
        vectors = encoder.embed(sample)
        elapsed = time.perf_counter() - started
    except AtlasError as exc:
        return f"SKIPPED: {exc}", None
    return f"{encoder.encoder_id}: {len(vectors)} spans in {elapsed:.2f}s", elapsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="span-size sweep over a snapshot")
    parser.add_argument("snapshot_dir", type=Path)
    parser.add_argument("--sizes", default=",".join(str(s) for s in SWEEP_TARGETS))
    parser.add_argument("--hard-cap-tokens", type=int, default=HARD_CAP_TOKENS)
    parser.add_argument("--limit", type=int, default=None,
                        help="segment only the first N unsealed nodes (a slice, not a sample)")
    parser.add_argument("--no-encoder", action="store_true",
                        help="do not attempt the encoder timing arm")
    args = parser.parse_args(argv)

    sizes = [int(s) for s in args.sizes.split(",") if s.strip()]
    try:
        rows, sample = sweep(args.snapshot_dir, sizes, args.limit, args.hard_cap_tokens)
    except AtlasError as exc:
        print(f"REFUSED {exc}", file=sys.stderr)
        return 1

    scope = f"first {args.limit} nodes" if args.limit else "whole snapshot"
    print(f"span-size sweep over {args.snapshot_dir} ({scope}, cap={args.hard_cap_tokens})")
    print()
    print(f"{'target':>7} {'spans':>10} {'leaf':>10} {'coverage':>10} {'oversize':>9} "
          f"{'p50':>6} {'p90':>6} {'seconds':>9}")
    for row in rows:
        print(f"{row['target']:>7} {row['spans']:>10} {row['leaf_spans']:>10} "
              f"{row['coverage']:>10.6f} {row['oversize']:>9} {row['p50']:>6} "
              f"{row['p90']:>6} {row['seconds']:>9.2f}")
    print()
    for row in rows:
        if row["oversize_reasons"]:
            named = ", ".join(f"{k}={v}" for k, v in sorted(row["oversize_reasons"].items()))
            print(f"target {row['target']} oversize by reason: {named}")
    for row in rows:
        if row["miss_reasons"]:
            named = ", ".join(f"{k}={v}" for k, v in sorted(row["miss_reasons"].items()))
            print(f"target {row['target']} segmentation misses: {named}")
    print()
    if args.no_encoder:
        print("encoder timing    SKIPPED: --no-encoder")
    else:
        line, _ = _encoder_arm(sample)
        print(f"encoder timing    {line}")
    print()
    print("Retrieval quality is NOT measured here - span counts and size distributions say")
    print("nothing about what a query finds. That read is Phase 2's (bench v2 over this")
    print("snapshot); until it lands, choose a target on shape and cost only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
