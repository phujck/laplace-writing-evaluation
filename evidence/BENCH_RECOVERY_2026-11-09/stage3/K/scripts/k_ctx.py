"""Packet K step A: turn selection for every arm on L's frozen zero-call index, packed by one greedy rule for every
arm, zero model calls, vector cache only (no GPU). DEV-ONLY: dev24-w2 (fit) and the September final 48 (check), all
questions including the abstention ones (the headline is of 48). Gold never enters this script.

Arms (L/scripts/lm_contexts.py arm_specs; the index rules are not our method, so every arm gets them):
  ours_keys   relational_keys: dense order on key dn + R3 activation where routed (dev24 only), views=2, facets rr
  dense_keys  the RAG arm on the same index
  hybrid_keys hybrid 0.7 dense + 0.3 BM25 on the same index
Packing (identical for every arm): walk the arm's order, add the whole turn when its cl100k tokens (text + 12 for its
header line) fit in what is left of the budget, at most 120 turns. Output: K/ctx/sel_<split>.json with, per question,
the selected local indices per arm and budget, the top-400 order per arm, and the public fields of every turn that any
arm selected or ranked in its top 400 (session id, date, role, turn index, text).
  heavy.sh env CUDA_VISIBLE_DEVICES= L_SCRATCH=<K scratch> laplace-python k_ctx.py dev24|final48"""
import json, sys, os
from pathlib import Path
sys.path.insert(0, "/home/phujck/VScodeProjects/laplace/evidence/BENCH_RECOVERY_2026-11-09/stage3/L/scripts")
assert "K" in os.environ.get("L_SCRATCH", "")
import levers as LV
import lm_core as L
import lm_contexts as LC

K = Path("/home/phujck/VScodeProjects/laplace/evidence/BENCH_RECOVERY_2026-11-09/stage3/K")
BUDGETS = (2000, 4000, 8000)
TOP = 400
MAX_TURNS = 120
HDR = 12

_enc = None
def ntok(t):
    global _enc
    if _enc is None:
        import tiktoken
        _enc = tiktoken.get_encoding("cl100k_base")
    return len(_enc.encode(t, disallowed_special=()))

def greedy(order, toks, budget):
    out, used = [], 0
    for i in order:
        t = toks[i] + HDR
        if used + t <= budget:
            out.append(i); used += t
            if len(out) >= MAX_TURNS:
                break
        if budget - used < 30:
            break
    return out

def main(split):
    specs = LC.arm_specs("dn", "dn", "claude")
    arms = {"ours_keys": specs["relational_keys"]["cfg"], "dense_keys": specs["dense_keys"]["cfg"],
            "hybrid_keys": specs["hybrid_keys"]["cfg"]}
    LV._init((split,))
    br = {}
    if split == "dev24":
        from lm_branches import dev24_branches
        br = dev24_branches(LV._CASES[split])
    out = {}
    for c in LV._CASES[split]:
        st = LV.CaseState(c, br.get(c.qid), split)
        toks = [ntok(o["text"]) for o in c.obs]
        rec = {"question": c.question, "question_date": c.question_date, "abstention": c.abstention,
               "n_turns": len(c.obs), "sel": {}, "order": {}}
        keep = set()
        for a, cfg in arms.items():
            order, _score = st.order(cfg)
            if cfg["ranker"] == "rel" and br.get(c.qid):
                # R3 activation: active branches first (C._extended), then the dense order
                from relational import harness_coverage as C
                ext = C._extended(order, br[c.qid]["branch"], cfg["k"])
                order = list(dict.fromkeys(list(ext) + list(order)))
            rec["order"][a] = order[:TOP]
            keep.update(order[:TOP])
            for b in BUDGETS:
                s = greedy(order, toks, b)
                rec["sel"][f"{a}@{b}"] = s
                keep.update(s)
        rec["turns"] = {str(i): {"id": c.obs[i]["id"], "session_id": c.obs[i]["session_id"], "date": c.obs[i]["date"],
                                 "role": c.obs[i]["role"], "turn_index": c.obs[i]["turn_index"],
                                 "text": c.obs[i]["text"], "tokens": toks[i]} for i in sorted(keep)}
        out[c.qid] = rec
        print(c.qid, {k: len(v) for k, v in rec["sel"].items() if k.endswith("4000")}, flush=True)
    (K / "ctx").mkdir(exist_ok=True)
    (K / "ctx" / f"sel_{split}.json").write_text(json.dumps(out, ensure_ascii=False))

if __name__ == "__main__":
    main(sys.argv[1])
