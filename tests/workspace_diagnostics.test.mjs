// C12 OBSERVATION CONTRACT, PAGE SIDE (2026-10-15): the developer counters render only with diagnostics=1, only on an
// explicit click (no timer), from the owners' bounded counters; the shell's page listeners are added through one
// owner, counted, and all removed by workspace.destroy().
import {test} from 'node:test';
import assert from 'node:assert/strict';
const {mountShell}=await import('./helpers/shell_fixture.mjs');

test('without diagnostics=1 there is no readout and nothing extra is loaded',async()=>{
  const s=await mountShell();
  try{
    await s.workspace.show('settings');await s.settle();
    assert.equal(s.root.querySelector('.workspace-diagnostics'),null);
    assert.ok(!s.calls.some(call=>call.includes('traffic')),'the page never reads the server traffic view');
  }finally{s.restore();}
});

test('with diagnostics=1 Settings shows the counters on request; page listeners are counted and all removed on destroy',async()=>{
  const s=await mountShell({query:'diagnostics=1'});
  try{
    await s.workspace.show('settings');await s.settle();await s.settle();
    const details=s.root.querySelector('.workspace-diagnostics');assert.ok(details,'the readout is at the end of Settings');
    const output=s.root.querySelector('[data-laplace-diagnostics]');assert.equal(output.textContent,'Not read yet.','nothing is read until asked');
    assert.match(details.textContent,/reload resets it/);assert.match(details.textContent,/server traffic view/);
    const refresh=[...details.querySelectorAll('button')].find(node=>node.textContent==='Refresh counters');refresh.onclick();
    const shot=JSON.parse(output.textContent);
    assert.equal(shot.schema_version,'laplace.workspace-page-counters/1');
    assert.equal(shot.bridge.installed,true);assert.equal(typeof shot.bridge.ledger.rejected,'number');
    // P2: the frontend-basis check adds one focus and one reconnection listener (frontend-basis.mjs, workspace.mjs)
    assert.deepEqual(shot.page_listeners.active_by_type,{focus:2,visibilitychange:1,keydown:1,resize:2,'laplace-source-effect':1,beforeunload:1,'laplace-workspace-reconnected':1});
    assert.equal(shot.page_listeners.active,9);assert.equal(shot.page_listeners.removed,0);
    assert.equal(typeof shot.inspector.cache_entries,'number');assert.equal(shot.help_open,false);
    const removed=[],remove=window.removeEventListener,removeDoc=document.removeEventListener;
    window.removeEventListener=(type,fn,options)=>{removed.push('window:'+type);return remove(type,fn,options);};
    document.removeEventListener=(type,fn,options)=>{removed.push('document:'+type);return removeDoc(type,fn,options);};
    s.workspace.destroy();
    for(const type of ['window:focus','document:visibilitychange','document:keydown','window:resize','window:laplace-source-effect','window:beforeunload','window:message','window:laplace-workspace-reconnected'])
      assert.ok(removed.includes(type),type+' is removed by destroy');
    assert.ok(removed.filter(type=>type==='window:resize').length>=2,'both shell resize listeners (other owners remove their own too)');
    refresh.onclick();assert.equal(JSON.parse(output.textContent).page_listeners.active,0);
  }finally{s.restore();}
});

// C12 RESIDUAL R4 (Sol, 2026-10-15): workspace.destroy() tears down the shell-owned Help and task cue through their own
// owners: no cue/help DOM, observers, frames or cue listeners remain; a second destroy is safe; a help or task import
// still pending cannot mount afterwards; the cue's run is left open and resumable (no Finished, no Stopped, no seen).
test('destroy disposes an active task cue and help, idempotently, without writing an outcome; late imports cannot remount',async()=>{
  const s=await mountShell();
  const forwarded={add:globalThis.addEventListener,remove:globalThis.removeEventListener};
  const live=new Map(),key=(target,type)=>(target===document?'document:':'window:')+type;
  const track=(target,add,remove)=>({add:(type,fn,options)=>{live.set(key(target,type)+'#'+live.size,{target,type,fn});return add.call(target,type,fn,options);},
                                     remove:(type,fn,options)=>{for(const [k,row] of live)if(row.target===target&&row.type===type&&row.fn===fn)live.delete(k);return remove.call(target,type,fn,options);}});
  const win=track(window,window.addEventListener,window.removeEventListener),doc=track(document,document.addEventListener,document.removeEventListener);
  globalThis.addEventListener=win.add;globalThis.removeEventListener=win.remove;window.addEventListener=win.add;window.removeEventListener=win.remove;
  document.addEventListener=doc.add;document.removeEventListener=doc.remove;
  try{
    await s.root.querySelector('[data-guide]').onclick();await s.settle();
    const row=s.root.querySelector('.workspace-help').querySelectorAll('button').find(node=>node.dataset?.journey);
    assert.ok(row,'a declared task row');const journey=row.dataset.journey;
    await row.onclick();await s.settle();await s.settle();
    const cue=document.body.querySelector('.workspace-guide');assert.ok(cue&&cue.isConnected,'the cue is mounted');
    cue.querySelectorAll('button').find(node=>node.textContent==='Skip').onclick();   // the person moves on: progress is recorded
    const runId=JSON.parse(globalThis.sessionStorage.getItem('laplace:learning:book')).journeys[journey].run.id;
    const cueTypes=()=>[...live.values()].map(row=>row.type).filter(type=>['laplace-workspace-navigation','resize','scroll','keydown'].includes(type));
    assert.ok(['laplace-workspace-navigation','scroll'].every(type=>cueTypes().includes(type)));
    const store=JSON.parse(globalThis.sessionStorage?.getItem?.('laplace:learning:book')||'null');
    s.workspace.destroy();
    assert.equal(cue.isConnected,false,'no cue DOM remains');assert.equal(document.body.querySelector('.workspace-guide'),null);
    assert.equal(s.root.querySelector('.workspace-help'),null,'no help layer remains');
    assert.deepEqual(cueTypes(),[],'no cue, help or shell listener of these types remains');
    s.workspace.destroy();   // idempotent
    const after=JSON.parse(globalThis.sessionStorage.getItem('laplace:learning:book'));
    const entry=after.journeys[journey];
    assert.deepEqual([entry.step,entry.closed,entry.outcome,entry.run.id],[1,false,undefined,runId],'teardown writes no outcome: the run stays open at its step');
    void store;
  }finally{globalThis.addEventListener=forwarded.add;globalThis.removeEventListener=forwarded.remove;s.restore();}
});

test('a help open still pending when the workspace is destroyed never mounts',async()=>{
  const s=await mountShell();
  try{
    const pending=s.root.querySelector('[data-guide]').onclick();   // its imports and reads are not yet resolved
    s.workspace.destroy();await pending;await s.settle();
    assert.equal(s.root.querySelector('.workspace-help'),null);assert.equal(document.body.querySelector('.workspace-help'),null);
  }finally{s.restore();}
});
