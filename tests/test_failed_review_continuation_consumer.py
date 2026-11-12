"""Consume the real continuation owner through native and workflow read adapters."""
import copy
import hashlib
import json
import os
from pathlib import Path
from dataclasses import asdict
import pytest
from test_failed_review_continuation import partial, offered, host_seam
from test_app_workflow_dispatch import prepared
from test_packet_return_lifecycle import judgement
from laplace.native import tools, verbs, declarations
from laplace.pipeline import workflow_definitions as D
from laplace.work import project_work as W, owner_discovery as O
from laplace.writing import records, child_hosts, dispatch_execution as E, dispatch_parent, turn_admission
from laplace.projects import artifacts


def retain(name,value):
    home=os.environ.get('FAILED_REVIEW_CONSUMER_EVIDENCE')
    if home:
        target=Path(home);target.mkdir(parents=True,exist_ok=True)
        (target/(name+'.json')).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')


def parent(case):
    root, ident, _, _ = case
    turn='WT-explicit-parent-continuation'
    records.bank(root,{'record':'writing-turn','id':turn,'session_id':'WS-parent','project':'book','mode':'work','work_id':ident})
    child_hosts._begin_child_execution(root,'WS-parent',{'state':'RUNNING','turn_id':turn,'project':'book','session_id':'WS-parent','host':child_hosts._process_identity()})
    return turn


def run(case):
    root, ident, _, _ = case;task=W._tasks('book',root)[ident]
    return D.read(root,O.project_scope('book','sdk'),{'reference':task['prepared_workflow']['reference'],'facet':'app-run','work_id':ident,'step_id':'Review'})


def test_exact_native_schema_help_grammar_effect_and_same_request_recovery(partial,monkeypatch):
    root, ident, _, _=partial;payload=offered(partial);actor=parent(partial);launches=host_seam(monkeypatch,partial)
    act=verbs.classify('dispatch_continue',payload,project='book',root=root)
    assert act.exact and act.owner_call==('dispatch_continue',payload)
    request=asdict(act.request)
    answer=tools.request(root,'book','work',request,turn_id=actor);result=answer['owner_response']
    assert answer['outcome']=='banked' and result['effect']=='RECORDED' and len(launches)==1
    assert tools.call(root,'book','work',{'operation':'dispatch_continue','payload':payload},turn_id=actor)['replayed']
    recovery=tools.call(root,'book','work',result['read'],turn_id=actor)
    assert recovery['receipt']==result['receipt'] and len(launches)==1
    retain('native-effect-recovery',{'grammar':request,'answer':answer,'recovery':recovery,'launches':launches})
    initial=verbs.classify('dispatch_launch',{'id':ident},project='book',root=root)
    assert initial.exact and initial.owner_call==('dispatch_launch',{'id':ident})
    help=tools.execute(root,'book','work','help',{'operation':'dispatch_continue'},turn_id=actor)
    assert help['action']['operation']=='dispatch_continue'
    assert declarations.DECLARATIONS['dispatch_continue'].payload['required']==['id','packet','request_id','guard','budget']


def test_pending_unknown_has_no_invented_conversation_and_keeps_old_attempt(partial,monkeypatch):
    root, ident, _, _=partial;actor=parent(partial);launches=host_seam(monkeypatch,partial,failure='before')
    request=asdict(verbs.classify('dispatch_continue',offered(partial),project='book',root=root).request)
    answer=tools.request(root,'book','work',request,turn_id=actor);result=answer['owner_response']
    assert answer['outcome']=='banked' and result['effect']=='UNKNOWN'
    value=run(partial);step=value['step_detail']
    assert step['current_attempt']['turn_id'] is None and not step['current_attempt']['observed']
    assert 'conversation' not in step and 'typed_return_read' not in step
    assert step['binding']['status']=='UNAVAILABLE' and step['attempt_history'][0]['turn_id']=='WT-child-1'
    assert step['continuation_request']['effect']=='UNKNOWN' and not step['continue_action']['available']
    assert step['reused_outputs'][0]['output']['read']['http']['method']=='GET'
    assert len(launches)==1 and len(records.fold_records(root)['sessions'])==3
    retain('unknown-pending-projection',{'answer':answer,'step':step,'launches':launches})


