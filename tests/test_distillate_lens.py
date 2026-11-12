"""Tests for distillate_lens - the wire that makes a paper's rich layer reachable from its leaf.

Contracts: the join key normalizes away case/punctuation/separator style so a tex directory name
meets a real title; a prefix hit is the strong signal and a difflib hit the weak one; several node
ids sharing ONE normalized title are duplicate records of one work and travel together, while two
DIFFERENT titles inside the margin are ambiguous and are not applied at all; the minted referent is
one token per paper family, identical on every member (so ``keeper_ring.build_reach`` couples them);
and the edgeless-node guard holds - a member that had NO prior edge keeps its keyword reach instead
of having it REPLACED, because ``build_reach`` reads ``edge_targets or coverage``. Hermetic except
the last test, which asserts the live corpus's own join and skips when that corpus is absent.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from laplace.engine import distillate_lens as dl
from laplace.engine import keeper_ring

REPO = Path(__file__).resolve().parents[1]
PDFS_DIR = dl.PDFS_ROOT


# --- the join key ---

def test_norm_erases_case_punctuation_and_separator_style():
    assert dl._norm("Super-sensing: 100-Fold enhancement in THz time-domain") == \
        "super-sensing-100-fold-enhancement-in-thz-time-domain"
    assert dl._norm("Free to harmonic unitary transformations") == \
        dl._norm("Free to Harmonic Unitary Transformations")


def test_score_prefix_is_the_strong_signal_and_the_tail_is_never_penalised():
    key = "super-sensing-100-fold-enhancement-in-thz-time-domain"
    long_title = key + "-spectroscopy-contrast-via-superoscillating-waveform-shaping"
    assert dl._score(key, long_title) == 1.0            # the directory name is a truncated slug
    # a near-miss spelling still scores high, but it is not a prefix
    near = "entropy-nonconservation-and-boundary-conditions-for-hamiltonian-systems"
    assert 0.9 <= dl._score("entropy-non-conservation-and-boundary-conditions-for", near) < 1.0


# --- picking, and what "ambiguous" means ---

def test_pick_returns_every_id_sharing_the_winning_title():
    key = "wave-operator-representation"
    ids, conf, why = dl._pick(key, {"a//W1": "wave-operator-representation-of-quantum-dynamics",
                                    "b//W2": "wave-operator-representation-of-quantum-dynamics"})
    assert ids == ["a//W1", "b//W2"]        # duplicate OpenAlex records of ONE work
    assert (conf, why) == (1.0, "prefix")


def test_pick_refuses_two_different_titles_inside_the_margin():
    key = "driving-spin-boson-models"
    ids, _conf, why = dl._pick(key, {"a": "driving-spin-boson-models-from-equilibrium",
                                     "b": "driving-spin-boson-models-from-eqnilibrium"})
    assert ids == []                        # nothing is applied on a guess
    assert why.startswith("ambiguous-with:")


def test_pick_refuses_everything_below_the_floor():
    ids, _conf, why = dl._pick("non-uniqueness-of-driving-fields", {"a": "a-totally-different-paper"})
    assert (ids, why) == ([], "below-floor")


# --- the wire ---

def _table(members):
    return {"matched": {"paper-x": {"paper_id": "paper-x", **members}}}


def test_every_member_is_minted_the_same_family_token():
    idx = dl.distillate_edge_index(REPO, table=_table({
        "tex": ["published_corpus/tex/paper-x/main.tex"],
        "stores": ["corpus_stores/spine_chain/paper-x.jsonl"],
        "atoms": ["concept_corpus/atoms/px.md::an-atom"]}))
    token = f"{dl.DISTILLATE_PREFIX}paper-x"
    assert all(token in v for v in idx.values())
    assert set(idx) == {"published_corpus/tex/paper-x/main.tex",
                        "corpus_stores/spine_chain/paper-x.jsonl",
                        "concept_corpus/atoms/px.md::an-atom"}


def test_the_family_token_couples_the_leaf_to_its_distillate_through_build_reach():
    nodes = {
        "root": {"leaf": False, "members": ["tex", "atom", "other"], "coverage": []},
        "tex": {"leaf": True, "members": [], "coverage": ["published", "tex"]},
        "atom": {"leaf": True, "members": [], "coverage": ["harmonic"]},
        "other": {"leaf": True, "members": [], "coverage": ["unrelated"]},
    }
    idx = dl.distillate_edge_index(REPO, table={"matched": {"paper-x": {
        "paper_id": "paper-x", "tex": ["tex"], "atoms": ["atom"]}}})
    reach = keeper_ring.build_reach(nodes, idx)
    assert keeper_ring.coupling(reach, "tex", "atom") == 1      # the wire, and only the wire
    assert keeper_ring.coupling(reach, "tex", "other") == 0


def test_edgeless_member_keeps_its_coverage_reach_instead_of_losing_it():
    """build_reach reads ``edge_targets OR coverage`` - so a first edge on a previously edgeless
    node would REPLACE its keyword reach. The guard re-emits the node's own coverage, which is
    what build_reach would have fallen back to, so the wire is strictly additive."""
    table = _table({"stores": ["corpus_stores/spine_chain/paper-x.jsonl"],
                    "tex": ["published_corpus/tex/paper-x/main.tex"]})
    nodes = {"corpus_stores/spine_chain/paper-x.jsonl": {"coverage": ["spine", "chain"]},
             "published_corpus/tex/paper-x/main.tex": {"coverage": ["tex", "words"]}}
    base = {"published_corpus/tex/paper-x/main.tex": ["someCiteKey"]}   # this one already has edges
    idx = dl.distillate_edge_index(REPO, base=base, nodes=nodes, table=table)
    assert idx["corpus_stores/spine_chain/paper-x.jsonl"] == \
        [f"{dl.DISTILLATE_PREFIX}paper-x", "spine", "chain"]
    # the node that already had substrate gains the token ONLY - never its bag of words back
    assert idx["published_corpus/tex/paper-x/main.tex"] == [f"{dl.DISTILLATE_PREFIX}paper-x"]


def test_the_guarded_wire_never_shrinks_a_members_reach():
    """The end-to-end form of the guard, through build_reach itself."""
    nodes = {"root": {"leaf": False, "members": ["store", "atom"], "coverage": []},
             "store": {"leaf": True, "members": [], "coverage": ["spine", "chain"]},
             "atom": {"leaf": True, "members": [], "coverage": ["harmonic"]}}
    table = {"matched": {"paper-x": {"paper_id": "paper-x", "stores": ["store"], "atoms": ["atom"]}}}
    base = {"store": [], "atom": []}
    idx = dl.distillate_edge_index(REPO, base=base, nodes=nodes, table=table)
    before = keeper_ring.build_reach(nodes, {})
    after = keeper_ring.build_reach(nodes, idx)
    assert before["store"] <= after["store"] and before["atom"] <= after["atom"]
    assert keeper_ring.coupling(after, "store", "atom") == 1


def test_the_guard_drops_the_path_words_that_would_bury_the_family():
    """Residual (b) of the blind-surfacing re-run: the guard preserved reach and cost RANK - a
    wired node came back with a reach of path words, so every atom scored ``1/|reach|`` and any
    node sharing two path words outranked the family. The guard now re-emits the DISTINCTIVE
    coverage only, which is exactly the class its own measurement said was carrying real edges."""
    common = [f"n{i}" for i in range(2000)]                    # 2000 nodes all carrying "pdf"
    nodes = {n: {"coverage": ["pdf", n]} for n in common}
    nodes["life"] = {"coverage": ["pdf", "corpus", "twinning"]}
    table = _table({"life": ["life"]})
    idx = dl.distillate_edge_index(REPO, base={"life": []}, nodes=nodes, table=table)
    assert idx["life"] == [f"{dl.DISTILLATE_PREFIX}paper-x", "corpus", "twinning"]
    assert "pdf" not in idx["life"]                            # 2000/2001 nodes: location, not content


def test_the_guard_keeps_a_keyword_no_other_node_carries():
    nodes = {"store": {"coverage": ["spine", "chain"]}, "other": {"coverage": ["unrelated"]}}
    idx = dl.distillate_edge_index(REPO, base={"store": []}, nodes=nodes,
                                   table=_table({"stores": ["store"]}))
    assert idx["store"] == [f"{dl.DISTILLATE_PREFIX}paper-x", "spine", "chain"]


# --- the published-artefact legs (residual (a): where descent actually lands) ---

def test_a_truncated_file_title_still_joins_its_paper():
    """A file name carries a title cut to fit the filename, so the CANDIDATE is the shorter side -
    the one-sided ``candidate.startswith(key)`` test misses every such paper."""
    key = "sequential-optical-response-suppression-for-chemical-selectivity"
    cand = {"published_corpus/pdfs/Magann et al. - 2022 - Sequential optical response suppression "
            "for chemic.pdf": "sequential-optical-response-suppression-for-chemic"}
    assert dl._pick(key, cand) == ([], 0.0, "below-floor")          # the old, one-sided test
    ids, conf, why = dl._pick(key, cand, tolerant=True)
    assert ids == list(cand) and (conf, why) == (1.0, "prefix")


def test_a_short_overlap_is_a_coincidence_not_a_title():
    ids, _conf, why = dl._pick("free-snacks-in-quantum-complexity",
                               {"a": "free-snacks"}, tolerant=True)
    assert ids == [] and why == "below-floor"


def test_the_file_title_is_the_third_field_of_the_house_naming_convention():
    assert dl._file_title("McCaul et al. - 2017 - Partition-free approach to open quantum sy.pdf") \
        == "partition-free-approach-to-open-quantum-sy"
    # a name that does not carry the three fields yields its bare stem, which joins nothing
    assert dl._file_title("waveop2023.txt") == "waveop2023"


# --- the live corpus (the thing the blind surfacing test measured) ---

@pytest.mark.skipif(not (REPO / "published_corpus" / "tex").is_dir(),
                    reason="no published corpus in this checkout")
def test_the_live_join_reaches_the_two_blind_test_papers():
    table = dl.paper_families(REPO)
    # an ambiguous LEG is held for the operator, and never leaks into what gets wired
    for row in table["ambiguous"]:
        fam = table["matched"].get(row["paper_id"], {})
        assert not fam.get(row["leg"]), f"{row['paper_id']}/{row['leg']} was applied on a guess"
    ss = table["matched"]["super-sensing-100-fold-enhancement-in-thz-time-domain"]
    assert ss["atoms"], "the concept-atom leg is the arcana grain the blind agents grepped for"
    assert ss["collaborator"], "the OpenAlex program-paper handle must join by title"
    nu = table["matched"]["non-uniqueness-of-driving-fields-generating-non-linear"]
    walks = [s for s in nu["stores"] if "derivation_walk" in s or "spine_chain" in s]
    assert len(walks) == 2, "the stores the WO names as unreachable must be in the family"


@pytest.mark.skipif(not (REPO / "corpus_stores").is_dir(),
                    reason="no stage stores in this checkout")
def test_a_paper_whose_tex_lives_elsewhere_still_gets_a_family():
    """The family set is tex dirs UNION store paper_ids: a paper with stage-store rows but no
    published_corpus/tex/<id>/ directory joins on its tex-manifest title, not its bare id."""
    table = dl.paper_families(REPO)
    assert table["counts"]["store_only_papers"] > 0
    fam = table["matched"]["optical-indistinguishability-twinning"]
    assert not fam["tex"] and fam["stores"] and fam["atoms"]


@pytest.mark.skipif(not (REPO / PDFS_DIR).is_dir(), reason="no published pdfs in this checkout")
def test_the_papers_descent_lands_on_are_in_the_family():
    """The six papers whose descent landed on their own pdf/abstract and stranded 98 atoms
    (evidence/BLIND_SURFACING_RERUN_2026-08-20/ s4). Each must now reach that hit through the wire."""
    table = dl.paper_families(REPO)
    for pid in ("decoherence-free-entropic-gravity-model-and-experimental",
                "entropy-non-conservation-and-boundary-conditions-for",
                "single-atom-computing-hhg",
                "partition-free-approach-to-open-quantum-systems-in-harmonic",
                "diffusion-fails-to-make-a-stink",
                "dynamical-generation-of-epsilon-near-zero-behaviour-via"):
        fam = table["matched"][pid]
        assert fam.get("pdf"), f"{pid}: no published pdf leg"
        assert fam.get("archive"), f"{pid}: no archived pdf/abstract leg"
        assert fam.get("atoms"), f"{pid}: nothing for the wire to carry"
        members = dl.family_members(fam)
        assert set(fam["pdf"]) <= set(members) and set(fam["archive"]) <= set(members)


@pytest.mark.skipif(not (REPO / PDFS_DIR).is_dir(), reason="no published pdfs in this checkout")
def test_no_published_file_is_claimed_by_two_families():
    table = dl.paper_families(REPO)
    owner: dict[str, str] = {}
    for pid, fam in table["matched"].items():
        for nid in (fam.get("pdf") or []) + (fam.get("archive") or []):
            assert nid not in owner, f"{nid} claimed by {owner.get(nid)} and {pid}"
            owner[nid] = pid


@pytest.mark.skipif(not (REPO / PDFS_DIR).is_dir(), reason="no published pdfs in this checkout")
def test_the_repaired_pdf_names_carry_their_papers_title():
    """WO-20260820-published-pdf-name-repair. Two of the three named cases must join at the
    STRONG signal (prefix, 1.0) - the repair is in the NAME, never in a loosened join:

    * ``low-rank-approximation`` - its published pdf was named by the subtitle ("Fast computation
      of dissipative quantum systems wi") while the manifest title is "Beating the House: Fast
      Computation of ..."; the file now carries the manifest title, truncated to the house
      convention, so the truncation-tolerant prefix test lands it.
    * ``non-uniqueness-...`` - its pdf name carries a literal ``#U2010`` where a U+2010 hyphen
      belongs. No rename: ``_norm`` decodes the escape, so the mojibake name already joins at 1.0
      and a rename would only orphan the node id the embedding stores hold.

    The third case (``polaron-imposters``) is NOT a name defect: no published artefact for it
    exists under either file-leg root, so it has no pdf leg to repair. Asserted here so the
    absence stays measured instead of being re-diagnosed as a join bug.
    """
    table = dl.paper_families(REPO)
    for pid in ("low-rank-approximation",
                "non-uniqueness-of-driving-fields-generating-non-linear"):
        fam = table["matched"][pid]
        assert fam.get("pdf"), f"{pid}: no published pdf leg"
        assert fam["confidence"]["pdf"] == {"score": 1.0, "why": "prefix"}, \
            f"{pid}: the pdf leg must land on the strong signal, not a fuzzy guess"
        assert set(fam["pdf"]) <= set(dl.family_members(fam))
    assert not table["matched"]["polaron-imposters"].get("pdf"), \
        "polaron-imposters has no published artefact on disk - a missing file, not a bad name"
    assert table["counts"]["with_pdf"] == 24
