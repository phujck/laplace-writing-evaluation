#!/usr/bin/env python3
"""Numerical verification of the operatorial-loss projection thesis (R2).

Claim (R2): In variational quantum ML the scalar loss C(theta) = <0|U(theta)^dag O U(theta)|0>
suffers a "barren plateau" (exponentially small gradient variance) that is a PROJECTION
ARTIFACT. The *operator* gradient (i/2)[G, Omega] has a Hilbert-Schmidt norm that is
conserved (unitarily invariant, O(1), independent of qubit count n); only its rank-one
scalar projection onto a Haar-random state decays as ~1/d = 2^{-n}.

We verify two things:

IDENTITY 1 (exact projection law).
    For a traceless Hermitian A on d = 2^n dimensions, with |psi> Haar-random pure:
        Var[<psi|A|psi>] = Tr[A^2] / (d (d+1)) = ||A||_HS^2 / (d (d+1)).
    Checked by Monte Carlo.

IDENTITY 2 (McClean decay vs conserved operator norm -- the money plot).
    Standard McClean setup U(theta) = U_L e^{-i theta G/2} U_R, with U_L, U_R Haar-random.
    With |psi_R> = U_R|0> and Omega = e^{+i theta G/2} U_L^dag O U_L e^{-i theta G/2},
        d/dtheta C = <psi_R| (i/2)[G, Omega] |psi_R>.
    We show:
      * Var over random draws of the SCALAR gradient decays ~ 2^{-n}.
      * The OPERATOR gradient HS-norm fraction ||(i/2)[G,Omega]||_HS^2 / ||O||_HS^2
        stays flat (O(1), independent of n and of the random draw -- it is unitarily invariant).
      * The projection law of Identity 1 also predicts Var[d C] here, since U_R|0> is
        Haar-random (U_R a 2-design) and (i/2)[G,Omega] is traceless Hermitian.

Reproducible: RNG seeded. Dense numpy, Paulis built via kron.
Runtime target: < ~3 min.
"""

import json
import os
import time

import numpy as np

# ----------------------------------------------------------------------------
# Reproducibility
# ----------------------------------------------------------------------------
SEED = 20240603
rng = np.random.default_rng(SEED)

# ----------------------------------------------------------------------------
# Pauli matrices and helpers
# ----------------------------------------------------------------------------
I2 = np.eye(2, dtype=complex)
X = np.array([[0, 1], [1, 0]], dtype=complex)
Y = np.array([[0, -1j], [1j, 0]], dtype=complex)
Z = np.array([[1, 0], [0, -1]], dtype=complex)
PAULIS = [I2, X, Y, Z]  # indices 0=I,1=X,2=Y,3=Z


def kron_list(mats):
    """Tensor (Kronecker) product of a list of 2x2 matrices."""
    out = mats[0]
    for m in mats[1:]:
        out = np.kron(out, m)
    return out


def random_pauli_string(n, rng, allow_identity=False):
    """Build a random n-qubit Pauli string as a dense 2^n x 2^n matrix.

    Each qubit gets one of I,X,Y,Z. A Pauli string squares to the identity
    (so it is a valid generator G with G^2 = I) and is Hermitian and traceless
    unless it is the all-identity string.
    """
    while True:
        idx = rng.integers(0, 4, size=n)
        if allow_identity or np.any(idx != 0):
            break
    return kron_list([PAULIS[i] for i in idx])


def haar_unitary(d, rng):
    """Haar-random unitary of dimension d via QR of a complex Gaussian (with
    the standard phase correction so the distribution is exactly Haar)."""
    z = (rng.standard_normal((d, d)) + 1j * rng.standard_normal((d, d))) / np.sqrt(2.0)
    q, r = np.linalg.qr(z)
    ph = np.diagonal(r) / np.abs(np.diagonal(r))
    return q * ph[np.newaxis, :]


def haar_state(d, rng):
    """Haar-random pure state (column vector) of dimension d."""
    v = (rng.standard_normal(d) + 1j * rng.standard_normal(d))
    return v / np.linalg.norm(v)


