from pathlib import Path

import pytest

from atlas.errors import RuntimePolicyRefused
from atlas.runtime import SYSTEM_INTERPRETER, collect_runtime_receipt

ROOT = Path(__file__).resolve().parents[2]


def test_system_interpreter_emits_typed_cpu_receipt() -> None:
    receipt = collect_runtime_receipt(ROOT, observed_at="2026-08-24T12:00:00Z")
    assert receipt.executable == str(SYSTEM_INTERPRETER)
    assert receipt.repo_venv_refused is True
    assert receipt.device.selected == "cpu"
    assert receipt.device.available == ("cpu",)
    assert receipt.device.utilization == {"cpu": None}


def test_repo_venv_is_refused_before_symlink_resolution() -> None:
    lexical_alias = ROOT / ".venv" / "bin" / "python"
    with pytest.raises(RuntimePolicyRefused, match="repository .venv"):
        collect_runtime_receipt(ROOT, executable=lexical_alias)


def test_unavailable_device_fallback_is_explicit_and_acknowledged() -> None:
    receipt = collect_runtime_receipt(
        ROOT,
        requested_device="cuda:0",
        observed_at="2026-08-24T12:00:00Z",
    )
    assert receipt.device.selected == "cpu"
    assert receipt.device.fallbacks[0].from_device == "cuda:0"
    assert receipt.device.fallbacks[0].acknowledged is True
