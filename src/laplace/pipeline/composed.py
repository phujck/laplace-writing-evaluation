"""composed.py — the composition layer's schema, builder, and freshness organ.

Every minted record that will ask for the author's attention carries a ``composed``
block, authored at write time by the writer that held the integration context. This
module is the shared home for that block: the schema validator the mint sites call
before banking, the builder that stamps provenance and the freshness fingerprint, the
staleness check that names which dependency moved, and the altitude projection that
renders an absent block as a stated state rather than a guess.

The block travels stable across altitudes (glance / working / decision / audit); the
renderer selects which field to show. The rules encoded here come from
DESIGN_2026-07-22_the-interface-engine.md sections A and F:

  * per-action ownership (F.1): consequence, writes, confirm, and recommended live
    only on ``decision.actions[]`` rows. A card-level consequence key is refused — the
    selected action and the shown consequence must be unable to disagree.
  * barred vocabulary: raw record ids, source paths, and section anchors are refused
    in glance / working / consequence; they belong under ``audit`` as doors.
  * freshness (F.4): the block carries ``composed_against`` (goal version, substrate
    fingerprint, integrated record ids) and a version, so staleness is detectable and
    recomposition is owned by the minting writer.
  * the fallback law (A.3): a record with no block projects its absence in words and
    drops to the audit floor of raw ids — a glance is never synthesised at read time.

The four minting writers (superego verdicts, work orders, goal-tension rows, demand
audit + coverage rows) call the compose helpers below at their mint sites; there is no
central composer.
"""
from __future__ import annotations

import datetime as _dt
import re
from typing import Any, Optional

from laplace.pipeline.suppress import content_fingerprint as _content_fingerprint

# ---------------------------------------------------------------------------
# the barred-vocabulary fence (glance / working / consequence stay plain)
# ---------------------------------------------------------------------------

#: raw record / ruling ids — provenance that belongs under audit, not the account.
_BARRED_ID = re.compile(r"\b(?:PV|RW|PRM|RM|PRF|SEV|WO|FB)-\d")
#: a source module path rendered in the account.
_BARRED_PATH = re.compile(r"src/laplace/")
#: a raw section anchor rendered as prose.
_BARRED_ANCHOR = re.compile(r"\bsec:s\d+\b")

_ALTITUDES = ("glance", "working", "decision", "audit")
#: keys that may appear only on a ``decision.actions[]`` row (F.1). A card-level or
#: decision-level occurrence is the false-ruling class and is refused.
_ACTION_ONLY_KEYS = ("consequence", "writes", "confirm", "recommended")

_ABSENCE_REASON = ("no composed account — minted before the composition layer, or by a "
                   "writer that predates it")


def _assert_plain(field: str, text: str) -> None:
    """Refuse internal vocabulary in an account field. Raw ids, source paths, and
    section anchors are doors and live under audit — a glance / working / consequence
    that carries one is externalising integration back onto the reader."""
    for label, rx in (("a raw record id", _BARRED_ID),
                      ("a source path", _BARRED_PATH),
                      ("a section anchor", _BARRED_ANCHOR)):
        if rx.search(text):
            raise ValueError(
                f"composed.{field} carries {label} — internal vocabulary belongs under "
                f"audit, not the composed account: {text!r}")


# ---------------------------------------------------------------------------
# the fingerprint (reuses suppress's normalise-then-sha256 idiom, not a third fork)
# ---------------------------------------------------------------------------

def fingerprint(text: str) -> str:
    """A short stable content fingerprint over the composed block's dependencies —
    the same sha256-over-normalised-text idiom the suppression ledger uses, so a
    fingerprint banked this call matches next call for unchanged inputs."""
    return _content_fingerprint(text or "")


# ---------------------------------------------------------------------------
# the schema validator
# ---------------------------------------------------------------------------

def _validate_audit(audit: Any) -> None:
    if not isinstance(audit, dict):
        raise ValueError("composed.audit must be a dict {ids, provenance, citations}")
    for key in ("ids", "provenance", "citations"):
        v = audit.get(key)
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            raise ValueError(f"composed.audit.{key} must be a list of strings")


