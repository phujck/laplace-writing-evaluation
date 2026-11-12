"""E1 — the composed block + the four minting writers.

The composition layer (DESIGN_2026-07-22_the-interface-engine.md sections A and F):
every minted record that will ask for the author's attention carries a composed block,
authored at write time by the writer that held the integration context. Proven here:
the schema validator refuses a card-level consequence (F.1, the false-ruling class) and
barred vocabulary in the account fields; the fallback law renders absence explicitly and
never synthesises a glance; the freshness fingerprint is stable and is_fresh flips when a
dependency moves; the four minting writers (superego verdict, work order, goal-tension
row, demand audit) each emit a valid block; the tension card carries exactly the four
verbs with per-action consequence ownership and REGOAL's confirm gate non-null; and the
recommendation flag never encodes a selection.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from laplace.pipeline import composed


# ------------------------------------------------------------------ helpers
def _minimal(**over) -> dict:
    """A minimal valid block via the builder, overridable per test."""
    kw = dict(glance="A thing happened and it matters; a look is asked.",
              working="The manuscript gained a section; the goal is unchanged.",
              minted_by="test-writer", substrate_fingerprint="abc123")
    kw.update(over)
    return composed.make_composed(**kw)


# ============================================================ 1. schema validation
def test_builder_produces_a_valid_block_with_provenance_and_freshness():
    b = _minimal()
    composed.validate_composed(b)
    assert b["composition_version"] == 1
    assert b["minted_by"] == "test-writer"
    assert b["minted_at"]
    assert b["composed_against"]["substrate_fingerprint"] == "abc123"
    assert b["composed_against"]["record_ids"] == []
    assert b["audit"] == {"ids": [], "provenance": [], "citations": []}


def test_card_level_consequence_is_refused_F1():
    # F.1 — the false-ruling class: consequence lives ONLY on an actions[] row.
    b = _minimal()
    b["consequence"] = "the manuscript restructures"
    with pytest.raises(ValueError, match="card-level consequence"):
        composed.validate_composed(b)


def test_decision_level_action_keys_are_refused_F1():
    b = _minimal(decision={
        "tension": "the goal and the manuscript disagree",
        "actions": [{"verb": "run", "consequence": "it runs", "resolves": "the ask",
                     "writes": [], "recommended": False, "confirm": None}],
    })
    b["decision"]["writes"] = ["some-organ"]          # writes belongs on the row, not here
    with pytest.raises(ValueError, match="decision-level writes"):
        composed.validate_composed(b)


def test_barred_vocabulary_refused_in_glance():
    with pytest.raises(ValueError, match="raw record id"):
        _minimal(glance="Verdict SEV-20260722T101010Z stands and it matters.")


def test_barred_path_refused_in_working():
    with pytest.raises(ValueError, match="source path"):
        _minimal(working="The change lands in src/laplace/demand.py and holds.")


def test_barred_section_anchor_refused_in_consequence():
    with pytest.raises(ValueError, match="section anchor"):
        _minimal(decision={
            "tension": "a disagreement",
            "actions": [{"verb": "run",
                         "consequence": "the claim at sec:s3 is restructured",
                         "resolves": "the ask", "writes": [], "recommended": False,
                         "confirm": None}]})


def test_at_most_one_recommended_action():
    with pytest.raises(ValueError, match="at most one action may be recommended"):
        _minimal(decision={
            "tension": "a disagreement",
            "actions": [
                {"verb": "a", "consequence": "x", "resolves": "y", "writes": [],
                 "recommended": True, "confirm": None},
                {"verb": "b", "consequence": "x", "resolves": "y", "writes": [],
                 "recommended": True, "confirm": None},
            ]})


def test_composition_version_must_be_a_positive_int_not_bool():
    with pytest.raises(ValueError):
        _minimal(composition_version=0)
    with pytest.raises(ValueError):
        _minimal(composition_version=True)   # bool is an int subclass — refused


# ============================================================ 2. the fallback law
def test_absent_block_projects_explicit_absence_never_a_guess():
    record = {"id": "SEV-20200101T000000Z", "verdict": "STANDS", "claim": "old row"}
    proj = composed.project_altitude(record, "glance")
    assert proj["absent"] is True
    assert "no composed account" in proj["reason"]
    # the audit floor of raw ids — never a synthesised glance
    assert "glance" not in proj
    assert proj["audit"]["ids"] == ["SEV-20200101T000000Z"]


def test_present_block_projects_each_altitude():
    b = _minimal(decision={
        "tension": "t", "actions": [{"verb": "run", "consequence": "c", "resolves": "r",
                                     "writes": [], "recommended": False, "confirm": None}]})
    rec = {"composed": b}
    assert composed.project_altitude(rec, "glance")["glance"] == b["glance"]
    assert composed.project_altitude(rec, "working")["working"] == b["working"]
    assert composed.project_altitude(rec, "decision")["decision"] == b["decision"]
    assert composed.project_altitude(rec, "audit")["audit"] == b["audit"]


def test_unknown_altitude_raises():
    with pytest.raises(ValueError):
        composed.project_altitude({"composed": _minimal()}, "cockpit")


# ============================================================ 3. fingerprint + freshness
def test_fingerprint_is_stable_across_calls_and_whitespace():
    a = composed.fingerprint("the class-level result is the headline")
    b = composed.fingerprint("the  class-level   result is the headline")   # reflowed
    c = composed.fingerprint("the class-level result is NOT the headline")
    assert a == b            # normalisation absorbs whitespace
    assert a != c            # substance change moves it


def test_is_fresh_flips_when_substrate_moves():
    rec = {"composed": _minimal(substrate_fingerprint="fp-1", goal_version=1)}
    assert composed.is_fresh(rec, "fp-1", 1) == {"fresh": True, "moved": []}
    moved = composed.is_fresh(rec, "fp-2", 1)
    assert moved["fresh"] is False and moved["moved"] == ["substrate"]


def test_is_fresh_flips_when_goal_moves():
    rec = {"composed": _minimal(substrate_fingerprint="fp-1", goal_version=1)}
    moved = composed.is_fresh(rec, "fp-1", 2)
    assert moved["fresh"] is False and moved["moved"] == ["goal"]


def test_is_fresh_absent_block():
    assert composed.is_fresh({}, "fp", 1) == {"fresh": False, "moved": ["absent"]}


# ============================================================ 4. the tension card
def test_tension_card_has_exactly_the_four_verbs():
    gt_id, block = composed.compose_tension(
        node_id="res:headline", signature="DEMOTE", status="conjectured",
        goal_version=1, goal_essences=["a fast quantum estimate of the L2->L map"])
    composed.validate_composed(block)
    assert gt_id.startswith("GT-")
    verbs = [a["verb"] for a in block["decision"]["actions"]]
    assert verbs == ["REALIGN/RESPINE", "REGOAL", "HOLD/WAIVE", "DISMISS SIGNAL"]


def test_tension_regoal_confirm_gate_is_non_null_and_marked_reconstructed():
    _gt, block = composed.compose_tension(
        node_id="res:headline", signature="DEMOTE", status="conjectured",
        goal_version=1, goal_essences=["the class-level scaling result"])
    regoal = next(a for a in block["decision"]["actions"] if a["verb"] == "REGOAL")
    assert regoal["confirm"] is not None
    assert "confirm or correct" in regoal["confirm"]
    assert "the class-level scaling result" in regoal["confirm"]
    # the other verbs carry no confirm gate
    for a in block["decision"]["actions"]:
        if a["verb"] != "REGOAL":
            assert a["confirm"] is None


def test_tension_regoal_confirm_non_null_even_without_essences():
    _gt, block = composed.compose_tension(
        node_id="res:x", signature="DEMOTE", status="exploratory")
    regoal = next(a for a in block["decision"]["actions"] if a["verb"] == "REGOAL")
    assert regoal["confirm"] is not None      # the gate never vanishes


def test_tension_recommendation_never_encodes_a_selection():
    _gt, block = composed.compose_tension(
        node_id="res:headline", signature="DEMOTE", status="conjectured")
    # the machine does not pre-lean here — no action is recommended, none is selected
    assert sum(1 for a in block["decision"]["actions"] if a["recommended"]) == 0
    # there is no 'selected' field anywhere on the card
    assert all("selected" not in a for a in block["decision"]["actions"])


def test_tension_id_is_stable_across_recomputation():
    a, _ = composed.compose_tension(node_id="res:h", signature="DEMOTE",
                                    status="conjectured", goal_version=1)
    b, _ = composed.compose_tension(node_id="res:h", signature="DEMOTE",
                                    status="conjectured", goal_version=1)
    c, _ = composed.compose_tension(node_id="res:h", signature="DEMOTE",
                                    status="conjectured", goal_version=2)
    assert a == b            # same inputs → same id (addressable across recomputes)
    assert a != c            # a new goal version is a new detection identity


def test_tension_account_carries_no_barred_vocabulary():
    # the node id is present under audit, never in glance/working
    _gt, block = composed.compose_tension(node_id="sec:s3", signature="DEMOTE",
                                          status="conjectured")
    assert "sec:s3" not in block["glance"]
    assert "sec:s3" not in block["working"]
    assert "sec:s3" in block["audit"]["ids"]


# ============================================================ 5. the mint sites
def test_superego_verdict_mints_a_valid_block(tmp_path: Path):
    from laplace.engine import superego
    rec = {
        "station": "wave-close",
        "claim": "the composed block lands on every minting writer",
        "verdict": "STANDS",
        "judge": "judge-b", "builder": "builder-a",
        "questions": [{"question": "does every mint site compose at write time?",
                       "answer": "yes, all four writers emit a block", "served": "yes"}],
        "defects": [], "refs": ["DESIGN_2026-07-22"],
    }
    stored = superego.bank_verdict(tmp_path, rec)
    assert "composed" in stored
    composed.validate_composed(stored["composed"])
    assert stored["composed"]["decision"] is None            # a verdict is read, not ruled on
    assert stored["composed"]["audit"]["ids"] == [stored["id"]]
    assert stored["composed"]["audit"]["provenance"] == ["DESIGN_2026-07-22"]
    # the working account is the questions-as-prose
    assert "does every mint site" in stored["composed"]["working"].lower()


def test_superego_keeps_a_caller_authored_block(tmp_path: Path):
    from laplace.engine import superego
    authored = _minimal(glance="the judge composed this account itself",
                         minted_by="judge-b")
    rec = {
        "station": "wave-close", "claim": "a judge authored its own composed block",
        "verdict": "STANDS", "judge": "judge-b", "builder": "builder-a",
        "questions": [{"question": "kept?", "answer": "yes", "served": "yes"}],
        "defects": [], "refs": [], "composed": authored,
    }
    stored = superego.bank_verdict(tmp_path, rec)
    assert stored["composed"]["glance"] == "the judge composed this account itself"


def test_work_order_mints_a_valid_block_with_run_and_drop(tmp_path: Path):
    from laplace.manuscript import storyboard
    (tmp_path / "corpus_friction").mkdir(parents=True, exist_ok=True)
    rec = storyboard.bank_work_order("paper_x", "harnessed-round", "tester",
                                     root=tmp_path)
    assert "composed" in rec
    composed.validate_composed(rec["composed"])
    verbs = [a["verb"] for a in rec["composed"]["decision"]["actions"]]
    assert verbs == ["run", "drop"]
    # per-action ownership: each row owns its own consequence/writes/confirm/recommended
    for a in rec["composed"]["decision"]["actions"]:
        assert set(("consequence", "writes", "recommended", "confirm")) <= set(a)
    # the block was persisted, not only returned
    row = json.loads((tmp_path / "corpus_friction" / "work_orders.jsonl")
                     .read_text().splitlines()[0])
    assert "composed" in row


def test_goal_tension_mint_site_emits_a_block():
    from laplace.pipeline import demand
    net = {"nodes": {"res:headline": {"kind": "result", "status": "conjectured"}},
           "edge_index": {}, "spine": [{"id": "res:headline"}]}
    rows = demand.goal_tensions_over_net(net, goal_version=1,
                                         goal_essences=["the headline scaling result"])
    assert len(rows) == 1
    row = rows[0]
    assert row["id"].startswith("GT-")
    composed.validate_composed(row["composed"])
    # is_fresh is true at emit by construction (the detector holds the drift context)
    ca = row["composed"]["composed_against"]
    assert composed.is_fresh(row, ca["substrate_fingerprint"], 1)["fresh"] is True


def test_audit_row_helper_emits_a_valid_read_only_block():
    dq_id, block = composed.compose_audit_row(
        demand_id="D-honest-status", verdict="red", node_ids=["sec:s3", "res:x"],
        detail="check_coherence: 2 failing nodes", goal_version=1)
    composed.validate_composed(block)
    assert dq_id.startswith("DQ-")
    assert block["decision"] is None                # a queue row is ruled through its queue
    # the failing node ids live under audit, never in the account
    assert "sec:s3" not in block["glance"] and "sec:s3" not in block["working"]
    assert "sec:s3" in block["audit"]["ids"]


def test_coverage_row_helper_states_a_real_zero():
    block = composed.compose_coverage_row(axis="supports", covered=0, total=4,
                                          goal_version=1)
    composed.validate_composed(block)
    assert block["decision"] is None
    assert "measured" in block["glance"]            # a real zero, not a caveated bar


def test_demand_audit_composes_every_row_on_a_real_corpus():
    from laplace.research import corpus_ingest as ci
    from laplace.pipeline import demand
    repo = Path(__file__).resolve().parents[1]
    corpus = "paper_falqon"
    if ci.resolve_corpus(repo, corpus) is None:
        pytest.skip(f"{corpus} corpus not present")
    out = demand.audit(repo, corpus)
    assert len(out["rows"]) == 20
    for row in out["rows"]:
        assert row["id"].startswith("DQ-")
        composed.validate_composed(row["composed"])
    cov = demand.coverage_vector(repo, corpus)
    for ax in ("literature", "validation", "demonstration"):
        composed.validate_composed(cov[ax]["composed"])
