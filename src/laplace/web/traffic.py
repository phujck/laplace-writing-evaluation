"""THE TRAFFIC LEDGER (M5 C12 observation contract, 2026-10-15).

Purpose: let an operator who can read only DOM and process metrics (Root's actual gates: normal idle,
20 view switches, bridge reachability, body bytes) see what the server actually answered, per route,
without a browser performance API and without reading any private browser state.

Ownership: this module is the ONE transient authority for those counters. scanner.Handler feeds it at
the three points every HTTP exchange passes: the parsed request (begin), every write to the response
socket (a counting writer, so streamed events and static files count like JSON answers) and the end of
the exchange (status and elapsed time). Nothing else writes it; nothing is persisted.

What is counted, per route key:
  requests, status classes, in_flight, response_bytes_written (bytes the socket accepted: headers and
  body, observed), response_bytes_failed and write_failures (a write that raised: attempted, not
  delivered), request_declared_bytes (the sum of Content-Length values the client declared as plain
  ASCII decimal of at most 15 digits; not re-measured) and request_length, the count of every request by
  how its length was declared: declared, absent, invalid (not ASCII decimal, e.g. a superscript digit) or
  oversized (more than 15 digits). Nothing unparseable is guessed as zero. total_ms and max_ms cover one
  exchange from parsed request to return (for an event stream, its whole life). The event stream
  (/authoring/events) also has its lifecycle: opened, closed, open_now, writes, bytes_written,
  write_failures, counted on actual writes and close.

Route keys (bounded, C12 residual R2): never a query, payload, source text, transcript or any other
path text from the request. A key is a DECLARED HTTP route (writing_declarations.HTTP_DECLARATIONS and the
writing_verbs HTTP table), one of the fixed app pages in PAGE_ROUTES, or one of the fixed buckets in
BUCKETS (/shared/*, static trees, the legacy corpus/projection/walk families), the fixed family bucket of an
undeclared writing route (/research/*, /work/*, ...), or <other>. At most ROUTE_KEY_LIMIT rows exist IN TOTAL: once ROUTE_KEY_LIMIT - 1 rows exist, a
new key counts under "<overflow>", which takes the last row. Every key is at most ROUTE_KEY_BYTES bytes.

Never throwing: the observer computes everything it needs before it changes a counter, so an exchange is
either fully begun or not begun at all, and the scanner guards each call so a failure of the observer
can never change the answer to a request; such failures are counted under observer_errors. Bytes written
for an exchange that was never begun (before a request was parsed, or when beginning failed) count
under "unattributed".

Self-reads: a read of the ledger itself (GET /authoring/health?view=traffic) is counted under
"diagnostic", never under routes, so two reads can be differenced into normal traffic exactly.

Scope and reset: the process; every client of this server. A restart resets it. Reads are cheap (a
locked copy of small dicts), loopback-only (scanner) and never hash or read source.
"""
from __future__ import annotations

import os
import re
import threading
import time

SCHEMA = "laplace.writing-traffic/1"
ROUTE_KEY_LIMIT = 64
ROUTE_KEY_BYTES = 48
LENGTH_DIGITS = 15
STREAM_ROUTE = "/authoring/events"
OVERFLOW = "<overflow>"
#: the app pages the writing server serves outside the declared HTTP tables (fixed strings)
PAGE_ROUTES = frozenset({"/", "/project", "/walk", "/walk/doc", "/artefact", "/favicon.ico", STREAM_ROUTE, "/authoring/health"})
#: fixed buckets: (path prefix, key). A key is the bucket's own fixed text, never request text.
BUCKETS = (("/shared/", "/shared/*"), ("/static/", "<static>"), ("/vendor/", "<static>"), ("/fonts/", "<static>"),
           ("/assets/", "<static>"), ("/corpus/", "/corpus/*"), ("/projection/", "/projection/*"), ("/walk/", "/walk/*"))