def _validate_composed_against(ca: Any) -> None:
    if not isinstance(ca, dict):
        raise ValueError("composed.composed_against must be a dict")
    gv = ca.get("goal_version")
    if gv is not None and (not isinstance(gv, int) or isinstance(gv, bool)):
        raise ValueError("composed_against.goal_version must be an int or None")
    sf = ca.get("substrate_fingerprint")
    if not isinstance(sf, str) or not sf.strip():
        raise ValueError(
            "composed_against.substrate_fingerprint must be a non-empty fingerprint")
    rids = ca.get("record_ids")
    if not isinstance(rids, list) or not all(isinstance(x, str) for x in rids):
        raise ValueError("composed_against.record_ids must be a list of strings")


def _validate_decision(decision: Any) -> None:
    if not isinstance(decision, dict):
        raise ValueError("composed.decision must be null or a dict")
    for k in _ACTION_ONLY_KEYS:
        if k in decision:
            raise ValueError(
                f"composed.decision.{k} is a decision-level {k} — {k} lives only on the "
                "actions[] rows (entry-contract F.1, the false-ruling class)")
    tension = decision.get("tension")
    if not isinstance(tension, str) or not tension.strip():
        raise ValueError(
            "composed.decision.tension must be a non-empty account of the disagreement")
    actions = decision.get("actions")
    if not isinstance(actions, list) or not actions:
        raise ValueError(
            "composed.decision.actions must be a non-empty list of action rows")
    n_recommended = 0
    for a in actions:
        if not isinstance(a, dict):
            raise ValueError("each action row must be a dict")
        verb = a.get("verb")
        if not isinstance(verb, str) or not verb.strip():
            raise ValueError("each action row must carry a non-empty verb")
        consequence = a.get("consequence")
        if not isinstance(consequence, str) or not consequence.strip():
            raise ValueError(f"action {verb!r} must carry a plain consequence")
        _assert_plain("decision.actions[].consequence", consequence)
        resolves = a.get("resolves")
        if not isinstance(resolves, str) or not resolves.strip():
            raise ValueError(f"action {verb!r} must name the clause it resolves")
        writes = a.get("writes")
        if not isinstance(writes, list) or not all(isinstance(w, str) for w in writes):
            raise ValueError(f"action {verb!r} writes must be a list of organ names")
        rec = a.get("recommended")
        if not isinstance(rec, bool):
            raise ValueError(
                f"action {verb!r} recommended must be a bool — a marked lean, never a "
                "pre-selection")
        if rec:
            n_recommended += 1
        confirm = a.get("confirm")
        if confirm is not None and not isinstance(confirm, str):
            raise ValueError(f"action {verb!r} confirm must be a string gate or None")
    if n_recommended > 1:
        raise ValueError(
            "at most one action may be recommended — the flag marks a lean, it does not "
            "select a default for him")


def validate_composed(block: Any) -> dict:
    """Enforce the composed-block schema, raising ``ValueError`` on any violation.

    The card-level ownership rule (F.1) is checked first: consequence / writes /
    confirm / recommended may not sit at the card or decision level, only on an
    ``actions[]`` row. The barred-vocabulary fence runs on glance / working and every
    action consequence. Returns the block unchanged when clean."""
    if not isinstance(block, dict):
        raise ValueError("composed block must be a dict")

    for k in _ACTION_ONLY_KEYS:
        if k in block:
            raise ValueError(
                f"composed.{k} is a card-level {k} — {k} lives only on decision.actions[] "
                "rows (entry-contract F.1, the false-ruling class the bank door refuses)")

    glance = block.get("glance")
    if not isinstance(glance, str) or not glance.strip():
        raise ValueError("composed.glance must be a non-empty sentence")
    _assert_plain("glance", glance)

    nxt = block.get("next")
    if nxt is not None and not isinstance(nxt, str):
        raise ValueError("composed.next must be a string or None")

    working = block.get("working")
    if not isinstance(working, str) or not working.strip():
        raise ValueError("composed.working must be a non-empty account")
    _assert_plain("working", working)

    decision = block.get("decision")
    if decision is not None:
        _validate_decision(decision)

    _validate_audit(block.get("audit"))

    mb = block.get("minted_by")
    if not isinstance(mb, str) or not mb.strip():
        raise ValueError("composed.minted_by must name the writer that composed the block")
    ma = block.get("minted_at")
    if not isinstance(ma, str) or not ma.strip():
        raise ValueError("composed.minted_at must be an iso8601 timestamp string")
    cv = block.get("composition_version")
    if not isinstance(cv, int) or isinstance(cv, bool) or cv < 1:
        raise ValueError("composed.composition_version must be an int >= 1")

    _validate_composed_against(block.get("composed_against"))
    return block


