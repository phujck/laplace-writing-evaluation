"""THE DASHBOARD (surface 1) — THE JOB's home, served at ``/``.

His words, verbatim (the rubric): *"just, we need a dashboard that can handle all
of this, show the different projects, how they're progressing etc. and make making
a new one and fiddling with any part of a current one easy"*.

One READ door and one WRITE door, the scanner-dispatch ``handle(path, query, method,
body)`` idiom (mirrors ``guide`` / ``dials_surface``); the bare ``GET /`` page is served
by the scanner, and :func:`handle` returns ``None`` for it (foreign paths fall through):

  * ``GET  /dashboard/data``  — the project CARDS' one fetch: :func:`registry.project_states`
                                (the inventory authority) ENRICHED per card with the openable
                                artefact deep-link, compact per-project staleness chips carrying
                                platform-normalized fix OFFERS (offer-never-fire), the scaffold
                                flag (NEVER_RUN ≠ live paper), and the one next action. Bounded
                                to the 16KB first-paint law (only DEGRADED per-corpus staleness
                                reads ride; the global engine reads are not repeated per card).
  * ``POST /dashboard/new``   — The new project door (J6): {name, template} → the scaffold
                                BANKED on disk (project dirs, the conceptric seed ledger, the
                                projection_plan skeleton, the ``registry_projects.json`` data
                                row) with the heavy steps (first compile, embeddings) banked as
                                WORK ORDERS (offer law) — never fired inline. Validates the name
                                (slug-safe, path-safe, no registry collision) before it writes.

DASHBOARD LAW (conception §3, judge amendment 5): this surface renders only live
project state and doors — no explanatory copy — so it cannot regress into the killed
"landing" meta-surface. That law binds the HTML; this module only serves the state.

HONESTY: ``decisions-awaiting`` is OMITTED, not faked — the desk join is heavy and the
roster stays a cheap read (the registry's own ruling, kept here); ``staleness`` is plain
per-corpus reads, never a fabricated verdict; an artefact door is offered ONLY when
``/review`` can actually open it (a dead door is never offered as live).

The openable-door gate (W1 amendment A1 → W2 UNIFICATION): the ``open latest`` door is
gated on what the ARTEFACT surface can ACTUALLY render, resolved through the one
server-canonical authority — ``registry.project_context`` (W2). The W1 shim probed
``/review``'s own resolver (``review_surface.manuscript_dir`` → the plan's ``target_dir``),
which read the wrong root; W2 folded ``/review`` + ``/projection`` into ``/artefact`` on
``project_context``, so this shim collapsed to that one authority and the door now deep-links
``/artefact?corpus=<name>``. Projects whose real pdf the ``target_dir`` could not reach in
W1 (law-of-laws) now resolve through ``project_context`` and their door Plainly ENABLES.
"""
from __future__ import annotations
from laplace.core.checkout import source_tree

import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from laplace.core import process as core_process
from laplace.pipeline import project_state, registry
from laplace.projects import project_creation
from laplace.core import observe

_JSON = "application/json; charset=utf-8"




def _repo_root() -> Path:
    # src/laplace/web/dashboard.py -> parents[2] == the repo root (matches scanner._repo_root)
    return source_tree()


def _json_resp(status: int, obj: Any) -> tuple[int, str, bytes]:
    return status, _JSON, json.dumps(obj, ensure_ascii=False).encode("utf-8")




# ── GET /dashboard/data — the enriched roster ────────────────────────────────

def _staleness_chips(corpus: str, root: Path) -> list[dict]:
    """The compact per-project staleness chips (conception §3): only the DEGRADED
    PER-CORPUS reads (nodemap, plan→prose) — the global engine reads are the same for
    every project and are NOT repeated per card (no page-top alarm wall). Each chip
    carries its runnable fix, PLATFORM-NORMALIZED for the project root (``core.process.normalize_cmd``), that
    NEVER fires — the chip reveals the command, it does not run it (offer-never-fire)."""
    try:
        from laplace.web import shared_ui as su
        reads = su.staleness(corpus, root).get("reads", [])
    except Exception:  # noqa: BLE001 — a substrate hiccup on one project never breaks the roster
        return []
    chips = []
    for r in reads:
        if r.get("scope") != "corpus" or not r.get("degraded"):
            continue
        chips.append({
            "label": r.get("label") or r.get("id") or "derived read",
            "state": "absent" if not r.get("present") else "stale",
            "fix": core_process.normalize_cmd(r.get("fix") or "", root),
        })
    return chips


def _review_resolution(name: str) -> dict:
    """What the ARTEFACT surface can open for a project, resolved through the one
    server-canonical authority — :func:`registry.project_context` (W2 UNIFICATION). The W1
    shim probed ``/review``'s own resolver (``review_surface.manuscript_dir`` → the plan's
    ``target_dir``), which is the disease the W1 judge proved: it read the wrong root and
    lied on 6/9 doors. W2 folded ``/review`` (now ``/artefact``) onto ``project_context``,
    so this shim collapses to that ONE authority. Two truths the roster needs:

      * ``openable`` — ``project_context`` resolves a REAL current-artefact pdf, so the
        ``open latest`` door is live and truthful. law-of-laws — whose real ``main.pdf`` the
        plan's ``target_dir`` could NOT reach in W1 — now resolves through ``project_context``
        and its door Plainly ENABLES (the W2 door that A1 deferred).
      * ``minted`` — the current artefact is a CLEAN release/finalize product (a TIER signal,
        A6): a NEVER_RUN-stated paper that has minted a release is live work, not a scaffold.

    Fail-closed: an unknown corpus or a resolver hiccup yields both False — never a
    fabricated live door or a mis-promoted tier."""
    if not name:
        return {"openable": False, "minted": False}
    try:
        ctx = registry.project_context(name)
        if ctx is None:
            return {"openable": False, "minted": False}
        art = ctx.current_artefact or {}
    except Exception:  # noqa: BLE001 — a resolver hiccup never fabricates a door or a tier
        return {"openable": False, "minted": False}
    return {"openable": bool(art.get("pdf")),
            "minted": art.get("kind") in ("clean", "release")}


