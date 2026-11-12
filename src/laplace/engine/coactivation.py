"""coactivation.py - the analyser of co-firing: telemetry of use -> the reclustering signal.

The author's rule (2026-06-08): WHEN is a new node required, and WHEN is in-grade reclustering sensible?
*The same answer as everything - telemetry of use.* Which means co-activation must be recorded BOTH
inter- and intra-grade, and read here into the pairwise co-fire counts the recursive dreamer rewires on.

This is the CONSUMER the telemetry PRODUCERS were banked ahead of (``telemetry.reconstruction`` /
``telemetry.coactivation`` already log the ``activated`` sets - "Component 1, banked ahead of the
analyser that will read it"). What was missing: the activated sets were flat, so inter-grade could not be
told from intra-grade. The keeper ring now records each co-fired node with its grade (``record``), and
this module reads those sets into:

  * **intra-grade co-fire** - two nodes at the SAME grade fire together -> a new in-grade cluster is
    sensible (the sibling-merge / new-node signal);
  * **inter-grade co-fire** - a node and one at another grade fire together -> the cross-grade LINK is
    real and should be strengthened (the conjugate of the static coupling in ``keeper_ring.coupling``:
    that is shared substrate, this is co-firing IN USE).

It computes the SIGNAL only. Whether to ACT on a candidate (mutate the graded tree) is the recursive
dreamer's step, gated by the author's endogenous fitness rule (F1) - never an automatic restructure.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

from laplace.engine import telemetry

_PAIR_CAP = 48     # bound the activated set per event before pairing (keeps the analyser sub-O(N^2)-runaway)


def _norm_activated(activated: Iterable[Any]) -> list[tuple[str, int]]:
    """Accept ``[(id, grade), ...]`` or ``[{'id':..,'grade':..}, ...]`` -> a clean ``[(id, grade)]``,
    de-duplicated by id (a node that recurs in one reconstruction co-fires once, not N times)."""
    seen: dict[str, int] = {}
    for item in activated or []:
        if isinstance(item, dict):
            nid, g = item.get("id"), item.get("grade", 0)
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            nid, g = item[0], item[1]
        else:
            nid, g = item, 0
        if nid:
            seen[str(nid)] = int(g or 0)
    return list(seen.items())


# ---------------------------------------------------------------------------
# record - one reconstruction's grade-tagged co-fire set (the producer, grade-aware)
# ---------------------------------------------------------------------------

def record(activated: Iterable[Any], caller: str = "eigen", goal: str = "") -> dict[str, Any] | None:
    """Bank one reconstruction's co-fire set, GRADE-TAGGED (his inter+intra requirement). ``activated``
    is the nodes that fired together to produce one answer (the keeper ring's descent set + leaves),
    each ``(id, grade)``. Cheap to log, impossible to recover if not logged - so it is banked at the
    call, ahead of the dreamer that reads it. Returns the event, or None if nothing fired."""
    acts = _norm_activated(activated)
    if not acts:
        return None
    return telemetry.log("coactivation", caller=caller, goal=goal,
                         activated=[{"id": nid, "grade": g} for nid, g in acts])


def _activated_events(events: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """The events carrying a grade-tagged co-fire set: ``coactivation`` events, plus any ``reconstruction``
    event whose ``activated`` entries carry grades (forward-compatible)."""
    evs = events if events is not None else telemetry.events()
    out = []
    for ev in evs:
        if ev.get("phase") == "coactivation" and ev.get("activated"):
            out.append(ev)
        elif ev.get("phase") == "reconstruction" and ev.get("activated"):
            if any(isinstance(a, dict) and "grade" in a for a in ev["activated"]):
                out.append(ev)
    return out


# ---------------------------------------------------------------------------
# cofire - the pairwise co-firing counts, split inter vs intra grade
# ---------------------------------------------------------------------------

def cofire(events: list[dict[str, Any]] | None = None) -> dict[str, Counter]:
    """Count which node PAIRS fire together, split by grade relation. ``intra`` = same-grade pairs (the
    in-grade reclustering signal); ``inter`` = different-grade pairs (the cross-grade link signal). Keys
    are ordered ``(a, b)`` so a pair counts once regardless of activation order."""
    intra: Counter[tuple[str, str]] = Counter()
    inter: Counter[tuple[str, str]] = Counter()
    for ev in _activated_events(events):
        acts = _norm_activated(ev.get("activated", []))[:_PAIR_CAP]
        for i in range(len(acts)):
            ai, gi = acts[i]
            for j in range(i + 1, len(acts)):
                aj, gj = acts[j]
                key = (ai, aj) if ai < aj else (aj, ai)
                (intra if gi == gj else inter)[key] += 1
    return {"intra": intra, "inter": inter}


def observed_coupling(a: str, b: str, events: list[dict[str, Any]] | None = None) -> int:
    """The DYNAMIC coupling of two nodes: how often they co-fired in use (intra+inter) - the telemetry
    conjugate of ``keeper_ring.coupling`` (which counts shared substrate statically). Both feed link
    strength; this one is earned by use, his fitness signal."""
    cf = cofire(events)
    key = (a, b) if a < b else (b, a)
    return cf["intra"].get(key, 0) + cf["inter"].get(key, 0)


# ---------------------------------------------------------------------------
# recluster_candidates - the recursive dreamer's input (the signal, not the act)
# ---------------------------------------------------------------------------

def recluster_candidates(min_count: int = 2, top: int = 20,
                         events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """The reclustering signal from telemetry of use. ``recluster`` = same-grade pairs that co-fire >=
    ``min_count`` (a new in-grade cluster / merge is sensible); ``strengthen`` = cross-grade pairs that
    co-fire (the link is real). Ranked by count. This is what the recursive dreamer reads to decide where
    to grow a node or wire a link - the DECISION is the dreamer's, gated by F1; this only surfaces where."""
    cf = cofire(events)
    intra = sorted(((c, a, b) for (a, b), c in cf["intra"].items() if c >= min_count), reverse=True)
    inter = sorted(((c, a, b) for (a, b), c in cf["inter"].items() if c >= min_count), reverse=True)
    return {
        "recluster": [{"a": a, "b": b, "cofire": c,
                       "why": "same-grade nodes co-fire -> a new in-grade cluster / merge is sensible"}
                      for c, a, b in intra[:top]],
        "strengthen": [{"a": a, "b": b, "cofire": c,
                        "why": "cross-grade pair co-fires -> the inter-grade link is real, strengthen it"}
                       for c, a, b in inter[:top]],
        "events_read": len(_activated_events(events)),
        "note": ("telemetry of use -> structure: high INTRA-grade co-fire says a new node / recluster is "
                 "sensible; high INTER-grade co-fire says the link is real. The recursive dreamer acts on "
                 "this (F1-gated); the analyser only surfaces where."),
    }
