"""corpus_cocited.py - the co-citation surface, served as ``GET /corpus/co-cited``.

The mechanism behind conceptric2's "shared citations" lateral axis. Two concept nodes
are CO-CITED when they cite the same reference: a real edge over the citation substrate,
not a theatre knob. The relation is derived entirely from the live conceptric's
``edge_index`` - the same referents ``/corpus/content`` reads - so a pair the UI shows is
a pair you can find by hand in the ledger.

The citation substrate: a bibliography entry is a ``ref:<key>`` node of kind ``citation``.
A section / equation / figure / claim node that ``\\cite{key}``s carries that reference as
a referent in its ``edge_index`` row. Overlay-authored corpora store the referent in the
``ref:<key>`` node-id form; a fresh structural ingest may store the bare ``<key>`` - this
module normalises BOTH to the canonical ``ref:<key>`` citation-node id (audit markers
``confirmed::`` / ``sem::`` stripped first), so the surface is true across both build paths.

This is a VIEW. It rides an already-built ``corpus_ingest.corpus_network`` and NEVER embeds
(the PSU rule: views never embed). It is a pure read over ``nodes`` + ``edge_index``.

Two shapes, one endpoint:
  - ``?node=<id>``  -> the focus node's co-cited neighbours (what the lateral axis consumes)
  - (no node)       -> the co-citation PAIRS across the whole corpus (a corpus-level read)

Declared empty: a corpus with no citations (or a focus that cites nothing) returns 200 with an
empty list and ``n_bibkeys`` / ``cites`` telling the truth - never a false "no neighbours"
that hides a missing mechanism. A truly unknown corpus is the only 404 (raised by the caller).

Bounded payload (the golden law: <=16KB, <=40 rows): neighbours and pairs are each capped at
``cap`` (40), sorted deterministically, with ``truncated`` set and the true total reported.

Dispatch contract (wired into scanner.py's /corpus/ block, two lines - the corpus_stats idiom):

    from laplace.research import corpus_cocited as _corpus_cocited
    elif u.path == "/corpus/co-cited":
        st, ct, body = _corpus_cocited.handle(u.path, q, name); self._send(st, body, ct)
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

__all__ = ["handle", "co_cited"]

_MARKERS = ("confirmed::", "sem::")
# kinds that are the citation substrate itself, not co-citing works: excluded as citers so
# the relation is concept<->concept ("who else cites what I cite"), never "the citation I made".
_NON_CITER = {"citation", "references", "paper"}
_CAP = 40                # golden row bound
_ESS = 120              # essence truncation
_SHARED_CAP = 24        # bound the shared-refs list per row (usually 1-2)


def _strip(ref: str) -> str:
    for m in _MARKERS:
        if ref.startswith(m):
            return ref[len(m):]
    return ref


def _cited_refs(refs: list[str] | None, nodes: dict[str, dict]) -> set[str]:
    """The set of canonical ``ref:<key>`` citation-node ids a referent row cites. Accepts both
    the node-id form (``ref:key``) and the bare-key form (``key``); audit markers stripped."""
    out: set[str] = set()
    for r in refs or []:
        base = _strip(r)
        for cand in (base, "ref:" + base):
            n = nodes.get(cand)
            if n is not None and n.get("kind") == "citation":
                out.add(cand)
    return out


def _ess(nodes: dict[str, dict], nid: str) -> str:
    return (nodes.get(nid, {}).get("essence") or "")[:_ESS]


def co_cited(net: dict[str, Any], corpus_name: str,
             node: str | None = None, cap: int = _CAP) -> dict[str, Any]:
    """Compute the co-citation surface from an already-built corpus network. Pure - no I/O, no
    embedding; everything derives from ``nodes`` + ``edge_index``."""
    nodes: dict[str, dict] = net.get("nodes", {}) or {}
    edge_index: dict[str, list[str]] = net.get("edge_index", {}) or {}

    bibkeys = {nid for nid, n in nodes.items()
               if nid.startswith("ref:") and n.get("kind") == "citation"}

    # citer -> {canonical ref: ids it cites}; only nodes that actually cite a live reference
    cites_of: dict[str, set[str]] = {}
    for nid, refs in edge_index.items():
        n = nodes.get(nid)
        if n is None or n.get("kind") in _NON_CITER:
            continue
        ks = _cited_refs(refs, nodes)
        if ks:
            cites_of[nid] = ks

    base = {
        "corpus": corpus_name,
        "n_bibkeys": len(bibkeys),
        "n_citing_nodes": len(cites_of),
    }

    # ---- focus mode: the lateral axis's neighbours -----------------------------------
    if node is not None:
        mine = cites_of.get(node, set())
        neighbours: list[dict[str, Any]] = []
        if mine:
            for other, ks in cites_of.items():
                if other == node:
                    continue
                shared = mine & ks
                if shared:
                    sh = sorted(shared)
                    neighbours.append({
                        "id": other,
                        "kind": nodes.get(other, {}).get("kind"),
                        "essence": _ess(nodes, other),
                        "shared": sh[:_SHARED_CAP],
                        "n": len(sh),
                    })
        # most-shared first, then id - deterministic and bounded
        neighbours.sort(key=lambda r: (-r["n"], r["id"]))
        total = len(neighbours)
        return {
            **base,
            "node": node,
            "cites": sorted(mine)[:_SHARED_CAP],
            "n_cites": len(mine),
            "neighbours": neighbours[:cap],
            "n_neighbours": total,
            "truncated": total > cap,
        }

    # ---- corpus mode: the co-citation pairs ------------------------------------------
    ref2citers: dict[str, list[str]] = defaultdict(list)
    for nid, ks in cites_of.items():
        for k in ks:
            ref2citers[k].append(nid)

    pair_shared: dict[tuple[str, str], set[str]] = defaultdict(set)
    for ref, citers in ref2citers.items():
        if len(citers) < 2:
            continue
        cs = sorted(citers)
        for i in range(len(cs)):
            for j in range(i + 1, len(cs)):
                pair_shared[(cs[i], cs[j])].add(ref)

    pairs = [{"a": a, "b": b, "shared": sorted(sh)[:_SHARED_CAP], "n": len(sh)}
             for (a, b), sh in pair_shared.items()]
    pairs.sort(key=lambda r: (-r["n"], r["a"], r["b"]))
    total = len(pairs)
    return {
        **base,
        "pairs": pairs[:cap],
        "n_pairs": total,
        "truncated": total > cap,
    }


def handle(path: str, query: dict, corpus_name: str) -> tuple[int, str, bytes] | None:
    """Serve ``GET /corpus/co-cited``. Returns (status, content-type, body) or None when the
    path is not ours (the caller falls through). ``query`` is the parse_qs dict; ``corpus_name``
    is the already-resolved corpus= (falls back to the query when passed empty)."""
    if path != "/corpus/co-cited":
        return None
    from laplace.research import corpus_ingest as ci
    from laplace.core.checkout import repo_root as _repo_root   # the owner, not the server module

    rr = _repo_root()
    if not corpus_name:
        corpus_name = (query.get("corpus") or [""])[0] or ci.default_corpus(rr)
    troot = ci.resolve_corpus(rr, corpus_name)
    if not troot:
        return (404, "application/json",
                json.dumps({"error": f"unknown corpus {corpus_name}"}).encode("utf-8"))
    node = (query.get("node") or [""])[0] or None
    net = ci.corpus_network(troot, repo_root=rr, name=corpus_name)
    body = json.dumps(co_cited(net, corpus_name, node=node), ensure_ascii=False).encode("utf-8")
    return (200, "application/json", body)
