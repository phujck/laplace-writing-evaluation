"""Pure tests for scripts/run_claim_checks.py — one of each check class fed as a tmp AUDIT_*.md.

No network, no repo state: the corpus is a fixture written into tmp_path, so the assertions pin
the runner's classification (RUNNABLE vs PROSE, including the bare-`/` non-command), its evaluation
(→True pass, = N fail, EYE surfaced not judged), continuation folding, and exit semantics.
"""
import importlib.util
import sys
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "run_claim_checks",
    Path(__file__).resolve().parent.parent / "scripts" / "run_claim_checks.py",
)
rcc = importlib.util.module_from_spec(_SPEC)
sys.modules["run_claim_checks"] = rcc  # dataclass needs the module registered to resolve annotations
_SPEC.loader.exec_module(rcc)


# one of each class; the 4th check wraps onto a continuation line carrying a second backtick span.
FIXTURE = """# AUDIT test doc

### block
- CHECK: `python3 -c "print(True)"` → True
- CHECK: `python3 -c "print(1)"` = 2
- CHECK: `echo frozen` still says frozen.
- CHECK: `python3 -c "print(3)"` ≥ 2 AND
  `echo tail` and more prose.
- CHECK: no command here, stash and rerun reproduces the set.
- CHECK: every `/`-prefixed target resolves to a route.
"""


def _write(tmp_path: Path) -> Path:
    (tmp_path / "AUDIT_2099-01-01_fixture.md").write_text(FIXTURE, encoding="utf-8")
    return tmp_path


def test_classification_kinds(tmp_path):
    checks = rcc.collect(_write(tmp_path))
    assert [c.kind for c in checks] == [
        "RUNNABLE", "RUNNABLE", "RUNNABLE", "RUNNABLE", "PROSE", "PROSE"
    ]


def test_verdicts(tmp_path):
    checks = rcc.collect(_write(tmp_path))
    assert [c.verdict for c in checks] == [
        "PASS", "FAIL", "EYE", "PASS", "PROSE", "PROSE"
    ]


def test_continuation_folds_and_scopes_first_command(tmp_path):
    checks = rcc.collect(_write(tmp_path))
    wrapped = checks[3]
    # the continuation line folded into the text ...
    assert "echo tail" in wrapped.text
    # ... but the judged command is the first, and the ≥ 2 expectation is scoped before `echo tail`
    assert wrapped.command == 'python3 -c "print(3)"'
    assert wrapped.verdict == "PASS"


def test_bare_slash_backtick_is_prose(tmp_path):
    checks = rcc.collect(_write(tmp_path))
    assert checks[5].kind == "PROSE"
    assert checks[5].verdict == "PROSE"


def test_fail_output_captured(tmp_path):
    checks = rcc.collect(_write(tmp_path))
    fail = checks[1]
    assert fail.verdict == "FAIL"
    assert "1" in fail.output  # the command printed 1, the check expected = 2


def test_exit_nonzero_when_any_fail(tmp_path):
    _write(tmp_path)
    assert rcc.main(["--repo", str(tmp_path)]) == 1


def test_exit_zero_when_no_fail(tmp_path):
    # only a passing check + a prose line: no FAIL, exit 0
    (tmp_path / "AUDIT_2099-02-02_clean.md").write_text(
        "- CHECK: `python3 -c \"print(True)\"` → True\n"
        "- CHECK: no command, just prose.\n",
        encoding="utf-8",
    )
    assert rcc.main(["--repo", str(tmp_path)]) == 0


# --------------------------------------------------------------------------- shell-robustness
# "THE ENVIRONMENT IS PART OF THE CLAIM" (ARMING Appendix F). On Windows without Git's bin on
# PATH the old runner shelled every CHECK through `bash -c` and fabricated FAILs for checks that
# actually held. These pin the port: the common idioms (grep, python -c, test/&&/||) are evaluated
# NATIVELY and stay deterministic with no shell present; a genuinely-shell CHECK becomes an honest
# ENV, never a fabricated FAIL.

def _bash_absent(monkeypatch):
    """Simulate a Windows box with no bash/sh anywhere (and no Git-for-Windows bash on disk)."""
    real_which = rcc.shutil.which

    def fake_which(name, *a, **k):
        if name in ("bash", "sh"):
            return None
        return real_which(name, *a, **k)

    monkeypatch.setattr(rcc.shutil, "which", fake_which)
    monkeypatch.setattr(rcc.os.path, "isfile", lambda p: False)
    assert rcc._resolve_shell() is None  # the simulation actually took


# The three CHECK shapes that the old bash-only runner turned into false FAILs on Windows.
NATIVE_FIXTURE = """# AUDIT native
- CHECK: `grep -c 'alpha\\|beta' data.txt` = 2
- CHECK: `grep -n 'gamma' data.txt` resolves.
- CHECK: `python3 -c "print(True)"` → True
- CHECK: `test -f data.txt && echo True || echo False` → True
- CHECK: `python3 -c "print(2)"` = 2
"""


def _write_native(tmp_path):
    (tmp_path / "data.txt").write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
    (tmp_path / "AUDIT_2099-03-03_native.md").write_text(NATIVE_FIXTURE, encoding="utf-8")
    return tmp_path


