"""BITE B3 — paragraph-grain regen: the density heuristic + pN routing + the
paragraph builder + sliced briefs.

His ruling (2026-07-10): a SPARSE section fault regenerates the offending
``% <SEC>-pN`` paragraph(s) through sliced briefs; a DENSE or STRUCTURAL fault
regenerates the section (today's path). Section grain was measured wildly blunt
for small faults.

The route tests drive the REAL ``.claude/workflows/fixedpoint_route.py`` via the
planted-fixture runpy idiom (``planted_fixture``); the ``_route_target`` test
execs the routing helpers straight out of ``fixedpoint_mechround.py``; the
paragraph-dispatch test slices the SAME narrative packet the section builder
receives.
"""
from __future__ import annotations

import json

import pytest

import planted_fixture as pf

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# a marker-bearing fixture manuscript: N1 carries six % N1-pN paragraphs
# ---------------------------------------------------------------------------

# line numbers (1-based) matter for the anchor-line mapping path:
#   p1 [5,7]  p2 [8,11]  p3 [12,14]  p4 [15,17]  p5 [18,20]  p6 [21,22]
_N1_SIX = (
    "% PLAN:N1\n"
    "% NODES:\n"
    "\\section{Method}\\label{sec:N1}\n"
    "\n"
    "% N1-p1\n"
    "Body of paragraph one about the method.\n"
    "\n"
    "% N1-p2\n"
    "% NODES: def:beta\n"
    "Body of paragraph two developing the idea.\n"
    "\n"
    "% N1-p3\n"
    "Body of paragraph three.\n"
    "\n"
    "% N1-p4\n"
    "Body of paragraph four.\n"
    "\n"
    "% N1-p5\n"
    "Body of paragraph five.\n"
    "\n"
    "% N1-p6\n"
    "Body of paragraph six closes it.\n"
)


def _env(tmp_path, records, sections=("N1", "N2")):
    env = tmp_path / "route"
    env.mkdir(parents=True, exist_ok=True)
    body = ("\\documentclass{article}\\begin{document}\n"
            + "".join(f"\\input{{{s}}}\n" for s in sections)
            + "\\end{document}\n")
    (env / "main.tex").write_text(body, encoding="utf-8")
    (env / "N1.tex").write_text(_N1_SIX, encoding="utf-8")
    for s in sections:
        if s != "N1":
            (env / f"{s}.tex").write_text(
                f"\\section{{{s}}}\nBody of {s}.\n", encoding="utf-8")
    pf.write_plan(env / "plan.json", list(sections))
    fb = pf.write_feedback(env / "feedback.jsonl", records)
    proj = pf.make_project(plan_path=env / "plan.json")
    return env, fb, proj


def _dials(tmp_path, body):
    d = tmp_path / "dials.yaml"
    d.write_text(body, encoding="utf-8")
    return str(d)


def _para_finding(fid, *, paragraph="", where="", node_id="", kind="missing-content"):
    rec = pf.finding(kind, section="N1", node_id=node_id, where=where, fid=fid)
    if paragraph:
        rec["paragraph"] = paragraph        # the additive mechround stamp
    return rec


# ---------------------------------------------------------------------------
# (a) two SPARSE faults (p2 via the stamped paragraph field, p5 via an anchor
#     line) -> N1 DEMOTES: two paragraph_regens, N1 leaves dirty_sections
# ---------------------------------------------------------------------------

def test_sparse_faults_demote_to_paragraph_grain(tmp_path, monkeypatch):
    recs = [_para_finding("FB-1", paragraph="p2"),
            _para_finding("FB-2", where="N1.tex:19")]      # line 19 sits in p5 [18,20]
    env, fb, proj = _env(tmp_path, recs)
    r = pf.run_route(str(env / "main.tex"), str(fb), str(env), monkeypatch, proj)
    assert "N1" not in r["dirty_sections"]                 # demoted out of the dirty set
    pr = r["paragraph_regens"]
    assert len(pr) == 2
    by_pid = {e["paragraph_id"]: e for e in pr}
    assert set(by_pid) == {"N1-p2", "N1-p5"}
    assert by_pid["N1-p2"]["marker"] == "% N1-p2"
    assert by_pid["N1-p2"]["line_range"] == [8, 11]
    assert by_pid["N1-p5"]["line_range"] == [18, 20]
    assert by_pid["N1-p2"]["item_ids"] and by_pid["N1-p5"]["item_ids"]
    assert by_pid["N1-p2"]["section"] == "N1"


