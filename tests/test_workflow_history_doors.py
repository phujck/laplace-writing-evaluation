"""Focused public shared-door joins; owner large/cross-cell controls remain separate."""
import copy,json
from urllib.parse import parse_qs,urlsplit
from pathlib import Path
import pytest,jsonschema
from laplace import sdk
from laplace.pipeline import workflow_definitions as D,workflow_definition_history as L
from laplace.work import owner_discovery as O,project_work_views as V,project_work_navigation as N
from laplace.web import workflow_definitions_surface as HTTP,project_work_surface as WorkHTTP
from laplace.native import tools,declarations
from laplace.writing import delivery,schemas
from test_workflow_history_continuation import scene

@pytest.fixture(autouse=True)
def passive_catalogue(monkeypatch):
 from laplace.writing import provider_catalogue
 monkeypatch.setattr(provider_catalogue,'provider_catalogue',lambda *a,**k:{'schema_version':'laplace.provider-catalogue/1','observed_at':99999999999,'providers':[{'id':'codex','available':False,'models':[]}]})

def registered(root):
 (root/'book').mkdir(parents=True,exist_ok=True);(root/'book/main.tex').write_text('Public workflow source; no execution.\n')
 (root/'registry_projects.json').write_text(json.dumps({'projects':[{'name':'book','project_dir':'book','tex_root':'book','form':'book'}]}))

def http(root,handle):
 url=urlsplit(handle['http']['url']);code,_,body=HTTP.handle(url.path,parse_qs(url.query,keep_blank_values=True),'GET',repo_root=root)
 assert code==200,body.decode();return json.loads(body)

def test_actual_history_and_body_pages_cross_sdk_native_http_with_same_scope(tmp_path,monkeypatch):
 registered(tmp_path);scope,versions=scene(tmp_path,3,42000,project=True);ident=versions[0]['definition_id']
 request={'definition_id':ident,'facet':'history-page','project_lens':'book','limit':2,'capture_max_bytes':1000000,'metadata_max_rows':100}
 first=sdk.workflow_request(request,root=tmp_path);native=tools.execute(tmp_path,'book','review','project',{'view':'workflow-definitions','request':request});human=http(tmp_path,D.scoped_handle(scope,**request))
 for key in ['definition_id','scope','scope_id','head_at_start','selected_version','cut','known','unit','order','ordinal_base','offset','returned','covered','at_end','items']:
  assert first[key]==native[key]==human[key],key
 assert first['known']==3 and [r['ordinal'] for r in first['items']]==[3,2]
 assert first['body_verification']=='NOT_INSPECTED'
 # The complete selected saved body must be assembled in explicit issued order.
 read={**first['items'][0]['read']['request'],'body_offset':0,'body_limit':1000};page=sdk.workflow_request(read,root=tmp_path)
 assert page['state']=='BODY_PAGE' and page['definition'] is None and page['read_only']
 native=tools.execute(tmp_path,'book','review','project',{'view':'workflow-definitions','request':read});human=http(tmp_path,D.scoped_handle(scope,**read))
 for key in ['reference','version','cut','body_page','content','read_only']:assert page[key]==native[key]==human[key],key
 assert page['body_page']['unit']=='Unicode-code-point' and page['body_page']['returned']==len(page['content'])
 # Appending ordinary native read audit rows changes no selected definition cut.
 next_page=http(tmp_path,first['next_read']);assert next_page['cut']==first['cut'] and next_page['at_end']
 with pytest.raises(ValueError):tools.execute(tmp_path,'foreign','review','project',{'view':'workflow-definitions','request':request})
 (tmp_path/'door-sample.json').write_text(json.dumps({'history':first,'native_body_page':native,'http_body_page':human,'body_page':page,'last':next_page,'reference':versions[-1]['reference']},indent=2))

