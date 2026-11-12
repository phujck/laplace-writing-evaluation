"""Scoped tests for scripts/close_checklist.py — a tmp fixture repo proving
each check's PASS/WARN/FAIL outcome, the VERDICT sentinel, and the exit code.

The fixture is a minimal stand-in repo (git-initialized, with stub
scripts/detect_recurrence.py and scripts/rotate_handoff.py so the tests aren't
coupled to those scripts' real, heavier logic) — only close_checklist.py's own
shelling-out-and-interpreting behavior is under test here.
"""
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "close_checklist.py"

spec = importlib.util.spec_from_file_location("close_checklist", SCRIPT)
close_checklist = importlib.util.module_from_spec(spec)
sys.modules["close_checklist"] = close_checklist
spec.loader.exec_module(close_checklist)

# drain_frictions is my co-file: import it the same importlib way so the drain's
# REPORT half can be unit-tested directly on a fixture ledger (no subprocess).
_DRAIN_SCRIPT = REPO / "scripts" / "drain_frictions.py"
_dspec = importlib.util.spec_from_file_location("drain_frictions", _DRAIN_SCRIPT)
drain_frictions = importlib.util.module_from_spec(_dspec)
sys.modules["drain_frictions"] = drain_frictions
_dspec.loader.exec_module(drain_frictions)

TODAY = "2026-07-12"
RED = "\U0001f534"  # 🔴 OPEN_STACK live marker


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "scripts").mkdir()
    # stub detect_recurrence.py: --check exits 0 (clean) by default
    (repo / "scripts" / "detect_recurrence.py").write_text(
        "import sys\n"
        "if '--check' in sys.argv:\n"
        "    sys.exit(0)\n"
        "import json\n"
        "print(json.dumps({'recurrence_count': 0, 'ledgers': []}))\n"
    )
    # stub rotate_handoff.py: prints a dry-run report with 0 rollable sections
    (repo / "scripts" / "rotate_handoff.py").write_text(
        "print('current size:          1,000 bytes')\n"
        "print('arrow sections roll: 0 (0 bytes)')\n"
    )
    (repo / "HANDOFF.md").write_text(
        f"# handoff\n\n## ⟶ NEXT SESSION AIM ({TODAY} — fixture) — LATEST\n",
        encoding="utf-8",  # the payload carries ⟶/— — cp1252 (no PYTHONUTF8) errors otherwise
    )
    (repo / "OPEN_STACK.md").write_text(f"# open stack\n\n## {TODAY} sweep\n\nall clear\n")
    (repo / f"SESSION_HANDOFF_{TODAY}_fixture.md").write_text("# session handoff\n")
    (repo / "EIGEN_DIARY.md").write_text("# diary\n")
    (repo / "holdout").mkdir()
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


@pytest.fixture
def clean_repo(tmp_path):
    return _init_repo(tmp_path)


def _names(checks):
    return [c.name for c in checks]


def _by_name(checks, name):
    return [c for c in checks if c.name == name]


# --------------------------------------------------------------- happy path
def test_all_green_yields_pass_and_rc0(clean_repo):
    checks = close_checklist.run_all(clean_repo, TODAY)
    ok, fails, warns = close_checklist._verdict(checks)
    assert ok, [(c.name, c.status, c.detail) for c in fails]
    assert fails == []

    rc = close_checklist.main(["--repo", str(clean_repo), "--today", TODAY])
    assert rc == 0


def test_sentinel_last_line_pass(clean_repo, capsys):
    rc = close_checklist.main(["--repo", str(clean_repo), "--today", TODAY])
    out = capsys.readouterr().out.strip().splitlines()
    assert out[-1].startswith("VERDICT=PASS")
    assert rc == 0


# --------------------------------------------------------------- git state
def test_git_state_pass_on_clean_tree(clean_repo):
    c = close_checklist.check_git_state(clean_repo)
    assert c.status == "PASS"


def test_git_state_warn_on_dirty_tree(clean_repo):
    (clean_repo / "scratch.txt").write_text("dirt")
    c = close_checklist.check_git_state(clean_repo)
    assert c.status == "WARN"
    assert "dirty" in c.detail


# --------------------------------------------------------------- recurrence
def test_recurrence_pass_when_check_exits_0(clean_repo):
    c = close_checklist.check_recurrence(clean_repo)
    assert c.status == "PASS"


def test_recurrence_warns_never_fails_when_check_exits_1(clean_repo):
    (clean_repo / "scripts" / "detect_recurrence.py").write_text(
        "import sys, json\n"
        "if '--check' in sys.argv:\n"
        "    sys.exit(1)\n"
        "print(json.dumps({'recurrence_count': 3, 'ledgers': ['a.jsonl']}))\n"
    )
    c = close_checklist.check_recurrence(clean_repo)
    assert c.status == "WARN"
    assert "3" in c.detail


def test_recurrence_warn_when_script_missing(clean_repo):
    (clean_repo / "scripts" / "detect_recurrence.py").unlink()
    c = close_checklist.check_recurrence(clean_repo)
    assert c.status == "WARN"


# ------------------------------------------------- portable paths (NTFS gate)
def test_portable_paths_pass_on_clean_tree(clean_repo):
    c = close_checklist.check_portable_paths(clean_repo)
    assert c.status == "PASS", c.detail


def test_portable_paths_fail_on_planted_colon(clean_repo):
    # a tracked path with an NTFS-illegal ':' — the exact break RW-...-001240 hit
    (clean_repo / "sec:abstract.json").write_text("{}", encoding="utf-8")
    _git(clean_repo, "add", "-A")
    c = close_checklist.check_portable_paths(clean_repo)
    assert c.status == "FAIL", c.detail
    assert "sec:abstract.json" in c.detail
    # it is allowed to gate the exit code, and does
    assert "portable_paths" in close_checklist.FAIL_ELIGIBLE
    rc = close_checklist.main(["--repo", str(clean_repo), "--today", TODAY])
    assert rc == 1


@pytest.mark.parametrize("ch", list(':*?"<>|'))
def test_portable_paths_fail_on_each_illegal_char(clean_repo, ch):
    (clean_repo / f"bad{ch}name.txt").write_text("x", encoding="utf-8")
    _git(clean_repo, "add", "-A")
    c = close_checklist.check_portable_paths(clean_repo)
    assert c.status == "FAIL", (ch, c.detail)


