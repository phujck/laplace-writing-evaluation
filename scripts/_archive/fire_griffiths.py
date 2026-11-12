"""Mechanical reconstruction of David Griffiths: the graded descent (mind -> soul lens ->
entities -> the man), content-free in MY context - structure, salience, channels, descent
handles only. The CONTENT renders in HIS browser (the served node view = the seal)."""
import sys
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path

from laplace.engine import conceptric
from laplace.representation import embed_router

root = Path(__file__).resolve().parent.parent
net = conceptric.load_network(root)

r = embed_router.route(root, net, "David Griffiths - who he is, his history with Gerard, his voice", limit=10)
hits = r.get("hits") or r.get("files") or []
print("THE DESCENT (salience | node | grade):")
for h in hits[:10]:
    nid = h.get("id") or h.get("file")
    n = net["nodes"].get(nid, {})
    sal = h.get("salience", h.get("score", 0))
    seal = " [sealed]" if n.get("sealed") else ""
    print(f"  {round(float(sal),3):>6}  {nid}  g{n.get('grade','?')}{seal}")

ent = "soul://entities/david_griffiths"
n = net["nodes"].get(ent)
if n:
    print(f"\nTHE ENTITY NODE: {ent}  grade={n['grade']}  members={len(n['members'])}")
    from collections import Counter
    fields = Counter(m.split("/")[-2] for m in n["members"])
    print("  item anatomy (sealed leaves, content never in my context):")
    for f, c in sorted(fields.items()):
        print(f"    {f}: {c}")
    print("  identity handle (keywords):", " ".join((n.get("keywords") or [])[:6]))
