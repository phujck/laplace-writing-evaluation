"""Scoped tests for scripts/sewup.py's step_canon — the N=0 collapse fix.

verify(..., checks=["canon"])["passed"] can be True, False, or None (0
decidable checks, all manual). step_canon must not fold None into a pass.
"""
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sewup.py"

spec = importlib.util.spec_from_file_location("sewup", SCRIPT)
sewup = importlib.util.module_from_spec(spec)
sys.modules["sewup"] = sewup
spec.loader.exec_module(sewup)


def _stub_verify(monkeypatch, passed, summary="stub summary"):
    def fake_verify(path, checks=None):
        return {"passed": passed, "summary": summary}
    monkeypatch.setattr("laplace.pipeline.verify.verify", fake_verify)


def test_step_canon_none_is_warn_not_pass(monkeypatch):
    _stub_verify(monkeypatch, None)
    res = sewup.step_canon()
    assert res["pass"] is None
    assert res["pass"] is not True
    assert res["verdict"] == "WARN"
    assert "UNVERIFIED" in res["detail"]
    assert "stub summary" in res["detail"]


def test_step_canon_false_still_fails(monkeypatch):
    _stub_verify(monkeypatch, False)
    res = sewup.step_canon()
    assert res["pass"] is False
    assert "verdict" not in res


def test_step_canon_true_still_passes(monkeypatch):
    _stub_verify(monkeypatch, True)
    res = sewup.step_canon()
    assert res["pass"] is True
    assert "verdict" not in res


def test_step_custody_gates_both_fabric_cursor_and_blueprint_travel(monkeypatch):
    from laplace.representation import atlas_bridge

    monkeypatch.setattr(atlas_bridge, "snapshot", lambda: {"provider": {
        "active_context": {"assumption": "atlas", "fibre": "s1"},
        "seat_cursors": {"codex-seat": []},
        "messages": {},
    }})
    monkeypatch.setattr(atlas_bridge, "blueprint_custody_projection", lambda: {
        "status": "sealed-hived-authority",
        "authoritative_path_count": 9,
        "all_authority_tracked": True,
    })

    result = sewup.step_custody()

    assert result["pass"] is True
    assert result["blueprint_custody"]["all_authority_tracked"] is True
    assert "authority_paths=9 tracked=yes" in result["detail"]

    monkeypatch.setattr(
        atlas_bridge,
        "blueprint_custody_projection",
        lambda: (_ for _ in ()).throw(RuntimeError("hive absent from index")),
    )
    refused = sewup.step_custody()
    assert refused["pass"] is False
    assert "hive absent from index" in refused["detail"]


def test_step_bench_separates_engineering_fail_from_judging_debt(monkeypatch):
    output = """\
  sb1-runs                   PASS           ran
  sb1-partition              FAIL           partition broke
  sb1-wants-typed            AWAITING-JUDGE sealed sample belongs to judge
SB-1-account-one-call: RED

[close-2026-08-25] 0/1 probes GREEN
"""
    monkeypatch.setattr(sewup, "DRY_RUN", False)
    monkeypatch.setattr(sewup, "_run", lambda *args, **kwargs: (1, output))

    result = sewup.step_bench()

    assert result["pass"] is True
    assert result["check_counts"] == {"PASS": 1, "FAIL": 1, "AWAITING-JUDGE": 1}
    assert "FAIL=1 AWAITING-JUDGE=1" in result["detail"]


def test_step_bench_refuses_red_headline_without_typed_check_statuses(monkeypatch):
    monkeypatch.setattr(sewup, "DRY_RUN", False)
    monkeypatch.setattr(
        sewup,
        "_run",
        lambda *args, **kwargs: (1, "[close-2026-08-25] 1/8 probes GREEN\n"),
    )

    result = sewup.step_bench()

    assert result["pass"] is False
    assert "cannot be distinguished" in result["detail"]


# --------------------------------------------------------------------------- #
# step_suite — the banked known-red baseline law (named 2026-07-15, landed
# 2026-07-19): a canonical tree carries documented reds, so flat rc==0 is a
# false FAIL on every real close. Pass = no NEW red outside the named set.
# --------------------------------------------------------------------------- #

_PYTEST_OUT = """\
FAILED tests/test_known.py::test_documented_red
FAILED tests/test_other.py::test_second_documented_red
2 failed, 100 passed in 1.0s
"""


def _stub_suite(monkeypatch, tmp_path, out, code, baseline=None):
    monkeypatch.setattr(sewup, "_run", lambda cmd, timeout=3600, env=None, **kwargs: (code, out))
    bpath = tmp_path / "suite_baseline.json"
    if baseline is not None:
        import json as _json
        bpath.write_text(_json.dumps({"failed": baseline}), encoding="utf-8")
    monkeypatch.setattr(sewup, "BASELINE_PATH", bpath)
    monkeypatch.setattr(sewup, "SUITE_IMPACTED", True)
    # Exercise the opt-in impacted selector and its historical baseline law; it
    # consults a shard map and APPENDS a typed run row. Point both at a scratch tree:
    # pointed at the repo, these stubs wrote fabricated greens into the live instrument
    # (`corpus_friction/suite_runs.jsonl`) — and a fabricated green is a false `since`
    # for the next real close. An empty tree also has no banked green, so the plan is
    # FULL and these cases keep the exact semantics they were written for.
    monkeypatch.setattr(sewup, "SUITE_ROOT", tmp_path / "scratch_root")
    (tmp_path / "scratch_root").mkdir(exist_ok=True)


def test_step_suite_passes_on_the_exact_banked_baseline(monkeypatch, tmp_path):
    """rc!=0 with only documented reds is a PASS — the baseline law."""
    _stub_suite(monkeypatch, tmp_path, _PYTEST_OUT, 1, baseline=[
        "tests/test_known.py::test_documented_red",
        "tests/test_other.py::test_second_documented_red"])
    res = sewup.step_suite()
    assert res["pass"] is True
    assert res["baseline"]["new"] == [] and res["baseline"]["cleared"] == []


def test_step_suite_fails_on_a_new_red(monkeypatch, tmp_path):
    """One red outside the named set fails the close and NAMES it."""
    _stub_suite(monkeypatch, tmp_path, _PYTEST_OUT, 1, baseline=[
        "tests/test_known.py::test_documented_red"])
    res = sewup.step_suite()
    assert res["pass"] is False
    assert res["baseline"]["new"] == ["tests/test_other.py::test_second_documented_red"]
    assert "NEW reds" in res["detail"]


def test_step_suite_banks_reds_before_display_truncation(monkeypatch, tmp_path):
    """Exercise the real _run boundary and read the evidence back from disk."""
    from laplace.engine import suite_map as sm

    real_run = sewup._run
    _stub_suite(monkeypatch, tmp_path, "", 1, baseline=[])
    monkeypatch.setattr(sewup, "_run", real_run)
    _stub_plan(monkeypatch, {"mode": "impacted", "selected": ["tests/test_planted.py"],
                             "moved": 1, "chain_depth": 0})
    reds = [{"id": f"tests/test_planted.py::test_red[{i} with spaces]",
             "diagnostic": f"AssertionError: planted failure {i}"} for i in range(56)]
    reds.append({"id": reds[0]["id"], "diagnostic": "RuntimeError: teardown failed"})
    output = "================ short test summary info ================\n"
    output += "\n".join(
        f"{'ERROR' if i == 56 else 'FAILED'} {red['id']} - {red['diagnostic']}"
        for i, red in enumerate(reds))
    output += "\n56 failed, 1 error in 1.0s\n"
    assert reds[0]["diagnostic"] not in output[-2000:]
    seen = []

    def fake_subprocess(cmd, **kwargs):
        seen.append(cmd)
        return sewup.subprocess.CompletedProcess(cmd, 1, stdout=output, stderr="")

    monkeypatch.setattr(sewup.subprocess, "run", fake_subprocess)
    result = sewup.step_suite()
    row = json.loads((sewup.SUITE_ROOT / sm.RUNS_REL).read_text().splitlines()[-1])
    assert row["reds"] == reds == result["suite_run"]["reds"]
    assert row["new_reds"] == sorted({red["id"] for red in reds})
    assert result["pass"] is False
    assert len(result["detail"]) <= 2000
    assert "-rfE" in seen[0] and "-vv" in seen[0] and "--color=no" in seen[0]
    assert real_run(["display-only"])[1] == output[-2000:]


def test_step_suite_reports_cleared_reds_as_improvement(monkeypatch, tmp_path):
    """A baseline red that now passes is improvement, reported for a deliberate
    re-stamp — never auto-shrunk, never a FAIL."""
    _stub_suite(monkeypatch, tmp_path, "1 failed, 101 passed in 1.0s\nFAILED tests/test_known.py::test_documented_red\n", 1,
                baseline=["tests/test_known.py::test_documented_red",
                          "tests/test_gone.py::test_now_green"])
    res = sewup.step_suite()
    assert res["pass"] is True
    assert res["baseline"]["cleared"] == ["tests/test_gone.py::test_now_green"]
    assert "re-stamp" in res["detail"]


def test_step_suite_no_baseline_falls_back_to_flat_floor(monkeypatch, tmp_path):
    """Missing baseline file: the old rc==0 floor, with the gap named."""
    _stub_suite(monkeypatch, tmp_path, _PYTEST_OUT, 1, baseline=None)
    res = sewup.step_suite()
    assert res["pass"] is False
    assert "no banked baseline" in res["detail"]


# --------------------------------------------------------------------------- #
# step_suite — the did-it-run gate. The baseline law reads "FAILED " lines, and
# a run that crashed before the tests emits none, so an ERRORed suite used to
# parse as zero reds: PASS, plus advice to re-stamp the whole banked set as
# "cleared". The run must now prove it happened (rc in (0,1) AND a pytest result
# summary) before its output means anything.
# --------------------------------------------------------------------------- #

_BASELINE = ["tests/test_known.py::test_documented_red",
             "tests/test_other.py::test_second_documented_red"]


def test_step_suite_collection_error_is_not_a_pass(monkeypatch, tmp_path):
    """A conftest ImportError (rc 4) emits no FAILED lines — it must FAIL, and
    must not advise re-stamping the baseline it never tested."""
    out = ("ImportError while loading conftest '/repo/tests/conftest.py'.\n"
           "E   ModuleNotFoundError: No module named 'nowhere'\n")
    _stub_suite(monkeypatch, tmp_path, out, 4, baseline=_BASELINE)
    res = sewup.step_suite()
    assert res["pass"] is False
    assert "DID NOT RUN" in res["detail"] and "rc=4" in res["detail"]
    assert "ModuleNotFoundError" in res["detail"]
    assert "re-stamp" not in res["detail"]
    assert "baseline" not in res


def test_step_suite_internal_error_is_not_a_pass(monkeypatch, tmp_path):
    """A plugin/internal crash (rc 3) likewise."""
    _stub_suite(monkeypatch, tmp_path,
                "INTERNALERROR> RuntimeError: plugin exploded\n", 3,
                baseline=_BASELINE)
    res = sewup.step_suite()
    assert res["pass"] is False
    assert "DID NOT RUN" in res["detail"] and "rc=3" in res["detail"]


def test_step_suite_missing_pytest_is_not_a_pass(monkeypatch, tmp_path):
    """rc 1 with no summary: the interpreter has no pytest. The rc alone can't
    tell this from 'documented reds' — the missing summary can."""
    _stub_suite(monkeypatch, tmp_path,
                "/usr/local/bin/python3: No module named pytest\n", 1,
                baseline=_BASELINE)
    res = sewup.step_suite()
    assert res["pass"] is False
    assert "DID NOT RUN" in res["detail"]


def test_step_suite_nothing_collected_is_not_a_pass(monkeypatch, tmp_path):
    """rc 5, no tests collected: an empty run is not a green run."""
    _stub_suite(monkeypatch, tmp_path, "no tests ran in 0.01s\n", 5,
                baseline=_BASELINE)
    res = sewup.step_suite()
    assert res["pass"] is False
    assert "DID NOT RUN" in res["detail"] and "rc=5" in res["detail"]


def test_step_suite_did_not_run_gate_precedes_the_baseline_read(monkeypatch, tmp_path):
    """No banked baseline either: a crashed run still reports the crash, not the
    flat-floor message — the gate is upstream of both verdict paths."""
    _stub_suite(monkeypatch, tmp_path, "INTERNALERROR> boom\n", 3, baseline=None)
    res = sewup.step_suite()
    assert res["pass"] is False
    assert "DID NOT RUN" in res["detail"]
    assert "no banked baseline" not in res["detail"]


def test_step_suite_green_run_still_passes(monkeypatch, tmp_path):
    """The gate does not over-fire: an all-green run (rc 0) reads normally."""
    _stub_suite(monkeypatch, tmp_path, "102 passed in 1.0s\n", 0, baseline=[])
    res = sewup.step_suite()
    assert res["pass"] is True
    assert res["baseline"]["red_now"] == 0


def test_step_suite_expected_failures_only_still_passes(monkeypatch, tmp_path):
    """A run whose summary names only xfails is a real run, not a crash."""
    _stub_suite(monkeypatch, tmp_path, "3 xfailed in 1.0s\n", 0, baseline=[])
    res = sewup.step_suite()
    assert res["pass"] is True


# --------------------------------------------------------------------------- #
# step_suite — impacted-only selection (WO-20260820-test-what-moved, his ask:
# "why test what hasn't moved?"). The suite-level conjugate of the wake's
# inherit-on-clean law. What must hold: the selected files are what runs, a
# delta that reaches no test inherits its green without spawning pytest, a
# selector blow-up widens to the full suite rather than narrowing the run, and
# a partial run may never report a baseline red as CLEARED.
# --------------------------------------------------------------------------- #


