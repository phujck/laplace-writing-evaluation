"""The verify third of the loop: consistency ledgers.

Structured, in-process checks that mirror the legacy mccaul-protocol scripts
(epistemic_ledger, latex_forge lint, global_weaver) so they return a
machine-readable mismatch report - and, crucially, a boolean ``passed`` per
check, which is the outcome signal the fitness assessment consumes.

``run_backing`` separately invokes a skill's original script as a subprocess for
its full human artifact (e.g. epistemic_graph.md, a compiled PDF).
"""

from __future__ import annotations
from laplace.core.checkout import source_tree

import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from laplace.engine import telemetry
from laplace.pipeline.canon import Canon, get_canon

# Which verify check attributes its pass/fail to which skill (the fitness signal).
CHECK_SKILL = {
    "epistemic": "epistemic_ledger",
    "voice": "orchestrated_generation",
    "crossref": "global_weaver",
    "empirical": "empirical_ledger",
    "canon": "canon_weaver",
    "connectivity": "conceptric_coherence",
    "projection_labels": "conceptric_coherence",
    "glossary": "conceptric_coherence",
    "substrate": "literature_scout",
    "figures": "figure_standard",
    "conceptric_build": "conceptric_coherence",
    "meta_leak": "orchestrated_generation",
    "evolution": "conceptric_evolution",
    "contracts": "orchestrated_generation",
}


def read_safe(path: str | Path) -> str:
    """UTF-8 with a UTF-16 fallback (PowerShell artifacts), mirroring the legacy."""
    p = Path(path)
    try:
        return p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return p.read_text(encoding="utf-16")


# ---------------------------------------------------------------------------
# epistemic: orphaned equations + naked claims  (mirrors map_derivations.py)
# ---------------------------------------------------------------------------


def check_epistemic(text: str) -> dict[str, Any]:
    # An equation label is ``eq:`` OR a semantic epistemic prefix (def:/res:/irf:/
    # thm: - the convention SSG numbers its ~90 equations with, and zero ``eq:``).
    # The prefix set is graph.py's, so verify and the conceptric key identically;
    # the whole label (prefix included) is the orphan id, never rewritten.
    from laplace.pipeline.graph import EQ_LABEL_PREFIXES

    pfx = "(?:" + "|".join(re.escape(p) for p in EQ_LABEL_PREFIXES) + ")"
    labels = re.findall(r"\\label\{(" + pfx + r"[^}]+)\}", text)
    # Count every cross-reference command, not just \ref (manuscripts use \eqref).
    refs = re.findall(r"\\(?:ref|eqref|autoref|cref|Cref)\{(" + pfx + r"[^}]+)\}", text)
    orphans = sorted(set(labels) - set(refs))

    sections = re.split(r"\\section\{([^}]+)\}", text)
    naked: list[str] = []
    if len(sections) > 1:
        for i in range(1, len(sections), 2):
            name = sections[i]
            body = re.sub(r"%.*?$", "", sections[i + 1], flags=re.MULTILINE)
            has_math = re.search(r"\$|\\\[|\\begin\{equation\}|\\(?:eq|auto|c|C)?ref\{" + pfx, body)
            if len(body.split()) > 150 and not has_math:
                naked.append(name)

    return {
        "pass": not orphans and not naked,
        "orphans": orphans,
        "naked_claims": naked,
    }


# ---------------------------------------------------------------------------
# voice: the §11.5 failure-pattern DETECTOR + typography mechanics
# (2026-07-09 rebuild: the register-ban lint — Americanisms, slop vocabulary —
# is retired root-and-branch; a blacklist breeds synonyms, mandate §1.10. What
# runs here post-render is structural: the catalogued failure classes in
# schema.VOICE_FAILURE_PATTERNS, the profile's punctuation surface invariants,
# and the surviving TikZ/layout mechanics owned by latex_forge's typography
# half. Spelling-standard conformance is the weld's job with the profile in
# hand, never a word-list.)
# ---------------------------------------------------------------------------

_TIKZ_BANS = {
    r"\[red\]": "[red!80!black]",
    r"\[blue\]": "[blue!80!black]",
    r"\[green\]": "[green!80!black]",
    r"\[yellow\]": "[yellow!80!black]",
    r"\boutput/.style\b": "finalnode/.style (output is a reserved TikZ keyword)",
    r"\bstyle\s*=\s*output\b": "style=finalnode (output is reserved)",
    r"\[output\]": "[finalnode] (output is reserved)",
}


# Math regions carry syntax punctuation (`;`, `--`) the surface-invariant
# detector must NOT read as prose. Mask inline/same-line math; multi-line
# display math is tracked as state below (mirrors the TikZ carve-out).
# (Fix, 2026-07-09: the weld deleted the `;` inside `$(a_1\dots a_n; T)$`.)
_MATH_DISPLAY_INLINE = re.compile(r"(?<!\\)\$\$.*?\$\$|\\\[.*?\\\]")
_MATH_INLINE = re.compile(r"(?<!\\)\$[^$\n]+\$")
_MATH_TEX_INLINE = re.compile(r"\\\([^\n]*?\\\)")
_MATH_ENV_OPEN = re.compile(r"\\begin\{(equation|align|gather|multline|eqnarray|flalign|displaymath)\*?\}")
_MATH_ENV_CLOSE = re.compile(r"\\end\{(equation|align|gather|multline|eqnarray|flalign|displaymath)\*?\}")


def _mask_math(line: str) -> str:
    """Blank inline/same-line math (length-preserving) so its syntax punctuation
    is not read as prose by the surface-invariant detector."""
    line = _MATH_DISPLAY_INLINE.sub(lambda m: " " * len(m.group()), line)
    line = _MATH_INLINE.sub(lambda m: " " * len(m.group()), line)
    line = _MATH_TEX_INLINE.sub(lambda m: " " * len(m.group()), line)
    return line


