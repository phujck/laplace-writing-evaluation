"""The ordinary close gives every selected Source row one state instead of refusing on moved bytes.

Temporary roots only: the real Work/body owners retain each handoff; no model, GPU, network,
publication artifact or live root. Seams are named where a test varies a declaration supplier.
"""
import copy,hashlib,importlib.util,json
from pathlib import Path
import pytest
from laplace.core import identity
from laplace.work import source_contracts as SC,source_kernel as K,project_work as W,project_work_review as R,owner_discovery as O
from laplace.engine import source_kernel_input as E
from test_source_kernel_bridge import sample

DECLARING='src/laplace/work/project_work_review.py'
NOTE='src/laplace/work/carry_note.py'
OPERATOR=O.owned_workspace('sdk')
REAL_PROVIDERS=SC.providers


def sample_with_note(root):
 """The same real handoff as `sample`, also pinning one non-declaring public file."""
 root=Path(root);root.mkdir(exist_ok=True);(root/'p').mkdir(exist_ok=True)
 (root/'registry_projects.json').write_text(json.dumps({'projects':[{'name':'p','kind':'general','project_dir':'p'}]}))
 for rel,raw in [(DECLARING,Path(R.__file__).read_bytes()),(NOTE,b'"""Pinned public note."""\n')]:
  target=root/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
 binding={'owner':'domain.work','operation':'work_review.followup','consumer':K.CONSUMER,'segments':['authority']}
 W.task('p',{'id':'kernel','title':'Public typed Source ingestion','goal':'Exact declared meaning only','review_obligations':[{'id':'kernel','label':'Kernel facts','scope':'source','inputs':[DECLARING],'source_contract':binding}]},root)
 pins={rel:'sha256:'+hashlib.sha256((root/rel).read_bytes()).hexdigest() for rel in (DECLARING,NOTE)}
 first=R.record('p',{'id':'kernel','phase':'handoff','request_id':'kernel-note-handoff','expected_work_revision':W._task_revision(W._tasks('p',root)['kernel']),
  'object':{'kind':'source'},'pins':pins},root)
 selection={'namespace':'p','work_id':'kernel','handoff_id':first['phase']['id'],'obligation_id':'kernel'}
 return {'facet':'source-kernel','reference':SC.reference('domain.work','work_review.followup'),'selection':selection,'view':'prepare'},first


def published(root,maker=sample):
 """A packet as the selected publisher prepares it, and the parent's leaves for its rows."""
 payload,first=maker(root);payload['reference']=K.prepare(root,OPERATOR,payload)['reference']
 request={key:copy.deepcopy(payload[key]) for key in ['reference','selection']}|{'segments':['authority']}
 value=K.prepare_publication_inputs(root,OPERATOR,[request])
 parent={lid:copy.deepcopy(leaf['projection']) for lid,leaf in value['frame']['leaves'].items()}
 return payload,value['packet'],parent,value['frame']


def close(root,packet,parent):
 return K.validate_publication_inputs(root,OPERATOR,packet,retained=parent)['frame']


def only(frame):
 (lid,state),=frame['currentness'].items()
 return lid,state


def append(root,rel=DECLARING,text=b'\n# moved bytes, same meaning\n'):
 target=Path(root)/rel;target.write_bytes(target.read_bytes()+text)
 return 'sha256:'+hashlib.sha256(target.read_bytes()).hexdigest()


def supplier(replacement,*,module=None):
 """Vary only the declared-fact supplier of work_review.followup (named seam)."""
 def provider():
  return replacement(copy.deepcopy(R.source_contract()))
 provider.__module__=module or R.source_contract.__module__
 return lambda:tuple(provider if p is R.source_contract else p for p in REAL_PROVIDERS())


