"""Actual public operation doors; controlled native host metadata, no inference."""
import copy
import json
import hashlib
from urllib.parse import parse_qs, urlsplit
import pytest
import jsonschema
from laplace import sdk
from laplace.pipeline import workflow_definitions as D, workflow_operations as F
from laplace.work import owner_discovery as O
from laplace.web import workflow_definitions_surface as HTTP
from laplace.native import tools, declarations
from laplace.writing import records, child_hosts, schemas
from test_workflow_operations import body
from test_workflow_history_doors import registered

@pytest.fixture(autouse=True)
def passive_catalogue(monkeypatch):
 from laplace.writing import provider_catalogue
 monkeypatch.setattr(provider_catalogue, 'provider_catalogue', lambda *a, **k: {
  'schema_version': 'laplace.provider-catalogue/1', 'observed_at': 99999999999,
  'providers': [{'id': 'codex', 'available': False, 'models': []}]})

def post(root, handle, additions=None):
 wire={**copy.deepcopy(handle['http']['payload']), **(additions or {})}
 url=urlsplit(handle['http']['url'])
 sent=json.dumps(wire).encode()
 code,_,raw=HTTP.handle(url.path,parse_qs(url.query),'POST',sent,repo_root=root)
 assert code==200,raw.decode()
 value=json.loads(raw)
 if url.path=='/work/workflow-definitions':
  assert value['transport_request']=={'sha256':'sha256:'+hashlib.sha256(sent).hexdigest(),'encoding':'utf8-exact-request-body'}
 return value

def test_issued_draft_post_read_preserves_scope_across_sdk_native_http(tmp_path):
 registered(tmp_path)
 listing=sdk.workflow_request({'project_lens':'book'},root=tmp_path)
 offer=listing['execution_preview'];assert offer['read']['http']['method']=='POST'
 draft=body();draft['steps'][0]['assignment']['instructions']='Public Unicode Ω context. '*250
 additions={'definition':draft,'scope':{'kind':'project','namespace':'book'},'step_ids':['write','review']}
 wire={**offer['read']['http']['payload'],**additions}
 jsonschema.validate(wire, declarations.HTTP_DECLARATIONS['work/workflow-operation-read'].payload)
 jsonschema.validate({'view':'workflow-definitions','request':wire},schemas.SCHEMAS['project'])
 expected=sdk.workflow_request(wire,root=tmp_path)
 human=post(tmp_path,offer['read'],additions)
 native=tools.execute(tmp_path,'book','review','project',{'view':'workflow-definitions','request':wire})
 for key in ['scope','scope_id','basis','definition_digest','support','execution_permitted','roles']:
  assert expected[key]==human[key]==native[key],key
 assert expected['execution_permitted'] is False
 context_read=next(role['context_read'] for role in expected['roles'] if role['step_id']=='write')
 assert context_read['http']['method']=='POST' and context_read['required_inputs']==['definition']
 context=post(tmp_path,context_read,{'definition':draft,'limit':1})
 assert context['returned']==200 and context['next_read']['http']['method']=='POST'
 assert context['delivery']['permission_effect']=='none'
 assert not (tmp_path/'contract/dispatches.jsonl').exists()
 with pytest.raises(ValueError):
  tools.execute(tmp_path,'foreign','review','project',{'view':'workflow-definitions','request':wire})
 (tmp_path/'operation-door-sample.json').write_text(json.dumps({'preview':human,'context':context,'draft_offer':offer},indent=2))

