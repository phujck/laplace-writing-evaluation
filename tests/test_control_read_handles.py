"""Current receipt handles must execute through unchanged conversation admission."""
import copy
import pytest
from laplace.writing import provider_updates as updates
from laplace.native import tools as t
from laplace.writing import records as writing_records
from laplace.writing import child_hosts
from laplace.writing import turn_control
from laplace.writing import session_reads
from test_provider_update_join import _running_input


def inspect(root,handle):
    return t.call(root,'p','work',handle,turn_id='T')


def child_handle(root,tid,sid,parent):
    writing_records.bank(root,{'record':'writing-session','id':sid,'project':'p'})
    writing_records.bank(root,{'record':'writing-turn','id':tid,'session_id':sid,'project':'p','parent_turn_id':parent})
    child_hosts._update_child_execution(root,sid,{'state':'RUNNING','turn_id':tid,'session_id':sid,'project':'p','host':child_hosts._process_identity()})
    turn=updates.turn_scope(root,'p',tid)
    control=turn_control._queue_child_steering(root,turn,{'turn_id':tid,'project':'p','text':'Exact child clarification','delivery_mode':'project_tool_boundary'})
    public=session_reads.child_execution(root,sid,controls=True)['controls'][0]
    assert public['control_id']==control['control_id']
    return public['read_handle']['native_request']


def test_actual_public_control_handle_executes_for_same_conversation_and_exact_child(tmp_path,monkeypatch):
    _turn,control=_running_input(tmp_path,monkeypatch,{'text':'Exact current clarification'})
    public=session_reads.child_execution(tmp_path,'WS-S',controls=True)['controls'][0]
    handle=public['read_handle']['native_request']
    assert set(handle['payload'])=={'view','turn_id','item_id'}
    assert public['read_handle']['payload']==handle['payload']
    same=inspect(tmp_path,handle)['owner_response']['items'][0]
    assert same['control_id']==control['control_id'] and same['payload']['text']=='Exact current clarification'
    child=child_handle(tmp_path,'T-C','WS-C','T')
    exact=inspect(tmp_path,child)['owner_response']['items'][0]
    assert exact['turn_id']=='T-C' and exact['control_id']==child['payload']['item_id']


@pytest.mark.parametrize('case',['project','session','unrelated-child','missing-control'])
def test_current_control_handle_keeps_existing_scope_and_item_refusals(tmp_path,monkeypatch,case):
    _running_input(tmp_path,monkeypatch,{'text':'Current clarification'})
    handle=copy.deepcopy(session_reads.child_execution(tmp_path,'WS-S',controls=True)['controls'][0]['read_handle']['native_request'])
    if case=='project':handle['target']='other-project'
    elif case=='missing-control':handle['payload']['item_id']='missing-control'
    elif case=='session':handle=child_handle(tmp_path,'T-U','WS-U','')
    else:
        writing_records.bank(tmp_path,{'record':'writing-session','id':'WS-P','project':'p'})
        writing_records.bank(tmp_path,{'record':'writing-turn','id':'T-P','session_id':'WS-P','project':'p'})
        handle=child_handle(tmp_path,'T-U','WS-U','T-P')
    try:answer=inspect(tmp_path,handle)
    except ValueError as error:
        assert 'control' in str(error).lower() or 'conversation' in str(error).lower()
    else:
        assert answer.get('ok') is False or answer.get('refused')
        assert 'owner_response' not in answer