# ---------------------------------------------------------------------------
# the builder
# ---------------------------------------------------------------------------

def make_composed(*, glance: str, working: str, minted_by: str,
                  substrate_fingerprint: str, next: Optional[str] = None,
                  decision: Optional[dict] = None, audit: Optional[dict] = None,
                  goal_version: Optional[int] = None,
                  record_ids: Optional[list] = None,
                  minted_at: Optional[str] = None,
                  composition_version: int = 1) -> dict:
    """Assemble a composed block, stamp its provenance and freshness fingerprint, and
    validate it before returning. ``substrate_fingerprint`` and ``goal_version`` are
    the dependencies :func:`is_fresh` checks; ``record_ids`` are the integrated inputs.
    Raises ``ValueError`` if the resulting block violates the schema."""
    audit = audit or {}
    audit = {"ids": [str(x) for x in audit.get("ids", [])],
             "provenance": [str(x) for x in audit.get("provenance", [])],
             "citations": [str(x) for x in audit.get("citations", [])]}
    block = {
        "glance": glance,
        "next": next,
        "working": working,
        "decision": decision,
        "audit": audit,
        "minted_by": minted_by,
        "minted_at": minted_at or _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "composition_version": composition_version,
        "composed_against": {
            "goal_version": goal_version,
            "substrate_fingerprint": substrate_fingerprint,
            "record_ids": [str(x) for x in (record_ids or [])],
        },
    }
    validate_composed(block)
    return block


# ---------------------------------------------------------------------------
# freshness + the altitude projection (read side)
# ---------------------------------------------------------------------------

def is_fresh(record: dict, current_fingerprint: str,
             current_goal_version: Optional[int]) -> dict:
    """Whether a record's composed block still matches its dependencies. Returns
    ``{"fresh": bool, "moved": [...]}`` naming which dependency moved — ``substrate``
    when the fingerprint no longer matches, ``goal`` when the goal version changed,
    ``absent`` when the record carries no composed block at all."""
    block = (record or {}).get("composed")
    if not isinstance(block, dict):
        return {"fresh": False, "moved": ["absent"]}
    ca = block.get("composed_against") or {}
    moved: list[str] = []
    if ca.get("substrate_fingerprint") != current_fingerprint:
        moved.append("substrate")
    if ca.get("goal_version") != current_goal_version:
        moved.append("goal")
    return {"fresh": not moved, "moved": moved}


def project_altitude(record: dict, altitude: str) -> dict:
    """Project a record at one altitude (glance / working / decision / audit). A record
    with no composed block returns the explicit absence marker plus the audit floor of
    its raw ids — the fallback law (A.3): a glance is never synthesised at read time."""
    if altitude not in _ALTITUDES:
        raise ValueError(f"altitude must be one of {_ALTITUDES}: {altitude!r}")
    record = record or {}
    block = record.get("composed")
    if not isinstance(block, dict):
        ids: list[str] = []
        for k in ("id", "demand_id", "node_id"):
            v = record.get(k)
            if v:
                ids.append(str(v))
        return {"absent": True, "reason": _ABSENCE_REASON,
                "audit": {"ids": ids, "provenance": [], "citations": []}}
    if altitude == "glance":
        return {"glance": block.get("glance"), "next": block.get("next")}
    if altitude == "working":
        return {"working": block.get("working"), "glance": block.get("glance")}
    if altitude == "decision":
        return {"decision": block.get("decision")}
    return {"audit": block.get("audit")
            or {"ids": [], "provenance": [], "citations": []}}


