"""identity.py - B.2's row identity as a FIXED-WIDTH COLUMN, minted once at ingestion.

THE AUTHOR, 2026-09-22: "Why would it need to be mounting handles on every fucking descent.
Does reconstruct need an upfold before every execution?" The answer is no, and this module is
where the no lives. B.2 defines a row's identity as ``chash({kind, fields, witness_span_id})``.
That hash is a function of the row's own content, so it is knowable the moment the row is
admitted - at ingestion, which is the upfold - and nothing a read does can change it. Before
this module the read re-minted it: ``atlas.front.read._row_handles`` called
``TypedRowStore.row_ids`` on every supplied row of every answer (5,084 ``chash`` calls per
read, 0.49-0.81 of the whole read's seconds, measured through the declared entry in wave J2).

So the identity is minted ONCE, in ``TypedRowStore.append_rows``, and stored as four int64
words - the sha256 digest's own 32 bytes, nothing derived and nothing truncated - in a column
of the row's table. It rides into the item's segment like any other column, comes back on the
warm path with the rest of the projection, and an answer's handles are then ONE
``index_select`` over that column. The hex string is reconstructed only when a handle is
serialised, which is off the read's timed path.

It is also the record's ADDRESS. Global ordinals are a property of a projection: they say
where a row sits in the layout this process built, and two processes need not build the same
layout. An identity says which row it is. ``ordinals_of_identity`` is the one join between the
two, and it is fail-closed: an identity the record does not hold comes back as -1 and the
caller refuses by name rather than answering from a smaller record.

Complexity: ``words_of_ids``/``ids_of_words`` are O(k) with one hex conversion for the whole
batch; ``ordinals_of_identity`` is O(N log N + k log N) on the device, one sort and two
searchsorted calls, with no host round trip.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np
import torch

from ..ids import HASH_PREFIX, hex_of
from .errors import MalformedSource

__all__ = ["IDENTITY_WORDS", "IDENTITY_NULL", "words_of_ids", "ids_of_words",
           "ordinals_of_identity"]

# sha256 is 32 bytes; 32 bytes is four int64 words. The whole digest is stored, so the column
# carries B.2's identity itself and not a shortened key that could collide.
IDENTITY_WORDS = 4
# The word a row that has no identity carries. Nothing else in the column can hold it: it is
# the all-ones digest, and a sha256 output equal to it has probability 2^-256.
IDENTITY_NULL = -1


def words_of_ids(ids: Sequence[str]) -> np.ndarray:
    """B.2 identity strings -> an int64 ``[k, 4]`` block. One hex decode for the whole batch."""
    if not len(ids):
        return np.zeros((0, IDENTITY_WORDS), dtype=np.int64)
    digest = "".join([hex_of(value) for value in ids])  # loop-ok: one hex digest per row of the batch, joined once; the decode below is a single call
    raw = bytes.fromhex(digest)
    if len(raw) != len(ids) * 8 * IDENTITY_WORDS:
        raise MalformedSource("a B.2 identity is not a 32-byte sha256 digest",
                              rows=len(ids), bytes=len(raw))
    words = np.frombuffer(raw, dtype=">u8").astype(np.uint64).view(np.int64)
    return np.ascontiguousarray(words.reshape(len(ids), IDENTITY_WORDS))


def ids_of_words(words: np.ndarray | torch.Tensor) -> list[str]:
    """The inverse: an int64 ``[k, 4]`` block -> the B.2 identity strings. SERIALISATION ONLY.

    This is the only place the hex form is rebuilt, and it is called when a handle is written
    out, never inside a read's timed path.
    """
    array = (words.detach().cpu().numpy() if isinstance(words, torch.Tensor)
             else np.asarray(words))
    if not array.size:
        return []
    block = np.ascontiguousarray(array, dtype=np.int64)
    digest = block.view(np.uint64).astype(">u8").tobytes().hex()
    width = 16 * IDENTITY_WORDS
    return [HASH_PREFIX + digest[start:start + width]
            for start in range(0, len(digest), width)]  # loop-ok: one slice per row of the batch, off the timed path


def ordinals_of_identity(record_words: torch.Tensor,
                         needles: torch.Tensor) -> tuple[torch.Tensor, int]:
    """Where each identity sits in THIS process's record. Returns (ordinals, ambiguous).

    ``record_words`` is the record's identity column indexed by GLOBAL ORDINAL and ``needles``
    is any set of identities - a persisted tree's rank order, an answer's handle list. The join
    is one sort of the first word plus two ``searchsorted`` calls; the full 32 bytes are then
    compared, so a first-word collision cannot return a wrong row: it returns -1 and is counted
    in ``ambiguous``, which the caller refuses by name.

    Complexity: O(N log N + k log N) device, no host transfer.
    """
    if not record_words.numel():
        return (torch.full((needles.shape[0],), -1, dtype=torch.int64,
                           device=needles.device), 0)
    key = record_words[:, 0].contiguous()
    order = torch.argsort(key)
    sorted_key = key.index_select(0, order)
    want = needles[:, 0].contiguous()
    left = torch.searchsorted(sorted_key, want)
    right = torch.searchsorted(sorted_key, want, right=True)
    ambiguous = int((right - left > 1).sum())
    position = left.clamp(max=sorted_key.numel() - 1)
    candidate = order.index_select(0, position)
    same = (record_words.index_select(0, candidate) == needles).all(dim=1)
    found = torch.where(same & (right - left == 1), candidate,
                        torch.full_like(candidate, -1))
    return found, ambiguous
