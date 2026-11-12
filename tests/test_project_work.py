from pathlib import Path
import json
import pytest
from laplace.work import project_work as w
from laplace.web import project_work_surface as surface
from laplace.projects import library as writing_projects

def selected_project(root):
 """Work currentness observes a real declared source, alongside its evidence."""
 manuscript=root/'manuscript';manuscript.mkdir()
 (manuscript/'main.tex').write_text('\\documentclass{article}\n\\begin{document}Fixture.\\end{document}\n')
 (root/'registry_projects.json').write_text(json.dumps({'projects':[{
  'name':'p','kind':'conceptric','project_dir':'.','tex_root':'manuscript/main.tex'}]}))

def guarded_task(project,payload,root):
 prior=w._tasks(project,root).get(payload.get('id'))
 return w.task(project,{**({'expected_work_revision':w._task_revision(prior)} if prior else {}),**payload},root)

def guarded_transition(project,payload,root):
 tasks=w._tasks(project,root);task=tasks[payload['id']]
 basis,_=w._work_basis(tasks,task['id'])
 return w.transition(project,{'expected_work_scope_revision':basis['scope_revision'],
  'expected_work_status_revision':w._standing_revision(task),
  'expected_dependency_revision':w._dependency_revision(task,tasks),**payload},root)

def test_tasks_ready_and_evidence_gate(tmp_path,monkeypatch):
 selected_project(tmp_path)
 monkeypatch.setattr(w,'_root',lambda x=None:Path(tmp_path))
 monkeypatch.setattr('laplace.pipeline.authoring.load',lambda *a,**k:{'revision':0,'framing':{}})
 a=guarded_task('p',{'title':'evidence','goal':'measure'},tmp_path)
 b=guarded_task('p',{'title':'write','goal':'explain','depends_on':[a['id']]},tmp_path)
 assert w.state('p',tmp_path)['ready'][0]['id']==a['id']
 try:guarded_transition('p',{'id':a['id'],'status':'done'},tmp_path);assert False
 except ValueError:pass
 evidence=tmp_path/'evidence'/'run-1.json';evidence.parent.mkdir();evidence.write_text('{"ok":true}\n')
 guarded_transition('p',{'id':a['id'],'status':'done','evidence':['evidence/run-1.json']},tmp_path)
 assert any(x['id']==b['id'] for x in w.state('p',tmp_path)['ready'])

def test_surface_uses_scanner_bytes_contract(tmp_path,monkeypatch):
 monkeypatch.setattr(w,'_root',lambda x=None:Path(tmp_path))
 monkeypatch.setattr('laplace.pipeline.authoring.load',lambda *a,**k:{'revision':0,'framing':{}})
 code,ctype,body=surface.handle('/work/task',{},'POST',b'{"project":"p","title":"x","goal":"y"}',tmp_path)
 assert code==201 and ctype=='application/json' and b'WORK-' in body

def test_summary_state_uses_only_authoring_framing_projection(tmp_path,monkeypatch):
 (tmp_path/'registry_projects.json').write_text(json.dumps({'projects':[{'name':'p','project_dir':'p'}]}))
 monkeypatch.setattr('laplace.pipeline.authoring.summary',lambda *a,**k:{'project':'p','revision':7,'argument_revision':3,
  'argument':'Argument','framing':{'purpose':'Explain'},'section_ids':['N1']})
 monkeypatch.setattr('laplace.pipeline.authoring.load',lambda *a,**k:{'revision':7,'framing':{'purpose':'Explain'},'contexts':[{'large':'historical body'}]})
 task=guarded_task('p',{'title':'Continue','goal':'A visible task'},tmp_path)
 full=w.state('p',tmp_path)
 monkeypatch.setattr('laplace.pipeline.authoring.load',lambda *a,**k:(_ for _ in ()).throw(AssertionError('full load')))
 code,ctype,body=surface.handle('/work/state',{'project':['p'],'view':['summary']},'GET',b'',tmp_path)
 value=json.loads(body)
 assert code==200 and ctype=='application/json'
 assert value['framing']['revision']==7 and value['framing']['argument']=='Argument'
 assert value['framing']['framing']['purpose']=='Explain' and 'contexts' not in value['framing']
 assert value['tasks'][0]['id']==task['id']
 # LIST rows carry standing, not pins; the detail read carries the exact revision identities.
 assert 'work_scope_revision' not in value['tasks'][0]
 focused=w.read('p',{'view':'detail','id':task['id']},tmp_path)['task']
 assert focused['work_scope_revision']==full['tasks'][0]['work_scope_revision']
 assert value['tasks'][0]['currentness']['status']==full['tasks'][0]['currentness']['status']
 assert value['pagination']['total']==1 and value['read_cut']['revision']

