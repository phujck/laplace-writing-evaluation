"""The GPU spectral seed — the fold's algebraic side, with the affinity never formed.

HIS RULING (``PV-20260820T093000Z-gpu-takes-the-spectral-side``, 2026-08-20, verbatim): "the GPU
should definitely be doing the spectral side as well shouldn't it? Why on earth would you be doing
any of these algebraic processes by CPU?" That ruling fills the MIGRATION-OPEN gap
``ATLAS_MATHEMATICS.md`` §8.3 names in its own words: **"No document specifies a GPU eigensolver or
a GPU embedding path for the engine's own fold."** This module is that specification, executable.

THE IDENTITY (the S2 precedent, git ``97bae316``, proven on the pilot night at n = 14,300 —
98x deployed wall / 133x eigensolve against the incumbent's own top split, ARI 0.9986). The
incumbent's affinity, read straight off ``meaning_upfold._best_split``::

    A = (X @ X.T + 1.0) / 2.0        # meaning_upfold.py:413
    np.fill_diagonal(A, 1.0)         # meaning_upfold.py:414

For L2-normalised rows ``A_ii = (||x_i||^2 + 1)/2 = 1`` already, so the ``fill_diagonal`` is a
no-op — but it is carried here EXACTLY, as a diagonal correction ``delta_i = (1 - ||x_i||^2)/2``
added to the factored form, so this operator is the same operator for ANY X, not merely for the
unit-normalised X the fold happens to hand it. ``diagonal_repair_max = max|delta|`` is reported on
every solve; on the live basis it measures ~1e-8, which is the number that licenses the identity.

With the correction in hand the affinity is applied and never materialised::

    A v   = ( X (X.T v) + (1.T v) 1 ) / 2 + delta * v          4nd + O(n) flops, ZERO n^2 memory
    deg   = A 1 = ( X (X.T 1) + n 1 ) / 2 + delta              2nd + O(n) flops, ZERO n^2 memory
    M     = D^{-1/2} A D^{-1/2}                                the same, twice scaled
    L_sym = I - M          =>   lambda(L_sym) = 1 - mu(M)

so the BOTTOM k of the normalised Laplacian are the TOP k of M: one Lanczos pass, no dense object,
no factorisation, no shift-invert. At n = 14,300, d = 384 the dense affinity the incumbent must
materialise is 1.64 GB float64 / 818 MB float32; this operator's whole working set is X itself at
~22 MB in float32 — which is what makes a 4 GB card the right home for it rather than a stretch.

TWO SURFACES LIVE HERE, and they are not the same operator.

  * ``spectral_bottom`` — THE SEED (2026-08-20, ``LAPLACE_SPECTRAL_GPU``, benched at
    ``evidence/SELF_AUDIT_2026-08-20/gpu_spectral_bench.json``). It is the normalised Laplacian of
    the affinity WITH its self-loops, which is the operator ``ATLAS_MATHEMATICS.md`` §2.2 describes.
    Its numbers are banked; it is left exactly as it was benched.

  * ``FoldSpectral`` — THE PRODUCTION EMBEDDING (2026-08-20, second pass). It reproduces what
    ``sklearn.cluster.SpectralClustering(affinity="precomputed")`` ACTUALLY factors, which is
    measurably NOT the operator above. §2.2 says sklearn "overwrites the diagonal" of ``L_sym``;
    what scipy's ``csgraph_laplacian(normed=True)`` really does is ZERO THE ADJACENCY DIAGONAL
    FIRST (``_laplacian_dense``'s ``np.fill_diagonal(m, 0)``), take the degree of what remains, and
    set the Laplacian diagonal to 1 — so the operator is the normalised Laplacian of the
    SELF-LOOP-FREE affinity, with ``deg_i = Σ_j A_ij − 1``, and sklearn's own ``_set_diag`` is a
    no-op on that branch. Verified numerically against scikit-learn 1.9.0 + scipy 1.18.0 in this
    ``.venv`` (max abs deviation 1.4e-17 over the whole matrix), not read off the docstrings. The
    difference is not cosmetic: on a 1,200-leaf sample the two degrees differ by ~1/1000 of their
    value, which moves every eigenvector. ``FactorForm(self_loops=False)`` carries it exactly.

CPU IS THE FALLBACK, NEVER THE DEFAULT (his ruling, same line). For the SEED, absent cupy or absent
a device, the identical operator runs through ``scipy.sparse.linalg.LinearOperator`` and the same
Lanczos, so the code path under test is one path with two array modules. For the PRODUCTION fold,
the no-hardware fallback is the incumbent dense sklearn path itself (``meaning_upfold``'s
``_best_split_dense``), untouched — a fallback that is the thing being replaced cannot drift from it.
"""

