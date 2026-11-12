"""stage_store.py — the stage-stores truth-as-code (the two demo lenses).

The stage-stores design (``DESIGN_2026-07-15_the-stage-stores.md``) is a RENDER; the
truth, when built, is the store schemas AS CODE (this module) and the row objects on
the real filesystem under ``corpus_stores/`` (design Law 8, top of the design doc).
This module is the minimal first cut named there: the TWO lenses whose held-out-SECTION
gate is cleanest to run end-to-end, per the audit's stage-stores readiness verdict
(``AUDIT_2026-07-15_the-pipeline-workflow-audit.md`` → "The stage-stores readiness
verdict": *"a store that can't pick the right exemplar for a held-out section does not
wire in"*). The other three lenses (paragraph_plan / derivation_walk / figure_caption)
are DESIGNED there, built later.

THE V2 ARCHITECTURE — stores are VIEWS of per-paper conceptrics (design §1c), never a
second decomposition. A per-paper conceptric is built FIRST through the proven UP
operator ``corpus_ingest.build_corpus_network`` (atomised section/equation/figure nodes,
explicit ``\\eqref``/``\\cite``/containment edges, dependency grades, the spine). The
store rows here DERIVE as views of that net: a ``section_architecture`` row reads the
section→member joins, a ``spine_chain`` row IS a path through the derivation DAG. Every
row's ``provenance.span_ref`` names the conceptric NODE IDS it came from — The view law:
every row is traceable to real nodes, no free text is invented. A row's ``embed_text`` is
the author's REAL prose span (the retrieval basis + audit handle, mirroring the voice
store); only the abstracted ``form`` is what a stage prompt would ever see (design §(a),
the FORM/EMBED split — surfacing structure, never content).

THE NAMESPACING (design §3, "per-paper namespacing — isolation is mechanical, not
trusted"). One JSONL per paper per store; :func:`write_store` takes ONE paper's rows and
writes ONLY ``<store>/<paper_id>.jsonl``. A writer physically cannot name another paper's
file — cross-paper contamination is a filesystem impossibility, not a trust assumption.
The merge (the store-wide ``_index.json``) is a SEPARATE fan-in that :func:`write_store`
performs after each per-paper write, exactly as the design's orchestrator-only merge step.

Determinism: the derivers carry no wall-clock and no randomness — the same ``net`` yields
byte-identical rows forever (the property the holdout gate's replayable verdict rests on).
Extraction is mechanical (model tokens ~zero — the point of v2); the row fields a view
CANNOT fill mechanically are listed in :data:`RESIDUE_FIELDS`, and those name exactly the
fleet's model-read residue.
"""
from __future__ import annotations
from laplace.core.checkout import source_tree

import json
import re
from pathlib import Path
from typing import Any

# repo root = src/laplace/pipeline/stage_store.py -> parents[3]
_REPO_ROOT = source_tree()
CORPUS_STORES = _REPO_ROOT / "corpus_stores"

