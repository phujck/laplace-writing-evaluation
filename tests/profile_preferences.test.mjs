import {test,beforeEach} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {webcrypto} from 'node:crypto';
import {mountProfilePreferences,profileActionPayload,readProfileText,profileGenerationIntent,profileGenerationURL,profileGenerationCoordinates} from '../src/laplace/web/static_shared/profile-preferences.mjs';
import {ownerHumanTarget,qualifiedOwnerHTTP} from '../src/laplace/web/static_shared/writing-owner-read.mjs';
const fixture=JSON.parse(await readFile(new URL('./fixtures/editor_spine/profile-candidates.json',import.meta.url),'utf8'));
const clone=value=>structuredClone(value);
class Node{
  constructor(tag='div'){this.tag=tag;this.children=[];this.attrs={};this._text='';this.value='';this.isConnected=true;this.hidden=false;this.disabled=false;this.style={};}
  set textContent(value){this._text=String(value??'');this.children=[];}get textContent(){return this._text+this.children.map(node=>node.textContent).join('');}
  append(...nodes){for(const node of nodes){node.parentElement=this;this.children.push(node);}}replaceChildren(...nodes){this._text='';this.children=[];this.append(...nodes);}
  get firstElementChild(){return this.children[0];}setAttribute(key,value){this.attrs[key]=value;}all(){return[this,...this.children.flatMap(node=>node.all())];}
  querySelectorAll(selector){const tags=selector.split(',');return this.all().filter(node=>tags.includes(node.tag));}
  remove(){if(this.parentElement)this.parentElement.children=this.parentElement.children.filter(node=>node!==this);this.isConnected=false;}
  async click(){if(!this.disabled)await this.onclick?.({preventDefault(){}});}
}
beforeEach(()=>{globalThis.document={createElement:tag=>new Node(tag)};if(!globalThis.crypto)Object.defineProperty(globalThis,'crypto',{value:webcrypto,configurable:true});});
const find=(root,text)=>root.all().find(node=>node.tag==='button'&&node.textContent===text);
function harness({conflict=false,failRefreshAfterApply=false}={}){
  const host=new Node(),posts=[],generated=[];let applied=false,changed=0,uncertain=false;
  async function request(path,payload){
    if(payload){posts.push(clone(payload));if(conflict){uncertain=true;throw Error('CHANGED_INPUT: concurrent profile preference.');}assert.deepEqual(payload,fixture.candidate.apply_action.payload);applied=true;return clone(fixture.applied);}
    const url=new URL(path,'http://local'),view=url.searchParams.get('view');
    if(view==='summary'){if(applied&&failRefreshAfterApply)throw Error('Injected effective-view read outage.');return clone(applied?fixture.after:url.searchParams.has('project')?fixture.before:fixture.global_summary);}
    if(view==='content')return clone(applied?fixture.effective:fixture.current);
    if(view==='candidates')return {candidates:[clone(fixture.candidate)],pagination:{returned:1,total:1}};
    if(view==='candidate'){
      const part=url.searchParams.get('part');if(part)return clone(fixture.parts[part]);
      const value=clone(applied?fixture.applied:fixture.candidate);if(uncertain){value.currentness='CHANGED_INPUT';value.apply_action.permitted=false;value.current.revision='sha256:'+'a'.repeat(64);}return value;
    }
    throw Error('Unexpected owner route '+path);
  }
  return {host,posts,generated,request,changed:()=>changed,onChanged:()=>{changed++;},onGenerate:value=>{generated.push(value);}};
}

test('owner action templates retain exact identity, nested guards and required authored fields',()=>{
  const action=fixture.before.propose_action;
  const value=profileActionPayload(action,{change:{content:'typed profile'},reason:'My preference'});
  assert.deepEqual(value.guards,action.payload.guards);assert.equal(value.scope,'workspace');
  assert.throws(()=>profileActionPayload(action,{guards:{},change:{},reason:'x'}),/cannot replace/);
  assert.throws(()=>profileActionPayload(action,{change:{}}),/reason/);
  assert.equal(Object.hasOwn(value,'expected_revision'),false);
  assert.throws(()=>profileActionPayload({...action,http:{method:'POST',url:'https://foreign.example/work/profiles/change'}},{change:{},reason:'x'}),/same-origin/);
  assert.throws(()=>profileActionPayload({...action,http:{method:'POST',url:'/authoring/turn'}},{change:{},reason:'x'}),/same-origin/);
});