from __future__ import annotations

import os
import time
from typing import Any

ENV_FLAG = "LAPLACE_SPECTRAL_GPU"        # the SEED's opt-in (unchanged)
DENY_FLAG = "LAPLACE_NO_SPECTRAL_GPU"    # the PRODUCTION fold's explicit deny (his ruling: GPU default)
_TRUTHY = {"1", "true", "yes", "on"}

__all__ = [
    "DENY_FLAG", "ENV_FLAG", "EigensolverDeclined", "FactorForm", "FoldSpectral", "backend_choice", "cupy_module",
    "dense_fold_laplacian_eigenvalues", "dense_laplacian_eigenvalues", "fold_backend_choice",
    "gpu_ready", "gpu_requested", "silhouette_cosine_factored", "spectral_bottom",
]


class EigensolverDeclined(RuntimeError):
    """Every bounded GPU eigensolver attempt declined one cluster's operator.

    This is numerical residue, not a device verdict. The caller keeps the cluster
    intact and fingerprints that cut; it must never switch the rest of the fold to
    another device.
    """

    def __init__(self, attempts: list[dict[str, str]]):
        self.attempts = attempts
        stages = ", ".join(attempt["stage"] for attempt in attempts)
        super().__init__(f"GPU eigensolver declined after {stages}")


# ---------------------------------------------------------------------------
# availability — every refusal NAMES itself (the enemy is the quiet degrade)
# ---------------------------------------------------------------------------

def gpu_requested() -> bool:
    """True when the env flag asks for the GPU path. Unset means CPU, no message: this seed is
    opt-in until the parity gates pass, so an unset flag is an ordinary state, not a degrade."""
    return str(os.environ.get(ENV_FLAG, "")).strip().lower() in _TRUTHY


def cupy_module():
    """``(cupy, "")`` or ``(None, why)`` — never a bare None, so the caller can say what happened."""
    try:
        from laplace.representation import cuda_libs
        cuda_libs.preload()  # pip-shipped NVIDIA .so files, dlopen'd by absolute path first
        import cupy  # noqa: PLC0415 - deliberately lazy: importing cupy costs a CUDA context
    except Exception as exc:  # noqa: BLE001 - an absent/ABI-broken cupy is an ordinary CPU day
        return None, f"cupy did not import ({type(exc).__name__}: {exc})"
    return cupy, ""


def gpu_ready() -> tuple[bool, str]:
    """Is there a usable device AND a working cuBLAS behind it? Both are checked by DOING one,
    because ``cupy`` imports cleanly against a mismatched CUDA runtime and only fails at the first
    GEMM (measured on this box 2026-08-20: cupy-cuda12x imported, saw the A2000, then raised
    ``ImportError: libcublas.so.12`` on the first matmul — the box carries the cu13 libraries)."""
    cupy, why = cupy_module()
    if cupy is None:
        return False, why
    try:
        if cupy.cuda.runtime.getDeviceCount() < 1:
            return False, "cupy imported but no CUDA device is visible"
        probe = cupy.ones((4, 3), dtype=cupy.float32)
        float((probe @ probe.T).sum())     # forces cuBLAS to actually load and run
    except Exception as exc:  # noqa: BLE001 - a broken CUDA stack degrades to CPU, loudly named
        return False, f"the CUDA probe failed ({type(exc).__name__}: {exc})"
    return True, ""


def backend_choice() -> tuple[str, str]:
    """THE SEED's choice: opt-in, ``LAPLACE_SPECTRAL_GPU``. ``("gpu"|"cpu", why)``; ``why`` is empty
    on a clean choice and names the refusal otherwise. Left as benched."""
    if not gpu_requested():
        return "cpu", f"{ENV_FLAG} is not set (the GPU seed is opt-in until the parity gates pass)"
    ok, why = gpu_ready()
    return ("gpu", "") if ok else ("cpu", why)


def fold_backend_choice() -> tuple[str, str]:
    """THE PRODUCTION FOLD's choice, and it is the INVERSE polarity of the seed's.

    HIS RULING (``PV-20260820T093000Z-gpu-takes-the-spectral-side``): every algebraic organ of the
    fold targets the GPU on this box; CPU survives only as the no-hardware fallback, never the
    default. So there is no opt-IN here - ``LAPLACE_NO_SPECTRAL_GPU`` is the explicit DENY, and an
    absent cupy or an absent device is a fallback that NAMES itself rather than a quiet default."""
    if str(os.environ.get(DENY_FLAG, "")).strip().lower() in _TRUTHY:
        return "cpu", f"{DENY_FLAG} is set (the explicit deny)"
    ok, why = gpu_ready()
    return ("gpu", "") if ok else ("cpu", why)