def check_voice(text: str) -> dict[str, Any]:
    """Post-render detector: §11.5 voice-failure classes + typography mechanics.
    A hit is a boundary flag routed to the owning layer — never a new
    instruction into any generation prompt."""
    from laplace.pipeline import schema as _ps
    flags: list[dict[str, Any]] = []
    in_figure_star = False
    in_tikz = False
    in_math_env = False
    in_bracket_math = False
    lines = text.splitlines()
    in_frontmatter = bool(lines and lines[0].strip() == "---")
    in_fenced_code = False

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if in_frontmatter:
            if i > 1 and stripped == "---":
                in_frontmatter = False
            continue
        if stripped.startswith("```"):
            in_fenced_code = not in_fenced_code
            continue
        if in_fenced_code:
            continue
        if re.match(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$", line):
            continue
        if re.match(r"^(-{3,}|\*{3,}|_{3,})$", stripped):
            continue

        if r"\begin{figure*}" in line:
            in_figure_star = True
        elif r"\end{figure*}" in line:
            in_figure_star = False
        if r"\begin{tikzpicture}" in line or r"\begin{axis}" in line:
            in_tikz = True
        elif r"\end{tikzpicture}" in line or r"\end{axis}" in line:
            in_tikz = False
        if _MATH_ENV_OPEN.search(line):
            in_math_env = True
        elif _MATH_ENV_CLOSE.search(line):
            in_math_env = False
        if r"\[" in line and r"\]" not in line:
            in_bracket_math = True
        elif r"\]" in line:
            in_bracket_math = False

        if in_figure_star and r"\linewidth" in line and r"\includegraphics" in line:
            flags.append({"line": i, "kind": "layout", "message": r"\linewidth in figure* stretches single-column figures; use \columnwidth."})

        if in_tikz:
            if re.search(r"[xy]label\s*=\s*\{?\s*\$?[xyz]\$?\s*\}?(?=[,\]\s]|$)", line, re.I):
                flags.append({"line": i, "kind": "variable", "message": "Generic TikZ axis label (x/y/z); match manuscript symbols."})
            if re.search(r"\\node[^;]*\{\s*\$?[xyz]\$?\s*\}\s*;", line, re.I):
                flags.append({"line": i, "kind": "variable", "message": "Generic TikZ node variable (x/y/z); match manuscript symbols."})

        for pat, repl in _TIKZ_BANS.items():
            if re.search(pat, line, re.I):
                flags.append({"line": i, "kind": "tikz_colour", "message": f"Use Nature-style colour: {repl}."})
        for cls, pats in _ps.VOICE_FAILURE_PATTERNS.items():
            if cls == "surface-invariant":
                # inside multi-line display math the punctuation is syntax; skip.
                if in_math_env or in_bracket_math:
                    continue
                scan = _mask_math(line)  # blank inline math first
            else:
                scan = line
            re_flags = 0 if cls == "surface-invariant" else re.I
            for pat in pats:
                if re.search(pat, scan, re_flags):
                    if cls == "surface-invariant":
                        # TikZ carve-outs: a statement-terminating ; in TikZ
                        # code, and -- inside ranges or draw paths, are syntax.
                        if scan.strip().endswith(";") and ("\\" in line or "(" in line or "tikz" in line.lower()):
                            continue
                        if "--" in scan and (re.search(r"\d--\d", scan) or any(
                                c in line for c in (r"\draw", r"\path", r"\node", r"\fill"))):
                            continue
                    flags.append({"line": i, "kind": cls,
                                  "message": f"voice failure pattern ({cls}): {pat!r}"})
                    break  # one flag per class per line keeps reports readable

    return {"pass": not flags, "violations": flags, "count": len(flags)}


# ---------------------------------------------------------------------------
# crossref: broken refs + duplicate labels  (mirrors weave_orchestra.py)
# ---------------------------------------------------------------------------


def check_crossref(target: str | Path) -> dict[str, Any]:
    """Broken refs + duplicate labels across a manuscript's true reading order.

    Shares the conceptric's manuscript gatherer
    (``graph.gather_manuscript_files``) so verification and graphing read the
    *same* files in the *same* ``\\input`` order. A single root ``.tex`` is no
    longer checked in isolation, blind to the sections it pulls in - one
    artifact, one reading order. Comments are stripped, so a commented-out
    ``\\label`` no longer counts.
    """
    from laplace.pipeline.graph import gather_manuscript_files

    global_labels: dict[str, list[str]] = {}
    references_map: dict[str, list[str]] = {}
    for fp, content in gather_manuscript_files(target):
        name = fp.name
        for lbl in re.findall(r"\\label\{([^}]+)\}", content):
            global_labels.setdefault(lbl, []).append(name)
        references_map.setdefault(name, []).extend(
            re.findall(r"\\(?:ref|eqref|autoref|cref|Cref)\{([^}]+)\}", content)
        )

    broken = [
        {"file": fn, "ref": ref}
        for fn, refs in references_map.items()
        for ref in refs
        if ref not in global_labels
    ]
    duplicates = {lbl: files for lbl, files in global_labels.items() if len(files) > 1}
    return {"pass": not broken and not duplicates, "broken_refs": broken, "duplicate_labels": duplicates}


# ---------------------------------------------------------------------------
# canon: the engine's own consistency  (the contradicts guard, with teeth)
# ---------------------------------------------------------------------------


def _resolve_canon_node(graph, focus: str) -> str | None:
    """Map a focus string to a canon node id: exact id, last path segment, suffix, then label."""
    if focus in graph.nodes:
        return focus
    for nid in graph.nodes:
        if nid.rsplit("/", 1)[-1] == focus or nid.endswith(focus):
            return nid
    for nid, n in graph.nodes.items():
        if getattr(n, "label", None) == focus:
            return nid
    return None


def _health_report(h: dict[str, Any]) -> dict[str, Any]:
    return {
        "pass": h["pass"],
        "contradictions": h["contradictions"],
        "dangling": h["dangling"],
        "dead_wood_linked": h["dead_wood_linked"],
        "orphans": h["orphans"],
        "frontier": h["frontier"],
        "ancestral_count": len(h["ancestral"]),
    }


def check_canon(
    canon: Canon, focus: str | list[str] | None = None, depth: int = 1
) -> dict[str, Any]:
    """Run the canon graph's health as a verify check - whole-graph, or scoped to a grade.

    The verify third of the loop, turned on the engine itself: dangling links,
    deprecated-but-linked skills, and typed ``contradicts`` edges are the
    inconsistencies that fail it. ``ancestral`` is reported (the inherited
    baseline to audit on conflict) but is not itself a failure - closure is
    provenance, not completion, so an accountable node never fails the guard for
    being old.

    ``focus`` makes this **verify-at-grade**: instead of grinding the whole canon
    (which grows with the conceptric, so a global verify on every close scales
    badly), it inspects only the BFS neighbourhood (``depth``, default 1 = the node
    and its siblings) of the changed node(s). A focus that resolves to no canon node
    - a session that touched only trace files, say - **skips** the check rather than
    re-verifying a canon it did not touch. The conjugate of the graded hello: open
    and close both work at their grade, aware only of it and its siblings.
    """
    from laplace.pipeline.graph import CanonGraph

    graph = CanonGraph.from_canon(canon)
    if focus is None:
        return _health_report(graph.health())

    foci = [focus] if isinstance(focus, str) else list(focus)
    resolved = [nid for f in foci if (nid := _resolve_canon_node(graph, f))]
    scope = {"focus": foci, "resolved": resolved, "depth": depth}
    if not resolved:
        return {
            "pass": True,
            "contradictions": [], "dangling": [], "dead_wood_linked": [],
            "orphans": [], "frontier": {"loose": [], "unsourced": []},
            "ancestral_count": 0, "scope": scope,
            "note": "no canon nodes in scope - whole-canon verify skipped (verify at grade, not the whole graph)",
        }
    keep: dict[str, Any] = {}
    for nid in resolved:
        keep.update(graph.focus(nid, depth=depth).nodes)
    sub = CanonGraph(nodes=keep, edges=[e for e in graph.edges if e.src in keep and e.dst in keep])
    return {**_health_report(sub.health()), "scope": scope}


# ---------------------------------------------------------------------------
# citations: the exogenous-substrate surfacing rule
# ---------------------------------------------------------------------------

_ARXIV_RE = re.compile(r"arxiv[:\s]*([0-9]{4}\.[0-9]{4,5})", re.IGNORECASE)
_DOI_RE = re.compile(r"(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)")


def _ids(fields: dict) -> set[str]:
    """The stable external ids of a bib record - arXiv id and DOI - lowercased.
    These survive the citekey differences between a per-project ``refs.bib`` and
    the global ``corpus.bib``, so a reference can be matched across the two."""
    blob = " ".join(str(fields.get(k, "")) for k in ("note", "doi", "eprint", "url"))
    ids = {m.group(1).lower() for m in _ARXIV_RE.finditer(blob)}
    ids |= {m.group(1).lower().rstrip(".") for m in _DOI_RE.finditer(blob)}
    return ids


def check_corpus_citations(
    target: str | Path, corpus_path: str | Path, project: str
) -> dict[str, Any]:
    """Surface the exogenous knowledge a manuscript relies on but fails to cite.

    The engine's standing weakness is leaning on a fact without referencing it.
    This is the guard: the corpus records which references a *project* draws on
    (their ``provenance``), so every such reference must appear as a ``\\cite`` in
    that project's manuscript. References are matched across the per-project
    ``refs.bib`` and the global ``corpus.bib`` by their stable arXiv id / DOI, not
    by citekey, so the differing key schemes never hide an uncited reliance.

    A reference the project relies on that is either absent from the manuscript
    bibliography, or present but never ``\\cite``d in the body, is a *naked
    reliance* - reported and failing. The check is the verify-stage enforcement of
    ``canon://workflow/citation_discipline``.
    """
    from laplace.pipeline.graph import _parse_bib, _CITE_RE, gather_manuscript_files

    target = Path(target)
    body = "\n".join(content for _fp, content in gather_manuscript_files(target))
    cited_keys: set[str] = set()
    for m in _CITE_RE.finditer(body):
        cited_keys |= {k.strip() for k in m.group(1).split(",") if k.strip()}

    # The manuscript's own bibliography: map each stable id to its citekey, so a
    # corpus reference can be resolved to the key the prose actually cites.
    bib_dir = target if target.is_dir() else target.parent
    id_to_bibkey: dict[str, str] = {}
    all_bibkeys: set[str] = set()
    for bibf in sorted(bib_dir.glob("*.bib")):
        for bibkey, fields in _parse_bib(read_safe(bibf)):
            all_bibkeys.add(bibkey)
            for i in _ids(fields):
                id_to_bibkey.setdefault(i, bibkey)

    relied, surfaced, naked = [], [], []
    for key, fields in _parse_bib(read_safe(Path(corpus_path))):
        provs = {p.strip() for p in (fields.get("provenance") or "").split(",") if p.strip()}
        if project not in provs:
            continue
        relied.append(key)
        bibkey = next((id_to_bibkey[i] for i in _ids(fields) if i in id_to_bibkey), None)
        if bibkey is None and not _ids(fields) and key in all_bibkeys:
            # Id-less records (books, tech reports carry no arXiv/DOI): the stable-id
            # join cannot see them, so fall back to citekey identity with the
            # manuscript's own bibliography.
            bibkey = key
        if bibkey and bibkey in cited_keys:
            surfaced.append(key)
        else:
            naked.append({"ref": key, "claim": fields.get("claim", ""),
                          "in_bib": bool(bibkey), "bibkey": bibkey})
    return {
        "pass": not naked,
        "project": project,
        "relied_on": len(relied),
        "surfaced": len(surfaced),
        "naked_reliances": naked,
    }


# ---------------------------------------------------------------------------
# connectivity + projection_labels: the build-completion gates
# ---------------------------------------------------------------------------
#
# See canon://skills/conceptric_coherence, the four-gate build-completion contract.
# The projector descends from the spine down through ``deps``; a node the spine cannot
# reach is a node the projector never emits (a silent hole earlier gates do not catch).
# The projector then emits stable ``\label{}``/``\ref{}``/``\cite{}`` from each node's
# projection slot; a labelable node without ``projection.latex_label`` forces the
# projector to invent one (confabulation) or refuse (silent miss). Both are minted at
# node-creation, checked here, and never re-derived downstream.

_LABELABLE_PREFIXES = ("fig:", "eq:", "thm:", "def:", "ref:")


def _load_corpus_network(
    corpus_name: str, root: str | Path | None = None, workspace: str | Path | None = None
) -> tuple[dict, str] | tuple[None, str]:
    """Resolve a corpus name to (network, note) or (None, why-we-skip).

    ``root`` (additive; default None preserves today's behaviour) overrides ONLY
    the friction-ledger OVERLAY source, never the tex tree. An evolution mutates
    the L1 friction ledger, not the corpus tex, so gating a POST-evolution state
    means reading the tex from the real repo while reading the rewiring overlay
    from the rehearsal root the evolution wrote — the B10 apply-gate path. The
    corpus network caches on (tex_root, overlay-length, sem-stamp), so a longer
    evolved overlay is a distinct cache entry: base and rehearsal never collide.

    ``workspace`` (standalone boundary, 2026-10-20) is the other, explicit case: the
    caller's whole workspace (its registry, tex tree AND overlay), the root a Writing
    project lives in. The authoring context reads its glossary there, so an installed
    package serving an explicit workspace resolves the project's own corpus instead of
    the serving checkout's registry. ``workspace`` and ``root`` are never combined.
    """
    from laplace.research import corpus_ingest as _ci
    from laplace.core.checkout import repo_root as _repo_root   # the serving checkout, not the HTTP server

    if workspace is not None:
        if root is not None:
            raise ValueError("_load_corpus_network takes either workspace (whole) or root (overlay only)")
        ws = Path(workspace)
        troot = _ci.resolve_corpus(ws, corpus_name)
        if not troot:
            return None, (f"corpus {corpus_name!r} not in the workspace registry at {ws} "
                          f"(or no main.tex at its tex root)")
        return _ci.corpus_network(troot, repo_root=ws, name=corpus_name), ""
    rr = _repo_root()
    troot = _ci.resolve_corpus(rr, corpus_name)
    if not troot:
        return None, (f"corpus {corpus_name!r} not in the registry roster "
                      f"(or no main.tex at its tex root)")
    overlay_root = Path(root) if root is not None else rr
    return _ci.corpus_network(troot, repo_root=overlay_root, name=corpus_name), ""


def _strip_conf(x: Any) -> Any:
    """edge_index rows carry ``confirmed::``/``tentative::`` prefixes on some ids."""
    if isinstance(x, str):
        return x.replace("confirmed::", "").replace("tentative::", "")
    return x


#: The two synthetic container kinds ``corpus_ingest.atomise_paper`` mints above the
#: spine: the paper apex and the bibliography shell. They contain the spine; nothing in
#: the spine descends to them, so the reachability demand does not apply.
_STRUCTURAL_CONTAINER_KINDS = frozenset({"paper", "references"})


def _is_structural_container(nid: str, node: dict[str, Any]) -> bool:
    """True for the corpus apex (``paper://``) and the bibliography shell (``references``).

    Matched on the minting contract, not on the id string alone: apex = kind ``paper``
    with no parent; bibliography = kind ``references``. A content node that merely
    happens to be named ``references`` but carries another kind is NOT exempt.
    """
    kind = node.get("kind")
    if kind not in _STRUCTURAL_CONTAINER_KINDS:
        return False
    return kind == "references" or node.get("parent") is None


def check_connectivity(corpus_name: str,
                       root: str | Path | None = None) -> dict[str, Any]:
    """Every node in the corpus reachable from ≥1 spine beat via ``edge_index``.

    An orphan under this gate is a node no spine beat can descend to - so it never
    appears in the projection, however coherent it is locally. Compare with
    ``canon_weaver``'s topology check (which catches raw dangling edges) and the
    ``conceptric_coherence`` renormalisation audit (which catches under-described coarse
    nodes): connectivity is the third mode, orthogonal to both.

    ``root`` (additive) gates a POST-evolution state: the overlay is read from
    that rehearsal root instead of the live repo (see ``_load_corpus_network``).

    STRUCTURAL EXEMPTION (2026-08-21). ``corpus_ingest.atomise_paper`` mints two
    synthetic container nodes that are ANCESTORS of the spine, not its descendants:
    the apex ``paper://`` (parent ``None``, kind ``paper``) and the bibliography shell
    ``references``. Demanding that a spine beat reach its own container is a category
    error - reachability there is undefined, and any corpus that satisfied it did so by
    accident (``subset-sum-itqde`` passed only because one hand-authored node happens to
    carry an edge up to ``paper://``). They are exempted and reported under
    ``structural_exempt``; ``pass`` stays exact over the content nodes - a real orphan
    still refuses, which is what the WIRED bar consumes. ``ratio`` reports the
    reachable-content fraction as a first-class field for gauges that want the degree
    rather than the verdict.
    """
    net, note = _load_corpus_network(corpus_name, root)
    if net is None:
        return {"pass": None, "manual": True, "note": note}

    nodes = net["nodes"]
    spine = [b["id"] for b in net["spine"]]
    ei = net["edge_index"]

    # Virtual reverse-edges from ``projection.section_ref``: a fig/eq/thm node that
    # declares ``section_ref: <beat-id>`` is asserting "this beat consumes me". Fold
    # those into the traversal so a minted projection slot doubles as a structural
    # connectivity edge - locality wins: the label lives with the node it labels, and
    # the graph knows about it without a separate edge author-pass.
    section_ref_children: dict[str, list[str]] = {}
    for nid, node in nodes.items():
        proj = node.get("projection") or (node.get("meta") or {}).get("projection") or {}
        section_ref = proj.get("section_ref")
        if section_ref and section_ref in nodes:
            section_ref_children.setdefault(section_ref, []).append(nid)

    reachable: set[str] = set()
    frontier = list(spine)
    while frontier:
        n = frontier.pop()
        if n in reachable:
            continue
        reachable.add(n)
        for nb in ei.get(n, []):
            nb = _strip_conf(nb)
            if nb not in reachable and nb in nodes:
                frontier.append(nb)
        for child in section_ref_children.get(n, []):
            if child not in reachable:
                frontier.append(child)

    exempt = {nid for nid, node in nodes.items() if _is_structural_container(nid, node)}
    content = set(nodes) - exempt
    orphans = sorted(content - reachable)
    from collections import Counter
    kinds = dict(Counter(nodes[o].get("kind", "?") for o in orphans))
    return {
        "pass": not orphans,
        "corpus": corpus_name,
        "total_nodes": len(nodes),
        "spine_size": len(spine),
        "reachable_from_spine": len(reachable),
        "structural_exempt": sorted(exempt),
        "content_nodes": len(content),
        "reachable_content": len(content & reachable),
        "ratio": round(len(content & reachable) / len(content), 4) if content else 1.0,
        "orphans": orphans,
        "orphan_kinds": kinds,
    }


def check_projection_labels(corpus_name: str,
                            root: str | Path | None = None) -> dict[str, Any]:
    """Every ``fig:``/``eq:``/``thm:``/``def:``/``ref:`` node carries ``projection.latex_label``.

    Labelable node ids in the conceptric are internal (``fig:f4-within-window``); the
    manuscript's LaTeX carries the emit-time label (``\\label{fig:within-window}``). This
    gate enforces that the emit-time slot is minted at node-creation, so the projector
    walks the spine and every ``\\ref``/``\\cite`` resolves without downstream invention.
    Experiment-result figures also need ``projection.data_source`` (the CSV path) so the
    figure's claim is explicable from the substrate, not the caption alone.

    ``root`` (additive) gates a POST-evolution state (see ``_load_corpus_network``).
    """
    net, note = _load_corpus_network(corpus_name, root)
    if net is None:
        return {"pass": None, "manual": True, "note": note}

    nodes = net["nodes"]
    labelable = [nid for nid in nodes if any(nid.startswith(p) for p in _LABELABLE_PREFIXES)]

    missing_label: list[str] = []
    missing_data_source: list[str] = []
    for nid in labelable:
        node = nodes[nid]
        # Frontmatter may land on the node directly or under ``meta``.
        proj = node.get("projection") or (node.get("meta") or {}).get("projection") or {}
        if not proj.get("latex_label"):
            missing_label.append(nid)
        # Experiment-result figures (``fig:exp-*``) additionally need a data_source
        # so the render is checkable against the CSV that produced it.
        if nid.startswith("fig:exp-") and not proj.get("data_source"):
            missing_data_source.append(nid)

    return {
        "pass": not missing_label and not missing_data_source,
        "corpus": corpus_name,
        "labelable_nodes": len(labelable),
        "missing_latex_label": missing_label,
        "missing_data_source": missing_data_source,
    }


_GLOSSARY_STOP = frozenset(
    """the a an of in on at to for with and or is are be as by from into under over its it this
    that which where when there their we our one two three per not no any all every each both
    same other new own must can may without between across within via rather than here role
    data csv row column source output figure panel col double single evidence experiment""".split()
)


def _norm_term(t: str) -> str:
    """Case/hyphen/trailing-plural fold so 'Overlap Families' == 'overlap-family'."""
    t = re.sub(r"[\s\-]+", " ", t.strip().lower())
    t = re.sub(r"ies\b", "y", t)
    return re.sub(r"s\b", "", t)


def deprecated_vocabulary(corpus_name: str,
                          root: str | Path | None = None) -> dict[str, str]:
    """The retired-vocabulary map for a corpus: every ``def:`` node's
    ``projection.deprecated_aliases``, each normalised (``_norm_term``) to the id of
    the def that owns the canonical term. This is the one source of the deprecated-
    alias set — ``check_glossary`` uses it for its deprecated-usage gate, and
    ``scaffold_wipe.check_legacy_terms`` imports it to catch a retired term surviving
    in RENDERED prose (so both read one definition, never two). Returns ``{}`` when
    the corpus network is absent (an unregistered corpus is not a failure here). The
    corpus network is cached, so this is cheap to call alongside ``check_glossary``.
    ``root`` (additive) reads the deprecated set off a POST-evolution overlay."""
    net, _ = _load_corpus_network(corpus_name, root)
    if net is None:
        return {}
    dep: dict[str, str] = {}
    for nid, nd in net["nodes"].items():
        if not nid.startswith("def:"):
            continue
        proj = nd.get("projection") or (nd.get("meta") or {}).get("projection") or {}
        for t in proj.get("deprecated_aliases") or []:
            k = _norm_term(t)
            if k:
                dep[k] = nid
    return dep


def check_glossary(corpus_name: str,
                   root: str | Path | None = None) -> dict[str, Any]:
    """Terminology locked at the conceptric level: the ``def:`` nodes ARE the registry.

    Three defect classes, two fatal one advisory:
    - **coverage** (fatal): every ``def:`` node carries ``projection.term`` — a def without
      a declared term of art cannot anchor usage.
    - **collisions** (fatal): no two defs claim the same term or alias — the
      invent-and-reinvent failure, caught structurally.
    - **deprecated usage** (fatal): a term marked ``deprecated_aliases`` on any def appearing
      in any OTHER node's essence — retired vocabulary (e.g. 'visibility lift' post-F32)
      cannot silently persist.
    - **naked terms** (advisory): recurring multi-word phrases across essences matching no
      def's term/alias — surfaced at every verify, never failing it (the detector is noisy;
      minting is judgement).

    The gate is deliberately lexical — no embedding at verify time (fold-time intelligence,
    render-time mechanics). GLOSSARY.md renders FROM this registry (scripts/render_glossary.py),
    so the doc can never drift from the conceptric.

    ``root`` (additive) gates a POST-evolution state (see ``_load_corpus_network``).
    """
    net, note = _load_corpus_network(corpus_name, root)
    if net is None:
        return {"pass": None, "manual": True, "note": note}
    nodes = net["nodes"]

    def proj_of(nd: dict) -> dict:
        return nd.get("projection") or (nd.get("meta") or {}).get("projection") or {}

    defs = {nid: nd for nid, nd in nodes.items() if nid.startswith("def:")}
    missing_term = [nid for nid, nd in sorted(defs.items()) if not proj_of(nd).get("term")]

    claims: dict[str, list[str]] = {}
    for nid, nd in defs.items():
        p = proj_of(nd)
        for t in [p.get("term") or ""] + list(p.get("aliases") or []):
            if t:
                claims.setdefault(_norm_term(t), []).append(nid)
    # the deprecated-alias -> owning-def map is the ONE public accessor, shared with
    # scaffold_wipe.check_legacy_terms (corpus_network is cached, so this is cheap).
    deprecated = deprecated_vocabulary(corpus_name, root)
    collisions = {t: sorted(owners) for t, owners in claims.items() if len(set(owners)) > 1}

    # Node-id references (thm:conditional-visibility-lift) are provenance, not usage -
    # strip them before matching so only PROSE use of a retired term trips the gate.
    _id_re = re.compile(r"\b(?:def|irf|res|thm|ds|fig|ref|sup|goal|fork|flag|eq):[A-Za-z0-9_\-]+")
    deprecated_hits: list[dict[str, str]] = []
    for nid, nd in nodes.items():
        # Soft-retired nodes are provenance: their historical vocabulary stays as written.
        if proj_of(nd).get("retired"):
            continue
        ess = _norm_term(_id_re.sub(" ", nd.get("essence") or ""))
        for dep, owner in deprecated.items():
            if nid != owner and dep and dep in ess:
                deprecated_hits.append({"node": nid, "deprecated": dep, "canonical_def": owner})

    # advisory naked-term detector: 2-3 gram recurrence across essences, uncovered
    covered = set(claims) | set(deprecated)
    gram_nodes: dict[str, set] = {}
    for nid, nd in nodes.items():
        ess = re.sub(r"\$[^$]*\$", " ", (nd.get("essence") or "").lower())
        words = [w for w in re.findall(r"[a-z][a-z0-9\-]+", ess) if len(w) > 2]
        for n in (2, 3):
            for i in range(len(words) - n + 1):
                g = words[i:i + n]
                if g[0] in _GLOSSARY_STOP or g[-1] in _GLOSSARY_STOP:
                    continue
                key = _norm_term(" ".join(g))
                if key in covered or any(key in c or c in key for c in covered):
                    continue
                gram_nodes.setdefault(key, set()).add(nid)
    naked = sorted(((len(v), g) for g, v in gram_nodes.items() if len(v) >= 6), reverse=True)

    return {
        "pass": not missing_term and not collisions and not deprecated_hits,
        "corpus": corpus_name,
        "defs": len(defs),
        "terms_claimed": len(claims),
        "missing_term": missing_term,
        "collisions": collisions,
        "deprecated_hits": deprecated_hits,
        "advisory_naked_terms": [g for _, g in naked[:15]],
    }


def check_figures(corpus_name: str,
                  root: str | Path | None = None) -> dict[str, Any]:
    """Every ``fig:`` node carries a stranger-reproducible provenance block.

    ``projection.provenance`` must declare its ``kind`` ('data' | 'schematic') and:
    - data figures: ``data_files`` (the CSVs), ``engine`` (the script that produced
      them), ``banked_commit`` (the git sha that banked each data file), and a
      ``reproduce`` recipe - everything a stranger needs to regenerate the numbers.
    - schematic figures: ``generator`` and a ``reproduce`` note.
    The figure's WHAT-and-HOW lives in the node essence (enforced non-empty here).

    ``root`` (additive) gates a POST-evolution state (see ``_load_corpus_network``).
    """
    net, note = _load_corpus_network(corpus_name, root)
    if net is None:
        return {"pass": None, "manual": True, "note": note}
    nodes = net["nodes"]
    defects: list[dict[str, str]] = []
    figs = [nid for nid in sorted(nodes) if nid.startswith("fig:")]
    for nid in figs:
        nd = nodes[nid]
        proj = nd.get("projection") or (nd.get("meta") or {}).get("projection") or {}
        prov = proj.get("provenance") or {}
        if not (nd.get("essence") or "").strip():
            defects.append({"node": nid, "missing": "essence (what/how)"})
        if not prov:
            defects.append({"node": nid, "missing": "provenance block"})
            continue
        kind = prov.get("kind")
        if kind not in ("data", "schematic"):
            defects.append({"node": nid, "missing": "provenance.kind"})
        if not prov.get("reproduce"):
            defects.append({"node": nid, "missing": "provenance.reproduce"})
        if kind == "data":
            for field in ("engine",):
                if not prov.get(field):
                    defects.append({"node": nid, "missing": f"provenance.{field}"})
        if kind == "schematic" and not prov.get("generator"):
            defects.append({"node": nid, "missing": "provenance.generator"})
    return {"pass": not defects, "corpus": corpus_name,
            "figure_nodes": len(figs), "defects": defects}


def check_substrate(corpus_name: str,
                    root: str | Path | None = None) -> dict[str, Any]:
    """Every claim-bearing node (``res:``/``thm:``/``goal:``) reaches literature
    (``ref:``/``sup:``) within 2 outgoing hops of the edge graph.

    The substrate rule: nothing is assumed - a result either carries its own measured
    evidence (data_source) AND sits inside a scaffold of verified references, or it is
    not projectable. Two hops, not one, because the corpus convention routes many
    citations through role nodes (``sup:*-role``) and intermediate IRFs; more than two
    and the scaffold stops being the node's own. Data files are NOT literature - a
    CSV proves the number, a reference positions the claim.

    ``root`` (additive) gates a POST-evolution state (see ``_load_corpus_network``).
    """
    net, note = _load_corpus_network(corpus_name, root)
    if net is None:
        return {"pass": None, "manual": True, "note": note}
    nodes, ei = net["nodes"], net["edge_index"]

    def lit_within(nid: str, depth: int = 2) -> str | None:
        seen, frontier = {nid}, [nid]
        for _ in range(depth):
            nxt = []
            for n in frontier:
                for t in ei.get(n, []):
                    t = _strip_conf(t)
                    if t in nodes and t not in seen:
                        if t.startswith(("ref:", "sup:")):
                            return t
                        seen.add(t)
                        nxt.append(t)
            frontier = nxt
        return None

    targets = [nid for nid in sorted(nodes) if nid.startswith(("res:", "thm:", "goal:"))]
    unscaffolded = [nid for nid in targets if lit_within(nid) is None]
    return {
        "pass": not unscaffolded,
        "corpus": corpus_name,
        "claim_nodes": len(targets),
        "unscaffolded": unscaffolded,
    }


# ---------------------------------------------------------------------------
# topology + coherence: the two graph-health gates of the seven, computed on the
# friction-ledger corpus network (the object an evolution mutates)
# ---------------------------------------------------------------------------
#
# The build-completion contract's first two gates (canon://operations/gate_registry)
# are OWNED by canon_weaver's topology check and the conceptric_coherence
# renormalisation audit. Those instruments run on the CanonGraph markdown
# projection (substrate.md + blueprint.md) — an object an *evolution* never
# touches. An evolution rewires the L1 friction ledger, so to gate a POST-
# evolution apply the same two failure modes are computed here directly on the
# friction-ledger corpus network, to the registry's definitions:
#   topology  — zero dangling links, one connected component
#   coherence — no under-described coarse node (a res:/thm:/goal: shell drawing
#               from nothing below it is content-free — the renormalisation
#               "merge the content-free" failure)
# Container leaves (paper://, references, sections) are structure, not conceptric
# result shells, so they never enter the coherence coarse-node set.


def _real_refs(net_or_edge_index: dict, nid: str, nodes: dict | None = None) -> list[str]:
    """Return a node's logical prerequisites from the canonical projection.

    ``nodes`` is retained solely for callers holding an old, pre-projection
    in-memory shape. A built corpus network must pass the network itself, so
    coherence cannot mistake ordinary support, validation or analogy for a
    derivation.
    """
    if nodes is None:
        from laplace.research import corpus_ingest as ci
        return ci.inferential_dependencies(net_or_edge_index, nid)

    # Compatibility path for an old unprojected fixture; it cannot know typed
    # semantics and is intentionally not used by check_coherence.
    ei = net_or_edge_index
    out = []
    for ref in ei.get(nid, []):
        r = _strip_conf(ref).replace("sem::", "")
        if "::" in r or r == nid:
            continue
        if r in nodes:
            out.append(r)
    return out


def check_topology(corpus_name: str,
                   root: str | Path | None = None) -> dict[str, Any]:
    """Graph health: zero dangling links, one connected component.

    A dangling link is an edge whose target is not a live node (canon_weaver's
    topology failure, computed here on the friction-ledger network). Components
    are taken over the UNDIRECTED derivation graph: a pair of nodes linking only
    to each other is a disconnected island, not an integrated part. Gate 1 of
    the build-completion contract (canon://operations/gate_registry), run on the
    object an evolution mutates. ``root`` (additive) gates a POST-evolution state
    (see ``_load_corpus_network``).
    """
    net, note = _load_corpus_network(corpus_name, root)
    if net is None:
        return {"pass": None, "manual": True, "note": note}
    nodes, ei = net["nodes"], net["edge_index"]

    dangling: list[dict[str, str]] = []
    adj: dict[str, set] = {n: set() for n in nodes}
    for nid in nodes:
        for ref in ei.get(nid, []):
            r = _strip_conf(ref).replace("sem::", "")
            if "::" in r or r == nid:
                continue          # an audit marker or the self-identity referent
            if r not in nodes:
                dangling.append({"node": nid, "target": r})
                continue
            adj[nid].add(r)
            adj[r].add(nid)

    seen: set[str] = set()
    components = 0
    for start in nodes:
        if start in seen:
            continue
        components += 1
        stack = [start]
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x)
            stack.extend(adj[x] - seen)

    return {
        "pass": not dangling and components <= 1,
        "corpus": corpus_name,
        "total_nodes": len(nodes),
        "dangling": dangling,
        "components": components,
    }


