"""Mechanical assembly of the regraded structural ladder (no model).

Input:  the insert-middle workflow output (raw JSON), <key>.json (ladders + upfold).
Output: <key>_regraded.json         - generators -> rungs -> papers, with response-function
                                      essences (model-written symbols) and MECHANICAL weights
                                      (shared-technique structure, every entry locatored);
        _closure_floors_<key>.json  - blind floors at BOTH grades (rung->papers, generator->children);
        _closure_labels_<key>.json  - the stated essences the judge compares against.
        (key='mccaul' keeps the original v2 filenames.)

Usage:  assemble_regrade.py <raw.json> [key=mccaul]

The discipline (banked 2026-06-11): the model writes SYMBOLS, the mechanics compute STRENGTHS.
Generalised by key 2026-06-11 (wave 2): program/technique_clusters read from the top level
(mccaul shape) or under 'upfold' (wave-1 shape) - one operator, never a bespoke twin.
"""
import json, re, sys, itertools
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STRUCT_DIR = ROOT / "collaborator_corpus" / "_structural"

def canon(pid: str) -> str:
    m = re.match(r"(W\d+)", pid.strip())
    return m.group(1) if m else pid.strip()

def main(raw_path: str, key: str = "mccaul"):
    raw = json.loads(Path(raw_path).read_text(encoding="utf-8"))
    regraded = raw["result"]["regraded"]
    struct = json.loads((STRUCT_DIR / f"{key}.json").read_text(encoding="utf-8"))
    upfold = struct.get("upfold") or {}
    program_list = struct.get("program") or upfold.get("program") or []
    cluster_list = struct.get("technique_clusters") or upfold.get("technique_clusters") or []

    # canonical-id -> ladder (first occurrence wins; twins share a W-id)
    ladders = {}
    for lad in struct["ladders"]:
        ladders.setdefault(canon(lad["id"]), lad)

    # program membership per generator label (canonical, deduped); index fallback for
    # agents that renamed their generator instead of quoting the upfold label verbatim
    program = {p["generator"]: sorted({canon(x) for x in p["papers"]})
               for p in program_list}
    program_by_idx = {i: sorted({canon(x) for x in p["papers"]})
                      for i, p in enumerate(program_list)}

    def tech_names(cid):
        lad = ladders.get(cid)
        return {t["name"] for t in lad.get("techniques", [])} if lad else set()

    # canonical technique identities: the upfold's cross-linked technique_clusters.
    # Per-paper handles are independently generated and rarely string-match across papers;
    # the clusters ARE the canonicalisation the upfold paid intelligence for.
    clusters = [(c["technique"], {canon(x) for x in c["papers"]})
                for c in cluster_list]

    def paper_edges(members):
        """Mechanical rung->paper weights: w_raw = shared canonical techniques
        (co-membership in upfold technique_clusters) + exact shared handles.
        Locators name the sibling + the shared evidence. Auditable."""
        edges = []
        for p in members:
            locs, w = {}, 0
            for q in members:
                if q == p:
                    continue
                shared_h = sorted(tech_names(p) & tech_names(q))
                shared_c = sorted(t for t, mem in clusters if p in mem and q in mem)
                if shared_h or shared_c:
                    locs[q] = {"clusters": shared_c, "handles": shared_h}
                    w += len(shared_h) + len(shared_c)
            edges.append({"paper": p, "w_raw": w, "locators": locs})
        mx = max((e["w_raw"] for e in edges), default=0)
        for e in edges:
            e["w"] = round(e["w_raw"] / mx, 3) if mx else 0.0
        return edges

    out_gens, twin_collapse, coverage = [], {}, {}
    for g in regraded:
        mode = g["_mode"]
        # the label is ALWAYS the upfold's (the banked constraint), matched by index;
        # an agent that renamed its generator gets its rename recorded, never adopted
        idx_g = g.get("_idx")
        upfold_label = (program_list[idx_g]["generator"]
                        if idx_g is not None and idx_g < len(program_list) else g["generator"])
        label = upfold_label
        if g["generator"] != upfold_label:
            g.setdefault("_label_proposed", g["generator"])
        members_prog = program.get(label) or program_by_idx.get(idx_g, [])
        gen_rec = {"label": label, "essence": g["generator_essence"], "mode": mode,
                   "moves": g["moves"], "note": g["note"], "rungs": []}
        if g.get("_label_proposed"):
            gen_rec["label_proposed"] = g["_label_proposed"]
        if mode == "split":
            assigned_union = set()
            for r in g["rungs"]:
                raw_ids = r["papers"]
                mem = sorted({canon(x) for x in raw_ids})
                if len(raw_ids) != len(mem):
                    twin_collapse[f"{g['_key']}/{r['name']}"] = {"raw": len(raw_ids), "unique": len(mem)}
                assigned_union |= set(mem)
                gen_rec["rungs"].append({
                    "name": r["name"], "essence": r["essence"], "papers": mem,
                    "n_with_ladder": sum(1 for c in mem if c in ladders),
                    "paper_edges": paper_edges(mem),
                })
            # generator->rung coupling mass: total intra-rung shared-technique pair weight
            for rr in gen_rec["rungs"]:
                mass = sum(len(tech_names(a) & tech_names(b))
                           for a, b in itertools.combinations(rr["papers"], 2))
                rr["coupling_mass"] = mass
            missing = sorted(set(members_prog) - assigned_union)
            extra = sorted(assigned_union - set(members_prog))
            coverage[g["_key"]] = {"program": len(members_prog), "assigned": len(assigned_union),
                                   "missing_from_rungs": missing, "not_in_program": extra}
        else:  # enrich: no middle inserted; papers stay the generator's direct floor
            gen_rec["papers"] = members_prog
            gen_rec["paper_edges"] = paper_edges(members_prog)
            coverage[g["_key"]] = {"program": len(members_prog), "assigned": len(members_prog),
                                   "missing_from_rungs": [], "not_in_program": []}
        out_gens.append(gen_rec)

    # ---- closure files: blind floors (no labels) + stated labels, both grades ----
    floors, labels, idx = [], [], 0

    def paper_floor(members):
        fl = [{"techniques": sorted(tech_names(c)),
               "results": [r["claim"] for r in ladders[c].get("results", [])]}
              for c in members if c in ladders]
        return {"items": fl, "n_members_without_ladder": sum(1 for c in members if c not in ladders)}

    manifest = []  # lives only in the labels file (the judge's side) + the regraded record
    for g in out_gens:
        if g["mode"] == "split":
            for r in g["rungs"]:
                floors.append({"idx": idx, "kind": "rung->papers", "floor": paper_floor(r["papers"])})
                labels.append({"idx": idx, "kind": "rung->papers", "name": r["name"],
                               "stated": r["essence"], "parent": g["label"]})
                manifest.append((idx, g["label"], r["name"]))
                idx += 1
    for g in out_gens:
        if g["mode"] == "split":
            fl = {"child_essences": [{"name": r["name"], "essence": r["essence"]} for r in g["rungs"]]}
            floors.append({"idx": idx, "kind": "generator->rungs", "floor": fl})
        else:
            floors.append({"idx": idx, "kind": "generator->papers", "floor": paper_floor(g["papers"])})
        labels.append({"idx": idx, "kind": floors[-1]["kind"], "name": g["label"],
                       "stated": g["essence"], "parent": None})
        manifest.append((idx, g["label"], None))
        idx += 1

    regraded_doc = {
        "_key": key, "name": struct.get("name", key),
        "source": f"{key}.json (ladders unchanged) + insert-middle regrade 2026-06-11",
        "generators": out_gens,
        "_coverage": coverage, "_twin_collapse": twin_collapse,
        "_closure_manifest": [{"idx": i, "generator": gl, "rung": rn} for i, gl, rn in manifest],
        "_provenance": ("wf_insert_middle.mjs (model wrote essences/memberships/moves) + "
                        "assemble_regrade.py (mechanical: id canonicalisation, twin collapse, "
                        "shared-technique weights, closure floors/labels). Weights are counts of "
                        "shared technique names - every entry locatored, none model-asserted."),
    }
    suffix = "v2" if key == "mccaul" else key
    raw_name = "_regrade_raw.json" if key == "mccaul" else f"_regrade_raw_{key}.json"
    (STRUCT_DIR / f"{key}_regraded.json").write_text(
        json.dumps(regraded_doc, indent=1, ensure_ascii=False), encoding="utf-8")
    (STRUCT_DIR / f"_closure_floors_{suffix}.json").write_text(
        json.dumps(floors, indent=1, ensure_ascii=False), encoding="utf-8")
    (STRUCT_DIR / f"_closure_labels_{suffix}.json").write_text(
        json.dumps(labels, indent=1, ensure_ascii=False), encoding="utf-8")
    (STRUCT_DIR / raw_name).write_text(
        json.dumps(raw["result"], indent=1, ensure_ascii=False), encoding="utf-8")

    n_rungs = sum(len(g["rungs"]) for g in out_gens)
    print(f"generators: {len(out_gens)} ({sum(1 for g in out_gens if g['mode']=='split')} split, "
          f"{sum(1 for g in out_gens if g['mode']=='enrich')} enriched); rungs: {n_rungs}; "
          f"closure entries: {idx}")
    print("twin collapses:", json.dumps(twin_collapse))
    for k, c in coverage.items():
        flag = " <-- CHECK" if (c["missing_from_rungs"] or c["not_in_program"]) else ""
        print(f"coverage {k}: program={c['program']} assigned={c['assigned']} "
              f"missing={c['missing_from_rungs']} extra={c['not_in_program']}{flag}")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "mccaul")
