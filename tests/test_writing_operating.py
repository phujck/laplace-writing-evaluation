from __future__ import annotations

import json
from pathlib import Path
import threading

import pytest

from laplace.web import authoring as authoring_surface
from laplace.manuscript import manuscript_source, review_surface, writing_style
from laplace.writing import operating as writing_operating, provider as writing_provider
from laplace.projects import library as writing_projects
from laplace.native import tools as writing_tools
from laplace.writing import reads
from laplace.writing import records
from laplace.writing import turn_jobs
from laplace.writing import session_reads
from laplace.writing import turn_admission
from laplace.writing import turn_context
from laplace.manuscript import source_application
from laplace.writing.records import _fold as records_fold
from laplace.representation import writing_bodies
from laplace.pipeline import authoring
from laplace.core import checkout


def test_revise_output_schema_is_strict_for_every_declared_edit_field():
    item = writing_provider.EDIT_SCHEMA["properties"]["edits"]["items"]

    assert set(item["required"]) == set(item["properties"])
    assert item["properties"]["develops"]["type"] == "array"
    assert item["properties"]["evidence_refs"]["type"] == "array"


def test_codex_process_controls_are_supported_and_server_names_are_derived():
    overrides=writing_operating.codex_process_config_overrides(['z_server','alpha'])
    # A live Luna-low plant proved this feature owns the client-executed dynamic gateway:
    # disabling it produced completed text with zero laplace_project reads.
    assert 'code_mode_host' not in writing_operating.CODEX_PROCESS_DISABLED_FEATURES
    for feature in writing_operating.CODEX_PROCESS_DISABLED_FEATURES:
        assert f'features.{feature}=false' in overrides
    assert 'mcp_servers.alpha.enabled=false' in overrides
    assert 'mcp_servers.z_server.enabled=false' in overrides
    source=Path(writing_provider.__file__).read_text(encoding='utf-8')
    assert not any(name in source for name in ('node_repl','codex_apps','cua_repl'))
    with pytest.raises(ValueError,match='represented safely'):
        writing_operating.codex_process_config_overrides(['bad\nname'])
    with pytest.raises(ValueError,match='represented safely'):
        writing_operating.codex_process_config_overrides(['name.with.dot'])


def test_codex_connection_resolves_names_then_verifies_effective_closure(tmp_path,monkeypatch):
    launched=[]
    class Raw:
        def __init__(self,cwd,event=None,executable=None,tool_handler=None,launch_overrides=(),
                     send_initialized=True,**kwargs):
            self.launch_overrides=tuple(launch_overrides);self.closed=False;self.process=object()
            self.send_initialized=send_initialized
            launched.append(self)
        def request(self,method,params,timeout=30):
            if method=='config/read':
                return {'config':{'mcp_servers':{'fixture_server':{'enabled':False}}}}
            assert method=='mcpServerStatus/list'
            if len(launched)==1:
                return {'data':[{'name':'fixture_server','runtimeStatus':'connected',
                                 'tools':{'external_write':{}}}], 'nextCursor':None}
            return {'data':[{'name':'fixture_server','runtimeStatus':'disabled','tools':{}}],
                    'nextCursor':None}
        def close(self):self.closed=True
        def send(self,obj):return None
    monkeypatch.setattr(writing_provider,'_CodexRpcConnection',Raw)
    connection=writing_provider.CodexConnection(tmp_path,executable='/fixture/codex')
    assert len(launched)==2 and launched[0].closed
    assert launched[0].send_initialized is False and launched[1].send_initialized is True
    assert 'mcp_servers.fixture_server.enabled=false' in launched[1].launch_overrides
    assert connection.preflight=={'resolved_names':1,'effective_rows':1,
                                  'disabled_names':1,'closed':True}
    connection.close();assert launched[1].closed


def test_codex_connection_refuses_unknown_or_enabled_effective_server(tmp_path,monkeypatch):
    launched=[]
    class Raw:
        def __init__(self,cwd,event=None,executable=None,tool_handler=None,launch_overrides=(),
                     send_initialized=True,**kwargs):
            self.closed=False;self.process=object();launched.append(self)
        def request(self,method,params,timeout=30):
            if method=='config/read':
                return {'config':{'mcp_servers':{'fixture':{'enabled':False}}}}
            status='connected' if len(launched)==2 else 'notStarted'
            return {'data':[{'name':'fixture','runtimeStatus':status,'tools':{}}],
                    'nextCursor':None}
        def close(self):self.closed=True
        def send(self,obj):return None
    monkeypatch.setattr(writing_provider,'_CodexRpcConnection',Raw)
    with pytest.raises(writing_provider.ProviderError,match='non-project server'):
        writing_provider.CodexConnection(tmp_path,executable='/fixture/codex')
    assert len(launched)==2 and all(row.closed for row in launched)


def test_codex_tool_failures_are_banked_separately_from_successful_actions(tmp_path, monkeypatch):
    _project(tmp_path)

    class Connection:
        def __init__(self, cwd, event, tool_handler=None, **kwargs):
            self.event, self.tool_handler = event, tool_handler
        def request(self, method, params):
            if method == "thread/start":
                return {"thread": {"id": "writer-thread"}}
            if method == "turn/start":
                try:
                    self.tool_handler({"tool": "laplace_project", "threadId": "writer-thread",
                        "arguments": {"operation": "research_record", "payload": {"bad": True}}})
                except ValueError:
                    pass
                self.event({"method": "turn/completed", "params": {
                    "threadId": "writer-thread", "turn": {"id": "writer-turn", "status": "completed"}}})
                return {"turn": {"id": "writer-turn"}}
            raise AssertionError(method)
        def close(self): pass

    monkeypatch.setattr(writing_provider, "CodexConnection", Connection)
    monkeypatch.setattr(writing_tools, "execute", lambda *args, **kwargs: (_ for _ in ()).throw(
        ValueError("record requires label and key")))
    result = writing_provider.WritingTurn(
        tmp_path, "codex", "", "medium", None, lambda event: None,
        project="book", logical_turn_id="WT-failure").run("Exercise a failed tool.")
    rows = [json.loads(line) for line in (tmp_path / "contract" / "talk.jsonl").read_text().splitlines()]
    failure = next(row for row in rows if row.get("record") == "writing-tool-failure")

    assert result["status"] == "completed"
    assert failure["operation"] == "research_record"
    # THE ROW CARRIES A REFERENCE, THE READER CARRIES THE REQUEST (the whole synthesis).
    # `writing-tool-failure.payload` is held by custody at ANY size, so the gate's one
    # question per transport -- is this row's payload bounded? -- has one answer instead of
    # an answer that depends on how big the failing request happened to be.
    assert failure["payload"]["store"] == "contract/writing_bodies"
    assert writing_bodies.resolve_fields(
        failure, tmp_path, strict=True)["payload"] == {"bad": True}
    assert failure["error_type"] == "ValueError"
    assert "label and key" in failure["error"]


@pytest.fixture(autouse=True)
def _clear_controller_state():
    records_fold._CACHE.clear()
    turn_jobs._JOBS.clear()
    yield
    records_fold._CACHE.clear()
    turn_jobs._JOBS.clear()


def _project(root: Path) -> Path:
    (root / "contract").mkdir(parents=True, exist_ok=True)
    manuscript = root / "sources/book"
    manuscript.mkdir(parents=True)
    (manuscript / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\nOriginal prose.\n\\end{document}\n",
        encoding="utf-8",
    )
    status, result = writing_projects.import_source(
        {"name": "book", "title": "Book", "root": "sources/book/main.tex", "editable": True},
        root,
    )
    assert status == 201, result
    profile = root / "profiles/voice/book-v1.md"
    profile.parent.mkdir(parents=True)
    profile.write_text("# Book voice\nUse exact concrete language.\n", encoding="utf-8")
    current = writing_style.state("book", root)
    writing_style.save(
        "book",
        {
            "profile": "profiles/voice/book-v1.md",
            "guidance": "Explain the physical consequence before the implementation detail.",
            "expected_revision": current["revision"],
        },
        root,
    )
    return manuscript


def _wait(root: Path, started: dict) -> dict:
    job = turn_jobs._JOBS[started["turn_id"]]
    with job["condition"]:
        assert job["condition"].wait_for(lambda: job["done"], timeout=5)
    state = session_reads.session_state(root, started["session_id"])
    return next(row for row in state["turns"] if row["id"] == started["turn_id"])


def test_operating_brief_contains_selected_profile_guidance_and_role_permissions(tmp_path):
    _project(tmp_path)

    work = writing_operating.build("book", "work", tmp_path, {"surface": "project"})
    discuss = writing_operating.build("book", "discuss", tmp_path)

    assert work["writing_style"]["selected_profile"] == "profiles/voice/book-v1.md"
    assert work["writing_style"]["content"] == "# Book voice\nUse exact concrete language.\n"
    assert work["writing_style"]["guidance"].startswith("Explain the physical consequence")
    assert set(work["permissions"]) == reads.READS | reads.WRITES
    assert set(discuss["permissions"]) == reads.READS | reads.WRITES
    assert "store_artifact" in discuss["permissions"]
    assert work["tool_contract_digest"] == discuss["tool_contract_digest"]
    rendered = writing_operating.prompt(work)
    kernel = json.loads(writing_operating.kernel(work).split("\n", 1)[1])
    frame = json.loads(writing_operating.frame(work).split("\n", 1)[1])
    body = json.loads(writing_operating.body(work).split("\n", 1)[1])
    encoded = {**kernel, **frame, **body}
    assert rendered == (writing_operating.kernel(work) + writing_operating.BLOCK_JOIN
                        + writing_operating.body(work))
    assert set(kernel) & set(body) == set() and set(kernel) & set(frame) == set()
    assert body["writing_style"]["content"] == work["writing_style"]["content"]
    assert "planning_operations" not in encoded
    assert kernel["capability_guidance"]["discover"].startswith("Use help")
    assert kernel["orientation_layers"]["live"].startswith("live_scope")
    # the permissions are the TURN's, so they ride with the turn, not in the session block
    assert '"store_artifact"' in writing_operating.frame(work)
    assert '"store_artifact"' not in rendered and "store_artifact" in rendered
    moved = writing_operating.build("book", "work", tmp_path, {"surface": "manuscript", "node_id": "another"})
    assert writing_operating.prompt(moved) == rendered
    assert not {'workspace', 'selected_source', 'live_scope', 'digest'} & encoded.keys()


