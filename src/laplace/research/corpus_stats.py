"""corpus_stats.py - the REGRADE watch: size / degree / grade-proxy statistics for a
corpus conceptric, served as ``GET /corpus/grade_stats``.

The question this instruments: what is the right amount of content for a node? There is
a line between too large (a split candidate) and functionally content-free. If grading is
being done right the node counts should fall off roughly geometrically through the grades
- a power law. The law is WATCHED, never imposed (his ruling: instrument it, fix no
exponent): this module measures counts, sizes and ratio sequences, and fits nothing.

This is a VIEW. It rides ``corpus_ingest.corpus_network`` (the existing embedding-free
up-pass + overlay mechanism) and NEVER embeds (the PSU rule: views never embed).

Grade proxy (structural, mechanical): grade 0 = the spine beats; grade 1 = nodes within
one hop of a beat; grade 2 = within two hops; grade 3 = everything further (or
unreachable). Hops walk ``edge_index`` undirected, with the ``confirmed::`` / ``sem::``
audit markers stripped so a human-confirmed edge counts the same as an explicit one.

Dispatch contract (the orchestrator wires this into scanner.py - two lines):

    from laplace.research import corpus_stats as _corpus_stats
    # inside do_GET's /corpus/ block, where ``name`` is already resolved:
    elif u.path == "/corpus/grade_stats":
        st, ct, body = _corpus_stats.handle(u.path, q, name); self._send(st, body, ct)
"""

from __future__ import annotations

import json
import statistics
from collections import deque
from typing import Any

__all__ = ["handle", "grade_stats"]

_MARKERS = ("confirmed::", "sem::")
_CONTENT_FREE_MIN = 120                                # chars below which a node is suspect
_CONTENT_FREE_EXEMPT = {"support", "citation", "goal", "references"}  # kinds allowed to be short
_TOP_N = 10                                            # split-candidate list length
_HIST_FLOOR = 8                                        # first log bin: [0, 8); then doubling


def _strip(ref: str) -> str:
    """Strip the audit-marker prefixes so a referent compares as a plain node id."""
    for m in _MARKERS:
        if ref.startswith(m):
            return ref[len(m):]
    return ref


def _retired(node: dict[str, Any]) -> bool:
    proj = node.get("projection")
    return bool(proj.get("retired")) if isinstance(proj, dict) else False


def _log_bins(max_chars: int) -> list[tuple[int, int]]:
    """Doubling (log-spaced) bin edges covering [0, max_chars]: [0,8), [8,16), [16,32)..."""
    bins: list[tuple[int, int]] = [(0, _HIST_FLOOR)]
    hi = _HIST_FLOOR
    while hi <= max_chars:
        bins.append((hi, hi * 2))
        hi *= 2
    return bins


