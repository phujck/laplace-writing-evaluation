from pathlib import Path

import pytest

from laplace.web import authoring as authoring_surface
from laplace.manuscript import manuscript_proposals, review_surface
from laplace.manuscript import source_application
from laplace.writing import session_reads
from laplace.manuscript import proposal_currentness
from laplace.writing import records as writing_records
from laplace.writing.records import _fold as records_fold
from laplace.writing import turn_jobs
from laplace.manuscript import source_effects
from laplace.core import checkout
from test_writing_controller import _import_project, _seed_revision, _bind_rewrite_fixture, _apply_fixture


@pytest.fixture(autouse=True)
def clear_state():
    records_fold._CACHE.clear()
    turn_jobs._JOBS.clear()
    yield
    records_fold._CACHE.clear()
    turn_jobs._JOBS.clear()


def _decide_fixture(root,project,payload):
    turn=session_reads._records(root)['turns'].get(payload.get('turn_id'))
    if turn and not turn_jobs._JOBS.get(turn['id']) and not payload.get('proposal_version') and not payload.get('expected'):
        payload={**payload,'proposal_version':manuscript_proposals.proposal_version(turn)[0]}
    return manuscript_proposals.decide(root,project,payload)


def fixture(root: Path):
    manuscript, _ = _import_project(root, files={"main.tex":
        "\\documentclass{article}\n\\begin{document}\nFirst paragraph.\n\nSecond paragraph.\n\\end{document}\n"})
    edits = [
        {"file": "main.tex", "line_start": 3, "line_end": 3, "before": "First paragraph.",
         "after": "First revised paragraph.\n\nAn added explanation.", "reason": "Explain the premise."},
        {"file": "main.tex", "line_start": 5, "line_end": 5, "before": "Second paragraph.",
         "after": "Second revised paragraph.", "reason": "Clarify the conclusion."},
    ]
    turn = _seed_revision(root, "fixture", edits, selection={"files": ["main.tex"]})
    return manuscript, turn, edits


def test_preview_is_renderable_and_makes_no_source_changes(tmp_path):
    manuscript, turn, edits = fixture(tmp_path)
    before = (manuscript / "main.tex").read_bytes()
    preview = manuscript_proposals.preview(tmp_path, "fixture", turn)
    assert preview["remaining"] == 2
    assert all(edit["status"] == "pending" for edit in preview["edits"])
    assert preview["edits"][0]["after_blocks"][0]["kind"] == "para"
    assert (manuscript / "main.tex").read_bytes() == before


def test_selective_accept_relocates_next_hunk_and_is_idempotent(tmp_path, monkeypatch):
    manuscript, turn, edits = fixture(tmp_path)
    _bind_rewrite_fixture(monkeypatch, manuscript)
    first, second = [manuscript_proposals.edit_id(edit) for edit in edits]
    result = _decide_fixture(tmp_path, "fixture", {"turn_id": turn, "edit_id": first, "decision": "accept"})
    assert result["remaining"] == 1
    later = next(edit for edit in result["edits"] if edit["edit_id"] == second)
    assert later["status"] == "pending" and later["line_start"] == 7
    assert session_reads.pending_proposals(tmp_path, "fixture")["count"] == 1
    result = _decide_fixture(tmp_path, "fixture", {"turn_id": turn, "edit_id": second, "decision": "accept"})
    assert result["remaining"] == 0
    assert "Second revised paragraph." in (manuscript / "main.tex").read_text()
    retry = _decide_fixture(tmp_path, "fixture", {"turn_id": turn, "edit_id": second, "decision": "accept"})
    assert retry["reused"]
    assert session_reads.pending_proposals(tmp_path, "fixture")["count"] == 0


def test_reject_is_persistent_without_source_write(tmp_path):
    manuscript, turn, edits = fixture(tmp_path)
    before = (manuscript / "main.tex").read_bytes()
    for edit in edits:
        _decide_fixture(tmp_path, "fixture", {"turn_id": turn,
            "edit_id": manuscript_proposals.edit_id(edit), "decision": "reject"})
    records_fold._CACHE.clear()
    assert session_reads.pending_proposals(tmp_path, "fixture")["count"] == 0
    assert (manuscript / "main.tex").read_bytes() == before


def test_changed_source_is_conflict_and_cannot_be_accepted(tmp_path, monkeypatch):
    manuscript, turn, edits = fixture(tmp_path)
    _bind_rewrite_fixture(monkeypatch, manuscript)
    path = manuscript / "main.tex"
    path.write_text(path.read_text().replace("First paragraph.", "Author has rewritten this."))
    preview = manuscript_proposals.preview(tmp_path, "fixture", turn)
    assert preview["edits"][0]["status"] == "conflict"
    with pytest.raises(ValueError, match="source changed outside|source-revision-changed|original passage has changed"):
        _decide_fixture(tmp_path, "fixture", {"turn_id": turn,
            "edit_id": manuscript_proposals.edit_id(edits[0]), "decision": "accept"})
    assert "Author has rewritten this." in path.read_text()


def test_same_turn_direct_application_is_terminal_and_never_reopens_conflict(tmp_path,monkeypatch):
    manuscript,turn,edits=fixture(tmp_path);_bind_rewrite_fixture(monkeypatch,manuscript)
    applied=_apply_fixture(tmp_path,{"turn_id":turn})
    assert applied["complete"] is True
    # A later source movement cannot turn an accepted proposal back into a
    # replace-current action; the accepted snapshot remains inspectable.
    path=manuscript/"main.tex";path.write_text(path.read_text()+"\nLater unrelated text.\n")
    preview=manuscript_proposals.preview(tmp_path,"fixture",turn)
    assert preview["remaining"]==0
    assert preview["proposal_state"]=="applied" and preview["read_only"] is False
    assert [row["status"] for row in preview["edits"]]==["accepted","accepted"]
    assert preview["edits"][0]["after"]==edits[0]["after"]
    before_apps=len(source_effects.applications(session_reads._records(tmp_path)["turns"][turn]))
    result=_decide_fixture(tmp_path,"fixture",{
        "turn_id":turn,"edit_id":preview["edits"][0]["edit_id"],"decision":"replace-current"})
    assert result["reused"] and result["terminal_state"]=="applied"
    assert len(source_effects.applications(session_reads._records(tmp_path)["turns"][turn]))==before_apps


