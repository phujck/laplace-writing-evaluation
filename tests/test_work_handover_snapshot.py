"""One selected engineering Work snapshot; no live ledger/approval transfer."""
import copy,json
from laplace.work import project_work as W,owner_discovery as O,object_facets as F,backlog
from laplace.projects import project_handover as H,artifacts


def test_selected_work_planning_hierarchy_and_standing_reopen_without_origin(tmp_path):
 root=tmp_path/'origin';root.mkdir();(root/'p').mkdir();(root/'registry_projects.json').write_text(json.dumps({'projects':[{'name':'p','kind':'general','project_dir':'p'}]}))
 for ident,extras in [('parent',{}),('prerequisite',{}),('selected',{'parent_work_id':'parent','depends_on':['prerequisite']})]:
  W.task('p',{'id':ident,'title':'Public '+ident,'goal':'Exact selected engineering purpose Ω',**extras},root)
 proof=root/'public-evidence.txt';proof.write_text('Accepted old public evidence Ω')
 for ident in ['prerequisite','selected']:
  action=W.read('p',{'view':'detail','id':ident},root)['allowed_actions']['task_status']['payload']
  W.transition('p',{**action,'status':'done','evidence':['public-evidence.txt']},root)
 wire=copy.deepcopy(W.read('p',{'view':'planning','id':'selected'},root)['actions']['planning']['payload'])
 wire['planning'].update(priority=42,order=-7,deferred=True,reason='A deliberate future maintenance choice, not undone completion.')
 W.task('p',wire,root);proof.write_text('Later public evidence Ω has changed')
 scope=O.owned_workspace('sdk');refs=[O.work_reference('p',ident) for ident in ['selected','parent']]
 observed={ref['identity']['id']:F._observe(root,scope,ref) for ref in refs}
 entries=[{'class':'included','reference':r,'expected_basis':observed[r['identity']['id']]['basis'],'permit_export':True} for r in refs]
 payload={'project':'p','action':'prepare','request_id':'public-engineering-snapshot','entries':entries,'max_files':30,'max_rows':30,'max_bytes':200000}
 prepared=H.object_request(root,scope,payload,door={'origin':'sdk'});assert prepared['state']=='RECORDED'
 dest=tmp_path/'recipient';exported=H.object_request(root,scope,{'project':'p','action':'export','reference':prepared['reference'],'expected_basis':prepared['basis'],'destination':str(dest)},door={'origin':'sdk'})
 assert exported['status']=='EXPORTED'
 root.rename(tmp_path/'unavailable-origin')
 inspection=H.inspect_handover(dest);reopened=H._inspect_object(dest);assert reopened['origin_reads']==0 and inspection['providers_started']==0
 manifest,_=H._json_artifact(dest,'p',prepared['reference']['identity']['id']);snapshots={}
 for item in manifest['entries']:
  value=json.loads(artifacts.read(dest,'p',{'id':item['artifact_id'],'expected_sha256':item['carried']['sha256'],'limit':20000})['content'])
  snapshots[value['subject']['identity']['id']]=value
 selected=snapshots['selected'];original=observed['selected']['value']
 assert selected['planning']==backlog.projection('p',original)
 assert selected['planning']['priority']==42 and selected['planning']['order']==-7 and selected['planning']['deferred']
 assert selected['planning']['revision']==original['planning_revision']
 assert selected['lifecycle']['completed'] is True and selected['current_acceptance']=={k:original['current_acceptance'][k] for k in ('status','review_required','kind') if k in original['current_acceptance']}
 assert selected['currentness']=={k:original['currentness'][k] for k in ('status','kind') if k in original['currentness']}
 assert snapshots['parent']['planning']['authored'] is False and snapshots['parent']['planning']['priority']==0
 relations=selected['relationships']['items'];assert [(r['relation'],r['source']['identity']['id'],r['target']['identity']['id']) for r in relations]==[('contains','parent','selected'),('requires','selected','prerequisite')]
 assert all('legacy' not in ref and 'read' not in ref for r in relations for ref in [r['source'],r['target']])
 text=json.dumps(snapshots);assert 'allowed_actions' not in text and 'APPROVED' not in text and 'public-evidence.txt' not in text
 assert not (dest/'corpus_friction/work_orders.jsonl').exists() and not (dest/'corpus_friction/p.jsonl').exists()
 (tmp_path/'work-snapshot-proof.json').write_text(json.dumps({'observed':{k:{'basis':v['basis']} for k,v in observed.items()},'snapshots':snapshots,'manifest':manifest,'inspection':inspection,'reopened':reopened},indent=2,ensure_ascii=False))