def _artefact_href(name: str) -> str:
    """The ``/artefact?corpus=<name>`` deep-link (name path-safe-encoded) into the one
    consolidated reader/annotator/editor. Offered only when :func:`_review_resolution`
    reports the corpus openable — never as a dead door."""
    from urllib.parse import quote
    return "/artefact?corpus=" + quote(name, safe="")


# ── THE PRIMARY DOOR (R2) — the release state machine's ACTUAL next move ──────
#
# R2 (mocks/REDLINES_2026-07-16.md §2b): the ONE primary door is the state machine's
# real next transition for THIS project — NEVER a constant-per-state-family guess. A
# banked recover order BEATS resume (a converging paper whose minted release never
# travelled must recover, not press on); a NEVER_RUN paper offers run; a card whose
# state has no derived transition SAYS SO (never a fabricated door). Derived here so the
# HTML renders the server's move, not its own re-derivation.

#: the converging band — states where the next move is "resume convergence" (derived
#: from release.STATES, not a family label). Below CANDIDATE_LOCKED the candidate is
#: still under the harnessed loop; the door resumes it.
_CONVERGING = frozenset({"WELDED", "MECHANICALLY_VALID", "UNDER_CONVERGENCE", "REOPENED"})

#: state -> the gesture its next transition invites, as the primary door's LABEL. This
#: is the door's words (a fact/route he acts on), distinct from the bare ``next_action``
#: token kept for back-compat. A state absent here has NO derived move (the card says so).
_DOOR_LABEL = {
    "NEVER_RUN": "run the release machine", "STAGED": "run the release machine",
    "WELDED": "resume convergence", "MECHANICALLY_VALID": "resume convergence",
    "UNDER_CONVERGENCE": "resume convergence", "REOPENED": "resume convergence",
    "CANDIDATE_LOCKED": "author review", "AUTHOR_REVIEWED": "final build",
    "FINAL_CLEAN_BUILD": "final gates", "FINAL_GATES_PASSED": "accept the release",
    "AUTHOR_ACCEPTED": "release", "RELEASED": "open the release",
}


def _work_order_projection(root: Path) -> dict:
    """The dashboard's diagnosed work-order projection.

    Readable rows still drive the cards as a lower bound, while ``integrity``
    prevents a poisoned line from presenting the smaller census as complete.
    Selection and diagnostics both delegate to the shared storyboard/ledger
    organs; the dashboard invents neither a parser nor a retirement join.
    """
    from laplace.engine import engine_ledger
    from laplace.manuscript import storyboard as _storyboard
    from laplace.pipeline.ledger import integrity_projection

    rows, residuals = _storyboard.load_work_orders_diagnosed(root)
    open_ids = {str(r["id"]) for r in
                _storyboard.work_order_partitions(rows)["open_rows"]}
    out: dict[str, list[dict]] = {}
    for row in rows:
        if (str(row.get("id") or "") in open_ids
                and engine_ledger.is_work_order(row)
                and row.get("corpus")):
            out.setdefault(str(row["corpus"]), []).append(row)
    return {
        "by_corpus": out,
        "integrity": integrity_projection(residuals),
    }


def _open_work_orders(root: Path) -> dict[str, list[dict]]:
    """Every OPEN work-order in ``corpus_friction/work_orders.jsonl``, indexed by corpus.
    A cheap one-file read (the roster stays a cheap inventory) that lets the primary door
    see a banked recover order — the machine's real next move for a converging paper whose
    minted release is absent on this box. A missing/corrupt store yields ``{}`` (the door
    degrades to the plain state move, never crashes)."""
    try:
        return _work_order_projection(root)["by_corpus"]
    except (OSError, ValueError):
        return {}


def _recover_order(name: str, orders: dict[str, list[dict]]) -> dict | None:
    """The banked, still-open RECOVER order for a project (action carries ``recover``),
    or ``None``. Its existence is the state machine saying: the next move is to consume
    this order, not to press convergence forward."""
    for w in orders.get(name, []):
        if "recover" in (w.get("action") or ""):
            return w
    return None


