#!/usr/bin/env python3
"""The payload-side fibre instrument: does the wake payload at rate R still NAME the
nodes each standing thread probe declares it must reach?

Why this exists. `laplace.engine.holdout.score_threads` - the instrument the 2026-08-20 wake-rate
pre-registration named for the thread axis - has the signature
``(repo_root, budget_s, wall, record)``. It never sees a payload: it routes the LIVE
network, so its verdicts cannot be a function of the wake rate. The wave-1 run measured
exactly that (identical verdicts in all seven arms, a structurally unfireable veto rule) and
P15 was ruled REFUTED with the caveat that the registered instrument answered a different
question. This module is the replacement for RATE questions only:

    router-side  (score_threads)      : can the retriever FIND the fibre in the corpus?
    payload-side (this)               : does the payload the reader is handed still NAME it?

The two are independent. A probe can be router-red and payload-green (the wake names the
node explicitly even though the embedding router would not surface it) and the reverse.
Reported as two axes, never merged.

Scoring is the bench's own shared normalizer + literal containment, so a payload-side HIT
means the exact node string is present in the text handed to the reader.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent


def _normalizer():
    spec = importlib.util.spec_from_file_location(
        "_rbench_norm", REPO / "scripts/reconstruction_bench.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.normalize


def load_probes(repo: Path) -> list[dict]:
    doc = json.loads((repo / "holdout/THREAD_PROBES.json").read_text(encoding="utf-8"))
    return list(doc.get("probes") or [])


def score_payload_fibre(payload_text: str, probes: list[dict], normalize=None) -> dict[str, Any]:
    """Per probe: which of its must_reach nodes the payload names, and whether ALL do.

    ``reached`` is all-of, deliberately: a probe declares the set of nodes that together
    carry the thread, and half a fibre is a miss. ``partial`` carries the softer signal so
    a run can see a fibre thin before it breaks.
    """
    norm = normalize or _normalizer()
    hay = norm(payload_text)
    rows = {}
    for p in probes:
        must = [str(x) for x in (p.get("must_reach") or [])]
        named = [m for m in must if norm(m) in hay]
        rows[str(p.get("id"))] = {
            "must_reach": must,
            "named": named,
            "n_named": len(named),
            "n_must": len(must),
            "reached": bool(must) and len(named) == len(must),
            "partial": bool(named) and len(named) < len(must),
            "router_expected_now": p.get("expected_now"),
        }
    n_reached = sum(1 for r in rows.values() if r["reached"])
    n_any = sum(1 for r in rows.values() if r["named"])
    return {
        "per_probe": rows,
        "n_probes": len(rows),
        "n_reached_all_of": n_reached,
        "n_named_any": n_any,
        "fibre_rate_all_of": round(n_reached / len(rows), 4) if rows else None,
        "fibre_rate_any_of": round(n_any / len(rows), 4) if rows else None,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="person", choices=["person", "engine"])
    ap.add_argument("--budget", type=int, default=None,
                    help="rate R for the lever-2 enforcer; omit for the unbudgeted control")
    args = ap.parse_args()

    import sys
    sys.path.insert(0, str(REPO / "src"))
    from laplace.engine import self_corpus, wake as wakemod, process_health  # noqa: E402

    orig = self_corpus._enforce_grade0_budget
    if args.budget is not None:
        self_corpus._enforce_grade0_budget = (  # type: ignore[assignment]
            lambda out, budget=None, _b=args.budget: orig(out, budget=_b))
    try:
        fp = self_corpus.reconstruct_self(REPO, grade=0, mode=args.mode)
    finally:
        self_corpus._enforce_grade0_budget = orig  # type: ignore[assignment]

    payload = {"probe": process_health.probe(), "fixed_point": fp,
               "semantic": wakemod._semantic_block(REPO)}
    text = json.dumps(payload, ensure_ascii=False, indent=1, default=str)
    out = score_payload_fibre(text, load_probes(REPO))
    out["mode"] = args.mode
    out["R"] = args.budget
    out["payload_chars"] = len(text)
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
