import {focusTarget} from './workspace-returns.mjs';
// THE ONE READ INSPECTOR (M5 C3, plan §3 inspector_rule).
//
// Every reading door adopts the dialog it creates, AT THE DOOR, before showing it:
//   writing-artifact.openArtifact    artifact bytes and owner reads (kinds artifact, owner-read)
//   writing-pdf.openPdf              every PDF viewer: manuscript PDF, template previews, figure
//                                    assets, literature PDFs, nested companion PDFs (kind pdf)
//   workspace-material.openSavedTurn the saved-turn panel and its nested turns (kind saved-turn)
//   panel()                          help diagrams and other plain panels (help-diagram, panel)
// A caller's own `onOpen` still runs after adoption. The shell and every door share one
// instance per document (`sharedInspector()`, window.laplaceInspector).
//
// ─ THE LIFETIME CONTRACT (Sol 2026-10-12; each transition has a test in
//   tests/workspace_shell.test.mjs or the door tests) ─────────────────────────────────────
//
//   OPEN            adopt(dialog,{kind,title,reopen}) makes the dialog the CURRENT panel and
//                   returns a small LIFETIME HANDLE {token}: a string token is the only thing a
//                   door keeps or hands on. Its read may still be pending.
//   REPLACED        a nested read adopts a new dialog: the current panel is closed with
//                   dataset.inspectorReplaced='true' (its own close handler must not return
//                   focus), its DOM reference is dropped, and a small ENTRY {token, kind,
//                   title, reopen, pin} is pushed onto the trail. `reopen` is a DESCRIPTOR
//                   {factory, args}: `factory` is a module-level function of the door (never a
//                   closure over the door's render scope) and `args` are plain arguments without
//                   DOM, opener, onOpen or currency callbacks. `pin` is small reopen state the
//                   door sets through pin(token, …): the exact owner URL and cut displayed, or
//                   the PDF's last reading position.
//   BACK            back(), the injected 'Back to <title>' control, or Close/Esc on a nested
//                   panel: the current panel is closed as REPLACED and the previous entry's
//                   factory(args, pin) runs. A reopen never pushes the panel it replaces.
//   GENUINE CLOSE   Close/Esc on the trail's ROOT: the trail is cleared and focus and scroll
//                   return to the opener recorded when the trail started (held weakly).
//   DESTINATION     closeTo(token, callback) explicitly leaves the current inspection. Its
//                   close owner clears opener/trail before invoking the scoped callback once;
//                   it does not also restore the old opener. Replacement cancels the handoff.
//   STALE ASYNC     a read that completes after its panel was replaced or closed must neither
//                   render nor reopen anything. Doors ask lineage(token) for the predicate a
//                   nested read is bound to: TRUE while the token is current OR on the trail
//                   (replaced by a child it can return to), FALSE after a genuine close. The
//                   predicate captures the token string only. A door's own `closed` flag must
//                   never be a child's currency: replacement would falsify it.
//   RESOURCES       nothing the inspector retains after replacement references a disposed
//                   dialog or its render scope: entries hold token/kind/title/descriptor/pin,
//                   the close listener holds the entry (whose dialog is dropped), the opener is
//                   a WeakRef. tests/helpers/inspector_retention_probe.mjs proves it with an
//                   actual door, a 1,000,000-character payload and a forced GC.
//
// ─ SNAPSHOTS ──────────────────────────────────────────────────────────────────────────────
//   An owner JSON payload read by a door is remembered under URL + the payload's cut
//   (payloadCut: read_cut.revision | read_cut | as_of | index_stamp | summary_revision |
//   revision | version). A reopen from the trail asks for the entry's PINNED url+cut, so Back
//   shows what was inspected, never the latest cut of the same URL. The door says
//   "Previously inspected · HH:MM" with Read current and exact provenance on demand; cached
//   panels are read-only. A first read never consults the cache; live build status, artifact
//   bytes and PDFs are never stored.
// ─ BOUNDS ─────────────────────────────────────────────────────────────────────────────────
//   SNAPSHOT_LIMIT entries (LRU), SNAPSHOT_BYTES of serialized UTF-8 per entry, TRAIL_LIMIT
//   entries; trail entries hold no DOM (dialog released on replacement) and reopen descriptors
//   are the door's own small argument objects without opener/onOpen references.
// The inspector owns no truth and never fetches.
export const INSPECTOR_CACHE_LIMIT=12, INSPECTOR_TRAIL_LIMIT=24, INSPECTOR_SNAPSHOT_BYTES=64*1024;
export const INSPECTOR_KINDS=['artifact','owner-read','pdf','saved-turn','help-diagram','panel'];
const encoder=new TextEncoder();
export const utf8Bytes=value=>{try{return encoder.encode(JSON.stringify(value)).length;}catch{return Infinity;}};

