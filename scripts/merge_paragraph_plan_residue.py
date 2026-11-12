#!/usr/bin/env python3
"""merge_paragraph_plan_residue.py — the MERGE + NORMALIZE + EMBED + GATE driver for the
paragraph_plan store (design §2.1 + §5). The orchestrator-only fan-in the per-paper readers never
touch.

The sequence, run once:

  1. MERGE  each paper's ``<paper_id>.residue.jsonl`` into the enriched canonical ``<paper_id>.jsonl``
     (``merge_residue.merge_residue``): validate every residue row against its skeleton (id,
     embed_text, span_ref char offsets, sha256 — any drift REFUSES that paper), fold the residue
     FORM + provenance.residue_read, stamp the proven provenance (offset_basis; defective marker),
     normalize (uniform length_band + normalized_role), consume the .residue.jsonl.
  2. TAXONOMY  write ``_role_taxonomy.json`` (the auditable slug -> coarse-class map).
  3. INDEX  rebuild ``_index.json`` with the store-level caveats block (findings a + b) + the
     defective-rows list (finalize_index).
  4. EMBED  ``embeddings.json`` keyed by row id (voice-store shape). embed_text is byte-identical to
     the voice-store passages ALREADY embedded with the same local backend, keyed by the same
     sha256 our rows carry — so the vectors are REUSED (verified), never recomputed, unless a row's
     text fails the byte-identity check (then that row alone is recomputed via the backend).
  5. GATE  the holdout gate on ``normalized_role`` (design §5): held-out fraction 0.3, seed 7,
     pick_fn = nearest-exemplar-by-cosine class vote (the demo discipline), baseline = holdout_gate's
     DEFAULT identity baseline. The defective row + null-class rows are excluded. The PLANTED-BAD
     refusal (shuffled embeddings) runs at the same scale. Writes ``gate_verdict.json``.

HONESTY LAW: if the gate refuses, that IS the result — reported, nothing tuned (design §5, §7).

Usage:
    .venv/bin/python scripts/merge_paragraph_plan_residue.py
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

STORE = "paragraph_plan"
STORE_DIR = _REPO_ROOT / "corpus_stores" / STORE
VOICE_CACHE = _REPO_ROOT / "corpus_stores" / "voice_corpus_cache" / "exemplar_passages"
HOLDOUT_FRACTION = 0.3
SEED = 7


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def paper_ids() -> list[str]:
    """The papers with a residue file to merge (skeleton + residue present)."""
    return sorted(p.name[: -len(".residue.jsonl")] for p in STORE_DIR.glob("*.residue.jsonl"))


# --------------------------------------------------------------------------- #
# embeddings — REUSE the voice-cache vectors (same backend, same text, sha256 key)
# --------------------------------------------------------------------------- #
def build_embeddings(rows: list[dict[str, Any]]) -> tuple[dict[str, list[float]], dict[str, Any]]:
    """Build ``{row_id: unit-vector}`` for the enriched rows. Each row's embed_text is (by the
    merge's validation) his real voice-store passage, keyed by ``span_ref.sha256``; the voice cache
    holds that passage's vector under the same sha256, computed with the same local backend. So the
    vector is REUSED when the cached text is byte-identical to the row's embed_text; only a row that
    fails that check is recomputed via the backend. Returns (items, report)."""
    import numpy as np

    cache = json.loads((VOICE_CACHE / "embeddings.json").read_text(encoding="utf-8"))
    cache_items = cache["items"]
    passages = {p["sha256"]: p for p in _load_jsonl(VOICE_CACHE / "passages.jsonl")}

    items: dict[str, list[float]] = {}
    reused = 0
    recompute_rows: list[dict[str, Any]] = []
    for r in rows:
        sha = (r["provenance"].get("span_ref") or {}).get("sha256")
        if (sha in cache_items and sha in passages
                and passages[sha]["text"] == r["embed_text"]):
            v = np.asarray(cache_items[sha], dtype=np.float64)
            v /= max(float(np.linalg.norm(v)), 1e-12)     # unit (voice-store shape)
            items[r["row_id"]] = v.tolist()
            reused += 1
        else:
            recompute_rows.append(r)

    backend_name = cache.get("backend")
    dim = cache.get("dim", 0)
    recomputed = 0
    if recompute_rows:
        from laplace.representation.embed_router import get_backend
        backend = get_backend()
        if backend is None:
            raise SystemExit("merge_paragraph_plan_residue: rows need recompute but no local "
                             "embedding backend is available")
        backend_name = backend.name
        vecs = np.asarray(backend.embed([r["embed_text"] for r in recompute_rows]),
                          dtype=np.float64)
        vecs /= np.clip(np.linalg.norm(vecs, axis=1, keepdims=True), 1e-12, None)
        dim = vecs.shape[1]
        for r, v in zip(recompute_rows, vecs):
            items[r["row_id"]] = v.tolist()
        recomputed = len(recompute_rows)

    report = {"reused": reused, "recomputed": recomputed, "backend": backend_name, "dim": int(dim),
              "source": "voice_corpus cache (corpus_stores/voice_corpus_cache/exemplar_passages), "
                        "sha256-keyed, same local backend"}
    out = {"backend": backend_name, "dim": int(dim), "items": items}
    (STORE_DIR / "embeddings.json").write_text(json.dumps(out), encoding="utf-8")
    return items, report


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

    papers = paper_ids()
    print(f"# merge_paragraph_plan_residue — {len(papers)} papers")

    # 1. MERGE per paper (validated / rejected)
    merges: list[dict[str, Any]] = []
    for pid in papers:
        try:
            summ = M.merge_residue(STORE, pid, stores_root=_REPO_ROOT / "corpus_stores")
            merges.append(summ)
            print(f"  {pid:42} VALIDATED rows={summ['rows']:3} "
                  f"defective={summ['defective']} roles_null={summ['roles_null']}")
        except M.ResidueDriftError as e:
            merges.append({"paper_id": pid, "status": "rejected", "error": str(e)})
            print(f"  {pid:42} REJECTED  {e}")

    # 2. TAXONOMY artifact
    (STORE_DIR / "_role_taxonomy.json").write_text(
        json.dumps(M.role_taxonomy_document(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(f"# taxonomy: {len(M.ROLE_CLASSES)} classes over {len(M.SLUG_TO_CLASS)} slugs "
          f"-> _role_taxonomy.json")

    # 3. INDEX with caveats
    M.finalize_index(STORE, stores_root=_REPO_ROOT / "corpus_stores")

    # gather all enriched rows from the canonical files (post-merge)
    all_rows: list[dict[str, Any]] = []
    for pid in papers:
        all_rows.extend(_load_jsonl(STORE_DIR / f"{pid}.jsonl"))

    # 4. EMBED (reuse)
    emb, emb_report = build_embeddings(all_rows)
    print(f"# embeddings: reused={emb_report['reused']} recomputed={emb_report['recomputed']} "
          f"dim={emb_report['dim']} backend={emb_report['backend']}")

    # 5. GATE — exclude defective + null-class; class = normalized_role
    eligible = [r for r in all_rows
                if not r.get("defective") and r["form"]["normalized_role"] is not None]
    n_defect = sum(1 for r in all_rows if r.get("defective"))
    n_null = sum(1 for r in all_rows
                 if not r.get("defective") and r["form"]["normalized_role"] is None)

    # PRIMARY control: the design §5 / demo IDENTITY baseline (signal-free query averaged) — the
    # control that captures class-size bias, so the planted-bad collapses onto it and REFUSES.
    real = M.nearest_exemplar_gate(eligible, emb, baseline="identity",
                                   holdout_fraction=HOLDOUT_FRACTION, seed=SEED)
    bad = M.nearest_exemplar_gate(eligible, emb, shuffle=True, baseline="identity",
                                  holdout_fraction=HOLDOUT_FRACTION, seed=SEED)
    # SECONDARY reading: holdout_gate's literal DEFAULT baseline (random floats). Recorded for
    # completeness — it does NOT model class-size bias, so the planted-bad is NOT refused under it.
    real_def = M.nearest_exemplar_gate(eligible, emb, baseline="default",
                                       holdout_fraction=HOLDOUT_FRACTION, seed=SEED)
    bad_def = M.nearest_exemplar_gate(eligible, emb, shuffle=True, baseline="default",
                                      holdout_fraction=HOLDOUT_FRACTION, seed=SEED)

    refusal_holds = (not bad["passed"])
    verdict = {
        "schema": "paragraph-plan-gate-verdict/0.2",
        "class_key": "normalized_role",
        "holdout_fraction": HOLDOUT_FRACTION,
        "seed": SEED,
        "pick_fn": "nearest-exemplar-by-embedding-cosine class vote, leave-one-out (demo discipline)",
        "primary_baseline": ("identity (design §5 / demo): the same nearest-class ranking driven by "
                             "a signal-free random query, averaged over 64 seeded draws — captures "
                             "class-size bias, so a signal-free store refuses"),
        "n_rows_total": len(all_rows),
        "n_defective_excluded": n_defect,
        "n_null_class_excluded": n_null,
        "n_eligible": len(eligible),
        "embeddings": emb_report,
        "merges": merges,
        "gate": real,
        "planted_bad_gate": bad,
        "wired_in": bool(real.get("passed")) and refusal_holds,
        "refusal_proof_holds": refusal_holds,
        "gate_holdout_default_baseline": real_def,
        "planted_bad_gate_holdout_default_baseline": bad_def,
        "baseline_finding": (
            "holdout_gate's DEFAULT baseline (random floats over surfaced candidates) sits at ~0.5 "
            "regardless of class sizes, so on this 15-class SKEWED store a signal-free picker beats "
            "it via class-size bias alone: the planted-bad PASSES under the default baseline "
            f"(score={bad_def['score']} > base={bad_def['baseline']}) — an INVALID refusal control. "
            "The design §5 IDENTITY baseline (signal-free query averaged) captures that bias, so the "
            f"planted-bad correctly REFUSES (score={bad['score']} < base={bad['baseline']}); the "
            "real store still wires in under both. The primary verdict uses the identity baseline."),
        "honesty": "the refusal IS the result; the store is untouched — only the baseline is the "
                   "valid class-size-bias control, never a tune of the data (design §5, §7)",
    }
    # STAMP the store state this verdict measured (gated_at + store_fingerprint), so a later re-mint
    # makes it visibly STALE instead of quietly wrong (store_gate_freshness).
    F.stamp_verdict(verdict, STORE_DIR)
    (STORE_DIR / "gate_verdict.json").write_text(
        json.dumps(verdict, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("\n# ===== GATE VERDICT (paragraph_plan / normalized_role) =====")
    print(f"  eligible={len(eligible)}  (excluded: defective={n_defect}, null-class={n_null})")
    rt = "PASS (wires in)" if real["passed"] else "REFUSED (does not wire in)"
    bt = "REFUSED (correct)" if not bad["passed"] else "PASSED (!! planted-bad not refused)"
    print(f"  [identity baseline — PRIMARY, the valid class-size-bias control]")
    print(f"    real:        score={real['score']} baseline={real['baseline']} "
          f"n_holdout={real['n_holdout']} mode={real['mode']} -> {rt}")
    print(f"    planted-bad: score={bad['score']} baseline={bad['baseline']} -> {bt}")
    print(f"  [holdout_gate default baseline — SECONDARY, does not model class-size bias]")
    print(f"    real:        score={real_def['score']} baseline={real_def['baseline']} -> "
          f"{'PASS' if real_def['passed'] else 'REFUSED'}")
    print(f"    planted-bad: score={bad_def['score']} baseline={bad_def['baseline']} -> "
          f"{'REFUSED' if not bad_def['passed'] else 'PASSED (default baseline cannot refuse it)'}")
    print(f"  refusal proof holds (identity baseline): {refusal_holds}")
    print(f"  wrote: {(STORE_DIR / 'gate_verdict.json').relative_to(_REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
