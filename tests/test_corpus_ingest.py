"""The node-CRUD overlay vocabulary: building a conceptric together, not only correcting one.

These exercise apply_overlay's structural ops (add/delete/move-node, set-kind) end to end through
build_corpus_network, asserting the BUILT tree (keeper.build_tree output) reflects each edit. No
embedding (semantic=False), so the suite is PSU-safe and runs in the hello check."""
from __future__ import annotations

from pathlib import Path

import pytest

from laplace.research import corpus_ingest as ci


def _root() -> Path:
    # the registry is the one door to a corpus tex root, and resolve_corpus applies
    # the main.tex gate itself - an absent corpus resolves to None, never a guess.
    r = ci.resolve_corpus(Path(__file__).resolve().parents[1], "law-of-laws")
    if r is None:
        pytest.skip("law-of-laws corpus not present")
    return r


def test_baseline_builds_without_overlay():
    net = ci.build_corpus_network(_root())
    assert net["nodes"], "the atomiser produced an empty tree"
    assert net["root"] == "paper://"


def test_add_node_inserts_a_derivation_step():
    root = _root()
    base = ci.build_corpus_network(root)
    # pick a real equation to hang a step under
    eq = next(k for k, v in base["nodes"].items() if v.get("kind") == "equation")
    overlay = [{"kind": "add-node", "node": "step:test-1", "parent": eq,
                "node_kind": "derivation-step", "essence": "substitute (3) into (2)",
                "target": eq}]
    net = ci.build_corpus_network(root, overlay=overlay)
    assert "step:test-1" in net["nodes"]
    n = net["nodes"]["step:test-1"]
    assert n["kind"] == "derivation-step"
    assert "substitute" in n["essence"]
    # it derives-from eq (the confirmed edge), so eq is reachable from the step
    assert eq in net["edge_index"]["step:test-1"]
    # the parent equation is now internal (it has a derivation child)
    assert net["nodes"][eq]["leaf"] is False


def test_set_kind_retags_and_toggles_provenance_exemption():
    root = _root()
    eq = next(k for k, v in ci.build_corpus_network(root)["nodes"].items()
              if v.get("kind") == "equation")
    net = ci.build_corpus_network(root, overlay=[{"kind": "set-kind", "node": eq, "value": "definition"}])
    assert net["nodes"][eq]["kind"] == "definition"
    assert eq in net["postulates"]              # definition is provenance-exempt
    net2 = ci.build_corpus_network(root, overlay=[{"kind": "set-kind", "node": eq, "value": "result"}])
    assert eq not in net2["postulates"]         # retagging away re-arms the gap flag


def test_move_node_reparents():
    root = _root()
    base = ci.build_corpus_network(root)
    secs = [k for k, v in base["nodes"].items() if v.get("kind") == "section"]
    eq = next(k for k, v in base["nodes"].items() if v.get("kind") == "equation")
    old_parent = base["nodes"][eq]["parent"]
    new_parent = next(s for s in secs if s != old_parent)
    net = ci.build_corpus_network(root, overlay=[{"kind": "move-node", "node": eq, "target": new_parent}])
    assert net["nodes"][eq]["parent"] == new_parent


def test_delete_node_removes_and_reparents_children():
    root = _root()
    base = ci.build_corpus_network(root)
    eq = next(k for k, v in base["nodes"].items() if v.get("kind") == "equation")
    parent = base["nodes"][eq]["parent"]
    # add a child under eq, then delete eq -> the child must survive, reparented to eq's parent
    overlay = [
        {"kind": "add-node", "node": "step:orphan", "parent": eq, "node_kind": "derivation-step",
         "essence": "a step that must outlive its parent"},
        {"kind": "delete-node", "node": eq},
    ]
    net = ci.build_corpus_network(root, overlay=overlay)
    assert eq not in net["nodes"]
    assert "step:orphan" in net["nodes"]
    assert net["nodes"]["step:orphan"]["parent"] == parent


def test_spine_is_ordered_and_curated():
    """The apex narrative chain: set-spine places a node on it with order + narrative; the built
    net['spine'] is the ordered, curated list (empty until placed). unset-spine removes it."""
    root = _root()
    base = ci.build_corpus_network(root)
    assert base["spine"] == []                      # nothing on the chain until curated
    eqs = [k for k, v in base["nodes"].items() if v.get("kind") == "equation"][:2]
    overlay = [
        {"kind": "set-spine", "node": eqs[1], "ord": 2, "narrative": "and then the second result"},
        {"kind": "set-spine", "node": eqs[0], "ord": 1, "narrative": "first, the headline result"},
    ]
    net = ci.build_corpus_network(root, overlay=overlay)
    assert [s["id"] for s in net["spine"]] == [eqs[0], eqs[1]]   # sorted by ord, not insertion
    assert net["spine"][0]["narrative"] == "first, the headline result"
    assert net["spine"][0]["kind"] == "equation"
    # remove the first from the chain
    net2 = ci.build_corpus_network(root, overlay=overlay + [{"kind": "unset-spine", "node": eqs[0]}])
    assert [s["id"] for s in net2["spine"]] == [eqs[1]]


