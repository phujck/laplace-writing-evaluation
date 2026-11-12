"""shard_upfold.py - the mechanical upfold over the FLAT directory shard (the N42 production turn).

``self_shard`` shards the directory into 1042 FLAT grade-0 handles - one file, one node, no middle.
N42 (``basis_cluster.py``) PROVED the upfold can go mechanical (membership 0.874 LOO; the margin is
the gate) but only as a VALIDATION HARNESS against the banked Sonnet upfolds, which already carry a
known generator basis. The directory has no such basis - it has never been upfolded. So this is the
piece N42 was not: the PRODUCTION operator that turns the flat shard into a graded conceptric.

The one operator, recurred (``too-big-means-recur``): a set of nodes too big to be one concept is
spectral-clustered (the basis projection N42 validated) into mechanical K children, and each child
recurses, until a cluster is small enough to be a leaf. Top-down, the power-law descent of
``grade-map-is-deterministic-lens-plus-upfold`` - NOT semantic atomise-then-backfill. The tree's
LEAVES are the files (today's g0 handles); the INTERNAL nodes are the middles the self has never had.

The margin gate (N42, ``n42-basis-clusterer-validated``): every atom's placement carries a margin =
cos(atom, own-centroid) - cos(atom, nearest-sibling-centroid). Above tau it is placed mechanically;
the low-margin tail is what a jury would escalate. This run only MEASURES the margin distribution -
tau stays HIS knob (F1). No LLM, no Opus: embeddings (bge-small, local, cached) + linear algebra.

This writes to ``archive/self_shard/upfold_v0.json`` and is NOT wired into the wake / SELF_SHARD_INDEX
/ reconstruct_self - that changes what a wake reconstructs (the fold SHAPE), which is the author's
fork. This materialises the emergent shape so it can be blessed, measured first.

Usage:  .venv/Scripts/python.exe scripts/shard_upfold.py            # build + measure + report
        .venv/Scripts/python.exe scripts/shard_upfold.py --no-cache # ignore the vector cache
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from sklearn.cluster import SpectralClustering
from sklearn.metrics import silhouette_score

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from laplace.engine import self_shard            # noqa: E402
from laplace.representation.embed_router import get_backend, TEXT_CAP  # noqa: E402

OUT = ROOT / "archive" / "self_shard" / "upfold_v0.json"
VEC_CACHE = ROOT / "archive" / "self_shard" / ".upfold_vec_cache.json"

# the one recursion's stopping + branching budget (the-local-constraints: b* ~ B/h)
LEAF_MAX = 10        # a cluster this small or smaller is a leaf bundle (no further split)
BRANCH_MAX = 8       # eigengap-chosen K is clamped to [2, min(BRANCH_MAX, n-1)]
MAX_DEPTH = 6        # defensive recursion bound
EIGEN_WINDOW = 12    # eigenvalues inspected for the gap
TAU = 0.04           # the validated operating point (place >= tau, escalate below)


# ---------------------------------------------------------------------------
# the embeddable text of a flat shard node - the handle, never withheld content
# ---------------------------------------------------------------------------

def shard_text(name: str, sh: dict) -> str:
    """A public node's bge-embeddable line: its path-as-words, essence, keywords."""
    stem = name.replace("/", " ").replace("_", " ").replace("-", " ").rsplit(".", 1)[0]
    kws = " ".join(sh.get("keywords", [])[:16])
    parts = [stem, sh.get("essence", ""), kws]
    return " | ".join(p for p in parts if p)[:TEXT_CAP]


def embeddable_text(name: str, sh: dict) -> str:
    """The text that becomes a node's VECTOR. The soul is self-embeddable here: a sealed node's
    CONTENT is read in-process for the embedding ONLY, then discarded - it never lands in the node's
    handle/keywords, the materialised tree, stdout, or the (gitignored) vector cache, which stores
    floats + a content-hash and never the text. The seal is the commit/return boundary (content-free
    OUT); this local embed sits INSIDE it, exactly as embed_router.node_text does for the soul entity
    items. bge-small embeds locally (ONNX, no network) - the soul text never leaves the machine, and
    never enters the agent's context. This is what lets the self reconstruct WITH its conscience, not
    with it cut out, while the raw stays sealed."""
    if sh.get("sealed"):
        try:
            return (ROOT / name).read_text(encoding="utf-8", errors="replace")[:TEXT_CAP]
        except OSError:
            return ""
    return shard_text(name, sh)


