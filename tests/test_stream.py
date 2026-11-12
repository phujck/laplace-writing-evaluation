"""The front door's SSE tailer (front door M1) — the module that had no tests at all.

Three laws, one test each, all over the real ``stream.serve`` loop with a fake request
handler (no socket, no server, no thread):

* **the tail survives a monster.** A JSONL line larger than the read window cannot be
  resolved by waiting: the old loop found no newline, ``continue``d without moving the
  cursor, and re-read the same window forever — every row behind it lost while the
  heartbeat kept the stream looking alive. It is stepped over now, and SAID.
* **the chat lane resumes.** Chat frames carry the cursor as their SSE ``id``, so an
  EventSource reconnect resumes instead of replaying the whole conversation.
* **an empty tracked set CLOSES.** A stream with nothing to tail says so and ends; it
  never heartbeats forever pretending to be a live channel.

The loop is bounded twice over: the fake ``wfile`` raises ``BrokenPipeError`` once it
has collected the frames under test (exactly what a closed tab does — serve's own clean
exit), and ``MAX_SESSION_S`` is monkeypatched down as a backstop.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from laplace.engine import sources
from laplace.web import stream

SID = "0123abcd-4567-89ab-cdef-0123456789ab"


# --------------------------------------------------------------------------- fakes

class _FakeWfile:
    """Collects frames; raises BrokenPipeError once ``stop_after`` have landed — the
    closed-tab path serve already handles, and the test's clean exit."""

    def __init__(self, stop_after: int) -> None:
        self.chunks: list[bytes] = []
        self.stop_after = stop_after

    def write(self, data: bytes) -> None:
        self.chunks.append(bytes(data))
        if len(self.chunks) >= self.stop_after:
            raise BrokenPipeError("the tab closed")

    def flush(self) -> None:
        pass

    @property
    def out(self) -> bytes:
        return b"".join(self.chunks)


class _FakeHandler:
    def __init__(self, stop_after: int = 3, last_event_id: str = "") -> None:
        self.headers = {"Last-Event-ID": last_event_id} if last_event_id else {}
        self.wfile = _FakeWfile(stop_after)
        self.status: int | None = None
        self.sent: dict[str, str] = {}

    def send_response(self, code: int) -> None:
        self.status = code

    def send_header(self, key: str, value: str) -> None:
        self.sent[key] = value

    def end_headers(self) -> None:
        pass


@pytest.fixture
def fast(monkeypatch):
    """No poll delay, and a hard session ceiling so no assertion can hang the suite."""
    monkeypatch.setattr(stream, "POLL_S", 0.0)
    monkeypatch.setattr(stream, "MAX_SESSION_S", 2.0)


def _point(monkeypatch, name: str, path: Path) -> None:
    monkeypatch.setitem(sources.SOURCES[name], "path", str(path))


# --------------------------------------------------------------------------- monster

def test_a_line_over_the_read_window_is_stepped_over_and_the_tail_survives(
        tmp_path, monkeypatch, fast):
    """The critical one: a 512 KB+ line stalled that source's tail FOREVER. Four such
    lines already sit in the host's transcripts, so the live chat pane reached one and
    silently stopped updating. The monster is skipped, loudly, and the small row
    behind it still arrives."""
    monster = json.dumps({"record": "act", "act_id": "MONSTER",
                          "pad": "x" * (stream.READ_WINDOW + 4096)})
    after = json.dumps({"record": "act", "act_id": "AFTER-THE-MONSTER"})
    f = tmp_path / "journal.jsonl"
    f.write_text(monster + "\n" + after + "\n", encoding="utf-8")
    _point(monkeypatch, "journal", f)

    h = _FakeHandler(stop_after=3)          # hello · skipped · the row behind it
    stream.serve(h, {"sources": ["journal"], "since": ["journal@0"]})
    out = h.wfile.out

    assert h.status == 200 and h.sent["Content-Type"].startswith("text/event-stream")
    assert b"event: skipped" in out, "a skipped line is a fact, never a silence"
    assert b"journal @0.." in out, "the skip names its source and its byte span"
    assert b"event: rows:journal" in out, "the tail behind the monster survived"
    assert b"AFTER-THE-MONSTER" in out
    assert b"MONSTER\"" not in out and b"xxxxxxxx" not in out, "the monster itself never renders"
    # the cursor moved past the monster: the id on the skipped frame is its end offset
    assert f"journal@{len(monster.encode()) + 1}".encode() in out


def test_a_genuine_partial_tail_still_waits(tmp_path, monkeypatch, fast):
    """The other half of the same branch: a short read with no newline is a line still
    being written — that one WAITS, and must never be skipped."""
    f = tmp_path / "journal.jsonl"
    f.write_text('{"record": "act", "act_id": "HALF-WRITTEN"', encoding="utf-8")
    _point(monkeypatch, "journal", f)

    h = _FakeHandler(stop_after=2)          # hello, then nothing but the ceiling
    stream.serve(h, {"sources": ["journal"], "since": ["journal@0"]})
    out = h.wfile.out
    assert b"event: hello" in out
    assert b"event: skipped" not in out, "a partial tail is a moment, not an oversized line"
    assert b"HALF-WRITTEN" not in out


