"""blocks.py - proposal by slow modes, acceptance by the two residual tests, and nothing else.

The division this module exists to keep:

  PROPOSAL is spectral and PROVISIONAL. The slow modes of THIS lens's whitened generator
  (Ltilde = I - D^{-1/2} A D^{-1/2}, built from integer located counts alone) cut the carrier by
  their SIGN PATTERN. Nothing about a proposal is an acceptance; a mode never accepts anything;
  no count of blocks, no depth and no resolution parameter is chosen anywhere in this file.

  ACCEPTANCE is two separate refusals, and only they decide:
    TEST 1 (A.11) observable adequacy, COMPONENTWISE over every declared task column and every
           value of its declared vocabulary: ||e_a|| = ||(I - P) atilde_a|| <= tau_a,
           tau_a = eps_a / sqrt(chi2_max), chi2_max = 1/b_min - 1, with b_min the smallest
           reference mass of a conditioning event the lens's declared grammar admits - MEASURED
           from the record, never stipulated.
    TEST 2 (A.13) dynamical closure: ||D_b||_2 <= tau_D with D = U^T Ltilde (I - P) and
           tau_D = min_a eps_a / (||atilde_a|| t* sqrt(chi2_max)), t* the declared walk horizon.
  A refused block is refused WITH the test, the column and the margin. DEPTH IS WHERE THE TESTS
  REFUSE: a refused block is split by the next slow mode and re-tested; a block that fails and
  cannot be split is an ATOM the spectral proposal could not place, and it is handed to the
  witness rule rather than forced into a node.

Why ||D_b||_2 is exactly computable per block without a dense operator. With rank-1 blocks the
columns of U are the whitened block indicators u_b = sqrt(pi|_b) / sqrt(mass_b), which are
orthonormal, so P = sum_c u_c u_c^T and

    D_b = u_b^T Ltilde (I - P) = M_b - sum_c (M U)_bc u_c^T,   M = U^T Ltilde,

and because the u_c are orthonormal, ||D_b||_2^2 = ||M_b||^2 - ||(M U)_b||^2 exactly. M has at
most nnz(Ltilde) stored entries, so the whole test costs one segment reduction over the edge
list. No n x n object is ever formed.

Complexity (n rows, nnz edges, K blocks, V declared task values, R refinement rounds):
  acceptance one round   O(nnz + n + V) device work, O(nnz) device memory
  the descent            O(R (nnz + n)), R bounded by the number of slow modes used, and the
                         modes are drawn in doubling batches whose size provably does not change
                         the accepted set (checked by ``schedule_invariance`` in the tests)
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Sequence

import torch

from .generator import ComponentGenerator
from .lens import LensDeclaration

__all__ = ["TaskColumns", "Tolerances", "AcceptanceRound", "BlockRefusal", "Descent",
           "TaggedComponent", "build_task_columns", "derive_tolerances", "slow_modes",
           "evaluate_blocking", "tagged_component", "evaluate_cover", "descend"]


# --------------------------------------------------------------------------- task columns
@dataclass(frozen=True, slots=True)
class TaskColumns:
    """The declared observables A.11 tests, as (column, value) indicator supports.

    ``owner`` marks, per row, which task column applies to it: a row of another kind is not
    MISSING the column, it does not declare it, so it is outside that column's sub-carrier and
    contributes neither mass nor residual to it (the same reading the A.34 face fold uses).
    """

    names: tuple[str, ...]                 # "<row kind>.<column>" per task column
    epsilon: torch.Tensor                  # float64 [A] - eps_a per task column
    column_of_row: torch.Tensor            # int64 [n] - task column applying to a row, or -1
    value_of_row: torch.Tensor             # int64 [n] - the value code, or -1
    value_base: torch.Tensor               # int64 [A + 1] - value code offsets per column
    value_column: torch.Tensor             # int64 [V] - the task column each global value is in
    value_mass: torch.Tensor               # float64 [V] - ||atilde_a||^2 per (column, value)
    column_mass: torch.Tensor              # float64 [A] - pi mass of each column's sub-carrier
    condition_min_mass: float              # b_min over the declared conditioning events

    @property
    def n_values(self) -> int:
        return int(self.value_column.numel())


def _column_codes(ingestion, component: ComponentGenerator, kind: str, column: str
                  ) -> tuple[torch.Tensor, torch.Tensor, int]:
    """(row mask over the component, int64 value code per member, vocabulary size). O(n)."""
    table = ingestion.store.table(kind)
    device = component.device
    local_of_global = torch.full((ingestion.store.row_count,), -1, dtype=torch.int64,
                                 device=device)
    local_of_global[table.global_ordinals] = torch.arange(
        len(table), dtype=torch.int64, device=device)
    position = local_of_global[component.global_rows]
    mask = position >= 0
    codes = torch.full((component.n,), -1, dtype=torch.int64, device=device)
    raw = table.column(column).to(torch.int64)
    # A null code (-1) is NOT dropped and is NOT a default: it is shifted to the declared value
    # 0, "the column is absent on this row". A block mixing rows that carry a status with rows
    # that do not is impure in that column, and A.11 should see that rather than be told a
    # convenient value.
    shifted = torch.where(raw < 0, torch.zeros_like(raw), raw + 1)
    codes[mask] = shifted[position[mask]]
    vocabulary = max(int(shifted.max()) + 1, 2) if raw.numel() else 2
    return mask, codes, vocabulary


def build_task_columns(ingestion, lens: LensDeclaration,
                       component: ComponentGenerator) -> TaskColumns:
    """A.11's declared observables and A.12's b_min, measured on this component. O(n * A)."""
    device = component.device
    names: list[str] = []
    epsilons: list[float] = []
    column_of_row = torch.full((component.n,), -1, dtype=torch.int64, device=device)
    value_of_row = torch.full((component.n,), -1, dtype=torch.int64, device=device)
    bases: list[int] = [0]
    value_column: list[torch.Tensor] = []
    column_mass: list[float] = []
    offset = 0
    for index, (kind, column) in enumerate(lens.task_columns()):
        mask, codes, vocabulary = _column_codes(ingestion, component, kind, column)
        names.append(f"{kind}.{column}")
        epsilons.append(lens.precision_of(kind, column))
        column_of_row[mask] = index
        value_of_row[mask] = codes[mask] + offset
        value_column.append(torch.full((vocabulary,), index, dtype=torch.int64, device=device))
        column_mass.append(float(component.pi[mask].sum()))
        offset += vocabulary
        bases.append(offset)
    value_column_t = (torch.cat(value_column) if value_column
                      else torch.empty(0, dtype=torch.int64, device=device))
    value_mass = torch.zeros(offset, dtype=torch.float64, device=device)
    seen = value_of_row >= 0
    if bool(seen.any()):
        value_mass.index_add_(0, value_of_row[seen], component.pi[seen])

    # A.12's b_min: the smallest reference mass of a conditioning event the declared grammar
    # admits. Measured on the record; if the lens declares no conditioning column, the admitted
    # events are the task columns' own values, which is the tightest honest reading.
    condition_masses: list[float] = []
    pairs = lens.condition_columns() or lens.task_columns()
    for kind, column in pairs:
        mask, codes, _ = _column_codes(ingestion, component, kind, column)
        if not bool(mask.any()):
            continue
        present = codes[mask]
        unique = torch.unique(present)
        mass = torch.zeros(int(unique.max()) + 1, dtype=torch.float64, device=device)
        mass.index_add_(0, present, component.pi[mask])
        positive = mass[mass > 0]
        if positive.numel():
            condition_masses.append(float(positive.min()))
    # The declared grammar ALWAYS admits the anchor event "the row with this id" (the dataset
    # declaration's anchor_fields are declared, B.5), whose reference mass is that row's own pi.
    # Including it is what stops b_min degenerating to 1 on a component where every row shares
    # one value of every declared column - a degenerate chi2_max = 0 would make TEST 1 vacuous.
    condition_masses.append(float(component.pi.min()))
    b_min = min(condition_masses)
    return TaskColumns(tuple(names),
                       torch.tensor(epsilons, dtype=torch.float64, device=device),
                       column_of_row, value_of_row,
                       torch.tensor(bases, dtype=torch.int64, device=device),
                       value_column_t, value_mass,
                       torch.tensor(column_mass, dtype=torch.float64, device=device),
                       b_min)


# --------------------------------------------------------------------------- tolerances
@dataclass(frozen=True, slots=True)
class Tolerances:
    """Every number the two tests compare against, each with the clause that derives it."""

    chi2_max: float
    b_min: float
    tau_observable: torch.Tensor      # float64 [A] - A.11's tau_a per task column
    tau_closure: float                # A.13's tau_D
    walk_horizon: int
    derivation: dict[str, str]


def derive_tolerances(lens: LensDeclaration, columns: TaskColumns) -> Tolerances:
    """A.11 and A.13's tolerances, DERIVED. Nothing here is set, chosen or tuned. O(A)."""
    b_min = columns.condition_min_mass
    chi2_max = max(1.0 / b_min - 1.0, 0.0)
    tau_a = columns.epsilon / (chi2_max ** 0.5)
    norms = torch.sqrt(columns.value_mass)
    per_value = columns.epsilon[columns.value_column] / (
        torch.clamp(norms, min=torch.finfo(torch.float64).tiny)
        * lens.walk_horizon * (chi2_max ** 0.5))
    live = columns.value_mass > 0
    tau_d = float(per_value[live].min()) if bool(live.any()) else float("inf")
    return Tolerances(
        chi2_max=chi2_max, b_min=b_min, tau_observable=tau_a, tau_closure=tau_d,
        walk_horizon=lens.walk_horizon,
        derivation={
            "b_min": "A.12: the smallest reference mass pi(A) over the conditioning events the "
                     "lens's declared query grammar admits, MEASURED on this component's pi.",
            "chi2_max": "A.12: chi2_max = 1/b_min - 1.",
            "tau_observable": "A.11: tau_a = eps_a / sqrt(chi2_max), componentwise per declared "
                              "task column; eps_a is the lens's authored answer precision with "
                              "its own derivation string.",
            "tau_closure": "A.13: tau_D = min_a eps_a / (||atilde_a|| t* sqrt(chi2_max)), with "
                           "t* the lens's declared walk horizon in item-paced units (A.3).",
        })