# ------------------------------------------------- durable_refs / seams / effect
def test_durable_refs_pass_when_script_exits_0(clean_repo):
    (clean_repo / "scripts" / "check_durable_refs.py").write_text("import sys\nsys.exit(0)\n")
    c = close_checklist.check_durable_refs(clean_repo)
    assert c.status == "PASS"


def test_durable_refs_fail_maps_to_warn_advisory(clean_repo):
    (clean_repo / "scripts" / "check_durable_refs.py").write_text(
        "print('VERDICT=FAIL hits=6 fail=6 warn=0')\n"
        "import sys\nsys.exit(1)\n"
    )
    c = close_checklist.check_durable_refs(clean_repo)
    assert c.status == "WARN"
    assert "advisory" in c.detail


def test_durable_refs_warn_when_script_missing(clean_repo):
    c = close_checklist.check_durable_refs(clean_repo)
    assert c.status == "WARN"


# ------------------------------------------------------------ F7: supersede_sweep gate
# AUDIT_2026-07-15 §B3: supersede_sweep.py's new --gate mode is wired in at the SAME
# WARN tier check_claim_checks uses (never FAIL_ELIGIBLE — FAIL-promotion is the
# author's later ruling). Shells out the same way check_durable_refs/check_claim_checks
# do; only --gate is ever invoked from here, never --fix.
def test_supersede_sweep_pass_when_gate_exits_0(clean_repo):
    (clean_repo / "scripts" / "supersede_sweep.py").write_text(
        "print('VERDICT=PASS unstamped=0')\nimport sys\nsys.exit(0)\n"
    )
    c = close_checklist.check_supersede_sweep(clean_repo)
    assert c.status == "PASS"
    assert "unstamped=0" in c.detail


def test_supersede_sweep_gate_fail_maps_to_warn_advisory(clean_repo):
    (clean_repo / "scripts" / "supersede_sweep.py").write_text(
        "print('VERDICT=FAIL unstamped=2 sites=X.md:3,Y.md:9')\nimport sys\nsys.exit(1)\n"
    )
    c = close_checklist.check_supersede_sweep(clean_repo)
    assert c.status == "WARN"
    assert "advisory" in c.detail
    assert "unstamped=2" in c.detail


def test_supersede_sweep_warn_when_script_missing(clean_repo):
    c = close_checklist.check_supersede_sweep(clean_repo)
    assert c.status == "WARN"


def test_supersede_sweep_invoked_with_gate_flag_only(clean_repo, monkeypatch):
    # the close must run bare --gate (never --fix, never --ruling/--all) — assert the
    # exact argv close_checklist shells out with.
    calls = []
    real_run = close_checklist._run

    def spy(cmd, cwd, timeout=120):
        calls.append(cmd)
        return real_run(cmd, cwd, timeout)

    (clean_repo / "scripts" / "supersede_sweep.py").write_text(
        "print('VERDICT=PASS unstamped=0')\n"
    )
    monkeypatch.setattr(close_checklist, "_run", spy)
    close_checklist.check_supersede_sweep(clean_repo)
    assert len(calls) == 1
    cmd = calls[0]
    assert cmd[-1] == "--gate"
    assert "--fix" not in cmd


def test_supersede_sweep_not_fail_eligible():
    assert "supersede_sweep" not in close_checklist.FAIL_ELIGIBLE


def test_supersede_sweep_present_in_run_all(clean_repo):
    assert "supersede_sweep" in _names(close_checklist.run_all(clean_repo, TODAY))


def test_seam_liveness_pass_when_no_warns(clean_repo):
    (clean_repo / "scripts" / "audit_silent_failures.py").write_text(
        "print('VERDICT=PASS warns=0')\n"
    )
    c = close_checklist.check_seam_liveness(clean_repo)
    assert c.status == "PASS"


def test_seam_liveness_warns_when_audit_reports_warns(clean_repo):
    (clean_repo / "scripts" / "audit_silent_failures.py").write_text(
        "print('VERDICT=PASS warns=4')\n"
    )
    c = close_checklist.check_seam_liveness(clean_repo)
    assert c.status == "WARN"
    assert "warns=4" in c.detail


def test_seam_liveness_never_fails(clean_repo):
    # even an audit that itself printed FAIL is only advisory here
    (clean_repo / "scripts" / "audit_silent_failures.py").write_text(
        "print('VERDICT=FAIL checks=1/7 reasons=x warns=2')\nimport sys\nsys.exit(1)\n"
    )
    c = close_checklist.check_seam_liveness(clean_repo)
    assert c.status == "WARN"


def test_effect_meter_pass_surfaces_summary_line(clean_repo):
    (clean_repo / "scripts" / "audit_effect_meter.py").write_text(
        "print('{}')\nprint()\nprint('N38 AUDIT-EFFECT METER  (repo: fixture)')\n"
        "print('judged pairs (distinct, latest-wins): 0')\n"
    )
    c = close_checklist.check_effect_meter(clean_repo)
    assert c.status == "PASS"
    assert "AUDIT-EFFECT METER" in c.detail


def test_effect_meter_never_warns_on_a_clean_run(clean_repo):
    # the measurement is surfaced as a reading, not a gate — a clean run is PASS
    (clean_repo / "scripts" / "audit_effect_meter.py").write_text(
        "print('N38 AUDIT-EFFECT METER  (repo: x)')\n"
    )
    c = close_checklist.check_effect_meter(clean_repo)
    assert c.status == "PASS"


def test_new_subchecks_not_fail_eligible():
    for name in ("durable_refs", "seam_liveness", "effect_meter"):
        assert name not in close_checklist.FAIL_ELIGIBLE


def test_new_subchecks_present_in_run_all(clean_repo):
    checks = close_checklist.run_all(clean_repo, TODAY)
    names = _names(checks)
    for name in ("durable_refs", "seam_liveness", "effect_meter"):
        assert name in names


# --------------------------------------------------------------- rotation
def test_rotation_pass_when_nothing_to_roll(clean_repo):
    c = close_checklist.check_rotation(clean_repo)
    assert c.status == "PASS"