def hs_norm_sq(A):
    """Hilbert-Schmidt norm squared: Tr[A^dag A] = sum |A_ij|^2."""
    return float(np.real(np.vdot(A, A)))


def comm(A, B):
    return A @ B - B @ A


# ----------------------------------------------------------------------------
# IDENTITY 1: Var[<psi|A|psi>] = ||A||_HS^2 / (d (d+1)) for traceless Hermitian A
# ----------------------------------------------------------------------------
def check_identity1(n_values, n_states, rng):
    results = []
    for n in n_values:
        d = 2 ** n
        # Build A = (i/2)[G, M], G a Pauli string (G^2=I), M = U_L^dag O U_L.
        # A is automatically traceless Hermitian:
        #   Hermitian: ([G,M])^dag = [M,G] = -[G,M], times i -> Hermitian.
        #   traceless: Tr[GM] = Tr[MG].
        G = random_pauli_string(n, rng)
        O = random_pauli_string(n, rng)
        U_L = haar_unitary(d, rng)
        M = U_L.conj().T @ O @ U_L
        A = 0.5j * comm(G, M)

        # sanity: traceless & Hermitian
        assert abs(np.trace(A)) < 1e-9, "A not traceless"
        assert np.allclose(A, A.conj().T, atol=1e-9), "A not Hermitian"

        # Monte Carlo over Haar-random pure states.
        # Vectorize: sample a batch of states as columns of a (d, n_states) array.
        Vs = (rng.standard_normal((d, n_states)) + 1j * rng.standard_normal((d, n_states)))
        Vs /= np.linalg.norm(Vs, axis=0, keepdims=True)
        # expectation values <psi|A|psi> = sum_i conj(psi_i) (A psi)_i
        AV = A @ Vs
        exp_vals = np.real(np.sum(Vs.conj() * AV, axis=0))  # real since A Hermitian

        emp_var = float(np.var(exp_vals, ddof=1))
        pred_var = hs_norm_sq(A) / (d * (d + 1))
        rel_err = abs(emp_var - pred_var) / pred_var

        results.append(
            dict(
                n=int(n),
                d=int(d),
                empirical_var=emp_var,
                predicted_var=pred_var,
                rel_err=rel_err,
                n_states=int(n_states),
            )
        )
        print(
            f"  [ID1] n={n} d={d}: emp_var={emp_var:.6e} pred_var={pred_var:.6e} "
            f"rel_err={rel_err*100:.2f}%"
        )
    return results


# ----------------------------------------------------------------------------
# IDENTITY 2: McClean decay vs conserved operator norm
# ----------------------------------------------------------------------------
def build_observable(n, kind):
    """Local Z_0 or global Z_0 Z_1 ... Z_{n-1}."""
    if kind == "local":
        mats = [Z] + [I2] * (n - 1)
    elif kind == "global":
        mats = [Z] * n
    else:
        raise ValueError(kind)
    return kron_list(mats)


def build_generator(n):
    """Fixed Pauli generator G = Y on the first qubit (G^2 = I)."""
    return kron_list([Y] + [I2] * (n - 1))


