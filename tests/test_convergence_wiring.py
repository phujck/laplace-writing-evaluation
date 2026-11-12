"""Phase F-wire completeness — the guard against an unrouted finding kind.

Every Phase-B..I component check module EXPORTS a finding-kinds manifest; Phase F
folds them ALL into ``schema.KIND_TO_WORK`` so no kind can reach
``propagate.intake_items`` unrouted (the door raises on one — completeness is its
invariant). This test IS that guard: it reconstructs each manifest from its owning
module and asserts

  * every component kind is routed, to the SAME owning stage its manifest declares;
  * the shared kinds (citation-cluster, figure-debris, orthography-fork) dedupe;
  * the two new soft dims (citation_coverage, style_conformance) are declared;
  * evaluate_round bridges the new reader labels without KeyError, and a HARD reader
    blocks only when it actually ran (candidate-lock cadence);
  * the intake door accepts a sample of the new kinds and routes them.
"""
from __future__ import annotations

import io
import json
import re
from collections import Counter
from pathlib import Path

import pytest

from laplace.pipeline import (
    apparatus_common,
    convergence,
    house_style,
    propagate,
    scaffold_wipe,
    schema,
    visual_gate,
)
from laplace.pipeline.readers import dimension_manifest, finding_kinds_manifest
from laplace.pipeline.readers import verdict_io


def _stage_of(kind: str):
    """The owning stage a wired kind resolves to (None for report-only)."""
    work = schema.KIND_TO_WORK[kind]
    return schema.WORK_TO_LAYER[work] if work is not None else None


def _component_manifests():
    """(label, {kind: expected_owning_stage_or_None}) for every component manifest,
    read from its OWNING module — the source of truth, never re-enumerated here."""
    b = {k: e["primary"] for k, e in scaffold_wipe.FINDING_KIND_STAGE.items()}
    c = dict(apparatus_common.FINDING_KIND_STAGE)
    d2 = {r["kind"]: r["owning_stage"] for r in visual_gate.routing_manifest()}
    # I1 routes by WORK kind; resolve to its owning stage (None stays report-only).
    i1 = {k: (schema.WORK_TO_LAYER[w] if w is not None else None)
          for k, w in house_style.KIND_ROUTES.items()}
    e = {r["kind"]: r["owning_stage"] for r in finding_kinds_manifest()}
    return [("B", b), ("C", c), ("D2", d2), ("I1", i1), ("E", e)]


# --- completeness: every kind routed, to the stage its manifest declares -----

def test_every_component_kind_is_routed_and_consistent():
    unrouted, mismatched = [], []
    for label, manifest in _component_manifests():
        for kind, expect_stage in manifest.items():
            if kind not in schema.KIND_TO_WORK:
                unrouted.append((label, kind))
                continue
            work = schema.KIND_TO_WORK[kind]
            assert work is None or work in schema.WORK_KINDS, (kind, work)
            assert work is None or work in schema.WORK_TO_LAYER, (kind, work)
            if _stage_of(kind) != expect_stage:
                mismatched.append((label, kind, _stage_of(kind), expect_stage))
    assert not unrouted, f"unrouted component kinds: {unrouted}"
    assert not mismatched, f"kinds routed to the wrong owning stage: {mismatched}"


def test_report_only_kinds_route_to_none():
    # orthography-fork (F33 British/American) is report-only in BOTH C and I1
    assert schema.KIND_TO_WORK["orthography-fork"] is None


