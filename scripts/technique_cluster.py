"""The clean-room for the cross-program technique resolver (technique_lens.py).

Technique granularity is fuzzier than person-names, so the resolution quality is the whole game -
this is the instrument for the author to SEE the clusters and bless the one knob (``tau``, the
cosine-distance merge ceiling). It does not assert quality; it lays the clusters out so HIS eye can
read them, the conjugate of ``basis_cluster.py`` (which validated membership against a Sonnet
ground truth - here there is no ground truth, the technique partition is what we are deciding).

Two outputs, reported plainly:

  SWEEP   tau in a small range -> how many techniques, how many cross-AUTHOR (the strong
          expertise-routing signal), how many rungs get placed, coverage. The granularity dial.

  LISTING at one tau (default), every kept technique: its key, whether it is cross-author, the
          authors, and each member rung (author | theme | name) - so a wrong merge or a missed
          split is visible at a glance.

Usage:  python scripts/technique_cluster.py                 # sweep + listing at DEFAULT_TAU
        python scripts/technique_cluster.py --tau 0.30      # listing at one tau
        python scripts/technique_cluster.py --sweep-only    # the dial, no listing
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from laplace.engine import technique_lens  # noqa: E402
from laplace.representation.embed_router import get_backend  # noqa: E402

SWEEP = [0.22, 0.26, 0.30, technique_lens.DEFAULT_TAU, 0.38, 0.42]
_SHORT = ROOT / "collaborator_corpus" / "_structural"


def _theme_short(theme_id: str) -> str:
    """The generator slug, without the file path - the readable theme handle."""
    return theme_id.rsplit("::", 1)[-1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tau", type=float, default=None, help="merge ceiling for the listing")
    ap.add_argument("--sweep-only", action="store_true")
    args = ap.parse_args()

    backend = get_backend()
    if backend is None or backend.name.startswith("hash"):
        print("ERROR: real embedder (bge-small) unavailable; sync the `embed` extra "
              "(uv pip install -e '.[embed,analysis]'). Refusing to cluster on hash vectors.")
        return 1
    print(f"embedder: {backend.name}")

    records = technique_lens._rung_instances(ROOT)
    nodes = {rid: {"grade": 1} for rid, _ in records}           # every rung is a 'live' node here
    reach: dict = {rid: set() for rid in nodes}
    lenses = {rid: ["physics"] for rid in nodes}
    n_rungs = len(records)
    n_themes = len({m["theme_id"] for _, m in records})
    n_authors = len({m["author"] for _, m in records})
    print(f"rungs: {n_rungs}  themes: {n_themes}  authors: {n_authors}\n")

    # ---- the granularity dial ----
    print(f"{'tau':>6}{'techniques':>12}{'cross-author':>14}{'rungs placed':>14}{'coverage':>10}")
    print("-" * 56)
    sweep_rows = []
    sorted_taus = sorted(set(SWEEP + ([args.tau] if args.tau is not None else [])))
    for tau in sorted_taus:
        techs = technique_lens.resolve(ROOT, nodes, dict(reach), lenses, tau)
        placed = len({m for t in techs for m in t["members"]})
        xa = sum(1 for t in techs if t["cross_author"])
        cov = placed / n_rungs if n_rungs else 0.0
        sweep_rows.append({"tau": tau, "techniques": len(techs), "cross_author": xa,
                           "rungs_placed": placed, "coverage": round(cov, 4)})
        mark = "  <-- default" if abs(tau - technique_lens.DEFAULT_TAU) < 1e-9 else ""
        print(f"{tau:>6.2f}{len(techs):>12}{xa:>14}{placed:>14}{cov*100:>9.1f}%{mark}")
    print()

    report: dict = {"embedder": backend.name, "n_rungs": n_rungs, "n_themes": n_themes,
                    "n_authors": n_authors, "default_tau": technique_lens.DEFAULT_TAU,
                    "sweep": sweep_rows}

    # ---- the listing at one tau ----
    if not args.sweep_only:
        tau = args.tau if args.tau is not None else technique_lens.DEFAULT_TAU
        techs = technique_lens.resolve(ROOT, nodes, dict(reach), lenses, tau)
        meta = {rid: m for rid, m in records}
        print(f"=== {len(techs)} techniques at tau={tau:.2f} "
              f"({sum(1 for t in techs if t['cross_author'])} cross-author) ===\n")
        listing = []
        for t in sorted(techs, key=lambda x: (not x["cross_author"], -len(x["members"]), x["key"])):
            tag = "CROSS-AUTHOR" if t["cross_author"] else "cross-theme "
            print(f"[{tag}] technique://{t['key']}   ({len(t['members'])} rungs, "
                  f"{len(t['authors'])} authors)")
            rows = []
            for rid in t["members"]:
                m = meta[rid]
                print(f"    {m['author']:<11} {_theme_short(m['theme_id'])[:34]:<34} {m['name']}")
                rows.append({"author": m["author"], "theme": _theme_short(m["theme_id"]),
                             "name": m["name"]})
            print()
            listing.append({"key": t["key"], "cross_author": t["cross_author"],
                            "authors": t["authors"], "members": rows})
        report["listing_tau"] = tau
        report["techniques"] = listing

    out = _SHORT / "_technique_cluster_report.json"
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
