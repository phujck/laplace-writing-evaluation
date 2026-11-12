"""Packet X step 4 + 5b (CPU, zero model calls, no gold): the canonicaliser over the extracted statements, and the
relational incidence.

This is relational/tuples.py:build_extract (tuples.py:689-793) with the news layout of the card path
(build_multihoprag, tuples.py:339-385) in place of the LongMem/QASPER layout, every rule reused by import:
* parts = (subject, object, mechanism, conditions, consequences) of the statement (tuples.STATEMENT_PARTS:595),
  each read by entities.extract with one CaseStats over the unit texts and the statement fields (tuples.py:698-710);
* registry = entities.Registry(FLOOR=2).build over one registry unit per piece, outlets excluded by
  entities.outlet_aliases(sources) as on the card path (tuples.py:342-349);
* polarity = polarity.decide over mechanism then consequences (tuples.py:723-726);
* m_code = nearest banked centroid of derived/tuples/mechanism_codebook_v1 (K=128) below its support radius, on the
  mechanism FIELD's vector (tuples.py:715-722). The vector is x5_embed's GPU fp16 row of the same imported encoder
  (build_extract encodes on CPU; same graph, fp16 rounding only);
* e_subj prefers the entity in the subject field, e_obj the best-ranked of the rest, else a quantity kind
  (tuples._assemble:214-265, subject_part='subject');
* time and source come from the article, never the model: t_coarse = publication month, t_fine = publication day,
  source = outlet (tuples.py:375-380).
A piece with no statement is a row with every statement axis <unknown> and statement=false (tuples.py:588-589).

Incidence (scipy sparse CSR, pieces in statements.jsonl order): piece x entity (every mention resolved to a registry
entity, any field), piece x source (outlet), piece x day, piece x document.

    scripts/laplace-python .../x4_tuples.py news
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

LAPLACE = Path("/home/phujck/VScodeProjects/laplace")
RF = LAPLACE / "synthetics papers" / "relational-frontend"
HERE = LAPLACE / "evidence/BENCH_RECOVERY_2026-11-09/stage3/X"
sys.path.insert(0, str(RF / "src"))
sys.path.insert(0, str(HERE / "scripts"))
sys.path.insert(0, str(LAPLACE / "evidence/BENCH_RECOVERY_2026-11-09/stage3/G/scripts"))

from relational import codebook as cb      # noqa: E402
from relational import entities as ent     # noqa: E402
from relational import polarity as pol     # noqa: E402
from relational import tuples as T         # noqa: E402

FIELDS = ("subject", "object", "mechanism", "conditions", "consequences")
assert FIELDS == T.STATEMENT_PARTS


def main(corpus: str) -> None:
    from scipy import sparse
    from x1_units import news_docs, frames_docs
    t0 = time.perf_counter()
    news = corpus == "news"
    docs = {d["doc"]: d for d in (news_docs() if news else frames_docs())}
    if not news:                           # tuples.TIME_AXES['frames'] (extract.py:682-683): heading, ordinal, page
        for d in docs.values():
            d["source"] = d["page_title"]
    rows_in = [json.loads(line) for line in (HERE / "out" / f"{corpus}_statements.jsonl").read_text().splitlines()]
    V = np.load(HERE / "out" / f"{corpus}_field_vectors.f16.npy")
    mask = np.load(HERE / "out" / f"{corpus}_field_mask.npy")
    assert V.shape[0] == len(rows_in)
    dec = ent.decode_entities
    stats = ent.CaseStats()
    texts_of = {}
    for r in rows_in:
        d = docs[r["doc"]]
        stats.add(dec(d["text"][r["start"]:r["end"]]))
        st = r.get("statement")
        texts = [dec((st or {}).get(f) or "") for f in FIELDS]
        texts_of[r["unit_id"]] = texts
        for t in texts:
            stats.add(t)
    sources = sorted({d["source"] for d in docs.values()})
    if news:
        days = sorted({d["published_at"][:10] for d in docs.values()})
        months = sorted({d["published_at"][:7] for d in docs.values()})
        outlets = ent.outlet_aliases(sources)
    else:                                  # text path: no outlet exclusion (tuples.build_text:532)
        months = sorted({d["heading"] for d in docs.values()})
        days = sorted({r["unit_id"].rsplit(":", 1)[1] for r in rows_in})
        outlets = set()
    reg_units = [{"id": r["unit_id"], "parts": [ent.extract(t, stats) for t in texts_of[r["unit_id"]]],
                  "texts": texts_of[r["unit_id"]]} for r in rows_in]
    reg_obj = ent.Registry(T.FLOOR)
    registry = reg_obj.build(reg_units, outlets)
    C, cbdoc = T._load_codebook()
    mi = FIELDS.index("mechanism")
    has_mech = mask[:, mi]
    codes, cos = cb.assign(V[:, mi].astype(np.float32), C, cbdoc["support_radius_cosine"])
    assembled = []
    for i, (r, ru) in enumerate(zip(rows_in, reg_units)):
        d = docs[r["doc"]]
        st = r.get("statement")
        stamp = d.get("published_at") or ""
        tc, tf = ((stamp[:7] or T.UNKNOWN, stamp[:10] or T.UNKNOWN) if news else
                  (d["heading"], r["unit_id"].rsplit(":", 1)[1]))
        prec = (pol.decide([("mechanism", texts_of[r["unit_id"]][mi]),
                            ("consequences", texts_of[r["unit_id"]][FIELDS.index("consequences")])])
                if st else {"polarity": T.UNKNOWN, "cue": None, "decided_by": None, "matches": {}})
        code = int(codes[i]) if has_mech[i] else -1
        assembled.append({"id": r["unit_id"], "local_alias": ru["local_alias"],
                          "parts": list(zip(FIELDS, ru["texts"], ru["parts"])),
                          "t_coarse": tc, "t_fine": tf,
                          "source": d["source"] or T.UNKNOWN, "polarity": prec, "m_code": code,
                          "m_cos": round(float(cos[i]), 6) if has_mech[i] else None})
    rows = T._assemble(assembled, reg_obj, registry, "mechanism", ("mechanism", "consequences", "object"),
                       subject_part="subject")
    for r, ri in zip(rows, rows_in):
        named = {m["canonical"] for m in r["mentions"] if m["field"] == "subject" and m["status"] == "entity"}
        r.update({"unit_id": ri["unit_id"], "doc": ri["doc"], "statement": ri.get("statement") is not None,
                  "e_subj_from": "subject" if r["e_subj"] in named else ("spread" if r["e_subj"] != T.UNKNOWN
                                                                          else None)})
    entity_vocab = T._entity_vocab(registry) + [T.RARE]
    vocabs = {"t_coarse": months + [T.UNKNOWN], "t_fine": days + [T.UNKNOWN], "source": sources + [T.UNKNOWN],
              "e_subj": entity_vocab + [T.UNKNOWN], "m_code": [f"m{c}" for c in range(cbdoc["K"])] + [T.UNKNOWN],
              "polarity": list(pol.CLASSES) + [T.UNKNOWN], "e_obj": entity_vocab + list(T.QTY_KINDS) + [T.UNKNOWN]}
    T._encode_rows(rows, vocabs)
    coverage, entropy = T.factor_tables(rows, vocabs)
    stated = [r for r in rows if r["statement"]]
    coverage_stated, _ = T.factor_tables(stated, vocabs) if stated else ({}, {})
    n = len(rows)
    # ---- incidence
    ent_ids = registry and {e["key"]: k for k, e in enumerate(registry["entities"])}
    er, ec = [], []
    for i, r in enumerate(rows):
        seen = set()
        for m in r["mentions"]:
            if m["status"] == "entity" and m["canonical"] in ent_ids:
                k = ent_ids[m["canonical"]]
                if k not in seen:
                    seen.add(k)
                    er.append(i)
                    ec.append(k)
    P_E = sparse.csr_matrix((np.ones(len(er), np.int8), (er, ec)), shape=(n, len(ent_ids)))
    src_ix = {s: k for k, s in enumerate(sources)}
    day_ix = {s: k for k, s in enumerate(days)}
    doc_ix = {k: i for i, k in enumerate(docs)}
    ndoc = len(doc_ix)
    P_S = sparse.csr_matrix((np.ones(n, np.int8), (np.arange(n), [src_ix[docs[r["doc"]]["source"]] for r in rows])),
                            shape=(n, len(sources)))
    if news:
        P_D = sparse.csr_matrix((np.ones(n, np.int8), (np.arange(n),
                                                       [day_ix[docs[r["doc"]]["published_at"][:10]] for r in rows])),
                                shape=(n, len(days)))
    else:                                  # FRAMES has no time axis: the page is the coarse group instead
        page_ix = {k: i for i, k in enumerate(sorted({d["page"] for d in docs.values()}))}
        P_D = sparse.csr_matrix((np.ones(n, np.int8), (np.arange(n), [page_ix[docs[r["doc"]]["page"]] for r in rows])),
                                shape=(n, len(page_ix)))
        days = sorted(page_ix, key=page_ix.get)
    P_A = sparse.csr_matrix((np.ones(n, np.int8), (np.arange(n), [doc_ix[r["doc"]] for r in rows])), shape=(n, ndoc))
    sparse.save_npz(HERE / "out" / f"{corpus}_incidence_entity.npz", P_E)
    sparse.save_npz(HERE / "out" / f"{corpus}_incidence_source.npz", P_S)
    sparse.save_npz(HERE / "out" / f"{corpus}_incidence_{'day' if news else 'page'}.npz", P_D)
    sparse.save_npz(HERE / "out" / f"{corpus}_incidence_document.npz", P_A)
    deg = np.asarray(P_E.sum(axis=0)).ravel()
    hub_cut = 0.01 * n
    keys = [e["key"] for e in registry["entities"]]
    hubs = sorted(((keys[k], int(deg[k])) for k in np.flatnonzero(deg > hub_cut)), key=lambda kv: -kv[1])
    subj_counts = Counter(r["e_subj"] for r in stated)
    hubs_subj = [(k, c) for k, c in subj_counts.most_common() if k not in (T.UNKNOWN, T.RARE) and c > hub_cut]
    # ---- the per-piece file other packets load
    with (HERE / "out" / f"{corpus}_pieces.jsonl").open("w") as fh:
        for r, ri in zip(rows, rows_in):
            fh.write(json.dumps({
                "unit_id": ri["unit_id"], "doc": ri["doc"], "start": ri["start"], "end": ri["end"],
                "statement": ri.get("statement"), "witnesses": ri.get("witnesses", []),
                "no_witness": ri.get("no_witness"),
                "tuple": {a: (r[a] if a != "m_code" else (f"m{r['m_code']}" if r["m_code"] >= 0 else T.UNKNOWN))
                          for a in T.AXES},
                "codes": r["codes"], "polarity_cue": r["polarity_cue"], "e_obj_from": r["e_obj_from"],
                "e_subj_from": r["e_subj_from"], "m_cos": r["m_cos"],
                "entities": sorted({m["canonical"] for m in r["mentions"] if m["status"] == "entity"})},
                ensure_ascii=False) + "\n")
    (HERE / "out" / f"{corpus}_vocabularies.json").write_text(json.dumps(
        {"axes": list(T.AXES), "vocabularies": vocabs, "entity_columns": keys, "source_columns": sources,
         ("day_columns" if news else "page_columns"): days, "document_columns": list(doc_ix)},
        ensure_ascii=False) + "\n")
    report = {"corpus": corpus, "pieces": n, "pieces_with_statement": len(stated),
              "coverage_by_axis_all_pieces": coverage, "coverage_by_axis_pieces_with_statement": coverage_stated,
              "entropy_by_axis": entropy,
              "registry": {k: registry[k] for k in ("size", "floor", "keys_before_floor", "mentions_total",
                                                    "mean_aliases_per_entity", "entities_with_alias")},
              "polarity": dict(sorted(Counter(r["polarity"] for r in rows).items())),
              "e_subj_from": dict(Counter(str(r["e_subj_from"]) for r in stated)),
              "e_obj_from": dict(Counter(str(r["e_obj_from"]) for r in stated)),
              "m_code_unknown_with_mechanism": int(((codes < 0) & has_mech).sum()),
              "mechanism_field_empty": int((~has_mech).sum()),
              "hub_rule": "registry entity mentioned (any field) on more than 1% of pieces",
              "hub_cut_pieces": hub_cut, "hubs_any_mention": hubs, "hubs_as_e_subj": hubs_subj,
              "incidence": {"entity": list(P_E.shape) + [int(P_E.nnz)], "source": list(P_S.shape),
                            ("day" if news else "page"): list(P_D.shape), "document": list(P_A.shape),
                            "pieces_with_no_entity": int((np.asarray(P_E.sum(axis=1)).ravel() == 0).sum()),
                            "entities_per_piece_mean": round(P_E.nnz / n, 3)},
              "seconds": round(time.perf_counter() - t0, 1)}
    (HERE / "out" / f"{corpus}_tuples_report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({k: report[k] for k in ("pieces", "pieces_with_statement", "registry", "polarity",
                                             "hubs_any_mention", "incidence", "seconds")}, ensure_ascii=False))
    print(json.dumps({a: {k: coverage_stated[a][k] for k in ("known", "unknown", "rare")} for a in T.AXES}))


if __name__ == "__main__":
    main(sys.argv[1])
