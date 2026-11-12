"""growth_surface.py — the growth cockpit's data doors + the four tension verbs.

The scanner owns the HTTP server and dispatches ``/growth/*`` and ``/surface/contract``
here through :func:`handle` (the same handler contract as ``storyboard`` / ``desk`` /
``assets_surface``). This module is the seam chosen over threading the cockpit into the
``/corpus/*`` inline chain: the composed brief, the six read doors, and the four
actor-guarded verb doors are one testable surface, and the false-ruling refusal (the
posted action fingerprint recomputed and matched) lives in one place.

The reads mint their payloads server-side from the composition layer (``pipeline.demand``
+ ``pipeline.composed`` — E2's write side): the client never reconstructs meaning. The
brief is the resting state — a few composed sentences plus one-line counts; everything
else is a count until a focus materialises it.

The verb doors ride REAL organs and refuse in plain words where an organ does not apply:
  * REALIGN/RESPINE  → a banked note on the corpus feedback ledger (author-gated);
  * REGOAL           → the goal supersede through the rewire ledger (an add-node naming
                       the old goal in ``supersedes``); ``growth.regoal`` is reserved for a
                       laddered project, and no project is laddered today, so this door
                       rides the supersede path and says so;
  * HOLD/WAIVE       → a banked tolerance row naming the mismatch clause (author-gated);
  * DISMISS SIGNAL   → a fingerprinted suppression keyed on the tension id, so the same
                       detection stays dismissed until its inputs change.

Every verb door is actor-guarded (``by`` an author actor), banks the optional note on the
same record (one write), and refuses when the posted verb+fingerprint pair does not match
the served action row — the selection and the displayed consequence cannot disagree.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_JSON = "application/json; charset=utf-8"
_CONTRACT_KEYS = ("surface", "purpose", "reads", "verbs", "counts", "structural",
                  "states", "queues")


def _repo_root() -> Path:
    from laplace.core.checkout import repo_root as rr   # the serving checkout's owner (the server module held the same object under an old name)
    return rr()


def _q1(query: dict, key: str, default: str = "") -> str:
    v = query.get(key, default)
    if isinstance(v, (list, tuple)):
        v = v[0] if v else default
    return (v or default).strip()


def _json_resp(status: int, obj: Any) -> tuple[int, str, bytes]:
    return status, _JSON, json.dumps(obj, ensure_ascii=False).encode("utf-8")


def _default_corpus() -> str:
    from laplace.research import corpus_ingest as _ci
    return _ci.default_corpus(_repo_root())


# ---------------------------------------------------------------------------
# the readers — one composed payload per summonable object
# ---------------------------------------------------------------------------

def all_tensions(repo_root: Path, corpus: str) -> list[dict]:
    """The tension rows for a corpus — the DEMOTE signature and the authored-goal
    reconciliation signature — each carrying its composed block whole."""
    from laplace.pipeline import demand
    rows: list[dict] = []
    try:
        rows += demand.goal_tensions(repo_root, corpus)
    except Exception:  # noqa: BLE001 — a signature that cannot read degrades to none
        pass
    try:
        rows += demand.author_goal_tensions(repo_root, corpus)
    except Exception:  # noqa: BLE001
        pass
    return rows


#: a red demand whose gap IS a coverage-axis gap → the outer axis it routes to. Small,
#: explicit, NAMED (the defensible subset): a claim citing no real corpus raises the
#: literature axis; an unresolved figure promise raises the demonstration axis; a claim
#: drawing from nothing below raises the validation axis. A demand outside this set carries
#: no routing button (its axis is not derivable), which is stated by absence, not guessed.
_DEMAND_AXIS = {
    "D-real-corpus-citation": "literature",
    "D-figure-resolves": "demonstration",
    "D-every-claim-has-a-result": "validation",
}


def _axis_route_index(repo_root: Path, corpus: str) -> dict[str, dict]:
    """Per outer axis with a live gap, the routing action served on its coverage row —
    ``{verb, consequence, fingerprint}`` — so a queue row whose demand maps to that axis
    can offer the SAME door (and post the same fingerprint the coverage button posts)."""
    idx: dict[str, dict] = {}
    try:
        for row in coverage_rows(repo_root, corpus):
            dec = (row.get("composed") or {}).get("decision") or {}
            act = next(iter(dec.get("actions") or []), None)
            if act:
                idx[row.get("axis")] = {"verb": act.get("verb"),
                                        "consequence": act.get("consequence"),
                                        "fingerprint": act.get("fingerprint")}
    except Exception:  # noqa: BLE001 — a coverage read that fails leaves no route hints
        pass
    return idx


def red_queue(repo_root: Path, corpus: str) -> list[dict]:
    """The demand-audit rows that need attention (verdict ``red``), each composed — the
    queue chip counts exactly these, and opening it materialises exactly these. A red row
    whose demand maps to a coverage axis with a live gap is enriched (additively) with that
    axis's routing action, so the surface can offer the axis-gap door on the row."""
    from laplace.pipeline import demand
    out = demand.audit(repo_root, corpus)
    reds = [r for r in out.get("rows", []) if r.get("verdict") == "red"]
    idx = _axis_route_index(repo_root, corpus)
    for r in reds:
        axis = _DEMAND_AXIS.get(r.get("demand_id"))
        if axis and axis in idx:
            r["route_axis"] = axis
            r["route"] = idx[axis]
    return reds


