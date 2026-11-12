"""Finite CUDA calculations backing the physical explanatory figures.

Controlled examples of the exact identities, separate from retrieval benchmarks.
"""
from hashlib import sha256
import json
from pathlib import Path
import sys
import torch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "numerics"))
import common


def compute():
    device, dtype = "cuda", torch.float64
    def tensor(value):
        return torch.tensor(value, device=device, dtype=dtype)
    def exp_symmetric(matrix, times):
        values, vectors = torch.linalg.eigh(matrix)
        return (vectors[None] * torch.exp(times[:, None, None]*values[None, None, :])) @ vectors.T
    root2 = 2.**.5
    U0 = tensor([[1, 0], [1, 0], [0, 1], [0, 1]])/root2
    contrast = tensor([1, -1, 0, 0])/root2
    U3 = torch.cat((U0, contrast[:, None]), 1)
    I = torch.eye(4, device=device, dtype=dtype)
    L = torch.zeros((4, 4), device=device, dtype=dtype)
    for i, rate in enumerate((1., .3, 2.)):
        L[i, i+1] = L[i+1, i] = rate
        L[i, i] -= rate; L[i+1, i+1] -= rate
    times = torch.linspace(0, 10, 401, device=device, dtype=dtype)
    evolution = exp_symmetric(L, times)
    rows = []
    for U in (U0, U3, I):
        A = U.T @ L @ U
        Q = I - U @ U.T
        D = U.T @ L @ Q
        exact = U.T @ evolution @ U
        approximate = exp_symmetric(A, times)
        errors = torch.linalg.matrix_norm(exact-approximate, ord=2)
        dnorm = torch.linalg.matrix_norm(D, ord=2)
        bounds = times * dnorm
        K = D @ exp_symmetric(Q @ L @ Q, times) @ D.T
        # Resolved propagator satisfies the exact eliminated-memory equation.
        derivative = U.T @ (L @ evolution) @ U
        h = float(times[1].cpu())
        convolution = torch.zeros_like(exact)
        for j in range(1, len(times)):
            terms = K[:j+1].flip(0) @ exact[:j+1]
            convolution[j] = h * (terms.sum(0) - .5*(terms[0]+terms[-1]))
        volterra_defect = torch.linalg.matrix_norm(derivative-A @ exact-convolution, ord=2)
        if bool((errors > bounds + 1e-12).any().cpu()):
            raise AssertionError("Duhamel bound failed")
        rows.append({"retained_rank": U.shape[1], "defect_norm": float(dnorm.cpu()),
                     "error": errors.cpu().tolist(), "bound": bounds.cpu().tolist(),
                     "memory_kernel_norm": torch.linalg.matrix_norm(K, ord=2).cpu().tolist(),
                     "volterra_trapezoid_max_defect": float(volterra_defect.max().cpu())})
    f = tensor([0., 1., 0., 1.])
    a = f/2  # sqrt(pi)*f, pi=1/4
    mass_only_loss = torch.linalg.vector_norm((I-U0 @ U0.T) @ a)
    full_loss = torch.linalg.vector_norm((I-I @ I.T) @ a)
    # An orthogonal family of local demand sections: total rank64, local rank4.
    # This is an observable-demand spectrum, not an MPS Schmidt spectrum.
    sectors, local_rank = 16, 4
    local_values = tensor([.5, .25, .15, .10])
    global_values = (torch.ones(sectors, device=device, dtype=dtype)[:, None]*local_values/sectors).flatten()
    global_values = global_values.sort(descending=True).values
    conditioned = torch.cat((local_values, torch.zeros(60, device=device, dtype=dtype)))
    return {
        "schema": "finite-physics-illustrations-v1", "scope": "controlled exact-identity illustrations, not corpus performance",
        "device": torch.cuda.get_device_name(), "dtype": "float64",
        "code_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "generator": L.cpu().tolist(), "reference": [.25]*4,
        "rate_unit": "arbitrary common inverse-time unit", "times": times.cpu().tolist(),
        "reduced_dynamics": rows,
        "register_counterexample": {"observable": f.cpu().tolist(),
            "lost_register_weighted_rms": float(mass_only_loss.cpu()), "transported_register_loss": float(full_loss.cpu())},
        "section_spectrum": {"sectors": sectors, "local_rank": local_rank,
            "global_eigenvalues": global_values.cpu().tolist(), "conditioned_eigenvalues": conditioned.cpu().tolist(),
            "global_trace": float(global_values.sum().cpu()), "conditioned_trace": float(conditioned.sum().cpu()),
            "interpretation": "direct sum of local observable-demand sections; conditioning changes the demand measure"},
    }


if __name__ == "__main__":
    target = HERE / "results/physics_illustrations_v1.json"
    if target.exists():
        raise RuntimeError("preserve existing illustrated calculation")
    with common.gpu_lock("finite physical illustrations"):
        result = compute()
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    print(json.dumps({"path": str(target), "sha256": sha256(target.read_bytes()).hexdigest(),
                      "register": result["register_counterexample"],
                      "max_quadrature_defect": max(x["volterra_trapezoid_max_defect"] for x in result["reduced_dynamics"])}))
