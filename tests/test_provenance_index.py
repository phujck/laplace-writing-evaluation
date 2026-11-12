"""The master node index (G5), the lineage walker (G6), and the two read doors.

These tests run the real index mint over paper_falqon's on-disk data (the flagship the
recon mapped), prove the eq->node ladder on the real ``eq:coh-total``, prove the spatial
join machinery on a synthetic nodemap fixture, and exercise the walker's depth / cycle /
orphan behaviour on synthetic graphs. The door tests assert the composed contract and the
composed 404 bodies. Real-data tests skip cleanly when a tree is absent, so a thin
checkout never hard-fails.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from laplace.pipeline import lineage, node_index as ni

REPO = Path(__file__).resolve().parents[1]
FALQON = "paper_falqon"


def _falqon_present() -> bool:
    return (REPO / "paper_falqon" / "manuscript" / "conceptric_v1.json").is_file()


falqon_only = pytest.mark.skipif(not _falqon_present(),
                                 reason="paper_falqon tree absent in this checkout")


# --------------------------------------------------------------------------- #
# G5 — the master index over real falqon data.
# --------------------------------------------------------------------------- #
@falqon_only
def test_index_builds_over_real_falqon():
    idx = ni.build_node_index(FALQON)
    assert idx is not None
    assert idx["counts"]["conceptric_nodes"] == 91
    # every source resolved (the join needs all five namespaces present).
    for k in ("conceptric", "nodemap", "prose", "plan", "chain"):
        assert idx["sources"][k], f"source {k} did not resolve"
    assert idx["substrate_fingerprint"]


@falqon_only
def test_eq_coh_total_resolves_to_page_and_concept():
    """The recon's spine assertion: eq:coh-total resolves to a PAGE and to a concept node.
    The concept resolution rides the isnad rung (the equation is authored inside the
    coherent-circuit-volume derivation fragment); its join is tagged truthfully."""
    idx = ni.build_node_index(FALQON)
    obj = (idx["objects"] or {}).get("eq:coh-total")
    assert obj is not None, "eq:coh-total is not in the index"
    # resolves to a page
    assert obj["page"] == 12
    # resolves to a concept node — its derivation origin (a real applied-graph node)
    assert obj["origin_node"], "eq:coh-total resolved to no concept node"
    assert obj["origin_node"].startswith("derivation:")
    # the join is honestly tagged and its provenance names how it was derived
    assert obj["join"] == "isnad"
    assert obj["isnad_link"] == "link-coherent-l"
    assert any("derivation fragment link-coherent-l" in p for p in obj["join_provenance"])


@falqon_only
def test_unjoinable_object_states_absence():
    """A rendered figure whose fig: label the conceptric never declared resolves to a
    landing (page) but NOT to a concept — and the absence is stated, per the fallback law,
    never papered over with a fabricated node."""
    idx = ni.build_node_index(FALQON)
    obj = (idx["objects"] or {}).get("figure:fig_resources")
    assert obj is not None
    assert obj["page"] == 6                     # it lands
    assert obj["conceptric_nodes"] == []        # but claims no concept
    assert obj["join"] == "landing"
    unresolved = {u["object"] for u in idx["unresolved"]}
    assert "figure:fig_resources" in unresolved
    reason = next(u["reason"] for u in idx["unresolved"]
                  if u["object"] == "figure:fig_resources")
    assert "not a declared conceptric node" in reason


@falqon_only
def test_falqon_figures_enumerate_now():
    """G2: paper_falqon is registered so enumerate_assets stops returning zero figures."""
    from laplace.pipeline import asset_model as am
    figs = [a for a in am.enumerate_assets(FALQON) if a.kind == "figure"]
    ids = {a.id for a in figs}
    assert "figure:fig_resources" in ids
    assert "figure:fig_witness" in ids
    # each resolves its fig: node and lands off the nodemap
    fr = next(a for a in figs if a.id == "figure:fig_resources")
    assert fr.node_id == "fig:resources"
    assert fr.landings and fr.landings[0].page == 6


@falqon_only
def test_paragraph_join_is_clean():
    idx = ni.build_node_index(FALQON)
    # s1-p1 realises fal_clm_001 (the clean prose_provenance join).
    p = (idx["objects"] or {}).get("s1-p1")
    assert p is not None
    assert "fal_clm_001" in p["conceptric_nodes"]
    assert p["join"] == "prose"
    # and the node record carries the paragraph back.
    assert "s1-p1" in idx["nodes"]["fal_clm_001"]["paragraph_ids"]
    assert idx["nodes"]["fal_clm_001"]["section"] == "s1"


# --------------------------------------------------------------------------- #
# G5 — the spatial join machinery (proven on a synthetic nodemap fixture, since
# falqon's labelled equations and paragraphs never share a page).
# --------------------------------------------------------------------------- #
def test_spatial_join_binds_equation_in_paragraph_band():
    """An equation whose measured rect sits below a paragraph marker, same page + column,
    joins that paragraph. Two paragraphs on the page: the equation must pick the one whose
    band contains it, not the other."""
    entries = {
        "p-top": [{"kind": "paragraph", "page": 3, "x0": 54.0, "y0": 100.0, "y1": 100.0}],
        "p-bot": [{"kind": "paragraph", "page": 3, "x0": 54.0, "y0": 400.0, "y1": 400.0}],
        "eq:mid": [{"kind": "equation", "page": 3, "x0": 60.0, "x1": 300.0,
                    "y0": 250.0, "y1": 275.0}],
        "eq:other-col": [{"kind": "equation", "page": 3, "x0": 330.0, "x1": 560.0,
                          "y0": 250.0, "y1": 275.0}],
    }
    joined = ni.spatial_eq_to_paragraph(entries)
    assert joined["eq:mid"] == "p-top"          # 250 is in [100, 400) of the left column
    # the right-column equation has no right-column paragraph → no fabricated join
    assert "eq:other-col" not in joined


def test_spatial_join_empty_when_no_shared_page():
    """Equations and paragraphs that never share a page yield nothing — the honest zero
    (exactly falqon's case: labelled equations are appendix-only, paragraphs body-only)."""
    entries = {
        "s1-p1": [{"kind": "paragraph", "page": 1, "x0": 54.0, "y0": 100.0, "y1": 100.0}],
        "eq:apx": [{"kind": "equation", "page": 12, "x0": 60.0, "x1": 300.0,
                    "y0": 250.0, "y1": 275.0}],
    }
    assert ni.spatial_eq_to_paragraph(entries) == {}


@falqon_only
def test_falqon_spatial_join_is_honestly_empty():
    """On the real falqon nodemap the spatial rung binds nothing (the geometry does not
    support it) — so no equation is tagged spatial. The isnad rung is what closes them."""
    idx = ni.build_node_index(FALQON)
    joins = {o["join"] for o in idx["objects"].values() if o["kind"] == "equation"}
    assert "spatial" not in joins


# --------------------------------------------------------------------------- #
# G6 — the walker: depth, cycles, orphans.
# --------------------------------------------------------------------------- #
def _fake_graph(monkeypatch, adj, node_ids=None, labels=None):
    ids = set(node_ids or adj.keys())
    for kids in adj.values():
        ids |= {d for _, d, _ in kids}
    nodes_by_id = {i: {"id": i, "label": (labels or {}).get(i, ""), "kind": "node"}
                   for i in ids}
    monkeypatch.setattr(lineage, "load_graph",
                        lambda corpus, root=None: {
                            "nodes_by_id": nodes_by_id, "adj": adj, "node_ids": set(ids)})


def test_walker_depth_limits(monkeypatch):
    adj = {"A": [("contains", "B", "e1")], "B": [("contains", "C", "e2")],
           "C": [("contains", "D", "e3")]}
    _fake_graph(monkeypatch, adj)
    d1 = lineage.descendants("x", "A", depth=1)
    assert {n["id"] for n in d1["nodes"]} == {"B"}
    d2 = lineage.descendants("x", "A", depth=2)
    assert {n["id"] for n in d2["nodes"]} == {"B", "C"}
    dfull = lineage.descendants("x", "A", depth=0)     # unbounded
    assert {n["id"] for n in dfull["nodes"]} == {"B", "C", "D"}


def test_walker_is_cycle_safe(monkeypatch):
    # A -> B -> C -> A : the unbounded walk must terminate and record the block.
    adj = {"A": [("contains", "B", "")], "B": [("contains", "C", "")],
           "C": [("contains", "A", "")]}
    _fake_graph(monkeypatch, adj)
    d = lineage.descendants("x", "A", depth=0)
    assert d["present"]
    assert "A" in d["health"]["cycles_blocked"]
    assert {n["id"] for n in d["nodes"]} == {"A", "B", "C"}


def test_walker_orphan_and_leaf_honesty(monkeypatch):
    adj = {"A": [("contains", "B", "")]}     # B is a leaf
    _fake_graph(monkeypatch, adj)
    leaf = lineage.descendants("x", "B", depth=0)
    assert leaf["present"] and leaf["is_leaf"]
    assert leaf["health"]["n_descendants"] == 0
    assert leaf["health"]["orphans"] == ["B"]


def test_walker_dangling_target_named(monkeypatch):
    # A -> Z, but Z is not a declared node → dangling, stated in health.
    adj = {"A": [("contains", "Z", "")]}
    monkeypatch.setattr(lineage, "load_graph", lambda corpus, root=None: {
        "nodes_by_id": {"A": {"id": "A", "label": "", "kind": "node"}},
        "adj": adj, "node_ids": {"A"}})
    d = lineage.descendants("x", "A", depth=0)
    assert d["health"]["dangling"] == ["Z"]


def test_walker_unknown_node_present_false(monkeypatch):
    _fake_graph(monkeypatch, {"A": [("contains", "B", "")]})
    d = lineage.descendants("x", "nope", depth=1)
    assert d is not None and d["present"] is False
    assert d["nodes"] == []


@falqon_only
def test_walker_on_real_falqon_graph():
    d = lineage.descendants(FALQON, "cluster:claims", depth=1)
    assert d["present"]
    assert d["health"]["n_descendants"] >= 20
    assert all(c["rel"] in lineage.DESCENT_RELS for c in d["tree"]["children"])


# --------------------------------------------------------------------------- #
# the two doors — contract, composed 404s, staleness.
# --------------------------------------------------------------------------- #
def _call(path, query):
    from laplace.web import provenance_surface as pr
    status, ctype, body = pr.handle(path, query, "GET", b"")
    return status, json.loads(body)


@falqon_only
def test_provenance_door_contract():
    s, o = _call("/provenance/object", {"corpus": [FALQON], "object": ["eq:coh-total"]})
    assert s == 200
    assert o["resolved"] is True
    assert isinstance(o["glance"], str) and o["glance"]
    # working carries the fields
    assert o["working"]["page"] == 12
    assert o["working"]["isnad"]["link"] == "link-coherent-l"
    # audit names the join and its per-field provenance + the staleness note
    assert o["audit"]["join"] == "isnad"
    assert o["audit"]["join_provenance"]
    assert "staleness" in o["audit"]


@falqon_only
def test_provenance_door_composed_404():
    s, o = _call("/provenance/object", {"corpus": [FALQON], "object": ["eq:nope"]})
    assert s == 404
    assert o["resolved"] is False
    # a composed 404 body, never a bare {"error": ...}
    assert "error" not in o
    assert "eq:nope" in o["glance"]
    assert o["audit"]["reason"]


@falqon_only
def test_descendants_door_contract():
    s, o = _call("/descendants/node", {"corpus": [FALQON], "node": ["cluster:claims"],
                                       "depth": ["1"]})
    assert s == 200
    assert o["present"] is True
    assert o["glance"]
    assert o["working"]["n_descendants"] >= 20
    assert isinstance(o["working"]["sections_touched"], list)
    assert "edges" in o["audit"] and "health" in o["audit"]
    assert "staleness" in o["audit"]


@falqon_only
def test_descendants_door_composed_404():
    s, o = _call("/descendants/node", {"corpus": [FALQON], "node": ["no_such"],
                                       "depth": ["2"]})
    assert s == 404
    assert o["present"] is False
    assert "error" not in o
    assert "no_such" in o["glance"]


@falqon_only
def test_index_freshness_after_mint(tmp_path, monkeypatch):
    """A minted index reads fresh against unchanged sources; the door's audit says so.

    The mint writes LIVE derived state and stamps a fresh ``built_at``, so it is gated
    read-only under pytest (``derived_writes``, WO-20260817-test-mutates-working-tree).
    This test is a test OF the mint, so it opts in deliberately — and then puts the
    committed bytes back, byte-for-byte, so a green run leaves the tree exactly as it
    found it. The restore is the point: the old ``finally: pass`` is what let a
    timestamp-only diff survive every run."""
    from laplace.pipeline import derived_writes as dw
    before = ni.index_path(FALQON)
    before_bytes = before.read_bytes() if (before and before.is_file()) else None
    monkeypatch.setenv(dw.WRITE_FLAG, "1")
    p = ni.write_node_index(FALQON)
    assert p is not None and p.is_file()
    try:
        idx, freshness = ni.get_index(FALQON)
        assert freshness["minted"] is True
        assert freshness["fresh"] is True
        assert freshness["moved"] == []
    finally:
        # derived state: restore the committed bytes (a mint only refreshes built_at
        # when the substrate has not moved). A checkout that had none keeps the new file.
        if before_bytes is not None:
            before.write_bytes(before_bytes)


def test_door_unknown_corpus_composed_404():
    from laplace.web import provenance_surface as pr
    status, ctype, body = pr.handle(
        "/provenance/object", {"corpus": ["no-such-corpus"], "object": ["x"]}, "GET", b"")
    o = json.loads(body)
    assert status == 404
    assert "error" not in o
    assert o["glance"]