@pytest.mark.parametrize("native_id, expected_method", [(None, "thread/start"), ("old-thread", "thread/resume")])
def test_codex_initializes_with_the_operating_brief_and_resumes_without_reinjecting_it(
    tmp_path, monkeypatch, native_id, expected_method
):
    _project(tmp_path)
    brief = writing_operating.build("book", "work", tmp_path)
    calls = []

    class Connection:
        def __init__(self, cwd, event, tool_handler=None, **kwargs):
            self.event = event
            self.tool_handler = tool_handler

        def request(self, method, params):
            calls.append((method, params))
            if method in {"thread/start", "thread/resume"}:
                return {"thread": {"id": native_id or "new-thread"}, "model": "actual-model"}
            if method == "turn/start":
                self.event({"method": "item/completed", "params": {
                    "threadId": native_id or "new-thread", "turnId": "native-turn", "item": {
                    "type": "agentMessage", "id": "answer",
                    "text": json.dumps({"answer": "done", "edits": []}),
                }}})
                self.event({"method": "turn/completed", "params": {
                    "threadId": native_id or "new-thread", "turn": {"id": "native-turn", "status": "completed"}}})
                return {"turn": {"id": "native-turn"}}
            raise AssertionError(method)

        def close(self):
            pass

    monkeypatch.setattr(writing_provider, "CodexConnection", Connection)
    turn = writing_provider.WritingTurn(
        tmp_path, "codex", "", "medium", native_id, lambda event: None,
        "work", project="book", logical_turn_id="WT-contract",
    )
    turn.operating_brief = brief

    result = turn.run("Do the work.")

    assert result["status"] == "completed"
    method, params = next(call for call in calls if call[0] in {"thread/start", "thread/resume"})
    assert method == expected_method
    assert params["sandbox"] == "read-only"
    assert params["config"] == writing_operating.CODEX_SESSION_CONFIG
    assert params["config"]["web_search"] == "disabled"
    assert "sandbox_workspace_write" not in params["config"]
    if native_id:
        assert "developerInstructions" not in params
        assert {key: params["config"][key] for key in ("features.multi_agent", "project_doc_max_bytes")} == {"features.multi_agent": False, "project_doc_max_bytes": 0}
    else:
        assert params["baseInstructions"] == writing_operating.kernel(brief, "codex")
        assert params["developerInstructions"] == ""
        assert {key: params["config"][key] for key in ("features.multi_agent", "project_doc_max_bytes")} == {"features.multi_agent": False, "project_doc_max_bytes": 0}
        encoded = json.loads(writing_operating.body(brief).split("\n", 1)[1])
        assert encoded["writing_style"]["content"] == brief["writing_style"]["content"]
        assert writing_operating.body(brief) not in params["baseInstructions"]
        # the turn frame rides with the turn on this transport too
        turn = next(sent for method, sent in calls if method == "turn/start")
        assert writing_operating.body(brief) in turn["input"][0]["text"]
        assert writing_operating.frame(brief) in turn["input"][0]["text"]
        assert '"store_artifact"' in writing_operating.frame(brief)
    if native_id:
        assert params["threadId"] == native_id
        assert "dynamicTools" not in params
    else:
        assert params["dynamicTools"] == [writing_tools.specification()]


@pytest.mark.parametrize("native_id", [None, "resumed-writer"])
def test_codex_foreign_completion_cannot_replace_or_interrupt_the_writer(tmp_path, monkeypatch, native_id):
    _project(tmp_path)
    writing_tools.execute(tmp_path, "book", "work", "store_artifact", {
        "path": "inputs/owned.md", "before": None, "content": "The writer read this source.",
        "reason":"Retain the exact source for the writer completion test."})
    emitted = []
    connections = []
    writer_id = native_id or "new-writer"

    class Connection:
        def __init__(self, cwd, event, tool_handler=None, **kwargs):
            self.event, self.tool_handler = event, tool_handler
            self.closed = False
            connections.append(self)

        def message(self, thread_id, turn_id, text, phase="final_answer"):
            self.event({"method": "item/agentMessage/delta", "params": {
                "threadId": thread_id, "turnId": turn_id, "itemId": text, "delta": text}})
            self.event({"method": "item/completed", "params": {
                "threadId": thread_id, "turnId": turn_id,
                "item": {"type": "agentMessage", "id": text, "text": text, "phase": phase}}})

        def complete(self, thread_id, turn_id, status):
            self.event({"method": "turn/completed", "params": {
                "threadId": thread_id, "turn": {"id": turn_id, "status": status}}})

        def request(self, method, params):
            if method in {"thread/start", "thread/resume"}:
                return {"thread": {"id": writer_id}}
            assert method == "turn/start"
            # App-server may send these before returning the new turn ID.
            self.message(writer_id, "writer-turn", "Reading the source.\n", "commentary")
            self.message("child-thread", "child-turn", "Blocked helper without project tool.")
            self.complete("child-thread", "child-turn", "completed")
            self.message(writer_id, "previous-turn", "Stale writer reply.")
            self.complete(writer_id, "previous-turn", "failed")
            self.message(None, "writer-turn", "Unscoped reply.")

            def finish_writer():
                if self.closed:
                    return
                result = self.tool_handler({"threadId": writer_id, "turnId": "writer-turn",
                    "tool": "laplace_project", "arguments": {
                        "operation": "read_artifact", "payload": {"path": "inputs/owned.md"}}})
                self.message(writer_id, "writer-turn", result["content"])
                self.complete(writer_id, "writer-turn", "completed")

            self.timer = threading.Timer(0.05, finish_writer)
            self.timer.start()
            return {"turn": {"id": "writer-turn"}}

        def close(self):
            self.closed = True
            self.timer.join(timeout=1)

    monkeypatch.setattr(writing_provider, "CodexConnection", Connection)
    writer = writing_provider.WritingTurn(tmp_path, "codex", "", "medium", native_id,
                                         emitted.append, "discuss", project="book")
    result = writer.run("Read the source.")

    assert result["status"] == "completed"
    assert result["turn_id"] == "writer-turn"
    assert result["text"] == "The writer read this source."
    assert [e["text"] for e in emitted if e["type"] == "delta"] == [
        "Reading the source.\n", "The writer read this source."]
    assert connections[0].closed


def test_codex_uses_only_own_turn_token_usage_notification(tmp_path, monkeypatch):
    _project(tmp_path)

    class Connection:
        def __init__(self, cwd, event, tool_handler=None, **kwargs): self.event = event
        def request(self, method, params):
            if method == "thread/start": return {"thread": {"id": "writer-thread"}}
            if method == "turn/start":
                self.event({"method": "thread/tokenUsage/updated", "params": {
                    "threadId": "foreign-thread", "turnId": "foreign-turn", "tokenUsage": {
                        "last": {"cachedInputTokens": 1, "inputTokens": 2, "outputTokens": 3,
                                 "reasoningOutputTokens": 4, "totalTokens": 5},
                        "total": {"cachedInputTokens": 1, "inputTokens": 2, "outputTokens": 3,
                                  "reasoningOutputTokens": 4, "totalTokens": 5}}}})
                self.event({"method": "thread/tokenUsage/updated", "params": {
                    "threadId": "writer-thread", "turnId": "writer-turn", "tokenUsage": {
                        "last": {"cachedInputTokens": 11, "cacheWriteInputTokens": 7, "inputTokens": 31,
                                 "outputTokens": 17, "reasoningOutputTokens": 9, "totalTokens": 48},
                        "total": {"cachedInputTokens": 23, "inputTokens": 29, "outputTokens": 31,
                                  "reasoningOutputTokens": 37, "totalTokens": 60}, "modelContextWindow": 1000}}})
                self.event({"method": "item/completed", "params": {"threadId": "writer-thread",
                    "turnId": "writer-turn", "item": {"type": "agentMessage", "id": "answer", "text": "done"}}})
                self.event({"method": "turn/completed", "params": {"threadId": "writer-thread",
                    "turn": {"id": "writer-turn", "status": "completed"}}})
                return {"turn": {"id": "writer-turn"}}
            raise AssertionError(method)
        def close(self): pass

    monkeypatch.setattr(writing_provider, "CodexConnection", Connection)
    result = writing_provider.WritingTurn(tmp_path, "codex", "", "medium", None,
                                          lambda event: None).run("Count this.")

    # the contract's seven names, from this turn's `last` only: `total` is the thread's
    # cumulative count and the policy's scope is the active turn.
    assert result["usage"] == {"provider": "codex", "input": 13, "cached_input": 11,
                              "cache_write_input": 7, "output": 17, "reasoning_output": 9,
                              "total": 48, "context_window": 1000}
    assert result["context_window_effective"] == 1000
    assert result["context_tokens_used"] == 31


def test_codex_capability_context_limit_is_model_specific_and_not_unbounded(tmp_path, monkeypatch):
    class Connection:
        def __init__(self, *args, **kwargs): pass
        def request(self, method, params):
            assert method == "model/list"
            return {"data": [{"model": "gpt-6-astra", "displayName": "Astra", "hidden": False,
                              "defaultReasoningEffort": "medium", "supportedReasoningEfforts": []},
                             {"model": "unknown-model", "displayName": "Unknown", "hidden": False,
                              "defaultReasoningEffort": "medium", "supportedReasoningEfforts": []}]}
        def close(self): pass
    monkeypatch.setattr(writing_provider.shutil, "which", lambda name: "/fixture/codex" if name == "codex" else None)
    monkeypatch.setattr(writing_provider, "CodexConnection", Connection)

    models = writing_provider.capabilities(tmp_path, refresh=True)["providers"][0]["models"]

    assert models[0]["context_window_advertised"] == 1_050_000
    assert models[1]["context_window_advertised"] is None


def test_provider_catalogue_sees_newer_saved_discovery_without_restart(tmp_path, monkeypatch):
    old = {'schema_version':'laplace.provider-catalogue/1','observed_at':1,
           'providers':[{'id':'claude','models':[{'id':''}]}]}
    fresh = {**old,'observed_at':2,'providers':[{'id':'claude','models':[{'id':'discovered-model'}]}]}
    monkeypatch.setattr(writing_provider,'_CAP_CACHE',(0,old))
    monkeypatch.setattr(writing_provider,'_CAP_CACHE_ROOT',tmp_path)
    path=writing_provider._catalogue_path(tmp_path);path.parent.mkdir();path.write_text(json.dumps(fresh))
    monkeypatch.setattr(writing_provider.subprocess,'run',lambda *a,**k:pytest.fail('idle launch'))
    # the served rows are the SAVED rows plus the tier each model belongs to, derived at
    # read time (writing_provider.with_model_choice); nothing new is discovered or started
    assert writing_provider.provider_catalogue(tmp_path)['providers']==\
        writing_provider.with_model_choice(fresh)['providers']


def test_provider_refresh_failure_retains_previously_discovered_choices(tmp_path, monkeypatch):
    saved={'schema_version':'laplace.provider-catalogue/1','observed_at':1,'providers':[
        {'id':'codex','models':[{'id':'known-codex','name':'Known Codex'}]},
        {'id':'claude','models':[{'id':'known-claude','name':'Known Claude'}]}]}
    path=writing_provider._catalogue_path(tmp_path);path.parent.mkdir();path.write_text(json.dumps(saved))
    monkeypatch.setattr(writing_provider,'_CAP_CACHE',None)
    monkeypatch.setattr(writing_provider.shutil,'which',lambda name:None)
    result=writing_provider.capabilities(tmp_path,refresh=True)
    assert [p['models'] for p in result['providers']]==\
        [p['models'] for p in writing_provider.with_model_choice(saved)['providers']]
    assert all(not p['available'] for p in result['providers'])


