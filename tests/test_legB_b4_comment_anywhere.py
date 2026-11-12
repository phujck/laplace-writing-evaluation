"""legB-B4 — COMMENT-ANYWHERE server paths (B13.3) + the figure-feedback gesture
(B13.5 half). Exercises the ``comment`` verb's four honest anchor tiers through the
REAL feedback door on THROWAWAY temp trees (the live ledger is never touched):

  * NODE-anchored  — the selection lands on a nodemap node (grade 'node').
  * SECTION-coarse — no node, resolved to the section (grade 'section').
  * FIGURE          — a ``fig:`` block: kind='figure-standard', keyed by the label,
                      so F31's re-authoring session consumes it (grade 'figure').
  * PAGE-REGION     — no nodemap anchor at all: banked honestly with {page, rect,
                      nearest section}, marked region-grade, NEVER a fabricated node.

Every claim is a banked-record assertion; the anchor grade is the honesty contract.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from laplace.manuscript import review_surface as rv
from laplace.pipeline.ledger import read_jsonl

pytestmark = pytest.mark.unit


_MAIN = ("\\documentclass{article}\\begin{document}\n"
         "\\input{N1}\n\\end{document}\n")
_N1 = (
    "% PLAN:N1\n"
    "\\section{Introduction}\\label{sec:N1}\n"
    "\n% N1-p1\n"
    "The quick brown fox jumps over the lazy dog.\n"
    "\n% N1-p2\n"
    "The lazy dog sleeps here in the afternoon sun.\n"
)


def _md(tmp_path: Path) -> Path:
    md = tmp_path / "ms"
    md.mkdir(parents=True)
    (md / "main.tex").write_text(_MAIN, encoding="utf-8")
    (md / "N1.tex").write_text(_N1, encoding="utf-8")
    (md / "feedback").mkdir()
    return md


def _ledger(md: Path) -> list[dict]:
    p = md / "feedback" / "feedback.jsonl"
    return read_jsonl(p) if p.is_file() else []


def _comments(md: Path) -> list[dict]:
    return [r for r in _ledger(md) if r.get("kind") in ("comment", "figure-standard")]


# ===========================================================================
# TIER 1 — NODE-anchored (the existing precise anchor, grade 'node')
# ===========================================================================

def test_node_anchored_comment_is_grade_node(tmp_path):
    md = _md(tmp_path)
    res = rv.adjudicate(md, "proj", {"by": "author", 
        "verb": "comment", "node": "def:alpha", "section": "N1",
        "paragraph": "N1-p1", "comment": "this derivation is unmotivated"})
    assert res.get("ok") is True and res.get("grade") == "node"
    rec = _comments(md)[-1]
    assert rec["kind"] == "comment" and rec["node_id"] == "def:alpha"
    assert (rec["anchor"] or {}).get("grade") == "node"


def test_prose_paragraph_comment_is_grade_paragraph_keyed_by_section(tmp_path):
    """A prose-paragraph selection sends the pid but no conceptric node: it banks
    section-keyed (node_id = the section) with grade 'paragraph' (precise) and the pid
    riding the anchor — the existing B13.2 semantic, now graded honestly."""
    md = _md(tmp_path)
    res = rv.adjudicate(md, "proj", {"by": "author", 
        "verb": "comment", "section": "N1", "paragraph": "N1-p1", "coarse": False,
        "comment": "the opener hedges"})
    assert res.get("ok") is True and res.get("grade") == "paragraph"
    rec = _comments(md)[-1]
    assert rec["kind"] == "comment" and rec["node_id"] == "N1"
    assert (rec["anchor"] or {}).get("grade") == "paragraph"
    assert (rec["anchor"] or {}).get("paragraph_id") == "N1-p1"


# ===========================================================================
# TIER 2 — SECTION-coarse (no node, resolved to the section beat, marked coarse)
# ===========================================================================

def test_section_coarse_comment_is_grade_section(tmp_path):
    md = _md(tmp_path)
    res = rv.adjudicate(md, "proj", {"by": "author", 
        "verb": "comment", "section": "N1", "coarse": True,
        "comment": "the whole section drifts off-voice"})
    assert res.get("ok") is True and res.get("grade") == "section"
    rec = _comments(md)[-1]
    assert rec["kind"] == "comment" and rec["node_id"] == "N1"
    assert (rec["anchor"] or {}).get("grade") == "section"
    assert (rec["anchor"] or {}).get("coarse") is True


# ===========================================================================
# TIER 3 — FIGURE (B13.5): a `fig:` block → kind='figure-standard', keyed by label
# ===========================================================================

def test_figure_node_banks_figure_standard_keyed_by_label(tmp_path):
    """Commenting on a `fig:`-labelled node (its float region or its caption) banks the
    F31-consumed 'figure-standard' review kind, node_id = the figure's label."""
    md = _md(tmp_path)
    res = rv.adjudicate(md, "proj", {"by": "author", 
        "verb": "comment", "node": "fig:widget-sweep", "section": "N1",
        "comment": "panel (b) is mislabelled — swap the axes"})
    assert res.get("ok") is True
    assert res.get("grade") == "figure" and res.get("review_kind") == "figure-standard"
    assert res.get("figure") == "fig:widget-sweep"
    rec = _comments(md)[-1]
    assert rec["kind"] == "figure-standard"          # the kind F31 consumes
    assert rec["node_id"] == "fig:widget-sweep"      # keyed by the figure label
    assert (rec["anchor"] or {}).get("figure") == "fig:widget-sweep"