def test_workspace_selected_unregistered_work_uses_registered_custody_not_identity(tmp_path,monkeypatch):
 import pytest
 root=tmp_path/'origin';root.mkdir();(root/'p').mkdir();registry=root/'registry_projects.json';registry.write_text(json.dumps({'projects':[{'name':'p','kind':'general','project_dir':'p'}]}));before=registry.read_bytes()
 W.task('orphan',{'id':'unregistered-engineering','title':'Public unregistered engineering','goal':'Frozen metadata only Ω'},root)
 action=W.read('orphan',{'view':'planning','id':'unregistered-engineering'},root)['actions']['planning']['payload'];action=copy.deepcopy(action)
 action['planning'].update(priority=77,order=-19,deferred=True,reason='Retain an explicit external namespace observation.')
 W.task('orphan',action,root);ref=O.work_reference('orphan','unregistered-engineering');scope=O.owned_workspace('sdk');observed=F._observe(root,scope,ref)
 payload={'project':'p','action':'prepare','request_id':'explicit-cross-namespace-work','entries':[{'class':'included','reference':ref,'expected_basis':observed['basis'],'permit_export':True}],'max_files':30,'max_rows':30,'max_bytes':200000}
 calls=[];original=F._observe
 def tracked(*a,**kw):calls.append(a[2]);return original(*a,**kw)
 monkeypatch.setattr(F,'_observe',tracked)
 for wrong_scope,door in [(O.project_scope('p','http'),{'origin':'human'}),(O.project_scope('p','sdk'),{'origin':'sdk'}),(O.owned_workspace('native'),{'origin':'native'})]:
  with pytest.raises(ValueError,match='EXPLICIT_AUTHOR_EXPORT_SELECTION_REQUIRED'):H.object_request(root,wrong_scope,payload,door=door)
 assert not calls
 with pytest.raises(ValueError,match='INVALID_HANDOVER_REQUEST'):H.object_request(root,scope,{**payload,'allow_cross_project':True},door={'origin':'sdk'})
 forged=copy.deepcopy(payload);forged['entries'][0]['allow_cross_project']=True
 with pytest.raises(ValueError,match='EXPLICIT_PERMITTED_ENTRY_REQUIRED'):H.object_request(root,scope,forged,door={'origin':'sdk'})
 foreign=copy.deepcopy(payload);foreign['entries'][0]['reference']={'schema_version':'laplace.reference/1','owner':'domain.research','kind':'concept','identity':{'project':'orphan','node':'question:unread'}}
 with pytest.raises(ValueError,match='FOREIGN_SELECTED_OBJECT'):H.object_request(root,scope,foreign,door={'origin':'sdk'})
 with pytest.raises(ValueError):H.object_request(root,scope,{**payload,'project':'absent'},door={'origin':'sdk'})
 malformed=copy.deepcopy(payload);malformed['entries'][0]['reference']={**ref,'scope':{'kind':'owned-workspace'}}
 with pytest.raises(ValueError,match='INVALID_SELECTED_REFERENCE'):H.object_request(root,scope,malformed,door={'origin':'sdk'})
 assert not calls
 prepared=H.object_request(root,scope,payload,door={'origin':'sdk'});assert prepared['state']=='RECORDED' and calls and all(x==ref for x in calls)
 dest=tmp_path/'recipient';out=H.object_request(root,scope,{'project':'p','action':'export','reference':prepared['reference'],'expected_basis':prepared['basis'],'destination':str(dest)},door={'origin':'sdk'})
 assert out['status']=='EXPORTED' and registry.read_bytes()==before
 root.rename(tmp_path/'offline-origin');assert H._inspect_object(dest)['origin_reads']==0
 manifest,_=H._json_artifact(dest,'p',prepared['reference']['identity']['id']);entry=manifest['entries'][0]
 snapshot=json.loads(artifacts.read(dest,'p',{'id':entry['artifact_id'],'expected_sha256':entry['carried']['sha256'],'limit':20000})['content'])
 assert snapshot['subject']['identity']=={'namespace':'orphan','id':'unregistered-engineering'}
 assert snapshot['planning']==backlog.projection('orphan',observed['value']) and snapshot['planning']['priority']==77 and snapshot['planning']['order']==-19
 assert [x['name'] for x in json.loads((dest/'registry_projects.json').read_text())['projects']]==['p']
 assert not (dest/'corpus_friction/work_orders.jsonl').exists() and not W.read('orphan',{'view':'summary'},dest)['tasks']
 (tmp_path/'cross-namespace-work-proof.json').write_text(json.dumps({'snapshot':snapshot,'manifest':manifest,'inspection':H.inspect_handover(dest),'rejected_before_read':True,'original_registry_unchanged':True},indent=2,ensure_ascii=False))


