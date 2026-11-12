"""the lineage surface — per-project views of the conceptric and its descendants.

The author's commission: a dedicated place to see how a paper's concept graph links
across the map into the manuscript it becomes. Different views of one conceptric and its
descendants — everything the engine already carries, gathered onto one surface.

This surface reads the master node index (:mod:`laplace.pipeline.node_index`), the descent
walker (:mod:`laplace.pipeline.lineage`), and the composed provenance doors
(:mod:`laplace.web.provenance_surface`), and serves five read models plus one page:

  * ``GET /lineage`` — the page (a brief base altitude; the views materialise on focus).
  * ``GET /lineage/brief?corpus=`` — a composed prose glance of the paper's lineage health
    (how many concepts, how many reached the manuscript, how many rendered objects trace
    their origin, what stays unresolved and why), the real counts, the staleness verdict,
    and the empty state when a corpus carries no conceptric or index yet.
  * ``GET /lineage/node?corpus=&node=`` — node-outward: one concept and everything it became.
    Its descendants tree (relation-labelled edges, evidence one act deep), the sections it
    touches, and the paragraphs / equations / assets that realise it, each carrying its join
    provenance worded. Doors to open the node in the editor and in the growth cockpit.
  * ``GET /lineage/object?corpus=&object=`` — object-backward: one rendered object walked back
    through its chain (paragraph -> concept -> the derivation origin, or the isnad rung where
    that is the resolving link). Composed over the provenance door.
  * ``GET /lineage/whole?corpus=`` — the whole graph at a coarse altitude: the sections as
    regions weighted by realisation, and the unresolved objects as their own visible band
    (absence as a first-class region, never hidden).
  * ``GET /lineage/find?corpus=&q=`` — a small finder over the index's concepts and objects,
    for the brief's pickers; label-leading, the id carried as a tail chip.

Read-only but for one door: ``POST /lineage/reindex?corpus=`` mints the per-project
``node_index.json`` (derived state, like a nodemap — it overwrites only that one file). The
five reads never write; a corpus, node, or object that does not resolve returns a composed
body that says what did not resolve, never a bare error blob.

Pure handler module, the scanner-dispatch contract (mirrors ``guide`` / ``assets``): the
scanner owns the HTTP server and dispatches ``/lineage*`` here via :func:`handle`. This
module never starts a server.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_HTML = Path(__file__).resolve().parent / "lineage.html"
_JSON = "application/json; charset=utf-8"


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


def _resolve_corpus(corpus: str) -> str:
    if corpus:
        return corpus
    try:
        from laplace.pipeline import registry
        return registry.default_project(_repo_root())
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# section titles — the plan's human labels, joined so a region names its section.
# ---------------------------------------------------------------------------
def _section_titles(corpus: str) -> tuple[dict[str, str], list[str]]:
    """``{section_id: title}`` plus the section ids in plan order. Empty when the corpus
    has no projection plan (the region falls back to naming the raw section id)."""
    try:
        from laplace.web import shared_ui
        from laplace.manuscript import manuscript_plan
        plan = manuscript_plan.plan_payload(corpus)
    except Exception:
        plan = None
    if not plan:
        return {}, []
    titles: dict[str, str] = {}
    order: list[str] = []
    for s in plan.get("sections") or []:
        sid = s.get("id")
        if sid:
            titles[sid] = s.get("title") or sid
            order.append(sid)
    return titles, order


# ---------------------------------------------------------------------------
# THE BRIEF — a composed prose glance of the paper's lineage health.
# ---------------------------------------------------------------------------
def _plural(n: int, one: str, many: str | None = None) -> str:
    return one if n == 1 else (many or one + "s")


def brief_payload(corpus: str, root: Path | None = None) -> dict | None:
    """The composed base-altitude glance plus the counts, staleness, and (when the corpus
    resolves but has no index) the instructive empty state. ``None`` when the corpus does
    not resolve to a manuscript at all."""
    corpus = _resolve_corpus(corpus)
    if not corpus:
        return None
    from laplace.pipeline import node_index as ni
    index, freshness = ni.get_index(corpus, root)
    if index is None:
        # the corpus resolves to no manuscript / conceptric — the instructive empty state.
        return {
            "corpus": corpus, "present": False,
            "glance": (f"{corpus} has no concept graph on this surface yet. Once its corpus is "
                       "folded into a conceptric and a manuscript is projected, this brief will "
                       "read how many concepts it holds, how many reached the paper, and which "
                       "rendered objects trace their origin."),
            "empty": {"what_it_would_show": [
                "the concept count and how many realise into the manuscript",
                "every rendered object walked back to the concept it argues",
                "the whole graph as regions, with the unresolved objects as their own band"],
                "what_builds_it": "fold the corpus into a conceptric, then project the "
                                  "manuscript; the master index is minted from those sources"},
            "counts": {}, "staleness": None, "remint": None,
        }

    c = index.get("counts") or {}
    nodes = index.get("nodes") or {}
    objects = index.get("objects") or {}
    concepts = c.get("conceptric_nodes", len(nodes))
    realised = sum(1 for m in nodes.values()
                   if (m.get("paragraph_ids") or m.get("equations") or m.get("asset_id")))
    rendered = c.get("objects", len(objects))
    resolved = sum(1 for o in objects.values()
                   if o.get("conceptric_nodes") or o.get("origin_node"))
    n_eq = c.get("equations", 0)
    n_eq_res = c.get("equations_resolved", 0)
    unresolved = index.get("unresolved") or []
    n_un = len(unresolved)
    # the unresolved band, grouped by kind with a worded reason for the group.
    by_kind: dict[str, int] = {}
    for u in unresolved:
        by_kind[u.get("kind") or "object"] = by_kind.get(u.get("kind") or "object", 0) + 1
    band = []
    _reason = {
        "paragraph": "paragraphs that realise no concept node",
        "figure": "figures the concept graph does not yet claim",
        "derivation": "derivations that land as figures without a substrate concept",
        "equation": "equations with no resolving join",
    }
    for kind, n in sorted(by_kind.items(), key=lambda kv: -kv[1]):
        band.append({"kind": kind, "n": n,
                     "reason": _reason.get(kind, f"{kind} objects with no resolved origin")})

    # the composed glance — plain words, the internal ids held back for the views.
    band_clause = ""
    if band:
        parts = [f"{b['n']} {b['reason']}" for b in band]
        if len(parts) == 1:
            band_clause = parts[0]
        elif len(parts) == 2:
            band_clause = parts[0] + " and " + parts[1]
        else:
            band_clause = ", ".join(parts[:-1]) + ", and " + parts[-1]
    eq_clause = ""
    if n_eq:
        eq_clause = (f" Every one of the {n_eq} {_plural(n_eq, 'equation')} among them resolves "
                     "through its derivation." if n_eq_res == n_eq
                     else f" {n_eq_res} of the {n_eq} equations among them resolve through a "
                          "derivation; the rest stay open.")
    glance = (
        f"{corpus} holds {concepts} {_plural(concepts, 'concept')}; "
        f"{realised} of them reached the manuscript as prose. Of {rendered} rendered "
        f"{_plural(rendered, 'object')}, {resolved} trace back to the concept they argue."
        + eq_clause
        + (f" {n_un} {_plural(n_un, 'object')} {'stays' if n_un == 1 else 'stay'} unresolved: "
           f"{band_clause}." if n_un else " Nothing is left unresolved.")
    )

    remint = {
        "route": "POST /lineage/reindex",
        "label": "re-mint the index",
        "writes": "the per-project node_index.json (derived state; only that one file)",
        "psu": "local-safe",
    }
    return {
        "corpus": corpus, "present": True,
        "glance": glance,
        "counts": {
            "concepts": concepts, "realised": realised,
            "rendered": rendered, "resolved": resolved,
            "equations": n_eq, "equations_resolved": n_eq_res,
            "paragraphs": c.get("paragraphs", 0), "assets": c.get("assets", 0),
            "unresolved": n_un,
        },
        "band": band,
        "sources": index.get("sources") or {},
        "staleness": _staleness_note(freshness),
        "remint": remint,
    }


def _staleness_note(freshness: dict) -> dict:
    """The brief's staleness verdict in the shape the .hy-stale idiom reads, so the note
    surfaces in place with a fix that names the re-mint door (never a silent stale index)."""
    minted = bool(freshness.get("minted"))
    fresh = bool(freshness.get("fresh"))
    if not minted:
        return {"present": False, "fresh": True,
                "reason": "built in memory — no minted index on disk yet",
                "built_ts": None, "fix": "re-mint the index to bank it on disk"}
    return {
        "present": True, "fresh": fresh,
        "reason": (None if fresh else "the minted index is older than its sources — "
                   "a concept, plan, or prose file moved since it was built"),
        "built_ts": freshness.get("minted") if isinstance(freshness.get("minted"), str) else None,
        "fix": ("the minted index matches its sources" if fresh
                else "re-mint the index to refresh it"),
    }


# ---------------------------------------------------------------------------
# THE FINDER — a small list over concepts + objects, for the brief's pickers.
# ---------------------------------------------------------------------------
def find_payload(corpus: str, q: str, root: Path | None = None,
                 limit: int = 24) -> dict | None:
    """Concepts and objects matching ``q`` (a substring of the id or the label), each row
    label-leading with the id carried as a tail chip. ``None`` when the corpus has no index."""
    corpus = _resolve_corpus(corpus)
    if not corpus:
        return None
    from laplace.pipeline import node_index as ni
    index, _ = ni.get_index(corpus, root)
    if index is None:
        return None
    ql = (q or "").strip().lower()
    nodes = index.get("nodes") or {}
    objects = index.get("objects") or {}

    def _hit(idv: str, label: str) -> bool:
        if not ql:
            return True
        return ql in idv.lower() or ql in (label or "").lower()

    concept_rows = []
    for nid, m in nodes.items():
        label = m.get("label") or ""
        if not _hit(nid, label):
            continue
        n_real = len(m.get("paragraph_ids") or []) + len(m.get("equations") or []) \
            + (1 if m.get("asset_id") else 0)
        concept_rows.append({"id": nid, "label": label, "kind": m.get("kind") or "",
                             "section": m.get("section"), "realises": n_real})
    # weight: nodes that realise more sort first (they show the richest lineage outward).
    concept_rows.sort(key=lambda r: (-r["realises"], r["id"]))

    object_rows = []
    for oid, o in objects.items():
        # paragraphs are addressed node-outward, not object-backward; the finder's object
        # side offers the rendered objects a reader points at — equations, figures, assets.
        if o.get("kind") == "paragraph":
            continue
        if not _hit(oid, ""):
            continue
        resolved = bool(o.get("conceptric_nodes") or o.get("origin_node"))
        object_rows.append({"id": oid, "kind": o.get("kind") or "object",
                            "page": o.get("page"), "resolved": resolved,
                            "join": o.get("join")})
    object_rows.sort(key=lambda r: (0 if r["resolved"] else 1, r["id"]))

    return {"corpus": corpus, "q": q,
            "concepts": concept_rows[:limit], "objects": object_rows[:limit],
            "n_concepts": len(concept_rows), "n_objects": len(object_rows)}


# ---------------------------------------------------------------------------
# NODE-OUTWARD — one concept and everything it became.
# ---------------------------------------------------------------------------
def _realises_for(index: dict, nid: str) -> dict:
    """The rendered objects that realise a concept, each with its join provenance worded:
    the paragraphs (prose provenance), the equations (their eq->node join), and the asset."""
    nodes = index.get("nodes") or {}
    objects = index.get("objects") or {}
    m = nodes.get(nid) or {}
    paras = []
    for pid in m.get("paragraph_ids") or []:
        po = objects.get(pid) or {}
        paras.append({"id": pid, "function": po.get("function") or "",
                      "proposition": (po.get("proposition") or "")[:200],
                      "section": po.get("section"),
                      "join": po.get("join") or "prose",
                      "provenance": po.get("join_provenance")
                      or ["realised in prose — the paragraph names this concept"]})
    eqs = []
    for label in m.get("equations") or []:
        eo = objects.get(label) or {}
        eqs.append({"id": label, "page": eo.get("page"),
                    "join": eo.get("join") or "",
                    "origin": eo.get("origin_gloss"),
                    "provenance": eo.get("join_provenance") or []})
    asset = None
    aid = m.get("asset_id")
    if aid:
        ao = objects.get(aid) or {}
        asset = {"id": aid, "kind": ao.get("kind") or "asset", "page": ao.get("page"),
                 "join": ao.get("join") or "", "provenance": ao.get("join_provenance") or []}
    return {"paragraphs": paras, "equations": eqs, "asset": asset}


def node_payload(corpus: str, node: str, depth: int = 0,
                 root: Path | None = None) -> dict | None:
    """Node-outward: the descendants tree joined to the objects that realise the concept,
    each with its join provenance and its crossings (editor / growth-cockpit doors).
    ``None`` when the corpus conceptric does not resolve; an unknown node returns a
    composed ``present: False`` body."""
    corpus = _resolve_corpus(corpus)
    if not corpus:
        return None
    from laplace.web import provenance_surface as pr
    from laplace.pipeline import node_index as ni
    walk = pr.descendants_payload(corpus, node, depth, root)
    if walk is None:
        return None
    index, freshness = ni.get_index(corpus, root)
    index = index or {"nodes": {}, "objects": {}}
    nodes_meta = index.get("nodes") or {}
    meta = nodes_meta.get(node) or {}

    if not walk.get("present"):
        return {"corpus": corpus, "node": node, "present": False,
                "glance": walk.get("glance") or (f"No concept named {node!r} is in "
                                                 f"{corpus}'s graph, so it has no lineage."),
                "audit": walk.get("audit") or {"ids": [node]}}

    realises = _realises_for(index, node)
    working = walk.get("working") or {}
    titles, _order = _section_titles(corpus)
    label = meta.get("label") or ""
    kind = meta.get("kind") or ""
    section = meta.get("section")
    section_title = titles.get(section, section) if section else None
    sections_touched = [{"id": s, "title": titles.get(s, s)}
                        for s in (working.get("sections_touched") or [])]
    n_desc = working.get("n_descendants", 0)
    n_par = len(realises["paragraphs"])
    n_eq = len(realises["equations"])
    has_asset = bool(realises["asset"])

    # a composed sentence naming the concept and the reach — the label leads, the id is held
    # for the identity chip in the view. A long parameter label is trimmed to its first
    # clause so the glance reads as a sentence, not a spilled definition.
    lead = (label or "this concept").strip()
    for stop in (". ", "; ", " = ", " ("):
        i = lead.find(stop)
        if 0 < i <= 64:
            lead = lead[:i]
            break
    if len(lead) > 72:
        lead = lead[:71].rstrip() + "…"
    realise_bits = []
    if n_par:
        realise_bits.append(f"{n_par} {_plural(n_par, 'paragraph')}")
    if n_eq:
        realise_bits.append(f"{n_eq} {_plural(n_eq, 'equation')}")
    if has_asset:
        realise_bits.append("a rendered asset")
    realise_clause = (" It realises into " + (", ".join(realise_bits[:-1]) + " and " + realise_bits[-1]
                      if len(realise_bits) > 1 else realise_bits[0]) + "."
                      if realise_bits else " Nothing in the manuscript realises it directly yet.")
    if n_desc:
        glance = (f"{lead} leads to {n_desc} {_plural(n_desc, 'descendant')} across "
                  f"{len(working.get('sections_touched') or [])} "
                  f"{_plural(len(working.get('sections_touched') or []), 'section')}."
                  + realise_clause)
    else:
        glance = (f"{lead} is a leaf — nothing descends from it." + realise_clause)

    # the crossings every node row carries: the editor and the growth cockpit, corpus-scoped.
    from urllib.parse import quote
    cq = quote(corpus)
    nq = quote(node)
    doors = {
        "editor": {"label": "open in the editor", "href": f"/artefact?corpus={cq}&node={nq}"},
        "grow": {"label": "open in Grow", "href": f"/conceptric?corpus={cq}&node={nq}"},
    }
    return {
        "corpus": corpus, "node": node, "present": True,
        "glance": glance,
        "identity": {"id": node, "label": label, "kind": kind, "section": section,
                     "section_title": section_title},
        "descendants": {
            "tree": working.get("tree"),
            "n": n_desc,
            "sections_touched": working.get("sections_touched") or [],
            "sections": sections_touched,
            "edges": (walk.get("audit") or {}).get("edges") or [],
            "health": (walk.get("audit") or {}).get("health") or {},
        },
        "realises": realises,
        "doors": doors,
        "staleness": _staleness_note(freshness),
    }


# ---------------------------------------------------------------------------
# OBJECT-BACKWARD — one rendered object walked back through its chain.
# ---------------------------------------------------------------------------
def object_payload(corpus: str, object_ref: str,
                   root: Path | None = None) -> dict | None:
    """Object-backward: the chain from a rendered object back to the concept it argues and
    the derivation origin (the isnad rung where that resolves it). Composed over the
    provenance door, then re-shaped into ordered walk steps with the crossings the row
    carries. ``None`` when the corpus does not resolve; an unknown object returns a
    composed ``resolved: False`` body."""
    corpus = _resolve_corpus(corpus)
    if not corpus:
        return None
    from laplace.web import provenance_surface as pr
    from laplace.pipeline import node_index as ni
    prov = pr.provenance_payload(corpus, object_ref, root)
    if prov is None:
        return None
    corpus = prov.get("corpus", corpus)
    if not prov.get("resolved"):
        index, _ = ni.get_index(corpus, root)
        return pr._compose_object_404(corpus, object_ref, index)

    working = prov.get("working") or {}
    audit = prov.get("audit") or {}
    # the ordered walk back: the object, then its paragraph (if any), then the concept(s), then
    # the derivation origin (the isnad rung). Each step names where the step was read from.
    steps: list[dict] = []
    steps.append({"stage": "object", "label": object_ref,
                  "detail": prov.get("glance") or "",
                  "note": f"page {working.get('page')}" if working.get("page") else ""})
    para = working.get("paragraph")
    if para:
        steps.append({"stage": "paragraph", "label": para.get("spec_id") or "",
                      "detail": (para.get("proposition") or "")[:220],
                      "note": (para.get("function") or "")})
    concept_nodes = working.get("conceptric_nodes") or []
    for cn in concept_nodes:
        steps.append({"stage": "concept", "label": cn.get("label") or cn.get("id") or "",
                      "detail": cn.get("kind") or "", "id": cn.get("id"),
                      "note": "the concept the object argues"})
    isnad = working.get("isnad")
    if isnad and (isnad.get("origin") or isnad.get("origin_node") or isnad.get("link")):
        steps.append({"stage": "origin", "label": isnad.get("origin") or "the derivation origin",
                      "detail": "", "id": isnad.get("origin_node"),
                      "note": "the derivation link where the object was authored — its "
                              "resolving rung"})

    from urllib.parse import quote
    cq = quote(corpus)
    oq = quote(object_ref)
    # the door must land the traced object under the eye, not just the corpus: the artefact
    # surface's cold deep-link reads ?object=<id> (openDeepLinkedObject in artefact-panes.mjs)
    # and opens straight to that object's provenance pane — the same param name, so the walk
    # back here hands off into the walk forward there on the SAME object.
    doors = {"editor": {"label": "open in the editor",
                        "href": f"/artefact?corpus={cq}&object={oq}"}}
    # a concept in the chain carries a crossing back into node-outward (the inverse walk).
    if concept_nodes:
        doors["node_outward"] = {"label": "see this concept outward",
                                 "id": concept_nodes[0].get("id")}
        doors["grow"] = {"label": "open in Grow",
                         "href": f"/conceptric?corpus={cq}&node={quote(concept_nodes[0].get('id') or '')}"}

    return {
        "corpus": corpus, "object": object_ref, "resolved": True,
        "glance": prov.get("glance") or "",
        "steps": steps,
        "join": audit.get("join"),
        "join_provenance": audit.get("join_provenance") or [],
        "doors": doors,
        "staleness": (audit.get("staleness") or {}),
    }


# ---------------------------------------------------------------------------
# THE WHOLE — the graph at a coarse altitude: sections as regions, the unresolved band.
# ---------------------------------------------------------------------------
def whole_payload(corpus: str, root: Path | None = None) -> dict | None:
    """The whole graph as regions: each section a region weighted by how much realises in
    it, plus the unresolved objects gathered into their own band (absence as a region).
    ``None`` when the corpus has no index."""
    corpus = _resolve_corpus(corpus)
    if not corpus:
        return None
    from laplace.pipeline import node_index as ni
    index, freshness = ni.get_index(corpus, root)
    if index is None:
        return None
    nodes = index.get("nodes") or {}
    objects = index.get("objects") or {}
    titles, order = _section_titles(corpus)

    # per-section tallies: concepts placed there, concepts that realise, and objects landing.
    reg: dict[str, dict] = {}

    def _touch(sid: str) -> dict:
        return reg.setdefault(sid, {"id": sid, "title": titles.get(sid, sid),
                                    "concepts": 0, "realised": 0, "objects": 0})

    unplaced_key = "__unplaced__"
    for nid, m in nodes.items():
        sid = m.get("section") or unplaced_key
        r = _touch(sid)
        r["concepts"] += 1
        if m.get("paragraph_ids") or m.get("equations") or m.get("asset_id"):
            r["realised"] += 1
    for oid, o in objects.items():
        sid = o.get("section")
        if not sid:
            continue
        _touch(sid)["objects"] += 1

    # order: plan order first, then any sections not in the plan, then unplaced last.
    ordered_ids = [s for s in order if s in reg] + \
        [s for s in reg if s not in order and s != unplaced_key]
    regions = []
    max_w = 1
    for sid in ordered_ids:
        r = reg[sid]
        w = r["objects"] + r["realised"]
        r["weight"] = w
        max_w = max(max_w, w)
        regions.append(r)
    if unplaced_key in reg:
        r = reg[unplaced_key]
        r["id"] = None
        r["title"] = "unplaced concepts"
        r["weight"] = r["objects"] + r["realised"]
        max_w = max(max_w, r["weight"])
        regions.append(r)
    for r in regions:
        r["weight_frac"] = round(r["weight"] / max_w, 3) if max_w else 0.0

    # the unresolved band — its own region, the objects grouped by kind with worded reasons.
    unresolved = index.get("unresolved") or []
    by_kind: dict[str, list[dict]] = {}
    for u in unresolved:
        by_kind.setdefault(u.get("kind") or "object", []).append(u)
    _reason = {
        "paragraph": "realise no concept node",
        "figure": "the concept graph does not yet claim them",
        "derivation": "land as figures without a substrate concept",
        "equation": "carry no resolving join",
    }
    groups = []
    for kind, rows in sorted(by_kind.items(), key=lambda kv: -len(kv[1])):
        groups.append({"kind": kind, "n": len(rows),
                       "reason": _reason.get(kind, "carry no resolved origin"),
                       "sample": [rrow.get("object") for rrow in rows[:8]]})

    c = index.get("counts") or {}
    glance = (f"{corpus}'s graph spreads across {len([r for r in regions if r['id']])} "
              f"sections. The bands below weight each region by how much of the manuscript "
              f"realises in it; the unresolved band gathers the "
              f"{len(unresolved)} {_plural(len(unresolved), 'object')} the graph does not "
              "yet place.")
    return {
        "corpus": corpus, "present": True, "glance": glance,
        "regions": regions,
        "unresolved": {"n": len(unresolved), "groups": groups},
        "counts": {"concepts": c.get("conceptric_nodes", len(nodes)),
                   "objects": c.get("objects", len(objects))},
        "staleness": _staleness_note(freshness),
    }


# ---------------------------------------------------------------------------
# the HTTP handler (the scanner-dispatch contract).
# ---------------------------------------------------------------------------
def handle(path: str, query: dict, method: str,
           body: bytes) -> tuple[int, str, bytes] | None:
    """Route one ``/lineage*`` request. Returns (status, content_type, body) or ``None``
    when the path is not ours (the scanner falls through). Every read is GET; the one
    write is ``POST /lineage/reindex``."""
    if path != "/lineage" and not path.startswith("/lineage/"):
        return None
    method = (method or "GET").upper()

    if path == "/lineage":
        if method != "GET":
            return _json_resp(405, {"error": f"{method} not allowed — /lineage is a page"})
        if not _HTML.is_file():
            return _json_resp(500, {"error": "lineage.html missing on disk"})
        return 200, "text/html; charset=utf-8", _HTML.read_bytes()

    # the one write door: mint the per-project node_index.json (derived state).
    if path == "/lineage/reindex":
        if method != "POST":
            return _json_resp(405, {"error": f"{method} not allowed — reindex is POST"})
        corpus = _resolve_corpus(_q1(query, "corpus"))
        if not corpus:
            return _json_resp(400, {"error": "corpus is required"})
        from laplace.pipeline import derived_writes, node_index as ni
        # the read-only case is answered FIRST and by its own name: minting is gated
        # (WO-20260817-test-mutates-working-tree), and a shut gate returning None must
        # never be reported as "no manuscript resolves" — that is the wrong absence.
        note = derived_writes.read_only_note()
        if note:
            return _json_resp(503, {"error": note, "corpus": corpus, "minted": False,
                                    "glance": f"did not mint {corpus} — {note}."})
        p = ni.write_node_index(corpus)
        if p is None:
            return _json_resp(404, {"error": f"no manuscript resolves for {corpus!r} — "
                                    "nothing to mint"})
        return _json_resp(200, {"corpus": corpus, "minted": True,
                                "wrote": "node_index.json",
                                "glance": f"re-minted the index for {corpus}."})

    if method != "GET":
        return _json_resp(405, {"error": f"{method} not allowed — {path} is read-only"})

    if path == "/lineage/brief":
        out = brief_payload(_q1(query, "corpus"))
        if out is None:
            rc = _q1(query, "corpus") or "(none active)"
            return _json_resp(404, {"corpus": rc, "present": False,
                                    "glance": f"No project resolves for {rc!r}."})
        return _json_resp(200, out)

    if path == "/lineage/find":
        out = find_payload(_q1(query, "corpus"), _q1(query, "q"))
        if out is None:
            return _json_resp(404, {"error": f"no index for corpus {_q1(query, 'corpus')!r}"})
        return _json_resp(200, out)

    if path == "/lineage/node":
        node = _q1(query, "node")
        if not node:
            return _json_resp(400, {"error": "node is required (a concept id)"})
        try:
            depth = int(_q1(query, "depth", "0"))
        except ValueError:
            depth = 0
        out = node_payload(_q1(query, "corpus"), node, depth)
        if out is None:
            return _json_resp(404, {"corpus": _q1(query, "corpus"), "node": node,
                                    "present": False,
                                    "glance": "No conceptric resolves for this corpus."})
        if not out.get("present"):
            return _json_resp(404, out)
        return _json_resp(200, out)

    if path == "/lineage/object":
        obj = _q1(query, "object")
        if not obj:
            return _json_resp(400, {"error": "object is required (a label, concept id, or asset id)"})
        out = object_payload(_q1(query, "corpus"), obj)
        if out is None:
            return _json_resp(404, {"corpus": _q1(query, "corpus"), "object": obj,
                                    "resolved": False,
                                    "glance": "No manuscript resolves for this corpus."})
        if not out.get("resolved"):
            return _json_resp(404, out)
        return _json_resp(200, out)

    if path == "/lineage/whole":
        out = whole_payload(_q1(query, "corpus"))
        if out is None:
            return _json_resp(404, {"corpus": _q1(query, "corpus"), "present": False,
                                    "glance": "No index resolves for this corpus."})
        return _json_resp(200, out)

    return _json_resp(404, {"error": f"no lineage route {path!r}"})
