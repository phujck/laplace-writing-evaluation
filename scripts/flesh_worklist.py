"""The FLESH WORK-ORDER - the measured map for his verdict (fifty-first, 2026-07-03):
"a reasonable spine but lacks flesh... it lacks context and depth, in both directions."

Mechanical, no judgment calls: for every node the paper projects (the NODES markers,
via the doc model), walk its edges in the corpus network and collect the COMPLEMENT
neighbours - live nodes the paper never cites - split by direction:

  DEPTH   = complement neighbours BELOW a projected node (what it derives from /
            depends on): the derivational chain a reader cannot currently follow.
  CONTEXT = complement neighbours ABOVE a projected node (what motivates or uses
            it): the framing tissue that says why it matters.

Output: manuscript/flesh_worklist.json (per section, per projected node, the two
lists with essences) + a per-section summary to stdout. The plan-object edit that
executes the pull is HIS-EYED work; this map is its evidence.

Usage: python scripts/flesh_worklist.py [<root.tex>] [<corpus>]
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from laplace.research import corpus_ingest as ci
from laplace.manuscript import projection_viewer as pv
from laplace.web.scanner import _repo_root


def main(root_tex: str, corpus: str) -> None:
    rr = _repo_root()
    model = pv.doc_model(root_tex)
    if "error" in model:
        raise SystemExit(model["error"])
    net = pv._network(corpus)
    if net is None:
        raise SystemExit(f"unknown corpus {corpus}")
    nodes = net["nodes"]

    # the projected set, per section (the NODES markers through the same parser)
    sec_nodes: dict[str, list[str]] = defaultdict(list)
    projected: set[str] = set()
    for f in model["files"]:
        p = pv._safe_path(f["file"])
        if p is None or not p.is_file():
            continue
        for span in pv.load_map(p):
            for nid in span.get("nodes") or []:
                projected.add(nid)
                if nid not in sec_nodes[span.get("section") or "?"]:
                    sec_nodes[span.get("section") or "?"].append(nid)

    def live(nid: str) -> bool:
        nd = nodes.get(nid)
        if nd is None:
            return False
        proj = nd.get("projection") or {}
        return not (nd.get("retired") or proj.get("retired")
                    or nd.get("kind") in ("citation", "root", "references")
                    or nid.startswith("paper://") or nid == "references")

    # direction through the ONE mechanism the inspector already trusts:
    # neighborhood(net, nid).below = dependencies (depth), .above = consumers (context)
    def brief(nid: str) -> dict:
        nd = nodes.get(nid, {})
        return {"id": nid, "kind": nd.get("kind"), "grade": nd.get("grade"),
                "essence": (nd.get("essence") or "")[:180]}

    nb_cache: dict[str, dict] = {}

    def nb(nid: str) -> dict:
        if nid not in nb_cache:
            nb_cache[nid] = ci.neighborhood(net, nid, cap=64)
        return nb_cache[nid]

    out: dict[str, dict] = {}
    totals = {"depth": set(), "context": set()}
    for sec in sorted(sec_nodes):
        rows = []
        for nid in sec_nodes[sec]:
            hood = nb(nid)
            depth = sorted({d["id"] for d in hood.get("below", [])
                            if d.get("prov") != "candidate"
                            and live(d["id"]) and d["id"] not in projected})
            ctx = sorted({d["id"] for d in hood.get("above", [])
                          if live(d["id"]) and d["id"] not in projected})
            if not depth and not ctx:
                continue
            totals["depth"].update(depth)
            totals["context"].update(ctx)
            rows.append({"node": nid,
                         "depth": [brief(n) for n in depth],
                         "context": [brief(n) for n in ctx]})
        if rows:
            out[sec] = {"n_projected": len(sec_nodes[sec]), "hungry": rows}

    dest = Path(root_tex).parent.parent / "flesh_worklist.json"
    dest = _repo_root() / dest if not dest.is_absolute() else dest
    dest.write_text(json.dumps(
        {"corpus": corpus, "root": model["root"],
         "verdict": "a reasonable spine but lacks flesh - context and depth, "
                    "in both directions (his, 2026-07-03)",
         "n_depth_candidates": len(totals["depth"]),
         "n_context_candidates": len(totals["context"]),
         "sections": out}, indent=1, ensure_ascii=False), encoding="utf-8")

    print(f"flesh worklist -> {dest}")
    print(f"one-hop complement candidates: {len(totals['depth'])} depth, "
          f"{len(totals['context'])} context")
    for sec, d in out.items():
        nd = sum(len(r["depth"]) for r in d["hungry"])
        nc = sum(len(r["context"]) for r in d["hungry"])
        print(f"  {sec}: {len(d['hungry'])}/{d['n_projected']} projected nodes hungry "
              f"({nd} depth, {nc} context edges)")


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else \
        "synthetics papers/subset-sum-itqde/manuscript/whitepaper/main.tex"
    main(root, sys.argv[2] if len(sys.argv) > 2 else "subset-sum-itqde")
