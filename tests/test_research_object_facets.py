"""Real public owner joins. No provider, network or copied author project."""
import copy,json
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
import pytest
from test_logical_planning import _fixture
from laplace.core import identity
from laplace.work import owner_discovery as O,object_facets as F
from laplace.research import object_context as R,research_records,concepts
from laplace.projects import artifacts

@pytest.fixture
def scene(tmp_path):
 root=tmp_path/'public';root.mkdir();home=_fixture(root)
 (root/'logic/data').mkdir();(root/'logic/data/result.json').write_text('{"value":7}')
 (root/'logic/data/method.txt').write_text('Public method Ω.\nExact selected evidence.\n')
 (root/'logic/private').mkdir();(root/'logic/private/secret-name.txt').write_text('PRIVATE_SENTINEL')
 code,result=research_records.record('logic',{'record':{'kind':'result','id':'R7','scope':'project','title':'Public method result','source':'data/method.txt','result':'data/result.json'}},root)
 assert code==201,result
 return root,home

def test_workspace_without_project_and_actual_sdk_http_native_projection(scene):
 from laplace import sdk
 from laplace.web import project_work_surface
 from laplace.native import tools
 root,home=scene;payload={'facet':'workspace','family':'concept','limit':2}
 value=sdk.request(payload,root=root)
 assert value['subject'] is None and value['items'] and value['scope_id'] and value['pagination']['next_read']
 assert any(x['id']=='logic' for x in value['project_lenses'])
 code,_,raw=project_work_surface.handle('/work/discovery',{'facet':['workspace'],'family':['concept'],'limit':['2']},'GET',repo_root=root)
 assert code==200,json.loads(raw)
 http=json.loads(raw);assert http['basis']==value['basis'] and http['scope_id']==value['scope_id']
 native=tools.execute(root,'logic','work','project',{'view':'discovery','request':payload})
 assert native['items']==value['items'] and native['scope']['kind']=='project'
 ref=R.reference('concept','logic','result:one');object_value=sdk.request({'facet':'object','reference':ref},root=root)
 assert object_value['facets']['purpose']['value']['summary']=='The construction is admissible.'
 assert all(x['read']['sdk']['payload']['reference']==ref for x in object_value['project_lenses'])
 packet=F.resolve_object_context(root,'logic',{'reference':ref,'expected_basis':object_value['basis']})
 assert set(packet)=={'reference','basis','summary','read'} and 'content' not in packet
 with pytest.raises(ValueError):F.resolve_object_context(root,'another',{'reference':ref,'expected_basis':object_value['basis']})
 (root/'workspace-proof.json').write_text(json.dumps({'workspace':http,'selected':object_value,'context':packet},indent=2))

def test_owner_question_action_and_source_only_capability(scene):
 root,home=scene;value=O.request(root,O.owned_workspace('http'),{'facet':'workspace','project_lens':'logic'})
 action=value['facets']['actions']['items'][0];assert action['permitted'] and action['fields'][0]['name']=='meaning'
 payload={**action['http']['payload'],'meaning':'Does the changed method still support the claim?'}
 from laplace.web import project_work_surface
 code,_,raw=project_work_surface.handle(action['http']['url'],{},'POST',json.dumps(payload).encode(),root)
 assert code==200,json.loads(raw)
 ident=payload['node'];made=F.request(root,O.owned_workspace('sdk'),{'facet':'object','reference':R.reference('concept','logic',ident)})
 assert made['facets']['purpose']['value']['summary']==payload['meaning']
 from laplace.projects import library
 code,created=library.create({'name':'notes','title':'Source optional','kind':'general'},root);assert code==201
 before=sorted(str(p.relative_to(root)) for p in root.rglob('*') if p.is_file())
 empty=F.request(root,O.owned_workspace('http'),{'facet':'workspace','project_lens':'notes'})
 assert not empty['facets']['actions']['items'][0]['permitted']
 assert sorted(str(p.relative_to(root)) for p in root.rglob('*') if p.is_file())==before
 assert not list((root/'writing_projects/notes').rglob('*.tex'))
 (root/'question-action-proof.json').write_text(json.dumps({'action':action,'created':made,'source_optional':empty},indent=2))

def test_exact_source_packet_page_descriptor_and_stale_private_refusals(scene):
 root,home=scene;reference=F.ref('domain.projects','source-file',project='logic',path='data/method.txt',scope='project')
 value=F.request(root,O.owned_workspace('sdk'),{'facet':'object','reference':reference})
 read=F.handle({'facet':'object','reference':reference,'section':'body','offset':7,'limit':16,'as_of':value['basis']})
 descriptor=F.input_from_read(root,O.project_scope('logic','native'),reference,read)
 packet=F.capture_inputs(root,'logic',{'entries':[descriptor]})
 assert packet['entries'][0]['content']==(root/'logic/data/method.txt').read_text()[7:23]
 assert packet['entries'][0]['coverage']=={'complete_selected':True,'whole_source':False}
 assert packet['consumed_bases']==[{'reference':reference,'basis':value['basis']}]
 assert packet['measurements']['utf8_bytes']==len(identity.canonical_bytes(packet))
 assert packet['measurements']['characters']==len(identity.canonical_bytes(packet).decode('utf-8'))
 wrong=copy.deepcopy(read);wrong['native']['payload']['request']['reference']['identity']['path']='data/result.json'
 with pytest.raises(ValueError):F.input_from_read(root,O.project_scope('logic','native'),reference,wrong)
 (root/'logic/data/method.txt').write_text('Changed public method')
 with pytest.raises(ValueError,match='CHANGED_INPUT'):F.capture_inputs(root,'logic',{'entries':[descriptor]})
 private=F.ref('domain.projects','source-file',project='logic',path='private/secret-name.txt',scope='project')
 with pytest.raises(ValueError) as e:F.request(root,O.owned_workspace('http'),{'facet':'object','reference':private})
 assert 'secret-name' not in str(e.value) and 'PRIVATE_SENTINEL' not in str(e.value)
 (root/'packet-proof.json').write_text(json.dumps({'descriptor':descriptor,'packet':packet},indent=2))

