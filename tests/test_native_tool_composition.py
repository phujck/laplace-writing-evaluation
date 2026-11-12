"""The deployed tool offer, exact owner help, mediation and guarded receipt agree."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import jsonschema
import pytest

from laplace.core import grammar
from laplace.manuscript import project_structure
from laplace.native import tools as writing_tools
from test_project_structure import _fixture

TREE = Path(__file__).resolve().parents[1]


def _invoke(root, fields, mode="work"):
    jsonschema.validate(fields, writing_tools.specification()["inputSchema"])
    return writing_tools.call(root, "book", mode, fields)


def _native_reconcile(root):
    index = _invoke(root, {"operation": "help", "payload": {}})
    concept = next(row for row in index["concepts"] if row["concept"] == "plan@plan")
    assert "run" in concept["verbs"]
    catalogue = _invoke(root, {"operation": "help", "payload": {"concept": concept["concept"]}})
    assert any(row["operation"] == "structure_change" for row in catalogue["catalogue"])
    detail = _invoke(root, {"operation": "help", "payload": {
        "operation": "structure_change", "variant": "reconcile"}})["action"]
    assert detail["native"]["available"] is True
    return detail["native"]["native_request"]


def test_offered_contract_to_help_to_guarded_owner_receipt(tmp_path):
    manuscript = _fixture(tmp_path)
    offered = writing_tools.specification()
    assert offered["name"] == "laplace_project"
    assert set(offered["inputSchema"]["properties"]["verb"]["enum"]) == set(grammar.VERBS)
    request = _native_reconcile(tmp_path)
    before = (manuscript / "projection_plan.json").read_bytes()
    stale = {**request, "expected": [str(grammar.mint("plan", "book", "f" * 64))]}
    refused = _invoke(tmp_path, stale)
    assert refused["ok"] is False
    assert refused["refused"]["kind"] == "identity-stale"
    assert refused["refused"]["needed"]["expected"] == request["expected"]
    assert refused["refused"]["owner"]["operation"] == "structure_change"
    assert (manuscript / "projection_plan.json").read_bytes() == before
    repaired = {**stale, **refused["refused"]["needed"]}
    receipt = _invoke(tmp_path, repaired)
    assert receipt["ok"] is True and receipt["outcome"] == "applied"
    assert receipt["owner"]["operation"] == "structure_change"
    assert receipt["banked_row"]["verb"] == request["verb"]
    assert receipt["owner_response"]["ok"] is True
    assert project_structure.state("book", tmp_path)["revision"]


def test_semantic_spelling_preserves_review_and_selected_project_guards(tmp_path):
    manuscript = _fixture(tmp_path)
    request = _native_reconcile(tmp_path)
    before = (manuscript / "projection_plan.json").read_bytes()
    denied = _invoke(tmp_path, request, mode="review")
    assert denied["ok"] is False and "review" in denied["refused"]["said"]
    wrong = _invoke(tmp_path, {**request, "target": "other"})
    assert wrong["ok"] is False and wrong["refused"]["needed"] == {"target": "book"}
    assert (manuscript / "projection_plan.json").read_bytes() == before


def test_mixed_unknown_and_wrong_type_envelopes_are_never_ignored(tmp_path):
    request = {"verb": "read", "concept": "contract@project", "target": "book",
               "expected": [], "payload": {}, "by": ""}
    for fields in ({**request, "operation": "help"}, {**request, "payload": []},
                   {**request, "extra": True}, {**request, "target": 3}):
        with pytest.raises(ValueError, match="offered contract"):
            writing_tools.call(tmp_path, "book", "work", fields)
    jsonschema.validate(request, writing_tools.specification()["inputSchema"])
    assert _invoke(tmp_path, request)["owner"]["operation"] == "help"


def test_legacy_calls_and_shim_discovery_remain_available(tmp_path):
    _fixture(tmp_path)
    old = {"operation": "help", "payload": {"operation": "session_settings"}}
    result = _invoke(tmp_path, old)
    assert result == writing_tools.execute(tmp_path, "book", "work", "help", old["payload"])
    assert result["action"]["native"]["available"] is False
    assert result["action"]["native"]["why"]


def test_actual_mcp_offer_and_call_use_the_same_semantic_contract(tmp_path):
    _fixture(tmp_path)
    semantic = {"verb": "read", "concept": "contract@project", "target": "book",
                "expected": [], "payload": {"operation": "structure_change", "variant": "reconcile"}, "by": ""}
    messages = [{"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                    "name": "laplace_project", "arguments": semantic}}]
    done = subprocess.run([str(TREE / "scripts/laplace-python"), "-m", "laplace.native.tools",
                           "--root", str(tmp_path), "--project", "book", "--mode", "work"],
                          input="\n".join(json.dumps(row) for row in messages) + "\n",
                          text=True, capture_output=True, timeout=15, cwd=TREE)
    assert done.returncode == 0, done.stderr
    listed, called = [json.loads(line) for line in done.stdout.splitlines()]
    tool = listed["result"]["tools"][0]
    assert tool["name"] == writing_tools.specification()["name"]
    assert tool["inputSchema"] == writing_tools.specification()["inputSchema"]
    jsonschema.validate(semantic, tool["inputSchema"])
    receipt = json.loads(called["result"]["content"][0]["text"])
    assert receipt["ok"] is True and receipt["owner"]["operation"] == "help"
    assert receipt["owner_response"]["action"]["native"]["native_request"]["verb"] == "run"


def test_codex_callback_consumes_the_actual_offered_semantic_shape(tmp_path, monkeypatch):
    from laplace.writing import provider as writing_provider
    _fixture(tmp_path)
    calls, offers = [], []
    semantic = {"verb": "read", "concept": "contract@project", "target": "book",
                "expected": [], "payload": {}, "by": ""}

    class Connection:
        def __init__(self, cwd, event, tool_handler=None, **kwargs):
            self.event, self.tool_handler = event, tool_handler
        def request(self, method, params):
            if method == "thread/start":
                offers.extend(params["dynamicTools"])
                return {"thread": {"id": "fixture-thread"}}
            if method == "turn/start":
                jsonschema.validate(semantic, offers[0]["inputSchema"])
                calls.append(self.tool_handler({"threadId": "fixture-thread", "tool": "laplace_project",
                                               "arguments": semantic}))
                self.event({"method": "turn/completed", "params": {
                    "threadId": "fixture-thread", "turn": {"id": "fixture-turn", "status": "completed"}}})
                return {"turn": {"id": "fixture-turn"}}
            raise AssertionError(method)
        def close(self):
            pass

    monkeypatch.setattr(writing_provider, "CodexConnection", Connection)
    writing_provider.WritingTurn(tmp_path, "codex", "", "medium", None,
                                lambda event: None, project="book",
                                logical_turn_id="fixture-logical-turn").run("Inspect existing owner help.")
    assert offers == [writing_tools.specification()]
    assert calls[0]["owner"]["operation"] == "help" and calls[0]["outcome"] == "read"
    assert calls[0]["owner_response"]["concepts"]


def test_exact_help_consumes_concrete_owner_context_and_never_ignores_it(tmp_path):
    _fixture(tmp_path)
    detail = _invoke(tmp_path, {"operation": "help", "payload": {
        "operation": "concept", "context": {"node": "res:one"}}})["action"]
    assert detail["example"]["node"] == "res:one"
    assert detail["native"]["available"] is True
    request = detail["native"]["native_request"]
    assert request["target"] == "book::res:one"
    assert request["payload"]["node"] == "res:one"
    receipt = _invoke(tmp_path, request)
    assert receipt["ok"] is True and receipt["outcome"] == "read"
    assert receipt["owner"]["operation"] == "concept"
    for context in ({"file": "other.tex"}, {"node": 3}, {"node": "res:one", "unknown": "x"}):
        with pytest.raises(ValueError):
            _invoke(tmp_path, {"operation": "help", "payload": {"operation": "concept", "context": context}})


def test_semantic_owner_runtime_does_not_require_git_or_provider_processes(tmp_path, monkeypatch):
    _fixture(tmp_path)
    def forbid(*args, **kwargs):
        raise AssertionError("native owner runtime must not launch processes")
    monkeypatch.setattr(subprocess, "run", forbid)
    request = _native_reconcile(tmp_path)
    receipt = _invoke(tmp_path, request)
    assert receipt["ok"] is True


def test_missing_owner_identities_are_never_advertised_as_ready_native_examples(tmp_path):
    detail = _invoke(tmp_path, {"operation": "help", "payload": {
        "operation": "structure_change", "variant": "reconcile"}})["action"]
    assert detail["native"]["available"] is False
    assert "identity unavailable" in detail["native"]["why"]
    assert detail["expected"] and all(row.get("needs") or row.get("token") or row.get("absent")
                                      or row.get("closes") for row in detail["expected"])
