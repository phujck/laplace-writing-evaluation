"""The workspace activity view remains an exact, read-only projection."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from laplace.work import history as author_history
from laplace.web import authoring as authoring_surface
from laplace.writing import operations
from laplace.core import checkout


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _fixture(root: Path) -> None:
    manuscript = root / "sources" / "book"
    manuscript.mkdir(parents=True)
    (manuscript / "main.tex").write_text("Old prose.\n", encoding="utf-8")
    (root / "registry_projects.json").write_text(json.dumps({"projects": [{
        "name": "book", "kind": "tex", "project_dir": "sources/book", "manuscript_dir": "sources/book",
        "tex_root": "sources/book", "versions_dir": "sources/book/versions",
        "document": {"root": "main.tex", "manuscript_dir": "sources/book"}}]}), encoding="utf-8")
    _write(manuscript / "authoring.json", {"schema_version": "laplace.authoring/1", "project": "book", "revision": 1,
        "argument_revision": 0, "argument": "", "framing": {}, "section_ids": [], "contexts": [], "corrections": [{
            "id": "AC-one", "project": "book", "created": "2026-09-30T10:00:00Z", "text": "Retain the qualification.",
            "kind": "factual", "scope": "passage", "anchor": {"file": "main.tex", "line_start": 1, "line_end": 1},
            "by": "author", "status": "open"}, {"id": "AC-note", "project": "book", "created": "2026-09-30T09:59:00Z", "text": "Keep this scope.",
            "kind": "style", "scope": "project", "anchor": {}, "by": "author", "status": "open"}]})
    feedback = manuscript / "feedback" / "feedback.jsonl"
    feedback.parent.mkdir()
    feedback.write_text(json.dumps({"id": "FB-edit", "record": "source-edit", "ts": "2026-09-30T10:00:30Z", "by": "author", "anchor": {"file": "main.tex", "line_start": 1, "line_end": 1}, "text": "Direct Walk edit.", "before": "Old prose.", "after": "Walk prose."}) + "\n", encoding="utf-8")
    talk = root / "contract" / "talk.jsonl"
    talk.parent.mkdir(parents=True)
    rows = [
        {"record": "writing-session", "id": "WS-one", "project": "book", "provider": "codex", "model": "stale-model", "role": "author", "ts": "2026-09-30T10:01:00Z"},
        {"record": "writing-turn", "id": "WT-one", "session_id": "WS-one", "project": "book", "text": "Revise this passage.", "ts": "2026-09-30T10:02:00Z", "provider_settings": {"provider": "codex", "model": "recorded-model", "effort": "high"}},
        {"record": "writing-reply", "id": "WR-one", "turn_id": "WT-one", "session_id": "WS-one", "project": "book", "text": "Here is the revision.", "ts": "2026-09-30T10:02:30Z", "usage": {"provider": "codex"}, "context_tokens_used": 123},
        {"record": "writing-application", "id": "WA-one", "turn_id": "WT-one", "project": "book", "complete": True, "ts": "2026-09-30T10:03:00Z", "origin": "current-turn-tool", "actor": {"label": "eigen:session", "kind": "agent", "provider": "codex", "model": "recorded-model"}, "receipts": [{"version_id": "save-one"}], "owned_changes": {"schema_version": "laplace.owner-mutation/1", "files": [{"path": "sources/book/main.tex", "after_sha256": hashlib.sha256(b"New prose.\n").hexdigest()}]}, "edits": [{"file": "main.tex", "before": "Old prose.", "after": "New prose."}]},
        {"record": "writing-application", "id": "WA-human", "turn_id": "WT-one", "project": "book", "complete": True, "ts": "2026-09-30T10:03:01Z", "origin": "manuscript-review", "edits": [{"file": "main.tex", "before": "Old prose.", "after": "New prose."}]},
        {"record": "writing-tool-action", "id": "ACTION-research", "turn_id": "WT-one", "project": "book", "operation": "research_record", "ts": "2026-09-30T10:03:30Z", "outcome": {"receipts": ["result-one"], "views": ["research", "pipeline"], "revisions": {"revision": "sha256:record-r2"}, "output_sha256": "sha256:response-only"}},
    ]
    talk.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    saved = manuscript / "editor_saves" / "save-one"
    saved.mkdir(parents=True)
    saved_bytes = b"Old prose.\n"
    (saved / "main.tex").write_bytes(saved_bytes)
    _write(saved / "VERSION.json", {"version_id": "save-one", "ts": "2026-09-30T10:04:00Z", "author": "author", "surface": "editor", "file": "main.tex", "sha": hashlib.sha256(saved_bytes).hexdigest()})
    (root / "corpus_friction").mkdir(parents=True)
    (root / "corpus_friction" / "book.jsonl").write_text(json.dumps({"id": "RW-one", "ts": "2026-09-30T10:05:00Z", "kind": "edit-essence", "node": "claim:one", "value": "A revised claim.", "by": "manual"}) + "\n", encoding="utf-8")
    _write(manuscript / "research_records.json", {"records": [{"id": "result-one", "kind": "result", "revision": "sha256:record-r2", "summary": "Current transport result.", "question": "What moved?", "limitations": "Current limits."}], "history": [{"id": "result-one", "revision": "sha256:record-r2", "archived_at": "2026-09-30T10:06:00Z", "record": {"id": "result-one", "kind": "result", "revision": "sha256:record-r2", "summary": "Prior numerical result.", "question": "What moved?", "limitations": "Prior limits.", "provenance": {"recorded_at": "2026-09-30T10:06:00Z", "dependencies": []}}}], "history_dropped": 2})
    _write(manuscript / "formal" / "check_receipts.json", {"receipts": [{"id": "PROOF-one", "checked_at": "2026-09-30T10:07:00Z", "file": "proof.lean", "file_digest": "0" * 64, "declaration": "checkOne", "concept": {"id": "claim:one"}, "result": {"id": "result-one"}, "proof_status": "CHECKED"}]})
    _write(manuscript / "references.json", {"associations": [{"key": "ref-one", "claim_id": "claim:one", "reading_observations": [{"id": "READ-one", "reference_key": "ref-one", "source_sha256": "1" * 64, "locator": "characters 0–10", "observation": "passage returned by reference_text"}]}]})
    refs_path = manuscript / "references.json"
    owner_hash = hashlib.sha256(refs_path.read_bytes()).hexdigest()
    with talk.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"record": "writing-tool-action", "id": "ACTION-literature", "turn_id": "WT-one", "project": "book",
            "operation": "literature_import", "ts": "2026-09-30T10:07:30Z", "outcome": {
                "status": "SUCCEEDED", "identities": ["ref-one"], "output_sha256": "response-fingerprint",
                "owner_evidence": {"schema_version": "laplace.owner-evidence/1",
                    "files": [{"scope": "repository", "path": "sources/book/references.json", "after_sha256": owner_hash}],
                    "objects": [{"owner": "references", "id": "ref-one|claim:one", "key": "ref-one", "after_revision": "sha256:stored-record"}]}}}) + "\n")
    _write(manuscript / "research_runs" / "run-one.json", {"id": "run-one", "project": "book", "producer_id": "fixture-producer", "started_at": 10.0})
    _write(manuscript / "research_runs" / "run-one.receipt.json", {"state": "COMPLETE", "finished_at": 12.5})


def test_activity_is_bounded_scoped_and_uses_immutable_turn_settings(tmp_path):
    _fixture(tmp_path)
    value = author_history.history("book", {"view": "activity", "limit": 99}, tmp_path)
    assert value["schema_version"] == "laplace.activity-history/1"
    assert value["pagination"]["limit"] == 20
    turn = next(row for row in value["items"] if row["id"] == "activity:journal:WT-one")
    reply = next(row for row in value["items"] if row["id"] == "activity:journal:WR-one")
    assert turn["actor"]["kind"] == "unknown", "a writing request is not a provider action"
    assert reply["actor"]["model"] == "recorded-model"
    assert reply["actor"]["kind"] == "agent"
    assert author_history.history("book", {"file": "main.tex"}, tmp_path)["items"]
    assert all(row["category"] == "manuscript" for row in author_history.history("book", {"category": "manuscript"}, tmp_path)["items"])
    frozen = author_history.history("book", {"as_of": "2026-09-30T10:02:00Z"}, tmp_path)
    assert all(row["at"] is None or row["at"] <= "2026-09-30T10:02:00Z" for row in frozen["items"])
    first = author_history.history("book", {}, tmp_path)
    assert first["as_of"] == "2026-09-30T10:07:30Z"
    assert author_history.history("book", {"actor": "unknown"}, tmp_path)["items"]
    assert all(row["actor"]["kind"] == "unknown" for row in author_history.history("book", {"actor": "unknown"}, tmp_path)["items"])


def test_detail_verifies_banked_and_current_bytes_without_claiming_validity(tmp_path):
    _fixture(tmp_path)
    detail = author_history.detail("book", "activity:editor-save:save-one", tmp_path)
    assert [row["status"] for row in detail["hashes"]] == ["current", "unavailable"]
    (tmp_path / "sources" / "book" / "main.tex").write_text("Changed prose.\n", encoding="utf-8")
    changed = author_history.detail("book", "activity:editor-save:save-one", tmp_path)
    assert changed["hashes"][1]["status"] == "unavailable"
    assert "scientific validity" in changed["limitations"][0]
    correction = author_history.detail("book", "activity:authoring:AC-one", tmp_path)
    assert correction["hashes"][0]["status"] == "unrecorded"


def test_exact_id_is_required_and_help_stays_small(tmp_path):
    _fixture(tmp_path)
    try:
        author_history.detail("book", "activity:journal:missing", tmp_path)
    except ValueError as exc:
        assert "unavailable" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("missing exact activity item was accepted")
    contract = author_history.help()["views"]["activity"]
    assert contract["list"]["limit"] == 20
    assert "activity:journal" not in json.dumps(contract)


def test_durable_scientific_owners_are_visible_without_inventing_attribution(tmp_path):
    _fixture(tmp_path)
    value = author_history.history("book", {}, tmp_path)
    owners = {item["owner"]: item for item in value["items"]}
    assert {"concept", "research", "formal", "literature"} <= set(owners)
    assert owners["concept"]["actor"]["kind"] == "unknown", "manual is not safe evidence of a human/agent identity"
    assert owners["literature"]["at"] is None
    assert any("dropped 2" in item for item in value["limitations"])
    formal = author_history.detail("book", "activity:formal:PROOF-one", tmp_path)
    assert formal["hashes"][0]["status"] == "missing"
    assert {target["kind"] for target in owners["formal"]["targets"]} == {"formal", "concept", "research"}
    formal_target = owners["formal"]["targets"][0]
    assert formal_target["concept_id"] == "claim:one" and formal_target["receipt_id"] == "PROOF-one"
    feedback = next(item for item in value["items"] if item["id"] == "activity:authoring:FB-edit")
    assert feedback["targets"][0]["correction_id"] == "FB-edit"
    note = next(item for item in value["items"] if item["id"] == "activity:authoring:AC-note")
    assert note["targets"][0]["kind"] == "note"
    anchored_note = next(item for item in value["items"] if item["id"] == "activity:authoring:AC-one")
    assert [target["kind"] for target in anchored_note["targets"]] == ["note", "manuscript"]
    assert "correction_id" not in anchored_note["targets"][1]
    concept = author_history.detail("book", "activity:concept:RW-one", tmp_path)
    assert concept["hashes"][0]["status"] == "unrecorded"


def test_talk_projection_indexes_only_the_new_append_between_pages(tmp_path):
    _fixture(tmp_path)
    author_history.history("book", {}, tmp_path)
    key = (str(tmp_path.resolve()), "book")
    state = author_history._TALK_CACHE[key]
    first_rows, first_offset = len(state["rows"]), state["offset"]
    with (tmp_path / "contract" / "talk.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"record": "writing-tool-action", "id": "ACTION-later", "turn_id": "WT-one", "project": "book", "operation": "proof_check", "ts": "2026-09-30T11:00:00Z"}) + "\n")
    later = author_history.history("book", {"category": "formal"}, tmp_path)
    assert any(row["id"] == "activity:journal:ACTION-later" for row in later["items"])
    assert state["offset"] > first_offset and len(state["rows"]) == first_rows + 1
    author_history.history("book", {}, tmp_path)
    assert len(state["rows"]) == first_rows + 1, "a repeated page must not reread/duplicate the old talk prefix"


def test_canonical_research_action_uses_outcome_receipt_as_exact_result_target(tmp_path):
    _fixture(tmp_path)
    value = author_history.history("book", {"category": "research"}, tmp_path)
    action = next(row for row in value["items"] if row["id"] == "activity:journal:ACTION-research")
    target = next(row for row in action["targets"] if row["kind"] == "research")
    assert target["id"] == "result-one"
    assert target["label"] == "Current transport result."
    assert action["summary"] == "Recorded research result"
    detail = author_history.detail("book", action["id"], tmp_path)
    identity = next(row for row in detail["hashes"] if row["label"].startswith("Research record identity"))
    assert identity["status"] == "current" and identity["recorded"] == "sha256:record-r2"
    assert detail["comparison"]["changes"][0]["after"] == "What moved?"
    archive = next(row for row in author_history.history("book", {"category": "research"}, tmp_path)["items"] if row["owner"] == "research")
    assert action["id"] in archive["related_activity_ids"] and archive["id"] in action["related_activity_ids"]


def test_identical_application_effects_keep_human_approval_and_agent_execution_distinct(tmp_path):
    _fixture(tmp_path)
    items = author_history.history("book", {"category": "manuscript"}, tmp_path)["items"]
    agent = next(item for item in items if item["id"] == "activity:journal:WA-one")
    human = next(item for item in items if item["id"] == "activity:journal:WA-human")
    assert agent["actor"]["kind"] == "agent" and agent["summary"] == "Agent-applied revision"
    assert human["actor"]["kind"] == "human" and human["summary"] == "Author-approved revision"
    assert any(target.get("id") == "save-one" for target in agent["targets"])
    detail = author_history.detail("book", agent["id"], tmp_path)
    assert detail["hashes"][0]["status"] == "changed"


def test_telemetry_groups_only_recorded_activity_usage_runs_and_identity_types(tmp_path):
    _fixture(tmp_path)
    value = author_history.telemetry("book", {}, tmp_path)
    assert value["as_of"] == "2026-09-30T10:07:30Z"
    assert value["totals"]["unrecorded_date"] >= 1
    assert any(row["category"] == "research" and row["filter"]["as_of"] == value["as_of"]
               for row in value["series"]["by_category"])
    assert value["runs"] == [{"id": "run-one", "outcome": "COMPLETE", "producer_id": "fixture-producer",
                               "started_at": 10.0, "finished_at": 12.5, "duration_seconds": 2.5,
                               "result_id": None, "filter": None}]
    usage = value["usage"]["by_provider_model"][0]
    assert usage["provider"] == "codex" and usage["model"] == "recorded-model" and usage["latest_context_tokens_used"] == 123
    coverage = {row["type"]: row["count"] for row in value["identity_coverage"]}
    assert coverage["recorded_file_identities"] and coverage["record_revisions"] and coverage["response_fingerprints"]
    assert "sha256:" not in json.dumps(value)


def test_tool_attempt_telemetry_counts_original_rows_once_with_exact_drills(tmp_path):
    _fixture(tmp_path)
    path=tmp_path/"contract"/"talk.jsonl"
    extra=[
        {"record":"writing-tool-read","id":"READ-source","turn_id":"WT-one","project":"book",
         "operation":"source","ts":"2026-09-30T10:03:10Z","payload":{"files":["main.tex"]},"output_sha256":"digest"},
        {"record":"writing-tool-read-baseline","id":"READBASE-source","turn_id":"WT-one","project":"book",
         "operation":"source","ts":"2026-09-30T10:03:11Z","payload":{"files":["main.tex"]},"output_sha256":"digest2"},
        {"record":"writing-tool-failure","id":"FAIL-source","turn_id":"WT-one","project":"book",
         "operation":"source","ts":"2026-09-30T10:03:12Z","error":"failed"},
    ]
    with path.open("a",encoding="utf-8") as stream:
        for row in extra:stream.write(json.dumps(row)+"\n")

    value=author_history.telemetry("book",{},tmp_path);tools=value["tool_calls"]
    # Two fixture actions + one original read + one failure. Baseline is derived
    # bookkeeping and the reply contains no separately counted nested action.
    assert tools["total"]==4
    operations={row["operation"]:row["count"] for row in tools["by_operation"]}
    assert operations=={"source":2,"literature_import":1,"research_record":1}
    assert tools["filter"]=={"event_kind":"tool-attempt","as_of":"2026-09-30T10:07:30Z"}
    assert tools["coverage"]["storage_bytes_recorded"]>0
    assert tools["coverage"]["response_bytes_recorded"]==0
    assert tools["operations_omitted"]==tools["time_operation_bins_omitted"]==0
    scoped=author_history.telemetry("book",{"provider":"codex","model":"recorded-model",
        "from":"2026-09-30T10:03:00Z","to":"2026-09-30T10:04:00Z"},tmp_path)["tool_calls"]
    for row in [*scoped["by_operation"],*scoped["by_outcome"],*scoped["by_time_operation"],
                *scoped["session_choices"]]:
        assert row["filter"]["provider"]=="codex" and row["filter"]["model"]=="recorded-model"
        assert row["filter"]["as_of"]=="2026-09-30T10:07:30Z"
    assert all(row["filter"]["from"]>="2026-09-30T10:03:00Z" and
               row["filter"]["to"]<="2026-09-30T10:04:00Z" for row in scoped["by_time_operation"])
    assert author_history.telemetry("book",{"file":"main.tex"},tmp_path)["tool_calls"]["total"]==1
    source=author_history.history("book",{"event_kind":"tool-attempt","operation":"source"},tmp_path)
    assert {row["id"] for row in source["items"]}=={
        "activity:journal:READ-source","activity:journal:FAIL-source"}
    exact=author_history.record("book","activity:journal:READ-source",tmp_path)
    by_record_id=author_history.record("book","READ-source",tmp_path)
    assert by_record_id==exact
    assert "_storage_bytes" not in exact["record"]
    assert exact["measurements"] == [{"kind":"storage_bytes",
        "value":next(row for row in author_history._talk_rows(tmp_path) if row.get("id")=="READ-source")["_storage_bytes"],
        "unit":"bytes","basis":"exact stored journal line"}]


def test_literature_import_distinguishes_owner_bytes_record_identity_and_response_fingerprint(tmp_path):
    _fixture(tmp_path)
    value = author_history.history("book", {"category": "literature"}, tmp_path)
    action = next(row for row in value["items"] if row["id"] == "activity:journal:ACTION-literature")
    assert action["targets"] == [{"kind": "literature", "id": "ref-one", "label": "ref-one"}]
    detail = author_history.detail("book", action["id"], tmp_path)
    kinds = {row["kind"]: row for row in detail["hashes"]}
    assert kinds["file"]["status"] == "current"
    assert kinds["response"]["status"] == "recorded"
    assert detail["comparison"]["title"] == "Imported citation"


def test_exact_record_is_lazy_and_never_reconstructs_missing_text(tmp_path):
    _fixture(tmp_path)
    reply = author_history.record("book", "activity:journal:WR-one", tmp_path)
    assert reply["record_kind"] == "writing-reply" and reply["text"] == "Here is the revision."
    action = author_history.record("book", "activity:journal:ACTION-literature", tmp_path)
    assert action["text"] is None and action["record"]["operation"] == "literature_import"


def test_history_http_routes_telemetry_and_exact_record(tmp_path, monkeypatch):
    _fixture(tmp_path)
    monkeypatch.setattr(checkout, "repo_root", lambda: tmp_path)
    status, _content, body = authoring_surface.handle("/authoring/history", {"project": ["book"], "view": ["telemetry"]}, "GET", b"")
    assert status == 200 and json.loads(body)["series"]["activity"]
    status, _content, body = authoring_surface.handle("/authoring/history", {"project": ["book"], "view": ["record"], "id": ["activity:journal:WR-one"]}, "GET", b"")
    assert status == 200 and json.loads(body)["text"] == "Here is the revision."


def test_telemetry_keeps_malformed_dates_unrecorded_and_provider_drills_exact(tmp_path):
    _fixture(tmp_path)
    with (tmp_path / "contract" / "talk.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"record": "writing-tool-action", "id": "ACTION-bad-time", "turn_id": "WT-one",
            "project": "book", "operation": "research_record", "ts": "not-a-time"}) + "\n")
    value = author_history.telemetry("book", {"provider": "codex", "model": "recorded-model"}, tmp_path)
    assert value["totals"]["unrecorded_date"] >= 1
    assert value["usage"]["by_provider_model"][0]["filter"]["model"] == "recorded-model"
    assert all(row["filter"]["outcome"] == row["outcome"] for row in value["series"]["by_outcome"])


def test_concurrent_history_reads_index_each_journal_event_once(tmp_path,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import time
    path=tmp_path/'contract'/'talk.jsonl';path.parent.mkdir()
    rows=[{'record':'writing-turn','id':f'WT-{index}','project':'book'} for index in range(60)]
    path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
    original=Path.open
    class SlowRead:
        def __init__(self,stream):self.stream=stream
        def __enter__(self):return self
        def __exit__(self,*args):self.stream.close()
        def seek(self,*args):return self.stream.seek(*args)
        def tell(self):return self.stream.tell()
        def readline(self):
            line=self.stream.readline();time.sleep(.001);return line
    def opening(file,*args,**kwargs):
        stream=original(file,*args,**kwargs)
        return SlowRead(stream) if file==path and args==('rb',) else stream
    monkeypatch.setattr(Path,'open',opening)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda _:author_history._talk_rows(tmp_path),range(4)))
    assert all([row['id'] for row in result]==[row['id'] for row in rows] for result in results)
    assert len(author_history._talk_rows(tmp_path))==60


def test_exact_research_archive_keeps_scientific_record_object_and_scalar_owner_kind(tmp_path):
    _fixture(tmp_path)
    source=tmp_path/'sources/book/research_records.json'
    before=source.read_bytes()
    stored=json.loads(before)['history'][0]
    value=author_history.record('book','activity:research:result-one@sha256:record-r2',tmp_path)
    assert value['item']['id']=='activity:research:result-one@sha256:record-r2'
    assert value['item']['owner']=='research' and value['record_kind']=='research'
    assert value['record']['record']==stored['record']
    assert value['record']['revision']==stored['revision']
    assert value['measurements']==[] and source.read_bytes()==before
    value['record']['record']['summary']='caller-local change'
    assert author_history.record('book',value['item']['id'],tmp_path)['record']['record']==stored['record']


def test_one_file_coordinate_resolves_the_same_across_history_telemetry_native_and_http(tmp_path, monkeypatch):
    """M5-I1/R1: a BOUND manuscript target is identified by its checkout path (`repo_file`).
    The query is resolved ONCE at the owner (author_history.file_scope) to ONE qualified
    source through the selected source and the identities already bound: the walk's
    qualified path and the manuscript-relative path a source block carries find the same
    rows; a row bound to another edition under the same display name is never joined; an
    unbound legacy record stays reachable by its exact recorded name and never drags a
    BOUND row of the same name in; a bare basename never widens; an ambiguous spelling is
    stated and matches nothing. The history page, the telemetry scope, the native operation
    and the HTTP route consume the same resolution, and the returned `repo_file` is the
    continuation coordinate that survives a selection change."""
    _fixture(tmp_path)
    manuscript = tmp_path / "sources" / "book"
    for relative in ("chapters/one.tex", "appendix/one.tex"):
        path = manuscript / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Chapter prose.\n", encoding="utf-8")
    # saves: two same-named current files, one old-edition save with the SAME display spelling as the
    # current chapter, and one legacy save that recorded a bare name without a checkout path
    for ident, relative, bound, stamp in (("save-two", "chapters/one.tex", "sources/book/chapters/one.tex", "10:08:00"),
                                          ("save-three", "appendix/one.tex", "sources/book/appendix/one.tex", "10:09:00"),
                                          ("save-old", "chapters/one.tex", "sources/old-edition/chapters/one.tex", "10:07:50"),
                                          ("save-legacy", "one.tex", None, "10:07:40")):
        saved = manuscript / "editor_saves" / ident
        saved.mkdir(parents=True)
        (saved / "one.tex").write_bytes(b"Chapter prose.\n")
        _write(saved / "VERSION.json", {"version_id": ident, "ts": f"2026-09-30T{stamp}Z", "author": "author", "surface": "editor",
                                        "file": relative, **({"source_file": bound} if bound else {}), "sha": hashlib.sha256(b"Chapter prose.\n").hexdigest()})
    # the saved delta: the producer banked the checkout path, the display spelling is the basename
    with (manuscript / "feedback" / "feedback.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"id": "FB-delta", "record": "source-edit", "ts": "2026-09-30T10:08:30Z", "by": "author",
                                 "anchor": {"file": "one.tex", "repo_file": "sources/book/chapters/one.tex", "line_start": 1, "line_end": 1},
                                 "text": "Chapter edit.", "before": "Chapter prose.", "after": "Chapter prose, revised."}) + "\n")
    ids = lambda value: sorted(row["id"] for row in value["items"])
    page = lambda **query: author_history.history("book", {"view": "activity", **query}, tmp_path)
    bound = ["activity:authoring:FB-delta", "activity:editor-save:save-two"]
    current = {"file": "chapters/one.tex", "repo_file": "sources/book/chapters/one.tex", "relative": "chapters/one.tex",
               "resolution": "selected-source", "names": ["chapters/one.tex", "sources/book/chapters/one.tex"]}
    resolved = lambda value: {key: item for key, item in value["scope"].items() if key != "continuation"}
    relative = page(file="chapters/one.tex")
    assert ids(relative) == bound, "the manuscript-relative spelling finds the snapshot and the delta, not the old edition under the same name"
    assert resolved(relative) == current
    assert relative["scope"]["continuation"] == {"file": "sources/book/chapters/one.tex", "file_scope": '{"names":["chapters/one.tex","sources/book/chapters/one.tex"],"repo_file":"sources/book/chapters/one.tex"}'}
    qualified = page(file="sources/book/chapters/one.tex")
    assert ids(qualified) == bound and resolved(qualified) == {**current, "file": "sources/book/chapters/one.tex"}, "the walk's checkout path is the same coordinate"
    assert qualified["scope"]["continuation"] == relative["scope"]["continuation"], "both spellings continue with one handle"
    old = page(file="sources/old-edition/chapters/one.tex")
    assert ids(old) == ["activity:editor-save:save-old"], "the other edition is reachable only by its own identity"
    assert old["scope"]["resolution"] == "checkout" and old["scope"]["relative"] is None, "a known identity outside the selected source resolves to itself"
    assert ids(page(file="appendix/one.tex")) == ["activity:editor-save:save-three"], "a same-named file elsewhere is another coordinate"
    legacy = page(file="one.tex")
    assert ids(legacy) == ["activity:editor-save:save-legacy"], "a bare name finds only the unbound record that recorded it; the BOUND delta with that display name is not joined"
    assert legacy["scope"]["repo_file"] == "sources/book/one.tex" and legacy["scope"]["names"] == ["one.tex", "sources/book/one.tex"]
    assert "activity:editor-save:save-one" in ids(page(file="main.tex")), "the legacy UNPROVED save keeps its recorded name"
    # the rows keep their recorded spellings and bindings
    delta = next(row for row in relative["items"] if row["id"] == "activity:authoring:FB-delta")
    assert delta["targets"][0]["file"] == "one.tex" and delta["targets"][0]["repo_file"] == "sources/book/chapters/one.tex" and delta["targets"][0]["binding"] == "BOUND"
    assert next(row for row in page(file="main.tex")["items"] if row["id"] == "activity:editor-save:save-one")["targets"][0]["binding"] == "UNPROVED"
    assert "scope" not in page(), "an unscoped page is unchanged"
    # an unsafe spelling resolves to no identity and reaches no BOUND row
    assert page(file="../sources/book/chapters/one.tex")["items"] == [] and page(file="../sources/book/chapters/one.tex")["scope"]["resolution"] == "unresolved"
    # telemetry, the native operation and the HTTP route share the resolution
    telemetry = author_history.telemetry("book", {"file": "chapters/one.tex"}, tmp_path)
    assert telemetry["totals"]["activity"] == len(bound) and telemetry["scope"] == {"file": "chapters/one.tex"}, "the telemetry scope counts the same rows and echoes the requested spelling"
    native = operations._execute(tmp_path, "book", "work", "author_history", {"view": "activity", "file": "chapters/one.tex"})
    assert ids(native) == bound and native["scope"] == relative["scope"]
    monkeypatch.setattr(checkout, "repo_root", lambda: tmp_path)
    status, _content, body = authoring_surface.handle("/authoring/history", {"project": ["book"], "view": ["activity"], "file": ["chapters/one.tex"]}, "GET", b"")
    assert status == 200
    over_http = json.loads(body)
    assert ids(over_http) == bound and over_http["scope"] == relative["scope"]
    # an ambiguous spelling: the same relative path is also a file at the checkout root
    (tmp_path / "chapters").mkdir()
    (tmp_path / "chapters" / "one.tex").write_text("A root-level file.\n", encoding="utf-8")
    ambiguous = page(file="chapters/one.tex")
    assert ambiguous["items"] == [] and ambiguous["scope"]["resolution"] == "ambiguous"
    assert ambiguous["scope"]["candidates"] == ["chapters/one.tex", "sources/book/chapters/one.tex"]
    assert any("ambiguous" in note for note in ambiguous["limitations"])
    assert ids(page(file="sources/book/chapters/one.tex")) == bound, "the checkout path stays exact"
    (tmp_path / "chapters" / "one.tex").unlink()
    (tmp_path / "chapters").rmdir()


def test_a_scoped_walk_keeps_its_whole_first_page_basis_when_the_selection_changes(tmp_path, monkeypatch):
    """M5-R1 continuation: the first page of a file walk returns its whole basis as a handle
    (`scope.continuation`: the stable source and the recorded names it admitted). A later page
    that asks with that handle keeps the same membership and order under the same cutoff after
    the selected source moved, so no row is skipped or repeated across mixed legacy and BOUND
    rows at any page size; a handle that disagrees with the `file` beside it, or a malformed one,
    is refused before any offset is applied. Native and HTTP continue with the same handle."""
    _fixture(tmp_path)
    manuscript = tmp_path / "sources" / "book"
    (manuscript / "chapters").mkdir()
    (manuscript / "chapters" / "one.tex").write_text("Chapter prose.\n", encoding="utf-8")
    # BOUND saves of the current chapter interleaved with legacy saves that recorded only its relative name
    for ident, bound, stamp in (("save-a", True, "10:08:00"), ("legacy-b", False, "10:08:10"), ("save-c", True, "10:08:20"), ("legacy-d", False, "10:08:30"), ("save-e", True, "10:08:40")):
        saved = manuscript / "editor_saves" / ident
        saved.mkdir(parents=True)
        (saved / "one.tex").write_bytes(b"Chapter prose.\n")
        _write(saved / "VERSION.json", {"version_id": ident, "ts": f"2026-09-30T{stamp}Z", "author": "author", "surface": "editor", "file": "chapters/one.tex",
                                        **({"source_file": "sources/book/chapters/one.tex"} if bound else {}), "sha": hashlib.sha256(b"Chapter prose.\n").hexdigest()})
    page = lambda **query: author_history.history("book", {"view": "activity", **query}, tmp_path)
    ids = lambda value: [row["id"] for row in value["items"]]
    whole = page(file="chapters/one.tex")
    expected = ["activity:editor-save:" + name for name in ("save-e", "legacy-d", "save-c", "legacy-b", "save-a")]
    assert ids(whole) == expected, "legacy rows by their recorded relative name and BOUND rows by identity, in one order"
    assert whole["scope"]["continuation"] == {"file": "sources/book/chapters/one.tex",
                                               "file_scope": json.dumps({"names": ["chapters/one.tex", "sources/book/chapters/one.tex"], "repo_file": "sources/book/chapters/one.tex"}, sort_keys=True, separators=(",", ":"))}
    from laplace.manuscript import manuscript_source
    real = manuscript_source.resolve
    moved = {"on": False}
    monkeypatch.setattr(manuscript_source, "resolve", lambda project, root=None, *a, **k: {**real(project, root, *a, **k), **({"manuscript_dir": "sources/other"} if moved["on"] else {})})

    def walk(limit):
        """The walk a consumer makes: the first page by the relative spelling, every later page by the handle."""
        first = page(file="chapters/one.tex", limit=limit)
        seen, handle, as_of = ids(first), first["scope"]["continuation"], first["as_of"]
        offset = first["pagination"]["next_offset"]
        moved["on"] = True   # the selected source moves after the first page
        try:
            while offset is not None:
                later = page(**handle, offset=offset, as_of=as_of, limit=limit)
                assert later["scope"]["resolution"] == "continuation" and later["scope"]["continuation"] == handle and later["as_of"] == as_of
                seen += ids(later)
                offset = later["pagination"]["next_offset"]
        finally:
            moved["on"] = False
        return seen
    assert walk(1) == expected and walk(2) == expected, "no row skipped or repeated at either page size"
    # the relative spelling after the move means the new selection's file: only the legacy names still match, so the
    # same offset lands on a different membership (Root's counterexample); that is what the handle protects against
    moved["on"] = True
    drifted = page(file="chapters/one.tex", offset=1, as_of=whole["as_of"], limit=1)
    assert drifted["scope"]["repo_file"] == "sources/other/chapters/one.tex" and ids(drifted) == ["activity:editor-save:legacy-b"] and drifted["pagination"]["total"] == 2
    # a changed basis is refused before any offset applies
    handle = whole["scope"]["continuation"]
    import pytest
    with pytest.raises(ValueError, match="basis changed"):
        page(file="sources/other/chapters/one.tex", file_scope=handle["file_scope"], offset=1, as_of=whole["as_of"])
    with pytest.raises(ValueError, match="continuation handle"):
        page(file="sources/book/chapters/one.tex", file_scope=json.dumps({"repo_file": "sources/book/chapters/one.tex", "names": ["../x"]}), offset=1)
    with pytest.raises(ValueError, match="continuation handle"):
        page(file="sources/book/chapters/one.tex", file_scope="not json", offset=1)
    # native and HTTP continue with the same handle after the move
    native = operations._execute(tmp_path, "book", "work", "author_history", {"view": "activity", **handle, "offset": 1, "as_of": whole["as_of"], "limit": 2})
    assert ids(native) == expected[1:3] and native["scope"]["continuation"] == handle
    monkeypatch.setattr(checkout, "repo_root", lambda: tmp_path)
    status, _content, body = authoring_surface.handle("/authoring/history", {"project": ["book"], "view": ["activity"], "file": [handle["file"]], "file_scope": [handle["file_scope"]],
                                                                             "offset": ["3"], "as_of": [whole["as_of"]], "limit": ["2"]}, "GET", b"")
    assert status == 200 and ids(json.loads(body)) == expected[3:5]
    moved["on"] = False
    # the telemetry scope shares the carried basis
    assert author_history.telemetry("book", {**handle}, tmp_path)["totals"]["activity"] == len(expected)


def test_a_carried_basis_without_its_file_is_refused_at_the_common_boundary_for_every_consumer(tmp_path, monkeypatch):
    """M5 scope admission: a valid continuation handle whose `file` is omitted, empty or whitespace is neither a
    project-wide read nor a scoped one. It is refused once, at the owner's common admission, before any filter or
    slice, so no consumer (activity page, telemetry, native, HTTP) can receive project-wide rows under a scoped echo.
    The valid pair keeps its exact mixed membership."""
    _fixture(tmp_path)
    manuscript = tmp_path / "sources" / "book"
    (manuscript / "chapters").mkdir()
    (manuscript / "chapters" / "one.tex").write_text("Chapter prose.\n", encoding="utf-8")
    for ident, bound, stamp in (("save-a", True, "10:08:00"), ("legacy-b", False, "10:08:10"), ("save-c", True, "10:08:20")):
        saved = manuscript / "editor_saves" / ident
        saved.mkdir(parents=True)
        (saved / "one.tex").write_bytes(b"Chapter prose.\n")
        _write(saved / "VERSION.json", {"version_id": ident, "ts": f"2026-09-30T{stamp}Z", "author": "author", "surface": "editor", "file": "chapters/one.tex",
                                        **({"source_file": "sources/book/chapters/one.tex"} if bound else {}), "sha": hashlib.sha256(b"Chapter prose.\n").hexdigest()})
    page = lambda **query: author_history.history("book", {"view": "activity", **query}, tmp_path)
    ids = lambda value: [row["id"] for row in value["items"]]
    first = page(file="chapters/one.tex", limit=1)
    handle = first["scope"]["continuation"]
    expected = ["activity:editor-save:" + name for name in ("save-c", "legacy-b", "save-a")]
    assert ids(page(**handle)) == expected, "the valid pair keeps the mixed membership"
    whole_project = len(page()["items"])
    assert whole_project > len(expected)
    import pytest
    monkeypatch.setattr(checkout, "repo_root", lambda: tmp_path)
    for absent in ({}, {"file": ""}, {"file": "   "}):
        query = {"file_scope": handle["file_scope"], **absent}
        with pytest.raises(ValueError, match="needs the file it continues"):
            page(**query, offset=0)
        with pytest.raises(ValueError, match="needs the file it continues"):
            author_history.telemetry("book", query, tmp_path)
        with pytest.raises(ValueError, match="needs the file it continues"):
            operations._execute(tmp_path, "book", "work", "author_history", {"view": "activity", **query})
        status, _content, body = authoring_surface.handle("/authoring/history", {"project": ["book"], "view": ["activity"], **{key: [value] for key, value in query.items()}}, "GET", b"")
        assert status != 200 and "needs the file it continues" in body.decode("utf-8", "replace"), (status, body[:200])
    # a blank carried basis is no basis: the plain project-wide read stands
    assert len(page(file_scope="   ")["items"]) == whole_project and "scope" not in page(file_scope="   ")
