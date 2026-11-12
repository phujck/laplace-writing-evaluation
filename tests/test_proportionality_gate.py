"""C3.2 — the PRE-RENDER proportionality gate (``check_plan_proportionality``).

The post-render gate (``check_proportionality`` in the same module, covered in
``test_pipeline_coherence.py``) reads finished prose; this gate reads the PLAN and
asks whether manuscript MASS follows the author's contribution ranking. The mass
proxy is the pipeline's own planned-node count, attributed through the C3.1
``serves`` edge.

FAIL-CLOSED contract (the four cases the spec pins):
  * an over-weighted EXCLUDED contribution FLAGS,
  * a rank INVERSION FLAGS,
  * a PROPORTIONATE plan is silent,
  * a plan with NO serves declarations reports coverage UNMEASURABLE — never a
    silent false pass.
"""

from __future__ import annotations

from pathlib import Path

from laplace.pipeline import proportionality_audit as c9
from laplace.pipeline.schema import contribution_rank_id

ROOT = Path(__file__).resolve().parents[1]

# One ranked meta reused across cases: rank-1 primary, rank-2 primary, an
# exploratory-excluded rank-3. Addressable by content-id, by rank int, by rank str.
_META = {"contribution_rank": [
    {"rank": 1, "claim": "the main hardness result", "role": "primary"},
    {"rank": 2, "claim": "the estimator design", "role": "primary"},
    {"rank": 3, "claim": "a numerical side probe", "role": "exploratory-excluded"}]}

_C1 = contribution_rank_id("the main hardness result")
_C2 = contribution_rank_id("the estimator design")
_C3 = contribution_rank_id("a numerical side probe")


def _sec(sid, serves, nodes):
    return {"id": sid, "serves": serves,
            "nodes_in_order": [f"def:{sid}-{i}" for i in range(nodes)]}


def _kinds(r):
    return {f["kind"] for f in r["findings"]}


# --------------------------------------------------------------------------- #
# 1. a PROPORTIONATE plan is silent                                           #
# --------------------------------------------------------------------------- #

def test_proportionate_plan_is_silent():
    # rank-1 heaviest (5), rank-2 lighter (2), excluded served by nothing.
    plan = {"meta": _META, "sections": [
        _sec("S1", _C1, 3), _sec("S2", _C1, 2),   # rank-1 mass = 5
        _sec("S3", 2, 2)]}                          # rank-2 mass = 2 (by rank number)
    r = c9.check_plan_proportionality(plan)
    assert r["pass"] is True
    assert r["findings"] == []
    assert r["measurable"] is True
    # the coverage table is still populated for the crank to read
    assert r["coverage"][_C1]["mass"] == 5
    assert r["coverage"][_C2]["mass"] == 2
    assert r["coverage"][_C3]["mass"] == 0


# --------------------------------------------------------------------------- #
# 2. an over-weighted EXCLUDED contribution FLAGS                             #
# --------------------------------------------------------------------------- #

def test_excluded_with_nonzero_mass_flags():
    plan = {"meta": _META, "sections": [
        _sec("S1", _C1, 4),        # rank-1 still heaviest
        _sec("S2", _C2, 2),
        _sec("S3", _C3, 3)]}       # excluded contribution SERVED — the defect
    r = c9.check_plan_proportionality(plan)
    assert r["pass"] is False
    assert "proportionality" in _kinds(r)
    assert any("excluded" in f["issue"] for f in r["findings"])
    assert r["coverage"][_C3]["mass"] == 3


# --------------------------------------------------------------------------- #
# 3. a rank INVERSION FLAGS                                                   #
# --------------------------------------------------------------------------- #

def test_rank_inversion_flags():
    # rank-2 outweighs rank-1: an inversion (and rank-1 loses the plurality).
    plan = {"meta": _META, "sections": [
        _sec("S1", _C1, 1),        # rank-1 mass = 1
        _sec("S2", _C2, 5)]}       # rank-2 mass = 5  -> inversion
    r = c9.check_plan_proportionality(plan)
    assert r["pass"] is False
    assert any("inversion" in f["issue"] for f in r["findings"])


def test_rank1_not_plurality_flags_on_tie():
    # a tie at the top means rank-1 holds no plurality (no strict inversion).
    plan = {"meta": _META, "sections": [
        _sec("S1", _C1, 3),
        _sec("S2", _C2, 3)]}       # equal mass -> rank-1 has no plurality
    r = c9.check_plan_proportionality(plan)
    assert r["pass"] is False
    assert any("plurality" in f["issue"] for f in r["findings"])
    # a tie is not a strict inversion — the inversion clause must stay quiet
    assert not any("inversion" in f["issue"] for f in r["findings"])


