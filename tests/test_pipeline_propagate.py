"""The propagate operator (P3): the minimal propagation from a perturbation.

(a) the LIVE PROOF over the real subset-sum-itqde intake ledger — the typed
worklist DAG with every derivation blocked into its section's prose re-run;
(b) synthetic change-set classification (re-homing, essence edits, reorders);
(c) purity — propagate never writes; (d) the KIND_TO_WORK completeness gate
that catches a new feedback kind arriving without routing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from laplace.pipeline import ledger, registry, schema
from laplace.pipeline import propagate as prop

RR = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# (a) the live proof — acceptance gate 8b
# ---------------------------------------------------------------------------

def test_live_ledger_emits_the_typed_worklist_dag():
    rep = prop.propagate("subset-sum-itqde")
    wl = rep["worklist"]

    # exact counts, recomputed from the ledger so the pin can never drift from
    # the intake it proves. The recount mirrors the intake door in full: resolved
    # records are spent, a record named by a later record's ``supersedes`` is
    # retired (the append-only correction mechanism). For the WORK-kind counts the
    # ACTION records (adjudications/suppressions/author-edits) are excluded EXACTLY
    # as the door excludes them — a ``confirmation`` whose ``kind`` mirrors its
    # target finding's kind (e.g. figure-standard) is a verdict, never a figure
    # work item, so counting it double-reads a finding intake never dispatches.
    from laplace.pipeline import adjudicate as _adj, edits as _edits, suppress as _sup
    _non_finding = (set(_adj.ADJ_RECORD_KINDS)
                    | {_sup.RECORD_KIND, _sup.REVOKE_KIND, _edits.RECORD_KIND})
    recs = ledger.live_findings(
        ledger.read_jsonl(RR / registry.resolve("subset-sum-itqde").feedback_ledger))
    superseded = {r["supersedes"] for r in recs if r.get("supersedes")}
    live = [r for r in recs if (r.get("status") or "open") != "resolved"
            and r.get("id") not in superseded]
    findings = [r for r in live if r.get("record") not in _non_finding]
    by_work: dict = {}
    for r in findings:
        by_work[schema.KIND_TO_WORK.get(r.get("kind"))] = \
            by_work.get(schema.KIND_TO_WORK.get(r.get("kind")), 0) + 1
    for work in ("derive", "simulate", "figure", "mint"):
        assert sum(1 for w in wl if w["kind"] == work) == by_work.get(work, 0), work
    # comments_routed counts EVERY live None-routed record — findings AND the
    # action records whose kind maps to None (intent-revoke / conceptric-intent /
    # …) — exactly as propagate's own comment tally does (it does not exclude the
    # action family), so this compares over the FULL live view, not `findings`.
    none_over_live = sum(1 for r in live if schema.KIND_TO_WORK.get(r.get("kind")) is None)
    assert rep["comments_routed"] == none_over_live

    # the standing WK-050 residue is PRESENT as a subset (the 2026-07-09
    # post-rebuild residue: WK-050's simulation + its owning section's
    # synthesised prose re-run blocked on it). The ledger legitimately GROWS
    # with live pipeline use (the convergence loop pours findings through the
    # one door), so exact totals are not pinned - that snapshot pin was a time
    # bomb the first real convergence run tripped (2026-07-10).
    assert rep["comments_routed"] >= 5
    sim = next(w for w in wl if w["kind"] == "simulate"
               and w.get("target") == "irf:retained-overlap-budget")
    rerun = next(w for w in wl if w["kind"] == "prose"
                 and sim["id"] in (w.get("blocked_by") or []))
    assert sim["target"] == "irf:retained-overlap-budget"
    assert sim["worker"] == "script-or-agent:numerics"
    assert rerun["section"] == sim["section"] and sim["id"] in rerun["blocked_by"]

    plan = registry.resolve("subset-sum-itqde").read_plan(RR)
    section_ids = {sec.get("id") for sec in schema.plan_sections(plan)}
    assert sim["section"] in section_ids       # anchored to the LIVE arc

    # zero cycles: the returned order IS a topological order
    ids = {w["id"] for w in wl}
    seen: set[str] = set()
    for w in wl:
        assert set(w["blocked_by"]) & ids <= seen, w["id"]
        seen.add(w["id"])
    assert not any("cycle_dropped" in w for w in wl)

    # the full item contract, and dispatch covers every worked PLAN section.
    # Scoped to plan sections by the same anti-drift discipline the count pins
    # follow (above): the live ledger has grown to hold findings banked with
    # malformed section anchors ('?', a raw section_ref like
    # 'numerical_validation→app:NA2'), whose work items land on sections that are
    # NOT in the plan — and ``minimum_dispatch`` is built over plan sections only,
    # so it can never contain them. The proof that matters holds: every worked
    # section that IS a plan section is dispatched.
    for w in wl:
        assert set(schema.WORK_ITEM_FIELDS) <= set(w)
    worked_plan_sections = {w["section"] for w in wl if w["section"] in section_ids}
    assert worked_plan_sections <= set(rep["minimum_dispatch"])


# ---------------------------------------------------------------------------
# (b) synthetic change-set — the dirty classification behaviour
# ---------------------------------------------------------------------------

_PLAN = {
    "meta": {"project": "toy"},
    "sections": [
        {"id": "S1", "beats": ["res:beat-a"],
         "nodes_in_order": ["res:beat-a", "def:x", "def:y"], "figures": []},
        {"id": "S2", "beats": ["res:beat-b"],
         "nodes_in_order": ["res:beat-b", "def:z"], "figures": ["fig:p"]},
    ],
    "appendices": [
        {"id": "A1", "beats": [], "nodes_in_order": ["def:x"], "figures": []},
    ],
}


def test_section_ref_move_affects_exactly_both_owner_sections():
    move = [{"kind": "set-projection", "node": "def:y",
             "value": {"section_ref": "res:beat-b"}}]
    assert prop.affected_sections(move, _PLAN) == {"S1": {"def:y"}, "S2": {"def:y"}}
    assert prop.changeset_classes(move, _PLAN) == {"S1": "expensive", "S2": "expensive"}


def test_edit_essence_marks_exactly_its_holders_expensive():
    recs = [{"kind": "edit-essence", "node": "def:x", "value": "new essence"}]
    assert prop.affected_sections(recs, _PLAN) == {"S1": {"def:x"}, "A1": {"def:x"}}
    assert prop.changeset_classes(recs, _PLAN) == {"S1": "expensive", "A1": "expensive"}


def test_reorder_only_change_is_cheap_and_substance_outranks_it():
    reorder = [{"kind": "set-spine", "node": "res:beat-a", "ord": 2}]
    assert prop.affected_sections(reorder, _PLAN) == {"S1": {"res:beat-a"}}
    assert prop.changeset_classes(reorder, _PLAN) == {"S1": "cheap"}
    both = reorder + [{"kind": "edit-essence", "node": "def:y", "value": "e"}]
    assert prop.changeset_classes(both, _PLAN)["S1"] == "expensive"
    # figure membership counts; auxiliary pass-throughs perturb nothing
    assert prop.affected_sections(
        [{"kind": "edit-essence", "node": "fig:p", "value": "e"}], _PLAN) == {"S2": {"fig:p"}}
    assert prop.affected_sections([{"kind": "data", "node": "def:x"}], _PLAN) == {}


def test_changeset_since_accepts_byte_and_id_marks(tmp_path):
    lp = tmp_path / "corpus_friction" / "subset-sum-itqde.jsonl"
    r1 = {"id": "RW-1", "kind": "add-node", "node": "def:a"}
    r2 = {"id": "RW-1", "kind": "edit-essence", "node": "def:a", "value": "e"}
    r3 = {"id": "RW-2", "kind": "set-spine", "node": "def:a", "ord": 1}
    ledger.append_jsonl(lp, r1)
    ledger.append_jsonl(lp, r2)
    mark = lp.stat().st_size
    ledger.append_jsonl(lp, r3)
    assert prop.changeset_since("subset-sum-itqde", mark, tmp_path) == [r3]
    assert prop.changeset_since("subset-sum-itqde", str(mark), tmp_path) == [r3]
    # an id mark cuts after the LAST record carrying it (live ids repeat)
    assert prop.changeset_since("subset-sum-itqde", "RW-1", tmp_path) == [r3]
    assert prop.changeset_since("subset-sum-itqde", None, tmp_path) == [r1, r2, r3]
    with pytest.raises(ValueError):
        prop.changeset_since("subset-sum-itqde", "RW-nope", tmp_path)
    with pytest.raises(ValueError):
        prop.changeset_since("no-such-project", 0, tmp_path)


# ---------------------------------------------------------------------------
# intake routing + the worklist DAG rules, synthetic
# ---------------------------------------------------------------------------

def test_intake_routing_ownership_and_resolved():
    net_nodes = {"def:x": {}, "def:z": {}}
    recs = [
        {"id": "F1", "kind": "missing-derivation", "node_id": "def:x",
         "anchor": {"section": "A1"}, "comment": "walk the derivation", "status": "open"},
        {"id": "F2", "kind": "imprecise", "node_id": "def:z", "anchor": {}, "text": "cite it"},
        {"id": "F3", "kind": "note", "node_id": "def:x", "comment": "just a note"},
        {"id": "F4", "kind": "missing-derivation", "node_id": "def:x", "status": "resolved"},
        {"id": "F5", "kind": "missing-node", "node_id": "def:new-idea",
         "anchor": {"section": "S2"}},
    ]
    items = prop.intake_items(recs, _PLAN, net_nodes)
    assert [w["kind"] for w in items] == ["derive", "prose", "mint"]
    d, p, m = items
    assert d["section"] == "A1"            # anchor disambiguates the multi-homed def:x
    assert d["goal"].startswith("missing-derivation: walk the derivation")
    assert d["source_feedback"] == "F1"
    assert p["section"] == "S2" and p["target"] == "def:z"   # schema field name accepted
    assert m["target"] == "def:new-idea"   # a mint's node does not exist yet, by definition
    assert (d["worker"], m["worker"], p["worker"]) == (
        "agent:derivation-builder", "agent:derivation-builder", "agent:prose-realiser")


def test_pour_repairs_idless_and_stamps_the_section_anchor(tmp_path):
    # bite-zero-B: the honest reader pour. A finding arriving id:null is REPAIRED
    # (assigned its deterministic finding_id — supersede mechanics need an id, so a
    # null-id finding is a permanent un-retirable zombie), and the section anchor is
    # STAMPED (from a leading N-token in `where`), so the pour can never deposit the
    # unroutable, section-less record the shakedown pour did.
    led = tmp_path / "feedback.jsonl"
    rec = ledger.pour_finding(
        led, {"reader": "R2", "kind": "referee-insufficient",
              "where": "N4-p10: the baseline juxtaposition", "issue": "x"},
        project="p")
    assert rec["id"] and rec["id"] == ledger.finding_id(rec)   # repaired, deterministic
    assert rec["section"] == "N4" and rec["anchor"]["section"] == "N4"
    # a finding with no locatable section is REFUSED, never poured section-less
    with pytest.raises(ValueError):
        ledger.pour_finding(
            led, {"reader": "R1", "kind": "cold-undefined-term",
                  "where": "Section Introduction, some prose", "issue": "y"})


def test_live_findings_stamps_a_deterministic_id_on_idless_records():
    # the read-side twin of the pour's id law: a legacy record poured id:null is
    # stamped its deterministic id at the live-view boundary, so it becomes
    # addressable (an anchored re-pour can then supersede it by that id) — and the
    # source record is never mutated.
    idless = {"reader": "R1", "kind": "cold-undefined-term",
              "where": "Introduction blah", "issue": "z"}
    src = dict(idless)
    (live,) = ledger.live_findings([idless])
    assert live["id"] == ledger.finding_id(idless)
    assert idless == src                                   # not mutated in place
    # a carried id wins over the derived one
    (kept,) = ledger.live_findings([{"id": "FB-keep", "kind": "note"}])
    assert kept["id"] == "FB-keep"


def test_worklist_never_emits_a_none_section_item_after_supersede():
    # the acceptance shape of the heal: an id-less, section-less original superseded
    # by its anchored twin yields ONE properly-sectioned item and NO None-section
    # item (the pour dishonesty that put `None` into minimum_dispatch).
    net_nodes: dict = {}
    original = {"reader": "R2", "kind": "referee-inherited-uncited",
                "where": "N3-p16 heat kernel", "issue": "uncited"}
    fid = ledger.finding_id(original)
    twin = {"id": "TWIN-0", "kind": "referee-inherited-uncited", "node_id": None,
            "anchor": {"section": "S2"}, "section": "S2", "where": "N3-p16 heat kernel"}
    resolution = {"id": "RES-0", "record": "resolution", "supersedes": fid,
                  "status": "resolved"}
    # the id-less original is stamped an id by the live view, then retired by RES-0
    live = ledger.live_findings([dict(original), twin, resolution])
    items = prop.intake_items(live, _PLAN, net_nodes)
    assert all(it["section"] is not None for it in items)
    assert [it["section"] for it in items if it["kind"] == "derive"] == ["S2"]


def test_intake_attaches_scope_and_owning_stage():
    # 2026-07-09: the intake door now carries the explicit owning-stage
    # (WORK_TO_LAYER) and the INSTRUCTION_SCOPES scope + a `local` flag.
    net_nodes = {"def:x": {}}
    recs = [
        {"id": "F1", "kind": "imprecise", "node_id": "def:x", "scope": "node", "text": "tighten"},
        {"id": "F2", "kind": "voice", "node_id": "def:x", "scope": "global", "text": "register"},
        {"id": "F3", "kind": "missing-derivation", "node_id": "def:x", "text": "derive"},  # unscoped
    ]
    a, b, c = prop.intake_items(recs, _PLAN, net_nodes)
    assert a["owning_stage"] == "prose" and a["scope"] == "node" and a["local"] is True
    assert b["owning_stage"] == "prose" and b["scope"] == "global" and b["local"] is False
    assert c["owning_stage"] == "research-state"      # missing-derivation -> derive -> research-state
    assert c["scope"] == "node" and c["local"] is True  # unscoped defaults to local


_NET = {
    "nodes": {"thm:t": {}, "def:q": {}, "sim:bank-a": {},
              "fig:F": {"projection": {"data_source": "sim:bank-a"}}},
    "edge_index": {"thm:t": ["thm:t", "def:q", "confirmed::def:q"], "fig:F": ["fig:F"]},
}


def _item(i, kind, target, section):
    return {"id": f"T-{i}-{kind}", "kind": kind, "project": "toy", "target": target,
            "section": section, "goal": f"{kind}: t", "blocked_by": [],
            "source_feedback": None, "worker": prop.WORKERS[kind]}


def test_worklist_blocks_prose_figures_and_depth1_ancestors():
    items = [
        _item(1, "derive", "def:q", "S1"),
        _item(2, "derive", "thm:t", "S3"),
        _item(3, "simulate", "sim:bank-a", "S2"),
        _item(4, "figure", "fig:F", "S2"),
    ]
    wl = prop.worklist(items, _NET)
    by_id = {w["id"]: w for w in wl}
    # a prose re-run synthesised for every substance-bearing section
    assert {w["section"] for w in wl if w["kind"] == "prose"} == {"S1", "S2", "S3"}
    # figure blocked by the simulate item that regenerates its data_source
    assert "T-3-simulate" in by_id["T-4-figure"]["blocked_by"]
    # S3's prose blocked by its own derive AND the depth-1 ancestor derive
    # (def:q is a derives-from referent of thm:t)
    assert {"T-1-derive", "T-2-derive"} <= set(by_id["WK-prose-S3"]["blocked_by"])
    # topological: every blocker precedes its dependant; no cycle breaks needed
    ids = {w["id"] for w in wl}
    seen: set[str] = set()
    for w in wl:
        assert set(w["blocked_by"]) & ids <= seen
        seen.add(w["id"])
    assert not any("cycle_dropped" in w for w in wl)
    # the caller's items are never mutated
    assert items[3]["blocked_by"] == []


# ---------------------------------------------------------------------------
# (c) purity — the operator is a pure read
# ---------------------------------------------------------------------------

def test_propagate_is_a_pure_read():
    proj = registry.resolve("subset-sum-itqde")
    plan_path = RR / proj.plan_path
    watched = [plan_path, RR / proj.ledger, RR / proj.feedback_ledger,
               plan_path.with_name("projection_plan.friction.jsonl"),
               plan_path.with_name("projection_plan.base.json")]
    before = {p: p.read_bytes() for p in watched if p.is_file()}
    assert len(before) >= 3
    rep = prop.propagate("subset-sum-itqde", since=0)   # exercise every leg
    assert rep["changeset"] > 0 and rep["worklist"] and rep["minimum_dispatch"]
    for p, b in before.items():
        assert p.read_bytes() == b, f"propagate wrote {p}"


def test_propagate_refuses_unknown_project():
    with pytest.raises(ValueError):
        prop.propagate("no-such-project")


# ---------------------------------------------------------------------------
# (d) the routing-completeness gate
# ---------------------------------------------------------------------------

def test_every_live_feedback_kind_is_routed():
    recs = ledger.read_jsonl(RR / registry.resolve("subset-sum-itqde").feedback_ledger)
    assert recs, "the live intake ledger is expected on disk"
    # only FINDING records carry a routable kind. Action/verdict records are
    # excluded EXACTLY as the intake door excludes them — by importing the door's
    # OWN set (one producer, no drift; the C5.7 regression was exactly this set
    # and its local copy diverging).
    _non_finding = prop.non_finding_record_kinds()
    finding_kinds = {r.get("kind") for r in recs if r.get("record") not in _non_finding}
    missing = sorted(finding_kinds - set(schema.KIND_TO_WORK))
    assert not missing, (
        f"feedback kinds without routing in schema.KIND_TO_WORK: {missing} — "
        "route them there before they reach the intake door")


def test_intake_refuses_an_unrouted_kind_by_name():
    bad = [{"id": "FB-x", "kind": "brand-new-kind", "node_id": "def:x", "status": "open"}]
    with pytest.raises(ValueError, match="brand-new-kind"):
        prop.intake_items(bad, _PLAN, {})


# the six banked desk-review kinds + the projection-intent record type: VERDICT-
# only (None) at the intake door, the unblock for the live subset-sum-itqde ledger
# whose author-desk-review row raised ValueError at propagate.intake_items (HEAD).
_DESK_REVIEW_KINDS = ("author-desk-review", "quadrature-conflation",
                      "novelty-overbroad", "access-model-unstated",
                      "symbol-collision-M", "contribution-rank-absent")


def test_desk_review_kinds_and_projection_intent_route_to_none():
    for kind in _DESK_REVIEW_KINDS + ("projection-intent",):
        assert kind in schema.KIND_TO_WORK, kind
        assert schema.KIND_TO_WORK[kind] is None, kind


def test_intake_no_longer_raises_on_the_desk_review_kinds():
    recs = [{"id": f"FB-{i}", "kind": k, "node_id": "def:x", "status": "open"}
            for i, k in enumerate(_DESK_REVIEW_KINDS)]
    # verdict-only kinds emit NO work item and NO raise (the door lets them through)
    assert prop.intake_items(recs, _PLAN, {}) == []


def test_live_subset_sum_propagate_no_longer_raises():
    # the live-bug regression: the banked author-desk-review row on the real
    # subset-sum-itqde ledger no longer raises at the intake door (pure read).
    rep = prop.propagate("subset-sum-itqde")
    assert rep["comments_routed"] >= 6         # the six desk-review kinds route as comments


def test_supersedes_retires_the_named_record():
    # the correction mechanism: a later record naming an earlier id retires it
    # (wrong kind at intake, e.g. the 28 voice comments banked as
    # missing-derivation) - append-only, and the correction propagates
    from laplace.pipeline import propagate, registry, schema

    plan = registry.resolve("subset-sum-itqde").read_plan()
    net_nodes = {"def:x": {"kind": "definition"}}
    recs = [
        {"id": "FB-A", "kind": "missing-derivation", "node_id": "def:x",
         "text": "mislabeled voice comment"},
        {"id": "FB-B", "kind": "voice", "node_id": "def:x",
         "text": "the corrected record", "supersedes": "FB-A"},
    ]
    items = propagate.intake_items(recs, plan, net_nodes)
    assert [i["source_feedback"] for i in items] == ["FB-B"]
    assert items[0]["kind"] == schema.KIND_TO_WORK["voice"]
