"""the desk cockpit (surface 6) — every decision a cockpit, at ``/desk``.

The conception's P6 (DESIGN_2026-07-14 §6): the chair walk found a desk row that
expanded into the SAME truncated one-liner plus six ruling buttons — a ruling demanded
on a document that could not be read from where the ruling happens, whose file path
was not even a link. This surface is the pattern that replaces it. Every decision
expands IN PLACE into a COCKPIT with four zones:

  1. CONTEXT — the full renderable referent, INLINE (never a truncation): the verbatim
     source document (``feedback/sources/*.md`` rendered readable), the finding's exact
     ledger row, the manuscript prose the node concerns, the OPEN_STACK / friction record,
     the work-order JSON prettied. Fetched lazily per row (``GET /desk/referent``) so the
     list stays bounded (Law I) while the cockpit shows the WHOLE referent.
  2. CONSEQUENCES — what changes on each available ruling (``_DECISION_CONSEQUENCES``);
     a class with no model renders its declared absence, never an omitted silence.
  3. TOOLS — ALL execution verbs inline, arm-to-fire on destructive ones, every one a
     THIN dispatch through the one mutation door (``POST /desk/act``) to an existing
     executor (never new mutation logic here).
  4. DEEP-LINKS — the exact spine locations on the WORKING surfaces
     (``/artefact?corpus&node&section``, ``/conceptric?node``, ``/storyboard#beat``) —
     never a surface's front door.

Rehoused from ``guide.py``'s desk mechanics (W1.3 join → W2.1 act door), moved out of
the dying ``/guide`` explainer. The (class, verb) roster, the fail-closed 422, and the
by-attribution actor guard are preserved EXACTLY — this module owns NO write machinery:
every verb resolves the target, stamps the actor, and hands off to the executor whose
contract (validate → idempotency → append-only) already holds.

The routes (GET reads + the one act POST):

  * ``GET  /desk``           — the surface page (``desk.html``; served by the scanner,
                               like the other apps — :func:`handle` returns ``None``).
  * ``GET  /desk/data``      — the read-model: the eleven provenance classes joined into
                               a strata-first summary + a bounded (≤``_QUEUE_CAP``, Law I),
                               his-move-ordered drill-down. Each class joins a REAL store.
  * ``GET  /desk/referent``  — the full CONTEXT referent for ONE row (``?class&project&id``).
  * ``GET  /desk/architecture-profile`` — the READABLE render of
                               ``profiles/author_architecture.yaml`` (Part 2, W-CRAP): the
                               confirm-architecture-profile work-order's referent opens ON
                               this composed view (his charge "how am I supposed to see this
                               profile"). An altitude of the desk's work, not a nav page.
  * ``POST /desk/act``       — the one mutation door: each verb a thin dispatch to an
                               existing executor; a NAMED-but-unwired verb is a fail-closed
                               422 naming where its door lands.
"""
from __future__ import annotations
from laplace.core import observe
from laplace.core.checkout import source_tree

import json
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

from laplace.engine import engine_ledger
from laplace.engine import open_stack_store
from laplace.pipeline import adjudicate as _adj
from laplace.pipeline import edits as _edits
from laplace.pipeline import friction_consumer as _fc
from laplace.pipeline import registry
from laplace.pipeline import suppress as _suppress
from laplace.pipeline.friction_consumer import open_frictions
from laplace.pipeline.ledger import append_jsonl, read_jsonl

#: ledger ``record`` types that are ACTIONS on a finding (adjudications /
#: suppressions / the txn journal / projection-intents), never findings the desk
#: adjudicates. Built from the SAME canonical constants review_surface's findings
#: board excludes (``_NON_FINDING_RECORDS``) so the two readers agree — an action a
#: ruling deposited never reads back as a fresh finding, and ``projection-intent``
#: (∈ ``ADJ_RECORD_KINDS``) is claimed by the plan-ops branch below, not here.
_NON_FINDING_RECORDS = frozenset(_adj.ADJ_RECORD_KINDS
                                 | {_suppress.RECORD_KIND, _suppress.REVOKE_KIND,
                                    _edits.RECORD_KIND, "txn"})


def _is_author_sourced(rec: dict) -> bool:
    """True when a feedback record is AUTHOR-origin — his to adjudicate — rather than a
    machine detection (a mech-panel round / reader / holdout finding: the converge
    loop's work, never his desk).

    Derived from the fields the LIVE writers actually stamp, NOT from an ingest-era
    ``record``/``source`` shape no writer reproduces:

    * the ANNOTATE door (:func:`manuscript_bridge.feedback_add`, the one the artefact
      tray / node-comment surfaces bank through) stamps ``by`` = an author actor
      (``gerard``, a claimed handle, a remote ``visitor:``) and NO ``source``;
    * the RELAY path stamps ``source`` = ``the-author:…`` / ``author…`` / a judgement
      source-doc under ``feedback/sources/``.

    A machine panel stamps ``by`` = ``judge-panel`` and/or a machine ``source``
    (``mech-panel:…`` / ``reader`` / ``R7`` / ``holdout-…`` / ``machine``) — none of
    which this admits, so the 2000-strong machine ledger never floods his desk."""
    from laplace.manuscript import manuscript_bridge as _mb
    by = (rec.get("by") or "").strip().lower()
    src = (rec.get("source") or "").strip().lower()
    if by in _mb.AUTHOR_ACTORS or by.startswith("author") or by.startswith("visitor:"):
        return True
    return (src.startswith("the-author") or src.startswith("author")
            or "feedback/sources/" in src)

_HTML = Path(__file__).resolve().parent / "desk.html"
_REPO_ROOT = source_tree()

_JSON = "application/json; charset=utf-8"


def _q1(query: dict, key: str, default: str = "") -> str:
    v = query.get(key)
    if isinstance(v, list):
        return v[0] if v else default
    return v if v is not None else default


def _json_resp(status: int, obj: Any) -> tuple[int, str, bytes]:
    return status, _JSON, json.dumps(obj, ensure_ascii=False).encode("utf-8")




def _ruling_id(prefix: str, target: str) -> str:
    """A stable-enough append-only ruling id: ``<PREFIX>-<UTCstamp>-<target>``. Used by the
    fork/lift ruling writers — the record is append-only, the id names what it rules."""
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    clean = "".join(ch if ch.isalnum() else "-" for ch in str(target)).strip("-") or "row"
    return f"{prefix}-{stamp}-{clean[:48]}"


#: the sidecar ledgers the desk's ruling writers append to — read back by the desk's own
#: reconciling readers (``_desk_forks`` / ``_desk_lifts``) so a ruled row leaves the desk.
_LIFT_RULINGS_REL = "corpus_friction/dream_lift_rulings.jsonl"


def _truncate(text: str, n: int = 120) -> str:
    """Bound ``text`` to ``n`` chars at a WORD boundary (finding 7) — back up to the last
    whole word rather than clipping mid-word ("…autho…"), then trim trailing punctuation
    before the ellipsis. A word boundary is only honoured when it falls within the last 40%
    of the cap (else a very long single word is clipped as before)."""
    t = (text or "").strip()
    if len(t) <= n:
        return t
    clip = t[: n - 1].rstrip()
    sp = clip.rfind(" ")
    if sp >= n * 0.6:
        clip = clip[:sp]
    return clip.rstrip(" .,;:—–-") + "…"


def _first_clause(text: str, n: int = 120) -> str:
    """The first sentence-ish clause of ``text`` — split at the first sentence /
    semicolon / newline boundary that falls within ``n`` chars, else the whole text
    bounded to ``n``. Used to build a legible title (verb + object + the clause that
    actually distinguishes this row from its siblings), never a mid-word truncation
    pretending to be the whole note."""
    t = (text or "").strip()
    if not t:
        return ""
    for sep in (". ", "; ", "\n"):
        i = t.find(sep)
        if 0 < i <= n:
            return t[:i].strip()
    return _truncate(t, n)


# ---------------------------------------------------------------------------
# THE TYPED OPEN_STACK fork store (W2.3) — read through the ONE shared reader
# (``laplace.engine.open_stack_store``) so the desk surface and the WAKE (self_corpus)
# read ONE store one way. AUDIT_2026-07-15 §B1 closed the drift channel where the
# wake's textual glyph-scan of rendered OPEN_STACK.md could resurrect a fork this
# typed ``status`` field had retired. The desk's filtering is unchanged (byte-
# identical): ``_LIVE_MARKER in (f["status"] or "")``, now housed in the store module.
# ---------------------------------------------------------------------------
def _load_open_stack_forks(repo: Path) -> list[dict]:
    return open_stack_store.load_forks(repo)


def _live_open_stack_forks(repo: Path) -> list[dict]:
    return open_stack_store.live_forks(repo)


# ---------------------------------------------------------------------------
# LAW I (the density law): the desk is a bounded worklist, not a scroll wall.
# ---------------------------------------------------------------------------
_QUEUE_CAP = 40
#: the per-class inline sample cap: each class shows at most this many rows in the drill-
#: down; the rest ride the class's ``more_href`` DOOR (a served view of the whole class,
#: ``GET /desk/class``). Small so the DEFAULT desk is a cleared worklist, not a firehose —
#: the door carries the tail (P10: a capped list is lawful only with a real +N-more door).
_CLASS_CAP = 8
#: the golden payload byte ceiling (Law I): the read-model is bounded, never a firehose.
_BYTE_CAP = 16 * 1024


# ---------------------------------------------------------------------------
# THE ELEVEN CLASSES (authored once; each JOINS a real store). ``owner`` splits
# them: ``him`` = a decision only he (or the proxy on his behalf) makes.
# ``engine`` = a mechanical move surfaced for awareness — it waits on a machine
# session and is never his to fire at the desk (read-only exhaust).
#
# ONE TRUTH (stranger-walk finding, banked leg F, corrected 2026-07-23): the BRIEF's
# quiet-or-not gate is ``his_move`` — the sum of counts across ``him``-owned classes
# below, taken from the SAME direct store reads (``_desk_feedback``, ``_desk_forks``,
# ``_desk_proxy``, ``_desk_lifts``, plan-ops) that build each class's rows/chip. It is
# NOT the ``top`` strip (``project_state.owed_to_author``) — that used to be the sole
# gate and could drift from these class reads, saying "quiet" while a him-owned chip
# sat right below it, nonzero, naming the very decision the banner denied. The ``top``
# strip still supplies the richer NAMED lead (:func:`_compose_brief_prose`) when it
# resolves one, but never overrides the class-read count on whether the desk is quiet.
# ---------------------------------------------------------------------------
_DESK_CLASSES: list[dict] = [
    {"class": "adjudications", "label": "his adjudications", "scope": "project", "owner": "him",
     "store": "per-project feedback.jsonl — open author-sourced findings (annotate-door by-actor + relayed), machine panels excluded",
     "verbs": ["confirm", "dismiss", "defer", "route-plan", "route-conceptric", "comment"]},
    {"class": "plan-ops", "label": "plan-ops (projection-intents)", "scope": "project", "owner": "him",
     "store": "per-project feedback.jsonl — open projection-intents (adjudicate.live)",
     "verbs": ["ratify", "revoke-intent"]},
    {"class": "forks", "label": "open author-forks", "scope": "engine", "owner": "him",
     "store": "OPEN_STACK.md (🔴-live) + corpus_friction/*.jsonl `fork` records",
     "verbs": ["bank-ruling", "contest-ruling"]},
    {"class": "proxy-drafts", "label": "proxy drafts", "scope": "engine", "owner": "him",
     "store": "proxy_verdicts.jsonl — autonomous rulings, contestable (uncontested)",
     "verbs": ["confirm", "amend", "reject"]},
    {"class": "lifts", "label": "dream lifts", "scope": "region", "owner": "him",
     "store": "corpus_friction/dream_lifts_*.json — PROPOSED, awaiting authorization",
     "verbs": ["authorize", "refuse"]},
    {"class": "open-frictions", "label": "open frictions", "scope": "project", "owner": "engine",
     "store": "corpus_friction/*.jsonl — the unified friction channel (non-fork)",
     "verbs": ["resolve"]},
    {"class": "recurrence-clusters", "label": "recurrence clusters", "scope": "engine", "owner": "engine",
     "store": "corpus_friction/*.jsonl — chain-prefix rollups with ≥2 witnesses",
     "verbs": ["resolve-cluster"]},
    {"class": "stale-reads", "label": "stale derived-reads", "scope": "global", "owner": "engine",
     "store": "the derived-read artifacts (shared_ui.staleness: router cache, metric, voice store)",
     "verbs": ["rebuild"]},
    {"class": "work-orders", "label": "open work-orders", "scope": "project", "owner": "engine",
     "store": "corpus_friction/work_orders.jsonl — model-heavy launches banked for a later session to run",
     "verbs": ["consume"]},
    {"class": "holdout", "label": "holdout prediction", "scope": "global", "owner": "engine",
     "store": "holdout/PREDICTION_pending.json — pending, awaiting scoring",
     "verbs": ["score"]},
    {"class": "release-states", "label": "release states needing a move", "scope": "project", "owner": "engine",
     "store": "pipeline.registry state sidecars (release/state.json)",
     "verbs": ["run", "resume"]},
]

