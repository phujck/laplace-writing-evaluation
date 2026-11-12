"""The conceptric as a living graph: seats, the calls they make, and what returns.

His commission, 2026-08-25 in session (W12): "some super sexy graphical view showing
seats and the calls through the conceptric they make, and what returns ... both for
aesthetic reasons and practical purposes of monitoring system health and observability.
Plus I reckon when it's all connected it'll really light up and look like a brain."

BOTH AXES ARE LOAD-BEARING. The observability axis answers a defect measured the same
day: laplace-atlas-watcher burned 71% of a core for seven hours while blocked on a fibre
mismatch, and PASSED EVERY LIVENESS TEST while carrying zero information. Liveness and
information are different axes and nothing showed the second one. The aesthetic axis is
his too, and it is not decoration: an observability surface nobody opens is worth exactly
as much as no surface.

WHAT THIS DOES NOT SHOW, said here because a graph that hides its dark half is the very
defect it exists to catch: EventKind declares 26 kinds and only 11 have ever fired.
reconstruction.moved and reconstruction.materialized -- the two this view most wants --
have never fired once (FIND-20260825-descent-kinds-declared-never-fired). So the SEAT lane
below is real and live, and the CONCEPTRIC-CALL lane is dark until descent emits. The kind
spectrum renders every unfired kind AS UNFIRED rather than omitting it, and the descent
pane states its own emptiness rather than drawing an empty box that reads as calm.

ROWS BEFORE RENDERS: project() returns typed rows and names its source; render() draws
only what project() returned and fabricates no number.
"""
from __future__ import annotations
from laplace.core.checkout import source_tree

import collections
import html
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "laplace.engine.descent-telemetry/1"

#: the widest tail ever built, so every narrower request is a slice of one projection
_MAX_TAIL = 90

DEFAULT_STORE = Path.home() / ".mcp-gerard" / "laplace" / "atlas" / "conceptric"

# the two kinds this view exists to draw, named so the dark half is legible by id
DESCENT_KINDS = ("reconstruction.moved", "reconstruction.materialized")

# seat hues - stable per seat so his eye learns them across sessions
_SEAT_HUE = {
    "gerard-seat": "#D9A441",
    "codex-seat": "#5CB878",
    "claude-seat": "#7FA9D9",
    "interface-seat": "#C77FD9",
    "ego-seat": "#D97862",
}
_FALLBACK_HUE = "#9CA1AB"


def _v(x: Any) -> Any:
    return getattr(x, "value", x)


def _ts(raw: Any) -> float | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


#: one projection per (store, head, cursor, tail). A full events() replay is 265ms over
#: ~960 events and this pane's census rides /front/places, which the shell fetches AT BOOT
#: — so an uncached read would put a quarter-second tollbooth on his front door for a
#: number he has not asked to see yet. read_drift_token() answers in 0.2ms and carries the
#: head event id and cursor, so an unmoved store costs nothing and a moved one cannot be
#: served stale.
_CACHE: dict[str, Any] = {}


def _stamp(payload: dict[str, Any]) -> dict[str, Any]:
    """Recompute every TIME-DEPENDENT field on the way out.

    A cached payload keeping its original read_at would be a freshness label that is
    itself stale — the precise trap this whole surface exists to catch, and the one I
    nearly filed a false finding about on the board's own age line. The rows are cached;
    the clock never is.
    """
    now = datetime.now(timezone.utc)
    payload["read_at"] = now.isoformat(timespec="seconds")
    last = _ts(payload["totals"].get("last_at"))
    payload["totals"]["age_seconds"] = round(now.timestamp() - last) if last else None
    return payload


def _plain(x: Any) -> Any:
    """Coerce a store value to something JSON can carry.

    The conceptric returns typed objects — SourceRef, Residual, enums — not dicts. A
    detail pane that assumes Mapping raises on the one event the reader clicked, which
    turns "open this" into "this door is broken". Everything degrades to a string rather
    than to nothing: an unreadable field is shown as text, never dropped.
    """
    import dataclasses
    if x is None:
        return None
    if isinstance(x, Mapping):
        return {k: _plain(v) for k, v in x.items()}
    if dataclasses.is_dataclass(x) and not isinstance(x, type):
        return {k: _plain(v) for k, v in dataclasses.asdict(x).items()}
    if isinstance(x, (list, tuple)):
        return [_plain(v) for v in x]
    if isinstance(x, (str, int, float, bool)):
        return x
    return str(getattr(x, "value", x))


def _goal(p: Mapping[str, Any]) -> str:
    """The one human-readable line an event carries, wherever its kind happens to put it."""
    for k in ("goal", "message_type", "action", "operation", "verb", "title"):
        v = p.get(k)
        if v:
            return str(v)[:120]
    args = p.get("arguments")
    if isinstance(args, Mapping) and args.get("goal"):
        return str(args["goal"])[:120]
    return ""


def _returned(p: Mapping[str, Any]) -> str:
    """WHAT CAME BACK — his commission names this explicitly ("and what returns"). An
    event that produced a handle, a disposition or a residual says so; one that did not
    says nothing rather than an empty string dressed as a result."""
    for k in ("reconstruction_handle", "materialization_handle", "body_handle",
              "disposition", "result", "outcome", "verdict", "handle"):
        v = p.get(k)
        if v:
            return f"{k}={str(v)[:80]}"
    return ""


def _depths(events: Any) -> tuple[dict[str, int], dict[str, Any]]:
    """Distance from a causal ROOT over the CONDENSATION of the graph, plus a residual.

    THE LIE THIS REPLACES, planted by codex: the previous pass was iterative and so could
    not recurse the page down, and I called that "cycle-safe". It is not. On a 2-cycle
    A<->B, visiting in order (A,B) yields {B:0, A:1} and order (B,A) yields {A:0, B:1} —
    the same graph, two different answers, neither of them a distance from a root, because
    A CYCLE HAS NO ROOT. My own test asserted only that output was total and non-negative,
    which blessed it. A depth axis that reports a confident number for a question with no
    answer is the exact class this surface exists to catch.

    So: Tarjan's SCC, depth over the condensation DAG, and every member of a non-trivial
    component gets depth None and is COUNTED in a residual rather than given a number.
    An event whose depth is unknown renders as unknown; it does not get an invented one.
    """
    by_id = {e.event_id: e for e in events}
    parents = {eid: [c for c in (e.causation_ids or ()) if c in by_id]
               for eid, e in by_id.items()}

    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: dict[str, bool] = {}
    stack: list[str] = []
    comp_of: dict[str, int] = {}
    comps: list[list[str]] = []
    counter = 0

    for root in by_id:                      # iterative Tarjan — the page must not recurse
        if root in index:
            continue
        work = [(root, iter(parents[root]))]
        index[root] = low[root] = counter; counter += 1
        stack.append(root); on_stack[root] = True
        while work:
            node, it = work[-1]
            advanced = False
            for nxt in it:
                if nxt not in index:
                    index[nxt] = low[nxt] = counter; counter += 1
                    stack.append(nxt); on_stack[nxt] = True
                    work.append((nxt, iter(parents[nxt])))
                    advanced = True
                    break
                if on_stack.get(nxt):
                    low[node] = min(low[node], index[nxt])
            if advanced:
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[node])
            if low[node] == index[node]:
                comp: list[str] = []
                while True:
                    m = stack.pop(); on_stack[m] = False
                    comp_of[m] = len(comps); comp.append(m)
                    if m == node:
                        break
                comps.append(comp)

    cyclic = {c for comp in comps if len(comp) > 1 for c in comp}
    for eid, ps in parents.items():         # a self-loop is a cycle of one
        if eid in ps:
            cyclic.add(eid)

    comp_parents: dict[int, set[int]] = {i: set() for i in range(len(comps))}
    for eid, ps in parents.items():
        for pnt in ps:
            if comp_of[pnt] != comp_of[eid]:
                comp_parents[comp_of[eid]].add(comp_of[pnt])

    comp_depth: dict[int, int] = {}
    for ci in range(len(comps)):            # condensation is a DAG; resolve by need
        order = [ci]
        while order:
            cur = order[-1]
            if cur in comp_depth:
                order.pop(); continue
            pend = [x for x in comp_parents[cur] if x not in comp_depth]
            if pend:
                order.extend(pend); continue
            comp_depth[cur] = 1 + max((comp_depth[x] for x in comp_parents[cur]),
                                      default=-1)
            order.pop()

    out: dict[str, int] = {}
    for eid in by_id:
        if eid not in cyclic:
            out[eid] = comp_depth[comp_of[eid]]
    residual = {
        "cyclic_events": len(cyclic),
        "cycles": sum(1 for comp in comps if len(comp) > 1),
        "note": ("events inside a causal cycle have NO distance from a root and are served "
                 "with depth unknown, never with an invented number; the depth projection "
                 "puts them in their own lane"),
    }
    return out, residual


