"""Unit tests for converge.py - the G0b halt predicate, spectral-radius framed.

Covers the rho-estimator (the instrument), the rho*(grade, kind) policy socket with the people
ratchet, the four halt states, the instrument/policy DECOUPLING, and the dial-attributable
convergence telemetry producer. All on fixture verdict-objects - zero cloud, no ghost.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[1]
_CONV = _REPO / "src" / "laplace" / "pipeline" / "canon" / "skills" / "reconstruction_fitness" / "scripts" / "converge.py"


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = mod  # dataclasses needs the module registered
    spec.loader.exec_module(mod)
    return mod


cv = _load(_CONV)


def _vseq(lost_lists, fate="faithful", kind="factual"):
    return [cv.Verdict(cycle=i, lost=tuple(x), fate=fate, kind=kind) for i, x in enumerate(lost_lists)]


# --------------------------------------------------------------------------- #
# The spectral-radius estimator - rho from successive lost-set deltas.
# --------------------------------------------------------------------------- #
def test_estimate_rho_contracting():
    # deltas 4 -> 2 -> 1, last ratio 1/2
    vs = _vseq([[], ["a", "b", "c", "d"], ["a", "b"], ["a", "b", "c"]])
    assert cv.estimate_rho(vs) == 0.5


def test_estimate_rho_edge_is_one():
    # growing sets, each step adds 2: deltas 2,2,2 -> rho 1.0 (the marginal edge)
    vs = _vseq([["a", "b"], ["a", "b", "c", "d"], ["a", "b", "c", "d", "e", "f"],
                ["a", "b", "c", "d", "e", "f", "g", "h"]])
    assert cv.estimate_rho(vs) == 1.0


def test_estimate_rho_runaway_above_one():
    # deltas 1,2,4 -> rho 2.0
    vs = _vseq([["a"], ["a", "b"], ["a", "b", "c", "d"], ["a", "b", "c", "d", "e", "f", "g", "h"]])
    assert cv.estimate_rho(vs) == 2.0


def test_estimate_rho_needs_three_verdicts():
    assert cv.estimate_rho(_vseq([["a"], ["b"]])) is None


# --------------------------------------------------------------------------- #
# The policy socket - conservative defaults, default-to-factual, the people ratchet.
# --------------------------------------------------------------------------- #
def test_rho_star_defaults_and_default_to_factual():
    assert cv.rho_star(kind="factual") == 0.30
    assert cv.rho_star(kind="generative") == 0.85
    assert cv.rho_star(kind="") == 0.30          # default to the safe basin
    assert cv.rho_star(kind="unknown") == 0.30   # unknown kind -> factual, conservative
    assert cv.rho_star(kind="generative", override=0.5) == 0.5  # a tuned policy may propose


def test_rho_star_people_floor_is_a_ratchet():
    assert cv.rho_star(kind="factual_people") == cv.PEOPLE_CEILING
    # tightening (more contractive) is allowed
    assert cv.rho_star(kind="factual_people", override=0.10) == 0.10
    # loosening toward the edge is CLAMPED - the covenant never lets a people-fact drift up
    assert cv.rho_star(kind="factual_people", override=0.90) == cv.PEOPLE_CEILING


# --------------------------------------------------------------------------- #
# The four halt states.
# --------------------------------------------------------------------------- #
def test_stable_faithful_converges_faithful():
    vs = _vseq([["x", "y"], ["x"], [], []], fate="faithful", kind="factual")
    h = cv.converged(vs, grade="summary", kind="factual")
    assert h.state == cv.FAITHFUL and h.stable and h.done


def test_stable_confabulated_is_the_degenerate_plateau():
    vs = _vseq([["x", "y"], ["x"], [], []], fate="confabulated", kind="factual")
    h = cv.converged(vs, kind="factual")
    assert h.state == cv.DEGENERATE  # a stable fixed point that is the plateau -> route up


def test_limit_cycle_is_oscillating():
    vs = _vseq([["a"], ["b"], ["a"], ["b"]], fate="faithful", kind="factual")
    h = cv.converged(vs, kind="factual")
    assert h.state == cv.OSCILLATING and h.revisited


def test_runaway_rho_is_oscillating():
    vs = _vseq([["a"], ["a", "b"], ["a", "b", "c", "d"],
                ["a", "b", "c", "d", "e", "f", "g", "h"]], fate="faithful")
    h = cv.converged(vs, kind="factual")
    assert h.state == cv.OSCILLATING and h.rho >= 1.0


def test_still_contracting_is_open_within_budget():
    vs = _vseq([[], ["a", "b", "c", "d"], ["a", "b"], ["a", "b", "c"]], fate="faithful", kind="factual")
    h = cv.converged(vs, kind="factual", budget=8)  # rho 0.5 > 0.30, not yet at the basin
    assert h.state == cv.OPEN and not h.budget_exhausted


def test_budget_exhausted_slow_converger_is_open_not_oscillating():
    # The author's correction: a slow-but-still-contracting loop must NOT be mislabelled oscillating.
    vs = _vseq([[], ["a", "b", "c", "d"], ["a", "b"], ["a", "b", "c"]], fate="faithful", kind="factual")
    h = cv.converged(vs, kind="factual", budget=2)
    assert h.state == cv.OPEN and h.budget_exhausted  # flagged, not runaway


# --------------------------------------------------------------------------- #
# Instrument / policy DECOUPLING - same signals, different rho*, different verdict.
# --------------------------------------------------------------------------- #
def test_same_trace_decouples_on_kind():
    vs = _vseq([[], ["a", "b", "c", "d"], ["a", "b"], ["a", "b", "c"]], fate="faithful")  # rho 0.5
    factual = cv.converged(vs, kind="factual")       # 0.5 > 0.30 -> still open
    generative = cv.converged(vs, kind="generative")  # 0.5 <= 0.85, in-band -> faithful
    assert factual.state == cv.OPEN
    assert generative.state == cv.FAITHFUL
    assert factual.state != generative.state  # the policy, not the instrument, moved


def test_generative_over_contraction_is_degenerate():
    # A generative node squeezed to a stable fixed point collapsed past the edge to the obvious.
    vs = _vseq([["x"], [], []], fate="faithful", kind="generative")
    h = cv.converged(vs, kind="generative")
    assert h.state == cv.DEGENERATE  # the imagination died; for factual the same trace is FAITHFUL
    assert cv.converged(vs, kind="factual").state == cv.FAITHFUL


# --------------------------------------------------------------------------- #
# The dial-attributable convergence telemetry producer.
# --------------------------------------------------------------------------- #
def test_convergence_producer_banks_the_dials(tmp_path, monkeypatch):
    monkeypatch.setenv("LAPLACE_STATE", str(tmp_path / "state"))
    from laplace.engine import telemetry

    assert set(telemetry.HALT_STATES) == {
        "converged-faithful", "converged-degenerate", "oscillating", "open"}
    ev = telemetry.convergence(state="converged-faithful", grade="summary", kind="factual",
                               cycle=3, rho=0.12, rho_star=0.30, target="objA")
    assert ev["state"] == "converged-faithful"
    assert ev["grade"] == "summary" and ev["kind"] == "factual"
    assert ev["rho"] == 0.12 and ev["rho_star"] == 0.30  # both dials banked
    assert ev["cycle"] == 3 and ev["target"] == "objA"
    with pytest.raises(ValueError):
        telemetry.convergence(state="nonsense")


def test_bank_helper_logs_through_converge(tmp_path, monkeypatch):
    monkeypatch.setenv("LAPLACE_STATE", str(tmp_path / "state"))
    vs = _vseq([["x", "y"], ["x"], [], []], fate="faithful", kind="factual")
    h = cv.converged(vs, grade="summary", kind="factual")
    cv.bank(h, grade="summary", kind="factual", target_id="objA")
    from laplace.engine import telemetry
    evs = [e for e in telemetry.events() if e.get("phase") == "convergence"]
    assert len(evs) == 1
    assert evs[0]["state"] == cv.FAITHFUL
    assert evs[0]["rho_star"] == 0.30