def test_style_routes_to_the_template_owner_and_refuses_the_retired_profile_preview(tmp_path,monkeypatch):
 # /work/style is the document-template owner's door (prepare|apply|recover with exact
 # guards). The old "save a profile and start a preview" path is retired: a legacy
 # payload is refused by the owner contract and never reaches a preview renderer.
 from laplace.manuscript import document_style
 monkeypatch.setattr(document_style,'preview',lambda *a,**k:pytest.fail('retired profile preview must not run'))
 with pytest.raises(ValueError,match='owner contract'):
  w.style('p',{'profile':'article'},tmp_path)
 from laplace.manuscript.template_contracts import change_contract
 assert [branch['properties']['action']['const'] for branch in change_contract()['oneOf']]==['prepare','apply','recover']

def test_task_sections_must_resolve_and_verified_has_no_self_award_door(tmp_path,monkeypatch):
 manuscript=tmp_path/'book/manuscript';manuscript.mkdir(parents=True)
 (tmp_path/'registry_projects.json').write_text(json.dumps({'projects':[{
  'name':'book','project_dir':'book','tex_root':'book/manuscript',
  'manifest':{'document':{'root':'book/manuscript/main.tex'}}}]}))
 (manuscript/'main.tex').write_text('\\documentclass{article}\n\\begin{document}x\\end{document}\n')
 (manuscript/'projection_plan.json').write_text(json.dumps({'meta':{'project':'book'},
  'sections':[{'id':'N1','title':'One','beats':[],'nodes_in_order':[]}]}))
 monkeypatch.setattr('laplace.pipeline.authoring.load',lambda *a,**k:{'revision':0,'framing':{}})
 with __import__('pytest').raises(ValueError,match='section_ids'):
  guarded_task('book',{'title':'bad','goal':'bad','section_ids':['missing']},tmp_path)
 task=guarded_task('book',{'title':'good','goal':'good','section_ids':['N1']},tmp_path)
 evidence=tmp_path/'evidence/result.json';evidence.parent.mkdir();evidence.write_text('{}')
 guarded_transition('book',{'id':task['id'],'status':'done','evidence':['evidence/result.json']},tmp_path)
 with __import__('pytest').raises(ValueError,match='independent'):
  guarded_transition('book',{'id':task['id'],'status':'verified','evidence':['evidence/result.json']},tmp_path)

def test_session_request_task_preserves_a_validated_source_anchor(tmp_path,monkeypatch):
 manuscript=tmp_path/'book/manuscript';manuscript.mkdir(parents=True)
 (tmp_path/'registry_projects.json').write_text(json.dumps({'projects':[{
  'name':'book','project_dir':'book','tex_root':'book/manuscript',
  'manifest':{'document':{'root':'book/manuscript/main.tex'}}}]}))
 (manuscript/'main.tex').write_text('\\documentclass{article}\n\\begin{document}\nEditable text.\n\\end{document}\n')
 monkeypatch.setattr('laplace.pipeline.authoring.load',lambda *a,**k:{'revision':0,'framing':{}})
 task=guarded_task('book',{'id':'REQUEST-one','title':'Cite this','goal':'Find a source.',
  'kind':'session-request','section_ids':[],
  'anchor':{'file':'main.tex','line_start':3,'line_end':3,'quote':'Editable text.','section':'sec:one'}},tmp_path)
 state=next(row for row in w.state('book',tmp_path)['tasks'] if row['id']=='REQUEST-one')
 assert task['anchor']==state['anchor']=={'file':'main.tex','line_start':3,'line_end':3,
                                            'quote':'Editable text.','section':'sec:one'}
 with __import__('pytest').raises(ValueError,match='anchor file'):
  guarded_task('book',{'title':'bad','goal':'bad','kind':'session-request',
                 'anchor':{'file':'../outside.tex'}},tmp_path)
 cancelled=guarded_transition('book',{'id':'REQUEST-one','status':'cancelled'},tmp_path)
 assert cancelled['status']=='cancelled'
 assert not any(row['id']=='REQUEST-one' for row in w.state('book',tmp_path)['ready'])
 ordinary=guarded_task('book',{'title':'ordinary','goal':'ordinary'},tmp_path)
 with __import__('pytest').raises(ValueError,match='session-request'):
  guarded_transition('book',{'id':ordinary['id'],'status':'cancelled'},tmp_path)

