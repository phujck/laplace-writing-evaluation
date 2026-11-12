"""Packet L (LongMemEval-S), stage 3 of BENCH_RECOVERY: the zero-call coverage harness.

DEV-ONLY. Material: dev24-w2 (24 questions, 18 answerable) as FIT and the September final 48 (42 answerable) as
CHECK. The pinned w3 188 is never opened: its draw file is read for its qids only, to assert disjointness.

What this module holds (no model call anywhere; GPU only through `encode`, wrapped by the caller in the shared lock):
  material(split)      cases, opaque observations, question text/date/type, P6's class per qid
  gold(split)          gold answer-turn ids from P6's classes.json (P6 read them through the logged loader; used here
                       only to SCORE, never as an input to ranking or packing)
  encode(texts, role)  the imported fp16 BGE-small (relational.encoder) on CUDA under a 1.0 GiB arena, cached by
                       sha256(role, text) in the scratchpad (no corpus copy kept in the repo)
  bm25(...)            atlas.reconstruction.lexical_index's BM25 (k1 1.2, b 0.75, idf log1p((n-df+.5)/(df+.5)),
                       query term counts weighted) re-implemented on CPU; reproduction against the imported hybrid
                       ranking is checked by the caller
  Packers              the organs index_gap uses: pair_cover = packer.pack_budgets over (previous, selected) pairs
                       (index_gap.py:549-550); chain_first_fit = memory_benchmark.pack_expansion_groups over
                       expansion_groups (the September dense/hybrid packer, index_gap.py:544)
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import datetime as _dt
from pathlib import Path

import numpy as np

LAPLACE = Path("/home/phujck/VScodeProjects/laplace")
RF = LAPLACE / "synthetics papers/relational-frontend"
P6 = LAPLACE / "evidence/BENCH_RECOVERY_2026-11-09/stage2/P6-longmem-operator-need"
HERE = LAPLACE / "evidence/BENCH_RECOVERY_2026-11-09/stage3/L"
SCRATCH = Path(os.environ.get("L_SCRATCH", "/tmp/claude-1000/-home-phujck-VScodeProjects-laplace/"
                              "fa5de812-b113-48f4-a3b5-1f6a285e3864/scratchpad/L"))
SCRATCH.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(RF / "src"))
sys.dont_write_bytecode = True

BUDGETS = (1000, 2000, 4000, 8000)
TOP_K = 50
MAXIMUM = 100

_mb = None


def mb():
    global _mb
    if _mb is None:
        from relational import harness_coverage as C
        _mb = C._extension("memory_benchmark")
    return _mb


# ------------------------------------------------------------------------------------------------ material

def split_ids() -> dict:
    dev = json.loads((RF / "derived/datasets/draws/longmemeval_s_dev24-w2.json").read_text())["qids"]
    man = json.loads((RF / "imported/results/extension_reviews/longmem_split_manifest.json").read_text())
    fin = list(man["final_ids"])
    sealed = set(json.loads((RF / "derived/datasets/draws/longmemeval_s_w3.json").read_text())["qids"])
    assert not (set(dev) | set(fin)) & sealed, "development material overlaps the pinned w3 188"
    assert not set(dev) & set(fin)
    return {"dev24": list(dev), "final48": fin}


_classes = None


def p6_records() -> dict:
    global _classes
    if _classes is None:
        d = json.loads((P6 / "classes.json").read_text())
        _classes = {r["qid"]: r for r in d["records"]}
    return _classes


class Case:
    """One question: its haystack as opaque observations (memory_benchmark.case_to_uniform) and its question."""

    def __init__(self, qid, case, namespace):
        self.qid = qid
        self.case = case
        self.namespace = namespace
        self.obs, self.query = mb().case_to_uniform(case, namespace)
        self.question = case.query.question
        self.question_date = case.query.question_date
        self.turns = [(s, t) for s in case.sessions for t in s.turns]
        self.prev_local = []
        pos = {(o["document_id"], o["turn_index"]): i for i, o in enumerate(self.obs)}
        for o in self.obs:
            self.prev_local.append(pos.get((o["document_id"], o["turn_index"] - 1)))
        self.next_local = [pos.get((o["document_id"], o["turn_index"] + 1)) for o in self.obs]
        self.session_of = [s.session_index for s, _t in self.turns]
        rec = p6_records().get(qid, {})
        self.stratum = rec.get("stratum")
        self.klass = rec.get("class")
        self.abstention = qid.endswith("_abs")


def material(split: str) -> list[Case]:
    from relational import index_text as XT
    ids = split_ids()[split]
    cases = XT.longmem_cases(ids)
    namespace = mb().build_opaque_namespace([cases[q] for q in ids])
    return [Case(q, cases[q], namespace) for q in ids]


def gold(split: str) -> dict:
    """qid -> set of gold opaque turn ids (answerable only). From P6's classes.json (logged gold read, 2026-11-09)."""
    recs = p6_records()
    out = {}
    for q in split_ids()[split]:
        if q.endswith("_abs"):
            continue
        out[q] = set(recs[q]["required_turn_ids"])
    return out