# --------------------------------------------------------------------------- #
# 4. NO serves declarations -> coverage UNMEASURABLE (never a false pass)     #
# --------------------------------------------------------------------------- #

def test_no_serves_is_unmeasurable_not_a_false_pass():
    plan = {"meta": _META, "sections": [
        {"id": "S1", "nodes_in_order": ["def:a", "def:b"]},
        {"id": "S2", "nodes_in_order": ["def:c"]}]}
    r = c9.check_plan_proportionality(plan)
    assert r["pass"] is False                       # NOT a silent clean bill
    assert r["measurable"] is False
    assert any("UNMEASURABLE" in f["issue"] for f in r["findings"])


def test_serves_present_but_unresolvable_is_still_unmeasurable():
    # a `serves` that names nothing real (the validator FAILS it separately) must
    # not be counted as measured coverage here — no false pass through a typo.
    plan = {"meta": _META, "sections": [
        {"id": "S1", "serves": "c-nonexistent", "nodes_in_order": ["def:a"]}]}
    r = c9.check_plan_proportionality(plan)
    assert r["pass"] is False and r["measurable"] is False


# --------------------------------------------------------------------------- #
# fail-closed on NON-SCALAR serves (must report, never crash)                 #
# --------------------------------------------------------------------------- #

def test_dict_serves_is_unmeasurable_not_a_crash():
    # a dict-valued `serves` is unhashable — the gate must treat it as an
    # unresolvable ref (unmeasurable coverage), NEVER raise TypeError.
    plan = {"meta": _META, "sections": [
        {"id": "S1", "serves": {"weird": "dict"}, "nodes_in_order": ["def:a"]}]}
    r = c9.check_plan_proportionality(plan)
    assert r["measurable"] is False            # dict resolves to nothing
    assert r["pass"] is False                  # NOT a silent false pass


def test_bool_serves_never_credits_rank_one():
    # hash(True) == hash(1) and True == 1, so an unguarded ref_index.get(True)
    # returns the rank-1 id — a SILENT false pass crediting full mass to rank-1.
    # bool must be excluded before the (str, int) whitelist (int subclass).
    for serves in (True, [True], False, [False]):
        plan = {"meta": _META, "sections": [
            {"id": "S1", "serves": serves, "nodes_in_order": ["def:a", "def:b"]}]}
        r = c9.check_plan_proportionality(plan)
        assert r["measurable"] is False, serves    # bool resolves to NOTHING
        assert r["pass"] is False, serves          # never a silent clean
        assert all(row["mass"] == 0 for row in r["coverage"].values()), serves
        # ^ zero mass credited anywhere — the rank-1 silent credit is dead


def test_list_with_dict_serves_skips_the_dict_and_resolves_the_rest():
    # a list mixing a real ref with a dict must accrue mass for the real ref and
    # silently drop the non-scalar entry — no crash, no faked coverage from the dict.
    plan = {"meta": _META, "sections": [
        {"id": "S1", "serves": [_C1, {"weird": "dict"}],
         "nodes_in_order": ["def:a", "def:b"]}]}
    r = c9.check_plan_proportionality(plan)
    assert r["measurable"] is True
    assert r["coverage"][_C1]["mass"] == 2     # the real ref still measured
    # the dict contributed nothing anywhere
    assert sum(cov["mass"] for cid, cov in r["coverage"].items() if cid != _C1) == 0


def test_none_in_serves_list_is_ignored_not_a_crash():
    # a None entry in the list is filtered out; a real ref beside it still resolves.
    plan = {"meta": _META, "sections": [
        {"id": "S1", "serves": [None, _C1],
         "nodes_in_order": ["def:a", "def:b"]}]}
    r = c9.check_plan_proportionality(plan)
    assert r["coverage"][_C1]["mass"] == 2
    assert r["measurable"] is True


def test_list_with_only_dict_serves_is_unmeasurable():
    plan = {"meta": _META, "sections": [
        {"id": "S1", "serves": [{"a": 1}], "nodes_in_order": ["def:a"]}]}
    r = c9.check_plan_proportionality(plan)
    assert r["measurable"] is False and r["pass"] is False


# --------------------------------------------------------------------------- #
# additive floor + resolution idioms                                          #
# --------------------------------------------------------------------------- #

def test_absent_contribution_rank_measures_nothing():
    # no rank at all: nothing to weigh, measurability undefined (not a defect).
    r = c9.check_plan_proportionality({"sections": [{"id": "S1", "serves": 1}]})
    assert r["pass"] is True
    assert r["measurable"] is None
    assert r["findings"] == []


