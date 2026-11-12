"""Mechanically assign rung-orphaned papers (in a generator's program but no rung claimed
them) by cosine to rung floor centroids - the same dot product the router fires. The model
wrote the symbols; the mechanics close the coverage. Provenance recorded on the rung.

Usage: assign_orphans.py <key>
"""
import io
import json
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
SD = ROOT / "collaborator_corpus" / "_structural"

from laplace.representation import embed_router


def canon(pid):
    m = re.match(r"(W\d+)", pid.strip())
    return m.group(1) if m else pid.strip()


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


def main(key):
    reg_path = SD / f"{key}_regraded.json"
    reg = json.loads(reg_path.read_text(encoding="utf-8"))
    struct = json.loads((SD / f"{key}.json").read_text(encoding="utf-8"))
    ladders = {}
    for lad in struct["ladders"]:
        ladders.setdefault(canon(lad["id"]), lad)

    def floor_text(cid):
        lad = ladders.get(cid)
        if not lad:
            return None
        techs = "; ".join(t.get("statement", t.get("name", "")) for t in lad.get("techniques", []))
        res = "; ".join(r.get("claim", "") for r in lad.get("results", []))
        return f"{lad.get('title', '')}. {techs}. {res}"

    backend = embed_router.get_backend()
    fixed = 0
    for gkey, cov in (reg.get("_coverage") or {}).items():
        missing = cov.get("missing_from_rungs") or []
        if not missing:
            continue
        # locate the generator by matching coverage key order to generator order
        idx = list(reg["_coverage"].keys()).index(gkey)
        gen = reg["generators"][idx]
        rungs = gen.get("rungs") or []
        if not rungs:
            continue
        texts, keys = [], []
        for r in rungs:
            for p in r["papers"]:
                ft = floor_text(p)
                if ft:
                    keys.append(("paper", p)); texts.append(ft)
        for p in missing:
            ft = floor_text(p)
            if ft:
                keys.append(("orphan", p)); texts.append(ft)
        vecs = backend.embed(texts)
        V = {k: unit(v) for k, v in zip(keys, vecs)}
        cents = {r["name"]: centroid([V[("paper", p)] for p in r["papers"] if ("paper", p) in V])
                 for r in rungs}
        for p in missing:
            if ("orphan", p) not in V:
                print(f"  {gkey}: {p} has NO ladder - left as recorded grit")
                continue
            scores = sorted(((dot(V[("orphan", p)], c), n) for n, c in cents.items() if c),
                            reverse=True)
            best, second = scores[0], (scores[1] if len(scores) > 1 else (float("nan"), "-"))
            rung = next(r for r in rungs if r["name"] == best[1])
            rung["papers"].append(p)
            rung.setdefault("_mechanical_assignments", []).append({
                "paper": p, "cos": round(best[0], 3),
                "margin": round(best[0] - second[0], 3) if second[1] != "-" else None,
                "runner_up": second[1],
                "why": "rung-orphan closed by cosine to rung floor centroid (assign_orphans.py)"})
            cov["missing_from_rungs"] = [x for x in cov["missing_from_rungs"] if x != p]
            cov["assigned"] = cov.get("assigned", 0) + 1
            fixed += 1
            print(f"  {gkey}: {p} -> {best[1]} (cos {best[0]:.3f}, margin {best[0]-second[0]:+.3f} vs {second[1]})")
    if fixed:
        reg_path.write_text(json.dumps(reg, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"{key}: {fixed} orphan(s) assigned mechanically, file updated")
    else:
        print(f"{key}: no rung-orphans to assign")


if __name__ == "__main__":
    main(sys.argv[1])