@pytest.mark.parametrize('state',['restored','third-state','inverse','new-science-current-b','cross-span'])
def test_historical_application_never_settles_fresh_same_text_basis(tmp_path,monkeypatch,state):
    import json
    from laplace.pipeline import authoring
    manuscript,old_turn,edits=fixture(tmp_path);_bind_rewrite_fixture(monkeypatch,manuscript)
    path=manuscript/'main.tex';initial=path.read_text()
    old_version=manuscript_proposals.proposal_version(session_reads._records(tmp_path)['turns'][old_turn])[0]
    applied=_apply_fixture(tmp_path,{'turn_id':old_turn})
    fresh_edits=json.loads(json.dumps(edits))
    if state in {'restored','inverse'}:path.write_text(initial)
    elif state=='third-state':path.write_text(initial.replace('First paragraph.','A third source state.'))
    elif state=='cross-span':
        text=initial.replace('\\end{document}','First paragraph.\n\\end{document}')
        path.write_text(text);line=next(i for i,row in reversed(list(enumerate(text.splitlines(),1))) if row=='First paragraph.')
        fresh_edits=[{**fresh_edits[0],'line_start':line,'line_end':line}]
        fresh_edits[0].pop('source_anchor',None)
    else:
        authoring.bank_correction('fixture',{'text':'A different scientific requirement.','kind':'factual',
            'scope':'project','by':'author'},repo_root=tmp_path)
    if state=='inverse':
        source=session_reads._records(tmp_path)['turns'][old_turn]['document']
        writing_records.bank(tmp_path,{'record':'writing-turn','id':'WT-inverse','session_id':'WS-inverse',
            'project':'fixture','document':source})
        inverse=[{**edit,'before':edit['after'],'after':edit['before']} for edit in edits]
        writing_records.bank(tmp_path,{'record':'writing-application','id':'WA-inverse','turn_id':'WT-inverse',
            'project':'fixture','complete':True,'edits':inverse})
    fresh=_seed_revision(tmp_path,'fixture',fresh_edits,selection={'files':['main.tex']},suffix='fresh')
    records=session_reads._records(tmp_path);new=records['turns'][fresh]
    assert manuscript_proposals.proposal_version(new)[0]!=old_version
    view=proposal_currentness.proposal_view(new,records=records)
    assert view['proposal_state']=='ready' and len(view['proposal']['edits'])==len(fresh_edits)
    preview=manuscript_proposals.preview(tmp_path,'fixture',fresh)
    assert preview['remaining']==len(fresh_edits)
    assert all(row['status'] in {'pending','conflict'} for row in preview['edits'])
    assert manuscript_proposals.preview(tmp_path,'fixture',old_turn,old_version)['proposal_state']=='applied'
    if state in {'third-state','new-science-current-b'}:
        before=path.read_bytes()
        assert 'accept' not in preview['edits'][0]['allowed_actions']
        with pytest.raises(ValueError):_decide_fixture(tmp_path,'fixture',{'turn_id':fresh,
            'edit_id':preview['edits'][0]['edit_id'],'decision':'accept'})
        assert path.read_bytes()==before
    elif state=='restored':
        assert all('accept' in row['allowed_actions'] for row in preview['edits'])
        accepted=_decide_fixture(tmp_path,'fixture',{'turn_id':fresh,
            'edit_id':preview['edits'][0]['edit_id'],'decision':'accept'})
        assert accepted['application']['id']!=applied['id']


def test_historical_effect_match_remains_visible_until_explicit_supersession(tmp_path):
    manuscript, old_turn, edits = fixture(tmp_path)
    from laplace.manuscript import manuscript_source
    source = manuscript_source.resolve("fixture", repo_root=tmp_path)
    later_turn = "WT-later-effect"
    writing_records.bank(tmp_path, {"record": "writing-session", "id": "WS-later-effect",
                                       "project": "fixture", "provider": "codex", "model": "m", "effort": "medium"})
    writing_records.bank(tmp_path, {"record": "writing-turn", "id": later_turn, "session_id": "WS-later-effect",
                                       "project": "fixture", "document": source})
    effect = records_fold._proposal_effect_digest({"edits": edits})
    writing_records.bank(tmp_path, {"record": "writing-application", "id": "WA-later-effect",
                                       "turn_id": later_turn, "project": "fixture", "complete": True,
                                       "edit_sha256": effect, "edits": edits})
    # A later source addition must not make a fulfilled old proposal appear safe to
    # replace over the new work.
    path = manuscript / "main.tex"
    path.write_text(path.read_text(encoding="utf-8") + "\n% figures retained\n", encoding="utf-8")
    pending = session_reads.pending_proposals(tmp_path, "fixture")
    assert pending["count"] == 1
    preview = manuscript_proposals.preview(tmp_path, "fixture", old_turn)
    assert preview["remaining"] == 2
    assert preview["historical_application_matches"] == [{"id": "WA-later-effect", "turn_id": later_turn,
                                               "project": "fixture", "origin": None}]
    assert all(row["status"] == "conflict" for row in preview["edits"])
    with pytest.raises(ValueError, match="changed|source|basis|passage"):
        _decide_fixture(tmp_path, "fixture", {"turn_id": old_turn,
            "edit_id": manuscript_proposals.edit_id(edits[0]), "decision": "replace-current", "review_token": "stale"})
    assert "% figures retained" in path.read_text(encoding="utf-8")
    before=path.read_bytes()
    for row in preview['edits']:
        result=_decide_fixture(tmp_path,'fixture',{'turn_id':old_turn,'edit_id':row['edit_id'],
            'decision':'supersede','application_id':'WA-later-effect'})
    assert result['remaining']==0 and result['proposal_state']=='superseded'
    assert session_reads.pending_proposals(tmp_path,'fixture')['count']==0
    assert path.read_bytes()==before