def test_close_carries_moved_bytes(tmp_path):
 payload,packet,parent,before=published(tmp_path)
 lid,state=only(close(tmp_path,packet,parent));assert state['state']=='CURRENT' and state['moved']==[]
 observed=append(tmp_path)
 frame=close(tmp_path,packet,parent);lid,state=only(frame)
 assert state['state']=='CARRIED' and state['by']=='work.source_kernel' and state['changed_segments']==[]
 assert state['moved']==[{'path':DECLARING,'retained_sha256':json.loads(parent[lid]['exact_descent']['reference'])['source_inputs'][0]['sha256'],'observed_sha256':observed}]
 # The CARRIED leaf is the parent's leaf exactly: node id, content handle and embedding text.
 assert set(frame['leaves'])==set(before['leaves'])
 assert frame['leaves'][lid]['projection']['content_handle']==parent[lid]['content_handle']
 assert frame['leaves'][lid]['embedding_text']==before['leaves'][lid]['embedding_text'] and frame['leaves']==before['leaves']
 assert json.loads(frame['leaves'][lid]['embedding_text'])['source_inputs'][0]['sha256']!=observed  # retained pins, not today's
 # Fresh selection admits CARRIED too, with the same leaf.
 fresh=K.validate_publication_inputs(tmp_path,OPERATOR,packet);assert fresh['frame']['leaves']==before['leaves']
 assert K.prepare(tmp_path,OPERATOR,payload)['leaves']==before['leaves']


def test_close_carries_moved_non_declaring_pin_from_parent_edition(tmp_path):
 payload,packet,parent,before=published(tmp_path,sample_with_note)
 append(tmp_path,NOTE,b'# a non-code-meaning edit\n')
 frame=close(tmp_path,packet,parent);lid,state=only(frame)
 assert state['state']=='CARRIED' and [row['path'] for row in state['moved']]==[NOTE] and frame['leaves']==before['leaves']
 # Fresh selection has no retained edition stating the moved pin's size: it says so and refuses.
 with pytest.raises(ValueError,match='SOURCE_KERNEL_SOURCE_UNKNOWN: .*size'):K.validate_publication_inputs(tmp_path,OPERATOR,packet)


def changed_authority(value):
 value['segments']['authority']={**value['segments']['authority'],'carry_test':'the consumed segment changed'}
 return value


def changed_context(value):
 value['relations'].append({'consumer':'tests.close_carry','relation':'evaluates','segments':['authority'],'location':'tests/test_source_close_carry.py','says':'a new relation on the consumed segment'})
 return value


@pytest.mark.parametrize('change,why',[(changed_authority,'segment'),(changed_context,'leaf context')])
def test_close_stale_on_changed_segment(tmp_path,monkeypatch,change,why):
 payload,packet,parent,before=published(tmp_path)
 monkeypatch.setattr(SC,'providers',supplier(change))
 # Meaning that moved without its pinned bytes moving is not re-read: bytes are the consumed custody.
 assert only(close(tmp_path,packet,parent))[1]['state']=='CURRENT'
 append(tmp_path)
 frame=close(tmp_path,packet,parent);lid,state=only(frame)
 assert state['state']=='STALE' and state['changed_segments']==['authority'] and why in state['reason']
 assert frame['leaves']==before['leaves']  # the parent's exact retained leaf, labelled
 with pytest.raises(ValueError,match='SOURCE_KERNEL_SOURCE_STALE'):K.validate_publication_inputs(tmp_path,OPERATOR,packet)
 with pytest.raises(ValueError,match='SOURCE_KERNEL_SOURCE_STALE'):K.prepare(tmp_path,OPERATOR,payload)
 with pytest.raises(ValueError,match='SOURCE_KERNEL_SOURCE_STALE'):K.read(tmp_path,OPERATOR,payload)
 with pytest.raises(ValueError,match='SOURCE_KERNEL_RETAINED_LEAF_UNAVAILABLE'):close(tmp_path,packet,{})


def qualified(monkeypatch,root,status):
 """Named seam: a qualified source_basis on the real handoff, with the development owner's verdict varied."""
 from laplace.work import development_source as D
 real=K._selected
 basis={'repository':'lane-checkout','checkout_identity':'sha256:'+'1'*64,'base':'0'*40}
 def selected(*args,**kw):
  s,phase,held,names=real(*args,**kw)
  return s,{**phase,'source_basis':basis},held,names
 monkeypatch.setattr(K,'_selected',selected)
 monkeypatch.setattr(D,'_checkout',lambda *_:Path(root).resolve())
 monkeypatch.setattr(D,'validate_review_basis',lambda *a,**k:{'status':status[0],'reason':status[1],'observed_pins':{}})


@pytest.mark.parametrize('status',[('CHANGED','the recorded source checkout base changed'),('CHANGED','consumed source bytes changed'),
 ('CHANGED','the configured source repository was retargeted'),('UNKNOWN','a consumed source file is unavailable')])
