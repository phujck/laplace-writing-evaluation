"""R10 Restart — plumbing tests (hermetic, no live LLM).

builder != judge: these exercise the WIRING (PDF binding + text extraction precedence,
the two packets, the seal INVERSION between phases, the verb law, the bank shapes, the
roster registration), never the read QUALITY (that needs the two real sealed reads at
candidate-lock + the intended object + Gerard). The LLM phases are STUBBED — hand-written
blind/compare replies drive make_reader_report + bank without a model, exactly as A1's
fixture drove the sealed reader wiring.
"""
from pathlib import Path

import json

import pytest

from laplace.pipeline import adjudicate, ledger
from laplace.pipeline import readers as R
from laplace.pipeline.readers import restart_reader as RR


# --- roster registration: R10 is a full, single-owned member -----------------

def test_roster_invariants_green_with_r10():
    # single ownership (now 14 hard-failures) and kind partition both hold with R10.
    so = R.verify_single_ownership()
    assert so["ok"], so["violations"]
    assert so["n_failures"] == 14
    kp = R.verify_kind_partition()
    assert kp["ok"], kp["violations"]
    r10 = R.READERS["R10"]
    assert r10.organ == "sealed_subagent"
    assert r10.dimension == "artefact_integrity"     # the object-survives-as-itself axis
    assert r10.hardness == "hard"
    assert r10.panel_label == "restart_reader"
    assert r10.cadence.read == "candidate_lock" and r10.cadence.floor is None
    assert r10.owns == ("identity-mismatch",)
    assert set(r10.owned_kinds) == {"identity-mismatch", "emphasis-mismatch",
                                    "conclusion-overreach", "exclusion-violated"}


def test_r10_kinds_are_verdict_only_in_the_manifest():
    rows = {r["kind"]: r for r in R.finding_kinds_manifest() if r["reader"] == "R10"}
    assert set(rows) == {"identity-mismatch", "emphasis-mismatch",
                         "conclusion-overreach", "exclusion-violated"}
    for row in rows.values():
        assert row["work_kind"] is None                 # verdict-only: no per-node work
        assert row["owning_stage"] is None


def test_r10_kinds_wire_to_none_in_the_schema():
    from laplace.pipeline import schema
    schema.register_component_kinds()                    # idempotent
    for k in ("identity-mismatch", "emphasis-mismatch",
              "conclusion-overreach", "exclusion-violated"):
        assert schema.KIND_TO_WORK[k] is None            # reaches the intake door, routed to None


# --- extract_artefact_text: discover-final-pdf precedence + honest failure ----

def _finalize(mdir: Path, pdf_name: str):
    rel = mdir / "release"
    rel.mkdir(parents=True, exist_ok=True)
    (rel / "finalize.json").write_text(json.dumps({"pdf_path": pdf_name}))


def test_extract_binds_through_discover_final_pdf(tmp_path, monkeypatch):
    # a finalize.json names the canonical PDF; a decoy main.pdf must NOT be chosen.
    mdir = tmp_path / "manuscript"
    mdir.mkdir()
    (mdir / "the-object.pdf").write_bytes(b"%PDF-1.5 canonical")
    (mdir / "main.pdf").write_bytes(b"%PDF-1.5 decoy")
    _finalize(mdir, "the-object.pdf")

    seen = {}

    def fake_resolve_uv():
        return "uv"                                      # pretend uv exists

    def fake_uv(pdf_path, uv_bin, timeout):
        seen["pdf"] = Path(pdf_path).name
        return "PRIMARY CONTRIBUTION recovered from the finished pages."

    monkeypatch.setattr(RR, "_resolve_uv", fake_resolve_uv)
    monkeypatch.setattr(RR, "_extract_via_uv", fake_uv)
    txt = RR.extract_artefact_text(mdir)
    assert "recovered from the finished pages" in txt
    assert seen["pdf"] == "the-object.pdf"               # bound via _discover_final_pdf, not main.pdf


def test_extract_errors_honestly_with_no_extractor(tmp_path, monkeypatch):
    mdir = tmp_path / "manuscript"
    mdir.mkdir()
    (mdir / "main.pdf").write_bytes(b"%PDF-1.5")
    monkeypatch.setattr(RR, "_resolve_uv", lambda: None)          # no uv
    monkeypatch.setattr(RR, "_extract_via_poppler", lambda p, t: None)  # no poppler
    with pytest.raises(RuntimeError) as ei:
        RR.extract_artefact_text(mdir)
    msg = str(ei.value)
    assert "uv not resolvable" in msg                    # names the uv failure
    assert "poppler" in msg                              # and the poppler failure — both


def test_extract_refuses_when_no_pdf_to_bind(tmp_path):
    mdir = tmp_path / "manuscript"
    mdir.mkdir()
    with pytest.raises(RuntimeError) as ei:
        RR.extract_artefact_text(mdir)
    assert "no final PDF to bind" in str(ei.value)


def test_extract_falls_back_to_poppler(tmp_path, monkeypatch):
    mdir = tmp_path / "manuscript"
    mdir.mkdir()
    (mdir / "main.pdf").write_bytes(b"%PDF-1.5")
    monkeypatch.setattr(RR, "_resolve_uv", lambda: None)          # uv unavailable
    monkeypatch.setattr(RR, "_extract_via_poppler",
                        lambda p, t: "poppler-extracted text of the whole artefact")
    txt = RR.extract_artefact_text(mdir)
    assert "poppler-extracted" in txt


# --- blind_packet: NO meta/plan/intent; compare_packet: the intended object IN -

_INTENDED = {
    "contribution_rank": ["the exact-PDF revalidation gate", "the staged pipeline"],
    "thesis": "an offline convergence loop that certifies the finished object",
    "exclusions": ["no cloud dependency", "no benchmark leaderboard claim"],
}


def test_blind_packet_hides_the_intended_object():
    text = "The paper reports a convergence loop and measures its lock behaviour."
    p = RR.blind_packet(text)
    # the seal HOLDS at phase 1 — the blind reader is denied every construction sentinel
    assert p["seal_check"]["ok"], p["seal_check"]
    assert p["phase"] == "blind"
    # none of the intended-object keys/values leak into the blind packet
    blob = json.dumps(p)
    for key in _INTENDED:
        assert key not in blob
    for val in ("exact-PDF revalidation gate", "no cloud dependency",
                "offline convergence loop that certifies"):
        assert val not in blob
    # the recovery questionnaire IS present
    assert "RECOVERY QUESTIONNAIRE" in p["prompt"]
    assert "PRIMARY CONTRIBUTION" in p["prompt"]


def test_compare_packet_carries_the_intended_object_and_inverts_the_seal():
    blind = {"contribution": "a convergence loop", "conclusion_claims": "it locks",
             "weighting": ["Methods: heavy"], "evidence": "one run", "excluded": []}
    p = RR.compare_packet(blind, _INTENDED)
    assert p["phase"] == "compare"
    # the seal is INVERTED: the check proves the intended object is PRESENT (ok=True)
    assert p["seal_check"]["ok"] is True
    assert p["seal_check"]["inverted"] is True
    assert p["seal_check"]["intended_present"] is True
    # the intended object's keys/values ARE in the compare packet (that is the point)
    blob = json.dumps(p)
    assert "contribution_rank" in blob
    assert "exact-PDF revalidation gate" in blob
    assert "no cloud dependency" in blob
    # the blind recovery is also present so the reader can set them side by side
    assert "a convergence loop" in blob


