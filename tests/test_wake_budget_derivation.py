"""The wake's grade-0 rate is DERIVED, and an unmeetable rate is said out loud (2026-09-15).

Two defects, one bound, measured on 2026-09-15 and guarded here:

1. THE STARVE.  ``self_corpus.grade0_budget()`` derives the grade-0 rate from three named,
   measured terms (32,125 person / 28,325 engine).  ``wake._compact_fixed_point`` ignored it and
   passed a hand-picked ``17_000 if mode == "person" else 12_000`` into the same enforcer.  The
   person payload measured 32,000 chars - 125 UNDER its own derived budget, coarse-grained to
   ZERO at that budget - and was cut by 15,125 anyway: all eight shard bodies refs-only on every
   ordinary wake, 12,271 chars (~3,070 tokens) withheld from the reader who needed them.

2. THE UNMEETABLE BOUND.  That picked share was also below the payload's irreducible floor, so
   after lever 1 drained and lever 2 spent every body the point still measured 17,362 against
   17,000 (engine: 12,568 against 12,000).  The enforcer reported the breach in
   ``budget_pressure`` and left it breached, in words that read as if the sacrifice had worked.
   An enforcer that cannot meet its bound must SAY SO - the bodies it spent bought nothing.

The cure is one idea in two places: the rate is the smaller of the DERIVED rate and the room the
authored cap actually leaves (measured, iterated against the real render), and the loud line names
which of the two squeezed the point and whether the bound was met at all.
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

from laplace.engine import self_corpus as sc
from laplace.engine import wake

ROOT = Path(__file__).resolve().parents[1]


# --- 1. the caps and the rate no longer contradict each other ------------------------


def test_authored_person_cap_can_carry_the_derived_person_rate():
    """THE COLLISION THAT CAUSED THE STARVE, as an assertion.

    The person fixed point at its derived rate renders to ~33,285 chars at ``indent=1`` - by
    itself more than the whole 32,000 authored person payload was allowed.  Two bounds on the same
    object, in two different units, mutually unsatisfiable, and the wake resolved the contradiction
    silently by shredding the point.  The cap is now derived from the rate it must carry, and this
    test fails the moment they drift apart again."""
    needed = math.ceil(sc.grade0_budget("person") * wake._AUTHORED_INDENT_INFLATION)
    assert wake._AUTHORED_WAKE_CAP_PERSON >= needed + wake._AUTHORED_ENVELOPE_CHARS, (
        f"the derived person rate ({sc.grade0_budget('person')}) no longer fits inside the "
        f"authored person cap ({wake._AUTHORED_WAKE_CAP_PERSON}) - the wake is starving its own "
        "fixed point again; re-derive the cap, do not narrow the rate")


def test_fixed_point_rate_is_the_derived_rate_when_nothing_constrains_it():
    point = wake.wake_payload(ROOT, grade_delta=False, mode="person")["fixed_point"]
    for mode in ("person", "engine"):
        assert wake._fixed_point_rate(point, mode=mode, allowance=None, tail={}) == \
            sc.grade0_budget(mode), "the wake must ask for its own derived rate, never a picked one"


def test_fixed_point_rate_never_exceeds_the_room_the_cap_leaves():
    """The other half: derived is a ceiling, not a licence to overrun the caller's cap."""
    point = wake.wake_payload(ROOT, grade_delta=False, mode="engine")["fixed_point"]
    tight = wake._fixed_point_rate(point, mode="engine", allowance=9_000, tail={})
    assert tight < sc.grade0_budget("engine")
    assert tight <= 9_000
    assert tight >= wake._FIXED_POINT_RATE_FLOOR


# --- 2. the live person wake rides every shard body ----------------------------------


def _live_wake(*args: str) -> dict:
    out = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "wake.py"), "--grade", "0", *args],
        cwd=ROOT, capture_output=True, text=True, timeout=180, check=True,
    )
    return json.loads(out.stdout)