# ---------------------------------------------------------------------------
# (b) DENSE fault: 4 faulted paragraphs of 6 (> 0.4*6 -> ceil 3) -> section grain
# ---------------------------------------------------------------------------

def test_dense_faults_stay_section_grain(tmp_path, monkeypatch):
    recs = [_para_finding(f"FB-{i}", paragraph=f"p{i}") for i in (1, 2, 3, 4)]
    env, fb, proj = _env(tmp_path, recs)
    r = pf.run_route(str(env / "main.tex"), str(fb), str(env), monkeypatch, proj)
    assert "N1" in r["dirty_sections"]                     # dense -> whole-section regen
    assert [e for e in r["paragraph_regens"] if e["section"] == "N1"] == []


# ---------------------------------------------------------------------------
# (c) a STRUCTURAL kind forces section grain even when sparse
# ---------------------------------------------------------------------------

def test_structural_kind_forces_section_grain(tmp_path, monkeypatch):
    recs = [_para_finding("FB-1", paragraph="p2", kind="missing-content")]
    env, fb, proj = _env(tmp_path, recs)
    dials = _dials(tmp_path, "regen_grain:\n  structural_kinds: [missing-content]\n")
    r = pf.run_route(str(env / "main.tex"), str(fb), str(env), monkeypatch, proj,
                     dials_path=dials)
    assert "N1" in r["dirty_sections"]                     # structural -> never a patch
    assert [e for e in r["paragraph_regens"] if e["section"] == "N1"] == []


# ---------------------------------------------------------------------------
# (d) mode: section is the KILL-SWITCH — byte-identical to the pre-B3 route
#     (the additive key is ABSENT and the section stays in dirty_sections)
# ---------------------------------------------------------------------------

def test_mode_section_kill_switch(tmp_path, monkeypatch):
    recs = [_para_finding("FB-1", paragraph="p2"),
            _para_finding("FB-2", paragraph="p5")]         # would demote in auto
    env, fb, proj = _env(tmp_path, recs)
    dials = _dials(tmp_path, "regen_grain:\n  mode: section\n")
    r = pf.run_route(str(env / "main.tex"), str(fb), str(env), monkeypatch, proj,
                     dials_path=dials)
    assert "paragraph_regens" not in r                     # additive key omitted
    assert "N1" in r["dirty_sections"]                     # today's behaviour restored


# ---------------------------------------------------------------------------
# (e) an UNMAPPABLE item (no paragraph field, no anchor line, no NODES match) ->
#     section grain (a whole-section fault we cannot localise stays section-grain)
# ---------------------------------------------------------------------------

def test_unmappable_item_stays_section_grain(tmp_path, monkeypatch):
    recs = [_para_finding("FB-1", where="unlocatable", node_id="def:absent")]
    env, fb, proj = _env(tmp_path, recs)
    r = pf.run_route(str(env / "main.tex"), str(fb), str(env), monkeypatch, proj)
    assert "N1" in r["dirty_sections"]
    assert [e for e in r["paragraph_regens"] if e["section"] == "N1"] == []


# a NODES-membership mapping DOES demote (def:beta named in p2's % NODES: comment)
def test_nodes_membership_maps_to_unit(tmp_path, monkeypatch):
    recs = [_para_finding("FB-1", node_id="def:beta")]     # only p2 names def:beta
    env, fb, proj = _env(tmp_path, recs)
    r = pf.run_route(str(env / "main.tex"), str(fb), str(env), monkeypatch, proj)
    assert "N1" not in r["dirty_sections"]
    pr = [e for e in r["paragraph_regens"] if e["section"] == "N1"]
    assert len(pr) == 1 and pr[0]["paragraph_id"] == "N1-p2"


