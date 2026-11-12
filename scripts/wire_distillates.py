#!/usr/bin/env python3
"""Join a paper's tex leaves to its distillate layer, and PROVE the join changed what a descent
surfaces.

WO-20260820-wire-distillates-to-leaves. The blind surfacing test measured that the rich layer -
``concept_corpus`` atoms, ``collaborator_corpus`` program-ladder paper handles keyed by OpenAlex
id, per-paper ``corpus_stores`` rows - carries arcana-grain content but is unreachable by descent
from the paper's tex leaf. ``laplace.engine.distillate_lens`` is the repair; this script is its operator
surface:

  ``--table``  emit the reviewable match table (matched / ambiguous / unmatched + counts).
  ``--prove``  run the BEFORE/AFTER descent proof for the named papers: the ``open_descender``
               hit list, and the neighbourhood (``conceptric.lateral``) of the top hit, computed
               once with the distillate wire suppressed and once with it live.

Nothing here writes a store. The wire is a pure derivation merged into the substrate edge index at
``conceptric._self_edge_index``; the match table is banked to evidence as the AUDIT record of what
was joined, never as the input the wire reads (reconstruction-is-mechanical-render).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from laplace.engine import distillate_lens  # noqa: E402

DEFAULT_PAPERS = ["super-sensing-100-fold-enhancement-in-thz-time-domain",
                  "non-uniqueness-of-driving-fields-generating-non-linear"]
DEFAULT_QUERIES = {
    "super-sensing-100-fold-enhancement-in-thz-time-domain":
        "super-sensing 100-fold enhancement in THz time domain spectroscopy",
    "non-uniqueness-of-driving-fields-generating-non-linear":
        "non-uniqueness of driving fields generating non-linear optical response",
}


def _is_distillate(nid: str) -> bool:
    """A node id belonging to the rich layer the blind test could not reach by descent."""
    return (nid.startswith(distillate_lens.ATOMS_ROOT)
            or nid.startswith(distillate_lens.STORES_ROOT)
            or nid.startswith(distillate_lens.THEMES_ROOT)
            or nid.startswith(distillate_lens.CONNECTOME_ROOT)
            or nid.startswith(distillate_lens.LIFE_PAPERS)
            or "_structural/" in nid)


def emit_table(out_path: Path | None) -> dict:
    table = distillate_lens.paper_families(ROOT)
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(table, ensure_ascii=False, indent=1), encoding="utf-8")
    return table


def prove(papers: list[str], k: int, width: int) -> dict:
    """BEFORE/AFTER, in one process, over the same tree and the same embedder.

    BEFORE is not a git checkout: it is the SAME network built with the distillate wire suppressed
    (``distillate_edge_index`` monkeypatched to empty and the edge-index memo cleared), so the only
    difference between the two halves is the wire itself."""
    from laplace.engine import conceptric, recursive_read

    des = recursive_read.open_descender(ROOT)
    hits: dict[str, list[dict]] = {}
    for paper in papers:
        q = DEFAULT_QUERIES.get(paper, paper.replace("-", " "))
        packet = des.descend(q, k=k, beam=4, fire="dutiful")
        hits[paper] = [{"id": h["id"], "score": h["score"], "distillate": _is_distillate(h["id"])}
                       for h in packet["hits"]]

    def neighbourhood(suppress: bool) -> dict[str, list[dict]]:
        real = distillate_lens.distillate_edge_index
        conceptric._SELF_EDGE_INDEX_MEMO.clear()
        if suppress:
            distillate_lens.distillate_edge_index = lambda *a, **kw: {}
        try:
            net = conceptric.load_network(ROOT)
            out = {}
            for paper, hs in hits.items():
                anchor = next((h["id"] for h in hs if h["id"].startswith(
                    f"{distillate_lens.TEX_ROOT}/{paper}/")), hs[0]["id"])
                lat = conceptric.lateral(net, anchor, width=width, conjectural=True)
                reach = net["reach"]
                out[paper] = {"anchor": anchor,
                              "neighbours": [{"id": n["id"], "out": n["out"],
                                              "shared_n": n["shared"],
                                              "shared": sorted(reach.get(anchor, set())
                                                               & reach.get(n["id"], set()))[:3],
                                              "distillate": _is_distillate(n["id"])} for n in lat]}
            return out
        finally:
            distillate_lens.distillate_edge_index = real
            conceptric._SELF_EDGE_INDEX_MEMO.clear()

    before = neighbourhood(suppress=True)
    after = neighbourhood(suppress=False)
    summary = {}
    for paper in papers:
        b = [n["id"] for n in before[paper]["neighbours"] if n["distillate"]]
        a = [n["id"] for n in after[paper]["neighbours"] if n["distillate"]]
        summary[paper] = {"anchor": after[paper]["anchor"],
                          "descent_hits": hits[paper],
                          "distillate_in_hits": [h["id"] for h in hits[paper] if h["distillate"]],
                          "before_distillate_neighbours": b,
                          "after_distillate_neighbours": a,
                          "gained": sorted(set(a) - set(b))}
    return {"papers": papers, "before": before, "after": after, "summary": summary}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--table", action="store_true", help="emit the match table")
    ap.add_argument("--out", type=Path, default=None, help="bank the match table here")
    ap.add_argument("--prove", action="store_true", help="run the BEFORE/AFTER descent proof")
    ap.add_argument("--prove-out", type=Path, default=None, help="bank the proof here")
    ap.add_argument("--papers", nargs="*", default=DEFAULT_PAPERS)
    ap.add_argument("--k", type=int, default=15)
    ap.add_argument("--width", type=int, default=12)
    args = ap.parse_args(argv)

    report: dict = {}
    if args.table or not args.prove:
        table = emit_table(args.out)
        report["counts"] = table["counts"]
        report["ambiguous"] = table["ambiguous"]
        report["unmatched"] = table["unmatched"]
    if args.prove:
        p = prove(args.papers, args.k, args.width)
        report["proof"] = p["summary"]
        if args.prove_out is not None:
            args.prove_out.parent.mkdir(parents=True, exist_ok=True)
            args.prove_out.write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
