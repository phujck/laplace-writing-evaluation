"""The staged manuscript pipeline (2026-07-09 rebuild) — per-stage machinery.

Pure-function tests plus live-project integration checks against
subset-sum-itqde (whose staged artifacts are committed). The prose stage's
context-isolation law is load-bearing: these tests pin it mechanically.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from laplace.pipeline import verify
from laplace.pipeline import (contracts_verify, dispatch, document_model,
                              narrative, projection_spec, registry, schema,
                              structural, tex_backend)

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "subset-sum-itqde"


# ---------------------------------------------------------------------------
# schema: the staged vocabulary is closed and mutually consistent
# ---------------------------------------------------------------------------

def test_every_feedback_kind_routes_to_a_registered_worker():
    for kind, work in schema.KIND_TO_WORK.items():
        if work is None:
            continue
        assert work in schema.WORK_KINDS, (kind, work)
        assert work in schema.WORK_TO_LAYER, (kind, work)


def test_plan_meta_typed_carries_no_voice_channel():
    assert "voice_refs" not in schema.PLAN_META_TYPED
    assert "voice" not in schema.PLAN_META_TYPED


def test_voice_failure_lexicon_has_the_mandate_classes():
    for cls in ("self-adjudication", "narrator-visible", "opposition-flourish",
                "apparatus-exposed", "surface-invariant"):
        assert schema.VOICE_FAILURE_PATTERNS.get(cls), cls


def test_policy_handles_carry_no_voice_nodes():
    assert not any("voice" in h or "manuscript_voice" in h
                   for h in schema.POLICY_HANDLES), schema.POLICY_HANDLES


# ---------------------------------------------------------------------------
# the voice detector (§11.5): classes fire; carve-outs hold
# ---------------------------------------------------------------------------

def test_detector_flags_narrator_and_surface_invariants():
    r = verify.check_voice("The paper now turns to the estimator; a claim.\n")
    kinds = {f["kind"] for f in r["violations"]}
    assert "narrator-visible" in kinds
    assert "surface-invariant" in kinds
    assert not r["pass"]


def test_detector_spares_tikz_and_math_syntax():
    text = "\n".join([
        r"\draw (0,0) -- (1,1);",
        r"rows 3--5 of the table span \(x\) values",
        r"$a \; b$ spacing stays legal",
    ])
    r = verify.check_voice(text)
    assert not [f for f in r["violations"] if f["kind"] == "surface-invariant"], r


def test_detector_spares_math_semicolon_but_not_prose():
    # 2026-07-09 fix: the surface-invariant `;` detector must exempt math mode
    # (it was mutilating `$(a_1\dots a_n; T)$` -> `$(a_1\dots a_n)$`), while a
    # genuine prose semicolon still flags.
    math = verify.check_voice(r"The tuple $(a_1\dots a_n; T)$ fixes the instance.")
    assert not [f for f in math["violations"] if f["kind"] == "surface-invariant"], math
    disp = verify.check_voice("\\begin{equation}\n f(x; y) = x - y\n\\end{equation}")
    assert not [f for f in disp["violations"] if f["kind"] == "surface-invariant"], disp
    prose = verify.check_voice("This reads clearly; the semicolon here is prose.")
    assert [f for f in prose["violations"] if f["kind"] == "surface-invariant"], prose


def test_detector_carries_no_register_blacklist():
    # the retired lint classes must be gone root-and-branch
    r = verify.check_voice("We delve into a crucial tapestry of behavior.\n")
    kinds = {f["kind"] for f in r["violations"]}
    assert "americanism" not in kinds and "ai_slop" not in kinds


def test_meta_leak_owner_severed_from_welder():
    assert verify.CHECK_SKILL["meta_leak"] == "orchestrated_generation"
    assert verify.CHECK_SKILL["voice"] == "orchestrated_generation"


# ---------------------------------------------------------------------------
# stage E: the prose dispatch's context isolation
# ---------------------------------------------------------------------------

def test_prose_dispatch_carries_no_engine_kernel():
    d = dispatch.compile_dispatch("N4", "probe", "prose", PROJECT)
    if "error" in d:
        assert "narrative" in d["error"]      # typed refusal names the stage
        pytest.skip("no narrative spec on disk for N4")
    # W-AIM (0ad73500, 2026-07-22): every prompt-bearing dispatch opens with the
    # content-level AIM block ABOVE its preamble. The contract the test holds is
    # unchanged — the clean stage preamble still leads the engine-facing body —
    # so read the body past the AIM fence, never a bare `in`.
    assert d["prompt"].split("<!-- /AIM -->", 1)[-1].lstrip().startswith(
        schema.PROSE_STAGE_PREAMBLE[:40])
    assert "graded hierarchy" not in d["prompt"].split("<!-- PACKET -->")[0]
    assert "canon://" not in d["prompt"].split("<!-- PACKET -->")[0]


def test_prose_dispatch_joins_the_voice_profile_exactly_once():
    d = dispatch.compile_dispatch("N4", "probe", "prose", PROJECT)
    if "error" in d:
        pytest.skip("no narrative spec on disk for N4")
    assert d["prompt"].count("<!-- VOICE-PROFILE -->") == 1


def test_node_dispatch_still_opens_with_the_kernel():
    d = dispatch.compile_dispatch("def:spectral-surface", "probe", "derive", PROJECT)
    # same W-AIM head as the prose packet: the graded-node kernel still opens the
    # body, below the content-level AIM block.
    assert "prompt" in d and d["prompt"].split("<!-- /AIM -->", 1)[-1].lstrip(
        ).startswith("You are one node")
    assert "VOICE-PROFILE" not in d["prompt"]  # voice never reaches node workers


def test_narrative_dispatch_never_names_voice():
    d = dispatch.compile_dispatch("N4", "probe", "narrative", PROJECT)
    if "error" in d:
        pytest.skip(d["error"])
    assert "voice" not in d["prompt"].lower().replace("invoice", "")


# ---------------------------------------------------------------------------
# THE TRIANGLE — plan.meta.contribution_rank threads into every kernel packet
# (the ONE authored judgement; strictly additive — byte-identical when absent)
# ---------------------------------------------------------------------------

def test_contribution_rank_block_accepts_both_shapes():
    # plain ordered strings
    b1 = dispatch._contribution_rank_block(["primary claim", "second claim"])
    assert b1.startswith("CONTRIBUTION RANK (authored once, plan meta")
    assert "1. primary claim" in b1 and "2. second claim" in b1
    # {rank, claim, role} dicts, with an excluded/exploratory role demoted
    b2 = dispatch._contribution_rank_block([
        {"rank": 1, "claim": "the main theorem", "role": "primary"},
        {"rank": 2, "claim": "a side probe", "role": "exploratory"}])
    assert "1. the main theorem [primary]" in b2
    assert "EXCLUDED/exploratory: a side probe (exploratory)" in b2
    # absent/empty → no block (the additive floor)
    assert dispatch._contribution_rank_block(None) == ""
    assert dispatch._contribution_rank_block([]) == ""


def test_contribution_rank_lines_catches_compound_excluded_roles():
    """A role need not read EXACTLY 'excluded'/'exploratory' - compound roles like
    the real SSG plan's 'exploratory-excluded' must still demote to the excluded
    line (substring match, not equality). Found live: the exact-match check missed
    subset-sum-itqde's actual 4th-rank entry (role 'exploratory-excluded'), so the
    board's authored-spine strip would have shown 4 primaries and 0 excluded."""
    from laplace.pipeline import schema
    primary, excluded = schema.contribution_rank_lines([
        {"rank": 1, "claim": "kept", "role": "primary"},
        {"rank": 2, "claim": "dropped", "role": "exploratory-excluded"},
    ])
    assert len(primary) == 1 and len(excluded) == 1
    assert "dropped" in excluded[0]