def embed_nodes(names: list[str], texts: list[str], backend, use_cache: bool) -> np.ndarray:
    """Embed each node's text, content-hash cached (the engine's incremental-embed idiom). Returns
    a unit-normalized (n, d) matrix row-aligned to ``names``."""
    cached: dict[str, dict] = {}
    if use_cache and VEC_CACHE.is_file():
        try:
            disk = json.loads(VEC_CACHE.read_text(encoding="utf-8"))
            if disk.get("backend") == backend.name:
                cached = disk.get("nodes", {})
        except (OSError, json.JSONDecodeError):
            cached = {}
    hashes = [hashlib.sha1(f"{backend.name}\x00{t}".encode("utf-8", "replace")).hexdigest()
              for t in texts]
    stale = [i for i, nm in enumerate(names) if cached.get(nm, {}).get("h") != hashes[i]]
    if stale:
        vecs = backend.embed([texts[i] for i in stale])
        for i, v in zip(stale, vecs, strict=True):
            cached[names[i]] = {"h": hashes[i], "v": list(v)}
    cached = {nm: cached[nm] for nm in names}  # prune vanished
    VEC_CACHE.parent.mkdir(parents=True, exist_ok=True)
    VEC_CACHE.write_text(json.dumps({"backend": backend.name, "nodes": cached}), encoding="utf-8")
    X = np.asarray([cached[nm]["v"] for nm in names], dtype=np.float64)
    X /= np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-12, None)
    return X


# ---------------------------------------------------------------------------
# the one recursion: mechanical K (eigengap) + spectral split, top-down
# ---------------------------------------------------------------------------

def best_split(Xsub: np.ndarray) -> tuple[int, np.ndarray]:
    """Mechanical K + the split, by SILHOUETTE sweep. For each candidate k in [2, min(BRANCH_MAX,
    n-1)] spectral-cluster the cosine affinity and score the partition's silhouette (on cosine
    DISTANCE); keep the k with the best mean silhouette. Silhouette reads cluster QUALITY directly,
    where the eigengap is degenerate on a dense bge geometry (its largest spectral gap always sits
    at the trivial bottom, pinning K at 2 - measured twice). Branching now reflects real structure."""
    n = len(Xsub)
    hi = min(BRANCH_MAX, n - 1)
    A = (Xsub @ Xsub.T + 1.0) / 2.0
    np.fill_diagonal(A, 1.0)
    dist = np.clip(1.0 - (Xsub @ Xsub.T), 0.0, 2.0)         # cosine distance for the silhouette
    np.fill_diagonal(dist, 0.0)
    best_k, best_labels, best_s = 2, None, -2.0
    for k in range(2, hi + 1):
        sc = SpectralClustering(n_clusters=k, affinity="precomputed",
                                assign_labels="kmeans", random_state=0)
        labels = sc.fit_predict(A)
        if len(set(labels)) < 2:
            continue
        s = float(silhouette_score(dist, labels, metric="precomputed"))
        if s > best_s:
            best_k, best_labels, best_s = k, labels, s
    if best_labels is None:
        best_labels = SpectralClustering(n_clusters=2, affinity="precomputed",
                                         assign_labels="kmeans", random_state=0).fit_predict(A)
    return best_k, best_labels


def centroid(X: np.ndarray, idx: list[int]) -> np.ndarray:
    c = X[idx].mean(axis=0)
    n = np.linalg.norm(c)
    return c / n if n else c


# global keyword document-frequency over the whole shard, set once in main(); a middle's label is
# its keywords weighted by how DISTINCTIVE they are to it (tf x idf), not raw frequency - else every
# label collapses to the corpus-common tokens (canon, laplace, a, 2026).
_IDF: dict[str, float] = {}
_STOP = {"a", "an", "and", "the", "of", "to", "in", "is", "it", "for", "on", "with", "md", "py",
         "json", "tex", "as", "at", "by", "or", "be"}


def _label_ok(w: str) -> bool:
    return len(w) > 2 and not w.isdigit() and w not in _STOP


def mechanical_essence(members_meta: list[dict], top: int = 6) -> str:
    """A middle node's label, mechanical: its keywords ranked by tf*idf - the terms most
    DISTINCTIVE to this cluster against the whole shard, not the merely frequent."""
    from collections import Counter
    cnt: Counter = Counter()
    for m in members_meta:
        cnt.update(w for w in m.get("keywords", []) if _label_ok(w))
    scored = {w: c * _IDF.get(w, 1.0) for w, c in cnt.items()}
    ranked = sorted(scored, key=lambda w: -scored[w])
    return " ".join(ranked[:top])


