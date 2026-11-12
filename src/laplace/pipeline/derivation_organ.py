"""derivation_organ.py — the derivation organ's reader: the aspiration-first reach
instrument, read-only.

The governing steer (PV-20260721T121500Z-author-steer-aspiration-first-isnads),
quoted verbatim: *"one must ask themselves what the best possible version of a result
is. what would have the furthest reach, broadest scope and deepest impact? And then
the game is to try to build the chain from the substrate towards that. Think of it
like haddiths and isnads, except it all has to actually be true ... Sets the end point
before we know if that end point is achievable."*

So the organ has two banked artifacts under ``<manuscript>/aspiration/``:

* ``aspiration.json`` — the maximal true claim (reach / scope / impact) asserted as
  the boundary condition before achievability is known. This doubles as R10's rich
  intended object.
* ``chain.jsonl`` — the isnad: obligations as links from the substrate toward the
  aspiration, each ``{id, from, to, kind, status, attestation, ts}``. A link is
  ``attested`` when a builder has forged its derivation (a ``.tex`` fragment), a
  computation (a script + output), or an entailment cite; otherwise ``gap`` — the
  structured residual, the gap named, not a retreat to a weaker claim.

This module is a pure reader (the fitness_panel idiom): it measures reach — how far up
the aspiration the attested chain actually got — the metric draft-psi-v2 gates on. It
never writes, never judges; hedging-as-inaction becomes mechanically visible here.
Absent artifacts degrade to empty fields, never a raise.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
from pathlib import Path
from typing import Any

_ASPIRATION_REL = "aspiration/aspiration.json"
_CHAIN_REL = "aspiration/chain.jsonl"
_FEEDBACK_REL = "feedback/feedback.jsonl"

# a node token is the "N_xxx" handle at the head of a from/to field (before its
# colon-gloss). One link may cite SEVERAL from-nodes ("N_a + N_b -> N_c"); the graph
# reader extracts every N_-token so a join link contributes an edge from each source.
_NODE_TOKEN = re.compile(r"N_[A-Za-z0-9_]+")


def _read_json(p: Path) -> dict | None:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def _read_jsonl(p: Path) -> list[dict]:
    out: list[dict] = []
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue                       # a malformed line is skipped, never raises
        if isinstance(obj, dict):
            out.append(obj)
    return out


def _md_path(md: str | Path) -> Path:
    return Path(md)


# ---------------------------------------------------------------------------
# the pure reads.
# ---------------------------------------------------------------------------

def read_aspiration(md: str | Path) -> dict[str, Any]:
    """The maximal-claim boundary condition. ``present: False`` when no aspiration has
    been banked yet — the organ has run Phase 0 or it has not."""
    p = _md_path(md) / _ASPIRATION_REL
    d = _read_json(p)
    if d is None or d.get("record") != "aspiration":
        return {"present": False}
    return {
        "present": True,
        "claim_maximal": d.get("claim_maximal") or "",
        "reach_axes": d.get("reach_axes") or {},
        "demonstrandum": [s for s in (d.get("demonstrandum") or [])
                          if isinstance(s, str)],
        "banked_by": d.get("banked_by") or "",
        "ts": d.get("ts") or "",
    }


def _chain_last_wins(md: str | Path) -> list[dict[str, Any]]:
    """The raw chain records, last-wins per id, in first-appearance order — the whole
    banked record verbatim (all fields, including ``intent_id``/``node_id`` growth
    stamps and any ``_contest``/``_gap_named`` markers). The shared reducer behind
    :func:`read_chain` and the growth-leg stampers; empty ``[]`` when absent."""
    rows = _read_jsonl(_md_path(md) / _CHAIN_REL)
    order: list[str] = []
    latest: dict[str, dict] = {}
    for r in rows:
        lid = r.get("id")
        if not isinstance(lid, str) or not lid:
            continue
        if lid not in latest:
            order.append(lid)
        latest[lid] = r
    return [latest[lid] for lid in order]


def read_chain(md: str | Path) -> list[dict[str, Any]]:
    """The isnad links, last-wins per id (an append-only ledger: a link is banked as
    ``gap`` then re-appended ``attested`` once forged). Returned in first-appearance
    order. Empty ``[]`` when no chain exists.

    The growth stamps ride through when present: a link minted into the conceptric as
    growth carries ``intent_id`` (the conceptric-intent it queued), and once that
    intent is ratified it carries ``node_id`` (the applied node key — the isnad<->
    conceptric join made explicit). Both are surfaced only when present, so a plain
    isnad link's projection is byte-unchanged; the sheet card spreads this record, so
    it carries the stamps automatically."""
    out: list[dict[str, Any]] = []
    for r in _chain_last_wins(md):
        status = r.get("status") or "gap"
        rec: dict[str, Any] = {
            "id": r["id"],
            "from": r.get("from") or "",
            "to": r.get("to") or "",
            "kind": r.get("kind") or "",
            "status": "attested" if status == "attested" else "gap",
            "attestation": r.get("attestation"),
            "ts": r.get("ts") or "",
        }
        if r.get("intent_id"):
            rec["intent_id"] = r["intent_id"]
        if r.get("node_id"):
            rec["node_id"] = r["node_id"]
        for key in ('from_ids', 'to_id', 'question', 'source_refs'):
            if key in r:
                rec[key] = r[key]
        out.append(rec)
    return out


# ---------------------------------------------------------------------------
# the reach metric — how far up the aspiration the attested chain got.
# ---------------------------------------------------------------------------

def _from_nodes(link: dict) -> list[str]:
    if isinstance(link.get('from_ids'), list):
        return link['from_ids']
    return _NODE_TOKEN.findall(str(link.get("from") or ""))


def _to_node(link: dict) -> str | None:
    if link.get('to_id'):
        return link['to_id']
    m = _NODE_TOKEN.search(str(link.get("to") or ""))
    return m.group(0) if m else None


def _longest_attested_depth(links: list[dict]) -> int:
    """Longest chain of ATTESTED links, ordered substrate -> aspiration (one link's
    to-node feeding a later link's from-node). Depth is counted in links. A pure DAG
    longest-path via memoised DFS; robust to the join links (several from-nodes)."""
    attested = [l for l in links if l.get("status") == "attested"]
    # edges: for each attested link, an edge from each of its from-nodes to its to-node,
    # labelled by the link (so a node reached is the END of that link).
    # incoming[node] = list of (src_node, depth_of_link=1) — but we want longest chain
    # of links, so treat each attested link as a unit-weight edge and find the longest
    # path over the node graph.
    succ: dict[str, list[str]] = {}
    for l in attested:
        tn = _to_node(l)
        if tn is None:
            continue
        for fn in _from_nodes(l):
            if fn == tn:
                continue                   # ignore self-loops
            succ.setdefault(fn, []).append(tn)

    memo: dict[str, int] = {}
    visiting: set[str] = set()

    def depth_from(node: str) -> int:
        # number of attested links reachable downstream of `node`.
        if node in memo:
            return memo[node]
        if node in visiting:
            return 0                       # cycle guard (chains should be acyclic)
        visiting.add(node)
        best = 0
        for nxt in succ.get(node, []):
            best = max(best, 1 + depth_from(nxt))
        visiting.discard(node)
        memo[node] = best
        return best

    all_nodes = set(succ.keys())
    for tos in succ.values():
        all_nodes.update(tos)
    return max((depth_from(n) for n in all_nodes), default=0)


def reach(md: str | Path) -> dict[str, Any]:
    """The reach metric draft-psi-v2 gates on — a pure read of the banked chain.

    Returns ``{present, links_total, links_attested, depth_attested, frontier_gap}``:

    * ``links_total`` / ``links_attested`` — the obligation count and how many are forged;
    * ``depth_attested`` — the longest attested isnad path (in links) from the
      substrate toward the aspiration: how far up the chain actually reaches, not
      merely how many isolated links exist;
    * ``frontier_gap`` — the named gaps blocking further ascent, each ``{id, from, to,
      why}`` — the structured residual made mechanically visible (hedging-as-inaction
      cannot hide here).

    Empty when no chain has been banked.
    """
    links = read_chain(md)
    asp = read_aspiration(md)
    total = len(links)
    attested = [l for l in links if l["status"] == "attested"]
    gaps = [l for l in links if l["status"] == "gap"]

    frontier: list[dict[str, Any]] = []
    # re-read the raw ledger once for the gap "_gap_named" annotation (the reader-shape
    # drops underscore fields; the frontier wants the named reason verbatim).
    raw_latest: dict[str, dict] = {}
    for r in _read_jsonl(_md_path(md) / _CHAIN_REL):
        if isinstance(r.get("id"), str):
            raw_latest[r["id"]] = r
    for g in gaps:
        raw = raw_latest.get(g["id"], {})
        frontier.append({
            "id": g["id"],
            "from": g["from"],
            "to": g["to"],
            "kind": g["kind"],
            "why": raw.get("_gap_named") or raw.get("attestation")
                   or "gap: not yet attested (the named residual)",
        })

    return {
        "present": bool(links) or asp.get("present", False),
        "aspiration_present": asp.get("present", False),
        "links_total": total,
        "links_attested": len(attested),
        "depth_attested": _longest_attested_depth(links),
        "frontier_gap": frontier,
        "law": ("Reach, not presence — draft-psi-v2 gates on how far up the aspiration "
                "the attested isnad reached, generation over generation; an unforged "
                "link stays a named gap (the structured residual), not a retreat to a "
                "weaker claim (PV-20260721T121500Z-author-steer-aspiration-first-isnads)."),
    }


# ---------------------------------------------------------------------------
# The generic growth leg — attested derivation links enter the conceptric as growth
# (his ruling: "new results/assets need to be part of conceptric growth not simply
# part of the projection ... traceable maintainable surfaceable and automatable").
# Generic over any project's manuscript_dir; falqon is the first project through. Two
# append-only stampers that never raise:
#
#   * mint_growth_intents — each attested link with no stamp mints one conceptric-
#     intent (via adjudicate.make_conceptric_intent) onto the feedback ledger and
#     stamps the link with its ``intent_id`` (re-runs dedup). A gap never mints.
#   * record_growth_nodes — each link whose intent was ratified (the ledger shows a
#     ratified-operation carrying the applied node key) is stamped with ``node_id`` —
#     the isnad<->conceptric join made explicit.
#
# Neither touches the single apply path (evolve.execute via the ratify door): mint
# only queues an intent (the draft-only law holds), record only joins after the
# author's attributed ratification.
# ---------------------------------------------------------------------------

# the intent kind the growth mint speaks: a derivation link asserts content that is
# not yet a node — "content-missing" is the draftable conceptric-intent whose
# op-template mints a node (evolution_consumer.DRAFTABLE_INTENTS).
_GROWTH_INTENT_KIND = "content-missing"

# the isnad verb per link kind — the one-sentence claim reads as an attestation.
_KIND_PHRASE = {
    "derived": "is derived to",
    "computed": "is computed to",
    "cited": "entails",
    "entailment": "entails",
}

# ref paths named in an attestation (a forged .tex fragment, a computed .json/.py
# output, an entailment cite) — surfaced into the intent context verbatim.
_REF_PATH = re.compile(r"[\w./-]+\.(?:tex|json|py|csv|txt|md)")


def _now() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def _append_jsonl(path: Path, obj: dict) -> None:
    """Append ONE json line, creating the parent dir. The append-only idiom the
    whole ledger family shares."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _growth_claim(rec: dict) -> str:
    """The one-sentence isnad claim (the intent SUBSTANCE = the gap.quote): the
    link's from/to joined by its kind's attestation verb."""
    frm = str(rec.get("from") or "").strip()
    to = str(rec.get("to") or "").strip()
    phrase = _KIND_PHRASE.get(str(rec.get("kind") or "").strip(), "reaches")
    if frm and to:
        return f"{frm} {phrase} {to}."
    if to:
        return f"The chain attests {to}."
    return f"Attested derivation link {rec.get('id') or ''}.".strip()


def _growth_context(rec: dict) -> str:
    """The intent CONTEXT: the attestation text + the fragment/computed ref paths
    it names + the isnad link identity — the traceable provenance of the claim."""
    att = str(rec.get("attestation") or "").strip()
    lines: list[str] = []
    if att:
        lines.append(f"Attestation: {att}")
    refs = _REF_PATH.findall(att)
    if refs:
        lines.append("Refs: " + ", ".join(dict.fromkeys(refs)))
    lines.append(f"Isnad link {rec.get('id') or ''}: "
                 f"{rec.get('from') or ''} -> {rec.get('to') or ''} "
                 f"({rec.get('kind') or ''})")
    return "\n".join(lines)


def mint_growth_intents(md: str | Path, corpus: str, *, by: str) -> dict[str, Any]:
    """Mint a conceptric-intent for every attested chain link not yet stamped — the
    generic growth mint, generic over any project's ``md`` (manuscript dir).

    For each last-wins link with ``status == "attested"`` and neither an ``intent_id``
    nor a ``node_id`` field: mint one conceptric-intent via
    :func:`adjudicate.make_conceptric_intent` whose substance (``gap.quote``) is the
    link's one-sentence isnad claim and whose context (``gap.context``) is the
    attestation text + ref paths; append it to ``<md>/feedback/feedback.jsonl``; and
    stamp the link (chain append, last-wins) with the minted ``intent_id`` so a re-run
    dedups (a link carrying ``intent_id`` or ``node_id`` is skipped). A gap link never
    mints (only forged claims enter the conceptric as growth).

    Append-only, never raises. Returns
    ``{"minted": [{id, intent_id, claim}], "skipped": n}``."""
    from laplace.pipeline import adjudicate as _adj

    md = _md_path(md)
    chain_p = md / _CHAIN_REL
    feedback_p = md / _FEEDBACK_REL

    minted: list[dict[str, Any]] = []
    skipped = 0
    for rec in _chain_last_wins(md):
        # only forged claims grow the conceptric; a gap stays a NAMED residual.
        if (rec.get("status") or "gap") != "attested":
            skipped += 1
            continue
        # dedup: an already-minted (intent_id) or already-joined (node_id) link is done.
        if rec.get("intent_id") or rec.get("node_id"):
            skipped += 1
            continue

        claim = _growth_claim(rec)
        context = _growth_context(rec)
        anchor = _to_node(rec) or str(rec.get("id") or "")
        try:
            intent = _adj.make_conceptric_intent(
                anchor, _GROWTH_INTENT_KIND, note=claim,
                actor=(by or "author"), project=corpus)
            intent["gap"] = {"quote": claim, "context": context}
            _append_jsonl(feedback_p, intent)
            # stamp the link: re-append the whole record + the intent_id (last-wins).
            stamped = dict(rec)
            stamped["intent_id"] = intent["id"]
            stamped["ts"] = _now()
            _append_jsonl(chain_p, stamped)
        except Exception:
            # a single malformed link never sinks the batch (honest-empty per link).
            skipped += 1
            continue
        minted.append({"id": rec.get("id"), "intent_id": intent["id"], "claim": claim})

    return {"minted": minted, "skipped": skipped}


def _applied_node_by_intent(md: Path) -> dict[str, str]:
    """The feedback ledger's ratified joins: ``{intent_id: applied_node_key}`` for
    every ratified-operation that applied (outcome ``applied``). The node key is the
    ``object.key`` the one apply leg banked (``_apply_one`` -> ``make_ratified_
    operation``). Empty when no ledger or no applies."""
    out: dict[str, str] = {}
    for r in _read_jsonl(md / _FEEDBACK_REL):
        if r.get("record") != "ratified-operation":
            continue
        if r.get("outcome") != "applied":
            continue
        target = r.get("target")
        key = ((r.get("object") or {}).get("key")) or ""
        if isinstance(target, str) and target and key:
            out[target] = str(key)
    return out


def record_growth_nodes(md: str | Path, corpus: str) -> dict[str, Any]:
    """Join the isnad to the conceptric for every ratified growth intent — the generic
    growth record, generic over any project's ``md``.

    For each last-wins link that carries an ``intent_id`` but no ``node_id`` yet, and
    whose intent the feedback ledger shows ratified (a ratified-operation with the
    applied node key), stamp the link (chain append, last-wins) with ``node_id`` = the
    applied node key — the isnad<->conceptric join made explicit and durable. Skips a
    link whose intent has not been ratified (stays open at the desk) and a link already
    joined (``node_id`` present — dedup).

    Append-only, never raises. Returns ``{"joined": [{id, intent_id, node_id}]}``.
    ``corpus`` rides for symmetry with the mint (the ledger is per-manuscript)."""
    md = _md_path(md)
    chain_p = md / _CHAIN_REL
    applied = _applied_node_by_intent(md)

    joined: list[dict[str, Any]] = []
    for rec in _chain_last_wins(md):
        iid = rec.get("intent_id")
        if not iid or rec.get("node_id"):
            continue                       # not minted yet, or already joined (dedup)
        node_key = applied.get(str(iid))
        if not node_key:
            continue                       # intent not ratified yet — stays open
        try:
            stamped = dict(rec)
            stamped["node_id"] = node_key
            stamped["ts"] = _now()
            _append_jsonl(chain_p, stamped)
        except Exception:
            continue
        joined.append({"id": rec.get("id"), "intent_id": iid, "node_id": node_key})

    return {"joined": joined}


# ---- moved from laplace.web.derivation_surface (2026-10-21, core native/physical closure)
_DERIVATIONS_REL = "aspiration/derivations"




def read_sheet(md: str | Path) -> dict[str, Any]:
    """The joined derivation face for one manuscript, empty when nothing has been
    banked. ``aspiration`` is the maximal-claim boundary condition; ``chain`` is the
    isnad link-by-link (each carrying ``fragment_available`` — a forged ``.tex``
    exists — and, for a ``gap`` link, its named ``why`` + any later contests);
    ``reach`` is how far up the aspiration the attested chain got. The doors block
    names the interaction routes (the evolution-desk idiom)."""
    md = Path(md)
    asp = read_aspiration(md)
    links = read_chain(md)
    r = reach(md)
    why_by_id = {g["id"]: g.get("why") for g in (r.get("frontier_gap") or [])}

    # contests ride the chain ledger as later records carrying ``_contest`` (status
    # unchanged); collect them per link so a contested link shows its grounds.
    contests_by_id: dict[str, list[dict]] = {}
    for raw in _read_jsonl(md / _CHAIN_REL):
        c = raw.get("_contest")
        lid = raw.get("id")
        if isinstance(c, dict) and isinstance(lid, str):
            contests_by_id.setdefault(lid, []).append(
                {"by": c.get("by") or "", "reason": c.get("reason") or "",
                 "at": c.get("at") or raw.get("ts") or ""})

    ddir = md / _DERIVATIONS_REL
    chain: list[dict[str, Any]] = []
    for l in links:
        lid = l["id"]
        chain.append({
            **l,
            "fragment_available": (ddir / f"{lid}.tex").is_file(),
            "why": why_by_id.get(lid) if l["status"] == "gap" else None,
            "contests": contests_by_id.get(lid, []),
        })

    reached = {
        "aspiration_present": r.get("aspiration_present", False),
        "links_total": r.get("links_total", 0),
        "links_attested": r.get("links_attested", 0),
        "depth_attested": r.get("depth_attested", 0),
        "frontier_n": len(r.get("frontier_gap") or []),
        "frontier_gap": r.get("frontier_gap") or [],
    }
    return {
        "present": bool(asp.get("present")) or bool(links),
        "aspiration": asp,
        "chain": chain,
        "reach": reached,
        "law": r.get("law", ""),
        "doors": {
            "sheet": "GET /derivation/sheet?corpus= — the aspiration + chain + reach, "
                     "joined (pure read; every attested link a forged .tex fragment)",
            "fragment": "GET /derivation/fragment?corpus=&link= — one link's forged "
                        ".tex text (read-only, path-fenced to aspiration/derivations/)",
            "rescope": "POST /derivation/rescope {corpus, by, armed, claim, reason?} — "
                       "re-scope the boundary claim by APPENDED revision (the prior "
                       "banks to aspiration_history.jsonl; aspiration.json stays the "
                       "latest-pointer)",
            "forge": "POST /derivation/forge {corpus, link_id, by, armed} — bank a "
                     "work-order for the next forging attempt on a GAP link (offer "
                     "law; an attested link is contested, not re-forged)",
            "contest": "POST /derivation/contest {corpus, link_id, by, armed, reason} "
                       "— append a contest record (status stays; last-wins reads "
                       "unaffected until a re-attestation lands)",
        },
    }