export function payloadCut(value){
  if(!value||typeof value!=='object')return null;
  const cut=value.read_cut;
  if(cut&&typeof cut==='object'){for(const key of ['revision','cut','digest'])if(typeof cut[key]==='string'&&cut[key])return cut[key];}
  for(const key of ['read_cut','as_of','index_stamp','summary_revision','revision','version'])if(typeof value[key]==='string'&&value[key])return value[key];
  return null;
}

export function createInspector({page:fixedPage=null,limit=INSPECTOR_CACHE_LIMIT,trailLimit=INSPECTOR_TRAIL_LIMIT,snapshotBytes=INSPECTOR_SNAPSHOT_BYTES,clock=()=>new Date().toISOString()}={}){
  const snapshots=new Map();   // key: url + '\u0000' + cut → {url,cut,value,at,bytes,sequence}
  let current=null,trail=[],opener=null,qualifiedOpener=null,scrollOwners=[],returnCancelled=false,returnCleanup=null,pendingReturn=null,sequence=0,tokens=0;
  const weak=node=>node?(typeof WeakRef==='function'?new WeakRef(node):{deref:()=>node}):null;
  const doc=()=>fixedPage||globalThis.document;   // resolved per call: the shared instance outlives a page's document in tests
  const closeForms=(except=null)=>{const page=doc();for(const dialog of page?.querySelectorAll?.('dialog[open]')||[])if(dialog!==except&&!dialog.dataset?.inspector)dialog.close?.();};
  const qualifiedTarget=()=>{const root=qualifiedOpener?.root?.deref();return root?.isConnected!==false&&qualifiedOpener&&qualifiedOpener.isCurrent()?focusTarget(root,qualifiedOpener.coordinate):null;};
  const clearReturn=()=>{returnCleanup?.();returnCleanup=null;opener=null;qualifiedOpener=null;scrollOwners=[];returnCancelled=false;};
  const recordOpener=returnFocus=>{if(current||trail.length)return;const page=doc();const active=page?.activeElement;const node=active&&active!==page?.body?active:null;opener=weak(node);qualifiedOpener=returnFocus?.root&&returnFocus.coordinate?{root:weak(returnFocus.root),coordinate:structuredClone(returnFocus.coordinate),isCurrent:returnFocus.isCurrent||(()=>true)}:null;returnCancelled=false;scrollOwners=[];for(let owner=node;owner;owner=owner.parentElement)if(owner.scrollTop||owner.scrollLeft)scrollOwners.push([weak(owner),owner.scrollTop,owner.scrollLeft]);
    if(qualifiedOpener){const gesture=event=>{if(!current?.dialog?.contains?.(event.target))returnCancelled=true;},focused=event=>{const target=qualifiedTarget(),at=event.target;if(at===page.body||current?.dialog?.contains?.(at)||at?.isConnected===false||at===opener?.deref()||target&&(at===target||at?.contains?.(target)))return;returnCancelled=true;};page.addEventListener?.('pointerdown',gesture,true);page.addEventListener?.('keydown',gesture,true);page.addEventListener?.('focusin',focused,true);returnCleanup=()=>{page.removeEventListener?.('pointerdown',gesture,true);page.removeEventListener?.('keydown',gesture,true);page.removeEventListener?.('focusin',focused,true);};}
  };
  const restore=(closedDialog=null)=>{const prior=opener?.deref(),admitted=!qualifiedOpener||qualifiedOpener.isCurrent(),target=qualifiedTarget(),active=doc()?.activeElement;if(admitted&&!returnCancelled)for(const [ref,top,left]of scrollOwners){const node=ref?.deref();if(node&&node.isConnected!==false){node.scrollTop=top;node.scrollLeft=left;}}const node=admitted&&!returnCancelled?(target||prior):null;
    // Native dialog Close can restore a surviving project ancestor after a
    // nested reading was rebuilt. That fallback is not a new author intent.
    const nativeFallback=target&&active?.contains?.(target);
    if(node&&node.isConnected!==false&&!node.disabled&&(!qualifiedOpener||active===doc()?.body||active===prior||active===target||nativeFallback||closedDialog?.contains?.(active)||active?.isConnected===false))node.focus?.({preventScroll:true});clearReturn();};
  // REPLACED: close the dialog as replaced and release it; the entry keeps only metadata
  const release=entry=>{const dialog=entry.dialog;entry.replaced=true;entry.dialog=null;entry.destination=null;entry.destinationCleanup?.();entry.destinationCleanup=null;if(!dialog)return;if(dialog.dataset)dialog.dataset.inspectorReplaced='true';dialog.close?.();};
  const descriptor=entry=>({token:entry.token,kind:entry.kind,title:entry.title,reopen:entry.reopen,pin:entry.pin});
  const onTrail=token=>trail.some(entry=>entry.token===token);
  function remember(url,value){
    if(typeof url!=='string'||!url||value==null||typeof value!=='object')return false;
    const bytes=utf8Bytes(value);if(bytes>snapshotBytes)return false;
    const cut=payloadCut(value),key=url+'\u0000'+(cut??'');
    snapshots.delete(key);snapshots.set(key,{url,cut,value,at:clock(),bytes,sequence:++sequence});
    while(snapshots.size>limit)snapshots.delete(snapshots.keys().next().value);
    return true;
  }
  function snapshot(url,cut=null){
    let entry=null;
    if(cut!=null)entry=snapshots.get(url+'\u0000'+cut)||null;
    else for(const candidate of snapshots.values())if(candidate.url===url&&(!entry||candidate.sequence>entry.sequence))entry=candidate;   // the most recently REMEMBERED cut for this URL
    if(!entry)return null;
    const key=entry.url+'\u0000'+(entry.cut??'');snapshots.delete(key);snapshots.set(key,entry);
    return {url:entry.url,cut:entry.cut,at:entry.at,bytes:entry.bytes,value:entry.value};
  }
  const cached=(url,cut=null)=>snapshot(url,cut)?.value;
  const invoke=(reopen,pin)=>typeof reopen==='function'?reopen(pin):reopen.factory(reopen.args,pin);   // a descriptor {factory,args}, or a plain function for tests
  const runReopen=previous=>{pendingReturn=previous;let result;try{result=invoke(previous.reopen,previous.pin);}catch(error){pendingReturn=null;throw error;}Promise.resolve(result).catch(()=>{}).finally(()=>{if(pendingReturn===previous)pendingReturn=null;});return result;};
  // BACK
  function back(){const previous=trail.pop();if(!previous)return false;const entry=current;current=null;if(entry)release(entry);return runReopen(previous);}
  // OPEN
  function adopt(dialog,{kind='panel',title='Reading',reopen=null,returnFocus=null}={}){
    if(!dialog)throw Error('The inspector adopts an existing dialog.');
    if(reopen&&typeof reopen!=='function'&&(typeof reopen.factory!=='function'||reopen.args===undefined))throw Error('A reopen descriptor is {factory, args}.');
    if(current&&current.dialog===dialog)return {back,depth:trail.length,adopted:false,token:current.token};   // idempotent: a door and its caller may both adopt
    const returning=pendingReturn;pendingReturn=null;
    closeForms(dialog);if(!returning)recordOpener(returnFocus);
    if(current&&current.dialog!==dialog){const previous=current;current=null;if(!returning&&previous.reopen){trail.push(descriptor(previous));while(trail.length>trailLimit)trail.shift();}release(previous);}
    const entry={token:'ins-'+(++tokens),dialog,kind,title,reopen,pin:returning?.pin||null,replaced:false,destination:null,destinationCleanup:null};current=entry;
    if(dialog.dataset){dialog.dataset.inspector=kind;dialog.dataset.inspectorDepth=String(trail.length);dialog.dataset.inspectorToken=entry.token;}
    dialog.classList?.add?.('workspace-inspector');
    if(trail.length&&doc()?.createElement){const previous=trail.at(-1),control=doc().createElement('button');control.type='button';control.className='inspector-back';control.textContent='Back to '+previous.title;control.setAttribute?.('aria-label','Back to '+previous.title);control.onclick=()=>back();dialog.prepend?.(control);}
    // GENUINE CLOSE (root) or Back (nested); a replaced dialog's close is ignored here.
    // The listener captures the entry only (its dialog is dropped on replacement), never the dialog.
    const onClose=()=>{if(current!==entry)return;current=null;if(entry.replaced)return;const closedDialog=entry.dialog;entry.dialog=null;
      if(entry.destination){const destination=entry.destination;entry.destination=null;trail=[];clearReturn();pendingReturn=null;
        try{Promise.resolve(destination()).catch(error=>console.warn('Inspector destination unavailable:',error.message));}catch(error){console.warn('Inspector destination unavailable:',error.message);}return;}
      if(trail.length){runReopen(trail.pop());return;}restore(closedDialog);};
    if(typeof dialog.addEventListener==='function')dialog.addEventListener('close',onClose,{once:true});
    else{const prior=dialog.onclose;dialog.onclose=(...args)=>{prior?.(...args);onClose();};}   // a door that only sets onclose (and the test DOM doubles)
    return {back,depth:trail.length,adopted:true,token:entry.token};
  }
  // small reopen state carried by the token's entry: the exact owner URL + cut displayed, or a position
  // a lifetime handle is the token string or a small plain {token} holder a door fills at adoption
  const keyOf=handle=>String((handle&&typeof handle==='object'?handle.token:handle)||'');
  // An explicit domain return consumes this current dialog once. Its close event
  // settles this owner before handoff, instead of restoring the old opener/trail.
  // Replacement or Back cancels the armed destination; ordinary callers are unchanged.
  function closeTo(handle,destination){
    if(typeof destination!=='function')throw Error('An inspector destination is a scoped callback.');
    if(!current||current.token!==keyOf(handle)||!current.dialog||current.dialog.open===false||current.destination)return false;
    const entry=current,page=doc();let closing=true,cancelled=false;
    const gesture=()=>{cancelled=true;},focus=event=>{if(!closing&&event.target!==page?.body)cancelled=true;};
    const cleanup=()=>{page?.removeEventListener?.('pointerdown',gesture,true);page?.removeEventListener?.('keydown',gesture,true);page?.removeEventListener?.('focusin',focus,true);entry.destinationCleanup=null;};
    page?.addEventListener?.('pointerdown',gesture,true);page?.addEventListener?.('keydown',gesture,true);page?.addEventListener?.('focusin',focus,true);
    entry.destinationCleanup=cleanup;entry.destination=()=>{cleanup();if(!cancelled)return destination();};
    // close() performs native opener focus synchronously; later author intent before
    // its queued close event still cancels the destination, without restoring the opener.
    try{entry.dialog.close();}catch(error){entry.destination=null;cleanup();throw error;}finally{closing=false;}return true;
  }
  function pin(handle,value){const token=keyOf(handle);if(current&&current.token===token)current.pin=value||null;else for(const entry of trail)if(entry.token===token)entry.pin=value||null;return value||null;}
  // STALE ASYNC: the predicate a nested read is bound to; it captures the handle only (string or {token}), never DOM
  function lineage(handle){return ()=>{const key=keyOf(handle);return !!key&&((current?.token===key)||onTrail(key));};}
  const wasReplaced=dialog=>dialog?.dataset?.inspectorReplaced==='true';
  const tokenOf=dialog=>dialog?.dataset?.inspectorToken||null;
  function panel({kind='panel',title,render,label=title}){
    const open=()=>{const page=doc();const dialog=page.createElement('dialog');dialog.className='workspace-dialog inspector-panel';dialog.setAttribute('aria-label',label);const heading=page.createElement('h2');heading.textContent=title;const close=page.createElement('button');close.type='button';close.className='inspector-close';close.textContent='Close';close.onclick=()=>dialog.close();const body=page.createElement('div');body.className='inspector-body';dialog.append(heading,close,body);dialog.onclose=()=>dialog.remove();page.body.append(dialog);adopt(dialog,{kind,title,reopen:open});dialog.showModal?.();const result=render(body,{dialog,inspector:api});return Promise.resolve(result).then(()=>dialog);};
    return open();
  }
  const api={adopt,back,closeTo,panel,remember,snapshot,cached,closeForms,pin,lineage,wasReplaced,tokenOf,
    get current(){return current?{kind:current.kind,title:current.title,dialog:current.dialog,token:current.token,pin:current.pin}:null;},
    get trail(){return trail.map(entry=>({kind:entry.kind,title:entry.title,pin:entry.pin,retainsDialog:'dialog' in entry,descriptor:typeof entry.reopen==='function'?'function':'factory'}));},
    get cacheSize(){return snapshots.size;},
    get cacheLimit(){return limit;},
    get snapshotBytes(){return snapshotBytes;}};
  return api;
}

// The one instance per document the shell and every door share. Tests reset it between cases.
export function sharedInspector(options){
  const scope=globalThis;
  if(!scope.laplaceInspector||scope.laplaceInspectorDocument!==scope.document){scope.laplaceInspector=createInspector(options);scope.laplaceInspectorDocument=scope.document;}
  return scope.laplaceInspector;
}
export function resetSharedInspector(){delete globalThis.laplaceInspector;delete globalThis.laplaceInspectorDocument;}
// A door's own close handler must not return focus when the inspector replaced the dialog.
export const replacedByInspector=dialog=>dialog?.dataset?.inspectorReplaced==='true';