def test_opening_provider_catalogue_never_starts_a_native_provider(tmp_path, monkeypatch):
    monkeypatch.setattr(writing_provider, '_CAP_CACHE', None)
    monkeypatch.setattr(writing_provider.shutil, 'which', lambda name: '/installed/' + name)
    monkeypatch.setattr(writing_provider, 'CodexConnection', lambda *a, **k: pytest.fail('idle Codex launch'))
    monkeypatch.setattr(writing_provider.subprocess, 'run', lambda *a, **k: pytest.fail('idle provider process'))
    empty = writing_provider.provider_catalogue(tmp_path)
    assert all(row['available'] and row['auth_state'] == 'UNVERIFIED' for row in empty['providers'])
    assert not (tmp_path / '.laplace-cache').exists()
    saved = {'schema_version': 'laplace.provider-catalogue/1', 'observed_at': 123,
             'providers': [{'id': 'claude', 'models': [{'id': 'recorded-model'}]}]}
    path = writing_provider._catalogue_path(tmp_path)
    path.parent.mkdir()
    path.write_text(json.dumps(saved))
    cached = writing_provider.provider_catalogue(tmp_path)
    assert cached['cached'] and cached['providers'] == writing_provider.with_model_choice(saved)['providers']
    assert cached['observed_at'] == 123
    monkeypatch.setattr(checkout, 'repo_root', lambda: tmp_path)
    monkeypatch.setattr(writing_provider, 'capabilities', lambda *a, **k: pytest.fail('view opened live provider'))
    code, _, body = authoring_surface.handle('/authoring/providers', {}, 'GET', b'')
    assert code == 200 and json.loads(body)['providers'] == \
        writing_provider.with_model_choice(saved)['providers']


def test_provider_without_effort_control_records_the_effort_it_sends(tmp_path, monkeypatch):
    """It used to bank the compatibility value 'medium' for a model the adapter sends no
    effort flag for, which is what the live session row
    WS-abc8cfa1d95c4828bc49aacbd93b81b8 in contract/talk.jsonl carries.  The recorded effort
    is now what was sent --- None --- and a pane may still display Automatic."""
    from laplace.work import project_work
    monkeypatch.setattr(writing_provider, 'capabilities', lambda *a, **k: {'providers': [
        {'id': 'claude', 'available': True, 'models': [{'id': 'haiku',
         'resolved_model': 'claude-haiku-fixture', 'supports_effort': False, 'efforts': []}]}]})
    for model in ('haiku', 'claude-haiku-fixture'):
        result = project_work.validate_session_settings({'provider': 'claude', 'model': model, 'effort': 'medium'}, tmp_path)
        # Both spellings name ONE advertised row and the row's own id is what is saved: a
        # session row carrying two spellings of one model is a second holder, and the
        # resolved model id is already on the binding row.
        assert result['model'] == 'haiku' and result['effort'] is None
        assert result['model_source'] == 'named' and result['tier'] == 'light'


@pytest.mark.parametrize("native_id, expected_method", [(None, "thread/start"), ("existing-thread", "thread/resume")])
def test_selected_codex_thread_start_and_resume_leave_capacity_provider_owned(tmp_path, monkeypatch,
                                                                               native_id, expected_method):
    _project(tmp_path)
    calls = []
    class Connection:
        def __init__(self, cwd, event, tool_handler=None, **kwargs): self.event = event
        def request(self, method, params):
            calls.append((method, params))
            if method == "model/list":
                return {"data": [{"model": "gpt-6-astra", "supportedReasoningEfforts": [{"reasoningEffort": "medium"}]}]}
            if method in {"thread/start", "thread/resume"}: return {"thread": {"id": native_id or "new-thread"}}
            if method == "turn/start":
                self.event({"method": "turn/completed", "params": {"threadId": native_id or "new-thread",
                            "turn": {"id": "new-turn", "status": "completed"}}})
                return {"turn": {"id": "new-turn"}}
            raise AssertionError(method)
        def close(self): pass
    monkeypatch.setattr(writing_provider, "CodexConnection", Connection)
    turn = writing_provider.WritingTurn(tmp_path, "codex", "gpt-6-astra", "medium", native_id,
                                        lambda event: None, project="book")
    turn.operating_brief = writing_operating.build("book", "work", tmp_path)

    turn.run("Read the selected manuscript.")

    method, params = next((method, params) for method, params in calls if method in {"thread/start", "thread/resume"})
    assert method == expected_method
    assert not {"model_context_window", "model_auto_compact_token_limit",
                "model_auto_compact_token_limit_scope"} & set(params["config"])
    # The installed supported value closes the native web-search route explicitly; omission
    # is not treated as none. Provider usage events remain the effective-window authority.
    assert params["config"]["web_search"] == "disabled"
    assert "sandbox_workspace_write" not in params["config"]
    assert params["sandbox"] == "read-only"


def test_codex_native_file_change_reports_only_selected_manuscript_paths(tmp_path, monkeypatch):
    selected = (tmp_path / "source" / "main.tex").resolve()
    class Connection:
        # the transport also passes native_tool_calls (and on_spawn when set); this fake accepts the real signature
        def __init__(self, cwd, event, tool_handler=None, **kwargs): self.event = event
        def request(self, method, params):
            if method == "thread/start": return {"thread": {"id": "writer-thread"}}
            if method == "turn/start":
                self.event({"method": "item/completed", "params": {"threadId": "writer-thread", "turnId": "writer-turn",
                    "item": {"type": "fileChange", "id": "f1", "status": "completed", "changes": [
                        {"path": "source/main.tex", "kind": "update", "diff": ""},
                        {"path": "unrelated.txt", "kind": "update", "diff": ""}]}}})
                self.event({"method": "turn/completed", "params": {"threadId": "writer-thread",
                    "turn": {"id": "writer-turn", "status": "completed"}}})
                return {"turn": {"id": "writer-turn"}}
            raise AssertionError(method)
        def close(self): pass
    monkeypatch.setattr(writing_provider, "CodexConnection", Connection)

    result = writing_provider.WritingTurn(tmp_path, "codex", "", "medium", None, lambda event: None,
                                          native_source_paths=[selected]).run("Edit the selected source.")

    assert result["native_file_changes"] == [{"path": str(selected), "kind": "update", "status": "completed"}]


def test_claude_assistant_usage_is_per_message_and_context_window_comes_only_from_model_usage():
    assistant = {"input_tokens": 2, "cache_creation_input_tokens": 17,
                 "cache_read_input_tokens": 23, "output_tokens": 3}
    result = {"usage": {"input_tokens": 999},
              "modelUsage": {"claude-fixture": {"contextWindow": 1_000_000}}}

    assert writing_provider._claude_assistant_usage(assistant) == assistant
    assert writing_provider.context_tokens_used(
        writing_provider.usage_projection("claude", assistant)) == 42
    assert writing_provider.context_window_max("claude", "", {"model_usage": result["modelUsage"]}) == 1_000_000
    assert writing_provider._claude_assistant_usage("unavailable") is None


def test_claude_context_window_matches_writer_model_and_never_picks_an_arbitrary_helper():
    models = {"claude-haiku-4": {"contextWindow": 200_000},
              "claude-opus-5[1m]": {"contextWindow": 1_000_000}}

    assert writing_provider.context_window_max("claude", "claude-opus-5", {"model_usage": models}) == 1_000_000
    assert writing_provider.context_window_max("claude", "", {"model_usage": models}) is None


@pytest.mark.parametrize("denied", [False, True])
@pytest.mark.parametrize("native_id", [None, "claude-existing"])
def test_claude_resumes_with_one_stable_system_slot_and_no_user_history_copy(
    tmp_path, monkeypatch, native_id, denied
):
    _project(tmp_path)
    brief = writing_operating.build("book", "discuss", tmp_path)
    launched = []

    class Input:
        def __init__(self):
            self.text = ""

        def write(self, value):
            self.text += value

        def close(self):
            pass

    class Process:
        pid = 12345

        def __init__(self, argv, **kwargs):
            self.argv = argv
            self.stdin = Input()
            self.stdout = iter([
                json.dumps({"type": "system", "subtype": "init", "session_id": native_id or "claude-new", "model": "actual"}) + "\n",
                json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "done"}],
                    "usage": {"input_tokens": 3, "cache_creation_input_tokens": 5,
                              "cache_read_input_tokens": 7, "output_tokens": 11}}}) + "\n",
                json.dumps({"type": "result", "result": "done", "is_error": False,
                    "permission_denials": [{"tool_name": "mcp__laplace__laplace_project",
                        "tool_use_id": "denied-read", "tool_input": {"operation": "source", "payload": {}}}] if denied else [],
                    "usage": {"input_tokens": 999},
                    "modelUsage": {"actual": {"contextWindow": 1_000_000}}}) + "\n",
            ])
            launched.append(self)

        def wait(self, timeout=None):
            return 0

        def poll(self):
            return 0

    monkeypatch.setattr(writing_provider.shutil, "which", lambda name: "/fixture/claude")
    monkeypatch.setattr(writing_provider.subprocess, "Popen", Process)
    turn = writing_provider.WritingTurn(
        tmp_path, "claude", "", "high", native_id, lambda event: None,
        "discuss", project="book", logical_turn_id="WT-claude",
    )
    turn.operating_brief = brief

    result = turn.run("Discuss this.")

    assert result["status"] == "completed"
    assert result["usage"] == {"provider": "claude", "input": 3, "cached_input": 7,
                              "cache_write_input": 5, "output": 11, "reasoning_output": None,
                              "total": 26, "context_window": 1_000_000}
    assert result["context_tokens_used"] == 15
    assert result["context_window_effective"] == 1_000_000
    argv = launched[0].argv
    assert argv[argv.index("--permission-mode") + 1] == "auto"
    assert argv[argv.index("--permission-prompts") + 1] == "none"
    assert argv[argv.index("--tools") + 1] == ""
    assert "--strict-mcp-config" in argv
    assert argv.count("--settings") == 1
    assert json.loads(argv[argv.index("--settings") + 1]) == {"outputStyle":"default"}
    assert argv[argv.index("--allowedTools") + 1] == "mcp__laplace__laplace_project"
    assert "--dangerously-skip-permissions" not in argv
    if denied:
        assert result["provider_issues"][0]["operation"] == "source"
        records = [json.loads(line) for line in (tmp_path / "contract/talk.jsonl").read_text().splitlines()]
        failure = next(row for row in records if row.get("error_type") == "ProviderPermissionDenied")
        assert failure["turn_id"] == "WT-claude" and failure["operation"] == "source"
    # The kernel is the WHOLE system prompt and the CLI's dynamic sections go with it.
    # Measured 2026-10-05 from one session workspace at haiku low (evidence/WRITING_JOINS_
    # 2026-10-04/S1/observed-process/decision/): arm A `--append-system-prompt` 15,102
    # first-turn context tokens; arm C, this pair plus `--setting-sources ''`, 8,716; arm B,
    # exactly this argv, 9,079 (one further call under the orchestrator's ruling).
    index = argv.index("--system-prompt")
    assert argv[index + 1] == writing_operating.kernel(brief, "claude")
    assert argv.count("--system-prompt") == 1
    assert "--exclude-dynamic-system-prompt-sections" in argv
    assert "--append-system-prompt" not in argv
    body, frame_block = writing_operating.body(brief), writing_operating.frame(brief)
    join = writing_operating.BLOCK_JOIN
    if native_id:
        # a resumed process re-receives the kernel, because the CLI rebuilds its system
        # slot, and never the body, which the retained first user turn already carries
        assert launched[0].stdin.text == frame_block + join + "Discuss this."
    else:
        assert launched[0].stdin.text == body + join + frame_block + join + "Discuss this."
    encoded = json.loads(body.split("\n", 1)[1])
    assert encoded["writing_style"]["content"] == brief["writing_style"]["content"]
    assert json.loads(argv[index + 1].split("\n", 1)[1])["tool_visible_name"] == (
        "mcp__laplace__laplace_project")
    assert ('--resume' in argv) is bool(native_id)
    if native_id:
        assert argv[argv.index("--resume") + 1] == native_id