def coverage_rows(repo_root: Path, corpus: str) -> list[dict]:
    """The three coverage axes, each carrying its composed row."""
    from laplace.pipeline import demand
    cov = demand.coverage_vector(repo_root, corpus)
    rows = []
    for key in ("literature", "validation", "demonstration"):
        ax = cov.get(key)
        if isinstance(ax, dict):
            rows.append({"axis": key, "covered": ax.get("covered", 0),
                         "total": ax.get("total", 0), "uncovered": ax.get("uncovered", []),
                         "composed": ax.get("composed")})
    return rows


def open_work_order_rows(repo_root: Path, corpus: str) -> list[dict]:
    """The OPEN work orders for this corpus, each with its full composed row."""
    from laplace.manuscript import storyboard as _sb
    orders = _sb.open_work_orders(_sb.load_work_orders(repo_root))
    return [o for o in orders if (o.get("corpus") or "") == corpus]


def growth_situation(repo_root: Path, corpus: str) -> dict:
    """The growth state for a corpus (the sidecar rung or a pre-ladder null)."""
    from laplace.pipeline import growth
    return growth.growth_state(repo_root, corpus)


# ---------------------------------------------------------------------------
# the reconciled tension — banked history, read-only (the last authored-goal
# tension he already RULED). No fabrication: every field is a real record.
# ---------------------------------------------------------------------------

def _tension_miss_note(corpus: str, gt_id: str = "") -> str:
    """The composed sentence a deep link to a missing/ruled tension hears — the same
    wording the write door refuses with, so the read and the write agree. Minted
    server-side; the client renders it verbatim (it reconstructs no meaning)."""
    idp = f" {gt_id!r}" if gt_id else ""
    return (f"No open tension{idp} on {corpus!r} — it may be already ruled or dismissed. "
            "A tension is a drift the machine cannot rule on its own; when one is open it "
            "pins here for your call, and when it is ruled the ruling is banked as history.")