def test_editing_task_title_and_goal_preserves_omitted_semantics(tmp_path,monkeypatch):
 manuscript=tmp_path/'book/manuscript';manuscript.mkdir(parents=True)
 (tmp_path/'registry_projects.json').write_text(json.dumps({'projects':[{
  'name':'book','project_dir':'book','tex_root':'book/manuscript',
  'manifest':{'document':{'root':'book/manuscript/main.tex'}}}]}))
 (manuscript/'main.tex').write_text('\\documentclass{article}\n\\begin{document}x\\end{document}\n')
 (manuscript/'projection_plan.json').write_text(json.dumps({'meta':{'project':'book'},
  'sections':[{'id':'N1','title':'One','beats':[],'nodes_in_order':[]}]}))
 monkeypatch.setattr('laplace.pipeline.authoring.load',lambda *a,**k:{'revision':0,'framing':{}})
 prerequisite=guarded_task('book',{'title':'Prerequisite','goal':'Establish it'},tmp_path)
 original=guarded_task('book',{'title':'Draft','goal':'Explain it','kind':'writing',
  'depends_on':[prerequisite['id']],'section_ids':['N1'],'evidence':['notes/original.md'],
  'origin':'author:fixture'},tmp_path)

 updated=guarded_task('book',{'id':original['id'],'title':'Revised title','goal':'Sharper condition'},tmp_path)
 resolved=next(row for row in w.state('book',tmp_path)['tasks'] if row['id']==original['id'])

 assert updated['task_kind']=='writing' and updated['depends_on']==[prerequisite['id']]
 assert updated['section_ids']==['N1'] and updated['evidence']==['notes/original.md']
 assert updated['origin']=='author:fixture' and resolved['status']=='blocked'

def test_imported_revtex_derives_article_form_without_writing_source(tmp_path):
 source=tmp_path/'adaptive/manuscript';source.mkdir(parents=True)
 main=source/'main.tex';main.write_text(
  '% \\documentclass{book}\n\\documentclass[reprint,aps,prx]{revtex4-2}\n'
  '\\begin{document}\nSubstantive adaptive normal form prose.\n\\end{document}\n')
 before=main.read_bytes()
 status,result=writing_projects.import_source({'name':'adaptive','title':'Adaptive Normal Form',
  'root':'adaptive/manuscript/main.tex','editable':True},tmp_path)
 assert status==201,result

 value=w.state('adaptive',tmp_path)

 assert value['form']=='article'
 assert value['form_origin']=='selected-source'
 assert value['form_source']['documentclass']=='revtex4-2'
 assert value['form_source']['source_revision']
 assert main.read_bytes()==before
 assert not (source/'manuscript_spec.json').exists()

def test_authored_manuscript_genre_wins_over_selected_source_class(tmp_path):
 source=tmp_path/'report/manuscript';source.mkdir(parents=True)
 main=source/'main.tex';main.write_text(
  '\\documentclass{article}\n\\begin{document}\nSubstantive report prose.\n\\end{document}\n')
 (source/'manuscript_spec.json').write_text(json.dumps({'manuscript':{'genre':'report'}}))
 before={path.name:path.read_bytes() for path in source.iterdir()}
 status,result=writing_projects.import_source({'name':'authored','title':'Authored Report',
  'root':'report/manuscript/main.tex','editable':True},tmp_path)
 assert status==201,result

 value=w.state('authored',tmp_path)

 assert value['form']=='report' and value['form_origin']=='manuscript-spec'
 assert value['form_source']=={'origin':'manuscript-spec','documentclass':None,'source_revision':None}
 assert {path.name:path.read_bytes() for path in source.iterdir()}==before