def test_compare_seal_inverted_flags_a_missing_intended_object():
    p = RR.compare_packet({"contribution": "x"}, {})     # no intended object supplied
    assert p["seal_check"]["ok"] is False                # the inverse defect: nothing to compare
    assert p["seal_check"]["intended_present"] is False


# --- the verb law: the table is surjective onto PROJECTION_VERBS --------------

def test_verb_table_covers_every_projection_verb():
    covered = set(RR.VERB_FOR_MISMATCH.values())
    assert covered == set(adjudicate.PROJECTION_VERBS)   # every plan-altitude verb reachable
    # every verb in the table is a real PROJECTION_VERB (no stray)
    for verb in covered:
        assert verb in adjudicate.PROJECTION_VERBS
    # the directive's named anchors: contribution=RESPINE, wholesale identity=RESTART
    assert RR.VERB_FOR_MISMATCH["contribution"] == "RESPINE"
    assert RR.VERB_FOR_MISMATCH["identity"] == "RESTART"
    assert RR.VERB_FOR_MISMATCH["emphasis"] == "DEMOTE"
    # every mismatch rule names an R10-owned kind
    for rule in RR.MISMATCH_TABLE.values():
        assert rule.kind in R.READERS["R10"].owned_kinds
        assert rule.object_kind in ("meta", "section")


# --- bank: one reader-report + a DRAFT projection-intent per mismatch ---------

def _synthetic_comparison():
    return [
        {"type": "contribution", "object_key": "contribution", "note": "spine points at the wrong result"},
        {"type": "emphasis", "object_key": "N4", "note": "Methods overweighted vs its rank"},
        {"type": "overreach", "object_key": "N7", "note": "the conclusion overclaims"},
        {"type": "exclusion", "object_key": "N5", "note": "an excluded topic is present"},
        {"type": "identity", "object_key": "genre", "note": "a survey, not the intended result paper"},
    ]


def test_bank_writes_report_and_draft_intents_with_correct_verbs(tmp_path):
    fp = tmp_path / "feedback.jsonl"
    blind = {"contribution": "a survey of methods"}
    out = RR.bank(tmp_path, blind, _synthetic_comparison(),
                  project="p", round=2, feedback_path=fp)
    recs = ledger.read_jsonl(fp)

    # exactly one reader-report, R10, both phases banked
    reports = [r for r in recs if r.get("record") == "reader-report"]
    assert len(reports) == 1
    rep = reports[0]
    assert rep["reader"] == "R10"
    assert set(rep["phases"]) == {"blind", "compare"}
    assert rep["clean"] is False and len(rep["findings"]) == 5
    assert rep["dimension"] == "artefact_integrity"

    # one DRAFT projection-intent per mismatch, verbs from the table, draft-only law
    intents = [r for r in recs if r.get("record") == adjudicate.PROJECTION_INTENT]
    assert len(intents) == 5
    for it in intents:
        assert it["status"] == "open"                    # queued, never executed
        assert it["scope"] == "plan"
        assert it["source"] == "R10:restart-reader"
        assert it["verb"] in adjudicate.PROJECTION_VERBS
    verbs = {it["object"].get("key") or it["object"].get("sid"): it["verb"] for it in intents}
    # the mismatch types mapped to their table verbs
    assert verbs["contribution"] == "RESPINE"
    assert verbs["N4"] == "DEMOTE"
    assert verbs["N7"] == "CUT"                          # overreach
    assert verbs["genre"] == "RESTART"                   # wholesale identity
    # object kinds: contribution/identity → meta (key), section mismatches → section (sid)
    by_verb = {it["verb"]: it["object"]["kind"] for it in intents}
    assert by_verb["RESPINE"] == "meta"
    assert by_verb["DEMOTE"] == "section"

    # every intent targets a real finding id carried in the report
    report_ids = {f["id"] for f in rep["findings"]}
    for it in intents:
        assert it["target"] in report_ids
    assert out["n_findings"] == 5 and out["clean"] is False


def test_bank_clean_when_the_recovered_paper_is_the_intended_paper(tmp_path):
    fp = tmp_path / "feedback.jsonl"
    out = RR.bank(tmp_path, {"contribution": "the intended result"}, [],
                  feedback_path=fp)
    recs = ledger.read_jsonl(fp)
    reports = [r for r in recs if r.get("record") == "reader-report"]
    assert len(reports) == 1 and reports[0]["clean"] is True
    # no mismatches → no projection-intents
    assert [r for r in recs if r.get("record") == adjudicate.PROJECTION_INTENT] == []
    assert out["clean"] is True and out["n_findings"] == 0


# =============================================================================
# C5.1a — fail-closed R10 parsing + compare seal + truncation gate
# =============================================================================

# --- LEVER 1 (PARSE): a wrong-shape comparison RAISES, never reads as clean ----

@pytest.mark.parametrize("bad", [
    {"contribution": "x", "evidence": "y"},   # a blind-report-shaped dict, wrong here
    {"foo": 1},                               # a dict with none of the recognised keys
    "no mismatches, all good",                # a bare string (well-formed but not a list)
    None,                                     # what _coerce_json returns for garbage text
    42,                                        # a scalar
    ["identity", "contribution"],             # a JSON list of NON-dicts
    {"mismatches": "not-a-list"},             # recognised key, wrong-typed value
])
def test_wrong_shape_comparison_raises_never_clean(bad):
    """A well-formed-JSON-but-wrong-shape comparison must RAISE (the fail-loud extractor
    idiom) rather than let make_reader_report certify a clean whole-artefact verdict —
    this is the leg verdict_io's transport gate does not close."""
    with pytest.raises(ValueError):
        RR.make_reader_report({"contribution": "recovered"}, bad)


def test_bank_wrong_shape_raises_and_banks_nothing(tmp_path):
    """The raise propagates through bank: a wrong-shape reply certifies nothing and
    leaves no reader-report on the ledger."""
    fp = tmp_path / "feedback.jsonl"
    with pytest.raises(ValueError):
        RR.bank(tmp_path, {"contribution": "x"}, {"contribution": "x"}, feedback_path=fp)
    assert not fp.exists()                                  # nothing certified, nothing banked


def test_genuinely_empty_list_is_clean_not_a_raise():
    """The distinguished case: a genuinely-empty mismatch list IS clean (recognised
    shape), never confused with an unparseable reply. Both the bare ``[]`` and the
    ``{"mismatches": []}`` carrier read clean."""
    for empty in ([], {"mismatches": []}, {"findings": []}, {"verdict": []}):
        rep = RR.make_reader_report({"contribution": "the intended result"}, empty)
        assert rep["clean"] is True and rep["findings"] == []


# --- LEVER 2 (SEAL): the intended object needs the hierarchy, not any non-empty --

def test_seal_requires_contribution_rank_and_exclusions():
    """``compare_seal_inverted`` seals ok=True only when the intended object carries the
    hierarchy: contribution_rank AND the exclusions carrier. Any bare non-empty dict no
    longer seals."""
    full = RR.compare_packet({"contribution": "x"}, _INTENDED)  # rank + exclusions present
    assert full["seal_check"]["ok"] is True

    # missing exclusions → not sealed
    no_excl = RR.compare_packet({"contribution": "x"},
                                {"contribution_rank": ["the primary claim"]})
    assert no_excl["seal_check"]["ok"] is False
    assert "exclusions" in no_excl["seal_check"]["note"]

    # missing contribution_rank → not sealed
    no_rank = RR.compare_packet({"contribution": "x"},
                                {"exclusions": ["no cloud claim"]})
    assert no_rank["seal_check"]["ok"] is False
    assert "contribution_rank" in no_rank["seal_check"]["note"]

    # a bare non-empty dict (neither field) → not sealed (the old bool(intended) leg)
    bare = RR.compare_packet({"contribution": "x"}, {"thesis": "some thesis"})
    assert bare["seal_check"]["ok"] is False