def test_rotation_warns_when_sections_rollable(clean_repo):
    (clean_repo / "scripts" / "rotate_handoff.py").write_text(
        "print('current size:          300,000 bytes')\n"
        "print('arrow sections roll: 12 (100,000 bytes)')\n"
    )
    c = close_checklist.check_rotation(clean_repo)
    assert c.status == "WARN"
    assert "12" in c.detail


# --------------------------------------------------------------- handoff freshness
def test_handoff_freshness_pass_when_dated_today(clean_repo):
    c = close_checklist.check_handoff_freshness(clean_repo, TODAY)
    assert c.status == "PASS"


def test_handoff_freshness_fails_when_stale(clean_repo):
    c = close_checklist.check_handoff_freshness(clean_repo, "2026-07-13")
    assert c.status == "FAIL"


def test_handoff_freshness_fails_when_missing(tmp_path):
    repo = tmp_path / "no_handoff"
    repo.mkdir()
    c = close_checklist.check_handoff_freshness(repo, TODAY)
    assert c.status == "FAIL"


# --------------------------------------------------------------- session handoff dated
def test_session_handoff_dated_pass(clean_repo):
    c = close_checklist.check_session_handoff_dated(clean_repo, TODAY)
    assert c.status == "PASS"


def test_session_handoff_dated_fails_when_absent(clean_repo):
    c = close_checklist.check_session_handoff_dated(clean_repo, "2026-07-13")
    assert c.status == "FAIL"


# --------------------------------------------------------------- open stack sweep
# AUDIT_2026-07-15 §B2: a dated header alone used to PASS — "the sweep happened" and "the
# sweep was thorough" were mechanically indistinguishable. Now the section BODY must carry
# the typed `swept: complete` marker; an admitted deferral FAILs; a dated section stating
# neither WARNs (the unstated outcome). The base clean_repo fixture's OPEN_STACK.md ("##
# {TODAY} sweep\n\nall clear\n") deliberately carries neither token, so its own default
# read is now the WARN case — not a regression, the finding made mechanical.
def test_open_stack_sweep_warns_when_dated_but_completeness_unstated(clean_repo):
    c = close_checklist.check_open_stack_sweep(clean_repo, TODAY)
    assert c.status == "WARN"
    assert "completeness unstated" in c.detail
    assert "swept: complete" in c.detail


def test_open_stack_sweep_pass_when_swept_complete(clean_repo):
    (clean_repo / "OPEN_STACK.md").write_text(
        f"# open stack\n\n## {TODAY} sweep\n\nswept: complete — the full row-sweep ran.\n"
    )
    c = close_checklist.check_open_stack_sweep(clean_repo, TODAY)
    assert c.status == "PASS"
    assert "swept: complete" in c.detail


def test_open_stack_sweep_fails_when_body_admits_deferral(clean_repo):
    (clean_repo / "OPEN_STACK.md").write_text(
        f"# open stack\n\n## {TODAY} sweep (stretch-scoped; "
        "the full row-sweep deferred AGAIN, named)\n\n"
        "**Summary:** the stretch executed the arming whole; the full 71-row sweep "
        "is now TWO closes deferred — drift, carried loudly as next close's first debt.\n"
    )
    c = close_checklist.check_open_stack_sweep(clean_repo, TODAY)
    assert c.status == "FAIL"
    assert "deferred AGAIN" in c.detail
    assert "swept: complete" in c.detail


def test_open_stack_sweep_dated_but_deferred_is_never_pass(clean_repo):
    (clean_repo / "OPEN_STACK.md").write_text(
        f"# open stack\n\n## {TODAY} sweep\n\nthe row-sweep deferral stands again.\n"
    )
    c = close_checklist.check_open_stack_sweep(clean_repo, TODAY)
    assert c.status != "PASS"


def test_open_stack_sweep_fails_when_not_dated_today(clean_repo):
    c = close_checklist.check_open_stack_sweep(clean_repo, "2026-07-13")
    assert c.status == "FAIL"


def test_open_stack_sweep_fails_when_missing(tmp_path):
    repo = tmp_path / "no_stack"
    repo.mkdir()
    c = close_checklist.check_open_stack_sweep(repo, TODAY)
    assert c.status == "FAIL"


# --------------------------------------------------------------- instrument usage
def test_instrument_usage_pass_when_referenced(clean_repo):
    inst = clean_repo / f"PROXY_RESOLUTIONS_{TODAY}_v1.md"
    inst.write_text("resolutions\n")
    # reference it from the (same-date-or-later) session handoff
    sh = clean_repo / f"SESSION_HANDOFF_{TODAY}_fixture.md"
    sh.write_text(sh.read_text() + f"\nsee {inst.stem} for detail\n")
    checks = close_checklist.check_instrument_usage(clean_repo, TODAY)
    matches = _by_name(checks, "instrument_usage")
    assert any(c.status == "PASS" and inst.name in c.detail for c in matches)


def test_instrument_usage_warns_when_never_consumed(clean_repo):
    inst = clean_repo / f"DREAM_AUDIT_{TODAY}_orphan.md"
    inst.write_text("an instrument nobody read\n")
    checks = close_checklist.check_instrument_usage(clean_repo, TODAY)
    matches = _by_name(checks, "instrument_usage")
    warned = [c for c in matches if c.status == "WARN" and inst.name in c.detail]
    assert warned, [(c.status, c.detail) for c in matches]
    assert "never consumed" in warned[0].detail


def test_instrument_usage_ignores_files_older_than_last_handoff(clean_repo):
    # last dated handoff is TODAY; an older instrument is out of scope
    old = clean_repo / "DECISION_2026-07-01_old-call.md"
    old.write_text("an old, already-settled decision\n")
    checks = close_checklist.check_instrument_usage(clean_repo, TODAY)
    assert not any(old.name in c.detail for c in checks)


def test_instrument_usage_never_fails(clean_repo):
    (clean_repo / f"DECISION_{TODAY}_orphan.md").write_text("x\n")
    checks = close_checklist.check_instrument_usage(clean_repo, TODAY)
    assert all(c.status in ("PASS", "WARN") for c in checks)


