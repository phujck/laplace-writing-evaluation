from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from atlas.errors import ArmUnavailable
from atlas.tools import raptor_fold


def test_gate_refusal_starts_zero_claude_processes(monkeypatch: pytest.MonkeyPatch) -> None:
    commands: list[list[str]] = []

    def run(cmd: list[str], **_kwargs: object) -> SimpleNamespace:
        commands.append(cmd)
        return SimpleNamespace(returncode=2, stdout="", stderr="DISPATCH_REFUSED")

    monkeypatch.setattr(raptor_fold.subprocess, "run", run)
    with pytest.raises(ArmUnavailable):
        raptor_fold.dispatch_batch("prompt", "L0-B00", 1, admission=None)
    assert len(commands) == 1
    assert commands[0][0] == "node"
    assert not any(command[:2] == ["claude", "-p"] for command in commands)


def test_gate_pass_is_immediately_followed_by_exactly_one_claude_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    def run(cmd: list[str], **_kwargs: object) -> SimpleNamespace:
        commands.append(cmd)
        if cmd[0] == "node":
            return SimpleNamespace(returncode=0, stdout='{"status":"ADMITTED"}', stderr="")
        payload = {
            "usage": {},
            "modelUsage": {},
            "result": json.dumps([{"cluster_id": "c1", "summary": "exact"}]),
        }
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(raptor_fold.subprocess, "run", run)
    got = raptor_fold.dispatch_batch(
        "prompt", "L0-B00", 1, admission={"exact": True}
    )
    assert [command[0] for command in commands] == ["node", "claude"]
    assert commands[1][:2] == ["claude", "-p"]
    assert got["items"] == [{"cluster_id": "c1", "summary": "exact"}]
