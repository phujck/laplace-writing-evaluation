"""Dry-run: drain the wire-proposal audit with THE ONE OPERATOR, not a bespoke signal.

A wire-proposal is a (query, node) edge the symbolic layer could not explain. The decision -
wire (real, teach the keywords) / grit (conjectural, keep) / noise (accident, discard) - is the
SAME question as N42 placement: does this thing project onto its home with a sharp margin, or is
it a diffuse stray? So we recur the operator instead of inventing a signal:

  build the basis  V = top-K principal directions of the whole conceptric's node embeddings
                   (grades-are-basis-projection, applied to the engine's own nodes).
  the test         a real edge SURVIVES the projection - query and node agree in the denoised
                   basis (align = cos(V q, V n)); a surface accident lives in the discarded
                   directions, so full-space cosine is high but basis-agreement is not.
  the margin       m_node = top1-top2 of |V n| - how sharply the node has a home at all
                   (a config/path artifact is diffuse; a real concept is sharp).

Ground truth = the 118 banked jury verdicts (.wire_verdicts.jsonl). Validate the operator
separates them, THEN apply to the unjudged frontier. Embeddings only (bge-small, local). Mutates
nothing.

Usage:  python scripts/wire_drain_dryrun.py [K]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from laplace.engine import conceptric                                    # noqa: E402
from laplace.representation.embed_router import get_backend, node_text, proposal_pairs, ensure_embeddings


def read_jsonl(p: Path):
    out = []
    if p.is_file():
        for ln in p.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                try:
                    out.append(json.loads(ln))
                except ValueError:
                    pass
    return out


def auc(pos: np.ndarray, neg: np.ndarray) -> float:
    """P(score(pos) > score(neg)) - rank separation, threshold-free."""
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    wins = sum((pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()
               for _ in [0])
    return float(wins) / (len(pos) * len(neg))


def main(K: int = 64) -> int:
    backend = get_backend()
    if backend is None or backend.name.startswith("hash"):
        print("ERROR: real embedder unavailable.")
        return 1
    net = conceptric.load_network(ROOT)
    nodes = net["nodes"]
    vecs = ensure_embeddings(ROOT, net, backend)["vectors"]
    ids = list(vecs)
    X = np.asarray([vecs[i] for i in ids], dtype=np.float64)
    X /= np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-12, None)
    # the basis: top-K principal directions of the conceptric (centered)
    Xc = X - X.mean(0, keepdims=True)
    _, _, Vt = np.linalg.svd(Xc, full_matrices=False)
    V = Vt[:K]                                            # K x D
    print(f"embedder: {backend.name} | nodes: {len(ids)} | basis K={K}\n")

    vmap = {i: np.asarray(v, dtype=np.float64) for i, v in vecs.items()}

    def node_vec(nid: str) -> np.ndarray:
        v = vmap.get(nid)
        if v is None:
            txt = node_text(ROOT, net, nid) if nid in nodes else nid
            v = np.asarray(backend.embed([txt])[0], dtype=np.float64)
        n = np.linalg.norm(v)
        return v / n if n else v

    _qc: dict[str, np.ndarray] = {}

    def qvec(q: str) -> np.ndarray:
        if q not in _qc:
            _qc[q] = np.asarray(backend.query(q), dtype=np.float64)
        return _qc[q]

    def signals(query: str, nid: str):
        qv = qvec(query); nv = node_vec(nid)
        full = float(qv @ nv)
        qcoef = V @ qv; ncoef = V @ nv
        denom = float(np.linalg.norm(qcoef) * np.linalg.norm(ncoef))
        align = float(qcoef @ ncoef) / denom if denom else 0.0
        a = np.abs(ncoef); a.sort()
        m_node = float(a[-1] - a[-2]) if len(a) >= 2 else float(a[-1])
        return full, align, m_node

    # ---- validate against the 118 banked verdicts ----
    verdicts = [v for v in read_jsonl(ROOT / ".wire_verdicts.jsonl")
                if v.get("verdict") in ("wire", "grit", "noise")]
    rows = {"wire": [], "grit": [], "noise": []}
    for v in verdicts:
        rows[v["verdict"]].append(signals(v.get("query", ""), v.get("id", "")))
    arr = {k: np.asarray(r) if r else np.zeros((0, 3)) for k, r in rows.items()}

    names = ["full_cos", "basis_align", "m_node"]
    print(f"banked: wire {len(arr['wire'])}, grit {len(arr['grit'])}, noise {len(arr['noise'])}")
    print(f"\n  {'signal':<13}{'wire_mean':>11}{'grit_mean':>11}{'noise_mean':>12}"
          f"{'AUC wire>noise':>16}")
    for j, nm in enumerate(names):
        wm = arr["wire"][:, j].mean() if len(arr["wire"]) else float("nan")
        gm = arr["grit"][:, j].mean() if len(arr["grit"]) else float("nan")
        nmn = arr["noise"][:, j].mean() if len(arr["noise"]) else float("nan")
        a = auc(arr["wire"][:, j], arr["noise"][:, j])
        print(f"  {nm:<13}{wm:>11.3f}{gm:>11.3f}{nmn:>12.3f}{a:>16.3f}")

    # PRECISION gate on the plainest operator signal: full_cos (the route coefficient).
    # wire iff cos >= hi (above the noise tail), noise iff cos <= lo (below the wire tail),
    # else escalate the ambiguous middle to a cheap jury - N42's margin gate, recurred.
    wj = arr["wire"][:, 0]; nj = arr["noise"][:, 0]; gj = arr["grit"][:, 0]
    print(f"\n  precision sweep on full_cos (the route coefficient):")
    print(f"  {'hi':>6}{'lo':>6}{'noise_drained':>15}{'wire_called':>14}"
          f"{'corrupt':>9}{'escalate%':>11}")
    best = None
    for hi in (0.62, 0.65, 0.68, 0.70):
        for lo in (0.46, 0.48, 0.50):
            def cls(c):
                return "wire" if c >= hi else "noise" if c <= lo else "escalate"
            nd_tot = int((nj <= lo).sum()); nd_bad = int((wj <= lo).sum())  # wire wrongly drained
            wc_tot = int((wj >= hi).sum()); wc_bad = int((nj >= hi).sum())  # noise wrongly wired
            esc = int((np.r_[wj, gj, nj] > lo).sum() - (np.r_[wj, gj, nj] >= hi).sum())
            escf = esc / len(verdicts)
            print(f"  {hi:>6.2f}{lo:>6.2f}{nd_tot:>9}/{nd_tot+nd_bad:<5}{wc_tot:>8}/{wc_tot+wc_bad:<5}"
                  f"{wc_bad:>9}{escf*100:>10.0f}%")
            # objective: zero corrupting noise->wire, then max mechanical coverage
            score = (wc_bad == 0, nd_tot + wc_tot)
            if best is None or score > best[0]:
                best = (score, hi, lo)
    _, hi, lo = best
    def classify(c):
        return "wire" if c >= hi else "noise" if c <= lo else "escalate"
    pairs = proposal_pairs(ROOT)
    ap = {"wire": 0, "noise": 0, "escalate": 0}
    for p in pairs:
        full, _, _ = signals(p["query"], p["id"])
        ap[classify(full)] += 1
    n = len(pairs)
    print(f"\n  CHOSEN operating point: wire>= {hi:.2f} (auto-wire), noise<= {lo:.2f} "
          f"(auto-discard), else jury")
    print(f"  APPLIED to {n} unjudged: auto-wire {ap['wire']}, auto-noise {ap['noise']}, "
          f"jury {ap['escalate']} -> {ap['wire']+ap['noise']}/{n} mechanical "
          f"({100*(ap['wire']+ap['noise'])/n:.0f}%), {ap['escalate']} need intelligence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 64))
