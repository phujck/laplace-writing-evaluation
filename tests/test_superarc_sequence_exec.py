"""The sequence bench: sandbox, byte-compare, typed residue, shared normalization.

Every candidate here is a REAL program run in the real sandbox — the defects
worth catching (an empty stdout scoring as a pass, an infinite loop hanging the
loop, an inherited token) only exist when the execution is the real one.
"""
from __future__ import annotations

import sys

import pytest

from laplace.research.superarc import sequence_exec as sx

FIB = "1,1,2,3,5,8,13,21"
BITS = "0,0,1,0,1,1,0,0,1"


def _printer(literal: str) -> str:
    return f"print({literal!r})"


# --------------------------------------------------------------------------- #
# normalize_answer — shared law for every arm
# --------------------------------------------------------------------------- #


def test_normalize_strips_comments_and_collapses_whitespace():
    raw = "  0, 1,\n 1,\t2   # the first four\n"
    assert sx.normalize_answer(raw) == "0,1,1,2"


def test_normalize_is_idempotent_and_total_on_empty():
    once = sx.normalize_answer("a(n) = a(n-1) + a(n-2)   # recurrence")
    assert sx.normalize_answer(once) == once == "a(n) = a(n-1) + a(n-2)"
    assert sx.normalize_answer("") == ""
    assert sx.normalize_answer(None) == ""
    assert sx.normalize_answer("   \n\t ") == ""


def test_normalize_does_not_treat_floor_division_as_a_comment():
    assert sx.normalize_answer("a(n)=n//2") == "a(n)=n//2"


def test_parse_and_format_round_trip_the_comma_convention():
    assert sx.parse_sequence(" 0 , 1 ,1 ") == ["0", "1", "1"]
    assert sx.parse_sequence("") == []
    assert sx.parse_sequence(None) == []
    assert sx.format_sequence([0, 1, 1]) == "0,1,1"


# --------------------------------------------------------------------------- #
# The gate
# --------------------------------------------------------------------------- #


def test_correct_candidate_passes_with_no_residue():
    v = sx.verify_candidate(_printer(FIB), FIB)
    assert v.passed is True
    assert v.residue is None
    assert v.answer == v.target == FIB
    assert v.execution["returncode"] == 0


def test_correct_candidate_may_compute_rather_than_print_a_literal():
    src = (
        "a, b = 1, 1\n"
        "out = []\n"
        "for _ in range(8):\n"
        "    out.append(a)\n"
        "    a, b = b, a + b\n"
        "print(','.join(str(x) for x in out))\n"
    )
    assert sx.verify_candidate(src, FIB).passed is True


def test_target_may_be_given_as_terms():
    v = sx.verify_candidate(_printer(FIB), [1, 1, 2, 3, 5, 8, 13, 21])
    assert v.passed is True


def test_trailing_whitespace_in_output_is_non_semantic():
    assert sx.verify_candidate(f"print('  {FIB}  \\n\\n')", FIB).passed is True


# --------------------------------------------------------------------------- #
# Anti-vacuity: no trace is a FAILURE, not zero divergences
# --------------------------------------------------------------------------- #


def test_no_output_candidate_fails_the_gate():
    src = "a, b = 1, 1\nfor _ in range(8):\n    a, b = b, a + b\n"
    v = sx.verify_candidate(src, FIB)
    assert v.passed is False
    assert v.residue["class"] == "no-output"
    assert v.residue["got_len"] == 0
    assert v.execution["returncode"] == 0  # exited clean and still FAILS


def test_whitespace_only_output_is_no_output():
    v = sx.verify_candidate("print('   ')", FIB)
    assert v.passed is False
    assert v.residue["class"] == "no-output"


def test_empty_target_never_passes_on_empty_output():
    v = sx.verify_candidate("pass", "")
    assert v.passed is False
    assert v.residue["class"] == "no-output"


def test_infinite_loop_times_out_cleanly():
    v = sx.verify_candidate("while True:\n    pass\n", FIB, timeout=2.0)
    assert v.passed is False
    assert v.residue["class"] == "timeout"
    assert v.execution["timed_out"] is True
    assert v.execution["duration_s"] < 30.0


def test_partial_output_before_timeout_is_still_a_timeout():
    src = (
        "import sys\n"
        "sys.stdout.write('1,1,')\n"
        "sys.stdout.flush()\n"
        "while True:\n"
        "    pass\n"
    )
    v = sx.verify_candidate(src, FIB, timeout=2.0)
    assert v.residue["class"] == "timeout"
    assert v.answer.startswith("1,1")


def test_crashing_candidate_yields_a_crash_residue_with_a_stderr_tail():
    v = sx.verify_candidate("raise ValueError('boom')", FIB)
    assert v.passed is False
    assert v.residue["class"] == "crash"
    assert "ValueError" in v.execution["stderr_tail"]
    assert v.execution["returncode"] != 0


# --------------------------------------------------------------------------- #
# Planted-wrong candidates -> the correct typed residue, per class
# --------------------------------------------------------------------------- #