def reconciled_tension(repo_root: Path, corpus: str) -> dict | None:
    """The most recent authored-goal tension this corpus has already RULED, reconstructed
    as read-only banked history. READ-ONLY.

    Fires when a GENUINELY-HIS ``author-goal`` verdict names this corpus AND a goal
    supersede postdates it (the mechanical reading of "reconciled" — the same predicate
    that drops the live tension). The tension is recomposed the way it was posed (its
    composed conflict and the four verbs it offered, REGOAL recommended) and paired with
    the REAL ruling banked: his REGOAL add-node, his commentary verbatim, the new goal
    essence, and the record's actor and timestamp. Nothing is synthesised — absence of
    either half returns ``None`` (stated by the caller, never a fabricated row)."""
    from laplace.engine import author_proxy
    from laplace.research import corpus_ingest as _ci

    verdicts = author_proxy.load_verdicts(repo_root)
    verdict = None
    for v in verdicts:
        if v.get("kind") != "author-goal" or v.get("confidence") != "GENUINELY-HIS":
            continue
        from laplace.pipeline import demand as _demand
        if not _demand._verdict_names_corpus(v, corpus):
            continue
        verdict = v
        break
    if verdict is None:
        return None
    when = verdict.get("date") or ""

    # the ruling: the most recent goal add-node whose supersedes is set and whose ts
    # postdates the verdict (the REGOAL he banked through the rewire ledger).
    try:
        recs = _ci.rewire_list(repo_root, corpus)
    except Exception:  # noqa: BLE001 — a roster hiccup reads as not-yet-reconciled
        return None
    ruling_rec = None
    for r in recs:
        if r.get("kind") != "add-node" or not (r.get("supersedes") or "").strip():
            continue
        if str(r.get("ts") or "") <= str(when or ""):
            continue
        if str(r.get("node_kind") or "") and r.get("node_kind") != "goal":
            continue
        if ruling_rec is None or str(r.get("ts") or "") > str(ruling_rec.get("ts") or ""):
            ruling_rec = r
    if ruling_rec is None:
        return None

    # recompose the tension the way it was posed — the verbs it offered, REGOAL recommended.
    from laplace.pipeline import demand as _demand
    net = _demand._net(repo_root, corpus)
    goal = _demand._read_goal(repo_root, corpus, net)
    goal_nodes = goal.get("goal_nodes") or []
    goal_node_id = goal_nodes[0] if goal_nodes else "goal"
    banked_essence = next((e for e in (goal.get("essences") or []) if str(e).strip()), "")
    from laplace.pipeline import composed as _composed
    gt_id, block = _composed.compose_author_goal_tension(
        corpus=corpus, goal_node_id=goal_node_id, banked_goal_essence=banked_essence,
        restatement_gist=str(verdict.get("ruling") or "")[:400],
        reconstruction=_demand._reconstruct_authored_goal(banked_essence),
        gen_note="that reshaping is already queued on the manuscript's current generation",
        goal_version=goal.get("goal_version"), verdict_ref=str(verdict.get("id") or ""))

    return {
        "id": gt_id,
        "signature": "AUTHOR-GOAL",
        "ruled": True,
        "verb": "REGOAL",
        "composed": block,
        "ruling": {
            "record_id": ruling_rec.get("id"),
            "by": ruling_rec.get("by"),
            "ts": ruling_rec.get("ts"),
            "commentary": ruling_rec.get("narrative") or "",
            "superseded": ruling_rec.get("supersedes"),
            "new_goal": ruling_rec.get("node"),
            "new_goal_essence": ruling_rec.get("essence") or "",
        },
        "provenance": {"verdict": verdict.get("id"), "record": ruling_rec.get("id")},
    }


