"""Leg C bite C1 — the adjudication step is EXPLICITLY inert (no silent no-op).

The banked fear: dial settings could make the machine-adjudication step a silent
no-op that still spent its dispatch. When the dials name NO adjudicable classes
(no ``routing.defer_kinds`` AND no ``machine_adjudication.may_dismiss``) but the
step is still enabled, the organ now short-circuits with an EXPLICIT evidence-file
note (``skipped: "no-adjudicable-classes"``) before touching the ledger or
gathering the manuscript — and the JS skips the dispatch entirely so the no-op
costs no agent spend. Proved here on the organ: nothing is banked, no residue is
written, and the skip note is stamped.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import planted_fixture as pf
from laplace.pipeline import dials as D

pytestmark = pytest.mark.unit


def test_inert_adjudication_writes_skip_note_and_banks_nothing(tmp_path, monkeypatch):
    md = tmp_path / "m"
    md.mkdir()
    (md / "main.tex").write_text(
        "\\documentclass{article}\\begin{document}\n\\input{N1}\n\\end{document}\n",
        encoding="utf-8")
    (md / "N1.tex").write_text(r"\section{A}\label{sec:a}" "\nProse.\n", encoding="utf-8")
    pf.write_plan(md / "plan.json", ["N1"])

    # an OPEN finding sits in the ledger — the skip must NOT bank over it
    fb = md / "feedback.jsonl"
    fb.write_text(json.dumps({"id": "F1", "record": "finding", "kind": "eq-unused",
                              "section": "N1", "status": "open", "ts": "t"}) + "\n",
                  encoding="utf-8")
    before = fb.read_bytes()

    # dials: ENABLED, but no deferred classes and no dismiss-permitted kinds -> inert
    monkeypatch.setattr(D, "load_dials", lambda p: {
        "machine_adjudication": {"enabled": True, "may_dismiss": [],
                                 "calibration_threshold": 5},
        "routing": {"defer_kinds": []}})

    proj = pf.make_project(plan_path=str(md / "plan.json"))
    res = pf.run_adjudicate(str(md / "main.tex"), str(fb), str(md), monkeypatch, proj)

    # the organ emits the explicit skip note, banks nothing
    assert res.get("skipped") == "no-adjudicable-classes"
    assert res.get("banked") == 0 and res.get("decided") == 0 and res.get("residue") == 0

    rd = md / "rounds" / "adjudicate_r1"
    verdicts = json.loads((rd / "verdicts.json").read_text(encoding="utf-8"))
    assert verdicts.get("skipped") == "no-adjudicable-classes"
    assert verdicts.get("banked") == 0
    assert not (rd / "residue.json").exists()     # no referee queue -> no spend

    # the ledger is byte-identical: the open finding was never ruled over
    assert fb.read_bytes() == before


def test_adjudicable_classes_present_still_runs(tmp_path, monkeypatch):
    """Control: with a deferred class present the organ does NOT short-circuit —
    it runs the Tier-1 pass (no skip note)."""
    md = tmp_path / "m"
    md.mkdir()
    (md / "main.tex").write_text(
        "\\documentclass{article}\\begin{document}\n\\input{N1}\n\\end{document}\n",
        encoding="utf-8")
    (md / "N1.tex").write_text(r"\section{A}\label{sec:a}" "\nProse.\n", encoding="utf-8")
    pf.write_plan(md / "plan.json", ["N1"])
    fb = md / "feedback.jsonl"
    fb.write_text("", encoding="utf-8")

    monkeypatch.setattr(D, "load_dials", lambda p: {
        "machine_adjudication": {"enabled": True, "may_dismiss": ["eq-unused"],
                                 "calibration_threshold": 5},
        "routing": {"defer_kinds": ["eq-unused"]}})

    proj = pf.make_project(plan_path=str(md / "plan.json"))
    res = pf.run_adjudicate(str(md / "main.tex"), str(fb), str(md), monkeypatch, proj)
    assert res.get("skipped") is None            # ran the real pass, no short-circuit
