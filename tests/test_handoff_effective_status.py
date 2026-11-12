"""tests/test_handoff_effective_status.py — WO-20260820-ledger-semantics-hardening,
cure (a) at the render: the handoff's ledger delta and its live-agenda "open:" line
read the EFFECTIVE status (the RES-row join), never the raise-time stored field.

The failure this pins: a work-order raised and consumed in the SAME close carries
status "open" on disk forever — the field is written at mint and never rewritten — so
the next instance picked it up off the agenda as live work that was already done.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from laplace.engine import handoff_render


def _write(root: Path, rel: str, rows: list[dict]) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


REL = "corpus_friction/work_orders.jsonl"


def _delta(tmp_path: Path, rows: list[dict], since: str | None = None) -> dict:
    _write(tmp_path, REL, rows)
    return handoff_render.ledger_delta(tmp_path, REL, since)


def test_consumed_row_carries_effective_status_and_keeps_the_stored_one(tmp_path: Path):
    rows = [{"kind": "work-order", "id": "WO-x", "status": "open",
             "ts": "2026-08-20T10:00:00Z", "what": "a thing"},
            {"record": "resolution", "id": "RES-x", "consumes": "WO-x",
             "ts": "2026-08-20T11:00:00Z", "text": "landed",
             "evidence": ["commit:x"]}]
    line = _delta(tmp_path, rows)["buckets"]["raised"][0]
    assert line["status"] == "open", "the stored raise-time field is never rewritten"
    assert line["effective"] == "resolved"
    assert line["status_reason"] == "consumed_by:RES-x"


def test_unconsumed_row_stays_open(tmp_path: Path):
    rows = [{"kind": "work-order", "id": "WO-y", "status": "open",
             "ts": "2026-08-20T10:00:00Z", "what": "still live"}]
    line = _delta(tmp_path, rows)["buckets"]["raised"][0]
    assert (line["effective"], line["status_reason"]) == ("open", "stored")


def test_index_is_built_from_the_whole_file_not_the_window(tmp_path: Path):
    """The resolution can sit OUTSIDE the delta window and still close the row —
    a window-local index would report the row open."""
    rows = [{"kind": "work-order", "id": "WO-z", "status": "open",
             "ts": "2026-08-20T10:00:00Z", "what": "raised in-window"},
            {"record": "resolution", "id": "RES-z", "consumes": "WO-z",
             "ts": "2026-08-19T09:00:00Z", "text": "closed before the mark",
             "evidence": ["commit:z"]}]
    delta = _delta(tmp_path, rows, since="2026-08-20T00:00:00Z")
    raised = delta["buckets"]["raised"]
    assert [r["id"] for r in raised] == ["WO-z"]
    assert raised[0]["effective"] == "resolved"


def test_still_open_filters_the_consumed_row_out_of_the_agenda_line(tmp_path: Path):
    rows = [{"kind": "work-order", "id": "WO-done", "status": "open",
             "ts": "2026-08-20T10:00:00Z", "what": "done same day"},
            {"record": "resolution", "id": "RES-done", "consumes": "WO-done",
             "ts": "2026-08-20T11:00:00Z", "text": "landed",
             "evidence": ["commit:done"]},
            {"kind": "work-order", "id": "WO-live", "status": "open",
             "ts": "2026-08-20T10:05:00Z", "what": "genuinely open"}]
    delta = _delta(tmp_path, rows)
    live = [r["id"] for r in delta["buckets"]["raised"] if handoff_render._still_open(r)]
    assert live == ["WO-live"]


def test_still_open_falls_back_to_the_stored_field(tmp_path: Path):
    assert handoff_render._still_open({"status": "open"})
    assert handoff_render._still_open({"status": ""})
    assert not handoff_render._still_open({"status": "resolved"})
    assert not handoff_render._still_open({"status": "open", "effective": "resolved"})


def test_delta_lines_state_the_drift_in_place(tmp_path: Path):
    rows = [{"kind": "work-order", "id": "WO-d", "status": "open",
             "ts": "2026-08-20T10:00:00Z", "what": "drifted"},
            {"record": "resolution", "id": "RES-d", "consumes": "WO-d",
             "ts": "2026-08-20T11:00:00Z", "text": "landed",
             "evidence": ["commit:d"]}]
    text = "\n".join(handoff_render._delta_lines(_delta(tmp_path, rows)))
    assert "open→resolved consumed_by:RES-d" in text