def test_seal_empty_exclusions_carrier_still_seals():
    """The exclusions CARRIER need only be declared — a paper may exclude nothing. An
    empty ``exclusions`` list with a real rank still seals (present, not truthy)."""
    p = RR.compare_packet({"contribution": "x"},
                          {"contribution_rank": ["the primary claim"], "exclusions": []})
    assert p["seal_check"]["ok"] is True
    assert p["seal_check"]["exclusions_form"] == "meta.exclusions"


# --- LEVER 2b (SEAL): the ROLE form of the exclusions statement ----------------
# His ruling PV-20260820T223004Z. The exclusions statement has two authorings; the seal
# reads both, exactly, and refuses when neither is present.

#: the live SSG plan's rank, in the shape it is actually authored (the 2026-07-22 respine
#: envelope applied TWICE) — rank 4 carries the exclusion in its ROLE, and the plan has no
#: ``meta.exclusions`` key at all. This is the case the seal had been failing on.
_SSG_RANK = {"value": {"value": [
    {"rank": 1, "claim": "the reusable Gaussian spectral surface and its finite-record "
                         "envelope", "role": "primary"},
    {"rank": 2, "claim": "subset-sum as validation of the surface", "role": "validation"},
    {"rank": 3, "claim": "the fingerprint/decoder as a benchmark application",
     "role": "benchmark-application"},
    {"rank": 4, "claim": "the planted hardness construction",
     "role": "exploratory-excluded"},
]}}


def test_seal_accepts_the_role_form_of_exclusions():
    """CASE 1 — a rank entry whose role is exclusion-class IS an exclusions statement.
    The live SSG meta (no ``exclusions`` key, rank 4 role ``exploratory-excluded``, the
    respine envelope doubled) seals, and the check names which form carried it."""
    sc = RR.compare_packet({"contribution": "x"},
                           {"contribution_rank": _SSG_RANK})["seal_check"]
    assert sc["ok"] is True
    assert sc["exclusions_form"] == "contribution_rank.role"
    assert sc["exclusion_roles"] == ["exploratory-excluded"]
    assert "exploratory-excluded" in sc["note"]


def test_seal_still_accepts_the_explicit_exclusions_key():
    """CASE 2 — the KEY form keeps working, unchanged, including when the rank carries
    no roles at all (a plain list of claim strings)."""
    sc = RR.compare_packet({"contribution": "x"}, _INTENDED)["seal_check"]
    assert sc["ok"] is True
    assert sc["exclusions_form"] == "meta.exclusions"
    assert sc["exclusion_roles"] == []

    # both forms at once are reported as both, and still seal.
    both = RR.compare_packet(
        {"contribution": "x"},
        {"contribution_rank": _SSG_RANK, "exclusions": ["no cloud claim"]})["seal_check"]
    assert both["ok"] is True and both["exclusions_form"] == "both"


def test_seal_fails_when_neither_exclusions_form_is_present():
    """CASE 3 — NEITHER form present still FAILS. A rank whose every role is a
    contribution role states no exclusion, and the refusal names both remedies."""
    no_excl_roles = {"contribution_rank": {"value": [
        {"rank": 1, "claim": "the primary claim", "role": "primary"},
        {"rank": 2, "claim": "the validating claim", "role": "validation"},
    ]}}
    sc = RR.compare_packet({"contribution": "x"}, no_excl_roles)["seal_check"]
    assert sc["ok"] is False
    assert sc["exclusions_form"] == "none"
    assert sc["exclusion_roles"] == []
    assert "meta.exclusions" in sc["note"] and "exploratory-excluded" in sc["note"]

    # and a plain claim-string rank (no role slot at all) still fails.
    plain = RR.compare_packet({"contribution": "x"},
                              {"contribution_rank": ["the primary claim"]})["seal_check"]
    assert plain["ok"] is False and plain["exclusions_form"] == "none"


def test_role_match_is_exact_against_the_closed_set_never_a_substring():
    """FAIL-CLOSED. The role read is exact membership in :data:`RR.EXCLUSION_ROLES` after
    strip + casefold, and nothing else — a role that merely CONTAINS an exclusion word
    does not seal. Case and surrounding whitespace are the only normalisation."""
    def _roles(role):
        return RR.rank_exclusion_roles([{"rank": 1, "claim": "c", "role": role}])

    for exact in sorted(RR.EXCLUSION_ROLES):
        assert _roles(exact) == [exact]
    assert _roles("  Exploratory-Excluded  ") == ["Exploratory-Excluded"]   # strip+fold
    for near in ("excluded-by-the-author", "exploratory-but-kept", "not-excluded",
                 "exclude", "exploration", "", "primary", None):
        assert _roles(near) == [], near

    # an entry with no claim text carries no seal (the renderer drops it too), and a
    # non-dict entry has no role slot at all.
    assert RR.rank_exclusion_roles([{"rank": 1, "claim": "  ",
                                     "role": "exploratory-excluded"}]) == []
    assert RR.rank_exclusion_roles(["exploratory-excluded"]) == []
    # an unreadable rank states no exclusions rather than raising.
    assert RR.rank_exclusion_roles(None) == []
    assert RR.rank_exclusion_roles({"value": "not a list"}) == []


def test_exclusion_roles_diverge_from_the_renderer_only_in_the_safe_direction():
    """The seal is STRICTER than ``schema.contribution_rank_lines`` (which splits on a
    substring test), never looser: every role this module treats as exclusion-class must
    also land on the renderer's EXCLUDED line. So the seal can refuse a rank the board
    would show as excluded, but can never seal one the board would show as primary."""
    from laplace.pipeline import schema

    for role in sorted(RR.EXCLUSION_ROLES):
        primary, excluded = schema.contribution_rank_lines(
            [{"rank": 1, "claim": "the claim", "role": role}])
        assert primary == [] and len(excluded) == 1, role


def test_seal_flips_true_on_the_live_ssg_plan():
    """The live plan on disk, not a fixture: ``synthetics papers/subset-sum-itqde`` seals
    under the role form. Skipped (never silently passed) if the plan is not present."""
    plan_path = (Path(__file__).resolve().parents[1] /
                 "synthetics papers/subset-sum-itqde/manuscript/projection_plan.json")
    if not plan_path.is_file():
        pytest.skip(f"live SSG plan absent at {plan_path}")
    meta = json.loads(plan_path.read_text(encoding="utf-8")).get("meta") or {}
    assert "exclusions" not in meta          # the key form is genuinely absent here
    sc = RR.compare_packet({"contribution": "x"}, meta)["seal_check"]
    assert sc["ok"] is True
    assert sc["exclusions_form"] == "contribution_rank.role"
    assert sc["exclusion_roles"] == ["exploratory-excluded"]


# --- LEVER 3 (TRUNCATION): a truncated blind read forbids a clean verdict -------

def test_truncated_blind_read_forbids_a_clean_verdict():
    """A truncated blind read never met the WHOLE artefact, so it may not certify clean
    even with zero mismatches — the verdict reads 'truncated', not 'clean'."""
    rep = RR.make_reader_report({"contribution": "recovered"}, [], truncated=True)
    assert rep["clean"] is False                            # forbidden despite zero mismatches
    assert rep["truncated"] is True
    assert rep["provenance"]["verdict"] == "truncated"