def grade_stats(net: dict[str, Any], corpus_name: str) -> dict[str, Any]:
    """Compute the regrade statistics from an already-built corpus network. Pure -
    no I/O, no embedding; everything derives from nodes / edge_index / spine."""
    all_nodes: dict[str, dict] = net.get("nodes", {})
    edge_index: dict[str, list[str]] = net.get("edge_index", {}) or {}
    # the atoms: leaf nodes (internal dir/section containers are structure, not content)
    leaves = {nid: n for nid, n in all_nodes.items() if n.get("leaf")}

    # -- adjacency + degree (stripped, deduplicated, self-loops dropped) ----------------
    out_refs: dict[str, set[str]] = {}
    for src, refs in edge_index.items():
        if src not in all_nodes:
            continue
        tgts = {_strip(r) for r in (refs or [])}
        out_refs[src] = {t for t in tgts if t != src and t in all_nodes}
    in_refs: dict[str, set[str]] = {}
    for src, tgts in out_refs.items():
        for t in tgts:
            in_refs.setdefault(t, set()).add(src)

    def degree(nid: str) -> int:
        return len(out_refs.get(nid, ())) + len(in_refs.get(nid, ()))

    # -- grade proxy: BFS (undirected) from the spine beats ------------------------------
    beats = [s["id"] for s in net.get("spine", []) if s.get("id") in all_nodes]
    dist: dict[str, int] = {b: 0 for b in beats}
    frontier = deque(beats)
    while frontier:
        cur = frontier.popleft()
        for nxt in out_refs.get(cur, set()) | in_refs.get(cur, set()):
            if nxt not in dist:
                dist[nxt] = dist[cur] + 1
                frontier.append(nxt)

    def proxy(nid: str) -> int:
        d = dist.get(nid)
        return 3 if d is None else min(d, 3)

    # -- per-node rows -------------------------------------------------------------------
    rows = []
    for nid, n in sorted(leaves.items()):
        ess = n.get("essence") or ""
        rows.append({"id": nid, "kind": n.get("kind"), "chars": len(ess),
                     "words": len(ess.split()), "degree": degree(nid),
                     "grade_proxy": proxy(nid), "retired": _retired(n)})
    live = [r for r in rows if not r["retired"]]

    # -- size histogram (log-spaced doubling bins) over LIVE nodes, per kind -------------
    max_chars = max((r["chars"] for r in live), default=0)
    bins = []
    for lo, hi in _log_bins(max_chars):
        in_bin = [r for r in live if lo <= r["chars"] < hi]
        by_kind: dict[str, int] = {}
        for r in in_bin:
            k = r["kind"] or "other"
            by_kind[k] = by_kind.get(k, 0) + 1
        bins.append({"lo": lo, "hi": hi, "count": len(in_bin), "by_kind": by_kind})

    # -- the grade ladder: count + size stats per proxy grade, live nodes ---------------
    labels = {0: "spine beats", 1: "≤1 hop from a beat", 2: "≤2 hops from a beat",
              3: "further / unreached"}
    grades = []
    for g in range(4):
        sizes = [r["chars"] for r in live if r["grade_proxy"] == g]
        grades.append({
            "grade": g, "label": labels[g], "count": len(sizes),
            "mean_chars": round(statistics.mean(sizes), 1) if sizes else None,
            "median_chars": statistics.median(sizes) if sizes else None,
        })
    # the watched power law: the raw ratio sequence between successive grade counts.
    # Reported, never fitted - no exponent is fixed, no target is enforced.
    counts = [g["count"] for g in grades]
    ratios = [round(counts[i + 1] / counts[i], 2) if counts[i] else None
              for i in range(len(counts) - 1)]

    # -- outliers ------------------------------------------------------------------------
    split_candidates = sorted(live, key=lambda r: r["chars"], reverse=True)[:_TOP_N]
    content_free = sorted(
        (r for r in live
         if r["chars"] < _CONTENT_FREE_MIN and (r["kind"] or "") not in _CONTENT_FREE_EXEMPT),
        key=lambda r: r["chars"])

    return {
        "corpus": corpus_name,
        "n_nodes": len(rows), "n_live": len(live), "n_retired": len(rows) - len(live),
        "n_beats": len(beats),
        "nodes": rows,
        "histogram": {"scale": "log2-chars", "bins": bins},
        "grades": grades,
        "count_ratios": ratios,
        "watch": ("counts per grade should fall roughly geometrically if grading is right; "
                  "the ratio sequence is reported, nothing is fitted - the power law is "
                  "watched, never imposed"),
        "outliers": {"split_candidates": split_candidates, "content_free": content_free},
    }


def handle(path: str, query: dict, corpus_name: str) -> tuple[int, str, bytes] | None:
    """Serve ``GET /corpus/grade_stats``. Returns (status, content-type, body) or None
    when the path is not ours (the orchestrator falls through). ``query`` is the
    parse_qs dict; ``corpus_name`` is the already-extracted corpus= param (falls back
    to the query when the orchestrator passes it empty)."""
    if path != "/corpus/grade_stats":
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
    net = ci.corpus_network(troot, repo_root=rr, name=corpus_name)
    body = json.dumps(grade_stats(net, corpus_name), ensure_ascii=False).encode("utf-8")
    return (200, "application/json", body)
