"""Numerical experiments ON the corpus, for the EigenEngine core paper - applying the engine's own
no-naked-claims / numerical-evidence standard to the engine itself (his, 2026-06-13).

Read-only over the committed fold. Writes a JSON report to paper_eigen/_experiments/ and prints a
summary. Three experiments + one census, all MECHANICAL (zero model inference):

  E1  grade histogram of the whole conceptric  -> the log-compression (geometric decay of the base)
  E2  per-corpus apex(themes) vs base(papers)   -> how apex size scales with corpus size (across folds)
  E3  per-centre cross-link cost + citation-free -> the cost is constant; the citation-free fraction
                                                    is a distribution over 8 independent centres (n>1)
  C   cross-lens identity census                -> persons / portraits / lenses fused at zero model cost

Reuses scripts/author_theme_crosslink.py's functions verbatim, so E3's numbers are computed by the
SAME mechanical metric the proof script uses. Run: python scripts/corpus_experiments.py
"""
from __future__ import annotations

import glob
import json
import math
import os
import statistics
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import author_theme_crosslink as X  # noqa: E402  - reuse the exact proof-script metric


def e1_grade_histogram() -> dict:
    """The fold decays geometrically. Reported over ONE substrate two ways:

      corpus_ladder  - FROZEN + reproducible: the demonstration corpus (the 8 *_regraded.json author
                       folds, the same substrate E2/E3 use). paper -> cluster -> theme, three levels.
      store_histogram - the engine's full working store (live; includes engine-self and cross-lens
                       overlay nodes, NOT just the corpus). Corroborates the SAME branching b at a
                       larger scale and deeper ladder; reported as such, never conflated with the corpus.
    """
    # --- the demonstration corpus ladder (frozen JSON; the paper's quantitative spine) -------------
    apex = mid = base = 0
    uniq: set[str] = set()
    for f in _corpora():
        d = json.load(open(f, encoding="utf-8"))
        gens = d.get("generators", [])
        apex += len(gens)
        for g in gens:
            rungs = g.get("rungs", [])
            mid += len(rungs)
            for r in rungs:
                if isinstance(r, dict):
                    ps = r.get("papers") or r.get("members") or []
                    base += len(ps)
                    uniq.update(str(p) for p in ps)
    ladder = [base, mid, apex]
    cratios = [ladder[i] / ladder[i + 1] for i in range(len(ladder) - 1) if ladder[i + 1]]
    cb = statistics.geometric_mean(cratios) if cratios else float("nan")
    corpus_ladder = {
        "base_papers": base,
        "mid_clusters": mid,
        "apex_themes": apex,
        "unique_papers": len(uniq),
        "ladder": ladder,
        "ladder_labels": ["papers", "clusters", "themes"],
        "branching_ratios": [round(r, 2) for r in cratios],
        "branching_b": round(cb, 2),
        "implied_depth_log_b_base": round(math.log(base, cb), 2) if cb and cb > 1 else None,
        "note": "the 8 author corpora folded paper->cluster->theme; frozen (reads only committed JSON), "
                "the same substrate as E2/E3. Branching b is the geometric mean of the level ratios.",
    }

    # --- the full engine store (live; corroborates the same b at a deeper ladder) ------------------
    from pathlib import Path
    from laplace.engine import conceptric as C
    net = C.load_network(Path(ROOT))
    nodes = net["nodes"] if isinstance(net, dict) and "nodes" in net else getattr(net, "nodes", {})
    hist = Counter(v.get("grade", 0) for v in nodes.values())
    grades = sorted(hist)
    counts = {int(g): int(hist[g]) for g in grades}
    base_levels = [counts[grades[0]]]
    for g in grades[1:]:
        if counts[g] < base_levels[-1]:
            base_levels.append(counts[g])
        else:
            break
    ratios = [base_levels[i] / base_levels[i + 1] for i in range(len(base_levels) - 1) if base_levels[i + 1]]
    b = statistics.geometric_mean(ratios) if ratios else float("nan")
    total = sum(counts.values())
    store_histogram = {
        "counts_by_grade": counts,
        "total_nodes": total,
        "n_grades": len(grades),
        "base_ladder": base_levels,
        "base_branching_ratios": [round(r, 2) for r in ratios],
        "branching_b": round(b, 2),
        "implied_depth_log_b_N": round(math.log(total, b), 2) if b and b > 1 else None,
        "note": "the engine's full working store, NOT the demonstration corpus: it also holds the engine's "
                "own self-record and the cross-lens overlay apexes (person://, technique://, lens nodes). "
                "Live, so the exact counts grow with the store; reported as corroboration that the same "
                "geometric branching b holds at a larger scale and across a deeper ladder.",
    }
    return {"corpus_ladder": corpus_ladder, "store_histogram": store_histogram}


def _corpora() -> list[str]:
    fs = sorted(glob.glob(os.path.join(ROOT, "collaborator_corpus/_structural/*_regraded.json")))
    return [f for f in fs if os.path.basename(f) != "eigen_operations_regraded.json"]


def e2_apex_vs_base() -> dict:
    rows = []
    for f in _corpora():
        d = json.load(open(f, encoding="utf-8"))
        author = os.path.basename(f).replace("_regraded.json", "")
        gens = d.get("generators", [])
        apex = len(gens)  # themes = the corpus's condensed top
        base = 0          # paper-instances at the floor
        for g in gens:
            for r in g.get("rungs", []):
                if isinstance(r, dict):
                    base += len(r.get("papers") or r.get("members") or [])
        rows.append({"author": author, "name": d.get("name", author), "base_papers": base, "apex_themes": apex})
    rows = [r for r in rows if r["base_papers"] > 0]
    # fit: is apex ~ a*ln(base)+c (log) or apex ~ base^alpha (power)? report both with R^2.
    xs_ln = [math.log(r["base_papers"]) for r in rows]
    ys = [r["apex_themes"] for r in rows]
    fits = {}
    if len(rows) >= 3:
        fits["log"] = _linfit(xs_ln, ys)                                   # apex = a*ln(base)+c
        fits["power"] = _linfit([math.log(r["base_papers"]) for r in rows],
                                [math.log(y) for y in ys])                 # ln(apex)=alpha*ln(base)+c
    return {"rows": sorted(rows, key=lambda r: r["base_papers"]), "fits": fits}


