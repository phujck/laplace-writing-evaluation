"""The GPU spectral seed's CPU fallback is the tested path — because it is the one that must run
everywhere, and because it is the SAME operator the GPU runs (one implementation, two array
modules, ``src/laplace/representation/spectral_gpu.py``).

His ruling ``PV-20260820T093000Z-gpu-takes-the-spectral-side`` makes CPU the fallback, never the
default. A fallback nobody exercises is a fallback that is broken the day it is needed, so these
run on every box, GPU or not. The two GPU cases skip cleanly when cupy is absent or the CUDA stack
is broken - the skip condition is ``gpu_ready()``, which PROBES cuBLAS with a real GEMM rather than
trusting that ``import cupy`` succeeding means the card works (measured 2026-08-20: it does not).
"""

import numpy as np
import pytest

from laplace.representation import spectral_gpu as S

pytestmark = pytest.mark.filterwarnings("ignore::RuntimeWarning")

_GPU_OK, _GPU_WHY = S.gpu_ready()
needs_gpu = pytest.mark.skipif(not _GPU_OK, reason=f"no usable CUDA device: {_GPU_WHY}")


def _basis(n=120, d=24, seed=3, unit=True):
    """A small basis shaped like the fold's: unit-normalised rows, so the incumbent's
    ``fill_diagonal(A, 1.0)`` is the no-op the factored identity relies on."""
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(n, d))
    if unit:
        X /= np.linalg.norm(X, axis=1, keepdims=True)
    return X


def test_cpu_fallback_matches_the_dense_incumbent_arithmetic():
    """The gate the bench runs at n=500, held here at n=120 so it runs in CI: the factor-form
    bottom-k against ``numpy.linalg.eigvalsh`` of the same normalised Laplacian."""
    X = _basis()
    ref = S.dense_laplacian_eigenvalues(X, 6)
    out = S.spectral_bottom(X, 6, backend="cpu", dtype="float64")
    assert out["backend"] == "cpu"
    assert np.max(np.abs(out["eigenvalues"] - ref)) <= 1e-4
    assert out["eigenvalues"][0] == pytest.approx(0.0, abs=1e-8)   # connected graph -> one zero
    assert np.all(np.diff(out["eigenvalues"]) >= -1e-12)           # returned ascending
    assert out["matvecs"] > 0                                      # the count is MEASURED
    # the working set is X plus one n-vector and NOTHING else - no n^2 object was allocated
    assert out["working_set_bytes"] == X.nbytes + X.shape[0] * X.itemsize


def test_the_affinity_is_never_formed_and_the_matvec_is_the_incumbent_s():
    """``A v`` through the factor form equals ``A v`` through the incumbent's dense A, to float64
    round-off - the identity, not an approximation."""
    X = _basis()
    n = X.shape[0]
    A = (X @ X.T + 1.0) / 2.0
    np.fill_diagonal(A, 1.0)                       # meaning_upfold._best_split:414, verbatim
    v = np.random.default_rng(5).normal(size=n)
    ff = S.FactorForm(X, np)
    assert np.allclose(ff.affinity_matvec(v), A @ v, rtol=0, atol=1e-10)
    assert np.allclose(ff.degree(), A.sum(axis=1), rtol=0, atol=1e-10)
    assert ff.matvecs == 1
    assert ff.flops() == pytest.approx(4.0 * n * X.shape[1] + 5.0 * n)


def test_the_working_set_scales_in_n_not_in_n_squared():
    """Wall 1's killer, as an assertion rather than a claim: doubling n doubles this operator's
    memory, while the affinity it replaces quadruples. At the fold's real n=14,300 that is 22 MB
    against an 818 MB float32 dense affinity on a 4 GB card."""
    small = S.FactorForm(_basis(n=200, d=24), np)
    big = S.FactorForm(_basis(n=400, d=24), np)
    assert big.working_set_bytes == pytest.approx(2 * small.working_set_bytes, rel=0.01)
    assert big.working_set_bytes < (400 ** 2) * 8 / 10          # vs the dense A it never builds


def test_the_diagonal_repair_is_carried_for_non_unit_rows():
    """Unit rows make ``fill_diagonal`` a no-op; NON-unit rows are where a factored form that
    silently drops the repair stops being the incumbent's operator. It must still match."""
    X = _basis(n=60, d=12, seed=9, unit=False) * 0.4      # deliberately off the sphere
    ff = S.FactorForm(X, np)
    assert ff.diagonal_repair_max > 1e-3                  # the repair is real here, not round-off
    ref = S.dense_laplacian_eigenvalues(X, 5)
    out = S.spectral_bottom(X, 5, backend="cpu", dtype="float64")
    assert np.max(np.abs(out["eigenvalues"] - ref)) <= 1e-4


