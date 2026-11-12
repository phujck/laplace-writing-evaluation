"""THE LADDER — target-first transitions: hold the target, move the altitude.

One gesture on a selection token opens SIX rungs over the one substrate — concept ·
argument · prose · evidence · judgment · machine — each a real ``<a href>`` carrying
the selection, with a true count, a declared absence that names its own fix, and an
declared staleness verdict. Pure reads: the join rides the CACHED ``corpus_network``
(``corpus_ingest``), globs asset roots, reads small JSON and the two decision ledgers —
never a subprocess, never an embed, never a rebuild (the PSU boom-guard).

The up-conjugate (this wave, first-class): the rungs are read BY the engine, not painted
beside it. :data:`_RUNG_SOURCES` declares each rung's substrate reader as the SAME
callable the owning surface uses (the bijection clause — every rung has a reader, every
declared reader has a rung); :func:`doors_for` is the one href-composition the desk's
deep-links derive from too, so the desk and the viewer resolve a target through one
function. Drift fails loudly: a store mutation moves the rung's count on the next call.

The route is ``GET /shared/ladder?corpus=&target=&kind=`` (served in ``shared_ui.handle``,
the ``versions`` idiom). 400 on a missing corpus; 404 on an unregistered one (fenced
before any disk touch); 200 with ``target.known:false`` for an unresolvable target (a
helpful panel, never a dead end); a degraded read is a per-rung field, never a 5xx.
"""

from __future__ import annotations
from laplace.core.observe import iso_utc as _iso
from laplace.core.checkout import source_tree

import re
import time as _time
from pathlib import Path
from typing import Any
from urllib.parse import quote

from laplace.engine import altitude

#: an asset target's id shape — ``figure:<stem>`` / ``derivation:<id>`` (asset_model's ids).
_ASSET_RE = re.compile(r"^(figure|derivation):")
#: the URL keys the client passes as ``kind=`` — the key it read off the live URL. A hint
#: in this set WINS over the server grammar (the client knows which selection it holds).
_HINT_KINDS = frozenset({"project", "node", "section", "pid", "beat", "asset", "version", "round"})
#: the fixed rung order (his ruling: one gesture, six rungs, always this order).
_RUNG_ORDER = ("concept", "argument", "prose", "evidence", "judgment", "machine")
#: items shed loudly past this (the golden law, enforced not asserted); counts never reduced.
_LADDER_MAX_BYTES = 16 * 1024
#: per-rung item cap (the panel shows ≤6 exemplars; the count carries the honest total).
_ITEMS_CAP = 6


def _repo_root() -> Path:
    return source_tree()


def _q(s: Any) -> str:
    return quote(str(s), safe="")




def _short(text: str, n: int = 80) -> str:
    t = (text or "").strip()
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


# ═══════════════════════════════════════════════════════════════════════════
# TARGET DETECTION — the client passes the URL key it read; the hint wins. The
# server grammar is the fallback (and the truth when no hint rides).
# ═══════════════════════════════════════════════════════════════════════════
def detect_target(target: str, kind_hint: str = "", corpus: str = "",
                  spine_ids: frozenset[str] = frozenset()) -> dict[str, Any]:
    """Classify ``target`` into one of the seven kinds — project / node / section / pid /
    beat / asset / version — reusing ``altitude.detect_anchor`` for the pid/section/node
    grammar (never re-derived). ``kind_hint`` (the client's URL key) WINS when it names a
    real kind. Returns ``{raw, kind, section, node, anchor}`` — the section/node fields
    ride from the anchor grammar so the door composer needs no second parse."""
    raw = (target or "").strip()
    hint = (kind_hint or "").strip().lower()
    a = altitude.detect_anchor(raw)
    if not raw or raw == (corpus or "").strip():
        kind = "project"
    elif _ASSET_RE.match(raw):
        kind = "asset"
    elif a["kind"] == "pid":
        kind = "pid"
    elif a["kind"] == "section":
        kind = "section"
    elif raw in spine_ids:
        kind = "beat"
    else:
        kind = "node"
    if hint in _HINT_KINDS:                 # the client read the URL key — it wins
        kind = hint
    return {"raw": raw, "kind": kind, "section": a["section"], "node": a["node"], "anchor": a}