def test_cross_turn_matches_preserve_all_authored_edits_until_explicit_supersession(tmp_path):
    _manuscript,old_turn,edits=fixture(tmp_path)
    from laplace.manuscript import manuscript_source
    source=manuscript_source.resolve("fixture",repo_root=tmp_path);later="WT-refinement"
    writing_records.bank(tmp_path,{"record":"writing-session","id":"WS-refinement",
        "project":"fixture","provider":"codex","model":"m","effort":"medium"})
    writing_records.bank(tmp_path,{"record":"writing-turn","id":later,
        "session_id":"WS-refinement","project":"fixture","document":source})
    refined={**edits[1],"after":"Second paragraph with the author’s precision."}
    writing_records.bank(tmp_path,{"record":"writing-application","id":"WA-refinement",
        "turn_id":later,"project":"fixture","complete":True,"edits":[edits[0],refined]})

    records=session_reads._records(tmp_path)
    view=proposal_currentness.proposal_view(records["turns"][old_turn],records=records)
    assert view["proposal_state"]=="ready" and view["proposal"]["edits"]==edits
    preview=manuscript_proposals.preview(tmp_path,"fixture",old_turn)
    assert [row["status"] for row in preview["edits"]]==["pending","pending"]
    assert preview["edits"][0]["historical_application_matches"][0]['turn_id']==later
    assert preview["edits"][1]["after"]==edits[1]["after"]
    assert preview["edits"][1]["next_decision"]=={
        "decision":"supersede","application_id":"WA-refinement"}
    before_apps=sum(len(source_effects.applications(turn))
                    for turn in session_reads._records(tmp_path)["turns"].values())
    with pytest.raises(ValueError,match="review|changed|fresh"):
        _decide_fixture(tmp_path,"fixture",{"turn_id":old_turn,
            "edit_id":manuscript_proposals.edit_id(edits[1]),"decision":"replace-current",
            "review_token":"stale"})
    assert sum(len(source_effects.applications(turn))
               for turn in session_reads._records(tmp_path)["turns"].values())==before_apps
    result=_decide_fixture(tmp_path,"fixture",{"turn_id":old_turn,
        "edit_id":manuscript_proposals.edit_id(edits[1]),"decision":"supersede",
        "application_id":"WA-refinement"})
    assert result["decision"]["decision"]=="superseded"
    assert result["remaining"]==1 and result["edits"][1]["status"]=="superseded"
    assert result["edits"][1]["application_turn_id"]==later
    assert result["edits"][1]["after"]==refined["after"]
    assert session_reads.pending_proposals(tmp_path,"fixture")["count"]==1
    final=_decide_fixture(tmp_path,'fixture',{'turn_id':old_turn,'edit_id':manuscript_proposals.edit_id(edits[0]),
        'decision':'supersede','application_id':'WA-refinement'})
    assert final['remaining']==0 and session_reads.pending_proposals(tmp_path,'fixture')['count']==0


def test_native_whole_proposal_supersession_records_exact_later_lineage_without_source_write(tmp_path):
    manuscript,old_turn,edits=fixture(tmp_path)
    from laplace.manuscript import manuscript_source
    from laplace.native import tools as writing_tools
    source=manuscript_source.resolve("fixture",repo_root=tmp_path);later="WT-native-refinement"
    writing_records.bank(tmp_path,{"record":"writing-session","id":"WS-native-refinement",
        "project":"fixture","provider":"codex","model":"m","effort":"high"})
    writing_records.bank(tmp_path,{"record":"writing-turn","id":later,
        "session_id":"WS-native-refinement","project":"fixture","document":source})
    refined={**edits[1],"after":"Second paragraph with the accepted precision."}
    writing_records.bank(tmp_path,{"record":"writing-application","id":"WA-native-refinement",
        "turn_id":later,"project":"fixture","complete":True,"edits":[edits[0],refined]})
    # Preserve a prior stale decision: the newer lineage row must supersede it,
    # never delete it or replay its source replacement.
    writing_records.bank(tmp_path,{"record":"writing-proposal-decision","id":"DECISION-stale",
        "project":"fixture","turn_id":old_turn,"edit_id":manuscript_proposals.edit_id(edits[1]),
        "decision":"accepted","resolution":"replace-current","by":"author"})
    before=(manuscript/"main.tex").read_bytes()
    payload={"target_turn_id":old_turn,"application_id":"WA-native-refinement",
             "reason":"The later accepted revision replaces this complete older intent."}
    result=writing_tools.execute(tmp_path,"fixture","work","proposal_supersede",payload,
                                 turn_id=later)
    assert result["status"]=="SUPERSEDED" and result["remaining"]==0
    assert (result["exact_effects"],result["refined_effects"])==(1,1)
    assert result["application_turn_id"]==later and len(result["decision_ids"])==2
    assert (manuscript/"main.tex").read_bytes()==before
    target=session_reads._records(tmp_path)["turns"][old_turn]
    assert any(row["id"]=="DECISION-stale" for row in target["proposal_decisions"])
    assert all(row["decision"]=="superseded" and row["application_id"]=="WA-native-refinement"
               for row in manuscript_proposals.decisions(target).values())
    reused=writing_tools.execute(tmp_path,"fixture","work","proposal_supersede",payload,
                                 turn_id=later)
    assert reused["reused"] is True and reused["remaining"]==0