# ---------------------------------------------------------------------------
# the operator — array-module agnostic, so GPU and CPU are ONE implementation
# ---------------------------------------------------------------------------

class FactorForm:
    """``A = (X X.T + J)/2`` with ``A_ii`` repaired to 1, applied and never formed.

    ``xp`` is ``numpy`` or ``cupy``; ``X`` is that module's (n, d) array. Every matvec is counted,
    so the flop figure a bench prints is MEASURED off the solve rather than modelled from k.

    ``self_loops=False`` gives the SAME affinity with its diagonal zeroed - which is what
    scipy's ``csgraph_laplacian`` builds its degree from, and therefore what the incumbent
    ``SpectralClustering`` actually factors (see the module docstring). Because the repair has
    already forced ``A_ii = 1`` EXACTLY, zeroing the diagonal is exactly ``A - I``: subtract ``v``
    from the matvec and ``1`` from the degree, with no second n-vector to carry."""

    def __init__(self, X, xp, *, self_loops: bool = True):
        self.xp, self.X = xp, X
        self.n, self.d = int(X.shape[0]), int(X.shape[1])
        self.self_loops = bool(self_loops)
        self.row_norm2 = (X * X).sum(axis=1)
        # meaning_upfold.py:414's np.fill_diagonal(A, 1.0), carried exactly. Zero for unit rows.
        self.delta = (1.0 - self.row_norm2) * X.dtype.type(0.5)
        self.matvecs = 0

    @property
    def diagonal_repair_max(self) -> float:
        """``max|delta|`` — how far the factored diagonal sat from the incumbent's forced 1.0.
        This is the number that says the identity holds, so it is reported, never assumed."""
        return float(abs(self.delta).max()) if self.n else 0.0

    @property
    def working_set_bytes(self) -> int:
        return int(self.X.nbytes + self.delta.nbytes)

    def degree(self):
        """``deg = A 1 = (X (X.T 1) + n 1)/2 + delta`` — O(nd), no n^2 anywhere. Loop-free: ``-1``."""
        s = self.X.sum(axis=0)
        deg = (self.X @ s + self.X.dtype.type(self.n)) * self.X.dtype.type(0.5) + self.delta
        return deg if self.self_loops else deg - self.X.dtype.type(1.0)

    def affinity_matvec(self, v):
        """``A v = (X (X.T v) + (1.T v) 1)/2 + delta * v``. Loop-free: ``- v`` (since ``A_ii = 1``)."""
        self.matvecs += 1
        half = self.X.dtype.type(0.5)
        out = (self.X @ (self.X.T @ v) + v.sum()) * half + self.delta * v
        return out if self.self_loops else out - v

    def flops(self) -> float:
        """4nd for the two GEMVs plus ~5n for the scalings, the rank-one term and the repair."""
        return self.matvecs * (4.0 * self.n * self.d + 5.0 * self.n)


def _eigsh_top(op, k: int, eigsh, xp, *, tol: float, maxiter: int | None, ncv: int | None):
    """Top-k algebraic eigenpairs of the normalised affinity ``M`` (spectrum in [-1, 1]).

    ``which="LA"`` is the direct ask. Where a backend's Lanczos does not offer it, ``M + I`` has a
    NON-NEGATIVE spectrum, so its largest-magnitude pairs ARE its largest-algebraic pairs and
    ``which="LM"`` is exact rather than approximate — the shift changes no Krylov space, only the
    selection rule. Returns ``(mu, U, which_used)``."""
    kw: dict[str, Any] = {"k": k, "tol": tol}
    if maxiter is not None:
        kw["maxiter"] = maxiter
    if ncv is not None:
        kw["ncv"] = ncv
    try:
        mu, U = eigsh(op, which="LA", **kw)
        return mu, U, "LA"
    except (ValueError, NotImplementedError, TypeError) as exc:
        shifted = _shift_by_identity(op, xp)
        if shifted is None:
            raise
        mu, U = eigsh(shifted, which="LM", **kw)
        return mu - 1.0, U, f"LM(M+I) [LA refused: {type(exc).__name__}]"


def _shift_by_identity(op, xp):
    """``M -> M + I`` as another LinearOperator of the same class (or None if not constructible)."""
    cls = type(op)
    try:
        return cls(shape=op.shape, matvec=lambda v: op.matvec(v) + v.ravel(), dtype=op.dtype)
    except Exception:  # noqa: BLE001 - a backend whose LinearOperator will not take a closure
        return None