#: class -> its named verbs (derived from the one authored table, never a 2nd copy).
_CLASS_VERBS: dict[str, list[str]] = {c["class"]: c["verbs"] for c in _DESK_CLASSES}

#: release states that still need a move (anything short of the human/terminal bar).
_RELEASE_NEEDS_MOVE = {"NEVER_RUN", "STAGED", "WELDED", "MECHANICALLY_VALID",
                       "UNDER_CONVERGENCE", "CANDIDATE_LOCKED", "REOPENED"}


# ---------------------------------------------------------------------------
# ZONE 2 — CONSEQUENCES: what changes per ruling, per (class, verb). A class/verb
# absent here renders its HONEST ABSENCE in the cockpit ("no consequence model
# yet"), never an omitted silence (conception §6.2). Authored once; the read-model
# carries it on the strata so the cockpit reads the SAME truth for every row of a
# class (never re-derived per row).
# ---------------------------------------------------------------------------
_DECISION_CONSEQUENCES: dict[str, dict[str, str]] = {
    "adjudications": {
        "confirm": "the finding is banked confirmed — a ruled item in the ledger; suppression untouched.",
        "dismiss": "writes a fingerprinted suppression — THIS finding and re-detections with the same "
                   "content stay silent until the content changes (a stale suppression re-surfaces).",
        "defer": "the finding leaves the active queue but is NOT discarded — it returns if re-raised.",
        "route-plan": "routes the finding to the PLAN as a draft projection-intent — nothing auto-applies.",
        "route-conceptric": "routes the finding to the CONCEPTRIC as a draft intent — nothing auto-applies.",
        "comment": "appends a comment to the finding — no state change (opens /artefact to compose).",
    },
    "plan-ops": {
        "ratify": "applies EVERY open plan intent for this project (the C3.5 bridge is a BATCH, not just "
                  "this row); the plan changes and consumed intents retire — idempotent on a re-fire.",
        "revoke-intent": "supersedes THIS queued intent — it will not be applied; the plan is unchanged.",
    },
    "work-orders": {
        "consume": "closes this work-order through an EVIDENCE-carrying resolution — it leaves the open "
                   "set; refused (order stays open) without evidence or an actor.",
    },
    "release-states": {
        "run": "launches the pipeline for this project (deferred — the /pipeline run panel owns the door, W6).",
        "resume": "resumes a mid-flight project (deferred — the /pipeline run panel owns the door, W6).",
    },
    "stale-reads": {
        "rebuild": "engine-owned: the PSU law NAMES the fix; a click never fires a heavy rebuild.",
    },
    "forks": {
        "bank-ruling": "banks your ruling on this author-fork — appends a fork-ruling record to the "
                       "OPEN_STACK store; the fork retires off your desk (append-only, never a line edit).",
        "contest-ruling": "records your objection to this fork — appends a contested fork-ruling; the "
                          "fork leaves your desk with the disagreement on the record (append-only).",
    },
    "proxy-drafts": {
        "confirm": "affirms the proxy's autonomous ruling — appends a kind:\"confirm\" record "
                   "(append-only, retrospective); the verdict stands and leaves your contestable set.",
        "amend": "opens the compose surface to write a REPLACEMENT ruling — nothing is written "
                 "until you bank it there; the standing verdict is untouched meanwhile.",
        "reject": "contests the proxy's ruling — appends a kind:\"contest\" record (never an "
                  "in-place edit); the verdict is overruled and drops off your desk.",
    },
    "lifts": {
        "authorize": "authorizes this dream-lift — appends an authorized lift-ruling; the proposal "
                     "leaves your desk (append-only; the forge stays a separate, explicit act).",
        "refuse": "refuses this dream-lift — appends a refused lift-ruling; the proposal leaves your desk.",
    },
    "open-frictions": {
        "resolve": "resolves this open friction — appends an evidence-carrying resolution to its "
                   "friction ledger; the friction retires (an evidence-less resolve is refused).",
    },
    "recurrence-clusters": {
        "resolve-cluster": "resolves EVERY open friction sharing this cluster's recurring root — one "
                           "evidence-carrying resolution per witness; the cluster dissolves once fewer "
                           "than two remain (an evidence-less resolve is refused).",
    },
    "holdout": {
        "score": "scores the pending holdout prediction — runs each mechanical check, banks a "
                 "holdout/SCORED_<ts>.json, and clears the pending file (the prediction leaves your desk). "
                 "The mechanical half runs unconditionally; the ARCHIVE is refused without "
                 "behavioral_scores, because archiving unlinks the pending file and the behavioral "
                 "claims would be settled unread.",
    },
}


# ---------------------------------------------------------------------------
# ZONE 4 — DEEP-LINKS: the exact spine location on the WORKING surfaces, never a
# front door. A row carries a primary ``href`` (the first, most-precise landing)
# plus a ``deeplinks`` list of {label, href} into the other spine surfaces.
# ---------------------------------------------------------------------------
def _artefact_href(name: str, node: str = "", section: str = "") -> str:
    """A deep-link into ``/artefact`` (the one reader/annotator) for corpus ``name`` at
    the finding's node/section — carried as store.mjs selection params (``corpus``,
    ``node``, ``section``), so the annotator opens ON the referent, never the front door."""
    href = f"/artefact?corpus={quote(name, safe='')}"
    if node:
        href += f"&node={quote(str(node), safe='')}"
    if section:
        href += f"&section={quote(str(section), safe='')}"
    return href


def _conceptric_href(node: str) -> str:
    """A deep-link into ``/conceptric`` at the node — where the finding's node argues."""
    return f"/conceptric?node={quote(str(node), safe='')}" if node else ""


def _storyboard_href(name: str, beat: str = "") -> str:
    """A deep-link into ``/storyboard`` for corpus ``name``, at the beat anchor when known."""
    href = f"/storyboard?corpus={quote(name, safe='')}" if name else "/storyboard"
    if beat:
        href += f"#{quote(str(beat), safe='')}"
    return href


def _adjudication_deeplinks(name: str, node: str, section: str) -> list[dict]:
    """The spine locations an adjudication concerns: the paragraph in the reader, where
    the node argues in the conceptric, and the section's beat on the board.

    The up-conjugate (#1): the three hrefs are derived from ``ladder.doors_for`` — the
    SAME href-composition the ladder panel serves — so the desk and the viewer resolve a
    target through ONE function and can never drift. The labels stay the desk's own (the
    reader/conceptric/board framing); the routes are the ladder's prose/concept/argument
    doors, verbatim."""
    from laplace.web import ladder
    target = {"raw": node or section, "kind": "node" if node else "section",
              "node": node, "section": section, "node_ids": [node] if node else []}
    doors = {d["id"]: d["href"] for d in ladder.doors_for(name, target)}
    out: list[dict] = [{"label": "read the paragraph (/artefact)", "href": doors["prose"]}]
    if node:
        out.append({"label": "where it argues (/conceptric)", "href": doors["concept"]})
    out.append({"label": "the section's beat (/storyboard)", "href": doors["argument"]})
    return out


def _rel_to_repo(p: Path, repo: Path) -> str:
    """A repo-relative POSIX path for a store the scoped read touched (the two-stores
    proof records these), or the absolute string when the path escapes the root."""
    try:
        return p.resolve().relative_to(repo.resolve()).as_posix()
    except (ValueError, OSError):
        return str(p)


def scoped_decisions(repo: Path, corpus: str, node_ids, section: str | None = None,
                     asset_id: str | None = None, cap: int = 20) -> dict:
    """THE (corpus, target)-SCOPED open-decision read — the ladder's judgment rung and the
    desk's shared join, ONE home. Reads EXACTLY TWO stores, never the directory glob:

      1. the project's ``feedback_ledger`` — open, author-sourced findings (the filter
         idiom of :func:`_desk_feedback`: open ∧ not an action-record ∧ author-sourced),
         kept when the finding's node ∈ ``node_ids`` or its section == ``section``;
      2. ``corpus_friction/<corpus>.jsonl`` (that ONE file) — open non-fork friction rows,
         kept when the row's node ∈ ``node_ids``.

    An unscoped call (no node_ids, no section, no asset) is the PROJECT scope — every open
    decision of the corpus. ``count`` is the true total across both stores; ``rows`` is
    capped at ``cap`` (the count is never reduced to the shown length). ``sources`` names
    the two store paths actually read (the bijection's ledger substrate)."""
    node_set = {str(n).strip() for n in (node_ids or []) if str(n).strip()}
    section = (section or "").strip()
    scoped = bool(node_set or section or asset_id)
    rows: list[dict] = []
    total = 0
    sources: dict[str, str | None] = {"feedback_ledger": None, "corpus_friction": None}

    proj = registry.resolve(corpus)
    if proj is not None and proj.feedback_ledger:
        try:
            led = proj.path(proj.feedback_ledger, repo)
        except Exception:  # noqa: BLE001 - a bad sibling path is skipped, never fatal
            led = None
        if led is not None and led.is_file():
            sources["feedback_ledger"] = _rel_to_repo(led, repo)
            for rec in read_jsonl(led):
                if (rec.get("status") or "open") != "open":
                    continue
                if rec.get("record") in _NON_FINDING_RECORDS:
                    continue
                if not _is_author_sourced(rec):
                    continue
                node = (rec.get("node_id") or rec.get("node") or "").strip()
                anchor = rec.get("anchor") or {}
                # the annotate door's earliest shape wrote ``anchor`` as the bare
                # section string ('abstract', 'sec:r2_intro-p3') — read it as such.
                if isinstance(anchor, str):
                    anchor = {"section": anchor}
                sec = (rec.get("section") or anchor.get("section") or "").strip()
                if scoped and not ((node and node in node_set) or (section and sec == section)):
                    continue
                total += 1
                if len(rows) < cap:
                    kind = (rec.get("kind") or "note").strip()
                    fid = rec.get("id")
                    title = f"{kind} · {sec}".strip(" ·")
                    body = rec.get("text") or rec.get("comment") or ""
                    fields = {"finding_id": fid, "node": node, "kind": kind, "section": sec}
                    # the row's PRIMARY href is the ladder prose door (dl[0]) — ONE
                    # composition, so the desk's landing can never drift from the viewer's.
                    dls = _adjudication_deeplinks(corpus, node, sec)
                    rows.append(_desk_row(
                        "adjudications", corpus, fid, title, body,
                        _CLASS_VERBS["adjudications"], dls[0]["href"],
                        rec.get("ts") or "", fields, dls))

    fled = repo / "corpus_friction" / f"{corpus}.jsonl"
    if fled.is_file():
        sources["corpus_friction"] = _rel_to_repo(fled, repo)
        for r in open_frictions(read_jsonl(fled)):
            if r.get("kind") == "fork":
                continue
            node = (r.get("node") or "").strip()
            if scoped and not (node and node in node_set):
                continue
            total += 1
            if len(rows) < cap:
                title = f"{r.get('kind') or 'friction'} · {node}".strip(" ·")
                rows.append(_desk_row(
                    "open-frictions", corpus, r.get("id"), title, _fc._one_line(r),
                    _CLASS_VERBS["open-frictions"], "", r.get("ts") or ""))

    return {"count": total, "rows": rows[:cap], "sources": sources}


# ---------------------------------------------------------------------------
# THE ROW + the eleven joins (verbatim from the proven W1.3 read-model, rehoused).
# ``verbs`` are NAMES the cockpit offers as arm-to-fire tools; ``href`` deep-links
# onto the NEW surfaces; ``fields`` are the door-ready target fields the cockpit
# rides straight into the act payload (a fire with a missing field is the door's
# honest 422, not a client fabrication).
# ---------------------------------------------------------------------------
def _desk_row(cls: str, project: str, rid: Any, title: str, context: str,
              verbs: list[str], href: str, ts: str, fields: dict | None = None,
              deeplinks: list[dict] | None = None, title_cap: int = 80) -> dict:
    return {
        "class": cls,
        "project": project or "",
        "id": rid,
        "title": _truncate(title, title_cap),
        "context": _truncate(context, 90),
        "verbs": list(verbs),
        "href": href or "",
        "deeplinks": list(deeplinks or ([{"label": "open", "href": href}] if href else [])),
        "ts": ts or "",
        "fields": dict(fields or {}),
    }


