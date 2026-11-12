#!/usr/bin/env python3
"""demo_stage_stores.py — THE 2x2 stage-stores demonstration (design §5, §7; the audit's
readiness-verdict evidence).

The smallest REAL proof of the whole stage-stores shape, end to end, on his real papers:

    per-paper conceptric (the proven UP operator)  ->  store VIEWS (design §1c)
        ->  per-paper namespaced JSONL files (design §3)  ->  local ONNX embeddings
        ->  per-store HOLDOUT GATE (design §5: ship iff retrieval beats the identity
            baseline)  ->  the REFUSAL of a planted signal-free store.

Two papers x two lenses (NOT the fleet — the fleet fires on his word only, design §7):

  papers  (census-picked, top-2 by structural richness, sections >= 2):
    - quantum-dynamical-emulation-itqde
    - classical-influence-functionals
  lenses  (the two whose held-out-SECTION gate is cleanest to run):
    - section_architecture   (design §2.2)
    - spine_chain            (design §2.3)

THE CONCEPTRIC. The demo papers ship as SINGLE-file tex with INLINE ``\\section{}`` — but the
proven UP operator ``corpus_ingest.build_corpus_network`` discovers sections through
``\\input{}`` (the multi-file layout of the registered papers / the falqon pour). So the
driver splits each paper's ``\\section`` blocks into the ``\\input{}`` layout the atomiser
consumes, IN AN OS TEMP DIR — ``voice_corpus/`` is read-only, never mutated — and feeds THAT
to ``build_corpus_network``. The result is the real full-fidelity conceptric (section /
equation / figure nodes, explicit ``\\eqref`` edges, dependency grades). The split is
mechanical; the per-section real prose is re-attached to the net (``section_prose`` /
``section_meta``), keyed by the net's OWN section ids, so a row's ``embed_text`` is his real
prose and its ``span_ref`` traces to conceptric node ids.

THE GATE (design §5, the ``metric_distill`` gate-then-ship discipline via
``pipeline.holdout_gate``). For a held-out section/rung, does retrieval by his-prose cosine
surface the right FORM CLASS (``job`` for section_architecture, ``ladder_move`` for
spine_chain)? The picker ranks each candidate class by its NEAREST real row (design's top-k
nearest, leave-one-out). The BASELINE is the true identity baseline — the SAME nearest-class
ranking driven by a signal-free RANDOM query, averaged over many draws — so it captures the
class-size bias exactly (``metric_distill``'s "a picker with no real signal, evaluated the
exact same way"). A store passes iff its real-query AUC strictly beats that baseline.

THE REFUSAL PROOF. A planted BAD store = the same rows with their embeddings SHUFFLED (a
store with no real signal). Its real-query ranking collapses onto the signal-free baseline;
the gate returns ``passed=False`` — the refusal that keeps the run honest (design §5: "a
store that can't pass does not wire in — the refusal is the result"). If a REAL store also
refuses, that is reported honestly, never tuned away (design §7).

Model tokens ~zero: both lenses are view-derivable mechanically (the point of v2). Embeddings
are the LOCAL vendored bge-small over ONNX (no network). Everything is deterministic where
feasible (the gate is seeded).

Usage:
    .venv/bin/python scripts/demo_stage_stores.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from laplace.representation.embed_router import get_backend  # noqa: E402
from laplace.pipeline import stage_store  # noqa: E402
from laplace.pipeline.dials import load_dials  # noqa: E402
from laplace.pipeline.fanout import chunk, width  # noqa: E402
from laplace.pipeline.holdout_gate import holdout_gate  # noqa: E402
from laplace.pipeline.section_bridge import bridged_network  # noqa: E402

DEMO_PAPERS = ["quantum-dynamical-emulation-itqde", "classical-influence-functionals"]
LENSES = ["section_architecture", "spine_chain"]
CLASS_KEY = {"section_architecture": "job", "spine_chain": "ladder_move"}
HOLDOUT_FRACTION = 0.3        # >= the gate's MIN_HOLDOUT floor over these small stores
BASELINE_DRAWS = 64          # identity-baseline stability: averaged signal-free queries
STORES_ROOT = _REPO_ROOT / "corpus_stores"

# --------------------------------------------------------------------------- #
# the conceptric: THE SECTION BRIDGE, now productized (design §1c; the audit's
# readiness precondition — "the inline-\section -> \input{} bridge productized").
# The split-into-\input-layout + per-section prose enrichment this demo proved lives
# in ``pipeline.section_bridge.bridged_network``; the demo delegates to it verbatim.
# --------------------------------------------------------------------------- #
def build_paper_net(paper_id: str) -> dict[str, Any]:
    """Resolve the paper's tex (census exemplar dir, first .tex) and build its full-fidelity
    conceptric through the shared bridge (``section_bridge.bridged_network``): the proven UP
    operator over the split \\input{} layout, enriched with per-section real prose keyed by the
    net's own section ids. The split lands in the bridge's own OS tempdir — ``voice_corpus/``
    is never mutated."""
    src_dir = _REPO_ROOT / "voice_corpus" / "exemplars" / paper_id
    tex_files = sorted(src_dir.glob("*.tex"))
    if not tex_files:
        raise SystemExit(f"demo_stage_stores: no .tex under {src_dir}")
    return bridged_network(tex_files[0], paper_id)


# --------------------------------------------------------------------------- #
# embeddings (local ONNX) — the voice-store shape, keyed by row id
# --------------------------------------------------------------------------- #
def embed_store(store_name: str, rows: list[dict[str, Any]], backend: Any) -> dict[str, list[float]]:
    """Embed every row's ``embed_text`` via the local vendored backend and write
    ``corpus_stores/<store>/embeddings.json`` keyed by row id (backend + dim, voice-store
    shape). Returns the {row_id: vector} map."""
    import numpy as np

    vecs = backend.embed([r["embed_text"] for r in rows])
    X = np.asarray(vecs, dtype=np.float64)
    X /= np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-12, None)
    items = {r["row_id"]: X[i].tolist() for i, r in enumerate(rows)}
    dim = X.shape[1] if len(rows) else 0
    out = STORES_ROOT / store_name / "embeddings.json"
    out.write_text(json.dumps({"backend": backend.name, "dim": int(dim), "items": items}),
                   encoding="utf-8")
    return items


# --------------------------------------------------------------------------- #
# the holdout gate: retrieval-surfaces-right-class vs the identity baseline
# --------------------------------------------------------------------------- #
def run_store_gate(rows: list[dict[str, Any]], embeddings: dict[str, list[float]],
                   class_key: str, *, shuffle: bool = False,
                   holdout_fraction: float = HOLDOUT_FRACTION) -> dict[str, Any]:
    """Gate a store: does his-prose cosine retrieval surface the right FORM class for a
    held-out row, beating the identity baseline? (design §5).

    ``pick_fn(i)`` ranks each candidate class by its NEAREST training row's cosine to the
    held-out row (leave-one-out; the design's "top-k contains a section of the same class").
    ``baseline_fn(i)`` is the identity baseline — the SAME nearest-class ranking driven by a
    signal-free RANDOM query, averaged over ``BASELINE_DRAWS`` draws — so class-size bias is
    captured identically on both sides and only real query-signal can move ``score`` above it.

    ``shuffle=True`` builds the PLANTED BAD store: the row embeddings are permuted (seeded),
    decoupling them from the classes — the store with no real signal that must be REFUSED.
    """
    import numpy as np

    classes = [r["form"][class_key] for r in rows]
    X = np.asarray([embeddings[r["row_id"]] for r in rows], dtype=np.float64)
    X /= np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-12, None)
    if shuffle:
        perm = np.random.default_rng(1_000_003).permutation(len(rows))
        X = X[perm]
    items = list(range(len(rows)))
    dim = X.shape[1] if len(rows) else 0

    def nearest_class_map(qv: "np.ndarray", i: int) -> dict[str, float]:
        sims = X @ qv
        best: dict[str, float] = {}
        for j in items:
            if j == i:
                continue
            c = classes[j]
            if sims[j] > best.get(c, -2.0):
                best[c] = float(sims[j])
        return best

    def pick_fn(i: int) -> dict[str, float]:
        return nearest_class_map(X[i], i)

    def baseline_fn(i: int) -> dict[str, float]:
        rng = np.random.default_rng([20260715, i])
        acc: dict[str, list[float]] = {}
        for _ in range(BASELINE_DRAWS):
            q = rng.standard_normal(dim)
            q /= max(float(np.linalg.norm(q)), 1e-12)
            for c, s in nearest_class_map(q, i).items():
                acc.setdefault(c, []).append(s)
        return {c: float(np.mean(v)) for c, v in acc.items()}

    def truth_fn(i: int) -> str:
        return classes[i]

    return holdout_gate(items, pick_fn=pick_fn, truth_fn=truth_fn,
                        baseline_fn=baseline_fn, holdout_fraction=holdout_fraction)


# --------------------------------------------------------------------------- #
# the driver
# --------------------------------------------------------------------------- #
DERIVERS = {
    "section_architecture": stage_store.derive_section_architecture,
    "spine_chain": stage_store.derive_spine_chain,
}


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

    backend = get_backend()
    if backend is None:
        print("demo_stage_stores: no local embedding backend (models/fastembed unavailable); "
              "the demo needs the vendored ONNX model.", file=sys.stderr)
        return 1

    dials = load_dials()
    fan_width = width(dials)

    # the fleet unit is a lens-read (one paper through one lens); bound it by the fanout dial
    # (design §6: "the lens fleet chunks into fanout-sized batches, never uncapped").
    work_items = [(p, lens) for p in DEMO_PAPERS for lens in LENSES]
    batches = chunk(work_items, fan_width)
    print(f"# demo_stage_stores — 2x2 (2 papers x 2 lenses = {len(work_items)} lens-reads)")
    print(f"fanout.max_width={fan_width} ({'UNCAPPED' if fan_width <= 0 else 'capped'}) "
          f"-> {len(batches)} batch(es) of <= {fan_width or len(work_items)} lens-reads")

    store_rows: dict[str, list[dict[str, Any]]] = {lens: [] for lens in LENSES}
    per_paper_counts: dict[str, dict[str, int]] = {}
    # build each paper's conceptric ONCE (both lenses view the same net); the bridge owns and
    # cleans up its own OS tempdir per paper, so no shared temp root is managed here.
    nets: dict[str, dict[str, Any]] = {}
    for paper_id in DEMO_PAPERS:
        nets[paper_id] = build_paper_net(paper_id)
        nodes = nets[paper_id]["nodes"]
        n_sec = sum(1 for n in nodes.values() if n.get("kind") == "section")
        n_eq = sum(1 for n in nodes.values() if n.get("kind") == "equation")
        n_fig = sum(1 for n in nodes.values() if n.get("kind") == "figure")
        print(f"  conceptric[{paper_id}]: {len(nodes)} nodes "
              f"({n_sec} sec / {n_eq} eq / {n_fig} fig)")

    # process the fanout-bounded batches: derive views + write namespaced files
    for bi, batch in enumerate(batches):
        print(f"  batch {bi + 1}/{len(batches)}: {[f'{p}:{lens}' for p, lens in batch]}")
        for paper_id, lens in batch:
            rows = DERIVERS[lens](nets[paper_id], paper_id)
            stage_store.write_store(lens, paper_id, rows, stores_root=STORES_ROOT)
            store_rows[lens].extend(rows)
            per_paper_counts.setdefault(lens, {})[paper_id] = len(rows)

    # embed each store (merged across papers) + run the gates
    verdict: dict[str, Any] = {
        "schema": "stage-store-demo-verdict/0.1",
        "papers": DEMO_PAPERS,
        "lenses": LENSES,
        "fanout": {"max_width": fan_width, "n_batches": len(batches),
                   "n_lens_reads": len(work_items)},
        "backend": backend.name,
        "holdout_fraction": HOLDOUT_FRACTION,
        "residue_fields": stage_store.RESIDUE_FIELDS,
        "stores": {},
    }
    for lens in LENSES:
        rows = store_rows[lens]
        emb = embed_store(lens, rows, backend)
        real = run_store_gate(rows, emb, CLASS_KEY[lens])
        bad = run_store_gate(rows, emb, CLASS_KEY[lens], shuffle=True)
        verdict["stores"][lens] = {
            "class_key": CLASS_KEY[lens],
            "rows": len(rows),
            "rows_per_paper": per_paper_counts.get(lens, {}),
            "dim": emb and len(next(iter(emb.values()))) or 0,
            "gate": real,
            "planted_bad_gate": bad,
            "wired_in": bool(real.get("passed")),
        }

    STORES_ROOT.mkdir(parents=True, exist_ok=True)
    (STORES_ROOT / "demo_verdict.json").write_text(
        json.dumps(verdict, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # the machine-readable summary
    print("\n# ===== DEMO SUMMARY =====")
    print(json.dumps({"stores": {
        lens: {
            "class": v["class_key"], "rows": v["rows"], "rows_per_paper": v["rows_per_paper"],
            "gate_score": v["gate"]["score"], "gate_baseline": v["gate"]["baseline"],
            "gate_passed": v["gate"]["passed"], "gate_mode": v["gate"]["mode"],
            "n_holdout": v["gate"]["n_holdout"],
            "planted_bad_score": v["planted_bad_gate"]["score"],
            "planted_bad_baseline": v["planted_bad_gate"]["baseline"],
            "planted_bad_passed": v["planted_bad_gate"]["passed"],
            "wired_in": v["wired_in"],
        } for lens, v in verdict["stores"].items()
    }}, indent=2))

    print("\n# ===== VERDICT (per store) =====")
    for lens, v in verdict["stores"].items():
        g, b = v["gate"], v["planted_bad_gate"]
        real_tag = "PASS (wires in)" if g["passed"] else "REFUSED (does not wire in)"
        bad_tag = "REFUSED" if not b["passed"] else "PASSED (!! bad store not refused)"
        print(f"  {lens:<22} rows={v['rows']:<3} class={v['class_key']:<12} "
              f"real: score={g['score']} base={g['baseline']} -> {real_tag}")
        print(f"  {'':22} planted-bad: score={b['score']} base={b['baseline']} -> {bad_tag}")

    refusal_ok = all(not v["planted_bad_gate"]["passed"] for v in verdict["stores"].values())
    print(f"\nREFUSAL PROOF: every planted bad store refused = {refusal_ok}")
    print(f"wrote: {(STORES_ROOT / 'demo_verdict.json').relative_to(_REPO_ROOT)}")
    return 0 if refusal_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