def test_close_qualified_basis_not_current_unknown(tmp_path,monkeypatch,status):
 qualified(monkeypatch,tmp_path,('CURRENT','the exact recorded qualified source and consumed pins still match'))
 payload,packet,parent,before=published(tmp_path)
 assert json.loads(next(iter(parent.values()))['exact_descent']['reference'])['repository']['id']=='lane-checkout'
 qualified(monkeypatch,tmp_path,status)
 frame=close(tmp_path,packet,parent);lid,state=only(frame)
 assert state['state']=='UNKNOWN' and status[0] in state['reason'] and 'live tree' in state['reason'] and frame['leaves']==before['leaves']
 with pytest.raises(ValueError,match='SOURCE_KERNEL_SOURCE_UNKNOWN'):K.validate_publication_inputs(tmp_path,OPERATOR,packet)


def test_close_qualified_bytes_moved_at_its_checkout_unknown(tmp_path,monkeypatch):
 qualified(monkeypatch,tmp_path,('CURRENT','the exact recorded qualified source and consumed pins still match'))
 payload,packet,parent,before=published(tmp_path)
 append(tmp_path)
 lid,state=only(close(tmp_path,packet,parent));assert state['state']=='UNKNOWN' and 'another checkout' in state['reason']


def test_close_pinned_file_deleted_unknown(tmp_path):
 payload,packet,parent,before=published(tmp_path)
 (tmp_path/DECLARING).unlink()
 frame=close(tmp_path,packet,parent);lid,state=only(frame)
 assert state['state']=='UNKNOWN' and 'deleted' in state['reason'] and state['moved'][0]['observed_sha256'] is None
 assert frame['leaves']==before['leaves']
 with pytest.raises(ValueError,match='SOURCE_KERNEL_SOURCE_UNKNOWN'):K.prepare(tmp_path,OPERATOR,payload)


@pytest.mark.parametrize('cause',['excluded','oversized'])
def test_close_pinned_file_excluded_unknown(tmp_path,monkeypatch,cause):
 payload,packet,parent,before=published(tmp_path)
 from laplace.work import source_inventory as I
 if cause=='excluded':monkeypatch.setattr(I,'_eligible',lambda path:path!=DECLARING)
 else:monkeypatch.setattr(I,'MAX_FILE',16)
 frame=close(tmp_path,packet,parent);lid,state=only(frame)
 assert state['state']=='UNKNOWN' and ('excluded' if cause=='excluded' else 'bound') in state['reason'] and frame['leaves']==before['leaves']
 with pytest.raises(ValueError,match='SOURCE_KERNEL_SOURCE_UNKNOWN'):K.prepare(tmp_path,OPERATOR,payload)


def test_close_declaration_removed_unknown(tmp_path,monkeypatch):
 payload,packet,parent,before=published(tmp_path)
 append(tmp_path)
 monkeypatch.setattr(SC,'providers',lambda:tuple(p for p in REAL_PROVIDERS() if p is not R.source_contract))
 frame=close(tmp_path,packet,parent);lid,state=only(frame)
 assert state['state']=='UNKNOWN' and 'no owner declares' in state['reason'] and frame['leaves']==before['leaves']
 # Fresh selection keeps the Source admission's own refusal of an undeclared operation.
 with pytest.raises(ValueError,match='UNKNOWN_TARGET'):K.prepare(tmp_path,OPERATOR,payload)
 with pytest.raises(ValueError,match='UNKNOWN_TARGET'):K.validate_publication_inputs(tmp_path,OPERATOR,packet)


def test_close_declaration_moved_carried(tmp_path,monkeypatch):
 payload,packet,parent,before=published(tmp_path)
 append(tmp_path)
 monkeypatch.setattr(SC,'providers',supplier(lambda value:value,module='laplace.work.moved_owner'))
 frame=close(tmp_path,packet,parent);lid,state=only(frame)
 assert state['state']=='CARRIED' and state['declaring_moved']=={'from':DECLARING,'to':'src/laplace/work/moved_owner.py'}
 assert frame['leaves']==before['leaves']
 monkeypatch.setattr(SC,'providers',supplier(changed_authority,module='laplace.work.moved_owner'))
 lid,state=only(close(tmp_path,packet,parent));assert state['state']=='STALE' and state['declaring_moved']['to']=='src/laplace/work/moved_owner.py'


