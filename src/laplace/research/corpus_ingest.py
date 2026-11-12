"""corpus_ingest.py - the UP operator exposed for an arbitrary finished paper.

The one operator already builds the self (keeper.build_self): atomise a corpus into grade-0 leaves,
route them up with a structural parent_of (+ the meaning-cluster middle), and consolidate with
keeper.build_tree; then couple by the merged edge-index via keeper_ring.build_reach. This module is
the same assembly pointed at a FINISHED PAPER instead of the repo - the seam build_self never exposed
(meaning_upfold.cluster_residue was only called for the self). Nothing here re-derives the operator;
it only atomises a paper's .tex/.bib into the leaf+edge shape build_tree/build_reach already consume.

Reverse-engineering a paper IS learning IS this up-pass. The conceptric it returns is fed straight to
the existing DOWN operators (conceptric.reconstruct_node / grade_view / explode for the view,
keeper_ring.reconstruct for the projection) - one substrate, three directions.
"""
from __future__ import annotations
from laplace.core.checkout import source_tree

import json
import logging
import re
from pathlib import Path
from typing import Any

from laplace.engine import keeper
from laplace.engine.keeper_ring import build_reach
from laplace.manuscript.manuscript_bridge import _BIB_ENTRY, _bibfield

# the LOGICAL-object taxonomy (his reframe, 2026-06-29): a conceptric is a graded tree of logical
# objects, not document pieces. set-kind/add-node retag a node into this vocabulary. The atomiser
# still mints document kinds (section/equation/figure/citation) as the structural first draft; the
# human (and, later, the remote semantic operator) lifts them to logical kinds as the tree is built.
LOGICAL_KINDS = (
    "goal",        # the project's central claim — one per corpus, sits ABOVE the derivation DAG as
                   # the spine's orientation slot (rendered as prose, not math; not a derivation step)
    "definition", "postulate", "derivation-step", "lemma",
    "intermediate-result", "result", "theorem", "support",
    "technique",   # a reusable method (the recurring move promoted to substrate; surfaces by a lens)
    "question",    # an authored open obligation anchored to a logical object or relation
    "portal",      # a live reference to another conceptric's result (apex there, substrate here)
    "citation")    # a bibliographic substrate node (ref:Key) — minted from .bib at ingest OR from
                   # the editor's literature-search bulk-stage picker
# the provenance-exempt kinds: foundational nodes with NO derivation of their own, so they must never
# be scored as "missing provenance" (the content-vs-goal cut). Postulates/definitions are axioms; a
# technique is a method (its justification is its own concern); a portal's derivation lives in the
# other conceptric (descend on demand). A goal is the orientation, not a step; a citation is
# substrate the paper rests on, not derives from. Retagging into one clears the gap flag; out re-arms.
PROVENANCE_EXEMPT = {"goal", "postulate", "definition", "axiom", "technique", "portal",
    "support", "citation", "question"}

# the kinds that live in the DERIVATION DAG (the connectivity the spine is read off). Sections are
# containment, citations are support - neither is a derivation edge, so connectivity excludes them.
# Goal is also excluded: it's the project-level orientation, not a derivation step, so it never
# appears in neighborhoods / the landscape / gap counts.
DERIVATION_KINDS = ({"equation"} | set(LOGICAL_KINDS)) - {"goal", "citation"}

# the displayed-math environments whose \label is a first-class equation node
_MATH_ENVS = ["equation", "align", "gather", "multline", "eqnarray"]
_ENV_RX = re.compile(
    r"\\begin\{(" + "|".join(_MATH_ENVS) + r")\*?\}(.*?)\\end\{\1\*?\}", re.DOTALL)
_FIG_RX = re.compile(r"\\begin\{figure\*?\}(.*?)\\end\{figure\*?\}", re.DOTALL)
_LABEL_RX = re.compile(r"\\label\{([^}]+)\}")
_REF_RX = re.compile(r"\\(?:eqref|ref|cref|Cref)\{([^}]+)\}")
_CITE_RX = re.compile(r"\\cite[tp]?\*?\{([^}]+)\}")
_SECTITLE_RX = re.compile(r"\\section\*?\{([^}]+)\}")
_INPUT_RX = re.compile(r"\\input\{([^}]+)\}")
_BIB_PATH_RX = re.compile(r"\\bibliography\{([^}]+)\}")
# a POSTULATE / definition is an axiom of the paper - it has no derivation, so it must not be
# scored as "missing provenance" (the same content-vs-goal disambiguation: a postulate is not a
# failed derivation). Detected from the prose lead-in that introduces the equation.
_POSTULATE_RX = re.compile(
    r"\b(postulat|we (define|take|posit|assume|introduce|set|denote|write|require|impose)|"
    r"by definition|let us (define|denote|write|set)|define[ds]?\b|denote[ds]?\b|axiom|ansatz)", re.I)


def _refs(text: str) -> list[str]:
    out: list[str] = []
    for m in _REF_RX.findall(text):
        out += [t.strip() for t in m.split(",") if t.strip()]
    return out


def _cites(text: str) -> list[str]:
    out: list[str] = []
    for m in _CITE_RX.findall(text):
        out += [t.strip() for t in m.split(",") if t.strip()]
    return out


def _kw(s: str, extra: list[str] | None = None) -> list[str]:
    toks = [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z\-]{3,}", s)][:8]
    return list(dict.fromkeys((extra or []) + toks))


def atomise_paper(tex_root: Path, root_file: Path | None = None) -> tuple[dict[str, dict], dict[str, list[str]], dict[str, str]]:
    """A finished paper -> (leaves, edge_index, parent_map).

    leaves: id -> {kind, essence, keywords, sealed} (build_tree's contract).
    edge_index: leaf id -> [referent strings] (build_reach's contract). Every labelled element carries
        its OWN label as a referent (its identity) plus every label/key it \\eqref/\\ref/\\cite's, so a
        node that references eq:X shares the referent 'eq:X' with eq:X itself - real, directional
        dependency (out/in asymmetry), never a prose mention.
    parent_map: containment for build_tree (eq/fig -> section, section -> root, citation -> references).
    """
    main = root_file or tex_root / "main.tex"
    if not main.is_file() and root_file is None:
        candidates = [path for path in tex_root.glob('*.tex')
                      if re.search(r'\\documentclass\b', path.read_text(encoding='utf-8',errors='ignore'))]
        if len(candidates) == 1: main = candidates[0]
    tex_root = main.parent
    text = main.read_text(encoding="utf-8", errors="ignore")
    root_id = "paper://"
    refs_id = "references"
    leaves: dict[str, dict] = {}
    edge_index: dict[str, list[str]] = {}
    parent_map: dict[str, str] = {refs_id: root_id}   # paper:// is the apex (no parent)
    title_match = re.search(r'\\title\s*\{([^}]+)\}', text)
    leaves[root_id] = {"kind": "paper", "essence": title_match.group(1) if title_match else "the paper", "keywords": []}
    leaves[refs_id] = {"kind": "references", "essence": "the bibliography", "keywords": []}

    # --- sections in \input reading order; equations + figures inside each ---
    body_start = re.search(r'\\begin\s*\{document\}', text)
    root_body = text[body_start.end():] if body_start else text
    for sec_file in _INPUT_RX.findall(root_body):
        path = (tex_root / sec_file)
        if path.suffix != ".tex":
            path = path.with_suffix(".tex")
        if not path.is_file():
            continue
        body = path.read_text(encoding="utf-8", errors="ignore")
        # the section's id is its actual \label{sec:...} (so \ref resolves); else the filename stem
        seclab = next((l for l in _LABEL_RX.findall(body) if l.startswith("sec:")), None)
        sid = seclab or ("sec:" + Path(sec_file).stem)
        title = (_SECTITLE_RX.search(body) or [None, Path(sec_file).stem])
        title = title.group(1) if hasattr(title, "group") else Path(sec_file).stem
        leaves[sid] = {"kind": "section", "essence": title, "keywords": _kw(title)}
        parent_map[sid] = root_id
        # the section's own referents: every cite/ref it makes + its identity
        edge_index[sid] = list(dict.fromkeys([sid] + _cites(body) + _refs(body)))
        # equations: an equation derives_from the labels \eqref'd in the prose lead-in just before it
        # (the derivation chain lives in the surrounding text, not inside the math env). Referents =
        # its own label + the eqrefs/cites in that lead-in + any in the env itself -> directional
        # 'eq:Y references eq:X' edges, asymmetric under coupling, never a prose word-match.
        for em in _ENV_RX.finditer(body):
            env = em.group(2)
            lead = body[max(0, em.start() - 600):em.start()]
            postulate = bool(_POSTULATE_RX.search(lead[-300:]))
            for lab in _LABEL_RX.findall(env):
                if not lab.startswith("eq:"):
                    continue
                deps = [r for r in _refs(lead) + _refs(env) if r.startswith("eq:") and r != lab]
                leaves[lab] = {"kind": "equation",
                               "essence": re.sub(r"\s+", " ", env).strip()[:240],
                               "keywords": _kw(lab, [lab]),
                               "ord": len([k for k in leaves if k.startswith("eq:")]),
                               "ctx": re.sub(r"\s+", " ", lead).strip()[-300:],
                               "postulate": postulate}
                parent_map[lab] = sid
                edge_index[lab] = list(dict.fromkeys([lab] + deps + _cites(lead) + _cites(env)))
        # figures
        for fig in _FIG_RX.findall(body):
            labs = [l for l in _LABEL_RX.findall(fig) if l.startswith("fig:")]
            if not labs:
                continue
            cap = re.search(r"\\caption\{(.*?)\}", fig, re.DOTALL)
            cap = re.sub(r"\s+", " ", cap.group(1)).strip()[:200] if cap else labs[0]
            leaves[labs[0]] = {"kind": "figure", "essence": cap, "keywords": _kw(cap, [labs[0]])}
            parent_map[labs[0]] = sid
            edge_index[labs[0]] = list(dict.fromkeys([labs[0]] + _refs(fig) + _cites(fig)))

    # --- citations: the bibliography, the broad leaf base ---
    bibm = _BIB_PATH_RX.search(text)
    if bibm:
        bibrel = bibm.group(1).split(",")[0].strip()
        bibp = (tex_root / bibrel)
        if bibp.suffix != ".bib":
            bibp = bibp.with_suffix(".bib")
        if bibp.is_file():
            btext = bibp.read_text(encoding="utf-8", errors="ignore")
            for m in _BIB_ENTRY.finditer(btext):
                key, fields = m.group(2), m.group(3)
                first = _bibfield(fields, "author").split(" and ")[0].split(",")[0].strip()
                year = _bibfield(fields, "year")
                cid = "ref:" + key
                leaves[cid] = {"kind": "citation",
                               "essence": (first + " " + year).strip() + " — " + _bibfield(fields, "title")[:120],
                               "keywords": _kw(key, [key])}
                parent_map[cid] = refs_id
                edge_index[cid] = [key]      # its identity referent; sections that \cite{key} share it
    return leaves, edge_index, parent_map


