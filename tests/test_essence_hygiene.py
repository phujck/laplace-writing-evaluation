"""Essence hygiene migration (essence_hygiene_2026-07-08): the audit rule, the
applied L1 state, the append-only law, and the decomposed plan meta. These
assert the REAL repo state (the migration is applied), the same convention as
test_pipeline_briefs.py."""

from __future__ import annotations

import json
from pathlib import Path

from laplace.research import corpus_ingest as ci
from laplace.pipeline import migrate_essences as me
from laplace.pipeline import registry, schema

RR = Path(__file__).resolve().parents[1]
PROJECT = "subset-sum-itqde"
EVO = RR / "synthetics papers/subset-sum-itqde/manuscript/evolutions" / me.EVOLUTION_ID


def _banked() -> dict:
    return json.loads((EVO / "migration_plan.json").read_text(encoding="utf-8"))


def _flagged_rows() -> list[dict]:
    return [r for r in _banked()["rows"] if r["verdict"] == "flag"]


def test_audit_rule_flags_def_staircase():
    row = next(r for r in _flagged_rows() if r["node"] == "def:staircase")
    # the rule itself fires on the banked pre-migration essence
    hits = me.flag_hits(row["essence_now"])
    assert any(h.startswith("organising-meta") for h in hits), hits
    assert row["object_part"] and row["framing_part"]


def test_live_essences_carry_no_directives_post_apply():
    rows = me.audit(PROJECT, RR)
    assert [r["node"] for r in rows if r["verdict"] == "flag"] == []


def test_framing_slots_populated_for_migrated_nodes():
    net = ci.corpus_network(ci.resolve_corpus(RR, PROJECT), repo_root=RR, name=PROJECT)
    for r in _flagged_rows():
        fr = schema.proj_of(net["nodes"][r["node"]]).get("framing")
        assert fr == r["framing_part"], r["node"]


def test_l1_strictly_appended_from_the_freeze():
    proj = registry.resolve(PROJECT)
    live = proj.path(proj.ledger, RR).read_bytes()
    freezes = sorted((EVO / "_freeze").glob("pre_migration_*/subset-sum-itqde.jsonl"))
    assert freezes, "freeze snapshot missing"
    frozen = freezes[0].read_bytes()
    assert live.startswith(frozen)          # append-only: the past is a byte-prefix
    assert len(live) > len(frozen)          # and the migration did append


def test_plan_meta_is_typed_and_voice_channel_is_gone():
    meta = registry.resolve(PROJECT).read_plan(RR)["meta"]
    for field in schema.PLAN_META_TYPED:
        assert meta.get(field), field
    # Ratified plan-meta policy: kept exact on purpose. The ONE sanctioned mover of
    # these values is Leg 1's gated evolution apply (the migration/evolution stage);
    # if it legitimately re-ratifies the mode set or postures, update these pins to
    # the new ratified policy — do not let any other stage drift them.
    assert len(meta["workflow_modes"]) == 7
    assert set(meta["postures"]) == {"per-node-kind", "per-claim"}
    assert meta["gate_refs"] == me.GATE_REFS
    # the legacy contract wall stays nulled-not-deleted (set-meta merge law)...
    assert "builder_contract" in meta and meta["builder_contract"] is None
    # ...but the voice channel is REMOVED outright (2026-07-09 rebuild): voice
    # rides only the versioned profile at the final leg, never plan meta.
    assert "voice_refs" not in meta
    assert "voice" not in meta


def test_framing_rides_the_narrative_dispatch_not_prose():
    # framing's consumer moved with the rebuild: it shapes PARAGRAPH PLANS
    # (the narrative worker's OBJECT), and the prose packet never carries it.
    from laplace.pipeline import dispatch
    plan = registry.resolve(PROJECT).read_plan(RR)
    owner = next((s["id"] for s in schema.plan_sections(plan)
                  if "def:staircase" in schema.section_nodes(s)), None)
    assert owner, "def:staircase is planned somewhere"
    d = dispatch.compile_dispatch(owner, "probe", "narrative", PROJECT)
    if "error" in d:
        import pytest
        pytest.skip(d["error"])             # contracts not yet authored
    assert "Framing (positioning guidance" in d["prompt"]
    assert "Position the staircase" in d["prompt"]