def test_kernel_byte_identical_without_rank():
    assert dispatch.kernel(None, "t", "g", "derive") == \
        dispatch.kernel(None, "t", "g", "derive", rank=None)


_REAL_READ_PLAN = registry.Project.read_plan


def _patch_plan_rank(monkeypatch, rank):
    """Inject (or clear, when ``rank is None``) ``meta.contribution_rank`` into the
    REAL plan without disturbing sections/appendices — so narrative_packet still
    resolves. The rank-injection seam for the additive proof."""
    def _patched(self, rr=None):
        plan = dict(_REAL_READ_PLAN(self, rr) or {})
        meta = dict(plan.get("meta") or {})
        meta.pop("contribution_rank", None)
        if rank is not None:
            meta["contribution_rank"] = rank
        plan["meta"] = meta
        return plan
    monkeypatch.setattr(registry.Project, "read_plan", _patched)


RANK = [{"rank": 1, "claim": "the primary result", "role": "primary"},
        {"rank": 2, "claim": "an exploratory aside", "role": "exploratory"}]


def test_contribution_rank_threads_into_kernel_bearing_packets(monkeypatch):
    block = dispatch._contribution_rank_block(RANK)
    for worker in ("derive", "mint"):            # kernel-bearing node workers
        _patch_plan_rank(monkeypatch, None)
        without = dispatch.compile_dispatch("def:spectral-surface", "probe",
                                            worker, PROJECT)
        _patch_plan_rank(monkeypatch, RANK)
        withr = dispatch.compile_dispatch("def:spectral-surface", "probe",
                                          worker, PROJECT)
        assert "prompt" in without and "prompt" in withr, worker
        assert "CONTRIBUTION RANK" not in without["prompt"], worker
        assert block in withr["prompt"], worker
        assert "the primary result" in withr["prompt"], worker
        # strictly ADDITIVE: removing the injected block yields the rank-less packet
        assert withr["prompt"].replace("\n\n" + block, "", 1) == without["prompt"], worker


