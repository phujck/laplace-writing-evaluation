"""Tests for the META-LEAK SCRUB (meta_leak_scrub) — the source-tier body-prose
leak detector composed over the core no_meta_leak gate."""
from __future__ import annotations

from laplace.pipeline import meta_leak_scrub as MLS
from laplace.pipeline import schema


def test_tier_label_in_prose_fires():
    hits = MLS.scrub_text("s1.tex",
        "The lattice dimensions are a SCENARIO-tier choice, not a derived value.")
    assert any(h["class"] == "tier-label" for h in hits)
    assert hits[0]["trust"] == "unverified"
    assert "SCENARIO-tier" in hits[0]["quote"]      # verbatim primary record


def test_trust_predicate_and_verify_token():
    hits = MLS.scrub_text("s7.tex",
        "The records carry trust=unverified pending a door-check, flagged TO-VERIFY.")
    classes = {h["class"] for h in hits}
    assert "trust-predicate" in classes
    assert "verify-token" in classes


def test_table_row_not_charged():
    # the tier BELONGS in the assumption table -> a pipe row is never a leak
    hits = MLS.scrub_text("appendix_a.tex",
        "| FALQON layers | 500 | - | SCENARIO |")
    assert hits == []


def test_latex_tabular_row_not_charged():
    hits = MLS.scrub_text("appendix_a.tex",
        "lattice shape & $6\\times5$ & SCENARIO \\\\")
    assert hits == []


def test_comment_line_not_charged():
    hits = MLS.scrub_text("s1.tex", "% this is a SCENARIO-tier note to self")
    assert hits == []


def test_clean_prose_passes():
    hits = MLS.scrub_text("s1.tex",
        "The lattice is a six-by-five grid of thirty sites with two spins each.")
    assert hits == []


def test_to_findings_shape():
    hits = MLS.scrub_text("s1.tex", "This is a SCENARIO-tier assumption.")
    scrub = {"hits": hits}
    findings = MLS.to_findings(scrub, round=3)
    assert findings
    for f in findings:
        assert f["route"] == "prose"
        assert f["trust"] == "unverified"
        assert f["kind"] == "meta-leak-source-tier"


def test_scrub_tex_dir(tmp_path):
    (tmp_path / "s1.tex").write_text(
        "A SCENARIO-tier value here.\n", encoding="utf-8")
    (tmp_path / "s2.tex").write_text(
        "Clean prose with no typing tokens at all.\n", encoding="utf-8")
    hits = MLS.scrub_tex_dir(tmp_path)
    assert len(hits) == 1
    assert hits[0]["file"] == "s1.tex"


def test_scrub_project_composes_core(tmp_path):
    # tex_dir override lets us drive scrub_project without a registered project's
    # tree; the core gate runs on the (unknown) project and returns manual/None,
    # the source-tier scrub runs on the dir.
    (tmp_path / "s1.tex").write_text(
        "The overhead is a SCENARIO estimate, carrying trust=unverified.\n",
        encoding="utf-8")
    res = MLS.scrub_project("paper_falqon", tex_dir=tmp_path)
    assert res["n"] >= 1
    assert res["source_tier"]["n"] >= 1
    assert res["pass"] is False


def test_kinds_registered_in_schema():
    schema.register_component_kinds()
    for row in MLS.finding_kinds_manifest():
        assert row["kind"] in schema.KIND_TO_WORK, row["kind"]


def test_mechround_hard_gate_wires_source_tier_scrub():
    """WIRING REGRESSION (his rejection PV-20260717T005612Z): the HARD ``no_meta_leak``
    gate must compose the SOURCE-TIER scrub, not only the core process-vocab gate.
    Before this wire, a source-tier body leak passed ``check_meta_leak`` silently and
    reached the compiled PDF. Lock that the mechround panel folds ``source_tier_hits``
    into the meta_leak gate's pass condition and its hit list."""
    from pathlib import Path
    src = Path(__file__).resolve().parents[1] / ".claude/workflows/fixedpoint_mechround.py"
    text = src.read_text(encoding="utf-8")
    # the scrub is called over the manuscript dir...
    assert "scrub_tex_dir(Path(main_tex).parent)" in text
    # ...its hits feed the meta_leak gate's HARD pass condition...
    assert "and not source_tier_hits" in text
    # ...and are surfaced in the gate's hit list, not dropped.
    assert "+ source_tier_hits" in text


def test_source_tier_leak_would_block_gate(tmp_path):
    """End-to-end organ check: a manuscript fragment carrying the tier register in
    body prose yields hits, so the gate's ``not source_tier_hits`` is False (blocks);
    a clean fragment yields none (passes)."""
    (tmp_path / "s1.tex").write_text(
        "% s1-p1\nThe layer count is a SCENARIO-tier choice, flagged TO-VERIFY.\n",
        encoding="utf-8")
    dirty = MLS.scrub_tex_dir(tmp_path)
    assert dirty and not (not dirty)          # non-empty -> gate blocks
    (tmp_path / "s1.tex").write_text(
        "% s1-p1\nThe layer count is a chosen value, not yet checked against source.\n",
        encoding="utf-8")
    clean = MLS.scrub_tex_dir(tmp_path)
    assert clean == []                        # empty -> gate passes
