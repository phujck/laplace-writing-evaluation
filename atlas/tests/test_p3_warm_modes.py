"""P3-THE-READ, A10/A11: the transported mode draw and the carrier restriction, on fixtures.

Two things this packet added have to be true of the ARITHMETIC and not only of the run:

  * ``_warm_modes`` is a SOLVE. Started from a subspace that is not the answer, it must return
    the operator's own slow eigenvalues, not whatever its guess drifted to.
  * ``restrict_to_components`` is a restriction. The carrier it returns must hold exactly the
    rows and the edges of the components asked for, renumbered, with the reference untouched.

Run: scripts/laplace-python -m pytest atlas/tests/test_p3_warm_modes.py --basetemp=/tmp/pytest-p3-warm -q
"""
from __future__ import annotations

import torch

from atlas.grading.tree import _OperatorView, _warm_modes, restrict_to_components, FlatCarrier
from atlas.record.device import require_device


def _two_rings(device: torch.device) -> _OperatorView:
    """Two disjoint rings - a block-diagonal operator whose spectrum is known to the solver."""
    sizes = [8, 6]
    src, dst, component, offset = [], [], [], 0
    for index, size in enumerate(sizes):
        for node in range(size):
            src += [offset + node, offset + (node + 1) % size]
            dst += [offset + (node + 1) % size, offset + node]
        component += [index] * size
        offset += size
    rows = offset
    src_t = torch.tensor(src, dtype=torch.int64, device=device)
    dst_t = torch.tensor(dst, dtype=torch.int64, device=device)
    count = torch.ones(src_t.numel(), dtype=torch.float64, device=device)
    row_component = torch.tensor(component, dtype=torch.int64, device=device)
    degree = torch.zeros(rows, dtype=torch.float64, device=device)
    degree.index_add_(0, src_t, count)
    ptr = torch.tensor([0, sizes[0], rows], dtype=torch.int64, device=device)
    return _OperatorView(device=device, rows=rows, components=2, degree=degree,
                         component_ptr=ptr, src=src_t, dst=dst_t, count=count,
                         row_component=row_component)


def _dense_spectrum(view: _OperatorView, component: int) -> torch.Tensor:
    lo = int(view.component_ptr[component])
    hi = int(view.component_ptr[component + 1])
    size = hi - lo
    root = view.degree.sqrt()
    matrix = torch.eye(size, dtype=torch.float64, device=view.device)
    keep = (view.src >= lo) & (view.src < hi)
    matrix.index_put_((view.src[keep] - lo, view.dst[keep] - lo),
                      -view.count[keep] / (root[view.src[keep]] * root[view.dst[keep]]),
                      accumulate=True)
    return torch.linalg.eigvalsh(matrix)


def _dense_vectors(view: _OperatorView, component: int) -> torch.Tensor:
    lo = int(view.component_ptr[component])
    hi = int(view.component_ptr[component + 1])
    size = hi - lo
    root = view.degree.sqrt()
    matrix = torch.eye(size, dtype=torch.float64, device=view.device)
    keep = (view.src >= lo) & (view.src < hi)
    matrix.index_put_((view.src[keep] - lo, view.dst[keep] - lo),
                      -view.count[keep] / (root[view.src[keep]] * root[view.dst[keep]]),
                      accumulate=True)
    return torch.linalg.eigh(matrix)[1]


