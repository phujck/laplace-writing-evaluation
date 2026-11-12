"""The corpus semantic re-embed - the offline, PSU-gated embedding pass over a project
conceptric's NODES (the fiftieth's item 2: ~1,400 ledger ops had built nodes no embedding
pass ever saw, so the semantic wire could not run over the corpus at all).

Mirrors the engine's standing pattern exactly:
- fold-time intelligence, view path reads a cache (`corpus_candidates` does this for
  equations; this does it for conceptric nodes),
- content-hashed incremental vectors (`embed_router.ensure_embeddings` shape),
- the mechanical wire gate, DENSITY-ROBUST: a single-paper conceptric is one tight
  semantic cluster (measured on subset-sum-itqde: 27,844 of 64k pairs clear the self
  store's flat WIRE_HI=0.70 - a flat threshold would lay a near-complete graph), so the
  rule is MUTUAL top-k: a wire lays only if each node ranks the other in its top-k
  nearest non-connected neighbours AND cos >= floor; the mutual middle band is banked
  for a jury - never auto-wired,
- `sem::` audit markers, never `confirmed::` (machine estimate stays distinguishable
  from human ground truth forever).

Outputs, per corpus root (both gitignored):
  .corpus_node_vectors.json  - {backend, nodes: {nid: {h, v}}}
  .corpus_sem_edges.json     - {backend, hi, lo, wires: [{a,b,cos}], escalate: [{a,b,cos}]}

`build_corpus_network` reads .corpus_sem_edges.json when present and lays each wire as a
plain edge pair + sem:: audit markers, so the gates (connectivity/substrate) see the
semantic wire. Delete the file to return to the explicit-edges-only picture.

Usage: python scripts/corpus_semantic_embed.py [<corpus-name>] [--hi H] [--lo L] [--refresh]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from laplace.research import corpus_ingest as ci                      # noqa: E402
from laplace.representation.embed_router import WIRE_HI, get_backend  # noqa: E402

VECTOR_FILE = ".corpus_node_vectors.json"
SEM_EDGE_FILE = ".corpus_sem_edges.json"


def corpus_node_text(nid: str, nd: dict) -> str:
    """What a conceptric node IS, bounded: id, kind, essence, keywords."""
    kws = " ".join(nd.get("keywords") or [])
    return f"{nid}\n{nd.get('kind', '')}\n{nd.get('essence', '') or ''}\n{kws}"[:2000]


def ensure_corpus_vectors(troot: Path, nodes: dict, backend) -> dict[str, list[float]]:
    cache_path = troot / VECTOR_FILE
    cached: dict = {}
    if cache_path.is_file():
        try:
            disk = json.loads(cache_path.read_text(encoding="utf-8"))
            if disk.get("backend") == backend.name:
                cached = disk.get("nodes", {})
        except (OSError, json.JSONDecodeError):
            cached = {}
    texts = {nid: corpus_node_text(nid, nd) for nid, nd in nodes.items()}
    hashes = {nid: hashlib.sha1(f"{backend.name}\x00{t}".encode("utf-8", "replace")).hexdigest()
              for nid, t in texts.items()}
    stale = [nid for nid in nodes if cached.get(nid, {}).get("h") != hashes[nid]]
    if stale:
        for nid, vec in zip(stale, backend.embed([texts[n] for n in stale]), strict=True):
            cached[nid] = {"h": hashes[nid], "v": vec}
    cached = {nid: e for nid, e in cached.items() if nid in nodes}
    cache_path.write_text(json.dumps({"backend": backend.name, "nodes": cached}),
                          encoding="utf-8")
    print(f"vectors: {len(stale)} embedded, {len(cached) - len(stale)} cached, "
          f"{len(cached)} total")
    return {nid: e["v"] for nid, e in cached.items()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus", nargs="?", default="subset-sum-itqde")
    ap.add_argument("--k", type=int, default=3,
                    help="mutual top-k neighbourhood size")
    ap.add_argument("--hi", type=float, default=0.80,
                    help="wire floor: mutual pairs at/above this lay the wire")
    ap.add_argument("--lo", type=float, default=WIRE_HI,
                    help="jury floor: mutual pairs in [lo, hi) are banked for a jury")
    ap.add_argument("--refresh", action="store_true",
                    help="drop the vector cache and re-embed everything")
    a = ap.parse_args()

    troot = ci.resolve_corpus(ROOT, a.corpus)
    if troot is None:
        print(f"unknown corpus {a.corpus!r}"); return 1
    if a.refresh and (troot / VECTOR_FILE).is_file():
        (troot / VECTOR_FILE).unlink()

    net = ci.corpus_network(troot, repo_root=ROOT, name=a.corpus)
    nodes = net["nodes"]
    backend = get_backend()
    if backend is None:
        print("no embedding backend available"); return 1

    vectors = ensure_corpus_vectors(troot, nodes, backend)

    import numpy as np
    ids = sorted(vectors)
    X = np.asarray([vectors[i] for i in ids], dtype=np.float64)
    X /= np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-12, None)
    S = X @ X.T

    # pairs already connected by ANY explicit/confirmed edge are not proposals
    connected: set[frozenset] = set()
    from laplace.pipeline.verify import _strip_conf
    for k, vs in net["edge_index"].items():
        for v in vs:
            v = _strip_conf(v)
            if isinstance(v, str) and v.startswith("sem::"):
                v = v[5:]
            if v != k and v in nodes:
                connected.add(frozenset((k, v)))

    # mutual top-k over non-connected pairs: each node's k nearest candidate
    # neighbours; a pair is proposed only when the ranking is MUTUAL
    n = len(ids)
    topk: list[set[int]] = []
    for i in range(n):
        order = np.argsort(-S[i])
        picks: set[int] = set()
        for j in order:
            j = int(j)
            if j == i or frozenset((ids[i], ids[j])) in connected:
                continue
            if float(S[i, j]) < a.lo:
                break
            picks.add(j)
            if len(picks) >= a.k:
                break
        topk.append(picks)

    wires, escalate = [], []
    for i in range(n):
        for j in topk[i]:
            if j < i or i not in topk[j]:
                continue
            c = float(S[i, j])
            rec = {"a": ids[i], "b": ids[j], "cos": round(c, 4)}
            (wires if c >= a.hi else escalate).append(rec)

    wires.sort(key=lambda r: -r["cos"])
    escalate.sort(key=lambda r: -r["cos"])
    out = {"backend": backend.name, "k": a.k, "hi": a.hi, "lo": a.lo,
           "wires": wires, "escalate": escalate}
    (troot / SEM_EDGE_FILE).write_text(json.dumps(out, indent=1), encoding="utf-8")

    import collections
    hist = collections.Counter()
    for r in wires + escalate:
        hist[f"{int(r['cos'] * 20) / 20:.2f}"] += 1
    print(f"nodes {n} | already-connected pairs {len(connected)}")
    print(f"wires (cos>={a.hi}): {len(wires)} | escalate ({a.lo}-{a.hi}): {len(escalate)}")
    print("cos histogram (0.05 bins):",
          dict(sorted(hist.items(), reverse=True)))
    for r in wires[:10]:
        print(f"  wire {r['cos']:.3f}  {r['a']}  <->  {r['b']}")
    print(f"wrote {troot / SEM_EDGE_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
