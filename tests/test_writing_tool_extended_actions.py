"""Focused fixture coverage for writer actions backed by existing owners."""
from __future__ import annotations

import json
import hashlib

import pytest

from laplace.research import references_surface
from laplace.native import contracts as writing_contracts, tools as writing_tools
from laplace.writing import operating as writing_operating
from laplace.writing import reads
from laplace.manuscript import source_application
from laplace.writing import turn_reads
from laplace.writing import records as writing_records
from laplace.writing.records import _fold as records_fold
from laplace.pipeline import authoring


def _project(root):
    (root / "contract").mkdir()
    manuscript = root / "proj" / "manuscript"
    manuscript.mkdir(parents=True)
    (root / "registry_projects.json").write_text(json.dumps({"projects": [{
        "name": "p", "kind": "conceptric", "project_dir": "proj",
        "tex_root": "proj/manuscript",
    }]}), encoding="utf-8")
    (manuscript / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\nText.\n"
        "\\bibliography{sources}\n\\end{document}\n", encoding="utf-8")
    (manuscript / "sources.bib").write_text("", encoding="utf-8")
    (root / "proj" / "data.csv").write_text("x,y\n1,2\n2,3\n", encoding="utf-8")
    return manuscript


def test_every_deployed_writer_operation_has_an_explicit_contract():
    deployed = reads.READS | reads.WRITES
    assert deployed <= set(writing_contracts.CONTRACTS)
    # The whole-tool fallback is gone: an undeclared operation is refused by name
    # rather than served the owner's entire schema under a generic summary
    # (the old writing_contracts.py:623-628).
    with pytest.raises(ValueError, match="no declaration is deployed"):
        writing_contracts.exact_contract("future_uncontracted_action", permitted=True)


class _Library:
    def item(self, key):
        if key != "ABCDEFGH":
            return "fixture", None
        return "fixture", {"key": key, "version": "1", "modified": "now",
            "item_type": "journalArticle", "title": "Fixture Paper",
            "creators": ["Ada Lovelace"], "year": "2024", "doi": "10.1/fixture",
            "url": "", "citation_key": "fixture_paper", "attachments": []}


def test_writer_dispatches_reference_attach_and_attached_read(tmp_path, monkeypatch):
    manuscript = _project(tmp_path)
    monkeypatch.setattr(references_surface, "Library", _Library)

    attached = writing_tools.execute(tmp_path, "p", "work", "reference_attach", {
        "key": "ABCDEFGH", "claim_id": "claim:fixture", "note": "Fixture support."})
    listed = writing_tools.execute(tmp_path, "p", "work", "references_attached", {})

    assert attached["association"]["citekey"] == "fixture_paper"
    assert "@article{fixture_paper," in (manuscript / "sources.bib").read_text(encoding="utf-8")
    assert listed["associations"][0]["key"] == "ABCDEFGH"


def test_writer_dispatches_visual_place_and_run_lifecycle(tmp_path):
    manuscript = _project(tmp_path)
    spec = {"id": "fixture-plot", "title": "Fixture plot", "question": "Does y rise?",
            "kind": "plot", "caption": "Fixture plot.", "source_data": "data.csv",
            "x": "x", "series": ["y"]}

    assert writing_tools.execute(tmp_path, "p", "work", "visual_create", {"spec": spec})["readiness"] == "SPECIFIED"
    assert writing_tools.execute(tmp_path, "p", "work", "visual_render", {"id": "fixture-plot"})["readiness"] == "GENERATED"
    placed = writing_tools.execute(tmp_path, "p", "work", "visual_place", {
        "id": "fixture-plot", "file": "main.tex", "after_line": 3})

    runs = manuscript / "research_runs"; runs.mkdir()
    (runs / "run-fixture.json").write_text(json.dumps({"id": "run-fixture", "state": "RUNNING"}), encoding="utf-8")
    status = writing_tools.execute(tmp_path, "p", "work", "run_status", {"id": "run-fixture"})
    cancelled = writing_tools.execute(tmp_path, "p", "work", "run_cancel", {"id": "run-fixture"})

    assert placed["placed_at"] == "main.tex"
    assert "\\label{fig:fixture-plot}" in (manuscript / "main.tex").read_text(encoding="utf-8")
    assert status["state"] == "RUNNING" and cancelled["ok"] is True
    assert (runs / "run-fixture.cancel").read_text(encoding="utf-8") == "cancelled"


