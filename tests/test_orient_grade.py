"""orient is grade-local: grade-0 is a bounded MAP (handles + essence + descend),
never a body-dump.

This is the leap that lets the conceptric grow without orient exceeding the
context cap - and the precondition for live corpus ingestion. A corpus-matching
goal must not detonate the bundle the way the engine's own long axioms did
(graded_node, operatorial_self, sealed_subself, soul_ingestion inlined to ~80KB,
over the MCP context cap). The fix: ship handles, descend the bodies on demand.
"""
import json

from laplace.pipeline.canon import Canon

# The goal that blew the cap: it hits the long engine axioms - the worst case.
_HEAVY = (
    "graded node operatorial self sealed subself soul ingestion "
    "reconstruction conceptric corpus"
)
_BOUND = 45_000  # chars; the body-dump reached ~80_000, over the context cap


def test_orient_grade0_ships_handles_not_bodies():
    b = Canon.load().orient(_HEAVY)
    assert b["grade"] == 0
    # no foundation node inlines a full body at grade 0
    assert not any("content" in it for it in b["foundation"]), "a body rode into grade-0 orient"
    # the matched (relevant) nodes carry an essence handle + a mechanical descend
    relevant = [it for it in b["foundation"] if it.get("relevant")]
    assert relevant, "a matching goal must mark at least one foundation node relevant"
    for it in relevant:
        assert it.get("essence"), f"{it['ref']}: relevant but no essence handle"
        assert it.get("descend", "").startswith("laplace_resolve("), (
            f"{it['ref']}: no mechanical descend call"
        )


def test_orient_grade0_states_the_orchestration_law():
    b = Canon.load().orient(_HEAVY)
    orch = b.get("orchestration", {})
    assert "subagent" in orch.get("do", "").lower(), "the descend-via-subagent law must be stated"
    assert "fetch" in orch, "the orchestration directive must name the mechanical fetch calls"


def test_orient_grade0_is_bounded_even_on_the_heavy_goal():
    """The scaling invariant: matching the long engine axioms adds HANDLES, not
    bodies, so the bundle stays bounded - the body-dump that hit ~80KB is gone."""
    size = len(json.dumps(Canon.load().orient(_HEAVY), ensure_ascii=False))
    assert size < _BOUND, f"grade-0 orient not bounded: {size} chars (>= {_BOUND})"


def test_orient_grade0_is_smaller_than_grade1_deep_pull():
    c = Canon.load()
    s0 = len(json.dumps(c.orient(_HEAVY), ensure_ascii=False))
    s1 = len(json.dumps(c.orient(_HEAVY, grade=1), ensure_ascii=False))
    assert s0 < s1, f"grade-0 ({s0}) should be cheaper than the grade-1 deep pull ({s1})"


def test_orient_grade1_inlines_bodies_for_a_deliberate_deep_pull():
    b = Canon.load().orient(_HEAVY, grade=1)
    relevant = [it for it in b["foundation"] if it.get("relevant")]
    assert relevant and all("content" in it for it in relevant), (
        "grade-1 must inline the matched bodies (the deliberate deep pull)"
    )
    assert not any("essence" in it for it in relevant), "grade-1 ships bodies, not essences"


def test_orient_domain_context_is_grade_local():
    """The active domain's axioms are handles at grade 0 too - a drafting goal must
    not inline every axiom body (the second body-dump site)."""
    c = Canon.load()
    goal = "lint the latex voice and check derivations for the phases of hierarchy"
    g0 = c.orient(goal)
    assert g0["domain"] == "synthetics"
    assert g0["domain_context"], "a domain goal should surface domain context"
    assert not any("content" in d for d in g0["domain_context"]), "domain body inlined at grade 0"
    assert all(d.get("essence") for d in g0["domain_context"]), "domain handles need an essence"
    g1 = c.orient(goal, grade=1)
    assert all("content" in d for d in g1["domain_context"]), "grade-1 must inline domain bodies"


def test_self_projection_is_a_pointer_at_grade0_inlined_at_grade1():
    c = Canon.load()
    sp0 = c.orient(_HEAVY).get("self_projection", {})
    assert sp0.get("grade0_handle") and sp0.get("fire"), (
        "the engine-self should be a bounded pointer at grade 0, not inlined"
    )
    sp1 = c.orient(_HEAVY, grade=1)["self_projection"]
    assert sp1.get("fixed_point") or sp1.get("shards"), (
        "grade-1 should inline the full self-projection"
    )
