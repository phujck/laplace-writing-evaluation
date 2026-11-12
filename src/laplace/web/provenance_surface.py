"""the provenance + lineage doors — two read surfaces over the master node index.

The author ruled the instrument: in the editor, open a pane on an equation or a figure and
see where it came from; and, over the conceptric, a lineage surface for a node and its
descendants. This module serves the data behind those panes as two GET-only doors, each
composed in the engine's block grammar — a glance sentence a reader acts on, a working
block with the fields, and an audit block whose ``join_provenance`` names which table each
fact was read from.

  * ``GET /provenance/object?corpus=&object=`` — one rendered object (a tex label, a
    conceptric id, an asset id, or a paragraph spec id) resolved across the five id
    namespaces through :mod:`laplace.pipeline.node_index`. Glance: a composed sentence
    naming the object, where it came from, and where it lands. Working: the concept
    nodes, section, paragraph function, isnad origin, and asset landings. Audit: the join
    and its per-field provenance, plus a staleness note when the minted index is older
    than its sources.
  * ``GET /descendants/node?corpus=&node=&depth=`` — a conceptric node and everything it
    leads to, walked by :mod:`laplace.pipeline.lineage`. Glance: the descendant, section,
    asset, and finding counts in words. Working: the recursive tree, the sections and
    assets touched, and the equations under it. Audit: the raw descent edges with their
    evidence, the graph health, and the staleness note.

Read-only, by the actor-honesty law: neither door writes. A corpus, object, or node that
does not resolve returns a composed 404 body that says what did not resolve — never a bare
error blob.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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
# open findings — count findings anchored on a node set (read-only, best-effort).
# ---------------------------------------------------------------------------
def _open_findings_for(corpus: str, node_ids: set[str]) -> list[dict]:
    """Every open finding anchored to a node in ``node_ids``, off the feedback ledger the
    review surface writes. Declared empty when there is no ledger — never a fabricated count."""
    if not node_ids:
        return []
    try:
        from laplace.manuscript import review_surface as rs
        from laplace.manuscript import manuscript_bridge as mb
        from laplace.pipeline.suppress import _finding_node
    except Exception:
        return []
    md = rs.manuscript_dir(corpus, "")
    if md is None:
        return []
    ledger = md / "feedback" / "feedback.jsonl"
    if not ledger.is_file():
        return []
    project = rs._project_name(corpus, md)
    out: list[dict] = []
    for rec in mb.feedback_list(_repo_root(), project, ledger=ledger).get("records", []):
        if rec.get("status") not in (None, "open"):
            continue
        where = _finding_node(rec)
        if where in node_ids:
            out.append({"id": rec.get("id"), "node": where,
                        "comment": (rec.get("comment") or "")[:160],
                        "by": rec.get("by") or "", "ts": rec.get("ts") or ""})
    return out


def _staleness(freshness: dict) -> dict:
    """The audit staleness note both doors carry: whether the served index still matches
    its sources, and which dependency moved when it does not."""
    return {"index_minted": freshness.get("minted"),
            "fresh": freshness.get("fresh"),
            "moved": freshness.get("moved") or [],
            "note": freshness.get("note")}


# ---------------------------------------------------------------------------
# THE PROVENANCE DOOR — GET /provenance/object
# ---------------------------------------------------------------------------
def _compose_object_glance(corpus: str, ref: str, rec: dict) -> str:
    """A composed sentence: the object, where it came from, and where it lands — plain
    words, the internal slugs held back for the audit block."""
    kind = rec.get("kind") or rec.get("resolved_kind") or "object"
    page = rec.get("page")
    where = f" on page {page} of {corpus}" if page else f" in {corpus}"
    if kind == "equation":
        origin = rec.get("origin_gloss")
        conc = rec.get("conceptric_nodes") or []
        if conc:
            return (f"{ref} is an equation{where}; it argues the concept the manuscript "
                    "realises in prose, and its provenance traces through that paragraph.")
        if origin:
            return (f"{ref} is an equation{where}; it was authored inside the derivation of "
                    f"{origin}, and carries that derivation as where it came from.")
        return (f"{ref} is an equation{where}; no paragraph or derivation resolves its "
                "concept yet, so its origin is stated as open.")
    if kind in ("figure", "derivation"):
        conc = rec.get("conceptric_nodes") or []
        if conc:
            return (f"{ref} is a {kind}{where}; it supports a named concept node and lands "
                    "in the rendered artefact.")
        if rec.get("landings"):
            return (f"{ref} is a {kind}{where}; it lands in the rendered artefact, but no "
                    "conceptric node claims it yet, so its concept is stated as open.")
        return f"{ref} is a {kind} in {corpus}; it has no reader landing yet."
    if kind == "paragraph":
        conc = rec.get("conceptric_nodes") or []
        fn = (rec.get("function") or "").strip()
        lead = f"{ref} is a paragraph{where}"
        if conc:
            return (lead + f"; it realises {len(conc)} concept node"
                    + ("" if len(conc) == 1 else "s")
                    + (f", and its job is {fn.rstrip('.').lower()}." if fn else "."))
        return lead + "; it realises no concept node, stated as open."
    if rec.get("resolved_kind") == "conceptric_node":
        sec = rec.get("section")
        seg = f", carried in section {sec}" if sec else ""
        return (f"{ref} is a concept node in {corpus}{seg}; the objects that realise it are "
                "listed under working.")
    return f"{ref} resolves in {corpus}; its detail is under working."


def provenance_payload(corpus: str, object_ref: str,
                       root: Path | None = None) -> dict | None:
    """Resolve one object across namespaces and compose its provenance block. ``None`` when
    the corpus does not resolve (a 404 with the corpus named); a resolved corpus with an
    unresolvable object returns a dict carrying ``resolved: False`` for the composed 404."""
    corpus = _resolve_corpus(corpus)
    if not corpus:
        return None
    from laplace.pipeline import node_index as ni
    index, freshness = ni.get_index(corpus, root)
    if index is None:
        return None
    rec = ni.resolve_object(index, object_ref)
    if rec is None:
        return {"resolved": False, "corpus": corpus, "object": object_ref}

    conc = rec.get("conceptric_nodes") or []
    nodes_meta = index.get("nodes") or {}
    concept_nodes = [{"id": n, "label": (nodes_meta.get(n) or {}).get("label", ""),
                      "kind": (nodes_meta.get(n) or {}).get("kind", "")} for n in conc]
    # the paragraph block (for an equation joined spatially, or a paragraph object).
    paragraph = None
    pid = rec.get("paragraph_id") or (object_ref if rec.get("kind") == "paragraph" else None)
    if pid and pid in (index.get("objects") or {}):
        po = index["objects"][pid]
        paragraph = {"spec_id": pid, "function": po.get("function"),
                     "proposition": po.get("proposition"),
                     "nodes_realised": po.get("conceptric_nodes")}
    findings = _open_findings_for(corpus, set(conc))
    glance = _compose_object_glance(corpus, object_ref, rec)
    working = {
        "conceptric_nodes": concept_nodes,
        "section": rec.get("section"),
        "page": rec.get("page"),
        "paragraph": paragraph,
        "isnad": ({"link": rec.get("isnad_link"), "origin_node": rec.get("origin_node"),
                   "origin": rec.get("origin_gloss")}
                  if rec.get("isnad_link") or rec.get("origin_node") else None),
        "asset_landings": rec.get("landings") or [],
        "node_id": rec.get("node_id"),
    }
    audit = {
        "join": rec.get("join"),
        "join_provenance": rec.get("join_provenance") or [],
        "resolved_kind": rec.get("resolved_kind"),
        "open_findings": findings,
        "ids": [object_ref] + list(conc)
               + ([rec.get("origin_node")] if rec.get("origin_node") else []),
        "staleness": _staleness(freshness),
    }
    return {"resolved": True, "corpus": corpus, "object": object_ref,
            "glance": glance, "working": working, "audit": audit}


def _compose_object_404(corpus: str, object_ref: str, index: dict | None) -> dict:
    n = len((index or {}).get("objects") or {}) + len((index or {}).get("nodes") or {})
    return {
        "resolved": False, "corpus": corpus, "object": object_ref,
        "glance": (f"Nothing named {object_ref!r} resolves in {corpus}. It is not a tex "
                   "label, a concept node, an asset, or a paragraph the index carries."),
        "working": {"searched": ["tex labels", "conceptric ids", "asset ids",
                                 "paragraph spec ids"],
                    "index_objects": n},
        "audit": {"reason": "no cross-namespace match in the master node index",
                  "ids": [object_ref]},
    }


# ---------------------------------------------------------------------------
# THE LINEAGE DOOR — GET /descendants/node
# ---------------------------------------------------------------------------
def _sections_and_assets_for(index: dict, node_ids: list[str]) -> tuple[list[str], list[dict], list[str]]:
    """The sections touched, the assets, and the equations under a set of descendant node
    ids — read off the master index's node records (one truth, no re-derivation)."""
    nodes_meta = index.get("nodes") or {}
    sections: list[str] = []
    assets: list[dict] = []
    equations: list[str] = []
    for nid in node_ids:
        meta = nodes_meta.get(nid) or {}
        sec = meta.get("section")
        if sec and sec not in sections:
            sections.append(sec)
        aid = meta.get("asset_id")
        if aid and aid not in {a["id"] for a in assets}:
            assets.append({"id": aid, "node": nid})
        for eq in meta.get("equations") or []:
            if eq not in equations:
                equations.append(eq)
    return sections, assets, equations