def test_the_env_flag_governs_the_default_and_cpu_is_the_fallback(monkeypatch):
    monkeypatch.delenv(S.ENV_FLAG, raising=False)
    assert S.gpu_requested() is False
    backend, why = S.backend_choice()
    assert backend == "cpu" and S.ENV_FLAG in why        # an unset flag NAMES itself
    monkeypatch.setenv(S.ENV_FLAG, "1")
    assert S.gpu_requested() is True
    backend, why = S.backend_choice()
    assert backend == ("gpu" if _GPU_OK else "cpu")
    if backend == "cpu":
        assert why                                       # a refusal is never silent


def test_the_production_fold_takes_the_device_by_default_and_the_seed_stays_opt_in():
    """THE FENCE MOVED, 2026-08-20 (this test previously asserted the opposite).

    It used to assert that ``meaning_upfold`` did not so much as name this module - the seed was the
    instrument, not the swap, and the swap was owed parity gates. Those gates were run (eigenvalue
    parity 1.2e-7 at n=500/2000 against the incumbent's own dense arithmetic; identical chosen k,
    identical partitions and identical silhouettes at n=500/1500/3000 on the live basis) and his
    ruling ``PV-20260820T093000Z-gpu-takes-the-spectral-side`` is what the fold now obeys. So the
    contract under test inverts: the PRODUCTION fold reaches for the device by DEFAULT, and the two
    polarities stay distinct - ``ENV_FLAG`` opts the SEED in, ``DENY_FLAG`` opts the FOLD out."""
    from pathlib import Path
    src = Path(__file__).resolve().parents[1] / "src/laplace/engine/meaning_upfold.py"
    body = src.read_text(encoding="utf-8")
    assert "spectral_gpu" in body                     # the swap landed
    assert "fold_backend_choice" in body              # ...through the fold's own polarity
    assert S.ENV_FLAG not in body                     # ...and NOT through the seed's opt-in flag
    assert S.DENY_FLAG in body                        # the deny is the fold's only env lever


def test_fold_backend_choice_is_deny_polarity_not_opt_in(monkeypatch):
    """The seed opts IN; the fold opts OUT. The two must never be confused - an opt-in default would
    silently keep the 15-minute CPU path his complaint names."""
    monkeypatch.delenv(S.DENY_FLAG, raising=False)
    monkeypatch.delenv(S.ENV_FLAG, raising=False)
    backend, why = S.fold_backend_choice()
    assert backend == ("gpu" if _GPU_OK else "cpu")   # unset means GPU where there IS one
    if backend == "cpu":
        assert why                                    # ...and a fallback always names itself
    monkeypatch.setenv(S.DENY_FLAG, "1")
    backend, why = S.fold_backend_choice()
    assert backend == "cpu" and S.DENY_FLAG in why


def test_bad_k_is_refused_loudly():
    X = _basis(n=20, d=8)
    with pytest.raises(ValueError):
        S.spectral_bottom(X, 20, backend="cpu")
    with pytest.raises(ValueError):
        S.spectral_bottom(X, 0, backend="cpu")
    with pytest.raises(ValueError):
        S.spectral_bottom(X, 3, backend="tpu")


@needs_gpu
def test_gpu_agrees_with_the_dense_incumbent_arithmetic():
    X = _basis(n=400, d=48, seed=17)
    ref = S.dense_laplacian_eigenvalues(X, 8)
    out = S.spectral_bottom(X, 8, backend="gpu", dtype="float32")
    assert out["backend"] == "gpu"
    assert np.max(np.abs(out["eigenvalues"] - ref)) <= 1e-4
    assert out["vram_pool_peak_bytes"] < out["vram_device_total_bytes"]


@needs_gpu
def test_gpu_and_cpu_are_the_same_operator():
    X = _basis(n=400, d=48, seed=17)
    g = S.spectral_bottom(X, 8, backend="gpu", dtype="float32")["eigenvalues"]
    c = S.spectral_bottom(X, 8, backend="cpu", dtype="float64")["eigenvalues"]
    assert np.max(np.abs(g - c)) <= 1e-4


# ---------------------------------------------------------------------------
# FoldSpectral - the PRODUCTION embedding. A different operator from the seed above, and the
# difference is the point: this one reproduces what sklearn's SpectralClustering actually factors.
# ---------------------------------------------------------------------------

