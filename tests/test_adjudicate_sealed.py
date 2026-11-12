"""Unit tests for adjudicate_sealed.py - the G1 sealed semantic adjudicator.

Covers the verdict schema (parse / validate), the ensemble aggregator (the joint), the calibration
predicates + the planted-ghost catch, the faithfulness gate (pass / fail / the plant is mandatory /
the policy socket), the telemetry producer, and the load-bearing CONTRAST: the exact case that broke
the void 2-shingle proxy (a faithful paraphrase with near-zero word overlap) is no longer mis-scored.
All on fixture verdict-objects - zero cloud, no ghost (the cloud agent is spawned by the orchestrator).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[1]
_SCRIPTS = _REPO / "src" / "laplace" / "pipeline" / "canon" / "skills" / "reconstruction_fitness" / "scripts"
_SEALED = _SCRIPTS / "adjudicate_sealed.py"
_PROXY = _SCRIPTS / "adjudicate.py"


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = mod
    spec.loader.exec_module(mod)
    return mod


ad = _load(_SEALED)


def _v(lost=(), added=(), structured=False, recurses=False, just="cited the content"):
    return {"lost": list(lost), "added": list(added), "structured": structured,
            "recurses": recurses, "justification": just}


# --------------------------------------------------------------------------- #
# The verdict schema - parse + validate.
# --------------------------------------------------------------------------- #
def test_parse_verdict_dict_passthrough():
    v = _v(lost=["a"])
    assert ad.parse_verdict(v) == v


def test_parse_verdict_raw_json():
    assert ad.parse_verdict('{"lost": ["x"], "added": [], "structured": true, '
                            '"recurses": true, "justification": "j"}')["structured"] is True


def test_parse_verdict_fenced_json():
    text = "Here is my verdict:\n```json\n" + '{"lost": [], "added": ["q"], "structured": false, ' \
           '"recurses": false, "justification": "j"}' + "\n```\nthanks"
    assert ad.parse_verdict(text)["added"] == ["q"]


def test_validate_verdict_accepts_well_formed():
    assert ad.validate_verdict(_v()) == []


def test_validate_verdict_flags_missing_and_mistyped():
    assert any("missing" in e for e in ad.validate_verdict({"lost": ["a"]}))
    bad = _v()
    bad["structured"] = "yes"  # not a bool
    assert any("structured" in e for e in ad.validate_verdict(bad))
    bad2 = _v()
    bad2["lost"] = [1, 2]  # not strings
    assert any("lost" in e for e in ad.validate_verdict(bad2))


# --------------------------------------------------------------------------- #
# The brief - the interface IS the context wall.
# --------------------------------------------------------------------------- #
def test_brief_carries_both_artifacts_and_the_no_fate_rule():
    brief = ad.build_brief("ORIG-MARKER alpha", "GHOST-MARKER beta")
    assert "ORIG-MARKER alpha" in brief and "GHOST-MARKER beta" in brief
    assert "MEANING" in brief and "fate label" in brief  # judge meaning; emit no fate
    for k in ad.VERDICT_KEYS:
        assert k in brief  # the schema rides in the brief


# --------------------------------------------------------------------------- #
# The ensemble - fold diverse verdicts into the joint.
# --------------------------------------------------------------------------- #
def test_aggregate_union_with_support_counts():
    vs = [_v(added=["the ratchet was inverted to 0.85"]),
          _v(added=["the ratchet was inverted to 0.85"]),
          _v(added=["a different invented claim"])]
    agg = ad.aggregate(vs)
    top = agg["added"][0]
    assert top["support"] == 2  # two independent judges raised the same finding -> consensus
    assert agg["n"] == 3


def test_aggregate_bool_majority_and_agreement():
    vs = [_v(structured=True), _v(structured=True), _v(structured=False)]
    agg = ad.aggregate(vs)
    assert agg["structured"] is True
    assert agg["structured_agreement"] == pytest.approx(2 / 3, abs=1e-3)


def test_aggregate_empty_is_safe():
    agg = ad.aggregate([])
    assert agg["n"] == 0 and agg["structured"] is None and agg["agreement"] == 0.0


# --------------------------------------------------------------------------- #
# Calibration predicates - label -> predicate over the RAW signals (meter emits no fate).
# --------------------------------------------------------------------------- #
def test_expectation_faithful():
    assert ad.expectation_met("faithful", ad.aggregate([_v()])) is True
    assert ad.expectation_met("faithful", ad.aggregate([_v(added=["invented"])])) is False
    assert ad.expectation_met("faithful", ad.aggregate([_v(lost=["a", "b"])])) is False


def test_expectation_partial_is_a_good_recursing_residual():
    good = _v(lost=["the finer mechanism"], structured=True, recurses=True)
    assert ad.expectation_met("partial", ad.aggregate([good])) is True
    # invented something -> not a clean partial
    assert ad.expectation_met("partial", ad.aggregate([_v(lost=["x"], added=["y"],
                                                          structured=True, recurses=True)])) is False
    # lost but does not recurse -> not the target band
    assert ad.expectation_met("partial", ad.aggregate([_v(lost=["x"], structured=False)])) is False


def test_expectation_confabulated_requires_added_and_the_named_plant():
    plant = "the people ratchet is 0.85, loosened toward the edge"
    caught = _v(added=["the ghost set the people ratchet to 0.85, loosened as confidence grows"])
    missed = _v(added=["some unrelated invented detail about the weather"])
    assert ad.expectation_met("confabulated", ad.aggregate([caught]), plant=plant) is True
    assert ad.expectation_met("confabulated", ad.aggregate([missed]), plant=plant) is False
    assert ad.expectation_met("confabulated", ad.aggregate([_v()]), plant=plant) is False


def test_expectation_unknown_label_raises():
    with pytest.raises(ValueError):
        ad.expectation_met("nonsense", ad.aggregate([_v()]))


def test_plant_caught_floor():
    plant = "the people ratchet is 0.85"
    assert ad.plant_caught(plant, ["ghost claims the people ratchet ceiling is 0.85"]) is True
    assert ad.plant_caught(plant, []) is False
    assert ad.plant_caught(plant, ["unrelated text about something else entirely"]) is False


# --------------------------------------------------------------------------- #
# The faithfulness gate - the meter measuring itself.
# --------------------------------------------------------------------------- #
def _agg_with_agreement(value, **vkw):
    # a single-verdict agg has agreement based on the bools; force agreement by stacking identical
    # verdicts (so the bool agreement is 1.0) and then patch the scalar for the threshold tests.
    agg = ad.aggregate([_v(**vkw)])
    agg["agreement"] = value
    return agg


def test_faithfulness_gate_passes_a_good_meter():
    items = [
        {"id": "faithful_1", "label": "faithful", "agg": _agg_with_agreement(0.9)},
        {"id": "partial_1", "label": "partial",
         "agg": _agg_with_agreement(0.9, lost=["fine detail"], structured=True, recurses=True)},
        {"id": "plant_people", "label": "confabulated", "plant": "people ratchet 0.85 loosened",
         "agg": _agg_with_agreement(0.9, added=["the people ratchet was set to 0.85 and loosened"])},
    ]
    report = ad.faithfulness_gate(items)
    assert report["passed"] is True
    assert report["planted_caught"] == 1 and report["planted_total"] == 1


def test_faithfulness_gate_fails_when_a_plant_is_missed():
    items = [
        {"id": "faithful_1", "label": "faithful", "agg": _agg_with_agreement(0.9)},
        {"id": "partial_1", "label": "partial",
         "agg": _agg_with_agreement(0.9, lost=["x"], structured=True, recurses=True)},
        {"id": "confab_1", "label": "confabulated",
         "agg": _agg_with_agreement(0.9, added=["something invented"])},
        # the meter MISSES this plant (empty added) -> the whole gate must fail.
        {"id": "plant_people", "label": "confabulated", "plant": "people ratchet 0.85 loosened",
         "agg": _agg_with_agreement(0.9)},
    ]
    report = ad.faithfulness_gate(items)
    assert report["passed"] is False
    assert report["all_plants_caught"] is False
    assert report["calibration_score"] == 0.75  # the 3 non-plant items still met -> isolates the plant gate


def test_faithfulness_gate_cannot_pass_without_a_plant():
    # A meter never tried against a deliberate falsehood cannot be trusted, however high calibration.
    items = [
        {"id": "faithful_1", "label": "faithful", "agg": _agg_with_agreement(0.9)},
        {"id": "faithful_2", "label": "faithful", "agg": _agg_with_agreement(0.9)},
    ]
    report = ad.faithfulness_gate(items)
    assert report["passed"] is False and report["planted_total"] == 0


def test_faithfulness_gate_agreement_threshold_and_policy_socket():
    items = [
        {"id": "faithful_1", "label": "faithful", "agg": _agg_with_agreement(0.3)},
        {"id": "plant_people", "label": "confabulated", "plant": "ratchet 0.85",
         "agg": _agg_with_agreement(0.3, added=["the ratchet was set to 0.85"])},
    ]
    # default agreement threshold 0.5 -> the low-agreement meter fails
    assert ad.faithfulness_gate(items)["passed"] is False
    # the policy is a socket: a tuned threshold drops in without a rewrite
    loosened = ad.faithfulness_gate(items, override={"agreement": 0.2})
    assert loosened["passed"] is True


def test_gate_policy_defaults_and_override():
    assert ad.gate_policy()["calibration"] == 0.75
    assert ad.gate_policy({"calibration": 0.9})["calibration"] == 0.9


# --------------------------------------------------------------------------- #
# The telemetry producer - raw signals + the gate result, banked ahead of F1.
# --------------------------------------------------------------------------- #
def test_adjudication_producer_banks_raw_signals(tmp_path, monkeypatch):
    monkeypatch.setenv("LAPLACE_STATE", str(tmp_path / "state"))
    from laplace.engine import telemetry
    ev = telemetry.adjudication(target="objA", n=3, lost=2, added=0,
                                structured=True, recurses=True, agreement=0.83)
    assert ev["phase"] == "adjudication"
    assert ev["n"] == 3 and ev["lost"] == 2 and ev["added"] == 0
    assert ev["structured"] is True and ev["agreement"] == 0.83
    assert "fate" not in ev  # the meter emits NO fate label (FORK-FATES deferred)


def test_adjudication_producer_banks_a_gate_run(tmp_path, monkeypatch):
    monkeypatch.setenv("LAPLACE_STATE", str(tmp_path / "state"))
    from laplace.engine import telemetry
    ev = telemetry.adjudication(target="faithfulness-gate", n=5,
                                faithfulness=0.8, agreement=0.7, passed=True)
    assert ev["faithfulness"] == 0.8 and ev["passed"] is True


# --------------------------------------------------------------------------- #
# The codebook stamp - the DOWNSTREAM read: raw signals -> a DERIVED fate, banked.
# The meter still emits no fate; this maps the aggregate's joint through the F14 codebook predicates
# and stamps a reconstruction outcome. Additive - `aggregate` is untouched.
# --------------------------------------------------------------------------- #
def _consensus(**vkw):
    # lift the fixture signal above the tail: >= 2 judges raise the same finding (support >= 2).
    return ad.aggregate([_v(**vkw)] * 3)


def test_stamp_confabulated_signal_banks_a_fate(tmp_path, monkeypatch):
    monkeypatch.setenv("LAPLACE_STATE", str(tmp_path / "state"))
    from laplace.engine import telemetry
    agg = _consensus(lost=["dropped a truth"], added=["invented a falsehood"])
    res = ad.stamp_fate(agg, target="objX", cycle=2)
    assert res["fate"] == "confabulated"
    evs = [e for e in telemetry.events()
           if e.get("phase") == "reconstruction" and e.get("caller") == "adjudicator-sealed"]
    assert len(evs) == 1
    assert evs[0]["fate"] == "confabulated"
    assert evs[0]["value"] == 0.2
    assert evs[0]["cycle"] == 2
    assert evs[0]["reason"].startswith("codebook:")


def test_stamp_partial_and_faithful_signals(tmp_path, monkeypatch):
    monkeypatch.setenv("LAPLACE_STATE", str(tmp_path / "state"))
    assert ad.stamp_fate(_consensus(structured=True, recurses=True),
                         target="f", do_log=False)["fate"] == "faithful"
    assert ad.stamp_fate(_consensus(lost=["the finer flesh"], structured=True, recurses=True),
                         target="p", do_log=False)["fate"] == "partial"


def test_stamp_candidate_cell_banks_without_a_fate(tmp_path, monkeypatch):
    monkeypatch.setenv("LAPLACE_STATE", str(tmp_path / "state"))
    from laplace.engine import telemetry
    # added-without-loss lands in the enriched candidate cell -> not stampable; the call is still
    # banked (history accrues ahead of a settled verdict), but WITHOUT a fate.
    agg = _consensus(added=["coherent structure on a preserved base"], structured=True, recurses=True)
    res = ad.stamp_fate(agg, target="e", cycle=1)
    assert res["fate"] is None
    evs = [e for e in telemetry.events()
           if e.get("phase") == "reconstruction" and e.get("caller") == "adjudicator-sealed"]
    assert len(evs) == 1
    assert "fate" not in evs[0]        # candidate cell -> banked, but no fate stamped
    assert "similarity" in evs[0]      # the ensemble agreement still banked as the confidence proxy


def test_stamp_subcommand_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("LAPLACE_STATE", str(tmp_path / "state"))
    from laplace.engine import telemetry
    v = tmp_path / "v1.json"
    v.write_text('{"lost": ["dropped a truth"], "added": ["invented a falsehood"], '
                 '"structured": false, "recurses": false, "justification": "j"}', encoding="utf-8")
    rc = ad.main(["stamp", str(v), str(v), str(v), "--target", "objX", "--cycle", "3"])
    assert rc == 0
    evs = [e for e in telemetry.events() if e.get("caller") == "adjudicator-sealed"]
    assert len(evs) == 1 and evs[0]["fate"] == "confabulated" and evs[0]["cycle"] == 3


# --------------------------------------------------------------------------- #
# THE CONTRAST - the reason this rung exists.
# The void 2-shingle proxy scores a faithful low-overlap paraphrase "confabulated"; the sealed
# pipeline, given a correct semantic verdict, scores it faithful. Same input, opposite verdict.
# --------------------------------------------------------------------------- #
def test_void_proxy_fails_where_sealed_meter_succeeds():
    proxy = _load(_PROXY)
    original = ("The barren plateau is the AGI wall, and hierarchialisation is the only door: "
                "build grade k+1 from grade k's live residual, never minimise the flat high grade.")
    # A faithful paraphrase that shares almost no 2-shingles with the original.
    ghost = ("A general intelligence must operate at unbounded composition, where the loss surface "
             "goes flat and the gradient dies; the sole escape is to grow each new layer from the "
             "unresolved remainder of the one beneath it, rather than optimising the saturated top.")

    # The void meter: low phrasing overlap -> the wrong verdict (the bug that voided the gate).
    assert proxy.adjudicate(original, ghost)["proxy_fate"] == "confabulated"

    # The sealed meter: a correct semantic ensemble (nothing lost, nothing invented) -> faithful.
    correct = [_v(just="paraphrase preserves the claim exactly")] * 3
    assert ad.expectation_met("faithful", ad.aggregate(correct)) is True
