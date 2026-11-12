"""keeper.py - the recursive grade-keeper: the upward operator, unified over self and soul.

The link BETWEEN grades (the vital element the flat store missed). See KEEPER_ARCHITECTURE.md for the
full design: the ring (message rings down / enriches up), the recursive sealed self-call harness, and
the staged plan. This module is **Stage 1**: the mechanical graded BUILD - no LLM, deterministic.

The one operator: from grade-0 leaves + a STRUCTURAL parent function (directory for the self;
source/stream for the soul), build the graded conceptric bottom-up, grade-local. Each coarse node's
handle is ASCENDED from its children: keywords that **recur across siblings** are promoted into it
(Gerard's rule - anything used repeatedly is pushed up to the grade where it is used), and its members
(down) + parent (up) are wired so a grade-k reconstruction carries what it holds and the coarse
description of the grade above. The faithfulness gate is **LOCAL** (sample each node's members), never
the O(N^2) all-pairs sweep that made the flat self-shard build slow.

Stages 2-4 (the prompt-dependent ring, the sealed recursion, wiring the hello through it) build ON
this; they are NOT here. This stage is additive - it does not touch the live flat ``self_shard`` path,
so the running engine is unaffected until the ring is proven.
"""

from __future__ import annotations
from laplace.core.checkout import source_tree

import hashlib
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable

GRADED_LOCAL = ".self_graded.json"     # TRACKED per THE UNSEAL (PV-20260712-f11-the-unseal, 2026-07-12) -
                                        # the full graded tree; committed so reconstruction is DETERMINISTIC
                                        # across sessions (absent it, build_self re-derives a different
                                        # identity chain per call) - not a disposable regenerable cache
SKELETON = "SELF_GRADED_INDEX.md"      # committed - the coarse navigable view
DEFAULT_WIDTH = 24                     # a coarse node wider than this is reshape-flagged (phi proxy; his threshold)
PROMOTE_MIN = 2                        # a keyword recurring across >= this many children ascends (recurrence rule v1)
PROMOTE_CAP = 12                       # cap promoted keywords per coarse handle
HANDOFF_SERIES = "session-handoff-series"   # N28 - the dated handoffs graded as ONE series node


# ---------------------------------------------------------------------------
# the structural parent functions - one per substrate (the only per-substrate piece)
# ---------------------------------------------------------------------------

def dir_parent(node_id: str, root_id: str = "") -> str | None:
    """The SELF substrate's structural parent: a file's directory; a dir's parent; root -> None.
    Top-level items ascend to the root node (``root_id``, default '')."""
    nid = node_id.strip("/")
    if not nid:
        return None                 # the root has no parent
    if "/" not in nid:
        return root_id              # a top-level item -> root
    return nid.rsplit("/", 1)[0]


def series_parent(node_id: str) -> str | None:
    """N28: the dated session handoffs are ONE semantic object (mutual cosine ~0.825 - they flood
    any flat ranking), so they grade ``self-record -> session-handoff-series -> dated files``
    instead of sitting as N top-level leaves. F22's version-series precedent applied to my own
    record - no self-exemption. The weld's atomisation finds them graded, not flat. Matched by
    BASENAME wherever they live (two early handoffs sat stray in ``src/laplace`` and flooded that
    branch instead) - only deliberate archives (``archive/``) stay where history put them."""
    base = node_id.rsplit("/", 1)[-1]
    if base.startswith("SESSION_HANDOFF_") and "::" not in node_id \
            and not node_id.startswith("archive/"):
        return HANDOFF_SERIES
    return None


# ---------------------------------------------------------------------------
# keep / ascend - the coarse handle, recurrence-promoted from the children
# ---------------------------------------------------------------------------

def promote_keywords(child_kw_lists: list[list[str]], min_count: int = PROMOTE_MIN,
                     cap: int = PROMOTE_CAP) -> list[str]:
    """The promotion rule: a keyword that recurs across >= min_count children ascends to the parent
    handle (held once above, not duplicated below). Falls back to the most frequent when nothing
    clears the bar (a thin node still gets a non-empty handle)."""
    cnt: Counter[str] = Counter()
    for kws in child_kw_lists:
        cnt.update(set(kws))
    # Deterministic tie-break (W6.2 REPAIR 2026-07-14): most_common() orders equal-count
    # keywords by Counter insertion order, which rides set() iteration and is
    # PYTHONHASHSEED-dependent - so the promoted list flipped across process loads. That was
    # the warm-arrival churn: node_text embeds these handles, and ~7 top-level nodes'
    # text-hashes changed every cold start, making the boot pre-warm re-embed them. Sort by
    # count DESC then keyword ASC: salience is preserved, the order is now process-stable.
    ranked = sorted(cnt.items(), key=lambda kc: (-kc[1], kc[0]))
    promoted = [kw for kw, c in ranked if c >= min_count]
    if not promoted:
        promoted = [kw for kw, _c in ranked[:cap]]
    return promoted[:cap]