def test_wiring_count_dedupes_the_three_shared_kinds():
    from laplace.pipeline import promise_audit, meta_leak_scrub
    from laplace.pipeline.readers import source_delta
    wired = schema.register_component_kinds()   # idempotent — safe to re-run
    with_dupes = (len(scaffold_wipe.FINDING_KIND_STAGE)      # 7
                  # 28 C1..C9 kinds + the 8 authored-closure kinds (closure-roadmap-*,
                  # closure-dependency-unlinked, closure-object-*) that
                  # pipeline/authored_closure.py emits and readers/apparatus.py routes
                  + len(apparatus_common.FINDING_KIND_STAGE)  # 36
                  + len(visual_gate.VISUAL_FINDING_KINDS)     # 6
                  + len(house_style.KIND_ROUTES)              # 5
                  + len(finding_kinds_manifest())             # 21 (14 + R9's 3 + R10's 4)
                  # DETECTOR-ORGANS (ARMING_2026-07-16): promise (5) + source-delta
                  # (3) + meta-leak source-tier (1); gap_ledger consumes (0).
                  + len(promise_audit.finding_kinds_manifest())     # 5
                  + len(source_delta.finding_kinds_manifest())      # 3
                  + len(meta_leak_scrub.finding_kinds_manifest()))  # 1
    assert with_dupes == 84
    # citation-cluster (B,C), figure-debris (B,E), orthography-fork (C,I1) merge -> 61;
    # R9's three caption-blind-* and R10's four whole-artefact kinds are unique -> 64;
    # the nine detector-organ kinds are all fresh -> 73; the eight authored-closure
    # kinds are all fresh -> 81. Exactly three kinds are shared, so the dedupe is
    # the arithmetic below — a fourth sharer would break BOTH lines at once.
    assert len(wired) == 81
    assert len(wired) == with_dupes - 3
    # …and the three are those three, named. This is what the counts above stand
    # for; without it a new sharer plus a new kind cancel out in the arithmetic.
    seen = Counter(k for _label, m in _component_manifests() for k in m)
    seen += Counter(r["kind"] for mod in (promise_audit, source_delta, meta_leak_scrub)
                    for r in mod.finding_kinds_manifest())
    assert {k for k, n in seen.items() if n > 1} == {
        "citation-cluster", "figure-debris", "orthography-fork"}


# --- the two new soft dimensions --------------------------------------------

def test_new_soft_dimensions_declared_soft_only():
    for dim in ("citation_coverage", "style_conformance"):
        assert dim in convergence.SOFT_DIMENSIONS
        assert dim not in convergence.HARD_DIMENSIONS


def test_reader_dimensions_are_existing_contract_axes():
    allowed = (set(convergence.HARD_DIMENSIONS) | set(convergence.SOFT_DIMENSIONS)
               | {"author_acceptance"})
    for row in dimension_manifest():
        assert row["dimension"] in allowed, row


# --- evaluate_round bridges the new reader labels ----------------------------

def _panel(**labels):
    """label -> (clean, n_flags)."""
    return [{"label": lbl, "clean": cl, "flags": [{"issue": "x"}] * nf}
            for lbl, (cl, nf) in labels.items()]


def test_evaluate_round_bridges_every_new_reader_label():
    panel = _panel(
        meta_leak=(True, 0), voice=(True, 0), closure=(True, 0), caption=(True, 0),
        claims=(True, 0), calc=(True, 0),
        cold_reader=(True, 0), skim_reader=(True, 0), referee=(True, 0),
        apparatus=(True, 0), figure_reader=(True, 0), visual=(True, 0),
        feral=(True, 0), citation=(True, 0), house_style=(True, 0))
    r = convergence.evaluate_round(panel, round=1)
    ev = r["contract"]
    assert set(ev["hard"]) == set(convergence.HARD_DIMENSIONS)
    assert set(ev["soft"]) == set(convergence.SOFT_DIMENSIONS)
    assert r["hard_failing"] is False   # every reader clean -> hard gates pass


def test_hard_reader_blocks_only_when_it_ran():
    base = dict(meta_leak=(True, 0), voice=(True, 0), closure=(True, 0),
                caption=(True, 0), claims=(True, 0), calc=(True, 0))
    # candidate-lock reader ABSENT: the hard gate is unchanged (a normal fixer round)
    silent = convergence.evaluate_round(_panel(**base))
    assert silent["contract"]["hard"]["no_meta_leak"] is True
    assert silent["hard_failing"] is False
    # candidate-lock reader RAN and is not clean: it blocks the hard gate
    blocked = convergence.evaluate_round(_panel(**base, figure_reader=(False, 2)))
    assert blocked["contract"]["hard"]["no_meta_leak"] is False
    assert blocked["hard_failing"] is True


def test_silent_reader_scores_neutral_not_clean():
    # a soft reader that never ran contributes 0.5 (never a free 1.0), so a group
    # with one clean + one silent reader lands strictly between.
    panel = _panel(meta_leak=(True, 0), voice=(True, 0), closure=(True, 0),
                   caption=(True, 0), claims=(True, 0), calc=(True, 0))
    soft = convergence.evaluate_round(panel)["contract"]["soft"]
    # closure clean (1.0) + skim_reader silent (0.5) -> 0.75
    assert soft["reader_reconstruction"] == 0.75
    # new soft dims default neutral when their label is absent
    assert soft["citation_coverage"] == 0.5
    assert soft["style_conformance"] == 0.5