def brief_payload(repo_root: Path, corpus: str) -> dict:
    """The composed BRIEF — the resting state. A few composed sentences on where the
    project sits, plus one-line counts for everything summonable. Minted server-side; the
    client renders it verbatim. Each count equals the rows its door returns (the counts
    law), so a chip of N opens exactly those N."""
    from laplace.pipeline import composed as _composed

    state = growth_situation(repo_root, corpus)
    cov = coverage_rows(repo_root, corpus)
    tensions = all_tensions(repo_root, corpus)
    queue = red_queue(repo_root, corpus)
    wos = open_work_order_rows(repo_root, corpus)
    zero_axes = [c["axis"] for c in cov if c.get("total") and not c.get("covered")]

    rung = state.get("state")
    if rung:
        where = (f"This project sits at the {rung} rung of the growth ladder"
                 + (f", goal version {state.get('goal_version')}" if state.get("goal_version") else "")
                 + ".")
    elif state.get("pre_ladder"):
        where = "This project predates the growth ladder — a finished body of work, not yet re-poured onto the rungs."
    else:
        where = "This project has not been seeded onto the growth ladder yet."

    # the goal leads — what this paper IS, in the words that authored it (goal-v2 after
    # a supersede; the essence the gauge itself reads). A brief that never states the
    # goal describes furniture (the perfectionist pass's first wince).
    goal_line = ""
    goal_info = (cov[0].get("_goal") if cov else None) or {}
    try:
        from laplace.pipeline import demand as _demand
        gv = _demand.coverage_vector(repo_root, corpus).get("goal", {})
        essences = [e for e in (gv.get("essences") or []) if e]
        if essences:
            goal_line = f"The goal: {essences[0].rstrip('.')}. "
    except Exception:  # noqa: BLE001 — a goal that cannot be read is stated by absence below
        pass

    # name the covered axes with their real numbers; zeros stay honest but never bury
    # the numbers that moved.
    covered_axes = [c for c in cov if c.get("covered")]
    if covered_axes:
        parts = ", ".join(f"{c['axis']} covers {c['covered']} of {c['total']}" for c in covered_axes)
        zeros = f"; {' and '.join(zero_axes)} still read zero" if zero_axes else ""
        cov_clause = f"{parts}{zeros}"
    elif len(zero_axes) == 3:
        cov_clause = ("Literature, validation, and figure-demonstration coverage read as "
                      "measured zeros against the current goal")
    elif zero_axes:
        cov_clause = f"{len(zero_axes)} of the three coverage axes read as measured zeros"
    else:
        cov_clause = "no coverage axis is raised on this project yet"
    ask = ""
    if tensions:
        t0 = tensions[0].get("composed") or {}
        ask = " One decision is waiting: " + (t0.get("glance") or
              "a drift the machine cannot rule is open for your ruling.")
    cov_sentence = cov_clause[:1].upper() + cov_clause[1:]
    glance = (f"{goal_line}{where} {cov_sentence}.{ask} Everything else — the queues, the "
              "coverage axes, the open orders — stays a count until you summon it.")
    working = (f"{where} {cov_clause}. There are {len(tensions)} open tension(s), {len(queue)} "
               f"requirement(s) below the floor, and {len(wos)} open work order(s) on this project.")

    block = _composed.make_composed(
        glance=glance, working=working, minted_by="growth_surface.brief",
        substrate_fingerprint=_composed.fingerprint(
            f"{corpus}|{rung}|{len(tensions)}|{len(queue)}|{len(wos)}|{len(zero_axes)}"),
        goal_version=state.get("goal_version"),
        audit={"ids": [corpus], "provenance": ["the growth cockpit brief"], "citations": []})
    brief = _composed.project_altitude({"composed": block}, "glance")
    # the tension station knows, without a chip, whether a ruled tension is bankable
    # history to read (fix 1b) — a boolean, not a count (it opens one read, not N rows).
    try:
        has_reconciled = reconciled_tension(repo_root, corpus) is not None
    except Exception:  # noqa: BLE001 — the station degrades to "none ruled" on a read hiccup
        has_reconciled = False
    return {
        "corpus": corpus,
        "brief": brief,                         # {glance, next}
        "state": state,
        "reconciled": has_reconciled,           # a ruled tension is readable as history
        "counts": {
            "tensions": len(tensions),
            "coverage_axes": len(cov),
            "queue": len(queue),
            "work_orders": len(wos),
            "zero_axes": len(zero_axes),
        },
    }


