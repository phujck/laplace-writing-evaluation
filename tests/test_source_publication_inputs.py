"""Actual selected Work custody, pure preparation only; no publisher or model seam."""
import copy,json
import pytest
from test_source_kernel_bridge import sample
from laplace.work import source_kernel as K,owner_discovery as O,project_work as W,project_work_review as R


def request(payload,segments=None):
 return {key:copy.deepcopy(payload[key]) for key in ['reference','selection']}|{'segments':segments or ['authority']}


def test_exact_segment_packets_bases_receipts_and_detachment(tmp_path):
 payload,first=sample(tmp_path,segments=['authority','purpose']);scope=O.owned_workspace('sdk')
 payload['reference']=K.prepare(tmp_path,scope,payload)['reference']
 value=K.prepare_publication_inputs(tmp_path,scope,[request(payload,['authority','purpose'])])
 packet=value['packet'];assert len(packet['inputs'])==2 and len(value['frame']['leaves'])==2
 assert K.validate_publication_inputs(tmp_path,scope,packet)==value
 visible=K.read(tmp_path,scope,{**payload,'segments':['authority']});row=next(r for r in packet['inputs'] if r['request']['segments']==['authority'])
 assert visible['prepared_basis']==row['prepared_basis'] and visible['source_basis']==row['source_basis']
 expected=copy.deepcopy(packet);packet['inputs'][0]['request']['selection']['work_id']='local mutation'
 assert K.prepare_publication_inputs(tmp_path,scope,[request(payload,['purpose','authority'])])['packet']==expected
 (tmp_path/'input-packet-proof.json').write_text(json.dumps({'packet':expected,'read':visible,'private_leaf_ids':list(value['frame']['leaves'])},indent=2))


def test_operator_scope_before_custody_and_changed_or_forged_basis(tmp_path,monkeypatch):
 called=[]
 with monkeypatch.context() as m:
  m.setattr(K,'prepare',lambda *_:called.append('BODY'))
  for scope in [O.project_scope('p','native'),O.project_scope('p','http'),O.owned_workspace('native')]:
   with pytest.raises(ValueError,match='OPERATOR_REQUIRED'):K.prepare_publication_inputs(tmp_path,scope,[{}])
   with pytest.raises(ValueError,match='OPERATOR_REQUIRED'):K.validate_publication_inputs(tmp_path,scope,{})
   with pytest.raises(ValueError,match='OPERATOR_REQUIRED'):K.merge_publication_inputs(tmp_path,scope,None,{},set())
 assert called==[]
 payload,_=sample(tmp_path);scope=O.owned_workspace('sdk');payload['reference']=K.prepare(tmp_path,scope,payload)['reference'];req=request(payload)
 original=K.prepare_publication_inputs(tmp_path,scope,[req])['packet']
 for field in ['prepared_basis','source_basis','node_id']:
  bad=copy.deepcopy(original);bad['inputs'][0][field]=('OP-SOURCE-' if field=='node_id' else 'sha256:')+'0'*64
  with pytest.raises(ValueError,match='INPUT_CHANGED'):K.validate_publication_inputs(tmp_path,scope,bad)
 with pytest.raises(ValueError,match='INVALID_INPUT'):K.prepare_publication_inputs(tmp_path,scope,[{**req,'body':'untrusted'}])
 unversioned=copy.deepcopy(req);unversioned['reference'].pop('version')
 with pytest.raises(ValueError,match='VERSION_REQUIRED'):K.prepare_publication_inputs(tmp_path,scope,[unversioned])
 target=tmp_path/'src/laplace/work/project_work_review.py';target.write_bytes(target.read_bytes()+b'\n# changed public input\n')
 carried=K.validate_publication_inputs(tmp_path,scope,original)
 assert carried['packet']==original and [row['state'] for row in carried['frame']['currentness'].values()]==['CARRIED']


