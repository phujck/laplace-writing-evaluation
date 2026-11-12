#!/usr/bin/env python3
"""Generate figures from sealed, completed numerical stages only."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter
import numpy as np


HERE = Path(__file__).resolve().parent
EXTENSION = HERE.parent
RESULTS = EXTENSION / "results"
STYLE_PATH = (
    EXTENSION.parents[2] / "subset-sum-itqde" / "manuscript" / "figures" / "figstyle.py"
)
LOCALITY_PATH = RESULTS / "query_locality_matrix_v1.json"
PHYSICS_PATH = RESULTS / "physics_illustrations_v1.json"
ARRAYS_PATH = HERE / "completed_figures_arrays_v1.json"
PROVENANCE_PATH = HERE / "completed_figures_provenance_v1.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha(value) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()).hexdigest()


def load_style():
    spec = importlib.util.spec_from_file_location("completed_figure_style", STYLE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load figure style: {STYLE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def save_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def timing_summary(cells, q: int):
    methods = ("raw_packed_direct", "weighted_unique_direct", "recursive_exact_integer")
    output = {}
    for method in methods:
        rows = []
        for d in sorted({row["d"] for row in cells}):
            values = [
                row["methods"][method]["api_s_median"] * 1e3
                for row in cells
                if row["d"] == d and row["Q"] == q
                and row["methods"][method]["status"] == "MEASURED"
            ]
            rows.append({
                "d": d, "N": 2 ** (d - 1), "regimes": len(values),
                "minimum_ms": min(values), "median_ms": float(np.median(values)),
                "maximum_ms": max(values),
            })
        output[method] = rows
    return output


def support_summary(cells):
    output = {}
    for d in sorted({row["d"] for row in cells}):
        rows = []
        for r in sorted({row["fixed_coordinates"] for row in cells if row["d"] == d}):
            regimes = {
                (row["location"], row["support_fraction_min"], row["support_fraction_max"])
                for row in cells if row["d"] == d and row["fixed_coordinates"] == r
            }
            fractions = sorted({item[1] for item in regimes})
            if len(fractions) != 1 or any(lo != hi for _, lo, hi in regimes):
                raise AssertionError(f"support fraction drift for d={d}, r={r}")
            rows.append({
                "fixed_coordinates": r,
                "support_fraction": fractions[0],
                "locations": sorted(item[0] for item in regimes),
                "regimes": len(regimes),
            })
        output[str(d)] = rows
    return output


def negative_summary(all_cells):
    output = {}
    for law in ("small_unique_support_64", "high_entropy_unique_half_support"):
        rows = [row for row in all_cells if row["law"] == law and row["d"] == 19 and row["Q"] == 1024]
        methods = {}
        for method in ("raw_packed_direct", "weighted_unique_direct", "recursive_exact_integer"):
            measured = [row["methods"][method].get("api_s_median") for row in rows
                        if row["methods"][method]["status"] == "MEASURED"]
            methods[method] = {
                "status": "MEASURED" if measured else "CAPACITY_OR_WIDTH_REFUSAL",
                "warm_api_ms_median": float(np.median(measured) * 1e3) if measured else None,
                "cells": len(measured) if measured else len(rows),
                "maximum_width": max(
                    row["methods"][method].get("width", 0) for row in rows),
            }
        output[law] = methods
    return output


def make_scaling_figure(style, locality):
    all_cells = locality["cells"]
    parity = [row for row in all_cells
              if row["law"] == "unique_even_parity" and row["fixed_coordinates"] >= 1]
    timing = {str(q): timing_summary(parity, q) for q in (1, 1024)}
    support = support_summary(parity)
    negatives = negative_summary(all_cells)

    build = next(row for row in locality["builds"]
                 if row["law"] == "unique_even_parity" and row["d"] == 19)
    exemplar = next(row for row in parity if row["d"] == 19 and row["Q"] == 1024)
    exact = exemplar["methods"]["recursive_exact_integer"]
    quotient = build["bytes"]["quotient"]
    integer = build["bytes"]["integer_addon"]
    query_workspace = exact["retained_bytes"] - integer
    logical_read = exact["work"]["bytes_read"]
    memory = {
        "d": 19, "Q": 1024, "quotient_bytes": quotient,
        "integer_plan_bytes": integer, "per_query_workspace_bytes": query_workspace,
        "logical_read_bytes_estimate": logical_read,
    }

    colors = {
        "raw_packed_direct": style.OKABE_ITO["verm"],
        "weighted_unique_direct": style.OKABE_ITO["green"],
        "recursive_exact_integer": style.OKABE_ITO["blue"],
    }
    labels = {
        "raw_packed_direct": "raw packed",
        "weighted_unique_direct": "weighted unique",
        "recursive_exact_integer": "exact recursive",
    }
    markers = {"raw_packed_direct": "o", "weighted_unique_direct": "s",
               "recursive_exact_integer": "^"}

    fig = plt.figure(figsize=(style.COL_DOUBLE_IN, 6.35), layout="constrained")
    grid = fig.add_gridspec(2, 6, height_ratios=(1.0, 1.05), hspace=0.18, wspace=0.35)
    axes = [fig.add_subplot(grid[0, 0:2]), fig.add_subplot(grid[0, 2:4]),
            fig.add_subplot(grid[0, 4:6]), fig.add_subplot(grid[1, 0:3]),
            fig.add_subplot(grid[1, 3:6])]

    for ax, q, letter in zip(axes[:2], (1, 1024), ("(a)", "(b)")):
        for method in labels:
            rows = timing[str(q)][method]
            x = np.asarray([row["N"] for row in rows])
            mid = np.asarray([row["median_ms"] for row in rows])
            low = np.asarray([row["minimum_ms"] for row in rows])
            high = np.asarray([row["maximum_ms"] for row in rows])
            ax.fill_between(x, low, high, color=colors[method], alpha=0.13, linewidth=0)
            ax.plot(x, mid, marker=markers[method], ms=4.0, color=colors[method],
                    label=labels[method])
        ax.set_xscale("log", base=2); ax.set_yscale("log")
        ax.set_xlabel("rows $N$"); ax.set_ylabel("warm API time (ms)")
        ax.set_xticks([2**12, 2**15, 2**18], [r"$2^{12}$", r"$2^{15}$", r"$2^{18}$"])
        ax.text(0.05, 0.93, f"$Q={q:,}$", transform=ax.transAxes, va="top")
        style.finish_axes(ax, grid=True); style.panel_label(ax, letter)
    axes[0].legend(frameon=False, loc="upper left", bbox_to_anchor=(0.0, 0.82))

    ax = axes[2]
    d_colors = {13: style.OKABE_ITO["sky"], 14: "#70A4CC", 15: "#4C91C7",
                16: style.OKABE_ITO["blue"], 17: "#355C9A", 18: "#523D88",
                19: style.OKABE_ITO["purple"]}
    for d_text, rows in support.items():
        d = int(d_text)
        ax.plot([row["fixed_coordinates"] for row in rows],
                [row["support_fraction"] for row in rows], marker="o", ms=3.2,
                color=d_colors[d], label=f"$d={d}$")
    ax.set_yscale("log", base=2)
    ax.set_xlabel("fixed coordinates $r$"); ax.set_ylabel("support fraction")
    ax.set_xticks([1, 4, 8, 12, 16, 19])
    ax.text(0.04, 0.04, "112 distinct $(d,r,$ location$)$ regimes\n(all $r\\geq1$; $Q$-invariant)",
            transform=ax.transAxes, va="bottom", fontsize=7.5,
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.82, "pad": 1.5})
    ax.legend(frameon=False, ncol=2, loc="upper right", handlelength=1.2,
              columnspacing=0.8)
    style.finish_axes(ax, grid=True); style.panel_label(ax, "(c)")

    ax = axes[3]
    values = np.asarray([quotient, integer, query_workspace, logical_read], dtype=float) / 1024
    bar_colors = [style.OKABE_ITO["blue"], style.OKABE_ITO["sky"],
                  style.OKABE_ITO["orange"], "white"]
    bars = ax.bar(np.arange(4), values, color=bar_colors,
                  edgecolor=[style.OKABE_ITO["blue"], style.OKABE_ITO["sky"],
                             style.OKABE_ITO["orange"], style.INK],
                  hatch=[None, None, None, "///"], linewidth=1.0)
    ax.set_yscale("log"); ax.set_ylabel("KiB (log scale)")
    ax.set_xticks(np.arange(4), ["quotient", "integer\nplan", "$Q$ workspace",
                                 "logical reads\n(estimate)"])
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width()/2, value*1.12, f"{value:.1f}",
                ha="center", va="bottom", fontsize=7.5)
    ax.text(0.03, 0.95, "$d=19, Q=1{,}024$", transform=ax.transAxes, va="top")
    ax.text(3, 65, "algorithmic estimate\n(not DRAM traffic)",
            ha="center", va="center", fontsize=7.5,
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.80, "pad": 1.2})
    style.finish_axes(ax, grid=True); style.panel_label(ax, "(d)")

    ax = axes[4]
    laws = ("small_unique_support_64", "high_entropy_unique_half_support")
    x = np.arange(2); width = 0.22
    for offset, method in zip((-1, 0, 1), labels):
        heights = [negatives[law][method]["warm_api_ms_median"] for law in laws]
        plotted = [np.nan if value is None else value for value in heights]
        ax.bar(x + offset*width, plotted, width=width, color=colors[method],
               label=labels[method])
        if heights[1] is None:
            ymax = max(value for law in laws for item in negatives[law].values()
                       if (value := item["warm_api_ms_median"]) is not None)
            ax.plot(x[1] + offset*width, ymax*1.3, marker="x", ms=7,
                    mew=1.4, color=colors[method])
            ax.text(x[1] + offset*width, ymax*1.55, "refused\nwidth 25,945 > 128",
                    ha="center", va="bottom", fontsize=7.0, color=colors[method])
    ax.set_yscale("log"); ax.set_ylabel("warm API time (ms)")
    ax.set_xticks(x, ["64 unique rows", "high entropy\n(all rows unique)"])
    ax.text(0.03, 0.96, "$d=19, Q=1{,}024$", transform=ax.transAxes, va="top")
    ax.text(0.03, 0.68, "exact recursive: 500 measured cells\n+ 24 declared width refusals",
            transform=ax.transAxes, va="top", fontsize=7.5,
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.84, "pad": 1.5})
    style.finish_axes(ax, grid=True); style.panel_label(ax, "(e)")

    stem = HERE / "query_locality_completed_v1"
    style.save(fig, stem, preview=True, col="double")
    plt.close(fig)
    return {"timing": timing, "support": support, "memory": memory,
            "negative_controls": negatives}, stem


def make_physics_figure(style, physics):
    t = np.asarray(physics["times"], dtype=float)
    rows = physics["reduced_dynamics"]
    colors = {2: style.OKABE_ITO["verm"], 3: style.OKABE_ITO["blue"],
              4: style.OKABE_ITO["green"]}
    fig, axes = plt.subplots(2, 2, figsize=(style.COL_DOUBLE_IN, 5.35), layout="constrained")
    axes = axes.ravel()

    ax = axes[0]
    for row in rows:
        rank = row["retained_rank"]; y = np.asarray(row["memory_kernel_norm"], dtype=float)
        if np.any(y > 0):
            ax.plot(t[y > 0], y[y > 0], color=colors[rank], label=f"rank {rank}")
    ax.axhline(1e-18, color=colors[4], lw=1.2, ls=(0, (3, 2)))
    ax.text(0.98, 0.09, "rank 4: identically zero", transform=ax.transAxes,
            ha="right", color=colors[4], fontsize=8)
    ax.set_yscale("log"); ax.set_xlabel("time"); ax.set_ylabel(r"memory kernel $\|K(t)\|_2$")
    ax.legend(frameon=False, loc="upper right")
    style.finish_axes(ax, grid=True); style.panel_label(ax, "(a)")

    ax = axes[1]
    for row in rows:
        rank = row["retained_rank"]
        error = np.asarray(row["error"], dtype=float)
        bound = np.asarray(row["bound"], dtype=float)
        if np.any(error > 0):
            ax.plot(t[error > 0], error[error > 0], color=colors[rank],
                    label=f"rank {rank} error")
            ax.plot(t[bound > 0], bound[bound > 0], color=colors[rank], alpha=0.58,
                    ls=(0, (4, 2)), label=f"rank {rank} bound")
    ax.text(0.98, 0.07, "rank 4: zero error and zero bound", transform=ax.transAxes,
            ha="right", color=colors[4], fontsize=8)
    ax.set_yscale("log"); ax.set_xlabel("time"); ax.set_ylabel("retained-state error")
    ax.legend(frameon=True, facecolor="white", edgecolor="none", framealpha=0.82,
              ncol=2, loc="upper left", columnspacing=0.8)
    style.finish_axes(ax, grid=True); style.panel_label(ax, "(b)")

    ax = axes[2]
    ranks = [row["retained_rank"] for row in rows]
    defects = [row["volterra_trapezoid_max_defect"] for row in rows]
    draw = [value if value > 0 else 3e-7 for value in defects]
    bars = ax.bar(np.arange(3), draw, color=[colors[r] for r in ranks], width=0.62)
    ax.set_yscale("log"); ax.set_ylim(2e-7, 3e-5)
    ax.set_xticks(np.arange(3), [f"rank {r}" for r in ranks])
    ax.set_ylabel("max Duhamel/Volterra defect")
    for bar, value in zip(bars, defects):
        label = "exact 0" if value == 0 else f"{value:.2g}"
        ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()*1.16, label,
                ha="center", va="bottom", fontsize=8)
    coupling = " / ".join(f"{row['defect_norm']:.3f}" for row in rows)
    ax.text(0.98, 0.95, r"coupling $\|D\|_2$ (ranks 2/3/4)" + f"\n{coupling}",
            transform=ax.transAxes, va="top", ha="right", fontsize=8,
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.86, "pad": 1.5})
    style.finish_axes(ax, grid=True); style.panel_label(ax, "(c)")

    ax = axes[3]
    counter = physics["register_counterexample"]
    values = [counter["lost_register_weighted_rms"], counter["transported_register_loss"]]
    bars = ax.bar([0, 1], values, width=0.56,
                  color=[style.OKABE_ITO["orange"], style.OKABE_ITO["green"]])
    ax.set_ylim(0, 0.58); ax.set_ylabel("weighted RMS loss")
    ax.set_xticks([0, 1], ["discarded\nregister", "transported\nregister"])
    for bar, value in zip(bars, values):
        ax.text(bar.get_x()+bar.get_width()/2, max(value, 0.012)+0.015,
                f"{value:.1f}", ha="center", va="bottom", fontweight="bold")
    ax.annotate("same observable", xy=(1, 0.02), xytext=(0.5, 0.34),
                ha="center", arrowprops={"arrowstyle": "->", "lw": 0.8,
                                           "color": style.INK})
    ax.text(0.98, 0.92, "transport preserves the task register;\nprojection alone loses it",
            transform=ax.transAxes, ha="right", va="top", fontsize=8,
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.86, "pad": 1.5})
    style.finish_axes(ax, grid=False, zero_ref=0); style.panel_label(ax, "(d)")

    stem = HERE / "controlled_effective_dynamics_v1"
    style.save(fig, stem, preview=True, col="double")
    plt.close(fig)
    arrays = {
        "times": physics["times"],
        "reduced_dynamics": physics["reduced_dynamics"],
        "register_counterexample": physics["register_counterexample"],
    }
    return arrays, stem


def main() -> int:
    HERE.mkdir(parents=True, exist_ok=True)
    style = load_style(); style.use_house_style()
    locality = json.loads(LOCALITY_PATH.read_text())
    physics = json.loads(PHYSICS_PATH.read_text())
    scaling_arrays, scaling_stem = make_scaling_figure(style, locality)
    physics_arrays, physics_stem = make_physics_figure(style, physics)
    arrays = {
        "schema": "completed-results-figure-arrays/1",
        "query_locality": scaling_arrays,
        "controlled_effective_dynamics": physics_arrays,
    }
    save_json(ARRAYS_PATH, arrays)
    outputs = [scaling_stem.with_suffix(suffix) for suffix in (".pdf", ".png")]
    outputs += [physics_stem.with_suffix(suffix) for suffix in (".pdf", ".png")]
    provenance = {
        "schema": "completed-results-figures-provenance/1",
        "generator_sha256": sha256(Path(__file__)),
        "style_sha256": sha256(STYLE_PATH),
        "raw_sources": {
            str(LOCALITY_PATH.relative_to(EXTENSION)): sha256(LOCALITY_PATH),
            str(PHYSICS_PATH.relative_to(EXTENSION)): sha256(PHYSICS_PATH),
        },
        "generated_arrays_sha256": sha256(ARRAYS_PATH),
        "generated_arrays_canonical_sha256": canonical_sha(arrays),
        "outputs": {path.name: sha256(path) for path in outputs},
        "claim_boundaries": [
            "Warm API timing is shown; cold compilation and build cost are excluded.",
            "Logical byte reads are operation-count estimates, not measured DRAM traffic.",
            "The exact recursive kernel was measured in 500 cells and refused in 24 high-entropy width cells.",
            "The physics panels are controlled exact-identity illustrations, not corpus performance.",
        ],
    }
    save_json(PROVENANCE_PATH, provenance)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
