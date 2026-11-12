#!/usr/bin/env python3
"""Generate minimal toy-dynamics demonstrations for the loss-geometry papers.

The simulations are deliberately small.  They are not neural models; they
are executable checks that the manuscript's selector produces the qualitative
regimes claimed in the text:

1. Shared-register reuse is efficient while evaluator gradients align, but
   adaptive repartitioning becomes preferable when conflict exceeds the cost
   of maintaining separate registers.
2. Two-scale promotion has complementary failure modes: low thresholds
   over-promote noise, while high thresholds miss structural shifts.
3. A concrete block coarse-graining of the two-scale ensemble yields an
   explicit representation-covariance defect, an induced running cost, and
   the residual defect left after fitting that running cost.
"""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import ListedColormap


ROOT = Path(__file__).resolve().parents[1]
FIG_DIR = ROOT / "manuscript" / "figures"
DATA_DIR = ROOT / "validation" / "data"
FIG_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "DejaVu Sans"],
        "font.size": 8.2,
        "axes.labelsize": 8.2,
        "axes.titlesize": 8.6,
        "legend.fontsize": 7.0,
        "xtick.labelsize": 7.6,
        "ytick.labelsize": 7.6,
        "figure.dpi": 180,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.03,
        "mathtext.fontset": "dejavusans",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "text.usetex": False,
    }
)

COLOR_NAIVE = "#5f6670"
COLOR_ATTENTION = "#2b6cb0"
COLOR_PARTITION = "#c84630"
COLOR_SHARED_REGION = "#7fb685"
COLOR_PARTITION_REGION = "#e9a84f"
COLOR_LOW = "#c43c39"
COLOR_CAL = "#21867a"
COLOR_HIGH = "#4c6f9f"
COLOR_DEFECT = "#6f4a8e"
COLOR_FLOW = "#a05a2c"


def save_csv(path: Path, rows: list[dict[str, object]]) -> None:
    """Write a list of flat dictionaries as a CSV file."""
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def d_sq(theta: np.ndarray | float) -> np.ndarray | float:
    """Squared separation between evaluator optima a and b(theta)."""
    return 2.0 * (1.0 - np.cos(theta))


def agent_a_loss(theta: np.ndarray | float) -> np.ndarray | float:
    """Naive shared register with equal weights and no conflict term."""
    return d_sq(theta) / 8.0


def agent_b_loss(theta: np.ndarray | float, gamma: float, eta: float) -> np.ndarray | float:
    """Attention-only arbitration loss after optimizing over alpha."""
    interior = d_sq(theta) * (0.5 + gamma) / 4.0
    boundary = eta / 2.0
    return np.minimum(interior, boundary)


def agent_b_alpha1(theta: np.ndarray | float, gamma: float, eta: float) -> np.ndarray | float:
    """One representative optimal arbitration weight."""
    interior_is_min = d_sq(theta) * (0.5 + gamma) <= 2.0 * eta
    return np.where(interior_is_min, 0.5, 1.0)


def agent_c_loss(theta: np.ndarray | float, gamma: float, eta: float, c_part: float) -> np.ndarray | float:
    """Adaptive partitioning: choose the cheaper of shared mode and split mode."""
    return np.minimum(agent_b_loss(theta, gamma, eta), c_part)


def conflict_cost(theta: np.ndarray | float, gamma: float, alpha1: np.ndarray | float) -> np.ndarray | float:
    """Omega_conflict for the quadratic two-evaluator register."""
    alpha2 = 1.0 - alpha1
    return gamma * alpha1 * alpha2 * d_sq(theta)