def semantic_provenance(leaves: dict[str, dict], edge_index: dict[str, list[str]],
                        threshold: float = 0.55,
                        relation_events: list[dict] | None = None) -> int:
    """The SEMANTIC half of the up-operator: recover a derived equation's provenance from its
    derivation prose when no explicit \\eqref encodes it. Reuses the engine's embedder
    (embed_router) - intelligence paid once at fold time. For each non-postulate equation lacking
    an explicit eq-dependency, link it to the EARLIER equation whose content its derivation lead-in
    is closest to (cosine > threshold). Directional (earlier->later), thresholded, and tagged with a
    'sem::' referent so the estimate stays auditable and distinct from an explicit \\eqref. Returns
    the count of edges added; degrades to 0 if the embedder is unavailable (never breaks the build)."""
    eqs = sorted([k for k, lf in leaves.items() if lf.get("kind") == "equation"],
                 key=lambda k: leaves[k].get("ord", 0))
    if len(eqs) < 2:
        return 0
    try:
        import numpy as np
        from laplace.representation.embed_router import get_backend
        backend = get_backend()
        texts = [f"{leaves[e].get('ctx','')} {leaves[e].get('essence','')}"[:512] for e in eqs]
        X = np.asarray(backend.embed(texts), dtype=np.float64)
        X /= np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-12, None)
    except Exception:  # noqa: BLE001 - the semantic pass is additive; unavailability leaves explicit edges only
        return 0
    added = 0
    for i, e in enumerate(eqs):
        lf = leaves[e]
        if lf.get("postulate") or i == 0:
            continue
        if any(r.startswith("eq:") and r != e for r in edge_index.get(e, [])):
            continue                                   # already has an explicit \eqref provenance
        sims = X[:i] @ X[i]                             # similarity to every EARLIER equation
        j = int(sims.argmax())
        if float(sims[j]) >= threshold:
            edge_index.setdefault(e, []).append(eqs[j])           # the directional provenance edge
            edge_index[e].append("sem::" + eqs[j])               # an audit marker (semantic, not \eqref)
            if relation_events is not None:
                relation_events.append({"source": e, "target": eqs[j],
                    "rel": "prerequisite", "producer": "semantic-provenance",
                    "mode": "semantic", "detail": {"threshold": threshold}})
            added += 1
    return added


_SEM_EDGE_FILE = ".corpus_sem_edges.json"   # gitignored cache: scripts/corpus_semantic_embed.py


def apply_semantic_wires(tex_root: Path | str, edge_index: dict[str, list[str]],
                         relation_events: list[dict] | None = None) -> int:
    """Lay the offline node-level semantic wires (scripts/corpus_semantic_embed.py) from the
    per-corpus cache: each mutual-top-k pair becomes a symmetric plain edge + ``sem::`` audit
    markers, so the build gates (connectivity/substrate) see the wire while its machine
    provenance stays distinguishable from a human ``confirmed::`` edge forever. Runs BEFORE
    apply_overlay so a ledger remove-edge permanently kills a bad machine wire. Additive:
    no cache file, no wires. Returns the count laid."""
    cache = Path(tex_root) / _SEM_EDGE_FILE
    if not cache.is_file():
        return 0
    try:
        wires = json.loads(cache.read_text(encoding="utf-8")).get("wires", [])
    except (OSError, json.JSONDecodeError):
        return 0
    laid = 0
    for w in wires:
        a, b = w.get("a"), w.get("b")
        if not a or not b:
            continue
        for src, dst in ((a, b), (b, a)):
            row = edge_index.setdefault(src, [])
            if dst not in row:
                row.append(dst)
                row.append("sem::" + dst)
                laid += 1
        if relation_events is not None:
            relation_events.append({"source": min(a, b), "target": max(a, b),
                "rel": "analogy", "producer": "semantic-wire", "mode": "semantic",
                "detail": {key: w.get(key) for key in sorted(w) if key not in {"a", "b"}}})
    return laid


def _clm_to_node(cid: str) -> str:
    """The evidence-ledger claim id -> the poured conceptric node id (the pour's
    convention, mechanical): ``FAL-CLM-004`` -> ``fal_clm_004``. Lowercase, hyphens to
    underscores. A claim whose mapped id is not a live node is skipped by the caller
    (no dangling), so this is a pure name transform, never a resolution guarantee."""
    return (cid or "").lower().replace("-", "_")


def apply_evidence_edges(leaves: dict, edge_index: dict, parent_map: dict,
                         name: str | None, repo_root: Path | str | None,
                         relation_events: list[dict] | None = None) -> int:
    """G3 leg-2 wired (W-G): the evidence ledger's LIVE claim->validation pointers become
    ``validates``-axis edges in the edge_index the coverage gauge walks. DETERMINISTIC on
    every build — this is the builder emitting the edges from the source of truth (the
    evidence ledger + the numerics store), never a mutable ledger write (a poured
    conceptric takes no writes; re-pour must reproduce it byte-for-byte). Additive and
    fail-closed: a corpus with no registered ``evidence_store``, an absent ledger, or an
    unparseable store wires NOTHING (a true zero — no token, no coverage).

    The mechanism, in one breath: the one evidence PARSER (``scripts/ingest_synthetic``:
    ``_VALREF`` + ``_classify_valref``, which dereferences ``readings:*``/``ledger:*``
    pointers into the numerics store) yields the LIVE pointers per claim; each claim id
    maps to its conceptric node (:func:`_clm_to_node`); each live pointer resolves to a
    LIVE evidence node (a ``ledger:<param>`` folds onto its existing assumption-param
    node; a ``readings:<keypath>`` mints a provenance-exempt evidence node keyed by the
    pointer); and the result node gains ``validates::<evidence-node>`` minted through the
    one home (``schema.token_for``) — so the gauge's resolvable forward read counts it.
    Returns the number of validates edges emitted."""
    if not name or repo_root is None:
        return 0
    try:
        from laplace.pipeline import registry as _registry
        proj = _registry.all_projects(repo_root=repo_root).get(name)
    except Exception:  # noqa: BLE001 — a registry hiccup wires nothing, never a crash
        return 0
    if proj is None or not getattr(proj, "evidence_store", ""):
        return 0                                  # no evidence store => true zeros
    project_dir = getattr(proj, "project_dir", "") or ""
    if not project_dir:
        return 0
    project_root = (Path(repo_root) / project_dir).resolve()
    # containment belt (the same fence resolve_corpus enforces): never read outside the repo.
    try:
        if not project_root.is_relative_to(Path(repo_root).resolve()):
            return 0
    except (OSError, ValueError):
        return 0
    # the one evidence parser (never re-typed here — the parallel-path trap): its
    # deref decides which pointers are LIVE. Imported function-locally so corpus_ingest
    # keeps no top-level dependency on the scripts tree, and a missing/broken ingest
    # module simply wires nothing.
    try:
        import sys as _sys
        # The parser is implementation code from this checkout; ``repo_root`` is
        # the data root and is intentionally redirectable for isolated runs.
        scripts_dir = str((source_tree() / "scripts").resolve())
        if scripts_dir not in _sys.path:
            _sys.path.insert(0, scripts_dir)
        import ingest_synthetic as _ing
        _regraded, edges = _ing.build(project_root, name)
    except Exception:  # noqa: BLE001 — parse failure => no wiring (fail-closed)
        return 0

    from laplace.pipeline import schema as _schema
    live_by_claim = (edges or {}).get("claim_to_validation") or {}
    root_id = next((n for n, p in parent_map.items() if p is None), "paper://")
    emitted = 0
    for cid in sorted(live_by_claim):
        node = _clm_to_node(cid)
        if node not in leaves:
            continue                              # no dangling: the claim has no node here
        for ptr in sorted(dict.fromkeys(live_by_claim[cid])):
            # resolve the pointer to a LIVE evidence node the validates edge can target.
            tgt: str
            if ptr.startswith("ledger:") and ptr.split(":", 1)[1] in leaves:
                tgt = ptr.split(":", 1)[1]        # fold onto the existing assumption-param node
            else:
                tgt = ptr                         # mint (or reuse) an evidence node keyed by the pointer
                if tgt not in leaves:
                    leaves[tgt] = {"kind": "support",
                                   "essence": f"evidence reading {ptr}",
                                   "keywords": _kw(ptr, [ptr]), "postulate": True}
                    parent_map[tgt] = parent_map.get(node) or root_id
                    edge_index.setdefault(tgt, [tgt])
            token = _schema.token_for("validates", tgt)   # the one minter
            row = edge_index.setdefault(node, [node])
            if token not in row:
                row.append(token)
                emitted += 1
            if relation_events is not None:
                relation_events.append({"source": node, "target": tgt,
                    "rel": "validated_by", "producer": "registered-evidence",
                    "mode": "deterministic", "detail": {"pointer": ptr, "claim": cid}})
    return emitted


def _source_relation_events(leaves: dict, edge_index: dict) -> list[dict]:
    """Relations directly witnessed by the selected source atomiser.

    Equation-to-equation references are the only source references promoted to
    premises.  Every other resolvable reference remains an inspectable connection
    with unknown logical force; citation, section and figure adjacency is not an
    entailment merely because both endpoints are nodes.
    """
    node_ids = set(leaves)
    out: list[dict] = []
    for source, tokens in edge_index.items():
        for target in tokens:
            if target == source or target not in node_ids or "::" in str(target):
                continue
            equation_ref = (leaves.get(source, {}).get("kind") == "equation"
                            and leaves.get(target, {}).get("kind") == "equation")
            out.append({"source": source, "target": target,
                        "rel": "prerequisite" if equation_ref else "unknown",
                        "producer": "selected-source", "mode": "explicit-reference",
                        "detail": {"inferential_basis": "equation-reference" if equation_ref
                                   else "none"}})
    return out


def _overlay_relation_state(records: list[dict]) -> tuple[dict[tuple[str, str], dict],
                                                          set[tuple[str, str]], list[dict]]:
    """Reduce edge records to the current authored relation per directed pair.

    This is derived state, not a third ledger.  A current overlay relation masks
    producer semantics for the same pair while retaining their provenance on the
    projected relation.  A remove masks the pair entirely.  Historical malformed
    rel/axis combinations survive as diagnostics instead of being rewritten.
    """
    from laplace.pipeline import schema
    current: dict[tuple[str, str], dict] = {}
    removed: set[tuple[str, str]] = set()
    diagnostics: list[dict] = []
    for index, row in enumerate(records):
        kind = row.get("kind")
        node, target = str(row.get("node") or ""), str(row.get("target") or "")
        pair = (node, target)
        if kind == "delete-node" and node:
            for existing in list(current):
                if node in existing:
                    current.pop(existing, None); removed.add(existing)
            continue
        if not all(pair):
            continue
        if kind == "remove-edge":
            candidates = [pair]
            reverse = (pair[1], pair[0])
            reverse_row = current.get(reverse) or {}
            if any(p.get("authored_axis") in {"supports", "demonstrates"}
                   and not p.get("explicit_relation")
                   for p in reverse_row.get("provenance") or []):
                candidates.append(reverse)
            for candidate in candidates:
                current.pop(candidate, None); removed.add(candidate)
            continue
        if kind not in {"add-edge", "confirm-edge", "retype-edge", "add-node"}:
            continue
        rel = str(row.get("rel") or "").strip()
        axis = str(row.get("axis") or "").strip()
        explicit_rel = bool(rel)
        # Historical axis-only bearer records use storage direction: the token
        # lives on the literature/figure bearer and points at the borne claim.
        # The public relation reads claim -> bearer.  Explicit ``rel`` records
        # use the public node -> target direction directly.
        if not rel and axis in {"supports", "demonstrates"}:
            pair = (target, node)
        if not rel:
            rel = schema.relation_for_axis(axis) or ("unknown" if axis else "prerequisite")
        semantics = schema.relation_semantics(rel) or schema.relation_semantics("unknown")
        if rel == "unknown" and axis:
            semantics = {**semantics, "axis": axis,
                         "direction": "axis-declared-non-inferential"}
        unknown_axis = bool(axis and axis not in schema.AXIS_NAMES)
        conflict = (f"Historical axis {axis!r} is not registered; its logical force is unresolved."
                    if unknown_axis else schema.relation_axis_error(rel, axis) if explicit_rel else None)
        if unknown_axis:
            semantics = {**semantics, "axis": axis, "direction": "unresolved"}
        if conflict:
            diagnostics.append({"type": "unknown-historical-axis" if unknown_axis else "relation-axis-conflict", "source": node,
                                "target": target, "record_id": row.get("id"),
                                "record_index": index, "issue": conflict})
        prior_provenance = list((current.get(pair) or {}).get("provenance") or [])
        current[pair] = {"source": pair[0], "target": pair[1], "rel": rel,
                         "axis": semantics.get("axis"),
                         "direction": semantics.get("direction"),
                         "inferential": bool(semantics.get("inferential")) and not conflict,
                         "ambiguous": bool(conflict),
                         "rationale": str(row.get("rationale") or ""),
                         "provenance": prior_provenance + [{"producer": "author-overlay",
                             "record_id": row.get("id"), "operation": kind,
                             "by": row.get("by"), "explicit_relation": bool(row.get("rel")),
                             "authored_axis": axis or None}],
                         "diagnostics": ([conflict] if conflict else [])}
        removed.discard(pair)
    return current, removed, diagnostics