def test_prose_packet_carries_the_hierarchy_as_content_not_kernel(monkeypatch):
    # §13 walls the KERNEL channel off from prose — but the contribution rank is
    # the paper’s own contribution hierarchy: content, not scaffolding, and the
    # prose realiser is its most important consumer. It now reaches prose through
    # the narrative packet, reframed as authored content (never as an engine
    # instruction) — kernel/policy framing still never crosses into prose.
    _patch_plan_rank(monkeypatch, None)
    a = dispatch.compile_dispatch("N4", "probe", "prose", PROJECT)
    _patch_plan_rank(monkeypatch, RANK)
    b = dispatch.compile_dispatch("N4", "probe", "prose", PROJECT)
    if "error" in a or "error" in b:
        pytest.skip("no narrative spec on disk for N4")

    # absent rank -> byte-identical to today (the additive floor)
    assert "CONTRIBUTION" not in a["prompt"]
    assert "contribution_hierarchy" not in a["prompt"]

    # present rank -> the hierarchy reaches prose, framed as CONTENT ...
    assert "THE PAPER'S CONTRIBUTION HIERARCHY" in b["prompt"]
    assert "contribution_hierarchy" in b["prompt"]
    assert "the primary result" in b["prompt"]
    assert "an exploratory aside" in b["prompt"]

    # ... and never as the kernel's POLICY-voiced block or any kernel scaffolding
    # (the §13 assertion this test always pinned, still true with content present)
    for prompt in (a["prompt"], b["prompt"]):
        assert "CONTRIBUTION RANK (authored once" not in prompt   # the kernel framing
        assert "You are one node in a graded hierarchy" not in prompt
        assert "<!-- POLICY -->" not in prompt
        assert "CONTRACT:" not in prompt
        assert "canon://" not in prompt


def _load_plan_validator():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "validate_projection_plan",
        ROOT / "scripts" / "validate_projection_plan.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_validator_accepts_good_contribution_rank_shapes_and_absence():
    v = _load_plan_validator()
    assert v.check_contribution_rank({}) == []                       # absent → clean
    assert v.check_contribution_rank({"contribution_rank": ["a", "b"]}) == []
    assert v.check_contribution_rank(
        {"contribution_rank": [{"rank": 1, "claim": "x", "role": "primary"}]}) == []


def test_validator_rejects_malformed_contribution_rank():
    v = _load_plan_validator()
    assert v.check_contribution_rank({"contribution_rank": []})       # empty list
    assert v.check_contribution_rank({"contribution_rank": "notalist"})
    assert v.check_contribution_rank({"contribution_rank": [{"claim": "x"}]})  # no rank/role
    assert v.check_contribution_rank({"contribution_rank": [123]})     # not str/dict


# ---------------------------------------------------------------------------
# C3.1 — stable contribution ids + section ownership (`serves`) + exclusions
# ---------------------------------------------------------------------------

import re as _re


def _line_ids(lines):
    """Extract the trailing ``{#id}`` markers the rendered rank lines carry."""
    return [_re.search(r"\{#(c[0-9a-f]+)\}", ln).group(1) for ln in lines]


def test_contribution_rank_id_is_content_derived_not_ordinal():
    # same claim -> same id (strip-stable); different claim -> different id
    a = schema.contribution_rank_id("the reusable spectral surface")
    assert a == schema.contribution_rank_id("  the reusable spectral surface  ")
    assert a != schema.contribution_rank_id("a different claim entirely")
    # opaque + non-ordinal: not the rank number, not derivable from position
    assert a.startswith("c") and not a[1:].isdigit()
    assert schema.contribution_rank_id("") == ""          # empty claim -> no id


def test_rank_ids_byte_identical_across_renders_and_list_vs_dict_authoring():
    rank = [{"rank": 1, "claim": "alpha claim", "role": "primary"},
            {"rank": 2, "claim": "beta claim", "role": "exploratory-excluded"}]
    p1, e1 = schema.contribution_rank_lines(rank)
    p2, e2 = schema.contribution_rank_lines(rank)
    assert (p1, e1) == (p2, e2)                            # two renders: byte-identical
    assert _line_ids(p1) == [schema.contribution_rank_id("alpha claim")]
    assert _line_ids(e1) == [schema.contribution_rank_id("beta claim")]
    # the SAME claims authored as plain strings derive the SAME ids (position/role
    # differ — beta has no role here so it lands in primary — but the id is identity)
    pl, el = schema.contribution_rank_lines(["alpha claim", "beta claim"])
    assert _line_ids(pl) == [schema.contribution_rank_id("alpha claim"),
                             schema.contribution_rank_id("beta claim")]
    assert schema.contribution_rank_id("alpha claim") in p1[0]     # dict form
    assert schema.contribution_rank_id("alpha claim") in pl[0]     # str form


