"""converge.py - the halt predicate of the graded climb (G0b), spectral-radius framed.

The wake-sleep reconstruction loop (digest-down <-> regenerate-up) is a map T on the brief; its
fixed point's stability is the SPECTRAL RADIUS rho of the Jacobian. rho < 1 contracts (stable,
faithful); rho -> 1- is the lower edge of chaos (expressivity peaks, converges slowly); rho >= 1
runs away. The lambda_0 in psi = log_n lambda_0 IS that leading eigenvalue, so the convergent
point is the eigenvalue - which makes the OPTIMAL halt threshold F1 (the endogenous fitness rule,
the author's fork). This module is the INSTRUMENT, kept decoupled from the POLICY: it estimates
rho from the cycle trace and reports the signals; the target rho*(grade, kind) is a pluggable
socket with conservative defaults, so the optimum drops in later without a rewrite (good enough to
progress, the seam left open).

No cloud, no ghost: this is pure logic over structured verdict-objects (what adjudicate.py
produces). The ghost reconstruction that fills the loop is a sealed cloud agent (G1); here we build
and test the control that decides when the loop has closed, and how. builder != judge.

The convergent point is NOT uniform (the author, 2026-06-06): factual reconstruction - about the
world and the people in it - wants deep stability (rho* well below 1); generative / insight
reconstruction wants the lower edge (rho* near 1, halt before the imagination collapses to the
obvious). And one asymmetry the covenant pins: factual-about-PEOPLE rho* is a RATCHET, never
loosened toward the edge - confabulating a fact about a person is a harm (canon://engine/self).
Imagination is licensed for ideas, forbidden for people.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

_HERE = Path(__file__).resolve()
_REPO = _HERE.parents[6]

# Halt states (mirror telemetry.HALT_STATES).
FAITHFUL = "converged-faithful"
DEGENERATE = "converged-degenerate"
OSCILLATING = "oscillating"
OPEN = "open"

# --- the policy socket: rho*(grade, kind), conservative defaults, the people ratchet ----------
# Good-enough defaults behind a pluggable socket (the author's directive: good enough to progress,
# the seam left open). One stable basin + one edge band; no per-grade tuning yet (grade is taken so
# the socket is grade-aware when F1 fills it). default kind -> factual: the safe direction is the
# basin, not the edge; a node EARNS the generative tag.
RHO_STAR_DEFAULTS: dict[str, float] = {"factual": 0.30, "generative": 0.85}
# The covenant floor: factual-about-people may only ever be MORE contractive than this, never less.
# A ratchet, not a knob - mutable downward (stricter) only.
PEOPLE_CEILING: float = 0.20
DEFAULT_BUDGET: int = 8


def rho_star(grade: str = "", kind: str = "", override: float | None = None) -> float:
    """The target spectral radius for a node of this grade and kind - the pluggable policy.

    ``kind`` is ``factual`` | ``generative`` | ``factual_people`` (default: factual, the safe
    basin). ``grade`` is accepted for the grade-aware optimum F1 will supply, but the conservative
    default does not vary by grade yet. ``override`` lets a future/tuned policy propose a target;
    for ``factual_people`` it is CLAMPED at :data:`PEOPLE_CEILING` (the ratchet - the covenant
    never lets a people-fact drift toward the edge).
    """
    k = (kind or "factual").strip().lower()
    if k == "factual_people":
        target = override if override is not None else PEOPLE_CEILING
        return min(target, PEOPLE_CEILING)  # ratchet: only ever more contractive
    if override is not None:
        return override
    return RHO_STAR_DEFAULTS.get(k, RHO_STAR_DEFAULTS["factual"])


@dataclass
class Verdict:
    """One cycle's adjudicated verdict - the structured object converged() reads.

    Built from adjudicate.py's dict (``lost`` + ``similarity`` + ``proxy_fate``) plus the cycle
    index and the node's grade/kind context (for dial-attribution).
    """

    cycle: int
    lost: tuple[str, ...] = ()
    similarity: float | None = None
    fate: str | None = None
    grade: str = ""
    kind: str = ""

    @classmethod
    def from_adjudication(cls, cycle: int, adj: dict, grade: str = "", kind: str = "") -> "Verdict":
        return cls(
            cycle=cycle,
            lost=tuple(adj.get("lost", ())),
            similarity=adj.get("similarity"),
            fate=adj.get("proxy_fate"),
            grade=grade,
            kind=kind,
        )


@dataclass
class Halt:
    """The halt decision + the signals that produced it - fully dial-attributable."""

    state: str
    rho: float | None
    rho_star: float
    stable: bool
    revisited: bool
    budget_exhausted: bool
    cycle: int

    @property
    def done(self) -> bool:
        return self.state != OPEN


def _sig(lost) -> frozenset:
    return frozenset(lost)


def lost_delta(a, b) -> int:
    """Size of the symmetric difference between two lost-sets - the discrete ||Delta E||."""
    return len(_sig(a) ^ _sig(b))


def estimate_rho(verdicts: list[Verdict]) -> float | None:
    """Empirical spectral radius from successive lost-set changes.

    Near a fixed point the error decays as ||Delta||_{n+1} / ||Delta||_n -> rho (the dominant
    eigenvalue magnitude). Needs >= 3 verdicts (two deltas) to form a ratio; returns None below
    that. The estimate is noisy (the adjudicator is stochastic) - smoothing over more deltas is a
    mutable refinement, deferred. Divide-by-zero guards: an already-stable prev delta (0) returns
    0.0 if still stable, else 1.0 (re-opening from a settled set is not contracting).
    """
    if len(verdicts) < 3:
        return None
    deltas = [lost_delta(verdicts[i].lost, verdicts[i - 1].lost) for i in range(1, len(verdicts))]
    d_prev, d_last = deltas[-2], deltas[-1]
    if d_prev == 0:
        return 0.0 if d_last == 0 else 1.0
    return round(d_last / d_prev, 4)


def revisits(verdicts: list[Verdict]) -> bool:
    """A limit cycle: the latest lost-set re-appears from >= 2 cycles back (period >= 2).

    A match with the IMMEDIATELY previous set is a fixed point (stable), not a cycle - handled
    separately. The deterministic-map logic: a revisited configuration would repeat forever; with a
    stochastic adjudicator it is strong evidence, not proof (a principled heuristic, not a constant
    wall-clock budget - the author's correction).
    """
    if len(verdicts) < 3:
        return False
    sigs = [_sig(v.lost) for v in verdicts]
    return sigs[-1] in sigs[:-2]


def converged(
    verdicts,
    *,
    grade: str = "",
    kind: str = "",
    policy=rho_star,
    budget: int = DEFAULT_BUDGET,
    override: float | None = None,
) -> Halt:
    """The halt predicate. Pure over a sequence of structured verdict-objects.

    Decoupled instrument/policy: the SIGNALS (rho, stability, revisitation) are measured; the
    POLICY (the target rho* + the verdict map) is the pluggable ``policy`` + the fate. The states:

      * OSCILLATING - rho >= 1 OR a limit cycle (revisitation). Runaway / non-closing.
      * CONVERGED-FAITHFUL - contracted to the target (rho <= rho*) with a faithful/partial fate.
      * CONVERGED-DEGENERATE - contracted but the fate is confabulated (a stable fixed point that
        is the PLATEAU - route UP to grow the missing layer, never minimise it); OR a *generative*
        node over-contracted below the edge (rho < rho*/2 or fully stable) - the imagination
        collapsed to the obvious, the false click.
      * OPEN - still contracting (rho > rho*) with budget left, OR budget exhausted while still
        contracting (rho < 1): a SLOW converger, flagged ``budget_exhausted`` - NOT mislabelled
        oscillating (the author's correction to a constant budget).
    """
    vs = list(verdicts)
    target = policy(grade=grade, kind=kind, override=override)
    cyc = vs[-1].cycle if vs else 0
    if len(vs) < 2:
        return Halt(OPEN, None, target, False, False, False, cyc)

    stable = lost_delta(vs[-1].lost, vs[-2].lost) == 0
    revisited = revisits(vs)
    rho = estimate_rho(vs)
    fate = vs[-1].fate
    kind_l = (kind or "factual").strip().lower()

    if revisited or (rho is not None and rho >= 1.0):
        return Halt(OSCILLATING, rho, target, stable, revisited, False, cyc)

    contracted = stable or (rho is not None and rho <= target)
    if contracted:
        if fate == "confabulated":
            state = DEGENERATE
        elif kind_l == "generative" and (stable or (rho is not None and rho < target / 2)):
            state = DEGENERATE  # over-contracted: the imagination collapsed to the obvious
        else:
            state = FAITHFUL
        return Halt(state, rho, target, stable, revisited, False, cyc)

    exhausted = (len(vs) - 1) >= budget
    return Halt(OPEN, rho, target, stable, revisited, exhausted, cyc)


def _telemetry():
    try:
        from laplace.engine import telemetry  # type: ignore

        return telemetry
    except Exception:
        sys.path.insert(0, str(_REPO / "src"))
        from laplace.engine import telemetry  # type: ignore

        return telemetry


def bank(halt: Halt, grade: str = "", kind: str = "", target_id: str = "") -> None:
    """Bank the dial-attributable convergence record (best-effort).

    The point of logging (grade, kind, rho, rho*) every cycle: when a lesson does not land, the
    trace says WHICH dial to nudge before the next round of ingestion (the author, 2026-06-06).
    """
    try:
        tel = _telemetry()
        tel.convergence(
            state=halt.state,
            grade=grade,
            kind=kind,
            cycle=halt.cycle,
            rho=halt.rho,
            rho_star=halt.rho_star,
            target=target_id,
            reason="budget_exhausted" if halt.budget_exhausted else "",
        )
    except Exception as e:  # telemetry is best-effort; never break the loop on a log failure
        print(f"(convergence telemetry not logged: {e})", file=sys.stderr)
