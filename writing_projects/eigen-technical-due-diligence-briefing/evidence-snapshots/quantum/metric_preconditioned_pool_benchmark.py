from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import scipy.linalg as la


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "validation" / "data"
FIG_DIR = ROOT / "manuscript" / "figures"

I2 = np.eye(2, dtype=complex)
X = np.array([[0, 1], [1, 0]], dtype=complex)
Y = np.array([[0, -1j], [1j, 0]], dtype=complex)
Z = np.diag([1, -1]).astype(complex)
N = (I2 - Z) / 2

P_INDICES = [0, 4, 8, 12]  # q2=q3=0, active q0,q1 arbitrary.

COLORS = {
    "bare": "#D1495B",
    "raw": "#6D597A",
    "metric": "#2A9D8F",
    "exact_metric": "#3A6EA5",
    "grid": "#D9DEE7",
}


def tensor_ops(ops: list[np.ndarray]) -> np.ndarray:
    result = ops[0]
    for op in ops[1:]:
        result = np.kron(result, op)
    return result


def local(op: np.ndarray, idx: int, num_qubits: int = 4) -> np.ndarray:
    ops = [I2] * num_qubits
    ops[idx] = op
    return tensor_ops(ops)


def build_multiscale_hamiltonian(scale: float) -> np.ndarray:
    """Two leakage channels: one large-amplitude/high-gap and one low-gap."""
    active = -local(X, 0) - 0.7 * local(X, 1) + 0.2 * (local(Z, 0) @ local(Z, 1))
    environment = 0.4 * local(N, 2) + 30.0 * local(N, 3)
    boundary = scale * (
        0.8 * (local(Z, 1) @ local(X, 2))
        + 0.9 * (local(X, 0) @ local(X, 3))
    )
    return active + environment + boundary


def initial_basis() -> np.ndarray:
    basis = np.zeros((16, 4), dtype=complex)
    for col, idx in enumerate(P_INDICES):
        basis[idx, col] = 1.0
    return basis


def solve_ritz(hamiltonian: np.ndarray, basis: np.ndarray) -> tuple[float, np.ndarray]:
    active_hamiltonian = basis.conj().T @ hamiltonian @ basis
    values, vectors = np.linalg.eigh(active_hamiltonian)
    return float(np.real(values[0])), basis @ vectors[:, 0]


def projector_complement(basis: np.ndarray) -> np.ndarray:
    projector = basis @ basis.conj().T
    return np.eye(projector.shape[0], dtype=complex) - projector


def augment_basis(basis: np.ndarray, vector: np.ndarray) -> np.ndarray:
    candidate = vector - basis @ (basis.conj().T @ vector)
    norm = float(np.linalg.norm(candidate))
    if norm < 1e-12:
        return basis
    return np.hstack([basis, (candidate / norm).reshape(-1, 1)])


def feshbach_dressing(
    hamiltonian: np.ndarray,
    basis: np.ndarray,
    energy: float,
    residual: np.ndarray,
) -> np.ndarray:
    complement = projector_complement(basis)
    values, vectors = np.linalg.eigh(complement)
    q_basis = vectors[:, values > 0.5]
    q_h_q = q_basis.conj().T @ hamiltonian @ q_basis
    q_residual = q_basis.conj().T @ residual
    dressed = la.solve(
        energy * np.eye(q_h_q.shape[0]) - q_h_q,
        q_residual,
        assume_a="her",
    )
    return q_basis @ dressed


def boundary_dictionary() -> list[dict[str, object]]:
    return [
        {
            "name": "low_gap",
            "label": r"$Z_1X_2$ low gap",
            "operator": local(Z, 1) @ local(X, 2),
        },
        {
            "name": "high_gap",
            "label": r"$X_0X_3$ high gap",
            "operator": local(X, 0) @ local(X, 3),
        },
    ]


def candidate_scores(
    hamiltonian: np.ndarray,
    basis: np.ndarray,
    energy: float,
    state: np.ndarray,
) -> list[dict[str, object]]:
    complement = projector_complement(basis)
    residual = complement @ hamiltonian @ state
    dressed = feshbach_dressing(hamiltonian, basis, energy, residual)
    rows: list[dict[str, object]] = []

    for item in boundary_dictionary():
        vector = complement @ item["operator"] @ state
        raw_score = float(abs(np.vdot(vector, residual)))
        norm = max(float(np.real(np.vdot(vector, vector))), 1e-15)
        denominator = float(
            abs(np.real(np.vdot(vector, (hamiltonian - energy * np.eye(16)) @ vector))) / norm
        )
        gap_metric_score = raw_score / max(denominator, 1e-12)
        exact_metric_score = float(abs(np.vdot(vector, dressed)))
        rows.append(
            {
                "candidate": item["name"],
                "label": item["label"],
                "vector": vector,
                "raw_score": raw_score,
                "denominator": denominator,
                "gap_metric_score": gap_metric_score,
                "exact_metric_score": exact_metric_score,
            }
        )
    return rows


def select_candidate(scores: list[dict[str, object]], method: str) -> dict[str, object]:
    key = {
        "raw": "raw_score",
        "gap_metric": "gap_metric_score",
        "exact_metric": "exact_metric_score",
    }[method]
    return max(scores, key=lambda row: float(row[key]))