# --------------------------------------------------------------- holdout
def test_holdout_pass_when_no_pending(clean_repo):
    c = close_checklist.check_holdout(clean_repo)
    assert c.status == "PASS"


# --------------------------------------------------------------- holdout
# WO-20260817-holdout-scores-deposit (the thin-systems audit 2026-08-17): check_holdout reads
# the wake's BANKED VERDICTS (holdout/LAST_SCORE.json), not file mtimes. The two mtime-era tests
# these replace could only ever assert WARN, because the mtime comparison had no other verdict
# to give — which was the defect.
def _bank_scorecard(repo, results, *, banked="2026-08-17T00:00:00"):
    (repo / "holdout" / "PREDICTION_pending.json").write_text(
        json.dumps({"banked": banked, "mechanical": []}), encoding="utf-8")
    (repo / "holdout" / "LAST_SCORE.json").write_text(
        json.dumps({"banked": banked, "scored_at": "2026-08-20T09:00:00",
                    "mechanical": results}), encoding="utf-8")


def test_holdout_warns_when_pending_but_never_scored(clean_repo):
    (clean_repo / "holdout" / "PREDICTION_pending.json").write_text("{}")
    c = close_checklist.check_holdout(clean_repo)
    assert c.status == "WARN"
    assert "LAST_SCORE.json absent" in c.detail


def test_holdout_warns_when_scorecard_grades_an_older_prediction(clean_repo):
    _bank_scorecard(clean_repo, [{"id": "p", "verdict": "PASS", "detail": "rc=0"}])
    (clean_repo / "holdout" / "PREDICTION_pending.json").write_text(
        json.dumps({"banked": "2026-08-19T00:00:00", "mechanical": []}), encoding="utf-8")
    c = close_checklist.check_holdout(clean_repo)
    assert c.status == "WARN"
    assert "awaiting its first scoring wake" in c.detail


def test_holdout_fails_when_a_check_actually_broke(clean_repo):
    """rc 1 = a graded fail: the surface the author held out actually broke. FAIL, and the only
    reason 'holdout' is FAIL_ELIGIBLE."""
    _bank_scorecard(clean_repo, [{"id": "sb-scroll-law", "verdict": "FAIL", "detail": "rc=1"}])
    c = close_checklist.check_holdout(clean_repo)
    assert c.status == "FAIL"
    assert "BREACHED" in c.detail and "sb-scroll-law" in c.detail


def test_holdout_warns_when_the_probe_refused_to_grade(clean_repo):
    """rc 3 = service_probe.REFUSAL_EXIT: playwright/browser/service absent. The probe could not
    probe, so this is UNRUNNABLE — WARN naming it, never a FAIL and never a pass."""
    _bank_scorecard(clean_repo, [{"id": "sb-scroll-law", "verdict": "FAIL", "detail": "rc=3"}])
    c = close_checklist.check_holdout(clean_repo)
    assert c.status == "WARN"
    assert "UNRUNNABLE" in c.detail


def test_holdout_warns_when_the_wall_could_not_pay(clean_repo):
    _bank_scorecard(clean_repo, [{"id": "sb-scroll-law", "verdict": "UNPAYABLE",
                                  "detail": "not run: floor 5s"}])
    c = close_checklist.check_holdout(clean_repo)
    assert c.status == "WARN"
    assert "UNPROVEN" in c.detail


def test_holdout_passes_when_every_check_held(clean_repo):
    _bank_scorecard(clean_repo, [{"id": "a", "verdict": "PASS", "detail": "rc=0"},
                                 {"id": "b", "verdict": "PASS", "detail": "rc=0"}])
    c = close_checklist.check_holdout(clean_repo)
    assert c.status == "PASS"
    assert "2 mechanical check(s) held" in c.detail


# --------------------------------------------------------- fork adjudication (proxy)
def _write_live_fork(repo, fork_line):
    (repo / "OPEN_STACK.md").write_text(
        f"# open stack\n\n## {TODAY} sweep\n\n## Stratum 1 — author-forks\n\n{fork_line}\n"
    )


def test_fork_adjudication_pass_when_no_live_forks(clean_repo):
    # the fixture OPEN_STACK has no 🔴 rows
    checks = close_checklist.check_fork_adjudication(clean_repo)
    assert all(c.status == "PASS" for c in checks)


def test_fork_adjudication_warns_on_unadjudicated_fork(clean_repo):
    _write_live_fork(clean_repo, f"- **F77 a parked fork — live {RED} ({TODAY})**: unfinished")
    # no proxy_verdicts.jsonl at all → nothing references F77
    checks = close_checklist.check_fork_adjudication(clean_repo)
    warned = [c for c in checks if c.status == "WARN" and "F77" in c.detail]
    assert warned, [(c.status, c.detail) for c in checks]
    assert "parked" in warned[0].detail


def test_fork_adjudication_pass_when_verdict_references_it(clean_repo):
    _write_live_fork(clean_repo, f"- **F77 an adjudicated fork — live {RED} ({TODAY})**: decided")
    (clean_repo / "proxy_verdicts.jsonl").write_text(
        json.dumps({"id": "PV-20260712-f77-x", "question": "F77 — close it?",
                    "confidence": "GENUINELY-HIS", "ruling": "closed"}) + "\n"
    )
    checks = close_checklist.check_fork_adjudication(clean_repo)
    assert any(c.status == "PASS" and "F77" in c.detail for c in checks)
    assert not any(c.status == "WARN" for c in checks)


def test_fork_adjudication_reads_table_format_too(clean_repo):
    _write_live_fork(
        clean_repo,
        f"| F88 | **a table fork** | {TODAY} | 2 | {RED} | notes |")
    checks = close_checklist.check_fork_adjudication(clean_repo)
    assert any("F88" in c.detail for c in checks)


# ------------------------------------------------- unseal follow-through (raw uncommitted)
def test_unseal_pass_when_no_soul_dump(clean_repo):
    c = close_checklist.check_unseal_follow_through(clean_repo)
    assert c.status == "PASS"