def test_ledger_to_overlay_round_trip(tmp_path):
    """The route's backing path: rewire_add -> jsonl ledger -> rewire_list -> corpus_network overlay.
    Uses a TEMP repo_root for the ledger (the real corpus tex for the build), so nothing touches the
    live corpus_friction/. This is what POST /corpus/rewire then GET /corpus/content exercises."""
    root = _root()
    eq = next(k for k, v in ci.build_corpus_network(root)["nodes"].items()
              if v.get("kind") == "equation")
    ok = ci.rewire_add(tmp_path, "law-of-laws", {
        "kind": "add-node", "node": "step:rt-1", "parent": eq,
        "node_kind": "derivation-step", "essence": "round-trip step"})
    assert ok.get("ok")
    overlay = ci.rewire_list(tmp_path, "law-of-laws")
    assert len(overlay) == 1 and overlay[0]["node"] == "step:rt-1"
    net = ci.corpus_network(root, repo_root=tmp_path, name="law-of-laws")
    assert "step:rt-1" in net["nodes"]
    assert net["nodes"]["step:rt-1"]["essence"] == "round-trip step"


def test_dep_grade_floors_postulates_and_climbs():
    """Dependency grade: postulates and dependency-free nodes at 0; a node deriving from a grade-k
    node is at least k+1. Built from a small synthetic net so the invariant is exact."""
    leaves = {
        "paper://": {"kind": "paper", "essence": "", "keywords": []},
        "eq:ax": {"kind": "postulate", "essence": "an axiom", "keywords": [], "postulate": True},
        "eq:a": {"kind": "equation", "essence": "first", "keywords": []},
        "eq:b": {"kind": "equation", "essence": "second", "keywords": []},
    }
    parent = {"eq:ax": "paper://", "eq:a": "paper://", "eq:b": "paper://"}
    edge_index = {"eq:a": ["eq:a", "eq:ax"], "eq:b": ["eq:b", "eq:a"]}  # a<-ax, b<-a
    net = {"nodes": ci.keeper.build_tree(leaves, parent.get, root_id="paper://"),
           "edge_index": edge_index, "postulates": {"eq:ax"}}
    dg = ci.dep_grade(net)
    assert dg["eq:ax"] == 0 and dg["eq:a"] == 1 and dg["eq:b"] == 2


def test_neighborhood_directions_and_filtering():
    """The connectivity neighborhood: a real equation's consumers land ABOVE, its dependencies/
    candidates BELOW, sections never appear (containment, not derivation)."""
    root = _root()
    net = ci.corpus_network(root, repo_root=Path("."), name="law-of-laws")
    cand = ci.candidates_cached(root)
    # find an equation that has at least one consumer
    target = None
    for nid, n in net["nodes"].items():
        if n.get("kind") != "equation":
            continue
        nb = ci.neighborhood(net, nid, cand)
        if nb["above"]:
            target = nb
            break
    assert target is not None, "expected at least one equation with a consumer"
    # no section/citation leaks into any zone (derivation DAG only)
    for zone in ("above", "below", "lateral"):
        for m in target[zone]:
            assert m["kind"] in ci.DERIVATION_KINDS, f"{m['id']} ({m['kind']}) leaked into {zone}"
    assert target["node"]["n_above"] == len([x for x in target["above"]]) or target["truncated"]["above"]


def test_neighborhood_reflects_a_confirmed_edge():
    """Confirming a dependency moves it from candidate to a real below-edge with prov=confirmed."""
    root = _root()
    base = ci.corpus_network(root, repo_root=Path("."), name="law-of-laws")
    cand = ci.candidates_cached(root)
    if not cand:
        # .corpus_candidates.json is a regenerable, gitignored embedding cache: present on
        # a machine that has run the semantic pass, absent on a fresh clone. No cache, no
        # candidate edges to confirm - skip rather than assert on environment state.
        pytest.skip("no corpus-candidates cache in this environment")
    # an equation with a candidate dependency
    src = tgt = None
    for nid, n in base["nodes"].items():
        if n.get("kind") == "equation":
            nb = ci.neighborhood(base, nid, cand)
            cands = [b for b in nb["below"] if b["prov"] == "candidate"]
            if cands:
                src, tgt = nid, cands[0]["id"]
                break
    assert src and tgt
    net = ci.build_corpus_network(root, overlay=[{"kind": "confirm-edge", "node": src, "target": tgt}])
    nb = ci.neighborhood(net, src, cand)
    rec = next((b for b in nb["below"] if b["id"] == tgt), None)
    assert rec and rec["prov"] == "confirmed"


