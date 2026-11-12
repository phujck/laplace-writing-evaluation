"""Adjudication records — the author's ear made executable (G-3).

The verbs that RULE on a finding, each ONE append-only record on the SAME
``feedback.jsonl`` the intake/review/suppression records ride (the one door). A
verb is idempotent and revocable: re-issuing it is a no-op, and every ruling is
a node in the ledger the route and the evolution machinery later consume.

The division of labour with :mod:`suppress`:

  * DISMISS / WIDEN / REVOKE are suppression semantics (a fingerprinted
    non-fault, the wildcard silence, the superseding revoke) and live in
    ``suppress`` — they gate the fixer's spend.
  * CONFIRM / DEFER / route-to-conceptric / CALIBRATE live here — they steer
    dispatch (confirm EXEMPTS a finding from class-grain deferral, defer
    WITHHOLDS it) or QUEUE a typed, evolution-adjacent intent for the
    substrate/dreamer without executing anything.

Every record carries a top-level ``record`` discriminator (so the route and the
review surface can tell an ACTION from a finding — the exact reason the route's
findings filter and the review surface both exclude :data:`ADJ_RECORD_KINDS`), a
``target`` (the finding id it rules on, except the kind-level calibration
intent), and a ``provenance`` ``{actor, verdict, round, ts}`` block mirroring the
suppression provenance shape. The conceptric/calibration intents are
EVOLUTION-ADJACENT in shape — node/kind-anchored, a typed ``intent``/``payload``,
``status: "open"`` (queued, never executed) — so the evolution machinery can
consume them later. Nothing here runs an evolution; it deposits, correctly shaped.
"""
from __future__ import annotations

import datetime as _dt
from typing import Iterable

# ---------------------------------------------------------------------------
# record discriminators (the top-level ``record`` field on the shared ledger)
# ---------------------------------------------------------------------------

CONFIRM = "confirmation"
DEFER = "defer"
CONCEPTRIC_INTENT = "conceptric-intent"
#: the PLAN-altitude sibling of the conceptric intent (2026-07-13). Where
#: :data:`CONCEPTRIC_INTENT` types a NODE-fault to the substrate, a
#: ``projection-intent`` types a WHOLE-ARTEFACT / plan-altitude finding to the
#: PLAN — the altitude that owns a CUT / DEMOTE / SPLIT / … of a meta key or a
#: whole section. Same evolution-adjacent shape (a typed ``verb`` + ``object``,
#: ``status: "open"``, queued never executed); the evolution consumer drafts a
#: PLAN PROPOSAL from it, and the draft-only law holds — nothing auto-applies.
PROJECTION_INTENT = "projection-intent"
CALIBRATION_INTENT = "calibration-intent"
#: the substrate-queue revoke (G-4): supersedes an open conceptric/calibration
#: intent. ``live`` already honours ``supersedes``, so appending one retires the
#: queued deposit — the append-only mirror of the suppression revoke.
INTENT_REVOKE = "intent-revoke"
#: retire a FINDING itself (not an intent): a superseding resolution record. Two
#: uses, both append-only corrections of a mis-poured ledger: SUPERSEDE a legacy
#: id-less finding that an anchored re-pour replaces, and ROLL BACK the panel
#: records of a challenger round the dominance guard REJECTED (they describe bytes
#: that never shipped). ``live``/intake honour ``supersedes``, so appending one
#: retires its target; ``status: "resolved"`` keeps the resolution record itself
#: off every worklist.
RESOLUTION = "resolution"
#: the APPLIED-op record of the projection-intent apply bridge (C3.5, Fork 8:
#: ``PV-20260713T221204Z-weld-apply-bridge``). When the evolution consumer
#: DERIVES a projection-intent into a storyboard plan op and applies it through
#: the plan-ledger door, it banks one of these carrying the ACTUAL plan delta
#: (``before``/``after`` of the touched meta key or section nodes) beside the
#: :data:`INTENT_REVOKE` that retires the consumed intent. An un-derivable op
#: banks one too, with ``outcome: "needs-author"`` and no delta — the intent
#: stays open. Both are ACTIONS (never findings), ``status: "resolved"``.
RATIFIED_OPERATION = "ratified-operation"
#: THE SELECTION RULING (P3, the selection desk's door): the author's word on ONE
#: heredity generation — promote / hold / retire. Record-only: it banks his verdict
#: against a generation id (with the draft it did-or-did-not override, the rule
#: version it was judged under, and a readings digest), and mutates NO artifact. An
#: ACTION (never a finding); ``status: "resolved"`` keeps it off every worklist, and
#: a later ruling on the same generation CONTESTS it (append-only correction).
SELECTION_RULING = "selection-ruling"
#: THE SCOPE-LATER DOOR (the redline walk, 2026-08-10): the author's altitude on a
#: row he already banked UNSCOPED. Scope is optional at capture and required
#: downstream, so the deposit loop's cheapest gesture — select, Enter, no digit —
#: has to stay first-class AND reachable afterwards. This is that reach: an APPEND
#: naming the target row and the altitude, never an in-place relabel of the banked
#: line. The latest scoping record for a target wins (the review surface folds them
#: over the row when it reads the ledger), so a re-scope is itself append-only.
#: An ACTION (never a finding); ``status: "resolved"`` keeps it off every worklist.
SCOPING = "scoping"

