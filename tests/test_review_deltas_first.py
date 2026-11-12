"""W2.4 - /review deltas-first: the strata summary that first paint ships (bounded
≤16KB, no finding bodies), the failure signal riding the badge, tray-on-demand
returning exactly a stratum's findings, and the last-visit cursor on .cockpit.json
(nested-merged so his other cockpit keys survive).

Pure-logic over synthetic manuscript trees (the internal functions take a Path
directly) plus the scanner cockpit writer over a tmp repo root. No browser, no
LaTeX - the live render is the smoke.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from laplace.manuscript import review_surface as rv
from laplace.web import review_http
from laplace.web import scanner as sc

pytestmark = pytest.mark.unit

_SUMMARY_BUDGET = 16 * 1024


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

def _make(tmp_path: Path, feedback=None) -> Path:
    md = tmp_path / "wp"
    md.mkdir()
    (md / "main.tex").write_text(
        "\\documentclass{article}\\begin{document}x\\end{document}", encoding="utf-8")
    if feedback is not None:
        (md / "feedback").mkdir()
        (md / "feedback" / "feedback.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in feedback), encoding="utf-8")
    return md


def _fb(fid, kind, ts, comment="c"):
    # a node-less finding (lists unanchored, but still counts by class) - class is
    # decided by kind alone, so anchoring is irrelevant to the summary's counts.
    return {"id": fid, "node_id": "", "kind": kind,
            "anchor": {"section": "S1"}, "comment": comment, "ts": ts}


# ---------------------------------------------------------------------------
# 1. the summary is BOUNDED - first paint never ships the finding-body flood
# ---------------------------------------------------------------------------

def _size(obj) -> int:
    return len(json.dumps(obj, ensure_ascii=False).encode("utf-8"))


def test_summary_is_bounded_under_a_flood(tmp_path):
    # a 2000-finding board with fat comments would be a ~MB payload as bodies; the
    # summary must reduce it to counts and stay under the golden law.
    big = "x" * 400
    fb = [_fb(f"F{i}", "unsupported-claim" if i % 3 == 0 else "note",
              f"2026-07-{(i % 27) + 1:02d}T00:00:00Z", comment=big)
          for i in range(2000)]
    md = _make(tmp_path, feedback=fb)
    out = rv.summary(md, "big")
    assert _size(out) <= _SUMMARY_BUDGET, f"summary {_size(out)}B > {_SUMMARY_BUDGET}B"
    # the count is the FULL board (honest), but no finding body ships
    assert out["counts"]["total"] == 2000
    assert "by_node" not in out and "unanchored" not in out
    for s in out["strata"]:
        assert "findings" not in s          # a stratum is a count, never a body list


def test_summary_bounded_via_route_head(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "_repo_root", lambda: tmp_path)
    fb = [_fb(f"F{i}", "unsupported-claim", f"2026-07-01T00:00:{i % 60:02d}Z")
          for i in range(500)]
    md = _make(tmp_path, feedback=fb)
    monkeypatch.setattr(rv, "_resolve", lambda q: (md, "big", ""))
    status, ctype, body = review_http.handle("/review/summary", {}, "GET", b"")
    assert status == 200
    assert len(body) <= _SUMMARY_BUDGET


# ---------------------------------------------------------------------------
# 2. the FAILURE SIGNAL rides the badge - a red class is never a neutral count
# ---------------------------------------------------------------------------

def test_red_class_surfaces_in_the_badges(tmp_path):
    # fabricate ONE hard finding (a hard kind) in the fixture
    md = _make(tmp_path, feedback=[_fb("H1", "unsupported-claim", "2026-07-10T00:00:00Z")])
    out = rv.summary(md, "wp")
    hard = next(s for s in out["strata"] if s["id"] == "hard")
    assert hard["count"] == 1
    assert hard["failing"] is True             # the badge carries the failure
    assert hard["severity"] == "fail"
    assert out["failing"] is True              # the roll-up is red


def test_no_hard_no_red(tmp_path):
    md = _make(tmp_path, feedback=[_fb("S1", "note", "2026-07-10T00:00:00Z")])
    out = rv.summary(md, "wp")
    hard = next(s for s in out["strata"] if s["id"] == "hard")
    assert hard["count"] == 0 and hard["failing"] is False
    assert out["failing"] is False


def test_new_failure_reads_red_not_neutral(tmp_path):
    fb = [_fb("OLD", "unsupported-claim", "2026-07-01T00:00:00Z"),
          _fb("NEW", "unsupported-claim", "2026-07-10T00:00:00Z")]
    md = _make(tmp_path, feedback=fb)
    out = rv.summary(md, "wp", since="2026-07-05T00:00:00Z")
    hard = next(s for s in out["strata"] if s["id"] == "hard")
    assert hard["new"] == 1                     # one hard finding since the visit
    assert hard["new_failing"] is True          # and it reads as a NEW failure (red)
    assert out["new_failing"] is True


# ---------------------------------------------------------------------------
# 3. tray-on-demand returns EXACTLY the stratum's findings
# ---------------------------------------------------------------------------

def test_tray_on_demand_returns_exactly_the_stratum(tmp_path):
    fb = [_fb("H1", "unsupported-claim", "2026-07-10T00:00:00Z"),
          _fb("H2", "missing-derivation", "2026-07-10T00:00:01Z"),
          _fb("S1", "note", "2026-07-10T00:00:02Z"),
          _fb("S2", "note", "2026-07-10T00:00:03Z")]
    md = _make(tmp_path, feedback=fb)
    board = rv.findings(md, "wp")
    sliced = rv._board_head(board, cls="hard")
    got = [f for f in sliced["unanchored"]] + \
          [f for g in sliced["by_node"] for f in g["findings"]]
    assert {f["id"] for f in got} == {"H1", "H2"}      # exactly the hard stratum
    assert all(f["cls"] == "hard" for f in got)
    # the facet chips stay HONEST - counts are the full board, not the slice
    assert sliced["counts"]["hard"] == 2 and sliced["counts"]["soft"] == 2


def test_tray_on_demand_via_route(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "_repo_root", lambda: tmp_path)
    fb = [_fb("H1", "unsupported-claim", "2026-07-10T00:00:00Z"),
          _fb("S1", "note", "2026-07-10T00:00:02Z")]
    md = _make(tmp_path, feedback=fb)
    monkeypatch.setattr(rv, "_resolve", lambda q: (md, "wp", ""))
    status, _, body = review_http.handle("/review/findings", {"cls": ["hard"]}, "GET", b"")
    data = json.loads(body)
    ids = [f["id"] for f in data["unanchored"]] + \
          [f["id"] for g in data["by_node"] for f in g["findings"]]
    assert set(ids) == {"H1"}


# ---------------------------------------------------------------------------
# 4. last-visit persistence MERGES - his other cockpit keys survive
# ---------------------------------------------------------------------------

def test_last_visit_merges_and_preserves_cockpit_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "_repo_root", lambda: tmp_path)
    # his prior cockpit: an active project, a knob layout, and one other corpus cursor
    sc.cockpit_state({"active_corpus": "eigenengine",
                      "panel_layout": {"a": 1},
                      "review_last_visit": {"other": "2026-07-01T00:00:00Z"}})
    res = sc.record_review_visit("wp", "2026-07-10T00:00:00Z")
    assert res["ok"] is True and res["ts"] == "2026-07-10T00:00:00Z"
    st = sc.cockpit_state()
    # the NEW cursor landed
    assert st["review_last_visit"]["wp"] == "2026-07-10T00:00:00Z"
    # every OTHER cockpit key survives (top-level AND the sibling corpus cursor)
    assert st["active_corpus"] == "eigenengine"
    assert st["panel_layout"] == {"a": 1}
    assert st["review_last_visit"]["other"] == "2026-07-01T00:00:00Z"
    # the reader round-trips
    assert sc.review_last_visit("wp") == "2026-07-10T00:00:00Z"
    assert sc.review_last_visit("nope") == ""


def test_visit_cursor_is_monotone(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "_repo_root", lambda: tmp_path)
    sc.record_review_visit("wp", "2026-07-10T00:00:00Z")
    # a stale tab banking an OLDER ts must not move the baseline backward
    sc.record_review_visit("wp", "2026-07-01T00:00:00Z")
    assert sc.review_last_visit("wp") == "2026-07-10T00:00:00Z"


def test_visit_route_writes_cockpit(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "_repo_root", lambda: tmp_path)
    body = json.dumps({"corpus": "wp", "ts": "2026-07-10T00:00:00Z"}).encode()
    status, _, out = review_http.handle("/review/visit", {}, "POST", body)
    assert status == 200 and json.loads(out)["ok"] is True
    assert sc.review_last_visit("wp") == "2026-07-10T00:00:00Z"
    # a bare body (no ts) is a clean 400, never a silent no-op that reads OK
    status2, _, _ = review_http.handle("/review/visit", {}, "POST", b"{}")
    assert status2 == 400


def test_summary_route_reads_persisted_cursor(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "_repo_root", lambda: tmp_path)
    fb = [_fb("OLD", "unsupported-claim", "2026-07-01T00:00:00Z"),
          _fb("NEW", "unsupported-claim", "2026-07-10T00:00:00Z")]
    md = _make(tmp_path, feedback=fb)
    monkeypatch.setattr(rv, "_resolve", lambda q: (md, "wp", ""))
    sc.record_review_visit("wp", "2026-07-05T00:00:00Z")
    status, _, body = review_http.handle("/review/summary", {}, "GET", b"")
    out = json.loads(body)
    hard = next(s for s in out["strata"] if s["id"] == "hard")
    assert hard["new"] == 1                     # only NEW is newer than the cursor
    assert out["max_ts"] == "2026-07-10T00:00:00Z"   # client banks this next
    # the visit key helper mirrors the old localStorage basis
    assert rv._visit_key("wp") == "wp"
    assert rv._visit_key("", "some/dir") == "dir:some/dir"