def test_close_declaration_moved_with_old_file_unchanged_is_compared(tmp_path,monkeypatch):
 """No pinned byte moved, the declaration moved module: the row is still compared (judge r1, test_A)."""
 payload,packet,parent,before=published(tmp_path)
 monkeypatch.setattr(SC,'providers',supplier(changed_authority,module='laplace.work.moved_owner'))
 frame=close(tmp_path,packet,parent);lid,state=only(frame)
 assert state['state']=='STALE' and state['moved']==[] and state['changed_segments']==['authority']
 assert state['declaring_moved']=={'from':DECLARING,'to':'src/laplace/work/moved_owner.py'} and 'declaration moved to another module' in state['reason']
 assert frame['leaves']==before['leaves']
 with pytest.raises(ValueError,match='SOURCE_KERNEL_SOURCE_STALE'):K.validate_publication_inputs(tmp_path,OPERATOR,packet)
 with pytest.raises(ValueError,match='SOURCE_KERNEL_SOURCE_STALE'):K.prepare(tmp_path,OPERATOR,payload)
 # Equal meaning in another module, no byte moved: CARRIED, the parent's exact leaf, fresh selection admits it.
 monkeypatch.setattr(SC,'providers',supplier(lambda value:value,module='laplace.work.moved_owner'))
 frame=close(tmp_path,packet,parent);lid,state=only(frame)
 assert state['state']=='CARRIED' and state['moved']==[] and state['declaring_moved']['to']=='src/laplace/work/moved_owner.py'
 assert frame['leaves']==before['leaves']
 assert only(K.validate_publication_inputs(tmp_path,OPERATOR,packet)['frame'])[1]['state']=='CARRIED'
 # Removed with no byte moved: UNKNOWN in the close (it was an uncaught StopIteration on the base).
 monkeypatch.setattr(SC,'providers',lambda:tuple(p for p in REAL_PROVIDERS() if p is not R.source_contract))
 assert only(close(tmp_path,packet,parent))[1]['state']=='UNKNOWN'


def test_only_a_close_carry_publishes_retained_rows(tmp_path,monkeypatch):
 """C4: the active packet read through input_frame is fresh selection; only close_inputs' carry publishes STALE."""
 from laplace.representation import source_publication as P
 payload,packet,parent,before=published(tmp_path)
 monkeypatch.setattr(SC,'providers',supplier(changed_authority));append(tmp_path)
 monkeypatch.setattr(P,'selections',lambda root:copy.deepcopy(packet))
 with pytest.raises(ValueError,match='SOURCE_KERNEL_SOURCE_STALE'):E.input_frame(tmp_path,copy.deepcopy(packet))
 with pytest.raises(ValueError,match='SOURCE_KERNEL_SOURCE_STALE'):E.input_frame(tmp_path)  # keeper's default: the active packet
 request={key:copy.deepcopy(payload[key]) for key in ['reference','selection']}|{'segments':['authority'],'facet':'source-kernel','view':'prepare'}
 with pytest.raises(ValueError,match='SOURCE_KERNEL_SOURCE_STALE'):E.input_frame(tmp_path,[request])
 carry=E.close_inputs(tmp_path,packet,{'selected_content':parent,'publication_handle':'sha256:'+'9'*64})
 frame=E.input_frame(tmp_path,carry);lid,state=only(frame)
 assert state['state']=='STALE' and frame['leaves']==before['leaves'] and carry['currentness']==frame['currentness']
 # Deleted pin: UNKNOWN refuses in the same fresh readers and publishes only through the carry.
 (tmp_path/DECLARING).unlink()
 with pytest.raises(ValueError,match='SOURCE_KERNEL_SOURCE_UNKNOWN'):E.input_frame(tmp_path)
 carry=E.close_inputs(tmp_path,packet,{'selected_content':parent,'publication_handle':'sha256:'+'9'*64})
 assert only(E.input_frame(tmp_path,carry))[1]['state']=='UNKNOWN'