def test_unseal_warns_on_untracked_raw(clean_repo):
    dump = clean_repo / "archive" / "soul_dump"
    dump.mkdir(parents=True)
    (dump / "raw_dump.txt").write_text("the raw, present but uncommitted\n")
    c = close_checklist.check_unseal_follow_through(clean_repo)
    assert c.status == "WARN"
    assert "uncommitted" in c.detail


def test_unseal_pass_when_raw_is_tracked(clean_repo):
    dump = clean_repo / "archive" / "soul_dump"
    dump.mkdir(parents=True)
    (dump / "raw_dump.txt").write_text("the raw, now committed\n")
    _git(clean_repo, "add", "-A")
    _git(clean_repo, "commit", "-q", "-m", "commit the raw")
    c = close_checklist.check_unseal_follow_through(clean_repo)
    assert c.status == "PASS"


# --------------------------------------------------- new checks are advisory only
def test_new_proxy_checks_not_fail_eligible():
    for name in ("fork_adjudication", "unseal_follow_through"):
        assert name not in close_checklist.FAIL_ELIGIBLE


def test_new_proxy_checks_present_in_run_all(clean_repo):
    names = _names(close_checklist.run_all(clean_repo, TODAY))
    assert "fork_adjudication" in names
    assert "unseal_follow_through" in names


# ------------------------------------------------ graded-close beat gate (W5)
def test_close_beats_present_in_run_all(clean_repo):
    assert "close_beats" in _names(close_checklist.run_all(clean_repo, TODAY))


def test_close_beats_not_fail_eligible():
    assert "close_beats" not in close_checklist.FAIL_ELIGIBLE


def test_fail_eligible_set_unchanged():
    # the gate stays narrow: the missing-trace-artifact checks, portable_paths (the
    # NTFS-portability gate, RW-...-001240 — a tracked colon aborts a Windows checkout),
    # first_chair (THE FIRST-CHAIR CLAUSE, ARMING_2026-07-16 — a produced artefact that
    # would ship unread is the same trace-corruption class the close is allowed to gate on),
    # and contact_law (STANDING_LAW 2026-07-21b — a lying operating contract or an
    # evidence-free delivered promise is a corrupted trace; the close refuses it).
    # UPDATED TO CURRENT TRUTH (W-TRIAGE 2026-07-22): three later checks ARMED to
    # FAIL_ELIGIBLE in close_checklist.py — orphan_census (THE REAPER, PRM-20260721-liveness-law:
    # the orphan count cannot rise), scroll_law (THE SCROLL LAW, P10 as amended 2026-07-21), and
    # register_zero (the armed register gate). The pin was stale, not the src — the gate legitimately
    # grew teeth; this asserts the current armed set.
    assert close_checklist.FAIL_ELIGIBLE == {
        "handoff_freshness", "session_handoff_dated", "open_stack_sweep",
        "claude_md_render", "portable_paths", "first_chair", "contact_law",
        "orphan_census", "scroll_law", "register_zero",
        # W-TEETH (2026-07-22 night): the aging gate - an open row past its class age
        # without a dated, owned defer blocks the close (the ask-or-decide law made
        # mechanical).
        "aging_teeth",
        # THE THIN-SYSTEMS AUDIT (2026-08-17), three more armed: open_stack_render
        # (WO-20260817-openstack-render-close-gate — the banner the renderer stamps into
        # OPEN_STACK.md already STATES "Drift fails the close", and nothing ran it),
        # metric_currency (WO-20260817-restored-metric-honest-mtime — the metric-distill
        # gate's DECLINE was a print with no promotion path), and holdout
        # (WO-20260817-holdout-scores-deposit — the wake scored the author's verbatim
        # holdout, printed FAIL, and the close could only ever WARN off mtimes).
        "open_stack_render", "metric_currency", "holdout",
    }


def test_close_beats_returns_conforming_check(clean_repo):
    c = close_checklist.check_close_beats(clean_repo)
    assert isinstance(c, close_checklist.Check)
    assert c.name == "close_beats"
    assert c.status in ("PASS", "WARN")  # never FAIL — advisory only
    assert c.detail


def test_close_beats_warns_when_mark_unresolvable(clean_repo):
    # the fixture's SESSION_HANDOFF was added in the ROOT commit and no subject
    # marks a close, so no mark resolves -> gating unavailable, WARN, all fire.
    c = close_checklist.check_close_beats(clean_repo)
    assert c.status == "WARN"
    assert "gating unavailable" in c.detail


def test_close_beats_passes_and_lists_skipped_when_mark_resolves(clean_repo):
    # bank a close on top of the fixture's init so the mark resolves; nothing moved
    # since -> the diff-gated beats are skipped, reported as a PASS reading.
    (clean_repo / "EIGEN_DIARY.md").write_text("the trace\n")
    _git(clean_repo, "add", "-A")
    _git(clean_repo, "commit", "-q", "-m", f"sew up {TODAY} — the close")
    c = close_checklist.check_close_beats(clean_repo)
    assert c.status == "PASS"
    assert "beats fire" in c.detail
    assert "skipped:" in c.detail
    assert "architecture" in c.detail  # a gated beat with no moved source


# --------------------------------------------------------------- overall FAIL wiring
def test_missing_trace_artifacts_yields_fail_and_rc1(clean_repo):
    (clean_repo / f"SESSION_HANDOFF_{TODAY}_fixture.md").unlink()
    rc = close_checklist.main(["--repo", str(clean_repo), "--today", TODAY])
    assert rc == 1


def test_fail_sentinel_names_reasons(clean_repo, capsys):
    (clean_repo / f"SESSION_HANDOFF_{TODAY}_fixture.md").unlink()
    close_checklist.main(["--repo", str(clean_repo), "--today", TODAY])
    out = capsys.readouterr().out.strip().splitlines()
    last = out[-1]
    assert last.startswith("VERDICT=FAIL")
    assert "session_handoff_dated" in last


def test_warn_only_still_yields_pass_and_rc0(clean_repo):
    # a WARN-class problem (dirty tree) must not fail the whole run
    (clean_repo / "scratch.txt").write_text("dirt")
    rc = close_checklist.main(["--repo", str(clean_repo), "--today", TODAY])
    assert rc == 0