# ---------------------------------------------------------------------------
# the compose helpers (one per minting writer's record family)
# ---------------------------------------------------------------------------

def compose_work_order(*, wo_id: str, action: str, corpus: str, what: str, why: str,
                       cost_class: str = "model-heavy",
                       minted_by: str = "bank_work_order",
                       ts: Optional[str] = None) -> dict:
    """The composed block for a banked work order. The decision offers the two real
    doors an open order has: run it, or drop it with a reason. Recommendation is left
    unmarked — the order is queued, not urged."""
    corpus_phrase = corpus or "this manuscript"
    action_phrase = str(action).replace("-", " ").strip() or "a run"
    glance = (f"A {action_phrase} run is queued for {corpus_phrase} but has not started; it is "
              "banked as a request so a later session can carry it, and it is waiting on a "
              "go-ahead.")
    working = (f"{str(what).strip().rstrip('.')}. {str(why).strip().rstrip('.')}. Nothing runs "
               "until the order is picked up — the banked request is the whole act so far.")
    decision = {
        "tension": f"The {action_phrase} run is worth its cost only if it is still wanted now.",
        "actions": [
            {"verb": "run",
             "consequence": ("The run is carried out and its result is stored against "
                             f"{corpus_phrase}; the order is marked done."),
             "resolves": "whether the queued run should proceed",
             "writes": ["storyboard.resolve_work_order (evidence-backed)",
                        "the corpus store the run appends"],
             "recommended": False, "confirm": None},
            {"verb": "drop",
             "consequence": ("The order is set aside with a stated reason and nothing runs; the "
                             "manuscript is left as it stands."),
             "resolves": "whether the queued run should proceed",
             "writes": ["storyboard.resolve_work_order (the resolution row)"],
             "recommended": False, "confirm": None},
        ],
    }
    audit = {"ids": [str(wo_id)], "provenance": [f"banked by {minted_by}"], "citations": []}
    sfp = fingerprint(f"{action}|{corpus}|{what}|{why}")
    return make_composed(glance=glance, working=working, decision=decision, audit=audit,
                         minted_by=minted_by, substrate_fingerprint=sfp, goal_version=None,
                         record_ids=[str(wo_id)], minted_at=ts)


#: the plain word for a demoted epistemic status (internal enum kept out of the account).
_STATUS_WORD = {"conjectured": "provisional", "exploratory": "exploratory"}


def _reconstruct_goal(goal_essences: Optional[list], status_word: str) -> str:
    """The provisional goal string REGOAL shows before any supersede — marked as
    reconstructed so it is confirmed or corrected, never minted as authored text."""
    marker = "Reconstructed goal (confirm or correct this before it is saved): "
    essences = [str(e).strip() for e in (goal_essences or []) if e and str(e).strip()]
    if essences:
        return marker + " ".join(essences)
    return (marker + "the paper's primary contribution is the claim currently presented as "
            + status_word + ".")


