"""Public retained Source inputs, no live fold/provider. Exact fake output boundary is labelled."""
import copy,json,hashlib
from pathlib import Path
import pytest
from laplace.work import source_contracts as SC,source_kernel as K,project_work as W,project_work_review as R,owner_discovery as O


def sample(root,*,request='kernel-handoff',segments=None):
 root=Path(root);root.mkdir(exist_ok=True);(root/'p').mkdir(exist_ok=True);(root/'registry_projects.json').write_text(json.dumps({'projects':[{'name':'p','kind':'general','project_dir':'p'}]}))
 path='src/laplace/work/project_work_review.py';target=root/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(Path(R.__file__).read_bytes())
 binding={'owner':'domain.work','operation':'work_review.followup','consumer':K.CONSUMER,'segments':segments or ['authority']}
 W.task('p',{'id':'kernel','title':'Public typed Source ingestion','goal':'Exact declared meaning only','review_obligations':[{'id':'kernel','label':'Kernel facts','scope':'source','inputs':[path],'source_contract':binding}]},root)
 payload={'id':'kernel','phase':'handoff','request_id':request,'expected_work_revision':W._task_revision(W._tasks('p',root)['kernel']),
  'object':{'kind':'source'},'pins':{path:'sha256:'+hashlib.sha256(target.read_bytes()).hexdigest()}}
 first=R.record('p',payload,root);selection={'namespace':'p','work_id':'kernel','handoff_id':first['phase']['id'],'obligation_id':'kernel'}
 return {'facet':'source-kernel','reference':SC.reference('domain.work','work_review.followup'),'selection':selection,'view':'prepare'},first


def test_retained_projection_and_actual_sdk_native_http(tmp_path,monkeypatch):
 payload,first=sample(tmp_path);scope=O.owned_workspace('sdk');prepared=K.read(tmp_path,scope,payload);again=K.read(tmp_path,scope,payload)
 assert prepared==again and prepared['state']=='PREPARED' and prepared['kernel']['state']=='UNRESOLVED'
 leaf=K.prepare(tmp_path,scope,payload);value=next(iter(leaf['leaves'].values()));route=value['projection']['exact_descent']
 assert K.descend(tmp_path,O.project_scope('p','native'),json.loads(route['reference']))==json.loads(value['embedding_text'])
 frame=K.input_frame(tmp_path,[payload,payload]);assert len(frame['leaves'])==1 and len(frame['receipts'])==2
 assert 'kernel_context' in first['phase']['source_contracts']['kernel']
 from laplace import sdk
 from laplace.native import tools
 from laplace.web import project_work_surface as H
 native=tools.execute(tmp_path,'p','work','project',{'view':'discovery','request':payload})
 python=sdk.request(payload,root=tmp_path)
 issued=prepared['read']['request'];query={k:[json.dumps(v) if isinstance(v,(dict,list)) else str(v)] for k,v in issued.items()}
 code,_,raw=H.handle('/work/discovery',query,'GET',repo_root=tmp_path);human=json.loads(raw);assert code==200,raw
 assert native['leaves']==python['leaves']==human['leaves']==prepared['leaves']
 with pytest.raises(ValueError,match='NOT_IN_SCOPE'):tools.execute(tmp_path,'other','work','project',{'view':'discovery','request':payload})
 # Exact existing engine resolver, supplied actual project scope; root selection substituted only in test.
 from laplace.engine import descent as D
 monkeypatch.setattr(D,'source_tree',lambda:tmp_path)
 read=D.descend(kind='source-contract',reference=route['reference'],source='',read_scope=O.project_scope('p','native'),content_budget=12000)
 assert read['content_handle']==value['projection']['content_handle']
 with pytest.raises(D.DescentRefused):D.descend(kind='source-contract',reference=route['reference'],source='',read_scope=O.project_scope('other','native'))
 (tmp_path/'actual-source-kernel-samples.json').write_text(json.dumps({'publication':first,'prepared':prepared,'python':python,'native':native,'http':human,'typed_descent':read},indent=2,ensure_ascii=False))


