"""The distribution readout (mechanical, no model): per-grade counts, branching ratios,
and the grit census - members with ZERO mechanical coupling to their rung siblings
(w_raw=0: no shared technique names). The bottom-up conjugate of the closure test:
closure asks 'is each node comprehensible from above'; this asks 'is the ladder
statistically healthy from below' (power-law branching, no cliffs, bounded grit).
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SD = ROOT / "collaborator_corpus" / "_structural"

reg = json.loads((SD / "mccaul_regraded.json").read_text(encoding="utf-8"))
struct = json.loads((SD / "mccaul.json").read_text(encoding="utf-8"))

import re
def canon(pid):
    m = re.match(r"(W\d+)", pid.strip()); return m.group(1) if m else pid.strip()
ladders = {}
for lad in struct["ladders"]:
    ladders.setdefault(canon(lad["id"]), lad)

gens = reg["generators"]
n_gen = len(gens)
n_rung = sum(len(g["rungs"]) for g in gens)
papers = set()
for g in gens:
    for r in g.get("rungs", []): papers |= set(r["papers"])
    papers |= set(g.get("papers", []))
n_tech = sum(len(l.get("techniques", [])) for c, l in ladders.items() if c in papers)
n_res = sum(len(l.get("results", [])) for c, l in ladders.items() if c in papers)

# mid-grade node count: rungs + the enrich-mode generators' direct paper-floors count as pass-through
mid = n_rung + sum(1 for g in gens if g["mode"] == "enrich")
print(f"grade ladder: {n_gen} generators -> {mid} mid-nodes ({n_rung} rungs + "
      f"{mid-n_rung} enrich pass-throughs) -> {len(papers)} papers -> {n_tech} techniques -> {n_res} results")
print(f"branching:    gen->mid {mid/n_gen:.2f} | mid->paper {len(papers)/mid:.2f} | "
      f"paper->tech {n_tech/len(papers):.2f} | tech->result {n_res/n_tech:.2f}")

# grit census: zero-coupling members per cluster (no shared techniques with any sibling)
print("\ngrit census (w_raw=0 = no mechanical coupling to rung siblings):")
total, grit = 0, []
for g in gens:
    clusters = ([(r["name"], r["paper_edges"]) for r in g.get("rungs", [])]
                or [(g["label"][:40], g.get("paper_edges", []))])
    for name, edges in clusters:
        for e in edges:
            total += 1
            if e["w_raw"] == 0:
                ttl = ladders.get(e["paper"], {}).get("title", "(no ladder)")[:60]
                grit.append((name, e["paper"], ttl))
for name, pid, ttl in grit:
    print(f"  {name}: {pid} - {ttl}")
print(f"\ngrit fraction: {len(grit)}/{total} = {len(grit)/total:.0%} of members uncoupled at their grade")
