"""LongMem reader contexts for packet R (stage3/R/CONTEXT_FORMAT.md), zero model calls, vector cache only (no GPU).

Writes stage3/L/reader_contexts_<material>.json, validated by relational.witness_context.load_context_file before it is
written. One row per (answerable question, arm). Passages are whole conversation turns (the dataset's own unit, never
a token cut) carrying the September public fields (id, text, document_id, date, role, session_id, turn_index), in packed
order; R regroups them by (session day, session id). DEV-ONLY material: dev24-w2 and the September final 48.

ARMS (each a general rule from levers.py; every arm gets the same pass-1 budget, the same tokenizer and the same unit
text; only selection differs). The frozen zero-call index (levers stage 3; the key `dn` was chosen on dev24 AND
the final 48, so the final 48 is not held out for it, see RETURN.md section 7): key `dn` (turn + session-date line + resolved date/quantity mentions), views=2 (long-turn windows +
one sentence view per sentence of every user turn, max rule), the WHOLE TURN as the packed unit, the question's
compiled obligation facets round-robin (q=rr), head 50, covering pack (packer.pack_budgets).
  relational_ledger  that index with key `lafact_dn` (+ span-verified typed fact lines from L-A), R3 activation where
                     a route table exists (dev24), plus the (session day, entity, polarity) continuation header for
                     count/latest questions; growth 'slots'
  dense_ledger       the same index and pack, dense order, key `laraw_dn` (+ the model's own unverified fact fields:
                     the public K=V+fact key, dense-with-fact-keys); growth 'ranker'
  hybrid             the September hybrid exactly (0.5 dense + 0.5 BM25/max on the raw key, first-fit chain packer):
                     the preregistered baseline; growth 'ranker'
  dense              the September dense arm exactly (raw key, question only, first-fit chain): rung 1 of the ladder
  hybrid_keys        hybrid GIVEN THE FROZEN INDEX (key dn, views=2, whole turn, facet round-robin, covering pack),
                     lexical weight 0.3 chosen on fit: unit, keys and views are not our method, so hybrid gets them
  relational_keys / dense_keys   the zero-call arms on the frozen index without any extraction (dense_keys is the
                     honest control: the RAG arm given the same index; on the final 48 it equals relational_keys
                     because no route table exists there). Named differently from the ledger arms.
An arm whose key needs la/tuples_<set>_<reader>.json is skipped (and said so) until `la_extract.py parse` wrote it;
parse refuses a partial extraction unless --allow-partial, and a partial ledger is marked in the file (ledger_completeness).
--header-tuples <name> adds the header to relational_keys from la/tuples_<set>_<name>.json (a zero-call test of the
header path on the v1-proxy ledger; write it with --out to a file NOT named reader_contexts*, so R never reads it).

THE HEADER (relational_ledger only). From the admitted typed facts of the units inside the packed context: rows
(session date ISO, entity, polarity, session_id) whose entity (registry key, else the object's class key) equals the
question's class key (la_schema.class_key of the noun phrase after 'how many' / 'how much', or of the question's
content words for a 'latest' question: currently / now / still / most recent / last). count = the number of distinct
(session day, entity) episodes. No row matched -> no header (a sparse ledger's silence is not a count of zero).
The header's tokens are taken out of the pass-1 budget (pack at budget - header).

  heavy.sh env CUDA_VISIBLE_DEVICES= scripts/laplace-python lm_contexts.py --split dev24 --arms hybrid,relational_keys \
      --budget 4000 [--reader claude] [--key-rel dn --key-dense dn] [--header-tuples v1proxy --out <file>]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import levers as LV            # installs the encode guard (no GPU)
import lm_core as L
import la_keys as LK
import la_schema as S

SCHEMA = "bench-recovery.stage3.reader-contexts/1"
MATERIAL = {"dev24": "dev24-w2", "final48": "sep-final48"}
RESERVE_TOKENS = 6000


FROZEN = {"q": "rr", "views": 2, "unit": "turn"}
# hybrid given the frozen index: the lexical weight chosen on the FIT half only (levers_s3: hybrid|dn|rr|views=2|
# unit=turn mean coverage 1k-8k on dev24 .8681 at alpha 0.3 vs .8333 at 0.5; on every pair-unit fit row of
# levers_s2, 0.7 was below 0.3)
HYBRID_KEYS_ALPHA = 0.3


def arm_specs(key_rel: str, key_dense: str, reader: str) -> dict:
    idx = "turn unit, views=2 (user-turn sentence views + long-turn windows), facet round-robin, covering pack"
    return {
        "relational_ledger": {"cfg": LV.default_cfg(ranker="rel", key="lafact_dn", **FROZEN), "pack": "cover",
                              "growth_mode": "slots", "header": True, "needs_tuples": True,
                              "selection": f"dense order on turn + date/mention line + span-verified typed fact lines, "
                                           f"R3 activation where routed; {idx}; continuation header"},
        "dense_ledger": {"cfg": LV.default_cfg(ranker="dense", key="laraw_dn", **FROZEN), "pack": "cover",
                         "growth_mode": "ranker", "header": False, "needs_tuples": True,
                         "selection": f"dense order on turn + date/mention line + the model's unverified fact fields "
                                      f"(K=V+fact); {idx}"},
        "hybrid": {"cfg": LV.default_cfg(ranker="hybrid", key="raw", q="q"), "pack": "chain_ff",
                   "growth_mode": "ranker", "header": False, "needs_tuples": False,
                   "selection": "September hybrid 0.5 dense + 0.5 BM25/max on the raw turn key, first-fit chain"},
        "dense": {"cfg": LV.default_cfg(ranker="dense", key="raw", q="q"), "pack": "chain_ff",
                  "growth_mode": "ranker", "header": False, "needs_tuples": False,
                  "selection": "September dense on the raw turn key, first-fit chain (rung 1 of the ladder)"},
        "hybrid_keys": {"cfg": LV.default_cfg(ranker="hybrid", key=key_dense, alpha=HYBRID_KEYS_ALPHA, **FROZEN),
                        "pack": "cover", "growth_mode": "ranker", "header": False, "needs_tuples": False,
                        "selection": f"hybrid {1 - HYBRID_KEYS_ALPHA:.1f} dense + {HYBRID_KEYS_ALPHA:.1f} BM25/max "
                                     f"on key '{key_dense}' (alpha chosen on fit); {idx}"},
        "relational_keys": {"cfg": LV.default_cfg(ranker="rel", key=key_rel, **FROZEN), "pack": "cover",
                            "growth_mode": "slots", "header": False, "needs_tuples": False,
                            "selection": f"dense order on key '{key_rel}' + R3 activation where routed; {idx}"},
        "dense_keys": {"cfg": LV.default_cfg(ranker="dense", key=key_dense, **FROZEN), "pack": "cover",
                       "growth_mode": "ranker", "header": False, "needs_tuples": False,
                       "selection": f"dense order on key '{key_dense}'; {idx}"},
    }


# ------------------------------------------------------------------------------------------------ header

_LATEST = re.compile(r"\b(currently|now|still|most recent(ly)?|latest|these days|at the moment)\b", re.I)


_MEASURE = {"piece", "type", "kind", "sort", "time", "day", "week", "month", "year", "hour", "minute", "night",
            "episode", "mile", "dollar", "item", "much", "many"}
_TIME_UNIT = {"day", "week", "month", "year", "hour", "minute", "night"}


def question_class(question: str) -> tuple[str | None, str | None]:
    """(obligation kind, class key) from the question text alone, or (None, None) when no class is determinable.
    'how many/much <np>': the head of <np>; when that head is a measure word, the head of its 'of <np>' complement
    ('pieces of furniture' -> furniture), else of the first prepositional object ('days ... on camping trips' -> trip);
    a time unit followed by ago / passed / older / since is a duration question, not a count (None)."""
    m = re.search(r"\bhow (many|much)\s+(.+?)(?:\s+(?:have|has|had|did|do|does|am|is|are|was|were|will|would)\b|[?,]|$)",
                  question, re.I)
    if m:
        np_ = m.group(2)
        rest = question[m.end(2):]
        if re.match(r"(have|has|had|did|do|does|am|is|are|was|were|will|would|i)\b", np_, re.I):
            return None, None                                  # 'how much did I earn': no counted noun
        words = {S.singular(w) for w in re.findall(r"[a-z]+", np_.lower())}
        if words & _TIME_UNIT and re.search(r"\b(ago|passed|older|younger|since|between)\b", question, re.I):
            return None, None                                  # a duration question, not a count
        k = S.class_key(np_)
        if k in _MEASURE or k == S.UNKNOWN:
            if k in _TIME_UNIT and re.search(r"\b(ago|passed|older|younger|since|between|before|after)\b", question, re.I):
                return None, None
            mo = re.search(r"\bof\s+(.+)$", np_, re.I)
            if mo:
                k = S.class_key(mo.group(1))
            else:
                mp = re.search(r"\b(?:on|in|at|to|for|from|with)\s+(.+?)(?:\s+(?:in|this|last|so far|in the past)\b|[?,]|$)",
                               rest, re.I)
                k = S.class_key(mp.group(1)) if mp else S.UNKNOWN
        return ("aggregation", k) if k not in (S.UNKNOWN, *_MEASURE) else (None, None)
    if _LATEST.search(question):
        content = re.sub(r"\b(what|which|where|who|how|is|are|was|my|i|do|does|did|the|a|an|currently|now|still|"
                         r"most|recent|recently|latest|these|days|at|moment)\b", " ", question.lower())
        k = S.class_key(content)
        return ("state_history", k) if k != S.UNKNOWN else (None, None)
    return None, None


def unit_ids(c) -> list[str]:
    out = []
    for s in c.case.sessions:
        key = LK._session_key(s)
        out.extend(f"lm:{key[:16]}:{i}" for i, _t in enumerate(s.turns))
    assert len(out) == len(c.obs)
    return out


def header_for(c, packed_local: list[int], tuples_units: dict) -> dict | None:
    from relational import packer as P
    kind, klass = question_class(c.question)
    if not kind:
        return None
    uids = unit_ids(c)
    rows, episodes = [], set()
    for i in packed_local:
        for f in (tuples_units.get(uids[i]) or {}).get("facts") or []:
            if not f.get("admitted"):
                continue
            ent = f.get("entity") or f.get("object_class")
            if not ent or ent == S.UNKNOWN:
                continue
            if klass not in (f.get("object_class"), str(ent).split(":")[-1]):
                continue
            day = L.parse_lm_date(c.obs[i]["date"]).isoformat()
            rows.append((day, str(ent), f["polarity"], c.obs[i]["session_id"]))
            episodes.add((day, str(ent)))
    if not rows:
        return None        # no verified tuple matched: absence from a sparse ledger is not a count of zero
    return P.continuation_header({"kind": kind, "subject": klass}, {"count": len(episodes), "rows": rows})


# ------------------------------------------------------------------------------------------------ packing

def public(o: dict) -> dict:
    return {k: o[k] for k in L.mb().PUBLIC_CONTEXT_FIELDS}


def pack_ids(pk: L.Packer, st: LV.CaseState, spec: dict, budget: int, branch_info) -> tuple[list[str], list[int]]:
    """Packed observation ids at `budget` and the arm's full order (local indices)."""
    from relational import harness_coverage as C
    from relational import packer as P
    cfg = spec["cfg"]
    order, score = st.order(cfg)
    obs = st.c.obs
    if spec["pack"] == "chain_ff":           # the September packer (expansion groups, first fit)
        groups = L.mb().expansion_groups(obs, order, cfg["k"])
        packed, _rej, _w = L.mb().pack_expansion_groups(pk.cp.cache, groups, pk.tok, token_budget=budget,
                                                         max_objects=L.MAXIMUM, seam_cache=pk.cp.seam)
        return list(packed.observation_ids), order
    branch = branch_info["branch"] if (cfg["ranker"] in ("rel", "relh") and branch_info) else {i: "facet" for i in order}
    ext = C._extended(order, branch, cfg["k"])
    if cfg["unit"] == "pair":
        groups = pk.pairs(ext, len(ext))
    elif cfg["unit"] == "turn":
        groups = [(obs[i]["id"],) for i in ext]
    else:
        raise ValueError(f"unit {cfg['unit']!r} is not offered to the reader contexts")
    cands = [{"id": obs[i]["id"], "score": float(score[i]), "branch_r3": branch.get(i, "facet"),
              "object_ids": list(g)} for i, g in zip(ext, groups)]
    lc = C.longmem_candidates(cands, obs, "branch_r3", L.mb())
    _plan, _curve, pkd = P.pack_budgets(lc, pk.tok, (budget,), L.MAXIMUM, public_fields=L.mb().PUBLIC_CONTEXT_FIELDS)
    return list(pkd[budget].observation_ids), order