#: The row fields a MECHANICAL view cannot fill faithfully — the model-read residue the
#: lensing fleet exists to supply (design §1c: "Model reads shrink to what a view cannot
#: derive mechanically — the FORM abstractions"). A field listed here is either emitted as
#: ``None`` (genuinely unavailable mechanically) or filled with a coarse mechanical PROXY
#: that stands in until a model read lands (marked in the docstrings below). The demo
#: reports these so the residue is named, never hidden.
RESIDUE_FIELDS: dict[str, list[str]] = {
    # job: a COARSE mechanical proxy stands in (position + title keyword); the faithful
    # fine-grained function-class ("establish-the-correspondence") is a model read.
    # arc / question_class: no mechanical basis — emitted None.
    "section_architecture": ["job(fine-grained)", "arc", "question_class"],
    # ladder_move: a mechanical num-dependency proxy stands in (extend/combine/synthesise);
    # the faithful move-class (generalise/specialise/apply/bound/contrast) is a model read
    # — and its gate refusal PROVES the proxy carries no prose signal (see the demo).
    # claim_class / supports_class: no mechanical basis — emitted None.
    "spine_chain": ["ladder_move(faithful)", "claim_class", "supports_class"],
    # paragraph_plan: an INHERITED row (imported from the voice store, stage zero) carries the
    # real-paragraph SKELETON — his prose span (embed_text) + its file/char/paragraph provenance
    # (span_ref) + mechanical length — but NONE of the FORM abstractions. Every field below is a
    # model read the fleet still owes; the import is a chunking-read not spent, not the lens read.
    "paragraph_plan": ["role", "connective_prev", "connective_next", "carries_math",
                       "carries_figure", "proposition_shape", "detail_level", "length_band"],
    # derivation_walk (§2.4): the WALK is mechanical (step position, rung span, what the step
    # connects, the arity step_kind proxy) but the STEP RHETORIC is model residue.
    #   step_kind(faithful): a COARSE arity proxy stands in ({define|advance|combine}); the faithful
    #     {define|substitute|expand|bound|limit|invoke-result} is a model read of the derivation prose.
    #   granularity / elision: no mechanical basis (does he show every line, one line, or only the
    #     result? does he elide via 'it-follows-that' / an appendix?) — emitted None.
    #   eq_env: the display environment name (align/gather/…) is NOT preserved by the conceptric — the
    #     atomiser keeps the env CONTENT as essence but drops the env tag — so it is emitted None here
    #     (a conceptric-absent field, not itself a prose read).
    "derivation_walk": ["step_kind(faithful)", "granularity", "elision", "eq_env"],
    # figure_caption (§2.5): caption presence/length + referenced-from-sections are mechanical (the
    # net's float nodes + \ref edges); the CAPTION RHETORIC is model residue.
    #   caption_move: {labels|asserts-then-shows|contrasts|quantifies} — a model read of the caption.
    #   figure_role: {schematic|evidence|comparison|data} — a model read.
    #   panels / panel_labels: the atomiser keeps only the figure's FIRST \label — subpanel structure
    #     is not in the conceptric — so both are emitted None (a re-read of the float supplies them).
    "figure_caption": ["caption_move", "figure_role", "panels", "panel_labels"],
}

_LABEL_RX = re.compile(r"\\label\{[^}]*\}?")


# --------------------------------------------------------------------------- #
# small mechanical rubrics (deterministic, model-free)
# --------------------------------------------------------------------------- #
def _clean_title(essence: str) -> str:
    """A section node's ``essence`` is the raw ``\\section{...}`` title, which may carry a
    trailing ``\\label{...}`` fragment (the atomiser's title regex stops at the first brace).
    Strip the label remnant and tidy whitespace — mechanical, no content invented."""
    t = _LABEL_RX.sub("", essence or "")
    return re.sub(r"\s+", " ", t).strip()


def _section_job(title: str, idx: int) -> str:
    """A COARSE, deterministic function-class for a section (design §2.2 ``job``), from its
    position + title keywords. This is a mechanical PROXY: the faithful job-class is a model
    read (see :data:`RESIDUE_FIELDS`). The proxy is the gate's class — the demo measures
    whether real-prose embedding proximity aligns with it."""
    t = (title or "").lower()
    if idx == 0:
        return "introduce"
    if re.search(r"conclu|outlook|summary|discussion|closing|remark", t):
        return "conclude"
    if re.search(r"numeric|simulat|illustrat|experiment|\bresult|hardware|implement", t):
        return "demonstrate"
    if re.search(r"algorithm|method|protocol|procedure|\btest|estimator|quadrature|sampling", t):
        return "method"
    return "develop"


def _ladder_move(n_deps: int) -> str:
    """A deterministic move-class for a spine rung (design §2.3 ``ladder_move``) from its
    equation in-degree in the derivation DAG. Mechanical PROXY for the faithful
    generalise/specialise/apply/bound/contrast (a model read; see :data:`RESIDUE_FIELDS`)."""
    if n_deps >= 3:
        return "synthesise"
    if n_deps == 2:
        return "combine"
    return "extend"


def _step_kind(n_eq_deps: int, is_postulate: bool) -> str:
    """A COARSE, deterministic step-class for a derivation step (design §2.4 ``step_kind``) from
    its equation-dependency ARITY in the derivation DAG. Mechanical PROXY: the faithful
    ``{define|substitute|expand|bound|limit|invoke-result}`` is a model read of the derivation
    prose (see :data:`RESIDUE_FIELDS`). The three arity classes are the derivation_walk store's
    GATE class — the demo measures whether real-prose embedding proximity aligns with them:
      * ``define``  — a base/axiom equation with NO equation prerequisite (the derivation floor).
      * ``advance`` — a single-prerequisite linear step.
      * ``combine`` — two or more prerequisites converge into this step.
    """
    if is_postulate or n_eq_deps == 0:
        return "define"
    if n_eq_deps == 1:
        return "advance"
    return "combine"