def _empty_class() -> dict:
    return {"rows": [], "by_project": {}, "count": 0}


def _desk_feedback(repo: Path) -> tuple[dict, dict]:
    """adjudications + plan-ops in ONE pass over every registered project's feedback
    ledger. A superseded record (``adjudicate.live``) is retired and never surfaces."""
    adj, ops = _empty_class(), _empty_class()
    for name, proj in registry.all_projects().items():
        if not proj.feedback_ledger:
            continue
        try:
            ledger = proj.path(proj.feedback_ledger, repo)
        except Exception:  # noqa: BLE001 - a bad sibling path is skipped, never fatal
            continue
        if ledger is None or not ledger.is_file():
            continue
        recs = read_jsonl(ledger)
        live_ids = {r.get("id") for r in _adj.live(recs)}
        proj_ops: list[dict] = []          # open projection-intents, collected first (TITLE
                                            # LEGIBILITY + the batch-ratify footgun both need
                                            # every sibling id BEFORE any row is built).
        for rec in recs:
            status = rec.get("status") or "open"
            record = rec.get("record")
            # ADJUDICATIONS — an OPEN, AUTHOR-sourced finding (not an action on one).
            # The live annotate door stamps no ``record`` and no ``source`` (his note
            # rides ``by``/``comment``); the relay path stamps ``source: the-author…``.
            # Both surface; the machine panels/readers (``record:"finding"`` + a machine
            # source) do NOT — they are the converge loop's, never his desk.
            if (status == "open" and record not in _NON_FINDING_RECORDS
                    and _is_author_sourced(rec)):
                adj["count"] += 1
                adj["by_project"][name] = adj["by_project"].get(name, 0) + 1
                node = (rec.get("node_id") or rec.get("node") or "").strip()
                anchor = rec.get("anchor") or {}
                # the annotate door's earliest shape wrote ``anchor`` as the bare
                # section string ('abstract', 'sec:r2_intro-p3') — read it as such.
                if isinstance(anchor, str):
                    anchor = {"section": anchor}
                # the annotate door carries the section on ``anchor.section``; the relay
                # path on a top-level ``section`` — read both so either shape anchors.
                section = (rec.get("section") or anchor.get("section") or "").strip()
                kind = (rec.get("kind") or "note").strip()
                fid = rec.get("id")
                title = f"{kind} · {section}".strip(" ·")
                # the finding body is ``text`` (relay/machine shape) or ``comment``
                # (the annotate door's field) — never assume one shape.
                body = rec.get("text") or rec.get("comment") or ""
                fields = {"finding_id": fid, "node": node, "kind": kind, "section": section}
                # the row's PRIMARY href is the ladder prose door (dl[0]) — ONE
                # composition, so the desk's landing can never drift from the viewer's.
                dls = _adjudication_deeplinks(name, node, section)
                adj["rows"].append(_desk_row(
                    "adjudications", name, fid, title, body,
                    _CLASS_VERBS["adjudications"], dls[0]["href"],
                    rec.get("ts") or "", fields, dls))
            elif (record == "projection-intent" and status == "open"
                  and rec.get("id") in live_ids):
                proj_ops.append(rec)

        # THE BATCH-RATIFY FOOTGUN (E3): reconstructed evolution_consumer.apply_plan_
        # proposals (:779) — it has NO per-id target; it batch-applies EVERY open
        # projection-intent for the corpus in one call, full stop. Since the door this
        # verb dispatches to genuinely cannot fire one id, the per-row "ratify" button
        # must NAME every sibling id it will actually fire (desk-panes.mjs renders
        # this on the label AND the arm text) — never a per-row face on a batch door.
        ratify_all_ids = [str(r.get("id")) for r in proj_ops if r.get("id")]
        for rec in proj_ops:
            ops["count"] += 1
            ops["by_project"][name] = ops["by_project"].get(name, 0) + 1
            obj = rec.get("object") or {}
            # the storyboard anchor (href only) is the SECTION id when this op is a
            # section op — distinct from the object's identifying KEY used in the title.
            anchor = (obj.get("sid") or obj.get("section") or "").strip()
            kind = (obj.get("kind") or "").strip()
            key = (obj.get("sid") or obj.get("key") or "").strip()
            object_ref = f"{kind}:{key}" if key else kind
            verb = (rec.get("verb") or "").strip()
            note = (rec.get("payload") or {}).get("note") or ""
            # TITLE LEGIBILITY (E3): verb + object.key + the note's first clause — three
            # identical "REOPEN meta" rows (bare verb+kind, no key, no note) become
            # distinguishable ("REOPEN meta:contribution_rank - the class thesis …").
            title = " ".join(p for p in (verb, object_ref) if p)
            clause = _first_clause(note)
            if clause:
                title = f"{title} - {clause}" if title else clause
            row = _desk_row(
                "plan-ops", name, rec.get("id"), title, note,
                _CLASS_VERBS["plan-ops"], _storyboard_href(name, anchor),
                rec.get("ts") or "", {"supersedes": rec.get("id")},
                [{"label": "the plan spine (/storyboard)", "href": _storyboard_href(name, anchor)}],
                title_cap=120)
            row["ratify_all_ids"] = ratify_all_ids     # display-only (never POSTed —
                                                       # doFire sends only `fields`)
            ops["rows"].append(row)
    return adj, ops


def _fork_evidence_href(f: dict, repo: Path) -> tuple[str, str]:
    """fork deep-links (E3): an engine-scoped fork carries no plan/spine location
    (it is not anchored to a corpus node) — but its typed ``refs`` field NAMES an
    evidence doc (a repo-relative path, PV-/WO- ids the refs list also carries have
    no extension and are skipped). Resolve the FIRST ref that is an actual file
    under the repo (path-fenced) into a ``file://`` deep-link + its label, so Zone 4
    lands somewhere real instead of ``href=""`` doing double duty as a dead link.
    Returns ``("", "")`` when no ref resolves — the declared absence stays plain."""
    for ref in (f.get("refs") or []):
        ref = str(ref or "").strip()
        if not ref:
            continue
        path, _, frag = ref.partition("#")
        leaf = path.rsplit("/", 1)[-1]
        if "." not in leaf:                    # PV-.../WO-... ids carry no extension
            continue
        try:
            resolved = (repo / path).resolve()
            resolved.relative_to(repo.resolve())      # containment fence
        except (ValueError, OSError):
            continue
        if not resolved.is_file():
            continue
        href = resolved.as_uri() + (("#" + quote(frag, safe="")) if frag else "")
        return href, f"the evidence doc ({leaf})"
    return "", ""


def _desk_forks(repo: Path) -> dict:
    """Open author-forks: the OPEN_STACK 🔴-live records (the typed store, W2.3) PLUS any
    friction-ledger ``kind:"fork"`` open record — the two fork homes joined, deduped by id.
    A fork a WORDED bank-ruling / contest-ruling retired is excluded — read through
    ``open_stack_store.ruled_fork_ids`` (the F39 one-truth reader, landed 2026-07-23), never
    a local re-derivation: a wordless ruling row (guard-bypassing probe residue) must stay
    inert here exactly as it does for the journey badge and ``open_forks`` — one frontier,
    one reader, so the desk class and every other consumer of the fork frontier agree."""
    out = _empty_class()
    seen: set[str] = set()
    ruled = open_stack_store.ruled_fork_ids(repo)
    for f in _live_open_stack_forks(repo):
        fid = str(f.get("id") or "fork")
        if fid in seen or fid in ruled:
            continue
        seen.add(fid)
        title = (f.get("title") or fid).replace("**", "").strip()
        context = f.get("context") or f.get("trigger") or ""
        # PRIMARY href lands on a REAL served surface when the fork names its corpus
        # (F39 carries corpus=paper_falqon); the evidence doc rides Zone 4 as a labeled
        # deep-link. An engine-wide fork (F37/F38, no corpus) keeps href="" (honest
        # absence) with the evidence doc still named — never a dead corpus front door.
        corpus = (f.get("corpus") or "").strip()
        ev_href, ev_label = _fork_evidence_href(f, repo)
        primary = _artefact_href(corpus) if corpus else ""
        deeplinks: list[dict] = []
        if primary:
            deeplinks.append({"label": f"the manuscript (/artefact · {corpus})", "href": primary})
        if ev_href:
            deeplinks.append({"label": ev_label, "href": ev_href})
        out["rows"].append(_desk_row("forks", corpus or "engine", fid, title or fid,
                                     context, _CLASS_VERBS["forks"], primary or ev_href, "",
                                     fields={"id": fid, "target": fid},
                                     deeplinks=deeplinks or None))
    d = repo / "corpus_friction"
    if d.is_dir():
        for led in sorted(d.glob("*.jsonl")):
            for r in open_frictions(read_jsonl(led)):
                if r.get("kind") != "fork":
                    continue
                fid = str(r.get("id") or "fork")
                if fid in ruled:
                    continue
                if fid in seen:
                    continue
                seen.add(fid)
                out["rows"].append(_desk_row("forks", led.stem, fid,
                                             r.get("node") or fid, _fc._one_line(r),
                                             _CLASS_VERBS["forks"], "", "",
                                             fields={"id": fid, "target": fid}))
    out["count"] = len(out["rows"])
    return out


def _desk_proxy(repo: Path) -> dict:
    """Proxy drafts: autonomous rulings still open to his correction — every
    ``proxy_verdicts.jsonl`` verdict neither a ``contest`` record nor already contested."""
    out = _empty_class()
    try:
        from laplace.engine import author_proxy
        recs = author_proxy.load_verdicts(repo)
    except Exception:  # noqa: BLE001 - an unreadable ledger is honestly empty
        return out
    contested = {r.get("contests") for r in recs if r.get("kind") == "contest"}
    confirmed = {r.get("confirms") for r in recs if r.get("kind") == "confirm"}
    for r in recs:
        if r.get("kind") in ("contest", "confirm"):
            continue
        rid = r.get("id")
        if r.get("contested") or rid in contested or rid in confirmed:
            continue
        # the row carries the verdict id as the door-ready `target` (the confirm/reject
        # executors key off it) — a fire with no target is the door's honest 422.
        out["rows"].append(_desk_row("proxy-drafts", "engine", rid,
                                     r.get("question") or "", r.get("ruling") or "",
                                     _CLASS_VERBS["proxy-drafts"], "", r.get("date") or "",
                                     fields={"id": rid, "target": rid}))
    out["count"] = len(out["rows"])
    return out


def _newest_dream_lifts(repo: Path) -> Path | None:
    d = repo / "corpus_friction"
    if not d.is_dir():
        return None
    cands = sorted(d.glob("dream_lifts_*.json"))
    return cands[-1] if cands else None


def _lift_coherent(prop: dict) -> bool:
    j = prop.get("judgment")
    if isinstance(j, dict):                       # the typed judgment carries a coherent flag
        return bool(j.get("coherent"))
    s = str(j or "").lower()
    return bool(s) and "refus" not in s and "reject" not in s


def _lift_context(prop: dict) -> str:
    """A PLAIN one-line context for a lift row (P8: no raw dict on a card). The typed judgment
    is a dict — render its essence / slug, never ``{'index': 0, ...}`` stringified."""
    j = prop.get("judgment")
    if isinstance(j, dict):
        essence = str(j.get("essence") or "").strip()
        members = prop.get("members") or []
        bits = [essence] if essence else []
        bits.append(f"{len(members)} members" if members else "a proposed coarse node")
        return " · ".join(b for b in bits if b)
    return str(j or "")


def _desk_lifts(repo: Path) -> dict:
    """Dream lifts awaiting his authorization — the newest ``dream_lifts_*.json`` manifest,
    only while its status is PROPOSED, coherent proposals only."""
    out = _empty_class()
    p = _newest_dream_lifts(repo)
    if p is None:
        return out
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return out
    if not str(d.get("status") or "").upper().startswith("PROPOSED"):
        return out
    date = d.get("date") or ""
    ruled = _ruled_lift_slugs(repo)
    for prop in d.get("proposals") or []:
        if not _lift_coherent(prop):
            continue
        region = prop.get("region") or "engine"
        slug = prop.get("proposed_slug") or ""
        if slug in ruled:                       # authorize/refuse retired it (durable)
            continue
        out["rows"].append(_desk_row("lifts", region, slug, slug or region,
                                     _lift_context(prop),
                                     _CLASS_VERBS["lifts"], "", date,
                                     fields={"id": slug, "target": slug, "region": region}))
    out["count"] = len(out["rows"])
    return out