# ---------------------------------------------------------------------------
# the public solve
# ---------------------------------------------------------------------------

def spectral_bottom(X, k: int = 8, *, backend: str | None = None, dtype: str = "float32",
                    tol: float = 0.0, maxiter: int | None = None, ncv: int | None = None,
                    return_vectors: bool = False) -> dict[str, Any]:
    """Bottom-k eigenvalues of the normalised Laplacian of ``meaning_upfold``'s cosine affinity,
    computed through the factored operator so the n x n affinity is never allocated.

    ``X`` is the (n, d) numpy basis, row-aligned as ``meaning_upfold._embed`` returns it (rows
    unit-normalised in the fold; non-unit rows are handled exactly by the diagonal repair, not
    silently renormalised). ``backend`` overrides ``backend_choice()`` — pass ``"cpu"`` or
    ``"gpu"`` in a test; leave it None in anything that should honour the env flag.

    Returns a dict carrying the eigenvalues ASCENDING as float64 numpy, plus every number a bench
    or a gate needs to be checked rather than believed: the backend actually used and why, the
    measured matvec count and flops, the diagonal repair, the working set, and (on GPU) the memory
    pool's high-water mark for this solve."""
    import numpy as np

    if backend is None:
        backend, why = backend_choice()
    else:
        backend, why = backend, "caller override"
    if backend not in ("cpu", "gpu"):
        raise ValueError(f"backend must be 'cpu' or 'gpu', not {backend!r}")

    Xnp = np.ascontiguousarray(np.asarray(X), dtype=np.dtype(dtype))
    n, d = Xnp.shape
    if k < 1 or k >= n:
        raise ValueError(f"k must satisfy 1 <= k < n; got k={k} for n={n}")

    vram_peak = None
    if backend == "gpu":
        cupy, cwhy = cupy_module()
        if cupy is None:
            raise RuntimeError(f"backend='gpu' asked for, but {cwhy}")
        from cupyx.scipy.sparse.linalg import LinearOperator, eigsh  # noqa: PLC0415
        pool = cupy.get_default_memory_pool()
        pool.free_all_blocks()          # so total_bytes() below is THIS solve's high-water mark
        xp = cupy
        Xdev = cupy.asarray(Xnp)
    else:
        from scipy.sparse.linalg import LinearOperator, eigsh  # noqa: PLC0415
        xp = np
        Xdev = Xnp

    ff = FactorForm(Xdev, xp)
    deg = ff.degree()
    # the fold's affinity is strictly positive ((x.x + 1)/2 >= 0, +1 on the diagonal), so every
    # degree is >= 1; the clip is a guard against a pathological X, not an expected branch.
    dinv = 1.0 / xp.sqrt(xp.clip(deg, xp.asarray(1e-12, dtype=Xdev.dtype), None))

    def _mv(v):
        u = dinv * v.ravel()
        return dinv * ff.affinity_matvec(u)

    op = LinearOperator(shape=(n, n), matvec=_mv, dtype=Xdev.dtype)

    if backend == "gpu":
        xp.cuda.Stream.null.synchronize()
    t0 = time.perf_counter()
    mu, U, which_used = _eigsh_top(op, k, eigsh, xp, tol=tol, maxiter=maxiter, ncv=ncv)
    if backend == "gpu":
        xp.cuda.Stream.null.synchronize()
    wall = time.perf_counter() - t0

    mu_np = np.asarray(xp.asnumpy(mu) if backend == "gpu" else mu, dtype=np.float64)
    lam = np.sort(1.0 - mu_np)                    # lambda(L_sym) = 1 - mu(M), ascending
    out: dict[str, Any] = {
        "backend": backend, "backend_why": why, "which": which_used,
        "n": int(n), "d": int(d), "k": int(k), "dtype": str(Xnp.dtype),
        "eigenvalues": lam,
        "wall_sec": float(wall),
        "matvecs": int(ff.matvecs),
        "flops_measured": float(ff.flops()),
        "diagonal_repair_max": ff.diagonal_repair_max,
        "working_set_bytes": ff.working_set_bytes,
    }
    if backend == "gpu":
        cupy, _ = cupy_module()
        vram_peak = int(cupy.get_default_memory_pool().total_bytes())
        free_b, total_b = cupy.cuda.Device().mem_info
        out["vram_pool_peak_bytes"] = vram_peak
        out["vram_device_total_bytes"] = int(total_b)
        out["vram_device_free_bytes"] = int(free_b)
    if return_vectors:
        Unp = np.asarray(xp.asnumpy(U) if backend == "gpu" else U, dtype=np.float64)
        out["eigenvectors"] = Unp[:, np.argsort(-mu_np)]
    return out


