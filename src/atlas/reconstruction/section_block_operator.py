"""Sparse block transport for reversible retained-register operators.

This is a bounded CUDA reference kernel.  It avoids dense global operators and
composite isometries, but its explicit COO expansion can still cost
``operator_nnz * local_rank**2`` and can densify between interacting blocks.
Capacity refusal and measured work are part of the public result.
"""
from __future__ import annotations

from dataclasses import dataclass

import torch

from .gpu_budget import resolve_gpu_budget


@dataclass(frozen=True)
class SparseSymmetricOperator:
    dimension: int
    rows: torch.Tensor
    columns: torch.Tensor
    values: torch.Tensor
    reference: torch.Tensor
    norm_upper: torch.Tensor
    source_norm_upper: torch.Tensor
    composed_defect_bound: torch.Tensor
    stored_bytes: int
    work: dict

    @property
    def device(self):
        return self.values.device


@dataclass(frozen=True)
class BlockIsometry:
    coefficients: torch.Tensor             # [K,rpad], local modes by owner
    parent_labels: torch.Tensor             # [K]
    mode_offsets: torch.Tensor              # [P+1]
    mode_ranks: torch.Tensor                # [P]
    constant_local_indices: torch.Tensor    # [P]
    output_mode_owners: torch.Tensor        # [Kout]
    output_local_modes: torch.Tensor        # [Kout]
    output_reference: torch.Tensor          # [Kout]
    owner_order: torch.Tensor               # [K]
    owner_offsets: torch.Tensor             # [P+1]
    stored_bytes: int
    padded_coefficient_entries: int
    active_coefficient_entries: int
    budget: dict | None = None

    @property
    def input_dimension(self):
        return self.coefficients.shape[0]

    @property
    def output_dimension(self):
        return int(self.mode_offsets[-1].detach().cpu())


@dataclass(frozen=True)
class PositiveMassCOO:
    rows: torch.Tensor
    columns: torch.Tensor
    values: torch.Tensor
    reference_mass: torch.Tensor
    constant_mode_indices: torch.Tensor
    column_conservation_defect: torch.Tensor
    stationarity_defect: torch.Tensor
    minimum_offdiagonal: torch.Tensor
    stored_bytes: int


@dataclass(frozen=True)
class BlockTransportResult:
    operator: SparseSymmetricOperator
    mass_operator: PositiveMassCOO
    defect_block_rows: torch.Tensor
    defect_block_columns: torch.Tensor
    defect_block_frobenius: torch.Tensor
    stage_defect_bound: torch.Tensor
    work: dict


def _validated(predicate, message):
    if not bool(predicate.detach().cpu()):
        raise ValueError(message)


def _integer_cuda(value, name, rank=1):
    if not isinstance(value, torch.Tensor) or not value.is_cuda or value.dtype != torch.int64 or value.ndim != rank:
        raise TypeError(f"{name} must be CUDA int64 rank-{rank}")


def _float_cuda(value, name, rank=None):
    if not isinstance(value, torch.Tensor) or not value.is_cuda or not value.dtype.is_floating_point:
        raise TypeError(f"{name} must be a CUDA floating tensor")
    if rank is not None and value.ndim != rank:
        raise ValueError(f"{name} must have rank {rank}")


def _tensor_bytes(*values):
    return sum(value.numel() * value.element_size() for value in values)


def _coalesce(rows, columns, values, dimension):
    if rows.numel() == 0:
        return rows, columns, values
    keys = rows * dimension + columns
    unique, inverse = torch.unique(keys, sorted=True, return_inverse=True)
    summed = torch.zeros(unique.numel(), device=values.device, dtype=values.dtype)
    summed.index_add_(0, inverse, values)
    keep = summed != 0
    unique, summed = unique[keep], summed[keep]
    return (
        torch.div(unique, dimension, rounding_mode="floor"),
        torch.remainder(unique, dimension),
        summed,
    )


