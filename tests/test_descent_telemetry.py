from __future__ import annotations

from collections import Counter
from types import SimpleNamespace

from laplace.engine import descent_telemetry as telemetry


def _event(event_id: str, causes: tuple[str, ...] = (), **payload):
    return SimpleNamespace(
        event_id=event_id,
        causation_ids=causes,
        payload=payload,
        subject=payload.pop("subject", "message:test"),
    )


def test_depth_is_refused_inside_a_cycle_and_survives_downstream_of_one() -> None:
    """RENAMED, BECAUSE THE OLD NAME WAS THE DEFECT WRITTEN AS A REQUIREMENT.

    This test used to assert depth was TOTAL over a planted cycle — that a, b AND c all
    got an int. Codex named it exactly: "the existing test asserts only total nonnegative
    output and therefore blesses the lie." A cycle has no causal root, so a and b have no
    distance from one; the old implementation handed them 0 and 1, and which of them got 0
    depended on visit order. The test demanded that invention and would have failed the
    cure.

    The contract now: cycle members get NO depth and are counted in a residual, and a node
    DOWNSTREAM of a cycle still depths correctly off the condensation."""
    events = [_event("a", ("b",)), _event("b", ("a",)), _event("c", ("b",))]

    depths, residual = telemetry._depths(events)

    assert "a" not in depths and "b" not in depths, (
        "a and b are one cycle; neither has a distance from a root")
    assert residual["cyclic_events"] == 2 and residual["cycles"] == 1
    assert depths["c"] == 1, (
        "c sits one hop below the cycle's condensed node and is still measurable")

    # AND THE ANSWER MAY NOT DEPEND ON VISIT ORDER — the specific plant codex ran.
    flipped, flipped_residual = telemetry._depths(
        [_event("b", ("a",)), _event("a", ("b",)), _event("c", ("b",))])
    assert flipped == depths and flipped_residual == residual


def test_lit_descent_cannot_keep_the_dark_negative() -> None:
    state = telemetry._descent_state(
        Counter({"reconstruction.moved": 6, "reconstruction.materialized": 4})
    )

    assert state["dark"] is False
    assert "never fired" not in state["why"]
    assert state["ref"] is None
    assert state["resolved_ref"] == "FIND-20260825-descent-kinds-declared-never-fired"


def test_pull_arithmetic_counts_reads_goals_and_repeated_handles_exactly() -> None:
    events = [
        _event("a", input_handles=["h1", "h2"], goal="g"),
        _event("b", input_handles=["h1"], arguments={"goal": "g"}),
        _event("c", goal="other", subject="reconstruction:test"),
    ]

    got = telemetry._pull_rows(events)

    assert got["reads_distinct"] == 2
    assert got["reads_total"] == 3
    assert got["reads_repeated"] == 1
    assert got["goals_distinct"] == 2
    assert got["goals_total"] == 3