def test_the_fold_operator_is_the_loop_free_one_and_the_seed_is_not():
    """``ATLAS_MATHEMATICS`` §2.2 says sklearn 'overwrites the diagonal' of ``L_sym``; what scipy
    actually does is zero the ADJACENCY diagonal first, so the degree excludes the self-loop. The
    two operators are genuinely different, and the fold must use the second one - otherwise every
    eigenvector is computed from a degree that is off by 1 in ~1000."""
    X = _basis(n=150, d=16, seed=5)
    with_loops = S.dense_laplacian_eigenvalues(X, 8)
    without = S.dense_fold_laplacian_eigenvalues(X, 8)
    assert np.max(np.abs(with_loops - without)) > 1e-6          # not the same operator
    fs = S.FoldSpectral(X, backend="cpu", dtype="float64")
    _E, lam = fs.embedding(8)
    assert np.max(np.abs(lam - without)) <= 1e-4                # the fold takes the loop-free one
    fs.close()


def test_fold_embedding_reproduces_sklearns_own_maps():
    """The whole contract in one assertion: the subspace ``FoldSpectral`` hands k-means is the
    subspace ``sklearn.manifold._spectral_embedding`` hands it - same rescale, same retained trivial
    vector. Compared by principal angles, because eigenvectors inside a degenerate block are defined
    only up to rotation and equality there would be a wrong test, not a strict one."""
    from sklearn.manifold._spectral_embedding import _spectral_embedding
    from sklearn.utils import check_random_state
    X = _basis(n=200, d=24, seed=9)
    A = (X @ X.T + 1.0) / 2.0
    np.fill_diagonal(A, 1.0)
    maps = _spectral_embedding(A, n_components=6, eigen_solver=None,
                               random_state=check_random_state(0), eigen_tol="auto",
                               drop_first=False)
    fs = S.FoldSpectral(X, backend="cpu", dtype="float64")
    E, _lam = fs.embedding(6)
    fs.close()
    Qa, _ = np.linalg.qr(maps)
    Qb, _ = np.linalg.qr(E)
    assert float(np.linalg.svd(Qa.T @ Qb, compute_uv=False).min()) > 1 - 1e-6


def test_the_k_sweep_slices_one_solve_exactly():
    """The 7x re-solve is removed by NESTING, not by approximation: the bottom-k eigenspace is a
    prefix of the bottom-k_max one, so slicing must be exact, not close."""
    X = _basis(n=200, d=24, seed=11)
    fs = S.FoldSpectral(X, backend="cpu", dtype="float64")
    E8, _ = fs.embedding(8)
    E3, _ = fs.embedding(3)
    fs.close()
    assert np.max(np.abs(E8[:, :3] - E3)) <= 1e-12


@pytest.mark.parametrize("labels_kind", ["plain", "singleton"])
def test_factored_silhouette_is_sklearns_silhouette(labels_kind):
    """The n x n cosine-distance matrix is never built; the identity that replaces it has to be
    exact, INCLUDING sklearn's 0-for-a-singleton-cluster convention."""
    from sklearn.metrics import silhouette_score
    X = _basis(n=180, d=16, seed=13)
    rng = np.random.default_rng(2)
    labels = rng.integers(0, 4, len(X))
    if labels_kind == "singleton":
        labels[0] = 99
    dist = np.clip(1.0 - (X @ X.T), 0.0, 2.0)
    np.fill_diagonal(dist, 0.0)
    ref = float(silhouette_score(dist, labels, metric="precomputed"))
    fs = S.FoldSpectral(X, backend="cpu", dtype="float64")
    assert abs(fs.silhouette(labels) - ref) <= 1e-9
    fs.close()


def test_non_unit_rows_are_detected_not_silently_approximated():
    """The factored silhouette is exact only while ``clip(1 - x.x, 0, 2)`` cannot bite. That is a
    property of unit rows, so it is CHECKED - ``_best_split_gpu`` refuses rather than approximate."""
    X = _basis(n=60, d=8, seed=4, unit=False)
    fs = S.FoldSpectral(X, backend="cpu", dtype="float64")
    assert fs.rows_are_unit is False
    fs.close()
    fs = S.FoldSpectral(_basis(n=60, d=8, seed=4), backend="cpu", dtype="float64")
    assert fs.rows_are_unit is True
    fs.close()


@needs_gpu
def test_fold_gpu_matches_the_dense_fold_reference():
    X = _basis(n=400, d=48, seed=17)
    ref = S.dense_fold_laplacian_eigenvalues(X, 8)
    fs = S.FoldSpectral(X, backend="gpu", dtype="float32")
    _E, lam = fs.embedding(8)
    fs.close()
    assert np.max(np.abs(lam - ref)) <= 1e-4