def _caption_band(n: int) -> list[int]:
    """A coarse length band ``[lo, lo+80]`` for a caption of ``n`` chars — the FORM of the length,
    never the caption itself (mirrors the paragraph-plan ``length_band``). Deterministic 80-char
    buckets, so retrieval never sees a raw count."""
    lo = (n // 80) * 80
    return [lo, lo + 80]


def _caption_size(n: int) -> str:
    """A COARSE, deterministic caption-length class (design §2.5) — the most class-shaped MECHANICAL
    field the figure schema carries (``caption_move`` / ``figure_role`` / ``panels`` are model
    residue). The figure_caption store's GATE class; three buckets so the gate has a real
    multi-class target:
      * ``terse`` (< 120 chars) · ``standard`` (120–319) · ``expansive`` (>= 320)."""
    if n < 120:
        return "terse"
    if n < 320:
        return "standard"
    return "expansive"


def _pid_tag(paper_id: str) -> str:
    """A short, stable, collision-resistant tag for a paper_id (used only in ``row_id``;
    the full paper_id always rides in ``provenance``). Initials of the hyphen parts, e.g.
    ``quantum-dynamical-emulation-itqde`` -> ``qdei``; a single-token id keeps its first
    eight chars."""
    parts = [p for p in re.split(r"[-_ ]+", paper_id) if p]
    if len(parts) >= 2:
        return "".join(p[0] for p in parts).lower()
    return (paper_id[:8] or "paper").lower()


def _eq_deps(net: dict[str, Any], eq_id: str) -> list[str]:
    """The logical equation prerequisites of ``eq_id``, sorted deterministically.

    ``edge_index`` remains a general-connectivity compatibility carrier. This
    stage-store is a derivation view, so it uses canonical inferential
    adjacency rather than promoting a support or citation into a rung.
    """
    from laplace.research import corpus_ingest as ci

    nodes = net["nodes"]
    return sorted(
        r for r in ci.inferential_dependencies(net, eq_id)
        if r != eq_id and r in nodes
        and nodes[r].get("kind") == "equation"
    )


# --------------------------------------------------------------------------- #
# LENS 1 — section-architecture (design §2.2)
# --------------------------------------------------------------------------- #
def derive_section_architecture(net: dict[str, Any], paper_id: str) -> list[dict[str, Any]]:
    """Derive the ``section_architecture`` store rows as a VIEW of ``net`` (design §2.2):
    one row per real section node. Mirrors the ``structural`` section contract.

    The MECHANICAL fields (filled from the conceptric):
      * ``position``      — "N-of-M" section order.
      * ``para_count``    — blank-line prose blocks in the section span.
      * ``forward_reach`` — later sections that ``\\ref`` this one ("used-by-K-later-sections").
      * ``carries``       — child equation / figure node counts (the section→member joins).
      * ``job``           — a COARSE proxy (position + title keyword); the faithful class is
                            model residue (:data:`RESIDUE_FIELDS`).
    The MODEL-RESIDUE fields (emitted ``None`` — a view has no mechanical basis):
      * ``arc`` {entry_state, exit_state}, ``question_class``.

    ``embed_text`` is the section's REAL opening+closing prose (the retrieval basis + audit
    handle) — read from the enrichment ``net["section_prose"]`` when present (the demo
    driver attaches it, keyed by the net's own section ids), else the cleaned section title.
    ``provenance.span_ref`` names the conceptric section NODE ID (the view law), plus the
    file + char span when the enrichment carries them (design §2.2 span_ref shape).

    Deterministic: sections are emitted in reading order; no wall-clock, no randomness.
    """
    nodes = net["nodes"]
    ei = net.get("edge_index", {})
    prose_map = net.get("section_prose", {})
    meta_map = net.get("section_meta", {})
    source_file = net.get("source_file")
    tag = _pid_tag(paper_id)

    sec_ids = [nid for nid, n in nodes.items() if n.get("kind") == "section"]
    # reading order: the enrichment's idx when present, else insertion order (a stable
    # tiebreak on id so two sections never sort ambiguously).
    sec_ids.sort(key=lambda s: (meta_map.get(s, {}).get("idx", 10_000), s))
    n_sec = len(sec_ids)
    order_index = {s: i for i, s in enumerate(sec_ids)}

    rows: list[dict[str, Any]] = []
    for pos, sid in enumerate(sec_ids):
        node = nodes[sid]
        meta = meta_map.get(sid, {})
        title = meta.get("title") or _clean_title(node.get("essence", ""))
        label = meta.get("label") or (sid if sid.startswith("sec:") else None)

        members = node.get("members") or []
        n_eq = sum(1 for m in members if nodes.get(m, {}).get("kind") == "equation")
        n_fig = sum(1 for m in members if nodes.get(m, {}).get("kind") == "figure")

        # forward_reach: later sections whose atomised referents include THIS section's id
        # or its real \label (a \ref{sec:X} lands X in that section's edge_index row).
        keys = {sid} | ({label} if label else set())
        reach = 0
        for other in sec_ids:
            if order_index[other] <= pos:
                continue
            if keys & set(ei.get(other, [])):
                reach += 1

        prose = prose_map.get(sid) or _clean_title(node.get("essence", "")) or sid
        span_ref: dict[str, Any] = {"node_ids": [sid], "section_label": label}
        if source_file:
            span_ref["file"] = source_file
        for k in ("char_start", "char_end", "paragraph_count"):
            if k in meta:
                span_ref[k] = meta[k]

        rows.append({
            "row_id": f"SA-{tag}-s{pos}",
            "embed_text": prose,
            "form": {
                "job": _section_job(title, pos),
                "arc": None,                       # model residue
                "question_class": None,            # model residue
                "position": f"{pos + 1}-of-{n_sec}",
                "para_count": meta.get("para_count"),
                "forward_reach": f"used-by-{reach}-later-sections",
                "carries": {"equations": n_eq, "figures": n_fig},
                "title": title,                    # mechanical, for the audit handle
            },
            "provenance": {
                "paper_id": paper_id,
                "source_kind": "tex",
                "extraction_lens": "section_architecture",
                "span_ref": span_ref,
            },
        })
    return rows


# --------------------------------------------------------------------------- #
# LENS 2 — spine-chain (design §2.3)
# --------------------------------------------------------------------------- #
def derive_spine_chain(net: dict[str, Any], paper_id: str) -> list[dict[str, Any]]:
    """Derive the ``spine_chain`` store rows as a VIEW of ``net`` (design §2.3): how results
    ladder. One row per equation that stands on a derivation rung — an equation node with at
    least one equation DEPENDENCY (an explicit ``\\eqref`` edge in the atomiser's DAG). The
    row IS a path through the dependency DAG (design §1c: "a spine-chain row IS the spine
    stratum").

    An authored/curated spine (``net["spine"]``, populated only by a rewiring overlay) is
    used when present; a freshly-atomised paper has none, so the ladder is read mechanically
    off ``corpus_ingest.dep_grade`` — the derivational depth that IS the ladder height.

    The MECHANICAL fields:
      * ``rung`` / ``of_rungs``   — this equation's dep-grade and the max grade (ladder top).
      * ``depends_on_rung``       — the grade of its deepest equation dependency.
      * ``ladder_move``           — a num-dependency PROXY (extend/combine/synthesise); the
                                    faithful move-class is model residue (:data:`RESIDUE_FIELDS`).
    The MODEL-RESIDUE fields (emitted ``None``): ``claim_class``, ``supports_class``.

    ``embed_text`` is the equation's REAL derivation lead-in prose (``net["ctx"]``) + its
    display LaTeX (the node ``essence``) — the retrieval basis, node-derived. ``span_ref``
    names the equation node + its dependency node ids + the parent section (the view law).

    Deterministic: rows are emitted sorted by (grade, id); no wall-clock, no randomness.
    """
    from laplace.research.corpus_ingest import dep_grade

    nodes = net["nodes"]
    ctx = net.get("ctx", {})
    tag = _pid_tag(paper_id)

    dg = dep_grade(net)
    eq_grades = [dg.get(nid, 0) for nid, n in nodes.items() if n.get("kind") == "equation"]
    of_rungs = max(eq_grades) if eq_grades else 0

    rungs = [nid for nid, n in nodes.items()
             if n.get("kind") == "equation" and _eq_deps(net, nid)]
    rungs.sort(key=lambda e: (dg.get(e, 0), e))

    rows: list[dict[str, Any]] = []
    for e in rungs:
        deps = _eq_deps(net, e)
        node = nodes[e]
        parent = node.get("parent")
        depends_on = max((dg.get(d, 0) for d in deps), default=0)
        embed_text = (str(ctx.get(e, "")) + " " + str(node.get("essence", ""))).strip()[:700]

        rows.append({
            "row_id": f"SC-{tag}-{e.replace('eq:', '').replace(':', '-')}",
            "embed_text": embed_text,
            "form": {
                "rung": dg.get(e, 0),
                "of_rungs": of_rungs,
                "ladder_move": _ladder_move(len(deps)),
                "depends_on_rung": depends_on,
                "claim_class": None,               # model residue
                "supports_class": None,            # model residue
            },
            "provenance": {
                "paper_id": paper_id,
                "source_kind": "tex",
                "extraction_lens": "spine_chain",
                "span_ref": {
                    "node_ids": [e, *deps],
                    "section_node": parent,
                    "source": "conceptric-derivation-dag",
                },
            },
        })
    return rows


# --------------------------------------------------------------------------- #
# LENS 3 — derivation-walk (design §2.4)
# --------------------------------------------------------------------------- #
def derive_derivation_walk(net: dict[str, Any], paper_id: str) -> list[dict[str, Any]]:
    """Derive the ``derivation_walk`` store rows as a VIEW of ``net`` (design §2.4): step
    granularity, where he elides. One row per STEP on the paper's eq-dependency walk — every
    equation node that either stands on a rung (has an ``\\eqref`` equation dependency) OR is
    itself a prerequisite of another equation. An equation referenced by nothing and depending
    on nothing is an isolated display, not a step on any walk — it is excluded. The row IS a
    path through the derivation DAG (design §1c: "a derivation-walk row IS a path through
    dependency edges").

    The MECHANICAL fields (from the dep graph — the WALK):
      * ``step_kind``   — a COARSE arity PROXY (``define``/``advance``/``combine``); the faithful
                          step-class is model residue (:data:`RESIDUE_FIELDS`). This is the store's
                          gate class.
      * ``position``    — this step's "N-of-M" place in the walk (dep-grade then id order).
      * ``rung`` / ``of_rungs`` — this step's dep-grade and the ladder top (the max eq grade).
      * ``rung_span``   — ``[depends_on_rung, rung]``: what the step connects, ladder-wise (the
                          grade of its deepest prerequisite up to its own grade).
      * ``prereq_kind`` — mechanical: does the deepest prerequisite itself stand on a rung
                          (``prior-step``), is it a floor/base equation (``base-equation``), or is
                          this a base step with no prerequisite (``none``)?
      * ``n_prereqs`` / ``carries_eq`` — arity and whether the node carries display LaTeX.
    The MODEL-RESIDUE fields (emitted ``None`` — a view has no mechanical basis): ``granularity``,
    ``elision``; and ``eq_env`` (the display-environment name the atomiser drops).

    ``embed_text`` is the step's REAL derivation lead-in prose (``net["ctx"]``) + its display LaTeX
    (the node ``essence``) — node-derived, the same basis the spine lens uses. ``span_ref`` names the
    equation node + its prerequisite node ids + the parent section (the view law). The ``sem::`` /
    ``confirmed::`` audit markers are never surfaced (``_eq_deps`` filters ``::``).

    Deterministic: steps are emitted sorted by (grade, id); no wall-clock, no randomness.
    """
    from laplace.research.corpus_ingest import dep_grade

    nodes = net["nodes"]
    ctx = net.get("ctx", {})
    postulates = net.get("postulates", set())
    tag = _pid_tag(paper_id)

    dg = dep_grade(net)
    eqs = [nid for nid, n in nodes.items() if n.get("kind") == "equation"]
    of_rungs = max((dg.get(e, 0) for e in eqs), default=0)
    deps_of = {e: _eq_deps(net, e) for e in eqs}
    is_prereq: set[str] = set()
    for e in eqs:
        is_prereq.update(deps_of[e])

    walk = [e for e in eqs if deps_of[e] or e in is_prereq]
    walk.sort(key=lambda e: (dg.get(e, 0), e))

    rows: list[dict[str, Any]] = []
    for pos, e in enumerate(walk):
        node = nodes[e]
        deps = deps_of[e]
        rung = dg.get(e, 0)
        depends_on = max((dg.get(d, 0) for d in deps), default=0)
        is_post = e in postulates or bool(node.get("postulate"))
        if not deps:
            prereq_kind = "none"                       # a base step — the walk's floor
        else:
            deepest = max(deps, key=lambda d: (dg.get(d, 0), d))
            prereq_kind = "prior-step" if deps_of.get(deepest) else "base-equation"
        embed_text = (str(ctx.get(e, "")) + " " + str(node.get("essence", ""))).strip()[:700]

        rows.append({
            "row_id": f"DW-{tag}-{e.replace('eq:', '').replace(':', '-')}",
            "embed_text": embed_text,
            "form": {
                "step_kind": _step_kind(len(deps), is_post),   # mechanical arity proxy (gate class)
                "position": f"{pos + 1}-of-{len(walk)}",
                "rung": rung,
                "of_rungs": of_rungs,
                "rung_span": [depends_on, rung],               # what the step connects (ladder-wise)
                "prereq_kind": prereq_kind,
                "n_prereqs": len(deps),
                "carries_eq": bool(node.get("essence")),
                "granularity": None,                           # model residue
                "elision": None,                               # model residue
                "eq_env": None,                                # conceptric-absent (atomiser drops env)
            },
            "provenance": {
                "paper_id": paper_id,
                "source_kind": "tex",
                "extraction_lens": "derivation_walk",
                "span_ref": {
                    "node_ids": [e, *deps],
                    "section_node": node.get("parent"),
                    "source": "conceptric-derivation-dag",
                },
            },
        })
    return rows


# --------------------------------------------------------------------------- #
# LENS 4 — figure-caption (design §2.5)
# --------------------------------------------------------------------------- #
def derive_figure_caption(net: dict[str, Any], paper_id: str) -> list[dict[str, Any]]:
    """Derive the ``figure_caption`` store rows as a VIEW of ``net`` (design §2.5): figure
    rhetoric. One row per real figure node (the float nodes the atomiser mints from
    ``\\begin{figure}`` blocks).

    The MECHANICAL fields:
      * ``has_caption``   — whether the float carries a real caption (its ``essence`` is the caption
                            text, falling back to the bare ``\\label`` when a figure has none).
      * ``caption_size``  — a COARSE length class (``terse``/``standard``/``expansive``); the store's
                            gate class (the semantically-meaningful ``caption_move``/``figure_role``
                            are model residue, so this length proxy is the most class-shaped
                            MECHANICAL field the schema carries).
      * ``caption_len`` / ``caption_len_band`` — the raw length + its band (form, not content).
      * ``ref_density`` / ``referenced_by_sections`` — referenced-from-sections via the net's edges:
                            a section ``\\ref{fig:X}`` lands ``fig:X`` in that section's atomised
                            referents, so this is a mechanical count over ``edge_index``.
      * ``position``      — the figure's "N-of-M" place (parent-section reading order, then id).
    The MODEL-RESIDUE fields (emitted ``None``): ``caption_move``, ``figure_role``, ``panels``,
    ``panel_labels`` (the atomiser keeps only the float's first ``\\label`` — no subpanel structure).

    ``embed_text`` is the figure's REAL caption prose (the node ``essence``) — node-derived, the
    retrieval basis. ``span_ref`` names the figure node, its parent section, and the section node ids
    that reference it (the view law — every id is a real node).

    Deterministic: figures are emitted in parent-section reading order then id; no randomness.
    """
    nodes = net["nodes"]
    ei = net.get("edge_index", {})
    meta_map = net.get("section_meta", {})
    source_file = net.get("source_file")
    tag = _pid_tag(paper_id)

    sec_ids = [nid for nid, n in nodes.items() if n.get("kind") == "section"]
    sec_order = {s: i for i, s in enumerate(
        sorted(sec_ids, key=lambda s: (meta_map.get(s, {}).get("idx", 10_000), s)))}

    fig_ids = [nid for nid, n in nodes.items() if n.get("kind") == "figure"]
    fig_ids.sort(key=lambda f: (sec_order.get(nodes[f].get("parent"), 10_000), f))
    n_fig = len(fig_ids)

    rows: list[dict[str, Any]] = []
    for pos, fid in enumerate(fig_ids):
        node = nodes[fid]
        parent = node.get("parent")
        caption = node.get("essence", "") or ""
        has_caption = bool(caption.strip()) and caption.strip() != fid   # essence falls back to label
        cap_len = len(caption)

        # referenced-from-sections via the net's edges (the atomiser lands \ref{fig:X} in the
        # referencing section's edge_index row). Sorted for determinism.
        ref_secs = sorted(s for s in sec_ids if fid in ei.get(s, []))

        span_ref: dict[str, Any] = {
            "node_ids": [fid],
            "section_node": parent,
            "referenced_by": ref_secs,
        }
        if source_file:
            span_ref["file"] = source_file

        rows.append({
            "row_id": f"FC-{tag}-{fid.replace('fig:', '').replace(':', '-')}",
            "embed_text": caption or fid,
            "form": {
                "caption_move": None,                          # model residue (caption rhetoric)
                "figure_role": None,                           # model residue
                "panels": None,                                # conceptric-absent (single label kept)
                "panel_labels": None,                          # conceptric-absent / model read
                "has_caption": has_caption,
                "caption_size": _caption_size(cap_len),        # mechanical class (gate class)
                "caption_len": cap_len,                        # mechanical, audit handle
                "caption_len_band": _caption_band(cap_len),
                "ref_density": f"referenced-by-{len(ref_secs)}-sections",
                "referenced_by_sections": len(ref_secs),
                "position": f"{pos + 1}-of-{n_fig}",
            },
            "provenance": {
                "paper_id": paper_id,
                "source_kind": "tex",
                "extraction_lens": "figure_caption",
                "span_ref": span_ref,
            },
        })
    return rows


# --------------------------------------------------------------------------- #
# the namespaced writer + orchestrator-only merge (design §3)
# --------------------------------------------------------------------------- #
def _validate_namespacing(paper_id: str, rows: list[dict[str, Any]]) -> None:
    """Enforce the isolation law BY CONSTRUCTION: every row this call writes must belong to
    ``paper_id``. A row whose ``provenance.paper_id`` differs is a cross-paper contamination
    attempt — refused, never written (design §3: isolation is mechanical, not trusted)."""
    for r in rows:
        rp = (r.get("provenance") or {}).get("paper_id")
        if rp != paper_id:
            raise ValueError(
                f"stage_store.write_store: row {r.get('row_id')!r} carries "
                f"provenance.paper_id={rp!r} but this write is namespaced to {paper_id!r}; "
                "a writer writes ONLY its own paper's rows (design §3)")


def _index_row(r: dict[str, Any]) -> dict[str, Any]:
    """A row's metadata for the merged ``_index.json`` — everything EXCEPT ``embed_text``
    (the design's index carries no his-prose; it is the object retrieval loads once)."""
    return {"row_id": r["row_id"], "form": r["form"], "provenance": r["provenance"]}


def write_store(store_name: str, paper_id: str, rows: list[dict[str, Any]],
                *, stores_root: Path | str | None = None) -> Path:
    """Write ONE paper's rows to its namespaced JSONL and merge the store-wide ``_index.json``.

    The namespacing is the API shape (design §3): this call names exactly ONE output path —
    ``<stores_root>/<store_name>/<paper_id>.jsonl`` — and can touch no other paper's file.
    Every row is validated to belong to ``paper_id`` first (:func:`_validate_namespacing`);
    a foreign row raises rather than writes. The merge into ``_index.json`` is the separate
    orchestrator-only fan-in (row metadata across all papers, no ``embed_text``), rebuilt
    from every ``*.jsonl`` present so a re-write of one paper never drops another's rows.

    Returns the JSONL path written.
    """
    root = Path(stores_root) if stores_root is not None else CORPUS_STORES
    _validate_namespacing(paper_id, rows)

    store_dir = root / store_name
    store_dir.mkdir(parents=True, exist_ok=True)
    jsonl = store_dir / f"{paper_id}.jsonl"
    jsonl.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8",
    )

    # merge _index.json: read every per-paper jsonl (this write included) into one index.
    papers: dict[str, dict[str, Any]] = {}
    index_rows: list[dict[str, Any]] = []
    for jf in sorted(store_dir.glob("*.jsonl")):
        pid = jf.stem
        prows = [json.loads(ln) for ln in jf.read_text(encoding="utf-8").splitlines() if ln.strip()]
        papers[pid] = {"paper_id": pid, "rows": len(prows), "path": jf.name}
        index_rows.extend(_index_row(r) for r in prows)
    index = {
        "schema": "stage-store/0.1",
        "store": store_name,
        "papers": sorted(papers.values(), key=lambda p: p["paper_id"]),
        "row_count": len(index_rows),
        "rows": index_rows,
    }
    (store_dir / "_index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return jsonl


# --------------------------------------------------------------------------- #
# STAGE ZERO — the ancestor inventory's import leg (design §1b step 2)
# --------------------------------------------------------------------------- #
#: The provenance marker prefix for a row salvaged from an ancestor store rather than read by a
#: fresh lens. It carries the ``::`` of the ``sem::``/``confirmed::`` audit discipline so an
#: inherited row is FOREVER distinguishable from a fresh lens read — a merged ``_index.json`` is
#: filterable on ``provenance.extraction_lens.startswith("inherited::")`` (design §1b: "the sem::
#: discipline applied to inheritance, so a salvaged row is forever distinguishable").
INHERITED_PREFIX = "inherited::"


def inherited_lens(source_store: str) -> str:
    """The ``extraction_lens`` value stamped on rows imported from ``source_store`` — e.g.
    ``inherited::voice_corpus``. The one place the marker string is formed, so the reader and
    the writer can never drift (:data:`INHERITED_PREFIX`)."""
    return f"{INHERITED_PREFIX}{source_store}"


def is_inherited(row: dict[str, Any]) -> bool:
    """True iff ``row`` was imported from an ancestor store (its ``extraction_lens`` carries the
    :data:`INHERITED_PREFIX`), never produced by a fresh lens read."""
    lens = (row.get("provenance") or {}).get("extraction_lens", "")
    return isinstance(lens, str) and lens.startswith(INHERITED_PREFIX)


def import_inherited(store_name: str, paper_id: str, rows: list[dict[str, Any]],
                     source_store: str, *, stores_root: Path | str | None = None) -> Path:
    """STAGE ZERO's import leg (design §1b step 2): salvage FORM-relevant ancestor-store rows
    into a stage store as INHERITED rows, so a fresh lens never re-authors what a deprecated
    store already decomposed. Every imported row is stamped
    ``provenance.extraction_lens = inherited::<source_store>`` (:func:`inherited_lens`) — the
    sem:: discipline applied to inheritance: a salvaged row is FOREVER distinguishable from a
    fresh lens read (an ``inherited::voice_corpus`` row is never a ``paragraph_plan`` row), and
    every import is traceable to its ancestor via ``provenance.inherited_from``.

    The namespacing holds by construction. The import delegates to :func:`write_store`, so the
    per-paper isolation law is not re-implemented and not weakened: an import CANNOT cross paper
    namespaces. A row that already carries a ``provenance.paper_id`` different from ``paper_id``
    is REFUSED (``write_store`` raises), never written; a row with no ``paper_id`` is stamped to
    the write's namespace. Cross-paper contamination stays a filesystem impossibility (design §3).

    Returns the JSONL path written. Does not mutate the caller's row objects (each row +
    provenance is shallow-copied before the marker is stamped).
    """
    marker = inherited_lens(source_store)
    stamped: list[dict[str, Any]] = []
    for r in rows:
        row = dict(r)
        prov = dict(row.get("provenance") or {})
        prov["extraction_lens"] = marker                 # ALWAYS the inherited marker (override)
        prov["inherited_from"] = source_store            # the ancestor, for the audit trail
        prov.setdefault("paper_id", paper_id)            # stamp namespace when absent; a differing
        row["provenance"] = prov                         # one is refused by write_store below
        stamped.append(row)
    return write_store(store_name, paper_id, stamped, stores_root=stores_root)