_C31_META = {"contribution_rank": [
    {"rank": 1, "claim": "the main result", "role": "primary"},
    {"rank": 2, "claim": "a side probe", "role": "exploratory-excluded"}]}


def test_validator_serves_resolves_by_id_and_rank_number():
    v = _load_plan_validator()
    cid = v.contribution_rank_id("the main result")
    plan = {"meta": _C31_META, "sections": [
        {"id": "S1", "serves": cid},        # by stable content-id
        {"id": "S2", "serves": 2},          # by rank number (int)
        {"id": "S3", "serves": "1"}]}       # by rank number (str)
    defects, served, unserved = v.check_serves(plan, _C31_META)
    assert defects == [] and served == 3 and unserved == 0


def test_validator_unknown_serves_fails_closed():
    v = _load_plan_validator()
    plan = {"meta": _C31_META, "sections": [
        {"id": "S1", "serves": "c-does-not-exist"},
        {"id": "S2", "serves": 99},         # no such rank
        {"id": "S3", "serves": []}]}        # declared but empty
    defects, served, unserved = v.check_serves(plan, _C31_META)
    assert len(defects) == 3
    # S1/S2 declare a (non-empty) serves so they count as serving even though the
    # reference is unknown (that is what makes it a defect); S3's empty serves is a
    # defect and counts as neither
    assert served == 2 and unserved == 0
    # and a plan with NO contribution_rank cannot resolve any serves at all
    d2, _, _ = v.check_serves({"sections": [{"id": "S", "serves": 1}]}, {})
    assert len(d2) == 1


def test_validator_nonscalar_serves_fails_closed_not_a_crash():
    v = _load_plan_validator()
    # a dict serves, a list-with-dict serves, and a None-in-list serves: each
    # non-scalar entry must yield a DEFECT row, never raise TypeError on `ref in index`.
    cid = v.contribution_rank_id("the main result")
    plan = {"meta": _C31_META, "sections": [
        {"id": "S1", "serves": {"weird": "dict"}},        # dict -> defect
        {"id": "S2", "serves": [cid, {"a": 1}]},          # list w/ dict -> one defect
        {"id": "S3", "serves": [None, {"b": 2}]}]}        # None filtered, dict -> defect
    defects, served, unserved = v.check_serves(plan, _C31_META)
    # S1's dict, S2's dict, and S3's dict each fault; the real cid in S2 resolves clean
    assert len(defects) == 3
    assert all("str/int" in why for _sid, why in defects)
    assert unserved == 0


def test_validator_bool_serves_is_a_defect_never_rank_one():
    v = _load_plan_validator()
    # True == 1 and hash(True) == hash(1): an unguarded `True in index` is truthy
    # via the rank-number key, silently resolving `serves: true` as rank 1.
    # check_exclusions already guards bool; check_serves must match it.
    plan = {"meta": _C31_META, "sections": [
        {"id": "S1", "serves": True},
        {"id": "S2", "serves": [False]}]}
    defects, served, unserved = v.check_serves(plan, _C31_META)
    assert len(defects) == 2                   # each bool faults as non-scalar
    assert all("str/int" in why for _sid, why in defects)


def test_validator_unhashable_authored_rank_fails_closed_not_a_crash():
    """A MALFORMED authored ``rank`` field (list/dict — unhashable) must not take
    the whole validation down. Indexing it raised ``TypeError`` inside
    ``contribution_index``/``_excluded_index``, so ``validate`` CRASHED where it
    owed a FAIL report — every other defect list and the loud unserved count died
    with it. The entry keeps its content-id door (identity), loses only its
    rank-number one (a position), and the shape defect is reported by
    ``check_contribution_rank``."""
    v = _load_plan_validator()
    bad = {"contribution_rank": [
        {"rank": [], "claim": "the main result", "role": "primary"},
        {"rank": {"a": 1}, "claim": "a side probe", "role": "exploratory-excluded"}]}
    # the shape defect is still LOUD (one row per malformed entry)
    assert len(v.check_contribution_rank(bad)) == 2
    # ...and neither index raises; the content-id door still resolves
    cid = v.contribution_rank_id("the main result")
    defects, served, unserved = v.check_serves(
        {"sections": [{"id": "S1", "serves": cid}, {"id": "S2", "serves": 1}]}, bad)
    assert defects == [("S2", "serves references unknown contribution 1")]
    assert served == 2 and unserved == 0
    # exclusions resolve by content-id / claim text, never by the malformed rank
    ex_cid = v.contribution_rank_id("a side probe")
    assert v.check_exclusions(dict(bad, exclusions=[ex_cid, "a side probe"])) == []
    assert v.check_exclusions(dict(bad, exclusions=[2]))     # rank door is gone -> defect