def build(split: str, arms: list[str], budget: int, reader: str, key_rel: str, key_dense: str,
          include_abs: bool, header_tuples: str | None = None) -> dict:
    from relational import witness_context as W
    specs = arm_specs(key_rel, key_dense, reader)
    have_tuples = LK.available(split, reader)
    if header_tuples:
        specs["relational_keys"]["header"] = True
        specs["relational_keys"]["header_from"] = header_tuples
    skipped = {a: "needs la/tuples (run la_extract.py parse after E4)" for a in arms
               if specs[a]["needs_tuples"] and not have_tuples}
    arms = [a for a in arms if a not in skipped]
    tuples_units = LK._load(split, reader) if have_tuples else {}
    hdr_units = LK._load(split, header_tuples) if header_tuples else None
    LV._init((split,))
    br = {}
    if split == "dev24":
        from lm_branches import dev24_branches
        br = dev24_branches(LV._CASES[split])
    types = W.longmem_raw_types()
    rows = []
    for c in LV._CASES[split]:
        if c.abstention and not include_abs:
            continue
        st = LV.CaseState(c, br.get(c.qid), split)
        pk = L.Packer(c)
        local = {o["id"]: i for i, o in enumerate(c.obs)}
        for a in arms:
            spec = specs[a]
            if spec["cfg"]["key"] not in st.dk:
                skipped[a] = f"key {spec['cfg']['key']} unavailable on {split}"
                continue
            hdr = None
            b = budget
            units_for_header = hdr_units if spec.get("header_from") else (tuples_units if have_tuples else None)
            if spec["header"] and units_for_header is not None:
                ids0, _o = pack_ids(pk, st, spec, budget, br.get(c.qid))
                hdr = header_for(c, [local[x] for x in ids0], units_for_header)
                if hdr is not None:
                    b = budget - W.passage_tokens(hdr)
            ids, order = pack_ids(pk, st, spec, b, br.get(c.qid))
            passages = ([hdr] if hdr else []) + [public(c.obs[local[x]]) for x in ids]
            inside = set(ids)
            reserve, rt = [], 0
            for i in order:
                if c.obs[i]["id"] in inside:
                    continue
                p = public(c.obs[i])
                t = W.passage_tokens(p)
                if rt + t > RESERVE_TOKENS:
                    break
                reserve.append(p)
                rt += t
            ctx_tokens = sum(W.passage_tokens(p) for p in passages)
            rows.append({"qid": c.qid, "arm": a, "question": c.question, "question_date": c.question_date,
                         "stratum": types[c.qid]["question_type"], "passages": passages,
                         "context_tokens": ctx_tokens,
                         "context_sha256": hashlib.sha256(W.canonical(passages).encode()).hexdigest(),
                         "reserve": reserve, "reserve_rule": "remaining turns of the case history in the arm's own "
                                                             "order, up to 6,000 cl100k tokens",
                         "work": {"pack": spec["pack"], "pack_budget_evidence_tokens": b, "header": hdr is not None,
                                  "turns": len(ids), "config": LV.cfg_name(spec["cfg"])}})
    script = Path(__file__).resolve()
    doc = {"schema": SCHEMA, "dataset": "longmemeval_s", "material": MATERIAL[split], "label": "DEV-ONLY",
           "producer": {"packet": "L", "script": str(script),
                        "script_sha256": hashlib.sha256(script.read_bytes()).hexdigest()},
           "tokenizer": "cl100k_base", "pass1_budget_tokens": budget,
           "arms": {a: {"selection": specs[a]["selection"], "growth_mode": specs[a]["growth_mode"],
                        "header": specs[a]["header"]} for a in arms if a not in skipped},
           "rows": rows, "skipped_arms": skipped, "model_calls": 0,
           "ledger_completeness": (LK._completeness(split, reader) if have_tuples else None)}
    return doc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=("dev24", "final48"), required=True)
    ap.add_argument("--arms", default="hybrid,dense,hybrid_keys,relational_keys,dense_keys,relational_ledger,dense_ledger")
    ap.add_argument("--budget", type=int, default=4000)
    ap.add_argument("--reader", default="claude")
    ap.add_argument("--key-rel", default="dn")
    ap.add_argument("--key-dense", default="dn")
    ap.add_argument("--include-abs", action="store_true")
    ap.add_argument("--header-tuples", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    doc = build(a.split, a.arms.split(","), a.budget, a.reader, a.key_rel, a.key_dense, a.include_abs,
                a.header_tuples)
    out = Path(a.out) if a.out else L.HERE / f"reader_contexts_{a.split}.json"
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, sort_keys=True))
    from relational import witness_context as W
    W.load_context_file(tmp)                  # validated before it takes the real name
    tmp.replace(out)
    by_arm = {}
    for r in doc["rows"]:
        by_arm.setdefault(r["arm"], []).append(r["context_tokens"])
    print(json.dumps({"out": str(out), "rows": len(doc["rows"]), "skipped": doc["skipped_arms"],
                      "context_tokens_mean": {k: round(sum(v) / len(v)) for k, v in by_arm.items()},
                      "headers": sum(1 for r in doc["rows"] if r["work"]["header"]), "model_calls": 0}, indent=1))


if __name__ == "__main__":
    main()
