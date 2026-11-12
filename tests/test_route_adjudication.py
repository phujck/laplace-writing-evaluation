"""G-3 route wiring: the confirmed-exemption + per-instance defer respect in
``.claude/workflows/fixedpoint_route.py``, driven as the real script (the
planted-failure idiom: runpy in-process over a throwaway project).

The two additive rules over the class-grain defer filter:

  * a CONFIRMED finding rides through class-grain deferral (a confirmed
    ``eq-unused`` is real work — dispatch it even though its class is deferred);
  * a PER-INSTANCE defer record withholds its finding exactly like a class defer
    (reported, never dispatched).

Everything else stays byte-identical — no adjudication records means the route
behaves as before (the 12+8 verified properties hold; these tests only add).
"""
from __future__ import annotations

import pytest

import planted_fixture as pf
from laplace.pipeline import adjudicate as ADJ

pytestmark = pytest.mark.unit


def _env(tmp_path, records, sections=("N1", "N2")):
    env = tmp_path / "route"
    env.mkdir(parents=True, exist_ok=True)
    body = ("\\documentclass{article}\\begin{document}\n"
            + "".join(f"\\input{{{s}}}\n" for s in sections)
            + "\\end{document}\n")
    (env / "main.tex").write_text(body, encoding="utf-8")
    for s in sections:
        (env / f"{s}.tex").write_text(f"\\section{{{s}}}\nBody of {s}.\n",
                                      encoding="utf-8")
    pf.write_plan(env / "plan.json", list(sections))
    fb = pf.write_feedback(env / "feedback.jsonl", records)
    proj = pf.make_project(plan_path=env / "plan.json")
    return env, fb, proj


def _dials(tmp_path, defer_kinds):
    d = tmp_path / "dials.yaml"
    d.write_text("routing:\n  defer_kinds: [" + ", ".join(defer_kinds) + "]\n",
                 encoding="utf-8")
    return str(d)


# ---------------------------------------------------------------------------
# class-grain defer holds absent a confirmation (the baseline the exemption lifts)
# ---------------------------------------------------------------------------

def test_class_defer_holds_without_confirmation(tmp_path, monkeypatch):
    rec = pf.finding("eq-unused", section="N1", node_id="res:orphan-eq")
    env, fb, proj = _env(tmp_path, [rec])
    r = pf.run_route(str(env / "main.tex"), str(fb), str(env), monkeypatch, proj,
                     dials_path=_dials(tmp_path, ["eq-unused"]))
    assert r["deferred"] == 1
    assert "eq-unused" in r["deferred_kinds"]
    assert "N1" not in r["dirty_sections"]        # deferred → never dispatched


# ---------------------------------------------------------------------------
# VERB 1 — a CONFIRMED finding rides through class-grain deferral
# ---------------------------------------------------------------------------

def test_confirmed_finding_exempt_from_class_defer(tmp_path, monkeypatch):
    finding = pf.finding("eq-unused", section="N1", node_id="res:orphan-eq")
    confirm = ADJ.make_confirmation(finding["id"], node_id="res:orphan-eq",
                                    kind="eq-unused", round=1,
                                    project=pf.THROWAWAY)
    env, fb, proj = _env(tmp_path, [finding, confirm])
    r = pf.run_route(str(env / "main.tex"), str(fb), str(env), monkeypatch, proj,
                     dials_path=_dials(tmp_path, ["eq-unused"]))
    # the exemption: confirmed eq-unused is dispatched despite its deferred class
    assert r["deferred"] == 0
    assert "N1" in r["dirty_sections"]            # rides through → structural regen
    # the confirmation record itself is NOT re-counted as a finding
    assert r["kept"] == 1


# ---------------------------------------------------------------------------
# VERB 4 — a PER-INSTANCE defer withholds its finding like a class defer
# ---------------------------------------------------------------------------

def test_per_instance_defer_withholds_dispatch(tmp_path, monkeypatch):
    finding = pf.finding("missing-content", section="N1")
    # control: no defer → N1 is dirty (dispatched)
    env0, fb0, proj0 = _env(tmp_path / "a", [finding])
    r0 = pf.run_route(str(env0 / "main.tex"), str(fb0), str(env0), monkeypatch, proj0)
    assert "N1" in r0["dirty_sections"]

    defer = ADJ.make_defer(finding["id"], node_id="", kind="missing-content",
                           section="N1", round=1, project=pf.THROWAWAY)
    env1, fb1, proj1 = _env(tmp_path / "b", [finding, defer])
    r1 = pf.run_route(str(env1 / "main.tex"), str(fb1), str(env1), monkeypatch, proj1)
    assert r1["deferred"] == 1
    assert "N1" not in r1["dirty_sections"]       # per-instance defer respected
    assert "missing-content" in r1["deferred_kinds"]


# ---------------------------------------------------------------------------
# a confirmation WINS over a per-instance defer on the same finding (route rule)
# ---------------------------------------------------------------------------

def test_confirmation_beats_per_instance_defer(tmp_path, monkeypatch):
    finding = pf.finding("missing-content", section="N1")
    defer = ADJ.make_defer(finding["id"], kind="missing-content", section="N1",
                           project=pf.THROWAWAY)
    confirm = ADJ.make_confirmation(finding["id"], kind="missing-content",
                                    section="N1", project=pf.THROWAWAY)
    env, fb, proj = _env(tmp_path, [finding, defer, confirm])
    r = pf.run_route(str(env / "main.tex"), str(fb), str(env), monkeypatch, proj)
    assert r["deferred"] == 0
    assert "N1" in r["dirty_sections"]            # confirmation exempts, defer loses