def check_coherence(corpus_name: str,
                    root: str | Path | None = None) -> dict[str, Any]:
    """Renormalisation: every coarse node is described by the level below it.

    A coarse node (a ``res:``/``thm:``/``goal:`` result shell) is *described*
    only when it draws from at least one finer node. A coarse node that derives
    from nothing is content-free — the renormalisation audit's "merge the
    content-free" failure (canon://skills/conceptric_coherence). Gate 2 of the
    build-completion contract, computed on the friction-ledger network so it sees
    a POST-evolution state; the fuller integration score (>=2 draws, why-and-how)
    runs on the CanonGraph projection at build time. ``root`` (additive) gates a
    POST-evolution state (see ``_load_corpus_network``).
    """
    net, note = _load_corpus_network(corpus_name, root)
    if net is None:
        return {"pass": None, "manual": True, "note": note}
    nodes, ei = net["nodes"], net["edge_index"]

    coarse = [nid for nid in sorted(nodes)
              if nid.startswith(("res:", "thm:", "goal:"))]
    under_described = [nid for nid in coarse if not _real_refs(net, nid)]
    return {
        "pass": not under_described,
        "corpus": corpus_name,
        "coarse_nodes": len(coarse),
        "under_described": under_described,
    }


# ---------------------------------------------------------------------------
# meta_leak: object_not_artefact as a mechanical gate over the compiled tex
# ---------------------------------------------------------------------------


