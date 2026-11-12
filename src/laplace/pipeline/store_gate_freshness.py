"""store_gate_freshness — a corpus-store gate verdict is a MEASUREMENT OF A STORE STATE, and it
must say which state it measured.

THE FAILURE THIS ORGAN CLOSES. ``b17378c2`` re-minted 280 rows' ``embed_text`` across
``corpus_stores/section_architecture`` and ``corpus_stores/paragraph_plan`` and regenerated both
``embeddings.json``. The gate verdicts sitting in those directories were deliberately left untouched
(re-running a gate inside a repair commit launders the measurement) — and, carrying neither a
timestamp nor any fingerprint of the rows they scored, they went on reading as live verdicts of a
store that no longer existed. Nothing in the repository could tell a reader otherwise.

THE RULE. Every verdict carries ``gated_at`` and a ``store_fingerprint``: the sha256 of the store's
(row_id, embed_text) pairs and the sha256 of its committed ``embeddings.json``. A re-mint moves both
hashes, so :func:`freshness` calls the verdict STALE the moment the store moves under it. A verdict
without the stamp is UNSTAMPED — treated as stale, never as fresh: silence is not freshness.

THE TWO EXITS from staleness, both honest, never a silent carry:

  * RE-DERIVE (:func:`regate`) — re-run the gate ONLY: the merged rows and the committed embeddings
    are read, never rewritten, and no residue is consumed. This is the gate-only caller the
    merge drivers do not provide (``merge_four_lens_residue.py`` / ``merge_paragraph_plan_residue.py``
    re-derive the rows as well, which would destroy the folded residue).
  * INVALIDATE (:func:`invalidate`) — for a verdict that CANNOT be re-derived because the class it
    scored no longer exists under that key. The numbers are left exactly as measured; a
    ``superseded`` block is added naming the store state at invalidation and where the live verdict
    now is. Marking a measurement dead is not laundering it; overwriting it would be.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FINGERPRINT_SCHEMA = "store-gate-fingerprint/0.1"

#: statuses :func:`freshness` can return. STALE and UNSTAMPED are both "do not trust this verdict";
#: SUPERSEDED is a verdict explicitly retired by :func:`invalidate` — dead by declaration, not by
#: neglect, and therefore not an open red.
FRESH, STALE, UNSTAMPED, MISSING, SUPERSEDED = "FRESH", "STALE", "UNSTAMPED", "MISSING", "SUPERSEDED"

#: the statuses a reader must NOT trust as a live measurement of the store.
UNTRUSTWORTHY = (STALE, UNSTAMPED, SUPERSEDED)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_row_files(store_dir: Path) -> list[Path]:
    """The store's canonical per-paper row files: ``*.jsonl`` minus the un-merged ``*.residue.jsonl``
    and minus the ``_``-prefixed store artifacts (index, taxonomy)."""
    return sorted(p for p in store_dir.glob("*.jsonl")
                  if not p.name.endswith(".residue.jsonl") and not p.name.startswith("_"))


def load_rows(store_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for f in canonical_row_files(store_dir):
        rows.extend(json.loads(ln) for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip())
    return rows


def store_fingerprint(store_dir: Path) -> dict[str, Any]:
    """The identity of the store state a gate scored. ``rows_sha256`` moves when any row's
    ``embed_text`` or the row set moves (a re-mint); ``embeddings_sha256`` moves when the committed
    vectors are regenerated. Either one moving invalidates a verdict."""
    rows = load_rows(store_dir)
    payload = "\n".join(f"{r['row_id']}\x00{r.get('embed_text', '')}"
                        for r in sorted(rows, key=lambda r: r["row_id"]))
    fp: dict[str, Any] = {
        "schema": FINGERPRINT_SCHEMA,
        "n_rows": len(rows),
        "rows_sha256": _sha(payload),
        "row_files": [p.name for p in canonical_row_files(store_dir)],
    }
    emb_path = store_dir / "embeddings.json"
    if emb_path.exists():
        raw = emb_path.read_text(encoding="utf-8")
        cache = json.loads(raw)
        fp |= {
            "embeddings_sha256": _sha(raw),
            "embeddings_backend": cache.get("backend"),
            "embeddings_dim": cache.get("dim"),
            "n_embeddings": len(cache.get("items", {})),
        }
    else:
        fp |= {"embeddings_sha256": None, "embeddings_backend": None,
               "embeddings_dim": None, "n_embeddings": 0}
    return fp


#: the fingerprint fields compared for staleness (``row_files`` is descriptive, not load-bearing).
_COMPARED = ("n_rows", "rows_sha256", "embeddings_sha256", "embeddings_backend",
             "embeddings_dim", "n_embeddings")


def stamp_verdict(verdict: dict[str, Any], store_dir: Path, *, now: str | None = None) -> dict[str, Any]:
    """Stamp a verdict with the state it measured. Called by whatever writes the verdict — the merge
    drivers and :func:`regate` alike — so a verdict can never reach disk anonymous again."""
    verdict["gated_at"] = now or _now_iso()
    verdict["store_fingerprint"] = store_fingerprint(store_dir)
    return verdict


def freshness(store_dir: Path, verdict_file: str = "gate_verdict.json", *,
              current: dict[str, Any] | None = None) -> dict[str, Any]:
    """Is this verdict a measurement of the store as it stands? Returns a typed row; ``drift`` names
    every fingerprint field that moved."""
    path = store_dir / verdict_file
    row: dict[str, Any] = {"store": store_dir.name, "verdict": verdict_file,
                           "path": str(path), "status": MISSING, "drift": [], "gated_at": None}
    if not path.exists():
        return row
    verdict = json.loads(path.read_text(encoding="utf-8"))
    row["gated_at"] = verdict.get("gated_at")
    if isinstance(verdict.get("superseded"), dict):
        row["status"] = SUPERSEDED
        row["drift"] = [f"superseded by {verdict['superseded'].get('superseded_by')} at "
                        f"{verdict['superseded'].get('invalidated_at')}"]
        return row
    stamped = verdict.get("store_fingerprint")
    if not isinstance(stamped, dict):
        row["status"] = UNSTAMPED
        row["drift"] = ["store_fingerprint absent — the verdict names no store state"]
        return row
    cur = current if current is not None else store_fingerprint(store_dir)
    drift = [f"{k}: verdict={stamped.get(k)!r} store={cur.get(k)!r}"
             for k in _COMPARED if stamped.get(k) != cur.get(k)]
    row["status"] = FRESH if not drift else STALE
    row["drift"] = drift
    return row


def store_freshness(store_dir: Path) -> list[dict[str, Any]]:
    """Freshness of every verdict file in the store, one row each."""
    cur = store_fingerprint(store_dir)
    names = sorted(p.name for p in store_dir.glob("*verdict*.json"))
    return [freshness(store_dir, n, current=cur) for n in names]


def gate_eligible(rows: list[dict[str, Any]], class_key: str) -> dict[str, Any]:
    """The gate-eligible subset and its exclusion census — defective rows and null-class rows out,
    exactly as the merge drivers select them."""
    eligible = [r for r in rows if not r.get("defective") and r["form"].get(class_key) is not None]
    return {
        "eligible": eligible,
        "n_rows_total": len(rows),
        "n_defective_excluded": sum(1 for r in rows if r.get("defective")),
        "n_caveat_flagged_kept": sum(1 for r in rows if r.get("caveat")),
        "n_null_class_excluded": sum(1 for r in rows
                                     if not r.get("defective") and r["form"].get(class_key) is None),
        "n_eligible": len(eligible),
        "classes_present": sorted({r["form"][class_key] for r in eligible}),
    }


def load_embeddings(store_dir: Path, rows: list[dict[str, Any]]) -> tuple[dict[str, list[float]], dict[str, Any]]:
    """READ the committed row-id-keyed ``embeddings.json`` — never write it, never recompute. A row
    with no vector is a REFUSAL, not a silent recompute: at re-gate time a missing vector means the
    store and its embeddings disagree, and inventing one would hide exactly the drift this organ
    exists to catch."""
    import numpy as np

    cache = json.loads((store_dir / "embeddings.json").read_text(encoding="utf-8"))
    items = cache["items"]
    missing = [r["row_id"] for r in rows if r["row_id"] not in items]
    if missing:
        raise ValueError(f"{store_dir.name}: {len(missing)} row(s) have no committed embedding "
                         f"(first: {missing[:3]}) — the store and embeddings.json disagree; "
                         "re-embed the store before re-gating")
    out: dict[str, list[float]] = {}
    for r in rows:
        v = np.asarray(items[r["row_id"]], dtype=np.float64)
        v /= max(float(np.linalg.norm(v)), 1e-12)
        out[r["row_id"]] = v.tolist()
    report = {
        "reused": len(rows), "recomputed": 0,
        "backend": cache.get("backend"), "dim": cache.get("dim"),
        "source": (f"committed corpus_stores/{store_dir.name}/embeddings.json (row-id keyed), "
                   "read-only at re-gate: no vector is recomputed, a missing one refuses"),
    }
    return out, report


def regate(store_dir: Path, class_key: str, *, holdout_fraction: float = 0.3,
           seed: int = 7) -> dict[str, Any]:
    """RE-DERIVE the gate alone, against the store as it stands. Reads rows and embeddings; writes
    nothing, consumes no residue, derives no row. Returns the blocks a verdict is built from."""
    from laplace.pipeline import merge_residue as M

    rows = load_rows(store_dir)
    census = gate_eligible(rows, class_key)
    eligible = census.pop("eligible")
    emb, emb_report = load_embeddings(store_dir, rows)

    def _g(shuffle: bool, baseline: str) -> dict[str, Any]:
        return M.nearest_exemplar_gate(eligible, emb, class_key=class_key, shuffle=shuffle,
                                       baseline=baseline, holdout_fraction=holdout_fraction,
                                       seed=seed)

    real, bad = _g(False, "identity"), _g(True, "identity")
    real_def, bad_def = _g(False, "default"), _g(True, "default")
    refusal_holds = not bad["passed"]
    return census | {
        "class_key": class_key,
        "holdout_fraction": holdout_fraction,
        "seed": seed,
        "backend": emb_report["backend"],
        "embeddings": emb_report,
        "gate": real,
        "planted_bad_gate": bad,
        "gate_holdout_default_baseline": real_def,
        "planted_bad_gate_holdout_default_baseline": bad_def,
        "refusal_proof_holds": refusal_holds,
        "wired_in": bool(real.get("passed")) and refusal_holds,
    }


#: a measured score printed into prose has >= 3 decimals; a schema tag ("…/0.2") has one. Rows
#: before renders: prose quoting a number is a RENDER of the gate blocks and goes stale with them.
_PROSE_NUMBER = re.compile(r"\d+\.\d{3,}")

_GATE_BLOCKS = ("gate", "planted_bad_gate", "gate_holdout_default_baseline",
                "planted_bad_gate_holdout_default_baseline")


def measured_numbers(verdict: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for key in _GATE_BLOCKS:
        for v in (verdict.get(key) or {}).values():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                out.add(f"{float(v):.6f}".rstrip("0").rstrip("."))
                out.add(str(v))
    return out


def prose_number_drift(verdict: dict[str, Any], *, skip: tuple[str, ...] = ()) -> list[str]:
    """Every top-level prose field quoting a score that is NOT in the current gate blocks — the
    render-carrying-state failure, caught rather than left for a reader to trip over."""
    known = measured_numbers(verdict)
    drift = []
    for k, v in verdict.items():
        if k in skip or not isinstance(v, str):
            continue
        stale = [n for n in _PROSE_NUMBER.findall(v) if n not in known]
        if stale:
            drift.append(f"{k}: quotes {stale} — not among the current measured scores")
    return drift


def _render_baseline_finding(v: dict[str, Any]) -> str:
    """The paragraph_plan verdict's authored finding, re-rendered from the CURRENT blocks (it quotes
    four measured scores; leaving the prose behind while the numbers move is the same staleness one
    level down)."""
    bad, bad_def = v["planted_bad_gate"], v["planted_bad_gate_holdout_default_baseline"]
    return (
        "holdout_gate's DEFAULT baseline (random floats over surfaced candidates) sits at ~0.5 "
        f"regardless of class sizes, so on this {v['n_classes']}-class SKEWED store a signal-free "
        "picker beats it via class-size bias alone: the planted-bad "
        f"{'PASSES' if bad_def['passed'] else 'REFUSES'} under the default baseline "
        f"(score={bad_def['score']} vs base={bad_def['baseline']}) — an INVALID refusal control. The "
        "design §5 IDENTITY baseline (signal-free query averaged) captures that bias, so the "
        f"planted-bad correctly {'REFUSES' if not bad['passed'] else 'PASSES (!!)'} "
        f"(score={bad['score']} vs base={bad['baseline']}); the real store still wires in under both. "
        "The primary verdict uses the identity baseline. [re-rendered from the blocks above at "
        "re-gate — never carried over]")


def rewrite_gate_verdict(store_dir: Path, class_key: str, *, verdict_file: str = "gate_verdict.json",
                         holdout_fraction: float = 0.3, seed: int = 7,
                         now: str | None = None) -> dict[str, Any]:
    """Re-derive and rewrite one store's gate verdict IN PLACE, preserving every prose field the
    original carried (schema, stage, honesty note, findings, merge ledger) and replacing only the
    measured blocks — then stamp it. The prose is authored judgement about the gate; the numbers are
    the measurement. Only the numbers re-derive."""
    path = store_dir / verdict_file
    verdict = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    prior = {"gate": verdict.get("gate"), "gated_at": verdict.get("gated_at"),
             "store_fingerprint": verdict.get("store_fingerprint")}
    prior_regated = verdict.get("regated") or {}
    verdict.update(regate(store_dir, class_key, holdout_fraction=holdout_fraction, seed=seed))
    if prior["gate"] == verdict["gate"] and prior_regated.get("previous_gate") is not None:
        # a NO-OP re-gate (nothing moved): keep the genuinely superseded measurement, never
        # overwrite the predecessor with a copy of the incumbent.
        prior = {"gate": prior_regated["previous_gate"],
                 "gated_at": prior_regated.get("previous_gated_at"),
                 "store_fingerprint": prior_regated.get("previous_store_fingerprint")}
    verdict["n_classes"] = len(verdict["classes_present"])
    if "baseline_finding" in verdict:
        verdict["baseline_finding"] = _render_baseline_finding(verdict)
    verdict["regated"] = {
        "why": ("the store moved under the previous verdict (re-mint); re-derived gate-only — rows "
                "and embeddings read, never rewritten, no residue consumed"),
        "prose_number_drift": prose_number_drift(verdict),
        "previous_gate": prior["gate"],
        "previous_gated_at": prior["gated_at"],
        "previous_store_fingerprint": prior["store_fingerprint"],
    }
    stamp_verdict(verdict, store_dir, now=now)
    path.write_text(json.dumps(verdict, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return verdict


def invalidate(store_dir: Path, verdict_file: str, *, reason: str, superseded_by: str,
               now: str | None = None) -> dict[str, Any]:
    """Mark a verdict DEAD without touching a single measured number: the store it scored is gone and
    the gate cannot be honestly re-derived. The ``superseded`` block names why, the store state at
    invalidation, and where the live verdict is."""
    path = store_dir / verdict_file
    verdict = json.loads(path.read_text(encoding="utf-8"))
    verdict["superseded"] = {
        "status": "SUPERSEDED — this verdict measures a store state that no longer exists",
        "reason": reason,
        "superseded_by": superseded_by,
        "invalidated_at": now or _now_iso(),
        "store_fingerprint_at_invalidation": store_fingerprint(store_dir),
        "measurement_untouched": ("every score, baseline and count below is exactly as measured; "
                                  "nothing was re-run into this file"),
    }
    path.write_text(json.dumps(verdict, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return verdict
