"""Mechanically merge a promote-node round (one flat generator -> split with rungs)
into mccaul_regraded.json and emit the mini-gate files for that neighbourhood only.
No model: the model wrote essences/assignments; this writes the merge + weights + blind files.
"""
import json, re, itertools, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SD = ROOT / "collaborator_corpus" / "_structural"

def canon(pid):
    m = re.match(r"(W\d+)", pid.strip())
    return m.group(1) if m else pid.strip()

def main(raw_path):
    struct = json.loads((SD / "mccaul.json").read_text(encoding="utf-8"))
    reg = json.loads((SD / "mccaul_regraded.json").read_text(encoding="utf-8"))
    raw = json.loads(Path(raw_path).read_text(encoding="utf-8"))
    res = raw["result"]

    ladders = {}
    for lad in struct["ladders"]:
        ladders.setdefault(canon(lad["id"]), lad)
    clusters = [(c["technique"], {canon(x) for x in c["papers"]})
                for c in struct.get("technique_clusters", [])]

    def tech_names(cid):
        lad = ladders.get(cid)
        return {t["name"] for t in lad.get("techniques", [])} if lad else set()

    def paper_edges(members):
        edges = []
        for p in members:
            locs, w = {}, 0
            for q in members:
                if q == p:
                    continue
                sh = sorted(tech_names(p) & tech_names(q))
                sc = sorted(t for t, mem in clusters if p in mem and q in mem)
                if sh or sc:
                    locs[q] = {"clusters": sc, "handles": sh}
                    w += len(sh) + len(sc)
            edges.append({"paper": p, "w_raw": w, "locators": locs})
        mx = max((e["w_raw"] for e in edges), default=0)
        for e in edges:
            e["w"] = round(e["w_raw"] / mx, 3) if mx else 0.0
        return edges

    g = next(x for x in reg["generators"] if x["label"] == res["generator"])
    prog = set(g.pop("papers"))
    g.pop("paper_edges", None)
    g["mode"] = "split"
    g["essence"] = res["generator_essence"]
    g["rungs"] = []
    assigned = set()
    for rr in res["rungs"]:
        mem = sorted({canon(x) for x in rr["papers"]})
        assigned |= set(mem)
        mass = sum(len(tech_names(a) & tech_names(b)) +
                   sum(1 for t, cm in clusters if a in cm and b in cm)
                   for a, b in itertools.combinations(mem, 2))
        g["rungs"].append({"name": rr["name"], "essence": rr["essence"], "papers": mem,
                           "n_with_ladder": sum(1 for c in mem if c in ladders),
                           "paper_edges": paper_edges(mem), "coupling_mass": mass})
    print("coverage:", "exact" if prog == assigned else f"MISMATCH {sorted(prog ^ assigned)}")
    g["note"] += " | PROMOTED 2026-06-11 (v3 gate idx=7 major): " + res["note"][:400]
    reg["_provenance"] += " | promote round (wf_promote_node.mjs + apply_promote.py): open-q split into 3 rungs (2 branches + envelope; the zero-coupling grit paper became the envelope node)."

    floors, labels, idx = [], [], 0

    def paper_floor(members):
        fl = [{"techniques": sorted(tech_names(c)),
               "results": [x["claim"] for x in ladders[c].get("results", [])]}
              for c in members if c in ladders]
        return {"items": fl, "n_members_without_ladder": sum(1 for c in members if c not in ladders)}

    for rr in g["rungs"]:
        floors.append({"idx": idx, "kind": "rung->papers", "floor": paper_floor(rr["papers"])})
        labels.append({"idx": idx, "kind": "rung->papers", "name": rr["name"],
                       "stated": rr["essence"], "parent": g["label"]})
        idx += 1
    floors.append({"idx": idx, "kind": "generator->rungs",
                   "floor": {"child_essences": [{"name": r["name"], "essence": r["essence"]} for r in g["rungs"]]}})
    labels.append({"idx": idx, "kind": "generator->rungs", "name": g["label"], "stated": g["essence"], "parent": None})
    idx += 1

    (SD / "mccaul_regraded.json").write_text(json.dumps(reg, indent=1, ensure_ascii=False), encoding="utf-8")
    (SD / "_closure_floors_v4.json").write_text(json.dumps(floors, indent=1, ensure_ascii=False), encoding="utf-8")
    (SD / "_closure_labels_v4.json").write_text(json.dumps(labels, indent=1, ensure_ascii=False), encoding="utf-8")
    (SD / "_promote_raw_openq.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"merged: {g['label'][:50]} -> {len(g['rungs'])} rungs; mini-gate entries: {idx}")

if __name__ == "__main__":
    main(sys.argv[1])