def compose_tension(*, node_id: str, signature: str, status: str,
                    goal_version: Optional[int] = None,
                    goal_essences: Optional[list] = None,
                    minted_by: str = "goal_tensions") -> tuple[str, dict]:
    """Compose a goal-tension row: the composed conflict, and the four tension verbs
    (REALIGN/RESPINE, REGOAL, HOLD/WAIVE, DISMISS SIGNAL), each owning its own
    consequence and organ. Returns ``(gt_id, block)``; the id is stable across
    recomputations so a ruling or suppression can address the same detection."""
    status_word = _STATUS_WORD.get(status, status or "provisional")
    gt_id = "GT-" + fingerprint(f"{node_id}|{signature}|{goal_version}")
    glance = (f"The manuscript still presents a headline claim as {status_word}, while the goal "
              "names it a primary contribution — a reader will not take it as the main result. "
              "A ruling is asked: realign the manuscript, change the goal, tolerate the gap, or "
              "dismiss the signal.")
    working = ("The goal ranks this claim among the paper's primary contributions, but the "
               f"manuscript still carries it as {status_word}. The goal and the manuscript "
               "disagree about how central the claim is; they cannot both stand as they are.")
    decision = {
        "tension": (f"The goal treats this claim as a primary contribution; the manuscript still "
                    f"presents it as {status_word}."),
        "actions": [
            {"verb": "REALIGN/RESPINE",
             "consequence": ("The manuscript is restructured so the claim reads as a primary "
                             "result; the goal stands unchanged; the stored record notes the ruling."),
             "resolves": "the manuscript presents the claim below the rank the goal gives it",
             "writes": ["the projection plan (meta.contribution_rank)"],
             "recommended": False, "confirm": None},
            {"verb": "REGOAL",
             "consequence": ("The goal is changed so the claim's current standing becomes what the "
                             "paper promises; the manuscript is left as written; the earlier goal "
                             "is superseded."),
             "resolves": "the goal asks for more than the manuscript delivers",
             "writes": ["growth.regoal", "the goal supersede through the rewire ledger"],
             "recommended": False,
             "confirm": _reconstruct_goal(goal_essences, status_word)},
            {"verb": "HOLD/WAIVE",
             "consequence": ("The mismatch is recorded as knowingly tolerated; neither the "
                             "manuscript nor the goal changes; the named gap stays on the record."),
             "resolves": "whether the gap must be closed at all",
             "writes": ["the READY waiver record (author-gated)"],
             "recommended": False, "confirm": None},
            {"verb": "DISMISS SIGNAL",
             "consequence": ("The detection is marked wrong and set aside; it stays dismissed "
                             "until its inputs change; nothing in the manuscript or goal moves."),
             "resolves": "whether the tension is real at all",
             "writes": ["a fingerprinted suppression keyed on this detection"],
             "recommended": False, "confirm": None},
        ],
    }
    audit = {"ids": [gt_id, str(node_id)],
             "provenance": ["the goal-tension detector (DEMOTE signature)"], "citations": []}
    sfp = fingerprint(f"{node_id}|{signature}|{status}")
    block = make_composed(glance=glance, working=working, decision=decision, audit=audit,
                          minted_by=minted_by, substrate_fingerprint=sfp,
                          goal_version=goal_version, record_ids=[gt_id, str(node_id)])
    return gt_id, block


def action_fingerprint(verb: str, consequence: str) -> str:
    """A stable per-action fingerprint over the verb and its plain consequence — the
    seat of the false-ruling refusal (entry-contract F.1): the surface posts this back
    with the chosen verb, and the door recomposes the tension and refuses a verb whose
    posted fingerprint no longer matches the consequence the surface displayed."""
    return fingerprint(f"{verb}|{consequence}")


def _stamp_action_fingerprints(decision: dict) -> dict:
    """Attach :func:`action_fingerprint` to every action row of a decision in place, so
    a served action row carries the server-verifiable seat the bank door recomputes."""
    for a in (decision.get("actions") or []):
        a["fingerprint"] = action_fingerprint(a.get("verb", ""), a.get("consequence", ""))
    return decision