# --------------------------------------------------------------------------- proposal
def slow_modes(component: ComponentGenerator, wanted: int) -> tuple[torch.Tensor, torch.Tensor]:
    """The ``wanted`` slowest modes of Ltilde, constant mode first. GPU only, no CPU path.

    Dense symmetric eigendecomposition is used exactly when the dense matrix fits the declared
    per-component device share and Lanczos could not supply the modes anyway (it needs
    k < n - 1); otherwise CuPy's sparse symmetric eigensolver runs on the same device memory,
    zero-copy through DLPack. The two routes compute the same modes: the choice is a resource
    decision and changes cost, not the accepted set.

    Complexity: dense O(n^3); Lanczos O(nnz * k) per iteration.
    """
    rows, cols, values = component.whitened_laplacian_coo()
    n = component.n
    wanted = max(1, min(wanted, n))
    dense_bytes = n * n * 8
    if wanted >= n - 1 or dense_bytes <= DENSE_SHARE_BYTES:
        matrix = torch.zeros((n, n), dtype=torch.float64, device=component.device)
        matrix.index_put_((rows, cols), values, accumulate=True)
        eigenvalues, eigenvectors = torch.linalg.eigh(matrix)
        return eigenvalues[:wanted].contiguous(), eigenvectors[:, :wanted].contiguous()
    import cupy
    from cupyx.scipy.sparse import coo_matrix
    from cupyx.scipy.sparse.linalg import eigsh
    data = cupy.from_dlpack(values.detach())
    row_index = cupy.from_dlpack(rows.detach().to(torch.int32))
    col_index = cupy.from_dlpack(cols.detach().to(torch.int32))
    sparse = coo_matrix((data, (row_index, col_index)), shape=(n, n)).tocsr()
    # The normalised Laplacian's spectrum lies in [0, 2]; 2I - L turns the SLOWEST modes of L
    # into the LARGEST of the shifted operator, which is the direction Lanczos converges in.
    shifted = -sparse
    shifted.setdiag(shifted.diagonal() + 2.0)
    shifted_values, vectors = eigsh(shifted, k=wanted, which="LA")
    order = cupy.argsort(-shifted_values)
    eigenvalues = 2.0 - shifted_values[order]
    vectors = vectors[:, order]
    return (torch.from_dlpack(eigenvalues).to(torch.float64),
            torch.from_dlpack(vectors).to(torch.float64))


