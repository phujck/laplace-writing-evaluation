"""Render the EigenEngine core-paper figures FROM the measured corpus experiments
(paper_eigen/_experiments/corpus_experiments.json) and the appendix data
(paper_eigen/_experiments/corpus_appendix.json). Authors are shown by anonymised ID (A = the
author, 1..7 = collaborators); names live only in the appendix tables. Data check-plots first -
every figure is a direct read of measured numbers. Writes PDF+PNG to paper_eigen/figures/.

Run (after corpus_experiments.py and corpus_appendix.py): python scripts/corpus_figures.py
"""
from __future__ import annotations

import json
import math
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXP = os.path.join(ROOT, "paper_eigen", "_experiments", "corpus_experiments.json")
APX = os.path.join(ROOT, "paper_eigen", "_experiments", "corpus_appendix.json")
FIGDIR = os.path.join(ROOT, "paper_eigen", "figures")

# house palette, matched to eigenengine.sty (ink / phys / acc / faint)
INK = "#1A1A2E"
ACCENT = "#2C6FAD"   # phys - deep macro-scale blue
MUTED = "#9AA5B1"    # faint
WARN = "#C0392B"     # acc - muted vermilion

plt.rcParams.update({
    "font.size": 9, "font.family": "serif", "mathtext.fontset": "cm",
    # embed TrueType/Type-42 fonts, never matplotlib's Type-3 PDF default
    "pdf.fonttype": 42, "ps.fonttype": 42,
    "axes.edgecolor": INK, "axes.labelcolor": INK,
    "xtick.color": INK, "ytick.color": INK, "text.color": INK,
    "xtick.direction": "in", "ytick.direction": "in",
    "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 300,
})


def _save(fig, name):
    os.makedirs(FIGDIR, exist_ok=True)
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(FIGDIR, f"{name}.{ext}"), bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {name}.pdf / .png")


def fig_grade_histogram(e1):
    """Geometric compression at two scales. The demonstration corpus (blue: papers -> clusters ->
    themes) and the engine's full store (grey: the deeper grade ladder) fall along the same slope --
    the branching b is a property of the fold, not of either substrate's size."""
    cl, sh = e1["corpus_ladder"], e1["store_histogram"]
    fig, ax = plt.subplots(figsize=(4.6, 3.2))

    # the engine's full store: node count vs grade (corroboration), plotted as a faint line+markers
    sgr = sorted(int(g) for g in sh["counts_by_grade"])
    svals = [sh["counts_by_grade"][str(g)] if str(g) in sh["counts_by_grade"] else sh["counts_by_grade"][g] for g in sgr]
    n_store_ladder = len(sh["base_ladder"])
    ax.plot(sgr[:n_store_ladder], svals[:n_store_ladder], "-o", color=MUTED, ms=4, lw=1.2,
            zorder=2, label=f"full store, {sh['total_nodes']} nodes  ($b\\approx{sh['branching_b']}$)")
    ax.plot(sgr[n_store_ladder:], svals[n_store_ladder:], "o", color=MUTED, ms=3, alpha=0.5, zorder=2)

    # the demonstration corpus: papers -> clusters -> themes (the frozen spine), as bold bars
    cvals = cl["ladder"]
    cgr = list(range(len(cvals)))
    ax.bar(cgr, cvals, color=ACCENT, width=0.5, zorder=3, alpha=0.92,
           label=f"corpus: {cl['base_papers']} papers $\\to$ {cl['apex_themes']} themes  ($b\\approx{cl['branching_b']}$)")
    for x, (v, lab) in enumerate(zip(cvals, cl["ladder_labels"])):
        ax.text(x, v * 1.25, f"{v}\n{lab}", ha="center", va="bottom", fontsize=7.5, color=INK)

    ax.set_yscale("log")
    ax.set_xlabel("fold level (0 = base, higher = coarser)")
    ax.set_ylabel("number of nodes (log scale)")
    ax.set_xticks(sgr)
    ax.set_ylim(top=max(svals) * 4)
    ax.legend(loc="upper right", frameon=False, fontsize=7.2)
    _save(fig, "fig_grade_histogram")


def fig_apex_scaling(e2, key2id):
    rows = e2["rows"]
    xs = [r["base_papers"] for r in rows]
    ys = [r["apex_themes"] for r in rows]
    fig, ax = plt.subplots(figsize=(4.4, 3.0))
    ax.scatter(xs, ys, color=ACCENT, s=42, zorder=3, edgecolor="white", linewidth=0.6)
    for r in rows:
        ax.annotate(key2id.get(r["author"], "?"), (r["base_papers"], r["apex_themes"]),
                    textcoords="offset points", xytext=(5, 3), fontsize=8, color=INK)
    pw = e2["fits"].get("power")
    if pw:
        xx = sorted(xs)
        yy = [math.exp(pw["intercept"]) * (x ** pw["slope"]) for x in xx]
        ax.plot(xx, yy, color=WARN, lw=1.4, ls="--", zorder=2,
                label=f"apex $\\propto$ base$^{{{pw['slope']}}}$  ($R^2={pw['r2']}$)")
        ax.legend(loc="upper left", frameon=False, fontsize=7.5)
    ax.set_xscale("log")
    ax.set_xlabel("base: paper-instances in the corpus (log scale)")
    ax.set_ylabel("apex: theme-summary nodes")
    _save(fig, "fig_apex_scaling")


