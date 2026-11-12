"""columns.py - how a declared field becomes an integer column, and back.

The rule this module exists to keep: no Python object survives into the numeric path. A typed
row store is columnar integer tensors; strings are dictionary codes, dates are integer day keys,
timestamps are integer second keys, booleans are 0/1. Every decode is exact, so the record's
identity (B.2's ``chash`` over field VALUES) is computed from the decoded values and is
independent of the store's local code assignment.

THE NULL SENTINEL, and why it is a declared row rather than a literal. The toy fixture declares
it (``evidence/ATLAS_PROGRAMME/lane_c/toy_corpus.py:19-22``): "NULL is the explicit sentinel
(None here; INT32_MIN in the column tensors) ... A null is never zero and never silently
skipped." That rule is generalised here by WIDTH rather than restated for one width: the null
of an integer column is the minimum representable value of its dtype. For int32 that IS
INT32_MIN, so the fixture's convention is reproduced, not replaced; for the int8 and int16
categorical codes the fixture's constant does not fit, and a sentinel that does not fit in the
column is not a sentinel. A real value equal to the sentinel raises ``NullSentinelCollision``
rather than being silently indistinguishable from absence.

Dictionary codes are a STORE ENCODING, not an extractor output. B.28 forbids an extractor from
consulting corpus-level statistics; the extractor here emits values, and the store assigns codes.
That keeps the per-item extraction cache byte-identical across corpora, and it is why a code is
never part of an identity.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Sequence

import torch

from .errors import ClosedColumnViolation, NullSentinelCollision

__all__ = ["ColumnType", "NULL_OF", "DTYPE_OF", "EPOCH_DAY", "day_key", "second_key",
           "date_of_key", "datetime_of_key", "encode_column", "decode_column", "code_width"]

# Column types. Closed set: a declaration naming anything else is refused at freeze time.
COLUMN_TYPES = ("int64", "bool", "date", "timestamp", "enum", "dict_utf8", "span_ref")

ColumnType = str

# The epoch of both integer time keys. Not a tuned constant: it is the origin of the Unix day
# and second counts, chosen so a key is a small integer and the encoding is lossless and total.
EPOCH_DAY = _dt.date(1970, 1, 1)
_EPOCH_ORDINAL = EPOCH_DAY.toordinal()

DTYPE_OF: dict[str, torch.dtype] = {
    "int64": torch.int64,
    "bool": torch.int8,
    "date": torch.int64,
    "timestamp": torch.int64,
    "span_ref": torch.int64,
    # enum / dict_utf8 dtypes depend on the declared vocabulary size; see code_width.
}

# The null of an integer column is the minimum representable value of its dtype (see module
# docstring). These are the four widths this layer uses.
NULL_OF: dict[torch.dtype, int] = {
    torch.int8: -(2 ** 7),
    torch.int16: -(2 ** 15),
    torch.int32: -(2 ** 31),
    torch.int64: -(2 ** 63),
}


def code_width(vocabulary_size: int) -> torch.dtype:
    """The narrowest integer dtype holding ``vocabulary_size`` codes plus its null sentinel.

    Codes are 0..n-1 and the sentinel is the dtype minimum, so the capacity of a width is its
    positive range. Widths are representability, never tuning. Complexity: O(1).
    """
    if vocabulary_size <= 2 ** 7 - 1:
        return torch.int8
    if vocabulary_size <= 2 ** 15 - 1:
        return torch.int16
    if vocabulary_size <= 2 ** 31 - 1:
        return torch.int32
    return torch.int64


def day_key(value: _dt.date | None) -> int | None:
    """A date as days since 1970-01-01. Lossless, total and order-preserving. O(1)."""
    if value is None:
        return None
    if isinstance(value, _dt.datetime):
        value = value.date()
    return value.toordinal() - _EPOCH_ORDINAL


def date_of_key(key: int) -> _dt.date:
    return _dt.date.fromordinal(key + _EPOCH_ORDINAL)


def second_key(value: _dt.datetime | None) -> int | None:
    """A naive datetime as seconds since 1970-01-01T00:00:00. O(1).

    Most sources carry no timezone (LongMemEval '2023/05/20 (Sat) 02:21', the engine's
    '2026-07-14T23:56:02') and none is invented for them: the key is the naive civil second.
    A surface that DOES carry an explicit offset is converted to UTC before the count is taken -
    the offset is applied, never dropped, because dropping it would make two instants that the
    source distinguishes compare equal.
    """
    if value is None:
        return None
    if not isinstance(value, _dt.datetime):
        value = _dt.datetime(value.year, value.month, value.day)
    if value.tzinfo is not None:
        value = value.astimezone(_dt.timezone.utc).replace(tzinfo=None)
    delta = value - _dt.datetime(1970, 1, 1)
    return int(delta.total_seconds())


def datetime_of_key(key: int) -> _dt.datetime:
    return _dt.datetime(1970, 1, 1) + _dt.timedelta(seconds=int(key))


def encode_column(values: Sequence[Any], column_type: str, *, vocabulary: tuple[str, ...] | None,
                  device: torch.device, name: str = "") -> torch.Tensor:
    """Host-side serialisation of one parsed column into its integer tensor.

    This is the ONE place a Python sequence is walked per row, and it is serialisation, not the
    numeric core: it turns already-parsed values into the tensor the numeric core then works on
    with sort/unique/scatter only. Complexity: O(len(values)); one H2D copy.
    """
    dtype = _dtype_for(column_type, vocabulary)
    null = NULL_OF[dtype]
    if column_type in ("enum", "dict_utf8"):
        assert vocabulary is not None
        index = {surface: code for code, surface in enumerate(vocabulary)}
        try:
            keys = [null if v is None else index[v] for v in values]
        except KeyError as exc:                      # a value outside a CLOSED vocabulary
            raise ClosedColumnViolation(
                "value outside the declared vocabulary", column=name, value=exc.args[0],
                vocabulary_size=len(vocabulary)) from exc
    elif column_type == "date":
        keys = [null if v is None else day_key(v) for v in values]
    elif column_type == "timestamp":
        keys = [null if v is None else second_key(v) for v in values]
    elif column_type == "bool":
        keys = [null if v is None else (1 if v else 0) for v in values]
    else:                                             # int64, span_ref
        keys = [null if v is None else int(v) for v in values]
        if any(k == null for k, v in zip(keys, values) if v is not None):
            raise NullSentinelCollision("a value equals the column's null sentinel",
                                        column=name, sentinel=null)
    return torch.tensor(keys, dtype=dtype, device=device)


def decode_column(tensor: torch.Tensor, column_type: str,
                  vocabulary: tuple[str, ...] | None) -> list[Any]:
    """Exact inverse of ``encode_column``; null decodes to ``None``. O(len(tensor)); one D2H."""
    null = NULL_OF[tensor.dtype]
    keys = tensor.tolist()
    if column_type in ("enum", "dict_utf8"):
        assert vocabulary is not None
        return [None if k == null else vocabulary[k] for k in keys]
    if column_type == "date":
        return [None if k == null else date_of_key(k) for k in keys]
    if column_type == "timestamp":
        return [None if k == null else datetime_of_key(k) for k in keys]
    if column_type == "bool":
        return [None if k == null else bool(k) for k in keys]
    return [None if k == null else int(k) for k in keys]


def _dtype_for(column_type: str, vocabulary: tuple[str, ...] | None) -> torch.dtype:
    if column_type in ("enum", "dict_utf8"):
        if vocabulary is None:
            raise ClosedColumnViolation("a coded column needs a vocabulary", type=column_type)
        # An ENUM's vocabulary is closed by the declaration, so its width is fixed once and can
        # be the narrowest that fits. A dict_utf8 dictionary GROWS as items arrive, and a width
        # that changed on the 128th distinct value would silently re-code every stored row - so
        # it is int32 always: capacity 2**31-1, chosen for representability, not tuned.
        return code_width(len(vocabulary)) if column_type == "enum" else torch.int32
    dtype = DTYPE_OF.get(column_type)
    if dtype is None:
        raise ClosedColumnViolation("unknown column type", type=column_type)
    return dtype
