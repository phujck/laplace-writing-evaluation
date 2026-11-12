// M5 C2/C3: the shell's top bar, navigation layouts, entry aliases and rules, failure
// channel, place memo, bridge ledger, book-outline retirement, help verification per
// mount, the design tokens and the one read inspector. Behavioural tests slice the
// actual shell/walk functions by string boundaries into doubles, as the other shell
// tests do, and drive the REAL reading doors (writing-artifact, workspace-material)
// through the shared inspector; source pins name the retirements with every consumer.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createInspector,payloadCut,sharedInspector,resetSharedInspector,utf8Bytes,INSPECTOR_CACHE_LIMIT,INSPECTOR_SNAPSHOT_BYTES} from '../src/laplace/web/static_shared/workspace-inspector.mjs';
import {openArtifact} from '../src/laplace/web/static_shared/writing-artifact.mjs';
import {openSavedTurn} from '../src/laplace/web/static_shared/workspace-material.mjs';
import {walkSource} from './helpers/walk_source.mjs';
import {operatorHTTP} from '../src/laplace/web/static_shared/workspace-work.mjs';
import * as harness from './helpers/evidence_reader_harness.mjs';

const read=async rel=>readFile(new URL(rel,import.meta.url),'utf8');
// the shell's text: the mount facade and its domain controllers (workspace-*.mjs, M5 S2 F1/F2)
const shell=(await import('./helpers/workspace_source.mjs')).workspaceSource();
// the same text with the line breaker's continuations joined, for pins on one original line
const flat=shell.replace(/\n\s*/g,'');
const walk=walkSource();
const panel=await read('../src/laplace/web/static_shared/writing-panel.mjs');
const bridgeSource=await read('../src/laplace/web/static_shared/workspace-bridge.mjs');
const css=await read('../src/laplace/web/static_shared/workspace.css');
const pdfSource=await read('../src/laplace/web/static_shared/writing-pdf.mjs');
const artifactSource=await read('../src/laplace/web/static_shared/writing-artifact.mjs');
const materialSource=await read('../src/laplace/web/static_shared/workspace-material.mjs');
// workspace.mjs imports /shared/ modules the node resolver cannot reach; its pure exports are sliced
// the bridge ledger's owner is workspace-bridge.mjs (M5 readability P2); the shell re-exports it
import {createBridgeLedger,UNKNOWN_PRODUCER_MESSAGES,HANDLED_BRIDGE_MESSAGES,UNKNOWN_SAMPLE_LIMIT,messageBytes} from '../src/laplace/web/static_shared/workspace-bridge.mjs';
import {SERVICE_PRELUDE} from './helpers/shell_services.mjs';
const facadeText=await read('../src/laplace/web/static_shared/workspace.mjs'),chromeText=await read('../src/laplace/web/static_shared/workspace-chrome.mjs');
const {canonicalWorkspaceView,navLayout,NAV_LABELS,NAV_CLOSED_KEY,SESSION_OPEN_KEY}=await import('data:text/javascript;base64,'+Buffer.from(
 facadeText.slice(facadeText.indexOf('export function canonicalWorkspaceView'),facadeText.indexOf('export async function mountWorkspace'))
 +chromeText.slice(chromeText.indexOf('export const NAV_LABELS'),chromeText.indexOf('export function mountChrome'))).toString('base64'));
const slice=(source,start,end)=>{const a=source.indexOf(start),b=source.indexOf(end,a+start.length);assert.ok(a>=0&&b>a,'slice boundaries exist: '+start.slice(0,40));return source.slice(a,b);};
const evaluate=async(code,exports)=>import('data:text/javascript;base64,'+Buffer.from(code+'\nexport {'+exports.join(',')+'};').toString('base64'));