def compose_author_goal_tension(*, corpus: str, goal_node_id: str,
                                banked_goal_essence: str, restatement_gist: str,
                                reconstruction: str, gen_note: str = "",
                                goal_version: Optional[int] = None,
                                verdict_ref: str = "",
                                minted_by: str = "author_goal_tensions") -> tuple[str, dict]:
    """Compose the authored-goal reconciliation tension — the second drift signature.

    The banked goal names one thing (resource estimates), his own restatement names
    another (the mid-circuit methodological development, and what coherent feedback
    gains); the two have not been reconciled, and only he can say which the paper is.
    Returns ``(gt_id, block)`` with a stable id keyed on the corpus + the authored
    restatement, so a ruling or a suppression addresses the same detection. Each of the
    four verbs owns its consequence, its organ, and its :func:`action_fingerprint` seat;
    the recommendation leans REGOAL, marked never pre-selected.
    """
    gt_id = "GT-" + fingerprint(f"{corpus}|author-goal|{verdict_ref}")
    banked = (banked_goal_essence or "the banked goal").strip().rstrip(".")
    glance = ("The banked goal titles this paper a set of resource estimates, but his own "
              "restatement puts the mid-circuit methodological development — how to run this "
              "class of algorithm coherently, and what that gains — as the real goal; the two "
              "have not been reconciled, and the paper cannot be both at once.")
    working = ("The banked goal reads as a resource-estimate title, while his restatement names "
               "the interesting goal as the coherent, clever way to run the measurement-driven "
               "iteration and what coherence buys — with the resource estimate as a separate "
               "supporting part. The stored goal and his stated intent disagree about what the "
               "paper is for; reconciling them is his ruling to make.")
    realign_conseq = ("The manuscript is reshaped so the methodological development reads as the "
                      "headline and the resource estimate becomes the supporting part; the banked "
                      "goal stands; the reshaping is banked as a note on the manuscript"
                      + (f" — {gen_note}" if gen_note else "") + ".")
    regoal_conseq = ("The banked goal is replaced by his restatement of what the paper is for; you "
                     "confirm the new goal text first — nothing is saved until you approve it — then "
                     "a new goal version supersedes the old one and the queues re-audit against it.")
    hold_conseq = ("The mismatch between the banked title and his stated intent is recorded as "
                   "knowingly tolerated, with his reason; neither the manuscript nor the goal "
                   "changes, and the named gap stays on the record.")
    dismiss_conseq = ("The reconciliation prompt is set aside as not a real tension; it stays "
                      "dismissed until the goal material or his statement changes; nothing in the "
                      "manuscript or the goal moves.")
    decision = {
        "tension": (f"The banked goal presents the paper as {banked!r}; his restatement puts the "
                    "coherent mid-circuit methodological development as the real contribution."),
        "actions": [
            {"verb": "REALIGN/RESPINE", "consequence": realign_conseq,
             "resolves": "the manuscript still leads on the resource estimate, not the method",
             "writes": ["a banked note on the manuscript ledger (author-gated)"],
             "recommended": False, "confirm": None},
            {"verb": "REGOAL", "consequence": regoal_conseq,
             "resolves": "the banked goal names the wrong thing as the paper's contribution",
             "writes": ["the goal supersede through the rewire ledger"],
             "recommended": True, "confirm": reconstruction},
            {"verb": "HOLD/WAIVE", "consequence": hold_conseq,
             "resolves": "whether the mismatch must be closed at all",
             "writes": ["a banked tolerance row (author-gated)"],
             "recommended": False, "confirm": None},
            {"verb": "DISMISS SIGNAL", "consequence": dismiss_conseq,
             "resolves": "whether the reconciliation is worth raising at all",
             "writes": ["a fingerprinted suppression keyed on this detection"],
             "recommended": False, "confirm": None},
        ],
    }
    _stamp_action_fingerprints(decision)
    audit = {"ids": [gt_id, str(goal_node_id)],
             "provenance": ["his restatement of the goal, banked in his words"],
             "citations": [verdict_ref] if verdict_ref else []}
    sfp = fingerprint(f"{corpus}|{restatement_gist}|{banked}")
    block = make_composed(glance=glance, working=working, decision=decision, audit=audit,
                          minted_by=minted_by, substrate_fingerprint=sfp,
                          goal_version=goal_version, record_ids=[gt_id, str(goal_node_id)])
    return gt_id, block