def _primary_door(name: str, state: str, artefact_href: str | None,
                  recover: dict | None) -> dict:
    """THE primary door (R2): ``{label, href, kind, why}``. ``label=None`` with
    ``kind="unknown"`` when the state declares no derived move — the card then says so
    plainly instead of offering a fabricated door. Precedence: a banked recover order
    (beats resume) -> the state's own transition -> plain "cannot derive"."""
    from urllib.parse import quote
    pipe = "/pipeline?project=" + quote(name, safe="")
    if recover is not None:
        wid = recover.get("id", "")
        return {"label": "recover the release", "kind": "recover",
                "href": "/desk?wo=" + quote(wid, safe=""),
                "why": "banked recover order " + wid + " — the machine's next move, ahead of resume"}
    label = _DOOR_LABEL.get(state)
    if label is None:
        return {"label": None, "kind": "unknown", "href": None,
                "why": "no derived next move — release state " + state}
    if state == "RELEASED":
        if not artefact_href:
            return {"label": None, "kind": "unknown", "href": None,
                    "why": "released, but no local artefact resolves to open"}
        return {"label": label, "kind": "open", "href": artefact_href,
                "why": "open the minted release"}
    kind = ("run" if state in ("NEVER_RUN", "STAGED")
            else "resume" if state in _CONVERGING else "advance")
    return {"label": label, "kind": kind, "href": pipe,
            "why": "release state " + state + " -> " + label}


def _card_growth(row: dict | None) -> dict | None:
    """The growth fields a dashboard CARD paints, cut from the producer's full row: the
    rung (``state``) and the absent-vs-pre-ladder split the scaffold chip reads.

    The rest of :func:`growth.growth_state` — the bar, the goal version, the reason
    prose, and the birth demand queues — stays on the producer, ``/corpus/meta`` and the
    growth cockpit, which are the reads that draw it. The queues alone run ~3.9KB per
    seeded project; carried on every card they spent half the 16KB first-paint budget on
    bytes no card paints."""
    if not isinstance(row, dict):
        return row
    return {"present": bool(row.get("present")), "state": row.get("state"),
            "pre_ladder": bool(row.get("pre_ladder"))}


def _card_verdict(verdict: dict | None) -> dict | None:
    """The truth-layer fields a dashboard CARD paints, cut from the producer's full join:
    the composed position and its evidence, the generation line (gen, debt trajectory,
    any open RESPINE intent), and the minted artefact's name and date.

    The rest of :func:`project_state.project_verdict` — the rounds block, the next act,
    the owed-to-author rows, the artefact's path/exists pair, and its own copy of the
    growth row (the card already carries one under ``growth``) — stays on the producer,
    which the pipeline surface reads whole."""
    if not isinstance(verdict, dict):
        return verdict
    gen = verdict.get("generations") or {}
    art = verdict.get("artefact") or {}
    return {
        "present": bool(verdict.get("present")),
        "position": verdict.get("position"),
        "position_evidence": verdict.get("position_evidence") or [],
        "generations": {"gen": gen.get("gen"),
                        "debt_trajectory": gen.get("debt_trajectory") or [],
                        "respine_intent": gen.get("respine_intent")},
        "artefact": {"name": art.get("name"), "minted_at": art.get("minted_at")},
    }


def _card_artefact(art: dict | None) -> dict | None:
    """The current-artefact fields a dashboard CARD paints, cut from the registry row: the
    pdf the ``open latest`` door reaches, plus the ``version_id``/``kind`` the card's words
    and the LIVE tier read.

    The ``tex`` source path is a PRODUCER fact — no card paints it, and the door it would
    open does not exist on this surface — while riding on every row it cost 983B of the
    16KB first paint. :func:`registry.project_states` keeps the whole row (``pdf``, ``tex``,
    ``version_id``, ``kind``) for the reads that draw it."""
    if not isinstance(art, dict):
        return art
    return {k: art.get(k) for k in ("pdf", "version_id", "kind")}


# ── THE FIRST-PAINT BYTE LAW, ENFORCED AT THE PRODUCER ───────────────────────
#
# conception §8 bounds this route to a 16KB first paint. That law used to be bounded "by
# construction" and DISCOVERED by a test whenever it broke: every registered project costs
# ~700B, so the roster re-crossed the line on registration (2026-08-13, the 18th card, 250B
# over). The bound now lives where the bytes are made — the same pattern /shared/versions
# already runs (``shared_ui._VERSIONS_MAX_BYTES`` + ``_enforce_versions_budget``): the tail
# sheds, LOUDLY, so the payload fits at ANY roster size and the test only witnesses it.

_DASHBOARD_MAX_BYTES = 16 * 1024

#: what a THINNED card keeps — the card CONTRACT (identity, tier, state, the door, the
#: honest staleness chips). What sheds is the heavy per-card JOINS (``verdict``, ``growth``,
#: the composed position words, the primary door's ``why`` prose, the recover reveal): a
#: thinned card still renders and still routes, it just stops carrying its join.
#: (``orders_n`` and ``release_absent`` ride BECAUSE the brief's tiles read them off this
#: same read model — the lock-step law: a thinned card must still compose a tile.)
_THIN_KEEP = ("name", "kind", "state", "pipeline_position", "updated", "rounds_n",
              "next_action", "scaffold", "live", "orders_n", "release_absent",
              "latest_artefact", "artefact_href", "staleness")


def _thin_card(card: dict) -> dict:
    """One card cut to :data:`_THIN_KEEP` and FLAGGED (``thinned``) — never a silent
    quiet-down. The client renders a thinned card in its plain form; the flag is what
    tells it (and him) that this card's join was shed for the byte law."""
    out = {k: card[k] for k in _THIN_KEEP if k in card}
    out["thinned"] = True
    return out