# ---------------------------------------------------------------------------
# (f) _route_target parses 'N1-p3' and 'N1.tex:N1-p3' and yields the paragraph
#     (execed straight out of the real mechround source — no argv main run)
# ---------------------------------------------------------------------------

def _load_route_target():
    import re
    src = (pf.WORKFLOWS / "fixedpoint_mechround.py").read_text(encoding="utf-8")
    start = src.index("_FRAG_RE = re.compile")
    end = src.index("# --- BITE B2")
    ns: dict = {"re": re}
    exec(compile(src[start:end], "<mechround-routing>", "exec"), ns)
    return ns["_route_target"]


def test_route_target_parses_paragraph_variants():
    rt = _load_route_target()
    assert rt("N1-p3") == ("N1", "", "p3")
    assert rt("N1.tex:N1-p3") == ("N1", "", "p3")
    # a plain fragment / file:line where carries NO paragraph (additive, "" default)
    assert rt("N1") == ("N1", "", "")
    assert rt("N1.tex:24") == ("N1", "", "")


def test_route_target_stamps_paragraph_on_finding():
    """The pour deposits the pN as an additive `paragraph` field (the stamp the
    route heuristic reads); a non-paragraph where deposits no such field."""
    rt = _load_route_target()
    for where, expect in (("N1-p3", "p3"), ("N1.tex:N1-p3", "p3")):
        sec, node, para = rt(where)
        rec = {"section": sec, "node_id": node}
        if para:
            rec["paragraph"] = para
        assert rec.get("paragraph") == expect
    sec, node, para = rt("N1")
    rec = {"section": sec}
    if para:
        rec["paragraph"] = para
    assert "paragraph" not in rec


# ---------------------------------------------------------------------------
# (g) compile_paragraph_dispatch slices the packet to one unit's nodes + fences
# ---------------------------------------------------------------------------

_G_FRAG = (
    "% PLAN:N1\n% NODES:\n\\section{Method}\n\n"
    "% N1-p1\nFirst paragraph prose.\n\n"
    "% N1-p2\nSecond paragraph prose.\n\n"
    "% N1-p3\nThird paragraph prose.\n"
)

_G_PACKET = {
    "section_id": "N1", "contract": {},
    "paragraphs": [
        {"paragraph_id": "N1-p1", "input_nodes": ["def:a"], "equation_anchor": None},
        {"paragraph_id": "N1-p2", "input_nodes": ["def:b", "res:c"],
         "equation_anchor": "eq:2"},
        {"paragraph_id": "N1-p3", "input_nodes": ["def:d"], "equation_anchor": None},
    ],
    "objects": {"def:a": {"essence": "aaa"}, "def:b": {"essence": "bbb"},
                "res:c": {"essence": "ccc"}, "def:d": {"essence": "ddd"}},
    "equation_ledger": {"eq:2": {"section": "N1", "latex": "E=2"},
                        "eq:x": {"section": "N1", "latex": "E=x"}},
    "notation": [], "terminology": {}, "citations": {}, "genre": "white paper",
}


def test_compile_paragraph_dispatch_slices_to_unit(tmp_path, monkeypatch):
    from laplace.pipeline import dispatch, registry

    md = tmp_path / "ms"
    md.mkdir()
    (md / "N1.tex").write_text(_G_FRAG, encoding="utf-8")
    plan = md / "plan.json"
    pf.write_plan(plan, ["N1"])
    proj = pf.make_project(target_dir=str(md), plan_path=plan)

    monkeypatch.setattr(registry, "resolve",
                        lambda n: proj if n == proj.name else None)
    monkeypatch.setattr(dispatch.narrative, "narrative_packet",
                        lambda project, sid, repo_root=None: json.loads(json.dumps(_G_PACKET)))

    d = dispatch.compile_paragraph_dispatch(proj.name, "N1", "N1-p2")
    assert "error" not in d
    # ONLY p2's nodes are discharged; the neighbours' nodes are absent
    assert d["nodes"] == ["def:b", "res:c"]
    assert set(d["fences"]) == {"previous", "next"}
    prompt = d["prompt"]
    assert "def:b" in prompt and "res:c" in prompt and "eq:2" in prompt
    assert "def:a" not in prompt and "def:d" not in prompt   # neighbour nodes sliced out
    assert "eq:x" not in prompt                              # ledger narrowed to the anchor
    # the adjacent-paragraph FENCE carries the neighbours' rendered text (read-only)
    assert "First paragraph prose." in prompt                # p1 (previous)
    assert "Third paragraph prose." in prompt                # p3 (next)
    assert "N1-p2" in prompt


