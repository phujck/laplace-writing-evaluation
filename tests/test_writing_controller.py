"""Adversarial regressions for the live writing controller.

Every source, journal and project in this module lives below ``tmp_path``.  Provider
processes are never launched; the manuscript rewrite door is represented by a small
byte-guarded fixture with the same success/pending/error contract.
"""
from __future__ import annotations

import io
import hashlib
import json
import os
from pathlib import Path
import threading

import pytest

from laplace.web import authoring as controller
from laplace.writing import session_reads
from laplace.writing import records as writing_records
from laplace.manuscript import source_application
from laplace.writing import turn_jobs
from laplace.writing import turn_control
from laplace.writing import turn_context
from laplace.writing import turn_admission
from laplace.writing import turn_reads
from laplace.writing import mutation_attribution
from laplace.writing import provider_updates
from laplace.writing.records import _fold as records_fold
from laplace.representation import writing_bodies
from laplace.writing import operations
from laplace.writing import provider as writing_provider
from laplace.writing import mutation_attribution, turn_reads
from laplace.manuscript import manuscript_source, review_surface
from laplace.projects import library as writing_projects
from laplace.native import tools as writing_tools
from laplace.writing import reads as read_contract
from laplace.web import scanner
from laplace.pipeline import authoring
from laplace.core import checkout


@pytest.fixture(autouse=True)
def _clear_controller_process_state():
    records_fold._CACHE.clear()
    turn_jobs._JOBS.clear()
    yield
    records_fold._CACHE.clear()
    turn_jobs._JOBS.clear()


def _import_project(root: Path, name: str = "fixture", *, editable: bool = True,
                    files: dict[str, str] | None = None) -> tuple[Path, dict]:
    (root / "contract").mkdir(parents=True, exist_ok=True)
    source = root / "sources" / name
    source.mkdir(parents=True)
    supplied = files or {
        "main.tex": "\\documentclass{article}\n\\begin{document}\nOriginal prose.\n\\end{document}\n"
    }
    for rel, text in supplied.items():
        target = source / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    status, result = writing_projects.import_source(
        {"name": name, "title": name.title(), "root": f"sources/{name}/main.tex",
         "editable": editable}, root)
    assert status == 201, result
    return source, manuscript_source.resolve(name, repo_root=root)


def _seed_revision(root: Path, project: str, edits: list[dict], *, selection=None,
                   context: dict | None = None, suffix: str = "x") -> str:
    (root / "contract").mkdir(parents=True, exist_ok=True)
    source = manuscript_source.resolve(project, repo_root=root)
    if context is None:
        context=authoring.build_context(project,selection,repo_root=root)
    # Saved-candidate fixtures carry the same exact source anchors produced by
    # real preflight. Missing input basis is tested explicitly with context={}.
    from laplace.manuscript import proposal_preflight
    manuscript=root/source['manuscript_dir']
    edits=list(edits)
    for edit in edits:
        target=proposal_preflight._resolve(root,manuscript,str(edit.get('file') or ''))
        if target and target.is_file() and not edit.get('source_anchor'):
            raw=target.read_text();lo=edit.get('line_start');hi=edit.get('line_end')
            if isinstance(lo,int) and isinstance(hi,int) and '\n'.join(raw.split('\n')[lo-1:hi])==edit.get('before'):
                edit['source_anchor']=proposal_preflight.source_anchor(raw,lo,hi)
    session_id, turn_id = f"WS-{suffix}", f"WT-{suffix}"
    writing_records.bank(root, {"record": "writing-session", "id": session_id,
                            "project": project, "provider": "codex", "model": "m",
                            "effort": "medium"})
    writing_records.bank(root, {"record": "writing-turn", "id": turn_id,
                            "session_id": session_id, "project": project,
                            "request_id": f"request-{suffix}", "text": "revise",
                            "mode": "revise", "selection": selection,
                            "context_id": context.get("context_id"),
                            "dependencies": context.get("dependencies"),
                            "document": context.get("document", source)})
    writing_records.bank(root, {"record": "writing-reply", "id": f"WR-{suffix}",
                            "turn_id": turn_id, "session_id": session_id,
                            "project": project, "status": "completed",
                            "proposal": {"answer": "proposal", "edits": edits}})
    return turn_id


def _apply_fixture(root,payload):
    turn=session_reads._records(root)['turns'][payload['turn_id']]
    proposal=(turn.get('reply') or {}).get('proposal') or turn.get('pending_proposal') or {}
    return source_application.apply_proposal(root,{**payload,'proposal_version':payload.get('proposal_version') or __import__('laplace.manuscript.manuscript_proposals',fromlist=['proposal_version']).proposal_version(turn)[0]})


def _seal_new_fixture_candidate(root,turn_id):
    turn=session_reads._records(root)['turns'][turn_id]
    proposal=(turn.get('reply') or {}).get('proposal') or turn['pending_proposal']
    writing_records.bank(root,{'record':'writing-reply','id':'WR-reseal-'+turn_id,'turn_id':turn_id,
        'project':turn['project'],'status':'completed','proposal':{**proposal,'answer':proposal.get('answer','')+' after exact reads'}})


def test_steering_delivers_current_passage_context_and_replaces_old_attention(tmp_path):
    _import_project(tmp_path,files={'main.tex':'\\documentclass{article}\n\\begin{document}\nOld focus.\n\nNew focus.\n\\end{document}\n'})
    turn=_seed_revision(tmp_path,'fixture',[],selection={'files':['main.tex'],'line_start':3,'line_end':3})
    received=[]
    class Provider:
        def control_capabilities(self):return {'can_steer':True,'can_interrupt':True}
        def steer(self,text):received.append(text);return {'ok':True}
    turn_jobs._JOBS[turn]={'done':False,'provider':Provider()}
    response=turn_control.steer_turn(tmp_path,{'turn_id':turn,'text':'Explain this new passage.',
        'selection':{'files':['main.tex'],'line_start':5,'line_end':5},
        'workspace_context':{'surface':'manuscript'}})
    assert response['ok'] and 'New focus.' in received[0]
    assert 'Explain this new passage.' in received[0]
    current=session_reads._records(tmp_path)['turns'][turn]
    assert current['selection']['line_start']==5
    assert current['workspace_context']['node_id'] is None
    assert current['steering'][-1]['text']=='Explain this new passage.'


def test_shared_group_workspace_context_keeps_exact_members_without_stale_scalar_focus(tmp_path):
    manuscript,_=_import_project(tmp_path)
    from laplace.research import corpus_ingest
    for ident,kind,text in [('def:member-a','definition','Member A'),
                            ('res:member-b','result','Member B')]:
        assert corpus_ingest.rewire_add(tmp_path,'fixture',{'kind':'add-node','node':ident,
            'node_kind':kind,'essence':text,'parent':'paper://'}).get('ok')
    turn=_seed_revision(tmp_path,'fixture',[],selection={'files':['main.tex'],'line_start':3,'line_end':3},suffix='group')
    received=[]
    class Provider:
        def control_capabilities(self):return {'can_steer':True,'can_interrupt':True}
        def steer(self,text):received.append(text);return {'ok':True}
    turn_jobs._JOBS[turn]={'done':False,'provider':Provider()}
    group={'surface':'structure','node_ids':['def:member-a','res:member-b'],'label':'Shared basis'}

    first=turn_control.steer_turn(tmp_path,{'turn_id':turn,'text':'Explain this group.',
        'workspace_context':group})
    # A source refresh/reselection sends the same group and must not collapse it
    # back to an earlier scalar node focus.
    second=turn_control.steer_turn(tmp_path,{'turn_id':turn,'text':'Continue after refresh.',
        'selection':{'files':['main.tex'],'line_start':3,'line_end':3},
        'workspace_context':group})

    assert first['ok'] and second['ok']
    assert all('"node_ids": ["def:member-a", "res:member-b"]' in text for text in received)
    assert 'concept_history' in received[0]
    assert all('Shared basis' in text for text in received)
    current=session_reads._records(tmp_path)['turns'][turn]
    assert current['workspace_context']['node_id'] is None
    assert current['workspace_context']['node_ids']==['def:member-a','res:member-b']
    assert current['selection']['node_ids']==['def:member-a','res:member-b']


def test_review_workspace_context_validates_turn_applications_and_returns_lazy_history_reads(tmp_path):
    _import_project(tmp_path);turn=_seed_revision(tmp_path,'fixture',[],suffix='review-context')
    application={"record":"writing-application","id":"WA-review-context","turn_id":turn,
        "project":"fixture","complete":True,"edits":[{"file":"main.tex","line_start":3,
        "line_end":3,"before":"Original prose.","after":"Accepted prose."}]}
    writing_records.bank(tmp_path,application);before=(tmp_path/'contract/talk.jsonl').stat().st_size
    value=turn_context._workspace_context(tmp_path,'fixture',{"surface":"review",
        "label":"Accepted comparison","review":{"turn_id":turn,
        "application_ids":["WA-review-context"]}})
    assert value['review']['application_ids']==['WA-review-context']
    assert value['review']['files']==['main.tex'] and value['review']['files_omitted']==0
    assert value['review']['history_reads']==[
        {'operation':'author_history','payload':{'view':'record','id':'activity:journal:'+turn}},
        {'operation':'author_history','payload':{'view':'record','id':'activity:journal:WA-review-context'}}]
    assert (tmp_path/'contract/talk.jsonl').stat().st_size==before
    turn_only=turn_context._workspace_context(tmp_path,'fixture',{"surface":"review",
        "review":{"turn_id":turn,"application_ids":[]}})
    assert turn_only['review']['application_ids']==[] and len(turn_only['review']['history_reads'])==1
    with pytest.raises(ValueError,match='unavailable or incomplete'):
        turn_context._workspace_context(tmp_path,'fixture',{"surface":"review",
            "review":{"turn_id":turn,"application_ids":["WA-missing"]}})
    with pytest.raises(ValueError,match='at most 50'):
        turn_context._workspace_context(tmp_path,'fixture',{"surface":"review",
            "review":{"turn_id":turn,"application_ids":[f'WA-{i}' for i in range(51)]}})


def _rewrite_door(manuscript: Path, *, refuse: str | None = None, calls=None):
    calls = calls if calls is not None else []

    def adjudicate(md: Path, project: str, payload: dict, *, source_changes=None, repo_root=None) -> dict:
        assert md == manuscript
        path = (md / payload["file"]).resolve()
        raw = path.read_text(encoding="utf-8")
        lines = raw.split("\n")
        lo, hi = payload["line_start"], payload["line_end"]
        current = "\n".join(lines[lo - 1:hi]) if hi <= len(lines) else None
        calls.append({"file": payload["file"], "line_start": lo, "line_end": hi,
                      "before": payload["before"], "after": payload["after"],
                      "current": current})
        if refuse and payload["file"] == refuse and payload["after"] != raw:
            return {"error": "planted second-file refusal", "reason": "planted"}
        if current != payload["before"]:
            return {"ok": True, "pending": True, "applied": None}
        lines[lo - 1:hi] = payload["after"].split("\n")
        updated = "\n".join(lines)
        path.write_text(updated, encoding="utf-8")
        if source_changes is not None:
            source_changes.append((path, raw, updated))
        return {"ok": True, "pending": False,
                "applied": {"file": payload["file"], "lines": [lo, hi]}}

    return adjudicate


def _bind_rewrite_fixture(monkeypatch, manuscript: Path, **kwargs):
    monkeypatch.setattr(review_surface, "manuscript_dir", lambda project: manuscript)
    calls: list[dict] = []
    monkeypatch.setattr(review_surface, "adjudicate",
                        _rewrite_door(manuscript, calls=calls, **kwargs))
    return calls


def _application_rows(root: Path) -> list[dict]:
    path = root / "contract" / "talk.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if json.loads(line).get("record") == "writing-application"]


def test_one_proposal_applies_once_and_reuses_complete_receipt(tmp_path, monkeypatch):
    manuscript, _ = _import_project(tmp_path)
    turn = _seed_revision(tmp_path, "fixture", [{
        "file": "main.tex", "line_start": 3, "line_end": 3,
        "before": "Original prose.", "after": "Revised prose.", "reason": "clarity"}])
    calls = _bind_rewrite_fixture(monkeypatch, manuscript)

    first = _apply_fixture(tmp_path, {"turn_id": turn})
    second = _apply_fixture(tmp_path, {"turn_id": turn})

    assert first["complete"] is True
    assert second["reused"] is True and second["id"] == first["id"]
    assert manuscript.joinpath("main.tex").read_text(encoding="utf-8").splitlines()[2] == "Revised prose."
    assert len(calls) == 1
    assert len(_application_rows(tmp_path)) == 1


def test_application_receipt_is_existing_owner_projection_and_record_is_lazy(tmp_path, monkeypatch):
    lines=["\\documentclass{article}","\\begin{document}","Opening.",
           "Line 4: "+("x"*180),*[f"Line {index}: "+("x"*180) for index in range(5,101)],
           "\\end{document}"]
    manuscript,_=_import_project(tmp_path,files={"main.tex":"\n".join(lines)+"\n"})
    before=lines[3];after=before+" twenty-seven-added-chars!!"
    turn=_seed_revision(tmp_path,"fixture",[{"file":"main.tex","line_start":4,"line_end":4,
        "before":before,"after":after,"reason":"small accepted edit"}],suffix="hunk-storage")
    monkeypatch.setattr(review_surface,"_repo_root",lambda:tmp_path)

    applied=_apply_fixture(tmp_path,{"turn_id":turn})

    assert applied["complete"] is True and len(applied["receipts"])==1
    receipt=applied["receipts"][0]
    assert "record" not in receipt
    assert receipt["file"]=="main.tex" and receipt["lines"]==[4,4]
    assert "file_versions" not in applied and "undo_contexts" not in applied
    feedback=manuscript/"feedback"/"feedback.jsonl"
    row=json.loads(feedback.read_text().splitlines()[-1])
    assert row["anchor"]["lines"]==[4,4]
    assert row["anchor"]["before"]==row["anchor"]["quote"]==before
    assert row["anchor"]["after"]==after
    assert len(json.dumps(row))<5000
    exact=session_reads.session_turn_detail(tmp_path,"fixture",turn,"application",item_id=applied["id"])
    assert exact["application"]["receipts"][0]["record"]==row
    assert exact["application"]["edits"][0]["undo_basis"]["record_id"]==row["id"]


def test_disjoint_and_adjacent_edits_keep_hunk_receipt_correspondence(tmp_path,monkeypatch):
    manuscript,_=_import_project(tmp_path,files={"main.tex":"\\documentclass{article}\n\\begin{document}\nA\nB\nC\nD\n\\end{document}\n"})
    edits=[{"file":"main.tex","line_start":3,"line_end":3,"before":"A","after":"A2","reason":"one"},
           {"file":"main.tex","line_start":4,"line_end":4,"before":"B","after":"B2","reason":"adjacent"},
           {"file":"main.tex","line_start":6,"line_end":6,"before":"D","after":"D2","reason":"disjoint"}]
    turn=_seed_revision(tmp_path,"fixture",edits,suffix="hunk-many")
    calls=_bind_rewrite_fixture(monkeypatch,manuscript)
    applied=_apply_fixture(tmp_path,{"turn_id":turn})
    assert applied["complete"] is True
    assert [(row["line_start"],row["line_end"]) for row in calls]==[(3,6)]
    assert len(applied["receipts"])==1
    assert applied["receipts"][0]["file"]=="main.tex"
    assert applied["receipts"][0]["lines"]==[3,6]
    assert (manuscript/"main.tex").read_text()=="\\documentclass{article}\n\\begin{document}\nA2\nB2\nC\nD2\n\\end{document}\n"


def test_enclosing_span_preserves_multiline_and_deletion_final_bytes(tmp_path,monkeypatch):
    manuscript,_=_import_project(tmp_path,files={"main.tex":"\\documentclass{article}\n\\begin{document}\nA\nB\nC\nD\n\\end{document}\n"})
    edits=[{"file":"main.tex","line_start":3,"line_end":3,"before":"A","after":"A1\nA2","reason":"split"},
           {"file":"main.tex","line_start":4,"line_end":5,"before":"B\nC","after":"B","reason":"delete"}]
    turn=_seed_revision(tmp_path,"fixture",edits,suffix="hunk-line-count")
    calls=_bind_rewrite_fixture(monkeypatch,manuscript)
    applied=_apply_fixture(tmp_path,{"turn_id":turn})
    assert applied["complete"] is True
    assert [(row["line_start"],row["line_end"],row["before"],row["after"])
            for row in calls]==[(3,5,"A\nB\nC","A1\nA2\nB")]
    assert (manuscript/"main.tex").read_text()=="\\documentclass{article}\n\\begin{document}\nA1\nA2\nB\nD\n\\end{document}\n"


def test_successful_multifile_application_has_one_corresponding_receipt_per_edit(tmp_path,monkeypatch):
    manuscript,_=_import_project(tmp_path,files={"main.tex":"\\documentclass{article}\n\\begin{document}\n\\input{a}\n\\input{b}\n\\end{document}\n",
        "a.tex":"A one.\n","b.tex":"B one.\n"})
    edits=[{"file":"a.tex","line_start":1,"line_end":1,"before":"A one.","after":"A two.","reason":"a"},
           {"file":"b.tex","line_start":1,"line_end":1,"before":"B one.","after":"B two.","reason":"b"}]
    turn=_seed_revision(tmp_path,"fixture",edits,suffix="hunk-files")
    calls=_bind_rewrite_fixture(monkeypatch,manuscript)
    applied=_apply_fixture(tmp_path,{"turn_id":turn})
    assert applied["complete"] is True and len(calls)==len(applied["receipts"])==2
    assert [row["file"] for row in applied["receipts"]]==["a.tex","b.tex"]
    assert (manuscript/"a.tex").read_text()=="A two.\n"
    assert (manuscript/"b.tex").read_text()=="B two.\n"


