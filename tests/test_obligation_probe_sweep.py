"""tests/test_obligation_probe_sweep.py — WO-20260820-probe-strength-declaration
and the engine_ledger wiring from WO-20260820-ledger-semantics-hardening."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

_spec = importlib.util.spec_from_file_location(
    "obligation_probe_sweep", REPO / "scripts" / "obligation_probe_sweep.py")
ops = importlib.util.module_from_spec(_spec)
sys.modules["obligation_probe_sweep"] = ops  # dataclass needs its module registered
_spec.loader.exec_module(ops)


# ---------------------------------------------------------------------------
# classify_probe_strength
# ---------------------------------------------------------------------------

def test_bare_test_dash_f_is_porcelain():
    assert ops.classify_probe_strength("test -f gate_task1.json") == "porcelain"


def test_bare_grep_chain_is_porcelain():
    assert ops.classify_probe_strength(
        "test -f gate_task1.json && grep kmeans work_orders.jsonl") == "porcelain"


def test_grep_own_text_is_porcelain():
    assert ops.classify_probe_strength(
        "grep -q 'write_skeleton' scripts/reembed.py") == "porcelain"


def test_python_dash_c_reading_a_store_is_content():
    cmd = ('.venv/bin/python -c "import json,sys;e=[x for x in '
           'json.load(open(\'localstate.json\'))[\'entries\']];sys.exit(0 if e else 1)"')
    assert ops.classify_probe_strength(cmd) == "content"


def test_python_dash_c_source_substring_check_is_content():
    cmd = ('.venv/bin/python -c "import sys;s=open(\'src/laplace/pipeline/release.py\')'
           '.read();sys.exit(0 if \'feedback\' in s else 1)"')
    assert ops.classify_probe_strength(cmd) == "content"


def test_pytest_invocation_is_behavior():
    cmd = ".venv/bin/python -m pytest tests -q -k essence_hygiene"
    assert ops.classify_probe_strength(cmd) == "behavior"


def test_project_import_with_call_is_behavior():
    cmd = ('.venv/bin/python -c "import sys;sys.path.insert(0,\'scripts\');'
           'import close_checklist as c;sys.exit(0 if c.some_check() else 1)"')
    assert ops.classify_probe_strength(cmd) == "behavior"


def test_project_import_without_call_is_content_not_behavior():
    cmd = ('.venv/bin/python -c "import sys;sys.path.insert(0,\'scripts\');'
           'import close_checklist as c;sys.exit(0 if \'fence_rate\' in c.FAIL_ELIGIBLE else 1)"')
    assert ops.classify_probe_strength(cmd) == "content"


def test_unrecognized_shape_falls_back_to_content_never_porcelain_or_behavior():
    assert ops.classify_probe_strength("some-arbitrary-command --flag") == "content"


def test_pytest_substring_inside_a_path_is_not_mistaken_for_a_pytest_run():
    # regression: a pytest tmp_path fixture's own directories are named like
    # /tmp/pytest-of-user/pytest-433/... — "pytest" appears as a \b-bounded word
    # there (hyphen is a non-word char) but is not a `pytest` shell token.
    cmd = ("python3 -c \"import json,sys;"
           "d=json.load(open('/tmp/pytest-of-x/pytest-433/marker.json'));"
           "sys.exit(0 if d.get('cured') else 1)\"")
    assert ops.classify_probe_strength(cmd) == "content"


# ---------------------------------------------------------------------------
# porcelain PASS is never proposed for strike-off (run_sweep integration)
# ---------------------------------------------------------------------------

def _write_ledger(tmp_path: Path, rows: list[dict]) -> Path:
    import json
    d = tmp_path / "corpus_friction"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "work_orders.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    (tmp_path / "contract").mkdir(parents=True, exist_ok=True)
    (tmp_path / "contract" / "promises.jsonl").write_text("", encoding="utf-8")
    return p


def _git_init(tmp_path: Path):
    import subprocess
    subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.email", "t@t.t"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "add", "-A"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=str(tmp_path), check=True)


def test_porcelain_pass_never_proposed_for_strike_off(tmp_path: Path):
    _write_ledger(tmp_path, [
        {"record": "work_order", "kind": "work-order", "id": "WO-porcelain",
         "status": "open", "accept": "test -f " + __file__,
         "done_means": "pass", "probe_cost": "cheap"},
    ])
    _git_init(tmp_path)
    results = ops.run_sweep(tmp_path, cheap_only=True, timeout=30)
    assert len(results) == 1
    r = results[0]
    assert r.verdict == "PASS"
    assert r.row.strength == "porcelain"
    assert r.proposed_strike_off is False


def test_content_pass_is_proposed_for_strike_off(tmp_path: Path):
    marker = tmp_path / "marker.json"
    marker.write_text('{"cured": true}', encoding="utf-8")
    accept = (
        f"python3 -c \"import json,sys;"
        f"d=json.load(open('{marker.as_posix()}'));"
        f"sys.exit(0 if d.get('cured') else 1)\""
    )
    _write_ledger(tmp_path, [
        {"record": "work_order", "kind": "work-order", "id": "WO-content",
         "status": "open", "accept": accept,
         "done_means": "pass", "probe_cost": "cheap"},
    ])
    _git_init(tmp_path)
    results = ops.run_sweep(tmp_path, cheap_only=True, timeout=30)
    r = results[0]
    assert r.verdict == "PASS"
    assert r.row.strength == "content"
    assert r.proposed_strike_off is True


def test_effective_status_reflects_resolution_join(tmp_path: Path):
    _write_ledger(tmp_path, [
        {"record": "work_order", "kind": "work-order", "id": "WO-consumed",
         "status": "open", "accept": "test -f " + __file__,
         "done_means": "pass", "probe_cost": "cheap"},
        {"record": "resolution", "kind": "", "id": "RES-consumed",
         "consumes": "WO-consumed", "status": "resolved",
         "evidence": ["commit:consumed"]},
    ])
    _git_init(tmp_path)
    results = ops.run_sweep(tmp_path, cheap_only=True, timeout=30)
    row = next(r for r in results if r.row.id == "WO-consumed")
    assert row.effective_status == "resolved"
    assert row.status_reason == "consumed_by:RES-consumed"
    assert row.row.stored_status == "open"


def test_report_carries_strength_and_status_drift_columns(tmp_path: Path):
    _write_ledger(tmp_path, [
        {"record": "work_order", "kind": "work-order", "id": "WO-x",
         "status": "open", "accept": "test -f " + __file__,
         "done_means": "pass", "probe_cost": "cheap"},
        {"record": "resolution", "kind": "", "id": "RES-x",
         "consumes": "WO-x", "status": "resolved", "evidence": ["commit:x"]},
    ])
    _git_init(tmp_path)
    results = ops.run_sweep(tmp_path, cheap_only=True, timeout=30)
    report = ops.to_report(results, cheap_only=True)
    row = report["rows"][0]
    assert row["strength"] == "porcelain"
    assert row["stored_status"] == "open"
    assert row["effective_status"] == "resolved"
    assert row["status_drifted"] is True
    s = report["summary"]
    assert "porcelain" in s and "content" in s and "behavior" in s
    assert "porcelain_pass_withheld_from_strike_off" in s
    assert "status_drifted_from_stored" in s
