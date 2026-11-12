"""Manual, write-suppressed full upfold of a frozen persisted vector population.

Run with /usr/bin/python3 tests/measure_meaning_upfold_full.py. The sole file
write is one timing row after successful validation and unchanged-input checks.
This measures cached-vector repartitioning, not source re-sharding or embedding.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factor-cpu", action="store_true",
                        help="run the GPU splitter's existing factor algebra on its CPU backend")
    args = parser.parse_args()
    start = time.perf_counter()
    root = Path(__file__).resolve().parents[1]
    timing_path = root / ".reembed_timing.jsonl"
    allow_append = False
    blocked = []

    def guard(event, args):
        if event == "open":
            path, _, flags = args
            writing = isinstance(flags, int) and flags & (
                os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            if not writing or str(path) == "/dev/null":
                return
            if allow_append and str(path) == str(timing_path) and flags & os.O_APPEND:
                return
        elif event not in {"os.mkdir", "os.remove", "os.rename", "os.rmdir", "os.symlink", "os.link"}:
            return
        blocked.append({"event": event, "path": str(args[0])})
        raise RuntimeError("MEASUREMENT_WRITE_REFUSED")

    sys.addaudithook(guard)
    import numpy as np
    from threadpoolctl import threadpool_info
    from laplace.engine import meaning_upfold as mu
    from laplace.representation import embed_router, spectral_gpu
    from laplace.engine.residue import ResidueLedger

    assert (mu.LEAF_MAX, mu.MAX_DEPTH) == (10, 6)
    assert not mu._selector_on(), "residual selector needs a separate measurement contract"
    assert os.environ.get("LAPLACE_ORGAN_V1", "0") != "1"
    choice = spectral_gpu.fold_backend_choice()
    phases = {"imports_device": time.perf_counter() - start}
    print(json.dumps({"device_probe": choice, "blocked_writes": blocked}), flush=True)
    assert not blocked, "device setup attempted a forbidden side-file write"

    files = [".self_embeddings.json", ".self_graded.json", mu.TREE_FILE, mu.IDX_FILE, mu.VEC_FILE]
    t = time.perf_counter()
    snapshots = {name: (root / name).read_bytes() for name in files}
    stamps = {name: hashlib.sha256(raw).hexdigest() for name, raw in snapshots.items()}
    phases["snapshot_read_hash"] = time.perf_counter() - t
    t = time.perf_counter()
    before_tree = json.loads(snapshots[mu.TREE_FILE])
    before = mu.depth_cap_figure(before_tree)
    graded = json.loads(snapshots[".self_graded.json"])
    idx = json.loads(snapshots[mu.IDX_FILE])
    matrix = np.load(io.BytesIO(snapshots[mu.VEC_FILE]), allow_pickle=False)
    assert idx["format"] == mu.SIDECAR_FORMAT
    assert idx["backend"] == before_tree["version"]
    assert idx["sha256"] == stamps[mu.VEC_FILE]
    assert list(matrix.shape) == idx["shape"]
    names = sorted(before_tree["leaf_sha"])
    assert set(names) == set(idx["nodes"])
    assert sorted(e["row"] for e in idx["nodes"].values()) == list(range(len(names)))
    assert all(idx["nodes"][n]["h"] == before_tree["leaf_sha"][n] for n in names)
    assert all(n in graded for n in names)
    residue = {n: graded[n] for n in names}
    backend = SimpleNamespace(name=idx["backend"])
    phases["prepare_frozen_inputs"] = time.perf_counter() - t
    print(json.dumps({"before": before, "vector_shape": list(matrix.shape)}), flush=True)

    phases.update(embed_cached=0.0, split=0.0, project=0.0, serialize=0.0)
    calls = {"gpu": 0, "cpu_dense": 0, "cpu_factor": 0}
    rows = dict.fromkeys(calls, 0)
    captured = {}
    original_embed, original_split = mu._embed, mu._best_split
    original_project = mu._build_tree_from_full
    original_factor = spectral_gpu.FoldSpectral

    def embed(*args, **kwargs):
        t = time.perf_counter()
        result = original_embed(*args, **kwargs)
        phases["embed_cached"] += time.perf_counter() - t
        return result

    def split(X, level=1):
        large = len(X) >= int(os.environ.get("LAPLACE_FOLD_GPU_MIN_N", mu._SPECTRAL_GPU_MIN_N))
        device = "cpu_factor" if args.factor_cpu and large else (
            "gpu" if choice[0] == "gpu" and large else "cpu_dense")
        t = time.perf_counter()
        if device == "cpu_factor":
            with patch.object(spectral_gpu, "FoldSpectral", side_effect=lambda *a, **kw:
                              original_factor(*a, backend="cpu", **kw)):
                result = mu._best_split_gpu(X, level)
        else:
            result = original_split(X, level)
        elapsed = time.perf_counter() - t
        phases["split"] += elapsed
        calls[device] += 1
        rows[device] += len(X)
        if level == 1:
            print(json.dumps({"top_split_seconds": elapsed, "n": len(X), "k": result[0]}), flush=True)
        return result

    def project(*args, **kwargs):
        t, embed_before = time.perf_counter(), phases["embed_cached"]
        result = original_project(*args, **kwargs)
        phases["project"] += time.perf_counter() - t - (phases["embed_cached"] - embed_before)
        return result

    def persist(_, tree):
        t = time.perf_counter()
        captured["raw"] = json.dumps(tree).encode()
        captured["tree"] = tree
        phases["serialize"] += time.perf_counter() - t

    # Keep the production full recursion, embedding cache-hit normalization, and
    # tree projection. Substitute only frozen input adapters and persistence sinks.
    # Stored leaf hashes bind the copied vectors; source text is not re-derived.
    mu._gpu_fold.update(choice=choice)
    with patch.object(embed_router, "get_backend", return_value=backend), \
         patch.object(mu, "read_sidecar", return_value=(idx["nodes"], matrix)), \
         patch.object(mu, "migrate_legacy_store", return_value="snapshot"), \
         patch.object(mu, "_embeddable_text", side_effect=lambda _, n, *a: n), \
         patch.object(mu, "_text_sha", side_effect=lambda _, n: before_tree["leaf_sha"][n]), \
         patch.object(mu, "_embed", side_effect=embed), \
         patch.object(mu, "_best_split", side_effect=split), \
         patch.object(mu, "_build_tree_from_full", side_effect=project), \
         patch.object(mu, "_persist_tree", side_effect=persist), \
         patch.object(ResidueLedger, "bank", return_value=None):
        t = time.perf_counter()
        pm, cn = mu._full(root, residue, backend, before_tree["root_id"],
                          before_tree["lens_hash"], "WO-20260914-eh-07 memory-copy measurement",
                          before_tree.get("lens_pairs"))
        fold_total = time.perf_counter() - t
    assert cn and captured and set(names).issubset(pm)
    assert not blocked, "any attempted side-file write invalidates this measurement"
    phases["fold_other"] = fold_total - sum(phases[k] for k in (
        "embed_cached", "split", "project", "serialize"))
    t = time.perf_counter()
    after = mu.depth_cap_figure(json.loads(captured["raw"]))
    assert before["corpus_members"] == after["corpus_members"]
    phases["validate_after"] = time.perf_counter() - t
    t = time.perf_counter()
    end_stamps = {name: mu._sha256_file(root / name) for name in files}
    assert end_stamps == stamps, "INPUT_DRIFT: measurement invalid; timing row not banked"
    phases["verify_live_unchanged"] = time.perf_counter() - t
    row = {
        "ts": datetime.now(timezone.utc).isoformat(), "mode": "full-rebuild-measured",
        "work_order": "WO-20260914-eh-07-the-depth-cap",
        "scope": "production _full on in-memory copied persisted vectors; no source rebuild",
        "command": "PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=6 OMP_NUM_THREADS=6 MKL_NUM_THREADS=6 /usr/bin/python3 tests/measure_meaning_upfold_full.py" + (" --factor-cpu" if args.factor_cpu else ""),
        "caps": {"leaf_max": mu.LEAF_MAX, "branch_max": mu.BRANCH_MAX, "max_depth": mu.MAX_DEPTH},
        "device": {"spectral": "cpu-factor/dense-small" if args.factor_cpu else choice[0],
                   "reason": choice[1], "threadpools": threadpool_info()},
        "phases": {k: round(v, 6) for k, v in phases.items()},
        "full_path_seconds": round(fold_total, 6), "total": round(time.perf_counter() - start, 6),
        "volume": {"leaves": len(names), "dimensions": matrix.shape[1],
                   "split_calls": calls, "split_rows": rows},
        "before": before, "after": after, "inputs_sha256_before": stamps,
        "inputs_sha256_after": end_stamps, "rebuilt_tree_sha256": hashlib.sha256(captured["raw"]).hexdigest(),
        "live_inputs_unchanged": True,
        "residuals": ["No filesystem scratch copy: repository-only and no-/tmp fence; RAM snapshots used.",
                      "Frozen persisted vectors/hashes; current source re-sharding and fresh embedding unmeasured.",
                      "Tree serialization measured; disk persistence and residue telemetry banking suppressed.",
                      "GPU probe found no CUDA device; this is not GPU latency.",
                      "With --factor-cpu, large splits use existing FoldSpectral(backend=cpu) through _best_split_gpu; native dense CPU fallback latency remains unmeasured.",
                      "Initial native dense CPU attempt was interrupted in the top split (exit 130); no timing row was banked for it.",
                      "No wire, index, or final network embedding: not a whole deposit timing.",
                      "Independent reviewer could not start: collaboration service thread error."],
    }
    encoded = json.dumps(row, sort_keys=True)
    allow_append = True
    with timing_path.open("a", encoding="utf-8") as stream:
        stream.write(encoded + "\n")
    allow_append = False
    assert timing_path.read_text().splitlines()[-1] == encoded
    print(encoded, flush=True)


if __name__ == "__main__":
    main()