def test_validator_bool_authored_rank_never_seizes_rank_one():
    """``True == 1`` and ``hash(True) == hash(1)``: an unguarded ``index[n]`` on a
    ``{"rank": true}`` entry would answer a legitimate ``serves: 1`` with the WRONG
    claim — a silent mis-resolution, worse than a defect."""
    v = _load_plan_validator()
    bad = {"contribution_rank": [
        {"rank": True, "claim": "the impostor", "role": "primary"},
        {"rank": 2, "claim": "the real second", "role": "primary"}]}
    index = v.contribution_index(bad)
    assert 1 not in index and True not in index and "1" not in index
    assert index[2] == "the real second"
    assert index[v.contribution_rank_id("the impostor")] == "the impostor"
    defects, _served, _unserved = v.check_serves(
        {"sections": [{"id": "S1", "serves": 1}]}, bad)
    assert defects == [("S1", "serves references unknown contribution 1")]


def test_validator_without_serves_still_valid_with_loud_count():
    v = _load_plan_validator()
    plan = {"meta": _C31_META, "sections": [
        {"id": "S1"}, {"id": "S2"}, {"id": "S3"}]}
    defects, served, unserved = v.check_serves(plan, _C31_META)
    assert defects == []                    # absence is not an error (incremental adoption)
    assert served == 0 and unserved == 3    # ...but the count is loud


def test_validator_full_run_without_serves_passes_and_reports_count():
    """The real subset-sum-itqde plan declares no `serves` — it must still PASS,
    with the loud unserved count surfaced (adoption is incremental)."""
    v = _load_plan_validator()
    plan_path = ROOT / "synthetics papers" / "subset-sum-itqde" / "manuscript" \
        / "projection_plan.json"
    if not plan_path.is_file():
        pytest.skip("subset-sum-itqde plan not on disk")
    r = v.validate(str(plan_path), "subset-sum-itqde")
    assert r["pass"], r
    assert r["serves_defects"] == []
    assert r["sections_serving"] == 0 and r["sections_without_serves"] > 0


def test_validator_exclusions_shape():
    v = _load_plan_validator()
    # absent -> clean
    assert v.check_exclusions({}) == []
    # a valid exclusion names an excluded-role contribution (by id, rank, or claim)
    cid = v.contribution_rank_id("a side probe")
    good = dict(_C31_META, exclusions=[cid, 2, "a side probe",
                                       {"ref": "2", "reason": "out of scope"}])
    assert v.check_exclusions(good) == []
    # a non-excluded (primary) contribution is NOT a legitimate exclusion member
    bad_primary = dict(_C31_META, exclusions=[v.contribution_rank_id("the main result")])
    assert v.check_exclusions(bad_primary)
    # shapeless / unknown / empty -> defects
    assert v.check_exclusions(dict(_C31_META, exclusions="notalist"))
    assert v.check_exclusions(dict(_C31_META, exclusions=[]))
    assert v.check_exclusions(dict(_C31_META, exclusions=[123]))
    assert v.check_exclusions(dict(_C31_META, exclusions=["c-nope"]))


# ---------------------------------------------------------------------------
# the 2026-07-22 RESPINE envelope: contribution_rank stored as
# {value:[...], projection_ruling:{...}} — every reader reads .value, none
# rewrites the store to a bare list (the ratified projection_ruling stands).
# ---------------------------------------------------------------------------

def _wrapped_meta():
    """A respine-wrapped contribution_rank (the ratified paper_falqon shape): the
    rank list lives under ``value``; ``projection_ruling`` carries its provenance."""
    return {"contribution_rank": {
        "value": [
            {"rank": 1, "claim": "the class thesis", "role": "primary"},
            {"rank": 2, "claim": "a derived step", "role": "derived"},
            {"rank": 3, "claim": "a parked probe", "role": "exploratory-excluded"}],
        "projection_ruling": {"verb": "respine", "intent": "PI-20260721-142526-161107",
                              "note": "ratified", "applied_by": "gerard"}}}