def test_native_claude_child_imports_the_loaded_code_owner_despite_poisoned_path_and_cwd(tmp_path, monkeypatch):
    """A real child interpreter and no model. The Claude transport's actual launch environment (which the CLI hands to
    the native tool child it spawns) imports laplace from the package this process loaded, on the selected runtime,
    although the inherited PYTHONPATH and the child's cwd both carry a foreign laplace and the project data root is
    a distinct directory. An unprotected control proves the poisoned inputs really would select the foreign code."""
    import os, subprocess, sys
    data_root = tmp_path / 'project-data'; data_root.mkdir(); _project(data_root)
    poison = "raise SystemExit('FOREIGN LAPLACE IMPORTED')\n"
    for base in (tmp_path / 'foreign', tmp_path / 'unrelated-cwd'):
        (base / 'laplace' / 'native').mkdir(parents=True)
        for rel in ('laplace/__init__.py', 'laplace/native/__init__.py', 'laplace/native/tools.py'):
            (base / rel).write_text(poison)
    unrelated = tmp_path / 'unrelated-cwd'
    monkeypatch.setenv('PYTHONPATH', str(tmp_path / 'foreign'))
    monkeypatch.setenv('PYTHONSTARTUP', str(tmp_path / 'foreign' / 'laplace' / '__init__.py'))
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    monkeypatch.setenv('CODEX_HOME', str(tmp_path / 'codex-home'))
    launched = []
    class Process:
        def __init__(self, argv, **kwargs):
            launched.append((list(argv), dict(kwargs)))
            raise OSError('captured launch only: no model process')
    real_popen = writing_provider.subprocess.Popen
    monkeypatch.setattr(writing_provider.shutil, 'which', lambda name: '/fixture/claude')
    monkeypatch.setattr(writing_provider.subprocess, 'Popen', Process)
    turn = writing_provider.WritingTurn(data_root, 'claude', '', 'high', None, lambda event: None,
                                        'discuss', project='book', logical_turn_id='WT-origin')
    turn.operating_brief = writing_operating.build('book', 'discuss', data_root)
    try:
        turn.run('Origin probe.')
    except Exception:
        pass
    assert len(launched) == 1, 'the actual transport reached its single launch'
    monkeypatch.setattr(writing_provider.subprocess, 'Popen', real_popen)   # the probes below are real processes
    argv, kwargs = launched[0]
    env = kwargs['env']
    server = json.loads(argv[argv.index('--mcp-config') + 1])['mcpServers']['laplace']
    assert server['command'] == sys.executable and server['args'][:2] == ['-m', 'laplace.native.tools']
    assert server['args'][server['args'].index('--root') + 1] == str(data_root), 'the project data root stays distinct'
    assert '--strict-mcp-config' in argv and argv[argv.index('--allowedTools') + 1] == 'mcp__laplace__laplace_project'
    loaded = checkout.package_root()
    assert env['PYTHONPATH'] == str(loaded.parent) and env['PYTHONSAFEPATH'] == '1' and env['PYTHONNOUSERSITE'] == '1'
    assert 'PYTHONSTARTUP' not in env and 'CLAUDECODE' not in env
    assert env['HOME'] == str(tmp_path / 'home') and env['CODEX_HOME'] == str(tmp_path / 'codex-home')
    assert str(data_root) not in env['PYTHONPATH'] and str(tmp_path / 'foreign') not in env['PYTHONPATH']
    probe = ("import json, sys, laplace, laplace.native.tools as tools; "
             "print(json.dumps({'laplace': laplace.__file__, 'tools': tools.__file__, 'exe': sys.executable}))")
    child = subprocess.run([server['command'], '-c', probe], cwd=unrelated, env=env,
                           capture_output=True, text=True, timeout=90)
    assert child.returncode == 0, child.stderr[-2000:]
    seen = json.loads(child.stdout.strip().splitlines()[-1])
    assert Path(seen['laplace']).resolve() == (loaded / '__init__.py').resolve()
    assert Path(seen['tools']).resolve() == (loaded / 'native' / 'tools.py').resolve() and seen['exe'] == sys.executable
    # Control: the same interpreter with the inherited environment and cwd selects the foreign owner, so the pass above
    # discriminates rather than passing vacuously.
    inherited = {key: value for key, value in os.environ.items() if key != 'PYTHONSTARTUP'}
    control = subprocess.run([server['command'], '-c', probe], cwd=unrelated, env=inherited,
                             capture_output=True, text=True, timeout=90)
    assert control.returncode != 0 and 'FOREIGN LAPLACE IMPORTED' in control.stderr


def test_native_child_host_imports_the_loaded_code_owner_for_every_membership_despite_poisoned_path_and_cwd(tmp_path, monkeypatch):
    """F2: turn_execution.launch_child_host starts the dispatch, source-event and source-return host BEFORE any provider
    helper. Its actual launch (captured, no host or model process) must carry the loaded-package environment for all three
    memberships, keep sys.executable, --root as the data root, cwd, stdin handshake and HOME/CODEX_HOME; a real subprocess
    with that environment in the poisoned data-root cwd imports the loaded owner, and the inherited control does not."""
    import os, subprocess, sys
    from laplace.core import checkout
    from laplace.writing import turn_execution
    data_root = tmp_path / 'project-data'; data_root.mkdir()
    poison = "raise SystemExit('FOREIGN LAPLACE IMPORTED')\n"
    for base in (tmp_path / 'foreign', data_root):
        (base / 'laplace' / 'native').mkdir(parents=True)
        for rel in ('laplace/__init__.py', 'laplace/native/__init__.py', 'laplace/native/tools.py'):
            (base / rel).write_text(poison)
    monkeypatch.setenv('PYTHONPATH', str(tmp_path / 'foreign'))
    monkeypatch.setenv('PYTHONSTARTUP', str(tmp_path / 'foreign' / 'laplace' / '__init__.py'))
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    monkeypatch.setenv('CODEX_HOME', str(tmp_path / 'codex-home'))
    launched = []
    class Host:
        def __init__(self, argv, **kwargs):
            launched.append((list(argv), dict(kwargs)))
            raise OSError('captured launch only: no host process')
    real_popen = subprocess.Popen
    monkeypatch.setattr(subprocess, 'Popen', Host)
    payload = {'project': 'book', 'mode': 'review'}
    for dispatch, extra in (({'dispatch_id': 'DP-origin', 'parent_turn_id': 'WT-parent'}, {}),
                            ({}, {'source_event': 'WD-origin-review'}), ({}, {'source_return': 'WD-origin-return'})):
        with pytest.raises(OSError):
            turn_execution.launch_child_host(data_root, payload, dispatch, **extra)
    monkeypatch.setattr(subprocess, 'Popen', real_popen)   # the probes below are real processes
    assert len(launched) == 3
    loaded = checkout.package_root()
    probe = ("import json, sys, laplace, laplace.native.tools as tools; "
             "print(json.dumps({'laplace': laplace.__file__, 'tools': tools.__file__, 'exe': sys.executable}))")
    flags = []
    for argv, kwargs in launched:
        assert argv[:3] == [sys.executable, '-m', 'laplace.native.tools'] and argv[argv.index('--root') + 1] == str(data_root)
        assert '--start-child-turn' in argv and kwargs['cwd'] == str(data_root) and kwargs['stdin'] == subprocess.PIPE
        env = kwargs['env']
        assert env['PYTHONPATH'] == str(loaded.parent) and env['PYTHONSAFEPATH'] == '1' and env['PYTHONNOUSERSITE'] == '1'
        assert 'PYTHONSTARTUP' not in env and str(tmp_path / 'foreign') not in env['PYTHONPATH']
        assert env['HOME'] == str(tmp_path / 'home') and env['CODEX_HOME'] == str(tmp_path / 'codex-home')
        flags.append(next(flag for flag in ('--dispatch-id', '--source-event', '--source-return') if flag in argv))
        child = subprocess.run([argv[0], '-c', probe], cwd=kwargs['cwd'], env=env, capture_output=True, text=True, timeout=90)
        assert child.returncode == 0, child.stderr[-2000:]
        seen = json.loads(child.stdout.strip().splitlines()[-1])
        assert Path(seen['laplace']).resolve() == (loaded / '__init__.py').resolve()
        assert Path(seen['tools']).resolve() == (loaded / 'native' / 'tools.py').resolve() and seen['exe'] == sys.executable
    assert flags == ['--dispatch-id', '--source-event', '--source-return']
    inherited = {key: value for key, value in os.environ.items() if key != 'PYTHONSTARTUP'}
    control = subprocess.run([sys.executable, '-c', probe], cwd=str(data_root), env=inherited, capture_output=True, text=True, timeout=90)
    assert control.returncode != 0 and 'FOREIGN LAPLACE IMPORTED' in control.stderr


def test_exact_action_schema_and_example_changes_invalidate_contract_without_expanding_context(tmp_path,monkeypatch):
    """A change to one DECLARATION moves that action's digest and nothing else.

    The change used to be simulated by editing `CONTRACTS['source']['example']`.  There
    is no hand-written example any more and `CONTRACTS` is a projection, so the change is
    made where the contract now lives: one more rule on the `source` declaration.
    """
    _project(tmp_path)
    import dataclasses
    from laplace.native import declarations as writing_declarations
    before = writing_operating.tool_contract()
    declaration = writing_declarations.DECLARATIONS['source']
    changed = dataclasses.replace(declaration, rules=declaration.rules + (
        writing_declarations.Rule('shape', field='files',
                                  door='src/laplace/writing_tools.py:199',
                                  says='a fixture rule, to move this action digest'),))
    monkeypatch.setitem(writing_declarations.DECLARATIONS, 'source', changed)
    after = writing_operating.tool_contract()
    assert after['digest'] != before['digest']
    assert after['exact_actions_digest'] != before['exact_actions_digest']
    assert after['action_catalogue'] == before['action_catalogue']
    assert after['tool'] == before['tool']
    assert after['native_registration_signature'] == before['native_registration_signature']
    assert after['exact_action_digests']['source'] != before['exact_action_digests']['source']
    assert after['exact_action_digests']['structure'] == before['exact_action_digests']['structure']
    assert 'exact_action_digests' not in writing_operating.prompt(
        writing_operating.build('book','work',tmp_path))
    # the brief references the declarations, so a rule's text never reaches it
    assert 'a fixture rule' not in str(after['operation_payload_contracts'])