def test_serves_resolves_by_id_and_rank_number_and_string():
    # the same three addressing modes the C3.1 validator accepts all accrue mass.
    plan = {"meta": _META, "sections": [
        _sec("S1", _C1, 3),        # by content-id
        _sec("S2", 1, 2),          # by rank number (int) -> also rank-1
        _sec("S3", "2", 4)]}       # by rank number (str) -> rank-2
    r = c9.check_plan_proportionality(plan)
    assert r["coverage"][_C1]["mass"] == 5     # 3 + 2, both resolved to rank-1
    assert r["coverage"][_C2]["mass"] == 4
    assert sorted(r["coverage"][_C1]["sections"]) == ["S1", "S2"]


def test_beats_count_toward_mass():
    # the mass proxy is nodes_in_order + beats, matching the plan validator.
    plan = {"meta": _META, "sections": [
        {"id": "S1", "serves": _C1,
         "nodes_in_order": ["def:a"], "beats": ["res:b", "res:c"]},
        {"id": "S2", "serves": _C2, "nodes_in_order": ["def:d"]}]}
    r = c9.check_plan_proportionality(plan)
    assert r["coverage"][_C1]["mass"] == 3     # 1 node + 2 beats
    assert r["coverage"][_C2]["mass"] == 1


def test_appendices_serve_too():
    plan = {"meta": _META,
            "sections": [_sec("S1", _C1, 2)],
            "appendices": [_sec("A1", _C1, 3)]}
    r = c9.check_plan_proportionality(plan)
    assert r["coverage"][_C1]["mass"] == 5
    assert "A1" in r["coverage"][_C1]["sections"]


# --------------------------------------------------------------------------- #
# the MALFORMED-RANK side of the same door (the `serves` side is above).       #
#                                                                              #
# Why these are fail-closed and not hygiene: `check_plan_proportionality` is    #
# called from `validate_projection_plan.validate`, whose one in-pipeline caller #
# `storyboard._validate_reduced` converts `validate() raised` into              #
# `{"pass": True}`. So a TypeError raised HERE does not surface as a red — it   #
# launders the WHOLE pre-render plan validation into a silent green. Every      #
# crash below was therefore a false pass of the plan gate.                      #
# --------------------------------------------------------------------------- #

def test_unhashable_authored_rank_reports_instead_of_crashing():
    # `{"rank": []}` is unhashable; indexing the ref table on it raised TypeError
    # inside the audit. The entry keeps its content-id door and loses only its
    # rank-number one — and the audit still delivers a report.
    meta = {"contribution_rank": [
        {"rank": [], "claim": "the malformed one", "role": "primary"},
        {"rank": 2, "claim": "the well-formed one", "role": "primary"}]}
    plan = {"meta": meta, "sections": [
        {"id": "S1", "serves": 2, "nodes_in_order": ["res:a", "res:b"]}]}
    r = c9.check_plan_proportionality(plan)          # must not raise
    assert r["measurable"] is True
    # the well-formed contribution still resolves by its rank number...
    assert r["coverage"][contribution_rank_id("the well-formed one")]["mass"] == 2
    # ...and the malformed one is still ADDRESSABLE by its stable content-id
    assert contribution_rank_id("the malformed one") in r["coverage"]


def test_unhashable_rank_still_resolves_by_content_id():
    # the id is IDENTITY, the rank is a POSITION: losing the rank door must not
    # cost the contribution its content-id door.
    cid = contribution_rank_id("the malformed one")
    meta = {"contribution_rank": [
        {"rank": {"bad": 1}, "claim": "the malformed one", "role": "primary"}]}
    plan = {"meta": meta, "sections": [
        {"id": "S1", "serves": cid, "nodes_in_order": ["res:a"]}]}
    r = c9.check_plan_proportionality(plan)
    assert r["measurable"] is True
    assert r["coverage"][cid]["mass"] == 1


def test_bool_authored_rank_never_seizes_the_rank_one_key():
    # hash(True) == hash(1): a `{"rank": true}` decoy declared AFTER the real
    # rank-1 used to overwrite the rank-1 index entry and swallow `serves: 1` —
    # the real rank-1 was credited 0 and the decoy took the mass.
    meta = {"contribution_rank": [
        {"rank": 1, "claim": "the real rank one", "role": "primary"},
        {"rank": True, "claim": "the bool decoy", "role": "primary"}]}
    plan = {"meta": meta, "sections": [
        {"id": "S1", "serves": 1, "nodes_in_order": ["res:a", "res:b"]}]}
    r = c9.check_plan_proportionality(plan)
    assert r["coverage"][contribution_rank_id("the real rank one")]["mass"] == 2
    assert r["coverage"][contribution_rank_id("the bool decoy")]["mass"] == 0