# ═══════════════════════════════════════════════════════════════════════════
# DOORS — the ONE href-composition. Pure: reads only the target fields + corpus, no
# store touch. The rung payload rides these hrefs AND the desk's deep-links derive
# from them (the up-conjugate: one target → one set of doors, for every consumer).
# ═══════════════════════════════════════════════════════════════════════════
def _conceptric_door(node: str) -> str:
    return f"/conceptric?node={_q(node)}" if node else "/conceptric"


def _storyboard_door(corpus: str, beat: str = "") -> str:
    href = f"/storyboard?corpus={_q(corpus)}" if corpus else "/storyboard"
    return href + f"#{_q(beat)}" if beat else href


def _artefact_door(corpus: str, node: str = "", section: str = "", version: str = "") -> str:
    href = f"/artefact?corpus={_q(corpus)}"
    if node:
        href += f"&node={_q(node)}"
    if section:
        href += f"&section={_q(section)}"
    if version:
        href += f"&version={_q(version)}"
    return href


def _assets_door(corpus: str, asset: str = "") -> str:
    href = f"/assets?corpus={_q(corpus)}"
    return href + f"&asset={_q(asset)}" if asset else href


def _desk_door(decision: str = "") -> str:
    return f"/desk?decision={_q(decision)}" if decision else "/desk"


def _pipeline_door(corpus: str) -> str:
    return f"/pipeline?project={_q(corpus)}"


def doors_for(corpus: str, target: dict[str, Any]) -> list[dict[str, str]]:
    """The six rung doors for one target — the composition both the ladder payload and the
    desk deep-links ride. ``target`` is a ``detect_target`` dict (or the desk's
    ``{raw,kind,node,section,node_ids}`` shape); optional ``beat`` / ``decision`` fields
    sharpen the argument / judgment doors when the caller has resolved them."""
    node = (target.get("node") or "").strip()
    section = (target.get("section") or "").strip()
    kind = target.get("kind")
    raw = (target.get("raw") or "").strip()
    node_ids = target.get("node_ids") or []
    concept_node = node or (str(node_ids[0]) if node_ids else "")
    beat = (target.get("beat") or "").strip() or section
    version = raw if kind in ("version", "round") else ""
    asset = raw if kind == "asset" else ""
    decision = (target.get("decision") or "").strip()
    return [
        {"id": "concept", "href": _conceptric_door(concept_node)},
        {"id": "argument", "href": _storyboard_door(corpus, beat)},
        {"id": "prose", "href": _artefact_door(corpus, node, section, version)},
        {"id": "evidence", "href": _assets_door(corpus, asset)},
        {"id": "judgment", "href": _desk_door(decision)},
        {"id": "machine", "href": _pipeline_door(corpus)},
    ]


# ═══════════════════════════════════════════════════════════════════════════
# THE RUNG-SOURCE BIJECTION (the up-conjugate). Each rung's substrate reader is the
# SAME callable the owning surface reads through — a rung with no reader, or a reader
# with no rung, fails the census clause. These are the imported callables themselves
# (identity-checked in the test), never name strings.
# ═══════════════════════════════════════════════════════════════════════════
def _rung_sources() -> dict[str, Any]:
    from laplace.research import corpus_ingest as ci
    from laplace.manuscript import storyboard as sb
    from laplace.web import desk
    from laplace.pipeline import asset_model, registry
    return {
        "concept": ci.corpus_network,        # the % NODES / graph substrate (conceptric reads it too)
        "argument": sb.enriched_plan,        # the projection plan / beats (the storyboard's own reader)
        "prose": altitude.section_nodes,     # the % NODES fact source — the reader /artefact's projection uses
        "evidence": asset_model.enumerate_assets,   # the asset roots (the assets surface's reader)
        "judgment": desk.scoped_decisions,   # the feedback + friction decision ledgers (the desk's join)
        "machine": registry.project_states,  # the release state machine (the pipeline's inventory)
    }