# --- C5.3: artefact_integrity consumes R10 roster-conditionally --------------
# The four fail-closed legs. artefact_integrity = compile ∧ caption ∧ visual today;
# when R10 (restart_reader) is in the ACTIVE tier's lock roster it ALSO ANDs in
# R10's file-backed clean, under the tightened rule "rostered ⇒ must have a PASSING
# verdict". The panel entries below ride the REAL transport (verdict_io over on-disk
# verdict files + the restart organ) so the seam convergence consumes is the seam the
# loop produces — never a hand-forged shape.

_R10 = "R10"                       # the reader id the roster carries
_R10_LABEL = "restart_reader"      # its panel label (single-sourced from the roster)


def _artefact_panel(*extra):
    """A panel whose compile/caption/visual inputs to artefact_integrity are all
    clean — plus any extra reader entries. compile_ok is passed separately."""
    base = [{"label": "caption", "clean": True, "flags": []},
            {"label": "visual", "clean": True, "flags": []}]
    return base + list(extra)


def _pre_r10_artefact_integrity(panel, *, compile_ok=True):
    """The artefact_integrity value under the PRE-R10 definition
    (compile ∧ caption ∧ visual), computed independently of evaluate_round — the
    reference the fix_mode=loop tier must still equal byte-for-byte."""
    by = {p["label"]: p for p in panel}

    def clean(label):
        return bool(by.get(label, {}).get("clean"))

    def hard_ok(label):
        p = by.get(label)
        if p is None:
            return True
        if p.get("failed"):
            return False
        return bool(p.get("clean"))

    return bool(compile_ok) and clean("caption") and hard_ok("visual")


def _r10_entry_from_reply(round_dir, raw):
    """Drive the REAL R10 transport: parse the compare-phase reply with the restart
    organ, write the on-disk verdict file, and rebuild the panel entry via
    assemble_sidecar — exactly the seam the mechround merges. Returns the single
    restart_reader panel entry."""
    findings = verdict_io.parse_reply("restart", _R10, raw)      # rides make_reader_report
    verdict_io.write_verdict(_R10, _R10_LABEL, findings, round_dir)
    entries = verdict_io.assemble_sidecar(round_dir, [_R10], calc_mirror=False)
    return next(e for e in entries if e["label"] == _R10_LABEL)


# leg 1 — true-positive: a real identity-mismatch flips the HARD axis to unmet
def test_rostered_r10_identity_mismatch_unmeets_artefact_integrity(tmp_path):
    # a real COMPARE reply carrying a `contribution` (identity) mismatch: the restart
    # organ turns it into an unclean verdict; with R10 rostered, artefact_integrity is
    # HARD-unmet even though compile/caption/visual are all clean.
    reply = json.dumps([{"type": "contribution", "object_key": "apex",
                         "note": "the blind reader recovered a different paper"}])
    entry = _r10_entry_from_reply(tmp_path, reply)
    assert entry["clean"] is False                       # the organ found the mismatch
    panel = _artefact_panel(entry)
    r = convergence.evaluate_round(panel, compile_ok=True, lock_roster=[_R10])
    assert r["contract"]["hard"]["artefact_integrity"] is False
    assert r["hard_failing"] is True
    # and the pre-R10 axis (its other inputs) is clean — the flip is R10's doing alone
    assert _pre_r10_artefact_integrity(panel) is True


# leg 2 — absent: a ROSTERED R10 with no verdict file leaves the axis unmet
def test_rostered_r10_absent_verdict_unmeets_artefact_integrity(tmp_path):
    # no verdict file written: assemble_sidecar yields {label, failed:true} (silence
    # never passes). Rostered ⇒ absent must leave artefact_integrity unmet.
    entries = verdict_io.assemble_sidecar(tmp_path, [_R10], calc_mirror=False)
    entry = next(e for e in entries if e["label"] == _R10_LABEL)
    assert entry.get("failed") is True and entry["clean"] is False
    panel = _artefact_panel(entry)
    r = convergence.evaluate_round(panel, compile_ok=True, lock_roster=[_R10])
    assert r["contract"]["hard"]["artefact_integrity"] is False
    assert r["hard_failing"] is True