def _cycle_paths(adjacency: dict[str, set[str]]) -> list[list[str]]:
    """Return deterministic inferential cycles, each canonicalised once."""
    cycles: set[tuple[str, ...]] = set()
    visiting: list[str] = []
    active: set[str] = set()
    done: set[str] = set()

    def canonical(path: list[str]) -> tuple[str, ...]:
        ring = path[:-1]
        if not ring:
            return tuple(path)
        rotations = [tuple(ring[i:] + ring[:i]) for i in range(len(ring))]
        best = min(rotations)
        return best + (best[0],)

    def walk(node: str) -> None:
        if node in done:
            return
        active.add(node); visiting.append(node)
        for target in sorted(adjacency.get(node, ())):
            if target in active:
                start = visiting.index(target)
                cycles.add(canonical(visiting[start:] + [target]))
            elif target not in done:
                walk(target)
        visiting.pop(); active.discard(node); done.add(node)

    for node in sorted(adjacency):
        walk(node)
    return [list(path) for path in sorted(cycles)]


def relation_projection(nodes: dict, edge_index: dict, records: list[dict] | None = None,
                        producer_events: list[dict] | None = None) -> tuple[list[dict], list[dict]]:
    """Project the merged graph into typed relations with retained provenance.

    ``edge_index`` remains the compatibility/general-graph carrier.  This view is
    rebuilt with the network and is never persisted.  Logical consumers use only
    the unambiguous relations whose contract says ``inferential``; graph consumers
    retain every connection.
    """
    from laplace.pipeline import schema
    records = records or []
    producer_events = producer_events or []
    overlay, removed, diagnostics = _overlay_relation_state(records)
    node_ids = set(nodes)
    by_pair: dict[tuple[str, str], list[dict]] = {}
    for event in producer_events:
        pair = (str(event.get("source") or ""), str(event.get("target") or ""))
        if all(pair) and pair[0] in node_ids and pair[1] in node_ids:
            by_pair.setdefault(pair, []).append(event)

    # Recover compatibility edges that predate producer instrumentation.  A
    # confirmed marker documents legacy derives semantics; an unmarked bare edge
    # is visible but cannot discharge a derivation gap.
    parsed_by_pair: dict[tuple[str, str], list[dict]] = {}
    bare_pairs: set[tuple[str, str]] = set()
    for holder, tokens in edge_index.items():
        for token in tokens:
            parsed = schema.parse_edge_token(token)
            if parsed is None:
                if token in node_ids and token != holder:
                    bare_pairs.add((holder, token))
                continue
            axis = parsed.get("axis")
            if axis == "connects":
                pair = (parsed.get("lo"), parsed.get("hi"))
            elif axis in {"supports", "demonstrates"}:
                pair = (parsed.get("target"), holder)  # bearer token -> public borne-by direction
            else:
                pair = (holder, parsed.get("target"))
            if all(pair) and pair[0] in node_ids and pair[1] in node_ids:
                parsed_by_pair.setdefault(pair, []).append(parsed)

    bearer_storage_pairs = {(str(row.get("node") or ""), str(row.get("target") or ""))
                            for row in records
                            if not row.get("rel") and row.get("axis") in {"supports", "demonstrates"}}
    bare_pairs.difference_update(bearer_storage_pairs)

    all_pairs = set(by_pair) | set(overlay) | bare_pairs | set(parsed_by_pair)
    relations: list[dict] = []
    for pair in sorted(all_pairs):
        if pair in removed or pair[0] not in node_ids or pair[1] not in node_ids:
            continue
        origins = by_pair.get(pair, [])
        provenance = [{"producer": e.get("producer"), "mode": e.get("mode"),
                       "detail": e.get("detail") or {}} for e in origins]
        if pair in overlay:
            row = dict(overlay[pair])
            row["provenance"] = provenance + row["provenance"]
            relations.append(row)
            continue

        # Producer-declared relations may coexist on one pair (for example a
        # source prerequisite later carrying independent validation evidence).
        grouped: dict[tuple[str, str | None], list[dict]] = {}
        for event in origins:
            rel = event.get("rel") if event.get("rel") in schema.RELATION_SEMANTICS else "unknown"
            sem = schema.relation_semantics(rel) or schema.relation_semantics("unknown")
            grouped.setdefault((rel, sem.get("axis")), []).append(event)
        for (rel, axis), events in sorted(grouped.items()):
            sem = schema.relation_semantics(rel) or schema.relation_semantics("unknown")
            relations.append({"source": pair[0], "target": pair[1], "rel": rel,
                "axis": axis, "direction": sem["direction"],
                "inferential": bool(sem["inferential"]), "ambiguous": rel == "unknown",
                "provenance": [{"producer": e.get("producer"), "mode": e.get("mode"),
                                "detail": e.get("detail") or {}} for e in events],
                "diagnostics": (["source connection has no documented logical force"]
                                if rel == "unknown" else [])})

        if grouped:
            continue
        parsed = parsed_by_pair.get(pair, [])
        derived = next((p for p in parsed if p.get("axis") == "derives"), None)
        if derived and derived.get("mode") in {"confirmed", "tentative"}:
            sem = schema.relation_semantics("prerequisite")
            relations.append({"source": pair[0], "target": pair[1],
                "rel": "prerequisite", "axis": "derives", "direction": sem["direction"],
                "inferential": True, "ambiguous": False,
                "provenance": [{"producer": "legacy-edge-index", "mode": derived.get("mode")}],
                "diagnostics": ["legacy inferential marker retained by compatibility policy"]})
            diagnostics.append({"type": "legacy-inferential-edge", "source": pair[0],
                                "target": pair[1], "mode": derived.get("mode")})
            continue
        typed = next((p for p in parsed if schema.relation_for_axis(p.get("axis"))), None)
        if typed:
            rel = schema.relation_for_axis(typed["axis"])
            sem = schema.relation_semantics(rel)
            relations.append({"source": pair[0], "target": pair[1], "rel": rel,
                "axis": typed["axis"], "direction": sem["direction"],
                "inferential": bool(sem["inferential"]), "ambiguous": False,
                "provenance": [{"producer": "legacy-edge-index", "mode": typed.get("mode")}],
                "diagnostics": []})
            continue
        if parsed:
            axis = parsed[0].get("axis")
            relations.append({"source": pair[0], "target": pair[1], "rel": "unknown",
                "axis": axis, "direction": "axis-declared-non-inferential",
                "inferential": False, "ambiguous": False,
                "provenance": [{"producer": "legacy-edge-index", "mode": parsed[0].get("mode")}],
                "diagnostics": []})
            continue
        relations.append({"source": pair[0], "target": pair[1], "rel": "unknown",
            "axis": None, "direction": "unresolved", "inferential": False, "ambiguous": True,
            "provenance": [{"producer": "legacy-bare-edge", "mode": "untyped"}],
            "diagnostics": ["bare edge has no documented inferential semantics"]})
        diagnostics.append({"type": "ambiguous-bare-edge", "source": pair[0], "target": pair[1]})

    adjacency: dict[str, set[str]] = {}
    for relation in relations:
        if relation.get("inferential") and not relation.get("ambiguous"):
            adjacency.setdefault(relation["source"], set()).add(relation["target"])
    for cycle in _cycle_paths(adjacency):
        diagnostics.append({"type": "inferential-cycle", "path": cycle})
    relations.sort(key=lambda r: (r["source"], r["target"], r["rel"], r.get("axis") or ""))
    return relations, diagnostics


def build_corpus_network(tex_root: Path | str, semantic: bool = False,
                         overlay: list[dict] | None = None,
                         name: str | None = None,
                         repo_root: Path | str | None = None) -> dict[str, Any]:
    """The up-pass: atomise -> (semantic provenance) -> build_tree -> build_reach, returning the
    {nodes, reach, lenses, root} shape the existing DOWN operators consume.

    ``semantic`` defaults OFF: it embeds (the heavy, PSU-gated step that tripped on a cold paper),
    so the VIEW path - which must stay light - never embeds. The structural conceptric (sections,
    equations, figures, citations + real \\eqref/\\cite/containment edges) is already true to view.
    The semantic provenance enrichment is opt-in (the measurement path / a cached or remote run).

    ``name``/``repo_root`` are optional: supplied (from :func:`corpus_network`), the
    deterministic evidence-edge pass (:func:`apply_evidence_edges`, W-G) wires the
    corpus' LIVE validation pointers into the edge_index the coverage gauge reads; absent,
    the pass no-ops (every other caller of the raw up-operator is unchanged)."""
    tex_root = Path(tex_root)
    root_file = None
    if name and repo_root is not None:
        from laplace.manuscript import manuscript_source
        selected = manuscript_source.resolve(name, repo_root=repo_root)
        if selected.get('root'):
            root_file = Path(repo_root) / selected['root']
    leaves, edge_index, parent_map = atomise_paper(tex_root, root_file=root_file)
    relation_events = _source_relation_events(leaves, edge_index)
    n_sem = semantic_provenance(leaves, edge_index, relation_events=relation_events) if semantic else 0
    n_sem += apply_semantic_wires(tex_root, edge_index, relation_events=relation_events)   # the offline node-level pass's cache
    if overlay:
        apply_overlay(leaves, edge_index, overlay, parent_map)   # the human's rewiring, compounded in
    # the deterministic evidence-edge pass (W-G): after the human overlay so the poured
    # result/claim nodes are present, before build_tree so the minted evidence nodes are
    # consolidated into the tree. A no-op unless (name, repo_root) name a corpus with a
    # registered evidence_store.
    n_val = apply_evidence_edges(leaves, edge_index, parent_map, name, repo_root,
                                 relation_events=relation_events)

    def parent_of(nid: str) -> str | None:
        return parent_map.get(nid)

    nodes = keeper.build_tree(leaves, parent_of, root_id="paper://")
    reach = build_reach(nodes, edge_index)
    root = next((k for k, v in nodes.items() if v.get("parent") is None), "paper://")
    postulates = {k for k, lf in leaves.items() if lf.get("postulate")}
    # the SPINE: the apex narrative chain of high-level results, manually curated (his ruling
    # 2026-06-29). Computed from the overlaid leaves (the same pattern as postulates) so it never
    # depends on build_tree preserving custom fields. Ordered; each carries its narrative connective.
    spine = sorted(
        ({"id": k, "ord": lf.get("spine_ord", 0), "narrative": lf.get("spine_narrative", ""),
          "essence": lf.get("essence", ""), "kind": lf.get("kind")}
         for k, lf in leaves.items() if lf.get("spine")),
        key=lambda s: (s["ord"], s["id"]))
    ctx = {k: lf["ctx"] for k, lf in leaves.items() if lf.get("ctx")}   # the derivation lead-in prose
    relations, relation_diagnostics = relation_projection(
        nodes, edge_index, records=overlay or [], producer_events=relation_events)
    return {"nodes": nodes, "reach": reach, "lenses": {}, "root": root,
            "edge_index": edge_index, "postulates": postulates, "spine": spine,
            "ctx": ctx, "n_semantic_edges": n_sem, "n_validation_edges": n_val,
            "relations": relations, "relation_diagnostics": relation_diagnostics}