def test_json_output_is_valid_and_carries_sentinel(clean_repo, capsys):
    rc = close_checklist.main(["--repo", str(clean_repo), "--today", TODAY, "--json"])
    out = capsys.readouterr().out.strip().splitlines()
    assert out[-1].startswith("VERDICT=")
    body = "\n".join(out[:-1])
    parsed = json.loads(body)
    assert parsed["ok"] is True
    assert parsed["today"] == TODAY
    assert isinstance(parsed["checks"], list) and parsed["checks"]
    assert rc == 0


def test_never_writes_anything(clean_repo):
    before = {
        p: p.stat().st_mtime
        for p in clean_repo.rglob("*")
        if p.is_file() and ".git" not in p.parts
    }
    close_checklist.main(["--repo", str(clean_repo), "--today", TODAY])
    after = {
        p: p.stat().st_mtime
        for p in clean_repo.rglob("*")
        if p.is_file() and ".git" not in p.parts
    }
    assert before == after
    assert set(before) == set(after)


# ============================================================ C5.5 — the drain beat
# --------------------------- the drain's REPORT half reports counts on a fixture ledger
def _friction_ledger(tmp_path, rows):
    ledger = tmp_path / "corpus_friction" / "laplace_engine.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return ledger


def test_drain_report_counts_open_and_consumed_on_fixture_ledger(tmp_path):
    # two open frictions + one retired by an EVIDENCE-carrying resolution (consumed)
    ledger = _friction_ledger(tmp_path, [
        {"id": "FR-1", "record": "friction", "kind": "friction", "status": "open",
         "node": "a", "value": "x", "owning_layer": "scripts/foo"},
        {"id": "FR-2", "record": "friction", "kind": "friction", "status": "open",
         "node": "b", "value": "y", "owning_layer": "scripts/bar"},
        {"id": "FR-3", "record": "friction", "kind": "friction", "status": "open",
         "node": "c", "value": "z", "owning_layer": "scripts/baz"},
        {"id": "RES-1", "record": "resolution", "supersedes": "FR-3",
         "evidence": "commit abc123"},
    ])
    rep = drain_frictions.report(ledger, tmp_path)
    assert rep["ledger_found"] is True
    assert rep["open"] == 2          # FR-1, FR-2 (FR-3 retired by evidence-carrying RES-1)
    assert rep["consumed"] == 1      # FR-3
    assert rep["feedback_raw_append_total"] == 0


def test_drain_report_evidence_less_resolution_leaves_target_open(tmp_path):
    # a resolution with NO evidence must not count as consumption — target stays open
    ledger = _friction_ledger(tmp_path, [
        {"id": "FR-9", "record": "friction", "kind": "friction", "status": "open",
         "node": "n", "value": "v", "owning_layer": "scripts/q"},
        {"id": "RES-9", "record": "resolution", "supersedes": "FR-9", "evidence": ""},
    ])
    rep = drain_frictions.report(ledger, tmp_path)
    assert rep["open"] == 1
    assert rep["consumed"] == 0


def test_drain_report_tolerates_missing_ledger(tmp_path):
    rep = drain_frictions.report(tmp_path / "nope.jsonl", tmp_path)
    assert rep["ledger_found"] is False
    assert rep["open"] == 0 and rep["consumed"] == 0


# --------------------------- findings that exist SOLELY as raw FEEDBACK appends
def test_drain_report_counts_raw_feedback_only_findings(tmp_path):
    ledger = _friction_ledger(tmp_path, [])  # empty friction ledger
    fb = tmp_path / "manuscript" / "feedback" / "feedback.jsonl"
    fb.parent.mkdir(parents=True)
    fb.write_text("\n".join([
        # a POURED finding — carries the structured ``record`` stamp
        json.dumps({"id": "FB-1", "record": "finding", "kind": "citation-uncited",
                    "text": "poured through the door"}),
        # two RAW appends — the loop tier's {where, issue, fix} reply, no record
        json.dumps({"where": "fig:x", "issue": "raw scrawl", "fix": "..."}),
        json.dumps({"where": "fig:y", "issue": "another raw", "fix": "..."}),
        # a structured adjudication row — also has a ``record``, NOT a raw append
        json.dumps({"id": "C-1", "record": "confirmation", "supersedes": "FB-1"}),
        "{ this line is not valid json",  # an unparseable scrawl counts as raw
    ]) + "\n", encoding="utf-8")
    rep = drain_frictions.report(ledger, tmp_path)
    assert rep["feedback_raw_append_total"] == 3  # 2 record-less + 1 unparseable
    assert len(rep["feedback_raw_appends"]) == 1
    entry = rep["feedback_raw_appends"][0]
    assert entry["raw_appends"] == 3
    assert "feedback" in entry["file"]


def test_drain_report_clean_feedback_has_no_raw_appends(tmp_path):
    ledger = _friction_ledger(tmp_path, [])
    fb = tmp_path / "manuscript" / "feedback" / "feedback.jsonl"
    fb.parent.mkdir(parents=True)
    fb.write_text(
        json.dumps({"id": "FB-1", "record": "finding", "kind": "meta-leak",
                    "text": "all poured"}) + "\n", encoding="utf-8")
    rep = drain_frictions.report(ledger, tmp_path)
    assert rep["feedback_raw_append_total"] == 0
    assert rep["feedback_raw_appends"] == []


# --------------------------- the close beat wiring (advisory, WARN-only)
def test_friction_drain_present_in_run_all(clean_repo):
    assert "friction_drain" in _names(close_checklist.run_all(clean_repo, TODAY))


def test_friction_drain_not_fail_eligible():
    assert "friction_drain" not in close_checklist.FAIL_ELIGIBLE


def test_friction_drain_warns_when_script_missing(clean_repo):
    # the fixture repo has no scripts/drain_frictions.py -> graceful WARN, never FAIL
    c = close_checklist.check_friction_drain(clean_repo)
    assert c.status == "WARN"
    assert "not found" in c.detail


