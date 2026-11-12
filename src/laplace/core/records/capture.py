"""Captured reading of one append-only JSONL log: incremental suffix reads, exact selected rows and stable cuts.

  CapturedLog          one log's read position. advance() reads only complete rows appended since the last read and
                       hands each to the owner's admit(); a replaced, truncated or recreated file (device/inode,
                       size, timestamps and fixed head/tail prefix windows) resets the owner and reads afresh. An
                       incomplete trailing row stays unread until its newline lands. Rows that do not decode as
                       objects are counted, never fatal.
  read_captured_row    the exact bytes of one previously captured row, re-hashed: a changed row raises
                       CapturedRowChanged, so a selection made at one cut cannot silently read another.
  line_hash            a captured row's identity: core.identity.bytes_digest of its exact line bytes.
  encode_token / decode_token
                       the opaque continuation token codec (unpadded base64url of compact JSON).
  encode_cut / decode_cut
                       a captured cut: {v: 1, upper: last order included, query: hash of the request scope,
                       revision: hash of what was selected, offset?: page position}; decode_cut refuses any other shape.

What rows mean, which are indexed and how (Writing's sessions, turns, proposals; the engine ledger's classes) belongs to
the owner that subclasses or drives this; nothing here knows a record kind. No import-time effects.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any

from laplace.core.identity import bytes_digest
from laplace.core.records.rows import decode_row

#: bytes of the head and tail prefix windows re-hashed to detect a replaced log without rereading it
ANCHOR_WINDOW = 4096


class CapturedRowChanged(ValueError):
    """The selected row's bytes no longer hash to what was captured."""


def line_hash(raw: bytes) -> str:
    return bytes_digest(raw)


class CapturedLog:
    """Incremental reading of one append-only log. Owners override _reset() and _admit(); _after_advance() is
    optional. The position (offset, order, identity, prefix anchors), generation, status, malformed count and
    read statistics are this object's; what an owner indexes from each row is the owner's."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.offset = self.order = 0
        self.identity = None
        self._generation = object()
        self._prefix_anchors: tuple = ()
        self.source_status = 'MISSING'
        self.malformed_rows = 0
        self.stats = {'scans': 0, 'suffix_reads': 0, 'bytes_read': 0, 'rows_seen': 0,
                      'index_anchor_reads': 0, 'index_anchor_bytes': 0}

    # ---- owner hooks
    def _reset(self) -> None:
        """Forget everything indexed from this log (it was replaced, truncated or removed)."""

    def _decode(self, raw: bytes):
        """Default tolerant JSON-object policy; a domain may retain stricter failures."""
        return decode_row(raw)

    def _admit(self, row: dict, raw: bytes, offset: int, end: int) -> bool:
        """Index one decoded row; return False when the owner counts it as malformed."""
        return True

    def _after_advance(self) -> None:
        """Called once after the new rows of one advance were admitted."""

    # ---- the read
    def advance(self):
        path = self.path
        if not path.exists():
            if self.identity is not None:
                self._reset()
                self.offset = self.order = 0; self.identity = None; self._prefix_anchors = (); self.malformed_rows = 0
            self.source_status = 'MISSING'
            return self
        self.source_status = 'AVAILABLE'
        stat = path.stat()
        identity = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
        if identity == self.identity:
            return self
        reset = (self.identity is None or identity[:2] != self.identity[:2]
                 or stat.st_size < self.offset
                 or stat.st_size == self.offset and identity[3:] != self.identity[3:])
        head = tail = b''
        if not reset and self.offset:
            # Fixed prefix windows detect replacement/inode reuse without making
            # a large boundary row force a full rescan on every append. These are
            # replacement heuristics, not proof that every middle byte is intact.
            with path.open('rb') as stream:
                windows = []
                for offset, length, digest in self._prefix_anchors:
                    stream.seek(offset); data = stream.read(length)
                    self.stats['index_anchor_reads'] += 1
                    self.stats['index_anchor_bytes'] += len(data)
                    windows.append(data)
                    if hashlib.sha256(data).hexdigest() != digest:
                        reset = True
                if windows:
                    head = windows[0]; tail = windows[-1]
                else:
                    reset = True
        if reset:
            self._generation = object()
            head = tail = b''
            self._reset()
            self.offset = self.order = 0; self.malformed_rows = 0; self.stats['scans'] += 1
        else:
            self.stats['suffix_reads'] += 1
        with path.open('rb') as stream:
            stream.seek(self.offset)
            while True:
                offset = stream.tell(); raw = stream.readline()
                self.stats['bytes_read'] += len(raw)
                if not raw or not raw.endswith(b'\n'):
                    break
                head += raw[:max(0, ANCHOR_WINDOW - len(head))]
                tail = (tail + raw[-ANCHOR_WINDOW:])[-ANCHOR_WINDOW:]
                self.order += 1; self.stats['rows_seen'] += 1
                row = self._decode(raw)
                if row is None or not self._admit(row, raw, offset, stream.tell()):
                    self.malformed_rows += 1
                self.offset = stream.tell()
        self._after_advance()
        # An incomplete trailing row remains unread until its terminating newline.
        self._prefix_anchors = tuple((offset, len(data), hashlib.sha256(data).hexdigest())
                                     for offset, data in {0: head, max(0, self.offset - len(tail)): tail}.items() if data)
        self.identity = identity
        return self


def read_captured_row(path: Path | str, offset: int, end: int, expected_hash: str) -> tuple[dict, bytes]:
    """The exact captured row at [offset, end), verified against its captured line hash."""
    with Path(path).open('rb') as stream:
        stream.seek(offset); data = stream.read(end - offset)
    if line_hash(data) != expected_hash:
        raise CapturedRowChanged('The selected journal row changed; read its metadata cut again.')
    return json.loads(data), data


def encode_token(value: Any) -> str:
    return base64.urlsafe_b64encode(json.dumps(value, separators=(',', ':')).encode()).decode().rstrip('=')


def decode_token(token: str) -> Any:
    """The JSON value a token carries; ValueError (or TypeError/UnicodeError) when it is not one."""
    return json.loads(base64.urlsafe_b64decode(token + '=' * (-len(token) % 4)))


encode_cut = encode_token


def decode_cut(token: str) -> dict:
    try:
        if not isinstance(token, str) or len(token) > 4096:
            raise ValueError()
        data = decode_token(token)
        if not isinstance(data, dict) or data.get('v') != 1:
            raise ValueError()
        if (not isinstance(data.get('upper'), int) or isinstance(data.get('upper'), bool)
                or data['upper'] < 0 or not isinstance(data.get('query'), str)
                or not isinstance(data.get('revision'), str)):
            raise ValueError()
        if 'offset' in data and (not isinstance(data['offset'], int)
                or isinstance(data['offset'], bool) or data['offset'] < 0):
            raise ValueError()
        return data
    except (ValueError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('Analytics cursor/cut is malformed or unsupported; read this owner again.') from exc
