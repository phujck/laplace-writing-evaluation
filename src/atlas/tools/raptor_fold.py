"""raptor_fold - build the RAPTOR fold: cluster, dispatch the summaries, embed them, bank the bill.

    PYTHONPATH=src python3 -m atlas.tools.raptor_fold <snapshot_dir> \\
        --universe bench-filtered --projection-generation sha256:<hex> [--dry-run]

THIS IS THE DISPATCH SITE. Every summary is written by a dispatched agent carrying an EXPLICIT
model stamp - ``DISPATCH_SPEC`` below - and never an inherited one. The dispatch-model law (his,
2026-07-11) is that Eigen orchestrates and dispatched agents are opus-level or less; ``sonnet`` is
inside that ceiling, and the literal is written in the shape ``scripts/audit_dispatch_models.py``
greps for, with this file added to that auditor's scan globs. A dispatch site the auditor cannot
see is the hole the auditor exists to close, so the site was made visible rather than merely
compliant.

EVERY CALL IS RECORDED, COUNTED NOT DECLARED (seam J7). One row per invocation in
``manifest.json``: the batch id, the model asked for, the models the harness actually billed, the
prompt's byte-length and its bytes/4 token estimate, the token counts the API returned, the wall
seconds, and whether the call was a retry. A retry is a call and is counted as one - a fold bill
that quietly excludes its own failures is not a bill. ``model_calls`` is then RECOUNTED from those
rows by the arm, so the summary field and the evidence cannot drift apart.

THE FOLD IS A BILL, SO IT IS NEVER INCURRED IMPLICITLY. The arm refuses if the fold is absent
rather than building one, because a benchmark run that can spend money by being run is a benchmark
whose costs nobody counted. ``--dry-run`` builds the tree, writes the prompts and prints the
projected bill without calling anything, which is how the budget was checked before it was spent.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np

from ..bench.raptor_fold import (
    BATCH_SIZE,
    MAX_DEPTH,
    RAPTOR_RECIPE_VERSION,
    TARGET_SUMMARIES,
    batch_items,
    build_prompt,
    build_tree,
    fold_generation,
    fold_id_of,
    store_dir,
    summarization_order,
)
from ..bench.universe import BENCH_FILTERED, FULL_UNIVERSE, RULED_ONLY, SnapshotView
from ..encoders.bge_onnx import BgeOnnxEncoder
from ..errors import ArmUnavailable, AtlasError
from ..snapshot import load_snapshot
from ..store import write_atomic, write_jsonl

UNIVERSES = {"bench-filtered": BENCH_FILTERED, "ruled-only": RULED_ONLY, "full": FULL_UNIVERSE}
DEFAULT_SEED = 20260801

#: THE DISPATCH SPEC. Written as a ``"model": "<token>"`` literal because that is exactly what
#: ``scripts/audit_dispatch_models.py`` extracts and checks against ``pipeline.schema.MAX_MODEL``;
#: this file is in that auditor's scan globs, so the ceiling is enforced here mechanically rather
#: than promised in prose. Changing the token to anything above the ceiling turns the suite red.
DISPATCH_SPEC = {"model": "sonnet"}

#: Concurrent dispatched agents. Four keeps the wall clock reasonable without making the API the
#: bottleneck for everything else on this box.
MAX_CONCURRENCY = 4

#: A batch that does not come back as parseable JSON is retried this many extra times. Each retry
#: is a counted model call.
MAX_RETRIES = 2

PROJECTION_STORE = Path(__file__).resolve().parents[3] / "atlas" / "stores" / "projections"   # the container's stores (R2)
DISPATCH_GATE = Path(__file__).resolve().parents[3] / "scripts" / "dispatch_gate.mjs"


def _tokens_estimate(text: str) -> int:
    """bytes/4 - the repo's canonical estimate, and what the brief asks the manifest to carry."""
    return len(text.encode("utf-8")) // 4


