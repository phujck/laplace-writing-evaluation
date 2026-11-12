// Executes the real Work selection owner (workspace-work-view.mjs, M5 S2 F1) and the real Work controller, with
// the conversation's changed callback (workspace-conversation.mjs) over them: not a second policy. The owner's
// own functions are run unchanged; they receive the same named services the shell gives mountWorkView.
import {readFile} from 'node:fs/promises';
import {installDOM,Node} from './evidence_reader_harness.mjs';
import {savedActionSourceEffect} from '../../src/laplace/web/static_shared/source-effect.mjs';
import {savedActionPlanPublication} from '../../src/laplace/web/static_shared/plan-publication.mjs';
import {mountOperatorWork} from '../../src/laplace/web/static_shared/workspace-work.mjs';
const workView=await readFile(new URL('../../src/laplace/web/static_shared/workspace-work-view.mjs',import.meta.url),'utf8');
const conversation=await readFile(new URL('../../src/laplace/web/static_shared/workspace-conversation.mjs',import.meta.url),'utf8');
// the owner's functions: everything after its own memory, up to the Work view's render
const ownerStart=workView.indexOf(';\n',workView.indexOf("  // the domain's own memory"))+2;
const callbacks=workView.slice(ownerStart,workView.indexOf('  async function renderWork('));
const mountStart=workView.indexOf('    const controller=await mountOperatorWork',workView.indexOf('  async function renderWork('));
const mountCall=workView.slice(mountStart,workView.indexOf('    if(!host.isConnected)',mountStart));
const changeStart=conversation.indexOf('onChanged:async');
const changedCallback=conversation.slice(changeStart+'onChanged:'.length,conversation.indexOf('},onInspect:',changeStart)+1);
export const workDetail=(project,id,status='open')=>({project,view:'detail',task:{id,title:id,status,goal:'Authored '+id,work_scope_revision:'sha256:'+'1'.repeat(64),dependency_revision:'sha256:'+'2'.repeat(64)},read_cut:{revision:'cut-'+id+'-'+status},blockers:[],children:{items:[]},dependants:{items:[]},allowed_actions:{task_status:{permitted:true,statuses:['done'],payload:{id,expected_work_scope_revision:'original-'+id,expected_dependency_revision:'deps-'+id},http:{method:'POST',url:'/work/transition'}}}});
export async function workSelectionFixture({project='fixture',initial='B',explicit=true,session=null,startup=Promise.resolve(true)}={}){
 const dom=installDOM(),oldLocation=globalThis.location,oldHistory=globalThis.history,root=new Node('main'),fields=new Map(),calls=[],notices=[];
 dom.body.append(root);for(const key of ['[data-clear-task]','[data-work-scope]']){const n=new Node('div');root.append(n);fields.set(key,n);}
 globalThis.location={href:'http://local/project?'+new URLSearchParams({workspace:'writing',corpus:project,view:'work',...(explicit?{work:initial||''}:{})})};globalThis.history={replaceState:(_state,_title,url)=>{globalThis.location.href=String(url);}};
 const rows=new Map(['A','B','C'].map(id=>[id,workDetail(project,id)]));let read=url=>structuredClone(rows.get(new URL(url,'http://local').searchParams.get('id')));
 const api=async url=>{calls.push(url);return read(url);},scopeSession=session||{session:'S',origin:{turnId:'T',workId:initial||'A'},scope(){}};
 const key='__workOwner'+Math.random().toString(36).slice(2);
 globalThis[key]={savedActionSourceEffect,savedActionPlanPublication,mountOperatorWork,project,root,$:key=>fields.get(key),api,session:scopeSession,notice:(...args)=>notices.push(args),state:{tasks:[...rows.values()].map(v=>v.task)},task:initial?rows.get(initial).task:null,explicit,startup};
 const code=`const {savedActionSourceEffect,savedActionPlanPublication,mountOperatorWork,project,root,$,api,session:scopeSession,notice,state:initialState,startup:workStartup}=globalThis[${JSON.stringify(key)}];
 const enc=encodeURIComponent(project),initialQuery=new URL(location.href).searchParams;
 let task=globalThis[${JSON.stringify(key)}].task,explicitWorkIntent=globalThis[${JSON.stringify(key)}].explicit,workIntentRevision=0,workRefreshRevision=0,workController=null,workMemory={},requestedWork=null,workChoices=null,workChoicesLoading=null;
 let currentView='work',loadVersion=1,dirty=false,state=initialState,structure=null;
 const views={current:()=>currentView,show:async()=>true,generation:()=>loadVersion,info:()=>({})};
 const forms={dirty:()=>dirty,setDirty:value=>{dirty=value;},leave:()=>true,guard:fn=>fn,wire:()=>{},changed:async()=>{}};
 const ui={notice,$,root,button:(label,fn)=>{const b=document.createElement('button');b.textContent=label;b.onclick=fn;return b;},actionAlert:()=>{},main:()=>root};
 const workState={get:()=>state,set:value=>{state=value;},summaryRead:'/work/state?project='+enc+'&view=summary&limit=12'};
 const structures={get:()=>structure,set:value=>{structure=value;}};
 const inspect={projectArtifact:()=>{},ownerRead:()=>{},savedMarkdown:()=>{}};
 const discussion={session:()=>scopeSession,talk:()=>{},open:()=>{},conversation:()=>{},savedTurn:()=>{},generateProfile:()=>{}};
 const activity={openOwner:()=>{}},place={remember:()=>{}},context=()=>({surface:'project'}),settingsTruthText=()=>'';
 const home={refreshOverview:()=>{},refreshHome:async()=>{},refreshStyle:async()=>{},refreshMetadata:async()=>{}};
 const manuscript={editor:()=>null,updates:{invalidate:async()=>{}}};
 ${callbacks}
 const work={select:selectWork,request:requestWorkSelection,refresh:refreshSelectedWork,reload:reloadState,open:openWork,admit:admitRequestedWork,task:()=>task,requested:()=>requestedWork};
 export const runChanged=${changedCallback};
 export async function remount(host){${mountCall};workController=controller;return controller;}
 export {selectWork,requestWorkSelection,refreshSelectedWork,openWork,admitRequestedWork};
 export const requested=()=>requestedWork&&{...requestedWork};export const currentTask=()=>task;export const isExplicit=()=>explicitWorkIntent;
 export const setController=value=>workController=value;export const changeView=()=>++loadVersion;`;
 const owner=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'));delete globalThis[key];
 const host=new Node('section');root.append(host);
 const controller=await mountOperatorWork(host,{project,summary:{tasks:[...rows.values()].map(v=>v.task)},initialWork:initial,initialDetail:initial?structuredClone(rows.get(initial)):null,request:api,onSelect:owner.selectWork,onRequest:id=>owner.requestWorkSelection(id)});
 owner.setController(controller);
 return {dom,root,host,owner,controller,calls,notices,fields,rows,setRead:fn=>{read=fn;},readDefault:url=>structuredClone(rows.get(new URL(url,'http://local').searchParams.get('id'))),restore(){controller.destroy();dom.restore();globalThis.location=oldLocation;globalThis.history=oldHistory;}};
}


