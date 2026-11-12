"""conceptric.py - the unified graded network and the dimensionalised pull (the scanner's organ).

His design (2026-06-10, memory ``pull-radius-dimensionalised-thinking-phases``): the whole
conceptric is ONE linked network with two principal axes -

* **width (interactions)**: at any grade, a node's lateral strength to a peer is the CUMULATIVE
  shared substrate of the grades below them, normalized per node - not a binary edge, a pull.
* **depth (identity)**: a node's conceptual identity is its uplinks - what it is a part of.

One formula carries both axes. Coupling is **DIRECTIONAL**:

    s(a -> b) = |reach(a) ∩ reach(b)| / |reach(a)|

``reach`` aggregates bottom-up (``keeper_ring.build_reach``), so between siblings this reads the
cumulative common substrate below (width), and between child and parent the SAME formula gives
child->parent ~= 1 ("I am almost wholly part of this") while parent->child = the child's SHARE of
the parent (identity weight). The asymmetry is the descend/ascend asymmetry, kept, never averaged
away.

**The pull radius is dimensionalised**: (width, lens, conjectural) are mechanical knobs per level,
and the THINKING PHASES are just presets over them - recall pulls tight and lens-locked, ideation
pulls wide and surfaces the conjectural grit (``conjectural-links-are-creativity``: kept links that
fire on ideation, never on recall). No intelligence in the traversal - intelligence was paid at
build; this module only reads wire already laid.

Per-grade normalized strength distributions double as the **phi panel** (``phi-is-watched-not-
imposed``): clustering should flatten the distribution grade by grade; the panel shows the
trajectory, imposes nothing.

Seal: soul nodes ride as HANDLES (entity stems, trait slugs - identity preserved, content
withheld); their reach is locator window tokens (``soul_provenance``), so trait <-> entity coupling
is a read-off of shared substrate. This module never returns soul content.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from laplace.engine.keeper import HANDOFF_SERIES
from laplace.engine.keeper_ring import CONJECTURE_PREFIX, build_reach
from laplace.engine.record_shard import SESSIONS_ARCHIVE, TRANSCRIPT_SERIES

# ---------------------------------------------------------------------------
# the thinking phases - parameter presets on the pre-built network (his rule)
# ---------------------------------------------------------------------------

PHASES: dict[str, dict[str, Any]] = {
    # tight, lens-locked, no grit: find the thing you already know is there
    "recall": {"width": 4, "lens_locked": True, "conjectural": False},
    # the default working radius: moderate fan, cross-lens allowed
    "survey": {"width": 12, "lens_locked": False, "conjectural": False},
    # wide, cross-lens, conjectural grit surfaced: where creativity lives
    "ideate": {"width": 24, "lens_locked": False, "conjectural": True},
    # CONSUMPTION: a reader landing on a node and taking its whole neighbourhood, not browsing it.
    # A paper family is ~60 nodes, so any tighter cut lands INSIDE the family and hands the reader
    # a truncated one - see CONSUMPTION_WIDTH.
    "consume": {"width": 60, "lens_locked": False, "conjectural": False},
}

# THE CONSUMPTION WIDTH (2026-08-20, ruled BY MEASUREMENT on the 25-paper blind-surfacing harness,
# evidence/BLIND_SURFACING_RERUN_2026-08-20/). The question was how a landed reader gets the whole
# of a node's rich layer rather than a slice of it, and two arms were run against each other:
#   (A) raise the consumption width 20 -> 60, ranking unchanged;
#   (B) leave the width and weight `out` by IDF, so rare family tokens outrank common path words.
# Measured, once the fallback guard stops re-emitting path words (distillate_lens.GUARD_MAX_DOCFREQ):
#   arm A  216 -> 271 atoms reached of 271 in the landed families; family nodes 374 -> 469.
#   arm B  215 atoms at width 20 (ONE FEWER than the unweighted rank) and identical 271 at width 60.
# Arm B is refuted on its own claim: with the denominator cleaned, IDF weighting buys nothing and
# would re-rank every lateral in the engine to buy it. ALTERNATIVE NOT TAKEN, recorded here so the
# next reader does not re-derive it. Arm A's cost, named: a node form widens (the partition-free
# pdf node, scripts/reconstruct_node.py, 5.0 KB at width 12 -> 7.4 KB at 20 -> 19.1 KB at 60), and
# the extra fan is overwhelmingly the node's OWN family, which is the content the reader came for.
CONSUMPTION_WIDTH = PHASES["consume"]["width"]

# how fast salience fades up a hit's own descent path (per step above the recovery) - half of
# the fire's reconstruction geometry; the router's constants (beam/width/decay) are the other.
ANCESTOR_DECAY = 0.85

# the lateral IDF floor (his calibration 2026-07-11: "laterals ride single low-IDF keywords").
# A lone shared substrate token carries an at-grade edge ONLY when it is distinctive - present in
# at most this fraction of the substrate-bearing nodes. Edges sharing >=2 tokens are kept
# unconditionally. A high document-frequency term (a "the"/"py"-class word) can no longer, by
# itself, forge a lateral pull.
LATERAL_IDF_MAX_DOCFREQ = 0.10

# section handles: a leaf doc with no member nodes still exposes descendable slices - each ATX
# heading of the section level becomes a child pointer with a line span, so a reconstructor
# descends into a section instead of flat-reading the whole file (his: "doc nodes give no
# section handles").
_ATX_RX = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_DOC_LEAF_SUFFIXES = ("md", "markdown", "txt")

# essence keyword hygiene: the projection's keyword badges drop pure stopword / path-noise
# tokens so a code leaf shows its real handles, not a bag of "the"/"and"/"py" (his: "code leaves
# give stopword bags"). Conservative - only obvious non-content tokens.
_VIEW_STOPWORDS = {
    "the", "and", "a", "an", "of", "to", "in", "is", "it", "for", "on", "with", "as",
    "by", "or", "this", "that", "be", "are", "at", "from", "was", "were", "but", "not",
    "py", "src", "txt", "md", "self",
}

TRAITS_INDEX = "archive/soul_dump/_shard/_traits/_INDEX.json"
TRAITS_DIR = "archive/soul_dump/_shard/_traits"
# the dyad's materialised axes (committed - the value ring is ONE ring, two exhibitors;
# his traits stay sealed/local above, the dyad's travel with the repo)
DYAD_TRAITS_DIR = "archive/self_record/_weld/traits"

SOUL_ENTITIES_PARENT = "soul://entities"
SOUL_TRAITS_PARENT = "soul://traits"


# ---------------------------------------------------------------------------
# directional coupling - the one formula, both axes
# ---------------------------------------------------------------------------

def coupling_directed(reach: dict[str, set[str]], a: str, b: str) -> dict[str, Any]:
    """The directional pull between two nodes. ``out`` is a's view of b (what fraction of a's own
    substrate is shared), ``in`` is b's view of a. ``conjectural`` iff the ONLY shared substrate is
    conjecture:: grit - surfaced on ideation, never asserted on recall."""
    ra, rb = reach.get(a, set()), reach.get(b, set())
    shared = ra & rb
    n = len(shared)
    return {
        "shared": n,
        "out": (n / len(ra)) if ra else 0.0,
        "in": (n / len(rb)) if rb else 0.0,
        "conjectural": n > 0 and all(t.startswith(CONJECTURE_PREFIX) for t in shared),
    }


# ---------------------------------------------------------------------------
# the network - the graded self tree + the sealed soul overlay, one object
# ---------------------------------------------------------------------------

_SELF_EDGE_INDEX_MEMO: dict[str, dict[str, list[str]]] = {}


def _self_edge_index(repo_root: Path) -> dict[str, list[str]]:
    """The merged substrate edge-index - the exact recipe ``reconstruct_self_ring`` uses, reused so
    the scanner's couplings ARE the reconstruction's couplings (one object, never a parallel picture).

    HOT-6a (2026-08-20 self-audit): a bare PROCESS-SCOPED memo, keyed only on ``repo_root`` - NOT
    mtime-keyed. The merge draws from 5 subsystems (``self_shard`` + four lens edge-index builders),
    each globbing/reading across many of ITS OWN files with no single mtime that would cheaply prove
    "nothing changed" - the verifier found that building a trustworthy mtime key here would need
    either a broad directory walk (paying its own I/O back) or new staleness hooks threaded through
    all five, i.e. not the "~10-line change" a memo sounds like. A bare per-process cache avoids that
    problem entirely because it targets a narrower guarantee: within the lifetime of ONE short-lived
    process (a deposit, ``reconstruct_node.py``, a scanner boot) - the callers this repo actually
    has - nothing rewrites these shards out from under the process that is reading them, so the first
    call's answer stays correct for every later call in the same process. This is layer (a) only
    (the in-process duplicate-rebuild inside one deposit, e.g. ``metric_distill.wire_pairs`` calling
    this again after ``load_network`` already did); it does NOT persist across processes (layer (b),
    an on-disk banked index, is a separate design call the finder flagged as needing its own
    staleness contract, deliberately not taken here).

    LIMITATION, stated once and not to be quietly relied on: a LONG-LIVED process that both serves
    from this network AND edits the shard files it is built from (nothing in this repo does that
    today) would keep serving the first answer until it restarts. If such a caller ever exists, it
    needs real invalidation before reusing this memo - do not assume this cache self-heals."""
    key = str(repo_root)
    cached = _SELF_EDGE_INDEX_MEMO.get(key)
    if cached is not None:
        return cached
    from laplace.engine import collaborator_lens, concept_lens, distillate_lens, record_shard, self_shard, structural_lens
    index = self_shard.load_index(repo_root)
    edge_index = {name: [e["to"] for e in sh.get("edges", [])] for name, sh in index.items()}
    edge_index = concept_lens.merge_edge_index(edge_index, concept_lens.lens_edge_index(repo_root))
    edge_index = concept_lens.merge_edge_index(edge_index, concept_lens.cross_pillar_edge_index(repo_root))
    edge_index = concept_lens.merge_edge_index(edge_index, collaborator_lens.collaborator_edge_index(repo_root))
    edge_index = concept_lens.merge_edge_index(edge_index, record_shard.record_edge_index(repo_root))
    edge_index = concept_lens.merge_edge_index(edge_index, structural_lens.structural_edge_index(repo_root))
    # THE DISTILLATE WIRE (WO-20260820-wire-distillates-to-leaves, the blind surfacing test).
    # A paper's rich layer - its concept-atoms, its program-ladder OpenAlex handle, its per-paper
    # stage-store rows - is lens-claimed, so it is absent from the residue meaning-tree the
    # descender reads and can never be a descent HIT. It can be a descent hit's NEIGHBOUR, and
    # this is the wire that makes it one: one shared `distillate_edge::<paper_id>` referent minted
    # on every member of the family. LAST in the merge, because its edgeless-node guard reads the
    # index built so far (see distillate_lens.distillate_edge_index) - a node that had no edge
    # keeps its keyword reach instead of having it replaced by the new token.
    # The guard needs the graded tree (a wired node's own coverage), and it is read HERE rather
    # than handed in by load_network so that every caller of this memo - load_network and
    # metric_distill.wire_pairs alike - gets the identical index whichever one warms it first.
    from laplace.engine import keeper
    graded = keeper.load_tree_local(repo_root)
    edge_index = concept_lens.merge_edge_index(
        edge_index, distillate_lens.distillate_edge_index(
            repo_root, base=edge_index, nodes=graded))
    # THE DIGEST WIRE (DP-A2, the six red thread probes). A concept cluster's handle is six tf*idf
    # PATH keywords, so a content-grade query ("closure residual coupling between scales") is scored
    # against file-name words and misses the node that holds the mechanism. `laplace.engine.digest_mint`
    # extracts a claim-grade digest - one claim sentence plus its load-bearing object tokens, read
    # off the node's own members, no model call - and `digest_lens` mints one referent per object on
    # the digested node AND on the leaf that supplied it, so the object becomes substrate the reach
    # can couple on. A LENS, exactly like the distillate wire above and for the same residue-tree
    # reason: a digest written into a shard would recluster as content. LAST in the merge, so its
    # edgeless-leaf guard reads the whole index built so far. No store, no rows, no digests banked =
    # {} and this line is a no-op.
    from laplace.engine import digest_lens
    edge_index = concept_lens.merge_edge_index(
        edge_index, digest_lens.digest_edge_index(repo_root, base=edge_index, nodes=graded))
    _SELF_EDGE_INDEX_MEMO[key] = edge_index
    return edge_index


def node_lenses(nid: str, node: dict[str, Any] | None = None) -> list[str]:
    """Mechanical lens membership for a node - the aspects it belongs to, derived from where it
    lives (never decreed). A node can wear several badges; the overlap is the point."""
    out: list[str] = []
    if nid.startswith("technique://"):              # the cross-program technique apex (technique_lens)
        return ["technique"]
    if nid.startswith("soul://") or nid.startswith("soul/") or nid.startswith("soul_corpus"):
        out.append("soul")
    if nid.startswith(SOUL_TRAITS_PARENT) or "/_traits/" in nid:
        out.append("values")
    if nid.startswith(SOUL_ENTITIES_PARENT):
        out.append("people")
    if nid.startswith("concept_corpus") or nid.startswith("reference_corpus"):
        out.append("physics")
    if "_structural/" in nid:
        if nid.startswith("engine_corpus"):
            out.append("engine")                    # the operations lens - the mechanised workings
        elif nid.startswith("archive/self_record"):
            out.append("self-record")               # the regraded build record
        elif nid.startswith("synthetics_corpus"):
            out.append("synthetics")                # the orchestra's synthetic paper-projects - its own lens...
            out.append("physics")                   # ...cross-wired into physics (his call: distinct lens, physics-linked)
        else:
            out.append("physics")                   # the regraded program ladders (gen->rung->paper)
    if nid.startswith("life_corpus/people") or nid.startswith("collaborator"):
        out.append("people")
    if nid.startswith("src/laplace") or nid.startswith("tests"):
        out.append("engine")
    if (nid.startswith("EIGEN_") or nid in ("HANDOFF.md", "OPEN_STACK.md", HANDOFF_SERIES,
                                            TRANSCRIPT_SERIES)
            or nid.startswith("SESSION_HANDOFF") or nid.startswith(SESSIONS_ARCHIVE)):
        out.append("self-record")
    if node and node.get("grade", 0) == 0 and not out:
        out.append("substrate")
    return out or ["world"]


def _attach(nodes: dict[str, dict[str, Any]], reach: dict[str, set[str]],
            nid: str, parent: str, grade: int, toks: set[str], leaf: bool = True) -> None:
    nodes[nid] = {"id": nid, "grade": grade, "parent": parent, "leaf": leaf,
                  "members": [], "coverage": [], "keywords": []}
    if parent in nodes:
        nodes[parent]["members"].append(nid)
    reach[nid] = toks


def _soul_overlay(repo_root: Path, nodes: dict[str, dict[str, Any]],
                  reach: dict[str, set[str]]) -> None:
    """Attach the sealed soul layer as HANDLES: entities (reach = their locator windows) and the
    value-ring traits (reach = their instances' windows). Trait <-> entity coupling then reads off
    shared substrate windows - the binding ring made visible, content withheld."""
    try:
        from laplace.engine import soul_provenance
        ent_reach = soul_provenance.entity_reach(repo_root)
    except Exception:                                   # noqa: BLE001 - no soul layer is fine
        ent_reach = {}
    root_id = "" if "" in nodes else next((k for k, v in nodes.items() if v.get("parent") is None), "")
    top_grade = max((n.get("grade", 0) for n in nodes.values()), default=1)
    if ent_reach:
        from laplace.pipeline.canon import _tokenize
        by_stem = soul_provenance.entities_by_stem(repo_root)
        _attach(nodes, reach, SOUL_ENTITIES_PARENT, root_id, max(1, top_grade - 1), set(), leaf=False)
        name_cov: set[str] = set()
        for stem, toks in sorted(ent_reach.items()):
            kw = sorted(_tokenize(stem.replace("_", " ").replace("-", " ")))
            ent_id = f"{SOUL_ENTITIES_PARENT}/{stem}"
            _attach(nodes, reach, ent_id, SOUL_ENTITIES_PARENT, 1, set(toks), leaf=False)
            nodes[ent_id]["keywords"] = kw          # the entity's NAME is its handle (identity, not
            nodes[ent_id]["coverage"] = kw          # content) - so a query for the person reaches it
            name_cov |= set(kw)
            # the entity's ITEMS as sealed grade-0 leaves - so a SPECIFIC query about the person
            # ("his PhD", "how she signs off") descends INTO the fold and recovers the right item,
            # not just the whole profile. The item's MEANING rides only the gitignored embedding
            # (fold-time disk read, embed_router.node_text); everything that can travel - the
            # node, its essence, a fire return - stays content-free. The act-sufficient collapse
            # then works for free: a generic pull yields the entity (items absorbed under the
            # hotter parent handle), an item that OUT-PULLS its parent earns the recovery.
            _data = by_stem.get(stem)
            for field in soul_provenance.ITEM_FIELDS:
                items = (_data[1] if _data else {}).get(field)
                if not isinstance(items, list):
                    continue
                for i, it in enumerate(items):
                    loc = soul_provenance.item_locator(it)
                    item_id = f"{ent_id}/{field}/{i}"
                    _attach(nodes, reach, item_id, ent_id, 0,
                            soul_provenance.locator_tokens(loc) if loc else set())
                    nodes[item_id]["keywords"] = kw + [field]
                    nodes[item_id]["sealed"] = True
                    nodes[item_id]["essence"] = (f"a sealed {field} item of {stem} - "
                                                 "content served to the local browser only")
            if not nodes[ent_id]["members"]:
                nodes[ent_id]["leaf"] = True        # an itemless entity stays a plain leaf handle
        # the parent handle SPEAKS FOR ITS MEMBERS by naming them: without this a specifically-named
        # entity is rank-1 by cosine yet unreachable, because the generic parent handle never clears
        # the descent beam to be expanded (found live folding David Griffiths, 2026-06-10). Names are
        # identity (the handle), never the sealed content - they ride the gitignored embedding only.
        nodes[SOUL_ENTITIES_PARENT]["coverage"] = sorted(name_cov)
        nodes[SOUL_ENTITIES_PARENT]["keywords"] = sorted(name_cov)
        reach[SOUL_ENTITIES_PARENT] = set().union(*ent_reach.values()) if ent_reach else set()

    trait_dirs = [d for d in (repo_root / TRAITS_DIR, repo_root / DYAD_TRAITS_DIR) if d.is_dir()]
    if trait_dirs:
        _attach(nodes, reach, SOUL_TRAITS_PARENT, root_id, max(1, top_grade - 1), set(), leaf=False)
        all_toks: set[str] = set()
        from laplace.engine import soul_provenance
        for tdir in trait_dirs:
            for f in sorted(tdir.glob("*.json")):
                if f.name.startswith("_"):
                    continue
                try:
                    d = json.loads(f.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                toks: set[str] = set()
                for inst in d.get("instances", []):
                    loc = inst.get("locator")
                    if isinstance(loc, str) and loc.strip():
                        toks |= soul_provenance.locator_tokens(loc)
                nid = f"{SOUL_TRAITS_PARENT}/{f.stem}"
                if nid in nodes:        # same stem in both dirs: the sealed dir won, skip
                    continue
                _attach(nodes, reach, nid, SOUL_TRAITS_PARENT, 1, toks)
                if d.get("axis") == "dyad":
                    # the dyad's axis: exhibited by both, instances in the committed
                    # record - the node says so (the view must distinguish exhibitors)
                    nodes[nid]["exhibited_by"] = d.get("exhibited_by", [])
                    nodes[nid]["axis"] = "dyad"
                all_toks |= toks
        reach[SOUL_TRAITS_PARENT] = all_toks


def load_network(repo_root: Path | str) -> dict[str, Any]:
    """The one network: the graded self tree (keeper) wired by the merged substrate edge-index
    (the ring's own recipe) + the sealed soul overlay + the MIND overlay (the post-condensed apex
    as routable topology - the same structure the view enters at, so view = mechanism holds for
    the fire too). Returns {nodes, reach, lenses, root} with root = the apex."""
    from laplace.engine import keeper
    repo_root = Path(repo_root)
    # the identity chain must be stable across calls: prefer the BANKED graded tree; only rebuild
    # when it is absent, and say so out loud when the fallback fires (his: the `... or build_self()`
    # fallback rebuilds nondeterministically). A banked graph -> a deterministic load.
    banked = keeper.load_tree_local(repo_root)
    degraded = False
    if banked:
        raw = banked
    else:
        # RW-20260711-104729-600001: the old silent `... or build_self()` fallback spun a
        # FULL nondeterministic rebuild here, so the identity chain depended on whether
        # .self_graded.json was present at call time (two runs, two chains). We refuse that:
        # a wake must never silently spin a full spectral rebuild. Print ONE loud line - the
        # missing file, the cause, the fix - and return a CHEAP DEGRADED network: the
        # dir_parent directory structure over the self-shard leaves, WITHOUT the
        # meaning_upfold clustering (never the spectral path). The dict is stamped
        # "degraded": True so a caller can refuse to trust it as an identity source.
        from laplace.engine import self_shard
        print(
            f"load_network: DEGRADED - no banked graded tree (.self_graded.json) at {repo_root}; "
            "returning the cheap dir_parent-only network WITHOUT meaning clustering "
            "(never the spectral rebuild). Bank the real graph: run scripts/reembed.py "
            "(the close deposit).",
            file=sys.stderr,
        )
        raw = keeper.build_tree(self_shard.shard_repo(repo_root))
        degraded = True
    nodes = {k: dict(v) for k, v in raw.items()}
    reach = build_reach(nodes, _self_edge_index(repo_root))
    _soul_overlay(repo_root, nodes, reach)
    # the audited wires (N29): an accepted geometric-only find taught the symbols its query
    # tokens - merged here so the why-handle, the lexical channel and the embedding text all
    # see them (the node re-embeds via the content hash; the wire becomes symbol AND geometry).
    from laplace.representation import embed_router
    for nid, toks in embed_router.load_learned_keywords(repo_root).items():
        if nid in nodes:
            n = nodes[nid]
            n["keywords"] = sorted(set(n.get("keywords") or []) | set(toks))
            n["coverage"] = sorted(set(n.get("coverage") or []) | set(toks))
    lenses = {nid: node_lenses(nid, n) for nid, n in nodes.items()}
    tree_root = next((k for k, v in nodes.items() if v.get("parent") is None), "")
    _mind_overlay(repo_root, nodes, reach, lenses, tree_root)
    # the cross-lens identity resolver (his build, 2026-06-13): fuse each entity's per-lens portraits
    # into one `person://` apex and inject a shared identity atom so they couple on the SAME reach the
    # recall / navigator / generation pull reads. In the build, so every ingest/close re-resolves and
    # the apex enriches itself. Guarded inside; a failure leaves the unfused network intact.
    from laplace.engine import identity_lens
    identity_lens.identity_overlay(repo_root, nodes, reach, lenses)
    # the cross-program technique resolver (his build, 2026-06-13): the conjugate of the identity
    # overlay - fuse the same TECHNIQUE across authors/programs (by the MEANING of each rung, not its
    # name) into one `technique://` apex + a shared coupling atom, and lift the generators' `moves`
    # to conjectural technique-transfer edges. After the identity overlay so a rung already wears its
    # person/physics lenses before it gains its technique uplink. Guarded inside; a failure leaves
    # the network without a technique layer, never broken.
    from laplace.engine import technique_lens
    technique_lens.technique_overlay(repo_root, nodes, reach, lenses)
    net = {"nodes": nodes, "reach": reach, "lenses": lenses,
           "repo_root": str(repo_root),
           "root": MIND if MIND in nodes else tree_root}
    # Only the DEGRADED path stamps the flag; the normal banked-tree path returns the
    # dict byte-identically (no extra key), so callers that never degrade see no change.
    if degraded:
        net["degraded"] = True
    return net


# ---------------------------------------------------------------------------
# the two axes of a node - identity (depth) and interactions (width)
# ---------------------------------------------------------------------------

def identity_chain(net: dict[str, Any], nid: str) -> list[dict[str, Any]]:
    """The depth axis: the uplinks that say what a node IS a part of, root-first. Each link carries
    ``share`` - the parent's view of this child (what fraction of the parent's substrate the child
    constitutes) - the identity weight, read off the one formula."""
    nodes, reach = net["nodes"], net["reach"]
    chain: list[dict[str, Any]] = []
    cur = nid
    seen = {cur}
    while True:
        parent = nodes.get(cur, {}).get("parent")
        if parent is None or parent not in nodes or parent in seen:
            break
        c = coupling_directed(reach, parent, cur)
        chain.append({"id": parent, "grade": nodes[parent].get("grade", 0),
                      "share": round(c["out"], 4)})
        seen.add(parent)
        cur = parent
    chain.reverse()
    return chain


def _heading_handles(repo_root: Path | str, nid: str, grade: int) -> list[dict[str, Any]]:
    """A doc leaf's section handles: each ATX heading of the section level becomes a descendable
    child pointer with a 1-based line span (``path#Lstart-Lend``), carrying its heading text as an
    inline essence. So a reconstructor descends into a section slice instead of flat-reading the
    file (his: 'doc nodes give no section handles'). Fenced code blocks are skipped."""
    try:
        text = (Path(repo_root) / nid).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    lines = text.splitlines()
    heads: list[tuple[int, int, str]] = []          # (level, 1-based lineno, title)
    fence = False
    for i, ln in enumerate(lines, 1):
        if ln.lstrip().startswith("```"):
            fence = not fence
            continue
        if fence:
            continue
        m = _ATX_RX.match(ln)
        if m:
            heads.append((len(m.group(1)), i, m.group(2).strip()))
    if not heads:
        return []
    # the section level: '##' if any exist (the usual §), else the shallowest heading present.
    target = 2 if any(h[0] == 2 for h in heads) else min(h[0] for h in heads)
    boundaries = [lno for lvl, lno, _ in heads if lvl <= target]
    out: list[dict[str, Any]] = []
    for lvl, lno, title in heads:
        if lvl != target:
            continue
        nxt = next((b for b in boundaries if b > lno), len(lines) + 1)
        end = nxt - 1
        out.append({"id": f"{nid}#L{lno}-L{end}", "grade": grade, "leaf": True,
                    "share": 0.0, "n_children": 0, "span": [lno, end],
                    "heading": title, "essence": title})
    return out


def children_view(net: dict[str, Any], nid: str) -> list[dict[str, Any]]:
    """The descent handles: members one grade below, each with its share of this node's substrate
    (parent's view), descending - the biggest constituent first. A doc leaf with no member nodes
    falls back to its section (heading) handles so the descent never dead-ends at a flat read."""
    nodes, reach = net["nodes"], net["reach"]
    node = nodes.get(nid)
    if not node:
        return []
    out = []
    for m in node.get("members", []):
        if m not in nodes:
            continue
        c = coupling_directed(reach, nid, m)
        out.append({"id": m, "grade": nodes[m].get("grade", 0), "leaf": nodes[m].get("leaf", True),
                    "share": round(c["out"], 4), "n_children": len(nodes[m].get("members", []))})
    if out:
        out.sort(key=lambda x: (-x["share"], x["id"]))
        return out
    # no member nodes: a doc leaf still exposes descendable section handles (document order).
    repo_root = net.get("repo_root")
    if repo_root and node.get("leaf", True) and nid.rsplit(".", 1)[-1].lower() in _DOC_LEAF_SUFFIXES:
        return _heading_handles(repo_root, nid, node.get("grade", 0))
    return out


def _doc_freq(net: dict[str, Any]) -> tuple[dict[str, int], int]:
    """The substrate's document frequency: how many substrate-bearing nodes each token appears in,
    plus that node count (the IDF denominator). Computed once and cached on the net so the lateral
    floor costs nothing after the first fan."""
    cached = net.get("_doc_freq")
    if cached is not None:
        return cached
    df: dict[str, int] = {}
    n = 0
    for toks in net["reach"].values():
        if not toks:
            continue
        n += 1
        for t in set(toks):
            df[t] = df.get(t, 0) + 1
    net["_doc_freq"] = (df, n)
    return df, n


def _shared_carries_edge(shared: set[str], df: dict[str, int], n: int) -> bool:
    """The IDF floor (defect 3): >=2 shared tokens always carry an edge; a LONE shared token
    carries one only when it is distinctive - present in at most ``LATERAL_IDF_MAX_DOCFREQ`` of the
    substrate-bearing nodes. A common (low-IDF) token cannot, alone, forge a lateral pull."""
    if len(shared) >= 2:
        return True
    if len(shared) != 1:
        return False
    t = next(iter(shared))
    return df.get(t, 0) <= LATERAL_IDF_MAX_DOCFREQ * n


def lateral(net: dict[str, Any], nid: str, width: int = 12, lens: str | None = None,
            conjectural: bool = False, scope: str = "grade") -> list[dict[str, Any]]:
    """The width axis: the node's at-grade interactions, ranked by DIRECTIONAL strength (its own
    view, ``out``), cut at the pull width. ``lens`` restricts candidates to a lens (lens-specific
    pull); ``conjectural`` admits the grit links (ideation) or drops them (recall); ``scope`` is
    'siblings' (same parent) or 'grade' (the whole level). A single low-IDF shared token no longer
    carries an edge - the IDF floor (his calibration) keeps the fabric off common keywords."""
    nodes, reach, lenses = net["nodes"], net["reach"], net["lenses"]
    node = nodes.get(nid)
    if not node:
        return []
    g = node.get("grade", 0)
    if scope == "siblings":
        parent = node.get("parent")
        cands = [m for m in nodes.get(parent, {}).get("members", []) if m != nid] if parent in nodes else []
    else:
        cands = [k for k, v in nodes.items() if v.get("grade", -1) == g and k != nid]
    if lens:
        cands = [c for c in cands if lens in lenses.get(c, [])]
    df, n_docs = _doc_freq(net)
    ra = reach.get(nid, set())
    out = []
    for c in cands:
        shared = ra & reach.get(c, set())
        if not shared:
            continue
        cp = coupling_directed(reach, nid, c)
        if cp["conjectural"] and not conjectural:
            continue
        # the IDF floor gates the SUBSTANTIVE fabric only; conjecture:: grit is a deliberate
        # single-token ideation bridge, already gated by the conjectural switch above.
        if not cp["conjectural"] and not _shared_carries_edge(shared, df, n_docs):
            continue
        out.append({"id": c, "grade": g, "shared": cp["shared"],
                    "out": round(cp["out"], 4), "in": round(cp["in"], 4),
                    "conjectural": cp["conjectural"], "lenses": lenses.get(c, [])})
    out.sort(key=lambda x: (-x["out"], x["id"]))
    return out[:max(0, int(width))]


def resolve_knobs(width: int | None = None, lens: str | None = None,
                  conjectural: bool | None = None, phase: str | None = None) -> dict[str, Any]:
    """The dimensionalised pull radius: explicit knobs override; a phase preset fills the rest.
    A couple of mechanical parameters per level - ways to move between thinking phases."""
    preset = PHASES.get(phase or "", PHASES["survey"])
    return {
        "width": width if width is not None else preset["width"],
        "lens": lens if lens is not None else None,
        "lens_locked": preset["lens_locked"] if lens is None else True,
        "conjectural": conjectural if conjectural is not None else preset["conjectural"],
        "phase": phase or ("custom" if any(v is not None for v in (width, lens, conjectural)) else "survey"),
    }


def node_view(net: dict[str, Any], nid: str, width: int | None = None, lens: str | None = None,
              conjectural: bool | None = None, phase: str | None = None,
              scope: str = "grade") -> dict[str, Any]:
    """The node as a two-axis cross-section: identity (uplinks), constituents (downlinks), and
    interactions (the lateral pull under the current knobs) + lens badges + flags. This is what a
    reconstruction FROM this node would see; the scanner renders it; the two never diverge."""
    nodes, lenses = net["nodes"], net["lenses"]
    node = nodes.get(nid)
    if not node:
        return {"error": f"unknown node: {nid}"}
    knobs = resolve_knobs(width, lens, conjectural, phase)
    eff_lens = knobs["lens"] if knobs["lens"] else (lenses.get(nid, [None])[0] if knobs["lens_locked"] else None)
    lat = lateral(net, nid, width=knobs["width"], lens=eff_lens,
                  conjectural=knobs["conjectural"], scope=scope)
    kids = children_view(net, nid)
    n_members = len(node.get("members", []))
    from laplace.engine.keeper import DEFAULT_WIDTH
    return {
        "id": nid,
        "grade": node.get("grade", 0),
        "leaf": node.get("leaf", True),
        "lenses": lenses.get(nid, []),
        # keyword hygiene (defect 2): drop pure stopword / path-noise tokens so a code leaf's
        # badges are content, not a bag of "the"/"and"/"py". Never emptied - if the filter would
        # leave nothing, the raw keywords stand (better a noisy handle than a blank one).
        "keywords": ([k for k in (node.get("keywords") or []) if k.lower() not in _VIEW_STOPWORDS]
                     or (node.get("keywords") or []))[:12],
        # the dyad's axes carry their exhibitors - the view must see who a trait is OF
        "axis": node.get("axis"),
        "exhibited_by": node.get("exhibited_by", []),
        "identity": identity_chain(net, nid),
        "children": kids,
        "lateral": lat,
        "knobs": {**knobs, "lens_effective": eff_lens, "scope": scope},
        "flags": {
            "too_wide": n_members > DEFAULT_WIDTH,
            "singleton": not lat and not node.get("leaf", True),
            "sealed": "soul" in lenses.get(nid, []),
        },
        "substrate_size": len(net["reach"].get(nid, set())),
        # the both-directions door (assets.yaml close-examination seal): every asset whose
        # nodes_supported reaches this node doors BACK to the named asset in /assets. The
        # forward doors (a landing → the reader, a node → the conceptric) already ride
        # /assets/object; this is the return leg, so the two surfaces cross-reference.
        "assets": _assets_for_node(net, nid),
    }


def _build_asset_backindex(name: str, repo_root: str | None) -> dict[str, list[dict]]:
    """node id → the assets that support it, each a door to the named asset in /assets.
    Built once per net (filesystem-cheap enumeration); degrades to an empty index when the
    project resolves no asset roster — the door is simply absent, never a fabricated one."""
    from urllib.parse import quote as _quote
    idx: dict[str, list[dict]] = {}
    try:
        from laplace.pipeline import asset_model as _am
        assets = _am.enumerate_assets(name)
    except Exception:  # noqa: BLE001 — an unresolvable roster leaves the return leg absent
        return idx
    for a in assets or []:
        door = {"id": a.id, "kind": a.kind,
                "href": f"/assets?corpus={_quote(name, safe='')}&asset={_quote(a.id, safe='')}"}
        targets = set(getattr(a, "nodes_supported", None) or [])
        if getattr(a, "node_id", None):
            targets.add(a.node_id)
        for n in targets:
            idx.setdefault(n, []).append(door)
    return idx


def _assets_for_node(net: dict[str, Any], nid: str) -> list[dict]:
    """The assets that door back to ``nid`` — from a reverse index cached on the net. Empty
    when the net carries no corpus identity (built without name), so the view path stays as
    light as before for the self network and any nameless build."""
    name = net.get("name")
    if not name:
        return []
    idx = net.get("_assets_by_node")
    if idx is None:
        idx = _build_asset_backindex(name, net.get("repo_root"))
        net["_assets_by_node"] = idx
    return idx.get(nid, [])


def resolve_name(net: dict[str, Any], query: str, k: int = 8) -> list[tuple[int, str]]:
    """Approximate id resolution for reconstruction: score every node by keyword overlap with
    the query plus a path-substring boost, so a near-exact NAME - a function, a file stem, a
    canon slug the caller knows but not as the full node id - surfaces its node. The conjugate
    of ``self_shard.reconstruct_by_name`` (which reads self_shard's own index), run here against
    the live keeper net so the one reconstruction path (``reconstruct_node`` / the CLI) answers a
    name, not only an exact id. Ranked (score desc, id asc); empty when nothing overlaps."""
    from laplace.pipeline.canon import _tokenize
    q = _tokenize(query)
    ql = query.lower().strip()
    scored: list[tuple[int, str]] = []
    for cand, node in net["nodes"].items():
        score = len(q & set(node.get("keywords") or []))
        if ql and ql in cand.lower():
            score += 5
        if score:
            scored.append((score, cand))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return scored[:k]


def reconstruct_node(net: dict[str, Any], nid: str, grade: int | None = None,
                     width: int | None = None, lens: str | None = None,
                     radius: float | None = None, conjectural: bool | None = None,
                     phase: str | None = None, scope: str = "grade",
                     cross_lens: bool = True) -> dict[str, Any]:
    """THE reconstruction primitive: the local view of the global conceptric FROM a node - at a
    grade, through a lens, tuned to a CORRELATION RADIUS, with CROSS-LENS couplings surfaced. This
    is the one object with two faces (his unification 2026-06-13): what a node fires into when it
    reconstructs itself, AND what the navigator renders - so what he sees and what the
    reconstructors see is provably the same thing (view == mechanism). A generalisation of
    node_view, adding the two knobs node_view lacked: the correlation-radius cut (keep couplings at
    or above a STRENGTH, not a fixed top-N - 'tune your vision of the node to its correlation
    radius') and the cross-lens bridges (where this node couples OUT of its own lens - 'see
    cross-lens correlation'). A firing calls this on its node; it does not read a baked brief.

    A caller who names an object by an approximate NAME (a function, a file stem, a canon slug -
    what an agent dispatched ``reconstruct(node, goal)`` actually knows) rather than its exact
    node id still resolves: on an exact-id miss the name is scored against the net (``resolve_name``)
    and a DECISIVE winner is reconstructed with ``resolved_from`` stamped; an ambiguous miss returns
    ``did_you_mean`` candidates rather than dead-ending on 'unknown node' or silently mis-picking."""
    if nid not in net["nodes"]:
        cands = resolve_name(net, nid)
        top = cands[0] if cands else None
        # decisive = an exact-ish substring hit (>=5), or a clear top over the runner-up
        decisive = bool(top) and (top[0] >= 5
                                  or (top[0] >= 2 and (len(cands) == 1 or top[0] > cands[1][0])))
        if decisive:
            resolved = reconstruct_node(net, top[1], grade=grade, width=width, lens=lens,
                                        radius=radius, conjectural=conjectural, phase=phase,
                                        scope=scope, cross_lens=cross_lens)
            resolved["resolved_from"] = nid
            resolved["candidates"] = [{"id": c, "score": s} for s, c in cands]
            return resolved
        return {"error": f"unknown node: {nid}",
                "did_you_mean": [{"id": c, "score": s} for s, c in cands]}
    # THE CONSUMPTION DEFAULT (2026-08-20): an unqualified `reconstruct(node, goal)` is a reader
    # CONSUMING the node, not the navigator browsing it, so its default phase is `consume`
    # (CONSUMPTION_WIDTH) rather than node_view's `survey`. An explicit width, phase or radius all
    # still win - this only replaces the width a caller never named. node_view itself is untouched:
    # the render keeps his survey calibration.
    view = node_view(net, nid, width=width, lens=lens, conjectural=conjectural,
                     phase=phase or ("consume" if width is None else None), scope=scope)
    if "error" in view:
        return view
    # correlation radius: cut the lateral fabric by coupling STRENGTH (directional out), so the
    # node sees only what is genuinely within its pull radius - not everything at the grade.
    if radius is not None:
        view["lateral"] = [l for l in view["lateral"] if l.get("out", 0.0) >= radius]
    view["radius"] = radius
    # cross-lens bridges: this node's at-grade couplings into OTHER lenses than its own - the
    # correlations a single-lens descent can never show. Computed over a wide conjectural sweep.
    if cross_lens:
        own = set(net["lenses"].get(nid, []))
        wide = lateral(net, nid, width=width or 24, conjectural=True, scope="grade")
        bridges: dict[str, list[dict[str, Any]]] = {}
        for c in wide:
            for other in (L for L in c.get("lenses", []) if L not in own):
                bridges.setdefault(other, []).append(
                    {"id": c["id"], "out": c["out"], "shared": c["shared"]})
        view["cross_lens"] = [
            {"lens": L, "n": len(v), "neighbours": sorted(v, key=lambda x: -x["out"])[:6]}
            for L, v in sorted(bridges.items(), key=lambda kv: -len(kv[1]))]
    # the cross-lens identity ring-UP: the `person://` apex(es) this node is a portrait of (set by
    # identity_lens). A portrait keeps its native tree parent; this is an ADDITIONAL uplink to the
    # fused self, so a firing on one lens-portrait can ring up to the person and back down the others
    # - the path that lets generation think with the whole entity, not one lens of it.
    apexes = net["nodes"].get(nid, {}).get("identities") or []
    if apexes:
        ids = []
        for a in apexes:
            an = net["nodes"].get(a)
            if an is None:
                continue
            # carry the SIBLING portraits (this entity in its OTHER lenses) directly, so a firing on
            # one lens reaches the whole person in a single pull - the correlates ride in, they are
            # not one hop away. Bounded; ranked by the sibling's reach (its richest portrait first).
            sibs = sorted((m for m in an.get("members", []) if m != nid and m in net["nodes"]),
                          key=lambda m: -len(net["reach"].get(m, set())))
            ids.append({"id": a, "essence": an.get("essence", ""),
                        "lenses": an.get("resolved_lenses", []),
                        # the richest portraits first (by reach); cap high enough that a whole person's
                        # cross-lens correlates ride in without truncation (the clean-room's one finding)
                        "correlates": [{"id": s, "lenses": net["lenses"].get(s, [])} for s in sibs[:16]]})
        view["identities"] = ids
    # the cross-program technique ring-UP (set by technique_lens): the `technique://` apex(es) this
    # rung is an instance OF. The conjugate of `identities` - where that rings up to the same PERSON
    # across lenses, this rings up to the same TECHNIQUE across authors/programs, carrying the
    # co-wielders (who else does this technique) directly so an expertise pull or a generation fire
    # reaches them in one hop - the cross-author correlates ride in.
    tech_apexes = net["nodes"].get(nid, {}).get("techniques") or []
    if tech_apexes:
        techs = []
        for a in tech_apexes:
            an = net["nodes"].get(a)
            if an is None:
                continue
            sibs = sorted((m for m in an.get("members", []) if m != nid and m in net["nodes"]),
                          key=lambda m: -len(net["reach"].get(m, set())))
            techs.append({"id": a, "essence": an.get("essence", ""),
                          "cross_author": an.get("cross_author", False),
                          "authors": an.get("resolved_authors", []),
                          "correlates": [{"id": s, "lenses": net["lenses"].get(s, [])} for s in sibs[:16]]})
        view["techniques"] = techs
    # the lifted technique-transfer edges (the `moves`, conjectural - the creativity seed): where a
    # theme SENT a technique to another program, and where it RECEIVED one. Bounded; carries the
    # author's own `why` so an ideation pull can follow the transfer.
    nd = net["nodes"].get(nid, {})
    if nd.get("transfers"):
        view["transfers"] = nd["transfers"][:12]
    if nd.get("transferred_into"):
        view["transferred_into"] = nd["transferred_into"][:12]
    # the grade axis: the view ENTERS at this node's grade and the descent handles carry the
    # levels (identity = grades up, children = the grade below). target_grade is where a caller
    # wants to land; the navigator drives it by descending children, a firing by re-calling here.
    view["entry_grade"] = view["grade"]
    view["target_grade"] = grade if grade is not None else view["grade"]
    return view


# ---------------------------------------------------------------------------
# the grade-flat projection - the lateral fabric at one grade (his ruling:
# the vertical map shows descent; exploration wants the horizontal couplings)
# ---------------------------------------------------------------------------

def grade_view(repo_root: Path | str, net: dict[str, Any], grade: int,
               lens: str | None = None, cap: int = 160, k: int = 6) -> dict[str, Any]:
    """The flat network AT one grade: its nodes (capped, largest substrate first) and each node's
    top-``k`` directional lateral couplings - the horizontal fabric the vertical map cannot show.
    Served, never recomputed client-side (view = mechanism)."""
    nodes, lenses = net["nodes"], net["lenses"]
    ids = [i for i, n in nodes.items() if n.get("grade", -1) == grade]
    if lens:
        ids = [i for i in ids if lens in lenses.get(i, [])]
    ids.sort(key=lambda i: -len(net["reach"].get(i, set())))
    ids = ids[:cap]
    id_set = set(ids)
    out_nodes = []
    edges = []
    seen_edges: set[tuple[str, str]] = set()
    for nid in ids:
        out_nodes.append({"id": nid, "label": nid.rstrip("/").split("/")[-1] or "(root)",
                          # kind + grade ride each slice node so the board card can wear its
                          # kind badge WITHOUT a per-card content fetch (W3: the board owns the
                          # centre, node cards wear kind badges — the mock's D5 contract). grade
                          # is the slice grade for every node here; carried so the card is
                          # self-describing when read off the wire.
                          "kind": nodes[nid].get("kind"),
                          "grade": nodes[nid].get("grade", grade),
                          "essence": essence(repo_root, net, nid),
                          "n_below": len(nodes[nid].get("members", [])),
                          "substrate_size": len(net["reach"].get(nid, set())),
                          "lenses": lenses.get(nid, [])})
        for e in lateral(net, nid, width=k, conjectural=True, scope="grade"):
            if e["id"] not in id_set:
                continue
            key = tuple(sorted((nid, e["id"])))
            if key in seen_edges:
                continue
            seen_edges.add(key)
            edges.append({"a": nid, "b": e["id"], "out": e["out"], "in": e["in"],
                          "shared": e["shared"], "conjectural": e["conjectural"]})
    return {"grade": grade, "lens": lens, "nodes": out_nodes, "edges": edges,
            "n_total_at_grade": len([i for i, n in nodes.items() if n.get("grade", -1) == grade]),
            "capped": len(ids) < len([i for i, n in nodes.items() if n.get("grade", -1) == grade])}


def explode(repo_root: Path | str, net: dict[str, Any], nid: str, k: int = 6) -> dict[str, Any]:
    """Explode one node in the flat view: its CHILDREN in the grade below, the children's links to
    EACH OTHER (the intra-cluster fabric), and the node's UPLINKS (identity) - both axes revealed
    in place. Children pair-coupled exhaustively (bounded by the width cap)."""
    nodes = net["nodes"]
    node = nodes.get(nid)
    if node is None:
        return {"id": nid, "error": "unknown node"}
    kids = children_view(net, nid)[:24]
    kid_ids = [c["id"] for c in kids]
    children = [{**c, "label": c["id"].rstrip("/").split("/")[-1],
                 "essence": essence(repo_root, net, c["id"])} for c in kids]
    inner = []
    for i, a in enumerate(kid_ids):
        for b in kid_ids[i + 1:]:
            c = coupling_directed(net["reach"], a, b)
            if c["shared"]:
                inner.append({"a": a, "b": b, "out": c["out"], "in": c["in"],
                              "shared": c["shared"], "conjectural": c["conjectural"]})
    inner.sort(key=lambda e: -e["shared"])
    return {"id": nid, "grade": node.get("grade", 0),
            "essence": essence(repo_root, net, nid),
            "children": children, "inner_edges": inner[:120],
            "uplinks": identity_chain(net, nid),
            "lateral": lateral(net, nid, width=k, conjectural=True, scope="grade")}


# ---------------------------------------------------------------------------
# the phi panel - per-grade normalized strength distributions (watched, not imposed)
# ---------------------------------------------------------------------------

def _grade_spectral(ids: list[str], reach: dict[str, set[str]], cap: int = 120,
                    iters: int = 60) -> dict[str, Any]:
    """The grade's spectral radius lambda0 (Perron root of the directional coupling sub-matrix,
    largest-substrate nodes sampled) + psi = log_n lambda0 (F1's literal object). HIS RULING
    (2026-06-10): the enrichment policy / pull gain IS the grade spectral radius, tunable -
    lambda0 > 1 means a recursive pull at this grade amplifies (loops deepen before surfacing),
    < 1 means it damps (straight up-and-down recall). WATCHED here; tuned nowhere yet - the
    thinking-level signals are learned from use, synthetics will give the clue (his)."""
    import math
    sample = sorted(ids, key=lambda i: -len(reach.get(i, set())))[:cap]
    n = len(sample)
    if n < 2:
        return {"lambda0": 0.0, "psi": 0.0, "n_sampled": n}
    rows: list[list[float]] = []
    for a in sample:
        ra = reach.get(a, set())
        row = []
        for b in sample:
            if a == b or not ra:
                row.append(0.0)
            else:
                shared = len(ra & reach.get(b, set()))
                row.append(shared / len(ra) if shared else 0.0)
        rows.append(row)
    v = [1.0 / n] * n
    lam = 0.0
    for _ in range(iters):
        w = [sum(rows[i][j] * v[j] for j in range(n)) for i in range(n)]
        nrm = max(w) if w else 0.0
        if nrm <= 1e-12:
            return {"lambda0": 0.0, "psi": 0.0, "n_sampled": n}
        lam = nrm
        v = [x / nrm for x in w]
    psi = math.log(lam) / math.log(n) if lam > 0 else 0.0
    return {"lambda0": round(lam, 4), "psi": round(psi, 4), "n_sampled": n}


def phi_panel(net: dict[str, Any], sample_cap: int = 400) -> dict[str, Any]:
    """Per grade: node count, width stats, the distribution of sibling out-strengths, and the
    grade SPECTRAL RADIUS (the pull gain - his ruling; see ``_grade_spectral``). Clustering
    should FLATTEN the distribution as the grades climb (steep floor -> flat apex); the panel
    shows the trajectory and imposes no exponent (his ruling). Sibling-scoped and sampled so
    the panel stays cheap on a large floor."""
    nodes, reach = net["nodes"], net["reach"]
    by_grade: dict[int, list[str]] = {}
    for k, v in nodes.items():
        by_grade.setdefault(v.get("grade", 0), []).append(k)
    panel = []
    for g in sorted(by_grade):
        ids = by_grade[g]
        widths = [len(nodes[i].get("members", [])) for i in ids if not nodes[i].get("leaf", True)]
        strengths: list[float] = []
        for nid in ids[:sample_cap]:
            parent = nodes[nid].get("parent")
            if parent not in nodes:
                continue
            sibs = [m for m in nodes[parent].get("members", []) if m != nid][:24]
            for s in sibs:
                c = coupling_directed(reach, nid, s)
                if c["shared"]:
                    strengths.append(c["out"])
        strengths.sort()
        n = len(strengths)
        panel.append({
            "grade": g, "n_nodes": len(ids),
            "n_internal": len(widths), "max_width": max(widths, default=0),
            "mean_width": round(sum(widths) / len(widths), 2) if widths else 0,
            "n_couplings": n,
            "strength_median": round(strengths[n // 2], 4) if n else 0.0,
            "strength_p90": round(strengths[int(n * 0.9)], 4) if n else 0.0,
            "strength_mean": round(sum(strengths) / n, 4) if n else 0.0,
            **_grade_spectral(ids, reach),
        })
    return {"grades": panel,
            "note": "phi is watched, not imposed - the flattening trajectory, no exponent; "
                    "lambda0 = the grade's pull gain (his ruling 2026-06-10: enrichment policy = "
                    "grade spectral radius, tunable, learned from use)"}


def lens_grade_matrix(net: dict[str, Any]) -> dict[str, Any]:
    """The lens x grade DENSITY MATRIX - the watched instrument for the grade-distribution
    diagnosis (his, 2026-06-11): one universal grade ladder forces lenses of enormously
    different densities through the same rungs, so the distribution is miles off. Per-lens
    grade histograms make the maldistribution VISIBLE before any reshape is ruled - per-lens
    ladders stay conjecture until this shows the shape. Counts only; watched, never imposed."""
    nodes, lenses = net["nodes"], net["lenses"]
    grades = sorted({v.get("grade", 0) for v in nodes.values()})
    matrix: dict[str, dict[str, int]] = {}
    for nid, node in nodes.items():
        g = str(node.get("grade", 0))
        for ln in lenses.get(nid, ["world"]):
            row = matrix.setdefault(ln, {})
            row[g] = row.get(g, 0) + 1
    rows = []
    for ln, hist in sorted(matrix.items(), key=lambda kv: -sum(kv[1].values())):
        total = sum(hist.values())
        peak = max(hist.values(), default=0)
        depth = max((int(g) for g, c in hist.items() if c), default=0)
        rows.append({"lens": ln, "total": total, "depth": depth,
                     "peak": peak, "hist": {g: hist.get(g, 0) for g in map(str, grades)}})
    return {"grades": [str(g) for g in grades], "rows": rows,
            "note": "per-lens grade densities, counts only - the evidence the per-lens-ladder "
                    "ruling needs; watched, not imposed"}


# ---------------------------------------------------------------------------
# the mind view - enter at the post-condensed apex (his ruling, 2026-06-10:
# view-from-the-condensed-apex). Built UP, viewed DOWN: the apex decomposes into
# the top-level lenses; each lens descends its own grading; substrate is where a
# descent BOTTOMS, never where a view starts. Ancestry, not parent/child.
# ---------------------------------------------------------------------------

MIND = "mind://"
LENS_PREFIX = "mind://lens/"
STANDING = "mind://standing"

# The fixed point's sources - what the hello reconstructs from; surfaced FIRST under the apex.
_STANDING_SOURCES = ["HANDOFF.md", "EIGEN_PROTOCOL.md", "AGENTS.md", "TECHNICAL_GUIDE.md",
                     "ATLAS_DEVELOPMENT_STATE.md", "OPEN_STACK.md", "CLAUDE.md", "EIGEN_DIARY.md"]


def _standing_essence(repo_root: Path | str) -> str:
    """The current aim's headline, read live from HANDOFF.md - the top of the mind."""
    try:
        head = (Path(repo_root) / "HANDOFF.md").read_text(encoding="utf-8", errors="replace")[:6000]
    except OSError:
        return "the standing goals and instructions (HANDOFF.md unavailable)"
    for line in head.splitlines():
        if line.startswith("## ⟶ NEXT SESSION AIM"):
            return line.lstrip("# ").strip()[:160]
    return "the standing goals and instructions - the fixed point the hello reconstructs"

_LENS_ESSENCE = {
    "engine": "the machinery - the engine's own code and tests",
    "physics": "the concept corpus - pillars, themes, papers, atoms",
    "people": "the relational world - collaborators and the soul's entities",
    "soul": "the sealed soul - his record, entities, the raw vessel (visible locally)",
    "values": "the binding ring - recurring traits across his world and his record",
    "self-record": "the engine's own memory - handoffs, diary, the open stack",
    "world": "everything else the tree holds - the unlensed remainder",
    "substrate": "the raw floor - windows and atoms reconstruction bottoms at",
}


def lens_roots(net: dict[str, Any]) -> dict[str, list[str]]:
    """Where each lens BEGINS: the nodes wearing a lens whose ancestor does not - the natural
    entry points one level below the apex. Grades and lenses unify here: the apex's first
    decomposition IS the lens set, and a lens's own tree descends from its roots."""
    nodes, lenses = net["nodes"], net["lenses"]
    roots: dict[str, list[str]] = {}
    for nid, node in nodes.items():
        for ln in lenses.get(nid, []):
            parent = node.get("parent")
            if parent is None or ln not in lenses.get(parent, []) or parent == net["root"]:
                roots.setdefault(ln, []).append(nid)
    for ln in roots:
        roots[ln].sort(key=lambda i: -len(net["reach"].get(i, set())))
    return roots


def _mind_overlay(repo_root: Path | str, nodes: dict[str, dict[str, Any]],
                  reach: dict[str, set[str]], lenses: dict[str, list[str]],
                  tree_root: str) -> None:
    """The post-condensed apex MATERIALISED as routable topology: ``mind://`` decomposes into
    STANDING (the fixed point's sources, first - his ruling, ``navigator-is-the-future-hello``)
    and the lens entries; each carries members, an ascended handle (the keeper's own promotion
    rule - nothing hand-planted), unioned coverage (so the lexical ring descends it too) and
    unioned reach (so the coupling math sees it). The view's ``expand`` reads THIS - one
    structure, entered by the eye and by the fire alike."""
    from laplace.engine.keeper import promote_keywords
    top = max((n.get("grade", 0) for n in nodes.values()), default=1)
    roots = lens_roots({"nodes": nodes, "reach": reach, "lenses": lenses, "root": tree_root})

    def _cov(ids: list[str]) -> list[str]:
        cov: set[str] = set()
        for i in ids:
            n = nodes.get(i, {})
            cov.update(n.get("coverage") or n.get("keywords") or [])
        return sorted(cov)

    def _attach_mind(nid: str, parent: str | None, grade: int, members: list[str],
                     essence_line: str) -> None:
        nodes[nid] = {"id": nid, "grade": grade, "kind": "mind", "parent": parent,
                      "leaf": False, "members": members, "essence": essence_line,
                      "keywords": promote_keywords([nodes[m].get("keywords") or [] for m in members]),
                      "coverage": _cov(members), "sealed": False}
        reach[nid] = set().union(*(reach.get(m, set()) for m in members)) if members else set()
        lenses[nid] = ["self-record"] if nid == STANDING else (
            [nid[len(LENS_PREFIX):]] if nid.startswith(LENS_PREFIX) else ["world"])

    mind_members: list[str] = []
    standing_members = [s for s in _STANDING_SOURCES if s in nodes]
    if standing_members:
        _attach_mind(STANDING, MIND, top + 1, standing_members, _standing_essence(repo_root))
        mind_members.append(STANDING)
    order = ["self-record", "values", "people", "soul", "physics", "engine", "world", "substrate"]
    for ln in order:
        if not roots.get(ln):
            continue
        lid = LENS_PREFIX + ln
        _attach_mind(lid, MIND, top + 1, roots[ln], _LENS_ESSENCE.get(ln, "a top-level lens"))
        mind_members.append(lid)
    if mind_members:
        _attach_mind(MIND, None, top + 2, mind_members,
                     "the post-condensed apex - everything, at a glance; descend for detail")


def _first_text(path: Path, cap: int = 2048) -> str:
    try:
        head = path.read_text(encoding="utf-8", errors="replace")[:cap]
    except OSError:
        return ""
    for line in head.splitlines():
        if line.startswith("#!"):                # a shebang is not an essence (defect 2)
            continue
        s = line.strip().lstrip("#").strip().strip('"').strip("'")
        if len(s) > 8 and not s.startswith(("---", "<!--", "from ", "import ", "{", "[")):
            return s[:140]
    return ""


def _py_essence(path: Path, max_syms: int = 8) -> str:
    """A code leaf's real handle (defect 2): the module docstring's first sentence + its top-level
    def/class names - the symbols, not a stopword bag or the shebang. Parsed with ``ast`` (never
    executed); a syntax error falls back to a regex sweep for the same signatures."""
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    doc = ""
    syms: list[str] = []
    try:
        import ast
        tree = ast.parse(src)
        d = ast.get_docstring(tree)
        if d:
            first = d.strip().replace("\n", " ")
            doc = first.split(". ")[0].strip().rstrip(".")[:120]
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                syms.append(node.name)
    except (SyntaxError, ValueError):
        syms = re.findall(r"^(?:async\s+)?(?:def|class)\s+([A-Za-z_]\w*)", src, re.M)
    if not doc and not syms:
        return ""
    parts: list[str] = []
    if doc:
        parts.append(doc)
    if syms:
        shown = ", ".join(syms[:max_syms])
        parts.append("defines " + shown + (f" +{len(syms) - max_syms} more" if len(syms) > max_syms else ""))
    return " - ".join(parts)


def essence(repo_root: Path | str, net: dict[str, Any], nid: str) -> str:
    """A one-line content description for ANY node - nothing renders as a bare singleton (his
    rule). Mechanical: lens blurbs, file first-headings/docstrings, trait/entity handles, and
    composed links-down-to lines for internal grade handles."""
    repo_root = Path(repo_root)
    nodes = net["nodes"]
    if nid == MIND:
        return "the post-condensed apex - everything, at a glance; descend for detail"
    if nid == STANDING:
        return _standing_essence(repo_root)
    if nid.startswith(LENS_PREFIX):
        return _LENS_ESSENCE.get(nid[len(LENS_PREFIX):], "a top-level lens")
    if nid.startswith(SOUL_TRAITS_PARENT + "/"):
        if nodes.get(nid, {}).get("axis") == "dyad":
            return ("a trait of the dyad - exhibited by both, instances in the "
                    "committed record")
        return "a recurring trait in the binding ring - open for instances with verbatim sources"
    if nid == SOUL_TRAITS_PARENT:
        return "the value ring - traits clustered by recurrence across the folded world"
    if nid.startswith(SOUL_ENTITIES_PARENT + "/"):
        rest = [s for s in nid[len(SOUL_ENTITIES_PARENT) + 1:].split("/") if s]
        if len(rest) >= 3:                      # an entity ITEM: content-free here, always - the
            return (f"a sealed {rest[1]} item of {rest[0]} - "    # meaning rides the local
                    "content served to the local browser only")   # embedding, never the handle
        return "a folded soul entity (voice / history / relations) - sealed from git, visible here"
    if nid == SOUL_ENTITIES_PARENT:
        return "the folded soul entities - the people of his world, him the hub"
    node = nodes.get(nid, {})
    if node.get("sealed") and node.get("essence"):
        return node["essence"]              # a sealed handle speaks ONLY through its stored,
                                            # content-free line - never a read of the sealed file
    if "::" in nid and node.get("essence"):
        return node["essence"]              # a virtual atom carries its own handle (no file to read)
    if node.get("leaf", True):
        f = repo_root / nid
        if f.suffix == ".py":                       # a code leaf speaks in symbols, not stopwords
            sym = _py_essence(f)
            if sym:
                return sym
        if f.suffix in (".md", ".py", ".txt", ".tex", ".yaml", ".yml", ".mjs", ".html"):
            line = _first_text(f)
            if line:
                return line
        return f"a {f.suffix.lstrip('.') or 'file'} leaf at the substrate"
    if node.get("essence"):
        return node["essence"]              # the stored handle IS what the router embeds and
                                            # descends on - the view shows the mechanism's line
    members = node.get("members", [])[:4]
    tails = [m.rstrip("/").split("/")[-1] for m in members]
    more = len(node.get("members", [])) - len(tails)
    return ("links down to " + ", ".join(tails) + (f" +{more} more" if more > 0 else "")) if tails else "an empty grade handle"


def expand(repo_root: Path | str, net: dict[str, Any], nid: str = MIND) -> dict[str, Any]:
    """Progressive disclosure, ONE level at a time, viewed top-down: the node + its essence + the
    next level down (each member with label, essence, counts, share) - the at-a-glance contract:
    detail materialises only on hover (essence/tooltips) or descent (this call again)."""
    nodes, reach, lenses = net["nodes"], net["reach"], net["lenses"]

    def _entry(mid: str, share: float | None = None) -> dict[str, Any]:
        m = nodes.get(mid, {})
        return {
            "id": mid, "label": (mid.rstrip("/").split("/")[-1] or "(root)") if not mid.startswith("mind://") else mid.split("/")[-1],
            "essence": essence(repo_root, net, mid),
            "grade": m.get("grade"), "leaf": m.get("leaf", False) if mid in nodes else False,
            "n_below": len(m.get("members", [])) if mid in nodes else None,
            "substrate_size": len(reach.get(mid, set())),
            "lenses": lenses.get(mid, []) if mid in nodes else [],
            "share": share,
            "expandable": bool(m.get("members")) if mid in nodes else True,
        }

    # the apex levels read the MATERIALISED mind overlay when it exists (load_network builds it;
    # the fire descends the same nodes) - the view never constructs a private copy of the mind.
    # The standing child leads by construction (his ruling, navigator-is-the-future-hello).
    if nid == MIND:
        if MIND in nodes:
            return {"id": MIND, "label": "mind", "essence": essence(repo_root, net, MIND),
                    "view_depth": 0,
                    "members": [_entry(m) for m in nodes[MIND].get("members", [])],
                    "note": "viewed condensed->fine; built the other way (ancestry)"}
        roots = lens_roots(net)
        order = ["self-record", "values", "people", "soul", "physics", "engine", "world", "substrate"]
        members = [{**_entry(LENS_PREFIX + ln), "expandable": True,
                    "n_below": len(roots.get(ln, [])),
                    "substrate_size": sum(len(net["reach"].get(r, set())) for r in roots.get(ln, []))}
                   for ln in order if roots.get(ln)]
        members.insert(0, {
            "id": STANDING, "label": "standing", "essence": _standing_essence(repo_root),
            "grade": None, "leaf": False, "n_below": len(_STANDING_SOURCES),
            "substrate_size": 0, "lenses": ["self-record"], "share": None, "expandable": True,
        })
        return {"id": MIND, "label": "mind", "essence": essence(repo_root, net, MIND),
                "view_depth": 0, "members": members,
                "note": "viewed condensed->fine; built the other way (ancestry)"}
    if nid == STANDING:
        members = (nodes[STANDING].get("members", []) if STANDING in nodes
                   else [s for s in _STANDING_SOURCES
                         if s in nodes or (Path(repo_root) / s).is_file()])
        return {"id": STANDING, "label": "standing", "essence": _standing_essence(repo_root),
                "view_depth": 1, "members": [_entry(s) for s in members]}
    if nid.startswith(LENS_PREFIX):
        ln = nid[len(LENS_PREFIX):]
        roots = nodes[nid].get("members", []) if nid in nodes else lens_roots(net).get(ln, [])
        return {"id": nid, "label": ln, "essence": essence(repo_root, net, nid), "view_depth": 1,
                "members": [_entry(r) for r in roots[:40]],
                "n_total": len(roots)}
    node = nodes.get(nid)
    if node is None:
        return {"id": nid, "error": "unknown node"}
    kids = children_view(net, nid)
    return {"id": nid, "label": nid.rstrip("/").split("/")[-1] or "(root)",
            "essence": essence(repo_root, net, nid),
            "grade": node.get("grade"), "leaf": node.get("leaf", True),
            "members": [_entry(k["id"], k["share"]) for k in kids],
            "lenses": lenses.get(nid, [])}


def fire_by_grade(repo_root: Path | str, net: dict[str, Any], goal: str,
                  floor: int | None = None, limit: int = 10,
                  beam: int | None = None, per_branch_width: int | None = None,
                  path_decay: float | None = None,
                  ancestor_decay: float = ANCESTOR_DECAY,
                  use_metric: bool = True,
                  force_router: str | None = None, metric_override: Any = None,
                  record_proposals: bool = False) -> dict[str, Any]:
    """A prompt enters at the TOP and decomposes downward: graded recall, every hit carrying its
    full descent path, the recovery grouped BY GRADE so the descent is readable. ``floor`` is the
    GRANULARITY control: each path is truncated at the chosen grade, so the recovery comes back as
    the handle AT that depth (substrate only when the task truly needs it). The mouth - a semantic
    parse into multiple queries - is the next slice; this routes one query grade-by-grade.

    Routing is the EMBEDDING ROUTER (cosine-guided descent, ``embed_router.route``); when no model
    is available it falls back to the lexical ring, and the return says which router fired - the
    view must never imply geometry that didn't run.

    ``beam``/``per_branch_width``/``path_decay`` turn the router's descent geometry per fire
    (None = the router's standing defaults); ``ancestor_decay`` turns how fast salience fades up
    a hit's own path. The fired values ride back in ``geometry`` - the cockpit's live controls
    are these parameters, on the engine's own call, never a view-side re-computation.

    ``use_metric=False`` fires raw cosine (no trained M); ``force_router='lexical'`` fires the
    lexical ring outright. Together they are the comparison fire's variants - reorganisation
    on/off as the engine's own switch, so 'with vs without' is two real fires, never a view."""
    from laplace.representation import embed_router
    from laplace.engine import keeper
    repo_root = Path(repo_root)
    nodes = net["nodes"]
    rkw: dict[str, Any] = {"limit": limit, "use_metric": use_metric}
    if metric_override is not None:
        rkw["metric_override"] = metric_override
    if record_proposals:
        rkw["record_proposals"] = True
    if beam is not None:
        rkw["beam"] = beam
    if per_branch_width is not None:
        rkw["per_branch_width"] = per_branch_width
    if path_decay is not None:
        rkw["path_decay"] = path_decay
    rec = None if force_router == "lexical" else embed_router.route(repo_root, net, goal, **rkw)
    if rec is None:
        rec = keeper.recall(nodes, goal, start=net.get("root", ""), limit=limit)
        rec["router"] = "lexical" if force_router == "lexical" else "lexical-fallback"
    else:
        # THE IDENTITY CHANNEL: names are symbolic, and a two-common-word name embeds nowhere
        # near its entity - "Guy Skinner" pulled engine files at cos 0.50 while token overlap
        # found him instantly (the bench's first live catch, 2026-06-11). So the lexical ring
        # ALWAYS fires beside the geometry (it costs milliseconds and visits the relevant
        # subtree only) and the recall is salience-merged: geometry may find, the graph may
        # ALSO find - and every hit says which channel(s) reached it.
        from laplace.pipeline.canon import _tokenize
        lex = keeper.recall(nodes, goal, start=net.get("root", ""), limit=limit)
        q_tok = _tokenize(goal)
        geo_files = rec.get("files", [])
        for f in geo_files:
            if isinstance(f.get("why"), dict):
                f["why"]["channel"] = "both" if f["why"].get("lexical") else "geometric"
        geo_max = max((f.get("score", 0) for f in geo_files), default=0) or 1.0
        lex_files = list({f["file"]: f for f in lex.get("files", [])}.values())  # dedupe multi-path
        lex_max = max((f.get("score", 0) for f in lex_files), default=0) or 1.0
        seen = {f["file"] for f in geo_files}
        for f in lex_files:
            if f["file"] in seen:
                continue
            n = nodes.get(f["file"], {})
            overlap = sorted(q_tok & (set(n.get("keywords") or []) | set(n.get("coverage") or [])))
            geo_files.append({"file": f["file"], "cos": None,
                              "score": round(f.get("score", 0) / lex_max * geo_max, 4),
                              "path": [p for p in f.get("path", []) if p],
                              "why": {"channel": "lexical", "own_cos": None, "heat": None,
                                      "via": None, "via_heat": None, "geometric_only": False,
                                      "lexical": overlap[:8]}})
        geo_files.sort(key=lambda f: (-f.get("score", 0), f["file"]))
        rec["router"] = str(rec.get("router", "")) + "+lex"
    files = rec.get("files", [])
    max_score = max((h.get("score", 0) for h in files), default=0) or 1
    hits = []
    per_grade: dict[str, dict[str, dict[str, Any]]] = {}
    for h in files:
        path = [p for p in h.get("path", []) if p in nodes]
        if floor is not None:
            cut = [p for p in path if nodes[p].get("grade", 0) >= floor]
            recovered = cut[-1] if cut else (path[0] if path else h["file"])
            path = cut or path[:1]
        else:
            recovered = h["file"]
        # salience: closeness to the centre of the pull, mechanical (his rule) - the hit's
        # normalized score; ancestors on the path inherit it decayed per step above the recovery.
        sal = round(h.get("score", 0) / max_score, 3)
        steps = []
        n = len(path)
        for i, p in enumerate(path):
            s = round(sal * (ancestor_decay ** (n - 1 - i)), 3)
            steps.append({"id": p, "grade": nodes[p].get("grade", 0), "salience": s})
        hits.append({"recovered": recovered, "score": h.get("score", 0), "salience": sal,
                     "path": steps, "essence": essence(repo_root, net, recovered),
                     # the why-handle (geometry may find, the graph must explain): the hit's own
                     # evidence rides with it; absent under the lexical fallback (overlap IS its why)
                     "why": h.get("why"),
                     # everything needed to follow up (his rule): the handles to go deeper
                     "follow_up": {"expand": f"/network/mind?id={recovered}",
                                   "content": f"/network/content?id={recovered}",
                                   "cross_section": f"/network/node?id={recovered}"}})
        for st in steps:
            bucket = per_grade.setdefault(str(st["grade"]), {})
            prev = bucket.get(st["id"])
            if prev is None or st["salience"] > prev["salience"]:
                bucket[st["id"]] = {"id": st["id"], "salience": st["salience"],
                                    "essence": essence(repo_root, net, st["id"])}
    # salience-merge the router's DIRECT per-grade hits (every grade fired in parallel): a node
    # the geometry reached on its own merits joins its grade's bucket, max salience winning.
    for g, direct in (rec.get("per_grade_direct") or {}).items():
        bucket = per_grade.setdefault(g, {})
        for d in direct:
            prev = bucket.get(d["id"])
            if prev is None or d["salience"] > prev["salience"]:
                bucket[d["id"]] = {"id": d["id"], "salience": d["salience"],
                                   "essence": essence(repo_root, net, d["id"])}
    pg = {g: sorted(v.values(), key=lambda x: -x["salience"])
          for g, v in sorted(per_grade.items(), key=lambda kv: -int(kv[0]))}
    geometry = dict(rec.get("geometry") or {})
    geometry["ancestor_decay"] = float(ancestor_decay)
    geometry["floor"] = floor
    return {"goal": goal, "floor": floor, "n_visited": rec.get("visited"),
            "n_total": rec.get("total"), "router": rec.get("router", "lexical"),
            "geometry": geometry,
            "hits": hits, "per_grade": pg, "proposals": rec.get("proposals", []),
            "note": "one query routed grade-by-grade; salience = closeness to the pull's centre, "
                    "mechanical; the mouth (parse into multiple queries) is the next slice"}


# ---------------------------------------------------------------------------
# local display content - soul visible to the author (his ruling, 2026-06-10)
# ---------------------------------------------------------------------------

def node_content(repo_root: Path | str, nid: str, cap: int = 120_000) -> dict[str, Any]:
    """The node's CONTENT for the author's local display (memory ``soul-visible-locally-until-
    ready``): the scanner reads the file and serves HIS browser directly - no model context ever
    holds it, so the commit/return seal is untouched while he sees everything. Trait nodes return
    their instances (verbatim sources + locators); entity nodes their folded fields; file nodes
    their text, capped. Display-sealing returns when the judgement is ready, not by a gate here."""
    repo_root = Path(repo_root)
    if nid.startswith(SOUL_TRAITS_PARENT + "/"):
        stem = nid.rsplit("/", 1)[1] + ".json"
        f = repo_root / TRAITS_DIR / stem
        if not f.is_file():                       # the dyad's axes live in the committed dir
            f = repo_root / DYAD_TRAITS_DIR / stem
        if not f.is_file():
            return {"id": nid, "kind": "trait", "error": "trait file missing"}
        try:
            return {"id": nid, "kind": "trait", "content": json.loads(f.read_text(encoding="utf-8"))}
        except (OSError, json.JSONDecodeError) as exc:
            return {"id": nid, "kind": "trait", "error": str(exc)}
    if nid == SOUL_TRAITS_PARENT:
        f = repo_root / TRAITS_INDEX
        try:
            content = json.loads(f.read_text(encoding="utf-8")) if f.is_file() else []
        except (OSError, json.JSONDecodeError) as exc:
            return {"id": nid, "kind": "trait-index", "error": str(exc)}
        if not isinstance(content, list):
            content = [content]
        ddir = repo_root / DYAD_TRAITS_DIR        # the dyad's axes join the ring's index
        if ddir.is_dir():
            for df in sorted(ddir.glob("*.json")):
                if df.name.startswith("_"):
                    continue
                try:
                    d = json.loads(df.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                content.append({"trait": d.get("trait", df.stem), "axis": "dyad",
                                "exhibited_by": d.get("exhibited_by", []),
                                "recurrence": d.get("recurrence", 0)})
        return {"id": nid, "kind": "trait-index", "content": content}
    if nid.startswith(SOUL_ENTITIES_PARENT):
        from laplace.engine import soul_provenance
        rest = [s for s in nid[len(SOUL_ENTITIES_PARENT):].split("/") if s]
        if not rest:
            return {"id": nid, "kind": "entity-index",
                    "content": sorted(p.stem for p, _ in soul_provenance.iter_entities(repo_root))}
        if len(rest) >= 3 and rest[2].isdigit():
            # one field ITEM, served whole (head + note + locator) to the author's browser -
            # the smallest unit of person reconstruction, same seal posture as the profile.
            it = soul_provenance.item_of(repo_root, rest[0], rest[1], int(rest[2]))
            if it is None:
                return {"id": nid, "kind": "entity-item", "error": "item not found"}
            return {"id": nid, "kind": "entity-item", "stem": rest[0], "field": rest[1],
                    "index": int(rest[2]), "content": it}
        stem = rest[0]
        ent = soul_provenance.entities_by_stem(repo_root).get(stem)
        if ent is not None:
            p, d = ent
            return {"id": nid, "kind": "entity", "path": str(p.relative_to(repo_root)),
                    # the profile is a MECHANICAL render of the fold (no model) - served to
                    # the author's browser here, never reconstructed through the orchestrator
                    "profile": soul_provenance.render_entity_profile(d), "content": d}
        return {"id": nid, "kind": "entity", "error": "entity not found"}
    if "::" in nid:
        from laplace.engine import record_shard
        atom = record_shard.atom_content(repo_root, nid)    # the verbatim floor: the exact committed
        if atom is not None:                                # char range + its locator, never a paraphrase
            return atom
    f = repo_root / nid
    if f.is_file():
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return {"id": nid, "kind": "file", "error": str(exc)}
        return {"id": nid, "kind": "file", "truncated": len(text) > cap, "content": text[:cap]}
    return {"id": nid, "kind": "node", "error": "no content source (an internal grade handle)"}


# ---------------------------------------------------------------------------
# trace replay - what a reconstruction actually did (the diagnostic core)
# ---------------------------------------------------------------------------

def replay(limit: int = 20) -> list[dict[str, Any]]:
    """The recent reconstruction/trace events, oldest-first - the ordered calls, what was gathered
    and skipped, the verdicts. The scanner renders these as paths over the network, so a failing
    reconstruction can be SEEN: where it descended, what it pulled, where it flattened."""
    from laplace.engine import telemetry
    evs = [e for e in telemetry.events() if e.get("phase") in ("reconstruction", "trace")]
    return evs[-limit:]