def test_validator_reads_respine_wrapped_contribution_rank_non_lossily():
    v = _load_plan_validator()
    meta = _wrapped_meta()
    before = json.loads(json.dumps(meta))            # a deep snapshot of the store shape

    # (i) check_contribution_rank PASSES on the wrapped shape (was: "must be a
    #     non-empty list" — the ratified thesis invisible to the whole chain)
    assert v.check_contribution_rank(meta) == []

    # (ii) serves resolve against the wrapped entries — by rank number AND content-id
    cid = v.contribution_rank_id("the class thesis")
    plan = {"meta": meta, "sections": [
        {"id": "S1", "serves": 1}, {"id": "S2", "serves": [2]}, {"id": "S3", "serves": cid}]}
    defects, served, unserved = v.check_serves(plan, meta)
    assert defects == [] and served == 3 and unserved == 0

    # (ii) exclusions resolve against the wrapped entries too: the excluded-role
    #      entry (rank 3) is a legitimate member; a primary (rank 1) is not
    assert v.check_exclusions(dict(meta, exclusions=[3])) == []
    assert v.check_exclusions(dict(meta, exclusions=[v.contribution_rank_id("a parked probe")])) == []
    assert v.check_exclusions(dict(meta, exclusions=[1]))     # primary is not excludable

    # NON-LOSSY: no reader mutated the store — the {value, projection_ruling}
    # envelope is byte-intact after the whole validation pass
    assert meta == before
    assert isinstance(meta["contribution_rank"], dict)
    assert meta["contribution_rank"]["projection_ruling"]["note"] == "ratified"


def test_validator_wrapped_rank_missing_value_is_still_malformed():
    # the unwrap only reads a `value` key; a dict WITHOUT one is not a rank list
    v = _load_plan_validator()
    assert v.check_contribution_rank({"contribution_rank": {"projection_ruling": {}}})


def test_contribution_rank_lines_unwraps_the_respine_envelope():
    # the ONE decode (kernel block, prose hierarchy, board strip all ride it) reads
    # .value, so the wrapped shape renders identically to the equivalent bare list
    wrapped = _wrapped_meta()["contribution_rank"]
    pw, ew = schema.contribution_rank_lines(wrapped)
    pb, eb = schema.contribution_rank_lines(wrapped["value"])
    assert (pw, ew) == (pb, eb)
    assert pw and ew                                  # the thesis is now visible
    assert "the class thesis" in pw[0]
    assert any("a parked probe" in ln for ln in ew)


def test_kernel_block_renders_the_wrapped_thesis():
    # the kernel-block renderer (dispatch) must carry the ratified thesis into every
    # builder packet even when the plan stored it under the respine envelope
    block = dispatch._contribution_rank_block(_wrapped_meta()["contribution_rank"])
    assert block.startswith("CONTRIBUTION RANK (authored once, plan meta")
    assert "the class thesis" in block
    assert "a parked probe" in block


# ---------------------------------------------------------------------------
# stage F: fragment parsing + fidelity mechanics (pure)
# ---------------------------------------------------------------------------

FRAG = """% PLAN:NX
% NODES: def:a thm:b
\\section{Example}\\label{sec:nx}
First paragraph prose about the object.

Second paragraph carrying the display anchor below.
\\begin{equation}\\label{eq:anchor-x}
x = 1
\\end{equation}
Third paragraph closes the example citing \\cite{ref_one} and \\ref{fig:nf9}.
"""


def test_parse_fragment_lifts_environments_and_markers():
    p = document_model.parse_fragment(FRAG, "NX")
    assert p["equation_labels"] == ["eq:anchor-x"]
    assert p["citations"] == ["ref_one"]
    assert p["figure_refs"] == ["fig:nf9"]
    assert p["nodes_marked"] == ["def:a", "thm:b"]
    assert len(p["paragraph_blocks"]) >= 3


# ---------------------------------------------------------------------------
# stage G: deterministic backend
# ---------------------------------------------------------------------------

def test_preamble_renders_deterministically_from_the_profile():
    profile = tex_backend.load_profile()
    record = {"working_title": "T"}
    one = tex_backend.render_preamble(profile, record)
    two = tex_backend.render_preamble(profile, record)
    assert one == two
    assert one.startswith("\\documentclass[")
    # the profile declares the eigen house layer, so the emitter emits
    # \usepackage{eigen-revtex} and TRIMS the packages the layer provides
    # (braket among them) — see test_template_agreement for the gate agreement.
    assert "revtex4-2" in one and "\\usepackage{eigen-revtex}" in one
    assert "\\usepackage{braket}" not in one


def test_title_block_places_authors_before_abstract():
    rendered = tex_backend.render_title_block({
        "working_title": "T",
        "authors": [{"name": "A. Author", "affiliations": ["EigenEngine"]}],
        "abstract": "An abstract.",
    })
    assert rendered.index("\\author{A. Author}") < rendered.index("\\begin{abstract}")
    assert "\\affiliation{EigenEngine}" in rendered


def test_figure_env_renders_spec_caption_and_defers_honestly():
    profile = tex_backend.load_profile()
    banked = tex_backend.render_figure_env("fig:nf9", {
        "figure_id": "fig:nf9", "status": "banked", "asset": "figures/NF9.pdf",
        "caption": "What is plotted; how generated; what it supports; "
                   "what it does not establish.", "width": "single",
    }, profile)
    assert "\\includegraphics" in banked and "\\caption{" in banked
    assert "\\label{fig:nf9}" in banked
    deferred = tex_backend.render_figure_env("fig:nf9", {
        "figure_id": "fig:nf9", "status": "deferred",
        "question_answered": "pending run"}, profile)
    assert "DEFERRED" in deferred and "\\includegraphics" not in deferred


