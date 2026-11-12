#!/usr/bin/env python3
"""recursive_read_harness.py - score the recursive read path against the flat cache.

The strangler pattern's validation leg (his 07-28 framing: the flat cache is the ORACLE while the
new organ grows beside it). The residue-vector store holds a vector for every leaf; brute-force
cosine over it is ground truth by construction, because it is the same geometry the tree's
centroids were folded from. This harness asks one question per query: how much of the oracle's
top-k does a descent recover, and at what cost.

THE STORE, since 2026-08-20 (MV-1): the ``.meaning_vectors.f32.npy`` + ``.meaning_vectors.index.json``
sidecar pair, read here through ``meaning_upfold.load_vectors`` - which falls back to the legacy
``.meaning_vectors.json`` monolith, naming the fallback, for as long as that file survives the
transition. The oracle's numbers are unchanged by the migration: every value the JSON held was
exactly a float32, so the binary store is the same ground truth in 20% of the bytes.

METRICS, per beam width:
  overlap@k      |recursive top-k INTERSECT oracle top-k| / k, averaged over queries. The headline:
                 what the pruning costs.
  Kendall tau    rank agreement on the intersection (tau-b). MEASURED AND REPORTED, but it is 1.000
                 by construction and carries no information here: both paths score a leaf by the
                 same plain cosine, so any leaf the descent recovers sits in the same relative
                 order the oracle put it in. It is kept because a future change that makes the
                 descent score differently (path-inherited heat, a learned metric) would break that
                 identity, and tau is the tripwire that would say so. Undefined below a 2-item
                 intersection: skipped and counted, never reported as 0.
  top1           fraction of queries where the descent's best leaf IS the oracle's best leaf.
  score deficit  mean(oracle top-k cosine) - mean(recursive top-k cosine). What the misses actually
                 cost in the geometry - a missed leaf that scored 0.699 against a kept 0.700 is a
                 different failure than one that scored 0.4, and overlap@k cannot tell them apart.
  materialized   leaf vectors the recursive path computed. The oracle's count is every leaf it
                 dots, which is the whole corpus - that difference IS the design.
  seconds        wall-clock per query, both paths. Reported because it does not flatter the new
                 path: re-embedding is slower than a matmul over vectors already on disk.

QUERY SAMPLE (--queries N, half of each, deterministic under --seed):
  (a) cluster labels - the IDF-distinctive phrases meaning_upfold authored on the clusters. Real
      corpus vocabulary, and the phrasing a caller would plausibly type.
  (b) leaf source texts truncated to the first 12 words - a "find me this document" probe.
  Both are embedded through backend.query() (the bge retrieval prefix), the same call the
  recursive path makes, so the two paths compare one query vector, not two.

  A leaf-text query is NOT excluded from its own answer: the oracle ranks it first and so should
  the descent, so those queries measure whether the descent can find the thing it was handed.

NO ORACLE ON THIS BOX: if NO residue-vector store is present at all (they are gitignored - this is
a sealed-derived store and the 2026-08-01 perimeter law keeps it off any boundary that travels),
the harness builds a SYNTHETIC mini-corpus with a deterministic in-process backend, folds a real
tree over it, and scores that instead - clearly marked in the output. The synthetic run proves the
harness and the descent mechanics; it is not evidence about the real map. A store that is PRESENT
but unreadable REFUSES instead of falling through here (MV-3, 2026-08-20): a fabricated corpus
printed as the real map is worse than no number at all.

Usage:
    PYTHONPATH=src python3 scripts/recursive_read_harness.py --queries 40 --k 10 --beams 2,4,8,16
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from laplace.engine import meaning_upfold, recursive_read  # noqa: E402

# ---------------------------------------------------------------------------
# scoring
# ---------------------------------------------------------------------------

def overlap_at_k(recursive: list[str], oracle: list[str], k: int) -> float:
    return len(set(recursive[:k]) & set(oracle[:k])) / float(k)


def kendall_tau(recursive: list[str], oracle: list[str]) -> float | None:
    """Tau-b over the items both lists contain, ranked by each list's own order.

    Written out rather than pulled from scipy: the analysis extra is optional in this repo, k is
    <= 20, and O(k^2) on 20 items is free. None when fewer than two shared items - an undefined
    tau is reported as undefined, never as 0.0."""
    shared = [x for x in oracle if x in set(recursive)]
    if len(shared) < 2:
        return None
    r_rank = {name: i for i, name in enumerate(recursive)}
    o_rank = {name: i for i, name in enumerate(oracle)}
    concordant = discordant = 0
    for i in range(len(shared)):
        for j in range(i + 1, len(shared)):
            a, b = shared[i], shared[j]
            sign = (r_rank[a] - r_rank[b]) * (o_rank[a] - o_rank[b])
            if sign > 0:
                concordant += 1
            elif sign < 0:
                discordant += 1
    total = concordant + discordant
    return (concordant - discordant) / total if total else None


# ---------------------------------------------------------------------------
# the oracle - brute force over the flat cache
# ---------------------------------------------------------------------------

class FlatOracle:
    """Every tree leaf's banked vector as one matrix. ``rank`` is a single (n, d) @ (d,) dot.

    Restricted to leaves the TREE knows: the two paths must range over the same universe or the
    overlap number is measuring corpus drift instead of pruning. Leaves in the tree but absent from
    the cache are reported, not dropped quietly."""

    def __init__(self, repo: Path, tree: dict):
        import numpy as np
        # MV-1 (2026-08-20): the store is the binary sidecar pair, read through the module's own
        # API - which falls back to the legacy .meaning_vectors.json monolith, named, when the
        # pair is absent. Either way the oracle is the SAME float64 values it always dotted:
        # every value in this store is exactly a float32, so the encoding change is not an
        # approximation of the ground truth, it is the ground truth in fewer bytes.
        backend_name, names, mat_all = meaning_upfold.load_vectors(repo)
        if backend_name != tree["version"]:
            raise SystemExit(f"oracle backend {backend_name!r} != tree version "
                             f"{tree['version']!r} - refusing to score across geometries")
        row = {n: i for i, n in enumerate(names)}
        leaves = sorted(tree["leaf_sha"])
        self.missing = [n for n in leaves if n not in row]
        self.names = [n for n in leaves if n in row]
        mat = np.asarray(mat_all[[row[n] for n in self.names]], dtype=np.float64)
        mat /= np.clip(np.linalg.norm(mat, axis=1, keepdims=True), 1e-12, None)
        self.mat = mat
        self._np = np

    def rank(self, qv, k: int) -> tuple[list[str], list[float], float]:
        t0 = time.perf_counter()
        scores = self.mat @ qv
        order = self._np.argsort(-scores, kind="stable")[:k]
        return ([self.names[i] for i in order], [float(scores[i]) for i in order],
                time.perf_counter() - t0)


# ---------------------------------------------------------------------------
# the synthetic fallback
# ---------------------------------------------------------------------------

class SyntheticBackend:
    """Deterministic offline geometry - four keyword families on orthogonal axes plus jitter. Same
    idiom as tests/test_meaning_upfold_incremental.py's FakeBackend; NOT the hash router."""

    name = "synthetic:harness-v1"
    FAMILIES = ("alpha", "beta", "gamma", "delta")
    dim = 12

    def _vec(self, text: str) -> list[float]:
        import hashlib
        v = [0.0] * self.dim
        fam = 0
        for i, key in enumerate(self.FAMILIES):
            if key in text:
                fam, v[i] = i, 1.0
                break
        h = int(hashlib.sha1(text.encode("utf-8")).hexdigest(), 16)
        for off in range(4):
            v[4 + ((fam * 2 + off) % 8)] += ((h >> (off * 8)) % 100) / 400.0
        n = sum(x * x for x in v) ** 0.5
        return [x / n for x in v] if n else v

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def query(self, text: str) -> list[float]:
        return self._vec(text)