#: every record type that is an ACTION on findings, never itself a finding. The
#: route (fixedpoint_route) and the review surface exclude these from the
#: findings they route/display (a confirmation whose ``kind`` mirrors the
#: finding's own kind would otherwise be double-counted as a finding).
ADJ_RECORD_KINDS = frozenset({CONFIRM, DEFER, CONCEPTRIC_INTENT,
                              PROJECTION_INTENT, CALIBRATION_INTENT,
                              INTENT_REVOKE, RESOLUTION, RATIFIED_OPERATION,
                              SELECTION_RULING, SCOPING})

#: the conceptric-intent categories (the human-facing substrate-fault taxonomy;
#: the evolution machinery maps each to a rewire kind when it is later consumed).
CONCEPTRIC_INTENTS = ("essence-wrong", "edge-missing", "content-missing",
                      "grade-wrong", "other")

#: the projection-intent verbs (the plan-altitude op vocabulary; the evolution
#: consumer drafts each as a PROPOSED plan op — a set-meta / section change — the
#: author ratifies before any storyboard op is written). CUT retires, DEMOTE
#: lowers prominence, SPLIT divides, REORDER re-sequences, REOPEN un-retires,
#: RESPINE re-anchors the apex chain, RESTART re-plans from the conceptric.
PROJECTION_VERBS = ("CUT", "DEMOTE", "SPLIT", "REORDER", "REOPEN",
                    "RESPINE", "RESTART")


# ---------------------------------------------------------------------------
# small shared shape helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def _rid(prefix: str) -> str:
    return _dt.datetime.now().strftime(f"{prefix}-%Y%m%d-%H%M%S-%f")


def _prov(actor: str, verdict: str, round: int, ts: str) -> dict:
    return {"actor": actor, "verdict": verdict, "round": round, "ts": ts}


# ---------------------------------------------------------------------------
# the record builders (each not-yet-written; the surface appends via the one door)
# ---------------------------------------------------------------------------

def make_confirmation(finding_id: str, *, node_id: str = "", kind: str = "",
                      section: str = "", actor: str = "author", round: int = 0,
                      project: str = "", rec_id: str | None = None,
                      ts: str | None = None) -> dict:
    """A CONFIRM ruling: the finding is real. Status stays ``open`` (it is still
    work to dispatch), but a confirmed finding gets dispatch priority and is
    EXEMPT from class-grain deferral — the route reads :func:`confirmed_ids` so a
    confirmed ``eq-unused`` rides through even though its class is deferred."""
    now = ts or _now()
    return {
        "id": rec_id or _rid("CONF"),
        "record": CONFIRM,
        "project": project,
        "ts": now,
        "target": finding_id,
        "node_id": node_id,
        "kind": kind,
        "section": section,
        "status": "open",              # a confirmed finding is still open work
        "source": actor,
        "text": f"confirmed finding {finding_id!r}",
        "provenance": _prov(actor, "confirmed", round, now),
    }