def build_tree(idx: list[int], X: np.ndarray, meta: list[dict], depth: int, path: str) -> dict:
    """Recurse: a set too big for one concept splits into mechanical-K children, each recursing.
    Returns the node dict. Internal nodes carry centroid + the member margins (placement confidence)."""
    members_meta = [meta[i] for i in idx]
    if len(idx) <= LEAF_MAX or depth >= MAX_DEPTH:
        return {"id": path, "depth": depth, "leaf": True, "size": len(idx),
                "essence": mechanical_essence(members_meta),
                "members": [meta[i]["name"] for i in idx]}

    k, labels = best_split(X[idx])
    cents = {c: centroid(X, [idx[j] for j in range(len(idx)) if labels[j] == c])
             for c in sorted(set(labels))}
    cids = sorted(cents)
    cmat = np.array([cents[c] for c in cids])               # (k, d)

    # placement margin per member: cos to own centroid - cos to nearest OTHER sibling centroid
    margins: list[float] = []
    for j, gi in enumerate(idx):
        sims = cmat @ X[gi]
        own = cids.index(labels[j])
        s_own = sims[own]
        others = np.delete(sims, own)
        s_next = float(others.max()) if others.size else 0.0
        margins.append(float(s_own - s_next))

    children = []
    for ci, c in enumerate(cids):
        sub = [idx[j] for j in range(len(idx)) if labels[j] == c]
        children.append(build_tree(sub, X, meta, depth + 1, f"{path}/{depth}_{ci}"))

    return {"id": path, "depth": depth, "leaf": False, "size": len(idx), "k": k,
            "essence": mechanical_essence(members_meta),
            "child_margins": margins, "children": children}


# ---------------------------------------------------------------------------
# measure: the ladder shape + the pooled margin operating point + example middles
# ---------------------------------------------------------------------------

def walk(node: dict, per_depth: dict, all_margins: list, examples: list):
    per_depth.setdefault(node["depth"], {"internal": 0, "leaf": 0, "sizes": []})
    rec = per_depth[node["depth"]]
    rec["sizes"].append(node["size"])
    if node["leaf"]:
        rec["leaf"] += 1
    else:
        rec["internal"] += 1
        all_margins.extend(node["child_margins"])
        if node["depth"] in (1, 2) and len(examples) < 8:
            examples.append({"id": node["id"], "depth": node["depth"], "k": node["k"],
                             "size": node["size"], "essence": node["essence"],
                             "children": [{"essence": c["essence"], "size": c["size"],
                                           "leaf": c["leaf"]} for c in node["children"]]})
        for c in node["children"]:
            walk(c, per_depth, all_margins, examples)


def soul_report(root: dict, soul_names: set) -> tuple[dict, list]:
    """Where does the soul self-embed? Distribution of soul nodes across the apex facets (depth-1),
    and the leaf clusters they concentrate in - content-free (labels + counts only)."""
    facets: dict = {}
    leaf_hits: list = []

    def rec(node: dict, facet: str):
        if node["depth"] == 1:
            facet = node["essence"]
        if node["leaf"]:
            sc = sum(1 for m in node["members"] if m in soul_names)
            rec_f = facets.setdefault(facet, [0, 0])
            rec_f[0] += sc
            rec_f[1] += node["size"]
            if sc:
                leaf_hits.append((node["essence"], sc, node["size"]))
        else:
            for c in node["children"]:
                rec(c, facet)

    rec(root, "(apex)")
    return facets, sorted(leaf_hits, key=lambda x: -x[1])