def _served_input(root, action):
    """The input a served help names: inline, or (D2 help sections) its exact `input` section read through the same door."""
    if "input" in action or "input" not in (action.get("sections") or {}).get("chars", {}):
        return action["input"]
    assert "input_summary" in action, "a moved input is named and summarised"
    return writing_tools.execute(root, "p", "work", "help", {"operation": action["operation"], "section": "input"})["action"]["value"]


def test_writer_help_is_operation_bounded_and_artifacts_allow_project_files(tmp_path):
    _project(tmp_path)
    help_value = writing_tools.execute(tmp_path, "p", "work", "help", {"operation": "visual_place"})
    saved = writing_tools.execute(tmp_path, "p", "work", "store_artifact", {
        "path": "tooling/generated/config.yaml", "before": None,
        "content": "enabled: true\n", "reason": "fixture"})

    # The example is generated from the schema, so the assertion is about its shape,
    # not about a literal somebody typed: visual_place requires the spec id and the
    # figure's expected_revision, and the identity field arrives as this project's live
    # token or as the read that would obtain it.
    example = help_value["action"]["example"]
    schema = _served_input(tmp_path, help_value["action"])
    # `id` plus one of {file, section}: the example satisfies the anyOf as well as the
    # required list, which a template built from `required` alone would not.
    assert set(example) == {"id", "file"}, example
    assert set(schema["required"]) <= set(example) <= set(schema["properties"])
    # The one home this door guards, with the read that serves it. The old help said in
    # prose that source.source_revision must NOT be sent as expected_source_revision
    # (GRAMMAR.md section 1.3); the field now carries its home instead.
    guarded = {row["home_kind"]: row for row in help_value["action"]["expected"]}
    assert list(guarded) == ["selected-edition"], guarded
    assert guarded["selected-edition"]["asked_for_as"] == ["expected_source_revision"]
    assert guarded["selected-edition"]["read"] == "source {} -> document.revision"
    assert "tool" not in help_value and "operation_payload_contracts" not in help_value
    assert saved["saved"] == "proj/tooling/generated/config.yaml"


def test_concept_and_logical_help_use_deployed_string_operation_variants(tmp_path):
    _project(tmp_path)
    # help {operation} serves the variant INDEX for a door with more than three of
    # them, and one variant on request: the full oneOf was 11,303 characters for
    # logical_plan_change alone (context-economy.md finding 4).
    index=writing_tools.execute(tmp_path,'p','work','help',{'operation':'logical_plan_change'})['action']
    assert 'connect' in index['variants'] and 'input' not in index
    connect=writing_tools.execute(tmp_path,'p','work','help',
        {'operation':'logical_plan_change','variant':'connect'})['action']['input']
    assert {'operation','base_revision','source','target','relation','rationale'}<=set(connect['required'])
    assert connect['properties']['operation']=={'const':'connect'}
    assert 'node_kind' not in connect['properties']
    add=writing_tools.execute(tmp_path,'p','work','help',
        {'operation':'concept_change','variant':'add_node'})['action']['input']
    assert {'node_kind','essence','parent','target','ref'}<=set(add['properties'])
    assert add['properties']['operation']=={'const':'add_node'}


