"""Packet D, FRAMES (CPU, zero model calls): does query-time diffusion over a graph of pieces put every linked gold
page (and the answer-bearing passage) into the 4,000 / 8,000-token context more often than the seed alone, on the
190 consumed FRAMES W3 questions, fit half and check half (G's split: within each stratum label, qids sorted,
alternate).

World, arms, delivery and scoring are packet G's (stage3/G/scripts/g6_frames.py, imported): the banked 149,447 leaves
(and G's context-keyed leaf vectors when present), the lock-matched question vectors, s = cos + w * BM25 / max BM25,
'rag' (MMR 0.7 over a 200 pool) and 'ours' (F-C: dense head 50, then one witness per active (page, section, entity)
branch, then the rest), frag (one object per piece) and merge (one block per section, G's best FRAMES delivery),
and the scoring (all gold pages present; the answer covered on the 72 questions whose answer occurs in a gold page).

Edge families (zero model calls):
  relational  adj (consecutive leaves of a section), sec (same section), page (same page), ent (same registered entity
              on the card's e_subj / e_obj routes, frames_routes_v2.json; entity codes < 82,431, the rest are
              <rare>/quantity/<unknown>), link (leaf mentions another fetched page's title: the hyperlink the explaintext
              fetch dropped, recovered by a case-checked title n-gram match; W = B_page diag(1/|page|) B_link^T + T)
  language    knn (16-NN cosine over the leaf vectors, Eq. H1 weights). FRAMES has no September cards or tree.
Seeds: 'dense' = the top-50 of the arm's score; 'title' = half that, half on the top-5 leaves (by score) of every page
whose title the question itself states (the same title finder; what the question names, found by rule).

    heavy.sh scripts/laplace-python .../D/scripts/d_frames.py sweep OUT.json
    heavy.sh scripts/laplace-python .../D/scripts/d_frames.py write CONFIG.json OUT.json
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy import sparse

LAPLACE = Path("/home/phujck/VScodeProjects/laplace")
RF = LAPLACE / "synthetics papers" / "relational-frontend"
G_DIR = LAPLACE / "evidence/BENCH_RECOVERY_2026-11-09/stage3/G"
HERE = Path(__file__).resolve().parent
SCR = HERE.parent / "scratch"
sys.path.insert(0, str(G_DIR / "scripts"))
sys.path.insert(0, str(HERE))
import g_common as G  # noqa: E402
import g6_frames as FR  # noqa: E402
import d_lib as L  # noqa: E402

N_ENT = 82431
REL = ["adj", "sec", "page", "ent", "link"]
SETS = {**{f: [f] for f in REL + ["knn"]}, "rel": REL, "both": REL + ["knn"], "self": ["self"]}
BETAS = (0.05, 0.15, 0.4)
_TOK = re.compile(r"[A-Za-z0-9]+(?:[&\-'][A-Za-z0-9]+)*")


def kinds():
    k = {"leaf_w02": ("leaf", "plain", 0.2), "leaf_w0": ("leaf", "plain", 0.0)}
    if (G_DIR / "vectors/frames_leaf_ctx.f16.npy").exists():
        k["leafctx_w02"] = ("leaf", "ctx", 0.2)
    return k


# ---------------------------------------------------------------------------------------------- title finder
def title_dict(world):
    pages = {}
    for k in world.sec_keys:
        s = world.sections[k]
        pages.setdefault(s["page"], s["page_title"])
    keys, pid = {}, {}
    for j, (p, t) in enumerate(sorted(pages.items())):
        pid[p] = j
        base = re.sub(r"\s*\([^)]*\)\s*$", "", t).strip()
        toks = tuple(x.casefold() for x in _TOK.findall(base))
        if not toks or len("".join(toks)) < 4:
            continue
        keys.setdefault(toks, set()).add(j)
    return keys, pid


def find_titles(text, keys, maxn):
    toks = [(m.group(0), m.group(0).casefold()) for m in _TOK.finditer(text)]
    out = set()
    i = 0
    while i < len(toks):
        if not (toks[i][0][0].isupper() or toks[i][0][0].isdigit()):
            i += 1
            continue
        hit = 0
        for n in range(min(maxn, len(toks) - i), 0, -1):
            key = tuple(t[1] for t in toks[i:i + n])
            if key in keys and (toks[i + n - 1][0][0].isupper() or toks[i + n - 1][0][0].isdigit()):
                out |= keys[key]
                hit = n
                break
        i += max(hit, 1)
    return out


# ---------------------------------------------------------------------------------------------- graph
def build_families(world, kind, key, want):
    SCR.mkdir(exist_ok=True)   # judge round 1, defect 1: every caller (sweep, write, final, link) caches here
    U = world.units["leaf"]
    n = len(U)
    si = U[:, 0].astype(np.int64)
    ordn = U[:, 3].astype(np.int64)
    keys, pid = title_dict(world)
    page_of_unit = np.asarray([pid[world.page_of_si[s]] for s in si], np.int64)
    npages = len(pid)
    fams, rec = {}, {}
    t0 = time.perf_counter()
    B_page = L.incidence([[p] for p in page_of_unit], n, npages)
    if "adj" in want:
        fams["adj"] = L.Family("adj", "direct", n, W=L.adjacency(si, ordn))
    if "sec" in want:
        B = L.incidence([[s] for s in si], n, len(world.texts))
        fams["sec"] = L.Family("sec", "bip", n, B=B, w=L.inv_freq(B))
    if "page" in want:
        fams["page"] = L.Family("page", "bip", n, B=B_page, w=L.inv_freq(B_page))
    if "ent" in want:
        cache = SCR / "frames_ent_groups.npz"
        if cache.exists():
            z = np.load(cache)
            rows, cols = z["rows"], z["cols"]
        else:
            doc = json.loads((RF / "derived/index/frames_routes_v2.json").read_text())
            assert doc["cards"] == n and doc["columns"][0] == "card"
            ci = doc["columns"].index("e_subj")
            co = doc["columns"].index("e_obj")
            assert doc["unit_ids"] == list(world.leaf_ids)
            pairs = set()
            for r in doc["routes"]:
                for c in (r[ci], r[co]):
                    if c < N_ENT:
                        pairs.add((r[0], c))
            del doc
            arr = np.asarray(sorted(pairs), np.int64).reshape(-1, 2)
            rows, cols = arr[:, 0], arr[:, 1]
            np.savez(cache, rows=rows, cols=cols)
        B = sparse.csr_matrix((np.ones(len(rows), np.float32), (rows, cols)), shape=(n, N_ENT))
        fams["ent"] = L.Family("ent", "bip", n, B=B, w=L.inv_freq(B))
        rec["ent"] = {"pieces_with_entity": int((np.diff(B.indptr) > 0).sum()), "pairs": int(B.nnz)}
    if "link" in want:
        cache = SCR / "frames_link_groups.npz"
        if cache.exists():
            z = np.load(cache)
            rows, cols = z["rows"], z["cols"]
        else:
            maxn = min(8, max(len(k) for k in keys))
            rr, cc = [], []
            for i in range(n):
                s, a, b = int(U[i, 0]), int(U[i, 1]), int(U[i, 2])
                for p in find_titles(world.texts[s][a:b], keys, maxn):
                    if p != page_of_unit[i]:
                        rr.append(i)
                        cc.append(p)
            rows, cols = np.asarray(rr, np.int64), np.asarray(cc, np.int64)
            np.savez(cache, rows=rows, cols=cols)
        B_link = sparse.csr_matrix((np.ones(len(rows), np.float32), (rows, cols)), shape=(n, npages))
        B_link.data[:] = 1
        fams["link"] = L.Family("link", "pair", n, B=B_page, B2=B_link, w=L.inv_freq(B_page))
        rec["link"] = {"pieces_mentioning_another_page": int((np.diff(B_link.tocsr().indptr) > 0).sum()),
                       "mentions": int(B_link.nnz), "pages_mentioned": int((np.asarray(B_link.sum(0)).ravel() > 0).sum()),
                       "title_keys": len(keys)}
    if "self" in want:   # control: S = I, so h = the seed itself (no graph); separates the MMR re-weighting
        fams["self"] = L.Family("self", "direct", n, W=sparse.identity(n, format="csr", dtype=np.float32), lazy=False)
    if "knn" in want:
        cache = SCR / f"frames_knn_{key}.npz"
        if cache.exists():
            W = sparse.load_npz(cache)
        else:
            W = L.knn_graph(world.V("leaf", key), 16, block=1024)
            sparse.save_npz(cache, W)
        fams["knn"] = L.Family("knn", "direct", n, W=W)
    rec["families"] = {k: f.receipt() for k, f in fams.items()}
    rec["build_seconds"] = round(time.perf_counter() - t0, 1)
    return fams, rec, (keys, pid, page_of_unit)


# ---------------------------------------------------------------------------------------------- arm
class Arm:
    def __init__(self, world, key, w, tinfo):
        self.world, self.key, self.w = world, key, w
        self.V = world.V("leaf", key)
        n = self.V.shape[0]
        self.base = np.empty((n, len(world.qids)), np.float32)
        for qi in range(len(world.qids)):
            self.base[:, qi] = world.score(qi, "leaf", key, w)
        self.seed = {"dense": np.stack([L.seed_from_scores(self.base[:, j]) for j in range(self.base.shape[1])], 1)}
        keys, pid, page_of_unit = tinfo
        maxn = min(8, max(len(k) for k in keys))
        units_of_page = defaultdict(list)
        for i, p in enumerate(page_of_unit):
            units_of_page[int(p)].append(i)
        ts, self.q_titles = [], {}
        for qi, qid in enumerate(world.qids):
            named = find_titles(world.question[qid], keys, maxn)
            self.q_titles[qid] = len(named)
            col = 0.5 * self.seed["dense"][:, qi] if named else self.seed["dense"][:, qi].copy()
            if named:
                per = 0.5 / len(named)
                for p in named:
                    us = np.asarray(units_of_page[p])
                    top = us[np.argsort(-self.base[us, qi])[:5]]
                    col[top] += per / len(top)
            ts.append(col)
        self.seed["title"] = np.stack(ts, 1).astype(np.float32)
        self.cost = {}

    def units(self, which, r, qi):
        """G's rag / ours orderings with the diffused rank r in place of the score."""
        W = self.world
        if which == "rag":
            pool = 200
            order = np.argpartition(-r, pool)[:pool]
            order = order[np.argsort(-r[order], kind="stable")]
            return [W.unit_obj("leaf", i) for i in G.mmr(order, r[order], self.V, 200)]
        top = np.argpartition(-r, 3000)[:3000]
        top = top[np.argsort(-r[top], kind="stable")]
        out = [int(i) for i in top[:50]]
        head = set(out)
        act = W.active.get(qi, {})
        if act:
            branch_units = defaultdict(set)
            for c, b in act.items():
                branch_units[b].add(c)
            wit = []
            for b, us in branch_units.items():
                us = list(us)
                best = us[int(np.argmax(r[us]))]
                wit.append((float(r[best]), best))
            for sc, u in sorted(wit, key=lambda t: (-t[0], t[1])):
                if u not in head:
                    head.add(u)
                    out.append(u)
        out += [int(i) for i in top if int(i) not in head][:400]
        return [W.unit_obj("leaf", i) for i in out]

    def frag(self, units, budget):
        packed, chosen = [], []
        used = 2
        for u in units:
            t = self.cost.get(u["id"])
            if t is None:
                t = G.ntok(G.canonical({k: u[k] for k in ("id", "text", "sources", "dates")})) + 1
                self.cost[u["id"]] = t
            if used + t <= budget:
                packed.append({k: u[k] for k in ("id", "text", "sources", "dates")})
                chosen.append(u)
                used += t
        while packed and G.ctx_tokens(packed) > budget:
            packed.pop()
            chosen.pop()
        return packed, G.spans_of_fragments(chosen)

    def merge(self, units, budget):
        for u in units[:600]:
            self.world.view(u["doc"])
        return G.delivered_pack(units, self.world.views, budget, None, extend=False, max_tries=600)


