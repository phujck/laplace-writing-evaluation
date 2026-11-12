"""metric_distill.py - distill the coupling wire into the embedding metric (weights-from-concepts).

The conjugate of machine learning, taken literally for the first time: ML trains weights and mines
for concepts; we WROTE the concepts (the edge index, the graded wire - every link locatored) and
now train the geometry to agree with them. The object learned is a bilinear similarity

    s(a, b) = a' M b          (M symmetric, d x d, initialised at the identity)

so the untrained metric IS the special case M = I (raw cosine), and the training is a small,
auditable bend of the space toward the graph: positives are the SYMBOLIC wire (shard edges +
parent-child links - asserted structure only, never conjectural grit), negatives are sampled
unwired pairs, the loss is a margin hinge, and an identity anchor keeps the bend earned
(||M - I||_F penalised - the pretrained space is not destroyed, only corrected).

d=384 means M has ~147k parameters - gradient steps are outer products, no torch. M's eigenspectrum
is READABLE - the first weight matrix this engine has trained, and its spectrum is inspectable the
way F1 wants the coupling matrix's spectrum watched.

THE DEVICE (2026-08-20, his ruling ``PV-20260820T093000Z-gpu-takes-the-spectral-side``: every
algebraic organ of the fold targets the GPU on this box; CPU survives only as the no-hardware
fallback). This was the close's top phase at 45.4 s, and it is 106,470 sequential rank-one updates
of a 384x384 matrix plus, per update, a full anchor pass and a full symmetrisation - ~190 GFLOP of
which two thirds is the two d^2 passes that have nothing to do with the wire. The port moves THE
SAME ARITHMETIC to the device and nothing else. Specifically NOT ported: any batching of the
updates. HOT-1's minibatch hoist was REFUTED by measurement (hinge violation rate 62%, flat across
epochs - there is no sparsity to exploit and the updates are genuinely sequential), so the loop
keeps its exact shape, its exact order, and its exact per-step float32 arithmetic. What changes is
where the arithmetic happens, plus two fusions that are bit-identical rewrites of numpy's own
evaluation order (the anchor and the symmetrisation become one pass; the hinge branch becomes a
0-or-lr multiplier, which adds exact zero where the branch would have skipped).

THE RNG STAYS ON THE HOST, deliberately. ``sample_neg`` and the epoch permutations never read M, so
the CPU and device paths consume the SAME draws in the SAME order and train on a bit-identical
sequence of (anchor, positive, negative) triples. The only divergence between the two paths is
cuBLAS's summation order against OpenBLAS's - which is the divergence the parity gate is sized
against, rather than one that had to be argued away.

The gate keeps it plain: ``main`` saves M ONLY if the held-out AUC beats the identity baseline
AND the navigator's hello check stays 5/5 with M applied. A metric that wins the benchmark but
breaks the standing recall does not ship.
"""

from __future__ import annotations
from laplace.core.checkout import source_tree

import json
from pathlib import Path
from typing import Any

from laplace.representation.embed_router import METRIC_FILE
from laplace.pipeline import dial_profiles as dials



# ---------------------------------------------------------------------------
# the training pairs - the symbolic wire, nothing else
# ---------------------------------------------------------------------------

def wire_pairs(repo_root: Path | str, net: dict[str, Any]) -> list[tuple[str, str]]:
    """The asserted couplings the metric must learn: the merged substrate edge index (the ring's
    own recipe) + every parent-child link in the graded tree. Both endpoints must be embedded
    nodes. Conjectural grit is EXCLUDED - the metric learns what is asserted, and the audit keeps
    surfacing what is merely plausible."""
    from laplace.engine import conceptric
    from laplace.engine.keeper_ring import CONJECTURE_PREFIX
    nodes = net["nodes"]
    pairs: set[tuple[str, str]] = set()
    for a, outs in conceptric._self_edge_index(Path(repo_root)).items():
        if a not in nodes or a.startswith(CONJECTURE_PREFIX):
            continue
        for b in outs:
            if b in nodes and b != a and not str(b).startswith(CONJECTURE_PREFIX):
                pairs.add((a, b) if a < b else (b, a))
    for nid, node in nodes.items():
        p = node.get("parent")
        if p is not None and p in nodes:
            pairs.add((nid, p) if nid < p else (p, nid))
    return sorted(pairs)


# ---------------------------------------------------------------------------
# train - hinge on s(a,p) - s(a,n), gradients are outer products
# ---------------------------------------------------------------------------

DENY_FLAG = "LAPLACE_NO_METRIC_GPU"   # the explicit deny; absent hardware falls back on its own
_KERNELS: dict[str, Any] = {}


def fit_backend(device: str | None = None) -> tuple[str, str]:
    """``("gpu"|"cpu", why)`` for the distillation. GPU is the DEFAULT (his ruling); ``device``
    overrides for a test; ``LAPLACE_NO_METRIC_GPU`` is the explicit deny. The probe is
    ``spectral_gpu.gpu_ready()`` - one real cuBLAS GEMM - because cupy imports cleanly against a
    mismatched CUDA runtime and only fails at the first matmul."""
    import os
    from laplace.representation import device_policy
    if device is not None:
        device_policy.record_fallback("metric-distill", device, "caller override", dialed=True)
        return device, "caller override"
    if str(os.environ.get(DENY_FLAG, "")).strip().lower() in {"1", "true", "yes", "on"}:
        device_policy.record_fallback("metric-distill", "cpu",
                                      f"{DENY_FLAG} is set (the explicit deny)", dialed=True)
        return "cpu", f"{DENY_FLAG} is set (the explicit deny)"
    try:
        from laplace.representation.spectral_gpu import gpu_ready
    except Exception as exc:  # noqa: BLE001
        why = f"spectral_gpu did not import ({type(exc).__name__}: {exc})"
        device_policy.record_fallback("metric-distill", "cpu", why)
        return "cpu", why
    ok, why = gpu_ready()
    if not ok:
        device_policy.record_fallback("metric-distill", "cpu", why)
    return ("gpu", "") if ok else ("cpu", why)


