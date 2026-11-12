"""The convergence CONTRACT + the acceptance algebra the loop is judged against.

Invariants before mechanism (his correction, 2026-07-09): convergence is defined
by a finished-object CONTRACT, not by exhaustion or a round-over-round flag
delta. Its direction is toward the *clearest acceptable expression of a fixed
argument*, not the most heavily-processed one. This module is the contract and
the acceptance algebra:

  * the nine contract dimensions, split HARD (non-compensable) / SOFT (optimised);
  * dominance / monotone acceptance (improvement, not mere change);
  * the neutral reference surface + voice's burden of proof;
  * the disagreement matrix (classify judge conflict -> owning layer);
  * the stop rule (convergence vs stagnation), which is PROVISIONAL — final
    convergence always requires explicit author acceptance.

The loop that DRIVES this (judges, cold reader, bounded-candidate generation,
minimal re-projection) consumes these functions; keeping the contract here means
it is unit-testable without a manuscript run and the interface + master guide can
render exactly the same rules the loop enforces. Everything is JSON-shaped so a
verdict banks straight into the feedback ledger and surfaces in the DECISIONS
rail.
"""
from __future__ import annotations

from typing import Any

# --- the finished-object contract -------------------------------------------
# HARD gates are non-compensable: a failure BLOCKS and is never traded off
# against excellence elsewhere. SOFT dimensions are optimised and dominance-
# compared — this is where voice must earn its place. `author_acceptance` is the
# terminal bar and is human (never machine-scored), so it is not in either tuple.
HARD_DIMENSIONS = (
    "semantic_identity",     # content neither added nor lost
    "technical_support",     # no naked reliances; every claim carried
    "structural_fulfilment", # the narrative spec's beats all realised
    "artefact_integrity",    # compiles clean; typography; markers intact
    "provenance_integrity",  # the %<sid>-pN thread survives the round-trip
    "no_meta_leak",          # no policy/scaffolding echo in the prose
)
SOFT_DIMENSIONS = (
    "reader_reconstruction", # a cold reader rebuilds the argument from the page
    "prose_transparency",    # structure felt, not declared; no self-narration
    "authorial_fit",         # his register, right for the venue
    "economy_of_attention",  # reader effort matches genuine difficulty
    "rhythm",                # sentence movement
    "citation_coverage",     # C2 — every externally-grounded assertion carries a cite
    "style_conformance",     # I1 — the rendered object wears his house conventions
)
CONTRACT_DIMENSIONS = HARD_DIMENSIONS + SOFT_DIMENSIONS

#: soft-score materiality threshold: a change smaller than this is NOT a
#: "material" improvement or deterioration (guards against neutral churn).
SOFT_EPS = 0.05

#: the five prohibitions a voice candidate must not trigger vs the neutral
#: reference surface (each is a "how much worse than neutral" delta; > EPS fails).
#: content_delta is exact (any added/lost content fails).
VOICE_PROHIBITIONS = (
    "content_delta",          # added or lost content (exact: must be 0)
    "reader_effort_delta",    # increased reader effort
    "repetition_delta",       # repeated ideas
    "conspicuousness_delta",  # authorial presence more conspicuous than reasoning
    "clarity_delta",          # weakened technical clarity
)


def _soft(ev: dict) -> dict:
    return ev.get("soft") or {}


def hard_pass(ev: dict) -> bool:
    """Every HARD dimension passes. A candidate evaluation is
    ``{"hard": {dim: bool}, "soft": {dim: float}}``."""
    hard = ev.get("hard") or {}
    return all(bool(hard.get(d, False)) for d in HARD_DIMENSIONS)