def evaluate(world, arm, which, R, delivery, budget):
    per_q, toks, packs = {}, {}, {}
    for qi, qid in enumerate(world.qids):
        units = arm.units(which, R[:, qi], qi)
        packed, spans = (arm.frag if delivery == "frag" else arm.merge)(units, budget)
        per_q[qid] = world.score_ctx(qid, packed, spans) if world.gold is not None else None
        toks[qid] = G.ctx_tokens(packed)
        packs[qid] = (packed, units, spans)
    return per_q, toks, packs


def summary_of(world, per_q, toks):
    s = FR.summarise(world, per_q, toks)
    multi = [q for q in world.qids if per_q[q]["gold_pages"] >= 2]
    s["multi_page"] = {"q": len(multi), "all_gold": sum(per_q[q]["all_gold"] for q in multi),
                       "gold_present": sum(per_q[q]["gold_present"] for q in multi),
                       "gold_pages": sum(per_q[q]["gold_pages"] for q in multi)}
    return s


def ranks(arm, acc_op, beta):
    if acc_op is None:
        return arm.base
    out = np.empty_like(arm.base)
    for j in range(arm.base.shape[1]):
        out[:, j] = L.combine(arm.base[:, j], acc_op[:, j], beta)
    return out


# ---------------------------------------------------------------------------------------------- sweep
def sweep(out_path: str):
    t0 = time.perf_counter()
    SCR.mkdir(exist_ok=True)
    world = FR.Frames()
    world.load_gold()
    ops = L.standard_ops()
    K = kinds()
    results = {"meta": {"kinds": K, "sets": SETS, "betas": BETAS, "ops": list(ops),
                        "split": "G: within FRAMES stratum label, qids sorted, alternate (half 0 = fit)"},
               "graphs": {}, "configs": []}

    def log(msg):
        print(f"[{time.perf_counter() - t0:7.0f}s] {msg}", flush=True)

    def record(cfg, per_q, toks):
        s = summary_of(world, per_q, toks)
        results["configs"].append({"config": cfg, "summary": s,
                                   "per_q": {q: [v["answer_covered"], v["all_gold"], v["gold_present"]]
                                             for q, v in per_q.items()}})
        log(f"{json.dumps(cfg)} | allgold {s['all']['all_gold']} fit {s['fit']['all_gold']} check "
            f"{s['check']['all_gold']} | ans {s['all']['answer_covered']} fit {s['fit']['answer_covered']} check "
            f"{s['check']['answer_covered']} | multi {s['multi_page']['all_gold']}/{s['multi_page']['q']} "
            f"| present {s['all']['gold_present']}")
        if len(results["configs"]) % 25 == 0:
            Path(out_path).write_text(json.dumps(results, sort_keys=True) + "\n")
        return s

    fams, rec, tinfo = build_families(world, None, "plain", set(REL) | {"self"})
    results["graphs"]["relational"] = rec
    log(f"relational graph {json.dumps(rec)}")
    knn = {}
    for kname, (kind, key, w) in K.items():
        if key not in knn:
            f2, r2, _ = build_families(world, None, key, {"knn"})
            knn[key] = f2["knn"]
            results["graphs"][f"knn_{key}"] = r2
            log(f"knn {key} {json.dumps(r2)}")
        allf = {**fams, "knn": knn[key]}
        arm = Arm(world, key, w, tinfo)
        log(f"{kname}: questions naming a fetched page title: "
            f"{sum(1 for v in arm.q_titles.values() if v)} / {len(arm.q_titles)}")
        frag_scores = {}
        for which in ("rag", "ours"):
            for budget in (8000, 4000):
                per_q, toks, _ = evaluate(world, arm, which, arm.base, "frag", budget)
                s = record({"kind": kname, "arm": which, "seed": "-", "set": "none", "op": None, "beta": 0,
                            "delivery": "frag", "budget": budget}, per_q, toks)
                frag_scores[(which, "-", "none", None, 0, budget)] = s
        seeds = ("dense", "title") if kname == "leaf_w02" else ("dense",)
        sets = SETS if kname == "leaf_w02" else {k: SETS[k] for k in ("link", "rel", "knn", "both", "self")}
        for seed in seeds:
            for sname, members in sets.items():
                if seed == "title" and sname not in ("link", "rel", "both", "page"):
                    continue
                acc = L.diffuse([allf[m] for m in members], arm.seed[seed], ops)
                for which in ("rag", "ours"):
                    for op in ops:
                        for beta in BETAS:
                            per_q, toks, _ = evaluate(world, arm, which, ranks(arm, acc[op], beta), "frag", 8000)
                            s = record({"kind": kname, "arm": which, "seed": seed, "set": sname, "op": op,
                                        "beta": beta, "delivery": "frag", "budget": 8000}, per_q, toks)
                            frag_scores[(which, seed, sname, op, beta, 8000)] = s
                del acc
        # merge delivery at 8,000 and 4,000: seed-only, and the best (op, beta) per (arm, seed, set) by FIT all-gold
        for which in ("rag", "ours"):
            for budget in (8000, 4000):
                per_q, toks, _ = evaluate(world, arm, which, arm.base, "merge", budget)
                record({"kind": kname, "arm": which, "seed": "-", "set": "none", "op": None, "beta": 0,
                        "delivery": "merge", "budget": budget}, per_q, toks)
        groups = sorted({(k[0], k[1], k[2]) for k in frag_scores if k[2] != "none"})
        for which, seed, sname in groups:
            cand = sorted(((v["fit"]["all_gold"], v["fit"]["answer_covered"], -k[4], k)
                           for k, v in frag_scores.items() if k[:3] == (which, seed, sname)), reverse=True)[0]
            k = cand[3]
            acc = L.diffuse([allf[m] for m in SETS[sname]], arm.seed[seed], {k[3]: ops[k[3]]})
            budgets = (8000, 4000) if (kname == "leaf_w02" and sname in ("rel", "both", "link", "knn")) else (8000,)
            for budget in budgets:
                per_q, toks, _ = evaluate(world, arm, which, ranks(arm, acc[k[3]], k[4]), "merge", budget)
                record({"kind": kname, "arm": which, "seed": seed, "set": sname, "op": k[3], "beta": k[4],
                        "delivery": "merge", "budget": budget}, per_q, toks)
            del acc
        del arm
    results["meta"]["seconds"] = round(time.perf_counter() - t0, 1)
    Path(out_path).write_text(json.dumps(results, sort_keys=True) + "\n")
    log("done")