def __getattr__(name: str):
    """``ladder._RUNG_SOURCES`` — the bijection resolved LIVE (the census of rung →
    substrate reader). Resolved on access, not captured at import, so each reader IS the
    owning surface's CURRENT function (identity holds even after a surface module reload,
    the plain meaning of "the SAME function the surface uses")."""
    if name == "_RUNG_SOURCES":
        return _rung_sources()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# ═══════════════════════════════════════════════════════════════════════════
# THE RUNG SHAPE — one uniform verdict per rung.
# ═══════════════════════════════════════════════════════════════════════════
def _rung(rid: str, label: str, *, present: bool, count: int, sub: str, href: str,
          items: list | None = None, absent: dict | None = None,
          stale: dict | None = None) -> dict[str, Any]:
    """One rung: present ⇒ count + sub + door + items; absent ⇒ the reason + its fix door.
    ``stale`` carries the degraded-read verdict as a warn chip (prose/evidence), never a
    green paint over a degraded substrate."""
    return {
        "id": rid, "label": label, "present": bool(present),
        "count": int(count), "sub": sub, "href": href if present else "",
        "items": list(items or [])[:_ITEMS_CAP] if present else [],
        "absent": absent if not present else None,
        "stale": stale,
    }


def _absent(reason: str, fix: str, fix_href: str) -> dict[str, str]:
    """An absence: THE fact + THE fix + THE door, and it stops (the text law)."""
    return {"reason": reason, "fix": fix, "fix_href": fix_href}


def _stale_chip(verdict: dict) -> dict | None:
    """The ``read_nodemap`` verdict as a warn chip when the read is degraded (absent OR
    stale) — the fact + the fix, so prose/evidence never paint green over a stale read."""
    if not verdict.get("degraded"):
        return None
    return {"reason": verdict.get("reason") or "the node→region map is degraded",
            "fix": verdict.get("fix") or "", "built_ts": verdict.get("built_ts")}


def _prose_stale_chip(report: list[dict], owning: str | None, project_scope: bool) -> dict | None:
    """The prose rung's OWN staleness organ: the plan→prose projection diff
    (``storyboard.dirty_report`` — the same read ``shared_ui.read_plan_prose`` verdicts).
    The nodemap chip (:func:`_stale_chip`) cannot see this — a plan edit that leaves the
    node→region map untouched still moves the prose off its plan. Per-section for a section
    target; the dirty-section count for the whole project/version. ``None`` when fresh."""
    if not report:
        return None
    fix = "rebuild the projection — the rebuild pane on /storyboard"
    if project_scope:
        n = sum(1 for r in report if r.get("dirty"))
        if not n:
            return None
        return {"reason": f"{n} section(s) stale — the prose no longer matches the plan",
                "fix": fix, "built_ts": None}
    if not owning:
        return None
    row = next((r for r in report if r.get("id") == owning), None)
    if not row or not row.get("dirty"):
        return None
    return {"reason": f"section {owning} stale — the prose no longer matches the plan",
            "fix": fix, "built_ts": None}


# ═══════════════════════════════════════════════════════════════════════════
# THE PAYLOAD.
# ═══════════════════════════════════════════════════════════════════════════
def _enforce_ladder_budget(out: dict) -> None:
    """The byte half of the golden law, ENFORCED not asserted: shed rung ITEMS (never
    counts) loudly until the payload fits ≤16KB. ``omitted`` names how many exemplars
    were shed; ``truncated`` flags it. Counts stay the plain discovered totals."""
    import json

    def _size(o: dict) -> int:
        return len(json.dumps(o, ensure_ascii=False).encode("utf-8"))

    # shed from the item-heaviest rung first, one exemplar at a time, until it fits.
    while _size(out) > _LADDER_MAX_BYTES:
        heaviest = max((r for r in out["rungs"] if r["items"]),
                       key=lambda r: len(r["items"]), default=None)
        if heaviest is None:
            break
        heaviest["items"].pop()
        out["omitted"] += 1
        out["truncated"] = True


