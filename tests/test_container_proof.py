"""Leg C bite C3 -- the fresh-container proof, wired as a SLOW/e2e test.

This drives ``scripts/container_proof.py`` end to end: a cold local file:// clone of
the current branch, the reconstructed hook bootstrap (uv venv + editable install), the
FIXED ensure_tex idempotency, the grade-0 wake from the clone, one mechanical detect
round on SSG, a served-scanner Playwright smoke of the review landing view, and the
clone's pytest suite (green modulo the named synctex environmental set). It is HEAVY
(a full clone + venv + suite), so it is GATED OUT of the default run:

  * default ``pytest tests/`` -> SKIPPED (so the fast suite stays fast, and so the
    proof's own in-clone suite leg does not re-enter this test -> no recursion).
  * run it explicitly with the env switch:

        LAPLACE_RUN_CONTAINER_PROOF=1 python -m pytest tests/test_container_proof.py -q

    or, equivalently, run the script directly:

        python scripts/container_proof.py /path/to/workdir

The ``container_proof`` marker allows ``pytest -m container_proof`` selection; the env
switch above remains the master gate.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / "scripts" / "container_proof.py"

pytestmark = [
    pytest.mark.container_proof,
    pytest.mark.skipif(
        os.environ.get("LAPLACE_RUN_CONTAINER_PROOF") != "1",
        reason="fresh-container proof is slow/e2e; set LAPLACE_RUN_CONTAINER_PROOF=1 to run",
    ),
]


def test_fresh_container_proof(tmp_path):
    """A cold clone surfaces the whole pipeline: every leg green, overall exit 0."""
    assert _SCRIPT.is_file(), f"missing {_SCRIPT}"
    workdir = tmp_path / "cproof"
    env = dict(os.environ)
    env.pop("LAPLACE_RUN_CONTAINER_PROOF", None)  # the script must not recurse into pytest
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), str(workdir)],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=3600,
    )
    report_path = workdir / "proof_report.json"
    assert report_path.is_file(), (
        "no proof report emitted\n--- stdout ---\n" + proc.stdout[-2000:]
        + "\n--- stderr ---\n" + proc.stderr[-2000:]
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    failed = [s for s in report["proof_steps"] if not s["ok"]]
    assert report["overall"] == "PASS" and proc.returncode == 0, (
        "container proof FAILED; failing legs: "
        + json.dumps(failed, indent=2)
        + "\n--- stdout tail ---\n" + proc.stdout[-2000:]
    )