def test_bank_truncated_read_is_not_clean(tmp_path):
    """The truncation gate rides through bank: a truncated read banks a non-clean
    verdict even with an empty mismatch list."""
    fp = tmp_path / "feedback.jsonl"
    out = RR.bank(tmp_path, {"contribution": "recovered"}, [],
                  truncated=True, feedback_path=fp)
    assert out["clean"] is False and out["n_findings"] == 0
    rep = [r for r in ledger.read_jsonl(fp) if r.get("record") == "reader-report"][0]
    assert rep["clean"] is False and rep["truncated"] is True


def test_the_blind_packet_truncated_flag_is_the_gate_input():
    """The gate's input is the ``blind_packet`` ``truncated`` flag (:253): a payload over
    the cap sets it, and that flag is exactly what forbids the clean whole-artefact
    verdict when threaded into make_reader_report."""
    over_cap = "z" * 10
    pkt = RR.blind_packet(over_cap, max_input_chars=4)
    assert pkt["truncated"] is True
    rep = RR.make_reader_report({"contribution": "recovered"}, [],
                                truncated=pkt["truncated"])
    assert rep["clean"] is False


# --- HAPPY PATH still works: findings from a well-formed list; empty → clean -----

def test_happy_path_well_formed_mismatch_list_still_yields_findings():
    """A well-formed mismatch list still produces findings (the parse hardening does not
    strangle the real path), and a well-formed empty list with an untruncated read still
    certifies clean."""
    rep = RR.make_reader_report({"contribution": "a survey"}, _synthetic_comparison())
    assert rep["clean"] is False and len(rep["findings"]) == 5
    assert rep["provenance"]["verdict"] == "identity-mismatch"

    clean = RR.make_reader_report({"contribution": "the intended result"}, [],
                                  truncated=False)
    assert clean["clean"] is True and clean["findings"] == []
    assert clean["provenance"]["verdict"] == "clean"


# =============================================================================
# C3.4 — target resolution against the LIVE plan
# =============================================================================
#
# The plan rides into make_reader_report/bank (additive, default None = HEAD). Each
# mismatch's object_key resolves against plan_sections sids + plan.meta keys; a resolved
# key mints the projection-intent as today, an unresolved key is FLAGGED on the finding
# and mints NOTHING (the finding still banks — the signal kept, the actuator refused).

_PLAN = {
    "sections": [{"id": "S1", "nodes_in_order": ["res:a"]},
                 {"id": "S2", "nodes_in_order": ["res:b"]}],
    "appendices": [{"id": "APP1", "nodes_in_order": ["res:c"]}],
    "meta": {"contribution_rank": ["the primary claim"], "thesis": "one true thesis"},
}


def test_plan_none_is_byte_compatible_with_head(tmp_path):
    """The additive default proven: ``plan=None`` stamps NO ``resolution`` on any finding
    and mints every intent exactly as HEAD did — the pre-C3.4 behaviour, unchanged."""
    fp = tmp_path / "feedback.jsonl"
    out = RR.bank(tmp_path, {"contribution": "a survey"}, _synthetic_comparison(),
                  project="p", round=2, feedback_path=fp)               # plan omitted
    for f in out["report"]["findings"]:
        assert "resolution" not in f                    # no stamp when the plan is absent
    intents = [r for r in ledger.read_jsonl(fp)
               if r.get("record") == adjudicate.PROJECTION_INTENT]
    assert len(intents) == 5                            # every mismatch still mints, as today
    assert len(out["intents"]) == 5

    # and make_reader_report(plan=None) is identical to the no-kwarg call
    a = RR.make_reader_report({"contribution": "x"}, _synthetic_comparison())
    b = RR.make_reader_report({"contribution": "x"}, _synthetic_comparison(), plan=None,
                              ts=a["ts"], rec_id=a["id"])
    assert a == b


def test_resolved_section_sid_mints_intent_with_object_sid(tmp_path):
    """A mismatch whose ``object_key`` names a real section id resolves; the intent it
    mints carries ``object.sid`` exactly as today (section-kind actuator)."""
    fp = tmp_path / "feedback.jsonl"
    comparison = [{"type": "emphasis", "object_key": "S2",
                   "note": "S2 overweighted vs its rank"}]
    out = RR.bank(tmp_path, {"contribution": "x"}, comparison,
                  feedback_path=fp, plan=_PLAN)
    f = out["report"]["findings"][0]
    assert f["resolution"] == "resolved"
    intents = [r for r in ledger.read_jsonl(fp)
               if r.get("record") == adjudicate.PROJECTION_INTENT]
    assert len(intents) == 1 and len(out["intents"]) == 1
    obj = intents[0]["object"]
    assert obj["kind"] == "section" and obj["sid"] == "S2"
    # an appendix id resolves too (plan_sections includes appendices)
    comparison2 = [{"type": "order", "object_key": "APP1", "note": "misordered"}]
    out2 = RR.bank(tmp_path, {"contribution": "x"}, comparison2,
                   feedback_path=tmp_path / "f2.jsonl", plan=_PLAN)
    assert out2["report"]["findings"][0]["resolution"] == "resolved"
    assert len(out2["intents"]) == 1


def test_resolved_meta_key_mints_intent_with_object_key(tmp_path):
    """A mismatch whose ``object_key`` names a real ``plan.meta`` key resolves; the intent
    carries ``object.key`` (meta-kind actuator)."""
    fp = tmp_path / "feedback.jsonl"
    comparison = [{"type": "contribution", "object_key": "contribution_rank",
                   "note": "spine points at the wrong result"}]
    out = RR.bank(tmp_path, {"contribution": "x"}, comparison,
                  feedback_path=fp, plan=_PLAN)
    f = out["report"]["findings"][0]
    assert f["resolution"] == "resolved"
    intents = [r for r in ledger.read_jsonl(fp)
               if r.get("record") == adjudicate.PROJECTION_INTENT]
    assert len(intents) == 1 and len(out["intents"]) == 1
    obj = intents[0]["object"]
    assert obj["kind"] == "meta" and obj["key"] == "contribution_rank"
    assert intents[0]["verb"] == "RESPINE"


def test_unresolved_key_is_flagged_and_mints_no_intent(tmp_path):
    """An ``object_key`` in NEITHER namespace is flagged ``resolution:"unresolved"`` and
    mints NO intent — the finding still banks (the signal is kept, the actuator refused)."""
    fp = tmp_path / "feedback.jsonl"
    comparison = [{"type": "emphasis", "object_key": "ghost-section",
                   "note": "names a section the plan does not carry"}]
    out = RR.bank(tmp_path, {"contribution": "x"}, comparison,
                  feedback_path=fp, plan=_PLAN)
    f = out["report"]["findings"][0]
    assert f["resolution"] == "unresolved"
    # the finding IS banked in the reader-report
    recs = ledger.read_jsonl(fp)
    rep = [r for r in recs if r.get("record") == "reader-report"][0]
    assert len(rep["findings"]) == 1
    assert rep["findings"][0]["resolution"] == "unresolved"
    # but NO projection-intent was minted for it
    assert [r for r in recs if r.get("record") == adjudicate.PROJECTION_INTENT] == []
    assert out["intents"] == [] and out["n_findings"] == 1