def test_research_record_help_names_existing_claim_binding_follow_through(tmp_path):
    _project(tmp_path)
    action=writing_tools.execute(tmp_path,'p','work','help',{'operation':'research_record'})['action']
    binding=action['next_steps']['bind_result']
    assert binding['write']['operation']=='structure_change'
    assert binding['write']['payload']['operation']=='bind_results'
    assert [row['operation'] for row in binding['reads']]==['concept','structure']
    assert 'Do not infer' in binding['safeguard']


def test_writer_dispatches_current_turn_apply_revision(tmp_path, monkeypatch):
    _project(tmp_path)
    calls = []
    monkeypatch.setattr(source_application, 'apply_revision', lambda root, project, turn_id, payload: (
        calls.append((root, project, turn_id, payload)) or {"complete": True, "id": "WA-fixture"}))
    monkeypatch.setattr(turn_reads, 'refresh_turn_read_baselines',
                        lambda *args: (_ for _ in ()).throw(AssertionError("apply owns its own baseline")))

    result = writing_tools.execute(tmp_path, "p", "work", "apply_revision", {
        "proposal": {"edits": []}}, turn_id="WT-fixture")

    assert calls[0][1:3] == ("p", "WT-fixture")
    assert result["action_receipt"]["refreshed_read_baselines"] == 0


def test_large_native_write_responses_keep_receipts_and_omit_repeated_bodies():
    action={"id":"ACTION-x","status":"SUCCEEDED","views":["manuscript"],
            "identities":[],"receipts":["WA-x"],"paths":[],"revisions":{},
            "refreshed_read_baselines":0}
    applied=writing_tools._compact_write_response("p","apply_revision",{},
        {"id":"WA-x","complete":True,"edits":[{"file":"chapter.tex","before":"a"*20000,
          "after":"b"*20000}],"action_receipt":action})
    assert applied["complete"] is True and applied["files"]==["chapter.tex"]
    assert "edits" not in applied and applied["next_read"]["payload"]["id"]=="activity:journal:WA-x"
    framed=writing_tools._compact_write_response("p","framing",{},
        {"project":"p","revision":3,"argument_revision":2,
         "framing":{"purpose":"Explain."},"contexts":[{"body":"x"*20000}]})
    assert framed["framing"]=={"purpose":"Explain."} and "contexts" not in framed
    producer=writing_tools._compact_write_response("p","research_producer",{},
        {"producer":{"id":"p","executable":"run.py","dependencies":["x"*20000]}})
    assert producer["producer"]=={"id":"p","executable":"run.py"}


def test_source_read_defaults_to_turn_selection_and_returns_per_file_guard(tmp_path):
    _project(tmp_path)
    records_fold._CACHE.clear()
    writing_records.bank(tmp_path, {"record": "writing-session", "id": "WS-source",
        "project": "p", "provider": "codex", "model": "", "effort": "low"})
    writing_records.bank(tmp_path, {"record": "writing-turn", "id": "WT-source",
        "session_id": "WS-source", "project": "p", "mode": "work",
        "selection": {"files": ["main.tex"]}})
    read = writing_tools.execute(tmp_path, "p", "work", "source", {}, turn_id="WT-source")
    assert read["sources"][0]["file"].endswith("main.tex")
    assert read["sources"][0]["expected_source_digest"].startswith("sha256:")


def test_writer_captures_before_write_baseline_before_refresh(tmp_path, monkeypatch):
    _project(tmp_path)
    from laplace.work import project_work
    captured = {"baselines": {"READ-fixture": "old"}}
    calls = []
    monkeypatch.setattr(project_work, "style", lambda *args: {"id": "preview", "status": "READY"})
    monkeypatch.setattr(turn_reads, 'capture_turn_read_baselines',
                        lambda *args: calls.append(("capture", args)) or captured)
    monkeypatch.setattr(turn_reads, 'refresh_turn_read_baselines',
                        lambda *args, **kwargs: calls.append(("refresh", args)) or {"refreshed": 1})

    result = writing_tools.execute(tmp_path, "p", "work", "style", {}, turn_id="WT-fixture")

    assert [name for name, _args in calls] == ["capture", "refresh"]
    assert calls[1][1][-1] is captured
    assert result["action_receipt"]["refreshed_read_baselines"] == 1


