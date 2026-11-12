"""The translation loop's vector->semantic half, v0 (his teaching, 2026-06-11):

  "Once you have the map between the semantic and the vectorial, everything is mechanical,
   and you just dot product the vector with existing vectors at the grade. That's how you
   get the vectorial residue, and infer the semantic content."

Embed the input once (semantic->vector, the paid half). Then descend the network grade by
grade: at each grade dot the ORIGINAL vector against the grade's basis (the current node's
children), project onto the top-k absorbers (Gram-Schmidt), and carry the RESIDUE - the part
the basis cannot express. The coefficients ARE the reading (where it lives, what it couples
to); the residual norm is the novelty; the residue's nearest nodes localise what the new
part resembles (the grit seed). No model anywhere - one embed call, then dot products.

Usage: project_residue.py "<text>"  |  project_residue.py --file <path>
"""
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent

import numpy as np

from laplace.engine import conceptric
from laplace.representation import embed_router

TOP_K = 4          # basis size per grade (the absorbers)
SHOW = 5           # coefficients rendered per grade
MAX_DEPTH = 12


def unit(v):
    v = np.asarray(v, dtype="float32")
    n = float(np.linalg.norm(v))
    return v / n if n else v


def label_of(net, nid):
    n = net["nodes"].get(nid, {})
    lab = n.get("label") or nid
    return f"{lab}  [g{n.get('grade', '?')}]"


def main():
    args = sys.argv[1:]
    if args and args[0] == "--file":
        text = Path(args[1]).read_text(encoding="utf-8")
        src = args[1]
    else:
        text = " ".join(args)
        src = "inline"
    if not text.strip():
        print("no input")
        return 1

    net = conceptric.load_network(ROOT)
    backend = embed_router.get_backend()
    emb = embed_router.ensure_embeddings(ROOT, net, backend)
    vecs = {nid: unit(v) for nid, v in emb["vectors"].items()}
    v = unit(backend.query(text))

    nodes = net["nodes"]
    # ENTER AT THE CONDENSED APEX (view-from-the-condensed-apex): the top two grades that
    # carry vectors, descend through memberships from there - never the flat file roots
    grades = [n.get("grade", 0) for nid, n in nodes.items() if nid in vecs]
    g_top = max(grades)
    roots = [nid for nid, n in nodes.items()
             if nid in vecs and n.get("grade", 0) >= g_top - 1]

    print(f"PROJECTION CASCADE  ({src}, {len(text)} chars -> 1 embed, then dot products only)")
    print(f"{'='*78}")

    candidates = roots
    level = 0
    residue = v
    trail = []
    while candidates and level < MAX_DEPTH:
        scored = sorted(((float(np.dot(v, vecs[c])), c) for c in candidates if c in vecs),
                        reverse=True)
        if not scored:
            break
        # Gram-Schmidt the top-k basis, project the ORIGINAL vector, take the residue
        basis = []
        for _, c in scored[:TOP_K]:
            b = vecs[c].copy()
            for q in basis:
                b -= float(np.dot(b, q)) * q
            n = float(np.linalg.norm(b))
            if n > 1e-6:
                basis.append(b / n)
        proj = sum(float(np.dot(v, q)) * q for q in basis) if basis else np.zeros_like(v)
        residue = v - proj
        r_norm = float(np.linalg.norm(residue))
        absorbed = float(np.linalg.norm(proj))

        print(f"\ngrade step {level}  |  absorbed {absorbed:.3f}  residue {r_norm:.3f}")
        for s, c in scored[:SHOW]:
            print(f"   {s:+.3f}  {label_of(net, c)}")

        # descend through the best candidate that CAN be descended through (has vectored
        # children); pure leaves end the trail even when they score highest
        best, kids = None, []
        for _, c in scored:
            ks = [m for m in (nodes.get(c, {}).get("members") or []) if m in vecs]
            if ks:
                best, kids = c, ks
                break
        if best is None:
            best = scored[0][1]
        trail.append(best)
        candidates = kids
        level += 1

    print(f"\n{'-'*78}")
    print("descent trail:", " -> ".join(t.split('/')[-1][:40] for t in trail))

    # the grit localiser: what does the unexplained part resemble?
    r = unit(residue) if float(np.linalg.norm(residue)) > 1e-6 else None
    if r is not None:
        near = sorted(((float(np.dot(r, b)), nid) for nid, b in vecs.items()), reverse=True)[:SHOW]
        print(f"\nRESIDUE (novelty norm {float(np.linalg.norm(residue)):.3f}) - nearest existing nodes:")
        for s, nid in near:
            print(f"   {s:+.3f}  {label_of(net, nid)}")
        print("\nreading: high coefficients = where it lives; the residue is the part no")
        print("current node expresses - if its norm is large and its neighbours are weak,")
        print("the input carries a NEW node (the grit seed gets a name; nothing else does).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
