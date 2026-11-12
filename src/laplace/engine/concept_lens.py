"""concept_lens.py - the integrade wiring for the physics lens (the keeper's per-substrate piece).

The third soul map (``concept_corpus/``) was built last session as 2 pillars -> 7 themes -> 20 papers
(/ 372 atoms) -> 236 conceptric edges, sharded into the self - but graded by DIRECTORY (atoms/, themes/,
pillars/ as sibling dirs), so the keeper ring descended by-kind, not by-meaning, and the conceptric's
edges sat inside the conceptric ``.md`` bodies where ``build_reach`` never saw them. That is "within-grade
wired but not reconstructable-THROUGH": the descent path was wrong and the lateral coupling was dead.

This module supplies the two MECHANICAL pieces that make the lens live, both derived from the wiring the
materialiser already wrote into the self-shard index (manifest-free):

  * ``lens_membership`` - the SEMANTIC parent function for the lens (the integrade/vertical link). A paper
    ascends to its theme (its own up-edge), a theme to its pillar (inverted from the pillar's down-edges),
    a pillar to the lens root; the conceptric file rides with its theme; an unclustered singleton attaches
    to the lens root directly (faithful - it has no recurring theme). The keeper builds pillar(g2) ->
    theme(g1) -> paper(g0) instead of the by-kind directory.

  * ``lens_edge_index`` - the LATERAL coupling (the within-grade link). The 236 directed conceptric edges
    (``paperA:atomX -> paperB:atomY``, typed + strengthed) are parsed out of the conceptric bodies and
    minted as SHARED REFERENT tokens on both endpoint papers, so ``keeper_ring.build_reach`` counts them:
    ``coupling(A, B)`` becomes the number of concept-atoms A and B share, not a flat 1-via-theme. That is
    what makes the enrichment (the coupled-neighbour pull-up) reflect the real idea-structure of the physics.

The semantic content of the lens (which papers, which themes, the deep cross-pillar bridges) was produced
by sealed subs + adjudicated builder!=judge last session; this is pure mechanical wiring of that output -
no LLM, deterministic, testable. The cross-pillar SPARSE deep bridges + the return-synthesis enrichment
policy stay the author's forks (F14/F23); this module only makes the existing structure reconstructable.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from laplace.pipeline.schema import token_for as _token_for

LENS_ROOT = "concept_corpus"
_ATOMS = f"{LENS_ROOT}/atoms/"
_THEMES = f"{LENS_ROOT}/themes/"
_PILLARS = f"{LENS_ROOT}/pillars/"
_CONNECTOME = f"{LENS_ROOT}/conceptric/"
ATOM_SEP = "::"                 # a virtual atom node id: "concept_corpus/atoms/<slug>.md::<atom-name>"
_ESSENCE_CAP = 320              # an atom handle is a glance at the fact, not the whole statement

# a conceptric bullet: - **paperA:atomX** -> **paperB:atomY**  _(kind, strength, source)_
_EDGE_RE = re.compile(
    r"\*\*([^:*]+):([^*]+?)\*\*\s*->\s*\*\*([^:*]+):([^*]+?)\*\*\s*_\(([^)]+)\)_"
)


def is_lens(node_id: str) -> bool:
    """True iff a node id lives under the physics lens (``concept_corpus/``)."""
    return node_id == LENS_ROOT or node_id.startswith(LENS_ROOT + "/")


def atom_parent(node_id: str) -> str | None:
    """A virtual atom node's parent is its PAPER (the part before ``::``); non-atom ids -> None.

    This is what puts the atoms at the substrate FLOOR (g0) and the paper one grade up as a CLUSTER of
    its atomic facts (g1) - a paper is a bundle of mechanisms/concepts/results, not itself an atom, so it
    belongs above the floor (his, 2026-06-08: papers-at-g0 was too close to the centre / always-surfacing).
    The lens then grades atom(g0) -> paper(g1) -> theme(g2) -> pillar(g3) -> lens(g4); an atom surfaces
    only on a full physics descent, never in the hello's coarse map - the lens is an ORGAN, not the centre."""
    if ATOM_SEP in node_id:
        return node_id.split(ATOM_SEP, 1)[0]
    return None


