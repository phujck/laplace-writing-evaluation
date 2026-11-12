"""Exact compatible-fibre coupling over tagged section routes.

Source content is stored once.  A route is only an incidence from a source to a
compatible tuple of finest section labels, carrying an integer numerator over a
declared common denominator.  The quotient sees categorical labels, never a
unique source-ID axis; sparse postings retain provenance for reached tuples.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import torch

from .gpu_state import ConditionalState, build_state, contract


_I64_MAX = torch.iinfo(torch.int64).max


@dataclass(frozen=True)
class TuplePostings:
    tuple_table: torch.Tensor             # [T, F] categorical labels
    route_to_tuple: torch.Tensor          # [M]
    route_order: torch.Tensor             # [M], grouped by tuple
    tuple_offsets: torch.Tensor           # [T+1]
    route_source_rows: torch.Tensor       # [M], original route order
    route_numerators: torch.Tensor        # [M], original route order
    label_tuple_orders: tuple[torch.Tensor, ...]
    label_tuple_offsets: tuple[torch.Tensor, ...]
    label_tuple_bitsets: tuple[torch.Tensor, ...]
    bitset_word_count: int


@dataclass(frozen=True)
class CouplingState:
    source_ids: torch.Tensor
    source_weights: torch.Tensor
    common_denominator: int
    cardinalities: tuple[int, ...]
    quotient: ConditionalState
    postings: TuplePostings
    route_weights: torch.Tensor           # source_weight[source] * route_numerator

    @property
    def device(self) -> torch.device:
        return self.source_ids.device


@dataclass(frozen=True)
class IntersectionMass:
    routing_numerator: torch.Tensor       # exact integer tagged mass
    common_denominator: int
    total_source_weight: torch.Tensor
    probability: torch.Tensor             # routing_numerator / (D * total_source_weight)
    source_mass_numerator: torch.Tensor   # same numerator; denominator is D
    source_mass_denominator: int
    contract_integer_certified: torch.Tensor
    quotient_work: object


@dataclass(frozen=True)
class IntersectionSupport:
    proven_nonempty: torch.Tensor
    proven_empty: torch.Tensor
    potentially_nonempty: torch.Tensor
    quotient_work: object


@dataclass(frozen=True)
class TupleIntersectionSupport:
    proven_nonempty: torch.Tensor
    proven_empty: torch.Tensor
    potentially_nonempty: torch.Tensor
    tuple_entries_tested: torch.Tensor
    supported_tuples: torch.Tensor
    bitset_word_operations: torch.Tensor
    support_mode: str


@dataclass(frozen=True)
class ReachedPostings:
    source_rows: torch.Tensor
    summed_route_numerators: torch.Tensor
    routes_read: torch.Tensor
    route_indices: torch.Tensor
    route_tuple_indices: torch.Tensor


@dataclass(frozen=True)
class BatchedTupleCandidates:
    tuple_indices: torch.Tensor
    valid: torch.Tensor
    tuple_entries_read: torch.Tensor
    truncated: torch.Tensor


@dataclass(frozen=True)
class TupleMaskSelection:
    """Exact tuple IDs selected by one complete routing mask."""

    tuple_indices: torch.Tensor
    bitset_word_operations: torch.Tensor
    tuple_decode_entries: torch.Tensor
    support_mode: str


def _require_cuda_integer(value: torch.Tensor, name: str, *, rank: int | None = None) -> None:
    if not isinstance(value, torch.Tensor) or not value.is_cuda or value.dtype != torch.int64:
        raise TypeError(f"{name} must be a CUDA int64 tensor")
    if rank is not None and value.ndim != rank:
        raise ValueError(f"{name} must have rank {rank}")


def _validated(condition: torch.Tensor, message: str) -> None:
    """Synchronize one device-computed input predicate without poisoning CUDA."""

    if not bool(condition.detach().item()):
        raise ValueError(message)


def build_coupling(
    source_ids: torch.Tensor,
    route_source_rows: torch.Tensor,
    membership_labels: torch.Tensor,
    route_numerators: torch.Tensor,
    common_denominator: int,
    source_weights: torch.Tensor,
    cardinalities: Sequence[int],
    *,
    max_route_rows: int,
    max_route_bytes: int,
) -> CouplingState:
    """Build an exact route-weighted quotient and tuple-posting CSR on CUDA.

    ``route_numerators`` for every original source sum exactly to
    ``common_denominator``.  There is no implicit product of per-fibre weights.
    """
    _require_cuda_integer(source_ids, "source_ids", rank=1)
    _require_cuda_integer(source_weights, "source_weights", rank=1)
    _require_cuda_integer(route_source_rows, "route_source_rows", rank=1)
    _require_cuda_integer(route_numerators, "route_numerators", rank=1)
    _require_cuda_integer(membership_labels, "membership_labels", rank=2)
    if source_weights.shape != source_ids.shape:
        raise ValueError("source_weights must align with source_ids")
    if route_source_rows.shape != route_numerators.shape or route_source_rows.numel() != membership_labels.shape[0]:
        raise ValueError("route arrays and membership labels must share M rows")
    if membership_labels.device != source_ids.device or source_weights.device != source_ids.device:
        raise ValueError("all coupling tensors must share one CUDA device")
    if (
        not isinstance(common_denominator, int)
        or common_denominator <= 0
        or common_denominator > _I64_MAX
    ):
        raise ValueError("common_denominator must be a positive Python integer")
    if len(cardinalities) != membership_labels.shape[1] or any(int(card) <= 0 for card in cardinalities):
        raise ValueError("cardinalities must specify every positive membership axis")
    if route_source_rows.numel() > max_route_rows:
        raise MemoryError("route row budget exceeded")
    if route_source_rows.numel() == 0 or source_ids.numel() == 0:
        raise ValueError("coupling requires sources and route rows")
    estimated = (route_source_rows.numel() * (membership_labels.shape[1] + 5) * 8)
    if estimated > max_route_bytes:
        raise MemoryError("route byte budget exceeded")

    n = source_ids.numel()
    cards = tuple(int(card) for card in cardinalities)
    card_tensor = torch.tensor(cards, device=source_ids.device, dtype=torch.int64)
    sorted_source_ids = torch.sort(source_ids).values
    unique_source_ids = torch.ones((), device=source_ids.device, dtype=torch.bool) if n <= 1 else torch.all(sorted_source_ids[1:] != sorted_source_ids[:-1])
    _validated(unique_source_ids, "source_ids must be unique")
    _validated(torch.all(source_weights > 0), "source weights must be positive")
    _validated(
        torch.all((route_source_rows >= 0) & (route_source_rows < n)),
        "route source row outside source table",
    )
    _validated(torch.all(route_numerators > 0), "route numerators must be positive")
    _validated(
        torch.all(route_numerators <= common_denominator),
        "route numerator exceeds common denominator",
    )
    _validated(
        torch.all(membership_labels >= 0) & torch.all(membership_labels < card_tensor),
        "membership label outside cardinality",
    )

    routes_per_source = torch.bincount(route_source_rows, minlength=n).to(torch.int64)
    _validated(torch.all(routes_per_source > 0), "every source needs at least one route")
    maximum_routes = torch.max(routes_per_source)
    _validated(
        torch.all(route_numerators <= (_I64_MAX // maximum_routes)),
        "route numerator segment sum can overflow int64",
    )
    numerator_by_source = torch.zeros(n, device=source_ids.device, dtype=torch.int64)
    numerator_by_source.index_add_(0, route_source_rows, route_numerators)
    _validated(
        torch.all(numerator_by_source == common_denominator),
        "route numerators must sum to common denominator for every source",
    )
    _validated(
        torch.all(source_weights <= (_I64_MAX // max(n, 1))),
        "source-weight sum can overflow int64",
    )
    total_source_weight = torch.sum(source_weights)
    _validated(
        total_source_weight <= (_I64_MAX // common_denominator),
        "common-denominator source total can overflow int64",
    )
    routed_source_weights = source_weights.index_select(0, route_source_rows)
    _validated(
        torch.all(routed_source_weights <= (_I64_MAX // route_numerators)),
        "route-weight multiplication overflows int64",
    )
    route_weights = routed_source_weights * route_numerators
    route_count = route_weights.numel()
    _validated(
        torch.max(route_weights) <= (_I64_MAX // max(route_count, 1)),
        "route total can overflow int64",
    )

    tuple_table, route_to_tuple = torch.unique(membership_labels, dim=0, sorted=True, return_inverse=True)
    route_order = torch.argsort(route_to_tuple, stable=True)
    tuple_counts = torch.bincount(route_to_tuple, minlength=tuple_table.shape[0]).to(torch.int64)
    tuple_offsets = torch.cat((torch.zeros(1, device=source_ids.device, dtype=torch.int64), torch.cumsum(tuple_counts, dim=0)))
    label_orders, label_offsets, label_bitsets = [], [], []
    word_count = (tuple_table.shape[0] + 62) // 63
    for axis, cardinality in enumerate(cards):
        labels = tuple_table[:, axis]
        order = torch.argsort(labels, stable=True)
        counts = torch.bincount(labels, minlength=cardinality).to(torch.int64)
        label_orders.append(order)
        label_offsets.append(torch.cat((torch.zeros(1, device=source_ids.device, dtype=torch.int64), torch.cumsum(counts, dim=0))))
        bitsets = torch.zeros(
            (cardinality, word_count), device=source_ids.device, dtype=torch.int64
        )
        tuple_index = torch.arange(tuple_table.shape[0], device=source_ids.device)
        word = torch.div(tuple_index, 63, rounding_mode="floor")
        bit = torch.bitwise_left_shift(
            torch.ones_like(tuple_index, dtype=torch.int64),
            torch.remainder(tuple_index, 63),
        )
        flat = labels * word_count + word
        bitsets.view(-1).index_add_(0, flat, bit)
        label_bitsets.append(bitsets)
    quotient = build_state(membership_labels, cards, row_weights=route_weights)
    return CouplingState(
        source_ids=source_ids,
        source_weights=source_weights,
        common_denominator=common_denominator,
        cardinalities=cards,
        quotient=quotient,
        postings=TuplePostings(
            tuple_table,
            route_to_tuple,
            route_order,
            tuple_offsets,
            route_source_rows,
            route_numerators,
            tuple(label_orders),
            tuple(label_offsets),
            tuple(label_bitsets),
            word_count,
        ),
        route_weights=route_weights,
    )


def intersection_mass(coupling: CouplingState, label_masks: torch.Tensor) -> IntersectionMass:
    """Certified batched routing masses for parent/descendant membership masks.

    ``label_masks[q, fibre, label]`` contains the allowed finest labels supplied
    by ancestry/metadata compilation.  It is intentionally independent of
    source vectors and never constructs a query-by-source score table.
    """
    if not isinstance(label_masks, torch.Tensor) or not label_masks.is_cuda or label_masks.ndim != 3:
        raise TypeError("label_masks must be a CUDA [Q,F,max_card] tensor")
    if label_masks.device != coupling.device or label_masks.shape[1] != len(coupling.cardinalities):
        raise ValueError("label mask fibre axes do not match coupling")
    if label_masks.shape[2] < max(coupling.cardinalities):
        raise ValueError("label mask label axis is too short")
    _validated(
        torch.all((label_masks == 0) | (label_masks == 1)),
        "intersection masks must be Boolean 0/1",
    )
    factors = label_masks.to(dtype=torch.float64)
    result = contract(coupling.quotient, factors)
    _validated(
        torch.all(result.integer_mass_certified),
        "intersection mass lacks an exact integer certificate",
    )
    routing = result.integer_masses
    total_source_weight = torch.sum(coupling.source_weights)
    denominator = coupling.common_denominator * total_source_weight
    probability = routing.to(torch.float64) / denominator.to(torch.float64)
    return IntersectionMass(
        routing_numerator=routing,
        common_denominator=coupling.common_denominator,
        total_source_weight=total_source_weight,
        probability=probability,
        source_mass_numerator=routing,
        source_mass_denominator=coupling.common_denominator,
        contract_integer_certified=result.integer_mass_certified,
        quotient_work=result.work,
    )


def intersection_support(coupling: CouplingState, label_masks: torch.Tensor) -> IntersectionSupport:
    """Conservative frontier support from compact quotient mass intervals."""
    if not isinstance(label_masks, torch.Tensor) or not label_masks.is_cuda or label_masks.ndim != 3:
        raise TypeError("label_masks must be a CUDA [Q,F,max_card] tensor")
    if label_masks.device != coupling.device or label_masks.shape[1] != len(coupling.cardinalities):
        raise ValueError("label mask fibre axes do not match coupling")
    _validated(
        torch.all((label_masks == 0) | (label_masks == 1)),
        "intersection masks must be Boolean 0/1",
    )
    result = contract(coupling.quotient, label_masks.to(dtype=torch.float64))
    lower = result.masses - result.mass_absolute_error_bound
    upper = result.masses + result.mass_absolute_error_bound
    certified = result.integer_mass_certified
    exact = result.integer_masses
    proven_empty = (certified & (exact == 0)) | (upper <= 0)
    proven_nonempty = (certified & (exact > 0)) | (lower > 0)
    return IntersectionSupport(proven_nonempty, proven_empty, ~proven_empty, result.work)


def intersection_support_tuples(
    coupling: CouplingState, label_masks: torch.Tensor
) -> TupleIntersectionSupport:
    """Exact support-only intersection over compact tuple incidence, never sources.

    This path intentionally avoids probability contraction when the caller needs
    only existence.  It tests the stored distinct membership tuples and retains
    the general quotient API for weighted masses.
    """

    if not isinstance(label_masks, torch.Tensor) or not label_masks.is_cuda or label_masks.ndim != 3:
        raise TypeError("label_masks must be a CUDA [Q,F,max_card] tensor")
    if label_masks.device != coupling.device or label_masks.shape[1] != len(coupling.cardinalities):
        raise ValueError("label mask fibre axes do not match coupling")
    if label_masks.shape[2] < max(coupling.cardinalities):
        raise ValueError("label mask label axis is too short")
    _validated(
        torch.all((label_masks == 0) | (label_masks == 1)),
        "intersection masks must be Boolean 0/1",
    )
    tuples = coupling.postings.tuple_table
    bitsets = getattr(coupling.postings, "label_tuple_bitsets", None)
    if bitsets is not None:
        active = None
        word_operations = 0
        for axis, cardinality in enumerate(coupling.cardinalities):
            selected = label_masks[:, axis, :cardinality].to(torch.int64)
            # Label rows are disjoint within one axis, so integer sum is the
            # exact bitwise union without requiring unsupported int64 GEMM.
            allowed = torch.sum(
                selected.unsqueeze(2) * bitsets[axis].unsqueeze(0), dim=1
            )
            active = allowed if active is None else torch.bitwise_and(active, allowed)
            word_operations += selected.shape[0] * cardinality * bitsets[axis].shape[1]
        nonempty = torch.any(active != 0, dim=1)
        return TupleIntersectionSupport(
            proven_nonempty=nonempty,
            proven_empty=~nonempty,
            potentially_nonempty=nonempty,
            tuple_entries_tested=torch.zeros((), device=coupling.device, dtype=torch.int64),
            supported_tuples=torch.full(
                (), -1, device=coupling.device, dtype=torch.int64
            ),
            bitset_word_operations=torch.tensor(
                word_operations, device=coupling.device, dtype=torch.int64
            ),
            support_mode="exact_word_bitset",
        )
    allowed = torch.ones(
        (label_masks.shape[0], tuples.shape[0]),
        device=coupling.device,
        dtype=torch.bool,
    )
    for axis in range(len(coupling.cardinalities)):
        allowed &= label_masks[:, axis, tuples[:, axis]].to(torch.bool)
    nonempty = torch.any(allowed, dim=1)
    return TupleIntersectionSupport(
        proven_nonempty=nonempty,
        proven_empty=~nonempty,
        potentially_nonempty=nonempty,
        tuple_entries_tested=torch.tensor(
            label_masks.shape[0]
            * tuples.shape[0]
            * len(coupling.cardinalities),
            device=coupling.device,
            dtype=torch.int64,
        ),
        supported_tuples=torch.sum(allowed.to(torch.int64)),
        bitset_word_operations=torch.zeros(
            (), device=coupling.device, dtype=torch.int64
        ),
        support_mode="exact_dense_tuple_incidence_compatibility",
    )


def tuples_matching_mask(
    coupling: CouplingState, label_mask: torch.Tensor
) -> TupleMaskSelection:
    """Return exact tuple IDs for one mask through the packed word index.

    The packed index intersects label unions in 63-tuple words.  Decoding the
    final word vector touches each distinct tuple once, but never allocates a
    query-by-tuple incidence table and never visits source rows.
    """

    if not isinstance(label_mask, torch.Tensor) or not label_mask.is_cuda or label_mask.ndim != 2:
        raise TypeError("label_mask must be one CUDA [F,max_card] tensor")
    if label_mask.device != coupling.device or label_mask.shape[0] != len(coupling.cardinalities):
        raise ValueError("label mask fibre axes do not match coupling")
    if label_mask.shape[1] < max(coupling.cardinalities):
        raise ValueError("label mask label axis is too short")
    _validated(
        torch.all((label_mask == 0) | (label_mask == 1)),
        "intersection masks must be Boolean 0/1",
    )
    tuple_count = coupling.postings.tuple_table.shape[0]
    bitsets = getattr(coupling.postings, "label_tuple_bitsets", None)
    if bitsets is not None:
        active = None
        word_operations = 0
        for axis, cardinality in enumerate(coupling.cardinalities):
            selected = label_mask[axis, :cardinality].to(torch.int64)
            allowed = torch.sum(selected[:, None] * bitsets[axis], dim=0)
            active = allowed if active is None else torch.bitwise_and(active, allowed)
            word_operations += cardinality * bitsets[axis].shape[1]
        tuple_indices = torch.arange(tuple_count, device=coupling.device, dtype=torch.int64)
        word = torch.div(tuple_indices, 63, rounding_mode="floor")
        bit = torch.bitwise_left_shift(
            torch.ones_like(tuple_indices), torch.remainder(tuple_indices, 63)
        )
        keep = torch.bitwise_and(active[word], bit) != 0
        return TupleMaskSelection(
            tuple_indices[keep],
            torch.tensor(word_operations, device=coupling.device, dtype=torch.int64),
            torch.tensor(tuple_count, device=coupling.device, dtype=torch.int64),
            "exact_word_bitset_decode",
        )
    # Compatibility for indexes serialized before the word index was added.
    tuples = coupling.postings.tuple_table
    keep = torch.ones(tuple_count, device=coupling.device, dtype=torch.bool)
    for axis in range(len(coupling.cardinalities)):
        keep &= label_mask[axis, tuples[:, axis]].to(torch.bool)
    return TupleMaskSelection(
        torch.arange(tuple_count, device=coupling.device, dtype=torch.int64)[keep],
        torch.zeros((), device=coupling.device, dtype=torch.int64),
        torch.tensor(tuple_count, device=coupling.device, dtype=torch.int64),
        "exact_dense_tuple_decode_compatibility",
    )


def candidate_tuples_for_label(coupling: CouplingState, axis: int, label: int) -> torch.Tensor:
    """CSR lookup for one anchor fibre label; it never scans all tuple rows."""
    if axis < 0 or axis >= len(coupling.cardinalities) or label < 0 or label >= coupling.cardinalities[axis]:
        raise ValueError("axis or label outside coupling cardinality")
    offsets = coupling.postings.label_tuple_offsets[axis]
    order = coupling.postings.label_tuple_orders[axis]
    start, stop = offsets[label], offsets[label + 1]
    return order[start:stop]


def candidate_tuples_batched(coupling: CouplingState, axes: torch.Tensor, labels: torch.Tensor, *, max_candidates: int) -> BatchedTupleCandidates:
    """Bounded device CSR gathers; overflow is explicit rather than silently scanned."""
    _require_cuda_integer(axes, "axes", rank=1)
    _require_cuda_integer(labels, "labels", rank=1)
    if axes.shape != labels.shape or axes.device != coupling.device:
        raise ValueError("axes and labels must align on the coupling device")
    _validated(
        torch.all((axes >= 0) & (axes < len(coupling.cardinalities))),
        "axis outside coupling",
    )
    if max_candidates < 1:
        raise ValueError("max_candidates must be positive")
    q = axes.numel()
    result = torch.full((q, max_candidates), -1, device=coupling.device, dtype=torch.int64)
    valid = torch.zeros((q, max_candidates), device=coupling.device, dtype=torch.bool)
    counts, truncated = [], torch.zeros(q, device=coupling.device, dtype=torch.bool)
    local_positions = torch.arange(max_candidates, device=coupling.device, dtype=torch.int64)
    for axis in range(len(coupling.cardinalities)):
        selected = torch.nonzero(axes == axis, as_tuple=False).flatten()
        local_labels = labels[selected]
        _validated(
            torch.all((local_labels >= 0) & (local_labels < coupling.cardinalities[axis])),
            "label outside coupling cardinality",
        )
        offsets = coupling.postings.label_tuple_offsets[axis]
        starts, stops = offsets[local_labels], offsets[local_labels + 1]
        lengths = stops - starts
        local_valid = local_positions[None, :] < lengths[:, None]
        safe = torch.minimum(starts[:, None] + local_positions[None, :], (stops - 1)[:, None].clamp_min(0))
        result[selected] = torch.where(local_valid, coupling.postings.label_tuple_orders[axis][safe], result[selected])
        valid[selected] = local_valid
        truncated[selected] = lengths > max_candidates
        counts.append(torch.sum(torch.minimum(lengths, torch.full_like(lengths, max_candidates))))
    return BatchedTupleCandidates(result, valid, torch.sum(torch.stack(counts)), truncated)


def filter_tuple_candidates(coupling: CouplingState, tuple_indices: torch.Tensor, label_mask: torch.Tensor) -> torch.Tensor:
    """Check all remaining masks only on candidates obtained from an anchor CSR."""
    _require_cuda_integer(tuple_indices, "tuple_indices", rank=1)
    if label_mask.ndim != 2 or label_mask.shape[0] != len(coupling.cardinalities):
        raise ValueError("one routing label mask must have shape [F,max_card]")
    if tuple_indices.device != coupling.device or label_mask.device != coupling.device:
        raise ValueError("candidate tuples and masks must share coupling device")
    _validated(
        torch.all((label_mask == 0) | (label_mask == 1)),
        "intersection masks must be Boolean 0/1",
    )
    rows = coupling.postings.tuple_table[tuple_indices]
    allowed = torch.ones(rows.shape[0], device=coupling.device, dtype=torch.bool)
    for axis in range(len(coupling.cardinalities)):
        allowed &= label_mask[axis, rows[:, axis]].to(torch.bool)
    return tuple_indices[allowed]


def reached_sources(coupling: CouplingState, reached_tuple_indices: torch.Tensor) -> ReachedPostings:
    """Gather only selected tuple CSR ranges, then deduplicate reached sources."""
    _require_cuda_integer(reached_tuple_indices, "reached_tuple_indices", rank=1)
    if reached_tuple_indices.device != coupling.device:
        raise ValueError("tuple indices must share coupling device")
    count = coupling.postings.tuple_table.shape[0]
    _validated(
        torch.all((reached_tuple_indices >= 0) & (reached_tuple_indices < count)),
        "tuple index outside posting table",
    )
    selected_tuples = torch.unique(reached_tuple_indices, sorted=True)
    starts = coupling.postings.tuple_offsets[selected_tuples]
    stops = coupling.postings.tuple_offsets[selected_tuples + 1]
    lengths = stops - starts
    routes_read = torch.sum(lengths)
    prefix = torch.cumsum(lengths, dim=0) - lengths
    base = torch.repeat_interleave(starts, lengths)
    local = torch.arange(routes_read, device=coupling.device, dtype=torch.int64) - torch.repeat_interleave(prefix, lengths)
    selected_route_indices = coupling.postings.route_order[base + local]
    route_rows = coupling.postings.route_source_rows[selected_route_indices]
    route_numerators = coupling.postings.route_numerators[selected_route_indices]
    unique_rows, inverse = torch.unique(route_rows, sorted=True, return_inverse=True)
    # A reached source may have several selected tags.  Keep its route numerator
    # for diagnostics; source identity is deduplicated only at this boundary.
    summed_numerators = torch.zeros(unique_rows.shape[0], device=coupling.device, dtype=torch.int64)
    summed_numerators.index_add_(0, inverse, route_numerators)
    route_tuple_indices = coupling.postings.route_to_tuple[selected_route_indices]
    return ReachedPostings(
        unique_rows,
        summed_numerators,
        routes_read,
        selected_route_indices,
        route_tuple_indices,
    )


__all__ = ["BatchedTupleCandidates", "CouplingState", "IntersectionMass", "IntersectionSupport", "TupleIntersectionSupport", "TupleMaskSelection", "ReachedPostings", "TuplePostings", "build_coupling", "candidate_tuples_batched", "candidate_tuples_for_label", "filter_tuple_candidates", "intersection_mass", "intersection_support", "intersection_support_tuples", "tuples_matching_mask", "reached_sources"]
