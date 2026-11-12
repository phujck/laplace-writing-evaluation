"""spans.py - the columnar span table. Span identity is bytes and offsets, and nothing else.

B.1: ``span_id = chash({source_content_hash, start, end, segmenter_id, seg_version})``, and "no
encoder id, generation id, pour handle, fibre name, clock value or model name may appear in the
hashed field set". ``atlas.schema.Span.compute_id`` already implements exactly that field set,
so it is REUSED here rather than re-derived - the record layer and the existing schema layer
cannot drift apart if there is one function.

What is new is the columnar form. ``schema.Span`` is one Python object per span, which is the
right shape for a manifest and the wrong shape for a hundred thousand turns: the numeric path
needs ``(blob_ord, start, end)`` as int64 tensors so a witness address can be gathered, masked
and scattered with the rows that carry it. This table is that form; ``span_id`` is minted on
demand for the spans a caller actually names.

The storage underneath it RESERVES rather than chunks (``_Growable``, ``_GrowableHost``), and
that is a measured correction, not a preference: the chunk list this replaces made an append
O(1) and the next read O(everything stored), so an ingest paid for the whole table once per
item. Two constants appear here and neither is tuned on an outcome: ``_GROWTH`` is any factor
above 1 (which is what makes an append amortised O(1)), fixed at 1.5 so the reserved slack is
at most half the live array, because peak device bytes is a reported field; ``_MIN_CAPACITY``
is the first reservation, so that the ingester's small per-turn appends do not each reallocate.
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np
import torch

from ..schema import Span
from .device import require_device

__all__ = ["SpanTable"]

# The growth factor of every append-only buffer in the record. 1.5 rather than 2 because the
# tables are device-resident and a reported peak device figure pays for the slack: 1.5 bounds
# the waste at 50% of the live array while keeping the amortised cost of an append O(1).
_GROWTH = 1.5
_MIN_CAPACITY = 1024


class _Growable:
    """An append-only device buffer that grows by RESERVING, so a read is a view and not a copy.

    MEASURED 2026-09-22, and it is why this class exists. The chunk-list form it replaces was
    O(1) per append and O(total) per READ: every reader (``SpanTable.columns``,
    ``TypedTable.column``, ``witness_span``, ``global_ordinals``) re-concatenated every chunk
    whenever the row count had moved, and the witness check reads a span address for every
    candidate row - so an ingest of n items paid O(n x total) inside ``torch.cat``. In a 35 s
    profile of 30 LongMemEval haystacks ``torch.cat`` was 3.428 s against 0.325 s at 10
    haystacks: the number of CALLS tripled with the items while the seconds went up 10.5x,
    which is the signature of a per-item pass over everything already stored.

    Reserving instead makes the whole array ``buffer[:count]`` - no allocation and no copy per
    read - and an append amortised O(k) in the rows appended, independent of what is already
    there. That is B.29's item-locality at the level of the columns themselves.
    Complexity: append O(k) amortised, read O(1). Memory: at most ``_GROWTH`` x the live array.
    """

    def __init__(self, device: torch.device, *, width: int = 0,
                 dtype: torch.dtype | None = None) -> None:
        self.device = device
        self.width = width                     # 0 is a 1-D column, w > 0 an [n, w] block
        self.dtype = dtype                     # None: taken from the first block appended
        self._buffer: torch.Tensor | None = None
        self._count = 0

    def _reserve(self, extra: int) -> None:
        need = self._count + extra
        have = 0 if self._buffer is None else int(self._buffer.shape[0])
        if need <= have:
            return
        capacity = max(need, int(have * _GROWTH) + 1, _MIN_CAPACITY)
        shape = (capacity,) if not self.width else (capacity, self.width)
        grown = torch.empty(shape, dtype=self.dtype, device=self.device)
        if self._count and self._buffer is not None:
            grown[:self._count] = self._buffer[:self._count]
        self._buffer = grown

    def append(self, block: torch.Tensor) -> None:
        """Copy one block into the reserved tail. One device-to-device copy. O(k) amortised."""
        rows = int(block.shape[0])
        if not rows:
            return
        if self.dtype is None:
            self.dtype = block.dtype
        self._reserve(rows)
        assert self._buffer is not None
        self._buffer[self._count:self._count + rows] = block
        self._count += rows

    def __len__(self) -> int:
        return self._count

    @property
    def view(self) -> torch.Tensor:
        """The live array. A VIEW of the reserved buffer: no allocation, no copy, no cat."""
        if self._buffer is None:
            shape = (0,) if not self.width else (0, self.width)
            return torch.empty(shape, dtype=self.dtype or torch.int64, device=self.device)
        return self._buffer[:self._count]


class _GrowableHost:
    """The same reservation on the host, for the columns a per-ROW caller reads.

    ``witness.py:145`` reads one span's address for every candidate row, and a one-row
    ``Tensor.tolist()`` is a device synchronisation: 12,971 of them in a 3-haystack ingest,
    12% of a 30-haystack profile. The span table is 24 bytes per span, so it is mirrored here
    and an address is a host lookup. Complexity: append O(k) amortised, read O(1).
    """

    def __init__(self, width: int) -> None:
        self.width = width
        self._buffer = np.empty((0, width), dtype=np.int64)
        self._count = 0

    def append(self, block: np.ndarray) -> None:
        rows = int(block.shape[0])
        if not rows:
            return
        need = self._count + rows
        if need > self._buffer.shape[0]:
            capacity = max(need, int(self._buffer.shape[0] * _GROWTH) + 1, _MIN_CAPACITY)
            grown = np.empty((capacity, self.width), dtype=np.int64)
            grown[:self._count] = self._buffer[:self._count]
            self._buffer = grown
        self._buffer[self._count:need] = block
        self._count = need

    @property
    def view(self) -> np.ndarray:
        return self._buffer[:self._count]


class SpanTable:
    """Append-only columnar spans: blob ordinal, start, end. One row per distinct byte range."""

    def __init__(self, segmenter_id: str, seg_version: str, device: torch.device) -> None:
        self.segmenter_id = segmenter_id
        self.seg_version = seg_version
        self.device = require_device(device)
        self._handles: list[str] = []
        self._handle_index: dict[str, int] = {}
        self._table = _Growable(self.device, width=3, dtype=torch.int64)
        self._host = _GrowableHost(3)
        self._count = 0

    # ---------------------------------------------------------------- writing
    def blob_ordinal(self, content_handle: str) -> int:
        """Ordinal of a content handle in this table's blob list, appending if new. O(1)."""
        found = self._handle_index.get(content_handle)
        if found is None:
            found = len(self._handles)
            self._handles.append(content_handle)
            self._handle_index[content_handle] = found
        return found

    def append(self, blob_ords: list[int], starts: list[int], ends: list[int]) -> torch.Tensor:
        """Append n spans; return their int64 ordinals. Complexity: O(n), one H2D copy.

        Append RESERVES rather than re-concatenates: adding one turn to a million-span table
        copies one row into the buffer's tail and every reader sees a view, which is what makes
        B.29's O(diff) true at this level - the old chunk list made the APPEND O(1) and the next
        READ O(total), so an ingest paid for the whole table once per item.
        """
        if not blob_ords:
            return torch.empty(0, dtype=torch.int64, device=self.device)
        host = np.ascontiguousarray(np.array([blob_ords, starts, ends], dtype=np.int64).T)
        self._host.append(host)
        first = self._count
        self._count += host.shape[0]
        return torch.arange(first, self._count, dtype=torch.int64, device=self.device)

    # ---------------------------------------------------------------- reading
    def __len__(self) -> int:
        return self._count

    @property
    def columns(self) -> torch.Tensor:
        """The [n, 3] int64 device view (blob_ord, start, end). O(rows appended since the last
        read): the spans a caller appended are copied to the device in ONE transfer when the
        device form is first asked for, and never row by row.

        MEASURED 2026-09-22: the ingester appends spans in small groups - 68,894 calls for
        273,794 spans at 30 LongMemEval haystacks - and one host-to-device copy per call cost
        250 microseconds each, 17.3 s of a 72 s profile, because a tiny transfer is dominated by
        its own launch. The device form is only READ by the relation joins and the segment cut,
        a handful of times per ingest, so the transfer belongs there and not in the append.
        """
        pending = self._count - len(self._table)
        if pending > 0:
            self._table.append(torch.from_numpy(
                self._host.view[len(self._table):]).to(self.device))
        return self._table.view

    @property
    def host_columns(self) -> np.ndarray:
        """The same table on the host - what a per-ROW address lookup reads. O(1), no copy."""
        return self._host.view

    def handle(self, blob_ord: int) -> str:
        return self._handles[int(blob_ord)]

    def handles(self) -> tuple[str, ...]:
        return tuple(self._handles)

    def address(self, span_ord: int) -> tuple[str, int, int]:
        """(content_handle, start, end) of one span - the address B.4 re-reads bytes from.

        Read from the host mirror: a one-row ``tolist()`` off the device is a synchronisation,
        and the witness check calls this once per candidate row. O(1), no device traffic.
        """
        row = self._host.view[int(span_ord)]
        return self._handles[int(row[0])], int(row[1]), int(row[2])

    def addresses(self, span_ords: torch.Tensor) -> list[tuple[str, int, int]]:
        """Addresses of many spans, gathered on the host mirror. Complexity: O(k)."""
        picked = self._host.view[span_ords.to(torch.int64).cpu().numpy()]
        return [(self._handles[int(r[0])], int(r[1]), int(r[2])) for r in picked]

    def span_id(self, span_ord: int) -> str:
        """B.1's span id for one span, via ``atlas.schema.Span.compute_id``. O(1)."""
        handle, start, end = self.address(span_ord)
        return Span.compute_id(handle, start, end, self.segmenter_id, self.seg_version)

    def span_ids(self, span_ords: torch.Tensor) -> list[str]:
        return [Span.compute_id(h, s, e, self.segmenter_id, self.seg_version)
                for h, s, e in self.addresses(span_ords)]

    # ------------------------------------------------------------- persistence
    # ``to_arrays``/``from_arrays`` are the host image of this table and its inverse. They are
    # additive: nothing above them changed. The image is what ``record.segments`` writes and
    # reads, and its one non-obvious property is that the blob column is RE-BASED onto the
    # handle list the image carries - so a slice of this table depends on the spans in it and
    # not on how many blobs happened to arrive before them. That is what makes a per-item slice
    # a pure function of that item.
    def to_arrays(self, start: int = 0, stop: int | None = None) -> dict[str, Any]:
        """Host image of spans ``[start, stop)``: [n,3] int64 and the handles it indexes.

        Complexity: O(n), one device->host transfer. Memory: 24 bytes per span on the host.
        """
        stop = self._count if stop is None else stop
        block = self._host.view[start:stop]
        if block.shape[0] == 0:
            return {"columns": np.zeros((0, 3), dtype="<i8"), "handles": ()}
        blob = block[:, 0]
        _, first = np.unique(blob, return_index=True)
        order = blob[np.sort(first)]                      # distinct blob ords, first appearance
        rank = np.argsort(order)
        local = rank[np.searchsorted(order[rank], blob)]
        out = np.empty_like(block)
        out[:, 0] = local
        out[:, 1:] = block[:, 1:]
        return {"columns": np.ascontiguousarray(out, dtype="<i8"),
                "handles": tuple(self._handles[int(o)] for o in order)}

    def from_arrays(self, columns: np.ndarray, handles: Sequence[str]) -> int:
        """Append host spans whose blob column indexes ``handles``. Returns H2D copies (0 or 1).

        ONE host-to-device copy for the whole block, however many items it was concatenated
        from. Complexity: O(n) host re-base plus one transfer.
        """
        if columns.shape[0] == 0:
            return 0
        remap = np.array([self.blob_ordinal(h) for h in handles], dtype=np.int64)
        block = np.array(columns, dtype=np.int64, copy=True)
        block[:, 0] = remap[block[:, 0]]
        self._host.append(np.ascontiguousarray(block))
        self._count += block.shape[0]
        return 1