def test_native_whole_proposal_supersession_refuses_partial_application(tmp_path):
    _manuscript,old_turn,edits=fixture(tmp_path)
    from laplace.manuscript import manuscript_source
    from laplace.native import tools as writing_tools
    source=manuscript_source.resolve("fixture",repo_root=tmp_path);later="WT-partial-lineage"
    writing_records.bank(tmp_path,{"record":"writing-session","id":"WS-partial-lineage",
        "project":"fixture","provider":"codex","model":"m","effort":"high"})
    writing_records.bank(tmp_path,{"record":"writing-turn","id":later,
        "session_id":"WS-partial-lineage","project":"fixture","document":source})
    writing_records.bank(tmp_path,{"record":"writing-application","id":"WA-partial-lineage",
        "turn_id":later,"project":"fixture","complete":True,"edits":[edits[0]]})
    with pytest.raises(ValueError,match="does not cover every proposal edit"):
        writing_tools.execute(tmp_path,"fixture","work","proposal_supersede",{
            "target_turn_id":old_turn,"application_id":"WA-partial-lineage",
            "reason":"Incomplete later application."},turn_id=later)
    assert manuscript_proposals.decisions(session_reads._records(tmp_path)["turns"][old_turn])=={}


def test_cross_turn_same_text_at_different_span_does_not_auto_fulfill(tmp_path):
    manuscript,_=_import_project(tmp_path,files={"main.tex":
        "\\documentclass{article}\n\\begin{document}\nSame.\n\nSame.\n\\end{document}\n"})
    edit={"file":"main.tex","line_start":3,"line_end":3,"before":"Same.","after":"Changed."}
    old=_seed_revision(tmp_path,"fixture",[edit],selection={"files":["main.tex"]},suffix="same-old")
    from laplace.manuscript import manuscript_source
    source=manuscript_source.resolve("fixture",repo_root=tmp_path);later="WT-same-later"
    writing_records.bank(tmp_path,{"record":"writing-session","id":"WS-same-later",
        "project":"fixture","provider":"codex","model":"m","effort":"low"})
    writing_records.bank(tmp_path,{"record":"writing-turn","id":later,"session_id":"WS-same-later",
        "project":"fixture","document":source})
    writing_records.bank(tmp_path,{"record":"writing-application","id":"WA-same-later",
        "turn_id":later,"project":"fixture","complete":True,
        "edits":[{**{k:v for k,v in edit.items() if k!="source_anchor"},"line_start":5,"line_end":5}]})
    records=session_reads._records(tmp_path)
    view=proposal_currentness.proposal_view(records["turns"][old],records=records)
    assert view["proposal_state"]=="ready" and len(view["proposal"]["edits"])==1


def test_cross_turn_partial_or_other_edition_application_does_not_hide_proposal(tmp_path):
    _manuscript, old_turn, edits = fixture(tmp_path)
    from laplace.manuscript import manuscript_source
    source = manuscript_source.resolve("fixture", repo_root=tmp_path)
    effect = records_fold._proposal_effect_digest({"edits": edits})
    for suffix, complete, edition in (("partial", False, source.get("edition")), ("edition", True, "other")):
        turn = "WT-" + suffix
        writing_records.bank(tmp_path, {"record": "writing-session", "id": "WS-" + suffix,
                                           "project": "fixture", "provider": "codex", "model": "m", "effort": "medium"})
        writing_records.bank(tmp_path, {"record": "writing-turn", "id": turn, "session_id": "WS-" + suffix,
                                           "project": "fixture", "document": {**source, "edition": edition}})
        writing_records.bank(tmp_path, {"record": "writing-application", "id": "WA-" + suffix,
                                           "turn_id": turn, "project": "fixture", "complete": complete,
                                           "edit_sha256": effect, "edits": edits})
    assert session_reads.pending_proposals(tmp_path, "fixture")["count"] == 1


def test_foreign_project_cannot_inspect_or_decide(tmp_path):
    _, turn, edits = fixture(tmp_path)
    with pytest.raises(ValueError, match="selected project"):
        manuscript_proposals.preview(tmp_path, "another-project", turn)
    with pytest.raises(ValueError, match="selected project"):
        _decide_fixture(tmp_path, "another-project", {"turn_id": turn,
            "edit_id": manuscript_proposals.edit_id(edits[0]), "decision": "accept"})


def test_conflicted_historical_location_is_inspection_only(tmp_path,monkeypatch):
    manuscript,turn,edits=fixture(tmp_path)
    calls=_bind_rewrite_fixture(monkeypatch,manuscript)
    path=manuscript/'main.tex'
    path.write_text(path.read_text().replace('First paragraph.','Author current version.'))
    before=path.read_bytes()
    row=manuscript_proposals.preview(tmp_path,'fixture',turn)['edits'][0]
    assert row['status']=='conflict' and not row.get('review_token')
    assert row['current_mapping']=='unproven-historical-location'
    with pytest.raises(ValueError,match='source changed outside|changed after you opened'):
        _decide_fixture(tmp_path,'fixture',{'turn_id':turn,
            'edit_id':row['edit_id'],'decision':'replace-current','review_token':'cached-token'})
    assert path.read_bytes()==before and not calls


def test_conflict_resolution_refuses_source_changed_after_comparison(tmp_path,monkeypatch):
    manuscript,turn,edits=fixture(tmp_path)
    _bind_rewrite_fixture(monkeypatch,manuscript)
    path=manuscript/'main.tex'
    row=manuscript_proposals.preview(tmp_path,'fixture',turn)['edits'][0]
    path.write_text(path.read_text().replace('First paragraph.','Current.'))
    path.write_text(path.read_text().replace('Current.','Latest typing.'))
    with pytest.raises(ValueError,match='source changed outside|changed after you opened'):
        _decide_fixture(tmp_path,'fixture',{'turn_id':turn,
            'edit_id':row['edit_id'],'decision':'replace-current','review_token':row['review_token']})
    assert 'Latest typing.' in path.read_text()