# The author's persisted cockpit state (gitignored local knobs). Mirrors
# scanner.COCKPIT_FILE — kept as a local constant so the corpus layer never has to
# import the server module (scanner already imports corpus_ingest; the reverse
# would close the loop). Read-only here; scanner.cockpit_state owns the write.
_COCKPIT_FILE = ".cockpit.json"


def active_corpus(repo_root: Path | str | None = None) -> str:
    """The author's persisted active project — the ``active_corpus`` key of the
    gitignored ``.cockpit.json`` (scanner.cockpit_state is its one writer), or
    ``""`` when the file is absent, unreadable, corrupt, or carries no such key.
    Pure read and FAIL-CLOSED: a broken cockpit NEVER raises — the serving path
    must degrade to the derived default, never 500 on local state."""
    if repo_root is None:
        return ""
    p = Path(repo_root) / _COCKPIT_FILE
    try:
        state = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if isinstance(state, dict):
        v = state.get("active_corpus")
        if isinstance(v, str):
            return v.strip()
    return ""


def registered_corpora(repo_root: Path | str | None = None,
                       openable: bool = False) -> list[str]:
    """Every registered corpus name: the registry's conceptric rows
    (:func:`registry.conceptric_projects`, the one door — W-growth G0).
    Membership IS registry membership — there is no second list to consult (the
    desync his 2026-08-04 catch named: every project born through the dashboard
    door after 07-22 was invisible to the viewer because two serving-path
    consumers still read a hardcoded dict; that dict is now data, migrated into
    the registry itself). ``openable=True`` additionally applies the same
    ``main.tex`` gate :func:`resolve_corpus` applies, so a roster never offers a
    name that 404s on open.

    DEGRADED MODE — a registry read that RAISES yields an EMPTY roster, logged at
    error level. The old behaviour handed back the hardcoded keys ("a degraded
    roster beats a dead switch"), but with the dict retired the only stale source
    left would be a second parse of the registry's own data file — a second door,
    rebuilt to paper over the first one failing. An empty switcher with a loud log
    is the truthful report: the roster is unknown, not empty-because-nothing-exists.
    Every caller already handles an empty roster (``default_corpus`` returns
    ``""``, ``/corpus/list`` serves an empty list), so this degrades, never 500s."""
    try:
        from laplace.pipeline import registry
        rows = registry.conceptric_projects(repo_root)
    except Exception:
        logging.exception("corpus roster unavailable: the registry read failed "
                          "(serving an empty roster, NOT a stale one)")
        return []
    names = [r["name"] for r in rows]
    if openable and repo_root is not None:
        names = [n for n in names if resolve_corpus(repo_root, n) is not None]
    return names


def default_corpus(repo_root: Path | str | None = None) -> str:
    """The corpus a view opens on when no ``?corpus=`` rides the URL. NEVER a
    hardcoded name (the law-of-laws leak, his 2026-07-03): the active project
    env var wins (an explicit session override), else the author's PERSISTED
    active project (``.cockpit.json`` active_corpus, W0.2), else the corpus whose
    friction ledger moved most recently (the one actually being worked), else the
    first registered corpus. Every candidate is validated against the registry
    roster (:func:`registered_corpora`) so a stale or foreign persisted value
    fails closed onto the derived default.

    The roster validated against is the OPENABLE one — the same list
    ``/corpus/list`` serves beside this default. Validating against the
    unfiltered roster let the served default name a corpus that is absent from
    the switcher and 404s on open (the window a project born before its
    ``main.tex`` settles sits in). When NOTHING is openable the unfiltered
    roster is used: with an empty switcher every default 404s anyway, so the
    registered name is the more useful report.

    DEGRADED MODE — an EMPTY registry roster yields ``""``, the no-project
    answer. Until 2026-08-04 this returned the first key of a hardcoded dict,
    which meant a broken or empty registry served a name the switcher did not
    offer; with the dict retired there is no name to invent. ``""`` is a value
    every consumer already handles (an unknown corpus fails closed to a plain
    label and ``main_tex=None``, never a raise)."""
    import os
    names = registered_corpora(repo_root, openable=True) or registered_corpora(repo_root)
    env = os.environ.get("LAPLACE_ACTIVE_PROJECT", "").strip()
    if env in names:
        return env
    if repo_root is not None:
        persisted = active_corpus(repo_root)
        if persisted in names:
            return persisted
        newest, newest_mt = "", 0.0
        for name in names:
            f = Path(repo_root) / "corpus_friction" / f"{name}.jsonl"
            try:
                mt = f.stat().st_mtime
            except OSError:
                continue
            if mt > newest_mt:
                newest, newest_mt = name, mt
        if newest:
            return newest
    return names[0] if names else ""


def project_context(repo_root: Path | str,
                    corpus: str = "") -> dict[str, str | None]:
    """The one project context a bare view opens on: the active corpus, its
    server-derived main tex (repo-relative), the compiled PDF when present, an
    plain label, and ``source`` naming how the tex was found. When ``corpus`` is
    empty the active project (``default_corpus``) is used. FAIL-CLOSED: an unknown
    corpus or a corpus with no artefact yields ``main_tex=None`` with a plain
    label, never a raise.

    The root resolution DELEGATES to the one server-canonical
    :func:`registry.project_context` (W0.3): /projection therefore bootstraps the
    SAME current artefact /review shows — for subset-sum-itqde the REAL
    ``whitepaper/main.tex`` (the two-root repair), never the 35-line ``tex/main.tex``
    stub the registered tex root used to hand back. Only the resolved paths change; the
    return shape ``{corpus, main_tex, pdf, label, source}`` is preserved for the
    /projection and /review context consumers. The active-project resolution
    (LAPLACE_ACTIVE_PROJECT / the cockpit) is unchanged."""
    rr = Path(repo_root)
    name = (corpus or "").strip() or default_corpus(rr)
    out: dict[str, str | None] = {
        "corpus": name, "main_tex": None, "pdf": None,
        "label": name, "source": "main-tex",
    }
    from laplace.pipeline import registry
    ctx = registry.project_context(name, rr)
    if ctx is None:
        out["source"] = "unknown-corpus"
        out["label"] = f"{name} (unknown corpus)"
        return out
    art = ctx.current_artefact            # THE one server-computed {pdf, tex, version_id, kind}
    out["main_tex"] = art["tex"]
    out["pdf"] = art["pdf"]
    if art["tex"]:
        out["source"] = "main-tex"        # a real main.tex resolved at the artefact root
    elif art["pdf"]:
        out["source"] = "newest-pdf"
        out["label"] = f"{name} (no main.tex — {art['kind'] or 'pdf'})"
    else:
        out["source"] = "no-artefact"
        out["label"] = f"{name} (no main.tex, no PDF)"
    return out


# Per-corpus extra roots searched for figure/code assets that live OUTSIDE the paper tree.
# Resolved relative to $HOME so they survive across machines. The asset endpoint's by-convention
# search hits the in-tree dirs (synthetics papers/<corpus>/source, /figures, /code, ...) FIRST;
# these extras are only a fallback when assets aren't in the paper's tree yet.
CORPUS_ASSET_ROOTS: dict[str, list[str]] = {
    # free-snacks: full source is now in-tree under synthetics papers/free-snacks/source/ — no
    # external fallback needed.
}
_CORPUS_CACHE: dict[str, dict] = {}
_CANDIDATE_FILE = ".corpus_candidates.json"   # gitignored cache: the embedding step, run once


def corpus_candidates(tex_root: Path | str, k: int = 3, refresh: bool = False) -> dict[str, list]:
    """Top-k semantic EARLIER-equation candidates per equation, cached to disk. THIS is the embedding
    step (PSU-gated) - run once, offline; the view path only ever READS the cache. The faithfulness
    test says the true \\eqref edge is among the top-3 ~75% of the time, so these are exactly the
    candidates the human confirms/corrects in the rewire panel (supplying the precision @1 lacks)."""
    tex_root = Path(tex_root)
    cache = tex_root / _CANDIDATE_FILE
    if cache.is_file() and not refresh:
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    leaves, _ei, _pm = atomise_paper(tex_root)
    eqs = sorted([e for e, lf in leaves.items() if lf.get("kind") == "equation"],
                 key=lambda e: leaves[e].get("ord", 0))
    out: dict[str, list] = {}
    try:
        import numpy as np
        from laplace.representation.embed_router import get_backend
        backend = get_backend()
        texts = [f"{leaves[e].get('ctx','')} {leaves[e].get('essence','')}"[:512] for e in eqs]
        X = np.asarray(backend.embed(texts), dtype=np.float64)
        X /= np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-12, None)
    except Exception:  # noqa: BLE001 - no embedder -> empty candidates, the view degrades gracefully
        return {}
    for i, e in enumerate(eqs):
        if i == 0:
            continue
        sims = X[:i] @ X[i]
        top = list(np.argsort(-sims))[:k]
        out[e] = [{"id": eqs[j], "sim": round(float(sims[j]), 3)} for j in top]
    cache.write_text(json.dumps(out), encoding="utf-8")
    return out


# --- the conceptric-friction ledger: the human's REWIRING, persisted + compounding -----------------

def _rewire_path(repo_root: Path | str, name: str, *, ensure_dir: bool = False) -> Path:
    # WO-20260821-mkdir-on-read-path: a PURE READ must not create directories - the
    # mkdir rides only when a WRITER asks for it (a read-intent invocation never mutates).
    d = Path(repo_root) / "corpus_friction"
    if ensure_dir:
        d.mkdir(parents=True, exist_ok=True)
    return d / f"{re.sub(r'[^a-z0-9_-]', '_', name)}.jsonl"