def test_selection_refusals_old_custody_and_changed_pin(tmp_path,monkeypatch):
 payload,first=sample(tmp_path);scope=O.owned_workspace('sdk');original=K.prepare(tmp_path,scope,payload)
 with pytest.raises(ValueError,match='NOT_IN_SCOPE'):K.prepare(tmp_path,O.project_scope('foreign','native'),payload)
 changed=copy.deepcopy(payload);changed['reference']['version']={'declaration':'sha256:'+'0'*64}
 with pytest.raises(ValueError,match='MISMATCH'):K.prepare(tmp_path,scope,changed)
 with pytest.raises(ValueError,match='BUDGET'):K.read(tmp_path,scope,{**payload,'budget':1})
 # Old receipts stay ordinarily readable; absence of new retained context is never backfilled.
 task=W._tasks('p',tmp_path)['kernel'];phase=next(x for x in task['phases'] if x['id']==payload['selection']['handoff_id'])
 old=copy.deepcopy(phase);old['source_contracts']['kernel'].pop('kernel_context')
 monkeypatch.setattr(K,'_selected',lambda *_:(payload['selection'],old,old['source_contracts']['kernel'],['authority']))
 with pytest.raises(ValueError,match='CONTEXT_NOT_RETAINED'):K.prepare(tmp_path,scope,payload)
 monkeypatch.undo()
 (tmp_path/'unconsumed.txt').write_text('Unrelated public input')
 assert K.prepare(tmp_path,scope,payload)['leaves']==original['leaves']
 target=tmp_path/'src/laplace/work/project_work_review.py';target.write_text(target.read_text()+'\n# changed public source\n')
 # Moved bytes with an unchanged consumed meaning are carried: the same leaf, its retained pins.
 carried=K.prepare(tmp_path,scope,payload);assert carried['leaves']==original['leaves']
 assert [row['state'] for row in carried['currentness'].values()]==['CARRIED']
 # This is a historical typed meaning read, still available independently of current source preparation.
 version=original['reference']['version']['declaration'];assert SC.read_version(tmp_path,'domain.work','work_review.followup',version,select='segment:authority')['state']=='RETAINED_VERSION'


def test_keeper_inputs_dedup_conflict_and_verified_counterpart_boundary(tmp_path,monkeypatch):
 payload,first=sample(tmp_path);scope=O.owned_workspace('sdk');frame=K.input_frame(tmp_path,[payload]);leaf=next(iter(frame['leaves'].values()));lid=next(iter(frame['leaves']))
 from laplace.engine import keeper,source_kernel_input as E
 # Isolated keeper fixture: explicit selected roots, no broad runtime capture or actual embedding/fold.
 monkeypatch.setattr(keeper,'_is_semantic_operator_output',lambda _:False)
 from laplace.engine import self_shard
 monkeypatch.setattr(self_shard,'_tracked_files',lambda _: [])  # One explicit discovery seam: no whole-tree/Git enumeration, including record-floor discovery.
 captured,parent,_,_,_=keeper.semantic_input_frame(tmp_path,source_kernel_inputs=[payload])
 assert captured[lid]==leaf and parent(lid)=='operational://declared-source'
 from laplace.representation import semantic_vertical as V
 coverage={'schema_version':V.COVERAGE_SCHEMA,'source_kernel_inputs':[payload]};coverage['coverage_handle']=V.digest(coverage)
 coverage_path=tmp_path/V.COVERAGE_PATH;coverage_path.write_bytes(V.canonical_bytes(coverage))
 assert E.input_frame(tmp_path)['leaves']==frame['leaves']
 coverage_path.write_text(coverage_path.read_text()+' ')
 # Whitespace changes do not alter the canonical coverage object; a changed selected cut must fail its body digest.
 broken=json.loads(coverage_path.read_text());broken['source_kernel_inputs']=[];coverage_path.write_text(json.dumps(broken))
 with pytest.raises(RuntimeError,match='coverage handle'):E.input_frame(tmp_path)
 coverage_path.unlink()
 nodes=keeper.build_tree(frame['leaves'],parent_of=lambda nid: '' if nid else None)
 assert nodes[lid]['projection']==leaf['projection'] and nodes[lid]['ref']==leaf['ref']
 from laplace.representation import source_publication as P
 assert P.counterparts(tmp_path,scope,K.prepare(tmp_path,scope,payload))['state']=='UNRESOLVED'
 (tmp_path/'.self_graded.json').write_text(json.dumps(nodes))
 # A tree or retired-F selector alone is never active publication evidence.
 from laplace.representation import embedding_health as H
 monkeypatch.setattr(H,'semantic_fold_down',lambda *_,**kw:pytest.fail('Retired F called for current Source counterpart'))
 assert P.counterparts(tmp_path,scope,K.prepare(tmp_path,scope,payload))['state']=='UNRESOLVED'
 # Conflicting same logical leaf is refused; identical inputs deduplicate with both custody receipts.
 bad=copy.deepcopy(frame['leaves']);bad[lid]['projection']['content_handle']='sha256:'+'0'*64
 original=K.prepare;count=[]
 def conflicting(*args):
  value=original(*args);count.append(1)
  if len(count)>1:value['leaves']=bad
  return value
 monkeypatch.setattr(K,'prepare',conflicting)
 with pytest.raises(ValueError,match='CONFLICTING_EDITIONS'):K.input_frame(tmp_path,[payload,payload])
 (tmp_path/'isolated-keeper-proof.json').write_text(json.dumps({'logical_node':lid,'nodes':nodes,'live_fold':False,'verification_boundary_substituted':True},indent=2))