def check_meta_leak(project: str) -> dict[str, Any]:
    """Scan a project's compiled .tex for meta-instruction leaking into prose —
    the machine's vocabulary, plan/fork routing language, and performative
    posture (canon://workflow/object_not_artefact: a policy sentence in the
    output IS the defect). The lexicon is data in ``pipeline.schema``; comment
    lines are excluded so the %PLAN/%NODES markers never fire their own gate.
    A fenced-brief POLICY channel, when present, is echo-scanned too: any
    6-word shingle of policy text appearing verbatim in prose is a leak."""
    from laplace.pipeline import registry, schema

    proj = registry.resolve(project)
    if proj is None:
        return {"pass": None, "error": f"unknown project {project!r}"}
    tex_dir = proj.resolved_target_dir()
    if tex_dir is None or not tex_dir.is_dir():
        return {"pass": None, "manual": True,
                "note": f"no compiled tex dir for {project!r}"}

    compiled = {cls: [re.compile(p, re.IGNORECASE) for p in pats]
                for cls, pats in schema.META_LEAK_PATTERNS.items()}
    hits: list[dict[str, Any]] = []
    for tex in sorted(tex_dir.glob("*.tex")):
        for lineno, line in enumerate(read_safe(tex).splitlines(), 1):
            if line.lstrip().startswith("%"):
                continue                      # structural markers stay silent
            body = line.split("%", 1)[0]      # trailing comments too
            for cls, pats in compiled.items():
                for pat in pats:
                    m = pat.search(body)
                    if m:
                        hits.append({"file": tex.name, "line": lineno,
                                     "class": cls, "match": m.group(0)})

    # Configuration echo: text that CONFIGURES the generator must never surface
    # in prose. Sources (2026-07-09 staged rebuild): compiled dispatches' POLICY
    # channels, the prose stage preamble, and the voice profile itself — a
    # profile sentence appearing verbatim in the manuscript is the §1.10 leak.
    shingle_hits: list[dict[str, Any]] = []
    if True:
        shingles: set[str] = set()

        def _shingle(text: str) -> None:
            words = text.lower().split()
            shingles.update(" ".join(words[i:i + 6])
                            for i in range(len(words) - 5))

        dispatches_dir = proj.stage_path("dispatches")
        if dispatches_dir and dispatches_dir.is_dir():
            for d in sorted(dispatches_dir.glob("*_dispatch.md")):
                _shingle(schema.parse_channels(
                    read_safe(d)).get(schema.BRIEF_CHANNEL_POLICY, ""))
        _shingle(schema.PROSE_STAGE_PREAMBLE)
        from laplace.pipeline import dispatch as _dispatch
        profile = proj.path(_dispatch.VOICE_PROFILE_PATH)
        if profile and profile.is_file():
            _shingle(read_safe(profile))
        if shingles:
            for tex in sorted(tex_dir.glob("*.tex")):
                flat = " ".join(w for line in read_safe(tex).splitlines()
                                if not line.lstrip().startswith("%")
                                for w in line.split("%", 1)[0].lower().split())
                for sh in shingles:
                    if sh in flat:
                        shingle_hits.append({"file": tex.name, "class": "policy-echo",
                                             "match": sh})
    hits.extend(shingle_hits)
    return {"pass": not hits, "project": project, "hits": hits, "n": len(hits)}