def test_the_real_ssg_targets_each_decided(tmp_path):
    """The named SSG targets: ``contribution_rank`` IS a real meta key (resolves, mints);
    ``weighting``/``excluded``/``artefact`` are not carried by this plan (unresolved, no
    intent). One report banks all four findings; only the resolved one mints an actuator."""
    fp = tmp_path / "feedback.jsonl"
    comparison = [
        {"type": "contribution", "object_key": "contribution_rank", "note": "wrong spine"},
        {"type": "emphasis", "object_key": "weighting", "note": "weighting off"},
        {"type": "exclusion", "object_key": "excluded", "note": "excluded present"},
        {"type": "identity", "object_key": "artefact", "note": "a different object"},
    ]
    out = RR.bank(tmp_path, {"contribution": "x"}, comparison,
                  feedback_path=fp, plan=_PLAN)
    res = {f["where"]: f["resolution"] for f in out["report"]["findings"]}
    assert res == {"contribution_rank": "resolved", "weighting": "unresolved",
                   "excluded": "unresolved", "artefact": "unresolved"}
    intents = [r for r in ledger.read_jsonl(fp)
               if r.get("record") == adjudicate.PROJECTION_INTENT]
    assert len(intents) == 1                            # only contribution_rank minted
    assert intents[0]["object"] == {"kind": "meta", "key": "contribution_rank"}
    assert out["n_findings"] == 4                       # all four signals kept

    # a plan that DOES carry the others — EACH IN ITS OWN NAMESPACE — resolves them:
    # contribution(meta) + identity(meta) land in plan.meta; emphasis(section) +
    # exclusion(section) land in the section ids. (Placing a section-kind target in meta,
    # or vice versa, must NOT resolve — that cross-namespace confusion is the C3.4 defect.)
    plan2 = dict(_PLAN, meta={"contribution_rank": ["c"], "artefact": {}})
    plan2 = {**plan2, "sections": _PLAN["sections"] + [{"id": "excluded"}, {"id": "weighting"}]}
    out2 = RR.bank(tmp_path, {"contribution": "x"}, comparison,
                   feedback_path=tmp_path / "f2.jsonl", plan=plan2)
    res2 = {f["where"]: f["resolution"] for f in out2["report"]["findings"]}
    assert all(v == "resolved" for v in res2.values()), res2
    assert len(out2["intents"]) == 4                    # all addressable now


# --- C3.4 fail-closed: resolution is NAMESPACE-SCOPED by the mismatch type's object_kind


def test_meta_mismatch_naming_a_real_section_id_is_unresolved(tmp_path):
    """The exact defect vector: a ``contribution`` mismatch (object_kind=meta) whose
    ``object_key`` names a real SECTION id (``S1``) must NOT resolve via the section
    namespace — the intent it would mint is a meta-kind actuator pointing at a section.
    Cross-namespace => ``unresolved`` + ZERO intents (the signal banks, the actuator is
    refused — the same fail-closed refusal proven for unknown keys)."""
    fp = tmp_path / "feedback.jsonl"
    comparison = [{"type": "contribution", "object_key": "S1",
                   "note": "S1 is a real section id, but this is a meta-kind mismatch"}]
    out = RR.bank(tmp_path, {"contribution": "x"}, comparison,
                  feedback_path=fp, plan=_PLAN)
    f = out["report"]["findings"][0]
    assert f["resolution"] == "unresolved"              # NOT resolved via the wrong namespace
    recs = ledger.read_jsonl(fp)
    rep = [r for r in recs if r.get("record") == "reader-report"][0]
    assert len(rep["findings"]) == 1                    # the finding still banks
    assert rep["findings"][0]["resolution"] == "unresolved"
    # NO meta-kind intent minted pointing at a section
    assert [r for r in recs if r.get("record") == adjudicate.PROJECTION_INTENT] == []
    assert out["intents"] == [] and out["n_findings"] == 1


def test_section_mismatch_naming_a_real_meta_key_is_unresolved(tmp_path):
    """The mirror vector: an ``emphasis`` mismatch (object_kind=section) whose
    ``object_key`` names a real ``plan.meta`` key (``contribution_rank``) must NOT resolve
    via the meta namespace. Cross-namespace => ``unresolved`` + zero intents."""
    fp = tmp_path / "feedback.jsonl"
    comparison = [{"type": "emphasis", "object_key": "contribution_rank",
                   "note": "a real meta key, but this is a section-kind mismatch"}]
    out = RR.bank(tmp_path, {"contribution": "x"}, comparison,
                  feedback_path=fp, plan=_PLAN)
    f = out["report"]["findings"][0]
    assert f["resolution"] == "unresolved"
    recs = ledger.read_jsonl(fp)
    assert [r for r in recs if r.get("record") == adjudicate.PROJECTION_INTENT] == []
    assert out["intents"] == [] and out["n_findings"] == 1


def test_correct_namespace_still_mints_after_the_scope_fix(tmp_path):
    """Guard the non-regression: a section-kind mismatch naming a real section id and a
    meta-kind mismatch naming a real meta key BOTH still resolve and mint exactly as
    before — the scope fix narrows only the cross-namespace leg."""
    fp = tmp_path / "feedback.jsonl"
    comparison = [
        {"type": "emphasis", "object_key": "S1", "note": "S1 overweighted"},      # section→section
        {"type": "contribution", "object_key": "contribution_rank", "note": "wrong spine"},  # meta→meta
    ]
    out = RR.bank(tmp_path, {"contribution": "x"}, comparison,
                  feedback_path=fp, plan=_PLAN)
    res = {f["where"]: f["resolution"] for f in out["report"]["findings"]}
    assert res == {"S1": "resolved", "contribution_rank": "resolved"}
    intents = [r for r in ledger.read_jsonl(fp)
               if r.get("record") == adjudicate.PROJECTION_INTENT]
    objs = {i["object"].get("sid") or i["object"].get("key"): i["object"]["kind"]
            for i in intents}
    assert objs == {"S1": "section", "contribution_rank": "meta"}


# --- C3.4 fail-closed: an UNREADABLE plan degrades, it never destroys the banked read

#: JSON-shaped, NOT plan-shaped — each of these made ``_plan_target_namespaces`` raise.
_DEFECTIVE_PLANS = [
    {"meta": "not-a-mapping", "sections": []},
    {"meta": {}, "sections": "not-a-list"},
    {"meta": {}, "sections": ["a bare string, not a section dict"]},
    {"meta": {"contribution_rank": ["c"]}, "sections": [{"id": "S1"}, 7]},
]


@pytest.mark.parametrize("plan", _DEFECTIVE_PLANS)
def test_unreadable_plan_banks_the_report_and_mints_nothing(tmp_path, plan):
    """A plan that is JSON-shaped but not plan-shaped must NOT raise out of :func:`bank`.
    Because ``bank`` resolves BEFORE it appends, a raise took the WHOLE reader-report with
    it — both phases and every finding of a dispatched blind+compare read, lost to an
    untyped ``AttributeError``, which is the exact inverse of C3.4's law (keep the signal,
    refuse the actuator). It degrades instead: the report banks, every finding is
    ``unresolved`` and carries a ``resolution_basis`` naming the defect, and ZERO intents
    mint."""
    fp = tmp_path / "feedback.jsonl"
    comparison = [
        {"type": "contribution", "object_key": "contribution_rank", "note": "wrong spine"},
        {"type": "emphasis", "object_key": "S1", "note": "S1 overweighted"},
    ]
    out = RR.bank(tmp_path, {"contribution": "x"}, comparison,
                  feedback_path=fp, plan=plan)
    recs = ledger.read_jsonl(fp)
    rep = [r for r in recs if r.get("record") == "reader-report"][0]
    assert len(rep["findings"]) == 2 and out["n_findings"] == 2   # the read SURVIVES
    for f in rep["findings"]:
        assert f["resolution"] == "unresolved"                   # nothing addressable
        assert f["resolution_basis"].startswith(RR.PLAN_UNREADABLE_BASIS)  # and it says so
    assert [r for r in recs if r.get("record") == adjudicate.PROJECTION_INTENT] == []
    assert out["intents"] == []
    assert rep["clean"] is False        # the mismatch count decides clean, not the plan