def test_historical_engine_obligations_are_separate_human_read_only(tmp_path):
 from laplace.engine import historical_obligations as H
 (tmp_path/'corpus_friction').mkdir();(tmp_path/'contract').mkdir()
 records=[{'record':'work_order','id':'WO-one','status':'open','what':'Public historical work'},
 {'record':'work_order','id':'WO-two','status':'open','what':'Public resolved work'},
 {'record':'resolution','id':'RES-two','consumes':'WO-two','status':'resolved','evidence':['public-proof']},
 {'record':'project-work','id':'canonical-app-work','project':'p','status':'open','title':'Different domain'}]
 path=tmp_path/'corpus_friction/work_orders.jsonl';path.write_text(''.join(json.dumps(r)+'\n' for r in records));before=path.read_bytes()
 (tmp_path/'contract/promises.jsonl').write_text(json.dumps({'record':'promise','id':'PRM-one','status':'open','ask':'Public promise distinct from delivered artifact'})+'\n')
 request={'facet':'historical-obligations','source':'work_orders'};scope=O.owned_workspace('sdk')
 missing=H.read(tmp_path,O.owned_workspace('sdk'),{'facet':'historical-obligations','source':'promises'})
 assert missing['coverage']['source_available'] is True
 value=H.read(tmp_path,scope,request);assert [r['id'] for r in value['rows']]==['WO-one'] and value['coverage']['known']==2
 closed=H.read(tmp_path,scope,{**request,'state':'closed'});assert [r['id'] for r in closed['rows']]==['WO-two']
 read=H.read(tmp_path,scope,value['rows'][0]['read']['request']);assert json.loads(read['content'])['id']=='WO-one' and read['schema_version']==H.SCHEMA
 with pytest.raises(ValueError,match='HUMAN_ROOT_ONLY'):H.read(tmp_path,O.project_scope('p','native'),request)
 assert H.read(tmp_path,scope,{**request,'source':'promises'})['rows'][0]['id']=='PRM-one'
 promises=tmp_path/'contract/promises.jsonl';promises.unlink();absent=H.read(tmp_path,scope,{**request,'source':'promises'});assert absent['coverage']['source_state']=='ABSENT' and absent['coverage']['known']==0
 promises.write_text('');empty=H.read(tmp_path,scope,{**request,'source':'promises'});assert empty['coverage']['source_state']=='AVAILABLE' and empty['coverage']['known']==0
 assert path.read_bytes()==before
 path.write_bytes(before+json.dumps({'record':'work_order','id':'WO-three','status':'open','what':'New public entry'}).encode()+b'\n')
 with pytest.raises(ValueError,match='CUT_CHANGED'):H.read(tmp_path,scope,{**request,'as_of':value['read_cut']})
 (tmp_path/'historical-samples.json').write_text(json.dumps({'catalogue':value,'closed':closed,'record':read,'promises':H.read(tmp_path,scope,{**request,'source':'promises'})},indent=2))


