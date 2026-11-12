"""Tests for the GAP LEDGER + RESEARCH-INTENT TYPING (gap_ledger)."""
from __future__ import annotations

from laplace.pipeline import gap_ledger as GL


def _findings():
    return [
        {"kind": "promise-figure-absent", "where": "s7", "section": "s7",
         "issue": "no figure", "severity": 0.7},
        {"kind": "source-motivation-lost", "where": "source-vs-projection",
         "issue": "why dropped", "primary": "Because ..."},
        {"kind": "float-orphan", "where": "s3", "section": "s3",
         "issue": "never ref'd"},
        {"kind": "promise-citation-absent", "where": "s4", "section": "s4",
         "issue": "cite ghost"},
        {"kind": "tex-layout", "where": "s1", "issue": "overfull"},  # NOT a gap
    ]


def test_compile_types_gaps():
    gaps = GL.compile_gaps(_findings())
    by = {g.kind: g.gap_class for g in gaps}
    assert by["promise-figure-absent"] == "evidence-shaped"
    assert by["source-motivation-lost"] == "ungrounded"
    assert by["float-orphan"] == "orphaned"
    assert by["promise-citation-absent"] == "ungrounded"
    # a non-gap finding does not become a gap
    assert "tex-layout" not in by


def test_spine_criticality_flag_and_rank():
    gaps = GL.compile_gaps(_findings(), spine_sections=["s7", "s3", "s4"])
    crit = {g.section: g.spine_critical for g in gaps}
    assert crit["s7"] is True and crit["s3"] is True
    ranked = GL.rank_gaps(gaps)
    # spine-critical gaps come before off-spine (source-vs-projection has section "")
    assert ranked[0].spine_critical is True


def test_diagnostics_thin_and_orphan():
    gaps = GL.compile_gaps([], diagnostics={
        "thin_beats": [{"beat": "b1", "section": "s2", "note": "empty argues-in"}],
        "orphans": ["N9"],
    })
    classes = {g.gap_class for g in gaps}
    assert "thin" in classes and "orphaned" in classes


def test_substrate_absent_retyping():
    gaps = GL.compile_gaps(_findings())
    # inject a quarry that grounds nothing -> all substrate-absent
    GL.probe_quarry(gaps, lambda g: 0.1)
    GL.retype_substrate_absent(gaps, cosine_floor=0.62)
    by_class = {g.kind: g.research_class for g in gaps if g.substrate_absent}
    assert by_class["promise-figure-absent"] == "computation"   # evidence -> computed
    assert by_class["promise-citation-absent"] == "literature"  # cite -> cited
    # a SOURCE-DELTA loss is his own prose -> source-recoverable, NEVER novel
    assert by_class["source-motivation-lost"] == "source-recoverable"
    # epistemic provenance travels with substrate
    ev = {g.research_class: g.epistemic for g in gaps if g.substrate_absent}
    assert ev["computation"] == "computed"
    assert ev["literature"] == "cited"
    assert ev["source-recoverable"] == "mined"          # his draft is the substrate


def test_source_delta_never_novel_via_source_quarry():
    # a source-delta gap whose lost span is VERBATIM in the source stays MINEABLE
    # (re-project from his draft) — the source-aware quarry scores it ~1.0, not the
    # conceptric ~0.0 that would mistype it novel.
    span = ("Because no measurement intervenes between layers, no re-preparation "
            "is required to advance the coherent evolution across the circuit.")
    findings = [{"kind": "source-motivation-lost", "where": "source-vs-projection",
                 "issue": "why dropped", "primary": span, "quote": span}]
    gaps = GL.compile_gaps(findings)
    q = GL.source_aware_quarry_fn("p", span + "\n\nUnrelated filler sentence here.",
                                  source_is_text=True)
    GL.probe_quarry(gaps, q)
    GL.retype_substrate_absent(gaps)
    g = gaps[0]
    assert g.quarry_score > GL.DEFAULT_COSINE_FLOOR      # recovered from source
    assert g.substrate_absent is False                   # -> stays mineable
    assert g.research_class is None                       # never re-typed novel


def test_source_delta_unrecoverable_routes_source_recoverable_not_novel():
    # a source-delta gap whose span does NOT recover from source still routes to
    # source-recoverable (the door), NEVER novel — the belt-and-suspenders leg.
    findings = [{"kind": "source-argument-lost", "where": "source-vs-projection",
                 "issue": "move dropped", "primary": "orphan span", "quote": "orphan"}]
    gaps = GL.compile_gaps(findings)
    GL.probe_quarry(gaps, lambda g: 0.05)                # quarry grounds nothing
    GL.retype_substrate_absent(gaps)
    g = gaps[0]
    assert g.substrate_absent is True
    assert g.research_class == "source-recoverable"
    assert g.epistemic == "mined"
    ri = GL.to_research_intents(gaps, project="p")
    assert ri and ri[0]["door"] == "re-project-from-source"


