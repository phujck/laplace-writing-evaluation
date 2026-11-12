"""Tests for the SOURCE-DELTA reader (readers.source_delta)."""
from __future__ import annotations

from laplace.pipeline.readers import source_delta as SD
from laplace.pipeline import schema


def test_dropped_motivation_is_lost():
    source = ("The register holds the estimate. Because no measurement intervenes "
              "between the feedback layers, no state re-preparation is ever required "
              "and the loop stays coherent throughout the run.")
    # projection keeps the fact but drops the WHY
    projection = "The register holds the estimate. The loop stays coherent."
    res = SD.read_source_delta(source, projection,
                              source_is_text=True, projection_is_text=True)
    assert res["pass"] is False
    kinds = {f["kind"] for f in res["findings"]}
    assert "source-motivation-lost" in kinds
    lost = [f for f in res["findings"] if f["kind"] == "source-motivation-lost"][0]
    assert "Because no measurement" in lost["primary"]     # verbatim primary record


def test_surviving_reasoning_is_clean():
    unit = ("Because the sign of the feedback coefficient is chosen to oppose the "
            "gradient direction, the energy is guaranteed to decrease each layer.")
    source = "First a setup. " + unit
    projection = "First a setup sentence here. " + unit    # survives verbatim
    res = SD.read_source_delta(source, projection,
                              source_is_text=True, projection_is_text=True)
    assert not any("Because the sign" in f["primary"] for f in res["findings"]), \
        res["findings"]


def test_argument_move_kind():
    source = ("Setup. The volume scales linearly in the layer count rather than "
              "quadratically, which means the wall clock collapses to hours.")
    projection = "Setup only, nothing about scaling here."
    res = SD.read_source_delta(source, projection,
                              source_is_text=True, projection_is_text=True)
    kinds = {f["kind"] for f in res["findings"]}
    assert kinds & {"source-argument-lost", "source-connective-lost"}


def test_bare_facts_not_flagged():
    # no reasoning marker -> not a reasoning unit -> never a finding, even if absent
    source = "The lattice has thirty sites. The qubit count is sixty."
    projection = "Completely different prose about apples and oranges entirely."
    res = SD.read_source_delta(source, projection,
                              source_is_text=True, projection_is_text=True)
    assert res["present"]["source_reasoning_units"] == 0
    assert res["findings"] == []


def test_present_census_and_route():
    source = ("Because the estimate is written coherently, no restart is needed, "
              "and this is why the wall clock falls so far below the sampling route.")
    res = SD.read_source_delta(source, "unrelated text",
                              source_is_text=True, projection_is_text=True)
    assert res["present"]["source_reasoning_units"] >= 1
    for f in res["findings"]:
        assert f["route"] == SD.FINDING_KIND_STAGE[f["kind"]]
        assert f["reader"] == "source_delta"


def test_kinds_registered_in_schema():
    schema.register_component_kinds()
    for row in SD.finding_kinds_manifest():
        assert row["kind"] in schema.KIND_TO_WORK, row["kind"]