def test_explicit_consumption_reconsideration_and_judgement_no_pure_read_write(scene):
 root,home=scene;claim=R.reference('concept','logic','result:one');result=R.reference('research-record','logic','R7')
 c=R.read(root,'logic',claim);r=R.read(root,'logic',result);author=lambda request,current:{'actor':'public-author','kind':'author','authority':'actual test operator'}
 bind={'reference':claim,'expected_basis':c['basis'],'request_id':'bind-public-consumption','operation':'bind-consumed','consumed_bases':[{'reference':result,'basis':r['basis']}]}
 R.change(root,'logic',bind,admit=author)
 assert R.change(root,'logic',bind,admit=author)['reused']
 ledger=root/'corpus_friction/logic.jsonl';before=ledger.read_bytes()
 dependents=O.request(root,O.owned_workspace('sdk'),{'facet':'dependents','reference':result,'changed_basis':r['basis'],'change_kind':'assumption'})
 assert ledger.read_bytes()==before and [x['dependent']['identity']['node'] for x in dependents['items']]==['result:one']
 assert dependents['coverage']['state']=='RECORDED_ONLY'
 c=R.read(root,'logic',claim);mark={'reference':claim,'expected_basis':c['basis'],'request_id':'mark-public-assumption','operation':'mark-reconsideration','concern_id':'public-cutoff','changed':{'reference':result,'basis':r['basis']},'change_kind':'assumption','summary':'A changed scientific assumption, not a byte freshness assertion.'}
 R.change(root,'logic',mark,admit=author);c=R.read(root,'logic',claim)
 clear={'reference':claim,'expected_basis':c['basis'],'expected_concern_basis':identity.canonical_digest(c['concerns'][0]),'request_id':'clear-public-assumption','operation':'clear-reconsideration','concern_id':'public-cutoff','disposition':'UNCHANGED','summary':'Producer says unchanged','evidence':[]}
 with pytest.raises(ValueError,match='scientific assumption'):R.change(root,'logic',clear,admit=author)
 clear['disposition']='REVISE'
 with pytest.raises(ValueError,match='bound judgement'):R.change(root,'logic',clear,admit=lambda r,c:{'kind':'revalidation','actor':'producer'})
 out=R.change(root,'logic',clear,admit=lambda r,c:{'kind':'judgement','actor':'public-independent-review','authority':'controlled existing owner seam'})
 c=R.read(root,'logic',claim);assert c['concerns'][0]['state']=='DISPOSED' and c['concerns'][0]['disposition']=='REVISE'
 assert len(c['value']['projection']['research_object_history'])==3
 pointer=out['concern'];assert R.read(root,'logic',pointer['reference'])['basis']==pointer['basis']
 assert R.change(root,'logic',clear,admit=author)['concern']==pointer
 (root/'dependents-proof.json').write_text(json.dumps({'pure':dependents,'concern':c['concerns'],'effect':out},indent=2))


def test_actual_issued_http_object_body_input_and_record_bounds(scene):
 from laplace.web import project_work_surface
 root,home=scene;scope=O.owned_workspace('http');reference=F.ref('domain.projects','source-file',project='logic',path='data/method.txt',scope='project')
 for fields in [{'facet':'object','reference':reference},{'facet':'object','reference':reference,'section':'body','offset':3,'limit':4000}]:
  h=F.handle(fields);u=urlsplit(h['http']['url']);code,_,raw=project_work_surface.handle(u.path,parse_qs(u.query),'GET',repo_root=root)
  assert code==200,json.loads(raw)
  value=json.loads(raw);assert value['scope_id']
  if fields.get('section')=='body':assert value['items'][0]['content']==(root/'logic/data/method.txt').read_text()[3:]
 body=F.handle({'facet':'object','reference':reference,'section':'body','offset':3,'limit':10,'as_of':value['basis']})
 h=F.handle({'facet':'input','reference':reference,'read':body});u=urlsplit(h['http']['url']);code,_,raw=project_work_surface.handle(u.path,parse_qs(u.query),'GET',repo_root=root)
 assert code==200,json.loads(raw)
 emitted=json.loads(raw);assert emitted['input_descriptor']['selection']=={'offset':3,'limit':10}
 with pytest.raises(ValueError):O.request(root,scope,{'facet':'workspace','limit':4000})
 (root/'http-input-proof.json').write_text(json.dumps({'object':value,'input':emitted},indent=2))


def test_existing_workflow_owner_reference_and_pointer_remain_project_scoped(scene):
 from laplace.pipeline import workflow_definitions as D
 root,home=scene
 body={'schema_version':D.SCHEMA,'title':'Public review definition','description':'Exact authored workflow purpose.','settings':{},'layout':{},'steps':[{'id':'writer','title':'Writer','parent_id':None,'assignment':{'role':'builder','instructions':'Return a proposal only.','settings':{}}}],'edges':[]}
 saved=D.save(root,O.project_scope('logic','sdk'),{'request_id':'public-research-object-definition','expected_revision':None,'definition':body})
 reference=D.reference(saved['definition_id'],saved['version'])
 root_value=F.request(root,O.owned_workspace('sdk'),{'facet':'workspace','family':'workflow-definition'})
 assert root_value['items'][0]['reference']==reference
 selected=F.request(root,O.owned_workspace('sdk'),{'facet':'object','reference':reference})
 assert selected['facets']['purpose']['value']['summary']==body['description']
 assert F.resolve_object_context(root,'logic',{'reference':reference,'expected_basis':selected['basis']})['reference']==reference
 with pytest.raises(ValueError):F.resolve_object_context(root,'different',{'reference':reference,'expected_basis':selected['basis']})
 (root/'definition-facet-proof.json').write_text(json.dumps({'workspace':root_value,'selected':selected},indent=2))