def _ruled_lift_slugs(repo: Path) -> set[str]:
    """The lift slugs an authorize / refuse has retired (the desk's own append-only
    ``lift-ruling`` records). Read here — the reconciliation that makes the two lift verbs
    durable: a ruled lift leaves the desk though the proposal manifest is untouched."""
    p = repo / _LIFT_RULINGS_REL
    if not p.is_file():
        return set()
    return {str(r.get("rules")) for r in read_jsonl(p)
            if r.get("kind") == "lift-ruling" and r.get("rules")}


def _friction_scan(repo: Path) -> tuple[dict, dict]:
    """open-frictions + recurrence-clusters in ONE walk of ``corpus_friction/*.jsonl``."""
    frictions, clusters = _empty_class(), _empty_class()
    d = repo / "corpus_friction"
    if not d.is_dir():
        return frictions, clusters
    groups: dict[tuple, list[dict]] = {}
    for led in sorted(d.glob("*.jsonl")):
        proj = led.stem
        for r in open_frictions(read_jsonl(led)):
            if r.get("kind") == "fork":
                continue
            frictions["count"] += 1
            frictions["by_project"][proj] = frictions["by_project"].get(proj, 0) + 1
            title = f"{r.get('kind') or 'friction'} · {r.get('node') or ''}".strip(" ·")
            fid = r.get("id")
            frictions["rows"].append(_desk_row("open-frictions", proj, fid,
                                               title, _fc._one_line(r),
                                               _CLASS_VERBS["open-frictions"], "", "",
                                               fields={"id": fid, "target": fid, "project": proj}))
            groups.setdefault(_fc._group_key(r), []).append(r)
    for key in sorted(g for g, recs in groups.items() if len(recs) >= 2):
        recs = groups[key]
        clusters["count"] += 1
        heading = _fc._group_heading(key)
        # resolve-cluster re-derives the group by its key — carried as door-ready fields so
        # the executor resolves EVERY witness sharing this recurring root, not just a row id.
        clusters["rows"].append(_desk_row(
            "recurrence-clusters", "engine", heading, heading,
            f"{len(recs)} witnesses — the recurring root",
            _CLASS_VERBS["recurrence-clusters"], "", "",
            fields={"group_kind": key[0], "group_prefix": key[1]}))
    return frictions, clusters


def _desk_stale(repo: Path) -> dict:
    """Stale derived-reads: the degraded (absent OR stale) global reads from the W1.2
    staleness contract. PURE READ — the ``rebuild`` verb NAMES the fix (the PSU law)."""
    out = _empty_class()
    try:
        from laplace.web import shared_ui
        data = shared_ui.staleness("", repo_root=repo)
    except Exception:  # noqa: BLE001
        return out
    for r in data.get("reads") or []:
        if not r.get("degraded"):
            continue
        ctx = " → ".join(x for x in (r.get("reason") or "", r.get("fix") or "") if x)
        out["rows"].append(_desk_row("stale-reads", r.get("scope") or "global",
                                     r.get("id"), r.get("label") or r.get("id") or "", ctx,
                                     _CLASS_VERBS["stale-reads"], "", r.get("built_ts") or ""))
    out["count"] = len(out["rows"])
    return out


def _desk_workorders(repo: Path) -> dict:
    """Open work-orders: COUNT AND SELECTION ARE THE ACCOUNT'S (``laplace.engine.wake.account`` -
    WO-20260823-desk-queue-account-dialect: the desk's legacy ``storyboard.
    open_work_order_handles`` parse read a different open-set than the account, so the
    desk and the wake served two answers to "what is owed"; the same one-dialect
    migration the wake's shard made). The store is still read here for the display
    fields the account does not carry; the account decides WHICH ids are open.

    UNFRAMED ROWS ARE MARKED (WO-20260821-composed-bypassed-at-bank): a row with no
    composed block renders with ``composed: False`` in its fields and an ``[unframed]``
    prefix - the organ that frames records for his reading is bypassed on nearly every
    order (0 of 132 at census), and the gap must be visible at the desk, not silent."""
    out = _empty_class()
    try:
        from laplace.engine import wake as _wake
        from laplace.pipeline.ledger import read_jsonl_counted
        acct = _wake.account(repo)["work_orders"]
        rows, _dropped = read_jsonl_counted(
            repo / "corpus_friction" / "work_orders.jsonl", required=True)
        by_id = {r.get("id"): r for r in rows if r.get("id")}
    except Exception as exc:  # noqa: BLE001 - loud degraded row, never empty/green
        out["rows"].append(_desk_row(
            "work-orders", "_engine", "work-orders-integrity",
            "work-order ledger unavailable",
            f"{type(exc).__name__}: {exc}", [], "", "",
            fields={"integrity": "wounded", "store":
                    "corpus_friction/work_orders.jsonl"}))
        out["by_project"]["_engine"] = 1
        out["count"] = 1
        out["degraded"] = True
        return out
    open_rows = [(a, by_id.get(a["id"]) or {}) for a in acct["open_rows"]]
    # newest-first under the cap, exactly as the wake's shard: recency from the row's own
    # ts, the account's date as fallback, so fresh orders never shed behind the cap.
    open_rows.sort(key=lambda p: str(p[1].get("ts") or p[0].get("date") or ""), reverse=True)
    for a, r in open_rows[:_QUEUE_CAP]:
        corpus = r.get("corpus") or ""
        scope = corpus.lstrip("_") if corpus else "engine"
        framed = isinstance(r.get("composed"), dict)
        out["count"] += 1
        out["by_project"][corpus] = out["by_project"].get(corpus, 0) + 1
        out["rows"].append(_desk_row(
            "work-orders", corpus, a.get("id"),
            f"{r.get('action') or '?'} · {scope}",
            ("" if framed else "[unframed] ")
            + f"[{a.get('cost') or 'untyped'}] {r.get('what') or r.get('text') or ''}"[:400],
            _CLASS_VERBS["work-orders"], _artefact_href(corpus) if corpus else "",
            r.get("ts") or a.get("date") or "",
            fields={"id": a.get("id"), "evidence_refs": [],
                    "cost_class": a.get("cost") or "untyped",
                    "composed": framed}))
    out["count"] = acct["open"]
    return out


def _desk_holdout(repo: Path) -> dict:
    """The holdout prediction awaiting scoring — one pending prediction, or nothing banked."""
    out = _empty_class()
    try:
        from laplace.engine import holdout
        pend = holdout.load_pending(repo)
    except Exception:  # noqa: BLE001
        return out
    if not pend:
        return out
    mech = pend.get("mechanical") or []
    beh = pend.get("behavioral") or []
    if not (mech or beh):
        return out
    out["count"] = 1
    out["rows"].append(_desk_row(
        "holdout", "engine", "holdout-pending",
        f"prediction pending · {len(mech)} mechanical + {len(beh)} behavioral",
        pend.get("note") or "", _CLASS_VERBS["holdout"], "", pend.get("banked") or "",
        fields={"id": "holdout-pending"}))
    return out


def _desk_release(repo: Path) -> dict:
    """Release states needing a move — every registered project short of the terminal/human
    bar. The ``run``/``resume`` verbs are NAMED; the pipeline surface owns the launch door
    (W6, now live). The deep-link re-aims onto ``/pipeline?project=`` (the chain from the
    state machine — the organ, its dials, and the scoped fire, in one place)."""
    out = _empty_class()
    for r in registry.project_states(repo):
        state = (r.get("state") or "").upper()
        if state not in _RELEASE_NEEDS_MOVE:
            continue
        name = r.get("name") or ""
        out["count"] += 1
        out["by_project"][name] = 1
        href = f"/pipeline?project={quote(name, safe='')}"
        out["rows"].append(_desk_row(
            "release-states", name, name, f"{name} · {state}",
            f"{int(r.get('rounds_n') or 0)} rounds · {r.get('kind') or ''}".strip(" ·"),
            _CLASS_VERBS["release-states"], href, r.get("updated") or "",
            deeplinks=[{"label": "the pipeline board (/pipeline)", "href": href}]))
    return out


def _class_more_href(cls: str) -> str:
    """THE +N-MORE DOOR (P10): a REAL served view of the WHOLE class — ``GET /desk/class``
    returns every row of one class (its own higher cap + tail split), so a capped inline
    sample is lawful. Set on a stratum only when its inline sample is short of the count."""
    return f"/desk/class?class={quote(cls, safe='')}"


#: THE CONSEQUENCE ORDER (the brief's "most consequential first", BACKED — finding 5): a
#: his-decision ranking the desk already knows. A register verdict (an author-fork on the
#: register) outranks a drafted plan intent (a respine that changes nothing until ratified);
#: adjudications and lifts sit between. Rows the strip never carries (engine classes) are
#: harmless in the table. The brief SORTS the owed strip by this and NAMES the lead — the
#: claim is performed by the data, not asserted over an unsorted append order.
_CONSEQUENCE_ORDER = ["forks", "adjudications", "lifts", "proxy-drafts", "plan-ops"]


def _consequence_rank(row: dict) -> int:
    try:
        return _CONSEQUENCE_ORDER.index(row.get("class") or "")
    except ValueError:
        return len(_CONSEQUENCE_ORDER)


def _owed_top_rows(repo: Path, flat_rows: list[dict]) -> list[dict]:
    """THE CLEARING (ACT 2): the desk opens with the genuinely-HIS decisions on top — a top
    strip fed by :func:`project_state.owed_to_author` (imported, never edited), across every
    registered project. Each owed item is resolved to the FULL desk row already built for it
    (so it carries whole referent fields, verbs, deep-links); an owed item with no built row
    (a RESPINE intent whose plan-op is present, a project fork) still renders as a plain
    handle. him-vs-engine is on the row here by construction — every top row is his."""
    from laplace.pipeline import project_state
    by_id = {str(r.get("id")): r for r in flat_rows}
    top: list[dict] = []
    seen: set[str] = set()
    try:
        projects = list(registry.all_projects().keys())
    except Exception:  # noqa: BLE001 — a roster hiccup yields an empty (honest) top strip
        projects = []
    for name in projects:
        try:
            verdict = project_state.project_verdict(repo, name)
        except Exception:  # noqa: BLE001 — the truth layer degrades honestly, never 500s the desk
            continue
        for owed in verdict.get("owed_to_author") or []:
            oid = str(owed.get("id") or "")
            if not oid or oid in seen:
                continue
            seen.add(oid)
            row = by_id.get(oid)
            if row is not None:
                r = dict(row)
                r["owner"] = "him"
                r["owed_kind"] = owed.get("kind") or ""
                top.append(r)
            else:
                # an owed item the class joins didn't surface (capped out, or a fork scoped
                # to a project) — render the handle whole rather than drop his ask silently.
                cls = "forks" if owed.get("kind") == "open-stack-fork" else "plan-ops"
                href = owed.get("href") or ""
                top.append(_desk_row(
                    cls, name, oid, owed.get("title") or oid, owed.get("title") or "",
                    _CLASS_VERBS.get(cls, []), href, "",
                    fields={"id": oid, "target": oid, "project": name},
                    deeplinks=[{"label": "open where it lands", "href": href}] if href else None,
                    title_cap=140) | {"owner": "him", "owed_kind": owed.get("kind") or ""})
    # MOST CONSEQUENTIAL FIRST, BACKED (finding 5): a stable sort by the consequence order —
    # register verdicts ahead of plan intents — so the brief's lead is the real lead, not the
    # registry's iteration order. Stable: ties keep their owed (per-project) discovery order.
    top.sort(key=_consequence_rank)
    return top


#: the per-producer join for ONE class (the ``more_href`` door reads the whole class through
#: the SAME producer the summary sampled — never a second, drifting reader).
def _class_producer(repo: Path, cls: str) -> dict:
    if cls == "adjudications":
        return _desk_feedback(repo)[0]
    if cls == "plan-ops":
        return _desk_feedback(repo)[1]
    if cls == "forks":
        return _desk_forks(repo)
    if cls == "proxy-drafts":
        return _desk_proxy(repo)
    if cls == "lifts":
        return _desk_lifts(repo)
    if cls == "open-frictions":
        return _friction_scan(repo)[0]
    if cls == "recurrence-clusters":
        return _friction_scan(repo)[1]
    if cls == "stale-reads":
        return _desk_stale(repo)
    if cls == "work-orders":
        return _desk_workorders(repo)
    if cls == "holdout":
        return _desk_holdout(repo)
    if cls == "release-states":
        return _desk_release(repo)
    return _empty_class()


#: the whole-class door's own cap — generous (the tail beyond it is a rare, still-honest
#: second door), but bounded so even a 500-friction class can't firehose the door payload.
_CLASS_DOOR_CAP = 200


