"""G4 — the demand registry + gauges + the refusal router.

The manuscript FORM object's 20 D-demands, wrapped as DATA over the existing scattered
checks; the token-free demand audit whose strongest verdict is floor-holds (never
'passed'); the per-axis coverage vector with honest zeros on real denominators; the
DEMOTE goal-tension detector; and the refusal router that mints typed feedback through
the one intake door. Proven inert on a real corpus (subset-sum-itqde round-trip).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from laplace.research import corpus_ingest as ci
from laplace.pipeline import demand, propagate, schema

REPO = Path(__file__).resolve().parents[1]

# The 20 D-demand bullets of canon/wiki/workflow/manuscript_projection.md (the doc's
# approximate "20"; the +1 is D-asset-existence-out-of-loop, itself flagged as Ring IV's
# sharpening of D-figure-resolves). The registry must carry each exactly once.
_PROSE_DEMANDS = {
    "D-roadmap", "D-sections-close-the-primitives", "D-every-claim-has-a-result",
    "D-figure-resolves", "D-ends-on-the-frontier",
    "D-no-naked-claims", "D-real-corpus-citation", "D-honest-status",
    "D-equation-grounded", "D-caption-true", "D-one-document",
    "D-motivated-sections", "D-define-before-use", "D-no-leaked-meta", "D-reader-floor",
    "D-house-document-class", "D-figures-to-house-style", "D-house-typography-mechanics",
    "D-forge-compiler", "D-asset-existence-out-of-loop",
}


# ============================================================ 1. the registry as data

def test_every_prose_demand_appears_exactly_once():
    ids = [d["id"] for d in demand.DEMANDS]
    assert len(ids) == len(set(ids)), "a demand id is duplicated"
    assert set(ids) == _PROSE_DEMANDS, "the registry does not match the prose doc's D- bullets"


def test_ring_and_friction_and_activation_are_typed():
    for d in demand.DEMANDS:
        assert d["ring"] in demand.RINGS
        assert d["default_friction_type"] in demand.FRICTION_TYPES
        ga = d["goal_activation"]
        assert ga == "always" or ga.startswith("goal-conditioned:")
        assert d["note"].strip(), f"{d['id']} carries no naming note"


def test_oracle_rows_carry_no_mechanical_check():
    # the ~7 judged-tier demands render judged-pending by construction — no verify/loop_gates
    split = demand.registry_split()
    assert len(split["oracle_tier"]) == 7
    for did in split["oracle_tier"]:
        oc = demand.demand_by_id(did)["owning_check"]
        assert oc.startswith("oracle:"), f"{did} is oracle-tier but names a mechanical check"
    # and no oracle id leaks into the mechanical tier
    assert set(split["oracle_tier"]).isdisjoint(split["mechanical_tier"])


def test_registry_split_counts():
    split = demand.registry_split()
    assert split["total"] == 20
    assert split["per_ring"] == {"I completeness": 5, "II consistency": 6,
                                 "III clarity": 4, "IV presentation": 5}
    # 5 run on the symbolic wire; the rest are rendered/unbuilt/oracle
    assert len(split["runnable_here_symbolic"]) == 5
    assert len(split["unbuilt_ring_iv"]) == 4


# ============================================================ 2. the audit, token-free

def test_audit_verdict_vocabulary_has_no_passed():
    # the demand-audit-floor-honest contract: 'passed' is structurally unavailable
    assert "passed" not in demand.AUDIT_VERDICTS
    assert "pass" not in demand.AUDIT_VERDICTS


def test_audit_on_real_corpus_floor_honest():
    corpus = "subset-sum-itqde"
    if ci.resolve_corpus(REPO, corpus) is None:
        pytest.skip(f"{corpus} corpus not present")
    out = demand.audit(REPO, corpus)
    rows = out["rows"]
    assert len(rows) == 20
    # every verdict is in the honest vocabulary; none is 'passed'/'pass'
    for r in rows:
        assert r["verdict"] in demand.AUDIT_VERDICTS
    blob = json.dumps(rows)
    assert '"verdict": "passed"' not in blob and '"verdict": "pass"' not in blob
    # the 7 oracle demands render judged-pending, never green
    oracle = {d for d in _PROSE_DEMANDS
              if demand.demand_by_id(d)["owning_check"].startswith("oracle:")}
    for r in rows:
        if r["demand_id"] in oracle:
            assert r["verdict"] == "judged-pending"
            assert r["node_ids"] == []
    # honest-status is red with the fail-names-node-ids shape (no gate reads the G1 slot yet)
    hs = next(r for r in rows if r["demand_id"] == "D-honest-status")
    assert hs["verdict"] == "red" and hs["node_ids"], "honest-status floor should be red today"
    # a symbolic gate actually ran and held (coherence/substrate on the finished corpus)
    assert any(r["verdict"] == "floor-holds" for r in rows)
    # the Ring IV house demands are honestly out of the symbolic audit's reach
    for r in rows:
        if r["ring"] == "IV presentation" and demand.demand_by_id(
                r["demand_id"])["owning_check"].startswith("unbuilt:"):
            assert r["verdict"] == "not-runnable-here"


def test_audit_summary_partitions_the_rows():
    corpus = "subset-sum-itqde"
    if ci.resolve_corpus(REPO, corpus) is None:
        pytest.skip(f"{corpus} corpus not present")
    s = demand.audit(REPO, corpus)["summary"]
    total = (s["red"] + s["floor_holds"] + s["judged_pending"]
             + s["not_runnable_here"] + s["inactive"])
    assert total == s["n_demands"] == 20
    # the full split pinned (the G4 judge's coverage-gap note: a loose assertion let
    # a misreported split ride green). These numbers change only when a gate lands
    # or a demand activates - a drift here is a finding, not noise.
    assert s["red"] == 1
    assert s["floor_holds"] == 4
    assert s["judged_pending"] == 7
    assert s["not_runnable_here"] == 8
    assert s["inactive"] == 0


def test_audit_bad_corpus_raises_not_fakes_a_floor():
    with pytest.raises(ValueError):
        demand.audit(REPO, "no-such-corpus-xyz")


# ============================================================ 2b. the status floor

def test_status_floor_flags_missing_and_holds_when_present():
    net = {"nodes": {
        "res:a": {"kind": "result"},                       # no status → flagged
        "thm:b": {"kind": "theorem", "status": "proven"},  # canonical → ok
        "res:c": {"kind": "result", "status": "cited"},    # legacy carrier folds → imported → ok
        "def:d": {"kind": "definition"},                   # not load-bearing → ignored
    }, "edge_index": {}, "spine": []}
    res = demand.status_floor(net)
    assert res["load_bearing"] == 3
    assert res["missing_status"] == ["res:a"]
    assert res["pass"] is False


# ============================================================ 3. the coverage vector

def test_coverage_honest_zeros_with_real_denominators():
    # two load-bearing claims, one supports edge → 1/2 literature; validation/demonstration 0/N
    net = {"nodes": {
        "res:a": {"kind": "result"}, "res:b": {"kind": "result"},
        "ref:foo": {"kind": "citation"},
    }, "edge_index": {
        # bearer-keyed (the reconciled direction): the supports token lives ON the
        # literature node, targeting the claim it bears
        "ref:foo": ["ref:foo", schema.token_for("supports", "res:a")],
        "res:b": ["res:b"],
    }, "spine": []}
    cov = demand.coverage_over_net(net)
    assert cov["load_bearing_claims"] == 2
    assert cov["literature"] == {"axis": "supports", "covered": 1, "total": 2,
                                 "fraction": 0.5, "uncovered": ["res:b"]}
    assert cov["validation"]["covered"] == 0 and cov["validation"]["total"] == 2
    assert cov["demonstration"]["covered"] == 0 and cov["demonstration"]["total"] == 2


def test_coverage_validates_dereference_and_demonstration():
    net = {"nodes": {
        "res:a": {"kind": "result"}, "fig:x": {"kind": "figure"}, "read:y": {"kind": "support"},
    }, "edge_index": {
        # validates stays claim-keyed (leg 2's convention, direction-consistent);
        # demonstrates is bearer-keyed - the token lives ON the figure (leg 3)
        "res:a": ["res:a",
                  schema.token_for("validates", "read:y"),        # resolves → counts
                  schema.token_for("validates", "read:missing")], # dangles → dropped
        "fig:x": [schema.token_for("demonstrates", "res:a")],
    }, "spine": []}
    cov = demand.coverage_over_net(net)
    assert cov["validation"]["covered"] == 1        # the resolvable reading counts
    assert cov["demonstration"] == {"axis": "demonstrates", "covered": 1, "total": 1,
                                    "fraction": 1.0, "uncovered": []}


def test_coverage_absolute_zero_registers_no_crash():
    cov = demand.coverage_over_net({"nodes": {}, "edge_index": {}, "spine": []})
    assert cov["load_bearing_claims"] == 0
    for ax in ("literature", "validation", "demonstration"):
        assert cov[ax]["covered"] == 0 and cov[ax]["total"] == 0 and cov[ax]["fraction"] == 0.0


def test_coverage_on_real_falqon_renders_honest_zeros():
    """POST-W-G (commit 651d1eb, 2026-07-22): the coverage gauge is now WIRED to the substrate, so
    the axes no longer all read a pre-wave zero. paper_falqon's VALIDATION axis truthfully reads
    17/22 — G3's live claim->validation pointers (banked by the growth-stage close but never wired
    into the conceptric edge_index the gauge walks) are now `validates`-axis edges the gauge counts
    DETERMINISTICALLY at build time from the evidence ledger + numerics store. LITERATURE and
    DEMONSTRATION stay EARNED ZEROS (no citation / demonstration edges poured yet). This SUPERSEDES the
    pre-W-G snapshot this test used to pin ('G3 has not landed the axes yet', 0/22 on every axis)."""
    corpus = "paper_falqon"
    if ci.resolve_corpus(REPO, corpus) is None:
        pytest.skip(f"{corpus} corpus not present")
    cov = demand.coverage_vector(REPO, corpus)
    assert cov["load_bearing_claims"] == 22          # a REAL denominator
    # validation is WIRED now (W-G): 17 of the 22 load-bearing claims carry validation edges.
    assert cov["validation"]["covered"] == 17 and cov["validation"]["total"] == 22, \
        f"validation should read 17/22 post-W-G, got {cov['validation']}"
    # literature + demonstration stay earned zeros — no citation / demonstration edges are poured yet.
    for ax in ("literature", "demonstration"):
        assert cov[ax]["covered"] == 0, f"{ax} must stay an earned zero, got {cov[ax]}"


# ============================================================ 3b. the goal-tension detector

def test_demote_fires_only_for_spine_and_demoted():
    net = {"nodes": {
        "res:headline": {"kind": "result", "status": "conjectured"},  # spine + demoted → DEMOTE
        "res:solid": {"kind": "result", "status": "proven"},          # spine + proven → no
        "res:offspine": {"kind": "result", "status": "exploratory"},  # demoted but off-spine → no
    }, "edge_index": {}, "spine": [{"id": "res:headline"}, {"id": "res:solid"}]}
    rows = demand.goal_tensions_over_net(net)
    assert len(rows) == 1
    assert rows[0] == {**rows[0], "node_id": "res:headline", "signature": "DEMOTE",
                       "status": "conjectured", "friction_type": "TENSION",
                       "demand": "D-honest-status"}


def test_demote_honest_zero_when_no_status():
    # today's substrate carries no status (G3 writes them) → the detector is wired, not faked
    net = {"nodes": {"res:a": {"kind": "result"}},
           "edge_index": {}, "spine": [{"id": "res:a"}]}
    assert demand.goal_tensions_over_net(net) == []


# ============================================================ 4. the refusal router

def _refuted_verdict():
    return {
        "id": "SEV-test", "station": "wave-close", "verdict": "REFUTED",
        "claim": "the audit is complete", "judge": "j", "builder": "b",
        "questions": [
            {"question": "every claim has a result?", "answer": "no", "served": "no",
             "demand": "D-every-claim-has-a-result", "node_id": "res:stub"},
            {"question": "house class REVTeX?", "answer": "partial", "served": "partial",
             "demand": "D-house-document-class"},
            {"question": "honest tier?", "answer": "no", "served": "no",
             "demand": "D-honest-status"},
            {"question": "abstract present?", "answer": "yes", "served": "yes"},  # not routed
        ],
        "defects": [
            {"severity": "must-fix", "what": "naked citation", "evidence": "s3:44",
             "friction": "CONTENT"},
            {"severity": "note", "what": "caption over-claims", "evidence": "fig2",
             "demand": "D-caption-true"},
        ],
    }


def test_route_refusal_classes_and_counts():
    r = demand.route_refusal(REPO, _refuted_verdict())
    assert r["counts"] == {"CONTENT": 3, "FORM": 1, "TENSION": 1}
    # the registry drives the class: house-class → FORM, caption → TENSION, claim-result → CONTENT
    by_demand = {x.get("demand"): x for x in r["routed"] if x.get("demand")}
    assert by_demand["D-house-document-class"]["friction"] == "FORM"
    assert by_demand["D-house-document-class"]["owning_stage"] == "demand-registry"
    assert by_demand["D-caption-true"]["friction"] == "TENSION"
    assert by_demand["D-caption-true"]["owning_stage"] == "goal-tension-queue"
    assert by_demand["D-honest-status"]["friction"] == "CONTENT"


def test_route_refusal_sticky_questions_only_unserved():
    r = demand.route_refusal(REPO, _refuted_verdict())
    # the served=yes question never sticks; the three no/partial ones do
    assert len(r["sticky_questions"]) == 3
    assert "abstract present?" not in r["sticky_questions"]
    assert "every claim has a result?" in r["sticky_questions"]


def test_route_refusal_content_becomes_mint_work_items_through_the_one_door():
    r = demand.route_refusal(REPO, _refuted_verdict())
    # only CONTENT demands new substance → mint work items; FORM/TENSION route as comments
    assert len(r["work_items"]) == 3
    assert all(w["kind"] == "mint" and w["owning_stage"] == "projection"
               for w in r["work_items"])
    # a node-carrying CONTENT question mints against its node
    assert any(w["target"] == "res:stub" for w in r["work_items"])


def test_route_refusal_explicit_friction_overrides_demand_lookup():
    v = {"id": "x", "verdict": "REFUTED", "claim": "c", "questions": [],
         "defects": [{"severity": "note", "what": "w", "evidence": "e",
                      "demand": "D-honest-status", "friction": "TENSION"}]}
    r = demand.route_refusal(REPO, v)
    assert r["routed"][0]["friction"] == "TENSION"     # explicit wins over the demand's CONTENT


def test_route_refusal_partial_stands_routes_its_unserved_rows():
    v = {"id": "y", "verdict": "STANDS", "claim": "c",
         "questions": [{"question": "q1", "answer": "mostly", "served": "partial",
                        "demand": "D-no-naked-claims"}],
         "defects": []}
    r = demand.route_refusal(REPO, v)
    assert r["counts"]["CONTENT"] == 1
    assert r["sticky_questions"] == ["q1"]


# ============================================================ 5. the schema additive rows

def test_growth_kinds_registered_additively():
    assert schema.KIND_TO_WORK["growth-content"] == "mint"
    assert schema.KIND_TO_WORK["growth-form"] is None
    assert schema.KIND_TO_WORK["growth-tension"] is None
    # existing routings untouched (spot-check a couple)
    assert schema.KIND_TO_WORK["missing-derivation"] == "derive"
    assert schema.KIND_TO_WORK["naked-claim"] == "prose"


def test_intake_door_accepts_the_growth_kinds_without_raising():
    # the door RAISES on an unrouted kind by design — prove the three are routed
    recs = [
        {"id": "1", "kind": "growth-content", "node_id": "res:x", "text": "t"},
        {"id": "2", "kind": "growth-form", "text": "t"},
        {"id": "3", "kind": "growth-tension", "text": "t"},
    ]
    items = propagate.intake_items(recs, {}, {})
    # only growth-content demands work (mint); form/tension are None-routed comments
    assert [it["kind"] for it in items] == ["mint"]


def test_intake_door_still_raises_on_a_truly_unrouted_kind():
    with pytest.raises(ValueError):
        propagate.intake_items([{"id": "1", "kind": "not-a-registered-kind", "text": "t"}],
                               {}, {})


# ============================================================ 6. inertness (the round-trip)

# Frozen from the pre-G4 build (identical to the G1 baseline): importing demand + the
# additive schema rows must move NOTHING in the built network.
_BASE = {"n_nodes": 494, "node_hash": "df0595a17a0f2f30",
         "n_edge_refs": 2926, "ei_hash": "e0b18b819150292f", "n_spine": 15}


def test_subset_sum_build_unchanged_by_g4():
    tex_root = REPO / "synthetics papers/subset-sum-itqde/manuscript/tex"
    if not (tex_root / "main.tex").is_file():
        pytest.skip("subset-sum-itqde corpus not present")
    net = ci.corpus_network(tex_root, REPO, "subset-sum-itqde")
    ids = sorted(net["nodes"])
    ei = net["edge_index"]
    node_hash = hashlib.sha256("\n".join(ids).encode()).hexdigest()[:16]
    ei_hash = hashlib.sha256(
        json.dumps({k: sorted(v) for k, v in ei.items()}, sort_keys=True).encode()
    ).hexdigest()[:16]
    assert len(ids) == _BASE["n_nodes"] and node_hash == _BASE["node_hash"]
    assert sum(len(v) for v in ei.values()) == _BASE["n_edge_refs"]
    assert ei_hash == _BASE["ei_hash"] and len(net["spine"]) == _BASE["n_spine"]


def test_bearer_keyed_coverage_reads_the_emitted_direction():
    # the G3 judge's direction catch, closed: a supports/demonstrates token lives on
    # the bearer (ref:/fig:) targeting the claim/result, and coverage credits the target
    from laplace.pipeline import schema
    net = {"nodes": {"res:foo": {"kind": "result"}, "ref:a": {"kind": "citation"},
                     "fig:f": {"kind": "figure"}},
           "edge_index": {"ref:a": ["res:foo", schema.token_for("supports", "res:foo")],
                          "fig:f": [schema.token_for("demonstrates", "res:foo")]}}
    cov = demand.coverage_over_net(net)
    assert cov["literature"]["covered"] == 1 and cov["literature"]["uncovered"] == []
    assert cov["demonstration"]["covered"] == 1