test('exact profile text chunks join only within one immutable identity and complete hash',async()=>{
  const original=fixture.parts.proposed,raw=new TextEncoder().encode(original.content),cut=100;
  const first={...clone(original),content:new TextDecoder().decode(raw.slice(0,cut)),coverage:{...original.coverage,end:cut,complete:false},next_read:{http:{url:'/work/profiles?part=proposed'}}};
  const second={...clone(original),content:new TextDecoder().decode(raw.slice(cut)),coverage:{...original.coverage,start:cut,complete:false}};
  assert.equal(await readProfileText(first,async()=>second),original.content);
  await assert.rejects(readProfileText(first,async()=>({...second,candidate_ref:{...second.candidate_ref,version:'sha256:'+'0'.repeat(64)}})),/identity/);
  await assert.rejects(readProfileText({...clone(original),content:original.content.replace('Lead','Hide')},async()=>{}),/coverage|identity/);
});

test('actual owner candidate compares, applies and visibly reloads effective workspace values',async()=>{
  const h=harness();await mountProfilePreferences(h.host,{project:'book',family:'architecture',scope:'workspace',request:h.request,onChanged:h.onChanged,enableEdit:false});
  assert.match(h.host.textContent,/shared across the workspace/);
  await h.host.all().find(node=>node.tag==='button'&&node.title==='Compare before applying').click();assert.match(h.host.textContent,/Current preferences/);assert.match(h.host.textContent,/Lead with the concrete mechanism/);
  await find(h.host,'Apply this preference').click();assert.equal(h.posts.length,1);assert.equal(h.changed(),1);
  assert.match(h.host.textContent,/Preference applied/);assert.match(h.host.textContent,/Lead with the concrete mechanism/);
  assert.match(h.host.textContent,/Not personally confirmed/,'applying a preference must not acquire human confirmation');
  assert.match(h.host.textContent,/Every field guides whole-paper structure planning/);
  assert.match(h.host.textContent,/Section preference palette/);
});

test('uncertain or changed-input application retains exact candidate and requires inspection, never replay',async()=>{
  const h=harness({conflict:true});const control=await mountProfilePreferences(h.host,{project:'book',family:'architecture',request:h.request,enableEdit:false});
  await h.host.all().find(node=>node.tag==='button'&&node.title==='Compare before applying').click();await find(h.host,'Apply this preference').click();
  assert.equal(h.posts.length,1);assert.deepEqual(control.selectedCandidate.candidate_ref,fixture.candidate.candidate_ref);
  assert.equal(find(h.host,'Apply this preference'),undefined);await find(h.host,'Inspect saved outcome').click();
  assert.equal(h.posts.length,1);assert.equal(find(h.host,'Apply this preference'),undefined);assert.match(h.host.textContent,/original inputs have changed/);
});

test('a completed application with a refresh outage stays applied and does not offer replay',async()=>{
  const h=harness({failRefreshAfterApply:true});await mountProfilePreferences(h.host,{project:'book',family:'architecture',request:h.request,enableEdit:false});
  await h.host.all().find(node=>node.tag==='button'&&node.title==='Compare before applying').click();await find(h.host,'Apply this preference').click();
  assert.equal(h.posts.length,1);assert.match(h.host.textContent,/Preference applied, but/);
  assert.equal(find(h.host,'Apply this preference'),undefined);assert.ok(find(h.host,'Inspect applied preference'));
});

test('a structural preference draft survives stale proposal refusal with its original owner guard',async()=>{
  const h=harness({conflict:true});const control=await mountProfilePreferences(h.host,{project:'book',family:'architecture',request:h.request});
  await find(h.host,'Edit structural preferences').click();
  const summary=h.host.all().find(node=>node.attrs['aria-label']==='What to prefer');summary.value='Keep my authored structural draft.';
  const reason=h.host.all().find(node=>node.attrs['aria-label']==='Reason for this preference');reason.value='My explicit preference.';
  const form=h.host.all().find(node=>node.tag==='form');form.oninput();
  await find(h.host,'Preview my changes').click();assert.equal(h.posts.length,1);
  assert.deepEqual(h.posts[0].guards,fixture.before.propose_action.payload.guards);
  assert.equal(summary.value,'Keep my authored structural draft.');assert.equal(control.hasDraft,true);assert.equal(control.closeReady(),false);
  assert.match(h.host.textContent,/Save your draft as a suggestion or cancel/);
  await find(h.host,'Cancel local edit').click();assert.equal(control.hasDraft,false);
});