def test_issued_entries_scope_and_equal_distinct_publications(tmp_path):
 payload,first=sample(tmp_path);scope=O.owned_workspace('sdk')
 path='src/laplace/work/project_work_review.py';pin=first['phase']['pins'][path]
 second=R.record('p',{'id':'kernel','phase':'handoff','request_id':'another-kernel-handoff','expected_work_revision':W._task_revision(W._tasks('p',tmp_path)['kernel']),'object':{'kind':'source'},'pins':{path:pin}},tmp_path)
 other={**payload,'selection':{**payload['selection'],'handoff_id':second['phase']['id']}}
 joined=K.input_frame(tmp_path,[payload,other]);reverse=K.input_frame(tmp_path,[other,payload])
 assert len(joined['leaves'])==1 and len(joined['receipts'])==2 and joined['leaves']==reverse['leaves']
 binding={'owner':'domain.work','operation':'work_review.followup','consumer':K.CONSUMER,'segments':['authority']}
 W.task('foreign',{'id':'secret-name-not-exported','title':'Foreign title not returned','goal':'Separate native scope','review_obligations':[{'id':'kernel','label':'Public foreign facts','scope':'source','inputs':[path],'source_contract':binding}]},tmp_path)
 R.record('foreign',{'id':'secret-name-not-exported','phase':'handoff','request_id':'foreign-kernel-handoff','expected_work_revision':W._task_revision(W._tasks('foreign',tmp_path)['secret-name-not-exported']),'object':{'kind':'source'},'pins':{path:pin}},tmp_path)
 from laplace import sdk
 from laplace.web import project_work_surface as H
 root_entry=sdk.source_kernel(view='contracts',root=tmp_path)
 native_entry=O.request(tmp_path,O.project_scope('p','native'),{'facet':'source-kernel','view':'contracts'})
 choice=next(r for r in native_entry['contracts'] if r['reference']['identity']['operation']=='work_review.followup')
 native=O.request(tmp_path,O.project_scope('p','native'),choice['publications_read']['request']);assert len(native['publications'])==2
 def http(read):
  from urllib.parse import urlsplit,parse_qs
  u=urlsplit(read['http']['url']);code,_,raw=H.handle(u.path,parse_qs(u.query),'GET',repo_root=tmp_path);assert code==200,raw;return json.loads(raw)
 issued=http(native['read']);assert len(issued['publications'])==2 and 'secret-name-not-exported' not in json.dumps(issued)
 declaration=http(choice['declaration_read']);nested=http(declaration['declaration']['source_kernel_read']);assert len(nested['publications'])==2
 prepared=http(native['publications'][0]['read']);facts=http(prepared['leaves'][0]['retained_read']);standing=http(prepared['current_standing_read'])
 assert facts['state']=='RETAINED_SEGMENT' and facts['selection']['namespace']=='p' and standing['state']=='CURRENT_STANDING'
 assert prepared['leaves'][0]['retained_read']['request'].get('namespace')=='p'
 # The public read issues preparation through its top-level read; leaf prepare_read stays private to K.prepare.
 assert prepared['read']['request'].get('namespace')=='p'
 assert facts['scope']['kind']=='project' and facts['scope']['namespace']=='p'
 assert facts['read']['request']['namespace']=='p'
 with pytest.raises(ValueError,match='NOT_IN_SCOPE'):O.request(tmp_path,O.project_scope('p','native'),{**payload,'namespace':'foreign'})
 catalogue=W.read('',{'view':'catalogue'},tmp_path);assert catalogue['source_inspector_read']['request']=={'facet':'source-kernel','view':'contracts'} and len(catalogue['historical_obligations_reads'])==2
 (tmp_path/'entry-scope-samples.json').write_text(json.dumps({'workspace_entry':catalogue['source_inspector_read'],'contracts':root_entry,'native_contracts':native_entry,'native_publications':native,'http_native_read':issued,'declaration':declaration,'prepared':prepared,'retained_segment':facts,'current_standing':standing,'historical_entries':catalogue['historical_obligations_reads']},indent=2,ensure_ascii=False))


