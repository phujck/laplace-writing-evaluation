"""The swap, live: the query-conditioned residual in the seat usage-count held.

His pre-registration conditioned the promoter's unfreeze on the closure-residual signal
REPLACING usage-count - not on the replay merely measuring well. The replay is banked
(``evidence/FITNESS_SWAP_REPLAY_2026-08-20/query_conditioned/``, 4 of 12 flips against a
bar of 4). These tests are what makes the replacement real and keeps it honest:

  * **polarity** - D1 (PV-20260820T223000Z) says HIGH residual = DEMANDS INVESTMENT, so R
    enters fitness positively. The naive inverse (``1 - R``, "reachable is good") is the
    opposite ruling, and every polarity test here fails under it. That is the point: the
    easy mistake is the one worth a red.
  * **parity** - the 12 historical transitions, replayed through the LIVE fitness function,
    reproduce the banked flip set exactly. If the wiring ever stops carrying the signal the
    replay measured, the number his bar was read against stops being about this code.
  * **the invisible-but-good class** - idea_foundry and reconciler, deprecated for a
    silence their own claimed tasks explain (best ranks 371 and 229). They are the reason
    the swap exists, and they must read as demanding investment, never as demote.

Nothing here loads a model or a network: the residuals are read from the banked bundle and
the banked store, which is exactly how the live decision path reads them.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from laplace.engine import assess

ROOT = Path(__file__).resolve().parents[1]
QC = ROOT / "evidence/FITNESS_SWAP_REPLAY_2026-08-20/query_conditioned"
FLIPS = QC / "flips.json"

# The four the replay flipped, named here so a silent change to the bundle cannot quietly
# re-write what "4 of 12" meant.
THE_FOUR = {"idea_foundry", "reconciler", "session_closer", "voice_corpus_reader"}

# A signal row with no telemetry at all: every other term sits at its neutral default, so
# only the swapped signal moves the fitness. This is the swap isolated, which is what the
# registered mapping asks for - "only the ordering decides".
NEUTRAL_SIG = {
    "usage": 0, "offered": 0, "verify_pass": 0, "verify_total": 0,
    "exec_ok": 0, "exec_total": 0, "feedback": 0, "retention_obs": [],
}


def _sig(**over):
    return {**NEUTRAL_SIG, **over}


@pytest.fixture(scope="module")
def replay():
    payload = json.loads(FLIPS.read_text(encoding="utf-8"))
    return payload["primary_as_prior_lane_classified"]


# --- polarity: D1, not the naive inverse -----------------------------------------------

def test_the_residual_sits_in_the_seat_usage_count_held():
    """Same weight, new occupant - and usage no longer moves the fitness at all."""
    assert assess.W_RESIDUAL == 0.35
    assert not hasattr(assess, "W_USAGE"), "the old signal must not still have a weight"
    quiet = assess._fitness(_sig(usage=0), residual=0.99)
    busy = assess._fitness(_sig(usage=40), residual=0.99)
    assert quiet["fitness"] == busy["fitness"], "usage-count still moves fitness"
    assert busy["usage_norm"] == 1.0 and quiet["usage_norm"] == 0.0


def test_polarity_is_demands_investment_and_not_the_naive_inverse():
    """High R = the skill's own tasks cannot route to it = demands investment = LIFTS
    fitness, exactly as a high usage count used to. Under ``1 - R`` this inverts."""
    unreachable = assess._fitness(NEUTRAL_SIG, residual=0.9998)
    reachable = assess._fitness(NEUTRAL_SIG, residual=0.7371)
    assert unreachable["fitness_exact"] > reachable["fitness_exact"]
    # and the term is the residual itself, at its full weight
    assert unreachable["fitness_exact"] - reachable["fitness_exact"] == pytest.approx(
        assess.W_RESIDUAL * (0.9998 - 0.7371)
    )


def test_an_unknown_residual_is_neutral_and_says_so():
    """A skill with no banked measurement must not be scored as if it had one. Neutral,
    flagged, and never guessed - the same discipline `_recently_touched` keeps for git."""
    unknown = assess._fitness(NEUTRAL_SIG, residual=None)
    assert unknown["residual"] is None and unknown["residual_known"] is False
    assert unknown["fitness_exact"] == pytest.approx(
        assess._fitness(NEUTRAL_SIG, residual=0.5)["fitness_exact"]
    )


def test_usage_count_survives_as_a_reported_diagnostic():
    """Demoted, not deleted: the incumbent's own number is still computed beside the new
    one, which is what lets a disagreement be seen instead of inferred."""
    # every non-swapped term at its neutral default: quality, feedback and retention all
    # unknown => 0.5 each, so the rest of the sum is a fixed 0.325.
    rest = (assess.W_QUALITY + assess.W_FEEDBACK + assess.W_RETENTION) * 0.5
    row = assess._fitness(_sig(usage=40), residual=0.80)
    assert row["usage_norm"] == 1.0
    assert row["usage_fitness"] == pytest.approx(round(assess.W_RESIDUAL * 1.0 + rest, 3))
    assert row["fitness"] == pytest.approx(round(assess.W_RESIDUAL * 0.80 + rest, 3))
    assert row["usage_fitness"] != row["fitness"]


def test_the_exact_fitness_survives_the_rounding_the_display_does():
    """R differs in the 4th decimal across the population, so a 3-dp round makes ties out
    of the ordering the signal's whole content lives in. Anything that ranks reads exact."""
    a = assess._fitness(NEUTRAL_SIG, residual=0.999034)
    b = assess._fitness(NEUTRAL_SIG, residual=0.998646)
    assert a["fitness"] == b["fitness"], "the 3-dp display is expected to collapse these"
    assert a["fitness_exact"] > b["fitness_exact"], "the ordering must survive anyway"


