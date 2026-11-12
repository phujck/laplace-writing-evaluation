"""Packet J, FRAMES world (CPU, zero model calls): the method's multi-hop stages as general rules, measured as
linked-gold-page delivery and answer-passage delivery on the fit and check halves before any reader call, and the
reader contexts they write. Pass-2 contexts (the reader's stated needs fetched) are built here too.

World, pieces, scores, delivery and gold scoring are packets G and D, imported (G/scripts/g6_frames.py,
D/scripts/d_frames.py, D/scripts/d_frames_link.py); D's scratch caches are redirected to J/scratch.

Shared non-method settings (every arm): the banked 149,447 leaves, the lock-matched question vectors,
s = cos + 0.2 * BM25 / max BM25, merged-section delivery (G.delivered_pack, extend False), the budget.

Ours, stages (each a general rule; names used in the results):
  head H          the top H pieces by s (stage 6 seed; H = 50 at 8k, 25 at 4k so the head fits the budget)
  link:mass       D's link witness: weight one hop from the top-20 pieces along recovered title links, summed per
                  target page, top-5 pages, best piece each
  link:rel        the same candidate pages (linked from the head), ranked by the target page's own best piece score
                  for the question (follow the link, then ask whether the page answers anything), top-M
  req             stage 5+7: the question compiled into its chain of requirements (R's compile_frames); each
                  requirement ranks pieces by s + lam * s_req (s_req = cos(need) + 0.2 BM25(need)); witnesses taken
                  round-robin, top P per requirement, so every link of the chain has its section
  act             the F-C activation witnesses (one per active page/section/entity branch)
  rest            the remaining pieces by s
RAG: MMR 0.7 over a 200 pool on s + 0.4 * seed / max seed (D's frozen RAG setting, rag_self0.4).

    heavy.sh scripts/laplace-python .../J/scripts/j_world.py measure OUT.json
    heavy.sh scripts/laplace-python .../J/scripts/j_world.py write SPEC.json OUT_CTX.json
    heavy.sh scripts/laplace-python .../J/scripts/j_world.py pass2 CTX.json READ.json VARIANT OUT_CTX.json
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

J = Path("/home/phujck/VScodeProjects/laplace/evidence/BENCH_RECOVERY_2026-11-09/stage3/J")
D_SCRIPTS = J.parent / "D/scripts"
sys.path.insert(0, str(D_SCRIPTS))
import d_frames as DF  # noqa: E402
import d_frames_link as DL  # noqa: E402

DF.SCR = J / "scratch"          # D's caches go to J's own folder
G = DF.G
RFSRC = DF.RF / "src"
sys.path.insert(0, str(RFSRC))


class World:
    def __init__(self, with_gold=True):
        t0 = time.perf_counter()
        self.w = DF.FR.Frames()
        if with_gold:
            self.w.load_gold()
        fams, rec, tinfo = DF.build_families(self.w, None, "plain", {"link"})
        self.keys, self.pid, self.page_of_unit = tinfo
        self.B_link = fams["link"].B2.tocsr()
        pu = defaultdict(list)
        for i, p in enumerate(self.page_of_unit):
            pu[int(p)].append(i)
        self.page_units = {p: np.asarray(v) for p, v in pu.items()}
        self.arm = DF.Arm(self.w, "plain", 0.2, tinfo)
        self.R_rag = DF.ranks(self.arm, self.arm.seed["dense"], 0.4)
        self.V = self.w.V("leaf", "plain")
        self.bm = self.w.bm("leaf", "plain")
        self._enc = None
        self.req = {}
        print(f"world ready {time.perf_counter() - t0:.0f}s", flush=True)

    # ------------------------------------------------------------------ text scoring (question-free)
    def encoder(self):
        if self._enc is None:
            from relational import codebook as cb
            self._enc = cb.imported_encoder()
        return self._enc

    def text_scores(self, texts):
        """s(text) = cos(query vector of text) + 0.2 * BM25(text) / max, for each text (rows)."""
        if not texts:
            return np.zeros((0, self.V.shape[0]), np.float32)
        Q = np.asarray(self.encoder().embed(list(texts), role="query"), np.float32)
        Q /= np.linalg.norm(Q, axis=1, keepdims=True)
        out = np.empty((len(texts), self.V.shape[0]), np.float32)
        for k, t in enumerate(texts):
            s = self.V @ Q[k]
            b = self.bm.scores(t)
            mx = float(b.max())
            out[k] = s + (0.2 * b / mx if mx > 0 else 0.0)
        return out

    def compile_requirements(self):
        from relational import witness_compile as WCo
        need_texts, owner = [], []
        for qi, qid in enumerate(self.w.qids):
            c = WCo.compile_frames(self.w.question[qid], self.w.stratum[qid])
            needs = [o.need for o in c.obligations] if len(c.obligations) > 1 else []
            self.req[qi] = {"needs": needs}
            for n in needs:
                need_texts.append(n)
                owner.append(qi)
        S = self.text_scores(need_texts)
        for qi in self.req:
            self.req[qi]["S"] = []
        for k, qi in enumerate(owner):
            self.req[qi]["S"].append(S[k])
        print(f"requirements: {len(need_texts)} needs over {sum(1 for v in self.req.values() if v['needs'])} "
              f"multi-requirement questions", flush=True)

    # ------------------------------------------------------------------ orderings
    def ours_units(self, qi, head=50, link=None, M=5, K=20, per_page=1, req=None, lam=1.0, P=2, act=False):
        r = self.arm.base[:, qi]
        top = np.argpartition(-r, 3000)[:3000]
        top = top[np.argsort(-r[top], kind="stable")]
        out = [int(i) for i in top[:head]]
        seen = set(out)

        def add(i):
            i = int(i)
            if i not in seen:
                seen.add(i)
                out.append(i)
        if req and self.req.get(qi, {}).get("needs"):
            lists = []
            for s_o in self.req[qi]["S"]:
                rr = r + lam * s_o
                t = np.argpartition(-rr, 200)[:200]
                lists.append([int(x) for x in t[np.argsort(-rr[t], kind="stable")]])
            ptr = [0] * len(lists)
            for _ in range(P):
                for k, L in enumerate(lists):
                    while ptr[k] < len(L) and L[ptr[k]] in seen:
                        ptr[k] += 1
                    if ptr[k] < len(L):
                        add(L[ptr[k]])
        if link:
            head_pages = {int(self.page_of_unit[i]) for i in top[:head]}
            src = top[:K]
            mass = defaultdict(float)
            for i in src:
                a, b = self.B_link.indptr[i], self.B_link.indptr[i + 1]
                for p in self.B_link.indices[a:b]:
                    mass[int(p)] += float(r[i])
            if link == "mass":
                pages = [p for p, _ in sorted(mass.items(), key=lambda t: (-t[1], t[0]))][:M]
            else:   # rel: candidate pages linked from the head, ranked by their own best piece for the question
                cand = [p for p in mass if p not in head_pages]
                best = {p: float(r[self.page_units[p]].max()) for p in cand}
                pages = [p for p, _ in sorted(best.items(), key=lambda t: (-t[1], t[0]))][:M]
            for p in pages:
                us = self.page_units[p]
                for x in us[np.argsort(-r[us], kind="stable")[:per_page]]:
                    add(x)
        if act:
            a_ = self.w.active.get(qi, {})
            bu = defaultdict(set)
            for c, b in a_.items():
                bu[b].add(c)
            aw = []
            for b, us in bu.items():
                us = list(us)
                bst = us[int(np.argmax(r[us]))]
                aw.append((float(r[bst]), bst))
            for sc, u in sorted(aw, key=lambda t: (-t[0], t[1])):
                add(u)
        out += [int(i) for i in top if int(i) not in seen][:400]     # D's tail rule (d_frames_link.py:87)
        return [self.w.unit_obj("leaf", i) for i in out]

    def rag_units(self, qi):
        return self.arm.units("rag", self.R_rag[:, qi], qi)

    def units(self, qi, spec):
        if spec["arm"] == "rag":
            return self.rag_units(qi)
        return self.ours_units(qi, **{k: v for k, v in spec.items() if k not in ("arm", "budget")})

    def pack(self, units, budget):
        return self.arm.merge(units, budget)



def _score(w, qid, spans):
    g = w.gold[qid]
    pages = {w.page_of_si[si] for si in spans}
    cov = None
    if g["answer_spans"]:
        cov = any(G.covered(sp, spans.get(w.sections[sk]["si"], []))
                  for sk, sps in g["answer_spans"].items() for sp in sps)
    gp = list(g["pages"])
    return {"answer_covered": cov, "gold_pages": len(gp), "gold_present": sum(p in pages for p in gp),
            "all_gold": bool(gp) and all(p in pages for p in gp)}


def summarise(w, per_q):
    out = {}
    for name, qs in (("all", w.qids), ("fit", [q for q in w.qids if w.half[q] == 0]),
                     ("check", [q for q in w.qids if w.half[q] == 1])):
        loc = [q for q in qs if per_q[q]["answer_covered"] is not None]
        out[name] = {"all_gold": sum(per_q[q]["all_gold"] for q in qs),
                     "answer_covered": sum(per_q[q]["answer_covered"] for q in loc),
                     "gold_present": sum(per_q[q]["gold_present"] for q in qs)}
    return out


def fmt(s):
    return (f"allgold {s['all']['all_gold']} ({s['fit']['all_gold']}/{s['check']['all_gold']}) | ans "
            f"{s['all']['answer_covered']} ({s['fit']['answer_covered']}/{s['check']['answer_covered']}) | present "
            f"{s['all']['gold_present']}")


SPECS = {
    # 8,000 tokens
    "rag@8k": {"arm": "rag", "budget": 8000},
    "D_ours@8k": {"arm": "ours", "head": 50, "link": "mass", "act": True, "budget": 8000},
    "ours_noact@8k": {"arm": "ours", "head": 50, "link": "mass", "act": False, "budget": 8000},
    "seed_noact@8k": {"arm": "ours", "head": 50, "budget": 8000},
    "rel5@8k": {"arm": "ours", "head": 50, "link": "rel", "M": 5, "budget": 8000},
    "rel8@8k": {"arm": "ours", "head": 50, "link": "rel", "M": 8, "budget": 8000},
    "rel5h40@8k": {"arm": "ours", "head": 40, "link": "rel", "M": 5, "budget": 8000},
    "req@8k": {"arm": "ours", "head": 50, "req": True, "budget": 8000},
    "req_h30@8k": {"arm": "ours", "head": 30, "req": True, "budget": 8000},
    "req_rel5@8k": {"arm": "ours", "head": 50, "req": True, "link": "rel", "M": 5, "budget": 8000},
    "req_rel5_h30@8k": {"arm": "ours", "head": 30, "req": True, "link": "rel", "M": 5, "budget": 8000},
    "req_mass@8k": {"arm": "ours", "head": 50, "req": True, "link": "mass", "budget": 8000},
    "req_l05_rel5@8k": {"arm": "ours", "head": 50, "req": True, "lam": 0.5, "link": "rel", "M": 5, "budget": 8000},
    "req_P3_rel5_h30@8k": {"arm": "ours", "head": 30, "req": True, "P": 3, "link": "rel", "M": 5, "budget": 8000},
    # 4,000 tokens: the head must fit the budget
    "rag@4k": {"arm": "rag", "budget": 4000},
    "ours_noact@4k": {"arm": "ours", "head": 25, "link": "mass", "act": False, "budget": 4000},
    "seed_noact@4k": {"arm": "ours", "head": 25, "budget": 4000},
    "rel5@4k": {"arm": "ours", "head": 25, "link": "rel", "M": 5, "budget": 4000},
    "req_rel5@4k": {"arm": "ours", "head": 15, "req": True, "link": "rel", "M": 5, "budget": 4000},
    "req_rel3_h20@4k": {"arm": "ours", "head": 20, "req": True, "P": 1, "link": "rel", "M": 3, "budget": 4000},
}


def measure(out_path, names=None):
    W = World()
    W.compile_requirements()
    res = {}
    names = names or list(SPECS)
    t0 = time.perf_counter()
    for name in names:
        spec = SPECS[name]
        per_q = {}
        for qi, qid in enumerate(W.w.qids):
            packed, spans = W.pack(W.units(qi, spec), spec["budget"])
            per_q[qid] = _score(W.w, qid, spans)
        s = summarise(W.w, per_q)
        res[name] = {"spec": spec, "summary": s,
                     "per_q": {q: [v["answer_covered"], v["all_gold"], v["gold_present"], v["gold_pages"]]
                               for q, v in per_q.items()}}
        print(f"[{time.perf_counter() - t0:5.0f}s] {name:22s} {fmt(s)}", flush=True)
        Path(out_path).write_text(json.dumps(res, sort_keys=True) + "\n")


def block_rows(W, qi, packed, spans, arm_name, extra=None):
    qid = W.w.qids[qi]
    ps = [{k: p[k] for k in ("id", "text", "sources", "dates")} for p in packed]
    return {"qid": qid, "arm": arm_name, "question": W.w.question[qid], "question_date": None,
            "stratum": W.w.stratum[qid], "passages": ps, "context_tokens": G.ctx_tokens(ps),
            "context_sha256": hashlib.sha256(G.canonical(ps).encode()).hexdigest(),
            "spans": {str(si): [list(x) for x in v] for si, v in spans.items()}, **(extra or {})}


def write(spec_path, out_path):
    """SPEC.json: {arm_name: spec_name}. Writes rows with their delivered spans (for pass 2); no gold field."""
    spec = json.loads(Path(spec_path).read_text())
    W = World(with_gold=False)
    if any(SPECS[s].get("req") for s in spec.values()):
        W.compile_requirements()
    rows = []
    for arm_name, sname in spec.items():
        sp = SPECS[sname]
        for qi in range(len(W.w.qids)):
            packed, spans = W.pack(W.units(qi, sp), sp["budget"])
            rows.append(block_rows(W, qi, packed, spans, arm_name, {"spec": sname}))
    doc = {"schema": "bench-recovery.stage3.reader-contexts/1", "dataset": "frames", "material": "w3-consumed",
           "label": "DEV-ONLY", "producer": {"packet": "J", "script": str(Path(__file__).resolve()),
                                            "specs": {a: SPECS[s] for a, s in spec.items()}},
           "cut": "packet-J-leaf-merge-sections", "rows": rows}
    Path(out_path).write_text(json.dumps(doc, ensure_ascii=False) + "\n")
    print(json.dumps({"rows": len(rows), "arms": list(spec)}), flush=True)


# ------------------------------------------------------------------ pass 2: the reader's stated needs, fetched
def fetch_units(W, qi, phrases, kind, taken_spans, per_phrase=200):
    """Ranked new units for the reader's stated needs. Every arm ranks each phrase by s(phrase) (+ the question score
    at weight 0.5: the need is read in the question's context), round-robin over phrases.
    rag   that ranking through MMR 0.7 (its own ranker)
    ours  first, per phrase, the pages whose title the phrase names (the title finder that recovered the links,
          exact binding as the frontend does with the question): their best pieces by the phrase ranking; then
          pages title-linked from the delivered sections whose title the phrase names; then the phrase ranking."""
    if not phrases:
        return []
    Sph = W.text_scores(phrases)
    r = W.arm.base[:, qi]
    lists = []
    for k, ph in enumerate(phrases):
        rr = Sph[k] + 0.5 * r
        t = np.argpartition(-rr, per_phrase)[:per_phrase]
        t = t[np.argsort(-rr[t], kind="stable")]
        if kind == "rag":
            L = [int(x) for x in G.mmr(t, rr[t], W.V, per_phrase)]
        else:
            named = DF.find_titles(ph, W.keys, 8)
            first = []
            for p in sorted(named, key=lambda p: -float(rr[W.page_units[p]].max())):
                us = W.page_units[p]
                first += [int(x) for x in us[np.argsort(-rr[us], kind="stable")[:3]]]
            L = first + [int(x) for x in t]
        lists.append(L)
    out, seen, ptr = [], set(), [0] * len(lists)
    while any(ptr[k] < len(L) for k, L in enumerate(lists)) and len(out) < 600:
        for k, L in enumerate(lists):
            while ptr[k] < len(L) and L[ptr[k]] in seen:
                ptr[k] += 1
            if ptr[k] < len(L):
                seen.add(L[ptr[k]])
                out.append(L[ptr[k]])
    units = []
    for i in out:
        u = W.w.unit_obj("leaf", i)
        rest = G.subtract_spans((u["start"], u["end"]), taken_spans.get(u["doc"], []))
        for a, b in rest:
            if b - a >= 40:
                units.append({**u, "start": a, "end": b, "text": W.w.texts[u["doc"]][a:b]})
    return units


def pass2(ctx_path, read_path, variant, out_path, budget=4000):
    """For every row whose pass-1 read named missing facts, fetch them (fetch_units) and write the pass-2 row:
    pass-1 passages followed by the fetched blocks (ids suffixed ':g2'), pass-2 budget 4,000 tokens for every arm.
    Rows with nothing missing are not written (their pass-1 answer stands)."""
    ctx = json.loads(Path(ctx_path).read_text())
    rd = json.loads(Path(read_path).read_text())["per_q"]
    W = World(with_gold=False)
    qidx = {q: i for i, q in enumerate(W.w.qids)}
    rows, n_missing = [], 0
    for r in ctx["rows"]:
        key = f"{r['qid']}|{r['arm']}|{variant}"
        got = rd.get(key)
        if not got or not got.get("missing"):
            continue
        n_missing += 1
        phrases = [p for p in got["missing"] if isinstance(p, str) and p.strip()][:6]
        taken = {int(si): [tuple(x) for x in v] for si, v in r["spans"].items()}
        kind = "rag" if r["arm"].startswith("rag") else "ours"
        units = fetch_units(W, qidx[r["qid"]], phrases, kind, taken)
        for u in units[:600]:
            W.w.view(u["doc"])
        packed2, spans2 = G.delivered_pack(units, W.w.views, budget, None, extend=False, max_tries=600)
        for p in packed2:
            p["id"] = p["id"] + ":g2"
        ps2 = [{k: p[k] for k in ("id", "text", "sources", "dates")} for p in packed2]
        allspans = defaultdict(list)
        for si, v in taken.items():
            allspans[si] += v
        for si, v in spans2.items():
            allspans[int(si)] += list(v)
        row = {**r, "passages": r["passages"] + ps2, "pass2_phrases": phrases, "pass2_blocks": len(ps2),
               "context_tokens": G.ctx_tokens(r["passages"] + ps2),
               "spans": {str(si): [list(x) for x in G.merge_spans(v)] for si, v in allspans.items()}}
        rows.append(row)
    doc = {**{k: v for k, v in ctx.items() if k != "rows"}, "pass2": {"from_read": read_path, "variant": variant,
                                                                    "budget": budget}, "rows": rows}
    Path(out_path).write_text(json.dumps(doc, ensure_ascii=False) + "\n")
    print(json.dumps({"rows_with_missing": n_missing, "written": len(rows)}), flush=True)


def score_ctx_file(path, out_path):
    """Gold-scored delivery of a written contexts file (scoring only)."""
    W = World()
    doc = json.loads(Path(path).read_text())
    res = defaultdict(dict)
    for r in doc["rows"]:
        spans = {int(si): [tuple(x) for x in v] for si, v in r["spans"].items()}
        res[r["arm"]][r["qid"]] = _score(W.w, r["qid"], spans)
    out = {}
    for arm, per_q in res.items():
        full = {q: per_q.get(q, {"answer_covered": None, "all_gold": False, "gold_present": 0, "gold_pages": 0})
                for q in W.w.qids}
        out[arm] = {"rows": len(per_q), "summary": summarise(W.w, full),
                    "per_q": {q: [v["answer_covered"], v["all_gold"], v["gold_present"], v["gold_pages"]]
                              for q, v in per_q.items()}}
        print(arm, len(per_q), fmt(out[arm]["summary"]), flush=True)
    Path(out_path).write_text(json.dumps(out, sort_keys=True) + "\n")


if __name__ == "__main__":
    op = sys.argv[1]
    if op == "measure":
        measure(sys.argv[2], sys.argv[3].split(",") if len(sys.argv) > 3 else None)
    elif op == "write":
        write(sys.argv[2], sys.argv[3])
    elif op == "pass2":
        pass2(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])
    elif op == "scorefile":
        score_ctx_file(sys.argv[2], sys.argv[3])