# ---------------------------------------------------------------------------
# the production embedding — sklearn's own pipeline, factored, computed ONCE at k_max
# ---------------------------------------------------------------------------

def _sign_flip(E):
    """``sklearn.utils.extmath._deterministic_vector_sign_flip``, applied per COMPONENT (column).

    sklearn flips each row of its (k, n) embedding so the entry of largest magnitude is positive;
    our embedding is (n, k), so the same rule runs down the columns. It is a reflection, so it
    changes no clustering — it is carried because it is what makes OUR eigenvectors reproducible
    run to run, which is the property the incumbent got for free from a seeded ARPACK ``v0``."""
    import numpy as np
    idx = np.argmax(np.abs(E), axis=0)
    signs = np.sign(E[idx, np.arange(E.shape[1])])
    signs[signs == 0] = 1.0
    return E * signs


class FoldSpectral:
    """One ``_best_split``'s worth of algebra, with ``X`` resident on the chosen device.

    THE CONTRACT REPRODUCED (``ATLAS_MATHEMATICS.md`` §2.2, corrected against the installed
    scikit-learn — see the module docstring): the affinity ``A = (X X.T + 1)/2`` with ``A_ii = 1``;
    the normalised Laplacian of ``A`` WITH ITS DIAGONAL ZEROED, ``L' = I − D^{-1/2} A_off D^{-1/2}``,
    ``deg = A_off 1``; the bottom-k eigenvectors of ``L'`` (trivial vector RETAINED — sklearn passes
    ``drop_first=False``); each rescaled by ``1/√deg`` to recover the random-walk vectors ``u =
    D^{-1/2} x``; then the deterministic sign flip. That (n, k) array IS sklearn's ``maps``.

    THE k-SWEEP COLLAPSES TO ONE SOLVE. The incumbent refits ``SpectralClustering`` for every
    ``k ∈ [2, 8]``, i.e. seven eigen-solves of the same operator for seven NESTED subspaces. The
    bottom-k set is a prefix of the bottom-k_max set, so ``embedding(k)`` is literally
    ``embedding(k_max)[:, :k]`` — one solve at ``k_max``, sliced. That alone removes the 7x
    re-solve, before the device is considered.

    The solve is Lanczos on the factored operator: ``L' = I − M`` so the BOTTOM of ``L'`` is the TOP
    of ``M``, and ``M`` is applied through ``FactorForm`` in ``O(nd)`` per matvec with the n×n
    affinity never allocated."""

    def __init__(self, X, *, backend: str | None = None, dtype: str = "float32",
                 tol: float = 0.0, maxiter: int | None = None, ncv: int | None = None):
        import numpy as np
        if backend is None:
            backend, why = fold_backend_choice()
        else:
            why = "caller override"
        if backend not in ("cpu", "gpu"):
            raise ValueError(f"backend must be 'cpu' or 'gpu', not {backend!r}")
        Xnp = np.ascontiguousarray(np.asarray(X), dtype=np.dtype(dtype))
        self.backend, self.backend_why = backend, why
        self.n, self.d = int(Xnp.shape[0]), int(Xnp.shape[1])
        self.tol, self.maxiter, self.ncv = tol, maxiter, ncv
        self.solve_wall_sec = 0.0
        if backend == "gpu":
            cupy, cwhy = cupy_module()
            if cupy is None:
                raise RuntimeError(f"backend='gpu' asked for, but {cwhy}")
            from cupyx.scipy.sparse.linalg import LinearOperator, eigsh  # noqa: PLC0415
            self.xp, self.X = cupy, cupy.asarray(Xnp)
        else:
            from scipy.sparse.linalg import LinearOperator, eigsh  # noqa: PLC0415
            self.xp, self.X = np, Xnp
        self._LinearOperator, self._eigsh = LinearOperator, eigsh
        self.ff = FactorForm(self.X, self.xp, self_loops=False)
        deg = self.ff.degree()
        tiny = self.xp.asarray(1e-12, dtype=self.X.dtype)
        self.dinv = 1.0 / self.xp.sqrt(self.xp.clip(deg, tiny, None))

    # -- the guard: the silhouette identity below is EXACT only where the clip cannot bite -------
    @property
    def rows_are_unit(self) -> bool:
        """Is every row L2-normalised (to float32's resolution)? ``meaning_upfold._embed`` normalises,
        so this is true in the fold; it is CHECKED rather than assumed because the factored silhouette
        below is exact only when ``1 − x_i·x_j`` never leaves ``[0, 2]``, which Cauchy-Schwarz
        guarantees for unit rows and nothing guarantees otherwise."""
        return float(abs(self.ff.row_norm2 - 1.0).max()) <= 1e-5 if self.n else True

    @staticmethod
    def _nonconvergence(exc: BaseException) -> bool:
        """Recognise the numerical decline across NumPy, SciPy and CuPy vocabularies."""
        name = type(exc).__name__.lower()
        message = str(exc).lower()
        return ("noconvergence" in name or "no convergence" in message or
                "did not converge" in message or "failed to converge" in message)

    def _operator(self, *, dtype=None, jitter: float = 0.0):
        """Build this cluster's operator, optionally in another GPU precision.

        Jitter is a deterministic zero-mean diagonal spread. An identity shift
        cannot split a repeated eigenspace and therefore would not cure the failure
        this retry exists for.
        """
        X = self.X if dtype is None else self.X.astype(dtype, copy=False)
        ff = self.ff if X is self.X else FactorForm(X, self.xp, self_loops=False)
        tiny = self.xp.asarray(1e-12, dtype=X.dtype)
        dinv = 1.0 / self.xp.sqrt(self.xp.clip(ff.degree(), tiny, None))
        diagonal = None
        if jitter:
            if self.n == 1:
                diagonal = self.xp.zeros(1, dtype=X.dtype)
            else:
                diagonal = (self.xp.linspace(-0.5, 0.5, self.n, dtype=X.dtype) *
                            X.dtype.type(jitter))

        def _mv(v):
            flat = v.ravel()
            out = dinv * ff.affinity_matvec(dinv * flat)
            return out if diagonal is None else out + diagonal * flat

        return X, ff, dinv, self._LinearOperator(
            shape=(self.n, self.n), matvec=_mv, dtype=X.dtype)

    def _finish_embedding(self, mu, U, dinv):
        import numpy as np
        xp = self.xp
        mu_np = np.asarray(xp.asnumpy(mu) if self.backend == "gpu" else mu, dtype=np.float64)
        Unp = np.asarray(xp.asnumpy(U) if self.backend == "gpu" else U, dtype=np.float64)
        dd_inv = np.asarray(xp.asnumpy(dinv) if self.backend == "gpu" else dinv,
                            dtype=np.float64)
        if not (np.isfinite(mu_np).all() and np.isfinite(Unp).all() and
                np.isfinite(dd_inv).all()):
            raise np.linalg.LinAlgError("eigenpairs did not converge to finite values")
        order = np.argsort(-mu_np)
        lam = 1.0 - mu_np[order]
        embedding = Unp[:, order] * dd_inv[:, None]
        if not np.isfinite(embedding).all():
            raise np.linalg.LinAlgError("eigenpairs did not converge to a finite embedding")
        return _sign_flip(embedding), lam

    def _embedding_eigsh(self, k: int, *, dtype=None, jitter: float = 0.0,
                         tol: float | None = None):
        _X, _ff, dinv, op = self._operator(dtype=dtype, jitter=jitter)
        xp = self.xp
        if self.backend == "gpu":
            xp.cuda.Stream.null.synchronize()
        t0 = time.perf_counter()
        mu, U, self.which = _eigsh_top(op, k, self._eigsh, xp,
                                       tol=self.tol if tol is None else tol,
                                       maxiter=self.maxiter, ncv=self.ncv)
        if self.backend == "gpu":
            xp.cuda.Stream.null.synchronize()
        self.solve_wall_sec += time.perf_counter() - t0
        return self._finish_embedding(mu, U, dinv)

    def _embedding_power(self, k: int, *, tol: float, iterations: int):
        """Deterministic block-power/Rayleigh-Ritz recovery on the same GPU operator."""
        xp = self.xp
        _X, ff, dinv, _op = self._operator(dtype=xp.float64)

        def apply(Q):
            return xp.stack([dinv * ff.affinity_matvec(dinv * Q[:, j])
                             for j in range(Q.shape[1])], axis=1)

        rows = xp.arange(self.n, dtype=xp.float64)[:, None]
        cols = xp.arange(1, k + 1, dtype=xp.float64)[None, :]
        Q = xp.cos((rows + 0.5) * cols * (xp.pi / self.n))
        Q, _ = xp.linalg.qr(Q, mode="reduced")
        threshold = max(float(tol), 1e-14)
        t0 = time.perf_counter()
        for _ in range(int(iterations)):
            Q, _ = xp.linalg.qr(apply(Q), mode="reduced")
            AQ = apply(Q)
            T = (Q.T @ AQ + AQ.T @ Q) * 0.5
            values, vectors = xp.linalg.eigh(T)
            order = xp.argsort(values)[::-1]
            mu = values[order]
            U = Q @ vectors[:, order]
            residual = xp.linalg.norm(apply(U) - U * mu[None, :], axis=0).max()
            if float(residual) <= threshold:
                if self.backend == "gpu":
                    xp.cuda.Stream.null.synchronize()
                self.solve_wall_sec += time.perf_counter() - t0
                self.which = "block-power/Rayleigh-Ritz"
                return self._finish_embedding(mu, U, dinv)
            Q = U
        if self.backend == "gpu":
            xp.cuda.Stream.null.synchronize()
        self.solve_wall_sec += time.perf_counter() - t0
        raise RuntimeError(f"block power failed to converge in {iterations} iterations")

    def embedding(self, k: int):
        """sklearn's maps, with bounded cluster-local recovery for non-convergence.

        The successful incumbent call is byte-for-byte the first attempt. Only a
        numerical non-convergence enters the dialled GPU sequence: float64, a
        deterministic diagonal jitter, then block power/Rayleigh-Ritz. Exhaustion
        raises :class:`EigensolverDeclined` for the owning cluster to type.
        """
        if k < 1 or k >= self.n:
            raise ValueError(f"k must satisfy 1 <= k < n; got k={k} for n={self.n}")
        if self.backend != "gpu":
            return self._embedding_eigsh(k)
        from laplace.pipeline import dial_profiles as dials
        tolerance = float(dials.value("engine-fold", "eigensolver_tolerance"))
        jitter = float(dials.value("engine-fold", "eigensolver_jitter"))
        power_iterations = int(dials.value("engine-fold", "eigensolver_power_iterations"))
        attempts: list[dict[str, str]] = []

        def attempt(stage, call):
            try:
                return call()
            except Exception as exc:  # noqa: BLE001 - classified; device faults still propagate
                if not self._nonconvergence(exc):
                    raise
                attempts.append({"stage": stage, "error": f"{type(exc).__name__}: {exc}"})
                return None

        result = attempt("float32-lanczos", lambda: self._embedding_eigsh(k))
        if result is not None:
            return result
        result = attempt("float64-lanczos", lambda: self._embedding_eigsh(
            k, dtype=self.xp.float64, tol=tolerance))
        if result is not None:
            return result
        result = attempt("float64-jittered-lanczos", lambda: self._embedding_eigsh(
            k, dtype=self.xp.float64, jitter=jitter, tol=tolerance))
        if result is not None:
            return result
        result = attempt("float64-block-power", lambda: self._embedding_power(
            k, tol=tolerance, iterations=power_iterations))
        if result is not None:
            return result
        raise EigensolverDeclined(attempts)

    def silhouette(self, labels) -> float:
        """Mean silhouette over the COSINE distance ``d(i,j) = clip(1 − x_i·x_j, 0, 2)`` with a zero
        diagonal — the incumbent's ``silhouette_score(dist, labels, metric="precomputed")``, without
        the n×n ``dist``.

        THE IDENTITY. Every silhouette needs is, per point and per cluster, the MEAN distance from
        the point to that cluster's members. For this distance that mean is a cluster SUM away::

            Σ_{j∈C} d(i,j) = |C| − x_i · (Σ_{j∈C} x_j)

        so one (n_c, d) matrix of cluster sums and one (n, n_c) GEMM give every number exactly, in
        O(n d k) with no n² object anywhere. This is algebra, not approximation: it reproduces
        ``sklearn.metrics.silhouette_score`` to float rounding (gated), which is why it is allowed to
        replace it. It is exact only while the clip is inert — see ``rows_are_unit``."""
        return silhouette_cosine_factored(self.X, labels, self.xp,
                                          row_norm2=self.ff.row_norm2)

    def close(self) -> None:
        """Release owned arrays while preserving the allocator for the next cut.

        A full fold creates one instance per cluster. Clearing CuPy's global pool
        here forced subsequent cuts to allocate device memory again and discarded
        reusable allocations belonging to other algebraic work in this process.
        Dropping our references returns these arrays to the pool; process exit
        releases the CUDA context. No array or solver result survives this close.
        """
        self.X = self.dinv = self.ff = None

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def silhouette_cosine_factored(X, labels, xp, row_norm2=None) -> float:
    """``silhouette_score(clip(1 − X X.T, 0, 2) with zero diagonal, labels, metric="precomputed")``,
    computed through cluster sums (see ``FoldSpectral.silhouette``). ``X`` is ``xp``'s (n, d) array;
    ``labels`` is any array of n integer labels. Returns a python float.

    Degenerate handling matches sklearn exactly: a singleton cluster scores 0 (sklearn reaches the
    same value through a 0/0 and ``np.nan_to_num``), and fewer than two distinct labels is an error
    there and a ``0.0`` here — the caller has already skipped that case."""
    import numpy as np
    lab = np.asarray(labels).ravel()
    uniq, inv = np.unique(lab, return_inverse=True)
    n, nc = len(lab), len(uniq)
    if nc < 2 or n < 2:
        return 0.0
    dt = X.dtype
    H = xp.zeros((n, nc), dtype=dt)
    H[xp.asarray(np.arange(n)), xp.asarray(inv)] = dt.type(1.0)
    sizes = H.sum(axis=0)                                   # (nc,)
    S = H.T @ X                                             # (nc, d) cluster sums
    D = sizes[None, :] - X @ S.T                            # (n, nc) SUM of distances i -> cluster
    if row_norm2 is None:
        row_norm2 = (X * X).sum(axis=1)
    own = xp.asarray(inv)
    rows = xp.asarray(np.arange(n))
    # dist(i, i) is forced to 0 by the incumbent's fill_diagonal; the sum above counted
    # (1 - ||x_i||^2) for it, so it comes back out. Exactly zero for unit rows.
    D[rows, own] = D[rows, own] - (dt.type(1.0) - row_norm2)
    own_size = sizes[own]
    a = D[rows, own] / xp.maximum(own_size - dt.type(1.0), dt.type(1.0))
    means = D / sizes[None, :]
    means[rows, own] = dt.type(np.inf)
    b = means.min(axis=1)
    s = (b - a) / xp.maximum(xp.maximum(a, b), dt.type(1e-300))
    s = xp.where(own_size > dt.type(1.0), s, xp.zeros_like(s))   # sklearn: singleton -> 0
    return float(s.mean())