def test_native_thread_resumes_only_when_deployed_tool_contract_is_unchanged(tmp_path, monkeypatch):
    _project(tmp_path)
    contract_digest = writing_operating.tool_contract()["digest"]
    registration_signature=writing_operating.tool_contract()["native_registration_signature"]
    captured = []

    class Provider:
        def __init__(self, cwd, provider, model, effort, native_id, event, mode,
                         project=None, logical_turn_id=None, **kwargs):
            self.native_id = native_id
            self.event = event
            captured.append(self)

        def run(self, prompt):
            self.prompt = prompt
            self.event({"type": "session", "native_id": self.native_id or "replacement", "model": "actual", "provider": "codex"})
            return {"status": "completed", "text": "done", "turn_id": "native-turn"}

    monkeypatch.setattr(writing_provider, "WritingTurn", Provider)

    same = turn_admission.new_session(tmp_path, "book", "codex", "", "medium")
    records.bank(tmp_path, {"record": "writing-binding", "id": "WB-same",
        "session_id": same["id"], "native_id": "native-current", "model": "actual",
        "tool_contract_digest": contract_digest,
        "native_registration_signature":registration_signature})
    same_brief=writing_operating.build('book','discuss',tmp_path)
    records.bank(tmp_path,{"record":"writing-turn","id":"WT-same-kernel",
        "session_id":same["id"],"project":"book","mode":"discuss","text":"Earlier.",
        "orientation":turn_context._orientation_snapshot(same_brief)})
    records.bank(tmp_path,{"record":"writing-reply","id":"WR-same-kernel",
        "turn_id":"WT-same-kernel","session_id":same["id"],"project":"book",
        "status":"completed","text":"Earlier saved reply."})
    started = turn_admission.start_turn(tmp_path, {"project": "book", "session_id": same["id"],
        "text": "continue", "mode": "discuss", "request_id": "same-contract"})
    same_turn = _wait(tmp_path, started)
    assert captured[-1].native_id == "native-current"
    assert same_turn["native_contract_migration"] is None

    old = turn_admission.new_session(tmp_path, "book", "codex", "", "medium")
    records.bank(tmp_path, {"record": "writing-binding", "id": "WB-old",
        "session_id": old["id"], "native_id": "native-obsolete", "model": "actual",
        "tool_contract_digest": "sha256:obsolete",
        "native_registration_signature":"sha256:obsolete-registration"})
    for index in range(10):
        turn_id = f"WT-history-{index}"
        records.bank(tmp_path, {"record": "writing-turn", "id": turn_id,
            "session_id": old["id"], "project": "book", "text": f"QUESTION-{index}" + "q" * 2100})
        records.bank(tmp_path, {"record": "writing-reply", "id": f"WR-history-{index}",
            "turn_id": turn_id, "session_id": old["id"], "project": "book",
            "status": "completed", "text": f"ANSWER-{index}" + "a" * 4100})
    started = turn_admission.start_turn(tmp_path, {"project": "book", "session_id": old["id"],
        "text": "continue after deployment", "mode": "discuss", "request_id": "changed-contract"})
    migrated = _wait(tmp_path, started)

    assert captured[-1].native_id is None
    assert migrated["native_contract_migration"]["reason"] == "native tool registration is incompatible or unproven"
    assert migrated["native_contract_migration"]["previous_native_id"] == "native-obsolete"
    assert migrated["native_contract_migration"]["registration_compatibility"]["basis"] == "native registration signature changed"
    assert "QUESTION-0" not in captured[-1].prompt and "QUESTION-1" not in captured[-1].prompt
    assert "QUESTION-2" in captured[-1].prompt and "QUESTION-9" in captured[-1].prompt
    assert "q" * 2001 not in captured[-1].prompt
    assert "a" * 4001 not in captured[-1].prompt


def test_help_only_contract_change_rebinds_before_delivering_the_new_kernel(tmp_path,monkeypatch):
    _project(tmp_path)
    from laplace.native import contracts as writing_contracts
    from laplace.writing import reads
    before_brief=writing_operating.build('book','work',tmp_path)
    captured=[]
    class Provider:
        def __init__(self,cwd,provider,model,effort,native_id,event,mode,**kwargs):
            self.native_id=native_id;self.event=event;captured.append(self)
        def run(self,prompt):
            self.prompt=prompt;self.event({'type':'session','native_id':self.native_id or 'replacement',
                'model':'actual','provider':'codex'});return {'status':'completed','text':'done'}
    monkeypatch.setattr(writing_provider, 'WritingTurn',Provider)
    session=turn_admission.new_session(tmp_path,'book','codex','','medium')
    records.bank(tmp_path,{'record':'writing-binding','id':'WB-help-delta',
        'session_id':session['id'],'native_id':'native-science-reading','model':'actual',
        'tool_contract_digest':before_brief['tool_contract_digest'],
        'native_registration_signature':before_brief['native_registration_signature']})
    records.bank(tmp_path,{'record':'writing-turn','id':'WT-help-before',
        'session_id':session['id'],'project':'book','mode':'work','text':'Read the source.',
        'orientation':turn_context._orientation_snapshot(before_brief),
        'operating_brief':{'permissions':sorted(reads.READS|reads.WRITES)}})
    records.bank(tmp_path,{'record':'writing-reply','id':'WR-help-before',
        'turn_id':'WT-help-before','session_id':session['id'],'project':'book',
        'status':'completed','text':'Earlier saved reply.'})
    import dataclasses
    from laplace.native import declarations as writing_declarations
    declaration=writing_declarations.DECLARATIONS['repository']
    changed=dataclasses.replace(declaration,rules=declaration.rules+(
        writing_declarations.Rule('shape',field='page',
                                  door='src/laplace/writing_tools.py:275',
                                  says='a fixture rule, to move one action digest'),))
    monkeypatch.setitem(writing_declarations.DECLARATIONS,'repository',changed)

    started=turn_admission.start_turn(tmp_path,{'project':'book','session_id':session['id'],
        'text':'Continue the same scientific reading.','mode':'work','request_id':'help-delta-1'})
    turn=_wait(tmp_path,started)
    assert captured[-1].native_id is None
    assert turn['native_contract_migration']['reason'] == (
        'session-invariant operating kernel changed or is unproven')
    assert turn['native_contract_migration']['changed_kernel_members'] == ['tool_contract_digest']
    assert '"changed_actions"' not in captured[-1].prompt
    assert '"operation_contract"' not in captured[-1].prompt and '"rules"' not in captured[-1].prompt

    started=turn_admission.start_turn(tmp_path,{'project':'book','session_id':session['id'],
        'text':'Continue once more.','mode':'work','request_id':'help-delta-2'})
    _wait(tmp_path,started)
    assert captured[-1].native_id=='replacement'
    assert 'CHANGED PROJECT ORIENTATION' not in captured[-1].prompt


def test_legacy_contract_delta_is_bounded_and_does_not_invent_changed_actions():
    current={'tool_contract_digest':'new','exact_action_digests':{'source':'a','repository':'b'},
             'action_catalogue_digest':'catalogue','role_permissions_digest':'permissions'}
    delta=writing_operating.orientation_delta({'tool_contract_digest':'old'},current)['guidance']['contract_delta']
    assert delta['changed_actions']==[] and delta['prior_action_detail_available'] is False
    assert delta['catalogue_changed'] is None and delta['permissions_changed'] is None


def test_capability_guidance_only_change_is_detected_once_by_orientation(tmp_path,monkeypatch):
    _project(tmp_path)
    before=writing_operating.build('book','work',tmp_path)
    prior=turn_context._orientation_snapshot(before)
    recipe='When code mode returns an image handle, emit it as typed image content once.'
    monkeypatch.setattr(writing_operating,'CAPABILITY_GUIDANCE',{
        **writing_operating.CAPABILITY_GUIDANCE,'repository_images':recipe})
    after=writing_operating.build('book','work',tmp_path)
    changed=writing_operating.orientation_delta(prior,after)
    unchanged=writing_operating.orientation_delta(turn_context._orientation_snapshot(after),after)

    assert after['native_registration_signature']==before['native_registration_signature']
    assert after['tool_contract_digest']==before['tool_contract_digest']
    assert after['shared_rules_revision']==before['shared_rules_revision']
    assert after['capability_guidance_revision']!=before['capability_guidance_revision']
    assert changed=={'changed':True,'guidance':{
        'capability_guidance_revision':after['capability_guidance_revision'],
        'capability_guidance':after['capability_guidance']}}
    assert unchanged=={'changed':False,'guidance':{}}


@pytest.mark.parametrize('provider_name',['claude','codex'])
@pytest.mark.parametrize('kernel_case',['unchanged','changed','missing-proof'])
def test_native_binding_requires_current_kernel_identity_on_both_providers(
        tmp_path,monkeypatch,provider_name,kernel_case):
    _project(tmp_path)
    before=writing_operating.build('book','work',tmp_path)
    session=turn_admission.new_session(tmp_path,'book',provider_name,'','medium')
    records.bank(tmp_path,{'record':'writing-binding','id':'WB-kernel-proof',
        'session_id':session['id'],'native_id':'native-kernel','model':'actual',
        'tool_contract_digest':before['tool_contract_digest'],
        'native_registration_signature':before['native_registration_signature']})
    if kernel_case!='missing-proof':
        records.bank(tmp_path,{'record':'writing-turn','id':'WT-kernel-proof',
            'session_id':session['id'],'project':'book','mode':'work','text':'Earlier turn.',
            'orientation':turn_context._orientation_snapshot(before)})
        records.bank(tmp_path,{'record':'writing-reply','id':'WR-kernel-proof',
            'turn_id':'WT-kernel-proof','session_id':session['id'],'project':'book',
            'status':'completed','text':'Earlier saved reply.'})
    if kernel_case=='changed':
        monkeypatch.setattr(writing_operating,'CAPABILITY_GUIDANCE',{
            **writing_operating.CAPABILITY_GUIDANCE,
            'repository_images':'A changed session-invariant capability rule.'})
    captured=[]
    class Provider:
        def __init__(self,cwd,provider,model,effort,native_id,event,mode,**kwargs):
            self.native_id=native_id;self.event=event;captured.append(self)
        def run(self,prompt):
            self.event({'type':'session','native_id':self.native_id or 'replacement',
                        'model':'actual','provider':provider_name})
            return {'status':'completed','text':'done'}
    monkeypatch.setattr(writing_provider, 'WritingTurn',Provider)

    started=turn_admission.start_turn(tmp_path,{'project':'book','session_id':session['id'],
        'text':'Continue.','mode':'work','request_id':'kernel-'+kernel_case})
    turn=_wait(tmp_path,started)
    if kernel_case=='unchanged':
        assert captured[-1].native_id=='native-kernel'
        assert turn['native_contract_migration'] is None
    else:
        assert captured[-1].native_id is None
        migration=turn['native_contract_migration']
        assert migration['reason']=='session-invariant operating kernel changed or is unproven'
        if kernel_case=='changed':
            assert migration['changed_kernel_members']==['capability_guidance_revision']
        else:
            assert set(migration['changed_kernel_members'])=={
                'tool_contract_digest','shared_rules_revision','capability_guidance_revision'}