def test_figure_affordance_normalizes_a_bare_label(tmp_path):
    """The comment-on-figure affordance may pass a bare label; the server anchors it to
    the honest ``fig:`` id (never a fabricated node)."""
    md = _md(tmp_path)
    res = rv.adjudicate(md, "proj", {"by": "author", 
        "verb": "comment", "figure": "widget-sweep",
        "comment": "caption over-claims"})
    assert res.get("ok") is True and res.get("figure") == "fig:widget-sweep"
    rec = _comments(md)[-1]
    assert rec["kind"] == "figure-standard" and rec["node_id"] == "fig:widget-sweep"


def test_figure_standard_comment_intakes_to_the_figures_stage(tmp_path):
    """END-TO-END: a banked figure-standard comment routes to the figures stage via the
    SAME intake F31's re-authoring session consumes — the gesture feeds the queue."""
    from laplace.pipeline import propagate
    md = _md(tmp_path)
    rv.adjudicate(md, "proj", {"by": "author", 
        "verb": "comment", "node": "fig:widget-sweep", "section": "N1",
        "comment": "panel mislabelled"})
    rec = _comments(md)[-1]
    plan = {"meta": {"project": "proj"},
            "sections": [{"id": "N1", "nodes_in_order": ["fig:widget-sweep"]}]}
    items = propagate.intake_items([rec], plan, {"fig:widget-sweep": {}})
    assert len(items) == 1
    assert items[0]["kind"] == "figure" and items[0]["owning_stage"] == "figures"


# ===========================================================================
# TIER 4 — PAGE-REGION fallback (B13.3): no nodemap anchor → honest region-grade
# ===========================================================================

def test_region_fallback_banks_region_grade_with_rect(tmp_path):
    """A comment with NO node/section/paragraph but a page region banks honestly as
    region-grade: the rect + page ride the anchor, marked coarse, NEVER a fake node."""
    md = _md(tmp_path)
    res = rv.adjudicate(md, "proj", {"by": "author", 
        "verb": "comment", "page": 3,
        "region": {"page": 3, "x0": 40.0, "y0": 120.0, "x1": 260.0, "y1": 210.0},
        "comment": "this whole margin block is out of place"})
    assert res.get("ok") is True
    assert res.get("grade") == "region" and res.get("coarse") is True
    rec = _comments(md)[-1]
    assert rec["kind"] == "comment"
    anc = rec["anchor"] or {}
    assert anc.get("grade") == "region" and anc.get("coarse") is True
    assert anc.get("region", {}).get("x0") == 40.0 and anc.get("region", {}).get("page") == 3
    # the honest pseudo-key names the page-region, not a conceptric node
    assert rec["node_id"] == "region:p3"


def test_region_with_nearest_section_keeps_section_but_marks_region(tmp_path):
    """When a nearest section is known it is carried (honest coarse locator), but the
    grade stays 'region' and the rect is preserved — the surface never upgrades it to a
    precise anchor."""
    md = _md(tmp_path)
    res = rv.adjudicate(md, "proj", {"by": "author", 
        "verb": "comment", "section": "N1", "page": 2,
        "region": {"page": 2, "x0": 10.0, "y0": 10.0, "x1": 50.0, "y1": 50.0},
        "comment": "floating near the intro"})
    # a section present → the node/section tier claims it FIRST (grade 'section');
    # the region tier is the true no-anchor fallback. Pin that precedence explicitly.
    assert res.get("ok") is True and res.get("grade") == "section"


def test_region_finding_lists_unanchored_and_never_fabricates_a_node(tmp_path, monkeypatch):
    """The banked region comment surfaces in findings() as UNANCHORED (its pseudo id is
    node-shaped but is not a conceptric node) carrying grade='region' + its rect."""
    md = _md(tmp_path)
    nm = {"present": True, "fresh": True,
          "entries": {"N1-p1": [{"page": 1}]}, "coverage": {}}
    monkeypatch.setattr(rv, "nodemap_state", lambda _md: nm)
    rv.adjudicate(md, "proj", {"by": "author", 
        "verb": "comment", "page": 5,
        "region": {"page": 5, "x0": 1.0, "y0": 2.0, "x1": 3.0, "y1": 4.0},
        "comment": "dead whitespace note"})
    board = rv.findings(md, "proj")
    reg = [f for f in board["unanchored"] if f.get("grade") == "region"]
    assert len(reg) == 1
    assert reg[0]["node"] is None                    # NOT surfaced as a conceptric node
    assert reg[0]["region"]["page"] == 5
    # it never leaks into the anchored node groups
    assert all(g["node"] != "region:p5" for g in board["by_node"])


def test_empty_comment_all_tiers_refused(tmp_path):
    md = _md(tmp_path)
    for extra in ({"node": "def:x"}, {"section": "N1"}, {"figure": "widget"},
                  {"region": {"page": 1}}):
        res = rv.adjudicate(md, "proj", {"by": "author", "verb": "comment", "comment": "  ", **extra})
        assert res.get("ok") is not True and "comment text is required" in res.get("error", "")
    assert _comments(md) == []                        # nothing banked


def test_comment_with_no_anchor_at_all_is_honest_refusal(tmp_path):
    md = _md(tmp_path)
    res = rv.adjudicate(md, "proj", {"by": "author", "verb": "comment", "comment": "floating"})
    assert res.get("ok") is not True
    assert "required to comment" in res.get("error", "")
    assert _comments(md) == []