def test_merge_retains_unselected_expected_entries_and_equal_distinct_custody(tmp_path,monkeypatch):
 payload,first=sample(tmp_path,segments=['authority','purpose']);scope=O.owned_workspace('publication-cli');payload['reference']=K.prepare(tmp_path,scope,payload)['reference']
 parent=K.prepare_publication_inputs(tmp_path,scope,[request(payload,['authority','purpose'])])['packet']
 path='src/laplace/work/project_work_review.py';second=R.record('p',{'id':'kernel','phase':'handoff','request_id':'second-input-packet','expected_work_revision':W._task_revision(W._tasks('p',tmp_path)['kernel']),'object':{'kind':'source'},'pins':first['phase']['pins']},tmp_path)
 newer=copy.deepcopy(payload);newer['selection']['handoff_id']=second['phase']['id']
 new=K.prepare_publication_inputs(tmp_path,scope,[request(newer)])
 original_prepare=K.prepare
 def only_new(root,scope,value):
  assert value['segments']==['authority'] and value['selection']==newer['selection'],'Carried purpose/custody must not be re-prepared'
  return original_prepare(root,scope,value)
 with monkeypatch.context() as m:
  m.setattr(K,'prepare',only_new)
  carried=K.merge_publication_inputs(tmp_path,scope,parent,new['packet'],set())
  replaced=K.merge_publication_inputs(tmp_path,scope,parent,new['packet'],set(new['frame']['leaves']))
 assert len(carried['inputs'])==3 and len(replaced['inputs'])==2
 old_purpose=next(row for row in parent['inputs'] if row['request']['segments']==['purpose'])
 assert old_purpose in replaced['inputs'] and old_purpose in carried['inputs']
 valid=K.validate_publication_inputs(tmp_path,scope,carried);assert len(valid['frame']['leaves'])==2 and len(valid['frame']['receipts'])==2
 assert K.merge_publication_inputs(tmp_path,scope,None,new['packet'],set())==new['packet']
 (tmp_path/'merge-proof.json').write_text(json.dumps({'parent':parent,'new':new['packet'],'carried':carried,'replaced':replaced},indent=2))


def test_active_owner_read_and_sdk_delegation_preserve_exact_qualified_target(tmp_path,monkeypatch):
 """A typed owner seam only; real publication/receipt verification belongs to A's public controls."""
 import sys,types
 from laplace import sdk
 payload,_=sample(tmp_path);scope=O.project_scope('p','http');item=K.prepare(tmp_path,scope,payload);leaf=item['metadata'][0]
 publication='sha256:'+'a'*64;calls=[];summary={'mode':'selected-source-contribution','publication_handle':publication,'parent_basis':'sha256:'+'b'*64,'retained_basis':'sha256:'+'b'*64,'coverage':{'complete_world':False,'selected_namespace':'p'},'derived_changes':{'nodes':[],'artifacts':[]}}
 owner=types.ModuleType('laplace.representation.source_publication')
 def counterparts(root,actual,held):
  assert actual.namespace=='p' and held['reference']==item['reference'];calls.append('counterpart')
  target={'reference':held['reference'],'selection':held['selection'],'segments':[leaf['segment']],'node_id':leaf['id'],'content_handle':leaf['content_handle'],'semantic_handle':leaf['semantic_handle'],'publication_handle':publication}
  return {'state':'PUBLISHED','publication':summary,'counterparts':[{'id':leaf['id'],'content_handle':leaf['content_handle'],'semantic_handle':leaf['semantic_handle'],'publication_handle':publication,'read':{'kind':'current-publication-object','reference':json.dumps(target)}}]}
 def read_object(root,actual,target):
  assert actual.namespace=='p' and target['node_id']==leaf['id'] and target['publication_handle']==publication
  if target['semantic_handle']!=leaf['semantic_handle']:raise ValueError('PUBLICATION_OTHER_SELECTED_MEANING')
  calls.append('object')
  return {**target,'publication':summary,'facts':{'exact':'owner supplied retained meaning'}}
 owner.counterparts=counterparts;owner.read_object=read_object
 owner.request=lambda root,actual,request: {'door':actual.door,'kind':actual.kind,'request':copy.deepcopy(request)}
 monkeypatch.setitem(sys.modules,owner.__name__,owner)
 held=K.read(tmp_path,scope,{**payload,'view':'counterpart'});read=held['kernel']['counterparts'][0]['read']
 assert read['request']['namespace']=='p' and read['request']['segments']==['authority'] and 'fold_receipt_handle' not in read['request']
 recovered=K.read(tmp_path,scope,read['request']);assert recovered['publication']==summary and recovered['node_id']==leaf['id'] and recovered['facts']['exact']
 forged={**read['request'],'semantic_handle':'sha256:'+'0'*64}
 with pytest.raises(ValueError,match='OTHER_SELECTED_MEANING'):K.read(tmp_path,scope,forged)
 with pytest.raises(ValueError,match='ACTIVE_PUBLICATION_REQUIRED'):K.read(tmp_path,scope,{**read['request'],'fold_receipt_handle':publication})
 with pytest.raises(ValueError,match='NOT_IN_SCOPE'):K.read(tmp_path,O.project_scope('foreign','native'),read['request'])
 assert calls==['counterpart','object']
 # Today's source changes refuse fresh admission but cannot erase the retained
 # object's existing exact owner read. No Work/body lookup or prepare on recovery.
 path=tmp_path/'src/laplace/work/project_work_review.py';path.write_bytes(path.read_bytes()+b'\n# changed after publication\n')
 assert K.read(tmp_path,scope,{**payload,'view':'prepare'})['leaves'][0]['content_handle']==leaf['content_handle']
 with monkeypatch.context() as m:
  m.setattr(K,'prepare',lambda *_:pytest.fail('Published recovery must not re-admit current source'))
  m.setattr(K,'_selected',lambda *_:pytest.fail('Published receipt owner resolves exact retained custody'))
  assert K.read(tmp_path,scope,read['request'])['facts']==recovered['facts']
  # Consume the actual issued target through all shared read envelopes, not only
  # the direct Source facade. The final publication verifier is still this test's
  # declared typed seam; schema/native/HTTP admission is real.
  from laplace.web import project_work_surface as H
  from laplace.native import tools
  from urllib.parse import urlsplit,parse_qs
  url=urlsplit(read['http']['url']);code,_,raw=H.handle(url.path,parse_qs(url.query),'GET',repo_root=tmp_path)
  assert code==200,raw
  assert json.loads(raw)['node_id']==leaf['id']
  assert sdk.request(read['request'],root=tmp_path)['facts']==recovered['facts']
  assert tools.execute(tmp_path,'p','work','project',{'view':'discovery','request':read['request']})['facts']==recovered['facts']
 assert sdk.source_publication({'action':'prepare','inputs':[]},root=tmp_path)=={'door':'sdk','kind':'owned-workspace','request':{'action':'prepare','inputs':[]}}
 (tmp_path/'active-wrapper-proof.json').write_text(json.dumps({'counterpart':held,'recovered':recovered,'calls':calls,'qualification':'Typed owner seam, no actual publication claim'},indent=2))


