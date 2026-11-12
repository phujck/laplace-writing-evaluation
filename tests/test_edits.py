"""BITE B4 — the TERMINAL rung: edit-in-place + structured edit capture + the
route's protection of the author's hand.

His ruling (2026-07-10): the interaction ladder is edit-in-place (TERMINAL, never
regenerated) → local patch → paragraph regen → section regen → substrate. An
author edit banks a before/after/anchor/kind record; the route never regenerates
over a protected unit.

The route tests drive the REAL ``.claude/workflows/fixedpoint_route.py`` via the
planted-fixture runpy idiom; the verb tests drive the REAL
``review_surface.adjudicate`` door on a tmp manuscript.
"""
from __future__ import annotations

import pytest

import planted_fixture as pf
from laplace.pipeline import edits
from laplace.pipeline.ledger import read_jsonl
from laplace.pipeline.suppress import content_fingerprint

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# a marker-bearing fixture manuscript: N1 carries six % N1-pN paragraphs
#   p1 [5,7]  p2 [8,11]  p3 [12,14]  p4 [15,17]  p5 [18,20]  p6 [21,22]
# ---------------------------------------------------------------------------

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
        rec["paragraph"] = paragraph
    return rec


def _edit(section, paragraph_id, **kw):
    return edits.make_author_edit(section, paragraph_id, f"{section}.tex",
                                  "old bytes", "new bytes", **kw)


def _n1_paras(route):
    return [e for e in (route.get("paragraph_regens") or []) if e["section"] == "N1"]


# ---------------------------------------------------------------------------
# (a) protection FORCES paragraph grain even for a DENSE fault, over the
#     UNPROTECTED units only — the protected paragraph is excluded
# ---------------------------------------------------------------------------

def test_protected_paragraph_demotes_dense_over_unprotected(tmp_path, monkeypatch):
    recs = [_para_finding(f"FB-{i}", paragraph=f"p{i}") for i in (1, 2, 3, 4, 5)]
    recs.append(_edit("N1", "N1-p3"))                     # the author's hand on p3
    env, fb, proj = _env(tmp_path, recs)
    r = pf.run_route(str(env / "main.tex"), str(fb), str(env), monkeypatch, proj)
    # 5 faulted units of 6 is DENSE (B3 alone would keep section grain); protection
    # overrides density because the author's hand must never be regenerated over.
    assert "N1" not in r["dirty_sections"]
    pids = {e["paragraph_id"] for e in _n1_paras(r)}
    assert pids == {"N1-p1", "N1-p2", "N1-p4", "N1-p5"}
    assert "N1-p3" not in pids                            # the protected unit is excluded
    assert ["N1", "N1-p3"] in r["protected_units"]
    assert r["protected_holds"] == []


# ---------------------------------------------------------------------------
# (b) a STRUCTURAL fault on a section with a protected paragraph would need
#     section grain -> the whole section is HELD for the author
# ---------------------------------------------------------------------------

def test_protected_paragraph_structural_fault_holds_section(tmp_path, monkeypatch):
    recs = [_para_finding("FB-1", paragraph="p2", kind="missing-content"),
            _edit("N1", "N1-p3")]
    env, fb, proj = _env(tmp_path, recs)
    dials = _dials(tmp_path, "regen_grain:\n  structural_kinds: [missing-content]\n")
    r = pf.run_route(str(env / "main.tex"), str(fb), str(env), monkeypatch, proj,
                     dials_path=dials)
    assert "N1" not in r["dirty_sections"]                # never regen over the hand
    assert _n1_paras(r) == []                             # no paragraph grain either
    held = [h for h in r["protected_holds"] if h["section"] == "N1"]
    assert held and "structural" in held[0]["reason"]


# ---------------------------------------------------------------------------
# (c) a WHOLE-SECTION edit (paragraph "") holds ALL regens on that section
# ---------------------------------------------------------------------------

def test_whole_section_edit_holds_all_regens(tmp_path, monkeypatch):
    # a sparse fault B3 would happily demote — protection holds it anyway.
    recs = [_para_finding("FB-1", paragraph="p2"),
            _edit("N1", "")]                              # whole-section edit
    env, fb, proj = _env(tmp_path, recs)
    r = pf.run_route(str(env / "main.tex"), str(fb), str(env), monkeypatch, proj)
    assert "N1" not in r["dirty_sections"]
    assert _n1_paras(r) == []                             # every regen on N1 held
    held = [h for h in r["protected_holds"] if h["section"] == "N1"]
    assert held and "whole-section" in held[0]["reason"]
    assert ["N1", ""] in r["protected_units"]


