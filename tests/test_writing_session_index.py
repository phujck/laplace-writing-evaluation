"""GET /authoring/state?view=all-sessions: the cross-project session index read (wave 9, Sessions page).

The journal fold and the live-turn registry are replaced by small fixtures; no provider is launched and nothing
outside tmp_path is read or written.
"""
from __future__ import annotations

import json

import pytest

from laplace.core import checkout
from laplace.web import authoring as controller
from laplace.writing import session_reads
from laplace.writing import turn_jobs


def _fold():
    return {"sessions": {
        "WS-old": {"id": "WS-old", "project": "garden", "title": "Old finished", "role": "author",
                   "provider": "claude", "model": "default", "ts": "2026-11-01T09:00:00Z"},
        "WS-fail": {"id": "WS-fail", "project": "herbs", "title": "Failed one", "role": "author",
                    "provider": "codex", "model": "gpt", "ts": "2026-11-02T09:00:00Z"},
        "WS-run": {"id": "WS-run", "project": "garden", "title": "Running one", "role": "author",
                   "provider": "claude", "model": "default", "ts": "2026-10-30T09:00:00Z"},
        "WS-child": {"id": "WS-child", "project": "garden", "title": "Child", "role": "author",
                     "provider": "claude", "model": "default", "ts": "2026-11-03T09:00:00Z"},
        "WS-wait": {"id": "WS-wait", "project": "herbs", "title": "Waiting", "role": "review",
                    "provider": "claude", "model": "default", "ts": "2026-10-29T09:00:00Z"},
        "WS-empty": {"id": "WS-empty", "project": "herbs", "title": None, "ts": "2026-11-04T09:00:00Z"}},
        "turns": {
        "WT-o": {"id": "WT-o", "session_id": "WS-old", "ts": "2026-11-01T09:01:00Z", "mode": "discuss",
                 "reply": {"status": "completed", "ts": "2026-11-01T09:02:00Z"}},
        "WT-f": {"id": "WT-f", "session_id": "WS-fail", "ts": "2026-11-02T09:01:00Z",
                 "tool_failures": [{"id": "F1"}, {"id": "F2"}],
                 "reply": {"status": "failed", "error": "Provider stopped", "ts": "2026-11-02T09:03:00Z"}},
        "WT-r0": {"id": "WT-r0", "session_id": "WS-run", "ts": "2026-10-30T09:01:00Z",
                  "reply": {"status": "completed"}},
        "WT-r1": {"id": "WT-r1", "session_id": "WS-run", "ts": "2026-10-30T10:00:00Z"},
        "WT-c": {"id": "WT-c", "session_id": "WS-child", "ts": "2026-11-03T09:01:00Z",
                 "parent_turn_id": "WT-r0", "dispatch_id": "D-1", "reply": {"status": "interrupted"}},
        "WT-w": {"id": "WT-w", "session_id": "WS-wait", "ts": "2026-10-29T09:01:00Z",
                 "proposal_versions": {"v1": {}}, "reply": {"status": "completed"}}}}


@pytest.fixture
def index(tmp_path, monkeypatch):
    monkeypatch.setattr(checkout, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(session_reads, "_records", lambda _root: _fold())
    monkeypatch.setattr(turn_jobs, "active_work_projection", lambda runs=(), limit=16: ([
        {"kind": "turn", "project": "garden", "session_id": "WS-run", "turn_id": "WT-r1"},
        {"kind": "research-run", "project": "garden", "session_id": None}], 0))

    def read(**query):
        status, _content, body = controller.handle(
            "/authoring/state", {"view": ["all-sessions"], **{k: [v] for k, v in query.items()}}, "GET", b"")
        return status, json.loads(body)
    return read


def test_lists_every_project_live_first_then_waiting_then_newest(index):
    status, value = index()
    assert status == 200 and value["schema_version"] == "laplace.session-index/1"
    assert [row["session_id"] for row in value["sessions"]] == [
        "WS-run", "WS-wait", "WS-empty", "WS-child", "WS-fail", "WS-old"]
    assert value["counts"] == {"all": 6, "running": 1, "waiting": 1, "failed": 1}
    assert value["projects"] == [{"project": "garden", "sessions": 3}, {"project": "herbs", "sessions": 3}]
    run = value["sessions"][0]
    assert run["state"] == "running" and run["active"] == {"kind": "turn", "turn_id": "WT-r1", "since": "2026-10-30T10:00:00Z"}
    assert run["turn_count"] == 2 and run["last_turn"]["turn_id"] == "WT-r1"


def test_states_reasons_failures_and_parent_are_copied_from_records(index):
    _status, value = index()
    rows = {row["session_id"]: row for row in value["sessions"]}
    assert rows["WS-fail"]["state"] == "failed" and rows["WS-fail"]["last_turn"]["error"] == "Provider stopped"
    assert rows["WS-fail"]["tool_failures"] == 2 and rows["WS-fail"]["last_turn"]["ended_at"] == "2026-11-02T09:03:00Z"
    assert rows["WS-old"]["state"] == "completed" and rows["WS-old"]["active"] is None
    assert rows["WS-child"]["state"] == "interrupted"
    assert rows["WS-child"]["parent"] == {"turn_id": "WT-r0", "session_id": "WS-run", "title": "Running one", "dispatch_id": "D-1"}
    assert rows["WS-wait"]["state"] == "waiting" and rows["WS-wait"]["last_turn"]["awaiting_proposal_decision"] is True
    assert rows["WS-empty"]["state"] == "no-turn" and rows["WS-empty"]["last_turn"] is None


def test_project_and_state_filters_and_paging(index):
    _status, value = index(project="herbs")
    assert value["project"] == "herbs" and value["counts"] == {"all": 3, "running": 0, "waiting": 1, "failed": 1}
    assert {row["project"] for row in value["sessions"]} == {"herbs"}
    _status, value = index(state="failed")
    assert [row["session_id"] for row in value["sessions"]] == ["WS-fail"] and value["counts"]["all"] == 6
    _status, value = index(limit="2", offset="2")
    assert [row["session_id"] for row in value["sessions"]] == ["WS-empty", "WS-child"]
    assert value["next_offset"] == 4 and value["total"] == 6
    status, value = index(state="everything")
    assert status == 409 and "running, waiting or failed" in value["error"]


def test_existing_sessions_view_is_unchanged(index):
    status, _content, body = controller.handle("/authoring/state", {"project": ["garden"], "view": ["sessions"]}, "GET", b"")
    value = json.loads(body)
    assert status == 200 and value["session_count"] == 3 and set(value) == {"project", "sessions", "session_count"}
