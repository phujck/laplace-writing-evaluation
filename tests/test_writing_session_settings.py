import json
from pathlib import Path

import pytest

from laplace.writing import provider as writing_provider, operating as writing_operating
from laplace.projects import library as writing_projects
from laplace.writing import turn_admission
from laplace.writing import records as writing_records
from laplace.writing import session_reads
from laplace.writing import turn_jobs
from laplace.writing.records import _fold as records_fold
from laplace.writing import turn_context
from laplace.writing import provider as writing_provider


@pytest.fixture
def project(tmp_path, monkeypatch):
    records_fold._CACHE.clear();turn_jobs._JOBS.clear()
    manuscript=tmp_path/'source';manuscript.mkdir()
    (manuscript/'main.tex').write_text('\\documentclass{article}\n\\begin{document}\nA paragraph.\n\\end{document}\n')
    assert writing_projects.import_source({'name':'book','title':'Book','root':'source/main.tex','editable':True},tmp_path)[0]==201
    monkeypatch.setattr(writing_provider,'capabilities',lambda root,**kw:{'providers':[
        {'id':'codex','available':True,'models':[{'id':m,'efforts':['low','medium','high']} for m in ['first','second']]},
        {'id':'claude','available':True,'models':[{'id':'','efforts':['low','medium','high']}]}]})
    yield tmp_path
    records_fold._CACHE.clear();turn_jobs._JOBS.clear()


def test_model_and_effort_updates_keep_native_binding_history_and_identity(project):
    root=project;s=turn_admission.new_session(root,'book','codex','first','low')
    writing_records.bank(root,{'record':'writing-binding','id':'binding','session_id':s['id'],'native_id':'native','model':'first'})
    writing_records.bank(root,{'record':'writing-turn','id':'old','session_id':s['id'],'project':'book','text':'Keep this thought.','mode':'discuss'})
    for values in [{'effort':'high'},{'model':'second'}]:
        changed=turn_admission.configure_session(root,'book',s['id'],values)['session']
        assert changed['id']==s['id'] and changed['native_id']=='native'
    records_fold._CACHE.clear()
    state=session_reads.session_state(root,s['id'])
    assert state['session']['model']=='second' and state['session']['effort']=='high'
    assert state['turns'][0]['text']=='Keep this thought.'


def _continuing_session(root,monkeypatch,prior_reply):
    captured=[]
    class Provider:
        def __init__(self,cwd,provider,model,effort,native_id,event,mode,**kwargs):
            captured.append((provider,model,effort,native_id,mode));self.event=event
        def run(self,prompt):
            self.event({'type':'session','native_id':'native','model':captured[-1][1],'provider':'codex'})
            return {'status':'completed','text':'done','turn_id':'turn'}
    monkeypatch.setattr(writing_provider, 'WritingTurn',Provider)
    s=turn_admission.new_session(root,'book','codex','first','low')
    brief=writing_operating.build('book','discuss',root)
    writing_records.bank(root,{'record':'writing-binding','id':'binding','session_id':s['id'],
        'native_id':'native','model':'first','tool_contract_digest':brief['tool_contract_digest'],
        'native_registration_signature':brief['native_registration_signature']})
    writing_records.bank(root,{'record':'writing-turn','id':'prior','session_id':s['id'],
        'project':'book','text':'Earlier.','mode':'discuss',
        'orientation':turn_context._orientation_snapshot(brief),**({'reply':prior_reply} if prior_reply else {})})
    return s,captured


def test_a_prior_turn_without_a_saved_reply_starts_a_fresh_native_session(project,monkeypatch):
    # Delivery of the earlier turn is unproven: the owner never resumes that native thread.
    s,captured=_continuing_session(project,monkeypatch,None)
    started=turn_admission.start_turn(project,{'project':'book','session_id':s['id'],'text':'Continue.','mode':'discuss','provider':'codex','model':'first','effort':'low'})
    job=turn_jobs._JOBS[started['turn_id']]
    with job['condition']:assert job['condition'].wait_for(lambda:job['done'],timeout=5)
    assert started['session_id']==s['id'] and captured[-1]==('codex','first','low',None,'discuss')
    bindings=[json.loads(line) for line in (project/records_fold._STORE).read_text().splitlines() if '"writing-binding"' in line]
    assert any(row.get('reason')=='previous turn has no saved terminal reply' and row.get('previous_native_id')=='native' for row in bindings)


def test_continuing_turn_uses_changed_settings_and_mode_without_forking(project,monkeypatch):
    root=project
    s,captured=_continuing_session(root,monkeypatch,{'status':'completed','text':'Earlier answer.'})   # delivered: resumable
    for mode,model,effort in [('discuss','first','low'),('work','second','high'),('revise','second','medium')]:
        started=turn_admission.start_turn(root,{'project':'book','session_id':s['id'],'text':'Continue.','mode':mode,'provider':'codex','model':model,'effort':effort})
        job=turn_jobs._JOBS[started['turn_id']]
        with job['condition']:assert job['condition'].wait_for(lambda:job['done'],timeout=5)
        assert started['session_id']==s['id']
        assert captured[-1]==('codex',model,effort,'native',mode)
    state=session_reads.session_state(root,s['id'])
    assert [t['mode'] for t in state['turns']]==['discuss','discuss','work','revise']
    assert state['turns'][2]['provider_settings']=={'provider':'codex','model':'second','effort':'high'}


def test_provider_change_retains_logical_history_and_requests_context_handoff(project):
    root=project;s=turn_admission.new_session(root,'book','codex','first','low')
    writing_records.bank(root,{'record':'writing-binding','id':'binding','session_id':s['id'],'native_id':'native','model':'first'})
    value=turn_admission.configure_session(root,'book',s['id'],{'provider':'claude','model':'','effort':'medium'})['session']
    assert value['id']==s['id'] and value['native_id'] is None
    assert value['pending_context']['previous_native_id']=='native'


def test_busy_invalid_or_foreign_settings_do_not_mutate_the_session(project):
    root=project;s=turn_admission.new_session(root,'book','codex','first','low')
    with pytest.raises(ValueError,match='advertised'):turn_admission.configure_session(root,'book',s['id'],{'model':'unknown'})
    with pytest.raises(ValueError,match='belong'):turn_admission.configure_session(root,'foreign',s['id'],{'effort':'high'})
    turn_jobs._JOBS['active']={'session_id':s['id'],'done':False}
    with pytest.raises(ValueError,match='current reply'):turn_admission.configure_session(root,'book',s['id'],{'effort':'high'})
    current=session_reads._records(root)['sessions'][s['id']]
    assert current['model']=='first' and current['effort']=='low'