# ---------------------------------------------------------------------------
# (f) NO protection records -> route output byte-identical to the pre-B4 route:
#     the two protected keys are ABSENT (chosen shape) and B3 is untouched
# ---------------------------------------------------------------------------

def test_no_protection_records_route_unchanged(tmp_path, monkeypatch):
    recs = [_para_finding("FB-1", paragraph="p2")]        # sparse -> B3 demotes p2
    env, fb, proj = _env(tmp_path, recs)
    r = pf.run_route(str(env / "main.tex"), str(fb), str(env), monkeypatch, proj)
    assert "protected_units" not in r                     # ABSENT, not empty
    assert "protected_holds" not in r
    # B3 behaviour intact and unchanged:
    assert "N1" not in r["dirty_sections"]
    pr = _n1_paras(r)
    assert len(pr) == 1 and pr[0]["paragraph_id"] == "N1-p2"


# ===========================================================================
# the review-surface verb: applies the splice + banks the capture in one write
# ===========================================================================

_VERB_N1 = (
    "% PLAN:N1\n"
    "\\section{Method}\n"
    "\n"
    "% N1-p1\n"
    "The quick brown fox.\n"
    "\n"
    "% N1-p2\n"
    "The lazy dog sleeps here.\n"
)


def _verb_md(tmp_path, n1=_VERB_N1):
    md = tmp_path / "ms"
    md.mkdir()
    (md / "main.tex").write_text(
        "\\documentclass{article}\\begin{document}\n\\input{N1}\n\\end{document}\n",
        encoding="utf-8")
    (md / "N1.tex").write_text(n1, encoding="utf-8")
    return md


def _ledger(md):
    p = md / "feedback" / "feedback.jsonl"
    return read_jsonl(p) if p.is_file() else []


# ---------------------------------------------------------------------------
# (d) the splice applies EXACTLY ONCE; ambiguous/absent `before` is refused with
#     a structured error and NO ledger record
# ---------------------------------------------------------------------------

def test_edit_in_place_applies_splice_once_and_banks(tmp_path):
    import laplace.manuscript.review_surface as rs
    md = _verb_md(tmp_path)
    out = rs.adjudicate(md, "projX", {
        "by": "author", "verb": "edit-in-place", "section": "N1", "paragraph": "N1-p2",
        "before": "The lazy dog sleeps here.", "after": "The lazy dog runs now."})
    assert out.get("ok") is True and out["verb"] == "edit-in-place"
    assert "The lazy dog runs now." in (md / "N1.tex").read_text(encoding="utf-8")
    assert "The quick brown fox." in (md / "N1.tex").read_text(encoding="utf-8")
    recs = _ledger(md)
    assert len(recs) == 1 and recs[0]["record"] == "author-edit"


def test_edit_in_place_refuses_absent_before_no_record(tmp_path):
    import laplace.manuscript.review_surface as rs
    md = _verb_md(tmp_path)
    before = (md / "N1.tex").read_text(encoding="utf-8")
    out = rs.adjudicate(md, "projX", {
        "by": "author", "verb": "edit-in-place", "section": "N1", "paragraph": "N1-p2",
        "before": "text that is simply not present", "after": "x"})
    assert "error" in out and out.get("reason") == "absent" and out.get("count") == 0
    assert _ledger(md) == []                              # NO ledger record
    assert (md / "N1.tex").read_text(encoding="utf-8") == before   # bytes untouched


def test_edit_in_place_refuses_ambiguous_before_no_record(tmp_path):
    import laplace.manuscript.review_surface as rs
    n1 = _VERB_N1 + "\n% N1-p3\nrepeat me. repeat me.\n"
    md = _verb_md(tmp_path, n1)
    before = (md / "N1.tex").read_text(encoding="utf-8")
    out = rs.adjudicate(md, "projX", {
        "by": "author", "verb": "edit-in-place", "section": "N1", "paragraph": "N1-p3",
        "before": "repeat me.", "after": "x"})
    assert "error" in out and out.get("reason") == "ambiguous" and out.get("count") == 2
    assert _ledger(md) == []
    assert (md / "N1.tex").read_text(encoding="utf-8") == before


