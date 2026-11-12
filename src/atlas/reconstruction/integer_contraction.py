"""Exact integer continuation for prepared binary Boolean quotient queries.

Let a child state have a primitive integer leaf distribution ``c_i / T_b``:
the positive ``c_i`` have gcd one and sum to ``T_b``.  A reduced edge ``n/d``
therefore assigns branch leaves ``n*c_i / (d*T_b)``.  Their least common
denominator is

    d*T_b / gcd(n*c_1, ..., n*c_m, d*T_b)
      = d*(T_b/gcd(n,T_b)),

because gcd(c_i)=1 and gcd(n,d)=1.  The parent primitive total is the lcm of
those branch denominators.  This module constructs and validates the resulting
integer edge multipliers before any query executes.  All gcd/lcm products are
checked before multiplication; malformed or unrepresentable states are refused.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import torch
import triton
import triton.language as tl


INT32_MAX = torch.iinfo(torch.int32).max
INT64_MAX = torch.iinfo(torch.int64).max


class IntegerPlanRefusal(RuntimeError):
    """The exact primitive continuation cannot be represented safely."""


@dataclass(frozen=True)
class PrimitiveLayer:
    totals: torch.Tensor
    multipliers: torch.Tensor


@dataclass(frozen=True)
class IntegerContinuationPlan:
    state: Any
    layers: tuple[PrimitiveLayer, ...]
    children: torch.Tensor
    multipliers: torch.Tensor
    state_counts: torch.Tensor
    axes: torch.Tensor
    root_scale: torch.Tensor
    root_state: int
    width: int
    max_cardinality: int
    message_dtype: torch.dtype
    retained_bytes: int
    validation: dict


@dataclass(frozen=True)
class ExactBooleanQueries:
    masks: torch.Tensor
    values: torch.Tensor
    identically_zero: torch.Tensor
    dimension: int
    storage_bytes: int

    @property
    def count(self) -> int:
        return self.masks.numel()


@dataclass(frozen=True)
class IntegerExecutionPlan:
    continuation: IntegerContinuationPlan
    queries: ExactBooleanQueries
    output: torch.Tensor
    retained_bytes: int


@triton.jit
def _direct_int64_partial_kernel(
    codes_ptr,
    masks_ptr,
    values_ptr,
    zero_ptr,
    partial_ptr,
    n_rows,
    n_blocks: tl.constexpr,
    block_rows: tl.constexpr,
):
    query = tl.program_id(0)
    block = tl.program_id(1)
    offsets = block * block_rows + tl.arange(0, block_rows)
    valid = offsets < n_rows
    codes = tl.load(codes_ptr + offsets, mask=valid, other=0)
    mask = tl.load(masks_ptr + query)
    value = tl.load(values_ptr + query)
    forced_zero = tl.load(zero_ptr + query) != 0
    hit = valid & ((codes & mask) == value) & ~forced_zero
    count = tl.sum(hit.to(tl.int64), axis=0)
    tl.store(partial_ptr + query * n_blocks + block, count)


@triton.jit
def _direct_int64_finalize_kernel(
    partial_ptr,
    output_ptr,
    n_blocks: tl.constexpr,
    reduce_block: tl.constexpr,
):
    query = tl.program_id(0)
    offsets = tl.arange(0, reduce_block)
    values = tl.load(partial_ptr + query * n_blocks + offsets, mask=offsets < n_blocks, other=0)
    tl.store(output_ptr + query, tl.sum(values, axis=0))


@triton.jit
def _integer_boolean_kernel(
    children_ptr,
    multiplier_ptr,
    state_count_ptr,
    axis_ptr,
    masks_ptr,
    values_ptr,
    zero_ptr,
    root_scale_ptr,
    output_ptr,
    D: tl.constexpr,
    WIDTH: tl.constexpr,
    MAX_CARD: tl.constexpr,
    BLOCK: tl.constexpr,
    MESSAGE_INT64: tl.constexpr,
    ROOT_STATE: tl.constexpr,
):
    query = tl.program_id(0)
    states = tl.arange(0, BLOCK)
    mask = tl.load(masks_ptr + query)
    value = tl.load(values_ptr + query)
    forced_zero = tl.load(zero_ptr + query) != 0
    if MESSAGE_INT64:
        continuation = tl.full((BLOCK,), 1, tl.int64)
    else:
        continuation = tl.full((BLOCK,), 1, tl.int32)
    for reverse_cut in tl.static_range(D):
        cut = D - 1 - reverse_cut
        state_count = tl.load(state_count_ptr + cut)
        axis = tl.load(axis_ptr + cut)
        constrained = (mask & (1 << axis)) != 0
        wanted = (value >> axis) & 1
        if MESSAGE_INT64:
            accumulated = tl.zeros((BLOCK,), tl.int64)
        else:
            accumulated = tl.zeros((BLOCK,), tl.int32)
        for symbol in tl.static_range(MAX_CARD):
            slot = (cut * WIDTH + states) * MAX_CARD + symbol
            valid = states < state_count
            child = tl.load(children_ptr + slot, mask=valid, other=0)
            child = tl.maximum(child, 0)
            multiplier = tl.load(multiplier_ptr + slot, mask=valid, other=0)
            factor = (~constrained) | (wanted == symbol)
            accumulated += multiplier * factor.to(multiplier.dtype) * tl.gather(continuation, child, axis=0)
        continuation = accumulated
    root = tl.sum(tl.where(states == ROOT_STATE, continuation, 0), axis=0).to(tl.int64)
    result = root * tl.load(root_scale_ptr)
    tl.store(output_ptr + query, tl.where(forced_zero, 0, result))


def _bytes(*tensors: torch.Tensor) -> int:
    return sum(t.numel() * t.element_size() for t in tensors)


def _check(condition: torch.Tensor, message: str) -> None:
    try:
        if not bool(condition.detach().cpu()):
            raise IntegerPlanRefusal(message)
    except RuntimeError as error:
        if isinstance(error, IntegerPlanRefusal):
            raise
        raise IntegerPlanRefusal(message) from error


def _checked_mul(left: torch.Tensor, right: torch.Tensor, message: str) -> torch.Tensor:
    _check((left >= 0).all() & (right > 0).all(), f"{message}: operands must be nonnegative/positive")
    _check(torch.all(left <= INT64_MAX // right), f"{message}: int64 multiplication overflow")
    return left * right


@torch.no_grad()
def build_integer_continuation(
    state: Any,
    *,
    max_width: int = 128,
    max_bytes: int,
) -> IntegerContinuationPlan:
    """Build and validate primitive integer messages for a conditional state."""

    if state.device.type != "cuda":
        raise TypeError("integer continuation requires a CUDA state")
    if state.dimension <= 0 or len(state.layers) != state.dimension:
        raise IntegerPlanRefusal("state layer count is inconsistent")
    axis_order = tuple(int(axis) for axis in state.order)
    if len(axis_order) != state.dimension or sorted(axis_order) != list(range(state.dimension)):
        raise IntegerPlanRefusal("state order must be a permutation of semantic axes")
    if any(int(layer.axis) != axis_order[cut] for cut, layer in enumerate(state.layers)):
        raise IntegerPlanRefusal("layer axes do not agree with state order")
    if any(layer.cardinality != 2 for layer in state.layers):
        raise IntegerPlanRefusal("integer Boolean kernel currently requires binary axes")
    width = max(layer.state_count for layer in state.layers)
    if width > max_width:
        raise IntegerPlanRefusal(f"quotient width {width} exceeds exact fused cap {max_width}")
    root_state = int(state.root_state)
    if root_state < 0 or root_state >= state.layers[0].state_count:
        raise IntegerPlanRefusal("root state is outside the first quotient layer")
    _check(state.total_weight > 0, "total weight must be positive")

    # Refuse retained storage before allocating primitive or padded plan tensors.
    # int64 is the safe upper bound; a later int32 choice can only reduce it.
    layer_bytes_upper = sum(
        layer.state_count * 8 + layer.children.numel() * 8 for layer in state.layers
    )
    packed_bytes_upper = state.dimension * width * 2 * (4 + 8) + state.dimension * 8 + 8
    retained_upper = layer_bytes_upper + packed_bytes_upper
    if retained_upper > max_bytes:
        raise IntegerPlanRefusal(
            f"integer continuation retained preflight requires at most {retained_upper:,} bytes, budget {max_bytes:,}"
        )

    child_totals = torch.ones(1, dtype=torch.int64, device=state.device)
    reversed_primitive: list[PrimitiveLayer] = []
    checked_edges = checked_states = 0
    maximum_total = 1
    maximum_multiplier = 1
    for reverse_cut, layer in enumerate(reversed(state.layers)):
        if layer.children.dtype != torch.int64 or layer.numerators.dtype != torch.int64 or layer.denominators.dtype != torch.int64:
            raise IntegerPlanRefusal("conditional integer topology must use int64")
        supported = layer.numerators > 0
        _check(torch.all(layer.denominators > 0), "edge denominators must be positive")
        _check(torch.all(layer.numerators >= 0), "edge numerators must be nonnegative")
        _check(torch.all(~supported | ((layer.children >= 0) & (layer.children < child_totals.numel()))), "supported child index outside next layer")
        _check(torch.all(~supported | (torch.gcd(layer.numerators, layer.denominators) == 1)), "edge probability is not reduced")
        # Unsupported slots may contain any sentinel.  Mask them before the
        # gather so even a large positive sentinel can never index child state.
        safe_child = torch.where(supported, layer.children, torch.zeros_like(layer.children))
        child = child_totals[safe_child]
        numerator = torch.where(supported, layer.numerators, torch.ones_like(layer.numerators))
        denominator = torch.where(supported, layer.denominators, torch.ones_like(layer.denominators))
        child = torch.where(supported, child, torch.ones_like(child))
        gcd_n_child = torch.gcd(numerator, child)
        branch_denominator = _checked_mul(
            denominator,
            child // gcd_n_child,
            f"cut {state.dimension - 1 - reverse_cut} branch denominator",
        )
        branch_denominator = torch.where(supported, branch_denominator, torch.ones_like(branch_denominator))

        totals = torch.ones(layer.state_count, dtype=torch.int64, device=state.device)
        for symbol in range(layer.cardinality):
            local = branch_denominator[:, symbol]
            gcd_total = torch.gcd(totals, local)
            totals = _checked_mul(
                totals,
                local // gcd_total,
                f"cut {state.dimension - 1 - reverse_cut} lcm",
            )
        quotient = totals[:, None] // branch_denominator
        _check(torch.all(totals[:, None] % branch_denominator == 0), "branch denominator does not divide parent total")
        multipliers = _checked_mul(
            quotient,
            numerator // gcd_n_child,
            f"cut {state.dimension - 1 - reverse_cut} edge multiplier",
        )
        multipliers = torch.where(supported, multipliers, torch.zeros_like(multipliers))
        products = _checked_mul(
            multipliers,
            child,
            f"cut {state.dimension - 1 - reverse_cut} normalization product",
        )
        _check(torch.all(torch.sum(products, dim=1) == totals), "primitive edge multipliers fail normalization")
        reversed_primitive.append(PrimitiveLayer(totals.contiguous(), multipliers.contiguous()))
        child_totals = totals
        checked_edges += int(torch.count_nonzero(supported).detach().cpu())
        checked_states += totals.numel()
        maximum_total = max(maximum_total, int(torch.max(totals).detach().cpu()))
        maximum_multiplier = max(maximum_multiplier, int(torch.max(multipliers).detach().cpu()))

    layers = tuple(reversed(reversed_primitive))
    root_total = layers[0].totals[root_state]
    _check(state.total_weight % root_total == 0, "root primitive total does not divide empirical total weight")
    root_scale = (state.total_weight // root_total).to(torch.int64).reshape(1)
    reconstructed = _checked_mul(root_total.reshape(1), root_scale, "root scale reconstruction")
    _check(reconstructed[0] == state.total_weight, "root scale reconstruction failed")
    message_dtype = torch.int32 if max(maximum_total, maximum_multiplier) <= INT32_MAX else torch.int64
    max_cardinality = 2
    message_size = torch.empty((), dtype=message_dtype).element_size()
    packed_bytes = (
        state.dimension * width * max_cardinality * (4 + message_size)
        + state.dimension * 8
        + 8
    )
    layer_bytes = sum(_bytes(layer.totals, layer.multipliers) for layer in layers)
    retained = packed_bytes + layer_bytes
    if retained > max_bytes:
        raise IntegerPlanRefusal(f"integer continuation requires {retained:,} bytes, budget {max_bytes:,}")

    children = torch.full((state.dimension, width, 2), -1, dtype=torch.int32, device=state.device)
    packed_multipliers = torch.zeros((state.dimension, width, 2), dtype=message_dtype, device=state.device)
    for cut, (source, primitive) in enumerate(zip(state.layers, layers, strict=True)):
        children[cut, : source.state_count] = source.children.to(torch.int32)
        packed_multipliers[cut, : source.state_count] = primitive.multipliers.to(message_dtype)
    state_counts = torch.tensor([layer.state_count for layer in state.layers], dtype=torch.int32, device=state.device)
    axes = torch.tensor(state.order, dtype=torch.int32, device=state.device)
    return IntegerContinuationPlan(
        state=state,
        layers=layers,
        children=children,
        multipliers=packed_multipliers,
        state_counts=state_counts,
        axes=axes,
        root_scale=root_scale,
        root_state=root_state,
        width=width,
        max_cardinality=max_cardinality,
        message_dtype=message_dtype,
        retained_bytes=retained,
        validation={
            "status": "PASS",
            "checked_states": checked_states,
            "checked_supported_edges": checked_edges,
            "maximum_primitive_total": maximum_total,
            "maximum_edge_multiplier": maximum_multiplier,
            "root_primitive_total": int(root_total.detach().cpu()),
            "root_scale": int(root_scale[0].detach().cpu()),
            "message_dtype": str(message_dtype),
            "overflow_policy": "gcd reduction then checked multiply for branch denominator, lcm, multiplier and normalization product",
        },
    )


@torch.no_grad()
def prepare_exact_queries(base_queries: Any, *, identically_zero: torch.Tensor | None = None) -> ExactBooleanQueries:
    masks, values = base_queries.masks, base_queries.values
    if masks.dtype != torch.int32 or values.dtype != torch.int32 or not masks.is_cuda:
        raise TypeError("base Boolean queries must be CUDA int32")
    if identically_zero is None:
        zero = torch.zeros(masks.numel(), dtype=torch.uint8, device=masks.device)
    else:
        if identically_zero.device != masks.device or identically_zero.shape != masks.shape:
            raise ValueError("identically_zero must align with Boolean queries")
        # Validate original values before narrowing.  In particular, 256 must
        # not wrap to uint8 zero and silently become an ordinary query.
        _check(
            torch.all((identically_zero == 0) | (identically_zero == 1)),
            "identically-zero flags must contain only zero or one",
        )
        zero = identically_zero.to(torch.uint8).contiguous()
    return ExactBooleanQueries(masks, values, zero, base_queries.dimension, _bytes(masks, values, zero))


@torch.no_grad()
def prepare_integer_execution(
    continuation: IntegerContinuationPlan,
    queries: ExactBooleanQueries,
    *,
    max_bytes: int,
) -> IntegerExecutionPlan:
    if queries.dimension != continuation.state.dimension or queries.masks.device != continuation.state.device:
        raise ValueError("query chart differs from continuation chart")
    output_bytes = queries.count * 8
    retained = continuation.retained_bytes + queries.storage_bytes + output_bytes
    if retained > max_bytes:
        raise IntegerPlanRefusal(f"integer execution requires {retained:,} bytes, budget {max_bytes:,}")
    output = torch.empty(queries.count, dtype=torch.int64, device=continuation.state.device)
    return IntegerExecutionPlan(continuation, queries, output, retained)


@torch.no_grad()
def integer_boolean_count(plan: IntegerExecutionPlan) -> torch.Tensor:
    continuation = plan.continuation
    block = triton.next_power_of_2(continuation.width)
    _integer_boolean_kernel[(plan.queries.count,)](
        continuation.children,
        continuation.multipliers,
        continuation.state_counts,
        continuation.axes,
        plan.queries.masks,
        plan.queries.values,
        plan.queries.identically_zero,
        continuation.root_scale,
        plan.output,
        D=continuation.state.dimension,
        WIDTH=continuation.width,
        MAX_CARD=continuation.max_cardinality,
        BLOCK=block,
        MESSAGE_INT64=continuation.message_dtype == torch.int64,
        ROOT_STATE=continuation.root_state,
        num_warps=4 if block >= 64 else 2,
    )
    return plan.output


def integer_work(plan: IntegerExecutionPlan) -> dict[str, int | str]:
    state = plan.continuation.state
    q = plan.queries.count
    slots = q * state.dimension * plan.continuation.width * 2
    state_rows = q * sum(layer.state_count for layer in state.layers)
    message_bytes = torch.empty((), dtype=plan.continuation.message_dtype).element_size()
    return {
        "message_dtype": str(plan.continuation.message_dtype),
        "state_rows": state_rows,
        "padded_transition_slots_read": slots,
        "integer_multiplier_products": slots,
        "integer_reduction_additions": q * sum(layer.state_count for layer in state.layers),
        "bytes_read": (
            slots * (4 + message_bytes)
            + q * (4 + 4 + 1)
            + q * state.dimension * 8
            + q * 8  # one int64 root-scale load per query
        ),
        "bytes_written": q * 8,
    }


@torch.no_grad()
def direct_int64_oracle(codes: torch.Tensor, queries: ExactBooleanQueries, *, max_bytes: int) -> torch.Tensor:
    """Independent exact tiled raw-row oracle used only for validation."""

    if codes.dtype != torch.int32 or not codes.is_cuda or codes.ndim != 1:
        raise TypeError("oracle codes must be one CUDA int32 vector")
    if queries.masks.device != codes.device:
        raise ValueError("oracle query device differs")
    block_rows = 1024
    blocks = (codes.numel() + block_rows - 1) // block_rows
    required = queries.count * blocks * 8 + queries.count * 8
    if required > max_bytes:
        raise IntegerPlanRefusal(f"direct int64 oracle requires {required:,} bytes, budget {max_bytes:,}")
    partial = torch.empty((queries.count, blocks), dtype=torch.int64, device=codes.device)
    output = torch.empty(queries.count, dtype=torch.int64, device=codes.device)
    _direct_int64_partial_kernel[(queries.count, blocks)](
        codes,
        queries.masks,
        queries.values,
        queries.identically_zero,
        partial,
        codes.numel(),
        n_blocks=blocks,
        block_rows=block_rows,
        num_warps=4,
    )
    _direct_int64_finalize_kernel[(queries.count,)](
        partial,
        output,
        n_blocks=blocks,
        reduce_block=triton.next_power_of_2(blocks),
        num_warps=4,
    )
    return output


__all__ = [
    "ExactBooleanQueries",
    "IntegerContinuationPlan",
    "IntegerExecutionPlan",
    "IntegerPlanRefusal",
    "build_integer_continuation",
    "direct_int64_oracle",
    "integer_boolean_count",
    "integer_work",
    "prepare_exact_queries",
    "prepare_integer_execution",
]
