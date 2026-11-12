"""The model FLOOR: the conjugate of the 2026-07-11 ceiling (B17).

The ceiling asks "did a stage run richer than the orchestrator". The floor asks the
question a measured arm turns on: "did EVERY stage run at the tier the arm claims".
Four seams, exercised here: the pin composes with the clamp in the one safe order; the
arm profile is a lawful, allowlisted policy that moves BOTH model policies; the audit
sees a below-floor stamp in source AND in a completed run; and the one bootstrap stage
that structurally cannot obey is exempt BY LABEL, from the floor only, with a row.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from laplace.representation import custody_mode
from laplace.engine import descent
from laplace.web import dials_surface as ds
from laplace.pipeline import dials
from laplace.pipeline import dials, schema
from laplace.pipeline.dispatch import compile_dispatch

ROOT = Path(__file__).resolve().parents[1]
ARM_PROFILE = "dials-arm-opus.yaml"


def _load_audit():
    spec = importlib.util.spec_from_file_location(
        "audit_dispatch_models", ROOT / "scripts" / "audit_dispatch_models.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("audit_dispatch_models", mod)
    spec.loader.exec_module(mod)
    return mod


def _plant_source(tmp_path: Path, name: str, body: str) -> Path:
    f = tmp_path / name
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(body, encoding="utf-8")
    return f


# THE DISPATCH PRECONDITION (2026-09-15). compile_dispatch is a hard gate before any
# compiler action: every packet carries an exact typed descent of its node - content
# verified by hash, read-only, no transition claim - or it refuses with
# MISSING_RECONSTRUCTION. That law arrived after this floor test was written and is
# orthogonal to the model stamp, so these two seams satisfy it the way their conjugate
# ceiling test (tests/test_dispatch_model_ceiling.py) already does: a REAL descent over
# a real repository node, never a hand-built dict. The node is incidental to the floor -
# the WORKER is what selects the tier - so any exact node serves.
FLOOR_NODE = "README.md"


def _exact_node_reconstruction(goal: str) -> dict:
    """An exact typed descent of FLOOR_NODE, admissible under the custody-off gate."""
    rec = descent.descend(kind="repository-file", reference=FLOOR_NODE, goal=goal,
                          record_telemetry=False)
    assert rec["content_status"] == "COMPLETE", rec
    rec.update(goal=goal, authority_write="none")
    return rec


def _plant_manifest(tmp_path: Path, rows: list[dict]) -> Path:
    f = tmp_path / "rounds" / "harnessed" / "agents_manifest.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(rows), encoding="utf-8")
    return f


# --- the pin ---------------------------------------------------------------

def test_pin_raises_only_and_composes_with_the_clamp():
    # a floor RAISES; it never demotes a stage that already asks for more
    assert schema.pin_model("sonnet", "opus") == "opus"
    assert schema.pin_model("haiku", "sonnet") == "sonnet"
    assert schema.pin_model("opus", "sonnet") == "opus"
    # None is inert: the per-worker default stands, byte-identical to pre-pin
    assert schema.pin_model("sonnet", None) == "sonnet"
    # PIN THEN CLAMP: the ceiling law is applied last and still wins
    assert schema.clamp_model(schema.pin_model("haiku", "opus")) == "opus"
    assert schema.clamp_model(schema.pin_model("unknown-tier", "opus")) == "opus"
    # a mistyped arm policy fails loudly rather than running at the default tier
    with pytest.raises(ValueError):
        schema.pin_model("sonnet", "opus-max")


def test_clamp_semantics_are_untouched_by_the_pin():
    # the pin is a SEPARATE organ: clamp_model's pass-through contract, which
    # readability_gate and pipeline_surface depend on, must not have moved
    assert schema.clamp_model("haiku") == "haiku"
    assert schema.clamp_model("sonnet") == "sonnet"
    assert schema.clamp_model("opus-max") == schema.MAX_MODEL


# --- the arm profile -------------------------------------------------------

def test_arm_profile_is_allowlisted_and_pins_every_seat():
    path = dials.profile_path(ARM_PROFILE)          # a non-allowlisted name raises here
    assert path.is_file()
    d = dials.load_dials(path)
    assert d["version"] == "dials-arm-opus"
    # the JS leg's policy: every role at the apex (the organs read roles.*.model)
    assert {r["model"] for r in d["roles"].values()} == {"opus"}
    # the python leg's policy: the floor + the verbatim id
    assert dials.model_pin(d) == "opus"
    assert dials.model_id(d) == "claude-opus-5"


def test_the_live_profile_stays_inert():
    # parallel-artefact discipline: the arm is a NEW file, not an edit of the live
    # calibration. dials-v1 must carry no pin, so nothing outside an arm run moves.
    assert dials.model_pin(dials.load_dials()) is None
    assert dials.model_id(dials.load_dials()) is None
    assert dials.defaults()["dispatch"] == {"model_pin": None, "model_id": None}


def test_the_four_organs_read_the_same_pinned_profile():
    # the organs take every stage's tier from DIALS.roles[role] and their dials path
    # from the --dials argument, so pointing them at the arm profile pins the JS leg
    # with no script edit. This asserts that wiring still holds.
    for name in ("project-harnessed.js", "project-pipeline.js",
                 "project-fixedpoint.js", "project-staged.js"):
        src = (ROOT / ".claude" / "workflows" / name).read_text(encoding="utf-8")
        assert "DIALS.roles[role]" in src, name
        assert "A.dials" in src, name


# --- the missing wire: compile_dispatch under the arm ----------------------

def test_compile_dispatch_stamps_opus_for_a_sonnet_default_worker(monkeypatch):
    # structure's schema.WORKER_MODEL default is sonnet — the exact case the pin
    # exists for. Without a profile the constant stands; under the arm it does not.
    assert schema.WORKER_MODEL["structure"][0] == "sonnet"
    monkeypatch.setattr(custody_mode, "is_off", lambda *_: True)
    goal = "resolve the structure"
    rec = _exact_node_reconstruction(goal)
    plain = compile_dispatch(FLOOR_NODE, goal, worker="structure",
                             project="paper_falqon", reconstruction=rec)
    assert "error" not in plain, plain
    assert plain["reconstruction_admission"]["admission_result"]["status"] == "ADMITTED"
    assert plain["model"] == "sonnet"
    assert "model_id" not in plain

    armed = compile_dispatch(FLOOR_NODE, goal, worker="structure",
                             project="paper_falqon", dials_profile=ARM_PROFILE,
                             reconstruction=rec)
    assert "error" not in armed, armed
    assert armed["model"] == "opus"
    # the tier is what the audit enforces; the id is what the ledger proves
    assert armed["model_id"] == "claude-opus-5"
    # effort is NOT pinned — the arm moves one variable
    assert armed["effort"] == plain["effort"]


def test_the_pinned_stamp_still_obeys_the_ceiling(monkeypatch):
    monkeypatch.setattr(custody_mode, "is_off", lambda *_: True)
    goal = "render"
    armed = compile_dispatch(FLOOR_NODE, goal, worker="render",
                             project="paper_falqon", dials_profile=ARM_PROFILE,
                             reconstruction=_exact_node_reconstruction(goal))
    assert "error" not in armed, armed
    rank = {m: i for i, m in enumerate(schema.MODEL_RANK)}
    assert rank[armed["model"]] <= rank[schema.MAX_MODEL]


# --- the audit: floor mode, source leg -------------------------------------

def test_planted_sonnet_is_clean_under_the_ceiling_and_red_under_the_floor(tmp_path):
    mod = _load_audit()
    _plant_source(tmp_path, "scripts/wf_arm.mjs",
                  "const a = await agent('x', {model: 'sonnet'})\n")
    assert mod.audit(tmp_path) == []
    red = mod.audit(tmp_path, floor="opus")
    assert [(r.token, r.kind) for r in red] == [("sonnet", "source")]


def test_recursive_globs_reach_a_nested_dispatch_site(tmp_path):
    # the pre-B17 globs were non-recursive: a dispatch site one directory down was
    # invisible, and the audit's green was a false green.
    mod = _load_audit()
    _plant_source(tmp_path, "scripts/workflows/deep.workflow.mjs",
                  "await agent('x', {model: 'sonnet'})\n")
    _plant_source(tmp_path, "experiments/deep/x.js",
                  "await agent('x', {model: 'sonnet'})\n")
    assert mod.audit(tmp_path) == []
    assert len(mod.audit(tmp_path, floor="opus")) == 2


def test_the_formerly_invisible_real_sites_are_scanned():
    mod = _load_audit()
    scanned = {str(f.relative_to(ROOT)) for f in mod._iter_files(ROOT)}
    for missed in ("scripts/workflows/falqon_phase_b.workflow.mjs",
                   "workflows/hello_fidelity_test.mjs",
                   "workflows/hello_generator.mjs",
                   "experiments/plateau_falsifier.workflow.js"):
        assert missed in scanned, missed


def test_vendored_trees_are_never_scanned(tmp_path):
    mod = _load_audit()
    _plant_source(tmp_path, "scripts/node_modules/pkg/index.js",
                  "await agent('x', {model: 'sonnet'})\n")
    assert mod.audit(tmp_path, floor="opus") == []


# --- the audit: floor mode, run leg ----------------------------------------

def test_planted_sonnet_row_in_a_run_manifest_is_clean_then_red(tmp_path):
    mod = _load_audit()
    _plant_manifest(tmp_path, [
        {"ordinal": 0, "label": "builder#1", "phase": "Fix", "model": "opus"},
        {"ordinal": 1, "label": "lock:R9#1", "phase": "Lock", "model": "sonnet"},
    ])
    assert mod.audit(tmp_path, run=tmp_path) == []
    red = mod.audit(tmp_path, floor="opus", run=tmp_path)
    assert [(r.locus, r.label, r.token, r.kind) for r in red] == [
        (1, "lock:R9#1", "sonnet", "run")]


def test_run_leg_reads_the_nested_wave_shape(tmp_path):
    # the loop runners bank a different shape (waves, worker rather than label);
    # the walk is structural so a second manifest shape is covered on arrival.
    mod = _load_audit()
    f = tmp_path / "loops" / "loop_4" / "dispatch_manifest.json"
    f.parent.mkdir(parents=True)
    f.write_text(json.dumps({"loop": 4, "waves": [
        {"wave": 1, "worker": "derive", "model": "opus", "stamp": "explicit"},
        {"wave": 2, "worker": "mint", "model": "haiku", "stamp": "explicit"}]}),
        encoding="utf-8")
    assert mod.audit(tmp_path, run=tmp_path) == []
    red = mod.audit(tmp_path, floor="opus", run=tmp_path)
    assert [(r.label, r.token) for r in red] == [("mint", "haiku")]


def test_a_versioned_model_id_resolves_to_its_tier(tmp_path):
    # run ledgers record exact ids; an id the audit cannot read is one it cannot
    # enforce. A provider component is REQUIRED — 'opus-max' stays unknown.
    mod = _load_audit()
    assert mod.tier_of("claude-opus-5") == "opus"
    assert mod.tier_of("us.anthropic.claude-sonnet-4-5-20250929") == "sonnet"
    assert mod.tier_of("claude-haiku-4-5-20251001") == "haiku"
    assert mod.tier_of("opus") == "opus"
    assert mod.tier_of("opus-max") is None
    _plant_manifest(tmp_path, [{"ordinal": 0, "label": "b", "model": "claude-opus-5"},
                               {"ordinal": 1, "label": "c", "model": "claude-sonnet-5"}])
    red = mod.audit(tmp_path, floor="opus", run=tmp_path)
    assert [r.token for r in red] == ["claude-sonnet-5"]


def test_an_unparseable_manifest_is_a_violation_not_a_pass(tmp_path):
    mod = _load_audit()
    f = tmp_path / "rounds" / "agents_manifest.json"
    f.parent.mkdir(parents=True)
    f.write_text("{not json", encoding="utf-8")
    assert len(mod.audit(tmp_path, run=tmp_path)) == 1


# --- the one exemption, by label -------------------------------------------

def test_bootstrap_is_floor_exempt_with_an_explicit_row_in_source(tmp_path):
    mod = _load_audit()
    _plant_source(tmp_path, ".claude/workflows/organ.js",
                  "const BOOTSTRAP_MODEL = 'haiku'\n"
                  "await agent('x', {label: 'load-dials', model: BOOTSTRAP_MODEL})\n")
    rep = mod.scan(tmp_path, floor="opus")
    assert rep.violations == []
    assert [(r.token, r.label) for r in rep.exemptions] == [("haiku", "load-dials")]


def test_bootstrap_is_floor_exempt_with_an_explicit_row_in_a_run(tmp_path):
    mod = _load_audit()
    _plant_manifest(tmp_path, [
        {"ordinal": 0, "label": "load-dials", "phase": "", "model": "haiku"},
        {"ordinal": 1, "label": "builder#1", "phase": "Fix", "model": "opus"},
    ])
    rep = mod.scan(tmp_path, floor="opus", run=tmp_path)
    assert rep.violations == []
    assert [(r.locus, r.label, r.token) for r in rep.exemptions] == [
        (0, "load-dials", "haiku")]


def test_the_exemption_is_from_the_floor_never_the_ceiling(tmp_path):
    mod = _load_audit()
    _plant_manifest(tmp_path, [
        {"ordinal": 0, "label": "load-dials", "model": "opus-max"}])
    rep = mod.scan(tmp_path, floor="opus", run=tmp_path)
    assert [r.token for r in rep.violations] == ["opus-max"]
    assert rep.exemptions == []


def test_the_exemption_cannot_widen_past_the_one_named_stage(tmp_path):
    mod = _load_audit()
    assert mod.FLOOR_EXEMPT_LABELS == frozenset({"load-dials"})
    _plant_manifest(tmp_path, [
        {"ordinal": 0, "label": "load-dials-and-more", "model": "haiku"}])
    assert len(mod.audit(tmp_path, floor="opus", run=tmp_path)) == 1


def test_an_unknown_floor_tier_raises(tmp_path):
    mod = _load_audit()
    with pytest.raises(ValueError):
        mod.scan(tmp_path, floor="opus-5")
