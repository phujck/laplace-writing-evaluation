"""Fire-test the operations lens: does a task-shaped goal return my own workings at grade,
with the exact calls riding the essence? (view = mechanism: the navigator's own calls)."""
import sys
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path

from laplace.engine import conceptric, spine
from laplace.representation import embed_router

root = Path(__file__).resolve().parent.parent
net = conceptric.load_network(root)
ops = [k for k in net["nodes"] if k.startswith("engine_corpus/_structural")]
print(f"operations nodes in network: {len(ops)}")

for goal in ("how do I regrade a lens", "deposit the new lens so it routes", "sew up"):
    r = embed_router.route(root, net, goal, limit=5)
    hits = r.get("hits") or r.get("files") or []
    print(f"\nFIRE: {goal}")
    for h in hits[:5]:
        nid = h.get("id") or h.get("file")
        sal = h.get("salience", h.get("score", ""))
        mark = "  <-- OPS" if (nid and nid.startswith("engine_corpus")) else ""
        print(f"  {sal if isinstance(sal, str) else round(float(sal), 3)}  {nid}{mark}")

# the spine's view of a task goal
sp = spine.spine_for_goal(root, "run the regrade loop on the next collaborator") if hasattr(spine, "spine_for_goal") else None
if sp is None:
    try:
        sp = spine.reflex(root, "run the regrade loop on the next collaborator")
    except AttributeError:
        sp = "(spine API name differs - checked via /spine endpoint instead)"
print("\nSPINE on 'run the regrade loop on the next collaborator':")
print(str(sp)[:600])
