"""The mechanical closure gate, generalised to any freshly-sharded lens (gen -> papers, no
rungs yet) - and reframed per his correction (2026-06-11): SOME BLEED IS FINE, that's
reconstruction; the DEGREE of bleed is a geometry reading, not a defect list. A linking/
envelope node SHOULD sit near its siblings (near-zero margin = its role's signature); a
tight cluster should not. The gate therefore reports the bleed spectrum and flags only the
EXTREMES for the intelligent stage: LOW-FIT (the label does not sit on its own floor) and
deep negative margin (the label sits closer to a SIBLING's floor than its own - likely a
mis-assignment or a missing middle). The flagged set = the residue; the residue is RECURRED
(judged, inserted, re-gated), and each recursion makes the next pass more mechanical.

Usage: python mech_closure_lens.py <shard.json> [more shards...]
"""
import json, re, sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
from laplace.representation import embed_router

def canon(pid):
    m = re.match(r"(W\d+)", str(pid).strip())
    return m.group(1) if m else str(pid).strip()

def unit(v):
    s = sum(x * x for x in v) ** 0.5
    return [x / s for x in v] if s else v

def centroid(vecs):
    if not vecs:
        return None
    n = len(vecs[0])
    return unit([sum(v[i] for v in vecs) / len(vecs) for i in range(n)])

def dot(a, b):
    return sum(x * y for x, y in zip(a, b))

backend = embed_router.get_backend()

for path in sys.argv[1:]:
    shard = json.loads(Path(path).read_text(encoding="utf-8"))
    key = shard.get("_key") or shard.get("key")
    ladders = {}
    for lad in shard.get("ladders", []):
        ladders.setdefault(canon(lad.get("id", "")), lad)
    program = (shard.get("upfold") or shard).get("program") or shard.get("program", [])

    def floor_text(cid):
        lad = ladders.get(cid)
        if not lad:
            return None
        techs = "; ".join(t.get("statement", t.get("name", "")) for t in lad.get("techniques", []))
        res = "; ".join(r.get("claim", "") for r in lad.get("results", []))
        return f"{lad.get('title','')}. {lad.get('meta_goal','')}. {techs}. {res}"

    texts, keys = [], []
    for g in program:
        for p in g.get("papers", []):
            c = canon(p)
            ft = floor_text(c)
            if ft and ("paper", c) not in keys:
                keys.append(("paper", c)); texts.append(ft)
        keys.append(("gen", g["generator"])); texts.append(f"{g['generator']}. {g.get('why','')}")
    V = {k: unit(v) for k, v in zip(keys, backend.embed(texts))}

    cents = {}
    for g in program:
        mem = [V[("paper", canon(p))] for p in g.get("papers", []) if ("paper", canon(p)) in V]
        cents[g["generator"]] = centroid(mem)

    print(f"\n=== {key}: {len(program)} generators - the bleed spectrum (geometry, not defects) ===")
    print(f"{'generator':<62} {'cos_own':>8} {'margin':>8}  reading")
    flagged = []
    for g in program:
        own = cents[g["generator"]]
        if own is None:
            print(f"{g['generator'][:60]:<62} {'-':>8} {'-':>8}  NO-FLOOR (all members ladderless)")
            flagged.append((g["generator"], "no-floor"))
            continue
        gv = V[("gen", g["generator"])]
        cos_own = dot(gv, own)
        sibs = [(n, dot(gv, c)) for n, c in cents.items() if n != g["generator"] and c is not None]
        best_sib, best = max(sibs, key=lambda t: t[1]) if sibs else ("", float("nan"))
        margin = cos_own - best
        if cos_own < 0.50:
            reading = "LOW-FIT <- judge"
            flagged.append((g["generator"], "low-fit"))
        elif margin < -0.02:
            reading = f"INVERTED toward [{best_sib[:30]}] <- judge"
            flagged.append((g["generator"], "inverted"))
        elif margin < 0.04:
            reading = f"high bleed toward [{best_sib[:30]}] (role? linking node or shared program)"
        else:
            reading = "tight"
        print(f"{g['generator'][:60]:<62} {cos_own:>8.3f} {margin:>8.3f}  {reading}")
    print(f"flagged for the intelligent stage: {len(flagged)}" + (f" -> {[f[0][:40] for f in flagged]}" if flagged else " (none - the lexical judges stay home)"))
