from __future__ import annotations

import shutil
from pathlib import Path

from scripts import audit_dispatch_gate as audit

ROOT = Path(__file__).resolve().parents[1]


def _fixture(tmp_path: Path) -> Path:
    for rel in audit.WORKFLOWS:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, target)
    raptor = Path("src/atlas/tools/raptor_fold.py")
    (tmp_path / raptor).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / raptor, tmp_path / raptor)
    return tmp_path


def test_live_inventory_is_25_files_81_gated_calls_and_zero_raw() -> None:
    got = audit.audit(ROOT)
    assert got["status"] == "PASS"
    assert got["workflow_files"] == 25
    assert got["gated_agent_calls"] == 81
    assert got["raw_agent_calls"] == 0
    assert got["raptor_raw"] is False


def test_planted_82nd_raw_call_refuses(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    planted = root / "scripts" / "planted_raw.mjs"
    planted.write_text("await agent('raw', {label: 'raw'})\n", encoding="utf-8")
    got = audit.audit(root)
    assert got["status"] == "REFUSED"
    assert any(row.startswith("UNREGISTERED_PROVIDER_PATH:scripts/planted_raw.mjs")
               for row in got["violations"])
    assert any(row.startswith("RAW_AGENT:scripts/planted_raw.mjs")
               for row in got["violations"])


def test_provider_alias_and_raptor_reordering_refuse(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    workflow = root / audit.WORKFLOWS[0]
    workflow.write_text(
        workflow.read_text(encoding="utf-8") + "\nconst bypass = agent\n",
        encoding="utf-8",
    )
    raptor = root / "src/atlas/tools/raptor_fold.py"
    source = raptor.read_text(encoding="utf-8")
    source = source.replace(
        "_verify_dispatch_admission(prompt, label, admission)",
        "_verify_dispatch_admission_after_provider(prompt, label, admission)",
        1,
    )
    raptor.write_text(source, encoding="utf-8")
    got = audit.audit(root)
    assert got["status"] == "REFUSED"
    assert any(row.startswith("PROVIDER_ALIAS:") for row in got["violations"])
    assert "RAW_RAPTOR_CLAUDE_P" in got["violations"]