def load_projection(generation_id: str, view: SnapshotView,
                    store: Path = PROJECTION_STORE) -> np.ndarray:
    """The leaf vectors ``dense_flat`` already built, aligned to ``view.leaf_spans``.

    Read by SPAN CONTENT HASH, the same key ``dense_flat`` writes under, so this is the identical
    geometry and not a re-derivation of it. A missing key is a refusal: silently embedding the
    gap would make RAPTOR's tree depend on vectors nobody banked.
    """
    gen_dir = store / generation_id.split(":", 1)[-1]
    keys_path, vec_path = gen_dir / "keys.json", gen_dir / "vectors.npy"
    if not keys_path.is_file() or not vec_path.is_file():
        raise ArmUnavailable("the dense projection generation is not banked; RAPTOR reuses it "
                             "rather than re-embedding 68,502 spans", generation=generation_id,
                             path=str(gen_dir))
    keys = json.loads(keys_path.read_text(encoding="utf-8"))
    matrix = np.load(vec_path)
    index = {key: i for i, key in enumerate(keys)}
    rows: list[int] = []
    missing = 0
    for span in view.leaf_spans:
        key = view.span_content_hash(span)
        row = index.get(key)
        if row is None:
            missing += 1
            if missing <= 3:
                print(f"  MISSING vector for span {span.span_id} ({span.node_id})")
            continue
        rows.append(row)
    if missing:
        raise ArmUnavailable("the banked projection does not cover this view",
                             generation=generation_id, missing=missing,
                             spans=len(view.leaf_spans))
    return np.asarray(matrix[rows], dtype=np.float32)


def _verify_dispatch_admission(prompt: str, label: str, admission: dict[str, Any] | None
                               ) -> None:
    """Run the shared D2 verifier; refusal occurs before any Claude process exists."""
    payload = json.dumps({"label": label, "prompt": prompt, "admission": admission})
    gate = subprocess.run(
        ["node", str(DISPATCH_GATE), "--verify-json"],
        input=payload,
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(Path.cwd()),
    )
    if gate.returncode != 0:
        raise ArmUnavailable(
            "RAPTOR dispatch reconstruction admission refused",
            label=label,
            gate_error=(gate.stderr or gate.stdout).strip()[:500],
        )


