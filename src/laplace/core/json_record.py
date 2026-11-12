"""BOUNDED PINNED JSON-RECORD READING (campaign bounded source reading, 2026-10-14).

Purpose: read ONE value of a JSON source through an existing reader (the repository source reader
and the project artifact reader) by an explicit RFC 6901 JSON Pointer, instead of paging a
multi-megabyte file by characters and extracting the record by hand.

Ownership: none. This module holds no storage, cache or holder; the calling reader owns the source
fence, its identity (sha256 of the exact bytes) and its perimeter. It is given the bytes the reader
already admitted and returns one bounded page of the selected value.

Contract:
- pointer: "" selects the whole document; otherwise "/"-separated reference tokens with "~1" for
  "/" and "~0" for "~" (any other "~" escape is refused). Array tokens are "0" or a decimal without
  a leading zero, inside the array; "-" (past the end) is refused. Keys are exact Unicode strings.
- the source must be strict JSON in UTF-8 (a leading BOM is accepted); NaN/Infinity are refused; a
  duplicate key on the selected path makes the pointer ambiguous and is refused.
- the returned text is the selected value re-serialized with source key order, original number
  spellings and ensure_ascii off (indent 1); units are Unicode characters of that text; offset/limit
  page it, next_offset continues it. The full value is never returned beside a truncated page.
- a continuation carries the source pin (expected_sha256); a changed source is refused.
"""
from __future__ import annotations

import hashlib
import json
import os
import time

POINTER_DEFAULT_LIMIT = 6000          # characters of the selected value per page
POINTER_MAX_LIMIT = 40000             # the readers' existing maximum page
POINTER_MAX_SOURCE_BYTES = 64 * 1024 * 1024   # one bounded parse per read; larger sources are refused
POINTER_MAX_LENGTH = 4096
MAX_VALUE_DEPTH = 256                  # nesting of the selected value; deeper values are refused, never recursed into
READ_CHUNK = 1 << 20
SERIALIZATION = ('JSON re-serialization of the selected value: source key order, original number spellings, '
                 'ensure_ascii off, indent 1. Units are Unicode characters of this text.')


# Refusal budgets are measured at the TRANSPORT boundary: the UTF-8 bytes of the text serialized as a JSON
# string (ensure_ascii off, quotes and escapes included), so a NUL that serializes as \u0000 costs six bytes.
MAX_DIAGNOSTIC_BYTES = 1024           # a whole refusal message as a JSON string
REFUSAL_ENVELOPE_BYTES = 16           # declared allowance for the HTTP refusal envelope {"error": <message>} (11 bytes today)
MAX_SHOWN_KEY_BYTES = 160             # one source-controlled key or pointer token inside a message
MAX_SHOWN_PLACE_BYTES = 240           # one source-controlled location inside a message


def serialized_bytes(text: str) -> int:
    """UTF-8 bytes of text serialized as a JSON string (quotes and escapes included): the transport cost."""
    return len(json.dumps(text, ensure_ascii=False).encode('utf-8', 'surrogatepass'))


def _bounded(text: str, limit: int) -> str:
    """text when its serialized JSON string fits limit; otherwise the longest safe prefix whose serialized
    form, with the truncation note, fits, and the complete length and identity of the whole.

    Source-controlled keys and paths can be megabytes long or full of control characters that expand under
    JSON escaping, so a refusal never echoes them whole: the prefix is cut on a character boundary and the
    remainder is named by its character count, UTF-8 byte count and a sha256 prefix of the complete text,
    so the cause stays inspectable.
    """
    if serialized_bytes(text) <= limit:
        return text
    data = text.encode('utf-8', 'surrogatepass')
    tail = '... [truncated: %d characters, %d UTF-8 bytes, sha256:%s]' % (len(text), len(data), hashlib.sha256(data).hexdigest()[:16])
    room = limit - serialized_bytes(tail) + 2          # the joined string carries one pair of quotes
    low, high = 0, min(len(text), max(0, room))
    while low < high:                                  # the longest prefix whose serialized form fits
        middle = (low + high + 1) // 2
        if serialized_bytes(text[:middle]) <= room:
            low = middle
        else:
            high = middle - 1
    return text[:low] + tail


class RecordRefusal(ValueError):
    """A JSON-record read that cannot be answered as asked (pointer, source JSON, size or pin); callers refuse it.
    Its message is bounded at MAX_DIAGNOSTIC_BYTES of UTF-8 whatever the source holds."""

    def __init__(self, message=''):
        super().__init__(_bounded(str(message), MAX_DIAGNOSTIC_BYTES))


class _Object(dict):
    """A parsed object that remembers keys it saw more than once."""
    __slots__ = ('duplicates', 'order')


class _Number(str):
    """A number kept as its exact source spelling."""


def _object(pairs):
    value = _Object()
    value.duplicates = set()
    value.order = []
    for key, item in pairs:
        if key in value:
            value.duplicates.add(key)
        else:
            value.order.append(key)
        value[key] = item
    return value