def test_readable_plan_stamps_no_resolution_basis(tmp_path):
    """The degradation stamp is the EXCEPTION, never the norm: a well-formed plan leaves
    ``resolution_basis`` off every finding, resolved and unresolved alike."""
    comparison = [
        {"type": "contribution", "object_key": "contribution_rank", "note": "resolves"},
        {"type": "emphasis", "object_key": "ghost", "note": "does not resolve"},
    ]
    rep = RR.make_reader_report({"contribution": "x"}, comparison, plan=_PLAN)
    res = {f["where"]: f["resolution"] for f in rep["findings"]}
    assert res == {"contribution_rank": "resolved", "ghost": "unresolved"}
    assert all("resolution_basis" not in f for f in rep["findings"])
    # an EMPTY plan is READABLE (not defective): it addresses nothing, and says nothing
    empty = RR.make_reader_report({"contribution": "x"}, comparison, plan={})
    assert all(f["resolution"] == "unresolved" and "resolution_basis" not in f
               for f in empty["findings"])


# =============================================================================
# W2-S1 — the CLOSED section-id vocabulary on the compare packet
# =============================================================================
#
# ``compare_packet(blind, intended, sid_roster=None)`` gains an ADDITIVE {sid: title}
# vocabulary. Resolution downstream is EXACT by law (C3.4, and the C3.4 judge law that
# sec-III must never match sec-III-quadrature), so an UNADDRESSED reader invents keys
# ("weighting", "Section V") that reach no actuator. The roster closes that at the
# SOURCE — the reader is told the addresses — and NOT by loosening the match. Three
# properties are load-bearing and each has its own fail-closed test below:
#   (a) sid_roster=None is byte-compatible with HEAD;
#   (b) no fuzzy/prefix/fold matching is introduced ANYWHERE by this change;
#   (c) a mismatch about something ABSENT from the roster routes to the artefact
#       escape hatch and mints nothing — never to a silent wrong match.

_ROSTER = {"N1": "Introduction",
           "N2": "Relation to ITQDE and record-based spectral methods",
           "N3": "Spectral Surface Generation"}


def _head_compare_prompt(blind, intended):
    """The phase-2 prompt EXACTLY as it stood before the roster existed — frozen here so
    the additive default cannot drift. Any change to the no-roster prompt fails this."""
    intended_json = json.dumps(dict(intended or {}), ensure_ascii=False, indent=2,
                               sort_keys=True)
    blind_json = (blind if isinstance(blind, str)
                  else json.dumps(blind, ensure_ascii=False, indent=2, sort_keys=True))
    menu = ", ".join(sorted(RR.MISMATCH_TABLE))
    return (
        f"{RR.COMPARE_INSTRUCTION}\n\n"
        f"=== WHAT YOU RECOVERED BLIND ===\n{blind_json}\n\n"
        f"=== THE INTENDED OBJECT ===\n{intended_json}\n\n"
        'Return ONLY JSON: a list of mismatches, each {"type": "<one of: '
        f'{menu}>", "object_key": "<the meta key or the section id it concerns>", '
        '"note": "<what disagrees, one line>"}. Empty list if the recovered paper IS '
        "the intended paper on every axis."
    )


def test_sid_roster_none_is_byte_compatible_with_head():
    """(a) The additive default proven at the PACKET level: no roster => the HEAD prompt
    byte-for-byte, the HEAD payload keys exactly, no vocabulary block anywhere."""
    blind = {"contribution": "a convergence loop", "weighting": ["Methods: heavy"]}
    p = RR.compare_packet(blind, _INTENDED)
    assert p["prompt"] == _head_compare_prompt(blind, _INTENDED)
    assert "sid_roster" not in p and "object_key_vocabulary" not in p
    assert set(p) == {"reader", "organ", "phase", "instruction", "intended",
                      "blind_report", "mismatch_types", "compare_schema",
                      "seal_inversion", "prompt", "seal_check"}
    blob = json.dumps(p)
    assert "VOCABULARY" not in blob and RR.ARTEFACT_OBJECT_KEY not in blob
    # explicit-None is identical to the omitted kwarg
    assert RR.compare_packet(blind, _INTENDED, None) == p
    assert RR.compare_packet(blind, _INTENDED, sid_roster=None) == p


def test_sid_roster_constrains_object_key_to_the_closed_vocabulary():
    """With a roster the prompt names every id AND its title, names the meta keys, states
    that matching is exact, and offers the artefact escape hatch — and the payload carries
    the vocabulary as data for the caller that parses the reply."""
    blind = {"contribution": "a convergence loop"}
    p = RR.compare_packet(blind, _INTENDED, _ROSTER)
    prompt = p["prompt"]
    for sid, title in _ROSTER.items():
        assert sid in prompt and title in prompt
    for key in _INTENDED:
        assert key in prompt
    assert "CLOSED" in prompt
    assert RR.ARTEFACT_OBJECT_KEY in prompt
    assert "EXACT" in prompt                       # the exactness is stated to the reader
    assert p["sid_roster"] == _ROSTER
    v = p["object_key_vocabulary"]
    assert v["sids"] == list(_ROSTER)              # author order preserved (order mismatches)
    assert v["meta_keys"] == sorted(_INTENDED)
    assert v["escape_hatch"] == RR.ARTEFACT_OBJECT_KEY
    # the seal inversion is untouched: intent is still present by design
    assert p["seal_check"]["ok"] is True and p["seal_check"]["inverted"] is True


def test_sid_roster_carries_ids_and_titles_only_never_jobs_or_the_plan():
    """The roster is a vocabulary, not a plan leak: only ids and titles reach the packet.
    Building one from live plan sections must not drag jobs / node lists / contracts in."""
    plan_sections = [
        {"id": "N1", "title": "Introduction", "job": "seduce the referee in one page",
         "nodes_in_order": ["res:apex-claim", "res:secret-lemma"],
         "contract": {"must_state": "the unpublished bound"}},
        {"id": "N2", "title": "Methods", "job": "hide the weak experiment",
         "nodes_in_order": ["res:weak-run"]},
    ]
    roster = {s["id"]: s["title"] for s in plan_sections}
    p = RR.compare_packet({"contribution": "x"}, _INTENDED, roster)
    blob = json.dumps(p)
    for leak in ("seduce the referee", "hide the weak experiment", "res:apex-claim",
                 "res:secret-lemma", "res:weak-run", "must_state",
                 "the unpublished bound", "nodes_in_order"):
        assert leak not in blob, leak
    assert "N1" in blob and "Introduction" in blob and "Methods" in blob


def test_an_unusable_roster_raises_rather_than_pretending_to_constrain():
    """Fail-LOUD: a roster that cannot constrain is worse than none, because the prompt
    would still announce a closed vocabulary the reader could not honour."""
    blind = {"contribution": "x"}
    with pytest.raises(ValueError):                       # empty: constrains nothing
        RR.compare_packet(blind, _INTENDED, {})
    with pytest.raises(ValueError):                       # not a mapping
        RR.compare_packet(blind, _INTENDED, ["N1", "N2"])
    with pytest.raises(ValueError):                       # blank id
        RR.compare_packet(blind, _INTENDED, {"  ": "Introduction"})
    with pytest.raises(ValueError):                       # multi-line id
        RR.compare_packet(blind, _INTENDED, {"N1\nN2": "Introduction"})
    with pytest.raises(ValueError):                       # id == the escape hatch
        RR.compare_packet(blind, _INTENDED, {RR.ARTEFACT_OBJECT_KEY: "Introduction"})
    with pytest.raises(ValueError):                       # collides with the meta namespace
        RR.compare_packet(blind, _INTENDED, {"thesis": "Introduction"})
    with pytest.raises(ValueError):                       # the hatch as a real meta key
        RR.compare_packet(blind, {RR.ARTEFACT_OBJECT_KEY: "x",
                                  "contribution_rank": ["a"], "exclusions": []},
                          {"N1": "Introduction"})


