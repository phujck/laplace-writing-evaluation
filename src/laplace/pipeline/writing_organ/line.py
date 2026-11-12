"""The line machinery: spectral order, cutwidth, and telling naturalness over the claim graph.

The arrangement mathematics of DESIGN_2026-08-07 addendum: pedagogical load is the
cutwidth of the linear extension; the tractable ordering relaxation is seriation by the
Fiedler vector of the graph Laplacian; a telling is natural when its arc's order agrees
with the graph's spectral geometry. All numpy, no model.

Run: python3 -m laplace.pipeline.writing_organ.line <manuscript_dir>   (reports on the current graph)
"""

from __future__ import annotations

import json
import sys
import pathlib

import numpy as np


def load(manuscript_dir: pathlib.Path) -> tuple[list[dict], list[dict], dict[str, int]]:
    g = json.loads((manuscript_dir / "claim_graph.json").read_text())
    idx = {v["id"]: i for i, v in enumerate(g["vertices"])}
    return g["vertices"], g["edges"], idx


def laplacian(n: int, edges: list[dict], idx: dict[str, int]) -> np.ndarray:
    A = np.zeros((n, n))
    for e in edges:
        i, j = idx[e["src"]], idx[e["dst"]]
        A[i, j] += 1.0
        A[j, i] += 1.0
    return np.diag(A.sum(1)) - A


def fiedler_order(L: np.ndarray) -> np.ndarray:
    vals, vecs = np.linalg.eigh(L)
    return np.argsort(vecs[:, 1])


def cutwidth(order: np.ndarray, edges: list[dict], idx: dict[str, int]) -> int:
    pos = np.empty(len(order), dtype=int)
    pos[order] = np.arange(len(order))
    cuts = np.zeros(len(order) + 1, dtype=int)
    for e in edges:
        a, b = pos[idx[e["src"]]], pos[idx[e["dst"]]]
        lo, hi = (a, b) if a < b else (b, a)
        cuts[lo + 1:hi + 1] += 1
    return int(cuts.max())


def order_consistency(arc_positions: dict[str, int], L: np.ndarray, idx: dict[str, int]) -> float:
    """Spearman correlation between an arc's claim ordering and the Fiedler ordering,
    sign-corrected (the Fiedler vector's sign is arbitrary)."""
    vals, vecs = np.linalg.eigh(L)
    f = vecs[:, 1]
    ids = [i for i in arc_positions if i in idx]
    if len(ids) < 3:
        return float("nan")
    a = np.array([arc_positions[i] for i in ids], dtype=float)
    b = np.array([f[idx[i]] for i in ids])
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    r = np.corrcoef(ra, rb)[0, 1]
    return float(abs(r))


def score_telling(telling: dict, vertices: list[dict], edges: list[dict], idx: dict[str, int]) -> dict:
    """Naturalness: coverage (castless load-bearing atoms) + order-consistency of the arc.
    Compression is scored at Phase 3 via the quiz - stated, not silently skipped."""
    cast = telling.get("cast", {})
    excluded = set(telling.get("excluded", []))
    load_bearing = [v["id"] for v in vertices if v["kind"] in ("claim", "result")]
    castless = [i for i in load_bearing if i not in cast and i not in excluded]

    arc_positions: dict[str, int] = {}
    for m, movement in enumerate(telling.get("arc", [])):
        for cid in movement.get("discharges", []):
            arc_positions.setdefault(cid, m)
    L = laplacian(len(vertices), edges, idx)
    oc = order_consistency(arc_positions, L, idx)

    pos = {v: m for v, m in arc_positions.items() if v in idx}
    fwd = 0
    for e in edges:
        if e["rel"] in ("draws", "grounds") and e["src"] in pos and e["dst"] in pos:
            if pos[e["dst"]] > pos[e["src"]]:
                fwd += 1
    return {"castless_load_bearing": len(castless), "castless_ids": castless[:10],
            "excluded": len(excluded), "order_consistency": round(oc, 3),
            "forward_support_edges": fwd,
            "arc_movements": len(telling.get("arc", []))}


def main() -> int:
    md = pathlib.Path(sys.argv[1])
    vertices, edges, idx = load(md)
    L = laplacian(len(vertices), edges, idx)
    forder = fiedler_order(L)
    cw_fiedler = cutwidth(forder, edges, idx)
    doc_order = np.arange(len(vertices))
    cw_doc = cutwidth(doc_order, edges, idx)
    print(f"vertices {len(vertices)}  edges {len(edges)}")
    print(f"cutwidth: conceptric order {cw_doc}  |  Fiedler order {cw_fiedler}")
    ids = [vertices[i]["id"] for i in forder[:12]]
    print("Fiedler head:", " ".join(ids))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
