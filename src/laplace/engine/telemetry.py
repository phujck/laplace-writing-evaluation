"""Telemetry ledger: the durable, append-only record of loop activity.

Every orient/execute/verify call appends a structured event here. This log is the
substrate the endogenous assessment reads to compute skill fitness, which in turn
governs the dreamer's silent promotions and deprecations.

Storage is a JSONL file under the state dir (``LAPLACE_STATE`` or
``~/.mcp-gerard/laplace``). Append-only and cheap; the audited, revertible record
of *canon edits* lives in the canon git history (see dreamer.py), not here.
"""

from __future__ import annotations
from laplace.core.checkout import package_root
from laplace.core.checkout import state_root

import itertools
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def state_dir() -> Path:
    d = state_root()
    d.mkdir(parents=True, exist_ok=True)
    return d


def telemetry_path() -> Path:
    """This session's telemetry shard - the file ``log`` appends to.

    Per-session sharding is the lock-free serialisation of the substrate: each
    drive of the loop writes only to its own file, so concurrent agents (each a
    distinct session) never interleave appends into one file. An interleaved
    line is the corruption ``events`` silently drops as unparseable - which would
    make the co-activation count quietly undercount, and a lossy substrate bounds
    every later component (Component 1). Reads merge every shard; see
    :func:`_all_shards`.
    """
    return state_dir() / f"telemetry.{session_id()}.jsonl"


def _all_shards() -> list[Path]:
    """Every telemetry shard, plus the legacy single file, for a merged read.

    ``telemetry.<session>.jsonl`` shards (two dots) plus the historic
    ``telemetry.jsonl`` (one dot, never matched by the shard glob) so a record
    written before sharding is never orphaned.
    """
    d = state_dir()
    shards = sorted(d.glob("telemetry.*.jsonl"))
    legacy = d / "telemetry.jsonl"
    if legacy.exists():
        shards.append(legacy)
    return shards


# A session id groups events from one drive of the loop. Override per host client
# via LAPLACE_SESSION; otherwise one id per server process.
_SESSION = os.environ.get("LAPLACE_SESSION") or uuid.uuid4().hex[:12]

# A monotonic per-process sequence number, stamped on every event by ``log``. It is
# the tie-breaker that makes event ORDER exact when the wall clock cannot: the ISO
# ``ts`` is coarse on some platforms (Windows ~16ms), so several events logged in one
# tick share a timestamp. ``seq`` orders those by append order, so a window taken
# strictly AFTER a marker (see :func:`events_since_last_dream`) never leaks an event
# that merely shares the marker's tick. It resets per process; cross-process order
# still falls to ``ts`` (distinct in practice, as sessions run at different times).
_SEQ = itertools.count(1)


def session_id() -> str:
    return os.environ.get("LAPLACE_SESSION") or _SESSION


def log(phase: str, **fields: Any) -> dict[str, Any]:
    """Append one event and return it."""
    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "seq": next(_SEQ),
        "session": session_id(),
        "phase": phase,
        **fields,
    }
    path = telemetry_path()
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def coactivation(bundle: dict[str, Any]) -> list[str]:
    """The set of canon nodes that fired together for one goal.

    The co-activation record: the nodes ``orient`` marked relevant for a goal -
    the matched foundation nodes plus the active domain's nodes - and not the
    always-offered global refs, which are constant and so carry no signal. Banked
    per orient on the ``orient`` event (field ``activated``), this is the raw
    substrate a later growth rule reads to decide which nodes consistently
    co-activate and should be grouped into a new layer (see EIGEN_ARCHITECTURE.md,
    Component 1). Cheap to log, impossible to recover if not logged - so it is
    banked now, ahead of the analyser that will read it.
    """
    refs: list[str] = []
    for item in bundle.get("foundation", []):
        # A node co-activates because it MATCHED the goal - grade-independent.
        # ``relevant`` is the grade-local marker; ``content`` is the legacy marker,
        # kept so telemetry banked before the graded orient still parses.
        if isinstance(item, dict) and item.get("ref") and (
            item.get("relevant") or "content" in item
        ):
            refs.append(item["ref"])
    for item in bundle.get("domain_context", []):
        if isinstance(item, dict) and item.get("ref"):
            refs.append(item["ref"])
    return refs


