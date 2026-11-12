"""Resolve explicitly exported source locations without rewriting history.

An export records old absolute source names as aliases for checkout-relative
files. It does not infer aliases from basenames, access the author's machine or
claim that a relocated file still has its original bytes after later editing.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path, PurePosixPath, PureWindowsPath

MANIFEST = "writing-portability.json"


@lru_cache(maxsize=8)
def _manifest(path: str, identity: tuple):
    # Identity includes ctime/inode as well as length/mtime, so replacement and
    # same-length edits invalidate this bounded read cache.
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema") != "laplace.writing-portability/1":
        raise ValueError("unknown portable source manifest")
    return data


def _normalised_sha(value) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    raw = value[7:] if value.startswith('sha256:') else value
    raw = raw.lower()
    if len(raw) != 64 or any(ch not in '0123456789abcdef' for ch in raw):
        return None
    return 'sha256:' + raw


def _alias_version(alias, sha256):
    """One recorded spelling may name several exact byte versions.

    The alias's own ``path`` is the PRIMARY target (the current file when the spelling is a
    current checkout address). ``versions`` maps an original ``sha256:`` pin to the explicitly
    pinned companion holding exactly those bytes (an original reading of a file that has since
    changed). A reader that knows the bytes it recorded passes that pin and receives the
    matching version; a reader without a pin, or with a pin no version carries, receives the
    primary target and performs its own hash comparison as before. Nothing is inferred.
    """
    wanted = _normalised_sha(sha256)
    versions = alias.get("versions") if isinstance(alias, dict) else None
    if wanted and isinstance(versions, dict):
        if _normalised_sha(alias.get("original_sha256")) == wanted:
            return alias
        chosen = versions.get(wanted)
        if isinstance(chosen, dict) and isinstance(chosen.get("path"), str):
            return chosen
    return alias


def source_path(value: str, root: Path, *, sha256: str | None = None) -> Path:
    root = Path(root).resolve()
    manifest = root / MANIFEST
    if manifest.is_file():
        stat = manifest.stat()
        if stat.st_size > 4 * 1024 * 1024:
            raise ValueError("portable source manifest exceeds size limit")
        data = _manifest(str(manifest), (stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))
        raw_value = str(value)
        alias = (data.get("source_aliases") or {}).get(raw_value)
        if not alias and raw_value.startswith('\\'):
            alias = (data.get("source_aliases") or {}).get(raw_value.replace('\\', '/'))
        if alias:
            alias = _alias_version(alias, sha256)
        if not alias:
            for old, relative in sorted((data.get("directory_aliases") or {}).items(), key=lambda item: -len(item[0])):
                path_type = PurePosixPath if old.startswith('/') else PureWindowsPath
                spelling = raw_value.replace('\\', '/') if path_type is PurePosixPath else raw_value
                try:
                    suffix = path_type(spelling).relative_to(path_type(old))
                except ValueError:
                    continue
                alias = {"path": (Path(relative) / Path(*suffix.parts)).as_posix()}
                break
        if alias:
            rel = Path(alias["path"])
            if rel.is_absolute() or ".." in rel.parts:
                raise ValueError("portable source alias must remain inside this checkout")
            path = (root / rel).resolve()
            if not path.is_relative_to(root):
                raise ValueError("portable source alias escapes checkout")
            return path
        # Export mode must never silently read a file on the original author's
        # machine just because the independent test happens on that same host.
        path = Path(str(value)).expanduser()
        if _recorded_absolute(str(value)) and not path.resolve().is_relative_to(root):
            raise ValueError("source is not included in this evaluation checkout")
    path = Path(str(value)).expanduser()
    return (root / path if not path.is_absolute() else path).resolve()


def export_root(base: Path) -> Path | None:
    """Find the explicit export boundary containing an already scoped path."""
    path = Path(base).resolve()
    return next((p for p in (path, *path.parents) if (p / MANIFEST).is_file()), None)


def _recorded_absolute(value: str) -> bool:
    return PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute() or value.startswith('\\')


def scoped_path(base: Path, value: str | Path) -> Path | None:
    path = Path(value)
    candidate = (base / path).resolve()
    if candidate.is_relative_to(base.resolve()) and (path.is_absolute() or not _recorded_absolute(str(value))):
        return candidate
    root = export_root(base) if _recorded_absolute(str(value)) else None
    try:
        candidate = source_path(str(value), root) if root else (base / path).resolve()
    except ValueError:
        return None
    return candidate if candidate.is_relative_to(base.resolve()) else None


def relocate_run(job: dict, manuscript: Path) -> dict:
    root = export_root(manuscript)
    if root is None:
        return job
    result = dict(job)
    recorded = {}
    for key in ("producer_base", "cwd", "result_absolute", "stdout_path", "stderr_path", "cancel_path"):
        if result.get(key):
            current = source_path(str(result[key]), root)
            if str(current) != str(result[key]):
                recorded[key] = result[key]
                result[key] = str(current)
    if recorded:
        result["recorded_original_locations"] = recorded
        result["location_resolution"] = "explicit evaluation export aliases; original job and receipt bytes unchanged"
    return result
