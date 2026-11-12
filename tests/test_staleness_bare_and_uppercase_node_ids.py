"""Staleness detection over BARE and UPPERCASE node ids (IDEMPOTENCE row 7).

Before 2026-08-07 the dirty diff filtered both sides of its set difference through
``schema.NODE_ID_RE`` (``^[a-z][\\w-]*:[^\\s]+$``), which only matches a kind-prefixed
id. Every conceptric mints bare ones too — ``RQ-CLM-043`` (roland's uppercase dashed
claim idiom), ``fal_clm_001`` / ``d_context_window`` / ``ridge_lambda`` (snake_case
defs) — so those ids dropped out of the plan set AND the fragment set, the difference
came out empty, and a rebuilt project read CLEAN after its node pool changed. Roland
was totally blind (every content id is bare or uppercase); falqon and eigenengine
partially.

The three fixtures below are the three corpora SHAPES, not the corpora: roland
(``RQ-CLM-nnn`` + snake defs + ``sec:``/``fig:`` prefixes), falqon (``fal_clm_nnn`` +
kind-prefixed results), eigenengine (``d_``/``c_``/``r_`` snake ids). Each is run
through both diff paths — ``restructure.dirty_diff`` (plan vs plan) and
``storyboard.dirty_report`` (plan vs the fragment's ``% NODES`` markers).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from laplace.manuscript import projection_viewer as pv
from laplace.manuscript import storyboard as sb
from laplace.pipeline import restructure, schema

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# the three corpora SHAPES (small fixtures — the real pools stay on disk)
# ---------------------------------------------------------------------------

#: (shape name, section id, node list before, node list after). Each "after" both
#: adds an uppercase id and swaps a snake_case def — the two idioms row 7 names.
SHAPES = [
    ("roland",
     "sec_r2_theory_laws",
     ["RQ-CLM-043", "ridge_lambda", "res:minimal-reservoir"],
     ["RQ-CLM-043", "RQ-CLM-044", "accessible_bandwidth", "res:minimal-reservoir"]),
    ("falqon",
     "s3",
     ["fal_clm_001", "cycle_time", "def:bg-b3-feedback-precision"],
     ["fal_clm_001", "fal_clm_002", "hopping_terms", "def:bg-b3-feedback-precision"]),
    ("eigenengine",
     "sec_structure",
     ["d_context_window", "c_apex_layer", "r_result1"],
     ["d_context_window", "d_fold", "c_ladder_loops", "r_result1"]),
]

IDS = [s[0] for s in SHAPES]


def _plan(sid: str, nodes: list[str], target: str = "wp") -> dict:
    return {"meta": {"target_dir": target},
            "sections": [{"id": sid, "title": sid, "nodes_in_order": list(nodes)}],
            "appendices": []}


def _fragment(sid: str, nodes: list[str]) -> str:
    """A compiled fragment discharging ``nodes`` — the shape the realiser emits."""
    return (f"% PLAN:{sid}\n% NODES: {', '.join(nodes)}\n"
            f"% {sid}-p1\nProse for the span.\n")


# ---------------------------------------------------------------------------
# the id filter itself
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,sid,before,after", SHAPES, ids=IDS)
def test_clean_ids_keeps_the_bare_and_uppercase_pool_ids(name, sid, before, after):
    """The regression's root: every id in the shape survives the filter. Under the
    pre-fix pattern the bare ids vanished, leaving only the kind-prefixed ones."""
    kept = schema.clean_ids(after)
    assert kept == set(after), f"{name}: dropped {sorted(set(after) - kept)}"
    # and the pre-fix pattern is why they used to vanish
    narrow = {x for x in after if schema.NODE_ID_RE.match(x)}
    assert narrow != set(after), f"{name}: fixture must exercise non-prefixed ids"


# ---------------------------------------------------------------------------
# path 1 — restructure.dirty_diff (plan vs plan)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,sid,before,after", SHAPES, ids=IDS)
def test_dirty_diff_detects_a_bare_id_node_pool_change(name, sid, before, after):
    d = restructure.dirty_diff(_plan(sid, before), _plan(sid, after))
    row = next(s for s in d["sections"] if s["id"] == sid)
    assert row["changed"] is True and row["class"] == "expensive", f"{name}: {row}"
    assert set(row["added"]) == set(after) - set(before), f"{name}: {row}"
    assert set(row["removed"]) == set(before) - set(after), f"{name}: {row}"


@pytest.mark.parametrize("name,sid,before,after", SHAPES, ids=IDS)
def test_dirty_diff_stays_cheap_when_only_the_title_moves(name, sid, before, after):
    """The other side of the gate: widening must not make every section dirty."""
    old = _plan(sid, before)
    new = _plan(sid, before)
    new["sections"][0]["title"] = "A New Title"
    row = next(s for s in restructure.dirty_diff(old, new)["sections"] if s["id"] == sid)
    assert row["changed"] is False and row["class"] == "cheap", f"{name}: {row}"


# ---------------------------------------------------------------------------
# path 2 — storyboard.dirty_report (plan vs the fragment's % NODES markers)
# ---------------------------------------------------------------------------

def _report(monkeypatch, tmp_path: Path, sid: str,
            plan_nodes: list[str], tex_nodes: list[str]) -> dict:
    """One section's dirty row. ``_load_plan``/``_repo_root`` are the two doors
    ``dirty_report`` reaches the world through; patching them keeps the fixture to
    a plan dict and one tex file instead of a registered project."""
    target = tmp_path / "wp"
    target.mkdir(parents=True, exist_ok=True)
    (target / f"{sid}.tex").write_text(_fragment(sid, tex_nodes), encoding="utf-8")
    plan = _plan(sid, plan_nodes)
    monkeypatch.setattr(sb, "_load_plan", lambda corpus: (tmp_path / "plan.json", plan))
    monkeypatch.setattr(sb, "_repo_root", lambda: tmp_path)
    rows = sb.dirty_report("fixture")
    return next(r for r in rows if r["id"] == sid)


@pytest.mark.parametrize("name,sid,before,after", SHAPES, ids=IDS)
def test_dirty_report_detects_a_bare_id_change_against_the_fragment(
        monkeypatch, tmp_path, name, sid, before, after):
    """The second-build read: the fragment still discharges the OLD pool, the plan
    asks for the NEW one. This is the row-7 symptom — it used to report CLEAN."""
    row = _report(monkeypatch, tmp_path, sid, plan_nodes=after, tex_nodes=before)
    assert row["has_markers"] is True, row
    assert row["dirty"] is True, f"{name}: {row}"
    assert set(row["added"]) == set(after) - set(before), f"{name}: {row}"
    assert set(row["removed"]) == set(before) - set(after), f"{name}: {row}"


@pytest.mark.parametrize("name,sid,before,after", SHAPES, ids=IDS)
def test_dirty_report_reads_clean_when_the_fragment_matches(
        monkeypatch, tmp_path, name, sid, before, after):
    row = _report(monkeypatch, tmp_path, sid, plan_nodes=after, tex_nodes=after)
    assert row["dirty"] is False, f"{name}: {row}"
    assert row["n_plan"] == row["n_tex"] == len(after), f"{name}: {row}"


# ---------------------------------------------------------------------------
# what the widening must NOT admit
# ---------------------------------------------------------------------------

def test_prose_and_latex_never_enter_the_id_sets():
    """A blind builder's trailing prose rode the same ``% NODES`` line as the ids
    (``synthetics papers/.../S10.tex``). The charset and the aside strip keep it out."""
    noise = ["(evidence)", "(the", "achieved)", "back:", "home)",
             r"\section{Conclusion}\label{sec:N8}", "%", "104-104", "(front-matter)"]
    assert schema.clean_ids(noise) == set()


def test_a_parenthesised_aside_on_a_nodes_marker_is_not_a_node():
    text = ("% PLAN:S10\n% NODES: res:integer-decoder (evidence)\nProse.\n\n"
            "% NODES: (step back: what the whole object achieved)\nMore prose.\n")
    marked = [n for span in pv.parse_map(text) for n in span["nodes"]]
    assert marked == ["res:integer-decoder"], marked


def test_paragraph_spec_ids_are_not_nodes():
    """``<section>-p<N>`` is prose provenance and shares the bare-id charset."""
    assert schema.clean_ids(["abstract-p1", "sec_r2_theory-p12"]) == set()


def test_support_namespaces_still_drop_out_for_bare_pools():
    assert schema.clean_ids(["fig:nmse_heatmap", "ref:mccaul2025minimal",
                             "RQ-CLM-043"]) == {"RQ-CLM-043"}


def test_the_identity_guard_still_refuses_bare_references():
    """``NODE_ID_RE`` is the guard ``citation_direction.resolve_claim_node`` and
    ``review_surface._feedback_findings`` read to decide whether a free-text
    reference names a node at all. Widening IT would turn section stems, bib keys
    and the ``source-vs-projection`` sentinel into fabricated anchors — the pool
    grammar is a separate object for exactly that reason."""
    for bare in ("introduction", "limits_and_discussion", "appendix_c.tex",
                 "chan2025shadow", "source-vs-projection", "N5"):
        assert not schema.NODE_ID_RE.match(bare), bare
        assert schema.POOL_ID_RE.match(bare), bare
    for prefixed in ("region:p7", "def:widget", "res:main-bound", "sec:Fourier-analysis"):
        assert schema.NODE_ID_RE.match(prefixed), prefixed


# ---------------------------------------------------------------------------
# the shapes are the real ones (the fixtures are not invented)
# ---------------------------------------------------------------------------

REPO = Path(__file__).resolve().parents[1]
POOLS = {"roland": REPO / "paper_roland_qrc" / "manuscript" / "conceptric_v1.json",
         "falqon": REPO / "paper_falqon" / "manuscript" / "conceptric_v1.json",
         "eigenengine": REPO / "eigenengine" / "manuscript" / "conceptric_v1.json"}


@pytest.mark.parametrize("name", sorted(POOLS))
def test_every_live_pool_id_survives_the_filter(name):
    """Whole-pool sweep against the corpora on disk: the only ids the diff drops
    are the declared support namespaces (``fig:``/``ref:``)."""
    p = POOLS[name]
    if not p.is_file():
        pytest.skip(f"{p} not on disk")
    ids = [n["id"] for n in json.loads(p.read_text(encoding="utf-8"))["nodes"]]
    dropped = sorted({i for i in ids if not schema.is_pool_id(i)})
    assert all(i.startswith(schema.NON_CONTENT_PREFIXES) for i in dropped), dropped
    assert len(schema.clean_ids(ids)) == len(set(ids)) - len(dropped)