def test_pre_inference_refusal_invalidates_unproved_held_context_without_replay(
        tmp_path,monkeypatch):
    _project(tmp_path)
    before=writing_operating.build('book','work',tmp_path)
    session=turn_admission.new_session(tmp_path,'book','codex','','medium')
    records.bank(tmp_path,{'record':'writing-binding','id':'WB-preflight-before',
        'session_id':session['id'],'native_id':'native-before','model':'actual',
        'tool_contract_digest':before['tool_contract_digest'],
        'native_registration_signature':before['native_registration_signature']})
    prior_parts={part['key']:part['token'] for part in writing_operating.body_parts(before)}
    records.bank(tmp_path,{'record':'writing-turn','id':'WT-preflight-before',
        'session_id':session['id'],'project':'book','mode':'work','text':'Earlier.',
        'orientation':turn_context._orientation_snapshot(before),
        'context_parts':prior_parts})
    records.bank(tmp_path,{'record':'writing-reply','id':'WR-preflight-before',
        'turn_id':'WT-preflight-before','session_id':session['id'],'project':'book',
        'status':'completed','text':'Earlier saved reply.'})
    (tmp_path/'profiles/voice/book-v1.md').write_text(
        '# Book voice\nChanged guidance that has not reached the provider.\n',encoding='utf-8')

    class Refused:
        def __init__(self,*args,**kwargs):
            raise writing_provider.ProviderError('Provider tool preflight refused before inference.')
    monkeypatch.setattr(writing_provider, 'WritingTurn',Refused)
    started=turn_admission.start_turn(tmp_path,{'project':'book','session_id':session['id'],
        'text':'Continue after the local preflight.','mode':'work','request_id':'preflight-refusal'})
    refused=_wait(tmp_path,started)
    assert refused['reply']['status']=='failed'
    assert refused['reply']['provider_stage']=='pre-inference'
    assert session_reads._records(tmp_path)['sessions'][session['id']]['native_id'] is None
    assert refused['context_parts']['operating_brief.writing_style'] != (
        prior_parts['operating_brief.writing_style'])

    captured=[]
    class Accepted:
        def __init__(self,cwd,provider,model,effort,native_id,event,mode,**kwargs):
            self.native_id=native_id;self.event=event;self.inference_started=False
            captured.append(self)
        def run(self,prompt):
            self.inference_started=True
            self.event({'type':'session','native_id':'native-after','model':'actual','provider':'codex'})
            return {'status':'completed','text':'done'}
    monkeypatch.setattr(writing_provider, 'WritingTurn',Accepted)
    started=turn_admission.start_turn(tmp_path,{'project':'book','session_id':session['id'],
        'text':'Explicit new attempt.','mode':'work','request_id':'after-preflight-refusal'})
    recovered=_wait(tmp_path,started)
    assert captured[-1].native_id is None
    assert recovered['reply']['status']=='completed'
    assert recovered['context_parts']['operating_brief.writing_style'] == (
        refused['context_parts']['operating_brief.writing_style'])


def test_reported_inference_failure_keeps_native_binding_for_explicit_retry(
        tmp_path,monkeypatch):
    _project(tmp_path)
    session=turn_admission.new_session(tmp_path,'book','codex','','medium')
    captured=[]
    class Provider:
        def __init__(self,cwd,provider,model,effort,native_id,event,mode,**kwargs):
            self.native_id=native_id;self.event=event;self.inference_started=False
            captured.append(self)
        def run(self,prompt):
            self.prompt=prompt;self.inference_started=True
            self.event({'type':'session','native_id':self.native_id or 'native-inference',
                        'model':'actual','provider':'codex'})
            if len(captured)==1:
                return {'status':'failed','text':'partial result',
                        'error':'provider reported failure'}
            return {'status':'completed','text':'recovered'}
    monkeypatch.setattr(writing_provider, 'WritingTurn',Provider)

    started=turn_admission.start_turn(tmp_path,{'project':'book','session_id':session['id'],
        'text':'FIRST_FAILURE_MARKER','mode':'work','request_id':'reported-inference-failure'})
    failed=_wait(tmp_path,started)
    assert failed['reply']['status']=='failed'
    assert failed['reply']['provider_stage']=='inference'

    started=turn_admission.start_turn(tmp_path,{'project':'book','session_id':session['id'],
        'text':'Explicit retry.','mode':'work','request_id':'reported-inference-retry'})
    recovered=_wait(tmp_path,started)
    assert captured[-1].native_id=='native-inference'
    assert recovered['native_contract_migration'] is None
    assert 'SAVED CONVERSATION CONTEXT AFTER A CONNECTION UPDATE' not in captured[-1].prompt
    assert 'FIRST_FAILURE_MARKER' not in captured[-1].prompt
    assert recovered['reply']['status']=='completed'


def test_binding_persistence_failure_is_terminal_and_explicit_retry_redelivers_context(
        tmp_path,monkeypatch):
    _project(tmp_path)
    brief=writing_operating.build('book','work',tmp_path)
    session=turn_admission.new_session(tmp_path,'book','codex','','medium')
    records.bank(tmp_path,{'record':'writing-binding','id':'WB-terminal-before',
        'session_id':session['id'],'native_id':'native-before','model':'actual',
        'tool_contract_digest':brief['tool_contract_digest'],
        'native_registration_signature':brief['native_registration_signature']})
    records.bank(tmp_path,{'record':'writing-turn','id':'WT-terminal-before',
        'session_id':session['id'],'project':'book','mode':'work','text':'Earlier.',
        'orientation':turn_context._orientation_snapshot(brief)})
    records.bank(tmp_path,{'record':'writing-reply','id':'WR-terminal-before',
        'turn_id':'WT-terminal-before','session_id':session['id'],'project':'book',
        'status':'completed','native_id':'native-before','text':'Earlier saved reply.'})
    constructor_calls=[]
    class Refused:
        def __init__(self,*args,**kwargs):
            constructor_calls.append('refused')
            raise writing_provider.ProviderError('planted pre-inference refusal')
    monkeypatch.setattr(writing_provider, 'WritingTurn',Refused)
    owner_bank=records.bank;injected=[]
    def failing_bank(root,row):
        if (row.get('record')=='writing-binding'
                and row.get('reason')=='provider refused before inference'):
            injected.append(row['record'])
            raise PermissionError('planted binding persistence failure')
        return owner_bank(root,row)
    monkeypatch.setattr(records,'bank',failing_bank)
    started=turn_admission.start_turn(tmp_path,{'project':'book','session_id':session['id'],
        'text':'Continue.','mode':'work','selection':{'files':['main.tex'],'line_start':3,'line_end':3},
        'request_id':'terminal-binding-fault'})
    refused=_wait(tmp_path,started);job=turn_jobs._JOBS[started['turn_id']]
    terminal=[event for event in job['events'] if event['type'] in {'complete','error'}]
    assert job['done'] is True and len(terminal)==1 and terminal[0]['type']=='complete'
    assert refused['reply']['status']=='failed' and refused['reply']['provider_stage']=='pre-inference'
    assert 'planted pre-inference refusal' in refused['reply']['error']
    assert 'binding invalidation was not saved: planted binding persistence failure' in refused['reply']['error']
    assert constructor_calls==['refused'] and injected==['writing-binding']
    assert session_reads._records(tmp_path)['sessions'][session['id']]['native_id']=='native-before'

    monkeypatch.setattr(records,'bank',owner_bank)
    captured=[]
    class Accepted:
        def __init__(self,cwd,provider,model,effort,native_id,event,mode,**kwargs):
            self.native_id=native_id;self.event=event;captured.append(self)
        def run(self,prompt):
            self.prompt=prompt;self.event({'type':'session','native_id':'native-after',
                'model':'actual','provider':'codex'});return {'status':'completed','text':'done'}
    monkeypatch.setattr(writing_provider, 'WritingTurn',Accepted)
    started=turn_admission.start_turn(tmp_path,{'project':'book','session_id':session['id'],
        'text':'Explicit retry.','mode':'work','selection':{'files':['main.tex'],'line_start':3,'line_end':3},
        'request_id':'terminal-binding-retry'})
    recovered=_wait(tmp_path,started)
    assert captured[-1].native_id is None
    assert recovered['native_contract_migration']['reason']==(
        'previous turn ended before inference or its delivery is unproven')
    assert 'Original prose.' in captured[-1].prompt
    assert recovered['reply']['status']=='completed'


def test_legacy_binding_requires_kernel_proof_even_when_registration_is_reconstructable(tmp_path,monkeypatch):
    _project(tmp_path)
    from laplace.writing import reads
    captured=[]
    class Provider:
        def __init__(self,cwd,provider,model,effort,native_id,event,mode,**kwargs):
            self.native_id=native_id;self.event=event;captured.append(self)
        def run(self,prompt):
            self.event({'type':'session','native_id':self.native_id or 'replacement',
                'model':'actual','provider':'codex'});return {'status':'completed','text':'done'}
    monkeypatch.setattr(writing_provider, 'WritingTurn',Provider)
    compatible=turn_admission.new_session(tmp_path,'book','codex','','medium')
    records.bank(tmp_path,{'record':'writing-binding','id':'WB-legacy-known',
        'session_id':compatible['id'],'native_id':'native-legacy','model':'actual',
        'tool_contract_digest':'sha256:old-help'})
    records.bank(tmp_path,{'record':'writing-turn','id':'WT-legacy-known',
        'session_id':compatible['id'],'project':'book','mode':'work','text':'Earlier.',
        'operating_brief':{'schema_version':writing_operating.VERSION,
                           'permissions':sorted(reads.READS|reads.WRITES)},
        'orientation':{'tool_contract_digest':'sha256:old-help'}})
    records.bank(tmp_path,{'record':'writing-reply','id':'WR-legacy-known',
        'turn_id':'WT-legacy-known','session_id':compatible['id'],'project':'book',
        'status':'completed','text':'Earlier saved reply.'})
    started=turn_admission.start_turn(tmp_path,{'project':'book','session_id':compatible['id'],
        'text':'Resume.','mode':'work','request_id':'legacy-known'})
    turn=_wait(tmp_path,started)
    assert captured[-1].native_id is None
    assert turn['native_contract_migration']['reason'] == (
        'native tool registration is incompatible or unproven')
    assert turn['native_registration_compatibility']['compatible'] is False

    unknown=turn_admission.new_session(tmp_path,'book','codex','','medium')
    records.bank(tmp_path,{'record':'writing-binding','id':'WB-legacy-unknown',
        'session_id':unknown['id'],'native_id':'native-unknown','model':'actual',
        'tool_contract_digest':'sha256:old-help'})
    started=turn_admission.start_turn(tmp_path,{'project':'book','session_id':unknown['id'],
        'text':'Resume.','mode':'work','request_id':'legacy-unknown'})
    turn=_wait(tmp_path,started)
    assert captured[-1].native_id is None
    assert turn['native_contract_migration']['registration_compatibility']['compatible'] is False


