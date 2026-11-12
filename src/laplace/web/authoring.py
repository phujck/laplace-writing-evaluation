"""The /authoring HTTP door of the existing scanner: the event stream and the facade the scanner routes /authoring/*
through. Everything a request reaches is its owner's: the router and family handlers are laplace.web.authoring_http,
the turn lifecycle laplace.writing.turn_admission, the live turns laplace.writing.turn_jobs, the session read model
laplace.writing.session_reads, source application laplace.manuscript.source_application. This module forwards no owner
name; it resolves the root once, at this door.

  _root()                      the serving checkout (laplace.core.checkout.repo_root)
  stream(handler, query)       /authoring/events: one live turn's server-sent events
  handle(path, query, method, body)   every other /authoring/* request, handed to writing.authoring_http
"""
from __future__ import annotations

import json

from laplace.web import authoring_http
from laplace.web.authoring_http import _value
from laplace.writing.records._fold import _LOCK
from laplace.writing.turn_jobs import _JOBS


def _root():
    from laplace.core.checkout import repo_root
    return repo_root()


def stream(handler, query):
    ident = _value(query, "turn")
    with _LOCK:
        job = _JOBS.get(ident)
    if not job or job["root"] != _root():
        handler.send_error(404, "Turn stream expired; reload the saved session.")
        return
    try:
        cursor = int(handler.headers.get("Last-Event-ID") or _value(query, "after", "0"))
    except ValueError:
        cursor = 0
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("Connection", "close")
    handler.end_headers()
    try:
        while True:
            with job["condition"]:
                if cursor >= len(job["events"]) and not job["done"]:
                    job["condition"].wait(15)
                events, done = job["events"][cursor:], job["done"]
            for event in events:
                handler.wfile.write((f"id: {event['seq']}\ndata: " + json.dumps(event, ensure_ascii=False) + "\n\n").encode())
                cursor = event["seq"]
            if not events:
                handler.wfile.write(b": heartbeat\n\n")
            handler.wfile.flush()
            if done:
                break
    except (BrokenPipeError, ConnectionResetError, OSError):
        pass


def handle(path: str, query: dict, method: str, body: bytes):
    """The /authoring/* HTTP facade: writing.authoring_http parses, routes and renders (S1 B4).

    The event stream (/authoring/events) is served by stream_events, never here; the root is
    resolved once, at this door, and handed to the router explicitly."""
    if not path.startswith("/authoring/") or path == "/authoring/events":
        return None
    return authoring_http.handle(_root(), path, query, method, body)