# leg 3 — malformed (relies on C5.1a): a wrong-shape reply is failed, never clean
def test_rostered_r10_malformed_reply_unmeets_artefact_integrity(tmp_path, monkeypatch):
    # a well-formed-JSON-but-WRONG-SHAPE compare reply. C5.1a makes the restart organ
    # fail-LOUD: parse_reply RAISES rather than certifying clean.
    bad = json.dumps({"summary": "looks fine to me"})   # none of {mismatches,findings,verdict}
    with pytest.raises(ValueError):
        verdict_io.parse_reply("restart", _R10, bad)
    # driven through the write CLI, the raise is caught and banked as a FAILED verdict
    # FILE (exit nonzero) — the shape convergence then reads.
    monkeypatch.setattr("sys.stdin", io.StringIO(bad))
    rc = verdict_io.main(["write", "restart", _R10, _R10_LABEL, str(tmp_path)])
    assert rc == 1                                       # unclean/failed exit
    entries = verdict_io.assemble_sidecar(tmp_path, [_R10], calc_mirror=False)
    entry = next(e for e in entries if e["label"] == _R10_LABEL)
    assert entry["clean"] is False
    panel = _artefact_panel(entry)
    r = convergence.evaluate_round(panel, compile_ok=True, lock_roster=[_R10])
    assert r["contract"]["hard"]["artefact_integrity"] is False
    assert r["hard_failing"] is True


# leg 4 — tier parity: a roster WITHOUT R10 computes the axis exactly as before
def test_loop_tier_without_r10_is_byte_equal_to_pre_r10(tmp_path):
    # the fix_mode=loop tier does not roster R10. On the SAME fixtures as legs 1–3 the
    # R10 clause is omitted, so artefact_integrity is byte-for-byte the pre-R10
    # definition — a stray R10 entry (even a FAILED one) is IGNORED, the retained tier
    # is provably not broken.
    mismatch = _r10_entry_from_reply(tmp_path / "mm", json.dumps(
        [{"type": "contribution", "object_key": "apex", "note": "different paper"}]))
    absent = next(e for e in verdict_io.assemble_sidecar(
        tmp_path / "abs", [_R10], calc_mirror=False) if e["label"] == _R10_LABEL)
    clean_r10 = _r10_entry_from_reply(tmp_path / "ok", json.dumps([]))  # empty list = clean
    fixtures = [
        _artefact_panel(),                 # no R10 entry at all
        _artefact_panel(mismatch),         # a failing R10 entry present but NOT rostered
        _artefact_panel(absent),           # a failed (absent-derived) R10 entry present
        _artefact_panel(clean_r10),        # a clean R10 entry present
    ]
    for panel in fixtures:
        for roster in (None, [], ["R1", "R6"]):        # every non-R10-rostering roster
            got = convergence.evaluate_round(
                panel, compile_ok=True, lock_roster=roster
            )["contract"]["hard"]["artefact_integrity"]
            want = _pre_r10_artefact_integrity(panel, compile_ok=True)
            assert got is want, (roster, [p["label"] for p in panel])
            assert want is True                        # caption+visual clean ⇒ axis met
    # and a compile failure still unmeets the axis identically in the loop tier
    for roster in (None, ["R1"]):
        r = convergence.evaluate_round(_artefact_panel(mismatch), compile_ok=False,
                                       lock_roster=roster)
        assert r["contract"]["hard"]["artefact_integrity"] is False


# --- the intake door accepts the new kinds -----------------------------------

def test_intake_door_routes_a_sample_of_new_kinds():
    # one kind per owning stage, so the door is exercised across all seven layers
    sample = ["figure-debris", "citation-cluster", "eq-unused", "overfull-visual",
              "matter-scaffold", "referee-inherited-uncited", "referee-insufficient"]
    recs = [{"id": f"FB-{i}", "kind": k, "node_id": "def:x", "status": "open",
             "text": "seeded finding"} for i, k in enumerate(sample)]
    plan = {"meta": {"project": "p"}, "sections": []}
    items = propagate.intake_items(recs, plan, {"def:x": {}})
    assert len(items) == len(sample)    # none is report-only -> each yields an item
    for it in items:
        assert it["kind"] in schema.WORK_KINDS
        assert it["owning_stage"] in schema.WORK_TO_LAYER.values()
    # the seven stages are all reached
    assert {it["owning_stage"] for it in items} == {
        "figures", "prose", "structural", "document", "narrative",
        "research-state", "projection"}


