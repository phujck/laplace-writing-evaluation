"""Packet I: derive reading-variant rows from a contexts file (no model call, no gold). The passages are unchanged;
only the instruction (and schema) changes, identically for every arm. Variants: rules, notes, notes2, table, table2
(i_lib.variant_prompt). 'table*' hand the reader the compiled requirements (I/ctx/obligations.pkl: need text, bound
outlet and date) - the same requirements for every arm, since they come from the question, not from a selector.

    i_variants.py CONTEXTS.json VARIANT ARMS(comma) OUT.json [SAMPLE]
SAMPLE k > 0: the same prompt bytes under purpose 'reader-resample-k' (its own cache identity), arm suffix '#sk',
for a majority-of-three reading (i_vote.py).
"""
import json
import pickle
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import i_lib as L  # noqa: E402

SCHEMA = {"rules": None, "notes": "notes", "notes2": "notes", "table": "table", "table2": "table"}


def main(src, variant, arms, out, sample=0):
    sample = int(sample)
    arms = set(arms.split(","))
    obl = pickle.load(open(L.I / "ctx/obligations.pkl", "rb"))
    rows = []
    for r in L.load_contexts(src)["rows"]:
        if r["arm"] not in arms:
            continue
        reqs = [{"id": o["id"], "need": o["need"], "outlet": o["slots"].get("source", "<unknown>"),
                 "date": o["slots"].get("date", "<unknown>")} for o in obl[r["qid"]]["obligations"]]
        prompt = L.variant_prompt(variant, r["question"], r["passages"], reqs)
        rows.append({"qid": r["qid"], "arm": f"{r['arm']}+{variant}" + (f"#s{sample}" if sample else ""),
                     "question": r["question"],
                     "stratum": r.get("stratum"), "passages": r["passages"], "context_tokens": r["context_tokens"],
                     "prompt": prompt, "schema": SCHEMA[variant],
                     "purpose": "reader" if not sample else f"reader-resample-{sample}",
                     "diag_covered": r.get("diag_covered")})
    Path(out).write_text(json.dumps({"rows": rows, "variant": variant, "source": src}, ensure_ascii=False) + "\n")
    print(variant, len(rows))


if __name__ == "__main__":
    main(*sys.argv[1:6])
