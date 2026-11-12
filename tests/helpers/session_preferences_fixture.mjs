// Production conversation/inspector with a deterministic typed owner transport seam.
// This is controller coverage; real HTTP/owner/custody evidence is separate.
import {webcrypto,createHash}from'node:crypto';
import {installHTMLDocument}from'./html_dom.mjs';
import {WorkspaceSession}from'../../src/laplace/web/static_shared/workspace-session.mjs';
const canonical=v=>JSON.stringify(v,(_k,x)=>x&&typeof x==='object'&&!Array.isArray(x)?Object.fromEntries(Object.keys(x).sort().map(k=>[k,x[k]])):x),pin=v=>'sha256:'+createHash('sha256').update(canonical(v)).digest('hex');
export async function pilotSessionFixture({initialSession='existing',width=1280,change=null,read:readGate=null}={}){
 const env=installHTMLDocument({width}),host=document.createElement('main');document.body.append(host);if(!globalThis.crypto)Object.defineProperty(globalThis,'crypto',{configurable:true,value:webcrypto});
 const target={kind:'conversation',session_id:'existing'},defaultTarget=target,calls=[],history=new Map();let values={provider:'codex',model:'model',effort:'medium'},revision=0,requestNumber=0;
 const door=t=>t?.kind==='project-defaults'?'/work/session-preferences':'/authoring/session-settings';
 const read=(action='read',id,t=target)=>({http:{method:'GET',url:door(t)+'?'+new URLSearchParams({project:'book',request:JSON.stringify({action,target:t,...id?{request_id:id}:{}})})}});
 const providers=['codex','claude'].map(id=>({id,name:id,available:true,models:['model','different-model','gpt-6-luna','public-small'].map(id=>({id,name:id,supports_effort:id!=='public-small',efforts:id==='public-small'?[]:['low','medium','high']}))}));
 const session=()=>({id:'existing',project:'book',role:'author',...values,settings_revision:revision});
 // a read or save names its own target (a conversation or the project's defaults); the view answers for that target
 const view=(target=defaultTarget)=>{const request_id='settings-'+(++requestNumber),basis=pin({values,revision});return {schema_version:'laplace.session-settings/1',project:'book',target,title:'Public conversation',basis,settings_revision:revision,effective:{...values},settings:Object.fromEntries(Object.entries(values).map(([k,value])=>[k,{value,origin:'recorded-value',provenance:null,meaning:'Recorded public fixture value.'}])),authority:{session_role:'author',description:'Recorded role',conditional:'Owner validation remains required.',latest_admitted:null},providers,read:read('read',undefined,target),actions:{change:{permitted:true,http:{method:'POST',url:door(target),payload:{project:'book',action:'change',target,request_id,expected_basis:basis,values:{...values}}},intent_projection:{algorithm:'sha256-canonical-json-utf8',excluded_fields:['action','request_id']},request_read:read('request',request_id,target),withdraw:{http:{method:'POST',url:door(target),payload:{project:'book',action:'withdraw',target,request_id}},required_inputs:['intent_digest','original_request']}}}};};
 const json=(value,status=200)=>new Response(JSON.stringify(value),{status,headers:{'content-type':'application/json'}});
 globalThis.fetch=async(path,options)=>{const payload=options?.body?JSON.parse(options.body):null,row={path,payload,method:options?.method||'GET'};calls.push(row);const url=new URL(path,'http://local');
  if(url.pathname==='/authoring/providers')return json({providers,cached:true,model_choice:{}});
  if(url.pathname==='/work/session-preferences'&&!url.searchParams.has('request')&&!payload?.action)return json({preferences:{...values},settings_read:read('read',undefined,{kind:'project-defaults'})});
  if(url.pathname==='/authoring/state')return json({sessions:[session()],session_count:1});
  if(url.pathname==='/work/state')return json({tasks:[]});
  if(url.pathname==='/authoring/session')return json({session:session(),turns:[],active:null,settings_read:read()});
  if(url.pathname==='/authoring/session-settings'||url.pathname==='/work/session-preferences'){
   if(!payload){const query=JSON.parse(url.searchParams.get('request'));if(query.action==='read'&&readGate){const intercepted=await readGate(query,{value:view()});if(intercepted!==undefined)return json(intercepted);}return json(query.action==='read'?view(query.target):history.get(query.request_id)||{schema_version:'laplace.session-settings-request/1',project:'book',target:query.target,request_id:query.request_id,effect:'NONE',terminal:false});}
   if(change){const intercepted=await change(payload,{calls,view});if(intercepted!==undefined)return intercepted;}
   values={...values,...payload.values};revision++;const result={schema_version:'laplace.session-settings-request/1',project:'book',target:payload.target,request_id:payload.request_id,effect:'RECORDED',terminal:true,intent_digest:pin(Object.fromEntries(Object.entries(payload).filter(([k])=>!['action','request_id'].includes(k)))),original_request:payload,receipt:{values:{...values},settings_revision:revision},current:view(payload.target),current_read:read('read',undefined,payload.target)};history.set(payload.request_id,result);return json(result);
  }
  throw Error('Unexpected controller-fixture request '+path);
 };
 const current=new WorkspaceSession(host,{project:'book',initialSession,getContext:()=>({surface:'project',label:'Public reading'})});await current.ready;const guards=[],guard=current.guard.bind(current);current.guard=(...args)=>{const p=guard(...args);guards.push(p);return p;};
 const button=label=>host.querySelectorAll('button').find(n=>n.textContent===label);
 return {current,host,calls,guards,button,async open(){current.find('[data-settings-open]').onclick();await guards.at(-1);},close(){current.destroy();env.restore();},json};
}