def dominates(candidate: dict, incumbent: dict, eps: float = SOFT_EPS) -> bool:
    """Monotone acceptance — improvement, not mere change. A candidate dominates
    the incumbent iff: all HARD gates pass, at least one implicated SOFT
    dimension materially improves, and NO soft dimension materially deteriorates.
    Rejects neutral churn, stylistic novelty without explanatory gain, and
    offset-benefit changes."""
    if not hard_pass(candidate):
        return False
    cs, is_ = _soft(candidate), _soft(incumbent)
    improved = any(cs.get(d, 0.0) - is_.get(d, 0.0) > eps for d in SOFT_DIMENSIONS)
    degraded = any(is_.get(d, 0.0) - cs.get(d, 0.0) > eps for d in SOFT_DIMENSIONS)
    return improved and not degraded


def voice_dominates_neutral(voice_ev: dict, neutral_ev: dict, prohibitions: dict,
                            eps: float = SOFT_EPS) -> bool:
    """Voice's burden of proof. The voice candidate is accepted over the neutral
    reference surface only when it dominates neutral AND triggers none of the
    five prohibitions (adds content, increases reader effort, repeats ideas,
    makes the authorial presence more conspicuous than the reasoning, or weakens
    clarity). Voice is not better for being more authored — it must demonstrate
    the improvement. `prohibitions` values are voice-minus-neutral deltas where
    positive means *worse*."""
    if not dominates(voice_ev, neutral_ev, eps):
        return False
    if int(prohibitions.get("content_delta", 0)) != 0:
        return False
    for k in ("reader_effort_delta", "repetition_delta",
              "conspicuousness_delta", "clarity_delta"):
        if float(prohibitions.get(k, 0.0)) > eps:
            return False
    return True


def accept_candidate(candidate: dict, incumbent: dict | None, *, is_voice: bool = False,
                     neutral: dict | None = None, prohibitions: dict | None = None,
                     eps: float = SOFT_EPS) -> dict:
    """The single acceptance decision. Returns ``{"accept": bool, "reason": str}``.
    A voice candidate additionally carries the burden of proof against the neutral
    reference surface. The first candidate that passes the hard gates seeds the
    incumbent (nothing to dominate yet)."""
    if not hard_pass(candidate):
        return {"accept": False, "reason": "a hard gate fails (non-compensable)"}
    if is_voice:
        if neutral is None:
            return {"accept": False, "reason": "voice candidate has no neutral reference to beat"}
        if not voice_dominates_neutral(candidate, neutral, prohibitions or {}, eps):
            return {"accept": False,
                    "reason": "voice does not dominate the neutral surface — retain neutral"}
    if incumbent is None:
        return {"accept": True, "reason": "seeds the incumbent (hard gates pass, none to dominate)"}
    if dominates(candidate, incumbent, eps):
        return {"accept": True, "reason": "materially dominates the incumbent"}
    return {"accept": False, "reason": "no material improvement over the incumbent (change != improvement)"}


# --- the disagreement matrix -------------------------------------------------
# Judge disagreement is diagnostic STRUCTURE, not noise: a pass/fail combination
# names the earliest likely failure layer. Conflicting judgements are NEVER
# averaged into one score. Each entry -> (pathology, owning_layer, overruleable).
_DISAGREEMENT = {
    ("fidelity", "cold_reader"):     ("explanation problem", "narrative", True),
    ("cold_reader", "prose"):        ("understandable but unbearable surface", "prose", True),
    ("prose", "voice"):              ("readable but anonymous / counterfeit", "voice", True),
    ("voice", "prose"):              ("persona applied too aggressively", "weld-voice", True),
    ("structure", "repeated_content"): ("narrative-packet / renderer duplication", "narrative", True),
}