# Outcome fates for a retention event - did the work survive contact with the artifact.
# survived != earned: a *kept* line may merely be safe, and a line *rewritten toward the
# line* is the craft working, not a loss - only a *bypass* (hand-corrected away, routed
# around) is a real loss. The mapped value is the outcome weight a future analyser joins to
# a co-activation (the link Component 1 was missing). It is fed to a skill's fitness only
# when a ``skill`` is named; the default (no skill) banks the outcome without touching any
# fitness gradient, so microexpression work stays off the gradient until the signal can tell
# a rewrite from a bypass.
RETENTION_FATES: dict[str, float] = {"kept": 0.9, "rewritten": 0.6, "bypassed": 0.2}


def retention(
    fate: str,
    skill: str | None = None,
    nodes: list[str] | None = None,
    reason: str = "",
    artifact: str = "",
    source: str = "author",
) -> dict[str, Any]:
    """Log one retention outcome at session close.

    ``fate`` is one of :data:`RETENTION_FATES`. ``skill`` is optional and, when
    given, makes the outcome count toward that skill's fitness (``assess``); leave
    it ``None`` (the default) to bank the outcome for the analyser without touching
    any fitness gradient. ``nodes`` echoes the co-activation set this outcome
    scopes, for the later co-activation x retention join. ``source`` names WHERE the
    fate was read: the default ``"author"`` is the session-close hand-judgement; a
    ``"door"`` outcome is banked mechanically by an approved cockpit door (the
    evolution desk's ratify/reject apply), so the analyser can separate a judged
    retention from a doored one. It rides every event; existing call sites keep the
    default, so their calls stay compatible.
    """
    if fate not in RETENTION_FATES:
        raise ValueError(
            f"unknown retention fate {fate!r}; expected one of {sorted(RETENTION_FATES)}"
        )
    fields: dict[str, Any] = {"fate": fate, "value": RETENTION_FATES[fate],
                              "source": source}
    if reason:
        fields["reason"] = reason
    if skill is not None:
        fields["skill"] = skill
    if nodes:
        fields["activated"] = list(nodes)
    if artifact:
        fields["artifact"] = artifact
    return log("retention", **fields)


# Fidelity fates for a reconstruction event - how faithfully a digest rebuilt its source.
# This is the *inverse* of digestion scored: a session (or any object) is digested into the
# conceptric, then a blind, context-starved agent is asked to reconstruct it from the digest
# ALONE. The fate is how the rebuilt ghost compared to the original (held in archival storage,
# never in the working store). It mirrors RETENTION_FATES on purpose - the same survived-vs-earned
# axis, read on memory: a *faithful* ghost means the digest carried the object; a *partial* ghost
# means the spine survived but the flesh was lost (the rewrite-toward-the-line analogue, the craft
# of compression working, not a loss); a *confabulated* ghost asserted what was never in the source
# or mis-placed it (the dangerous loss - the confident wrong placement, the microexpression defect
# at the retrieval layer). The ``activated`` field is the reinforcement signal the author named:
# the nodes/stubs a reconstruction *called*, banked every time, so ghosts summoned again and again
# accrete in the activation history the growth-rule analyser reads to restructure (Component 1->2).
RECONSTRUCTION_FATES: dict[str, float] = {"faithful": 0.9, "partial": 0.6, "confabulated": 0.2}

# The DERIVED fates codebook (F14): the empirically-read vocabulary that layers OVER the frozen base
# above. RECONSTRUCTION_FATES is the settled three, hard-coded and byte-stable - the floor that holds
# in a base-only clone. The codebook is where a fate GRADUATES from candidate to stampable once the
# batch occupies its cell (enriched today, others tomorrow), so the stampable set is the base merged
# with the codebook's NON-CANDIDATE fates, resolved at call time rather than frozen here.
_FATES_CODEBOOK = (package_root() / "pipeline" / "canon" / "skills"
                   / "reconstruction_fitness" / "fates_codebook.json")