def test_legacy_equal_operation_names_do_not_bless_changed_schema_or_callback(tmp_path,monkeypatch):
    _project(tmp_path)
    from copy import deepcopy
    from laplace.writing import reads
    brief=writing_operating.build('book','work',tmp_path)
    permissions=sorted(reads.READS|reads.WRITES)
    session={'role':'author','tool_contract_digest':'sha256:legacy'}
    previous={'operating_brief':{'schema_version':writing_operating.VERSION,
                                'permissions':permissions}}
    accepted=turn_context._legacy_registration_compatibility(session,previous,brief)
    # The deployed gateway now also offers semantic requests; a saved legacy v1
    # operation-only registration cannot certify that new shape, even with equal names.
    assert accepted['compatible'] is False
    assert accepted['reconstructed_signature']!=brief['native_registration_signature']

    changed_schema=deepcopy(brief)
    tool=deepcopy(brief['operation_contract'])
    tool['inputSchema']['properties']['payload']['additionalProperties']=False
    changed_schema['operation_contract']=tool
    changed_schema['native_registration_signature']=writing_operating.native_registration_signature(tool)
    rejected=turn_context._legacy_registration_compatibility(session,previous,changed_schema)
    assert rejected['compatible'] is False
    assert rejected['basis']=='saved v1 structural registration differs from current gateway schema or callback protocol'

    changed_callback=deepcopy(brief)
    registration={'schema_version':writing_operating.NATIVE_REGISTRATION_VERSION,
        'gateway':{key:tool_value for key,tool_value in brief['operation_contract'].items()
                   if key in ('type','name','inputSchema')},
        'callback_protocol':'laplace-project-tool-call/2'}
    changed_callback['native_registration_signature']=writing_operating.digest(registration)
    rejected=turn_context._legacy_registration_compatibility(session,previous,changed_callback)
    assert rejected['compatible'] is False

    legacy_signature=writing_operating.legacy_v1_registration_signature(permissions)
    monkeypatch.setattr(writing_operating,'CURRENT_CALLBACK_PROTOCOL','laplace-project-tool-call/2')
    future=writing_operating.build('book','work',tmp_path)
    assert writing_operating.legacy_v1_registration_signature(permissions)==legacy_signature
    assert future['native_registration_signature']!=legacy_signature
    assert turn_context._legacy_registration_compatibility(session,previous,future)['compatible'] is False


def test_help_and_history_reads_revalidate_without_banking_duplicate_receipts(tmp_path, monkeypatch):
    manuscript = _project(tmp_path)
    records.bank(tmp_path, {"record": "writing-session", "id": "WS-read",
        "project": "book", "provider": "codex", "model": "", "effort": "medium"})
    records.bank(tmp_path, {"record": "writing-turn", "id": "WT-old",
        "session_id": "WS-read", "project": "book", "text": "Earlier question"})
    records.bank(tmp_path, {"record": "writing-reply", "id": "WR-old",
        "turn_id": "WT-old", "session_id": "WS-read", "project": "book",
        "status": "completed", "text": "Earlier answer"})
    context=authoring.build_context("book", {"files":["main.tex"],"line_start":3,"line_end":3},repo_root=tmp_path)
    records.bank(tmp_path, {"record": "writing-turn", "id": "WT-current",
        "session_id": "WS-read", "project": "book", "text": "Revise", "mode": "revise",
        "context_id":context["context_id"], "dependencies":context["dependencies"],
        "document":context["document"]})
    writing_tools.execute(tmp_path, "book", "revise", "help", {"operation": "source"}, turn_id="WT-current")
    history = writing_tools.execute(tmp_path, "book", "revise", "conversation_history", {"limit": 6}, turn_id="WT-current")
    assert history["turns"] == [{"id": "WT-old", "question": "Earlier question",
                                  "answer": "Earlier answer", "truncated": False}]
    records.bank(tmp_path, {"record": "writing-reply", "id": "WR-current",
        "turn_id": "WT-current", "session_id": "WS-read", "project": "book", "status": "completed",
        "proposal": {"answer": "proposal", "edits": [{"file": "main.tex", "line_start": 3,
            "line_end": 3, "before": "Original prose.", "after": "Revised prose.", "reason": "clarity"}]}})

    calls = []
    monkeypatch.setattr(review_surface, "manuscript_dir", lambda project: manuscript)
    monkeypatch.setattr(review_surface, "_repo_root", lambda: tmp_path)
    original_source = (manuscript / "main.tex").read_text(encoding="utf-8")
    owner_adjudicate = review_surface.adjudicate
    def adjudicate(md, project, payload, *, source_changes=None, repo_root=None):
        calls.append(payload)
        return owner_adjudicate(md, project, payload, source_changes=source_changes, repo_root=repo_root)
    monkeypatch.setattr(review_surface, "adjudicate", adjudicate)

    before = [json.loads(line) for line in (tmp_path / "contract/talk.jsonl").read_text().splitlines()]
    from laplace.manuscript.manuscript_proposals import proposal_version
    version=proposal_version(session_reads._records(tmp_path)["turns"]["WT-current"])[0]
    result = source_application.apply_proposal(tmp_path, {"turn_id": "WT-current", "proposal_version": version})
    after = [json.loads(line) for line in (tmp_path / "contract/talk.jsonl").read_text().splitlines()]

    assert result["complete"] is True and len(calls) == 1
    assert (manuscript / "main.tex").read_text(encoding="utf-8") == original_source.replace(
        "Original prose.", "Revised prose.")
    assert sum(row.get("record") == "writing-tool-read" for row in before) == 2
    assert sum(row.get("record") == "writing-tool-read" for row in after) == 2


def test_writing_style_change_makes_an_existing_proposal_stale(tmp_path, monkeypatch):
    manuscript = _project(tmp_path)
    selection = {"files": ["main.tex"], "line_start": 3, "line_end": 3}
    context = authoring.build_context("book", selection, repo_root=tmp_path)
    records.bank(tmp_path, {"record": "writing-session", "id": "WS-style",
        "project": "book", "provider": "codex", "model": "", "effort": "medium"})
    records.bank(tmp_path, {"record": "writing-turn", "id": "WT-style",
        "session_id": "WS-style", "project": "book", "text": "Revise", "mode": "revise",
        "selection": selection, "context_id": context["context_id"],
        "dependencies": context["dependencies"], "document": context["document"]})
    records.bank(tmp_path, {"record": "writing-reply", "id": "WR-style",
        "turn_id": "WT-style", "session_id": "WS-style", "project": "book", "status": "completed",
        "proposal": {"answer": "proposal", "edits": [{"file": "main.tex", "line_start": 3,
            "line_end": 3, "before": "Original prose.", "after": "Revised prose.", "reason": "voice"}]}})
    from laplace.manuscript.manuscript_proposals import proposal_version
    version=proposal_version(session_reads._records(tmp_path)["turns"]["WT-style"])[0]
    current = writing_style.state("book", tmp_path)
    writing_style.save("book", {"profile": current["profile"], "guidance": "New project guidance.",
        "expected_revision": current["revision"]}, tmp_path)
    monkeypatch.setattr(review_surface, "manuscript_dir", lambda project: manuscript)
    monkeypatch.setattr(review_surface, "adjudicate", lambda *args, **kwargs: pytest.fail("stale proposal wrote source"))

    with pytest.raises(ValueError, match="changed"):
        source_application.apply_proposal(tmp_path, {"turn_id": "WT-style", "proposal_version": version})

    assert (manuscript / "main.tex").read_text(encoding="utf-8").splitlines()[2] == "Original prose."


def test_claude_native_text_message_boundaries_do_not_split_chunks_or_publish_tool_thinking_messages(tmp_path, monkeypatch):
    import io
    events=[]
    def stream(kind, *, parent=None, **fields):
        return {"type":"stream_event", "parent_tool_use_id":parent,
                "event":{"type":kind, **fields}}
    def start(ident, **extra):
        return stream("message_start", message={"id":ident,"role":"assistant","content":[]}, **extra)
    def text(value, **extra):
        return stream("content_block_delta", delta={"type":"text_delta","text":value}, **extra)
    rows=[start('thinking-only'),
          stream('content_block_start',content_block={'type':'thinking','thinking':''}),
          stream('content_block_delta',delta={'type':'thinking_delta','thinking':'private reasoning'}),
          stream('message_stop'),
          start('first'),text('The arch'),text('itecture.'),stream('message_stop'),
          start('tool-only'),stream('content_block_start',content_block={'type':'tool_use','id':'tool','name':'read'}),
          stream('content_block_delta',delta={'type':'input_json_delta','partial_json':'{}'}),stream('message_stop'),
          start('second'),text(''),
          start('child',parent='tool-parent'),text('Subagent text',parent='tool-parent'),stream('message_stop',parent='tool-parent'),
          stream('content_block_delta',delta={'type':'thinking_delta','thinking':'more reasoning'}),
          text('The Wigner'),text(' source.'),stream('message_stop'),
          start('last-thinking-only'),stream('message_stop')]
    class Process:
        pid=12345
        def __init__(self,*args,**kwargs):
            self.stdin=io.StringIO();self.stdout=iter(json.dumps(row)+'\n' for row in rows)
        def wait(self,timeout=None):return 0
        def poll(self):return 0
    monkeypatch.setattr(writing_provider.shutil,'which',lambda name:'/fixture/claude')
    monkeypatch.setattr(writing_provider.subprocess,'Popen',Process)
    monkeypatch.setattr(writing_provider,'context_window_advertised',lambda *args:None)
    turn=writing_provider.WritingTurn(tmp_path,'claude','','medium',None,events.append)
    result=turn.run('Read the source.')
    assert events==[
        {'type':'progress','text':'agentMessage'},
        {'type':'delta','text':'The arch'}, {'type':'delta','text':'itecture.'},
        {'type':'progress','text':'agentMessage'},
        {'type':'delta','text':'\n\n'},
        {'type':'delta','text':'The Wigner'}, {'type':'delta','text':' source.'}]
    assert result['text']=='The architecture.\n\nThe Wigner source.'
    assert result['status']=='completed'