def check_identity2(n_values, n_samples, observables, rng):
    """For each n and observable, sample (U_L, U_R, theta) draws.

    Returns per-(n, obs) dict with:
      - var_grad_scalar: Var over draws of dC/dtheta
      - op_grad_fraction_mean / std: ||(i/2)[G,Omega]||_HS^2 / ||O||_HS^2 across draws
      - id1_pred_var: ||(i/2)[G,Omega]||_HS^2 / (d(d+1)) averaged over draws (Identity-1 prediction)
    """
    per_obs = {obs: [] for obs in observables}

    for n in n_values:
        d = 2 ** n
        G = build_generator(n)
        for obs in observables:
            O = build_observable(n, obs)
            O_hs = hs_norm_sq(O)  # = d for a Pauli string

            grads = np.empty(n_samples, dtype=float)
            op_fracs = np.empty(n_samples, dtype=float)
            id1_preds = np.empty(n_samples, dtype=float)

            for s in range(n_samples):
                theta = rng.uniform(0.0, 2.0 * np.pi)
                U_L = haar_unitary(d, rng)
                U_R = haar_unitary(d, rng)

                # e^{-i theta G/2}: since G^2 = I, exp(-i a G) = cos(a) I - i sin(a) G
                a = theta / 2.0
                expm = np.cos(a) * np.eye(d) - 1j * np.sin(a) * G  # e^{-i theta G/2}
                expp = np.cos(a) * np.eye(d) + 1j * np.sin(a) * G  # e^{+i theta G/2}

                ULOUL = U_L.conj().T @ O @ U_L
                Omega = expp @ ULOUL @ expm

                Op = 0.5j * comm(G, Omega)  # operator gradient (i/2)[G, Omega]

                # scalar gradient: <psi_R| Op |psi_R>, psi_R = U_R |0>
                psi_R = U_R[:, 0]  # first column = U_R |0>
                grad = np.real(np.vdot(psi_R, Op @ psi_R))
                grads[s] = grad

                op_norm_sq = hs_norm_sq(Op)
                op_fracs[s] = op_norm_sq / O_hs
                id1_preds[s] = op_norm_sq / (d * (d + 1))

            var_grad = float(np.var(grads, ddof=1))
            per_obs[obs].append(
                dict(
                    n=int(n),
                    d=int(d),
                    observable=obs,
                    var_grad_scalar=var_grad,
                    op_grad_fraction_mean=float(np.mean(op_fracs)),
                    op_grad_fraction_std=float(np.std(op_fracs, ddof=1)),
                    id1_pred_var=float(np.mean(id1_preds)),
                    n_samples=int(n_samples),
                )
            )
            print(
                f"  [ID2] n={n} obs={obs:6s}: var_grad={var_grad:.4e} "
                f"op_frac={np.mean(op_fracs):.4f}+/-{np.std(op_fracs, ddof=1):.4f} "
                f"id1_pred={np.mean(id1_preds):.4e}"
            )
    return per_obs


def fit_log_slope(n_values, var_values):
    """Fit log10(var) = slope * n + b ; return slope, intercept."""
    n_arr = np.asarray(n_values, dtype=float)
    y = np.log10(np.asarray(var_values, dtype=float))
    slope, intercept = np.polyfit(n_arr, y, 1)
    return float(slope), float(intercept)