def _tokens(text: str) -> list[str]:
    from laplace.pipeline.canon import _tokenize
    # ``_tokenize`` returns a set.  The sequence becomes part of the leaf handle and
    # therefore the embedding input, so set iteration here made identical content move
    # whenever PYTHONHASHSEED changed.
    return sorted(_tokenize(text))


def lens_atom_leaves(repo_root: Path | str) -> dict[str, dict[str, Any]]:
    """Materialise the 372-style concept-ATOMS as the grade-0 substrate of the lens (the finest exogenous
    facts: one node per mechanism/concept/result/method, with its statement + locator). Read straight from
    ``concept_corpus/_atoms_manifest.json`` (public physics, never sealed) - virtual nodes (NOT files), so
    a reconstruction bottoms at the atom's STATEMENT (``base`` falls back to the node essence when there is
    no source file). The id is ``<paper-file>::<atom-name>`` so ``atom_parent`` routes it up to its paper."""
    import json
    root = Path(repo_root)
    mpath = root / "concept_corpus" / "_atoms_manifest.json"
    out: dict[str, dict[str, Any]] = {}
    if not mpath.is_file():
        return out
    data = json.loads(mpath.read_text(encoding="utf-8"))
    for p in data.get("papers", []):
        slug = p.get("slug", "")
        paper = f"{_ATOMS}{slug}.md"
        seen: set[str] = set()
        for a in p.get("atoms", []):
            name = (a.get("name") or "").strip()
            if not name:
                continue
            aid = f"{paper}{ATOM_SEP}{name}"
            if aid in seen:                          # a paper may repeat an atom name; keep the first
                continue
            seen.add(aid)
            kind = a.get("kind", "concept")
            stmt = (a.get("statement") or "").strip()
            loc = a.get("locator", "")
            essence = f"{kind}: {stmt}"[:_ESSENCE_CAP]
            kws = _tokens(f"{name} {stmt}")[:14]
            out[aid] = {"kind": f"atom-{kind}", "essence": essence, "keywords": kws,
                        "sealed": False, "locator": loc}
    return out


def _theme_of_atom(edges: list[dict[str, Any]]) -> str | None:
    """A paper's primary theme = its up-edge into ``concept_corpus/themes/...`` (empty for a singleton)."""
    for e in edges:
        to = e.get("to", "")
        if to.startswith(_THEMES):
            return to
    return None


def lens_membership(index: dict[str, dict[str, Any]], root_id: str = "") -> dict[str, str]:
    """The lens's SEMANTIC parent map: ``node_id -> parent_id`` for every lens node whose parent is NOT
    its directory. Derived from the self-shard ``index`` edges (manifest-free):

      * paper (``atoms/S.md``) -> its theme (own up-edge), or the lens root if unclustered (singleton);
      * theme (``themes/T.md``) -> its pillar (inverted from the pillar's down-edges), or lens root if none;
      * pillar (``pillars/P.md``) -> the lens root;
      * conceptric (``conceptric/T.md``) -> its theme (same id), or lens root if the theme is missing.

    Nodes not returned here (the manifests, the ``concept_corpus`` dir itself) fall through to ``dir_parent``.
    """
    members: dict[str, str] = {}

    # theme -> pillar, inverted from each pillar's down-edges into themes/
    theme_pillar: dict[str, str] = {}
    for nid, sh in index.items():
        if nid.startswith(_PILLARS):
            for e in sh.get("edges", []):
                to = e.get("to", "")
                if to.startswith(_THEMES):
                    theme_pillar[to] = nid

    for nid, sh in index.items():
        if not is_lens(nid):
            continue
        if nid.startswith(_ATOMS):
            members[nid] = _theme_of_atom(sh.get("edges", [])) or LENS_ROOT
        elif nid.startswith(_THEMES):
            members[nid] = theme_pillar.get(nid, LENS_ROOT)
        elif nid.startswith(_PILLARS):
            members[nid] = LENS_ROOT
        elif nid.startswith(_CONNECTOME):
            theme = _THEMES + nid[len(_CONNECTOME):]            # conceptric/T.md -> themes/T.md
            members[nid] = theme if theme in index else LENS_ROOT
    return members