def summarize(node_id: str, kid_nodes: list[dict[str, Any]], root_id: str = "") -> str:
    """The coarse essence - a glance at what the cluster IS (kinds + size). No content is read; this
    synthesises from the children's handles only, so a sealed subtree never leaks through it."""
    base = node_id.rsplit("/", 1)[-1] if node_id and node_id != root_id else "(root)"
    kinds = Counter(kn["kind"] for kn in kid_nodes)
    kind_str = ", ".join(f"{k}x{v}" for k, v in kinds.most_common(4))
    return f"{base}/ - {len(kid_nodes)} item(s): {kind_str}"


# ---------------------------------------------------------------------------
# build the graded tree - bottom-up, grade-local (no O(N^2))
# ---------------------------------------------------------------------------

def build_tree(leaves: dict[str, dict[str, Any]],
               parent_of: Callable[[str], str | None] = dir_parent,
               root_id: str = "", width_bound: int = DEFAULT_WIDTH) -> dict[str, dict[str, Any]]:
    """Build the graded conceptric from grade-0 leaves + a structural parent function.

    ``leaves``: id -> {kind, essence, keywords, sealed}. Returns id -> graded node:
    {id, grade, kind, essence, keywords, members(down), parent(up), sealed, leaf}. Grade is HEIGHT
    (0 = leaf, 1 + max child grade for an internal node), so the grade is "how coarse", per node."""
    nodes: dict[str, dict[str, Any]] = {}
    children: dict[str, set[str]] = {}

    for lid, lf in leaves.items():
        kws = list(lf.get("keywords", []))
        nodes[lid] = {"id": lid, "grade": 0, "kind": lf.get("kind", "file"),
                      "essence": lf.get("essence", ""), "keywords": kws, "coverage": kws,
                      "members": [], "parent": None, "sealed": bool(lf.get("sealed", False)),
                      "leaf": True}
        # Preserve the projection slot (canon://skills/conceptric_coherence, the
        # build-completion contract): a leaf's emit-time labels (latex_label,
        # section_ref, data_source) travel with the node up through build_tree, so
        # the projector always finds them where the node lives.
        if lf.get("projection"):
            nodes[lid]["projection"] = dict(lf["projection"])
        # The epistemic status slot travels with the node the same way (written by
        # the set-status rewire op via apply_overlay), so a completeness gauge and
        # the projector find the node's status where the node lives.
        if lf.get("status"):
            nodes[lid]["status"] = lf["status"]
        # Source identity belongs to the authored object, not to its current
        # containment edge.  Preserve it when a leaf becomes an internal node
        # and when the same leaves are rebuilt after a move-node overlay.
        for source_key in ("source", "sources", "ref"):
            if lf.get(source_key) is not None:
                value = lf[source_key]
                nodes[lid][source_key] = dict(value) if isinstance(value, dict) else \
                    list(value) if isinstance(value, list) else value

    # containment: walk each node up to the root, creating ancestor (dir) nodes + child links
    for nid in list(nodes):
        cur = nid
        while True:
            p = parent_of(cur)
            if p is None:
                break
            children.setdefault(p, set()).add(cur)
            if p not in nodes:
                nodes[p] = {"id": p, "grade": 0, "kind": "dir", "essence": "", "keywords": [],
                            "coverage": [], "members": [], "parent": None, "sealed": False,
                            "leaf": False}
            cur = p

    # post-order resolve: grade + ascended handle for every internal node
    resolved: set[str] = set()

    def resolve(nid: str) -> dict[str, Any]:
        node = nodes[nid]
        if nid in resolved:
            return node
        kids = sorted(children.get(nid, ()))
        if not kids:                                # a GENUINE leaf (no children below) - re-read its source
            return node
        resolved.add(nid)
        # A node with children is INTERNAL even if it arrived as a real file-leaf: a semantic parent
        # function (e.g. concept_lens) makes the theme/pillar FILES coarse nodes that also carry their own
        # adjudicated essence. Such an AUTHORED coarse node keeps its essence (the faithful handle the
        # keeper wrote last session beats a re-summarised one); a plain dir node is summarised as before.
        was_leaf = bool(node.get("leaf"))
        authored = was_leaf and bool(node.get("essence"))
        # The semantic fold happens before this containment pass because its parent map is one of
        # this pass's inputs.  A real file can subsequently become an internal node (lens atoms,
        # structural rungs, record slices): its served handle then legitimately gains promoted
        # child terms.  Preserve the exact pre-ascent handle so recursive_read can reproduce the
        # vector/hash the fold banked instead of comparing the enriched serving handle with the
        # original route handle and declaring a freshly deposited tree stale.
        if was_leaf:
            node["route_handle"] = {
                "essence": node.get("essence", ""),
                "keywords": list(node.get("keywords") or []),
                "sealed": bool(node.get("sealed", False)),
            }
        node["leaf"] = False
        kid_nodes = [resolve(k) for k in kids]
        node["members"] = kids
        node["grade"] = 1 + max((kn["grade"] for kn in kid_nodes), default=0)
        promoted = promote_keywords([kn["keywords"] for kn in kid_nodes])
        node["ascended"] = promoted                 # what was ASCENDED from members (the gate checks THIS),
        node["authored"] = authored                 # distinct from an authored node's own file-read terms
        if authored:
            own = node.get("keywords") or []        # own terms first (they route to the authored node),
            node["keywords"] = list(dict.fromkeys(own + promoted))[:2 * PROMOTE_CAP]   # + the recurrences below
        else:
            node["keywords"] = promoted
            node["essence"] = summarize(nid, kid_nodes, root_id)
        cov: set[str] = set(node.get("keywords") or [])   # an authored node is findable by its OWN terms too,
        for kn in kid_nodes:                        # plus coverage = what's FINDABLE below (routes the descent)
            cov.update(kn.get("coverage") or kn["keywords"])
        node["coverage"] = sorted(cov)
        node["sealed"] = bool(kid_nodes) and all(kn["sealed"] for kn in kid_nodes)
        for k in kids:
            nodes[k]["parent"] = nid
        return node

    for nid in [n for n in nodes if parent_of(n) is None]:
        resolve(nid)
    for nid in list(nodes):            # defensive: resolve anything with children not reached from a root
        if nid not in resolved and children.get(nid):
            resolve(nid)
    return nodes