def empty_brief_payload(repo_root: Path, corpus: str) -> dict:
    """The teaching empty state for a project the growth surface cannot brief — a stated
    absence, never a synthesised body. Fires when the corpus does not resolve to a tex root
    (not indexed) or resolves but is not seeded onto the surface. Names the surface, states
    the worded reason, says what GROW would show, and hands the doors that still work (the
    stock map at minimum). Minted server-side; the client renders it verbatim."""
    from laplace.pipeline import composed as _composed
    from laplace.research import corpus_ingest as _ci

    indexed = _ci.resolve_corpus(repo_root, corpus) is not None
    if not indexed:
        reason_code = "unindexed"
        reason = ("This project is not indexed onto the growth surface — no manuscript tex root "
                  "resolves for it, so there is no substrate to gauge against the goal yet.")
    else:
        reason_code = "unseeded"
        reason = ("This project resolves but is not seeded onto the growth surface — it has no "
                  "plan the cockpit can read its shape from yet.")
    glance = (f"There is no growth brief for {corpus!r}. {reason} A brief needs the manuscript "
              "poured onto the surface first; until then the shape below stays a promise, not a "
              "reading.")
    block = _composed.make_composed(
        glance=glance, working=(reason + " Nothing is measured, so nothing is claimed."),
        minted_by="growth_surface.empty_brief",
        substrate_fingerprint=_composed.fingerprint(f"{corpus}|empty|{reason_code}"),
        audit={"ids": [corpus], "provenance": ["the growth cockpit empty-state teach"], "citations": []})
    brief = _composed.project_altitude({"composed": block}, "glance")
    return {
        "corpus": corpus,
        "brief": brief,
        "empty": True,
        "reason_code": reason_code,
        "reason": reason,
        "would_show": [
            "the SHAPE — the ladder position and the coverage axes measured against the goal",
            "any open tension pinned where it pulls, opening to the four verbs for your ruling",
            "the queue of requirements below the floor, and the open work orders",
        ],
        "doors": [
            {"label": "read the stock — the graded descent", "href": "/conceptric/map?corpus=" + corpus},
        ],
        "state": growth_situation(repo_root, corpus) if indexed else
                 {"present": False, "state": None, "pre_ladder": False},
        "counts": {"tensions": 0, "coverage_axes": 0, "queue": 0, "work_orders": 0, "zero_axes": 0},
    }


# ---------------------------------------------------------------------------
# the verb doors — actor-guarded, one write, false-ruling-refused
# ---------------------------------------------------------------------------

def _find_tension(repo_root: Path, corpus: str, gt_id: str) -> dict | None:
    for row in all_tensions(repo_root, corpus):
        if row.get("id") == gt_id:
            return row
    return None


def _feedback_ledger(repo_root: Path, corpus: str):
    from laplace.pipeline import demand
    return demand._corpus_feedback_ledger(repo_root, corpus)


def _rule(repo_root: Path, payload: dict) -> tuple[int, dict]:
    """POST /growth/rule — bank one ruling on one tension. Actor-guarded; the note rides
    the same record; the posted verb+fingerprint must match the served action row."""
    from laplace.manuscript.manuscript_bridge import AUTHOR_ACTORS
    from laplace.pipeline import composed as _composed

    corpus = (payload.get("corpus") or _default_corpus()).strip()
    gt_id = (payload.get("gt_id") or payload.get("id") or "").strip()
    verb = (payload.get("verb") or "").strip()
    posted_fp = (payload.get("fingerprint") or "").strip()
    by = (payload.get("by") or "").strip()
    note = (payload.get("note") or "").strip()

    if not gt_id or not verb:
        return 400, {"ok": False, "error": "gt_id and verb are required"}
    # actor guard — every verb on a goal tension is his ruling (author jurisdiction).
    if not by:
        return 422, {"ok": False, "error": "by required — a ruling is actor-attributed and this door defaults nowhere"}
    if by.strip().lower() not in AUTHOR_ACTORS:
        return 403, {"ok": False, "error": f"{by!r} is not an author actor — this ruling is his to make"}

    row = _find_tension(repo_root, corpus, gt_id)
    if row is None:
        return 404, {"ok": False, "error": f"no open tension {gt_id!r} on {corpus!r} — it may be already ruled or dismissed"}
    decision = (row.get("composed") or {}).get("decision") or {}
    action = next((a for a in decision.get("actions", []) if a.get("verb") == verb), None)
    if action is None:
        return 400, {"ok": False, "error": f"verb {verb!r} is not an action on this tension"}
    # the false-ruling refusal: recompute the seat and refuse a stale/mismatched pair.
    server_fp = _composed.action_fingerprint(action.get("verb", ""), action.get("consequence", ""))
    if not posted_fp:
        return 422, {"ok": False, "error": "no consequence fingerprint rode the ruling — the door only "
                     "banks a choice made against the served consequence; reload the tension and rule "
                     "from the surface", "server_fingerprint": server_fp}
    if posted_fp != server_fp:
        return 409, {"ok": False, "error": "the posted consequence no longer matches the served ruling — "
                     "the surface is stale; reload the tension before banking", "server_fingerprint": server_fp}

    goal_node = row.get("node_id") or "goal"
    if verb == "REALIGN/RESPINE":
        return _do_realign(repo_root, corpus, goal_node, action, note, by)
    if verb == "REGOAL":
        return _do_regoal(repo_root, corpus, goal_node, action, note, by, payload)
    if verb == "HOLD/WAIVE":
        return _do_hold(repo_root, corpus, goal_node, action, note, by)
    if verb == "DISMISS SIGNAL":
        return _do_dismiss(repo_root, corpus, gt_id, row, action, note, by)
    return 400, {"ok": False, "error": f"unknown verb {verb!r}"}