def test_summary_and_full_share_currentness_without_rehashing_shared_evidence(tmp_path, monkeypatch):
 selected_project(tmp_path)
 import hashlib
 evidence=tmp_path/'result.bin'; evidence.write_bytes(b'observed result'*8192)
 receipt={'path':'result.bin','sha256':hashlib.sha256(evidence.read_bytes()).hexdigest()}
 tasks={f'WORK-{i}':{'id':f'WORK-{i}','status':'done','evidence_receipts':[receipt]} for i in range(12)}
 tasks['WORK-follow']={'id':'WORK-follow','status':'open','depends_on':['WORK-0']}
 monkeypatch.setattr(w,'_tasks',lambda *a:tasks)
 monkeypatch.setattr('laplace.pipeline.authoring.load',lambda *a,**k:{'framing':{}})
 monkeypatch.setattr('laplace.pipeline.authoring.summary',lambda *a,**k:{'framing':{}})
 opened=[]; open_file=Path.open; read_bytes=Path.read_bytes
 def observed_open(path,*args,**kwargs):
  if path==evidence:opened.append(path)
  return open_file(path,*args,**kwargs)
 def no_body(path):
  assert path!=evidence,'currentness must stream evidence, not load its full body'
  return read_bytes(path)
 monkeypatch.setattr(Path,'open',observed_open)
 monkeypatch.setattr(Path,'read_bytes',no_body)
 w._DIGEST_CACHE.clear()
 full=w.state('p',tmp_path); assert len(opened)==1
 # A second read within the same stat identity reuses the digest: one stat, no reopen.
 summary=w.summary('p',tmp_path); assert len(opened)==1
 assert summary['tasks']==full['tasks']
 assert [t['status'] for t in summary['tasks']]==['done']*12+['ready']
 evidence.write_bytes(b'changed result')
 changed=w.summary('p',tmp_path)
 assert all(t['status']=='blocked' for t in changed['tasks'])
 assert changed['tasks'][0]['currentness']['status']=='STALE'
 assert len(opened)==3  # original read, changed write, fresh read of the changed identity


def test_work_containment_context_and_completion_currentness(tmp_path, monkeypatch):
 selected_project(tmp_path)
 import pytest
 monkeypatch.setattr('laplace.pipeline.authoring.load',lambda *a,**k:{'framing':{}})
 monkeypatch.setattr('laplace.pipeline.authoring.summary',lambda *a,**k:{'framing':{}})
 parent=guarded_task('p',{'id':'campaign','title':'Campaign','goal':'Explain observed mechanisms','kind':'campaign'},tmp_path)
 middle=guarded_task('p',{'id':'chapter','title':'Chapter','goal':'Explain dependency currentness','parent_work_id':'campaign'},tmp_path)
 leaf=guarded_task('p',{'id':'figure','title':'Figure','goal':'Show changed source propagation','parent_work_id':'chapter'},tmp_path)
 assert not leaf['depends_on']
 context=w.context('p','figure',tmp_path)
 assert [r['id'] for r in context['ancestors']]==['campaign','chapter']
 assert 'Explain observed mechanisms' in context['prompt']
 assert context['status']=='ready'  # containment does not schedule prerequisites
 rows={row['id']:row for row in w.state('p',tmp_path)['tasks']}
 assert rows['campaign']['child_work_ids']==['chapter']
 assert rows['chapter']['child_work_ids']==['figure']
 before=w._ledger(tmp_path).read_bytes()
 with pytest.raises(ValueError,match='cycle'):
  guarded_task('p',{'id':'campaign','parent_work_id':'figure'},tmp_path)
 assert w._ledger(tmp_path).read_bytes()==before
 guarded_task('other',{'id':'foreign','title':'Foreign','goal':'Separate owner'},tmp_path)
 with pytest.raises(ValueError,match='existing work'):
  guarded_task('p',{'id':'figure','parent_work_id':'foreign'},tmp_path)
 report=tmp_path/'report.txt';report.write_text('observed result')
 guarded_transition('p',{'id':'figure','status':'done','evidence':['report.txt']},tmp_path)
 rows={row['id']:row for row in w.summary('p',tmp_path)['tasks']}
 assert rows['figure']['status']=='done' and rows['campaign']['status']=='ready'
 assert rows['figure']['completion_work_basis']==context['work_basis']
 guarded_task('p',{'id':'unrelated','title':'Other','goal':'Independent work'},tmp_path)
 assert w.context('p','figure',tmp_path)['work_basis']==context['work_basis']
 guarded_task('p',{'id':'campaign','goal':'Explain only independently observed mechanisms'},tmp_path)
 updated=w.context('p','figure',tmp_path)
 assert updated['work_basis']!=context['work_basis']
 assert updated['status']=='blocked' and updated['evidence_currentness']['status']=='STALE'
 assert w._tasks('p',tmp_path)['figure']['completion_work_basis']==context['work_basis']
 guarded_task('p',{'id':'figure','parent_work_id':None},tmp_path)
 assert w.context('p','figure',tmp_path)['ancestors']==[]


