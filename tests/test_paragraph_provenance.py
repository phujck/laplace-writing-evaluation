"""Paragraph-granular provenance — the join key that resolves a rendered span to
ITS paragraph (spec_id), not the whole section.

The realiser/weld emit ``% <sid>-pN`` before every paragraph; this pins that the
viewer parses them into paragraph spans WITHOUT disturbing the section-granular
``parse_map`` the dirty diff and the ledger/anchor consumers depend on.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from laplace.manuscript import projection_viewer as pv
from laplace.pipeline import dispatch, registry, schema

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "subset-sum-itqde"

SAMPLE = """% PLAN:N1
% NODES: def:a def:b res:c
\\section{Intro}\\label{sec:N1}

% N1-p1
First paragraph prose with enough real words to count as a block.
\\begin{equation}\\label{def:a}
a = 1
\\end{equation}
trailing sentence.

% N1-p2
Second paragraph, distinct span, same section.

% PLAN:N2
% NODES: def:d
\\section{Next}\\label{sec:N2}

% N2-p1
A paragraph under the second section, so its span carries N2.
"""


# ---------------------------------------------------------------------------
# the marker regex is precise — it matches paragraph markers and ONLY those
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("line", ["% N1-p1", "% NA1-p12", "%  sec3-p4  ", "%NA1-p1"])
def test_para_marker_matches_paragraph_lines(line):
    assert pv._PARA_RE.match(line)
    assert schema.PARA_MARKER_RE.match(line)


@pytest.mark.parametrize("line", [
    "% PLAN:NA1", "% NODES: def:hamiltonian def:x", "% see Eq-p3 in text",
    "% just a comment", "\\section{Body}",
])
def test_para_marker_rejects_non_paragraph_lines(line):
    assert not pv._PARA_RE.match(line)
    assert not schema.PARA_MARKER_RE.match(line)


# ---------------------------------------------------------------------------
# parse_paragraphs: spec_id + section + contiguous, non-overlapping spans
# ---------------------------------------------------------------------------

def test_parse_paragraphs_keys_each_span_by_spec_id_and_section():
    spans = pv.parse_paragraphs(SAMPLE)
    assert [s["spec_id"] for s in spans] == ["N1-p1", "N1-p2", "N2-p1"]
    assert [s["section"] for s in spans] == ["N1", "N1", "N2"]
    # spans are ordered, non-overlapping, 1-based inclusive
    for a, b in zip(spans, spans[1:]):
        assert a["start_line"] < a["end_line"] < b["start_line"] or \
               a["end_line"] < b["start_line"]
    # a paragraph span closes at the next paragraph OR section marker
    p2 = next(s for s in spans if s["spec_id"] == "N1-p2")
    assert p2["end_line"] < next(s for s in spans if s["spec_id"] == "N2-p1")["start_line"]


def test_parse_paragraphs_empty_without_markers():
    assert pv.parse_paragraphs("\\section{Plain}\nNo markers here at all.\n") == []


# ---------------------------------------------------------------------------
# parse_map is UNCHANGED — section-granular, still carrying the section node set
# (the six ledger/anchor consumers depend on this shape; the finer layer is added
# beside it, never on top of it)
# ---------------------------------------------------------------------------

def test_parse_map_stays_section_granular():
    secs = pv.parse_map(SAMPLE)
    assert [s["section"] for s in secs] == ["N1", "N2"]
    n1 = next(s for s in secs if s["section"] == "N1")
    assert set(n1["nodes"]) == {"def:a", "def:b", "res:c"}
    assert "spec_id" not in n1            # the section span carries no paragraph id


# ---------------------------------------------------------------------------
# the decision-sidecar contract is closed and well-formed
# ---------------------------------------------------------------------------

def test_decision_contract_is_closed():
    assert set(schema.DECISION_KINDS) == {
        "ambiguity-resolved", "substance-doubt", "cross-link-opportunity",
        "voice-choice", "paragraph-restructure"}
    for f in ("spec_id", "section", "stage", "kind", "after", "rationale"):
        assert f in schema.DECISION_RECORD_FIELDS


def test_parse_paragraphs_merges_adjacent_markers():
    # the weld MERGES two plan paragraphs: their markers sit adjacently, so the
    # resulting paragraph carries BOTH spec_ids (his many-to-many model)
    merged = ("% PLAN:N3\n% NODES: def:a def:b\n\\section{S}\n\n"
              "% N3-p1\n% N3-p2\nOne merged paragraph carrying two plan units of content here.\n\n"
              "% N3-p3\nA separate later paragraph with its own distinct span of prose.\n")
    spans = pv.parse_paragraphs(merged)
    assert [s["spec_ids"] for s in spans] == [["N3-p1", "N3-p2"], ["N3-p3"]]
    assert spans[0]["spec_id"] == "N3-p1"          # single-value callers still work
    assert spans[0]["end_line"] < spans[1]["start_line"]


# ---------------------------------------------------------------------------
# live: the committed SSG fragments carry paragraph markers that resolve
# ---------------------------------------------------------------------------

def _ssg_fragment(name: str) -> Path:
    return ROOT / "synthetics papers" / PROJECT / "manuscript" / "whitepaper" / name


@pytest.mark.skipif(not _ssg_fragment("NA1.tex").is_file(),
                    reason="SSG whitepaper fragments not present")
def test_forks_join_surfaces_the_decision_layer():
    # NA1 carries paragraph markers + realiser qualifications (its R-notes)
    out = pv.forks(str(_ssg_fragment("NA1.tex")), PROJECT)
    assert "paragraphs" in out and out["paragraphs"]
    forked = [p for p in out["paragraphs"] if p["qualifications"] or p["decisions"]]
    assert forked, "NA1 should surface the realiser's forks as qualifications"
    p = forked[0]
    assert p["spec_id"].startswith("NA1-p")
    assert p["start_line"] and p["end_line"]
    assert "nodes_realised" in p and "decisions" in p   # weld decisions empty pre-weld
    # generic + graceful: a missing project is a typed error, not a crash
    assert "error" in pv.forks(str(_ssg_fragment("NA1.tex")), "")


@pytest.mark.skipif(not _ssg_fragment("NA1.tex").is_file(),
                    reason="SSG whitepaper fragments not present")
def test_live_ssg_fragment_paragraphs_resolve():
    frag = _ssg_fragment("NA1.tex")
    spans = pv.load_paragraphs(frag)
    assert spans, "NA1.tex should carry % NA1-pN markers"
    assert all(s["section"] == "NA1" for s in spans)
    assert all(s["spec_id"].startswith("NA1-p") for s in spans)
    # every paragraph line falls inside exactly one paragraph span
    ids = [s["spec_id"] for s in spans]
    assert ids == sorted(set(ids), key=ids.index)      # unique, in order


# ---------------------------------------------------------------------------
# the weld emits its forks — and the compiler stays GENERIC (SSG is the first
# example, never the design target: no manuscript-specific count baked in)
# ---------------------------------------------------------------------------

def test_decisions_stage_resolves_through_the_registry():
    proj = registry.resolve(PROJECT)
    if proj is None:
        pytest.skip("SSG not resolvable")
    d = proj.stage_path("decisions")
    assert d is not None and d.name == "decisions"   # a home, not a hardcoded path


def test_weld_dispatch_is_generic_and_records_forks():
    d = dispatch.compile_weld_dispatch(PROJECT)
    if "error" in d:
        pytest.skip(d["error"])
    prompt = d["prompt"]
    # GENERICITY: no manuscript-specific section count baked into the compiler
    assert "eleven" not in prompt.lower()
    assert "twelve" not in prompt.lower()
    # adaptive staging + a registry-resolved home for the decision sidecar
    assert d["staging"] in ("global", "rolling")
    assert d["decisions_dir"] and d["decisions_dir"].endswith("decisions")
    # the decision contract is present and generic (a <sid> placeholder, per kind)
    assert "decision sidecar" in prompt
    assert all(k in prompt for k in schema.DECISION_KINDS)
    # cross-links are SURFACED, never silently written (the substance freeze holds)
    assert "never silently written" in prompt
    assert "substance freeze holds" in prompt


def test_weld_dispatch_voice_toggle_neutral_first_voice_last():
    # his ruling 2026-07-09: the manuscript completes in a NEUTRAL tone first; voice
    # is the last, opt-in layer. The default weld is neutral (no profile fenced);
    # voice_on=True is RETRIEVAL-GROUNDED (Phase I2) — it writes FROM his real prose,
    # the profile demoted to thin orientation, and REFUSES a spec-driven pass.
    neutral = dispatch.compile_weld_dispatch(PROJECT)
    if "error" in neutral:
        pytest.skip(neutral["error"])
    assert neutral["voice_on"] is False
    assert "NEUTRAL technical register" in neutral["prompt"]
    assert "REGISTER-ORIENTATION" not in neutral["prompt"]   # no profile fenced in neutral mode
    assert "RETRIEVED-EXEMPLARS" not in neutral["prompt"]

    voice = dispatch.compile_weld_dispatch(PROJECT, voice_on=True)
    assert voice["voice_on"] is True
    if voice.get("neutral_fallback"):
        # FAIL-LOUD: the sealed voice store is not built in this environment, so
        # voice_on ships neutral rather than degrade to a spec-driven pass. That is
        # the CORRECT refusal, not a regression.
        assert "Refusing a spec-driven pass" in voice["error"]
        assert "prompt" not in voice
        pytest.skip("voice store unavailable — fail-loud neutral fallback exercised")
    # RETRIEVAL-GROUNDED: exemplars are the substrate, the profile is demoted, and
    # the old spec-driven instruction ("as ONE voice - the profile below") is gone.
    assert "RETRIEVED-EXEMPLARS" in voice["prompt"]
    assert "REGISTER-ORIENTATION" in voice["prompt"]         # profile present, demoted
    assert "as ONE voice - the profile below" not in voice["prompt"]
    assert "a description of a generator does not generate" in voice["prompt"]
    assert voice["retrieval"]["paragraphs_with_exemplars"] >= 1