def test_question_request_exact_replay_settlement_and_late_original(scene,monkeypatch):
 from laplace.web import project_work_surface
 root,home=scene
 def post(payload):
  code,_,raw=project_work_surface.handle('/work/object-change',{},'POST',json.dumps(payload).encode(),root)
  return code,json.loads(raw)
 action=F._question_actions(root,'logic')[0];original={**action['http']['payload'],'meaning':'A public question'}
 assert R.question_request(root,'logic',original)['state']=='NONE'
 code,made=post(original);assert code==200 and made['state']=='RECORDED',made
 assert post(original)[1]['record_id']==made['record_id']
 changed={**original,'meaning':'Changed intent'}
 assert post(changed)[0]==422
 stale={**F._question_actions(root,'logic')[0]['http']['payload'],'meaning':'Stale question'}
 # Owner edition changes are explicit; manufacture no new current guard for old wire.
 from laplace.research import corpus_ingest
 corpus_ingest.rewire_add(root,'logic',{'kind':'add-node','node':'other:public','node_kind':'question','essence':'Another author question','by':'fixture'})
 code,terminal=post(stale);assert code==200 and terminal['state']=='NOT_ADMITTED',terminal
 assert post(stale)[1]['record_id']==terminal['record_id']
 absent={**F._question_actions(root,'logic')[0]['http']['payload'],'meaning':'An unconfirmed original'}
 code,settled=post({'project':'logic','operation':'settle-question','original_request':absent})
 assert code==200 and settled['state']=='NOT_ADMITTED' and settled['reason_code']=='EXPLICITLY_SETTLED',settled
 assert post(absent)[1]['state']=='NOT_ADMITTED'
 assert absent['node'] not in concepts._network('logic',root)['nodes']
 assert settled['new_decision_read'] and settled['reconcile']
 u=urlsplit(settled['reconcile']['http']['url']);code,_,raw=project_work_surface.handle(u.path,parse_qs(u.query),'GET',repo_root=root)
 assert code==200 and json.loads(raw)['state']=='NOT_ADMITTED' and json.loads(raw)['terminal'] is True
 (root/'question-recovery-proof.json').write_text(json.dumps({'recorded':made,'stale':terminal,'settled':settled},indent=2))


def test_question_claim_method_result_with_real_selected_consumption(scene):
 root,home=scene;scope=O.owned_workspace('sdk')
 question={**F._question_actions(root,'logic')[0]['http']['payload'],'meaning':'Does this method support the claim?'}
 q=F.change(root,scope,question,door={'origin':'sdk'});assert q['state']=='RECORDED',q
 source=F.ref('domain.projects','source-file',project='logic',path='data/method.txt',scope='project')
 observed=F._observe(root,scope,source);descriptor=F.input_from_read(root,scope,source,observed['read'])
 selected=F.request(root,scope,{'facet':'object','reference':q['reference']});assert selected['facets']['purpose']['value']['title']=='Question';actions=[x for x in selected['facets']['actions']['items'] if x['id'].startswith('create-')]
 results=[]
 for template in actions:
  action=next(x for x in F.request(root,scope,{'facet':'object','reference':q['reference']})['facets']['actions']['items'] if x['id']==template['id'])
  wire={**action['http']['payload'],'meaning':'Public '+action['title'],'inputs':[descriptor]}
  result=F.change(root,scope,wire,door={'origin':'sdk'});assert result['state']=='RECORDED',result
  actual=R.read(root,'logic',result['reference']);assert actual['consumed_bases']==[{'reference':source,'basis':observed['basis']}]
  assert F.change(root,scope,wire,door={'origin':'sdk'})['record_id']==result['record_id']
  results.append(result)
 assert len(results)==3
 (root/'scientific-route-proof.json').write_text(json.dumps({'question':q,'objects':results,'input':descriptor},indent=2))


def test_selected_portable_handover_fresh_recipient_without_origin(scene,tmp_path):
 from laplace.projects import project_handover as H,material_intake
 from laplace.pipeline import workflow_definitions as D
 root,home=scene;scope=O.owned_workspace('sdk')
 artifact=artifacts.store(root,'logic',{'path':'public/evidence.txt','scope':'project','before':None,'content':'Complete selected public evidence Ω.'})
 source=F.ref('domain.projects','source-file',project='logic',path='data/method.txt',scope='project')
 art=F.ref('domain.projects','artifact',project='logic',id=artifact['id'])
 claim=R.reference('concept','logic','result:one');result=R.reference('research-record','logic','R7')
 body={'schema_version':D.SCHEMA,'title':'Selected method','description':'Public exact method definition','settings':{},'layout':{},'steps':[{'id':'review','title':'Review','parent_id':None,'assignment':{'role':'critic','instructions':'Review only the explicit packet.','settings':{}}}],'edges':[]}
 saved=D.save(root,O.project_scope('logic','sdk'),{'request_id':'portable-definition','expected_revision':None,'definition':body})
 definition=D.reference(saved['definition_id'],saved['version'])
 entries=[{'class':'included','reference':ref,'expected_basis':F._observe(root,scope,ref)['basis'],'permit_export':True} for ref in [source,art,claim,result,definition]]
 entries += [{'class':'private_not_included','reason_code':'NOT_INCLUDED'},{'class':'unavailable'},{'class':'external','public_locator':'https://example.org/public-paper'},{'class':'runtime-unbound','provider':'public-provider','model':'unbound-model'}]
 payload={'project':'logic','action':'prepare','request_id':'public-portable-research-handover','entries':entries,'max_files':100,'max_rows':100,'max_bytes':2_000_000}
 value=H.object_request(root,scope,payload,door={'origin':'sdk'});assert value['state']=='RECORDED',value
 assert H.object_request(root,scope,payload,door={'origin':'sdk'})['reused']
 destination=tmp_path/'recipient';exported=H.object_request(root,scope,{'project':'logic','action':'export','reference':value['reference'],'expected_basis':value['basis'],'destination':str(destination)},door={'origin':'sdk'})
 assert exported['status']=='EXPORTED' and exported['inspection']['state']=='REOPENED'
 assert not (destination/'logic/private').exists() and not (destination/'corpus_friction/logic.jsonl').exists()
 manifest=H._json_artifact(destination,'logic',value['reference']['identity']['id'])[0]
 public_bytes=b''.join(p.read_bytes() for p in destination.rglob('*') if p.is_file())
 assert b'PRIVATE_SENTINEL' not in public_bytes and b'secret-name' not in public_bytes and str(root).encode() not in public_bytes
 # No origin fallback: move the entire original public workspace before reopening.
 root.rename(tmp_path/'offline-origin')
 inspection=H.inspect_handover(destination);reopened=H._inspect_object(destination)
 assert reopened['origin_reads']==0 and inspection['providers_started']==0
 assert artifacts.read(destination,'logic',{'id':artifact['id'],'expected_sha256':artifact['revision'],'limit':4000})['content']=='Complete selected public evidence Ω.'
 assert D.read(destination,O.owned_workspace('sdk'),{'reference':definition,'facet':'inspect'})['definition']['description']==body['description']
 (tmp_path/'portable-proof.json').write_text(json.dumps({'prepared':value,'export':exported,'inspection':inspection,'reopened':reopened,'manifest':manifest},indent=2))