def test_mixed_int_and_str_ranks_do_not_crash_the_inversion_sort():
    # sorted(..., key=rank) / min(..., key=rank) raised
    # "'<' not supported between instances of 'str' and 'int'".
    meta = {"contribution_rank": [
        {"rank": 1, "claim": "int ranked", "role": "primary"},
        {"rank": "2", "claim": "str ranked", "role": "primary"}]}
    plan = {"meta": meta, "sections": [
        {"id": "S1", "serves": contribution_rank_id("int ranked"),
         "nodes_in_order": ["res:a"]}]}
    r = c9.check_plan_proportionality(plan)          # must not raise
    assert r["measurable"] is True
    assert isinstance(r["findings"], list)


def test_non_dict_section_is_skipped_not_a_crash():
    # a malformed `sections` entry raised AttributeError on `.get`.
    plan = {"meta": _META,
            "sections": ["a bare string", _sec("S2", _C1, 2)]}
    r = c9.check_plan_proportionality(plan)          # must not raise
    assert r["coverage"][_C1]["mass"] == 2


def test_sections_as_a_bare_string_is_unmeasurable_not_a_crash():
    # plan_sections yields a str CHARACTER by character; each char has no .get.
    r = c9.check_plan_proportionality({"meta": _META, "sections": "oops"})
    assert r["measurable"] is False and r["pass"] is False


# --------------------------------------------------------------------------- #
# the mass proxy is CONTENT nodes: fig:/ref: are apparatus, not weight.        #
# --------------------------------------------------------------------------- #

def test_support_ids_do_not_manufacture_a_false_inversion():
    # `_section_mass` claimed the NON_CONTENT_PREFIXES exclusion in prose but did
    # not apply it, and APPENDICES really do carry fig: ids in nodes_in_order
    # (validate_projection_plan checks provenance on exactly that shape). Three
    # apparatus ids beside one content node outweighed a 2-node body section and
    # flagged a rank inversion that does not exist — a FALSE FLAG.
    plan = {"meta": _META,
            "sections": [_sec("S1", _C1, 2)],                       # rank-1 mass 2
            "appendices": [{"id": "A1", "serves": 2,
                            "nodes_in_order": ["fig:x", "fig:y", "ref:z", "res:c"]}]}
    r = c9.check_plan_proportionality(plan)
    assert r["coverage"][_C2]["mass"] == 1     # one CONTENT node, not four
    assert r["coverage"][_C1]["mass"] == 2
    assert r["pass"] is True                   # no inversion: 2 > 1
    assert r["findings"] == []


def test_paragraph_spec_ids_are_not_content_mass():
    # `<section>-p<N>` is prose provenance (schema.SPEC_ID_TAIL_RE), never a node.
    plan = {"meta": _META, "sections": [
        {"id": "S1", "serves": _C1, "nodes_in_order": ["res:a", "S1-p1", "S1-p2"]},
        {"id": "S2", "serves": _C2, "nodes_in_order": ["res:b"]}]}
    r = c9.check_plan_proportionality(plan)
    assert r["coverage"][_C1]["mass"] == 1
    assert r["coverage"][_C2]["mass"] == 1


def test_support_only_section_serves_but_carries_no_mass():
    # a section serving a contribution with apparatus ONLY contributes zero mass,
    # yet still counts as a serving declaration (coverage stays measurable).
    plan = {"meta": _META, "sections": [
        {"id": "S1", "serves": _C1, "nodes_in_order": ["fig:a", "ref:b"]}]}
    r = c9.check_plan_proportionality(plan)
    assert r["measurable"] is True
    assert r["coverage"][_C1]["mass"] == 0
    assert "S1" in r["coverage"][_C1]["sections"]


# --------------------------------------------------------------------------- #
# the wired call site: validate() surfaces proportionality WARN-tier          #
# --------------------------------------------------------------------------- #

def test_validate_surfaces_proportionality_without_blocking():
    """The pre-render plan validator carries the proportionality report but does
    NOT fold it into `pass` (WARN-tier) — the live SSG plan declares no serves, so
    coverage is unmeasurable yet the plan still validates."""
    import importlib.util
    vp = ROOT / "scripts" / "validate_projection_plan.py"
    spec = importlib.util.spec_from_file_location("_c32_validate", vp)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    plan_path = ROOT / "synthetics papers" / "subset-sum-itqde" / "manuscript" \
        / "projection_plan.json"
    if not plan_path.is_file():
        import pytest
        pytest.skip("subset-sum-itqde plan not on disk")
    r = mod.validate(str(plan_path), "subset-sum-itqde")
    assert "proportionality" in r
    # the live plan carries no serves -> unmeasurable, but the plan still PASSES
    # (proportionality is WARN-tier, never folded into `ok`).
    assert r["proportionality"]["measurable"] is False
    assert r["pass"] is True