def make_defer(finding_id: str, *, node_id: str = "", kind: str = "",
               section: str = "", note: str = "", actor: str = "author",
               round: int = 0, project: str = "", rec_id: str | None = None,
               ts: str | None = None) -> dict:
    """A DEFER ruling: valid, but not this convergence run. Status ``deferred``;
    the route treats a per-instance defer like a class defer — reported, never
    dispatched (:func:`deferred_ids`)."""
    now = ts or _now()
    return {
        "id": rec_id or _rid("DEF"),
        "record": DEFER,
        "project": project,
        "ts": now,
        "target": finding_id,
        "node_id": node_id,
        "kind": kind,
        "section": section,
        "status": "deferred",
        "source": actor,
        "text": f"deferred finding {finding_id!r}" + (f": {note}" if note else ""),
        "provenance": _prov(actor, "deferred", round, now),
    }


def make_conceptric_intent(node_id: str, intent: str, *, note: str = "",
                           finding_id: str = "", kind: str = "", section: str = "",
                           actor: str = "author", round: int = 0, project: str = "",
                           rec_id: str | None = None, ts: str | None = None) -> dict:
    """A route-to-conceptric deposit: the finding's true home is the SUBSTRATE
    ('this essence is wrong', 'a missing edge', 'absent content'). A TYPED,
    node-anchored intent — evolution-adjacent in shape (``node`` keyed like a
    rewire record, a typed ``intent`` + ``payload``, ``status: "open"``) — that
    QUEUES for the evolution machinery. It executes NOTHING; ``intent`` outside
    :data:`CONCEPTRIC_INTENTS` is normalised to ``"other"``."""
    now = ts or _now()
    if intent not in CONCEPTRIC_INTENTS:
        intent = "other"
    return {
        "id": rec_id or _rid("CI"),
        "record": CONCEPTRIC_INTENT,
        "project": project,
        "ts": now,
        "target": finding_id,
        "node": node_id,               # evolution-adjacent: rewire records key on ``node``
        "node_id": node_id,            # + the feedback-ledger field convention
        "kind": CONCEPTRIC_INTENT,
        "section": section,
        "intent": intent,
        "payload": {"intent": intent, "note": note, "finding_kind": kind},
        "status": "open",              # queued, never executed
        "source": actor,
        "text": f"route to conceptric ({intent}) on {node_id!r}"
                + (f": {note}" if note else ""),
        "provenance": _prov(actor, "route-to-conceptric", round, now),
    }


def make_projection_intent(finding_id: str, verb: str, *, object_kind: str = "meta",
                           object_key: str = "", note: str = "", finding_kind: str = "",
                           section: str = "", actor: str = "author", round: int = 0,
                           project: str = "", rec_id: str | None = None,
                           ts: str | None = None) -> dict:
    """A route-to-plan deposit: the finding's true home is the PLAN, not a node —
    a whole-artefact/plan-altitude correction the plan altitude owns (CUT a meta
    key, DEMOTE a section, SPLIT/REORDER/…). A TYPED, plan-anchored intent —
    evolution-adjacent in shape (a typed ``verb`` + ``object``, ``status:
    "open"``) — that QUEUES for the evolution consumer. It executes NOTHING; the
    consumer DRAFTS a plan proposal and the author ratifies (the draft-only law).

    ``verb`` outside :data:`PROJECTION_VERBS` is normalised to ``"CUT"`` (the
    safest default: propose a retirement, never a silent restructure).
    ``object`` names WHAT the verb acts on: a ``meta`` key (``object_key`` is a
    ``plan.meta`` field) or a ``section`` (``object_key`` is the section id, also
    mirrored to ``sid``)."""
    now = ts or _now()
    if verb not in PROJECTION_VERBS:
        verb = "CUT"
    if object_kind not in ("meta", "section"):
        object_kind = "meta"
    obj: dict = {"kind": object_kind}
    if object_kind == "section":
        obj["sid"] = object_key
    else:
        obj["key"] = object_key
    obj_desc = obj.get("sid") or obj.get("key") or ""
    return {
        "id": rec_id or _rid("PI"),
        "record": PROJECTION_INTENT,
        "project": project,
        "ts": now,
        "target": finding_id,          # the plan-altitude finding it rules on
        "scope": "plan",               # the altitude that owns the correction
        "kind": PROJECTION_INTENT,     # KIND_TO_WORK routes this to None (verdict-only)
        "section": section,
        "verb": verb,
        "object": obj,
        "payload": {"note": note, "finding_kind": finding_kind},
        "status": "open",              # queued, never executed
        "source": actor,
        "text": f"route to plan ({verb} {object_kind}:{obj_desc})"
                + (f": {note}" if note else ""),
        "provenance": _prov(actor, "route-to-plan", round, now),
    }


