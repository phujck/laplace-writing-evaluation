"""THE FANOUT — the pipeline's fan-out width / batch bound (audit §A4).

AUDIT_2026-07-15 §A4 found that every pipeline fan-out was an UNCAPPED
one-agent-per-item dispatch (``parallel(items.map(...))`` at
``project-staged.js:67,99`` and ``project-fixedpoint.js:210,467``): a 125-unit
fleet wired through the pipeline today would be an untested uncapped dispatch.
The bounded/batched discipline existed only in the unshared ``wf_fold_*.mjs``
family — ``pack()`` at ``scripts/wf_fold_up.mjs:44-53`` (greedy char-budget
batches) and ``chunk()`` at ``scripts/wf_fold_person.mjs:29`` (fixed-width
slices). This module lifts THAT precedent to the one calibration surface: the
``fanout`` dial group (``pipeline/dials.py`` ``_DEFAULTS``) names the bound, and
the pipeline reads it here — never a constant buried in a script.

The dial default is UNCAPPED (``fanout.max_width == 0``) — today's exact shape,
so a fresh fleet's dispatch width does not change until a profile opts a real cap
in. ``width(dials) == 0`` means "one batch = the whole list", byte-identical to
the pre-F2 uncapped fan-out.

Pure stdlib. The workflow scripts cannot import this reliably (no filesystem in
the DSL), so each carries a ~4-line inline ``chunkList`` mirror of :func:`chunk`;
THIS module is the Python-side surface (the router, the fleet planners, tests).
"""
from __future__ import annotations

from typing import Any, Callable, Sequence, TypeVar

_T = TypeVar("_T")


def pack(items: Sequence[_T], max_chars: int,
         size_fn: Callable[[_T], int] = len) -> list[list[_T]]:
    """Greedy char-budget batches of ``items``, ORDER-PRESERVING (the port of
    ``wf_fold_up.mjs`` ``pack``, §A4 precedent).

    Each batch's summed ``size_fn(item)`` stays at or below ``max_chars``; the
    next item that would overflow the current (non-empty) batch opens a new one.
    A single item larger than ``max_chars`` becomes its OWN batch (it can never
    fit, so it is never dropped and never wedged in with a neighbour). No batch
    is ever empty; empty ``items`` yields ``[]``.

    ``size_fn`` defaults to ``len`` (the char count of a string item); pass e.g.
    ``lambda it: len(json.dumps(it))`` to budget on the JSON-serialised size, as
    the ``wf_fold`` family does.
    """
    batches: list[list[_T]] = []
    cur: list[_T] = []
    n = 0
    for it in items:
        s = size_fn(it)
        if cur and n + s > max_chars:
            batches.append(cur)
            cur = []
            n = 0
        cur.append(it)
        n += s
    if cur:
        batches.append(cur)
    return batches


def chunk(items: Sequence[_T], width: int) -> list[list[_T]]:
    """Fixed-width slices of ``items`` (the port of ``wf_fold_person.mjs``
    ``chunk``, §A4 precedent). Order-preserving; the last slice may be short.

    ``width <= 0`` is UNCAPPED: the whole list returns as a single batch (the
    fan-out default — byte-identical to today's uncapped dispatch). Empty
    ``items`` yields ``[]`` (never an empty batch). This mirrors the inline
    ``chunkList`` helper carried in the workflow scripts.
    """
    seq = list(items)
    if width <= 0:
        return [seq] if seq else []
    return [seq[i:i + width] for i in range(0, len(seq), width)]


def width(dials: dict[str, Any]) -> int:
    """The fan-out width cap from the ``fanout`` dial group, ``0`` = UNCAPPED.

    Declared default: a missing/empty ``fanout`` group (or an absent ``max_width``)
    reads as ``0`` — today's uncapped behaviour — never a surprise cap.
    """
    fo = (dials or {}).get("fanout") or {}
    return int(fo.get("max_width", 0) or 0)


def batch_max_chars(dials: dict[str, Any]) -> int:
    """The char budget for :func:`pack` from the ``fanout`` dial group. Plain
    default (missing group / key) is the dial default 140000, never 0 — a 0
    budget would put every item in its own batch."""
    fo = (dials or {}).get("fanout") or {}
    return int(fo.get("batch_max_chars", 140000) or 140000)
