import json, sys
sys.stdout.reconfigure(encoding="utf-8")
d = json.load(open(sys.argv[1], encoding="utf-8"))
out = d["result"]
out["_provenance"] = ("structural shard (wf_structural_shard.mjs) 2026-06-11: the 55 session handoffs as the "
                      "corpus of the build programme - same operator as mccaul/magann. UPFOLD = candidate "
                      "generators of the SELF; his oracle eye PRE-REGISTERED before these become the middle "
                      "(backwards-loop guard).")
dest = r"C:\Users\gerar\VScodeProjects\laplace\archive\self_record\_structural\self_record.json"
json.dump(out, open(dest, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
up = out["upfold"]
print("self_record:", out["n_papers"], "session ladders;", len(up["program"]), "candidate generators")
print("note:", up.get("note", ""))
print()
for g in up["program"]:
    print(f"[{len(g['papers'])} sessions] {g['generator']}")
    print(f"    why: {g['why'][:220]}")