def test_neighborhood_excludes_retired_nodes():
    """A retired node (projection.retired) must not surface as anyone's neighbour - no dependency,
    consumer, lateral, or candidate. Retiring a live neighbour makes it vanish from the view (his:
    retired nodes must not show up in the editor offering redundant connections)."""
    root = _root()
    net = ci.corpus_network(root, repo_root=Path("."), name="law-of-laws")
    cand = ci.candidates_cached(root)
    # find an equation whose neighborhood names at least one other node in some zone
    src = victim = zone = None
    for nid, n in net["nodes"].items():
        if n.get("kind") != "equation":
            continue
        nb = ci.neighborhood(net, nid, cand)
        for z in ("below", "above", "lateral"):
            if nb[z]:
                src, victim, zone = nid, nb[z][0]["id"], z
                break
        if src:
            break
    assert src and victim, "expected an equation with at least one neighbour"
    # retire the neighbour, rebuild the neighborhood: it must be gone from every zone
    net["nodes"][victim].setdefault("projection", {})["retired"] = True
    nb2 = ci.neighborhood(net, src, cand)
    for z in ("below", "above", "lateral"):
        assert victim not in {m["id"] for m in nb2[z]}, f"retired {victim} still leaked into {z}"


def test_gaps_are_underived_derivation_nodes():
    """A gap = a derivation node, not a postulate, with no derivation dependency. Marking it a
    postulate clears the gap; the count is well-defined."""
    root = _root()
    base = ci.build_corpus_network(root)
    g0 = ci.gaps(base)
    assert g0, "the hollow DAG should have gaps"
    victim = g0[0]
    cleared = ci.gaps(ci.build_corpus_network(root, overlay=[{"kind": "set-kind", "node": victim, "value": "postulate"}]))
    assert victim not in cleared and len(cleared) == len(g0) - 1


def test_derivation_subtree_closes_and_flags_gaps():
    """The closure of a node includes the node itself and is gap-flagged; a confirmed dependency
    deepens it."""
    root = _root()
    base = ci.build_corpus_network(root)
    cand = ci.candidates_cached(root)
    # an equation with a candidate to confirm
    src = tgt = None
    for nid, n in base["nodes"].items():
        if n.get("kind") == "equation":
            nb = ci.neighborhood(base, nid, cand)
            c = [b for b in nb["below"] if b["prov"] == "candidate"]
            if c:
                src, tgt = nid, c[0]["id"]
                break
    sub0 = ci.derivation_subtree(base, src)
    assert any(n["id"] == src for n in sub0["nodes"])
    assert all(n["gap"] is False for n in sub0["nodes"] if n["postulate"])
    net = ci.build_corpus_network(root, overlay=[{"kind": "confirm-edge", "node": src, "target": tgt}])
    sub1 = ci.derivation_subtree(net, src)
    assert {n["id"] for n in sub1["nodes"]} >= {src, tgt}   # the dependency is now in the closure


def test_dag_map_grades_and_flags():
    root = _root()
    net = ci.build_corpus_network(root)
    mp = ci.dag_map(net)
    assert mp["nodes"] and mp["n_gaps"] == len(ci.gaps(net))
    # only derivation kinds, every node graded
    assert all(n["kind"] in ci.DERIVATION_KINDS and isinstance(n["grade"], int) for n in mp["nodes"])
    # every edge endpoint is present
    ids = {n["id"] for n in mp["nodes"]}
    assert all(e["from"] in ids and e["to"] in ids for e in mp["edges"])


def test_search_finds_by_content_not_id():
    """Search is the precondition for a usable surface: a node is found by words in its content
    (essence/id/kind/lead-in), ranked, never by knowing its id."""
    import re as _re
    root = _root()
    net = ci.corpus_network(root, repo_root=Path("."), name="law-of-laws")
    assert ci.search_nodes(net, "") == []   # empty query -> no results, never the whole corpus
    res = ci.search_nodes(net, "free energy")
    assert res and all("id" in r and "essence" in r for r in res)
    # a node is surfaced by a word from its OWN content, without anyone knowing its id
    for nid, n in net["nodes"].items():
        words = _re.findall(r"[a-z]{6,}", (n.get("essence") or "").lower())
        if words:
            hit = ci.search_nodes(net, words[0])
            assert any(r["id"] == nid for r in hit), f"'{words[0]}' should surface {nid}"
            break


def test_extract_macros_reads_the_preamble():
    macros = ci.extract_macros(_root())
    assert isinstance(macros, dict)
    # the law-of-laws preamble defines \Ocal (an operator) — it must resolve, not stay unknown
    assert any(k for k in macros), "expected at least one macro from the paper preamble"
    if "\\Ocal" in macros:
        assert "mathcal" in macros["\\Ocal"] or "operatorname" in macros["\\Ocal"]


def test_rewire_add_validates_kinds(tmp_path):
    assert "error" in ci.rewire_add(tmp_path, "x", {"kind": "bogus", "node": "n"})
    assert "error" in ci.rewire_add(tmp_path, "x", {"kind": "set-kind", "node": "n", "value": "not-a-kind"})
    ok = ci.rewire_add(tmp_path, "x", {"kind": "add-node", "node": "step:y",
                                       "node_kind": "derivation-step", "essence": "z"})
    assert ok.get("ok") and ok["record"]["essence"] == "z"
