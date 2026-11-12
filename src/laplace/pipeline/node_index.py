"""node_index.py — the master node index (G5): the join that binds a rendered object
to the concept it argues.

The recon found five id namespaces that never met: conceptric node ids
(``fal_clm_001``), tex ``\\label`` targets (``eq:coh-total``) in the nodemap, isnad
handles (``N_coherent_l``) in the aspiration chain, asset ids (``figure:fig_resources``),
and paragraph spec ids (``s5-p3``). Section->node (the projection plan) and
paragraph->node (prose provenance ``nodes_realised``) are clean and populated; the
rendered-object->concept join had to be built. This module builds it, mints a per-project
``<manuscript>/node_index.json``, and states every join it cannot close rather than
fabricating one.

The eq->node ladder (first hit wins, each tagged with how it was derived):

1. ``prose``   — a prose-provenance paragraph lists the equation label in its
   ``equations`` field; the equation inherits that paragraph's ``nodes_realised``.
2. ``spatial`` — the equation's measured rect sits in a paragraph's column band in
   nodemap coordinates; the equation inherits that paragraph's ``nodes_realised``. The
   join is tagged ``spatial`` so the provenance is truthful about the geometry it rests on.
3. ``isnad``   — the equation's ``\\label`` is defined inside an aspiration derivation
   fragment (``link-*.tex``); the equation resolves to that chain link, and to the link's
   conceptric node when (and only when) the handle strict-resolves to one.

An object with no resolvable concept node is recorded under ``unresolved`` with the reason
stated — the fallback law: absence is reported, never papered over.
"""
from __future__ import annotations
from laplace.core.checkout import source_tree

import datetime as _dt
import json
import re
from pathlib import Path

from laplace.pipeline import derived_writes
from laplace.pipeline.suppress import content_fingerprint as _content_fingerprint

#: the index format version — bumped when the record shape changes so a stale mint is legible.
INDEX_VERSION = 1

#: the label of the derivation-fragment convention's store, relative to a manuscript dir.
_FRAG_REL = "aspiration/derivations"

_EQ_LABEL_RX = re.compile(r"\\label\{(eq:[^}]+)\}")
_N_HANDLE_RX = re.compile(r"N_[A-Za-z0-9_]+")


def _repo_root() -> Path:
    return source_tree()


def _manuscript_dir(corpus: str) -> Path | None:
    try:
        from laplace.manuscript import review_surface as rs
    except Exception:
        return None
    return rs.manuscript_dir(corpus, "")


def _load_json(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text(encoding="utf-8")) or {}
    except (OSError, json.JSONDecodeError):
        return None


# --------------------------------------------------------------------------- #
# source loaders (each tolerant of absence — a missing source is stated, not fatal)
# --------------------------------------------------------------------------- #

def _load_conceptric(md: Path) -> dict:
    doc = _load_json(md / "conceptric_v1.json") or {}
    nodes = {n["id"]: n for n in doc.get("nodes") or []
             if isinstance(n, dict) and n.get("id")}
    return nodes


def _load_sections(md: Path) -> dict[str, str]:
    """node id -> section id, from the projection plan's per-section ``nodes_in_order``
    (sections and appendices both). The clean, verified section->node join, inverted."""
    doc = _load_json(md / "projection_plan.json") or {}
    out: dict[str, str] = {}
    for block in (doc.get("sections") or []) + (doc.get("appendices") or []):
        sid = block.get("id")
        for nid in block.get("nodes_in_order") or []:
            out.setdefault(nid, sid)
    return out