@torch.no_grad()
def incidence_operator(
    source_count: int,
    edge_sources: torch.Tensor,
    edge_targets: torch.Tensor,
    conductance: torch.Tensor,
    sqrt_reference: torch.Tensor,
    *,
    max_bytes=None,
    tolerance=2e-9,
) -> SparseSymmetricOperator:
    """Construct ``L=-DD^T`` from undirected reversible graph conductances."""

    _integer_cuda(edge_sources, "edge_sources")
    _integer_cuda(edge_targets, "edge_targets")
    _float_cuda(conductance, "conductance", rank=1)
    _float_cuda(sqrt_reference, "sqrt_reference", rank=1)
    if source_count <= 0 or sqrt_reference.numel() != source_count:
        raise ValueError("source_count and reference disagree")
    if edge_sources.shape != edge_targets.shape or edge_sources.shape != conductance.shape:
        raise ValueError("edge arrays must align")
    if any(value.device != sqrt_reference.device for value in (edge_sources, edge_targets, conductance)):
        raise ValueError("incidence tensors must share one CUDA device")
    _validated(torch.all((edge_sources >= 0) & (edge_sources < source_count)), "edge source outside jurisdiction")
    _validated(torch.all((edge_targets >= 0) & (edge_targets < source_count)), "edge target outside jurisdiction")
    _validated(torch.all(edge_sources != edge_targets), "self edges are not incidence columns")
    _validated(torch.all(torch.isfinite(conductance)) & torch.all(conductance > 0), "conductance must be finite positive")
    reference = sqrt_reference.double()
    _validated(torch.all(reference > 0) & torch.all(torch.isfinite(reference)), "reference must have finite positive support")
    _validated(torch.abs(torch.sum(reference.square()) - 1) <= tolerance, "reference squares must sum to one")
    edge_count = edge_sources.numel()
    resident = _tensor_bytes(
        edge_sources, edge_targets, conductance, sqrt_reference
    )
    budget = resolve_gpu_budget(
        reference.device, max_bytes, resident_bytes=resident
    )
    max_bytes = budget.max_bytes
    preflight = max(1, edge_count) * 4 * (8 + 8 + 8) * 3
    if resident + preflight > max_bytes:
        raise MemoryError("incidence COO construction exceeds capacity")
    weight = conductance.double()
    pi = reference.square()
    rows = torch.cat((edge_sources, edge_targets, edge_sources, edge_targets))
    columns = torch.cat((edge_sources, edge_targets, edge_targets, edge_sources))
    values = torch.cat((
        -weight / pi[edge_sources],
        -weight / pi[edge_targets],
        weight / (reference[edge_sources] * reference[edge_targets]),
        weight / (reference[edge_sources] * reference[edge_targets]),
    ))
    contribution_count = values.numel()
    rows, columns, values = _coalesce(rows, columns, values, source_count)
    exit_rate = torch.zeros(source_count, device=reference.device, dtype=torch.float64)
    exit_rate.index_add_(0, edge_sources, weight / pi[edge_sources])
    exit_rate.index_add_(0, edge_targets, weight / pi[edge_targets])
    norm_upper = 2 * exit_rate.max()
    stored = _tensor_bytes(rows, columns, values, reference, norm_upper)
    if stored > max_bytes:
        raise MemoryError("coalesced incidence operator exceeds capacity")
    result = SparseSymmetricOperator(
        source_count, rows, columns, values, reference, norm_upper,
        norm_upper.clone(), torch.zeros((), device=reference.device, dtype=torch.float64),
        stored,
        {
            "construction": "reversible_graph_incidence",
            "undirected_edges": edge_count,
            "padded_coo_contributions": contribution_count,
            "coalesced_nnz": values.numel(),
            "preflight_bytes": preflight,
            "stored_bytes": stored,
            "norm_bound": "2*maximum_exit_rate",
            "dtype": "float64",
            "budget": budget.receipt(),
        },
    )
    _validated(
        torch.linalg.vector_norm(
            apply_operator(result, reference, max_bytes=max_bytes)
        ) <= 20 * tolerance,
        "incidence operator does not preserve reference",
    )
    return result


