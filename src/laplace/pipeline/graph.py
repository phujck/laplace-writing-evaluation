"""The canon as one typed graph, projected into many renders.

The Laplace canon is already a graph: wiki nodes, skills, and domains, wired by
``[[name]]`` wikilinks and ``canon://`` references in the prose, plus the
structural belongs-to relations between a domain and its axioms, projects, and
skills. This module makes that latent graph explicit as a single ``CanonGraph``
object, then projects it into whatever surface the moment needs - Mermaid for a
note or a PDF, an Obsidian Canvas for the vault, a graph-config for Obsidian's
native view, or a plain JSON edge list for any interactive viewer.

The design follows the canon's own discipline: synthesise, do not partition.
AutoSci (the repo this was scouted from) keeps three separate graphs - a wiki
graph, a manuscript DAG, and a claim-dependency graph. Here there is one node
and edge model. A manuscript-structure graph is the same object built from a
different source, so every renderer below serves it for free once it lands.

Two things this does that a static export does not:

* **Provenance on every edge.** Each link carries the line of prose it was
  found in (``evidence``) and the file it came from (``source``). A link is
  never asserted without the text that justifies it.
* **Fitness-weighted nodes.** A skill node's weight is its measured fitness
  from the telemetry ledger, not a hand-set importance. The rendered graph is a
  self-portrait of the engine: load-bearing skills render large and bright, dead
  wood renders faint. Health is a property of the topology - orphans, dangling
  links, and deprecated-but-still-linked skills are first-class findings.
"""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Iterable

from laplace.pipeline.canon import Canon, _split_frontmatter, get_canon

# ---------------------------------------------------------------------------
# Extraction patterns
# ---------------------------------------------------------------------------

_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
_CANON_RE = re.compile(r"canon://([A-Za-z0-9_./-]+)")

# Group palettes. Hex for Mermaid/JSON; Obsidian's graph + canvas use a built-in
# palette indexed "1".."6", so each group also carries a canvas colour id.
_WIKI_SECTION_HEX = {
    "aesthetics": "#EC4899",
    "operations": "#4A90D9",
    "structure": "#84CC16",
    "workflow": "#F39C12",
    "templates": "#95A5A6",
    "author": "#2ECC71",
    "voice_corpus": "#1ABC9C",
    "domains": "#E67E22",
}
_ACTIVITY_HEX = {
    "generating": "#F39C12",
    "staging": "#4A90D9",
    "evaluating": "#9B5DE5",
}
_DOMAIN_HEX = "#E74C3C"
_AGENT_HEX = "#F1C40F"
_MISSING_HEX = "#C0392B"

# Manuscript-projection groups (the same graph, a different source). A section
# is coloured by its core-outward ring when the title exposes one, else a
# neutral section hue. Claims and citations are the interlock layer above the
# structure - what the prose asserts, and what it leans on.
_MANUSCRIPT_HEX = {
    "section": "#4A90D9",
    "figure": "#16A085",
    "equation": "#9B5DE5",
    "claim": "#D35400",
    "citation": "#7F8C8D",
    "ring_core": "#E74C3C",
    "ring_inner": "#F39C12",
    "ring_outer": "#4A90D9",
}

# Obsidian/Canvas palette ids (built-in: 1 red, 2 orange, 3 yellow, 4 green,
# 5 cyan, 6 purple). One per group, chosen for mutual contrast.
_GROUP_CANVAS_COLOR = {
    "aesthetics": "6",
    "operations": "5",
    "structure": "4",
    "workflow": "3",
    "templates": "2",
    "author": "4",
    "voice_corpus": "5",
    "domains": "2",
    "generating": "3",
    "staging": "5",
    "evaluating": "6",
    "domain": "1",
    "missing": "1",
    "section": "5",
    "figure": "4",
    "equation": "6",
    "claim": "2",
    "citation": "5",
    "ring_core": "1",
    "ring_inner": "3",
    "ring_outer": "5",
    "agent": "3",
}

# Section-title heuristics for the core-outward ring (canon://workflow/core_outward_trunk).
_RING_CORE = re.compile(r"\b(result|theorem|main|core|derivation)\b", re.I)
_RING_OUTER = re.compile(
    r"\b(intro|introduction|related|background|discussion|conclusion|appendix)\b", re.I
)

# Manuscript-structure extraction. The interlock layer above sections/equations:
# claims (theorem-like environments), the citations the prose leans on, and the
# figure forms a section can hold - a full figure env, a bare TikZ picture, or a
# loose \includegraphics. \input/\include drive the true reading order.
_CLAIM_ENVS = (
    "theorem", "lemma", "proposition", "corollary", "claim",
    "conjecture", "definition", "assumption", "result", "remark",
)
_CLAIM_RE = re.compile(
    r"\\begin\{(" + "|".join(_CLAIM_ENVS) + r")\}(?:\[[^\]]*\])?(.*?)\\end\{\1\}",
    re.DOTALL,
)
_CITE_RE = re.compile(
    r"\\(?:cite|citep|citet|citealp|citeauthor|citeyear|autocite|textcite|parencite)"
    r"\*?(?:\[[^\]]*\])*\{([^}]+)\}"
)
_TIKZ_RE = re.compile(r"\\begin\{tikzpicture\}.*?\\end\{tikzpicture\}", re.DOTALL)
_INCLUDEGRAPHICS_RE = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}")
_INPUT_RE = re.compile(r"\\(?:input|include|subfile)\{([^}]+)\}")
_LABEL_RE = re.compile(r"\\label\{([^}]+)\}")
# Display-math environments, so an equation node can carry its actual LaTeX body
# (for a faithful KaTeX render) rather than only its label. Starred variants too.
_MATH_ENVS = ("equation", "align", "gather", "multline", "eqnarray", "displaymath", "flalign")
_MATH_ENV_RE = re.compile(
    r"\\begin\{(" + "|".join(_MATH_ENVS) + r")\*?\}(.*?)\\end\{\1\*?\}", re.DOTALL
)
_REF_RE = re.compile(r"\\(?:ref|eqref|autoref|cref|Cref|pageref)\{([^}]+)\}")

# Semantic label prefixes. A manuscript may number a display equation with an
# epistemic role rather than a bare ``eq:`` - the SSG whitepaper numbers all ~90
# of its equations def:/res:/irf:/thm: and uses zero ``eq:`` / ``\newtheorem``.
# A numbered environment so labelled is captured as BOTH an equation node (it
# carries a LaTeX body) AND a claim node (the prefix names the assertion the
# equation embodies), additively alongside the ``eq:`` path. This is prefix-set-
# driven, so any manuscript using these conventions works, and the label is read
# byte-for-byte: the semantic prefix IS the node identifier, never rewritten or
# spell-fixed. ``EQ_LABEL_PREFIXES`` is the full set that makes an equation node;
# ``CLAIM_LABEL_PREFIXES`` the subset that additionally makes a claim node.
CLAIM_LABEL_PREFIXES = ("def:", "res:", "irf:", "thm:")
# ``ds:`` is a displayed data/model statement: it is a numbered equation node,
# but not automatically an epistemic claim node.
EQ_LABEL_PREFIXES = ("eq:", "ds:") + CLAIM_LABEL_PREFIXES

# Code spans: a documented ``[[name]]`` / ``canon://`` example shown as syntax is
# not a real cross-link. Mask both before extracting edges (the canon's own rule -
# canon_weaver: a link in a code fence does not count).
_CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")


def _mask_code_spans(text: str) -> str:
    """Blank fenced and inline code, length-preserving (code -> spaces, newlines
    kept). Edge extraction scans the masked copy so a DOCUMENTED ``[[name]]`` or
    ``canon://`` example - syntax shown in a code span, not a real cross-link - is
    never harvested as a dangling edge. Positions are preserved, so a surviving
    match still indexes the original body for its evidence line."""

    def _blank(m: "re.Match[str]") -> str:
        return re.sub(r"[^\n]", " ", m.group(0))

    text = _CODE_FENCE_RE.sub(_blank, text)
    text = _INLINE_CODE_RE.sub(_blank, text)
    return text


def _group_hex(group: str) -> str:
    if group in _WIKI_SECTION_HEX:
        return _WIKI_SECTION_HEX[group]
    if group in _ACTIVITY_HEX:
        return _ACTIVITY_HEX[group]
    if group in _MANUSCRIPT_HEX:
        return _MANUSCRIPT_HEX[group]
    if group == "domain":
        return _DOMAIN_HEX
    if group == "agent":
        return _AGENT_HEX
    if group == "missing":
        return _MISSING_HEX
    return "#7F8C8D"


# ---------------------------------------------------------------------------
# Data model - one node, one edge, for every projection
# ---------------------------------------------------------------------------


@dataclass
class Node:
    id: str  # stable: "wiki:<ref>" | "skill:<name>" | "domain:<name>" | "missing:<token>"
    kind: str  # wiki | skill | domain | missing
    label: str
    group: str  # colour bucket: wiki section | skill activity | "domain" | "missing"
    status: str | None = None  # skill lifecycle: core | experimental | deprecated
    weight: float = 0.5  # 0..1; skill fitness, else a neutral prior
    source: str = ""  # provenance: a node id (generated_by) or an outside door (author|literature|model)
    link: str = "linked"  # learning state: loose (arrived, unwired) | linked | closed
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class Edge:
    src: str
    dst: str
    rel: str  # links_to | belongs_to_domain | has_axioms | has_project | dangling
    evidence: str = ""  # the line of prose the link was found in
    source: str = ""  # the file the edge was extracted from
    count: int = 1  # collapsed parallel links