def rewire_list(repo_root: Path | str, name: str) -> list[dict]:
    from laplace.pipeline.ledger import read_jsonl
    return read_jsonl(_rewire_path(repo_root, name))


def friction_current(records: list[dict]) -> list[dict]:
    """Collapse the append-only friction event log to the CURRENT per-node state - one deposit per
    live node, not every event ever emitted (his 2026-07-03: a PDF-sourced corpus authors its whole
    conceptric AS friction deposits, so the raw log is the build history, not a rewiring queue, and
    the tab must show the reduced present, not thousands of stale events). Mirrors apply_overlay's
    net effect per node: last-write-wins essence/kind, delete-node removes, set-projection.retired
    drops. Emits newest-authored first, each marked applied (it is the state, not a pending edit)."""
    state: dict[str, dict] = {}
    order: dict[str, int] = {}
    retired: set[str] = set()
    for i, r in enumerate(records):
        node, k = r.get("node"), r.get("kind")
        if not node:
            continue
        if k == "delete-node":
            state.pop(node, None); retired.discard(node); continue
        if k == "add-node":
            state[node] = {"kind": "node", "node": node, "node_kind": r.get("node_kind"),
                           "essence": r.get("essence", ""), "ts": r.get("ts"),
                           "by": r.get("by"), "applied": True}
            order.setdefault(node, i)
        elif k == "edit-essence" and node in state and r.get("value"):
            state[node]["essence"] = r["value"]; state[node]["ts"] = r.get("ts")
        elif k == "set-kind" and node in state and r.get("value"):
            state[node]["node_kind"] = r["value"]
        elif k == "set-status" and node in state and r.get("value"):
            st = _canonical_status(r["value"])
            if st:
                state[node]["status"] = st; state[node]["ts"] = r.get("ts")
        elif k == "set-projection" and isinstance(r.get("value"), dict) and "retired" in r["value"]:
            (retired.add if r["value"]["retired"] else retired.discard)(node)
    live = [state[n] for n in state if n not in retired]
    live.sort(key=lambda rec: -order.get(rec["node"], 0))   # newest-authored first
    return live


# the write gate's kind vocabulary lives in the one schema module (leaf import,
# no cycle); the local name is kept so every existing reference reads unchanged.
from laplace.pipeline.schema import FRICTION_KINDS as _FRICTION_KINDS
from laplace.pipeline.schema import REWIRE_KINDS as _REWIRE_KINDS
from laplace.pipeline.schema import (
    AXIS_NAMES as _AXIS_NAMES,
    PAIR_AXES as _PAIR_AXES,
    EPISTEMIC_STATUSES as _EPISTEMIC_STATUSES,
    canonical_status as _canonical_status,
    token_for as _token_for,
    EDGE_RELATIONS as _EDGE_RELATIONS,
    relation_axis_error as _relation_axis_error,
    relation_for_axis as _relation_for_axis,
    relation_semantics as _relation_semantics,
    parse_edge_token as _parse_edge_token,
)


def rewire_add(repo_root: Path | str, name: str, payload: dict, *, precondition=None) -> dict:
    """Deposit one rewiring friction record. Append-only; applied as an overlay on the next build
    (friction -> regrow). kinds:
      confirm-edge|add-edge|remove-edge  — the dependency edges (target=the derived-from node)
      reclassify|edit-essence            — postulate-toggle / rewrite the content
      set-kind                           — retag into the LOGICAL_KINDS taxonomy (value=kind)
      add-node                           — insert a node (node=new id, parent, node_kind, essence,
                                           optional target=a born edge; optional axis types that
                                           born edge — supports for a citation minted from a
                                           node-scoped search — else it is a confirmed derives edge)
      move-node                          — reparent (target=new parent)
      delete-node                        — remove (children reparent to keep the tree whole)
      set-spine                          — place on the apex narrative chain (ord, narrative)
      unset-spine                        — remove from the chain
      set-source                         — replace canonical source locators (value=array), preserving content and proof
      set-status                         — write the node's epistemic status (value=one of
                                           schema.EPISTEMIC_STATUSES, or a STATUS_ALIASES carrier)
    add-edge/confirm-edge take an optional ``axis`` (a schema.TARGET_AXES name); an add-node
    takes an optional ``supersedes`` (an older node id the new node retires — goal versioning)
    and an optional ``ref`` (the source locator, file+lines or file#id — the same field every
    builder-emitted node carries, so a door-deposited node cites its source as a FIELD instead
    of folding it into the essence prose).
    """
    import datetime as _dt
    kind = (payload.get("kind") or "").strip()
    node = (payload.get("node") or "").strip()
    if kind not in _REWIRE_KINDS or not node:
        return {"error": "kind and node required"}
    if kind == "set-kind" and payload.get("value") not in LOGICAL_KINDS:
        return {"error": f"set-kind value must be one of {LOGICAL_KINDS}"}
    if kind == "add-node" and (payload.get("node_kind") or "derivation-step") not in LOGICAL_KINDS:
        return {"error": f"add-node node_kind must be one of {LOGICAL_KINDS}"}
    if kind == "set-status" and _canonical_status(payload.get("value")) is None:
        return {"error": f"set-status value must resolve to one of {_EPISTEMIC_STATUSES} "
                         "(an alias in schema.STATUS_ALIASES folds too)"}
    # An authored relation is the semantic carrier; ``axis`` is its storage
    # family and may not contradict it.  Axis-only legacy callers remain
    # accepted where the registry has an exact relation mapping.
    axis = (payload.get("axis") or "").strip()
    if axis:
        if axis not in _AXIS_NAMES:
            return {"error": f"axis must be one of {_AXIS_NAMES}"}
        if axis in _PAIR_AXES and (payload.get("rel") or "").strip() != "analogy":
            return {"error": f"axis {axis!r} is a lateral pair family, not an edge-target axis"}
    rel = (payload.get("rel") or "").strip()
    if rel and rel not in _EDGE_RELATIONS:
        return {"error": f"rel must be one of {sorted(_EDGE_RELATIONS)}"}
    conflict = _relation_axis_error(rel, axis)
    if conflict:
        return {"error": conflict}
    if kind == "retype-edge" and not rel:
        return {"error": "retype-edge requires an explicit rel"}
    root = Path(repo_root).resolve()
    tex_root = resolve_corpus(root, name)
    if tex_root is None:
        # The long-standing isolated-ledger rehearsal keeps the authoritative
        # corpus source in this checkout while redirecting only corpus_friction
        # to a temporary root. Preserve that read-only source seam; writes still
        # land solely beneath the supplied repo_root.
        source_root = source_tree()
        tex_root = resolve_corpus(source_root, name)
    try:
        net = corpus_network(tex_root, repo_root=root, name=name) if tex_root else {"nodes": {}, "edge_index": {}}
    except (OSError, ValueError, KeyError) as exc:
        return {"error": f"current conceptric is unavailable: {exc}"}
    nodes = net.get("nodes") or {}
    target = str(payload.get("target") or "").strip()
    existing_node_op = kind not in {"add-node"}
    if existing_node_op and node not in nodes:
        return {"error": f"node is not live: {node}"}
    if kind == "add-node" and node in nodes:
        return {"error": f"node already exists: {node}"}
    if kind == "set-source":
        from laplace.research.mathematical_records import validate_source_replacement
        try:validate_source_replacement(name,payload.get("value"),root)
        except (ValueError,OSError,TypeError) as exc:return {"error":str(exc)}
    if kind == "add-node" and payload.get("ref") is not None:
        from laplace.research.mathematical_records import validate_created_source_reference
        try:validate_created_source_reference(name,payload["ref"],root)
        except (ValueError,OSError,TypeError) as exc:return {"error":str(exc)}
    if kind in {"add-edge", "confirm-edge", "remove-edge", "retype-edge", "move-node"}:
        if not target or target not in nodes:
            return {"error": f"target is not live: {target or '<missing>'}"}
        if target == node:
            return {"error": "self-links and self-parenting are refused"}
    if kind == "move-node" and node == net.get("root"):
        return {"error": "the canonical conceptric root cannot be moved"}
    if kind == "add-node":
        parent = str(payload.get("parent") or "").strip()
        if parent and parent not in nodes:
            return {"error": f"parent is not live: {parent}"}
        if target and target not in nodes:
            return {"error": f"target is not live: {target}"}
        if parent == node or target == node:
            return {"error": "a new node cannot parent or derive from itself"}
        supersedes = str(payload.get("supersedes") or "").strip()
        if supersedes and supersedes not in nodes:
            return {"error": f"superseded node is not live: {supersedes}"}
    if kind == "move-node":
        cursor, seen = target, set()
        while cursor and cursor not in seen:
            if cursor == node:
                return {"error": "move-node would create a containment cycle"}
            seen.add(cursor)
            cursor = str((nodes.get(cursor) or {}).get("parent") or "")
    if kind in {"remove-edge", "retype-edge"}:
        live_pairs = {(row.get("source"), row.get("target"))
                      for row in net.get("relations") or []}
        storage_pair = any(token == target or
                           ((parsed := _parse_edge_token(token)) is not None
                            and parsed.get("target") == target)
                           for token in (net.get("edge_index") or {}).get(node, []))
        if (node, target) not in live_pairs and not (kind == "remove-edge" and storage_pair):
            return {"error": "remove-edge names no current edge in node derives-from target direction"}
    effective_rel = rel or _relation_for_axis(axis) or ("unknown" if axis else "prerequisite")
    if kind in {"add-edge", "confirm-edge", "retype-edge"} and effective_rel == "prerequisite":
        prerequisite = {nid: set(inferential_dependencies(net, nid)) for nid in nodes}
        if kind == "retype-edge":
            prerequisite.get(node, set()).discard(target)
        stack, seen = [target], set()
        while stack:
            current = stack.pop()
            if current == node:
                return {"error": "prerequisite edge would create a dependency cycle (node derives-from target)"}
            if current in seen:
                continue
            seen.add(current); stack.extend(prerequisite.get(current, ()))
    rec = {"id": _dt.datetime.now().strftime("RW-%Y%m%d-%H%M%S-%f"),
           "ts": _dt.datetime.now().isoformat(timespec="seconds"),
           "kind": kind, "node": node, "target": payload.get("target"),
           "value": payload.get("value"), "by": payload.get("by", "gerard"), "status": "open"}
    # add-node / set-spine fields + the axis typing (edges) + supersedes (goal versioning)
    # + ``ref`` (the source citation): every builder-emitted node carries one (file+lines,
    # refs-only), and until now the door dropped it — so a node deposited through the
    # sanctioned door could only fold its source into the essence prose, while a node
    # emitted by a builder carried it as a field. Same shape, one vocabulary
    # (WO-20260820-rewire-append-drifts-the-builder).
    for extra in ("parent", "node_kind", "essence", "ord", "narrative", "axis", "rel", "supersedes",
                  "ref", "projection", "rationale"):
        if payload.get(extra) is not None:
            rec[extra] = payload[extra]
    from laplace.pipeline.ledger import append_jsonl
    def final_precondition():
        # Source availability/hash is part of a set-source mutation. Recheck it
        # in the ledger append critical section, adjacent to the optimistic
        # concept revision guard supplied by the concepts owner.
        if kind=="set-source":
            from laplace.research.mathematical_records import validate_source_replacement
            try:validate_source_replacement(name,payload.get("value"),root)
            except (ValueError,OSError,TypeError) as exc:return {"error":str(exc)}
        return precondition() if precondition is not None else None
    refusal=append_jsonl(_rewire_path(repo_root, name, ensure_dir=True), rec,
                         precondition=final_precondition)
    if refusal:return refusal
    return {"ok": True, "record": rec}