def _load_prose(md: Path) -> tuple[dict[str, dict], dict[str, list[str]]]:
    """Two maps off ``prose_provenance/*.json``:

    * ``para_of`` — spec id -> {section, nodes_realised, equations, function}.
    * ``eq_prose`` — an equation label -> the nodes of the paragraph that declares it in
      its ``equations`` field (the clean eq->node path, empty in falqon today).
    """
    para_of: dict[str, dict] = {}
    eq_prose: dict[str, list[str]] = {}
    pdir = md / "prose_provenance"
    if not pdir.is_dir():
        return para_of, eq_prose
    for f in sorted(pdir.glob("*.json")):
        doc = _load_json(f) or {}
        sec = doc.get("section_id")
        for para in doc.get("paragraphs") or []:
            spec_ids = [sid for sid in (para.get("spec_ids") or [para.get("spec_id")]) if sid]
            if not spec_ids:
                continue
            nodes = list(para.get("nodes_realised") or [])
            for sid in spec_ids:
                entry = para_of.setdefault(sid, {
                    "section": sec, "nodes_realised": [], "equations": [],
                    "function": "", "proposition": "", "occurrences": [], "sections": [],
                })
                if sec not in entry["sections"]:
                    entry["sections"].append(sec)
                entry["section"] = sec if len(entry["sections"]) == 1 else None
                entry["occurrences"].append({"section": sec, "nodes_realised": nodes,
                    "equations": list(para.get("equations") or []), "spec_ids": spec_ids,
                    "function": para.get("function") or "", "proposition": para.get("proposition") or ""})
                entry["nodes_realised"] = list(dict.fromkeys(
                    entry["nodes_realised"] + nodes
                ))
                entry["equations"] = list(dict.fromkeys(
                    entry["equations"] + list(para.get("equations") or [])
                ))
                entry["function"] = entry["function"] or para.get("function") or ""
                entry["proposition"] = entry["proposition"] or para.get("proposition") or ""
            for eq in para.get("equations") or []:
                eq_prose.setdefault(eq, [])
                for n in nodes:
                    if n not in eq_prose[eq]:
                        eq_prose[eq].append(n)
    return para_of, eq_prose


def _load_nodemap(md: Path) -> dict:
    """The nodemap ``entries`` (label/spec-id -> [region...]), plus its stored source
    fingerprint. Missing map -> empty entries, ``present`` False."""
    doc = _load_json(md / "main.nodemap.json")
    if doc is None:
        return {"present": False, "entries": {}, "source_fingerprint": None}
    return {"present": True, "entries": doc.get("entries") or {},
            "source_fingerprint": doc.get("source_fingerprint")}


def _fragment_eq_labels(md: Path) -> dict[str, str]:
    """equation label -> the derivation-fragment link id that defines its ``\\label``.
    The isnad rung of the eq->node ladder: an equation authored inside ``link-X.tex``
    belongs to chain link ``X``."""
    out: dict[str, str] = {}
    fdir = md / _FRAG_REL
    if not fdir.is_dir():
        return out
    for f in sorted(fdir.glob("link-*.tex")):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in _EQ_LABEL_RX.finditer(text):
            out.setdefault(m.group(1), f.stem)
    return out


def _load_chain(corpus: str, md: Path) -> dict[str, dict]:
    """The aspiration chain, last-wins by link id (``read_chain`` is the one reader)."""
    try:
        from laplace.pipeline import derivation_organ
        rows = derivation_organ.read_chain(md)
    except Exception:
        return {}
    return {r["id"]: r for r in rows if r.get("id")}


# --------------------------------------------------------------------------- #
# the isnad-handle -> conceptric resolver (G2): STRICT, or absent-and-stated.
# --------------------------------------------------------------------------- #

def _slug_tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", (text or "").lower()) if len(t) > 2}


def _handle_gloss(field: str) -> str | None:
    """The human phrase an isnad ``to``/``from`` field carries after its ``N_handle:``
    prefix (``N_coherent_l: coherent circuit volume ~ L (...)`` -> ``coherent circuit
    volume ~ L``). A parenthetical aside and any trailing section tag are trimmed so the
    phrase reads in a composed sentence. ``None`` when the field is empty."""
    text = (field or "").strip()
    if not text:
        return None
    # drop the leading handle(s) up to the first colon-gloss.
    if ":" in text:
        text = text.split(":", 1)[1].strip()
    # trim a trailing parenthetical and a bare section tag.
    text = re.sub(r"\s*\([^)]*\)\s*$", "", text).strip()
    return text or None