def _refuse_constant(name):
    raise RecordRefusal('The source is not strict JSON: %s is not a JSON value.' % name)


def read_capped(path, cap: int) -> bytes:
    """The source bytes, reading at most cap + 1 bytes however the file changes (repair1 R4).

    The descriptor is opened once; a file already larger than cap is refused before any read; at
    most cap + 1 bytes are requested; a file that grew past cap, or whose size or modification
    time moved during the read, is refused.  The bytes returned are the bytes the pin is computed
    from.  Nothing is kept after the call.
    """
    fd = os.open(path, os.O_RDONLY)
    try:
        before = os.fstat(fd)
        if before.st_size > cap:
            raise RecordRefusal('The source is %d bytes; JSON-record reads parse at most %d bytes. Page it with offset/limit instead.' % (before.st_size, cap))
        chunks, remaining = [], cap + 1
        while remaining > 0:
            chunk = os.read(fd, min(remaining, READ_CHUNK))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(fd)
    finally:
        os.close(fd)
    data = b''.join(chunks)
    if len(data) > cap:
        raise RecordRefusal('The source grew past %d bytes during the read; JSON-record reads parse at most %d bytes.' % (cap, cap))
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or len(data) != after.st_size:
        raise RecordRefusal('Source revision conflict: the source changed during the read; read it again.')
    return data


def tokens(pointer) -> list[str]:
    if not isinstance(pointer, str) or len(pointer) > POINTER_MAX_LENGTH:
        raise RecordRefusal('pointer must be a JSON Pointer string of at most %d characters.' % POINTER_MAX_LENGTH)
    if _surrogate(pointer):
        raise RecordRefusal('pointer contains an unpaired UTF-16 surrogate; it cannot name a JSON key.')
    if pointer == '':
        return []
    if not pointer.startswith('/'):
        raise RecordRefusal('pointer must be "" (the whole document) or start with "/" (RFC 6901).')
    out = []
    for raw in pointer[1:].split('/'):
        index = 0
        while True:
            index = raw.find('~', index)
            if index < 0:
                break
            if raw[index + 1:index + 2] not in ('0', '1'):
                raise RecordRefusal('pointer has an invalid "~" escape; use "~0" for "~" and "~1" for "/".')
            index += 2
        out.append(raw.replace('~1', '/').replace('~0', '~'))
    return out


def _kind(value) -> str:
    if isinstance(value, dict):
        return 'object'
    if isinstance(value, list):
        return 'array'
    if isinstance(value, str) and not isinstance(value, _Number):
        return 'string'
    if isinstance(value, _Number):
        return 'number'
    if isinstance(value, bool):
        return 'boolean'
    if value is None:
        return 'null'
    raise RecordRefusal('Unsupported parsed JSON value.')


def _serialize(value, depth=0) -> str:
    pad, inner = ' ' * depth, ' ' * (depth + 1)
    if isinstance(value, _Number):
        return str(value)
    if isinstance(value, dict):
        keys = getattr(value, 'order', None) or list(value)
        if not keys:
            return '{}'
        return '{\n' + ',\n'.join(inner + json.dumps(key, ensure_ascii=False) + ': ' + _serialize(value[key], depth + 1) for key in keys) + '\n' + pad + '}'
    if isinstance(value, list):
        if not value:
            return '[]'
        return '[\n' + ',\n'.join(inner + _serialize(item, depth + 1) for item in value) + '\n' + pad + ']'
    return json.dumps(value, ensure_ascii=False)


def _surrogate(text) -> bool:
    return any('\ud800' <= char <= '\udfff' for char in text)


def _shown(text) -> str:
    """A key or token for a message: readable, ASCII-escaped when it holds an unpaired surrogate, and
    bounded at MAX_SHOWN_KEY_BYTES with its complete length and identity named."""
    return _bounded(json.dumps(text, ensure_ascii=_surrogate(text)), MAX_SHOWN_KEY_BYTES)


def _place(where) -> str:
    """A location for a message, bounded at MAX_SHOWN_PLACE_BYTES."""
    return _bounded(where, MAX_SHOWN_PLACE_BYTES) if where else '(document root)'