def make_calibration_intent(finding_kind: str, *, dismissal_count: int = 0,
                            note: str = "", actor: str = "author", round: int = 0,
                            project: str = "", rec_id: str | None = None,
                            ts: str | None = None) -> dict:
    """the meta-signal deposit: N dismissals of a KIND is evidence the CHECK, not
    each instance, is miscalibrated. A kind-level (NOT node-level) intent that
    queues 'recalibrate the check?' for the dreamer/next session. No
    auto-recalibration — author-gated evidence only."""
    now = ts or _now()
    return {
        "id": rec_id or _rid("CAL"),
        "record": CALIBRATION_INTENT,
        "project": project,
        "ts": now,
        "kind": CALIBRATION_INTENT,
        "finding_kind": finding_kind,
        "payload": {"finding_kind": finding_kind,
                    "dismissal_count": dismissal_count, "note": note},
        "status": "open",              # queued, never executed
        "source": actor,
        "text": f"recalibrate check {finding_kind!r} ({dismissal_count} dismissals)"
                + (f": {note}" if note else ""),
        "provenance": _prov(actor, "recalibrate-check", round, now),
    }


def make_intent_revocation(intent_id: str, *, reason: str = "", actor: str = "author",
                           round: int = 0, project: str = "", rec_id: str | None = None,
                           ts: str | None = None) -> dict:
    """A REVOKE superseding an open substrate-queue intent (a conceptric- or
    calibration-intent). :func:`live` drops any record named by a later
    ``supersedes``, so appending this retires ``intent_id`` from the queue on the
    next read — the append-only mirror of :func:`suppress.make_revocation`, and
    itself an :data:`ADJ_RECORD_KINDS` action so it never reads back as a finding.
    ``status: "resolved"`` so the intake/propagate spent-record path skips it."""
    now = ts or _now()
    return {
        "id": rec_id or _rid("IREV"),
        "record": INTENT_REVOKE,
        "project": project,
        "ts": now,
        "supersedes": intent_id,
        "status": "resolved",
        "source": actor,
        "text": f"revoked substrate intent {intent_id!r}" + (f": {reason}" if reason else ""),
        "provenance": _prov(actor, "revoke-intent", round, now),
    }


def make_ratified_operation(intent_id: str, *, outcome: str = "applied",
                            verb: str = "", object_kind: str = "",
                            object_key: str = "", op_kind: str = "",
                            before: object = None, after: object = None,
                            reason: str = "", corpus: str = "",
                            actor: str = "author", round: int = 0,
                            project: str = "", rec_id: str | None = None,
                            ts: str | None = None) -> dict:
    """The APPLIED-op record of the projection-intent apply bridge (C3.5, Fork 8
    ruled: ``PV-20260713T221204Z-weld-apply-bridge`` — auto-derive-and-apply with
    retrospective ledger correction, the 2026-07-12 fork-law amendment governing
    over the in-code draft-only law for the projection-intent path only).

    ``outcome="applied"``: ``intent_id`` was derived into ``op_kind`` and applied
    through the storyboard plan-ledger door; ``before``/``after`` carry the ACTUAL
    plan delta (the touched ``plan.meta`` key or section nodes). This record is
    banked BESIDE a :func:`make_intent_revocation` that retires the consumed
    intent, so the author's correction is retrospective THROUGH the ledger (contest
    this record → flip to the alt), never a prospective per-item queue.

    ``outcome="needs-author"``: the op was un-derivable (unresolved object, a verb
    with no mechanical transform, or a section op needing content judgment);
    NOTHING was applied and the intent stays open. ``reason`` names why.

    An :data:`ADJ_RECORD_KINDS` action (never a finding); ``status: "resolved"`` so
    it stays off every worklist."""
    now = ts or _now()
    applied = outcome == "applied"
    obj_desc = f"{object_kind}:{object_key}" if object_kind else object_key
    text = (f"applied {verb} {obj_desc} via {op_kind} (ruling {intent_id!r})"
            if applied else
            f"needs-author {verb} {obj_desc}: {reason} (intent {intent_id!r} kept open)")
    return {
        "id": rec_id or _rid("ROP"),
        "record": RATIFIED_OPERATION,
        "project": project,
        "ts": now,
        "target": intent_id,           # the projection-intent this op consumed/refused
        "scope": "plan",
        "outcome": outcome,            # "applied" | "needs-author"
        "verb": verb,
        "object": {"kind": object_kind, "key": object_key},
        "op_kind": op_kind,            # the storyboard op kind executed ("" when refused)
        "corpus": corpus,
        "delta": {"before": before, "after": after} if applied else None,
        "reason": reason,
        "status": "resolved",
        "source": actor,
        "text": text,
        "provenance": _prov(actor, "apply-projection-intent" if applied
                            else "needs-author", round, now),
    }