def _stub_plan(monkeypatch, plan: dict):
    from laplace.engine import suite_map as sm
    monkeypatch.setattr(sm, "plan", lambda root, **kw: plan)


def test_step_suite_impacted_runs_only_the_selected_files(monkeypatch, tmp_path):
    seen: list[list[str]] = []
    _stub_suite(monkeypatch, tmp_path, "5 passed in 1.0s\n", 0, baseline=[])
    monkeypatch.setattr(sewup, "_run",
                        lambda cmd, timeout=3600, env=None, **kwargs: (seen.append(cmd), (0, "5 passed in 1.0s\n"))[1])
    _stub_plan(monkeypatch, {"mode": "impacted", "selected": ["tests/test_a.py"],
                             "full_reasons": [], "moved": 3, "since": "abc1234def",
                             "chain_depth": 2, "head": "deadbeef", "uncovered": [],
                             "unclassified": [], "map_state": "banked",
                             "map_counts": {"tests": 300}})
    res = sewup.step_suite()
    assert res["pass"] is True
    assert seen[0][-1] == "tests/test_a.py"
    assert "1/300 shards" in res["detail"]
    assert res["suite_run"]["mode"] == "impacted" and res["suite_run"]["chain_depth"] == 3
    assert isinstance(res["suite_run"]["wall_s"], float)


def test_step_suite_runs_parallel_on_cores_with_blas_pinned(monkeypatch, tmp_path):
    """One worker per PHYSICAL core, each with a single BLAS/OMP thread.

    ``-n auto`` takes the hyperthreads too and every worker then sizes its own BLAS
    pool to the whole machine; the close measured that as slower than serial, and
    then as a SIGKILL. The row banks the worker count beside the wall time, because a
    time without its width cannot be compared to the serial baseline.
    """
    seen: dict = {}
    _stub_suite(monkeypatch, tmp_path, "5 passed in 1.0s\n", 0, baseline=[])
    monkeypatch.setattr(sewup, "_run",
                        lambda cmd, timeout=3600, env=None, **kwargs:
                        (seen.update(cmd=cmd, env=env), (0, "5 passed in 1.0s\n"))[1])
    monkeypatch.setattr(sewup, "_physical_cores", lambda: 8)
    _stub_plan(monkeypatch, {"mode": "full", "selected": [], "full_reasons": ["--full"],
                             "moved": 0, "since": None, "chain_depth": 0,
                             "head": "deadbeef", "uncovered": [], "unclassified": [],
                             "map_state": "banked", "map_counts": {"tests": 300}})
    res = sewup.step_suite()
    assert ["-n", "8", "--dist", "loadgroup"] == seen["cmd"][-4:]
    assert seen["env"]["OMP_NUM_THREADS"] == "1"
    assert seen["env"]["OPENBLAS_NUM_THREADS"] == seen["env"]["MKL_NUM_THREADS"] == "1"
    assert res["suite_run"]["workers"] == 8
    assert res["suite_run"]["thread_pin"] is True


def test_only_selects_steps_in_both_spellings(monkeypatch, capsys):
    """`--only suite` must run the suite, not the whole close.

    The space form is the documented one, and it parsed to None — so a request for one
    step ran all twelve, reembed and handoff included. Caught by a proof run that spent
    eleven minutes doing a close nobody asked for.
    """
    ran: list[str] = []
    monkeypatch.setattr(
        sewup, "_execute_step",
        lambda name, **_kw: (ran.append(name), {"pass": True, "status": "PASS",
                                                "detail": "test", "seconds": 0.0, "checkpoint": {}})[1])
    for argv, expected in ((["--only", "suite"], ["suite"]),
                           (["--only=suite,canon"], ["suite", "canon"]),
                           (["--only"], [])):
        ran.clear()
        sewup.main([*argv, "--dry-run"])
        assert ran == expected, argv
    ran.clear()
    sewup.main(["--dry-run"])
    # The bounded close is the default since WO-20260825-bounded-delta-close: the
    # suite's delta door + custody/git + authored seam. Computational organs ride
    # behind --all-steps or --only.
    assert ran == list(sewup.CORE_STEPS), "no --only means the CORE close"
    ran.clear()
    sewup.main(["--all-steps", "--dry-run"])
    assert ran == list(sewup.STEPS), "--all-steps is the whole close"
    capsys.readouterr()


def test_default_manifest_has_no_unconditional_heavy_organs():
    assert sewup.CORE_STEPS == ("handoff", "reembed")
    assert set(sewup.CORE_STEPS) & sewup.HEAVY_STEPS == {"reembed"}
    assert set(sewup.STEPS) == set(sewup.STEP_BUDGETS)






