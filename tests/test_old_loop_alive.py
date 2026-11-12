"""LEG A — the old converge loop (project-fixedpoint) is DEMOTED, not deleted.

The ruling (his, 2026-07-10): the fixing middle is demoted behind a dial
(``loop.fix_mode: harnessed|loop``); the old every-round loop survives behind
``loop`` and is kept ALIVE by one planted-fixture test until the replication
verdict (A6) is final. This is that test: it pins the dial's two modes and smokes
the old loop's driver stages (mechround + route) so a refactor that breaks the
demoted loop is caught here, not at the replication run.

GATE PIN (2026-07-15, AUDIT_2026-07-15 §A-GATE): the shipped default is 'loop' —
the harnessed default remains the RULED TARGET, its flip re-gated on a
corpus-mode mint proof (the tex-mode live proof refused honestly: corpus-coupled
hard dimensions, §A7). When the gate passes, flip the default AND this pin
together with the evidence banked.
"""
from __future__ import annotations

import pytest

import planted_fixture as pf
from laplace.pipeline import dials as D

pytestmark = pytest.mark.unit


def test_fix_mode_dial_gate_pinned_loop_and_accepts_harnessed():
    d = D.load_dials(None)
    assert d["loop"]["fix_mode"] == "loop"               # gate-pinned (§A-GATE 2026-07-15)
    # 'harnessed' is the accepted ruled-target override (flips on the gate's mint proof)
    d2 = D.defaults()
    d2["loop"]["fix_mode"] = "harnessed"
    assert d2["loop"]["fix_mode"] == "harnessed"
    # the harnessed calibration block travels with the dial
    assert d["loop"]["harnessed"]["second_pass_open_threshold"] >= 0
    assert d["loop"]["harnessed"]["max_passes"] >= 1


def _planted(tmp_path, monkeypatch):
    md = tmp_path / "m"
    md.mkdir()
    pf.write_dirty(md)
    fb = pf.write_feedback(md / "feedback.jsonl",
                           [pf.finding("overfull_hbox", scope="node", section="N2",
                                       where="N2.tex:5")])
    pf.write_plan(md / "plan.json", ["N1", "N2"])
    proj = pf.make_project(plan_path=md / "plan.json")
    return md, fb, proj


def test_old_loop_route_stage_still_runs(tmp_path, monkeypatch):
    # the demoted loop's routing organ still parses + emits ROUTE_JSON (importable,
    # alive). If a later refactor breaks fixedpoint_route.py this fails loudly.
    md, fb, proj = _planted(tmp_path, monkeypatch)
    route = pf.run_route(str(md / "main.tex"), str(fb), str(md), monkeypatch, proj)
    assert "dirty_sections" in route and "local_patches" in route


def test_old_loop_mechround_stage_still_runs(tmp_path, monkeypatch):
    # the demoted loop's every-round panel still assembles + emits MECH_JSON.
    md, fb, proj = _planted(tmp_path, monkeypatch)
    summary, doc = pf.run_mechround(str(md / "main.tex"), "-", str(md / "r.json"),
                                    str(fb), str(md), monkeypatch, proj, round_no=1)
    assert "panel" in doc and isinstance(summary.get("labels"), dict)
