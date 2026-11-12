"""The readability gate: a whole-object stranger read whose refusal blocks the lock.

Born from the r2 verdict (``evidence/FIRST_CHAIR_2026-07-21_r2-read.md``): every local
judge stayed silent on an unreadable paper, so the gate is a whole-object reader immune to
confected local passes. These prove the grading pipeline (read -> mechanical floor ->
dispatch -> settle) end to end with the model layer stubbed at the dispatch boundary, and
the candidate-lock wiring that refuses on a FAIL or an UNAVAILABLE.

The reader model is never called here: a deterministic stranger stub stands at the
dispatch boundary, keyed off the real fixture text, so the pipeline is exercised without a
real model call.
"""
from __future__ import annotations

import json
from pathlib import Path

from laplace.pipeline import candidate_lock
from laplace.pipeline import readability_gate as rg


# --- fixtures ---------------------------------------------------------------

#: intro + definitions before use + a held thesis: the readable shape.
GOOD_TEX = r"""\documentclass{article}
\begin{document}
\section{Introduction}
This paper studies the FALQON algorithm on a lattice Hamiltonian. We motivate the
problem, state our contribution -- a linear depth bound -- and give a roadmap. Let
$H$ denote the Hamiltonian and $p$ the layer count, both defined here before use.
\section{Background}
We define the hopping term and the onsite term in terms of $H$ and $p$.
\section{Results}
Our thesis, that the depth scales linearly with system size, is borne out by the
construction of the preceding sections.
\end{document}
"""

#: missing the introduction beat and carrying provenance narration + ledger names +
#: per-number hedging: the r2 falqon defects, condensed.
BAD_TEX = r"""\documentclass{article}
\begin{document}
\section{The setting, and every assumption on the table}
This count is derived rather than assumed. The tier labels describe how a number was
obtained within this paper, not any claim about its objective necessity.
system_qubits = 60 logical qubits. falqon_layers = 500 layers. The onset has not been
checked. No Trotter error bound is computed. It was swept but not measured here.
\end{document}
"""


def _manuscript(tmp_path: Path, tex: str) -> Path:
    md = tmp_path / "manuscript"
    md.mkdir()
    (md / "main.tex").write_text(tex, encoding="utf-8")
    return md


def _stranger_reader(prompt: str, *, model: str, effort: str) -> str:
    """A deterministic hold-out stranger at the dispatch boundary. It reads the prompt
    (which carries the artefact text), passes a paper that opens on an introduction and
    keeps a plain register, and fails one that does not -- keyed off the real fixture, so
    the whole pipeline runs without a model call."""
    import re

    has_intro = bool(re.search(r"\\section\{[^}]*Introduction", prompt))
    leaks = "derived rather than assumed" in prompt
    if has_intro and not leaks:
        return json.dumps({
            "verdict": "PASS", "mechanisms": [],
            "stranger_account": "A study of FALQON depth scaling on a lattice, with a "
                                "linear bound argued from the construction."})
    mechs = []
    if not has_intro:
        mechs.append({"class": "a", "where": "opening",
                      "finding": "no introduction that teaches before use", "quote": ""})
    if leaks:
        mechs.append({"class": "d", "where": "prose",
                      "finding": "provenance narration in the running text",
                      "quote": "derived rather than assumed"})
    return json.dumps({"verdict": "FAIL", "mechanisms": mechs,
                       "stranger_account": "audit rows in sequence, no story"})


def _eligible_evidence() -> tuple[dict, dict, bool]:
    return {"hard_failing": False}, {"ok": True, "errors": 0, "undefined": 0}, True


# --- the structural floor (mechanical grader) -------------------------------

def test_structural_floor_clean_on_the_readable_shape():
    assert rg.structural_floor(GOOD_TEX) == []


def test_structural_floor_names_the_r2_breaches():
    floor = rg.structural_floor(BAD_TEX)
    classes = {m["class"] for m in floor}
    # the missing introduction beat (a) and the register leakage (d) are both named.
    assert "a" in classes
    assert "d" in classes
    findings = " ".join(m["finding"] for m in floor)
    assert "introduction beat" in findings
    assert "provenance narration" in findings
    assert any("system_qubits" in m["where"] for m in floor)   # ledger name in prose


# --- the grading pipeline (dispatch boundary stubbed) -----------------------

def test_good_artefact_passes_structurally_and_reads_clean(tmp_path):
    md = _manuscript(tmp_path, GOOD_TEX)
    verdict = rg.grade(md, dispatch=_stranger_reader)
    assert verdict["verdict"] == rg.PASS
    assert verdict["source"] == "tex"          # no PDF -> the full tex is read
    assert verdict["model"] == rg.GATE_MODEL   # the reader was stamped, not inherited
    assert verdict["stranger_account"]
    assert not rg.blocks_lock(verdict)


def test_bad_artefact_fails_with_mechanisms_named(tmp_path):
    md = _manuscript(tmp_path, BAD_TEX)
    verdict = rg.grade(md, dispatch=_stranger_reader)
    assert verdict["verdict"] == rg.FAIL
    assert rg.blocks_lock(verdict)
    classes = {m["class"] for m in verdict["mechanisms"]}
    assert "a" in classes and "d" in classes   # missing intro + register leakage
    reasons = rg.refusal_reasons(verdict)
    assert any("introduction beat" in r for r in reasons)
    assert any("provenance narration" in r for r in reasons)


def test_no_model_is_unavailable_and_blocks(tmp_path):
    md = _manuscript(tmp_path, GOOD_TEX)
    verdict = rg.grade(md, dispatch=None)       # the reader boundary is unreachable
    assert verdict["verdict"] == rg.UNAVAILABLE
    assert verdict["reason"] == "no_model"
    assert rg.blocks_lock(verdict)              # an unreadable-unknown never passes