@torch.no_grad()
def build_block_isometry(
    coefficients: torch.Tensor,
    parent_labels: torch.Tensor,
    mode_offsets: torch.Tensor,
    mode_ranks: torch.Tensor,
    reference: torch.Tensor,
    *,
    constant_local_indices: torch.Tensor | None = None,
    max_bytes=None,
    tolerance=2e-9,
) -> BlockIsometry:
    """Validate a padded block-local isometry without constructing dense U."""

    _float_cuda(coefficients, "coefficients", rank=2)
    _integer_cuda(parent_labels, "parent_labels")
    _integer_cuda(mode_offsets, "mode_offsets")
    _integer_cuda(mode_ranks, "mode_ranks")
    _float_cuda(reference, "reference", rank=1)
    k, rpad = coefficients.shape
    parents = mode_ranks.numel()
    if parent_labels.numel() != k or reference.numel() != k or mode_offsets.numel() != parents + 1:
        raise ValueError("block isometry shapes disagree")
    if any(value.device != coefficients.device for value in (parent_labels, mode_offsets, mode_ranks, reference)):
        raise ValueError("block isometry tensors must share one CUDA device")
    coefficients = coefficients.double()
    reference = reference.double()
    resident = _tensor_bytes(
        coefficients, parent_labels, mode_offsets, mode_ranks, reference
    )
    budget = resolve_gpu_budget(
        coefficients.device, max_bytes, resident_bytes=resident
    )
    max_bytes = budget.max_bytes
    _validated(torch.all((parent_labels >= 0) & (parent_labels < parents)), "parent label outside map")
    _validated(torch.all((mode_ranks > 0) & (mode_ranks <= rpad)), "mode rank outside padded width")
    _validated(mode_offsets[0] == 0, "mode offsets must start at zero")
    _validated(torch.all(mode_offsets[1:] - mode_offsets[:-1] == mode_ranks), "mode offsets must compactly encode ranks")
    if constant_local_indices is None:
        constants = torch.zeros(parents, device=coefficients.device, dtype=torch.int64)
    else:
        _integer_cuda(constant_local_indices, "constant_local_indices")
        if constant_local_indices.device != coefficients.device or constant_local_indices.numel() != parents:
            raise ValueError("one constant local index per parent required")
        constants = constant_local_indices
    _validated(torch.all((constants >= 0) & (constants < mode_ranks)), "constant local index outside active modes")
    preflight = k * rpad * rpad * 8 * 3
    if resident + preflight > max_bytes:
        raise MemoryError("block-isometry Gram validation exceeds capacity")
    local = torch.arange(rpad, device=coefficients.device)
    active = local[None, :] < mode_ranks[parent_labels, None]
    _validated(torch.max(torch.abs(coefficients * ~active)) <= tolerance, "padded coefficient slots must be zero")
    outer = coefficients[:, :, None].double() * coefficients[:, None, :].double()
    gram = torch.zeros((parents, rpad, rpad), device=coefficients.device, dtype=torch.float64)
    gram.index_add_(0, parent_labels, outer)
    target = torch.zeros_like(gram)
    diagonal = torch.arange(rpad, device=coefficients.device)
    target[:, diagonal, diagonal] = (
        diagonal[None, :] < mode_ranks[:, None]
    ).to(target.dtype)
    _validated(torch.max(torch.abs(gram - target)) <= tolerance, "local coefficient columns are not orthonormal")
    output_owners = torch.repeat_interleave(torch.arange(parents, device=coefficients.device), mode_ranks)
    output_local = torch.arange(mode_offsets[-1], device=coefficients.device) - torch.repeat_interleave(mode_offsets[:-1], mode_ranks)
    mode = mode_offsets[parent_labels, None] + local[None, :]
    contribution = coefficients.double() * active
    output_reference = torch.zeros(mode_offsets[-1], device=coefficients.device, dtype=torch.float64)
    output_reference.index_add_(0, mode[active], (reference.double()[:, None] * contribution)[active])
    constant_modes = mode_offsets[:-1] + constants
    nonconstant = torch.ones(output_reference.numel(), device=coefficients.device, dtype=torch.bool)
    nonconstant[constant_modes] = False
    _validated(torch.all(output_reference[constant_modes] > 0), "constant modes need positive reference coordinates")
    if nonconstant.any():
        _validated(torch.max(torch.abs(output_reference[nonconstant])) <= tolerance, "signed mode acquired reference mass")
    owner_order = torch.argsort(parent_labels, stable=True)
    counts = torch.bincount(parent_labels, minlength=parents)
    owner_offsets = torch.cat((torch.zeros(1, device=coefficients.device, dtype=torch.int64), torch.cumsum(counts, 0)))
    stored = _tensor_bytes(
        coefficients, parent_labels, mode_offsets, mode_ranks, constants,
        output_owners, output_local, output_reference, owner_order, owner_offsets,
    )
    if stored > max_bytes:
        raise MemoryError("block isometry storage exceeds capacity")
    result = BlockIsometry(
        coefficients.double(), parent_labels, mode_offsets, mode_ranks, constants,
        output_owners, output_local, output_reference, owner_order, owner_offsets,
        stored, coefficients.numel(), int(active.sum().detach().cpu()),
        budget.receipt(),
    )
    _validated(
        torch.linalg.vector_norm(
            apply_down(result, output_reference, max_bytes=max_bytes)
            - reference.double()
        ) <= 20 * tolerance,
        "block map does not preserve the reference",
    )
    return result