def friction_add(repo_root: Path | str, name: str, payload: dict) -> dict:
    """Deposit one friction/fork record — the one sanctioned write door for the
    unified friction channel (2026-07-11 learning-loop design §1b; the sibling of
    :func:`rewire_add`, mirror discipline). Bare ``append_jsonl`` would admit any
    mis-shaped dict; this gate validates ``kind`` against ``FRICTION_KINDS``,
    requires ``node`` + ``owning_layer``, mints ``id``/``ts``/``status: "open"``,
    and appends through the ledger's one write shape. kinds:
      friction — an engine stumble (dispatch, protocol, tooling); ``owning_layer``
                 names the organ that owns the fix
      fork     — an author decision the machine cannot make; lands on the ledger
                 of the substrate it arose on
    ``chain`` (RECOMMENDED, not yet required — seed records predate it) is the
    chain of custody: an ordered list of short goal-frame strings, coarse→fine
    (session goal → phase/bite → dispatch goal → local action), the descent
    from global goal to this local friction. When present its SHAPE is
    validated: a non-empty list of non-empty strings. The drain counts the
    chainless so the gap stays visible.
    """
    import datetime as _dt
    kind = (payload.get("kind") or "").strip()
    node = (payload.get("node") or "").strip()
    owning_layer = (payload.get("owning_layer") or "").strip()
    if kind not in _FRICTION_KINDS or not node:
        return {"error": f"kind must be one of {_FRICTION_KINDS} and node required"}
    if not owning_layer:
        return {"error": "owning_layer required (the organ that owns the fix)"}
    chain = payload.get("chain")
    if chain is not None:
        if (not isinstance(chain, (list, tuple)) or not chain
                or not all(isinstance(f, str) and f.strip() for f in chain)):
            return {"error": "chain must be a non-empty list of non-empty "
                             "strings, coarse→fine (session goal → phase/bite "
                             "→ dispatch goal → local action)"}
        chain = [f.strip() for f in chain]
    # the ledger's live idiom bands ids per writer session (…-0000XX, …-5000XX);
    # an explicit id is honoured, else the rewire_add mint shape is used
    rec = {"id": (payload.get("id") or "").strip()
                 or _dt.datetime.now().strftime("RW-%Y%m%d-%H%M%S-%f"),
           "ts": _dt.datetime.now().isoformat(timespec="seconds"),
           "kind": kind, "node": node, "target": payload.get("target"),
           "value": payload.get("value"), "by": payload.get("by", "eigen"),
           "status": "open", "owning_layer": owning_layer}
    # the remaining spine extras (evidence is normally filled at consumption,
    # by a resolution record — passed through here only if a reporter carries it)
    for extra in ("parent", "cost", "proposal", "evidence"):
        if payload.get(extra) is not None:
            rec[extra] = payload[extra]
    if chain is not None:
        rec["chain"] = chain
    from laplace.pipeline.ledger import append_jsonl
    append_jsonl(_rewire_path(repo_root, name, ensure_dir=True), rec)
    return {"ok": True, "record": rec}


def _remove_pair_tokens(edge_index: dict, source: str, target: str) -> None:
    """Remove every marker representation for one public directed relation pair."""
    from laplace.pipeline import schema
    edge_index[source] = [token for token in edge_index.get(source, [])
        if not (token == target
                or ((parsed := schema.parse_edge_token(token)) is not None
                    and ((parsed.get("axis") != "connects" and parsed.get("target") == target)
                         or (parsed.get("axis") == "connects"
                             and {parsed.get("lo"), parsed.get("hi")} == {source, target}))))]
    # supports/demonstrates are stored on the bearer and point back to the borne
    # logical node, so remove their reverse-storage tokens too.
    edge_index[target] = [token for token in edge_index.get(target, [])
        if not ((parsed := schema.parse_edge_token(token)) is not None
                and parsed.get("axis") in {"supports", "demonstrates"}
                and parsed.get("target") == source)]


def _apply_relation_tokens(edge_index: dict, source: str, target: str, rel: str,
                           *, mode: str = "confirmed") -> None:
    """Lay a relation's compatibility tokens while keeping the bare graph edge."""
    from laplace.pipeline import schema
    row = edge_index.setdefault(source, [])
    if target not in row:
        row.append(target)
    semantics = schema.relation_semantics(rel) or schema.relation_semantics("unknown")
    axis = semantics.get("axis")
    if axis == "derives":
        token = _token_for("derives", target, mode=mode)
        if token not in row:
            row.append(token)
    elif axis in {"validates", "implements"}:
        token = _token_for(axis, target)
        if token not in row:
            row.append(token)
    elif axis == "supports":
        reverse = edge_index.setdefault(target, [])
        token = _token_for("supports", source)
        if token not in reverse:
            reverse.append(token)
    elif axis == "connects":
        lo, hi = sorted((source, target))
        token = _token_for("connects", lo=lo, hi=hi, atoms="overlay", kind="analogy")
        if token not in row:
            row.append(token)


def apply_overlay(leaves: dict, edge_index: dict, records: list[dict],
                  parent_map: dict | None = None) -> None:
    """Apply the rewiring ledger to the atomised leaves+edges BEFORE consolidation, so the human's
    rewiring persists and compounds into the built object.

    Edge ops (confirm/add/remove-edge) and content ops (reclassify/edit-essence) need only
    leaves+edge_index. The NODE ops (add/delete/move-node, set-kind) — the vocabulary of building a
    conceptric together rather than only correcting a finished one — also reshape containment, so
    they need ``parent_map`` (the call site in build_corpus_network passes it; when None those ops
    no-op rather than corrupt a half-built tree)."""
    for r in records:
        k, node, tgt = r.get("kind"), r.get("node"), r.get("target")
        if k in ("confirm-edge", "add-edge", "retype-edge") and node and tgt:
            from laplace.pipeline import schema as _schema
            rel = (r.get("rel") or "").strip()
            axis = (r.get("axis") or "").strip()
            _remove_pair_tokens(edge_index, node, tgt)
            if not rel and axis and axis != "derives":
                row = edge_index.setdefault(node, [])
                if tgt not in row:
                    row.append(tgt)
                # Retain the original pair, but never invent a registered token
                # for a historical unknown axis. relation_projection carries
                # its exact authored axis/receipt as an unresolved diagnostic.
                if axis in _AXIS_NAMES and axis not in _PAIR_AXES:
                    token = _token_for(axis, tgt)
                    if token not in row:
                        row.append(token)
            else:
                rel = rel or _schema.relation_for_axis(axis) or "prerequisite"
                _apply_relation_tokens(edge_index, node, tgt, rel)
        elif k == "set-status" and node in leaves:
            st = _canonical_status(r.get("value"))                # fold the carrier into the enum
            if st:
                leaves[node]["status"] = st
        elif k == "remove-edge" and node and tgt:
            _remove_pair_tokens(edge_index, node, tgt)
        elif k == "reclassify" and node in leaves:
            leaves[node]["postulate"] = (r.get("value") == "postulate")
        elif k == "edit-essence" and node in leaves and r.get("value"):
            leaves[node]["essence"] = r["value"]
        elif k == "set-source" and node in leaves and isinstance(r.get("value"),list):
            prior_ref=leaves[node].get("source") or leaves[node].get("ref")
            if leaves[node].get("kind")=="citation" and isinstance(prior_ref,dict) and prior_ref.get("reference_key"):
                projection=dict(leaves[node].get("projection") or {})
                bibliography=dict(projection.get("bibliography") or {})
                for identity_field in ("reference_key","citekey"):
                    if prior_ref.get(identity_field):bibliography.setdefault(identity_field,prior_ref[identity_field])
                projection["bibliography"]=bibliography
                leaves[node]["projection"]=projection
            leaves[node]["source"] = r["value"]
            leaves[node]["ref"] = r["value"]
            leaves[node].pop("sources",None)
        # --- node CRUD: insert a derivation step / a result, retag, move, or remove a node ---------
        elif k == "set-kind" and node in leaves and r.get("value"):
            leaves[node]["kind"] = r["value"]
            leaves[node]["postulate"] = r["value"] in PROVENANCE_EXEMPT
        elif k == "add-node" and node and parent_map is not None:
            kind = r.get("node_kind") or "derivation-step"
            essence = r.get("essence") or ""
            leaves[node] = {"kind": kind, "essence": essence,
                            "keywords": _kw(essence or node, [node]),
                            "postulate": kind in PROVENANCE_EXEMPT}
            if r.get("ref") is not None:
                # ``ref`` is the canonical source locator carried by a deposited
                # logical object.  Keep it in the leaf under the same readable
                # source slot used by the concept API; containment changes must
                # never erase the object's identity or provenance.
                leaves[node]["source"] = r["ref"]
                leaves[node]["ref"] = r["ref"]
            if isinstance(r.get("projection"), dict):
                leaves[node]["projection"] = dict(r["projection"])
            parent = r.get("parent")
            if parent:
                parent_map[node] = parent
            edge_index.setdefault(node, [node])                 # its identity referent
            if tgt:                                             # born with an edge to a node
                from laplace.pipeline import schema as _schema
                axis = (r.get("axis") or "").strip()
                rel = (r.get("rel") or "").strip()
                if not rel and axis and axis != "derives":
                    row = edge_index.setdefault(node, [])
                    if tgt not in row:
                        row.append(tgt)
                    if axis in _AXIS_NAMES and axis not in _PAIR_AXES:
                        token = _token_for(axis, tgt)
                        if token not in row:
                            row.append(token)
                else:
                    rel = rel or _schema.relation_for_axis(axis) or "prerequisite"
                    _apply_relation_tokens(edge_index, node, tgt, rel)
            # goal versioning (the findings-ledger idiom): a v2 add-node naming an
            # older node in ``supersedes`` retires that node so exactly one live goal
            # remains — children reparent to keep the tree whole (mirrors delete-node).
            # A dangling target is a no-op and the add-node's own effect is kept
            # (append-only: the record is never dropped).
            sup = (r.get("supersedes") or "").strip()
            if sup and sup in leaves and sup != node:
                fallback = parent_map.get(sup)
                for child, par in list(parent_map.items()):
                    if par == sup:
                        parent_map[child] = fallback
                leaves.pop(sup, None)
                parent_map.pop(sup, None)
                edge_index.pop(sup, None)
                for kk in list(edge_index):                     # strip dangling references to the retired node
                    edge_index[kk] = [x for x in edge_index[kk]
                                      if x not in (sup, "sem::" + sup, "confirmed::" + sup)]
        elif k == "set-spine" and node in leaves:
            leaves[node]["spine"] = True                        # on the apex narrative chain
            try:
                leaves[node]["spine_ord"] = int(r.get("ord", 0) or 0)
            except (TypeError, ValueError):
                leaves[node]["spine_ord"] = 0
            if r.get("narrative") is not None:
                leaves[node]["spine_narrative"] = r["narrative"]   # the connective to the next result
        elif k == "unset-spine" and node in leaves:
            for sk in ("spine", "spine_ord", "spine_narrative"):
                leaves[node].pop(sk, None)
        elif k == "set-projection" and node in leaves and isinstance(r.get("value"), dict):
            # Emit-time slot: latex_label the projector emits as ``\label{...}``,
            # section_ref the beat this node belongs to (doubles as a virtual connectivity
            # edge in ``check_connectivity``), data_source for experiment-result figures so
            # the render is checkable against the CSV that produced it. Merge rather than
            # replace so a later set-projection can add a field without clobbering an
            # earlier one.
            leaves[node].setdefault("projection", {}).update(r["value"])
        elif k == "move-node" and node and tgt and parent_map is not None:
            if node in leaves:
                parent_map[node] = tgt
        elif k == "delete-node" and node and parent_map is not None:
            fallback = parent_map.get(node)                     # reparent children so the tree stays whole
            for child, par in list(parent_map.items()):
                if par == node:
                    parent_map[child] = fallback
            leaves.pop(node, None)
            parent_map.pop(node, None)
            edge_index.pop(node, None)
            for kk in list(edge_index):                         # strip dangling references to the gone node
                edge_index[kk] = [x for x in edge_index[kk]
                                  if x not in (node, "sem::" + node, "confirmed::" + node)]


