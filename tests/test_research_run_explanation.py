"""Passive retained-role explanation; these fixtures are not kernel evidence."""
import copy
import json
from pathlib import Path

import pytest

from laplace.web import research_surface as rs
from laplace.native import tools as writing_tools
from laplace.research import research_runs


def retained(path='normal'):
    roles={'guardian':{'pid':111771,'start_token':'guardian-known-token'},
           'supervisor':{'pid':111772,'start_token':'supervisor-known-token'}}
    job={'id':'run-retained','project':'fixture','state':'RUNNING','launch_token':'known-launch',
         'pid':111771,'supervisor_start_token':'guardian-known-token',
         'execution_deadline_monotonic':100.,
         'supervision':{'schema_version':'laplace.research-supervision/1','roles':{},'cleanup_limit_seconds':6.}}
    cleanup={'status':'VERIFIED','remaining':[],'issues':[],
             'deadline_monotonic':106.,'budget_seconds':6.}
    if path=='normal':cleanup['guardian_verification']=copy.deepcopy(cleanup)
    role='supervisor' if path=='fallback' else 'guardian'
    receipt={'supervision_schema':'laplace.research-supervision/1','launch_token':'known-launch',
             'state':'FAILED','execution_state':'FAILED','exit_code':3,'roles':roles,
             'execution_deadline_monotonic':100.,'cleanup':cleanup,
             'supervision':{'schema_version':'laplace.research-supervision/1','phase':'TERMINAL',
                 'roles':roles,'cleanup_limit_seconds':6.,'cleanup_deadline_monotonic':106.},
             'publisher':{'role':role,**roles[role]}}
    return job,receipt


@pytest.mark.parametrize('path,label',[
    ('normal','Supervisor cleanup; guardian verification'),
    ('takeover','Guardian takeover cleanup'),
    ('fallback','Supervisor survivor cleanup after guardian loss')])
def test_retained_normal_takeover_and_fallback_explain_without_copying_identities(path,label,monkeypatch):
    from laplace.research import research_runner
    job,receipt=retained(path);before=copy.deepcopy((job,receipt))
    monkeypatch.setattr(research_runner,'identity_state',lambda *_a:pytest.fail('explanation probed live processes'))
    explanation=research_runs.run_status_explanation(job,receipt)
    assert explanation['cleanup_path']['label']==label
    assert explanation['identity_fields']==research_runs.producer_execution_contract()['role_fields']
    assert (job,receipt)==before
    serialized=json.dumps(explanation)
    for value in ['111771','111772','guardian-known-token','supervisor-known-token','known-launch']:
        assert value not in serialized
    assert 'cleanup.status' in explanation['evidence']


@pytest.mark.parametrize('change',[
    lambda j,r:r['cleanup'].update(status='UNKNOWN',issues=['unproved']),
    lambda j,r:r['cleanup'].update(guardian_verification={}),
    lambda j,r:r['cleanup']['guardian_verification'].update(deadline_monotonic=105.),
    lambda j,r:r['publisher'].update(role=[]),
    lambda j,r:j.update(supervision=['invalid']),
    lambda j,r:j['supervision'].update(schema_version='unsupported'),
])
def test_unproved_malformed_and_unsupported_paths_stay_unestablished(change):
    job,receipt=retained();change(job,receipt);before=copy.deepcopy((job,receipt))
    assert research_runs.run_status_explanation(job,receipt)['cleanup_path']['label']=='Cleanup path unestablished'
    assert (job,receipt)==before


def test_legacy_missing_and_pending_have_no_retrospective_role_or_success():
    legacy={'state':'COMPLETE','pid':111771,'supervisor_start_token':'old-token'}
    explanation=research_runs.run_status_explanation(legacy,{'state':'COMPLETE'})
    assert explanation['cleanup_path']['label']=='Legacy cleanup path unrecorded'
    assert 'cleanup role unrecorded' in explanation['identity_fields']['pid']
    job,receipt=retained()
    receipt.update(state='RUNNING',cleanup={'status':'PENDING'})
    receipt['supervision']['phase']='ACTIVE'
    assert research_runs.run_status_explanation(job,receipt)['cleanup_path']['label']=='Cleanup path pending'
    assert research_runs.run_status_explanation(job,None)['cleanup_path']['label']=='Cleanup path pending'
    assert research_runs.run_status_explanation(job,None,receipt_error='unreadable')['cleanup_path']['label']=='Cleanup path unestablished'
    assert research_runs.run_status_explanation(legacy,[])['cleanup_path']['label']=='Cleanup path unestablished'


@pytest.mark.parametrize('path',['normal','takeover','fallback'])
def test_native_http_and_owner_share_labels_without_changing_retained_bytes_or_evidence(tmp_path,path):
    manuscript=tmp_path/'fixture'/'manuscript';runs=manuscript/'research_runs';runs.mkdir(parents=True)
    (tmp_path/'registry_projects.json').write_text(json.dumps({'projects':[{
        'name':'fixture','kind':'conceptric','project_dir':'fixture','tex_root':'fixture/manuscript'}]}))
    job,receipt=retained(path);job['result_absolute']=str(runs/'result.json')
    job_path=runs/'run-retained.json';receipt_path=runs/'run-retained.receipt.json'
    job_path.write_text(json.dumps(job));receipt_path.write_text(json.dumps(receipt))
    handle={'id':job['id'],'project':'fixture','job_path':job_path.relative_to(tmp_path).as_posix(),'launch_token':job['launch_token']}
    (runs/'index.json').write_text(json.dumps({'runs':[job['id']], 'run_handles':{job['id']:handle},'pending_supervision':[]}))
    before=(job_path.read_bytes(),receipt_path.read_bytes())
    native=writing_tools.execute(tmp_path,'fixture','work','run_status',{'id':job['id']})
    code,_,raw=rs.handle('/research/run/status',{'project':['fixture'],'id':[job['id']]},'GET',b'',repo_root=tmp_path)
    observed=json.loads(raw)
    assert code==200 and observed['status_explanation']==native['status_explanation']==research_runs.run_status_explanation(job,receipt)
    assert observed['state']==receipt['state'] and observed['cleanup']==receipt['cleanup']
    assert (job_path.read_bytes(),receipt_path.read_bytes())==before


@pytest.mark.parametrize('operation',['run_status','run_cancel','experiment_run','research_producer'])
def test_current_help_shares_one_producer_execution_contract(tmp_path,operation):
    from laplace.native import declarations as writing_declarations
    expected=research_runs.producer_execution_contract()
    assert writing_declarations.protocol(operation)==expected
    # compact help advertises the protocol by size (sections.chars); the one exact section is read by name
    compact=writing_tools.help_response(tmp_path,'fixture','work',{'operation':operation})
    assert 'execution_protocol' in compact['action']['sections']['chars']
    actual=writing_tools.help_response(tmp_path,'fixture','work',{'operation':operation,'section':'execution_protocol'})
    assert actual['action']['value']==expected
    assert 'supervisor_start_token' in expected['role_fields']
    assert all(word in expected['cleanup_paths'] for word in ('cleanup.status','remaining','issues','Legacy'))


@pytest.mark.parametrize('receipt',[None,{}])
@pytest.mark.parametrize('roles',[['invalid'],None])
def test_malformed_known_job_cannot_use_no_receipt_pending_shortcut(receipt,roles):
    job,_=retained();job['supervision']['roles']=roles
    before=copy.deepcopy(job)
    assert research_runs.run_status_explanation(job,receipt)['cleanup_path']['label']=='Cleanup path unestablished'
    assert job==before