def test_dispatch_failure_is_unavailable_and_blocks(tmp_path):
    md = _manuscript(tmp_path, GOOD_TEX)

    def _broken(prompt, *, model, effort):
        raise RuntimeError("reader host down")

    verdict = rg.grade(md, dispatch=_broken)
    assert verdict["verdict"] == rg.UNAVAILABLE
    assert verdict["reason"] == "model_unreachable"
    assert rg.blocks_lock(verdict)


def test_no_artefact_is_unavailable_and_blocks(tmp_path):
    md = tmp_path / "empty"
    md.mkdir()                                  # no PDF, no tex
    verdict = rg.grade(md, dispatch=_stranger_reader)
    assert verdict["verdict"] == rg.UNAVAILABLE
    assert verdict["reason"] == "no_artefact"
    assert rg.blocks_lock(verdict)


def test_truncated_read_cannot_certify_a_whole_object_pass():
    # a reader reply that would otherwise PASS cannot certify a whole-object PASS when the
    # read was truncated -- the whole object was never met, so the verdict is refused.
    would_pass = {"verdict": "PASS", "mechanisms": [],
                  "stranger_account": "a complete, readable account"}
    verdict = rg.settle_verdict(would_pass, floor=[], truncated=True, model=rg.GATE_MODEL)
    assert verdict["verdict"] == rg.UNAVAILABLE
    assert verdict["reason"] == "truncated"
    assert rg.blocks_lock(verdict)
    # the same reply on a whole read passes.
    whole = rg.settle_verdict(would_pass, floor=[], truncated=False, model=rg.GATE_MODEL)
    assert whole["verdict"] == rg.PASS


def test_grade_marks_truncation_on_a_capped_read(tmp_path):
    md = _manuscript(tmp_path, GOOD_TEX)
    verdict = rg.grade(md, dispatch=_stranger_reader, max_input_chars=50)
    # a capped read is refused (never a silent whole-object verdict); it does not PASS.
    assert verdict["verdict"] != rg.PASS
    assert rg.blocks_lock(verdict)


def test_unparseable_reader_reply_is_unavailable(tmp_path):
    md = _manuscript(tmp_path, GOOD_TEX)

    def _garbage(prompt, *, model, effort):
        return "I could not read the paper, sorry."

    verdict = rg.grade(md, dispatch=_garbage)
    assert verdict["verdict"] == rg.UNAVAILABLE
    assert rg.blocks_lock(verdict)


def test_floor_breach_overrides_a_reader_pass(tmp_path):
    """A reader that says PASS cannot override a mechanical (a)-(d) breach: the verdict is
    settled deterministically, not taken as the reader's claim."""
    md = _manuscript(tmp_path, BAD_TEX)

    def _lenient(prompt, *, model, effort):
        return json.dumps({"verdict": "PASS", "mechanisms": [],
                           "stranger_account": "looks fine to me"})

    verdict = rg.grade(md, dispatch=_lenient)
    assert verdict["verdict"] == rg.FAIL       # the floor's breaches force the FAIL


def test_dispatch_carries_a_clamped_model_stamp():
    disp = rg.compile_read_dispatch("prompt", model="opus-with-headroom")
    # an unknown / above-ceiling name is clamped to the ceiling, never passed through.
    from laplace.pipeline import schema
    assert disp["model"] == schema.clamp_model("opus-with-headroom")
    assert schema.MODEL_RANK.index(disp["model"]) <= schema.MODEL_RANK.index(schema.MAX_MODEL)


# --- the candidate-lock wiring (the lock-blocking tier) ---------------------

def test_lock_refuses_on_readability_fail(tmp_path):
    md = _manuscript(tmp_path, BAD_TEX)
    res = candidate_lock.record_lock(md, *_eligible_evidence(), by="gerard",
                                     readability=_stranger_reader)
    assert res["eligible"] is False            # blocked despite the local greens
    assert res["advanced"] is False
    assert res["reasons"]
    assert res["readability"]["verdict"] == rg.FAIL
    # the machine was not driven: no lock sidecar was written.
    assert not (md / "release" / "state.json").is_file()


def test_lock_blocks_when_reader_unavailable(tmp_path):
    md = _manuscript(tmp_path, GOOD_TEX)
    res = candidate_lock.record_lock(md, *_eligible_evidence(), by="gerard",
                                     readability=None)   # tier wired, no reader reachable
    assert res["eligible"] is False
    assert res["advanced"] is False
    assert res["readability"]["verdict"] == rg.UNAVAILABLE
    assert not (md / "release" / "state.json").is_file()


def test_lock_advances_on_readability_pass(tmp_path):
    from laplace.pipeline import release
    md = _manuscript(tmp_path, GOOD_TEX)
    res = candidate_lock.record_lock(md, *_eligible_evidence(), by="gerard",
                                     readability=_stranger_reader)
    assert res["eligible"] is True
    assert res["advanced"] is True
    assert res["state"] == "CANDIDATE_LOCKED"
    assert release.current_state(md) == "CANDIDATE_LOCKED"


def test_unwired_lock_is_byte_identical_to_before(tmp_path):
    """A caller that predates the tier passes no reader boundary; the lock behaves exactly
    as it did before the tier existed (the tier is off, not fail-closed, when unwired)."""
    md = _manuscript(tmp_path, BAD_TEX)         # unreadable, but the tier is not engaged
    res = candidate_lock.record_lock(md, *_eligible_evidence(), by="gerard")
    assert res["eligible"] is True
    assert res["advanced"] is True
    assert "readability" not in res
