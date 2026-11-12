"""Tests for collaborator_lens - the collaborator corpus (relational map) on the atoms-g0 floor.

Contracts: a collaborator's distilled CONTRIBUTIONS materialise as g0 atoms routed up to the person
(``<person>::<atom>`` via the shared ``atom_parent``); a LOW-confidence contribution is kept and flagged
conjectural (his grit); the cross-corpus wire to the lens is FAITHFUL (matched from shared-themes +
contribution names against real lens slugs, never forced) and couples by a SHARED ``xcorpus::`` token on
both ends (a directed link would not couple). Hermetic - a miniature lens + one distillate.
"""

from __future__ import annotations

import json

import pytest

from laplace.engine import collaborator_lens, concept_lens, keeper_ring


@pytest.fixture()
def collab_repo(tmp_path):
    cc = tmp_path / "concept_corpus"
    (cc / "themes").mkdir(parents=True)
    (cc / "atoms").mkdir()
    (cc / "themes" / "wonder-control-theme.md").write_text("# Wonder control\n", encoding="utf-8")
    (cc / "atoms" / "wonder-method-2020.md").write_text("# wonder method\n", encoding="utf-8")
    dd = tmp_path / "collaborator_corpus" / "_distillates"
    dd.mkdir(parents=True)
    (dd / "alice.json").write_text(json.dumps({
        "_key": "alice", "name": "Alice Q", "openalex_id": "A1",
        "role": "collaborator", "summary": "works with McCaul",
        "shared_themes": ["wonder-control-theme", "unmatched-topic"],
        "contribution_atoms": [
            {"name": "wonder-method-discovery", "kind": "method", "statement": "found the wonder method",
             "with_mccaul": True, "confidence": "high"},
            {"name": "speculative-link", "kind": "concept", "statement": "a weakly-indicated idea",
             "with_mccaul": False, "confidence": "low"},
        ],
    }), encoding="utf-8")
    vd = tmp_path / "collaborator_corpus" / "_voice"
    vd.mkdir(parents=True)
    (vd / "alice.json").write_text(json.dumps({
        "_key": "alice", "name": "Alice Q", "n_works": 40,
        "voice_items": [
            {"name": "paradox-first-framing", "kind": "style", "confidence": "high",
             "statement": "leads with the physical paradox then resolves it formally",
             "works": ["W1 2020", "W2 2021"]},
            {"name": "one-off-hunch", "kind": "posture", "confidence": "low",
             "statement": "a thinly-grounded one-off", "works": ["W3 2019"]},
        ],
    }), encoding="utf-8")
    return tmp_path


def test_contributions_are_g0_atoms_under_the_person(collab_repo):
    leaves = collaborator_lens.collaborator_leaves(collab_repo)
    a = "collaborator_corpus/people/alice.md::wonder-method-discovery"
    g = "collaborator_corpus/people/alice.md::speculative-link"
    assert a in leaves and leaves[a]["kind"] == "collab-method"
    assert concept_lens.atom_parent(a) == "collaborator_corpus/people/alice.md"   # routes up to the person cluster
    assert leaves[g]["conjectural"] is True and leaves[a]["conjectural"] is False  # low-confidence = grit, flagged


def test_scientific_voice_atoms_join_the_same_floor(collab_repo):
    """The voice fold (N36, from the papers): voice items materialise as g0 atoms under the SAME
    person cluster as the contributions, ``voice-`` prefixed (a person's voice and their topics
    stay distinguishable), confidence-graded with low = conjectural grit, coupled inperson::."""
    leaves = collaborator_lens.collaborator_leaves(collab_repo)
    v = "collaborator_corpus/people/alice.md::voice-paradox-first-framing"
    g = "collaborator_corpus/people/alice.md::voice-one-off-hunch"
    assert v in leaves and leaves[v]["kind"] == "voice-style"
    assert leaves[v]["essence"].startswith("voice (style):")
    assert concept_lens.atom_parent(v) == "collaborator_corpus/people/alice.md"
    assert leaves[g]["conjectural"] is True and leaves[v]["conjectural"] is False
    assert leaves[v]["works"] == ["W1 2020", "W2 2021"]          # grounded: the works ride the leaf
    ei = collaborator_lens.collaborator_edge_index(collab_repo)
    assert ei[v] == ["inperson::collaborator_corpus/people/alice.md"]


def test_cross_corpus_wire_is_faithful_and_couples(collab_repo):
    wires = collaborator_lens.cross_corpus_wires(collab_repo)
    person = "collaborator_corpus/people/alice.md"
    assert wires[person] == {"concept_corpus/themes/wonder-control-theme.md",
                             "concept_corpus/atoms/wonder-method-2020.md"}   # matched theme + co-built paper
    # 'unmatched-topic' produced no wire (faithful, not forced)
    assert not any("unmatched" in w for w in wires[person])

    ei = collaborator_lens.collaborator_edge_index(collab_repo)
    theme = "concept_corpus/themes/wonder-control-theme.md"
    # the xcorpus token is on BOTH ends (a shared referent -> real coupling, not a directed link)
    shared = set(ei[person]) & set(ei[theme])
    assert shared and all(t.startswith("xcorpus::") for t in shared)
    leaf = lambda nid: {"id": nid, "leaf": True, "members": [], "keywords": [], "coverage": []}
    nodes = {person: leaf(person), theme: leaf(theme)}
    reach = keeper_ring.build_reach(nodes, ei)
    assert keeper_ring.coupling(reach, person, theme) >= 1
