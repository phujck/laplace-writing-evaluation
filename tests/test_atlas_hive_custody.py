"""Custody boundary for the Atlas hived-store morphology.

The causal ledger and its content-addressed bodies are one authority object.  A
fresh clone carrying only the ledger would contain valid-looking handles that can
never descend, so hives must be trackable.  The search/graph index is derived and
must remain ignored.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _ignored(path: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "check-ignore", "-v", path],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_authority_hives_are_trackable_with_their_ledger() -> None:
    probe = _ignored("atlas/stores/blueprint/hives/ab/custody-probe.zlib")
    assert probe.returncode == 1, (
        "a blueprint hive is ignored, so a committed ledger would carry dangling handles: "
        + probe.stdout
    )


def test_disposable_projection_index_remains_ignored() -> None:
    probe = _ignored("atlas/stores/blueprint/conceptric.index.sqlite3")
    assert probe.returncode == 0
    assert "conceptric.index.sqlite3" in probe.stdout