def make_shared_register_demo() -> None:
    """Create the shared-register loss and partition phase diagram."""
    theta = np.linspace(0.0, np.pi, 500)
    gamma = 1.0
    eta = 0.8
    c_part = 0.25

    loss_a = agent_a_loss(theta)
    loss_b = agent_b_loss(theta, gamma, eta)
    loss_c = agent_c_loss(theta, gamma, eta, c_part)

    fig, axes = plt.subplots(2, 1, figsize=(3.45, 4.0), constrained_layout=True)
    ax = axes[0]
    ax.plot(theta, loss_a, color=COLOR_NAIVE, lw=1.7, label="A: fixed shared")
    ax.plot(theta, loss_b, color=COLOR_ATTENTION, lw=1.9, label="B: weight arbitration")
    ax.plot(theta, loss_c, color=COLOR_PARTITION, lw=1.9, ls="--", label="C: adaptive partition")
    ax.axhline(c_part, color=COLOR_PARTITION_REGION, lw=1.0, ls=":")
    ax.set_xlim(0.0, np.pi)
    ax.set_ylim(0.0, 0.55)
    ax.set_xticks([0, np.pi / 2, np.pi])
    ax.set_xticklabels(["0", r"$\pi/2$", r"$\pi$"])
    ax.set_xlabel(r"evaluator separation $\theta$")
    ax.set_ylabel(r"effective loss")
    ax.set_title("(a) shared-register conflict", loc="left", fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(color="0.88", lw=0.5, alpha=0.65)
    ax.text(2.46, loss_a[-1] - 0.02, "fixed", color=COLOR_NAIVE, ha="left", va="center")
    ax.text(1.58, 0.42, "arbitrate", color=COLOR_ATTENTION, ha="left", va="center")
    ax.text(1.22, c_part + 0.035, "partition", color=COLOR_PARTITION, ha="left", va="center")
    ax.text(2.60, c_part - 0.035, r"$C_{\rm part}$", color=COLOR_PARTITION_REGION, ha="left", va="center")

    theta_grid = np.linspace(0.0, np.pi, 280)
    c_grid = np.linspace(0.02, 0.55, 220)
    boundary = agent_b_loss(theta_grid, gamma, eta)
    phase = (boundary[None, :] > c_grid[:, None]).astype(float)

    ax = axes[1]
    cmap = ListedColormap([COLOR_SHARED_REGION, COLOR_PARTITION_REGION])
    ax.pcolormesh(
        theta_grid,
        c_grid,
        phase,
        cmap=cmap,
        shading="nearest",
        alpha=0.78,
        rasterized=True,
    )
    ax.plot(theta_grid, boundary, color="black", lw=1.5)
    ax.text(0.21, 0.78, "shared reuse", transform=ax.transAxes, color="#2f6f45", ha="center", fontweight="bold")
    ax.text(0.72, 0.25, "split register", transform=ax.transAxes, color="#8a5515", ha="center", fontweight="bold")
    ax.set_xlim(0.0, np.pi)
    ax.set_ylim(c_grid[0], c_grid[-1])
    ax.set_xticks([0, np.pi / 2, np.pi])
    ax.set_xticklabels(["0", r"$\pi/2$", r"$\pi$"])
    ax.set_xlabel(r"evaluator separation $\theta$")
    ax.set_ylabel(r"partition cost $C_{\rm part}$")
    ax.set_title("(b) reuse-partition boundary", loc="left", fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)

    out = FIG_DIR / "fig_yba_toy_shared_register.pdf"
    fig.savefig(out)
    plt.close(fig)

    rows = []
    for theta_value, la, lb, lc in zip(theta, loss_a, loss_b, loss_c):
        alpha1 = float(agent_b_alpha1(theta_value, gamma, eta))
        rows.append(
            {
                "theta": float(theta_value),
                "d_sq": float(d_sq(theta_value)),
                "L_A": float(la),
                "L_B": float(lb),
                "alpha1_B": alpha1,
                "alpha2_B": 1.0 - alpha1,
                "Omega_conflict": float(conflict_cost(theta_value, gamma, alpha1)),
                "L_C": float(lc),
                "mode_C": "partitioned" if lb > c_part else "shared",
            }
        )
    save_csv(DATA_DIR / "shared_register_results.csv", rows)

    partition_argument = 1.0 - (2.0 * c_part / (0.5 + gamma))
    arbitration_argument = 1.0 - (eta / (0.5 + gamma))
    theta_partition = (
        float(np.arccos(np.clip(partition_argument, -1.0, 1.0)))
        if c_part < eta / 2.0
        else float("nan")
    )
    theta_arbitration = float(np.arccos(np.clip(arbitration_argument, -1.0, 1.0)))
    save_csv(
        DATA_DIR / "shared_register_summary.csv",
        [
            {
                "gamma": gamma,
                "eta": eta,
                "partition_cost": c_part,
                "theta_partition_boundary": theta_partition,
                "theta_arbitration_boundary": theta_arbitration,
                "max_attention_only_loss": eta / 2.0,
                "partition_preempts_boundary_suppression": bool(
                    np.isfinite(theta_partition) and theta_partition < theta_arbitration
                ),
            }
        ],
    )
    print(f"[ok] wrote {out.relative_to(ROOT)}")


SHIFT_SCHEDULE = [(140, 1.75), (310, 0.60), (470, 1.45), (600, 1.05)]


def generate_regime_data(
    t_steps: int = 700, sigma: float = 0.25, seed: int = 42
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Generate a piecewise-stationary linear observation stream."""
    rng = np.random.default_rng(seed)
    x = rng.normal(size=t_steps)
    theta_true = np.ones(t_steps)
    for t_shift, value in SHIFT_SCHEDULE:
        theta_true[t_shift:] = value
    y = theta_true * x + sigma * rng.normal(size=t_steps)
    return x, y, theta_true


def run_two_scale_agent(
    x: np.ndarray,
    y: np.ndarray,
    c0: float,
    c1: float,
    *,
    beta: float = 2.5,
    window: int = 28,
    adapt_rate: float = 0.22,
    sigma: float = 0.25,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Run the two-scale promotion rule from Eq. (two-scale threshold)."""
    t_steps = len(y)
    theta_hat = np.empty(t_steps)
    theta_hat[0] = 1.0
    pre_update_error = np.zeros(t_steps)
    promotions = np.zeros(t_steps, dtype=bool)
    delta_cost = c1 - c0

    for t in range(1, t_steps):
        theta = theta_hat[t - 1]
        error = y[t] - theta * x[t]
        pre_update_error[t] = error

        start = max(0, t - window + 1)
        x_window = x[start : t + 1]
        y_window = y[start : t + 1]
        if len(x_window) >= 8:
            theta_window = np.sum(x_window * y_window) / (np.sum(x_window * x_window) + 1e-6)
            current_loss = np.mean((y_window - theta * x_window) ** 2)
            candidate_loss = np.mean((y_window - theta_window * x_window) ** 2)
            structural_gain = max(0.0, current_loss - candidate_loss)
        else:
            theta_window = theta
            structural_gain = 0.0

        local_gain = 0.10 * min(error * error, sigma * sigma)
        if beta * (structural_gain - local_gain) > delta_cost:
            if abs(x[t]) > 0.15:
                noisy_observation = np.clip(y[t] / x[t], -1.5, 3.5)
            else:
                noisy_observation = theta_window
            theta = theta + adapt_rate * (noisy_observation - theta)
            promotions[t] = True

        theta_hat[t] = theta

    return theta_hat, pre_update_error, promotions


def sigmoid(z: np.ndarray | float) -> np.ndarray | float:
    """Numerically stable logistic function."""
    z_arr = np.asarray(z)
    out = np.empty_like(z_arr, dtype=float)
    positive = z_arr >= 0
    out[positive] = 1.0 / (1.0 + np.exp(-z_arr[positive]))
    exp_z = np.exp(z_arr[~positive])
    out[~positive] = exp_z / (1.0 + exp_z)
    if np.isscalar(z):
        return float(out)
    return out


def logit(p: np.ndarray | float) -> np.ndarray | float:
    """Log odds with clipping to keep finite diagnostic couplings."""
    clipped = np.clip(p, 1e-9, 1.0 - 1e-9)
    return np.log(clipped / (1.0 - clipped))


def two_scale_gain_stream(
    x: np.ndarray,
    y: np.ndarray,
    theta_path: np.ndarray,
    *,
    beta: float = 2.5,
    window: int = 28,
    sigma: float = 0.25,
) -> np.ndarray:
    """Return beta times the fine-scale structural-minus-local gain stream."""
    margin = np.zeros(len(y))
    for t in range(1, len(y)):
        theta = theta_path[t - 1]
        error = y[t] - theta * x[t]
        start = max(0, t - window + 1)
        x_window = x[start : t + 1]
        y_window = y[start : t + 1]
        if len(x_window) >= 8:
            theta_window = np.sum(x_window * y_window) / (np.sum(x_window * x_window) + 1e-6)
            current_loss = np.mean((y_window - theta * x_window) ** 2)
            candidate_loss = np.mean((y_window - theta_window * x_window) ** 2)
            structural_gain = max(0.0, current_loss - candidate_loss)
        else:
            structural_gain = 0.0
        local_gain = 0.10 * min(error * error, sigma * sigma)
        margin[t] = beta * (structural_gain - local_gain)
    return margin


def coarse_graining_defect_rows(
    c_values: np.ndarray,
    *,
    block_size: int = 4,
    reference_cost: float = 0.5,
    seed: int = 42,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Compute a concrete ensemble defect for block coarse-graining.

    Fine time steps carry Bernoulli promotion probabilities
    p_t(c)=sigmoid(m_t-c).  The coarse event is whether any fine promotion
    occurs in a block.  The pushed-forward probability is therefore
    1-prod_t(1-p_t).  The direct coarse law uses the same functional form on
    the summed block margin, sigmoid(sum_t m_t-c).  Their total-variation
    distance is the representation-covariance defect for this toy map.
    """
    x, y, _ = generate_regime_data(seed=seed)
    theta_hat, _, _ = run_two_scale_agent(x, y, 0.0, 0.060)
    margin = two_scale_gain_stream(x, y, theta_hat)
    usable = margin[40:]
    n_blocks = len(usable) // block_size
    block_margins = usable[: n_blocks * block_size].reshape(n_blocks, block_size)
    block_sums = block_margins.sum(axis=1)

    rows: list[dict[str, object]] = []
    c_eff_means = []
    for c_value in c_values:
        p_fine = sigmoid(block_margins - c_value)
        p_push = 1.0 - np.prod(1.0 - p_fine, axis=1)
        p_direct = sigmoid(block_sums - c_value)
        tv = np.abs(p_push - p_direct)
        c_eff = block_sums - logit(p_push)
        mean_c_eff = float(np.mean(c_eff))
        p_running_fit = sigmoid(block_sums - mean_c_eff)
        tv_running_fit = np.abs(p_push - p_running_fit)
        rows.append(
            {
                "c1_minus_c0": float(c_value),
                "mean_tv_defect": float(np.mean(tv)),
                "max_tv_defect": float(np.max(tv)),
                "mean_tv_after_running_cost": float(np.mean(tv_running_fit)),
                "max_tv_after_running_cost": float(np.max(tv_running_fit)),
                "mean_pushed_probability": float(np.mean(p_push)),
                "mean_direct_probability": float(np.mean(p_direct)),
                "mean_running_fit_probability": float(np.mean(p_running_fit)),
                "mean_effective_cost": mean_c_eff,
                "std_effective_cost": float(np.std(c_eff)),
                "block_size": block_size,
                "block_count": n_blocks,
            }
        )
        c_eff_means.append(mean_c_eff)

    c_eff_arr = np.array(c_eff_means)
    reference_index = int(np.argmin(np.abs(c_values - reference_cost)))
    if 0 < reference_index < len(c_values) - 1:
        slope = (c_eff_arr[reference_index + 1] - c_eff_arr[reference_index - 1]) / (
            c_values[reference_index + 1] - c_values[reference_index - 1]
        )
    else:
        slope = np.nan
    abs_slope = abs(float(slope)) if np.isfinite(slope) else float("nan")
    if not np.isfinite(abs_slope):
        classification = "undetermined"
    elif abs_slope > 1.05:
        classification = "relevant"
    elif abs_slope < 0.95:
        classification = "irrelevant"
    else:
        classification = "marginal"

    summary = {
        "reference_cost": float(c_values[reference_index]),
        "effective_cost_at_reference": float(c_eff_arr[reference_index]),
        "std_effective_cost_at_reference": float(rows[reference_index]["std_effective_cost"]),
        "mean_tv_defect_at_reference": float(rows[reference_index]["mean_tv_defect"]),
        "mean_tv_after_running_cost_at_reference": float(
            rows[reference_index]["mean_tv_after_running_cost"]
        ),
        "linearized_slope": float(slope),
        "classification": classification,
        "block_size": block_size,
        "block_count": n_blocks,
    }
    return rows, summary


def promotion_metrics(c1: float, seeds: range = range(24)) -> dict[str, float]:
    """Average promotion diagnostics across generated streams."""
    false_share = []
    missed_shift_rate = []
    decision_error = []
    mse = []
    roughness = []
    promotion_rate = []
    shift_times = [time for time, _ in SHIFT_SCHEDULE]

    for seed in seeds:
        x, y, _ = generate_regime_data(seed=seed)
        theta_hat, _, promotions = run_two_scale_agent(x, y, 0.0, c1)
        promoted_at = np.where(promotions)[0]
        false_promotions = sum(
            1 for t in promoted_at if all(abs(t - shift) > 35 for shift in shift_times)
        )
        misses = sum(
            1
            for shift in shift_times
            if not np.any(promotions[shift : min(shift + 65, len(y))])
        )
        false_share_value = false_promotions / max(len(promoted_at), 1)
        missed_value = misses / len(shift_times)
        false_share.append(false_share_value)
        missed_shift_rate.append(missed_value)
        decision_error.append(0.5 * (false_share_value + missed_value))
        mse.append(float(np.mean((y[50:] - theta_hat[50:] * x[50:]) ** 2)))
        roughness.append(float(np.mean(np.diff(theta_hat) ** 2)))
        promotion_rate.append(float(len(promoted_at) / len(y)))

    return {
        "c1_minus_c0": c1,
        "false_promotion_share": float(np.mean(false_share)),
        "missed_shift_rate": float(np.mean(missed_shift_rate)),
        "decision_error_index": float(np.mean(decision_error)),
        "mean_sq_prediction_error": float(np.mean(mse)),
        "theta_roughness": float(np.mean(roughness)),
        "promotion_rate": float(np.mean(promotion_rate)),
    }


def make_two_scale_promotion_demo() -> None:
    """Create a combined full-width figure for two-scale promotion."""
    c_values = np.linspace(0.001, 0.50, 80)
    rows = [promotion_metrics(float(c_value)) for c_value in c_values]
    save_csv(DATA_DIR / "two_scale_results.csv", rows)

    false_share = np.array([row["false_promotion_share"] for row in rows])
    missed = np.array([row["missed_shift_rate"] for row in rows])
    decision = np.array([row["decision_error_index"] for row in rows])
    best_index = int(np.argmin(decision))
    best_cost = float(c_values[best_index])

    representative_rows = []
    for name, c_value in [
        ("low threshold", 0.005),
        ("calibrated", best_cost),
        ("high threshold", 0.400),
    ]:
        metrics = promotion_metrics(float(c_value))
        metrics["label"] = name
        metrics["is_grid_minimum"] = bool(name == "calibrated")
        representative_rows.append(metrics)
    save_csv(DATA_DIR / "two_scale_summary.csv", representative_rows)

    x, y, theta_true = generate_regime_data(seed=42)
    agents = [
        ("low threshold", 0.005, COLOR_LOW),
        ("calibrated", best_cost, COLOR_CAL),
        ("high threshold", 0.400, COLOR_HIGH),
    ]
    time = np.arange(len(y))

    fig = plt.figure(figsize=(7.1, 4.25), constrained_layout=True)
    grid = fig.add_gridspec(3, 2, width_ratios=[1.25, 1.0])
    tracking_axes = [fig.add_subplot(grid[row, 0]) for row in range(3)]
    rates_ax = fig.add_subplot(grid[0:2, 1])
    index_ax = fig.add_subplot(grid[2, 1])

    for row, (ax, (name, c1, color)) in enumerate(zip(tracking_axes, agents)):
        theta_hat, _, promotions = run_two_scale_agent(x, y, 0.0, c1)
        ax.plot(time, theta_true, color="0.25", lw=1.0, alpha=0.72)
        ax.plot(time, theta_hat, color=color, lw=1.15)
        promoted_at = np.where(promotions)[0]
        if len(promoted_at):
            ax.scatter(promoted_at, theta_hat[promoted_at], s=3.5, color=color, alpha=0.22, linewidths=0)
        for shift, _ in SHIFT_SCHEDULE:
            ax.axvline(shift, color="0.68", lw=0.45, ls=":")
        ax.set_ylim(0.1, 2.2)
        ax.set_ylabel(r"$\theta$")
        ax.set_title(f"({chr(97 + row)}) {name}", loc="left", fontweight="bold")
        ax.text(0.98, 0.82, rf"$c={c1:.3f}$", transform=ax.transAxes, ha="right", va="center", color=color)
        ax.spines[["top", "right"]].set_visible(False)
    tracking_axes[-1].set_xlabel("time step")

    rates_ax.plot(c_values, false_share, color=COLOR_LOW, lw=1.7, label="false-promotion share")
    rates_ax.plot(c_values, missed, color=COLOR_HIGH, lw=1.7, label="missed-shift rate")
    rates_ax.set_xlabel(r"structural cost $c_1-c_0$")
    rates_ax.set_ylabel("rate")
    rates_ax.set_ylim(-0.02, 0.65)
    rates_ax.set_title("(d) complementary failures", loc="left", fontweight="bold")
    rates_ax.text(0.09, false_share[8] + 0.05, "false promotions", color=COLOR_LOW, ha="left", va="center")
    rates_ax.text(0.30, missed[-1] + 0.035, "missed shifts", color=COLOR_HIGH, ha="left", va="center")
    rates_ax.spines[["top", "right"]].set_visible(False)
    rates_ax.grid(color="0.88", lw=0.5, alpha=0.65)

    index_ax.plot(c_values, decision, color=COLOR_CAL, lw=1.9)
    index_ax.scatter(c_values[best_index], decision[best_index], s=22, color=COLOR_CAL, zorder=3)
    index_ax.annotate(
        "best threshold",
        xy=(c_values[best_index], decision[best_index]),
        xytext=(c_values[best_index] + 0.12, decision[best_index] + 0.09),
        arrowprops={"arrowstyle": "->", "lw": 0.8, "color": COLOR_CAL},
        color=COLOR_CAL,
        ha="left",
        va="center",
    )
    index_ax.set_xlabel(r"structural cost $c_1-c_0$")
    index_ax.set_ylabel("index")
    index_ax.set_ylim(0.0, max(0.35, 1.08 * float(decision.max())))
    index_ax.set_title("(e) interior compromise", loc="left", fontweight="bold")
    index_ax.spines[["top", "right"]].set_visible(False)
    index_ax.grid(color="0.88", lw=0.5, alpha=0.65)

    out = FIG_DIR / "fig_yba_toy_two_scale_promotion.pdf"
    fig.savefig(out)
    plt.close(fig)
    print(f"[ok] wrote {out.relative_to(ROOT)}")


def make_coarse_graining_defect_demo() -> None:
    """Create a concrete representation-covariance defect diagnostic."""
    c_values = np.linspace(0.001, 2.00, 120)
    rows, summary = coarse_graining_defect_rows(c_values)
    save_csv(DATA_DIR / "coarse_graining_defect.csv", rows)
    save_csv(DATA_DIR / "coarse_graining_defect_summary.csv", [summary])

    mean_defect = np.array([row["mean_tv_defect"] for row in rows], dtype=float)
    fit_defect = np.array([row["mean_tv_after_running_cost"] for row in rows], dtype=float)
    c_eff = np.array([row["mean_effective_cost"] for row in rows], dtype=float)
    reference_cost = float(summary["reference_cost"])
    reference_index = int(np.argmin(np.abs(c_values - reference_cost)))
    reference_eff = c_eff[reference_index]
    delta_c = c_values - reference_cost
    delta_eff = c_eff - reference_eff
    slope = float(summary["linearized_slope"])
    classification = str(summary["classification"])

    fig, axes = plt.subplots(1, 2, figsize=(7.1, 2.45), constrained_layout=True)
    ax = axes[0]
    ax.plot(c_values, mean_defect, color=COLOR_DEFECT, lw=1.9)
    ax.plot(c_values, fit_defect, color=COLOR_ATTENTION, lw=1.5, ls="--")
    ax.axvline(reference_cost, color="0.35", lw=0.8, ls="--")
    ax.text(1.40, mean_defect[-16], "same cost", color=COLOR_DEFECT, ha="left", va="center")
    ax.text(1.15, fit_defect[-22] + 0.015, "after fit", color=COLOR_ATTENTION, ha="left", va="center")
    ax.text(reference_cost + 0.04, 0.444, "reference", color="0.35", ha="left", va="center")
    ax.set_xlabel(r"fine structural cost $c_1-c_0$")
    ax.set_ylabel(r"$\epsilon_{\rm ens}$")
    ax.set_title("(a) block coarse-graining defect", loc="left", fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(color="0.88", lw=0.5, alpha=0.65)

    ax = axes[1]
    ax.plot(delta_c, delta_eff, color=COLOR_FLOW, lw=1.9)
    ax.plot(delta_c, delta_c, color="0.25", lw=1.0, ls="--")
    ax.scatter([0.0], [0.0], color=COLOR_FLOW, s=24)
    ax.text(0.93, delta_eff[-20] + 0.08, r"$\delta c_{\rm eff}$", color=COLOR_FLOW, ha="left", va="center")
    ax.text(0.98, 0.98, "unchanged", color="0.25", ha="left", va="center")
    ax.set_xlabel(r"fine perturbation $\delta c$")
    ax.set_ylabel(r"block perturbation $\delta c_{\rm eff}$")
    ax.set_title(f"(b) threshold flow: {classification}, slope {slope:.2f}", loc="left", fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(color="0.88", lw=0.5, alpha=0.65)

    out = FIG_DIR / "fig_yba_toy_coarse_graining_defect.pdf"
    fig.savefig(out)
    plt.close(fig)
    print(f"[ok] wrote {out.relative_to(ROOT)}")


def main() -> None:
    make_shared_register_demo()
    make_two_scale_promotion_demo()
    make_coarse_graining_defect_demo()
    print("[ok] toy dynamics figures and data are current")


if __name__ == "__main__":
    main()
