"""Tests for concept_lens - the integrade wiring that makes the physics lens reconstructable-THROUGH.

Contracts: the SEMANTIC parent grades the lens pillar -> theme -> paper (not by-kind directory); an
unclustered singleton attaches to the lens root; the conceptric file rides with its theme; the 236-style
conceptric edges parse into UNDIRECTED shared-referent tokens so build_reach COUPLES the papers that share
concept-atoms (not a flat theme-share); and the whole thing reconstructs THROUGH the grades (the ring
descends pillar->theme->paper, grade-local, and the gate stays green - the authored coarse nodes keep their
adjudicated essence). Mostly hermetic (a miniature lens repo); the parse contract also runs on synthetic input.
"""

from __future__ import annotations

import json

import pytest

from laplace.engine import concept_lens, keeper, keeper_ring, self_shard


# --- the semantic parent map (the integrade / vertical link) ---

def test_lens_membership_grades_pillar_theme_paper():
    index = {
        "concept_corpus/pillars/P.md": {"kind": "md", "edges": [{"to": "concept_corpus/themes/T.md"}]},
        "concept_corpus/themes/T.md": {"kind": "md", "edges": [{"to": "life_corpus/papers/x.md"}]},
        "concept_corpus/atoms/x.md": {"kind": "md", "edges": [
            {"to": "concept_corpus/themes/T.md"}, {"to": "life_corpus/papers/x.md"}]},
        "concept_corpus/atoms/lonely.md": {"kind": "md", "edges": [{"to": "life_corpus/papers/lonely.md"}]},
        "concept_corpus/conceptric/T.md": {"kind": "md", "edges": []},
        "concept_corpus/_manifest.json": {"kind": "json", "edges": []},
    }
    m = concept_lens.lens_membership(index)
    assert m["concept_corpus/atoms/x.md"] == "concept_corpus/themes/T.md"        # paper -> its theme (own up-edge)
    assert m["concept_corpus/themes/T.md"] == "concept_corpus/pillars/P.md"      # theme -> pillar (inverted down-edge)
    assert m["concept_corpus/pillars/P.md"] == "concept_corpus"                  # pillar -> the lens root
    assert m["concept_corpus/atoms/lonely.md"] == "concept_corpus"               # a singleton -> the lens root
    assert m["concept_corpus/conceptric/T.md"] == "concept_corpus/themes/T.md"   # conceptric rides its theme
    assert "concept_corpus/_manifest.json" not in m                             # metadata -> falls to dir_parent


# --- the conceptric lateral edges (the within-grade / coupling link) ---

def test_parse_conceptric_and_couple(tmp_path):
    cdir = tmp_path / "concept_corpus" / "conceptric"
    cdir.mkdir(parents=True)
    (cdir / "T.md").write_text(
        "# Connectome - T\n\n## Edges\n"
        "- **paper-a:mechanism-one** -> **paper-b:mechanism-two**  _(shared-mechanism, high, haiku)_\n"
        "- **paper-a:concept-z** -> **paper-b:concept-w**  _(method-reuse, medium, haiku)_\n"
        "- **paper-a:thing** -> **paper-c:other**  _(concept-dependency, high, haiku)_\n",
        encoding="utf-8")
    edges = concept_lens.parse_conceptric(tmp_path)
    assert len(edges) == 3
    assert edges[0]["src_paper"] == "concept_corpus/atoms/paper-a.md"
    assert edges[0]["dst_paper"] == "concept_corpus/atoms/paper-b.md"
    assert {e["kind"] for e in edges} == {"shared-mechanism", "method-reuse", "concept-dependency"}

    ei = concept_lens.lens_edge_index(tmp_path)
    a, b, c = (f"concept_corpus/atoms/paper-{x}.md" for x in "abc")
    assert set(ei[a]) >= set(ei[b])                          # a & b share their 2 edge tokens (undirected)
    assert len(set(ei[a]) & set(ei[b])) == 2                 # 2 shared conceptric edges
    assert len(set(ei[a]) & set(ei[c])) == 1                 # 1 with c

    leaf = lambda nid: {"id": nid, "leaf": True, "members": [], "keywords": [], "coverage": []}
    nodes = {a: leaf(a), b: leaf(b), c: leaf(c)}
    reach = keeper_ring.build_reach(nodes, ei)
    assert keeper_ring.coupling(reach, a, b) == 2            # coupling = the count of shared atoms (real)
    assert keeper_ring.coupling(reach, a, c) == 1


@pytest.fixture()
def bridges_repo(tmp_path):
    cc = tmp_path / "concept_corpus"
    cc.mkdir(parents=True)
    (cc / "cross_pillar_bridges.md").write_text(
        "# Cross-pillar bridges\n\n## Faithful (wired)\n"
        "- **concept_corpus/themes/A.md** <=> **concept_corpus/themes/B.md**  _(shared-principle, high)_\n"
        "  the real bridge\n\n## Conjectural (the grit; surfaced on ideation, never asserted)\n"
        "- **concept_corpus/themes/C.md** <=> **concept_corpus/themes/D.md**  _(method-transfer, unresolved)_\n"
        "  IF this holds THEN something follows\n",
        encoding="utf-8")
    return tmp_path