def test_artifact_real_http_page_input_and_bind_receipt(scene):
 from laplace.projects import material_intake
 root,home=scene;scope=O.owned_workspace('sdk')
 saved=artifacts.store(root,'logic',{'path':'public/selected.txt','scope':'project','before':None,'content':'Public exact Unicode Ω source.'})
 ref=F.ref('domain.projects','artifact',project='logic',id=saved['id']);observed=F._observe(root,scope,ref)
 issued=observed['read'];u=urlsplit(issued['http']['url'])
 code,_,raw=material_intake.http(u.path,parse_qs(u.query),'GET',b'',root)
 page=json.loads(raw);assert code==200 and page['content']=='Public exact Unicode Ω source.',page
 descriptor=F.input_from_read(root,scope,ref,page['page_read']);assert identity.revision_matches(descriptor['expected_basis'],saved['revision'])
 claim=R.reference('concept','logic','result:one');value=F.request(root,scope,{'facet':'object','reference':claim})
 action=next(x for x in value['facets']['actions']['items'] if x['id']=='bind-consumed')
 original={**action['http']['payload'],'inputs':[descriptor]}
 out=F.change(root,scope,original,door={'origin':'sdk'});assert out['state']=='RECORDED'
 status=F.request(root,scope,{'facet':'object-request','project_lens':'logic','object_request':original})
 assert status['state']=='RECORDED' and status['event']['record_id']==out['event']['record_id']
 assert value['conversation']['available'] and value['conversation']['project']=='logic'
 (root/'artifact-bind-proof.json').write_text(json.dumps({'page':page,'descriptor':descriptor,'action':action,'receipt':out,'status':status},indent=2))


def test_registered_native_http_owner_contract_and_scope(scene):
 from laplace.native import tools
 from laplace.native.declarations import DECLARATIONS,HTTP_DECLARATIONS
 from laplace.writing import reads
 from jsonschema import Draft202012Validator
 root,home=scene
 assert reads.effect('research_handover',{'action':'request'})=='read'
 assert reads.effect('research_handover',{'action':'prepare'})=='write'
 value=tools.execute(root,'logic','work','research_handover',{'action':'request','request_id':'not-yet-public'})
 assert value['state']=='NONE'
 wire={**F._question_actions(root,'logic')[0]['http']['payload'],'meaning':'Native cannot invent an active author.'}
 with pytest.raises(ValueError):tools.execute(root,'logic','work','research_object_change',wire)
 assert R.question_request(root,'logic',wire)['state']=='NONE'
 for name,original in [('research_object_change',wire),('research_handover',{'action':'request','request_id':'not-yet-public'})]:
  assert not list(Draft202012Validator(DECLARATIONS[name].payload).iter_errors(original))
 for name,original in [('work/object-change',wire),('work/object-handover',{'project':'logic','action':'request','request_id':'not-yet-public'}),('work/object-discovery',{'facet':'workspace'})]:
  assert not list(Draft202012Validator(HTTP_DECLARATIONS[name].payload).iter_errors(original))
 (root/'declared-doors-proof.json').write_text(json.dumps({'native':value,'question':wire,'registered':list(DECLARATIONS)[-5:]},indent=2))


def test_exact_selected_reads_version_fence_and_reference_pure_capture(scene,tmp_path):
 from laplace.projects import material_intake
 from test_retained_source_literature import tree,seed_original,wire
 from laplace.research import literature
 root,home=scene;scope=O.owned_workspace('sdk')
 saved=artifacts.store(root,'logic',{'path':'public/window.txt','scope':'project','before':None,'content':'0123 Ω selected exact tail'})
 ref=F.ref('domain.projects','artifact',project='logic',id=saved['id']);basis=F._observe(root,scope,ref)['basis']
 packet=F.capture_inputs(root,'logic',{'entries':[{'reference':ref,'expected_basis':basis,'selection':{'offset':5,'limit':8}}]})
 issued=packet['entries'][0]['read'];u=urlsplit(issued['http']['url']);code,_,raw=material_intake.http(u.path,parse_qs(u.query),'GET',b'',root)
 assert code==200 and json.loads(raw)['content']==packet['entries'][0]['content']=='Ω selec'
 assert packet['entries'][0]['source_receipt']['units']=='UTF-8 bytes' and packet['entries'][0]['source_receipt']['end']==13
 source=F.ref('domain.projects','source-file',project='logic',path='data/method.txt',scope='project');pin=F._observe(root,scope,source)['basis']
 with pytest.raises(ValueError):F.capture_inputs(root,'logic',{'entries':[{'reference':source,'expected_basis':pin,'selection':{'pointer':'/fabricated'}}]})
 with pytest.raises(ValueError):F.resolve_object_context(root,'logic',{'reference':{**source,'version':{'unknown':'ignored?'}},'expected_basis':pin})
 other=tree(tmp_path/'reference',manuscript=False);original,_raw=seed_original(other);code,stored=literature.import_reference('p',wire(original),other);assert code==201
 reference=R.reference('reference','p',stored['association']['key']);observed=F._observe(other,scope,reference)
 page=observed['facets']['inputs_outputs']['items'][0]['read'];before=(other/'p/manuscript/references.json').read_bytes()
 descriptor=F.input_from_read(other,scope,reference,page);captured=F.capture_inputs(other,'p',{'entries':[descriptor]})
 assert captured['entries'][0]['content']==_raw.decode() and (other/'p/manuscript/references.json').read_bytes()==before
 (root/'exact-selected-read-proof.json').write_text(json.dumps({'packet':packet,'issued':json.loads(raw),'reference_descriptor':descriptor,'reference_packet':captured},indent=2))


