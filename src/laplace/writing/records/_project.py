"""Project-scoped talk reads feeding the existing multi-owner Activity adapter."""
from __future__ import annotations
import json,threading
from pathlib import Path
from typing import Any
_TALK = "contract/talk.jsonl"


_TALK_CACHE: dict[tuple[str, str], dict[str, Any]] = {}


_TALK_LOCK = threading.RLock()


_TALK_RELEVANT = {"writing-session", "writing-turn", "writing-reply", "writing-application",
                  "writing-proposal-decision", "writing-tool-action", "writing-tool-failure",
                  "writing-tool-read", "writing-native-file-change", "writing-proposal", "writing-artifact"}


def _walk_talk(path: Path, visit, *, start: int = 0,
               stop: int | None = None) -> tuple[int, int]:
    """Return ``(last complete line, furthest byte observed)`` after visiting rows."""
    offset = observed = start
    try:
        with path.open("rb") as stream:
            stream.seek(start)
            while stop is None or stream.tell() < stop:
                before = stream.tell()
                line = stream.readline()
                observed = stream.tell()
                if not line or not line.endswith(b"\n") or (stop is not None and stream.tell() > stop):
                    return before, observed
                offset = stream.tell()
                try:
                    row = json.loads(line)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if isinstance(row, dict) and row.get("record") in _TALK_RELEVANT:
                    row["_storage_bytes"] = len(line)
                    visit(row)
    except OSError:
        return start, start
    return offset, observed


def _talk_file_identity(path: Path) -> tuple[int, int, int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns


def _scan_project_talk(root: Path, project: str, *, revision: int = 0) -> dict[str, Any]:
    """Cold-scan the canonical ledger into one project's complete derived working set.

    The first pass retains only linkage metadata.  The second retains exact rows for
    ``project`` plus the session/turn rows required to attribute them.  Thus a reply
    written before its turn or a turn written before its session is still found, while
    unrelated public reply bodies are never held by the selected project's cache.
    """
    path = root / _TALK
    sessions: dict[str, str | None] = {}
    turns: dict[str, tuple[str | None, str | None]] = {}
    direct_turns: set[str] = set()
    direct_sessions: set[str] = set()
    identity_before = _talk_file_identity(path)

    def link(row: dict[str, Any]) -> None:
        kind = row.get("record")
        ident = str(row.get("id") or "")
        if kind == "writing-session" and ident:
            sessions[ident] = str(row.get("project")) if row.get("project") not in (None, "") else None
        elif kind == "writing-turn" and ident:
            turns[ident] = (str(row.get("project")) if row.get("project") not in (None, "") else None,
                            str(row.get("session_id")) if row.get("session_id") not in (None, "") else None)
        if row.get("project") == project:
            if row.get("turn_id") not in (None, ""):
                direct_turns.add(str(row["turn_id"]))
            if row.get("session_id") not in (None, ""):
                direct_sessions.add(str(row["session_id"]))

    complete, observed = _walk_talk(path, link)
    belonging_sessions = {ident for ident, owner in sessions.items() if owner == project}
    belonging_turns = {ident for ident, (owner, session_id) in turns.items()
                       if owner == project or session_id in belonging_sessions}
    needed_turns = belonging_turns | direct_turns
    needed_sessions = belonging_sessions | direct_sessions | {
        session_id for ident, (_owner, session_id) in turns.items()
        if ident in needed_turns and session_id}
    rows: list[dict[str, Any]] = []

    def collect(row: dict[str, Any]) -> None:
        kind = row.get("record")
        ident = str(row.get("id") or "")
        turn_id = str(row.get("turn_id") or "")
        session_id = str(row.get("session_id") or "")
        belongs = (row.get("project") == project or turn_id in belonging_turns
                   or session_id in belonging_sessions)
        context = ((kind == "writing-session" and ident in needed_sessions)
                   or (kind == "writing-turn" and ident in needed_turns))
        if belongs or context:
            rows.append(row)

    _walk_talk(path, collect, stop=complete)
    identity = _talk_file_identity(path)
    return {"offset": complete, "identity": identity, "rows": rows,
            "belonging_sessions": belonging_sessions, "belonging_turns": belonging_turns,
            "needed_sessions": needed_sessions, "needed_turns": needed_turns,
            "settled": (identity_before is None and identity is None) or bool(
                identity_before and identity and identity_before[:2] == identity[:2]
                and identity[2] <= observed),
            "revision": revision + 1}


def _advance_project_talk(root: Path, project: str, state: dict[str, Any] | None) -> dict[str, Any]:
    """Advance one selected project over the ledger suffix without global retention."""
    path = root / _TALK
    identity = _talk_file_identity(path)
    if state is None:
        return _scan_project_talk(root, project)
    previous = state.get("identity")
    if identity is None:
        return state if previous is None else _scan_project_talk(root, project, revision=state["revision"])
    if identity == previous:
        return state if state.get("settled") else _scan_project_talk(
            root, project, revision=state["revision"])
    if (previous is None or identity[:2] != previous[:2] or identity[2] < state["offset"]
            or (identity[2] == previous[2] and identity[3] != previous[3])):
        return _scan_project_talk(root, project, revision=state["revision"])

    selected: list[dict[str, Any]] = []
    needs_rescan = False

    def visit(row: dict[str, Any]) -> None:
        nonlocal needs_rescan
        kind = row.get("record")
        ident = str(row.get("id") or "")
        turn_id = str(row.get("turn_id") or "")
        session_id = str(row.get("session_id") or "")
        if kind == "writing-session":
            if row.get("project") == project or ident in state["needed_sessions"]:
                needs_rescan = True
            return
        if kind == "writing-turn":
            if (row.get("project") == project or session_id in state["belonging_sessions"]
                    or ident in state["needed_turns"]):
                needs_rescan = True
            return
        if (row.get("project") == project or turn_id in state["belonging_turns"]
                or session_id in state["belonging_sessions"]):
            selected.append(row)
            if row.get("project") == project:
                if turn_id:
                    needs_rescan = needs_rescan or turn_id not in state["needed_turns"]
                    state["needed_turns"].add(turn_id)
                if session_id:
                    needs_rescan = needs_rescan or session_id not in state["needed_sessions"]
                    state["needed_sessions"].add(session_id)

    identity_before = identity
    end, observed = _walk_talk(path, visit, start=state["offset"])
    if needs_rescan:
        return _scan_project_talk(root, project, revision=state["revision"])
    state["offset"] = end
    state["identity"] = _talk_file_identity(path)
    state["settled"] = bool(state["identity"] and identity_before[:2] == state["identity"][:2]
                            and state["identity"][2] <= observed)
    if selected:
        state["rows"].extend(selected)
        state["revision"] += 1
    return state


def _talk_rows(root: Path, project: str | None = None) -> list[dict[str, Any]]:
    """Return exact activity rows without retaining unrelated bodies.

    Internal callers name a project and normally receive the project-owned state from
    :func:`_indexed`.  The project-less form is a compatibility/debug read: it scans
    complete rows once and does not seed a persistent global-body cache.
    """
    with _TALK_LOCK:
        if project is not None:
            return list(_scan_project_talk(root, project)["rows"])
        rows: list[dict[str, Any]] = []
        _walk_talk(root / _TALK, rows.append)
        return rows