def test_faithful_bridges_wire_into_standard_coupling(bridges_repo):
    cp = concept_lens.cross_pillar_edge_index(bridges_repo)
    a, b = "concept_corpus/themes/A.md", "concept_corpus/themes/B.md"
    assert a in cp and b in cp and cp[a] == cp[b] and len(cp[a]) == 1   # one undirected faithful token, both ends
    assert "concept_corpus/themes/C.md" not in cp                      # the conjectural bridge is NOT in standard coupling
    assert not any(concept_lens.is_conjecture_token(t) for v in cp.values() for t in v)


def test_conjectural_bridges_are_kept_on_a_separate_channel(bridges_repo):
    # his grit ruling: the refuted/low-confidence link is KEPT (not dropped), on a conjecture:: channel that
    # surfaces ONLY when ideation merges it - never on factual recall.
    conj = concept_lens.conjectural_edge_index(bridges_repo)
    c, d = "concept_corpus/themes/C.md", "concept_corpus/themes/D.md"
    assert c in conj and d in conj and conj[c] == conj[d]              # the conjecture mints a shared token, both ends
    assert all(concept_lens.is_conjecture_token(t) for v in conj.values() for t in v)
    assert "concept_corpus/themes/A.md" not in conj                   # the faithful bridge is not on this channel

    # recall reach (faithful only) does NOT couple C<->D; ideation reach (merge conjectural) DOES, flagged
    leaf = lambda nid: {"id": nid, "leaf": True, "members": [], "keywords": [], "coverage": []}
    nodes = {n: leaf(n) for n in (c, d)}
    recall = keeper_ring.build_reach(nodes, concept_lens.cross_pillar_edge_index(bridges_repo))
    ideate = keeper_ring.build_reach(nodes, conj)
    assert keeper_ring.coupling(recall, c, d) == 0                     # invisible to recall
    assert keeper_ring.coupling(ideate, c, d) == 1                     # surfaces on ideation
    pulls = keeper_ring.neighbour_pull(nodes, ideate, [c], budget=8, pull_fraction=0.9, scope_ids=[c, d])
    assert pulls and pulls[0]["node"] == d and pulls[0]["conjectural"] is True   # surfaced FLAGGED unresolved


def test_merge_edge_index_dedups_and_is_pure():
    base = {"a": ["t1"], "b": ["t2"]}
    extra = {"a": ["t1", "t3"], "c": ["t4"]}
    out = concept_lens.merge_edge_index(base, extra)
    assert out["a"] == ["t1", "t3"] and out["c"] == ["t4"]   # dedup per node, new keys added
    assert base["a"] == ["t1"]                               # base not mutated (pure)


# --- end to end: a miniature lens reconstructs THROUGH the grades ---

# physics-termed slugs (as in the real corpus): a node surfaces at the words in its path stem, so the
# slug must carry meaning for the ring to route to it - a thin name like 'alpha' carries none.
_PA = "concept_corpus/atoms/stochastic-liouville-bath-2017.md"
_PB = "concept_corpus/atoms/stochastic-harmonic-bath-2018.md"
_SINGLE = "concept_corpus/atoms/entropic-gravity-singleton-2021.md"
_TH = "concept_corpus/themes/th.md"
_PIL = "concept_corpus/pillars/pil.md"


@pytest.fixture()
def lens_repo(tmp_path):
    """A miniature concept_corpus: one pillar over one theme over two papers + a singleton + a conceptric."""
    cc = tmp_path / "concept_corpus"
    (cc / "pillars").mkdir(parents=True)
    (cc / "themes").mkdir()
    (cc / "atoms").mkdir()
    (cc / "conceptric").mkdir()
    (cc / "pillars" / "pil.md").write_text(
        "# Open systems pillar\n\nThe foundational half.\n\n[[concept_corpus/themes/th.md]]\n", encoding="utf-8")
    (cc / "themes" / "th.md").write_text(
        "# Stochastic open systems theme\n\nExact stochastic representations.\n\n"
        "[[life_corpus/papers/stochastic-liouville-bath-2017.md]]\n"
        "[[life_corpus/papers/stochastic-harmonic-bath-2018.md]]\n", encoding="utf-8")
    (cc / "atoms" / "stochastic-liouville-bath-2017.md").write_text(
        "# stochastic liouville bath\n\ninfluence functional derivation.\n\n"
        "[[concept_corpus/themes/th.md]]\n[[life_corpus/papers/stochastic-liouville-bath-2017.md]]\n",
        encoding="utf-8")
    (cc / "atoms" / "stochastic-harmonic-bath-2018.md").write_text(
        "# stochastic harmonic bath\n\nspin-boson representation.\n\n"
        "[[concept_corpus/themes/th.md]]\n[[life_corpus/papers/stochastic-harmonic-bath-2018.md]]\n",
        encoding="utf-8")
    (cc / "atoms" / "entropic-gravity-singleton-2021.md").write_text(
        "# entropic gravity\n\na singleton, no recurring theme.\n\n[[life_corpus/papers/entropic.md]]\n",
        encoding="utf-8")
    (cc / "conceptric" / "th.md").write_text(
        "# Connectome - th\n\n## Edges\n"
        "- **stochastic-liouville-bath-2017:bath-coupling** -> "
        "**stochastic-harmonic-bath-2018:bath-coupling**  _(shared-mechanism, high, haiku)_\n",
        encoding="utf-8")
    (cc / "_atoms_manifest.json").write_text(json.dumps({"papers": [
        {"slug": "stochastic-liouville-bath-2017", "theme": "th", "atoms": [
            {"name": "influence-functional-derivation", "kind": "mechanism",
             "statement": "the bath is kept exactly via an influence functional and traded for noise",
             "locator": "Sec 2"},
            {"name": "stochastic-liouville-equation", "kind": "result",
             "statement": "a closed stochastic Liouville equation for the reduced density matrix",
             "locator": "Sec 3"}]},
        {"slug": "stochastic-harmonic-bath-2018", "theme": "th", "atoms": [
            {"name": "spin-boson-implementation", "kind": "method",
             "statement": "first numerical implementation on a driven spin-boson model", "locator": "Sec 4"}]},
    ]}), encoding="utf-8")
    return tmp_path