// Real guarded Work producers/projection, isolated tiny roots. No JS dependency calculation.
export async function actualWorkEffectCases(){
 const {spawnSync}=await import('node:child_process'),{fileURLToPath}=await import('node:url');
 const result=spawnSync('./scripts/laplace-python',['-c',String.raw`
import json,runpy,tempfile
from pathlib import Path
h=runpy.run_path('tests/test_project_work_views.py')
make,detail,move=h['make'],h['detail'],h['move']
out={}
with tempfile.TemporaryDirectory(prefix='laplace-work-effect-owner-') as raw:
 base=Path(raw)
 for case in ('direct','prerequisite','evidence'):
  root=base/case;root.mkdir()
  if case=='prerequisite':make(root,'A');make(root,'B',depends_on=['A'])
  else:make(root,'B')
  (root/'result').write_text('original result')
  if case=='evidence':move(root,'B','done',evidence=['result'])
  before=detail(root,'B')
  if case=='direct':move(root,'B','done',evidence=['result'])
  elif case=='prerequisite':move(root,'A','done',evidence=['result'])
  else:(root/'result').write_text('changed result')
  out[case]={'before':before,'after':detail(root,'B')}
 print(json.dumps(out))
`],{cwd:fileURLToPath(new URL('../..',import.meta.url)),encoding:'utf8',timeout:30000});
 if(result.status!==0)throw Error(result.stderr||'Actual Work owner fixture refused');return JSON.parse(result.stdout);
}
