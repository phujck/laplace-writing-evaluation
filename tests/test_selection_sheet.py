"""THE SELECTION SHEET + THE DRAFT RULE (P2): every generation joined to its OWN
banked readings, a DRAFT verdict proposed against ψ/φ (HIS), honest-empty on every
absent ref, and an ABSENT reading that never promotes (silence holds, absence named).

Pure, tmp_path everywhere: a hand-built ``generations.jsonl`` + dated artifact files,
a registry monkeypatched to a tmp project, telemetry monkeypatched to a fixed event
list. The real shipped ``draft-psi-v1.yaml`` is copied under the tmp root so the rule
overlay + round-trip are exercised against the real file.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from laplace.pipeline import registry
from laplace.pipeline import selection_sheet as ss

_SELDIR = Path(__file__).resolve().parents[1] / "profiles" / "selection"
_REAL_RULE = _SELDIR / "draft-psi-v1.yaml"
_REAL_RULE_V2 = _SELDIR / "draft-psi-v2.yaml"


def _setup(tmp_path, monkeypatch, *, gen_rows, artifacts, feedback_rows=(),
           events=(), suite=True, dial="draft-psi-v1"):
    md = tmp_path / "manuscript"
    (md / "feedback").mkdir(parents=True, exist_ok=True)
    for rel, content in artifacts.items():
        p = md / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(content), encoding="utf-8")
    with (md / "generations.jsonl").open("w", encoding="utf-8") as f:
        for r in gen_rows:
            f.write(json.dumps(r) + "\n")
    with (md / "feedback" / "feedback.jsonl").open("w", encoding="utf-8") as f:
        for r in feedback_rows:
            f.write(json.dumps(r) + "\n")
    (tmp_path / "profiles" / "selection").mkdir(parents=True, exist_ok=True)
    (tmp_path / "profiles" / "selection" / "draft-psi-v1.yaml").write_bytes(
        _REAL_RULE.read_bytes())
    (tmp_path / "profiles" / "selection" / "draft-psi-v2.yaml").write_bytes(
        _REAL_RULE_V2.read_bytes())
    # the selection dial names which rule file the sheet reads; default draft-psi-v1
    # keeps existing tests on the exact v1 behavior, the v2 tests flip it explicitly.
    monkeypatch.setattr("laplace.pipeline.dials.load_dials",
                        lambda *a, **k: {"selection": {"draft_psi": dial}})
    if suite:
        (tmp_path / "corpus_friction").mkdir(parents=True, exist_ok=True)
        (tmp_path / "corpus_friction" / "suite_baseline.json").write_text(
            json.dumps({"counts": {"failed": 15}, "captured_at": "2026-07-19"}),
            encoding="utf-8")
    proj = registry.Project(name="tproj", kind="conceptric", manuscript_dir="manuscript")
    monkeypatch.setattr(registry, "resolve", lambda name: proj if name == "tproj" else None)
    monkeypatch.setattr("laplace.engine.telemetry.events", lambda *a, **k: list(events))
    return md


def _clean_r10(report_id="RPT-1", clean=True, findings=()):
    return {"record": "reader-report", "reader": "R10", "id": report_id,
            "clean": clean, "findings": list(findings)}


def _promote_gen(n=1, report_id="RPT-1"):
    """A generation whose readings pass all three gates with a positive net gain."""
    row = {
        "id": f"GEN-{n}", "record": "generation", "n": n, "corpus": "tproj",
        "stamped_at": f"2026-07-2{n}T00:00:00", "dials_profile": "dials-v1",
        "entered": {"ratified_op_ids": [], "intent_ids": []},
        "reprojection": {"run_record": f"reprojection/run_record_{n}.json",
                         "freeze_verdict": f"reprojection/freeze_verdict_{n}.json"},
        "converge": {"detect_pre": f"rounds/harnessed/detect_pre_{n}.json",
                     "detect_post": f"rounds/harnessed/detect_post_{n}.json"},
        "r10": {"report_id": report_id, "clean": True},
    }
    artifacts = {
        f"reprojection/run_record_{n}.json":
            {"source_delta_before": {"n": 30}, "source_delta_after": {"n": 20}},
        f"reprojection/freeze_verdict_{n}.json":
            {"pass": True, "substance_pass": True, "mechanical_pass": True, "classes": {}},
        f"rounds/harnessed/detect_pre_{n}.json": {"open_findings_n": 5},
        f"rounds/harnessed/detect_post_{n}.json": {"open_findings_n": 3},
    }
    return row, artifacts


# ---------------------------------------------------------------------------

def test_join_correctness(tmp_path, monkeypatch):
    row, artifacts = _promote_gen()
    _setup(tmp_path, monkeypatch, gen_rows=[row], artifacts=artifacts,
           feedback_rows=[_clean_r10()])
    out = ss.read_selection("tproj", root=tmp_path)
    assert out["present"] is True
    g = out["generations"][0]
    assert g["n"] == 1 and g["id"] == "GEN-1" and g["dials_profile"] == "dials-v1"
    assert g["debt_before"] == 30 and g["debt_after"] == 20 and g["debt_delta"] == 10
    assert g["freeze"]["substance_pass"] is True
    assert g["mechround"] == {"pre": 5, "post": 3, "derivative": -2}
    assert g["r10"] == {"ran": True, "clean": True, "findings_n": 0, "mismatch_kinds": []}


def test_honest_empty(tmp_path, monkeypatch):
    # no generations.jsonl at all — present False, no raise
    proj = registry.Project(name="tproj", kind="conceptric", manuscript_dir="manuscript")
    (tmp_path / "manuscript").mkdir()
    monkeypatch.setattr(registry, "resolve", lambda name: proj if name == "tproj" else None)
    monkeypatch.setattr("laplace.engine.telemetry.events", lambda *a, **k: [])
    out = ss.read_selection("tproj", root=tmp_path)
    assert out["present"] is False and out["generations"] == []
    # an unregistered project degrades too
    assert ss.read_selection("nope", root=tmp_path) == {"present": False, "corpus": "nope"}


def test_promote_when_gates_pass_and_positive_delta(tmp_path, monkeypatch):
    row, artifacts = _promote_gen()
    _setup(tmp_path, monkeypatch, gen_rows=[row], artifacts=artifacts,
           feedback_rows=[_clean_r10()])
    out = ss.read_selection("tproj", root=tmp_path)
    dv = out["generations"][0]["draft_verdict"]
    assert dv["verdict"] == "promote"
    assert all(g["pass"] is True for g in dv["gates"].values())
    # every reason cites a number + a clause
    assert any("30→20" in r and "structure earned" in r for r in dv["reasons"])
    assert any("net gain 10 > 0" in r for r in dv["reasons"])
    assert out["counts"]["promote"] == 1


def test_hold_with_absence_named_on_null_ref(tmp_path, monkeypatch):
    # run_record + freeze + detect refs all null → debt/freeze/derivative absent →
    # gates null → HOLD, absence NAMED, never promote (even with a clean r10).
    row = {
        "id": "GEN-1", "record": "generation", "n": 1, "corpus": "tproj",
        "stamped_at": "2026-07-21T00:00:00", "dials_profile": "dials-v1",
        "entered": {"intent_ids": []},
        "reprojection": {"run_record": None, "freeze_verdict": None},
        "converge": {"detect_pre": None, "detect_post": None},
        "r10": {"report_id": "RPT-1", "clean": True},
    }
    _setup(tmp_path, monkeypatch, gen_rows=[row], artifacts={},
           feedback_rows=[_clean_r10()])
    dv = ss.read_selection("tproj", root=tmp_path)["generations"][0]["draft_verdict"]
    assert dv["verdict"] == "hold"
    assert dv["gates"]["gate_cost"]["pass"] is None
    assert dv["gates"]["gate_representation_stability"]["pass"] is None
    assert any("absent" in r for r in dv["reasons"])


def test_debt_before_falls_back_to_prev_generation(tmp_path, monkeypatch):
    # gen1 carries before/after (30→20); gen2's run_record has NO before, so before
    # falls back to gen1's after (20). The reason documents the fallback.
    row1, art1 = _promote_gen(n=1, report_id="RPT-1")
    row2, art2 = _promote_gen(n=2, report_id="RPT-2")
    art2["reprojection/run_record_2.json"] = {"source_delta_after": {"n": 10}}  # no before
    arts = {**art1, **art2}
    _setup(tmp_path, monkeypatch, gen_rows=[row1, row2], artifacts=arts,
           feedback_rows=[_clean_r10("RPT-1"), _clean_r10("RPT-2")])
    out = ss.read_selection("tproj", root=tmp_path)
    g2 = next(g for g in out["generations"] if g["n"] == 2)
    assert g2["debt_before"] == 20 and g2["debt_after"] == 10  # fell back to gen1.after
    assert g2["debt_before_source"] == "prev-generation"
    assert any("prev generation's after" in r for r in g2["draft_verdict"]["reasons"])


def test_debt_before_falls_back_to_census_for_gen_one(tmp_path, monkeypatch):
    # gen1's run_record carries NO before and there is no previous generation —
    # the third source: the fitness trajectory's latest point STRICTLY before the
    # run_record date (the falqon gen-1 case: the 07-17 census measured 30, the
    # 07-19 gate banked only after=20). A point at-or-after the run never counts.
    row, art = _promote_gen()
    art["reprojection/run_record_1.json"] = {"at": "2026-07-19T00:00:00",
                                             "source_delta_after": {"n": 20}}
    _setup(tmp_path, monkeypatch, gen_rows=[row], artifacts=art,
           feedback_rows=[_clean_r10()])
    import laplace.pipeline.fitness_panel as fp
    monkeypatch.setattr(fp, "read_fitness", lambda c: {"debt_trajectory": [
        {"at": "2026-07-17", "n": 30, "source": "census"},
        {"at": "2026-07-19", "n": 20, "source": "run_record"}]})
    g = ss.read_selection("tproj", root=tmp_path)["generations"][0]
    assert g["debt_before"] == 30 and g["debt_before_source"] == "census"
    assert g["debt_delta"] == 10
    assert any("the census point" in r for r in g["draft_verdict"]["reasons"])
    assert g["draft_verdict"]["verdict"] == "promote"


def test_retire_needs_both(tmp_path, monkeypatch):
    # debt ROSE (20→30) but r10 CLEAN → hold, not retire
    row_a, art_a = _promote_gen()
    art_a["reprojection/run_record_1.json"] = {"source_delta_before": {"n": 20},
                                               "source_delta_after": {"n": 30}}
    _setup(tmp_path, monkeypatch, gen_rows=[row_a], artifacts=art_a,
           feedback_rows=[_clean_r10()])
    assert ss.read_selection("tproj", root=tmp_path)["generations"][0][
        "draft_verdict"]["verdict"] == "hold"

    # debt ROSE AND r10 UNCLEAN → retire
    row_b, art_b = _promote_gen(report_id="RPT-2")
    art_b["reprojection/run_record_1.json"] = {"source_delta_before": {"n": 20},
                                               "source_delta_after": {"n": 30}}
    unclean = _clean_r10("RPT-2", clean=False,
                         findings=[{"mismatch_type": "identity", "kind": "identity-mismatch"}])
    _setup(tmp_path, monkeypatch, gen_rows=[row_b], artifacts=art_b,
           feedback_rows=[unclean])
    dv = ss.read_selection("tproj", root=tmp_path)["generations"][0]["draft_verdict"]
    assert dv["verdict"] == "retire"
    assert dv["gates"]["gate_self_consistency"]["pass"] is False


def test_author_beats_machine(tmp_path, monkeypatch):
    row, artifacts = _promote_gen()
    row["entered"] = {"intent_ids": ["INT1"]}
    events = [
        {"phase": "retention", "artifact": "tproj:INT1", "source": "door", "fate": "kept"},
        {"phase": "retention", "artifact": "tproj:INT1", "source": "gate", "fate": "rewritten"},
        {"phase": "retention", "artifact": "tproj:INT1", "source": "author", "fate": "bypassed"},
    ]
    _setup(tmp_path, monkeypatch, gen_rows=[row], artifacts=artifacts,
           feedback_rows=[_clean_r10()], events=events)
    ret = ss.read_selection("tproj", root=tmp_path)["generations"][0]["retention"]
    assert ret["keys"] == 1
    assert ret["author_ruled"] == 1 and ret["machine_superseded"] == 2
    assert ret["by_fate"] == {"bypassed": 1}   # the author's fate won the key


def test_unknown_yaml_key_raises(tmp_path):
    (tmp_path / "profiles" / "selection").mkdir(parents=True)
    (tmp_path / "profiles" / "selection" / "bad.yaml").write_text(
        "version: draft-psi-v1\ngate_cost:\n  bogus_key: true\n", encoding="utf-8")
    with pytest.raises(ValueError) as ei:
        ss._load_rule(tmp_path, "bad")
    assert "gate_cost.bogus_key" in str(ei.value)


def test_rule_version_and_law_ride_payload(tmp_path, monkeypatch):
    row, artifacts = _promote_gen()
    _setup(tmp_path, monkeypatch, gen_rows=[row], artifacts=artifacts,
           feedback_rows=[_clean_r10()])
    out = ss.read_selection("tproj", root=tmp_path)
    assert out["rule"]["version"] == "draft-psi-v1"
    assert "the author's ruling supersedes" in out["rule"]["law"]
    assert out["rule"]["path"].endswith("draft-psi-v1.yaml")
    dv = out["generations"][0]["draft_verdict"]
    assert dv["rule"] == "draft-psi-v1" and dv["law"] == out["rule"]["law"]
    assert dv["draft"] is True


def test_shipped_rule_equals_code_defaults():
    # the shipped draft-psi-v1.yaml overlays to EXACTLY the in-module defaults
    # (the dials shipped-yaml-equals-defaults invariant, for the rule file).
    repo_root = Path(__file__).resolve().parents[1]
    loaded = ss._load_rule(repo_root, "draft-psi-v1")
    assert loaded["rule"] == ss._DRAFT_PSI_DEFAULTS


def test_selection_dial_default_and_enum():
    from laplace.pipeline import dials
    from laplace.web import dials_surface as ds
    # the live DEFAULT dial STAYS draft-psi-v1 (flipping it is his/orchestrator word);
    # the enum GAINS draft-psi-v2 so the dial CAN be set to it.
    assert dials.defaults()["selection"]["draft_psi"] == "draft-psi-v1"
    assert ds._LEAF_ENUMS["selection.draft_psi"] == {"draft-psi-v1", "draft-psi-v2"}


# ---------------------------------------------------------------------------
# DRAFT-PSI-V2 — THE REACH GATE (the isnad frame, PV-20260721T121500Z)
# ---------------------------------------------------------------------------

def _reach(depth, attested, total=10, gap=None):
    return {"links_total": total, "links_attested": attested,
            "depth_attested": depth,
            "frontier_gap": (total - attested if gap is None else gap)}


def test_v2_loads_with_reach_gate():
    # v2 is a NEW file: three v1 gates + ledger UNCHANGED, plus gate_reach ON. v1's
    # code defaults carry gate_reach OFF (the schema slot), so v1 round-trips inert.
    repo_root = Path(__file__).resolve().parents[1]
    v2 = ss._load_rule(repo_root, "draft-psi-v2")
    assert v2["version"] == "draft-psi-v2"
    assert v2["rule"]["gate_reach"] == {"aspiration_must_exist": True,
                                        "reach_must_not_fall": True}
    # the three v1 gates + ledger are byte-equal to v1's
    v1 = ss._load_rule(repo_root, "draft-psi-v1")
    for k in ("gate_self_consistency", "gate_cost", "gate_representation_stability",
              "promotion_ledger", "retire_when", "otherwise"):
        assert v2["rule"][k] == v1["rule"][k]
    # v1's own gate_reach is the inert default
    assert v1["rule"]["gate_reach"] == {"aspiration_must_exist": False,
                                        "reach_must_not_fall": False}


def test_v2_reach_null_holds_when_no_aspiration(tmp_path, monkeypatch):
    # a generation that banks NO aspiration under v2 → gate_reach null → HOLD, the
    # stall NAMED (silence never promotes), even though every v1 gate would pass.
    row, artifacts = _promote_gen()
    _setup(tmp_path, monkeypatch, gen_rows=[row], artifacts=artifacts,
           feedback_rows=[_clean_r10()], dial="draft-psi-v2")
    dv = ss.read_selection("tproj", root=tmp_path)["generations"][0]["draft_verdict"]
    assert dv["rule"] == "draft-psi-v2"
    assert dv["gates"]["gate_reach"]["pass"] is None
    assert dv["verdict"] == "hold"              # would-be promote, held by the reach gate
    assert any("aspiration absent" in r and "silence never promotes" in r
               for r in dv["reasons"])


def test_v2_reach_falling_fails_gate(tmp_path, monkeypatch):
    # gen1 reaches depth 3; gen2 RETREATS to depth 1 → gate_reach fails → HOLD.
    row1, art1 = _promote_gen(n=1, report_id="RPT-1")
    row2, art2 = _promote_gen(n=2, report_id="RPT-2")
    row1["reach"] = _reach(depth=3, attested=6)
    row2["reach"] = _reach(depth=1, attested=2)      # reach FELL
    _setup(tmp_path, monkeypatch, gen_rows=[row1, row2], artifacts={**art1, **art2},
           feedback_rows=[_clean_r10("RPT-1"), _clean_r10("RPT-2")],
           dial="draft-psi-v2")
    out = ss.read_selection("tproj", root=tmp_path)
    g2 = next(g for g in out["generations"] if g["n"] == 2)
    dv2 = g2["draft_verdict"]
    assert dv2["gates"]["gate_reach"]["pass"] is False
    assert dv2["verdict"] == "hold"
    assert any("FELL" in r for r in dv2["reasons"])
    # gen1 (no prior baseline) passes the reach gate on presence alone
    g1 = next(g for g in out["generations"] if g["n"] == 1)
    assert g1["draft_verdict"]["gates"]["gate_reach"]["pass"] is True


def test_v2_reach_growing_passes_and_promotes(tmp_path, monkeypatch):
    # gen1 depth 1; gen2 GROWS to depth 3 → gate_reach passes; with all v1 gates
    # passing and a positive net gain, gen2 PROMOTES under v2.
    row1, art1 = _promote_gen(n=1, report_id="RPT-1")
    row2, art2 = _promote_gen(n=2, report_id="RPT-2")
    row1["reach"] = _reach(depth=1, attested=2)
    row2["reach"] = _reach(depth=3, attested=6)      # reach GREW
    _setup(tmp_path, monkeypatch, gen_rows=[row1, row2], artifacts={**art1, **art2},
           feedback_rows=[_clean_r10("RPT-1"), _clean_r10("RPT-2")],
           dial="draft-psi-v2")
    out = ss.read_selection("tproj", root=tmp_path)
    g2 = next(g for g in out["generations"] if g["n"] == 2)
    dv2 = g2["draft_verdict"]
    assert dv2["gates"]["gate_reach"]["pass"] is True
    assert all(g["pass"] is True for g in dv2["gates"].values())
    assert dv2["verdict"] == "promote"
    assert any("held/grew" in r for r in dv2["reasons"])


def test_v2_live_reach_from_frozen_organ(tmp_path, monkeypatch):
    # the NEWEST generation with no banked snapshot reads the manuscript's LIVE reach
    # via the frozen derivation_organ.reach(md) — imported inside the reader. Here we
    # stand in a fake reach() + a banked aspiration record and prove the live reading
    # rides the gate. Patch reach() on the module (order-independent: patching
    # sys.modules is skipped once the package attribute is already bound by another
    # test's top-level import).
    row, artifacts = _promote_gen()
    md = _setup(tmp_path, monkeypatch, gen_rows=[row], artifacts=artifacts,
                feedback_rows=[_clean_r10()], dial="draft-psi-v2")
    (md / "aspiration").mkdir(parents=True, exist_ok=True)
    (md / "aspiration" / "aspiration.json").write_text(
        json.dumps({"record": "aspiration", "claim_maximal": "the furthest reach"}),
        encoding="utf-8")
    from laplace.pipeline import derivation_organ as _do
    monkeypatch.setattr(_do, "reach", lambda md_arg: _reach(depth=2, attested=5))
    g = ss.read_selection("tproj", root=tmp_path)["generations"][0]
    assert g["reach"] == _reach(depth=2, attested=5)
    assert g["draft_verdict"]["gates"]["gate_reach"]["pass"] is True   # present, no prior
    assert g["draft_verdict"]["verdict"] == "promote"


def test_v1_default_dial_has_no_reach_gate(tmp_path, monkeypatch):
    # under the DEFAULT dial (draft-psi-v1) the reach gate is never computed — the
    # verdict carries exactly the three v1 gates and no reach reading (byte-identical).
    row, artifacts = _promote_gen()
    _setup(tmp_path, monkeypatch, gen_rows=[row], artifacts=artifacts,
           feedback_rows=[_clean_r10()])            # dial defaults to draft-psi-v1
    g = ss.read_selection("tproj", root=tmp_path)["generations"][0]
    assert "gate_reach" not in g["draft_verdict"]["gates"]
    assert set(g["draft_verdict"]["gates"]) == {
        "gate_self_consistency", "gate_cost", "gate_representation_stability"}
    assert "reach" not in g and "prev_reach" not in g
    assert g["draft_verdict"]["verdict"] == "promote"