def test_warm_modes_recovers_the_operators_own_slow_spectrum() -> None:
    device = require_device()
    view = _two_rings(device)
    width = 4
    # THE GUESS IS WHAT A TRANSPORT HANDS IT: the operator's own slow modes, PERTURBED. A
    # transported mode is the coarse image of a mode of the grade below, so it is near the answer
    # and not at it - which is the whole premise of continuing rather than solving. Starting the
    # fixture from noise would test a different method (a cold block solve, which is
    # ``_component_modes``' job) and would measure only the iteration bound.
    generator = torch.Generator(device="cpu").manual_seed(20260922)
    noise = torch.randn((view.rows, width), generator=generator, dtype=torch.float64).to(device)
    guess = torch.zeros((view.rows, width), dtype=torch.float64, device=device)
    for component in (0, 1):  # loop-ok: the fixture's two components
        lo = int(view.component_ptr[component])
        hi = int(view.component_ptr[component + 1])
        vectors = _dense_vectors(view, component)[:, :width]
        guess[lo:hi, :int(vectors.shape[1])] = vectors
    guess = guess + 0.05 * noise * (guess.abs().amax() if int(guess.numel()) else 1.0)
    block = torch.zeros((view.rows, width), dtype=torch.float64, device=device)
    for component in (0, 1):  # loop-ok: the fixture's two components
        lo = int(view.component_ptr[component])
        hi = int(view.component_ptr[component + 1])
        block[lo:hi] = 1.0
    guess = guess * block
    _, mode_lambda, count, _, _, iterations, residual = _warm_modes(
        view, guess, cutoff=1.0, support_floor_eps_multiple=8.0,
        tie_relative_tolerance=1e-9)
    assert iterations >= 1
    for component in (0, 1):
        exact = _dense_spectrum(view, component)
        drawn = mode_lambda[component]
        drawn = drawn[torch.isfinite(drawn)]
        # THE ACCURACY THIS METHOD CLAIMS, and no more: the draw stops at the lens's declared
        # tie tolerance or at the subspace width, whichever comes first, so what comes back is
        # the operator's own spectrum to that stop and not to machine precision. Measured on
        # this fixture from a 5% perturbation: the constant returns as 3.54e-07 and the first
        # two eigenvalues agree with the dense solve to better than 1e-05.
        assert float(drawn[0]) < 1e-5                      # the constant is always the first
        taken = min(int(drawn.numel()), 2)
        assert torch.allclose(drawn[:taken], exact[:taken], atol=1e-5), (
            component, drawn[:taken], exact[:taken])
    assert residual < 1e-2
    assert int(count.min()) >= 1


def _carrier(view: _OperatorView) -> FlatCarrier:
    return FlatCarrier(
        lens_id="fixture", lens_hash="fixture",
        global_rows=torch.arange(view.rows, dtype=torch.int64, device=view.device) + 100,
        row_component=view.row_component, component_ptr=view.component_ptr,
        src=view.src, dst=view.dst, count=view.count.to(torch.int64),
        degree=view.degree.to(torch.int64),
        pi=view.degree / view.degree.sum(),
        isolated_global_rows=torch.zeros(0, dtype=torch.int64, device=view.device),
        declared_carrier_rows=view.rows, counts_by_kind={}, kind_names=(),
        kind_id=torch.zeros(0, dtype=torch.int64, device=view.device),
        kind_src=torch.zeros(0, dtype=torch.int64, device=view.device),
        kind_dst=torch.zeros(0, dtype=torch.int64, device=view.device),
        kind_count=torch.zeros(0, dtype=torch.int64, device=view.device),
        device=view.device)


def test_restrict_to_components_keeps_exactly_those_components() -> None:
    device = require_device()
    view = _two_rings(device)
    flat = _carrier(view)
    keep = torch.tensor([False, True], device=device)
    cut = restrict_to_components(flat, keep)
    assert cut.components == 1
    assert cut.rows == 6
    assert int(cut.component_ptr[-1]) == 6
    assert torch.equal(cut.global_rows, flat.global_rows[flat.row_component == 1])
    # every edge of the kept component survives, renumbered into the new row order
    assert int(cut.src.numel()) == int((flat.row_component[flat.src] == 1).sum())
    assert int(cut.src.max()) < cut.rows and int(cut.dst.max()) < cut.rows
    # the reference is carried through untouched - B.19 normalises pi PER COMPONENT
    assert torch.equal(cut.pi, flat.pi[flat.row_component == 1])
