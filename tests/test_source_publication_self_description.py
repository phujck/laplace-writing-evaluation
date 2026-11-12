"""One public declaration/custody/read journey; no publication, device or host state."""
import copy,hashlib,json
from pathlib import Path
from urllib.parse import urlsplit,parse_qs,urlencode
import pytest
from laplace.core.identity import canonical_bytes
from laplace.representation import source_publication as P
from laplace.work import source_contracts as SC,source_kernel as K,owner_discovery as O,project_work as W,project_work_review as R

INPUTS=['src/laplace/representation/source_publication.py','src/laplace/work/source_kernel.py','src/laplace/engine/source_kernel_input.py','scripts/reembed.py','runtime_profiles.toml']
REF=SC.reference('domain.representation','source_publication')
NAMESPACE='source-publication-self-description-'+('x'*125)

def public_root(root):
 (root/NAMESPACE).mkdir();(root/'registry_projects.json').write_text(json.dumps({'projects':[{'name':NAMESPACE,'kind':'general','project_dir':NAMESPACE}]}))
 source=Path(__file__).resolve().parents[1]
 for rel in INPUTS:
  target=root/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((source/rel).read_bytes())
 return O.project_scope(NAMESPACE,'native')

def retained(root):
 scope=public_root(root);segments=list(P.source_contract()['segments'])
 binding={'owner':'domain.representation','operation':'source_publication','consumer':K.CONSUMER,'segments':segments}
 W.task(NAMESPACE,{'id':'public-kernel-owner','title':'Describe the public publisher','goal':'Exact operation facts only','review_obligations':[{'id':'prior','label':'Prior obligation kept','scope':'other'},{'id':'kernel-owner','label':'Kernel owner facts','scope':'source','inputs':INPUTS,'source_contract':binding}]},root)
 pins={rel:'sha256:'+hashlib.sha256((root/rel).read_bytes()).hexdigest() for rel in INPUTS}
 result=R.record(NAMESPACE,{'id':'public-kernel-owner','phase':'handoff','request_id':'public-kernel-owner-handoff','expected_work_revision':W._task_revision(W._tasks(NAMESPACE,root)['public-kernel-owner']),'object':{'kind':'source'},'pins':pins,'obligations':['kernel-owner']},root)
 selection={'namespace':NAMESPACE,'work_id':'public-kernel-owner','handoff_id':result['phase']['id'],'obligation_id':'kernel-owner'}
 held=result['phase']['source_contracts']['kernel-owner'];ref=SC.reference('domain.representation','source_publication',held['version'])
 return scope,selection,ref,segments,result

def http(root,handle):
 from laplace.web import project_work_surface as H
 parsed=urlsplit(handle['http']['url']);status,_,raw=H.handle(parsed.path,parse_qs(parsed.query),'GET',repo_root=root)
 assert status==200,raw
 return json.loads(raw)

def test_pure_factory_and_existing_dispatch_fields(tmp_path,monkeypatch):
 before=P.source_contract();assert before==P.source_contract() and len(before['segments'])==9
 assert [row['operation'] for row in SC.declarations()]==['work_review.followup','development_source','source_publication']
 assert before['segments']['composition']['steps']==before['steps']
 assert before['segments']['authority']['operator']['doors']==list(P.OPERATOR_DOORS)
 assert before['segments']['admission']['request']==P.contract()
 assert before['segments']['admission']['action_fields']=={key:list(value) for key,value in P.ACTION_FIELDS.items()}
 changed=P.source_contract();changed['segments']['authority']['operator']['doors'].append('native');assert P.source_contract()==before
 calls=[]
 wires=[('prepare',{'action':'prepare','inputs':[{}]}),
  ('commit',{'action':'commit','request_id':'public-dispatch-id','prepared':{},'expected_publication_basis':'sha256:'+'0'*64}),
  ('inspect_request',{'action':'request','request_id':'public-dispatch-id'}),
  ('recover',{'action':'recover','request_id':'public-dispatch-id'}),
  ('read_object',{'action':'object','reference':{},'selection':{},'segments':['authority'],'node_id':'OP-SOURCE-'+'0'*64,'content_handle':'sha256:'+'0'*64,'semantic_handle':'sha256:'+'0'*64,'publication_handle':'sha256:'+'0'*64})]
 for function,wire in wires:
  monkeypatch.setattr(P,function,lambda *args,key=function:calls.append(key) or {'state':'pure-test-dispatch'})
  assert P.request(tmp_path,O.owned_workspace('sdk'),wire)['state']=='pure-test-dispatch'
  for bad in [{**wire,'unexpected':True},{key:value for key,value in wire.items() if key!=next(k for k in wire if k!='action')}]:
   with pytest.raises(ValueError):P.request(tmp_path,O.owned_workspace('sdk'),bad)
 assert calls==[function for function,_ in wires]
 monkeypatch.undo()
 monkeypatch.setattr(K,'prepare_publication_inputs',lambda *_:pytest.fail('Project caller reached input custody'))
 for scope in [O.project_scope('p','native'),O.owned_workspace('native'),O.project_scope('p','sdk')]:
  with pytest.raises(ValueError,match='TRUSTED_OPERATOR_ONLY'):P.request(tmp_path,scope,{'action':'prepare','inputs':[{}]})


