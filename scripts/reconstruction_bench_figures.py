#!/usr/bin/env python3
"""Figures for the reconstruction benchmark - v2, redesigned at his rejection
of the first set ("completely reimagine how you're going to present the data
so it's intuitive what the person is seeing").

Design rule: one figure, one message, visible in three seconds, linear scales
so disparity reads as geometry. Palette: the validated categorical slots;
correctness never color-alone.

  figA  same answers, different bills   - 3 horizontal bars, linear
  figB  what you get for what you spend - 4-dot scatter, answered vs tokens
  figC  the gap only widens             - linear history sweep, shaded wedge
  figD  what a query touches            - waffle, ~13 of 1000 cells lit

  PYTHONPATH=src python3 scripts/reconstruction_bench_figures.py
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch

REPO = Path(__file__).resolve().parent.parent

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
BLUE = "#2a78d6"
ORANGE = "#eb6834"
AQUA = "#1baf7a"
YELLOW = "#eda100"
YELLOW_INK = "#8a5d00"  # label ink for the low-contrast yellow (relief rule)


def newfig(w, h):
    fig, ax = plt.subplots(figsize=(w, h), dpi=160)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(colors=MUTED, labelsize=9, length=0)
    return fig, ax


def fig_a_bills(report, out: Path):
    """Orientation questions (classes 1-4): equal or better answers, the bill
    as geometry. Linear scale, three bars, direct labels, no axis to decode."""
    rows = report["rows"]
    orient = [r["task"] for r in rows if r["arm"] == "A"
              and r["class"] in ("current-aim", "standing-law",
                                 "session-state", "project-state")]
    n = len(orient)

    def stats(arm):
        sub = [r for r in rows if r["arm"] == arm and r["task"] in orient]
        ok = sum(1 for r in sub if r["correct"])
        return ok, sub[0]["tokens_context"]  # flat arms: the set, once; A: the wake

    a_ok, a_tok = stats("A")
    b_ok, b_tok = stats("B")
    bp_ok, bp_tok = stats("B+")

    entries = [
        ("wake reconstruction", a_tok, a_ok, BLUE, INK),
        ("flat read, standard set", b_tok, b_ok, ORANGE, INK),
        ("flat read, charitable set", bp_tok, bp_ok, AQUA, INK),
    ]
    fig, ax = newfig(9.2, 3.9)
    y = [2, 1, 0]
    for (label, tok, ok, color, _), yi in zip(entries, y):
        ax.barh(yi, tok, 0.52, color=color, zorder=3)
        ax.text(-3000, yi, label, ha="right", va="center", fontsize=10,
                color=INK2, linespacing=1.4)
        ax.text(tok + 2500, yi, f"{tok:,} tok · {ok}/{n}",
                va="center", fontsize=10.5, color=INK,
                fontweight="bold" if yi == 2 else "normal")
    ax.set_xlim(0, bp_tok * 1.38)
    ax.set_ylim(-0.55, 3.05)
    ax.set_yticks([])
    ax.set_xticks([])
    ax.set_title(
        "Context tokens to answer the twelve orientation questions",
        fontsize=12, color=INK, loc="left", pad=10)
    fig.tight_layout(rect=(0.16, 0.02, 1, 1))
    fig.savefig(out / "figA_bills.png", facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)


def fig_b_value(report, out: Path):
    """All 18 tasks: answered (y) against what the session paid (x). Four dots.
    Up and left is better; the axes need no explanation."""
    s = report["headline"]["session_tokens"]
    answered = {arm: report["summary"][arm]["correct"] for arm in ("A", "B", "B+", "C")}
    pts = [
        ("A", "wake reconstruction", s["A"], answered["A"], BLUE, INK),
        ("B", "flat read, standard", s["B"], answered["B"], ORANGE, INK),
        ("B+", "flat read, charitable", s["B+"], answered["B+"], AQUA, INK),
        ("C", "grep per question", s["C"], answered["C"], YELLOW, YELLOW_INK),
    ]
    fig, ax = newfig(8.6, 5.2)
    ax.yaxis.grid(True, color=GRID, linewidth=0.7)
    ax.set_axisbelow(True)
    offsets = {
        "wake reconstruction": ((-8, 26), "left"),
        "flat read, standard": ((20, -26), "left"),
        "flat read, charitable": ((22, -6), "left"),
        "grep per question": ((-22, 4), "right"),
    }
    for _, label, x, yv, color, ink in pts:
        ax.scatter(x / 1000, yv, s=340, color=color, zorder=3,
                   edgecolors=SURFACE, linewidths=2)
        (dx, dy), ha = offsets[label]
        ax.annotate(f"{label}\n{x / 1000:.0f}k tokens → {yv}/18",
                    (x / 1000, yv), textcoords="offset points",
                    xytext=(dx, dy), fontsize=10, color=ink, ha=ha,
                    linespacing=1.5)
    ax.set_xlim(-25, 960)
    ax.set_ylim(0, 18.9)
    ax.set_yticks([0, 6, 12, 18])
    ax.set_xticks([0, 250, 500, 750])
    ax.set_xticklabels(["0", "250k", "500k", "750k"])
    ax.set_xlabel("context tokens per session", fontsize=9.5, color=INK2)
    ax.set_ylabel("questions answered, of 18", fontsize=9.5, color=INK2)
    ax.set_title("Questions answered vs context tokens spent, one session per arm",
                 fontsize=12, color=INK, loc="left", pad=10)
    fig.tight_layout()
    fig.savefig(out / "figB_value.png", facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)


DIARY_HEAD = re.compile(rb"(?m)^## ")


def _blob(commit: str, path: str) -> bytes:
    r = subprocess.run(["git", "show", f"{commit}:{path}"], cwd=REPO,
                       capture_output=True)
    return r.stdout if r.returncode == 0 else b""


def fallback_set_bytes(commit: str) -> int:
    total = 0
    for name in ("CLAUDE.md", "AGENTS.md", "HANDOFF.md", "EIGEN_ARCHITECTURE.md"):
        total += len(_blob(commit, name))
    r = subprocess.run(["git", "ls-tree", "--name-only", commit], cwd=REPO,
                       capture_output=True, text=True)
    handoffs = sorted(n for n in r.stdout.splitlines()
                      if n.startswith("SESSION_HANDOFF_"))
    if handoffs:
        total += len(_blob(commit, handoffs[-1]))
    diary = _blob(commit, "EIGEN_DIARY.md")
    heads = [m.start() for m in DIARY_HEAD.finditer(diary)]
    total += len(diary[heads[-5]:]) if len(heads) >= 5 else len(diary)
    return total


def fig_c_gap(report, out: Path):
    """Eight weeks of this repo's own history, linear scale: the flat read
    climbs with the corpus, the wake is capped in code. The wedge is the point."""
    r = subprocess.run(
        ["git", "log", "--reverse", "--format=%H %cs", "--", "EIGEN_DIARY.md"],
        cwd=REPO, capture_output=True, text=True)
    by_date: dict[str, str] = {}
    for sha, date in (ln.split() for ln in r.stdout.splitlines()):
        by_date[date] = sha
    sampled = sorted(by_date.items())
    step = max(1, len(sampled) // 20)
    sampled = sampled[::step] + ([sampled[-1]] if sampled[-1] != sampled[::step][-1] else [])

    dates, toks = [], []
    for date, sha in sampled:
        b = fallback_set_bytes(sha)
        if b:
            dates.append(date)
            toks.append(b / 4000)  # k tokens
    wake_now = report["wake_bytes"] / 4000

    fig, ax = newfig(9.2, 4.9)
    ax.yaxis.grid(True, color=GRID, linewidth=0.7)
    ax.set_axisbelow(True)
    x = np.arange(len(dates))
    ax.fill_between(x, [wake_now] * len(x), toks, color=ORANGE, alpha=0.12,
                    zorder=1)
    ax.plot(x, toks, color=ORANGE, linewidth=2.4, zorder=3)
    ax.plot(x, [wake_now] * len(x), color=BLUE, linewidth=2.4, zorder=3)
    ax.annotate("flat fallback set", (x[len(x) // 3], max(toks) + 5),
                fontsize=10.5, color=ORANGE)
    ax.annotate(f"{toks[-1]:.0f}k", (x[-1], toks[-1]),
                textcoords="offset points", xytext=(6, 0), fontsize=10,
                color=ORANGE, va="center", fontweight="bold")
    ax.annotate(f"{toks[0]:.0f}k", (x[0], toks[0]),
                textcoords="offset points", xytext=(-2, -14), fontsize=10,
                color=ORANGE)
    ax.annotate("wake payload (grade-0 cap)", (x[2], wake_now + 4),
                fontsize=10.5, color=BLUE)
    ax.annotate(f"{wake_now:.0f}k", (x[-1], wake_now),
                textcoords="offset points", xytext=(6, 0), fontsize=10,
                color=BLUE, va="center", fontweight="bold")
    tick_idx = list(range(0, len(dates), max(1, len(dates) // 6)))
    ax.set_xticks(tick_idx)
    ax.set_xticklabels([dates[i][5:] for i in tick_idx], fontsize=9, color=MUTED)
    ax.set_ylim(0, max(toks) * 1.22)
    ax.set_ylabel("context tokens, thousands", fontsize=9.5, color=INK2)
    ax.set_title("Orientation cost across eight weeks of repository history",
                 fontsize=12, color=INK, loc="left", pad=10)
    fig.tight_layout()
    fig.savefig(out / "figC_gap.png", facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)


def fig_d_touch(report, out: Path):
    """The waffle: 1,000 cells = the 12,335-leaf corpus; the lit cells are what
    one retrieval query materializes. A flat read pays for every cell."""
    frac = np.mean([
        (r["packet"].get("materialized") or 0) / 12335
        for r in report["rows"] if r["arm"] == "A" and r.get("packet")
    ])
    lit = max(1, round(frac * 1000))
    cols, rows_n = 50, 20
    fig, ax = newfig(8.6, 3.3)
    rng = np.random.default_rng(20260728)
    lit_idx = set(rng.choice(cols * rows_n, size=lit, replace=False).tolist())
    for i in range(cols * rows_n):
        r_, c_ = divmod(i, cols)
        color = BLUE if i in lit_idx else GRID
        ax.add_patch(plt.Rectangle((c_ * 1.0, r_ * 1.0), 0.82, 0.82,
                                   color=color, zorder=3 if i in lit_idx else 2))
    ax.set_xlim(-0.5, cols + 17)
    ax.set_ylim(-1.2, rows_n + 0.4)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_aspect("equal")
    ax.text(cols + 1.2, rows_n - 1.2,
            f"■ one retrieval query: {frac * 100:.1f}%",
            fontsize=10.5, color=BLUE, va="top", fontweight="bold")
    ax.text(cols + 1.2, rows_n - 3.6,
            "■ flat read: 100%",
            fontsize=10.5, color=MUTED, va="top")
    ax.set_title("Share of 12,335 corpus documents read per query",
                 fontsize=12, color=INK, loc="left", pad=10)
    fig.tight_layout()
    fig.savefig(out / "figD_touch.png", facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", default="evidence/reconstruction_bench_2026-07-28")
    args = ap.parse_args()
    bundle = REPO / args.bundle
    report = json.loads((bundle / "rows.json").read_text())
    fig_a_bills(report, bundle)
    fig_b_value(report, bundle)
    fig_c_gap(report, bundle)
    fig_d_touch(report, bundle)
    for f in sorted(bundle.glob("fig*.png")):
        print(f.name, f.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
