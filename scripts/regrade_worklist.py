"""The regrade work-order, computed mechanically - the thin-middle diagnosis turned into
a per-edge worklist the regrade panel (and the author) can act on.

The ladder's disease (watched by corpus_stats, first read 11/126/141/59): the spine beats
hub a massive one-hop shelf, so counts never fall off geometrically - there is no earned
middle. The mechanical signal for WHICH beat->node edges hold the shelf too close: a
g1 node X whose best NON-BEAT g1 neighbour Y is semantically closer to X than X's beat is
(cos(X,Y) > cos(X,beat) + margin) is a DEMOTION CANDIDATE - its natural home is a hop
below Y, not on the beat. Nothing is removed here: machine judgment never unpicks human
wiring. The worklist is banked for the panel; each row carries the evidence (both cosines,
the suggested mid-grade parent).

Requires the offline vectors (scripts/corpus_semantic_embed.py) - the pass item 2 built.

Usage: python scripts/regrade_worklist.py [<corpus-name>] [--margin M]
Writes: <corpus-root>/.regrade_worklist.json  (gitignored, regenerable)
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from laplace.research import corpus_ingest as ci                          # noqa: E402
from laplace.research.corpus_stats import _strip                          # noqa: E402

VECTOR_FILE = ".corpus_node_vectors.json"
OUT_FILE = ".regrade_worklist.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus", nargs="?", default="subset-sum-itqde")
    ap.add_argument("--margin", type=float, default=0.05,
                    help="cos(X, mid) must beat cos(X, beat) by this much")
    a = ap.parse_args()

    troot = ci.resolve_corpus(ROOT, a.corpus)
    if troot is None:
        print(f"unknown corpus {a.corpus!r}"); return 1
    vecs_file = troot / VECTOR_FILE
    if not vecs_file.is_file():
        print(f"no vectors at {vecs_file} - run scripts/corpus_semantic_embed.py first")
        return 1

    net = ci.corpus_network(troot, repo_root=ROOT, name=a.corpus)
    nodes = net["nodes"]
    beats = [b["id"] for b in net["spine"]]

    # undirected adjacency, markers stripped
    adj: dict[str, set[str]] = {}
    for k, vs in net["edge_index"].items():
        for v in vs:
            v = _strip(v)
            if v != k and v in nodes:
                adj.setdefault(k, set()).add(v)
                adj.setdefault(v, set()).add(k)

    # grade proxy = hops from the nearest beat (corpus_stats' rule)
    dist = {b: 0 for b in beats}
    q = deque(beats)
    while q:
        n = q.popleft()
        for nb in adj.get(n, ()):
            if nb not in dist:
                dist[nb] = dist[n] + 1
                q.append(nb)

    import numpy as np
    raw = json.loads(vecs_file.read_text(encoding="utf-8"))["nodes"]
    ids = [i for i in raw if i in nodes]
    X = np.asarray([raw[i]["v"] for i in ids], dtype=np.float64)
    X /= np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-12, None)
    idx = {nid: k for k, nid in enumerate(ids)}

    def cos(u: str, v: str) -> float:
        return float(X[idx[u]] @ X[idx[v]]) if u in idx and v in idx else -1.0

    rows = []
    beat_set = set(beats)
    for nid, d in dist.items():
        if d != 1 or nid in beat_set:
            continue
        anchors = [b for b in adj.get(nid, ()) if b in beat_set]
        mids = [m for m in adj.get(nid, ())
                if m not in beat_set and dist.get(m, 99) == 1]
        if not anchors or not mids:
            continue
        best_beat = max(anchors, key=lambda b: cos(nid, b))
        best_mid = max(mids, key=lambda m: cos(nid, m))
        cb, cm = cos(nid, best_beat), cos(nid, best_mid)
        if cm > cb + a.margin:
            rows.append({"node": nid, "kind": nodes[nid].get("kind"),
                         "beat": best_beat, "cos_beat": round(cb, 4),
                         "suggested_parent": best_mid, "cos_parent": round(cm, 4),
                         "gap": round(cm - cb, 4)})

    rows.sort(key=lambda r: -r["gap"])
    g1 = sum(1 for d in dist.values() if d == 1)
    out = {"corpus": a.corpus, "margin": a.margin, "g1_shelf": g1,
           "demotion_candidates": rows,
           "note": ("evidence only - nothing auto-removed; acting on a row means, in the "
                    "panel: remove-edge(node, beat) once node->suggested_parent is a real "
                    "edge (add-edge/confirm-edge if the wire is right)")}
    (troot / OUT_FILE).write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"g1 shelf: {g1} | demotion candidates: {len(rows)} (margin {a.margin})")
    for r in rows[:12]:
        print(f"  {r['gap']:+.3f}  {r['node']}  beat={r['beat']} ({r['cos_beat']:.2f})"
              f" -> {r['suggested_parent']} ({r['cos_parent']:.2f})")
    print(f"wrote {troot / OUT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