def dispatch_batch(prompt: str, batch_id: str, attempt: int,
                   timeout_s: int = 900,
                   admission: dict[str, Any] | None = None) -> dict[str, Any]:
    """One dispatched agent. Returns the parsed result plus the counted bill for THIS call."""
    label = f"raptor:{batch_id}:attempt:{attempt}"
    _verify_dispatch_admission(prompt, label, admission)
    cmd = [
        "claude", "-p",
        "--model", DISPATCH_SPEC["model"],
        "--output-format", "json",
        "--strict-mcp-config",
    ]
    started = time.perf_counter()
    proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                          timeout=timeout_s, cwd=str(Path.cwd()))
    wall = time.perf_counter() - started
    call: dict[str, Any] = {
        "batch_id": batch_id,
        "attempt": attempt,
        "is_retry": attempt > 1,
        "model_requested": DISPATCH_SPEC["model"],
        "prompt_bytes": len(prompt.encode("utf-8")),
        "prompt_tokens_estimate_bytes_over_4": _tokens_estimate(prompt),
        "wall_seconds": round(wall, 3),
        "exit_code": proc.returncode,
    }
    payload: dict[str, Any] = {}
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        call["error"] = f"non-JSON envelope: {proc.stdout[:200]!r} {proc.stderr[:200]!r}"
        return {"call": call, "items": None}

    usage = payload.get("usage") or {}
    call.update({
        "api_input_tokens": usage.get("input_tokens"),
        "api_output_tokens": usage.get("output_tokens"),
        "api_cache_creation_tokens": usage.get("cache_creation_input_tokens"),
        "api_cache_read_tokens": usage.get("cache_read_input_tokens"),
        "cost_usd": payload.get("total_cost_usd"),
        "duration_api_ms": payload.get("duration_api_ms"),
        # The harness bills ancillary models (a haiku for housekeeping) beside the one asked for.
        # Recorded verbatim rather than filtered: the law is a CEILING on every model that ran,
        # and hiding the small ones would make the record of it partial.
        "models_billed": sorted((payload.get("modelUsage") or {}).keys()),
        "is_error": bool(payload.get("is_error")),
    })
    text = (payload.get("result") or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        items = json.loads(text)
        if not isinstance(items, list):
            raise ValueError("not a list")
    except (json.JSONDecodeError, ValueError) as exc:
        call["error"] = f"summary payload did not parse as a JSON array: {exc}"
        return {"call": call, "items": None}
    return {"call": call, "items": items}


def run_level(level_items: list[dict[str, Any]], level: int,
              calls: list[dict[str, Any]],
              dispatch_admissions: dict[str, dict[str, Any]]) -> dict[str, str]:
    """Dispatch one level's clusters in batches, concurrently. Returns ``{cluster_id: summary}``."""
    batches = [level_items[i:i + BATCH_SIZE] for i in range(0, len(level_items), BATCH_SIZE)]
    out: dict[str, str] = {}

    def work(pair: tuple[int, list[dict[str, Any]]]
             ) -> tuple[str, dict[str, str], list[dict[str, Any]]]:
        """One batch, with its retries. Returns its own calls so nothing is shared across threads."""
        number, items = pair
        batch_id = f"L{level}-B{number:02d}"
        wanted = {item["cluster_id"] for item in items}
        prompt = build_prompt(items)
        local: dict[str, str] = {}
        local_calls: list[dict[str, Any]] = []
        for attempt in range(1, MAX_RETRIES + 2):
            label = f"raptor:{batch_id}:attempt:{attempt}"
            result = dispatch_batch(
                prompt,
                batch_id,
                attempt,
                admission=dispatch_admissions.get(label),
            )
            local_calls.append(result["call"])
            if result["items"] is None:
                continue
            for row in result["items"]:
                cid = str(row.get("cluster_id", "")).strip()
                summary = str(row.get("summary", "")).strip()
                if cid in wanted and summary:
                    local[cid] = summary
            if wanted <= set(local):
                break
        return batch_id, local, local_calls

    collected: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENCY) as pool:
        for batch_id, local, local_calls in pool.map(work, list(enumerate(batches))):
            print(f"    {batch_id}: {len(local)} summaries "
                  f"({len(local_calls)} call(s))", flush=True)
            out.update(local)
            collected.extend(local_calls)
    calls.extend(sorted(collected, key=lambda c: (c["batch_id"], c["attempt"])))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="build and bank the RAPTOR fold")
    ap.add_argument("snapshot_dir", type=Path)
    ap.add_argument("--universe", default="bench-filtered", choices=sorted(UNIVERSES))
    ap.add_argument("--projection-generation", required=True)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--target-summaries", type=int, default=TARGET_SUMMARIES)
    ap.add_argument("--max-depth", type=int, default=MAX_DEPTH)
    ap.add_argument("--store-root", type=Path, default=None)
    ap.add_argument("--model-dir", default=None)
    ap.add_argument("--dispatch-admissions", type=Path, default=None,
                    help="exact label-keyed D1 reconstruction admission receipts")
    ap.add_argument("--dry-run", action="store_true",
                    help="build the tree and the prompts, print the projected bill, call nothing")
    args = ap.parse_args(argv)

    if not args.dry_run and args.dispatch_admissions is None:
        print("REFUSED --dispatch-admissions is required before RAPTOR provider calls",
              file=sys.stderr)
        return 1
    dispatch_admissions = (
        json.loads(args.dispatch_admissions.read_text(encoding="utf-8"))
        if args.dispatch_admissions is not None
        else {}
    )
    if not isinstance(dispatch_admissions, dict):
        print("REFUSED dispatch admissions must be a label-keyed JSON object", file=sys.stderr)
        return 1

    try:
        snap = load_snapshot(args.snapshot_dir)
        segmentation = snap.segmentation() or {}
        view = SnapshotView(snap, UNIVERSES[args.universe])
        print(f"view {view.universe.name}: {len(view.node_ids)} nodes, "
              f"{len(view.leaf_spans)} leaf spans")

        generation = fold_generation(view, segmentation.get("generation_id", ""),
                                     args.projection_generation, args.seed,
                                     args.target_summaries, args.max_depth)
        fold_id = fold_id_of(generation)
        out_dir = store_dir(fold_id, args.store_root)
        print(f"fold_id {fold_id}\npath    {out_dir}")

        X = load_projection(args.projection_generation, view)
        print(f"projection reused: {X.shape[0]} vectors x {X.shape[1]} dims (0 re-embedded)")

        clustering_started = time.perf_counter()
        clusters = build_tree(X, seed=args.seed, target_summaries=args.target_summaries,
                              max_depth=args.max_depth)
        clustering_seconds = time.perf_counter() - clustering_started
        levels = summarization_order(clusters)
        total = sum(len(level) for level in levels)
        print(f"tree built in {clustering_seconds:.1f}s: {total} summaries over "
              f"{len(levels)} level(s) "
              f"({', '.join(f'L{clusters[ids[0]].level}={len(ids)}' for ids in levels)})")
        sizes = sorted((clusters[c].size for level in levels for c in level), reverse=True)
        if sizes:
            print(f"cluster sizes: max {sizes[0]}, median {sizes[len(sizes) // 2]}, min {sizes[-1]}")
    except AtlasError as exc:
        print(f"REFUSED {exc}", file=sys.stderr)
        return 1

    summaries: dict[str, str] = {}
    calls: list[dict[str, Any]] = []
    dispatch_started = time.perf_counter()
    for level_ids in levels:
        items = batch_items(view, X, clusters, level_ids, summaries)
        if args.dry_run:
            prompts = [build_prompt(items[i:i + BATCH_SIZE])
                       for i in range(0, len(items), BATCH_SIZE)]
            est = sum(_tokens_estimate(p) for p in prompts)
            print(f"  level {clusters[level_ids[0]].level}: {len(items)} clusters, "
                  f"{len(prompts)} batches, ~{est:,} prompt tokens (bytes/4)")
            summaries.update({cid: f"[dry-run placeholder for {cid}]" for cid in level_ids})
            continue
        print(f"  level {clusters[level_ids[0]].level}: {len(items)} clusters "
              f"in {(len(items) + BATCH_SIZE - 1) // BATCH_SIZE} batches")
        summaries.update(
            run_level(items, clusters[level_ids[0]].level, calls, dispatch_admissions)
        )
    dispatch_seconds = time.perf_counter() - dispatch_started

    if args.dry_run:
        print("dry run: nothing dispatched, nothing banked")
        return 0

    missing = [cid for level in levels for cid in level if cid not in summaries]
    if missing:
        print(f"REFUSED {len(missing)} cluster(s) came back without a summary: "
              f"{missing[:10]}", file=sys.stderr)
        return 1

    # --- embed the summaries (new text, a real and separate bill) ----------
    encoder = BgeOnnxEncoder(model_dir=args.model_dir,
                             threads=int(os.environ.get("LAPLACE_EMBED_THREADS", "0")) or None)
    ordered_ids = [cid for level in levels for cid in level]
    embed_started = time.perf_counter()
    vectors = np.asarray(encoder.embed([summaries[cid] for cid in ordered_ids]),
                         dtype=np.float32)
    embed_seconds = time.perf_counter() - embed_started
    print(f"embedded {len(ordered_ids)} summaries in {embed_seconds:.1f}s")

    out_dir.mkdir(parents=True, exist_ok=True)
    rows = [{
        "cluster_id": cid, "level": clusters[cid].level, "parent_id": clusters[cid].parent_id,
        "size": clusters[cid].size, "children": list(clusters[cid].children),
        "summary": summaries[cid],
        "representative_span_ids": list(clusters[cid].representative_span_ids),
    } for cid in ordered_ids]
    write_jsonl(out_dir / "summaries.jsonl", rows)
    np.save(out_dir / "vectors.npy", vectors)
    write_atomic(out_dir / "tree.json", (json.dumps(
        {"fold_id": fold_id, "generation": generation,
         "clusters": [clusters[c].to_record() for c in sorted(clusters)]},
        sort_keys=True, indent=1) + "\n").encode("utf-8"))

    billed = sorted({m for c in calls for m in (c.get("models_billed") or [])})
    manifest = {
        "kind": "raptor-fold/1",
        "recipe_version": RAPTOR_RECIPE_VERSION,
        "fold_id": fold_id,
        "generation": generation,
        "summary_count": len(ordered_ids),
        "target_summaries": args.target_summaries,
        "levels": {str(clusters[ids[0]].level): len(ids) for ids in levels},
        "model_calls": len(calls),
        "model_calls_successful": sum(1 for c in calls if not c.get("error")),
        "model_calls_retried": sum(1 for c in calls if c.get("is_retry")),
        "model_requested": DISPATCH_SPEC["model"],
        "models_billed": billed,
        "prompt_tokens_estimate_bytes_over_4": sum(
            c["prompt_tokens_estimate_bytes_over_4"] for c in calls),
        "api_input_tokens": sum(c.get("api_input_tokens") or 0 for c in calls),
        "api_output_tokens": sum(c.get("api_output_tokens") or 0 for c in calls),
        "api_cache_creation_tokens": sum(c.get("api_cache_creation_tokens") or 0 for c in calls),
        "api_cache_read_tokens": sum(c.get("api_cache_read_tokens") or 0 for c in calls),
        "cost_usd": round(sum(c.get("cost_usd") or 0.0 for c in calls), 6),
        "clustering_wall_seconds": round(clustering_seconds, 3),
        "dispatch_wall_seconds": round(dispatch_seconds, 3),
        "embed_wall_seconds": round(embed_seconds, 3),
        "fold_wall_seconds": round(clustering_seconds + dispatch_seconds + embed_seconds, 3),
        "summary_vectors_built": int(vectors.shape[0]),
        "encoder_id": encoder.encoder_id,
        "vector_bytes": int(vectors.nbytes),
        "sealed_content_in_prompts": False,
        "seal_note": ("every prompt character came from SnapshotView.span_text over unsealed "
                      "leaf spans; _assert_unsealed_sources re-checked each representative "
                      "against the snapshot's node records before the prompt was built"),
        "calls": calls,
    }
    write_atomic(out_dir / "manifest.json",
                 (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode("utf-8"))

    print(f"\nFOLD BANKED {out_dir}")
    print(f"  summaries        {manifest['summary_count']}")
    print(f"  model calls      {manifest['model_calls']} "
          f"({manifest['model_calls_retried']} retries) model={manifest['model_requested']} "
          f"billed={','.join(billed)}")
    print(f"  prompt tokens    {manifest['prompt_tokens_estimate_bytes_over_4']:,} (bytes/4 est) "
          f"| api in {manifest['api_input_tokens']:,} "
          f"cache_create {manifest['api_cache_creation_tokens']:,} "
          f"out {manifest['api_output_tokens']:,}")
    print(f"  cost             ${manifest['cost_usd']:.4f}")
    print(f"  wall             cluster {clustering_seconds:.1f}s + dispatch "
          f"{dispatch_seconds:.1f}s + embed {embed_seconds:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
