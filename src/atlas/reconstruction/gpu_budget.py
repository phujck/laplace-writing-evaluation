"""Shared dynamic CUDA allocation budgets with explicit resident accounting."""
from __future__ import annotations

from dataclasses import asdict, dataclass

import torch


@dataclass(frozen=True)
class GpuBudget:
    max_bytes: int
    source: str
    resident_bytes: int
    free_bytes: int | None
    reusable_pool_bytes: int | None
    total_device_bytes: int | None
    headroom_bytes: int | None

    def receipt(self):
        return asdict(self)


def compute_gpu_budget(
    *,
    resident_bytes: int,
    explicit_max_bytes: int | None = None,
    free_bytes: int | None = None,
    total_device_bytes: int | None = None,
    reserved_bytes: int = 0,
    allocated_bytes: int = 0,
    minimum_headroom_bytes: int = 256 * 1024**2,
    headroom_fraction: float = 0.10,
) -> GpuBudget:
    """Pure integer budget calculation used by CUDA and CPU fixture tests."""

    if resident_bytes < 0 or reserved_bytes < 0 or allocated_bytes < 0:
        raise ValueError("GPU byte counts must be nonnegative")
    if minimum_headroom_bytes < 0 or not 0 <= headroom_fraction < 1:
        raise ValueError("invalid GPU headroom policy")
    if explicit_max_bytes is not None:
        if explicit_max_bytes <= 0:
            raise ValueError("explicit max_bytes must be positive")
        return GpuBudget(
            int(explicit_max_bytes), "explicit", int(resident_bytes),
            None, None, None, None,
        )
    if free_bytes is None or total_device_bytes is None:
        raise ValueError("dynamic budget requires free and total device bytes")
    if free_bytes < 0 or total_device_bytes <= 0 or free_bytes > total_device_bytes:
        raise ValueError("invalid CUDA free/total byte report")
    reusable = max(int(reserved_bytes) - int(allocated_bytes), 0)
    headroom = max(
        int(minimum_headroom_bytes),
        int(total_device_bytes * headroom_fraction),
    )
    allocatable = max(int(free_bytes) + reusable - headroom, 0)
    # The capacity checks include these operation-owned resident buffers on the
    # left side, so only those bytes are added back to express a total budget.
    budget = int(resident_bytes) + allocatable
    return GpuBudget(
        budget, "dynamic_cuda_mem_get_info", int(resident_bytes),
        int(free_bytes), reusable, int(total_device_bytes), headroom,
    )


def resolve_gpu_budget(device, max_bytes=None, *, resident_bytes=0) -> GpuBudget:
    """Resolve one public-operation budget; nested calls receive its integer."""

    if max_bytes is not None:
        return compute_gpu_budget(
            resident_bytes=int(resident_bytes), explicit_max_bytes=int(max_bytes)
        )
    device = torch.device(device)
    if device.type != "cuda":
        raise TypeError("dynamic GPU budget requires a CUDA device")
    free, total = torch.cuda.mem_get_info(device)
    reserved = torch.cuda.memory_reserved(device)
    allocated = torch.cuda.memory_allocated(device)
    return compute_gpu_budget(
        resident_bytes=int(resident_bytes),
        free_bytes=int(free),
        total_device_bytes=int(total),
        reserved_bytes=int(reserved),
        allocated_bytes=int(allocated),
    )


__all__ = ["GpuBudget", "compute_gpu_budget", "resolve_gpu_budget"]