CHUNK = 2000        # steps per launch: long enough to amortise, short enough for any watchdog

_PAIR_STEP_SRC = r"""
// THE INCUMBENT TRAINING LOOP, AS ONE KERNEL - AND THE LOOP ITSELF IS INSIDE IT.
//
// TWO MEASURED FACTS SHAPED THIS, both of them found by building the obvious thing first:
//
//  1. A cupy call per line came out at 0.97x - no faster than numpy. `cupy.dot(v, xp)` on two
//     vectors goes to cuBLAS `sdot` in HOST pointer mode, which synchronises the stream to hand
//     the scalar back: 45.6 us measured, against 8.0 us for a full 384x384 fused pass on the same
//     box. Eight of those per pair and the loop spends its life waiting for scalars. So the scores
//     are block reductions that never leave the device, and the hinge decision is made by thread 0
//     and broadcast through shared memory - the host never reads a value back mid-training.
//
//  2. One launch per pair came out at 363 us/pair, of which 189 us was cupy's own argument
//     marshalling on the HOST - i.e. the launch cost more than the arithmetic. So the STEP LOOP
//     MOVED INSIDE: the host uploads the whole chunk's (anchor, positive, 4 negatives) index table
//     once and issues ONE launch for thousands of sequential steps. The per-step host cost is now
//     zero, and what is left is the arithmetic itself.
//
// WHY ONE BLOCK. The steps are genuinely sequential (HOT-1's minibatch hoist was REFUTED by
// measurement: 62% hinge violation rate, flat across epochs), so every step must see the previous
// step's M. Within one block that ordering costs a `__syncthreads()` (~ns); across blocks it would
// cost a grid-wide cooperative sync (~us) at every one of the thirteen phase boundaries per pair,
// which measured WORSE than the single block it was meant to beat. The block is therefore sized to
// fill one SM exactly (TX*TY = 1536 threads on this device) and the r-dimension of the `xa @ M`
// product is split across TY so no thread idles.
//
// THE ARITHMETIC IS THE INCUMBENT'S, LINE BY LINE:
//   v      = xa @ M                                   (float32)
//   viol   = margin - (double)sp + (double)sn         <- numpy's `float()` widening and its order
//   if viol > 0:  M[r][c] += lr * (xa[r] * (xp[c] - xn[c]))
//   M     -= lr*anchor*(M - I) ;  M = (M + M.T)/2
// The last two lines fold into one in-place pass: the result is symmetric, so the thread owning
// (r,c) with r <= c computes the value once and writes both cells - no scratch copy of M exists.
// Skipping the rank-one update when the hinge is inactive is bit-identical to adding 0.0f, and it
// is the ONLY thing this kernel declines to compute. Nothing is batched, reordered across steps,
// or approximated. Every reduction is a fixed-order tree in a single block, so the result is
// DETERMINISTIC run to run - which the seed comment at the top of this module promises and an
// atomicAdd reduction would have quietly broken.

#define D @D@
#define NNEG @NNEG@
#define TX @TX@
#define TY @TY@
#define NT (TX * TY)
#define RED @RED@
#define STRIDE (2 + NNEG)

__device__ __forceinline__ void load_row(float* dst, const float* __restrict__ X, int r, int tid)
{
    for (int i = tid; i < D; i += NT) dst[i] = X[(size_t)r * D + i];
}

// v = xa @ M, with the r-sum split across ty and recombined in a fixed order.
__device__ __forceinline__ void gemv_xa_M(
        float* sv, float* part, const float* sxa, const float* __restrict__ M,
        int tx, int ty, int tid)
{
    for (int col = tx; col < D; col += TX) {
        float acc = 0.0f;
        for (int r = ty; r < D; r += TY) acc += sxa[r] * M[(size_t)r * D + col];
        part[ty * D + col] = acc;
    }
    __syncthreads();
    for (int col = tid; col < D; col += NT) {
        float t = 0.0f;
        for (int q = 0; q < TY; ++q) t += part[q * D + col];
        sv[col] = t;
    }
    __syncthreads();
}

// M -= lr*anchor*(M - I) followed by M = (M + M.T)/2, in ONE in-place pass.
//
// THE TRANSPOSE IS THE WHOLE COST. Written the obvious way - every thread reads M[r][c] and
// M[c][r] - this single pass measured 153 us/pair, MORE than the four `xa @ M` products and the
// four rank-one updates put together (49 us and 109 us), because the mirror read strides by D and
// every 4-byte access becomes its own 32-byte transaction. Tiled 32x32 through shared memory it is
// ~14 us: both tiles come in coalesced, the mirror is taken in shared (padded to 33 to kill the
// bank conflict), and both write backs go out coalesced. The arithmetic per cell is untouched -
// this is a memory access pattern, not a different formula.
__device__ __forceinline__ void anchor_symmetrise(float* __restrict__ M, float c, int tid)
{
#if (D % 32 == 0) && (NT == 1024)
    __shared__ float A[32][33], B[32][33];
    const int i = tid >> 5, j = tid & 31;
    for (int I = 0; I < D / 32; ++I) {
        for (int J = I; J < D / 32; ++J) {
            const size_t pa = (size_t)(I * 32 + i) * D + (J * 32 + j);
            const size_t pb = (size_t)(J * 32 + i) * D + (I * 32 + j);
            A[i][j] = M[pa];
            B[i][j] = M[pb];
            __syncthreads();
            const float ea = ((I * 32 + i) == (J * 32 + j)) ? 1.0f : 0.0f;
            const float eb = ((J * 32 + i) == (I * 32 + j)) ? 1.0f : 0.0f;
            const float a1 = A[i][j], a2 = B[j][i];
            const float b1 = B[i][j], b2 = A[j][i];
            const float oa = ((a1 - c * (a1 - ea)) + (a2 - c * (a2 - ea))) / 2.0f;
            const float ob = ((b1 - c * (b1 - eb)) + (b2 - c * (b2 - eb))) / 2.0f;
            __syncthreads();
            M[pa] = oa;
            M[pb] = ob;
            __syncthreads();
        }
    }
#else
    for (int idx = tid; idx < D * D; idx += NT) {          // the general fallback shape
        const int r = idx / D, col = idx - r * D;
        if (r <= col) {
            const size_t i2 = (size_t)col * D + r;
            const float e = (r == col) ? 1.0f : 0.0f;
            const float m1 = M[idx], m2 = M[i2];
            const float o = ((m1 - c * (m1 - e)) + (m2 - c * (m2 - e))) / 2.0f;
            M[idx] = o; M[i2] = o;
        }
    }
    __syncthreads();
#endif
}

extern "C" __global__ void metric_train_chunk(
        float* __restrict__ M, const float* __restrict__ X,
        const int* __restrict__ steps, const int nsteps,
        const double margin, const float lr, const float c)
{
    __shared__ float sv[D], sxa[D], sxp[D], sxn[D];
    __shared__ float part[TY * D];
    __shared__ float red[2 * RED];
    __shared__ float scale;

    const int tx = threadIdx.x, ty = threadIdx.y, tid = ty * TX + tx;

    for (int s = 0; s < nsteps; ++s) {
        const int* st = steps + (size_t)s * STRIDE;
        load_row(sxa, X, st[0], tid);
        load_row(sxp, X, st[1], tid);
        __syncthreads();

        for (int j = 0; j < NNEG; ++j) {
            load_row(sxn, X, st[2 + j], tid);
            __syncthreads();
            gemv_xa_M(sv, part, sxa, M, tx, ty, tid);

            if (tid < RED) {
                float pp = 0.0f, pn = 0.0f;
                for (int i = tid; i < D; i += RED) { pp += sv[i] * sxp[i]; pn += sv[i] * sxn[i]; }
                red[tid] = pp; red[RED + tid] = pn;
            }
            __syncthreads();
            for (int q = RED / 2; q > 0; q >>= 1) {
                if (tid < q) { red[tid] += red[tid + q]; red[RED + tid] += red[RED + tid + q]; }
                __syncthreads();
            }
            if (tid == 0) {
                const double viol = margin - (double)red[0] + (double)red[RED];
                scale = (viol > 0.0) ? lr : 0.0f;
            }
            __syncthreads();

            if (scale != 0.0f) {                    // skipping == adding 0.0f, exactly
                for (int idx = tid; idx < D * D; idx += NT) {
                    const int r = idx / D, col = idx - r * D;
                    M[idx] += scale * (sxa[r] * (sxp[col] - sxn[col]));
                }
            }
            __syncthreads();
        }

        anchor_symmetrise(M, c, tid);
    }
}

// The held-out AUC tally: v = xa @ Mat once per held pair, then NNEG comparisons, all on device,
// all in one launch, summed in a fixed order so the tally is deterministic.
extern "C" __global__ void metric_auc_all(
        const float* __restrict__ Mat, const float* __restrict__ X,
        const int* __restrict__ steps, const int nsteps, long long* __restrict__ wins)
{
    __shared__ float sv[D], sxa[D], part[TY * D], red[RED];
    __shared__ float sp_val;
    __shared__ long long tally;

    const int tx = threadIdx.x, ty = threadIdx.y, tid = ty * TX + tx;
    if (tid == 0) tally = 0;
    __syncthreads();

    for (int s = 0; s < nsteps; ++s) {
        const int* st = steps + (size_t)s * STRIDE;
        load_row(sxa, X, st[0], tid);
        __syncthreads();
        gemv_xa_M(sv, part, sxa, Mat, tx, ty, tid);

        for (int j = -1; j < NNEG; ++j) {
            const int other = (j < 0) ? st[1] : st[2 + j];
            if (tid < RED) {
                float acc = 0.0f;
                for (int i = tid; i < D; i += RED) acc += sv[i] * X[(size_t)other * D + i];
                red[tid] = acc;
            }
            __syncthreads();
            for (int q = RED / 2; q > 0; q >>= 1) {
                if (tid < q) red[tid] += red[tid + q];
                __syncthreads();
            }
            if (tid == 0) {
                if (j < 0) sp_val = red[0];
                else if (sp_val > red[0]) tally += 1;
            }
            __syncthreads();
        }
    }
    if (tid == 0) *wins = tally;
}
"""


