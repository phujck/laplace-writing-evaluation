import json, sys
sys.stdout.reconfigure(encoding="utf-8")
src, dest = sys.argv[1], sys.argv[2]
d = json.load(open(src, encoding="utf-8"))
out = d["result"]
out["_provenance"] = "structural shard (wf_structural_shard.mjs) 2026-06-11 - same operator as mccaul"
json.dump(out, open(dest, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
up = out["upfold"]
print(f"{out['_key'] if '_key' in out else out['key']}: {out['n_papers']} ladders -> {len(up['program'])} generators")
for g in up["program"]:
    print(f"  [{len(g['papers'])} papers] {g['generator']}")