def fig_citation_free(e3, key2id):
    rows = sorted(e3["rows"], key=lambda r: r["citation_free_frac"])
    ids = [key2id.get(r["centre"], "?") for r in rows]
    fracs = [r["citation_free_frac"] for r in rows]
    colors = [WARN if key2id.get(r["centre"]) == "A" else ACCENT for r in rows]
    fig, ax = plt.subplots(figsize=(4.4, 3.0))
    ax.barh(ids, fracs, color=colors)
    m = e3["citation_free_frac_mean"]
    ax.axvline(m, color=INK, lw=1.0, ls=":")
    ax.text(m, len(ids) - 0.4, f" mean {m}", fontsize=7.5, va="top")
    ax.set_xlim(0, 1.05)
    ax.set_xlabel("fraction of cross-links that are citation-free")
    ax.set_ylabel("centred author (ID)")
    _save(fig, "fig_citation_free")


def fig_crosslink_network(apx):
    ids = apx["id_order"]
    papers = {L["id"]: L["n_papers"] for L in apx["legend"]}
    n = len(ids)
    pos = {}
    for k, i in enumerate(ids):
        th = math.pi / 2 - 2 * math.pi * k / n
        pos[i] = (math.cos(th), math.sin(th))
    fig, ax = plt.subplots(figsize=(4.6, 4.6))
    for e in apx["edges"]:
        if e["sim"] < 0.10:
            continue
        x0, y0 = pos[e["i"]]
        x1, y1 = pos[e["j"]]
        col = ACCENT if e["citation_free"] else WARN
        ax.plot([x0, x1], [y0, y1], color=col, lw=0.6 + 9 * (e["sim"] - 0.09),
                alpha=0.75, zorder=1, solid_capstyle="round")
    for i in ids:
        x, y = pos[i]
        s = 120 + 2.0 * math.sqrt(papers[i]) * 14
        ax.scatter([x], [y], s=s, color="white", edgecolor=INK, linewidth=1.2, zorder=3)
        ax.text(x, y, i, ha="center", va="center", fontsize=10, fontweight="bold",
                color=INK, zorder=4)
    ax.plot([], [], color=ACCENT, lw=2.4, label="citation-free")
    ax.plot([], [], color=WARN, lw=2.4, label="shared paper(s)")
    ax.legend(loc="lower center", frameon=False, fontsize=8, ncol=2,
              bbox_to_anchor=(0.5, -0.04))
    ax.set_xlim(-1.35, 1.35)
    ax.set_ylim(-1.35, 1.35)
    ax.set_aspect("equal")
    ax.axis("off")
    _save(fig, "fig_crosslink_network")


def fig_coupling_heatmap(apx):
    ids = apx["id_order"]
    M = np.array(apx["coupling_matrix"], dtype=float)
    masked = np.ma.array(M, mask=np.eye(len(ids), dtype=bool))   # hide the self-diagonal
    fig, ax = plt.subplots(figsize=(4.6, 4.0))
    cmap = plt.cm.get_cmap("YlGnBu").copy()
    cmap.set_bad("white")
    im = ax.imshow(masked, cmap=cmap, vmin=0, vmax=float(masked.max()))
    ax.set_xticks(range(len(ids)))
    ax.set_yticks(range(len(ids)))
    ax.set_xticklabels(ids)
    ax.set_yticklabels(ids)
    ax.set_xlabel("author ID")
    ax.set_ylabel("author ID")
    for i in range(len(ids)):
        for j in range(len(ids)):
            if i == j:
                continue
            v = M[i][j]
            ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=6.5,
                    color=(INK if v < 0.16 else "white"))
    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cb.set_label("strongest thematic coupling", fontsize=8)
    _save(fig, "fig_coupling_heatmap")


def main():
    exp = json.load(open(EXP, encoding="utf-8"))
    apx = json.load(open(APX, encoding="utf-8"))
    key2id = {L["key"]: L["id"] for L in apx["legend"]}
    print("rendering figures (anonymised IDs)")
    fig_grade_histogram(exp["e1_grade_histogram"])
    fig_apex_scaling(exp["e2_apex_vs_base"], key2id)
    fig_citation_free(exp["e3_per_centre_crosslink"], key2id)
    fig_crosslink_network(apx)
    fig_coupling_heatmap(apx)


if __name__ == "__main__":
    main()