def _enforce_first_paint_budget(out: dict) -> None:
    """The byte half of the 16KB first-paint law, ENFORCED not asserted (mirrors
    :func:`shared_ui._enforce_versions_budget`). While the payload is over budget:

      1. SHED displayed integrity residuals while retaining their full-set count and
         content commitment,
      2. THIN the coldest cards to the card contract (``thinned`` counts them), and
      3. if the thinned roster still does not fit, SHED cards outright, coldest first,
         with the LOUD ``truncated`` flag + ``omitted`` count.

    COLDEST first means the shelf (never-live) cards before the live bench, each
    oldest-``updated`` first — the hottest work is the last thing to lose detail, and a
    project he has not touched is the first. ``n`` and ``open_orders`` stay the as-discovered
    totals, so a shed card is still counted, never disappeared."""
    def _size(o: dict) -> int:
        return len(json.dumps(o, ensure_ascii=False).encode("utf-8"))

    if _size(out) <= _DASHBOARD_MAX_BYTES:
        return
    integrity = out.get("work_order_integrity") or {}
    residuals = integrity.get("residuals")
    while isinstance(residuals, list) and residuals and _size(out) > _DASHBOARD_MAX_BYTES:
        residuals.pop()
        integrity["residuals_truncated"] = True
        integrity["residuals_omitted"] = max(
            0, int(integrity.get("residual_count") or 0) - len(residuals))
        integrity["surface_residuals_omitted_by_budget"] = (
            int(integrity.get("surface_residuals_omitted_by_budget") or 0) + 1)
    cards = out["projects"]
    cold = sorted(cards, key=lambda c: (bool(c.get("live")), c.get("updated") or ""))
    for card in cold:                       # 1 — thin, coldest first
        if _size(out) <= _DASHBOARD_MAX_BYTES:
            return
        thin = _thin_card(card)
        card.clear()
        card.update(thin)
        out["thinned"] += 1
    for card in cold:                       # 2 — shed, coldest first, loudly
        if _size(out) <= _DASHBOARD_MAX_BYTES:
            break
        cards.remove(card)                  # names are unique registry keys
        out["omitted"] += 1
        out["truncated"] = True
    # ``thinned`` names what is SERVED thinned; a card that was thinned and then shed is
    # counted once, under ``omitted``. The recount can only shrink the number (fewer
    # digits, never more), so it can never push the payload back over the budget.
    out["thinned"] = sum(1 for c in cards if c.get("thinned"))
    if _size(out) > _DASHBOARD_MAX_BYTES:
        raise ValueError("dashboard first-paint payload cannot fit its declared byte budget")