# ---------------------------------------------------------------------------------------------- contexts
def write(config_path: str, out_path: str):
    """Reader contexts (stage3/R/CONTEXT_FORMAT.md) for every arm in CONFIG on all 190 questions; reserve = the next
    pieces of the same ranked list not delivered (>= 12,000 tokens). No gold is read."""
    cfgs = json.loads(Path(config_path).read_text())
    world = FR.Frames()
    ops = L.standard_ops()
    K = kinds()
    rows, arms_meta = [], {}
    fams, _, tinfo = build_families(world, None, "plain", set(REL) | {"self"})
    for name, c in cfgs.items():
        kind, key, w = K[c["kind"]]
        arm = Arm(world, key, w, tinfo)
        if c["set"] == "none":
            R = arm.base
        else:
            allf = dict(fams)
            if "knn" in SETS[c["set"]]:
                allf["knn"] = build_families(world, None, key, {"knn"})[0]["knn"]
            acc = L.diffuse([allf[m] for m in SETS[c["set"]]], arm.seed[c["seed"]], {c["op"]: ops[c["op"]]})
            R = ranks(arm, acc[c["op"]], c["beta"])
        _, _, packs = evaluate(world, arm, c["arm"], R, c["delivery"], c["budget"])
        arms_meta[name] = {"selection": "packet D query-time diffusion: " + json.dumps(c, sort_keys=True),
                           "growth_mode": "slots" if c["arm"] == "ours" else "ranker", "header": False}
        for qi, qid in enumerate(world.qids):
            packed, units = packs[qid][:2]
            ps = []
            for p in packed:
                # exactly the packed object; R reads page (sources), section and piece from the id form
                ps.append({k: p[k] for k in ("id", "text", "sources", "dates")})
            ids = {p["id"] for p in ps}
            reserve, rt = [], 0
            for u in units:
                if u["id"] in ids or rt >= 12000:
                    continue
                sk = ":".join(u["id"].split(":")[:3])
                s = world.sections[sk]
                q = {k: u[k] for k in ("id", "text", "sources", "dates")}
                q.update({"doc_id": s["page"][:16], "section": int(sk.split(":s")[-1]),
                          "piece": int(u["id"].split(":p")[-1]), "title": s["page_title"]})
                reserve.append(q)
                rt += G.ntok(G.canonical({k: u[k] for k in ("id", "text", "sources", "dates")})) + 1
            rows.append({"qid": qid, "arm": name, "question": world.question[qid], "question_date": None,
                         "stratum": world.stratum[qid], "passages": ps, "context_tokens": G.ctx_tokens(ps),
                         "context_sha256": hashlib.sha256(G.canonical(ps).encode()).hexdigest(),
                         "reserve": reserve, "reserve_rule": "next pieces of the same diffused ranking not delivered",
                         "work": {"config": c, "blocks": len(ps)}})
    me = Path(__file__).resolve()
    cut = "packet-D-" + "-".join(sorted({f"{c['kind']}-{c['delivery']}" for c in cfgs.values()}))
    out = {"schema": "bench-recovery.stage3.reader-contexts/1", "dataset": "frames", "material": "w3-consumed",
           "label": "DEV-ONLY", "producer": {"packet": "D", "script": str(me),
                                            "script_sha256": hashlib.sha256(me.read_bytes()).hexdigest(),
                                            "config": cfgs},
           "tokenizer": "cl100k_base", "cut": cut, "pass1_budget_tokens": max(c["budget"] for c in cfgs.values()),
           "arms": arms_meta, "rows": rows}
    Path(out_path).write_text(json.dumps(out, ensure_ascii=False, sort_keys=True) + "\n")
    sys.path.insert(0, str(RF / "src"))
    from relational import witness_context as WC
    doc = WC.load_context_file(out_path)
    print(json.dumps({"rows": len(doc["rows"]), "arms": list(arms_meta), "cut": cut,
                      "median_tokens": float(np.median([r["context_tokens"] for r in rows]))}))


if __name__ == "__main__":
    if sys.argv[1] == "sweep":
        sweep(sys.argv[2])
    elif sys.argv[1] == "write":
        write(sys.argv[2], sys.argv[3])