def test_compile_paragraph_dispatch_unknown_paragraph(tmp_path, monkeypatch):
    from laplace.pipeline import dispatch, registry
    md = tmp_path / "ms"
    md.mkdir()
    (md / "N1.tex").write_text(_G_FRAG, encoding="utf-8")
    plan = md / "plan.json"
    pf.write_plan(plan, ["N1"])
    proj = pf.make_project(target_dir=str(md), plan_path=plan)
    monkeypatch.setattr(registry, "resolve",
                        lambda n: proj if n == proj.name else None)
    monkeypatch.setattr(dispatch.narrative, "narrative_packet",
                        lambda project, sid, repo_root=None: json.loads(json.dumps(_G_PACKET)))
    d = dispatch.compile_paragraph_dispatch(proj.name, "N1", "N1-p9")
    assert "error" in d and "N1-p9" in d["error"]


# ---------------------------------------------------------------------------
# the judge's coverage-gap probes, folded in (all confirmed green in scratch)
# ---------------------------------------------------------------------------

def test_exact_ceil_boundary_demotes(tmp_path, monkeypatch):
    # 3 faulted units of 6: ceil(0.4*6) = 3, and 3 <= 3 -> DEMOTE
    recs = [_para_finding(f"FB-{i}", paragraph=f"p{i}") for i in (1, 3, 5)]
    env, fb, proj = _env(tmp_path, recs)
    r = pf.run_route(str(env / "main.tex"), str(fb), str(env), monkeypatch, proj)
    assert "N1" not in r["dirty_sections"]
    assert len([e for e in r["paragraph_regens"] if e["section"] == "N1"]) == 3


def test_zero_marker_section_stays_section_grain(tmp_path, monkeypatch):
    # a section with NO % <SEC>-pN markers must not demote and must not crash
    recs = [_para_finding("FB-1", where="N1.tex:3")]
    env, fb, proj = _env(tmp_path, recs)
    (env / "N1.tex").write_text(
        "% PLAN:N1\n\\section{Method}\nUnmarked prose only.\n", encoding="utf-8")
    r = pf.run_route(str(env / "main.tex"), str(fb), str(env), monkeypatch, proj)
    assert "N1" in r["dirty_sections"]
    assert [e for e in r["paragraph_regens"] if e["section"] == "N1"] == []


def test_two_items_same_unit_count_one_faulted_unit(tmp_path, monkeypatch):
    # two findings in p2 = ONE faulted unit (<= ceil) -> demote, both item_ids ride
    recs = [_para_finding("FB-1", paragraph="p2"),
            _para_finding("FB-2", paragraph="p2")]
    env, fb, proj = _env(tmp_path, recs)
    r = pf.run_route(str(env / "main.tex"), str(fb), str(env), monkeypatch, proj)
    pr = [e for e in r["paragraph_regens"] if e["section"] == "N1"]
    assert len(pr) == 1 and pr[0]["paragraph_id"] == "N1-p2"
    assert len(pr[0]["item_ids"]) == 2


def test_anchor_exactly_on_marker_line_maps_to_unit(tmp_path, monkeypatch):
    # line 8 IS the % N1-p2 marker line; start is inclusive -> maps to p2
    recs = [_para_finding("FB-1", where="N1.tex:8")]
    env, fb, proj = _env(tmp_path, recs)
    r = pf.run_route(str(env / "main.tex"), str(fb), str(env), monkeypatch, proj)
    pr = [e for e in r["paragraph_regens"] if e["section"] == "N1"]
    assert len(pr) == 1 and pr[0]["paragraph_id"] == "N1-p2"
