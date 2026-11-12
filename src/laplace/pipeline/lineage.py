"""lineage.py — the conceptric descent walker (G6).

One pure function, :func:`descendants`, walks a project's ``conceptric_v1.json`` edge
list from a starting node and returns everything the node leads to: the recursive
lineage tree, the flat descendant set, the raw edges it traversed (each carrying its
relation and its evidence string), and a health block that states orphans and dangling
targets rather than hiding them.

Design discipline (the fallback law, and cheap):

* **the descent relations are named, not all edges.** A conceptric carries several edge
  families (``contains``, ``draws``, ``shares``, ``precedes``, ``has_project`` ...); only
  the three descent relations below are lineage. A ``draws`` dependency or a ``precedes``
  ordering is not a descendant and is left out of the tree.
* **cycle-safe.** A conceptric is authored, not proven acyclic; a self-loop or a back
  edge must not spin the walk. Every node is expanded at most once; a second arrival is
  recorded as a traversed edge but not re-expanded.
* **orphan honesty.** A node with no outgoing descent edge is not an error — it is a
  leaf, and the health block says the start node was a leaf when it had no lineage. A
  start node absent from the graph returns ``present: False`` with an empty tree, never a
  fabricated one. An edge whose target is not a declared node is a dangling target, named
  in health.
* **pure.** No filesystem work at import; one read of the conceptric per call, no token
  spend, no network.
"""
from __future__ import annotations
from laplace.core.checkout import source_tree

import json
from pathlib import Path

#: the three edge relations that constitute lineage descent. Every other relation
#: (``draws`` dependency, ``shares`` sibling link, ``precedes`` ordering) is not a
#: descendant relation and is never walked here.
DESCENT_RELS = frozenset({"contains", "demonstrates", "supported_by"})


def _repo_root() -> Path:
    # src/laplace/pipeline/lineage.py -> parents[3] == the repo root
    return source_tree()


def _conceptric_path(corpus: str, root: Path) -> Path | None:
    """The ``conceptric_v1.json`` of a corpus, resolved through the manuscript dir the
    review surface resolves (the one authority). ``None`` when the corpus or its
    manuscript does not resolve."""
    try:
        from laplace.manuscript import review_surface as rs
    except Exception:
        return None
    md = rs.manuscript_dir(corpus, "")
    if md is None:
        return None
    p = md / "conceptric_v1.json"
    return p if p.is_file() else None


def load_graph(corpus: str, root: Path | None = None) -> dict | None:
    """Load a corpus's conceptric as ``{nodes_by_id, adj, node_ids}``. ``adj`` maps a
    source id to the list of ``(rel, dst, evidence)`` descent edges leaving it, in file
    order. ``None`` when the conceptric does not resolve."""
    root = (root or _repo_root()).resolve()
    p = _conceptric_path(corpus, root)
    if p is None:
        return None
    try:
        doc = json.loads(p.read_text(encoding="utf-8")) or {}
    except (OSError, json.JSONDecodeError):
        return None
    nodes = doc.get("nodes") or []
    edges = doc.get("edges") or []
    nodes_by_id = {n["id"]: n for n in nodes if isinstance(n, dict) and n.get("id")}
    adj: dict[str, list[tuple[str, str, str]]] = {}
    for e in edges:
        if not isinstance(e, dict):
            continue
        rel = e.get("rel")
        if rel not in DESCENT_RELS:
            continue
        src, dst = e.get("src"), e.get("dst")
        if not src or not dst:
            continue
        adj.setdefault(src, []).append((rel, dst, e.get("evidence") or ""))
    return {"nodes_by_id": nodes_by_id, "adj": adj, "node_ids": set(nodes_by_id)}


def _label_of(nodes_by_id: dict, nid: str) -> str:
    n = nodes_by_id.get(nid) or {}
    return n.get("label") or ""


def _kind_of(nodes_by_id: dict, nid: str) -> str:
    n = nodes_by_id.get(nid) or {}
    return n.get("kind") or ""


def descendants(corpus: str, node: str, depth: int = 0,
                root: Path | None = None) -> dict | None:
    """Every conceptric node reachable from ``node`` by descent relations, to ``depth``.

    ``depth`` counts levels below the start: ``1`` is the direct children, ``2`` two
    generations, and ``0`` (or any value ``<= 0``) is an unbounded walk (cycle-guarded).
    Returns ``None`` only when the corpus's conceptric does not resolve — an unknown
    *node* inside a resolved corpus returns a real payload with ``present: False``.

    The payload::

        {
          corpus, node, present, is_leaf, depth_requested,
          tree:  {id, label, kind, children: [{rel, evidence, ...node...}, ...]},
          nodes: [{id, label, kind, depth}, ...],     # the flat descendant set (no start)
          edges: [{src, dst, rel, evidence}, ...],    # every descent edge traversed
          health: {orphans, dangling, cycles_blocked, n_descendants}
        }
    """
    g = load_graph(corpus, root)
    if g is None:
        return None
    nodes_by_id, adj, node_ids = g["nodes_by_id"], g["adj"], g["node_ids"]
    present = node in node_ids
    unbounded = depth is None or depth <= 0

    flat: list[dict] = []
    traversed: list[dict] = []
    dangling: list[str] = []
    cycles_blocked: list[str] = []
    expanded: set[str] = set()

    def build(nid: str, level: int) -> dict:
        n = nodes_by_id.get(nid) or {}
        node_out = {"id": nid, "label": n.get("label") or "",
                    "kind": n.get("kind") or "", "children": []}
        if not unbounded and level >= depth:
            return node_out
        if nid in expanded:
            # a second arrival at an already-expanded node: record the block, do not recurse.
            cycles_blocked.append(nid)
            return node_out
        expanded.add(nid)
        for rel, dst, evidence in adj.get(nid, []):
            traversed.append({"src": nid, "dst": dst, "rel": rel, "evidence": evidence})
            if dst not in node_ids:
                dangling.append(dst)
            child = build(dst, level + 1)
            child_row = {"rel": rel, "evidence": evidence, **child}
            node_out["children"].append(child_row)
            # the flat set records each descendant once, at its shallowest depth.
            if dst not in {r["id"] for r in flat}:
                flat.append({"id": dst, "label": _label_of(nodes_by_id, dst),
                             "kind": _kind_of(nodes_by_id, dst), "depth": level + 1})
        return node_out

    tree = build(node, 0) if present else {"id": node, "label": "", "kind": "",
                                           "children": []}
    is_leaf = present and not adj.get(node)
    return {
        "corpus": corpus,
        "node": node,
        "present": present,
        "is_leaf": is_leaf,
        "depth_requested": ("unbounded" if unbounded else depth),
        "tree": tree,
        "nodes": flat,
        "edges": traversed,
        "health": {
            "orphans": [] if present and not is_leaf else ([node] if present else []),
            "dangling": sorted(set(dangling)),
            "cycles_blocked": sorted(set(cycles_blocked)),
            "n_descendants": len(flat),
        },
    }