def _bank_feedback(repo_root: Path, corpus: str, goal_node: str, kind: str,
                   comment: str, action: dict, by: str) -> dict | None:
    from laplace.manuscript import manuscript_bridge as _mb
    led = _feedback_ledger(repo_root, corpus)
    if led is None:
        return None
    payload = {
        "node_id": goal_node, "comment": comment, "kind": kind, "by": by,
        "anchor": {"verb": action.get("verb"), "consequence": action.get("consequence"),
                   "resolves": action.get("resolves")},
    }
    return _mb.feedback_add(repo_root, corpus, payload, ledger=led)


def _do_realign(repo_root, corpus, goal_node, action, note, by):
    comment = note or ("Realign the manuscript to lead on the method — " + action.get("consequence", ""))
    res = _bank_feedback(repo_root, corpus, goal_node, "goal-realign", comment, action, by)
    if res is None:
        return 404, {"ok": False, "error": f"corpus {corpus!r} has no manuscript feedback ledger to bank against"}
    if res.get("error"):
        return 400, {"ok": False, "error": res["error"]}
    return 200, {"ok": True, "verb": "REALIGN/RESPINE", "banked": res.get("record"),
                 "consequence": action.get("consequence")}


def _do_hold(repo_root, corpus, goal_node, action, note, by):
    comment = note or ("Hold: the mismatch between the banked goal and the stated intent is tolerated — "
                       + (action.get("resolves") or ""))
    res = _bank_feedback(repo_root, corpus, goal_node, "goal-tolerance", comment, action, by)
    if res is None:
        return 404, {"ok": False, "error": f"corpus {corpus!r} has no manuscript feedback ledger to bank against"}
    if res.get("error"):
        return 400, {"ok": False, "error": res["error"]}
    return 200, {"ok": True, "verb": "HOLD/WAIVE", "banked": res.get("record"),
                 "consequence": action.get("consequence")}


def _do_dismiss(repo_root, corpus, gt_id, row, action, note, by):
    from laplace.pipeline import demand
    from laplace.pipeline import suppress as _suppress
    led = _feedback_ledger(repo_root, corpus)
    if led is None:
        return 404, {"ok": False, "error": f"corpus {corpus!r} has no ledger to bank a suppression against"}
    block = row.get("composed") or {}
    node_text = (block.get("glance") or "") + (block.get("working") or "")
    rec = _suppress.make_suppression(
        gt_id, demand.AUTHOR_GOAL_KIND, node_text,
        reason=(note or "the detector is wrong for this project's intended goal"),
        actor=by, round=0, project=corpus)
    _suppress.append_suppression(led, rec)
    return 200, {"ok": True, "verb": "DISMISS SIGNAL", "banked": rec,
                 "consequence": action.get("consequence")}