# ---------------------------------------------------------------------------
# conceptric_build: the seven-gate composite the evolution contracts invoke
# ---------------------------------------------------------------------------


def check_conceptric_build(project: str) -> dict[str, Any]:
    """The build-completion composite: the five conceptric gates + the plan
    validator + the dirty report, as ONE verdict. This is the check the banked
    evolution contracts already invoked by name while the dispatch silently
    dropped it — the hole the hard-fail aggregation now closes."""
    import importlib.util
    import json as _json
    import tempfile

    from laplace.pipeline import registry

    proj = registry.resolve(project)
    if proj is None:
        return {"pass": None, "error": f"unknown project {project!r}"}

    gates = {
        "connectivity": check_connectivity(project),
        "projection_labels": check_projection_labels(project),
        "glossary": check_glossary(project),
        "substrate": check_substrate(project),
        "figures": check_figures(project),
    }

    plan_res: dict[str, Any] = {"pass": None, "manual": True, "note": "no plan"}
    plan_path = proj.plan()
    if plan_path is not None and plan_path.is_file():
        vp = source_tree() / "scripts" / "validate_projection_plan.py"
        try:
            spec = importlib.util.spec_from_file_location("_vf_validate", vp)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            plan_res = mod.validate(str(plan_path), project)
        except Exception as e:  # the validator is part of the verdict: failing to run it fails
            plan_res = {"pass": False, "error": f"plan validator unavailable: {e}"}

    dirty: list[dict[str, Any]] = []
    try:
        from laplace.manuscript import storyboard
        dirty = [d for d in storyboard.dirty_report(project) if d.get("dirty")]
    except Exception as e:
        dirty = [{"error": f"dirty report unavailable: {e}", "dirty": True}]

    gate_passes = [g.get("pass") for g in gates.values()]
    decided = [p for p in gate_passes + [plan_res.get("pass")] if p is not None]
    ok = bool(decided) and all(decided) and not dirty
    return {"pass": ok, "project": project, "gates": gates,
            "plan": plan_res, "dirty_sections": dirty}