# ------------------------------------------------------------------------------------------------ encoding

_enc = None
_batch = None
CACHE_FILE = SCRATCH / "vec_cache.npz"
_vcache: dict | None = None


def _key(role: str, text: str) -> str:
    return hashlib.sha256(json.dumps([role, text], ensure_ascii=False).encode()).hexdigest()


def _load_cache():
    global _vcache
    if _vcache is None:
        _vcache = {}
        if CACHE_FILE.exists():
            z = np.load(CACHE_FILE)
            for k, v in zip(z["keys"], z["vecs"]):
                _vcache[str(k)] = v
    return _vcache


def save_cache():
    c = _load_cache()
    if not c:
        return
    keys = np.array(list(c.keys()))
    vecs = np.stack([c[k] for k in keys]).astype(np.float16)
    np.savez(CACHE_FILE, keys=keys, vecs=vecs)


def encode(texts: list[str], role: str) -> np.ndarray:
    """L2-normalised float32 vectors; uncached texts go through the imported encoder on CUDA (1.0 GiB arena)."""
    global _enc, _batch
    c = _load_cache()
    keys = [_key(role, t) for t in texts]
    todo = list(dict.fromkeys(t for t, k in zip(texts, keys) if k not in c))
    if todo:
        if _enc is None:
            from relational.encoder import load_imported_encoder
            from relational import index_text as XT
            budget = int(0.8 * 2 ** 30)   # arena; CUDA context on top stays under the 1.2 GiB cap
            _enc = load_imported_encoder("cuda", budget_bytes=budget)
            _batch = XT.encoder_batch(_enc, budget)["batch"]
        from relational import index_text as XT
        vals = XT._encode(_enc, todo, role, _batch)
        for t, v in zip(todo, vals):
            c[_key(role, t)] = v.astype(np.float16)
    out = np.stack([c[k] for k in keys]).astype(np.float32)
    out /= np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-12)
    return out


def release_encoder():
    global _enc
    if _enc is not None:
        try:
            _enc.close()
        except Exception:
            pass
        _enc = None


_tok = None


def encoder_tokens(text: str) -> int:
    """Untruncated BGE token count (the encoder truncates at 512)."""
    global _tok
    if _tok is None:
        from tokenizers import Tokenizer
        from relational import paths
        _tok = Tokenizer.from_file(str(paths.imported("models/bge-small-en-v1.5-fp16/tokenizer.json")))
        _tok.no_truncation()
        _tok.no_padding()
    return len(_tok.encode(text).ids)


# ------------------------------------------------------------------------------------------------ BM25 (CPU)

_TOKEN = re.compile(r"[^\W_]+(?:[-'’][^\W_]+)*", re.UNICODE)


def norm_tokens(text: str) -> list[str]:
    import unicodedata
    t = unicodedata.normalize("NFKC", str(text)).casefold().replace("’", "'")
    return [m.group(0) for m in _TOKEN.finditer(t)]


def bm25(doc_texts: list[str], query: str, k1: float = 1.2, b: float = 0.75) -> np.ndarray:
    docs = [norm_tokens(t) for t in doc_texts]
    n = len(docs)
    lengths = np.array([len(d) for d in docs], dtype=np.float64)
    avg = lengths.mean() if n else 1.0
    df: dict[str, int] = {}
    tfs = []
    for d in docs:
        tf: dict[str, int] = {}
        for w in d:
            tf[w] = tf.get(w, 0) + 1
        tfs.append(tf)
        for w in tf:
            df[w] = df.get(w, 0) + 1
    q = norm_tokens(query)
    qc: dict[str, int] = {}
    for w in q:
        if w in df:
            qc[w] = qc.get(w, 0) + 1
    scores = np.zeros(n, dtype=np.float64)
    for w, c in qc.items():
        idf = np.log1p((n - df[w] + 0.5) / (df[w] + 0.5))
        for i, tf in enumerate(tfs):
            f = tf.get(w)
            if f:
                scores[i] += c * idf * (f * (k1 + 1.0) / (f + k1 * (1.0 - b + b * lengths[i] / avg)))
    return scores