def corpus_network(tex_root: Path | str, repo_root: Path | str | None = None,
                   name: str | None = None) -> dict[str, Any]:
    """A cached, embedding-free corpus network for the VIEW path. Applies the corpus's rewiring
    overlay (the human's accumulated edits) when (repo_root, name) are given - so the viewed object
    is the human-corrected one. Cache invalidates when the ledger grows."""
    overlay = rewire_list(repo_root, name) if (repo_root and name) else []
    sem = Path(tex_root) / _SEM_EDGE_FILE
    sem_stamp = f"{sem.stat().st_mtime_ns}:{sem.stat().st_size}" if sem.is_file() else "-"
    # The key must carry the overlay's IDENTITY, not its length: two equal-length
    # overlays on the same corpus (a base and a gated_apply rehearsal, or two
    # rehearsals) otherwise collide and the second caller reads the FIRST's
    # network — fictional gate verdicts in either direction (the B10 judge
    # proved a clean evolution wrongly refused on a stale dangling net).
    import hashlib as _hl
    overlay_stamp = (_hl.blake2s(json.dumps(overlay, sort_keys=True, default=str)
                                 .encode("utf-8")).hexdigest()[:16]
                     if overlay else "0")
    # ``name`` joins the key: the evidence-edge pass (W-G) keys its wiring on the
    # registered corpus (its evidence_store), so two corpora sharing a tex_root must not
    # read one another's validation-wired net.
    selected_stamp = ''
    if name and repo_root is not None:
        from laplace.manuscript import manuscript_source
        selected = manuscript_source.resolve(name, repo_root=repo_root)
        selected_stamp = str(selected.get('root')) + ':' + str(selected.get('revision'))
    key = f"{Path(tex_root).resolve()}::{name or '-'}::{overlay_stamp}::{sem_stamp}::{selected_stamp}"
    if key not in _CORPUS_CACHE:
        _CORPUS_CACHE[key] = build_corpus_network(
            tex_root, semantic=False, overlay=overlay, name=name, repo_root=repo_root)
    net = _CORPUS_CACHE[key]
    # carry the corpus identity on the net so a view FROM a node can resolve the project's
    # assets (the both-directions door: a node an asset supports doors back to that asset).
    # Additive and idempotent; absent when the net is built without (repo_root, name).
    if name:
        net["name"] = name
    if repo_root is not None:
        net["repo_root"] = str(repo_root)
    return net


def resolve_corpus(repo_root: Path | str, name: str) -> Path | None:
    """The corpus tex root for ``name``, or ``None``. The tex root is read from the one
    authoritative project list (:func:`registry.conceptric_projects`) — the registry is
    the one door (W-growth G0), and since 2026-08-04 the ONLY one: the hardcoded
    corpus→tex-root dict that used to gate this lookup is deleted, its keys migrated
    into the registry as data rows, so a dashboard-scaffolded project (e.g.
    crank-2026-07-15) and a finished paper resolve here by exactly the same route.
    The selected manuscript metadata determines the root filename. A named book
    remains openable without a main.tex alias; legacy unselected roots retain
    their ordinary main.tex resolution."""
    from laplace.pipeline import registry
    rel = next((row["tex_root"] for row in registry.conceptric_projects(repo_root)
                if row["name"] == name), None)
    if rel is None:
        # a source-optional project that owns its plan (writing.project_lifecycle) reads its concept network
        # from its own manuscript home; one without plan ownership still has none
        record = registry.resolve(name, repo_root)
        if record is not None and record.kind == "project" and record.plan_path:
            rel = record.tex_root
    p = Path(repo_root) / rel if rel else None
    if p is not None:
        # the containment belt (the G0 judge's catch): whatever the registry hands
        # back, a resolved root outside repo_root never leaves this function - the
        # merge-side fence is defense, this choke point is the guarantee.
        try:
            if not p.resolve().is_relative_to(Path(repo_root).resolve()):
                return None
        except OSError:
            return None
    if p is None: return None
    from laplace.manuscript import manuscript_source
    selected = manuscript_source.resolve(name, repo_root=repo_root)
    selected_path = Path(repo_root) / selected['root'] if selected.get('root') else p / 'main.tex'
    return p if selected_path.is_file() else None


def candidates_cached(tex_root: Path | str) -> dict[str, list]:
    """READ-ONLY candidate load — the view path's PSU-safe door. Returns the cached semantic
    candidates if the offline embedding pass has been run, else {}. NEVER embeds (unlike
    corpus_candidates, which will compute+cache on a miss)."""
    cache = Path(tex_root) / _CANDIDATE_FILE
    if cache.is_file():
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return {}


# --- the CONNECTIVITY engine: dependency grade + the typed directional neighborhood -----------------
# His ruling (2026-06-29): a node has ONE containment home (a tree) but MANY dependencies (a DAG).
# The viewer must show the node embedded in its connectivity - what it derives FROM (below, possibly
# many), what derives from IT (above, its consumers), and what couples WITHIN its grade (lateral).
# "The connectivity is what's really necessary to build the spine" - the high-level results are read
# off the DAG (deep below, many consumers above). All mechanical (edge_index + the reverse index).

def _dep_ids(edge_index: dict, nid: str, node_ids: set) -> list[str]:
    """Legacy bare-edge dependency reader for nets without a relation projection."""
    return [r for r in edge_index.get(nid, [])
            if r in node_ids and r != nid and "::" not in r]


def inferential_dependencies(net: dict, nid: str) -> list[str]:
    """The documented, unambiguous logical prerequisites of ``nid``.

    Built corpus networks always carry the derived ``relations`` projection.
    The bare-edge fallback exists only for older in-memory callers and fixtures
    that construct the pre-contract net shape directly.
    """
    nodes = net.get("nodes") or {}
    if "relations" not in net:
        return _dep_ids(net.get("edge_index") or {}, nid, set(nodes))
    relations = net.get("relations") or []
    stamp = (id(relations), len(relations))
    cached = net.get("_inferential_dependency_index")
    if not cached or cached[0] != stamp:
        adjacency: dict[str, list[str]] = {}
        for row in relations:
            if (row.get("target") in nodes and row.get("inferential")
                    and not row.get("ambiguous")):
                bucket = adjacency.setdefault(row.get("source"), [])
                if row["target"] not in bucket:
                    bucket.append(row["target"])
        cached = (stamp, adjacency)
        net["_inferential_dependency_index"] = cached
    return list(cached[1].get(nid, ()))


def relation_diagnostics(net: dict) -> list[dict]:
    """Public copy of ambiguity/conflict/cycle diagnostics on the merged view."""
    return [dict(row) for row in net.get("relation_diagnostics") or []]


def dep_grade(net: dict) -> dict[str, int]:
    """Grade by DERIVATIONAL depth, not containment: postulates/definitions and dependency-free
    nodes sit at the floor (0); every other node is 1 + the deepest dependency. Memoised DFS with a
    cycle guard (a derivation should be acyclic; a stray cycle degrades to 0 rather than looping).

    His ruling (2026-06-30): the SPINE is the top stratum of the conceptric by convention, not by
    derivational accident. After dependency depths are computed, every spine-tagged node is
    elevated to ``g_max`` (the highest dep_grade over all nodes), so the spine sits as a unified
    top tier regardless of how deep each beat's substrate climb happens to be. This is a read
    projection: it returns the spine-elevated grade map and never annotates the shared cached
    network. Consumers that need pre-elevation depths compute them explicitly alongside this map.
    """
    nodes = net["nodes"]
    post = net.get("postulates", set())
    memo: dict[str, int] = {}

    def g(nid: str, stack: frozenset) -> int:
        if nid in memo:
            return memo[nid]
        if nid in stack:
            return 0
        deps = inferential_dependencies(net, nid)
        if nid in post or not deps:
            memo[nid] = 0
            return 0
        val = max(0, 1 + max((g(d, stack | {nid}) for d in deps), default=-1))
        memo[nid] = val
        return val

    dep = {nid: g(nid, frozenset()) for nid in nodes}
    # Spine elevation: lift every spine-tagged node to g_max so the spine forms the top stratum.
    # Their dep_depth is recorded on the node for the dependency view; the returned grade is the
    # elevated one. The spine list (``net["spine"]``) is the canonical source -- ``build_tree``
    # drops per-leaf flags, so we read spine membership from the curated list, not from the node.
    if dep:
        g_max = max(dep.values())
        spine_ids = {s["id"] for s in net.get("spine", [])}
        for nid in nodes:
            if nid in spine_ids and dep.get(nid, 0) < g_max:
                dep[nid] = g_max
    return dep


def _prov(net: dict, holder: str, dep: str) -> str:
    """How a derives-from edge from holder->dep is attested: human-confirmed, semantic estimate,
    or explicit (a real \\eqref / the atomiser)."""
    for relation in net.get("relations") or []:
        if (relation.get("source"), relation.get("target")) == (holder, dep) \
                and relation.get("inferential") and not relation.get("ambiguous"):
            producers = {row.get("producer") for row in relation.get("provenance") or []}
            if "author-overlay" in producers:
                return "confirmed"
            if "semantic-provenance" in producers:
                return "semantic"
            return "explicit"
    lst = (net.get("edge_index") or {}).get(holder, [])
    if "confirmed::" + dep in lst:
        return "confirmed"
    if "sem::" + dep in lst:
        return "semantic"
    return "explicit"