def build_synthetic(tmp: Path, n_per_family: int = 40) -> tuple[dict, dict, SyntheticBackend]:
    """Fold a real tree over a synthetic residue, and hand back the leaf texts as the leaf source."""
    backend = SyntheticBackend()
    residue = {}
    for fam in SyntheticBackend.FAMILIES:
        for i in range(n_per_family):
            nid = f"synthetic/{fam}/doc_{i:03d}.md"
            residue[nid] = {"kind": "file", "essence": f"{fam} document {i}",
                            "keywords": [fam, f"topic{i % 7}", f"item{i}"], "leaf": True}
    import laplace.representation.embed_router as er
    real_get = er.get_backend
    er.get_backend = lambda: backend
    try:
        pm, cn = meaning_upfold.cluster_residue_incremental(
            tmp, residue, None, root_id="", lens_hash="synthetic", allow_spectral=True,
            lens_pairs=[])
    finally:
        er.get_backend = real_get
    if not cn:
        raise SystemExit("synthetic fold produced no clusters - cannot score the descent")
    tree = meaning_upfold.load_tree(tmp)
    return tree, residue, backend


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------

def sample_queries(tree: dict, leaf_source, n: int, rng: random.Random) -> list[tuple[str, str]]:
    labels = sorted({c["label"] for c in tree["clusters"].values() if c.get("label")})
    leaves = sorted(tree["leaf_sha"])
    half = n // 2
    out = [("label", q) for q in rng.sample(labels, min(half, len(labels)))]
    for name in rng.sample(leaves, min(n - len(out), len(leaves))):
        words = leaf_source(name).split()
        if words:
            out.append(("leaf-text", " ".join(words[:12])))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--queries", type=int, default=40)
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--beams", default="2,4,8,16")
    ap.add_argument("--seed", type=int, default=20260728)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    beams = [int(b) for b in args.beams.split(",") if b.strip()]
    rng = random.Random(args.seed)

    import numpy as np

    # MV-3's objection (2026-08-20): the synthetic branch may only fire when there is NO store at
    # all. A store that is PRESENT but unreadable must refuse - falling through to the synthetic
    # corpus would silently score a fabricated mini-corpus and print it as the real map, which is
    # the exact silent-degrade class recursive_read.py names as its enemy.
    _vec, _idx = meaning_upfold.sidecar_paths(REPO)
    _store = ([p for p in (_vec, _idx) if p.is_file()]
              + [p for p in (REPO / meaning_upfold.CACHE_FILE,) if p.is_file()])
    synthetic = not _store
    tmpdir = None
    if synthetic:
        import tempfile
        tmpdir = tempfile.mkdtemp(prefix="rr_harness_")
        root = Path(tmpdir)
        print(f"SYNTHETIC RUN: no residue-vector store under {REPO} - neither the "
              f"{meaning_upfold.VEC_FILE} + {meaning_upfold.IDX_FILE} sidecar nor the legacy "
              f"{meaning_upfold.CACHE_FILE} (all gitignored). "
              f"Folding a synthetic mini-corpus in {root}. These numbers describe the harness and "
              f"the descent mechanics, NOT the real map.")
        tree, residue, backend = build_synthetic(root)
        leaf_source = _synthetic_leaf_source(root, residue)
        # the synthetic oracle is the same vectors, computed directly
        oracle = _SyntheticOracle(tree, leaf_source, backend)
        dsc_kwargs = {"tree": tree, "backend": backend, "leaf_source": leaf_source,
                      "allow_test_backend": True}
    else:
        root = REPO
        tree = meaning_upfold.load_tree(root)
        if tree is None:
            raise SystemExit(f"{REPO / meaning_upfold.TREE_FILE} did not parse")
        try:
            oracle = FlatOracle(root, tree)
        except FileNotFoundError as exc:
            raise SystemExit(
                f"a residue-vector store IS present ({', '.join(p.name for p in _store)}) but the "
                f"oracle could not load it: {exc}. Refusing - the synthetic fallback would score a "
                f"fabricated mini-corpus and print it as the real map.") from exc
        leaf_source = recursive_read.SelfGradedLeafSource(root)
        dsc_kwargs = {"tree": tree, "leaf_source": leaf_source}
        print(f"REAL RUN: tree {tree['version']} - {len(tree['clusters'])} clusters, "
              f"{len(tree['leaf_sha'])} leaves; oracle covers {len(oracle.names)} of them"
              + (f" ({len(oracle.missing)} tree leaves absent from the flat cache: "
                 f"{', '.join(oracle.missing[:4])})" if oracle.missing else ""))

    dsc = recursive_read.open_descender(root, **dsc_kwargs)
    queries = sample_queries(tree, leaf_source, args.queries, rng)
    print(f"{len(queries)} queries "
          f"({sum(1 for kind, _ in queries if kind == 'label')} cluster labels, "
          f"{sum(1 for kind, _ in queries if kind == 'leaf-text')} leaf texts), k={args.k}, "
          f"seed={args.seed}\n")

    # the oracle leg, once - it does not depend on beam
    oracle_top: dict[str, list[str]] = {}
    oracle_scores: dict[str, list[float]] = {}
    oracle_secs = []
    for _kind, q in queries:
        qv = np.asarray(dsc.backend.query(q), dtype=np.float64)
        qv /= np.clip(np.linalg.norm(qv), 1e-12, None)
        top, sc, secs = oracle.rank(qv, args.k)
        oracle_top[q] = top
        oracle_scores[q] = sc
        oracle_secs.append(secs)

    rows = []
    for beam in beams:
        ov, taus, mats, secs, undefined, stale = [], [], [], [], 0, set()
        top1, deficits = [], []
        for _kind, q in queries:
            packet = dsc.descend(q, k=args.k, beam=beam)
            got = [h["id"] for h in packet["hits"]]
            ov.append(overlap_at_k(got, oracle_top[q], args.k))
            tau = kendall_tau(got, oracle_top[q])
            if tau is None:
                undefined += 1
            else:
                taus.append(tau)
            top1.append(1.0 if got and got[0] == oracle_top[q][0] else 0.0)
            mine = [h["score"] for h in packet["hits"]]
            theirs = oracle_scores[q][:len(mine)] or [0.0]
            deficits.append(sum(theirs) / len(theirs) - (sum(mine) / len(mine) if mine else 0.0))
            mats.append(packet["materialized"])
            secs.append(packet["seconds"])
            stale.update(packet["stale"])
        row = {"beam": beam, "overlap_at_k": round(sum(ov) / len(ov), 4),
               "kendall_tau": (round(sum(taus) / len(taus), 4) if taus else None),
               "tau_undefined": undefined,
               "top1_hit_rate": round(sum(top1) / len(top1), 4),
               "score_deficit_mean": round(sum(deficits) / len(deficits), 4),
               "materialized_mean": round(sum(mats) / len(mats), 1),
               "seconds_mean": round(sum(secs) / len(secs), 4),
               "stale_leaves": sorted(stale)}
        rows.append(row)
        print(f"beam {beam:>3}  overlap@{args.k} {row['overlap_at_k']:.3f}  "
              f"tau {row['kendall_tau'] if row['kendall_tau'] is not None else 'n/a '}"
              f"(undef {undefined:>2})  top1 {row['top1_hit_rate']:.3f}  "
              f"deficit {row['score_deficit_mean']:+.4f}  "
              f"materialized {row['materialized_mean']:>7.1f}  "
              f"{row['seconds_mean']:.3f} s/query")

    n_oracle_vecs = len(oracle.names) if not synthetic else len(tree["leaf_sha"])
    print(f"\nbrute force  overlap@{args.k} 1.000  tau 1.0   (undef  0)  top1 1.000  "
          f"deficit +0.0000  materialized {n_oracle_vecs:>7}  "
          f"{sum(oracle_secs) / len(oracle_secs):.4f} s/query "
          f"(vectors read from disk, not recomputed)")

    report = {"synthetic": synthetic, "seed": args.seed, "k": args.k,
              "n_queries": len(queries), "tree_version": tree["version"],
              "n_clusters": len(tree["clusters"]), "n_leaves": len(tree["leaf_sha"]),
              "oracle_vectors": n_oracle_vecs,
              "oracle_seconds_mean": round(sum(oracle_secs) / len(oracle_secs), 5),
              "oracle_missing_leaves": (oracle.missing if not synthetic else []),
              "rows": rows}
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nwrote {args.out}")
    return 0


def _synthetic_leaf_source(root: Path, residue: dict):
    def source(name: str) -> str:
        node = residue.get(name)
        if node is None:
            raise recursive_read.RecursiveReadError(
                "leaf-source-unreadable", f"synthetic leaf {name!r} has no source")
        return meaning_upfold._embeddable_text(root, name, node, 480)
    return source


class _SyntheticOracle:
    """Brute force over the synthetic corpus - every leaf embedded directly, no cache file."""

    def __init__(self, tree: dict, leaf_source, backend):
        import numpy as np
        self.names = sorted(tree["leaf_sha"])
        self.missing: list[str] = []
        mat = np.asarray(backend.embed([leaf_source(n) for n in self.names]), dtype=np.float64)
        mat /= np.clip(np.linalg.norm(mat, axis=1, keepdims=True), 1e-12, None)
        self.mat = mat
        self._np = np

    def rank(self, qv, k: int):
        t0 = time.perf_counter()
        scores = self.mat @ qv
        order = self._np.argsort(-scores, kind="stable")[:k]
        return ([self.names[i] for i in order], [float(scores[i]) for i in order],
                time.perf_counter() - t0)


if __name__ == "__main__":
    raise SystemExit(main())
