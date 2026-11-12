"""pathsafe.py — the one sid -> filename projection boundary.

A section id is ``kind:slug`` (e.g. ``sec:abstract``). A colon — and the other
Windows/NTFS-illegal filename characters ``* ? " < > |`` — cannot appear in a
tracked path or a Windows checkout ABORTS (friction RW-20260713-203140-001240:
66 banked ``sec:...`` files stranded in the index, unreadable on the author's
box). This module is the single encoder every ``sid -> path`` boundary routes
through:

  * the FILENAME is a PROJECTION: each illegal char becomes ``'_'``;
  * the TRUE id is preserved verbatim inside the payload / manifest / JSON body;
  * a filename is NEVER decoded back into a sid — a reader resolves the true id
    from the payload/manifest and re-encodes it *here* when it needs the path.

Injectivity is ENFORCED, not assumed: :func:`encode_sids_for_dir` raises when
two distinct sids destined for the same directory would collide onto one
filename. (Real ids are ``kind:slug`` with hyphens, so ``':' -> '_'`` is
injective over that domain — but the guard fires rather than trusting it.)
"""
from __future__ import annotations

import re
from typing import Iterable

#: the Windows/NTFS-illegal filename characters — the exact set the close-gate
#: (scripts/close_checklist.py :: check_portable_paths) refuses in any tracked
#: path. Kept here as the ONE definition both the encoder and the gate cite.
ILLEGAL_PATH_CHARS = ':*?"<>|'
_ILLEGAL_RE = re.compile(r'[:*?"<>|]')


def encode_sid_for_path(sid: str) -> str:
    """Project a sid onto a portable filename stem: every NTFS-illegal char ->
    ``'_'``. Deterministic and IDEMPOTENT — an already-clean stem is returned
    byte-for-byte (``encode(encode(sid)) == encode(sid)``), so a reader that
    was handed a clean sid, or the encoded stem itself, resolves to the same
    path. Raises on an empty/non-string sid (a filename with no id is a bug at
    the boundary, never silently a bare extension)."""
    if not isinstance(sid, str) or not sid:
        raise ValueError(
            f"encode_sid_for_path: sid must be a non-empty str, got {sid!r}")
    return _ILLEGAL_RE.sub("_", sid)


def encode_sids_for_dir(sids: Iterable[str]) -> dict[str, str]:
    """Encode a collection of sids bound for the SAME directory to a
    ``{sid: stem}`` map, RAISING on collision — two distinct sids projecting to
    one filename is a hard error (the injectivity guard). Use at any boundary
    that materialises a whole directory of per-sid files."""
    seen: dict[str, str] = {}
    out: dict[str, str] = {}
    for sid in sids:
        stem = encode_sid_for_path(sid)
        prior = seen.get(stem)
        if prior is not None and prior != sid:
            raise ValueError(
                f"sid path collision: {sid!r} and {prior!r} both encode to "
                f"the filename stem {stem!r} — distinct ids may not share a path")
        seen[stem] = sid
        out[sid] = stem
    return out