def test_concurrent_reparenting_cannot_create_containment_cycle(tmp_path):
 import concurrent.futures, threading
 for ident in ('a','b'):guarded_task('p',{'id':ident,'title':ident,'goal':'Keep ownership acyclic'},tmp_path)
 barrier=threading.Barrier(2)
 def move(ident,parent):
  barrier.wait()
  try:guarded_task('p',{'id':ident,'parent_work_id':parent},tmp_path);return 'saved'
  except ValueError:return 'refused'
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
  a=pool.submit(move,'a','b');b=pool.submit(move,'b','a')
  assert sorted([a.result(),b.result()])==['refused','saved']
 for ident in ('a','b'):assert w._work_ancestors(w._tasks('p',tmp_path),ident)[1] is None


def test_nested_work_fold_hashes_each_spec_once_and_retains_compact_basis(tmp_path,monkeypatch):
 import hashlib
 evidence=tmp_path/'result';evidence.write_text('one shared result')
 receipt={'path':'result','sha256':hashlib.sha256(evidence.read_bytes()).hexdigest()}
 original=w._task_revision;counts=[]
 for count in (16,32):
  tasks={f'WORK-{i}':{'id':f'WORK-{i}','project':'p','title':'Goal','goal':'Observed result',
      'status':'done','parent_work_id':f'WORK-{i-1}' if i else None,'evidence_receipts':[receipt]} for i in range(count)}
  cache={}
  for ident,row in tasks.items():row['completion_work_basis']=w._work_basis(tasks,ident,cache=cache)[0]
  calls=[]
  monkeypatch.setattr(w,'_task_revision',lambda row:calls.append(row['id']) or original(row))
  observed=w._resolved_tasks(tasks,tmp_path)
  counts.append(len(calls));assert all(row['status']=='done' for row in observed)
  assert all('ancestors' not in row['completion_work_basis'] for row in observed)
  assert len(observed[-1]['completion_work_basis'])==len(observed[0]['completion_work_basis'])
  tasks['WORK-0']['goal']='A changed global goal'
  assert all(row['status']=='blocked' for row in w._resolved_tasks(tasks,tmp_path))
  monkeypatch.setattr(w,'_task_revision',original)
 assert counts==[16,32]


def test_early_ancestor_list_completion_receipt_remains_readable(tmp_path):
 import hashlib
 evidence=tmp_path/'result';evidence.write_text('observed result')
 parent={'id':'parent','title':'Parent','goal':'Original goal'}
 child={'id':'child','project':'p','title':'Child','goal':'Original result','parent_work_id':'parent','status':'done',
        'evidence_receipts':[{'path':'result','sha256':hashlib.sha256(evidence.read_bytes()).hexdigest()}]}
 child['completion_work_basis']={'work_id':'child','revision':w._task_revision(child),
                                'ancestors':[{'id':'parent','revision':w._task_revision(parent)}]}
 tasks={'parent':parent,'child':child}
 assert w._resolved_tasks(tasks,tmp_path)[1]['status']=='done'
 parent['goal']='Changed goal'
 assert w._resolved_tasks(tasks,tmp_path)[1]['status']=='blocked'
