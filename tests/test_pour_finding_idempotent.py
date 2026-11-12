"""bite-zero-judge (Leg A) — ``ledger.pour_finding`` is the sanctioned reader→ledger
door AND it is idempotent; the harnessed flow's reader pour routes THROUGH it.

Two mechanism guards the judge indicted:
  1. re-pouring the same finding must not deposit a SECOND live record sharing the
     one deterministic finding_id (a "double-live" the supersede mechanics can never
     disambiguate) — the second pour is a no-op returning the existing live twin.
  2. the harnessed reader-pour stage (``harnessed_stage.py pour``) banks reader
     findings through ``pour_finding`` (id repair + section anchor + idempotence),
     never ``append_jsonl`` directly.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from laplace.pipeline import ledger as L
from laplace.pipeline import adjudicate as ADJ

import planted_fixture as pf

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 1. pour_finding is idempotent on a live record
# ---------------------------------------------------------------------------

def _reader_finding(**over):
    f = {"reader": "R1", "kind": "cold-undefined-term",
         "section": "N2", "anchor": {"section": "N2"},
         "where": "N2-p1 the term is used before it is defined", "issue": "undefined"}
    f.update(over)
    return f


def test_double_pour_of_the_same_finding_is_one_live_record(tmp_path):
    fb = tmp_path / "fb.jsonl"
    a = L.pour_finding(fb, _reader_finding(), project="p")
    b = L.pour_finding(fb, _reader_finding(), project="p")     # identical re-pour
    assert a["id"] == b["id"]                                   # deterministic id
    recs = L.read_jsonl(fb)
    live = [r for r in recs if r.get("id") == a["id"]]
    assert len(live) == 1, "the second pour must be a no-op, not a double-live"


def test_distinct_findings_both_land(tmp_path):
    fb = tmp_path / "fb.jsonl"
    L.pour_finding(fb, _reader_finding(issue="one"), project="p")
    L.pour_finding(fb, _reader_finding(where="N2-p2 a different span", issue="two"),
                   project="p")
    assert len([r for r in L.read_jsonl(fb) if r.get("record") is None
                or r.get("kind") == "cold-undefined-term"]) == 2


def test_resolved_prior_does_not_block_a_recurred_repour(tmp_path):
    # a finding that was RESOLVED then recurs re-opens honestly (the idempotence
    # guard is on LIVE records only, never a spent one).
    fb = tmp_path / "fb.jsonl"
    first = L.pour_finding(fb, _reader_finding(), project="p")
    # supersede it with a resolution (the spent-record gesture)
    L.append_jsonl(fb, ADJ.make_resolution(first["id"], project="p"))
    again = L.pour_finding(fb, _reader_finding(), project="p")
    assert again["id"] == first["id"]
    # the recurred pour DID append (the prior is superseded/spent, not live)
    assert sum(1 for r in L.read_jsonl(fb)
               if r.get("kind") == "cold-undefined-term") == 2


# ---------------------------------------------------------------------------
# 2. the harnessed reader-pour stage routes THROUGH the door
# ---------------------------------------------------------------------------

def test_harnessed_pour_stage_goes_through_pour_finding(tmp_path, monkeypatch):
    fb = tmp_path / "feedback.jsonl"
    proj = pf.make_project(name=pf.THROWAWAY)
    findings = [_reader_finding(reader="R1", issue="a"),
                _reader_finding(reader="R7", where="N3-p2 abrupt jump", issue="b")]
    import json
    ret = pf.run_harnessed("pour", [str(fb), "p", "-"], monkeypatch, proj,
                           stdin=json.dumps(findings))
    assert ret["ok"] is True and ret["poured"] == 2 and ret["refused"] == 0
    recs = L.read_jsonl(fb)
    # the DOOR's fingerprint: every poured record carries a repaired id AND a
    # stamped section anchor (append_jsonl would have preserved the raw shape).
    poured = [r for r in recs if r.get("kind") == "cold-undefined-term"]
    assert len(poured) == 2
    for r in poured:
        assert r.get("id"), "id must be repaired by the door"
        assert (r.get("anchor") or {}).get("section"), "section anchor must be stamped"


def test_harnessed_pour_stage_is_idempotent(tmp_path, monkeypatch):
    fb = tmp_path / "feedback.jsonl"
    proj = pf.make_project(name=pf.THROWAWAY)
    import json
    payload = json.dumps([_reader_finding()])
    pf.run_harnessed("pour", [str(fb), "p", "-"], monkeypatch, proj, stdin=payload)
    ret2 = pf.run_harnessed("pour", [str(fb), "p", "-"], monkeypatch, proj, stdin=payload)
    assert ret2["poured"] == 0 and ret2["idempotent_skipped"] == 1
    assert sum(1 for r in L.read_jsonl(fb)
               if r.get("kind") == "cold-undefined-term") == 1


def test_harnessed_pour_stage_refuses_a_section_less_finding(tmp_path, monkeypatch):
    fb = tmp_path / "feedback.jsonl"
    proj = pf.make_project(name=pf.THROWAWAY)
    import json
    bad = {"reader": "R1", "kind": "cold-undefined-term",
           "where": "no locatable token here", "issue": "z"}
    ret = pf.run_harnessed("pour", [str(fb), "p", "-"], monkeypatch, proj,
                           stdin=json.dumps([bad]))
    assert ret["ok"] is False and ret["refused"] == 1 and ret["poured"] == 0