def _block_shape(d: int) -> tuple[int, int, int]:
    """``(TX, TY, RED)`` for a basis of width ``d``.

    TX threads walk the COLUMNS of M and TY splits the ``xa @ M`` row-sum, so the pair of them
    decides how much of the block actually has work. CUDA caps a block at 1024 threads, so the
    choice maximises the thread count first, then picks the split that leaves the column loop
    BALANCED (``d`` a multiple of TX - at d=384 that is 128x8, where every thread owns exactly
    three columns and forty-eight rows), then prefers the wider TX because TY costs shared memory.
    RED is a power of two at most NT for the fixed-order reduction tree."""
    d = int(d)
    best = None
    for tx in range(32, 1025, 32):
        ty = 1024 // tx
        if ty < 1:
            continue
        nt = tx * ty
        idle = -(-d // tx) * tx - d                       # columns a full sweep would waste
        shared = (4 * d + ty * d + 2 * min(nt, max(32, d)) + 8) * 4
        if shared > 46000:                                # stay under the 48 KB static limit
            continue
        cand = (nt, -idle, tx, ty)
        if best is None or cand > best:
            best = cand
    if best is None:                                      # a d so wide that even TY=1 will not fit
        raise ValueError(f"no viable block shape for d={d} (shared memory)")
    _nt, _idle, tx, ty = best
    red = 1
    while red * 2 <= min(tx * ty, max(32, d)):
        red *= 2
    return tx, ty, red


def _kernels(cupy, d: int, nneg: int):
    """Compile (once per (d, nneg), cached by cupy too) the chunked trainer and the AUC tally."""
    key = (int(d), int(nneg))
    if key not in _KERNELS:
        tx, ty, red = _block_shape(d)
        src = _PAIR_STEP_SRC
        for tok, val in (("D", d), ("NNEG", nneg), ("TX", tx),
                         ("TY", ty), ("RED", red)):
            src = src.replace(f"@{tok}@", str(int(val)))
        mod = cupy.RawModule(code=src, options=("-std=c++11",))
        _KERNELS[key] = (mod.get_function("metric_train_chunk"),
                         mod.get_function("metric_auc_all"), (tx, ty))
    return _KERNELS[key]


def _fit_cpu(X, ids, trainset, held, sample_neg, rng, d, *, epochs, lr, margin, anchor,
             neg_per_pos, initial_M=None):
    """The incumbent loop, VERBATIM - the no-hardware fallback and the parity reference."""
    import numpy as np

    def auc(Mat: Any) -> float:
        wins = trials = 0
        for a, p in held:
            xa = X[a]
            sp = float(xa @ Mat @ X[p])
            for _ in range(neg_per_pos):
                sn = float(xa @ Mat @ X[sample_neg(a)])
                wins += 1 if sp > sn else 0
                trials += 1
        return wins / trials if trials else 0.0

    M = np.eye(d, dtype="float32") if initial_M is None else np.array(initial_M, dtype="float32", copy=True)
    auc_identity = auc(np.eye(d, dtype="float32"))
    eye = np.eye(d, dtype="float32")
    for _ in range(epochs):
        order = rng.permutation(len(trainset))
        for idx in order:
            a, p = trainset[int(idx)]
            xa, xp = X[a], X[p]
            for _ in range(neg_per_pos):
                xn = X[sample_neg(a)]
                viol = margin - float(xa @ M @ xp) + float(xa @ M @ xn)
                if viol > 0:
                    # d/dM [x_a' M (x_p - x_n)] = outer(x_a, x_p - x_n); hinge active only on violation
                    M += lr * np.outer(xa, xp - xn)
            M -= lr * anchor * (M - eye)
            M = (M + M.T) / 2.0                       # keep the similarity symmetric
    return M, auc_identity, auc(M)


def _fit_gpu(X, ids, trainset, held, sample_neg, rng, d, *, epochs, lr, margin, anchor,
             neg_per_pos, initial_M=None):
    """The same loop, same order, same draws, on the device.

    The basis is transferred ONCE as a single (N, d) float32 block and every ``x`` below is a row
    VIEW into it - no per-step host->device traffic at all. Nothing in the loop reads a value back
    to the host: the hinge decision lives on the device as a 0-or-lr multiplier, so the CPU never
    blocks on a result and the kernel stream runs ahead. One synchronisation happens per ``auc``
    tally and one at the end."""
    import cupy
    import numpy as np
    train_chunk, auc_all, block = _kernels(cupy, d, neg_per_pos)
    row = {nm: i for i, nm in enumerate(ids)}
    Xd = cupy.asarray(np.ascontiguousarray(np.stack([X[nm] for nm in ids]), dtype=np.float32))
    m64, lr32, c32 = np.float64(margin), np.float32(lr), np.float32(lr * anchor)
    stride = 2 + neg_per_pos

    def table(seq):
        """The (anchor, positive, negatives...) index table for a whole pass, uploaded ONCE.

        The negatives are drawn in the SAME ORDER the step loop would have drawn them - lawful
        because ``sample_neg`` never reads M, so hoisting the draws leaves the RNG stream, and
        therefore the training sequence, bit-identical to the CPU path's."""
        t = np.empty((len(seq), stride), dtype=np.int32)
        for i, (a, p) in enumerate(seq):
            t[i, 0], t[i, 1] = row[a], row[p]
            for j in range(neg_per_pos):
                t[i, 2 + j] = row[sample_neg(a)]
        return cupy.asarray(t)

    def auc(Mat) -> float:
        wins = cupy.zeros((), dtype=cupy.int64)
        auc_all((1,), block, (Mat, Xd, table(held), np.int32(len(held)), wins))
        trials = len(held) * neg_per_pos
        return int(wins) / trials if trials else 0.0

    M = cupy.eye(d, dtype=cupy.float32) if initial_M is None else cupy.array(initial_M, dtype=cupy.float32)
    auc_identity = auc(cupy.eye(d, dtype=cupy.float32))
    for _ in range(epochs):
        order = rng.permutation(len(trainset))
        steps = table([trainset[int(i)] for i in order])
        # chunked so no single launch runs long enough to meet a display watchdog: the arithmetic
        # is identical however the steps are grouped (M carries across launches on the device).
        for lo in range(0, len(order), CHUNK):
            hi = min(lo + CHUNK, len(order))
            train_chunk((1,), block,
                        (M, Xd, steps[lo:hi], np.int32(hi - lo), m64, lr32, c32))
    auc_trained = auc(M)
    return cupy.asnumpy(M), auc_identity, auc_trained


def _evaluation_auc(M, evaluation, *, device):
    """One immutable set of positive/negative trials and vectors for both scores."""
    import numpy as np
    X, table = evaluation["X"], evaluation["table"]
    if device == "gpu":
        import cupy
        _, kernel, block = _kernels(cupy, X.shape[1], table.shape[1] - 2)
        wins = cupy.zeros((), dtype=cupy.int64)
        kernel((1,), block, (cupy.asarray(M), cupy.asarray(X), cupy.asarray(table),
                            np.int32(len(table)), wins))
        return int(wins) / (len(table) * (table.shape[1] - 2))
    wins = 0
    for a, p, *negatives in table:
        v = X[a] @ M
        wins += sum(float(v @ X[p]) > float(v @ X[n]) for n in negatives)
    return wins / (len(table) * (table.shape[1] - 2))


def train(vecs: dict[str, Any], pairs: list[tuple[str, str]],
          epochs: int | None = None, lr: float | None = None, margin: float | None = None,
          anchor: float | None = None, neg_per_pos: int | None = None,
          holdout: float | None = None, seed: int | None = None,
          device: str | None = None, *, initial_M=None, evaluation=None,
          active_pairs=None, require_gpu=False) -> dict[str, Any]:
    """Fit only supplied positives; warm starts never split or resample the pinned evaluation."""
    import numpy as np
    ds = dials.current("engine-metric")["dials"]
    epochs = ds["epochs"]["value"] if epochs is None else epochs
    lr = ds["lr"]["value"] if lr is None else lr
    margin = ds["margin"]["value"] if margin is None else margin
    anchor = ds["anchor"]["value"] if anchor is None else anchor
    neg_per_pos = ds["neg_per_pos"]["value"] if neg_per_pos is None else neg_per_pos
    holdout = ds["holdout"]["value"] if holdout is None else holdout
    seed = ds["seed"]["value"] if seed is None else seed
    backend, why = fit_backend(device)
    if require_gpu and backend != "gpu":
        raise ValueError(f"CURE-B-GPU-001: GPU required: {why}")
    rng = np.random.default_rng(seed)
    ids = sorted(vecs)
    X = {i: np.asarray(vecs[i], dtype="float32") for i in ids}
    usable = sorted({tuple(sorted((a, b))) for a, b in pairs if a in X and b in X and a != b})
    positives = {tuple(sorted(pair)) for pair in (active_pairs if active_pairs is not None else usable)}
    d = X[ids[0]].shape[0]
    if initial_M is not None and (initial_M.shape != (d, d) or not np.isfinite(initial_M).all()):
        raise ValueError("CURE-B-BASIS-001: warm metric dimension or values invalid")

    def sample_neg(a):
        for _ in range(ds["sample_neg"]["value"]):
            n = ids[int(rng.integers(len(ids)))]
            if n != a and tuple(sorted((a, n))) not in positives:
                return n
        # Never silently relabel a wired pair as a negative.
        candidates = [n for n in ids if n != a and tuple(sorted((a, n))) not in positives]
        if not candidates:
            raise ValueError(f"CURE-B-NEGATIVE-001: no unwired negative for {a}")
        return candidates[int(rng.integers(len(candidates)))]

    if evaluation is None:
        if len(usable) < 10:
            raise ValueError(f"too little wire to learn from ({len(usable)} usable pairs)")
        perm = rng.permutation(len(usable))
        n_held = max(1, int(len(usable) * holdout))
        held = [usable[i] for i in perm[:n_held]]
        trials = [[a, p] + [sample_neg(a) for _ in range(neg_per_pos)] for a, p in held]
        eval_ids = sorted({n for trial in trials for n in trial})
        rows = {n: i for i, n in enumerate(eval_ids)}
        evaluation = {"ids": eval_ids, "pairs": [list(p) for p in held],
                      "X": np.stack([X[n] for n in eval_ids]),
                      "table": np.asarray([[rows[n] for n in trial] for trial in trials], dtype="int32")}
    held_set = {tuple(p) for p in evaluation["pairs"]}
    trainset = [p for p in usable if p not in held_set]
    kw = dict(epochs=epochs, lr=lr, margin=margin, anchor=anchor,
              neg_per_pos=neg_per_pos, initial_M=initial_M)
    fitter = _fit_gpu if backend == "gpu" else _fit_cpu
    # Device failures propagate: a live deposit must never restart on the CPU.
    M, _, _ = fitter(X, ids, trainset, [], sample_neg, rng, d, **kw)
    eye = np.eye(d, dtype="float32")
    auc_identity = _evaluation_auc(eye, evaluation, device=backend)
    auc_trained = _evaluation_auc(M, evaluation, device=backend)
    evals = np.linalg.eigvalsh(M)
    return {"M": M, "evaluation": evaluation,
            "auc_identity": round(auc_identity, 6), "auc_trained": round(auc_trained, 6),
            "n_train": len(trainset), "n_held": len(evaluation["pairs"]), "device": backend,
            "spectrum": {"top": [round(float(v), 4) for v in evals[-8:][::-1]],
                         "bottom": [round(float(v), 4) for v in evals[:4]]},
            "drift": round(float(np.linalg.norm(M - eye)), 4)}


# ---------------------------------------------------------------------------
# entry - train, gate, ship-or-refuse
# ---------------------------------------------------------------------------

def hello_gate(repo_root: Path | str, net: dict[str, Any], metric=None) -> dict[str, Any]:
    """Verify standing reconstruction, including one bounded descent from its handle.

    A graded result may return the standing handle instead of each underlying file.
    Count that route only when the router actually returned it and its source files
    are present and hashable. Never insert a handle that retrieval did not reach.
    """
    import hashlib
    from laplace.engine import conceptric
    root = Path(repo_root).resolve()
    standing = net["nodes"].get(conceptric.STANDING, {})
    sources = list(standing.get("members", []))
    out = conceptric.fire_by_grade(root, net, "standing session aim next goals handoff",
                                   metric_override=metric)
    ids = {h["recovered"] for h in out["hits"]}
    ids |= {e["id"] for v in out["per_grade"].values() for e in v}
    expanded = set()
    if conceptric.STANDING in ids:
        expanded = {entry["id"] for entry in conceptric.expand(root, net, conceptric.STANDING)["members"]}
    verified = {}
    for source in sources:
        if source not in ids and source not in expanded:
            continue
        path = (root / source).resolve()
        if path.is_relative_to(root) and path.is_file() and path.stat().st_size:
            verified[source] = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    return {"found": len(verified), "total": len(sources),
            "pass": bool(sources) and len(verified) == len(sources), "router": out.get("router"),
            "direct_found": len(set(sources) & ids),
            "expanded_via": conceptric.STANDING if expanded else None,
            "source_hashes": verified, "missing": [source for source in sources if source not in verified]}


def _pairs_path(repo_root):
    """The metric's PAIR SETS live beside the receipt, never inside it.

    Measured 2026-09-15: embedding active_pairs, evaluation_ids and evaluation_pairs in the receipt
    made .metric_M.receipt.json 101.5 MB and - because the verdict carries changed_ids and the
    deposit copies the verdict into its timing record - .reembed_timing.jsonl 97.3 MB, one 50 MB row
    per deposit. GitHub refused the push, which is the only reason it was caught. The receipt now
    carries HANDLES and COUNTS; the sets live here, gitignored and local. Losing this file costs one
    `scripts/reembed.py --full-metric` re-baseline, never correctness.
    """
    return Path(repo_root) / ".metric_pairs.json"


def _bank_pairs(repo_root, sets: dict) -> dict:
    path = _pairs_path(repo_root)
    body = json.dumps(sets, sort_keys=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(body, encoding="utf-8")
    tmp.replace(path)
    return {f"{k}_count": len(v) for k, v in sets.items()} | {"pairs_handle": _digest(body.encode())}


def _read_pairs(repo_root) -> dict:
    path = _pairs_path(repo_root)
    if not path.is_file():
        return {}
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
        return result if isinstance(result, dict) else {}
    except ValueError:
        return {}


def _receipt_path(repo_root):
    return (Path(repo_root) / METRIC_FILE).with_suffix(".receipt.json")


def _digest(data):
    import hashlib
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _preserve_generation(repo_root, snapshots):
    """Keep the exact pre-recovery bytes once, without mistaking them for a usable baseline."""
    signature = _digest(json.dumps({name: _digest(value[0]) for name, value in snapshots.items()},
                                  sort_keys=True).encode()).split(":", 1)[1]
    directory = Path(repo_root) / ".metric_recovery" / signature
    directory.mkdir(parents=True, exist_ok=True)
    for name, (body, stat) in snapshots.items():
        target = directory / name
        if target.exists():
            if target.read_bytes() != body:
                raise ValueError("metric recovery evidence differs at " + str(target))
        else:
            target.write_bytes(body)
            import os
            os.chmod(target, stat.st_mode & 0o777)
            os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    return str(directory.relative_to(repo_root))


def record_embedding_changes(repo_root, changed_ids):
    """Producer accounting survives a declined fit and deposits that never reach the fitter.

    Record before the embedding cache is written: a crash may over-report work but cannot
    acknowledge embeddings without retaining their metric obligation. Repeated ids carry a
    generation counter so a concurrent embedding cannot be erased by an older fit's receipt.
    """
    import fcntl
    import os
    path = _receipt_path(repo_root)
    with os.fdopen(os.open(path, os.O_RDWR | os.O_CREAT, 0o600), "r+", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        handle.seek(0)
        raw = handle.read()
        state = json.loads(raw) if raw else {"schema_version": "laplace.metric-receipt/1", "banked": None, "pending": {}, "history": []}
        pending = state["pending"]
        for nid in changed_ids:
            pending[nid] = pending.get(nid, 0) + 1
        handle.seek(0)
        handle.write(json.dumps(state, sort_keys=True))
        handle.truncate()
        handle.flush()
        return state


def pair_delta(current, previous, changed_ids, replay_fraction, seed):
    """Retirement removes a positive from both the changed training set and replay."""
    import math
    import numpy as np
    current, previous = set(map(tuple, current)), set(map(tuple, previous))
    changed_ids = set(changed_ids)
    retired = previous - current
    changed = (current - previous) | {p for p in current if changed_ids.intersection(p)}
    old = sorted((current & previous) - changed)
    n = min(len(old), math.ceil(len(old) * replay_fraction)) if changed or retired else 0
    rng = np.random.default_rng(seed)
    replay = [old[int(i)] for i in rng.choice(len(old), size=n, replace=False)] if n else []
    return sorted(changed), sorted(replay), sorted(retired)


def distill(repo_root: Path | str, net: dict[str, Any], vectors: dict[str, Any], *,
            changed_ids=None, full_metric=False, render_artifacts=None) -> dict[str, Any]:
    """Bank a gated metric generation; absent lineage requires the explicit full door."""
    import fcntl
    import os
    import time
    import numpy as np
    started = time.perf_counter()
    repo_root = Path(repo_root)
    metric_path = repo_root / METRIC_FILE
    generation_paths = (metric_path, _receipt_path(repo_root), _pairs_path(repo_root))
    original = ({path.name: (path.read_bytes(), path.stat())
                 for path in generation_paths if path.is_file()} if full_metric else {})
    state = record_embedding_changes(repo_root, changed_ids or [])
    pending = dict(state["pending"])
    banked = state["banked"]
    prior_bytes = (original[metric_path.name][0] if metric_path.name in original else
                   metric_path.read_bytes() if metric_path.is_file() else None)
    prior_stat = metric_path.stat() if prior_bytes is not None else None
    parent = _digest(prior_bytes) if banked and prior_bytes else "GENESIS"
    if banked and not full_metric and parent != banked["metric_hash"]:
        return {"shipped": False, "status": "CURE-B-LINEAGE-001",
                "why": "metric bytes differ from banked parent receipt"}
    if not banked and not full_metric:
        return {"shipped": False, "status": "CURE-B-BASELINE-001",
                "why": "explicit --full-metric initialization required"}
    if not full_metric and changed_ids is None:
        return {"shipped": False, "status": "CURE-B-INPUT-001",
                "why": "increment requires the producer changed_ids accounting, including an explicit empty list"}
    def store_stamp():
        from laplace.representation.embed_router import _file_digest
        return {name: _file_digest(repo_root / name)
                for name in (".self_embeddings.json", ".self_graded.json", ".meaning_tree.json")
                if (repo_root / name).is_file()}
    before = store_stamp()
    pairs = wire_pairs(repo_root, net)
    pairs = sorted({tuple(p) for p in pairs if all(n in vectors for n in p)})
    ds = dials.current("engine-metric")
    evaluation = initial = None
    prior_pairs = (original[_pairs_path(repo_root).name][0] if _pairs_path(repo_root).name in original else
                   _pairs_path(repo_root).read_bytes() if _pairs_path(repo_root).is_file() else None)
    _sets = _read_pairs(repo_root) if not full_metric else {}
    previous = _sets.get("active_pairs", []) if banked else []
    if banked and not full_metric:
        if prior_pairs is None or _digest(prior_pairs) != banked.get("pairs_handle"):
            return {"shipped": False, "status": "CURE-B-PAIRS-001",
                    "why": "pair sidecar differs from the banked generation; explicit --full-metric recovery required"}
        with np.load(metric_path, allow_pickle=False) as artifact:
            initial = artifact["M"]
            evaluation = {"X": artifact["evaluation_X"], "table": artifact["evaluation_table"],
                          "ids": _sets.get("evaluation_ids", []), "pairs": _sets.get("evaluation_pairs", [])}
        pin = _digest(evaluation["X"].tobytes() + evaluation["table"].tobytes() +
                      json.dumps(evaluation["ids"]).encode())
        if pin != banked["evaluation_hash"]:
            return {"shipped": False, "status": "CURE-B-EVALUATION-001", "why": "evaluation pin mismatch"}
    if full_metric:
        # A full baseline derives a NEW evaluation from current vectors and wire. It must not
        # need the missing/corrupt old evaluation it is explicitly being asked to recover.
        previous = []
    held = set(map(tuple, evaluation["pairs"])) if evaluation else set()
    changed, replay, retired = pair_delta(set(pairs) - held, set(map(tuple, previous)) - held,
                                         pending, ds["dials"]["replay_fraction"]["value"],
                                         ds["dials"]["seed"]["value"])
    retired = sorted(set(map(tuple, previous)) - set(pairs))
    selected = pairs if full_metric else changed + replay
    # The metric receipt is written before staged renders replace their predecessors.
    # Compare the actual published basis against those final render hashes, not the
    # pre-publication .self_graded hash in store_after.
    banked_stores = dict((banked or {}).get("store_after", {}))
    banked_stores.update({name: digest for name, digest in
                         (banked or {}).get("render_artifacts", {}).items()
                         if name in banked_stores})
    inherited_fields = ("auc_identity", "auc_trained", "n_held", "spectrum", "drift")
    reuse_fit = (
        not full_metric and bool(banked and banked.get("shipped") is True)
        and not pending and not changed and not replay and not retired
        and set(pairs) == set(map(tuple, previous))
        and set(before) == {".self_embeddings.json", ".self_graded.json", ".meaning_tree.json"}
        and before == banked_stores
        and ds["dial_set_id"] == banked.get("dial_set_id")
        and all(key in banked for key in inherited_fields)
        and bool(vectors) and initial is not None
        and initial.shape == (len(next(iter(vectors.values()))),) * 2
        and bool(np.isfinite(initial).all())
    )
    if reuse_fit:
        # Metric bytes, evaluation pin, pairs, basis and dials were verified above.
        # No training step exists, so M and its pinned scores/spectrum are unchanged.
        # Recall below still exercises this exact candidate against the current network.
        M = initial
        rep = {key: banked[key] for key in inherited_fields}
        rep.update(n_train=0, device="not-run", fit_reused=True,
                   reused_from_metric=parent,
                   reused_fit_device=banked.get("reused_fit_device", banked.get("device")))
    else:
        rep = train(vectors, selected, initial_M=None if full_metric else initial,
                    evaluation=evaluation, active_pairs=pairs, require_gpu=True)
        evaluation = rep.pop("evaluation")
        M = rep.pop("M")
        rep["fit_reused"] = False
    after = store_stamp()
    baseline = rep["auc_trained"] if full_metric else banked["baseline_auc_trained"]
    verdict = {"schema_version": "laplace.metric-generation/1", **rep,
               "store_before": before, "store_after": after,
               "render_artifacts": (dict(render_artifacts) if render_artifacts is not None else
                                    {k: v for k, v in after.items() if k == ".self_graded.json"}),
               "mode": "full" if full_metric else "incremental", "parent": parent,
               "pairs_changed": rep["n_train"] if full_metric else len(changed) + len(retired),
               "pairs_replayed": 0 if full_metric else len(replay), "pairs_retired": len(retired),
               "n_pairs": len(pairs), "changed_count": len(pending),
               "changed_ids_handle": _digest(json.dumps(sorted(pending)).encode()),
               "dial_set_id": ds["dial_set_id"], "baseline_auc_trained": baseline,
               "evaluation_hash": _digest(evaluation["X"].tobytes() + evaluation["table"].tobytes() +
                                          json.dumps(evaluation["ids"]).encode()),
               "shipped": False}
    if before != after:
        verdict.update(status="CURE-B-STORE-001", why="live fold changed during metric fit")
    elif rep["auc_trained"] <= rep["auc_identity"]:
        verdict.update(status="CURE-B-AUC-001", why="trained AUC does not beat identity")
    elif abs(rep["auc_trained"] - baseline) > 0.01:
        verdict.update(status="CURE-B-AUC-002", why="trained AUC differs from pinned full baseline by more than 0.01")
    else:
        # Exercise the candidate in memory. Readers never see a metric which has not passed
        # recall, and this check cannot accidentally load the old on-disk metric.
        try:
            gate = hello_gate(repo_root, net, M)
            verdict["hello_gate"] = gate
            if not (gate.get("pass") and gate.get("total", 0) > 0
                    and gate.get("found") == gate.get("total")):
                raise ValueError("standing recall did not recover every standing member")
        except Exception as exc:
            verdict.update(status="CURE-B-HELLO-001", why=str(exc),
                           restored_prior_artifact=prior_bytes is not None)
            verdict["seconds"] = round(time.perf_counter() - started, 6)
            return verdict
        # Serialize publication with producer accounting; fail closed if the basis moved during fit.
        with _receipt_path(repo_root).open("r+", encoding="utf-8") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            latest = json.load(handle)
            if (latest != state or store_stamp() != before
                    or dials.current("engine-metric")["dial_set_id"] != ds["dial_set_id"]
                    or (metric_path.read_bytes() if metric_path.exists() else None) != prior_bytes
                    or (_pairs_path(repo_root).read_bytes() if _pairs_path(repo_root).exists() else None) != prior_pairs):
                verdict.update(status="CURE-B-CONCURRENT-001", why="metric or embedding accounting changed during fit")
            else:
                try:
                    if full_metric and original:
                        verdict["prior_generation_preserved_at"] = _preserve_generation(repo_root, original)
                    if not reuse_fit:
                        np.savez(metric_path, M=M, evaluation_X=evaluation["X"],
                                 evaluation_table=evaluation["table"])
                    verdict.update(shipped=True, metric_hash=_digest(metric_path.read_bytes()),
                                   seconds=round(time.perf_counter() - started, 6))
                    if reuse_fit:
                        counts = {f"{key}_count": len(_sets[key]) for key in
                                  ("active_pairs", "retired_pairs", "evaluation_ids", "evaluation_pairs")}
                        counts["pairs_handle"] = banked["pairs_handle"]
                    else:
                        counts = _bank_pairs(repo_root, {"active_pairs": pairs, "retired_pairs": retired,
                                                         "evaluation_ids": evaluation["ids"],
                                                         "evaluation_pairs": evaluation["pairs"]})
                    receipt = {**verdict, **counts}
                    # HISTORY IS BOUNDED: the last 50 verdicts. A receipt that grows without limit is
                    # the same defect as a fold rewritten whole (2026-09-15).
                    state = {"schema_version": "laplace.metric-receipt/2", "banked": receipt, "pending": {},
                             "history": [*latest.get("history", []), verdict][-50:]}
                    handle.seek(0)
                    handle.write(json.dumps(state, sort_keys=True))
                    handle.truncate()
                    handle.flush()
                except Exception as exc:
                    if prior_bytes is not None:
                        metric_path.write_bytes(prior_bytes)
                        os.utime(metric_path, ns=(prior_stat.st_atime_ns, prior_stat.st_mtime_ns))
                    else:
                        metric_path.unlink(missing_ok=True)
                    if prior_pairs is None:
                        _pairs_path(repo_root).unlink(missing_ok=True)
                    else:
                        _pairs_path(repo_root).write_bytes(prior_pairs)
                    handle.seek(0)
                    handle.write(json.dumps(latest, sort_keys=True))
                    handle.truncate()
                    handle.flush()
                    verdict.update(shipped=False, status="CURE-B-PUBLISH-001", why=str(exc),
                                   restored_prior_artifact=prior_bytes is not None)
    verdict["seconds"] = round(time.perf_counter() - started, 6)
    return verdict


def main(argv: list[str]) -> int:
    """The CLI wrapper: acquire the network and the full-fold basis, then :func:`distill` them.
    The fold is ``bulk=True`` - training needs every vector, and the producer posture ignores the
    serving budget."""
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    import argparse
    parser = argparse.ArgumentParser(description="Incremental metric; --full-metric initializes or explicitly refits.")
    parser.add_argument("--repo", type=Path, default=source_tree(),
                        help="repository owning the network, metric, receipt and pair sidecar")
    parser.add_argument("--full-metric", action="store_true")
    args = parser.parse_args(argv)
    from laplace.engine import conceptric
    from laplace.representation import embed_router
    repo_root = args.repo.resolve()
    backend = embed_router.get_backend()
    if backend is None:
        print(json.dumps({"error": "no embedding backend"}))
        return 1
    net = conceptric.load_network(repo_root)
    emb = embed_router.ensure_embeddings(repo_root, net, backend, bulk=True)
    verdict = distill(repo_root, net, emb["vectors"], changed_ids=emb.get("changed_ids", []),
                      full_metric=args.full_metric)
    print(json.dumps(verdict, ensure_ascii=False, indent=2))
    return 0 if verdict.get("shipped") else 1


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