@dataclass
class CanonGraph:
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)

    # -- construction -------------------------------------------------------
    @classmethod
    def from_canon(
        cls, canon: Canon | None = None, with_fitness: bool = True
    ) -> CanonGraph:
        """Extract the typed graph latent in the canon.

        Nodes are every wiki page, skill, and domain. Edges are the structural
        belongs-to relations plus every ``[[name]]`` and ``canon://`` link found
        in the prose, each carrying the line it came from. Unresolved links
        become ``dangling`` edges into a synthetic ``missing:`` node, so a broken
        cross-reference is visible rather than silently dropped.

        A node's frontmatter may also carry a ``consistency: <ref> | <rel> |
        <note>`` annotation (one entry or a list), projected here into a typed
        ``supports``/``contradicts`` edge - the canon-prose peer of the substrate
        seed, so the canon's own prose can declare an axiom-level conflict.
        """
        canon = canon or get_canon()
        g = cls()

        # Nodes: domains, wiki pages, skills. Each carries provenance - the canon
        # was grown ad-hoc across prior sessions, so an un-attributed node is
        # "ancestor" (see laplace.pipeline.canon.ANCESTOR), and a node the engine generated
        # carries its recorded door instead.
        for dname, dmeta in canon.domains().items():
            g.nodes[f"domain:{dname}"] = Node(
                id=f"domain:{dname}",
                kind="domain",
                label=dname,
                group="domain",
                source=str((dmeta or {}).get("source") or "") or "ancestor",
                meta={"tags": (dmeta or {}).get("tags", [])},
            )
        for ref, n in canon.wiki.items():
            # ``parent`` is the coarse node this one nests beneath (canon.py's
            # hierarchicalisation - a directory's ``index`` stands in for its
            # subgraph). Carrying it into the node, plus a ``contains`` edge
            # below, makes the canon navigable scale-local in the viewer exactly
            # as the substrate is: a coarse node opens to reveal its interior.
            g.nodes[f"wiki:{ref}"] = Node(
                id=f"wiki:{ref}",
                kind="wiki",
                label=n.title,
                group=_wiki_group(ref),
                source=n.source,
                link=n.link,
                meta={
                    "ref": f"canon://{ref}", "scope": n.scope, "domain": n.domain,
                    "tags": n.tags,
                    "parent": f"wiki:{n.parent}" if n.parent else None,
                    "coarse": canon.is_coarse(ref),
                    "earned_by": n.earned_by,
                },
            )

        fitness = _fitness_map(canon) if with_fitness else {}
        for name, sk in canon.skills.items():
            g.nodes[f"skill:{name}"] = Node(
                id=f"skill:{name}",
                kind="skill",
                label=name,
                group=sk.activity if sk.activity in _ACTIVITY_HEX else "staging",
                status=sk.status,
                weight=float(fitness.get(name, 0.5)),
                source=sk.source,
                link=sk.link,
                meta={
                    "domain": sk.domain,
                    "backing": sk.backing,
                    "tags": sk.tags,
                    "fitness": fitness.get(name),
                    "earned_by": sk.earned_by,
                },
            )

        # Agent personas (canon/agents/*.yaml). The canon prose links to these
        # via canon://agents/<name>.yaml, so they are real nodes, not dangling
        # targets. They are the dream-loop's actors - the dreamer and the
        # empiricist - so the graph shows who acts on the canon, not just what.
        agents_dir = canon.root / "agents"
        if agents_dir.is_dir():
            for ay in sorted(agents_dir.glob("*.yaml")):
                aname = ay.stem
                role = _agent_role(ay)
                g.nodes[f"agent:{aname}"] = Node(
                    id=f"agent:{aname}", kind="agent", label=aname, group="agent",
                    source="ancestor",
                    meta={"role": role, "ref": f"canon://agents/{aname}.yaml"},
                )

        # Resolution index for [[name]] and canon:// targets.
        resolver = g._build_resolver(canon)

        # Structural edges: domain -> axioms / projects, skill -> its domain.
        for dname, dmeta in canon.domains().items():
            dmeta = dmeta or {}
            ax = dmeta.get("axioms")
            if ax and f"wiki:{ax}" in g.nodes:
                g.edges.append(Edge(f"domain:{dname}", f"wiki:{ax}", "has_axioms", source="index.yaml"))
            for pref in (dmeta.get("projects") or {}).values():
                if f"wiki:{pref}" in g.nodes:
                    g.edges.append(Edge(f"domain:{dname}", f"wiki:{pref}", "has_project", source="index.yaml"))
        for name, sk in canon.skills.items():
            if sk.domain and sk.domain != "global" and f"domain:{sk.domain}" in g.nodes:
                g.edges.append(Edge(f"skill:{name}", f"domain:{sk.domain}", "belongs_to_domain", source="index.yaml"))

        # Containment edges: the coarse-graining hierarchy, so the viewer can
        # descend a coarse node into its interior (the scale-local read). A wiki
        # node ``contains`` the wiki nodes that nest beneath it (by ``parent``);
        # a domain ``contains`` its axioms, projects, and skills. This is the
        # same ``contains`` relation the substrate and manuscript projections
        # already emit - one model, every renderer serves it unchanged.
        for ref, n in canon.wiki.items():
            if n.parent and f"wiki:{n.parent}" in g.nodes:
                g.edges.append(Edge(f"wiki:{n.parent}", f"wiki:{ref}", "contains", source="hierarchy"))
        for dname, dmeta in canon.domains().items():
            dmeta = dmeta or {}
            ax = dmeta.get("axioms")
            if ax and f"wiki:{ax}" in g.nodes:
                g.edges.append(Edge(f"domain:{dname}", f"wiki:{ax}", "contains", source="hierarchy"))
            for pref in (dmeta.get("projects") or {}).values():
                if f"wiki:{pref}" in g.nodes:
                    g.edges.append(Edge(f"domain:{dname}", f"wiki:{pref}", "contains", source="hierarchy"))
        for name, sk in canon.skills.items():
            if sk.domain and sk.domain != "global" and f"domain:{sk.domain}" in g.nodes:
                g.edges.append(Edge(f"domain:{sk.domain}", f"skill:{name}", "contains", source="hierarchy"))

        # Prose edges: every [[name]] and canon:// link, with provenance.
        for ref, n in canon.wiki.items():
            g._extract_prose_edges(f"wiki:{ref}", n.path, resolver, canon)
        for name, sk in canon.skills.items():
            if sk.skill_md.exists():
                g._extract_prose_edges(f"skill:{name}", sk.skill_md, resolver, canon)
        # Agent personas carry deliberate canon:// refs to the skills they wield
        # (the_empiricist -> empirical_ledger). Scan them too, so a dream-loop
        # actor is wired to what it acts on rather than orphaned beside it. Their
        # refs are intentional (often backticked), so they opt out of masking.
        if agents_dir.is_dir():
            for ay in sorted(agents_dir.glob("*.yaml")):
                g._extract_prose_edges(f"agent:{ay.stem}", ay, resolver, canon, mask_code=False)

        # Typed consistency edges from a node's own frontmatter annotation - the
        # canon-prose peer of the substrate's ``consistency:`` seed. A wiki page
        # or skill may declare a ``supports`` or ``contradicts`` relation to
        # another canon node; ``contradicts`` is the highest-signal edge the
        # health guard surfaces, so the canon's own prose can now declare an
        # axiom-level conflict, not only the substrate/manuscript projections.
        for ref, n in canon.wiki.items():
            for cref, rel, note in n.consistency:
                g._add_consistency_edge(f"wiki:{ref}", cref, rel, note, resolver)
        for name, sk in canon.skills.items():
            for cref, rel, note in sk.consistency:
                g._add_consistency_edge(f"skill:{name}", cref, rel, note, resolver)

        g._collapse_parallel_edges()
        return g

    @classmethod
    def from_manuscript(cls, target) -> CanonGraph:
        """Build the SAME graph object from a LaTeX manuscript's structure.

        This is the synthesis the canon asks for: a manuscript is not a separate
        kind of graph, it is the same node/edge model sourced from ``.tex``
        instead of canon prose. Five node kinds make the interlock visible
        before the prose is read in order:

        * **sections** - in true reading order. A single root file is flattened
          along its ``\\input``/``\\include`` tree, so the section->section
          ``precedes`` chain follows how the paper is read, not how its files
          sort. A directory of loose section files falls back to sorted-glob
          merge (the crossref ledger's order).
        * **figures** - a full ``figure`` env, a bare ``tikzpicture``, or a
          loose ``\\includegraphics``. A section ``contains`` the figures in its
          span.
        * **equations** - every ``eq:`` label, contained by its section.
        * **claims** - theorem-like environments (result, proposition, lemma,
          ...). A claim is ``contains``ed by its section and ``supported_by`` the
          equations it states or invokes - the 'derive, do not assert' backbone
          the epistemic_ledger checks, here made navigable.
        * **citations** - every ``\\cite`` key. The section, and the claim if the
          cite sits inside one, ``cites`` it.

        A reference (``\\ref``/``\\eqref``) becomes an edge to the thing
        referenced, and a reference to a label never defined becomes a dangling
        edge, exactly as a broken wikilink does. Every renderer then serves this
        graph unchanged.

        ``target`` is a root ``.tex`` file (preferred - its ``\\input`` order is
        authoritative) or a directory of ``.tex`` files.
        """
        full = _gather_manuscript_text(target)

        g = cls()
        label_owner: dict[str, str] = {}

        # Sections -> nodes, with character spans so children can be attributed.
        spans: list[tuple[int, int, str]] = []
        sec_marks = [
            (m.start(), m.group(2))
            for m in re.finditer(r"\\(sub)?section\*?\{([^}]+)\}", full)
        ]
        for i, (start, name) in enumerate(sec_marks):
            end = sec_marks[i + 1][0] if i + 1 < len(sec_marks) else len(full)
            sid = f"sec:{_slug(name)}"
            if sid in g.nodes:
                sid = f"{sid}_{i}"  # disambiguate repeated titles
            g.nodes[sid] = Node(
                id=sid, kind="section", label=name, group=_ring_group(name),
                meta={"order": i, "ring": _ring_group(name)},
            )
            spans.append((start, end, sid))
            if i > 0:
                g.edges.append(Edge(spans[i - 1][2], sid, "precedes", source="structure"))
            # A section's own \label(s) sit before its first environment - a
            # section may carry several as aliases. Register each so a
            # \ref{sec:...} elsewhere resolves to this section (the
            # section->section interlock) rather than dangling.
            seg = full[start:end]
            cutoff = seg.find(r"\begin{")
            for lab_m in _LABEL_RE.finditer(seg):
                if cutoff != -1 and lab_m.start() >= cutoff:
                    break
                label_owner.setdefault(lab_m.group(1), sid)

        def _owner(pos: int) -> str | None:
            for s, e, sid in spans:
                if s <= pos < e:
                    return sid
            return None

        fig_spans: list[tuple[int, int]] = []

        def _add_figure(fid: str, label: str, owner_pos: int, meta: dict[str, Any]) -> None:
            g.nodes.setdefault(fid, Node(id=fid, kind="figure", label=label, group="figure", meta=meta))
            owner = _owner(owner_pos)
            if owner:
                g.edges.append(Edge(owner, fid, "contains", source="structure"))

        # Float envs (figure, table) -> figure nodes; a float belongs to the
        # section it sits in. A table is a labelled, captioned float that the
        # prose \refs exactly as a figure, so it interlocks the same way.
        for m in re.finditer(r"\\begin\{(figure|table)\*?\}(.*?)\\end\{\1\*?\}", full, re.DOTALL):
            env, body = m.group(1), m.group(2)
            fig_spans.append((m.start(), m.end()))
            lab = _LABEL_RE.search(body)
            cap = re.search(r"\\caption\{((?:[^{}]|\{[^{}]*\})*)\}", body, re.DOTALL)
            key = lab.group(1) if lab else f"{env}_{m.start()}"
            fid = f"fig:{_slug(key)}"
            # The image the float draws, if any - so the node carries its asset
            # path (a viewer renders the real figure, not just the caption). The
            # first \includegraphics in the body is the figure's graphic.
            inc = _INCLUDEGRAPHICS_RE.search(body)
            meta = {"label": key, "float": env}
            if inc:
                meta["file"] = inc.group(1).strip()
            _add_figure(fid, cap.group(1).strip()[:48] if cap else key, m.start(), meta)
            if lab:
                label_owner[lab.group(1)] = fid

        def _in_figure(pos: int) -> bool:
            return any(s <= pos < e for s, e in fig_spans)

        # A bare TikZ picture or a loose \includegraphics outside any figure env
        # is a figure in its own right - a schematic dropped straight into the
        # prose still interlocks with the section that holds it.
        for m in _TIKZ_RE.finditer(full):
            if _in_figure(m.start()):
                continue
            lab = _LABEL_RE.search(m.group(0))
            key = lab.group(1) if lab else f"tikz_{m.start()}"
            fid = f"fig:{_slug(key)}"
            _add_figure(fid, key, m.start(), {"label": key, "tikz": True})
            if lab:
                label_owner[lab.group(1)] = fid
        for m in _INCLUDEGRAPHICS_RE.finditer(full):
            if _in_figure(m.start()):
                continue
            fname = m.group(1).strip()
            _add_figure(f"fig:{_slug(fname)}", fname, m.start(), {"file": fname})

        # Equations -> nodes, contained by their section. A labelled display-math
        # environment carries its LaTeX body in ``meta.latex`` so a viewer renders
        # the actual mathematics (KaTeX), not just the label. The ``eq:`` prefix is
        # the base case; a manuscript may instead number a display equation with a
        # SEMANTIC epistemic prefix (SSG numbers all ~90 equations def:/res:/irf:/
        # thm: and uses zero ``eq:``), in which case the equation is BOTH an
        # equation node and a claim node - see ``_add_semantic_claim``. Every
        # eq/claim node also carries a ``reading_order`` (its source position in
        # \input order) so a later phase can catch a reference that precedes the
        # thing it introduces. Captured per environment first; a bare
        # ``\label{eq:...}`` outside a known env still makes a node (label only)
        # via the fallback pass below.
        labelled_in_env: set[str] = set()
        # Claim spans - theorem-like envs AND semantic-prefixed numbered equations
        # - so the citation pass below can attribute a \cite to the enclosing claim.
        claim_spans: list[tuple[int, int, str]] = []

        def _add_semantic_claim(lab: str, body: str, start: int, end: int, eqid: str) -> None:
            """A numbered equation whose label carries an epistemic prefix
            (def:/res:/irf:/thm:) is also a claim: the prefix names the assertion
            the equation embodies. Mirror the theorem-env claim - contained by its
            section, supported_by its own equation (and any it \\eqrefs) - so a
            manuscript that numbers claims-as-equations gets the apparatus for free.
            The claim shares the equation's reading order and keeps the raw label."""
            cid = f"claim:{_slug(lab)}"
            if cid in g.nodes:
                cid = f"{cid}_{start}"
            g.nodes[cid] = Node(
                id=cid, kind="claim", label=lab, group="claim",
                meta={"env": "equation", "label": lab, "role": lab.split(":", 1)[0],
                      "reading_order": start},
            )
            claim_spans.append((start, end, cid))
            owner = _owner(start)
            if owner:
                g.edges.append(Edge(owner, cid, "contains", source="structure"))
            # claim -> evidence: its own equation body, plus any equation it \eqrefs.
            ev = _line_at(full, start)
            g.edges.append(Edge(cid, eqid, "supported_by", ev, "structure"))
            for el in {r for r in _REF_RE.findall(body) if r.startswith(EQ_LABEL_PREFIXES)}:
                dst = label_owner.get(el, f"eq:{_slug(el)}")
                if dst in g.nodes and dst != eqid:
                    g.edges.append(Edge(cid, dst, "supported_by", ev, "structure"))

        for m in _MATH_ENV_RE.finditer(full):
            body = m.group(2)
            lab_m = _LABEL_RE.search(body)
            if not (lab_m and lab_m.group(1).startswith(EQ_LABEL_PREFIXES)):
                continue
            lab = lab_m.group(1)
            labelled_in_env.add(lab)
            eid = f"eq:{_slug(lab)}"
            latex = _clean_math(body)
            if eid in g.nodes:
                g.nodes[eid].meta.setdefault("latex", latex)
            else:
                g.nodes[eid] = Node(id=eid, kind="equation", label=lab, group="equation",
                                    meta={"label": lab, "latex": latex, "reading_order": m.start()})
            g.nodes[eid].meta.setdefault("reading_order", m.start())
            label_owner[lab] = eid
            owner = _owner(m.start())
            if owner:
                g.edges.append(Edge(owner, eid, "contains", source="structure"))
            # A semantic prefix marks the equation as a claim as well.
            if lab.startswith(CLAIM_LABEL_PREFIXES):
                _add_semantic_claim(lab, body, m.start(), m.end(), eid)
        for m in re.finditer(r"\\label\{(eq:[^}]+)\}", full):
            lab = m.group(1)
            if lab in labelled_in_env:
                continue  # already captured with its LaTeX body
            eid = f"eq:{_slug(lab)}"
            g.nodes.setdefault(
                eid, Node(id=eid, kind="equation", label=lab, group="equation",
                          meta={"label": lab, "reading_order": m.start()})
            )
            g.nodes[eid].meta.setdefault("reading_order", m.start())
            label_owner[lab] = eid
            owner = _owner(m.start())
            if owner:
                g.edges.append(Edge(owner, eid, "contains", source="structure"))

        # Claims (theorem-like envs) -> nodes, contained by their section and
        # supported_by the equations they state or invoke. Cites inside a claim
        # are attributed to it in the citation pass below. (Semantic-prefixed
        # equations already registered their claim spans above.)
        for i, m in enumerate(_CLAIM_RE.finditer(full)):
            env, body = m.group(1), m.group(2)
            lab = _LABEL_RE.search(body)
            name = re.match(r"\\begin\{" + re.escape(env) + r"\}\[([^\]]*)\]", m.group(0))
            key = lab.group(1) if lab else (name.group(1) if name else f"{env}_{i}")
            cid = f"claim:{_slug(key)}"
            if cid in g.nodes:
                cid = f"{cid}_{i}"
            g.nodes[cid] = Node(
                id=cid, kind="claim", label=(name.group(1) if name else key),
                group="claim", meta={"env": env, "label": lab.group(1) if lab else None,
                                     "reading_order": m.start()},
            )
            claim_spans.append((m.start(), m.end(), cid))
            if lab:
                label_owner[lab.group(1)] = cid
            owner = _owner(m.start())
            if owner:
                g.edges.append(Edge(owner, cid, "contains", source="structure"))
            # claim -> evidence: every equation the claim states or references
            # (any recognised equation-label prefix, not only ``eq:``).
            ev = _line_at(full, m.start())
            eq_labels = {
                l for l in _LABEL_RE.findall(body) if l.startswith(EQ_LABEL_PREFIXES)
            } | {
                r for r in _REF_RE.findall(body) if r.startswith(EQ_LABEL_PREFIXES)
            }
            for el in eq_labels:
                dst = label_owner.get(el, f"eq:{_slug(el)}")
                if dst in g.nodes:
                    g.edges.append(Edge(cid, dst, "supported_by", ev, "structure"))

        def _claim_owner(pos: int) -> str | None:
            for s, e, cid in claim_spans:
                if s <= pos < e:
                    return cid
            return None

        # Citations -> nodes; the section (and the claim, if any) that invokes a
        # reference cites it. Multiple keys in one \cite are separate citations.
        for m in _CITE_RE.finditer(full):
            ev = _line_at(full, m.start())
            owner = _owner(m.start())
            claim = _claim_owner(m.start())
            for key in (k.strip() for k in m.group(1).split(",")):
                if not key:
                    continue
                cnode = f"cite:{key}"
                g.nodes.setdefault(
                    cnode, Node(id=cnode, kind="citation", label=key, group="citation", meta={"key": key})
                )
                if owner:
                    g.edges.append(Edge(owner, cnode, "cites", ev, "structure"))
                if claim:
                    g.edges.append(Edge(claim, cnode, "cites", ev, "structure"))

        # References -> edges from the citing section to the referenced object.
        for m in _REF_RE.finditer(full):
            lab = m.group(1)
            owner = _owner(m.start())
            if owner is None:
                continue
            dst = label_owner.get(lab)
            ev = _line_at(full, m.start())
            if dst is None:
                miss = f"missing:{lab}"
                g.nodes.setdefault(miss, Node(id=miss, kind="missing", label=lab, group="missing"))
                g.edges.append(Edge(owner, miss, "dangling", ev, "structure"))
            elif dst != owner:
                g.edges.append(Edge(owner, dst, "references", ev, "structure"))

        g._collapse_parallel_edges()
        return g

    @classmethod
    def from_blueprint(cls, target) -> CanonGraph:
        """Build the graph from a manuscript BLUEPRINT (``blueprint.md``).

        The same node/edge model as a compiled manuscript, but sourced from the
        *plan* that exists before any ``.tex``. This is what makes the paper
        navigable while it is still being elicited: sections in reading order,
        the claims each makes (carrying their result-ledger provenance and
        status), the equations and figures placed in them, and the citations
        they lean on. Every renderer that serves ``from_canon`` and
        ``from_manuscript`` serves this unchanged - one model, three sources.

        Node kinds match the manuscript projection (section / claim / equation /
        figure / citation) so the live preview is the same object the compiled
        paper will be, only earlier and editable.
        """
        from pathlib import Path

        spine, sections = _parse_blueprint(Path(target).read_text(encoding="utf-8"))
        g = cls()
        if spine:
            g.nodes["blueprint:spine"] = Node(
                id="blueprint:spine", kind="domain", label=spine.get("title", "Spine"),
                group="domain", meta=spine,
            )
        prev = None
        for order, sec in enumerate(sections):
            sid = f"sec:{_slug(sec['id'])}"
            if sid in g.nodes:
                sid = f"{sid}_{order}"
            g.nodes[sid] = Node(
                id=sid, kind="section", label=sec["title"],
                group=_blueprint_ring_group(sec.get("ring")), status=sec.get("status"),
                meta={"ring": sec.get("ring"), "status": sec.get("status"),
                      "intent": sec.get("intent", ""), "order": order},
            )
            if "blueprint:spine" in g.nodes and prev is None:
                g.edges.append(Edge("blueprint:spine", sid, "has_project", source="blueprint"))
            if prev:
                g.edges.append(Edge(prev, sid, "precedes", source="blueprint"))
            prev = sid
            for i, cl in enumerate(sec.get("claims", [])):
                cid = f"claim:{_slug(sec['id'])}_{i}"
                g.nodes[cid] = Node(
                    id=cid, kind="claim", label=(cl["text"][:60] or cid), group="claim",
                    status=cl.get("status"),
                    meta={"result": cl.get("result"), "status": cl.get("status"),
                          "headline": cl.get("headline", False), "text": cl["text"]},
                )
                g.edges.append(Edge(sid, cid, "contains", source="blueprint"))
                cl["_node"] = cid
            for eq in sec.get("equations", []):
                eid = f"eq:{_slug(eq['label'])}"
                g.nodes.setdefault(eid, Node(id=eid, kind="equation", label=eq["label"],
                                             group="equation", meta={"latex": eq.get("latex", "")}))
                g.edges.append(Edge(sid, eid, "contains", source="blueprint"))
                tc = _match_claim(sec.get("claims", []), eq.get("serves"))
                if tc and tc.get("_node"):
                    g.edges.append(Edge(tc["_node"], eid, "supported_by", source="blueprint"))
            for fg in sec.get("figures", []):
                fid = f"fig:{_slug(fg['label'])}"
                g.nodes.setdefault(fid, Node(id=fid, kind="figure", label=(fg.get("caption") or fg["label"]),
                                             group="figure", meta={"label": fg["label"]}))
                g.edges.append(Edge(sid, fid, "contains", source="blueprint"))
            for ct in sec.get("cites", []):
                cnode = f"cite:{ct['key']}"
                g.nodes.setdefault(cnode, Node(id=cnode, kind="citation", label=ct["key"],
                                               group="citation", meta={"relation": ct.get("relation", "context")}))
                g.edges.append(Edge(sid, cnode, "cites", source="blueprint"))
        g._collapse_parallel_edges()
        return g

    @classmethod
    def from_substrate(cls, target) -> "CanonGraph":
        """Build the graph from a SUBSTRATE seed - the atomic level, bottom-up.

        The recursive baseline: a handful of coarse nodes (the endogenous /
        exogenous / intrinsic split), each a collection of the microscopic
        objects that feed into it. A coarse node carries a ``summary`` (shown on
        click) and ``contains`` its atoms; the viewer zooms a coarse node open to
        reveal them. Atoms are leaves now and gain their own sub-graphs later -
        the same node, one scale down - which is what makes the structure
        self-similar. Every renderer serves this unchanged.
        """
        from pathlib import Path

        title, seed = _parse_substrate(Path(target).read_text(encoding="utf-8"))
        g = cls()
        # The three coarse roots are the outside doors the network is sourced
        # through: endogenous from the author, exogenous from the literature,
        # intrinsic from the model's own priors. Atoms inherit their door.
        _DOOR = {"endogenous": "author", "exogenous": "literature", "intrinsic": "model"}

        # Pass 1: every node and its children, with stable ids.
        for order, nd in enumerate(seed):
            is_cluster = nd["kind"] == "cluster"
            nid = f"cluster:{_slug(nd['id'])}" if is_cluster else nd["id"]
            group = nd["id"].strip().lower() if is_cluster else nd["kind"]
            door = nd["source"] or (_DOOR.get(group, "") if is_cluster else "")
            g.nodes[nid] = Node(
                id=nid, kind=nd["kind"], label=nd["label"], group=group,
                source=door, link=nd["link"],
                meta={"summary": nd["summary"],
                      "scale": "coarse" if is_cluster else nd["kind"],
                      "order": order, "title": title},
            )
            nd["_nid"] = nid
            for ci, ch in enumerate(nd["children"]):
                chid = ch["handle"] or f"{nid}:{_slug(ch['kind'])}_{ci}"
                ch["_cid"] = chid
                g.nodes[chid] = Node(
                    id=chid, kind=ch["kind"], label=ch["text"],
                    group=group if is_cluster else ch["kind"],
                    source=door if is_cluster else nid, link=ch["link"],
                    meta={"parent": nid, "scale": "atom", "atom_kind": ch["kind"]},
                )
                g.edges.append(Edge(nid, chid, "contains", source="substrate"))

        # Pass 2: draws (the coarse-graining choice) and consistency (typed check),
        # including microscopic draws - an atom resting on a more primitive atom,
        # e.g. an endogenous definition on an intrinsic prior.
        for nd in seed:
            nid = nd["_nid"]
            for ref in nd["draws"]:
                if ref in g.nodes:
                    g.edges.append(Edge(nid, ref, "draws", source="substrate"))
            for ref, rel, note in nd["consistency"]:
                if ref in g.nodes and rel in ("supports", "contradicts"):
                    g.edges.append(Edge(nid, ref, rel, evidence=note, source="substrate"))
            for ch in nd["children"]:
                for ref in ch.get("draws", []):
                    if ref in g.nodes:
                        g.edges.append(Edge(ch["_cid"], ref, "draws", source="substrate"))

        # Interactions are computed, not drawn. ``induced`` projects shared draws
        # into peer interactions; ``lift`` aggregates cross-group micro edges into
        # macro couplings, so each coarse layer is a network in its own right.
        g.edges.extend(g.induced_interactions(rel="draws", threshold=1))
        g.edges.extend(g.lift_interactions(threshold=1))
        return g

    @classmethod
    def from_corpus(cls, target) -> "CanonGraph":
        """Build the graph from the global literature corpus (``corpus.bib``).

        The exogenous substrate as a first-class projection of the one
        conceptric - the literature is not a separate kind of graph, it is the
        same node/edge model sourced from the ``corpus_librarian`` store
        (canon://skills/corpus_librarian) instead of canon prose or a manuscript.
        The corpus is itself a **conceptric**, not a flat list - it nests:

        * **themes** - the coarse layer (``corpus/keywords.yaml`` ``themes``). A
          theme ``contains`` its clusters: the super-cluster a group of concepts
          cohere into.
        * **clusters** - the leaf concept layer. A cluster ``contains`` its
          references; a reference labelled with several clusters bridges them.
        * **references** - one per record, through the ``literature`` door,
          carrying its distilled ``claim``, its essential ``summary`` (the
          accurate primitive representation - this is long-term memory), and its
          ``status``. ``status`` sets the node's ``link`` (an ``unverified``
          record is ``loose`` - arrived, not yet trusted) and its ``weight``, so
          the render is a self-portrait, the way a skill's fitness sizes it.
        * **projects** - one per ``provenance`` key, ``cites``-ing every
          reference that carries it: who drew on what.

        Two kinds of edge carry the relational information:

        * **typed semantic relations** between sibling references - the record's
          rank-ordered ``relations`` field (``extends:key | why``,
          ``contests:key | why``, ...) becomes a typed reference->reference edge
          whose ``evidence`` is the human sentence that makes the edge mean
          something and whose ``count`` preserves the rank. A relation to a key
          not in the store becomes a ``dangling`` edge, visible like any broken
          link.
        * **computed couplings**, by the same one-mode projection the substrate
          uses (``induced_interactions``): two **projects** sharing a reference
          interact (cross-project); two **clusters** sharing a bridging reference
          interact (within-corpus). Drawn from co-dependence, not by hand.
        """
        from pathlib import Path

        target = Path(target)
        records = _parse_bib(target.read_text(encoding="utf-8"))
        tax = _load_corpus_taxonomy(target.parent)
        cluster_theme, theme_label = tax["cluster_theme"], tax["theme_label"]
        g = cls()
        for key, f in records:
            status = (f.get("status") or "unverified").strip().lower()
            clusters = [c.strip() for c in (f.get("cluster") or "").split(",") if c.strip()] or ["unclustered"]
            provs = [p.strip() for p in (f.get("provenance") or "").split(",") if p.strip()]
            themes = [cluster_theme[c] for c in clusters if c in cluster_theme]
            rid = f"ref:{key}"
            g.nodes[rid] = Node(
                id=rid, kind="reference", label=key, group=_slug(clusters[0]),
                status=status, weight=_STATUS_WEIGHT.get(status, 0.3),
                source="literature", link=_STATUS_LINK.get(status, "loose"),
                meta={
                    "title": f.get("title", ""), "year": f.get("year", ""),
                    "claim": f.get("claim", ""), "tldr": f.get("tldr", ""),
                    "summary": f.get("summary", ""), "status": status,
                    "doi": f.get("doi", ""), "clusters": clusters,
                    "themes": sorted(set(themes)), "provenance": provs,
                    "keywords": [k.strip() for k in (f.get("keywords") or "").split(",") if k.strip()],
                    "relations": f.get("relations", ""),
                },
            )
            for c in clusters:
                cid = f"cluster:{_slug(c)}"
                theme = cluster_theme.get(c)
                g.nodes.setdefault(cid, Node(
                    id=cid, kind="cluster", label=c, group=_slug(c),
                    source="literature", meta={"scale": "coarse", "theme": theme},
                ))
                g.edges.append(Edge(cid, rid, "contains", source="corpus"))
                if theme:
                    tid = f"theme:{_slug(theme)}"
                    g.nodes.setdefault(tid, Node(
                        id=tid, kind="theme", label=theme_label.get(theme, theme),
                        group=_slug(theme), source="literature",
                        meta={"scale": "theme", "theme": theme},
                    ))
                    g.edges.append(Edge(tid, cid, "contains", source="corpus"))
            for p in provs:
                pid = f"project:{_slug(p)}"
                g.nodes.setdefault(pid, Node(
                    id=pid, kind="project", label=p, group="project", source="literature",
                ))
                g.edges.append(Edge(pid, rid, "cites", source="corpus"))

        # Typed semantic relations: a reference's rank-ordered map of edges to the
        # sibling references it relates to, each carrying the sentence that makes
        # the link mean something. The rank rides in ``count`` (1 = top), so a
        # renderer or a later reader can read the most-important relation first.
        for key, f in records:
            rid = f"ref:{key}"
            for rank, (rtype, tgt, desc) in enumerate(_parse_relations(f.get("relations", "")), start=1):
                tnode = f"ref:{tgt}"
                if tnode == rid:
                    continue
                if tnode in g.nodes:
                    g.edges.append(Edge(rid, tnode, rtype, evidence=desc, source="corpus", count=rank))
                else:
                    miss = f"missing:{tgt}"
                    g.nodes.setdefault(miss, Node(id=miss, kind="missing", label=tgt, group="missing"))
                    g.edges.append(Edge(rid, miss, "dangling", desc or f"relation: {rtype}:{tgt}", "corpus"))

        # Computed couplings (the substrate's rule): projects sharing a reference
        # interact (cross-project); clusters sharing a bridging reference interact
        # (within-corpus). The typed relation edges above are left as themselves -
        # the relational signal is explicit, not collapsed into a count.
        g.edges.extend(g.induced_interactions(rel="cites", threshold=1))
        g.edges.extend(g.induced_interactions(rel="contains", threshold=1))
        g._collapse_parallel_edges()
        return g

    # -- internals ----------------------------------------------------------
    def _build_resolver(self, canon: Canon) -> dict[str, str]:
        """Map every token a link might use to a node id.

        Resolution order matters: an exact skill name or full wiki ref wins over
        a bare path tail, which is the ambiguous case (two pages can share a
        leaf name). On a tail collision the first by sorted ref wins, which is
        deterministic and good enough - the dangling check still catches a link
        that resolves to the wrong twin only if it points nowhere.
        """
        idx: dict[str, str] = {}
        for dname in canon.domains():
            idx.setdefault(dname, f"domain:{dname}")
        # Agents are addressed as agents/<name>.yaml or agents/<name> in prose.
        for nid in self.nodes:
            if nid.startswith("agent:"):
                aname = nid.split(":", 1)[1]
                idx[f"agents/{aname}.yaml"] = nid
                idx[f"agents/{aname}"] = nid
                idx.setdefault(aname, nid)
        # Tails first (lowest priority), so exact refs/names below overwrite them.
        for ref in sorted(canon.wiki):
            tail = ref.rsplit("/", 1)[-1]
            idx.setdefault(tail, f"wiki:{ref}")
        for ref in canon.wiki:
            idx[ref] = f"wiki:{ref}"
        for name in canon.skills:
            idx[name] = f"skill:{name}"
        return idx

    def _extract_prose_edges(
        self, src_id: str, path, resolver: dict[str, str], canon: Canon,
        mask_code: bool = True,
    ) -> None:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return
        _, body = _split_frontmatter(text)
        source = path.name
        # Scan a code-masked copy so a DOCUMENTED [[name]]/canon:// example in a
        # fence or backticks is never harvested as a real edge. Masking is
        # length-preserving, so a surviving match still indexes the original body
        # for evidence. Agent yaml carries deliberate backticked refs to the
        # skills it wields, so it opts out (mask_code=False).
        scan = _mask_code_spans(body) if mask_code else body

        for m in _WIKILINK_RE.finditer(scan):
            token = m.group(1).split("|", 1)[0].strip()
            token = token.rsplit("/", 1)[-1].removesuffix(".md")
            self._add_link(src_id, token, resolver, body, m.start(), source)

        for m in _CANON_RE.finditer(scan):
            # The char class admits '.', so a link ending a sentence captures the
            # trailing full stop (canon://x.yaml.) - strip trailing punctuation
            # before resolving, then drop a bare .md page suffix.
            raw = m.group(1).strip().rstrip(".").removesuffix(".md")
            if raw.startswith("skills/"):
                # strip the leading "skills/" then drop any trailing "/SKILL"
                # so both canon://skills/<name> and canon://skills/<name>/SKILL.md
                # resolve to the same skill:<name> node.
                token = raw.split("/", 1)[1].removesuffix("/SKILL")
            else:
                token = raw  # full wiki ref, or agents/<name>.yaml
            self._add_link(src_id, token, resolver, body, m.start(), source)

    def _add_link(
        self, src_id: str, token: str, resolver: dict[str, str],
        body: str, pos: int, source: str,
    ) -> None:
        if not token or "..." in token or any(c in token for c in "<>*"):
            return  # a prose template placeholder, not a real link
        dst = resolver.get(token)
        evidence = _line_at(body, pos)
        if dst is None:
            miss_id = f"missing:{token}"
            self.nodes.setdefault(
                miss_id,
                Node(id=miss_id, kind="missing", label=token, group="missing"),
            )
            self.edges.append(Edge(src_id, miss_id, "dangling", evidence, source))
            return
        if dst == src_id:
            return  # a page that names itself is not an edge
        self.edges.append(Edge(src_id, dst, "links_to", evidence, source))

    def _add_consistency_edge(
        self, src_id: str, ref: str, rel: str, note: str,
        resolver: dict[str, str],
    ) -> None:
        """Project one frontmatter ``consistency`` tuple into a typed edge.

        The canon-prose peer of the substrate's ``consistency:`` seed (see
        ``from_substrate`` Pass 2). ``ref`` resolves through the same index a
        prose link uses, so a tail, a full wiki ref, a ``canon://`` form, or a
        skill name all work. An unresolved ref becomes a ``dangling`` edge so a
        broken annotation is visible, never silently dropped.
        """
        rel = (rel or "").strip().lower()
        if rel not in ("supports", "contradicts"):
            return  # an unknown relation is not a typed check edge
        token = ref.strip().removeprefix("canon://").rstrip(".").removesuffix(".md")
        if token.startswith("skills/"):
            token = token.split("/", 1)[1].removesuffix("/SKILL")
        dst = resolver.get(token) or resolver.get(token.rsplit("/", 1)[-1])
        if dst is None:
            miss_id = f"missing:{token}"
            self.nodes.setdefault(
                miss_id,
                Node(id=miss_id, kind="missing", label=token, group="missing"),
            )
            self.edges.append(
                Edge(src_id, miss_id, "dangling", note or f"consistency: {ref}", "canon")
            )
            return
        if dst == src_id:
            return  # a node declaring a check against itself is not an edge
        self.edges.append(Edge(src_id, dst, rel, note, "canon"))

    def _collapse_parallel_edges(self) -> None:
        seen: dict[tuple[str, str, str], Edge] = {}
        for e in self.edges:
            key = (e.src, e.dst, e.rel)
            if key in seen:
                seen[key].count += 1
            else:
                seen[key] = e
        self.edges = list(seen.values())

    # -- analytics ----------------------------------------------------------
    def neighbours(self, undirected: bool = True) -> dict[str, set[str]]:
        adj: dict[str, set[str]] = defaultdict(set)
        for e in self.edges:
            adj[e.src].add(e.dst)
            if undirected:
                adj[e.dst].add(e.src)
        return adj

    def health(self) -> dict[str, Any]:
        """Topology as a health report.

        * orphans - real nodes (not ``missing``) with no edge at all
        * dangling - links into a non-existent target
        * dead_wood_linked - deprecated skills still pointed at by live prose
        * components - count of connected components over real nodes
        """
        adj = self.neighbours(undirected=True)
        real = {nid for nid, n in self.nodes.items() if n.kind != "missing"}
        orphans = sorted(nid for nid in real if not adj.get(nid))

        dangling = [
            {"from": e.src, "to": self.nodes[e.dst].label, "evidence": e.evidence, "source": e.source}
            for e in self.edges
            if e.rel == "dangling"
        ]

        deprecated = {
            nid for nid, n in self.nodes.items() if n.kind == "skill" and n.status == "deprecated"
        }
        dead_wood_linked = sorted(
            {e.dst for e in self.edges if e.rel == "links_to" and e.dst in deprecated}
        )

        # Contradictions: the consistency guard with teeth. A ``contradicts`` edge
        # is a typed inconsistency one node asserts against another (the
        # substrate's ``consistency:`` line, or a canon node's own
        # ``consistency:`` frontmatter annotation). Each
        # carries which inherited (``ancestor``) nodes it implicates - the audit
        # trigger, since the ad-hoc baseline is what to scrutinise first when the
        # graph stops cohering. A contradiction is a finding, not noise: it is the
        # most useful thing the guard can surface.
        # GAP: implicit conflicts (two axioms that clash without an explicit edge)
        # are not detected here - that needs a semantic pass, named not faked.
        contradictions = [
            {
                "from": e.src,
                "to": e.dst,
                "evidence": e.evidence,
                "source": e.source,
                "ancestor_implicated": sorted(
                    nid for nid in (e.src, e.dst)
                    if nid in self.nodes and self.nodes[nid].source == "ancestor"
                ),
            }
            for e in self.edges
            if e.rel == "contradicts"
        ]

        # Frontier = the learning to-do. ``loose`` nodes have arrived but are not
        # yet wired in; ``unsourced`` nodes claim to be linked yet trace to no
        # source (a provenance-closure violation: sourced from nowhere). The
        # exogenous/intrinsic doors are legitimate sources, never unsourced - and
        # so is ``ancestor``, the pre-provenance baseline, so the frontier flags
        # only genuinely unattributed nodes (an engine writer that failed to
        # stamp), not the whole inherited canon.
        loose = sorted(nid for nid, n in self.nodes.items() if n.link == "loose")
        unsourced = sorted(
            nid for nid, n in self.nodes.items()
            if n.kind != "missing" and not n.source and n.link != "loose"
        )
        frontier = {"loose": loose, "unsourced": unsourced}

        # The inherited baseline: nodes carried from prior ad-hoc sessions. Not a
        # to-do (they function until proven otherwise), but a cohort to scrutinise
        # first when a contradiction or malfunction surfaces - between "do not
        # touch" and "do not trust".
        ancestral = sorted(
            nid for nid, n in self.nodes.items() if n.source == "ancestor"
        )

        return {
            "orphans": orphans,
            "dangling": dangling,
            "dead_wood_linked": dead_wood_linked,
            "contradictions": contradictions,
            "frontier": frontier,
            "ancestral": ancestral,
            "components": self._component_count(real, adj),
            "node_count": len(real),
            "edge_count": sum(1 for e in self.edges if e.rel != "dangling"),
            "pass": not orphans and not dangling and not dead_wood_linked and not contradictions,
        }

    def audit_both_ways(self, occurrence_root: Any = None) -> dict[str, Any]:
        """The both-ways audit: is every node coarse-grainable in *both* directions?

        The sew-up principle turned on the whole engine (``EIGEN_ARCHITECTURE.md``,
        the recursive-self-similar docket): *above and below are each generator of
        and generated by the other.* Concretely, two pointers per node:

        * **provenance-down** - the specific *occurrence* that earned this node.
          The ``source`` door records the coarse origin (``dreamer`` / ``author`` /
          ``ancestor``); the down-pointer wants the concrete occurrence (a dated
          session, a result, a soul entry). A node whose only provenance is the
          pre-provenance baseline ``ancestor`` (or nothing) is **unearned**: it
          asserts a rule with no trace of what taught it. This is the existing
          ``ancestral`` frontier read as one half of the duality - *closure is
          provenance*, made into a coarse-graining-down obligation.
        * **draws-up** - the more-global idea this node *instantiates*. A node is
          **anchored** if it points up or laterally into the conceptric: it has a
          ``parent`` (the coarse node it nests beneath), belongs to a domain, or
          carries a prose/consistency/draws edge to another real node. A node with
          no outward edge at all is **unanchored** - an island asserting a local
          fact that draws up to nothing.

        The two frontiers are the to-do the v2 both-ways wiring works down. This is
        the *measurement* (build it, look at the gap); it sets no policy and wires
        no edge - it only names, per node, which pointer is missing. A node missing
        *neither* is fully coarse-grainable both ways; the loop closes through it.

        When ``occurrence_root`` is given, each ``earned_by`` occurrence is resolved
        against it, and one that names a non-existent artifact is reported as
        ``stale_provenance`` - the down-pointer's peer of a dangling link. A
        provenance pointer to a deleted handoff is closure that no longer closes.
        """
        from pathlib import Path

        root = Path(occurrence_root) if occurrence_root is not None else None
        real = {nid: n for nid, n in self.nodes.items() if n.kind != "missing"}

        # Outgoing real edges per node (the up/lateral pointers - excludes the
        # structural ``contains`` a coarse node emits *downward* to its children,
        # and the ``dangling`` non-edges).
        _DOWNWARD = {"dangling", "contains", "has_axioms", "has_project"}
        out_real: dict[str, int] = defaultdict(int)
        for e in self.edges:
            if e.rel in _DOWNWARD:
                continue
            if e.src in real and e.dst in real:
                out_real[e.src] += 1
        has_parent = {
            nid for nid, n in real.items() if n.meta.get("parent")
        }

        unearned, unanchored, closed, stale = [], [], [], []
        for nid, n in real.items():
            # provenance-down is present when *either* the coarse ``source`` door
            # names a concrete origin (not the pre-provenance ``ancestor``) *or* an
            # explicit ``earned_by`` annotation names the occurrence that earned it.
            # The annotation upgrades a still-``ancestor`` node to earned: it is how
            # the down-frontier closes one node at a time without re-stamping source.
            earned_by = n.meta.get("earned_by") or []
            earned = (bool(n.source) and n.source != "ancestor") or bool(earned_by)
            anchored = nid in has_parent or out_real.get(nid, 0) > 0
            row = {
                "id": nid,
                "kind": n.kind,
                "scope": n.meta.get("scope"),
                "source": n.source or "(none)",
                "earned_by": [o for o, _ in earned_by],
            }
            if not earned:
                unearned.append(row)
            if not anchored:
                unanchored.append(row)
            if earned and anchored:
                closed.append(nid)
            if root is not None:
                for occ, _note in earned_by:
                    # an occurrence may carry a #fragment or be a bare id - resolve
                    # the path part only, against the repo root.
                    occ_path = occ.split("#", 1)[0].strip()
                    if occ_path and not (root / occ_path).exists():
                        stale.append({"id": nid, "occurrence": occ})

        n_real = len(real)
        return {
            "node_count": n_real,
            # provenance-down: the occurrence that earned the node
            "unearned": sorted(unearned, key=lambda r: r["id"]),
            "earned_count": n_real - len(unearned),
            # draws-up: the idea the node instantiates
            "unanchored": sorted(unanchored, key=lambda r: r["id"]),
            "anchored_count": n_real - len(unanchored),
            # both pointers present - the loop closes through these nodes
            "both_ways_count": len(closed),
            # provenance pointers into a now-missing artifact (only when checked)
            "stale_provenance": sorted(stale, key=lambda r: r["id"]),
            "pass": not unearned and not unanchored,
        }

    @staticmethod
    def _component_count(real: set[str], adj: dict[str, set[str]]) -> int:
        seen: set[str] = set()
        comps = 0
        for start in real:
            if start in seen:
                continue
            comps += 1
            stack = [start]
            while stack:
                cur = stack.pop()
                if cur in seen:
                    continue
                seen.add(cur)
                stack.extend(n for n in adj.get(cur, ()) if n in real and n not in seen)
        return comps

    def focus(self, node_id: str, depth: int = 2) -> CanonGraph:
        """Return the BFS neighbourhood subgraph within ``depth`` hops of a node."""
        if node_id not in self.nodes:
            raise KeyError(f"node {node_id!r} not in graph")
        adj = self.neighbours(undirected=True)
        keep: dict[str, int] = {node_id: 0}
        q: deque[str] = deque([node_id])
        while q:
            cur = q.popleft()
            if keep[cur] >= depth:
                continue
            for nxt in adj.get(cur, ()):
                if nxt not in keep:
                    keep[nxt] = keep[cur] + 1
                    q.append(nxt)
        sub = CanonGraph(
            nodes={nid: self.nodes[nid] for nid in keep},
            edges=[e for e in self.edges if e.src in keep and e.dst in keep],
        )
        # Stash BFS depth for radial layout in the canvas renderer.
        for nid, d in keep.items():
            sub.nodes[nid].meta = {**sub.nodes[nid].meta, "_ring": d}
        return sub

    def filter_kinds(self, kinds: Iterable[str]) -> CanonGraph:
        keep = {nid for nid, n in self.nodes.items() if n.kind in set(kinds)}
        return CanonGraph(
            nodes={nid: self.nodes[nid] for nid in keep},
            edges=[e for e in self.edges if e.src in keep and e.dst in keep],
        )

    def induced_interactions(self, rel: str = "contains", threshold: int = 1) -> list[Edge]:
        """Lateral interactions DERIVED from shared children: the one-mode
        projection of the parent->child bipartite graph along ``rel``. Two
        parents sharing >= ``threshold`` children get a ``shares`` edge whose
        weight is the shared count. This is how interaction at a layer is
        computed from co-dependence on the layer below, not hand-drawn - the
        author's rule that two upper nodes drawing the same lower information
        interact, and that interaction is describable at their own layer."""
        kids: dict[str, set[str]] = defaultdict(set)
        for e in self.edges:
            if e.rel == rel:
                kids[e.src].add(e.dst)
        parents = sorted(p for p in kids if kids[p])
        out: list[Edge] = []
        for i in range(len(parents)):
            for j in range(i + 1, len(parents)):
                shared = kids[parents[i]] & kids[parents[j]]
                if len(shared) >= threshold:
                    out.append(Edge(parents[i], parents[j], "shares",
                                    evidence=", ".join(sorted(shared))[:200],
                                    source="induced", count=len(shared)))
        return out

    def lift_interactions(self, threshold: int = 1) -> list[Edge]:
        """Coarse-graining of edges (renormalised couplings): lift every
        cross-group micro edge to a ``shares`` interaction between the coarse
        parents that ``contains`` its endpoints. If an endogenous definition
        rests on an intrinsic prior, the endogenous and intrinsic coarse nodes
        interact at the macro layer, weighted by how many primitives they share.
        The interaction structure compresses with the nodes - which is what lets
        a layer be read without opening its interior."""
        parent: dict[str, str] = {}
        for e in self.edges:
            if e.rel == "contains":
                parent[e.dst] = e.src
        pairs: dict[tuple, int] = defaultdict(int)
        for e in self.edges:
            pa, pb = parent.get(e.src), parent.get(e.dst)
            if pa and pb and pa != pb:
                pairs[tuple(sorted((pa, pb)))] += 1
        return [Edge(a, b, "shares", source="lifted", count=c)
                for (a, b), c in pairs.items() if c >= threshold]

    # -- projections --------------------------------------------------------
    # Node threshold above which to_json auto-summarises when summary=True. Must
    # stay above the canon's own node count or the canon graph would wrongly
    # self-summarise - raise it as the canon grows (it is here to bound genuinely
    # large manuscript graphs, not to cap the canon).
    _SUMMARY_THRESHOLD = 120

    def to_json(self, summary: bool = False) -> dict[str, Any]:
        """The interchange format. Any viewer - and any future graph source,
        like a manuscript-structure graph - speaks this.

        When ``summary`` is True and the graph exceeds ``_SUMMARY_THRESHOLD``
        nodes, the full node/edge lists are replaced with kind counts, relation
        counts, and a small node sample, keeping the response well inside the
        MCP token budget. The ``health`` block is always returned in full. Pass
        ``summary=False`` (the default) to get the complete lists.
        """
        h = self.health()
        if summary and len(self.nodes) > self._SUMMARY_THRESHOLD:
            kind_counts: dict[str, int] = {}
            for n in self.nodes.values():
                kind_counts[n.kind] = kind_counts.get(n.kind, 0) + 1
            rel_counts: dict[str, int] = {}
            for e in self.edges:
                rel_counts[e.rel] = rel_counts.get(e.rel, 0) + 1
            sample = [
                {"id": n.id, "kind": n.kind, "label": n.label, "group": n.group}
                for n in list(self.nodes.values())[:20]
            ]
            return {
                "summary": True,
                "node_count": len(self.nodes),
                "edge_count": len(self.edges),
                "kind_counts": kind_counts,
                "rel_counts": rel_counts,
                "node_sample": sample,
                "health": h,
            }
        return {
            "nodes": [
                {
                    "id": n.id, "kind": n.kind, "label": n.label, "group": n.group,
                    "status": n.status, "weight": round(n.weight, 3),
                    "source": n.source, "link": n.link, "meta": n.meta,
                }
                for n in self.nodes.values()
            ],
            "edges": [
                {
                    "src": e.src, "dst": e.dst, "rel": e.rel,
                    "evidence": e.evidence, "source": e.source, "count": e.count,
                }
                for e in self.edges
            ],
            "health": h,
        }

    def to_mermaid(self, direction: str = "LR") -> str:
        """A Mermaid ``graph`` - the universal projection, embeds in any
        markdown note or, via a filter, a manuscript appendix.

        Node shape and class carry meaning: a deprecated skill or an orphan
        renders in a warning class, a dangling link renders dashed into a ghost
        node. Skill node size tracks fitness through the class buckets.
        """
        lines = [f"graph {direction}"]
        groups: dict[str, list[str]] = defaultdict(list)
        classes: dict[str, str] = {}

        for n in self.nodes.values():
            nid = _mid(n.id)
            label = _esc(n.label)
            if n.kind == "missing":
                node = f'{nid}["{label}"]'
                classes[nid] = "dangling"
            elif n.kind == "domain":
                node = f'{nid}{{{{"{label}"}}}}'
                classes[nid] = "g_domain"
            elif n.kind == "skill":
                node = f'{nid}(["{label}"])'
                classes[nid] = _skill_class(n)
            else:
                node = f'{nid}["{label}"]'
                classes[nid] = f"g_{n.group}"
            groups[n.group].append(node)

        # Emit nodes grouped into subgraphs by colour bucket for readability.
        for group, decls in groups.items():
            lines.append(f"  subgraph {_mid('grp_'+group)}[{_esc(group)}]")
            for d in decls:
                lines.append(f"    {d}")
            lines.append("  end")

        for e in self.edges:
            arrow = "-.->|dangling|" if e.rel == "dangling" else (
                f"-->|{_esc(e.rel)}|" if e.rel != "links_to" else "-->"
            )
            lines.append(f"  {_mid(e.src)} {arrow} {_mid(e.dst)}")

        for nid, cls in classes.items():
            lines.append(f"  class {nid} {cls};")

        # classDefs: group colours, plus skill-fitness and warning buckets.
        for group in groups:
            if group in ("domain", "missing"):
                continue
            lines.append(f"  classDef g_{group} fill:{_group_hex(group)},color:#fff,stroke:#333;")
        lines.append(f"  classDef g_domain fill:{_DOMAIN_HEX},color:#fff,stroke:#000,stroke-width:2px;")
        lines.append("  classDef dangling fill:#fff,color:#900,stroke:#900,stroke-dasharray:4 3;")
        lines.append("  classDef skill_hot fill:#9B5DE5,color:#fff,stroke:#333,stroke-width:3px;")
        lines.append("  classDef skill_warm fill:#B388E0,color:#fff,stroke:#333;")
        lines.append("  classDef skill_cold fill:#E8DAF5,color:#333,stroke:#999;")
        lines.append("  classDef skill_dead fill:#eee,color:#999,stroke:#bbb,stroke-dasharray:3 3;")
        return "\n".join(lines)

    def to_obsidian_graph(self) -> dict[str, Any]:
        """An Obsidian ``graph.json`` colour-group config, one group per bucket.

        Obsidian colours by note path. Canon pages do not live in the vault by
        default, so the colour groups key off the label text - drop this beside a
        vault export of the canon and the groups light up."""
        groups = []
        seen: set[str] = set()
        for n in self.nodes.values():
            if n.group in seen or n.kind == "missing":
                continue
            seen.add(n.group)
            groups.append({"query": f"tag:#{n.group} OR path:{n.group}", "color": _rgb(_group_hex(n.group))})
        return {
            "colorGroups": groups,
            "showTags": True,
            "showAttachments": False,
            "collapse-filter": False,
            "scale": 1,
        }

    def to_canvas(self, radial: bool = False) -> dict[str, Any]:
        """An Obsidian ``.canvas`` (JSONCanvas). Force-clustered by group for the
        full map, or concentric rings by BFS depth when built from ``focus``.

        Layout is deterministic - positions come from group/ring indices and
        node order, never randomness, so the same graph always lays out the same
        way and a diff of two canvases is meaningful."""
        cnodes, cedges = [], []
        positions = self._radial_positions() if radial else self._clustered_positions()
        for n in self.nodes.values():
            x, y = positions[n.id]
            size = _canvas_size(n)
            cnodes.append({
                "id": _cid(n.id),
                "type": "text",
                "text": f"**{n.label}**" + (f"\n_{n.status}_" if n.status else ""),
                "x": int(x), "y": int(y),
                "width": size, "height": max(60, size // 3),
                "color": _GROUP_CANVAS_COLOR.get(n.group, "1"),
            })
        for i, e in enumerate(self.edges):
            cedges.append({
                "id": f"e{i}",
                "fromNode": _cid(e.src),
                "toNode": _cid(e.dst),
                "label": "" if e.rel == "links_to" else e.rel,
                "toEnd": "arrow",
                **({"color": "1"} if e.rel == "dangling" else {}),
            })
        return {"nodes": cnodes, "edges": cedges}

    # -- layouts (deterministic) -------------------------------------------
    def _clustered_positions(self) -> dict[str, tuple[float, float]]:
        by_group: dict[str, list[Node]] = defaultdict(list)
        for n in self.nodes.values():
            by_group[n.group].append(n)
        pos: dict[str, tuple[float, float]] = {}
        groups = sorted(by_group)
        ring_r = 1600
        for gi, group in enumerate(groups):
            ga = 2 * math.pi * gi / max(1, len(groups))
            cx, cy = ring_r * math.cos(ga), ring_r * math.sin(ga)
            members = sorted(by_group[group], key=lambda n: n.id)
            cols = max(1, int(math.ceil(math.sqrt(len(members)))))
            for mi, n in enumerate(members):
                row, col = divmod(mi, cols)
                pos[n.id] = (cx + col * 420 - cols * 210, cy + row * 200)
        return pos

    def _radial_positions(self) -> dict[str, tuple[float, float]]:
        rings: dict[int, list[Node]] = defaultdict(list)
        for n in self.nodes.values():
            rings[int(n.meta.get("_ring", 1))].append(n)
        pos: dict[str, tuple[float, float]] = {}
        for d, members in rings.items():
            members = sorted(members, key=lambda n: n.id)
            if d == 0:
                pos[members[0].id] = (0.0, 0.0)
                continue
            r = 700 * d
            for mi, n in enumerate(members):
                a = 2 * math.pi * mi / max(1, len(members))
                pos[n.id] = (r * math.cos(a), r * math.sin(a))
        return pos


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wiki_group(ref: str) -> str:
    top = ref.split("/", 1)[0]
    return top if top in _WIKI_SECTION_HEX else "structure"


def _agent_role(path) -> str:
    """Pull the ``role:`` line from an agent yaml without a full parse."""
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("role:"):
                return line.split(":", 1)[1].strip()
    except (OSError, UnicodeError):
        pass
    return ""


def _read_tex(fp) -> str:
    try:
        return fp.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return fp.read_text(encoding="utf-16")


def _strip_comments(text: str) -> str:
    return re.sub(r"(?<!\\)%.*?$", "", text, flags=re.MULTILINE)


def _flatten_inputs(root, seen: set | None = None, depth: int = 0) -> str:
    """Inline every ``\\input``/``\\include`` from a root ``.tex``, in place.

    Section ordering in a multi-file manuscript lives in the root file's input
    sequence, not in sorted filenames - the discussion follows the results,
    appendices run a..k. Splicing each child where it is invoked recovers that
    true reading order, so the section ``precedes`` chain matches the paper. The
    ``seen`` set and depth cap guard against an include cycle.
    """
    from pathlib import Path

    root = Path(root)
    seen = set() if seen is None else seen
    rp = root.resolve()
    if rp in seen or depth > 32:
        return ""
    seen.add(rp)
    try:
        text = _strip_comments(_read_tex(root))
    except (OSError, UnicodeError):
        return ""

    def _repl(m: "re.Match[str]") -> str:
        cpath = root.parent / m.group(1).strip()
        if cpath.suffix != ".tex":
            cpath = cpath.with_suffix(".tex")
        return _flatten_inputs(cpath, seen, depth + 1)

    return _INPUT_RE.sub(_repl, text)


def _gather_manuscript_text(target) -> str:
    """Merge a manuscript's sources into one comment-stripped string.

    A single file is flattened along its ``\\input`` tree (true reading order).
    A directory is the sorted-glob fallback for a loose set of section files
    with no root, mirroring the crossref ledger's merge order.
    """
    from pathlib import Path

    target = Path(target)
    if target.is_dir():
        parts = []
        for fp in sorted(target.glob("**/*.tex")):
            try:
                parts.append(_strip_comments(_read_tex(fp)))
            except (OSError, UnicodeError):
                continue
        return "\n".join(parts)
    return _flatten_inputs(target)


def _gather_input_files(root, seen: set | None = None, depth: int = 0) -> list:
    """The ``(path, comment-stripped text)`` of a root ``.tex`` and its input tree.

    The pair-yielding peer of :func:`_flatten_inputs`: the same input-following
    discipline (same ``_INPUT_RE``, same cycle/depth guard) but it keeps each
    file distinct instead of inlining, so a caller that needs per-file
    attribution - crossref's duplicate-label ledger - keeps it. Pre-order: the
    root precedes the children it pulls in, in the order they are ``\\input``.
    """
    from pathlib import Path

    root = Path(root)
    seen = set() if seen is None else seen
    rp = root.resolve()
    if rp in seen or depth > 32:
        return []
    seen.add(rp)
    try:
        text = _strip_comments(_read_tex(root))
    except (OSError, UnicodeError):
        return []
    out = [(root, text)]
    for m in _INPUT_RE.finditer(text):
        cpath = root.parent / m.group(1).strip()
        if cpath.suffix != ".tex":
            cpath = cpath.with_suffix(".tex")
        out.extend(_gather_input_files(cpath, seen, depth + 1))
    return out


def gather_manuscript_files(target) -> list:
    """A manuscript's sources in reading order, comment-stripped and attributed.

    The one gatherer crossref and the conceptric share, so a single artifact has
    a single reading order. A root ``.tex`` is walked along its
    ``\\input``/``\\include`` tree (the order the paper actually reads); a
    directory is the sorted-glob fallback for a rootless set of section files.
    Returns ``(path, text)`` pairs: join the text for one string, or keep them
    per-file when attribution matters.
    """
    from pathlib import Path

    target = Path(target)
    if target.is_dir():
        out = []
        for fp in sorted(target.glob("**/*.tex")):
            try:
                out.append((fp, _strip_comments(_read_tex(fp))))
            except (OSError, UnicodeError):
                continue
        return out
    return _gather_input_files(target)


def _ring_group(name: str) -> str:
    """Classify a section into a core-outward ring by its title."""
    if _RING_CORE.search(name):
        return "ring_core"
    if _RING_OUTER.search(name):
        return "ring_outer"
    return "section"


def _slug(s: str) -> str:
    s = re.sub(r"[:/\s\-]+", "_", s.strip())
    s = re.sub(r"[^A-Za-z0-9_]", "", s)
    return (s[:60] or "x").lower()


# -- corpus parsing (the exogenous substrate, from corpus.bib) --------------
# A reference's trust status maps to the learning-state link the frontier reads
# (unverified is 'loose': arrived, not yet wired in) and to a render weight, so
# the corpus graph is a self-portrait the way the skill graph is.
_STATUS_LINK = {
    "established": "closed", "borrowed": "linked", "provisional": "linked",
    "contested": "linked", "unverified": "loose", "open-gap": "loose",
}
_STATUS_WEIGHT = {
    "established": 0.9, "provisional": 0.6, "borrowed": 0.5,
    "open-gap": 0.5, "contested": 0.4, "unverified": 0.3,
}
_BIB_ENTRY_RE = re.compile(r"@\w+\s*\{\s*([^,\s]+)\s*,")
_BIB_FIELD_RE = re.compile(
    r"(\w+)\s*=\s*(\{(?:[^{}]|\{[^{}]*\})*\}|\"[^\"]*\"|[^,\n]+)"
)


# The controlled relation vocabulary (mirrors corpus/keywords.yaml `relations`).
# A relation a record declares to a sibling becomes a typed reference->reference
# edge; an unknown type is dropped (not faked into a generic link).
_REL_TYPES = {
    "extends", "refines", "generalizes", "specializes", "contests", "corroborates",
    "applies", "tests", "motivates", "background_for", "analogue_of", "method_for",
    "reviews",
}
_REL_RE = re.compile(r"([a-z_]+)\s*:\s*([^|]+?)\s*(?:\|\s*(.*))?$")


def _parse_relations(raw: str) -> list[tuple[str, str, str]]:
    """Parse a record's ``relations`` field into ``(type, target_key, description)``.

    Grammar: ``type:targetkey | description`` entries, ``;``-separated, in rank
    order (most important first). The description is the semantic sentence that
    makes the edge mean something; an entry with an unknown type or no target is
    skipped."""
    out: list[tuple[str, str, str]] = []
    for chunk in raw.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        m = _REL_RE.match(chunk)
        if not m:
            continue
        rtype, tgt, desc = m.group(1).strip(), m.group(2).strip(), (m.group(3) or "").strip()
        if rtype in _REL_TYPES and tgt:
            out.append((rtype, tgt, desc))
    return out


def _load_corpus_taxonomy(dirpath) -> dict[str, dict[str, str]]:
    """Read ``keywords.yaml`` beside the corpus for the cluster->theme hierarchy.

    Returns ``{"cluster_theme": {cluster: theme}, "theme_label": {theme: label}}``.
    Defensive: a missing or unparseable file yields empty maps, and the corpus
    graph degrades to flat (clusters with no theme), never an error."""
    from pathlib import Path

    res = {"cluster_theme": {}, "theme_label": {}}
    kp = Path(dirpath) / "keywords.yaml"
    if not kp.exists():
        return res
    try:
        import yaml

        data = yaml.safe_load(kp.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001 - the taxonomy is an enrichment, never a hard dep
        return res
    for tname, t in (data.get("themes") or {}).items():
        t = t or {}
        res["theme_label"][tname] = t.get("label", tname)
        for c in t.get("clusters", []) or []:
            res["cluster_theme"][c] = tname
    return res


def _parse_bib(text: str) -> list[tuple[str, dict[str, str]]]:
    """Parse a biblatex file into ``(citekey, {field: value})`` pairs.

    Tolerant, stdlib-regex, the peer of ``corpus_librarian``'s ``check_corpus``
    parser: a balanced-brace scan finds each entry body, then a field pass reads
    ``field = {value}`` / ``"value"`` / bare. ``partial:<restriction>`` and
    accented braces survive. The conceptric reads the store the librarian writes,
    so the two parse it the same way."""
    out: list[tuple[str, dict[str, str]]] = []
    for m in _BIB_ENTRY_RE.finditer(text):
        key = m.group(1).strip()
        i = m.start() + text[m.start():].index("{") + 1
        depth, j = 1, i
        while j < len(text) and depth > 0:
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
            j += 1
        body = text[m.end():j - 1]
        fields: dict[str, str] = {}
        for fm in _BIB_FIELD_RE.finditer(body):
            fields[fm.group(1).strip().lower()] = fm.group(2).strip().strip("{}").strip('"').strip()
        out.append((key, fields))
    return out


def _clean_math(body: str) -> str:
    """The LaTeX of a math environment, fit for KaTeX: drop the ``\\label`` and
    ``\\notag``/``\\nonumber`` markers (KaTeX rejects ``\\label``), collapse
    whitespace. Kept compact - this is the body a viewer typesets, not a
    reformatter."""
    body = _LABEL_RE.sub("", body)
    body = re.sub(r"\\(?:notag|nonumber)\b", "", body)
    return body.strip()


# -- blueprint parsing (the plan, before the .tex) -------------------------
_RING_GROUPS = {"core": "ring_core", "inner": "ring_inner", "framing": "ring_outer"}


def _blueprint_ring_group(ring: str | None) -> str:
    return _RING_GROUPS.get((ring or "").strip().lower(), "section")


def _match_claim(claims: list[dict], serves: str | None) -> dict | None:
    """Resolve an equation's ``serves:`` to a claim - by 1-based index (C1/1) or
    by a case-insensitive substring of the claim text."""
    if not serves:
        return None
    serves = serves.strip()
    m = re.match(r"[cC]?(\d+)$", serves)
    if m:
        idx = int(m.group(1)) - 1
        if 0 <= idx < len(claims):
            return claims[idx]
    for cl in claims:
        if serves.lower() in cl.get("text", "").lower():
            return cl
    return None


def _parse_substrate(text: str) -> tuple[str, list[dict]]:
    """Parse a layered graph seed into (title, node dicts).

    Grammar (line-parseable, grown by use):
      ``# Substrate: <title>``
      ``## <id> | <Label> | kind:<k> | source:<s> | link:<loose|linked|closed>``
        a node. ``kind`` defaults to ``cluster`` for the endogenous / exogenous /
        intrinsic roots, else ``node``. ``source`` and ``link`` are optional.
      ``summary: <one line>``
      ``draws: <ref>, <ref>, ...``  the lower nodes this one is fed from (by id or
                                    child handle): the coarse-graining *choice*.
      ``consistency: <ref> | <supports|contradicts> | <note>``  a typed check edge.
      ``- <kind> [#<handle>]: <text> [| link:<loose|...>]``  a child (``contains``).
    """
    title = ""
    nodes: list[dict] = []
    cur: dict | None = None

    def _kv(parts: list[str]) -> dict:
        d: dict = {}
        for p in parts:
            if ":" in p:
                k, v = p.split(":", 1)
                d[k.strip().lower()] = v.strip()
        return d

    roots = {"endogenous", "exogenous", "intrinsic"}
    for raw in text.splitlines():
        s = raw.strip()
        if s.startswith("## "):
            parts = [p.strip() for p in s[3:].split("|")]
            hid = parts[0] or f"n{len(nodes)}"
            kv = _kv(parts[2:])
            cur = {
                "id": hid,
                "label": parts[1] if len(parts) > 1 and parts[1] else hid,
                "kind": kv.get("kind", "cluster" if hid in roots else "node"),
                "source": kv.get("source", ""),
                "link": kv.get("link", "linked"),
                "summary": "", "draws": [], "consistency": [], "children": [],
            }
            nodes.append(cur)
            continue
        if s.startswith("# ") and cur is None:
            title = s[2:].strip()
            continue
        if cur is None:
            continue
        low = s.lower()
        if low.startswith("summary:"):
            cur["summary"] = s.split(":", 1)[1].strip()
            continue
        if low.startswith("draws:"):
            cur["draws"] += [r.strip() for r in s.split(":", 1)[1].split(",") if r.strip()]
            continue
        if low.startswith("consistency:"):
            seg = [p.strip() for p in s.split(":", 1)[1].split("|")]
            if seg and seg[0]:
                rel = seg[1].lower() if len(seg) > 1 else "supports"
                note = seg[2] if len(seg) > 2 else ""
                cur["consistency"].append((seg[0], rel, note))
            continue
        m = re.match(r"-\s*([A-Za-z_][A-Za-z0-9_ ]*?)\s*(?:#([A-Za-z0-9_]+))?\s*:\s*(.+)", s)
        if m:
            rest = m.group(3).strip()
            link = "linked"; chdraws: list[str] = []
            if "|" in rest:
                bits = [t.strip() for t in rest.split("|")]
                rest = bits[0]
                for t in bits[1:]:
                    if t.lower().startswith("link:"):
                        link = t.split(":", 1)[1].strip()
                    elif t.lower().startswith("draws:"):
                        chdraws = [r.strip() for r in t.split(":", 1)[1].split(",") if r.strip()]
            cur["children"].append(
                {"kind": m.group(1).strip().lower(), "handle": m.group(2), "text": rest,
                 "link": link, "draws": chdraws}
            )
    return title, nodes


def _parse_blueprint(text: str) -> tuple[dict, list[dict]]:
    """Parse blueprint.md into (spine dict, ordered section dicts).

    Format (human-readable, line-parseable):
      spine lines before the first section: ``- thesis: ...`` / frame / title / register
      section header:  ``## <id> | <Title> | ring:<core|inner|framing> | status:<...>``
      ``intent: ...``
      ``- claim: <text> | result:<Rk> | status:<...> [| headline]``
      ``- equation: <label> | <latex> | serves:<claim index or substring>``
      ``- figure: <label> | <caption?>``
      ``- cite: <key> | relation:<supports|contests|context>``
    """
    spine: dict = {}
    sections: list[dict] = []
    cur: dict | None = None
    in_sections = False
    for raw in text.splitlines():
        s = raw.strip()
        if s.startswith("## "):
            in_sections = True
            parts = [p.strip() for p in s[3:].split("|")]
            sec: dict = {
                "id": parts[0] or f"s{len(sections)}",
                "title": parts[1] if len(parts) > 1 and parts[1] else parts[0],
                "claims": [], "equations": [], "figures": [], "cites": [], "intent": "",
            }
            for p in parts[2:]:
                if ":" in p:
                    k, v = p.split(":", 1)
                    sec[k.strip().lower()] = v.strip()
            sections.append(sec)
            cur = sec
            continue
        if not in_sections:
            m = re.match(r"-?\s*(thesis|frame|title|register)\s*:\s*(.+)", s, re.I)
            if m:
                spine[m.group(1).lower()] = m.group(2).strip()
            continue
        if cur is None:
            continue
        if s.lower().startswith("intent:"):
            cur["intent"] = s.split(":", 1)[1].strip()
            continue
        m = re.match(r"-\s*(claim|equation|figure|cite)\s*:\s*(.+)", s, re.I)
        if not m:
            continue
        kind, rest = m.group(1).lower(), m.group(2)
        fields = [f.strip() for f in rest.split("|")]
        if kind == "claim":
            cl: dict = {"text": fields[0], "headline": False}
            for f in fields[1:]:
                if f.lower() == "headline":
                    cl["headline"] = True
                elif ":" in f:
                    k, v = f.split(":", 1)
                    cl[k.strip().lower()] = v.strip()
            cur["claims"].append(cl)
        elif kind == "equation":
            eq: dict = {"label": fields[0], "latex": fields[1] if len(fields) > 1 else ""}
            for f in fields[2:]:
                if ":" in f:
                    k, v = f.split(":", 1)
                    eq[k.strip().lower()] = v.strip()
            cur["equations"].append(eq)
        elif kind == "figure":
            cur["figures"].append({"label": fields[0], "caption": fields[1] if len(fields) > 1 else ""})
        elif kind == "cite":
            ct: dict = {"key": fields[0]}
            for f in fields[1:]:
                if ":" in f:
                    k, v = f.split(":", 1)
                    ct[k.strip().lower()] = v.strip()
            cur["cites"].append(ct)
    return spine, sections


def _fitness_map(canon: Canon) -> dict[str, float]:
    """Per-skill fitness from telemetry, defensively. No ledger -> empty map and
    every skill keeps the neutral prior."""
    try:
        from laplace.engine import assess as _assess

        return {name: float(d.get("fitness", 0.5)) for name, d in _assess.assess(canon).items()}
    except Exception:  # noqa: BLE001 - fitness is an enrichment, never a hard dep
        return {}


def _skill_class(n: Node) -> str:
    if n.status == "deprecated":
        return "skill_dead"
    if n.weight >= 0.66:
        return "skill_hot"
    if n.weight >= 0.45:
        return "skill_warm"
    return "skill_cold"


def _canvas_size(n: Node) -> int:
    if n.kind == "domain":
        return 360
    if n.kind == "skill":
        return int(220 + 360 * max(0.0, min(1.0, n.weight)))  # fitness -> size
    if n.kind == "missing":
        return 200
    return 320


def _line_at(body: str, pos: int) -> str:
    start = body.rfind("\n", 0, pos) + 1
    end = body.find("\n", pos)
    if end == -1:
        end = len(body)
    return body[start:end].strip()[:200]


_MID_RE = re.compile(r"[^A-Za-z0-9]")


def _mid(node_id: str) -> str:
    """A Mermaid-safe identifier."""
    return "n_" + _MID_RE.sub("_", node_id)


def _cid(node_id: str) -> str:
    return _MID_RE.sub("_", node_id)


def _esc(s: str) -> str:
    return s.replace('"', "'").replace("\n", " ").replace("|", "/")


def _rgb(hex_colour: str) -> int:
    """Obsidian graph colours are packed 0xRRGGBB integers."""
    return int(hex_colour.lstrip("#"), 16)


# ---------------------------------------------------------------------------
# Top-level API + CLI
# ---------------------------------------------------------------------------

_RENDERERS = ("mermaid", "json", "canvas", "obsidian")


def render(
    fmt: str = "mermaid",
    focus: str | None = None,
    depth: int = 2,
    kinds: list[str] | None = None,
    canon: Canon | None = None,
    manuscript: str | None = None,
    summary: bool = False,
    blueprint: str | None = None,
    substrate: str | None = None,
    corpus: str | None = None,
) -> dict[str, Any]:
    """Build a graph and project it. Source is the canon by default, or a
    manuscript ``.tex``/directory when ``manuscript`` is given - the same
    renderers serve both. Returns the artifact plus a health summary, so a
    caller sees the topology's defects alongside the picture.

    When ``fmt='json'`` and ``summary=True``, the JSON projection uses a
    bounded summary when the graph exceeds the node threshold - safe for large
    manuscripts that would otherwise overflow the MCP token budget.
    """
    if corpus:
        from pathlib import Path

        if not Path(corpus).exists():
            return {"error": f"corpus path not found: {corpus}"}
        g = CanonGraph.from_corpus(corpus)
    elif substrate:
        from pathlib import Path

        if not Path(substrate).exists():
            return {"error": f"substrate path not found: {substrate}"}
        g = CanonGraph.from_substrate(substrate)
    elif blueprint:
        from pathlib import Path

        if not Path(blueprint).exists():
            return {"error": f"blueprint path not found: {blueprint}"}
        g = CanonGraph.from_blueprint(blueprint)
    elif manuscript:
        from pathlib import Path

        if not Path(manuscript).exists():
            return {"error": f"manuscript path not found: {manuscript}"}
        g = CanonGraph.from_manuscript(manuscript)
    else:
        g = CanonGraph.from_canon(canon)
    scoped = g
    if kinds:
        scoped = scoped.filter_kinds(kinds)
    radial = False
    if focus:
        fid = focus if focus in scoped.nodes else _match_node(scoped, focus)
        if fid is None:
            return {"error": f"focus node {focus!r} not found", "closest": _closest(scoped, focus)}
        scoped = scoped.focus(fid, depth)
        radial = True

    if fmt == "mermaid":
        artifact: Any = scoped.to_mermaid()
    elif fmt == "json":
        artifact = scoped.to_json(summary=summary)
    elif fmt == "canvas":
        artifact = scoped.to_canvas(radial=radial)
    elif fmt == "obsidian":
        artifact = scoped.to_obsidian_graph()
    else:
        return {"error": f"unknown format {fmt!r}", "formats": list(_RENDERERS)}

    return {
        "format": fmt,
        "focus": focus,
        "artifact": artifact,
        "health": g.health(),
        "stats": {"nodes": len(scoped.nodes), "edges": len(scoped.edges)},
    }


def _match_node(g: CanonGraph, token: str) -> str | None:
    if token in g.nodes:
        return token
    for prefix in ("skill:", "wiki:", "domain:"):
        if f"{prefix}{token}" in g.nodes:
            return f"{prefix}{token}"
    for nid, n in g.nodes.items():
        if n.label == token:
            return nid
    return None


def _closest(g: CanonGraph, token: str, k: int = 5) -> list[str]:
    t = token.lower()
    scored = sorted(
        ((sum(1 for c in t if c in nid.lower()), nid) for nid in g.nodes),
        reverse=True,
    )
    return [nid for _, nid in scored[:k]]


def _main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="Project the Laplace canon graph.")
    p.add_argument("--format", default="mermaid", choices=_RENDERERS)
    p.add_argument("--focus", default=None, help="centre on a node (id, skill name, or label)")
    p.add_argument("--depth", type=int, default=2)
    p.add_argument("--kinds", default=None, help="comma-separated: wiki,skill,domain (canon) or section,figure,equation,claim,citation (manuscript)")
    p.add_argument("--manuscript", default=None, help="build from a .tex file or directory instead of the canon")
    p.add_argument("--corpus", default=None, help="build from a corpus.bib (the global literature store) instead of the canon")
    p.add_argument("--out", default=None, help="write artifact to a file")
    p.add_argument("--health", action="store_true", help="print only the health report")
    args = p.parse_args(argv)

    if args.health:
        if args.corpus:
            g = CanonGraph.from_corpus(args.corpus)
        elif args.manuscript:
            g = CanonGraph.from_manuscript(args.manuscript)
        else:
            g = CanonGraph.from_canon()
        print(json.dumps(g.health(), indent=2))
        return 0

    kinds = args.kinds.split(",") if args.kinds else None
    res = render(args.format, args.focus, args.depth, kinds,
                 manuscript=args.manuscript, corpus=args.corpus)
    if "error" in res:
        print(json.dumps(res, indent=2))
        return 1
    artifact = res["artifact"]
    text = artifact if isinstance(artifact, str) else json.dumps(artifact, indent=2)
    if args.out:
        from pathlib import Path

        Path(args.out).write_text(text, encoding="utf-8")
        h = res["health"]
        print(f"wrote {args.format} to {args.out}  ({res['stats']['nodes']} nodes, "
              f"{res['stats']['edges']} edges, {len(h['dangling'])} dangling, "
              f"{len(h['orphans'])} orphans)")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