def normalize_lexical(s: np.ndarray) -> np.ndarray:
    p = np.clip(s, 0, None)
    m = p.max() if len(p) else 0
    return p / m if m > 0 else np.zeros_like(p)


def stable_order(scores: np.ndarray) -> list[int]:
    return [int(i) for i in np.argsort(-scores, kind="stable")]


# ------------------------------------------------------------------------------------------------ packers

class Packer:
    """Per case: the context cache and the two packing organs (index_gap.CasePacker, with the head size a parameter)."""

    def __init__(self, c: Case):
        from relational import index_gap as G
        m = mb()
        self.tok = m.token_budget_runtime.evidence_tokenizer()
        self.cp = G.CasePacker(m, self.tok, c.case, c.namespace)
        assert [o["id"] for o in self.cp.observations] == [o["id"] for o in c.obs]
        self.c = c

    def pairs(self, order: list[int], k: int) -> list[tuple]:
        obs = self.c.obs
        out = []
        for i in order[:k]:
            p = self.c.prev_local[i]
            out.append(tuple(obs[x]["id"] for x in ((p, i) if p is not None else (i,))))
        return out

    def pair_cover(self, order: list[int], branch: dict | None = None, score: dict | None = None,
                   k: int = TOP_K, unit: str = "pair") -> dict:
        """Covering pack (packer.pack_budgets) of the top-k (+ every active episode's best) as pair/turn units."""
        from relational import harness_coverage as C
        from relational import packer as P
        branch = branch or {i: "facet" for i in order}
        if score is None:
            score = {i: 1.0 / (1.0 + r) for r, i in enumerate(order)}
        ext = C._extended(order, branch, k)
        obs = self.c.obs
        if unit == "pair":
            groups = self.pairs(ext, len(ext))
        elif unit == "turn":
            groups = [(obs[i]["id"],) for i in ext]
        elif unit == "round":       # the selected turn with its next turn (user->assistant round)
            groups = []
            for i in ext:
                n = self.c.next_local[i] if obs[i]["role"] == "user" else None
                p = self.c.prev_local[i] if obs[i]["role"] == "assistant" else None
                ids = [x for x in (p, i, n) if x is not None]
                groups.append(tuple(obs[x]["id"] for x in ids))
        else:
            raise ValueError(unit)
        cands = [{"id": obs[i]["id"], "score": float(score[i]), "branch_r3": branch.get(i, "facet"),
                  "object_ids": list(g)} for i, g in zip(ext, groups)]
        _p, pk = self.cp.covering(cands)
        return pk

    def chain_first_fit(self, order: list[int], k: int = TOP_K) -> dict:
        return self.cp.first_fit(mb().expansion_groups(self.c.obs, order, k))


# ------------------------------------------------------------------------------------------------ metrics

def coverage(packs: dict[str, dict], gold_by_q: dict) -> dict:
    """packs: qid -> {budget: [ids]}; -> per budget: mean fraction, complete count, n."""
    out = {}
    qs = [q for q in packs if q in gold_by_q]
    for b in map(str, BUDGETS):
        fr = [len(set(packs[q][b]) & gold_by_q[q]) / len(gold_by_q[q]) for q in qs]
        out[b] = {"fraction": round(float(np.mean(fr)), 4) if fr else None,
                  "complete": int(sum(1 for f in fr if f == 1.0)), "n": len(qs)}
    return out


def ranks_of(order: list[int], c: Case, gold_ids: set) -> list[int]:
    pos = {c.obs[i]["id"]: r + 1 for r, i in enumerate(order)}
    return sorted(pos[g] for g in gold_ids)


# ------------------------------------------------------------------------------------------------ dates

def parse_lm_date(text: str) -> _dt.date:
    return _dt.datetime.strptime(text.split(" ")[0], "%Y/%m/%d").date()
