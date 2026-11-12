#!/usr/bin/env python3
"""Parity + speed for the GPU spectral seed — the instrument his ruling asked for, measured.

HIS RULING: ``PV-20260820T093000Z-gpu-takes-the-spectral-side`` (2026-08-20) — "the GPU should
definitely be doing the spectral side as well shouldn't it?" ``ATLAS_MATHEMATICS.md`` §8.3 names
the gap this closes: "No document specifies a GPU eigensolver or a GPU embedding path for the
engine's own fold."

WHAT IS MEASURED, and in this order, because a speed number from a wrong operator is worse than
no number at all:

  1. PARITY FIRST, and the run says FAIL rather than printing a ratio if it fails.
     a. n = 500 seeded draw from the LIVE basis: the GPU factor-form bottom-k against the dense
        ``numpy.linalg.eigvalsh`` of the SAME normalised Laplacian, built the incumbent's own way
        (``meaning_upfold._best_split`` lines 413-414). Gate: max |deviation| <= 1e-4.
     b. The CPU factor form against that same dense reference — the control that separates "the
        factored identity is exact" from "float32 on the GPU is close enough". If (a) fails and
        (b) passes, the fault is precision; if both fail, the fault is the operator.
     c. Full-n matvec agreement against a BLOCK-materialised dense A (never held whole). This is
        the check that the identity survives at the scale the eigensolve actually runs, which a
        500-leaf draw cannot speak to.

  2. SPEED at n = every residue leaf, GPU factor form, min of R repeats, loadavg recorded (this
     box runs other audit lanes; the contended arm is the fast one, so the ratios read low).
     The CPU factor form is timed at the same n as the second reference point, so the GPU's gain
     over the ALREADY-FAST replacement is separated from the replacement's gain over the incumbent.
     **No full CPU dense fold is run.** The incumbent's cost comes from two banked figures, and
     the difference between them is stated rather than smoothed over — see ``incumbent_reference``.

  3. VRAM. The whole point of the factored form is that the n x n affinity never exists: at
     n = 14,300 it would be 818 MB in float32 / 1.64 GB in float64 on a 4 GB card. The guard
     asserts the operator's working set stays in the tens of MB and the pool's high-water mark
     fits the device.

Read-only against the store. Writes exactly one file: the JSON named by --out.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

import numpy as np  # noqa: E402

from laplace.representation import spectral_gpu as S  # noqa: E402
from laplace.engine.meaning_upfold import load_vectors  # noqa: E402

# The incumbent's cost, banked — NOT re-run here (a full CPU dense fold is hours of this box).
INCUMBENT = {
    "full_upfold_wall_sec": 488.92,
    "full_upfold_n": 21420,
    "full_upfold_source": "ATLAS_MATHEMATICS.md:672 (.reembed_timing.jsonl:67), deposit 2026-08-15 14:38",
    "full_upfold_caveat": "a FULL upfold (every recursion level) at n=21,420, not a top split at "
                          "n=14,300 - it is the commissioned reference figure, and it is NOT "
                          "like-for-like against a single top-level eigensolve. Quoted, and the "
                          "ratio against it is labelled, but the measured row below is the honest one.",
    "top_split_wall_sec": 637.674,
    "top_split_cpu_sec": 1214.872,
    "top_split_peak_rss_mb": 8190.2,
    "top_split_per_eigensolve_sec": 104.764,
    "top_split_n": 14300,
    "top_split_source": "evidence/S2_FULLSCALE_2026-08-20/run/assembled.json "
                        "head_to_head_top_level_MEASURED.incumbent - meaning_upfold._best_split "
                        "re-run on THIS box, on THIS basis, at THIS n on the pilot night (git 97bae316)",
    "s2_cpu_factor_form_eigensolve_wall_sec": 4.7891,
    "s2_cpu_factor_form_deployed_wall_sec": 6.4945,
    "s2_source": "the same assembled.json, replacement arm (scipy LinearOperator + eigsh, float64)",
}


def loadavg() -> float:
    try:
        return round(os.getloadavg()[0], 2)
    except OSError:
        return -1.0


def timed_min(fn, repeats: int):
    """Min-of-R wall, with every sample kept (a min alone hides a bimodal box) and with the RESULT
    of the fastest repeat, not the last. Keeping the last repeat's result is how a report ends up
    printing an inner eigensolve time larger than the outer deployed time it sits inside - observed
    on the first run of this bench under contention, and fixed here rather than explained away."""
    samples, best, best_wall = [], None, float("inf")
    for _ in range(max(1, repeats)):
        t0 = time.perf_counter()
        res = fn()
        dt = time.perf_counter() - t0
        samples.append(dt)
        if dt < best_wall:
            best, best_wall = res, dt
    return best_wall, [round(s, 6) for s in samples], best


# ---------------------------------------------------------------------------
# 1. parity
# ---------------------------------------------------------------------------

def parity_sample(X, n_sample: int, k: int, seed: int, atol: float) -> dict:
    rng = np.random.default_rng(seed)
    idx = np.sort(rng.choice(X.shape[0], size=min(n_sample, X.shape[0]), replace=False))
    Xs = np.ascontiguousarray(X[idx])

    t0 = time.perf_counter()
    ref = S.dense_laplacian_eigenvalues(Xs, k)
    dense_wall = time.perf_counter() - t0

    cpu = S.spectral_bottom(Xs, k, backend="cpu", dtype="float64")
    cpu_dev = float(np.max(np.abs(cpu["eigenvalues"] - ref)))

    gpu_ok, gpu_why = S.gpu_ready()
    gpu, gpu_dev = None, None
    if gpu_ok:
        gpu = S.spectral_bottom(Xs, k, backend="gpu", dtype="float32")
        gpu_dev = float(np.max(np.abs(gpu["eigenvalues"] - ref)))

    verdict = "PASS" if (cpu_dev <= atol and (gpu_dev is not None and gpu_dev <= atol)) else "FAIL"
    if not gpu_ok:
        verdict = "CPU-ONLY" if cpu_dev <= atol else "FAIL"
    return {
        "what": f"bottom-{k} eigenvalues of L_sym, factor form vs dense numpy.linalg.eigvalsh on "
                f"the SAME L, on a seeded {len(idx)}-leaf draw from the live basis",
        "n": int(len(idx)), "k": int(k), "seed": int(seed), "atol": atol,
        "dense_reference_eigenvalues": [round(float(v), 12) for v in ref],
        "dense_reference_wall_sec": round(dense_wall, 6),
        "cpu_factor_form": {
            "dtype": cpu["dtype"], "which": cpu["which"], "matvecs": cpu["matvecs"],
            "wall_sec": round(cpu["wall_sec"], 6),
            "eigenvalues": [round(float(v), 12) for v in cpu["eigenvalues"]],
            "max_abs_deviation": cpu_dev, "verdict": "PASS" if cpu_dev <= atol else "FAIL",
        },
        "gpu_factor_form": ({
            "dtype": gpu["dtype"], "which": gpu["which"], "matvecs": gpu["matvecs"],
            "wall_sec": round(gpu["wall_sec"], 6),
            "eigenvalues": [round(float(v), 12) for v in gpu["eigenvalues"]],
            "max_abs_deviation": gpu_dev, "verdict": "PASS" if gpu_dev <= atol else "FAIL",
            "diagonal_repair_max": gpu["diagonal_repair_max"],
        } if gpu is not None else {"skipped": gpu_why}),
        "verdict": verdict,
    }


def parity_matvec_full(X, backend: str, blocks: int, seed: int) -> dict:
    """Full-n matvec agreement against a BLOCK-materialised dense A. The dense object is built one
    stripe at a time and thrown away, so the check costs stripe memory, never n^2."""
    n = X.shape[0]
    rng = np.random.default_rng(seed)
    v = rng.normal(size=n)

    dtype = np.float32 if backend == "gpu" else np.float64
    Xt = np.ascontiguousarray(X, dtype=dtype)
    ff = S.FactorForm(Xt, np)
    if backend == "gpu":
        import cupy
        ffg = S.FactorForm(cupy.asarray(Xt), cupy)
        got = cupy.asnumpy(ffg.affinity_matvec(cupy.asarray(v, dtype=dtype))).astype(np.float64)
        repair = ffg.diagonal_repair_max
    else:
        got = np.asarray(ff.affinity_matvec(v.astype(dtype)), dtype=np.float64)
        repair = ff.diagonal_repair_max

    X64 = np.ascontiguousarray(X, dtype=np.float64)
    ref = np.empty(n, dtype=np.float64)
    step = max(1, n // max(1, blocks))
    t0 = time.perf_counter()
    for s in range(0, n, step):
        e = min(n, s + step)
        A = (X64[s:e] @ X64.T + 1.0) / 2.0             # the incumbent's affinity, one stripe
        rows = np.arange(s, e)
        A[np.arange(e - s), rows] = 1.0                # np.fill_diagonal(A, 1.0), stripe-local
        ref[s:e] = A @ v
        del A
    dense_wall = time.perf_counter() - t0

    err = np.abs(got - ref)
    rel = float(err.max() / max(np.abs(ref).max(), 1e-300))
    tol = 1e-5 if backend == "gpu" else 1e-10
    return {
        "what": f"A v at full n={n}, {backend} factor form ({np.dtype(dtype).name}) vs a "
                f"block-materialised dense A (float64, {blocks} stripes, never held whole)",
        "n": int(n), "backend": backend, "dtype": np.dtype(dtype).name,
        "max_abs_err": float(err.max()), "max_rel_err": rel,
        "rel_tol": tol, "verdict": "PASS" if rel < tol else "FAIL",
        "diagonal_repair_max": repair,
        "dense_reference_wall_sec": round(dense_wall, 3),
        "note": "diagonal_repair_max is max|1 - (||x_i||^2 + 1)/2| - how far the factored diagonal "
                "sat from the 1.0 meaning_upfold._best_split forces. It is CARRIED, not assumed "
                "away, which is what makes the factored operator exact rather than approximate.",
    }


# ---------------------------------------------------------------------------
# 2. speed + 3. VRAM
# ---------------------------------------------------------------------------

def speed_arm(X, k: int, backend: str, repeats: int, dtype: str) -> dict:
    n, d = X.shape
    la0 = loadavg()
    wall, samples, last = timed_min(
        lambda: S.spectral_bottom(X, k, backend=backend, dtype=dtype), repeats)
    row = {
        "backend": backend, "dtype": dtype, "n": int(n), "d": int(d), "k": int(k),
        "which": last["which"],
        "deployed_wall_sec": round(wall, 4),
        "eigensolve_wall_sec": round(float(last["wall_sec"]), 4),
        "deployed_samples_sec": samples,
        "matvecs": last["matvecs"],
        "flops_measured": last["flops_measured"],
        "working_set_bytes": last["working_set_bytes"],
        "diagonal_repair_max": last["diagonal_repair_max"],
        "eigenvalues": [round(float(v), 10) for v in last["eigenvalues"]],
        "loadavg_before": la0, "loadavg_after": loadavg(),
        "note": "deployed_wall_sec is the whole call (host->device copy, degree, operator build, "
                "Lanczos); eigensolve_wall_sec is the Lanczos alone.",
    }
    if backend == "gpu":
        row["vram_pool_peak_bytes"] = last["vram_pool_peak_bytes"]
        row["vram_device_total_bytes"] = last["vram_device_total_bytes"]
        row["vram_device_free_bytes"] = last["vram_device_free_bytes"]
    return row


def vram_guard(gpu_row: dict | None, n: int, budget_bytes: int, ws_ceiling_bytes: int) -> dict:
    dense32, dense64 = n * n * 4, n * n * 8
    if gpu_row is None:
        return {"verdict": "SKIPPED", "why": "no GPU arm ran",
                "dense_affinity_float32_bytes": dense32,
                "dense_affinity_float64_bytes": dense64}
    peak = int(gpu_row["vram_pool_peak_bytes"])
    ws = int(gpu_row["working_set_bytes"])
    checks = {
        "peak_fits_budget": {"peak_bytes": peak, "budget_bytes": budget_bytes,
                             "pass": peak < budget_bytes},
        "peak_fits_device": {"peak_bytes": peak,
                             "device_total_bytes": int(gpu_row["vram_device_total_bytes"]),
                             "pass": peak < int(gpu_row["vram_device_total_bytes"])},
        "working_set_is_factor_form": {
            "working_set_bytes": ws, "ceiling_bytes": ws_ceiling_bytes, "pass": ws < ws_ceiling_bytes,
            "why": "the factored operator's whole working set is X plus an n-vector - tens of MB. "
                   "An n^2 affinity in float32 would be "
                   f"{dense32 / 1024**2:.0f} MB ({dense32 / budget_bytes:.0%} of the 4 GB budget), "
                   f"in float64 {dense64 / 1024**3:.2f} GB (does not fit the card at all). "
                   "This ceiling is what discriminates the two.",
        },
    }
    return {
        "verdict": "PASS" if all(c["pass"] for c in checks.values()) else "FAIL",
        "checks": checks,
        "dense_affinity_float32_bytes": dense32,
        "dense_affinity_float64_bytes": dense64,
        "peak_over_dense_float32": round(peak / dense32, 5),
    }


def gpu_name() -> str:
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
                              "--format=csv,noheader"], capture_output=True, text=True, timeout=30)
        return out.stdout.strip() or "(nvidia-smi returned nothing)"
    except Exception as exc:  # noqa: BLE001
        return f"(nvidia-smi unavailable: {type(exc).__name__})"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=str(REPO))
    ap.add_argument("--out", default=str(REPO / "evidence/SELF_AUDIT_2026-08-20/gpu_spectral_bench.json"))
    ap.add_argument("--parity-n", type=int, default=500)
    ap.add_argument("--k", type=int, default=8,
                    help="one Lanczos pass at k=8 subsumes the incumbent's whole k=2..8 sweep, "
                         "which pays a separate dense eigensolve per k")
    ap.add_argument("--k-cross", type=int, default=32,
                    help="the S2 pilot night's mode count (evidence/S2_FULLSCALE_2026-08-20 "
                         "M_MODES=32). Timed as a SECOND arm so the cross-reference to that "
                         "night's banked 4.7891s CPU figure is like-for-like; 0 disables it")
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--atol", type=float, default=1e-4)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--blocks", type=int, default=29)
    ap.add_argument("--vram-budget-mb", type=int, default=4096)
    ap.add_argument("--ws-ceiling-mb", type=int, default=64)
    ap.add_argument("--skip-full-matvec", action="store_true",
                    help="skip parity check (c), the block-materialised full-n matvec")
    ap.add_argument("--skip-cpu-speed", action="store_true")
    args = ap.parse_args()

    print("== the GPU spectral seed: parity + speed ==")
    print(f"   box: {gpu_name()}")
    backend, why = S.backend_choice()
    ok, gwhy = S.gpu_ready()
    print(f"   {S.ENV_FLAG}={os.environ.get(S.ENV_FLAG, '(unset)')} -> backend_choice={backend}"
          f"{(' (' + why + ')') if why else ''}; gpu_ready={ok}{(' - ' + gwhy) if gwhy else ''}")

    t_load = time.perf_counter()
    bname, names, M = load_vectors(args.repo)
    X = np.ascontiguousarray(M, dtype=np.float64)
    X /= np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-12, None)  # _embed's own last line
    load_wall = time.perf_counter() - t_load
    n, d = X.shape
    print(f"   basis: {bname}  n={n}  d={d}  ({load_wall:.2f}s to read+normalise)")

    print(f"\n-- parity (a): n={args.parity_n} draw, factor form vs dense eigvalsh, atol={args.atol}")
    par = parity_sample(X, args.parity_n, args.k, args.seed, args.atol)
    print(f"   CPU factor form max|dev| = {par['cpu_factor_form']['max_abs_deviation']:.3e}"
          f"  [{par['cpu_factor_form']['verdict']}]")
    if "skipped" in par["gpu_factor_form"]:
        print(f"   GPU SKIPPED: {par['gpu_factor_form']['skipped']}")
    else:
        print(f"   GPU factor form max|dev| = {par['gpu_factor_form']['max_abs_deviation']:.3e}"
              f"  [{par['gpu_factor_form']['verdict']}]")
    print(f"   parity verdict: {par['verdict']}")

    mv = None
    if not args.skip_full_matvec:
        print(f"\n-- parity (c): full-n matvec vs a block-materialised dense A ({args.blocks} stripes)")
        mv = parity_matvec_full(X, "gpu" if ok else "cpu", args.blocks, args.seed)
        print(f"   max_rel_err = {mv['max_rel_err']:.3e} (tol {mv['rel_tol']:.0e})  [{mv['verdict']}]"
              f"   diagonal_repair_max = {mv['diagonal_repair_max']:.3e}")

    if par["verdict"] == "FAIL" or (mv is not None and mv["verdict"] == "FAIL"):
        print("\nPARITY FAILED - refusing to print a speed ratio for an operator that is not the "
              "same operator. Writing the JSON with the failure and stopping.")
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(
            {"verdict": "FAIL", "parity_sample": par, "parity_matvec_full": mv}, indent=1) + "\n")
        return 1

    print(f"\n-- speed: n={n}, k={args.k}, min of {args.repeats}")
    arms = {}
    if ok:
        arms["gpu_factor_form"] = speed_arm(X, args.k, "gpu", args.repeats, "float32")
        g = arms["gpu_factor_form"]
        print(f"   GPU  deployed {g['deployed_wall_sec']:.4f}s   eigensolve "
              f"{g['eigensolve_wall_sec']:.4f}s   matvecs {g['matvecs']}   "
              f"VRAM peak {g['vram_pool_peak_bytes'] / 1024**2:.1f} MB   loadavg {g['loadavg_after']}")
    if not args.skip_cpu_speed:
        arms["cpu_factor_form"] = speed_arm(X, args.k, "cpu", args.repeats, "float64")
        c = arms["cpu_factor_form"]
        print(f"   CPU  deployed {c['deployed_wall_sec']:.4f}s   eigensolve "
              f"{c['eigensolve_wall_sec']:.4f}s   matvecs {c['matvecs']}   loadavg {c['loadavg_after']}")

    if args.k_cross:
        print(f"\n-- speed cross-check at the S2 pilot night's k={args.k_cross}")
        if ok:
            arms["gpu_factor_form_k_cross"] = speed_arm(X, args.k_cross, "gpu", args.repeats, "float32")
            gx = arms["gpu_factor_form_k_cross"]
            print(f"   GPU  deployed {gx['deployed_wall_sec']:.4f}s   eigensolve "
                  f"{gx['eigensolve_wall_sec']:.4f}s   matvecs {gx['matvecs']}   "
                  f"VRAM peak {gx['vram_pool_peak_bytes'] / 1024**2:.1f} MB")
        if not args.skip_cpu_speed:
            arms["cpu_factor_form_k_cross"] = speed_arm(X, args.k_cross, "cpu", args.repeats, "float64")
            cx = arms["cpu_factor_form_k_cross"]
            print(f"   CPU  deployed {cx['deployed_wall_sec']:.4f}s   eigensolve "
                  f"{cx['eigensolve_wall_sec']:.4f}s   matvecs {cx['matvecs']}   "
                  f"(S2 banked the same arm at {INCUMBENT['s2_cpu_factor_form_eigensolve_wall_sec']}s "
                  f"eigensolve / {INCUMBENT['s2_cpu_factor_form_deployed_wall_sec']}s deployed)")

    g = arms.get("gpu_factor_form")
    c = arms.get("cpu_factor_form")
    ratios = {}
    if g:
        ratios["gpu_eigensolve_vs_incumbent_top_split_MEASURED"] = round(
            INCUMBENT["top_split_wall_sec"] / g["eigensolve_wall_sec"], 1)
        ratios["gpu_deployed_vs_incumbent_top_split_MEASURED"] = round(
            INCUMBENT["top_split_wall_sec"] / g["deployed_wall_sec"], 1)
        ratios["gpu_deployed_vs_banked_full_upfold_NOT_LIKE_FOR_LIKE"] = round(
            INCUMBENT["full_upfold_wall_sec"] / g["deployed_wall_sec"], 1)
        ratios["gpu_eigensolve_vs_incumbent_per_eigensolve"] = round(
            INCUMBENT["top_split_per_eigensolve_sec"] / g["eigensolve_wall_sec"], 1)
        if c:
            ratios["gpu_vs_cpu_factor_form_eigensolve"] = round(
                c["eigensolve_wall_sec"] / g["eigensolve_wall_sec"], 2)
            ratios["gpu_vs_cpu_factor_form_deployed"] = round(
                c["deployed_wall_sec"] / g["deployed_wall_sec"], 2)
    gx, cx = arms.get("gpu_factor_form_k_cross"), arms.get("cpu_factor_form_k_cross")
    if gx:
        ratios["k_cross_gpu_eigensolve_vs_S2_banked_cpu"] = round(
            INCUMBENT["s2_cpu_factor_form_eigensolve_wall_sec"] / gx["eigensolve_wall_sec"], 1)
        ratios["k_cross_gpu_deployed_vs_incumbent_top_split_MEASURED"] = round(
            INCUMBENT["top_split_wall_sec"] / gx["deployed_wall_sec"], 1)
        if cx:
            ratios["k_cross_gpu_vs_cpu_factor_form_eigensolve"] = round(
                cx["eigensolve_wall_sec"] / gx["eigensolve_wall_sec"], 2)

    # guard the WORST GPU arm, not the first: a wider k holds more Lanczos vectors on the card
    worst = max([a for a in (g, gx) if a], key=lambda a: a["vram_pool_peak_bytes"], default=None)
    vram = vram_guard(worst, n, args.vram_budget_mb * 1024**2, args.ws_ceiling_mb * 1024**2)
    if worst is not None:
        vram["guarded_arm_k"] = int(worst["k"])
    print(f"\n-- VRAM guard: {vram['verdict']}")
    if g:
        for nm, ck in vram["checks"].items():
            print(f"   {'PASS' if ck['pass'] else 'FAIL'}  {nm}")

    agree = None
    if g and c:
        agree = float(np.max(np.abs(np.asarray(g["eigenvalues"]) - np.asarray(c["eigenvalues"]))))
        print(f"\n-- full-n GPU vs CPU factor-form eigenvalue agreement: max|dev| = {agree:.3e}")

    verdict = "PASS" if (par["verdict"] in ("PASS", "CPU-ONLY")
                         and (mv is None or mv["verdict"] == "PASS")
                         and vram["verdict"] in ("PASS", "SKIPPED")) else "FAIL"

    out = {
        "what": "the GPU spectral seed (src/laplace/representation/spectral_gpu.py): parity against the incumbent's "
                "own dense arithmetic, then wall-clock at full residue scale, then the VRAM guard",
        "ruling": "PV-20260820T093000Z-gpu-takes-the-spectral-side",
        "gap_filled": "ATLAS_MATHEMATICS.md 8.3 - 'No document specifies a GPU eigensolver or a "
                      "GPU embedding path for the engine's own fold.'",
        "fence": "THE INSTRUMENT, NOT THE SWAP. meaning_upfold._best_split is untouched; this path "
                 "runs only behind LAPLACE_SPECTRAL_GPU. The production swap rides the parity gates "
                 "at DESIGN_2026-08-11_the-atlas-gauntlet.md:281-288, which are about the TREE "
                 "(trigger rates, swap-vs-growth churn, open_descender materialisation) - not "
                 "eigenvalues. Nothing here pre-empts them.",
        "verdict": verdict,
        "when": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "box": {"gpu": gpu_name(), "platform": platform.platform(),
                "python": platform.python_version(), "loadavg_at_start": loadavg()},
        "versions": _versions(),
        "basis": {"backend": bname, "n": int(n), "d": int(d),
                  "source": ".meaning_vectors.f32.npy + .meaning_vectors.index.json via "
                            "meaning_upfold.load_vectors (read-only)",
                  "read_and_normalise_wall_sec": round(load_wall, 3)},
        "parity_sample": par,
        "parity_matvec_full": mv,
        "speed": arms,
        "full_n_gpu_vs_cpu_eigenvalue_max_deviation": agree,
        "incumbent_reference": INCUMBENT,
        "ratios": ratios,
        "ratio_notes": [
            f"The k={args.k} arm is the honest comparator for the incumbent's top split: "
            f"_best_split sweeps k=2..8 and pays a SEPARATE dense SpectralClustering eigensolve "
            f"per k (7 of them, 104.764 s each measured), while ONE Lanczos pass at k=8 yields "
            f"every embedding that sweep needs.",
            f"The k={args.k_cross} arm exists only to be like-for-like against the S2 pilot "
            f"night's banked CPU figure, which was taken at M_MODES=32 "
            f"(evidence/S2_FULLSCALE_2026-08-20/experiment.py:97). Comparing this repo's k=8 "
            f"number to that 4.7891 s would flatter the GPU by the width difference alone.",
            "Every ratio against 488.92 s is labelled NOT_LIKE_FOR_LIKE: that figure is a FULL "
            "upfold (all recursion levels) at n=21,420, not one top-level eigensolve at n=14,300.",
            "CONTENTION, stated in the direction it actually cuts here (the opposite of the S2 "
            "night's): this bench ran while sibling audit lanes held the box. The CPU arm competes "
            "for cores and is the one penalised; the GPU arm has the card to itself. So "
            "gpu_vs_cpu_factor_form_* reads HIGH, not low, and should be read as an upper bound "
            "until re-taken on a quiet box. The incumbent rows are banked numbers from a run that "
            "ended at loadavg 8.5, so the gpu_*_vs_incumbent_* ratios do not carry this bias. "
            "loadavg is recorded per arm.",
            "WHAT THIS DOES NOT REPLACE, and the reason the incumbent's 637.674 s is not all "
            "recoverable: that figure is 7 dense eigensolves (104.764 s each) PLUS 7 silhouette "
            "evaluations (5.23 s each) PLUS a 17.9 s dense gram build. This instrument replaces "
            "the eigensolve column only. A deployed fold still owes a way to CHOOSE k - the "
            "incumbent's silhouette sweep is O(n^2) per (k) cell on the same dense distance matrix "
            "this operator exists to never build, so the swap needs a spectrum-side rule (S2 used "
            "a diffusion effective-rank rule at t*) and that rule is NOT built or measured here.",
        ],
        "vram_guard": vram,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=1) + "\n")
    print(f"\n== {verdict} == wrote {args.out}")
    return 0 if verdict == "PASS" else 1


def _versions() -> dict:
    v = {"numpy": np.__version__}
    try:
        import scipy
        v["scipy"] = scipy.__version__
    except Exception:  # noqa: BLE001
        v["scipy"] = "(absent)"
    cupy, why = S.cupy_module()
    if cupy is None:
        v["cupy"] = f"(absent: {why})"
    else:
        v["cupy"] = cupy.__version__
        try:
            v["cuda_runtime"] = cupy.cuda.runtime.runtimeGetVersion()
            v["cuda_driver"] = cupy.cuda.runtime.driverGetVersion()
        except Exception:  # noqa: BLE001
            pass
    return v


if __name__ == "__main__":
    raise SystemExit(main())