def test_corrupt_missing_bodies_refuse_without_current_substitution(tmp_path):
 from laplace.representation import writing_bodies
 from atlas.errors import BlobMissing,BlobHashMismatch
 payload,first=sample(tmp_path);ref=first['phase']['source_contracts']['kernel']['kernel_context']['body'];path=writing_bodies.store(tmp_path).key_path(ref['content_handle']);original=path.read_bytes()
 path.unlink()
 with pytest.raises(BlobMissing):K.prepare(tmp_path,O.owned_workspace('sdk'),payload)
 path.parent.mkdir(exist_ok=True);path.write_bytes(b'X'*len(original))
 with pytest.raises(BlobHashMismatch):K.prepare(tmp_path,O.owned_workspace('sdk'),payload)
 path.write_bytes(original);assert K.read(tmp_path,O.owned_workspace('sdk'),payload)['state']=='PREPARED'


def test_segment_locality_and_conflicting_retained_editions(tmp_path,monkeypatch):
 payload,first=sample(tmp_path);scope=O.owned_workspace('sdk');original=SC.declaration('domain.work','work_review.followup')
 # Only the declared-fact supplier is varied; both publications use the actual Work/body owner.
 unconsumed=copy.deepcopy(original);unconsumed['segments']['request']={'public_fixture_unconsumed_change':True}
 monkeypatch.setattr(SC,'declaration',lambda owner,op:copy.deepcopy(unconsumed))
 def publish(request):
  phase=R.record('p',{'id':'kernel','phase':'handoff','request_id':request,'expected_work_revision':W._task_revision(W._tasks('p',tmp_path)['kernel']),'object':{'kind':'source'},'pins':first['phase']['pins']},tmp_path)
  return {**payload,'selection':{**payload['selection'],'handoff_id':phase['phase']['id']}}
 other=publish('kernel-unconsumed-change');one=K.prepare(tmp_path,scope,payload);two=K.prepare(tmp_path,scope,other)
 assert one['reference']['version']!=two['reference']['version'] and one['leaves']==two['leaves']
 assert len(K.input_frame(tmp_path,[payload,other])['receipts'])==2
 consumed=copy.deepcopy(original);consumed['segments']['authority']={'public_fixture_changed_authority':True}
 monkeypatch.setattr(SC,'declaration',lambda owner,op:copy.deepcopy(consumed))
 changed=publish('kernel-consumed-change')
 with pytest.raises(ValueError,match='CONFLICTING_EDITIONS'):K.input_frame(tmp_path,[payload,changed])
 (tmp_path/'segment-locality-proof.json').write_text(json.dumps({'retained_versions_differ':True,'unconsumed_same_leaf':True,'selected_receipts':2,'consumed_conflict_refused':True,'declared_fact_supplier_substituted':True},indent=2))