# ---------------------------------------------------------------------------
# the reference — the dense object this exists to never build, built anyway, to be checked against
# ---------------------------------------------------------------------------

def dense_laplacian_eigenvalues(X, k: int | None = None):
    """The CPU-dense reference: form ``A`` exactly as ``meaning_upfold._best_split`` does, form
    ``L_sym = I - D^{-1/2} A D^{-1/2}``, and take ``numpy.linalg.eigvalsh``. O(n^2) memory and
    O(n^3) time BY DESIGN — this is the incumbent's own arithmetic, kept here only so parity is
    measured against the thing being replaced rather than against another approximation.

    Returns the ascending eigenvalues (all of them, or the bottom ``k``) as float64."""
    import numpy as np
    Xd = np.asarray(X, dtype=np.float64)
    A = (Xd @ Xd.T + 1.0) / 2.0
    np.fill_diagonal(A, 1.0)                      # meaning_upfold.py:414, verbatim
    dinv = 1.0 / np.sqrt(np.clip(A.sum(axis=1), 1e-12, None))
    L = -(A * dinv[:, None]) * dinv[None, :]
    L[np.diag_indices_from(L)] += 1.0             # L_sym = I - D^{-1/2} A D^{-1/2}
    lam = np.linalg.eigvalsh((L + L.T) * 0.5)     # symmetrise: the scaling is symmetric in exact
    return lam if k is None else lam[:k]          # arithmetic, and eigvalsh reads one triangle