def test_closed_history_transport_refuses_duplicates_unknowns_and_preserves_legacy(tmp_path,monkeypatch):
 registered(tmp_path);scope,versions=scene(tmp_path,2,100,project=True);ident=versions[0]['definition_id'];request={'definition_id':ident,'facet':'history-page','project_lens':'book'}
 schema=schemas.SCHEMAS['project'];jsonschema.validate({'view':'workflow-definitions','request':request},schema)
 for invalid in [{**request,'unexpected':True},{**request,'body_offset':0,'body_limit':0}]:
  with pytest.raises(jsonschema.ValidationError):jsonschema.validate({'view':'workflow-definitions','request':invalid},schema)
 first=sdk.workflow_request(request,root=tmp_path);assert first['known']==2
 seen=[];monkeypatch.setattr(D,'read',lambda *a,**k:seen.append(a) or {})
 for query in [{'facet':['history-page','inspect']},{'facet':['history-page'],'definition_id':[ident,ident]},{'reference':['{"owner":"one","owner":"two"}'],'facet':['history-page']}]:
  assert HTTP.handle('/work/workflow-definitions',query,'GET',repo_root=tmp_path)[0]==422
 assert not seen
 assert V.delivery_profile({'view':'workflow-definitions','request':{'facet':'history-page'}})['bound']==N.CAP
 assert V.delivery_profile({'view':'workflow-definitions','request':{'facet':'inspect'}}) is None
 jsonschema.validate({'view':'workflow-definitions','request':{'facet':'history','definition_id':ident}},schema)


def test_workspace_v2_pure_request_http_sdk_and_native_authority_stays_separate(tmp_path,monkeypatch):
 scope,versions=scene(tmp_path,2,100);payload={'action':'request','definition_transport':'lineage-v2','definitions':[versions[-1]['reference']],'destination':str(tmp_path.parent/'recipient'),'request_id':'public-transport-request','max_files':100,'max_rows':100,'max_bytes':2000000}
 # New profile is pure, typed and destination-qualified, not a fake project.
 schema=declarations.HTTP_DECLARATIONS['work/object-handover'].payload
 jsonschema.validate(payload,schema)
 with pytest.raises(jsonschema.ValidationError):jsonschema.validate({'action':'request'},schema)
 expected=sdk.research_handover(payload,root=tmp_path);code,_,raw=WorkHTTP.handle('/work/object-handover',{},'POST',json.dumps(payload).encode(),repo_root=tmp_path);actual=json.loads(raw)
 assert code==200 and actual['state']==expected['state']=='PREPARED' and actual['effect']==expected['effect']=='none'
 assert actual['export']['http']['payload']==expected['export']['http']['payload']
 assert actual['export']['http']['payload']['expected_lineage_basis'].startswith('sha256:')
 assert not (tmp_path.parent/'recipient').exists()
 from laplace.projects import project_handover_lineage as T
 monkeypatch.setattr(T,'_wire',lambda *a,**k:pytest.fail('native destination metadata before authority refusal'))
 with pytest.raises(ValueError,match='EXPLICIT_AUTHOR_EXPORT_SELECTION_REQUIRED'):tools.execute(tmp_path,'book','review','research_handover',payload)
 assert WorkHTTP.handle('/work/object-handover',{},'POST',b'{"action":"request","action":"export"}',repo_root=tmp_path)[0] in {400,422}
 (tmp_path/'handover-sample.json').write_text(json.dumps({'request':payload,'prepared':actual},indent=2))


def test_new_history_profile_obeys_existing_effective_delivery_line(tmp_path):
 registered(tmp_path);scope,versions=scene(tmp_path,3,42000,project=True)
 request={'reference':versions[-1]['reference'],'facet':'saved-version','project_lens':'book','body_offset':0,'body_limit':8000}
 with delivery.planned(line=12000):
  response=sdk.workflow_request(request,root=tmp_path)
  assert N.emitted(response)<=12000 and response['state']=='BODY_PAGE' and response['definition'] is None
 assert response['body_page']['returned']<=8000 and response['body_page']['sha256'].startswith('sha256:')
 native=tools.execute(tmp_path,'book','review','project',{'view':'workflow-definitions','request':request})
 assert N.emitted(native)<=N.CAP and native['state']=='BODY_PAGE'
 assert N.CAP==30000
