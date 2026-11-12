#!/usr/bin/env python3
"""merge_four_lens_residue.py — the MERGE + NORMALIZE + GATE driver for the four mechanical-view
stage stores (section_architecture / spine_chain / derivation_walk / figure_caption), design
§2.2-§2.5 + §5. The Stage-B fan-in over the fleet's residue: the reciprocal of
``merge_paragraph_plan_residue.py`` (the §2.1 precedent), generalized across four stores.

WHY STAGE B RE-GATES. Stage A (``four_lens_corpus_verdict.json``) gated each store on its MECHANICAL
proxy class (the num-dependency ``ladder_move``, the arity ``step_kind``, the position-keyword
``job``, the length ``caption_size``) and three of four REFUSED — the design's own prediction that a
mechanical proxy carries no prose signal. This driver folds the fleet's FAITHFUL model-read classes
onto those skeletons and re-gates on THEM: does his-prose cosine retrieval surface the right FAITHFUL
class for a held-out row? Whatever the answer, the honesty law holds — the refusal IS the result;
nothing is tuned.

The sequence, per store, run once:

  1. MERGE  each ``<paper>.residue.jsonl`` into the enriched canonical ``<paper>.jsonl``
     (``merge_residue.merge_residue`` dispatching on the store's ``StoreSpec``): validate every
     residue row byte-identical to its skeleton on all invariants (REFUSE the paper on drift, named),
     fold ONLY the reader-filled form fields + ``provenance.residue_read``, preserve the overridden
     mechanical proxy for audit, derive the coarse ``normalized_job`` (section only), stamp the
     ledger's defective (a+b) / caveat (c+d) marks, consume the ``.residue.jsonl``.
  2. TAXONOMY  write ``_job_taxonomy.json`` (section_architecture only — the auditable slug->class map).
  3. INDEX  rebuild ``_index.json`` with the store-level caveats block (finding e), the
     ``defective_rows`` + ``caveat_rows`` lists, the ``gate_class`` name (``finalize_index``).
  4. EMBED  REUSE the store's committed ``embeddings.json`` (row-id-keyed, same local bge-small
     backend; embed_text is byte-identical post-merge by the drift validation, so the vectors are
     unchanged). Coverage is verified; a row whose store lacks an embedding would be recomputed
     (none are, at Stage B). The (b) truncated rows keep their embeddings — built on corrupted text —
     and are EXCLUDED from the gate.
  5. GATE  the holdout gate on the store's FAITHFUL gate class (design §5): held-out fraction 0.3,
     seed 7, pick_fn = nearest-exemplar-by-cosine class vote (the demo discipline). The PRIMARY
     control is the design §5 / demo IDENTITY baseline (signal-free query averaged — captures
     class-size bias, so the planted-bad refuses); the holdout_gate DEFAULT random-float baseline is
     recorded as the secondary reading (as the paragraph precedent did). Defective + null-class rows
     excluded. The PLANTED-BAD refusal (shuffled embeddings) runs at the same scale. Writes
     ``<store>/gate_verdict.json``. For figure_caption, the mechanical ``caption_size`` gate (Stage
     A's PASS) is RE-MEASURED on the clean subset (the 14 defective rows removed) — the honest verdict.

HONESTY LAW: if a gate refuses, that IS the result — reported, nothing tuned (design §5, §7).

Usage:
    .venv/bin/python scripts/merge_four_lens_residue.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from laplace.pipeline import merge_residue as M  # noqa: E402
from laplace.pipeline import store_gate_freshness as F  # noqa: E402

STORES = ["section_architecture", "spine_chain", "derivation_walk", "figure_caption"]
CORPUS_STORES = _REPO_ROOT / "corpus_stores"
HOLDOUT_FRACTION = 0.3
SEED = 7

#: Stage A's figure_caption caption_size gate (from four_lens_corpus_verdict.json) — the PASS the
#: task flags as "partly on corrupted lengths". The re-measurement on the clean subset compares here.
STAGE_A_CAPTION_SIZE = {"score": 0.65625, "baseline": 0.53125, "passed": True, "note":
                        "Stage A default-baseline PASS, computed over ALL 106 rows incl the 14 "
                        "later-flagged defective (truncated/dead) whose caption_size is corrupted"}


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def paper_ids(store: str) -> list[str]:
    d = CORPUS_STORES / store
    return sorted(p.name[: -len(".residue.jsonl")] for p in d.glob("*.residue.jsonl"))


def reuse_embeddings(store: str, rows: list[dict[str, Any]]) -> tuple[dict[str, list[float]], dict[str, Any]]:
    """REUSE the store's committed row-id-keyed ``embeddings.json`` (design §5 / task 4). embed_text
    is byte-identical to the pre-merge skeleton (the drift validation enforces it), so every vector
    is unchanged; only a row whose store LACKS an embedding is recomputed via the local backend.
    Returns (row_id -> unit vector, report). embeddings.json is left untouched when nothing is
    recomputed (so the reuse is byte-provable in git)."""
    import numpy as np
    cache = json.loads((CORPUS_STORES / store / "embeddings.json").read_text(encoding="utf-8"))
    items_in = cache["items"]
    out: dict[str, list[float]] = {}
    missing: list[dict[str, Any]] = []
    for r in rows:
        v = items_in.get(r["row_id"])
        if v is None:
            missing.append(r)
            continue
        vv = np.asarray(v, dtype=np.float64)
        vv /= max(float(np.linalg.norm(vv)), 1e-12)
        out[r["row_id"]] = vv.tolist()
    recomputed = 0
    backend_name, dim = cache.get("backend"), cache.get("dim", 0)
    if missing:
        from laplace.representation.embed_router import get_backend
        backend = get_backend()
        if backend is None:
            raise SystemExit(f"merge_four_lens_residue: {store} has {len(missing)} rows with no "
                             "embedding and no local backend is available")
        backend_name = backend.name
        vecs = np.asarray(backend.embed([r["embed_text"] for r in missing]), dtype=np.float64)
        vecs /= np.clip(np.linalg.norm(vecs, axis=1, keepdims=True), 1e-12, None)
        dim = vecs.shape[1]
        for r, v in zip(missing, vecs):
            out[r["row_id"]] = v.tolist()
        recomputed = len(missing)
        # a recompute means the committed file was incomplete: rewrite it row-id-keyed.
        items_in.update({r["row_id"]: out[r["row_id"]] for r in missing})
        (CORPUS_STORES / store / "embeddings.json").write_text(
            json.dumps({"backend": backend_name, "dim": int(dim), "items": items_in}),
            encoding="utf-8")
    report = {"reused": len(rows) - recomputed, "recomputed": recomputed,
              "backend": backend_name, "dim": int(dim),
              "source": "committed corpus_stores/<store>/embeddings.json (row-id keyed, "
                        "same local bge-small backend; embed_text byte-identical post-merge)"}
    return out, report


def run_gate(eligible: list[dict[str, Any]], emb: dict[str, list[float]], class_key: str) -> dict[str, Any]:
    """Real + planted-bad, under BOTH baselines (identity primary, default secondary)."""
    real = M.nearest_exemplar_gate(eligible, emb, class_key=class_key, baseline="identity",
                                   holdout_fraction=HOLDOUT_FRACTION, seed=SEED)
    bad = M.nearest_exemplar_gate(eligible, emb, class_key=class_key, shuffle=True,
                                  baseline="identity", holdout_fraction=HOLDOUT_FRACTION, seed=SEED)
    real_def = M.nearest_exemplar_gate(eligible, emb, class_key=class_key, baseline="default",
                                       holdout_fraction=HOLDOUT_FRACTION, seed=SEED)
    bad_def = M.nearest_exemplar_gate(eligible, emb, class_key=class_key, shuffle=True,
                                      baseline="default", holdout_fraction=HOLDOUT_FRACTION, seed=SEED)
    return {"identity": {"real": real, "planted_bad": bad},
            "default": {"real": real_def, "planted_bad": bad_def}}


def corroborate_truncation(store: str, all_rows: list[dict[str, Any]], spec) -> dict[str, Any]:
    """Mechanically CROSS-CHECK the ledger's caption-truncated list (finding b) against the data: a
    named truncated row must LOOK truncated (embed_text a bare \\label{} fragment); a row that looks
    truncated but is NOT on the list is surfaced (never silently kept)."""
    named = {rid for rid, why in spec.defective_rows.items() if why == "caption-truncated-mechanical"}
    named_not_truncated, unlisted_truncated = [], []
    for r in all_rows:
        looks = M.looks_caption_truncated(r["embed_text"])
        if r["row_id"] in named and not looks:
            named_not_truncated.append(r["row_id"])
        if looks and r["row_id"] not in named:
            unlisted_truncated.append(r["row_id"])
    return {"named_truncated": sorted(named),
            "named_but_not_label_fragment": sorted(named_not_truncated),
            "label_fragment_but_unlisted": sorted(unlisted_truncated)}


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

    overall: dict[str, Any] = {}
    for store in STORES:
        spec = M.FOUR_LENS_SPECS[store]
        store_dir = CORPUS_STORES / store
        papers = paper_ids(store)
        print(f"\n# ===== {store} — {len(papers)} papers, gate class '{spec.gate_class_key}' =====")

        # 1. MERGE
        merges: list[dict[str, Any]] = []
        for pid in papers:
            try:
                summ = M.merge_residue(store, pid, stores_root=CORPUS_STORES)
                merges.append(summ)
            except M.ResidueDriftError as e:
                merges.append({"paper_id": pid, "status": "rejected", "error": str(e)})
                print(f"  {pid:52} REJECTED  {e}")
        rejected = [m for m in merges if m["status"] == "rejected"]

        # 2. TAXONOMY artifact (section_architecture only)
        if spec.taxonomy is not None:
            (store_dir / spec.taxonomy.file).write_text(
                json.dumps(spec.taxonomy.doc(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")

        # 3. INDEX with caveats
        M.finalize_index(store, stores_root=CORPUS_STORES)

        # gather enriched rows (post-merge, only successfully-merged papers on disk)
        all_rows: list[dict[str, Any]] = []
        for jf in sorted(store_dir.glob("*.jsonl")):
            all_rows.extend(_load_jsonl(jf))

        # 4. EMBED — reuse
        emb, emb_report = reuse_embeddings(store, all_rows)

        # 5. GATE on the faithful class
        ck = spec.gate_class_key
        n_defect = sum(1 for r in all_rows if r.get("defective"))
        n_caveat = sum(1 for r in all_rows if r.get("caveat"))
        eligible = [r for r in all_rows
                    if not r.get("defective") and r["form"].get(ck) is not None]
        n_null = sum(1 for r in all_rows
                     if not r.get("defective") and r["form"].get(ck) is None)
        classes_present = sorted({r["form"][ck] for r in eligible})
        g = run_gate(eligible, emb, ck)
        real, bad = g["identity"]["real"], g["identity"]["planted_bad"]
        real_def, bad_def = g["default"]["real"], g["default"]["planted_bad"]
        refusal_holds = not bad["passed"]

        verdict: dict[str, Any] = {
            "schema": "four-lens-gate-verdict/0.1",
            "store": store,
            "stage": "B (faithful model-read class; Stage A gated the mechanical proxy)",
            "class_key": ck,
            "classes_present": classes_present,
            "n_classes": len(classes_present),
            "holdout_fraction": HOLDOUT_FRACTION,
            "seed": SEED,
            "backend": emb_report["backend"],
            "pick_fn": "nearest-exemplar-by-embedding-cosine class vote, leave-one-out (demo discipline)",
            "primary_baseline": ("identity (design §5 / demo): the same nearest-class ranking driven "
                                 "by a signal-free random query, averaged over 64 seeded draws — "
                                 "captures class-size bias, so a signal-free store refuses"),
            "n_rows_total": len(all_rows),
            "n_defective_excluded": n_defect,
            "n_caveat_flagged_kept": n_caveat,
            "n_null_class_excluded": n_null,
            "n_eligible": len(eligible),
            "papers_rejected_on_drift": rejected,
            "embeddings": emb_report,
            "merges": merges,
            "gate": real,
            "planted_bad_gate": bad,
            "wired_in": bool(real.get("passed")) and refusal_holds,
            "refusal_proof_holds": refusal_holds,
            "gate_holdout_default_baseline": real_def,
            "planted_bad_gate_holdout_default_baseline": bad_def,
            "honesty": ("the refusal IS the result; the store is untouched — only the baseline is the "
                        "valid class-size-bias control, never a tune of the data (design §5, §7)"),
        }

        # figure_caption: RE-MEASURE the mechanical caption_size gate on the CLEAN subset
        if store == "figure_caption":
            clean = [r for r in all_rows
                     if not r.get("defective") and r["form"].get("caption_size") is not None]
            cs = run_gate(clean, emb, "caption_size")
            verdict["caption_size_remeasure_clean"] = {
                "note": ("Stage A's caption_size PASS was computed over all rows INCLUDING the 14 "
                         "defective (truncated/dead) rows whose caption_size is corrupted; this "
                         "re-measurement drops them (the honest verdict for the mechanical length "
                         "class). Reported under BOTH baselines; Stage A used the default one."),
                "stage_a": STAGE_A_CAPTION_SIZE,
                "n_clean": len(clean),
                "classes_present": sorted({r["form"]["caption_size"] for r in clean}),
                "identity_baseline": {"real": cs["identity"]["real"],
                                      "planted_bad": cs["identity"]["planted_bad"]},
                "default_baseline": {"real": cs["default"]["real"],
                                     "planted_bad": cs["default"]["planted_bad"]},
            }
            verdict["truncation_corroboration"] = corroborate_truncation(store, all_rows, spec)

        # STAMP the store state this verdict measured (gated_at + store_fingerprint), so a later
        # re-mint makes it visibly STALE instead of quietly wrong (store_gate_freshness).
        F.stamp_verdict(verdict, store_dir)
        (store_dir / "gate_verdict.json").write_text(
            json.dumps(verdict, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        # terse console line
        rt = "PASS" if real["passed"] else "REFUSED"
        bt = "REFUSED(correct)" if not bad["passed"] else "PASSED(!!)"
        print(f"  merged={len(papers) - len(rejected)}/{len(papers)}  eligible={len(eligible)}  "
              f"defective={n_defect}  caveat={n_caveat}  null={n_null}  classes={len(classes_present)}")
        print(f"  emb: reused={emb_report['reused']} recomputed={emb_report['recomputed']}")
        print(f"  [identity]  real score={real['score']} base={real['baseline']} "
              f"n_hold={real['n_holdout']} -> {rt}   planted-bad {bad['score']}/{bad['baseline']} -> {bt}")
        print(f"  [default]   real score={real_def['score']} base={real_def['baseline']}   "
              f"planted-bad {bad_def['score']}/{bad_def['baseline']}")
        if store == "figure_caption":
            cs = verdict["caption_size_remeasure_clean"]
            csi, csd = cs["identity_baseline"]["real"], cs["default_baseline"]["real"]
            print(f"  caption_size RE-MEASURE (clean n={cs['n_clean']}): "
                  f"identity {csi['score']}/{csi['baseline']} -> {'PASS' if csi['passed'] else 'REFUSED'}  |  "
                  f"default {csd['score']}/{csd['baseline']} -> {'PASS' if csd['passed'] else 'REFUSED'}  "
                  f"(Stage A default PASS was {STAGE_A_CAPTION_SIZE['score']}/{STAGE_A_CAPTION_SIZE['baseline']})")
            tc = verdict["truncation_corroboration"]
            print(f"  truncation corroboration: named={len(tc['named_truncated'])} "
                  f"mismatches={tc['named_but_not_label_fragment']} "
                  f"unlisted={tc['label_fragment_but_unlisted']}")

        overall[store] = {"gate": real, "planted_bad": bad, "wired_in": verdict["wired_in"],
                          "n_eligible": len(eligible), "n_defective": n_defect, "n_classes": len(classes_present)}

    print("\n# ===== SUMMARY =====")
    for s, v in overall.items():
        print(f"  {s:22} eligible={v['n_eligible']:3} defect={v['n_defective']:2} "
              f"classes={v['n_classes']} gate={v['gate']['score']}/{v['gate']['baseline']} "
              f"-> {'PASS' if v['gate']['passed'] else 'REFUSED'}  "
              f"planted-bad refused={not v['planted_bad']['passed']}  wired_in={v['wired_in']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
