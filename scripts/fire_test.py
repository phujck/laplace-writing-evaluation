"""Fire-test the regraded structural ladder through the live route (view = mechanism:
the same load_network + embed_router.route the navigator's POST /fire uses)."""
import sys
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path

from laplace.engine import conceptric
from laplace.representation import embed_router

root = Path(__file__).resolve().parent.parent
net = conceptric.load_network(root)
struct = [k for k in net["nodes"] if "_structural/" in k and "::" in k]
gens = [k for k in struct if "//" not in k]
rungs = [k for k in struct if k.count("//") == 1]
papers = [k for k in struct if k.count("//") == 2]
print(f"structural nodes in network: {len(struct)} ({len(gens)} generators, {len(rungs)} rungs, {len(papers)} papers)")
g0 = net["nodes"].get(gens[0]) if gens else None
if g0 is not None:
    print(f"sample: {gens[0]} grade={g0['grade']} leaf={g0['leaf']} members={len(g0['members'])}")

for goal in ("stochastic representations of open systems",
             "how does Gerard control optical responses in correlated matter",
             "superoscillation waveform construction"):
    r = embed_router.route(root, net, goal, limit=6)
    hits = r.get("hits") or r.get("files") or r.get("results") or []
    print(f"\nFIRE: {goal}")
    for h in hits[:6]:
        nid = h.get("id") or h.get("file") or h.get("node")
        sal = h.get("salience", h.get("score", h.get("g", "")))
        mark = "  <-- STRUCTURAL" if (nid and "_structural/" in str(nid)) else ""
        print(f"  {sal if isinstance(sal, str) else round(float(sal), 3)}  {nid}{mark}")