def dense_fold_laplacian_eigenvalues(X, k: int | None = None):
    """The CPU-dense reference for the PRODUCTION operator — the one the incumbent actually factors.

    Same construction as above but with the affinity's diagonal ZEROED before the degree is taken,
    which is what ``scipy.sparse.csgraph.laplacian(normed=True)`` does inside sklearn (module
    docstring). This is the reference ``FoldSpectral``'s eigenvalues are gated against, so parity is
    measured against the incumbent's own arithmetic rather than against a nearby operator that would
    make the number look better than it is."""
    import numpy as np
    Xd = np.asarray(X, dtype=np.float64)
    A = (Xd @ Xd.T + 1.0) / 2.0
    np.fill_diagonal(A, 1.0)                      # meaning_upfold.py:414, verbatim
    np.fill_diagonal(A, 0.0)                      # ...then scipy's _laplacian_dense zeroes it
    dinv = 1.0 / np.sqrt(np.clip(A.sum(axis=1), 1e-12, None))
    L = -(A * dinv[:, None]) * dinv[None, :]
    L[np.diag_indices_from(L)] = 1.0              # scipy's _setdiag_dense(m, 1) / sklearn's _set_diag
    lam = np.linalg.eigvalsh((L + L.T) * 0.5)
    return lam if k is None else lam[:k]
