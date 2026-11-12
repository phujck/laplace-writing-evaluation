"""Pure-Python contract tests for the /analytics surface — no browser.

Builds a synthetic manuscript dir with three harnessed rounds (r1, r2, r10 — the
r10 pins integer round ordering, not lexical) and drives ``analytics.handle``
directly. Asserts the per-project series is round-int ordered, findings-delta is
correct, and absent economics degrades to "never captured" (no fabricated 0). A
separate check holds the honesty contract on the live rollup: a NEVER_RUN project
carries an empty gate snapshot and "never captured" cost, never a zero-filled shell.
"""
from __future__ import annotations

import json

import pytest

from laplace.web import analytics

pytestmark = pytest.mark.unit


def _mech(rnd: int, hard: dict, opn: int, tmp) -> None:
    harnessed = tmp / "rounds" / "harnessed"
    harnessed.mkdir(parents=True, exist_ok=True)
    (harnessed / f"mech_r{rnd}.json").write_text(json.dumps({
        "round": rnd, "date": f"2026-07-{rnd:02d}",
        "contract": {"hard": hard, "soft": {"prose_flow": True}},
        "panel": [{"label": "meta_leak", "clean": hard.get("no_meta_leak", True), "flags": []}],
    }), encoding="utf-8")
    (harnessed / f"detect_post_r{rnd}.json").write_text(
        json.dumps({"open_findings_n": opn}), encoding="utf-8")


def _data(query: dict) -> dict:
    status, ctype, body = analytics.handle("/analytics/data", query, "GET", b"")
    assert status == 200, body
    assert "application/json" in ctype
    return json.loads(body)


def test_per_project_series_ordered_and_honest(tmp_path):
    _mech(1, {"semantic_identity": True, "no_meta_leak": True}, 50, tmp_path)
    _mech(2, {"semantic_identity": True, "no_meta_leak": True}, 40, tmp_path)
    _mech(10, {"semantic_identity": False, "no_meta_leak": True}, 30, tmp_path)

    led = _data({"project": [str(tmp_path)]})
    rounds = led["rounds"]
    # integer ordering: r10 sorts AFTER r2, not between r1 and r2
    assert [r["round"] for r in rounds] == [1, 2, 10]
    # findings-delta: r1 has no predecessor -> None; then -10, -10
    assert [r["findings_delta"] for r in rounds] == [None, -10, -10]
    # the hard gate flip lands at r10 (semantic_identity True -> False)
    assert rounds[-1]["gates"]["hard"]["semantic_identity"] == {
        "value": False, "from": True, "changed": True}
    # absent economics.json -> every round cost is the honest sentinel, never 0
    assert all(r["cost"] == "never captured" for r in rounds)


def test_unresolvable_project_is_404():
    status, ctype, body = analytics.handle(
        "/analytics/data", {"project": ["no_such_dir_xyz"]}, "GET", b"")
    assert status == 404
    assert "error" in json.loads(body)


def test_rollup_never_run_is_honest():
    roll = _data({})
    projects = roll["projects"]
    assert projects, "rollup returned no projects"
    zero = [p for p in projects if p["rounds_n"] == 0]
    assert zero, "expected at least one NEVER_RUN / zero-round project in the live repo"
    for p in zero:
        # zero rounds must render as absence, never a zero-filled contract snapshot
        assert p["hard"] == {}
        assert p["cost"]["status"] == "never captured"
        assert p["cost"]["total"] is None


def test_cost_rollup_splits_joined_and_econ_only():
    # one joined round + one orphaned econ-only round: total sums both, but the counts
    # split so the page can label the banked-but-orphaned cost honestly.
    rounds = [
        {"round": 1, "cost": 1.0},
        {"round": 6, "cost": 4.58, "econ_only": True},
    ]
    roll = analytics._cost_rollup(rounds)
    assert roll["status"] == "captured"
    assert roll["total"] == 5.58
    assert roll["captured_rounds"] == 1
    assert roll["econ_only_rounds"] == 1


def test_get_only():
    status, _, body = analytics.handle("/analytics/data", {}, "POST", b"")
    assert status == 405
    assert "read-only" in json.loads(body)["error"]


def test_page_served():
    status, ctype, body = analytics.handle("/analytics", {}, "GET", b"")
    assert status == 200
    assert "text/html" in ctype
    assert b"analytics" in body
