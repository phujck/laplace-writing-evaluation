"""content_blob.py - provider obligation 1: the bottom of the byte spine.

B.1 addresses every span into "the immutable source blob" and no clause in the contract declares
what that blob IS. Without a named store the spine has no bottom and B.4's witness check has
nothing to re-read. This module is that store: content-addressed, written once, never rewritten.

``content_handle`` is ``sha256:`` + hex over the blob's bytes - ``atlas.ids.hash_bytes``, reused
rather than re-authored, so the record layer and the existing snapshot layer agree on what a
content hash is by construction and not by convention.

Two kinds of blob, one interface:

* an in-memory blob, for a toy corpus or a single JSONL file;
* a FILE-RANGE blob, which holds (path, offset, length) and reads lazily. LongMemEval-S is
  277 MB and one haystack is one blob (B.33); copying 500 haystacks into memory to hash them
  would be the "load the whole file" move the pack forbids. A file-range blob hashes by
  streaming and reads only the window a span asks for.

``ingested_utc`` is recorded beside the blob and is NEVER part of the handle: ``ids.py``'s law
is that no clock enters an identity, and a blob store whose handles move under a clock cannot
address a span tomorrow.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..ids import hash_bytes
from .errors import BlobRewriteRefused

__all__ = ["ContentBlob", "ContentBlobStore"]

_STREAM_BLOCK = 1 << 20   # 1 MiB read block: an I/O size, not a method parameter.


@dataclass(frozen=True, slots=True)
class ContentBlob:
    """One immutable source blob. ``read`` is the only way its bytes are ever seen."""

    content_handle: str
    media_type: str
    size: int
    ingested_utc: str
    _data: bytes | None = field(default=None, repr=False)
    _path: Path | None = field(default=None, repr=False)
    _offset: int = field(default=0, repr=False)

    def read(self, start: int = 0, end: int | None = None) -> bytes:
        """Bytes ``[start, end)`` of this blob. Complexity: O(end - start)."""
        stop = self.size if end is None else end
        if start < 0 or stop > self.size or start > stop:
            raise BlobRewriteRefused(
                "span outside blob", handle=self.content_handle, start=start, end=stop,
                size=self.size)
        if self._data is not None:
            return self._data[start:stop]
        with self._path.open("rb") as handle:   # type: ignore[union-attr]
            handle.seek(self._offset + start)
            return handle.read(stop - start)


class ContentBlobStore:
    """A write-once content-addressed store of source blobs.

    Writing the same bytes twice is a no-op that returns the same handle and re-mints nothing:
    that is what makes "an unchanged input re-mints nothing" true at the bottom of the ladder.
    """

    def __init__(self) -> None:
        self._blobs: dict[str, ContentBlob] = {}

    # ---------------------------------------------------------------- writing
    def put_bytes(self, data: bytes, media_type: str) -> str:
        """Admit an in-memory blob; return its content handle. Complexity: O(len(data))."""
        handle = hash_bytes(data)
        blob = ContentBlob(handle, media_type, len(data), _utc_now(), _data=data)
        return self._admit(handle, blob)

    def put_file_range(self, path: Path, offset: int, length: int, media_type: str) -> str:
        """Admit a byte range of a file as a blob, hashing by streaming, never copying it.

        Complexity: O(length) time, O(1) memory beyond the 1 MiB read block.
        """
        digest = hashlib.sha256()
        remaining = length
        with path.open("rb") as handle:
            handle.seek(offset)
            while remaining > 0:
                block = handle.read(min(_STREAM_BLOCK, remaining))
                if not block:
                    break
                digest.update(block)
                remaining -= len(block)
        if remaining:
            raise BlobRewriteRefused("file range shorter than declared", path=str(path),
                                     offset=offset, length=length, short_by=remaining)
        content_handle = "sha256:" + digest.hexdigest()
        blob = ContentBlob(content_handle, media_type, length, _utc_now(),
                           _path=Path(path), _offset=offset)
        return self._admit(content_handle, blob)

    def _admit(self, handle: str, blob: ContentBlob) -> str:
        existing = self._blobs.get(handle)
        if existing is None:
            self._blobs[handle] = blob
            return handle
        if existing.media_type != blob.media_type or existing.size != blob.size:
            raise BlobRewriteRefused(
                "a blob is written once; this handle is already held under other declarations",
                handle=handle, held_media_type=existing.media_type,
                offered_media_type=blob.media_type)
        return handle            # identical content: no rewrite, no new ingested_utc, no churn.

    # ---------------------------------------------------------------- reading
    def __contains__(self, handle: str) -> bool:
        return handle in self._blobs

    def __len__(self) -> int:
        return len(self._blobs)

    def blob(self, handle: str) -> ContentBlob:
        blob = self._blobs.get(handle)
        if blob is None:
            raise BlobRewriteRefused("no such blob", handle=handle)
        return blob

    def read(self, handle: str, start: int, end: int) -> bytes:
        """Bytes of a span: ``blob[start:end]`` exactly as B.1 defines recovery."""
        return self.blob(handle).read(start, end)

    def handles(self) -> tuple[str, ...]:
        """Admitted handles in insertion order - the ordered list B.27's record_head hashes."""
        return tuple(self._blobs)

    def total_bytes(self) -> int:
        return sum(blob.size for blob in self._blobs.values())


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def blob_of_file(store: ContentBlobStore, path: Path, media_type: str) -> str:
    """Admit a whole file as one blob without reading it into memory."""
    return store.put_file_range(Path(path), 0, os.path.getsize(path), media_type)