def test_question_lost_ack_and_custody_unknown_do_not_duplicate(scene,monkeypatch):
 from laplace.research import corpus_ingest
 root,home=scene;scope=O.owned_workspace('sdk');original={**F._question_actions(root,'logic')[0]['http']['payload'],'meaning':'One exact question after a lost acknowledgement'}
 real=corpus_ingest.rewire_add
 def lost(*args,**kwargs):
  real(*args,**kwargs);raise OSError('Synthetic lost acknowledgement after actual canonical append')
 monkeypatch.setattr(corpus_ingest,'rewire_add',lost)
 value=F.change(root,scope,original,door={'origin':'sdk'});assert value['state']=='RECORDED'
 assert F.change(root,scope,original,door={'origin':'sdk'})['record_id']==value['record_id']
 ledger=root/'corpus_friction/logic.jsonl';before=ledger.read_bytes();assert before.count(original['request_id'].encode())==1
 ledger.write_bytes(before+b'not-json\n');corrupt=ledger.read_bytes()
 assert R.question_request(root,'logic',original)['state']=='UNKNOWN'
 assert F.change(root,scope,original,door={'origin':'sdk'})['state']=='UNKNOWN' and ledger.read_bytes()==corrupt
 (root/'lost-ack-proof.json').write_text(json.dumps({'recorded':value,'unknown':R.question_request(root,'logic',original)},indent=2))


def test_handover_privacy_permission_and_exact_export_reconciliation(scene,tmp_path):
 from laplace.projects import project_handover as H
 root,home=scene;scope=O.owned_workspace('sdk');source=F.ref('domain.projects','source-file',project='logic',path='data/method.txt',scope='project')
 payload={'project':'logic','action':'prepare','request_id':'small-public-reconcile','entries':[{'class':'included','reference':source,'expected_basis':F._observe(root,scope,source)['basis'],'permit_export':True}], 'max_files':30,'max_rows':30,'max_bytes':200000}
 talk=root/'contract/talk.jsonl';before=talk.read_bytes() if talk.exists() else None
 for extra in [{'class':'private_not_included','path':'private/secret-name.txt','sha256':'a'*64},{'class':'runtime-unbound','provider':'public','model':'model','version':{'private_path':'hidden'}}]:
  with pytest.raises(ValueError):H.object_request(root,scope,{**payload,'entries':payload['entries']+[extra]},door={'origin':'sdk'})
  assert (talk.read_bytes() if talk.exists() else None)==before
 with pytest.raises(ValueError):H.object_request(root,O.project_scope('logic','native'),payload,door={'origin':'native'})
 value=H.object_request(root,scope,payload,door={'origin':'sdk'});destination=tmp_path/'recipient-small'
 art=F.request(root,scope,{'facet':'object','reference':value['reference']});assert art['facets']['actions']['items'][0]['id']=='inspect-handover'
 body=H._json_artifact(root,'logic',value['reference']['identity']['id'])[0]
 fake=artifacts.store(root,'logic',{'path':'public/fake-handover.json','scope':'project','before':None,'content':json.dumps(body)})
 fake_ref=F.ref('domain.projects','artifact',project='logic',id=fake['id'])
 assert not F.request(root,scope,{'facet':'object','reference':fake_ref})['facets']['actions']['items']
 with pytest.raises(ValueError):H.object_request(root,scope,{'project':'logic','action':'read','reference':fake_ref},door={'origin':'sdk'})
 inspect={'project':'logic','action':'inspect','reference':value['reference'],'expected_basis':value['basis'],'destination':str(destination)}
 assert H.object_request(root,scope,inspect,door={'origin':'sdk'})['state']=='NONE'
 H.object_request(root,scope,{**inspect,'action':'export'},door={'origin':'sdk'})
 complete=H.object_request(root,scope,inspect,door={'origin':'sdk'});assert complete['state']=='COMPLETE_MATCH'
 (destination/'project-handover.json').write_text('incomplete public destination')
 assert H.object_request(root,scope,inspect,door={'origin':'sdk'})['state']=='UNKNOWN'
 with pytest.raises(ValueError):H.object_request(root,O.project_scope('logic','native'),inspect,door={'origin':'native'})
 (root/'handover-reconcile-proof.json').write_text(json.dumps({'prepared':value,'complete':complete,'unknown':H.object_request(root,scope,inspect,door={'origin':'sdk'})},indent=2))


def test_actual_pdf_selected_page_packet_is_text_not_whole_source(scene,tmp_path,monkeypatch):
 from test_writing_sources import _two_page_pdf
 from laplace.writing import records
 from laplace.projects import project_handover as H
 from laplace.projects import writing_sources
 real_tool=writing_sources._tool
 monkeypatch.setattr(writing_sources,'_tool',lambda name:'/usr/bin/'+name if name in {'pdfinfo','pdftotext'} else real_tool(name))
 root,home=scene;scope=O.owned_workspace('sdk');pdf=root/'logic/public/pages.pdf';pdf.parent.mkdir(exist_ok=True);_two_page_pdf(pdf)
 pin=identity.bytes_digest(pdf.read_bytes());ident='ART-public-two-page-source'
 records.bank(root,{'record':'writing-artifact','id':ident,'project':'logic','path':'logic/public/pages.pdf','artifact_path':'public/pages.pdf','scope':'project','sha256':pin.removeprefix('sha256:')})
 ref=F.ref('domain.projects','artifact',project='logic',id=ident)
 packet=F.capture_inputs(root,'logic',{'entries':[{'reference':ref,'expected_basis':pin,'selection':{'page':2,'page_count':1,'offset':0,'limit':2000}}]})
 entry=packet['entries'][0];assert 'SECOND PAGE TOKEN' in entry['content'] and 'FIRST PAGE TOKEN' not in entry['content']
 assert entry['source_receipt']['pdf_total_pages']==2 and entry['source_receipt']['pdf_page_start']==2
 assert entry['source_receipt']['extraction_state']=='TEXT_EXTRACTED' and not entry['coverage']['whole_source']
 desc=F.input_from_read(root,scope,ref,entry['read']);assert desc['selection']['page']==2 and desc['selection']['page_count']==1
 prepared=H.object_request(root,scope,{'project':'logic','action':'prepare','request_id':'public-pdf-portable','entries':[{'class':'included','reference':ref,'expected_basis':pin,'permit_export':True}], 'max_files':30,'max_rows':30,'max_bytes':200000},door={'origin':'sdk'})
 dest=tmp_path/'pdf-recipient';H.object_request(root,scope,{'project':'logic','action':'export','reference':prepared['reference'],'expected_basis':prepared['basis'],'destination':str(dest)},door={'origin':'sdk'})
 assert artifacts.identity(dest,'logic',{'id':ident})['revision']==pin.removeprefix('sha256:')
 assert (dest/'logic/public/pages.pdf').read_bytes()==pdf.read_bytes()
 (root/'pdf-selected-packet-proof.json').write_text(json.dumps({'packet':packet,'descriptor':desc,'portable':prepared,'reopened':H._inspect_object(dest)},indent=2))