def reconstruction_fates() -> dict[str, float]:
    """The stampable fate->value map: the frozen base merged with the codebook's settled fates.

    The base (:data:`RECONSTRUCTION_FATES`) is always present. When the codebook artifact resolves,
    its NON-candidate fates are layered on (value from the codebook); a ``candidate: true`` fate -
    an unoccupied cell asserted from no datum - is NOT stampable and is deliberately withheld, so a
    caller that names it still raises. The merge is tolerant of the artifact's absence: a base-only
    environment returns exactly the frozen three, byte-identical. Since the derived settled fates
    carry the base weights, the current merged view equals the base - F14 wires the MECHANISM (the
    cell graduates when occupied), it does not move today's map.
    """
    merged = dict(RECONSTRUCTION_FATES)
    try:
        data = json.loads(_FATES_CODEBOOK.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return merged
    for name, spec in (data.get("fates") or {}).items():
        if not isinstance(spec, dict) or spec.get("candidate"):
            continue
        val = spec.get("value")
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            merged[name] = float(val)
    return merged


def reconstruction(
    fate: str | None = None,
    target: str = "",
    caller: str = "eigen",
    nodes: list[str] | None = None,
    gap: str = "",
    reason: str = "",
    cycle: int = 0,
    similarity: float | None = None,
) -> dict[str, Any]:
    """Log one reconstruction-call event - the reinforcement record of memory recall.

    ``target`` is the object reconstructed (a session id, a conceptric node). ``caller`` is
    who summoned the ghost - ``"eigen"`` or a spawned sub-agent's id - so the activation history
    counts calls from the orchestrator AND its guides (the author's "telemetry of you and your
    sub-agents"). In the tripartite self-judgement loop the three roles each log with their own
    ``caller`` (``"digester"`` / ``"ghost"`` / ``"adjudicator"``) and a shared ``cycle`` index, so
    one full convergence loop is a readable trace. ``nodes`` is the digest stubs / conceptric nodes
    the reconstruction *called*, the co-activation-style reinforcement substrate; it is logged every
    time, even before a fidelity verdict, because the call itself is the signal that the path was
    worth walking. ``fate`` (one of :data:`RECONSTRUCTION_FATES`) is the judged fidelity, set by the
    blind adjudicator when it compares ghost to archived original; ``similarity`` is the cheap
    mechanical proxy (token overlap) banked alongside it; ``gap`` records what could not be rebuilt -
    the residue that is the spec for the reconstruction-key the digest failed to carry. ``fate`` is
    optional so a call can be banked at summon time and scored later, the way history accumulates
    ahead of judgement.
    """
    fates = reconstruction_fates()
    if fate is not None and fate not in fates:
        raise ValueError(
            f"unknown reconstruction fate {fate!r}; expected one of {sorted(fates)}"
        )
    fields: dict[str, Any] = {"caller": caller, "cycle": cycle}
    if target:
        fields["target"] = target
    if fate is not None:
        fields["fate"] = fate
        fields["value"] = fates[fate]
    if similarity is not None:
        fields["similarity"] = round(float(similarity), 4)
    if nodes:
        fields["activated"] = list(nodes)
    if gap:
        fields["gap"] = gap
    if reason:
        fields["reason"] = reason
    return log("reconstruction", **fields)


# Consistency verdicts for one cross-level supplier->producer judgement - the
# "judgement is the supply channels run backward" axis (EIGEN_ARCHITECTURE.md). Every
# node that *supplied* context is the oracle for what the producer did with it, and its
# verdict is one question: is what came back consistent with what I'd expect from what I
# gave you? The supplier holds the context-on-the-context, so it can catch *intent-drift*
# (``drifted``), not merely literal inconsistency. The mapped weight is the score a future
# fitness rule joins; it deliberately mirrors the other fate maps' survived-vs-earned axis.
TRACE_VERDICTS: dict[str, float] = {"consistent": 0.9, "drifted": 0.5, "inconsistent": 0.2}


def trace(
    span: str,
    caller: str = "eigen",
    role: str = "",
    request: str = "",
    spawned: list[str] | None = None,
    consulted: list[str] | None = None,
    returned: str = "",
    verdict: str | None = None,
    by: str = "",
    cycle: int = 0,
    reason: str = "",
) -> dict[str, Any]:
    """Log one node in the network trace - the shape the author named (2026-06-05).

    The recursive self-similar loop produces a TRACE: *what went where in response to an
    input, what came back, and how each level judged the output of the others.* This is the
    producer for that shape, banked ahead of its consumer the way the co-activation and
    reconstruction records were - the statistics of the consistency-verdicts accrued here
    are, over the long horizon, the **endogenous fitness** (Component 5), which is the
    author's fork, so this scaffolds the SHAPE only and computes nothing.

    One ``trace`` event records one segment of the loop:

    - ``span`` names the segment (e.g. ``"orchestrate"``, ``"spawn"``, ``"judge"``), and
      ``cycle`` groups the segments of one loop into a readable run, as ``reconstruction``
      groups its tripartite cycle.
    - ``caller`` / ``role`` are who drove this segment and the role it bound to (the
      role-first binding the spawn shape will carry; see R0). ``request`` is the input that
      entered the segment - the low-density instruction or the routed sub-instruction.
    - ``spawned`` is the sub-processes started (their ids), ``consulted`` the context nodes
      pulled on (the supply channels), ``returned`` a handle to what came back. Together
      these are *input -> what was spawned/consulted -> what returned*.
    - ``verdict`` (one of :data:`TRACE_VERDICTS`) is *the supplier's* consistency-verdict on
      what came back, and ``by`` names the supplier that judged (a level, an id, or
      ``"author"`` while the external loop is still the fitness function). It is optional: a
      segment can be banked when it fires and judged later, the way history accrues ahead of
      the verdict.

    Cheap to log, impossible to recover if not logged - so the shape is banked now, ahead
    of the converger that will read it. No consumer reads this yet, by design.
    """
    if verdict is not None and verdict not in TRACE_VERDICTS:
        raise ValueError(
            f"unknown trace verdict {verdict!r}; expected one of {sorted(TRACE_VERDICTS)}"
        )
    fields: dict[str, Any] = {"span": span, "caller": caller, "cycle": cycle}
    if role:
        fields["role"] = role
    if request:
        fields["request"] = request
    if spawned:
        fields["spawned"] = list(spawned)
    if consulted:
        fields["consulted"] = list(consulted)
    if returned:
        fields["returned"] = returned
    if verdict is not None:
        fields["verdict"] = verdict
        fields["value"] = TRACE_VERDICTS[verdict]
    if by:
        fields["by"] = by
    if reason:
        fields["reason"] = reason
    return log("trace", **fields)


# Halt states for one convergence decision over a wake-sleep cycle sequence - the loop-level
# verdict that sits ABOVE the per-ghost reconstruction fate. The spectral radius of the wake-sleep
# map governs it (rho < 1 contracts, rho ~ 1 is the edge of chaos, rho >= 1 runs away); the policy
# compares the estimate to a grade-and-kind-dependent target rho*. Each event is banked with
# (grade, kind, rho, rho_star) so a failed reconstruction is DIAL-ATTRIBUTABLE - the author's "we
# know which dial to nudge before the next round of ingestion." The optimal rho* is F1 (the
# endogenous fitness eigenvalue psi = log_n lambda_0); this producer scaffolds the shape and
# computes nothing - the rule is the fork, fed by the statistics accrued here.
HALT_STATES: tuple[str, ...] = (
    "converged-faithful",
    "converged-degenerate",
    "oscillating",
    "open",
)


def convergence(
    state: str,
    grade: str = "",
    kind: str = "",
    cycle: int = 0,
    rho: float | None = None,
    rho_star: float | None = None,
    target: str = "",
    reason: str = "",
) -> dict[str, Any]:
    """Log one loop-level halt decision - the dial-attributable convergence record.

    ``state`` is one of :data:`HALT_STATES`. ``rho`` is the estimated spectral radius (the
    contraction rate read off successive lost-set deltas), ``rho_star`` the policy target it was
    judged against; banking both makes a failure point at its dial (rho too high on a factual node
    -> nudge rho* down; collapsed on a generative node -> nudge rho* up). ``target`` names the
    object/node. Banked ahead of its consumer (F1), the way the other producers were.
    """
    if state not in HALT_STATES:
        raise ValueError(
            f"unknown halt state {state!r}; expected one of {list(HALT_STATES)}"
        )
    fields: dict[str, Any] = {"state": state, "cycle": cycle}
    if grade:
        fields["grade"] = grade
    if kind:
        fields["kind"] = kind
    if rho is not None:
        fields["rho"] = round(float(rho), 4)
    if rho_star is not None:
        fields["rho_star"] = round(float(rho_star), 4)
    if target:
        fields["target"] = target
    if reason:
        fields["reason"] = reason
    return log("convergence", **fields)


def adjudication(
    target: str = "",
    n: int = 0,
    lost: int = 0,
    added: int = 0,
    structured: bool | None = None,
    recurses: bool | None = None,
    agreement: float | None = None,
    faithfulness: float | None = None,
    passed: bool | None = None,
    caller: str = "adjudicator-sealed",
    cycle: int = 0,
    reason: str = "",
) -> dict[str, Any]:
    """Log one sealed semantic adjudication - the meter's raw signals, ahead of its consumer (F1).

    This is the G1 successor to the void 2-shingle proxy logged by ``reconstruction(fate=...)``.
    The sealed adjudicator emits NO fate label (FORK-FATES is deferred, the author's), so this
    producer banks the RAW SIGNALS instead: ``lost`` / ``added`` as counts (the content stays in
    the workdir; telemetry stays cheap), the approximate-closure booleans ``structured`` /
    ``recurses``, and the ensemble ``agreement`` (meaning lives in the joint - low agreement is the
    meter itself flagging an uncertain pair). When this records a FAITHFULNESS-GATE run rather than a
    single pair, ``faithfulness`` carries the calibration score and ``passed`` the gate verdict - the
    meter measuring itself, the precondition for it measuring anything else. ``n`` is the ensemble
    size. Banked ahead of the converger that reads it, the way every other producer here was.
    """
    fields: dict[str, Any] = {"caller": caller, "cycle": cycle, "n": n,
                              "lost": lost, "added": added}
    if target:
        fields["target"] = target
    if structured is not None:
        fields["structured"] = bool(structured)
    if recurses is not None:
        fields["recurses"] = bool(recurses)
    if agreement is not None:
        fields["agreement"] = round(float(agreement), 4)
    if faithfulness is not None:
        fields["faithfulness"] = round(float(faithfulness), 4)
    if passed is not None:
        fields["passed"] = bool(passed)
    if reason:
        fields["reason"] = reason
    return log("adjudication", **fields)


def events(since_session: str | None = None, since: str | None = None) -> list[dict[str, Any]]:
    """Read all events, optionally filtered by session id or ISO timestamp cutoff."""
    out: list[dict[str, Any]] = []
    for path in _all_shards():
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if since_session and ev.get("session") != since_session:
                continue
            if since and ev.get("ts", "") < since:
                continue
            out.append(ev)
    # Order by (ts, seq): the timestamp merges shards chronologically, and the
    # monotonic per-event seq breaks ties so same-tick events keep append order even
    # when a coarse clock stamps them identically. Legacy events predating ``seq``
    # default to -1, sorting before any seq-stamped event sharing their timestamp.
    out.sort(key=lambda e: (e.get("ts", ""), e.get("seq", -1)))
    return out


def last_dream_ts() -> str | None:
    """Return the ISO timestamp of the most recent dream_complete event, or None."""
    for ev in reversed(events()):
        if ev.get("phase") == "dream_complete":
            return ev["ts"]
    return None


def last_soul_dream_ts() -> str | None:
    """Return the ISO timestamp of the most recent soul_dream_complete event, or None.

    The CONJUGATE clock of :func:`last_dream_ts`, for the content-dreamer's own day-boundary.
    The soul-dream's day-window is the friction ledger, not telemetry (the corrections are banked
    in ``_friction.md``, read positionally), but the dream still stamps a completion marker so a
    standing run knows what it last consolidated and the cycle is dial-attributable like the canon
    dream. Kept separate from ``dream_complete`` so a canon dream never moves the soul clock and a
    soul dream never moves the canon clock - two conjugate operators, two boundaries.
    """
    for ev in reversed(events()):
        if ev.get("phase") == "soul_dream_complete":
            return ev["ts"]
    return None


def events_since_last_dream(session: str | None = None) -> list[dict[str, Any]]:
    """The DAY window: every event strictly AFTER the most recent dream_complete.

    The boundary is POSITIONAL in the merged ``(ts, seq)`` order, not a wall-clock
    ``ts >= marker`` comparison. On a coarse clock (Windows ISO resolution is ~16ms)
    the marker and the events logged in its same tick share a timestamp, so a ts
    comparison leaks a pre-marker event into the day - the day-dream then ``sees`` one
    event it has already consolidated (``events_seen`` reads 1 when it must read 0).
    Slicing after the marker's POSITION is immune: :func:`log` stamps a monotonic
    ``seq`` that orders same-tick events by append order, so the marker sorts after the
    work that preceded it and before the work that followed it. With no dream yet, the
    whole record is the day. ``session`` optionally scopes to one session's shard.

    This is the substrate half of the E3 conjugacy: both the open (``assess``) and the
    close (``dreamer.dream`` at grade 0) read THIS window, so they agree at the day-grade.
    """
    evs = events(since_session=session)
    cut = 0
    for i, ev in enumerate(evs):
        if ev.get("phase") == "dream_complete":
            cut = i + 1
    return evs[cut:]


def clear() -> None:
    """Wipe the telemetry log - every shard plus the legacy file (used by tests)."""
    for p in state_dir().glob("telemetry.*.jsonl"):
        p.unlink()
    legacy = state_dir() / "telemetry.jsonl"
    if legacy.exists():
        legacy.unlink()
