"""The dispatch-model law, enforced (his, 2026-07-11): agents are opus-level or less.

Three seams, three tests: the compiler stamps and clamps; the static audit holds green
on the real tree; the audit goes red on a planted violation (proving it can catch one).
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from laplace.representation import custody_mode
from laplace.engine import descent
from laplace.pipeline import schema
from laplace.pipeline.dispatch import compile_dispatch

ROOT = Path(__file__).resolve().parents[1]


def _load_audit():
    spec = importlib.util.spec_from_file_location(
        "audit_dispatch_models", ROOT / "scripts" / "audit_dispatch_models.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("audit_dispatch_models", mod)
    spec.loader.exec_module(mod)
    return mod


def test_compiled_dispatch_carries_clamped_model(tmp_path, monkeypatch):
    node, goal = "small.md", "render the manuscript"
    (tmp_path / node).write_text("Exact fixture content.\n", encoding="utf-8")
    # descend derives its repository root from the module location.
    monkeypatch.setattr(descent, "__file__", str(tmp_path / "src/laplace/engine/descent.py"))
    reconstruction = descent.descend(kind="repository-file", reference=node, goal=goal,
                                     content_budget=1024, record_telemetry=False)
    assert reconstruction["content_status"] == "COMPLETE"
    reconstruction.update(goal=goal, authority_write="none", content_status="COMPLETE")
    monkeypatch.setattr(custody_mode, "is_off", lambda *_: True)
    monkeypatch.setitem(schema.WORKER_MODEL, "render", ("opus-max", "high"))
    out = compile_dispatch(node, goal, worker="render", repo_root=tmp_path,
                           reconstruction=reconstruction)
    assert "error" not in out, out
    assert out["reconstruction_admission"]["admission_result"]["status"] == "ADMITTED"
    assert out["model"] == schema.MAX_MODEL
    assert out["effort"]


@pytest.mark.parametrize("custody_off", [False, True])
def test_missing_reconstruction_refused(monkeypatch, custody_off):
    monkeypatch.setattr(custody_mode, "is_off", lambda *_: custody_off)
    out = compile_dispatch("whole", "render the manuscript", worker="render")
    assert out["error"] == "dispatch reconstruction admission refused: MISSING_RECONSTRUCTION"
    assert out["reconstruction_admission"]["admission_result"] == {
        "status": "REFUSED", "reason": "MISSING_RECONSTRUCTION"}


def test_clamp_never_exceeds_ceiling():
    assert schema.clamp_model("opus") == "opus"
    assert schema.clamp_model("haiku") == "haiku"
    # anything unknown (including a hypothetical above-opus tier) lands AT the ceiling
    assert schema.clamp_model("opus-max") == schema.MAX_MODEL
    assert schema.clamp_model("fable") == schema.MAX_MODEL


def test_audit_green_on_real_tree():
    mod = _load_audit()
    assert mod.audit(ROOT) == [], "a workflow or dispatch row violates the model law"


def test_audit_red_on_planted_violation(tmp_path):
    mod = _load_audit()
    wf = tmp_path / "scripts"
    wf.mkdir()
    (wf / "wf_planted.mjs").write_text(
        "const a = await agent('x', {model: 'opus-max'})\n", encoding="utf-8")
    violations = mod.audit(tmp_path)
    assert len(violations) == 1
    assert violations[0][2] == "opus-max"


@pytest.mark.parametrize("surface", ["dispatch", "corpus"])
@pytest.mark.parametrize("defect", [None, "packet_model_stamp", "executor", "codex_model", "sandbox"])
def test_audit_dispatch_row_surfaces(tmp_path, surface, defect):
    mod = _load_audit()
    row = {"record": "dispatch" if surface == "dispatch" else "codex-dispatch", "packet_model_stamp": schema.MAX_MODEL,
           "executor": "codex-cli", "codex_model": "gpt-5.5", "sandbox": "read-only"}
    if defect == "packet_model_stamp":
        row[defect] = "opus-max"
    elif defect:
        del row[defect]
    path = tmp_path / ("contract/dispatches.jsonl" if surface == "dispatch"
                       else "corpus_friction/nested/dispatches.jsonl")
    path.parent.mkdir(parents=True)
    # A non-dispatch corpus record must not be audited as a dispatch.
    prefix = json.dumps({"record": "work-order"}) + "\n" if surface == "corpus" else ""
    path.write_text(prefix + json.dumps(row) + "\n", encoding="utf-8")
    report = mod.scan(tmp_path)
    assert (report.dispatch_rows, report.corpus_rows) == (
        (1, 0) if surface == "dispatch" else (0, 1))
    if defect:
        assert len(report.violations) == 1
        assert report.violations[0].path == path
        assert report.violations[0].token == (
            "opus-max" if defect == "packet_model_stamp" else f"<missing {defect}>")
        assert mod.main(["--root", str(tmp_path)]) == 1
    else:
        assert report.violations == []
        assert mod.main(["--root", str(tmp_path)]) == 0


@pytest.mark.parametrize("raw", ['{"record":', 'null', '{}'])
def test_audit_cannot_pass_unverifiable_dispatch_row(tmp_path, raw):
    path = tmp_path / "contract/dispatches.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(raw, encoding="utf-8")
    assert _load_audit().audit(tmp_path)
