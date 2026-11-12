"""Resolve a projection plan's appendix placeholder specs into pinned node lists.

The forty-ninth's plan declared A1/A2 as prose placeholders ("the ds:* closure of
<anchors>, pulled mechanically at build time"). This is the mechanical pull: it computes
each appendix's `nodes_in_order` and writes it INTO the plan, so the plan stays the one
binding contract (content selection + pinned linear order) and the brief builder never
interprets prose. The prose spec is preserved as `spec` for provenance.

Rules (measured on subset-sum-itqde: the anchors' depth-2 groups are disjoint, 8/7/7):
- A1: for each anchor theorem, the anchor itself, then its ds:* closure - the ds nodes
  adjacent to the anchor's evidence neighbourhood (one non-ds hop), chained freely
  through ds->ds edges - in prerequisites-first topological order; then the extra
  records the spec names (T5 analysis lineage).
- A2: the union of the sections' placed figures, in plan order, plus the named legacy
  evidence def. Every figure must carry a provenance block (the figures gate).

Usage: python scripts/resolve_appendix_nodes.py [<plan.json>] [<corpus-name>]
"""
import json, sys
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from laplace.research import corpus_ingest as ci
from laplace.web.scanner import _repo_root

A1_ANCHORS = [
    "thm:hardy-littlewood-collapse",
    "res:perturbative-rescue",
    "thm:staircase-cumulant-identities",
    # arc 4 (2026-07-02, the A1 builder's enrichment round): S2 defers the geometric
    # isolation, quadrature, and measurement-primitive derivations to the appendix, but
    # the three-anchor plan never selected their ds chains (15 of 37 uncovered). This
    # anchor's closure captures all of them.
    "res:itqde-spectral-readout",
]
A1_EXTRA = [
    # flag-covering irfs (the builder's typed ENRICHMENT-NEEDED round, 2026-07-02):
    # the w_T = O(||V||^2 n^{k/2}/Gamma_S) promotion and the J^4 excess-ratio identity
    # exist in the conceptric - the plan had under-selected them.
    "irf:target-cluster-second-order-spread",
    "irf:moment-excess-poly-K-any-tau",
    "res:t5-support-in-window-analysis",
    "res:t5v2-staircase-position-analysis",
    "res:t5v3-model-based-inference-analysis",
]
A2_EXTRA = ["def:numerics-v2-experiment-suite"]


def ds_closure(anchor: str, adj: dict[str, set[str]]) -> set[str]:
    """ds nodes one non-ds hop from the anchor, chained freely through ds->ds edges."""
    seen, out, q = {anchor}, set(), deque([(anchor, 0)])
    while q:
        n, d = q.popleft()
        if d >= 2:
            continue
        for nb in adj.get(n, ()):
            if nb in seen:
                continue
            seen.add(nb)
            if nb.startswith("ds:"):
                out.add(nb)
                q.append((nb, d))          # ds chains traverse freely
            elif d + 1 < 2:
                q.append((nb, d + 1))      # one hop through the evidence neighbourhood
    return out


def topo_order(group: set[str], directed: dict[str, list[str]]) -> list[str]:
    """Prerequisites first: edges point step -> prerequisite, so emit post-order."""
    order, seen = [], set()

    def visit(n: str) -> None:
        if n in seen:
            return
        seen.add(n)
        for nb in sorted(directed.get(n, [])):
            if nb in group:
                visit(nb)
        order.append(n)

    for n in sorted(group):
        visit(n)
    return order


def main(plan_path: str, corpus: str) -> int:
    rr = _repo_root()
    plan_file = Path(plan_path)
    plan = json.loads(plan_file.read_text(encoding="utf-8"))
    net = ci.corpus_network(ci.resolve_corpus(rr, corpus), repo_root=rr, name=corpus)

    def retired(nid: str) -> bool:
        nd = net["nodes"].get(nid) or {}
        proj = nd.get("projection") or (nd.get("meta") or {}).get("projection") or {}
        return bool(proj.get("retired"))

    directed = {k: [x for x in v if not x.startswith("confirmed::") and x != k]
                for k, v in net["edge_index"].items()}
    adj: dict[str, set[str]] = {}
    for k, vs in directed.items():
        for v in vs:
            adj.setdefault(k, set()).add(v)
            adj.setdefault(v, set()).add(k)

    a1, seen = [], set()
    for anchor in A1_ANCHORS:
        a1.append(anchor)
        seen.add(anchor)
        group = {n for n in ds_closure(anchor, adj) if not retired(n) and n not in seen}
        ordered = topo_order(group, directed)
        a1 += ordered
        seen.update(ordered)
    a1 += [x for x in A1_EXTRA if x not in seen]

    a2 = [f for sec in plan["sections"] for f in sec.get("figures", [])] + A2_EXTRA

    resolved = {"A1": a1, "A2": a2}
    for app in plan.get("appendices", []):
        if app["id"] not in resolved:
            continue
        if isinstance(app.get("nodes"), str):
            app["spec"] = app.pop("nodes")
        app["nodes_in_order"] = resolved[app["id"]]
        missing = [n for n in app["nodes_in_order"] if n not in net["nodes"]]
        if missing:
            print(f"{app['id']}: MISSING from network: {missing}")
            return 1
        print(f"{app['id']}: pinned {len(app['nodes_in_order'])} nodes")

    plan_file.write_text(json.dumps(plan, indent=1, ensure_ascii=False) + "\n",
                         encoding="utf-8")
    print(f"plan updated: {plan_file}")
    return 0


if __name__ == "__main__":
    plan = sys.argv[1] if len(sys.argv) > 1 else \
        "synthetics papers/subset-sum-itqde/manuscript/projection_plan.json"
    corpus = sys.argv[2] if len(sys.argv) > 2 else "subset-sum-itqde"
    raise SystemExit(main(plan, corpus))