def test_modern_unmatched_receipt_never_falls_back_by_position():
    edit={"file":"a.tex","line_start":1,"line_end":1}
    modern=[{"row_id":"record-b","file":"b.tex","lines":[1,1]}]
    legacy=[{"record":{"id":"record-old"}}]
    assert session_reads._application_receipt_for_edit(modern,edit,0)=={}
    ambiguous=[{"row_id":"one","file":"a.tex","lines":[1,2]},
               {"row_id":"two","file":"a.tex","lines":[1,3]}]
    assert session_reads._application_receipt_for_edit(ambiguous,edit,0)=={}
    assert session_reads._application_receipt_for_edit(legacy,edit,0)==legacy[0]


def test_current_turn_apply_revision_uses_the_same_source_door_and_is_idempotent(tmp_path, monkeypatch):
    manuscript, source = _import_project(tmp_path)
    selection = {"files": ["main.tex"], "line_start": 3, "line_end": 3}
    context = authoring.build_context("fixture", selection, repo_root=tmp_path)
    turn_id = "WT-current-tool"
    writing_records.bank(tmp_path, {"record": "writing-session", "id": "WS-current-tool",
                                "project": "fixture", "provider": "codex", "model": "m", "effort": "medium"})
    writing_records.bank(tmp_path, {"record": "writing-turn", "id": turn_id,
                                "session_id": "WS-current-tool", "project": "fixture",
                                "request_id": "current-tool", "text": "Make the requested edit.",
                                "mode": "work", "selection": selection,
                                "context_id": context["context_id"], "dependencies": context["dependencies"],
                                "document": context["document"]})
    # This is the normal provider sequence: inspect project material, deposit a scoped result,
    # then explicitly ask the current-turn apply tool to rewrite the exact source.
    writing_tools.execute(tmp_path, "fixture", "work", "source", {"files": ["main.tex"]}, turn_id=turn_id)
    writing_tools.execute(tmp_path, "fixture", "work", "store_artifact", {
        "path": "research/current-turn.md", "before": None, "content": "checked\n", "reason": "fixture"},
        turn_id=turn_id)
    turn_jobs._JOBS[turn_id] = {"done": False}
    calls = _bind_rewrite_fixture(monkeypatch, manuscript)
    payload = {"answer": "Applied requested correction.", "edits": [{
        "file": "main.tex", "line_start": 3, "line_end": 3,
        "before": "Original prose.", "after": "Current-turn prose.", "reason": "requested correction"}]}

    first = source_application.apply_revision(tmp_path, "fixture", turn_id, payload)
    second_payload = {"answer": "Applied the next requested correction.", "edits": [{
        "file": "main.tex", "line_start": 3, "line_end": 3,
        "before": "Current-turn prose.", "after": "Second atomic edit.", "reason": "second requested correction"}]}
    second = source_application.apply_revision(tmp_path, "fixture", turn_id, second_payload)
    retry = source_application.apply_revision(tmp_path, "fixture", turn_id, second_payload)

    assert first["complete"] is True and first["origin"] == "current-turn-tool"
    assert second["complete"] is True and second["id"] != first["id"]
    assert retry["reused"] is True and retry["id"] == second["id"]
    assert manuscript.joinpath("main.tex").read_text(encoding="utf-8").splitlines()[2] == "Second atomic edit."
    assert len(calls) == 2
    assert (tmp_path / source["storage_dir"] / "research" / "current-turn.md").read_text() == "checked\n"
    assert len(_application_rows(tmp_path)) == 2
    for row in _application_rows(tmp_path):
        assert row["actor"]["label"] == "eigen:session"
        assert row["actor"]["kind"] == "agent"
        assert row["owned_changes"]["schema_version"] == "laplace.owner-mutation/1"
        assert row["owned_changes"]["files"]