# --- parity: the 12, replayed through the LIVE fitness ---------------------------------

def _swap_through_live_fitness(transitions):
    """The registered mapping (definition.md 6), driven by the live fitness function.

    Order the transitions by what `assess._fitness` now returns - every other signal held
    at neutral, so the residual is the only thing moving - and hand PROMOTE to the top `m`,
    where `m` is the number the incumbent promoted. Only the ordering decides.
    """
    scored = [
        (assess._fitness(NEUTRAL_SIG, t["residual"])["fitness_exact"], t["skill"], t)
        for t in transitions
    ]
    scored.sort(key=lambda row: (-row[0], row[1]))
    m = sum(1 for t in transitions if t["banked"] == "PROMOTE")
    out = []
    for i, (_, _, t) in enumerate(scored):
        out.append({**t, "live_swapped": "PROMOTE" if i < m else "DEPRECATE"})
    return out, m


def test_the_twelve_replay_through_the_live_fitness_to_the_banked_decisions(replay):
    live, m = _swap_through_live_fitness(replay["transitions"])
    assert len(live) == replay["n"] == 12
    assert m == replay["m_promote"] == 6
    for row in live:
        assert row["live_swapped"] == row["swapped"], (
            f"{row['skill']} @ {row['at']}: the live fitness swaps it "
            f"{row['live_swapped']}, the banked replay swapped it {row['swapped']}"
        )


def test_the_live_fitness_reproduces_four_flips_and_meets_his_bar(replay):
    live, _ = _swap_through_live_fitness(replay["transitions"])
    flips = [r for r in live if r["live_swapped"] != r["banked"]]
    assert len(flips) == replay["flips"] == 4
    assert len(flips) >= replay["bar"], "D2b PV-20260820T223001Z: the bar is >= 4 of 12"
    assert len(flips) % 2 == 0, "the mapping preserves the margin, so flips come in pairs"


def test_the_flipped_four_are_the_four_the_evidence_names(replay):
    live, _ = _swap_through_live_fitness(replay["transitions"])
    assert {r["skill"] for r in live if r["live_swapped"] != r["banked"]} == THE_FOUR


def test_the_naive_inverse_would_not_reproduce_the_replay(replay):
    """The guard on the guard: if the polarity were flipped to ``1 - R``, this fixture
    would still 'pass' something - so check that it would NOT pass THIS."""
    inverted = [{**t, "residual": 1.0 - t["residual"]} for t in replay["transitions"]]
    live, _ = _swap_through_live_fitness(inverted)
    assert [r["live_swapped"] for r in live] != [r["swapped"] for r in live]


# --- the invisible-but-good class ------------------------------------------------------

def test_the_invisible_but_good_class_reads_demands_investment_not_demote():
    """idea_foundry and reconciler: offered, never used, and their own claimed tasks put
    them at best ranks 371 and 229. Usage-count calls that failure. The residual calls it a
    findability debt, and the promoter must no longer cull on it."""
    sig = _sig(offered=assess.OFFERED_UNUSED)
    fit = assess._fitness(sig, residual=0.998368)          # idea_foundry's banked R
    status, reason = assess._recommend(
        "experimental", sig, fit, recently_touched=False, is_protected=False,
        demands_investment=True,
    )
    assert status != "deprecated"
    assert "DEMANDS INVESTMENT" in reason and "0.998368" in reason


def test_without_the_guard_the_same_silence_still_deprecates():
    """The guard is the whole behaviour change; with it off, the incumbent path is intact.
    A skill whose residual is unknown or below the cut is judged exactly as before."""
    sig = _sig(offered=assess.OFFERED_UNUSED)
    fit = assess._fitness(sig, residual=None)
    status, reason = assess._recommend("experimental", sig, fit, demands_investment=False)
    assert status == "deprecated" and "never used" in reason