def parse_conceptric(repo_root: Path | str) -> list[dict[str, str]]:
    """Parse the directed within-theme edges out of the conceptric ``.md`` bodies. Returns one record per
    edge: ``{src_paper, dst_paper, src_atom, dst_atom, kind, strength, theme}`` (paper = the ``atoms/S.md``
    node id). The edges are atom-level; the paper-level collapse is done by ``lens_edge_index``. Public
    physics, read directly (never sealed)."""
    root = Path(repo_root)
    cdir = root / "concept_corpus" / "conceptric"
    out: list[dict[str, str]] = []
    if not cdir.is_dir():
        return out
    for f in sorted(cdir.glob("*.md")):
        theme = f"{_THEMES}{f.stem}.md"
        text = f.read_text(encoding="utf-8")
        for m in _EDGE_RE.finditer(text):
            sp, sa, dp, da, meta = (g.strip() for g in m.groups())
            parts = [p.strip() for p in meta.split(",")]
            kind = parts[0] if parts else ""
            strength = parts[1] if len(parts) > 1 else ""
            out.append({"src_paper": f"{_ATOMS}{sp}.md", "dst_paper": f"{_ATOMS}{dp}.md",
                        "src_atom": sa, "dst_atom": da, "kind": kind, "strength": strength, "theme": theme})
    return out


def lens_edge_index(repo_root: Path | str) -> dict[str, list[str]]:
    """The lens's structural + lateral referents for ``build_reach`` (coupling). Two parts:

      * **containment** (atom -> its paper): each g0 atom's referent is its PAPER, so an atom couples by
        STRUCTURE (same-paper siblings), NOT by its bag of physics keywords. Without this an atom would
        fall back to keyword-reach and two papers would couple just for both saying 'quantum' - the
        coupling must be the real shared substrate, not shared vocabulary.
      * **conceptric** (paper <-> paper): each within-theme conceptric edge A<->B mints ONE canonical,
        undirected token added to BOTH papers, so ``coupling(A, B)`` counts the concept-atoms they share -
        the live within-grade wiring. (The edges are paper-level: the conceptric's atom names are a
        Haiku-generated namespace that does NOT join the manifest atom names, so the faithful collapse is
        to the paper.)

    Merge into the self-shard edge index before ``build_reach``; it only ADDS substrate, never removes."""
    idx: dict[str, list[str]] = {}
    for aid, paper in atom_to_paper(repo_root).items():
        idx.setdefault(aid, []).append(f"inpaper::{paper}")     # the atom's structural referent (its paper)
    for e in parse_conceptric(repo_root):
        a, b = e["src_paper"], e["dst_paper"]
        lo, hi = sorted((a, b))
        atoms = "|".join(sorted((e["src_atom"], e["dst_atom"])))
        # minted through the one home (schema.token_for) on the ``connects`` axis, so
        # the prefix grammar is not hand-written here: the unordered atom pair + the
        # relation kind, now carrying the parsed strength too (dropped before). Both
        # endpoints mint the identical token, so the coupling COUNT is unchanged — the
        # token string is the only thing that moves (the metric retrain is banked).
        token = _token_for("connects", lo=lo, hi=hi, atoms=atoms,
                           kind=e["kind"], strength=e.get("strength", ""))
        idx.setdefault(a, []).append(token)
        idx.setdefault(b, []).append(token)
    return idx


