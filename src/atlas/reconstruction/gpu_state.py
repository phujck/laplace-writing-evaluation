"""Exact categorical conditional-state quotient with floating GPU contraction.

The state is a reduced ordered probability decision diagram, built from an
integer-weight empirical joint distribution.  A node at cut ``k`` denotes the
conditional law of axes ``order[k:]`` given one observed prefix.  Two nodes are
identified exactly when their normalized outgoing laws (symbol, successor and
rational probability) agree.

The quotient topology and reduced rational transitions are exact in int64 when
their validated sums fit.  ``contract`` evaluates those fractions in float32 or
float64, so its returned expectations and masses carry ordinary floating-point
roundoff; callers requiring integer indicator masses must range-check and use a
unique-rounding/error contract rather than treating the tensor as exact integer
arithmetic.

No Cartesian product is enumerated.  Storage is proportional to the quotient
states times the declared cardinality at each layer; the incompressible fallback
is the observed prefix trie.  The implementation is device agnostic for tests,
but its intended input is a CUDA integer tensor.

An exact append/delete update can change every suffix equivalence class.  The
supported update plan is therefore an immutable snapshot followed by a full
``build_state`` rebuild.  Incremental maintenance needs a separately verified
path-copying/refcount implementation and is deliberately not guessed here.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import time
from typing import Sequence

import torch

try:
    import triton
    import triton.language as tl
except ImportError:  # The exact torch path remains available without Triton.
    triton = None
    tl = None


_INT_DTYPES = {
    torch.int8,
    torch.int16,
    torch.int32,
    torch.int64,
    torch.uint8,
}
_INT64_MAX = torch.iinfo(torch.int64).max


class ExactMassRequired(RuntimeError):
    """Floating contraction cannot uniquely certify an exact integer mass."""


@dataclass(frozen=True)
class ConditionalLayer:
    """One cut of the exact conditional-law quotient.

    Arrays have shape ``[state_count, cardinality]``.  Unsupported symbols have
    child ``-1`` and probability ``0/1``.  Supported probabilities are stored as
    reduced positive integer fractions.  This transition layout also preserves
    what a later amplitude-MPS adapter needs: its local amplitude is
    ``sqrt(numerator / denominator)`` on each deterministic edge.
    """

    axis: int
    cardinality: int
    children: torch.Tensor
    numerators: torch.Tensor
    denominators: torch.Tensor

    @property
    def state_count(self) -> int:
        return self.children.shape[0]

    @property
    def support(self) -> torch.Tensor:
        return self.numerators != 0


@dataclass(frozen=True)
class BuildStats:
    input_rows: int
    unique_rows: int
    raw_prefix_nodes: int
    quotient_states: int
    quotient_slots: int
    sort_passes: int
    explicit_device_synchronizations: int
    elapsed_seconds: float


@dataclass(frozen=True)
class ConditionalState:
    cardinalities: tuple[int, ...]
    order: tuple[int, ...]
    inverse_order: tuple[int, ...]
    total_weight: torch.Tensor
    layers: tuple[ConditionalLayer, ...]
    root_state: int
    build: BuildStats
    update_strategy: str = "immutable snapshot; rebuild exactly after row changes"

    @property
    def device(self) -> torch.device:
        return self.total_weight.device

    @property
    def dimension(self) -> int:
        return len(self.cardinalities)


@dataclass(frozen=True)
class ContractWork:
    """Device-resident counters for work actually submitted by ``contract``."""

    active_state_rows: torch.Tensor
    supported_transitions: torch.Tensor
    dense_transition_slots: torch.Tensor
    factor_multiplies: torch.Tensor
    probability_multiplies: torch.Tensor
    reductions_adds: torch.Tensor
    compacted_query_indices: torch.Tensor


@dataclass(frozen=True)
class ContractResult:
    expectations: torch.Tensor
    masses: torch.Tensor
    total_weight: torch.Tensor
    mass_absolute_error_bound: torch.Tensor
    integer_masses: torch.Tensor
    integer_mass_certified: torch.Tensor
    work: ContractWork


@dataclass(frozen=True)
class SmallWidthPlan:
    """Padded device layout for the fused small-continuation kernel."""

    state: ConditionalState
    children: torch.Tensor
    probabilities: torch.Tensor
    state_counts: torch.Tensor
    cardinalities: torch.Tensor
    axes: torch.Tensor
    axes_long: torch.Tensor
    valid_categories: torch.Tensor
    width: int
    max_cardinality: int
    allocated_bytes: int


@dataclass(frozen=True)
class MarginalResult:
    values: torch.Tensor
    open_axis: int
    state_rows: torch.Tensor
    supported_transitions: torch.Tensor


if triton is not None:

    @triton.jit
    def _small_width_contract_kernel(
        children_ptr,
        probability_ptr,
        state_count_ptr,
        cardinality_ptr,
        axis_ptr,
        factor_ptr,
        output_ptr,
        query_stride,
        axis_stride,
        D: tl.constexpr,
        WIDTH: tl.constexpr,
        MAX_CARD: tl.constexpr,
        BLOCK: tl.constexpr,
        USE_FP64: tl.constexpr,
    ):
        query = tl.program_id(0)
        states = tl.arange(0, BLOCK)
        if USE_FP64:
            continuation = tl.full((BLOCK,), 1.0, tl.float64)
        else:
            continuation = tl.full((BLOCK,), 1.0, tl.float32)
        for reverse_cut in tl.static_range(D):
            cut = D - 1 - reverse_cut
            state_count = tl.load(state_count_ptr + cut)
            cardinality = tl.load(cardinality_ptr + cut)
            axis = tl.load(axis_ptr + cut)
            accumulated = tl.zeros((BLOCK,), continuation.dtype)
            for symbol in tl.static_range(MAX_CARD):
                slot = (cut * WIDTH + states) * MAX_CARD + symbol
                valid = (states < state_count) & (symbol < cardinality)
                child = tl.load(children_ptr + slot, mask=valid, other=0)
                child = tl.maximum(child, 0)
                probability = tl.load(probability_ptr + slot, mask=valid, other=0.0)
                factor = tl.load(
                    factor_ptr + query * query_stride + axis * axis_stride + symbol,
                    mask=symbol < cardinality,
                    other=0.0,
                )
                routed = tl.gather(continuation, child, axis=0)
                accumulated += probability * factor * routed
            continuation = accumulated
        tl.store(output_ptr + query, tl.sum(tl.where(states == 0, continuation, 0.0), axis=0))


def _async_assert(condition: torch.Tensor, message: str) -> None:
    """Queue a device assertion without copying predicate data to the host."""

    torch._assert_async(condition, message)


def _validate_metadata(
    X: torch.Tensor,
    cardinalities: Sequence[int],
    order: Sequence[int] | None,
) -> tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...]]:
    if not isinstance(X, torch.Tensor) or X.ndim != 2:
        raise TypeError("X must be a rank-2 torch tensor")
    if X.dtype not in _INT_DTYPES:
        raise TypeError("X must have an integer dtype")
    n, d = X.shape
    if d == 0:
        raise ValueError("at least one semantic axis is required")
    if n == 0:
        raise ValueError("an empirical probability state needs at least one row")
    cards = tuple(int(c) for c in cardinalities)
    if len(cards) != d or any(c <= 0 for c in cards):
        raise ValueError("cardinalities must contain one positive value per axis")
    axis_order = tuple(range(d)) if order is None else tuple(int(i) for i in order)
    if sorted(axis_order) != list(range(d)):
        raise ValueError("order must be a permutation of the semantic axes")
    inverse = [0] * d
    for cut, axis in enumerate(axis_order):
        inverse[axis] = cut
    return cards, axis_order, tuple(inverse)


def _lexicographic_permutation(X: torch.Tensor, cards: tuple[int, ...]) -> tuple[torch.Tensor, int]:
    """Return a device permutation, using one packed radix key when safe."""

    n, d = X.shape
    product = math.prod(cards)
    if product <= _INT64_MAX:
        key = torch.zeros(n, dtype=torch.int64, device=X.device)
        for axis, card in enumerate(cards):
            key = key * card + X[:, axis]
        return torch.argsort(key), 1

    # Exact overflow-safe fallback.  Stable least-significant-axis passes form a
    # lexicographic order and remain bounded by the number of semantic axes.
    permutation = torch.arange(n, device=X.device)
    for axis in range(d - 1, -1, -1):
        local = torch.argsort(X[permutation, axis], stable=True)
        permutation = permutation[local]
    return permutation, d


def _finish_contract(
    state: ConditionalState,
    expectations: torch.Tensor,
    identically_zero: torch.Tensor,
    deepest: torch.Tensor,
    boolean_factors: torch.Tensor,
    magnitude_bound: torch.Tensor,
    work: ContractWork,
) -> ContractResult:
    compute_dtype = expectations.dtype
    masses = expectations * state.total_weight.to(compute_dtype)

    # Standard gamma_n forward scale for the longest semantic path.  Assumptions
    # for integer certification are: positive normalized integer weights;
    # Boolean factors, so the true mass is a nonnegative integer; no int64 input
    # overflow (validated by build_state); and ordinary correctly-rounded basic
    # arithmetic.  A nonzero empirical event has probability at least
    # 1 / int64_max, so float32/64 Boolean paths do not underflow.  Each layer's
    # charge includes integer-to-float probability conversion/division, two
    # multiplies and its sum reduction; the final scaling is also charged.
    # magnitude_bound covers non-Boolean factor growth, but those queries never
    # receive an integer claim.  A backend-specific reduction proof could tighten
    # this conservative contract; until then bound >= 1/2 requires exact fallback.
    arithmetic_ops = 1 + sum(3 * layer.cardinality for layer in state.layers)
    unit = torch.finfo(compute_dtype).eps
    product = arithmetic_ops * unit
    gamma = product / (1.0 - product) if product < 1.0 else math.inf
    mass_absolute_error_bound = (
        state.total_weight.to(compute_dtype).abs() * magnitude_bound * gamma
    )
    all_ones = (~identically_zero) & (deepest < 0)
    known_integer = identically_zero | all_ones
    uniquely_roundable = boolean_factors & (mass_absolute_error_bound < 0.5)
    integer_mass_certified = known_integer | uniquely_roundable
    # Never cast an uncertified signed/overflowed floating result to int64.  Only
    # the range proved uniquely roundable reaches the conversion; metadata exact
    # zero/total cases are overwritten below from integer tensors.
    rounded = torch.round(
        torch.where(uniquely_roundable, masses, torch.zeros_like(masses))
    ).to(torch.int64)
    integer_masses = torch.where(
        integer_mass_certified, rounded, torch.full_like(rounded, -1)
    )
    integer_masses = torch.where(identically_zero, torch.zeros_like(integer_masses), integer_masses)
    integer_masses = torch.where(
        all_ones, state.total_weight.expand_as(integer_masses), integer_masses
    )
    mass_absolute_error_bound = torch.where(
        known_integer, torch.zeros_like(mass_absolute_error_bound), mass_absolute_error_bound
    )
    return ContractResult(
        expectations=expectations,
        masses=masses,
        total_weight=state.total_weight,
        mass_absolute_error_bound=mass_absolute_error_bound,
        integer_masses=integer_masses,
        integer_mass_certified=integer_mass_certified,
        work=work,
    )


@torch.no_grad()
def build_state(
    X: torch.Tensor,
    cardinalities: Sequence[int],
    order: Sequence[int] | None = None,
    row_weights: torch.Tensor | None = None,
) -> ConditionalState:
    """Build an exact conditional suffix-law quotient.

    ``X`` is ``[N, d]`` categorical data.  Categories must lie in
    ``0 <= X[:, j] < cardinalities[j]``; an unknown value is represented by an
    ordinary explicitly declared category.  Weights are positive integers.

    Construction costs ``O(N log N + d M + sum_k P_k c_k)`` device work with a
    packed sort key, where ``M`` is the number of distinct rows, ``P_k`` the
    number of observed prefixes at cut ``k`` and ``c_k`` the current axis
    cardinality.  The overflow-safe sort fallback is ``O(d N log N)``.  Peak
    retained state is ``O(sum_k S_k c_k)``; construction additionally keeps
    ``O(d M + max_k P_k c_k)`` integer workspace.  It never allocates the full
    product of cardinalities.
    """

    cards, axis_order, inverse = _validate_metadata(X, cardinalities, order)
    synchronizations = 0
    if X.is_cuda:
        torch.cuda.synchronize(X.device)
        synchronizations += 1
    started = time.perf_counter()

    n, d = X.shape
    X64 = X.to(dtype=torch.int64)
    card_device = torch.tensor(cards, dtype=torch.int64, device=X.device)
    _async_assert(torch.all(X64 >= 0) & torch.all(X64 < card_device), "category outside declared cardinality")

    if row_weights is None:
        weights = torch.ones(n, dtype=torch.int64, device=X.device)
    else:
        if not isinstance(row_weights, torch.Tensor) or row_weights.ndim != 1 or row_weights.shape[0] != n:
            raise TypeError("row_weights must be a rank-1 torch tensor with N entries")
        if row_weights.device != X.device or row_weights.dtype not in _INT_DTYPES:
            raise TypeError("row_weights must be an integer tensor on X.device")
        weights = row_weights.to(dtype=torch.int64)
    _async_assert(torch.all(weights > 0), "row weights must be positive")
    _async_assert(torch.max(weights) <= (_INT64_MAX // n), "integer row-weight sum can overflow int64")

    ordered_cards = tuple(cards[i] for i in axis_order)
    ordered_X = X64[:, axis_order]
    permutation, sort_passes = _lexicographic_permutation(ordered_X, ordered_cards)
    sorted_X = ordered_X[permutation]
    sorted_weights = weights[permutation]

    row_start = torch.ones(n, dtype=torch.bool, device=X.device)
    if n > 1:
        row_start[1:] = torch.any(sorted_X[1:] != sorted_X[:-1], dim=1)
    row_ids = torch.cumsum(row_start.to(torch.int64), dim=0) - 1
    unique_X = sorted_X[row_start]
    m = unique_X.shape[0]
    unique_weights = torch.zeros(m, dtype=torch.int64, device=X.device)
    unique_weights.index_add_(0, row_ids, sorted_weights)

    # All unique rows remain lexicographically sorted.  Prefix segment IDs and
    # starts are therefore vectorized scans, one per semantic cut.
    prefix_ids: list[torch.Tensor] = []
    prefix_starts: list[torch.Tensor] = []
    prefix_masses: list[torch.Tensor] = []
    boundary = torch.zeros(m, dtype=torch.bool, device=X.device)
    boundary[0] = True
    for cut in range(d + 1):
        if cut > 0 and m > 1:
            boundary[1:] |= unique_X[1:, cut - 1] != unique_X[:-1, cut - 1]
        ids = torch.cumsum(boundary.to(torch.int64), dim=0) - 1
        starts = torch.nonzero(boundary, as_tuple=False).flatten()
        masses = torch.zeros(starts.shape[0], dtype=torch.int64, device=X.device)
        masses.index_add_(0, ids, unique_weights)
        prefix_ids.append(ids)
        prefix_starts.append(starts)
        prefix_masses.append(masses)

    # At the terminal cut every observed full row has the same empty suffix.
    successor_quotient = torch.zeros(m, dtype=torch.int64, device=X.device)
    reversed_layers: list[ConditionalLayer] = []
    quotient_states = 1  # terminal empty-suffix state
    quotient_slots = 0
    raw_prefix_nodes = sum(t.shape[0] for t in prefix_starts)

    for cut in range(d - 1, -1, -1):
        parent_count = prefix_starts[cut].shape[0]
        card = ordered_cards[cut]
        child_starts = prefix_starts[cut + 1]
        parent_for_edge = prefix_ids[cut][child_starts]
        symbols = unique_X[child_starts, cut]
        edge_mass = prefix_masses[cut + 1]
        parent_mass = prefix_masses[cut][parent_for_edge]
        divisor = torch.gcd(edge_mass, parent_mass)
        reduced_numerator = edge_mass // divisor
        reduced_denominator = parent_mass // divisor

        children = torch.full((parent_count, card), -1, dtype=torch.int64, device=X.device)
        numerators = torch.zeros((parent_count, card), dtype=torch.int64, device=X.device)
        denominators = torch.ones((parent_count, card), dtype=torch.int64, device=X.device)
        flat_slot = parent_for_edge * card + symbols
        children.view(-1)[flat_slot] = successor_quotient
        numerators.view(-1)[flat_slot] = reduced_numerator
        denominators.view(-1)[flat_slot] = reduced_denominator

        signature = torch.stack((children, numerators, denominators), dim=2).reshape(parent_count, 3 * card)
        unique_signature, raw_to_quotient = torch.unique(signature, dim=0, return_inverse=True)
        quotient_count = unique_signature.shape[0]
        decoded = unique_signature.reshape(quotient_count, card, 3)
        layer = ConditionalLayer(
            axis=axis_order[cut],
            cardinality=card,
            children=decoded[:, :, 0].contiguous(),
            numerators=decoded[:, :, 1].contiguous(),
            denominators=decoded[:, :, 2].contiguous(),
        )
        reversed_layers.append(layer)
        successor_quotient = raw_to_quotient
        quotient_states += quotient_count
        quotient_slots += quotient_count * card

    layers = tuple(reversed(reversed_layers))
    # Cut zero has exactly one raw empty prefix, so its unique-signature ID is 0.
    root_state = 0
    if X.is_cuda:
        torch.cuda.synchronize(X.device)
        synchronizations += 1
    elapsed = time.perf_counter() - started
    total_weight = prefix_masses[0][0]
    return ConditionalState(
        cardinalities=cards,
        order=axis_order,
        inverse_order=inverse,
        total_weight=total_weight,
        layers=layers,
        root_state=root_state,
        build=BuildStats(
            input_rows=n,
            unique_rows=m,
            raw_prefix_nodes=raw_prefix_nodes,
            quotient_states=quotient_states,
            quotient_slots=quotient_slots,
            sort_passes=sort_passes,
            explicit_device_synchronizations=synchronizations,
            elapsed_seconds=elapsed,
        ),
    )


@torch.no_grad()
def contract(state: ConditionalState, query_factors: torch.Tensor) -> ContractResult:
    """Contract batched product factors against the empirical probability state.

    ``query_factors[q, j, x]`` is the factor applied when semantic axis ``j``
    has category ``x``.  Indicator factors express conjunctions, signed factors
    express parity/readouts, and all-ones factors marginalize an axis.  Padding
    beyond each declared cardinality is ignored.

    The structural quotient is exact, but division and contraction use
    ``float32`` or ``float64`` according to the input factor dtype.  Returned
    masses therefore are not promised to be bit-exact integers, including for
    indicator factors with otherwise legal int64 row weights.

    Queries with an all-zero factor are returned as zero without traversing the
    state.  An all-ones suffix has exact message one: a query only joins the
    device frontier at its deepest nontrivial factor.  The only Python traversal
    is over semantic layers; query compaction and all node work stay on device.
    No ``Q x N`` record score table is built.  Layer ``k`` temporarily uses
    ``O(A_k S_k c_k)`` arithmetic lanes and ``O(A_k max(S_k,S_{k+1}))`` message
    memory, where ``A_k`` is the number of active queries after suffix skipping.

    Expectations and general signed masses are floating results.  For Boolean
    0/1 factors the result additionally reports a conservative absolute mass
    error bound and an exact-integer certification mask.  Rounding is certified
    only when that bound is below one half; identically-zero and all-ones queries
    are exact directly from the integer state.  Call
    :func:`require_certified_integer_masses` when an application requires counts.
    """

    if not isinstance(query_factors, torch.Tensor) or query_factors.ndim != 3:
        raise TypeError("query_factors must have shape [Q, d, max_cardinality]")
    q, d, max_card = query_factors.shape
    if d != state.dimension or max_card < max(state.cardinalities):
        raise ValueError("query_factors has incompatible semantic dimensions")
    if query_factors.device != state.device or not query_factors.is_floating_point():
        raise TypeError("query_factors must be floating point on state.device")
    _async_assert(torch.all(torch.isfinite(query_factors)), "query factors must be finite")

    compute_dtype = torch.float64 if query_factors.dtype == torch.float64 else torch.float32
    factors = query_factors.to(dtype=compute_dtype)
    device = state.device
    deepest = torch.full((q,), -1, dtype=torch.int64, device=device)
    identically_zero = torch.zeros(q, dtype=torch.bool, device=device)
    boolean_factors = torch.ones(q, dtype=torch.bool, device=device)
    magnitude_bound = torch.ones(q, dtype=compute_dtype, device=device)
    for cut, axis in enumerate(state.order):
        local = factors[:, axis, : state.cardinalities[axis]]
        nontrivial = torch.any(local != 1, dim=1)
        deepest = torch.where(nontrivial, torch.full_like(deepest, cut), deepest)
        identically_zero |= torch.all(local == 0, dim=1)
        boolean_factors &= torch.all((local == 0) | (local == 1), dim=1)
        magnitude_bound *= torch.amax(torch.abs(local), dim=1)
    eligible = ~identically_zero

    counter_zero = torch.zeros((), dtype=torch.int64, device=device)
    active_state_rows = counter_zero.clone()
    supported_transitions = counter_zero.clone()
    dense_transition_slots = counter_zero.clone()
    reductions_adds = counter_zero.clone()
    compacted_query_indices = counter_zero.clone()

    previous: torch.Tensor | None = None
    root_indices: torch.Tensor | None = None
    for cut in range(d - 1, -1, -1):
        layer = state.layers[cut]
        active_mask = eligible & (deepest >= cut)
        active_indices = torch.nonzero(active_mask, as_tuple=False).flatten()
        local_factor = factors[active_indices, layer.axis, : layer.cardinality]
        active_count = torch.sum(active_mask.to(torch.int64))
        compacted_query_indices += active_count

        child_count = 1 if cut == d - 1 else state.layers[cut + 1].state_count
        child_messages = torch.ones_like(local_factor[:, :1]).expand(-1, child_count)
        if previous is not None:
            continuing = deepest[active_indices] > cut
            child_messages = child_messages.clone()
            child_messages[continuing] = previous

        safe_children = torch.clamp_min(layer.children, 0)
        routed = child_messages[:, safe_children.reshape(-1)].reshape(
            -1, layer.state_count, layer.cardinality
        )
        probability = layer.numerators.to(compute_dtype) / layer.denominators.to(compute_dtype)
        previous = torch.sum(
            routed * probability.unsqueeze(0) * local_factor.unsqueeze(1), dim=2
        )
        root_indices = active_indices

        active_state_rows += active_count * layer.state_count
        supported_transitions += active_count * torch.sum(layer.support.to(torch.int64))
        slots = active_count * layer.state_count * layer.cardinality
        dense_transition_slots += slots
        reductions_adds += active_count * layer.state_count * max(layer.cardinality - 1, 0)

    expectations = torch.ones(q, dtype=compute_dtype, device=device)
    expectations[identically_zero] = 0
    if previous is not None and root_indices is not None:
        expectations[root_indices] = previous[:, state.root_state]
    work = ContractWork(
        active_state_rows=active_state_rows,
        supported_transitions=supported_transitions,
        dense_transition_slots=dense_transition_slots,
        factor_multiplies=dense_transition_slots,
        probability_multiplies=dense_transition_slots,
        reductions_adds=reductions_adds,
        compacted_query_indices=compacted_query_indices,
    )
    return _finish_contract(
        state,
        expectations,
        identically_zero,
        deepest,
        boolean_factors,
        magnitude_bound,
        work,
    )


def require_certified_integer_masses(result: ContractResult) -> torch.Tensor:
    """Return exact integer counts or raise when floating rounding is ambiguous."""

    # Keep the certification comparator on the tensor device.  In CUDA use this
    # before a normal stream synchronization/error check at the API boundary.
    try:
        torch._assert_async(
            torch.all(result.integer_mass_certified),
            "query mass lacks a unique integer rounding certificate; use an "
            "exact record/rational fallback",
        )
        if result.integer_masses.is_cuda:
            # Exact-count API boundary: surface the device assertion before a
            # caller consumes the integers.  The comparator itself stays on GPU.
            torch.cuda.synchronize(result.integer_masses.device)
    except RuntimeError as error:
        raise ExactMassRequired(
            "query mass lacks a unique integer rounding certificate; use an "
            "exact record/rational fallback"
        ) from error
    return result.integer_masses


@torch.no_grad()
def prepare_small_width(
    state: ConditionalState,
    *,
    max_width: int = 128,
    max_bytes: int = 16 * 1024 * 1024,
    dtype: torch.dtype = torch.float32,
) -> SmallWidthPlan:
    """Pack a small quotient for one-program-per-query Triton contraction."""

    if triton is None:
        raise RuntimeError("Triton is unavailable; use the torch contraction")
    if state.device.type != "cuda":
        raise ValueError("the fused small-width path requires a CUDA state")
    if dtype not in (torch.float32, torch.float64):
        raise TypeError("fused probabilities support float32 or float64")
    width = max(layer.state_count for layer in state.layers)
    max_cardinality = max(layer.cardinality for layer in state.layers)
    if width > max_width:
        raise ValueError(f"quotient width {width} exceeds fused cap {max_width}")
    d = state.dimension
    slots = d * width * max_cardinality
    allocated = (
        slots * (4 + torch.empty((), dtype=dtype).element_size())
        + d * (3 * 4 + 8)
        + d * max_cardinality
    )
    if allocated > max_bytes:
        raise MemoryError(
            f"small-width plan requires {allocated:,} bytes, above {max_bytes:,}"
        )
    children = torch.full(
        (d, width, max_cardinality), -1, dtype=torch.int32, device=state.device
    )
    probabilities = torch.zeros(
        (d, width, max_cardinality), dtype=dtype, device=state.device
    )
    for cut, layer in enumerate(state.layers):
        states, card = layer.children.shape
        children[cut, :states, :card] = layer.children.to(torch.int32)
        probabilities[cut, :states, :card] = (
            layer.numerators.to(dtype) / layer.denominators.to(dtype)
        )
    axes = torch.tensor(state.order, dtype=torch.int32, device=state.device)
    packed_cardinalities = torch.tensor(
        [layer.cardinality for layer in state.layers],
        dtype=torch.int32,
        device=state.device,
    )
    return SmallWidthPlan(
        state=state,
        children=children,
        probabilities=probabilities,
        state_counts=torch.tensor(
            [layer.state_count for layer in state.layers],
            dtype=torch.int32,
            device=state.device,
        ),
        cardinalities=packed_cardinalities,
        axes=axes,
        axes_long=axes.to(torch.int64),
        valid_categories=(
            torch.arange(max_cardinality, device=state.device).unsqueeze(0)
            < packed_cardinalities.to(torch.int64).unsqueeze(1)
        ),
        width=width,
        max_cardinality=max_cardinality,
        allocated_bytes=allocated,
    )


@torch.no_grad()
def contract_small_width(plan: SmallWidthPlan, query_factors: torch.Tensor) -> ContractResult:
    """Fuse every semantic layer into one Triton program per query.

    This path deliberately scans every compact layer.  It trades suffix skipping
    for one launch and a register-resident continuation vector, and its work
    counters charge that full scan.  The ordinary torch path remains the fallback
    for wide quotients and suffix-heavy batches.
    """

    state = plan.state
    if query_factors.ndim != 3 or query_factors.shape[1] != state.dimension:
        raise ValueError("query_factors must have shape [Q,d,max_cardinality]")
    if query_factors.shape[2] < max(state.cardinalities):
        raise ValueError("query factor physical dimension is too small")
    if query_factors.device != state.device or query_factors.dtype != plan.probabilities.dtype:
        raise TypeError("query factors must match plan device and floating dtype")
    torch._assert_async(torch.all(torch.isfinite(query_factors)), "query factors must be finite")
    q = query_factors.shape[0]
    if q == 0:
        return contract(state, query_factors)

    # One batched metadata analysis replaces per-axis wrapper kernels.  Padding is
    # masked by the plan's declared physical support and cannot affect semantics.
    ordered = query_factors[
        :, plan.axes_long, : plan.max_cardinality
    ]
    valid = plan.valid_categories.unsqueeze(0)
    nontrivial = torch.any((ordered != 1) & valid, dim=2)
    cut_ids = torch.arange(state.dimension, dtype=torch.int64, device=state.device)
    deepest = torch.amax(
        torch.where(nontrivial, cut_ids.unsqueeze(0), torch.full_like(cut_ids, -1)),
        dim=1,
    )
    identically_zero = torch.any(
        torch.all((ordered == 0) | ~valid, dim=2), dim=1
    )
    boolean_factors = torch.all(
        (ordered == 0) | (ordered == 1) | ~valid, dim=(1, 2)
    )
    magnitude_bound = torch.prod(
        torch.amax(torch.where(valid, torch.abs(ordered), 0), dim=2), dim=1
    )

    expectations = torch.empty(q, dtype=query_factors.dtype, device=state.device)
    block = triton.next_power_of_2(plan.width)
    _small_width_contract_kernel[(q,)](
        plan.children,
        plan.probabilities,
        plan.state_counts,
        plan.cardinalities,
        plan.axes,
        query_factors,
        expectations,
        query_factors.stride(0),
        query_factors.stride(1),
        D=state.dimension,
        WIDTH=plan.width,
        MAX_CARD=plan.max_cardinality,
        BLOCK=block,
        USE_FP64=query_factors.dtype == torch.float64,
        num_warps=4 if block >= 64 else 2,
    )
    expectations = torch.where(identically_zero, torch.zeros_like(expectations), expectations)
    expectations = torch.where(
        (~identically_zero) & (deepest < 0), torch.ones_like(expectations), expectations
    )

    query_count = torch.tensor(q, dtype=torch.int64, device=state.device)
    state_rows_per_query = sum(layer.state_count for layer in state.layers)
    slots_per_query = sum(
        layer.state_count * layer.cardinality for layer in state.layers
    )
    support_per_query = torch.zeros((), dtype=torch.int64, device=state.device)
    for layer in state.layers:
        support_per_query += torch.sum(layer.support.to(torch.int64))
    dense_slots = query_count * slots_per_query
    work = ContractWork(
        active_state_rows=query_count * state_rows_per_query,
        supported_transitions=query_count * support_per_query,
        dense_transition_slots=dense_slots,
        factor_multiplies=dense_slots,
        probability_multiplies=dense_slots,
        reductions_adds=query_count
        * sum(layer.state_count * max(layer.cardinality - 1, 0) for layer in state.layers),
        compacted_query_indices=query_count * state.dimension,
    )
    return _finish_contract(
        state,
        expectations,
        identically_zero,
        deepest,
        boolean_factors,
        magnitude_bound,
        work,
    )


@torch.no_grad()
def marginal(
    state: ConditionalState,
    query_factors: torch.Tensor,
    *,
    open_axis: int,
) -> MarginalResult:
    """Return the weighted categorical marginal at one open semantic axis.

    Factors on ``open_axis`` are ignored.  A forward message contracts the
    prefix, a backward message contracts the suffix, and their transition join
    returns one value per category.  Work is ``Q`` times compact states/edges;
    no query-by-record or categorical one-hot document matrix is formed.
    """

    if open_axis < 0 or open_axis >= state.dimension:
        raise ValueError("open_axis is outside the semantic chart")
    if query_factors.ndim != 3 or query_factors.shape[1] != state.dimension:
        raise ValueError("query_factors must have shape [Q,d,max_cardinality]")
    if query_factors.shape[2] < max(state.cardinalities):
        raise ValueError("query factor physical dimension is too small")
    if query_factors.device != state.device or not query_factors.is_floating_point():
        raise TypeError("query factors must be floating point on state.device")
    torch._assert_async(torch.all(torch.isfinite(query_factors)), "query factors must be finite")
    dtype = torch.float64 if query_factors.dtype == torch.float64 else torch.float32
    factors = query_factors.to(dtype)
    q = factors.shape[0]
    open_cut = state.inverse_order[open_axis]

    backward = torch.ones((q, 1), dtype=dtype, device=state.device)
    state_rows = torch.zeros((), dtype=torch.int64, device=state.device)
    transitions = torch.zeros((), dtype=torch.int64, device=state.device)
    for cut in range(state.dimension - 1, open_cut, -1):
        layer = state.layers[cut]
        safe = torch.clamp_min(layer.children, 0)
        routed = backward[:, safe.reshape(-1)].reshape(
            q, layer.state_count, layer.cardinality
        )
        probability = layer.numerators.to(dtype) / layer.denominators.to(dtype)
        local = factors[:, layer.axis, : layer.cardinality]
        backward = torch.sum(
            routed * probability.unsqueeze(0) * local.unsqueeze(1), dim=2
        )
        state_rows += q * layer.state_count
        transitions += q * torch.sum(layer.support.to(torch.int64))

    forward = torch.ones((q, 1), dtype=dtype, device=state.device)
    for cut in range(open_cut):
        layer = state.layers[cut]
        right_dimension = state.layers[cut + 1].state_count
        probability = layer.numerators.to(dtype) / layer.denominators.to(dtype)
        local = factors[:, layer.axis, : layer.cardinality]
        contribution = forward.unsqueeze(2) * probability.unsqueeze(0) * local.unsqueeze(1)
        safe = torch.clamp_min(layer.children.reshape(-1), 0)
        targets = (
            torch.arange(q, device=state.device, dtype=torch.int64).unsqueeze(1)
            * right_dimension
            + safe.unsqueeze(0)
        )
        next_flat = torch.zeros(q * right_dimension, dtype=dtype, device=state.device)
        next_flat.index_add_(0, targets.reshape(-1), contribution.reshape(-1))
        forward = next_flat.reshape(q, right_dimension)
        state_rows += q * layer.state_count
        transitions += q * torch.sum(layer.support.to(torch.int64))

    layer = state.layers[open_cut]
    safe = torch.clamp_min(layer.children, 0)
    routed = backward[:, safe.reshape(-1)].reshape(
        q, layer.state_count, layer.cardinality
    )
    probability = layer.numerators.to(dtype) / layer.denominators.to(dtype)
    values = torch.sum(
        forward.unsqueeze(2) * probability.unsqueeze(0) * routed, dim=1
    )
    state_rows += q * layer.state_count
    transitions += q * torch.sum(layer.support.to(torch.int64))
    return MarginalResult(
        values=values,
        open_axis=open_axis,
        state_rows=state_rows,
        supported_transitions=transitions,
    )


__all__ = [
    "BuildStats",
    "ConditionalLayer",
    "ConditionalState",
    "ContractResult",
    "ContractWork",
    "ExactMassRequired",
    "MarginalResult",
    "SmallWidthPlan",
    "build_state",
    "contract",
    "contract_small_width",
    "marginal",
    "prepare_small_width",
    "require_certified_integer_masses",
]