def dashboard_data(root: Path | None = None) -> dict:
    """The dashboard's ONE read-model: every registered project as an enriched card row.
    ``registry.project_states`` is the inventory authority; each row gains ``scaffold``
    (NEVER_RUN, rendered reduced-emphasis), ``artefact_href`` (openable or null), and
    compact ``staleness`` chips (degraded per-corpus reads, fixes normalized). Cut to what
    a card paints, then BOUNDED to the 16KB first-paint law by its own enforcer
    (:func:`_enforce_first_paint_budget`) — the law holds at any roster size, and the
    payload says so in ``budget`` / ``thinned`` / ``truncated`` / ``omitted``.

    ACT 1 (the truth layer): every LIVE card also carries ``verdict`` —
    :func:`project_state.project_verdict`, the one join over the release
    machine, the generation ledger, the selection sheet, and the open
    RESPINE/register-verdict rows — so a card can plainly say "pre-release ·
    GEN-3 · r2 minted 2026-07-21" instead of the bare, pre-machine-blind
    ``pipeline_position``. A scaffold card (never run, no rounds, no minted
    artefact) carries ``verdict: null`` — there is nothing a join would add to
    a project that has genuinely never started, and the read stays cheap for
    the shelf.

    The two joined rows and the artefact row ride CUT to what a card paints
    (:func:`_card_growth`, :func:`_card_verdict`, :func:`_card_artefact`); the producers
    keep their full rows for the reads that draw them. Carrying both joins whole put the
    payload at 31,766B over a 17-project roster — the 16KB first-paint law is what bounds
    this route, and :func:`_enforce_first_paint_budget` is what MAKES it hold."""
    root = (root or _repo_root()).resolve()
    rows = registry.project_states(root)
    try:
        order_projection = _work_order_projection(root)
    except (OSError, ValueError) as exc:
        from laplace.pipeline.ledger import integrity_projection
        order_projection = {
            "by_corpus": {},
            "integrity": integrity_projection([
                {"defect": "store-unreadable",
                 "store": "corpus_friction/work_orders.jsonl",
                 "error": f"{type(exc).__name__}: {exc}"}
            ]),
        }
    orders = order_projection["by_corpus"]
    out = []
    open_orders = 0
    for r in rows:
        scaffold = r["state"] == "NEVER_RUN"
        review = _review_resolution(r["name"])
        # THE TIER (A6): a project is LIVE WORK — a full lab-bench card, not a scaffold
        # shelf card — when it has RUN (state past NEVER_RUN), OR carries real rounds, OR
        # has a minted release artefact. paper_falqon is NEVER_RUN-stated yet has rounds_n
        # and a minted release PDF: live, never a scaffold. The client keys the tier split
        # on THIS field (server-authored), never on a client re-derivation of state.
        live = (not scaffold) or (r["rounds_n"] > 0) or review["minted"]
        artefact_href = _artefact_href(r["name"]) if review["openable"] else None
        recover = _recover_order(r["name"], orders)
        # W-DASH — the open-order count for THIS project (scoped to a registered project,
        # so the brief's "orders" chip counts the projects' banked work, never the engine-
        # internal _engine/_interface channels). One read: `orders` is already in hand.
        orders_n = len(orders.get(r["name"], []))
        open_orders += orders_n
        # R2 — the ONE primary door, the state machine's actual next move (recover beats
        # resume; never-run runs; an underivable state says so). The client renders THIS.
        primary = _primary_door(r["name"], r["state"], artefact_href, recover)
        # D7 — an absent minted release with a banked recover order: the card wears the
        # warn is-offer chip revealing the order + its consume route (there is no local
        # re-mint CLI to fabricate — the reveal is the fact + the route, never a dead cmd).
        release_absent = recover is not None and artefact_href is None
        # ACT 1 — the truth layer: a LIVE card's join over the release machine +
        # generation ledger + selection sheet + open RESPINE/register-verdict rows
        # (project_state.project_verdict). Reader failures degrade to an absent
        # field inside the verdict itself, never a card 500; a scaffold gets no
        # verdict (nothing a join would add — honest, and keeps the shelf cheap).
        verdict = project_state.project_verdict(root, r["name"]) if live else None
        # de-enum the served position at the source: the producer returns real composed words
        # for a paper with a generation ledger but the bare state enum for a plain state, and
        # the card fact renders verdict.position verbatim. Compose it here (BEFORE the chrome
        # words are derived), so no raw enum serves anywhere on Home — tile, card, or L1 pill.
        if verdict is not None and (verdict.get("position") or "").strip():
            verdict["position"] = _compose_card_position(verdict.get("position"), r["state"])
        # ACT 1 (item 4) — the chrome/roster position words, from the SAME verdict the
        # cards render, so the L1 header pill (shell.js reads this row) can show the
        # truth-layer position ("pre-release · GEN-3") instead of the raw NEVER_RUN state.
        from laplace.web import shared_ui as _su
        position = _su.position_words(verdict)
        # G2 — the growth ladder rung, read through the ONE producer
        # (growth.growth_state), the same field project_verdict carries. Surfaced on
        # EVERY card (not only live ones) so a bare SEEDED scaffold — the crank — shows
        # its rung on the dashboard row, while a released paper renders a plain
        # pre-ladder null (never a fake SEEDED on a finished paper). Cut to the card's
        # fields by _card_growth on the way out.
        from laplace.pipeline import growth as _growth
        growth_row = ((verdict or {}).get("growth")
                      if verdict is not None else _growth.growth_state(root, r["name"]))
        out.append({
            "name": r["name"],
            # the RULED display name the card mounts under, from the registry's layout manifest
            # (the marriage law's cockpit leg). Carried only when a ruled name exists — a row
            # whose display name is just its own name would spend first-paint bytes to say
            # nothing (the 16KB law), so the client falls back to `name` on absence.
            **({"display_name": r["display_name"]}
               if r.get("display_name") and r["display_name"] != r["name"] else {}),
            "kind": r["kind"],
            "state": r["state"],
            "pipeline_position": r["pipeline_position"],
            "position": position,
            "growth": _card_growth(growth_row),
            "updated": r["updated"],
            "rounds_n": r["rounds_n"],
            "next_action": r["next_action"],
            "primary": primary,
            "release_absent": release_absent,
            "recover": ({"wo": recover["id"],
                         "reveal": recover["id"] + " · release-recover (banked, open)\n"
                                   "recover via the order → /desk?wo=" + recover["id"]}
                        if recover is not None else None),
            "scaffold": scaffold,
            "live": live,
            "orders_n": orders_n,
            # cut to the pdf door + the version/kind words (_card_artefact): the `tex`
            # source path is a producer fact no card paints (the 16KB law).
            "latest_artefact": _card_artefact(r["latest_artefact"]),
            # A1: the door is truthful — offered only when /review can ACTUALLY open it
            # (review's own resolver), never on registry pdf-presence (the lying door).
            "artefact_href": artefact_href,
            # only per-corpus staleness for a NEVER_RUN scaffold's absence — a scaffold has
            # no derived reads to be stale about yet (honest: no chips, not fake-fresh ones).
            "staleness": ([] if scaffold else _staleness_chips(r["name"], root)),
            # decisions-awaiting: OMITTED not faked (the heavy desk join; §3 honesty).
            # the card's cut of the truth-layer join (_card_verdict): what the card
            # paints rides, the producer keeps the whole row for the reads that need it.
            "verdict": _card_verdict(verdict),
        })
    payload = {"projects": out, "n": len(out), "open_orders": open_orders,
               "work_order_integrity": order_projection["integrity"],
               "generated_ts": observe.now_iso(), "templates": list(project_creation.TEMPLATES),
               # the byte law, declared and accounted on the wire (never a silent cut)
               "budget": {"max_bytes": _DASHBOARD_MAX_BYTES},
               "thinned": 0, "truncated": False, "omitted": 0}
    _enforce_first_paint_budget(payload)
    return payload


# ── GET /dashboard/brief — THE COMPOSED BRIEF (W-DASH) ────────────────────────
#
# The dashboard's resting altitude is no longer an inventory of cards — it is a composed
# brief of the WHOLE: what MOVED and what single decision or run is most consequential
# NOW (delta-and-ask, never project counts restated as sentences), plus the cards as the
# summonable inventory behind one open. THE LOCK-STEP LAW: the brief composes over the
# EXISTING :func:`dashboard_data` read model — the same project_state join the wake reads —
# never a parallel read, so the interface and the self-projection cannot disagree.


