"""Packet X step 3 (CPU, zero model calls, no gold): statements and witnesses from the extraction cache.

For every unit: its statement (subject + the four fields) from the cached response of the request that carried it,
and its witnesses. A support quote is a witness when, after normalising whitespace (any run -> one space) and quote
characters (curly single/double quotes and primes -> ASCII ' and ") in both the quote and the unit, it is a substring
of the unit's own text; it is stored with its character offsets [start, end) in the DOCUMENT text. Nothing else is
normalised (case, dashes, ellipses and punctuation must match). A quote that is not a span of its unit is dropped and
counted (with a diagnostic: whether it is a span elsewhere in the same document, and whether it is a span after
casefolding). A statement with no surviving quote is kept and flagged. A unit whose request has no cached response
has statement null.

    scripts/laplace-python .../x3_witness.py news
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

LAPLACE = Path("/home/phujck/VScodeProjects/laplace")
HERE = LAPLACE / "evidence/BENCH_RECOVERY_2026-11-09/stage3/X"
sys.path.insert(0, str(HERE / "scripts"))
sys.path.insert(0, str(LAPLACE / "evidence/BENCH_RECOVERY_2026-11-09/stage3/G/scripts"))

FIELDS = ("subject", "object", "mechanism", "conditions", "consequences")
QUOTE_MAP = {"‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'", "´": "'", "`": "'",
             "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"', "«": '"', "»": '"'}


def norm_map(text: str, fold: bool = False):
    """Normalised text and, for every normalised character, its index in ``text``."""
    out, idx, prev_space = [], [], True
    for i, ch in enumerate(text):
        if ch.isspace():
            if not prev_space:
                out.append(" ")
                idx.append(i)
            prev_space = True
            continue
        c = QUOTE_MAP.get(ch, ch)
        if fold:
            c = c.casefold()
        for x in c:
            out.append(x)
            idx.append(i)
        prev_space = False
    s = "".join(out)
    if s.endswith(" "):
        s, idx = s[:-1], idx[:-1]
    return s, idx


def find_span(quote: str, text: str, fold: bool = False):
    q, _ = norm_map(quote, fold)
    q = q.strip()
    if not q:
        return None
    t, idx = norm_map(text, fold)
    k = t.find(q)
    if k < 0:
        return None
    return idx[k], idx[k + len(q) - 1] + 1


def doc_texts(corpus: str) -> dict:
    if corpus == "news":
        from x1_units import news_docs
        return {d["doc"]: d["text"] for d in news_docs()}
    from x1_units import frames_docs
    return {d["doc"]: d["text"] for d in frames_docs()}


def main(corpus: str) -> None:
    from x2_extract import load_reader, build_requests
    mc = load_reader("claude", None, None)
    reqs = build_requests(corpus, mc)
    cache = HERE / "cache" / corpus
    units = json.loads((HERE / "out" / f"{corpus}_units.json").read_text())
    texts = doc_texts(corpus)
    span_of = {u["unit_id"]: (row["doc"], u["start"], u["end"]) for row in units["docs"] for u in row["units"]}
    stmt_of, req_of = {}, {}
    req_status = Counter()
    for r in reqs:
        path = cache / f"{r['request_sha256']}.json"
        if not path.exists():
            req_status["no cached response"] += 1
            continue
        res = json.loads(path.read_text())
        sts = res["response"]["statements"]
        got = [s.get("unit_id") for s in sts]
        if got == r["unit_ids"]:
            req_status["ids in order"] += 1
            pairs = list(zip(r["unit_ids"], sts))
        elif sorted(got) == sorted(r["unit_ids"]):
            req_status["ids permuted (matched by id)"] += 1
            by = {s["unit_id"]: s for s in sts}
            pairs = [(u, by[u]) for u in r["unit_ids"]]
        else:                                  # schema fixes the count; ids garbled -> match by position
            req_status["ids differ (matched by position)"] += 1
            pairs = list(zip(r["unit_ids"], sts))
        for uid, s in pairs:
            stmt_of[uid] = s
            req_of[uid] = r["request_sha256"]
    out_rows = []
    c = Counter()
    field_filled = Counter()
    for row in units["docs"]:
        text = texts[row["doc"]]
        assert hashlib.sha256(text.encode()).hexdigest() == row["text_sha256"]
        for u in row["units"]:
            uid, s0, e0 = u["unit_id"], u["start"], u["end"]
            utext = text[s0:e0]
            st = stmt_of.get(uid)
            rec = {"unit_id": uid, "doc": row["doc"], "start": s0, "end": e0}
            c["units"] += 1
            if st is None:
                rec["statement"] = None
                c["units without statement"] += 1
                out_rows.append(rec)
                continue
            c["statements"] += 1
            rec["statement"] = {f: (st.get(f) or "").strip() for f in FIELDS}
            for f in FIELDS:
                field_filled[f] += bool(rec["statement"][f])
            wit, dropped = [], []
            for q in st.get("support_quotes") or []:
                c["quotes"] += 1
                sp = find_span(q, utext)
                if sp is not None:
                    a, b = s0 + sp[0], s0 + sp[1]
                    if any(w["start"] == a and w["end"] == b for w in wit):
                        c["quotes duplicate"] += 1
                        continue
                    exact = q.strip() == text[a:b]
                    c["quotes kept"] += 1
                    c["quotes kept exact (no normalisation needed)"] += exact
                    wit.append({"start": a, "end": b, "text": text[a:b]})
                    continue
                c["quotes dropped"] += 1
                elsewhere = find_span(q, text)
                folded = find_span(q, utext, fold=True)
                why = ("span elsewhere in the document" if elsewhere else
                       "span after casefold" if folded else "not a span")
                c[f"dropped: {why}"] += 1
                dropped.append({"quote": q, "why": why})
            rec["witnesses"] = wit
            rec["quotes_dropped"] = dropped
            rec["no_witness"] = not wit
            c["statements with no surviving witness"] += not wit
            c["statements with 0 quotes returned"] += not (st.get("support_quotes") or [])
            out_rows.append(rec)
    path = HERE / "out" / f"{corpus}_statements.jsonl"
    with path.open("w") as fh:
        for r in out_rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    n_st = c["statements"] or 1
    n_q = c["quotes"] or 1
    report = {"corpus": corpus, "requests": len(reqs), "request_status": dict(req_status), "counts": dict(c),
              "rates": {"units_with_statement": round(c["statements"] / c["units"], 4),
                        "quotes_kept": round(c["quotes kept"] / n_q, 4),
                        "quotes_dropped": round(c["quotes dropped"] / n_q, 4),
                        "statements_flagged_no_witness": round(c["statements with no surviving witness"] / n_st, 4),
                        "quotes_per_statement": round(c["quotes"] / n_st, 3),
                        "witnesses_per_statement": round(c["quotes kept"] / n_st, 3)},
              "field_filled": {f: round(field_filled[f] / n_st, 4) for f in FIELDS},
              "file": str(path)}
    (HERE / "out" / f"{corpus}_witness_report.json").write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
