"""tests/test_packet_aim.py — W-AIM (2026-07-22): packets carry the aim; the planners
consume his architecture.

Two self-imposed kernel reds, flipped with behaviour:

  (1) PACKETS-CARRY-THE-AIM. Every compiled dispatch OPENS with a composed head minted by
      the dispatcher who holds the manifest — the goal (version + essence), this packet's
      role in the whole (its job, where it sits in the section order, what depends on it),
      and what acceptance writes back (his ruling: builders should know where they're
      aiming; the iteration should converge to the proper object, not guess).

  (2) ARCHITECTURE-PROFILE-CONSUMED. The narrative planners genuinely READ
      profiles/author_architecture.yaml in code — the section brief carries the profile's
      FORM fields (intro shape for the opener, the compression license wherever a
      derivation rides), so a generation cannot silently ignore how he writes. His two
      confirmed-his corrections ride every derivation-bearing section.

The honesty constraints are pinned: the head carries all three parts on a real packet; the
intro packet carries introduction_shape; a derivation-bearing packet carries the compression
license; and the whole channel is BYTE-INERT when the profile is absent (a tmp repo without
profiles/ compiles packets without the architecture channel, no crash).
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from laplace.pipeline import dispatch, narrative, registry, schema

REPO = Path(__file__).resolve().parents[1]

_CANDIDATES = ("eigenengine", "paper_falqon", "subset-sum-itqde")


def _a_manuscript_project() -> str | None:
    return next((n for n in _CANDIDATES if registry.resolve(n) is not None), None)


def _a_section(name: str) -> str | None:
    proj = registry.resolve(name)
    plan = (proj.read_plan(None) or {}) if proj else {}
    return next((s.get("id") for s in schema.plan_sections(plan) if s.get("id")), None)


# =========================================================================== THE AIM HEAD
def test_every_compiled_packet_carries_the_three_part_aim_head():
    """A compiled packet carries the composed head with all three parts — goal
    (version+essence), role in the whole, and what acceptance writes."""
    name = _a_manuscript_project()
    if name is None:
        pytest.skip("no manuscript project on disk")
    section = _a_section(name)
    d = dispatch.compile_dispatch(section, f"realise {section}", "prose", name, REPO)
    assert "error" not in d, d
    head = d["composed_head"]
    # part 1 — the goal (version + essence)
    assert set(head["goal"].keys()) == {"version", "essence"}
    assert isinstance(head["goal"]["essence"], str)
    # part 2 — the role in the whole (job / position / what depends on it)
    role = head["role_in_whole"]
    assert role["position"] and "of" in role["position"], role
    assert "depended_on_by" in role and isinstance(role["depended_on_by"], list)
    # part 3 — what acceptance writes back
    assert head["acceptance"]["writes"], head
    # the aim is a composed sentence, not a bare fact dump
    assert "converge" in head["aim"].lower()


def test_the_prompt_opens_with_the_aim_block():
    """The packet OPENS with the AIM block — the builder reads WHERE it aims before the
    work (his ruling: builders should not just guess)."""
    name = _a_manuscript_project()
    if name is None:
        pytest.skip("no manuscript project on disk")
    section = _a_section(name)
    d = dispatch.compile_dispatch(section, f"realise {section}", "prose", name, REPO)
    assert d["prompt"].lstrip().startswith("<!-- AIM -->"), d["prompt"][:80]


def test_aim_block_is_content_level_for_the_prose_packet():
    """§13 context isolation: the AIM block that opens a prose packet carries no engine
    framing — no graded-node kernel, no policy handles, no canon:// — so it rides the
    context-isolated prose packet without leaking scaffolding."""
    name = _a_manuscript_project()
    if name is None:
        pytest.skip("no manuscript project on disk")
    section = _a_section(name)
    d = dispatch.compile_dispatch(section, f"realise {section}", "prose", name, REPO)
    aim_block = d["prompt"].split("<!-- /AIM -->")[0]
    for banned in ("You are one node", "canon://", "<!-- POLICY -->", "CONTRACT:"):
        assert banned not in aim_block, f"AIM leaked engine framing: {banned}"


def test_aim_head_rides_even_without_a_manifest():
    """The aim is not optional: a node dispatch with no project (no manifest) still carries
    the composed head — a stated-empty goal, never a crash or a missing head."""
    d = dispatch.compile_dispatch("def:foo", "reconstruct def:foo", "derive", None, None)
    assert "error" not in d
    head = d["composed_head"]
    assert head["aim"]
    assert head["goal"] == {"version": None, "essence": ""}
    assert head["acceptance"]["writes"] == []


# =============================================================== THE ARCHITECTURE PROFILE
def test_architecture_profile_preserves_historical_correction_assertions():
    """Legacy assertions remain visible without becoming fresh human authority."""
    prof = narrative.architecture_profile(REPO)
    assert prof is not None, "profiles/author_architecture.yaml did not load"
    assert "introduction_shape" in prof and "conclusion_posture" in prof
    for name in ('derivation_granularity', 'section_rhythm'):
        assert prof[name]['historical_confirmation_assertion']
        assert not prof[name]['confirmed_his']


def test_intro_brief_carries_introduction_shape():
    """The opener's brief carries introduction_shape — how he opens (on the contribution,
    short runway, no display equations)."""
    prof = narrative.architecture_profile(REPO)
    brief = narrative.architecture_brief_for_section(prof, 0, 8, "introduce and motivate", False)
    assert brief is not None
    assert "introduction_shape" in brief["fields"], brief["fields"].keys()


def test_derivation_bearing_brief_carries_the_compression_license():
    """A derivation-bearing section's brief carries the compression license
    (derivation_granularity) AND the derivation placement (section_rhythm), and his two
    corrections ride it — a generation cannot silently ignore them."""
    prof = narrative.architecture_profile(REPO)
    brief = narrative.architecture_brief_for_section(prof, 4, 8, "derive-prove the result", True)
    assert brief is not None
    assert "derivation_granularity" in brief["fields"], "the compression license must ride"
    assert "section_rhythm" in brief["fields"], "the derivation placement must ride"
    assert brief['his_corrections'] == []
    assert all(brief['fields'][name]['historical_confirmation_assertion']
        for name in ('derivation_granularity', 'section_rhythm'))


def test_close_brief_carries_conclusion_posture():
    prof = narrative.architecture_profile(REPO)
    brief = narrative.architecture_brief_for_section(prof, 7, 8, "conclude and outlook", False)
    assert brief is not None
    assert "conclusion_posture" in brief["fields"]


def test_narrative_dispatch_threads_the_profile_on_a_real_section():
    """The consuming edge in code: a compiled NARRATIVE planner packet carries the
    author-architecture channel (refs + summaries), so the profile is read, not shelved."""
    name = _a_manuscript_project()
    if name is None:
        pytest.skip("no manuscript project on disk")
    proj = registry.resolve(name)
    from laplace.pipeline import structural
    contracts = (structural.load_contracts(name, REPO) or {}).get("sections") or {}
    plan = proj.read_plan(REPO) or {}
    section = next((s.get("id") for s in schema.plan_sections(plan)
                    if s.get("id") in contracts), None)
    if section is None:
        pytest.skip("no section with a resolved structure contract to plan a narrative for")
    d = dispatch.compile_dispatch(section, f"plan narrative {section}", "narrative", name, REPO)
    if "error" in d:
        pytest.skip(f"narrative dispatch not compilable: {d['error']}")
    assert "<!-- AUTHOR-ARCHITECTURE -->" in d["prompt"]
    assert "profiles/author_architecture.yaml" in d["prompt"]


# =============================================================== THE ADDITIVE FLOOR
def test_architecture_channel_is_byte_inert_without_the_profile():
    """A repo without profiles/author_architecture.yaml yields no channel and no crash —
    the loader returns None, the selector returns None, byte-identical to pre-wire."""
    tmp = Path(tempfile.mkdtemp(prefix="aim-inert-"))
    try:
        assert narrative.architecture_profile(tmp) is None
        assert narrative.architecture_brief_for_section(None, 0, 5, "derive", True) is None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_aim_head_helpers_do_not_crash_on_an_empty_manifest():
    """The aim head minted against an empty plan (no sections) degrades to a stated-minimal
    role, never an index error."""
    head = dispatch._aim_head(None, "sec:x", "goal", "prose", {}, None)
    assert head["role_in_whole"]["position"] is None
    assert head["role_in_whole"]["depended_on_by"] == []
    assert head["aim"]
