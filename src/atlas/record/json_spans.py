"""json_spans.py - the byte-offset JSON scanner: rung (a)'s eyes.

Why this exists at all. Clause B.1 says a span is byte offsets into the immutable source blob
and that "a span's text is recovered by blob[start:end]". ``json.loads`` throws the offsets
away, so a store built on it can only *copy* text into rows - which B.1 forbids and which
makes the witness check of B.4 unverifiable (there is nothing to re-read). This scanner is the
smallest thing that keeps the byte spine: it returns the same values ``json.loads`` would, each
carrying the byte range it was read from.

It is rung (a) by B.7's definition: the source container's own grammar, a parser with no
learned parameter, no model and no statistics.

Prior machinery. ``reconstruction/extension/longmem_data.py:172-238`` already streams the 277 MB
LongMemEval array with an incremental ``raw_decode`` loop, and that loop's shape (sliding buffer,
refill on ``JSONDecodeError``, refuse on truncation) is reused verbatim in ``iter_array_items``
below. What could not be reused is the decode itself: ``raw_decode`` works on ``str`` and reports
character positions, so its offsets are not byte offsets into the file and cannot address a span.
Hence a bytes-level scanner, with the buffer discipline carried over.

Cost. One compiled-regex match per token, no per-character Python. Measured on this machine at
~29 MB/s over LongMemEval-S (see the packet report); the scan is O(bytes) with O(depth) stack.

Span convention (part of the segmenter's declared identity, ``json-byte-scanner@1``): a string
value's span INCLUDES its surrounding quotes, so ``json.loads(blob[start:end])`` recovers the
value exactly, escapes and all. A span that stopped inside the quotes would need a second,
unstated rule to re-decode, and an unstated rule is where the bytes stop being the truth.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from .errors import MalformedSource

__all__ = ["JNode", "SEGMENTER_ID", "SEG_VERSION", "scan_value", "iter_array_items",
           "iter_object_members", "iter_jsonl_lines"]

SEGMENTER_ID = "json-byte-scanner"
SEG_VERSION = "1"

# One regex per token class; each match is one C-level call over a whole token.
_STRING = re.compile(rb'"(?:[^"\\\x00-\x1f]|\\["\\/bfnrt]|\\u[0-9a-fA-F]{4})*"')
_NUMBER = re.compile(rb"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][-+]?[0-9]+)?")
_WS = re.compile(rb"[ \t\n\r]*")


@dataclass(frozen=True, slots=True)
class JNode:
    """One JSON value and the byte range of the blob it was read from.

    ``members`` maps an object's key text to (key_node, value_node); ``items`` is an array's
    element list. ``value`` is the decoded scalar for a scalar node and ``None`` for containers,
    which are never materialised as Python objects by this scanner.
    """

    kind: str          # object | array | string | number | true | false | null
    start: int         # absolute byte offset of the first byte of the value
    end: int           # absolute byte offset one past its last byte
    value: Any = None
    members: dict[str, tuple["JNode", "JNode"]] | None = None
    items: tuple["JNode", ...] | None = None

    def member(self, key: str) -> "JNode":
        """The value node under ``key``. Refuses a missing key: rung (a) never guesses a field."""
        if self.members is None or key not in self.members:
            raise MalformedSource("object has no such member", key=key, at=self.start)
        return self.members[key][1]

    def get(self, key: str) -> "JNode | None":
        if self.members is None:
            return None
        found = self.members.get(key)
        return None if found is None else found[1]

    @property
    def text(self) -> str:
        """The decoded string value. Only meaningful for ``kind == 'string'``."""
        if self.kind != "string":
            raise MalformedSource("node is not a string", kind=self.kind, at=self.start)
        return str(self.value)


def _skip_ws(buf: bytes, pos: int) -> int:
    return _WS.match(buf, pos).end()


def scan_value(buf: bytes, pos: int = 0, base: int = 0) -> tuple[JNode, int]:
    """Scan one JSON value starting at ``buf[pos]``; return the node and the next position.

    ``base`` is added to every recorded offset, so a value scanned out of a sliding window
    still carries absolute file offsets.

    Complexity: O(bytes of the value) time, O(nesting depth) stack.
    """
    pos = _skip_ws(buf, pos)
    if pos >= len(buf):
        raise MalformedSource("value expected, input ended", at=base + pos)
    head = buf[pos:pos + 1]
    if head == b"{":
        return _scan_object(buf, pos, base)
    if head == b"[":
        return _scan_array(buf, pos, base)
    if head == b'"':
        match = _STRING.match(buf, pos)
        if match is None:
            raise MalformedSource("malformed string", at=base + pos)
        raw = match.group(0)
        return JNode("string", base + pos, base + match.end(),
                     json.loads(raw.decode("utf-8"))), match.end()
    for literal, kind, decoded in ((b"true", "true", True), (b"false", "false", False),
                                   (b"null", "null", None)):
        if buf.startswith(literal, pos):
            return JNode(kind, base + pos, base + pos + len(literal), decoded), pos + len(literal)
    match = _NUMBER.match(buf, pos)
    if match is None or match.end() == pos:
        raise MalformedSource("value expected", at=base + pos, saw=buf[pos:pos + 12].decode(
            "utf-8", "replace"))
    raw = match.group(0)
    number: Any = int(raw) if _NUMBER_IS_INT(raw) else float(raw)
    return JNode("number", base + pos, base + match.end(), number), match.end()


def _NUMBER_IS_INT(raw: bytes) -> bool:
    return b"." not in raw and b"e" not in raw and b"E" not in raw


def _scan_object(buf: bytes, pos: int, base: int) -> tuple[JNode, int]:
    start = pos
    pos = _skip_ws(buf, pos + 1)
    members: dict[str, tuple[JNode, JNode]] = {}
    if buf.startswith(b"}", pos):
        return JNode("object", base + start, base + pos + 1, members=members), pos + 1
    while True:
        pos = _skip_ws(buf, pos)
        match = _STRING.match(buf, pos)
        if match is None:
            raise MalformedSource("object key expected", at=base + pos)
        key_node = JNode("string", base + pos, base + match.end(),
                         json.loads(match.group(0).decode("utf-8")))
        pos = _skip_ws(buf, match.end())
        if not buf.startswith(b":", pos):
            raise MalformedSource("':' expected after object key", at=base + pos)
        value_node, pos = scan_value(buf, pos + 1, base)
        members[str(key_node.value)] = (key_node, value_node)
        pos = _skip_ws(buf, pos)
        if buf.startswith(b",", pos):
            pos += 1
            continue
        if buf.startswith(b"}", pos):
            return JNode("object", base + start, base + pos + 1, members=members), pos + 1
        raise MalformedSource("',' or '}' expected", at=base + pos)


def _scan_array(buf: bytes, pos: int, base: int) -> tuple[JNode, int]:
    start = pos
    pos = _skip_ws(buf, pos + 1)
    items: list[JNode] = []
    if buf.startswith(b"]", pos):
        return JNode("array", base + start, base + pos + 1, items=()), pos + 1
    while True:
        node, pos = scan_value(buf, pos, base)
        items.append(node)
        pos = _skip_ws(buf, pos)
        if buf.startswith(b",", pos):
            pos += 1
            continue
        if buf.startswith(b"]", pos):
            return JNode("array", base + start, base + pos + 1, items=tuple(items)), pos + 1
        raise MalformedSource("',' or ']' expected", at=base + pos)


def iter_array_items(path: Path, *, limit: int | None = None,
                     window: int = 1 << 22) -> Iterator[tuple[int, int, bytes]]:
    """Stream a top-level JSON array, yielding (start, end, raw_bytes) per element.

    The file is never fully materialised: a sliding byte window grows only far enough to hold
    the element currently being scanned. This is the buffer discipline of
    ``longmem_data.py:172-238`` carried over to bytes, which is what makes the offsets addressable.

    ``window`` (4 MiB) is an I/O block size, not a method parameter: it changes how many read
    syscalls happen and nothing else about the output. Complexity: O(file bytes) time,
    O(largest element) memory.
    """
    with path.open("rb") as handle:
        buf = handle.read(window)
        base = 0                      # absolute offset of buf[0]
        pos = _skip_ws(buf, 0)
        if not buf.startswith(b"[", pos):
            raise MalformedSource("top-level value is not an array", path=str(path))
        pos += 1
        emitted = 0
        while True:
            while True:
                pos = _skip_ws(buf, pos)
                while pos < len(buf) and buf[pos:pos + 1] == b",":
                    pos = _skip_ws(buf, pos + 1)
                if pos < len(buf):
                    break
                block = handle.read(window)
                if not block:
                    raise MalformedSource("unterminated top-level array", path=str(path))
                buf = buf[pos:] + block
                base += pos
                pos = 0
            if buf.startswith(b"]", pos):
                return
            while True:
                try:
                    node, next_pos = scan_value(buf, pos, base)
                    break
                except MalformedSource:
                    block = handle.read(window)
                    if not block:
                        raise
                    buf = buf[pos:] + block
                    base += pos
                    next_pos = pos = 0
            yield node.start, node.end, buf[pos:next_pos]
            pos = next_pos
            emitted += 1
            if limit is not None and emitted >= limit:
                return
            if pos > window:
                buf = buf[pos:]
                base += pos
                pos = 0


def iter_object_members(stream: Any, *, limit: int | None = None,
                        window: int = 1 << 22) -> Iterator[tuple[str, int, int, bytes]]:
    """Stream a top-level JSON OBJECT, yielding (key, start, end, raw_bytes) per member value.

    The array form above covers LongMemEval, whose file is a list of cases. QASPER's splits are
    a top-level object keyed by paper id, and B.34 says "one paper is one blob" - so the same
    buffer discipline is needed for an object, and re-reading the 11 MB member with
    ``json.load`` would throw away exactly the byte offsets B.1 addresses spans with.

    ``stream`` is any binary file object with ``read(n)``; it is read forward only, never
    seeked, so a ``tarfile.extractfile`` member works and the archive is never unpacked to disk.
    Complexity: O(file bytes) time, O(largest member) memory.
    """
    buf = stream.read(window)
    base = 0
    pos = _skip_ws(buf, 0)
    if not buf.startswith(b"{", pos):
        raise MalformedSource("top-level value is not an object")
    pos += 1
    emitted = 0
    while True:
        while True:
            pos = _skip_ws(buf, pos)
            while pos < len(buf) and buf[pos:pos + 1] == b",":
                pos = _skip_ws(buf, pos + 1)
            if pos < len(buf):
                break
            block = stream.read(window)
            if not block:
                raise MalformedSource("unterminated top-level object")
            buf = buf[pos:] + block
            base += pos
            pos = 0
        if buf.startswith(b"}", pos):
            return
        # The key, then the colon, then the value - each possibly straddling the window edge.
        while True:
            match = _STRING.match(buf, pos)
            after = _skip_ws(buf, match.end()) if match is not None else len(buf)
            if match is not None and after < len(buf) and buf[after:after + 1] == b":":
                break
            block = stream.read(window)
            if not block:
                raise MalformedSource("object key expected", at=base + pos)
            buf = buf[pos:] + block
            base += pos
            pos = 0
        key = str(json.loads(match.group(0).decode("utf-8")))
        value_pos = after + 1
        while True:
            try:
                node, next_pos = scan_value(buf, value_pos, base)
                break
            except MalformedSource:
                block = stream.read(window)
                if not block:
                    raise
                buf = buf[pos:] + block
                base += pos
                value_pos -= pos
                pos = 0
        # Slice from the NODE's own start, not from after the colon: the value's span begins at
        # its first byte, and any whitespace between the colon and it belongs to neither.
        yield key, node.start, node.end, buf[node.start - base:node.end - base]
        pos = next_pos
        emitted += 1
        if limit is not None and emitted >= limit:
            return
        if pos > window:
            buf = buf[pos:]
            base += pos
            pos = 0


def iter_jsonl_lines(data: bytes) -> Iterator[tuple[int, int]]:
    """Yield the (start, end) byte range of every non-blank line of a JSONL blob.

    B.32: "the whole file is the blob, one JSON object per line is one item, and its span is
    that line's byte range". The range excludes the terminating newline so that
    ``json.loads(blob[start:end])`` is exact. Complexity: O(bytes).
    """
    offset = 0
    total = len(data)
    while offset < total:
        nl = data.find(b"\n", offset)
        end = total if nl == -1 else nl
        line_end = end
        while line_end > offset and data[line_end - 1:line_end] in (b"\r", b" ", b"\t"):
            line_end -= 1
        if line_end > offset:
            yield offset, line_end
        if nl == -1:
            return
        offset = nl + 1