def _descent_href(name: str) -> str:
    """The descent door into a project's cockpit — the EXISTING /conceptric route, marked
    ``via=dashboard`` so the arrival is framed as a descent into the same object (the shell
    echo names the dashboard brief on landing)."""
    from urllib.parse import quote
    return "/conceptric?corpus=" + quote(name, safe="") + "&via=dashboard"


def _brief_moved_last(projects: list[dict]) -> dict | None:
    """The project that moved most recently — max ISO ``updated`` (lexicographic on the
    Z-stamp). A NEVER_RUN scaffold carries no stamp and can never win a real mover."""
    dated = [p for p in projects if p.get("updated")]
    return max(dated, key=lambda p: p["updated"]) if dated else None


def _brief_decisions(live: list[dict]) -> list[tuple[dict, dict]]:
    """Every live card carrying an open RESPINE projection-intent — the plan-altitude
    decision the truth-layer verdict already resolved (``verdict.generations.respine_intent``).
    The heavy desk/tension join stays OMITTED (§3 honesty); this is the cheap decision the
    read model already holds."""
    out = []
    for p in live:
        rs = ((p.get("verdict") or {}).get("generations") or {}).get("respine_intent")
        if rs:
            out.append((p, rs))
    return out


def _brief_consequential(live: list[dict], decisions: list[tuple[dict, dict]]) -> dict | None:
    """THE single most consequential item now — a queued decision (RESPINE) beats a banked
    recover order beats the next live run. Returns ``{name, kind, label, glance, href}`` for
    the one glance the resting brief renders, or ``None`` when nothing is live."""
    if decisions:
        p, rs = decisions[0]
        # plain outcome language at glance altitude — the drafted intent's raw title
        # (plan-meta vocabulary) stays behind the door it opens, never in the glance.
        return {"name": p["name"], "kind": "decision", "label": "rule the respine",
                "glance": ("a drafted respine on " + p["name"] + " awaits your ratify or "
                            "revoke — re-weight the manuscript to lead on its ranked "
                            "contribution"),
                "href": rs.get("href") or _descent_href(p["name"])}
    rec = [p for p in live if p.get("recover")]
    if rec:
        p = rec[0]
        pr = p.get("primary") or {}
        return {"name": p["name"], "kind": "recover",
                "label": pr.get("label") or "recover the release",
                "glance": "recover the minted release on " + p["name"]
                          + " — the release PDF is absent on this box",
                "href": pr.get("href") or _descent_href(p["name"])}
    runnable = [p for p in live if (p.get("primary") or {}).get("label")]
    if runnable:
        p = max(runnable, key=lambda x: x.get("updated") or "")
        pr = p["primary"]
        return {"name": p["name"], "kind": pr.get("kind") or "run", "label": pr["label"],
                "glance": pr["label"] + " on " + p["name"],
                "href": pr.get("href") or _descent_href(p["name"])}
    return None


def _moved_sentence(p: dict) -> str:
    """The 'what moved last' clause — a state delta, not a census. Names the mover and its
    truth-layer position, and (when it applies) the release-absent recover delta."""
    pos = (p.get("position") or p.get("pipeline_position") or p.get("state") or "").strip()
    frag = "Last to move: " + p["name"]
    if pos:
        frag += " — " + pos.lower().replace("_", " ")
    if p.get("recover"):
        frag += ", its minted release absent here (a recover order is banked)"
    return frag + "."


def _compose_glance(live: list[dict], moved: dict | None, conseq: dict | None,
                    n_orders: int) -> str:
    """THE brief prose (delta-and-ask): the single most consequential call NOW, what moved
    last, and what is queued — composed server-side, never project counts restated as
    sentences (those ride the count chips). Degrades to a plain cold-engine line when
    nothing has moved."""
    S: list[str] = []
    # the consequential call rides its own card directly below — the prose never
    # restates it (the perfectionist pass: the same sentence twice is a wince).
    if moved is not None and (conseq is None or moved["name"] != conseq["name"]):
        S.append(_moved_sentence(moved))
    elif moved is not None and conseq is not None and moved["name"] == conseq["name"]:
        others = [p for p in live if p["name"] != moved["name"] and p.get("updated")]
        if others:
            S.append(_moved_sentence(max(others, key=lambda p: p["updated"])))
    if n_orders:
        S.append(str(n_orders) + " banked order" + ("" if n_orders == 1 else "s")
                 + " wait to run.")
    if not S:
        S.append("No project has moved yet — open the inventory to seed the first run.")
    return " ".join(S)


#: composed position WORDS for every release-machine state (release.STATES plus NEVER_RUN
#: and REOPENED) — so a tile never serves a raw state enum (UNDER_CONVERGENCE) as its
#: position word. The truth-layer verdict already composes real words for a paper with a
#: generation ledger (e.g. "pre-release — GEN-3"); this map covers the plain states the
#: producer returns bare, so the picture reads in words, not machine caps.
_STATE_WORDS: dict[str, str] = {
    "NEVER_RUN": "not yet run",
    "STAGED": "staged for the first run",
    "WELDED": "welded — ready to converge",
    "MECHANICALLY_VALID": "mechanically valid — ready to converge",
    "UNDER_CONVERGENCE": "under convergence",
    "REOPENED": "reopened for another pass",
    "CANDIDATE_LOCKED": "candidate locked — your review waits",
    "AUTHOR_REVIEWED": "reviewed — ready for the final build",
    "FINAL_CLEAN_BUILD": "final clean build",
    "FINAL_GATES_PASSED": "final gates passed",
    "AUTHOR_ACCEPTED": "accepted — ready to release",
    "RELEASED": "released",
}