def test_context_route_defaults_to_fresh_source_and_audits_only_an_explicit_receipt(tmp_path, monkeypatch):
    captured = []
    monkeypatch.setattr(checkout, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(authoring, "inspect", lambda project, *, repo_root, context_id: captured.append(
        (project, repo_root, context_id)) or {"project": project, "context_id": context_id})
    status, _content, _body = controller.handle("/authoring/context", {"project": ["fixture"]}, "GET", b"")
    assert status == 200 and captured[-1] == ("fixture", tmp_path, "")
    status, _content, _body = controller.handle("/authoring/context", {"project": ["fixture"], "context_id": ["CTX-one"]}, "GET", b"")
    assert status == 200 and captured[-1] == ("fixture", tmp_path, "CTX-one")


def test_sessions_state_view_skips_full_authoring_load(tmp_path, monkeypatch):
    monkeypatch.setattr(checkout, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(session_reads, '_records', lambda _root: {"sessions": {
        "WS-one": {"id": "WS-one", "project": "fixture", "provider": "codex"},
        "WS-other": {"id": "WS-other", "project": "other", "provider": "codex"}}, "turns": {}})
    monkeypatch.setattr(authoring, "load", lambda *args, **kwargs: pytest.fail("full authoring state was loaded"))
    status, _content, body = controller.handle("/authoring/state", {"project": ["fixture"], "view": ["sessions"]}, "GET", b"")
    value = json.loads(body)
    assert status == 200 and value == {"project": "fixture", "sessions": [value["sessions"][0]], "session_count": 1}


def test_exact_second_chapter_source_apply_is_not_blocked_by_unrelated_mirror_state(tmp_path, monkeypatch):
    manuscript, _source = _import_project(tmp_path, files={
        "main.tex": "\\documentclass{article}\n\\begin{document}\n\\input{chapter2}\n\\end{document}\n",
        "chapter2.tex": "Chapter two opening.\n"})
    turn = _seed_revision(tmp_path, "fixture", [{"file": "chapter2.tex", "line_start": 1, "line_end": 1,
        "before": "Chapter two opening.", "after": "Restored chapter two opening.", "reason": "fixture"}],
        selection={"files": ["chapter2.tex"]}, suffix="chapter-two")
    _bind_rewrite_fixture(monkeypatch, manuscript)
    applied = _apply_fixture(tmp_path, {"turn_id": turn})
    assert applied["complete"] is True
    assert (manuscript / "chapter2.tex").read_text(encoding="utf-8") == "Restored chapter two opening.\n"


def test_literature_import_action_persists_bounded_owner_evidence(tmp_path):
    _manuscript, _source = _import_project(tmp_path)
    writing_records.bank(tmp_path, {"record": "writing-session", "id": "WS-literature-evidence",
                                "project": "fixture", "provider": "codex", "model": "m", "effort": "medium"})
    writing_records.bank(tmp_path, {"record": "writing-turn", "id": "WT-literature-evidence", "session_id": "WS-literature-evidence",
                                "project": "fixture", "text": "Import this reference.", "mode": "work"})
    writing_tools.execute(tmp_path, "fixture", "work", "literature_import", {
        "metadata": {"title": "Controlled source", "creators": ["Fixture Author"], "year": "2026", "item_type": "unpublished"},
        "provenance": {"description": "Fixture local metadata"}}, turn_id="WT-literature-evidence")
    action = next(json.loads(line) for line in (tmp_path / "contract" / "talk.jsonl").read_text().splitlines()
                  if json.loads(line).get("record") == "writing-tool-action")
    evidence = action["outcome"]["owner_evidence"]
    assert evidence["schema_version"] == "laplace.owner-evidence/1"
    assert evidence["files"][0]["path"].endswith("references.json")
    assert evidence["objects"][0]["owner"] == "references"


def test_provider_final_reply_marks_its_already_applied_revision_applied(tmp_path, monkeypatch):
    manuscript, _ = _import_project(tmp_path)
    _bind_rewrite_fixture(monkeypatch, manuscript)

    class Provider:
        def __init__(self, cwd, provider, model, effort, native_id, event, mode,
                         project=None, logical_turn_id=None, **kwargs):
            self.cwd, self.project, self.mode, self.logical_turn_id = cwd, project, mode, logical_turn_id

        def run(self, prompt):
            proposal = {"edits": [{
                "file": "main.tex", "line_start": 3, "line_end": 3,
                "before": "Original prose.", "after": "Saved by provider.", "reason": "requested"}]}
            writing_tools.execute(self.cwd, self.project, self.mode, "apply_revision", proposal,
                                  turn_id=self.logical_turn_id)
            return {"status": "completed", "text": "Saved the requested edit.",
                    "turn_id": "native-final"}

    monkeypatch.setattr(writing_provider, "WritingTurn", Provider)
    started = turn_admission.start_turn(tmp_path, {"project": "fixture", "provider": "codex", "mode": "work",
                                               "selection": {"files": ["main.tex"]}, "text": "Save this."})
    job = turn_jobs._JOBS[started["turn_id"]]
    with job["condition"]:
        assert job["condition"].wait_for(lambda: job["done"], timeout=5)
    turn = next(row for row in session_reads.session_state(tmp_path, started["session_id"])["turns"]
                if row["id"] == started["turn_id"])

    # A narrative terminal summary carries the existing exact candidate; it
    # neither clones it nor invents a new preflight/APPLIED validation.
    assert turn['reply']['proposal'] is None
    assert 'proposal_validation' not in turn['reply']
    carrier = turn['reply']['proposal_carrier']
    application = turn['application']
    assert carrier['kind'] == 'terminal-application-summary' and carrier['complete']
    assert carrier['candidate_version'] == application['candidate_version']
    assert carrier['application_ids'] == [application['id']]
    assert set(carrier['covered_edit_ids']) == set(application['candidate_edit_ids'])
    assert carrier['remaining_edit_ids'] == []
    assert application['turn_id'] == started['turn_id'] and application['project'] == 'fixture'
    retained = session_reads._records(tmp_path)['turns'][started['turn_id']]
    assert retained['proposal_bases'][carrier['candidate_version']]['record_id'] == carrier['candidate_record_id']
    assert retained['proposal_versions'][carrier['candidate_version']]['edits'][0]['after'] == 'Saved by provider.'
    assert turn["application"]["complete"] is True
    assert turn["proposal_state"] == "applied"
    assert manuscript.joinpath("main.tex").read_text(encoding="utf-8").splitlines()[2] == "Saved by provider."


def test_own_action_refreshes_only_affected_read_baseline_and_later_change_refuses(tmp_path, monkeypatch):
    manuscript, _ = _import_project(tmp_path)
    selection = {"files": ["main.tex"], "line_start": 3, "line_end": 3}
    context = authoring.build_context("fixture", selection, repo_root=tmp_path)
    turn_id = _seed_revision(tmp_path, "fixture", [{
        "file": "main.tex", "line_start": 3, "line_end": 3,
        "before": "Original prose.", "after": "Updated prose.", "reason": "fixture"}],
        selection=selection, context=context, suffix="baseline")
    writing_records.bank(tmp_path, {"record": "writing-tool-read", "id": "READ-before",
                                "turn_id": turn_id, "project": "fixture", "operation": "research",
                                "payload": {"project":"fixture"}, "output_sha256": read_contract.output_digest({"state": "before-own-action"})})
    original_execute = operations._execute
    observed = {"state": "before-own-action"}
    def execute(root, project, mode, operation, payload, turn_id=None):
        if operation == "research":
            return dict(observed)
        return original_execute(root, project, mode, operation, payload, turn_id=turn_id)
    monkeypatch.setattr(operations, '_execute', execute)

    before = turn_reads.capture_turn_read_baselines(tmp_path, "fixture", turn_id, "research_record")
    observed["state"] = "after-own-action"
    refreshed = turn_reads.refresh_turn_read_baselines(tmp_path, "fixture", turn_id, "research_record", before)
    _bind_rewrite_fixture(monkeypatch, manuscript)
    assert refreshed["refreshed"] == 0 and refreshed["attribution"]["exact"] is False
    # A global Research catalogue read is exploratory. The scoped context and
    # proposal preflight own this paragraph; direct source/evidence reads retain
    # separate guards.
    applied = _apply_fixture(tmp_path, {"turn_id": turn_id})

    assert applied["complete"] is True
    # Another unscoped catalogue change likewise does not make a new paragraph
    # inherit the lifetime conversation.
    turn = _seed_revision(tmp_path, "fixture", [{
        "file": "main.tex", "line_start": 3, "line_end": 3,
        "before": "Updated prose.", "after": "External conflict.", "reason": "fixture"}],
        selection=selection, context=authoring.build_context("fixture", selection, repo_root=tmp_path), suffix="external")
    writing_records.bank(tmp_path, {"record": "writing-tool-read", "id": "READ-after",
                                "turn_id": turn, "project": "fixture", "operation": "research",
                                "payload": {}, "output_sha256": read_contract.output_digest(dict(observed))})
    observed["state"] = "external-change"
    assert _apply_fixture(tmp_path, {"turn_id": turn})["complete"] is True


def test_equivalent_read_aliases_bank_one_baseline_transition_and_reexpand(tmp_path, monkeypatch):
    writing_records.bank(tmp_path, {"record": "writing-session", "id": "WS-alias",
                                "project": "fixture", "provider": "codex",
                                "model": "fixture", "effort": "low"})
    writing_records.bank(tmp_path, {"record": "writing-turn", "id": "WT-alias",
                                "session_id": "WS-alias", "project": "fixture",
                                "mode": "work"})
    reads = []
    for index, payload in enumerate(({"node": "same"}, {"q": "same"})):
        row = {"record": "writing-tool-read", "id": f"READ-alias-{index}",
               "turn_id": "WT-alias", "project": "fixture", "operation": "concept",
               "payload": payload, "output_sha256": "before"}
        writing_records.bank(tmp_path, row)
        key = json.dumps(["concept", payload], sort_keys=True)
        reads.append((key, row))
    monkeypatch.setattr(mutation_attribution, "_affected_turn_reads",
                        lambda *args, **kwargs: ({"id": "WT-alias", "project": "fixture",
                                                  "mode": "work"}, reads))
    monkeypatch.setattr(mutation_attribution, "_owned_changes_exact", lambda *args, **kwargs: (True, "fixture"))
    monkeypatch.setattr(turn_reads, "_refresh_owned_context", lambda *args, **kwargs: False)
    monkeypatch.setattr(operations, '_execute', lambda *args, **kwargs: {"state": "after"})
    monkeypatch.setattr(read_contract, 'read_output_digest', lambda *args, **kwargs: "after")

    refreshed = turn_reads.refresh_turn_read_baselines(
        tmp_path, "fixture", "WT-alias", "concept_change",
        {"baselines": {key: "before" for key, _row in reads}})

    assert refreshed["refreshed"] == 2
    assert refreshed["baseline_records"] == 1
    journal_rows = [json.loads(line) for line in
                    (tmp_path / "contract" / "talk.jsonl").read_text().splitlines()]
    baselines = [row for row in journal_rows if row.get("record") == "writing-tool-read-baseline"]
    assert len(baselines) == 1
    assert baselines[0]["payload_aliases"] == [{
        "payload": {"q": "same"}, "supersedes_read": "READ-alias-1"}]
    indexed = session_reads._records(tmp_path)["turns"]["WT-alias"]["tool_reads"]
    assert len(indexed) == 2
    assert {row["output_sha256"] for row in indexed.values()} == {"after"}
    assert {json.dumps(row["payload"], sort_keys=True) for row in indexed.values()} == {
        json.dumps({"node": "same"}, sort_keys=True),
        json.dumps({"q": "same"}, sort_keys=True)}


def test_pre_write_external_read_change_cannot_be_rebased_as_the_writers_own_action(tmp_path, monkeypatch):
    manuscript, _ = _import_project(tmp_path)
    selection = {"files": ["main.tex"], "line_start": 3, "line_end": 3}
    context = authoring.build_context("fixture", selection, repo_root=tmp_path)
    turn_id = _seed_revision(tmp_path, "fixture", [{
        "file": "main.tex", "line_start": 3, "line_end": 3,
        "before": "Original prose.", "after": "Should not apply.", "reason": "fixture"}],
        selection=selection, context=context, suffix="prewrite-conflict")
    writing_records.bank(tmp_path, {"record": "writing-tool-read", "id": "READ-prewrite",
                                "turn_id": turn_id, "project": "fixture", "operation": "research",
                                "payload": {}, "output_sha256": read_contract.output_digest({"state": "read"})})
    original_execute = operations._execute
    observed = {"state": "external-before-write"}
    def execute(root, project, mode, operation, payload, turn_id=None):
        if operation == "research":
            return dict(observed)
        return original_execute(root, project, mode, operation, payload, turn_id=turn_id)
    monkeypatch.setattr(operations, '_execute', execute)

    before = turn_reads.capture_turn_read_baselines(tmp_path, "fixture", turn_id, "research_record")
    observed["state"] = "writer-result-after-mutation"
    refreshed = turn_reads.refresh_turn_read_baselines(tmp_path, "fixture", turn_id, "research_record", before)
    _bind_rewrite_fixture(monkeypatch, manuscript)

    assert before["baselines"] == {} and before["conflicts"] == 1
    assert refreshed["refreshed"] == 0
    assert _apply_fixture(tmp_path, {"turn_id": turn_id})["complete"] is True


def test_action_scoped_baselines_replay_target_dependencies_and_leave_unrelated_reads_unblessed(tmp_path):
    _import_project(tmp_path)
    turn=_seed_revision(tmp_path,'fixture',[],selection={},suffix='scoped-baselines')
    reads=[
        ('concept',{'node':'claim:target'}),('concept',{'node':'claim:other'}),
        ('logical_plan',{'node':'claim:target'}),('logical_plan',{'node':'claim:other'}),
        ('concept_tree',{'node':'claim:target'}),('concept_tree',{'node':'claim:other'}),
        ('literature_scope',{'node':'claim:target'}),('literature_scope',{'node':'portal:other'}),
        ('reference_text',{'key':'source:target'}),('reference_text',{'key':'source:other'}),
        ('read_artifact',{'path':'research/target.md'}),('read_artifact',{'path':'research/other.md'}),
        ('structure',{}),('research',{}),('source',{'files':['main.tex']}),
    ]
    for index,(operation,payload) in enumerate(reads):
        writing_records.bank(tmp_path,{'record':'writing-tool-read','id':f'READ-scoped-{index}',
            'turn_id':turn,'project':'fixture','operation':operation,'payload':payload,
            'output_sha256':f'digest-{index}'})

    _turn,literature=mutation_attribution._affected_turn_reads(tmp_path,'fixture',turn,'literature_bind',
        include_potential=True,action_payload={'claim_id':'claim:target','key':'source:target'})
    selected={(row['operation'],json.dumps(row['payload'],sort_keys=True)) for _key,row in literature}
    assert ('concept',json.dumps({'node':'claim:target'},sort_keys=True)) in selected
    assert ('logical_plan',json.dumps({'node':'claim:target'},sort_keys=True)) in selected
    assert ('concept_tree',json.dumps({'node':'claim:target'},sort_keys=True)) in selected
    assert ('literature_scope',json.dumps({'node':'claim:target'},sort_keys=True)) in selected
    assert ('reference_text',json.dumps({'key':'source:target'},sort_keys=True)) in selected
    assert all('claim:other' not in payload and 'source:other' not in payload for _op,payload in selected)
    assert {operation for operation,_payload in selected} >= {'structure','research','source'}

    _turn,artifact=mutation_attribution._affected_turn_reads(tmp_path,'fixture',turn,'store_artifact',
        include_potential=True,action_payload={'path':'research/target.md','scope':'project'})
    artifact_scopes={(row['operation'],json.dumps(row['payload'],sort_keys=True)) for _key,row in artifact}
    assert artifact_scopes=={
        ('read_artifact',json.dumps({'path':'research/target.md'},sort_keys=True)),
        ('research',json.dumps({},sort_keys=True)),
    }


def test_exact_owner_receipt_refuses_external_before_during_and_after_changes(tmp_path):
    target=tmp_path/'owner.json';target.write_text('before')
    digest=lambda value:'sha256:'+hashlib.sha256(value.encode()).hexdigest()
    captured={'mutation_files':{'owner.json':digest('before')}}
    target.write_text('after')
    receipt={'schema_version':'laplace.owner-mutation/1','files':[{
        'scope':'repository','path':'owner.json','before_sha256':digest('before'),
        'after_sha256':digest('after'),'observed_after_sha256':digest('after')}],
        'objects':[],'rewire_records':[],'views':['references']}

    assert mutation_attribution._owned_changes_exact(tmp_path,captured,receipt)[0] is True
    external_before={**receipt,'files':[{**receipt['files'][0],
        'before_sha256':digest('external-before')}]}
    assert mutation_attribution._owned_changes_exact(tmp_path,captured,external_before)[0] is False
    foreign_after={**receipt,'files':[{**receipt['files'][0],
        'after_sha256':digest('intended'),'observed_after_sha256':digest('foreign-during')}]}
    assert mutation_attribution._owned_changes_exact(tmp_path,captured,foreign_after)[0] is False
    target.write_text('external-after')
    assert mutation_attribution._owned_changes_exact(tmp_path,captured,receipt)[0] is False


def test_exact_owner_receipt_accepts_unique_file_created_inside_owner_lock(tmp_path):
    target=tmp_path/'new-run.json';target.write_text('complete')
    digest='sha256:'+hashlib.sha256(b'complete').hexdigest()
    receipt={'schema_version':'laplace.owner-mutation/1','files':[{
        'scope':'repository','path':'new-run.json','before_sha256':None,
        'after_sha256':digest,'observed_after_sha256':digest}],
        'objects':[],'rewire_records':[],'views':['research']}
    ok,reason=mutation_attribution._owned_changes_exact(tmp_path,{'mutation_files':{}},receipt)
    assert ok is True and 'exact owner receipts' in reason
    receipt['files'][0]['before_sha256']='sha256:unobserved-existing'
    assert mutation_attribution._owned_changes_exact(tmp_path,{'mutation_files':{}},receipt)[0] is False


def test_source_read_digest_ignores_historical_context_diagnostics_only():
    source={'project':'p','document':{'root':'main.tex','manuscript_dir':'m','edition':'working',
        'read_only':False,'status':'resolved'},'selection':['chapter.tex'],
        'requested_selection':{'files':['chapter.tex'],'line_start':2,'line_end':2},
        'sources':[{'file':'chapter.tex','line_start':2,'line_end':2,'text':'Exact line.','expected_source_digest':'sha256:a'}],
        'boundaries':[],'diagnostics':[],'stale':[]}
    with_old_context={**source,'stale':[{'context_id':'CTX-old','reasons':['structure-plan-conceptric-or-evidence-changed']}]}
    changed={**source,'sources':[{**source['sources'][0],'text':'Externally changed line.','expected_source_digest':'sha256:b'}]}

    assert read_contract.read_output_digest('source',source)==read_contract.read_output_digest('source',with_old_context)
    assert read_contract.read_output_digest('source',source)!=read_contract.read_output_digest('source',changed)


def test_discovery_volatility_is_not_scientific_evidence_but_exact_repository_source_is():
    available = {"items": [{"doi": "10.1/example", "title": "Result"}],
                 "local_candidates": [{"cand_id": "local:one"}],
                 "metadata_only": True, "provider": "crossref",
                 "public_state": "AVAILABLE", "query": "same query"}
    unavailable = {"items": [], "local_candidates": [], "metadata_only": True,
                   "provider": "crossref", "public_state": "UNAVAILABLE",
                   "public_error": "HTTP Error 429", "query": "same query"}
    other_query = {**unavailable, "query": "different query"}
    assert read_contract.read_output_digest("literature_discover", available) == \
           read_contract.read_output_digest("literature_discover", unavailable)
    assert read_contract.read_output_digest("literature_discover", available) != \
           read_contract.read_output_digest("literature_discover", other_query)

    listing_before = {"repository": "papers", "matches": [{"path": "a.tex"}],
                      "offset": 0, "query": "", "timed_out": False}
    listing_after = {**listing_before,
                     "matches": [{"path": "a.tex"}, {"path": "new-neighbour.tex"}],
                     "timed_out": True}
    assert read_contract.read_output_digest("repository", listing_before) == \
           read_contract.read_output_digest("repository", listing_after)

    read_before = {"repository": "papers",
                   "source": {"path": "/papers/a.tex", "bytes": 5, "sha256": "aaa"},
                   "content": "proof", "offset": 0, "truncated": False,
                   "authority": "wrapper text", "note": "first wrapper"}
    same_source = {**read_before, "authority": "reworded wrapper", "note": "second wrapper"}
    changed_source = {**read_before,
                      "source": {**read_before["source"], "bytes": 6, "sha256": "bbb"},
                      "content": "proof!"}
    assert read_contract.read_output_digest("repository", read_before) == \
           read_contract.read_output_digest("repository", same_source)
    assert read_contract.read_output_digest("repository", read_before) != \
           read_contract.read_output_digest("repository", changed_source)


def test_transient_literature_discovery_availability_does_not_deadlock_apply(
        tmp_path, monkeypatch):
    manuscript, _ = _import_project(tmp_path)
    turn = _seed_revision(tmp_path, "fixture", [{
        "file": "main.tex", "line_start": 3, "line_end": 3,
        "before": "Original prose.", "after": "Revision with imported sources.",
        "reason": "The cited source was imported and read separately."}], suffix="discover-volatile")
    available = {"items": [{"doi": "10.1/example"}], "metadata_only": True,
                 "provider": "crossref", "public_state": "AVAILABLE", "query": "q"}
    unavailable = {"items": [], "metadata_only": True, "provider": "crossref",
                   "public_state": "UNAVAILABLE", "public_error": "HTTP 429", "query": "q"}
    writing_records.bank(tmp_path, {"record": "writing-tool-read", "id": "READ-discovery",
        "turn_id": turn, "project": "fixture", "operation": "literature_discover",
        "payload": {"q": "q", "limit": 4},
        "output_sha256": read_contract.read_output_digest("literature_discover", available)})
    monkeypatch.setattr(operations, '_execute', lambda *args, **kwargs: unavailable)
    _bind_rewrite_fixture(monkeypatch, manuscript)

    assert _apply_fixture(tmp_path, {"turn_id": turn})["complete"] is True


def test_changed_exact_repository_source_still_refuses_apply(tmp_path, monkeypatch):
    manuscript, _ = _import_project(tmp_path)
    turn = _seed_revision(tmp_path, "fixture", [{
        "file": "main.tex", "line_start": 3, "line_end": 3,
        "before": "Original prose.", "after": "Must remain unapplied.",
        "reason": "The consulted source changed."}], suffix="repository-change")
    before = {"repository": "papers",
              "source": {"path": "/papers/source.tex", "bytes": 5, "sha256": "aaa"},
              "content": "proof", "offset": 0, "truncated": False}
    changed = {**before,
               "source": {**before["source"], "bytes": 6, "sha256": "bbb"},
               "content": "proof!"}
    writing_records.bank(tmp_path, {"record": "writing-tool-read", "id": "READ-repository",
        "turn_id": turn, "project": "fixture", "operation": "repository",
        "payload": {"action": "read", "repository": "papers", "path": "source.tex"},
        "output_sha256": read_contract.read_output_digest("repository", before)})
    _seal_new_fixture_candidate(tmp_path,turn)
    monkeypatch.setattr(operations, '_execute', lambda *args, **kwargs: changed)
    _bind_rewrite_fixture(monkeypatch, manuscript)

    with pytest.raises(ValueError, match=r"Consulted project evidence changed \(repository\)"):
        _apply_fixture(tmp_path, {"turn_id": turn})
    assert manuscript.joinpath("main.tex").read_text(encoding="utf-8").splitlines()[2] == "Original prose."


def test_equivalent_repository_default_alias_uses_latest_exact_read(tmp_path,monkeypatch):
    manuscript,_=_import_project(tmp_path)
    turn=_seed_revision(tmp_path,"fixture",[{"file":"main.tex","line_start":3,"line_end":3,
        "before":"Original prose.","after":"Final bounded correction.","reason":"precision"}],
        suffix="repository-default-alias")
    old={"repository":"laplace","source":{"path":"/project/build.log","bytes":3,"sha256":"old"},
         "content":"old","offset":0,"truncated":False}
    current={"repository":"laplace","source":{"path":"/project/build.log","bytes":7,"sha256":"current"},
             "content":"current","offset":0,"truncated":False}
    common={"action":"read","repository":"laplace","path":"project/build.log","limit":2000}
    writing_records.bank(tmp_path,{"record":"writing-tool-read","id":"READ-log-old","turn_id":turn,
        "project":"fixture","operation":"repository","payload":{**common,"offset":0},
        "output_sha256":read_contract.read_output_digest("repository",old)})
    writing_records.bank(tmp_path,{"record":"writing-tool-read","id":"READ-log-current","turn_id":turn,
        "project":"fixture","operation":"repository","payload":common,
        "output_sha256":read_contract.read_output_digest("repository",current)})
    reads=session_reads._records(tmp_path)["turns"][turn]["tool_reads"]
    repository=[row for row in reads.values() if row.get("operation")=="repository"]
    assert len(repository)==1 and repository[0]["id"]=="READ-log-current"
    monkeypatch.setattr(operations,'_execute',lambda *args,**kwargs:current)
    _bind_rewrite_fixture(monkeypatch,manuscript)
    assert _apply_fixture(tmp_path,{"turn_id":turn})["complete"] is True


def test_label_only_generated_candidate_does_not_bypass_changed_argument(tmp_path,monkeypatch):
    text="\\documentclass{article}\n\\begin{document}\n\\section{Heading}\nProse unchanged.\n\n\\label{sec:heading}\n\\end{document}\n"
    manuscript,_=_import_project(tmp_path,files={"main.tex":text})
    selection={"files":["main.tex"],"line_start":3,"line_end":6}
    context=authoring.build_context("fixture",selection,repo_root=tmp_path)
    edit={"file":"main.tex","line_start":3,"line_end":6,
          "before":"\\section{Heading}\nProse unchanged.\n\n\\label{sec:heading}",
          "after":"\\section{Heading}\n\\label{sec:heading}\n\nProse unchanged.",
          "reason":"Keep the same label beside its heading."}
    turn=_seed_revision(tmp_path,"fixture",[edit],selection=selection,context=context,suffix="label-move")
    writing_records.bank(tmp_path,{"record":"writing-tool-read","id":"READ-old-research",
        "turn_id":turn,"project":"fixture","operation":"research","payload":{},
        "output_sha256":"old-research"})
    # The earlier conversation evidence and argument moved, but this edit's
    # entire non-label TeX and every label identity remain byte-equivalent.
    authoring.save("fixture",{"base_revision":authoring.load("fixture",tmp_path)["revision"],
                              "argument":"Later argument state."},repo_root=tmp_path)
    monkeypatch.setattr(operations,'_execute',lambda *args,**kwargs:{"changed":True})
    _bind_rewrite_fixture(monkeypatch,manuscript)

    assert mutation_attribution._label_only_source_edit(edit) is True
    with pytest.raises(ValueError,match="argument-or-framing-changed"):
        _apply_fixture(tmp_path,{"turn_id":turn})
    assert manuscript.joinpath("main.tex").read_text()==text

    manuscript.joinpath("main.tex").write_text(text.replace("Prose unchanged.","Externally changed."))
    other=_seed_revision(tmp_path,"fixture",[edit],selection=selection,
                         context=authoring.build_context("fixture",selection,repo_root=tmp_path),
                         suffix="label-stale")
    with pytest.raises(ValueError,match="invalid source addressing|changed"):
        _apply_fixture(tmp_path,{"turn_id":other})


def test_fresh_exact_source_read_recovers_changed_passage_context_without_new_turn(tmp_path,monkeypatch):
    manuscript,_=_import_project(tmp_path)
    selection={"files":["main.tex"],"line_start":3,"line_end":3}
    context=authoring.build_context("fixture",selection,repo_root=tmp_path)
    turn=_seed_revision(tmp_path,"fixture",[],selection=selection,context=context,suffix="source-recovery")
    source=manuscript/"main.tex"
    source.write_text(source.read_text().replace("Original prose.","Externally revised prose."))

    read=writing_tools.execute(tmp_path,"fixture","work","source",selection,turn_id=turn)

    assert read["context_refresh"]["refreshed"] is True
    assert "Externally revised prose." in read["context_refresh"]["prompt"]
    current=session_reads._records(tmp_path)["turns"][turn]
    assert current["science_context_digest"]==read["context_refresh"]["science_context_digest"]
    proposal={"edits":[{"file":"main.tex","line_start":3,"line_end":3,
        "before":"Externally revised prose.","after":"Author accepted current prose.",
        "reason":"Continue from the explicitly reread source."}]}
    _bind_rewrite_fixture(monkeypatch,manuscript)
    applied=writing_tools.execute(tmp_path,"fixture","work","apply_revision",proposal,turn_id=turn)
    assert applied["complete"] is True
    rows=[json.loads(line) for line in (tmp_path/"contract/talk.jsonl").read_text().splitlines()]
    apply_baseline=next(row for row in reversed(rows)
        if row.get("record")=="writing-turn-context-baseline" and row.get("cause")=="current-turn-apply")
    assert isinstance(apply_baseline.get("science_context_digest"),str)


def test_context_recovery_checks_only_reads_that_can_cover_exact_stale_reasons(tmp_path,monkeypatch):
    _import_project(tmp_path)
    turn=_seed_revision(tmp_path,'fixture',[],selection={'files':['main.tex']},
                        context={'context_id':'CTX-fixture'},suffix='narrow-recovery')
    correction_id='AC-target';target={'id':correction_id,'status':'open'}
    writing_records.bank(tmp_path,{'record':'writing-tool-read','id':'READ-author-target',
        'turn_id':turn,'project':'fixture','operation':'author_history',
        'payload':{'id':correction_id},'output_sha256':read_contract.output_digest(target)})
    for index in range(80):
        writing_records.bank(tmp_path,{'record':'writing-tool-read','id':f'READ-irrelevant-{index}',
            'turn_id':turn,'project':'fixture','operation':'concept',
            'payload':{'node':f'claim:{index}'},
            'output_sha256':read_contract.output_digest({'node':index})})
    monkeypatch.setattr(authoring,'inspect',lambda *a,**k:{'stale':[{
        'context_id':'CTX-fixture','reasons':['correction-unconsumed:'+correction_id]}]})
    calls=[]
    monkeypatch.setattr(operations,'_execute',lambda root,project,mode,operation,payload,turn_id=None:
        calls.append((operation,payload)) or target)
    monkeypatch.setattr(authoring,'build_context',lambda *a,**k:{'context_id':'CTX-current',
        'dependencies':{},'document':{},'consumed':{},'science_context_digest':'science','prompt':'CURRENT'})

    unrelated=turn_reads.refresh_context_after_read(tmp_path,'fixture',turn,'read_artifact')
    assert unrelated['refreshed'] is False and unrelated['reads_checked']==0
    assert calls==[]
    refreshed=turn_reads.refresh_context_after_read(tmp_path,'fixture',turn,'author_history')
    assert refreshed['refreshed'] is True and refreshed['reads_checked']==1
    assert calls==[('author_history',{'id':correction_id})]


@pytest.mark.parametrize("history_view", ["activity", "telemetry"])
def test_activity_history_is_audit_only_while_exact_correction_read_remains_a_dependency(
        tmp_path,monkeypatch,history_view):
    manuscript,_=_import_project(tmp_path)
    selection={"files":["main.tex"],"line_start":3,"line_end":3}
    context=authoring.build_context("fixture",selection,repo_root=tmp_path)
    turn=_seed_revision(tmp_path,"fixture",[{"file":"main.tex","line_start":3,"line_end":3,
        "before":"Original prose.","after":"Revised after reviewing history.",
        "reason":"History browsing must not become an authoring dependency."}],
        selection=selection,context=context,suffix="activity-audit")
    writing_tools.execute(tmp_path,"fixture","work","source",selection,turn_id=turn)
    listed=writing_tools.execute(tmp_path,"fixture","work","author_history",
        {"view":history_view,"limit":20},turn_id=turn)
    activity_read=next(row for row in session_reads._records(tmp_path)["turns"][turn]["tool_reads"].values()
        if row["operation"]=="author_history")

    # Appending a canonical action changes the timeline that was displayed,
    # but does not change manuscript evidence or an author instruction.
    writing_records.bank(tmp_path,{"record":"writing-tool-action","id":"ACTION-after-history",
        "turn_id":turn,"project":"fixture","operation":"research_record","ts":"2026-09-30T12:00:00Z",
        "outcome":{"views":["research"],"receipts":["result-later"]}})
    current=operations._execute(tmp_path,"fixture","work","author_history",
        {"view":history_view,"limit":20},turn_id=turn)
    assert read_contract.read_output_digest("author_history",listed)!=read_contract.read_output_digest(
        "author_history",current),"the timeline really changed after it was read"
    assert mutation_attribution._read_views("author_history",activity_read["payload"])==set()
    with monkeypatch.context() as scoped:
        scoped.setattr(authoring,"inspect",lambda *a,**k:pytest.fail(
            "an activity timeline read must not inspect or refresh current authoring context"))
        ignored=turn_reads.refresh_context_after_read(tmp_path,"fixture",turn,"author_history",
            {"view":history_view,"limit":20})
    assert ignored=={"refreshed":False,"reason":"historical audit read"}
    _bind_rewrite_fixture(monkeypatch,manuscript)
    assert _apply_fixture(tmp_path,{"turn_id":turn})["complete"] is True

    # A normal exact correction read retains correction/manuscript dependency
    # semantics. Resolving that instruction after it was consumed makes a new
    # proposal stale rather than treating author_history as audit-only.
    manuscript2,_=_import_project(tmp_path,"fixture-correction")
    correction=authoring.bank_correction("fixture-correction",{
        "text":"Keep the finite-size qualification.","kind":"factual",
        "scope":"project","by":"author"},repo_root=tmp_path)
    context2=authoring.build_context("fixture-correction",selection,repo_root=tmp_path)
    turn2=_seed_revision(tmp_path,"fixture-correction",[{"file":"main.tex","line_start":3,"line_end":3,
        "before":"Original prose.","after":"Revision that consumed the instruction.",
        "reason":"Apply the current author instruction."}],selection=selection,
        context=context2,suffix="correction-dependency")
    writing_tools.execute(tmp_path,"fixture-correction","work","source",selection,turn_id=turn2)
    exact=writing_tools.execute(tmp_path,"fixture-correction","work","author_history",
        {"id":correction["correction"]["id"]},turn_id=turn2)
    assert exact["item"]["id"]==correction["correction"]["id"]
    assert mutation_attribution._read_views("author_history",{"id":exact["item"]["id"]})=={
        "corrections","manuscript"}
    authoring.correction_status("fixture-correction",{
        "id":correction["correction"]["id"],"status":"resolved",
        "base_revision":correction["revision"]},repo_root=tmp_path)
    _bind_rewrite_fixture(monkeypatch,manuscript2)
    with pytest.raises(ValueError,match="applicable corrections changed|consumed argument, evidence or corrections changed"):
        _apply_fixture(tmp_path,{"turn_id":turn2})


def test_context_recovery_requires_every_current_instruction_guide_and_uses_latest_exact_read(
        tmp_path,monkeypatch):
    _import_project(tmp_path)
    turn=_seed_revision(tmp_path,'fixture',[],selection={'files':['main.tex']},
                        context={'context_id':'CTX-guides'},suffix='guide-recovery')
    old={'A.md':{'content':'A current'},'B.md':{'content':'B old'}}
    for index,path in enumerate(('A.md','B.md')):
        writing_records.bank(tmp_path,{'record':'writing-tool-read','id':f'READ-guide-{index}',
            'turn_id':turn,'project':'fixture','operation':'project_guidance','payload':{'path':path},
            'output_sha256':read_contract.output_digest(old[path])})
    monkeypatch.setattr(authoring,'inspect',lambda *a,**k:{'stale':[{
        'context_id':'CTX-guides','reasons':['project-working-guide-changed']}]})
    from laplace.manuscript import project_protocol
    monkeypatch.setattr(project_protocol,'load',lambda *a,**k:{'documents':[
        {'path':'A.md','role':'instructions'},{'path':'B.md','role':'instructions'}]})
    live={'A.md':{'content':'A current'},'B.md':{'content':'B changed'}};calls=[]
    monkeypatch.setattr(operations,'_execute',lambda root,project,mode,operation,payload,turn_id=None:
        calls.append(payload['path']) or live[payload['path']])
    monkeypatch.setattr(authoring,'build_context',lambda *a,**k:pytest.fail('unread changed guide was blessed'))

    refused=turn_reads.refresh_context_after_read(tmp_path,'fixture',turn,'project_guidance')
    assert refused['refreshed'] is False and refused['reads_checked']==2
    assert refused['uncovered']==['project-working-guide-changed']
    assert calls==['A.md','B.md']

    writing_records.bank(tmp_path,{'record':'writing-tool-read','id':'READ-guide-B-current',
        'turn_id':turn,'project':'fixture','operation':'project_guidance','payload':{'path':'B.md'},
        'output_sha256':read_contract.output_digest(live['B.md'])})
    monkeypatch.setattr(authoring,'build_context',lambda *a,**k:{'context_id':'CTX-guides-current',
        'dependencies':{},'document':{},'consumed':{},'science_context_digest':'science','prompt':'CURRENT'})
    calls.clear()
    refreshed=turn_reads.refresh_context_after_read(tmp_path,'fixture',turn,'project_guidance')
    assert refreshed['refreshed'] is True and refreshed['reads_checked']==2
    assert calls==['A.md','B.md']


def test_human_updates_are_bounded_race_coalesced_and_acknowledge_exact_history_reads(tmp_path):
    _import_project(tmp_path)
    turn=_seed_revision(tmp_path,'fixture',[],selection={'files':['main.tex'],'line_start':3,'line_end':3},
                        context={'context_id':'CTX-updates','consumed':{'corrections':[]}},suffix='updates')
    from laplace.pipeline import authoring
    agent=authoring.bank_correction('fixture',{'text':'Agent progress only.','kind':'note',
        'scope':'project','by':'eigen:session'},repo_root=tmp_path)['correction']
    other=authoring.bank_correction('fixture',{'text':'Other passage.','kind':'factual',
        'scope':'passage','anchor':{'file':'other.tex'},'by':'author'},repo_root=tmp_path)['correction']
    humans=[authoring.bank_correction('fixture',{'text':f'Human update {index}.','kind':'factual',
        'scope':'project','by':'author'},repo_root=tmp_path)['correction'] for index in range(5)]
    provider_updates.acknowledge(tmp_path,'fixture',turn,humans[-1]['id'])  # Unoffered acknowledgement is not delivery proof.

    assert not session_reads._records(tmp_path)['turns'][turn].get('author_update_acks')
    first=provider_updates.author_offer(tmp_path,'fixture',turn)
    assert first['status']=='OFFERED_AT_TOOL_BOUNDARY' and len(first['updates'])==3
    assert first['pending_total']==5 and first['omitted']==2
    assert agent['id'] not in json.dumps(first) and other['id'] not in json.dumps(first)
    second=provider_updates.author_offer(tmp_path,'fixture',turn)
    assert second['status']=='OFFERED_AT_TOOL_BOUNDARY' and len(second['updates'])==2
    third=provider_updates.author_offer(tmp_path,'fixture',turn)
    assert third['status']=='AWAITING_EXACT_READ' and third['pending_total']==5
    assert not any(row.get('text') for row in third.get('updates') or [])

    provider_updates.acknowledge(tmp_path,'fixture',turn,humans[0]['id'])
    provider_updates.acknowledge(tmp_path,'fixture',turn,humans[-1]['id'])
    saved=session_reads._records(tmp_path)['turns'][turn]
    assert saved['author_update_acks'][humans[0]['id']]['status']=='EXACT_SCOPED_AUTHOR_HISTORY_READ'
    assert saved['author_update_acks'][humans[-1]['id']]['status']=='EXACT_SCOPED_AUTHOR_HISTORY_READ'
    attempted=[ident for row in saved['author_update_deliveries'] for ident in row['correction_ids']]
    assert len(attempted)==len(set(attempted))==5

    from laplace.projects.writing_sources import content_items
    for provider,kind in [('codex','inputText'),('claude','text')]:
        items=content_items({'ok':True,'author_updates':first},provider)
        assert items[0]['type']==kind and 'OFFERED_AT_TOOL_BOUNDARY' in items[0]['text']

    turn2=_seed_revision(tmp_path,'fixture',[],selection={'files':['main.tex']},
                         context={'context_id':'CTX-race'},suffix='update-race')
    writing_records.bank(tmp_path,{'record':'writing-turn-context-baseline','id':'CTXBASE-race',
        'turn_id':turn2,'project':'fixture','context_id':'CTX-race-current',
        'consumed':{'corrections':[row['id'] for row in humans]}})
    newest=authoring.bank_correction('fixture',{'text':'One concurrent update.','kind':'request',
        'scope':'project','by':'author'},repo_root=tmp_path)['correction']
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as pool:
        parallel=list(pool.map(lambda _index:provider_updates.author_offer(
            tmp_path,'fixture',turn2),range(2)))
    assert sorted(row['status'] for row in parallel)==['AWAITING_EXACT_READ','OFFERED_AT_TOOL_BOUNDARY']
    race=session_reads._records(tmp_path)['turns'][turn2]['author_update_deliveries']
    assert [ident for row in race for ident in row['correction_ids']]==[newest['id']]


def test_unanchored_legacy_source_edit_requires_fresh_source_centered_proposal(tmp_path,monkeypatch):
    manuscript,_=_import_project(tmp_path)
    selection={"files":["main.tex"],"line_start":3,"line_end":3}
    context=authoring.build_context("fixture",selection,repo_root=tmp_path)
    turn=_seed_revision(tmp_path,"fixture",[{"file":"main.tex","line_start":3,"line_end":3,
        "before":"Original prose.","after":"Selected prose revised.","reason":"Precise selected edit."}],
        selection=selection,context=context,suffix="unrelated-source")
    writing_tools.execute(tmp_path,"fixture","work","source",selection,turn_id=turn)
    path=manuscript/"main.tex";path.write_text(path.read_text().replace(
        "\\end{document}","% unrelated trailing note\n\\end{document}"))
    _bind_rewrite_fixture(monkeypatch,manuscript)

    with pytest.raises(ValueError,match="source scope is unproven|consumed source changed outside"):
        _apply_fixture(tmp_path,{"turn_id":turn})
    writing_tools.execute(tmp_path,"fixture","work","source",selection,turn_id=turn)
    fresh=authoring.build_context("fixture",selection,repo_root=tmp_path)
    writing_records.bank(tmp_path,{'record':'writing-turn-context-baseline','id':'CTX-fresh-reproposal',
        'turn_id':turn,'project':'fixture',**{k:fresh.get(k) for k in ('context_id','dependencies','document','selection')}})
    applied=source_application.apply_revision(tmp_path,"fixture",turn,{"edits":[{"file":"main.tex","line_start":3,"line_end":3,
        "before":"Original prose.","after":"Selected prose revised.","reason":"Fresh observed occurrence."}]})

    assert applied["complete"] is True
    assert "Selected prose revised." in path.read_text()


def test_transient_run_status_change_does_not_veto_source_revision(tmp_path, monkeypatch):
    manuscript, _ = _import_project(tmp_path)
    selection = {"files": ["main.tex"], "line_start": 3, "line_end": 3}
    context = authoring.build_context("fixture", selection, repo_root=tmp_path)
    turn_id = _seed_revision(tmp_path, "fixture", [{"file": "main.tex", "line_start": 3, "line_end": 3,
        "before": "Original prose.", "after": "Changed prose.", "reason": "fixture"}],
        selection=selection, context=context, suffix="run-status")
    writing_records.bank(tmp_path, {"record": "writing-tool-read", "id": "READ-run",
        "turn_id": turn_id, "project": "fixture", "operation": "run_status", "payload": {"id": "run-1"},
        "output_sha256": read_contract.output_digest({"state": "RUNNING"})})
    original = operations._execute
    monkeypatch.setattr(operations, '_execute', lambda root, project, mode, operation, payload, turn_id=None:
                        {"state": "COMPLETE"} if operation == "run_status" else original(root, project, mode, operation, payload, turn_id=turn_id))
    _bind_rewrite_fixture(monkeypatch, manuscript)

    applied = _apply_fixture(tmp_path, {"turn_id": turn_id})

    assert applied["complete"] is True


def test_references_attached_change_remains_a_source_revision_dependency(tmp_path, monkeypatch):
    manuscript, _ = _import_project(tmp_path)
    selection = {"files": ["main.tex"], "line_start": 3, "line_end": 3}
    context = authoring.build_context("fixture", selection, repo_root=tmp_path)
    turn_id = _seed_revision(tmp_path, "fixture", [{"file": "main.tex", "line_start": 3, "line_end": 3,
        "before": "Original prose.", "after": "Changed prose.", "reason": "fixture"}],
        selection=selection, context=context, suffix="references-attached")
    writing_records.bank(tmp_path, {"record": "writing-tool-read", "id": "READ-attached",
        "turn_id": turn_id, "project": "fixture", "operation": "references_attached", "payload": {},
        "output_sha256": read_contract.output_digest({"associations": []})})
    _seal_new_fixture_candidate(tmp_path,turn_id)
    original = operations._execute
    monkeypatch.setattr(operations, '_execute', lambda root, project, mode, operation, payload, turn_id=None:
                        {"associations": [{"key": "changed"}]} if operation == "references_attached" else original(root, project, mode, operation, payload, turn_id=turn_id))
    _bind_rewrite_fixture(monkeypatch, manuscript)

    with pytest.raises(ValueError, match="references_attached"):
        _apply_fixture(tmp_path, {"turn_id": turn_id})


@pytest.mark.parametrize("stale_kind", ["source", "argument", "correction"])
def test_semantically_stale_revision_refuses_without_source_write(tmp_path, monkeypatch, stale_kind):
    manuscript, _ = _import_project(tmp_path)
    selection = {"files": ["main.tex"], "line_start": 3, "line_end": 3}
    context = authoring.build_context("fixture", selection, repo_root=tmp_path)
    turn = _seed_revision(tmp_path, "fixture", [{
        "file": "main.tex", "line_start": 3, "line_end": 3,
        "before": "Original prose.", "after": "Stale revision.", "reason": "clarity"}],
        selection=selection, context=context, suffix=stale_kind)
    before = manuscript.joinpath("main.tex").read_text(encoding="utf-8")
    if stale_kind == "source":
        manuscript.joinpath("main.tex").write_text(before.replace("Original prose.", "Source moved."),
                                                    encoding="utf-8")
        expected = manuscript.joinpath("main.tex").read_text(encoding="utf-8")
    elif stale_kind == "argument":
        authoring.save("fixture", {"base_revision": context["revision"],
                                    "argument": "A changed argument."}, repo_root=tmp_path)
        expected = before
    else:
        authoring.bank_correction("fixture", {"base_revision": context["revision"],
            "text": "Do not make this claim.", "kind": "factual", "scope": "project"},
            repo_root=tmp_path)
        expected = before
    calls = _bind_rewrite_fixture(monkeypatch, manuscript)

    with pytest.raises(ValueError, match="changed"):
        _apply_fixture(tmp_path, {"turn_id": turn})

    assert manuscript.joinpath("main.tex").read_text(encoding="utf-8") == expected
    assert calls == []
    assert _application_rows(tmp_path) == []


def test_multifile_refusal_rolls_back_and_never_reports_success(tmp_path, monkeypatch):
    manuscript, _ = _import_project(tmp_path, files={
        "main.tex": "\\documentclass{article}\n\\begin{document}\n\\input{a}\n\\input{b}\n\\end{document}\n",
        "a.tex": "A one.\n", "b.tex": "B one.\n"})
    turn = _seed_revision(tmp_path, "fixture", [
        {"file": "a.tex", "line_start": 1, "line_end": 1,
         "before": "A one.", "after": "A two.", "reason": "first"},
        {"file": "b.tex", "line_start": 1, "line_end": 1,
         "before": "B one.", "after": "B two.", "reason": "second"}], suffix="multi")
    _bind_rewrite_fixture(monkeypatch, manuscript, refuse="b.tex")

    result = _apply_fixture(tmp_path, {"turn_id": turn})

    assert result["complete"] is False
    assert result["rolled_back"] is True
    assert manuscript.joinpath("a.tex").read_text(encoding="utf-8") == "A one.\n"
    assert manuscript.joinpath("b.tex").read_text(encoding="utf-8") == "B one.\n"
    with pytest.raises(ValueError, match="did not finish"):
        _apply_fixture(tmp_path, {"turn_id": turn})


def test_concurrent_apply_banks_one_application_and_one_reuse(tmp_path, monkeypatch):
    manuscript, _ = _import_project(tmp_path)
    turn = _seed_revision(tmp_path, "fixture", [{
        "file": "main.tex", "line_start": 3, "line_end": 3,
        "before": "Original prose.", "after": "One landing.", "reason": "once"}], suffix="race")
    calls = _bind_rewrite_fixture(monkeypatch, manuscript)
    barrier = threading.Barrier(3)
    results, errors = [], []

    def apply():
        barrier.wait()
        try:
            results.append(_apply_fixture(tmp_path, {"turn_id": turn}))
        except Exception as exc:  # captured for an assertion with both threads joined
            errors.append(exc)

    threads = [threading.Thread(target=apply) for _ in range(2)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(timeout=10)

    assert errors == []
    assert len(results) == 2 and sum(bool(row.get("reused")) for row in results) == 1
    assert len(calls) == 1
    assert len(_application_rows(tmp_path)) == 1


def test_read_only_import_keeps_all_authoring_state_out_of_source(tmp_path):
    manuscript, source = _import_project(tmp_path, editable=False)
    assert source["read_only"] is True
    authoring.load("fixture", repo_root=tmp_path)
    authoring.build_context("fixture", {"files": ["main.tex"]}, repo_root=tmp_path)

    assert not (manuscript / ".authoring.lock").exists()
    assert not (manuscript / "authoring.json").exists()
    state = tmp_path / source["storage_dir"]
    assert (state / ".authoring.lock").is_file()
    assert (state / "authoring.json").is_file()


class _Headers(dict):
    pass


class _StreamHandler:
    def __init__(self):
        self.headers = _Headers()
        self.wfile = io.BytesIO()
        self.status = None

    def send_response(self, status):
        self.status = status

    def send_header(self, *args):
        pass

    def end_headers(self):
        pass

    def send_error(self, status, message):
        raise AssertionError((status, message))


def test_active_snapshot_cursor_prevents_delta_replay(tmp_path, monkeypatch):
    (tmp_path / "contract").mkdir()
    writing_records.bank(tmp_path, {"record": "writing-session", "id": "WS-stream",
                                "project": "fixture", "provider": "codex", "model": "m",
                                "effort": "medium"})
    job = {"id": "WT-stream", "session_id": "WS-stream", "root": tmp_path,
           "text": "AB", "progress": "writing", "events": [
               {"type": "delta", "text": "A", "seq": 1},
               {"type": "delta", "text": "B", "seq": 2}],
           "condition": threading.Condition(), "done": False, "provider": None}
    turn_jobs._JOBS[job["id"]] = job
    active = session_reads.session_state(tmp_path, "WS-stream")["active"]
    assert {key: active[key] for key in ("id", "text", "progress", "cursor")} == {
        "id": "WT-stream", "text": "AB", "progress": "writing", "cursor": 2}
    assert active.get("usage") is None
    job["done"] = True
    monkeypatch.setattr(checkout, "repo_root", lambda: tmp_path)
    handler = _StreamHandler()

    controller.stream(handler, {"turn": [job["id"]], "after": [str(active["cursor"])]})

    assert handler.status == 200
    assert "data:" not in handler.wfile.getvalue().decode("utf-8")


def test_provider_native_turn_id_cannot_overwrite_logical_reply_join(tmp_path, monkeypatch):
    _import_project(tmp_path)

    class _Provider:
        def __init__(self, cwd, provider, model, effort, native_id, event, mode, project=None,
                         logical_turn_id=None, **kwargs):
            self.event = event
            self.logical_turn_id = logical_turn_id
        def run(self, prompt):
            self.event({"type": "session", "native_id": "native-thread", "model": "actual-model",
                        "provider": "codex"})
            return {"status": "completed", "text": "Provider-shaped final answer.",
                    "native_id": "native-thread", "turn_id": "native-turn"}

    monkeypatch.setattr(writing_provider, "WritingTurn", _Provider)
    started = turn_admission.start_turn(tmp_path, {
        "project": "fixture", "provider": "codex", "model": "chosen-model", "effort": "medium",
        "text": "Answer this.", "mode": "discuss", "request_id": "provider-shaped",
        "selection": {"files": ["main.tex"], "line_start": 3, "line_end": 3}})
    logical = started["turn_id"]
    job = turn_jobs._JOBS[logical]
    with job["condition"]:
        assert job["condition"].wait_for(lambda: job["done"], timeout=5)

    state = session_reads.session_state(tmp_path, started["session_id"])
    turn = next(row for row in state["turns"] if row["id"] == logical)

    assert logical.startswith("WT-") and logical != "native-turn"
    assert turn["reply"]["turn_id"] == logical
    assert turn["reply"]["native_turn_id"] == "native-turn"
    assert turn["reply"]["text"] == "Provider-shaped final answer."
    assert turn["reply"]["status"] == "completed" and not turn["reply"].get("error")


def test_resumed_writer_pays_for_the_changed_argument_part_and_not_the_unchanged_framing(tmp_path, monkeypatch):
    """The ONE delta, on the part the author moved.

    This replaces the assertion that a changed argument arrives through a second
    block ("CHANGED PROJECT ORIENTATION SINCE THE LAST TURN" carrying
    `argument_and_framing`): `_argument_delta` is deleted and the sustained argument is
    a part of the delivery like any other, so a change to it re-delivers THAT part and
    the unchanged framing beside it is withheld with the read that reaches it.
    """
    _import_project(tmp_path)
    selection = {"files": ["main.tex"], "line_start": 3, "line_end": 3}
    initial = authoring.build_context("fixture", selection, repo_root=tmp_path)
    from laplace.writing import operating as writing_operating
    brief = writing_operating.build("fixture", "work", tmp_path)
    writing_records.bank(tmp_path, {"record": "writing-session", "id": "WS-resume-delta",
                                "project": "fixture", "provider": "codex", "model": "m", "effort": "medium"})
    writing_records.bank(tmp_path, {"record": "writing-binding", "id": "WB-resume-delta",
                                "session_id": "WS-resume-delta", "native_id": "native-resume",
                                "model": "m", "tool_contract_digest": brief["tool_contract_digest"]})
    writing_records.bank(tmp_path, {"record": "writing-turn", "id": "WT-before-delta",
                                "session_id": "WS-resume-delta", "project": "fixture", "mode": "work",
                                "dependencies": initial["dependencies"],
                                "context_parts": {part["key"]: part["token"]
                                                  for part in initial["parts"]},
                                "orientation": turn_context._orientation_snapshot(brief)})
    writing_records.bank(tmp_path,{"record":"writing-reply","id":"WR-before-delta",
        "turn_id":"WT-before-delta","session_id":"WS-resume-delta","project":"fixture",
        "status":"completed","text":"Earlier saved reply."})
    authoring.save("fixture", {"base_revision": initial["revision"], "argument": "Changed sustained argument."},
                   repo_root=tmp_path)
    prompts = []
    class Provider:
        def __init__(self, *args, **kwargs): pass
        def run(self, prompt):
            prompts.append(prompt)
            return {"status": "completed", "text": "done", "turn_id": "native-turn"}
    monkeypatch.setattr(writing_provider, "WritingTurn", Provider)

    started = turn_admission.start_turn(tmp_path, {"project": "fixture", "session_id": "WS-resume-delta",
                                                "mode": "work", "selection": selection, "text": "Continue."})
    job = turn_jobs._JOBS[started["turn_id"]]
    with job["condition"]:
        assert job["condition"].wait_for(lambda: job["done"], timeout=5)

    assert "Changed sustained argument." in prompts[0]
    assert "Whole-manuscript framing:" not in prompts[0]
    # The ONE delta block, in the one channel the contract names, parsed where it is
    # written: `context_withheld` used to be a key on the turn row with no reader in
    # `src/`, and the rows are derivable from the block, so the row key is deleted and
    # this assertion reads the delivery instead.
    assert writing_operating.DELTA_HEADER in prompts[0]
    block = prompts[0].split(writing_operating.DELTA_HEADER, 1)[1]
    delta = json.loads(block.split("\n")[2])
    withheld = {row["part"]: row["read"] for row in delta["already_delivered"]}
    assert "framing" in withheld and withheld["framing"]["operation"] == "project"
    assert "sustained_argument" not in withheld
    # and the row itself carries the part baseline and nothing derived from it
    turn = session_reads._records(tmp_path)["turns"][started["turn_id"]]
    assert "framing" in (turn.get("context_parts") or {})
    assert "context_withheld" not in turn and "context_altitude" not in turn
    assert '"operation_contract"' not in prompts[0]
    assert '"rules"' not in prompts[0]


def test_exact_owned_context_rebase_advances_science_digest_for_resume_but_external_change_returns_it(
        tmp_path, monkeypatch):
    _import_project(tmp_path)
    observed_framing = authoring.build_context("fixture", {}, tmp_path)["prompt_framing"]
    from laplace.writing import operating as writing_operating
    session_id, turn_id = "WS-owned-science", "WT-owned-science"
    brief = writing_operating.build("fixture", "work", tmp_path)
    writing_records.bank(tmp_path, {"record": "writing-session", "id": session_id,
                                "project": "fixture", "provider": "codex", "model": "m",
                                "effort": "medium"})
    writing_records.bank(tmp_path, {"record": "writing-binding", "id": "WB-owned-science",
                                "session_id": session_id, "native_id": "same-native", "model": "m",
                                "tool_contract_digest": brief["tool_contract_digest"],
                                "native_registration_signature": brief["native_registration_signature"]})
    writing_records.bank(tmp_path, {"record": "writing-turn", "id": turn_id,
                                "session_id": session_id, "project": "fixture", "mode": "work",
                                "text": "first", "selection": {}, "context_id": "CTX-before",
                                "science_context_digest": "science-before",
                                "orientation": turn_context._orientation_snapshot(brief)})
    writing_records.bank(tmp_path,{"record":"writing-reply","id":"WR-owned-science",
        "turn_id":turn_id,"session_id":session_id,"project":"fixture",
        "status":"completed","text":"Earlier saved reply."})
    science = {"digest": "science-after-owned"}
    def built(_project, selection=None, **_kwargs):
        digest = "science-for-changed-selection" if (selection or {}).get("node_id") else science["digest"]
        # The delivery speaks in NAMED PARTS now, each with the token the one delta
        # mechanism compares; the structure part's token moves exactly when its text does.
        parts = [{"key": "preamble", "text": "INTRO", "chars": 5, "token": "intro", "read": None},
                 {"key": "canonical_structure",
                  "text": "Canonical joined structure for this selected edition and scope:\nHUGE-SCIENCE",
                  "chars": 74, "token": "structure-" + digest,
                  "read": {"operation": "structure", "payload": {}}}]
        return {"context_id": "CTX-current", "dependencies": {}, "document": {}, "consumed": {},
                "science_context_digest": digest, "altitude": "section", "parts": parts,
                "prompt_framing": observed_framing,
                "prompt": "\n\n".join(part["text"] for part in parts)}
    monkeypatch.setattr(authoring, "inspect", lambda *_args, **_kwargs: {
        "stale": [{"context_id": "CTX-before",
                   "reasons": ["structure-plan-conceptric-or-evidence-changed"]}]})
    monkeypatch.setattr(authoring, "build_context", built)
    before = {"context_current": True, "context_id": "CTX-before"}
    old_turn = session_reads._records(tmp_path)["turns"][turn_id]

    assert turn_reads._refresh_owned_context(
        tmp_path, old_turn, "concept_change", before, actual_views=["concepts", "structure"])
    rebased = session_reads._records(tmp_path)["turns"][turn_id]
    assert rebased["science_context_digest"] == "science-after-owned"
    rows = [json.loads(line) for line in (tmp_path / "contract/talk.jsonl").read_text().splitlines()]
    original = next(row for row in rows if row.get("record") == "writing-turn" and row.get("id") == turn_id)
    assert original["science_context_digest"] == "science-before"  # origin remains immutable

    prompts = []
    class Provider:
        def __init__(self, *args, **kwargs): pass
        def run(self, prompt):
            prompts.append(prompt)
            return {"status": "completed", "text": "done", "turn_id": "native-turn"}
    monkeypatch.setattr(writing_provider, "WritingTurn", Provider)
    first = turn_admission.start_turn(tmp_path, {"project": "fixture", "session_id": session_id,
                                              "mode": "work", "text": "Continue owned work.",
                                              "request_id": "owned-resume"})
    with turn_jobs._JOBS[first["turn_id"]]["condition"]:
        assert turn_jobs._JOBS[first["turn_id"]]["condition"].wait_for(
            lambda: turn_jobs._JOBS[first["turn_id"]]["done"], timeout=5)
    assert "HUGE-SCIENCE" not in prompts[0]

    # A later unowned scientific change still differs from the persisted exact
    # post-write identity, so it is delivered on the following continuation.
    science["digest"] = "science-after-external"
    second = turn_admission.start_turn(tmp_path, {"project": "fixture", "session_id": session_id,
                                               "mode": "work", "text": "Continue after change.",
                                               "request_id": "external-resume"})
    with turn_jobs._JOBS[second["turn_id"]]["condition"]:
        assert turn_jobs._JOBS[second["turn_id"]]["condition"].wait_for(
            lambda: turn_jobs._JOBS[second["turn_id"]]["done"], timeout=5)
    assert "HUGE-SCIENCE" in prompts[1]

    third = turn_admission.start_turn(tmp_path, {"project": "fixture", "session_id": session_id,
                                              "mode": "work", "text": "Change the selected scope.",
                                              "selection": {"node_id": "different-scope"},
                                              "request_id": "selection-resume"})
    with turn_jobs._JOBS[third["turn_id"]]["condition"]:
        assert turn_jobs._JOBS[third["turn_id"]]["condition"].wait_for(
            lambda: turn_jobs._JOBS[third["turn_id"]]["done"], timeout=5)
    assert "HUGE-SCIENCE" in prompts[2]


@pytest.mark.parametrize("provider_name", ["codex", "claude"])
def test_persisted_orientation_delivers_shared_rules_once_then_resumes_without_repetition(
        tmp_path, monkeypatch, provider_name):
    """Exercise actual saved turns, rather than a hand-built orientation dict."""
    _import_project(tmp_path)
    from laplace.writing import operating as writing_operating
    captured = []

    class Provider:
        def __init__(self, cwd, provider, model, effort, native_id, event, mode, **kwargs):
            self.native_id, self.event = native_id, event
        def run(self, prompt):
            captured.append({"native_id": self.native_id, "prompt": prompt,
                             "brief": self.operating_brief})
            self.event({"type": "session", "native_id": self.native_id or "same-native",
                        "model": "fixture-model", "provider": provider_name})
            return {"status": "completed", "text": "done", "turn_id": "fixture-native-turn"}

    monkeypatch.setattr(writing_provider, "WritingTurn", Provider)
    monkeypatch.setattr(writing_provider, "capabilities", lambda *a, **k: {"providers": []})
    session = turn_admission.new_session(tmp_path, "fixture", provider_name, "", "low")

    def send():
        result = turn_admission.start_turn(tmp_path, {
            "project": "fixture", "session_id": session["id"], "mode": "work",
            "selection": {"files": ["main.tex"], "line_start": 3, "line_end": 3},
            "text": "Continue this same passage."})
        job = turn_jobs._JOBS[result["turn_id"]]
        with job["condition"]:
            assert job["condition"].wait_for(lambda: job["done"], timeout=5)
        turn = session_reads._records(tmp_path)["turns"][result["turn_id"]]
        assert turn["reply"]["status"] == "completed"
        return turn

    first = send()
    assert captured[-1]["native_id"] is None
    assert first["orientation"]["tool_contract_digest"] == captured[-1]["brief"]["tool_contract_digest"]
    send()
    assert captured[-1]["native_id"] == "same-native"
    assert "CHANGED PROJECT ORIENTATION" not in captured[-1]["prompt"]

    changed_rule = "Fixture-only changed shared rule: read the current target."
    monkeypatch.setattr(writing_operating, "RULES", [*writing_operating.RULES, changed_rule])
    changed_turn=send()
    assert captured[-1]["native_id"] is None
    assert changed_turn["native_contract_migration"]["changed_kernel_members"] == [
        "shared_rules_revision"]
    assert changed_rule in captured[-1]["brief"]["rules"]
    assert changed_rule not in captured[-1]["prompt"]
    assert '"operation_contract"' not in captured[-1]["prompt"]
    send()
    assert captured[-1]["native_id"] == "same-native"
    assert "CHANGED PROJECT ORIENTATION" not in captured[-1]["prompt"]
    assert changed_rule not in captured[-1]["prompt"]


def test_provider_proposal_unique_exact_lines_are_normalized_banked_and_apply(tmp_path, monkeypatch):
    lines = ["\\documentclass{article}", "\\begin{document}"] + [f"Preamble line {i}." for i in range(3, 15)] + [
        "\\section{Evidence and interpretation}", "\\label{sec:evidence}",
        "An observation and its interpretation are separate parts of the argument. A figure can make their relationship easier to inspect.",
        "",
        "For this interface test, the relation $y=x^2$ defines the illustrative curve used in this test. It is a fixture, not a scientific result.",
        "", "\\end{document}", ""]
    manuscript, _ = _import_project(tmp_path, files={"main.tex": "\n".join(lines)})
    before = "\n".join(lines[16:20])
    after = ("An observation is the recorded value before interpretation.\n\n"
             "For this interface test, the relation $y=x^2$ defines the illustrative curve used in this test. "
             "It is a fixture, not a scientific result.\n")
    prompts, source_reads = [], []

    class _Provider:
        def __init__(self, cwd, provider, model, effort, native_id, event, mode,
                         project=None, logical_turn_id=None, **kwargs):
            self.cwd, self.mode, self.project = cwd, mode, project
            self.logical_turn_id = logical_turn_id
        def run(self, prompt):
            prompts.append(prompt)
            source_reads.append(writing_tools.execute(self.cwd, self.project, self.mode, "source",
                {"files": ["sources/fixture/main.tex"], "include_numbered_text": True}, turn_id=self.logical_turn_id))
            return {"status": "completed", "text": "proposal", "turn_id": "native-normalized",
                    "proposal": {"answer": "Fresh proposal", "edits": [{
                        "file": "sources/fixture/main.tex", "line_start": 16, "line_end": 20,
                        "before": before, "after": after, "reason": "connected explanation"}]}}

    monkeypatch.setattr(writing_provider, "WritingTurn", _Provider)
    started = turn_admission.start_turn(tmp_path, {"project": "fixture", "provider": "codex",
        "mode": "revise", "text": "Regenerate from current source.", "request_id": "normalize-lines",
        "selection": {"files": ["main.tex"], "section_ids": ["sec:evidence"],
                      "line_start": 15, "line_end": 19}})
    turn_id = started["turn_id"]
    job = turn_jobs._JOBS[turn_id]
    with job["condition"]:
        assert job["condition"].wait_for(lambda: job["done"], timeout=5)
    turn = next(row for row in session_reads.session_state(tmp_path, started["session_id"])["turns"]
                if row["id"] == turn_id)
    validation = turn["reply"]["proposal_validation"]
    edit = turn["reply"]["proposal"]["edits"][0]

    assert validation["valid"] is True and validation["status"] == "NORMALIZED"
    assert validation["edits"][0]["original_span"] == {
        "file": "sources/fixture/main.tex", "line_start": 16, "line_end": 20}
    assert validation["edits"][0]["normalized_span"] == {
        "file": "main.tex", "line_start": 17, "line_end": 20}
    assert edit["before"] == before and edit["after"] == after
    assert (edit["file"], edit["line_start"], edit["line_end"]) == ("main.tex", 17, 20)
    assert "000015 | \\section{Evidence and interpretation}" in prompts[0]
    selected_source = source_reads[0]["sources"][0]
    assert "000017 | An observation and its interpretation" in selected_source["numbered_text"]
    assert selected_source["text"] == manuscript.joinpath("main.tex").read_text()

    calls = _bind_rewrite_fixture(monkeypatch, manuscript)
    applied = _apply_fixture(tmp_path, {"turn_id": turn_id})
    assert applied["complete"] is True and len(calls) == 1
    revised = manuscript.joinpath("main.tex").read_text().split("\n")
    assert revised[16:20] == after.split("\n")[:4]


def test_ambiguous_provider_span_is_banked_invalid_and_apply_names_model_error(tmp_path, monkeypatch):
    manuscript, _ = _import_project(tmp_path, files={"main.tex":
        "\\documentclass{article}\n\\begin{document}\nRepeated paragraph.\n\n"
        "Repeated paragraph.\n\\end{document}\n"})

    class _Provider:
        def __init__(self, *args, **kwargs): pass
        def run(self, prompt):
            return {"status": "completed", "text": "proposal", "proposal": {
                "answer": "ambiguous", "edits": [{"file": "main.tex", "line_start": 2,
                    "line_end": 2, "before": "Repeated paragraph.",
                    "after": "Changed paragraph.", "reason": "ambiguous fixture"}]}}

    monkeypatch.setattr(writing_provider, "WritingTurn", _Provider)
    started = turn_admission.start_turn(tmp_path, {"project": "fixture", "provider": "codex",
        "mode": "revise", "text": "Revise repeated prose.", "request_id": "ambiguous-lines",
        "selection": {"files": ["main.tex"]}})
    job = turn_jobs._JOBS[started["turn_id"]]
    with job["condition"]:
        assert job["condition"].wait_for(lambda: job["done"], timeout=5)
    turn = session_reads.session_state(tmp_path, started["session_id"])["turns"][0]
    validation = turn["reply"]["proposal_validation"]
    assert validation["valid"] is False and validation["status"] == "INVALID"
    assert "multiple exact full-line matches" in validation["errors"][0]
    original = manuscript.joinpath("main.tex").read_text()
    monkeypatch.setattr(review_surface, "adjudicate",
                        lambda *args, **kwargs: pytest.fail("invalid proposal reached source door"))
    with pytest.raises(ValueError, match="invalid source addressing.*multiple exact"):
        _apply_fixture(tmp_path, {"turn_id": started["turn_id"]})
    assert manuscript.joinpath("main.tex").read_text() == original


def test_selected_rendered_quote_reaches_provider_with_connected_source(tmp_path, monkeypatch):
    _import_project(tmp_path, files={"main.tex":
        "\\documentclass{article}\n\\begin{document}\n"
        "Context explains the need.\nThe \\emph{selected} claim.\n"
        "The next sentence qualifies it.\n\\end{document}\n"})
    prompts = []

    class _Provider:
        def __init__(self, *args, **kwargs):
            pass

        def run(self, prompt):
            prompts.append(prompt)
            return {"status": "completed", "text": "Discussed."}

    monkeypatch.setattr(writing_provider, "WritingTurn", _Provider)
    started = turn_admission.start_turn(tmp_path, {
        "project": "fixture", "provider": "codex", "model": "test", "text": "Improve this.",
        "selection": {"files": ["main.tex"], "line_start": 3, "line_end": 5,
                      "quote": "The selected claim.", "anchor": {"file": "main.tex", "line_start": 4}}})
    job = turn_jobs._JOBS[started["turn_id"]]
    with job["condition"]:
        assert job["condition"].wait_for(lambda: job["done"], timeout=5)
    assert len(prompts) == 1
    assert "Context explains the need." in prompts[0]
    assert "The next sentence qualifies it." in prompts[0]
    assert "AUTHOR'S SELECTED PASSAGE" in prompts[0]
    assert '"quote": "The selected claim."' in prompts[0]
    assert "obtain exact source" in prompts[0]


def test_new_and_resumed_turn_receive_exact_unsaved_draft_outside_source_receipt(tmp_path,monkeypatch):
    manuscript,_=_import_project(tmp_path)
    prompts=[]
    class Provider:
        def __init__(self,*args,**kwargs):pass
        def run(self,prompt):prompts.append(prompt);return {'status':'completed','text':'Seen.'}
    monkeypatch.setattr(writing_provider, 'WritingTurn',Provider)
    draft={'status':'UNSAVED','format':'tex','text':'Draft \\emph{words}.\n',
           'anchor':{'file':'main.tex','line_start':3,'line_end':3},
           'reason':'The source editor has unsaved text.'}
    payload={'project':'fixture','provider':'codex','mode':'work','text':'Discuss this draft.',
             'selection':{'files':['main.tex'],'line_start':3,'line_end':3,'draft':draft}}
    first=turn_admission.start_turn(tmp_path,payload)
    with turn_jobs._JOBS[first['turn_id']]['condition']:
        assert turn_jobs._JOBS[first['turn_id']]['condition'].wait_for(
            lambda:turn_jobs._JOBS[first['turn_id']]['done'],timeout=5)
    second=turn_admission.start_turn(tmp_path,{**payload,'session_id':first['session_id'],
        'request_id':'resume-with-current-draft'})
    with turn_jobs._JOBS[second['turn_id']]['condition']:
        assert turn_jobs._JOBS[second['turn_id']]['condition'].wait_for(
            lambda:turn_jobs._JOBS[second['turn_id']]['done'],timeout=5)
    assert len(prompts)==2 and all(json.dumps(draft,ensure_ascii=False) in prompt for prompt in prompts)
    assert all('UNSAVED LOCAL EDITOR DRAFT' in prompt and 'use the source tool' in prompt
               and 'Never use this draft as an expected_source_digest' in prompt for prompt in prompts)
    turns=session_reads._records(tmp_path)['turns']
    for ident in (first['turn_id'],second['turn_id']):
        assert 'draft' not in turns[ident]['selection']
        assert turns[ident]['unsaved_draft']==draft
        assert turns[ident]['dependencies']['source_dependencies'][0]['digest']==hashlib.sha256(
            b'Original prose.\n').hexdigest()
    read=writing_tools.execute(tmp_path,'fixture','work','source',{},turn_id=second['turn_id'])
    assert read['sources'][0]['text']=='Original prose.\n'


def test_steer_delivers_unsaved_draft_but_banks_only_persisted_source_scope(tmp_path):
    _import_project(tmp_path)
    turn=_seed_revision(tmp_path,'fixture',[],selection={'files':['main.tex'],'line_start':3,'line_end':3},
                        suffix='draft-steer')
    received=[]
    class Provider:
        def control_capabilities(self):return {'can_steer':True,'can_interrupt':True}
        def steer(self,text):received.append(text);return {'ok':True}
    turn_jobs._JOBS[turn]={'done':False,'provider':Provider()}
    draft={'status':'UNSAVED','format':'rendered','text':'Locally revised words.',
           'anchor':{'file':'main.tex','line_start':3,'line_end':3},
           'reason':'Typing continued while saving.'}
    result=turn_control.steer_turn(tmp_path,{'turn_id':turn,'text':'Use my current wording.',
        'selection':{'files':['main.tex'],'line_start':3,'line_end':3,'draft':draft},
        'workspace_context':{'surface':'manuscript'}})
    assert result['ok'] and json.dumps(draft,ensure_ascii=False) in received[0]
    current=session_reads._records(tmp_path)['turns'][turn]
    assert 'draft' not in current['selection']
    assert 'draft' not in current['steering'][-1]['selection']
    assert current['steering'][-1]['unsaved_draft']==draft


def test_failure_recovery_names_exact_stale_read_payload_without_rebasing(tmp_path):
    manuscript,_=_import_project(tmp_path)
    selection={'files':['main.tex'],'line_start':3,'line_end':3}
    context=authoring.build_context('fixture',selection,repo_root=tmp_path)
    turn=_seed_revision(tmp_path,'fixture',[],selection=selection,context=context,suffix='recover-reads')
    writing_tools.execute(tmp_path,'fixture','work','source',selection,turn_id=turn)
    manuscript.joinpath('main.tex').write_text(
        '\\documentclass{article}\n\\begin{document}\nChanged prose.\n\\end{document}\n')
    before=len(authoring.load('fixture',repo_root=tmp_path)['contexts'])
    recovery=turn_reads.failure_recovery_reads(tmp_path,'fixture',turn,'apply_revision',{},
        'Consulted project evidence changed (source). Request a fresh revision; nothing was applied.')
    assert recovery['reads'][0]['operation']=='source'
    assert recovery['reads'][0]['payload']=={**selection,'project':'fixture'}
    assert any(row['reason'].startswith('source-revision-changed') for row in recovery['reads'])
    assert len(authoring.load('fixture',repo_root=tmp_path)['contexts'])==before


@pytest.mark.parametrize('draft,error',[
    ({'status':'SAVED','format':'tex','text':'x','anchor':{'file':'main.tex','line_start':1,'line_end':1},'reason':'x'},'status must be UNSAVED'),
    ({'status':'UNSAVED','format':'html','text':'x','anchor':{'file':'main.tex','line_start':1,'line_end':1},'reason':'x'},'format must be tex or rendered'),
    ({'status':'UNSAVED','format':'tex','text':'x'*64001,'anchor':{'file':'main.tex','line_start':1,'line_end':1},'reason':'x'},'limited to 64000'),
    ({'status':'UNSAVED','format':'tex','text':'x','anchor':{'file':'../other.tex','line_start':1,'line_end':1},'reason':'x'},'project-relative source path'),
])
def test_unsaved_draft_validation_is_explicit_and_never_truncates(tmp_path,draft,error):
    _import_project(tmp_path)
    with pytest.raises(ValueError,match=error):
        turn_admission.start_turn(tmp_path,{'project':'fixture','provider':'codex','mode':'work','text':'Discuss.',
            'selection':{'files':['main.tex'],'draft':draft}})


def test_legacy_native_turn_receipt_recovers_only_unmatched_logical_turn(tmp_path):
    (tmp_path / "contract").mkdir()
    writing_records.bank(tmp_path, {"record": "writing-session", "id": "WS-old",
                                "project": "fixture", "provider": "codex", "model": "m",
                                "effort": "medium"})
    writing_records.bank(tmp_path, {"record": "writing-turn", "id": "WT-logical",
                                "session_id": "WS-old", "project": "fixture", "text": "question"})
    writing_records.bank(tmp_path, {"record": "writing-reply", "id": "WR-old",
                                "turn_id": "native-old-turn", "session_id": "WS-old",
                                "project": "fixture", "status": "completed", "text": "old answer"})

    turn = session_reads.session_state(tmp_path, "WS-old")["turns"][0]

    assert turn["reply"]["turn_id"] == "WT-logical"
    assert turn["reply"]["native_turn_id"] == "native-old-turn"


def test_successful_apply_button_remains_terminally_disabled():
    module = Path("src/laplace/web/static_shared/writing-panel.mjs").read_text(encoding="utf-8")

    assert "apply.dataset.done='1'" in module or 'apply.dataset.done="1"' in module


def test_project_and_artifact_reads_bank_with_their_turn_or_with_none(tmp_path):
    """AMENDED by wave WRITING-RECONCILIATION-W1, packet altitude-dispatch, 2026-10-02.

    This test asserted the law "a read banks ONLY inside a logical turn", which is the defect
    the friction report of 2026-10-01 measured: refusals and acts outside a turn are banked
    nowhere, so "the system's failure record is a census of one provider's turns"
    (writing_tools.py:1239 and writing_provider.py:550, both at 87ece9da). The dispatch now banks the act on every
    caller path, into the same file and the same record kinds, carrying the act's own grain
    (verb, concept, altitude). What the test still guards is the part that was right: a read
    inside a turn carries THAT turn's id, and a read outside one claims no turn rather than
    borrowing the last one. The old behaviour is still reachable, with its retirement trigger,
    through LAPLACE_WRITING_BANK_EVERY_PATH=0 (writing_verbs.bank_every_path).
    """
    manuscript, source = _import_project(tmp_path, editable=False)
    state = tmp_path / source['storage_dir']; (state / 'research').mkdir(parents=True)
    (state / 'research' / 'note.txt').write_text('evidence', encoding='utf-8')
    writing_tools.execute(tmp_path, 'fixture', 'discuss', 'project', {}, turn_id='WT-logical')
    writing_tools.execute(tmp_path, 'fixture', 'discuss', 'read_artifact', {'path':'research/note.txt'}, turn_id='WT-logical')
    writing_tools.execute(tmp_path, 'fixture', 'discuss', 'project', {})
    rows=[json.loads(x) for x in (tmp_path/'contract/talk.jsonl').read_text().splitlines()]
    reads=[x for x in rows if x.get('record')=='writing-tool-read']
    assert {x['operation'] for x in reads}=={'project','read_artifact'}
    assert [x['turn_id'] for x in reads]==['WT-logical','WT-logical',None]
    assert all((x['verb'],x['altitude'])==('read','project') for x in reads)
    assert {x['concept'] for x in reads}=={'project@project','artifact@project'}


def test_successful_write_banks_small_turn_bound_action_and_refusal_banks_nothing(tmp_path):
    _import_project(tmp_path, editable=False)
    payload = {"path": "research/action.md", "before": None,
               "content": "SECRET-CONTENT-MUST-NOT-ENTER-ACTION\n",
               "reason": "PRIVATE-REASON-MUST-NOT-ENTER-ACTION"}

    saved = writing_tools.execute(tmp_path, "fixture", "work", "store_artifact",
                                  payload, turn_id="WT-action")
    with pytest.raises(ValueError):
        writing_tools.execute(tmp_path, "fixture", "work", "store_artifact",
                              payload, turn_id="WT-action")
    with pytest.raises(ValueError, match="Independent review"):
        writing_tools.execute(tmp_path, "fixture", "review", "store_artifact",
                              {**payload, "path": "research/discuss.md"}, turn_id="WT-discuss")

    rows = [json.loads(line) for line in (tmp_path / "contract/talk.jsonl").read_text().splitlines()]
    actions = [row for row in rows if row.get("record") == "writing-tool-action"]
    assert len(actions) == 1
    action = actions[0]
    assert action["project"] == "fixture" and action["turn_id"] == "WT-action"
    assert action["operation"] == "store_artifact"
    assert action["outcome"]["status"] == "SUCCEEDED"
    assert action["outcome"]["paths"] == ["writing_projects/fixture/research/action.md",
                                             "research/action.md"]
    assert action["outcome"]["revisions"]["revision"] == saved["revision"]
    assert action["outcome"]["views"] == ["research", "artifact"]
    assert saved["action_receipt"]["id"] == action["id"]
    encoded = json.dumps(action)
    assert "SECRET-CONTENT" not in encoded and "PRIVATE-REASON" not in encoded


def _style_prepare_request(root):
    """A valid CURRENT template-preparation request: the selected source's exact selection and byte guards."""
    from laplace.manuscript import manuscript_source
    from laplace.manuscript import document_templates
    source = manuscript_source.resolve("fixture", repo_root=root, include_candidates=False)
    path = root / source["root"]
    return {"action": "prepare", "source_edits": [{"file": source["root"],
            "content": path.read_text().replace("\\documentclass{article}", "\\documentclass[11pt]{article}")}],
            "guards": {"expected_selection": manuscript_source.selection_identity(source, "fixture"),
                       "source_guards": {source["root"]: document_templates.pin(path.read_bytes())}},
            "reason": "Inspect typography"}


def test_partial_return_is_receipted_with_actual_status_not_fabricated_success(tmp_path, monkeypatch):
    # M5 S3: `style` now reaches the document-template owner (document_templates.change) with a current
    # prepare request; the retired project_work.style patch no longer stood for that owner. Only the actual
    # owner's return is stubbed, to the original controlled partial result, inside an admitted turn.
    _import_project(tmp_path)
    writing_records.bank(tmp_path, {"record": "writing-session", "id": "WS-partial", "project": "fixture",
        "provider": "codex", "model": "m", "effort": "low"})
    writing_records.bank(tmp_path, {"record": "writing-turn", "id": "WT-partial", "session_id": "WS-partial",
        "project": "fixture", "text": "Prepare a style candidate.", "mode": "work"})
    from laplace.manuscript import document_templates
    calls = []
    monkeypatch.setattr(document_templates, "change", lambda project, payload, root, **kwargs: calls.append(payload) or {
        "id": "preview-partial", "status": "FAILED", "error": "fixture failure"})
    journal = tmp_path / "contract/talk.jsonl"
    rows_of = lambda: [json.loads(line) for line in journal.read_text().splitlines()]
    before = len(rows_of())
    request = _style_prepare_request(tmp_path)

    result = writing_tools.execute(tmp_path, "fixture", "work", "style", request, turn_id="WT-partial")
    added = rows_of()[before:]
    actions = [row for row in added if row.get("record") == "writing-tool-action"]

    assert len(calls) == 1 and calls[0]["action"] == "prepare", "the actual owner was reached once"
    assert result["status"] == "FAILED"
    assert len(actions) == 1, "one truthful action receipt"
    action = actions[0]
    assert action["outcome"]["status"] == "FAILED"
    assert action["outcome"]["identities"] == ["preview-partial"]
    assert action["outcome"]["receipts"] == ["preview-partial"]
    assert "error" not in action["outcome"], "the owner's error text is not copied into the compact outcome"
    assert action.get("turn_id") == "WT-partial" and action.get("project") == "fixture"
    assert not [row for row in added if row.get("record") in {"writing-tool-read-baseline", "writing-turn-context-baseline"}], \
        "a failed preparation renews no read or context baseline"


def test_malformed_style_request_refuses_before_the_template_owner(tmp_path, monkeypatch):
    _import_project(tmp_path)
    from laplace.native import declarations as writing_declarations
    from laplace.manuscript import document_templates
    calls = []
    monkeypatch.setattr(document_templates, "change", lambda *args, **kwargs: calls.append(args) or {"status": "FAILED"})
    with pytest.raises(writing_declarations.PayloadAdmissionError):
        writing_tools.execute(tmp_path, "fixture", "work", "style", {}, turn_id="WT-partial")
    journal = tmp_path / "contract/talk.jsonl"
    rows = [json.loads(line) for line in journal.read_text().splitlines()] if journal.exists() else []
    assert calls == [] and not [row for row in rows if row.get("record") == "writing-tool-action"]


def test_session_and_reply_expose_actual_action_outcomes(tmp_path):
    _import_project(tmp_path, editable=False)
    writing_records.bank(tmp_path, {"record": "writing-session", "id": "WS-actions",
        "project": "fixture", "provider": "codex", "model": "m", "effort": "low"})
    writing_records.bank(tmp_path, {"record": "writing-turn", "id": "WT-actions",
        "session_id": "WS-actions", "project": "fixture", "text": "Do the work.", "mode": "work"})
    writing_tools.execute(tmp_path, "fixture", "work", "store_artifact", {
        "path": "research/outcome.md", "before": None, "content": "actual\n",
        "reason": "fixture"}, turn_id="WT-actions")
    writing_records.bank(tmp_path, {"record": "writing-reply", "id": "WR-actions",
        "turn_id": "WT-actions", "session_id": "WS-actions", "project": "fixture",
        "status": "completed", "text": "Done."})

    session = session_reads.session_state(tmp_path, "WS-actions")
    turn = session["turns"][0]

    assert len(session["actions"]) == len(turn["actions"]) == 1
    assert turn["reply"]["actions"] == turn["actions"]
    assert turn["actions"][0]["operation"] == "store_artifact"
    assert turn["actions"][0]["outcome"]["links"][0]["href"].startswith("/project?")


def test_provider_write_outcome_is_saved_and_emitted_with_logical_turn(tmp_path, monkeypatch):
    _import_project(tmp_path, editable=False)

    class _WorkingProvider:
        def __init__(self, cwd, provider, model, effort, native_id, event, mode,
                         project=None, logical_turn_id=None, **kwargs):
            self.cwd, self.project, self.mode = cwd, project, mode
            self.logical_turn_id = logical_turn_id

        def run(self, prompt):
            writing_tools.execute(self.cwd, self.project, self.mode, "store_artifact", {
                "path": "research/provider.md", "before": None,
                "content": "provider output\n", "reason": "fixture"},
                turn_id=self.logical_turn_id)
            return {"status": "completed", "text": "Project work completed."}

    monkeypatch.setattr(writing_provider, "WritingTurn", _WorkingProvider)
    started = turn_admission.start_turn(tmp_path, {"project": "fixture", "provider": "codex",
        "mode": "work", "text": "Create the bounded artifact."})
    job = turn_jobs._JOBS[started["turn_id"]]
    with job["condition"]:
        assert job["condition"].wait_for(lambda: job["done"], timeout=5)
    session = session_reads.session_state(tmp_path, started["session_id"])
    turn = session["turns"][0]
    complete = next(event for event in job["events"] if event.get("type") == "complete")

    assert turn["actions"][0]["turn_id"] == started["turn_id"]
    assert turn["reply"]["actions"] == turn["actions"]
    assert complete["result"]["actions"] == turn["actions"]


def test_native_selected_source_change_becomes_a_manuscript_refresh_action(tmp_path, monkeypatch):
    manuscript, _ = _import_project(tmp_path)
    class Provider:
        def __init__(self, *args, **kwargs): pass
        def run(self, prompt):
            return {"status": "completed", "text": "Edited natively.", "native_file_changes": [
                {"path": str((manuscript / "main.tex").resolve()), "kind": "update", "status": "completed"}]}
    monkeypatch.setattr(writing_provider, "WritingTurn", Provider)

    started = turn_admission.start_turn(tmp_path, {"project": "fixture", "provider": "codex", "mode": "work",
        "selection": {"files": ["main.tex"]}, "text": "Make the native source edit."})
    job = turn_jobs._JOBS[started["turn_id"]]
    with job["condition"]:
        assert job["condition"].wait_for(lambda: job["done"], timeout=5)
    turn = next(row for row in session_reads.session_state(tmp_path, started["session_id"])["turns"]
                if row["id"] == started["turn_id"])

    action = next(row for row in turn["actions"] if row["operation"] == "native_file_change")
    assert action["outcome"]["views"] == ["manuscript", "document"]
    assert action["outcome"]["paths"] == [str((manuscript / "main.tex").resolve())]


def test_project_tool_mode_and_paths_stay_inside_isolated_project(tmp_path):
    manuscript, source = _import_project(tmp_path, editable=False)
    state_root = tmp_path / source["storage_dir"]
    payload = {"path": "research/notes.md", "before": None,
               "content": "bounded result\n", "reason": "fixture"}

    with pytest.raises(ValueError, match="Independent review"):
        writing_tools.execute(tmp_path, "fixture", "review", "store_artifact", payload)
    saved = writing_tools.execute(tmp_path, "fixture", "work", "store_artifact", payload)
    read = writing_tools.execute(tmp_path, "fixture", "review", "read_artifact",
                                 {"path": "research/notes.md"})

    assert saved["saved"] == "writing_projects/fixture/research/notes.md"
    assert read["content"] == "bounded result\n"
    assert (state_root / "research" / "notes.md").is_file()
    assert not (manuscript / "research" / "notes.md").exists()
    with pytest.raises(ValueError, match="Research artifacts belong"):
        writing_tools.execute(tmp_path, "fixture", "work", "store_artifact",
                              {**payload, "path": "../escape.md"})


def test_project_tool_routes_handlers_with_the_explicit_fixture_root(tmp_path):
    _import_project(tmp_path, editable=False)

    result = writing_tools.execute(tmp_path, "fixture", "discuss", "research", {})

    assert result["project"] == "fixture"
    assert result["schema_version"] == "laplace.research-state/1"


def test_queued_session_requests_are_durable_dispatched_only_on_send_and_not_auto_completed(tmp_path, monkeypatch):
    _import_project(tmp_path)
    from laplace.work import project_work
    queued = project_work.task('fixture', {'id':'REQUEST-one','title':'Cite the selected claim',
        'goal':'Find supporting literature and add it when warranted.','kind':'session-request','section_ids':[],
        'anchor':{'file':'main.tex','line_start':3,'line_end':3,'quote':'Original prose.','section':'sec:fixture'}}, tmp_path)
    prompts = []
    class Provider:
        def __init__(self, *args, **kwargs): pass
        def run(self, prompt):
            prompts.append(prompt)
            return {'status':'completed','text':'Queued request considered.','turn_id':'native-queued'}
    monkeypatch.setattr(writing_provider, 'WritingTurn', Provider)

    started = turn_admission.start_turn(tmp_path, {'project':'fixture','provider':'codex','mode':'work',
        'text':'','queued_work_ids':[queued['id']]})
    job = turn_jobs._JOBS[started['turn_id']]
    with job['condition']:
        assert job['condition'].wait_for(lambda: job['done'],timeout=5)
    turn = next(row for row in session_reads.session_state(tmp_path, started['session_id'])['turns']
                if row['id']==started['turn_id'])

    assert started['queued_work_ids']==turn['queued_work_ids']==turn['reply']['queued_work_ids']==['REQUEST-one']
    assert 'QUEUED AUTHOR REQUESTS INCLUDED IN THIS TURN' in prompts[0]
    assert 'Original prose.' in prompts[0]
    assert next(row for row in project_work.state('fixture',tmp_path)['tasks'] if row['id']=='REQUEST-one')['status']=='ready'


def test_queued_session_request_ids_refuse_unknown_foreign_or_completed_tasks(tmp_path):
    _import_project(tmp_path)
    from laplace.work import project_work
    other = project_work.task('fixture', {'id':'WORK-not-request','title':'Other','goal':'Other work.'}, tmp_path)
    with pytest.raises(ValueError, match='unavailable'):
        turn_admission.start_turn(tmp_path, {'project':'fixture','text':'','queued_work_ids':['REQUEST-missing']})
    with pytest.raises(ValueError, match='session-request'):
        turn_admission.start_turn(tmp_path, {'project':'fixture','text':'','queued_work_ids':[other['id']]})
    queued = project_work.task('fixture', {'id':'REQUEST-done','title':'Done request','goal':'Already done.',
        'kind':'session-request'}, tmp_path)
    action=project_work.read('fixture',{'view':'detail','id':queued['id']},tmp_path)['allowed_actions']['task_status']
    project_work.transition('fixture',{**action['payload'],'status':'cancelled'},tmp_path)
    with pytest.raises(ValueError, match='already complete'):
        turn_admission.start_turn(tmp_path, {'project':'fixture','text':'','queued_work_ids':[queued['id']]})


def test_completed_session_request_stays_done_after_later_source_edit(tmp_path):
    source, _ = _import_project(tmp_path)
    from laplace.work import project_work
    queued = project_work.task('fixture', {'id':'REQUEST-answer','title':'Answer this',
        'goal':'Answer the author question.','kind':'session-request','section_ids':[],
        'anchor':{'file':'main.tex','line_start':3,'line_end':3,'quote':'Original prose.'}}, tmp_path)
    writing_records.bank(tmp_path, {'record':'writing-session','id':'WS-queued-done','project':'fixture',
                                'provider':'codex','model':'','effort':'low'})
    writing_records.bank(tmp_path, {'record':'writing-turn','id':'WT-queued-done','session_id':'WS-queued-done',
                                'project':'fixture','text':'Answer queued request.','mode':'work'})

    action=project_work.read('fixture',{'view':'detail','id':queued['id']},tmp_path)['allowed_actions']['task_status']
    transition = writing_tools.execute(tmp_path, 'fixture', 'work', 'task_status', {
        **action['payload'],'status':'done','summary':'Answered from the current manuscript.'}, turn_id='WT-queued-done')
    source.joinpath('main.tex').write_text(source.joinpath('main.tex').read_text(encoding='utf-8').replace('Original prose.','Later unrelated prose.'),encoding='utf-8')
    state = next(row for row in project_work.state('fixture',tmp_path)['tasks'] if row['id']==queued['id'])

    assert transition['completed_in_turn']=='WT-queued-done'
    assert state['status']=='done' and state['evidence_currentness']['historical'] is True


def test_section_change_endpoint_forwards_the_source_aware_transaction_payload(tmp_path, monkeypatch):
    from laplace.manuscript import manuscript_structure
    _import_project(tmp_path)
    captured = {}
    payload = {"project": "fixture", "operation": "delete-section", "section_id": "sec:intro",
               "expected_source_digest": "source-digest", "expected_plan_revision": "plan-revision",
               "receipt_id": "section-receipt"}
    def change(project, received, root):
        captured.update(project=project, payload=received, root=root)
        return {"ok": True, "operation": received["operation"], "receipt": {"id": received["receipt_id"]}}
    monkeypatch.setattr(checkout, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(manuscript_structure, "change", change, raising=False)

    status, _, raw = controller.handle("/authoring/section-change", {}, "POST", json.dumps(payload).encode())

    assert status == 200
    assert captured == {"project": "fixture", "payload": payload, "root": tmp_path}
    assert json.loads(raw)["receipt"]["id"] == "section-receipt"


def test_correction_status_endpoint_forwards_exact_status_payload(tmp_path, monkeypatch):
    _import_project(tmp_path)
    captured = {}
    payload = {"project": "fixture", "id": "AC-one", "status": "dismissed",
               "base_revision": 3, "note": "No longer applicable."}
    monkeypatch.setattr(checkout, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(authoring, "correction_status", lambda project, received, repo_root: (
        captured.update(project=project, payload=received, root=repo_root) or
        {"project": project, "revision": 4, "status": received["status"]}))

    status, _, raw = controller.handle(
        "/authoring/correction-status", {}, "POST", json.dumps(payload).encode())

    assert status == 200
    assert captured == {"project": "fixture", "payload": payload, "root": tmp_path}
    assert json.loads(raw)["status"] == "dismissed"


def test_session_state_exposes_tool_failures_separately_from_actions(tmp_path):
    _import_project(tmp_path)
    writing_records.bank(tmp_path, {"record": "writing-session", "id": "WS-failure",
        "project": "fixture", "provider": "codex", "model": "", "effort": "medium"})
    writing_records.bank(tmp_path, {"record": "writing-turn", "id": "WT-failure",
        "session_id": "WS-failure", "project": "fixture", "mode": "work", "text": "test"})
    writing_records.bank(tmp_path, {"record": "writing-tool-failure", "id": "FAIL-one",
        "turn_id": "WT-failure", "project": "fixture", "operation": "research_record",
        "payload": {"bad": True}, "error_type": "ValueError", "error": "bad record"})

    state = session_reads.session_state(tmp_path, "WS-failure")

    assert state["turns"][0]["tool_failures"][0]["id"] == "FAIL-one"
    assert state["turns"][0]["actions"] == []


def test_session_summary_is_small_and_exact_turn_activity_is_lazy_paginated(tmp_path):
    _import_project(tmp_path)
    writing_records.bank(tmp_path, {"record": "writing-session", "id": "WS-summary",
        "project": "fixture", "provider": "codex", "model": "m", "effort": "medium"})
    writing_records.bank(tmp_path, {"record": "writing-turn", "id": "WT-summary",
        "session_id": "WS-summary", "project": "fixture", "mode": "work",
        "text": "Keep the current goal visible.", "selection": {"files": ["main.tex"]}})
    large = "source body " * 5000
    for index in range(3):
        writing_records.bank(tmp_path, {"record": "writing-tool-action", "id": f"ACTION-{index}",
            "turn_id": "WT-summary", "project": "fixture", "operation": "store_artifact",
            "outcome": {"status": "SUCCEEDED", "paths": [f"artifact-{index}.md"],
                        "receipt": large}})
    for index in range(2):
        writing_records.bank(tmp_path, {"record": "writing-tool-failure", "id": f"FAIL-{index}",
            "turn_id": "WT-summary", "project": "fixture", "operation": "repository",
            "payload": {"path": f"missing-{index}.tex"}, "error": large})
    writing_records.bank(tmp_path, {"record": "writing-reply", "id": "WR-summary",
        "turn_id": "WT-summary", "session_id": "WS-summary", "project": "fixture",
        "status": "completed", "text": "The bounded response remains visible.",
        "provider_issues": [{"tool_use_id":"FAIL-0","operation":"repository","error":large},
                            {"tool_use_id":"provider-extra","operation":"source","error":"extra"}],
        "proposal": {"answer": "Review separately", "edits": [{
            "file": "main.tex", "line_start": 3, "line_end": 3,
            "before": "Original prose.", "after": large}]}})
    writing_records.bank(tmp_path, {"record": "writing-application", "id": "APP-summary",
        "turn_id": "WT-summary", "project": "fixture", "complete": True,
        "edits": [{"file": "main.tex", "line_start": 3, "line_end": 3,
                   "before": "Original prose.", "after": large}]})

    full = session_reads.session_state(tmp_path, "WS-summary")
    summary = session_reads.session_state(tmp_path, "WS-summary", view="summary", limit=20)
    encoded_full = len(json.dumps(full).encode()); encoded_summary = len(json.dumps(summary).encode())
    turn = summary["turns"][0]
    assert encoded_summary < encoded_full / 20
    assert turn["text"] == "Keep the current goal visible."
    # A thread row never carries reply.text (SR2): the excerpt is display_text and the exact
    # body is one read away through body_read.
    assert "text" not in turn["reply"] and turn["body_read"]["http"]["url"].endswith("view=turn")
    assert (turn["action_count"], turn["failure_count"], turn["proposal_edit_count"]) == (4, 3, 1)
    assert turn["reply"]["display_text"] == "Review separately"
    assert "proposal" not in turn and "tool_failures" not in turn and "actions" not in turn
    assert turn["undo_entries"] == [{"id": "APP-summary", "kind": "source-edits",
        "edit_count": 1, "detail": {"turn_id": "WT-summary", "view": "application",
                                    "item_id": "APP-summary"}}]

    actions = session_reads.session_turn_detail(tmp_path, "fixture", "WT-summary", "actions", 1, 1)
    failures = session_reads.session_turn_detail(tmp_path, "fixture", "WT-summary", "failures", 0, 1)
    exact = session_reads.session_turn_detail(tmp_path, "fixture", "WT-summary", "turn")
    application = session_reads.session_turn_detail(
        tmp_path, "fixture", "WT-summary", "application", item_id="APP-summary")
    assert actions["pagination"] == {"offset": 1, "limit": 1, "total": 4, "next_offset": 2}
    assert actions["items"][0]["id"] == "ACTION-1"
    assert failures["pagination"]["total"] == 3 and failures["items"][0]["record"]["id"] == "FAIL-0"
    assert exact["turn"]["proposal"]["edits"][0]["after"] == large
    assert application["application"]["edits"][0]["after"] == large


def test_session_summary_undo_handles_follow_journal_order_and_deduplicate_receipts(tmp_path):
    _import_project(tmp_path)
    writing_records.bank(tmp_path,{"record":"writing-session","id":"WS-order","project":"fixture",
        "provider":"codex","model":"m","effort":"low"})
    writing_records.bank(tmp_path,{"record":"writing-turn","id":"WT-order","session_id":"WS-order",
        "project":"fixture","mode":"work","text":"ordered"})
    first_ref={"kind":"block","id":"BLOCK-first","project":"fixture"}
    last_ref={"kind":"section","id":"SECTION-last","project":"fixture"}
    writing_records.bank(tmp_path,{"record":"writing-tool-action","id":"ACTION-first","turn_id":"WT-order",
        "project":"fixture","operation":"block_change","outcome":{"undo_ref":first_ref}})
    writing_records.bank(tmp_path,{"record":"writing-application","id":"APP-middle","turn_id":"WT-order",
        "project":"fixture","complete":True,"edits":[{"file":"main.tex","line_start":3,
        "line_end":3,"before":"Original prose.","after":"Middle."}]})
    writing_records.bank(tmp_path,{"record":"writing-tool-action","id":"ACTION-last","turn_id":"WT-order",
        "project":"fixture","operation":"section_change","outcome":{"undo_ref":last_ref}})
    writing_records.bank(tmp_path,{"record":"writing-application","id":"APP-last-duplicate","turn_id":"WT-order",
        "project":"fixture","complete":True,"undo_ref":last_ref})

    entries=session_reads.session_state(tmp_path,"WS-order",view="summary")["turns"][0]["undo_entries"]
    assert [row["id"] for row in entries]==["ACTION-first","APP-middle","APP-last-duplicate"]
    assert entries[-1]["undo_ref"]==last_ref


def test_large_public_bodies_use_verified_shared_custody_and_fail_closed(tmp_path):
    from laplace.representation import atlas_bridge
    from laplace.work import history as author_history
    _import_project(tmp_path)
    writing_records.bank(tmp_path,{"record":"writing-session","id":"WS-custody","project":"fixture",
        "provider":"codex","model":"m","effort":"low"})
    body={"answer":"Saved public proposal","edits":[{"file":"main.tex","line_start":3,
        "line_end":3,"before":"Original prose.","after":"x"*20000}]}
    for index in range(2):
        turn=f"WT-custody-{index}"
        writing_records.bank(tmp_path,{"record":"writing-turn","id":turn,"session_id":"WS-custody",
            "project":"fixture","mode":"revise","text":"revise"})
        writing_records.bank(tmp_path,{"record":"writing-proposal","id":f"PROP-custody-{index}",
            "turn_id":turn,"project":"fixture","proposal":body})
    rows=[json.loads(line) for line in (tmp_path/"contract"/"talk.jsonl").read_text().splitlines()]
    proposals=[row for row in rows if row.get("record")=="writing-proposal"]
    assert proposals[0]["proposal"]["schema_version"]=="laplace.writing-public-body-ref/1"
    assert proposals[0]["proposal"]["content_handle"]==proposals[1]["proposal"]["content_handle"]
    assert len(list((tmp_path/"contract"/"writing_bodies").rglob("*")))==2  # one directory + one shared blob
    assert session_reads._records(tmp_path)["turns"]["WT-custody-0"]["pending_proposal"]==body
    assert author_history.record(
        "fixture","activity:journal:PROP-custody-0",tmp_path)["record"]["proposal"]==body

    blob=writing_bodies.store(tmp_path).key_path(proposals[0]["proposal"]["content_handle"]);blob.unlink()
    records_fold._CACHE.clear()
    summary=session_reads.session_state(tmp_path,"WS-custody",view="summary")
    assert summary["turns"][0]["storage_errors"]
    with pytest.raises(ValueError,match="saved public body is unavailable or corrupt"):
        _apply_fixture(tmp_path,{"turn_id":"WT-custody-0"})


def test_change_preview_endpoint_forwards_read_only_file_or_correction_query(tmp_path, monkeypatch):
    from laplace.manuscript import manuscript_fragments
    _import_project(tmp_path)
    calls = []
    monkeypatch.setattr(checkout, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(manuscript_fragments, "change_preview", lambda project, payload, root: (
        calls.append((project, payload, root)) or {"mode": "baseline", "hunks": []}))

    status, _, raw = controller.handle("/authoring/change-preview", {
        "project": ["fixture"], "file": ["main.tex"]}, "GET", b"")

    assert status == 200 and json.loads(raw)["mode"] == "baseline"
    assert calls == [("fixture", {"file": "main.tex", "id": ""}, tmp_path)]


def test_scanner_project_library_handler_receives_the_scanner_root(tmp_path, monkeypatch):
    _import_project(tmp_path, editable=False)
    monkeypatch.setattr(scanner, "_repo_root", lambda: tmp_path)

    status, _, raw = scanner._writing_response(
        writing_projects, "/projects/library", {}, "GET", b"")
    names = {row["name"] for row in json.loads(raw)["projects"]}

    assert status == 200
    assert "fixture" in names


def test_corrupt_read_only_state_dir_cannot_escape_or_fall_back_to_source(tmp_path):
    manuscript = tmp_path / "source"
    manuscript.mkdir()
    (manuscript / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}words\\end{document}\n", encoding="utf-8")
    (tmp_path / "registry_projects.json").write_text(json.dumps({"projects": [{
        "name": "foreign", "kind": "conceptric", "project_dir": "state",
        "tex_root": "source", "manuscript_dir": "source",
        "manifest": {"document": {"root": "source/main.tex", "manuscript_dir": "source",
                                  "read_only": True, "state_dir": "../../escape"}}
    }]}), encoding="utf-8")

    with pytest.raises(ValueError):
        writing_tools.execute(tmp_path, "foreign", "work", "store_artifact", {
            "path": "research/x.md", "before": None, "content": "x", "reason": "boundary"})
    assert not (tmp_path.parent.parent / "escape" / "research" / "x.md").exists()
    assert not (manuscript / ".authoring.lock").exists()
    assert not (manuscript / "authoring.json").exists()

    # A nominal project read also needs to fail closed.  Falling back to the
    # author-owned source directory would mutate it merely by opening the UI/tool.
    with pytest.raises(ValueError, match="state|read-only|writable"):
        writing_tools.execute(tmp_path, "foreign", "discuss", "project", {})
    assert not (manuscript / ".authoring.lock").exists()
    assert not (manuscript / "authoring.json").exists()


def test_independent_review_cannot_reuse_producing_conversation(tmp_path):
    _import_project(tmp_path)
    session=turn_admission.new_session(tmp_path,'fixture','codex','chosen-model','low')
    with pytest.raises(ValueError,match='fresh review'):
        turn_admission.start_turn(tmp_path,{'project':'fixture','session_id':session['id'],
            'mode':'review','text':'Review independently.'})
    review = turn_admission.new_session(tmp_path, 'fixture', 'codex', 'chosen-model', 'low', role='review')
    with pytest.raises(ValueError, match='continue it in review mode'):
        turn_admission.start_turn(tmp_path, {'project':'fixture','session_id':review['id'],
            'mode':'discuss','text':'Leave review mode.'})


def test_review_request_id_cannot_recover_an_author_turn(tmp_path):
    _import_project(tmp_path)
    session = turn_admission.new_session(tmp_path, 'fixture', 'codex', 'chosen-model', 'low')
    writing_records.bank(tmp_path, {"record": "writing-turn", "id": "WT-author",
        "session_id": session["id"], "project": "fixture", "request_id": "same-request",
        "text": "produce", "mode": "discuss"})

    with pytest.raises(ValueError, match="different conversation role"):
        turn_admission.start_turn(tmp_path, {"project": "fixture", "mode": "review",
            "text": "review", "request_id": "same-request"})


def test_fresh_review_turn_is_role_bound_and_uses_independent_prompt(tmp_path, monkeypatch):
    _import_project(tmp_path)
    prompts = []
    class _Reviewer:
        def __init__(self, cwd, provider, model, effort, native_id, event, mode,
                         project=None, logical_turn_id=None, **kwargs):
            self.event = event
        def run(self, prompt):
            prompts.append(prompt)
            return {"status": "completed", "text": "reviewed", "turn_id": "native-review"}
    monkeypatch.setattr(writing_provider, "WritingTurn", _Reviewer)

    started = turn_admission.start_turn(tmp_path, {"project": "fixture", "provider": "codex",
        "mode": "review", "text": "Review independently.", "request_id": "fresh-review"})
    job = turn_jobs._JOBS[started["turn_id"]]
    with job["condition"]:
        assert job["condition"].wait_for(lambda: job["done"], timeout=5)
    state = session_reads.session_state(tmp_path, started["session_id"])

    assert state["session"]["role"] == "review"
    assert state["turns"][0]["mode"] == "review"
    assert "independent reviewer in a fresh conversation" in prompts[0]


def test_review_tools_can_bank_findings_but_cannot_change_reviewed_artifacts(tmp_path):
    manuscript,_source=_import_project(tmp_path)
    before={path.relative_to(manuscript).as_posix():path.read_bytes()
            for path in manuscript.rglob('*') if path.is_file()}
    writing_records.bank(tmp_path,{'record':'writing-session','id':'WS-review','project':'fixture','provider':'codex','model':'fixture-only','role':'review'})
    writing_records.bank(tmp_path,{'record':'writing-turn','id':'WT-review','session_id':'WS-review','project':'fixture','mode':'review','text':'Review the qualification'})
    result=writing_tools.execute(tmp_path,'fixture','review','note',{
        'text':'The qualification needs checking.','kind':'note','scope':'passage',
        'anchor':{'file':'main.tex','line_start':3,'line_end':3}},
        turn_id='WT-review',requested_by='author')
    assert result['correction']['by']=='eigen:review'
    assert result['correction']['context_role']=='anchored-review'
    task=writing_tools.execute(tmp_path,'fixture','review','task',{
        'title':'Check qualification','goal':'Establish whether the stated qualification holds.'},
        turn_id='WT-review')
    assert task['origin']=='eigen:review'
    # Exercise the normal validated intake with a valid literal write, then
    # the actual closed review-role gate for every write verb. Empty payloads
    # are no longer valid tests of intake ordering/role admission.
    with pytest.raises(ValueError,match='Independent review'):
        writing_tools.execute(tmp_path,'fixture','review','store_artifact',{'path':'research/overwrite.md','scope':'project','before':None,'content':'forbidden','reason':'role-negative'},turn_id='WT-review')
    # M5 (2026-10-16): work_review is review-permitted beside note/note_status/task (reviews and follow-ups only)
    for operation in read_contract.WRITES-{'note','note_status','task','work_review'}:
        with pytest.raises(ValueError,match='Independent review'):
            operations._execute(tmp_path,'fixture','review',operation,{},turn_id='WT-review')
    rows=[json.loads(line) for line in (tmp_path/'contract/talk.jsonl').read_text().splitlines()]
    actions=[row for row in rows if row.get('record')=='writing-tool-action']
    assert {row['operation'] for row in actions}=={'note','task'}
    assert not (tmp_path/'writing_projects/fixture/research/overwrite.md').exists()
    after={path.relative_to(manuscript).as_posix():path.read_bytes()
           for path in manuscript.rglob('*') if path.is_file() and path.relative_to(manuscript).as_posix() in before}
    assert after==before
    context=authoring.build_context('fixture',{'files':['main.tex'],'line_start':3,'line_end':3},repo_root=tmp_path)
    assert result['correction']['id'] in context['consumed']['corrections']
    assert 'qualification needs checking' in context['prompt']


def test_relative_controller_root_is_normalised_before_provider_resume(tmp_path, monkeypatch):
    _import_project(tmp_path)
    seen = []
    class Provider:
        def __init__(self, cwd, *args, **kwargs): seen.append(cwd)
        def run(self, prompt): return {"status": "completed", "text": "done"}
    monkeypatch.setattr(writing_provider, "WritingTurn", Provider)
    relative = Path(os.path.relpath(tmp_path, Path.cwd()))
    started = turn_admission.start_turn(relative, {"project": "fixture", "provider": "codex",
        "mode": "discuss", "text": "Use this session."})
    job = turn_jobs._JOBS[started["turn_id"]]
    with job["condition"]:
        assert job["condition"].wait_for(lambda: job["done"], timeout=5)
    assert seen == [tmp_path.resolve()]


def test_selected_work_turn_retains_consumed_ancestor_revisions(tmp_path, monkeypatch):
    _import_project(tmp_path)
    from laplace.work import project_work
    project_work.task('fixture', {'id':'WORK-parent','title':'Blueprint','goal':'Explain implemented behavior'}, tmp_path)
    project_work.task('fixture', {'id':'WORK-child','title':'Trace','goal':'Describe propagation','parent_work_id':'WORK-parent'}, tmp_path)
    expected=project_work.context('fixture','WORK-child',tmp_path)['work_basis']
    prompts=[]
    class Provider:
        def __init__(self,*args,**kwargs):pass
        def run(self,prompt):
            prompts.append(prompt)
            return {'status':'completed','text':'Observed fixture.','turn_id':'native-work-basis'}
    monkeypatch.setattr(writing_provider, 'WritingTurn',Provider)
    # The send acknowledges the CURRENT selected Work explicitly (M5 S3): its fresh detail guards travel with work_id.
    child=project_work.read('fixture',{'view':'detail','id':'WORK-child'},tmp_path)['task']
    guards={'expected_work_scope_revision':child['work_scope_revision'],'expected_dependency_revision':child['dependency_revision']}
    started=turn_admission.start_turn(tmp_path,{'project':'fixture','provider':'codex','mode':'work',
        'text':'Inspect selected work','work_id':'WORK-child',**guards})
    job=turn_jobs._JOBS[started['turn_id']]
    with job['condition']:assert job['condition'].wait_for(lambda:job['done'],timeout=5)
    action=project_work.read('fixture',{'view':'detail','id':'WORK-parent'},tmp_path)['allowed_actions']['task']
    project_work.task('fixture',{**action['payload'],'goal':'Explain observed and independently checked behavior'},tmp_path)
    # after the ancestor changed, the identical old guards no longer admit a send and nothing is delivered
    jobs=set(turn_jobs._JOBS)
    with pytest.raises(project_work.WorkConflict):
        turn_admission.start_turn(tmp_path,{'project':'fixture','provider':'codex','mode':'work',
            'text':'Inspect selected work again','work_id':'WORK-child',**guards})
    assert len(prompts)==1 and set(turn_jobs._JOBS)==jobs
    saved=session_reads.session_turn_detail(tmp_path,'fixture',started['turn_id'],'summary')['turn']
    assert saved['work_basis']==expected
    assert project_work.context('fixture','WORK-child',tmp_path)['work_basis']!=expected
    assert 'Explain implemented behavior' in prompts[0]
    assert 'Explain observed and independently checked behavior' not in prompts[0]