def test_conflict_can_save_authors_combined_version_or_keep_current(tmp_path,monkeypatch):
    manuscript,turn,edits=fixture(tmp_path)
    _bind_rewrite_fixture(monkeypatch,manuscript)
    path=manuscript/'main.tex'
    path.write_text(path.read_text().replace('First paragraph.','Current.').replace('Second paragraph.','Keep this.'))
    first,second=manuscript_proposals.preview(tmp_path,'fixture',turn)['edits']
    assert not first.get('review_token')
    with pytest.raises(ValueError,match='source changed outside|changed after you opened'):
        _decide_fixture(tmp_path,'fixture',{'turn_id':turn,'edit_id':first['edit_id'],
            'decision':'merge','review_token':'cached-token','merged_after':'Combined explanation.'})
    _decide_fixture(tmp_path,'fixture',{'turn_id':turn,'edit_id':first['edit_id'],'decision':'keep-current'})
    _decide_fixture(tmp_path,'fixture',{'turn_id':turn,'edit_id':second['edit_id'],
        'decision':'keep-current'})
    assert 'Current.' in path.read_text() and 'Keep this.' in path.read_text()
    assert manuscript_proposals.preview(tmp_path,'fixture',turn)['remaining']==0


def test_saved_suggestion_does_not_jump_to_surviving_duplicate(tmp_path,monkeypatch):
    manuscript,_=_import_project(tmp_path,files={'main.tex':
        '\\documentclass{article}\n\\begin{document}\nSame sentence.\n\nSame sentence.\n\\end{document}\n'})
    edit={'file':'main.tex','line_start':3,'line_end':3,'before':'Same sentence.',
          'after':'Replacement.','reason':'Rewrite the first occurrence.'}
    turn=_seed_revision(tmp_path,'fixture',[edit],selection={'files':['main.tex']})
    _bind_rewrite_fixture(monkeypatch,manuscript)
    path=manuscript/'main.tex'
    path.write_text(path.read_text().replace('Same sentence.','Author changed the first.',1))
    row=manuscript_proposals.preview(tmp_path,'fixture',turn)['edits'][0]
    assert row['status']=='conflict'
    assert not row.get('review_token') and row['current_mapping']=='unproven-historical-location'
    with pytest.raises(ValueError,match='source changed outside|source-revision-changed|original passage has changed'):
        _decide_fixture(tmp_path,'fixture',{'turn_id':turn,'edit_id':row['edit_id'],'decision':'accept'})
    assert path.read_text().count('Same sentence.')==1


def test_source_context_anchor_allows_unrelated_shift_but_not_occurrence_loss(tmp_path):
    from laplace.manuscript import proposal_preflight
    manuscript,turn,edits=fixture(tmp_path)
    original=session_reads._records(tmp_path)['turns'][turn]
    checked=proposal_preflight.preflight(tmp_path,'fixture',original,{'edits':[edits[1]]})
    anchored=checked['proposal']['edits'][0]
    assert anchored['source_anchor']['unique']
    path=manuscript/'main.tex';path.write_text('% Added preamble comment\n'+path.read_text())
    after=proposal_preflight.preflight(tmp_path,'fixture',original,{'edits':[anchored]},relocate_unanchored=False)
    assert after['valid'] and after['proposal']['edits'][0]['line_start']==6
    path.write_text(path.read_text().replace('Second paragraph.','Changed.'))
    assert not proposal_preflight.preflight(tmp_path,'fixture',original,{'edits':[anchored]},relocate_unanchored=False)['valid']


def test_same_path_different_edition_cannot_be_accepted_or_force_replaced(tmp_path):
    import json
    manuscript,turn,edits=fixture(tmp_path)
    registry=tmp_path/'registry_projects.json'
    data=json.loads(registry.read_text())
    data['projects'][0]['manifest']['document']['edition']='different-edition'
    registry.write_text(json.dumps(data))
    row=manuscript_proposals.preview(tmp_path,'fixture',turn)['edits'][0]
    assert row['status']=='conflict' and 'different manuscript version' in row['error']
    assert not row.get('review_token')


def active_fixture(root):
    from laplace.manuscript import manuscript_source
    manuscript, _ = _import_project(root, files={'main.tex':
        '\\documentclass{article}\n\\begin{document}\nFirst paragraph.\n\nSecond paragraph.\n\\end{document}\n'})
    edits=[{'file':'main.tex','line_start':3,'line_end':3,'before':'First paragraph.',
            'after':'First reviewed paragraph.','reason':'A complete saved atomic change.'}]
    from laplace.pipeline import authoring
    context=authoring.build_context('fixture',{'files':['main.tex']},repo_root=root)
    session,turn='WS-active-proposal','WT-active-proposal'
    writing_records.bank(root,{'record':'writing-session','id':session,'project':'fixture',
        'provider':'codex','model':'fixture','effort':'medium'})
    writing_records.bank(root,{'record':'writing-turn','id':turn,'session_id':session,
        'project':'fixture','text':'Develop the project.','mode':'work','selection':{'files':['main.tex']},
        'document':manuscript_source.resolve('fixture',repo_root=root),
        'context_id':context['context_id'],'dependencies':context['dependencies']})
    writing_records.bank(root,{'record':'writing-proposal','id':'PROP-complete-unit',
        'turn_id':turn,'project':'fixture','proposal':{'answer':'Saved unit.','edits':edits}})
    turn_jobs._JOBS[turn]={'id':turn,'session_id':session,'done':False,'text':'Now developing the next chapter.','provider':object()}
    return manuscript,turn,edits


def test_active_saved_version_accepts_atomically_without_stopping_the_continuing_turn(tmp_path,monkeypatch):
    manuscript,turn,edits=active_fixture(tmp_path)
    _bind_rewrite_fixture(monkeypatch,manuscript)
    job=dict(turn_jobs._JOBS[turn]);before=manuscript_proposals.preview(tmp_path,'fixture',turn)
    assert before['turn_active'] and before['reviewable'] and before['proposal_version'].startswith('sha256:')
    assert proposal_currentness.proposal_view(session_reads._records(tmp_path)['turns'][turn])['proposal_state']=='ready'
    payload={'turn_id':turn,'edit_id':before['edits'][0]['edit_id'],'decision':'accept','proposal_version':before['proposal_version']}
    accepted=_decide_fixture(tmp_path,'fixture',payload)
    assert accepted['application']['complete'] and accepted['remaining']==0
    assert 'First reviewed paragraph.' in (manuscript/'main.tex').read_text()
    assert turn_jobs._JOBS[turn]==job
    assert accepted['decision']['proposal_version']==before['proposal_version']
    assert accepted['application']['context_rebase']['advanced'] is False
    assert not session_reads._records(tmp_path)['turns'][turn].get('consumed')
    assert not session_reads._records(tmp_path)['turns'][turn].get('tool_reads')
    retried=_decide_fixture(tmp_path,'fixture',payload)
    assert retried['reused'] and retried['application']['id']==accepted['application']['id']
    assert len(source_effects.applications(session_reads._records(tmp_path)['turns'][turn]))==1


