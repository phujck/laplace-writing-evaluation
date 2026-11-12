"""figures.py - three figures, one message each, linear scales. The bench extra, imported lazily.

The house figure law, from the author's rejection of the first bench figure set ("completely
reimagine how you're going to present the data so it's intuitive what the person is seeing"):
ONE figure, ONE message, visible in three seconds, LINEAR scales so a disparity reads as geometry
rather than as an axis to decode, and correctness never carried by colour alone.

    fig A   who answers what          correctness per class x arm - the correctness figure, and
                                      it comes first because correctness comes first
    fig B   what an answer costs      tokens touched per arm, over CORRECT tasks only, so the
                                      bar is "what it cost the arm to be right"
    fig C   intelligence paid once    the cost-shape figure: fold cost amortized against
                                      per-query tokens, with query model calls stated on the face
    fig D   who paid a model          THE MONEY FIGURE (Phase 3): fold model tokens per arm, on a
                                      linear scale, so RAPTOR's bill stands beside six literal
                                      zeros. One message: this is the dimension the arms differ
                                      on, and it is paid ONCE - the query model calls are zero
                                      for every arm including RAPTOR's. A zero is drawn as a
                                      labelled absence rather than an invisible bar, because a
                                      bar chart where most bars have length zero reads as missing
                                      data unless the zeros are named.

matplotlib is a BENCH EXTRA, not an atlas runtime dependency - the runtime is numpy only. The
import lives inside ``draw`` and the caller is told loudly and by name when it is absent; figures
are skipped, never faked, and the run is still complete without them.

Nothing here computes a number. Every value is read from ``figure_input.json``, which
``summary.py`` produced by recomputing from the rows and asserting against the banked manifest. A
figure that did its own arithmetic would be a second, unasserted instrument.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# The validated categorical slots from the house palette, plus the ink and surface tones.
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"

#: SEVEN slots, extended from five in Phase 3 - and the extension was forced by a defect, not by
#: taste. With five colours and seven arms the palette wrapped: ``raptor`` was drawn in
#: ``flat_read:B``'s grey and ``incumbent_arch`` in ``flat_read:B+``'s, so the legend of the
#: correctness figure named seven arms and showed five colours. A figure whose whole law is "one
#: message, visible in three seconds" cannot ask the reader to disambiguate two arms by position.
#:
#: The order is deliberate: the two FLAT arms keep the neutral greys (they are the baseline
#: family and should recede), and the five ranking arms take distinct hues drawn from the
#: colourblind-safe family - blue, vermillion, green, purple, ochre. No two adjacent slots are
#: confusable under deuteranopia, and nothing in any figure is carried by colour alone: every bar
#: is directly labelled with its value and every axis is linear.
ARM_COLORS = ("#c3c2b7", "#8a8778", "#2a78d6", "#eb6834", "#1baf7a", "#8256b4", "#a8791f")


class FiguresUnavailable(RuntimeError):
    """matplotlib is absent. Named, printed, and the run continues without figures."""


def _mpl():
    try:
        import matplotlib
    except ImportError as exc:
        raise FiguresUnavailable(
            "matplotlib is not installed; figures are skipped. Install the atlas 'bench' extra "
            "(pip install -e 'atlas[bench]') to draw them. The run's numbers are unaffected."
        ) from exc
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def _newfig(plt, w: float, h: float):
    fig, ax = plt.subplots(figsize=(w, h), dpi=160)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(colors=MUTED, labelsize=9, length=0)
    return fig, ax


def fig_a_correctness(data: dict[str, Any], out: Path) -> Path:
    """MESSAGE: which arm answers which kind of question. Counts, linear, direct labels."""
    plt = _mpl()
    table = data["correctness"]
    arms, classes = table["arms"], table["classes"]
    fig, ax = _newfig(plt, 11.0, 5.2)
    width = 0.8 / max(1, len(arms))
    for a, arm in enumerate(arms):
        xs = [i + a * width for i in range(len(classes))]
        ys = [table["per_class"][cl][arm]["correct"] for cl in classes]
        ax.bar(xs, ys, width=width * 0.92, color=ARM_COLORS[a % len(ARM_COLORS)],
               label=arm, zorder=3)
        for x, y in zip(xs, ys, strict=True):
            if y:
                ax.text(x, y + 0.06, str(y), ha="center", va="bottom", fontsize=8, color=INK2)
    total = table["per_class"][classes[0]][arms[0]]["total"] if classes else 0
    ax.set_xticks([i + 0.4 - width / 2 for i in range(len(classes))])
    ax.set_xticklabels(classes, fontsize=9, color=INK2, rotation=20, ha="right")
    ax.set_ylim(0, max(1, total) + 0.6)
    ax.set_yticks(range(0, max(1, total) + 1))
    ax.yaxis.grid(True, color=GRID, zorder=0)
    ax.set_ylabel(f"questions answered (out of {total} per class)", fontsize=9, color=INK2)
    ax.set_title("Who answers what", fontsize=13, color=INK, loc="left", pad=16)
    # The legend sits BELOW the plot: at the top it collides with the title, and a title a reader
    # has to squint through is the opposite of one message in three seconds.
    ax.legend(frameon=False, fontsize=9, ncol=len(arms), loc="upper center",
              bbox_to_anchor=(0.5, -0.26), labelcolor=INK2)
    fig.tight_layout()
    fig.savefig(out, facecolor=SURFACE)
    plt.close(fig)
    return out


def fig_b_tokens(data: dict[str, Any], out: Path) -> Path:
    """MESSAGE: what being right cost. Median tokens touched over CORRECT tasks only, linear."""
    plt = _mpl()
    costs = data["cost"]
    arms = [a for a in data["correctness"]["arms"]
            if costs[a]["tokens_touched_median_correct"] is not None]
    values = [costs[a]["tokens_touched_median_correct"] for a in arms]
    labels = [f"{a}  ({costs[a]['correct']}/{costs[a]['total_tasks']} right)" for a in arms]
    fig, ax = _newfig(plt, 10.0, 0.85 * len(arms) + 2.2)
    ys = list(range(len(arms)))[::-1]
    ax.barh(ys, values, height=0.55,
            color=[ARM_COLORS[i % len(ARM_COLORS)] for i in range(len(arms))], zorder=3)
    for y, v in zip(ys, values, strict=True):
        ax.text(v + max(values) * 0.012, y, f"{v:,}", va="center", fontsize=10, color=INK)
    ax.set_yticks(ys)
    ax.set_yticklabels(labels, fontsize=10, color=INK2)
    ax.set_xlim(0, max(values) * 1.16 if values else 1)
    ax.xaxis.grid(True, color=GRID, zorder=0)
    ax.set_xlabel("tokens touched per answered question (median, correct tasks only)",
                  fontsize=9, color=INK2)
    ax.set_title("What an answer costs", fontsize=13, color=INK, loc="left", pad=14)
    fig.tight_layout()
    fig.savefig(out, facecolor=SURFACE)
    plt.close(fig)
    return out


def fig_c_cost_shape(data: dict[str, Any], out: Path) -> Path:
    """MESSAGE: intelligence paid once. Fold amortized against per-query tokens, calls stated."""
    plt = _mpl()
    costs = data["cost"]
    arms = data["correctness"]["arms"]
    fold_per_query = [costs[a]["fold_amortized_per_query"]["wall_seconds_per_query"] for a in arms]
    per_query_tokens = [costs[a]["tokens_touched_median_correct"] or 0 for a in arms]
    calls = [costs[a]["query_model_calls"] for a in arms]

    fig, ax = _newfig(plt, 10.0, 5.6)
    # Arms cluster hard at the origin - the cheap ones are cheap on BOTH axes - so labels are
    # staggered by rank within a cluster. Deterministic, not jittered: the same data always
    # produces the same picture.
    order = sorted(range(len(arms)), key=lambda i: (per_query_tokens[i], fold_per_query[i]))
    offsets = {index: rank for rank, index in enumerate(order)}
    for i, arm in enumerate(arms):
        ax.scatter([per_query_tokens[i]], [fold_per_query[i]], s=190,
                   color=ARM_COLORS[i % len(ARM_COLORS)], zorder=3)
        dy = 8 + 26 * (offsets[i] % 3) if fold_per_query[i] < max(fold_per_query or [1]) / 4 else 8
        ax.annotate(f"{arm}  ({calls[i]} model calls/query)",
                    (per_query_tokens[i], fold_per_query[i]),
                    textcoords="offset points", xytext=(14, dy), fontsize=9, color=INK2)
    ax.set_xlim(0, max(per_query_tokens) * 1.30 if any(per_query_tokens) else 1)
    ax.set_ylim(0, max(fold_per_query) * 1.35 if any(fold_per_query) else 1)
    ax.xaxis.grid(True, color=GRID, zorder=0)
    ax.yaxis.grid(True, color=GRID, zorder=0)
    ax.set_xlabel("tokens touched per answered question (median)", fontsize=9, color=INK2)
    ax.set_ylabel("fold seconds amortized per query", fontsize=9, color=INK2)
    ax.set_title("Intelligence paid once: the fold bill against the query bill",
                 fontsize=13, color=INK, loc="left", pad=14)
    ax.text(0.0, -0.20, "Every Tier-1 arm makes ZERO model calls per query - counted by a "
                        "wrapper, not declared. Linear scales on both axes.",
            transform=ax.transAxes, fontsize=8.5, color=MUTED)
    fig.tight_layout()
    fig.savefig(out, facecolor=SURFACE)
    plt.close(fig)
    return out


def fig_d_fold_bill(data: dict[str, Any], out: Path) -> Path:
    """MESSAGE: one arm paid a model to fold; none pays one to query. Linear, zeros named."""
    plt = _mpl()
    costs = data["cost"]
    arms = data["correctness"]["arms"]
    fold_tokens = [costs[a]["fold"]["model_tokens"] for a in arms]
    fold_calls = [costs[a]["fold"]["model_calls"] for a in arms]
    query_calls = [costs[a]["query_model_calls"] for a in arms]

    fig, ax = _newfig(plt, 10.0, 0.8 * len(arms) + 2.4)
    ys = list(range(len(arms)))[::-1]
    ax.barh(ys, fold_tokens, height=0.55,
            color=[ARM_COLORS[i % len(ARM_COLORS)] for i in range(len(arms))], zorder=3)
    top = max(fold_tokens) if any(fold_tokens) else 1
    for y, tokens, calls in zip(ys, fold_tokens, fold_calls, strict=True):
        if tokens:
            ax.text(tokens + top * 0.012, y, f"{tokens:,} tokens in {calls} calls",
                    va="center", fontsize=10, color=INK)
        else:
            # A zero-length bar is indistinguishable from a missing one; say the word.
            ax.text(top * 0.012, y, "zero - no model in the fold",
                    va="center", fontsize=9.5, color=MUTED)
    ax.set_yticks(ys)
    ax.set_yticklabels(arms, fontsize=10, color=INK2)
    ax.set_xlim(0, top * 1.42)
    ax.xaxis.grid(True, color=GRID, zorder=0)
    ax.set_xlabel("model tokens spent at FOLD time (prompt estimate, bytes/4)",
                  fontsize=9, color=INK2)
    ax.set_title("Who paid a model, and when", fontsize=13, color=INK, loc="left", pad=14)
    # Two short lines rather than one long one: at this figure width a single caption runs off
    # the canvas, and a caption a reader cannot finish is not a caption.
    ax.text(0.0, -0.20 - 0.012 * len(arms),
            f"Query-time model calls, every arm: {', '.join(str(c) for c in query_calls)} — "
            f"counted by a wrapper, not declared.",
            transform=ax.transAxes, fontsize=8.5, color=MUTED)
    ax.text(0.0, -0.26 - 0.012 * len(arms),
            f"The fold bill is paid ONCE and amortized; the query bill is zero for all "
            f"{len(arms)} arms. Linear scale.",
            transform=ax.transAxes, fontsize=8.5, color=MUTED)
    fig.tight_layout()
    fig.savefig(out, facecolor=SURFACE)
    plt.close(fig)
    return out


def draw_all(run_dir: Path) -> list[Path]:
    """Draw all four from ``figure_input.json``. Raises FiguresUnavailable if matplotlib is not."""
    run_dir = Path(run_dir)
    data = json.loads((run_dir / "figure_input.json").read_text(encoding="utf-8"))
    return [
        fig_a_correctness(data, run_dir / "figA_correctness.png"),
        fig_b_tokens(data, run_dir / "figB_tokens_at_correctness.png"),
        fig_c_cost_shape(data, run_dir / "figC_cost_shape.png"),
        fig_d_fold_bill(data, run_dir / "figD_fold_bill.png"),
    ]


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="draw the bench figures from figure_input.json")
    ap.add_argument("run_dir", type=Path)
    args = ap.parse_args(argv)
    try:
        for path in draw_all(args.run_dir):
            print(f"wrote {path}")
    except FiguresUnavailable as exc:
        print(f"FIGURES SKIPPED {exc}")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