def test_published_facts_and_retained_leaves_read_only_retained_values(tmp_path,monkeypatch):
 payload,packet,parent,before=published(tmp_path)
 (tmp_path/DECLARING).unlink()
 lid=next(iter(parent));request={'reference':payload['reference'],'selection':payload['selection'],'segments':['authority']}
 with monkeypatch.context() as m:
  m.setattr(K,'_current_meaning',lambda *_:pytest.fail('retained reading must not consult the current declaration'))
  m.setattr(K,'_source',lambda *_:pytest.fail('published reading must not access current raw source'))
  assert K.published_facts(tmp_path,OPERATOR,request,parent[lid])==json.loads(before['leaves'][lid]['embedding_text'])
  m.undo();m.setattr(K,'_current_meaning',lambda *_:pytest.fail('an unreadable pin needs no current meaning'))
  assert close(tmp_path,packet,parent)['leaves']==before['leaves']


def test_close_integrity_refusals_unchanged(tmp_path,monkeypatch):
 payload,packet,parent,before=published(tmp_path)
 append(tmp_path)  # a source edit is present; none of these is produced by it, and each still raises
 lid=next(iter(parent));row=packet['inputs'][0]
 def forged(**change):
  value=copy.deepcopy(packet)
  for key,new in change.items():
   if key=='selection':value['inputs'][0]['request']['selection'].update(new)
   elif key=='version':value['inputs'][0]['request']['reference']['version']={'declaration':new}
   elif key=='segments':value['inputs'][0]['request']['segments']=new
   else:value['inputs'][0][key]=new
  return value
 with pytest.raises(ValueError,match='SOURCE_KERNEL_NOT_IN_SCOPE'):K.prepare(tmp_path,O.project_scope('foreign','native'),payload,retained=parent,publish_retained=True)  # :50
 with pytest.raises(ValueError,match='SOURCE_KERNEL_PUBLICATION_UNAVAILABLE'):close(tmp_path,forged(selection={'handoff_id':'PHASE-missing'}),parent)  # :54
 with pytest.raises(ValueError,match='SOURCE_KERNEL_PUBLICATION_MISMATCH'):close(tmp_path,forged(version='sha256:'+'0'*64),parent)  # :56
 with pytest.raises(ValueError,match='SOURCE_KERNEL_SEGMENT_NOT_RETAINED'):close(tmp_path,forged(segments=['purpose']),parent)  # :58
 with pytest.raises(ValueError,match='SOURCE_PUBLICATION_INPUT_CHANGED'):close(tmp_path,forged(prepared_basis='sha256:'+'0'*64),parent)  # :260
 with pytest.raises(ValueError,match='SOURCE_PUBLICATION_INPUT_CHANGED'):close(tmp_path,forged(source_basis='sha256:'+'0'*64),parent)  # :260
 real=K._selected
 def held_with(change):
  def selected(*args,**kw):
   s,phase,held,names=real(*args,**kw);phase=copy.deepcopy(phase);held=copy.deepcopy(held);change(phase,held)
   return s,phase,held,names
  return selected
 cases=[('SOURCE_KERNEL_INPUT_BUDGET',lambda p,h:h['segments']['authority']['body'].update(bytes=K.MAX_BYTES+1)),  # :63
  ('SOURCE_KERNEL_CORRUPT_BODY',lambda p,h:h['segments']['authority'].update(basis='sha256:'+'0'*64)),  # :65
  ('SOURCE_KERNEL_PINNED_PUBLIC_INPUTS_REQUIRED',lambda p,h:p['pins'].update({'src/laplace/x%d.py'%i:'sha256:'+'0'*64 for i in range(K.MAX_PINS)})),  # :72
  ('SOURCE_KERNEL_TYPED_CONTEXT_NOT_RETAINED',lambda p,h:h.pop('kernel_context')),  # :94
  ('SOURCE_KERNEL_DECLARATION_EDITION_UNQUALIFIED',lambda p,h:p['pins'].update({DECLARING:'sha256:'+'2'*64})),  # :97
  ('SOURCE_KERNEL_DECLARING_SOURCE_PIN_REQUIRED',lambda p,h:p.update(pins={NOTE:'sha256:'+'3'*64}))]  # :92
 for code,change in cases:
  with monkeypatch.context() as m:
   m.setattr(K,'_selected',held_with(change))
   with pytest.raises(ValueError,match=code):close(tmp_path,packet,parent)
 # :178 conflicting editions of one logical leaf never win by order.
 original=K.prepare;count=[]
 def conflicting(*args,**kw):
  value=original(*args,**kw);count.append(1)
  if len(count)>1:value['leaves'][lid]={**value['leaves'][lid],'essence':'another edition'}
  return value
 with monkeypatch.context() as m:
  m.setattr(K,'prepare',conflicting)
  with pytest.raises(ValueError,match='SOURCE_KERNEL_CONFLICTING_EDITIONS'):K.input_frame(tmp_path,[payload,payload],retained=parent,publish_retained=True)
 # :270 the joined frame must contain the validated row's content, receipt and state.
 frame_of=K.input_frame
 with monkeypatch.context() as m:
  m.setattr(K,'input_frame',lambda *a,**k:{**frame_of(*a,**k),'currentness':{lid:{'state':'CURRENT'}}})
  with pytest.raises(ValueError,match='SOURCE_PUBLICATION_INPUT_CHANGED'):close(tmp_path,packet,parent)
 # A row with no parent leaf, and a parent leaf that does not bind this custody, refuse.
 (tmp_path/DECLARING).unlink()
 with pytest.raises(ValueError,match='SOURCE_KERNEL_RETAINED_LEAF_UNAVAILABLE'):close(tmp_path,packet,{})
 with pytest.raises(ValueError,match='SOURCE_KERNEL_RETAINED_LEAF_UNAVAILABLE'):E.close_inputs(tmp_path,packet,{'selected_content':{},'publication_handle':'sha256:'+'4'*64})
 bad=copy.deepcopy(parent);target=json.loads(bad[lid]['exact_descent']['reference']);target['context_basis']='sha256:'+'0'*64
 bad[lid]['exact_descent']['reference']=json.dumps(target)
 with pytest.raises(ValueError,match='SOURCE_KERNEL_PUBLISHED_MEANING_CHANGED'):close(tmp_path,packet,bad)
 bad=copy.deepcopy(parent);target=json.loads(bad[lid]['exact_descent']['reference']);target['source_inputs'][0]['sha256']='sha256:'+'0'*64
 bad[lid]['exact_descent']['reference']=json.dumps(target)
 with pytest.raises(ValueError,match='SOURCE_KERNEL_PUBLISHED_SOURCE_MISMATCH'):close(tmp_path,packet,bad)