class El{
  constructor(tag='div'){this.tag=tag;this.children=[];this.attrs={};this.dataset={};this.className='';this._text='';this.hidden=false;this.disabled=false;this.isConnected=true;this.open=false;this.scrollTop=0;this.scrollLeft=0;this.parentElement=null;this.listeners={};this.focused=0;this.closed=0;this.selected=false;
    const self=this;this.classList={add(...v){for(const c of v)if(!self.className.split(' ').includes(c))self.className=(self.className+' '+c).trim();},remove(...v){self.className=self.className.split(' ').filter(c=>!v.includes(c)).join(' ');},contains(c){return self.className.split(' ').includes(c);},toggle(c,force){const has=self.classList.contains(c);const want=force===undefined?!has:!!force;if(want&&!has)self.classList.add(c);if(!want&&has)self.classList.remove(c);return want;}};}
  set textContent(v){this._text=String(v??'');this.children=[];}get textContent(){return this._text+this.children.map(c=>c.textContent).join('');}
  append(...nodes){for(const n of nodes){n.parentElement=this;this.children.push(n);}}prepend(...nodes){for(const n of nodes.reverse()){n.parentElement=this;this.children.unshift(n);}}
  after(node){const p=this.parentElement;p.children.splice(p.children.indexOf(this)+1,0,node);node.parentElement=p;}before(node){const p=this.parentElement;p.children.splice(p.children.indexOf(this),0,node);node.parentElement=p;}
  remove(){const p=this.parentElement;if(p)p.children.splice(p.children.indexOf(this),1);this.isConnected=false;}
  replaceChildren(...nodes){this.children=[];this._text='';this.append(...nodes);}
  get nextElementSibling(){const p=this.parentElement;if(!p)return null;return p.children[p.children.indexOf(this)+1]||null;}
  get options(){return this.children.filter(c=>c.tag==='option');}get selectedOptions(){return this.options.filter(o=>o.selected);}
  get value(){if(this.tag==='select'){const chosen=this.options.find(o=>o.selected);return chosen?chosen._value??'':'';}return this._value??'';}
  set value(v){if(this.tag==='select'){let hit=false;for(const o of this.options){o.selected=!hit&&(o._value===String(v));if(o.selected)hit=true;}if(!hit)for(const o of this.options)o.selected=false;}else this._value=String(v);}
  setAttribute(k,v){this.attrs[k]=String(v);}getAttribute(k){return this.attrs[k]??null;}removeAttribute(k){delete this.attrs[k];}
  all(){return [this,...this.children.flatMap(c=>c.all())];}
  querySelector(sel){return this.all().slice(1).find(n=>matches(n,sel))||null;}querySelectorAll(sel){return this.all().slice(1).filter(n=>matches(n,sel));}
  addEventListener(name,fn){(this.listeners[name]||(this.listeners[name]=new Set())).add(fn);}removeEventListener(name,fn){this.listeners[name]?.delete(fn);}
  dispatch(name){for(const fn of [...(this.listeners[name]||[])])fn({target:this});if(typeof this['on'+name]==='function')this['on'+name]({target:this});}
  focus(){this.focused++;}
  showModal(){this.open=true;}close(){if(!this.open&&this.tag==='dialog'&&this.closed)return;this.open=false;this.closed++;this.dispatch('close');}
}
Object.defineProperty(El.prototype,'_value',{writable:true,value:undefined});
function matches(n,sel){
  if(sel==='dialog[open]')return n.tag==='dialog'&&n.open;
  if(sel.includes(' ')){const [a,b]=sel.split(' ');let p=n.parentElement;while(p){if(matches(p,a))return matches(n,b);p=p.parentElement;}return false;}
  if(sel.startsWith('.'))return n.classList.contains(sel.slice(1));
  if(sel.startsWith('[')){const m=sel.match(/^\[([a-z-]+)(?:="([^"]*)")?\]$/);if(!m)return false;const attr=m[1];const key=attr.startsWith('data-')?attr.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase()):null;const value=key!=null?n.dataset[key]:n.attrs[attr];return m[2]===undefined?value!==undefined:value===m[2];}
  return n.tag===sel;
}
const page=()=>{const body=new El('body');const doc={body,activeElement:body,createElement:tag=>new El(tag),querySelectorAll:sel=>body.querySelectorAll(sel)};return doc;};
const E=(tag,text='',cls='')=>{const n=new El(tag);n.textContent=text;n.className=cls;return n;};

// ─ navigation layouts, labels and aliases ─────────────────────────────────────────────────
test('the navigation has three layouts by width, short labels for the compact one, and no Dependencies or Conversations entry',()=>{
  assert.equal(navLayout(1280),'fixed');assert.equal(navLayout(1051),'fixed');assert.equal(navLayout(1050),'compact');assert.equal(navLayout(720),'compact');assert.equal(navLayout(719),'drawer');
  assert.deepEqual(NAV_LABELS.map(([id])=>id),['overview','work','material','history','settings','argument','reader-plan','research','manuscript','review','presentation']);
  assert.deepEqual(NAV_LABELS.map(([,,short])=>short),['Home','Work','Material','Activity','Settings','Argument','Plan','Research','Manuscript','Review','Output']);
  assert.equal(canonicalWorkspaceView('dependencies'),'material','view=dependencies is Material at its shared bindings');
  assert.equal(canonicalWorkspaceView('turns'),'turns','turns stays a routing word that show() resolves to the conversation library');
  assert.equal(canonicalWorkspaceView('structure','plan'),'reader-plan');
  assert.equal(NAV_CLOSED_KEY,'laplace:workspace:nav-closed');assert.equal(SESSION_OPEN_KEY,'laplace:workspace:session-open');
});

test('applyNavLayout: fixed shows the nav and hides Menu, compact honours the preference with short labels, drawer closes the nav without persisting',async()=>{
  const code=slice(shell,'  function applyNavLayout(){',"  ui.$('[data-focus]').onclick=focusManuscript;");   // the chrome owner (M5 S2 F1)
  const nav=new El('nav');nav.className='workspace-nav';const root=new El('div');root.className='workspace';const menu=new El('button');menu.dataset.nav='';root.append(menu,nav);
  for(const [id,label,short] of NAV_LABELS){const b=new El('button');b.dataset.view=id;b.dataset.label=label;b.dataset.short=short;b.textContent=label;nav.append(b);}
  const stored=new Map();globalThis.localStorage={getItem:k=>stored.get(k)??null,setItem:(k,v)=>stored.set(k,String(v))};
  const run=async width=>{globalThis.innerWidth=width;const {applyNavLayout}=await evaluate(`const root=globalThis.__navRoot,$=s=>root.querySelector(s),navLayout=${navLayout.toString()},NAV_CLOSED_KEY='laplace:workspace:nav-closed',ui={$,root};let focusRestore=null;${code}`,['applyNavLayout']);applyNavLayout();};
  globalThis.__navRoot=root;
  try{
    stored.set('laplace:workspace:nav-closed','true');
    await run(1280);assert.equal(root.dataset.navLayout,'fixed');assert.equal(menu.hidden,true);assert.equal(root.classList.contains('nav-closed'),false,'the preference applies only below 1050');assert.equal(nav.children[6].textContent,'Reader plan');
    await run(1000);assert.equal(root.dataset.navLayout,'compact');assert.equal(menu.hidden,false);assert.equal(root.classList.contains('nav-closed'),true,'the compact nav honours the saved preference');assert.equal(nav.children[6].textContent,'Plan');assert.equal(nav.children[10].textContent,'Output');assert.equal(menu.attrs['aria-expanded'],'false');
    stored.set('laplace:workspace:nav-closed','false');await run(1000);assert.equal(root.classList.contains('nav-closed'),false);assert.equal(menu.attrs['aria-expanded'],'true');
    await run(600);assert.equal(root.dataset.navLayout,'drawer');assert.equal(root.classList.contains('nav-closed'),true,'the drawer starts closed');assert.equal(stored.get('laplace:workspace:nav-closed'),'false','the drawer never writes the preference');assert.equal(nav.children[6].textContent,'Reader plan');
  }finally{delete globalThis.__navRoot;delete globalThis.localStorage;delete globalThis.innerWidth;}
});

// ─ the failure channel ────────────────────────────────────────────────────────────────────
test('a control says its failure beside itself and the notice row is untouched; the next attempt replaces the alert',async()=>{
  const code=slice(shell,'  const actionAlert=','\n  return {$,notice');   // the notices owner (M5 S2 F1)
  const notices=[];globalThis.__failure={E,notice:(t,e)=>notices.push([t,e])};
  try{const {button}=await evaluate(`const {E,notice}=globalThis.__failure;${code}`,['button','actionAlert']);
    const host=new El('section');let fail=true;const b=button('Save framing',async()=>{if(fail)throw Error('Revision conflict: the framing changed.');});host.append(b);
    await b.onclick({preventDefault(){}});
    assert.equal(host.children.length,2);assert.equal(host.children[1].textContent,'Revision conflict: the framing changed.');assert.equal(host.children[1].attrs.role,'alert');assert.ok('actionAlert' in host.children[1].dataset);assert.equal(b.disabled,false);assert.deepEqual(notices,[],'the notice row is for view-load failures');
    await b.onclick({preventDefault(){}});assert.equal(host.children.length,2,'a repeated failure replaces the alert instead of stacking');
    fail=false;await b.onclick({preventDefault(){}});assert.equal(host.children.length,1,'a success clears the previous alert');
    const detached=button('Detached',async()=>{throw Error('gone');});detached.isConnected=false;await detached.onclick();assert.deepEqual(notices,[['gone',true]],'a control no longer in the page falls back to the notice');
  }finally{delete globalThis.__failure;}
});

// ─ help declarations verified once per mount ──────────────────────────────────────────────
test('help declarations are verified against the owner once per workspace mount and never from a stored string (Sol HELP-CACHE)',async()=>{
  const code=slice(shell,'  let helpAreasVerified=null;','  // THE HELP DOOR (C10)');
  const mount=async(version)=>{const calls=[];globalThis.__help={api:async path=>{calls.push(path);return {help:{schema_version:'laplace.help-areas/1',version,areas:[],controls:[],journeys:[]}};}};const mod=await evaluate(`const project='book',api=globalThis.__help.api;${code}\n// ${version}-${calls.length}-${Math.random()}`,['helpAreas']);return {calls,helpAreas:mod.helpAreas};};
  try{
    const first=await mount('sha256:v1');const a=await first.helpAreas(),b=await first.helpAreas();assert.equal(first.calls.length,1,'one owner read per mount');assert.equal(a,b);assert.match(first.calls[0],/\/authoring\/help\?project=book&view=areas/);
    const second=await mount('sha256:v2');assert.equal((await second.helpAreas()).version,'sha256:v2','a new mount sees the new server declaration');assert.equal(second.calls.length,1);
    globalThis.__help={api:async()=>({help:{schema_version:'laplace.help-areas/1'}})};const broken=await evaluate(`const project='book',api=globalThis.__help.api;${code}\n// broken`,['helpAreas']);await assert.rejects(broken.helpAreas(),/incompatible/);
    assert.ok(!shell.includes("'laplace:help:'"),'no stored help string survives in the shell');assert.ok(!/sessionStorage\.(get|set)Item\(\s*'laplace:help/.test(shell));
  }finally{delete globalThis.__help;}
});

// ─ the bridge ledger and the walk's place message ─────────────────────────────────────────
test('the bridge ledger has declared counters, bounded unknown samples with overflow, place bytes, and the three unknown-producer counters',()=>{
  const ledger=createBridgeLedger();
  assert.deepEqual(Object.keys(ledger.ledger.messages),HANDLED_BRIDGE_MESSAGES);assert.ok(HANDLED_BRIDGE_MESSAGES.length>=19);
  for(const type of ['laplace:place','laplace:place','laplace:source-saved','laplace:focus-manuscript'])ledger.count(type,type==='laplace:place'?430:0);ledger.reject();
  assert.equal(ledger.ledger.messages['laplace:place'],2);assert.equal(ledger.ledger.messages['laplace:source-saved'],1);assert.equal(ledger.ledger.place,2);assert.equal(ledger.ledger.rejected,1);assert.deepEqual(ledger.ledger.place_bytes,{last:430,max:430});
  assert.deepEqual(ledger.ledger.unknown_producer,{'laplace:focus-manuscript':1,'laplace:show-sections':0,'laplace:read-origin-turn':0});
  for(let n=0;n<1000;n++)ledger.count('laplace:unknown-'+n);ledger.count(undefined);ledger.count({});
  assert.equal(Object.keys(ledger.ledger.messages).length,HANDLED_BRIDGE_MESSAGES.length,'no undeclared key is ever added');
  assert.equal(ledger.ledger.unknown.count,1002);assert.equal(ledger.ledger.unknown.samples.length,UNKNOWN_SAMPLE_LIMIT);assert.equal(ledger.ledger.unknown.overflow,1002-UNKNOWN_SAMPLE_LIMIT);
  assert.equal(messageBytes({type:'laplace:place',place:{a:1}}),JSON.stringify({type:'laplace:place',place:{a:1}}).length);
  assert.deepEqual(UNKNOWN_PRODUCER_MESSAGES,['laplace:focus-manuscript','laplace:show-sections','laplace:read-origin-turn']);
  // the route table (workspace-bridge.mjs) still routes each to a shell handler (workspace_bridge.test.mjs checks the handlers)
  for(const type of UNKNOWN_PRODUCER_MESSAGES){assert.ok(bridgeSource.includes("'"+type+"'"),type+' is still routed');for(const source of [walk,panel])assert.ok(!source.includes("postMessage({type:'"+type+"'"),'no producer of '+type);}
  assert.ok(walk.includes('THE BRIDGE CONTRACT')&&panel.includes('THE BRIDGE CONTRACT'));for(const letter of ['A ','B ','C ','D ','E ','F ','G '])assert.ok(walk.includes('//   '+letter),'walk header carries '+letter);
  assert.ok(walk.includes("emit('source-change-saved'")&&!/\.on\(\s*['"]source-change-saved['"]/.test(walk+panel+shell),'source-change-saved is emitted, unsubscribed and counted in emitted()');
});

test('the embedded walk posts place COORDINATES with the opaque owner revision, debounced with a max wait, never the document model, and skips unchanged places',async()=>{
  const code=slice(walk,'const PLACE_DEBOUNCE_MS = 100','api.placeStats = () =>')+slice(walk,'api.placeStats = () =>','\n});')+'\n});';
  const posts=[];const blocks=[{id:'b1',sectionId:'s1',src:{file:'chapters/03-identity-and-authority.tex',line_start:4,line_end:9}},{id:'b2',sectionId:'s1',src:{file:'chapters/03-identity-and-authority.tex',line_start:10,line_end:14}},{id:'b3',sectionId:'s2',src:{file:'chapters/04.tex',line_start:1,line_end:3}}];
  const revision='sha256:'+'f'.repeat(64);let position={sectionId:'s1',blockId:'b2',label:'§3 Identity and authority of a source read'};
  globalThis.__place={posts,blocks,root:{classList:{contains:c=>c==='writing-embedded'}},revision,get position(){return position;}};
  const setup=`const {posts,blocks,root}=globalThis.__place;const listeners={};const api={on:(n,f)=>{(listeners[n]||(listeners[n]=new Set())).add(f);},readingPosition:()=>globalThis.__place.position,sourceObservation:()=>({current_revision:globalThis.__place.revision}),documentVersion:()=>({huge:'x'.repeat(800000)})};const blockById=new Map(blocks.map(b=>[b.id,b]));const S={blocks};function srcOf(b){const s=(b&&b.src)||{};return {file:s.file||'',lineStart:Number(s.line_start||0),lineEnd:Number(s.line_end||s.line_start||0)};}const window={parent:{postMessage:(m,o)=>posts.push([m,o])}};const location={origin:'http://local'};`;
  try{const {api,listeners,placePayload}=await evaluate(setup+code+'\nconst _api=api,_listeners=listeners;export {_api as api,_listeners as listeners,placePayload};',[]);
    const payload=placePayload();
    assert.deepEqual(payload,{sectionId:'s1',blockId:'b2',label:'§3 Identity and authority of a source read',revision,selection:{files:['chapters/03-identity-and-authority.tex'],section_ids:['s1'],line_start:4,line_end:14}});
    assert.ok(!('documentVersion' in payload),'the document model never crosses the bridge');
    const bytes=new TextEncoder().encode(JSON.stringify({type:'laplace:place',place:payload})).length;assert.ok(bytes<1024,'a place message is a few hundred bytes: '+bytes);
    assert.deepEqual(Object.keys(listeners).sort(),['attention','document','edit-settled','section']);
    const fire=name=>{for(const fn of listeners[name])fn({});};
    fire('section');fire('attention');fire('edit-settled');assert.equal(posts.length,0,'debounced');await new Promise(r=>setTimeout(r,160));
    assert.equal(posts.length,1,'one post per settled burst');assert.equal(posts[0][0].type,'laplace:place');assert.equal(posts[0][1],'http://local');assert.equal(api.placeStats().last_bytes,bytes);
    fire('attention');await new Promise(r=>setTimeout(r,160));assert.equal(posts.length,1,'an unchanged place is not re-posted');assert.equal(api.placeStats().suppressed,1);
    position={sectionId:'s2',blockId:'b3',label:'§4'};const started=Date.now();const burst=setInterval(()=>fire('attention'),20);await new Promise(r=>setTimeout(r,700));clearInterval(burst);
    assert.equal(posts.length,2,'a continuous burst still yields one post within the max wait');assert.ok(Date.now()-started>=500);await new Promise(r=>setTimeout(r,160));assert.equal(posts.length,2,'the trailing flush after the burst found the place unchanged');
    const stats=api.placeStats();assert.equal(stats.sent,2);assert.ok(stats.suppressed>=2,'unchanged flushes are counted, not posted');assert.equal(stats.debounce_ms,100);assert.equal(stats.max_wait_ms,500);assert.ok(stats.last_bytes>0&&stats.last_bytes<1024);
    assert.ok(!slice(walk,'function placePayload()','const placeBridge').includes('D.documentVersion'),'placePayload does not read the document model');assert.ok(walk.includes('documentVersion:()=>D.documentVersion'),'the local documentVersion API stays for its guard consumers');
  }finally{delete globalThis.__place;}
});

test('setReturnMode marks the walk root while a cross-view return exists and clears it otherwise',async()=>{
  const match=walk.match(/setReturnMode: \(mode\) => \{\n[^}]*\n  \},\n\s+returnMode: \(\) => root\.dataset\.returnMode \|\| '',/);assert.ok(match,'the api declares setReturnMode and returnMode');
  const {api}=await evaluate(`const root={dataset:{}};const api={${match[0]}};`,['api']);
  assert.equal(api.setReturnMode('cross-view'),'cross-view');assert.equal(api.returnMode(),'cross-view');assert.equal(api.setReturnMode(''),'');assert.equal(api.returnMode(),'');assert.equal(api.setReturnMode('anything-else'),'','only the named mode is accepted');
  assert.ok(flat.includes("setReturnMode?.(returnPlace?'cross-view':'')"),'show() tells the walk about the cross-view return');
  const html=await read('../src/laplace/web/walk.html');assert.ok(html.includes('#walk[data-return-mode="cross-view"] #spine-toggle'),'the spine door is demoted by the return mode');
});

// ─ the one read inspector ─────────────────────────────────────────────────────────────────
test('the inspector keeps one modal, replaces with a trail, goes Back through the reopen thunk, closes forms first and returns focus and scroll to the opener',()=>{
  const doc=page();const inspector=createInspector({page:doc});
  const main=new El('main');main.scrollTop=420;const opener=new El('button');main.append(opener);doc.body.append(main);doc.activeElement=opener;
  const form=new El('dialog');form.className='workspace-dialog';form.open=true;doc.body.append(form);
  const dialogs=[];const openPanel=(title)=>{const d=new El('dialog');d.className='workspace-dialog';d.open=true;doc.body.append(d);dialogs.push(d);const reopen=()=>openPanel(title);inspector.adopt(d,{kind:'artifact',title,reopen});return d;};
  const a=openPanel('Evidence A');
  assert.equal(form.open,false,'an open form closes before the inspection');assert.equal(inspector.current.title,'Evidence A');assert.equal(a.dataset.inspector,'artifact');assert.deepEqual(inspector.trail,[]);
  assert.equal(inspector.adopt(a,{kind:'artifact',title:'Evidence A'}).adopted,false,'adopting the same dialog twice is a no-op');assert.equal(a.children.length,0);
  main.scrollTop=900;
  const b=openPanel('Evidence B');
  assert.equal(a.open,false,'the nested read replaced the first panel');assert.equal(a.dataset.inspectorReplaced,'true');assert.equal(inspector.current.title,'Evidence B');assert.deepEqual(inspector.trail,[{kind:'artifact',title:'Evidence A',pin:null,retainsDialog:false,descriptor:'function'}]);
  assert.equal(b.children[0].className,'inspector-back');assert.equal(b.children[0].textContent,'Back to Evidence A');assert.equal(b.dataset.inspectorDepth,'1');
  assert.equal(opener.focused,0,'a replacement does not return focus');
  b.children[0].onclick();
  assert.equal(b.open,false);assert.equal(dialogs.length,3,'Back reopened A through its thunk');assert.equal(inspector.current.title,'Evidence A');assert.deepEqual(inspector.trail,[],'returning does not push the replaced panel');
  const reopened=dialogs[2];assert.equal(reopened.children.length,0,'no Back control at the trail root');
  const nested=openPanel('Evidence D');assert.deepEqual(inspector.trail,[{kind:'artifact',title:'Evidence A',pin:null,retainsDialog:false,descriptor:'function'}]);
  nested.close();   // a user Close (or Esc) on a nested panel is Back
  assert.equal(dialogs.length,5,'closing the nested panel reopened its parent through the thunk');assert.equal(inspector.current.title,'Evidence A');assert.deepEqual(inspector.trail,[]);assert.equal(opener.focused,0);
  dialogs[4].close();
  assert.equal(inspector.current,null);assert.equal(opener.focused,1,'a user Close at the trail root returns focus to the recorded opener');assert.equal(main.scrollTop,420,'and its scroll position');
  const other=new El('button');main.append(other);doc.activeElement=other;openPanel('Evidence C');dialogs.at(-1).close();assert.equal(other.focused,1);assert.equal(opener.focused,1);
});

test('lifetime contract: lineage is true while a panel is current or on the trail and false after a genuine close; trail entries release their dialogs; reopen receives the pinned url+cut',()=>{
  const doc=page();const inspector=createInspector({page:doc});const reopens=[];
  const open=(title)=>{const d=new El('dialog');d.open=true;doc.body.append(d);const reopen=pin=>{reopens.push([title,pin]);return open(title);};inspector.adopt(d,{kind:'owner-read',title,reopen});return d;};
  const a=open('A');const aToken=inspector.tokenOf(a),aLineage=inspector.lineage(aToken);assert.equal(aLineage(),true,'OPEN: current');assert.match(aToken,/^ins-\d+$/,'a door keeps a string token, never the dialog');
  inspector.pin(aToken,{url:'/owner/w',cut:'cut-1'});assert.deepEqual(inspector.current.pin,{url:'/owner/w',cut:'cut-1'});
  const b=open('B');assert.equal(aLineage(),true,'REPLACED: still on the trail');assert.equal(a.dataset.inspectorReplaced,'true');assert.deepEqual(inspector.trail,[{kind:'owner-read',title:'A',pin:{url:'/owner/w',cut:'cut-1'},retainsDialog:false,descriptor:'function'}],'the trail entry released the dialog');
  const bLineage=inspector.lineage(inspector.tokenOf(b));inspector.pin(inspector.tokenOf(b),{url:'/owner/w',cut:'cut-2'});
  const c=open('C');assert.equal(aLineage(),true);assert.equal(bLineage(),true);
  c.close();   // BACK (Close on a nested panel)
  assert.deepEqual(reopens.at(-1),['B',{url:'/owner/w',cut:'cut-2'}],'the reopen received B\'s own pinned cut, not A\'s or the latest');assert.equal(inspector.current.title,'B');assert.equal(inspector.current.pin.cut,'cut-2','the returning panel keeps its pin');
  assert.equal(bLineage(),false,'the replaced B token is gone; its reopened successor has its own token');
  inspector.back();assert.deepEqual(reopens.at(-1),['A',{url:'/owner/w',cut:'cut-1'}]);assert.deepEqual(inspector.trail,[]);
  const a2=inspector.current.dialog;const a2Lineage=inspector.lineage(inspector.tokenOf(a2));a2.close();   // GENUINE CLOSE at the root
  assert.equal(inspector.current,null);assert.equal(a2Lineage(),false,'STALE ASYNC: a read completing now is rejected');assert.equal(aLineage(),false);
});

test('inspector snapshots are keyed by URL and owner cut, read object-shaped read_cut.revision, are bounded in count and bytes, and never hold a first read',()=>{
  const inspector=createInspector({limit:3,clock:()=>'2026-10-13T00:00:00Z'});
  assert.equal(payloadCut({read_cut:{revision:'cut-r1',scope:'…'},as_of:'x'}),'cut-r1','object-shaped read_cut.revision wins');assert.equal(payloadCut({read_cut:'c1'}),'c1');assert.equal(payloadCut({as_of:'a'}),'a');assert.equal(payloadCut({index_stamp:'sha256:s'}),'sha256:s');assert.equal(payloadCut({}),null);assert.equal(payloadCut('text'),null);
  assert.equal(inspector.remember('/owner/w',{read_cut:{revision:'r1'},n:1}),true);assert.equal(inspector.remember('/owner/w',{read_cut:{revision:'r2'},n:2}),true);
  assert.equal(inspector.cacheSize,2,'two cuts of one URL are two entries; a newer cut does not overwrite the older');
  assert.deepEqual(inspector.snapshot('/owner/w','r1').value,{read_cut:{revision:'r1'},n:1});assert.deepEqual(inspector.snapshot('/owner/w').value,{read_cut:{revision:'r2'},n:2},'without a cut, the latest remembered cut');assert.equal(inspector.snapshot('/owner/w','r9'),null);
  assert.equal(inspector.snapshot('/owner/w','r1').at,'2026-10-13T00:00:00Z');
  inspector.remember('/owner/x',{as_of:'a'});inspector.remember('/owner/y',{as_of:'b'});assert.equal(inspector.cacheSize,3);assert.equal(inspector.snapshot('/owner/w','r2'),null,'least recently used left first');
  assert.equal(inspector.remember('/owner/big',{text:'x'.repeat(INSPECTOR_SNAPSHOT_BYTES+1)}),false,'an oversized payload is not retained');assert.equal(inspector.remember('/owner/pdf',null),false);
  const unicode={text:'é'.repeat(45000)};assert.ok(JSON.stringify(unicode).length<INSPECTOR_SNAPSHOT_BYTES&&utf8Bytes(unicode)>INSPECTOR_SNAPSHOT_BYTES,'45,000 two-byte characters: under the cap by string length, over it in UTF-8');assert.equal(inspector.remember('/owner/unicode',unicode),false,'the cap is serialized UTF-8 bytes');
  assert.equal(INSPECTOR_CACHE_LIMIT,12);assert.equal(createInspector().cacheLimit,12);assert.equal(createInspector().snapshotBytes,65536);
});

test('the REAL owner-read door adopts itself, replaces on a nested read, and Back renders the bounded snapshot with its provenance and a Re-read current control',async()=>{
  resetSharedInspector();const d=harness.installDOM();
  try{
    const requests=[];const detail=(id,rev)=>({project:'p',view:'detail',task:{id,title:'Work '+id,status:'open',goal:'Goal '+id,dispatch:{children:[]}},blockers:[],children:{items:[]},dependants:{items:[]},allowed_actions:{},read_cut:{revision:rev}});
    const request=async route=>{requests.push(route);const id=new URL(route,'http://local').searchParams.get('id');return detail(id,'rev-'+id+'-'+requests.length);};
    const urlA='/work/state?'+new URLSearchParams({project:'p',view:'detail',id:'A'}),urlB='/work/state?'+new URLSearchParams({project:'p',view:'detail',id:'B'});
    const a=await openArtifact({ownerRead:{http:{method:'GET',url:urlA}},label:'Work A',request});
    const inspector=sharedInspector();
    assert.equal(inspector.current.kind,'owner-read');assert.equal(inspector.current.title,'Work A');assert.equal(a.dataset.inspector,'owner-read');assert.deepEqual(requests,[urlA]);
    assert.equal(inspector.cacheSize,1,'the first read is remembered for a later Back, never served from the cache');
    const b=await openArtifact({ownerRead:{http:{method:'GET',url:urlB}},label:'Work B',request});
    assert.equal(a.open,false,'A was replaced');assert.equal(d.dialogs().length,1);assert.deepEqual(inspector.trail,[{kind:'owner-read',title:'Work A',pin:{url:urlA,cut:'rev-A-1'},retainsDialog:false,descriptor:'factory'}]);assert.equal(b.children[0].className,'inspector-back');assert.equal(b.children[0].textContent,'Back to Work A');
    assert.equal(document.activeElement!==d.editor,true,'replacement did not return focus to the editor');
    assert.deepEqual(inspector.trail[0].pin,{url:urlA,cut:'rev-A-1'},'the trail entry pins the exact url+cut A displayed');
    const reopened=await b.children[0].onclick();
    assert.equal(b.open,false);assert.equal(requests.length,2,'Back did not re-read: A came from the snapshot');assert.equal(inspector.current.title,'Work A');assert.deepEqual(inspector.trail,[]);
    const body=harness.bodyOf(reopened);assert.match(body.textContent,/Previously inspected · \d\d:\d\d · read-only/,'concise historical state');assert.ok(!body.textContent.includes('Snapshot: the owner payload'));assert.match(body.textContent,/Work A/);
    const panel=reopened.querySelector('.artifact-current');assert.equal(panel.dataset.snapshot,'true');const provenance=panel.querySelector('.snapshot-provenance');assert.match(provenance.textContent,/Exact provenance/);assert.match(provenance.textContent,/cut rev-A-1/);assert.match(provenance.textContent,/no current permission is implied/);
    const reread=harness.findButton(reopened,'Read current');assert.ok(reread,'the historical state offers a fresh read');await reread.click();
    assert.equal(requests.length,3,'Read current reads the owner again');assert.ok(!harness.bodyOf(reopened).textContent.includes('Previously inspected'),'a fresh read carries no historical state');
    reopened.close();assert.equal(inspector.current,null);assert.equal(document.activeElement,d.editor,'the user Close returns focus to the opener recorded at the trail start');
  }finally{d.restore();resetSharedInspector();}
});

test('the REAL owner-read door pins Back to the inspected cut: the same URL read at cut 1 then cut 2 returns to cut 1',async()=>{
  resetSharedInspector();const d=harness.installDOM();
  try{
    let version=1;const url='/work/state?'+new URLSearchParams({project:'p',view:'detail',id:'W'});const requests=[];
    const request=async route=>{requests.push(route);return {project:'p',view:'detail',task:{id:'W',title:'Version '+version,status:'open',goal:'Goal',dispatch:{children:[]}},blockers:[],children:{items:[]},dependants:{items:[]},allowed_actions:{},read_cut:{revision:'cut-'+version}};};
    const first=await openArtifact({ownerRead:{http:{method:'GET',url}},label:'First inspection',request});assert.match(harness.bodyOf(first).textContent,/Version 1/);
    version=2;const second=await openArtifact({ownerRead:{http:{method:'GET',url}},label:'Second inspection',request});assert.match(harness.bodyOf(second).textContent,/Version 2/);
    const inspector=sharedInspector();assert.deepEqual(inspector.trail[0].pin,{url,cut:'cut-1'});assert.equal(inspector.cacheSize,2,'two cuts of one URL are two snapshots');
    const back=await second.children[0].onclick();
    assert.equal(requests.length,2);assert.match(harness.bodyOf(back).textContent,/Version 1/,'Back shows the inspected cut, not the latest cut of the URL');assert.ok(!harness.bodyOf(back).textContent.includes('Version 2'));assert.match(back.querySelector('.snapshot-provenance').textContent,/cut cut-1/);
    back.close();
  }finally{d.restore();resetSharedInspector();}
});

test('the REAL saved-turn door adopts itself and nested turns replace the panel instead of closing it first',async()=>{
  resetSharedInspector();const d=harness.installDOM();
  try{
    const turn={id:'WT-1',session_id:'WS',text:'Request',reply:{display_text:'Reply',status:'completed'},result_links:[],failures:[],action_count:0,failure_count:0};
    const dialog=await openSavedTurn({project:'p',turnId:'WT-1',request:async()=>({project:'p',turn})});
    const inspector=sharedInspector();assert.equal(inspector.current.kind,'saved-turn');assert.equal(dialog.dataset.inspector,'saved-turn');
    dialog.close();assert.equal(inspector.current,null);assert.equal(document.activeElement,d.editor);
    assert.ok(!materialSource.includes('dialog.close();await openSavedTurn('),'nested turns rely on the inspector replacement (trail), not on closing first');
    assert.ok(materialSource.includes("token=inspector.adopt(dialog,{kind:'saved-turn',title:'Saved turn',reopen:{factory:reopenSavedTurn,args:savedTurnArgs(options)}}).token;"),'a module-level factory with plain args');assert.ok(materialSource.includes('const nestedCurrent=()=>isCurrent()&&(fresh()||lineage());')&&materialSource.includes('const lineage=()=>inspector.lineage(token)();'),'nested currency is the token lineage');
  }finally{d.restore();resetSharedInspector();}
});

test('every PDF, artifact and saved-turn door adopts at the door; the shell passes no adopter and no caller can bypass it',async()=>{
  // openPdf: adoption before showModal, the last reading position in the reopen thunk, no focus steal on replacement
  assert.ok(pdfSource.includes("token=inspector.adopt(dialog,{kind:'pdf',title,reopen:{factory:reopenPdf,args:{url,title,notice,onOpenArtifact,initialPosition,onRendered}}}).token;")&&pdfSource.indexOf("inspector.adopt(dialog")<pdfSource.indexOf('dialog.showModal();window.addEventListener'));
  assert.ok(!pdfSource.includes('returnTo')&&!pdfSource.includes('closeCurrent'),'one return mechanism, no viewer singleton');assert.ok(pdfSource.includes('options.isCurrent=inspector.lineage(token)')&&pdfSource.includes('inspector.pin(token,{position:lastPosition})'));
  assert.ok(artifactSource.includes('const nested=nestedOpener(project,request,renderMarkdown,inspector.lineage(lifetime));')&&artifactSource.includes('const nestedOpener=(project,request,renderMarkdown,lineage)=>(p,l,o={})=>openArtifact(')&&artifactSource.includes('const {opener:_opener,onOpen:_onOpen,isCurrent:_isCurrent,onReadError:_onReadError,...reopenArgs}=options;')&&artifactSource.includes('const reopenArtifact=(args,pin)=>openArtifact('),'nested openers and reopen factories are module-level; the door keeps a {token} lifetime handle, never DOM');
  assert.ok(pdfSource.includes('if(pdf)lastPosition=readingPosition();')&&pdfSource.includes('!replacedByInspector(dialog))origin.focus()'));
  // openArtifact: the PDF shortcut and nested helper reach openPdf/openArtifact, which adopt themselves; the onclose focus return is guarded
  const shortcut=slice(artifactSource,"if(/\\.pdf$/i.test(path)){const {openPdf}",'\n');assert.ok(shortcut.includes('onOpen,onOpenArtifact:'),'the PDF shortcut hands the caller onOpen through');
  assert.ok(artifactSource.includes('document.body.append(dialog);adopt(dialog);dialog.showModal();')&&artifactSource.includes('replacedByInspector(dialog))return;'));
  // every opener in the tree goes through one of the three adopting doors
  const statics=await Promise.all(['manuscript-editor.mjs','workspace-output.mjs','writing-evidence.mjs','research-card.mjs','workspace-literature.mjs','workspace-analytics.mjs','workspace-work.mjs','derived-output.mjs','document-template.mjs'].map(f=>read('../src/laplace/web/static_shared/'+f)));
  for(const source of [...statics,walkSource()])for(const m of source.matchAll(/\b(openPdf|openArtifact|openSavedTurn)\(/g))assert.ok(['openPdf','openArtifact','openSavedTurn'].includes(m[1]));
  for(const needle of ["inspector.adopt(dialog","onOpen:dialog=>inspector.adopt"])assert.ok(!shell.includes(needle),'the shell no longer adopts for the doors: '+needle);
  assert.ok(shell.includes("const inspector=sharedInspector();"));
});

test('RESOURCES: owner → REAL PDF → REAL PDF retains neither the replaced owner dialog nor its 1,000,000-character payload; the negative control is detected (heap snapshot, property-edge reachability, --expose-gc)',async()=>{
  const {spawnSync}=await import('node:child_process');
  const probe=new URL('./helpers/inspector_retention_probe.mjs',import.meta.url);
  const run=spawnSync(process.execPath,['--expose-gc',probe.pathname],{encoding:'utf8',timeout:120000});
  assert.equal(run.status,0,run.stderr);
  const result=JSON.parse(run.stdout.trim().split('\n').at(-1));
  assert.deepEqual(result.afterPdf1,{ownerReplaced:true,current:'pdf',trail:[['owner-read','Exact template preview','factory',false]]},'the callback-bearing owner branch handed its nested opener to the REAL viewer, which replaced it');
  assert.deepEqual(result.afterPdf2.trail,[['owner-read','Exact template preview','factory',false],['pdf','Exact template preview','factory',false]],'the second REAL viewer replaced the first; PDF 1\'s entry retains args.onOpenArtifact (the nested opener)');
  assert.equal(result.afterPdf2.pdf1Replaced,true);assert.equal(result.afterPdf2.pdf2Current,true);assert.equal(result.pdf2Alive,true);
  assert.deepEqual(result.negativeControl,{dialogRetained:true,payloadRetained:true},'NEGATIVE CONTROL: a deliberately retained owner dialog is detected by property-edge reachability');
  assert.deepEqual(result.released,{dialogRetained:false,payloadRetained:false},'after the deliberate reference is dropped nothing in the inspector, the viewers or the nested opener retains the owner dialog or its payload');
});

test('panel() creates an adopted dialog for help diagrams with Back to the previous reading',async()=>{
  const doc=page();const inspector=createInspector({page:doc});
  const help=new El('dialog');help.open=true;doc.body.append(help);inspector.adopt(help,{kind:'panel',title:'Help · Work',reopen:()=>help});
  const dialog=await inspector.panel({kind:'help-diagram',title:'How Work moves',render:body=>{const p=new El('p');p.textContent='diagram';body.append(p);}});
  assert.equal(dialog.dataset.inspector,'help-diagram');assert.equal(help.open,false);assert.equal(dialog.children[0].textContent,'Back to Help · Work');assert.equal(dialog.querySelector('.inspector-body').textContent,'diagram');assert.equal(dialog.attrs['aria-label'],'How Work moves');
  assert.deepEqual(inspector.trail,[{kind:'panel',title:'Help · Work',pin:null,retainsDialog:false,descriptor:'function'}]);
});

// ─ the Work authoring form's owner-backed choices ─────────────────────────────────────────
test('the Add authored work selectors: bounded first read, retained owner continuation, narrowing, exact-id lookup, preserved selections, memo reuse and CHANGED_INPUT restart',async()=>{
  const loader=slice(shell,'  const WORK_CHOICE_PAGES=6,','  async function reloadState(');
  const form=slice(shell,"    const create=E('details','','operator-work-create');",'create.append(add);host.append(create);')+'create.append(add);host.append(create);';
  const calls=[],rows=n=>Array.from({length:n},(_,i)=>({id:'T'+(i+1),title:'Task '+(i+1),status:i%7===0?'done':'open'}));
  const catalogue=rows(700);let refuseContinuationOnce=false;
  const api=async url=>{calls.push(url);const q=new URL(url,'http://local').searchParams;
    if(q.get('view')==='detail'){const id=q.get('id');const row=catalogue.find(r=>r.id===id)||(id==='T-outside'?{id,title:'Outside the catalogue',status:'open'}:null);if(!row)throw Error('Unknown work');return {project:'book',view:'detail',task:row,read_cut:{revision:'cut'}};}
    const offset=Number(q.get('offset')||0),limit=Number(q.get('limit'));if(refuseContinuationOnce&&offset>0){refuseContinuationOnce=false;throw Error('CHANGED_INPUT: work records changed between pages');}const page=catalogue.slice(offset,offset+limit);const next=offset+page.length<catalogue.length?{http:{method:'GET',url:'/work/state?'+new URLSearchParams({project:'book',view:'summary',offset:offset+page.length,limit,as_of:'cut'})}}:null;return {tasks:page,pagination:{next_read:next}};};
  const field=(form,label,name,value='',options)=>{const l=E('label',label),input=E(options?'select':'input');input.name=name;if(options)for(const [v,t]of options){const o=E('option',t);o._value=v;input.append(o);}input.value=value??'';l.append(input);form.append(l);return input;};
  const area=(form,label,name)=>field(form,label,name);const alerts=[];
  const button=(label,fn)=>{const b=E('button',label);b.onclick=async()=>{try{await fn();}catch(error){alerts.push(error.message);}};return b;};
  const makeEnv=()=>({E,field,area,api,operatorHTTP,button,wireForm:(f,submit)=>{f.save=submit;},changed:async()=>{},actionAlert:(c,m)=>alerts.push(m),state:{tasks:rows(12)},workMemory:{},controller:{capture:()=>({drafts:{}})},host:new El('section')});
  globalThis.__choices=makeEnv();
  const code=`const {E,field,area,api,operatorHTTP,button,wireForm,changed,actionAlert,state,workMemory,controller,host}=globalThis.__choices;const project='book';let task=null,workChoices=null,workChoicesLoading=null;const WORK_SUMMARY_READ='/work/state?project=book&view=summary&limit=12';${SERVICE_PRELUDE}${loader}${form}\nexport {create,add,deps,parentField,choicesNote,loadWorkChoices,moreChoices,findField,exactField,addExact};`;
  const find=(host,label)=>host.all().find(n=>n.tag==='button'&&n.textContent===label);
  try{
    const m=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'));
    assert.equal(calls.length,0,'entry performs no catalogue read');assert.equal(m.deps.options.length,12);
    const typed=E('option','T650 (typed)');typed._value='T650';m.parentField.append(typed);m.parentField.value='T650';m.deps.options[2].selected=true;
    m.create.open=true;await m.create.ontoggle();
    assert.equal(calls.length,6,'the first read is bounded to six pages');assert.equal(m.deps.options.length,600);assert.equal(m.moreChoices.hidden,false,'the owner continuation is retained and offered');assert.match(m.choicesNote.textContent,/600 work items offered .*more exist/);
    assert.equal(m.parentField.value,'T650','the typed parent survived the refill');assert.deepEqual([...m.deps.selectedOptions].map(o=>o._value),['T3']);
    // More continues from the retained continuation, never discarding it
    await m.moreChoices.onclick();assert.equal(calls.length,7);assert.match(calls[6],/offset=600/);assert.equal(m.deps.options.length,700);assert.equal(m.moreChoices.hidden,true);assert.match(m.choicesNote.textContent,/700 work items offered \(owner catalogue, 7 pages\)/);
    assert.equal(m.parentField.value,'T650');assert.deepEqual([...m.deps.selectedOptions].map(o=>o._value),['T3']);
    // narrowing by title or id hides non-matching options but never a selected one
    m.findField.value='Task 69';m.findField.oninput();assert.equal(m.deps.options.filter(o=>!o.hidden).length,12,'Task 69, Task 690–699 and the selected T3');assert.equal(m.deps.options.find(o=>o._value==='T3').hidden,false);m.findField.value='';m.findField.oninput();assert.ok(m.deps.options.every(o=>!o.hidden));
    // an exact id outside the catalogue is looked up at the owner and offered, selected as a prerequisite
    m.exactField.value='T-outside';await m.addExact.onclick();assert.match(calls.at(-1),/view=detail&id=T-outside/);const added=m.deps.options.find(o=>o._value==='T-outside');assert.ok(added&&added.selected);assert.deepEqual(alerts,[]);
    m.exactField.value='T-missing';await m.addExact.onclick();assert.deepEqual(alerts,['Unknown work']);alerts.length=0;
    // reopen reuses the memo (rows + continuation) without a read
    const before=calls.length;m.create.open=false;delete m.create.dataset.choicesLoaded;m.create.open=true;await m.create.ontoggle();assert.equal(calls.length,before,'the memo is reused on reopen');assert.equal(m.deps.options.length,701);
    // CHANGED_INPUT on a continuation restarts from the first page once, re-reading what was offered, keeping selections
    globalThis.__choices=makeEnv();const m2=await import('data:text/javascript;base64,'+Buffer.from(code+'\n// second').toString('base64'));calls.length=0;refuseContinuationOnce=false;
    m2.create.open=true;await m2.create.ontoggle();assert.equal(calls.length,6);m2.deps.options[5].selected=true;refuseContinuationOnce=true;await m2.moreChoices.onclick();
    assert.ok(calls.length>=7+6,'the refused continuation restarted from page 1 up to the offered depth');assert.equal(m2.deps.options.length,700);assert.deepEqual([...m2.deps.selectedOptions].map(o=>o._value),['T6']);assert.deepEqual(alerts,[]);
    assert.ok(shell.includes("const WORK_SUMMARY_READ='/work/state?project='+enc+'&view=summary&limit=12'"),'the entry summary stays bounded');
  }finally{delete globalThis.__choices;}
});

// ─ the top bar, entry rules, entry reads and the retirements ──────────────────────────────
test('the top bar carries the Workspace menu, the Menu door, the contextual group and Help; the context strip row, Views and the header app links are retired',()=>{
  const header=slice(shell,"root.innerHTML=`<header class=\"workspace-header\">",'</header>');
  for(const needle of ['data-workspace-menu','data-control="workspace:menu"','data-nav data-control="nav:menu"','>Menu<','class="workspace-context" data-context','data-view-label','data-work-scope data-control="context:work"','data-clear-task data-control="context:clear"','data-return-reader data-control="context:return"','data-guide data-control="help:guide"','>Help<','data-talk data-control="conversation:toggle"'])assert.ok(header.includes(needle),needle);
  assert.ok(!header.includes('>Views<')&&!header.includes('href="/project?workspace=writing">Projects'),'Views and the bare Projects link are retired');
  assert.ok(!shell.includes("</header><p data-notice class=\"work-status\" role=\"status\"></p><div class=\"workspace-context\""),'the context strip row below the bar is retired');
  assert.ok(flat.includes("[['projects','Projects'],['activity','Workspace activity'],['dependencies','Workspace dependencies'],['owners','System owners'],['settings','App settings']]"),'the Workspace menu lists the five app destinations through bindAppLink');
  assert.ok(!shell.includes('workspace-app-link')&&!css.includes('workspace-app-link'));
});

test('entry rules: conversation closed on a cold entry unless asked; a saved association is never contextual Work; aliases reach the library and shared bindings',()=>{
  const rules=slice(shell,'  // ENTRY RULES','  for(const [id,label,short] of NAV_LABELS)').replace(/\n\s*/g,'');   // the chrome owner (M5 S2 F1)
  assert.ok(rules.includes("openSession(createdConversation,{remember:false})"),'a cold entry opens the conversation only for conversation=open or session=, and never rewrites the stored preference');
  assert.ok(!rules.includes("localStorage.getItem(SESSION_OPEN_KEY)"),'the stored session-open value is not an entry rule');
  assert.ok(rules.includes("initialQuery.get('conversation')==='open'||!!initialQuery.get('session')"));
  assert.ok(rules.includes("if(ui.root.dataset.navLayout==='compact')localStorage.setItem(NAV_CLOSED_KEY"),'the Menu door persists the preference only in the compact layout');
  assert.ok(shell.includes("localStorage.setItem(SESSION_OPEN_KEY,String(open))"),'the Conversation toggle still records the layout preference');
  const boot=slice(shell,'  // ENTRY READS','  try{\n    const coordinates=profileGenerationCoordinates').replace(/\n\s*/g,'');
  assert.ok(boot.includes("if(initialQuery.has('work'))"),'Work is restored at entry only when work= is present');
  assert.ok(!shell.includes('restoreConversationWork')&&!shell.includes('onWorkAssociation')&&!shell.includes('workStartup'),'no association-to-selection door remains');
  assert.ok(boot.includes("api(WORK_SUMMARY_READ),api('/projects/metadata?project='+enc)")&&!boot.includes("/projects/library"),'entry reads the metadata owner and the bounded Work summary, not the library');
  assert.ok(boot.includes("if(requested==='turns'){await show('overview',false,{reuseState:true});if(!entryCurrent())return workspace;}"),
    'view=turns opens Home with the conversation library (and the entry stops if this mount was destroyed meanwhile, S2-R2)');
  const show=slice(shell,'  async function show(view,ask=true','  async function readSavedTurn').replace(/\n\s*/g,'');   // views are domain controllers (M5 S2 F1)
  assert.ok(show.includes("const sharedBindings=view==='dependencies';")&&show.includes("/shared material/i"),'view=dependencies lands on Material at its shared bindings');
  assert.ok(show.includes("if(view==='turns'){chrome.openSession(true);await session.browseConversations();return true;}"));
  assert.ok(show.includes("const projects=(await home.library()).projects;"),'the library is read when Material opens');
  assert.ok(show.includes("if(view==='settings'&&version===loadVersion)await home.renderSettings(body);")&&show.includes("if(view==='presentation'&&version===loadVersion)await figures.render(body);"),'Settings and Presentation perform no Work summary read');
  assert.ok(!show.includes("if(view==='dependencies')"),'the Dependencies view branch is gone');
});

test('the book outline, the Dependencies view and the Home destinations row are retired with every consumer',async()=>{
  for(const needle of ['renderBookOutline','bookNav','book-outline','mountDependencies','project-destinations',"'Open turns'","['dependencies','Dependencies']","['turns','Conversations']"])assert.ok(!shell.includes(needle),'workspace.mjs still mentions '+needle);
  assert.ok(!css.includes('.book-outline')&&!css.includes('project-destinations'),'workspace.css retired the rules');
  assert.ok(!materialSource.includes('export async function mountDependencies'));assert.ok(!materialSource.includes("dependencies:'work'"));
  const app=await read('../src/laplace/web/static_shared/workspace-app.mjs');assert.ok(!app.includes('Open project-local dependencies')&&app.includes("['material','Open project material and shared bindings']"),'the app-level dependencies view links to Material');
  const declarations=await read('../src/laplace/native/declarations.py');assert.ok(!declarations.includes('("dependencies", "Dependencies")')&&!declarations.includes('("turns", "Conversations")')&&declarations.includes('"nav:menu"')&&declarations.includes('"workspace:menu"'),'the help owner declares the bar and not the retired entries');
  assert.ok(flat.includes("ui.button('Saved conversations',()=>views.show('turns'))"),'Home keeps one door to saved conversations');   // workspace-home.mjs
  assert.ok(flat.includes("shellState.placeMemo()&&shellState.placeMemo().source===manuscript.sourceWindow()"),'context() reads the place memo');   // workspace-context.mjs
});

test('the design tokens are one file, allowlisted, linked by both pages, and the walk aliases its colour names to them with held distinct from refusal',async()=>{
  const tokens=await read('../src/laplace/web/static_shared/tokens.css');
  for(const name of ['--ink','--ink2','--bg','--panel','--panel2','--edge','--edge2','--accent','--ok','--warn','--bad','--dim','--held','--serif','--mono','--display','--space-1','--space-8','--radius-1','--radius-2','--focus-ring','--motion-fast','--shadow-1'])assert.ok(new RegExp('^\\s+'+name+':','m').test(tokens),name);
  assert.ok(tokens.includes('--motion-fast: 120ms'));
  const warn=tokens.match(/--warn:\s*(#[0-9a-f]{6})/i)[1],held=tokens.match(/--held:\s*(#[0-9a-f]{6})/i)[1];assert.equal(held,warn,'held is the warn value as its own literal');
  const ui=await read('../src/laplace/web/shared_ui.py');assert.ok(ui.includes('"tokens.css": "text/css; charset=utf-8"')&&ui.includes('"workspace-inspector.mjs": "text/javascript; charset=utf-8"'));
  const pipeline=await read('../src/laplace/web/pipeline.html');assert.ok(pipeline.indexOf('/shared/tokens.css')>0&&pipeline.indexOf('/shared/tokens.css')<pipeline.indexOf('/shared/workspace.css'),'the shell page links tokens before workspace.css');
  const html=await read('../src/laplace/web/walk.html');const link=html.indexOf('<link rel="stylesheet" href="/shared/tokens.css">'),style=html.indexOf('<style>');assert.ok(link>0&&link<style,'walk.html links tokens before its inline style');
  const rootBlock=html.slice(html.indexOf(':root {'),html.indexOf('}',html.indexOf(':root {')));
  for(const alias of ['--ink-dim:  var(--ink2)','--bg-paper: var(--panel)','--bg-rail:  var(--panel2)','--line:     var(--edge)','--line-soft:var(--edge2)','--live:     var(--accent)','--warn:     var(--bad)','--parked:   var(--held)'])assert.ok(rootBlock.includes(alias),alias);
  assert.ok(!rootBlock.includes('--parked:   var(--warn)'),'parked no longer resolves through the overridden --warn');
  assert.ok(!/--ink:\s*#|--bg:\s*#/.test(rootBlock),'the walk no longer defines --ink or --bg itself');
  assert.ok(!html.includes('shell.js'),'the iframe page does not load the legacy shell script');
});