def one_step_result(scale: float, method: str) -> dict[str, object]:
    hamiltonian = build_multiscale_hamiltonian(scale)
    exact_energy = float(np.min(np.linalg.eigvalsh(hamiltonian)))
    basis = initial_basis()
    bare_energy, state = solve_ritz(hamiltonian, basis)
    scores = candidate_scores(hamiltonian, basis, bare_energy, state)
    selected = select_candidate(scores, method)
    augmented = augment_basis(basis, selected["vector"])
    energy, _ = solve_ritz(hamiltonian, augmented)
    return {
        "scale": scale,
        "method": method,
        "selected": selected["candidate"],
        "bare_error": bare_energy - exact_energy,
        "energy": energy,
        "error": energy - exact_energy,
        "raw_low": next(row for row in scores if row["candidate"] == "low_gap")["raw_score"],
        "raw_high": next(row for row in scores if row["candidate"] == "high_gap")["raw_score"],
        "metric_low": next(row for row in scores if row["candidate"] == "low_gap")[
            "gap_metric_score"
        ],
        "metric_high": next(row for row in scores if row["candidate"] == "high_gap")[
            "gap_metric_score"
        ],
    }


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def plot_results(rows: list[dict[str, object]], score_rows: list[dict[str, object]]) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 4.05), dpi=180)
    scales = sorted({float(row["scale"]) for row in rows})
    bare = [next(float(row["bare_error"]) for row in rows if float(row["scale"]) == scale) for scale in scales]
    axes[0].plot(scales, bare, "o-", lw=2.0, ms=4, color=COLORS["bare"], label="bare active space")

    for method, label, color, marker in [
        ("raw", "raw closure score", COLORS["raw"], "s--"),
        ("gap_metric", "gap-metric score", COLORS["metric"], "^-"),
        ("exact_metric", "Feshbach-metric score", COLORS["exact_metric"], "d:"),
    ]:
        values = [
            max(float(row["error"]), 1e-15)
            for scale in scales
            for row in rows
            if float(row["scale"]) == scale and row["method"] == method
        ]
        axes[0].plot(scales, values, marker, lw=2.0, ms=4, color=color, label=label)

    axes[0].set_yscale("log")
    axes[0].set_xlabel(r"boundary scale $\lambda$")
    axes[0].set_ylabel(r"one-step energy error")
    axes[0].grid(True, which="both", alpha=0.18)
    axes[0].legend(frameon=False, fontsize=6.7)

    scale_one = [row for row in score_rows if abs(float(row["scale"]) - 1.0) < 1e-12]
    labels = [str(row["label"]) for row in scale_one]
    x = np.arange(len(labels))
    width = 0.32
    raw = np.array([float(row["raw_score"]) for row in scale_one])
    metric = np.array([float(row["gap_metric_score"]) for row in scale_one])
    raw = raw / max(np.max(raw), 1e-15)
    metric = metric / max(np.max(metric), 1e-15)
    axes[1].bar(x - width / 2, raw, width, color=COLORS["raw"], label="raw")
    axes[1].bar(x + width / 2, metric, width, color=COLORS["metric"], label="gap metric")
    axes[1].set_xticks(x, labels, rotation=18, ha="right")
    axes[1].set_ylabel("normalized first-step score")
    axes[1].set_ylim(0, 1.08)
    axes[1].grid(True, axis="y", alpha=0.18)
    axes[1].legend(frameon=False, fontsize=7)

    fig.tight_layout(w_pad=1.8)
    fig.savefig(FIG_DIR / "fig_metric_preconditioned_pool.pdf", bbox_inches="tight")
    fig.savefig(FIG_DIR / "fig_metric_preconditioned_pool.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    scales = [0.4, 0.6, 0.8, 1.0, 1.2]
    rows = [
        one_step_result(scale, method)
        for scale in scales
        for method in ["raw", "gap_metric", "exact_metric"]
    ]

    score_rows: list[dict[str, object]] = []
    for scale in scales:
        hamiltonian = build_multiscale_hamiltonian(scale)
        basis = initial_basis()
        energy, state = solve_ritz(hamiltonian, basis)
        for score in candidate_scores(hamiltonian, basis, energy, state):
            score_rows.append(
                {
                    "scale": scale,
                    "candidate": score["candidate"],
                    "label": score["label"],
                    "raw_score": score["raw_score"],
                    "denominator": score["denominator"],
                    "gap_metric_score": score["gap_metric_score"],
                    "exact_metric_score": score["exact_metric_score"],
                }
            )

    write_csv(
        DATA_DIR / "metric_pool_sweep.csv",
        rows,
        [
            "scale",
            "method",
            "selected",
            "bare_error",
            "energy",
            "error",
            "raw_low",
            "raw_high",
            "metric_low",
            "metric_high",
        ],
    )
    write_csv(
        DATA_DIR / "metric_pool_scores.csv",
        score_rows,
        [
            "scale",
            "candidate",
            "label",
            "raw_score",
            "denominator",
            "gap_metric_score",
            "exact_metric_score",
        ],
    )
    plot_results(rows, score_rows)


if __name__ == "__main__":
    main()