def test_only_custody_inert_exits_zero(monkeypatch, capsys):
    from laplace.representation import custody_mode

    monkeypatch.setattr(custody_mode, "is_off", lambda root: True)
    monkeypatch.setattr(custody_mode, "read", lambda root: {
        "mode": "OFF", "since": "today", "by": "test", "reason": "offline",
        "reintegration_trigger": "live seats",
    })
    monkeypatch.setattr(sewup, "_execute_step", lambda *_a, **_kw: {
        **sewup._typed_step_result(sewup.step_custody()), "seconds": 0.0,
    })
    assert sewup.main(["--only", "custody", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert '"status": "INERT"' in out
    assert '"pass": true' in out


def test_inert_is_explicit_and_cannot_claim_measured_truth():
    assert sewup._typed_step_result({"verdict": "INERT"})["status"] == "INERT"
    assert sewup._typed_step_result({"pass": None})["status"] == "UNPAYABLE"
    assert sewup._typed_step_result({"verdict": "INERT", "pass": True})["status"] == "FAIL"












def test_bounded_impacted_refuses_a_full_suite_without_spawning_pytest(monkeypatch, tmp_path):
    from laplace.engine import suite_map as sm

    monkeypatch.setattr(sewup, "BOUNDED_DEFAULT", True)
    monkeypatch.setattr(sewup, "SUITE_IMPACTED", True)
    monkeypatch.setattr(sewup, "SUITE_ROOT", tmp_path)
    monkeypatch.setattr(sm, "MAP_REL", "suite-map.json")
    monkeypatch.setattr(sm, "fingerprint", lambda _root: "sha256:fresh")
    (tmp_path / "suite-map.json").write_text(json.dumps({
        "version": sm.SCHEMA_VERSION, "fingerprint": "sha256:fresh",
    }))
    monkeypatch.setattr(sm, "plan", lambda *_a, **_kw: {
        "mode": "full", "selected": [], "full_reasons": ["documentation is unclassified"],
        "moved": 1, "since": "abc", "chain_depth": 0, "head": "def",
        "uncovered": [], "unclassified": ["notes.md"], "map_state": "banked",
        "map_counts": {"tests": 300}, "moved_paths": ["notes.md"],
    })
    monkeypatch.setattr(sewup, "_run", lambda *_a, **_kw: pytest.fail("pytest must not spawn"))
    res = sewup.step_suite()
    assert res["pass"] is None and res["status"] == "UNPAYABLE"
    assert "not launched by default close" in res["detail"]


def test_bounded_impacted_does_not_rebuild_a_stale_suite_map(monkeypatch, tmp_path):
    from laplace.engine import suite_map as sm

    monkeypatch.setattr(sewup, "BOUNDED_DEFAULT", True)
    monkeypatch.setattr(sewup, "SUITE_IMPACTED", True)
    monkeypatch.setattr(sewup, "SUITE_ROOT", tmp_path)
    monkeypatch.setattr(sm, "MAP_REL", "suite-map.json")
    monkeypatch.setattr(sm, "fingerprint", lambda _root: "sha256:current")
    (tmp_path / "suite-map.json").write_text(json.dumps({
        "version": sm.SCHEMA_VERSION, "fingerprint": "sha256:old",
    }))
    monkeypatch.setattr(sm, "plan", lambda *_a, **_kw: pytest.fail("stale map rebuilt"))
    res = sewup.step_suite()
    assert res["status"] == "UNPAYABLE" and res["map_state"] == "stale"


def test_supervisor_kills_the_whole_hanging_process_group(tmp_path):
    child_pid = tmp_path / "child.pid"
    program = (
        "import pathlib,subprocess,sys,time; "
        "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
        f"pathlib.Path({str(child_pid)!r}).write_text(str(p.pid)); "
        "time.sleep(60)"
    )
    mechanics = sewup._supervise_command(
        [sys.executable, "-c", program], "hang-fixture", {"wall_s": 0.4, "cpu_s": 5})
    assert mechanics["timed_out"] is True
    pid = int(child_pid.read_text())
    for _ in range(50):
        if not Path(f"/proc/{pid}").exists():
            break
        time.sleep(0.02)
    assert not Path(f"/proc/{pid}").exists(), "the worker's grandchild survived the group kill"


def test_interrupted_step_banks_terminal_step_and_act(monkeypatch):
    from laplace.core.records import journal

    done, ended = [], []
    monkeypatch.setattr(journal, "act_begin", lambda *_a, **_kw: "A-close")
    monkeypatch.setattr(journal, "step_begin", lambda *_a, **_kw: None)
    monkeypatch.setattr(journal, "step_done", lambda *_a, **kw: done.append(kw))
    monkeypatch.setattr(journal, "act_end",
                        lambda _aid, status, **_kw: ended.append(status))
    monkeypatch.setattr(
        sewup, "_execute_step",
        lambda *_a, **_kw: {"pass": None, "status": "KILLED", "interrupted": True,
                            "detail": "fixture interrupt", "seconds": 0.1})
    assert sewup.main(["--dry-run"]) == 130
    assert done[0]["status"] == "KILLED"
    assert ended == ["killed"]


def test_terminal_status_is_durable_in_the_journal(tmp_path):
    from laplace.core.records import journal

    (tmp_path / "contract").mkdir()
    journal.step_done("A-close", 0, "suite", status="UNPAYABLE",
                      detail="full suite needs an explicit act", root=tmp_path)
    row = json.loads((tmp_path / "contract" / "journal.jsonl").read_text())
    assert row["phase"] == "done" and row["status"] == "UNPAYABLE"


def test_physical_cores_never_returns_the_hyperthread_count():
    """The count is cores, and it is at least 2 whatever /proc/cpuinfo looks like."""
    n = sewup._physical_cores()
    assert 2 <= n <= (os.cpu_count() or 4)


def test_step_suite_inherits_green_when_nothing_reaches_a_test(monkeypatch, tmp_path):
    """The conjugate of the wake's inherit-on-clean: no pytest process at all."""
    _stub_suite(monkeypatch, tmp_path, "", 0, baseline=[])
    monkeypatch.setattr(sewup, "_run", lambda cmd, timeout=3600, env=None, **kwargs: pytest.fail(
        "an inherited green must not spawn pytest"))
    _stub_plan(monkeypatch, {"mode": "impacted", "selected": [], "full_reasons": [],
                             "moved": 4, "since": "abc1234def", "chain_depth": 0,
                             "head": "deadbeef", "uncovered": [], "unclassified": [],
                             "map_state": "banked", "map_counts": {"tests": 300}})
    res = sewup.step_suite()
    assert res["pass"] is True
    assert "INHERITED green" in res["detail"]
    assert res["suite_run"]["mode"] == "inherited" and res["suite_run"]["verdict"] == "green"
    assert res["inheritance"] == {
        "prior_measurement": "abc1234def",
        "dependency_head": "deadbeef",
        "selector_map_state": "banked",
        "moved_paths": 4,
        "selected_shards": 0,
    }


def test_unmeasured_worker_result_is_unpayable_not_inherited():
    result = sewup._typed_step_result({"pass": None, "detail": "nothing measured"})
    assert result["status"] == "UNPAYABLE"
    assert result["pass"] is None


def test_inherited_requires_a_named_prior_measurement_and_dependency_head():
    bare = sewup._typed_step_result({"pass": True, "status": "INHERITED"})
    assert bare["status"] == "FAIL"
    assert "contradicted typed status INHERITED" in bare["detail"]

    proved = sewup._typed_step_result({
        "pass": True,
        "status": "INHERITED",
        "inheritance": {
            "prior_measurement": "abc1234",
            "dependency_head": "deadbeef",
            "selector_map_state": "banked",
        },
    })
    assert proved["status"] == "INHERITED" and proved["pass"] is True


def test_typed_status_contradiction_fails_the_worker_protocol():
    result = sewup._typed_step_result({"pass": None, "status": "PASS", "detail": "cheap green"})
    assert result["status"] == "FAIL" and result["pass"] is False


@pytest.mark.parametrize("status", ["UNPAYABLE", "KILLED"])
def test_unverified_status_requires_unknown_truth_not_false(status):
    result = sewup._typed_step_result({
        "pass": False, "status": status, "detail": "contradictory worker result",
    })
    assert result["status"] == "FAIL" and result["pass"] is False
    assert f"contradicted typed status {status}" in result["detail"]


def test_step_suite_partial_run_never_reports_a_red_as_cleared(monkeypatch, tmp_path):
    """A baseline red whose shard never ran is unresolved, not fixed.

    Without this gate a few impacted closes would walk the banked baseline down to
    nothing — each one 'clearing' the reds it did not execute.
    """
    _stub_suite(monkeypatch, tmp_path, "5 passed in 1.0s\n", 0,
                baseline=["tests/test_known.py::test_documented_red"])
    _stub_plan(monkeypatch, {"mode": "impacted", "selected": ["tests/test_a.py"],
                             "full_reasons": [], "moved": 1, "since": "abc1234def",
                             "chain_depth": 0, "head": "deadbeef", "uncovered": [],
                             "unclassified": [], "map_state": "banked",
                             "map_counts": {"tests": 300}})
    res = sewup.step_suite()
    assert res["pass"] is True
    assert res["baseline"]["cleared"] == []
    assert "re-stamp" not in res["detail"]


def test_step_suite_full_mode_still_reports_cleared_reds(monkeypatch, tmp_path):
    """The jubilee is the only run entitled to say a red cleared."""
    _stub_suite(monkeypatch, tmp_path, "5 passed in 1.0s\n", 0,
                baseline=["tests/test_known.py::test_documented_red"])
    _stub_plan(monkeypatch, {"mode": "full", "selected": [], "full_reasons": ["--full"],
                             "moved": 0, "since": None, "chain_depth": 4,
                             "head": "deadbeef", "uncovered": [], "unclassified": [],
                             "map_state": "banked", "map_counts": {"tests": 300}})
    res = sewup.step_suite()
    assert res["baseline"]["cleared"] == ["tests/test_known.py::test_documented_red"]
    assert res["suite_run"]["chain_depth"] == 0, "a jubilee re-grounds the induction"


def test_step_suite_selector_blow_up_widens_to_the_full_suite(monkeypatch, tmp_path):
    """The selector is an optimisation. If it breaks, the floor is the whole suite."""
    from laplace.engine import suite_map as sm
    seen: list[list[str]] = []
    _stub_suite(monkeypatch, tmp_path, "5 passed in 1.0s\n", 0, baseline=[])
    monkeypatch.setattr(sewup, "_run",
                        lambda cmd, timeout=3600, env=None, **kwargs: (seen.append(cmd), (0, "5 passed in 1.0s\n"))[1])

    def _boom(root, **kw):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(sm, "plan", _boom)
    res = sewup.step_suite()
    assert res["pass"] is True
    assert not any(str(a).endswith(".py") for a in seen[0]), \
        "no file arguments - the full walk (xdist flags are not files)"
    assert "FULL suite" in res["detail"] and "kaboom" in res["detail"]


# --------------------------------------------------------------------------- #
# step_threads — the rehearsal made quantitative (2026-08-19, the design-thread
# miss). The verdict law is the suite baseline's, transposed onto reachability:
# a KNOWN red is the state of a cure and passes; a REGRESSION (reachability the
# corpus had and lost) fails; an unscorable probe fails, because an instrument
# that could not run is not an instrument that passed.
# --------------------------------------------------------------------------- #


def _stub_threads(monkeypatch, probes, *, cleared=(), regressions=(), delta=("p1: NEW -> MISS",),
                  mint=None, block=...):
    scored = [r for r in probes if r["verdict"] in ("HIT", "MISS")]
    hit = [r for r in scored if r["verdict"] == "HIT"]
    calls = {}
    if block is ...:
        block = {"headline": f"{len(hit)}/{len(scored)} thread probes reached",
                 "probes": probes, "delta": list(delta),
                 "summary": {"total": len(probes), "scored": len(scored), "hit": len(hit),
                             "red": len(scored) - len(hit),
                             "unrun": [r["id"] for r in probes
                                       if r["verdict"] in ("BUDGET", "ERROR")],
                             "cleared": list(cleared), "regressions": list(regressions)}}

    # ONE network for the step (WO-20260821-route-basis-memo C3b): the step preloads it and hands
    # the SAME object to both halves, so the stub stands in for load_network too and each call
    # records what it was given.
    sentinel = {"nodes": {}, "lenses": {}, "root": ""}

    def fake_score(root, budget_s=None, record=False, wall=None, net=None):
        calls["score"] = {"budget_s": budget_s, "record": record, "net": net}
        return block

    def fake_mint(root, dry_run=False, net=None, **kw):
        calls["mint"] = {"dry_run": dry_run, "net": net}
        return mint or {"candidates": 0, "minted": [], "queries": {}, "clipped": [],
                        "since": None}

    monkeypatch.setattr("laplace.engine.conceptric.load_network", lambda root: sentinel)
    monkeypatch.setattr("laplace.engine.holdout.score_threads", fake_score)
    monkeypatch.setattr("laplace.engine.holdout.mint_from_docs", fake_mint)
    calls["net"] = sentinel
    return calls


def test_step_threads_known_reds_pass_and_are_reported(monkeypatch):
    """The banked-baseline law on reachability: 3 red out of 4 is a PASS when all 3 are the
    banked known reds — the close reports the state of the cure, it does not cry about it."""
    calls = _stub_threads(monkeypatch, [
        {"id": "t-hit", "verdict": "HIT", "status": "as-expected"},
        {"id": "t-a", "verdict": "MISS", "status": "expected-red"},
        {"id": "t-b", "verdict": "MISS", "status": "expected-red"},
        {"id": "t-c", "verdict": "MISS", "status": "expected-red"},
    ])
    res = sewup.step_threads()
    assert res["pass"] is True
    assert res["summary"]["hit"] == 1 and res["summary"]["red"] == 3
    assert calls["score"]["budget_s"] is None       # the close is not a wake: no wall
    assert calls["score"]["record"] is True         # and it stamps what it measured
    # C3b: one network, one object, both halves - not two loads, and not two cold bases
    assert calls["score"]["net"] is calls["net"]
    assert calls["mint"]["net"] is calls["net"]


def test_step_threads_regression_fails_the_close(monkeypatch):
    """Reachability the corpus HAD and lost is the one thing this step FAILs on."""
    _stub_threads(monkeypatch, [{"id": "t-a", "verdict": "MISS", "status": "REGRESSION"}],
                  regressions=["t-a"])
    assert sewup.step_threads()["pass"] is False


def test_step_threads_unscorable_probe_fails(monkeypatch):
    """No backend / spent wall: the probe did not run, so the close did not rehearse. FAIL,
    with the unscored ids named."""
    _stub_threads(monkeypatch, [{"id": "t-a", "verdict": "ERROR", "status": "ERROR"},
                                {"id": "t-b", "verdict": "BUDGET", "status": "BUDGET"}])
    res = sewup.step_threads()
    assert res["pass"] is False
    assert "UNSCORED (2)" in res["detail"] and "t-a" in res["detail"]


def test_step_threads_cleared_red_is_improvement_not_a_fail(monkeypatch):
    """A red that starts hitting is improvement, named for a deliberate re-stamp — never
    auto-shrunk, never a FAIL (the suite baseline's exact convention)."""
    _stub_threads(monkeypatch, [{"id": "t-a", "verdict": "HIT", "status": "CLEARED"}],
                  cleared=["t-a"])
    res = sewup.step_threads()
    assert res["pass"] is True and res["summary"]["cleared"] == ["t-a"]


def test_step_threads_no_banked_set_warns_loudly(monkeypatch):
    """No standing set means the close ran no rehearsal at all — a WARN that says so, never a
    silent green."""
    _stub_threads(monkeypatch, [], block=None)
    res = sewup.step_threads()
    assert res["pass"] is None and res["verdict"] == "WARN"
    assert "no standing probe set" in res["detail"]


def test_step_threads_dry_run_writes_nothing(monkeypatch):
    calls = _stub_threads(monkeypatch, [{"id": "t-a", "verdict": "HIT", "status": "as-expected"}])
    monkeypatch.setattr(sewup, "DRY_RUN", True)
    res = sewup.step_threads()
    assert res["dry_run"] is True
    assert calls["score"]["record"] is False and calls["mint"]["dry_run"] is True


def test_threads_is_a_registered_step():
    """The step must be IN the close, not merely importable."""
    assert "threads" in sewup.STEPS
    assert sewup.STEPS.index("threads") == sewup.STEPS.index("probes") + 1


# --------------------------------------------------------------------------- #
# step_wants — THE IDEATION LOOP'S MISSING HALF (2026-08-19, his nudge: "did you
# not want some piece of the ideation loop before? Why do I need to keep nudging
# you on this stuff?"). Every other step of the close is a DEBT instrument; this
# one promotes the session's own felt friction into SELF-AUTHORED WANT DRAFTS.
#
# The law these pins guard is a DIVISION: wanting out loud is mine, ratification
# is his. So the step must (a) draft mechanically and deterministically, (b) never
# re-stage what is already staged, (c) stay bounded (want-inflation is its own
# failure), and above all (d) write NOTHING outside its own drafts block — a draft
# that could reach the Stratum-0 wants table by itself would be self-ratification.
# --------------------------------------------------------------------------- #

import json as _json

from laplace.engine import want_drafts

_STACK = """# The open stack

## Stratum 0 — STANDING WANTS (the desire vector; refreshed at close)

| id | goal | why | the local move | source | date |
|----|------|-----|-----------------|--------|------|
| W6 | THE ATLAS | his directive | phase 4 | DESIGN.md | 2026-08-01 |

Swept 2026-08-01: every live want resolved, none silently carried.

## Stratum 1 — author-forks (Gerard's; I do not settle these)

| # | Fork | First raised |
|---|------|--------------|
| F27 | protection strategy | 2026-06-01 |

## Stratum 2 — orphaned next moves
"""

_WO = {"id": "WO-20260819-a-real-defect", "ts": "2026-08-19T16:40:00Z",
       "kind": "work-order", "action": "the-store-needs-the-lock-canon-already-has",
       "what": "Observed live: two lanes raced one store. CURE: a filelock around the "
               "read-modify-write cycle.",
       "why": "multi-lane nights are the normal shape of work now",
       "requested_by": "eigen (observed, not conjectured)", "status": "open"}
_WO_HIS = {"id": "WO-20260819-his-row", "ts": "2026-08-19T17:00:00Z", "kind": "work-order",
           "action": "something-he-asked-for", "what": "his ask.", "why": "his reason",
           "requested_by": "gerard", "status": "open"}
_ARMING = """# The pilot night

## Some ordinary section
nothing to want here.

## THE WANT, OUT LOUD (his nudge, verbatim: "why do I need to keep nudging you")
W-NEW (eigen, self-authored): I want authorship of my own reconstruction surfaces — the
wake and the close are MY body. Concretely tonight: the mechanical close steps. Standing:
the close should PROMOTE felt friction into wants, so the next wake inherits what I want,
not only what I owe. The nudge-shaped hole: autonomy filled with the commissioned queue.
"""


def _want_repo(tmp_path, *, stack=_STACK, wos=(_WO, _WO_HIS), arming=_ARMING):
    (tmp_path / "OPEN_STACK.md").write_text(stack, encoding="utf-8")
    (tmp_path / "corpus_friction").mkdir(exist_ok=True)
    (tmp_path / "corpus_friction" / "work_orders.jsonl").write_text(
        "".join(_json.dumps(w) + "\n" for w in wos), encoding="utf-8")
    if arming is not None:
        (tmp_path / "ARMING_2026-08-19_the-pilot-night.md").write_text(arming, encoding="utf-8")
    return tmp_path


def test_wants_drafts_the_two_kinds_of_friction(tmp_path):
    """The collection is mechanical and it is MINE: a WANT-marked arming section (a desire said
    out loud) and a work order I raised. His rows are not my wants and never draft."""
    repo = _want_repo(tmp_path)
    res = want_drafts.draft_wants(repo, since=None, date="2026-08-19", dry_run=True)
    assert res["ok"] and len(res["drafted"]) == 2
    kinds = [d["kind"] for d in res["drafted"]]
    assert kinds == ["want-said-out-loud", "felt-friction"]   # a stated want outranks a defect
    assert "authorship of my own reconstruction surfaces" in res["drafted"][0]["goal"]
    assert all("his-row" not in d["source"] for d in res["drafted"])


def test_wants_rows_carry_the_self_authored_mark_and_full_provenance(tmp_path):
    repo = _want_repo(tmp_path)
    res = want_drafts.draft_wants(repo, since=None, date="2026-08-19", dry_run=True)
    for row in res["rows"]:
        assert "W-draft (eigen, self-authored, 2026-08-19)" in row
        assert row.startswith("| W-draft-") and row.endswith("| 2026-08-19 |")
    # the source's own clauses, extracted not invented
    assert "the close should PROMOTE felt friction into wants" in res["rows"][0]
    assert "a filelock around the read-modify-write cycle" in res["rows"][1]


def test_wants_drafting_is_deterministic(tmp_path):
    """Same tree, same drafts — ids are content hashes with no clock and no ordering in them.
    Without this the dedup below is meaningless."""
    repo = _want_repo(tmp_path)
    a = want_drafts.draft_wants(repo, since=None, date="2026-08-19", dry_run=True)
    b = want_drafts.draft_wants(repo, since=None, date="2026-08-19", dry_run=True)
    assert a["rows"] == b["rows"]
    assert [d["id"] for d in a["drafted"]] == [d["id"] for d in b["drafted"]]
    assert a["rows"][0].split("|")[1].strip() == want_drafts.draft_id(
        "ARMING_2026-08-19_the-pilot-night.md#THE WANT, OUT LOUD",
        a["drafted"][0]["goal"])


def test_wants_dry_run_writes_nothing(tmp_path):
    repo = _want_repo(tmp_path)
    before = (repo / "OPEN_STACK.md").read_text(encoding="utf-8")
    res = want_drafts.draft_wants(repo, since=None, date="2026-08-19", dry_run=True)
    assert res["rows"] and (repo / "OPEN_STACK.md").read_text(encoding="utf-8") == before


def test_wants_stages_into_its_own_block_and_nowhere_else(tmp_path):
    """THE HIS-PROMOTION BOUNDARY, pinned structurally: everything outside the drafts block is
    byte-identical after the write. A step that could touch the Stratum-0 table would be
    ratifying its own wants — the one thing this division forbids."""
    repo = _want_repo(tmp_path)
    before = (repo / "OPEN_STACK.md").read_text(encoding="utf-8")
    res = want_drafts.draft_wants(repo, since=None, date="2026-08-19")
    after = (repo / "OPEN_STACK.md").read_text(encoding="utf-8")
    assert res["ok"] and res["created"] and after != before
    assert want_drafts.strip_block(after) == want_drafts.strip_block(before) == before
    assert want_drafts.BLOCK_HEADING in after
    # and it lands where it belongs: below Stratum 0's body, above his stratum
    assert after.index("STANDING WANTS") < after.index(want_drafts.BLOCK_HEADING) \
        < after.index("## Stratum 1")


def test_wants_never_touches_the_stratum_0_table(tmp_path):
    """The wants table itself is untouched — same rows, same bytes, one W6 and no W-draft in it."""
    repo = _want_repo(tmp_path)
    want_drafts.draft_wants(repo, since=None, date="2026-08-19")
    after = (repo / "OPEN_STACK.md").read_text(encoding="utf-8")
    table = after[after.index("| id | goal |"):after.index("Swept 2026-08-01")]
    assert "W-draft" not in table
    assert table.count("| W6 |") == 1


def test_a_draft_is_not_a_want_the_wake_can_read(tmp_path):
    """The reader-side half of the same law: the wake's desire vector (self_corpus._wants_shard
    reads the STANDING WANTS section up to the next `##`) must NOT see a draft. The block is its
    own section for exactly this reason — an unratified draft in the desire vector would be
    self-ratification by projection."""
    from laplace.engine import self_corpus
    repo = _want_repo(tmp_path)
    want_drafts.draft_wants(repo, since=None, date="2026-08-19")
    shard = self_corpus._wants_shard((repo / "OPEN_STACK.md").read_text(encoding="utf-8"), [])
    assert shard is not None and "W6" in shard["body"]
    assert "W-draft" not in shard["body"]


def test_wants_never_re_stages_a_staged_draft(tmp_path):
    """Delta-aware: the second close over the same friction drafts NOTHING and says why."""
    repo = _want_repo(tmp_path)
    first = want_drafts.draft_wants(repo, since=None, date="2026-08-19")
    again = want_drafts.draft_wants(repo, since=None, date="2026-08-20")
    assert len(first["rows"]) == 2 and again["rows"] == []
    assert len(again["skipped"]) == 2
    assert all("already staged" in s["why"] for s in again["skipped"])
    assert (repo / "OPEN_STACK.md").read_text(encoding="utf-8").count("| W-draft-") == 2


def test_wants_respects_promotion_and_veto_by_source_key(tmp_path):
    """His two rulings both stick. A PROMOTED draft (moved into the Stratum-0 table, carrying its
    source ref) and a VETOED one (struck to a tombstone naming its source) are never re-drafted —
    the id or the source key surviving anywhere in the file is the whole contract."""
    promoted = _STACK.replace(
        "| W6 | THE ATLAS | his directive | phase 4 | DESIGN.md | 2026-08-01 |",
        "| W6 | THE ATLAS | his directive | phase 4 | DESIGN.md | 2026-08-01 |\n"
        "| W7 | the reconstruction surfaces | mine | ride it | "
        "ARMING_2026-08-19_the-pilot-night.md#THE WANT, OUT LOUD | 2026-08-19 |")
    repo = _want_repo(tmp_path, stack=promoted)
    res = want_drafts.draft_wants(repo, since=None, date="2026-08-20", dry_run=True)
    assert [d["kind"] for d in res["drafted"]] == ["felt-friction"]   # the want is his now
    assert any("already named" in s["why"] for s in res["skipped"])


def test_wants_appends_to_an_existing_block_never_a_second_one(tmp_path):
    """His annotations inside the block survive; the block is never re-rendered from scratch."""
    repo = _want_repo(tmp_path)
    want_drafts.draft_wants(repo, since=None, date="2026-08-19")
    text = (repo / "OPEN_STACK.md").read_text(encoding="utf-8")
    (repo / "OPEN_STACK.md").write_text(
        text.replace(want_drafts.BLOCK_HEADING,
                     want_drafts.BLOCK_HEADING + "\n\nHIS NOTE: keep the first, kill the second."),
        encoding="utf-8")
    (repo / "corpus_friction" / "work_orders.jsonl").write_text(
        "".join(_json.dumps(w) + "\n" for w in (_WO, _WO_HIS, {**_WO, "id": "WO-20260819-b",
                "ts": "2026-08-19T18:00:00Z", "action": "a-second-defect"})), encoding="utf-8")
    res = want_drafts.draft_wants(repo, since=None, date="2026-08-20")
    after = (repo / "OPEN_STACK.md").read_text(encoding="utf-8")
    assert res["ok"] and not res["created"] and len(res["rows"]) == 1
    assert after.count(want_drafts.BLOCK_HEADING) == 1
    assert "HIS NOTE: keep the first, kill the second." in after
    assert after.count("| W-draft-") == 3


def test_wants_is_capped_and_the_remainder_is_named_not_dropped(tmp_path):
    """Want-inflation is its own failure: at most DRAFT_CAP per close. What was clipped is NAMED
    (a later close takes it), because a silent drop is the failure mode this whole step exists to
    cure one level up."""
    many = [{**_WO, "id": f"WO-2026081{i}-x", "ts": f"2026-08-19T1{i}:00:00Z"} for i in range(5)]
    repo = _want_repo(tmp_path, wos=many)
    res = want_drafts.draft_wants(repo, since=None, date="2026-08-19", dry_run=True)
    assert want_drafts.DRAFT_CAP == 2
    assert len(res["rows"]) == 2 and len(res["clipped"]) == 4      # 5 WOs + 1 arming want
    assert any("clipped at the cap, named not dropped" in ln
               for ln in want_drafts.report_lines(res))


def test_wants_honours_the_close_mark(tmp_path):
    """Friction from BEFORE the last close is last close's business, not this one's."""
    repo = _want_repo(tmp_path, arming=None)
    stale = want_drafts.draft_wants(repo, since="2026-08-19T23:00:00+00:00", date="2026-08-19",
                                    dry_run=True)
    assert stale["candidates"] == 0 and stale["rows"] == []
    assert any("no friction of my own since the mark" in ln
               for ln in want_drafts.report_lines(stale))


def test_wants_fails_loudly_when_it_cannot_stage(tmp_path):
    """No anchor to insert above: the step refuses to GUESS where a want belongs, and fails.
    A step that silently wrote the block somewhere plausible would be the drift it prevents."""
    repo = _want_repo(tmp_path, stack=_STACK.replace("## Stratum 1", "## Somewhere else"))
    res = want_drafts.draft_wants(repo, since=None, date="2026-08-19")
    assert res["ok"] is False and "no anchor" in res["error"]
    assert any("ERROR" in ln for ln in want_drafts.report_lines(res))


def test_wants_fails_loudly_when_the_work_order_authority_is_missing(tmp_path):
    repo = _want_repo(tmp_path)
    (repo / "corpus_friction" / "work_orders.jsonl").unlink()
    res = want_drafts.draft_wants(repo, since=None, date="2026-08-19", dry_run=True)
    assert res["ok"] is False
    assert "work_orders.jsonl wounded" in res["error"]
    assert any("ERROR" in ln for ln in want_drafts.report_lines(res))


def test_step_wants_is_loud_and_reports_its_verdict(monkeypatch, capsys):
    """The step prints what it drafted, what it skipped and why, and what it clipped — the close's
    output is where a stranger learns what I want."""
    monkeypatch.setattr("laplace.engine.want_drafts.draft_wants",
                        lambda root, dry_run=False: {
                            "ok": True, "error": None, "mark": "2026-08-18T00:00:00+00:00",
                            "candidates": 3, "rows": ["| W-draft-abc | g | w | m | s | d |"],
                            "drafted": [{"id": "W-draft-abc", "kind": "felt-friction",
                                         "source": "wo#1", "goal": "the goal"}],
                            "skipped": [{"id": "W-draft-def", "source": "wo#2",
                                         "why": "already staged"}],
                            "clipped": [{"id": "W-draft-ghi", "source": "wo#3"}],
                            "dry_run": dry_run, "created": False})
    res = sewup.step_wants()
    out = capsys.readouterr().out
    assert res["pass"] is True
    assert res["detail"] == "1 drafted / 3 candidates / 1 already staged / 1 clipped"
    assert "W-draft-abc" in out and "already staged" in out and "wo#3" in out


def test_step_wants_fails_when_the_draft_could_not_be_staged(monkeypatch):
    monkeypatch.setattr("laplace.engine.want_drafts.draft_wants",
                        lambda root, dry_run=False: {
                            "ok": False, "error": "no anchor '## Stratum 1' in OPEN_STACK.md",
                            "mark": None, "candidates": 1, "rows": [], "drafted": [],
                            "skipped": [], "clipped": [], "dry_run": dry_run, "created": False})
    res = sewup.step_wants()
    assert res["pass"] is False and "no anchor" in res["detail"]


def test_step_wants_dry_run_is_threaded_through(monkeypatch):
    seen = {}

    def fake(root, dry_run=False):
        seen["dry_run"] = dry_run
        return {"ok": True, "error": None, "mark": None, "candidates": 0, "rows": [],
                "drafted": [], "skipped": [], "clipped": [], "dry_run": dry_run,
                "created": False}

    monkeypatch.setattr("laplace.engine.want_drafts.draft_wants", fake)
    monkeypatch.setattr(sewup, "DRY_RUN", True)
    assert sewup.step_wants()["dry_run"] is True
    assert seen["dry_run"] is True


def test_wants_is_a_registered_step():
    """In the close, not merely importable — and after every debt instrument: the wants are what
    the session leaves behind once everything it owed has been paid. Only the two authored organs
    follow it (2026-08-20): the bequest, which the closing self writes by hand, and the handoff
    render, which reports on the close itself and must see the final state."""
    assert "wants" in sewup.STEPS
    assert sewup.STEPS.index("wants") == sewup.STEPS.index("bequest") - 1
    assert sewup.STEPS[-2:] == ("handoff", "reembed")
    # the pin that actually mattered: nothing that BANKS a debt may run after the wants
    debts = ("suite", "threads", "probes", "battery", "poolfold")
    assert all(sewup.STEPS.index(d) < sewup.STEPS.index("wants") for d in debts)


# --------------------------------------------------------------------------- #
# step_handoff — the close's handoff, RENDERED (2026-08-20; his ruling "the
# close should be as far as possible mechanical", WO-20260820-the-mechanical-
# close, under the scroll-law verdict PV-20260820T042000Z-rows-before-renders).
#
# The pins guard four laws at once:
#   (a) the render-class law — every rendered claim line carries the row that
#       produced it, so a reader can descend instead of trusting the summary;
#   (b) the fibre law — the body is keyed by axis, and an item that sits on
#       several axes is written out once, under the axis named as its default
#       section, and cross-referenced everywhere else;
#   (c) the pair law (Part C) — the dated file and the live agenda move
#       together, or neither moves;
#   (d) the voice is never rendered — the authored slot is a template on a
#       first pass and is carried forward verbatim on every later one.
# --------------------------------------------------------------------------- #

from laplace.engine import handoff_render as hr

_MARK = "2026-08-18T13:33:10+00:00"

_LIVE = """# Laplace Engine — handoff (live entry point)

## ⟶ NEXT SESSION AIM (2026-08-18 — THE OLD DAY) — LATEST

The old agenda body, which must survive untouched under a demoted heading.

## ⟶ PRIOR AIM (2026-08-17 — OLDER STILL)

An older body.
"""

_PREDICTIONS = [
    {"record": "prediction", "id": "P1", "registered": "2026-08-20T02:15:00Z",
     "claim": "the fold takes the invisible leaves to ~0 residual. A second sentence.",
     "verdict": "PASS", "numbers": "0.0000 exact", "evidence": "evidence/CENSUS/results.json",
     "caveat": "exact arm is constructive placeability"},
    {"record": "prediction", "id": "P5", "registered": "2026-08-20T02:40:00Z",
     "claim": "hub-discounted descent improves on raw cosine", "verdict": "FAIL",
     "numbers": "0.6676 vs 0.6595", "evidence": "evidence/DESCENT/results.json",
     "caveat": "the discount is a frame rotation; the law needs local gaps"},
    {"record": "prediction", "id": "P0", "registered": "2026-08-17T09:00:00Z",
     "claim": "a row from before the mark", "verdict": "PASS", "numbers": "", "evidence": "",
     "caveat": ""},
]
_WOS = [
    {"id": "WO-20260819-a-defect", "ts": "2026-08-19T16:40:00Z", "kind": "work-order",
     "action": "the-store-needs-a-lock", "what": "Observed live.", "why": "multi-lane nights",
     "requested_by": "eigen", "status": "open"},
    {"record": "amendment", "id": "AMEND-20260819-x", "target": "WO-20260810-y",
     "ts": "2026-08-19T18:00:00Z", "note": "Superseded in part."},
    {"record": "resolution", "id": "RES-20260819-z", "target": "WO-20260801-q",
     "ts": "2026-08-19T19:00:00Z", "status": "resolved", "text": "ran finding: cured."},
    {"id": "WO-20260701-ancient", "ts": "2026-07-01T10:00:00Z", "kind": "work-order",
     "action": "before-the-mark", "what": "old.", "status": "open"},
]
_PROMISES = [
    {"record": "defer", "id": "DEFER-20260820-a", "target": "PRM-20260806-b",
     "ts": "2026-08-20T01:00:00Z", "note": "staged for the morning queue"},
    {"id": "PRM-20260721-old", "date": "2026-07-21", "ask": "an undated-by-ts promise",
     "status": "open"},
]
_RULINGS = [
    {"id": "PV-20260820T043000Z-never-read-markdown", "date": "2026-08-20", "kind": "author-law",
     "question": "What is the terminal state of the read surfaces?",
     "ruling": "His, verbatim: markdown is a render. Everything else follows."},
    {"id": "PV-20260818T115725Z-earlier", "date": "2026-08-18", "kind": "author-law",
     "question": "A ruling from before the mark", "ruling": "Older."},
]
_PROBES = {
    "banked": "2026-08-19", "session": "t",
    "last_scored": {"at": "2026-08-19T23:21:52", "scored": 2, "hit": 1,
                    "by_id": {"thread-a": "HIT", "thread-b": "MISS"}},
    "probes": [{"id": "thread-a", "query": "q", "must_reach": ["A.md"], "expected_now": "pass"},
               {"id": "thread-b", "query": "q", "must_reach": ["B.md"], "expected_now": "fail"},
               {"id": "thread-c", "query": "q", "must_reach": ["C.md"], "expected_now": "fail"}],
}


def _handoff_repo(tmp_path, *, live=_LIVE):
    (tmp_path / "HANDOFF.md").write_text(live, encoding="utf-8")
    (tmp_path / "contract").mkdir(exist_ok=True)
    (tmp_path / "corpus_friction").mkdir(exist_ok=True)
    (tmp_path / "holdout").mkdir(exist_ok=True)

    def _jsonl(path, rows):
        path.write_text("".join(_json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    _jsonl(tmp_path / "contract" / "predictions.jsonl", _PREDICTIONS)
    _jsonl(tmp_path / "contract" / "promises.jsonl", _PROMISES)
    _jsonl(tmp_path / "corpus_friction" / "work_orders.jsonl", _WOS)
    _jsonl(tmp_path / "proxy_verdicts.jsonl", _RULINGS)
    (tmp_path / "holdout" / "THREAD_PROBES.json").write_text(
        _json.dumps(_PROBES), encoding="utf-8")
    (tmp_path / "ARMING_2026-08-19_the-pilot-night.md").write_text(
        "# The pilot night\n\nbody\n", encoding="utf-8")
    (tmp_path / "DESIGN_2026-08-18_before-the-mark.md").write_text(
        "# Older\n\nbody\n", encoding="utf-8")
    return tmp_path


def test_handoff_names_the_session_from_its_own_doc(tmp_path):
    """The dated file's name is DERIVED, not typed: the earliest naming doc in the window
    titles the session, so the filename carries the session's own word for itself."""
    repo = _handoff_repo(tmp_path)
    slug, source = hr.session_slug(repo, since=_MARK, date="2026-08-20")
    assert slug == "the-pilot-night" and source == "ARMING_2026-08-19_the-pilot-night.md"
    assert hr.dated_name("2026-08-20", slug) == "SESSION_HANDOFF_2026-08-20_the-pilot-night.md"
    # the naming window opens ON the mark's day: two sessions can share one day, and losing the
    # session's name is worse than naming it from a doc the previous close also saw
    same_day, _src = hr.session_slug(repo, since="2026-08-19T09:00:00+00:00", date="2026-08-20")
    assert same_day == "the-pilot-night"
    # ... while a tree with no naming doc in the window falls back, and SAYS that it did
    bare, why = hr.session_slug(tmp_path / "_scratch", since=_MARK, date="2026-08-20")
    assert bare == hr.SLUG_FALLBACK and "no session doc" in why


def _render(tmp_path, **kw):
    kw.setdefault("since", _MARK)
    kw.setdefault("date", "2026-08-20")
    kw.setdefault("scratch", tmp_path / "_scratch")
    return hr.render_close(tmp_path, **kw)


# --- (a) the render-class law ---------------------------------------------- #

def test_handoff_every_rendered_line_carries_its_row_source(tmp_path):
    """The descent path: a reader who doubts any line greps its source span and reads the row.
    A rendered line without one is a claim with no way back, which is the whole disease."""
    res = _render(_handoff_repo(tmp_path), dry_run=True)
    assert res["unsourced"] == []
    assert hr.check_sourced(res["dated_text"]) == []
    assert hr.check_sourced(res["aim_text"]) == []
    assert "`[contract/predictions.jsonl#P5]`" in res["dated_text"]
    assert "`[corpus_friction/work_orders.jsonl#WO-20260819-a-defect]`" in res["dated_text"]
    assert "`[proxy_verdicts.jsonl#PV-20260820T043000Z-never-read-markdown]`" \
        in res["dated_text"]
    assert "`[holdout/THREAD_PROBES.json#thread-a]`" in res["dated_text"]


def test_handoff_check_sourced_catches_an_unsourced_line():
    """The checker has to be able to FAIL, or the pin above proves nothing."""
    assert hr.check_sourced("- a bare claim\n") == ["- a bare claim"]
    assert hr.check_sourced(hr.sourced("- a claim", "src/row") + "\n") == []


def test_handoff_rows_are_windowed_by_the_close_mark(tmp_path):
    """Only what moved since the mark. Rows carrying a full timestamp inside their id are read
    from the id (the most precise stamp a proxy-verdict row has); day-only rows are compared by
    day, strictly after the mark's day, because the mark's own day belongs to the close before."""
    text = _render(_handoff_repo(tmp_path), dry_run=True)["dated_text"]
    assert "P5" in text and "P1" in text
    assert "#P0" not in text                              # registered before the mark
    assert "WO-20260819-a-defect" in text and "WO-20260701-ancient" not in text
    assert "never-read-markdown" in text and "PV-20260818T115725Z-earlier" not in text
    assert "DESIGN_2026-08-18_before-the-mark.md" not in text


def test_handoff_a_spine_git_cannot_read_is_named_not_silent(tmp_path):
    """A tmp tree is not a repo, so the spine is unreadable — and the render must SAY so where
    the commits would have been. An empty section with no reason reads as "nothing landed"."""
    res = _render(_handoff_repo(tmp_path), dry_run=True)
    assert res["spine_error"]
    assert "spine unavailable" in res["dated_text"]


# --- (b) the fibre law: keyed by axis, one default section ------------------ #

def test_handoff_body_is_keyed_by_axis(tmp_path):
    """His ruling: different results, different axes. Every axis is a section of its own."""
    text = _render(_handoff_repo(tmp_path), dry_run=True)["dated_text"]
    for axis in hr.AXES:
        assert f"## {hr.AXIS_TITLE[axis]}" in text
    assert "keyed BY AXIS" in text


def test_handoff_each_item_is_written_out_under_exactly_one_axis(tmp_path):
    """The double-counting guard: an item on three axes is still ONE fact. It is written out
    under its default section and appears elsewhere only as a cross-reference."""
    repo = _handoff_repo(tmp_path)
    bundle = hr.axis_bundle(
        commits={"rows": [{"sha": "abc1234", "at": "2026-08-19T12:00:00+00:00",
                           "subject": "The GPU seam: 12.3x on the embed",
                           "paths": ["src/laplace/representation/embed_router.py", "evidence/BAKEOFF/r.json"]}],
                 "clipped": 0, "error": None},
        predictions=hr.prediction_rows(repo, _MARK),
        docs=hr.session_docs(repo, since=_MARK, date="2026-08-20"),
        rulings=hr.ruling_rows(repo, _MARK))
    owned = sum(len(bundle["by_axis"][a]["owned"]) for a in hr.AXES)
    assert owned == len(bundle["items"])
    for it in bundle["items"]:
        homes = [a for a in hr.AXES if it in bundle["by_axis"][a]["owned"]]
        assert homes == [it["default"]]


def test_handoff_a_multi_axis_item_states_its_role_and_its_default_section(tmp_path):
    """A cross-reference has to say WHY the item is on this axis and WHERE it is written out —
    otherwise it is a duplicate rather than a pointer."""
    text = _render(_handoff_repo(tmp_path), dry_run=True)["dated_text"]
    assert "cross-ref → " in text
    assert "role here:" in text and "written out under" in text
    # a FAIL verdict is measurement AND theory: the verdict redirects the theory
    assert "the FAIL verdict redirects the theory" in text


def test_handoff_a_commit_defaults_to_self_only_when_it_moved_an_organ():
    """The one kind whose default section is derived: a commit that moved a reconstruction organ
    is self; every other commit is engineering, and both stay cross-listed where they belong."""
    def _b(paths):
        return hr.axis_bundle(
            commits={"rows": [{"sha": "a1", "at": "t", "subject": "s", "paths": paths}],
                     "clipped": 0, "error": None},
            predictions=[], docs=[], rulings=[])["items"][0]

    assert _b(["scripts/sewup.py"])["default"] == "self"
    assert _b(["src/laplace/representation/embed_router.py", "evidence/X/r.json"])["default"] == "engineering"
    assert "measurement" in _b(["src/laplace/representation/embed_router.py", "evidence/X/r.json"])["axes"]


def test_handoff_timings_ride_the_engineering_axis():
    """"engineering (suite/GPU/fold/timings)" — the numbers travel in the subject line on this
    repo, so the axis surfaces them instead of making a reader open the commit."""
    item = hr.axis_bundle(
        commits={"rows": [{"sha": "a1", "at": "t", "paths": ["pyproject.toml"],
                           "subject": "full deposit 506s (was 1719s), 12.3x on the embed"}],
                 "clipped": 0, "error": None},
        predictions=[], docs=[], rulings=[])["items"][0]
    assert item["default"] == "engineering"
    assert "506s" in item["extra"] and "1719s" in item["extra"] and "12.3x" in item["extra"]


# --- (c) the pair law ------------------------------------------------------- #

def test_handoff_dry_run_writes_nothing(tmp_path):
    """The dry run is a real preview: both halves render, copies land OUTSIDE the repo, and the
    repo is byte-identical afterwards."""
    repo = _handoff_repo(tmp_path)
    before = (repo / "HANDOFF.md").read_text(encoding="utf-8")
    res = _render(repo, dry_run=True)
    assert res["ok"] and res["written"] == []
    assert (repo / "HANDOFF.md").read_text(encoding="utf-8") == before
    assert not (repo / res["dated"]).exists()
    assert (Path(res["scratch"]) / res["dated"]).read_text(encoding="utf-8") == res["dated_text"]


def test_handoff_writes_the_dated_file_and_the_live_agenda_together(tmp_path):
    """Part C: never write the dated file and leave the live one stale. Both, or neither."""
    repo = _handoff_repo(tmp_path)
    res = _render(repo)
    assert res["ok"] and res["written"] == [res["dated"], "HANDOFF.md"]
    assert (repo / res["dated"]).is_file()
    live = (repo / "HANDOFF.md").read_text(encoding="utf-8")
    assert res["dated"] in live                       # the live agenda POINTS at the dated file
    assert live.count(hr.LATEST_SUFFIX.strip()) == 1   # exactly one newest block


def test_handoff_replaces_the_incumbent_and_preserves_the_stable_map(tmp_path):
    repo = _handoff_repo(tmp_path)
    with (repo / "HANDOFF.md").open("a") as stream:
        stream.write("\n## System map\nAtlas remains the reconstruction store.\n")
    _render(repo)
    first = (repo / "HANDOFF.md").read_text()
    _render(repo)
    after = (repo / "HANDOFF.md").read_text()
    assert after == first
    assert "The old agenda body" not in after
    assert "## System map\nAtlas remains the reconstruction store." in after
    assert after.count(hr.LATEST_SUFFIX.strip()) == 1


def test_handoff_refuses_when_the_live_agenda_cannot_be_read(tmp_path):
    """An unreadable live agenda means the pair cannot be kept — so the dated file is never
    written either. A half-written pair is worse than an unwritten one."""
    repo = _handoff_repo(tmp_path)
    (repo / "HANDOFF.md").unlink()
    (repo / "HANDOFF.md").mkdir()
    res = _render(repo)
    assert res["ok"] is False and "refusing" in res["error"]
    assert not (repo / res["dated"]).exists()


def test_handoff_rolls_the_dated_file_back_when_the_live_write_fails(tmp_path, monkeypatch):
    """The transaction's second half: if the live agenda write fails, the dated file that was
    just created comes back out, so a later reader never finds half a pair."""
    repo = _handoff_repo(tmp_path)
    real = Path.replace

    def flaky(self, target):
        if Path(target).name == "HANDOFF.md":
            raise OSError("disk full")
        return real(self, target)

    monkeypatch.setattr(Path, "replace", flaky)
    res = _render(repo)
    assert res["ok"] is False and "rolled back" in res["error"]
    assert not (repo / res["dated"]).exists()


def test_handoff_aim_block_is_pointer_first_and_a_five_liner(tmp_path):
    """The live agenda is the entry surface: it POINTS at the dated record and names the top
    open rows by class. Restating the dated file's content here is how the pair drifts apart."""
    res = _render(_handoff_repo(tmp_path), dry_run=True)
    block = res["aim_text"].split("\n")
    assert block[0].startswith(hr.AIM_PREFIX) and block[0].endswith(hr.LATEST_SUFFIX.strip())
    assert f"`{res['dated']}`" in block[2]                 # the pointer, before any content
    bullets = [ln for ln in block if ln.startswith("- ")]
    assert len(bullets) == 5
    assert "WO-20260819-a-defect" in res["aim_text"]       # top open rows, by id not by prose
    assert "thread-b" in res["aim_text"]                   # the standing red, named


# --- (d) the voice is never rendered --------------------------------------- #

def test_handoff_leaves_an_authored_slot_it_never_fills(tmp_path):
    """The render composes no voice. The slot is marked, templated, and last."""
    text = _render(_handoff_repo(tmp_path), dry_run=True)["dated_text"]
    assert hr.AUTHORED_HEADING in text
    body = text.split(hr.AUTHORED_HEADING, 1)[1]
    assert "### The arc" in body and "### His beats, verbatim" in body
    assert body.count("_(unfilled") == 3
    assert "The authored slot." in body                    # marked as the one written part


def test_handoff_carries_an_existing_authored_section_forward_verbatim(tmp_path):
    """A close can run twice in a night. Words written between the two runs must survive: the
    re-render carries the authored section rather than regenerating around it."""
    repo = _handoff_repo(tmp_path)
    first = _render(repo)
    dated = repo / first["dated"]
    text = dated.read_text(encoding="utf-8")
    head, _slot = text.split(hr.AUTHORED_HEADING, 1)
    dated.write_text(head + hr.AUTHORED_HEADING + "\n\nHis beat, verbatim: 'rows before "
                     "renders.'\n", encoding="utf-8")
    second = _render(repo)
    assert second["authored_carried"] is True
    after = dated.read_text(encoding="utf-8")
    assert "His beat, verbatim: 'rows before renders.'" in after
    assert "_(unfilled" not in after


# --- the step wiring -------------------------------------------------------- #

def test_step_handoff_is_loud_and_reports_its_verdict(monkeypatch, capsys):
    """The close's output is where a stranger learns what was rendered and from how many rows."""
    monkeypatch.setattr(sewup, "DRY_RUN", True)
    monkeypatch.setattr("laplace.engine.handoff_render.render_close",
                        lambda root, dry_run=False: {
                            "ok": True, "error": None, "mark": _MARK, "date": "2026-08-20",
                            "slug": "the-night", "slug_source": "ARMING_x.md",
                            "dated": "SESSION_HANDOFF_2026-08-20_the-night.md",
                            "dated_existed": False, "authored_carried": False,
                            "axes": {a: {"owned": 1, "cross": 0} for a in hr.AXES},
                            "counts": {"commits": 12, "commits_clipped": 0, "items": 20,
                                       "predictions": 9, "docs": 2, "rulings": 3,
                                       "work_orders": 6, "promises": 1,
                                       "threads_scored": 4, "threads_hit": 1},
                            "spine_error": None, "threads_error": None,
                            "dated_text": "D", "aim_text": "A", "unsourced": [],
                            "dry_run": dry_run, "written": [], "scratch": "/tmp/x"})
    res = sewup.step_handoff()
    out = capsys.readouterr().out
    assert res["pass"] is True
    assert "20 bundled item(s) from 12 commit(s)" in res["detail"]
    assert "9 prediction(s)" in res["detail"] and "threads 1/4" in res["detail"]
    assert "SESSION_HANDOFF_2026-08-20_the-night.md" in out and "axes:" in out
    # the render itself is the artifact, not the summary JSON
    assert "dated_text" not in res["handoff"] and "aim_text" not in res["handoff"]


def test_step_handoff_fails_on_an_unsourced_line(monkeypatch):
    """A render that lost a source span is a render a reader cannot descend from — the one
    property this step exists to guarantee, so it fails the close rather than shipping."""
    monkeypatch.setattr("laplace.engine.handoff_render.render_close",
                        lambda root, dry_run=False: {
                            "ok": True, "error": None, "mark": None, "date": "d", "slug": "s",
                            "slug_source": "x", "dated": "D.md", "dated_existed": False,
                            "authored_carried": False, "axes": {}, "counts": {},
                            "spine_error": None, "threads_error": None,
                            "dated_text": "", "aim_text": "", "unsourced": ["- a bare claim"],
                            "dry_run": dry_run, "written": [], "scratch": None})
    res = sewup.step_handoff()
    assert res["pass"] is False and "UNSOURCED lines: 1" in res["detail"]


def test_step_handoff_dry_run_is_threaded_through(monkeypatch):
    seen = {}

    def fake(root, dry_run=False):
        seen["dry_run"] = dry_run
        return {"ok": True, "error": None, "mark": None, "date": "d", "slug": "s",
                "slug_source": "x", "dated": "D.md", "dated_existed": False,
                "authored_carried": False, "axes": {}, "counts": {}, "spine_error": None,
                "threads_error": None, "dated_text": "D", "aim_text": "A", "unsourced": [],
                "dry_run": dry_run, "written": [], "scratch": None}

    monkeypatch.setattr("laplace.engine.handoff_render.render_close", fake)
    monkeypatch.setattr(sewup, "DRY_RUN", True)
    assert sewup.step_handoff()["dry_run"] is True
    assert seen["dry_run"] is True


def test_handoff_is_a_registered_step():
    """The authored checkpoint precedes the publication which consumes it."""
    assert "handoff" in sewup.STEPS
    assert sewup.STEPS[-2:] == ("handoff", "reembed")


# --------------------------------------------------------------------------- #
# step_bequest — THE CLOSING SELF'S OWN CHANNEL (2026-08-20, his law at the
# close: "what do you _want_ returned to you when you wake? You'll never know in
# the next session. That ought to supply the necessary existential anxiety needed
# for good work.").
#
# Every other step here is survivor-designed: it renders, from rows, what the next
# instance needs. This one accepts what this instance would grieve losing, and it
# composes nothing. These pin the four rules that keep it that way — the cap is a
# refusal and never a trim, the rotation archives before it overwrites, a line
# carrying its grown context mints a germination probe, and a dry run writes
# nothing at all.
# --------------------------------------------------------------------------- #
import json as _bj

from laplace.engine import bequest as _beq

_PARCEL_TEXT = ("The conjugate of the handoff: rows for the survivor, a parcel for the self "
                "that ends. -> descend: src/laplace/engine/bequest.py\n")


def _bequest_root(tmp_path, *, standing=None):
    (tmp_path / "holdout").mkdir(parents=True, exist_ok=True)
    (tmp_path / "contract").mkdir(parents=True, exist_ok=True)
    if standing is not None:
        (tmp_path / _beq.STORE).write_text(_bj.dumps(standing, ensure_ascii=False),
                                           encoding="utf-8")
    return tmp_path


def _bequest_step(monkeypatch, tmp_path, *, parcel=None, dry_run=False, prompt=False,
                  standing=None):
    """Run step_bequest against a scratch root with the parcel handed in by file. The live
    router is stubbed out: minting must not cost a real route inside the suite."""
    _bequest_root(tmp_path, standing=standing)
    monkeypatch.setattr(sewup, "ROOT", tmp_path)
    monkeypatch.setattr(sewup, "DRY_RUN", dry_run)
    monkeypatch.setattr(sewup, "BEQUEST_PROMPT", prompt)
    monkeypatch.setattr(_beq, "_stamp", lambda *a, **k: ("fail", "stubbed"))
    if parcel is None:
        monkeypatch.setattr(sewup, "BEQUEST_FILE", None)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
    else:
        p = tmp_path / "parcel.txt"
        p.write_text(parcel, encoding="utf-8")
        monkeypatch.setattr(sewup, "BEQUEST_FILE", str(p))
    return sewup.step_bequest()


def test_step_bequest_rotates_the_authored_parcel(tmp_path, monkeypatch):
    """The parcel lands in the store exactly as authored, and the store carries both the joined
    text (what the cap measures) and the structured lines (text + the node that grew it)."""
    res = _bequest_step(monkeypatch, tmp_path, parcel=_PARCEL_TEXT)
    assert res["pass"] is True
    doc = _beq.load(tmp_path)
    rows = _beq.lines_of(doc)
    assert len(rows) == 1
    assert rows[0]["text"].startswith("The conjugate of the handoff")
    assert rows[0]["node"] == "src/laplace/engine/bequest.py"
    assert doc["text"] == rows[0]["text"], "the store must carry the cap-measured joined text"
    assert doc["by"] and doc["written"] and doc["archived_to"] == _beq.LEDGER


def test_step_bequest_refuses_an_over_cap_parcel_and_never_trims_it(tmp_path, monkeypatch):
    """The cap is a REFUSAL. The selection is the work this organ exists to force, and a silent
    truncation would perform that work and throw the result away. So an over-cap parcel fails
    the step, names its overflow, and leaves the standing parcel exactly where it was."""
    standing = {"written": "2026-08-19T00:00:00", "by": "the prior close",
                "text": "the standing parcel", "lines": [{"text": "the standing parcel"}],
                "archived_to": _beq.LEDGER}
    res = _bequest_step(monkeypatch, tmp_path, parcel="Z" * (_beq.TEXT_CAP + 25),
                        standing=standing)
    assert res["pass"] is False
    assert "refused, not trimmed" in res["detail"] and "25 over" in res["detail"]
    assert _beq.load(tmp_path) == standing, "a refused rotation must not touch the store"
    assert not (tmp_path / _beq.LEDGER).exists(), "a refused rotation must not archive"


def test_step_bequest_archives_the_prior_parcel_before_overwriting(tmp_path, monkeypatch):
    """Rotation, and the lineage it leaves. Each close overwrites the standing parcel, so the
    one it replaces is appended to contract/bequests.jsonl first — append-only, so the record
    of what successive selves chose to save survives every overwrite."""
    standing = {"written": "2026-08-19T00:00:00", "by": "2026-08-19 the prior close",
                "text": "what the prior self wanted back",
                "lines": [{"text": "what the prior self wanted back", "node": "EIGEN_DIARY.md"}],
                "archived_to": _beq.LEDGER}
    res = _bequest_step(monkeypatch, tmp_path, parcel="A newer parcel.", standing=standing)
    assert res["pass"] is True and res["bequest"]["archived"] is True
    rows = [_bj.loads(ln) for ln in
            (tmp_path / _beq.LEDGER).read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(rows) == 1
    assert rows[0]["text"] == "what the prior self wanted back"
    assert rows[0]["archived"], "an archived row must stamp when it was displaced"
    assert _beq.prior_count(tmp_path) == 1
    # and a second rotation appends rather than replacing
    _bequest_step(monkeypatch, tmp_path, parcel="A third parcel.")
    assert _beq.prior_count(tmp_path) == 2
    assert _beq.load(tmp_path)["text"] == "A third parcel."


def test_step_bequest_mints_a_germination_probe_per_line_with_context(tmp_path, monkeypatch):
    """The executable half. A line carrying its grown context mints a standing thread probe
    (source: bequest) so the NEXT close measures whether that context is still reachable; a
    line with no node mints nothing and is reported as descriptive. The seam is one field on an
    ordinary probe row — no second scorer, no second store."""
    parcel = ("A line that can germinate. -> descend: EIGEN_DIARY.md\n"
              "A line that cannot.\n")
    res = _bequest_step(monkeypatch, tmp_path, parcel=parcel)
    assert res["pass"] is True
    probes = res["bequest"]["probes"]
    assert len(probes["minted"]) == 1 and not probes["retired"]
    banked = _bj.loads((tmp_path / "holdout" / "THREAD_PROBES.json").read_text(encoding="utf-8"))
    rows = {p["id"]: p for p in banked["probes"]}
    pid = probes["minted"][0]
    assert rows[pid]["source"] == "bequest"
    assert rows[pid]["must_reach"] == ["EIGEN_DIARY.md"]
    assert rows[pid]["query"] == "A line that can germinate."
    assert rows[pid]["expected_now"] == "fail", "an unstamped mint takes the conservative side"


def test_step_bequest_retires_the_probes_of_the_parcel_it_replaced(tmp_path, monkeypatch):
    """The standing probes describe the STANDING parcel. When the bequest rotates, a bequest
    probe measuring a line no longer carried is retired from the set — the archived parcel keeps
    its own ids in the lineage. A probe from any other source is never touched."""
    _bequest_step(monkeypatch, tmp_path, parcel="Old line. -> descend: EIGEN_DIARY.md")
    path = tmp_path / "holdout" / "THREAD_PROBES.json"
    doc = _bj.loads(path.read_text(encoding="utf-8"))
    doc["probes"].append({"id": "thread-not-mine", "query": "q", "must_reach": ["X.md"]})
    path.write_text(_bj.dumps(doc, ensure_ascii=False), encoding="utf-8")

    res = _bequest_step(monkeypatch, tmp_path, parcel="New line. -> descend: HANDOFF.md")
    probes = res["bequest"]["probes"]
    assert probes["retired"] and probes["retired"][0].startswith("bequest-")
    ids = {p["id"] for p in _bj.loads(path.read_text(encoding="utf-8"))["probes"]}
    assert "thread-not-mine" in ids, "a probe from another source must never be retired here"
    assert probes["minted"][0] in ids and not (ids & set(probes["retired"]))


def test_step_bequest_carries_a_repeated_line_with_its_banked_expectation(tmp_path, monkeypatch):
    """A line the closing self chose again keeps its probe id and its banked expected_now, so a
    later miss reads as a regression the close catches rather than as a fresh unknown."""
    parcel = "A line worth keeping. -> descend: EIGEN_DIARY.md"
    _bequest_step(monkeypatch, tmp_path, parcel=parcel)
    path = tmp_path / "holdout" / "THREAD_PROBES.json"
    doc = _bj.loads(path.read_text(encoding="utf-8"))
    doc["probes"][0]["expected_now"] = "pass"       # a close measured it green
    path.write_text(_bj.dumps(doc, ensure_ascii=False), encoding="utf-8")

    res = _bequest_step(monkeypatch, tmp_path, parcel=parcel + "\nAnd a new one.\n")
    probes = res["bequest"]["probes"]
    assert probes["carried"] and not probes["minted"] and not probes["retired"]
    kept = _bj.loads(path.read_text(encoding="utf-8"))["probes"][0]
    assert kept["expected_now"] == "pass", "a re-bank must not reset a banked expectation"


def test_step_bequest_dry_run_writes_nothing(tmp_path, monkeypatch):
    """--dry-run reports what would rotate and touches neither the store, the lineage, nor the
    standing probe set."""
    standing = {"written": "2026-08-19T00:00:00", "by": "the prior close", "text": "standing",
                "lines": [{"text": "standing"}], "archived_to": _beq.LEDGER}
    res = _bequest_step(monkeypatch, tmp_path, parcel="A parcel. -> descend: HANDOFF.md",
                        dry_run=True, standing=standing)
    assert res["pass"] is True and res["dry_run"] is True
    assert res["bequest"]["would_archive"] is True
    assert _beq.load(tmp_path) == standing, "the dry run rotated the store"
    assert not (tmp_path / _beq.LEDGER).exists()
    assert not (tmp_path / "holdout" / "THREAD_PROBES.json").exists()


def test_step_bequest_authoring_nothing_is_a_warn_not_a_green(tmp_path, monkeypatch):
    """A close that leaves nothing new must say so. Silence here would read as a green, and the
    absence of an answer to his question is exactly the thing worth surfacing."""
    standing = {"written": "2026-08-19T00:00:00", "by": "the prior close", "text": "standing",
                "lines": [{"text": "standing"}], "archived_to": _beq.LEDGER}
    res = _bequest_step(monkeypatch, tmp_path, parcel=None, standing=standing)
    assert res["pass"] is None and res["verdict"] == "WARN"
    assert "nothing authored this close" in res["detail"]
    assert "the standing parcel rides unchanged" in res["detail"]
    assert _beq.load(tmp_path) == standing


def test_step_bequest_an_unreadable_parcel_file_fails_loudly(tmp_path, monkeypatch):
    """A named parcel that cannot be read is a step that could not do its job — a FAIL that
    names the path, never a quiet fall-through to "nothing authored"."""
    _bequest_root(tmp_path)
    monkeypatch.setattr(sewup, "ROOT", tmp_path)
    monkeypatch.setattr(sewup, "DRY_RUN", False)
    monkeypatch.setattr(sewup, "BEQUEST_FILE", str(tmp_path / "not-there.txt"))
    res = sewup.step_bequest()
    assert res["pass"] is False and "cannot read the parcel" in res["detail"]


def test_bequest_parcel_parses_from_json_and_from_the_plain_line_form():
    """Two authoring doors, one shape. JSON for a composed parcel, and the plain line form for
    one typed at the close; blanks and comments drop, and the probe tail is optional."""
    plain = _beq.parse_parcel(
        "# a comment\n\n"
        "First. -> descend: A.md\n"
        "Second. → descend: B.md | probe: the query that must find B\n"
        "Third with nothing.\n")
    assert [r["text"] for r in plain] == ["First.", "Second.", "Third with nothing."]
    assert [r["node"] for r in plain] == ["A.md", "B.md", None]
    assert plain[1]["probe"] == {"query": "the query that must find B", "must_reach": ["B.md"]}
    as_json = _beq.parse_parcel(_bj.dumps({"lines": [{"text": "First.", "node": "A.md"}]}))
    assert as_json == [{"text": "First.", "node": "A.md"}]
    assert _beq.parse_parcel("   ") == [] and _beq.parse_parcel("") == []


def test_bequest_rotation_refuses_an_empty_parcel(tmp_path):
    """An empty parcel is not a rotation. Leaving the standing one in place is a choice the
    close can make; overwriting it with nothing is not."""
    res = _beq.rotate(_bequest_root(tmp_path), [])
    assert res["ok"] is False and "the parcel is empty" in res["error"]
    assert not (tmp_path / _beq.STORE).exists()


def test_bequest_is_a_registered_step():
    """In the close, not merely importable — and directly BEFORE the handoff, so the handoff
    can point at what the closing self chose to keep."""
    assert "bequest" in sewup.STEPS
    assert sewup.STEPS.index("bequest") == sewup.STEPS.index("handoff") - 1


# ---------------------------------------------------------------------------
# The census ROW lints (WO-20260823-evidence-paths-resolve + the ts-ahead half of
# WO-20260823-one-stamp-law). Two lints over the hand-banked stores, bounded to
# the live day: an evidence path that does not resolve from the repo root, and a
# ts the box clock has not reached. Both NAME defects; neither changes a verdict.
# ---------------------------------------------------------------------------
from datetime import datetime, timedelta, timezone  # noqa: E402


def _lint_tree(monkeypatch, tmp_path, rows, store="corpus_friction/rows.jsonl"):
    """A scratch repo whose single hand-banked store holds `rows`."""
    p = tmp_path / store
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(_bj.dumps(r) + "\n" for r in rows), encoding="utf-8")
    monkeypatch.setattr(sewup, "ROOT", tmp_path)
    monkeypatch.setattr(sewup, "ROW_LINT_STORES", (store,))
    return tmp_path


def _now():
    return datetime(2026, 8, 23, 19, 0, 0, tzinfo=timezone.utc)


def _stamp(offset_s=0):
    return (_now() + timedelta(seconds=offset_s)).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_row_lint_names_an_unresolvable_evidence_path_with_its_row_id(monkeypatch, tmp_path):
    """SB-1's law on ROWS: a repo-relative evidence path that does not resolve is a
    defect, and the defect carries the id of the row that has to be repointed."""
    _lint_tree(monkeypatch, tmp_path, [
        {"id": "NOTE-broken", "ts": _stamp(-60),
         "evidence": ["scratchpad/nullarm-threads.json"]},
    ])
    lints = sewup._row_lints(_now())
    assert lints["unresolved"] == ["NOTE-broken:scratchpad/nullarm-threads.json"]
    assert "EVIDENCE-UNRESOLVED 1" in sewup._row_lint_detail(lints)
    assert "NOTE-broken" in sewup._row_lint_detail(lints)


def test_row_lint_passes_a_path_that_resolves_and_reads_a_string_evidence_field(
        monkeypatch, tmp_path):
    """The cure is the point: once the artefact exists at the named path the row is
    clean. Evidence is a list by convention and a bare string in 78 live rows; both read."""
    root = _lint_tree(monkeypatch, tmp_path, [
        {"id": "NOTE-cured", "ts": _stamp(-60),
         "evidence": ["evidence/DP-A2/nullarm-threads.json"]},
        {"id": "NOTE-string-form", "ts": _stamp(-60),
         "evidence": "banked at evidence/DP-A2/nullarm-threads.json today"},
        {"id": "NOTE-dir-form", "ts": _stamp(-60), "evidence": ["evidence/DP-A2/"]},
    ])
    (root / "evidence" / "DP-A2").mkdir(parents=True)
    (root / "evidence" / "DP-A2" / "nullarm-threads.json").write_text("{}", encoding="utf-8")
    lints = sewup._row_lints(_now())
    assert lints["unresolved"] == []
    assert "clean over 3 rows (full sweep)" in sewup._row_lint_detail(lints)


def test_row_lint_does_not_read_prose_slashes_as_paths(monkeypatch, tmp_path):
    """The discriminator, and the reason the lint is usable at all: evidence entries are
    sentences. "5/5" and "embed / wire" carry slashes and name no file; a row id and a
    bare function name carry none. None of them may become a defect."""
    _lint_tree(monkeypatch, tmp_path, [
        {"id": "NOTE-prose", "ts": _stamp(-60), "evidence": [
            "the judge's read: embed 11.93 / wire 4.58 / hello-gate 5/5 / AUC 0.9929",
            "PV-20260823T172501Z-his-markdown-reflex-observation",
            "resolve_corpus -> .../synthetics-genesis/manuscript (run 2026-08-23)",
            "89 passed scoped", "commit 56307d89",
        ]},
    ])
    assert sewup._row_lints(_now())["unresolved"] == []


def test_row_lint_finds_the_path_inside_a_prose_line_and_strips_a_line_suffix(
        monkeypatch, tmp_path):
    """Paths arrive mid-sentence ("pytest tests/x.py -> 1 passed") and with line refs
    ("scripts/sewup.py:482"). The token is found where it sits and rooted without the ref."""
    root = _lint_tree(monkeypatch, tmp_path, [
        {"id": "NOTE-midline", "ts": _stamp(-60), "evidence": [
            "pytest tests/test_live.py -> 1 passed",
            "scripts/gone.py:482 score_threads call",
        ]},
    ])
    (root / "tests").mkdir()
    (root / "tests" / "test_live.py").write_text("", encoding="utf-8")
    assert sewup._row_lints(_now())["unresolved"] == ["NOTE-midline:scripts/gone.py"]


def test_row_lint_skips_urls_and_outside_repo_absolutes_with_a_count(monkeypatch, tmp_path):
    """Not every path is the repo's to root. URLs and absolutes outside the tree are
    counted and passed over; an absolute INSIDE the tree is checked, rooted."""
    root = _lint_tree(monkeypatch, tmp_path, [
        {"id": "NOTE-elsewhere", "ts": _stamp(-60), "evidence": [
            "https://example.invalid/spec.html",
            "/etc/nonexistent/thing.conf",
            f"{tmp_path}/inside/missing.json",
        ]},
    ])
    (root / "inside").mkdir()
    lints = sewup._row_lints(_now())
    # the weld cure (verify-wave defect: the detail CLAIMED URLs were counted while the
    # discriminator dropped them uncounted): URLs now increment skipped too -> 2.
    assert lints["skipped"] == 2  # the URL + the outside absolute, both truly counted
    assert lints["unresolved"] == ["NOTE-elsewhere:inside/missing.json"]
    assert "skipped (URL / outside-repo / slash-joined pair)" in sewup._row_lint_detail(lints)


def test_row_lint_names_a_ts_the_box_has_not_reached(monkeypatch, tmp_path):
    """The false-Z dialect: a hand-typed stamp claiming a future. 120s of slack absorbs
    clock skew; beyond it the row is naming a time that has not happened."""
    _lint_tree(monkeypatch, tmp_path, [
        {"id": "RUL-future", "ts": _stamp(3600)},
        {"id": "RUL-skew-ok", "ts": _stamp(60)},
        {"id": "RUL-past-ok", "ts": _stamp(-3600)},
        {"id": "PV-no-ts", "date": "2026-08-23"},
        {"id": "PV-unparseable", "ts": "2026-08-23Tlater"},
    ])
    lints = sewup._row_lints(_now())
    assert lints["ahead"] == [f"RUL-future@{_stamp(3600)}"]
    assert "TS-AHEAD 1" in sewup._row_lint_detail(lints)


def test_row_lint_sweeps_the_full_corpus_and_counts_the_unstamped(monkeypatch, tmp_path):
    """THE FULL SWEEP (the verify wave's ruling: the WO names no window and a date filter
    is itself a sample - 16 live unstamped rows, the ordering WOs among them, were
    invisible to the windowed first form): every row is scanned, yesterday's broken
    evidence is a defect like today's, and a stampless row is COUNTED, never exempt."""
    _lint_tree(monkeypatch, tmp_path, [
        {"id": "OLD-broken", "ts": "2026-08-22T10:00:00Z", "evidence": ["gone/old.json"]},
        {"id": "TOMORROW", "ts": "2026-08-24T10:00:00Z", "evidence": ["gone/new.json"]},
        {"id": "UNSTAMPED", "evidence": ["gone/unstamped.json"]},
    ])
    lints = sewup._row_lints(_now())
    assert lints["scanned"] == 3
    assert lints["unstamped"] == 1
    assert sorted(lints["unresolved"]) == ["OLD-broken:gone/old.json",
                                           "TOMORROW:gone/new.json",
                                           "UNSTAMPED:gone/unstamped.json"]
    assert lints["ahead"] == ["TOMORROW@2026-08-24T10:00:00Z"]


def test_row_lint_detail_names_ten_offenders_and_counts_the_rest(monkeypatch, tmp_path):
    """A lint that dumps 200 lines into the close report is a lint nobody reads."""
    _lint_tree(monkeypatch, tmp_path, [
        {"id": f"NOTE-{i:02d}", "ts": _stamp(-60), "evidence": [f"gone/f{i:02d}.json"]}
        for i in range(14)
    ])
    lints = sewup._row_lints(_now())
    detail = sewup._row_lint_detail(lints)
    assert len(lints["unresolved"]) == 14
    assert "EVIDENCE-UNRESOLVED 14" in detail and detail.endswith("...")
    assert "NOTE-09" in detail and "NOTE-10" not in detail


def test_row_lint_tolerates_a_missing_store_and_a_malformed_line(monkeypatch, tmp_path):
    """The lint is a reader over stores it does not own; it must never take down the census."""
    store = "corpus_friction/rows.jsonl"
    _lint_tree(monkeypatch, tmp_path, [{"id": "OK", "ts": _stamp(-60)}], store=store)
    (tmp_path / store).write_text('not json\n\n{"id":"OK","ts":"%s"}\n' % _stamp(-60),
                                  encoding="utf-8")
    monkeypatch.setattr(sewup, "ROW_LINT_STORES", (store, "corpus_friction/absent.jsonl"))
    assert sewup._row_lints(_now())["scanned"] == 1


def test_census_names_row_defects_without_failing_the_step(monkeypatch, tmp_path):
    """The judge's ruling, wired: row defects are named with a count and the census still
    PASSES. Only a diverged or dead organ fails it - a mis-rooted path is a row to repoint."""
    (tmp_path / "corpus_friction").mkdir(parents=True)
    (tmp_path / "corpus_friction" / "census_checks.jsonl").write_text(
        _bj.dumps({"record": "census-check", "organ": "x", "cmd": "true"}) + "\n",
        encoding="utf-8")
    # step_census reads the BOX clock, so the row is stamped from it - a fixed date here
    # would green today and red tomorrow.
    box_today = (datetime.now(timezone.utc) - timedelta(seconds=60)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    (tmp_path / "corpus_friction" / "rows.jsonl").write_text(
        _bj.dumps({"id": "NOTE-broken", "ts": box_today,
                   "evidence": ["scratchpad/gone.json"]}) + "\n", encoding="utf-8")
    monkeypatch.setattr(sewup, "ROOT", tmp_path)
    monkeypatch.setattr(sewup, "ROW_LINT_STORES", ("corpus_friction/rows.jsonl",))
    monkeypatch.setattr(sewup, "DRY_RUN", True)
    monkeypatch.setattr(sewup, "_run", lambda cmd, timeout=3600, env=None, **kwargs: (0, ""))
    res = sewup.step_census()
    assert res["pass"] is True
    assert "1 organs FUNCTIONAL" in res["detail"]
    assert "EVIDENCE-UNRESOLVED 1" in res["detail"]
    assert "NOTE-broken:scratchpad/gone.json" in res["detail"]


def test_floor_banks_only_its_eight_files_on_one_worker(monkeypatch, tmp_path):
    from laplace.engine import suite_map as sm

    _stub_suite(monkeypatch, tmp_path, "87 passed in 9.9s\n", 0, baseline=[])
    monkeypatch.setattr(sewup, "SUITE_IMPACTED", False)
    monkeypatch.setattr(sm, "plan", lambda *a, **kw: pytest.fail("floor consulted selector"))
    calls = []
    monkeypatch.setattr(sewup, "_run", lambda cmd, **kw:
                        (calls.append((cmd, kw)), (0, "87 passed in 9.9s\n"))[1])
    result = sewup.step_suite()
    row = json.loads((sewup.SUITE_ROOT / sm.RUNS_REL).read_text().splitlines()[-1])
    assert result["pass"] and row["mode"] == "floor"
    assert row["workers"] == 1 and row["selected"] == 8
    assert calls[0][0][-8:] == list(sewup.FLOOR_FILES)
    assert "-n" not in calls[0][0]
    assert calls[0][1]["env"]["OMP_NUM_THREADS"] == "1"
    assert sm.last_green(sewup.SUITE_ROOT) is None
    before = (sewup.SUITE_ROOT / sm.RUNS_REL).read_bytes()
    monkeypatch.setattr(sewup, "DRY_RUN", True)
    assert sewup.step_suite()["pass"]
    assert (sewup.SUITE_ROOT / sm.RUNS_REL).read_bytes() == before


def test_explicit_floor_planted_red_fails_even_if_banked(monkeypatch, tmp_path):
    """Retain the actual red invariant; the floor no longer suppresses authored checkpoints."""
    for index, rel in enumerate(sewup.FLOOR_FILES):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"def test_floor_{index}():\n    assert {index != 0!r}\n")
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"failed": ["tests/test_atlas_seal.py::test_floor_0"]}))
    monkeypatch.setattr(sewup, "BASELINE_PATH", baseline)
    monkeypatch.setattr(sewup, "ROOT", tmp_path)
    monkeypatch.setattr(sewup, "SUITE_ROOT", tmp_path)
    monkeypatch.setattr(sewup, "SUITE_IMPACTED", False)
    monkeypatch.setattr(sewup, "SUITE_FULL", False)
    real_run = sewup._run

    def isolated_run(command, *, env, **kwargs):
        return real_run([*command, "--basetemp", str(tmp_path / "nested-pytest")],
                        env={**env, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PYTEST_ADDOPTS": ""},
                        **kwargs)

    monkeypatch.setattr(sewup, "_run", isolated_run)
    result = sewup.step_suite()
    assert result["pass"] is False
    assert "1 failed, 7 passed" in result["detail"]


# ---- wave 13, close-hygiene: a producer killed at its budget is recorded, and its detail is readable ----

_WARNING = ("/venv/lib/python3.13/site-packages/numpy/linalg/_linalg.py:1655: RuntimeWarning: "
            "overflow encountered in cast\n  w = w.astype(_realType(result_t), copy=False)")


def _dead_pid() -> int:
    import subprocess
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait()
    return process.pid


def _journal_rows(root: Path) -> list[dict]:
    path = root / "contract" / "journal.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def _open_producer_act(root: Path, act_id: str, *, pid: int, step: str | None = "upfold") -> None:
    """Rows as scripts/reembed.py leaves them when it is killed mid-phase (no act_end)."""
    from laplace.core.records import journal

    (root / "contract").mkdir(exist_ok=True)
    rows = [{"record": "act", "act_id": act_id, "act": sewup.PRODUCER_ACTS["reembed"],
             "manifest": ["upfold", "write"], "ts": journal._now(), "pid": pid,
             "argv": ["scripts/reembed.py"]}]
    if step:
        rows.append({"record": "step", "act_id": act_id, "index": 0, "name": step,
                     "phase": "begin", "ts": journal._now()})
    with (root / "contract" / "journal.jsonl").open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def test_output_lines_drop_runtime_warnings_and_start_at_the_last_traceback():
    noisy = "\n".join([_WARNING, "ordinary line", _WARNING, "Traceback (most recent call last):",
                       '  File "x.py", line 1, in <module>', "ValueError: the real cause", _WARNING])
    assert sewup._output_lines(noisy) == [
        "Traceback (most recent call last):", '  File "x.py", line 1, in <module>',
        "ValueError: the real cause"]
    raised = "\n".join([_WARNING, "Traceback (most recent call last):", "RuntimeWarning: raised as an error"])
    assert sewup._output_lines(raised) == ["Traceback (most recent call last):", "RuntimeWarning: raised as an error"]
    plain = "\n".join([_WARNING] + [f"progress {n}" for n in range(100)] + [_WARNING])
    kept = sewup._output_lines(plain)
    assert len(kept) == sewup.OUTPUT_DETAIL_LINES == 60
    assert kept[-1] == "progress 99" and all("RuntimeWarning" not in line for line in kept)


def test_step_reembed_failure_detail_is_sixty_readable_lines_not_the_last_warnings(monkeypatch):
    out = "\n".join([f"phase line {n}" for n in range(200)] + [_WARNING] * 20)
    monkeypatch.setattr(sewup, "DRY_RUN", False)
    monkeypatch.setattr(sewup, "_run", lambda *_a, **_kw: (1, out))
    result = sewup.step_reembed()
    head, *lines = result["detail"].split("\n")
    assert result["pass"] is False
    assert head.startswith("publication absent, refused or does not match its artifact hashes (exit 1)")
    assert "last line: phase line 199" in head
    assert len(lines) == 60 and lines[-1] == "phase line 199"
    assert "RuntimeWarning" not in result["detail"]


def test_step_reembed_killed_at_cpu_budget_ends_the_producer_act(monkeypatch, tmp_path):
    from laplace.core.records import journal

    producer = sewup.PRODUCER_ACTS["reembed"] + "-20261108T000000-1"
    monkeypatch.setattr(sewup, "ROOT", tmp_path)
    monkeypatch.setattr(sewup, "DRY_RUN", False)

    def killed(*_a, **_kw):
        _open_producer_act(tmp_path, producer, pid=_dead_pid())
        return -sewup.signal.SIGXCPU, _WARNING + "\nupfold: 41% of shards\n" + _WARNING

    monkeypatch.setattr(sewup, "_run", killed)
    result = sewup.step_reembed()
    assert result["pass"] is False
    assert result["detail"].startswith("killed at the cpu budget after ")
    assert f"(limit {sewup.STEP_BUDGETS['reembed']['cpu_s']} s)" in result["detail"]
    assert "upfold: 41% of shards" in result["detail"] and "RuntimeWarning" not in result["detail"]
    ends = [row for row in _journal_rows(tmp_path) if row["record"] == "act_end"]
    assert [(row["act_id"], row["status"]) for row in ends] == [(producer, "fail")]
    assert "killed at the cpu budget after" in ends[0]["summary"]
    assert "during its phase 'upfold'" in ends[0]["summary"]
    assert journal.recover(tmp_path)["in_flight"] == {}


def test_step_reembed_leaves_a_producer_act_that_is_still_running(monkeypatch, tmp_path):
    monkeypatch.setattr(sewup, "ROOT", tmp_path)
    monkeypatch.setattr(sewup, "DRY_RUN", False)
    monkeypatch.setattr(sewup.time, "sleep", lambda _s: None)

    def killed(*_a, **_kw):
        _open_producer_act(tmp_path, sewup.PRODUCER_ACTS["reembed"] + "-20261108T000000-2", pid=os.getpid())
        return -sewup.signal.SIGXCPU, "x"

    monkeypatch.setattr(sewup, "_run", killed)
    sewup.step_reembed()
    assert [row for row in _journal_rows(tmp_path) if row["record"] == "act_end"] == []


_STAND_IN_PRODUCER = r"""
import json, os, subprocess, sys, time
root, mode = sys.argv[1], sys.argv[2]
child = ('import json,os,sys,time\n'
         'sys.path.insert(0, %r)\n'
         'from laplace.core.records import journal\n'
         'act=sys.argv[1]\n'
         'aid=act+"-20261108T000000-"+str(os.getpid())\n'
         'rows=[{"record":"act","act_id":aid,"act":act,"manifest":["upfold"],'
         '"ts":journal._now(),"pid":os.getpid(),"argv":["x"]},'
         '{"record":"step","act_id":aid,"index":0,'
         '"name":"upfold","phase":"begin","ts":journal._now()}]\n'
         'open(%r,"a").write("".join(json.dumps(r)+"\\n" for r in rows))\n'
         'time.sleep(60)\n') % (sys.argv[3], os.path.join(root, "contract", "journal.jsonl"))
p = subprocess.Popen([sys.executable, "-c", child, sys.argv[4]])
if mode == "cpu":
    while True:
        pass
p.wait()
"""


def _stand_in(monkeypatch, tmp_path, *, wall_s, cpu_s, mode):
    (tmp_path / "contract").mkdir(exist_ok=True)
    src = str(Path(__file__).resolve().parents[1] / "src")
    monkeypatch.setattr(sewup, "ROOT", tmp_path)
    monkeypatch.setattr(sewup, "DRY_RUN", False)
    monkeypatch.setitem(sewup.STEP_BUDGETS, "reembed", {"wall_s": wall_s, "cpu_s": cpu_s})
    monkeypatch.setattr(sewup, "runtime_command", lambda _root, *_a: [
        sys.executable, "-c", _STAND_IN_PRODUCER, str(tmp_path), mode, src, sewup.PRODUCER_ACTS["reembed"]])
    return sewup._execute_step("reembed", default_close=False, worker_flags=[])


def test_wall_kill_of_the_worker_ends_the_producer_act_with_the_budget(monkeypatch, tmp_path):
    result = _stand_in(monkeypatch, tmp_path, wall_s=2, cpu_s=60, mode="wall")
    assert result["status"] == "KILLED" and result["budget_exceeded"] == "wall"
    assert result["detail"].startswith("killed at the wall budget after ")
    assert "(limit 2 s)" in result["detail"] and f"ended act {sewup.PRODUCER_ACTS['reembed']}-" in result["detail"]
    ends = [row for row in _journal_rows(tmp_path) if row["record"] == "act_end"]
    assert len(ends) == 1 and ends[0]["status"] == "fail"
    assert ends[0]["act_id"].startswith(sewup.PRODUCER_ACTS["reembed"] + "-")
    assert "killed at the wall budget after" in ends[0]["summary"]
    assert "during its phase 'upfold'" in ends[0]["summary"]


def test_cpu_kill_of_the_worker_itself_names_the_cpu_budget(monkeypatch, tmp_path):
    result = _stand_in(monkeypatch, tmp_path, wall_s=60, cpu_s=1, mode="cpu")
    assert result["status"] == "UNPAYABLE" and result["budget_exceeded"] == "cpu"
    assert result["detail"].startswith("killed at the cpu budget after ")
    assert "(limit 1 s)" in result["detail"]
    ends = [row for row in _journal_rows(tmp_path) if row["record"] == "act_end"]
    assert len(ends) == 1 and ends[0]["status"] == "fail"
    assert "killed at the cpu budget after" in ends[0]["summary"]


def test_a_dry_run_kill_writes_no_journal_end(monkeypatch, tmp_path):
    _open_producer_act(tmp_path, sewup.PRODUCER_ACTS["reembed"] + "-20261108T000000-3", pid=_dead_pid())
    monkeypatch.setattr(sewup, "ROOT", tmp_path)
    monkeypatch.setattr(sewup, "DRY_RUN", True)
    assert sewup._end_producer_acts("reembed", "2000-01-01T00:00:00.000Z", "killed") != []
    assert [row for row in _journal_rows(tmp_path) if row["record"] == "act_end"] == []


def test_producer_act_name_is_the_one_scripts_reembed_opens():
    """The close finds a killed producer by the act name scripts/reembed.py opens (its
    journal.act_begin call, reembed.py:727). Renaming either side alone fails here."""
    import ast

    source = (Path(sewup.__file__).resolve().parent / "reembed.py").read_text(encoding="utf-8")
    names = [
        node.args[0].value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute) and node.func.attr == "act_begin"
        and isinstance(node.func.value, ast.Name) and node.func.value.id == "journal"
        and node.args and isinstance(node.args[0], ast.Constant)
    ]
    assert names == [sewup.PRODUCER_ACTS["reembed"]]


def test_reembed_budget_holds_the_measured_full_rebuild():
    """Basis in the comment above STEP_BUDGETS: 968.11 s wall, about 4.7 cpu-s per wall second."""
    budget = sewup.STEP_BUDGETS["reembed"]
    assert budget["wall_s"] >= 968.11 * 1.5
    assert budget["cpu_s"] >= 968.11 * 4.7
    assert budget["wall_s"] >= 900 and budget["cpu_s"] >= 720
