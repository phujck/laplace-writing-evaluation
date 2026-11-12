"""bite-zero-judge: adversarial regression probes banked against bite-zero A/B.

These lock in behaviour a FRESH JUDGE verified by hand and that had NO existing
coverage in the suite:

* the ``removals`` evolution-contract section (bite-zero-A's draft-only DELETE
  door) — collision-proofing + delete-node emission + expected-delta accounting.
  The suite carried zero references to ``removals`` before this file.
* ``ledger.pour_finding`` boundary guards (bite-zero-B's honest pour) — the
  leading-``N``-token-only section anchor (a finding that merely quotes a
  ``\\ref`` to another section is NOT mis-anchored), and the refusal of a
  section-less / id-less pour.
* RESOLUTION + intent-revoke exclusion completeness — both action records are
  dropped by the intake door AND the review surface's findings board (never read
  back as findings).

Every test here PASSES against the shipped code (0885de4, c68675a); each is the
positive lock of a claim the judge re-derived independently.
"""
from __future__ import annotations

import pytest

from laplace.pipeline import evolve, ledger, schema
from laplace.pipeline import adjudicate as _adj
from laplace.pipeline import propagate as prop
from laplace.manuscript import review_surface


# ---------------------------------------------------------------------------
# bite-zero-A — the ``removals`` contract section (was untested)
# ---------------------------------------------------------------------------

def test_removals_is_a_recognised_substrate_section():
    assert "removals" in schema.EVOLUTION_SUBSTRATE_SECTIONS


def test_removals_emits_delete_node_and_counts_as_removed():
    contract = {"shape": "substrate", "removals": ["derivation:ghost"]}
    recs = evolve.plan_records(contract)
    assert [(r["kind"], r["node"]) for r in recs] == [("delete-node", "derivation:ghost")]
    added, removed = evolve._expected_delta(contract)
    assert removed == {"derivation:ghost"} and added == set()


def test_removal_colliding_with_a_same_contract_mint_is_refused():
    # the builder's collision-proofing: a contract that mints AND removes the same
    # id is incoherent and must be refused before any ledger write.
    contract = {"shape": "substrate",
                "mints": [{"id": "ref:x", "node_kind": "citation", "essence": "e"}],
                "removals": [{"id": "ref:x"}]}
    with pytest.raises(evolve.EvolveError):
        evolve.plan_records(contract)


def test_removal_without_an_id_is_refused():
    with pytest.raises(evolve.EvolveError):
        evolve.plan_records({"shape": "substrate", "removals": [{}]})


# ---------------------------------------------------------------------------
# bite-zero-B — ledger.pour_finding boundary guards
# ---------------------------------------------------------------------------

def test_pour_leading_n_token_wins_over_a_midstring_ref(tmp_path):
    # a finding whose `where` LEADS with its own section token but also quotes a
    # \ref to a different section is anchored to the LEADING token, never the ref.
    rec = ledger.pour_finding(
        tmp_path / "fb.jsonl",
        {"reader": "R2", "kind": "referee-insufficient",
         "where": r"N2-p3 quotes Sec.~\ref{sec:N5} in passing", "issue": "w"},
        project="p")
    assert rec["section"] == "N2" and rec["anchor"]["section"] == "N2"


def test_pour_refuses_a_finding_that_only_quotes_a_ref(tmp_path):
    # leading token is prose ("In the intro..."), the only section marker is a
    # mid-string \ref — the conservative deriver refuses rather than mis-anchor.
    with pytest.raises(ValueError):
        ledger.pour_finding(
            tmp_path / "fb.jsonl",
            {"reader": "R1", "kind": "cold-undefined-term",
             "where": r"In the introduction, see Sec.~\ref{sec:N5}", "issue": "q"})


def test_pour_refuses_section_less_and_idless(tmp_path):
    with pytest.raises(ValueError):
        ledger.pour_finding(
            tmp_path / "fb.jsonl",
            {"reader": "R1", "kind": "cold-undefined-term",
             "where": "no locatable token here", "issue": "z"})


# ---------------------------------------------------------------------------
# bite-zero-B — RESOLUTION + intent-revoke are NEVER read back as findings
# ---------------------------------------------------------------------------

_MIN_PLAN = {
    "meta": {"project": "toy"},
    "sections": [{"id": "S1", "beats": ["res:beat-a"],
                  "nodes_in_order": ["res:beat-a"], "figures": []}],
    "appendices": [],
}


def test_resolution_and_intent_revoke_are_non_finding_records():
    res = _adj.make_resolution("FB-x", project="p")
    rev = _adj.make_intent_revocation("CI-x", project="p")
    # discriminator field is `record`, and both are in the action-record family
    assert res["record"] in _adj.ADJ_RECORD_KINDS
    assert rev["record"] in _adj.ADJ_RECORD_KINDS
    # the review surface's findings board excludes the same family
    assert res["record"] in review_surface._NON_FINDING_RECORDS
    assert rev["record"] in review_surface._NON_FINDING_RECORDS


def test_intake_door_drops_resolution_and_intent_revoke():
    res = _adj.make_resolution("FB-x", project="p")
    rev = _adj.make_intent_revocation("CI-x", project="p")
    # neither carries a routable finding kind; both must be dropped as actions,
    # not raise the unrouted-kind gate.
    items = prop.intake_items([res, rev], _MIN_PLAN, {})
    assert items == []


def test_resolution_supersedes_its_target_in_the_intake_view():
    # a live finding retired by a RESOLUTION never surfaces as work.
    original = {"id": "FB-orig", "kind": "cold-undefined-term",
                "section": "S1", "anchor": {"section": "S1"},
                "where": "N1-p1 blah"}
    res = _adj.make_resolution("FB-orig", project="p")
    items = prop.intake_items([original, res], _MIN_PLAN, {})
    assert all(it.get("id") != "FB-orig" for it in items)
