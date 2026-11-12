#!/usr/bin/env python3
"""consume_intents.py — draft (never apply) evolution contracts from a
manuscript's open conceptric-intent queue.

    consume_intents.py <manuscript_dir> [--corpus X] [--out DIR]

Reads ``<manuscript_dir>/feedback/feedback.jsonl``, drafts an
``evolution_plan.json`` + ``RATIFY.md`` for every open, draftable intent, prints
a JSON summary ``{"drafted": [...], "escalated": [...]}`` and exits 0 (2 on a
usage error). DRAFT-ONLY: there is no apply flag — the author ratifies and
applies (with the evolve operator) after reading each RATIFY.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# repo-root on sys.path so ``laplace`` imports whether run as a script or -m
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from laplace.pipeline import evolution_consumer as consumer  # noqa: E402


def _build_net(corpus: str, repo_root: Path):
    """Best-effort corpus network for grades + neighbourhoods. Any failure (an
    unregistered corpus, a missing tex tree) → None: the draft still proceeds on
    the intent payload alone, grades falling to the bounded default."""
    if not corpus:
        return None
    try:
        from laplace.research import corpus_ingest as ci
        from laplace.pipeline import registry
        proj = registry.resolve(corpus)
        if proj is None or not proj.tex_root:
            return None
        tex_root = repo_root / proj.tex_root
        if not (tex_root / "main.tex").is_file():
            return None
        return ci.corpus_network(tex_root, repo_root, corpus)
    except Exception:  # noqa: BLE001 — the net is an enrichment, never required
        return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="consume_intents.py",
        description="Draft (never apply) evolution contracts from the open "
                    "conceptric-intent queue.")
    ap.add_argument("manuscript_dir",
                    help="the dir holding feedback/feedback.jsonl")
    ap.add_argument("--corpus", default="",
                    help="the corpus/project name (for meta.project + the "
                         "dry-run rehearsal + grades)")
    ap.add_argument("--out", default="",
                    help="where evolutions/ lands (default: the manuscript dir)")
    try:
        args = ap.parse_args(argv)
    except SystemExit:
        return 2

    md = Path(args.manuscript_dir)
    if not md.is_dir():
        print(f"usage error: manuscript dir not found: {md}", file=sys.stderr)
        return 2

    repo_root = Path(__file__).resolve().parents[1]
    out_dir = Path(args.out) if args.out else md
    net = _build_net(args.corpus, repo_root)

    summary = consumer.consume(md, args.corpus, net, out_dir, repo_root=repo_root)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