def test_created_child_settlement_does_not_require_removed_parent(scene):
 from laplace.research import corpus_ingest
 root,home=scene;scope=O.owned_workspace('sdk');q=F.change(root,scope,{**F._question_actions(root,'logic')[0]['http']['payload'],'meaning':'A removable public question'},door={'origin':'sdk'})
 original={**F._question_actions(root,'logic',q['reference']['identity']['node'])[0]['http']['payload'],'meaning':'An unconfirmed child'}
 corpus_ingest.rewire_add(root,'logic',{'kind':'delete-node','node':q['reference']['identity']['node'],'by':'fixture'})
 result=F.change(root,scope,{'project':'logic','operation':'settle-question','original_request':original},door={'origin':'sdk'})
 assert result['state']=='NOT_ADMITTED' and result['terminal']
 assert F.change(root,scope,original,door={'origin':'sdk'})['state']=='NOT_ADMITTED'
 assert original['node'] not in concepts._network('logic',root)['nodes']
 (root/'removed-parent-settlement-proof.json').write_text(json.dumps(result,indent=2))


def test_actual_scoped_workflow_library_starter_save_and_existing_global_custody(scene):
 from laplace.web import project_work_surface,workflow_definitions_surface
 from laplace.pipeline import workflow_definitions as D
 from laplace import sdk
 root,home=scene;scope=O.owned_workspace('http')
 workspace=F.request(root,scope,{'facet':'workspace','project_lens':'logic'})
 h=workspace['workflow_library']['read'];u=urlsplit(h['http']['url'])
 code,_,raw=workflow_definitions_surface.handle(u.path,parse_qs(u.query),'GET',repo_root=root);listing=json.loads(raw)
 assert code==200 and listing['scope']['kind']=='project' and listing['scope']['namespace']=='logic',listing
 assert sdk.workflow_request(h['request'],root=root)['scope']['namespace']=='logic'
 u=urlsplit(listing['starters_read']['http']['url']);code,_,raw=workflow_definitions_surface.handle(u.path,parse_qs(u.query),'GET',repo_root=root)
 starter=json.loads(raw)['starters'][0];action=listing['actions']['create'];assert action['payload']['scope']=={'kind':'project','namespace':'logic'}
 u=urlsplit(action['http']['url']);code,_,raw=workflow_definitions_surface.handle(u.path,parse_qs(u.query),'POST',json.dumps({**action['payload'],'request_id':'real-library-public-save','definition':starter}).encode(),root)
 saved=json.loads(raw);assert code==200 and saved['scope']=={'kind':'project','namespace':'logic'},saved
 assert parse_qs(urlsplit(saved['read']['http']['url']).query)['project_lens']==['logic']
 value=F.request(root,scope,{'facet':'object','project_lens':'logic','reference':saved['reference']})
 assert value['conversation']['project']=='logic' and value['facets']['actions']['items'][0]['read']['request']['project_lens']=='logic'
 global_saved=D.save(root,O.owned_workspace('sdk'),{'request_id':'explicit-global-public-save','expected_revision':None,'definition':starter})
 global_value=F.request(root,scope,{'facet':'object','project_lens':'logic','reference':global_saved['reference']})
 assert global_value['subject']==global_saved['reference'] and global_value['conversation']['project'] is None
 u=urlsplit(h['http']['url']);bad=parse_qs(u.query);bad['project_lens']=['unknown'];assert workflow_definitions_surface.handle(u.path,bad,'GET',repo_root=root)[0]==422
 (root/'scoped-library-proof.json').write_text(json.dumps({'listing':listing,'saved':saved,'selected':value,'global':global_value},indent=2))


from test_research_workflow_runs import run_root,start_run

def test_actual_prepared_work_read_and_only_admitted_consumed_dependency(run_root):
 from laplace.work import owner_discovery as O
 s=run_root;root=s['root'];scope=O.owned_workspace('http');ref=O.work_reference('book',s['work'])
 value=F.request(root,scope,{'facet':'object','reference':ref})
 offered=value['facets']['feedback']['value']['read'];assert offered['native']['payload']=={'action':'workflow-status','work_id':s['work']}
 source=s['entry']['reference']
 before=F.request(root,scope,{'facet':'dependents','reference':source})
 assert not any(x['dependent']==ref for x in before['items'])
 start_run(s)
 after=F.request(root,scope,{'facet':'dependents','reference':source})
 matches=[x for x in after['items'] if x['dependent']==ref]
 assert matches and all(x['relation']=='admitted-evidence-packet' and x['turn_id'] for x in matches)
 assert after['coverage']['admitted_workflow_coverage']['state']=='RECORDED_ADMISSIONS_ONLY'
 (root/'work-run-consumption-proof.json').write_text(json.dumps({'work':value,'prepared':before,'admitted':after},indent=2))