def descendants_payload(corpus: str, node: str, depth: int,
                        root: Path | None = None) -> dict | None:
    """Walk a node's lineage and compose the block. ``None`` when the corpus conceptric
    does not resolve; an unknown node in a resolved corpus returns ``present: False`` for
    the composed 404."""
    corpus = _resolve_corpus(corpus)
    if not corpus:
        return None
    from laplace.pipeline import lineage, node_index as ni
    walk = lineage.descendants(corpus, node, depth=depth, root=root)
    if walk is None:
        return None
    index, freshness = ni.get_index(corpus, root)
    index = index or {"nodes": {}, "objects": {}}
    if not walk["present"]:
        return {"present": False, "corpus": corpus, "node": node,
                "glance": (f"No concept node named {node!r} is in {corpus}'s conceptric, so it "
                           "has no lineage to show."),
                "working": {"n_nodes_in_graph": len((index.get('nodes') or {}))},
                "audit": {"reason": "node absent from conceptric_v1.json",
                          "ids": [node], "staleness": _staleness(freshness)}}

    desc_ids = [r["id"] for r in walk["nodes"]]
    sections, assets, equations = _sections_and_assets_for(index, desc_ids + [node])
    findings = _open_findings_for(corpus, set(desc_ids) | {node})
    n_desc = walk["health"]["n_descendants"]

    if walk["is_leaf"]:
        glance = (f"{node} is a leaf in {corpus}: nothing descends from it, so its lineage is "
                  "itself alone.")
    else:
        glance = (f"{node} leads to {n_desc} descendant"
                  + ("" if n_desc == 1 else "s")
                  + f" across {len(sections)} section" + ("" if len(sections) == 1 else "s")
                  + f", {len(assets)} asset" + ("" if len(assets) == 1 else "s")
                  + f", and {len(findings)} open finding" + ("" if len(findings) == 1 else "s")
                  + ".")
    working = {
        "tree": walk["tree"],
        "n_descendants": n_desc,
        "sections_touched": sections,
        "assets": assets,
        "equations": equations,
    }
    audit = {
        "edges": walk["edges"],
        "health": walk["health"],
        "open_findings": findings,
        "ids": [node] + desc_ids,
        "staleness": _staleness(freshness),
    }
    return {"present": True, "corpus": corpus, "node": node,
            "depth": walk["depth_requested"],
            "glance": glance, "working": working, "audit": audit}