def test_native_grep_count_no_shell(tmp_path, monkeypatch):
    _bash_absent(monkeypatch)
    checks = rcc.collect(_write_native(tmp_path))
    # `grep -c 'alpha\\|beta'` counts 2 lines natively (BRE \| alternation) — PASS, not a FAIL.
    assert checks[0].command == "grep -c 'alpha\\|beta' data.txt"
    assert checks[0].verdict == "PASS"


def test_native_grep_resolves_no_shell(tmp_path, monkeypatch):
    _bash_absent(monkeypatch)
    checks = rcc.collect(_write_native(tmp_path))
    # `grep -n 'gamma'` matches → rc 0 + non-empty → "resolves" PASS natively, no shell needed.
    assert checks[1].verdict == "PASS"


def test_native_python_and_test_no_shell(tmp_path, monkeypatch):
    _bash_absent(monkeypatch)
    checks = rcc.collect(_write_native(tmp_path))
    # python -c runs on the current interpreter (no shell); `test -f && echo || echo` is modelled.
    assert checks[2].verdict == "PASS"   # python3 -c print(True) → True
    assert checks[3].verdict == "PASS"   # test -f data.txt (exists) && echo True → True
    assert checks[4].verdict == "PASS"   # python3 -c print(2) = 2
    # not one fabricated FAIL across the native population with bash absent
    assert all(c.verdict != "FAIL" for c in checks)
    assert rcc.main(["--repo", str(tmp_path)]) == 0


def test_native_verdicts_identical_with_shell_present(tmp_path):
    # the same corpus, shell present: native handling gives the same verdicts (no regression).
    checks = rcc.collect(_write_native(tmp_path))
    assert [c.verdict for c in checks] == ["PASS", "PASS", "PASS", "PASS", "PASS"]


def test_genuinely_shell_check_is_env_not_fail(tmp_path, monkeypatch):
    # A CHECK that truly needs a shell (a redirect) cannot be modelled natively; with no shell it
    # must report ENV (honest "cannot evaluate here"), NEVER a fabricated FAIL, and must not move
    # the exit code.
    (tmp_path / "AUDIT_2099-04-04_shell.md").write_text(
        "- CHECK: `cat missing.txt > out.txt` → True\n", encoding="utf-8"
    )
    _bash_absent(monkeypatch)
    checks = rcc.collect(tmp_path)
    assert checks[0].kind == "RUNNABLE"
    assert checks[0].verdict == "ENV"
    assert rcc.main(["--repo", str(tmp_path)]) == 0  # ENV never moves the exit code


def test_genuinely_shell_check_runs_when_shell_present(tmp_path):
    # ... and when a shell IS present, the same genuinely-shell CHECK is actually run (here the
    # redirect makes `cat` of a missing file exit non-zero, so `→ True` legitimately FAILs).
    (tmp_path / "AUDIT_2099-04-04_shell.md").write_text(
        "- CHECK: `cat missing.txt > out.txt && echo True` → True\n", encoding="utf-8"
    )
    checks = rcc.collect(tmp_path)
    assert checks[0].verdict in ("FAIL", "ENV")  # shell present → FAIL; absent CI shell → ENV
    if rcc._resolve_shell() is not None:
        assert checks[0].verdict == "FAIL"


# --------------------------------------------------------------------------- classifier stability
# The classifier runs BEFORE any shell, so its verdict must be identical with or without bash on
# PATH — it can never be a bash-dependence artifact. A live check like the advisory `.git` size
# probe classified PROSE at HEAD because `du` is not a command-starter; the port must NOT silently
# flip that to a runnable EYE. `du`/`cut` stay modelled in _BUILTINS (for later pipeline stages)
# without being classifier entry points.

def test_du_cut_check_stays_prose(tmp_path):
    # the live AUDIT_2026-07-13 advisory: `du -sm .git | cut -f1` — PROSE at HEAD, must stay PROSE.
    (tmp_path / "AUDIT_2099-05-05_size.md").write_text(
        "- CHECK (EYE): `du -sm .git | cut -f1` — surfaces the current size.\n",
        encoding="utf-8",
    )
    checks = rcc.collect(tmp_path)
    assert checks[0].kind == "PROSE"
    assert checks[0].verdict == "PROSE"
    assert "du" not in rcc.COMMAND_STARTERS and "cut" not in rcc.COMMAND_STARTERS
    # but cut is still modelled natively as a downstream pipeline stage
    assert "cut" in rcc._BUILTINS and "du" in rcc._BUILTINS


def test_native_defect_is_not_masked_by_shell_fallback(monkeypatch, tmp_path):
    # A genuine handler bug (TypeError, not a modelling gap) must propagate, not be swallowed into a
    # silent shell fallback. _run_simple catches only the parse-shaped exceptions.
    def buggy(argv, stdin, repo):
        raise TypeError("native-engine defect")

    monkeypatch.setitem(rcc._BUILTINS, "grep", buggy)
    import pytest  # local import: only this test needs it
    with pytest.raises(TypeError):
        rcc._run_simple("grep foo bar.txt", None, tmp_path)