def test_active_decisions_require_and_select_the_exact_reviewed_version(tmp_path,monkeypatch):
    manuscript,turn,edits=active_fixture(tmp_path)
    _bind_rewrite_fixture(monkeypatch,manuscript)
    original=(manuscript/'main.tex').read_bytes();preview=manuscript_proposals.preview(tmp_path,'fixture',turn)
    payload={'turn_id':turn,'edit_id':preview['edits'][0]['edit_id'],'decision':'accept'}
    with pytest.raises(ValueError,match='Refresh the saved suggestion'):
        _decide_fixture(tmp_path,'fixture',payload)
    # Even a changed scientific reason with the same source effects is a new
    # immutable review version; a matching edit_id alone is insufficient.
    writing_records.bank(tmp_path,{'record':'writing-proposal','id':'PROP-new-version',
        'project':'fixture','turn_id':turn,'proposal':{'answer':'Reconsidered.',
            'edits':[{**edits[0],'reason':'The scientific basis has changed.'}]}})
    with pytest.raises(ValueError,match='version is unavailable'):
        _decide_fixture(tmp_path,'fixture',{**payload,'proposal_version':'sha256:'+'0'*64})
    assert (manuscript/'main.tex').read_bytes()==original
    selected=_decide_fixture(tmp_path,'fixture',{**payload,'proposal_version':preview['proposal_version']})
    assert selected['decision']['proposal_version']==preview['proposal_version']
    assert edits[0]['after'] in (manuscript/'main.tex').read_text()


def test_active_review_keeps_source_guard_and_rejection_never_writes_source(tmp_path,monkeypatch):
    manuscript,turn,_=active_fixture(tmp_path)
    _bind_rewrite_fixture(monkeypatch,manuscript)
    preview=manuscript_proposals.preview(tmp_path,'fixture',turn)
    path=manuscript/'main.tex';path.write_text(path.read_text().replace('First paragraph.','Author typing changed this.'))
    current=path.read_bytes();payload={'turn_id':turn,'edit_id':preview['edits'][0]['edit_id'],'proposal_version':preview['proposal_version']}
    with pytest.raises(ValueError,match='source changed outside|source-revision-changed|original passage has changed'):
        _decide_fixture(tmp_path,'fixture',{**payload,'decision':'accept'})
    rejected=_decide_fixture(tmp_path,'fixture',{**payload,'decision':'reject'})
    assert rejected['decision']['decision']=='rejected' and path.read_bytes()==current
    assert turn_jobs._JOBS[turn]['done'] is False


@pytest.mark.parametrize('publication', ['writing-proposal','writing-reply'])
def test_proposal_and_final_reply_publication_cannot_race_inside_acceptance(tmp_path,monkeypatch,publication):
    import concurrent.futures
    import threading
    manuscript,turn,_=active_fixture(tmp_path)
    _bind_rewrite_fixture(monkeypatch,manuscript)
    preview=manuscript_proposals.preview(tmp_path,'fixture',turn)
    entered,release,started,published=(threading.Event() for _ in range(4))
    apply=source_application._apply_proposal_locked
    def paused(*args,**kwargs):
        entered.set()
        assert release.wait(5), 'test did not release the guarded apply'
        return apply(*args,**kwargs)
    monkeypatch.setattr(source_application,'_apply_proposal_locked',paused)
    second={'answer':'Next atomic unit.','edits':[{'file':'main.tex','line_start':5,'line_end':5,
        'before':'Second paragraph.','after':'Second proposed paragraph.','reason':'Next unit.'}]}
    def publish():
        started.set()
        writing_records.bank(tmp_path,{'record':publication,'id':'NEXT-version','turn_id':turn,
            'session_id':'WS-active-proposal','project':'fixture','proposal':second})
        published.set()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as workers:
        accepted=workers.submit(manuscript_proposals.decide,tmp_path,'fixture',{
            'turn_id':turn,'edit_id':preview['edits'][0]['edit_id'],'decision':'accept',
            'proposal_version':preview['proposal_version']})
        assert entered.wait(5)
        publishing=workers.submit(publish)
        try:
            assert started.wait(5)
            assert not published.wait(.2), 'a new proposal version escaped the apply lock'
        finally:
            release.set()
        result=accepted.result(timeout=10);publishing.result(timeout=10)
    assert result['application']['complete']
    text=(manuscript/'main.tex').read_text();assert 'First reviewed paragraph.' in text
    assert 'Second paragraph.' in text and 'Second proposed paragraph.' not in text
    latest=manuscript_proposals.preview(tmp_path,'fixture',turn)
    assert latest['proposal_version']!=preview['proposal_version'] and latest['remaining']==1
    assert proposal_currentness.proposal_view(session_reads._records(tmp_path)['turns'][turn])['proposal_state']=='ready'
    assert turn_jobs._JOBS[turn]['done'] is False


