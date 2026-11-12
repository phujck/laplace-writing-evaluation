"""Exact own task mutations preserve useful reads without blessing other writers."""
import json
import pytest
from laplace.web import authoring as authoring_surface
from laplace.work import project_work
from laplace.native import tools as writing_tools
from laplace.writing import operations
from test_literature_joined_workflow import project,seed_turn,execute


def test_own_task_create_and_transition_refresh_project_read_for_source_edit(tmp_path,monkeypatch):
    manuscript,source,key,original=project(tmp_path,monkeypatch)
    selection={'files':['chapters/chapter-01.tex'],'line_start':2,'line_end':2}
    turn=seed_turn(tmp_path,source,selection,'WT-task-own')
    execute(tmp_path,'project',{},turn);execute(tmp_path,'source',selection,turn)
    created=execute(tmp_path,'task',{'title':'Scoped work','goal':'Apply the observed edit'},turn)
    assert created['action_receipt']['mutation_attribution']['exact'] is True
    assert created['action_receipt']['refreshed_read_baselines']>=1
    changed=execute(tmp_path,'task_status',{'id':created['id'],'status':'in-progress'},turn)
    assert changed['action_receipt']['mutation_attribution']['exact'] is True
    applied=execute(tmp_path,'apply_revision',{'edits':[{'file':'chapters/chapter-01.tex','line_start':2,'line_end':2,
        'before':'First passage.','after':'First passage, clarified.','reason':'Observed exact source edit.'}]},turn)
    assert applied['complete']


def test_task_receipt_refuses_a_foreign_append_during_same_write(tmp_path,monkeypatch):
    manuscript,source,key,original=project(tmp_path,monkeypatch)
    turn=seed_turn(tmp_path,source,{'files':['chapters/chapter-01.tex']},'WT-task-foreign')
    execute(tmp_path,'project',{},turn)
    from laplace.core.records import journal
    bank=journal.bank_row
    def foreign(store,row,**kwargs):
        stamped=bank(store,row,**kwargs)
        if str(store).endswith('work_orders.jsonl'):
            bank(store,{'record':'project-work','id':'OTHER','task_id':'OTHER','project':'joined','title':'Concurrent task','goal':'Outside this action','status':'open'},**kwargs)
        return stamped
    monkeypatch.setattr(journal,'bank_row',foreign)
    created=execute(tmp_path,'task',{'title':'Own work','goal':'A current mutation'},turn)
    assert created['action_receipt']['mutation_attribution']['exact'] is False
    assert created['action_receipt']['refreshed_read_baselines']==0
    rows=project_work._tasks('joined',tmp_path)
    assert created['id'] in rows and 'OTHER' in rows


def test_source_unknown_fields_rejected_before_internal_scope_is_merged(tmp_path,monkeypatch):
    manuscript,source,key,original=project(tmp_path,monkeypatch)
    turn=seed_turn(tmp_path,source,{'files':['chapters/chapter-01.tex'],'line_start':2,'line_end':2,'ui_only':'server context'},'WT-source-fields')
    with pytest.raises(ValueError,match='scoped to project'):
        execute(tmp_path,'source',{'project':None},turn)
    with pytest.raises(ValueError,match='omit fresh'):
        execute(tmp_path,'source',{'fresh':True},turn)
    observed=execute(tmp_path,'source',{},turn)
    assert observed['sources'][0]['text'].strip()=='First passage.'
    assert operations._execute(tmp_path,'joined','work','source',{'files':['chapters/chapter-01.tex'],'node_ids':['result:first']})['sources']
    with pytest.raises(ValueError,match='must be a positive'):
        execute(tmp_path,'source',{'files':['chapters/chapter-01.tex'],'line_start':True},turn)


def test_action_next_read_is_a_small_physical_source_hint():
    result={'next_read':{'operation':'source','payload':{'files':['chapters/actual.tex'],'line_start':1,'line_end':3,'text':'never copy source'}}}
    summary=writing_tools._action_summary('joined','chapter',{},result)
    assert summary['next_read']=={'operation':'source','payload':{'files':['chapters/actual.tex'],'line_start':1,'line_end':3}}
    assert 'never copy source' not in json.dumps(summary)
