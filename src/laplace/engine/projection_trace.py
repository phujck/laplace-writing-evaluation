"""projection_trace.py - Phase 2: the round trip, and the triviality score.

The acceptance test the whole plan turns on: if the conceptric recovered by the UP operator
(corpus_ingest) is the true generating object, projecting the artefact back DOWN is trivial - every
element already constrained. So we measure exactly that. For each artefact element we ask: is it
present, and is everything it needs present and placed?

  triviality = (elements that fall out mechanically) / (all elements)

The residual is a TYPED friction report (CONTENT / FORM / TENSION) - the closure residual of
operatorial_self. A low score is not a failure of the test; it is the test working - the friction
names the missing nodes/edges, which is the evolutionary loop's next move. Run before any viewer.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

from laplace.research import corpus_ingest as ci


def round_trip(tex_root: Path | str) -> dict[str, Any]:
    tex_root = Path(tex_root)
    net = ci.build_corpus_network(tex_root, semantic=True)   # the measurement path: embed to fill provenance
    nodes, ei = net["nodes"], net["edge_index"]
    postulates = net.get("postulates", set())

    defined = set(nodes)                                   # every atomised element is a node
    bib_keys = {nid[len("ref:"):] for nid in nodes if nid.startswith("ref:")}
    eqs = [n for n in nodes if n.startswith("eq:")]
    figs = [n for n in nodes if n.startswith("fig:")]

    # re-walk the sections to collect every reference the prose actually makes (the demand side)
    main = (tex_root / "main.tex").read_text(encoding="utf-8", errors="ignore")
    cited_keys: set[str] = set()
    ref_targets: list[tuple[str, str]] = []               # (referrer-section, target-label)
    for sec_file in ci._INPUT_RX.findall(main):
        p = tex_root / sec_file
        p = p if p.suffix == ".tex" else p.with_suffix(".tex")
        if not p.is_file():
            continue
        body = p.read_text(encoding="utf-8", errors="ignore")
        sid = "sec:" + Path(sec_file).stem
        cited_keys |= set(ci._cites(body))
        for t in ci._refs(body):
            ref_targets.append((sid, t))

    friction: list[dict] = []

    # FORM: a \ref/\eqref/\cref to a label that does not resolve (dangling pointer)
    for sid, t in ref_targets:
        if t.startswith(("eq:", "fig:", "sec:")) and t not in defined:
            friction.append({"type": "FORM", "what": f"{sid} references undefined {t}"})

    # CONTENT: a DERIVED equation (not a postulate) that appears from nowhere - no derives-from
    # chain (explicit \eqref OR semantic), and never referenced. A postulate needs no provenance.
    referenced_eqs = {t for _, t in ref_targets if t.startswith("eq:")}
    for e in eqs:
        if e in postulates:
            continue
        has_dep = any(r.startswith("eq:") and r != e for r in ei.get(e, []))
        if not has_dep and e not in referenced_eqs:
            friction.append({"type": "CONTENT", "what": f"{e} has no provenance (derived, but no derives-from and never referenced)"})

    # an uncited bibliography entry does NOT make projection non-trivial - it is unused inventory,
    # reported aside, not scored. Triviality is over the elements the artefact actually USES.
    orphan_refs = sorted(bib_keys - cited_keys)
    used_citations = len(bib_keys & cited_keys)
    total = len(eqs) + len(figs) + used_citations + len(ref_targets)
    trivial = total - len(friction)
    score = round(trivial / total, 3) if total else 1.0
    by_type = Counter(f["type"] for f in friction)
    return {
        "paper": tex_root.parts[-3] if len(tex_root.parts) >= 3 else str(tex_root),
        "elements": {"equations": len(eqs), "figures": len(figs),
                     "citations_used": used_citations, "citations_total": len(bib_keys),
                     "internal_refs": len(ref_targets)},
        "triviality_score": score,
        "friction_total": len(friction),
        "friction_by_type": dict(by_type),
        "orphan_refs": len(orphan_refs),
        "postulates": len(postulates),
        "semantic_edges": net.get("n_semantic_edges", 0),
        "friction": friction,
    }


def faithfulness(tex_root: Path | str) -> dict[str, Any]:
    """The DISCRIMINATING metric the saturating triviality score isn't: where the paper EXPLICITLY
    encoded a dependency (\\eqref{eq:X} in eq Y's lead-in = Y derives from X), hold it out and ask
    whether the semantic operator ranks the true X first among the earlier equations. Precision@1 /
    recall@3 against real ground truth, no cross-format alignment. Embeds (cached papers only)."""
    import numpy as np
    tex_root = Path(tex_root)
    leaves, edge_index, _pm = ci.atomise_paper(tex_root)
    eqs = sorted([k for k, lf in leaves.items() if lf.get("kind") == "equation"],
                 key=lambda k: leaves[k].get("ord", 0))
    pos = {e: i for i, e in enumerate(eqs)}
    # ground truth: explicit eq->eq edges to an EARLIER equation
    truth = {e: {r for r in edge_index.get(e, []) if r.startswith("eq:") and r in pos and pos[r] < pos[e]}
             for e in eqs}
    truth = {e: t for e, t in truth.items() if t}
    if not truth:
        return {"error": "no explicit eq->eq ground-truth edges to test"}
    try:
        from laplace.representation.embed_router import get_backend
        backend = get_backend()
        texts = [f"{leaves[e].get('ctx','')} {leaves[e].get('essence','')}"[:512] for e in eqs]
        X = np.asarray(backend.embed(texts), dtype=np.float64)
        X /= np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-12, None)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"embedder unavailable: {exc}"}
    hit1 = hit3 = 0
    for e, tgts in truth.items():
        i = pos[e]
        sims = X[:i] @ X[i]                                   # rank EARLIER equations by similarity
        order = list(np.argsort(-sims))
        ranked = [eqs[j] for j in order]
        if ranked and ranked[0] in tgts:
            hit1 += 1
        if any(r in tgts for r in ranked[:3]):
            hit3 += 1
    n = len(truth)
    return {"ground_truth_edges": n, "precision@1": round(hit1 / n, 3),
            "recall@3": round(hit3 / n, 3), "baseline_random@1": round(
                sum(len(truth[e]) / max(pos[e], 1) for e in truth) / n, 3)}


if __name__ == "__main__":
    import sys
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        "synthetics papers/law-of-laws/manuscript/tex")
    if "--faithfulness" in sys.argv:
        print("FAITHFULNESS (held-out \\eqref ground truth):", faithfulness(root))
        sys.exit(0)
    r = round_trip(root)
    print("elements:", r["elements"])
    print(f"postulates (provenance-exempt): {r['postulates']} | semantic provenance edges added: {r['semantic_edges']}")
    print("TRIVIALITY SCORE:", r["triviality_score"], "| friction:", r["friction_total"],
          "| orphan (unused) refs:", r["orphan_refs"])
    print("friction by type:", r["friction_by_type"])
    for f in r["friction"][:12]:
        print(f"  [{f['type']}] {f['what']}")
    if r["friction_total"] > 12:
        print(f"  ... +{r['friction_total'] - 12} more")