def classify_disagreement(verdicts: dict) -> dict:
    """Map a set of judge verdicts (``{lens: bool_pass}``) to the earliest owning
    layer. `author` False with every machine judge True is the special case: the
    rendering TARGET is wrong and it is NOT overruleable. Returns
    ``{"pathology", "owning_layer", "overruleable"}``."""
    machine = ("fidelity", "cold_reader", "prose", "voice", "structure",
               "repeated_content")
    if verdicts.get("author") is False and all(
            verdicts.get(m, True) for m in machine):
        return {"pathology": "the rendering target is wrong",
                "owning_layer": "target", "overruleable": False}
    for (passer, failer), (path, layer, ovr) in _DISAGREEMENT.items():
        if verdicts.get(passer) is True and verdicts.get(failer) is False:
            return {"pathology": path, "owning_layer": layer, "overruleable": ovr}
    # no diagnostic disagreement: route any lone hard failure to its own layer.
    for lens in ("fidelity", "structure", "cold_reader", "prose", "voice"):
        if verdicts.get(lens) is False:
            return {"pathology": f"{lens} failure", "owning_layer": lens, "overruleable": True}
    return {"pathology": "no failure", "owning_layer": None, "overruleable": True}


# --- the stop rule (convergence vs stagnation) ------------------------------
def should_continue(state: dict) -> dict:
    """Convergence is NOT exhaustion. Continue while any hard gate fails, or while
    a bounded candidate materially dominates the incumbent. Stability is
    supporting evidence only AFTER the manuscript is in the acceptable region.
    Stop PROVISIONALLY when all hard gates pass, no systemic failure remains, the
    semantic + structural representations are fixed, the dirty-set has contracted,
    and no bounded rerender dominates. Final convergence requires explicit author
    acceptance. Returns ``{"continue": bool, "provisional_stop": bool, "reason"}``.

    `state`: hard_failing, systemic_failure, representations_fixed,
    dirty_contracted, bounded_dominator, round, budget (default 4), author_accepted.
    """
    def done(reason, *, author=False):
        return {"continue": False, "provisional_stop": not author,
                "final": author, "reason": reason}

    if state.get("author_accepted"):
        return done("author accepted — final convergence", author=True)
    if state.get("hard_failing"):
        return {"continue": True, "provisional_stop": False, "final": False,
                "reason": "a hard gate fails"}
    if state.get("bounded_dominator"):
        return {"continue": True, "provisional_stop": False, "final": False,
                "reason": "a bounded candidate materially dominates the incumbent"}
    if state.get("round", 0) >= state.get("budget", 4):
        return done("round budget exhausted (backstop) — provisional stop, author bar still open")
    in_region = (not state.get("systemic_failure")
                 and state.get("representations_fixed")
                 and state.get("dirty_contracted"))
    if in_region:
        return done("provisional convergence: hard gates pass, no systemic failure, "
                    "representations fixed, dirty-set contracted, no dominator — "
                    "author bar still open")
    return {"continue": True, "provisional_stop": False, "final": False,
            "reason": "not yet in the acceptable region"}


# --- candidate stores (rollback; no moving target) --------------------------
#: The immutable surfaces a run keeps. No operation overwrites the best known
#: surface; every candidate/verdict/route/integration is reversible. `neutral` is
#: the canonical reference surface for every prose comparison.
CANDIDATE_SLOTS = ("current", "accepted_incumbent", "best_neutral", "best_voice",
                   "last_author_approved")

#: The profiles pinned + version-recorded for a run; a change to ANY starts a NEW
#: run and invalidates comparison with prior stability (prevents judge/target
#: drift under the manuscript).
FROZEN_PROFILE_KEYS = ("projection", "narrative", "voice_profile", "judge_panel",
                       "typography_profile", "renderer")


def run_fingerprint(profiles: dict) -> tuple:
    """The identity of a convergence run: the pinned profile versions. Two rounds
    are comparable only when their fingerprints match."""
    return tuple(str(profiles.get(k, "")) for k in FROZEN_PROFILE_KEYS)


def same_run(a: dict, b: dict) -> bool:
    """Whether two rounds belong to the same convergence run (comparable
    stability). A change to any frozen profile starts a new run."""
    return run_fingerprint(a) == run_fingerprint(b)