def test_selected_work_export_uses_indexed_rows_above_global_journal_bound(tmp_path,monkeypatch):
 import pytest
 from laplace.core.records import capture
 from laplace.writing import records
 root=tmp_path/'origin';root.mkdir();(root/'p').mkdir();(root/'registry_projects.json').write_text(json.dumps({'projects':[{'name':'p','kind':'general','project_dir':'p'}]}));(root/'contract').mkdir()
 journal=root/'contract/talk.jsonl';padding=json.dumps({'record':'public-unrelated-padding','body':'PUBLIC_PADDING_'*80000}).encode()+b'\n'
 with journal.open('wb') as out:
  for n in range(65):out.write(padding)
 assert journal.stat().st_size>H.C.MAX_JSON
 padding_bytes=journal.stat().st_size
 with pytest.raises(ValueError,match='LEDGER_SCAN_BOUND'):H._bounded_rows(root,'contract/talk.jsonl')
 W.task('p',{'id':'scaled-selected','title':'Public selected scale','goal':'Only this engineering metadata is carried.'},root)
 scope=O.owned_workspace('sdk');ref=O.work_reference('p','scaled-selected');basis=F._observe(root,scope,ref)['basis']
 bounded=H._bounded_rows
 def no_global_talk(root_,rel):
  if rel in {'contract/talk.jsonl','contract/dispatches.jsonl'}:pytest.fail('Global raw-row scan or empty definition collector called')
  return bounded(root_,rel)
 monkeypatch.setattr(H,'_bounded_rows',no_global_talk)
 original=capture.read_captured_row;reads=[]
 def captured(path,offset,end,digest):
  if path==journal:
   assert offset>=padding_bytes;reads.append(end-offset)
  return original(path,offset,end,digest)
 monkeypatch.setattr(capture,'read_captured_row',captured)
 prepared=H.object_request(root,scope,{'project':'p','action':'prepare','request_id':'scaled-public-selected-work','entries':[{'class':'included','reference':ref,'expected_basis':basis,'permit_export':True}],'max_files':30,'max_rows':30,'max_bytes':200000},door={'origin':'sdk'})
 assert prepared['state']=='RECORDED'
 dest=tmp_path/'recipient';out=H.object_request(root,scope,{'project':'p','action':'export','reference':prepared['reference'],'expected_basis':prepared['basis'],'destination':str(dest)},door={'origin':'sdk'})
 assert out['status']=='EXPORTED' and H._inspect_object(dest)['origin_reads']==0
 assert reads and sum(reads)<200000 and (dest/'contract/talk.jsonl').stat().st_size<200000
 manifest,_=H._json_artifact(root,'p',prepared['reference']['identity']['id']);ids=manifest['selection']['artifact_ids']+[prepared['reference']['identity']['id']]
 with pytest.raises(ValueError,match='SELECTED_ARTIFACT_CUSTODY'):H._selected_artifact_rows(root,'foreign',ids,max_rows=30,max_bytes=200000)
 with pytest.raises(ValueError,match='SELECTED_ARTIFACT_ROW_BUDGET'):H._selected_artifact_rows(root,'p',ids,max_rows=30,max_bytes=1)
 idx=records.index(root);meta=idx.by_id[ids[0]][0];_row,raw=original(journal,meta['_offset'],meta['_end'],meta['_hash'])
 with journal.open('ab') as stream:stream.write(raw)
 with pytest.raises(ValueError,match='SELECTED_ARTIFACT_CUSTODY'):H._selected_artifact_rows(root,'p',ids,max_rows=30,max_bytes=200000)
 # Restore only the public duplicate appended by this test, then incomplete tail is UNKNOWN.
 with journal.open('r+b') as stream:
  end=stream.seek(0,2)-len(raw);stream.truncate(end);stream.seek(end);stream.write(b'{"incomplete":')
 with pytest.raises(ValueError,match='SELECTED_ARTIFACT_CUSTODY_UNKNOWN'):H._selected_artifact_rows(root,'p',ids,max_rows=30,max_bytes=200000)
 (tmp_path/'scaled-selected-export-proof.json').write_text(json.dumps({'global_journal_bytes':padding_bytes,'unchanged_global_bound':H.C.MAX_JSON,'selected_raw_reads':len(reads),'selected_raw_bytes':sum(reads),'recipient_bytes':(dest/'contract/talk.jsonl').stat().st_size,'no_global_raw_scan':True,'empty_definitions_not_scanned':True,'wrong_project_budget_duplicate_partial_refused':True,'inspection':out['inspection']},indent=2))