def _desk_class(repo: Path, cls: str, offset: int = 0) -> dict:
    """``GET /desk/class`` — the +N-more DOOR's served view of the WHOLE class: every row of
    one class (owner-stamped, offset-paginated), the count plain, a ``more_href`` when the
    door's own cap leaves a tail. This is what makes a capped inline sample lawful (P10)."""
    meta = next((m for m in _DESK_CLASSES if m["class"] == cls), None)
    if meta is None:
        return {"error": f"unknown desk class {cls!r}", "classes": sorted(_CLASS_VERBS)}
    data = _class_producer(repo, cls)
    all_rows = [dict(r, owner=meta["owner"]) for r in data["rows"]]
    window = all_rows[offset: offset + _CLASS_DOOR_CAP]
    end = offset + len(window)
    more = max(0, len(all_rows) - end)
    return {
        "class": cls,
        "label": meta["label"],
        "scope": meta["scope"],
        "owner": meta["owner"],
        "store": meta["store"],
        "verbs": list(meta["verbs"]),
        "deferred": {v: _DEFERRED_VERBS[(cls, v)] for v in meta["verbs"]
                     if (cls, v) in _DEFERRED_VERBS},
        "consequences": dict(_DECISION_CONSEQUENCES.get(cls, {})),
        # WHY, PER CLASS (finding 7c): the rail states why for every his row opened here.
        "why": _WHY_HE_IS_NEEDED.get(cls, "") if meta["owner"] == "him" else "",
        "count": data["count"],
        "by_project": data["by_project"],
        "offset": offset,
        "rows": window,
        "shown": len(window),
        "more": more,
        "more_href": (f"/desk/class?class={quote(cls, safe='')}&offset={end}"
                      if more > 0 else None),
        "generated_ts": observe.now_iso(),
    }


def _desk(repo: Path) -> dict:
    """THE DESK read-model: the eleven provenance classes joined into a strata-first summary
    + a bounded, strata-ordered drill-down, and (ACT 2) a TOP STRIP of the genuinely-his
    decisions (``project_state.owed_to_author``) that clears the desk without a mass rewrite.

    Each class is sampled independently up to ``_CLASS_CAP`` (CHIP == FILTER: a class never
    reads a live count against rows another class spent the cap on — the release-states 11→0
    defect is impossible by construction), and the tail rides a REAL ``more_href`` DOOR (a
    served view of the whole class, ``GET /desk/class``). The single flat ``rows`` list is
    the one copy the payload carries — strata do NOT duplicate their rows (halving the byte
    weight the 16KB golden payload, Law I, must fit). A final byte trim drops ONE row at a
    time from whichever class currently shows the most, so a drop always surfaces as THAT
    class's own ``more`` + door, never a silent global truncation a chip can't explain.
    Everything is derived FRESH; no verb is a live door here."""
    adj, ops = _desk_feedback(repo)
    frictions, clusters = _friction_scan(repo)
    by_class = {
        "adjudications": adj,
        "plan-ops": ops,
        "forks": _desk_forks(repo),
        "proxy-drafts": _desk_proxy(repo),
        "lifts": _desk_lifts(repo),
        "open-frictions": frictions,
        "recurrence-clusters": clusters,
        "stale-reads": _desk_stale(repo),
        "work-orders": _desk_workorders(repo),
        "holdout": _desk_holdout(repo),
        "release-states": _desk_release(repo),
    }
    #: class -> its inline sample rows (the ONE copy, owner-stamped), capped per class.
    sample: dict[str, list[dict]] = {}
    strata: list[dict] = []
    total = 0
    his_move = 0
    for meta in _DESK_CLASSES:
        c = meta["class"]
        data = by_class.get(c, _empty_class())
        total += data["count"]
        if meta["owner"] == "him":
            his_move += data["count"]
        rows = [dict(r, owner=meta["owner"]) for r in data["rows"][:_CLASS_CAP]]
        sample[c] = rows
        strata.append({
            "class": c,
            "label": meta["label"],
            "scope": meta["scope"],
            "owner": meta["owner"],
            "store": meta["store"],
            "verbs": list(meta["verbs"]),
            # DECORATIVE VERBS (E3, P3): the deferred-verb reason, keyed by verb — ONE
            # producer (``_DEFERRED_VERBS``, the same table the act door 422s from), so
            # desk-panes.mjs never re-derives or hand-copies which buttons are dead.
            "deferred": {v: _DEFERRED_VERBS[(c, v)] for v in meta["verbs"]
                        if (c, v) in _DEFERRED_VERBS},
            # ZONE 2 carried on the stratum — one truth per class, read by every row's cockpit.
            "consequences": dict(_DECISION_CONSEQUENCES.get(c, {})),
            # WHY, PER CLASS (finding 7c): the plain reason a his-row of this class needs him,
            # so the rail states "why it needs you" for EVERY his row opened from a chip — not
            # only the two brief-top rows that carry a per-row server-composed why.
            "why": _WHY_HE_IS_NEEDED.get(c, "") if meta["owner"] == "him" else "",
            "count": data["count"],
            "by_project": data["by_project"],
            "shown": len(rows),
            "more": max(0, data["count"] - len(rows)),
        })

    def _refresh_shown() -> None:
        for s in strata:
            c = s["class"]
            s["shown"] = len(sample[c])
            s["more"] = max(0, s["count"] - s["shown"])
            # CHIP == FILTER, closed under the door (P10): shown == reachable rows; the tail
            # (count - shown) is always reachable through a real served ``more_href``.
            s["more_href"] = _class_more_href(c) if s["more"] > 0 else None

    def _payload() -> dict:
        rows = [r for meta in _DESK_CLASSES for r in sample[meta["class"]]]
        shown_total = len(rows)
        return {
            "cap": _QUEUE_CAP,
            "classes": strata,
            "rows": rows,
            "total": total,
            "his_move": his_move,
            "shown": shown_total,
            "truncated": total > shown_total,
            "generated_ts": observe.now_iso(),
        }

    # THE GOLDEN PAYLOAD LAW (Law I): ≤16KB. Trim from whichever class CURRENTLY shows the
    # most (ties toward the lower-priority class, later in ``strata``) so an even, honest
    # "more" + door spreads across the fat classes instead of collapsing most to 0.
    def _fattest_class() -> str | None:
        best = None
        for meta in _DESK_CLASSES:
            c = meta["class"]
            if sample[c] and (best is None or len(sample[c]) >= len(sample[best])):
                best = c
        return best
    _refresh_shown()
    while len(json.dumps(_payload(), ensure_ascii=False).encode("utf-8")) > _BYTE_CAP:
        c = _fattest_class()
        if c is None:
            break
        sample[c].pop()
        _refresh_shown()

    payload = _payload()
    # the TOP STRIP is built AFTER the flat rows exist (it resolves owed items to the rows
    # already built) and is bounded to the byte cap along with the rest.
    payload["top"] = _owed_top_rows(repo, payload["rows"])
    while len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > _BYTE_CAP:
        c = _fattest_class()
        if c is None:
            break
        sample[c].pop()
        _refresh_shown()
        payload = _payload()
        payload["top"] = _owed_top_rows(repo, payload["rows"])
    return payload


# ---------------------------------------------------------------------------
# THE BRIEF (W-DESK) — the desk's resting altitude under the one instrument. The desk
# joins engine.mjs: at rest the surface is NOT an inventory of eleven classes but a
# COMPOSED BRIEF of what needs HIM now — the genuinely-his rows (``project_state.
# owed_to_author``, the ``top`` strip) rendered as glances with the plain reason each
# needs him, plus one-line counts for every summonable class. Nothing is materialised
# until a chip (or a deep-link, B.5) summons it. A desk with nothing owed says so in one
# line and stays quiet — that is the feature, never a count-recital dressed as prose.
# ---------------------------------------------------------------------------
#: class -> the plain reason a row of that class needs HIM (delta-and-ask, never an
#: inventory label). Composed once; the brief reads it to say WHY, not just how many.
_WHY_HE_IS_NEEDED: dict[str, str] = {
    "adjudications": "a finding is waiting on your adjudication",
    "plan-ops": "a plan intent is drafted and waiting for your ratify or revoke",
    "forks": "an author-fork is open on your register — your ruling banks or contests it",
    "proxy-drafts": "the proxy ruled on its own; confirm, amend, or reject it before it stands",
    "lifts": "a dream-lift is proposed and awaits your authorization",
}


def _compose_his_glance(row: dict) -> tuple[str, str]:
    """ONE genuinely-his row composed for the brief: a legible glance (its already-composed
    title) plus the plain reason it needs him. Refs-only — no raw store id leaks into the
    glance (the row's title is the legible composition, the ids ride ``fields`` at depth)."""
    glance = (row.get("title") or row.get("context") or "").strip()
    # plain words at glance altitude: file paths and stamp noise mask to phrases (the
    # raw text stays in the opened referent), and truncation lands on a word.
    glance = re.sub(r"\(?[\w./-]+\.(?:json|jsonl|md|py|tex)\b[^)]*\)?", "the banked record", glance)
    glance = re.sub(r"\b\d{4}-\d{2}-\d{2}T[\d:]+\b", "", glance)
    glance = re.sub(r"\s{2,}", " ", glance).strip(" ,—-")
    if glance.endswith("…") and ". " in glance:
        # upstream truncation cut mid-word; the first sentence carries the glance.
        glance = glance.split(". ", 1)[0].rstrip(".") + "."
    elif len(glance) > 160:
        glance = glance[:160].rsplit(" ", 1)[0].rstrip(",;— ") + "…"
    cls = row.get("class") or ""
    # plan-ops intents carry machine-terse titles (plan-meta vocabulary); the glance
    # speaks plainly and the raw title stays behind the opened cockpit.
    if cls == "plan-ops" and glance.upper().startswith("RESPINE"):
        proj = (row.get("project") or row.get("corpus") or "").strip()
        on = f" on {proj}" if proj else ""
        glance = (f"a drafted respine{on} awaits your ratify or revoke — re-weight the "
                  "manuscript to lead on its ranked contribution")
    why = _WHY_HE_IS_NEEDED.get(cls, "this decision is yours to make")
    return glance, why


def _compose_brief_prose(his: list[dict], his_move: int, total: int, engine_n: int) -> str:
    """The desk brief, delta-and-ask (his charge 2026-07-22): compose what needs him now and
    why it matters — lead by NAMING the single most consequential owed decision (``his`` is
    pre-sorted by :func:`_consequence_rank`, so first IS most consequential — finding 5), then
    count how many others wait. A desk with nothing owed stays quiet: one plain line, never a
    recital of the eleven class counts pretending to be prose.

    ONE TRUTH (stranger-walk finding, banked leg F): quiet-or-not is gated on ``his_move`` —
    the count :func:`_desk` derives from the SAME direct class reads (``_desk_feedback``,
    ``_desk_forks``, ``_desk_proxy``, ``_desk_lifts``, plan-ops) that produce the per-class
    strata/chips the page renders below the banner. It is NOT gated on ``len(his)`` — the
    ``top`` strip is a second, independently-sourced join (``project_state.owed_to_author``
    per project) that can drift from the class reads and previously said "quiet" while an
    author-owed class chip sat right below it, nonzero, naming the very decision the banner
    denied. ``his`` still supplies the richer NAMED lead when the two agree; when ``his_move``
    is positive but the top strip failed to resolve a lead (the drift case itself), the brief
    still speaks truthfully from the count rather than falling back to "quiet"."""
    if not his_move:
        tail = (f" {engine_n} engine item{'s' if engine_n != 1 else ''} sit below for "
                "awareness, summonable when you want them." if engine_n else "")
        return "nothing needs you right now — your desk is quiet." + tail
    # NAME THE LEAD (finding 5): the brief's "most consequential first" is now BACKED by the
    # sort, so the prose leads with the top row's actual substance (its composed glance) —
    # never a fill-in-the-count template asserting an ordering the data did not perform.
    lead = (his[0].get("glance") or his[0].get("title") or "").strip().rstrip(" .—-") if his else ""
    n = his_move
    if not lead:
        # the top strip's join didn't resolve a name (the drift case) — the count is still
        # the truth the class reads back, so it leads instead of a fabricated glance.
        return (f"{n} decision{'s' if n != 1 else ''} need you — open the classes below to "
                "see them.")
    if n == 1:
        return f"one decision genuinely needs you today — {lead}."
    others = n - 1
    return (f"the decisions that need you — most consequential first: {lead}; "
            f"{others} more below, each opening to its cockpit in place.")