@torch.no_grad()
def apply_up(mapping: BlockIsometry, values: torch.Tensor, *, max_bytes=None) -> torch.Tensor:
    """Apply U^T to one vector or a leading batch using scatter-add."""

    _float_cuda(values, "values")
    one = values.ndim == 1
    batch = values[None, :] if one else values
    if batch.ndim != 2 or batch.shape[1] != mapping.input_dimension or batch.device != mapping.coefficients.device:
        raise ValueError("UP input must end in the map input dimension")
    rpad = mapping.coefficients.shape[1]
    temporary = 8 * (
        2 * batch.shape[0] * mapping.input_dimension * rpad
        + batch.shape[0] * mapping.output_reference.numel()
        + 3 * mapping.input_dimension * rpad
    )
    resident = mapping.stored_bytes + values.numel() * values.element_size()
    budget = resolve_gpu_budget(values.device, max_bytes, resident_bytes=resident)
    if resident + temporary > budget.max_bytes:
        raise MemoryError("UP batch temporary exceeds capacity")
    local = torch.arange(rpad, device=values.device)
    active = local[None, :] < mapping.mode_ranks[mapping.parent_labels, None]
    modes = mapping.mode_offsets[mapping.parent_labels, None] + local[None, :]
    modes = torch.where(active, modes, torch.zeros_like(modes))
    contribution = batch[:, :, None] * mapping.coefficients[None, :, :]
    contribution = contribution * active[None, :, :]
    output = torch.zeros((batch.shape[0], mapping.output_reference.numel()), device=values.device, dtype=torch.float64)
    output.scatter_add_(1, modes.reshape(1, -1).expand(batch.shape[0], -1), contribution.reshape(batch.shape[0], -1))
    return output[0] if one else output


@torch.no_grad()
def apply_down(mapping: BlockIsometry, values: torch.Tensor, *, max_bytes=None) -> torch.Tensor:
    """Apply U to one vector or a leading batch using padded local gathers."""

    _float_cuda(values, "values")
    one = values.ndim == 1
    batch = values[None, :] if one else values
    if batch.ndim != 2 or batch.shape[1] != mapping.output_reference.numel() or batch.device != mapping.coefficients.device:
        raise ValueError("DOWN input must end in the map output dimension")
    rpad = mapping.coefficients.shape[1]
    temporary = 8 * (
        2 * batch.shape[0] * mapping.input_dimension * rpad
        + batch.shape[0] * mapping.input_dimension
        + 3 * mapping.input_dimension * rpad
    )
    resident = mapping.stored_bytes + values.numel() * values.element_size()
    budget = resolve_gpu_budget(values.device, max_bytes, resident_bytes=resident)
    if resident + temporary > budget.max_bytes:
        raise MemoryError("DOWN batch temporary exceeds capacity")
    local = torch.arange(rpad, device=values.device)
    active = local[None, :] < mapping.mode_ranks[mapping.parent_labels, None]
    modes = mapping.mode_offsets[mapping.parent_labels, None] + local[None, :]
    modes = torch.where(active, modes, torch.zeros_like(modes))
    gathered = batch[:, modes] * mapping.coefficients[None, :, :]
    output = torch.sum(gathered * active[None, :, :], dim=2)
    return output[0] if one else output