def _check_value(value, at):
    """Refuse the selected value when it has no single bounded JSON reading (iterative; repair1 R2):
    a repeated key (ambiguous), nesting deeper than MAX_VALUE_DEPTH, or an escaped unpaired UTF-16
    surrogate in a key or string (no UTF-8 text exists for it)."""
    stack = [(value, at, 0)]
    while stack:
        node, where, depth = stack.pop()
        place = _place(where)
        if isinstance(node, (dict, list)) and depth >= MAX_VALUE_DEPTH:
            raise RecordRefusal('The selected value nests deeper than %d levels at %s; select a deeper pointer.' % (MAX_VALUE_DEPTH, place))
        if isinstance(node, dict):
            if getattr(node, 'duplicates', None):
                raise RecordRefusal('The selected value is ambiguous: key %s appears more than once at %s; it has no single JSON reading.' % (_shown(sorted(node.duplicates)[0]), place))
            keys = getattr(node, 'order', None) or list(node)
            for key in keys:
                if _surrogate(key):
                    raise RecordRefusal('The selected value has a key %s with an unpaired UTF-16 surrogate escape at %s; it has no UTF-8 text.' % (_shown(key), place))
            stack.extend((node[key], where + '/' + key.replace('~', '~0').replace('/', '~1'), depth + 1) for key in reversed(keys))
        elif isinstance(node, list):
            stack.extend((item, where + '/' + str(index), depth + 1) for index, item in reversed(list(enumerate(node))))
        elif isinstance(node, str) and not isinstance(node, _Number) and _surrogate(node):
            raise RecordRefusal('The selected value has a string with an unpaired UTF-16 surrogate escape at %s; it has no UTF-8 text.' % place)


def select(raw: bytes, pointer: str):
    """Parse the admitted bytes once and return (value, locator facts). Refusals are ValueError."""
    if len(raw) > POINTER_MAX_SOURCE_BYTES:
        raise RecordRefusal('The source is %d bytes; JSON-record reads parse at most %d bytes. Page it with offset/limit instead.'
                         % (len(raw), POINTER_MAX_SOURCE_BYTES))
    path = tokens(pointer)
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise RecordRefusal('The source is not UTF-8 JSON (byte %d).' % exc.start) from None
    started = time.perf_counter()
    try:
        value = json.loads(text, object_pairs_hook=_object, parse_float=_Number, parse_int=_Number,
                           parse_constant=_refuse_constant)
    except json.JSONDecodeError as exc:
        raise RecordRefusal('The source is not valid JSON: %s at line %d column %d.' % (exc.msg, exc.lineno, exc.colno)) from None
    except RecursionError:
        raise RecordRefusal('The source nests JSON values too deeply to read as one record.') from None
    parse_ms = round((time.perf_counter() - started) * 1000, 1)
    walked = ''
    for token in path:
        shown = walked + '/' + token.replace('~', '~0').replace('/', '~1')
        if isinstance(value, dict):
            if token in getattr(value, 'duplicates', ()):
                raise RecordRefusal('The pointer is ambiguous: key %s appears more than once at %s.' % (_shown(token), _place(walked)))
            if token not in value:
                raise RecordRefusal('The pointer selects no value: %s has no key %s.' % (_place(walked), _shown(token)))
            value = value[token]
        elif isinstance(value, list):
            if token == '-':
                raise RecordRefusal('The pointer token "-" names the position after the last element of %s; it selects no value.' % (_place(walked)))
            if not token.isascii() or not token.isdigit() or (len(token) > 1 and token[0] == '0'):
                raise RecordRefusal('The pointer token %s is not an array index for %s.' % (_shown(token), _place(walked)))
            if int(token) >= len(value):
                raise RecordRefusal('The pointer selects no value: %s has %d elements.' % (_place(walked), len(value)))
            value = value[int(token)]
        else:
            raise RecordRefusal('The pointer selects no value: %s is a %s, not an object or array.' % (_place(walked), _kind(value)))
        walked = shown
    _check_value(value, walked)
    return value, {'pointer': pointer, 'tokens': path, 'type': _kind(value),
                   **({'members': len(value)} if isinstance(value, (dict, list)) else {}),
                   'parse': {'source_bytes': len(raw), 'parse_ms': parse_ms}}


def page(raw: bytes, source_sha256: str, payload: dict) -> dict:
    """One bounded page of the selected value, pinned to the exact source bytes the reader admitted."""
    pointer = payload.get('pointer')
    offset = payload.get('offset', 0)
    limit = payload.get('limit', POINTER_DEFAULT_LIMIT)
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise RecordRefusal('offset must be a non-negative character offset into the selected value.')
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= POINTER_MAX_LIMIT:
        raise RecordRefusal('limit must be 1-%d characters of the selected value.' % POINTER_MAX_LIMIT)
    from laplace.core import source_pin
    try:
        current = source_pin.check(source_sha256, payload)
    except source_pin.SourcePinRefusal as error:
        raise RecordRefusal(str(error)) from error
    value, locator = select(raw, pointer)
    text = _serialize(value)
    if offset > len(text):
        raise RecordRefusal('offset %d is past the end of the selected value (%d characters).' % (offset, len(text)))
    content = text[offset:offset + limit]
    more = offset + len(content) < len(text)
    return {'json_record': {**locator, 'source_sha256': current, 'value_chars': len(text),
                            'value_sha256': 'sha256:' + hashlib.sha256(text.encode('utf-8')).hexdigest(),
                            'serialization': SERIALIZATION},
            'content': content, 'offset': offset, 'limit': limit, 'truncated': more,
            'next_offset': offset + len(content) if more else None,
            'units': 'Unicode characters of the selected value\'s JSON serialization'}
