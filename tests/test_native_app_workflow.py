"""Consumer review through the actual native adapter; deterministic admitted host, no providers."""
from __future__ import annotations

import copy
from dataclasses import asdict
import json

import pytest

from test_app_workflow_dispatch import prepared
from laplace.pipeline import workflow_definitions as D
from laplace.native import tools, declarations, verbs
from laplace.work import project_work, owner_discovery
from laplace.writing import records, child_hosts
from laplace.projects import artifacts
from laplace.web import workflow_definitions_surface


def call(root, payload, **options):
    return tools.call(root, 'book', options.get('mode', 'work'),
        {'operation': 'workflow_definition_change', 'payload': payload}, turn_id=options.get('turn_id', 'prepare-turn'))


def test_actual_native_app_prepare_exact_effect_compact_receipt_and_read(prepared):
    root, caller, payload, saved = prepared
    public = {'action': 'prepare', **copy.deepcopy(payload)}
    result = call(root, public)
    assert result['effect'] == 'prepared' and result['status'] == 'NOT_STARTED'
    assert result['provider_started'] is False and result['receipt']['request_id'] == payload['request_id']
    assert result['work']['id'] == result['receipt']['work_id']
    assert result['definition']['reference'] == saved['reference']
    read = tools.execute(root, 'book', 'work', 'project', result['read']['native']['payload'], turn_id='prepare-turn')
    assert read['reference'] == saved['reference'] and read['work_id'] == result['work']['id']
    assert read['parent']['prepared_by']['turn_id'] == 'prepare-turn' and read['parent']['launched_by'] is None
    assert all(step.get('binding', {}).get('status') == 'UNAVAILABLE' for step in read['steps'])
    replay = call(root, public)
    assert replay['receipt'] == result['receipt'] and replay['replayed']
    assert len(records.fold_records(root)['turns']) == len(records.fold_records(root)['sessions']) == 1
    assert len([row for row in project_work._tasks('book', root).values() if row['task_kind'] == 'dispatch']) == 1
    (root / 'native-app-proof.json').write_text(json.dumps({'prepare': result, 'read': read, 'replay': replay}, indent=2))


def test_native_semantic_prepare_discriminator_preserves_other_task_routes(prepared):
    root, _, payload, _ = prepared
    public = {'action': 'prepare', **copy.deepcopy(payload)}
    act = verbs.classify('workflow_definition_change', public, project='book', root=root)
    assert act.exact and act.owner_call == ('workflow_definition_change', public)
    assert act.request.verb == 'create' and act.request.concept == 'task@project'
    assert act.request.payload['action'] == 'prepare'
    request = json.loads(json.dumps(asdict(act.request)))
    result = tools.call(root, 'book', 'work', request, turn_id='prepare-turn')
    assert result['owner_response']['effect'] == 'prepared'
    ordinary = verbs.classify('task', {'title': 'Ordinary work'}, project='book', root=root)
    assert ordinary.owner_call[0] == 'task'
    plan = verbs.classify('dispatch_plan', {'title': 'Ordinary plan', 'packets': []}, project='book', root=root)
    assert plan.owner_call[0] == 'dispatch_plan'
    assert declarations.DECLARATIONS['workflow_definition_change'].payload == D.native_change_contract()


@pytest.mark.parametrize('mode,turn', [('review', 'prepare-turn'), ('work', 'missing')])
def test_actual_native_prepare_refuses_unadmitted_or_review_before_artifact_work(prepared, mode, turn):
    root, _, payload, _ = prepared
    with pytest.raises(ValueError):
        call(root, {'action': 'prepare', **copy.deepcopy(payload)}, mode=mode, turn_id=turn)
    assert not project_work._tasks('book', root)
    assert not [row for row in records.index(root).by_project.get('book', []) if row.get('record') == 'writing-artifact']