def test_double_column_figure_width_uses_wide_environment():
    profile = tex_backend.load_profile()
    rendered = tex_backend.render_figure_env("fig:wide", {
        "figure_id": "fig:wide", "status": "banked", "asset": "figures/wide.pdf",
        "caption": "A full-width figure.", "width": "double-column",
    }, profile)
    assert "\\begin{figure*}" in rendered
    assert "\\end{figure*}" in rendered
    assert "width=\\textwidth" in rendered


# ---------------------------------------------------------------------------
# live project integration (artifacts committed by the rebuild)
# ---------------------------------------------------------------------------

def _stage(key: str) -> Path | None:
    proj = registry.resolve(PROJECT)
    return proj.stage_path(key) if proj else None


def test_live_manuscript_spec_validates():
    if not (_stage("spec") or Path()).is_file():
        pytest.skip("manuscript_spec.json not yet authored")
    r = projection_spec.validate_spec(PROJECT)
    assert r["pass"], r["issues"][:8]


def test_live_structural_gate_passes():
    if not (_stage("contracts") or Path()).is_file():
        pytest.skip("section_contracts.json not yet authored")
    r = structural.gate(PROJECT)
    assert r["pass"], r["issues"][:8]


def test_live_narratives_validate():
    nd = _stage("narrative")
    proj = registry.resolve(PROJECT)
    plan = proj.read_plan() or {}
    sids = [s["id"] for s in schema.plan_sections(plan)]
    have = {p.stem for p in nd.glob("*.json")} if (nd and nd.is_dir()) else set()
    if not set(sids) <= have:
        pytest.skip(f"narrative specs planned for {len(have)}/{len(sids)} sections")
    r = narrative.validate_all(PROJECT)
    assert r["pass"], {k: (v.get("issues") or v)[:3]
                       for k, v in r["sections"].items() if not v.get("pass")}


def test_staged_contract_row_green():
    r = contracts_verify.staged_stages_ready()
    assert r["pass"], r["missing"]


def test_stage_read_surface_serves_artifacts_and_typed_absence():
    from laplace.manuscript import storyboard as sb
    status, ctype, body = sb.handle(
        "/storyboard/stage", {"corpus": [PROJECT], "key": ["nope"]}, "GET", b"")
    assert status == 404
    status, ctype, body = sb.handle(
        "/storyboard/stage", {"corpus": [PROJECT], "key": ["spec"]}, "GET", b"")
    assert status in (200, 404)          # 200 once the spec artifact is authored
    if status == 200:
        assert json.loads(body)["artifact"]["manuscript"]["genre"]


# ---------------------------------------------------------------------------
# THE RETRIEVAL WIRE — the three authorized-but-unwired stores at their natural
# planning stages (DESIGN_2026-07-15_the-stage-stores §4; SCOUT_2026-07-16 TRACK
# B ADDENDUM). Each injection is BYTE-INERT at the shipped all-off dials and, when
# its dial is forced on, appends a FORM-EXEMPLARS envelope that is purely additive
# (the rest of the prompt stays byte-identical) and banks one audit sidecar.
# ---------------------------------------------------------------------------
import re as _re

from laplace.pipeline import (stage_retrieval as _sr, dials as _dials_mod,
                              derived_writes as _dw)


def _strip_form(prompt: str) -> str:
    """The prompt with every appended FORM-EXEMPLARS fence (and its leading blank
    line) removed — what must equal the dial-off prompt (the byte-inert law)."""
    return _re.sub(r"\n\n<!-- FORM-EXEMPLARS -->.*?<!-- /FORM-EXEMPLARS -->", "",
                   prompt, flags=_re.S)


def _force_stores_on(monkeypatch, *stores):
    d = _dials_mod.load_dials()
    for s in stores:
        d["stores"][s]["enabled"] = True
    monkeypatch.setattr(_sr, "load_dials", lambda *a, **k: d)


def _capture_sidecars(monkeypatch):
    """Redirect the sidecar bank into a list AND permit the bank to be attempted.

    The bank is gated read-only under pytest (``derived_writes``,
    WO-20260817-test-mutates-working-tree) so a live compile stops dirtying the
    working tree. These tests assert the wire DOES bank, so they opt in
    explicitly — safely, because the writer is monkeypatched away from disk
    first: nothing reaches the real tree either way."""
    calls = []
    monkeypatch.setattr(_sr, "write_form_channel_sidecar",
                        lambda path, record: (calls.append((str(path), record))
                                              or Path(path)))
    monkeypatch.setenv(_dw.WRITE_FLAG, "1")
    return calls