#: the convergence band — states whose word carries the banked-round truth when the read
#: model has it ("under convergence — round 5 banked"), degrading to the plain word when
#: no round is known.
_CONVERGING_WORDS = frozenset({"WELDED", "MECHANICALLY_VALID", "UNDER_CONVERGENCE", "REOPENED"})

#: a bare state enum: only uppercase letters, digits and underscores (no lowercase, no
#: spaces) — the shape the producer returns for a plain state. A composed phrase
#: ("pre-release — GEN-3") never matches, so it is kept verbatim.
_ENUM_RE = re.compile(r"^[A-Z0-9_]+$")


def _state_words(state: str | None) -> str:
    """The plain composed WORDS for a state enum (no round suffix) — the mapped phrase, or a
    lowercased de-underscored fallback for an unmapped state, so no machine-caps token serves.
    The one shared mapping both the card fact and the tile compose through."""
    s = (state or "").strip()
    return _STATE_WORDS.get(s) or (s.lower().replace("_", " ") if s else "")


def _compose_card_position(raw: str | None, state: str | None) -> str:
    """The position WORDS an inventory CARD fact serves — never a raw state enum. Keeps the
    truth-layer verdict's own words when it already composed real words ("pre-release — GEN-3");
    otherwise maps the bare state enum to its plain phrase. No round suffix: the card carries
    its own rounds chip, so the round truth is not restated in the position word."""
    r = (raw or "").strip()
    if r and not _ENUM_RE.match(r):
        return r                                      # already composed real words — keep
    return _state_words(state or r) or "state not yet resolved"


def _tile_position(p: dict) -> str:
    """The composed position WORDS a paper TILE serves — never a raw state enum. The plain
    card words plus, for a converging paper, the banked-round truth ("under convergence —
    round 5 banked"), because a tile has no separate rounds chip; degrades to the plain word
    when no round is known."""
    v = p.get("verdict") or {}
    base = _compose_card_position(v.get("position"), p.get("state"))
    state = (p.get("state") or "").strip()
    if state in _CONVERGING_WORDS and p.get("rounds_n") and "round" not in base:
        base += " — round " + str(p["rounds_n"]) + " banked"
    return base or "state not yet resolved"


def _papers_tiles(projects: list[dict]) -> list[dict]:
    """The lean per-tile picture THE PAPERS paints at rest — carried INSIDE the brief so the
    resting picture paints in lock-step with the prose over the one read model, with no
    second :func:`dashboard_data` compute-and-fetch on cold load (the lock-step law reaching
    to the picture). Each row carries exactly what a tile and its hover glance read: the name,
    the live/scaffold split, the state edge, the truth-layer position words, the round count,
    whether a decision waits, and the banked-order / absent-release asks. The heavy card body
    (facts, doors, the full generation ledger) stays in ``/dashboard/data``, materialised only
    when the full inventory is summoned — the picture is cheap, the inventory is lazy."""
    out = []
    for p in projects:
        v = p.get("verdict") or {}
        g = v.get("generations") or {}
        out.append({
            "name": p["name"],
            "live": p["live"],
            "state": p["state"],
            "pipeline_position": p["pipeline_position"],
            "rounds_n": p["rounds_n"],
            "orders_n": p["orders_n"],
            "release_absent": p["release_absent"],
            # a minimal verdict shape the tile/glance helpers read unchanged: the COMPOSED
            # position words (never a raw state enum — _tile_position maps the machine caps
            # to real words) + a boolean respine marker (the intent's plan-meta body stays
            # behind the door it opens, never in the picture).
            "verdict": ({"position": _tile_position(p),
                         "generations": {"respine_intent": bool(g.get("respine_intent"))}}
                        if p.get("verdict") else None),
        })
    return out


#: plain, path-free and id-free wording for a banked work-order, keyed by a keyword in its
#: action slug. The served orders list states what the order IS in words the author reads;
#: the store's raw ``what`` (which carries build paths) and the record id ride the desk route
#: only, never the reader's face (register zero — no raw ids or source paths in served copy).
_ORDER_WORDS: tuple[tuple[str, str], ...] = (
    ("recover", "recover the minted release — its PDF is absent on this box"),
    ("compile", "first compile — build the paper's PDF, banked for a later session"),
    ("embedding", "build the router embeddings, banked for a later session"),
    ("nodemap", "rebuild the node map, banked for a later session"),
    ("reproject", "a re-projection pass, banked for a later session"),
    ("projection", "a re-projection pass, banked for a later session"),
    ("harnessed", "a convergence round, banked for a later session"),
    ("round", "a convergence round, banked for a later session"),
    ("derivation", "a derivation pass, banked for a later session"),
)


def _order_words(action: str) -> str:
    """Plain wording for a banked order, composed from its action keyword — never the raw
    ``what`` (build paths) nor the record id. Falls to a plain named-step line for an action
    with no mapped keyword, so an unknown order still reads truthfully."""
    a = (action or "").strip().lower()
    for key, words in _ORDER_WORDS:
        if key in a:
            return words
    return "a banked step, named and waiting to run"