def _do_regoal(repo_root, corpus, goal_node, action, note, by, payload):
    from laplace.research import corpus_ingest as _ci
    confirmed = (payload.get("confirmed_goal_text") or "").strip()
    if not confirmed:
        return 422, {"ok": False, "error": "REGOAL requires the confirmed goal text — nothing supersedes a "
                     "goal string you have not confirmed (the confirm gate)"}
    # growth.regoal is reserved for a laddered project; today none is laddered, so this
    # door rides the supersede path and says so in the response.
    state = growth_situation(repo_root, corpus)
    laddered = bool(state.get("present"))
    import datetime as _dt
    new_id = "goal:v" + str((state.get("goal_version") or 1) + 1) + ":" + _dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    rw = _ci.rewire_add(repo_root, corpus, {
        "kind": "add-node", "node": new_id, "node_kind": "goal",
        "essence": confirmed, "supersedes": goal_node,
        "narrative": (note or "regoal: the goal is superseded by his confirmed restatement"),
        "by": by,
    })
    if rw.get("error"):
        return 400, {"ok": False, "error": rw["error"]}
    return 200, {"ok": True, "verb": "REGOAL", "banked": rw.get("record"),
                 "superseded": goal_node, "new_goal": new_id, "laddered": laddered,
                 "note": ("the goal is superseded through the rewire ledger; growth.regoal "
                          "(the ladder reopen) applies only once this project is on the ladder"),
                 "consequence": action.get("consequence")}


# ---------------------------------------------------------------------------
# the axis-gap door — dual-piloting (machine or him), false-ruling-refused
# ---------------------------------------------------------------------------

def _route_gap(repo_root: Path, payload: dict) -> tuple[int, dict]:
    """POST /growth/route-gap — route a coverage-axis gap to a banked work order. A
    dual-piloting door (machine or him): ``by`` must be present but need not be an author
    actor, so a worker session and he ride the same door. The posted consequence
    fingerprint must match the served coverage row's routing action (the false-ruling
    refusal — the selection and the displayed consequence cannot disagree); an unknown or
    covered axis refuses in plain words. Delegates the bank to
    :func:`storyboard.route_axis_gap`; the response carries the banked order and its
    composed glance."""
    from laplace.pipeline import composed as _composed
    from laplace.manuscript import storyboard as _sb

    corpus = (payload.get("corpus") or _default_corpus()).strip()
    axis = (payload.get("axis") or "").strip()
    by = (payload.get("by") or "").strip()
    note = (payload.get("note") or "").strip()
    posted_fp = (payload.get("fingerprint") or "").strip()
    node_ids = payload.get("node_ids") or []
    if isinstance(node_ids, str):
        node_ids = [node_ids]

    # actor guard — a routing is attributed (machine or author); this door defaults nowhere.
    if not by:
        return 422, {"ok": False, "error": "by required — a routing is actor-attributed "
                     "(a worker or the author) and this door defaults nowhere"}
    if not axis:
        return 400, {"ok": False, "error": "axis is required"}

    try:
        rows = coverage_rows(repo_root, corpus)
    except Exception:  # noqa: BLE001
        return 404, {"ok": False, "error": f"no coverage vector for corpus {corpus!r}"}
    row = next((r for r in rows if r.get("axis") == axis), None)
    if row is None:
        return 400, {"ok": False, "error": f"unknown axis {axis!r} — the routable axes are "
                     "literature, validation, and demonstration"}
    decision = (row.get("composed") or {}).get("decision") or {}
    action = next(iter(decision.get("actions") or []), None)
    if action is None:
        return 409, {"ok": False, "error": f"the {axis} axis has no gap to route — it is "
                     "covered or a real zero, so nothing is banked"}
    # the false-ruling refusal: recompute the seat and refuse a stale/mismatched/empty pair.
    server_fp = _composed.action_fingerprint(action.get("verb", ""), action.get("consequence", ""))
    if not posted_fp:
        return 422, {"ok": False, "error": "no consequence fingerprint rode the request — the "
                     "door only banks a choice made against the served consequence; reload the "
                     "coverage axis and route from the surface", "server_fingerprint": server_fp}
    if posted_fp != server_fp:
        return 409, {"ok": False, "error": "the posted consequence no longer matches the served "
                     "routing — the surface is stale; reload the coverage axis before routing",
                     "server_fingerprint": server_fp}
    return _sb.route_axis_gap(corpus, axis, node_ids, requested_by=by, note=note,
                              root=repo_root)