def ladder_payload(corpus: str, target: str = "", kind: str = "",
                   repo_root: Path | None = None) -> dict[str, Any] | None:
    """THE ladder read-model for ``corpus`` at ``target`` (the client's ``kind=`` hint
    riding). ``None`` for an unregistered corpus (the route → 404); a payload with
    ``target.known:false`` for a resolvable corpus but unresolvable target (the route →
    200, a helpful panel). Six rungs ALWAYS render; every absence is a rendered reason +
    fix door. Pure reads — the cached network, asset globs, small JSON, two ledgers."""
    from laplace.research import corpus_ingest as ci
    from laplace.web import shared_ui
    from laplace.manuscript import storyboard as sb
    from laplace.web import desk
    from laplace.pipeline import asset_model, registry

    rr = (repo_root or _repo_root()).resolve()
    proj = registry.resolve(corpus)
    if proj is None:                                    # the registry fence → 404 upstream
        return None

    troot = ci.resolve_corpus(rr, corpus)
    net = ci.corpus_network(troot, repo_root=rr, name=corpus) if troot else {"nodes": {}}
    nodes = net.get("nodes", {})
    dg = ci.dep_grade(net) if nodes else {}
    g_max = max(dg.values(), default=0)
    spine_ids = frozenset(b.get("id") for b in net.get("spine", []))

    ctx = registry.project_context(corpus, rr)
    md = ctx.manuscript_dir if ctx is not None else None
    target_dir = ctx.target_dir if ctx is not None else None
    sec_nodes = altitude.section_nodes(target_dir) if target_dir else {}

    t = detect_target(target, kind, corpus, spine_ids)
    kind = t["kind"]
    raw = t["raw"]
    enriched = sb.enriched_plan(corpus)                 # None when the corpus has no plan
    plan_sections = ((enriched.get("sections") or []) + (enriched.get("appendices") or [])
                     if enriched else [])

    # ── resolve the target's node set + owning section (the join every rung keys off) ──
    node_ids: list[str] = []
    owning: str | None = None
    label = corpus
    known = True
    if kind == "project":
        label = corpus
    elif kind in ("version", "round"):
        label = raw                                     # the revision id — the uniform ladder
    elif kind == "asset":
        assets_all = asset_model.enumerate_assets(corpus)
        this = next((a for a in assets_all if a.id == raw), None)
        known = this is not None
        node_ids = list(this.nodes_supported) if this is not None else []
        label = f"{this.kind}: {raw.split(':', 1)[-1]}" if this is not None else raw
    elif kind == "beat":
        known = raw in spine_ids
        anchored = [nid for nid, nd in nodes.items()
                    if ((nd.get("projection") or {}).get("section_ref")) == raw]
        node_ids = ([raw] if raw in nodes else []) + anchored
        label = _short((nodes.get(raw, {}).get("projection") or {}).get("term")
                       or (nodes.get(raw, {}).get("essence")) or raw)
    elif kind == "node":
        known = raw in nodes
        node_ids = [raw] if raw in nodes else []
        label = _short((nodes.get(raw, {}).get("projection") or {}).get("term")
                       or (nodes.get(raw, {}).get("essence")) or raw)
    else:                                               # section / pid
        node_ids = altitude.anchor_node_ids(t["anchor"], sec_nodes, corpus)
        owning = t["section"]
        known = bool(node_ids) or any(s.get("id") == owning for s in plan_sections)
        sec_meta = next((s for s in plan_sections if s.get("id") == owning), None)
        label = _short(sec_meta.get("title") if sec_meta else "") or (owning or raw)

    if kind == "node" and known:
        owning = altitude.owning_section(t["anchor"], sec_nodes, plan_sections, raw)
    elif kind in ("beat", "asset") and node_ids:
        first = node_ids[0]
        owning = altitude.owning_section({"kind": "node", "section": None, "node": first},
                                         sec_nodes, plan_sections, first)

    # the anchor beats (argument): the target's nodes' section_ref ∩ the spine. A
    # project (or a version — the uniform ladder) argues the WHOLE spine.
    if kind in ("project", "version", "round"):
        anchor_beats = sorted(spine_ids)
    else:
        anchor_beats = sorted({(nodes.get(nid, {}).get("projection") or {}).get("section_ref")
                               for nid in node_ids} & spine_ids)
        if kind == "beat" and raw in spine_ids:
            anchor_beats = sorted(set(anchor_beats) | {raw})
    grade = dg.get(raw) if kind in ("node", "beat") and raw in nodes else None

    # the door set for this target (the up-conjugate — the desk rides the same call).
    # detect_anchor sets t['node'] to the raw token, which for a version/round is a
    # revision id and for an asset is the asset id — neither is a graph node, so the
    # concept/prose doors must not carry it. A project/version/round opens the uniform,
    # project-scoped concept (no node focus); an asset opens on its supported node.
    if kind in ("project", "version", "round"):
        door_node = ""
    elif kind == "asset":
        door_node = str(node_ids[0]) if node_ids else ""
    else:
        door_node = t["node"]
    door_target = {**t, "node": door_node, "node_ids": node_ids,
                   "beat": (raw if kind == "beat" else ""),
                   "section": owning or t["section"] or ""}
    doors = {d["id"]: d["href"] for d in doors_for(corpus, door_target)}

    # two staleness organs, each read once. The nodemap verdict (node→region map) rides
    # the evidence chip — asset landings key off that map. The prose chip rides the
    # plan→prose projection diff (dirty_report), the ONLY read that catches a plan edit
    # that leaves the nodemap fresh but moves the prose off its plan.
    nm_stale = _stale_chip(shared_ui.read_nodemap(md))
    prose_report = sb.dirty_report(corpus)
    project_scope = kind in ("project", "version", "round")
    prose_stale = _prose_stale_chip(prose_report, owning, project_scope)

    rungs = [
        _rung_concept(corpus, kind, node_ids, nodes, dg, g_max, len(nodes), doors["concept"]),
        _rung_argument(corpus, enriched, anchor_beats, spine_ids, doors["argument"]),
        _rung_prose(corpus, kind, owning, node_ids, sec_nodes, plan_sections, ctx, raw,
                    doors["prose"], prose_stale),
        _rung_evidence(corpus, kind, raw, node_ids, doors["evidence"], nm_stale),
        _rung_judgment(rr, corpus, node_ids, owning, doors,
                       project_scope=project_scope, raw=raw, kind=kind),
        _rung_machine(corpus, ctx, doors["machine"]),
    ]

    out = {
        "corpus": corpus,
        "target": {"raw": raw, "kind": kind, "known": known, "label": label,
                   "section": owning or t["section"], "node_ids": node_ids,
                   "grade": grade, "spine": anchor_beats},
        "rungs": rungs,
        "budget": {"max_bytes": _LADDER_MAX_BYTES},
        "truncated": False,
        "omitted": 0,
        "generated_ts": _iso(_time.time()),
    }
    _enforce_ladder_budget(out)
    return out