# One component's share of the packet's declared 1 GiB device ceiling. Derivation: the ceiling
# is the brief's ("keep device memory under 1 GiB - another packet shares the card"); a dense
# symmetric eigendecomposition needs the matrix plus its eigenvectors plus LAPACK workspace, so
# a quarter of the ceiling is the largest dense matrix that cannot overrun it.
DEVICE_CEILING_BYTES = 1 << 30
DENSE_SHARE_BYTES = DEVICE_CEILING_BYTES // 4


# --------------------------------------------------------------------------- acceptance
@dataclass(frozen=True, slots=True)
class BlockRefusal:
    """Why one block was refused: the test, the column, the value, the margin."""

    block: int
    test: str
    column: str
    value_code: int
    measured: float
    tolerance: float

    @property
    def margin(self) -> float:
        return self.measured - self.tolerance

    def to_dict(self) -> dict[str, Any]:
        return {"block": self.block, "test": self.test, "column": self.column,
                "value_code": self.value_code, "measured": self.measured,
                "tolerance": self.tolerance, "margin": self.margin}


@dataclass(frozen=True, slots=True)
class AcceptanceRound:
    """One evaluation of a complete blocking: the two tests, per block, as two verdicts."""

    labels: torch.Tensor              # int64 [n] - block of each row (a partition here)
    blocks: int
    mass: torch.Tensor                # float64 [K] - transported mass per block (A.4)
    observable_worst: torch.Tensor    # float64 [K] - max_a,v ||e|| per block
    observable_worst_value: torch.Tensor   # int64 [K] - which (column, value) attained it
    closure_norm: torch.Tensor        # float64 [K] - ||D_b||_2 per block
    passes_observable: torch.Tensor   # bool [K]
    passes_closure: torch.Tensor      # bool [K]
    tolerances: Tolerances

    @property
    def accepted(self) -> torch.Tensor:
        return self.passes_observable & self.passes_closure

    def refusals(self, columns: TaskColumns) -> list[BlockRefusal]:
        out: list[BlockRefusal] = []
        tau_a = self.tolerances.tau_observable
        for block in torch.nonzero(~self.passes_observable, as_tuple=False).flatten().tolist():
            value = int(self.observable_worst_value[block])
            column = int(columns.value_column[value]) if value >= 0 else -1
            out.append(BlockRefusal(
                block, "A.11-observable-adequacy",
                columns.names[column] if column >= 0 else "(none)",
                value - int(columns.value_base[column]) if column >= 0 else -1,
                float(self.observable_worst[block]),
                float(tau_a[column]) if column >= 0 else float("inf")))
        for block in torch.nonzero(~self.passes_closure, as_tuple=False).flatten().tolist():
            out.append(BlockRefusal(block, "A.13-dynamical-closure", "(all columns)", -1,
                                    float(self.closure_norm[block]),
                                    self.tolerances.tau_closure))
        return out