def _humanize_demand(demand_id: str) -> str:
    """A plain phrase for a demand id, keeping the raw id out of the account. The
    known demands read as sentences a person can act on; the fallback de-slugs."""
    phrases = {
        "D-every-claim-has-a-result": "every claim carries a validating result",
        "D-figure-resolves": "every promised figure resolves to a real one",
        "D-no-naked-claims": "no claim stands without support",
        "D-honest-status": "every load-bearing claim declares how it is known",
        "D-real-corpus-citation": "every citation points into the real corpus",
    }
    if str(demand_id) in phrases:
        return phrases[str(demand_id)]
    name = str(demand_id)
    if name.startswith("D-"):
        name = name[2:]
    return name.replace("-", " ").strip() or "this requirement"


#: the glance for a demand-audit row, keyed on its verdict (plain outcome language).
_VERDICT_GLANCE = {
    "red": ("A required check found places where the manuscript falls short of what the goal "
            "asks; this requirement is not yet met."),
    "floor-holds": ("This requirement is met on the manuscript as it stands — the check found "
                    "nothing outstanding."),
    "judged-pending": ("This requirement needs a reader's judgement; no machine verdict stands "
                       "in for it."),
    "not-runnable-here": ("This requirement cannot be checked without a built artefact, so it is "
                          "not answerable here yet."),
    "inactive": "This requirement does not apply to the manuscript as it stands.",
}


def compose_audit_row(*, demand_id: str, verdict: str, node_ids: Optional[list],
                      detail: str = "", goal_version: Optional[int] = None,
                      minted_by: str = "demand.audit") -> tuple[str, dict]:
    """Compose a demand-audit queue row: glance + working in plain outcome language,
    ``decision`` null (the row's real doors today are reads — it is ruled through its
    queue, not on itself). Returns ``(dq_id, block)`` with a stable id."""
    node_ids = [str(x) for x in (node_ids or [])]
    dq_id = "DQ-" + fingerprint(f"{demand_id}|{goal_version}|{'|'.join(sorted(node_ids))}")
    name = _humanize_demand(demand_id)
    n = len(node_ids)
    glance = _VERDICT_GLANCE.get(verdict, "This requirement's status could not be read.")
    if verdict == "red":
        # a red glance names ITS demand and ITS count — four rows reading one identical
        # generic sentence is the integration pushed back onto him (the perfectionist
        # pass's sharpest wince). The raw detail string stays at audit depth.
        glance = (f"The requirement that {name} is not met — the check named "
                  f"{n} place{'s' if n != 1 else ''} needing attention.")
        working = (f"The requirement that {name} is not satisfied: the check named {n} place(s) "
                   "that need attention before the manuscript meets it.")
    elif verdict == "floor-holds":
        working = (f"The requirement that {name} holds on the manuscript as it stands; nothing "
                   "is outstanding.")
    elif verdict == "judged-pending":
        working = (f"The requirement that {name} is a matter for a reader's judgement, not a "
                   "mechanical check.")
    elif verdict == "not-runnable-here":
        working = (f"The requirement that {name} needs a built artefact to check; the token-free "
                   "pass cannot answer it, and says so rather than guessing.")
    elif verdict == "inactive":
        working = f"The requirement that {name} does not apply to this manuscript, so nothing is asked."
    else:
        working = f"The status of the requirement that {name} could not be read on this pass."
    audit = {"ids": [dq_id, str(demand_id)] + node_ids,
             "provenance": (["the demand audit (token-free symbolic pass)"]
                            + ([f"detail: {detail}"] if detail else [])), "citations": []}
    sfp = fingerprint(f"{demand_id}|{verdict}|{'|'.join(node_ids)}")
    block = make_composed(glance=glance, working=working, decision=None, audit=audit,
                          minted_by=minted_by, substrate_fingerprint=sfp,
                          goal_version=goal_version, record_ids=[dq_id])
    return dq_id, block


#: the plain word for a coverage axis (the internal axis key stays under audit).
_AXIS_WORD = {"supports": "literature grounding", "validates": "validation",
              "demonstrates": "figure demonstration"}

