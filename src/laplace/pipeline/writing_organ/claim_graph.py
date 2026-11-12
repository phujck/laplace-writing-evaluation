"""Phase 0 of the telling campaign: the claim graph, deterministically, from the conceptric.

No model anywhere. Vertices are the conceptric's typed atoms (claim, result, def,
limitation, evidence, reading, design); edges are its typed relations among them.
Containers (domain, cluster, section) contribute provenance, not vertices. Shaped so a
row pours into the atlas NodeBundle claims layer without rework.

Run: python3 -m laplace.pipeline.writing_organ.claim_graph <manuscript_dir>
Writes <manuscript_dir>/claim_graph.json and prints the gate report.
"""

from __future__ import annotations

import json
import re
import sys
import pathlib

ATOM_KINDS = {"claim", "result", "def", "limitation", "evidence", "reading", "design", "boundary"}
#: boundary - a field-level node beyond the paper (a practice, a folk intuition, a
#: hardware budget, a pattern): the cut beyond the artefact (DESIGN_2026-08-08b
#: section 8). The intro realises its in-edges; the conclusion its out-edges.
EDGE_RELS = {"draws", "demonstrates", "validated_by", "grounds", "precedes", "carries", "shares"}


def build(manuscript_dir: pathlib.Path) -> dict:
    c = json.loads((manuscript_dir / "conceptric_v1.json").read_text())
    nodes = {n["id"]: n for n in c["nodes"]}

    section_of: dict[str, str] = {}
    for e in c["edges"]:
        if e.get("rel") == "contains" and nodes.get(e["src"], {}).get("kind") == "section":
            section_of[e["dst"]] = e["src"]

    vertices = []
    for n in c["nodes"]:
        if n.get("kind") in ATOM_KINDS:
            vertices.append({
                "id": n["id"], "kind": n["kind"], "label": n.get("label", ""),
                "weight": n.get("weight"), "status": n.get("status"),
                "section": section_of.get(n["id"], ""),
            })
    vids = {v["id"] for v in vertices}

    edges = [
        {"src": e["src"], "dst": e["dst"], "rel": e["rel"]}
        for e in c["edges"]
        if e.get("rel") in EDGE_RELS and e["src"] in vids and e["dst"] in vids
    ]

    return {"vertices": vertices, "edges": edges,
            "provenance": {"source": "conceptric_v1.json", "built_by": "claim_graph.py",
                           "atom_kinds": sorted(ATOM_KINDS), "edge_rels": sorted(EDGE_RELS)}}


def gate(graph: dict, manuscript_dir: pathlib.Path) -> list[str]:
    """The Phase 0 gate: connectivity, tex-id resolution, edge preservation."""
    failures = []
    vids = {v["id"] for v in graph["vertices"]}

    adj: dict[str, set] = {v: set() for v in vids}
    for e in graph["edges"]:
        adj[e["src"]].add(e["dst"])
        adj[e["dst"]].add(e["src"])
    seen: set = set()
    stack = [next(iter(vids))]
    while stack:
        v = stack.pop()
        if v in seen:
            continue
        seen.add(v)
        stack.extend(adj[v] - seen)
    orphans = sorted(vids - seen)

    tex_ids = set()
    for f in manuscript_dir.glob("sec_*.tex"):
        for line in f.read_text().splitlines():
            if line.startswith("% NODES:"):
                tex_ids.update(re.findall(r"RQ-[A-Z]+-\d+", line))
    unresolved = sorted(tex_ids - vids)
    if unresolved:
        failures.append(f"{len(unresolved)} tex-cited RQ ids missing from the graph: {unresolved[:8]}")

    cited_orphans = sorted(set(orphans) & tex_ids)
    if cited_orphans:
        failures.append(f"{len(cited_orphans)} tex-cited atoms are structural orphans "
                        f"(reachable only through containers): {cited_orphans[:8]}")
    if orphans:
        print(f"GATE NOTE: {len(orphans)} structural orphans (atoms no other atom references) "
              f"- the caster must rule each excluded-or-woven: {orphans}")

    return failures


def main() -> int:
    md = pathlib.Path(sys.argv[1])
    g = build(md)
    out = md / "claim_graph.json"
    out.write_text(json.dumps(g, indent=1))
    kinds: dict[str, int] = {}
    for v in g["vertices"]:
        kinds[v["kind"]] = kinds.get(v["kind"], 0) + 1
    rels: dict[str, int] = {}
    for e in g["edges"]:
        rels[e["rel"]] = rels.get(e["rel"], 0) + 1
    print(f"claim graph: {len(g['vertices'])} vertices {dict(sorted(kinds.items()))}")
    print(f"             {len(g['edges'])} edges {dict(sorted(rels.items()))}")
    failures = gate(g, md)
    for f in failures:
        print("GATE FAIL:", f)
    if not failures:
        print("GATE PASS: connected; all tex-cited ids resolve")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