def _tail_row(e: Any, i: int, index: Mapping[str, int],
              depths: Mapping[str, int] | None = None) -> dict[str, Any]:
    p = e.payload or {}
    return {
        "i": i,
        # UNKNOWN, not zero: an event in a causal cycle has no distance from a root.
        "depth": (depths or {}).get(e.event_id),
        "event_id": e.event_id,
        "kind": _v(e.kind),
        "actor": _v(e.actor),
        "producer": _v(e.producer),
        "at": e.occurred_at,
        "ts": _ts(e.occurred_at),
        "fibre": e.fibre,
        "correlation": e.correlation_id,
        "subject": str(e.subject or "")[:110],
        "seat": str(p.get("sender_seat_id") or p.get("seat_id") or ""),
        "to": str(p.get("recipient_seat_id") or ""),
        "goal": _goal(p),
        "returned": _returned(p),
        "residual": (_v((e.residual or {}).get("status"))
                     if isinstance(e.residual, Mapping) else None),
        "causes": [index[c] for c in (e.causation_ids or ()) if c in index],
        "cause_ids": list(e.causation_ids or ()),
        "causes_outside_window": sum(1 for c in (e.causation_ids or ())
                                     if c not in index),
    }


def _machinery(root: Path) -> dict[str, Any]:
    """THE MACHINERY — the stores and the doors, folded into the surface that already
    answers "is the engine working".

    This is the collapse he asked for, done in the order that makes it real: capability
    first, chrome second. His words are "collapsing them down to fewer THAT ARE ABLE TO
    MUCH MORE", and the second clause is the load-bearing one — folding eleven tabs into
    four that land on the same eleven panes is chrome rearranged, not capability. So the
    two health tabs are absorbed HERE before either is removed from the nav.

    `#organ` answered "which store has rotted" and `/front/selftest` answered "which door
    is down". They are one question — is the machinery working — split across two
    destinations, neither of which showed the engine it belongs to.

    UNKNOWN IS A VALUE, and there are three distinct ones here that a naive render would
    collapse into a single green: a store with no freshness budget cannot be stale and must
    not read as fresh; a store that has never been written is absent, not quiet; and a door
    census that has never run is uncertified, not passing.
    """
    from laplace.engine import sources as _sources

    stores, no_budget, absent = [], 0, 0
    for r in _sources.roster():
        if not r.get("mtime"):
            absent += 1
            stores.append({"name": r["name"], "label": r.get("label") or r["name"],
                           "path": r.get("path"), "state": "never written",
                           "age_h": None, "budget_h": None})
            continue
        if not r.get("budget_s"):
            no_budget += 1
        stores.append({
            "name": r["name"], "label": r.get("label") or r["name"], "path": r.get("path"),
            "state": ("past its budget" if r.get("red")
                      else "no freshness budget" if not r.get("budget_s") else "fresh"),
            "age_h": round((r.get("age_s") or 0) / 3600.0, 1),
            "budget_h": round(r["budget_s"] / 3600.0, 1) if r.get("budget_s") else None,
            "quiet_is_normal": bool(r.get("quiet_is_normal")),
        })
    stores.sort(key=lambda r: (r["state"] != "past its budget",
                               r["state"] != "never written", r["name"]))

    bank_path = root / ".selftest_doors.json"
    if bank_path.exists():
        try:
            b = json.loads(bank_path.read_text(encoding="utf-8"))
            ran = b.get("ran_at")
            age = None
            t = _ts(ran)
            if t:
                age = round((datetime.now(timezone.utc).timestamp() - t) / 3600.0, 1)
            doors = {"state": "certified", "doors": b.get("doors"), "down": b.get("down"),
                     "ran_at": ran, "age_h": age,
                     "failing": [d for d in (b.get("detail") or []) if not d.get("ok")]}
        except (OSError, ValueError) as exc:
            doors = {"state": "unreadable", "why": f"{type(exc).__name__}: {exc}"}
    else:
        doors = {"state": "never certified",
                 "why": "the door census has not run in this repo. A door absent from a "
                        "census that never ran is uncertified, not passing."}

    return {
        "source": "laplace.engine.sources.roster() (every store, its age and its own budget) · "
                  ".selftest_doors.json (the last door census, banked when it was opened)",
        "staleness": "the stores are stat'd live on this build; the door census is a "
                     "BANKED run stamped with its age — this pane fires no door",
        "stores": stores, "doors": doors,
        "counts": {"stores": len(stores),
                   "past_budget": sum(1 for r in stores if r["state"] == "past its budget"),
                   "never_written": absent, "no_budget": no_budget},
        "note": (f"{no_budget} store(s) carry NO freshness budget and therefore can never "
                 f"be marked stale — they are shown as such rather than as fresh. "
                 f"{absent} have never been written at all."),
    }


def _pull_rows(events: Any) -> dict[str, Any]:
    """WHAT THE ENGINE IS ACTUALLY REACHING FOR — his ask: "some representation of the
    corpus showing what's being pulled most".

    THE HONEST NEGATIVE FIRST, because it decides the whole shape of this pane: content
    handles are almost all read ONCE. Measured live: 223 distinct input handles across 237
    reads. A most-read-handle chart would be a flat bar of ones dressed up as a ranking.
    The corpus is being read BROADLY, not repeatedly, and that is the finding rather than
    a gap in the data.

    So the pull that carries signal is by GOAL (what a reconstruction was aiming at, which
    repeats hard — one goal 40 times) and by SUBJECT CLASS (what sort of thing the engine
    addresses at all). Both are stated with their denominators.
    """
    goals: collections.Counter = collections.Counter()
    classes: collections.Counter = collections.Counter()
    reads: collections.Counter = collections.Counter()
    for e in events:
        p = e.payload or {}
        classes[str(e.subject or "(none)").split(":")[0]] += 1
        args = p.get("arguments")
        g = p.get("goal") or (args.get("goal") if isinstance(args, Mapping) else None)
        if g:
            goals[str(g)] += 1
        for h in (p.get("input_handles") or []):
            reads[str(h)] += 1
    repeated = sum(1 for _h, n in reads.items() if n > 1)
    return {
        "goals": [{"goal": g, "count": n} for g, n in goals.most_common(10)],
        "goals_distinct": len(goals), "goals_total": sum(goals.values()),
        "classes": [{"cls": c, "count": n} for c, n in classes.most_common(10)],
        "reads_distinct": len(reads), "reads_total": sum(reads.values()),
        "reads_repeated": repeated,
        "note": (f"{len(reads)} distinct content handles across {sum(reads.values())} reads; "
                 f"{repeated} were read more than once. The corpus is read BROADLY, not "
                 f"repeatedly — a most-read-handle ranking here would be a flat bar of ones, "
                 f"so this pane ranks what the reads were FOR instead."),
    }


def _descent_state(fired: Mapping[str, int]) -> dict[str, Any]:
    """Derive the descent instrument's claim from the same counts it displays."""

    moved = int(fired.get("reconstruction.moved", 0) or 0)
    materialized = int(fired.get("reconstruction.materialized", 0) or 0)
    dark = moved == 0 and materialized == 0
    if dark:
        return {
            "moved": moved,
            "materialized": materialized,
            "dark": True,
            "why": "reconstruction.moved and reconstruction.materialized are declared in "
                   "EventKind and have never fired. Until descent emits them this pane "
                   "has nothing to draw, and drawing an empty graph would read as a quiet "
                   "system rather than an uninstrumented one.",
            "ref": "FIND-20260825-descent-kinds-declared-never-fired",
        }
    return {
        "moved": moved,
        "materialized": materialized,
        "dark": False,
        "why": f"the descent instrument is lit: {moved} movement act(s) and "
               f"{materialized} materialization act(s) are present in this exact store",
        "ref": None,
        "resolved_ref": "FIND-20260825-descent-kinds-declared-never-fired",
    }


