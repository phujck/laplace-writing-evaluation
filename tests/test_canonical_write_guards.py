from __future__ import annotations

import json

from laplace.research import corpus_ingest


def _graph(root):
    manuscript = root / "graph" / "manuscript"; manuscript.mkdir(parents=True)
    (manuscript / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}Graph.\\end{document}\n")
    (root / "registry_projects.json").write_text(json.dumps({"projects": [{
        "name": "graph", "project_dir": "graph", "tex_root": "graph/manuscript"}]}))
    for ident in ("node:a", "node:b", "def:one", "res:one"):
        result = corpus_ingest.rewire_add(root, "graph", {"kind": "add-node", "node": ident,
            "node_kind": "definition" if ident.startswith("def:") else "result",
            "essence": ident, "by": "fixture"})
        assert result.get("ok"), result
    return manuscript


def test_edges_require_live_directional_endpoints_refuse_self_and_prerequisite_cycles(tmp_path):
    _graph(tmp_path)
    assert corpus_ingest.rewire_add(tmp_path, "graph", {"kind": "add-edge",
        "node": "missing", "target": "node:a", "rel": "support"})["error"].startswith("node is not live")
    assert corpus_ingest.rewire_add(tmp_path, "graph", {"kind": "add-edge",
        "node": "node:a", "target": "missing", "rel": "support"})["error"].startswith("target is not live")
    assert "self" in corpus_ingest.rewire_add(tmp_path, "graph", {"kind": "add-edge",
        "node": "node:a", "target": "node:a", "rel": "support"})["error"]

    # Direction is node derives-from target: A -> B means A requires B. The
    # reverse prerequisite would make B require A and close a cycle.
    first = corpus_ingest.rewire_add(tmp_path, "graph", {"kind": "add-edge",
        "node": "node:a", "target": "node:b", "rel": "prerequisite"})
    assert first.get("ok"), first
    reverse = corpus_ingest.rewire_add(tmp_path, "graph", {"kind": "add-edge",
        "node": "node:b", "target": "node:a", "rel": "prerequisite"})
    assert "cycle" in reverse["error"] and "node derives-from target" in reverse["error"]
    assert "current edge" in corpus_ingest.rewire_add(tmp_path, "graph", {
        "kind": "remove-edge", "node": "node:b", "target": "res:one"})["error"]

    # No speculative kind gate: a definition may support a result when the
    # author explicitly declares that typed relation.
    support = corpus_ingest.rewire_add(tmp_path, "graph", {"kind": "add-edge",
        "node": "def:one", "target": "res:one", "rel": "support"})
    assert support.get("ok"), support


def test_move_node_requires_live_parent_and_refuses_containment_cycle(tmp_path):
    _graph(tmp_path)
    assert "target is not live" in corpus_ingest.rewire_add(tmp_path, "graph", {
        "kind": "move-node", "node": "node:a", "target": "missing"})["error"]
    assert corpus_ingest.rewire_add(tmp_path, "graph", {"kind": "move-node",
        "node": "node:a", "target": "node:b"}).get("ok")
    cycle = corpus_ingest.rewire_add(tmp_path, "graph", {"kind": "move-node",
        "node": "node:b", "target": "node:a"})
    assert "containment cycle" in cycle["error"]
    assert "node is not live" in corpus_ingest.rewire_add(tmp_path, "graph", {
        "kind": "set-spine", "node": "missing", "ord": 9})["error"]