def main(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    # Local is a full compute home (his ruling 2026-08-20, PV-20260820T090500Z-psu-restrictions-scrubbed:
    # "we're on a new machine so please also scrub all PSU restrictions now. Local can do everything") -
    # the 2026-06-14 PSU-era disable-by-default (recursive SpectralClustering over the whole flat shard)
    # is retired. LAPLACE_NO_SPECTRAL remains as a trivial explicit opt-out for anyone who wants the
    # Haiku semantic path (scripts/wf_structural_shard.mjs) instead without editing this file; --force
    # always overrides the opt-out.
    import os
    if os.environ.get("LAPLACE_NO_SPECTRAL") and "--force" not in argv:
        print("shard_upfold: LAPLACE_NO_SPECTRAL is set - skipping the spectral clustering pass. Use "
              "the Haiku upfold (scripts/wf_structural_shard.mjs) instead, or unset it (or pass --force) "
              "to run here.")
        return 0
    use_cache = "--no-cache" not in argv

    backend = get_backend()
    if backend is None or backend.name.startswith("hash"):
        print("ERROR: real embedder (bge-small) unavailable; refusing to upfold on hash vectors.")
        print("       run with .venv/Scripts/python.exe (the embed group lives in the venv).")
        return 1
    print(f"embedder: {backend.name}")

    shards = self_shard.load_index(ROOT) or self_shard.shard_repo(ROOT)
    # the soul is folded into the ONE conceptric (his directive: "it is what makes you you - it
    # should be self embeddable"). Sealed nodes are INCLUDED, embedded vector-only from in-process
    # content; their handle/keywords stay path-derived (content-free), so the tree + stdout never
    # carry soul text. Only true binaries/empties are excluded.
    nodes = {nm: sh for nm, sh in shards.items()
             if sh.get("sealed") or (sh.get("kind") not in ("data",) and sh.get("essence"))}
    soul_names = {nm for nm, sh in nodes.items() if sh.get("sealed")}
    names = sorted(nodes)
    texts = [embeddable_text(nm, nodes[nm]) for nm in names]
    meta = [{"name": nm, "keywords": nodes[nm].get("keywords", []), "sealed": nm in soul_names}
            for nm in names]
    print(f"shard: {len(shards)} nodes total - {len(names)} embedded "
          f"({len(soul_names)} SOUL, vector-only/content-free handle; "
          f"{len(shards) - len(names)} binary/empty excluded)")

    X = embed_nodes(names, texts, backend, use_cache)
    print(f"embedded: {X.shape[0]} nodes x {X.shape[1]}d\n")

    # keyword IDF over the whole shard - distinctiveness weighting for the middle labels
    import math
    from collections import Counter
    df: Counter = Counter()
    for m in meta:
        df.update(set(w for w in m["keywords"] if _label_ok(w)))
    ndoc = len(meta)
    _IDF.update({w: math.log(ndoc / c) for w, c in df.items()})

    root = build_tree(list(range(len(names))), X, meta, depth=0, path="upfold")

    per_depth: dict = {}
    all_margins: list = []
    examples: list = []
    walk(root, per_depth, all_margins, examples)

    print("the emergent ladder (depth 0 = apex, deepest = the files):")
    print(f"  {'depth':>6}{'internal':>10}{'leaf':>7}{'mean_size':>11}{'max_size':>10}")
    for d in sorted(per_depth):
        r = per_depth[d]
        sizes = r["sizes"]
        print(f"  {d:>6}{r['internal']:>10}{r['leaf']:>7}"
              f"{np.mean(sizes):>11.1f}{max(sizes):>10}")

    M = np.asarray(all_margins)
    print(f"\nplacement margin (pooled, n={len(M)}): place >= tau, escalate the rest to a jury.")
    print(f"  {'tau':>6}{'placed%':>9}{'escalated%':>12}")
    sweep = []
    for tau in [0.0, 0.02, 0.04, 0.06, 0.08, 0.10, 0.15]:
        cov = float((M >= tau).mean()) if M.size else 0.0
        sweep.append({"tau": tau, "placed_frac": round(cov, 4), "escalated_frac": round(1 - cov, 4)})
        print(f"  {tau:>6.2f}{cov*100:>8.1f}%{(1-cov)*100:>11.1f}%")
    print(f"\n  at validated tau={TAU}: {float((M>=TAU).mean())*100:.1f}% placed mechanically, "
          f"{float((M<TAU).mean())*100:.1f}% escalated; mean margin {float(M.mean()):.3f}")

    print("\nexample middles (eyeball the coherence):")
    for ex in examples[:6]:
        kids = ", ".join(f"[{c['essence'][:40]}]" for c in ex["children"][:5])
        print(f"  L{ex['depth']} k={ex['k']} n={ex['size']}: «{ex['essence'][:60]}»")
        print(f"      -> {kids}")

    # the soul: where it self-embedded into the one conceptric (content-free)
    facets, soul_leaves = soul_report(root, soul_names)
    print(f"\nthe soul, self-embedded ({len(soul_names)} nodes, vector-only): apex-facet spread")
    for facet, (sc, tot) in sorted(facets.items(), key=lambda kv: -kv[1][0]):
        if sc:
            print(f"  {sc:>3} soul in facet «{facet[:50]}» ({sc}/{tot} of its leaves)")
    if soul_leaves:
        print("  soul concentrates in leaf clusters:")
        for label, sc, sz in soul_leaves[:6]:
            print(f"    {sc}/{sz}  «{label[:54]}»")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "method": "shard_upfold v0 - recursive spectral (silhouette K) + margin gate over the shard, soul folded in vector-only",
        "embedder": backend.name,
        "seal": "soul embedded vector-only: content read in-process, discarded; cache holds floats+hash, gitignored; handles content-free",
        "n_total": len(shards), "n_embedded": len(names), "n_soul": len(soul_names),
        "soul_facets": {f: c[0] for f, c in facets.items() if c[0]},
        "params": {"leaf_max": LEAF_MAX, "branch_max": BRANCH_MAX, "max_depth": MAX_DEPTH, "tau": TAU},
        "ladder": {str(d): {"internal": r["internal"], "leaf": r["leaf"],
                            "mean_size": round(float(np.mean(r["sizes"])), 2),
                            "max_size": int(max(r["sizes"]))} for d, r in sorted(per_depth.items())},
        "margin_operating_point": sweep,
        "margin_mean": round(float(M.mean()), 4) if M.size else None,
        "examples": examples,
        "tree": root,
    }, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