test('projectless generation asks for an explicit producing project and only prepares its actual session callback',async()=>{
  const h=harness();await mountProfilePreferences(h.host,{family:'architecture',request:h.request,onGenerate:h.onGenerate,getProjects:async()=>[{name:'book',title:'Fixture Book'}],enableEdit:false});
  await find(h.host,'Generate suggestion').click();assert.equal(h.generated.length,0);
  await find(h.host,'Use this project context').click();assert.equal(h.generated.length,0,'placeholder is not a hidden default project');
  const select=h.host.all().find(node=>node.tag==='select');select.value='book';await find(h.host,'Use this project context').click();
  assert.equal(h.generated.length,1);assert.equal(h.generated[0].project,'book');assert.match(h.generated[0].instruction,/profile_input_revision/);
  assert.match(h.generated[0].instruction,/do not apply it/);assert.equal(h.posts.length,0,'the component must not make a provider or profile mutation call');
});

test('profile Activity and model read handles preserve exact project, family and candidate identity',()=>{
  const handle=fixture.candidate.read_handle;
  const target=ownerHumanTarget(handle.http.url);
  assert.equal(target.kind,'profile');assert.equal(target.project,'book');
  assert.deepEqual(target.read_handle.payload.candidate_ref,fixture.candidate.candidate_ref);
  assert.ok(qualifiedOwnerHTTP(handle,'book'));
  assert.equal(qualifiedOwnerHTTP(handle,'other'),null);
  assert.equal(qualifiedOwnerHTTP({...handle,payload:{...handle.payload,candidate_ref:{...handle.payload.candidate_ref,version:'sha256:'+'0'.repeat(64)}}},'book'),null);
  for(const path of [handle.http.url+'&project=other',handle.http.url+'&family=architecture',handle.http.url.replace('/work/profiles?','/work/profiles/change?')])assert.equal(ownerHumanTarget(path),null);
});

test('global generation navigation carries typed coordinates and destination re-reads the owner',()=>{
  const intent=profileGenerationIntent('book',fixture.before);
  const url=new URL(profileGenerationURL(intent),'http://local');
  assert.equal(url.searchParams.get('corpus'),'book');
  assert.deepEqual(profileGenerationCoordinates(url.searchParams),{family:'architecture',scope:'workspace',view:'summary'});
  assert.equal(url.searchParams.has('instruction'),false,'no prompt or history is stored in the URL');
  assert.throws(()=>profileGenerationIntent('other',fixture.before),/actual project/);
  assert.throws(()=>profileGenerationCoordinates(new URLSearchParams('profile_generation=architecture&profile_scope=project')),/unsupported/);
  assert.throws(()=>profileGenerationCoordinates(new URLSearchParams('profile_generation=voice&profile_scope=workspace&profile_path=profiles/voice/../secret.md')),/invalid/);
  const voice={project:'book',family:'voice',scope:'workspace',profile:'profiles/voice/nested/résumé style.md'};
  assert.equal(profileGenerationCoordinates(new URL(profileGenerationURL(voice),'http://local').searchParams).profile,voice.profile);
});

test('absent architecture editor derives its starter from the inspected owner contract',async()=>{
  const h=harness();const absent=clone(fixture.absent),empty=clone(fixture.absent_content);
  absent.content_contract.starter={profile:{section_rhythm:{summary:''}}};
  const request=async(path,payload)=>{if(payload)return h.request(path,payload);const view=new URL(path,'http://local').searchParams.get('view');return view==='summary'?clone(absent):view==='content'?clone(empty):h.request(path,payload);};
  await mountProfilePreferences(h.host,{project:'book',family:'architecture',request});
  await find(h.host,'Write structural preferences').click();
  assert.equal(h.host.all().find(node=>node.attrs['aria-label']==='Preference name').value,'section_rhythm');
  assert.match(profileGenerationIntent('book',absent).instruction,/content_contract/);
  assert.equal(h.posts.length,0,'a starter is an authored draft, never an applied default');
});

// M5 C8: saved suggestions are relation rows with a standing chip; Compare is the door, Apply lives inside the comparison
test('saved suggestions render as relation rows with Compare as the only door',async()=>{
  const h=harness();await mountProfilePreferences(h.host,{project:'p',family:'architecture',scope:'workspace',request:h.request,onChanged:h.onChanged,onGenerate:h.onGenerate});
  const list=h.host.all().find(node=>node.attrs['data-control']==='profile:candidate');assert.ok(list,'the candidate list is declared');
  const doors=list.all().filter(node=>node.tag==='button');assert.equal(doors.length,1);assert.equal(doors[0].title,'Compare before applying');
  assert.equal(find(h.host,'Apply this preference'),undefined,'Apply appears only inside a comparison');
  await doors[0].click();assert.ok(find(h.host,'Apply this preference'));
});