def test_off_by_index_residue():
    v = sx.verify_candidate(_printer("1,2,3,5,8,13,21,34"), FIB)
    assert v.residue["class"] == "off-by-index"
    assert v.residue["index"] == 1
    assert (v.residue["got"], v.residue["expected"]) == ("2", "1")
    assert v.residue["detail"] == "shift 1"


def test_off_by_index_the_other_direction():
    v = sx.verify_candidate(_printer("0,1,1,2,3,5,8,13"), FIB)
    assert v.residue["class"] == "off-by-index"
    assert v.residue["detail"] == "shift -1"


def test_parity_flip_residue():
    flipped = ",".join("1" if t == "0" else "0" for t in BITS.split(","))
    v = sx.verify_candidate(_printer(flipped), BITS)
    assert v.residue["class"] == "parity-flip"
    assert v.residue["index"] == 0
    assert (v.residue["got"], v.residue["expected"]) == ("1", "0")


def test_scale_residue():
    v = sx.verify_candidate(_printer("2,2,4,6,10,16,26,42"), FIB)
    assert v.residue["class"] == "scale"
    assert v.residue["detail"] == "factor 2.0"


def test_wrong_tail_residue():
    v = sx.verify_candidate(_printer("1,1,2,3,5,9,14,23"), FIB)
    assert v.residue["class"] == "wrong-tail"
    assert v.residue["index"] == 5
    assert (v.residue["got"], v.residue["expected"]) == ("9", "8")


def test_short_output_indexes_the_executed_output_at_its_end():
    v = sx.verify_candidate(_printer("1,1,2,3"), FIB)
    assert v.residue["class"] == "wrong-tail"
    assert v.residue["index"] == v.residue["got_len"] == 4
    assert v.residue["got"] is None          # never a fabricated term
    assert v.residue["expected"] == "5"
    assert sx.check_residue_rows([v.residue]) == []


def test_overlong_output_diverges_at_the_target_end():
    v = sx.verify_candidate(_printer(FIB + ",34,55"), FIB)
    assert v.passed is False
    assert v.residue["index"] == 8
    assert v.residue["got"] == "34"
    assert v.residue["expected"] is None


def test_every_planted_class_is_in_the_closed_set():
    seen = {
        sx.verify_candidate(src, target).residue["class"]
        for src, target in (
            (_printer("1,2,3,5,8,13,21,34"), FIB),
            (_printer("2,2,4,6,10,16,26,42"), FIB),
            (_printer("1,1,2,3,5,9,14,23"), FIB),
            ("pass", FIB),
            ("raise SystemExit(3)", FIB),
        )
    }
    assert seen <= set(sx.RESIDUE_CLASSES)
    assert seen == {"off-by-index", "scale", "wrong-tail", "no-output", "crash"}


# --------------------------------------------------------------------------- #
# The classifier, directly (the order between shapes is load-bearing)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "got,expected,cls",
    [
        (["1"], ["2"], "wrong-tail"),                       # one term scales onto any other
        (["0", "1", "0"], ["0", "1", "0", "1"], "wrong-tail"),   # prefix beats the periodic shift
        (["1", "0", "1", "0"], ["0", "1", "0", "1"], "off-by-index"),  # shift beats the flip
        (["3", "6", "9"], ["1", "2", "3"], "scale"),
        (["0", "0", "0"], ["0", "0", "0"], "wrong-tail"),   # residual, never a pass
    ],
)
def test_classify_divergence_shapes(got, expected, cls):
    assert sx.classify_divergence(got, expected) == cls


def test_shift_search_is_capped_so_a_realignment_is_not_an_indexing_bug():
    expected = [str(i) for i in range(80)]
    near = expected[3:]
    far = expected[sx.MAX_INDEX_SHIFT + 4:]
    assert sx._shift_of(near, expected) == 3
    assert sx._shift_of(far, expected) is None
    assert sx.classify_divergence(far, expected) == "wrong-tail"


def test_classify_empty_output_is_no_output():
    assert sx.classify_divergence([], ["0", "1"]) == "no-output"


def test_scale_rejects_a_non_constant_factor_and_identity():
    assert sx._scale_factor(["2", "4", "7"], ["1", "2", "3"]) is None
    assert sx._scale_factor(["1", "2", "3"], ["1", "2", "3"]) is None
    assert sx._scale_factor(["0", "0"], ["0", "0"]) is None


def test_parity_flip_requires_every_term_flipped():
    assert sx._is_parity_flip(["1", "1", "0"], ["0", "0", "1"]) is True
    assert sx._is_parity_flip(["1", "0", "0"], ["0", "0", "1"]) is False
    assert sx._is_parity_flip(["2", "2"], ["0", "0"]) is False


# --------------------------------------------------------------------------- #
# Residue-row invariants (ported from check_residue.py)
# --------------------------------------------------------------------------- #


def test_residue_record_refuses_a_class_outside_the_closed_set():
    with pytest.raises(ValueError):
        sx.residue_record("almost-right", 0, ["1"], ["2"])