def _desk_brief(repo: Path) -> dict:
    """``GET /desk/brief`` — the composed resting altitude (W-DESK). Reuses the shared desk
    read-model (:func:`_desk`) for the genuinely-his ``top`` rows + the per-class counts,
    then MINTS the composed brief prose and each his-row's glance server-side (the client
    renders verbatim and reconstructs no meaning). The class chips carry counts + doors only
    — their rows never ride the brief; a chip (or a deep-link) materialises them on focus."""
    d = _desk(repo)
    top = d.get("top", [])
    strata = d.get("classes", [])
    his_move = d.get("his_move", 0)
    total = d.get("total", 0)
    engine_n = sum(c.get("count", 0) for c in strata if c.get("owner") != "him")
    his: list[dict] = []
    for r in top:
        glance, why = _compose_his_glance(r)
        his.append(dict(r, glance=glance, why=why))
    chips = [{"class": c["class"], "label": c["label"], "owner": c["owner"],
              "count": c.get("count", 0), "store": c.get("store", ""),
              "shown": c.get("shown", 0), "more": c.get("more", 0),
              "more_href": c.get("more_href")} for c in strata]
    return {
        "brief": {"glance": _compose_brief_prose(his, his_move, total, engine_n)},
        "his": his,
        "classes": chips,
        "his_move": his_move,
        "total": total,
        "engine_total": engine_n,
        "generated_ts": observe.now_iso(),
    }


# ---------------------------------------------------------------------------
# ZONE 1 — THE REFERENT: the full renderable CONTEXT for ONE row, fetched lazily so
# the list stays bounded while the cockpit shows the WHOLE document (never a
# truncation). Read fresh per request; law 8 — this DISPLAYS a source document as a
# document (content), it never derives state from markdown.
# ---------------------------------------------------------------------------
def _md_heading(text: str) -> str:
    """The first markdown heading (``# ...`` / ``## ...``) or the first non-blank line —
    the readable title of a source document."""
    for line in (text or "").splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            return s.lstrip("#").strip()
        return s[:120]
    return ""


