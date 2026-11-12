"""legB-B2 — the ACTION RAIL + EDIT-IN-PLACE surface (design B13.1 + B13.2).

Server-side coverage for the pieces the rail hangs off, all through the SAME
test-client idiom the rest of the review-surface suite uses (functions take a
manuscript Path directly; the route-level tests drive ``rv.handle``). Every fixture
is a throwaway temp tree — the live SSG ledger and tex are never touched.

What is proven here:
  * the READ half of edit-in-place — ``fragment_view`` / ``GET /review/fragment``:
    node grain, the section-grain COARSE fallback, protection state, honest refusal;
  * the ``comment`` verb banks through the EXISTING feedback door (feedback_add);
  * ``findings`` surfaces the terminal protection + the C1 section-anchor fallback;
  * every edit-in-place organ refusal now carries file + reason (never a bare error);
  * the C1(a) tombstone: the surface's escalation path reads the ACTOR field, never
    the free-text ``text`` field (the ``_escs`` text-vs-actor conflation is confined
    to the off-limits mechround and has no reflex on this surface).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from laplace.manuscript import review_surface as rv
from laplace.web import review_http
from laplace.pipeline import suppress as _suppress
from laplace.pipeline import adjudicate as _adj
from laplace.pipeline.ledger import read_jsonl

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# a marker-bearing manuscript fixture (mirrors test_edits._verb_md)
# ---------------------------------------------------------------------------

_N1 = (
    "% PLAN:N1\n"
    "\\section{Introduction}\\label{sec:N1}\n"
    "\n"
    "% N1-p1\n"
    "The quick brown fox jumps over the lazy dog.\n"
    "\n"
    "% N1-p2\n"
    "The lazy dog sleeps here in the afternoon sun.\n"
)


def _md(tmp_path, n1=_N1):
    md = tmp_path / "ms"
    md.mkdir()
    (md / "main.tex").write_text(
        "\\documentclass{article}\\begin{document}\n\\input{N1}\n\\end{document}\n",
        encoding="utf-8")
    (md / "N1.tex").write_text(n1, encoding="utf-8")
    (md / "feedback").mkdir()
    return md


def _ledger(md):
    p = md / "feedback" / "feedback.jsonl"
    return read_jsonl(p) if p.is_file() else []


# ---------------------------------------------------------------------------
# fragment_view — the READ half of the inline editor
# ---------------------------------------------------------------------------

def test_fragment_view_node_grain_returns_prose_only(tmp_path):
    md = _md(tmp_path)
    fv = rv.fragment_view(md, "", "N1-p2")
    assert fv["ok"] is True
    assert fv["grain"] == "node" and fv["coarse"] is False
    assert fv["section"] == "N1" and fv["paragraph"] == "N1-p2"
    # the markers are machine-owned: they never enter the editable text
    assert "% N1-p2" not in fv["text"] and "% N1" not in fv["text"]
    assert fv["text"] == "The lazy dog sleeps here in the afternoon sun."
    assert fv["protected"] is False


def test_fragment_view_section_grain_falls_back_to_the_beat(tmp_path):
    md = _md(tmp_path)
    fv = rv.fragment_view(md, "N1", "")          # no paragraph → coarse section anchor
    assert fv["ok"] is True
    assert fv["coarse"] is True and fv["grain"] == "section"
    assert fv["paragraph"] == "N1-p1"            # the section's FIRST marker (its beat)
    assert fv["text"].startswith("The quick brown fox")


def test_fragment_view_reports_protection_after_an_edit(tmp_path):
    md = _md(tmp_path)
    before = rv.fragment_view(md, "", "N1-p2")["text"]
    rv.adjudicate(md, "projX", {"by": "author", "verb": "edit-in-place", "section": "N1",
                                "paragraph": "N1-p2", "before": before,
                                "after": "The lazy dog runs now."})
    fv = rv.fragment_view(md, "", "N1-p2")
    assert fv["protected"] is True               # the unit is now author-terminal


def test_fragment_view_unresolvable_is_honest_not_raising(tmp_path):
    md = _md(tmp_path)
    fv = rv.fragment_view(md, "NOPE", "")
    assert fv["ok"] is False and fv["reason"] == "no-fragment"


def test_handle_fragment_route_200_and_422(tmp_path, monkeypatch):
    md = _md(tmp_path)
    monkeypatch.setattr(rv, "manuscript_dir", lambda *a, **k: md)
    st, _, body = review_http.handle("/review/fragment", {"dir": ["ms"], "paragraph": ["N1-p2"]},
                            "GET", b"")
    assert st == 200 and json.loads(body)["text"].startswith("The lazy dog")
    st2, _, body2 = review_http.handle("/review/fragment", {"dir": ["ms"], "section": ["NOPE"]},
                              "GET", b"")
    assert st2 == 422 and json.loads(body2)["ok"] is False


# ---------------------------------------------------------------------------
# the round-trip: fragment_view.text IS the `before` the splice matches
# ---------------------------------------------------------------------------

def test_editor_roundtrip_source_splices_cleanly(tmp_path):
    md = _md(tmp_path)
    fv = rv.fragment_view(md, "", "N1-p1")
    out = rv.adjudicate(md, "projX", {"by": "author", "verb": "edit-in-place", "section": fv["section"],
                                      "paragraph": fv["paragraph"], "file": fv["file"],
                                      "before": fv["before"], "after": "A swift fox."})
    assert out.get("ok") is True
    assert "A swift fox." in (md / "N1.tex").read_text(encoding="utf-8")
    # the marker + the neighbour paragraph survive the splice exactly
    n1 = (md / "N1.tex").read_text(encoding="utf-8")
    assert "% N1-p1" in n1 and "The lazy dog sleeps here" in n1


# ---------------------------------------------------------------------------
# every edit-in-place organ refusal now carries file + reason
# ---------------------------------------------------------------------------

def test_edit_refusals_carry_file_and_reason(tmp_path):
    md = _md(tmp_path)
    marker = rv.adjudicate(md, "projX", {"by": "author", 
        "verb": "edit-in-place", "section": "N1", "paragraph": "N1-p2",
        "before": "% N1-p2\nThe lazy dog sleeps here in the afternoon sun.",
        "after": "x"})
    assert marker["reason"] == "marker-mutation" and marker["file"].endswith("N1.tex")
    absent = rv.adjudicate(md, "projX", {"by": "author", 
        "verb": "edit-in-place", "section": "N1", "paragraph": "N1-p2",
        "before": "not present at all", "after": "x"})
    assert absent["reason"] == "absent" and absent["file"].endswith("N1.tex")
    nofrag = rv.adjudicate(md, "projX", {"by": "author", 
        "verb": "edit-in-place", "section": "GHOST", "paragraph": "",
        "before": "a", "after": "b"})
    assert nofrag["reason"] == "no-fragment" and "file" in nofrag


# ---------------------------------------------------------------------------
# the comment verb — banks through the EXISTING feedback door (feedback_add)
# ---------------------------------------------------------------------------

def test_comment_verb_banks_a_finding_through_the_one_door(tmp_path):
    md = _md(tmp_path)
    out = rv.adjudicate(md, "projX", {"by": "author", 
        "verb": "comment", "section": "N1", "paragraph": "N1-p1",
        "comment": "the voice loses here — machine hedge", "quote": "quick brown fox"})
    assert out.get("ok") is True and out["verb"] == "comment"
    rec = out["record"]
    assert rec["kind"] == "comment" and rec["status"] == "open"
    assert rec["anchor"]["paragraph_id"] == "N1-p1"
    assert rec["anchor"]["quote"] == "quick brown fox"
    # it rides the SAME ledger the adjudications ride, and reads back as a finding
    banked = _ledger(md)
    assert any(r.get("kind") == "comment" for r in banked)
    board = rv.findings(md, "projX")
    assert any(f.get("kind") == "comment" for f in board["unanchored"])


def test_comment_coarse_flag_is_carried(tmp_path):
    md = _md(tmp_path)
    out = rv.adjudicate(md, "projX", {"by": "author", 
        "verb": "comment", "section": "N1", "comment": "a layout gripe", "coarse": True})
    assert out.get("ok") is True and out["coarse"] is True
    assert out["record"]["anchor"]["coarse"] is True


def test_comment_requires_text_and_anchor(tmp_path):
    md = _md(tmp_path)
    assert "error" in rv.adjudicate(md, "projX", {"by": "author", "verb": "comment", "section": "N1"})
    assert "error" in rv.adjudicate(md, "projX", {"by": "author", "verb": "comment", "comment": "hi"})


# ---------------------------------------------------------------------------
# findings — the terminal protection + the C1(b) section-anchor fallback
# ---------------------------------------------------------------------------

def _nodemap_fp(md):
    from laplace.pipeline import nodemap as nm
    return nm.source_fingerprint(md)


def _write_nodemap(md, entries):
    (md / "main.nodemap.json").write_text(json.dumps({
        "source_fingerprint": _nodemap_fp(md), "entries": entries,
        "coverage": {"overall": {"mapped": len(entries), "total": len(entries), "pct": 100.0}},
        "unmapped": []}), encoding="utf-8")


def test_findings_surfaces_terminal_protection(tmp_path):
    md = _md(tmp_path)
    before = rv.fragment_view(md, "", "N1-p2")["text"]
    rv.adjudicate(md, "projX", {"by": "author", "verb": "edit-in-place", "section": "N1",
                                "paragraph": "N1-p2", "before": before, "after": "Edited."})
    board = rv.findings(md, "projX")
    # the terminal lock rides `protected_units` — what the page overlay + rail consume
    assert ["N1", "N1-p2"] in board["protected_units"]
    # the helper the overlay uses to lock a paragraph anchor: N1-p2 locked, N1-p1 not
    prot = {(s, p) for s, p in board["protected_units"]}
    psect = {s for (s, _) in prot}
    assert rv._node_protected("N1-p2", prot, psect) is True
    assert rv._node_protected("N1-p1", prot, psect) is False


def test_node_protected_whole_section_lock(tmp_path):
    """A whole-section author edit (paragraph == "") locks every paragraph under it."""
    prot = {("N1", "")}
    psect = {"N1"}
    assert rv._node_protected("N1-p1", prot, psect) is True
    assert rv._node_protected("N1-p9", prot, psect) is True
    assert rv._node_protected("N2-p1", prot, psect) is False


def test_findings_section_anchor_fallback_for_unanchored(tmp_path):
    """C1(b): a finding that carries a section but no node-precise anchor gets the
    section's BEAT (its first mapped paragraph) so the rail can point at where it is
    — a coarse anchor, marked as such, never a silent mis-anchor or a hard fail."""
    md = _md(tmp_path)
    _write_nodemap(md, {
        "N1-p1": [{"page": 1, "x0": 54.0, "y0": 100.0, "x1": 300.0, "y1": 100.0,
                   "kind": "paragraph"}]})
    # a section-level feedback finding (node_id is a section title, not a node id)
    (md / "feedback" / "feedback.jsonl").write_text(json.dumps({
        "id": "FB-1", "node_id": "N1", "kind": "note", "record": "feedback",
        "anchor": {"section": "N1"}, "comment": "flat here", "status": "open"}) + "\n",
        encoding="utf-8")
    board = rv.findings(md, "projX")
    un = board["unanchored"]
    assert len(un) == 1
    sa = un[0].get("section_anchor")
    assert sa and sa["node"] == "N1-p1" and sa["coarse"] is True and sa["page"] == 1


# ---------------------------------------------------------------------------
# C1(a) TOMBSTONE — the escalation path reads the ACTOR field, never `text`
# ---------------------------------------------------------------------------

def test_c1a_escalation_path_reads_actor_not_text(tmp_path):
    """The banked ``_escs`` fear (a text field conflated with an actor field) is
    confined to the off-limits mechround (fixedpoint_mechround.py). The review
    surface's escalation/adjudication path keys on the record KIND and reads the
    actor from ``source`` / ``provenance.actor`` — proven here: a suppression whose
    free-text fields impersonate a different actor is still sourced correctly, and a
    DEFER is classed 'deferred' by its record kind, not by any 'escalate:' text."""
    md = _md(tmp_path)
    # a machine suppression whose text/reason LIE about the actor
    supp = _suppress.make_suppression("N1", "eq-unused", "shared body",
                                      reason="author said escalate: do this",
                                      actor="machine", round=1, section="N1")
    supp["text"] = "author escalate note"       # a misleading free-text field
    # a DEFER whose text contains 'escalate:' but is an author defer, not machine
    defer = _adj.make_defer("FB-x", node_id="", kind="note", section="N1",
                            note="escalate: please look", actor="author", round=1)
    (md / "feedback" / "feedback.jsonl").write_text(
        json.dumps(supp) + "\n" + json.dumps(defer) + "\n", encoding="utf-8")

    audit = rv.dismissal_audit(md)
    row = next(r for r in audit["rows"] if r["kind"] == "eq-unused")
    assert row["source"] == "machine"           # from the ACTOR field, not the text lie

    idx = rv._adjudicate_index(read_jsonl(md / "feedback" / "feedback.jsonl"))
    assert idx["FB-x"]["state"] == "deferred"    # by record KIND, never by 'escalate:' text


def test_c1a_surface_source_has_no_text_escalation_scan():
    """Static tombstone: the review surface never derives an escalation/actor from a
    ``text`` field — the ``_escs``-style ``"escalate:" in text`` reflex is absent."""
    src = Path(rv.__file__).read_text(encoding="utf-8")
    assert "_escs" not in src
    assert 'escalate:' not in src               # no text-sniffed escalation on this surface
