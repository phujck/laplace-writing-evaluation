"""Emit the mechanical insert-middle gens args (idx/mode/key) per wave-2b corpus.
Mode rule (banked): members <= 5 -> enrich (already at ladder ratio), else split."""
import io
import json
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def kebab(label, used):
    k = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    k = "-".join(k.split("-")[:4]) or "gen"
    base, n = k, 2
    while k in used:
        k, n = f"{base}-{n}", n + 1
    used.add(k)
    return k


for key in sys.argv[1:]:
    d = json.load(open(f"collaborator_corpus/_structural/{key}.json", encoding="utf-8"))
    prog = (d.get("upfold") or {}).get("program") or d.get("program") or []
    used = set()
    gens = [{"idx": i, "mode": ("enrich" if len(g.get("papers") or []) <= 5 else "split"),
             "key": kebab(g.get("generator", f"g{i}"), used)}
            for i, g in enumerate(prog)]
    print(key, json.dumps(gens, ensure_ascii=False))