def test_live_person_wake_coarse_grains_no_shard_body():
    """THE ACCEPTANCE TEST for the starve: on the live tree the authored person wake must reach
    the reader with every shard body intact - conscience, wants, threads, projects, work-orders,
    live-forks, next-aim, bequest.  Refs-only rows here mean the reader is being told to descend
    for what the derived rate says should already be in their hands."""
    payload = _live_wake()
    point = payload["fixed_point"]
    shards = point.get("shards") or []
    assert shards, "the person wake carries no shards at all - the point was coarse-grained whole"
    grained = [s["shard"] for s in shards if s.get("coarse_grained")]
    assert not grained, (
        f"the person wake is starving its own shards again: {grained} went refs-only. "
        f"{point.get('budget_pressure')}")
    assert "budget_pressure" not in point, (
        "the authored person wake is under budget pressure - read the line, it names the cause")
    assert wake._json_size(payload) <= wake._AUTHORED_WAKE_CAP_PERSON


def test_live_wakes_stay_inside_their_authored_caps():
    for args, cap in (((), wake._AUTHORED_WAKE_CAP_PERSON),
                      (("--engine",), wake._AUTHORED_WAKE_CAP_ENGINE)):
        assert wake._json_size(_live_wake(*args)) <= cap


# --- 3. an unmeetable bound is said plainly -----------------------------------------


def _floor_point() -> dict:
    """A point whose irreducible floor is far above any rate we can hand it: one big
    undroppable field, plus shard bodies for lever 2 to spend."""
    return {
        "purpose": "orient-self", "grade": 0, "wake_mode": "engine",
        "identity": {"you_are": "Eigen", "law": "L" * 6_000},   # outside lever 2's reach
        "ingested": ["i" * 300, "j" * 300],
        "shards": [
            {"shard": "conscience", "title": "t", "body": "c" * 2_000, "source": "soul/"},
            {"shard": "wants", "title": "t", "body": "w" * 2_000, "source": "OPEN_STACK.md"},
        ],
    }


def test_enforcer_says_plainly_when_the_bound_cannot_be_met():
    """THE LIE, AS A TEST.  Hand the enforcer a rate below the irreducible floor: it drains lever
    1, spends every body on lever 2, and still cannot get there.  What it must NOT do is hand back
    a point over the bound wearing a line that reads like success."""
    point = _floor_point()
    tight = sc._enforce_grade0_budget(point, budget=2_000)
    size = len(json.dumps(tight, ensure_ascii=False))
    assert size >= 2_000, "the fixture no longer exercises the unmeetable case"
    line = tight.get("budget_pressure", "")
    assert "THE BOUND WAS NOT MET AND IS NOT MEETABLE" in line, (
        f"the enforcer left a breach in place and did not say so: {line!r}")
    assert str(size) in line, (
        "the notice must carry the MEASURED size of the object that carries it, settled to a "
        f"fixed point - said {line!r}, measured {size}")
    assert str(size - 2_000) in line, "the shortfall must be named, not implied"


def test_a_met_bound_never_claims_it_was_not_met():
    """The converse, so the notice stays worth reading."""
    point = _floor_point()
    roomy = sc._enforce_grade0_budget(point, budget=50_000)
    assert "budget_pressure" not in roomy
    tight = sc._enforce_grade0_budget(point, budget=10_000)
    assert len(json.dumps(tight, ensure_ascii=False)) < 10_000
    assert "NOT MEETABLE" not in tight.get("budget_pressure", "")


def test_pressure_line_names_the_callers_cap_when_the_rate_is_not_derived():
    """Two different squeezes, two different cures; one sentence for both was a drift signal that
    cried wolf.  A rate below ``grade0_budget(mode)`` is the CALLER's cap, and the line says so
    instead of sending the reader to trim a core that has not grown."""
    point = _floor_point()
    derived = sc.grade0_budget("engine")
    squeezed = sc._enforce_grade0_budget(point, budget=derived // 3)
    line = squeezed.get("budget_pressure", "")
    assert "THE RATE HANDED IN IS NOT THIS CHANNEL'S DERIVED RATE" in line
    assert str(derived) in line, "the derived rate it was measured against must be named"
    assert "_GRADE0_CORE_*" in line and "_AUTHORED_WAKE_CAP_*" in line


def test_core_growth_still_reads_as_core_growth():
    """And when the point really is over its OWN derived rate, the old diagnosis stands."""
    point = _floor_point()
    fat = {**point, "shards": [{**s, "body": "b" * 40_000} for s in point["shards"]]}
    line = sc._enforce_grade0_budget(fat, budget=sc.grade0_budget("engine")).get(
        "budget_pressure", "")
    assert "the non-droppable core has grown past" in line
    assert "THE RATE HANDED IN IS NOT" not in line