def _doc_excerpt(body: str, needles: list[str], radius: int = 1400) -> dict:
    """The relevant EXCERPT of a source document, anchored to the finding (P6: context
    surfaces where the decision is made — never an 18KB dump the reader must hunt through).
    Locate the first non-trivial ``needle`` (the anchor quote, a section heading) in the body
    and return ``radius`` chars around it, ellipsised at the cuts; when nothing anchors, the
    doc's OPENING (heading + first ``radius`` chars). The WHOLE body still rides alongside
    (behind the cockpit's expand door), so nothing is lost — only the lead is focused."""
    body = body or ""
    for n in needles:
        n = (n or "").strip()
        if len(n) < 6:
            continue
        i = body.find(n)
        if i < 0:                                # try a distinctive leading fragment
            frag = n[:48].strip()
            i = body.find(frag) if len(frag) >= 8 else -1
        if i >= 0:
            start = max(0, i - radius // 4)
            end = min(len(body), i + radius)
            ex = body[start:end]
            return {"text": ("…" if start > 0 else "") + ex + ("…" if end < len(body) else ""),
                    "anchor": n, "anchored": True,
                    "whole": len(body) > len(ex)}
    head = body[:radius]
    return {"text": head + ("…" if len(body) > radius else ""),
            "anchor": "", "anchored": False, "whole": len(body) > len(head)}


def _feedback_source_doc(md: Path, finding: dict) -> dict | None:
    """The verbatim source document a finding was relayed from (``feedback/sources/*.md`` or
    a ``feedback/*.md`` desk-review), rendered readable (heading + body). Resolved from the
    finding's ``source_doc``/``doc`` ref when present, else the NEWEST feedback source md —
    the chair's fix: the ruling reads the document from where the ruling happens.

    ``resolved`` is True only when the doc came from the finding's OWN ref — the caller leads
    with the anchored excerpt either way, but a fallback doc (the newest md, not this
    finding's) is labelled as such so it never masquerades as the finding's document."""
    fb = md / "feedback"
    if not fb.is_dir():
        return None
    ref = (finding.get("source_doc") or finding.get("doc") or "").strip()
    cand: Path | None = None
    resolved = False
    if ref:
        p = (fb / ref) if not ref.startswith("/") else Path(ref)
        try:
            p = p.resolve()
            p.relative_to(md.resolve())          # containment fence
            if p.is_file():
                cand = p
                resolved = True
        except (ValueError, OSError):
            cand = None
    if cand is None:
        mds = sorted(list((fb / "sources").glob("*.md")) if (fb / "sources").is_dir() else [])
        mds += sorted(fb.glob("*.md"))
        cand = mds[-1] if mds else None
    if cand is None:
        return None
    try:
        body = cand.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        rel = cand.resolve().relative_to(_REPO_ROOT.resolve()).as_posix()
    except (ValueError, OSError):
        rel = cand.name
    return {"path": rel, "heading": _md_heading(body), "body": body, "resolved": resolved}


def _finding_lead(finding: dict) -> tuple[str, str]:
    """The finding's OWN text — the LEAD of the anchored context (finding 6: the ruling
    reads what it rules, not an unanchored source dump). Returns ``(lead_text, directive)``:
    for a projection-intent, the plan directive (``verb object``) + its note; for an
    adjudication, the note body (``text``/``comment``). Either may be empty — a bare row,
    stated plainly and never fabricated."""
    if not finding:
        return "", ""
    if finding.get("record") == "projection-intent":
        obj = finding.get("object") or {}
        key = (obj.get("sid") or obj.get("key") or "").strip()
        kind = (obj.get("kind") or "").strip()
        object_ref = f"{kind}:{key}" if key else kind
        directive = " ".join(p for p in ((finding.get("verb") or "").strip(), object_ref) if p)
        note = (finding.get("payload") or {}).get("note") or ""
        return (note or directive), directive
    return (finding.get("text") or finding.get("comment") or ""), ""


def _adjudication_referent(project: str, rid: str, fields: dict) -> dict:
    """The full CONTEXT for an adjudication / plan-op row, ANCHORED to the finding (P6): the
    finding's OWN text leads, then the passage he marked, the manuscript prose its node
    concerns, and the source document as an anchored EXCERPT (the whole rides alongside for
    the cockpit's expand door). The exact ledger row rides at audit depth."""
    from laplace.manuscript import review_surface as _rs
    md = _rs.manuscript_dir(project, "")
    anchor_in = fields if isinstance(fields, dict) else {}
    zones: dict[str, Any] = {"anchor": {"node": anchor_in.get("node") or "",
                                        "section": anchor_in.get("section") or ""}}
    if md is None:
        zones["error"] = f"could not resolve the manuscript for {project!r}"
        return zones
    ledger = md / "feedback" / "feedback.jsonl"
    recs = read_jsonl(ledger) if ledger.is_file() else []
    finding = next((r for r in recs if str(r.get("id")) == str(rid)), None)
    zones["ledger_row"] = finding
    lead, directive = _finding_lead(finding or {})
    zones["finding_text"] = lead
    if directive:
        zones["intent_directive"] = directive
    # the passage he marked (the annotate door stamps the highlighted quote on anchor.text) —
    # the exact substance of the note, the anchor the source excerpt is composed around.
    anchor = (finding or {}).get("anchor") or {}
    marked = (anchor.get("text") or "").strip()
    section = (fields.get("section") or anchor.get("section") or "").strip()
    if marked:
        zones["marked_passage"] = marked
    node = (fields.get("node") or (finding or {}).get("node_id")
            or (finding or {}).get("node") or "").strip()
    if node:
        try:
            zones["node_text"] = (_rs._node_text_map(md) or {}).get(node, "")
        except Exception:  # noqa: BLE001
            zones["node_text"] = ""
    sd = _feedback_source_doc(md, finding or {})
    if sd:
        # ANCHOR THE DUMP (finding 6): the source doc rides as the excerpt around the finding
        # (the marked quote / the section / the node), the whole body kept for the expand door.
        sd["excerpt"] = _doc_excerpt(sd.get("body") or "",
                                     [marked, section, node, directive])
    zones["source_doc"] = sd
    return zones


def _forks_referent(rid: str) -> dict:
    """REFERENTS WHOLE (E3): the FULL fork row — never the desk row's truncated
    title/context. Searches BOTH fork homes ``_desk_forks`` joins: the typed
    OPEN_STACK store (full title + trigger + refs) and any ``corpus_friction/*.jsonl``
    ``kind:"fork"`` record (the D16 rule-in-place mouth's own rows)."""
    for f in _load_open_stack_forks(_REPO_ROOT):
        if str(f.get("id") or "") == str(rid):
            return {"fork": f, "id": rid}
    d = _REPO_ROOT / "corpus_friction"
    if d.is_dir():
        for led in sorted(d.glob("*.jsonl")):
            for r in read_jsonl(led):
                if r.get("kind") == "fork" and str(r.get("id") or "") == str(rid):
                    return {"fork": r, "id": rid, "source": led.stem}
    return {"error": f"no fork {rid!r} in the OPEN_STACK store or any corpus_friction "
                     "ledger (resolved, parked, or renamed since the desk read it)",
            "id": rid, "class": "forks"}


#: the ONE work-order whose referent opens a RENDERED profile, not just its ledger row.
_ARCH_PROFILE_ACTION = "author-confirm-architecture-profile"
_ARCH_PROFILE_YAML = "profiles/author_architecture.yaml"
_ARCH_PROFILE_ROUTE = "/desk/architecture-profile"


def architecture_profile_render(repo: Path) -> dict:
    """Compose ``profiles/author_architecture.yaml`` into a READABLE render (Part 2, W-CRAP).

    His charge, 2026-07-22: *"how am I supposed to see this profile"* — the profile is typed
    data with no surface; a profile nothing renders is a prose doc that rots. This is the
    smallest faithful render, composed per the composition law: each field's SUMMARY is the
    prose at glance; its EVIDENCE (store sources + the measured observation) rides behind a
    door, never the foreground. Personal confirmation resolves through the same
    exact decision-backed loader used by planners. Older prose assertions remain
    visible historical claims; they do not mint new authority. Editing and
    candidate application belong to the guarded profile owner.
    """
    from laplace.pipeline import narrative
    observed = narrative.architecture_status(repo, include_content=True)
    if observed['status'] != 'AVAILABLE':
        return {'error': observed['reason'], 'profile_status': observed}
    path = repo / _ARCH_PROFILE_YAML
    try:
        data = narrative.architecture_document(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return {"error": f"author-architecture profile unreadable: {e}"}

    status = str(data.get("status") or "").strip()
    reconstructed = "RECONSTRUCTED" in status.upper()

    fields: list[dict] = []
    for key, blk in (data.get("profile") or {}).items():
        if not isinstance(blk, dict):
            continue
        summary = (blk.get("summary") or "").strip()
        ev = blk.get("evidence") or {}
        authority = observed['fields'].get(key) or {}
        fields.append({
            "key": key,
            "name": str(key).replace("_", " "),
            "summary": summary,
            "his": bool(authority.get('confirmed_his')),
            "historical_confirmation_assertion": bool(authority.get('historical_confirmation_assertion')),
            "author_confirmation": authority.get('author_confirmation'),
            "evidence": {
                "sources": list(ev.get("sources") or []),
                "observation": (ev.get("observation") or "").strip(),
            },
        })

    au = data.get("authorship") or {}
    return {
        "route": _ARCH_PROFILE_ROUTE,
        "title": "Gerard McCaul — paper architecture profile",
        "author": data.get("author") or "Gerard McCaul",
        "version": data.get("version") or "",
        "status": status,
        "reconstructed": reconstructed,
        "his_correction_count": sum(1 for f in fields if f["his"]),
        "fields": fields,
        "consumes": [
            {"stage": c.get("stage"), "use": (c.get("use") or "").strip()}
            for c in (data.get("consumes") or []) if isinstance(c, dict)
        ],
        "derived_from": [
            {"source": d.get("source"), "scope": d.get("scope")}
            for d in (data.get("derived_from") or []) if isinstance(d, dict)
        ],
        "authorship": {
            "first_author_lead": list(au.get("first_author_lead") or []),
            "co_authored_excluded": list(au.get("co_authored_excluded") or []),
        },
        "gaps": [
            {"id": g.get("id"), "note": (g.get("note") or "").strip()}
            for g in (data.get("gaps") or []) if isinstance(g, dict)
        ],
    }


def _lift_referent(slug: str) -> dict:
    """The FULL dream-lift proposal for one slug (finding 1): the coherence judgment's
    essence + why, the region it lifts, its members, and the coherent flag — everything the
    authorize/refuse ruling reads, composed IN the cockpit so the decision is decide-in-
    seconds. Re-reads the newest ``dream_lifts_*.json`` (the same store ``_desk_lifts``
    sampled); a slug that has left the manifest renders its plain absence, never ``{}``."""
    p = _newest_dream_lifts(_REPO_ROOT)
    if p is None:
        return {"error": "no dream-lift manifest in corpus_friction (nothing proposed)",
                "id": slug, "class": "lifts"}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return {"error": f"dream-lift manifest unreadable: {e}", "id": slug, "class": "lifts"}
    for prop in d.get("proposals") or []:
        if (prop.get("proposed_slug") or "") != slug:
            continue
        j = prop.get("judgment") if isinstance(prop.get("judgment"), dict) else {}
        return {"lift": {
            "slug": slug,
            "region": prop.get("region") or "",
            "essence": (j.get("essence") or "").strip(),
            "why": (j.get("why") or "").strip(),
            "parent_hint": (j.get("parent_hint") or "").strip(),
            "coherent": _lift_coherent(prop),
            "members": list(prop.get("members") or []),
            "orphan_members": prop.get("orphan_members"),
            "assessor_coherence": prop.get("assessor_coherence"),
            "date": d.get("date") or "",
        }, "id": slug}
    return {"error": f"no dream-lift {slug!r} in the current manifest (authorized, refused, "
                     "or re-proposed since the desk read it)", "id": slug, "class": "lifts"}


def _friction_referent(rid: str, project: str) -> dict:
    """The FULL open-friction record for one id (finding 2): the friction's row and the
    surface it was found on, so the resolve decision reads what it resolves. Searches the
    project's ledger first, then every ``corpus_friction/*.jsonl`` — a live (open) row only."""
    d = _REPO_ROOT / "corpus_friction"
    if d.is_dir():
        cands = ([d / f"{project}.jsonl"] if project else []) + sorted(d.glob("*.jsonl"))
        seen: set[Path] = set()
        for led in cands:
            if led in seen or not led.is_file():
                continue
            seen.add(led)
            for r in open_frictions(read_jsonl(led)):
                if r.get("kind") == "fork":
                    continue
                if str(r.get("id")) == str(rid):
                    return {"friction": r, "id": rid, "surface": led.stem}
    return {"error": f"no open friction {rid!r} in any corpus_friction ledger (resolved "
                     "or superseded since the desk read it)", "id": rid, "class": "open-frictions"}


def _cluster_referent(fields: dict) -> dict:
    """The member WITNESSES of one recurrence cluster (finding 2): every open friction
    sharing the cluster's recurring root (``group_kind`` + ``group_prefix``), so the
    resolve-cluster decision reads the whole set one evidence-carrying resolution retires."""
    gk = (fields.get("group_kind") or "").strip()
    gp = (fields.get("group_prefix") or "").strip()
    if not (gk and gp):
        return {"error": "no cluster root on this row (group_kind + group_prefix absent)",
                "class": "recurrence-clusters"}
    members: list[dict] = []
    d = _REPO_ROOT / "corpus_friction"
    if d.is_dir():
        for led in sorted(d.glob("*.jsonl")):
            for r in open_frictions(read_jsonl(led)):
                if r.get("kind") == "fork":
                    continue
                if _fc._group_key(r) != (gk, gp):
                    continue
                members.append({"id": r.get("id"), "node": r.get("node") or "",
                                "value": _fc._one_line(r), "surface": led.stem})
    return {"cluster": {"heading": _fc._group_heading((gk, gp)), "kind": gk, "prefix": gp,
                        "members": members}, "id": _fc._group_heading((gk, gp))}


def _holdout_referent(rid: str) -> dict:
    """The pending holdout PREDICTION (finding 2): the mechanical checks scoring at the next
    session (id + what each expects) and the count of behavioral claims — behavioral IDS
    ONLY, never the claim text (the covenant: reading the claims early breaks his blindness).
    The banked note + session context lead, so the score decision reads what it will run."""
    try:
        from laplace.engine import holdout
        pend = holdout.load_pending(_REPO_ROOT)
    except Exception as e:  # noqa: BLE001
        return {"error": f"holdout referent unavailable: {e}", "id": rid, "class": "holdout"}
    if not pend:
        return {"error": "no pending holdout prediction to score (nothing banked)",
                "id": rid, "class": "holdout"}
    mech = pend.get("mechanical") or []
    beh = pend.get("behavioral") or []
    return {"holdout": {
        "note": (pend.get("note") or "").strip(),
        "session": (pend.get("session") or "").strip(),
        "banked": pend.get("banked") or "",
        "mechanical": [{"id": m.get("id") or "", "expect": m.get("expect") or "",
                        "cmd": m.get("cmd") or ""} for m in mech],
        # BLINDNESS COVENANT: ids only — the claim text is withheld until the score.
        "behavioral_ids": [b.get("id") or "" for b in beh],
        "behavioral_n": len(beh),
    }, "id": rid}


def _referent(cls: str, project: str, rid: str, fields: dict) -> dict:
    """ONE row's full referent, per class. Adjudications + plan-ops render the finding /
    intent + its source document + the manuscript prose; work-orders + forks their FULL
    ledger row (what/why/fix/blocks; title/trigger/refs) — never the bounded wake handle
    or the desk row's own truncated fields; lifts the FULL proposal (essence/region/members),
    frictions/clusters their live records, holdout its pending prediction. A class with no
    richer referent renders the row's own fields (never a crash, never a lie)."""
    if cls in ("adjudications", "plan-ops"):
        return _adjudication_referent(project, str(rid), fields or {})
    if cls == "work-orders":
        # REFERENTS WHOLE (E3): the wake's handle (``open_work_order_handles``) caps
        # ``what`` at 90 chars and drops ``why``/``fix``/``blocks``/``blocked_by``
        # entirely — read the store DIRECTLY for the whole banked row instead.
        try:
            from laplace.manuscript import storyboard as _sb
            row = next((r for r in _sb.load_work_orders(_REPO_ROOT)
                        if engine_ledger.is_work_order(r) and str(r.get("id")) == str(rid)),
                       None)
            if row is None:
                return {"error": f"no open work-order {rid!r} in the store "
                                 "(consumed, or renamed since the desk read it)",
                        "id": rid, "class": cls}
            out = {"work_order": row, "id": rid}
            # THE PROFILE MADE VISIBLE (Part 2, W-CRAP): the confirm-architecture-profile
            # order's referent OPENS the rendered profile inline — his charge "how am I
            # supposed to see this profile". Its own ledger row still renders above; the
            # composed view is the altitude the confirm decision is made at.
            if (row.get("action") == _ARCH_PROFILE_ACTION
                    or str(row.get("artifact") or "").endswith("author_architecture.yaml")):
                out["architecture_profile"] = architecture_profile_render(_REPO_ROOT)
                out["architecture_profile_href"] = _ARCH_PROFILE_ROUTE
            return out
        except Exception as e:  # noqa: BLE001
            return {"error": f"work-order referent unavailable: {e}", "id": rid}
    if cls == "forks":
        return _forks_referent(str(rid))
    if cls == "release-states":
        row = next((r for r in registry.project_states(_REPO_ROOT)
                    if (r.get("name") or "") == project), None)
        return {"release_state": row, "project": project}
    if cls == "proxy-drafts":
        # ZONE 1 for a proxy draft: the adjudicator's OWN output, whole — the question it
        # ruled on, its ruling, the reasoning/evidence it stood on, its confidence and date.
        # This is what makes confirm/amend/reject a decide-in-seconds call, not a guess.
        try:
            from laplace.engine import author_proxy
            v = next((r for r in author_proxy.load_verdicts(_REPO_ROOT)
                      if str(r.get("id")) == str(rid)), None)
        except Exception as e:  # noqa: BLE001
            return {"error": f"proxy verdict referent unavailable: {e}", "id": rid, "class": cls}
        if v is None:
            return {"error": f"no proxy verdict {rid!r} in the ledger (resolved or superseded)",
                    "id": rid, "class": cls}
        return {"proxy_verdict": v, "id": rid}
    if cls == "lifts":
        return _lift_referent(str(rid))
    if cls == "open-frictions":
        return _friction_referent(str(rid), project or "")
    if cls == "recurrence-clusters":
        return _cluster_referent(fields or {})
    if cls == "holdout":
        return _holdout_referent(str(rid))
    # stale-reads: the row's own fields ARE the derived-read record the store surfaced
    # (label + reason → fix), which the cockpit renders plainly — no richer store behind it.
    return {"record": fields or {}, "id": rid, "class": cls,
            "note": "this class carries no richer referent — the row's own record is the whole of it"}


# ---------------------------------------------------------------------------
# THE ONE MUTATION DOOR (``POST /desk/act``). Every verb is a THIN DISPATCH to an
# EXISTING executor — never new mutation logic. This module owns NO write machinery.
# ---------------------------------------------------------------------------
#: the AUTHORING verbs — those whose write carries HIS WORDS (a ruling / an objection), so
#: the door refuses an empty authored record (PV the-ruling-needs-a-composer). A verb that
#: writes no words (consume, ratify, confirm-affirm) is NOT here — its bare armed door is
#: correct. The cockpit renders each of these as a COMPOSER, never a bare confirm.
_AUTHORING_VERBS: frozenset[tuple[str, str]] = frozenset({
    ("forks", "bank-ruling"), ("forks", "contest-ruling"), ("proxy-drafts", "reject"),
})


_DEFERRED_VERBS: dict[tuple[str, str], str] = {
    ("release-states", "run"): "W6 — the /pipeline run panel owns the launch door",
    ("release-states", "resume"): "W6 — the /pipeline run panel owns the launch door",
    ("stale-reads", "rebuild"): "engine-owned: the PSU law names the fix, a click never fires a rebuild",
    ("proxy-drafts", "amend"): "the /artefact compose door writes the replacement ruling (a client-side compose link, never a blind POST)",
}


def _dispatch_desk_verb(cls: str, verb: str, payload: dict, by: str) -> dict | None:
    """Route one (class, verb) to its EXISTING executor and return the executor's own result
    dict, or ``None`` when the verb is NAMED but not wired this wave (the caller maps None →
    a fail-closed 422). No write happens here — every append is the executor's."""
    if cls in ("adjudications", "plan-ops"):
        from laplace.manuscript import review_surface as _rs
        corpus = (payload.get("project") or payload.get("corpus") or "").strip()
        dir_param = (payload.get("dir") or "").strip()
        md = _rs.manuscript_dir(corpus, dir_param)
        if md is None:
            return {"error": f"unknown project/corpus {corpus!r} — must resolve "
                             "inside the repo root", "class": cls, "verb": verb}
        project = _rs._project_name(corpus, md)

        if verb == "ratify":
            from laplace.pipeline import evolution_consumer as _ec
            res = _ec.apply_plan_proposals(md, corpus, by=by)
            if res.get("error"):
                return {"ok": False, "verb": verb, "class": cls, "error": res["error"]}
            applied = res.get("applied") or []
            return {"ok": True, "verb": verb, "class": cls,
                    "applied": applied, "needs_author": res.get("needs_author") or [],
                    "ledger": res.get("ledger"),
                    "idempotent": len(applied) == 0}

        # every other verb of these two classes is an adjudicate verb, VERBATIM.
        ap = dict(payload)
        ap["by"] = by
        return _rs.adjudicate(md, project, ap)

    if cls == "proxy-drafts" and verb in ("confirm", "reject"):
        from laplace.engine import author_proxy
        target = (payload.get("target") or payload.get("id") or "").strip()
        if not target:
            return {"ok": False, "class": cls, "verb": verb,
                    "error": "target required (the proxy verdict id to rule on)"}
        if verb == "reject":
            # HIS OBJECTION, NOT A DEFAULT (PV the-ruling-needs-a-composer): reject banks his
            # words (guarded non-empty at the door above) — never a silent "rejected on the desk".
            reason = (payload.get("ruling") or payload.get("reason") or "").strip()
            rec = author_proxy.contest_ruling(_REPO_ROOT, target, reason=reason, by=by)
        else:
            rec = author_proxy.confirm_ruling(
                _REPO_ROOT, target, reason=payload.get("reason") or "", by=by)
        return {"ok": True, "class": cls, "verb": verb, "target": target, "record": rec}

    if cls == "work-orders" and verb == "consume":
        from laplace.manuscript import storyboard as _sb
        order_id = (payload.get("id") or payload.get("target")
                    or payload.get("order_id") or "").strip()
        if not order_id:
            return {"ok": False, "class": cls, "verb": verb,
                    "error": "id required (the work-order to consume)"}
        _st, obj = _sb.resolve_work_order(
            order_id,
            evidence_refs=payload.get("evidence_refs") or payload.get("evidence"),
            by=by, reason=payload.get("reason") or "")
        return obj

    if cls == "forks" and verb in ("bank-ruling", "contest-ruling"):
        fork_id = (payload.get("id") or payload.get("target") or "").strip()
        if not fork_id:
            return {"ok": False, "class": cls, "verb": verb,
                    "error": "id required (the fork to rule)"}
        disposition = "banked" if verb == "bank-ruling" else "contested"
        # THE RULING'S SUBSTANCE (PV the-ruling-needs-a-composer): an authoring verb banks
        # HIS WORDS — the ruling text (guarded non-empty at the door above), his optional
        # quick-choice, and any commentary. ``reason`` mirrors the ruling for back-compat.
        ruling = (payload.get("ruling") or payload.get("reason") or "").strip()
        rec = {"id": _ruling_id("FR", fork_id), "kind": "fork-ruling",
               "rules": fork_id, "verb": verb, "disposition": disposition,
               "ruling": ruling, "choice": (payload.get("choice") or "").strip(),
               "commentary": (payload.get("commentary") or "").strip(),
               "reason": ruling, "by": by, "ts": observe.now_iso()}
        # append-only into the OPEN_STACK store the desk reader reconciles through
        # open_stack_store.ruled_fork_ids (the F39 one-truth reader); the fork retires off
        # the desk without a line edit (the proxy confirm/contest idiom).
        append_jsonl(_REPO_ROOT / open_stack_store.STORE_REL, rec)
        return {"ok": True, "class": cls, "verb": verb, "fork": fork_id,
                "disposition": disposition, "record": rec}

    if cls == "lifts" and verb in ("authorize", "refuse"):
        slug = (payload.get("id") or payload.get("target") or "").strip()
        if not slug:
            return {"ok": False, "class": cls, "verb": verb,
                    "error": "id required (the lift slug to rule)"}
        disposition = "authorized" if verb == "authorize" else "refused"
        rec = {"id": _ruling_id("LR", slug), "kind": "lift-ruling", "rules": slug,
               "region": (payload.get("region") or "").strip(), "verb": verb,
               "disposition": disposition, "reason": payload.get("reason") or "",
               "by": by, "ts": observe.now_iso()}
        append_jsonl(_REPO_ROOT / _LIFT_RULINGS_REL, rec)
        return {"ok": True, "class": cls, "verb": verb, "lift": slug,
                "disposition": disposition, "record": rec}

    if cls == "open-frictions" and verb == "resolve":
        target = (payload.get("id") or payload.get("target") or "").strip()
        project = (payload.get("project") or "").strip()
        evidence = payload.get("evidence") or payload.get("reason") or ""
        if not target:
            return {"ok": False, "class": cls, "verb": verb,
                    "error": "id required (the friction to resolve)"}
        try:
            res = _fc.make_friction_resolution(
                target, evidence=str(evidence), verb="resolved", actor=by,
                project=project or "laplace_engine")
        except ValueError as e:                       # evidence-less → refused, target OPEN
            return {"ok": False, "class": cls, "verb": verb,
                    "error": str(e), "still_open": True}
        led = _REPO_ROOT / "corpus_friction" / f"{project}.jsonl"
        append_jsonl(led, res)
        return {"ok": True, "class": cls, "verb": verb, "resolved": target,
                "ledger": _rel_to_repo(led, _REPO_ROOT), "resolution": res}

    if cls == "recurrence-clusters" and verb == "resolve-cluster":
        gk = (payload.get("group_kind") or "").strip()
        gp = (payload.get("group_prefix") or "").strip()
        evidence = payload.get("evidence") or payload.get("reason") or ""
        if not (gk and gp):
            return {"ok": False, "class": cls, "verb": verb,
                    "error": "group_kind + group_prefix required (the cluster's recurring root)"}
        if not str(evidence).strip():
            return {"ok": False, "class": cls, "verb": verb,
                    "error": "evidence required: resolving a cluster retires each witness "
                             "(an evidence-less resolution leaves them OPEN)", "still_open": True}
        resolved: list[str] = []
        d = _REPO_ROOT / "corpus_friction"
        if d.is_dir():
            for led in sorted(d.glob("*.jsonl")):
                recs = read_jsonl(led)
                for r in open_frictions(recs):
                    if r.get("kind") == "fork":
                        continue
                    if _fc._group_key(r) != (gk, gp):
                        continue
                    res = _fc.make_friction_resolution(
                        r["id"], evidence=str(evidence), verb="resolved-cluster",
                        actor=by, project=led.stem)
                    append_jsonl(led, res)
                    resolved.append(r["id"])
        return {"ok": True, "class": cls, "verb": verb, "resolved": resolved,
                "n": len(resolved), "idempotent": len(resolved) == 0}

    if cls == "holdout" and verb == "score":
        from laplace.engine import holdout as _ho
        scored = _ho.score_mechanical(_REPO_ROOT)
        if not scored:
            return {"ok": False, "class": cls, "verb": verb,
                    "error": "no pending holdout prediction to score"}
        # THE ARCHIVE IS NOT FREE (WO-20260817-holdout-scores-deposit, the thin-systems audit
        # 2026-08-17): archive() UNLINKS the pending prediction, so calling it with an empty
        # behavioral_scores settles the behavioral half UNREAD - the claims the author banked
        # are cleared off the desk having been scored by nobody. This verb used to hardcode
        # behavioral_scores=[] and always archive. Now the mechanical half always runs and is
        # deposited (holdout/LAST_SCORE.json, which the close reads), and the archive happens
        # only when the caller actually carries behavioral scores. Refusing is the honest
        # outcome, not an error: the scorecard still returns, the prediction simply stays open.
        behavioral = payload.get("behavioral_scores") or []
        if not isinstance(behavioral, list) or not behavioral:
            return {"ok": True, "class": cls, "verb": verb, "scored": scored,
                    "archive": None, "archived": False, "still_open": True,
                    "refused": "archive refused: no behavioral_scores supplied. Archiving "
                               "unlinks the pending prediction, and its behavioral claims "
                               "would be settled unread. The mechanical scorecard above ran "
                               "and is banked at holdout/LAST_SCORE.json; pass "
                               "behavioral_scores to settle the prediction."}
        out_path = _ho.archive(_REPO_ROOT, behavioral_scores=behavioral)
        return {"ok": True, "class": cls, "verb": verb, "scored": scored, "archived": True,
                "archive": _rel_to_repo(out_path, _REPO_ROOT) if out_path else None}

    return None                                       # NAMED but not wired this wave


def _desk_act(body: bytes) -> tuple[int, str, bytes]:
    """``POST /desk/act`` — the one mutation door. Validate the class + verb against the
    authored roster, apply the actor guard (an unattributed write is refused BEFORE any
    executor, 422, zero delta), then dispatch to the existing executor. A NAMED-but-unwired
    verb is a fail-closed 422 naming where its door lands."""
    try:
        payload = json.loads(body or b"{}")
    except (ValueError, TypeError):
        return _json_resp(400, {"error": "bad json"})
    if not isinstance(payload, dict):
        return _json_resp(400, {"error": "body must be a json object"})

    cls = (payload.get("class") or "").strip()
    verb = (payload.get("verb") or "").strip()
    if cls not in _CLASS_VERBS:
        return _json_resp(422, {"error": f"unknown desk class {cls!r}",
                                "classes": sorted(_CLASS_VERBS)})
    if verb not in _CLASS_VERBS[cls]:
        return _json_resp(422, {"error": f"{verb!r} is not a verb of class {cls!r}",
                                "verbs": _CLASS_VERBS[cls]})

    by = (payload.get("by") or "").strip()
    if not by:
        return _json_resp(422, {"error": "by (explicit actor) is required: desk "
                                "acts are actor-attributed and this door defaults "
                                "nowhere — an unattributed request must never write"})

    # THE AUTHORING GUARD (PV the-ruling-needs-a-composer): a verb that banks HIS WORDS is
    # refused when those words are empty — the same fail-closed idiom as the actor guard
    # (422, zero delta, BEFORE any executor). An authoring act without an authored substance
    # is a wordless ruling record; the cockpit's composer supplies the words, this closes the
    # hole for any direct caller. Verbs that write no words (consume, ratify) never reach here.
    if (cls, verb) in _AUTHORING_VERBS:
        authored = (payload.get("ruling") or payload.get("reason") or "").strip()
        if not authored:
            return _json_resp(422, {
                "error": f"an authoring {verb!r} must carry your words: this door banks a "
                         "ruling record and refuses an empty one — compose the ruling's "
                         "substance before firing (the cockpit's composer supplies it)",
                "class": cls, "verb": verb, "needs": "ruling"})

    res = _dispatch_desk_verb(cls, verb, payload, by)
    if res is None:
        return _json_resp(422, {"error": f"the {verb!r} door for class {cls!r} is "
                                "not wired this wave", "class": cls, "verb": verb,
                                "deferred_to": _DEFERRED_VERBS.get((cls, verb),
                                                                   "a later wave")})
    return _json_resp(200 if res.get("ok") else 422, res)


# ---------------------------------------------------------------------------
# the HTTP handler (analytics / dials contract): GET reads, the ONE act POST.
# ---------------------------------------------------------------------------
def handle(path: str, query: dict, method: str,
           body: bytes) -> tuple[int, str, bytes] | None:
    """Route one ``/desk*`` request. Returns (status, content_type, body) or ``None`` when
    the path is not ours — the bare ``GET /desk`` page is served by the scanner (mirrors
    the other apps). READ-ONLY except the one act door (``POST /desk/act``): every other
    path is GET-only and POST is 405."""
    if path != "/desk" and not path.startswith("/desk/"):
        return None
    method = (method or "GET").upper()

    if path == "/desk/act":
        if method != "POST":
            return _json_resp(405, {"error": f"{method} not allowed — desk acts are POST /desk/act"})
        return _desk_act(body)

    if method != "GET":
        return _json_resp(405, {"error": f"{method} not allowed — /desk is read-only"})

    if path == "/desk/data":
        try:
            return _json_resp(200, _desk(_REPO_ROOT))
        except Exception as e:  # a substrate hiccup is a 500, never a crash
            return _json_resp(500, {"error": f"desk assembly failed: {e}"})

    if path == "/desk/brief":
        # THE BRIEF (W-DESK): the desk's resting altitude under the one instrument — the
        # composed what-needs-him-now + one-line class counts (the client materialises a
        # class or pre-pins a deep-linked row from here, never a wall of eleven panes).
        try:
            return _json_resp(200, _desk_brief(_REPO_ROOT))
        except Exception as e:  # noqa: BLE001
            return _json_resp(500, {"error": f"desk brief assembly failed: {e}"})

    if path == _ARCH_PROFILE_ROUTE:
        # THE PROFILE MADE VISIBLE (Part 2, W-CRAP): the composed, readable render of
        # profiles/author_architecture.yaml. A real served view (the desk more_href idiom)
        # so the work-order referent's door and any direct read reach the SAME composition.
        try:
            return _json_resp(200, architecture_profile_render(_REPO_ROOT))
        except Exception as e:  # noqa: BLE001
            return _json_resp(500, {"error": f"architecture-profile render failed: {e}"})

    if path == "/desk/class":
        cls = _q1(query, "class")
        if cls not in _CLASS_VERBS:
            return _json_resp(422, {"error": f"unknown desk class {cls!r}",
                                    "classes": sorted(_CLASS_VERBS)})
        try:
            offset = max(0, int(_q1(query, "offset") or "0"))
        except (ValueError, TypeError):
            offset = 0
        try:
            return _json_resp(200, _desk_class(_REPO_ROOT, cls, offset))
        except Exception as e:  # noqa: BLE001
            return _json_resp(500, {"error": f"desk class view failed: {e}"})

    if path == "/desk/referent":
        cls = _q1(query, "class")
        if cls not in _CLASS_VERBS:
            return _json_resp(422, {"error": f"unknown desk class {cls!r}",
                                    "classes": sorted(_CLASS_VERBS)})
        try:
            fields = json.loads(_q1(query, "fields") or "{}")
            if not isinstance(fields, dict):
                fields = {}
        except (ValueError, TypeError):
            fields = {}
        # a referent needs the row's node/kind/section — accept them flat too (the cockpit
        # rides the row's own `fields` straight in, so a missing field is honest emptiness).
        # region (lifts) + group_kind/group_prefix (clusters) + target ride here too, so the
        # cluster/lift referents receive the door-ready fields the row spread flat.
        for k in ("node", "kind", "section", "finding_id", "supersedes",
                  "region", "group_kind", "group_prefix", "target"):
            v = _q1(query, k)
            if v and k not in fields:
                fields[k] = v
        try:
            return _json_resp(200, _referent(cls, _q1(query, "project"),
                                             _q1(query, "id"), fields))
        except Exception as e:  # noqa: BLE001
            return _json_resp(500, {"error": f"referent assembly failed: {e}"})

    if path == "/desk":
        return None                                    # bare page served by the scanner

    return _json_resp(404, {"error": f"no desk route {path!r}"})