# ---------------------------------------------------------------------------
# the HTTP handler (the scanner-dispatch contract): two GET-only read doors.
# ---------------------------------------------------------------------------
def handle(path: str, query: dict, method: str,
           body: bytes) -> tuple[int, str, bytes] | None:
    """Route a ``/provenance/*`` or ``/descendants/*`` request. Returns
    ``(status, content_type, body)`` or ``None`` when the path is not ours."""
    owns = path.startswith("/provenance") or path.startswith("/descendants")
    if not owns:
        return None
    method = (method or "GET").upper()

    if path == "/provenance/object":
        if method != "GET":
            return _json_resp(405, {"error": f"{method} not allowed — /provenance/object is GET"})
        corpus = _q1(query, "corpus")
        object_ref = _q1(query, "object")
        if not object_ref:
            return _json_resp(400, {"error": "object is required (a tex label, concept id, "
                                    "asset id, or paragraph spec id)"})
        out = provenance_payload(corpus, object_ref)
        if out is None:
            rc = _resolve_corpus(corpus) or corpus or "(none active)"
            return _json_resp(404, {
                "resolved": False, "corpus": rc, "object": object_ref,
                "glance": (f"No manuscript resolves for {rc!r}, so no object provenance can be "
                           "read."),
                "working": {}, "audit": {"reason": "corpus does not resolve to a manuscript",
                                         "ids": [object_ref]}})
        if not out.get("resolved"):
            from laplace.pipeline import node_index as ni
            index, _ = ni.get_index(out["corpus"])
            return _json_resp(404, _compose_object_404(out["corpus"], object_ref, index))
        return _json_resp(200, out)

    if path == "/descendants/node":
        if method != "GET":
            return _json_resp(405, {"error": f"{method} not allowed — /descendants/node is GET"})
        corpus = _q1(query, "corpus")
        node = _q1(query, "node")
        if not node:
            return _json_resp(400, {"error": "node is required (a conceptric node id)"})
        depth_s = _q1(query, "depth", "0")
        try:
            depth = int(depth_s)
        except ValueError:
            depth = 0
        out = descendants_payload(corpus, node, depth)
        if out is None:
            rc = _resolve_corpus(corpus) or corpus or "(none active)"
            return _json_resp(404, {
                "present": False, "corpus": rc, "node": node,
                "glance": (f"No conceptric resolves for {rc!r}, so no lineage can be walked."),
                "working": {}, "audit": {"reason": "corpus does not resolve to a conceptric",
                                         "ids": [node]}})
        if not out.get("present"):
            return _json_resp(404, out)
        return _json_resp(200, out)

    return _json_resp(404, {"error": f"no provenance route {path!r}"})