def test_claude_live_deltas_preserve_three_successive_native_assistant_message_boundaries(
        tmp_path, monkeypatch):
    import io
    events=[]
    texts=["I'll start with the authored wake, then orient into the project.",
           "Orientation is complete. Now the actual bounded unit.",
           "Now the actual numerical producer behind the claims."]
    rows=[]
    for index,value in enumerate(texts):
        rows.extend([
            {"type":"stream_event","event":{"type":"message_start",
                "message":{"id":f"native-{index}","role":"assistant","content":[]}}},
            {"type":"stream_event","event":{"type":"content_block_delta",
                "delta":{"type":"text_delta","text":value}}},
            {"type":"stream_event","event":{"type":"message_stop"}},
        ])
        if index < len(texts)-1:
            rows.extend([
                {"type":"stream_event","event":{"type":"message_start",
                    "message":{"id":f"tool-{index}","role":"assistant","content":[]}}},
                {"type":"stream_event","event":{"type":"content_block_start",
                    "content_block":{"type":"tool_use","id":f"call-{index}","name":"read"}}},
                {"type":"stream_event","event":{"type":"message_stop"}},
            ])
    class Process:
        pid=12346
        def __init__(self,*args,**kwargs):
            self.stdin=io.StringIO();self.stdout=iter(json.dumps(row)+'\n' for row in rows)
        def wait(self,timeout=None):return 0
        def poll(self):return 0
    monkeypatch.setattr(writing_provider.shutil,'which',lambda name:'/fixture/claude')
    monkeypatch.setattr(writing_provider.subprocess,'Popen',Process)
    monkeypatch.setattr(writing_provider,'context_window_advertised',lambda *args:None)

    result=writing_provider.WritingTurn(tmp_path,'claude','','medium',None,events.append).run('Read.')
    streamed=''.join(event.get('text','') for event in events if event['type']=='delta')

    assert streamed=='\n\n'.join(texts)
    assert result['text']==streamed
    assert [event for event in events if event['type']=='progress']==[
        {'type':'progress','text':'agentMessage'} for _ in texts]


# --------------------------------------------------------------------------- #
# the process workspace: ONE function, named by the contract, verified empty
# --------------------------------------------------------------------------- #
def test_the_session_workspace_is_an_empty_directory_under_the_state_root(tmp_path, monkeypatch):
    """`session_workspace` is where a provider process runs, and nothing else is.

    It resolves through the ONE state-root organ the live app already sets
    (`laplace.engine.telemetry.state_dir`, src/laplace/telemetry.py:23, from LAPLACE_STATE as
    `writing_server.configure` sets it at src/laplace/writing_server.py:22), so this packet
    adds no environment variable and no config key of its own.
    """
    from laplace.engine import telemetry
    root = telemetry.state_dir()

    first = writing_operating.session_workspace("WS-7")
    assert first == root / writing_operating.PROCESS_WORKSPACES / "WS-7"
    assert first.is_dir() and not sorted(first.iterdir())
    # created on demand, and the same directory on the session's next process
    assert writing_operating.session_workspace("WS-7") == first
    # one session, one directory
    assert writing_operating.session_workspace("WS-8") != first
    # a process that belongs to no session (model discovery, which sends no turn)
    assert writing_operating.session_workspace() == \
        root / writing_operating.PROCESS_WORKSPACES / writing_operating.DISCOVERY_SESSION
    # a session id names ONE path segment, so no id can escape the workspaces root
    escape = writing_operating.session_workspace("../../etc")
    assert escape.parent == root / writing_operating.PROCESS_WORKSPACES
    assert escape.name == "------etc"


@pytest.mark.parametrize("name", writing_operating.PROCESS_INSTRUCTION_NAMES)
def test_the_workspace_refuses_every_instruction_file_a_runtime_would_read(tmp_path, name):
    """Fail closed: the app refuses the turn rather than hand over undeclared instructions.

    These five names are the inputs the two runtimes derive their own instructions from --
    CLAUDE.md and `.claude` (hooks, skills, agents, memory index) for the CLI, AGENTS.md and
    `.codex` for the App Server, and `.git` for the working-tree summary both put in front
    of the model.  The conventional alternative, a transport flag, was measured 2026-10-04
    and does not do this: `--setting-sources ""` leaves CLAUDE.md and memory in place and
    `--bare` kills subscription auth
    (evidence/WRITING_JOINS_2026-10-04/parity-probe/instruction-bytes-by-transport.json).
    """
    workspace = writing_operating.session_workspace("WS-9")
    planted = workspace / name
    if name.startswith("."):
        planted.mkdir()
    else:
        planted.write_text("instructions nobody declared\n", encoding="utf-8")

    with pytest.raises(ValueError) as refused:
        writing_operating.session_workspace("WS-9")
    assert name in str(refused.value)
    assert "outside the contract" in str(refused.value)


@pytest.mark.parametrize("name", writing_operating.PROCESS_INSTRUCTION_NAMES)
def test_the_workspace_refuses_an_ancestor_that_carries_instructions(tmp_path, name):
    """Contract amendment 4: the GUARANTEE wins over the location, so an ANCESTOR refuses.

    An empty directory inside a project is still that project's session, because both
    installed runtimes read their own instructions by walking UP from the directory they run
    in: measured 2026-10-05 on the installed Claude CLI with zero inference, a workspace at
    `<checkout>/.laplace-state-probe/session-workspaces/P1` offered this repository's own
    `serve-walk` command, 56 slash commands and 7 agents -- what the checkout itself
    offered, where a directory outside every checkout offered 54 and 6
    (evidence/WRITING_JOINS_2026-10-04/S1/session-workspace/cli-cwd-probe/summary.json).
    So the app fails closed and the refusal names the ANCESTOR DIRECTORY and the file found
    there, because the launch is what has to change (a `--state` root outside the checkout;
    src/laplace/web/writing_server.py, docs/writing-container.md).
    """
    workspace = writing_operating.session_workspace("WS-ancestor")
    parent = workspace.parent
    planted = parent / name
    if name.startswith("."):
        planted.mkdir()
    else:
        planted.write_text("instructions nobody declared\n", encoding="utf-8")

    with pytest.raises(ValueError) as refused:
        writing_operating.session_workspace("WS-ancestor")
    assert "outside the contract" in str(refused.value)
    assert name in str(refused.value)
    assert str(parent) in str(refused.value)


def test_the_ancestor_walk_stops_at_home_and_checks_everything_below_it(tmp_path, monkeypatch):
    """The stop rule, pinned on both sides: $HOME is the floor, and the walk reaches it.

    `~/.claude` is loaded for every working directory, so the user-level floor is not a
    refusal -- it is NAMED, with its measured counts, in
    `session_policy()['process']['instructions_outside_the_contract']`.  Everything BETWEEN
    the workspace and $HOME is a project the runtime walks up into, and is refused.  This
    test exists because the first spelling of the rule (`home in parent.parents`, which is
    true of every directory strictly below $HOME) broke on the FIRST ancestor of any
    workspace under the home directory -- which is exactly where the live app's state root
    lives (~/.mcp-gerard/laplace), so the check was dead where it had to work.
    """
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    project = home / "project"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("LAPLACE_STATE", str(project / ".laplace-state"))

    # $HOME's own .claude is the floor, not a refusal
    workspace = writing_operating.session_workspace("WS-floor")
    assert workspace.is_dir() and workspace.parent.parent == project / ".laplace-state"
    # a directory BETWEEN the workspace and $HOME is refused, and named
    (project / ".git").mkdir()
    with pytest.raises(ValueError) as refused:
        writing_operating.session_workspace("WS-floor")
    assert str(project) in str(refused.value) and ".git" in str(refused.value)
    assert str(home / ".claude") not in str(refused.value)


@pytest.mark.parametrize('provider_name',['claude','codex'])
def test_claude_invocation_style_change_reports_shared_kernel_binding_impact(tmp_path,monkeypatch,provider_name):
    import copy
    _project(tmp_path)
    previous_policy=copy.deepcopy(writing_operating.session_policy())
    previous_policy.pop('output_style')
    previous_policy['transport_arguments']['claude']['arguments'].pop('--settings')
    with monkeypatch.context() as prior:
        prior.setattr(writing_operating,'session_policy',lambda *args:previous_policy)
        before=writing_operating.build('book','work',tmp_path)
    after=writing_operating.build('book','work',tmp_path)
    assert before['native_registration_signature']==after['native_registration_signature']
    assert before['tool_contract_digest']!=after['tool_contract_digest']
    assert writing_operating.kernel(before,provider_name)!=writing_operating.kernel(after,provider_name)
    session=turn_admission.new_session(tmp_path,'book',provider_name,'','medium')
    records.bank(tmp_path,{'record':'writing-binding','id':'WB-style-before','session_id':session['id'],
        'native_id':'original-native','model':'actual','tool_contract_digest':before['tool_contract_digest'],
        'native_registration_signature':before['native_registration_signature']})
    records.bank(tmp_path,{'record':'writing-turn','id':'WT-style-before','session_id':session['id'],
        'project':'book','mode':'work','text':'Earlier','orientation':turn_context._orientation_snapshot(before)})
    records.bank(tmp_path,{'record':'writing-reply','id':'WR-style-before','session_id':session['id'],
        'turn_id':'WT-style-before','project':'book','status':'completed','text':'Saved reply.'})
    captured=[]
    class Provider:
        def __init__(self,cwd,provider,model,effort,native_id,event,mode,**kwargs):self.native_id=native_id;self.event=event;captured.append(self)
        def run(self,prompt):
            self.process_blocks=writing_operating.process_instructions(self.operating_brief,provider_name,resumed=bool(self.native_id))
            self.delivery=writing_operating.delivery_receipt(self.operating_brief,provider_name,prompt,resumed=bool(self.native_id))
            self.event({'type':'session','native_id':self.native_id or 'replacement','model':'actual','provider':provider_name})
            return {'status':'completed','text':'done'}
    monkeypatch.setattr(writing_provider, 'WritingTurn',Provider)
    started=turn_admission.start_turn(tmp_path,{'project':'book','session_id':session['id'],'text':'Continue','mode':'work','request_id':'style-impact'})
    turn=_wait(tmp_path,started)
    assert captured[-1].native_id is None
    assert turn['native_contract_migration']['changed_kernel_members']==['tool_contract_digest']

    assert captured[-1].process_blocks['session_slot']==writing_operating.kernel(captured[-1].operating_brief,provider_name)
    assert captured[-1].delivery['parts']['body']['state']=='PREPARED'
    again=turn_admission.start_turn(tmp_path,{'project':'book','session_id':session['id'],'text':'Continue unchanged','mode':'work','request_id':'style-unchanged'})
    resumed=_wait(tmp_path,again)
    assert captured[-1].native_id=='replacement' and resumed['native_contract_migration'] is None
    assert captured[-1].delivery['parts']['body']['state']=='WITHHELD'
    assert writing_operating.body(captured[-1].operating_brief) not in captured[-1].process_blocks['turn_prefix']
    assert captured[-1].process_blocks['session_slot']==('' if provider_name=='codex' else writing_operating.kernel(captured[-1].operating_brief,provider_name))