# ----------------------------------------------------------------------------
# Plotting
# ----------------------------------------------------------------------------
def make_figure(id2_results, slopes, fig_dir):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {
            "font.size": 11,
            "axes.grid": True,
            "grid.alpha": 0.3,
            "figure.dpi": 130,
        }
    )

    fig, (ax_l, ax_r) = plt.subplots(1, 2, figsize=(11, 4.5))

    colors = {"local": "#1f77b4", "global": "#d62728"}
    markers = {"local": "o", "global": "s"}

    # Left panel: scalar gradient variance (log y) decaying in n.
    for obs, recs in id2_results.items():
        ns = [r["n"] for r in recs]
        vg = [r["var_grad_scalar"] for r in recs]
        ax_l.semilogy(
            ns, vg, marker=markers[obs], color=colors[obs],
            label=f"Var[$\\partial_\\theta C$] ({obs} $O$)", lw=1.8, ms=6,
        )
        # overlay Identity-1 prediction
        id1 = [r["id1_pred_var"] for r in recs]
        ax_l.semilogy(
            ns, id1, marker="x", color=colors[obs], ls="--", alpha=0.7, ms=7,
            label=f"ID1 law $\\|A\\|^2_{{HS}}/d(d{{+}}1)$ ({obs})",
        )
        # fitted slope annotation
        sl = slopes[obs]
        ax_l.annotate(
            f"slope={sl:.3f}/qubit\n($-\\log_{{10}}2={-np.log10(2):.3f}$)",
            xy=(ns[len(ns) // 2], vg[len(ns) // 2]),
            xytext=(0.05, 0.12 if obs == "local" else 0.02),
            textcoords="axes fraction", fontsize=9, color=colors[obs],
        )

    ax_l.set_xlabel("number of qubits $n$")
    ax_l.set_ylabel(r"Var$[\partial_\theta C]$  (scalar gradient)")
    ax_l.set_title("Scalar gradient variance:\nexponential decay (barren plateau)")
    ax_l.legend(fontsize=8, loc="upper right")

    # Right panel: conserved operator-gradient HS-norm fraction (flat).
    for obs, recs in id2_results.items():
        ns = [r["n"] for r in recs]
        frac = [r["op_grad_fraction_mean"] for r in recs]
        err = [r["op_grad_fraction_std"] for r in recs]
        ax_r.errorbar(
            ns, frac, yerr=err, marker=markers[obs], color=colors[obs],
            label=f"{obs} $O$", lw=1.8, ms=6, capsize=3,
        )
    ax_r.set_xlabel("number of qubits $n$")
    ax_r.set_ylabel(r"$\|(i/2)[G,\Omega]\|^2_{HS} / \|O\|^2_{HS}$")
    ax_r.set_title("Operator gradient norm fraction:\nconserved (flat, $O(1)$)")
    ax_r.set_ylim(bottom=0)
    ax_r.legend(fontsize=9, loc="best")

    fig.suptitle(
        "Barren plateau as a projection artifact: scalar projection decays, operator norm is conserved",
        fontsize=12, y=1.02,
    )
    fig.tight_layout()

    os.makedirs(fig_dir, exist_ok=True)
    png = os.path.join(fig_dir, "projection_artifact.png")
    pdf = os.path.join(fig_dir, "projection_artifact.pdf")
    fig.savefig(png, bbox_inches="tight")
    fig.savefig(pdf, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {png}")
    print(f"  wrote {pdf}")


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def main():
    t0 = time.time()
    here = os.path.dirname(os.path.abspath(__file__))
    paper_dir = os.path.dirname(here)
    fig_dir = os.path.join(paper_dir, "figures")
    json_path = os.path.join(here, "result.json")

    print("=" * 70)
    print("IDENTITY 1: Var[<psi|A|psi>] = ||A||_HS^2 / (d(d+1))")
    print("=" * 70)
    id1_n = [1, 2, 3, 4]
    id1_results = check_identity1(id1_n, n_states=80000, rng=rng)

    print()
    print("=" * 70)
    print("IDENTITY 2: McClean decay vs conserved operator-gradient norm")
    print("=" * 70)
    id2_n = [2, 3, 4, 5, 6, 7, 8]
    observables = ["local", "global"]
    # fewer samples at large n is fine for variance estimate; keep fixed & honest.
    id2_results = check_identity2(id2_n, n_samples=2000, observables=observables, rng=rng)

    # Fit log-slope of Var[dC] vs n for each observable.
    slopes = {}
    intercepts = {}
    for obs, recs in id2_results.items():
        ns = [r["n"] for r in recs]
        vg = [r["var_grad_scalar"] for r in recs]
        sl, b = fit_log_slope(ns, vg)
        slopes[obs] = sl
        intercepts[obs] = b
        print(
            f"  [FIT] obs={obs:6s}: log10(Var) slope = {sl:.4f} /qubit "
            f"(ideal 2-design = {-np.log10(2):.4f})"
        )

    # Assemble structured results.
    out = dict(
        meta=dict(
            seed=SEED,
            description="Verification of operatorial-loss projection thesis (R2).",
            ideal_2design_slope=float(-np.log10(2)),
        ),
        identity1=id1_results,
        identity2=dict(
            per_observable={
                obs: dict(
                    points=recs,
                    log10_var_slope=slopes[obs],
                    log10_var_intercept=intercepts[obs],
                )
                for obs, recs in id2_results.items()
            }
        ),
    )

    with open(json_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\n  wrote {json_path}")

    # Figure.
    print("\nMaking figure...")
    make_figure(id2_results, slopes, fig_dir)

    print(f"\nDone in {time.time() - t0:.1f} s")


if __name__ == "__main__":
    main()
