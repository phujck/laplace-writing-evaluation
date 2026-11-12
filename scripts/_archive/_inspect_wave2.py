"""Wave-2 preflight: shard shapes, member counts per generator, mechanical mode rule."""
import io
import json
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

for key in ("bondar", "magann"):
    d = json.load(open(f"collaborator_corpus/_structural/{key}.json", encoding="utf-8"))
    print(f"=== {key}: top keys {sorted(d.keys())}")
    up = d.get("upfold") or {}
    prog = up.get("program") or []
    print(f"  upfold.program: {len(prog)} generators | ladders: {len(d.get('ladders') or [])}")
    for i, g in enumerate(prog):
        members = g.get("papers") or g.get("members") or []
        label = (g.get("label") or g.get("generator") or "?")[:58]
        mode = "enrich" if len(members) <= 5 else "split"
        print(f"  [{i}] {len(members):>3} members  ->{mode:>7}  {label}")

m = json.load(open("collaborator_corpus/_structural/mccaul_regraded.json", encoding="utf-8"))
print("=== mccaul_regraded top keys:", sorted(m.keys()))
g0 = m["generators"][0]
print("  gen keys:", sorted(g0.keys()))
for g in m["generators"]:
    rungs = g.get("rungs") or []
    print(f"  {len(rungs)} rungs | mode={g.get('mode')} | {g['label'][:58]}")
if (m["generators"][0].get("rungs") or []):
    r = m["generators"][0]["rungs"][0]
    print("  rung keys:", sorted(r.keys()))