def make_resolution(target_id: str, *, verb: str = "supersede", reason: str = "",
                    kind: str = "", section: str = "", actor: str = "author",
                    round: int = 0, project: str = "", rec_id: str | None = None,
                    ts: str | None = None) -> dict:
    """Retire the FINDING ``target_id`` by appending a superseding resolution record
    (append-only — history is never rewritten in place). ``live``/``intake_items``
    drop any record named by a later ``supersedes``, so this retires ``target_id`` on
    the next read; ``status: "resolved"`` keeps the resolution record itself off every
    worklist, and its :data:`RESOLUTION` discriminator keeps it out of the findings the
    route and review surface display. ``verb`` names WHY (``supersede`` a legacy id-less
    finding an anchored re-pour replaces; ``rollback`` a rejected challenger round's
    panel record) — banked in the text and provenance so the trace stays plain."""
    now = ts or _now()
    return {
        "id": rec_id or _rid("RES"),
        "record": RESOLUTION,
        "project": project,
        "ts": now,
        "target": target_id,
        "supersedes": target_id,
        "kind": kind,
        "section": section,
        "status": "resolved",
        "source": actor,
        "text": f"{verb} finding {target_id!r}" + (f": {reason}" if reason else ""),
        "provenance": _prov(actor, f"{verb}-finding", round, now),
    }


def make_scoping(finding_id: str, scope: str, *, scope_source: str = "chosen",
                 previous_scope: str = "", suggested_scope: str = "", note: str = "",
                 kind: str = "", section: str = "", actor: str = "author",
                 round: int = 0, project: str = "", rec_id: str | None = None,
                 ts: str | None = None) -> dict:
    """Scope a row that was banked without one — append-only, never a relabel.

    The row keeps the line it was written on; this record names the altitude the
    author has now given it. It carries ``previous_scope`` (the altitude it held
    before, ``""`` for the unscoped case this door exists for) so the correction is
    legible without diffing, and ``suggested_scope`` so a rule's override rate stays
    derivable across the re-scope too.

    It does NOT ``supersede`` the target: the deposit itself still stands and is still
    the live finding. Only its altitude moves, and the reader that cares about altitude
    (:func:`review_surface._feedback_findings`) folds the LATEST scoping record for a
    target over the row when it reads the ledger."""
    now = ts or _now()
    return {
        "id": rec_id or _rid("SCOPE"),
        "record": SCOPING,
        "project": project,
        "ts": now,
        "target": finding_id,
        "scope": scope,
        "scope_source": scope_source,
        "previous_scope": previous_scope,
        "suggested_scope": suggested_scope,
        "kind": kind,
        "section": section,
        "status": "resolved",             # an action on a finding, never a worklist item
        "source": actor,
        "text": (f"scoped finding {finding_id!r} to {scope}"
                 + (f" (it was {previous_scope})" if previous_scope else " (it was unscoped)")
                 + (f": {note}" if note else "")),
        "provenance": _prov(actor, "scoped", round, now),
    }


