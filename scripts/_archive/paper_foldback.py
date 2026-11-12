"""The fold-back gate for the paper_eigen writing loop (discipline rule 3) - batched.

Each drafted section is embedded once and projected down the network (the same walk as
project_residue.py): the top-grade basis absorbs what the section is about, the residue is what
no existing node expresses. A section that is a true projection of the network routes home with
modest residue; a fluent guess routes elsewhere or leaves a fat residue. First run = the
calibration readings, recorded to JSON (not hard-failed) - judge nothing at a saturated edge.

Usage: paper_foldback.py  -> paper_eigen/_loop/foldback.json
"""
import io
import json
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
LOOP = ROOT / "paper_eigen" / "_loop"

import numpy as np

from laplace.engine import conceptric
from laplace.representation import embed_router

TOP_K = 4


def unit(v):
    v = np.asarray(v, dtype="float32")
    n = float(np.linalg.norm(v))
    return v / n if n else v


def main() -> int:
    net = conceptric.load_network(ROOT)
    backend = embed_router.get_backend()
    if backend is None:
        print(json.dumps({"error": "no embedding backend (run under the venv python)"}))
        return 1
    emb = embed_router.ensure_embeddings(ROOT, net, backend)
    vecs = {nid: unit(v) for nid, v in emb["vectors"].items()}
    nodes = net["nodes"]
    grades = [n.get("grade", 0) for nid, n in nodes.items() if nid in vecs]
    g_top = max(grades)
    roots = [nid for nid, n in nodes.items()
             if nid in vecs and n.get("grade", 0) >= g_top - 1]

    report = {}
    for k in range(1, 9):
        p = LOOP / f"draft_{k}.md"
        if not p.is_file():
            continue
        text = re.sub(r"<!--.*?-->", "", p.read_text(encoding="utf-8"), flags=re.S)
        v = unit(backend.query(text))
        scored = sorted(((float(np.dot(v, vecs[c])), c) for c in roots), reverse=True)
        basis = []
        for _, c in scored[:TOP_K]:
            b = vecs[c].copy()
            for q in basis:
                b -= float(np.dot(b, q)) * q
            n = float(np.linalg.norm(b))
            if n > 1e-6:
                basis.append(b / n)
        proj = sum(float(np.dot(v, q)) * q for q in basis)
        residue = v - proj
        r = unit(residue)
        near = sorted(((float(np.dot(r, b)), nid) for nid, b in vecs.items()), reverse=True)[:3]
        report[k] = {
            "absorbed": round(float(np.linalg.norm(proj)), 3),
            "residue": round(float(np.linalg.norm(residue)), 3),
            "top_absorbers": [(round(s, 3), c) for s, c in scored[:4]],
            "residue_neighbours": [(round(s, 3), nid) for s, nid in near],
        }
        print(f"S{k}: absorbed {report[k]['absorbed']}  residue {report[k]['residue']}  "
              f"top {scored[0][1]} ({scored[0][0]:+.3f})")
    (LOOP / "foldback.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"\n-> {LOOP / 'foldback.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
