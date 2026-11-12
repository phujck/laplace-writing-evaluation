"""Tests for the blind_reader pre-filter (canon://skills/blind_reader).

The script is the mechanical pre-pass, not the oracle. These tests pin the two
things it claims to catch: leaked operational/meta-prose (even when it wraps across
source lines, as it did in the operatorial-loss abstract) and the define-before-use
census, plus the masking that keeps a term in math or a comment from counting.
"""

import importlib.util
from pathlib import Path

_SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "src/laplace/pipeline/canon/skills/blind_reader/scripts/blind_read.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("blind_read", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


br = _load()


def test_leaked_meta_matches_across_line_wrap():
    # The real case: "we are" ends one line, the rest begins the next.
    text = "the question is sharp and we are\nexplicit about what is new here (the synthesis)."
    masked = br.mask_regions(text, ".tex")
    flags = br.find_leaked_meta(masked)
    kinds = [f["kind"] for f in flags]
    assert "leaked-meta" in kinds
    # Reported at the line where the phrase begins, not where it ends.
    assert flags[0]["line"] == 1


def test_leaked_meta_clean_prose_is_silent():
    text = "We promote the loss to an operator and band it by Pauli weight."
    flags = br.find_leaked_meta(br.mask_regions(text, ".tex"))
    assert flags == []


def test_census_flags_undefined_term():
    lines = ["We band the loss operator by Pauli weight and read off the plateau."]
    masked = [br.mask_regions(lines[0], ".tex")]
    flags = br.census_terms(lines, masked, ["loss operator", "Pauli weight"], window=0)
    terms = {f["term"] for f in flags}
    assert terms == {"loss operator", "Pauli weight"}
    assert all(f["kind"] == "undefined-term" for f in flags)


def test_census_grounded_by_citation_is_clean():
    lines = [r"Operator growth is established \cite{Parker2019}."]
    masked = [br.mask_regions(lines[0], ".tex")]
    flags = br.census_terms(lines, masked, ["operator growth"], window=0)
    assert flags == []


def test_census_grounded_by_definition_cue_is_clean():
    lines = ["The low-weight fraction is the share of the operator at low weight."]
    masked = [br.mask_regions(lines[0], ".tex")]
    flags = br.census_terms(lines, masked, ["low-weight fraction"], window=0)
    assert flags == []


def test_census_use_before_define_respects_window():
    lines = [
        "The loss operator drives everything.",   # line 1: bare use
        "Filler line with no grounding at all.",  # line 2
        "Here the loss operator is the Heisenberg observable.",  # line 3: grounded
    ]
    masked = [br.mask_regions(ln, ".tex") for ln in lines]
    flags = br.census_terms(lines, masked, ["loss operator"], window=1)
    assert len(flags) == 1
    assert flags[0]["kind"] == "use-before-define"
    assert flags[0]["line"] == 1


def test_masking_excludes_terms_in_math_and_comments():
    lines = [
        r"% the loss operator lives in this comment",
        r"$\text{loss operator}$ inside math",
    ]
    masked = [br.mask_regions(ln, ".tex") for ln in lines]
    flags = br.census_terms(lines, masked, ["loss operator"], window=0)
    # The term never appears in PROSE, so the census must not flag it at all.
    assert flags == []


def test_strict_exit_code_when_flags(tmp_path):
    p = tmp_path / "draft.tex"
    p.write_text("We use the loss operator throughout.", encoding="utf-8")
    rc = br.main([str(p), "--terms", "loss operator", "--strict"])
    assert rc == 1
    rc_clean = br.main([str(p), "--terms", "loss operator"])  # no --strict
    assert rc_clean == 0