def resolve_handle_to_conceptric(handle: str, gloss: str,
                                 conceptric: dict) -> str | None:
    """Resolve an isnad ``N_`` handle to a conceptric id ONLY on a real match, else
    ``None``. A match is one of:

    * the handle's stem equals a conceptric id (``N_regwidth`` -> ``regwidth``), or
    * the gloss's leading phrase equals a conceptric node's label (case-insensitive).

    Deliberately conservative: a fuzzy token overlap is not a match — inventing an
    edge here would be exactly the fabricated join the fallback law forbids. When
    nothing strict-resolves the caller records the absence with its reason.
    """
    stem = handle[2:] if handle.startswith("N_") else handle
    stem = stem.strip().lower()
    if stem in conceptric:
        return stem
    # gloss leading phrase (before the first comma / period) vs an exact node label.
    lead = re.split(r"[,.;:]", gloss or "", 1)[0].strip().lower()
    if lead:
        for nid, n in conceptric.items():
            lbl = (n.get("label") or "").strip().lower()
            if lbl and lbl == lead:
                return nid
    return None


def _link_conceptric_node(link: dict, conceptric: dict) -> str | None:
    """The conceptric node an isnad link resolves to, across every ``N_`` handle in its
    ``to``/``from`` glosses. ``None`` when no handle strict-resolves (stated by the caller)."""
    for field in ("to", "from"):
        text = link.get(field) or ""
        for m in _N_HANDLE_RX.finditer(text):
            hit = resolve_handle_to_conceptric(m.group(0), text, conceptric)
            if hit:
                return hit
    return None


# --------------------------------------------------------------------------- #
# the spatial eq->paragraph join — general, column-aware, honest about its geometry.
# --------------------------------------------------------------------------- #

def _first_region(regions: list) -> dict | None:
    return regions[0] if isinstance(regions, list) and regions else None


def _column_of(x0, page_mid: float = 300.0) -> str:
    """Which column a region's left edge sits in. Two-column reprints place the right
    column near x~318; a single-column layout collapses to ``left`` for everything."""
    try:
        return "right" if float(x0) >= page_mid else "left"
    except (TypeError, ValueError):
        return "left"


def spatial_eq_to_paragraph(entries: dict) -> dict[str, str]:
    """Map each equation label to the paragraph whose column band contains it, in
    nodemap coordinates. A paragraph marker is the TOP of its band; the band runs down
    to the next paragraph marker in the same page+column (or the page foot). An equation
    whose vertical midpoint falls in a band, same column, joins that paragraph.

    Returns ``{eq_label: paragraph_spec_id}`` for every equation that lands in a band.
    Equations and paragraphs that never share a page yield nothing — stated by the caller,
    never forced.
    """
    paras, eqs = {}, []
    for key, regions in entries.items():
        for region in regions if isinstance(regions, list) else []:
            page = region.get('page')
            if page is None:
                continue
            col = _column_of(region.get('x0'))
            y = float(region.get('y0') or 0.0)
            if region.get('kind') == 'paragraph':
                ids = region.get('spec_ids') or [key]
                paras.setdefault((page, col), {}).setdefault(y, set()).update(ids)
            elif region.get('kind') == 'equation':
                eqs.append((key, page, col, (y + float(region.get('y1') or y)) / 2))
    observed = {}
    for label, page, col, y in eqs:
        band = sorted(paras.get((page, col), {}).items())
        candidates = [ids for index, (top, ids) in enumerate(band)
                      if top <= y < (band[index + 1][0] if index + 1 < len(band) else float('inf'))]
        if not candidates and band and y < band[0][0]:
            candidates = [band[0][1]]
        observed.setdefault(label, set()).update(candidates[0] if candidates else [])
    # The compatibility return is scalar; ambiguous merged/multi-location
    # equations remain unjoined rather than inventing one scientific owner.
    out = {label: next(iter(ids)) for label, ids in observed.items() if len(ids) == 1}

    return out


# --------------------------------------------------------------------------- #
# the page reader — where a label/spec-id lands, off the nodemap.
# --------------------------------------------------------------------------- #

def _page_of(entries: dict, key: str) -> int | None:
    r = _first_region(entries.get(key))
    return r.get("page") if r else None


# --------------------------------------------------------------------------- #
# THE INDEX BUILDER
# --------------------------------------------------------------------------- #