_WRITING = ("authoring", "research", "references", "formal", "projects", "work", "concepts", "visuals")
#: an undeclared route under a writing prefix counts under its family's fixed bucket
_WRITING_BUCKETS = {family: "/" + family + "/*" for family in _WRITING}
_ASCII_DIGITS = re.compile(r"[0-9]+", re.ASCII)
_declared_routes: frozenset | None = None

_lock = threading.Lock()
_started = time.monotonic()
_routes: dict[str, dict] = {}
_stream = {"opened": 0, "closed": 0, "writes": 0, "bytes_written": 0, "write_failures": 0}
_diagnostic = {"reads": 0, "bytes_written": 0}
_unattributed = {"bytes_written": 0, "write_failures": 0}
_observer = {"errors": 0}


def _declared() -> frozenset:
    """The declared HTTP routes, read once from the declaration owner; empty if it cannot be read."""
    global _declared_routes
    if _declared_routes is None:
        try:
            from laplace.native import declarations as writing_declarations, verbs as writing_verbs
            routes = {d.route for d in writing_declarations.HTTP_DECLARATIONS.values()}
            routes |= {r.route for r in writing_verbs.HTTP_ROUTES}
            _declared_routes = frozenset(route for route in routes
                                         if route.startswith("/") and len(route.encode("utf-8")) <= ROUTE_KEY_BYTES)
        except Exception:  # an observer never fails a request; undeclared keys fall into buckets
            _declared_routes = frozenset()
    return _declared_routes


def route_key(path: str) -> str:
    """The bounded key of one request path: a declared route, a fixed page or a fixed bucket."""
    path = str(path or "/").split("?", 1)[0]
    if path in PAGE_ROUTES or path in _declared():
        return path
    for prefix, key in BUCKETS:
        if path.startswith(prefix):
            return key
    head = path.split("/")[1] if path.count("/") >= 1 else ""
    return _WRITING_BUCKETS.get(head, "<other>")   # an undeclared writing route keeps its family, nothing more


def declared_length(value) -> tuple[int | None, str]:
    """(bytes, label) of a declared Content-Length: plain ASCII decimal of at most LENGTH_DIGITS digits,
    else None with label absent / invalid / oversized. Never raises, never guesses."""
    if value is None:
        return None, "absent"
    text = value if isinstance(value, str) else str(value)
    if not _ASCII_DIGITS.fullmatch(text):
        return None, "invalid"
    if len(text) > LENGTH_DIGITS:
        return None, "oversized"
    return int(text), "declared"


def _row() -> dict:
    return {"requests": 0, "in_flight": 0, "status": {}, "response_bytes_written": 0, "response_bytes_failed": 0,
            "write_failures": 0, "request_declared_bytes": 0, "request_length": {}, "total_ms": 0.0, "max_ms": 0.0}


class Exchange:
    """One HTTP exchange's attribution: its key, whether it is a ledger self-read, and its counters."""
    __slots__ = ("key", "diagnostic", "stream", "started")

    def __init__(self, key: str, diagnostic: bool, stream: bool):
        self.key, self.diagnostic, self.stream, self.started = key, diagnostic, stream, time.monotonic()


def begin(method: str, path: str, *, diagnostic: bool = False, content_length=None) -> Exchange:
    """Open one exchange. Everything is computed first; the counters change only after nothing can fail."""
    key = route_key(path)
    size, label = declared_length(content_length)
    exchange = Exchange(key, diagnostic, key == STREAM_ROUTE)
    with _lock:
        if diagnostic:
            _diagnostic["reads"] += 1
            return exchange
        if key not in _routes and len(_routes) >= ROUTE_KEY_LIMIT - 1:
            exchange.key = key = OVERFLOW   # the last row is reserved for overflow: at most ROUTE_KEY_LIMIT rows
        row = _routes.get(key)
        if row is None:
            row = _routes[key] = _row()
        row["requests"] += 1
        row["in_flight"] += 1
        row["request_length"][label] = row["request_length"].get(label, 0) + 1
        if size is not None:
            row["request_declared_bytes"] += size
        if exchange.stream:
            _stream["opened"] += 1
    return exchange