def test_issued_consequence_actions_and_lazy_manuscript_selection(scene):
 from laplace.web import project_work_surface
 from laplace.pipeline import authoring
 root,home=scene;scope=O.owned_workspace('http')
 (home/'main.tex').write_text('\\documentclass{article}\n\\begin{document}\nPublic source chosen for a proposal.\n\\end{document}\n')
 def get(h):
  u=urlsplit(h['http']['url']);code,_,raw=project_work_surface.handle(u.path,parse_qs(u.query),'GET',repo_root=root)
  assert code==200,json.loads(raw)
  return json.loads(raw)
 def post(action,fields):
  code,_,raw=project_work_surface.handle(action['http']['url'],{},'POST',json.dumps({**action['http']['payload'],**fields}).encode(),root)
  assert code==200,json.loads(raw)
  return json.loads(raw)
 workspace=F.request(root,scope,{'facet':'workspace','project_lens':'logic'})
 choices=get(workspace['manuscript_choices_read']);assert choices['state']=='AVAILABLE'
 choice=choices['choices'][0];actual=authoring.inspect('logic',selection=choice['selection'],repo_root=root)
 assert actual['sources'] and choice['basis']['selection_identity']
 source=R.reference('research-record','logic','R7');claim=R.reference('concept','logic','result:one');unrelated=R.reference('concept','logic','def:one')
 before_unrelated=R.read(root,'logic',unrelated)
 R.change(root,'logic',{'reference':claim,'expected_basis':R.read(root,'logic',claim)['basis'],'request_id':'issued-consumption','operation':'bind-consumed','consumed_bases':[{'reference':source,'basis':R.read(root,'logic',source)['basis']}]},admit=lambda *_:{'kind':'author','actor':'public test operator'})
 selected=F.request(root,scope,{'facet':'object','reference':source});ledger=root/'corpus_friction/logic.jsonl';before=ledger.read_bytes()
 dependencies=get(selected['dependents_read']);kind=next(x for x in dependencies['controls']['change_kind']['choices'] if x['id']=='assumption')
 dependencies=get(kind['read']);assert ledger.read_bytes()==before and len(dependencies['items'])==1
 mark=dependencies['items'][0]['actions'][0];made=post(mark,{'summary':'A changed cutoff assumption needs a reasoned judgement.'})
 view=get(made['read']);concern=get(view['facets']['feedback']['items'][0]['read'])
 action=concern['facets']['actions']['items'][0];assert 'UNCHANGED' not in action['fields'][0]['choices']
 out=post(action,{'disposition':'REVISE','summary':'Revise the cutoff argument; source freshness alone does not answer this concern.'})
 assert R.read(root,'logic',out['concern']['reference'])['value']['state']=='DISPOSED'
 after_unrelated=R.read(root,'logic',unrelated)
 assert {k:v for k,v in after_unrelated.items() if k!='mutation_revision'}=={k:v for k,v in before_unrelated.items() if k!='mutation_revision'}
 (root/'issued-consequences-selection-proof.json').write_text(json.dumps({'choices':choices,'dependencies':dependencies,'mark':made,'concern':concern,'disposition':out},indent=2))


def test_manuscript_choice_reads_pinned_existing_source_body(scene):
 from laplace.web import project_work_surface
 root,home=scene;content='Public exact selected manuscript prose.\n';(home/'main.tex').write_text(content)
 choices=F.request(root,O.owned_workspace('http'),{'facet':'manuscript-selection','project_lens':'logic'})
 assert choices['choices']
 proof=[]
 for choice in choices['choices']:
  u=urlsplit(choice['read']['http']['url']);code,_,raw=project_work_surface.handle(u.path,parse_qs(u.query),'GET',repo_root=root)
  assert code==200,raw
  actual=json.loads(raw);assert actual['items'][0]['content']==content
  assert choice['selection']['source_observation']['file_revisions']
  proof.append({'choice':choice,'read':actual})
 (home/'main.tex').write_text(content+'Changed.\n')
 u=urlsplit(choices['choices'][-1]['read']['http']['url']);code,_,raw=project_work_surface.handle(u.path,parse_qs(u.query),'GET',repo_root=root)
 assert code==422 and json.loads(raw)['code']=='CHANGED_INPUT',raw
 (root/'pinned-manuscript-choice-read-proof.json').write_text(json.dumps({'reads':proof,'changed_status':code},indent=2))


def test_registered_research_adapter_uses_actual_project_capability(scene,monkeypatch):
 from laplace.web import research_surface
 from laplace.projects import library
 root,home=scene;scope=O.owned_workspace('http')
 workspace=F.request(root,scope,{'facet':'workspace'})
 assert not any(x['id']=='registered-research' for x in workspace['facets']['actions']['items'])
 selected=F.request(root,scope,{'facet':'workspace','project_lens':'logic'})
 action=next(x for x in selected['facets']['actions']['items'] if x['id']=='registered-research')
 assert action['adapter']=={'kind':'research-evidence','project':'logic'}
 u=urlsplit(action['read']['http']['url']);code,_,raw=research_surface.handle(u.path,parse_qs(u.query),'GET',b'',root)
 assert code==200,raw
 assert any(x['id']=='R7' for x in json.loads(raw)['results'])
 record=F.request(root,scope,{'facet':'object','reference':R.reference('research-record','logic','R7')})
 assert record['facets']['actions']['state']=='AVAILABLE' and any(x['id']=='registered-research' for x in record['facets']['actions']['items'])
 code,made=library.create({'name':'notes','title':'Unserved source-optional notes','kind':'general'},root);assert code==201
 assert library.project_capabilities('notes',root)['capabilities']['research']
 monkeypatch.setattr(library,'project_capabilities',lambda *a,**k:{'capabilities':{'research':False}})
 notes=F.request(root,scope,{'facet':'workspace','project_lens':'notes'})
 assert not any(x['id']=='registered-research' for x in notes['facets']['actions']['items'])
 (root/'registered-research-entry-proof.json').write_text(json.dumps({'action':action,'summary':json.loads(raw),'selected_record':record,'unserved':notes},indent=2))


