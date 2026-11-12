"""A finished wave banks its own rows, with nobody remembering a command.

The seam this closes (Atlas F1, packet C2): ``scripts/distil.py`` grew producers that turn a
finished wave into engine rows, but the path a wave actually runs on - the ``atlas-wave``
workflow script - never called them, so every wave banked rows only if a human remembered to.
The script now ends in a two-command banking step; these tests exercise exactly those two
commands over a FIXTURE run, in a temporary root, so the live stores are never written.

They also hold the two rules the banking step depends on:
 * the run is identified BY CONTENT (the plan's packet labels against the run journal's started
   labels), never by "the newest run" - which would bank the wrong wave the moment two run;
 * the wave's exact returns are deposited under ``evidence/WORKFLOWS/<run_id>/`` so the reader's
   own containment rule (``laplace.pipeline.workflow`` :617-620) lifts a ``result_ref`` and the
   ``run_path`` it serves resolves - instead of the containment rule being widened.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _distil():
    """scripts/distil.py is a script, not a package: load it by path, once per test."""
    spec = importlib.util.spec_from_file_location("distil_under_test", ROOT / "scripts" / "distil.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["distil_under_test"] = module
    spec.loader.exec_module(module)
    return module


def _fixture_run(tmp_path: Path, labels=("A1-alpha", "A2-beta"), session="s1") -> Path:
    """A wave-shaped run directory in the harness's own layout: the launched/started/result
    journal it writes, under <projects>/<project>/<session>/subagents/workflows/wf_*/."""
    run = tmp_path / "projects" / "a-project" / session / "subagents" / "workflows" / f"wf_{session}-abc"
    run.mkdir(parents=True)
    rows = [{"type": "launched"}]
    for n, label in enumerate(labels, 1):
        rows += [
            {"type": "started", "agentId": f"agent-b{n}", "key": f"k{n}", "label": f"build:{label}",
             "phase": "Build"},
            {"type": "result", "agentId": f"agent-b{n}", "key": f"k{n}",
             "result": {"output": f"/out/{label}.json", "summary": "built"}},
            {"type": "started", "agentId": f"agent-j{n}", "key": f"j{n}", "label": f"judge:{label}:r1",
             "phase": "Judge"},
            {"type": "result", "agentId": f"agent-j{n}", "key": f"j{n}",
             "result": {"accepted": n == 1, "checked": ["a", "b"], "deficiencies": []
                        if n == 1 else [{"item": "x", "problem": "p", "evidence": "e",
                                         "done_looks_like": "d"}]}},
        ]
    # the banking agent's own return: it must NOT appear in the returns file it is writing
    rows += [{"type": "started", "agentId": "agent-bank", "key": "kb", "label": "bank", "phase": "Bank"},
             {"type": "result", "agentId": "agent-bank", "key": "kb", "result": {"wave_rows": "{}"}}]
    (run / "journal.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return run


def _plan(tmp_path: Path, wave="FIXTURE-wave", labels=("A1-alpha", "A2-beta")) -> Path:
    path = tmp_path / "plan.json"
    path.write_text(json.dumps({"wave": wave, "plan_path": str(path),
                                "agents": [{"label": x, "output": f"/out/{x}.json"} for x in labels]}),
                    encoding="utf-8")
    return path


def _ns(**kw):
    return types.SimpleNamespace(**kw)


def test_the_run_is_found_from_the_plans_own_packet_labels(tmp_path, monkeypatch):
    distil = _distil()
    run = _fixture_run(tmp_path)
    decoy = _fixture_run(tmp_path, labels=("Z9-other",), session="s2")
    monkeypatch.setattr(distil, "_WF_JOURNALS",
                        str(tmp_path / "projects" / "*" / "*" / "subagents" / "workflows"
                            / "wf_*" / "journal.jsonl"))

    found, why = distil._find_run_dir({"A1-alpha", "A2-beta"})
    assert Path(found) == run, why
    assert Path(found) != decoy
    assert why["journals_scanned"] == 2, "both runs were considered; the right one was chosen"

    missing, why = distil._find_run_dir({"A1-alpha", "NOT-A-PACKET"})
    assert missing is None and "no run journal" in why["why"]


def test_a_wave_banks_its_own_rows_once_and_the_ref_lifts(tmp_path, monkeypatch):
    distil = _distil()
    run = _fixture_run(tmp_path)
    plan = _plan(tmp_path)
    root = tmp_path / "repo"
    (root / "contract").mkdir(parents=True)
    monkeypatch.setattr(distil, "ROOT", str(root))
    monkeypatch.setattr(distil, "WAVES_DIR", str(root / "evidence" / "ATLAS_PROGRAMME" / "waves"))

    rc = distil.cmd_wave_returns(_ns(plan=str(plan), wave=None, run_dir=str(run), out=None))
    assert rc == 0
    returns = json.loads((root / "evidence" / "ATLAS_PROGRAMME" / "waves" / "FIXTURE-wave"
                          / "returns.json").read_text(encoding="utf-8"))
    # four returns, and the banking agent's own return excluded (else a resume changes the bytes)
    assert len(returns["returns"]) == 4
    assert all("wave_rows" not in json.dumps(r["result"]) for r in returns["returns"])

    assert distil.cmd_wave_rows(_ns(waves=["FIXTURE-wave"])) == 0
    ledger = [json.loads(x) for x in (root / "contract" / "dispatches.jsonl")
              .read_text(encoding="utf-8").splitlines() if x.strip()]
    workflow_rows = [r for r in ledger if r.get("record") == "workflow"]
    assert len(workflow_rows) == 1 and workflow_rows[0]["wave"] == "FIXTURE-wave"
    assert workflow_rows[0]["accepted"] is False, "one judge rejected: the wave is not accepted"
    assert len([r for r in ledger if r.get("record") == "dispatch"]) == 4
    judged = [json.loads(x) for x in (root / "contract" / "judged_verdicts.jsonl")
              .read_text(encoding="utf-8").splitlines() if x.strip()]
    assert sorted(r["verdict"] for r in judged) == ["ACCEPTED", "REJECTED"]

    # the deposit: the reader's containment rule is satisfied, so the ref rides in the projection
    run_id = workflow_rows[0]["id"]
    deposit = root / "evidence" / "WORKFLOWS" / run_id / "returns.json"
    assert deposit.is_file(), "the run_path the reader serves must resolve"
    from laplace.pipeline.workflow import recent_workflows
    served = recent_workflows(root, limit=1)["workflows"][0]
    assert served["run_id"] == run_id and served["stage"] == "fixture-wave"
    assert served["result_ref"]["path"] == f"evidence/WORKFLOWS/{run_id}/returns.json"
    assert (root / served["run_path"]).is_dir()

    # IDEMPOTENCE: the same command again banks nothing at all
    before = (root / "contract" / "dispatches.jsonl").read_bytes()
    assert distil.cmd_wave_rows(_ns(waves=["FIXTURE-wave"])) == 0
    assert (root / "contract" / "dispatches.jsonl").read_bytes() == before