def test_writer_dispatches_section_change_to_the_source_owner(tmp_path, monkeypatch):
    _project(tmp_path)
    from laplace.manuscript import manuscript_structure
    payload = {"operation": "delete", "source_file": "main.tex", "line_start": 3,
               "expected_source_digest": "source", "expected_plan_revision": "plan"}
    monkeypatch.setattr(manuscript_structure, "change",
                        lambda project, received, root: {"ok": True, "undo": {"operation": "restore"}})

    result = writing_tools.execute(tmp_path, "p", "work", "section_change", payload)

    assert result == {"ok": True, "undo": {"operation": "restore"}}


def test_writer_dispatches_guarded_section_create_and_help_discovers_it(tmp_path):
    manuscript = _project(tmp_path)
    path = manuscript / "main.tex"; before = path.read_text(encoding="utf-8")
    created = writing_tools.execute(tmp_path, "p", "work", "section_change", {
        "operation": "create", "source_file": "main.tex", "after_line": 3, "after_before": "Text.",
        "expected_source_digest": hashlib.sha256(before.encode()).hexdigest(),
        "title": "Inserted", "kind": "section", "section_id": "inserted"})
    assert created["receipt"]["section_id"] == "inserted" and "\\section{Inserted}" in path.read_text()
    contract = writing_tools.execute(tmp_path, "p", "work", "help", {"operation": "section_change"})["action"]
    assert "create" in _served_input(tmp_path, contract)["properties"]["operation"]["enum"]


def test_orientation_delta_carries_changed_voice_protocol_and_source_only():
    previous = {"selected_source": {"root": "main.tex", "edition": "old", "revision": "1"},
                "writing_style": {"revision": "voice-1", "selected_profile": "old"},
                "project_protocol": {"revision": "guide-1"}, "workspace": {"surface": "manuscript"}}
    current = {"selected_source": {"root": "main.tex", "edition": "new", "revision": "2"},
               "writing_style": {"revision": "voice-2", "selected_profile": "new", "content": "New voice"},
               "project_protocol": {"revision": "guide-2", "documents": [{"content": "New guide"}]},
               "workspace": {"surface": "research"}}

    delta = writing_operating.orientation_delta(previous, current)

    assert delta["changed"] is True
    assert delta["guidance"]["writing_style"]["content"] == "New voice"
    assert delta["guidance"]["project_protocol"]["documents"][0]["content"] == "New guide"


def test_orientation_delta_delivers_changed_shared_rules_once():
    previous = {"shared_rules_revision": "rules-1", "tool_contract_digest": "tools",
                "selected_source": {}, "writing_style": {},
                "project_protocol": {"revision": "guide"}, "workspace": {}}
    current = {**previous, "shared_rules_revision": "rules-2",
               "rules": ["Inspect support gaps first."],
               "capability_guidance": {"discover": "Use help."}}

    changed = writing_operating.orientation_delta(previous, current)
    unchanged = writing_operating.orientation_delta(current, current)

    assert changed == {"changed": True, "guidance": {
        "shared_rules_revision": "rules-2", "rules": ["Inspect support gaps first."]}}
    assert unchanged == {"changed": False, "guidance": {}}