def _linfit(xs: list[float], ys: list[float]) -> dict:
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    slope = sxy / sxx if sxx else 0.0
    inter = my - slope * mx
    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum((ys[i] - (slope * xs[i] + inter)) ** 2 for i in range(n))
    r2 = 1 - ss_res / ss_tot if ss_tot else 0.0
    return {"slope": round(slope, 3), "intercept": round(inter, 3), "r2": round(r2, 3)}


def e3_per_centre() -> dict:
    themes_by_author = X._load_themes()
    idf = X._idf(themes_by_author)
    # global cost constants (independent of which author is centred)
    apex = sum(len(v) for v in themes_by_author.values())
    base = 0
    for f in _corpora():
        d = json.load(open(f, encoding="utf-8"))
        for g in d.get("generators", []):
            for r in g.get("rungs", []):
                if isinstance(r, dict):
                    base += len(r.get("papers") or r.get("members") or [])
    rows = []
    for author, cts in themes_by_author.items():
        others = [(a, t) for a, ts in themes_by_author.items() if a != author for t in ts]
        links = cfree = 0
        for ct in cts:
            cv = X._vec(ct["tokens"], idf)
            ranked = sorted(((X._cos(cv, X._vec(t["tokens"], idf)), a, t) for a, t in others),
                            key=lambda x: -x[0])[:3]
            for score, a, t in ranked:
                if score < 0.02:
                    continue
                links += 1
                cfree += (len(ct["papers"] & t["papers"]) == 0)
        rows.append({"centre": author, "themes": len(cts), "links": links,
                     "citation_free": cfree,
                     "citation_free_frac": round(cfree / links, 3) if links else 0.0})
    fracs = [r["citation_free_frac"] for r in rows if r["links"]]
    return {
        "model_inferences_per_query": 0,
        "apex_theme_nodes": apex,
        "base_paper_instances": base,
        "apex_over_total_ratio": round(apex / (apex + base), 3),
        "n_centres": len(rows),
        "rows": sorted(rows, key=lambda r: -r["citation_free_frac"]),
        "citation_free_frac_mean": round(statistics.mean(fracs), 3) if fracs else None,
        "citation_free_frac_min": round(min(fracs), 3) if fracs else None,
        "citation_free_frac_max": round(max(fracs), 3) if fracs else None,
    }


def c_identity_census() -> dict:
    from pathlib import Path
    from laplace.engine import conceptric as C
    net = C.load_network(Path(ROOT))
    nodes = net["nodes"] if isinstance(net, dict) and "nodes" in net else getattr(net, "nodes", {})
    persons = []
    for k, v in nodes.items():
        if str(k).startswith("person://"):
            members = v.get("members") or v.get("children") or []
            lenses = set()
            for m in members:
                if m in nodes:
                    lenses.update(nodes[m].get("lenses") or [])
            persons.append({"id": k, "portraits": len(members), "lenses": sorted(lenses)})
    persons.sort(key=lambda p: -p["portraits"])
    return {"n_persons": len(persons), "model_inferences": 0, "persons": persons[:12]}


def main() -> int:
    report = {
        "e1_grade_histogram": e1_grade_histogram(),
        "e2_apex_vs_base": e2_apex_vs_base(),
        "e3_per_centre_crosslink": e3_per_centre(),
        "c_identity_census": c_identity_census(),
    }
    out_dir = os.path.join(ROOT, "paper_eigen", "_experiments")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "corpus_experiments.json")
    json.dump(report, open(out, "w", encoding="utf-8"), indent=2)

    e1, e2, e3, c = report["e1_grade_histogram"], report["e2_apex_vs_base"], report["e3_per_centre_crosslink"], report["c_identity_census"]
    cl, sh = e1["corpus_ladder"], e1["store_histogram"]
    print(f"E1  corpus fold (frozen): papers={cl['base_papers']} -> clusters={cl['mid_clusters']} -> "
          f"themes={cl['apex_themes']}  ratios={cl['branching_ratios']}  b={cl['branching_b']}")
    print(f"    full store (live, corroboration): {sh['counts_by_grade']}")
    print(f"    store base ladder {sh['base_ladder']}  b={sh['branching_b']}  depth~log_b(N)={sh['implied_depth_log_b_N']}")
    print(f"E2  apex-vs-base across {len(e2['rows'])} corpora; fits={e2['fits']}")
    for r in e2["rows"]:
        print(f"    {r['name'][:24]:<24} base={r['base_papers']:>4}  apex={r['apex_themes']:>3}")
    print(f"E3  cost: {e3['model_inferences_per_query']} inferences, apex={e3['apex_theme_nodes']}, base={e3['base_paper_instances']}, ratio={e3['apex_over_total_ratio']}")
    print(f"    citation-free frac over {e3['n_centres']} centres: mean={e3['citation_free_frac_mean']} [{e3['citation_free_frac_min']}, {e3['citation_free_frac_max']}]")
    for r in e3["rows"]:
        print(f"    {r['centre']:<12} links={r['links']:>2}  citation-free={r['citation_free']:>2}  frac={r['citation_free_frac']}")
    print(f"C   identity census: {c['n_persons']} persons fused at {c['model_inferences']} model inferences")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