# ---------------------------------------------------------------------------
# contracts: every operational surface has its canon node, is orient-reachable,
# and its executable verify runs green (claims -> gates; the up-guarantee)
# ---------------------------------------------------------------------------


def check_contracts(canon: "Canon | None" = None) -> dict[str, Any]:
    """Run schema.OPERATION_CONTRACTS. A surface fails when its canon node is
    missing, its probe goal cannot reach the node through the manifest tags
    (the same token overlap orient's relevance marking uses), or its executable
    verify does not pass. A claim without a green gate is itself the finding."""
    import importlib

    from laplace.pipeline import schema as _schema

    canon = canon or get_canon()
    rows: list[dict[str, Any]] = []
    for c in _schema.OPERATION_CONTRACTS:
        row: dict[str, Any] = {"surface": c["surface"], "canon": c["canon"]}
        # (a) the canon node resolves
        try:
            canon.resolve(c["canon"].removeprefix("canon://"))
            row["canon_ok"] = True
        except Exception:
            row["canon_ok"] = False
        # (b) orient-reachability: probe tokens against the manifest tags of the
        # node (>=2 overlapping tokens - the relevance-marking mechanics)
        ref = c["canon"].removeprefix("canon://")
        meta = (canon.manifest.get("wiki") or {}).get(ref) or {}
        blob = set()
        for t in (meta.get("tags") or []) + ref.replace("/", " ").split():
            blob.update(t.lower().replace("-", " ").split())
        probe = set(c["probe"].lower().replace("-", " ").split())
        row["reachable"] = len(probe & blob) >= 2
        # (c) the executable claim
        mod_name, fn_name = c["verify"].split(":")
        try:
            fn = getattr(importlib.import_module(mod_name), fn_name)
            res = fn()
            row["verify_ok"] = bool(res.get("pass"))
            if not row["verify_ok"]:
                row["verify_detail"] = {k: v for k, v in res.items() if k != "pass"}
        except Exception as e:
            row["verify_ok"] = False
            row["verify_detail"] = f"verify raised: {e}"
        row["pass"] = row["canon_ok"] and row["reachable"] and row["verify_ok"]
        rows.append(row)
    failing = [r["surface"] for r in rows if not r["pass"]]
    return {"pass": not failing, "surfaces": rows, "failing": failing}