def test_active_acceptance_refuses_a_source_write_racing_the_final_exact_rewrite(tmp_path,monkeypatch):
    manuscript,turn,_=active_fixture(tmp_path)
    _bind_rewrite_fixture(monkeypatch,manuscript)
    preview=manuscript_proposals.preview(tmp_path,'fixture',turn)
    path=manuscript/'main.tex';adjudicate=review_surface.adjudicate;changed=False
    def raced(*args,**kwargs):
        nonlocal changed
        if not changed:
            changed=True
            path.write_text(path.read_text().replace('First paragraph.','Concurrent author text.'))
        return adjudicate(*args,**kwargs)
    monkeypatch.setattr(review_surface,'adjudicate',raced)
    result=_decide_fixture(tmp_path,'fixture',{'turn_id':turn,
        'edit_id':preview['edits'][0]['edit_id'],'decision':'accept',
        'proposal_version':preview['proposal_version']})
    assert result['reviewable'] is False and not result['application']['complete']
    assert result['application']['status']=='SOURCE_INCOMPLETE'
    assert 'decision' not in result and 'Inspect' in result['warning']
    assert 'Concurrent author text.' in path.read_text()
    assert 'First reviewed paragraph.' not in path.read_text()
    assert not session_reads._records(tmp_path)['turns'][turn].get('proposal_decisions')
    assert turn_jobs._JOBS[turn]['done'] is False


def test_http_preview_and_decision_use_the_sealed_version_for_an_active_turn(tmp_path,monkeypatch):
    import json
    manuscript,turn,_=active_fixture(tmp_path)
    _bind_rewrite_fixture(monkeypatch,manuscript)
    monkeypatch.setattr(checkout, 'repo_root',lambda:tmp_path)
    status,_,raw=authoring_surface.handle('/authoring/proposal-preview',{
        'project':['fixture'],'turn_id':[turn]},'GET',b'')
    preview=json.loads(raw);assert status==200 and preview['reviewable']
    payload={'project':'fixture','turn_id':turn,'edit_id':preview['edits'][0]['edit_id'],
             'decision':'accept','proposal_version':preview['proposal_version']}
    status,_,raw=authoring_surface.handle('/authoring/proposal-decision',{},'POST',json.dumps(payload).encode())
    result=json.loads(raw);assert status==200,result
    assert result['application']['complete'] and result['decision']['proposal_version']==payload['proposal_version']
    assert turn_jobs._JOBS[turn]['done'] is False


def _root_title_candidate(tmp_path,*,consulted_evidence=False):
    import json
    from laplace.native import tools as writing_tools
    from laplace.projects import artifacts as writing_artifacts
    from laplace.pipeline import authoring
    root_text="\\documentclass{article}\n\\title{Original title}\n\\hypersetup{pdftitle={Original title}}\n\\begin{document}\n\\input{chapter}\n\\end{document}\n"
    md,_=_import_project(tmp_path,files={'main.tex':root_text,'chapter.tex':'Body evidence.\n'})
    selection={'file':'main.tex','line_start':2,'line_end':3}
    context=authoring.build_context('fixture',selection,repo_root=tmp_path)
    assert context['dependencies']['source_dependencies']==[]
    assert context['dependencies']['source_revision']
    changes=[{'file':'main.tex','line_start':n,'line_end':n,'before':before,'after':after,'reason':'Update title.'}
        for n,before,after in [(2,'\\title{Original title}','\\title{New title}'),
            (3,'\\hypersetup{pdftitle={Original title}}','\\hypersetup{pdftitle={New title}}')]]
    tid=_seed_revision(tmp_path,'fixture',changes,selection=selection,context=context,suffix='root-aggregate')
    writing_tools.execute(tmp_path,'fixture','revise','source',{'files':['main.tex']},turn_id=tid)
    if consulted_evidence:
        artifact=writing_artifacts.project_root(tmp_path,'fixture')/'evidence.txt'
        artifact.write_text('Retained scientific premise.')
        writing_tools.execute(tmp_path,'fixture','revise','read_artifact',{'path':'evidence.txt','scope':'project'},turn_id=tid)
    candidate={'answer':'Exact title and PDF title edits.','edits':changes}
    writing_records.bank(tmp_path,{'record':'writing-proposal','id':'PROP-root-aggregate','turn_id':tid,
        'project':'fixture','proposal':candidate})
    version=manuscript_proposals.preview(tmp_path,'fixture',tid,records_fold._proposal_digest(candidate))['proposal_version']
    basis=session_reads._records(tmp_path)['turns'][tid]['proposal_bases'][version]
    assert basis['dependencies']['source_dependencies']==[]
    before=json.dumps(basis,sort_keys=True)
    return md,tid,version,before,root_text


@pytest.mark.parametrize('drift',[None,'external-root','included-source','correction','author-refinement','consulted-evidence','other-edition','undo'])
def test_modern_root_title_siblings_preserve_aggregate_context_and_consumed_reads(tmp_path,monkeypatch,drift):
    import json
    from laplace.pipeline import authoring
    md,tid,version,before,original=_root_title_candidate(tmp_path,consulted_evidence=drift=='consulted-evidence')
    _bind_rewrite_fixture(monkeypatch,md)
    preview=manuscript_proposals.preview(tmp_path,'fixture',tid,version)
    first=preview['edits'][0]
    payload={'turn_id':tid,'proposal_version':version,'edit_id':first['edit_id'],'decision':'accept'}
    if drift=='author-refinement':payload.update(decision='merge',review_token=first['review_token'],merged_after='\\title{Author title}')
    applied=manuscript_proposals.decide(tmp_path,'fixture',payload)
    if drift=='external-root':(md/'main.tex').write_text((md/'main.tex').read_text()+'External root change.\n')
    elif drift=='included-source':(md/'chapter.tex').write_text('Changed body evidence.\n')
    elif drift=='correction':authoring.bank_correction('fixture',{'text':'New scientific premise.','kind':'factual','scope':'project','by':'author'},repo_root=tmp_path)
    elif drift=='consulted-evidence':
        from laplace.projects import artifacts as writing_artifacts
        (writing_artifacts.project_root(tmp_path,'fixture')/'evidence.txt').write_text('Changed scientific premise.')
    elif drift=='other-edition':
        from laplace.pipeline import registry
        alternate=md/'alternate.tex';alternate.write_text(original)
        registry.set_document('fixture',{'root':alternate.relative_to(tmp_path).as_posix(),
            'manuscript_dir':md.relative_to(tmp_path).as_posix(),'edition':'alternate'},repo_root=tmp_path)
    elif drift=='undo':(md/'main.tex').write_text(original)
    remaining=manuscript_proposals.preview(tmp_path,'fixture',tid,version)['edits'][1]
    if drift:
        assert remaining['basis_currentness']=='STALE' and 'accept' not in remaining['allowed_actions']
    else:
        assert remaining['basis_currentness']=='CURRENT' and 'accept' in remaining['allowed_actions']
        final=manuscript_proposals.decide(tmp_path,'fixture',{'turn_id':tid,'proposal_version':version,
            'edit_id':remaining['edit_id'],'decision':'accept'})
        assert final['application']['validation_basis']['transition_ids']==[applied['application']['id']]
        assert '\\hypersetup{pdftitle={New title}}' in (md/'main.tex').read_text()
    assert json.dumps(session_reads._records(tmp_path)['turns'][tid]['proposal_bases'][version],sort_keys=True)==before