def test_current_constituent_actual_doors_and_observation(tmp_path,monkeypatch):
 scope=public_root(tmp_path);from laplace import sdk
 from laplace.native import tools
 payload={'facet':'source-kernel','view':'declaration','reference':REF,'namespace':NAMESPACE,'budget':15360}
 coarse=K.read(tmp_path,scope,payload);template=coarse['constituent_read'];assert 'version' not in template['request']['reference']
 assert len(coarse['declaration']['segments'])==9 and len(coarse['declaration']['steps'])==8
 selected=[]
 for name in ['segment:admission','step:prepare']:
  assert template['values'][name]==name
  req={**template['request'],template['field']:name};query=parse_qs(urlsplit(template['http']['url']).query);query[template['query_field']]=[name]
  handle={'request':req,'http':{'method':'GET','url':urlsplit(template['http']['url']).path+'?'+urlencode(query,doseq=True)}}
  response=http(tmp_path,handle);native=tools.execute(tmp_path,NAMESPACE,'work','project',{'view':'discovery','request':req});python=sdk.request(req,root=tmp_path)
  assert native['declaration']==python['declaration']==response['declaration']
  assert native['read']==python['read']==response['read']
  assert response['declaration']['reference']['version']['declaration']==template['observation']['declaration']
  assert len(canonical_bytes(response))<=15360
  assert http(tmp_path,response['up_read'])['declaration']==coarse['declaration']
  selected.append(response)
 assert len(canonical_bytes(coarse))<=15360
 with pytest.raises(ValueError,match='SELECT_REQUIRES_DECLARATION'):K.read(tmp_path,scope,{**payload,'view':'publications','select':'segment:admission'})
 with pytest.raises(ValueError):K.read(tmp_path,scope,{**payload,'select':'segment:missing'})
 with pytest.raises(ValueError,match='NOT_IN_SCOPE'):K.read(tmp_path,O.project_scope('foreign','native'),payload)
 # Observation changes are explicit; a client must not paint the old selection as unchanged.
 original=P.source_contract
 def changed():
  d=original();d['segments']['purpose']['meaning']+=' Changed public assumption.';return d
 monkeypatch.setattr(P,'source_contract',changed)
 newer=K.read(tmp_path,scope,{**payload,'select':'segment:purpose'})
 assert newer['declaration']['reference']['version']['declaration']!=template['observation']['declaration']
 (tmp_path/'current-owner-samples.json').write_text(json.dumps({'coarse':coarse,'selected':selected,'changed':newer},indent=2,ensure_ascii=False))


