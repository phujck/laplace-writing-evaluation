"""Candidate-lock: round completeness (silence never reads as pass), lock
eligibility (hard dims + clean compile + complete round), the self-contained
incumbent snapshot/restore, and the accept-or-restore transaction that wraps the
dominance decision — on reject the challenger's bytes are rolled back.
"""
import pytest

from laplace.pipeline import candidate_lock as cl
from laplace.pipeline import convergence as C


def _ev(hard=True, **soft):
    """A candidate evaluation: all hard dims `hard`, soft dims from kwargs."""
    h = {d: hard for d in C.HARD_DIMENSIONS}
    s = {d: soft.get(d, 0.5) for d in C.SOFT_DIMENSIONS}
    return {"hard": h, "soft": s}


def _verdict(label, clean=True, **extra):
    return {"label": label, "clean": clean, "flags": extra.get("flags", [])}


# --- round completeness — silence never reads as pass -----------------------

def test_complete_round_needs_every_expected_verdict():
    panel = [_verdict("R1"), _verdict("R2", clean=False), _verdict("R4")]
    st = cl.round_status(panel, expected=["R1", "R2", "R4"])
    assert st["complete"] is True          # an UNCLEAN verdict still counts as present
    assert st["missing"] == []             # completeness != pass (lock_eligible gates that)


def test_failed_verdict_makes_round_incomplete():
    panel = [_verdict("R1"), {"label": "R2", "failed": True}]
    st = cl.round_status(panel, expected=["R1", "R2"])
    assert st["complete"] is False
    assert "R2" in st["missing"]           # a failed judge is not a verdict


def test_malformed_verdict_makes_round_incomplete():
    panel = [_verdict("R1"), {"label": "R2"}]   # no boolean `clean` -> malformed
    st = cl.round_status(panel, expected=["R1", "R2"])
    assert st["complete"] is False
    assert "R2" in st["missing"]


def test_missing_expected_label_is_incomplete():
    panel = [_verdict("R1")]
    st = cl.round_status(panel, expected=["R1", "R2", "R4"])
    assert st["complete"] is False
    assert st["missing"] == ["R2", "R4"]


def test_empty_panel_no_expectation_is_incomplete():
    assert cl.round_status([])["complete"] is False       # nothing came back


# --- lock eligibility -------------------------------------------------------

_CLEAN_COMPILE = {"errors": 0, "undefined": 0}


def test_eligible_when_hard_pass_clean_compile_and_complete():
    # the HARD dims that read panel labels (claims, caption, meta_leak) must be
    # clean for evaluate_round to hard-pass; an absent label reads as not-clean.
    panel = [{"label": "claims", "clean": True},
             {"label": "caption", "clean": True},
             {"label": "meta_leak", "clean": True}]
    round_eval = C.evaluate_round(panel)
    assert round_eval["hard_failing"] is False        # guard the fixture's premise
    ok, reasons = cl.lock_eligible(round_eval, _CLEAN_COMPILE, round_complete=True)
    assert ok is True and reasons == []


def test_hard_shape_tolerance_raw_and_contract():
    # _hard_pass accepts an evaluate_round result, a raw {"hard":...} eval, and a
    # {"contract":...} wrap — whatever the caller has to hand.
    raw = _ev(hard=True)
    wrapped = {"contract": _ev(hard=True)}
    assert cl.lock_eligible(raw, _CLEAN_COMPILE, True)[0] is True
    assert cl.lock_eligible(wrapped, _CLEAN_COMPILE, True)[0] is True


def test_blocks_on_hard_fail():
    ok, reasons = cl.lock_eligible({"hard_failing": True}, _CLEAN_COMPILE, True)
    assert ok is False
    assert any("hard dimension" in r for r in reasons)


def test_blocks_on_dirty_compile():
    ok, reasons = cl.lock_eligible(_ev(hard=True), {"undefined": 2}, True)
    assert ok is False
    assert any("2 undefined" in r for r in reasons)


def test_blocks_on_missing_compile_report():
    ok, reasons = cl.lock_eligible(_ev(hard=True), {}, True)
    assert ok is False
    assert any("no compile report" in r for r in reasons)


def test_blocks_on_incomplete_round():
    ok, reasons = cl.lock_eligible(_ev(hard=True), _CLEAN_COMPILE, round_complete=False)
    assert ok is False
    assert any("round incomplete" in r for r in reasons)


# --- incumbent snapshot / restore — self-contained, no git reliance ---------

def _make_manuscript(root):
    (root / "main.tex").write_text("INCUMBENT BODY", encoding="utf-8")
    (root / "sections").mkdir()
    (root / "sections" / "intro.tex").write_text("intro incumbent", encoding="utf-8")
    (root / "main.pdf").write_bytes(b"%PDF-incumbent")
    (root / "main.log").write_text("log incumbent", encoding="utf-8")


def test_snapshot_is_self_contained(tmp_path):
    _make_manuscript(tmp_path)
    ref = cl.snapshot_incumbent(tmp_path, 1)
    from pathlib import Path
    snap = Path(ref)
    assert (snap / "SNAPSHOT.json").is_file()
    assert (snap / "main.tex").read_text(encoding="utf-8") == "INCUMBENT BODY"
    assert (snap / "sections" / "intro.tex").is_file()   # tree structure preserved
    assert (snap / "main.pdf").is_file() and (snap / "main.log").is_file()