def test_actual_declared_work_inventory_stays_within_its_existing_budget(tmp_path,monkeypatch):
 from laplace.work import source_inventory as I
 from laplace.projects import writing_sources
 from laplace.core.identity import reference
 # Code-only selected-owner observation. Configuration alias lookup is explicitly unavailable in this fixture.
 root=Path(__file__).resolve().parents[1]
 monkeypatch.setattr(writing_sources,'target_for_path',lambda *_: (_ for _ in ()).throw(ValueError('Public fixture has no configured alias')))
 value=I.read(root,O.owned_workspace('sdk'),{'facet':'source-inventory','reference':reference('core.identity','subsystem',{'id':'domain.work'}),'limit':1})
 size=len(json.dumps(value,ensure_ascii=False).encode());assert size<=I.MAX_RESPONSE and value['coverage']['returned']>=1
 # The over-budget response is compacted, with its actual trigger recorded truthfully.
 meta=value['coverage']['metadata'];assert meta['state']=='COMPACT' and meta['contracts']==len(value['contracts'])
 trigger=meta['trigger'];assert trigger['budget']==I.MAX_RESPONSE and trigger['response_bytes']>I.MAX_RESPONSE
 assert trigger['reason'].startswith('Fixed declaration metadata alone')==(trigger['fixed_metadata_bytes']>I.MAX_RESPONSE)
 # H1: the three standing qualifications are stated once and equal those of every uncompacted current row.
 from collections import Counter
 from laplace import system
 scope=O.owned_workspace('sdk');description=system.load(root/'src/laplace/system/description.json')
 full={json.dumps(r['reference'],sort_keys=True):r for r in I._contracts(root,description,'domain.work',scope=scope) if r['state']=='CURRENT_DECLARATION_ONLY'}
 q=meta['row_qualifications'];assert full and q['runtime_source_linkage']['loaded_code_asserted'] is False
 assert all(r['runtime_source_linkage']==q['runtime_source_linkage'] and r['coverage']['qualification']==q['current_read'] and r['qualification']==q['disk_pin'] for r in full.values())
 assert {'segment_bases','segment_reads','coverage','runtime_source_linkage','qualification'}<=set(meta['omitted_fields']['contracts'])
 # H3: each compacted contract read, followed through the discovery owner, is the coarse contract whose segment ids,
 # bases and selectors equal the uncompacted row.
 compact=[r for r in value['contracts'] if r['state']=='CURRENT_DECLARATION_ONLY'];assert len(compact)==len(full)
 for row in compact:
  assert row['qualifications']=='coverage.metadata.row_qualifications' and 'runtime_source_linkage' not in row
  whole=full[json.dumps(row['reference'],sort_keys=True)];coarse=O.request(root,scope,row['read']['request'])
  assert {s['id']:s['basis'] for s in coarse['segments']}==whole['segment_bases'] and row['segments']==len(whole['segment_bases'])
  assert {s['id']:s['next']['select'] for s in coarse['segments']}==whole['segment_reads']['values']
 # Grouped unavailable rows conserve the (state, reason, declaration) multiset and its counts.
 _,unavailable=I._inputs(root,description,system.subsystems(description)['domain.work']);grouped=value['coverage']['unavailable']
 assert Counter((g['state'],g['reason'],d) for g in grouped for d in g['declarations'])==Counter((u['state'],u['reason'],u['declaration']) for u in unavailable)
 assert meta['unavailable']==len(unavailable) and meta['unavailable_groups']==len(grouped) and value['state']==('PARTIAL' if unavailable else 'AVAILABLE')
 # Ordinary continuation keeps the same basis and bound.
 nxt=value['pagination']['next_read'];assert value['coverage']['known']>value['coverage']['returned'] and nxt
 more=I.read(root,scope,nxt['request'])
 assert more['basis']==value['basis'] and more['pagination']['offset']==value['coverage']['returned'] and len(json.dumps(more,ensure_ascii=False).encode())<=I.MAX_RESPONSE
 # A fabricated as_of is refused as a mismatch; no input changed.
 with pytest.raises(ValueError,match='CHANGED_INPUT'):I.read(root,scope,{**nxt['request'],'as_of':'sha256:'+'0'*64})
 # An actual changed input: the configured source reader now resolves every path, so the observed basis moves and the
 # issued continuation pinned to the earlier basis refuses instead of mixing two observations.
 monkeypatch.setattr(writing_sources,'target_for_path',lambda _root,rel:{'repository':'fixture-reader','path':rel})
 moved=I.read(root,scope,{k:v for k,v in nxt['request'].items() if k!='as_of'});assert moved['basis']!=value['basis']
 with pytest.raises(ValueError,match='CHANGED_INPUT'):I.read(root,scope,nxt['request'])
 assert all(row['source_kernel_read']['http']['method']=='GET' for row in value['contracts'] if row.get('state')=='CURRENT_DECLARATION_ONLY')
 (tmp_path/'inventory-fit.json').write_text(json.dumps({'bytes':size,'cap':I.MAX_RESPONSE,'coverage':value['coverage'],'alias_lookup_unavailable':True},indent=2))


def test_publisher_and_handed_declaring_editions_must_match(tmp_path):
 payload,first=sample(tmp_path);path='src/laplace/work/project_work_review.py';target=tmp_path/path
 target.write_text(target.read_text()+'\n# public alternate disk edition\n')
 pin='sha256:'+hashlib.sha256(target.read_bytes()).hexdigest()
 second=R.record('p',{'id':'kernel','phase':'handoff','request_id':'different-declaring-edition','expected_work_revision':W._task_revision(W._tasks('p',tmp_path)['kernel']),'object':{'kind':'source'},'pins':{path:pin}},tmp_path)
 selected={**payload,'selection':{**payload['selection'],'handoff_id':second['phase']['id']}}
 with pytest.raises(ValueError,match='DECLARATION_EDITION_UNQUALIFIED'):K.prepare(tmp_path,O.owned_workspace('sdk'),selected)
 assert K.read(tmp_path,O.owned_workspace('sdk'),{**selected,'view':'segment','segments':['authority']})['state']=='RETAINED_SEGMENT'