# ---------------------------------------------------------------------------
# (e) the banked record shape (status resolved, fingerprint over before,
#     provenance actor author) + protected_units replay from the raw ledger
# ---------------------------------------------------------------------------

def test_banked_record_shape_and_protected_units_replay(tmp_path):
    import laplace.manuscript.review_surface as rs
    md = _verb_md(tmp_path)
    before = "The lazy dog sleeps here."
    out = rs.adjudicate(md, "projX", {
        "by": "author", "verb": "edit-in-place", "section": "N1", "paragraph": "N1-p2",
        "before": before, "after": "The lazy dog runs.", "kind": "tighten",
        "round": 2})
    rec = out["record"]
    assert rec["record"] == "author-edit"
    assert rec["status"] == "resolved"                    # an edit is never work
    assert rec["fingerprint"] == content_fingerprint(before)
    assert rec["provenance"]["actor"] == "author"
    assert rec["provenance"]["verdict"] == "edit-in-place"
    assert rec["provenance"]["round"] == 2
    assert rec["kind"] == "tighten"
    assert rec["anchor"]["section"] == "N1"
    assert rec["anchor"]["paragraph_id"] == "N1-p2"
    # replay the protection straight from the raw ledger bytes:
    assert edits.protected_units(_ledger(md)) == {("N1", "N1-p2")}


def test_make_author_edit_shape_and_supersede_lifts_protection():
    e1 = edits.make_author_edit("N1", "N1-p2", "N1.tex", "a", "b", rec_id="EDIT-1")
    assert e1["record"] == "author-edit" and e1["status"] == "resolved"
    assert e1["fingerprint"] == content_fingerprint("a")
    assert edits.protected_units([e1]) == {("N1", "N1-p2")}
    # a superseding record retires the edit -> its protection lifts (append-only undo)
    rev = {"id": "EDIT-2", "record": "author-edit", "supersedes": "EDIT-1",
           "anchor": {}}
    assert e1 not in edits.live_edits([e1, rev])
    assert edits.protected_units([e1, rev]) == set()


def test_whole_section_protected_units_uses_empty_paragraph():
    e = edits.make_author_edit("N1", "", "N1.tex", "a", "b")
    assert edits.protected_units([e]) == {("N1", "")}


# ---------------------------------------------------------------------------
# the judge's refutation probes, banked: markers are machine-owned
# ---------------------------------------------------------------------------

def test_edit_cannot_delete_its_own_marker(tmp_path):
    """The proven end-to-end attack: an edit whose `before` swallows the
    % N1-p2 marker line would delete the very unit its protection names.
    The verb must refuse with reason marker-mutation, bytes untouched,
    no ledger record."""
    import laplace.manuscript.review_surface as rs
    md = _verb_md(tmp_path)
    original = (md / "N1.tex").read_text(encoding="utf-8")
    out = rs.adjudicate(md, "projX", {
        "by": "author", "verb": "edit-in-place", "section": "N1", "paragraph": "N1-p2",
        "before": "% N1-p2\nThe lazy dog sleeps here.",
        "after": "The lazy dog runs now."})
    assert "error" in out and out.get("reason") == "marker-mutation"
    assert (md / "N1.tex").read_text(encoding="utf-8") == original
    assert _ledger(md) == []


def test_edit_cannot_inject_a_marker(tmp_path):
    """The dual: `after` may not mint a structural line either."""
    import laplace.manuscript.review_surface as rs
    md = _verb_md(tmp_path)
    original = (md / "N1.tex").read_text(encoding="utf-8")
    out = rs.adjudicate(md, "projX", {
        "by": "author", "verb": "edit-in-place", "section": "N1", "paragraph": "N1-p2",
        "before": "The lazy dog sleeps here.",
        "after": "The lazy dog runs now.\n% N1-p9\nA smuggled unit."})
    assert "error" in out and out.get("reason") == "marker-mutation"
    assert (md / "N1.tex").read_text(encoding="utf-8") == original
    assert _ledger(md) == []