def test_exact_withdrawal_door_identity_recorded_winner_and_native_admission(tmp_path):
 registered(tmp_path)
 records.bank(tmp_path,{'record':'writing-session','id':'WS-public','project':'book','role':'author','provider':'codex','model':'controlled','effort':'medium'})
 records.bank(tmp_path,{'record':'writing-turn','id':'WT-public','session_id':'WS-public','project':'book','mode':'discuss','text':'Controlled native withdrawal','context_parts':[]})
 child_hosts._begin_child_execution(tmp_path,'WS-public',{'state':'RUNNING','turn_id':'WT-public','session_id':'WS-public','project':'book','host':child_hosts._process_identity(),'provider_process':None,'provider_processes':[]})
 draft=body();draft['layout']={'positions':{'write':{'x':1e-7,'y':0.2}}}
 original={'request_id':'public-withdraw','expected_revision':None,'definition':draft,'scope':{'kind':'project','namespace':'book'}}
 listing=sdk.workflow_request({'project_lens':'book'},root=tmp_path)
 offered=listing['actions']['create']['withdrawal']
 prepared=post(tmp_path,offered['prepare_read'],{'original_request':original})
 assert prepared['effect']=='none' and prepared['intent_digest']==prepared['withdraw']['original_request_digest']
 values={'original_request':original}
 wire={**prepared['withdraw']['http']['payload'],**values}
 first=sdk.workflow_withdraw(wire,root=tmp_path);assert first['status']=='NOT_ADMITTED'
 human=post(tmp_path,prepared['withdraw'],values)
 native=tools.execute(tmp_path,'book','discuss','workflow_definition_change',wire,turn_id='WT-public')
 for reply in [human,native]:
  assert reply['request_id']==first['request_id'] and reply['intent_digest']==first['intent_digest']
  assert reply['status']==reply['effect']=='NOT_ADMITTED' and reply['terminal']
 assert sdk.workflow_save(original,root=tmp_path)['status']=='NOT_ADMITTED'
 assert sdk.workflow_request({},root=tmp_path)['total']==0
 for project,mode in [('book','review'),('foreign','discuss')]:
  with pytest.raises(ValueError):
   tools.execute(tmp_path,project,mode,'workflow_definition_change',wire,turn_id='WT-public')
 recorded={**original,'request_id':'public-already-saved'}
 saved=sdk.workflow_save(recorded,root=tmp_path)
 recorded_preview=post(tmp_path,offered['prepare_read'],{'original_request':recorded})
 final=post(tmp_path,recorded_preview['withdraw'],{'original_request':recorded})
 assert final['status']=='RECORDED' and final['version']==saved['version']
 assert final['withdrawal']=='ALREADY_RECORDED_NO_UNDO'
 assert sdk.workflow_request({},root=tmp_path)['total']==1
 (tmp_path/'withdraw-door-sample.json').write_text(json.dumps({'sdk':first,'http':human,'native':native,'recorded_winner':final},indent=2))

def test_pure_post_and_withdraw_refuse_ambiguous_transport_before_owner(tmp_path,monkeypatch):
 registered(tmp_path);calls=[]
 monkeypatch.setattr(D,'read',lambda *a,**k:calls.append('read') or {})
 monkeypatch.setattr(D,'withdraw',lambda *a,**k:calls.append('withdraw') or {})
 invalid=[('/work/workflow-definitions',{},b'{"facet":"execution-preview","facet":"uses"}'),
  ('/work/workflow-definitions',{'project_lens':['book']},b'{"facet":"execution-preview","project_lens":"foreign"}'),
  ('/work/workflow-definitions',{},b'{"facet":"execution-preview","project_lens":"foreign"}'),
  ('/work/workflow-definitions/withdraw',{},b'{"action":"withdraw","action":"save"}')]
 for path,query,raw in invalid:assert HTTP.handle(path,query,'POST',raw,repo_root=tmp_path)[0]==422
 assert not calls

def test_recorded_run_read_is_offered_only_for_project_owned_designs(tmp_path):
 registered(tmp_path)
 saves={kind:sdk.workflow_save({'request_id':'public-runs-'+kind,'expected_revision':None,'definition':body(),'scope':scope},root=tmp_path)
  for kind,scope in [('project',{'kind':'project','namespace':'book'}),('workspace',{'kind':'owned-workspace'})]}
 assert saves['project']['effect']==saves['workspace']['effect']=='saved'
 assert 'facet=app-runs' in saves['project']['app_runs_read']['http']['url']
 assert 'app_runs_read' in saves['workspace'] and saves['workspace']['app_runs_read'] is None
 assert saves['project']['actions']['app_prepare']['available'] is True
 assert saves['workspace']['actions']['app_prepare']['available'] is False