def test_published_facts_use_original_canonical_custody_not_current_raw_sources(tmp_path,monkeypatch):
 payload,_=sample(tmp_path);scope=O.project_scope('p','http');item=K.prepare(tmp_path,scope,payload)
 leaf=next(iter(item['leaves'].values()));projection=leaf['projection'];expected=json.loads(leaf['embedding_text'])
 request={'reference':item['reference'],'selection':item['selection'],'segments':['authority']}
 assert K.published_facts(tmp_path,scope,request,projection)==expected
 source=tmp_path/'src/laplace/work/project_work_review.py';source.write_bytes(source.read_bytes()+b'\n# current Source edited\n')
 assert K.prepare(tmp_path,scope,payload)['leaves']==item['leaves']
 with monkeypatch.context() as m:
  m.setattr(K,'_source',lambda *_:pytest.fail('Published reading must not access current raw source'))
  assert K.published_facts(tmp_path,scope,request,projection)==expected
  bad=copy.deepcopy(projection);target=json.loads(bad['exact_descent']['reference']);target['context_basis']='sha256:'+'0'*64;bad['exact_descent']['reference']=json.dumps(target)
  with pytest.raises(ValueError,match='PUBLISHED_MEANING_CHANGED'):K.published_facts(tmp_path,scope,request,bad)
  bad=copy.deepcopy(projection);target=json.loads(bad['exact_descent']['reference']);target['source_inputs'][0]['sha256']='sha256:'+'0'*64;bad['exact_descent']['reference']=json.dumps(target)
  with pytest.raises(ValueError,match='PUBLISHED_SOURCE_MISMATCH'):K.published_facts(tmp_path,scope,request,bad)
 with monkeypatch.context() as m:
  m.setattr(K,'_body',lambda *_:pytest.fail('Foreign scope must refuse before custody body'))
  with pytest.raises(ValueError,match='NOT_IN_SCOPE'):K.published_facts(tmp_path,O.project_scope('foreign','native'),request,projection)
 (tmp_path/'published-facts-proof.json').write_text(json.dumps({'projection':projection,'facts':expected,'current_source_changed':True,'fresh_prepare_refused':True,'exact_retained_custody_readable':True},indent=2))