def test_report_only_kind_is_a_comment_not_a_work_item():
    recs = [{"id": "FB-o", "kind": "orthography-fork", "node_id": "def:x",
             "status": "open", "text": "british/american split"}]
    plan = {"meta": {"project": "p"}, "sections": []}
    assert propagate.intake_items(recs, plan, {"def:x": {}}) == []


# --- F3 (audit §A5): the JS driver's lock roster excludes R9/R10 --------------
# The Python evaluate_round is tier-aware (legs 1–4 above). This pins the JS side of
# the SAME carve-out: project-fixedpoint.js must serve the dialed roster MINUS the
# R9 rasteriser / R10 whole-PDF-restart arms (harnessed-only, per dials.py's ruling).
# The driver is JS, so we pin its SOURCE the way test_shared_model.py pins HTML/JS
# contracts — a grep-shaped assertion over the file text (comments stripped so the
# carve-out's PROSE mention of R9/R10 never reads as live code).

_REPO = Path(__file__).resolve().parents[1]
_FIXEDPOINT_JS = _REPO / ".claude" / "workflows" / "project-fixedpoint.js"


def _strip_js_comments(text: str) -> str:
    """Drop JS block/line comments so a MENTION of a token in a comment (the §A5
    carve-out note names R9/R10 and LOCK_READERS) never reads as live code."""
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)     # /* block */
    text = re.sub(r"(?m)//.*$", " ", text)                 # // line
    return text


def test_fixedpoint_derives_the_carveout_roster():
    """The FIXEDPOINT_READERS filter that drops R9/R10 is present in the driver."""
    src = _FIXEDPOINT_JS.read_text(encoding="utf-8")
    assert "const FIXEDPOINT_READERS = LOCK_READERS.filter(" in src
    # the filter drops exactly the two harnessed-only arms
    assert "r !== 'R9'" in src and "r !== 'R10'" in src


def test_fixedpoint_dispatch_and_assemble_use_the_carveout_roster():
    """Every reader-flow (dispatch loop + verdict assemble) rides FIXEDPOINT_READERS,
    NOT the full dialed LOCK_READERS — else a rostered-but-unimplemented R9/R10 would
    read as absent-file=failed forever under fix_mode=loop."""
    code = _strip_js_comments(_FIXEDPOINT_JS.read_text(encoding="utf-8"))
    # the dispatch loop iterates the carved roster
    assert "for (const rid of FIXEDPOINT_READERS)" in code
    assert "for (const rid of LOCK_READERS)" not in code
    # the verdict-assemble roster passed to verdict_io is the carved one
    assert "FIXEDPOINT_READERS.join(','" in code
    # LOCK_READERS survives ONLY as the source of the filter — it never FLOWS to a
    # reader again (no .join over it, no for-of over it in live code)
    assert "LOCK_READERS.join(" not in code
    # the carved roster is the one that flows: named at the derivation + all 3 flows
    assert code.count("FIXEDPOINT_READERS") >= 3


def test_fixedpoint_still_reads_the_full_roster_from_dials():
    """The carve-out is a FILTER, not a hard-coded list: LOCK_READERS still comes from
    the live dials (so a dial edit still reaches the loop), FIXEDPOINT_READERS derives
    from it. The harnessed organ's roster is the untouched dialed one."""
    code = _strip_js_comments(_FIXEDPOINT_JS.read_text(encoding="utf-8"))
    assert "const LOCK_READERS = (DIALS.loop.lock && DIALS.loop.lock.readers)" in code
    assert "const FIXEDPOINT_READERS = LOCK_READERS.filter(" in code


# --- F3 (audit §A5): the /pipeline surface renders the carve-out per organ ----

def test_pipeline_surface_carveout_note_names_the_harnessed_only_arms():
    """The module-level carve-out note is data-shaped and names R9/R10 as the
    harnessed-only arms — so the loop→converge mapping is no longer silent about the
    per-organ roster difference."""
    from laplace.web import pipeline_surface as ps
    note = ps._LOCK_CARVEOUT
    assert "R9" in note and "R10" in note
    assert "harnessed" in note.lower()
    assert "fix_mode=loop" in note or "old loop" in note.lower()