def test_research_original_run_request_http_native_and_declaration_are_pure(scene,monkeypatch):
 from laplace.research import research_runs as runs,research_catalogue
 from laplace.web import research_surface
 from laplace.native import tools
 from laplace.native.declarations import HTTP_DECLARATIONS
 from laplace.writing.schemas import SCHEMAS
 from jsonschema import Draft202012Validator
 from urllib.parse import urlencode
 root,home=scene;(home/'public_method.py').write_text('print("public inert registered method")\n')
 code,out=runs.register_producer('logic',{'id':'public-pure-request','executable':'public_method.py','scope':'manuscript','modes':['smoke'],'allowed_args':{'cutoff':'int'},'timeout_seconds':3},root)
 assert code==201,out
 code,summary=research_catalogue.state_read('logic',root,view='summary');assert code==200
 action=next(x for x in summary['producers'] if x['id']=='public-pure-request')['launch_action']
 wire={**action['http']['payload'],'mode':'smoke','args':{'cutoff':7},'runtime_seconds':3}
 assert 'project' not in wire
 monkeypatch.setattr(runs,'launch',lambda *a,**k:(_ for _ in ()).throw(AssertionError('Pure request read launched a producer.')))
 handle=action['request_read'];url=handle['http']['url']+'&'+urlencode({handle['query_field']:json.dumps(wire)})
 u=urlsplit(url);before=sorted(str(f.relative_to(root)) for f in root.rglob('*') if f.is_file())
 code,_,raw=research_surface.handle(u.path,parse_qs(u.query),'GET',b'',root);assert code==200,raw
 value=json.loads(raw);assert value['effect']=='NONE' and value['original_request']==wire and value['request_id']==wire['request_id']
 assert before==sorted(str(f.relative_to(root)) for f in root.rglob('*') if f.is_file())
 native=tools.execute(root,'logic','work','run_status',{'request':wire})
 assert native['effect']=='NONE' and native['id']==value['id'] and native['intent_digest']==value['intent_digest']
 assert not (home/'research_runs').exists()  # native transport may bank its ordinary audit, never a run
 assert not list(Draft202012Validator(HTTP_DECLARATIONS['research/run-request'].payload).iter_errors({'project':'logic','request':wire}))
 assert not list(Draft202012Validator(SCHEMAS['run_status']).iter_errors({'id':'existing-run'}))
 assert list(Draft202012Validator(SCHEMAS['run_status']).iter_errors({'id':'existing-run','request':wire}))
 assert list(Draft202012Validator(SCHEMAS['run_status']).iter_errors({'request':{k:v for k,v in wire.items() if k!='request_id'}}))
 for query in [dict(parse_qs(u.query),request=[json.dumps(wire),json.dumps(wire)]),dict(parse_qs(u.query),unexpected=['x']),{'project':['logic'],'request':['{"producer_id":"a","producer_id":"b"}']}]:
  status,_,reply=research_surface.handle(u.path,query,'GET',b'',root);assert status==422,reply
 code,_,old=research_surface.handle('/research/run/status',{'project':['logic'],'id':['not-a-run']},'GET',b'',root);assert code==404,old
 (root/'research-request-doors-proof.json').write_text(json.dumps({'action':action,'wire':wire,'http':value,'native':native,'legacy_status':code},indent=2))


def test_record_request_shared_doors_recover_exact_current_and_historical_save(scene,monkeypatch):
 from laplace.research import research_records as RR
 from laplace.web import research_surface
 from laplace.native import tools
 from laplace.native.declarations import HTTP_DECLARATIONS
 from jsonschema import Draft202012Validator
 from laplace.core.records import journal
 root,home=scene
 wire={'request_id':'public-record-first-request','record':{'kind':'result','id':'public-record-request','scope':'project','source':'data/method.txt','result':'data/result.json','title':'Public request boundary','summary':'Fixture tests record custody only.','limitations':'No supervised process or scientific acceptance asserted.'}}
 def get(h):
  u=urlsplit(h['http']['url']);code,_,raw=research_surface.handle(u.path,parse_qs(u.query),'GET',b'',root);assert code==200,raw
  return json.loads(raw)
 def post(value):return research_surface.handle('/research/record',{'project':['logic']},'POST',json.dumps(value).encode(),root)
 assert get(RR.request_read('logic',wire))['effect']=='NONE'
 real_response=RR._record_response
 monkeypatch.setattr(RR,'_record_response',lambda *a,**k:(_ for _ in ()).throw(OSError('Public lost post-publication response.')))
 with pytest.raises(OSError,match='post-publication'):post(wire)
 monkeypatch.setattr(RR,'_record_response',real_response)
 current=get(RR.request_read('logic',wire));assert current['effect']=='RECORDED' and not current['historical']
 native=tools.execute(root,'logic','work','research',{'view':'record-request','request':wire})
 assert native['record']==current['record'] and native['original_request']==wire
 detail=tools.execute(root,'logic','work',native['current_read']['native']['operation'],native['current_read']['native']['payload'])
 assert detail['result']['id']==wire['record']['id']
 selected=F.request(root,O.owned_workspace('http'),{'facet':'object','reference':R.reference('research-record','logic',wire['record']['id'])})
 history=selected['facets']['history']['value']['read'];assert history['native']['payload']['view']=='result' and get(history)['result']['id']==wire['record']['id']
 renewal=copy.deepcopy(wire);renewal['request_id']='public-record-renew-request';renewal['expected_revision']=current['record']['revision'];renewal['record']['summary']='Explicitly revised public interpretation.'
 real_bank=journal.bank_row
 monkeypatch.setattr(journal,'bank_row',lambda *a,**k:(_ for _ in ()).throw(OSError('Public post-publication journal interruption.')))
 with pytest.raises(OSError,match='journal interruption'):post(renewal)
 monkeypatch.setattr(journal,'bank_row',real_bank)
 updated=get(RR.request_read('logic',renewal));old=get(RR.request_read('logic',wire))
 assert updated['effect']=='RECORDED' and old['historical'] and old['record']==current['record']
 code,_,raw=post(wire);assert code==200 and json.loads(raw)['replayed']
 changed=copy.deepcopy(wire);changed['record']['summary']='Another intent using the same identity.'
 before=(home/'research_records.json').read_bytes();code,_,raw=post(changed);assert code==409 and json.loads(raw)['effect']=='CONFLICT'
 assert (home/'research_records.json').read_bytes()==before
 assert not list(Draft202012Validator(HTTP_DECLARATIONS['research/record'].payload).iter_errors({'project':'logic',**wire}))
 assert not list(Draft202012Validator(HTTP_DECLARATIONS['research/record-request'].payload).iter_errors({'project':'logic','request':wire}))
 (root/'record-result-request-doors-proof.json').write_text(json.dumps({'wire':wire,'current':current,'native':native,'updated':updated,'historical':old,'qualification':'Actual public canonical record owner and lost-ACK/history recovery; no fake COMPLETE run, process or scientific acceptance.'},indent=2))