def _brief_orders(orders: dict[str, list[dict]], names: list[str]) -> list[dict]:
    """Every banked, open work-order across the REGISTERED projects as a lean row the orders
    chip lists in place: the project it belongs to, plain path-free / id-free wording, and the
    desk deep-link that opens exactly this order in the work-orders cockpit. Scoped to the
    registered names so the list length equals the orders count (the engine-internal channels
    are excluded, matching :func:`dashboard_data`'s ``open_orders``)."""
    from urllib.parse import quote
    registered = set(names)
    out: list[dict] = []
    for corpus in names:
        if corpus not in registered:
            continue
        for w in orders.get(corpus, []):
            wid = w.get("id", "")
            out.append({
                "project": corpus,
                "words": _order_words(w.get("action") or ""),
                "href": "/desk?item=" + quote(wid, safe="") + "&class=work-orders",
            })
    return out


def _brief_decisions_list(decisions: list[tuple[dict, dict]]) -> list[dict]:
    """The open decisions the decisions chip lists in place — one row per live card carrying a
    drafted respine. Plain glance wording (path-free, id-free); the row descends into that
    project's focus on Home, where the rule-the-respine door already lives."""
    out = []
    for p, _rs in decisions:
        out.append({
            "project": p["name"],
            "glance": ("a drafted respine on " + p["name"] + " awaits your ratify or "
                       "revoke"),
        })
    return out


def dashboard_brief(root: Path | None = None) -> dict:
    """The composed brief of the whole (W-DASH), over the one :func:`dashboard_data` read
    model (the lock-step law — never a parallel join). Returns the delta-and-ask ``glance``,
    the ``consequential`` item's glance + door, the count chips (projects/decisions/orders),
    and — carried IN the brief so the resting picture paints in lock-step with no second
    compute — the lean ``papers`` tiles, the ``orders`` list, and the ``decisions`` list the
    count chips click through to. The heavy card bodies stay in ``/dashboard/data`` — the
    summonable inventory materialised behind one open."""
    root = (root or _repo_root()).resolve()
    data = dashboard_data(root)
    projects = data["projects"]
    live = [p for p in projects if p["live"]]
    scaffolds = [p for p in projects if not p["live"]]
    moved = _brief_moved_last(projects)
    decisions = _brief_decisions(live)
    conseq = _brief_consequential(live, decisions)
    n_orders = data["open_orders"]
    counts = {"projects": data["n"], "live": len(live), "scaffolds": len(scaffolds),
              "decisions": len(decisions), "orders": n_orders}
    # the orders list (scoped to the registered projects, one cheap re-read of the one-file
    # store) — the honest in-place list the orders chip clicks through to.
    order_rows = _brief_orders(_open_work_orders(root), [p["name"] for p in projects])
    return {"brief": {"glance": _compose_glance(live, moved, conseq, n_orders),
                      "moved_last": ({"name": moved["name"],
                                      "position": (moved.get("position")
                                                   or moved.get("pipeline_position")
                                                   or moved.get("state")),
                                      "updated": moved.get("updated")} if moved else None),
                      "consequential": conseq},
            "counts": counts, "n": data["n"], "generated_ts": data["generated_ts"],
            "work_order_integrity": data["work_order_integrity"],
            "papers": _papers_tiles(projects),
            "orders": order_rows,
            "decisions": _brief_decisions_list(decisions)}


# ── POST /dashboard/new — THE NEW PROJECT DOOR (J6) ──────────────────────────

























# ── the ONE dispatch door ────────────────────────────────────────────────────

def handle(path: str, query: dict, method: str,
           body: bytes) -> tuple[int, str, bytes] | None:
    """Route one ``/dashboard/*`` request. Returns (status, content_type, body) or
    ``None`` when the path is not ours (the bare ``GET /`` page is served by the scanner;
    any foreign path falls through). GET is read-only; the one write door is
    ``POST /dashboard/new`` (the New Project door)."""
    if not path.startswith("/dashboard/"):
        return None
    method = (method or "GET").upper()

    if path == "/dashboard/data":
        if method != "GET":
            return _json_resp(405, {"error": f"{method} not allowed — /dashboard/data is GET"})
        try:
            return _json_resp(200, dashboard_data())
        except Exception as e:  # noqa: BLE001 — a substrate hiccup is a 500, never a crash
            return _json_resp(500, {"error": f"dashboard data assembly failed: {e}"})

    if path == "/dashboard/brief":
        if method != "GET":
            return _json_resp(405, {"error": f"{method} not allowed — /dashboard/brief is GET"})
        try:
            return _json_resp(200, dashboard_brief())
        except Exception as e:  # noqa: BLE001 — the brief degrades to a 500, never a crash
            return _json_resp(500, {"error": f"dashboard brief assembly failed: {e}"})

    if path == "/dashboard/new":
        if method != "POST":
            return _json_resp(405, {"error": f"{method} not allowed — the New Project door "
                                    "is POST /dashboard/new"})
        try:
            payload = json.loads(body or b"{}") if body else {}
        except (ValueError, TypeError):
            return _json_resp(400, {"ok": False, "error": "body must be JSON {name, template}"})
        if not isinstance(payload, dict):
            return _json_resp(400, {"ok": False, "error": "body must be a JSON object"})
        status, obj = project_creation.create_project(payload.get("name", ""),
                                     payload.get("template", "conceptric"),
                                     goal=payload.get("goal") or payload.get("description"))
        return _json_resp(status, obj)

    return _json_resp(404, {"error": f"no dashboard route {path!r}"})