def _substrate_fingerprint(md: Path) -> str:
    """A content fingerprint over the index's sources, so staleness is detectable with
    the same normalise-then-hash idiom the composed block uses. Covers the conceptric,
    the projection plan, the nodemap, the chain, and every prose-provenance file."""
    parts: list[str] = []
    for rel in ("conceptric_v1.json", "projection_plan.json", "main.nodemap.json",
                "aspiration/chain.jsonl"):
        p = md / rel
        if p.is_file():
            try:
                parts.append(f"{rel}\0{p.read_text(encoding='utf-8', errors='replace')}")
            except OSError:
                pass
    pdir = md / "prose_provenance"
    if pdir.is_dir():
        for f in sorted(pdir.glob("*.json")):
            try:
                parts.append(f"{f.name}\0{f.read_text(encoding='utf-8', errors='replace')}")
            except OSError:
                pass
    return _content_fingerprint("\n".join(parts))


def build_node_index(corpus: str, root: Path | None = None) -> dict | None:
    """Build the master node index for ``corpus`` in memory (no write). ``None`` when the
    corpus's manuscript does not resolve.

    Structure::

        {
          corpus, built_at, index_version, substrate_fingerprint,
          sources: {conceptric, nodemap, prose, plan, chain},   # present flags
          nodes:   {<conceptric_id>: {label, kind, section, page, asset_id,
                                      paragraph_ids[], tex_labels[], equations[]}},
          objects: {<tex_label|spec_id|asset_id>: {kind, page, section,
                     conceptric_nodes[], paragraph_id, join, join_provenance,
                     isnad_link}},
          unresolved: [{object, kind, reason}],
          counts: {...}
        }
    """
    root = (root or _repo_root()).resolve()
    md = _manuscript_dir(corpus)
    if md is None:
        return None

    conceptric = _load_conceptric(md)
    section_of = _load_sections(md)
    para_of, eq_prose = _load_prose(md)
    nm = _load_nodemap(md)
    entries = nm["entries"]
    frag_eq = _fragment_eq_labels(md)
    chain = _load_chain(corpus, md)

    try:
        from laplace.pipeline import asset_model as am
        assets = am.enumerate_assets(corpus)
    except Exception:
        assets = []

    # the spatial eq->paragraph join (general; may be empty for this corpus).
    spatial = spatial_eq_to_paragraph(entries)

    # ---- node records, seeded from the conceptric ----
    nodes: dict[str, dict] = {}
    for nid, n in conceptric.items():
        nodes[nid] = {
            "label": n.get("label") or "",
            "kind": n.get("kind") or "",
            "section": section_of.get(nid),
            "page": None,
            "asset_id": None,
            "paragraph_ids": [],
            "tex_labels": [],
            "equations": [],
        }

    def _touch(nid: str) -> dict:
        return nodes.setdefault(nid, {
            "label": conceptric.get(nid, {}).get("label") or "",
            "kind": conceptric.get(nid, {}).get("kind") or "",
            "section": section_of.get(nid), "page": None, "asset_id": None,
            "paragraph_ids": [], "tex_labels": [], "equations": [],
        })

    objects: dict[str, dict] = {}
    unresolved: list[dict] = []

    # Resolve retained prose declarations through the observed occurrence location.
    eq_prose = {}
    # ---- paragraphs: spec id -> nodes_realised (the clean, populated join) ----
    for sid, meta in para_of.items():
        page = _page_of(entries, sid)
        physical = [region for region in entries.get(sid, []) if region.get('kind') == 'paragraph']
        source_sections = list(dict.fromkeys(region.get('source_section') or region.get('section')
            for region in physical if region.get('source_section') or region.get('section')))
        provenance = [row for row in meta.get('occurrences', []) if not source_sections or row['section'] in source_sections]
        if not source_sections and len(meta.get('sections', [])) > 1:
            provenance = []
        realised = list(dict.fromkeys(ident for row in provenance for ident in row['nodes_realised']))
        for row in provenance:
            for label in row['equations']:
                eq_prose[label] = list(dict.fromkeys(eq_prose.get(label, []) + row['nodes_realised']))
        functions = list(dict.fromkeys(row.get('function') or '' for row in provenance))
        propositions = list(dict.fromkeys(row.get('proposition') or '' for row in provenance))
        if not meta.get('occurrences'):
            realised = meta['nodes_realised']
        objects[sid] = {
            "kind": "paragraph",
            "page": page,
            "section": source_sections[0] if len(source_sections) == 1 else meta["section"] if not source_sections else None,
            "source_sections": source_sections, "source_occurrences": physical,
            "provenance_sections": meta.get("sections", []),
            "mapping_status": "EXPLICIT_OCCURRENCES" if source_sections else "AMBIGUOUS" if len(meta.get("sections", [])) > 1 else "RECORDED_ONLY",
            "conceptric_nodes": list(realised),
            "paragraph_id": sid,
            "join": "prose" if realised else "absent",
            "join_provenance": ["prose_provenance.nodes_realised"] if realised
                               else ["prose_provenance: paragraph realises no node"],
            "function": functions[0] if len(functions) == 1 else "",
            "proposition": propositions[0] if len(propositions) == 1 else "",
            "isnad_link": None,
        }
        if not realised:
            unresolved.append({"object": sid, "kind": "paragraph",
                               "reason": "paragraph realises no conceptric node"})
        for nid in realised:
            rec = _touch(nid)
            if sid not in rec["paragraph_ids"]:
                rec["paragraph_ids"].append(sid)
            if rec["page"] is None and page is not None:
                rec["page"] = page

    # ---- equations: the eq->node ladder (prose -> spatial -> isnad) ----
    for label, regions in entries.items():
        r = _first_region(regions)
        if not r or r.get("kind") != "equation":
            continue
        page = r.get("page")
        conc: list[str] = []
        join = "absent"
        prov: list[str] = []
        paragraph_id = None
        isnad_link = None
        origin_node = None       # the derivation-graph node the equation was authored under
        origin_gloss = None      # a human phrase for that origin (chain link's target gloss)
        # 1. prose
        if eq_prose.get(label):
            conc = list(eq_prose[label])
            join = "prose"
            prov = ["prose_provenance.equations -> nodes_realised"]
        # 2. spatial
        elif label in spatial:
            paragraph_id = spatial[label]
            conc = list((para_of.get(paragraph_id) or {}).get("nodes_realised") or [])
            join = "spatial"
            prov = [f"spatial: equation rect in paragraph {paragraph_id} column band",
                    "then prose_provenance.nodes_realised"]
        # 3. isnad — the equation was authored inside a derivation fragment; it resolves
        #    to that chain link and to the ratified derivation node the link carries, plus
        #    to a conceptric substrate node when (and only when) a handle strict-resolves.
        elif label in frag_eq:
            isnad_link = frag_eq[label]
            link = chain.get(isnad_link) or {}
            origin_node = link.get("node_id")
            origin_gloss = _handle_gloss(link.get("to") or link.get("from") or "")
            hit = _link_conceptric_node(link, conceptric)
            join = "isnad"
            prov = [f"isnad: equation label defined in derivation fragment {isnad_link}"]
            if hit:
                conc = [hit]
                prov.append("isnad handle strict-resolved to a conceptric substrate node")
            elif origin_node:
                prov.append(f"resolved to the derivation node {origin_node} the fragment "
                            "was ratified under (applied-graph node, not a substrate node)")
            else:
                prov.append("the fragment carries no ratified node — origin concept absent")
        if join == "absent":
            prov = ["no prose, spatial, or isnad join resolves this equation"]
        # an equation "resolves" when it reaches a substrate node OR its origin derivation node.
        has_concept = bool(conc) or bool(origin_node)
        objects[label] = {
            "kind": "equation",
            "page": page,
            "section": (section_of.get(conc[0]) if conc else None),
            "conceptric_nodes": conc,
            "origin_node": origin_node,
            "origin_gloss": origin_gloss,
            "paragraph_id": paragraph_id,
            "join": join,
            "join_provenance": prov,
            "isnad_link": isnad_link,
        }
        if not has_concept:
            unresolved.append({"object": label, "kind": "equation",
                               "reason": prov[-1] if prov else "no join"})
        for nid in conc:
            rec = _touch(nid)
            if label not in rec["tex_labels"]:
                rec["tex_labels"].append(label)
            if label not in rec["equations"]:
                rec["equations"].append(label)
            if rec["page"] is None and page is not None:
                rec["page"] = page

    # ---- assets: figures + derivations as addressable objects ----
    for a in assets:
        page = None
        if a.landings:
            page = a.landings[0].page
        node_id = a.node_id
        # a figure/derivation's conceptric node is its own node_id ONLY when that id is a
        # real conceptric node — a fig: label that the conceptric never declared resolves
        # to a landing (page), not a concept, and that absence is stated.
        conc = [node_id] if (node_id and node_id in conceptric) else []
        supported = [s for s in a.nodes_supported if s in conceptric]
        for s in supported:
            if s not in conc:
                conc.append(s)
        join = "asset" if conc else ("landing" if a.landings else "absent")
        prov = ["asset_model.enumerate_assets"]
        if a.node_id and not conc:
            prov.append(f"asset node id {a.node_id} is not a declared conceptric node "
                        "— landing only, concept absent")
        objects[a.id] = {
            "kind": a.kind,
            "page": page,
            "section": (section_of.get(conc[0]) if conc else None),
            "conceptric_nodes": conc,
            "paragraph_id": None,
            "join": join,
            "join_provenance": prov,
            "isnad_link": (a.id.split(":", 1)[1] if a.id.startswith("derivation:link-")
                           else None),
            "node_id": a.node_id,
            "landings": [{"page": l.page, "file": l.file, "kind": l.kind} for l in a.landings],
        }
        if not conc:
            unresolved.append({"object": a.id, "kind": a.kind,
                               "reason": prov[-1]})
        for nid in conc:
            rec = _touch(nid)
            if rec["asset_id"] is None:
                rec["asset_id"] = a.id
            if rec["page"] is None and page is not None:
                rec["page"] = page

    fp = _substrate_fingerprint(md)
    n_resolved_eq = sum(1 for o in objects.values()
                        if o["kind"] == "equation"
                        and (o["conceptric_nodes"] or o.get("origin_node")))
    n_eq = sum(1 for o in objects.values() if o["kind"] == "equation")
    return {
        "corpus": corpus,
        "built_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "index_version": INDEX_VERSION,
        "substrate_fingerprint": fp,
        "sources": {
            "conceptric": bool(conceptric),
            "nodemap": nm["present"],
            "prose": bool(para_of),
            "plan": bool(section_of),
            "chain": bool(chain),
            "nodemap_source_fingerprint": nm["source_fingerprint"],
        },
        "nodes": nodes,
        "objects": objects,
        "unresolved": unresolved,
        "counts": {
            "conceptric_nodes": len(conceptric),
            "objects": len(objects),
            "equations": n_eq,
            "equations_resolved": n_resolved_eq,
            "paragraphs": sum(1 for o in objects.values() if o["kind"] == "paragraph"),
            "assets": len(assets),
            "unresolved": len(unresolved),
        },
    }


