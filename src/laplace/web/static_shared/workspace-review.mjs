// workspace-review.mjs — Review: proposals, versions, comments and notes (M5 C9).
// Ownership: /authoring/proposals (queue and history, cut-pinned pages: createProjectReview is
//   the one project-lifetime observation views subscribe to), /authoring/history (notes and
//   comments by category, offset/limit, as_of), /authoring/correction and correction-status
//   (writes with base_revision).
// Tabs: Proposed, Versions, Comments, Notes, Closed (Global and Other notes when they have
//   rows). Saved manuscript edits are Activity records (C5): Review renders no saved-edit
//   cards and has no applied-edits category; one sentence points to Activity · Changes.
// Public contract: mountReview(host,options) -> {focusCorrection, refresh, showProposals,
//   setActive, destroy, hasDraft}; createProjectReview; proposalStandingLabel.
// Currentness: queue pages refuse a changed cut; a selected saved comparison is retained while
//   the queue refreshes; focus/visibility/storage/reconnected events trigger passive refreshes.
// Storage: localStorage laplace:proposal-update:<project> (a settled-decision nonce another
//   frame listens for through the storage event).
import {historyTime} from './workspace-history.mjs';
import {proposalReadURL} from './manuscript-editing.mjs';
import {scientificText} from '/shared/concept-reader.mjs';
const el=(tag,text='',cls='')=>{const n=document.createElement(tag);n.textContent=text;n.className=cls;return n;};
import {declareControl} from './workspace-presentation.mjs';
function styles(){if(document.querySelector('[data-writing-workflows]'))return;const css=el('link');css.rel='stylesheet';css.href='/shared/workspace-workflows.css';css.dataset.writingWorkflows='';document.head.append(css);}
// THE REVIEW TABS (M5 C9, plan §5 review): Proposed, Versions, Comments, Notes, Closed (Global
// and Other notes appear when they have rows). Saved manuscript edits are Activity records
// (C5): Review carries no saved-edit cards and no applied-edits category.
const FILTERS={open:{label:'Comments',correction_category:'passage-comments',status:'open'},notes:{label:'Notes',correction_category:'project-notes',status:'open'},global:{label:'Global notes',correction_category:'global-notes',status:'open'},other:{label:'Other notes',correction_category:'other',status:'open'},closed:{label:'Closed',correction_category:'notes',status:'closed'},proposals:{label:'Proposed'},'proposal-history':{label:'Versions'}};
const anchor=row=>{const a={...(row.anchor||{})};if(Array.isArray(a.lines)){a.line_start??=a.lines[0];a.line_end??=a.lines[1];}return a;};
const isEdit=row=>row.correction_category==='applied-edits';
export function proposalStandingLabel(row={}){
  const state=row.proposal_state;
  if(['ready','pending'].includes(state))return 'Awaiting exact comparison';
  if(state==='resolved-into-successor')return 'Resolved in a later revision';
  if(['conflict','blocked'].includes(state))return 'Needs reconciliation';
  return state||'Saved candidate';
}
// One project-lifetime owner observation. Views subscribe; they do not read or infer queue state.
export function createProjectReview({project,request,onReviewProposal,status=()=>{},events=globalThis.window,document:page=globalThis.document,isAlive=()=>true}){
  let data=null,error='',loading=false,disposed=false,generation=0,selection=null,collection={view:'queue'},pending=null,chain=Promise.resolve(),checkedAt=0;
  const listeners=new Set(),key='laplace:proposal-update:'+project;
  const snapshot=()=>({data,error,loading,selection,collection:{...collection}});
  const emit=()=>{if(!disposed&&isAlive())for(const listener of listeners)listener(snapshot());};
  function read({refresh=false,handle=null,view=collection.view,turnId=collection.turn_id,supersede=false}={}){
    if(disposed||!isAlive())return Promise.resolve(null);
    const scope={view,...(turnId?{turn_id:turnId}:{})},same=JSON.stringify(scope)===JSON.stringify(collection);
    if(!refresh&&!handle&&same&&data&&!error)return Promise.resolve(data);
    if(pending&&!supersede&&same&&!handle)return pending;
    const previous=data,path=handle?proposalReadURL(handle,{project,queue:true}):'/authoring/proposals?'+new URLSearchParams({project,...scope});
    if(handle){const q=new URL(path,'http://localhost').searchParams;if(q.get('view')!==scope.view||(q.get('turn_id')||'')!==(scope.turn_id||'')||!previous?.as_of)throw Error('Proposal continuation changed the selected collection. Refresh Review.');}
    const token=++generation;if(!same)data=null;collection=scope;loading=true;error='';checkedAt=Date.now();emit();
    const operation=chain.catch(()=>{}).then(async()=>{
      if(disposed||!isAlive()||token!==generation)return null;
      try{
        const next=await request(path);
        if(disposed||!isAlive()||token!==generation)return null;
        if(next.project!==project||next.view!==scope.view||!Array.isArray(next.proposals)||!next.as_of)throw Error('Proposal queue returned different or incomplete owner coordinates.');
        if(handle&&next.as_of!==previous.as_of)throw Error('Proposal owner cut changed between pages. Refresh Review; pages were not mixed.');
        const rows=handle?[...previous.proposals,...next.proposals]:next.proposals,seen=new Set();
        for(const row of rows){if(row.project!==project||!row.id||!row.proposal_version||!row.read_handle)throw Error('Proposal row has no exact project/version read handle.');proposalReadURL(row.read_handle,{project,turnId:row.id,version:row.proposal_version});const id=row.id+'::'+row.proposal_version;if(seen.has(id))throw Error('Proposal page repeats an exact candidate. Refresh Review.');seen.add(id);}
        const coverage=handle?(Array.isArray(previous?.coverage?.unavailable_candidate_records)&&Array.isArray(next.coverage?.unavailable_candidate_records)?{...next.coverage,unavailable_candidate_records:[...new Set([...previous.coverage.unavailable_candidate_records,...next.coverage.unavailable_candidate_records])]}:undefined):next.coverage;
        data={...next,proposals:rows,coverage};return data;
      }catch(err){if(!disposed&&isAlive()&&token===generation){error=err.message;throw err;}return null;}
      finally{if(!disposed&&isAlive()&&token===generation){loading=false;emit();}}
    });
    chain=operation;pending=operation;operation.finally(()=>{if(pending===operation)pending=null;}).catch(()=>{});return operation;
  }
  const passive=()=>{if(page?.visibilityState==='hidden'||Date.now()-checkedAt<4000)return;read({refresh:true}).catch(err=>status('Project Review could not refresh: '+err.message,true));};
  const storage=event=>{if(event.key===key&&page?.visibilityState!=='hidden')read({refresh:true,supersede:true}).catch(err=>status('Project Review could not refresh: '+err.message,true));};
  const reconnect=()=>{if(page?.visibilityState!=='hidden')read({refresh:true,supersede:true}).catch(err=>status('Project Review could not refresh: '+err.message,true));};
  events?.addEventListener?.('focus',passive);events?.addEventListener?.('storage',storage);events?.addEventListener?.('laplace-workspace-reconnected',reconnect);page?.addEventListener?.('visibilitychange',passive);
  return {snapshot,read,subscribe(listener){listeners.add(listener);return ()=>listeners.delete(listener);},
    more(){return data?.pagination?.next_read?read({handle:data.pagination.next_read}):Promise.resolve(data);},
    async open(turnId,{proposalVersion,readHandle,readOnly=false,decision=false}={}){
      if(!proposalVersion||!readHandle)throw Error('Choose an exact saved version in project Review before opening its comparison.');
      proposalReadURL(readHandle,{project,turnId,version:proposalVersion});
      selection=JSON.parse(JSON.stringify({turnId,proposalVersion,readHandle,readOnly}));emit();
      // decision:true is the explicit human-decision capability (feedback responses); a host whose review callback
      // only inspects (the writing panel's saved comparisons) keeps inspecting every other open
      return onReviewProposal(turnId,{proposalVersion,readHandle:selection.readHandle,readOnly,...(decision===true&&!readOnly?{decision:true}:{})});
    },
    async settled(){try{globalThis.localStorage?.setItem(key,JSON.stringify({at:Date.now(),nonce:Math.random()}));}catch{/* Owner focus refresh remains available. */}try{return await read({refresh:true,supersede:true});}catch(err){status('Decision or reply recorded; project Review refresh is unavailable: '+err.message+' Reinspect; do not repeat the effect.',true);return null;}},
    destroy(){disposed=true;generation++;listeners.clear();events?.removeEventListener?.('focus',passive);events?.removeEventListener?.('storage',storage);events?.removeEventListener?.('laplace-workspace-reconnected',reconnect);page?.removeEventListener?.('visibilitychange',passive);}
  };
}
export async function mountReview(host,options){
  styles();const {project,request,status=()=>{},onOpenPassage,onReviewProposal,onDiscuss,onDirty=()=>{}}=options;
  const queue=options.proposalController||createProjectReview({project,request,onReviewProposal,status}),ownsQueue=!options.proposalController;
  host.classList.add('workspace-review');let active=true,page={items:[],counts:{}},proposals={count:0,proposals:[]},filter=options.initialFilter||'proposals',offset=0,cut='',focus=null,error='',generation=0,disposed=false,returnPosition=null;
  const drafts=new Map(),draftHost=el('section','','review-drafts');
  const run=fn=>async()=>{try{await fn();}catch(err){status(err.message,true);}};
  const button=(label,fn,cls='',id=null,owner=null)=>{const b=el('button',label,cls);if(id)declareControl(b,id,owner);b.type='button';b.onclick=run(async()=>{b.disabled=true;try{await fn();}finally{b.disabled=false;}});return b;};
  const syncDirty=()=>onDirty([...drafts.values()].some(form=>!!form.querySelector('textarea')?.value));
  function forgetDraft(key){drafts.get(key)?.remove();drafts.delete(key);syncDirty();}
  async function read({refresh=false}={}){
    const token=++generation;if(refresh){cut='';offset=0;}error='';
    const selected=FILTERS[filter];
    try{
      const proposalFilter=['proposals','proposal-history'].includes(filter);
      const pending=await queue.read({refresh,view:filter==='proposal-history'?'history':'queue',turnId:filter==='proposal-history'?options.proposalTurnId:null});
      if(disposed||token!==generation)return;
      let result=page;
      if(!proposalFilter)result=await request('/authoring/history?'+new URLSearchParams({project,order:'newest',offset:String(offset),limit:'20',...(cut?{as_of:cut}:{}),...Object.fromEntries(Object.entries(selected).filter(([key])=>key!=='label'))}));
      if(disposed||host.isConnected===false||token!==generation)return;page=result;proposals=pending||queue.snapshot().data||{proposals:[]};cut=result.as_of;page.items=(result.items||[]).map(row=>({...row,_revision:result.revision}));await paint(token);
    }catch(err){if(disposed||host.isConnected===false||token!==generation)return;error=err.message;status(error,true);await paint(token);}
  }
  async function exactRow(row){
    if(row._exact)return row;const value=await request('/authoring/history?'+new URLSearchParams({project,id:row.id}));
    if(disposed||host.isConnected===false)throw Error('The review page was closed. Your note was not changed.');
    return {...value.item,_revision:value.revision,_exact:true};
  }
  async function focusId(id){
    const token=++generation;offset=page.offset||0;if(!focus)returnPosition={host:host.scrollTop||0,window:globalThis.window?.scrollY||0};
    try{const result=await request('/authoring/history?'+new URLSearchParams({project,id}));if(disposed||host.isConnected===false||token!==generation)return;focus={...result.item,_revision:result.revision,_exact:true};await paint(token);const target=[...host.querySelectorAll('[data-correction-id]')].find(node=>node.dataset.correctionId===id);if(target){target.tabIndex=-1;target.focus({preventScroll:true});target.scrollIntoView({block:'nearest'});}}
    catch(err){if(disposed||host.isConnected===false||token!==generation)return;status(err.message,true);}
  }
  function openDraft(row=null){
    const key=row?'reply:'+row.id:'new-note';if(drafts.has(key)){drafts.get(key).querySelector('textarea').focus();return;}
    let baseRevision=row?row._revision:page.revision;const form=el('form','','review-item'),input=el('textarea'),save=declareControl(el('button',row?'Save reply':'Save note','primary'),'review:note-save');
    form.append(el('h3',row?'Reply to note '+row.id:'Project note'));if(row){form.append(el('p',row.text||''));const passage=anchor(row).quote||anchor(row).passage_before;if(passage)form.append(el('blockquote',passage));}input.rows=row?3:4;input.required=true;input.setAttribute('aria-label',row?'Reply to comment':'New project note');input.oninput=syncDirty;form.append(input,save,button('Cancel',()=>forgetDraft(key),'','review:note-cancel'),button('Review current save revision',async()=>{const current=await request('/authoring/history?'+new URLSearchParams({project,...(row?{id:row.id}:{limit:'1'})}));const review=el('section','','review-item');review.append(el('p',row?current.item.text:'Current project revision '+current.revision),button('Use reviewed revision for this draft',()=>{baseRevision=current.revision;review.remove();status('This draft now uses the explicitly reviewed revision.');},'','review:note-use-revision'));form.append(review);},'','review:note-review-revision'));drafts.set(key,form);draftHost.append(form);input.focus();
    form.onsubmit=async event=>{event.preventDefault();if(save.disabled)return;save.disabled=input.disabled=true;
      try{const saved=await request('/authoring/correction',{project,text:input.value,kind:'note',scope:row?.scope==='passage'?'passage':'project',base_revision:baseRevision,...(row?{anchor:anchor(row),reply_to:row.id}:{}),by:'author'});forgetDraft(key);focus=null;if(!row)filter='notes';await read({refresh:true});status(row?(saved.correction?.reply_to===row.id?'Reply saved. The original note remains in the discussion.':'Follow-up note saved. This running engine did not retain the reply link; the original note was not replaced.'):'Project note saved.',!!row&&saved.correction?.reply_to!==row.id);}
      catch(err){status(err.message+' Your draft is retained. Review the current save revision before retrying a stale revision.',true);}finally{save.disabled=input.disabled=false;}
    };
  }
  async function setStatus(row,next){await request('/authoring/correction-status',{project,id:row.id,status:next,base_revision:row._revision,...(row.status==='superseded'&&next==='open'?{note:'Author reopened this superseded note; its replacement and prior history remain available.'}:{})});focus=null;await read({refresh:true});}
  function count(id){if(['proposals','proposal-history'].includes(id))return queue.snapshot().collection.view===(id==='proposals'?'queue':'history')?proposals.proposals?.length||0:null;if(!page.counts||!Object.keys(page.counts).length)return null;const rule=FILTERS[id];return Object.entries(page.counts||{}).reduce((total,[category,statuses])=>{if(rule.correction_category==='notes'?category==='applied-edits':category!==rule.correction_category)return total;return total+Object.entries(statuses).reduce((n,[state,value])=>n+((rule.status==='closed'?state!=='open':!rule.status||state===rule.status)?value:0),0);},0);}
  async function card(row){
    const a=anchor(row),node=el('article','','review-item');node.dataset.correctionId=row.id;
    const heading=el('div','','review-item-heading');heading.append(el('h3',isEdit(row)?'Saved manuscript edit':row.reply_to?'Reply':row.scope==='project'?'Project note':row.scope==='global'?'Global note':'Passage comment'),el('span',isEdit(row)?'Already applied':row.status||'Open','workflow-state'));node.append(heading);
    // C5: an applied edit is one Activity record; its card here is a compact pointer (heading,
    // passage, Review change / Inspect) and never repeats the hunks, text or status history
    if(!isEdit(row)){const text=el('div','','review-comment-text');await scientificText(text,row.text||'');node.append(text);
    if(row.text_truncated)node.append(el('p','Text preview · open the full note to read the remainder.','muted'));}
    else node.append(el('p','Recorded in Activity (manuscript changes) with its exact hunks and byte identities.','muted'));
    if(row.reply_to)node.append(button('Reply to note '+row.reply_to,()=>focusId(row.reply_to),'','review:record-reply-to',project+'::'+row.id));
    const quote=a.quote||a.passage_before;if(quote&&!isEdit(row))node.append(el('blockquote',quote));
    node.append(el('p',[a.file,a.section||a.section_id].filter(Boolean).join(' · '),'muted'));
    const actions=el('div','','workflow-actions');actions.append(button('Inspect full record',()=>focusId(row.id),'','review:record-inspect',project+'::'+row.id));if(a.file)actions.append(button('Open passage',async()=>{const exact=await exactRow(row);onOpenPassage(anchor(exact));},'','review:record-open-passage',project+'::'+row.id));
    if(row.origin_ref){const responses=button(row.has_review_route?'Review responses':'Request reviews',async()=>{const {openFeedbackRouteForOrigin}=await import('./feedback-route.mjs');return openFeedbackRouteForOrigin({project,origin:row.origin_ref,request,isCurrent:()=>!disposed&&host.isConnected!==false,openProposal:(turnId,choice)=>queue.open(turnId,choice)});});responses.dataset.control='review:responses';responses.dataset.controlOwner=project+'::'+row.id;actions.append(responses);}
    if(!isEdit(row)&&row.scope!=='global'){
      if((row.status||'open')==='open'){actions.append(button('Address with Eigen',async()=>{const detail=await exactRow(row);onDiscuss(`Address comment ${row.id}: ${detail.text}\nRead its current passage and relevant dependencies first; make the requested change or explain the unresolved issue.`,anchor(detail));},'','review:record-address',project+'::'+row.id),button('Resolve',()=>setStatus(row,'resolved'),'','review:record-resolve',project+'::'+row.id),button('Dismiss',()=>setStatus(row,'dismissed'),'','review:record-dismiss',project+'::'+row.id),button('Reply',async()=>openDraft(await exactRow(row)),'','review:record-reply',project+'::'+row.id));}
      else if(['resolved','dismissed','superseded'].includes(row.status))actions.append(button(row.status==='superseded'?'Reopen superseded note':'Reopen',()=>setStatus(row,'open'),'','review:record-reopen',project+'::'+row.id));
    }
    node.append(actions);if(isEdit(row)&&a.file)node.append(button('Review change in manuscript',()=>onOpenPassage({...a,correction_id:row.id,show_changes:true}),'primary','review:record-change',project+'::'+row.id));
    if(row.status_history?.length&&!isEdit(row)){const history=el('details');history.append(declareControl(el('summary','Status history'),'review:record-history',project+'::'+row.id));for(const event of row.status_history)history.append(el('p',[event.status,event.at,event.by,event.note].filter(Boolean).join(' · ')));node.append(history);}
    node.append(el('small',[row.by,row.created].filter(Boolean).join(' · '),'muted'));return node;
  }
  async function paint(token=generation){
    const content=el('section');content.append(el('h2','Review & notes'));const nav=el('div','','workflow-filters');nav.setAttribute('role','tablist');
    for(const id of ['proposals','proposal-history','open','notes','closed','global','other']){if(['global','other'].includes(id)&&!count(id)&&filter!==id)continue;const b=declareControl(button(`${FILTERS[id].label}${count(id)==null?'':(['proposals','proposal-history'].includes(id)?' · '+count(id)+' candidates inspected':' · '+count(id))}`,async()=>{filter=id;focus=null;offset=0;await read();}),'review:filter',id);b.setAttribute('role','tab');b.setAttribute('aria-selected',String(filter===id));nav.append(b);}content.append(nav);
    const controls=el('div','','workflow-actions');controls.append(declareControl(button('Refresh review',async()=>{focus=null;await read({refresh:true});}),'review:refresh'));content.append(controls,el('p','Saved manuscript edits are recorded in Activity · Changes with their exact hunks.','muted'));
    const selected=queue.snapshot().selection;if(selected){const provenance=el('details');provenance.append(el('summary','Selected comparison provenance'),el('p','Turn '+selected.turnId),el('p','Version '+selected.proposalVersion));content.append(el('p','Your selected saved comparison is retained while the queue refreshes.','muted'),button('Return to selected saved comparison',()=>queue.open(selected.turnId,selected)),provenance);}
    if(error){content.append(el('p',error,'workflow-error'),button('Retry this page',()=>read(),'','review:retry'));}
    else if(focus){if(focus._revision!==page.revision)content.append(el('p','This record is current. The retained review page belongs to an earlier snapshot; refresh it for current counts.','muted'));content.append(button('Back to review page',async()=>{focus=null;await paint();if(returnPosition){host.scrollTop=returnPosition.host;globalThis.window?.scrollTo?.(0,returnPosition.window);}},'','review:back'),await card(focus));}
    else if(['proposals','proposal-history'].includes(filter)){if(queue.snapshot().loading)content.append(el('p','Reading the project proposal owner…','muted'));if(!queue.snapshot().loading&&!proposals.proposals?.length)content.append(el('p',proposals.pagination?.remaining_candidates===0&&Array.isArray(proposals.coverage?.unavailable_candidate_records)&&!proposals.coverage.unavailable_candidate_records.length?(filter==='proposal-history'?'No saved candidate versions in this inspected scope.':'No manuscript changes are waiting for your decision.'):(proposals.coverage?.unavailable_candidate_records?.length?'No candidates were returned; some candidate records are unavailable.':(filter==='proposal-history'?'No saved candidate versions on this inspected page.':'No pending candidates on this inspected page.')),'workflow-empty'));for(const item of proposals.proposals||[]){const row=el('article','','review-item');row.append(el('h3',item.proposal_label||'Manuscript proposal','review-proposal-title'),el('p',`${item.edit_count} recorded edits · ${(item.files||[]).join(', ')}`,'muted'),el('p',historyTime(item.turn_ts,{date:true})+' · '+historyTime(item.turn_ts)+' · Version '+String(item.proposal_version||'unrecorded').slice(0,16)+' · '+proposalStandingLabel(item),'muted'),button(options.proposalActionLabel||'Review in manuscript',()=>queue.open(item.id,{proposalVersion:item.proposal_version,readHandle:item.read_handle}),'primary','review:proposal-open',project+'::'+item.id));const provenance=el('details');provenance.append(declareControl(el('summary','Provenance'),'review:proposal-provenance',project+'::'+item.id),el('p','Conversation: '+(item.conversation_title||item.session_id||'unavailable')),el('p',(item.candidate_ref?'Candidate ':'Turn ')+item.id),el('p','Recorded candidate state: '+(item.proposal_state||'not reported')),el('p','Version '+item.proposal_version),el('p','Label basis: '+(item.label_basis||'unavailable')),el('p','Recorded at '+(item.turn_ts||'unavailable')));if(options.onReadTurn)provenance.append(button('Read originating turn',()=>options.onReadTurn(item.id)));if(item.label_truncated){row.append(el('small','Label shortened · full context in Provenance','muted'));provenance.append(el('p','Stored context label truncated; the exact originating turn retains the full value.','muted'));}row.append(provenance);content.append(row);}if(proposals.count_basis)content.append(el('p','Inspected '+proposals.proposals.length+' rows · '+proposals.count_basis,'muted'));if(proposals.pagination?.next_read)content.append(button('Inspect more proposal candidates',()=>queue.more(),'','review:proposal-more'));}
    else{content.append(el('p',`${page.total||0} records · showing ${page.items.length?offset+1:0}–${offset+page.items.length}`,'muted'));if(!page.items.length)content.append(el('p','No records in this review category.','workflow-empty'));for(const row of page.items)content.append(await card(row));const paging=el('div','','workflow-actions');if(offset>0)paging.append(button('Previous records',async()=>{offset=Math.max(0,offset-20);await read();},'','review:previous'));if(page.next_offset!=null)paging.append(button('More records',async()=>{offset=page.next_offset;await read();},'','review:more'));content.append(paging);}
    if(options.allowNewNote!==false&&page.revision!=null)content.append(button('New project note',()=>openDraft(),'','review:new-note'));content.append(declareControl(button('Commission a review',()=>onDiscuss('Independently review the current manuscript against its purpose, reader needs, conceptual dependencies and evidence. Read the relevant sources, identify concrete passage-linked findings and preserve uncertainty. Save actionable comments and follow-up work.','review')),'review:commission'));
    if(disposed||!active||host.isConnected===false||token!==generation)return;const held=document.activeElement,keepCaret=!!held&&draftHost.contains?.(held),caret=keepCaret?{start:held.selectionStart,end:held.selectionEnd}:null;host.replaceChildren(content,draftHost);if(keepCaret){held.focus({preventScroll:true});if(Number.isInteger(caret.start))held.setSelectionRange?.(caret.start,caret.end);}
  }
  const unsubscribe=queue.subscribe(value=>{proposals=value.data||{proposals:[]};if(['proposals','proposal-history'].includes(filter)){error=value.error;if(active&&!disposed)paint().catch(err=>status(err.message,true));}});
  await read();if(options.correctionId)await focusId(options.correctionId);
  return {focusCorrection:focusId,refresh:()=>read({refresh:true}),async showProposals(turnId){options.proposalTurnId=turnId;filter=turnId?'proposal-history':'proposals';focus=null;await read();},setActive(value){active=value;if(value)paint().catch(err=>status(err.message,true));},destroy(){disposed=true;generation++;unsubscribe();if(ownsQueue)queue.destroy();},get hasDraft(){return [...drafts.values()].some(form=>!!form.querySelector('textarea')?.value);}};
}