def test_high_quarry_stays_mineable():
    gaps = GL.compile_gaps(_findings())
    GL.probe_quarry(gaps, lambda g: 0.9)
    GL.retype_substrate_absent(gaps)
    assert all(not g.substrate_absent for g in gaps)
    assert all(g.research_class is None for g in gaps)


def test_probe_exception_is_substrate_absent():
    gaps = GL.compile_gaps(_findings())
    def _boom(g):
        raise RuntimeError("no backend")
    GL.probe_quarry(gaps, _boom)
    assert all(g.quarry_score == 0.0 for g in gaps)


def test_cap_per_round():
    gaps = GL.compile_gaps(_findings())
    assert len(GL.cap_per_round(gaps, cap=2)) == 2
    assert len(GL.cap_per_round(gaps, cap=0)) == 0


def test_intent_streams_partition():
    gaps = GL.compile_gaps(_findings())
    GL.probe_quarry(gaps, lambda g: 0.1)          # all substrate-absent
    GL.retype_substrate_absent(gaps)
    concept = GL.to_conceptric_intents(gaps, project="p")
    research = GL.to_research_intents(gaps, project="p")
    # substrate-absent gaps go to research, none to conceptric
    assert concept == []
    assert len(research) == len(gaps)
    for r in research:
        assert r["research_class"] in GL.RESEARCH_CLASSES
        assert r["door"] in ("citation-direction", "evidence-organ",
                             "derivation-attempt", "re-project-from-source")
        assert r["gap"]["id"].startswith("GAP-")   # primary record rides along


def test_conceptric_intents_for_mineable():
    gaps = GL.compile_gaps(_findings())            # unprobed -> mineable
    concept = GL.to_conceptric_intents(gaps, project="p", round=3)
    assert len(concept) == len(gaps)
    for c in concept:
        assert c["record"] == "conceptric-intent"
        assert c["status"] == "open"               # queued, never executed
        assert c["intent"] in ("content-missing", "edge-missing", "other")


def test_build_ledger_end_to_end():
    led = GL.build_ledger(_findings(), spine_sections=["s7"],
                          quarry_fn=lambda g: 0.1, cap=3, project="p", round=3)
    assert led["census"]["capped"] == 3
    assert led["census"]["discovered"] >= 3
    assert led["all_gaps_n"] >= 3


def test_span_identity_dedup_keeps_distinct_lost_spans():
    # two source-delta findings sharing kind/where/issue-template (same 2-decimal
    # score) but DIFFERENT verbatim spans must NOT collapse — the span is identity.
    issue = "the source makes an argument MOVE ... (best projection overlap 0.20 < floor)"
    findings = [
        {"kind": "source-argument-lost", "where": "source-vs-projection",
         "issue": issue, "quote": "The commutator expectation is the central object."},
        {"kind": "source-argument-lost", "where": "source-vs-projection",
         "issue": issue, "quote": "Circuit volume scales linearly in layer count."},
    ]
    gaps = GL.compile_gaps(findings)
    assert len({g.id for g in gaps}) == 2          # distinct spans -> distinct gaps
    # a TRUE duplicate (identical span) still collapses to one
    dup = findings + [dict(findings[0])]
    assert len(GL.compile_gaps(dup)) == 2


def test_probe_systemexit_is_substrate_absent():
    # a fail-loud store raises SystemExit (a BaseException, not Exception); the probe
    # must degrade it to substrate-absent, never let it abort the round.
    gaps = GL.compile_gaps(_findings())
    def _fail_loud(g):
        raise SystemExit("stage_retrieval: store refused")
    GL.probe_quarry(gaps, _fail_loud)              # must not raise
    assert all(g.quarry_score == 0.0 for g in gaps)


def test_closure_metric():
    m = GL.closure_metric(["GAP-a", "GAP-b", "GAP-c"], ["GAP-b", "GAP-d"])
    assert m["closed"] == ["GAP-a", "GAP-c"]
    assert m["recurring"] == ["GAP-b"]
    assert m["discovered"] == ["GAP-d"]
    assert 0.0 <= m["closure_rate"] <= 1.0