def _need_backend():
    if _sr.get_backend() is None:
        pytest.skip("no embedding backend (vendored bge-small unavailable)")


def _assert_served(calls, stores):
    assert [r["store"] for _, r in calls] == stores
    for _, rec in calls:
        assert rec["query_digest"].startswith("sha256:")
        assert rec["exemplars"] and all("cos" in e and "row_id" in e
                                        for e in rec["exemplars"])


def test_structure_injects_section_architecture_and_stays_inert(monkeypatch):
    _need_backend()
    calls = _capture_sidecars(monkeypatch)
    off = dispatch.compile_dispatch("sec:structure", "probe", "structure", PROJECT)
    assert "prompt" in off and "FORM-EXEMPLARS" not in off["prompt"]
    assert calls == []                              # off → nothing served, nothing banked
    _force_stores_on(monkeypatch, "section_architecture")
    on = dispatch.compile_dispatch("sec:structure", "probe", "structure", PROJECT)
    assert "FORM-EXEMPLARS" in on["prompt"] and "section_architecture" in on["prompt"]
    assert _strip_form(on["prompt"]) == off["prompt"]   # purely additive
    _assert_served(calls, ["section_architecture"])


def test_narrative_injects_paragraph_plan_and_spine_chain_and_stays_inert(monkeypatch):
    _need_backend()
    if "prompt" not in dispatch.compile_dispatch("N1", "probe", "narrative", PROJECT):
        pytest.skip("no narrative object for N1")
    calls = _capture_sidecars(monkeypatch)
    # shipped law since his 2026-07-16 yes: paragraph_plan serves by default at the
    # narrative stage (one envelope + one sidecar); spine_chain stays off-inert
    off = dispatch.compile_dispatch("N1", "probe", "narrative", PROJECT)
    assert off["prompt"].count("<!-- FORM-EXEMPLARS -->") == 1
    assert "spine_chain" not in off["prompt"] and len(calls) == 1
    calls.clear()
    _force_stores_on(monkeypatch, "paragraph_plan", "spine_chain")
    on = dispatch.compile_dispatch("N1", "probe", "narrative", PROJECT)
    assert on["prompt"].count("<!-- FORM-EXEMPLARS -->") == 2
    assert "paragraph_plan" in on["prompt"] and "spine_chain" in on["prompt"]
    assert _strip_form(on["prompt"]) == _strip_form(off["prompt"])  # off lawfully carries the shipped-on paragraph_plan envelope
    _assert_served(calls, ["paragraph_plan", "spine_chain"])


def test_prose_injects_derivation_walk_for_derivation_sections_and_stays_inert(monkeypatch):
    _need_backend()
    if "prompt" not in dispatch.compile_dispatch("N1", "probe", "prose", PROJECT):
        pytest.skip("no prose packet for N1")
    calls = _capture_sidecars(monkeypatch)
    off = dispatch.compile_dispatch("N1", "probe", "prose", PROJECT)
    assert "FORM-EXEMPLARS" not in off["prompt"] and calls == []
    _force_stores_on(monkeypatch, "derivation_walk")
    on = dispatch.compile_dispatch("N1", "probe", "prose", PROJECT)
    assert "FORM-EXEMPLARS" in on["prompt"] and "derivation_walk" in on["prompt"]
    assert _strip_form(on["prompt"]) == off["prompt"]
    _assert_served(calls, ["derivation_walk"])


def test_packet_bears_derivation_scopes_the_prose_wire():
    # the derivation_walk wire fires ONLY for derivation-bearing sections: an empty
    # ledger + no anchors/details → no injection (the scope guard, dial-independent).
    assert dispatch._packet_bears_derivation({"equation_ledger": {"eq:1": {}}}) is True
    assert dispatch._packet_bears_derivation(
        {"paragraphs": [{"equation_anchor": "eq:1"}]}) is True
    assert dispatch._packet_bears_derivation(
        {"paragraphs": [{"derivation_detail": "sketch"}]}) is True
    assert dispatch._packet_bears_derivation(
        {"equation_ledger": {}, "paragraphs": [{"function": "orient"}]}) is False


def test_flipped_figure_caption_would_refuse_in_a_dispatch(monkeypatch):
    # the gate hardening reaches the wire: were figure_caption ever injected and its
    # dial flipped, the compile would REFUSE loudly (its real refusal_proof_holds is
    # false) — proving the dial cannot smuggle it past the gate through a stage.
    _need_backend()
    d = _dials_mod.load_dials()
    d["stores"]["figure_caption"]["enabled"] = True
    monkeypatch.setattr(_sr, "load_dials", lambda *a, **k: d)
    parts = []
    with pytest.raises(SystemExit) as ei:
        dispatch._inject_form_channel(parts, "figure_caption", "any object",
                                      "N1", registry.resolve(PROJECT), ROOT)
    assert "refusal_proof_holds=false" in str(ei.value)