@pytest.mark.parametrize('body_direction',['newer','older'])
def test_root_sibling_refuses_a_mixed_actual_physical_observation(tmp_path,monkeypatch,body_direction):
    from laplace.pipeline import authoring
    md,tid,version,_,original=_root_title_candidate(tmp_path)
    calls=_bind_rewrite_fixture(monkeypatch,md)
    preview=manuscript_proposals.preview(tmp_path,'fixture',tid,version)
    first=manuscript_proposals.decide(tmp_path,'fixture',{'turn_id':tid,'proposal_version':version,
        'edit_id':preview['edits'][0]['edit_id'],'decision':'accept'})
    path=md/'main.tex';post=path.read_bytes();inspect=authoring.inspect
    def mixed(*args,**kwargs):
        if kwargs.get('_source_observation') is None:return inspect(*args,**kwargs)
        # Both are real fixture disk reads. Force the context body's physical
        # cut newer/older than the app-chain source_fact already observed.
        path.write_bytes(post+b'External change.\n' if body_direction=='newer' else original.encode())
        try:return inspect(*args,**kwargs)
        finally:
            if body_direction=='older':path.write_bytes(post)
    monkeypatch.setattr(authoring,'inspect',mixed)
    remaining=manuscript_proposals.preview(tmp_path,'fixture',tid,version)['edits'][1]
    assert remaining['basis_currentness']=='STALE' and 'accept' not in remaining['allowed_actions']
    assert 'postimage changed during validation' in remaining['error']
    assert len(calls)==1 and first['application']['complete']


def test_project_review_reaches_the_anchored_cross_turn_comparison_without_an_owner_exception(tmp_path):
    """M5-I4: `_same_edit_occurrence` compares source anchors as Mappings. The name was used
    without its import, so every same-occurrence comparison raised NameError inside the
    Project Review read (preview -> applications_for_edits). The saved queue below carries
    anchored edits on both turns and reaches the anchor comparison; the occurrence rule itself
    is unchanged: equal anchors match, a different anchor at the same text does not."""
    from laplace.manuscript import proposal_preflight
    from laplace.manuscript import proposal_currentness
    raw = "\\documentclass{article}\n\\begin{document}\nFirst paragraph.\n\nSecond paragraph.\n\\end{document}\n"
    _manuscript, _ = _import_project(tmp_path, files={"main.tex": raw})
    edits = [
        {"file": "main.tex", "line_start": 3, "line_end": 3, "before": "First paragraph.",
         "after": "First revised paragraph.", "reason": "Explain the premise.", "source_anchor": proposal_preflight.source_anchor(raw, 3, 3)},
        {"file": "main.tex", "line_start": 5, "line_end": 5, "before": "Second paragraph.",
         "after": "Second revised paragraph.", "reason": "Clarify the conclusion.", "source_anchor": proposal_preflight.source_anchor(raw, 5, 5)},
    ]
    old_turn = _seed_revision(tmp_path, "fixture", edits, selection={"files": ["main.tex"]})
    from laplace.manuscript import manuscript_source
    source = manuscript_source.resolve("fixture", repo_root=tmp_path); later = "WT-anchored"
    writing_records.bank(tmp_path, {"record": "writing-session", "id": "WS-anchored", "project": "fixture", "provider": "codex", "model": "m", "effort": "medium"})
    writing_records.bank(tmp_path, {"record": "writing-turn", "id": later, "session_id": "WS-anchored", "project": "fixture", "document": source})
    refined = {**edits[1], "after": "Second paragraph with the author's precision."}
    writing_records.bank(tmp_path, {"record": "writing-application", "id": "WA-anchored", "turn_id": later, "project": "fixture", "complete": True, "edits": [edits[0], refined]})

    # the comparison itself, on anchored edits
    assert proposal_currentness._same_edit_occurrence(edits[0], dict(edits[0])) is True
    assert proposal_currentness._same_edit_occurrence(edits[1], refined, same_after=False) is True
    assert proposal_currentness._same_edit_occurrence(edits[1], refined) is False, "a different after text is not the same edit"
    moved = {**edits[0], "source_anchor": proposal_preflight.source_anchor(raw.replace("First paragraph.", "Preface.\n\nFirst paragraph."), 5, 5)}
    assert proposal_currentness._same_edit_occurrence(edits[0], moved) is False, "the same text at another anchored occurrence is another occurrence"

    # the Project Review queue and its read reach that comparison
    queue = session_reads.pending_proposals(tmp_path, "fixture")
    assert queue["count"] == 1
    preview = manuscript_proposals.preview(tmp_path, "fixture", old_turn)
    assert [row["status"] for row in preview["edits"]] == ["pending", "pending"]
    assert preview["edits"][0]["historical_application_matches"][0]["turn_id"] == later, "the exact anchored application is a historical match"
    assert preview["edits"][1]["next_decision"] == {"decision": "supersede", "application_id": "WA-anchored"}, "the refined anchored application is offered as a supersession"
    assert preview["edits"][1]["after"] == edits[1]["after"], "the proposal's own text is preserved"
