"""Exercise the compile-only door with real reconstruction and compilation."""
import json

import pytest

from laplace.representation import custody_mode
from laplace.engine import descent
from scripts import dispatch_codex as door


@pytest.mark.parametrize("flags,carrier", [([], "compile-only"),
    (["--compile-only"], "compile-only"), (["--carrier", "claude-agent"], "claude-agent")])
def test_compile_carriers(tmp_path, monkeypatch, capsys, flags, carrier):
    monkeypatch.setattr(door, "ROOT", tmp_path)
    monkeypatch.setattr(descent, "__file__", str(tmp_path / "src/laplace/engine/descent.py"))
    monkeypatch.setattr(custody_mode, "is_off", lambda *_: True)
    monkeypatch.setattr(custody_mode, "read", lambda *_: {"mode": "OFF", "id": "test"})
    (tmp_path / "node.md").write_text("Exact content.\n", encoding="utf-8")
    assert door.main(["node.md", "verify the node", "--model", "test-model", *flags]) == 0
    row = json.loads(capsys.readouterr().out)
    assert row["status"] == "COMPILED"
    assert row["carrier"] == carrier
    assert row["admission"]["status"] == "ADMITTED"
    out = tmp_path / row["out_dir"]
    assert json.loads((out / "row.json").read_text()) == row
    packet = json.loads((out / "packet.json").read_text())
    assert packet["model"] == row["packet_model_stamp"]
    prompt = (out / "prompt.md").read_text()
    assert prompt == packet["prompt"]
    assert row["prompt_handle"] == door._sha(prompt)
    ledger = [json.loads(line) for line in (tmp_path / door.LEDGER).read_text().splitlines()]
    assert ledger == [row]
    assert row["record"] == "dispatch"
    assert row["gpu"]["visible"] is None
    assert "<!-- EXECUTION-FENCE -->" in prompt


@pytest.mark.parametrize("flags", [["--run", "--compile-only"],
    ["--run", "--carrier", "claude-agent"], ["--carrier", "codex-cli"]])
def test_conflicting_execution_modes_refused(flags):
    with pytest.raises(SystemExit) as exc:
        door.main(["node.md", "verify the node", *flags])
    assert exc.value.code == 2