def test_a_core_skill_that_fell_out_of_use_is_also_spared_by_the_guard():
    sig = _sig(offered=assess.OFFERED_UNUSED * 2)
    fit = assess._fitness(sig, residual=0.998)
    assert assess._recommend("core", sig, fit, demands_investment=True)[0] == "core"
    assert assess._recommend("core", sig, fit, demands_investment=False)[0] == "deprecated"


def test_the_guard_cannot_promote_on_its_own():
    """Deliberately asymmetric: the residual spares, it does not raise. A never-used skill
    with a sky-high residual stays on probation - promoting it to core autonomously is a
    larger act than the bar ratified, and it is his to rule."""
    sig = _sig(offered=assess.OFFERED_UNUSED, usage=0)
    fit = assess._fitness(sig, residual=0.9999)
    assert assess._recommend("experimental", sig, fit, demands_investment=True)[0] != "core"


# --- the banked store and the live cut -------------------------------------------------

def test_the_store_carries_the_measured_population_and_a_median_cut():
    from laplace.pipeline.canon import Canon

    store = assess.load_residuals(Canon.load())
    assert store["available"] and store["population" if "population" in store else "residuals"]
    assert len(store["residuals"]) >= 50, "the archive is in the measured population"
    assert store["cut"] == pytest.approx(0.994757, abs=1e-6)


def test_the_guard_reproduces_the_replays_split_on_the_silence_deprecations(replay):
    """The live guard is a median split over the banked population; the replay's cut was
    the top-m of the twelve. They are different rules, so their agreement is a fact worth
    checking rather than assuming - and on this evidence they agree row for row."""
    from laplace.pipeline.canon import Canon

    cut = assess.load_residuals(Canon.load())["cut"]
    silence = [t for t in replay["transitions"]
               if t["prior_lane_class"] == "silence-deprecation" and t["banked"] == "DEPRECATE"]
    assert len(silence) >= 5, "the silence-deprecations are the class the guard acts on"
    for t in silence:
        spared = t["residual"] >= cut
        assert spared is (t["swapped"] == "PROMOTE"), (
            f"{t['skill']}: guard spares={spared}, replay swapped={t['swapped']}"
        )


def test_load_residuals_degrades_to_unknown_rather_than_guessing(tmp_path):
    class _Stub:
        root = tmp_path

    store = assess.load_residuals(_Stub())
    assert store["available"] is False and store["cut"] is None and store["residuals"] == {}
    (tmp_path / assess.RESIDUAL_STORE).write_text("{not json", encoding="utf-8")
    assert assess.load_residuals(_Stub())["available"] is False


def test_too_small_a_population_gets_no_cut(tmp_path):
    """A median over three numbers is not a population median. Below the floor the guard
    stays inert - never act on an unreliable signal."""
    class _Stub:
        root = tmp_path

    few = {n: 0.9 for n in "abc"}
    (tmp_path / assess.RESIDUAL_STORE).write_text(
        json.dumps({"residuals": few}), encoding="utf-8")
    assert assess.load_residuals(_Stub())["cut"] is None
    many = {str(i): 0.5 + i / 100 for i in range(assess.RESIDUAL_MIN_POPULATION)}
    (tmp_path / assess.RESIDUAL_STORE).write_text(
        json.dumps({"residuals": many}), encoding="utf-8")
    assert assess.load_residuals(_Stub())["cut"] is not None


def test_write_residual_cache_projects_the_instruments_payload(tmp_path):
    class _Stub:
        root = tmp_path

    payload = {
        "definition": "definition.md",
        "instrument": "laplace.engine.skill_residual.measure",
        "wall_seconds": 12.3,
        "rows": [{"skill": "a", "residual": 0.9}, {"skill": "b", "residual": 0.8},
                 {"skill": "bad"}],
    }
    path = assess.write_residual_cache(payload, _Stub(), source="rows.json")
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["residuals"] == {"a": 0.9, "b": 0.8}
    assert written["n_skills"] == 2 and written["source"] == "rows.json"


def test_the_banked_store_matches_the_evidence_it_was_projected_from():
    """The store is a projection, and a projection that drifts from its source is a render
    pretending to be a row. Checked against the bundle it names."""
    from laplace.pipeline.canon import Canon

    store = assess.load_residuals(Canon.load())
    rows = json.loads((QC / "rows_qc.json").read_text(encoding="utf-8"))["rows"]
    assert store["residuals"] == {r["skill"]: r["residual"] for r in rows}


# --- the alarm -------------------------------------------------------------------------

def test_the_report_carries_the_signal_provenance_and_the_alarm():
    from laplace.pipeline.canon import Canon

    rep = assess.assess(Canon.load())
    sig = rep["residual_signal"]
    assert sig["available"] and sig["polarity"].startswith("D1 PV-20260820T223000Z")
    assert sig["cut"] and sig["known_this_pass"] > 0
    assert isinstance(rep["signal_disagreements"], list)
    for row in rep["skills"]:
        assert row["signal_disagreement"] is (row["incumbent_status"] != row["recommended_status"])
