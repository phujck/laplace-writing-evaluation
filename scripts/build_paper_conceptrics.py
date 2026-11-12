#!/usr/bin/env python3
"""build_paper_conceptrics.py — THE FOUR-LENS MECHANICAL STAGE across the 25-paper corpus.

The Wave-4 demo (``scripts/demo_stage_stores.py``) proved the shape on 2 papers x 2 lenses; the
prior cut of this driver grew ONE lens (``section_architecture``) to the extractable tex corpus.
This driver fires ALL FOUR mechanical lenses over the now-complete 25-paper corpus, through THE
SECTION BRIDGE (``pipeline.section_bridge.bridged_network``), the readiness verdict's productized
precondition. Per paper it:

  1. builds the full-fidelity conceptric through the bridge (the proven UP operator over the split
     ``\\input{}`` layout, per-section real prose re-attached);
  2. derives the four MECHANICAL view stores as VIEWS of that ONE net (never a second
     decomposition — design §1c): ``section_architecture`` (§2.2), ``spine_chain`` (§2.3),
     ``derivation_walk`` (§2.4), ``figure_caption`` (§2.5);
  3. writes each store's per-paper namespaced JSONL + merged ``_index.json`` (design §3), embeds it
     with the SAME local ONNX backend (embed_text basis per each schema's row shape), and runs the
     SAME per-store holdout gate at corpus scale — real vs a planted-signal-free store.

THE CENSUS spans TWO tex homes (``papers_tex`` in ``corpus_friction/stage_corpus_census.json``):
his committed exemplars (``voice_corpus/exemplars/<slug>/``) and the arXiv sources
(``published_corpus/tex/<paper_id>/``). A paper the bridge cannot lift (no inline ``\\section``, no
resolving ``\\input`` layout — ``polaron-imposters`` and ``superoscillations`` in the voice home;
``driven-imposters`` in the arXiv home) is reported BY NAME per store, never a silent 2-node
conceptric.

THE GATE LAW (design §5, §7). Each store faces its holdout gate over the class its most
class-shaped MECHANICAL field carries:

  * ``section_architecture`` -> ``job``           (coarse section function-class proxy)
  * ``spine_chain``          -> ``ladder_move``    (dep-arity move-class proxy)
  * ``derivation_walk``      -> ``step_kind``      (dep-arity step-class proxy: define/advance/combine)
  * ``figure_caption``       -> ``caption_size``   (caption-length class: terse/standard/expansive)

EXPECTED (prior evidence): the mechanical proxies REFUSE — the real signal is model residue (the
FORM abstractions the readers enrich next), so a mechanical-class gate carries no prose signal
beyond the base rate. The refusal is reported honestly and TUNED NOTHING (design §7). The stores'
value at this stage is the mechanical skeleton + node-traceable ``span_ref`` the model readers
enrich; the residue each store owes is in ``stage_store.RESIDUE_FIELDS``, echoed in each verdict.

Determinism: the derivers + bridge are deterministic, so papers already built keep byte-identical
JSONL. Model tokens ~zero (the views are mechanical); embeddings are the vendored local bge-small
over ONNX (no network). Embeddings + gate are REUSED verbatim from the demo module.

Usage:
    .venv/bin/python scripts/build_paper_conceptrics.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

# reuse the demo's embedding + gate verbatim (identical methodology, one source of truth)
import demo_stage_stores as demo  # noqa: E402

from laplace.representation.embed_router import get_backend  # noqa: E402
from laplace.pipeline import stage_store  # noqa: E402
from laplace.pipeline.section_bridge import SectionBridgeError, bridged_network  # noqa: E402

CENSUS = _REPO_ROOT / "corpus_friction" / "stage_corpus_census.json"
STORES_ROOT = demo.STORES_ROOT
HOLDOUT_FRACTION = demo.HOLDOUT_FRACTION       # 0.3 (the demo's)

# the four mechanical lenses, their deriver, and the most class-shaped MECHANICAL field each
# schema carries (the gate class — see the module docstring / design §5).
STORES: dict[str, dict[str, Any]] = {
    "section_architecture": {"derive": stage_store.derive_section_architecture, "class": "job"},
    "spine_chain":          {"derive": stage_store.derive_spine_chain,          "class": "ladder_move"},
    "derivation_walk":      {"derive": stage_store.derive_derivation_walk,      "class": "step_kind"},
    "figure_caption":       {"derive": stage_store.derive_figure_caption,       "class": "caption_size"},
}


def _node_counts(net: dict[str, Any]) -> dict[str, int]:
    c = {"section": 0, "equation": 0, "figure": 0}
    for n in net["nodes"].values():
        k = n.get("kind")
        if k in c:
            c[k] += 1
    return c


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

    backend = get_backend()
    if backend is None:
        print("build_paper_conceptrics: no local embedding backend (models/fastembed "
              "unavailable); this driver needs the vendored ONNX model.", file=sys.stderr)
        return 1

    census = json.loads(CENSUS.read_text(encoding="utf-8"))
    papers = census["papers_tex"]
    homes = {"voice_corpus": 0, "published_corpus": 0}
    for e in papers:
        if e["tex_files"][0].startswith("voice_corpus"):
            homes["voice_corpus"] += 1
        elif e["tex_files"][0].startswith("published_corpus"):
            homes["published_corpus"] += 1
    print(f"# build_paper_conceptrics — FOUR mechanical lenses across the census "
          f"({len(papers)} tex papers: {homes['voice_corpus']} voice / "
          f"{homes['published_corpus']} arXiv)")
    print(f"# stores={list(STORES)} backend={backend.name} holdout_fraction={HOLDOUT_FRACTION}")

    # per-store accumulators
    store_rows: dict[str, list[dict[str, Any]]] = {s: [] for s in STORES}
    store_per_paper: dict[str, dict[str, int]] = {s: {} for s in STORES}
    store_no_rows: dict[str, list[dict[str, str]]] = {s: [] for s in STORES}
    unhandled: list[dict[str, str]] = []           # bridge could not lift the paper at all
    bridge_report: list[dict[str, Any]] = []       # every paper: built (+counts) or unbridgeable

    for entry in papers:
        pid = entry["paper_id"]
        tex_rel = entry["tex_files"][0]
        home = "voice" if tex_rel.startswith("voice_corpus") else "arxiv"
        tex_path = _REPO_ROOT / tex_rel
        try:
            net = bridged_network(tex_path, pid)
        except SectionBridgeError as e:
            unhandled.append({"paper_id": pid, "home": home, "tex": tex_rel, "reason": str(e)})
            bridge_report.append({"paper_id": pid, "home": home, "built": False, "reason": str(e)})
            print(f"  UNBRIDGEABLE  {pid:<52} [{home}] {e}")
            continue

        nc = _node_counts(net)
        rows_by_store: dict[str, int] = {}
        for store, spec in STORES.items():
            rows = spec["derive"](net, pid)
            if not rows:
                # section_architecture with 0 rows means no section nodes at all -> unhandled for
                # that store; the equation/figure lenses legitimately yield 0 rows for a paper with
                # no equations / no figures — a NO-ROWS finding, not an unbridgeable paper.
                reason = ("bridged but 0 section nodes"
                          if store == "section_architecture"
                          else f"bridged, no {store.replace('_', '-')} rows "
                               f"({nc['equation']} eq / {nc['figure']} fig)")
                store_no_rows[store].append({"paper_id": pid, "reason": reason})
                rows_by_store[store] = 0
                continue
            stage_store.write_store(store, pid, rows, stores_root=STORES_ROOT)
            store_rows[store].extend(rows)
            store_per_paper[store][pid] = len(rows)
            rows_by_store[store] = len(rows)

        bridge_report.append({
            "paper_id": pid, "home": home, "built": True, "bridged": net.get("bridged"),
            "nodes": len(net["nodes"]), **nc, "rows": rows_by_store})
        print(f"  BUILT  {pid:<52} [{home}] {len(net['nodes'])} nodes "
              f"({nc['section']}s/{nc['equation']}e/{nc['figure']}f) "
              f"rows: SA={rows_by_store['section_architecture']} "
              f"SC={rows_by_store['spine_chain']} DW={rows_by_store['derivation_walk']} "
              f"FC={rows_by_store['figure_caption']}"
              f"{'' if net.get('bridged') else '  [passthrough]'}")

    # per store: embed the merged store + run the SAME gate (real + planted-bad refusal control)
    print("\n# ===== PER-STORE GATES (mechanical class @ corpus scale) =====")
    store_verdicts: dict[str, dict[str, Any]] = {}
    refusal_invariant_ok = True
    for store, spec in STORES.items():
        rows = store_rows[store]
        class_key = spec["class"]
        emb = demo.embed_store(store, rows, backend)
        real = demo.run_store_gate(rows, emb, class_key, holdout_fraction=HOLDOUT_FRACTION)
        bad = demo.run_store_gate(rows, emb, class_key, shuffle=True,
                                  holdout_fraction=HOLDOUT_FRACTION)
        n_classes = len({r["form"][class_key] for r in rows})
        # the honesty invariant: a planted-signal-free store must NOT pass. "insufficient" (too
        # few holdout / single-class) counts as a non-pass — it is honest, not a fabricated pass.
        bad_passed = bool(bad.get("passed"))
        refusal_invariant_ok = refusal_invariant_ok and not bad_passed

        verdict = {
            "schema": "four-lens-corpus-verdict/0.1",
            "store": store,
            "class_key": class_key,
            "class_is": "mechanical PROXY (the faithful class is model residue)"
                        if store in ("section_architecture", "spine_chain", "derivation_walk")
                        else "mechanical caption-length class (caption rhetoric is model residue)",
            "backend": backend.name,
            "holdout_fraction": HOLDOUT_FRACTION,
            "census": str(CENSUS.relative_to(_REPO_ROOT)),
            "papers_built": sorted(store_per_paper[store]),
            "papers_no_rows": store_no_rows[store],
            "papers_unhandled": unhandled,
            "rows_total": len(rows),
            "n_classes": n_classes,
            "rows_per_paper": dict(sorted(store_per_paper[store].items())),
            "dim": (len(next(iter(emb.values()))) if emb else 0),
            "gate": real,
            "planted_bad_gate": bad,
            "wired_in": bool(real.get("passed")),
            "residue_fields": stage_store.RESIDUE_FIELDS.get(store, []),
            "finding": ("wires in — the mechanical class carries prose signal beyond the base rate"
                        if real.get("passed") else
                        "REFUSED — the mechanical proxy carries no prose signal beyond the base "
                        "rate; the faithful class is model residue (design §7). The store's value "
                        "is its mechanical skeleton + node-traceable span_refs, not this gate."),
        }
        store_verdicts[store] = verdict
        (STORES_ROOT / store / "corpus_verdict.json").write_text(
            json.dumps(verdict, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        g, b = real, bad
        real_tag = "PASS (wires in)" if g.get("passed") else "REFUSED (does not wire in)"
        bad_tag = "refused" if not bad_passed else "PASSED (!! honesty invariant broken)"
        print(f"  {store:<22} rows={len(rows):<4} classes={n_classes:<2} "
              f"real: score={g.get('score')} base={g.get('baseline')} mode={g.get('mode')} "
              f"-> {real_tag}")
        print(f"  {'':22} planted-bad: score={b.get('score')} base={b.get('baseline')} -> {bad_tag}")

    # the combined verdict + per-paper bridge report
    combined = {
        "schema": "four-lens-corpus-summary/0.1",
        "backend": backend.name,
        "holdout_fraction": HOLDOUT_FRACTION,
        "census": str(CENSUS.relative_to(_REPO_ROOT)),
        "papers_total": len(papers),
        "papers_built": sorted({r["paper_id"] for r in bridge_report if r["built"]}),
        "papers_unhandled": unhandled,
        "bridge_report": bridge_report,
        "stores": {s: {"rows_total": store_verdicts[s]["rows_total"],
                       "n_classes": store_verdicts[s]["n_classes"],
                       "papers_with_rows": len(store_per_paper[s]),
                       "gate": store_verdicts[s]["gate"],
                       "planted_bad_gate": store_verdicts[s]["planted_bad_gate"],
                       "wired_in": store_verdicts[s]["wired_in"]} for s in STORES},
        "refusal_invariant_ok": refusal_invariant_ok,
        "residue_fields": stage_store.RESIDUE_FIELDS,
    }
    out = STORES_ROOT / "four_lens_corpus_verdict.json"
    out.write_text(json.dumps(combined, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # the machine-readable summary
    print("\n# ===== CORPUS BUILD SUMMARY =====")
    print(json.dumps({
        "papers_total": len(papers),
        "papers_built": len(combined["papers_built"]),
        "papers_unhandled": [u["paper_id"] for u in unhandled],
        "rows_per_store": {s: store_verdicts[s]["rows_total"] for s in STORES},
        "papers_with_rows_per_store": {s: len(store_per_paper[s]) for s in STORES},
        "wired_in": {s: store_verdicts[s]["wired_in"] for s in STORES},
    }, indent=2))

    if unhandled:
        print(f"\nUNBRIDGEABLE papers ({len(unhandled)}):")
        for u in unhandled:
            print(f"  - {u['paper_id']} [{u['home']}]: {u['reason']}")

    print(f"\nREFUSAL INVARIANT (no planted-bad store passed): {refusal_invariant_ok}")
    print(f"WIRED IN: {[s for s in STORES if store_verdicts[s]['wired_in']] or 'none (all refused)'}")
    print(f"wrote: {out.relative_to(_REPO_ROOT)} + per-store corpus_verdict.json")
    # exit non-zero only if the honesty invariant (planted-bad refusal) breaks; a real-store
    # refusal at corpus scale is a FINDING to report, not a driver failure (design §7).
    return 0 if refusal_invariant_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