# ---------------------------------------------------------------------------
# aggregate verify
# ---------------------------------------------------------------------------

# ``citations`` rides in the default run so the corpus-citation gate is *considered*
# at every verify, including generation-time. When ``corpus``+``project`` are not
# supplied it returns ``pass: None`` (manual) and so never red-flags a non-citing
# artefact; when they are, it enforces ``citation_discipline`` (no naked reliances /
# no invented citekeys) as a hard pass/fail. This is the structural cure for the
# recurring "corpus bypassed at generation" failure: the gate is in the default path,
# not an opt-in a generating agent has to remember.
DEFAULT_CHECKS = ["epistemic", "voice", "crossref", "citations"]


def verify(
    target: str | Path,
    checks: list[str] | None = None,
    canon: Canon | None = None,
    corpus: str | Path | None = None,
    project: str | None = None,
    focus: str | list[str] | None = None,
) -> dict[str, Any]:
    """Run consistency checks on a target and return a structured mismatch report.

    ``corpus`` + ``project`` enable the ``citations`` check (the exogenous-substrate
    surfacing rule): every corpus reference the project relies on must be cited in
    the manuscript. ``focus`` scopes the ``canon`` check to a changed node's
    neighbourhood (verify-at-grade); a focus that touches no canon node skips it.
    """
    canon = canon or get_canon()
    checks = checks or DEFAULT_CHECKS
    target = Path(target)
    results: dict[str, Any] = {}

    text = None
    if not target.is_dir() and any(c in {"voice", "epistemic"} for c in checks):
        text = read_safe(target)

    for check in checks:
        if check == "voice":
            # The reader reads the WHOLE manuscript, not the root file: a root
            # .tex only \inputs its section bodies, so voice on the root alone is
            # blind to every banned phrase living in an \input'd file (an N8
            # price-metaphor slipped past exactly here). Gather the \input graph -
            # the shared resolver crossref/epistemic already use - and voice-check
            # each file, keeping per-file attribution (file+line) on every
            # finding. Comment-stripping preserves line numbers. A non-.tex single
            # target (e.g. a rendered markdown draft) keeps the single-file path,
            # since the LaTeX \input/comment resolver does not apply to it.
            if target.is_dir() or target.suffix == ".tex":
                from laplace.pipeline.graph import gather_manuscript_files
                merged: dict[str, Any] = {"violations": [], "count": 0}
                for fp, ftext in gather_manuscript_files(target):
                    sub = check_voice(ftext)
                    for v in sub["violations"]:
                        merged["violations"].append({**v, "file": str(fp)})
                merged["count"] = len(merged["violations"])
                merged["pass"] = not merged["violations"]
                results["voice"] = merged
            else:
                results["voice"] = check_voice(text or "")
        elif check == "epistemic":
            # The epistemic ledger reads the WHOLE manuscript: a root .tex only
            # \inputs its sections, so flatten the \input tree (the same gatherer
            # the conceptric uses) or the check is vacuous on a modular manuscript.
            from laplace.pipeline.graph import _gather_manuscript_text
            results["epistemic"] = check_epistemic(_gather_manuscript_text(target))
        elif check == "crossref":
            results["crossref"] = check_crossref(target)
        elif check == "canon":
            results["canon"] = check_canon(canon, focus=focus)
        elif check == "contracts":
            results["contracts"] = check_contracts(canon)
        elif check == "citations":
            if corpus and project:
                results["citations"] = check_corpus_citations(target, corpus, project)
            else:
                results["citations"] = {"pass": None, "manual": True,
                                        "note": "pass corpus=<corpus.bib> and project=<key> to enforce"}
        elif check == "empirical":
            # No deterministic check: hand back the protocol for an agent to run.
            sk = canon.skills.get("empirical_ledger")
            results["empirical"] = {
                "pass": None,
                "manual": True,
                "protocol": sk.skill_md.read_text(encoding="utf-8") if sk else "",
            }
        elif check in ("connectivity", "projection_labels", "glossary", "substrate",
                       "figures", "conceptric_build", "meta_leak", "evolution"):
            # The build-completion gates run against a project conceptric, keyed by
            # ``project`` (the same key the citations gate uses). Without a project
            # they return manual - the target may not be a conceptric-backed artefact.
            if not project:
                results[check] = {"pass": None, "manual": True,
                                  "note": "pass project=<corpus_name> to run this gate"}
            elif check == "connectivity":
                results["connectivity"] = check_connectivity(project)
            elif check == "glossary":
                results["glossary"] = check_glossary(project)
            elif check == "substrate":
                results["substrate"] = check_substrate(project)
            elif check == "figures":
                results["figures"] = check_figures(project)
            elif check == "conceptric_build":
                results["conceptric_build"] = check_conceptric_build(project)
            elif check == "meta_leak":
                results["meta_leak"] = check_meta_leak(project)
            elif check == "evolution":
                # the native evolution round-trip (pipeline.evolve): pass =
                # round_trip_exact OR already_applied - a banked, already-executed
                # contract correctly fails a fresh replay (fold by ledger, never
                # replay), which must not read as a red gate forever after.
                from laplace.pipeline import evolve as _evolve
                results["evolution"] = _evolve.verify_check(project)
            else:
                results["projection_labels"] = check_projection_labels(project)
        else:
            results[check] = {"pass": None, "error": f"unknown check {check!r}"}

    # Instrument here (not in the MCP wrapper) so any driver - MCP, Python API, a
    # subagent - feeds the fitness assessment identically.
    for check, res in results.items():
        skill = CHECK_SKILL.get(check)
        if skill and res.get("pass") is not None:
            telemetry.log("verify_check", skill=skill, check=check, passed=bool(res["pass"]))

    # A result carrying "error" is a MISTAKE (an unknown check name, an
    # unresolvable project), never a deferral: it hard-fails the whole verify.
    # This closes the silent hole where contracts invoked checks the dispatch
    # didn't know and the verdict stayed green (found 2026-07-08: the banked
    # evolution gates named 'evolution'/'conceptric_build' into the void).
    # Deliberate deferrals keep using "manual": True with pass None.
    errored = sorted(c for c, r in results.items() if r.get("error"))
    decided = [r["pass"] for r in results.values() if r.get("pass") is not None]
    passed = False if errored else (all(decided) if decided else None)
    n_issues = sum(
        len(r.get("violations", [])) + len(r.get("orphans", [])) + len(r.get("naked_claims", [])) + len(r.get("broken_refs", [])) + len(r.get("duplicate_labels", {})) + len(r.get("contradictions", [])) + len(r.get("dangling", [])) + len(r.get("dead_wood_linked", [])) + len(r.get("naked_reliances", [])) + len(r.get("collisions", {})) + len(r.get("deprecated_hits", [])) + len(r.get("missing_term", [])) + len(r.get("unscaffolded", [])) + len(r.get("defects", []))
        for r in results.values()
    )
    telemetry.log("verify", target=str(target), passed=passed, issue_count=n_issues)
    out = {
        "target": str(target),
        "checks": results,
        "passed": passed,
        "issue_count": n_issues,
        "summary": f"{'PASS' if passed else 'FAIL' if passed is False else 'PARTIAL'}: {n_issues} issue(s) across {len(results)} check(s).",
    }
    if errored:
        out["errored"] = errored
        out["summary"] += f" ERRORED: {', '.join(errored)}."
    return out