_ATOM = _PA + concept_lens.ATOM_SEP + "influence-functional-derivation"   # a g0 atom node id


def test_atoms_are_the_substrate_floor(lens_repo):
    leaves = concept_lens.lens_atom_leaves(lens_repo)
    assert _ATOM in leaves and "atom-mechanism" == leaves[_ATOM]["kind"]   # atoms materialised as g0 nodes
    assert "influence" in leaves[_ATOM]["essence"].lower()                 # the statement IS the handle
    assert concept_lens.atom_parent(_ATOM) == _PA                          # an atom hangs off its paper
    assert concept_lens.atom_parent(_PA) is None                           # a paper is not an atom


def test_keeper_grades_lens_through_meaning(lens_repo):
    nodes = keeper.build_self(lens_repo)
    th, pil = nodes[_TH], nodes[_PIL]
    # the floor is ATOMS: atom(g0) -> paper(g1) -> theme(g2) -> pillar(g3) -> lens(g4)
    assert nodes[_ATOM]["grade"] == 0 and nodes[_ATOM]["parent"] == _PA   # atom is the substrate floor
    assert nodes[_PA]["grade"] == 1 and nodes[_PA]["parent"] == _TH       # paper is a CLUSTER of atoms, off g0
    assert th["grade"] == 2 and th["parent"] == _PIL                      # theme g2
    assert pil["grade"] == 3 and nodes["concept_corpus"]["grade"] == 4    # pillar g3, lens organ g4
    assert nodes[_SINGLE]["parent"] == "concept_corpus"                   # a singleton paper -> the lens root
    assert th["authored"] is True and "stochastic" in th["essence"].lower()   # authored essence preserved
    assert keeper.local_faithfulness(nodes)["pass"] is True              # the gate stays green (ascended-only)


def test_coupling_is_structural_not_vocabulary(lens_repo):
    # the two papers share physics vocabulary ('stochastic', 'bath') AND a conceptric edge; coupling must
    # count the SHARED SUBSTRATE (conceptric + same theme), never the shared words - atoms couple by their
    # paper (containment), so a keyword bag never leaks into paper coupling.
    nodes = keeper.build_self(lens_repo)
    ei = {n: [e["to"] for e in sh.get("edges", [])] for n, sh in self_shard.shard_repo(lens_repo).items()}
    ei = concept_lens.merge_edge_index(ei, concept_lens.lens_edge_index(lens_repo))
    reach = keeper_ring.build_reach(nodes, ei)
    assert keeper_ring.coupling(reach, _PA, _PB) >= 1                     # the conceptric COUPLES them
    assert keeper_ring.coupling(reach, _PA, _SINGLE) == 0                 # no shared substrate -> 0 (not vocab)


def test_reconstruct_through_the_lens(lens_repo):
    nodes = keeper.build_self(lens_repo)
    ei = {n: [e["to"] for e in sh.get("edges", [])] for n, sh in self_shard.shard_repo(lens_repo).items()}
    ei = concept_lens.merge_edge_index(ei, concept_lens.lens_edge_index(lens_repo))
    reach = keeper_ring.build_reach(nodes, ei)
    # the ring descends lens -> pillar -> theme -> paper -> ATOM for a physics query, grade-local
    tr: dict = {}
    env = keeper_ring.reconstruct(nodes, "concept_corpus", "stochastic bath influence functional",
                                  reach=reach, pull_fraction=0.5, trace=tr)
    grades = {g for _, g in tr["activated"]}
    assert {3, 2, 1, 0} <= grades                                        # touched pillar(3), theme(2), paper(1), atom(0)
    assert tr["visited"] < len(nodes)                                    # grade-local, not a flat scan
    assert any(concept_lens.ATOM_SEP in l for l in env["leaves"])        # bottomed at an atom (the substrate)
