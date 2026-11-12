"""File observation faces shared by read models: when a file last changed and where it is, in one spelling.

  iso_utc(ts)          a POSIX timestamp as UTC ``YYYY-MM-DDTHH:MM:SSZ`` (None stays None)
  now_iso()            the current time in that spelling
  mtime(path)          a file's modification time, or None when it cannot be observed
  relative(path, root) the repository-relative POSIX path, or the absolute string for a path that escapes ``root``
                       (never a silent lie about where a file lives)

Standard library only; no import-time effects.
"""
from __future__ import annotations

import time
from pathlib import Path


def iso_utc(ts: float | None) -> str | None:
    if ts is None:
        return None
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def now_iso() -> str:
    """The current time as UTC ``YYYY-MM-DDTHH:MM:SSZ``."""
    return iso_utc(time.time())


def mtime(path: Path) -> float | None:
    try:
        return Path(path).stat().st_mtime
    except OSError:
        return None


def relative(path: Path, root: Path) -> str:
    try:
        return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return str(path)
