"""stream.py — the front door's SSE tailer (front door M1).

Append-only JSONL is already a durable, ordered, replayable stream whose cursor is
``(path, byte_offset)`` — so the byte offset IS the event id. Every frame carries the
full multi-source cursor as its SSE ``id:``; on reconnect the browser sends it back as
``Last-Event-ID`` unprompted, the tailer seeks each file to the given offset, and
exactly the missed lines replay. Reconnect-resume costs zero server state.

This module is the ONE streaming route and writes directly to the request handler
(the scanner's ``handle()`` contract returns whole bodies; a stream cannot ride it, so
the scanner dispatches ``GET /front/stream`` here explicitly). Everything rendered is
produced by front_door's fragment renderers — the browser holds no model.

Host-owned transcripts tail over the same machinery: ``chat=<session-uuid>`` follows
one transcript under the project's transcript dir. The uuid is validated against a
strict pattern and resolved inside that one directory only — never a path.

Read-only: this module writes nothing, ever.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from laplace.engine import rows as _rows
from laplace.engine import sources as _sources

#: poll cadence and bounds — a single-user loopback surface; one thread per open tab.
POLL_S = 0.5
HEARTBEAT_S = 15.0
MAX_SESSION_S = 4 * 3600
MAX_LINE_BYTES = 64 * 1024
#: one read per source per tick. A line LONGER than this window cannot be resolved by
#: waiting (the review's critical finding 2026-08-24: the tail stalled forever behind
#: one oversized transcript line) — it is stepped over loudly instead.
READ_WINDOW = 512 * 1024

_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def _line_end(path: Path, start: int) -> int:
    """Byte offset just past the next ``\\n`` at or after ``start`` — or EOF when the
    oversized line has no terminator yet. Used only to step over a line that cannot
    fit the read window; the tail behind it must survive."""
    at = start
    try:
        with open(path, "rb") as fh:
            fh.seek(at)
            while True:
                chunk = fh.read(READ_WINDOW)
                if not chunk:
                    return at
                nl = chunk.find(b"\n")
                if nl >= 0:
                    return at + nl + 1
                at += len(chunk)
    except OSError:
        return start


def _parse_cursor(raw: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for part in (raw or "").split(","):
        name, _, off = part.strip().partition("@")
        if name and off.isdigit():
            out[name] = int(off)
    return out


def _fmt_cursor(cur: dict[str, int]) -> str:
    return ",".join(f"{n}@{o}" for n, o in sorted(cur.items()))


def serve(handler: Any, query: dict[str, Any]) -> None:
    """Stream frames to one client until it disconnects. ``handler`` is the scanner's
    request handler (BaseHTTPRequestHandler); all writes are guarded — a closed tab
    must never take the engine down."""
    from laplace.web import front_door as _fd  # lazy: front_door owns the renderers

    requested = [n for n in (query.get("sources", [""])[0] or "").split(",") if n]
    names = [n for n in requested
             if n in _sources.SOURCES and _sources.get(n)["scan"]]
    track_atlas = "atlas" in requested
    expr = (query.get("where", [""])[0] or "")
    predicate, _parsed = _rows.compile_filter(expr)

    chat_sid = (query.get("chat", [""])[0] or "").strip()
    chat_path: Path | None = None
    if chat_sid and _UUID.match(chat_sid):
        cand = _sources.transcript_dir() / f"{chat_sid}.jsonl"
        if cand.exists():
            chat_path = cand

    cursor = _parse_cursor(handler.headers.get("Last-Event-ID", "")
                           or (query.get("since", [""])[0] or ""))

    def path_for(name: str) -> Path | None:
        if name == "chat":
            return chat_path
        spec = _sources.get(name)
        return Path(spec["abspath"]) if spec else None

    tracked = list(names) + (["chat"] if chat_path else []) + (["atlas"] if track_atlas else [])
    # Nothing to tail (a bare GET, an unknown source list, a dead chat sid): say so
    # and CLOSE, never loop — an empty stream that heartbeats forever reads as a live
    # channel, and the census's reachability probe rightly refuses a route that never
    # completes. The retry hint slows a misconfigured EventSource's reconnect spin.
    if not tracked:
        try:
            handler.send_response(200)
            handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
            handler.send_header("Cache-Control", "no-cache")
            handler.end_headers()
            handler.wfile.write(b"retry: 60000\nevent: empty\n"
                                b"data: no tailable sources requested\n\n")
            handler.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        return
    # start-at-end for sources with no cursor: the tail shows what happens NEXT;
    # history is /front/rows' job (same cursor, different door).
    for name in tracked:
        if name not in cursor:
            if name == "atlas":
                try:
                    from laplace.representation import atlas_bridge

                    # A tail cursor asks only whether the compact ledger advanced. A
                    # full replay here turned every open EventSource into two history
                    # reconstructions per second. The migration-stable drift token is
                    # exactly the O(1) authority for this question; it certifies no
                    # chain and is not used as one.
                    cursor[name] = int(atlas_bridge.drift_token()["cursor"])
                except Exception:
                    cursor[name] = 0
                continue
            p = path_for(name)
            try:
                cursor[name] = p.stat().st_size if p else 0
            except OSError:
                cursor[name] = 0

    try:
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
        handler.send_header("Cache-Control", "no-cache")
        handler.send_header("X-Accel-Buffering", "no")
        handler.end_headers()
    except (BrokenPipeError, ConnectionResetError, OSError):
        return

    def emit(event: str, data: str, with_id: bool = True) -> bool:
        chunks = "".join(f"data: {ln}\n" for ln in data.splitlines() or [""])
        frame = f"event: {event}\n{chunks}"
        if with_id:
            frame += f"id: {_fmt_cursor(cursor)}\n"
        frame += "\n"
        try:
            handler.wfile.write(frame.encode("utf-8"))
            handler.wfile.flush()
            return True
        except (BrokenPipeError, ConnectionResetError, OSError):
            return False

    if not emit("hello", _fmt_cursor(cursor)):
        return

    started = last_beat = time.time()
    while time.time() - started < MAX_SESSION_S:
        wrote = False
        for name in tracked:
            if name == "atlas":
                try:
                    import json as _json

                    from laplace.representation import atlas_bridge

                    token = atlas_bridge.drift_token()
                    event_count = int(token["cursor"])
                except Exception as exc:  # noqa: BLE001 — canonical outage is itself a delta
                    if not emit("atlas:unavailable", f"{type(exc).__name__}: {exc}", False):
                        return
                    continue
                off = cursor.get("atlas", 0)
                if event_count < off:
                    cursor["atlas"] = event_count
                    if not emit("rolled", "atlas"):
                        return
                elif event_count > off:
                    cursor["atlas"] = event_count
                    payload = _json.dumps({
                        "schema_version": "laplace.atlas-event-delta/1",
                        "after_cursor": off,
                        "event_cursor": event_count,
                        "head_event_id": token.get("head_event_id"),
                        "coalesced": event_count - off,
                    }, sort_keys=True, separators=(",", ":"))
                    if not emit("atlas:changed", payload):
                        return
                    wrote = True
                continue
            p = path_for(name)
            if p is None:
                continue
            try:
                size = p.stat().st_size
            except OSError:
                continue
            off = cursor.get(name, 0)
            if size < off:                     # rotation/truncation guard
                cursor[name] = 0
                if not emit("rolled", name):
                    return
                off = 0
            if size <= off:
                continue
            try:
                with open(p, "rb") as fh:
                    fh.seek(off)
                    data = fh.read(min(size - off, READ_WINDOW))
            except OSError:
                continue
            # only complete lines advance the cursor; a partial tail waits.
            newline = data.rfind(b"\n")
            if newline < 0:
                if len(data) < READ_WINDOW:
                    continue          # a genuine partial tail: more is still coming
                # the line AT off is bigger than the whole window — waiting can never
                # resolve it, and every row behind it would be lost forever. Find its
                # real end, step past it, and SAY so: a skipped line is a fact, not a
                # silence (the review's critical finding, 2026-08-24).
                end = _line_end(p, off + len(data))
                cursor[name] = end
                if not emit("skipped", f"{name} @{off}..{end} — {end - off:,} B line "
                                       f"exceeds the {READ_WINDOW // 1024} KB read "
                                       f"window; stepped over"):
                    return
                continue
            complete, advance = data[:newline + 1], newline + 1
            line_off = off
            for raw in complete.splitlines(keepends=True):
                this_off = line_off
                line_off += len(raw)
                if len(raw) > MAX_LINE_BYTES:
                    continue
                if name == "chat":
                    # the chat cursor advances and the frame CARRIES it: without an
                    # id the browser's Last-Event-ID never moves, and every automatic
                    # EventSource reconnect replays the whole conversation from the
                    # hello cursor (the review's finding, 2026-08-24).
                    cursor["chat"] = this_off + len(raw)
                    html = _fd.render_chat_line(raw)
                    if html and not emit("chat", html):
                        return
                    continue
                try:
                    import json as _json
                    row = _json.loads(raw)
                except ValueError:
                    continue
                if not isinstance(row, dict) or not predicate(row):
                    continue
                html = _fd.render_stream_row(name, this_off, row)
                cursor[name] = this_off + len(raw)
                if not emit(f"rows:{name}", html):
                    return
                wrote = True
            cursor[name] = off + advance
            # Invalidation follows BYTES, not successful parsing. A completed malformed
            # row still moved the store and must make derived projections re-read it so
            # they can surface their parse residual; waiting only for rows:<name> made
            # corruption freeze the prior confident count.
            if not emit("source:changed", name):
                return
            wrote = True
        now = time.time()
        if wrote:
            last_beat = now
        elif now - last_beat > HEARTBEAT_S:
            last_beat = now
            try:
                handler.wfile.write(b": ping\n\n")
                handler.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                return
        time.sleep(POLL_S)