def test_check_residue_rows_flags_the_cap_forbidden_keys_and_bad_index():
    good = sx.residue_record("wrong-tail", 1, ["1", "9"], ["1", "8"])
    assert sx.check_residue_rows([good]) == []

    over = [dict(good) for _ in range(sx.MAX_RESIDUE_ROWS + 1)]
    assert any("exceeds cap" in e for e in sx.check_residue_rows(over))

    smuggled = dict(good, synthesis="the loop found a closed form")
    assert any("forbidden synthesis keys" in e for e in sx.check_residue_rows([smuggled]))

    unindexed = dict(good, index=9)
    assert any("does not index" in e for e in sx.check_residue_rows([unindexed]))

    classless = dict(good, **{"class": "vibes"})
    assert any("class missing/unknown" in e for e in sx.check_residue_rows([classless]))

    no_index = dict(good, index=None)
    assert any("no index" in e for e in sx.check_residue_rows([no_index]))


def test_execution_level_rows_are_allowed_to_carry_no_index():
    for cls in ("no-output", "timeout", "crash"):
        row = sx.residue_record(cls, None, [], ["0"])
        assert sx.check_residue_rows([row]) == []


# --------------------------------------------------------------------------- #
# The containment itself
# --------------------------------------------------------------------------- #


def test_environment_is_not_inherited(monkeypatch):
    monkeypatch.setenv("SUPERARC_SECRET", "leaked")
    res = sx.run_candidate("import os\nprint(','.join(sorted(os.environ)))")
    assert res.ok is True
    assert "SUPERARC_SECRET" not in res.stdout
    assert "LAPLACE_SANDBOX" in res.stdout


def test_candidate_cannot_import_the_engine_that_spawned_it():
    res = sx.run_candidate("import laplace\nprint('imported')")
    assert res.ok is False
    assert "ModuleNotFoundError" in res.stderr


def test_candidate_runs_in_a_fresh_directory_that_does_not_survive(tmp_path):
    res = sx.run_candidate("import os\nopen('side_effect.txt','w').write('x')\nprint(os.getcwd())")
    assert res.ok is True
    cwd = res.stdout.strip()
    assert cwd != str(tmp_path)
    assert not (tmp_path / "side_effect.txt").exists()


def test_workdir_is_honoured_when_the_caller_wants_the_leavings(tmp_path):
    d = tmp_path / "run-1"
    res = sx.run_candidate("open('side_effect.txt','w').write('x')\nprint('ok')", workdir=d)
    assert res.ok is True
    assert (d / "candidate.py").is_file()
    assert (d / "side_effect.txt").is_file()


def test_stdout_is_bounded_with_an_explicit_truncation_marker():
    src = f"print('9,' * {sx.STDOUT_LIMIT})"
    res = sx.run_candidate(src)
    assert res.stdout_truncated is True
    assert res.stdout.endswith(sx.TRUNCATION_MARKER)
    assert len(res.stdout) == sx.STDOUT_LIMIT + len(sx.TRUNCATION_MARKER)


def test_stderr_is_bounded_with_the_marker_prefixed():
    src = f"import sys\nsys.stderr.write('e' * {sx.STDERR_TAIL_LIMIT * 3})\n"
    res = sx.run_candidate(src)
    assert res.stderr_truncated is True
    assert res.stderr.startswith(sx.TRUNCATION_MARKER)
    assert len(res.stderr) == sx.STDERR_TAIL_LIMIT + len(sx.TRUNCATION_MARKER)


def test_a_truncated_answer_can_never_pass_the_gate():
    long_target = ",".join("1" for _ in range(sx.STDOUT_LIMIT))
    v = sx.verify_candidate(_printer(long_target), long_target)
    assert v.passed is False
    assert sx.TRUNCATION_MARKER in v.answer


def test_short_bounds_are_returned_untruncated():
    assert sx._bounded_stdout_head("0,1,1") == ("0,1,1", False)
    assert sx._bounded_stderr_tail("") == ("", False)


def test_sandbox_env_carries_no_parent_state(monkeypatch):
    monkeypatch.setenv("LAPLACE_STATE", "/somewhere/real")
    env = sx.sandbox_env()
    assert "LAPLACE_STATE" not in env
    assert env["PATH"]


@pytest.mark.skipif(sys.platform == "win32", reason="rlimit is POSIX-only")
def test_rlimit_clamp_is_built_on_posix():
    assert sx._rlimit_preexec(sx.EXEC_TIMEOUT_S) is not None


def test_memory_hog_is_a_crash_not_a_hang():
    # RLIMIT_AS turns runaway allocation into MemoryError; without the clamp the
    # wall clock still catches it, so the assertion is on the gate, not the OS.
    src = "x = bytearray(4 * 1024 * 1024 * 1024)\nprint('allocated')"
    v = sx.verify_candidate(src, FIB, timeout=6.0)
    assert v.passed is False
    assert v.residue["class"] in ("crash", "timeout", "no-output")


def test_sandbox_error_is_a_verdict_not_an_exception(monkeypatch):
    def _boom(*a, **k):
        raise OSError("no fork for you")

    monkeypatch.setattr(sx.subprocess, "run", _boom)
    v = sx.verify_candidate(_printer(FIB), FIB)
    assert v.passed is False
    assert v.residue["class"] == "crash"
    assert "OSError" in v.execution["error"]
