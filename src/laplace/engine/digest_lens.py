"""The digest lens - the mechanical join between a node's banked CLAIM and the readers' substrate.

WHY A LENS AND NOT A STORE WRITE (the residue-tree law, stated in ``distillate_lens``' docstring and
binding here for the same reason). ``keeper.build_self`` clusters by meaning only what NO lens claims.
Write a digest into ``.self_graded.json`` or a shard and the next fold RECLUSTERS it as content: the
tree would grow a layer of its own summaries, re-embed them, and cluster the summary next to the
thing it summarises. So a digest never enters a leaf store. It rides the one channel the readers
already have - the substrate edge-index ``keeper_ring.build_reach`` folds into ``reach``, which
``conceptric.lateral`` / ``coupling_directed`` / ``embed_router.route`` all read - exactly as the
distillate wire does, and this module is that wire's mirror.

WHAT IS MINTED. For every SERVING digest row, one referent per load-bearing object token,
``digest::<normalized token>``, minted on the digested node AND on every leaf its ``src_pointers``
name. Two consequences, and they are the whole point:

  * the digested node's reach now carries the OBJECTS it holds, not only its members' path words, so
    a content query's terms have something in the coupling to meet;
  * the leaf that SUPPLIED an object carries the same referent, so ``coupling(node, leaf)`` counts
    the object they actually share and a descent that lands on either hands its reader the other.

THE FALLBACK HAZARD, and why the guard re-emits EVERYTHING (DP-A2 verify wave, cure A3).
``build_reach`` sets a LEAF's reach to ``edge_targets or coverage`` - so giving its first edge to a
previously edgeless leaf REPLACES its keyword reach rather than extending it. A ``src_pointer`` leaf
is routinely such a node. The first form of this guard borrowed ``distillate_lens``' DISTINCTIVE
filter and re-emitted only the coverage keywords below the doc-frequency ceiling - and that filter
is exactly what made the wire subtractive: measured on the live corpus, 5 nodes LOST reach tokens,
among them ``accounting`` stripped from a node on ``thread-2026-08-23-the-accounting-day``'s owed
path, because a keyword can be common across the tree and still be the only token a reader's query
shares with that leaf. So the rule here is not "re-emit what is distinctive" but THE WIRE MAY ONLY
ADD: for any node whose existing edge coverage is empty, the full existing coverage is re-emitted
alongside the digest referents. Additivity is measured on ``keeper_ring.build_reach`` output, not on
the edge index - the index is where the tokens are written, ``reach`` is where they are read.

SERVING, AND DRIFT (cure A1: ``basis`` is PROVENANCE, never a gate). A row records the
``(node_id, member_sha, basis, grade)`` it was minted under, but validity is carried by
``member_sha`` ALONE. ``basis`` is the tree's ``lens_hash``, which takes a new value nearly every
close (11 distinct values across 12 tracked commits, because every close mints a lens-claimed
handoff file) - gating on it sent the whole digest layer dark on every close, and would nullify a
re-fold done minutes after a mint. Against the CURRENT membership:

  * exact ``member_sha`` - SERVES, ``exact``;
  * Jaccard(banked members, current members) at or above ``digest_mint.DRIFT_FLOOR`` - SERVES,
    marked ``inherited-with-drift``;
  * below the floor - ``stale``. It serves nothing, and it is named. Only the stale TRANSITION banks
    a replacement row, and banking is the orchestrator's hand: this module never writes.

THE LAW IS RE-APPLIED READ-SIDE (cure A2). The mint's defect rules are the store's contract, but a
store is a file: anything can append to it, and a synthetic ``method="composed"`` row with no
pointers was PROVEN to wire ``digest::fabricated`` into the substrate through this lens. So ``serve``
re-checks the contract before wiring - ``method="extracted"`` (or ``"composed"`` WITH non-empty
``src_pointers``), non-empty ``src_pointers``, non-empty ``claim`` - and a non-conforming row is
SKIPPED with its reason counted into the caller's ``skipped`` / ``report`` dict. Never silently
served, and never silently dropped either.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from laplace.engine import digest_mint

# the one referent grammar this lens mints - a load-bearing OBJECT token, minted identically on the
# digested node and on the leaf that supplied it, so `coupling(a, b)` counts the object they share.
DIGEST_PREFIX = "digest::"

_NORM_RE = re.compile(r"[a-z0-9]+")


def token_referent(token: str) -> str:
    """The referent a load-bearing object mints. Lowercase alphanumeric runs, hyphen-joined - the
    same normalization ``distillate_lens._norm`` uses for its join key, so ``H_Q``, ``h q`` and
    ``H-Q`` are one referent and punctuation/case never forks the coupling. A token that normalizes
    to fewer than three characters is dropped: it is not distinctive enough to couple on."""
    key = "-".join(_NORM_RE.findall(token.lower()))
    return f"{DIGEST_PREFIX}{key}" if len(key) >= 3 else ""


#: the statuses that WIRE. Named once, read by ``serve`` and by ``digest_edge_index``, so the two
#: cannot drift apart over which verdict is a serve.
SERVING = ("exact", "inherited-with-drift")

_RANK = {"exact": 2, "inherited-with-drift": 1, "stale": 0}


def conformance(row: dict[str, Any]) -> str | None:
    """The mint's own defect law, re-applied at the READ boundary: the reason this row may not wire,
    or ``None`` when it conforms.

    ``digest_mint._defective`` polices the WRITE boundary, which is the right place for it and not
    enough on its own - ``.digests.jsonl`` is a file, and a hand-appended row carrying
    ``method="composed"`` with no ``src_pointers`` was proven to mint ``digest::fabricated`` straight
    into ``reach``. A digest's whole warrant is that it was READ off the corpus: no pointer, no
    warrant, no wire. The reasons are short stable keys because the caller COUNTS them."""
    method = str(row.get("method") or "")
    pointers = row.get("src_pointers") or []
    if method not in ("extracted", "composed"):
        return "method-not-extracted-or-composed"
    if method == "composed" and not pointers:
        return "composed-without-src-pointers"
    if not pointers:
        return "no-src-pointers"
    if not str(row.get("claim") or "").strip():
        return "empty-claim"
    # G5 AT THE READ BOUNDARY (the essence verify's defect: a hand-crafted 49,014-char claim
    # joined whole - ~13k tokens against bge's 512 window): the row's own banked caps are the
    # walls; a row over its own stamp neither wires nor joins.
    caps = row.get("caps") or {}
    max_sent = int(caps.get("max_sent") or 0) or digest_mint.MAX_SENT
    n_objects = int(caps.get("n_objects") or 0) or digest_mint.N_OBJECTS
    if len(str(row.get("claim") or "")) > max_sent:
        return "claim-over-cap"
    if len(row.get("object_tokens") or []) > n_objects:
        return "objects-over-cap"
    return None


def serve(nodes: dict[str, dict[str, Any]], rows: list[dict[str, Any]],
          drift_floor: float = digest_mint.DRIFT_FLOOR,
          skipped: dict[str, int] | None = None) -> dict[str, dict[str, Any]]:
    """``node_id -> {"row", "status", "jaccard"}`` - which banked row (if any) serves each node now.

    ``status`` is one of ``exact`` / ``inherited-with-drift`` / ``stale``. A node with several banked
    rows keeps the best: an exact ``member_sha`` beats any drift, and among drifts the highest
    Jaccard wins.

    VALIDITY IS ``member_sha``, NOT ``basis`` (cure A1). ``basis`` stays on the row as recorded
    provenance - which lens partition the membership was read under - and is never a gate here: the
    tree's ``lens_hash`` changes nearly every close, so gating on it dark-served the whole layer on
    the day it was minted.

    ``skipped`` (optional, an out-parameter) receives ``reason -> count`` for the rows ``conformance``
    refuses. Pass it wherever the count has to be reportable; the rows are dropped either way."""
    current: dict[str, list[str]] = {}
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        nid = row.get("node_id") or ""
        if nid not in nodes:
            continue
        why = conformance(row)
        if why:
            if skipped is not None:
                skipped[why] = skipped.get(why, 0) + 1
            continue
        if nid not in current:
            current[nid] = digest_mint.leaf_members(nodes, nid)
        cur = current[nid]
        if row.get("member_sha") == digest_mint.member_sha(cur):
            status, j = "exact", 1.0
        else:
            j = digest_mint.jaccard(row.get("members") or [], cur)
            status = "inherited-with-drift" if j >= drift_floor else "stale"
        prev = best.get(nid)
        if prev is None or (_RANK[status], j) > (_RANK[prev["status"]], prev["jaccard"]):
            best[nid] = {"row": row, "status": status, "jaccard": round(j, 4)}
    return best


def digest_edge_index(repo_root: Path | str,
                      base: dict[str, list[str]] | None = None,
                      nodes: dict[str, dict[str, Any]] | None = None,
                      rows: list[dict[str, Any]] | None = None,
                      report: dict[str, Any] | None = None) -> dict[str, list[str]]:
    """``node id -> its digest referents`` for ``keeper_ring.build_reach``, via
    ``conceptric._self_edge_index``'s merge. Mirrors ``distillate_lens.distillate_edge_index``:
    same signature, same guard position, same "without either argument the guard is skipped and the
    token is still minted" contract.

    Only SERVING rows contribute (``serve`` above), and only CONFORMING ones (``conformance``). A
    stale row mints nothing at all - a digest of a membership the node no longer has would wire the
    reader to what the node USED to hold, which is the imitated-continuity failure this whole layer
    exists against.

    THE GUARD IS ADDITIVE-BY-CONSTRUCTION (cure A3). For any node whose existing edge coverage is
    empty, its FULL existing coverage is re-emitted alongside the new referents - not the
    distinctive-filtered subset, which was measured to strip real tokens off real nodes. The wire
    may only ADD; that is checkable on ``keeper_ring.build_reach`` output and it is checked.

    ``report`` (optional, an out-parameter) receives the named counts a caller may want to print:
    rows read, rows skipped as non-conforming and why, nodes served by status, nodes wired."""
    repo_root = Path(repo_root)
    if nodes is None:
        nodes = digest_mint.load_nodes(repo_root)
    if rows is None:
        rows = digest_mint.load_rows(repo_root)
    if not rows:
        if report is not None:
            report.update({"n_rows": 0, "n_non_conforming": 0, "non_conforming": {},
                           "by_status": {}, "n_wired": 0})
        return {}
    skipped: dict[str, int] = {}
    served = serve(nodes, rows, skipped=skipped)

    guard_on = base is not None
    idx: dict[str, list[str]] = {}

    def mint_on(nid: str, referents: list[str]) -> None:
        if nid not in nodes:
            return
        bucket = idx.setdefault(nid, [])
        for ref in referents:
            if ref not in bucket:
                bucket.append(ref)
        # THE ADDITIVITY GUARD: a node whose first edge this is keeps its WHOLE coverage, because
        # build_reach reads `edge_targets or coverage` and would otherwise REPLACE the keyword reach
        # this node had been coupling on. Full coverage, not the distinctive subset - see the module
        # docstring for the five nodes the filtered form was measured to rob.
        if guard_on and not (base or {}).get(nid):
            node = nodes[nid]
            for kw in (node.get("coverage") or node.get("keywords") or []):
                if kw not in bucket:
                    bucket.append(kw)

    for nid, verdict in served.items():
        row = verdict["row"]
        if row is None or verdict["status"] not in SERVING:
            continue
        refs = [r for r in (token_referent(o.get("token", ""))
                            for o in (row.get("object_tokens") or [])) if r]
        if not refs:
            continue
        mint_on(nid, refs)
        for pointer in row.get("src_pointers") or []:
            if isinstance(pointer, (list, tuple)) and pointer:
                mint_on(str(pointer[0]), refs)

    if report is not None:
        by_status: dict[str, int] = {}
        for v in served.values():
            by_status[v["status"]] = by_status.get(v["status"], 0) + 1
        # RUL-20260823-basis-gate-to-provenance clause 1: cross-basis serving is always NAMED,
        # never silent - basis stopped gating, so the reader must see how many servings cross it.
        cur_basis = digest_mint.basis_of(repo_root)
        cross = sorted(nid for nid, v in served.items()
                       if v["row"] is not None and v["status"] in SERVING
                       and str(v["row"].get("basis") or "") != cur_basis)
        report.update({"n_rows": len(rows),
                       "n_non_conforming": sum(skipped.values()),
                       "non_conforming": dict(sorted(skipped.items())),
                       "by_status": dict(sorted(by_status.items())),
                       "n_cross_basis": len(cross),
                       "cross_basis_nodes": cross[:12],
                       "n_wired": len(idx)})
    return idx
