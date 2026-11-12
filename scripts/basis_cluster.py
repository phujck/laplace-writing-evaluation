"""N42 - the basis-projection clusterer, validated against the banked Sonnet upfolds.

His conjecture (2026-06-11, the Griffiths call; memory
``grades-are-basis-projection-clustering-mechanical``): pushing down grades = projecting
through a basis, so CLUSTERING itself can go mechanical -- generators are basis directions,
membership is the largest coefficient, bleed is the off-diagonal mass. If it holds against the
8 banked Sonnet upfolds, the upfold runs mechanical forever and the loose atoms that flood the
dream's wire-proposal audit get placed instead of flagged.

This is the VALIDATION HARNESS, not yet the production operator. The ground truth is the
Sonnet upfold's ``program`` (papers -> generators) in each ``<key>.json``; the atoms are the
``ladders`` (one paper each). Two tests, reported plainly -- the thresholds are HIS to read
(F1), this only measures:

  TEST A  membership-is-mechanical: given the Sonnet generators as basis directions, does the
          largest coefficient (nearest centroid, cosine) route each atom to its Sonnet home?
          Leave-one-out, so an atom never votes for its own placement. This is the weaker,
          practically decisive claim -- it is what drains the loose-atom flood.

  TEST B  clustering-is-mechanical: derive K clusters from the geometry ALONE (spectral
          embedding = the basis projection, then k-means), and match them to the Sonnet
          partition (Hungarian). ARI / NMI / best-match accuracy. The stronger claim.

The only model calls are embeddings (bge-small, local, fold-time). No LLM, no Opus.

Usage:  python scripts/basis_cluster.py            # all 8 banked corpora
        python scripts/basis_cluster.py magann     # one
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
from sklearn.cluster import SpectralClustering
from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score
from scipy.optimize import linear_sum_assignment

ROOT = Path(__file__).resolve().parent.parent
STRUCT_DIR = ROOT / "collaborator_corpus" / "_structural"
BANKED = ["alanissila", "balanov", "bondar", "booth", "jacobs", "magann", "totero", "mccaul"]

sys.path.insert(0, str(ROOT / "src"))
from laplace.representation.embed_router import get_backend  # noqa: E402


def canon(pid: str) -> str:
    m = re.match(r"(W\d+)", str(pid).strip())
    return m.group(1) if m else str(pid).strip()


def atom_text(lad: dict) -> str:
    """One paper as bge-embeddable text. Discriminative fields first (the program identity
    lives in goal/approach/technique, not the title) so internal truncation drops the tail."""
    techs = lad.get("techniques", []) or []
    tech = "; ".join(f"{t.get('name','')}: {t.get('statement','')}".strip(": ") for t in techs)
    res = "; ".join(r.get("claim", "") for r in (lad.get("results", []) or []))
    parts = [
        lad.get("meta_goal", ""),
        lad.get("approach", ""),
        tech,
        lad.get("title", ""),
        res,
    ]
    return "  ".join(p for p in parts if p).strip()


def load_corpus(key: str):
    """Return (ids, texts, gold_labels, report). gold = Sonnet generator index per atom;
    atoms outside the program, and program ids without an embeddable ladder, are dropped and
    counted. Multi-membership atoms (an id under >1 generator) are counted as bleed and
    assigned to their first generator for the hard-partition metrics."""
    struct = json.loads((STRUCT_DIR / f"{key}.json").read_text(encoding="utf-8"))
    upfold = struct.get("upfold") or {}
    program_list = struct.get("program") or upfold.get("program") or []

    # canonical-id -> atom text (first ladder occurrence wins, matching assemble_regrade)
    ladder_text: dict[str, str] = {}
    for lad in struct.get("ladders", []):
        cid = canon(lad["id"])
        ladder_text.setdefault(cid, atom_text(lad))

    # gold membership: generator index per canonical id; record multi-membership
    gen_of: dict[str, int] = {}
    multi = 0
    seen: set[str] = set()
    for gi, p in enumerate(program_list):
        for raw in p.get("papers", []):
            cid = canon(raw)
            if cid in seen and gen_of.get(cid) != gi:
                multi += 1
            seen.add(cid)
            gen_of.setdefault(cid, gi)  # first generator wins

    # full membership sets (an id under >1 generator) for the soft (fair) metric
    gen_sets: dict[str, set[int]] = {}
    for gi, p in enumerate(program_list):
        for raw in p.get("papers", []):
            gen_sets.setdefault(canon(raw), set()).add(gi)

    ids, texts, gold, gold_sets = [], [], [], []
    no_text = 0
    for cid, gi in gen_of.items():
        if cid in ladder_text and ladder_text[cid]:
            ids.append(cid)
            texts.append(ladder_text[cid])
            gold.append(gi)
            gold_sets.append(gen_sets[cid])
        else:
            no_text += 1

    report = {
        "n_generators": len(program_list),
        "n_program_papers": len(gen_of),
        "n_embedded": len(ids),
        "n_program_without_ladder": no_text,
        "n_ladders": len(ladder_text),
        "n_multi_membership": multi,
    }
    return ids, texts, np.asarray(gold, dtype=int), gold_sets, report


def test_a_membership(X: np.ndarray, gold: np.ndarray, gold_sets, K: int):
    """Leave-one-out nearest-Sonnet-centroid. X is unit-normalized so dot = cosine.
    Returns hard agreement (== first generator), soft agreement (in ANY of the atom's Sonnet
    generators - the fair number, since the Sonnet itself multi-placed the bleed atoms), the
    mean top1-top2 margin, and per-atom (margin, soft-correct) arrays for the coverage sweep."""
    n = len(gold)
    # centroid sums per generator (un-normalized); LOO subtracts the atom itself
    dim = X.shape[1]
    sums = np.zeros((K, dim), dtype=np.float64)
    counts = np.zeros(K, dtype=int)
    for i in range(n):
        sums[gold[i]] += X[i]
        counts[gold[i]] += 1

    pred = np.empty(n, dtype=int)
    margins = np.empty(n, dtype=float)
    for i in range(n):
        g = gold[i]
        cent = sums.copy()
        cent[g] -= X[i]                       # leave this atom out of its own home
        cnt = counts.copy()
        cnt[g] -= 1
        valid = cnt > 0
        # unit-normalize centroids; invalid (now-empty) generators score -inf
        norms = np.linalg.norm(cent, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        cu = cent / norms
        sims = cu @ X[i]
        sims[~valid] = -np.inf
        order = np.argsort(sims)[::-1]
        pred[i] = order[0]
        top2 = sims[order[1]] if len(order) > 1 and np.isfinite(sims[order[1]]) else 0.0
        margins[i] = sims[order[0]] - top2

    hard = (pred == gold)
    soft = np.array([pred[i] in gold_sets[i] for i in range(n)])
    return {"agreement": round(float(hard.mean()), 4),
            "agreement_soft": round(float(soft.mean()), 4),
            "mean_margin": round(float(margins.mean()), 4),
            "margins": margins, "soft_correct": soft, "n": n}


def test_b_clustering(X: np.ndarray, gold: np.ndarray, K: int):
    """Spectral embedding (the basis projection) + k-means, matched to the Sonnet partition.
    affinity = cosine (X is unit-normalized, so XX^T), shifted to [0,1] non-negative."""
    if len(gold) <= K:
        return {"skipped": "n<=K"}
    aff = (X @ X.T + 1.0) / 2.0
    np.fill_diagonal(aff, 1.0)
    sc = SpectralClustering(n_clusters=K, affinity="precomputed",
                            assign_labels="kmeans", random_state=0)
    pred = sc.fit_predict(aff)

    # Hungarian best-match accuracy on the contingency table
    C = np.zeros((K, K), dtype=int)
    for p, g in zip(pred, gold):
        C[p, g] += 1
    row, col = linear_sum_assignment(-C)
    matched = int(C[row, col].sum())
    acc = matched / len(gold)
    return {"ari": round(float(adjusted_rand_score(gold, pred)), 4),
            "nmi": round(float(normalized_mutual_info_score(gold, pred)), 4),
            "best_match_acc": round(float(acc), 4),
            "n": len(gold)}


def run(keys: list[str]):
    backend = get_backend()
    if backend is None or backend.name.startswith("hash"):
        print("ERROR: real embedder (bge-small) unavailable; refusing to validate on hash vectors.")
        return 1
    print(f"embedder: {backend.name}\n")

    results = {}
    agg_a, agg_a_soft, agg_b_ari, agg_b_acc = [], [], [], []
    pool_margin, pool_soft = [], []
    print(f"{'corpus':<12}{'K':>3}{'n':>5}{'A:hard':>8}{'A:soft':>8}{'margin':>8}"
          f"{'B:ARI':>8}{'B:NMI':>8}{'B:acc':>8}{'multi':>7}")
    print("-" * 79)
    for key in keys:
        ids, texts, gold, gold_sets, rep = load_corpus(key)
        K = rep["n_generators"]
        X = np.asarray(backend.embed(texts), dtype=np.float64)
        # re-normalize (defensive; backend already unit-norms)
        X /= np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-12, None)

        a = test_a_membership(X, gold, gold_sets, K)
        b = test_b_clustering(X, gold, K)
        pool_margin.append(a.pop("margins")); pool_soft.append(a.pop("soft_correct"))
        results[key] = {"report": rep, "test_a": a, "test_b": b}
        agg_a.append(a["agreement"]); agg_a_soft.append(a["agreement_soft"])
        if "ari" in b:
            agg_b_ari.append(b["ari"]); agg_b_acc.append(b["best_match_acc"])

        bari = b.get("ari", float("nan")); bnmi = b.get("nmi", float("nan"))
        bacc = b.get("best_match_acc", float("nan"))
        print(f"{key:<12}{K:>3}{a['n']:>5}{a['agreement']:>8.3f}{a['agreement_soft']:>8.3f}"
              f"{a['mean_margin']:>8.3f}{bari:>8.3f}{bnmi:>8.3f}{bacc:>8.3f}"
              f"{rep['n_multi_membership']:>7}")

    print("-" * 79)
    print(f"{'MEAN':<12}{'':>3}{'':>5}{np.mean(agg_a):>8.3f}{np.mean(agg_a_soft):>8.3f}"
          f"{'':>8}{np.mean(agg_b_ari):>8.3f}{'':>8}{np.mean(agg_b_acc):>8.3f}")

    # ---- the mechanical operating point: place above margin tau, escalate below ----
    M = np.concatenate(pool_margin); S = np.concatenate(pool_soft).astype(bool)
    order = np.argsort(M)
    print(f"\nmechanical operating point (pooled, n={len(M)}): place atoms with margin >= tau,")
    print("escalate the rest to a cheap jury. accuracy = soft-correct among the placed.")
    print(f"  {'tau':>6}{'placed%':>9}{'mech_acc':>10}{'escalated%':>12}")
    sweep = []
    for tau in [0.0, 0.02, 0.04, 0.06, 0.08, 0.10, 0.15]:
        placed = M >= tau
        cov = float(placed.mean())
        acc = float(S[placed].mean()) if placed.any() else float("nan")
        sweep.append({"tau": tau, "placed_frac": round(cov, 4), "mech_acc": round(acc, 4),
                      "escalated_frac": round(1 - cov, 4)})
        print(f"  {tau:>6.2f}{cov*100:>8.1f}%{acc:>10.3f}{(1-cov)*100:>11.1f}%")

    out = STRUCT_DIR / "_basis_cluster_validation.json"
    out.write_text(json.dumps({
        "method": "N42 basis-projection clusterer validation",
        "ground_truth": "Sonnet upfold program (papers->generators) per <key>.json",
        "embedder": backend.name,
        "test_a": "leave-one-out nearest-Sonnet-centroid (membership = largest coefficient)",
        "test_b": "spectral(cosine)+kmeans vs Sonnet partition (Hungarian); ARI/NMI/acc",
        "per_corpus": results,
        "aggregate": {"test_a_mean_agreement": round(float(np.mean(agg_a)), 4),
                      "test_a_mean_agreement_soft": round(float(np.mean(agg_a_soft)), 4),
                      "test_b_mean_ari": round(float(np.mean(agg_b_ari)), 4),
                      "test_b_mean_acc": round(float(np.mean(agg_b_acc)), 4)},
        "operating_point": sweep,
    }, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    # Local is a full compute home (his ruling 2026-08-20, PV-20260820T090500Z-psu-restrictions-scrubbed:
    # "we're on a new machine so please also scrub all PSU restrictions now. Local can do everything") -
    # the 2026-06-14 PSU-era disable-by-default (spectral clustering) is retired. LAPLACE_NO_SPECTRAL
    # remains as a trivial explicit opt-out for anyone who wants the Haiku upfold instead.
    import os
    if os.environ.get("LAPLACE_NO_SPECTRAL"):
        print("basis_cluster: LAPLACE_NO_SPECTRAL is set - skipping (spectral clustering). "
              "Use the Haiku upfold instead, or unset it to run here.")
        raise SystemExit(0)
    keys = sys.argv[1:] or BANKED
    raise SystemExit(run(keys))