def evaluate_blocking(component: ComponentGenerator, labels: torch.Tensor,
                      columns: TaskColumns, tolerances: Tolerances) -> AcceptanceRound:
    """Run BOTH tests on a complete blocking, per block, vectorised. O(nnz + n + K V_block)."""
    device = component.device
    n, pi = component.n, component.pi
    blocks = int(labels.max()) + 1 if labels.numel() else 0
    mass = torch.zeros(blocks, dtype=torch.float64, device=device)
    mass.index_add_(0, labels, pi)

    # ---- TEST 1 (A.11), componentwise over (task column, value)
    worst = torch.zeros(blocks, dtype=torch.float64, device=device)
    worst_value = torch.full((blocks,), -1, dtype=torch.int64, device=device)
    passes_observable = torch.ones(blocks, dtype=torch.bool, device=device)
    seen = columns.value_of_row >= 0
    if bool(seen.any()):
        rows = torch.nonzero(seen, as_tuple=False).flatten()
        key = labels[rows] * columns.n_values + columns.value_of_row[rows]
        unique, inverse = torch.unique(key, sorted=True, return_inverse=True)
        cell_mass = torch.zeros(unique.numel(), dtype=torch.float64, device=device)
        cell_mass.index_add_(0, inverse, pi[rows])
        cell_block = torch.div(unique, columns.n_values, rounding_mode="floor")
        cell_value = unique - cell_block * columns.n_values
        cell_column = columns.value_column[cell_value]
        # the sub-carrier mass of each (block, task column): a row of another kind does not
        # declare the column and is outside it
        column_key = cell_block * len(columns.names) + cell_column
        column_unique, column_inverse = torch.unique(column_key, sorted=True,
                                                     return_inverse=True)
        sub_mass = torch.zeros(column_unique.numel(), dtype=torch.float64, device=device)
        sub_mass.index_add_(0, column_inverse, cell_mass)
        residual = torch.sqrt(torch.clamp(
            cell_mass - cell_mass.square() / sub_mass[column_inverse], min=0.0))
        tau = tolerances.tau_observable[cell_column]
        scatter = torch.zeros(blocks, dtype=torch.float64, device=device)
        scatter.scatter_reduce_(0, cell_block, residual, reduce="amax", include_self=True)
        worst = scatter
        # which (column, value) attained the worst residual in each block
        hit = residual >= worst[cell_block] - 0.0
        worst_value.scatter_reduce_(0, cell_block[hit], cell_value[hit], reduce="amax",
                                    include_self=False)
        failing = torch.zeros(blocks, dtype=torch.int8, device=device)
        failing.scatter_reduce_(0, cell_block, (residual > tau).to(torch.int8),
                                reduce="amax", include_self=True)
        passes_observable = failing == 0

    # ---- TEST 2 (A.13), ||D_b||^2 = ||M_b||^2 - ||(M U)_b||^2 exactly
    rows, cols, values = component.whitened_laplacian_coo()
    u = torch.sqrt(pi / mass[labels])
    contribution = u[rows] * values                      # u_b(i) Ltilde_ij, b = labels[i]
    key = labels[rows] * n + cols
    unique, inverse = torch.unique(key, sorted=True, return_inverse=True)
    m_values = torch.zeros(unique.numel(), dtype=torch.float64, device=device)
    m_values.index_add_(0, inverse, contribution)
    m_block = torch.div(unique, n, rounding_mode="floor")
    m_col = unique - m_block * n
    m_row_norm = torch.zeros(blocks, dtype=torch.float64, device=device)
    m_row_norm.index_add_(0, m_block, m_values.square())
    coarse_key = m_block * blocks + labels[m_col]
    coarse_unique, coarse_inverse = torch.unique(coarse_key, sorted=True, return_inverse=True)
    coarse_values = torch.zeros(coarse_unique.numel(), dtype=torch.float64, device=device)
    coarse_values.index_add_(0, coarse_inverse, m_values * u[m_col])
    coarse_block = torch.div(coarse_unique, blocks, rounding_mode="floor")
    coarse_norm = torch.zeros(blocks, dtype=torch.float64, device=device)
    coarse_norm.index_add_(0, coarse_block, coarse_values.square())
    closure = torch.sqrt(torch.clamp(m_row_norm - coarse_norm, min=0.0))
    passes_closure = closure <= tolerances.tau_closure
    return AcceptanceRound(labels, blocks, mass, worst, worst_value, closure,
                           passes_observable, passes_closure, tolerances)