def test_native_prepare_lost_response_request_read_recovers_without_replay(prepared, monkeypatch):
    root, _, payload, _ = prepared
    result = call(root, {'action': 'prepare', **copy.deepcopy(payload)})
    recovered = tools.execute(root, 'book', 'work', 'project', {'view': 'workflow-definitions',
        'request': {'facet': 'request', 'request_id': payload['request_id']}}, turn_id='prepare-turn')
    assert recovered['status'] == 'RECORDED' and recovered['receipt'] == result['receipt']
    assert recovered['effect'] == 'prepared' and recovered['execution_status'] == 'NOT_STARTED'
    assert len([row for row in project_work._tasks('book', root).values() if row['task_kind'] == 'dispatch']) == 1
    assert len(records.fold_records(root)['sessions']) == 1


def test_owned_http_save_cannot_shadow_app_preparation_request(prepared):
    root,caller,payload,saved=prepared
    result=tools.execute(root,'book','work','workflow_definition_change',{'action':'prepare',**copy.deepcopy(payload)},turn_id='prepare-turn')
    code,_,raw=workflow_definitions_surface.handle('/work/workflow-definitions/save',{},'POST',json.dumps({
        'request_id':payload['request_id'],'expected_revision':None,'definition':saved['definition']}).encode(),repo_root=root)
    recovery=D.read(root,caller,{'facet':'request','request_id':payload['request_id']})
    _,_,http_raw=workflow_definitions_surface.handle('/work/workflow-definitions',{'facet':['request'],'request_id':[payload['request_id']]},'GET',repo_root=root)
    http_recovery=json.loads(http_raw)
    (root/'request-shadow-proof.json').write_text(json.dumps({'prepared':result,'http_save':{'status':code,'body':json.loads(raw)},'native_recovery':recovery,'http_recovery':http_recovery},indent=2))
    assert code==409 and json.loads(raw)['code']=='REQUEST_CONFLICT'
    assert recovery['effect']=='prepared' and recovery['receipt']==result['receipt']

    assert http_recovery['effect']=='prepared' and http_recovery['receipt']==result['receipt']


def test_large_real_preparation_keeps_compact_effect_and_fully_assembled_semantic_receipt(prepared):
    from laplace.writing import delivery
    root, _, payload, saved = prepared
    body=copy.deepcopy(saved['definition'])
    names=[*(('builder-'+str(i),'builder') for i in range(6)),('review-a','adversary'),('review-b','adversary')]
    body['steps']=[{'id':ident,'parent_id':None,'assignment':{'role':role,'instructions':'Full public instruction for '+ident,'settings':{}}} for ident,role in names]
    packets=[{'packet':ident,'role':'worker' if role=='builder' else 'judge'} for ident,role in names]
    body['edges']=[{'id':source+'-to-'+ident,'from':source,'to':ident,'kind':'control'} for ident,_ in names for source in project_work.dispatch_dependencies(packets,ident)]
    saved=D.save(root,owner_discovery.project_scope('book','sdk'),{'request_id':'large-body','expected_revision':None,'definition':body})
    public={'action':'prepare',**payload,'request_id':'large-prepare','reference':saved['reference'],'step_ids':[ident for ident,_ in names],'fan_out_max':8}
    request=json.loads(json.dumps(asdict(verbs.classify('workflow_definition_change',public,project='book',root=root).request)))
    result=tools.call(root,'book','work',request,turn_id='prepare-turn')
    effect=result['owner_response']
    assert effect['effect']=='prepared' and effect['full_response_omitted'] is True
    assert effect['receipt']['request_id']=='large-prepare' and effect['work']['id']==effect['receipt']['work_id']
    assert effect['definition']['reference']==saved['reference'] and effect['parent']['prepared_by']['turn_id']=='prepare-turn'
    assert effect['next_read']==effect['read']['native'] and effect['provider_started'] is False
    assert len(records.fold_records(root)['sessions'])==1
    (root/'large-native-proof.json').write_text(json.dumps({'assembled':result,'emitted_bytes':delivery.emitted(result),'children':0},indent=2))
