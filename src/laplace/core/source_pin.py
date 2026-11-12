"""Compare an optional full-raw-source pin with an identity already acquired by its owner.

No bytes, paths, parsing, paging, storage or authority are owned here.
"""
from __future__ import annotations

import re


class SourcePinRefusal(ValueError):
    """A malformed pin, absent pinned source, or different admitted source identity."""


def _normalized(value):
    if not isinstance(value, str) or not re.fullmatch(r'(?:sha256:)?[0-9a-fA-F]{64}', value):
        raise SourcePinRefusal('expected_sha256 must be a complete full-source SHA-256 digest.')
    return 'sha256:' + value.removeprefix('sha256:').lower()


def check(source_sha256, payload):
    """Canonical observed identity; compare only when the caller supplied a pin.

    The caller acquires its raw-source identity once, under its own fence/bounds.
    A selected value or page digest must never be supplied as that observation.
    """
    expected = _normalized(payload['expected_sha256']) if 'expected_sha256' in payload else None
    current = _normalized(source_sha256) if source_sha256 is not None else None
    if expected is not None and current is None:
        raise SourcePinRefusal('Source revision conflict: an absent source cannot satisfy the supplied pin; restart explicitly.')
    if expected is not None and expected != current:
        raise SourcePinRefusal('Source revision conflict: the source changed since the pinned read (expected %s, now %s); restart from the first page.' % (expected, current))
    return current