@torch.no_grad()
def apply_operator(operator: SparseSymmetricOperator, values: torch.Tensor, *, max_bytes=None) -> torch.Tensor:
    """Apply coordinate COO to one vector or a leading batch."""

    _float_cuda(values, "values")
    one = values.ndim == 1
    batch = values[None, :] if one else values
    if batch.ndim != 2 or batch.shape[1] != operator.dimension or batch.device != operator.device:
        raise ValueError("operator input must end in its coordinate dimension")
    temporary = 8 * batch.shape[0] * (
        2 * operator.values.numel() + operator.dimension
    )
    resident = operator.stored_bytes + values.numel() * values.element_size()
    budget = resolve_gpu_budget(values.device, max_bytes, resident_bytes=resident)
    if resident + temporary > budget.max_bytes:
        raise MemoryError("operator apply batch temporary exceeds capacity")
    contribution = batch[:, operator.columns] * operator.values[None, :]
    output = torch.zeros((batch.shape[0], operator.dimension), device=values.device, dtype=torch.float64)
    output.scatter_add_(1, operator.rows[None, :].expand(batch.shape[0], -1), contribution)
    return output[0] if one else output


@torch.no_grad()
def transport_block_operator(
    operator: SparseSymmetricOperator,
    mapping: BlockIsometry,
    *,
    max_bytes=None,
    numerical_allowance=2e-9,
) -> BlockTransportResult:
    """Compute sparse ``U^T L U`` and a block-norm closure certificate."""

    if operator.device != mapping.coefficients.device or operator.dimension != mapping.input_dimension:
        raise ValueError("operator and block map jurisdictions disagree")
    resident = operator.stored_bytes + mapping.stored_bytes
    budget = resolve_gpu_budget(
        operator.device, max_bytes, resident_bytes=resident
    )
    max_bytes = budget.max_bytes
    nnz = operator.values.numel()
    rpad = mapping.coefficients.shape[1]
    output_dimension = mapping.output_reference.numel()
    a_contributions = nnz * rpad * rpad
    # Sort only E parent-pair keys, then accumulate rpad x rpad outer products
    # per interacting block. Scalar output COO is derived after coalescing.
    first_preflight = (
        a_contributions * 8 * 6          # outer/block values, slots and sort workspace
        + nnz * 8 * 5                    # parent-pair keys/inverse/sort
        + nnz * rpad * 8 * 2             # coefficient gathers
    )
    if first_preflight + operator.stored_bytes + mapping.stored_bytes > max_bytes:
        raise MemoryError("block transport contribution expansion exceeds capacity")
    local = torch.arange(rpad, device=operator.device)
    row_owner = mapping.parent_labels[operator.rows]
    col_owner = mapping.parent_labels[operator.columns]
    row_active = local[None, :] < mapping.mode_ranks[row_owner, None]
    col_active = local[None, :] < mapping.mode_ranks[col_owner, None]
    pair_keys = row_owner * mapping.mode_ranks.numel() + col_owner
    unique_pairs, pair_inverse = torch.unique(pair_keys, sorted=True, return_inverse=True)
    pair_rows = torch.div(unique_pairs, mapping.mode_ranks.numel(), rounding_mode="floor")
    pair_cols = torch.remainder(unique_pairs, mapping.mode_ranks.numel())
    outer_contribution = (
        operator.values[:, None, None]
        * mapping.coefficients[operator.rows, :, None]
        * mapping.coefficients[operator.columns, None, :]
    )
    block_values = torch.zeros(
        (unique_pairs.numel(), rpad, rpad),
        device=operator.device, dtype=torch.float64,
    )
    block_values.index_add_(0, pair_inverse, outer_contribution)
    valid_blocks = (
        local[None, :, None] < mapping.mode_ranks[pair_rows, None, None]
    ) & (
        local[None, None, :] < mapping.mode_ranks[pair_cols, None, None]
    )
    block_rows = (
        mapping.mode_offsets[pair_rows, None, None]
        + local[None, :, None]
    ).expand(-1, -1, rpad)
    block_cols = (
        mapping.mode_offsets[pair_cols, None, None]
        + local[None, None, :]
    ).expand(-1, rpad, -1)
    # Retain every structurally valid block slot, including exact cancellation
    # zeros. Filtering on floating equality made COO structure depend on GPU
    # reduction order and understated later structural work.
    a_rows = block_rows[valid_blocks]
    a_cols = block_cols[valid_blocks]
    a_values = block_values[valid_blocks]
    actual_a_contributions = int(
        torch.sum(
            mapping.mode_ranks[row_owner] * mapping.mode_ranks[col_owner]
        ).detach().cpu()
    )
    coalesced_parent_blocks = unique_pairs.numel()
    output_block_slots = block_values.numel()
    del outer_contribution, block_values, pair_inverse, pair_keys, unique_pairs

    # A U^T expands each output-column mode only over the input coordinates
    # owned by that mode's parent block.
    a_col_owner = mapping.output_mode_owners[a_cols]
    lengths = mapping.owner_offsets[a_col_owner + 1] - mapping.owner_offsets[a_col_owner]
    au_contributions = int(torch.sum(lengths).detach().cpu())
    active_m_contributions = int(torch.sum(mapping.mode_ranks[row_owner]).detach().cpu())
    live_a_bytes = _tensor_bytes(a_rows, a_cols, a_values, a_col_owner, lengths)
    second_preflight = (
        live_a_bytes
        + (active_m_contributions + au_contributions) * 8 * 18
    )
    if second_preflight + operator.stored_bytes + mapping.stored_bytes > max_bytes:
        raise MemoryError("block closure residual expansion exceeds capacity")
    # M=U^T L in sparse rectangular coordinates, allocated only after the
    # second gate accounts for still-live output COO buffers.
    row_modes = mapping.mode_offsets[row_owner, None] + local[None, :]
    m_values = operator.values[:, None] * mapping.coefficients[operator.rows]
    m_rows = row_modes[row_active]
    m_cols = operator.columns[:, None].expand(-1, rpad)[row_active]
    m_values = m_values[row_active]
    m_keys = m_rows * operator.dimension + m_cols
    prefix = torch.cumsum(lengths, 0) - lengths
    starts = mapping.owner_offsets[a_col_owner]
    base = torch.repeat_interleave(starts, lengths)
    offset = torch.arange(torch.sum(lengths), device=operator.device) - torch.repeat_interleave(prefix, lengths)
    input_columns = mapping.owner_order[base + offset]
    repeated_rows = torch.repeat_interleave(a_rows, lengths)
    repeated_values = torch.repeat_interleave(a_values, lengths)
    repeated_local = torch.repeat_interleave(mapping.output_local_modes[a_cols], lengths)
    au_values = repeated_values * mapping.coefficients[input_columns, repeated_local]
    au_keys = repeated_rows * operator.dimension + input_columns
    residual_keys = torch.cat((m_keys, au_keys))
    residual_values = torch.cat((m_values, -au_values))
    unique_residual, residual_inverse = torch.unique(residual_keys, sorted=True, return_inverse=True)
    residual = torch.zeros(unique_residual.numel(), device=operator.device, dtype=torch.float64)
    residual.index_add_(0, residual_inverse, residual_values)
    # Keep structural residual slots for deterministic accounting; zero entries
    # contribute zero to every block norm.
    residual_rows = torch.div(unique_residual, operator.dimension, rounding_mode="floor")
    residual_cols = torch.remainder(unique_residual, operator.dimension)
    block_rows = mapping.output_mode_owners[residual_rows]
    block_cols = mapping.parent_labels[residual_cols]
    parent_count = mapping.mode_ranks.numel()
    block_keys = block_rows * parent_count + block_cols
    unique_blocks, block_inverse = torch.unique(block_keys, sorted=True, return_inverse=True)
    block_squared = torch.zeros(unique_blocks.numel(), device=operator.device, dtype=torch.float64)
    block_squared.index_add_(0, block_inverse, residual.square())
    block_norm = torch.sqrt(block_squared)
    defect_rows = torch.div(unique_blocks, parent_count, rounding_mode="floor")
    defect_cols = torch.remainder(unique_blocks, parent_count)
    row_sums = torch.zeros(parent_count, device=operator.device, dtype=torch.float64)
    col_sums = torch.zeros_like(row_sums)
    row_sums.index_add_(0, defect_rows, block_norm)
    col_sums.index_add_(0, defect_cols, block_norm)
    block_bound = torch.sqrt(row_sums.max() * col_sums.max()) if block_norm.numel() else torch.zeros((), device=operator.device, dtype=torch.float64)
    stage_bound = torch.minimum(block_bound + numerical_allowance, operator.norm_upper)
    composed_bound = torch.minimum(
        operator.source_norm_upper,
        operator.composed_defect_bound + stage_bound,
    )

    stored_operator = _tensor_bytes(a_rows, a_cols, a_values, mapping.output_reference)
    next_operator = SparseSymmetricOperator(
        output_dimension, a_rows, a_cols, a_values, mapping.output_reference,
        operator.norm_upper, operator.source_norm_upper, composed_bound,
        stored_operator,
        {
            "construction": "block_sparse_congruence",
            "input_nnz": nnz,
            "padded_A_contributions": a_contributions,
            "active_A_contributions": actual_a_contributions,
            "parent_pair_entries_sorted": nnz,
            "coalesced_parent_blocks": coalesced_parent_blocks,
            "output_block_slots_examined": output_block_slots,
            "coalesced_coo_slots": a_values.numel(),
            "padded_M_contributions": nnz * rpad,
            "active_M_contributions": active_m_contributions,
            "AU_contributions": au_contributions,
            "residual_coalesced_nnz": residual.numel(),
            "first_preflight_bytes": first_preflight,
            "second_preflight_bytes": second_preflight,
            "stored_bytes": stored_operator,
            "precision": "float64; composed bound carries original incidence norm only through recorded isometries",
        },
    )
    _validated(
        torch.linalg.vector_norm(
            apply_operator(
                next_operator, mapping.output_reference, max_bytes=max_bytes
            )
        ) <= 50 * numerical_allowance,
        "transported operator lost stationary reference",
    )

    constant_modes = mapping.mode_offsets[:-1] + mapping.constant_local_indices
    is_constant = torch.zeros(output_dimension, device=operator.device, dtype=torch.bool)
    is_constant[constant_modes] = True
    mass_keep = is_constant[a_rows] & is_constant[a_cols]
    mass_rows = mapping.output_mode_owners[a_rows[mass_keep]]
    mass_cols = mapping.output_mode_owners[a_cols[mass_keep]]
    mass_s = mapping.output_reference[constant_modes]
    mass_values = a_values[mass_keep] * mass_s[mass_rows] / mass_s[mass_cols]
    mass_rows, mass_cols, mass_values = _coalesce(
        mass_rows, mass_cols, mass_values, parent_count
    )
    mass_pi = mass_s.square()
    column_sum = torch.zeros(parent_count, device=operator.device, dtype=torch.float64)
    column_sum.index_add_(0, mass_cols, mass_values)
    stationary = torch.zeros_like(column_sum)
    stationary.index_add_(0, mass_rows, mass_values * mass_pi[mass_cols])
    offdiag = mass_rows != mass_cols
    minimum_offdiag = mass_values[offdiag].min() if offdiag.any() else torch.zeros((), device=operator.device, dtype=torch.float64)
    _validated(minimum_offdiag >= -numerical_allowance, "constant block is not a positive mass generator")
    _validated(torch.max(torch.abs(column_sum)) <= 50 * numerical_allowance, "mass generator is not column conservative")
    _validated(torch.max(torch.abs(stationary)) <= 50 * numerical_allowance, "mass generator does not preserve its reference")
    mass_stored = _tensor_bytes(mass_rows, mass_cols, mass_values, mass_pi, constant_modes)
    mass = PositiveMassCOO(
        mass_rows, mass_cols, mass_values, mass_pi, constant_modes,
        column_sum, stationary, minimum_offdiag, mass_stored,
    )
    total_stored = stored_operator + mass_stored + _tensor_bytes(
        defect_rows, defect_cols, block_norm
    )
    if total_stored + operator.stored_bytes + mapping.stored_bytes > max_bytes:
        raise MemoryError("transported sparse operator storage exceeds capacity")
    work = dict(next_operator.work)
    work.update(
        defect_blocks=block_norm.numel(),
        mass_nnz=mass_values.numel(),
        total_result_stored_bytes=total_stored,
        block_bound=float(block_bound.detach().cpu()),
        stage_bound=float(stage_bound.detach().cpu()),
        composed_bound=float(composed_bound.detach().cpu()),
        scaling_qualification="linear only for fixed local widths and sparse interacting parent blocks; dense block worst case retained",
        budget=budget.receipt(),
    )
    return BlockTransportResult(
        next_operator, mass, defect_rows, defect_cols, block_norm,
        stage_bound, work,
    )


__all__ = [
    "BlockIsometry", "BlockTransportResult", "PositiveMassCOO",
    "SparseSymmetricOperator", "apply_down", "apply_operator", "apply_up",
    "build_block_isometry", "incidence_operator", "transport_block_operator",
]