def atom_to_paper(repo_root: Path | str) -> dict[str, str]:
    """``atom node id -> its paper node id`` from the atoms manifest (the containment the floor hangs on)."""
    import json
    root = Path(repo_root)
    mpath = root / "concept_corpus" / "_atoms_manifest.json"
    out: dict[str, str] = {}
    if not mpath.is_file():
        return out
    data = json.loads(mpath.read_text(encoding="utf-8"))
    for p in data.get("papers", []):
        paper = f"{_ATOMS}{p.get('slug', '')}.md"
        for a in p.get("atoms", []):
            name = (a.get("name") or "").strip()
            if name:
                out[f"{paper}{ATOM_SEP}{name}"] = paper
    return out


_BRIDGE_RE = re.compile(r"\*\*([^*]+?)\*\*\s*<=>\s*\*\*([^*]+?)\*\*\s*_\(([^)]+)\)_")
_CONJ_HEADING = "## Conjectural"
CONJECTURE_PREFIX = "conjecture::"   # a conjectural edge token: surfaces on ideation only, never on recall


def is_conjecture_token(token: str) -> bool:
    return token.startswith(CONJECTURE_PREFIX)


def _bridges_file(repo_root: Path | str) -> str:
    f = Path(repo_root) / "concept_corpus" / "cross_pillar_bridges.md"
    return f.read_text(encoding="utf-8") if f.is_file() else ""


def cross_pillar_edge_index(repo_root: Path | str) -> dict[str, list[str]]:
    """The CROSS-PILLAR coupling: parse the FAITHFUL bridges (the part of cross_pillar_bridges.md BEFORE the
    '## Conjectural' heading - the judge-refuted ones are NOT in standard coupling) and mint one undirected
    token shared by the two anchor theme nodes, so coupling spans the two pillars (otherwise 0). The
    conjectural bridges ride a SEPARATE channel (``conjectural_edge_index``). Empty if the file is absent."""
    faithful = _bridges_file(repo_root).split(_CONJ_HEADING, 1)[0]   # standard coupling = faithful only
    idx: dict[str, list[str]] = {}
    for m in _BRIDGE_RE.finditer(faithful):
        a, b, meta = (g.strip() for g in m.groups())
        lo, hi = sorted((a, b))
        token = f"bridge::{lo}<=>{hi}::{meta.split(',')[0].strip()}"
        idx.setdefault(a, []).append(token)
        idx.setdefault(b, []).append(token)
    return idx


def conjectural_edge_index(repo_root: Path | str) -> dict[str, list[str]]:
    """The CONJECTURAL channel (his 'grit' ruling, 2026-06-08): the judge-refuted / low-confidence links are
    KEPT, not dropped - the 'if this connection holds, then X follows' edges that signal there *might* be
    something. They mint ``conjecture::`` tokens (distinct from faithful ``bridge::``) so a caller can merge
    them into the reach ONLY for an ideation/exploration task (never factual recall), where a pulled
    conjectural neighbour is surfaced FLAGGED UNRESOLVED - a prompt to a future self to try to establish it.
    Parsed from the section AFTER '## Conjectural'. This is the creativity band; synthetics' AI-chains reuse it."""
    text = _bridges_file(repo_root)
    parts = text.split(_CONJ_HEADING, 1)
    if len(parts) < 2:
        return {}
    idx: dict[str, list[str]] = {}
    for m in _BRIDGE_RE.finditer(parts[1]):
        a, b, meta = (g.strip() for g in m.groups())
        lo, hi = sorted((a, b))
        token = f"{CONJECTURE_PREFIX}{lo}<=>{hi}::{meta.split(',')[0].strip()}"
        idx.setdefault(a, []).append(token)
        idx.setdefault(b, []).append(token)
    return idx


def merge_edge_index(base: dict[str, list[str]], extra: dict[str, list[str]]) -> dict[str, list[str]]:
    """Merge ``extra`` referents into ``base`` (the self-shard edge index), de-duplicating per node. Pure;
    returns a new dict so callers never mutate the shard index in place."""
    out = {k: list(v) for k, v in base.items()}
    for k, vs in extra.items():
        cur = out.setdefault(k, [])
        seen = set(cur)
        for v in vs:
            if v not in seen:
                cur.append(v)
                seen.add(v)
    return out