# ── the six rung composers ──────────────────────────────────────────────────
def _rung_concept(corpus, kind, node_ids, nodes, dg, g_max, n_nodes, href):
    """concept ← the graph. For a project: the whole network (n_nodes, g_max, DERIVED
    dep_grade). For a node set: the anchor's nodes and their grades. Door /conceptric,
    node-focused (never a stored-grade slice pin — the derived grade is shown). A version
    (the uniform ladder) rides the whole-network view, like a project."""
    if kind in ("project", "version", "round"):
        present = n_nodes > 0
        sub = f"{n_nodes} nodes, {g_max + 1} grade-shells (derived depth, spine-elevated)"
        items = []
        return _rung("concept", "concept", present=present, count=n_nodes, sub=sub,
                     href=href, items=items,
                     absent=None if present else _absent(
                         "the corpus network has no nodes",
                         "ingest the corpus to build the graph", "/conceptric"))
    present = len(node_ids) > 0
    grades = sorted({dg.get(nid, 0) for nid in node_ids if nid in nodes})
    span = (f"grade {grades[0]}" if len(grades) == 1
            else f"grades {grades[0]}–{grades[-1]}") if grades else "ungraded"
    items = [{"id": nid, "kind": (nodes.get(nid) or {}).get("kind"), "grade": dg.get(nid)}
             for nid in node_ids if nid in nodes][:_ITEMS_CAP]
    return _rung("concept", "concept", present=present, count=len(node_ids),
                 sub=f"{len(node_ids)} node(s), {span}", href=href, items=items,
                 absent=None if present else _absent(
                     "this target resolves to no node in the graph",
                     "locate a node in the conceptric", "/conceptric"))