# --- (b) NO fuzzy, NO prefix, NO fold — the C3.4 judge law, re-proven here ----

_SPLIT_PLAN = {
    "sections": [{"id": "sec-III", "nodes_in_order": ["res:a"]},
                 {"id": "sec-III-quadrature", "nodes_in_order": ["res:b"]}],
    "meta": {"contribution_rank": ["the primary claim"], "exclusions": []},
}


def test_no_prefix_or_fuzzy_matching_is_introduced_anywhere(tmp_path):
    """The named vector: ``sec-III`` must resolve to ``sec-III`` and NOTHING else, and no
    near miss may resolve at all. Exact, case-sensitive, both directions of the prefix."""
    fp = tmp_path / "feedback.jsonl"
    comparison = [
        {"type": "emphasis", "object_key": "sec-III", "note": "exact hit"},
        {"type": "order", "object_key": "sec-III-quad", "note": "a PREFIX of a real id"},
        {"type": "order", "object_key": "sec-II", "note": "a PREFIX of sec-III"},
        {"type": "order", "object_key": "SEC-III", "note": "case drift"},
        {"type": "order", "object_key": "sec_III", "note": "separator drift"},
        {"type": "order", "object_key": "sec-IIIs", "note": "pluralised"},
    ]
    out = RR.bank(tmp_path, {"contribution": "x"}, comparison,
                  feedback_path=fp, plan=_SPLIT_PLAN)
    res = {f["where"]: f["resolution"] for f in out["report"]["findings"]}
    assert res == {"sec-III": "resolved", "sec-III-quad": "unresolved",
                   "sec-II": "unresolved", "SEC-III": "unresolved",
                   "sec_III": "unresolved", "sec-IIIs": "unresolved"}
    intents = [r for r in ledger.read_jsonl(fp)
               if r.get("record") == adjudicate.PROJECTION_INTENT]
    assert len(intents) == 1                              # exactly the exact hit
    assert intents[0]["object"]["sid"] == "sec-III"       # never sec-III-quadrature


# --- (c) the escape hatch: expressible, and never a silent match --------------

def test_the_artefact_hatch_is_expressible_and_mints_nothing(tmp_path):
    """A mismatch about something ABSENT from the roster routes to the hatch: the finding
    BANKS with its full note (the signal is kept and reaches the author) and mints NO
    intent — it is unresolved by the ordinary rule, with no special case in the resolver."""
    fp = tmp_path / "feedback.jsonl"
    note = "the paper is a survey; no section owns this and the plan never carried one"
    comparison = [{"type": "identity", "object_key": RR.ARTEFACT_OBJECT_KEY,
                   "note": note}]
    out = RR.bank(tmp_path, {"contribution": "x"}, comparison,
                  feedback_path=fp, plan=_SPLIT_PLAN)
    f = out["report"]["findings"][0]
    assert f["where"] == RR.ARTEFACT_OBJECT_KEY
    assert f["issue"] == note                             # expressible, in full
    assert f["resolution"] == "unresolved"
    recs = ledger.read_jsonl(fp)
    rep = [r for r in recs if r.get("record") == "reader-report"][0]
    assert len(rep["findings"]) == 1                      # banked
    assert [r for r in recs if r.get("record") == adjudicate.PROJECTION_INTENT] == []
    assert out["intents"] == []
    # and the hatch is not a member of EITHER live namespace — it can never collide
    sids, meta_keys = RR._plan_target_namespaces(_SPLIT_PLAN)
    assert RR.ARTEFACT_OBJECT_KEY not in sids and RR.ARTEFACT_OBJECT_KEY not in meta_keys


def test_a_roster_absent_target_never_routes_to_a_silent_match(tmp_path):
    """The hatch's whole reason: a mismatch about a section the plan does NOT carry must
    stay unresolved, never be absorbed by the nearest real id. Both spellings — the hatch
    and an invented id — refuse, and neither touches ``sec-III``."""
    fp = tmp_path / "feedback.jsonl"
    comparison = [
        {"type": "emphasis", "object_key": "sec-IV", "note": "a section that never was"},
        {"type": "emphasis", "object_key": RR.ARTEFACT_OBJECT_KEY,
         "note": "cross-cutting weighting with no single home"},
    ]
    out = RR.bank(tmp_path, {"contribution": "x"}, comparison,
                  feedback_path=fp, plan=_SPLIT_PLAN)
    assert {f["where"]: f["resolution"] for f in out["report"]["findings"]} == {
        "sec-IV": "unresolved", RR.ARTEFACT_OBJECT_KEY: "unresolved"}
    assert out["intents"] == []
    assert [r for r in ledger.read_jsonl(fp)
            if r.get("record") == adjudicate.PROJECTION_INTENT] == []


def test_the_prompt_states_which_namespace_each_mismatch_type_must_name():
    """The vocabulary is useless if the reader cannot tell WHICH half applies: resolution
    is namespace-SCOPED by the type's ``object_kind`` (C3.4), so a real section id written
    under a meta-kind type resolves to nothing. The prompt states the coupling, and states
    it FROM ``MISMATCH_TABLE`` — the same table the verb law and the resolver read, so the
    prompt cannot drift from the rule it announces."""
    p = RR.compare_packet({"contribution": "x"}, _INTENDED, _ROSTER)
    prompt = p["prompt"]
    sect = sorted(t for t, r in RR.MISMATCH_TABLE.items() if r.object_kind == "section")
    meta = sorted(t for t, r in RR.MISMATCH_TABLE.items() if r.object_kind == "meta")
    assert f"a SECTION ID is required for: {', '.join(sect)}" in prompt
    assert f"a META KEY is required for: {', '.join(meta)}" in prompt
    # every mismatch type is placed in exactly one of the two lists (the table partitions)
    assert set(sect) | set(meta) == set(RR.MISMATCH_TABLE)
    assert not set(sect) & set(meta)
    # and the cross-namespace case is routed to the hatch, never to a guess
    assert "resolves to nothing" in prompt and RR.ARTEFACT_OBJECT_KEY in prompt


# ---------------------------------------------------------------------------
# W4-B1: the reader meets the PROJECT's artefact, not the manuscript dir's
# (WO-20260820-r10-binds-the-wrong-pdf)
#
# The live defect: on SSG the plan declares meta.target_dir = '.../whitepaper',
# the manuscript dir's only top-level PDF is FIGURE_REVIEW.pdf (a figure-review
# audit), and the sole-top-level fall-through bound the AUDIT as the finished
# paper — so the whole-artefact grade never once read the whitepaper. The binding
# now runs through release.artefact_pdf_binding; these pin it at THIS callsite.
# ---------------------------------------------------------------------------

def _seen_pdf(monkeypatch):
    seen = {}

    def fake_uv(pdf_path, uv_bin, timeout):
        seen["pdf"] = Path(pdf_path)
        return "the whole rendered text of the object that was bound."

    monkeypatch.setattr(RR, "_resolve_uv", lambda: "uv")
    monkeypatch.setattr(RR, "_extract_via_uv", fake_uv)
    return seen


