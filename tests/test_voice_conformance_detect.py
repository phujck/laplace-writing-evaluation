"""voice_conformance_detect.py -- the meso/macro authorial-conformance detector.

His durable brief (FEEDBACK_2026-07-11): a manuscript can be locally voiced yet
mesoscopically/macroscopically alien. This detector reads the conceptric (substrate
importance: thesis proximity, claim/result mass, draws in-degree, beats) against the
storyboard (rhetorical prominence: order, prose/plan mass, opening/closing slots) and
emits typed findings where the rank-orders disagree. Built on synthetic plan/conceptric
fixtures so each finding kind (buried-lead, inflated-minor, dependency-inversion,
mass-mismatch) fires deterministically and the clean case stays clean.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "voice_conformance_detect", ROOT / "scripts" / "voice_conformance_detect.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("voice_conformance_detect", mod)
    spec.loader.exec_module(mod)
    return mod


vcd = _load()

THESIS = ("the central separation contribution folds acquisition apart from interrogation "
          "the decisive architectural result the governing invention")


def _sec(sid, title, job, nodes, beats):
    return {"id": sid, "title": title, "job": job, "nodes_in_order": nodes,
            "beats": beats, "refs": [], "figures": [], "notes": ""}


def _node(nid, kind, label):
    return {"id": nid, "kind": kind, "label": label, "meta": {}}


def _kinds_of(rep):
    return {f["kind"] for f in rep["findings"]}


def _clean_plan_con():
    """A conforming manuscript: importance and prominence agree, deps flow forward.

    s1 (front, most beats) carries the central thesis contribution and is drawn upon by
    everyone; s2/s3 are supporting mechanisms of descending weight; s4 is a proper
    conclusion that restates the thesis, so its closing-slot prominence is earned. No
    forward dependencies (everything draws material established earlier).
    """
    sections = [
        {"id": "abstract", "title": "Abstract", "job": "summary", "nodes_in_order": [],
         "beats": [], "refs": [], "figures": []},
        _sec("s1", "The central separation contribution", THESIS,
             ["c_central", "r_result", "d_core"], ["c_central", "r_result", "d_core"]),
        _sec("s2", "First supporting mechanism", "a supporting mechanism block of apparatus",
             ["c_supp1", "d_supp1"], ["c_supp1", "d_supp1"]),
        _sec("s3", "Second supporting mechanism", "another supporting apparatus block",
             ["c_supp2"], ["c_supp2"]),
        # conclusion: restates the governing contribution -> earns its closing prominence
        _sec("s4", "Conclusion: the contribution restated",
             "the central separation contribution as the decisive architectural result",
             ["c_conclusion"], ["c_conclusion", "c_conclusion2"]),
    ]
    nodes = [
        _node("c_central", "claim", "the central separation contribution governing invention"),
        _node("r_result", "result", "the decisive architectural result"),
        _node("d_core", "def", "core acquisition interrogation definition"),
        _node("c_supp1", "claim", "supporting mechanism one"),
        _node("d_supp1", "def", "supporting definition one"),
        _node("c_supp2", "claim", "supporting mechanism two"),
        _node("c_conclusion", "result", "the central separation contribution decisive result"),
        {"id": "blueprint:spine", "kind": "domain", "label": "spine",
         "meta": {"thesis": THESIS}},
    ]
    # every supporting node draws the core -> core is foundational, deps flow forward
    edges = [
        {"src": "c_supp1", "dst": "d_core", "rel": "draws"},
        {"src": "c_supp2", "dst": "d_core", "rel": "draws"},
        {"src": "c_conclusion", "dst": "c_central", "rel": "draws"},
    ]
    plan = {"meta": {"project": "clean_fixture"}, "sections": sections,
            "appendices": [], "excluded_by_rule": []}
    con = {"nodes": nodes, "edges": edges, "health": {}}
    return plan, con


def test_clean_case_is_clean():
    plan, con = _clean_plan_con()
    rep = vcd.analyse(plan, con, None, mdir=None, threshold=2)
    assert rep["summary"]["n_findings"] == 0, rep["findings"]
    assert rep["prose_available"] is False  # no .tex -> plan-level degrade


def test_verdict_clean_sentinel(capsys):
    plan, con = _clean_plan_con()
    import json
    tmp = ROOT / "tests" / "_vcd_clean.plan.json"
    tmpc = ROOT / "tests" / "_vcd_clean.con.json"
    tmp.write_text(json.dumps(plan)); tmpc.write_text(json.dumps(con))
    try:
        rc = vcd.main(["--plan", str(tmp), "--conceptric", str(tmpc), "--threshold", "2"])
        out = capsys.readouterr().out
        assert rc == 0
        assert out.strip().splitlines()[-1] == "VERDICT=CLEAN"
    finally:
        tmp.unlink(); tmpc.unlink()


def test_buried_lead_fires():
    """The central, most-drawn-upon, thesis-carrying section is shoved to the back with
    tiny plan mass -> high importance, low prominence."""
    sections = [
        {"id": "abstract", "title": "Abstract", "job": "s", "nodes_in_order": [],
         "beats": [], "refs": [], "figures": []},
        _sec("s1", "Chatty preamble", "throat-clearing background with lots of words " * 20,
             ["l_a"], ["l_a", "l_a2", "l_a3"]),
        _sec("s2", "Filler", "more background filler discussion at length " * 20,
             ["l_b"], ["l_b", "l_b2", "l_b3"]),
        _sec("s3", "Filler two", "yet more discussion padding text here " * 20,
             ["l_c"], ["l_c", "l_c2"]),
        # the real contribution, buried last, one beat, terse job
        _sec("s4", "The central contribution", THESIS,
             ["c_central", "r_result", "d_core"], ["c_central"]),
    ]
    nodes = [
        _node("l_a", "limitation", "aside"), _node("l_b", "limitation", "aside"),
        _node("l_c", "limitation", "aside"),
        _node("c_central", "claim", "the central separation contribution governing invention"),
        _node("r_result", "result", "the decisive architectural result acquisition"),
        _node("d_core", "def", "core interrogation definition"),
        {"id": "blueprint:spine", "kind": "domain", "label": "spine",
         "meta": {"thesis": THESIS}},
    ]
    edges = [  # everyone draws the buried contribution -> it is maximally foundational
        {"src": "l_a", "dst": "c_central", "rel": "draws"},
        {"src": "l_b", "dst": "r_result", "rel": "draws"},
        {"src": "l_c", "dst": "d_core", "rel": "draws"},
    ]
    plan = {"meta": {"project": "buried_fixture"}, "sections": sections,
            "appendices": [], "excluded_by_rule": []}
    con = {"nodes": nodes, "edges": edges, "health": {}}
    rep = vcd.analyse(plan, con, None, mdir=None, threshold=2)
    assert "buried-lead" in _kinds_of(rep)
    bl = [f for f in rep["findings"] if f["kind"] == "buried-lead"]
    assert any(f["section"] == "s4" for f in bl)
    # the buried section should be top substrate importance but low prominence
    f = next(f for f in bl if f["section"] == "s4")
    assert f["importance_rank"] < f["prominence_rank"]


def test_inflated_minor_fires():
    """A trivial limitation section sits up front with huge prose-space mass (a long job,
    NOT extra beats -- beats also feed substrate importance) while the central material is
    buried mid-paper. s1 is minor in substrate but maximally prominent."""
    sections = [
        {"id": "abstract", "title": "Abstract", "job": "s", "nodes_in_order": [],
         "beats": [], "refs": [], "figures": []},
        # minor content (one limitation, zero thesis-overlap, one beat) but front slot + a
        # huge job brief -> maximal rhetorical mass, minimal substrate weight
        _sec("s1", "Elaborate minor apparatus",
             "an elaborate peripheral apparatus digression at great length " * 20,
             ["l_a"], ["l_a"]),
        _sec("s2", "The central contribution", THESIS,
             ["c_central", "r_result", "d_core"], ["c_central", "r_result", "d_core"]),
        _sec("s3", "Body", "ordinary body block text here", ["c_x"], ["c_x"]),
        _sec("s4", "Body two", "another ordinary body block", ["c_y"], ["c_y"]),
    ]
    nodes = [
        _node("l_a", "limitation", "minor apparatus aside"),
        _node("c_central", "claim", "the central separation contribution governing invention"),
        _node("r_result", "result", "the decisive architectural result acquisition"),
        _node("d_core", "def", "core interrogation definition"),
        _node("c_x", "claim", "body claim x"), _node("c_y", "claim", "body claim y"),
        {"id": "blueprint:spine", "kind": "domain", "label": "spine",
         "meta": {"thesis": THESIS}},
    ]
    edges = [  # central material is drawn upon -> foundational, importance rank 1
        {"src": "c_x", "dst": "c_central", "rel": "draws"},
        {"src": "c_y", "dst": "r_result", "rel": "draws"},
    ]
    plan = {"meta": {"project": "inflated_fixture"}, "sections": sections,
            "appendices": [], "excluded_by_rule": []}
    con = {"nodes": nodes, "edges": edges, "health": {}}
    rep = vcd.analyse(plan, con, None, mdir=None, threshold=2)
    assert "inflated-minor" in _kinds_of(rep)
    im = [f for f in rep["findings"] if f["kind"] == "inflated-minor"]
    f = next(f for f in im if f["section"] == "s1")
    assert f["prominence_rank"] < f["importance_rank"]


def test_dependency_inversion_fires():
    """A claim in s1 draws a definition not established until s3 -> presentation precedes
    dependency."""
    sections = [
        {"id": "abstract", "title": "Abstract", "job": "s", "nodes_in_order": [],
         "beats": [], "refs": [], "figures": []},
        _sec("s1", "Uses the def early", "a block that leans on d_late",
             ["c_early"], ["c_early"]),
        _sec("s2", "Middle", "a middle block", ["c_mid"], ["c_mid"]),
        _sec("s3", "Defines it late", "where d_late is finally defined",
             ["d_late"], ["d_late"]),
    ]
    nodes = [
        _node("c_early", "claim", "early claim that needs the late definition"),
        _node("c_mid", "claim", "middle claim"),
        _node("d_late", "def", "the late definition"),
        {"id": "blueprint:spine", "kind": "domain", "label": "spine",
         "meta": {"thesis": THESIS}},
    ]
    edges = [{"src": "c_early", "dst": "d_late", "rel": "draws"}]
    plan = {"meta": {"project": "inversion_fixture"}, "sections": sections,
            "appendices": [], "excluded_by_rule": []}
    con = {"nodes": nodes, "edges": edges, "health": {}}
    rep = vcd.analyse(plan, con, None, mdir=None, threshold=2)
    di = [f for f in rep["findings"] if f["kind"] == "dependency-inversion"]
    assert di, rep["findings"]
    f = di[0]
    assert f["node"] == "c_early" and f["section"] == "s1"
    assert "d_late" in f["evidence"]


def test_dependency_inversion_from_reader_state():
    """reader_state introduce/use order is a second inversion source."""
    plan, con = _clean_plan_con()
    reader_state = {"project": "x", "nodes": {
        "some_param": {"introduced": "s3", "uses": ["s1"]}}}
    rep = vcd.analyse(plan, con, reader_state, mdir=None, threshold=2)
    di = [f for f in rep["findings"] if f["kind"] == "dependency-inversion"]
    assert any(f["node"] == "some_param" for f in di)


def test_mass_mismatch_needs_prose(tmp_path):
    """With realised .tex prose, a section whose prose mass rank is far from its importance
    rank fires mass-mismatch. Plan-level corpora never fire it."""
    sections = [
        {"id": "abstract", "title": "Abstract", "job": "s", "nodes_in_order": [],
         "beats": [], "refs": [], "figures": []},
        _sec("s1", "Central, starved of prose", THESIS,
             ["c_central", "r_result", "d_core"], ["c_central", "r_result"]),
        _sec("s2", "Minor, bloated prose", "a minor aside", ["l_a"], ["l_a"]),
        _sec("s3", "Body", "ordinary body", ["c_x"], ["c_x"]),
        _sec("s4", "Body two", "ordinary body two", ["c_y"], ["c_y"]),
    ]
    nodes = [
        _node("c_central", "claim", "the central separation contribution governing invention"),
        _node("r_result", "result", "the decisive architectural result acquisition"),
        _node("d_core", "def", "core interrogation definition"),
        _node("l_a", "limitation", "minor aside"),
        _node("c_x", "claim", "x"), _node("c_y", "claim", "y"),
        {"id": "blueprint:spine", "kind": "domain", "label": "spine",
         "meta": {"thesis": THESIS}},
    ]
    edges = [{"src": "l_a", "dst": "c_central", "rel": "draws"},
             {"src": "c_x", "dst": "r_result", "rel": "draws"}]
    plan = {"meta": {"project": "mass_fixture"}, "sections": sections,
            "appendices": [], "excluded_by_rule": []}
    con = {"nodes": nodes, "edges": edges, "health": {}}
    # realise prose: central section tiny, minor section huge
    (tmp_path / "s1.tex").write_text("Short.\n")
    (tmp_path / "s2.tex").write_text("word " * 400)
    (tmp_path / "s3.tex").write_text("word " * 40)
    (tmp_path / "s4.tex").write_text("word " * 40)
    rep = vcd.analyse(plan, con, None, mdir=str(tmp_path), threshold=2)
    assert rep["prose_available"] is True
    assert "mass-mismatch" in _kinds_of(rep)
    mm = [f for f in rep["findings"] if f["kind"] == "mass-mismatch"]
    # the central (important, starved) section is under-massed: prose rank >> importance rank
    assert any(f["section"] == "s1" and f["delta"] > 0 for f in mm)


def test_plan_level_never_fires_mass_mismatch():
    plan, con = _clean_plan_con()
    rep = vcd.analyse(plan, con, None, mdir=None, threshold=2)
    assert rep["prose_available"] is False
    assert "mass-mismatch" not in _kinds_of(rep)


def test_finding_schema_is_typed():
    """Every finding carries the contracted keys for the author's editor pass."""
    plan, con = _clean_plan_con()
    reader_state = {"project": "x", "nodes": {
        "p": {"introduced": "s3", "uses": ["s1"]}}}
    rep = vcd.analyse(plan, con, reader_state, mdir=None, threshold=2)
    for f in rep["findings"]:
        assert set(f) >= {"kind", "section", "node", "importance_rank",
                          "prominence_rank", "delta", "evidence"}
        assert f["kind"] in {"buried-lead", "inflated-minor",
                             "dependency-inversion", "mass-mismatch"}