def _rung_argument(corpus, enriched, anchor_beats, spine_ids, href):
    """argument ← the plan / spine. Present when a projection plan exists (the board is
    real); absent when the corpus has no plan (paper_eigen) — the fix seeds it."""
    if enriched is None:
        return _rung("argument", "argument", present=False, count=0, sub="", href=href,
                     absent=_absent("no projection plan for this corpus",
                                    "seed the narrative spine on the storyboard",
                                    f"/storyboard?corpus={_q(corpus)}"))
    count = len(anchor_beats)
    items = [{"id": b} for b in anchor_beats][:_ITEMS_CAP]
    sub = (f"{count} spine beat(s) argue this target" if count
           else f"no beat anchors this target ({len(spine_ids)} on the spine)")
    return _rung("argument", "argument", present=True, count=count, sub=sub, href=href,
                 items=items)


def _rung_prose(corpus, kind, owning, node_ids, sec_nodes, plan_sections, ctx, raw, href, stale):
    """prose ← the owning section + the materialized artefact (version-pinned for a version
    target). Present when a section owns the target or the project has a compiled artefact;
    carries the nodemap staleness as a warn chip (never green over a stale read)."""
    if kind in ("project", "version", "round"):
        art = ctx.current_artefact if ctx is not None else None
        present = bool(art)
        rev = raw if kind in ("version", "round") else (
            (art or {}).get("revision") if isinstance(art, dict) else None)
        if kind in ("version", "round"):
            sub = f"revision {raw} — the full history is on the version rail"
        else:
            sub = (f"the current artefact (revision {rev})" if rev
                   else "compiled artefact — revision unrecorded")
        return _rung("prose", "prose", present=present, count=1 if present else 0,
                     sub=sub, href=href, stale=stale,
                     absent=None if present else _absent(
                         "no compiled artefact for this project",
                         "run the pipeline to build one",
                         f"/pipeline?project={_q(corpus)}"))
    present = bool(owning)
    n = len(sec_nodes.get(owning, [])) if owning else 0
    sub = (f"section {owning} — {n} node(s) projected" if owning else "")
    return _rung("prose", "prose", present=present, count=n, sub=sub, href=href, stale=stale,
                 absent=None if present else _absent(
                     "no plan section owns this target",
                     "place it in a section on the storyboard",
                     f"/storyboard?corpus={_q(corpus)}"))