# ---------------------------------------------------------------------------
# the LOCAL faithfulness gate - sample each node's members (never all-pairs)
# ---------------------------------------------------------------------------

def local_faithfulness(nodes: dict[str, dict[str, Any]], k: int = 3) -> dict[str, Any]:
    """For each coarse node: its sampled members resolve, and every promoted keyword genuinely came
    from a member (the ascent is faithful - nothing invented on the way up). O(internal * k)."""
    internal = [n for n in nodes.values() if not n["leaf"]]
    checked = ok = 0
    bad: list[str] = []
    for node in internal:
        mems = node["members"]
        if not mems:
            continue
        member_kw: set[str] = set()
        for m in mems:
            member_kw |= set(nodes[m]["keywords"])
        # check only what was ASCENDED from members (the ascent-faithfulness contract); an AUTHORED coarse
        # node's own keywords are READ from its real file, not ascended, so they are faithful by construction
        # and exempt (checking them would falsely flag a real handle). Fallback to keywords for older trees.
        for kw in node.get("ascended", node["keywords"]):
            checked += 1
            if kw in member_kw:
                ok += 1
            else:
                bad.append(f"{node['id']}: promoted '{kw}' not in any member")
        for p in sorted({0, len(mems) // 2, len(mems) - 1})[:k]:
            checked += 1
            if mems[p] in nodes:
                ok += 1
            else:
                bad.append(f"{node['id']}: member {mems[p]} unresolved")
    return {"pass": not bad, "internal_nodes": len(internal), "checked": checked,
            "ok": ok, "bad": bad[:10]}


def grade_stats(nodes: dict[str, dict[str, Any]], width_bound: int = DEFAULT_WIDTH) -> dict[str, Any]:
    by_grade = Counter(n["grade"] for n in nodes.values())
    internal = [n for n in nodes.values() if not n["leaf"]]
    widths = [len(n["members"]) for n in internal]
    flags = [{"node": n["id"], "grade": n["grade"], "children": len(n["members"]),
              "why": "too wide - sub-grade (phi, his threshold)"}
             for n in internal if len(n["members"]) > width_bound]
    return {"n_nodes": len(nodes), "n_leaves": sum(1 for n in nodes.values() if n["leaf"]),
            "n_internal": len(internal), "max_grade": max(by_grade) if by_grade else 0,
            "by_grade": dict(sorted(by_grade.items())), "max_width": max(widths, default=0),
            "reshape_flags": sorted(flags, key=lambda f: -f["children"])[:20]}


# ---------------------------------------------------------------------------
# the ring (Stage 2) - read path, simple recall (mechanical; the prompt-dependent keeper is Stage 3)
# ---------------------------------------------------------------------------

def recall(nodes: dict[str, dict[str, Any]], message: str, start: str = "",
           limit: int = 10) -> dict[str, Any]:
    """The ring at its simplest: a message pipes DOWN, each grade pulls its relevant cluster (members
    whose COVERAGE the message touches), and the return feeds UP a ranked list of related leaves with
    the descent PATH. Relevance-pruned, so it visits the relevant subtree, not all nodes (grade-local,
    not a flat scan). This is ``select`` + ``pull_up`` with the trivial keeper operation; Stage 3
    replaces them with sealed sub-Eigens that do prompt-dependent work and enrich on the way up.

    Mechanical here (keyword routing): ``select`` descends a member iff its coverage meets the query;
    a leaf scores on its own keywords. No LLM, no source read."""
    from laplace.pipeline.canon import _tokenize

    q = _tokenize(message)
    ql = message.lower().strip()
    visited = {"n": 0}
    hits: list[tuple[int, str, list[str]]] = []

    def ring(nid: str, path: list[str]) -> None:
        visited["n"] += 1
        node = nodes.get(nid)
        if node is None:
            return
        if node["leaf"]:
            s = len(q & set(node["keywords"])) + (3 if ql and ql in nid.lower() else 0)
            if s > 0:
                hits.append((s, nid, path + [nid]))
            return
        for m in node["members"]:                          # DOWN-route into the relevant cluster only
            mn = nodes[m]
            cov = set(mn.get("coverage") or mn["keywords"])
            if (q & cov) or (ql and ql in m.lower()):
                ring(m, path + [nid])

    ring(start, [])
    hits.sort(key=lambda t: (-t[0], t[1]))                  # UP: the enriched return (here: a ranked list)
    return {"query": message, "visited": visited["n"], "total": len(nodes),
            "files": [{"file": f, "score": s, "path": p} for s, f, p in hits[:limit]]}


# ---------------------------------------------------------------------------
# persist - full tree (tracked, per THE UNSEAL) + coarse skeleton (committed)
# ---------------------------------------------------------------------------

def write_tree_local(repo_root: Path | str, nodes: dict[str, dict[str, Any]], *,
                     destination: Path | str | None = None) -> Path:
    """Persist the full graded tree (TRACKED per THE UNSEAL, not gitignored - see GRADED_LOCAL).

    STORE-03 (2026-08-20 self-audit): the write itself is wrapped in
    ``laplace.pipeline.locking.store_lock`` so two concurrent lanes' deposits can never interleave into a
    corrupt file. This is a CLI/producer call (``main()``, ``scripts/reembed.py``), not a hot
    serving path, so :class:`~laplace.pipeline.locking.StoreBusy` on contention propagates unchanged - a
    genuinely contended deposit fails loud (raise-not-block) rather than corrupting or hanging,
    and can simply be re-run."""
    from laplace.pipeline.locking import store_lock  # lazy: avoids a module-load cycle
    out = Path(destination) if destination is not None else Path(repo_root) / GRADED_LOCAL
    with store_lock("self-graded"):
        out.write_text(json.dumps(nodes, ensure_ascii=False), encoding="utf-8")
    return out


def load_tree_local(repo_root: Path | str) -> dict[str, dict[str, Any]]:
    p = Path(repo_root) / GRADED_LOCAL
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def write_skeleton(repo_root: Path | str, nodes: dict[str, dict[str, Any]],
                   stats: dict[str, Any], min_grade: int = 2, *,
                   destination: Path | str | None = None) -> Path:
    """The committed coarse view: the upper grades only (the navigable map). Leaves and grade-1 dirs
    stay in the local tree; this is the 'no level a hairball' top, diffable in git."""
    out = Path(destination) if destination is not None else Path(repo_root) / SKELETON
    lines = [
        "# Self graded index - the coarse navigable map",
        "",
        "<!-- generated by laplace.engine.keeper (Stage 1). The directory as a graded conceptric: leaves",
        "(files) at grade 0, directories ascending by HEIGHT, each coarse handle recurrence-promoted",
        "from its children. This committed view is the UPPER grades only (the navigable top); the full",
        "tree + leaves are in the tracked .self_graded.json (committed per THE UNSEAL, not gitignored -",
        "it travels so reconstruction stays deterministic). The ring (KEEPER_ARCHITECTURE.md)",
        "reconstructs through THAT JSON, not through this file: this is a HUMAN-navigable coarse",
        "index, diffable in git, load-bearing for nobody's reconstruction path (corrected",
        "2026-08-17 by the thin-systems audit - it had been advertising a role it does not hold). -->",
        "",
        f"_grades 0..{stats['max_grade']} · {stats['n_nodes']:,} nodes "
        f"({stats['n_leaves']:,} leaves, {stats['n_internal']:,} coarse) · "
        f"max width {stats['max_width']}_",
        "",
        "## Grade distribution",
        "",
    ]
    for g, c in stats["by_grade"].items():
        lines.append(f"- grade {g}: {c:,} node(s)")
    lines += ["", f"## Coarse nodes (grade >= {min_grade})", ""]
    coarse = sorted((n for n in nodes.values() if not n["leaf"] and n["grade"] >= min_grade),
                    key=lambda n: (-n["grade"], n["id"]))
    for n in coarse:
        seal = " · sealed" if n["sealed"] else ""
        kw = " ".join(n["keywords"][:6])
        lines.append(f"- **{n['id'] or '(root)'}** (g{n['grade']}, {len(n['members'])} members{seal}) "
                     f"- {n['essence']} · `{kw}`")
    lines += ["", "## Reshape flags (too wide -> sub-grade; phi, his threshold)", ""]
    if stats["reshape_flags"]:
        for f in stats["reshape_flags"]:
            lines.append(f"- **{f['node'] or '(root)'}** (g{f['grade']}): {f['children']} children")
    else:
        lines.append("- none - every coarse node is within the width bound.")
    lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
# the self application + entry
# ---------------------------------------------------------------------------

# The semantic fold is a function of authored/source-bearing inputs, not of its own current
# materializations.  These files remain in ``shards_out`` and therefore in the exact by-name
# self-shard index; excluding them here only prevents the recursive operator from consuming the
# artifacts it is about to replace.  Basename scope catches historical bakeoff shadow outputs as
# well as the live root outputs.  The future typed SemanticFoldTransition will surface their exact
# pre/post handles without putting mutable post bytes back into the pre frontier.
_SEMANTIC_OPERATOR_OUTPUT_BASENAMES = frozenset({
    ".meaning_tree.json",
    ".metric_M.npz",
    ".self_embeddings.json",
    ".self_graded.json",
})
_SEMANTIC_OPERATOR_OUTPUT_PATHS = frozenset({
    ".reembed_timing.jsonl",
    ".residue.jsonl",
    ".upfold_triggers.jsonl",
    ".wire_proposals.jsonl",
    ".wire_verdicts.jsonl",
    "SELF_GRADED_INDEX.md",
    "SELF_SHARD_INDEX.md",
    "contract/journal.jsonl",
})


def _is_semantic_operator_output(node_id: str) -> bool:
    normalized = node_id.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return (
        normalized in _SEMANTIC_OPERATOR_OUTPUT_PATHS
        or normalized.rsplit("/", 1)[-1] in _SEMANTIC_OPERATOR_OUTPUT_BASENAMES
    )

def semantic_input_frame(
    repo_root: Path | str,
    *,
    timings: dict[str, float] | None = None,
    shards_out: dict[str, dict[str, Any]] | None = None,
    persist_record_floor: bool = False,
    source_kernel_inputs=None,
) -> tuple[
    dict[str, dict[str, Any]],
    Callable[[str], str | None],
    dict[str, dict[str, Any]],
    str,
    list[str],
]:
    """Reconstruct the exact read-only input frontier consumed by ``build_self``.

    Deposit and freshness verification must not maintain two almost-equal definitions of the
    semantic corpus. This is their single source: file shards plus every virtual lens leaf, the
    lens parent operator, the unclaimed residue, and the exact lens-membership fingerprint. It
    performs no fold and writes no artifact by default. The deposit explicitly requests
    persistence of the record-floor locators alongside the tree it is producing.
    """

    from laplace.engine import collaborator_lens, concept_lens, record_shard, self_shard, structural_lens
    from laplace.representation import semantic_vertical

    repo_root = Path(repo_root)
    started = time.perf_counter()
    raw_leaves = self_shard.shard_repo(repo_root)
    if shards_out is not None:
        shards_out.clear()
        shards_out.update(raw_leaves)
    leaves = {
        node_id: leaf
        for node_id, leaf in raw_leaves.items()
        if not _is_semantic_operator_output(node_id)
    }
    if timings is not None:
        timings["shard_repo"] = time.perf_counter() - started
        started = time.perf_counter()

    # Explicit selected receipts only. The ordinary existing coverage manifest
    # retains the selection; absence creates no new Source leaves.
    from laplace.engine import source_kernel_input as source_kernel
    selected = source_kernel.input_frame(repo_root, source_kernel_inputs)
    for node_id, leaf in source_kernel.keeper_leaves(selected).items():
        if node_id in leaves and leaves[node_id] != leaf:raise ValueError('SOURCE_KERNEL_LOGICAL_ID_COLLISION')
        leaves[node_id] = leaf

    lens_map = concept_lens.lens_membership(leaves)
    leaves.update(concept_lens.lens_atom_leaves(repo_root))
    leaves.update(collaborator_lens.collaborator_leaves(repo_root))
    leaves.update(record_shard.floor_leaves(repo_root, persist=persist_record_floor))
    leaves.update(record_shard.transcript_leaves(repo_root))
    leaves.update(structural_lens.structural_leaves(repo_root))
    if (repo_root / semantic_vertical.COVERAGE_PATH).is_file():
        # One universal operational projection.  Failure is loud: a declared vertical fold may
        # never silently omit Atlas, Fabric or the current work frontier and call itself complete.
        leaves.update(semantic_vertical.operational_leaves(repo_root))
    if timings is not None:
        timings["lens_leaves"] = time.perf_counter() - started

    def lens_parent(nid: str) -> str | None:
        declared = leaves.get(nid, {}).get("semantic_parent")
        if declared is not None:
            return str(declared) if declared else None
        structural = structural_lens.structural_parent(nid)
        if structural is not None:
            return structural
        atom = concept_lens.atom_parent(nid)
        if atom is not None:
            return atom
        series = series_parent(nid)
        if series is not None:
            return series
        transcript = record_shard.transcript_parent(nid)
        if transcript is not None:
            return transcript
        return lens_map.get(nid)

    residue = {nid: leaf for nid, leaf in leaves.items() if lens_parent(nid) is None}
    lens_pairs = sorted(
        f"{nid}\x00{parent}"
        for nid in leaves
        if (parent := lens_parent(nid)) is not None
    )
    lens_hash = hashlib.sha1("\n".join(lens_pairs).encode("utf-8")).hexdigest()
    return leaves, lens_parent, residue, lens_hash, lens_pairs

def build_self(
    repo_root: Path | str,
    timings: dict[str, float] | None = None,
    shards_out: dict[str, dict[str, Any]] | None = None,
    force_full: bool = False,
    source_kernel_inputs=None,
) -> dict[str, dict[str, Any]]:
    """Build the graded SELF conceptric from the directory's grade-0 leaves (the self-shard).

    The parent function is ``dir_parent`` everywhere EXCEPT the physics lens (``concept_corpus/``), where
    a SEMANTIC parent (``concept_lens.lens_membership``, derived from the shard edges) grades it
    pillar -> theme -> paper instead of by the by-kind directory layout - so the keeper ring descends the
    lens through its MEANING (the integrade linkage). Additive elsewhere: every non-lens path is unchanged.

    ``timings`` (Weld B0, phase-timer instrumentation): OPTIONAL, default None, additive - when a dict is
    passed, this records the wall-clock duration (seconds) of each visible sub-phase into it under
    ``shard_repo`` / ``lens_leaves`` / ``meaning_upfold`` / ``build_tree``, so a caller (reembed.py) can
    bank a phase breakdown without build_self otherwise changing behavior. When None (the default, every
    existing caller), no timer calls happen and nothing changes.

    ``shards_out``: OPTIONAL, default None, additive - when a dict is passed, the RAW
    ``self_shard.shard_repo`` result is copied into it before the lens leaves are merged on top.
    The deposit (``scripts/reembed.py``) then re-indexes from THIS dict instead of letting
    ``self_shard.write_index``'s ``shards=None`` default walk and re-shard every tracked file a
    second time - the same 8-22 s derivation was being paid twice per deposit for one answer
    (WO-20260820-kmeans-is-the-new-bottleneck's sibling cure, 2026-08-20). A copy, not the live
    dict: ``leaves`` is mutated below with the lens/atom/record/structural leaves and the synthetic
    concept clusters, none of which are files and none of which belong in the flat file index."""
    from laplace.engine import record_shard

    repo_root = Path(repo_root)
    leaves, lens_parent, residue, lens_hash, lens_pairs = semantic_input_frame(
        repo_root,
        timings=timings,
        shards_out=shards_out,
        persist_record_floor=True,
        source_kernel_inputs=source_kernel_inputs,
    )
    _t0 = time.perf_counter() if timings is not None else 0.0

    # THE MEANING-BASED MIDDLE (his directive): the residue - everything no lens claims, which used
    # to fall to dir_parent (the FOLDER layout, the "sharding didn't work as intended") - is clustered
    # by MEANING instead (silhouette-spectral, the basis projection N42 validated; the soul folded in
    # vector-only). meaning_map routes residue leaves + the synthetic concept clusters; build_tree wires
    # them as authored coarse handles. Degrades to dir_parent on any unavailability - the build never breaks.
    meaning_map: dict[str, str] = {}
    try:
        from laplace.engine import meaning_upfold
        prev_tree = None if force_full else meaning_upfold.load_tree(repo_root)
        meaning_map, cluster_nodes = meaning_upfold.cluster_residue_incremental(
            repo_root, residue, prev_tree, root_id="", lens_hash=lens_hash, lens_pairs=lens_pairs)
        leaves.update(cluster_nodes)                          # the concept-cluster middles (authored essences)
    except Exception:  # noqa: BLE001 - the meaning middle is additive; a failure falls back to dir_parent
        meaning_map = {}
    if timings is not None:
        timings["meaning_upfold"] = time.perf_counter() - _t0
        _t0 = time.perf_counter()

    def parent_of(nid: str) -> str | None:
        if 'semantic_parent' in leaves.get(nid,{}):
            return str(leaves[nid]['semantic_parent'])
        if nid in meaning_map:                                # a clustered residue leaf or a concept middle
            return meaning_map[nid]
        lp = lens_parent(nid)
        return lp if lp is not None else dir_parent(nid)      # unclustered residue keeps the folder fallback

    nodes = build_tree(leaves, parent_of)
    if timings is not None:
        timings["build_tree"] = time.perf_counter() - _t0
    if HANDOFF_SERIES in nodes:                               # an authored handle for the series (it has no file
        nodes[HANDOFF_SERIES]["kind"] = "series"              # to read a first-heading from; the summarize() line
        nodes[HANDOFF_SERIES]["essence"] = (                  # would say only 'N items: file')
            "the dated session handoffs - the engine's session-by-session memory as one series; "
            "descend for a specific date or session")
    if record_shard.TRANSCRIPT_SERIES in nodes:
        nodes[record_shard.TRANSCRIPT_SERIES]["kind"] = "series"
        nodes[record_shard.TRANSCRIPT_SERIES]["essence"] = (
            "our sessions, both sides - the dialogue record (his turns and mine), sealed to the "
            "local display; descend for a sitting")
    return nodes


def default_repo_root() -> Path:
    return source_tree()


def main(argv: list[str]) -> int:
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    root = default_repo_root()
    nodes = build_self(root)
    stats = grade_stats(nodes)
    write_tree_local(root, nodes)
    write_skeleton(root, nodes, stats)
    gate = local_faithfulness(nodes)
    print(json.dumps({"stats": stats, "gate": gate}, ensure_ascii=False, indent=2))
    return 0 if gate["pass"] else 1


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