def test_source_help_contexts_and_existing_budget(tmp_path):
 from laplace.native import declarations as D
 value=D.help_areas('book');assert len(json.dumps(value).encode())<32768
 assert all(x in D.CONTROL_DECLARATIONS for x in ['source:inspect','backlog:historical'])
 assert D.VIEW_STATES['source-inspector']['reading'] and D.VIEW_STATES['historical-obligations']['reading']
 (tmp_path/'help-metadata.json').write_text(json.dumps({'default_bytes':len(json.dumps(value).encode()),'canonical_bytes':len(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()),'cap':32768,'controls':['source:inspect','backlog:historical']},indent=2))


def test_issued_historical_http_long_record_continuation(tmp_path):
 from laplace.engine import historical_obligations as H
 from laplace.web import project_work_surface as WHTTP
 from urllib.parse import urlsplit,parse_qs
 (tmp_path/'contract').mkdir();row={'record':'promise','id':'PRM-long','status':'open','ask':('Public Ωαx '*2000)+'END_OWNED_RECORD'}
 raw=json.dumps(row,ensure_ascii=False).encode()+b'\n';(tmp_path/'contract/promises.jsonl').write_bytes(raw)
 scope=O.owned_workspace('sdk');catalogue=H.read(tmp_path,scope,{'facet':'historical-obligations','source':'promises'});read=catalogue['rows'][0]['read'];pages=[];joined=b''
 while read:
  u=urlsplit(read['http']['url']);status,_,body=WHTTP.handle(u.path,parse_qs(u.query),'GET',repo_root=tmp_path)
  assert status==200,body;value=json.loads(body);assert value['view']=='record' and value['id']==row['id']
  joined+=value['content'].encode();pages.append({'offset':value['content_offset'],'next':value['content_next_offset'],'bytes':len(body)});read=value['next_read']
 assert len(pages)>1 and joined==raw and b'END_OWNED_RECORD' in joined
 (tmp_path/'http-long-record-proof.json').write_text(json.dumps({'pages':pages,'complete_raw_bytes':len(raw),'complete':True,'all_http_200':True},indent=2))


def test_historical_record_pins_preserve_owned_class_and_prior_generations(tmp_path):
 from laplace.engine import historical_obligations as H
 (tmp_path/'corpus_friction').mkdir();path=tmp_path/'corpus_friction/work_orders.jsonl'
 scope=O.owned_workspace('sdk');request={'facet':'historical-obligations','source':'work_orders'}
 first={'record':'work_order','id':'WO-selected','status':'open','what':'Owned generation one Ω'}
 other={'record':'resolution','id':'WO-selected','status':'resolved','consumes':'WO-unrelated','evidence':['public-proof']}
 write=lambda rows:path.write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows))
 write([first,other]);catalogue=H.read(tmp_path,scope,request);old_read=catalogue['rows'][0]['read']['request']
 assert json.loads(H.read(tmp_path,scope,old_read)['content'])==first
 wrong={**old_read,'expected_sha256':'sha256:'+hashlib.sha256((json.dumps(other,ensure_ascii=False)+'\n').encode()).hexdigest()}
 with pytest.raises(ValueError,match='RECORD_CHANGED'):H.read(tmp_path,scope,wrong)
 second={**first,'what':'Owned generation two Ω'};write([first,other,second])
 current=H.read(tmp_path,scope,request)['rows'][0];assert current['title']==second['what']
 assert json.loads(H.read(tmp_path,scope,current['read']['request'])['content'])==second
 assert json.loads(H.read(tmp_path,scope,old_read)['content'])==first
 # Duplicate identical bytes are the same content identity, not a global immutable-ID failure.
 with path.open('a') as stream:stream.write(json.dumps(second,ensure_ascii=False)+'\n')
 assert json.loads(H.read(tmp_path,scope,current['read']['request'])['content'])==second
 (tmp_path/'owned-history-generation-proof.json').write_text(json.dumps({'owned':first,'other_class':other,'latest':second,'old_pin_retained':True,'other_class_pin_refused':True,'identical_repeated_content_readable':True},indent=2))


