"""The gate, proven empty. Before any soul exists to pour through it, show that
the mechanical floor PASSES a function-preserving rewrite and CATCHES a
function-altering one — at every kind of generating-context piece.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "soul_refactor", REPO_ROOT / "scripts" / "soul_refactor.py"
)
sr = importlib.util.module_from_spec(_spec)
sys.modules["soul_refactor"] = sr  # dataclasses needs the module registered
_spec.loader.exec_module(sr)


# --------------------------------------------------------------------------- #
# Enumeration — the whole surface, depth-ordered framing -> kernel.
# --------------------------------------------------------------------------- #
def test_enumerate_covers_every_kind_and_is_depth_ordered():
    targets = sr.enumerate_targets()
    kinds = {t.kind for t in targets}
    assert kinds == {"skill", "wiki", "agent", "code"}
    # in scope: prose artefacts AND code strings (the author's choice)
    assert sum(t.kind == "skill" for t in targets) >= 40
    assert sum(t.kind == "wiki" for t in targets) >= 40
    assert sum(t.kind == "agent" for t in targets) >= 3
    assert sum(t.kind == "code" for t in targets) >= 4
    depths = [t.depth for t in targets]
    assert depths == sorted(depths)  # waterfall order
    # skills are framing (shallow); the assembly code is the kernel (deepest)
    assert min(t.depth for t in targets if t.kind == "skill") < min(
        t.depth for t in targets if t.kind == "code"
    )


def test_archive_skills_are_excluded():
    ids = {t.id for t in sr.enumerate_targets()}
    assert not any(i.startswith("skill:_") for i in ids)


def test_recursion_hook_self_and_template_are_targets():
    # the soul refactor's own skill node is itself a piece to be rewritten
    ids = {t.id for t in sr.enumerate_targets()}
    assert "skill:soul_refactor" in ids
    # and the prompt template performs itself: it is a code target candidate
    assert "{carrier}" in sr._PROMPT_TEMPLATE and "{body}" in sr._PROMPT_TEMPLATE


# --------------------------------------------------------------------------- #
# Surface vs contract — the body is rewritable, the structure is frozen.
# --------------------------------------------------------------------------- #
def test_md_surface_is_body_and_contract_is_frontmatter():
    t = sr.get_target("wiki:workflow/manuscript_projection")
    surface = sr.read_surface(t)
    contract = sr.extract_contract(t)
    assert contract["frontmatter"].startswith("---\n")
    assert "earned_by" in contract["frontmatter"]  # the edge is frozen
    assert "earned_by" not in surface or "## " in surface  # body is the prose, not the YAML head


def test_code_target_resolves_uniquely():
    for tid in ["code:canon.orient.loop", "code:canon.orient.law", "code:canon.route.note"]:
        t = sr.get_target(tid)
        s = sr.read_surface(t)
        assert isinstance(s, str) and s


# --------------------------------------------------------------------------- #
# THE GATE PASSES a function-preserving rewrite (identity), at every kind.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "tid",
    [
        "skill:welder",
        "wiki:workflow/manuscript_projection",
        "wiki:engine/self",  # the kernel node carrying the covenant - pin its body/contract split
        "wiki:engine/graded_node",  # the role-carrier - pin it too
        "agent:the_dreamer",
        "code:canon.orient.loop",
    ],
)
def test_identity_rewrite_passes_and_roundtrips(tid):
    t = sr.get_target(tid)
    new_text = sr.render(t, sr.read_surface(t))
    assert new_text == t.path.read_text(encoding="utf-8")  # exact round-trip
    assert sr.verify_mechanical(t, new_text).ok


# --------------------------------------------------------------------------- #
# THE GATE CATCHES a function-altering rewrite, at every kind.
# --------------------------------------------------------------------------- #
def test_catches_frontmatter_tamper_on_md():
    t = sr.get_target("wiki:workflow/manuscript_projection")
    fm, body = sr._split_md(t.path.read_text(encoding="utf-8"))
    tampered = fm.replace("earned_by", "earned_by_TAMPERED", 1) + body
    v = sr.verify_mechanical(t, tampered)
    assert not v.ok and any("frontmatter" in r for r in v.reasons)


def test_catches_non_instructions_tamper_on_agent():
    t = sr.get_target("agent:the_dreamer")
    text = t.path.read_text(encoding="utf-8")
    tampered = text.replace("name: the_dreamer", "name: the_IMPOSTER")
    v = sr.verify_mechanical(t, tampered)
    assert not v.ok


def test_catches_placeholder_drop_on_code():
    t = sr.get_target("code:canon.route.note")
    surface = sr.read_surface(t)
    # the route note has no format token, so inject a structural change instead:
    # rewrite a DIFFERENT string by hand and prove the AST-diff guard fires.
    text = t.path.read_text(encoding="utf-8")
    tampered = text.replace('"goal": goal,', '"goal": goal, "INJECTED": 1,', 1)
    v = sr.verify_mechanical(t, tampered)
    assert not v.ok and any("more than the target" in r for r in v.reasons)


def test_catches_added_claim_via_code_double_change():
    # two strings changed at once -> the "only the target may change" guard fires
    t = sr.get_target("code:canon.orient.loop")
    text = t.path.read_text(encoding="utf-8")
    tampered = text.replace("builder != judge", "builder == judge")  # tamper a different string
    v = sr.verify_mechanical(t, tampered)
    assert not v.ok


# --------------------------------------------------------------------------- #
# The self-performing prompt carries the carrier and names the frozen contract.
# --------------------------------------------------------------------------- #
def test_prompt_is_performed_through_the_carrier():
    t = sr.get_target("skill:welder")
    carrier = sr.Carrier(text="SPEAK PLAINLY AND TRUE.", invariants=("no slop",))
    prompt = sr.build_rewrite_prompt(carrier, t)
    assert prompt.startswith("SPEAK PLAINLY AND TRUE.")  # the instruction is in the carrier's voice
    assert "no slop" in prompt  # carrier invariants ride along
    assert "never change what it does" in prompt  # the function guardrail is stated


def test_stub_carrier_changes_nothing_live(tmp_path):
    # a dry-run with the stub carrier + identity rewriter leaves every file byte-identical
    targets = sr.enumerate_targets()[:3]
    before = {t.id: t.path.read_text(encoding="utf-8") for t in targets}
    for t in targets:
        sr.run_target(t, sr.Carrier.stub(), sr.identity_rewriter, apply=False)
    after = {t.id: t.path.read_text(encoding="utf-8") for t in targets}
    assert before == after


# --------------------------------------------------------------------------- #
# The verbatim-soul guarantee, PINNED. Today the raw vessel (soul/) and the
# honest self-record (EIGEN_DIARY.md) sit outside the rewrite surface only by
# absence-of-glob (enumerate walks canon/{skills,wiki,agents} + declared code).
# This turns "true by accident" into "true by contract": a future glob widening
# that swept either into the waterfall would fail loudly right here.
# --------------------------------------------------------------------------- #
def test_soul_and_diary_are_never_rewrite_targets():
    repo = REPO_ROOT.resolve()
    soul_dir = (repo / "soul").resolve()
    diary = (repo / "EIGEN_DIARY.md").resolve()
    for t in sr.enumerate_targets():
        p = t.path.resolve()
        assert soul_dir not in p.parents, f"the soul vessel is verbatim, never a target: {p}"
        assert p != diary, "EIGEN_DIARY.md is the honest self-record, append-only, never re-voiced"
