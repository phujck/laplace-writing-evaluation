"""Scoped tests for scripts/audit_silent_failures.py — a tmp fixture repo proving
each seam check's PASS/WARN outcome, the VERDICT sentinel, the rc mirror, and the
(empty) FAIL_ELIGIBLE contract.

The registry checks (economics / state / rounds) resolve the real, hardcoded
project roster under the tmp root, so the fixtures place files at a registered
project's real manuscript path (eigenengine/manuscript) to drive them.
"""
import importlib.util
import json
import os
import stat
import sys
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit_silent_failures.py"

spec = importlib.util.spec_from_file_location("audit_silent_failures", SCRIPT)
audit = importlib.util.module_from_spec(spec)
sys.modules["audit_silent_failures"] = audit
spec.loader.exec_module(audit)

# A registered project whose manuscript_dir resolves cleanly under any root.
EIGEN_MS = "eigenengine/manuscript"


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    return r


def _by_name(checks, name):
    return [c for c in checks if c.name == name]


def _eigen_harnessed(repo: Path) -> Path:
    d = repo / EIGEN_MS / "rounds" / "harnessed"
    d.mkdir(parents=True)
    return d


# --------------------------------------------------------------- economics-fresh
def test_economics_pass_when_no_harnessed_rounds(repo):
    checks = audit.check_economics_fresh(repo)
    assert len(checks) == 1 and checks[0].status == "PASS"
    assert "N=0" in checks[0].detail


def test_economics_warns_when_absent(repo):
    h = _eigen_harnessed(repo)
    (h / "mech_r1.json").write_text("{}")
    checks = _by_name(audit.check_economics_fresh(repo), "economics-fresh")
    warned = [c for c in checks if c.status == "WARN" and "eigenengine" in c.detail]
    assert warned and "absent" in warned[0].detail


def test_economics_pass_when_fresh(repo):
    h = _eigen_harnessed(repo)
    mech = h / "mech_r1.json"
    mech.write_text("{}")
    econ = repo / EIGEN_MS / "rounds" / "economics.json"
    econ.write_text("{}")
    old = time.time() - 100
    os.utime(mech, (old, old))  # economics.json is now newer
    checks = _by_name(audit.check_economics_fresh(repo), "economics-fresh")
    assert any(c.status == "PASS" and "eigenengine" in c.detail for c in checks)


def test_economics_warns_when_stale(repo):
    h = _eigen_harnessed(repo)
    mech = h / "mech_r1.json"
    econ = repo / EIGEN_MS / "rounds" / "economics.json"
    econ.write_text("{}")
    mech.write_text("{}")
    old = time.time() - 100
    os.utime(econ, (old, old))  # economics.json is now older than the mech record
    checks = _by_name(audit.check_economics_fresh(repo), "economics-fresh")
    warned = [c for c in checks if c.status == "WARN" and "stale" in c.detail]
    assert warned


# ----------------------------------------------------------------- state-present
def test_state_present_pass_when_state_json_exists(repo):
    rel = repo / EIGEN_MS / "release"
    rel.mkdir(parents=True)
    (rel / "state.json").write_text(json.dumps({"state": "UNDER_CONVERGENCE", "updated": "2026-07-12T00:00:00"}))
    checks = _by_name(audit.check_state_present(repo), "state-present")
    assert any(c.status == "PASS" and "eigenengine" in c.detail for c in checks)


def test_state_present_warns_never_run(repo):
    checks = _by_name(audit.check_state_present(repo), "state-present")
    warned = [c for c in checks if c.status == "WARN" and "eigenengine" in c.detail]
    assert warned and "NEVER_RUN" in warned[0].detail


# --------------------------------------------------------------- rounds-findable
def test_rounds_findable_pass_when_discovery_resolves(repo):
    h = _eigen_harnessed(repo)
    (h / "mech_r1.json").write_text(json.dumps({"round": 1}))
    checks = _by_name(audit.check_rounds_findable(repo), "rounds-findable")
    assert any(c.status == "PASS" and "eigenengine" in c.detail for c in checks)


def test_rounds_findable_pass_when_none_on_disk(repo):
    checks = audit.check_rounds_findable(repo)
    assert len(checks) == 1 and checks[0].status == "PASS"
    assert "N=0" in checks[0].detail


def test_rounds_findable_warns_when_on_disk_but_unresolved(repo):
    # a round file physically present but unparseable: discovery yields nothing
    # while the raw glob sees it — exactly the falqon-blindness class.
    h = _eigen_harnessed(repo)
    (h / "mech_r1.json").write_text("not json at all {")
    checks = _by_name(audit.check_rounds_findable(repo), "rounds-findable")
    warned = [c for c in checks if c.status == "WARN" and "eigenengine" in c.detail]
    assert warned and "discovery resolves 0" in warned[0].detail