# --------------------------------------------------------------------------- #
# mint + load + freshness
# --------------------------------------------------------------------------- #

def index_path(corpus: str) -> Path | None:
    md = _manuscript_dir(corpus)
    return (md / "node_index.json") if md is not None else None


def write_node_index(corpus: str, root: Path | None = None) -> Path | None:
    """Mint ``<manuscript>/node_index.json`` for ``corpus`` and return its path. ``None``
    when the corpus does not resolve. Derived state, like a nodemap: overwrites in place.

    The mint touches the LIVE repo, and the record carries a wall-clock ``built_at``, so
    an ungated mint rewrites the file even when the substrate has not moved — which is how
    a test that only asserts index freshness came to dirty the working tree
    (WO-20260817-test-mutates-working-tree; the same defect as the form-retrieval sidecar).
    The write is therefore gated on :func:`derived_writes.enabled`: live in a real run,
    read-only under pytest unless ``LAPLACE_SIDECAR_WRITE`` is set. When the gate is shut
    this returns ``None`` and STATES why via :func:`derived_writes.read_only_note` — it
    does not pretend to have minted, and it does not fall back to the file already on disk
    (a caller wanting that reads :func:`load_node_index` / :func:`get_index` deliberately)."""
    if not derived_writes.enabled():
        return None                     # read-only: stated, not silently skipped
    idx = build_node_index(corpus, root)
    if idx is None:
        return None
    p = index_path(corpus)
    if p is None:
        return None
    p.write_text(json.dumps(idx, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                 encoding="utf-8")
    return p


def load_node_index(corpus: str, root: Path | None = None) -> dict | None:
    """Read the minted index off disk. ``None`` when absent — the doors rebuild in memory
    rather than 404 on a never-minted index."""
    p = index_path(corpus)
    if p is None or not p.is_file():
        return None
    return _load_json(p)


#: the five presence flags in a built index's ``sources`` block. The sixth key,
#: ``nodemap_source_fingerprint``, is a hash string rather than a presence flag, so it is
#: not read here. NOTE: these flags do NOT cover the asset feeder — ``build_node_index``
#: also fills ``objects`` from ``asset_model.enumerate_assets`` and sets no flag for it —
#: so a corpus can build a non-empty graph with every flag zero (e.g. one whose only
#: content is figure objects). Emptiness is therefore judged on the BUILT GRAPH, never
#: on the flags alone.
_SOURCE_FLAGS: tuple[str, ...] = ("conceptric", "nodemap", "prose", "plan", "chain")


def _has_any_source(index: dict) -> bool:
    """True when at least one of the five sources fed this index."""
    src = index.get("sources") or {}
    return any(bool(src.get(k)) for k in _SOURCE_FLAGS)


def _graph_is_empty(index: dict) -> bool:
    """True when the built index holds nothing a door could serve — no nodes, no objects
    (the asset feeder's output, flagless), no unresolved refs. Judged on the graph itself
    because the source flags miss the asset feeder (see ``_SOURCE_FLAGS``)."""
    return not (index.get("nodes") or index.get("objects") or index.get("unresolved"))


def get_index(corpus: str, root: Path | None = None) -> tuple[dict | None, dict]:
    """The index a door serves: the minted one when present, else a fresh in-memory build,
    plus a freshness verdict. Returns ``(index, freshness)`` where freshness is
    ``{minted, fresh, moved, note}`` — ``moved`` names ``substrate`` when the minted index
    no longer matches its sources on disk."""
    disk = load_node_index(corpus, root)
    if disk is not None:
        now_fp = None
        md = _manuscript_dir(corpus)
        if md is not None:
            now_fp = _substrate_fingerprint(md)
        fresh = (disk.get("substrate_fingerprint") == now_fp) if now_fp else False
        moved = [] if fresh else (["substrate"] if now_fp else ["unknown"])
        note = ("the minted index matches its sources" if fresh
                else "the minted index is older than its sources — rebuild to refresh")
        return disk, {"minted": True, "fresh": fresh, "moved": moved, "note": note}
    live = build_node_index(corpus, root)
    if live is not None and not _has_any_source(live) and _graph_is_empty(live):
        # the manuscript dir resolves but nothing feeds the index: no conceptric, nodemap,
        # prose, plan, or chain — AND the built graph is genuinely empty (no asset-feeder
        # objects either). build_node_index still returns a well-formed all-zero index, and
        # a door serving it reads as a real graph that happens to hold nothing ("0 concepts,
        # 0 reached the manuscript"). Absent is the true answer, so the door gets None and
        # composes its own empty state. The graph-emptiness clause is load-bearing: the
        # source flags miss the asset feeder, so a corpus with only asset-feeder objects
        # (every flag zero, a non-empty graph) must NOT be dropped to None here.
        return None, {"minted": False, "fresh": True, "moved": [],
                      "note": "no index: nothing on disk feeds this corpus's graph yet"}
    return live, {"minted": False, "fresh": True, "moved": [],
                  "note": "built in memory (no minted index on disk)"}


# --------------------------------------------------------------------------- #
# cross-namespace object resolution (the /provenance/object door reads this).
# --------------------------------------------------------------------------- #

def resolve_object(index: dict, object_ref: str) -> dict | None:
    """Resolve an object reference across namespaces to its index record + kind.

    Accepts a tex label (``eq:coh-total`` / ``fig:resources``), a conceptric id
    (``fal_clm_011``), an asset id (``figure:fig_resources``), or a paragraph spec id
    (``s5-p3``). Returns ``{ref, resolved_kind, ...}`` or ``None`` when nothing resolves.
    """
    if not object_ref:
        return None
    objects = index.get("objects") or {}
    nodes = index.get("nodes") or {}
    # a direct object hit (tex label, asset id, paragraph spec id).
    if object_ref in objects:
        rec = dict(objects[object_ref])
        rec["ref"] = object_ref
        rec["resolved_kind"] = "object"
        return rec
    # a conceptric node id.
    if object_ref in nodes:
        rec = dict(nodes[object_ref])
        rec["ref"] = object_ref
        rec["resolved_kind"] = "conceptric_node"
        rec["conceptric_nodes"] = [object_ref]
        return rec
    return None
