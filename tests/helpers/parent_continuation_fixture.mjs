import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';

// Exact current owner coordinates in a small provider-free fixture. UI phase
// timing cases use these handles; actual dispatch execution is tested separately.
const generated=spawnSync('./scripts/laplace-python',['-c',String.raw`
import json,tempfile,time,sys
from pathlib import Path
import pytest
sys.path.insert(0,'tests')
from test_dispatch_plan_contract import parent,example
from test_dispatch_parent import synthesis_case,retained_execution_case
from laplace.web import authoring as authoring_surface; from laplace.work import project_work; from laplace.native import tools as writing_tools
from laplace.writing import dispatch_parent; from laplace.projects import artifacts
monkey=pytest.MonkeyPatch()
with tempfile.TemporaryDirectory(prefix='laplace-parent-consumer-') as raw:
 bank=authoring_surface._bank
 def admit_once(root,row):
  if row.get('record')=='writing-turn' and row.get('id')=='WT-parent':row={**row,'connected_observation':dispatch_parent.observation_budget(300)}
  return bank(root,row)
 monkey.setattr(authoring_surface,'_bank',admit_once)
 make=getattr(parent,'__wrapped__',None) or parent._get_wrapped_function()
 fixture=make(Path(raw),monkey);root=next(fixture)
 authoring_surface._begin_child_execution(root,'WS-parent',{'project':'book','session_id':'WS-parent','turn_id':'WT-parent','state':'RUNNING','host':authoring_surface._process_identity()})
 declared=example();declared['synthesis_return_path']='development/parent-synthesis.json'
 created=writing_tools.execute(root,'book','work','dispatch_plan',{'title':'UI fixture dispatch','goal':'Observe exact child state in the parent UI.','path':'development/ui-dispatch-plan.json','plan':declared},turn_id='WT-parent')
 task=project_work._tasks('book',root)[created['dispatch_id']]
 observation=dispatch_parent.prepare_observation(task,'book',root,'WT-parent',time.time())
 current=dispatch_parent.public(root,'book',observation)
 artifacts.store(root,'book',{'path':'development/ui-return.json','before':None,'content':json.dumps({'note':'UI coordinate fixture; not a typed completion claim'}),'reason':'Exact consumer coordinate fixture.'})
 artifact=dispatch_parent.artifact_metadata(root,'book','development/ui-return.json')
 detail=project_work.read('book',{'view':'detail','id':created['dispatch_id']},root)
 result={'observation':current,'artifact':artifact,'task':created['task'],'detail':detail}
 fixture.close()
for accepted in (True,False):
 with tempfile.TemporaryDirectory(prefix='laplace-parent-synthesis-consumer-') as raw:
  fixture=make(Path(raw),monkey);root=next(fixture)
  task,document,view=synthesis_case(root,accepted=accepted)
  artifacts.store(root,'book',{'path':'development/parent-return.json','before':None,'content':json.dumps(document),'reason':'Exact retained synthesis consumer fixture.'},'WT-parent')
  from laplace.work.project_work_views import handle
  result['accepted' if accepted else 'rejected']={'synthesis':dispatch_parent.synthesis_view(task,'book',root,view=view),
   'dispatch_id':task['id'],'dispatch_read':handle('book',{'view':'detail','id':task['id']})}
  if accepted:
   judge=view['children'][-1]
   artifacts.resolve_path(root,'book',judge['return_path']).unlink()
   authoring_surface._bank(root,{'record':'writing-tool-failure','id':'FAIL-reviewer-publication',
    'project':'book','turn_id':judge['turn_id'],'operation':'store_artifact',
    'payload':{'path':judge['return_path'],'scope':'project'},
    'error':'store_artifact was not permitted in the recorded review session.'})
   detail=project_work.read('book',{'view':'detail','id':task['id']},root)
   result['no_return']={'detail':detail,'continuation':dispatch_parent.public(root,'book',
    {**current,'dispatch_id':task['id'],'phase':'READY'},task=task),
    'turn_summary':authoring_surface.session_turn_detail(root,'book',judge['turn_id'],'summary'),
    'turn_failures':authoring_surface.session_turn_detail(root,'book',judge['turn_id'],'failures')}
  fixture.close()
with tempfile.TemporaryDirectory(prefix='laplace-parent-reply-only-consumer-') as raw:
 fixture=make(Path(raw),monkey);root=next(fixture)
 with monkey.context() as scoped:
  original_bank=authoring_surface._bank
  def reported_reply(root,row):
   if row.get('id')=='WR-child-1':row={**row,'text':'I could not publish: store_artifact was advertised as unavailable in review.'}
   return original_bank(root,row)
  scoped.setattr(authoring_surface,'_bank',reported_reply)
  task,document,view=synthesis_case(root)
 judge=view['children'][-1]
 artifacts.resolve_path(root,'book',judge['return_path']).unlink()
 result['reply_only']={'detail':project_work.read('book',{'view':'detail','id':task['id']},root),
  'continuation':dispatch_parent.public(root,'book',{**current,'dispatch_id':task['id'],'phase':'READY'},task=task)}
 fixture.close()
with tempfile.TemporaryDirectory(prefix='laplace-retained-prepared-consumer-') as raw:
 fixture=make(Path(raw),monkey);root=next(fixture)
 result['retained_prepared']=retained_execution_case(root)
 fixture.close()
print(json.dumps(result))
monkey.undo()
`],{cwd:fileURLToPath(new URL('../..',import.meta.url)),encoding:'utf8',timeout:30000});
assert.equal(generated.status,0,generated.stderr);
export const parentWire=JSON.parse(generated.stdout);