# ---------------------------------------------------------------------------
# the contract route — one authored source, rendered by the surface
# ---------------------------------------------------------------------------

def surface_contract(surface: str) -> dict | None:
    """The authored yaml blocks for a surface as JSON (states / queues / verbs /
    structural / counts) — the conjugate-views source the cockpit renders its ladder
    strip, queue headers, and verb roster from. Allowlisted to an existing yaml file, so
    a traversal name never reaches the filesystem."""
    import re
    if not surface or not re.fullmatch(r"[a-z0-9_-]+", surface):
        return None
    p = (_repo_root() / "contract" / "surfaces" / f"{surface}.yaml").resolve()
    base = (_repo_root() / "contract" / "surfaces").resolve()
    try:
        p.relative_to(base)
    except ValueError:
        return None
    if not p.is_file():
        return None
    import yaml
    doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return {k: doc.get(k) for k in _CONTRACT_KEYS if doc.get(k) is not None}


# ---------------------------------------------------------------------------
# routing
# ---------------------------------------------------------------------------

def handle(path: str, query: dict, method: str, body: bytes) -> tuple[int, str, bytes] | None:
    """Route one ``/growth/*`` or ``/surface/contract`` request. Returns (status,
    content_type, body) or None when the path is not ours (the scanner falls through)."""
    if not (path == "/surface/contract" or path == "/growth" or path.startswith("/growth/")):
        return None
    method = (method or "GET").upper()
    rr = _repo_root()

    if path == "/surface/contract":
        out = surface_contract(_q1(query, "surface"))
        if out is None:
            return _json_resp(404, {"error": "unknown surface contract"})
        return _json_resp(200, out)

    if method == "POST":
        if path == "/growth/rule":
            try:
                payload = json.loads(body or b"{}")
            except ValueError:
                return _json_resp(400, {"ok": False, "error": "bad json"})
            status, obj = _rule(rr, payload)
            return _json_resp(status, obj)
        if path == "/growth/route-gap":
            try:
                payload = json.loads(body or b"{}")
            except ValueError:
                return _json_resp(400, {"ok": False, "error": "bad json"})
            status, obj = _route_gap(rr, payload)
            return _json_resp(status, obj)
        return _json_resp(405, {"ok": False, "error": "method not allowed"})

    corpus = _q1(query, "corpus") or _default_corpus()
    from laplace.research import corpus_ingest as _ci
    if _ci.resolve_corpus(rr, corpus) is None:
        # the brief TEACHES on an unbriefable project (fix 5) — an honest empty state,
        # never a bare 404; every other door still 404s (nothing to read there).
        if path == "/growth/brief":
            return _json_resp(200, empty_brief_payload(rr, corpus))
        return _json_resp(404, {"error": f"unknown corpus {corpus!r}"})

    if path == "/growth/brief":
        return _json_resp(200, brief_payload(rr, corpus))
    if path == "/growth/reconciled":
        rec = reconciled_tension(rr, corpus)
        gt = _q1(query, "gt")
        matched = bool(rec and (not gt or rec.get("id") == gt))
        return _json_resp(200, {"corpus": corpus, "reconciled": rec if matched else None,
                                "miss_note": _tension_miss_note(corpus, gt)})
    if path == "/growth/tensions":
        rows = all_tensions(rr, corpus)
        return _json_resp(200, {"corpus": corpus, "tensions": rows, "count": len(rows)})
    if path == "/growth/queue":
        rows = red_queue(rr, corpus)
        return _json_resp(200, {"corpus": corpus, "rows": rows, "count": len(rows)})
    if path == "/growth/coverage":
        rows = coverage_rows(rr, corpus)
        return _json_resp(200, {"corpus": corpus, "axes": rows, "count": len(rows)})
    if path == "/growth/state":
        return _json_resp(200, {"corpus": corpus, "state": growth_situation(rr, corpus)})
    if path == "/growth/work-orders":
        rows = open_work_order_rows(rr, corpus)
        return _json_resp(200, {"corpus": corpus, "orders": rows, "count": len(rows)})
    return _json_resp(404, {"error": "not found"})
