"""Zero-call levers on operand recall (packet L, steps 1-2). CPU only: reads the vector cache encode_all.py wrote and
refuses to encode (no GPU in this script).

A CONFIG is a general rule applied identically to every question of a split:
  ranker  dense | hybrid | rel | relh rel = the dense order of the same key + R3's active branches (dev24 bank) packed
                                      by the covering packer; on the final 48 there is no activation (all 'facet');
                                      relh = the same with the hybrid score (dense + alpha * BM25/max) as the order
  key     keys.doc_keys variant       the turn's embedding key (the packed/read unit stays the raw turn)
  q       q | fmax | rr               question only | max over the obligation facets | round-robin over facet orders
  views   0 | 1 | 2 | 3               1: long turns scored by max over whole key and its views (L-D); 2: also sentence
                                      views of every user turn; 3: sentence views of every turn (sviews.py)
  quota   0 | m                       per-session quota: the m best turns of each session before any session's
                                      (m+1)-th (blocks of m, stable in score order)
  window  none | boost | filter       sessions inside the question's date window first | only those (when the window
                                      holds at least one session)
  role    0 | d                       +d to user turns' score unless the question addresses the assistant
  unit    pair | turn | round         the packed group (pair = (previous, selected), the L-B unit)
  k       candidate head (50)
  alpha   hybrid's lexical weight (0.5 = the September hybrid, 0.5*(dense + bm25/max))
  key v1fact|v1span|v1fact_dn|v1span_dn   dev24 only: proxy fact keys from the banked v1 extraction (v1keys.py);
          configs on these keys are skipped on the final 48 (no extraction exists there) and reported as fit-only
Packs: pair_cover (packer.pack_budgets, all rankers) and, for dense/hybrid, chain_ff (the September packer).
Gold is applied only after every pack of the case is computed (score step), never to ranking or packing.
"""
from __future__ import annotations

import argparse
import itertools
import json
import multiprocessing as mp
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np

import lm_core as L
import keys as K
import v1keys as V1
import la_keys as LK
import sviews as SV
import os
LA_READER = os.environ.get("LA_READER", "claude")

_ASSISTANT = re.compile(r"\b(you|your)\b", re.I)


def _forbid_encode(texts, role):
    c = L._load_cache()
    keys = [L._key(role, t) for t in texts]
    missing = [t for t, k in zip(texts, keys) if k not in c]
    if missing:
        raise RuntimeError(f"{len(missing)} texts are not in the vector cache; run encode_all.py under the GPU lock")
    out = np.stack([c[k] for k in keys]).astype(np.float32)
    return out / np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-12)


L.encode = _forbid_encode


def interleave(orders: list[list[int]]) -> list[int]:
    out, seen = [], set()
    for tup in itertools.zip_longest(*orders):
        for i in tup:
            if i is not None and i not in seen:
                seen.add(i)
                out.append(i)
    return out