def test_nine_retained_segments_single_read_navigation_and_private_frame(tmp_path):
 scope,selection,ref,names,handoff=retained(tmp_path)
 publications=K.read(tmp_path,scope,{'facet':'source-kernel','view':'publications','reference':REF,'namespace':NAMESPACE,'budget':15360})
 row=publications['publications'][0];assert row['segments']==sorted(names) and len(row['read']['request']['segments'])==1
 response=http(tmp_path,row['read']);responses=[]
 while True:
  nav=response['segment_navigation'];assert nav['known']==9 and nav['selected']==1 and response['leaves'][0]['segment']==nav['segment']
  assert len(json.dumps(response,ensure_ascii=False).encode())<=15360
  from laplace.native import tools
  native=tools.execute(tmp_path,NAMESPACE,'work','project',{'view':'discovery','request':response['read']['request']})
  assert len(json.dumps(native,ensure_ascii=False).encode())<=15360
  facts=http(tmp_path,response['leaves'][0]['retained_read']);assert facts['segment']==nav['segment'] and len(json.dumps(facts,ensure_ascii=False).encode())<=15360
  assert facts['relation_coverage']['state']=='AVAILABLE' and len(facts['typed_relations'])==response['leaves'][0]['relation_coverage']['known']
  assert all(nav['segment'] in relation['segments'] for relation in facts['typed_relations'])
  if nav['segment']=='composition':assert facts['facts']['steps']==P.source_contract()['steps']
  up_response=http(tmp_path,nav['up_read']);assert up_response['publications']==publications['publications']
  if responses:assert http(tmp_path,nav['previous_read'])==responses[-1]
  responses.append(response)
  if 'next_read' not in nav:break
  response=http(tmp_path,nav['next_read'])
 assert len(responses)==9
 view_responses={}
 for view in responses[0]['view_read']['values'].values():
  template=responses[0]['view_read'];req={**template['request'],template['field']:view}
  view_responses[view]=http(tmp_path,K._read_handle(req))
  assert len(json.dumps(view_responses[view],ensure_ascii=False).encode())<=15360
 operator=O.owned_workspace('sdk');request={'reference':ref,'selection':selection,'segments':names}
 internal=K.prepare_publication_inputs(tmp_path,operator,[request]);assert len(internal['frame']['leaves'])==9
 assert sum(p['bytes'] for p in internal['frame']['receipts'][0]['source_inputs'])<K.MAX_BYTES
 assert len(W._tasks(NAMESPACE,tmp_path)['public-kernel-owner']['review_obligations'])==2
 before=SC.version(P.source_contract());K.read(tmp_path,scope,{'facet':'source-kernel','view':'standing','reference':ref,'selection':selection});assert SC.version(P.source_contract())==before
 wrong=copy.deepcopy(request);wrong['reference']['version']['declaration']='sha256:'+'0'*64
 with pytest.raises(ValueError,match='MISMATCH'):K.prepare_publication_inputs(tmp_path,operator,[wrong])
 target=tmp_path/INPUTS[0];target.write_bytes(target.read_bytes()+b'\n# public later source edit\n')
 carried=K.validate_publication_inputs(tmp_path,operator,internal['packet'])
 assert carried['frame']['leaves']==internal['frame']['leaves'] and {row['state'] for row in carried['frame']['currentness'].values()}=={'CARRIED'}
 # Exact held source facts remain verifiable without current raw-source admission; no publication is asserted here.
 leaf=next(iter(internal['frame']['leaves'].values()));projection=leaf['projection'];segment=json.loads(leaf['embedding_text'])['segment']
 assert K.published_facts(tmp_path,scope,{'reference':ref,'selection':selection,'segments':[segment]},projection)==json.loads(leaf['embedding_text'])
 (tmp_path/'retained-owner-samples.json').write_text(json.dumps({'publications':publications,'retained_up':up_response,'view_responses':view_responses,'responses':responses,'handoff':handoff,'packet':internal['packet'],'raw_input_bytes':sum(p['bytes'] for p in internal['frame']['receipts'][0]['source_inputs']),'publication_executed':False},indent=2,ensure_ascii=False))


def test_retained_relation_context_is_exact_or_explicitly_unavailable(tmp_path,monkeypatch):
 scope,selection,ref,names,_=retained(tmp_path)
 payload={'facet':'source-kernel','view':'segment','reference':ref,'selection':selection,'segments':['purpose'],'budget':15360}
 actual=K._selected(tmp_path,scope,payload)
 # Explicit historical-format seam only; actual segment/body custody remains the public owner output.
 old=copy.deepcopy(actual[2]);old.pop('kernel_context')
 monkeypatch.setattr(K,'_selected',lambda *_:(actual[0],actual[1],old,actual[3]))
 value=K.read(tmp_path,scope,payload)
 assert value['facts']==P.source_contract()['segments']['purpose']
 assert value['typed_relations']==[] and value['relation_coverage']['state']=='UNAVAILABLE'
 broken=copy.deepcopy(actual[2]);broken['kernel_context']['basis']='sha256:'+'0'*64
 monkeypatch.setattr(K,'_selected',lambda *_:(actual[0],actual[1],broken,actual[3]))
 with pytest.raises(ValueError,match='CORRUPT_BODY'):K.read(tmp_path,scope,payload)
 (tmp_path/'relation-context-proof.json').write_text(json.dumps({'old_format':value,'corrupt_context_refused':True,'qualification':'Old-format input seam, actual public retained body. No historical backfill or publication.'},indent=2))