def make_selection_ruling(generation_id: str, *, verdict: str, draft_verdict: str,
                          overrode_draft: bool, rule_version: str,
                          readings_digest: dict, reason: str = "", actor: str,
                          project: str, round: int = 0, rec_id: str | None = None,
                          ts: str | None = None) -> dict:
    """the selection ruling (P3): the author's word on ONE heredity generation —
    ``promote`` / ``hold`` / ``retire``. Record-only: it banks his ``verdict``
    against ``generation_id``, WITH the ``draft_verdict`` it did-or-did-not
    override (``overrode_draft`` is computed server-side by the surface — the
    verdict against the live draft), the ``rule_version`` it was judged under, and
    a ``readings_digest`` (the debt before/after, freeze pass, r10-clean of the
    scored generation). It mutates no artifact — a later ruling on the same
    generation CONTESTS this one (append-only correction, the ledger mirror of the
    evolution desk's retrospective doors).

    An :data:`ADJ_RECORD_KINDS` action (never a finding); ``status: "resolved"`` so
    it stays off every worklist."""
    now = ts or _now()
    return {
        "id": rec_id or _rid("SEL"),
        "record": SELECTION_RULING,
        "project": project,
        "ts": now,
        "target": generation_id,          # the generation this ruling rules on
        "generation_id": generation_id,
        "verdict": verdict,               # promote | hold | retire
        "draft_verdict": draft_verdict,
        "overrode_draft": bool(overrode_draft),
        "rule_version": rule_version,
        "readings_digest": readings_digest,
        "reason": reason,
        "status": "resolved",
        "source": actor,
        "text": f"selection ruling {verdict!r} on generation {generation_id!r}"
                + (f" (overrode draft {draft_verdict!r})" if overrode_draft else "")
                + (f": {reason}" if reason else ""),
        "provenance": _prov(actor, verdict, round, now),
    }


# ---------------------------------------------------------------------------
# readers — the route + the surface consume these; a revoke supersedes here too
# ---------------------------------------------------------------------------

def live(records: Iterable[dict]) -> list[dict]:
    """Records not retired by a later ``supersedes`` (the revoke gesture applies
    to adjudication records as it does to suppressions)."""
    recs = [r for r in records if isinstance(r, dict)]
    superseded = {r.get("supersedes") for r in recs if r.get("supersedes")}
    return [r for r in recs if r.get("id") not in superseded]


def confirmed_ids(records: Iterable[dict]) -> set[str]:
    """The finding ids an author CONFIRMED (live confirmations). The route
    exempts these from class-grain AND per-instance deferral."""
    return {str(r.get("target")) for r in live(records)
            if r.get("record") == CONFIRM and r.get("target")}


def deferred_ids(records: Iterable[dict]) -> set[str]:
    """The finding ids DEFERRED per-instance (live defers). The route withholds
    these like a class defer; a confirmation on the same id wins (route rule)."""
    return {str(r.get("target")) for r in live(records)
            if r.get("record") == DEFER and r.get("target")}


def dismissal_counts(records: Iterable[dict]) -> dict[str, int]:
    """Count of ACTIVE (non-revoked) per-kind suppressions by finding-kind — the
    meta-signal's evidence. Wildcard (widen) suppressions are node-level silences,
    not a per-kind dismissal signal, so they are excluded."""
    from laplace.pipeline import suppress as _s
    recs = [r for r in records if isinstance(r, dict)]
    superseded = {r.get("supersedes") for r in recs if r.get("supersedes")}
    counts: dict[str, int] = {}
    for r in recs:
        if not _s.is_suppression(r) or r.get("id") in superseded:
            continue
        k = str(r.get("kind") or "")
        if k and k != _s.WILDCARD:
            counts[k] = counts.get(k, 0) + 1
    return counts


def calibrated_kinds(records: Iterable[dict]) -> set[str]:
    """Finding-kinds that already carry a live calibration-intent (so the surface
    shows 'recalibration queued' rather than re-offering the deposit)."""
    return {str(r.get("finding_kind")) for r in live(records)
            if r.get("record") == CALIBRATION_INTENT and r.get("finding_kind")}