def quota_order(order: list[int], session_of: list[int], m: int) -> list[int]:
    count, keyed = {}, []
    for r, i in enumerate(order):
        s = session_of[i]
        k = count.get(s, 0)
        count[s] = k + 1
        keyed.append((k // m, r, i))
    return [i for _b, _r, i in sorted(keyed)]


class CaseState:
    """Every vector and lexical score of one case, computed once; configs are evaluated against it."""

    def __init__(self, c: L.Case, branches: dict | None, split: str = "dev24"):
        m = L.mb()
        self.c = c
        self.dk = K.doc_keys(c, m)
        if split == "dev24":
            vv = V1.variants(c, self.dk)
            vv.pop("_coverage")
            self.dk.update(vv)
        if LK.available(split, LA_READER):
            lv = LK.variants(c, self.dk, split, LA_READER)
            lv.pop("_coverage")
            self.dk.update(lv)
        self.facets = K.obligations(c.question)
        self.fv = L.encode([m.preprocess_text("query", f) for f in self.facets], "query")
        self.vec = {}
        self.view_vecs = None
        self.branches = branches
        self.lex = {}
        n = len(c.obs)
        raw = self.dk["raw"]
        vs, owner = [], []
        for i, t in enumerate(raw):
            for w in K.views(t, L.encoder_tokens):
                vs.append(w)
                owner.append(i)
        self.views_owner = np.array(owner, dtype=np.int64)
        self.views_V = L.encode(vs, "doc") if vs else np.zeros((0, 384), np.float32)
        self.n = n
        self.window = K.question_window(c.question, c.question_date)
        self.session_dates = [L.parse_lm_date(s.session_date) for s, _t in c.turns]
        self.addresses_assistant = bool(_ASSISTANT.search(c.question))

    def V(self, key):
        if key not in self.vec:
            self.vec[key] = L.encode(self.dk[key], "doc")
        return self.vec[key]

    def sentence_views(self, mode):
        if not hasattr(self, "_sv"):
            self._sv = {}
        if mode not in self._sv:
            tv = SV.turn_views(self.c.obs, L.mb(), mode)
            own = np.array([i for i, _t in tv], dtype=np.int64)
            V = L.encode([t for _i, t in tv], "doc") if tv else np.zeros((0, 384), np.float32)
            self._sv[mode] = (own, V)
        return self._sv[mode]

    def dense_scores(self, key, views) -> np.ndarray:
        """(facets x turns) cosine matrix."""
        S = self.fv @ self.V(key).T
        sets = []
        if views and len(self.views_V):
            sets.append((self.views_owner, self.views_V))
        if views >= 2:
            sets.append(self.sentence_views(views))
        for own, VV in sets:
            if not len(VV):
                continue
            SVm = self.fv @ VV.T
            for j, i in enumerate(own):
                S[:, i] = np.maximum(S[:, i], SVm[:, j])
        return S

    def lex_scores(self, key) -> np.ndarray:
        if key not in self.lex:
            texts = self.dk[key]
            self.lex[key] = np.stack([L.normalize_lexical(L.bm25(texts, f)) for f in self.facets])
        return self.lex[key]

    def order(self, cfg) -> tuple[list[int], dict | None]:
        S = self.dense_scores(cfg["key"], cfg["views"])
        if cfg["ranker"] in ("hybrid", "relh"):
            al = cfg.get("alpha", 0.5)
            S = (1.0 - al) * S + al * self.lex_scores(cfg["key"])
        if cfg["role"]:
            bump = np.array([cfg["role"] if (o["role"] == "user") != self.addresses_assistant else 0.0
                             for o in self.c.obs])
            S = S + bump[None, :]
        if cfg["q"] == "q":
            vals = S[0]
            order = L.stable_order(vals)
        elif cfg["q"] == "fmax":
            vals = S.max(0)
            order = L.stable_order(vals)
        elif cfg["q"] == "rr":
            vals = None
            order = interleave([L.stable_order(S[0])] + [L.stable_order(S[j]) for j in range(1, len(S))])
        else:
            raise ValueError(cfg["q"])
        reordered = False
        if cfg["window"] != "none" and self.window is not None:
            lo, hi = self.window
            inw = [lo <= self.session_dates[i] <= hi for i in range(self.n)]
            if any(inw):
                if cfg["window"] == "boost":
                    order = [i for i in order if inw[i]] + [i for i in order if not inw[i]]
                else:
                    order = [i for i in order if inw[i]]
                reordered = True
        if cfg["quota"]:
            order = quota_order(order, self.c.session_of, cfg["quota"])
            reordered = True
        if vals is not None and not reordered:
            score = {i: (1.0 + float(vals[i])) / 2.0 for i in order}       # index.positive_score
        else:
            score = {i: 1.0 / (1.0 + r) for r, i in enumerate(order)}
        return order, score


def run_case(args):
    split, qid, cfgs, branch_info, gold_ids = args
    cases = {c.qid: c for c in _CASES[split]}
    c = cases[qid]
    st = CaseState(c, branch_info, split)
    pk = L.Packer(c)
    out = {}
    packs = {}
    orders = {}
    memo = {}
    cfgs = {n: cf for n, cf in cfgs.items() if cf["key"] in st.dk}
    for name, cfg in cfgs.items():
        order, score = st.order(cfg)
        orders[name] = order
        branch = None
        if cfg["ranker"] in ("rel", "relh") and branch_info is not None:
            branch = branch_info["branch"]
        head = tuple(order[:cfg["k"]])
        mk = ("pc", head, cfg["unit"], cfg["k"], branch is not None, tuple(round(score[i], 6) for i in head))
        if mk not in memo:
            memo[mk] = pk.pair_cover(order, branch, score, k=cfg["k"], unit=cfg["unit"])
        p = {"pair_cover": memo[mk]}
        if cfg["ranker"] not in ("rel", "relh") and cfg["unit"] == "pair":
            mk2 = ("ff", tuple(order), cfg["k"])
            if mk2 not in memo:
                memo[mk2] = pk.chain_first_fit(order, cfg["k"])
            p["chain_ff"] = memo[mk2]
        packs[name] = p
    # ---- score step (gold only here)
    for name in cfgs:
        ranks = L.ranks_of(orders[name], c, gold_ids) if len(orders[name]) == len(c.obs) else \
            L.ranks_of(orders[name] + [i for i in range(len(c.obs)) if i not in set(orders[name])], c, gold_ids)
        out[name] = {"ranks": ranks,
                     "held": {pn: {b: len(set(v[b]) & gold_ids) for b in v} for pn, v in packs[name].items()},
                     "required": len(gold_ids)}
    return qid, out


_CASES = {}


def _init(splits):
    for s in splits:
        _CASES[s] = L.material(s)
    if "dev24" in splits:
        V1._load()


def default_cfg(**kw):
    cfg = {"ranker": "dense", "key": "raw", "q": "q", "views": 0, "quota": 0, "window": "none", "role": 0.0,
           "unit": "pair", "k": L.TOP_K, "alpha": 0.5}
    cfg.update(kw)
    return cfg


def cfg_name(cfg):
    d = default_cfg()
    parts = [cfg["ranker"], cfg["key"], cfg["q"]]
    for k in ("views", "quota", "window", "role", "unit", "k", "alpha"):
        if cfg[k] != d[k]:
            parts.append(f"{k}={cfg[k]}")
    return "|".join(parts)


def grid(stage: str) -> dict:
    cfgs = []
    if stage == "1":
        for r in ("dense", "hybrid", "rel"):
            for key in ("raw", "date", "norm", "dn", "prev", "round", "prev_dn", "round_dn", "v1fact", "v1span",
                        "v1fact_dn", "v1span_dn"):
                for q in ("q", "fmax", "rr"):
                    for v in (0, 1):
                        cfgs.append(default_cfg(ranker=r, key=key, q=q, views=v))
    elif stage == "2":
        for r in ("dense", "hybrid", "rel"):
            for key in ("raw", "dn", "round_dn", "prev_dn"):
                for q in ("q", "rr"):
                    for mod in ({"quota": 1}, {"quota": 2}, {"quota": 3}, {"window": "boost"}, {"window": "filter"},
                                {"role": 0.02}, {"role": 0.05}, {"unit": "turn"}, {"unit": "round"}, {"k": 100}):
                        cfgs.append(default_cfg(ranker=r, key=key, q=q, views=1, **mod))
                    if r == "hybrid":
                        for al in (0.3, 0.7):
                            cfgs.append(default_cfg(ranker=r, key=key, q=q, views=1, alpha=al))
    elif stage == "e4":
        # E4 after `la_extract.py parse`: both indexes from one extraction (lafact = span-verified, ours; laraw = the
        # model's unverified fields, dense-with-fact-keys), the zero-call dn key beside them, the whole-turn unit the
        # zero-call grids chose (pair kept for the L-B report), views 1 and 2, and the September baselines.
        cfgs.append(default_cfg(ranker="hybrid", key="raw", q="q"))
        cfgs.append(default_cfg(ranker="dense", key="raw", q="q"))
        for r in ("dense", "rel"):
            for key in ("dn", "laraw", "lafact", "laraw_dn", "lafact_dn"):
                for v in (1, 2):
                    for unit in ("turn", "pair"):
                        cfgs.append(default_cfg(ranker=r, key=key, q="q", views=v, unit=unit))
        for key in ("dn", "laraw_dn", "lafact_dn"):
            cfgs.append(default_cfg(ranker="hybrid", key=key, q="q", views=1, unit="turn", alpha=0.3))
        # THE FROZEN PACK (lm_contexts.FROZEN: q=rr, views=2, whole turn), the one E7 reads: E4's verdict
        # (lafact vs laraw vs dn at 1k/2k) is taken on these rows. rel = relational_ledger's order (without header),
        # dense = dense_ledger / dense_keys, hybrid alpha 0.3 = hybrid_keys given the same keys.
        for r in ("rel", "dense"):
            for key in ("dn", "laraw_dn", "lafact_dn"):
                cfgs.append(default_cfg(ranker=r, key=key, q="rr", views=2, unit="turn"))
        for key in ("dn", "laraw_dn", "lafact_dn"):
            cfgs.append(default_cfg(ranker="hybrid", key=key, q="rr", views=2, unit="turn", alpha=0.3))
    else:
        for spec in json.loads(stage if not stage.startswith("@") else Path(stage[1:]).read_text()):
            cfgs.append(default_cfg(**spec))
    return {cfg_name(c): c for c in cfgs}


def summarise(results: dict, cfgs: dict, split: str) -> dict:
    recs = L.p6_records()
    op_classes = ("count_aggregate", "temporal", "latest_state")
    out = {}
    for name in cfgs:
        rows = {q: r[name] for q, r in results.items() if name in r}
        if not rows:
            continue
        packs = {}
        for pn in rows[next(iter(rows))]["held"]:
            per_b = {}
            for b in map(str, L.BUDGETS):
                fr = [r["held"][pn][b] / r["required"] for r in rows.values()]
                op = [r["held"][pn][b] == r["required"] for q, r in rows.items() if recs[q]["class"] in op_classes]
                per_b[b] = {"fraction": round(float(np.mean(fr)), 4), "complete": int(sum(f == 1.0 for f in fr)),
                            "operator_complete": int(sum(op)), "n": len(fr), "n_operator": len(op)}
            packs[pn] = per_b
        op_ranks = {q: r["ranks"] for q, r in rows.items() if recs[q]["class"] in op_classes}
        all_max = [max(r) for r in op_ranks.values()]
        out[name] = {"packs": packs, "operand_ranks": op_ranks,
                     "operator_max_rank_median": float(np.median(all_max)) if all_max else None,
                     "operator_operands_within_20": int(sum(sum(1 for x in r if x <= 20) for r in op_ranks.values())),
                     "operator_operands_within_50": int(sum(sum(1 for x in r if x <= 50) for r in op_ranks.values())),
                     "operator_operands": int(sum(len(r) for r in op_ranks.values()))}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="1")
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=2)       # heavy.sh rule: at most two processes per job
    a = ap.parse_args()
    t0 = time.time()
    cfgs = grid(a.stage)
    splits = ("dev24", "final48")
    _init(splits)
    from lm_branches import dev24_branches
    br = dev24_branches(_CASES["dev24"])
    jobs = []
    for s in splits:
        g = L.gold(s)
        for c in _CASES[s]:
            if c.qid in g:
                jobs.append((s, c.qid, cfgs, br.get(c.qid) if s == "dev24" else None, g[c.qid]))
    with mp.get_context("fork").Pool(a.workers) as pool:
        res = pool.map(run_case, jobs, chunksize=1)
    by_split = {s: {} for s in splits}
    for (s, qid, *_), (_q, r) in zip(jobs, res):
        by_split[s][qid] = r
    summary = {s: summarise(by_split[s], cfgs, s) for s in splits}
    result = {"stage": a.stage, "configs": cfgs, "summary": summary, "seconds": round(time.time() - t0, 1),
              "model_calls": 0, "gpu": "none (vector cache)"}
    Path(a.out).write_text(json.dumps(result, indent=1, sort_keys=True))
    print("configs", len(cfgs), "seconds", result["seconds"])


if __name__ == "__main__":
    main()
