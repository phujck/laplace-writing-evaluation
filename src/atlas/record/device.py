"""device.py - the one device policy of the record layer.

The charter: "Host code is parsing, orchestration and serialisation only; no silent NumPy/CPU
fallback in the numeric core." So the numeric core does not *choose* a device - it demands one
and refuses the host. There is no ``if cuda.is_available()`` anywhere in this package; a machine
without a GPU gets a named refusal, not a slower answer that looks the same.

The precedent is ``reconstruction/extension/evidence_selection.py:172-173``, which refuses CPU
metadata codes for the same reason; that refusal is reused here rather than re-authored.
"""

from __future__ import annotations

import torch

from .errors import CpuNumericPathRefused

__all__ = ["require_device", "peak_device_bytes", "reset_peak_device_bytes"]


def require_device(device: str | torch.device | None = None) -> torch.device:
    """The device the numeric core will run on. Refuses the host; never falls back.

    Complexity: O(1).
    """
    resolved = torch.device("cuda" if device is None else device)
    if resolved.type != "cuda":
        raise CpuNumericPathRefused(
            "the record layer's numeric core runs on CUDA only",
            asked_for=str(resolved),
        )
    if not torch.cuda.is_available():
        raise CpuNumericPathRefused(
            "CUDA is not available; the record layer does not fall back to the host",
            asked_for=str(resolved),
        )
    if resolved.index is None:
        resolved = torch.device("cuda", torch.cuda.current_device())
    return resolved


def reset_peak_device_bytes(device: torch.device) -> None:
    """Zero the allocator's high-water mark so a measurement starts before the expensive step."""
    torch.cuda.reset_peak_memory_stats(device)


def peak_device_bytes(device: torch.device) -> int:
    """Peak bytes the caching allocator held since the last reset. Complexity: O(1)."""
    return int(torch.cuda.max_memory_allocated(device))