def test_project_tool_is_compact_and_author_history_keeps_full_rows_on_demand(tmp_path):
    _project(tmp_path)
    authoring.save("p", {"argument": "A compact argument."}, repo_root=tmp_path)
    authoring.build_context("p", {"files": ["main.tex"]}, repo_root=tmp_path)
    correction = authoring.bank_correction("p", {"text": "Keep this qualification.", "kind": "note",
        "scope": "passage", "anchor": {"file": "main.tex", "line_start": 3, "line_end": 3}}, repo_root=tmp_path)

    project = writing_tools.execute(tmp_path, "p", "work", "project", {})
    history = writing_tools.execute(tmp_path, "p", "work", "author_history", {"file": "main.tex"})
    exact = writing_tools.execute(tmp_path, "p", "work", "author_history", {"id": correction["correction"]["id"]})

    assert "contexts" not in project["framing"] and "argument_text" not in project["framing"]
    assert "corrections" not in project["framing"] and "project_protocol" not in project
    assert history["items"][0]["text"] == "Keep this qualification."
    assert history["revision"] == exact["revision"] == correction["revision"]
    resolved = writing_tools.execute(tmp_path, "p", "work", "note_status", {
        "id": correction["correction"]["id"], "status": "resolved",
        "base_revision": exact["revision"], "note": "Addressed."})
    assert resolved["status"] == "resolved"
    help_value = writing_tools.execute(tmp_path, "p", "work", "help", {"operation": "note_status"})
    assert help_value["action"]["does"].startswith("Resolve, dismiss, or reopen")
    assert help_value["action"]["input"]["properties"]["status"]["enum"] == ["open", "resolved", "dismissed"]
    assert help_value["action"]["verb"] in ("change", "delete")
    assert exact["item"]["id"] == correction["correction"]["id"]


def test_author_changes_writer_read_uses_the_read_only_fragment_projection(tmp_path, monkeypatch):
    from laplace.manuscript import manuscript_fragments
    _project(tmp_path)
    seen = {}
    monkeypatch.setattr(manuscript_fragments, "change_preview", lambda project, payload, root: (
        seen.update(project=project, payload=payload, root=root) or
        {"mode": "baseline", "hunks": [{"anchor": {"file": "main.tex"}}]}))

    value = writing_tools.execute(tmp_path, "p", "work", "author_changes", {"file": "main.tex"})
    help_value = writing_tools.execute(tmp_path, "p", "work", "help", {"operation": "author_changes"})

    assert value["hunks"][0]["anchor"]["file"] == "main.tex"
    assert seen == {"project": "p", "payload": {"project": "p", "file": "main.tex"}, "root": tmp_path}
    assert help_value["action"]["effects"] == []
    # "file mode is aggregate baseline history" was the second clause of a summary;
    # it is now a rule attached to the `file` field, which is how a caller finds it.
    said = [rule["says"] for rule in help_value["action"]["rules"]]
    assert any("aggregate baseline history" in line for line in said), said


def test_prompt_summarizes_applied_edits_but_keeps_current_author_note():
    state = {"framing": {"purpose": "", "audience": "", "question": ""}, "argument": ""}
    prompt = authoring._prompt(state, [], [], [
        {"id": "EDIT-1", "applied": True, "kind": "author-edit", "scope": "passage", "by": "author",
         "text": "old", "before": "HISTORICAL BEFORE", "after": "HISTORICAL AFTER", "hunks": [{"x": "old"}]},
        {"id": "NOTE-1", "applied": False, "kind": "note", "scope": "passage", "by": "author",
         "text": "Keep the limitation."},
    ], [], [], include_orientation=False)

    assert "Keep the limitation." in prompt and "EDIT-1" in prompt
    assert "HISTORICAL BEFORE" not in prompt and "HISTORICAL AFTER" not in prompt


def test_structural_action_summary_keeps_only_durable_undo_handle():
    for operation, kind in (("block_change", "block"), ("section_change", "section")):
        result = {"undo_ref": {"kind": kind, "id": "receipt-1", "project": "p", "edits": [{"before": "private source"}]},
                  "undo": {"edits": [{"before": "private source"}]}}
        summary = writing_tools._action_summary("p", operation, {}, result)
        assert summary["undo_ref"] == {"kind": kind, "id": "receipt-1", "project": "p"}
        assert "private source" not in json.dumps(summary)
    assert "undo_ref" not in writing_tools._action_summary("p", "block_change", {}, {
        "undo_ref": {"kind": "block", "id": "receipt-1", "project": "another"}})