# ------------------------------------------------------- acceptance ON A COVER (A.26 tagged)
@dataclass(frozen=True, slots=True)
class TaggedComponent:
    """A.26's tagged numeric domain: one row per ACTIVE MEMBERSHIP TAG, mass split by B.25.

    A.11 and A.13 as the contract states them are tests on an ISOMETRY - the columns of U must
    be orthonormal, which they are for a partition and are NOT for a many-to-many cover, because
    two blocks sharing a member have overlapping support. A.33(d) and A.26 say where the cover
    lives instead: the tagged domain, in which a member held by k blocks becomes k tagged rows
    carrying B.25's declared weight 1/k of its mass. In that domain the cover IS a partition, so
    the two tests apply unchanged and their verdicts are exact rather than approximate.

    The tagged walk is the lifted ``section_calculus`` one: G_tag = J G_off D - Lambda_tag with
    J the scatter and D the reduce. Its symmetric witness matrix is S_tag(a,b) = w_a w_b S_ij,
    its degree is d_tag(a) = w_a d_i (because the weights of j's tags sum to one) and its
    stationary law is pi_tag(a) = w_a pi_i - all three checked by ``tagged_component`` itself.
    The weights are float and act ONLY here: B.36's coarse counts are taken on the UNTAGGED
    cover and stay int64 at every grade.

    Complexity: nnz_tag <= (max tags per row)^2 nnz; two tags per row is the measured worst case.
    """

    n: int
    pi: torch.Tensor               # float64 [t] - w_a pi_i, sums to 1
    src: torch.Tensor              # int64 [nnz_tag]
    dst: torch.Tensor              # int64 [nnz_tag]
    value: torch.Tensor            # float64 [nnz_tag] - S_tag, A.26's tagged numeric domain
    degree: torch.Tensor           # float64 [t]
    device: torch.device
    weight_defect: float           # max |sum_b w_ib - 1| over sources
    mass_defect: float             # max |pi_tag - w pi| - B.19 in the tagged domain

    def whitened_laplacian_coo(self) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Ltilde = I - D^{-1/2} S_tag D^{-1/2} as (rows, cols, values) float64. O(nnz_tag)."""
        root = torch.sqrt(self.degree)
        off = -self.value / (root[self.src] * root[self.dst])
        diag = torch.arange(self.n, dtype=torch.int64, device=self.device)
        rows = torch.cat([self.src, diag])
        cols = torch.cat([self.dst, diag])
        values = torch.cat([off, torch.ones(self.n, dtype=torch.float64, device=self.device)])
        return rows, cols, values


def tagged_component(component: ComponentGenerator, tag_row: torch.Tensor,
                     tag_weight: torch.Tensor) -> TaggedComponent:
    """Lift one component's generator into A.26's tagged domain. O(nnz * tags^2), vectorised."""
    device = component.device
    n = component.n
    tags = int(tag_row.numel())
    per_row = torch.bincount(tag_row, minlength=n)
    weight_sum = torch.zeros(n, dtype=torch.float64, device=device)
    weight_sum.index_add_(0, tag_row, tag_weight)
    weight_defect = float(torch.max(torch.abs(weight_sum - 1.0))) if n else 0.0

    # tags grouped by their source row, so a row's tags are a contiguous run
    order = torch.argsort(tag_row, stable=True)
    ptr = torch.zeros(n + 1, dtype=torch.int64, device=device)
    torch.cumsum(per_row, dim=0, out=ptr[1:])

    src_tags = per_row[component.src]
    dst_tags = per_row[component.dst]
    pairs = src_tags * dst_tags
    total = int(pairs.sum())
    if total:
        edge_ptr = torch.zeros(pairs.numel() + 1, dtype=torch.int64, device=device)
        torch.cumsum(pairs, dim=0, out=edge_ptr[1:])
        slot = torch.arange(total, dtype=torch.int64, device=device)
        edge = torch.searchsorted(edge_ptr[1:], slot, right=True)
        within = slot - edge_ptr[edge]
        a_index = torch.div(within, dst_tags[edge], rounding_mode="floor")
        b_index = within - a_index * dst_tags[edge]
        tag_a = order[ptr[component.src[edge]] + a_index]
        tag_b = order[ptr[component.dst[edge]] + b_index]
        value = tag_weight[tag_a] * tag_weight[tag_b] * component.count[edge].to(torch.float64)
    else:                                                   # pragma: no cover - a 1-row component
        tag_a = tag_b = torch.empty(0, dtype=torch.int64, device=device)
        value = torch.empty(0, dtype=torch.float64, device=device)
    degree = torch.zeros(tags, dtype=torch.float64, device=device)
    if total:
        degree.index_add_(0, tag_b, value)
    pi = degree / degree.sum()
    mass_defect = float(torch.max(torch.abs(pi - tag_weight * component.pi[tag_row]))) \
        if tags else 0.0
    return TaggedComponent(n=tags, pi=pi, src=tag_a, dst=tag_b, value=value, degree=degree,
                           device=device, weight_defect=weight_defect, mass_defect=mass_defect)


def evaluate_cover(component: ComponentGenerator, tag_row: torch.Tensor,
                   tag_block: torch.Tensor, tag_weight: torch.Tensor,
                   columns: TaskColumns, tolerances: Tolerances
                   ) -> tuple[AcceptanceRound, TaggedComponent]:
    """Run BOTH tests on the membership a cover actually carries. O(nnz_tag + t + K V).

    The tolerances are NOT recomputed here: they are properties of the lens and the record
    (A.11's eps_a, A.12's b_min on the component's own pi), not of the blocking, so a cover is
    judged against exactly the numbers the partition was judged against and the two verdicts are
    comparable. Only the membership and the observable supports move into the tagged domain.
    """
    tagged = tagged_component(component, tag_row, tag_weight)
    lifted = replace(columns,
                     column_of_row=columns.column_of_row[tag_row],
                     value_of_row=columns.value_of_row[tag_row])
    return evaluate_blocking(tagged, tag_block, lifted, tolerances), tagged


# --------------------------------------------------------------------------- the descent
@dataclass(frozen=True, slots=True)
class Descent:
    """What the descent produced: accepted blocks, refused atoms, and every refusal by name."""

    labels: torch.Tensor                      # int64 [n] - final cell of each row
    accepted_cells: tuple[int, ...]
    refused_cells: tuple[int, ...]
    refusals: tuple[BlockRefusal, ...]
    rounds: int
    modes_used: int
    eigenvalues: torch.Tensor
    final_round: AcceptanceRound
    columns: TaskColumns
    tolerances: Tolerances

    def accepted_members(self) -> list[torch.Tensor]:
        return [torch.nonzero(self.labels == cell, as_tuple=False).flatten()
                for cell in self.accepted_cells]


def _split(labels: torch.Tensor, cells: Sequence[int], vector: torch.Tensor) -> torch.Tensor:
    """Split each named cell by the sign of one mode. O(n). No cell count is chosen."""
    out = labels.clone()
    next_label = int(labels.max()) + 1
    for cell in cells:
        member = torch.nonzero(labels == cell, as_tuple=False).flatten()
        positive = member[vector[member] >= 0]
        negative = member[vector[member] < 0]
        if positive.numel() == 0 or negative.numel() == 0:
            continue
        out[negative] = next_label
        next_label += 1
    return out


def descend(ingestion, lens: LensDeclaration, component: ComponentGenerator) -> Descent:
    """Propose by slow modes, accept by the two tests, split exactly where they refuse.

    Complexity: O(R (nnz + n)) with R the number of refinement rounds, R <= modes used <= n - 1.
    """
    device = component.device
    columns = build_task_columns(ingestion, lens, component)
    tolerances = derive_tolerances(lens, columns)
    labels = torch.zeros(component.n, dtype=torch.int64, device=device)
    batch = 2
    eigenvalues, vectors = slow_modes(component, min(batch, component.n))
    refusals: list[BlockRefusal] = []
    rounds = 0
    mode = 1                                   # mode 0 is the constant; it cuts nothing
    frozen: set[int] = set()
    while True:
        evaluation = evaluate_blocking(component, labels, columns, tolerances)
        rounds += 1
        failing = torch.nonzero(~evaluation.accepted, as_tuple=False).flatten().tolist()
        failing = [cell for cell in failing if cell not in frozen]
        if not failing or mode >= min(component.n, vectors.shape[1]) and mode >= component.n - 1:
            refusals = evaluation.refusals(columns)
            break
        if mode >= vectors.shape[1]:
            batch = min(batch * 2, component.n)
            eigenvalues, vectors = slow_modes(component, batch)
            if mode >= vectors.shape[1]:
                refusals = evaluation.refusals(columns)
                break
        proposed = _split(labels, failing, vectors[:, mode])
        mode += 1
        if bool(torch.equal(proposed, labels)):
            # nothing this mode could cut: those cells are atoms of the spectral proposal
            frozen.update(failing)
            if len(frozen) == int(labels.max()) + 1:
                refusals = evaluation.refusals(columns)
                break
            continue
        labels = proposed
    final = evaluate_blocking(component, labels, columns, tolerances)
    accepted = torch.nonzero(final.accepted, as_tuple=False).flatten().tolist()
    refused = torch.nonzero(~final.accepted, as_tuple=False).flatten().tolist()
    return Descent(labels, tuple(accepted), tuple(refused),
                   tuple(final.refusals(columns)), rounds, mode, eigenvalues, final,
                   columns, tolerances)
