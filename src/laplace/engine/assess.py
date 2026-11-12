"""Endogenous assessment: the selection operator.

Turns the telemetry ledger into per-skill *fitness* and evidence-gated lifecycle
recommendations (experimental -> core -> deprecated). This is what lets the
dreamer act with silent autonomy safely: it never promotes by fiat, only on
measured evidence of use and good outcomes.

Fitness combines four signals:
  residual   - can the skill be routed to from the tasks it claims to serve
  quality    - did its verify checks pass / did its script run ok
  feedback   - explicit +/- signals logged against it
  retention  - did its contributions survive (default neutral until observed)

THE FIRST SIGNAL WAS USAGE-COUNT UNTIL 2026-08-20. F23 banked that usage-count is
not the fitness signal; the swap was pre-registered, measured blind, and ruled. It
is now the query-conditioned skill residual, and usage-count survives here only as a
reported diagnostic beside it - see the weights block below for the full citation.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

from laplace.engine import telemetry
from laplace.pipeline.canon import Canon, get_canon
from laplace.pipeline.verify import CHECK_SKILL  # re-exported for callers

__all__ = ["assess", "CHECK_SKILL", "write_residual_cache"]

# Fitness weights (sum to 1).
#
# Behavioural evidence (residual + quality) is explicitly dominant - the author
# under-vocalises praise, so explicit feedback skews negative and must not
# be the deciding signal. Absence of positive laplace_log calls is NOT a
# sign of dissatisfaction; it is the normal state. Only genuine negative
# outcomes (net-negative feedback, low verify/exec pass-rates) should pull
# fitness down. W_FEEDBACK is kept low enough that zero explicit feedback -
# which normalises to exactly 0.5 (neutral) - cannot by itself drive fitness
# below the deprecation threshold when the residual and quality are healthy.
#
# THE SWAP (2026-08-20, WO-20260820-residual-into-live-fitness). W_RESIDUAL holds
# the weight W_USAGE used to hold, and carries the query-conditioned skill residual
# (`laplace.engine.skill_residual`) instead of the usage count. The chain, in order:
#
#   * F23 banked that usage-count is not the metacognitive fitness signal - usage
#     counts what was OFFERED AND TAKEN, which is a fact about the orient surface,
#     not about the skill.
#   * D1 (PV-20260820T223000Z) fixed the POLARITY: high residual = DEMANDS
#     INVESTMENT. A high R means the skill's own claimed tasks cannot route to it -
#     invisible, which is not the same as unfit. So the high end of the residual
#     plays the role the high end of usage-count played: it lifts fitness. The
#     naive inverse (1 - R, "reachable is good") is the OPPOSITE ruling and is
#     wrong here; tests/test_fitness_residual_swap.py fails on it.
#   * D2b (PV-20260820T223001Z) set the unfreeze bar at >= 4 of the 12 usage-decided
#     historical transitions flipping under the swap. Measured blind against a
#     definition banked before the number existed: 4 of 12 flip (4 of 11 on the
#     honest re-read, 4-6 across every robustness variant). Bar met.
#     Evidence: evidence/FITNESS_SWAP_REPLAY_2026-08-20/query_conditioned/.
#
# Usage-count is NOT deleted. It is demoted to a reported diagnostic: every row
# still carries `usage`, `usage_norm` and `usage_fitness` (what the incumbent
# formula would have said), and `signal_disagreement` fires when the two readings
# land in different decision bands. A swap that silently agreed with the incumbent
# everywhere would be indistinguishable from no swap; the alarm is how the
# disagreement stays visible instead of becoming invisible progress.
W_RESIDUAL, W_QUALITY, W_FEEDBACK, W_RETENTION = 0.35, 0.45, 0.10, 0.10
USAGE_SAT = 10          # usage count at which usage_norm saturates to 1 (diagnostic only)
CONF_SAT = 5            # samples for full confidence in a transition

# The banked residual store, beside lifecycle.yaml in the canon root: both are
# machine-owned overlays, written deliberately and read at every dream. The live
# measure costs ~964s for 54 skills on CPU (definition.md 3), so it is banked and
# refreshed, never recomputed inline. Missing store or missing skill => the residual
# is UNKNOWN, and an unknown signal is neutral in the sum and inert in the guard.
RESIDUAL_STORE = "skill_residuals.json"
# WO-20260821-frozen-fitness-signal: a banked residual older than this refuses `known` -
# the frozen number stops silently deciding. DECLARED, in-band, revisable: two weeks spans
# the store's observed refresh cadence with margin; the close's probes step auto-refreshes
# past this bound (scripts/sewup.py), so a healthy engine never actually reaches it.
RESIDUAL_MAX_AGE_DAYS = 14.0
# A median needs a population to be a median. Below this many banked residuals the
# cut is not computed and the residual guard never fires - the house discipline of
# never acting on an unreliable signal (cf. `_recently_touched`'s no-git-no-grace).
RESIDUAL_MIN_POPULATION = 8

# Lifecycle thresholds.
PROMOTE_MIN_USES = 5
PROMOTE_FITNESS = 0.60
DEPRECATE_FITNESS = 0.30
OFFERED_UNUSED = 8      # offered this often but never used => stale
# Deprecation keys on usage==0, but refining or forging a SKILL.md emits no usage
# event - so a just-improved skill reads as "never used" the same window it was
# worked, and a blind apply would deprecate the newest, most-relevant canon. The
# probation grace exempts a skill whose SKILL.md was *committed within the assess
# window* (the dream judges events since the last dream, so an edit in that same
# window is the use the telemetry missed). It is scoped to the window, not a fixed
# span, so it spares only what was actually worked. When git authorship cannot be
# read, there is no grace - never spare on an unreliable signal.

# Refinement thresholds (orthogonal to lifecycle: "needs a content rewrite").
REFINE_MIN_CONFIDENCE = 0.5  # enough evidence to trust a complaint
REFINE_QUALITY = 0.7         # measured pass/ok-rate below this counts as friction


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


# ---------------------------------------------------------------------------
# the residual store - the swapped signal, banked
# ---------------------------------------------------------------------------


def _residual_path(canon: Canon) -> Path:
    return canon.root / RESIDUAL_STORE


def load_residuals(canon: Canon) -> dict[str, Any]:
    """Read the banked query-conditioned residuals for this canon.

    Returns ``{"residuals": {name: R}, "cut": float | None, "path": str,
    "available": bool}``. Every failure mode - no store, unreadable store, bad JSON,
    too small a population - degrades to "unknown", never to a guess: the residual
    then contributes neutrally to fitness and its guard stays inert.

    ``cut`` is the MEDIAN of the whole banked population, not of whichever skills a
    given pass happens to look at. definition.md 6 registered the point: an absolute
    threshold has no image on a bounded rank statistic, and the only distribution-free
    image of a threshold under a change of signal is its QUANTILE in the population.
    Taking the median of the measurement rather than of the pass keeps that cut a
    property of the signal instead of a property of who showed up.
    """
    path = _residual_path(canon)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"residuals": {}, "cut": None, "path": str(path), "available": False}
    raw = payload.get("residuals")
    if not isinstance(raw, dict):
        return {"residuals": {}, "cut": None, "path": str(path), "available": False}
    residuals = {
        str(k): float(v) for k, v in raw.items()
        if isinstance(v, (int, float)) and not isinstance(v, bool)
    }
    cut = (
        statistics.median(residuals.values())
        if len(residuals) >= RESIDUAL_MIN_POPULATION
        else None
    )
    return {
        "residuals": residuals,
        "cut": cut,
        "path": str(path),
        "available": bool(residuals),
        "measured_at": payload.get("measured_at"),
        "source": payload.get("source"),
    }


def write_residual_cache(
    payload: dict[str, Any], canon: Canon | None = None, source: str | None = None,
) -> Path:
    """Project a ``laplace.engine.skill_residual.measure`` payload into the banked store.

    The instrument stays blind - it has no idea a lifecycle exists and must keep it
    that way (tests/test_skill_residual.py checks structurally) - so the projection
    into the decision-time store lives here, on the deciding side, where it belongs.
    """
    canon = canon or get_canon()
    residuals = {
        str(r["skill"]): float(r["residual"])
        for r in payload.get("rows", [])
        if r.get("skill") and isinstance(r.get("residual"), (int, float))
    }
    path = _residual_path(canon)
    prior = {}
    try:
        prior = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        prior = {}
    from datetime import datetime, timezone
    out = {**prior}
    out.update({
        "definition": payload.get("definition", prior.get("definition")),
        "instrument": payload.get("instrument", prior.get("instrument")),
        "source": source or prior.get("source"),
        "wall_seconds": payload.get("wall_seconds"),
        "n_skills": len(residuals),
        # every refresh wears its moment (WO-20260821-frozen-fitness-signal): the payload's
        # own stamp when the instrument carried one, this seam's UTC clock otherwise -
        # never inherited from `prior`, which is exactly the frozen number being replaced.
        "measured_at": payload.get("measured_at")
        or datetime.now(timezone.utc).isoformat(),
        "residuals": dict(sorted(residuals.items())),
    })
    path.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _recent_committed_paths(root: Any, since: str | None) -> set[str] | None:
    """Repo-relative paths committed since ``since`` (an ISO ts), or None if git is
    unavailable.

    Git commit time reflects actual content authorship, unlike file mtime which a
    fresh checkout resets uniformly. Scoping to ``since`` (the assess window start)
    keeps the grace tight - it spares only skills worked in the period being judged,
    not every skill an active repo committed in some fixed span. None means "unknown",
    and callers fall back to mtime rather than guessing.
    """
    from laplace.core import versioning as gitio

    # Pure-Python git (Dulwich): non-root commits since the window start, with
    # the changed paths. No subprocess, so no fsmonitor-daemon pipe to deadlock
    # on. None means "git unavailable" and the caller grants no grace.
    return gitio.log_paths_since(root, since)


def _recently_touched(sk: Any, recent: set[str] | None) -> bool:
    """Was this skill's SKILL.md committed within the assess window?

    Conservative: when git authorship is unavailable (recent is None), there is no
    grace. mtime reflects a checkout, not authorship, so it would wrongly spare every
    skill in a fresh clone - better no grace than a false one.
    """
    if not recent:
        return False
    suffix = f"skills/{sk.name}/SKILL.md"
    return any(p.endswith(suffix) for p in recent)


def _skill_signals(name: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    usage = 0
    offered = 0
    verify_pass = verify_total = 0
    exec_ok = exec_total = 0
    feedback = 0
    retention_obs: list[float] = []

    for ev in events:
        phase = ev.get("phase")
        if phase == "orient" and name in (ev.get("offered") or []):
            offered += 1
        elif phase == "execute" and ev.get("skill") == name:
            usage += 1
            # A script run carries an `ok` outcome and scores exec quality. A bare
            # protocol fetch (no `ok`) counts as usage only, leaving quality neutral
            # until a real verify/feedback outcome is observed.
            if "ok" in ev:
                exec_total += 1
                if ev["ok"]:
                    exec_ok += 1
        elif phase == "verify_check" and ev.get("skill") == name:
            usage += 1
            verify_total += 1
            if ev.get("passed"):
                verify_pass += 1
        elif phase == "feedback" and ev.get("skill") == name:
            feedback += int(ev.get("signal", 0))
        elif phase == "retention" and ev.get("skill") == name:
            retention_obs.append(float(ev.get("value", 0.5)))

    return {
        "usage": usage,
        "offered": offered,
        "verify_pass": verify_pass,
        "verify_total": verify_total,
        "exec_ok": exec_ok,
        "exec_total": exec_total,
        "feedback": feedback,
        "retention_obs": retention_obs,
    }


def _fitness(sig: dict[str, Any], residual: float | None = None) -> dict[str, Any]:
    """Fitness, with the query-conditioned residual in the seat usage-count held.

    ``residual`` is R = 1 - MRR in (0, 1] from the banked store, or None when the skill
    has no banked measurement. Polarity is D1: R enters POSITIVELY - high residual means
    the skill demands investment, and demanding investment lifts fitness exactly as a
    high usage count used to. An unknown residual is neutral (0.5), the same convention
    quality and retention already use, and is reported as unknown rather than guessed.

    Usage-count is computed and returned beside it - `usage_norm`, and `usage_fitness`,
    the number the incumbent formula would have produced - so the swap can be audited on
    every live row instead of only in the replay bundle.
    """
    usage_norm = min(1.0, sig["usage"] / USAGE_SAT)
    residual_known = residual is not None
    residual_norm = float(residual) if residual_known else 0.5

    quals = []
    if sig["verify_total"]:
        quals.append(sig["verify_pass"] / sig["verify_total"])
    if sig["exec_total"]:
        quals.append(sig["exec_ok"] / sig["exec_total"])
    quality = sum(quals) / len(quals) if quals else 0.5  # neutral when unknown

    feedback_norm = (_clamp(sig["feedback"], -3, 3) + 3) / 6
    retention = (
        sum(sig["retention_obs"]) / len(sig["retention_obs"])
        if sig["retention_obs"]
        else 0.5
    )

    rest = (
        W_QUALITY * quality
        + W_FEEDBACK * feedback_norm
        + W_RETENTION * retention
    )
    fitness = W_RESIDUAL * residual_norm + rest
    usage_fitness = W_RESIDUAL * usage_norm + rest      # the incumbent, kept as a witness

    samples = sig["usage"] + abs(sig["feedback"])
    confidence = min(1.0, samples / CONF_SAT)
    return {
        "fitness": round(fitness, 3),
        # The ORDERING is where the residual's information lives - R runs 0.7371..0.9998
        # with a median of 0.9948, so neighbouring skills differ in the 4th decimal and a
        # 3-dp round collapses them into ties. `fitness` stays 3-dp because it is what gets
        # read, quoted in reasons, and banked into lifecycle.yaml; anything that RANKS
        # (this module's own sort, the replay parity fixture) must read `fitness_exact`.
        "fitness_exact": fitness,
        "quality": round(quality, 3),
        "usage_norm": round(usage_norm, 3),
        "confidence": round(confidence, 3),
        # the swapped signal, and the demoted one, side by side
        "residual": round(residual_norm, 6) if residual_known else None,
        "residual_known": residual_known,
        "usage_fitness": round(usage_fitness, 3),
    }


def _has_genuine_negative_outcome(sig: dict[str, Any]) -> bool:
    """True only when there is a concrete negative outcome, not merely silence.

    Absence of positive laplace_log feedback is normal - the author rarely
    vocalises praise. A skill must not be down-ranked for silence. Only act
    on explicit negative feedback OR a measured low pass/ok-rate.
    """
    if sig["feedback"] < 0:
        return True
    if sig["verify_total"] and (sig["verify_pass"] / sig["verify_total"]) < DEPRECATE_FITNESS:
        return True
    if sig["exec_total"] and (sig["exec_ok"] / sig["exec_total"]) < DEPRECATE_FITNESS:
        return True
    return False


def _structural_skills(canon: Canon) -> set[str]:
    """Skills the documented architecture leans on - referenced by a GLOBAL wiki
    node (a workflow / structure / aesthetics page) or by a ``core`` skill.

    Such a skill is *structural*: it is unused only because the active project
    has not reached the stage that exercises it (a literature rail is dormant
    during a figure phase), not because it failed. It must never be deprecated on
    silence alone - only on a genuine negative outcome. This is the structural
    backstop behind the "silence is not dissatisfaction" principle, and it stops
    the deprecate-on-silence path from eating backbone skills (literature_scout,
    reconciler, corpus_librarian) that the global workflow nodes still link to.

    Only GLOBAL-scope wiki nodes confer protection - a domain page that merely
    name-drops a skill as "deprecated, awaiting revival" (e.g. the web axioms on
    css_forge) is prose, not architecture, and must not shield it.
    """
    try:
        from laplace.pipeline import graph as _graph

        g = _graph.CanonGraph.from_canon(canon, with_fitness=False)  # no fitness: avoid assess recursion
    except Exception:  # noqa: BLE001 - the guard is an enrichment, never a hard dep
        return set()
    core_ids = {f"skill:{n}" for n, sk in canon.skills.items() if sk.status == "core"}
    protected: set[str] = set()
    for e in g.edges:
        if e.rel != "links_to" or not e.dst.startswith("skill:"):
            continue
        src = g.nodes.get(e.src)
        src_global_wiki = src is not None and src.kind == "wiki" and (src.meta or {}).get("scope") == "global"
        if src_global_wiki or e.src in core_ids:
            protected.add(e.dst[len("skill:"):])
    return protected


def _investment_reason(sig: dict[str, Any], fit: dict[str, Any]) -> str:
    return (
        f"DEMANDS INVESTMENT: offered {sig['offered']}x, never used - but its own claimed "
        f"tasks cannot route to it (residual {fit['residual']}, above the banked population "
        f"median). Invisible, which is not the same as unfit: the silence is what usage-count "
        f"reads as failure and the residual reads as a findability debt to pay (D1 "
        f"PV-20260820T223000Z)"
    )


def _recommend(
    status: str, sig: dict[str, Any], fit: dict[str, Any],
    recently_touched: bool = False, is_protected: bool = False,
    demands_investment: bool = False,
) -> tuple[str, str]:
    """Return (recommended_status, reason). Conservative: only act on evidence.

    Absence of positive feedback is treated as neutral, not negative. A skill
    is only down-ranked when there is a genuine negative outcome: explicit
    negative laplace_log signals or a measured low verify/exec pass-rate. A
    *structural* skill (referenced by the canon) is never deprecated on silence.

    ``demands_investment`` is the residual guard (2026-08-20): the skill's banked
    query-conditioned residual sits above the population median, so under D1 the silence
    that would have deprecated it reads as "cannot be found when needed", not as "unfit".
    It BLOCKS the two silence-demotion paths and nothing else. Deliberately asymmetric:
    the residual can spare, but it cannot promote on its own - PROMOTE_MIN_USES is left
    standing, because unfreezing a promoter that can raise a never-used skill to core on a
    findability score is a much larger act than the one his bar ratified, and it is his.
    """
    usage = sig["usage"]
    fitness = fit["fitness"]

    if status == "deprecated":
        # Resurrect if it is suddenly being used well again.
        if usage >= PROMOTE_MIN_USES and fitness >= PROMOTE_FITNESS:
            return "experimental", f"deprecated skill used again ({usage}x, fit {fitness})"
        return "deprecated", "remains unused"

    if status == "experimental":
        if usage >= PROMOTE_MIN_USES and fitness >= PROMOTE_FITNESS:
            return "core", f"earned promotion: {usage} uses, fitness {fitness}"
        # Structural promotion (the symmetric counterpart to no-deprecate-on-silence).
        # A skill referenced by a global wiki node or a core skill is load-bearing by
        # architecture: its place in the engine is established by the link, not by a
        # usage count it cannot accrue while phase-dormant. Such a skill (context_firewall,
        # reconciler, corpus_librarian) is surfaced at orient yet emits no `execute`
        # event, so PROMOTE_MIN_USES is never met and it reads "probationary" forever.
        # If it is a live architectural participant (offered) and shows no genuine
        # negative outcome, it has earned core: silence is not unfitness, and a backbone
        # the documented architecture depends on should not sit on probation indefinitely.
        if (
            is_protected
            and not recently_touched
            and sig["offered"] >= OFFERED_UNUSED
            and not _has_genuine_negative_outcome(sig)
        ):
            return "core", f"structural (canon-referenced), offered {sig['offered']}x, no negative outcome: earned core on standing, not count"
        if sig["offered"] >= OFFERED_UNUSED and usage == 0:
            if recently_touched:
                return "experimental", f"offered {sig['offered']}x, unused but newly forged/refined (grace)"
            if demands_investment:
                return "experimental", _investment_reason(sig, fit)
            return "deprecated", f"offered {sig['offered']}x, never used"
        # Down-rank only on genuine negative outcomes, never mere silence.
        if usage >= PROMOTE_MIN_USES and fitness < DEPRECATE_FITNESS and _has_genuine_negative_outcome(sig):
            return "deprecated", f"used but low fitness {fitness} (genuine negative outcome)"
        return "experimental", "still on probation"

    # status == core
    # Down-rank only on genuine negative outcomes, never mere silence.
    if usage >= PROMOTE_MIN_USES and fitness < DEPRECATE_FITNESS and _has_genuine_negative_outcome(sig):
        return "deprecated", f"core skill degraded to fitness {fitness} (genuine negative outcome)"
    if sig["offered"] >= OFFERED_UNUSED * 2 and usage == 0 and not recently_touched and not is_protected:
        if demands_investment:
            return "core", _investment_reason(sig, fit)
        return "deprecated", f"core skill fell out of use (offered {sig['offered']}x)"
    return "core", "healthy"


def _refine(status: str, sig: dict[str, Any], fit: dict[str, Any]) -> dict[str, Any]:
    """Does a *trusted* skill show friction worth a content rewrite?

    This is orthogonal to lifecycle. Frequent use does not by itself call for
    refinement - it makes a *complaint* trustworthy. So the refine signal fires
    only when confidence is high enough (the skill is genuinely exercised) AND a
    *measured* quality rate is poor or feedback is net-negative. The neutral
    "unknown quality" default (no verify/exec data) never triggers it.

    refine_signal = confidence x worst measured friction. This is exactly why a
    high-usage, low-quality skill - which lifecycle calls "healthy" because usage
    props up its fitness - still surfaces here: usage makes the bad quality
    *believed*, not excused.
    """
    if status == "deprecated" or fit["confidence"] < REFINE_MIN_CONFIDENCE:
        return {"needs_refine": False, "refine_signal": 0.0, "refine_reason": None}
    frictions: list[float] = []
    reasons: list[str] = []
    if sig["verify_total"]:
        rate = sig["verify_pass"] / sig["verify_total"]
        if rate < REFINE_QUALITY:
            frictions.append(REFINE_QUALITY - rate)
            reasons.append(f"verify pass-rate {round(rate, 3)}")
    if sig["exec_total"]:
        rate = sig["exec_ok"] / sig["exec_total"]
        if rate < REFINE_QUALITY:
            frictions.append(REFINE_QUALITY - rate)
            reasons.append(f"script ok-rate {round(rate, 3)}")
    if sig["feedback"] < 0:
        frictions.append(min(1.0, -sig["feedback"] / 3))
        reasons.append(f"net feedback {sig['feedback']}")
    if not frictions:
        return {"needs_refine": False, "refine_signal": 0.0, "refine_reason": None}
    return {
        "needs_refine": True,
        "refine_signal": round(fit["confidence"] * max(frictions), 3),
        "refine_reason": "; ".join(reasons),
    }


def assess(canon: Canon | None = None, session: str | None = None, since: str | None = None) -> dict[str, Any]:
    """Compute the fitness report and lifecycle recommendations for all skills."""
    canon = canon or get_canon()
    _META = {"dream_complete"}
    # The DAY window (``since`` is the last dream's ts) is taken POSITIONALLY - the
    # events after the most recent dream_complete marker - not by a ``ts >= since``
    # compare. A coarse wall clock stamps the marker and the events in its tick with
    # identical timestamps, so a ts compare leaks a pre-marker event into the day (E3');
    # slicing after the marker's position is immune (see telemetry.events_since_last_dream).
    # ``since`` (the marker ts) is still used below to scope the git-authorship grace.
    # ``since is None`` is the cumulative STANDING: every event. Reading the window this
    # one way keeps the open (assess) and the close (dream) conjugate at each grade.
    raw = (telemetry.events_since_last_dream(session=session)
           if since is not None else telemetry.events(since_session=session))
    evs = [ev for ev in raw if ev.get("phase") not in _META]
    skills_report: list[dict[str, Any]] = []
    transitions: list[dict[str, Any]] = []

    recent = _recent_committed_paths(canon.root, since)
    protected = _structural_skills(canon)
    residual_store = load_residuals(canon)
    residuals, cut = residual_store["residuals"], residual_store["cut"]
    # THE AGE GATE (WO-20260821-frozen-fitness-signal): a residual past the declared bound
    # refuses `known` for every skill - fitness degrades to the neutral-unknown convention
    # it already has, and the report says WHY loudly (residual_age_days + stale, below).
    # A banked number with no moment at all cannot claim known either: an unstamped or
    # unparseable measured_at is stale on its face (M-numbers-name-their-referents).
    residual_age_days: float | None = None
    residual_stale = False
    _measured = residual_store.get("measured_at")
    if _measured:
        try:
            from datetime import datetime, timezone
            _age = datetime.now(timezone.utc) - datetime.fromisoformat(str(_measured))
            residual_age_days = round(_age.total_seconds() / 86400.0, 2)
            residual_stale = residual_age_days > RESIDUAL_MAX_AGE_DAYS
        except ValueError:
            residual_stale = True
    else:
        residual_stale = bool(residuals)
    if residual_stale:
        residuals, cut = {}, None
    for name, sk in canon.skills.items():
        sig = _skill_signals(name, evs)
        residual = residuals.get(name)
        fit = _fitness(sig, residual)
        fit["residual_age_days"] = residual_age_days   # beside residual_known, every row
        demands_investment = (
            cut is not None and residual is not None and residual >= cut
        )
        recently_touched = _recently_touched(sk, recent)
        rec, reason = _recommend(
            sk.status, sig, fit, recently_touched, name in protected, demands_investment,
        )
        # THE ALARM. Run the demoted signal through the same recommender and keep the
        # answer: `incumbent_status` is what usage-count would have decided, and the two
        # are compared at the DECISION, not at the scalar. The scalar comparison would
        # fire on almost every row - R is compressed near 1 across the population, so the
        # residual term is nearly constant in level and carries its information in the
        # ORDERING (definition.md 6, which is why the guard is a quantile). A disagreement
        # that never reaches a decision is noise; this one always means the swap changed
        # what the promoter would do.
        incumbent_status, incumbent_reason = _recommend(
            sk.status, sig, {**fit, "fitness": fit["usage_fitness"]},
            recently_touched, name in protected, demands_investment=False,
        )
        ref = _refine(sk.status, sig, fit)
        # Keep "healthy" honest: a kept skill that needs a rewrite says so.
        if ref["needs_refine"] and rec == sk.status:
            reason = f"{reason} (refine: {ref['refine_reason']})"
        row = {
            "name": name,
            "status": sk.status,
            "recommended_status": rec,
            "reason": reason,
            "usage": sig["usage"],
            "offered": sig["offered"],
            "verify_pass_rate": (
                round(sig["verify_pass"] / sig["verify_total"], 3)
                if sig["verify_total"]
                else None
            ),
            "feedback": sig["feedback"],
            "demands_investment": demands_investment,
            "incumbent_status": incumbent_status,
            "signal_disagreement": incumbent_status != rec,
            **fit,
            **ref,
        }
        skills_report.append(row)
        if rec != sk.status:
            transitions.append(
                {"name": name, "from": sk.status, "to": rec, "reason": reason}
            )

    skills_report.sort(key=lambda r: r["fitness_exact"], reverse=True)
    return {
        "events_seen": len(evs),
        "skills": skills_report,
        "transitions": transitions,
        "unused": [r["name"] for r in skills_report if r["usage"] == 0],
        # The swapped signal's own provenance, so a reader of the report can see WHICH
        # signal decided without opening the store.
        "residual_signal": {
            "store": residual_store["path"],
            "available": residual_store["available"],
            "measured_at": residual_store.get("measured_at"),
            "source": residual_store.get("source"),
            "population": len(residuals),
            "cut": cut,
            "known_this_pass": sum(1 for r in skills_report if r["residual_known"]),
            "polarity": "D1 PV-20260820T223000Z - high residual = demands investment",
            # the age gate's own account (WO-20260821-frozen-fitness-signal): how old the
            # banked measurement is, the declared bound, and whether staleness refused it
            "residual_age_days": residual_age_days,
            "max_age_days": RESIDUAL_MAX_AGE_DAYS,
            "stale": residual_stale,
        },
        # The alarm, not a footnote: every skill the swap decides differently from the
        # signal it replaced. An empty list means the swap changed nothing this pass; a
        # populated one is the promoter acting on the new signal's own content, named
        # skill by skill with both answers, so a disagreement can never pass as agreement.
        "signal_disagreements": [
            {
                "name": r["name"],
                "residual_says": r["recommended_status"],
                "usage_says": r["incumbent_status"],
                "from": r["status"],
                "usage": r["usage"],
                "offered": r["offered"],
                "residual": r["residual"],
                "reason": r["reason"],
            }
            for r in skills_report if r["signal_disagreement"]
        ],
        "demands_investment": [r["name"] for r in skills_report if r["demands_investment"]],
        "refine_recommended": [
            {
                "name": r["name"],
                "refine_signal": r["refine_signal"],
                "refine_reason": r["refine_reason"],
            }
            for r in sorted(
                skills_report, key=lambda r: r["refine_signal"], reverse=True
            )
            if r["needs_refine"]
        ],
    }
