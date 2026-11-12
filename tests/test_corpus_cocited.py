"""W7.1 - the co-citation surface (/corpus/co-cited), the mechanism behind conceptric2's
"shared citations" lateral axis. FAIL-CLOSED per FORK 5's BUILT ruling: real pairs derivable
from the live conceptric, honest empty for a corpus without citations, bounded payload."""

from __future__ import annotations

import json

from laplace.research import corpus_cocited as cc


def _net(nodes, edge_index):
    return {"nodes": nodes, "edge_index": edge_index}


def _synthetic():
    """A tiny corpus: 3 references, 3 citing sections. sec:1 & sec:2 co-cite ref:B (via the
    node-id form AND the bare-key form, to prove both normalise); sec:3 cites ref:C alone."""
    nodes = {
        "paper://": {"kind": "paper"},
        "references": {"kind": "references"},
        "ref:A": {"kind": "citation", "essence": "Alpha 2001 — a"},
        "ref:B": {"kind": "citation", "essence": "Beta 2002 — b"},
        "ref:C": {"kind": "citation", "essence": "Gamma 2003 — c"},
        "sec:1": {"kind": "section", "essence": "section one"},
        "sec:2": {"kind": "section", "essence": "section two"},
        "sec:3": {"kind": "section", "essence": "section three"},
    }
    edge_index = {
        "sec:1": ["sec:1", "ref:A", "ref:B"],   # node-id form
        "sec:2": ["sec:2", "sem::B"],           # bare-key form behind an audit marker
        "sec:3": ["sec:3", "ref:C"],
        "ref:A": ["ref:A"], "ref:B": ["ref:B"], "ref:C": ["ref:C"],
    }
    return _net(nodes, edge_index)


# ---- BUILT: real pairs, both referent forms normalised -------------------------------

def test_pairs_are_real_co_citations():
    out = cc.co_cited(_synthetic(), "syn")
    assert out["n_bibkeys"] == 3
    assert out["n_citing_nodes"] == 3          # all three sections cite something live
    assert out["n_pairs"] == 1
    p = out["pairs"][0]
    assert {p["a"], p["b"]} == {"sec:1", "sec:2"}
    assert p["shared"] == ["ref:B"]            # bare 'B' + 'ref:B' both fold to ref:B
    assert p["n"] == 1
    assert out["truncated"] is False


def test_focus_mode_returns_neighbours():
    out = cc.co_cited(_synthetic(), "syn", node="sec:1")
    assert out["node"] == "sec:1"
    assert sorted(out["cites"]) == ["ref:A", "ref:B"]
    ids = [n["id"] for n in out["neighbours"]]
    assert ids == ["sec:2"]
    assert out["neighbours"][0]["shared"] == ["ref:B"]
    assert out["neighbours"][0]["n"] == 1


# ---- honest empty (never a false "no neighbours") ------------------------------------

def test_focus_with_no_shared_refs_is_honestly_empty():
    out = cc.co_cited(_synthetic(), "syn", node="sec:3")
    assert out["cites"] == ["ref:C"]           # it DID cite — the honesty is "no CO-citers"
    assert out["neighbours"] == []
    assert out["n_neighbours"] == 0


def test_citation_node_is_not_a_citer():
    # a reference node itself is the substrate, not a co-citing work
    out = cc.co_cited(_synthetic(), "syn", node="ref:A")
    assert out["cites"] == []
    assert out["neighbours"] == []


def test_corpus_without_citations_is_honestly_empty():
    nodes = {"paper://": {"kind": "paper"},
             "sec:1": {"kind": "section", "essence": "one"},
             "sec:2": {"kind": "section", "essence": "two"}}
    edge_index = {"sec:1": ["sec:1"], "sec:2": ["sec:2"]}
    net = _net(nodes, edge_index)
    out = cc.co_cited(net, "nocite")
    assert out["n_bibkeys"] == 0
    assert out["n_citing_nodes"] == 0
    assert out["pairs"] == []
    assert out["n_pairs"] == 0
    node_out = cc.co_cited(net, "nocite", node="sec:1")
    assert node_out["neighbours"] == []
    assert node_out["cites"] == []


# ---- bounded payload (golden law: <=40 rows, <=16KB) ---------------------------------

def test_neighbours_bounded_and_truncated_flag():
    nodes = {"ref:X": {"kind": "citation", "essence": "X"}}
    edge_index = {}
    for i in range(60):
        sid = f"sec:{i}"
        nodes[sid] = {"kind": "section", "essence": "s" * 400}
        edge_index[sid] = [sid, "ref:X"]
    out = cc.co_cited(_net(nodes, edge_index), "big", node="sec:0")
    assert out["n_neighbours"] == 59           # true total reported
    assert len(out["neighbours"]) == 40        # capped at the golden row bound
    assert out["truncated"] is True
    assert len(json.dumps(out).encode("utf-8")) <= 16 * 1024


def test_pairs_bounded():
    nodes = {"ref:X": {"kind": "citation", "essence": "X"}}
    edge_index = {}
    for i in range(20):                          # C(20,2)=190 pairs, all sharing ref:X
        sid = f"sec:{i}"
        nodes[sid] = {"kind": "section", "essence": "s"}
        edge_index[sid] = [sid, "ref:X"]
    out = cc.co_cited(_net(nodes, edge_index), "big")
    assert out["n_pairs"] == 190
    assert len(out["pairs"]) == 40
    assert out["truncated"] is True


def test_sort_is_deterministic_most_shared_first():
    nodes = {"ref:A": {"kind": "citation", "essence": "A"},
             "ref:B": {"kind": "citation", "essence": "B"},
             "sec:1": {"kind": "section", "essence": "1"},
             "sec:2": {"kind": "section", "essence": "2"},
             "sec:3": {"kind": "section", "essence": "3"}}
    # sec:1/sec:2 share BOTH refs; sec:1/sec:3 share only ref:A
    edge_index = {"sec:1": ["ref:A", "ref:B"], "sec:2": ["ref:A", "ref:B"], "sec:3": ["ref:A"]}
    out = cc.co_cited(_net(nodes, edge_index), "syn")
    assert out["pairs"][0]["n"] == 2           # most-shared pair leads
    assert {out["pairs"][0]["a"], out["pairs"][0]["b"]} == {"sec:1", "sec:2"}


# ---- the live conceptric: verify the hand-checked pair -------------------------------

def test_live_default_corpus_reproduces_a_hand_verified_pair():
    """thm:hardy-littlewood-collapse and irf:circle-method-equivalence both \\cite vaughan-1997
    in subset-sum-itqde (hand-verified against the live ledger). The endpoint must reproduce it."""
    from laplace.research import corpus_ingest as ci
    from laplace.web.scanner import _repo_root
    rr = _repo_root()
    name = ci.default_corpus(rr)
    troot = ci.resolve_corpus(rr, name)
    net = ci.corpus_network(troot, repo_root=rr, name=name)

    a, b = "thm:hardy-littlewood-collapse", "irf:circle-method-equivalence"
    if a not in net["nodes"] or b not in net["nodes"]:
        import pytest
        pytest.skip("live corpus lacks the hand-verified nodes (corpus drifted)")

    out = cc.co_cited(net, name, node=a)
    neigh = {n["id"]: n for n in out["neighbours"]}
    assert b in neigh, f"{b} should be co-cited with {a}"
    assert "ref:vaughan-1997" in neigh[b]["shared"]
    # bounded first paint
    assert len(json.dumps(out).encode("utf-8")) <= 16 * 1024