# ----------------------------------------------------------------- ledger-poison
def test_ledger_poison_pass_when_no_ledgers(repo):
    c = audit.check_ledger_poison(repo)
    assert c.status == "PASS" and "N=0" in c.detail


def test_ledger_poison_pass_when_clean(repo):
    f = repo / "corpus_friction"
    f.mkdir()
    (f / "a.jsonl").write_text('{"x": 1}\n{"y": 2}\n')
    c = audit.check_ledger_poison(repo)
    assert c.status == "PASS" and "dropped_n=0" in c.detail


def test_ledger_poison_warns_on_poisoned_line(repo):
    f = repo / "corpus_friction"
    f.mkdir()
    (f / "a.jsonl").write_text('{"x": 1}\nnot-json\n{"y": 2}\n')
    c = audit.check_ledger_poison(repo)
    assert c.status == "WARN"
    assert "dropped_n=1" in c.detail and "a.jsonl=1" in c.detail


# ---------------------------------------------------------------- versions-writer
def test_versions_writer_enforces_the_one_door(repo):
    # Fork 7 / W3.2: the gap is closed — the audit flips from a named-gap WARN to
    # ENFORCING that release.bank_snapshot (the one versions_dir writer) exists.
    c = audit.check_versions_writer(repo)
    assert c.status == "PASS" and "bank_snapshot" in c.detail


# ------------------------------------------------------------- interpreter-sanity
def test_interpreter_sanity_warns_when_venv_absent(repo):
    c = audit.check_interpreter_sanity(repo)
    assert c.status == "WARN" and "test-gate" in c.detail


def test_interpreter_sanity_pass_with_working_interpreter(repo):
    bindir = repo / ".venv" / "bin"
    bindir.mkdir(parents=True)
    py = bindir / "python"
    py.write_text("#!/bin/sh\nexit 0\n")  # a fake interpreter that imports cleanly
    py.chmod(py.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    c = audit.check_interpreter_sanity(repo)
    assert c.status == "PASS"


# ------------------------------------------------------------- voice-conformance
def test_voice_conformance_warns_when_absent(repo):
    c = audit.check_voice_conformance(repo)
    assert c.status == "WARN"


def test_voice_conformance_pass_when_names_inputs(repo):
    (repo / "conformance_2026-07-12.json").write_text(json.dumps({"corpus": "paper_x", "sections": []}))
    c = audit.check_voice_conformance(repo)
    assert c.status == "PASS" and "corpus=paper_x" in c.detail


def test_voice_conformance_warns_when_no_input_named(repo):
    (repo / "conformance_2026-07-12.json").write_text(json.dumps({"summary": "ok"}))
    c = audit.check_voice_conformance(repo)
    assert c.status == "WARN" and "no input corpus" in c.detail


# --------------------------------------------------------------- verdict / sentinel
def test_fail_eligible_is_empty():
    assert audit.FAIL_ELIGIBLE == frozenset()


def test_verdict_asserts_on_stray_fail():
    stray = [audit.Check("versions-writer", "FAIL", "x")]
    with pytest.raises(AssertionError):
        audit._verdict(stray)


def test_all_warn_still_verdict_pass_and_rc0(repo):
    rc = audit.main(["--repo", str(repo)])
    assert rc == 0


def test_sentinel_last_line_is_pass(repo, capsys):
    rc = audit.main(["--repo", str(repo)])
    out = capsys.readouterr().out.strip().splitlines()
    assert out[-1].startswith("VERDICT=PASS")
    assert rc == 0


def test_json_output_valid_and_carries_sentinel(repo, capsys):
    rc = audit.main(["--repo", str(repo), "--json"])
    out = capsys.readouterr().out.strip().splitlines()
    assert out[-1].startswith("VERDICT=")
    parsed = json.loads("\n".join(out[:-1]))
    assert parsed["ok"] is True
    assert isinstance(parsed["checks"], list) and parsed["checks"]
    assert rc == 0


def test_never_writes_anything(repo):
    (repo / "corpus_friction").mkdir()
    (repo / "corpus_friction" / "a.jsonl").write_text('{"x": 1}\n')
    before = {p: p.stat().st_mtime for p in repo.rglob("*") if p.is_file()}
    audit.main(["--repo", str(repo)])
    after = {p: p.stat().st_mtime for p in repo.rglob("*") if p.is_file()}
    assert before == after and set(before) == set(after)