def test_friction_drain_surfaces_counts_and_warns_on_raw(tmp_path):
    # a fixture repo carrying a copy of the real drain script + a raw-append feedback
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    shutil.copy(_DRAIN_SCRIPT, repo / "scripts" / "drain_frictions.py")
    _friction_ledger(repo, [
        {"id": "FR-1", "record": "friction", "kind": "friction", "status": "open",
         "node": "a", "value": "x", "owning_layer": "scripts/foo"},
    ])
    fb = repo / "manuscript" / "feedback" / "feedback.jsonl"
    fb.parent.mkdir(parents=True)
    fb.write_text(json.dumps({"where": "fig:x", "issue": "raw", "fix": "y"}) + "\n",
                  encoding="utf-8")
    c = close_checklist.check_friction_drain(repo)
    assert c.status == "WARN"
    assert "1 open" in c.detail
    assert "SOLELY as raw FEEDBACK appends" in c.detail


def test_friction_drain_passes_when_no_raw(tmp_path):
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    shutil.copy(_DRAIN_SCRIPT, repo / "scripts" / "drain_frictions.py")
    _friction_ledger(repo, [
        {"id": "FR-1", "record": "friction", "kind": "friction", "status": "open",
         "node": "a", "value": "x", "owning_layer": "scripts/foo"},
    ])
    c = close_checklist.check_friction_drain(repo)
    assert c.status == "PASS"
    assert "1 open" in c.detail
    assert "no raw-FEEDBACK-only findings" in c.detail


# ============================================================ C5.5 — the grep-guard
def test_feedback_append_guard_greens_on_head():
    # the real workflows: only project-fixedpoint.js raw-appends, and it's whitelisted
    c = close_checklist.check_feedback_append_guard(REPO)
    assert c.status == "PASS", c.detail
    assert "whitelisted" in c.detail


def test_feedback_append_guard_not_fail_eligible():
    assert "feedback_append_guard" not in close_checklist.FAIL_ELIGIBLE


def test_feedback_append_guard_reds_on_synthetic_harnessed_append(tmp_path):
    # a tmp COPY of the harnessed-path file (NEVER mutate the real one), with a
    # synthetic raw FEEDBACK-append line added -> the guard must red LOUDLY.
    wf = tmp_path / ".claude" / "workflows"
    wf.mkdir(parents=True)
    src = REPO / ".claude" / "workflows" / "project-harnessed.js"
    dst = wf / "project-harnessed.js"
    shutil.copy(src, dst)
    dst.write_text(dst.read_text(encoding="utf-8")
                   + '\n// synthetic: append each finding to "${FEEDBACK}"\n',
                   encoding="utf-8")
    c = close_checklist.check_feedback_append_guard(tmp_path)
    assert c.status == "WARN"
    assert "project-harnessed.js" in c.detail
    assert "HARNESSED POUR PATH" in c.detail


def test_feedback_append_guard_whitelists_fixedpoint(tmp_path):
    # a lone copy of project-fixedpoint.js (its 3 lock-tier appends) must stay green
    wf = tmp_path / ".claude" / "workflows"
    wf.mkdir(parents=True)
    shutil.copy(REPO / ".claude" / "workflows" / "project-fixedpoint.js",
                wf / "project-fixedpoint.js")
    c = close_checklist.check_feedback_append_guard(tmp_path)
    assert c.status == "PASS"


def test_feedback_append_guard_warns_when_workflows_absent(tmp_path):
    c = close_checklist.check_feedback_append_guard(tmp_path)
    assert c.status == "WARN"
    assert "not found" in c.detail


def test_feedback_append_guard_present_in_run_all(clean_repo):
    assert "feedback_append_guard" in _names(close_checklist.run_all(clean_repo, TODAY))


# ---------------------------------------------- gitignore forward-law (W6.2, advisory)
import os as _os


def _commit(repo, msg, when=None):
    env = dict(_os.environ)
    if when:
        # `when` carries an explicit +00:00; TZ=UTC is the belt to that brace, so a
        # bare timestamp could never be resolved against /etc/localtime and shear.
        env["GIT_AUTHOR_DATE"] = when
        env["GIT_COMMITTER_DATE"] = when
        env["TZ"] = "UTC"
    subprocess.run(["git", "commit", "-q", "-m", msg], cwd=repo, check=True,
                   capture_output=True, env=env)


def _repo_with_mark(tmp_path):
    """A repo whose HEAD-1 is a resolvable 'sew up' mark (non-root), so a later commit's
    added .gitignore rules are diffable against it."""
    repo = _init_repo(tmp_path)  # root init commit
    (repo / "afile.txt").write_text("x\n")
    _git(repo, "add", "-A")
    _commit(repo, f"sew up {TODAY} — the mark", when="2026-07-12T10:00:00+00:00")
    return repo


def test_forward_law_flags_orphan_rule(tmp_path):
    """A .gitignore rule added since the mark with no rebuild lane (no comment, no ensure_state
    entry) WARNs — never FAILs; the check is not FAIL_ELIGIBLE."""
    repo = _repo_with_mark(tmp_path)
    (repo / ".gitignore").write_text(".mystery_cache.json\n")
    _git(repo, "add", "-A")
    _commit(repo, "add an ignore rule", when="2026-07-12T10:05:00+00:00")

    c = close_checklist.check_gitignore_forward_law(repo)
    assert c.status == "WARN"
    assert ".mystery_cache.json" in c.detail
    assert "733024" in c.detail  # cites the reserved-gate-shape fork
    assert "gitignore_forward_law" not in close_checklist.FAIL_ELIGIBLE


def test_forward_law_passes_rule_with_ensure_state_lane(tmp_path):
    """The same rule PASSES when a localstate.json entry names the path — it has a rebuild lane."""
    repo = _repo_with_mark(tmp_path)
    (repo / ".gitignore").write_text(".mystery_cache.json\n")
    (repo / "localstate.json").write_text(json.dumps({"version": 1, "entries": [
        {"name": "mystery", "cost": "cheap", "check": "test -f .mystery_cache.json",
         "rebuild": "python -m mint_mystery", "note": "rebuilds .mystery_cache.json"}]}))
    _git(repo, "add", "-A")
    _commit(repo, "add rule + its ensure_state lane", when="2026-07-12T10:05:00+00:00")

    c = close_checklist.check_gitignore_forward_law(repo)
    assert c.status == "PASS"