def observer_failed() -> None:
    """Count an observer failure the scanner caught (the request itself is unaffected)."""
    with _lock:
        _observer["errors"] += 1


def wrote(exchange: Exchange | None, count: int, *, failed: bool = False) -> None:
    with _lock:
        if exchange is None:
            _unattributed["write_failures" if failed else "bytes_written"] += 1 if failed else count
            return
        if exchange.diagnostic:
            if not failed:
                _diagnostic["bytes_written"] += count
            return
        row = _routes[exchange.key]
        if failed:
            row["response_bytes_failed"] += count
            row["write_failures"] += 1
        else:
            row["response_bytes_written"] += count
        if exchange.stream:
            if failed:
                _stream["write_failures"] += 1
            else:
                _stream["writes"] += 1
                _stream["bytes_written"] += count


def end(exchange: Exchange | None, status: int | None) -> None:
    if exchange is None or exchange.diagnostic:
        return
    elapsed = (time.monotonic() - exchange.started) * 1000
    with _lock:
        row = _routes[exchange.key]
        row["in_flight"] -= 1
        status_class = (str(status)[0] + "xx") if status else "none"
        row["status"][status_class] = row["status"].get(status_class, 0) + 1
        row["total_ms"] += elapsed
        row["max_ms"] = max(row["max_ms"], elapsed)
        if exchange.stream:
            _stream["closed"] += 1


def snapshot() -> dict:
    """A copy of every counter; monotonic clock values in seconds since this process's ledger started."""
    with _lock:
        routes = {key: {**row, "status": dict(row["status"]), "request_length": dict(row["request_length"]),
                        "total_ms": round(row["total_ms"], 3), "max_ms": round(row["max_ms"], 3)}
                  for key, row in sorted(_routes.items())}
        stream = dict(_stream, open_now=_stream["opened"] - _stream["closed"])
        diagnostic, unattributed, observer_errors = dict(_diagnostic), dict(_unattributed), _observer["errors"]
    return {"schema_version": SCHEMA, "pid": os.getpid(), "elapsed_s": round(time.monotonic() - _started, 3),
            "routes": routes, "event_stream": stream, "diagnostic": diagnostic, "unattributed": unattributed,
            "observer_errors": observer_errors,
            "limits": {"route_keys": ROUTE_KEY_LIMIT, "route_keys_used": len(routes), "route_key_bytes": ROUTE_KEY_BYTES,
                       "length_digits": LENGTH_DIGITS, "overflow_key": OVERFLOW},
            "scope": "This server process since it started; every client. A restart resets it. Difference two reads; "
                     "reads of this view are counted under diagnostic only.",
            "not_counted": "Queries, payloads, source text, transcripts and undeclared path text are never recorded. "
                           "Request bodies are the declared Content-Length, not re-measured; an invalid, oversized or absent "
                           "length is counted by label, never as zero. Browser CPU, memory and cached responses are not visible here."}


class CountingWriter:
    """The response socket writer of one handler, counting accepted and failed writes against the
    handler's current exchange. Every other attribute is the wrapped writer's."""

    def __init__(self, inner, exchange):
        self._inner, self._exchange = inner, exchange

    def write(self, data):
        try:
            result = self._inner.write(data)
        except Exception:
            self._count(len(data), failed=True)
            raise
        self._count(len(data) if result is None else result)
        return result

    def _count(self, size, *, failed=False):
        try:
            wrote(self._exchange(), size, failed=failed)
        except Exception:   # the observer never changes what the socket did
            observer_failed()

    def __getattr__(self, name):
        return getattr(self._inner, name)


def _reset_for_tests() -> None:
    """Disposable reset for unit tests only; the server never calls it (counters are differenced)."""
    global _started
    with _lock:
        _routes.clear()
        _stream.update(opened=0, closed=0, writes=0, bytes_written=0, write_failures=0)
        _diagnostic.update(reads=0, bytes_written=0)
        _unattributed.update(bytes_written=0, write_failures=0)
        _observer.update(errors=0)
        _started = time.monotonic()