def test_a_malformed_completed_row_still_invalidates_derived_views(
        tmp_path, monkeypatch, fast):
    """A parser miss is not permission to freeze the last confident derived count."""
    f = tmp_path / "journal.jsonl"
    f.write_text("not-json\n", encoding="utf-8")
    _point(monkeypatch, "journal", f)

    h = _FakeHandler(stop_after=2)          # hello · source movement
    stream.serve(h, {"sources": ["journal"], "since": ["journal@0"]})

    assert b"event: source:changed" in h.wfile.out
    assert b"data: journal" in h.wfile.out


# --------------------------------------------------------------------------- chat

def test_chat_frames_advance_the_sse_id(tmp_path, monkeypatch, fast):
    """Emitted with ``with_id=False`` the browser's Last-Event-ID never moved, so every
    automatic EventSource reconnect replayed the conversation from the hello cursor."""
    monkeypatch.setattr(sources, "TRANSCRIPT_DIR", str(tmp_path))
    line = json.dumps({"message": {"role": "user", "content": "the tail resumes"}})
    (tmp_path / f"{SID}.jsonl").write_text(line + "\n", encoding="utf-8")

    h = _FakeHandler(stop_after=2)          # hello · one chat bubble
    stream.serve(h, {"chat": [SID], "since": ["chat@0"]})
    out = h.wfile.out

    assert b"event: chat" in out and b"the tail resumes" in out
    size = (tmp_path / f"{SID}.jsonl").stat().st_size
    assert f"id: chat@{size}".encode() in out, (
        "the chat frame carries the cursor: reconnect resumes, never replays")


def test_the_chat_cursor_is_honoured_on_reconnect(tmp_path, monkeypatch, fast):
    """The resume the id exists for: a Last-Event-ID past the first line replays only
    what came after it."""
    monkeypatch.setattr(sources, "TRANSCRIPT_DIR", str(tmp_path))
    first = json.dumps({"message": {"role": "user", "content": "already seen"}})
    second = json.dumps({"message": {"role": "assistant", "content": "the new one"}})
    (tmp_path / f"{SID}.jsonl").write_text(first + "\n" + second + "\n", encoding="utf-8")

    h = _FakeHandler(stop_after=2,
                     last_event_id=f"chat@{len(first.encode()) + 1}")
    stream.serve(h, {"chat": [SID]})
    out = h.wfile.out
    assert b"the new one" in out
    assert b"already seen" not in out, "resume, not replay"


# --------------------------------------------------------------------------- empty

def test_an_empty_tracked_set_closes_immediately(fast):
    """A stream with nothing to tail says so and ENDS. Heartbeating forever reads as a
    live channel, and the census's reachability probe rightly refuses a route that
    never completes."""
    h = _FakeHandler(stop_after=99)         # never reached: serve returns on its own
    stream.serve(h, {})
    out = h.wfile.out

    assert h.status == 200
    assert b"event: empty" in out and b"no tailable sources requested" in out
    assert b"retry: 60000" in out, "the retry hint slows a misconfigured reconnect spin"
    assert b"event: hello" not in out and b": ping" not in out


def test_an_unknown_source_and_a_dead_chat_sid_both_close_empty(fast):
    for query in ({"sources": ["no-such-source"]},
                  {"chat": ["not-a-uuid"]},
                  {"chat": ["ffffffff-ffff-ffff-ffff-ffffffffffff"]}):
        h = _FakeHandler(stop_after=99)
        stream.serve(h, query)
        assert b"event: empty" in h.wfile.out, query


def test_atlas_virtual_source_advances_the_canonical_event_cursor(monkeypatch, fast):
    from laplace.representation import atlas_bridge

    calls = iter((
        {"cursor": 12, "head_event_id": "event:12"},
        {"cursor": 14, "head_event_id": "event:14"},
    ))
    last = {"cursor": 14, "head_event_id": "event:14"}

    def drift_token():
        nonlocal last
        try:
            last = next(calls)
        except StopIteration:
            pass
        return last

    monkeypatch.setattr(atlas_bridge, "drift_token", drift_token)
    monkeypatch.setattr(
        atlas_bridge, "snapshot",
        lambda: (_ for _ in ()).throw(AssertionError("an SSE poll must not replay history")))
    h = _FakeHandler(stop_after=2)  # hello at 12, then canonical delta to 14
    stream.serve(h, {"sources": ["atlas"]})
    out = h.wfile.out

    assert b"event: atlas:changed" in out
    assert b'"after_cursor":12' in out and b'"event_cursor":14' in out
    assert b"id: atlas@14" in out