def test_forward_law_passes_rule_with_regen_comment(tmp_path):
    """A rule whose comment documents regen is reconstructable per surfacing_audit's taxonomy."""
    repo = _repo_with_mark(tmp_path)
    shutil.copy(REPO / "scripts" / "surfacing_audit.py", repo / "scripts" / "surfacing_audit.py")
    (repo / ".gitignore").write_text("# regenerable build cache, rebuilt at fold time\n.foo_cache\n")
    _git(repo, "add", "-A")
    _commit(repo, "add regenerable rule", when="2026-07-12T10:05:00+00:00")

    c = close_checklist.check_gitignore_forward_law(repo)
    assert c.status == "PASS"


def test_forward_law_pass_when_no_new_rules(tmp_path):
    """No .gitignore change since the mark -> PASS (nothing added)."""
    repo = _repo_with_mark(tmp_path)
    (repo / "note.txt").write_text("y\n")
    _git(repo, "add", "-A")
    _commit(repo, "unrelated change", when="2026-07-12T10:05:00+00:00")

    c = close_checklist.check_gitignore_forward_law(repo)
    assert c.status == "PASS"


def test_forward_law_skips_without_mark(clean_repo):
    """clean_repo's only close-marker is on the ROOT commit (skipped by last_banked_close), so
    the mark is unresolvable -> the advisory check skips honestly rather than flagging phantoms."""
    c = close_checklist.check_gitignore_forward_law(clean_repo)
    assert c.status == "PASS" and "skipped" in c.detail


# ============================================ the fence meter (DECISION_2026-08-17, step 2)
def _fence_ledger(repo, probe_hits):
    """Plant one banked probe row naming the given work-order ids on the fence's own
    ledger path, so the meter has something to diff the sweep's candidates against."""
    path = repo / "corpus_friction" / "fence_probes.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema": "fence.probe/1", "kind": "fence-probe", "id": "FP-20260817-01",
        "intent": "a fixture intent", "hits": [{"id": i} for i in probe_hits],
        "stamp": "2026-08-17T09:00:00Z",
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _sweep(ids, mark="2026-08-16T12:52:30+00:00", unavailable=""):
    """A faked landing-sweep finding: the close's real sweep reads the clock and the git
    log, and the meter under test is a pure function of the candidate ids it is handed."""
    return close_checklist.LandingCandidates(
        ids=list(ids),
        rows=[f"{i} [touched src/laplace/thing.py]" for i in ids],
        mark=mark,
        unavailable=unavailable,
    )


def test_fence_rate_present_in_run_all(clean_repo):
    assert "fence_rate" in _names(close_checklist.run_all(clean_repo, TODAY))


def test_fence_rate_not_fail_eligible(clean_repo):
    # WARN-tier by the decision's sequencing: FAIL waits on the store-faithfulness work
    # orders and then arrives per surface, so this row can never move the exit code.
    assert "fence_rate" not in close_checklist.FAIL_ELIGIBLE
    for c in _by_name(close_checklist.run_all(clean_repo, TODAY), "fence_rate"):
        assert c.status in ("PASS", "WARN")


def test_fence_rate_undefined_on_an_empty_denominator(clean_repo):
    """No landed candidate yet -> the rate is undefined and says so. A 0.0 here would read
    as a perfect score for a fence that has never been tested."""
    c = close_checklist.check_fence_rate(clean_repo, _sweep([]))
    assert c.status == "PASS"
    assert "undefined (no landed candidates yet)" in c.detail
    assert "0.0" not in c.detail


def test_fence_rate_names_caught_and_missed_ids(clean_repo):
    _fence_ledger(clean_repo, ["WO-caught-one"])
    c = close_checklist.check_fence_rate(
        clean_repo, _sweep(["WO-caught-one", "WO-missed-one"]))
    assert c.status == "WARN"
    assert "rate 0.5" in c.detail
    caught_half, missed_half = c.detail.split("missed:", 1)
    assert "WO-caught-one" in caught_half.split("caught:", 1)[1]
    assert "WO-missed-one" in missed_half
    assert "1 probe(s) banked" in c.detail


def test_fence_rate_passes_when_every_candidate_was_caught(clean_repo):
    _fence_ledger(clean_repo, ["WO-a", "WO-b"])
    c = close_checklist.check_fence_rate(clean_repo, _sweep(["WO-a", "WO-b"]))
    assert c.status == "PASS"
    assert "rate 0.0" in c.detail  # a real denominator, unlike the undefined case
    assert "missed: none" in c.detail


def test_fence_rate_warns_when_the_sweep_could_not_run(clean_repo):
    c = close_checklist.check_fence_rate(
        clean_repo, _sweep([], unavailable="git log unavailable: boom"))
    assert c.status == "WARN"
    assert "git log unavailable: boom" in c.detail


def test_fence_rate_banks_nothing(clean_repo):
    """The close is a pure reporter: the meter is called with no stamp, so the fence
    ledger it reads is byte-identical afterwards and no row is appended."""
    ledger = _fence_ledger(clean_repo, ["WO-a"])
    before = ledger.read_bytes()
    close_checklist.check_fence_rate(clean_repo, _sweep(["WO-a", "WO-b"]))
    assert ledger.read_bytes() == before


def test_one_sweep_feeds_both_the_census_and_the_meter(clean_repo, monkeypatch):
    """run_all walks the git log and the work-order ledger once: landing_sweep and
    fence_rate read the same candidate set."""
    calls = []
    real = close_checklist.landing_candidates

    def counted(repo):
        calls.append(repo)
        return real(repo)

    monkeypatch.setattr(close_checklist, "landing_candidates", counted)
    names = _names(close_checklist.run_all(clean_repo, TODAY))
    assert len(calls) == 1
    assert names.index("fence_rate") == names.index("landing_sweep") + 1


def test_fence_rate_names_a_missing_mark_never_no_candidates():
    # An empty mark with an empty unavailable is the no-banked-close /
    # mark-reader-could-not-run state (close_beats collapses both to None). The row
    # must name that state, not claim the sweep ran and found nothing.
    found = close_checklist.LandingCandidates([], [], "", "")
    check = close_checklist.check_fence_rate(Path("."), found)
    assert check.status == "PASS"
    assert "no banked close mark" in check.detail
    assert "no landed candidates yet" not in check.detail
