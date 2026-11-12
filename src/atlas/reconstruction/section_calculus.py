"""Typed finite coarse-section and corrective-register calculus on CUDA.

These identities evaluate a supplied coarse map, generator, task and correction
geometry.  They do not select a semantic hierarchy or claim that geometric
closure alone is task adequacy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import torch


@dataclass(frozen=True)
class StateObservableConventions:
    state_pushforward: str = "p_coarse = C p_fine"
    state_section: str = "p_fine_hat = R p_coarse; C R = I"
    observable_pullback: str = "f_fine = C.T f_coarse"
    observable_conditional_average: str = "f_coarse = R.T f_fine"
    closure_norm: str = "||A||_(W,F)^2 = Tr(A W A.T), W=diag(pi)"
    observable_norm: str = "||f||_(pi)^2 = f.T W f"
    state_perturbation_norm: str = "||dp||_(pi,-1)^2 = dp.T W^-1 dp"


@dataclass(frozen=True)
class CoarseCalculus:
    pi: torch.Tensor
    weights: torch.Tensor
    assignment: torch.Tensor
    labels: torch.Tensor
    section: torch.Tensor
    fine_generator: torch.Tensor
    coarse_generator: torch.Tensor
    residue: torch.Tensor
    weighted_column_profile: torch.Tensor
    closure_loss: torch.Tensor
    coarse_null: torch.Tensor
    section_identity_defect: torch.Tensor
    fine_null_defect: torch.Tensor
    coarse_null_defect: torch.Tensor
    conventions: StateObservableConventions


@dataclass(frozen=True)
class ResidueSplit:
    section: torch.Tensor
    retained_projector: torch.Tensor
    hidden_projector: torch.Tensor
    retained_mismatch: torch.Tensor
    hidden_coupling: torch.Tensor
    recomposed_residue: torch.Tensor
    decomposition_defect: torch.Tensor


@dataclass(frozen=True)
class CocycleResult:
    direct_residue: torch.Tensor
    composed_residue: torch.Tensor
    defect: torch.Tensor
    defect_norm: torch.Tensor


@dataclass(frozen=True)
class TaskAdequacy:
    reconstructed_observables: torch.Tensor
    residuals: torch.Tensor
    weighted_errors: torch.Tensor
    maximum_error: torch.Tensor
    adequate: torch.Tensor
    tolerance: float


@dataclass(frozen=True)
class WhitenedClosure:
    whitened_generator: torch.Tensor
    whitened_assignment: torch.Tensor
    retained_projector: torch.Tensor
    hidden_projector: torch.Tensor
    adjoint_residue: torch.Tensor
    transformed_residue: torch.Tensor
    identity_defect: torch.Tensor


@dataclass(frozen=True)
class TaskAnswerBounds:
    task_errors: torch.Tensor
    chi_square: torch.Tensor
    certified_bounds: torch.Tensor
    actual_errors: torch.Tensor
    coarse_observables: torch.Tensor


@dataclass(frozen=True)
class CorrectiveRegister:
    task_map: torch.Tensor
    candidate_chart: torch.Tensor
    correction_metric: torch.Tensor
    residual_demands: torch.Tensor
    residual_weights: torch.Tensor
    transported_demands: torch.Tensor
    demand_gram: torch.Tensor
    benefit_eigenvalues: torch.Tensor
    register: torch.Tensor
    physical_register: torch.Tensor
    chosen_rank: int
    solve_route: Literal["primal", "dual"]
    baseline_objective: torch.Tensor
    captured_reduction: torch.Tensor
    restricted_objective: torch.Tensor
    rank_cost: torch.Tensor
    metric_orthogonality_defect: torch.Tensor
    objective_identity_defect: torch.Tensor
    metric_eigenvalues: torch.Tensor
    supported_metric_rank: int
    metric_support_threshold: torch.Tensor
    unsupported_demand_norm: torch.Tensor
    requested_rank: int | None
    tie_extension: int
    tie_tolerance: float
    nonunique_tie: bool


@dataclass(frozen=True)
class TaggedCover:
    source_ids: torch.Tensor
    membership_weights: torch.Tensor
    tag_source_rows: torch.Tensor
    tag_section_ids: torch.Tensor
    tag_weights: torch.Tensor
    active_tags_per_source: torch.Tensor
    declared_section_count: int
    convention: str = (
        "positive active tags reference shared sources; declared weights sum to one per source"
    )

    @property
    def source_count(self) -> int:
        return self.source_ids.numel()

    @property
    def tag_count(self) -> int:
        return self.tag_source_rows.numel()


def _cuda_float(tensor: torch.Tensor, name: str) -> None:
    if not isinstance(tensor, torch.Tensor) or not tensor.is_cuda or not tensor.is_floating_point():
        raise TypeError(f"{name} must be a floating CUDA tensor")


def _validated(condition: torch.Tensor, message: str) -> None:
    """Synchronize a device-computed input predicate without poisoning CUDA."""

    if not bool(condition.detach().item()):
        raise ValueError(message)


@torch.no_grad()
def build_tagged_cover(
    membership_weights: torch.Tensor,
    source_ids: torch.Tensor,
    *,
    tolerance: float = 1e-8,
) -> TaggedCover:
    """Create factored active tags from a declared source-by-section partition of unity."""

    _cuda_float(membership_weights, "membership_weights")
    if membership_weights.ndim != 2 or not membership_weights.shape[1]:
        raise ValueError("membership_weights must have shape [source,section]")
    if (
        source_ids.ndim != 1
        or source_ids.shape[0] != membership_weights.shape[0]
        or source_ids.device != membership_weights.device
        or source_ids.dtype != torch.int64
    ):
        raise ValueError("source_ids must be CUDA int64 with one ID per weight row")
    sorted_ids = torch.sort(source_ids).values
    _validated(torch.all(sorted_ids[1:] != sorted_ids[:-1]), "source IDs must be unique")
    _validated(torch.min(membership_weights) >= 0, "cover weights must be nonnegative")
    row_sum = torch.sum(membership_weights, dim=1)
    _validated(
        torch.max(torch.abs(row_sum - 1)) <= tolerance,
        "every source must have positive cover summing to one",
    )
    active = torch.nonzero(membership_weights > 0, as_tuple=False)
    tag_source = active[:, 0].to(torch.int64)
    tag_section = active[:, 1].to(torch.int64)
    tag_weight = membership_weights[tag_source, tag_section]
    counts = torch.bincount(tag_source, minlength=source_ids.numel())
    return TaggedCover(
        source_ids=source_ids,
        membership_weights=membership_weights,
        tag_source_rows=tag_source,
        tag_section_ids=tag_section,
        tag_weights=tag_weight,
        active_tags_per_source=counts,
        declared_section_count=membership_weights.shape[1],
    )


@torch.no_grad()
def tag_scatter(cover: TaggedCover, source_state: torch.Tensor) -> torch.Tensor:
    """Apply J: split source mass across its declared active memberships."""

    _cuda_float(source_state, "source_state")
    if source_state.device != cover.source_ids.device or source_state.shape[-1] != cover.source_count:
        raise ValueError("source_state final dimension must equal cover source count")
    return source_state[..., cover.tag_source_rows] * cover.tag_weights


@torch.no_grad()
def tag_reduce(cover: TaggedCover, tag_state: torch.Tensor) -> torch.Tensor:
    """Apply D: sum tagged mass back to each shared source row."""

    _cuda_float(tag_state, "tag_state")
    if tag_state.device != cover.source_ids.device or tag_state.shape[-1] != cover.tag_count:
        raise ValueError("tag_state final dimension must equal active tag count")
    flat = tag_state.reshape(-1, cover.tag_count)
    reduced = torch.zeros(
        (flat.shape[0], cover.source_count), device=tag_state.device, dtype=tag_state.dtype
    )
    reduced.scatter_add_(
        1,
        cover.tag_source_rows.unsqueeze(0).expand(flat.shape[0], -1),
        flat,
    )
    return reduced.reshape(*tag_state.shape[:-1], cover.source_count)


@torch.no_grad()
def tag_lift_observable(cover: TaggedCover, source_observable: torch.Tensor) -> torch.Tensor:
    """Apply D.T to a source-compatible observable without copying source content."""

    _cuda_float(source_observable, "source_observable")
    if (
        source_observable.device != cover.source_ids.device
        or source_observable.shape[-1] != cover.source_count
    ):
        raise ValueError("observable final dimension must equal source count")
    return source_observable[..., cover.tag_source_rows]


@torch.no_grad()
def tag_generator_action(
    cover: TaggedCover,
    source_generator: torch.Tensor,
    tag_state: torch.Tensor,
) -> torch.Tensor:
    """Apply G_tag=J G_off D-Lambda_tag through reduction/action/scatter."""

    _cuda_float(source_generator, "source_generator")
    if source_generator.shape != (cover.source_count, cover.source_count):
        raise ValueError("source generator shape differs from cover source count")
    source = tag_reduce(cover, tag_state)
    off = source_generator - torch.diag(torch.diagonal(source_generator))
    moved = source @ off.T
    scattered = tag_scatter(cover, moved)
    exit_rate = -torch.diagonal(source_generator)
    return scattered - tag_state * exit_rate[cover.tag_source_rows]


@torch.no_grad()
def dense_tag_generator(
    cover: TaggedCover, source_generator: torch.Tensor
) -> torch.Tensor:
    """Materialize the lifted generator only for small exact checks."""

    _cuda_float(source_generator, "source_generator")
    if source_generator.shape != (cover.source_count, cover.source_count):
        raise ValueError("source generator shape differs from cover source count")
    J = torch.zeros(
        (cover.tag_count, cover.source_count),
        device=source_generator.device,
        dtype=source_generator.dtype,
    )
    J[torch.arange(cover.tag_count, device=J.device), cover.tag_source_rows] = cover.tag_weights
    D = torch.zeros(
        (cover.source_count, cover.tag_count), device=J.device, dtype=J.dtype
    )
    D[cover.tag_source_rows, torch.arange(cover.tag_count, device=J.device)] = 1
    off = source_generator - torch.diag(torch.diagonal(source_generator))
    exit_rate = -torch.diagonal(source_generator)[cover.tag_source_rows]
    return J @ off @ D - torch.diag(exit_rate)


def _assignment_matrix(
    assignment_or_labels: torch.Tensor, n: int, dtype: torch.dtype
) -> tuple[torch.Tensor, torch.Tensor]:
    if assignment_or_labels.ndim == 1:
        if assignment_or_labels.shape[0] != n or assignment_or_labels.dtype not in (
            torch.int32,
            torch.int64,
        ):
            raise ValueError("labels must be an integer vector with n entries")
        original_labels = assignment_or_labels.to(torch.int64)
        torch._assert_async(torch.all(original_labels >= 0), "coarse labels must be nonnegative")
        unique_labels, labels = torch.unique(original_labels, sorted=True, return_inverse=True)
        coarse_count = unique_labels.numel()
        if coarse_count > n:
            raise ValueError("coarse cell count cannot exceed fine state count")
        C = torch.nn.functional.one_hot(labels, coarse_count).T.to(dtype)
    elif assignment_or_labels.ndim == 2:
        C = assignment_or_labels.to(dtype)
        if C.shape[1] != n:
            raise ValueError("assignment matrix must have shape [m,n]")
        if C.shape[0] > n:
            raise ValueError("coarse cell count cannot exceed fine state count")
        torch._assert_async(
            torch.all((C == 0) | (C == 1)), "assignment must be binary"
        )
        torch._assert_async(
            torch.all(torch.sum(C, dim=0) == 1), "each fine state needs one coarse label"
        )
        torch._assert_async(torch.all(torch.sum(C, dim=1) > 0), "coarse cells cannot be empty")
        labels = torch.argmax(C, dim=0)
    else:
        raise ValueError("assignment must be labels [n] or binary matrix [m,n]")
    return C, labels


@torch.no_grad()
def build_coarse_calculus(
    pi: torch.Tensor,
    assignment_or_labels: torch.Tensor,
    generator: torch.Tensor,
    *,
    tolerance: float = 1e-9,
) -> CoarseCalculus:
    """Evaluate one supplied aggregation for a column-conservative CTMC generator."""

    _cuda_float(pi, "pi")
    _cuda_float(generator, "generator")
    if pi.ndim != 1 or generator.shape != (pi.numel(), pi.numel()):
        raise ValueError("require pi[n] and generator[n,n]")
    if generator.device != pi.device or assignment_or_labels.device != pi.device:
        raise ValueError("all calculus tensors must share one CUDA device")
    dtype = torch.float64 if pi.dtype == torch.float64 or generator.dtype == torch.float64 else torch.float32
    pi = pi.to(dtype)
    generator = generator.to(dtype)
    C, labels = _assignment_matrix(assignment_or_labels, pi.numel(), dtype)
    torch._assert_async(torch.all(pi > 0), "pi must have full positive support")
    torch._assert_async(torch.abs(torch.sum(pi) - 1) <= tolerance, "pi must sum to one")
    torch._assert_async(
        torch.max(torch.abs(torch.sum(generator, dim=0))) <= tolerance,
        "generator must be column conservative",
    )
    off_diagonal = generator - torch.diag(torch.diagonal(generator))
    torch._assert_async(torch.min(off_diagonal) >= -tolerance, "generator off-diagonals must be nonnegative")
    fine_null_defect = generator @ pi
    torch._assert_async(
        torch.max(torch.abs(fine_null_defect)) <= tolerance,
        "pi must be stationary for the declared generator",
    )

    coarse_mass = C @ pi
    section = (pi.unsqueeze(1) * C.T) / coarse_mass.unsqueeze(0)
    coarse_generator = C @ generator @ section
    residue = C @ generator - coarse_generator @ C
    column_profile = torch.sqrt(
        pi * torch.sum(residue.square(), dim=0)
    )
    closure_loss = torch.linalg.vector_norm(column_profile)
    section_defect = C @ section - torch.eye(C.shape[0], device=C.device, dtype=dtype)
    coarse_null_defect = coarse_generator @ coarse_mass
    return CoarseCalculus(
        pi=pi,
        weights=pi,
        assignment=C,
        labels=labels,
        section=section,
        fine_generator=generator,
        coarse_generator=coarse_generator,
        residue=residue,
        weighted_column_profile=column_profile,
        closure_loss=closure_loss,
        coarse_null=coarse_mass,
        section_identity_defect=section_defect,
        fine_null_defect=fine_null_defect,
        coarse_null_defect=coarse_null_defect,
        conventions=StateObservableConventions(),
    )


@torch.no_grad()
def split_residue(calculus: CoarseCalculus, section: torch.Tensor | None = None) -> ResidueSplit:
    """Split fixed residue using an explicitly chosen right-inverse section."""

    chosen = calculus.section if section is None else section.to(calculus.pi.dtype)
    C = calculus.assignment
    if chosen.device != C.device or chosen.shape != (C.shape[1], C.shape[0]):
        raise ValueError("section must have shape [n,m] on the calculus CUDA device")
    torch._assert_async(
        torch.max(torch.abs(C @ chosen - torch.eye(C.shape[0], device=C.device, dtype=C.dtype)))
        <= 1e-8,
        "chosen section is not a right inverse",
    )
    P = chosen @ C
    Q = torch.eye(P.shape[0], device=P.device, dtype=P.dtype) - P
    retained = C @ calculus.fine_generator @ chosen - calculus.coarse_generator
    hidden = C @ calculus.fine_generator @ Q
    recomposed = retained @ C + hidden
    return ResidueSplit(
        section=chosen,
        retained_projector=P,
        hidden_projector=Q,
        retained_mismatch=retained,
        hidden_coupling=hidden,
        recomposed_residue=recomposed,
        decomposition_defect=recomposed - calculus.residue,
    )


@torch.no_grad()
def closure_cocycle(
    first: CoarseCalculus,
    second: CoarseCalculus,
) -> CocycleResult:
    """Check Delta_02=C_12 Delta_01+Delta_12 C_01 exactly by typing."""

    C01, C12 = first.assignment, second.assignment
    if second.fine_generator.shape != first.coarse_generator.shape:
        raise ValueError("second calculus must act on the first coarse space")
    torch._assert_async(
        torch.max(torch.abs(second.fine_generator - first.coarse_generator)) <= 1e-8,
        "second fine generator differs from first coarse generator",
    )
    C02 = C12 @ C01
    direct = C02 @ first.fine_generator - second.coarse_generator @ C02
    composed = C12 @ first.residue + second.residue @ C01
    defect = direct - composed
    return CocycleResult(direct, composed, defect, torch.linalg.vector_norm(defect))


@torch.no_grad()
def task_adequacy(
    calculus: CoarseCalculus,
    observables: torch.Tensor,
    *,
    tolerance: float,
) -> TaskAdequacy:
    """Measure retained observable loss separately from generator closure."""

    _cuda_float(observables, "observables")
    if observables.device != calculus.pi.device or observables.ndim != 2:
        raise ValueError("observables must be CUDA [task,n]")
    if observables.shape[1] != calculus.pi.numel():
        raise ValueError("observable width differs from fine state count")
    typed_observables = observables.to(calculus.pi.dtype)
    reconstructed = (
        calculus.assignment.T @ (calculus.section.T @ typed_observables.T)
    ).T
    residual = typed_observables - reconstructed
    errors = torch.sqrt(torch.sum(calculus.pi.unsqueeze(0) * residual.square(), dim=1))
    maximum = torch.max(errors) if errors.numel() else torch.zeros((), device=errors.device)
    return TaskAdequacy(
        reconstructed_observables=reconstructed,
        residuals=residual,
        weighted_errors=errors,
        maximum_error=maximum,
        adequate=maximum <= tolerance,
        tolerance=tolerance,
    )


@torch.no_grad()
def whitened_adjoint_closure(calculus: CoarseCalculus) -> WhitenedClosure:
    """Return the Euclidean-whitened observable-boundary closure defect."""

    pi_root = torch.sqrt(calculus.pi)
    coarse_root = torch.sqrt(calculus.coarse_null)
    G_tilde = (
        calculus.fine_generator
        * pi_root.unsqueeze(0)
        / pi_root.unsqueeze(1)
    )
    C_tilde = (
        calculus.assignment
        * pi_root.unsqueeze(0)
        / coarse_root.unsqueeze(1)
    )
    P_tilde = C_tilde.T @ C_tilde
    Q_tilde = torch.eye(
        calculus.pi.numel(), device=calculus.pi.device, dtype=calculus.pi.dtype
    ) - P_tilde
    adjoint = Q_tilde @ G_tilde.T @ C_tilde.T
    transformed = (
        calculus.residue
        * pi_root.unsqueeze(0)
        / coarse_root.unsqueeze(1)
    ).T
    return WhitenedClosure(
        whitened_generator=G_tilde,
        whitened_assignment=C_tilde,
        retained_projector=P_tilde,
        hidden_projector=Q_tilde,
        adjoint_residue=adjoint,
        transformed_residue=transformed,
        identity_defect=adjoint - transformed,
    )


@torch.no_grad()
def task_answer_bounds(
    calculus: CoarseCalculus,
    observables: torch.Tensor,
    fine_laws: torch.Tensor,
) -> TaskAnswerBounds:
    """Evaluate sqrt(L_f)*sqrt(chi2(p||pi)) and its actual finite error."""

    adequacy = task_adequacy(calculus, observables, tolerance=float("inf"))
    _cuda_float(fine_laws, "fine_laws")
    laws = fine_laws.to(calculus.pi.dtype)
    if laws.ndim != 2 or laws.shape[1] != calculus.pi.numel():
        raise ValueError("fine_laws must have shape [law,n]")
    torch._assert_async(torch.all(laws >= 0), "fine laws must be nonnegative")
    torch._assert_async(
        torch.max(torch.abs(torch.sum(laws, dim=1) - 1)) <= 1e-8,
        "each fine law must sum to one",
    )
    chi_square = torch.sum(
        (laws - calculus.pi.unsqueeze(0)).square() / calculus.pi.unsqueeze(0), dim=1
    )
    bounds = adequacy.weighted_errors.unsqueeze(1) * torch.sqrt(chi_square).unsqueeze(0)
    coarse_observables = calculus.section.T @ observables.to(calculus.pi.dtype).T
    fine_answers = observables.to(calculus.pi.dtype) @ laws.T
    coarse_answers = coarse_observables.T @ (calculus.assignment @ laws.T)
    return TaskAnswerBounds(
        task_errors=adequacy.weighted_errors,
        chi_square=chi_square,
        certified_bounds=bounds,
        actual_errors=torch.abs(fine_answers - coarse_answers),
        coarse_observables=coarse_observables.T,
    )


@torch.no_grad()
def build_corrective_register(
    task_map: torch.Tensor,
    candidate_chart: torch.Tensor,
    correction_cost: torch.Tensor,
    residual_demands: torch.Tensor,
    residual_weights: torch.Tensor,
    *,
    regularization: float,
    rank: int | None = None,
    rank_price: float = 0.0,
    support_tolerance: float = 1e-10,
    unsupported_tolerance: float = 1e-9,
    tie_tolerance: float = 1e-7,
) -> CorrectiveRegister:
    """Construct Candidate-B's exact finite task/cost corrective register."""

    for tensor, name in (
        (task_map, "task_map"),
        (candidate_chart, "candidate_chart"),
        (correction_cost, "correction_cost"),
        (residual_demands, "residual_demands"),
        (residual_weights, "residual_weights"),
    ):
        _cuda_float(tensor, name)
    device = task_map.device
    if any(tensor.device != device for tensor in (
        candidate_chart, correction_cost, residual_demands, residual_weights
    )):
        raise ValueError("all corrective-register tensors must share one CUDA device")
    dtype = torch.float64 if any(
        tensor.dtype == torch.float64
        for tensor in (task_map, candidate_chart, correction_cost, residual_demands, residual_weights)
    ) else torch.float32
    T, F, K, E, p = (
        task_map.to(dtype),
        candidate_chart.to(dtype),
        correction_cost.to(dtype),
        residual_demands.to(dtype),
        residual_weights.to(dtype),
    )
    if T.ndim != 2 or F.ndim != 2 or E.ndim != 2 or K.ndim != 2 or p.ndim != 1:
        raise ValueError("task/candidate/cost/residual arrays have incompatible ranks")
    h, m = F.shape
    if T.shape[1] != h or E.shape[0] != h or K.shape != (m, m) or p.shape[0] != E.shape[1]:
        raise ValueError("task/candidate/cost/residual dimensions disagree")
    if (
        regularization < 0
        or rank_price < 0
        or support_tolerance <= 0
        or unsupported_tolerance < 0
        or tie_tolerance < 0
    ):
        raise ValueError("regularization/rank price/tolerances are invalid")
    for tensor in (T, F, K, E, p):
        torch._assert_async(torch.all(torch.isfinite(tensor)), "corrective inputs must be finite")
    torch._assert_async(torch.all(p >= 0), "residual weights must be nonnegative")
    torch._assert_async(torch.abs(torch.sum(p) - 1) <= 1e-8, "residual weights must sum to one")
    torch._assert_async(
        torch.max(torch.abs(K - K.T)) <= 1e-8, "correction cost K must be symmetric"
    )
    eigen_k = torch.linalg.eigvalsh((K + K.T) * 0.5)
    k_scale = torch.max(torch.abs(eigen_k)).clamp_min(1)
    torch._assert_async(
        torch.min(eigen_k) >= -support_tolerance * k_scale,
        "correction cost K must be positive semidefinite",
    )
    if regularization > 0:
        torch._assert_async(
            torch.min(eigen_k) > support_tolerance * k_scale,
            "positive regularization requires positive-definite correction cost K",
        )
    S = T @ F
    Hc = S.T @ S + regularization * K
    Hc = (Hc + Hc.T) * 0.5
    eigen_h, vectors_h = torch.linalg.eigh(Hc)
    h_scale = torch.max(torch.abs(eigen_h)).clamp_min(1)
    threshold = support_tolerance * h_scale
    supported = eigen_h > threshold
    torch._assert_async(
        torch.any(supported), "correction metric has empty observable support"
    )
    U_h = vectors_h[:, supported]
    lambda_h = eigen_h[supported]
    task_residual = T @ E
    transported = S.T @ task_residual
    B = transported * torch.sqrt(p).unsqueeze(0)
    unsupported = transported - U_h @ (U_h.T @ transported)
    unsupported_norm = torch.linalg.vector_norm(unsupported)
    demand_scale = torch.linalg.vector_norm(transported).clamp_min(1)
    torch._assert_async(
        unsupported_norm <= unsupported_tolerance * demand_scale,
        "transported demand has unsupported correction-metric component",
    )
    Hplus_B = U_h @ ((U_h.T @ B) / lambda_h.unsqueeze(1))
    residual_count = E.shape[1]
    supported_rank = lambda_h.numel()
    if supported_rank <= residual_count:
        whitened = (U_h.T @ B) / torch.sqrt(lambda_h).unsqueeze(1)
        gram = whitened @ whitened.T
        eta, U_support = torch.linalg.eigh((gram + gram.T) * 0.5)
        order = torch.argsort(eta, descending=True)
        eta = torch.clamp_min(eta[order], 0)
        U_support = U_support[:, order]
        full_register = U_h @ (U_support / torch.sqrt(lambda_h).unsqueeze(1))
        route: Literal["primal", "dual"] = "primal"
        demand_gram = gram
    else:
        gram = B.T @ Hplus_B
        eta, V = torch.linalg.eigh((gram + gram.T) * 0.5)
        order = torch.argsort(eta, descending=True)
        eta = torch.clamp_min(eta[order], 0)
        V = V[:, order]
        positive = eta > support_tolerance * torch.max(eta).clamp_min(1)
        eta = eta[positive]
        V = V[:, positive]
        full_register = Hplus_B @ (V / torch.sqrt(eta).unsqueeze(0))
        route = "dual"
        demand_gram = gram
    if rank is not None:
        if rank < 0:
            raise ValueError("rank must be nonnegative")
        requested = min(rank, eta.numel())
    else:
        requested = int(torch.sum(eta > 2 * rank_price).item())
    chosen = requested
    nonunique_tie = False
    if 0 < chosen < eta.numel():
        scale = torch.max(eta).clamp_min(1)
        boundary = eta[chosen - 1]
        tied = torch.abs(eta[chosen:] - boundary) <= tie_tolerance * scale
        if bool((boundary > support_tolerance * scale).detach().cpu()):
            leading = torch.cumprod(tied.to(torch.int64), dim=0)
            chosen += int(torch.sum(leading).item())
        else:
            nonunique_tie = bool(torch.any(tied).detach().cpu())
    register = full_register[:, :chosen]
    benefit = eta[: register.shape[1]]
    baseline = 0.5 * torch.sum(p * torch.sum(task_residual.square(), dim=0))
    captured = 0.5 * torch.sum(benefit)
    cost = torch.tensor(rank_price * register.shape[1], device=device, dtype=dtype)
    restricted = baseline - captured + cost
    metric_defect = (
        register.T @ Hc @ register
        - torch.eye(register.shape[1], device=device, dtype=dtype)
    )
    coefficients = register.T @ transported
    empirical_captured = 0.5 * torch.sum(p * torch.sum(coefficients.square(), dim=0))
    return CorrectiveRegister(
        task_map=T,
        candidate_chart=F,
        correction_metric=Hc,
        residual_demands=E,
        residual_weights=p,
        transported_demands=transported,
        demand_gram=demand_gram,
        benefit_eigenvalues=eta,
        register=register,
        physical_register=F @ register,
        chosen_rank=register.shape[1],
        solve_route=route,
        baseline_objective=baseline,
        captured_reduction=captured,
        restricted_objective=restricted,
        rank_cost=cost,
        metric_orthogonality_defect=metric_defect,
        objective_identity_defect=empirical_captured - captured,
        metric_eigenvalues=eigen_h,
        supported_metric_rank=supported_rank,
        metric_support_threshold=threshold,
        unsupported_demand_norm=unsupported_norm,
        requested_rank=rank,
        tie_extension=chosen - requested,
        tie_tolerance=tie_tolerance,
        nonunique_tie=nonunique_tie,
    )


__all__ = [
    "CoarseCalculus",
    "CocycleResult",
    "CorrectiveRegister",
    "ResidueSplit",
    "StateObservableConventions",
    "TaggedCover",
    "TaskAdequacy",
    "TaskAnswerBounds",
    "WhitenedClosure",
    "build_coarse_calculus",
    "build_corrective_register",
    "build_tagged_cover",
    "closure_cocycle",
    "split_residue",
    "dense_tag_generator",
    "tag_generator_action",
    "tag_lift_observable",
    "tag_reduce",
    "tag_scatter",
    "task_answer_bounds",
    "task_adequacy",
    "whitened_adjoint_closure",
]