def _ssg_shaped(tmp_path: Path) -> Path:
    md = tmp_path / "proj" / "manuscript"
    (md / "whitepaper").mkdir(parents=True)
    (md / "FIGURE_REVIEW.pdf").write_bytes(b"%PDF-1.5 the audit")
    (md / "whitepaper" / "main.pdf").write_bytes(b"%PDF-1.5 the paper")
    return md


def test_extract_binds_the_target_dir_artefact_not_the_manuscript_audit(tmp_path, monkeypatch):
    md = _ssg_shaped(tmp_path)
    seen = _seen_pdf(monkeypatch)
    RR.extract_artefact_text(md, plan={"meta": {"target_dir": "whitepaper"}})
    assert seen["pdf"].name == "main.pdf"
    assert seen["pdf"].parent.name == "whitepaper"      # the PAPER, not FIGURE_REVIEW.pdf


def test_extract_reads_the_committed_plan_when_none_is_passed(tmp_path, monkeypatch):
    """The live arm passes no plan: the convention path must reach the same object,
    else the fix is dead exactly where the defect lived."""
    md = _ssg_shaped(tmp_path)
    (md / "projection_plan.json").write_text(
        json.dumps({"meta": {"target_dir": "whitepaper"}, "sections": []}),
        encoding="utf-8")
    seen = _seen_pdf(monkeypatch)
    RR.extract_artefact_text(md)
    assert seen["pdf"].parent.name == "whitepaper"


def test_extract_refuses_an_audit_pdf_and_names_why(tmp_path, monkeypatch):
    """No plan, no target dir, one audit sheet: the read must FAIL, never certify the
    audit as the artefact. Silence never passes — and neither does the wrong object."""
    md = tmp_path / "m"
    md.mkdir()
    (md / "FIGURE_REVIEW.pdf").write_bytes(b"%PDF-1.5")
    _seen_pdf(monkeypatch)
    with pytest.raises(RuntimeError) as ei:
        RR.extract_artefact_text(md)
    msg = str(ei.value)
    assert "no final PDF to bind" in msg and "audit-named" in msg


def test_the_binding_is_inspectable_before_the_read(tmp_path):
    """The arm PRINTS what it bound, so a wrong binding is visible in the run instead
    of three months later."""
    md = _ssg_shaped(tmp_path)
    b = RR.artefact_pdf_binding(md, plan={"meta": {"target_dir": "whitepaper"}})
    assert b["pdf"] == "whitepaper/main.pdf" and b["source"] == "main.pdf"
    assert Path(b["target_dir"]).name == "whitepaper"


def test_extract_with_no_target_dir_is_unchanged(tmp_path, monkeypatch):
    """The plain case (no plan, no target dir, an ordinary artefact) still binds
    exactly as HEAD did — the finalize record over a decoy main.pdf."""
    md = tmp_path / "manuscript"
    md.mkdir()
    (md / "the-object.pdf").write_bytes(b"%PDF-1.5 canonical")
    (md / "main.pdf").write_bytes(b"%PDF-1.5 decoy")
    _finalize(md, "the-object.pdf")
    seen = _seen_pdf(monkeypatch)
    RR.extract_artefact_text(md)
    assert seen["pdf"].name == "the-object.pdf"


# ---------------------------------------------------------------------------
# W4-B3: reader-blindness provenance (WO-20260820-reader-blindness-provenance)
#
# A blind read whose contamination is disclosed only in a session return is a
# blind read whose contamination is LOST at the next reconstruction. The record
# now carries the disclosure, and the absence of one never reads as clean.
# ---------------------------------------------------------------------------

def test_absent_blindness_reads_as_undisclosed_never_clean():
    rep = RR.make_reader_report({"contribution": "x"}, [])
    assert rep["blindness"] == {"claimed": "undisclosed", "disclosures": [],
                                "disclosed": False}
    assert rep["clean"] is True          # the artefact verdict is untouched by provenance


def test_a_legacy_record_with_no_field_reads_as_undisclosed():
    """Every R10 record banked before this field existed: undisclosed, not clean."""
    assert RR.blindness_of({"record": "reader-report", "clean": True}) == {
        "claimed": "undisclosed", "disclosures": [], "disclosed": False}
    assert RR.blindness_of(None)["claimed"] == "undisclosed"


def test_a_clean_claim_is_recorded_as_claimed():
    rep = RR.make_reader_report({"contribution": "x"}, [],
                                blindness={"claimed": "clean", "disclosures": []})
    assert rep["blindness"] == {"claimed": "clean", "disclosures": [],
                                "disclosed": True}


def test_disclosures_outrank_a_clean_claim():
    """The predecessor's own case: a reader that inverted its act order to protect the
    blind read, but had seen a PDF listing gesturing at the content. It claimed clean
    and listed the exposure; the listing wins."""
    rep = RR.make_reader_report({"contribution": "x"}, [], blindness={
        "claimed": "clean",
        "disclosures": ["a find listing naming N15_planted_escape.pdf"]})
    assert rep["blindness"]["claimed"] == "contaminated"
    assert rep["blindness"]["downgraded"]
    assert rep["blindness"]["disclosures"] == [
        "a find listing naming N15_planted_escape.pdf"]


def test_an_unrecognised_claim_never_reads_as_clean():
    for claim in ("mostly clean", "cleanish", "CLEAN-ENOUGH", "", "unknown", 7, {}):
        b = RR.normalize_blindness({"claimed": claim})
        assert b["claimed"] == "undisclosed" and b["disclosed"] is False


def test_the_claim_vocabulary_is_case_and_space_tolerant_but_exact():
    assert RR.normalize_blindness({"claimed": "  Clean "})["claimed"] == "clean"
    assert RR.normalize_blindness("CONTAMINATED")["claimed"] == "contaminated"
    assert RR.normalize_blindness(["saw the plan"]) == {
        "claimed": "contaminated", "disclosures": ["saw the plan"], "disclosed": True}
    assert RR.normalize_blindness([])["claimed"] == "undisclosed"


def test_bank_carries_the_blindness_into_the_ledger(tmp_path):
    fp = tmp_path / "feedback.jsonl"
    out = RR.bank(tmp_path, {"contribution": "x"}, [], feedback_path=fp,
                  blindness={"claimed": "contaminated",
                             "disclosures": ["read the predecessor's return"]})
    banked = [r for r in ledger.read_jsonl(fp) if r.get("record") == "reader-report"]
    assert len(banked) == 1
    assert banked[0]["blindness"]["claimed"] == "contaminated"
    assert banked[0]["blindness"]["disclosures"] == ["read the predecessor's return"]
    assert RR.blindness_of(banked[0])["disclosed"] is True
    assert out["report"]["blindness"] == banked[0]["blindness"]


def test_blindness_does_not_perturb_the_finding_ids_or_the_verdict():
    """Provenance about the READ never moves the actuator ids or the artefact verdict —
    a contaminated reader's mismatches are still real findings."""
    comparison = [{"type": "contribution", "object_key": "thesis", "note": "n"}]
    a = RR.make_reader_report({"contribution": "x"}, comparison, ts="2026-08-21T00:00:00")
    b = RR.make_reader_report({"contribution": "x"}, comparison, ts="2026-08-21T00:00:00",
                              blindness={"claimed": "contaminated",
                                         "disclosures": ["saw a prior return"]})
    assert [f["id"] for f in a["findings"]] == [f["id"] for f in b["findings"]]
    assert a["id"] == b["id"] and a["clean"] == b["clean"]