#: per coverage axis (internal key) — the routing verb the surface names as a button, and
#: the plain consequence it owns (what a banked order writes, and what acceptance would
#: produce back in the conceptric). Only an axis with a live gap (``0 <= covered < total``)
#: carries the routing action; a real zero or a covered axis stays ``decision`` null.
_AXIS_ROUTE = {
    "supports": ("route to literature work",
                 "A literature-mining order is banked for the claims that ground nothing "
                 "yet; if a later session runs it and it is accepted, each named claim gains "
                 "a grounding node and a supports edge, so it traces to the corpus it rests "
                 "on. Nothing runs from this button — it only banks the request."),
    "validates": ("route to derivation work",
                  "A derivation-or-simulation order is banked for the claims that carry no "
                  "validation yet; if a later session runs it and it is accepted, each named "
                  "claim gains a derivation node and a validates edge, so it carries the "
                  "evidence it was missing. Nothing runs from this button — it only banks the "
                  "request."),
    "demonstrates": ("route to figure work",
                     "A figure-from-evidence order is banked for the results that nothing "
                     "shows yet; if a later session runs it and it is accepted, each named "
                     "result gains a figure node and a demonstrates edge, so a reader can see "
                     "it. Nothing runs from this button — it only banks the request."),
}


def compose_coverage_row(*, axis: str, covered: int, total: int,
                         goal_version: Optional[int] = None,
                         minted_by: str = "coverage_vector",
                         route: bool = False) -> dict:
    """Compose a coverage-axis row: glance + working. ``decision`` is null by default (a
    coverage row is read, and ruled through its queue). With ``route=True`` and a live gap
    (``0 <= covered < total``) the row carries a single routing action — the one door that
    turns the measured gap into a banked work order — with its per-action consequence and a
    server-verifiable :func:`action_fingerprint` seat. A real zero is stated as measured,
    not as a partially-filled bar needing a caveat, and carries no routing action."""
    axis_word = _AXIS_WORD.get(axis, str(axis))
    cov_id = "CV-" + fingerprint(f"{axis}|{total}|{goal_version}")
    if total == 0:
        glance = f"There is nothing to cover on the {axis_word} axis yet; the count is a real zero."
        working = (f"No load-bearing claim raises the {axis_word} axis on the manuscript as it "
                   "stands.")
    elif covered == 0:
        glance = (f"None of the {total} claims that need {axis_word} carry it yet — the axis is "
                  "empty, and this is measured, not assumed.")
        working = (f"{total} claims raise the {axis_word} axis and none are covered; the typed "
                   "links that would cover them have not landed.")
    else:
        glance = f"{covered} of {total} claims that need {axis_word} carry it; the rest are still open."
        working = (f"{covered} of {total} claims on the {axis_word} axis are covered; the "
                   "remainder are named as open on the axis.")
    decision = None
    if route and total and covered < total:
        verb_conseq = _AXIS_ROUTE.get(axis)
        if verb_conseq:
            verb, consequence = verb_conseq
            n_open = total - covered
            decision = {
                "tension": (f"{n_open} of {total} claims that need {axis_word} carry it, and "
                            "nothing has been asked to close the gap; the demand can stay a "
                            "report or become a banked order."),
                "actions": [{
                    "verb": verb,
                    "consequence": consequence,
                    "resolves": f"the {axis_word} axis reads a gap that nothing has been routed to close",
                    "writes": ["a banked work order in the friction channel"],
                    "recommended": False,
                    "confirm": None,
                }],
            }
            _stamp_action_fingerprints(decision)
    audit = {"ids": [cov_id], "provenance": ["the coverage-vector builder"], "citations": []}
    sfp = fingerprint(f"{axis}|{covered}|{total}")
    return make_composed(glance=glance, working=working, decision=decision, audit=audit,
                         minted_by=minted_by, substrate_fingerprint=sfp,
                         goal_version=goal_version, record_ids=[cov_id])