def test_restore_rolls_back_challenger_bytes(tmp_path):
    _make_manuscript(tmp_path)
    ref = cl.snapshot_incumbent(tmp_path, 1)
    # a challenger overwrites the fragments in place
    (tmp_path / "main.tex").write_text("CHALLENGER BODY", encoding="utf-8")
    (tmp_path / "sections" / "intro.tex").write_text("intro challenger", encoding="utf-8")
    out = cl.restore_incumbent(tmp_path, ref)
    assert "main.tex" in out["restored"]
    assert (tmp_path / "main.tex").read_text(encoding="utf-8") == "INCUMBENT BODY"
    assert (tmp_path / "sections" / "intro.tex").read_text(encoding="utf-8") == "intro incumbent"


def test_restore_accepts_int_and_string_refs(tmp_path):
    _make_manuscript(tmp_path)
    cl.snapshot_incumbent(tmp_path, 3)
    (tmp_path / "main.tex").write_text("X", encoding="utf-8")
    cl.restore_incumbent(tmp_path, 3)                     # int ref
    assert (tmp_path / "main.tex").read_text(encoding="utf-8") == "INCUMBENT BODY"
    (tmp_path / "main.tex").write_text("Y", encoding="utf-8")
    cl.restore_incumbent(tmp_path, "r3")                 # "r<N>" ref
    assert (tmp_path / "main.tex").read_text(encoding="utf-8") == "INCUMBENT BODY"


def test_latest_incumbent_tracks_highest_round(tmp_path):
    _make_manuscript(tmp_path)
    assert cl.latest_incumbent(tmp_path) is None
    cl.snapshot_incumbent(tmp_path, 1)
    cl.snapshot_incumbent(tmp_path, 2)
    from pathlib import Path
    assert Path(cl.latest_incumbent(tmp_path)).name == "incumbent_r2"


def test_restore_missing_snapshot_is_loud(tmp_path):
    _make_manuscript(tmp_path)
    with pytest.raises(FileNotFoundError):
        cl.restore_incumbent(tmp_path, 9)


# --- the artefact fingerprint (IDEMPOTENCE row 14) --------------------------
# The converge loop puts this digest in every round agent's prompt, so the
# harness's prompt-keyed agent cache cannot replay a pre-edit round verdict.
# What it must guarantee: same sources -> same digest (a resume still caches);
# any source edit -> different digest (every round prompt busts).

def test_fingerprint_is_stable_across_recompiles_and_snapshots(tmp_path):
    _make_manuscript(tmp_path)
    fp = cl.tex_fingerprint(tmp_path)
    assert len(fp) == 16
    (tmp_path / "main.pdf").write_bytes(b"%PDF-recompiled")   # build outputs move
    (tmp_path / "main.log").write_text("log recompiled", encoding="utf-8")
    assert cl.tex_fingerprint(tmp_path) == fp
    cl.snapshot_incumbent(tmp_path, 1)                        # rounds/ copies excluded
    assert cl.tex_fingerprint(tmp_path) == fp


def test_fingerprint_moves_on_any_source_edit_and_returns_on_revert(tmp_path):
    _make_manuscript(tmp_path)
    fp = cl.tex_fingerprint(tmp_path)
    (tmp_path / "sections" / "intro.tex").write_text("intro EDITED", encoding="utf-8")
    edited = cl.tex_fingerprint(tmp_path)
    assert edited != fp
    (tmp_path / "sections" / "intro.tex").write_text("intro incumbent", encoding="utf-8")
    assert cl.tex_fingerprint(tmp_path) == fp                 # content, not mtime
    (tmp_path / "refs.bib").write_text("@article{a}", encoding="utf-8")
    assert cl.tex_fingerprint(tmp_path) != fp                 # .bib counts too


def test_fingerprint_covers_layout_and_missing_dir(tmp_path):
    _make_manuscript(tmp_path)
    fp = cl.tex_fingerprint(tmp_path)
    (tmp_path / "sections" / "intro.tex").rename(tmp_path / "sections" / "opening.tex")
    assert cl.tex_fingerprint(tmp_path) != fp                 # a move is a change
    assert cl.tex_fingerprint(tmp_path / "does_not_exist") == ""


# --- the accept-or-restore transaction --------------------------------------

def test_accept_advances_incumbent_and_keeps_challenger_bytes(tmp_path):
    _make_manuscript(tmp_path)
    ref = cl.snapshot_incumbent(tmp_path, 1)
    (tmp_path / "main.tex").write_text("CHALLENGER WINS", encoding="utf-8")
    # candidate hard-passes; incumbent None -> seeds -> accepted.
    out = cl.accept_or_restore(tmp_path, ref, _ev(hard=True), None)
    assert out["accepted"] is True and out["restored"] is False
    assert (tmp_path / "main.tex").read_text(encoding="utf-8") == "CHALLENGER WINS"


def test_reject_on_hard_fail_restores_incumbent(tmp_path):
    _make_manuscript(tmp_path)
    ref = cl.snapshot_incumbent(tmp_path, 1)
    (tmp_path / "main.tex").write_text("CHALLENGER LOSES", encoding="utf-8")
    out = cl.accept_or_restore(tmp_path, ref, _ev(hard=False), None)
    assert out["accepted"] is False and out["restored"] is True
    assert (tmp_path / "main.tex").read_text(encoding="utf-8") == "INCUMBENT BODY"


def test_reject_on_no_dominance_restores_incumbent(tmp_path):
    _make_manuscript(tmp_path)
    ref = cl.snapshot_incumbent(tmp_path, 1)
    (tmp_path / "main.tex").write_text("NO IMPROVEMENT", encoding="utf-8")
    # hard-passes but does not dominate a non-None incumbent (identical soft).
    incumbent = _ev(hard=True)
    challenger = _ev(hard=True)
    out = cl.accept_or_restore(tmp_path, ref, challenger, incumbent)
    assert out["accepted"] is False and out["restored"] is True
    assert (tmp_path / "main.tex").read_text(encoding="utf-8") == "INCUMBENT BODY"