def reembed_module():
 path=Path(__file__).resolve().parents[1]/'scripts'/'reembed.py'
 spec=importlib.util.spec_from_file_location('reembed_close_carry',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 return module


def test_receipt_close_receipt_and_wake_record_every_state(tmp_path,monkeypatch):
 from laplace.representation import source_publication as P
 from laplace.engine import close_beats
 payload,packet,parent,before=published(tmp_path)
 append(tmp_path)
 parent_receipt={'selected_content':parent,'publication_handle':'sha256:'+'5'*64}
 carry=E.close_inputs(tmp_path,packet,parent_receipt)
 assert carry['packet']==packet and E.input_frame(tmp_path,carry)['leaves']==before['leaves']
 (lid,state),=carry['currentness'].items();assert state['state']=='CARRIED'
 monkeypatch.setattr(P,'artifact_rows',lambda root:{})  # named seam: no publication artifacts in a temporary root
 nodes={lid:{'kind':'declared-source-contract','projection':before['leaves'][lid]['projection']}}
 receipt=P.full_publication_receipt(tmp_path,{'act_id':'fixture'},carry,nodes,parent_receipt)
 assert receipt['source_kernel_inputs']==packet and receipt['source_currentness']=={lid:state}
 assert set(state)>={'state','moved','changed_segments','reason','by'} and state['moved'][0]['path']==DECLARING
 assert receipt['publication_handle']==identity.canonical_digest({k:v for k,v in receipt.items() if k!='publication_handle'})
 assert P.full_publication_receipt(tmp_path,{'act_id':'fixture'},packet,nodes,parent_receipt)['source_currentness'] is None
 moved={lid:{**nodes[lid],'projection':{**nodes[lid]['projection'],'content_handle':'sha256:'+'6'*64}}}
 with pytest.raises(ValueError,match='SOURCE_KERNEL_CURRENTNESS_MOVED'):P.full_publication_receipt(tmp_path,{},carry,moved,parent_receipt)
 # The close record carries the four counts; the wake shows them in one plain line.
 reembed=reembed_module()
 record=reembed._publication_record(tmp_path,published=False,reason='fixture',source_currentness=carry['currentness'])
 assert record['source_currentness']=={'current':0,'carried':1,'stale':0,'unknown':0}
 assert 'source_currentness' not in reembed._publication_record(tmp_path,published=False,reason='fixture')
 (tmp_path/'contract').mkdir(exist_ok=True)
 (tmp_path/'contract/close_receipt.json').write_text(json.dumps({'schema_version':'laplace.close/1','closed_at':'2026-11-06T20:00:00Z','act_id':'sewup-close-fixture',
  'status':'PUBLISHED','checkpoint':{'HANDOFF.md':'sha256:'+'7'*64},'publication':{'schema_version':'laplace.publication/1','published':True,
  'artifacts':{'.self_graded.json':'sha256:'+'8'*64},'source_currentness':{'current':8,'carried':1,'stale':1,'unknown':0}}}))
 line=close_beats.close_projection(tmp_path)['publication']['source_inputs']
 assert line=='Source inputs: 8 current, 1 carried (pinned bytes moved or the declaration moved to another module, meaning unchanged), 1 stale and 0 unknown (published as labelled retained history)'


def test_counterpart_labels_a_stale_retained_edition(tmp_path,monkeypatch):
 from laplace.representation import source_publication as P
 payload,packet,parent,before=published(tmp_path)
 monkeypatch.setattr(SC,'providers',supplier(changed_authority));append(tmp_path)
 lid=next(iter(parent));(tmp_path/'.self_graded.json').write_text(json.dumps({lid:before['leaves'][lid]}))
 receipt={'mode':'ordinary-full-deposit','publication_handle':'sha256:'+'9'*64,'source_kernel_inputs':packet,'selected_content':parent}
 monkeypatch.setattr(P,'current',lambda root:copy.deepcopy(receipt))  # named seam: the verified active receipt
 view=K.read(tmp_path,OPERATOR,{**payload,'view':'counterpart'})
 row,=view['kernel']['counterparts']
 assert view['kernel']['state']=='PUBLISHED' and row['currentness']=='retained edition; current declaration differs in authority'


def test_declaration_changes_only_currentness_and_one_relation():
 from laplace.representation import source_publication as P
 declaration=P.source_contract();bases=SC.bases(declaration)
 base={'admission':'sha256:3787b7e624a8c36b1566f471d60237e75a4a5218b77f25f4b0f74d0b3f74430a',
  'authority':'sha256:e24dc512e259b72da2c9f28f087c1f2afff5ea58a1ce26a1d0efef066d4caa41',
  'budgets':'sha256:19bb7f9a71e714a7dcd13d83b1cd33602395803299dd480d3f8303a40798a72e',
  'composition':'sha256:c1d163720f3d61a755cf97095e5fa05e10f411ba1d844b2c3efc11fa0511d56a',
  'descent':'sha256:b9876e81428c3d875d6c4bfda5a19646dcfae5fc8f6389be88ea38742b6f129e',
  'inputs':'sha256:26812beaa6eb1229858fb5e58024f67a4810e067490cc721dcb437b0f61c1d82',
  'purpose':'sha256:5ec2a62dac35c56f6eaa283ab4a9bb42e8219ce23b12b837a0f6d00c2912ced0',
  'recovery':'sha256:8dab6aaa0ff949f7698c123c7ed871850ed5dfa0bf67096214c3c0662510abfa'}
 # Leaf context bases at the base commit 0d2602eb1 (purpose, authority, recovery, relations of the segment).
 context={'admission':'sha256:5879386f256991aa2217fc6ba9e27a3a11a53ce66ef47c4846d0fe91c114480f','authority':'sha256:03b27918344a2b19221a2e43b87af8fbb95aca32a1ef778235054d559c9c02e7',
  'budgets':'sha256:ee2793245a72c5714e097fbced4a9b85a17c618b4eb6479f92fa971d2690cb32','composition':'sha256:b210a1a654cfcd4861d823df9da927db193a6e5fb0ca69cd55d2c58e976f4673',
  'descent':'sha256:3bf7a6d19e716ddf8e340750864b2ebea260d0fecc9ce7103341425306d8b5d8','inputs':'sha256:ce17607e83e3525a15912c8d2bf469eedebd46e6972e07c49db50dada171dc4e',
  'purpose':'sha256:ff410e3f24460211d189e3cfcc793c9879d22e246b5950aa533208a217f82bab','recovery':'sha256:3fadcf2f56a0f0cd88e4fa64e536cbb5b83e5c113af5cb7fc6613d631c5f0c4b'}
 assert {k:v for k,v in bases.items() if k!='currentness'}==base and bases['currentness']!='sha256:3e0a8f99c2b2dd2175619e1700afdcf830e15ca48f760a5563b5b6d4e23033d7'
 assert {k:K._context_basis(declaration,k) for k in base}==context
 assert set(declaration['segments']['currentness']['states'])==set(K.STATES)
 assert {'consumer':'engine.close_beats','relation':'projects','segments':['currentness'],'location':'src/laplace/engine/close_beats.py'} in declaration['relations']


def test_deposit_refuses_when_its_validation_moved_from_the_carry(tmp_path,monkeypatch):
 """Judge r2 B14: the close validates at t0, the source changes, the deposit re-validates at t1.

 The same calls as reembed.main -> keeper.semantic_input_frame -> full_publication_receipt, with
 no forged value. The deposit's own validation refuses SOURCE_KERNEL_CURRENTNESS_MOVED, so no
 receipt can record a state other than the one the publishing validation produced.
 """
 from laplace.engine import keeper,self_shard
 from laplace.representation import source_publication as P
 payload,packet,parent,before=published(tmp_path)
 parent_receipt={'selected_content':parent,'publication_handle':'sha256:'+'9'*64}
 carry=E.close_inputs(tmp_path,packet,parent_receipt)
 assert [v['state'] for v in carry['currentness'].values()]==['CURRENT']
 monkeypatch.setattr(keeper,'_is_semantic_operator_output',lambda _:False)
 monkeypatch.setattr(self_shard,'_tracked_files',lambda _: [])  # named seam: no whole-tree/Git enumeration
 monkeypatch.setattr(P,'artifact_rows',lambda root:{})  # named seam: no publication artifacts in a temporary root
 lid=next(iter(parent))
 # Unchanged between the two validations: the deposit's leaves and states are the carry's, and the receipt records them.
 leaves,*_=keeper.semantic_input_frame(tmp_path,source_kernel_inputs=carry)
 nodes={lid:{'kind':'declared-source-contract','projection':leaves[lid]['projection']}}
 assert P.full_publication_receipt(tmp_path,{'act_id':'fixture'},carry,nodes,parent_receipt)['source_currentness']==carry['currentness']
 # B14: the meaning changes and the bytes move after close_inputs; the t1 validation would say STALE.
 monkeypatch.setattr(SC,'providers',supplier(changed_authority));append(tmp_path)
 assert only(close(tmp_path,packet,parent))[1]['state']=='STALE'
 with pytest.raises(ValueError,match='SOURCE_KERNEL_CURRENTNESS_MOVED: '+lid):keeper.semantic_input_frame(tmp_path,source_kernel_inputs=carry)
 with pytest.raises(ValueError,match='SOURCE_KERNEL_CURRENTNESS_MOVED'):E.input_frame(tmp_path,carry)
 # Still CARRIED-shaped but observed at other bytes: the receipt's moved entry would be wrong, so it refuses too.
 monkeypatch.setattr(SC,'providers',REAL_PROVIDERS)
 carried=E.close_inputs(tmp_path,packet,parent_receipt);assert only({'currentness':carried['currentness']})[1]['state']=='CARRIED'
 append(tmp_path,text=b'\n# moved again\n')
 with pytest.raises(ValueError,match='SOURCE_KERNEL_CURRENTNESS_MOVED'):E.input_frame(tmp_path,carried)
 # Judge r2 B13: a carry whose recorded states were relabelled is not the deposit's validation either.
 fresh=E.close_inputs(tmp_path,packet,parent_receipt)
 forged=copy.deepcopy(fresh);forged['currentness']={k:{**v,'state':'CURRENT'} for k,v in forged['currentness'].items()}
 with pytest.raises(ValueError,match='SOURCE_KERNEL_CURRENTNESS_MOVED'):E.input_frame(tmp_path,forged)
 assert E.input_frame(tmp_path,fresh)['currentness']==fresh['currentness']