def test_composer_is_passive_exact_and_targets_inspected_original_parent_work(partial):
    root, ident, _, _=partial;value=run(partial);action=value['step_detail']['continue_action']
    assert action['available'] and action['native']['operation']=='dispatch_continue'
    request={**action['read']['request'],'request_id':'human-intent-one'}
    result=D.read(root,O.project_scope('book','sdk'),request);composed=result['action'];payload=composed['payload']
    assert composed['send_required'] and payload['session_id']=='WS-parent' and payload['work_id']==ident
    assert result['continuation_payload']=={**action['native']['payload'],'request_id':'human-intent-one'}
    context=turn_admission.work_context(root,payload,{'project':'book','mode':'work','session_id':'WS-parent'},records.fold_records(root),None)
    assert context['work_id']==ident and composed['work_target']['work_scope_revision']==payload['expected_work_scope_revision']
    assert set(E._continuation_task(root,'book',ident).get('dispatch_review_continuations') or {})==set()
    retain('passive-composer',{'offered':action,'composed':result,'Work_context':context})


def test_selected_actual_turn_permission_native_publish_and_historical_read_agree(partial,monkeypatch):
    root, ident, plan, worker=partial;actor=parent(partial);host_seam(monkeypatch,partial)
    continued=tools.call(root,'book','work',{'operation':'dispatch_continue','payload':offered(partial)},turn_id=actor);current=continued['current_attempt']['turn_id']
    with pytest.raises(ValueError,match='no admitted child return contract'):
        tools.execute(root,'book','review','session_settings',{'view':'return-contract'},turn_id='WT-child-1')
    old=tools.execute(root,'book','review','help',{'operation':'store_artifact'},turn_id='WT-child-1')
    assert old['action']['permitted'] is False
    document=judgement(worker,artifacts.resolve_path(root,'book',plan['packets'][0]['return_path']));document['packet']=worker['packet'];document['judged']['review_context']['session_id']='WS-child-1'
    read=tools.execute(root,'book','review','read_artifact',{'path':'development/report.md'},turn_id=current)['read_receipt']
    check={'kind':'owner-read','state':'PASSED','operation':read['operation'],'payload':read['payload'],'receipt_id':read['id'],'output_sha256':read['output_sha256'],'ok':True,'output_tail':'Exact public worker output read.'}
    document['scripted_check']=check;document['own_observations']=[{k:v for k,v in check.items() if k!='state'}]
    contract=tools.execute(root,'book','review','session_settings',{'view':'return-contract'},turn_id=current)['return_contract']
    action=copy.deepcopy(contract['publish_action']);action['payload']['content']=json.dumps(document)
    published=tools.call(root,'book','review',action,turn_id=current)
    with pytest.raises(ValueError,match='Independent review'):
        tools.call(root,'book','review',action,turn_id='WT-child-1')
    records.bank(root,{'record':'writing-reply','id':'WR-current-judge','project':'book','session_id':'WS-child-1','turn_id':current,'status':'completed','text':'Current independently judged result retained.'})
    child_hosts._finish_child_execution(root,'WS-child-1',current,'completed')
    value=run(partial);step=value['step_detail'];assert step['current_attempt']['turn_id']==current
    assert step['attempt_history'][0]['conversation']['turn_id']=='WT-child-1'
    assert step['state']=='COMPLETE' and value['observation']['review_state']=='ACCEPTED'
    retain('selected-publisher-history',{'published':published,'step':step,'observation':value['observation'],'stale_help':old})


def test_retained_valid_file_without_ART_uses_owner_path_read(partial):
    root, _, plan, worker = partial
    target = artifacts.resolve_path(root, 'book', 'development/unbanked-result.md')
    content = 'Existing valid public file output without an ART declaration.'
    target.write_text(content)
    pin = {'path': target.relative_to(root).as_posix(), 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}
    document = copy.deepcopy(worker);document.update(output=pin, files_written=[pin['path']])
    document['source']['artifacts'] = [document['inputs'][0], pin]
    before = artifacts.read(root, 'book', {'path': plan['packets'][0]['return_path']})
    artifacts.store(root, 'book', {'path': plan['packets'][0]['return_path'],
        'expected_revision': before['revision'], 'content': json.dumps(document), 'reason': 'Public retained output control.'}, 'WT-child-0')
    output = run(partial)['step_detail']['reused_outputs'][0]['output']
    assert output['id'] is None and output['revision'] == pin['sha256']
    read = output['read']['native']
    assert read == {'operation': 'read_artifact', 'payload': {'path': 'development/unbanked-result.md', 'scope': 'project'}}
    observed = tools.execute(root, 'book', 'work', read['operation'], read['payload'], turn_id='prepare-turn')
    assert observed['content'] == content and observed['revision'] == output['revision']
    retain('unbanked-output-corrected', {'output': output, 'native_read': read, 'observed': observed})