def delta(after_cursor: int, store_root: Path | str | None = None) -> dict[str, Any]:
    """Events banked SINCE a cursor — the live feed behind `atlas:changed`.

    The stream pushes only "the store moved to N"; the page asks here for what actually
    happened. Bounded: a client that has been away for a thousand events gets the last
    _MAX_TAIL and is TOLD it was truncated, never silently handed a window that pretends
    to be the whole delta.
    """
    from laplace.representation import atlas_bridge as ab
    root = Path(store_root) if store_root else DEFAULT_STORE
    events = ab.ConceptricStore(
        root, read_only=True,
        extra_authority_files=ab.EXTRA_AUTHORITY_FILES,
    ).events()
    # the store's cursor IS the event count, so a cursor is a position in this tuple
    fresh = list(events)[max(after_cursor, 0):]
    truncated = max(0, len(fresh) - _MAX_TAIL)
    fresh = fresh[-_MAX_TAIL:]
    index = {e.event_id: i for i, e in enumerate(fresh)}
    return {"schema_version": SCHEMA, "after_cursor": after_cursor,
            "event_cursor": len(events), "truncated": truncated,
            "read_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "events": [_tail_row(e, i, index) for i, e in enumerate(fresh)]}


def seat_detail(seat_id: str, store_root: Path | str | None = None,
                *, limit: int = 24) -> dict[str, Any]:
    """One seat, deeply: its traffic, its acts, what it is holding, what it last did.

    This is the `seats` page folded INTO the graph. His steer, 2026-08-25: "collapsing
    them down to fewer that are able to much more" — a node you can only hover is a
    picture; a node you can open is an instrument.
    """
    from laplace.representation import atlas_bridge as ab
    root = Path(store_root) if store_root else DEFAULT_STORE
    events = ab.ConceptricStore(
        root, read_only=True,
        extra_authority_files=ab.EXTRA_AUTHORITY_FILES,
    ).events()
    index = {e.event_id: i for i, e in enumerate(events)}

    sent, recv, acts = [], [], []
    for e in events:
        p = e.payload or {}
        if p.get("sender_seat_id") == seat_id:
            sent.append(e)
        if p.get("recipient_seat_id") == seat_id:
            recv.append(e)
        if str(p.get("seat_id") or "") == seat_id or _v(e.actor) == seat_id:
            acts.append(e)

    def rows(evs: list[Any]) -> list[dict[str, Any]]:
        return [_tail_row(e, index.get(e.event_id, 0), index) for e in evs[-limit:]][::-1]

    by_peer: collections.Counter = collections.Counter()
    for e in sent:
        p = e.payload or {}
        if p.get("recipient_seat_id"):
            by_peer[str(p["recipient_seat_id"])] += 1

    # pending_messages grew two REQUIRED keyword-only arguments (after_cursor, as_of) and
    # this caller was never updated, so every seat pane raised TypeError. The `except`
    # below commented "an unreadable inbox is stated, not zeroed" and then the count below
    # zeroed it anyway, because it counted rows-without-an-error-key and the error path has
    # exactly one row and it has an error key. So the pane rendered "in its inbox now: 0"
    # over a raw Python traceback, while the fabric held real queued mail. Absence rendered
    # as reassurance, on a surface built to catch absence rendered as reassurance.
    pending: list[dict[str, Any]] = []
    pending_error: str | None = None
    try:
        pend = ab.ConceptricStore(
            root, read_only=True,
            extra_authority_files=ab.EXTRA_AUTHORITY_FILES,
        ).pending_messages(
            seat_id, after_cursor=0,
            as_of=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        pending = [{"message_id": str(m.get("message_id", ""))[:38],
                    "from": m.get("sender_seat_id"), "type": m.get("message_type"),
                    "expires": m.get("expires_at")} for m in (pend or [])]
    except Exception as exc:  # noqa: BLE001 - an unreadable inbox is UNKNOWN, never 0
        pending_error = f"{type(exc).__name__}: {exc}"

    last_recon = next((e for e in reversed(events)
                       if _v(e.kind) in ("repl.evaluated",) + DESCENT_KINDS
                       and (_v(e.actor) == seat_id
                            or str((e.payload or {}).get("seat_id") or "") == seat_id)),
                      None)
    return {
        "schema_version": SCHEMA, "seat": seat_id,
        "hue": _SEAT_HUE.get(seat_id, _FALLBACK_HUE),
        # UNKNOWN is a value here, not a zero. `None` is what the pane must render as
        # "could not read", and no arithmetic downstream may turn it into a count.
        "totals": {"sent": len(sent), "received": len(recv), "acts": len(acts),
                   "pending": None if pending_error else len(pending)},
        "pending_error": pending_error,
        "peers": [{"seat": k, "count": n} for k, n in by_peer.most_common()],
        "pending": pending,
        "recent_sent": rows(sent),
        "recent_acts": rows(acts),
        "last_reconstruction": (_tail_row(last_recon, index.get(last_recon.event_id, 0),
                                          index) if last_recon else None),
        "source": f"ConceptricStore.events() + pending_messages({seat_id}) over {root}",
    }


def event_detail(event_id: str, store_root: Path | str | None = None) -> dict[str, Any]:
    """One event, opened: its payload, what CAUSED it, and what it went on to CAUSE.

    The effects half is the part a causal store usually hides — causation_ids point
    backwards only, so "what did this lead to" costs a scan. It is the question he
    actually asks of a trace, so it is computed here rather than left to him.
    """
    from laplace.representation import atlas_bridge as ab
    root = Path(store_root) if store_root else DEFAULT_STORE
    events = ab.ConceptricStore(
        root, read_only=True,
        extra_authority_files=ab.EXTRA_AUTHORITY_FILES,
    ).events()
    index = {e.event_id: i for i, e in enumerate(events)}
    match = next((e for e in events
                  if e.event_id == event_id or e.event_id.endswith(event_id)), None)
    if match is None:
        return {"schema_version": SCHEMA, "absent": event_id,
                "why": "no event in the store carries this id or suffix"}
    caused_by = [events[index[c]] for c in (match.causation_ids or ()) if c in index]
    causes = [e for e in events if match.event_id in (e.causation_ids or ())]
    body = match.payload or {}
    return {
        "schema_version": SCHEMA,
        "event": _tail_row(match, index[match.event_id], index),
        "assumption": str(match.assumption or "")[:400],
        "provenance": [_plain(x) for x in (match.provenance or ())][:4],
        "runtime": _plain(match.runtime),
        "residual": _plain(match.residual),
        "payload_keys": sorted(body)[:40],
        "payload": {k: str(v)[:400] for k, v in list(body.items())[:24]},
        "caused_by": [_tail_row(e, index[e.event_id], index) for e in caused_by],
        "caused": [_tail_row(e, index[e.event_id], index) for e in causes][:20],
        "source": f"ConceptricStore.events() over {root}",
    }


def project(store_root: Path | str | None = None, *, tail: int = 90) -> dict[str, Any]:
    """Read the conceptric read-only and return typed rows. No render decisions here."""
    from laplace.representation import atlas_bridge as ab  # local: the store is the one door

    root = Path(store_root) if store_root else DEFAULT_STORE
    try:
        token = ab.ConceptricStore.read_drift_token(root)
        # TAIL IS NOT IN THE KEY. It was, and that cost 1.6s: the census asks for
        # tail=1 and the page for tail=90, so they missed each other's cache and each
        # paid a full replay. One projection per store STATE; the tail is a slice of it.
        key = (str(root), str(token.get("head_event_id")), token.get("cursor"))
    except Exception:  # noqa: BLE001 - an unreadable token means build, never serve stale
        key = None
    if key is not None and _CACHE.get("key") == key:
        hit = dict(_CACHE["payload"])
        hit["tail"] = hit["tail"][-tail:] if tail else []
        return _stamp(hit)

    store = ab.ConceptricStore(
        root, read_only=True,
        extra_authority_files=ab.EXTRA_AUTHORITY_FILES,
    )
    events = store.events()

    declared = sorted(_v(k) for k in ab.EventKind)
    fired = collections.Counter(_v(e.kind) for e in events)
    unfired = [k for k in declared if k not in fired]

    # --- the seat lane: who called whom, off message payloads ------------------
    traffic: collections.Counter = collections.Counter()
    for e in events:
        if _v(e.kind) == "seat.message-sent":
            p = e.payload or {}
            a, b = p.get("sender_seat_id"), p.get("recipient_seat_id")
            if a and b:
                traffic[(str(a), str(b))] += 1

    seats = sorted({s for pair in traffic for s in pair})
    sent = collections.Counter(a for (a, _b), n in traffic.items() for _ in range(n))
    recv = collections.Counter(b for (_a, b), n in traffic.items() for _ in range(n))

    # what RETURNS: a send is delivered only when an acknowledgement causally joins it.
    acked = sum(1 for e in events if _v(e.kind) == "seat.message-acknowledged")
    pulled = sum(1 for e in events if _v(e.kind) == "seat.messages-pulled")
    sends = sum(traffic.values())

    # --- the causal DAG --------------------------------------------------------
    ids = {e.event_id for e in events}
    edges = sum(len(e.causation_ids or ()) for e in events)
    dangling = sum(1 for e in events for c in (e.causation_ids or ()) if c not in ids)
    roots = sum(1 for e in events if not (e.causation_ids or ()))

    correlations = collections.Counter(e.correlation_id for e in events)
    fibres = collections.Counter(e.fibre for e in events)

    # --- the live tail: the last `tail` events, with their in-window causes -----
    # build the widest tail once; project(tail=n) slices it on the way out
    recent = list(events)[-max(tail, _MAX_TAIL):]
    index = {e.event_id: i for i, e in enumerate(recent)}
    depths, depth_residual = _depths(events)
    tail_rows = [_tail_row(e, i, index, depths) for i, e in enumerate(recent)]

    first_ts, last_ts = _ts(events[0].occurred_at), _ts(events[-1].occurred_at)
    now = datetime.now(timezone.utc).timestamp()

    payload = {
        "schema_version": SCHEMA,
        "source": f"ConceptricStore.events() over {root} (read-only) · "
                  f"laplace.representation.atlas_bridge.EventKind for the declared vocabulary",
        "staleness": "live on every build - this pane fires no probe and caches nothing; "
                     "it reads the store and returns",
        "read_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "store_root": str(root),
        "totals": {
            "events": len(events),
            "causal_edges": edges,
            "dangling_causes": dangling,
            "root_events": roots,
            "correlations": len(correlations),
            "kinds_declared": len(declared),
            "kinds_fired": len(fired),
            "span_hours": round((last_ts - first_ts) / 3600.0, 1)
            if (first_ts and last_ts) else None,
            "first_at": events[0].occurred_at if events else None,
            "last_at": events[-1].occurred_at if events else None,
            "age_seconds": round(now - last_ts) if last_ts else None,
        },
        "seats": [{
            "seat": s,
            "sent": sent.get(s, 0),
            "received": recv.get(s, 0),
            "hue": _SEAT_HUE.get(s, _FALLBACK_HUE),
        } for s in seats],
        "traffic": [{"from": a, "to": b, "count": n}
                    for (a, b), n in sorted(traffic.items(), key=lambda kv: -kv[1])],
        "delivery": {"sends": sends, "pulls": pulled, "acks": acked,
                     "law": "delivered iff an accepted acknowledgement causally joins the "
                            "send to a same-seat, same-fibre typed reconstruction that "
                            "consumed the body - counts here are of ACTS, not of proofs"},
        "kinds": [{"kind": k, "count": fired.get(k, 0), "fired": k in fired,
                   "is_descent": k in DESCENT_KINDS} for k in declared],
        "unfired": unfired,
        "descent": _descent_state(fired),
        "fibres": [{"fibre": f or "(none)", "count": n} for f, n in fibres.most_common()],
        "pull": _pull_rows(events),
        "depth_residual": depth_residual,
        "machinery": _machinery(source_tree()),
        "top_traces": [{"correlation": c, "events": n}
                       for c, n in correlations.most_common(6)],
        "tail": tail_rows,
    }
    if key is not None:
        _CACHE["key"], _CACHE["payload"] = key, payload
    out = dict(payload)
    out["tail"] = out["tail"][-tail:] if tail else []
    return _stamp(out)


# --------------------------------------------------------------------------- render

def _seat_graph_svg(payload: dict[str, Any], w: int = 640, h: int = 520) -> str:
    """Seats on a ring, traffic as curved directed edges. Deterministic, no client libs.

    Every node and edge carries data-seat so the client can wire hover and click without
    the server shipping a layout engine. His steer: a node you can only look at is a
    picture; this one opens.
    """
    seats = payload["seats"]
    if not seats:
        return '<p class="dim">no seat has sent a message in this store.</p>'
    cx, cy, r, n = w / 2, h / 2, min(w, h) * 0.33, len(seats)
    pos = {}
    for i, st in enumerate(seats):
        a = -math.pi / 2 + 2 * math.pi * i / n
        pos[st["seat"]] = (cx + r * math.cos(a), cy + r * math.sin(a))

    heaviest = max((t["count"] for t in payload["traffic"]), default=1)
    out = [f'<svg viewBox="0 0 {w} {h}" id="brain" role="img" '
           f'aria-label="seat traffic through the conceptric">', '<defs>']
    for st in seats:
        sid = st["seat"].replace("-", "")
        out.append(f'<marker id="a{sid}" viewBox="0 0 10 10" refX="9" refY="5" '
                   f'markerWidth="5" markerHeight="5" orient="auto-start-reverse">'
                   f'<path d="M0,0 L10,5 L0,10 z" fill="{st["hue"]}"/></marker>')
    out.append('<filter id="glow" x="-70%" y="-70%" width="240%" height="240%">'
               '<feGaussianBlur stdDeviation="6" result="b"/><feMerge>'
               '<feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>'
               '</defs><g id="edges">')

    for t in payload["traffic"]:
        a, b = pos.get(t["from"]), pos.get(t["to"])
        if not a or not b:
            continue
        hue = next((x["hue"] for x in seats if x["seat"] == t["from"]), _FALLBACK_HUE)
        weight = t["count"] / heaviest
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy) or 1.0
        qx, qy = mx - dy / L * 0.16 * L, my + dx / L * 0.16 * L
        sx, sy = a[0] + (qx - a[0]) * .10, a[1] + (qy - a[1]) * .10
        ex, ey = b[0] + (qx - b[0]) * .22, b[1] + (qy - b[1]) * .22
        out.append(
            f'<path class="edge" data-from="{escape_attr(t["from"])}" '
            f'data-to="{escape_attr(t["to"])}" '
            f'id="e-{escape_attr(t["from"])}--{escape_attr(t["to"])}" '
            f'd="M{sx:.1f},{sy:.1f} Q{qx:.1f},{qy:.1f} {ex:.1f},{ey:.1f}" fill="none" '
            f'stroke="{hue}" stroke-width="{0.8 + 5.4 * weight:.2f}" stroke-linecap="round" '
            f'opacity="{0.20 + 0.55 * weight:.2f}" marker-end="url(#a{t["from"].replace("-", "")})">'
            f'<title>{html.escape(t["from"])} → {html.escape(t["to"])} · '
            f'{t["count"]} messages</title></path>')
    out.append('</g><g id="nodes">')

    busiest = max((st["sent"] + st["received"] for st in seats), default=1)
    for st in seats:
        x, y = pos[st["seat"]]
        total = st["sent"] + st["received"]
        rad = 16 + 26 * (total / busiest)
        sid = escape_attr(st["seat"])
        out.append(
            f'<g class="node" data-seat="{sid}" tabindex="0" role="button" '
            f'aria-label="open {html.escape(st["seat"])}">'
            f'<circle class="halo" cx="{x:.1f}" cy="{y:.1f}" r="{rad:.1f}" '
            f'fill="{st["hue"]}" fill-opacity=".14" stroke="{st["hue"]}" stroke-width="1.7" '
            f'filter="url(#glow)"/>'
            f'<circle class="core" cx="{x:.1f}" cy="{y:.1f}" r="{rad * .30:.1f}" '
            f'fill="{st["hue"]}"/>'
            f'<circle class="ping" cx="{x:.1f}" cy="{y:.1f}" r="{rad:.1f}" fill="none" '
            f'stroke="{st["hue"]}" stroke-width="2" opacity="0"/>'
            f'<text x="{x:.1f}" y="{y + rad + 18:.1f}" text-anchor="middle" class="lbl" '
            f'fill="{st["hue"]}">{html.escape(st["seat"])}</text>'
            f'<text x="{x:.1f}" y="{y + rad + 32:.1f}" text-anchor="middle" class="sub">'
            f'{st["sent"]}\u2191 {st["received"]}\u2193</text>'
            f'<title>{html.escape(st["seat"])} — click to open</title></g>')
    out.append('</g></svg>')
    return "".join(out)


def _river_shell(payload: dict[str, Any]) -> str:
    """The river is drawn CLIENT-SIDE so it can re-project without a round trip.

    It was server-drawn, and two things went wrong that were really one thing: the lane
    gutter was a guessed 106px while `reconstruction.materialized` needs ~140px, and the
    "causes older than this window" note was right-anchored at the same x, so it ran off
    the left edge and collided with the lane labels. His screenshot, and his words: "hey
    guess what I hate."

    Both are fixed at the root rather than nudged: the gutter is MEASURED from the longest
    label actually being drawn, labels render their human face (the kind's last segment —
    `materialized`, `acknowledged`) with the full kind on hover per the conjugate-handle
    law, and the margin note is a caption under the plot where a margin note belongs.
    Drawing client-side is what makes the measurement possible at all.
    """
    return ('<svg id="river" role="img" aria-label="event timeline; drawn after load"'
            '></svg>')


def escape_attr(v: Any) -> str:
    return html.escape(str(v), quote=True)


def render(payload: dict[str, Any]) -> str:
    """One self-contained interrogable surface. No CDN, no webfont, no framework.

    This absorbed four tabs rather than becoming a fifth (his steer, 2026-08-25: "just
    another row on the chrome ... collapsing them down to fewer that are able to much
    more"). A seat opens into what `/seats` showed; an event opens into its payload, its
    causes and what it caused; the river and the tail are `#run` with the causal links kept
    — and they ARE kept, which an earlier rewrite of this function claimed while having
    deleted them. A comment asserting a capability the code dropped is worse than the drop:
    it defeats the next reader's verification.
    """
    e = html.escape
    def chip(text: str, hue: str) -> str:
        return f'<span class="t" style="--t:{hue}">{html.escape(str(text))}</span>'
    t, d = payload["totals"], payload["descent"]
    spectrum = "".join(
        (f'<div class="k lit" data-kind="{escape_attr(k["kind"])}">'
         f'<span class="n">{k["count"]}</span><span class="kn">{e(k["kind"])}</span></div>')
        if k["fired"] else
        (f'<div class="k dark{" descent" if k["is_descent"] else ""}">'
         f'<span class="n">—</span><span class="kn">{e(k["kind"])}</span>'
         f'<span class="never">NEVER FIRED</span></div>')
        for k in payload["kinds"])
    traffic = "".join(
        f'<tr class="trow" data-from="{escape_attr(r["from"])}" '
        f'data-to="{escape_attr(r["to"])}"><td class="mono">{e(r["from"])}</td>'
        f'<td class="arr">→</td><td class="mono">{e(r["to"])}</td>'
        f'<td class="num">{r["count"]}</td></tr>' for r in payload["traffic"])

    return f"""<title>the conceptric</title>
<style>
:root{{color-scheme:dark;--ground:#0E1014;--card:#161A21;--card2:#1B2029;--ink:#E8E6E1;
 --dim:#9CA1AB;--gold:#D9A441;--bad:#D97862;--ok:#5CB878;--line:rgba(232,230,225,.10);
 --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace;
 --sans:system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--ground);color:var(--ink);font:14px/1.55 var(--sans)}}
a{{color:var(--gold);text-decoration:none}} a:hover{{text-decoration:underline}}
.wrap{{max-width:1500px;margin:0 auto;padding:16px 18px 60px}}
h1{{font-size:15px;letter-spacing:.16em;text-transform:lowercase;color:var(--gold);
 margin:0;font-weight:600;display:inline-block}}
h2{{font-size:11px;letter-spacing:.11em;text-transform:uppercase;color:var(--dim);
 margin:20px 0 7px;font-weight:600}}
.src{{font:11px/1.5 var(--mono);color:var(--dim);opacity:.7;margin:0 0 9px}}
.mono{{font-family:var(--mono)}} .dim{{color:var(--dim)}}
.top{{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;
 border-bottom:1px solid var(--line);padding-bottom:10px}}
#livedot{{width:8px;height:8px;border-radius:50%;background:var(--dim);display:inline-block;
 margin-right:6px;vertical-align:middle}}
#livedot.on{{background:var(--ok);animation:beat 1.6s ease-in-out infinite}}
@keyframes beat{{0%,100%{{opacity:.35}}50%{{opacity:1}}}}
.strip{{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}}
.stat{{background:var(--card);border:1px solid var(--line);border-radius:7px;
 padding:8px 12px;min-width:96px}}
.stat b{{display:block;font:19px/1.15 var(--mono)}}
.stat span{{font-size:10px;letter-spacing:.05em;color:var(--dim);text-transform:uppercase}}
.cols{{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr) minmax(300px,.85fr);
 gap:16px;align-items:start}}
@media(max-width:1180px){{.cols{{grid-template-columns:1fr}}}}
.panel{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:13px}}
svg{{display:block;width:100%;height:auto;overflow:visible}}
.lbl{{font:600 11.5px var(--mono)}} .sub{{font:10px var(--mono);fill:var(--dim)}}
.t{{display:inline-block;padding:1px 7px;border-radius:99px;font:10px var(--mono);
 letter-spacing:.04em;color:var(--t);border:1px solid color-mix(in srgb,var(--t) 45%,transparent);
 background:color-mix(in srgb,var(--t) 13%,transparent);white-space:nowrap}}
td.dim{{color:var(--dim)}}
.lane{{font:9px var(--mono);fill:var(--dim);opacity:.8}}
.dot{{cursor:pointer;transition:r .12s,opacity .12s}}
.dot:hover,.dot.lit{{r:5.5;opacity:1}}
.arc{{transition:opacity .12s,stroke-width .12s}}
#river.focused .dot{{opacity:.18}} #river.focused .dot.lit{{opacity:1}}
#river.focused .arc{{opacity:.05}} #river.focused .arc.lit{{opacity:.95;stroke-width:1.8}}
/* HOVER: the graph answers before you click — the hovered seat keeps full opacity, its
   edges brighten, everything unrelated recedes. */
.node{{cursor:pointer}} .node:focus{{outline:none}}
.node:focus .halo,.node:hover .halo{{fill-opacity:.30;stroke-width:2.6}}
#brain.focused .node{{opacity:.22;transition:opacity .16s}}
#brain.focused .node.on{{opacity:1}}
#brain.focused .edge{{opacity:.05 !important;transition:opacity .16s}}
#brain.focused .edge.on{{opacity:.95 !important}}
.edge{{transition:opacity .16s,stroke-width .16s}}
.ping{{pointer-events:none}}
.ping.fire{{animation:ping 1s ease-out}}
@keyframes ping{{0%{{opacity:.9;stroke-width:3}}100%{{opacity:0;stroke-width:1;r:78}}}}
table{{width:100%;border-collapse:collapse;font-size:12.5px}}
td,th{{padding:3px 6px;border-bottom:1px solid rgba(232,230,225,.05);text-align:left}}
th{{font:10px var(--mono);color:var(--dim);letter-spacing:.06em;text-transform:uppercase}}
.arr{{color:var(--dim);width:16px;text-align:center}} .num{{text-align:right;color:var(--gold)}}
.trow{{cursor:pointer}} .trow:hover{{background:rgba(217,164,65,.09)}}
.spectrum{{display:grid;grid-template-columns:repeat(auto-fill,minmax(212px,1fr));gap:5px}}
.k{{display:flex;align-items:baseline;gap:8px;padding:5px 9px;border-radius:6px;
 border:1px solid var(--line);font-size:12px}}
.k .n{{font:600 13px var(--mono);min-width:34px;text-align:right}}
.k .kn{{font-family:var(--mono);font-size:11px}}
.k.lit{{background:rgba(217,164,65,.07);border-color:rgba(217,164,65,.28);cursor:pointer}}
.k.lit:hover{{background:rgba(217,164,65,.16)}} .k.lit .n{{color:var(--gold)}}
.k.dark{{opacity:.45}} .k.dark .n{{color:var(--dim)}}
.k .never{{margin-left:auto;font:9px var(--mono);letter-spacing:.05em;color:var(--bad)}}
.k.descent{{opacity:1;border-color:rgba(217,120,98,.45);background:rgba(217,120,98,.07)}}
/* THE TAIL — one row per event, newest first, clickable, and it MOVES. */
#tail{{max-height:520px;overflow-y:auto;font-family:var(--mono);font-size:11.5px}}
.ev{{display:grid;grid-template-columns:58px 1fr auto;gap:8px;padding:4px 7px;
 border-radius:5px;cursor:pointer;border-left:2px solid transparent}}
.ev:hover{{background:var(--card2)}}
.ev.new{{animation:flash 1.8s ease-out}}
@keyframes flash{{0%{{background:rgba(217,164,65,.42)}}100%{{background:transparent}}}}
.ev .t{{color:var(--dim)}} .ev .k{{border:0;padding:0;display:inline}}
.ev .g{{color:var(--dim);opacity:.85}}
.ev.sel{{border-left-color:var(--gold);background:var(--card2)}}
.filters{{display:flex;gap:6px;flex-wrap:wrap;margin:0 0 9px}}
.filters button,.filters select{{background:var(--card2);color:var(--ink);
 border:1px solid var(--line);border-radius:5px;padding:3px 9px;font:11px var(--mono);
 cursor:pointer}}
.filters button.on{{border-color:var(--gold);color:var(--gold)}}
#detail{{position:sticky;top:14px;max-height:88vh;overflow-y:auto}}
#detail h3{{margin:0 0 3px;font:600 14px var(--mono)}}
#detail .kv{{display:grid;grid-template-columns:auto 1fr;gap:2px 10px;font:11.5px var(--mono);
 margin:8px 0}}
#detail .kv b{{color:var(--dim);font-weight:400;white-space:nowrap}}
#detail .kv span{{word-break:break-all}}
.sec{{margin-top:11px;padding-top:9px;border-top:1px solid var(--line)}}
.sec h4{{margin:0 0 5px;font:10px var(--mono);letter-spacing:.07em;text-transform:uppercase;
 color:var(--dim)}}
.note{{border-left:2px solid var(--bad);padding:8px 11px;margin:9px 0 0;
 background:rgba(217,120,98,.06);border-radius:0 6px 6px 0;font-size:12.5px}}
.note b{{color:var(--bad)}}
footer{{margin-top:24px;font:11px/1.6 var(--mono);color:var(--dim);opacity:.75}}
</style>
<div class="wrap">
<div class="top"><h1>the conceptric</h1>
 <span class="src" style="margin:0"><span id="livedot"></span><span id="livetext">connecting…</span></span>
 <span class="src" style="margin:0 0 0 auto"><a href="/front">← the front door</a></span></div>
<p class="src">{e(payload["source"])}<br>{e(payload["staleness"])} · read
 <span title="{e(payload["read_at"])} in the store">{e(payload["read_at"][11:16])} UTC</span> ·
 newest event <span id="agev">{t["age_seconds"]}</span>s ago</p>

<div class="strip">
 <div class="stat"><b id="n-events">{t["events"]}</b><span>events</span></div>
 <div class="stat"><b id="n-edges">{t["causal_edges"]}</b><span>causal edges</span></div>
 <div class="stat"><b>{t["dangling_causes"]}</b><span>dangling</span></div>
 <div class="stat"><b>{t["correlations"]}</b><span>traces</span></div>
 <div class="stat"><b>{t["kinds_fired"]}/{t["kinds_declared"]}</b><span>kinds fired</span></div>
 <div class="stat"><b>{t["span_hours"]}h</b><span>span</span></div>
</div>

<div class="cols">
 <div>
  <h2>the seats — hover to isolate, click to open</h2>
  <p class="src">seat.message-sent payloads · edge width and node size are message counts</p>
  <div class="panel">{_seat_graph_svg(payload)}
   <table style="margin-top:10px"><tr><th>from</th><th></th><th>to</th><th>msgs</th></tr>
   {traffic}</table></div>
 </div>
 <div>
  <h2>the causal river — time →, arcs point back to what caused each event</h2>
  <p class="src">causation_ids resolved inside this window · hover a dot or a tail row to
   light its whole ancestry</p>
  <div class="filters" id="axis">
   <button data-a="kind" class="on">by kind</button>
   <button data-a="depth">by depth</button>
   <button data-a="seat">by seat</button>
   <span class="src" style="margin:0 0 0 4px" id="axisnote"></span></div>
  <div class="panel" style="margin-bottom:6px">{_river_shell(payload)}</div>
  <p class="src" id="rivernote" style="margin:0 0 14px"></p>
  <h2>the live tail — newest first</h2>
  <div class="filters" id="filters">
   <button data-f="all" class="on">all</button>
   <button data-f="descent">descent</button>
   <button data-f="mail">mail</button>
   <button data-f="recon">reconstruction</button>
   <span class="src" style="margin:0 0 0 4px" id="tailnote"></span></div>
  <div class="panel"><div id="tail"></div></div>
 </div>
 <div id="detail" class="panel">
  <h3 class="dim">nothing open</h3>
  <p class="src">click a seat in the graph, a row in the traffic table, or any event in
   the tail. Everything here is fetched live from the store when you ask for it — the
   page holds no copy of it.</p>
 </div>
</div>

<h2>what the engine is reaching for</h2>
<p class="src">{e(payload["pull"]["note"])}</p>
<div class="cols" style="grid-template-columns:minmax(0,1.6fr) minmax(0,1fr)">
 <div class="panel"><h4 style="margin:0 0 6px;font:10px var(--mono);letter-spacing:.07em;
  text-transform:uppercase;color:var(--dim)">goals, most pulled — {payload["pull"]["goals_total"]}
  reconstructions over {payload["pull"]["goals_distinct"]} distinct goals</h4>
  <table>{"".join(
    f'<tr><td class="num" style="width:44px">{g["count"]}</td><td>{e(g["goal"][:110])}</td></tr>'
    for g in payload["pull"]["goals"])}</table></div>
 <div class="panel"><h4 style="margin:0 0 6px;font:10px var(--mono);letter-spacing:.07em;
  text-transform:uppercase;color:var(--dim)">what it addresses, by class</h4>
  <table>{"".join(
    f'<tr><td class="num" style="width:44px">{c["count"]}</td><td class="mono">{e(c["cls"])}</td></tr>'
    for c in payload["pull"]["classes"])}</table></div>
</div>

<h2>the machinery — the stores it writes, the doors it answers on</h2>
<p class="src">{e(payload["machinery"]["source"])}<br>{e(payload["machinery"]["staleness"])}</p>
<div class="cols" style="grid-template-columns:minmax(0,1.7fr) minmax(0,1fr)">
 <div class="panel">
  <h4 style="margin:0 0 6px;font:10px var(--mono);letter-spacing:.07em;text-transform:uppercase;
   color:var(--dim)">{payload["machinery"]["counts"]["stores"]} stores ·
   {payload["machinery"]["counts"]["past_budget"]} past their own budget</h4>
  <table>{"".join(
   f'<tr title="{escape_attr(r["path"])}">'
   f'<td>{chip(r["state"], "#a03626" if r["state"] == "past its budget" else "#8a6d1f" if r["state"] != "fresh" else "#2e7d32")}</td>'
   f'<td>{e(r["label"][:74])}</td>'
   f'<td class="num">{"" if r["age_h"] is None else str(r["age_h"]) + "h"}</td>'
   f'<td class="num dim">{"" if r["budget_h"] is None else "/ " + str(r["budget_h"]) + "h"}</td>'
   f'</tr>' for r in payload["machinery"]["stores"][:14])}</table>
  <p class="src" style="margin:8px 0 0">{e(payload["machinery"]["note"])}</p>
 </div>
 <div class="panel">
  <h4 style="margin:0 0 6px;font:10px var(--mono);letter-spacing:.07em;text-transform:uppercase;
   color:var(--dim)">the doors</h4>
  {(
    f'<p>{chip(str(payload["machinery"]["doors"]["down"]) + " not answering", "#a03626" if payload["machinery"]["doors"]["down"] else "#2e7d32")} '
    f'of {payload["machinery"]["doors"]["doors"]} censused · banked '
    f'{payload["machinery"]["doors"]["age_h"]}h ago</p>'
    + "".join(f'<div class="ev"><span class="t">{e(str(d.get("status") or ""))}</span>'
              f'<span class="mono">{e(d["door"])}</span></div>'
              for d in payload["machinery"]["doors"].get("failing", []))
    + '<p class="src">a NAMED LIST, not every route — a door absent from it is uncertified, '
      'not certified green. It is banked when the census is opened; this pane fires nothing.</p>'
    if payload["machinery"]["doors"]["state"] == "certified" else
    f'<p>{chip(payload["machinery"]["doors"]["state"], "#8a6d1f")}</p>'
    f'<p class="src">{e(payload["machinery"]["doors"].get("why", ""))}</p>'
  )}
 </div>
</div>

<h2>the vocabulary — what the engine can record, and what it has</h2>
<p class="src">laplace.representation.atlas_bridge.EventKind ({t["kinds_declared"]} declared) against
 observed counts. An unfired kind is shown AS UNFIRED, never omitted.</p>
<div class="spectrum">{spectrum}</div>
{'<div class="note"><b>THE DESCENT LANE IS DARK.</b> ' + e(d["why"]) + '</div>'
 if d["dark"] else
 '<div class="note" style="border-left-color:var(--ok);background:rgba(92,184,120,.07)">'
 '<b style="color:var(--ok)">DESCENT IS EMITTING.</b> reconstruction.moved '
 + str(d["moved"]) + ' · reconstruction.materialized ' + str(d["materialized"])
 + ' — this lane was dark until it was wired; every call now draws itself here.</div>'}

<footer>RENDER OF ROWS — laplace.engine.descent_telemetry.project() returned every number above;
 this page computes none of them. The live feed is /front/stream (atlas:changed) →
 /front/conceptric/delta.<br>W12 · his commission, 2026-08-25 · interface-seat</footer>
</div>
<script>
"use strict";
const TAIL = {json.dumps(payload["tail"])};
const HUE = {json.dumps({s["seat"]: s["hue"] for s in payload["seats"]})};
let riverDirty = false;\nlet cursor = {t["events"]}, filter = "all", sel = null, lastAt = {json.dumps(payload["totals"]["last_at"])};

const $ = (s, r) => (r || document).querySelector(s);

/* TIME IS RENDERED IN HIS CLOCK, NOT THE STORE'S. Events bank in UTC and the tail printed
   the raw UTC clock face — so at 21:47 local he read a 4-minute-old event as "20:47" and
   concluded the live feed had been dead for an hour. It had not; the render was an hour
   out because it showed a timezone he does not live in, with no marker saying so.
   Relative age is what he actually asks of a live feed ("is this moving"), so that leads;
   the exact local wall clock is summonable on hover, and the raw UTC stamp rides in the
   title beside it because it is the value in the store. */
function ago(iso) {{
  const t = Date.parse(iso);
  if (!isFinite(t)) return "\u2014";
  const s = Math.max(0, Math.round((Date.now() - t) / 1000));
  if (s < 60) return s + "s";
  if (s < 3600) return Math.round(s / 60) + "m";
  if (s < 86400) return (s / 3600).toFixed(1) + "h";
  return Math.round(s / 86400) + "d";
}}
function localClock(iso) {{
  const d = new Date(iso);
  return isFinite(d.getTime()) ? d.toLocaleTimeString([], {{hour12: false}}) : "\u2014";
}}
function timeTitle(iso) {{
  return localClock(iso) + " your clock \u00b7 " + iso + " in the store";
}}
const el = (t, c, txt) => {{ const n = document.createElement(t);
  if (c) n.className = c; if (txt != null) n.textContent = txt; return n; }};

/* ---- the tail ------------------------------------------------------------ */
const KINDF = {{
  all:     () => true,
  descent: k => k.startsWith("reconstruction."),
  mail:    k => k.startsWith("seat.message"),
  recon:   k => k === "repl.evaluated" || k.startsWith("reconstruction."),
}};
function evRow(ev, isNew) {{
  const row = el("div", "ev" + (isNew ? " new" : ""));
  row.dataset.id = ev.event_id; row.dataset.kind = ev.kind;
  const ts = el("span", "t", ago(ev.at));
  ts.title = timeTitle(ev.at);
  row.appendChild(ts);
  const mid = el("span");
  const k = el("span", "k"); k.textContent = ev.kind.split(".").pop();
  k.style.color = HUE[ev.seat] || "#7FA9D9";
  mid.appendChild(k);
  const label = ev.goal || ev.subject || "";
  if (label) mid.appendChild(el("span", "g", "  " + label));
  row.appendChild(mid);
  row.appendChild(el("span", "t", ev.to ? "→ " + ev.to : (ev.seat || ev.actor || "")));
  row.addEventListener("click", () => openEvent(ev.event_id, row));
  row.addEventListener("mouseenter", () => {{ if (ev.i != null) lightTrace(ev.i); }});
  row.addEventListener("mouseleave", dimTrace);
  return row;
}}
function paintTail() {{
  const box = $("#tail"); box.textContent = "";
  const rows = TAIL.filter(e => KINDF[filter](e.kind)).slice().reverse();
  rows.forEach(e => box.appendChild(evRow(e, false)));
  $("#tailnote").textContent = rows.length + " shown";
}}

/* ---- detail panes: fetched live, never held in the page ------------------- */
async function pane(url) {{
  const d = $("#detail"); d.textContent = "";
  d.appendChild(el("h3", "dim", "loading…"));
  try {{
    const r = await fetch(url, {{ headers: {{ Accept: "application/json" }} }});
    return await r.json();
  }} catch (err) {{ d.textContent = ""; d.appendChild(el("h3", "", "could not read"));
    d.appendChild(el("p", "src", String(err))); return null; }}
}}
function kv(parent, pairs) {{
  const g = el("div", "kv");
  for (const [k, v] of pairs) {{ if (v == null || v === "") continue;
    g.appendChild(el("b", null, k)); g.appendChild(el("span", null, String(v))); }}
  parent.appendChild(g);
}}
function section(parent, title, rows, onClick) {{
  if (!rows || !rows.length) return;
  const s = el("div", "sec"); s.appendChild(el("h4", null, title));
  rows.forEach(ev => {{ const r = evRow(ev, false);
    if (onClick) {{ r.addEventListener("click", () => onClick(ev)); }} s.appendChild(r); }});
  parent.appendChild(s);
}}
async function openSeat(id) {{
  const j = await pane("/front/conceptric/seat?id=" + encodeURIComponent(id));
  if (!j) return;
  const d = $("#detail"); d.textContent = "";
  const h = el("h3", null, j.seat); h.style.color = j.hue; d.appendChild(h);
  kv(d, [["sent", j.totals.sent], ["received", j.totals.received],
         ["acts", j.totals.acts],
         ["in its inbox now", j.totals.pending === null
            ? "could not read — see below" : j.totals.pending]]);
  if (j.pending_error) {{
    const w = el("div", "sec");
    w.appendChild(el("h4", null, "the inbox could not be read"));
    w.appendChild(el("p", "src", j.pending_error));
    w.appendChild(el("p", "src", "this is NOT an empty inbox — the count above is "
      + "withheld rather than shown as zero."));
    d.appendChild(w);
  }}
  if (j.peers.length) {{
    const s = el("div", "sec"); s.appendChild(el("h4", null, "talks to"));
    j.peers.forEach(pr => {{ const line = el("div", "ev");
      line.appendChild(el("span", "t", String(pr.count)));
      line.appendChild(el("span", null, pr.seat));
      line.addEventListener("click", () => openSeat(pr.seat)); s.appendChild(line); }});
    d.appendChild(s);
  }}
  if (j.pending && j.pending.length) {{
    const s = el("div", "sec"); s.appendChild(el("h4", null, "holding, unacknowledged"));
    j.pending.forEach(m => s.appendChild(el("div", "ev", m.error
      ? m.error : (m.from + " · " + m.type)))); d.appendChild(s);
  }}
  if (j.last_reconstruction) section(d, "last reconstruction", [j.last_reconstruction]);
  section(d, "recent sends", j.recent_sent.slice(0, 8));
  section(d, "recent acts", j.recent_acts.slice(0, 8));
  d.appendChild(el("p", "src", j.source));
  focusSeat(id);
}}
async function openEvent(id, row) {{
  if (sel) sel.classList.remove("sel");
  if (row) {{ row.classList.add("sel"); sel = row; }}
  const j = await pane("/front/conceptric/event?id=" + encodeURIComponent(id));
  if (!j) return;
  const d = $("#detail"); d.textContent = "";
  if (j.absent) {{ d.appendChild(el("h3", null, "no such event"));
    d.appendChild(el("p", "src", j.why)); return; }}
  const ev = j.event;
  d.appendChild(el("h3", null, ev.kind));
  kv(d, [["at", ev.at], ["actor", ev.actor], ["seat", ev.seat], ["to", ev.to],
         ["goal", ev.goal], ["RETURNED", ev.returned || "— nothing this event names"],
         ["fibre", ev.fibre], ["correlation", ev.correlation],
         ["subject", ev.subject], ["residual", ev.residual],
         ["event", ev.event_id]]);
  if (j.runtime) kv(d, Object.entries(j.runtime).slice(0, 6));
  section(d, "caused by", j.caused_by, e => openEvent(e.event_id));
  section(d, "went on to cause", j.caused, e => openEvent(e.event_id));
  if (j.payload) {{
    const s = el("div", "sec"); s.appendChild(el("h4", null, "payload"));
    kv(s, Object.entries(j.payload)); d.appendChild(s);
  }}
  d.appendChild(el("p", "src", j.source));
}}

/* ---- the river, drawn here so it can RE-PROJECT without a round trip ------- */
const river = $("#river");
const BY_I = {{}}; TAIL.forEach(e => {{ BY_I[e.i] = e; }});
const SVGNS = "http://www.w3.org/2000/svg";
let axis = "kind";
const AXIS = {{
  kind:  e => e.kind.split(".").pop(),        // human face; full kind on hover
  depth: e => "depth " + (e.depth || 0),
  seat:  e => e.seat || e.to || e.actor || "(none)",
}};
const AXIS_NOTE = {{
  kind:  "one lane per event kind — what sort of thing happened",
  depth: "one lane per distance from a causal root — how far down a chain of consequence "
       + "each event sits. The kind projection cannot show this at all.",
  seat:  "one lane per seat — whose work each event is",
}};
function svg(tag, attrs) {{
  const n = document.createElementNS(SVGNS, tag);
  for (const k in attrs) n.setAttribute(k, attrs[k]);
  return n;
}}
function drawRiver() {{
  if (!river) return;
  const rows = TAIL.slice(-90);
  river.textContent = "";
  if (!rows.length) return;
  const key = AXIS[axis];
  let lanes = [...new Set(rows.map(key))];
  lanes.sort(axis === "depth"
    ? (a, b) => parseInt(a.slice(6), 10) - parseInt(b.slice(6), 10)
    : (a, b) => a.localeCompare(b));

  /* THE GUTTER IS MEASURED, NOT GUESSED. It was a hardcoded 106px while the longest
     label needed ~140, so labels ran off the left edge and collided with the margin
     note. 6.05px per char at 9px monospace, floored so a short set still reads. */
  const gutter = Math.max(64, Math.ceil(Math.max(...lanes.map(l => l.length)) * 6.05) + 16);
  const W = Math.max(640, river.clientWidth || 700), top = 18;
  const H = Math.max(150, Math.min(300, 34 + lanes.length * 26));
  const bot = H - 16;
  river.setAttribute("viewBox", "0 0 " + W + " " + H);
  const laneY = {{}};
  lanes.forEach((l, i) => {{ laneY[l] = top + i * ((bot - top) / Math.max(lanes.length - 1, 1)); }});
  const step = (W - gutter - 14) / Math.max(rows.length - 1, 1);
  const X = i => gutter + i * step;
  const pos = {{}}; rows.forEach((e, n) => {{ pos[e.i] = n; }});

  lanes.forEach(l => {{
    const y = laneY[l];
    river.appendChild(svg("line", {{ x1: gutter - 6, y1: y, x2: W - 8, y2: y,
      stroke: "rgba(232,230,225,.06)" }}));
    const t = svg("text", {{ x: gutter - 12, y: y + 3.4, "text-anchor": "end", class: "lane" }});
    t.textContent = l; river.appendChild(t);
  }});
  const arcs = svg("g", {{ id: "arcs" }}), dots = svg("g", {{ id: "dots" }});
  let outside = 0;
  rows.forEach(e => {{
    outside += e.causes_outside_window || 0;
    (e.causes || []).forEach(c => {{
      if (pos[c] === undefined) return;
      const x1 = X(pos[c]), y1 = laneY[key(BY_I[c])];
      const x2 = X(pos[e.i]), y2 = laneY[key(e)];
      const a = svg("path", {{ class: "arc", "data-from": c, "data-to": e.i,
        d: "M" + x1 + "," + y1 + " Q" + ((x1 + x2) / 2) + "," + (Math.min(y1, y2) - 13)
           + " " + x2 + "," + y2,
        fill: "none", stroke: "#D9A441", "stroke-width": ".9", opacity: ".24" }});
      arcs.appendChild(a);
    }});
  }});
  rows.forEach(e => {{
    const d = svg("circle", {{ class: "dot", "data-i": e.i, "data-id": e.event_id,
      cx: X(pos[e.i]), cy: laneY[key(e)], r: 3,
      fill: HUE[e.seat] || HUE[e.to] || "#7FA9D9", opacity: ".8" }});
    const ttl = svg("title");
    ttl.textContent = ago(e.at) + " ago · " + localClock(e.at) + "  " + e.kind
      + (e.goal ? "  " + e.goal : "") + "  depth " + (e.depth || 0);
    d.appendChild(ttl);
    d.addEventListener("mouseenter", () => lightTrace(e.i));
    d.addEventListener("mouseleave", dimTrace);
    d.addEventListener("click", () => openEvent(e.event_id));
    dots.appendChild(d);
  }});
  river.appendChild(arcs); river.appendChild(dots);
  /* THE MARGIN NOTE LIVES IN THE CAPTION, not in the plot. Right-anchoring it inside the
     SVG at the lane-label x ran it off the left edge and into the labels. */
  $("#rivernote").textContent = rows.length + " events · " + lanes.length + " lanes"
    + (outside ? " · " + outside + " cause(s) older than this window — counted, not drawn" : "");
  $("#axisnote").textContent = AXIS_NOTE[axis];
}}
document.querySelectorAll("#axis button").forEach(b => {{
  b.addEventListener("click", () => {{
    document.querySelectorAll("#axis button").forEach(x => x.classList.remove("on"));
    b.classList.add("on"); axis = b.dataset.a; drawRiver();
  }});
}});
addEventListener("resize", () => drawRiver());
function ancestry(i, seen) {{
  seen = seen || new Set();
  if (seen.has(i)) return seen;
  seen.add(i);
  const ev = BY_I[i];
  if (ev) (ev.causes || []).forEach(c => ancestry(c, seen));
  return seen;
}}
function lightTrace(i) {{
  if (!river) return;
  const set = ancestry(i);
  river.classList.add("focused");
  river.querySelectorAll(".dot").forEach(d =>
    d.classList.toggle("lit", set.has(+d.dataset.i)));
  river.querySelectorAll(".arc").forEach(a =>
    a.classList.toggle("lit", set.has(+a.dataset.to) && set.has(+a.dataset.from)));
}}
function dimTrace() {{ if (river) river.classList.remove("focused"); }}
/* ---- hover isolation ------------------------------------------------------ */
const brain = $("#brain");
function focusSeat(id) {{
  brain.classList.add("focused");
  brain.querySelectorAll(".node").forEach(n =>
    n.classList.toggle("on", n.dataset.seat === id));
  brain.querySelectorAll(".edge").forEach(p =>
    p.classList.toggle("on", p.dataset.from === id || p.dataset.to === id));
}}
function unfocus() {{ brain.classList.remove("focused"); }}
brain.querySelectorAll(".node").forEach(n => {{
  n.addEventListener("mouseenter", () => focusSeat(n.dataset.seat));
  n.addEventListener("mouseleave", unfocus);
  n.addEventListener("focus", () => focusSeat(n.dataset.seat));
  n.addEventListener("click", () => openSeat(n.dataset.seat));
  n.addEventListener("keydown", ev => {{ if (ev.key === "Enter" || ev.key === " ")
    {{ ev.preventDefault(); openSeat(n.dataset.seat); }} }});
}});
document.querySelectorAll(".trow").forEach(r => {{
  r.addEventListener("mouseenter", () => {{
    brain.classList.add("focused");
    brain.querySelectorAll(".node").forEach(n => n.classList.toggle("on",
      n.dataset.seat === r.dataset.from || n.dataset.seat === r.dataset.to));
    brain.querySelectorAll(".edge").forEach(p => p.classList.toggle("on",
      p.dataset.from === r.dataset.from && p.dataset.to === r.dataset.to));
  }});
  r.addEventListener("mouseleave", unfocus);
  r.addEventListener("click", () => openSeat(r.dataset.from));
}});
document.querySelectorAll("#filters button").forEach(b => {{
  b.addEventListener("click", () => {{
    document.querySelectorAll("#filters button").forEach(x => x.classList.remove("on"));
    b.classList.add("on"); filter = b.dataset.f; paintTail();
  }});
}});
document.querySelectorAll(".k.lit").forEach(k => {{
  k.addEventListener("click", () => {{
    const want = k.dataset.kind;
    KINDF.one = kk => kk === want; filter = "one"; paintTail();
    document.querySelectorAll("#filters button").forEach(x => x.classList.remove("on"));
    $("#tailnote").textContent += " · only " + want;
  }});
}});

/* ---- LIVE: atlas:changed tells us the store moved; we ask what happened ---- */
function ping(seat) {{
  const n = brain.querySelector('.node[data-seat="' + CSS.escape(seat) + '"] .ping');
  if (!n) return; n.classList.remove("fire"); void n.offsetWidth; n.classList.add("fire");
}}
async function pull() {{
  try {{
    const r = await fetch("/front/conceptric/delta?after=" + cursor,
                          {{ headers: {{ Accept: "application/json" }} }});
    const j = await r.json();
    if (!j.events || !j.events.length) return;
    cursor = j.event_cursor;
    const box = $("#tail");
    j.events.forEach(ev => {{
      TAIL.push(ev); BY_I[ev.i] = ev; riverDirty = true;
      if (!KINDF[filter](ev.kind)) return;
      const row = evRow(ev, true);
      box.insertBefore(row, box.firstChild);
      if (ev.seat) ping(ev.seat);
      if (ev.to) ping(ev.to);
    }});
    while (TAIL.length > 400) TAIL.shift();
    $("#n-events").textContent = cursor;
    lastAt = j.events[j.events.length - 1].at || lastAt;
    $("#tailnote").textContent = box.childElementCount + " shown";
    if (j.truncated) $("#tailnote").textContent += " · " + j.truncated + " older not drawn";
  }} catch (err) {{ /* a failed pull is not a reason to kill the feed */ }}
}}
function live() {{
  const s = new EventSource("/front/stream?sources=atlas");
  s.addEventListener("open", () => {{ $("#livedot").classList.add("on");
    $("#livetext").textContent = "live"; }});
  s.addEventListener("atlas:changed", pull);
  s.addEventListener("rolled", () => {{ cursor = 0; pull(); }});
  s.addEventListener("error", () => {{ $("#livedot").classList.remove("on");
    $("#livetext").textContent = "reconnecting…"; }});
}}
setInterval(() => {{ if (!lastAt) return;
  const age = Math.round((Date.now() - Date.parse(lastAt)) / 1000);
  if (age >= 0) $("#agev").textContent = age; }}, 1000);

paintTail(); drawRiver(); live();\nsetInterval(() => {{ if (riverDirty) {{ riverDirty = false; drawRiver(); }} }}, 1200);
</script>"""


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="laplace-descent-telemetry", description=__doc__)
    ap.add_argument("--store", default=None)
    ap.add_argument("--tail", type=int, default=90)
    ap.add_argument("--json", action="store_true", help="emit the rows, not the render")
    ap.add_argument("-o", "--out", default=None, help="write the page here")
    a = ap.parse_args(argv)
    payload = project(a.store, tail=a.tail)
    if a.json:
        print(json.dumps(payload, indent=1))
        return 0
    page = render(payload)
    if a.out:
        Path(a.out).write_text(page, encoding="utf-8")
        print(json.dumps({"wrote": a.out, "bytes": len(page),
                          "events": payload["totals"]["events"],
                          "kinds_fired": payload["totals"]["kinds_fired"],
                          "descent_dark": payload["descent"]["dark"]}, indent=1))
    else:
        print(page)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
