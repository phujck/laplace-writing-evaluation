"""Mechanically merge the refine-essences round into mccaul_regraded.json and emit
round-3 closure files for the CHANGED NEIGHBOURHOOD only (verify-at-grade):
- the 4 rewritten rung essences (floors unchanged, labels new),
- the 2 promoted superoscillation rungs (new paper floors),
- all 6 generators (every split generator's floor = its child rung essences, and
  at least one child essence changed for each; open-q is enrich-mode, paper floor,
  but its own label changed).
No model. The model wrote the symbols (wf_refine_essences.mjs); this writes the merge,
the weights, and the blind files.
"""
import json, re, itertools, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SD = ROOT / "collaborator_corpus" / "_structural"

def canon(pid: str) -> str:
    m = re.match(r"(W\d+)", pid.strip())
    return m.group(1) if m else pid.strip()

def main(refine_raw_path: str):
    struct = json.loads((SD / "mccaul.json").read_text(encoding="utf-8"))
    reg = json.loads((SD / "mccaul_regraded.json").read_text(encoding="utf-8"))
    raw = json.loads(Path(refine_raw_path).read_text(encoding="utf-8"))
    refined = raw["result"]["refined"]

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

    man = {e["idx"]: (e["generator"], e["rung"]) for e in reg["_closure_manifest"]}
    def gen_by_label(label):
        return next(g for g in reg["generators"] if g["label"] == label)

    log = []
    for r in refined:
        gl, rn = man[r["idx"]]
        g = gen_by_label(gl)
        if r["idx"] == 13:  # superoscillations: promote to split
            g["essence"] = r["new_essence"]
            prog = set(g.pop("papers"))
            g.pop("paper_edges", None)
            g["mode"] = "split"
            g["rungs"] = []
            assigned = set()
            for rr in r["rungs"]:
                mem = sorted({canon(x) for x in rr["papers"]})
                assigned |= set(mem)
                mass = sum(len(tech_names(a) & tech_names(b)) +
                           sum(1 for t, cm in clusters if a in cm and b in cm)
                           for a, b in itertools.combinations(mem, 2))
                g["rungs"].append({"name": rr["name"], "essence": rr["essence"], "papers": mem,
                                   "n_with_ladder": sum(1 for c in mem if c in ladders),
                                   "paper_edges": paper_edges(mem), "coupling_mass": mass})
            log.append(f"promote superoscillations: 2 rungs, coverage "
                       f"{'exact' if prog == assigned else f'MISMATCH {sorted(prog ^ assigned)}'}")
        elif rn:  # rung essence rewrite
            rr = next(x for x in g["rungs"] if x["name"] == rn)
            rr["essence"] = r["new_essence"]
            log.append(f"essence: {rn}")
        else:     # generator essence rewrite
            g["essence"] = r["new_essence"]
            log.append(f"essence: gen {gl[:45]}")

    reg["_refine_round2"] = [{"idx": r["idx"], "note": r["note"]} for r in refined]
    reg["_provenance"] += (" | round 2 refine (wf_refine_essences.mjs) merged by apply_refine.py: "
                           "8 essences rewritten to the v2 gap specs, superoscillations promoted to "
                           "2 rungs; weights recomputed mechanically.")

    # ---- round-3 closure files: the changed neighbourhood ----
    floors, labels, manifest, idx = [], [], [], 0

    def paper_floor(members):
        fl = [{"techniques": sorted(tech_names(c)),
               "results": [x["claim"] for x in ladders[c].get("results", [])]}
              for c in members if c in ladders]
        return {"items": fl, "n_members_without_ladder": sum(1 for c in members if c not in ladders)}

    retest_rungs = [("Quantum-classical unification: a single dynamical framework", "kvn-operator-route"),
                    ("Laser-driven control of correlated matter: prescriptive and inverse approaches", "forward-prescriptive-control"),
                    ("Quantum simulation and computation: efficient algorithms for spectra and dynamics", "imaginary-time-to-unitary-mapping"),
                    ("Reservoir and machine learning with quantum/photonic substrates", "photonic-feature-space-ml"),
                    ("Superoscillations as a spectroscopic and confinement resource", "waveform-generation-and-phase-optimisation"),
                    ("Superoscillations as a spectroscopic and confinement resource", "deployment-spectroscopy-and-confinement")]
    for gl, rn in retest_rungs:
        rr = next(x for x in gen_by_label(gl)["rungs"] if x["name"] == rn)
        floors.append({"idx": idx, "kind": "rung->papers", "floor": paper_floor(rr["papers"])})
        labels.append({"idx": idx, "kind": "rung->papers", "name": rn, "stated": rr["essence"], "parent": gl})
        manifest.append({"idx": idx, "generator": gl, "rung": rn})
        idx += 1
    for g in reg["generators"]:
        if g["mode"] == "split":
            fl = {"child_essences": [{"name": r["name"], "essence": r["essence"]} for r in g["rungs"]]}
            floors.append({"idx": idx, "kind": "generator->rungs", "floor": fl})
        else:
            floors.append({"idx": idx, "kind": "generator->papers", "floor": paper_floor(g["papers"])})
        labels.append({"idx": idx, "kind": floors[-1]["kind"], "name": g["label"], "stated": g["essence"], "parent": None})
        manifest.append({"idx": idx, "generator": g["label"], "rung": None})
        idx += 1

    reg["_closure_manifest_v3"] = manifest
    (SD / "mccaul_regraded.json").write_text(json.dumps(reg, indent=1, ensure_ascii=False), encoding="utf-8")
    (SD / "_closure_floors_v3.json").write_text(json.dumps(floors, indent=1, ensure_ascii=False), encoding="utf-8")
    (SD / "_closure_labels_v3.json").write_text(json.dumps(labels, indent=1, ensure_ascii=False), encoding="utf-8")
    (SD / "_refine_raw_round2.json").write_text(json.dumps(raw["result"], indent=1, ensure_ascii=False), encoding="utf-8")
    for line in log:
        print("merged -", line)
    print(f"round-3 closure entries: {idx} (6 rungs + 6 generators)")

if __name__ == "__main__":
    main(sys.argv[1])