def _rung_evidence(corpus, kind, raw, node_ids, href, stale):
    """evidence ← the asset roots (figures + derivations). A node set: the assets whose
    ``nodes_supported`` intersect it. An asset target: the asset itself. Absent when no
    asset supports the target; carries nodemap staleness as a warn chip."""
    from laplace.pipeline import asset_model
    assets = asset_model.enumerate_assets(corpus)
    node_set = set(node_ids)
    if kind == "asset":
        matching = [a for a in assets if a.id == raw]
    elif kind in ("project", "version", "round"):
        matching = assets
    else:
        matching = [a for a in assets if node_set & set(a.nodes_supported)]
    present = len(matching) > 0
    items = [{"id": a.id, "kind": a.kind, "supports": len(a.nodes_supported),
              "landings": len(a.landings)} for a in matching][:_ITEMS_CAP]
    # the tail is the ACTUAL kind split (never the invariant "figures + derivations" gloss,
    # which claimed both kinds even on an all-figure set) — a count the chair acts on.
    nf = sum(1 for a in matching if a.kind == "figure")
    nd = len(matching) - nf
    sub = (f"{len(matching)} asset(s) — {nf} figure(s), {nd} derivation(s)" if present else "")
    return _rung("evidence", "evidence", present=present, count=len(matching), sub=sub,
                 href=href, items=items, stale=stale,
                 absent=None if present else _absent(
                     "no figure or derivation supports this target",
                     "bank an asset in the assets surface",
                     f"/assets?corpus={_q(corpus)}"))


def _rung_judgment(repo, corpus, node_ids, owning, doors, project_scope=False,
                   raw="", kind=""):
    """judgment ← the scoped decision ledgers (feedback + friction). Present when an open
    decision touches the target; absent when none — and the fix is the panel's own ✎ rule
    (POST /corpus/friction banks a fork), the up-affordance that writes through a typed
    door. The door sharpens to ``&decision=<id>`` when exactly one decision stands.

    A node target scopes by its raw id EVEN when that id resolves to no graph node: the
    friction/feedback stores key by the node STRING, so a decision banked on a since-
    renamed/removed node still surfaces on its own judgment rung. A non-empty scope keeps
    the read filtered (``scoped_decisions`` matches ``node in scope``), so an unknown node
    never leaks the project's decisions — only a project/version target reads unscoped."""
    from laplace.web import desk
    scope_ids = list(node_ids)
    if kind == "node" and raw and raw not in scope_ids:
        scope_ids.append(raw)                       # a friction on a now-unresolvable node still lands
    if not project_scope and not scope_ids and not owning:
        return _rung("judgment", "judgment", present=False, count=0, sub="",
                     href=doors["judgment"],
                     absent=_absent("no open decision on this target",
                                    "rule it with the ✎ on the panel head (banks a fork)",
                                    "/corpus/friction"))
    dec = desk.scoped_decisions(repo, corpus, scope_ids, section=owning)
    count = dec["count"]
    present = count > 0
    href = doors["judgment"]
    if count == 1 and dec["rows"]:
        href = _desk_door(str(dec["rows"][0].get("id") or ""))
    items = [{"id": r.get("id"), "class": r.get("class"), "title": r.get("title")}
             for r in dec["rows"]][:_ITEMS_CAP]
    sub = (f"{count} open decision(s) on this target" if present else "")
    return _rung("judgment", "judgment", present=present, count=count, sub=sub, href=href,
                 items=items,
                 absent=None if present else _absent(
                     "no open decision on this target",
                     "rule it with the ✎ on the panel head (banks a fork)",
                     "/corpus/friction"))


def _rung_machine(corpus, ctx, href):
    """machine ← the release state machine (registry.project_states). Present for any
    registered project (NEVER_RUN is a real state); the sub names where the release sits
    and the round count. Door /pipeline?project=."""
    from laplace.pipeline import registry
    row = next((r for r in registry.project_states() if (r.get("name") or "") == corpus), None)
    if row is None:
        return _rung("machine", "machine", present=False, count=0, sub="", href=href,
                     absent=_absent("no pipeline state for this corpus",
                                    "register the project's release state", "/pipeline"))
    state = (row.get("state") or "NEVER_RUN")
    rounds_n = int(row.get("rounds_n") or 0)
    sub = f"{state} · {rounds_n} round(s)"
    return _rung("machine", "machine", present=True, count=rounds_n, sub=sub, href=href,
                 items=[{"state": state, "rounds": rounds_n, "kind": row.get("kind")}])