def test_reply_presentation_declaration_retains_its_declaring_source_for_the_kernel_consumer(tmp_path):
 # The real Work/body owners publish the new declaration for kernel.declared-source; prepared meaning only, never a publication.
 from laplace.writing import session_projection as SP
 root=tmp_path;(root/'p').mkdir();(root/'registry_projects.json').write_text(json.dumps({'projects':[{'name':'p','kind':'general','project_dir':'p'}]}))
 path='src/laplace/writing/session_projection.py';target=root/path;target.parent.mkdir(parents=True);target.write_bytes(Path(SP.__file__).read_bytes())
 binding={'owner':'domain.authoring','operation':'reply_presentation','consumer':K.CONSUMER}
 W.task('p',{'id':'reply','title':'Public reply presentation','goal':'Declared reply presentation facts','review_obligations':[{'id':'kernel','label':'Kernel facts','scope':'source','inputs':[path],'source_contract':binding}]},root)
 pin='sha256:'+hashlib.sha256(target.read_bytes()).hexdigest()
 first=R.record('p',{'id':'reply','phase':'handoff','request_id':'reply-kernel-handoff','expected_work_revision':W._task_revision(W._tasks('p',root)['reply']),'object':{'kind':'source'},'pins':{path:pin}},root)
 held=first['phase']['source_contracts']['kernel']
 assert set(held['segments'])==set(SP.source_contract()['segments']) and held['version']==SC.version(SP.source_contract())
 assert 'kernel_context' in held
 payload={'facet':'source-kernel','reference':SC.reference('domain.authoring','reply_presentation'),'selection':{'namespace':'p','work_id':'reply','handoff_id':first['phase']['id'],'obligation_id':'kernel'},'view':'prepare'}
 # All nine segments in one prepared envelope exceed the existing kernel read budget: refused whole, nothing clipped.
 with pytest.raises(ValueError,match='SOURCE_KERNEL_BUDGET'):K.read(root,O.owned_workspace('sdk'),payload)
 selected={**payload,'segments':['purpose','precedence','fallback']}
 prepared=K.read(root,O.owned_workspace('sdk'),selected)
 assert prepared['state']=='PREPARED' and prepared['kernel']['state']=='UNRESOLVED', 'retained meaning prepared; no publication claimed'
 names=list(SP.source_contract()['segments']);assert len(names)==9
 # All nine through owner-issued handles only: the up_read publications choice, its first single-segment read, then
 # segment_navigation previous/next and each leaf's retained_read. Same versioned reference, repository and source pin
 # throughout, each retained basis equal to the held one, every read within the public bound, none a publication.
 scope=O.owned_workspace('sdk');publications=K.read(root,scope,prepared['segment_navigation']['up_read']['request'])
 choice=next(c for c in publications['publications'] if c['selection']['handoff_id']==first['phase']['id'])
 start=K.read(root,scope,choice['read']['request']);seen={};queue=[start]
 while queue:
  part=queue.pop();nav=part['segment_navigation'];name=nav['segment']
  if name in seen:continue
  seen[name]=part
  assert part['state']=='PREPARED' and part['kernel']['state']=='UNRESOLVED' and [leaf['segment'] for leaf in part['leaves']]==[name]
  assert len(json.dumps(part,ensure_ascii=False).encode())<=16384 and pin.split(':')[1] in json.dumps(part['source_inputs'])
  assert (part['reference'],part['repository'],part['source_inputs'])==(start['reference'],start['repository'],start['source_inputs'])
  fact=K.read(root,scope,part['leaves'][0]['retained_read']['request']);held_basis=held['segments'][name]
  held_basis=held_basis['basis'] if isinstance(held_basis,dict) else held_basis
  assert fact['state']=='RETAINED_SEGMENT' and held_basis in json.dumps(fact) and len(json.dumps(fact,ensure_ascii=False).encode())<=16384
  queue+=[K.read(root,scope,nav[key]['request']) for key in ('previous_read','next_read') if key in nav]
 assert sorted(seen)==sorted(names) and start['reference']==SC.reference('domain.authoring','reply_presentation',SC.version(SP.source_contract()))
 frame=K.prepare(root,O.owned_workspace('sdk'),payload)
 assert len(frame['leaves'])==len(names)
