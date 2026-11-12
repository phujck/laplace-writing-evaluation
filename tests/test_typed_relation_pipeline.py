"""Canonical producer -> reducer -> consumer controls for typed logical relations."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from laplace.research import concepts
from laplace.research import corpus_ingest as ci
from laplace.web import scanner
from laplace.pipeline import verify
from laplace.pipeline import dispatch, stage_store


REPO = Path(__file__).resolve().parents[1]


def _fixture(root: Path, *, evidence: bool = False) -> Path:
    manuscript = root / "book" / "manuscript"
    manuscript.mkdir(parents=True)
    (manuscript / "main.tex").write_text(
        "\\documentclass{book}\n\\begin{document}\n\\input{logic}\n\\end{document}\n",
        encoding="utf-8")
    (manuscript / "logic.tex").write_text(
        "\\section{Logic}\\label{sec:logic}\n"
        "We define the base.\\begin{equation}\\label{eq:base}x=x\\end{equation}\n"
        + ("ordinary derivation prose " * 30)
        + "Using \\eqref{eq:base},\\begin{equation}\\label{eq:derived}y=y\\end{equation}\n"
        + "\\begin{equation}\\label{eq:supported}z=z\\end{equation}\n",
        encoding="utf-8")
    project = {"name": "book", "kind": "conceptric", "project_dir": "book",
               "tex_root": "book/manuscript",
               "manifest": {"document": {"root": "book/manuscript/main.tex"}}}
    if evidence:
        project["evidence_store"] = "book/numerics"
        (root / "book" / "inputs").mkdir()
        (root / "book" / "literature").mkdir()
        (root / "book" / "numerics").mkdir()
        (root / "book" / "literature" / "references.bib").write_text("", encoding="utf-8")
        (root / "book" / "numerics" / "resource_readings.json").write_text(
            json.dumps({"headline": [{"depth": 7}]}), encoding="utf-8")
        (root / "book" / "inputs" / "evidence_ledger.md").write_text(
            "| id | claim | source | status | note |\n"
            "|---|---|---|---|---|\n"
            "| CLM-001 | A checked claim. | readings:resource:headline[0].depth | numerical_check | n |\n",
            encoding="utf-8")
    (root / "registry_projects.json").write_text(
        json.dumps({"projects": [project]}), encoding="utf-8")
    ci._CORPUS_CACHE.clear()
    return manuscript


def _change(root: Path, **payload) -> dict:
    current = concepts.state("book", root=root)
    status, result = concepts.change({"project": "book", "base_revision": current["revision"],
                                      "by": "author", **payload}, root=root)
    assert status == 200, result
    return result


def _add_planning_nodes(root: Path) -> None:
    _change(root, operation="add_node", node="def:premise", node_kind="definition",
            essence="The premise.", parent="paper://")
    _change(root, operation="add_node", node="res:claim", node_kind="result",
            essence="The claim.", parent="paper://")


def test_source_overlay_and_consumers_share_one_inferential_semantics(tmp_path, monkeypatch):
    manuscript = _fixture(tmp_path)
    _add_planning_nodes(tmp_path)

    # Source equation references remain inferential and retain their producer.
    source_net = ci.corpus_network(manuscript, repo_root=tmp_path, name="book")
    source_edge = next(row for row in source_net["relations"]
                       if (row["source"], row["target"]) == ("eq:derived", "eq:base"))
    assert source_edge["rel"] == "prerequisite" and source_edge["inferential"] is True
    assert {p["producer"] for p in source_edge["provenance"]} == {"selected-source"}
    # The real derivation consumers agree on a source prerequisite.
    assert stage_store._eq_deps(source_net, "eq:derived") == ["eq:base"]
    assert "Derives from" in dispatch._node_object("eq:derived", source_net, None)
    assert verify._real_refs(source_net, "eq:derived") == ["eq:base"]
    assert scanner.corpus_content_dependencies(source_net, "eq:derived") == {
        "explicit": ["eq:base"], "confirmed": []}

    # Support, analogy, implementation and validation stay visible to the
    # general graph but cannot clear a gap, deepen a derivation, or enter a
    # derivation consumer. This writes through the public change door, then
    # exercises the actual stage, dispatch, coherence and served-content paths.
    _change(tmp_path, operation="add_node", node="def:analogue", node_kind="definition",
            essence="An analogue.", parent="paper://")
    _change(tmp_path, operation="add_node", node="def:implementation", node_kind="definition",
            essence="An implementation.", parent="paper://")
    _change(tmp_path, operation="add_node", node="def:validation", node_kind="definition",
            essence="A validation.", parent="paper://")
    _change(tmp_path, operation="add_edge", node="res:claim", target="def:premise",
            rel="support")
    _change(tmp_path, operation="add_edge", node="res:claim", target="def:analogue",
            rel="analogy")
    _change(tmp_path, operation="add_edge", node="res:claim", target="def:implementation",
            rel="implementation")
    _change(tmp_path, operation="add_edge", node="res:claim", target="def:validation",
            rel="validated_by")
    _change(tmp_path, operation="add_edge", node="eq:supported", target="eq:base",
            rel="support")
    support_net = ci.corpus_network(manuscript, repo_root=tmp_path, name="book")
    support = next(row for row in support_net["relations"]
                   if (row["source"], row["target"]) == ("res:claim", "def:premise"))
    assert support["rel"] == "support" and support["axis"] == "supports"
    assert support["inferential"] is False
    assert "res:claim" in ci.gaps(support_net)
    assert ci.dep_grade(support_net)["res:claim"] == 0
    assert ci.derivation_subtree(support_net, "res:claim")["edges"] == []
    assert not [e for e in ci.dag_map(support_net)["edges"] if e["from"] == "res:claim"]
    visible = concepts.state("book", "res:claim", root=tmp_path)["relations"]
    assert any(e["rel"] == "support" and e["direction"] == "evidence" for e in visible)
    assert stage_store._eq_deps(support_net, "eq:supported") == []
    assert "Derives from" not in dispatch._node_object("res:claim", support_net, None)
    assert verify._real_refs(support_net, "res:claim") == []
    monkeypatch.setattr(verify, "_load_corpus_network", lambda *_args: (support_net, ""))
    assert verify.check_coherence("book", root=tmp_path)["under_described"] == ["res:claim"]
    assert scanner.corpus_content_dependencies(support_net, "eq:supported") == {
        "explicit": [], "confirmed": []}

    # Retyping uses the same ledger/reducer path and changes every inference consumer.
    _change(tmp_path, operation="retype_edge", node="res:claim", target="def:premise",
            rel="prerequisite")
    logical_net = ci.corpus_network(manuscript, repo_root=tmp_path, name="book")
    assert ci.inferential_dependencies(logical_net, "res:claim") == ["def:premise"]
    assert "res:claim" not in ci.gaps(logical_net)
    assert ci.dep_grade(logical_net)["res:claim"] == 1
    assert ci.derivation_subtree(logical_net, "res:claim")["edges"][0]["to"] == "def:premise"


def test_writer_refuses_contradiction_and_inferential_cycle_but_allows_graph_cycle(tmp_path):
    manuscript = _fixture(tmp_path)
    _add_planning_nodes(tmp_path)
    ledger = tmp_path / "corpus_friction" / "book.jsonl"
    before = ledger.read_bytes()
    current = concepts.state("book", root=tmp_path)
    status, refused = concepts.change({"project": "book", "operation": "add_edge",
        "base_revision": current["revision"], "node": "res:claim", "target": "def:premise",
        "rel": "support", "axis": "derives", "by": "author"}, root=tmp_path)
    assert status == 422 and "uses axis" in refused["error"]
    assert ledger.read_bytes() == before

    _change(tmp_path, operation="add_edge", node="res:claim", target="def:premise",
            rel="prerequisite")
    before_cycle = ledger.read_bytes()
    current = concepts.state("book", root=tmp_path)
    status, refused = concepts.change({"project": "book", "operation": "add_edge",
        "base_revision": current["revision"], "node": "def:premise", "target": "res:claim",
        "rel": "prerequisite", "by": "author"}, root=tmp_path)
    assert status == 422 and "dependency cycle" in refused["error"]
    assert ledger.read_bytes() == before_cycle

    # A two-way analogy is legal general-graph structure and never enters closure.
    _change(tmp_path, operation="add_edge", node="def:premise", target="res:claim",
            rel="analogy")
    _change(tmp_path, operation="retype_edge", node="res:claim", target="def:premise",
            rel="analogy")
    net = ci.corpus_network(manuscript, repo_root=tmp_path, name="book")
    assert len([r for r in net["relations"] if r["rel"] == "analogy"]) == 2
    assert ci.inferential_dependencies(net, "res:claim") == []
    assert not [d for d in net["relation_diagnostics"] if d["type"] == "inferential-cycle"]


def test_semantic_wire_and_registered_evidence_keep_provenance_without_inference(tmp_path):
    manuscript = _fixture(tmp_path, evidence=True)
    (manuscript / ".corpus_sem_edges.json").write_text(json.dumps({"wires": [{
        "a": "eq:base", "b": "eq:derived", "similarity": 0.91}]}), encoding="utf-8")
    _change(tmp_path, operation="add_node", node="clm_001", node_kind="result",
            essence="The registered claim.", parent="paper://")
    net = ci.corpus_network(manuscript, repo_root=tmp_path, name="book")
    analogy = next(r for r in net["relations"] if r["rel"] == "analogy")
    assert analogy["inferential"] is False
    assert {p["producer"] for p in analogy["provenance"]} == {"semantic-wire"}
    validation = next(r for r in net["relations"] if r["source"] == "clm_001"
                      and r["rel"] == "validated_by")
    assert validation["inferential"] is False and validation["axis"] == "validates"
    assert {p["producer"] for p in validation["provenance"]} == {"registered-evidence"}
    assert ci.dep_grade(net)["clm_001"] == 0 and "clm_001" in ci.gaps(net)


def test_historical_conflict_and_bare_edge_are_inspectable_not_inferential():
    nodes = {"a": {"kind": "result"}, "b": {"kind": "definition"}}
    relations, diagnostics = ci.relation_projection(nodes, {"a": ["b"], "b": ["b"]},
        records=[{"id": "old", "kind": "add-edge", "node": "a", "target": "b",
                  "rel": "support", "axis": "derives"}])
    assert relations[0]["ambiguous"] is True and relations[0]["inferential"] is False
    assert diagnostics[0]["type"] == "relation-axis-conflict"
    bare, bare_diagnostics = ci.relation_projection(nodes, {"a": ["b"], "b": ["b"]})
    assert bare[0]["rel"] == "unknown" and bare[0]["inferential"] is False
    assert bare_diagnostics[0]["type"] == "ambiguous-bare-edge"


def test_unknown_historical_axis_preserves_pair_and_receipt_without_crashing_or_becoming_a_premise():
    from copy import deepcopy
    nodes = {"claim": {"kind": "result", "essence": "A result."},
             "frame": {"kind": "support", "essence": "An authored narrative frame."}}
    for kind in ("add-edge", "add-node"):
        record = {"id": "RW-original-framing", "kind": kind, "node": "frame",
                  "target": "claim", "axis": "frames", "by": "original-author",
                  "node_kind": "support", "essence": "An authored narrative frame."}
        original = deepcopy(record)
        leaves = deepcopy(nodes)
        if kind == "add-node":
            leaves.pop("frame")
        edges = {"claim": ["claim"]}
        ci.apply_overlay(leaves, edges, [record], {})
        relations, diagnostics = ci.relation_projection(leaves, edges, records=[record])
        row = next(item for item in relations if item["source"] == "frame")
        assert row["target"] == "claim" and row["axis"] == "frames"
        assert row["rel"] == "unknown" and row["direction"] == "unresolved"
        assert row["ambiguous"] and not row["inferential"]
        assert row["provenance"][0]["record_id"] == record["id"]
        assert diagnostics[0]["type"] == "unknown-historical-axis"
        assert ci.inferential_dependencies({"nodes": leaves, "relations": relations}, "frame") == []
        assert record == original


def test_current_writer_still_refuses_unregistered_axis_before_deposit(tmp_path):
    result = ci.rewire_add(tmp_path, "book", {"kind": "add-edge", "node": "frame",
        "target": "claim", "axis": "frames"})
    assert "axis must be one of" in result["error"]
    assert not (tmp_path / "corpus_friction" / "book.jsonl").exists()


def test_axis_only_bearer_compatibility_normalises_and_removes_through_writer(tmp_path):
    manuscript = _fixture(tmp_path)
    _add_planning_nodes(tmp_path)
    added = ci.rewire_add(tmp_path, "book", {"kind": "add-node", "node": "ref:source",
        "node_kind": "citation", "parent": "references", "by": "fixture"})
    assert added.get("ok"), added
    supported = ci.rewire_add(tmp_path, "book", {"kind": "add-edge", "node": "ref:source",
        "target": "res:claim", "axis": "supports", "by": "fixture"})
    assert supported.get("ok"), supported
    net = ci.corpus_network(manuscript, repo_root=tmp_path, name="book")
    relation = next(row for row in net["relations"] if row.get("axis") == "supports")
    assert (relation["source"], relation["target"], relation["inferential"]) == (
        "res:claim", "ref:source", False)
    removed = ci.rewire_add(tmp_path, "book", {"kind": "remove-edge", "node": "ref:source",
        "target": "res:claim", "by": "fixture"})
    assert removed.get("ok"), removed
    after = ci.corpus_network(manuscript, repo_root=tmp_path, name="book")
    assert not [row for row in after["relations"]
                if {row["source"], row["target"]} == {"res:claim", "ref:source"}]


def test_isolated_relation_writes_leave_live_synthetics_bytes_identical(tmp_path):
    protected = [
        REPO / "corpus_friction/synthetics-master-guide.jsonl",
        REPO / "synthetics papers/synthetics-master-guide/manuscript/Synthetics.tex",
        REPO / "synthetics papers/synthetics-master-guide/manuscript/projection_plan.json",
        REPO / "synthetics papers/synthetics-master-guide/manuscript/projection_plan.friction.jsonl",
    ]
    before = {str(path.relative_to(REPO)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in protected if path.is_file()}
    _fixture(tmp_path)
    _add_planning_nodes(tmp_path)
    _change(tmp_path, operation="add_edge", node="res:claim", target="def:premise",
            rel="support")
    after = {str(path.relative_to(REPO)): hashlib.sha256(path.read_bytes()).hexdigest()
             for path in protected if path.is_file()}
    assert after == before and before