def test_converge_organ_payload_carries_the_lock_carveout():
    """The converge organ's board payload gains a ``lock_carveout`` field (data, not
    buried prose) so /pipeline can render the tier-aware roster per organ."""
    from laplace.web import pipeline_surface as ps
    from laplace.pipeline import registry
    project = next((n for n in ("subset-sum-itqde",)
                    if registry.resolve(n) is not None), None)
    if project is None:
        pytest.skip("no resolvable project on disk to build the chain read model")
    out = ps.chain(project)
    assert out is not None
    converge = next(o for o in out["organs"] if o["id"] == "converge")
    assert converge.get("lock_carveout") == ps._LOCK_CARVEOUT
    assert "R9" in converge["lock_carveout"] and "R10" in converge["lock_carveout"]


# --- W4-B2: the LIVE R10 arm's commands (WO-20260820-r10-bank-omits-plan) -----
# The roster and the target resolver are useless if the arm that fires them is
# wired without their inputs. The live defect: step 5 called RR.bank WITHOUT
# plan=, so _resolve_findings_against_plan never ran at the live callsite — and
# with plan=None the '__artefact__' escape hatch, whose whole purpose is to bank
# signal and mint NOTHING, minted a draft projection-intent pointed at the literal
# key. These pin the ARM's own command text, the way the fixedpoint roster tests
# above pin theirs (comments stripped, so a PROSE mention never reads as wiring).

_HARNESSED_JS = _REPO / ".claude" / "workflows" / "project-harnessed.js"


def _harnessed_code() -> str:
    return _strip_js_comments(_HARNESSED_JS.read_text(encoding="utf-8"))


def test_r10_bank_threads_the_plan():
    """Step 5 hands RR.bank the LIVE plan, read from the committed convention — the
    same file step 3 opens for the roster, so resolution and vocabulary agree."""
    code = _harnessed_code()
    assert "plan=json.load(open(${pq(DIR_CLEAN + '/projection_plan.json')}" in code
    assert code.count("plan=json.load(open(") == 2        # step 3 (roster) AND step 5 (bank)
    assert "plan=plan)" in code                            # threaded into the bank call
    # and never the defective shape: a bank call that ends at truncated=
    assert "truncated=bool(d.get('truncated')))))" not in code


def test_the_r10_arms_paths_survive_a_space():
    """A second way the arm was dead as wired: q() emits DOUBLE quotes, which CLOSE the
    shell's own double-quoted `python -c "..."` payload — so 'synthetics papers/<proj>/
    manuscript' split into argv words and the command died with a NameError before any
    reader ran. Every path interpolated into an R10 payload rides pq() (single quotes,
    literal to the shell inside a double-quoted string)."""
    src = _HARNESSED_JS.read_text(encoding="utf-8")
    arm = src[src.index("if (RESTART[rid]) {"):src.index("VERDICT_EOF_R10`")]
    assert "${q(" not in arm                    # no double-quoted interpolation survives
    for var in ("${pq(DIR_CLEAN)}", "${pq(PROJECT)}", "${pq(lockRoundDir)}"):
        assert var in arm, var
    assert "const pq = (s) =>" in src           # and the quoter itself is defined


def test_r10_bank_threads_the_blindness_disclosure():
    """The arm asks for the disclosure and BANKS it: a contaminated read can no longer
    enter the ledger looking like a blind one."""
    code = _harnessed_code()
    assert "DISCLOSE YOUR OWN BLINDNESS" in code           # the arm asks (step 2b)
    assert "blindness=d.get('blindness')" in code          # and banks what it is told
    assert '"blindness": <your step-2b disclosure JSON>' in code   # in the stdin shape


def test_r10_binds_the_project_artefact_and_shows_what_it_bound():
    """Step 1 goes through the plan-aware resolver and PRINTS the bound object, so a
    binding that reaches for an audit sheet is visible in the run itself."""
    code = _harnessed_code()
    assert "RR.artefact_pdf_binding(" in code
    assert "'artefact_pdf': b['pdf']" in code and "'pdf_source': b['source']" in code
    assert "RR.extract_artefact_text(" in code


def test_the_harnessed_arm_is_the_only_r10_driver():
    """The carve-out still holds after these edits: fixedpoint drives no R10 arm."""
    assert "artefact_pdf_binding" not in _strip_js_comments(
        _FIXEDPOINT_JS.read_text(encoding="utf-8"))