# --- the bridge: a live round's panel -> contract state -> stop decision -----
# The INTERIM mapping from the current project-fixedpoint panel onto the contract
# dimensions (the asymmetric panel will eventually emit dimensions directly).
# HARD: meta_leak + claims (technical support) + the mechanical checks passed in
# (compile/fidelity/provenance/structure). SOFT: the prose judges score their
# dimensions. This is what lets the loop stop on CONTRACT SATISFACTION rather than
# zero-flag exhaustion, using the same should_continue the tests pin.
def evaluate_round(panel: list[dict], *, compile_ok: bool = True,
                   fidelity_ok: bool = True, provenance_ok: bool = True,
                   structural_ok: bool = True, round: int = 0, budget: int = 4,
                   author_accepted: bool = False,
                   lock_roster: "list[str] | None" = None) -> dict:
    """Aggregate one convergence round (the panel + mechanical checks) into the
    contract evaluation, the disagreement classification, and should_continue's
    verdict. `panel` is the project-fixedpoint shape:
    ``[{"label","clean","flags",...}]``.

    Panel labels bridged (Phase F-wire, per the Phase-E reader dimension manifest):

      * the legacy set stays working — meta_leak/voice/closure/caption/claims/calc;
      * ``reader_reconstruction`` aggregates {cold_reader, skim_reader} (closure is
        the legacy cold-reader fallback); ``prose_transparency``/``rhythm`` fold in
        {feral}; ``authorial_fit`` and ``economy_of_attention`` are unchanged;
      * ``technical_support`` (HARD) also requires {referee, apparatus}; ``no_meta_leak``
        (HARD) also requires {figure_reader}; ``artefact_integrity`` (HARD) also
        requires {visual} — but only when that reader RAN (candidate-lock cadence),
        so a normal fixer round where they are silent is unchanged;
      * ``artefact_integrity`` ALSO ANDs in R10 (``restart_reader``, the whole-artefact
        identity grade) **roster-conditionally**: the R10 clause is part of the axis
        only when ``"R10"`` is in ``lock_roster`` (the active tier's
        ``dials.loop.lock.readers`` — harnessed). Within the rostered tier the "only
        when it RAN" guard is TIGHTENED to "rostered ⇒ must have a PASSING verdict": a
        rostered-but-absent or ``failed`` (malformed, C5.1a) R10 verdict leaves the
        axis UNMET (silence never passes). The non-R10-rostering ``fix_mode=loop`` tier
        omits the clause and keeps the pre-R10 definition byte-for-byte — the ROSTER is
        the switch, not the tier name;
      * ``citation_coverage`` (C2) reads the ``citation`` label; ``style_conformance``
        (I1) reads the ``house_style`` label;
      * ``author_acceptance`` stays the terminal human bar (never machine-scored here).

    A missing/silent reader label scores 0.5 via ``soft_score`` (never special-cased)
    and simply blends in; for a HARD reader, silence does not block (``hard_ok``)."""
    by = {p.get("label"): p for p in panel}

    def clean(label: str) -> bool:
        return bool(by.get(label, {}).get("clean"))

    def present(label: str) -> bool:
        return label in by and not by.get(label, {}).get("failed")

    def soft_score(label: str) -> float:
        p = by.get(label)
        if not p or p.get("failed"):
            return 0.5   # a missing/failed judge is neutral, never a free pass
        if p.get("clean"):
            return 1.0
        return max(0.0, 1.0 - 0.15 * len(p.get("flags") or []))

    def soft_agg(*labels: str) -> float:
        """Aggregate several reader labels onto one soft dimension: the mean of
        their ``soft_score``s. A silent reader contributes 0.5 (never special-cased),
        so a candidate-lock reader that has not run neither rewards nor punishes."""
        return sum(soft_score(lbl) for lbl in labels) / len(labels)

    def hard_ok(label: str) -> bool:
        """A HARD-dim reader that only fires at candidate-lock. Absent does NOT
        block (silent fixer round; absent-at-lock is caught by
        candidate_lock.round_complete). But a reader that RAN and CRASHED cannot
        certify a HARD dim, so a crash BLOCKS — it is not a silent pass. A reader
        that ran clean passes; ran-and-flagged blocks."""
        p = by.get(label)
        if p is None:
            return True
        if p.get("failed"):
            return False
        return bool(p.get("clean"))

    # R10 (the whole-artefact identity grade) is consumed ROSTER-CONDITIONALLY. When
    # its reader id is in the active tier's lock roster (``lock_roster`` =
    # ``dials.loop.lock.readers``), its file-backed ``clean`` bit ANDs into
    # ``artefact_integrity`` under a STRICTER rule than ``hard_ok``: rostered ⇒ the
    # reader must have RUN and passed. An absent (``failed``/missing) or ran-and-
    # flagged verdict leaves the axis UNMET — silence never passes. When the reader is
    # NOT rostered (the ``fix_mode=loop`` tier) this returns True and contributes
    # nothing, so the axis is byte-for-byte the pre-R10 definition.
    _roster = set(lock_roster or ())

    def rostered_clean(reader_id: str, label: str) -> bool:
        """A reader ROSTERED into the active lock tier must have RUN and passed:
        absent/``failed`` ⇒ unmet, ran-and-flagged ⇒ unmet, ran-clean ⇒ pass —
        stricter than :func:`hard_ok`, which lets an absent candidate-lock reader
        through. A reader NOT in the roster returns True (the pre-reader definition)."""
        if reader_id not in _roster:
            return True
        p = by.get(label)
        if p is None or p.get("failed"):
            return False
        return bool(p.get("clean"))

    reader_label = "cold_reader" if present("cold_reader") else "closure"
    hard = {
        "semantic_identity": bool(fidelity_ok),
        "technical_support": clean("claims") and hard_ok("referee") and hard_ok("apparatus"),
        "structural_fulfilment": bool(structural_ok),
        "artefact_integrity": (bool(compile_ok) and clean("caption") and hard_ok("visual")
                               and hard_ok("promise")
                               and rostered_clean("R10", "restart_reader")),
        "provenance_integrity": bool(provenance_ok),
        "no_meta_leak": clean("meta_leak") and hard_ok("figure_reader"),
    }
    soft = {
        "reader_reconstruction": soft_agg(reader_label, "skim_reader"),
        "prose_transparency": soft_agg("voice", "feral"),
        "authorial_fit": soft_score("voice"),
        "economy_of_attention": soft_score("calc"),
        "rhythm": soft_agg("voice", "feral"),
        "citation_coverage": soft_score("citation"),
        "style_conformance": soft_score("house_style"),
    }
    ev = {"hard": hard, "soft": soft}
    hard_failing = not hard_pass(ev)
    n_flags = sum(len([f for f in (p or {}).get("flags") or []
                       if "dismissed_n" not in f]) for p in panel)  # adjudication counter is not a flag
    # systemic: a hard failure, or a pervasive surface problem (a soft judge with
    # many flags) — the signal to re-render/re-weld rather than nibble.
    systemic = hard_failing or any(
        len((by.get(lbl) or {}).get("flags") or []) >= 3
        for lbl in ("voice", reader_label, "calc", "feral", "skim_reader"))
    verdicts = {
        "fidelity": bool(fidelity_ok),
        "cold_reader": clean(reader_label),
        "prose": clean("voice"),
        "voice": clean("voice"),
        "structure": bool(structural_ok),
        "repeated_content": not any(
            "repeat" in str(f.get("issue", "")).lower()
            for p in panel for f in (p.get("flags") or [])),
        "author": True if author_accepted else None,
    }
    state = {
        "hard_failing": hard_failing,
        "systemic_failure": systemic,
        "representations_fixed": (not systemic) and clean("claims"),
        "dirty_contracted": n_flags == 0,
        "bounded_dominator": False,   # the loop sets this when a bounded candidate wins
        "round": round, "budget": budget, "author_accepted": author_accepted,
    }
    return {
        "contract": ev,
        "hard_failing": hard_failing,
        "n_flags": n_flags,
        "disagreement": classify_disagreement(verdicts),
        "stop": should_continue(state),
    }