# ---------------------------------------------------------------------------
# execute: run a skill's backing script for its full artifact
# ---------------------------------------------------------------------------


_STDERR_TAIL_LIMIT = 2000
_STDERR_TRUNCATION_MARKER = "...[truncated]...\n"


def _bounded_stderr_tail(stderr: str | None) -> str:
    """Return the tail of ``stderr``, capped to ``_STDERR_TAIL_LIMIT`` chars.

    When the tail had to be cut, prefix a marker so a reader (human or
    dreamer) can tell a short/empty stderr from one that was chopped.
    """
    if not stderr:
        return ""
    if len(stderr) <= _STDERR_TAIL_LIMIT:
        return stderr
    return _STDERR_TRUNCATION_MARKER + stderr[-_STDERR_TAIL_LIMIT:]


def run_backing(
    skill: str,
    target: str = "",
    args: list[str] | None = None,
    canon: Canon | None = None,
    timeout: int = 90,
) -> dict[str, Any]:
    """Invoke a skill's backing script as a subprocess. Returns stdout/stderr/code."""
    canon = canon or get_canon()
    sk = canon.skills.get(skill)
    if sk is None:
        return {"error": f"unknown skill {skill!r}", "available": list(canon.skills)}
    if not sk.backing or not sk.backing_path or not sk.backing_path.exists():
        return {"error": f"skill {skill!r} has no runnable backing script"}

    script = sk.backing_path
    extra = ([target] if target else []) + (args or [])
    if script.suffix == ".ps1":
        cmd = ["powershell", "-NoProfile", "-File", str(script), *extra]
    else:
        cmd = [sys.executable, str(script), *extra]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        telemetry.log("execute", skill=skill, ok=False, target=target)
        return {"error": f"execution failed: {e}", "cmd": cmd}
    ok = proc.returncode == 0
    # Capture a short diagnostic signature on every run - the exit code and the
    # tail of stderr - so a later dreamer can self-diagnose ("script ok-rate
    # 0.0") without re-reproducing by hand. Bounded so the ledger stays
    # compact; a truncation marker is prefixed when the tail was cut so
    # readers can tell a short stderr from a chopped one.
    stderr_tail = _bounded_stderr_tail(proc.stderr)
    if ok:
        telemetry.log(
            "execute",
            skill=skill,
            ok=True,
            target=target,
            returncode=proc.returncode,
            stderr_tail=stderr_tail,
        )
    else:
        telemetry.log(
            "execute",
            skill=skill,
            ok=False,
            target=target,
            returncode=proc.returncode,
            stderr_tail=stderr_tail,
        )
    return {
        "skill": skill,
        "cmd": cmd,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "ok": ok,
    }
