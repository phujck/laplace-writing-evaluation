"""Specialized CUDA execution for prevalidated binary Boolean product queries.

The recursive kernel consumes the published padded small-width quotient plan but
does not repeat generic factor classification on every call.  The direct kernel
is a competent packed comparator: it reads one 32-bit row code per query and
uses bounded block partials, never a Q-by-N materialization.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import torch
import triton
import triton.language as tl


@dataclass(frozen=True)
class BooleanQueries:
    masks: torch.Tensor
    values: torch.Tensor
    dimension: int
    storage_bytes: int

    @property
    def count(self) -> int:
        return self.masks.numel()


@dataclass(frozen=True)
class PackedDirectPlan:
    codes: torch.Tensor
    weights: torch.Tensor
    queries: BooleanQueries
    partials: torch.Tensor
    output: torch.Tensor
    block_rows: int
    blocks: int
    retained_bytes: int
    workspace_bytes: int


@dataclass(frozen=True)
class RecursiveBooleanPlan:
    small_width_plan: Any
    queries: BooleanQueries
    output: torch.Tensor
    retained_bytes: int


@triton.jit
def _packed_direct_partial_kernel(
    codes_ptr,
    weights_ptr,
    masks_ptr,
    values_ptr,
    partial_ptr,
    n_rows,
    n_blocks: tl.constexpr,
    block_rows: tl.constexpr,
    UNIT_WEIGHTS: tl.constexpr,
):
    query = tl.program_id(0)
    block = tl.program_id(1)
    offsets = block * block_rows + tl.arange(0, block_rows)
    valid = offsets < n_rows
    codes = tl.load(codes_ptr + offsets, mask=valid, other=0)
    mask = tl.load(masks_ptr + query)
    value = tl.load(values_ptr + query)
    hit = valid & ((codes & mask) == value)
    if UNIT_WEIGHTS:
        contribution = hit.to(tl.float32)
    else:
        weights = tl.load(weights_ptr + offsets, mask=valid, other=0.0)
        contribution = tl.where(hit, weights, 0.0)
    count = tl.sum(contribution, axis=0)
    tl.store(partial_ptr + query * n_blocks + block, count)


@triton.jit
def _packed_direct_finalize_kernel(
    partial_ptr,
    output_ptr,
    n_blocks: tl.constexpr,
    reduce_block: tl.constexpr,
):
    query = tl.program_id(0)
    offsets = tl.arange(0, reduce_block)
    values = tl.load(
        partial_ptr + query * n_blocks + offsets,
        mask=offsets < n_blocks,
        other=0.0,
    )
    tl.store(output_ptr + query, tl.sum(values, axis=0))


@triton.jit
def _recursive_boolean_kernel(
    children_ptr,
    probability_ptr,
    state_count_ptr,
    axis_ptr,
    masks_ptr,
    values_ptr,
    output_ptr,
    total_weight_ptr,
    D: tl.constexpr,
    WIDTH: tl.constexpr,
    MAX_CARD: tl.constexpr,
    BLOCK: tl.constexpr,
):
    query = tl.program_id(0)
    states = tl.arange(0, BLOCK)
    mask = tl.load(masks_ptr + query)
    value = tl.load(values_ptr + query)
    continuation = tl.full((BLOCK,), 1.0, tl.float32)
    for reverse_cut in tl.static_range(D):
        cut = D - 1 - reverse_cut
        state_count = tl.load(state_count_ptr + cut)
        axis = tl.load(axis_ptr + cut)
        constrained = (mask & (1 << axis)) != 0
        wanted = (value >> axis) & 1
        accumulated = tl.zeros((BLOCK,), tl.float32)
        for symbol in tl.static_range(MAX_CARD):
            slot = (cut * WIDTH + states) * MAX_CARD + symbol
            valid = states < state_count
            child = tl.load(children_ptr + slot, mask=valid, other=0)
            child = tl.maximum(child, 0)
            probability = tl.load(probability_ptr + slot, mask=valid, other=0.0)
            factor = (~constrained) | (wanted == symbol)
            accumulated += probability * factor.to(tl.float32) * tl.gather(continuation, child, axis=0)
        continuation = accumulated
    root = tl.sum(tl.where(states == 0, continuation, 0.0), axis=0)
    tl.store(output_ptr + query, root * tl.load(total_weight_ptr))


def tensor_bytes(*tensors: torch.Tensor) -> int:
    return sum(t.numel() * t.element_size() for t in tensors)


@torch.no_grad()
def pack_binary_rows(rows: torch.Tensor) -> torch.Tensor:
    if not isinstance(rows, torch.Tensor) or not rows.is_cuda or rows.ndim != 2:
        raise TypeError("rows must be one CUDA [N,D] tensor")
    if rows.shape[1] <= 0 or rows.shape[1] > 30:
        raise ValueError("packed comparator supports 1..30 binary axes")
    values = rows.to(torch.int32)
    torch._assert_async(torch.all((values == 0) | (values == 1)), "rows must be binary")
    shifts = torch.arange(rows.shape[1], device=rows.device, dtype=torch.int32)
    return torch.sum(values << shifts, dim=1, dtype=torch.int32).contiguous()


@torch.no_grad()
def prepare_boolean_queries(masks: torch.Tensor, values: torch.Tensor, *, dimension: int) -> BooleanQueries:
    if dimension <= 0 or dimension > 30:
        raise ValueError("dimension must be in 1..30")
    if not isinstance(masks, torch.Tensor) or not isinstance(values, torch.Tensor):
        raise TypeError("masks and values must be tensors")
    if not masks.is_cuda or masks.device != values.device or masks.shape != values.shape or masks.ndim != 1:
        raise ValueError("masks and values must be aligned CUDA vectors")
    packed_masks = masks.to(torch.int32).contiguous()
    packed_values = values.to(torch.int32).contiguous()
    allowed = (1 << dimension) - 1
    torch._assert_async(torch.all((packed_masks & ~allowed) == 0), "query mask exceeds dimension")
    torch._assert_async(torch.all((packed_values & ~packed_masks) == 0), "query value outside mask")
    return BooleanQueries(packed_masks, packed_values, dimension, tensor_bytes(packed_masks, packed_values))


def direct_workspace_bytes(n_rows: int, queries: int, *, block_rows: int = 1024) -> int:
    blocks = math.ceil(n_rows / block_rows)
    return queries * blocks * 4 + queries * 4


@torch.no_grad()
def prepare_direct(
    codes: torch.Tensor,
    queries: BooleanQueries,
    *,
    max_bytes: int,
    block_rows: int = 1024,
    weights: torch.Tensor | None = None,
) -> PackedDirectPlan:
    if codes.dtype != torch.int32 or not codes.is_cuda or codes.ndim != 1:
        raise TypeError("codes must be one CUDA int32 vector")
    if queries.masks.device != codes.device:
        raise ValueError("query and row devices differ")
    if weights is None:
        packed_weights = torch.empty(0, dtype=torch.float32, device=codes.device)
    else:
        if weights.device != codes.device or weights.ndim != 1 or weights.numel() != codes.numel():
            raise ValueError("weights must align with packed codes")
        packed_weights = weights.to(torch.float32).contiguous()
        torch._assert_async(torch.all(packed_weights > 0), "direct weights must be positive")
    if block_rows != 1024:
        raise ValueError("the validated direct tile is 1024 rows")
    blocks = math.ceil(codes.numel() / block_rows)
    workspace = direct_workspace_bytes(codes.numel(), queries.count, block_rows=block_rows)
    retained = tensor_bytes(codes, packed_weights, queries.masks, queries.values) + workspace
    if retained > max_bytes:
        raise MemoryError(f"packed direct plan requires {retained:,} bytes, budget {max_bytes:,}")
    partials = torch.empty((queries.count, blocks), dtype=torch.float32, device=codes.device)
    output = torch.empty(queries.count, dtype=torch.float32, device=codes.device)
    return PackedDirectPlan(codes, packed_weights, queries, partials, output, block_rows, blocks, retained, workspace)


@torch.no_grad()
def packed_direct_count(plan: PackedDirectPlan) -> torch.Tensor:
    _packed_direct_partial_kernel[(plan.queries.count, plan.blocks)](
        plan.codes,
        plan.weights if plan.weights.numel() else plan.codes,
        plan.queries.masks,
        plan.queries.values,
        plan.partials,
        plan.codes.numel(),
        n_blocks=plan.blocks,
        block_rows=plan.block_rows,
        UNIT_WEIGHTS=plan.weights.numel() == 0,
        num_warps=4,
    )
    reduce_block = triton.next_power_of_2(plan.blocks)
    _packed_direct_finalize_kernel[(plan.queries.count,)](
        plan.partials,
        plan.output,
        n_blocks=plan.blocks,
        reduce_block=reduce_block,
        num_warps=4,
    )
    return plan.output


@torch.no_grad()
def prepare_recursive_boolean(small_width_plan: Any, queries: BooleanQueries, *, max_bytes: int) -> RecursiveBooleanPlan:
    state = small_width_plan.state
    if state.dimension != queries.dimension or state.device != queries.masks.device:
        raise ValueError("query chart differs from quotient chart")
    if max(state.cardinalities) != 2 or min(state.cardinalities) != 2:
        raise ValueError("specialized recursive path requires binary axes")
    if small_width_plan.probabilities.dtype != torch.float32:
        raise TypeError("specialized recursive path requires float32 probabilities")
    retained = small_width_plan.allocated_bytes + queries.storage_bytes + queries.count * 4
    if retained > max_bytes:
        raise MemoryError(f"recursive Boolean plan requires {retained:,} bytes, budget {max_bytes:,}")
    output = torch.empty(queries.count, dtype=torch.float32, device=state.device)
    return RecursiveBooleanPlan(small_width_plan, queries, output, retained)


@torch.no_grad()
def recursive_boolean_count(plan: RecursiveBooleanPlan) -> torch.Tensor:
    packed = plan.small_width_plan
    block = triton.next_power_of_2(packed.width)
    if block > 128:
        raise ValueError("recursive Boolean kernel width exceeds validated cap 128")
    _recursive_boolean_kernel[(plan.queries.count,)](
        packed.children,
        packed.probabilities,
        packed.state_counts,
        packed.axes,
        plan.queries.masks,
        plan.queries.values,
        plan.output,
        packed.state.total_weight.to(torch.float32),
        D=packed.state.dimension,
        WIDTH=packed.width,
        MAX_CARD=packed.max_cardinality,
        BLOCK=block,
        num_warps=4 if block >= 64 else 2,
    )
    return plan.output


def direct_work(plan: PackedDirectPlan) -> dict[str, int]:
    q, n, blocks = plan.queries.count, plan.codes.numel(), plan.blocks
    return {
        "row_codes_read": q * n,
        "predicate_bitwise_and": q * n,
        "predicate_equalities": q * n,
        "reduction_additions": q * ((n - blocks) + max(blocks - 1, 0)),
        "partial_values_written": q * blocks,
        "weight_values_read": 0 if plan.weights.numel() == 0 else q * n,
        "bytes_read": q * n * (4 if plan.weights.numel() == 0 else 8) + q * blocks * 8 + q * blocks * 4,
        "bytes_written": q * blocks * 4 + q * 4,
    }


def recursive_work(plan: RecursiveBooleanPlan) -> dict[str, int]:
    state = plan.small_width_plan.state
    q = plan.queries.count
    state_rows = q * sum(layer.state_count for layer in state.layers)
    slots = q * sum(layer.state_count * layer.cardinality for layer in state.layers)
    supported = q * sum(int(torch.count_nonzero(layer.numerators)) for layer in state.layers)
    # The kernel reads padded children/probabilities for every query.  Axis and
    # state-count metadata are one scalar each per layer and query.
    padded_slots = q * state.dimension * plan.small_width_plan.width * plan.small_width_plan.max_cardinality
    return {
        "state_rows": state_rows,
        "dense_transition_slots": slots,
        "supported_transitions": supported,
        "padded_transition_slots_read": padded_slots,
        "probability_multiplies": padded_slots,
        "factor_predicates": padded_slots,
        "reduction_additions": q * sum(layer.state_count * (layer.cardinality - 1) for layer in state.layers),
        "bytes_read": padded_slots * 8 + q * 8 + q * state.dimension * 8,
        "bytes_written": q * 4,
    }


__all__ = [
    "BooleanQueries",
    "PackedDirectPlan",
    "RecursiveBooleanPlan",
    "direct_work",
    "direct_workspace_bytes",
    "pack_binary_rows",
    "packed_direct_count",
    "prepare_boolean_queries",
    "prepare_direct",
    "prepare_recursive_boolean",
    "recursive_boolean_count",
    "recursive_work",
    "tensor_bytes",
]
