"""ONE TRUTH for the desk brief banner (stranger-walk finding, banked leg F, 2026-07-23):
"the brief banner ('nothing needs you right now — your desk is quiet') directly
contradicts the item's own 'a finding is waiting on your adjudication' one screen below
it." The banner's quiet-or-not gate used to read ``his`` (:func:`_owed_top_rows`, joined
from ``project_state.owed_to_author`` per project — a SECOND, independently-sourced read)
while the per-class rows/chips one screen below are built straight from ``_desk_feedback``
/ ``_desk_forks`` / ``_desk_proxy`` / ``_desk_lifts`` — the two could disagree, so the
banner could say "quiet" while a him-owned class chip sat right below it, nonzero, naming
the very decision the banner denied.

The fix makes the banner a PURE FUNCTION of ``his_move`` — the count :func:`_desk` derives
from those SAME direct class reads — never of the separately-sourced ``top`` strip. These
tests exercise both the pure composer (:func:`_compose_brief_prose`) and the brief endpoint
(:func:`_desk_brief`) wired against a hand-composed desk read-model, so the contract holds
independent of the live registry.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def _desk_mod():
    desk = importlib.import_module("laplace.web.desk")
    return importlib.reload(desk)


# --------------------------------------------------------------------------- #
# _compose_brief_prose — the pure composer, gated on ``his_move`` (the class-read count),
# never on ``len(his)`` (the separately-sourced top strip).
# --------------------------------------------------------------------------- #
def test_quiet_when_every_author_owed_class_is_empty():
    desk = _desk_mod()
    glance = desk._compose_brief_prose([], 0, 0, 0)
    assert "quiet" in glance
    assert "nothing needs you" in glance


def test_not_quiet_when_an_author_owed_class_is_nonempty_even_with_no_named_lead():
    """THE EXACT STRANGER-WALK CONTRADICTION: an adjudication sits in its class (his_move
    counts it) but the separately-sourced top strip never resolved it into ``his`` (a
    project_state.owed_to_author join miss/drift). The banner must NOT claim quiet."""
    desk = _desk_mod()
    glance = desk._compose_brief_prose([], 1, 1, 0)  # his=[] (drift), his_move=1
    assert "quiet" not in glance
    assert "1 decision" in glance


def test_not_quiet_and_names_the_lead_when_top_strip_agrees():
    desk = _desk_mod()
    his = [{"class": "adjudications", "glance": "a finding is waiting on your adjudication",
            "title": "finding F1"}]
    glance = desk._compose_brief_prose(his, 1, 1, 0)
    assert "quiet" not in glance
    assert "a finding is waiting on your adjudication" in glance


def test_not_quiet_counts_from_his_move_not_from_the_top_strip_length():
    """his_move (3) outranks len(his) (1) as the count of record — the "more" tally can't
    silently drift from the true class-read count either."""
    desk = _desk_mod()
    his = [{"class": "adjudications", "glance": "lead item", "title": "lead"}]
    glance = desk._compose_brief_prose(his, 3, 3, 0)
    assert "quiet" not in glance
    assert "2 more" in glance  # his_move(3) - 1, not len(his)(1) - 1


# --------------------------------------------------------------------------- #
# _desk_brief — the endpoint wiring, driven against a hand-composed desk read-model (the
# shape :func:`_desk` returns) so the contract holds without touching the live registry
# that :func:`_owed_top_rows` reads from (``registry.all_projects()`` is process-global).
# --------------------------------------------------------------------------- #
def test_desk_brief_quiet_when_desk_data_all_empty(monkeypatch):
    desk = _desk_mod()
    monkeypatch.setattr(desk, "_desk", lambda repo: {
        "top": [], "classes": [], "his_move": 0, "total": 0,
    })
    out = desk._desk_brief(Path("."))
    assert "quiet" in out["brief"]["glance"]
    assert out["his_move"] == 0


def test_desk_brief_not_quiet_when_a_him_class_is_nonempty(monkeypatch):
    """Composes desk data the way :func:`_desk` actually shapes it: an ``adjudications``
    class chip (owner "him") carrying a count, the SAME data the page renders as a chip
    with its "why" text — and the drifted top strip empty, reproducing the exact reported
    contradiction. The banner must not say quiet."""
    desk = _desk_mod()
    monkeypatch.setattr(desk, "_desk", lambda repo: {
        "top": [],  # the drifted owed_to_author join: resolves nothing
        "classes": [
            {"class": "adjudications", "label": "his adjudications", "owner": "him",
             "count": 1, "store": "feedback", "shown": 1, "more": 0, "more_href": None},
        ],
        "his_move": 1,
        "total": 1,
    })
    out = desk._desk_brief(Path("."))
    assert "quiet" not in out["brief"]["glance"]
    assert out["his_move"] == 1


def test_desk_brief_engine_only_classes_stay_quiet(monkeypatch):
    """An engine-owned class (read-only exhaust, never his to fire) carrying rows does NOT
    break quiet — only author-owed classes count, preserving the him/engine split intent."""
    desk = _desk_mod()
    monkeypatch.setattr(desk, "_desk", lambda repo: {
        "top": [],
        "classes": [
            {"class": "work-orders", "label": "open work-orders", "owner": "engine",
             "count": 4, "store": "work_orders", "shown": 4, "more": 0, "more_href": None},
        ],
        "his_move": 0,
        "total": 4,
    })
    out = desk._desk_brief(Path("."))
    assert "quiet" in out["brief"]["glance"]
    assert "4 engine item" in out["brief"]["glance"]


def test_missing_work_order_store_is_a_loud_desk_row(tmp_path):
    desk = _desk_mod()
    got = desk._desk_workorders(tmp_path)
    assert got["degraded"] is True and got["count"] == 1
    assert got["rows"][0]["id"] == "work-orders-integrity"
    assert got["rows"][0]["fields"]["integrity"] == "wounded"