def neighborhood(net: dict, nid: str, candidates: dict[str, list] | None = None,
                 cap: int = 16) -> dict[str, Any]:
    """The typed, directional neighborhood of nid - the connectivity view's data.

    below:   every node nid derives FROM (its dependencies; multiple, each tagged explicit/confirmed/
             semantic) + the unconfirmed semantic candidates (for confirm-in-place).
    above:   every node that derives from nid (its consumers - the reverse index, currently invisible).
    lateral: same-dependency-grade nodes that share a dependency with nid (within-grade coupling).
    Each neighbour carries id/kind/essence/grade/prov so the viewer renders math and places it by
    grade. Lists are capped (his no-silent-caps rule: the omitted count rides in 'truncated').

    Retired nodes (projection.retired) never appear as a neighbour: a retired node is out of the
    projection, so offering it as a dependency/consumer/lateral/candidate would wire live prose to
    dead structure (his: retired nodes must not show up in the editor offering redundant connections).
    The retired node itself stays viewable - only its role as OTHERS' neighbour is suppressed."""
    nodes = net["nodes"]
    candidates = candidates or {}
    dg = dep_grade(net)

    def _is_retired(mid: str) -> bool:
        n = nodes.get(mid, {})
        return bool(n.get("retired") or (n.get("projection") or {}).get("retired"))

    # traverse only the LIVE conceptric; the self node stays addressable even if retired
    node_ids = {m for m in nodes if not _is_retired(m) or m == nid}

    def enrich(mid: str, prov: str, **extra) -> dict:
        n = nodes.get(mid, {})
        return {"id": mid, "kind": n.get("kind"), "essence": n.get("essence", ""),
                "grade": dg.get(mid, 0), "prov": prov, **extra}

    def is_deriv(mid: str) -> bool:
        return nodes.get(mid, {}).get("kind") in DERIVATION_KINDS

    deps = [d for d in inferential_dependencies(net, nid) if d in node_ids and is_deriv(d)]
    below = [enrich(d, _prov(net, nid, d)) for d in deps]
    have = set(deps)
    for c in candidates.get(nid, []):
        if c["id"] not in have and c["id"] in node_ids and is_deriv(c["id"]):
            below.append(enrich(c["id"], "candidate", sim=c.get("sim")))

    above = [enrich(m, _prov(net, m, nid)) for m in node_ids
             if m != nid and is_deriv(m) and nid in inferential_dependencies(net, m)]

    gnid, dn = dg.get(nid, 0), set(deps)
    lateral = []
    for m in node_ids:
        if m == nid or not is_deriv(m) or dg.get(m, 0) != gnid:
            continue
        shared = dn & set(inferential_dependencies(net, m))
        if shared:
            lateral.append(enrich(m, "lateral", shared=sorted(shared)))
    lateral.sort(key=lambda x: -len(x["shared"]))

    def clip(lst):
        return lst[:cap], max(0, len(lst) - cap)

    below_c, below_t = clip(below)
    above_c, above_t = clip(above)
    lat_c, lat_t = clip(lateral)
    self_n = nodes.get(nid, {})
    return {
        "node": {"id": nid, "kind": self_n.get("kind"), "essence": self_n.get("essence", ""),
                 "grade": dg.get(nid, 0), "postulate": nid in net.get("postulates", set()),
                 "n_below": len(below), "n_above": len(above)},
        "below": below_c, "above": above_c, "lateral": lat_c,
        "truncated": {"below": below_t, "above": above_t, "lateral": lat_t},
        "relation_diagnostics": relation_diagnostics(net),
    }


def gaps(net: dict) -> list[str]:
    """The CONFABULATION ROOM, mechanically: every derivation node that is not a postulate and has
    no derivation dependency - its derivation is missing, so a projection would invent it. The
    systematic gap meter (his 'incompleteness of a derivation sub-tree IS the confabulation room')."""
    nodes = net["nodes"]
    post = net.get("postulates", set())

    def deriv_deps(x):
        return [d for d in inferential_dependencies(net, x)
                if nodes.get(d, {}).get("kind") in DERIVATION_KINDS]

    return [nid for nid, n in nodes.items()
            if n.get("kind") in DERIVATION_KINDS and nid not in post and not deriv_deps(nid)]


def derivation_subtree(net: dict, nid: str, max_nodes: int = 80) -> dict[str, Any]:
    """The COMPLETE derivation of nid as a self-contained sub-DAG: the transitive downward closure
    over derives-from, to the postulates/floor. His 'derivations complete as sub-trees so any result
    projects as a gap-free mini-doc.' Each node carries its grade + a gap flag (a non-postulate
    dead-end - where the derivation is incomplete). Capped, with the omitted count in 'truncated'."""
    nodes = net["nodes"]
    post = net.get("postulates", set())
    dg = dep_grade(net)

    def deriv_deps(x):
        return [d for d in inferential_dependencies(net, x)
                if nodes.get(d, {}).get("kind") in DERIVATION_KINDS]

    seen: dict[str, bool] = {}
    order: list[str] = []
    stack = [nid]
    truncated = 0
    while stack:
        x = stack.pop()
        if x in seen:
            continue
        if len(seen) >= max_nodes:
            truncated += 1
            continue
        seen[x] = True
        order.append(x)
        stack.extend(deriv_deps(x))
    sub_nodes, edges = [], []
    for x in order:
        n = nodes.get(x, {})
        gap = n.get("kind") in DERIVATION_KINDS and x not in post and not deriv_deps(x)
        sub_nodes.append({"id": x, "kind": n.get("kind"), "essence": n.get("essence", ""),
                          "grade": dg.get(x, 0), "postulate": x in post, "gap": gap})
        for d in deriv_deps(x):
            edges.append({"from": x, "to": d, "prov": _prov(net, x, d)})
    return {"root": nid, "nodes": sub_nodes, "edges": edges, "truncated": truncated,
            "relation_diagnostics": relation_diagnostics(net)}


def techniques(net: dict) -> list[dict]:
    """The TECHNIQUE LENS: each technique node with the nodes that use it, ordered by reach. This is
    how the recurring methods surface to the top — a second projection beside the result-spine."""
    nodes, ei = net["nodes"], net["edge_index"]
    out = []
    for tid, n in nodes.items():
        if n.get("kind") != "technique":
            continue
        users = [u for u in nodes if u != tid and tid in ei.get(u, [])]
        out.append({"id": tid, "essence": n.get("essence", ""),
                    "users": [{"id": u, "kind": nodes[u].get("kind"),
                               "essence": (nodes[u].get("essence") or "")[:90]} for u in users]})
    out.sort(key=lambda t: -len(t["users"]))
    return out


def dag_map(net: dict, max_nodes: int = 500) -> dict[str, Any]:
    """The whole DERIVATION DAG as one graded structure - the map you read the spine off. Every
    derivation node placed by dependency grade (floor of postulates -> apex of results), every
    derives-from edge, with spine/gap/postulate flags. Capped to the most-connected nodes if huge
    (his no-silent-caps: the dropped count rides in 'truncated')."""
    nodes = net["nodes"]
    post = net.get("postulates", set())
    dg = dep_grade(net)
    spine_ids = {s["id"] for s in net.get("spine", [])}
    gap_ids = set(gaps(net))

    def deriv_deps(x):
        return [d for d in inferential_dependencies(net, x)
                if nodes.get(d, {}).get("kind") in DERIVATION_KINDS]

    derivs = [nid for nid, n in nodes.items() if n.get("kind") in DERIVATION_KINDS]
    truncated = 0
    if len(derivs) > max_nodes:
        degree = {x: len(deriv_deps(x)) for x in derivs}
        for x in derivs:
            for d in deriv_deps(x):
                degree[d] = degree.get(d, 0) + 1
        derivs = sorted(derivs, key=lambda x: -degree[x])[:max_nodes]
        truncated = len([n for n in nodes.values() if n.get("kind") in DERIVATION_KINDS]) - max_nodes
    keep = set(derivs)
    mnodes = [{"id": x, "kind": nodes[x].get("kind"), "essence": nodes[x].get("essence", ""),
               "grade": dg.get(x, 0), "spine": x in spine_ids, "gap": x in gap_ids,
               "postulate": x in post} for x in derivs]
    medges = [{"from": x, "to": d} for x in derivs for d in deriv_deps(x) if d in keep]
    return {"nodes": mnodes, "edges": medges, "truncated": truncated,
            "max_grade": max((m["grade"] for m in mnodes), default=0), "n_gaps": len(gap_ids),
            "relation_diagnostics": relation_diagnostics(net)}


# --- math macro extraction: render the paper's OWN notation (kill KaTeX's red unknown-macro) -------
_NEWCMD_RX = re.compile(
    r"\\(?:newcommand|renewcommand|providecommand)\*?\s*\{?\s*\\([A-Za-z]+)\s*\}?\s*(?:\[(\d+)\])?\s*\{")
_DECLOP_RX = re.compile(r"\\DeclareMathOperator\*?\s*\{?\s*\\([A-Za-z]+)\s*\}?\s*\{")


def _balanced(s: str, i: int) -> str:
    """Content between the matching braces starting at s[i]=='{' (one level of nesting preserved)."""
    depth, out = 0, []
    while i < len(s):
        c = s[i]
        if c == "{":
            depth += 1
            if depth > 1:
                out.append(c)
        elif c == "}":
            depth -= 1
            if depth > 0:
                out.append(c)
            if depth == 0:
                break
        else:
            out.append(c)
        i += 1
    return "".join(out)


def search_nodes(net: dict, q: str, k: int = 24) -> list[dict]:
    """Find nodes by CONTENT, not id - the precondition for a usable surface (you wire by pointing
    at content you recognise, never by typing 'eq:fibre-contraction'). Embedding-free token/substring
    match over essence + id + kind + the derivation lead-in; ranked. Leaf nodes rank above containers."""
    q = (q or "").strip().lower()
    if not q:
        return []
    toks = [t for t in re.split(r"\W+", q) if t]
    ctx = net.get("ctx", {})
    scored = []
    for nid, n in net["nodes"].items():
        hay = (nid + " " + (n.get("essence") or "") + " " + (n.get("kind") or "") + " "
               + ctx.get(nid, "")).lower()
        score = 0
        if q in hay:
            score += 6
        score += sum(2 for t in toks if t in hay)
        if score:
            if n.get("leaf"):
                score += 1
            scored.append((score, nid, n))
    scored.sort(key=lambda x: -x[0])
    return [{"id": nid, "kind": n.get("kind"), "essence": (n.get("essence") or "")[:170],
             "grade": n.get("grade")} for _s, nid, n in scored[:k]]


def extract_macros(tex_root: Path | str) -> dict[str, str]:
    """The paper's \\newcommand / \\DeclareMathOperator definitions as a KaTeX macros map, so the
    viewer renders the author's real notation instead of red unknown-macro errors."""
    main = Path(tex_root) / "main.tex"
    if not main.is_file():
        return {}
    text = main.read_text(encoding="utf-8", errors="ignore")
    macros: dict[str, str] = {}
    for m in _NEWCMD_RX.finditer(text):
        macros["\\" + m.group(1)] = _balanced(text, m.end() - 1)
    for m in _DECLOP_RX.finditer(text):
        macros["\\" + m.group(1)] = "\\operatorname{" + _balanced(text, m.end() - 1) + "}"
    return macros


if __name__ == "__main__":      # Phase-1 verification: counts + the local faithfulness gate
    import sys
    from collections import Counter
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        "synthetics papers/law-of-laws/manuscript/tex")
    net = build_corpus_network(root)
    nodes = net["nodes"]
    kinds = Counter(n["kind"] for n in nodes.values() if n["leaf"])
    print("leaf kinds:", dict(kinds))
    print("total nodes:", len(nodes), "| grades:",
          dict(Counter(n["grade"] for n in nodes.values())))
    gate = keeper.local_faithfulness(nodes)
    print("faithfulness:", {k: gate[k] for k in ("pass", "internal_nodes", "checked", "ok")})
    if gate["bad"]:
        print("  bad:", gate["bad"][:5])
