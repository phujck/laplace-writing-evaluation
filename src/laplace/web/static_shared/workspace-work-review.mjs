// WORK REVIEW LIFECYCLE (moved unchanged from workspace-work.mjs; WORK-source-state-work-review-context-20261015).
// Purpose: a review-managed Work's ONE review surface: what stands (each obligation's outcome, currentness,
// independence and why), who handed off, the owner's next step, pending follow-up joins with the owner-issued
// recovery request, the exact review records (lazy view:review reads) and ONE phase recorder limited to the phases
// allowed_actions.work_review permits. Ownership: project_work_review owns phases, facet, guards and identities; this
// module paints the facet and keeps the draft (a stable request_id, so a retry replays and never records twice).
// The follow-up form explains itself from the owner's descriptor (action_context .. work_review.composition), never
// from a second description of the mechanics. Public contract: workReviewSection(ports) -> {reviewLifecycle(host,
// task, data)}. Ports are the Work controller's own closures: project, request, status, reader, select, drafts,
// dirty, clearDraft, button, readOnly, requestSelection, operatorHTTP, current(), generation(), selected(). Lifetime: every
// asynchronous result is fenced by generation()/selected()/current(), exactly as before the move.
import {stateChip,lazySection,declareControl} from './workspace-presentation.mjs';
import {qualifiedOwnerHTTP} from './writing-owner-read.mjs';
import {pendingRead} from './pending-read.mjs';
const el=(tag,text='',cls='')=>{const n=document.createElement(tag);n.textContent=text;n.className=cls;return n;};
export function workReviewIndependenceLabel(row){return row.independence==='INDEPENDENT'?'independent review':row.independence==='SELF'?'self-assessment'+(row.satisfied===true?' · locally satisfied':row.independent===true?' · independent review required':' · not locally satisfied'):'reviewer identity unproved';}
export function admitWorkReviewRecord({project,workId},handle,value){
    const want=handle?.payload||{},page=value?.history||value?.phases;
    if(value?.project!==project||value.view!=='review'||value.work_id!==workId)throw Error('The Work owner returned a different review record.');
    if(want.phase_id){const phase=value.phase;
      if(phase?.id!==want.phase_id)throw Error('The Work owner returned a different phase than the one requested.');
      if(phase.rows!=null){if(!phase.rows.length||phase.rows.some(row=>row.id!==want.phase_id))throw Error('The Work owner returned a different phase than the one requested.');}
      // A large phase arrives as its bounded header and one exact body page, never as an empty phase.
      else if(phase.rows_state!=='NOT_EXPANDED'||!Array.isArray(phase.header)||!phase.header.length||phase.header.some(row=>row.id!==want.phase_id)||
              !phase.body||phase.body.offset!==(want.offset??0))throw Error('The Work owner returned a different phase than the one requested.');}
    if(want.phase_revision&&value.phase?.revision!==want.phase_revision)throw Error('This phase record changed since it was inspected.');
    if(want.obligation_id&&value.obligation?.id!==want.obligation_id)throw Error('The Work owner returned a different obligation than the one requested.');
    if(want.as_of&&value.read_cut?.revision!==want.as_of)throw Error('The Work changed between history pages; read the record again.');
    if(want.offset!=null&&page&&page.offset!==want.offset)throw Error('The Work owner returned a different history page.');
    return value;
  }
// ONE checked body traversal of a header-only recorded phase, shared by every opener (the ordinary Work tab and the review
// evidence inspector). Each page must be the owner's exact issued page of the SAME phase id/revision, body hash/size and
// Work read cut, start exactly where the previous page ended and advance; a gap, regression, changed cut or identity
// refuses, and the body is shown as ending only when its last page reaches the recorded size with no continuation.
export function workReviewPhaseBodyReader({project,workId,phase,cut,load,current}){
  const revision=phase.revision,whole=phase.body,phaseId=phase.id,same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
  return async function readBody(host,first,label){
    let box=host.querySelector('.review-phase-body');if(!box){box=el('section','','review-phase-body');host.append(box);}
    const step=async(next,start)=>{
      const p=next?.payload||{};
      if(p.phase_id!==phaseId||p.phase_revision!==revision||!Number.isSafeInteger(p.offset)||p.offset!==start)throw Error('The phase page names another phase, revision or position.');
      const value=await load(next);if(!current())return;
      admitWorkReviewRecord({project,workId},next,value);
      const page=value.phase,body=page?.body;
      if(!page||page.rows!=null||page.rows_state!=='NOT_EXPANDED'||!body||typeof body!=='object'||page.revision!==revision||body.sha256!==whole.sha256||body.chars!==whole.chars||
        body.offset!==start||typeof body.content!=='string'||body.end_offset!==body.offset+[...body.content].length||body.end_offset>body.chars||body.end_offset===body.offset&&body.offset<body.chars)
        throw Error('The phase page does not continue the exact recorded body.');
      if(cut!==undefined&&!same(value.read_cut,cut))throw Error('The Work read cut changed while reading the recorded phase; nothing further is shown.');
      const ahead=body.next_read?.payload,complete=!body.next_read&&body.end_offset===body.chars;
      if((body.next_read?(ahead?.offset!==body.end_offset||ahead?.phase_id!==phaseId||ahead?.phase_revision!==revision||body.end_offset===body.chars):body.end_offset!==body.chars)||body.eof!==complete)
        throw Error('The phase page continuation is not contiguous with the recorded body.');
      box.replaceChildren(el('h4',label+' · characters '+body.offset+'–'+body.end_offset+' of '+body.chars+(complete?' · end of the recorded body':' · more pages remain')),el('pre',body.content),
        el('p','Exact recorded transport page; reassemble every page to recover the rows. Recorded standing only.','muted'));
      if(body.next_read){const more=el('button','Next phase page','act act-read');more.type='button';more.dataset.control='review-evidence:phase';
        more.onclick=()=>step(body.next_read,body.end_offset).catch(error=>{if(current())box.append(el('p',error.message,'work-status'));});box.append(more);}
    };
    try{await step(first,first?.payload?.offset);}catch(error){if(current())box.replaceChildren(el('p',error.message,'work-status'));}
  };
}
export function renderWorkReviewPhaseHeader(body,phase,{onRead=null}={}){
  for(const head of phase.header||[]){const item=el('article','','operator-review-phase');const actor=head.actor||{};
    item.append(el('h5',head.phase+(head.state?' · '+String(head.state).toLowerCase().replaceAll('_',' '):'')+(head.verdict?' · '+head.verdict:'')),
      el('p',(actor.actor||'unidentified')+' ('+(actor.origin||'origin not recorded')+')'+(head.independence?' · '+head.independence:'')));
    if(head.summary)item.append(el('p',head.summary+(head.summary_truncated?' …':'')));
    item.append(el('p',head.findings+' findings · '+head.pins+' pinned inputs · '+head.evidence+' evidence rows. This is the recorded standing; current applicability is in the review summary.','muted'));
    body.append(item);}
  const whole=phase.body||{};
  body.append(el('p','The whole recorded phase is '+whole.chars+' characters and is not expanded here. Its exact rows are unchanged; read them page by page from the Work owner.','muted'));
  if(onRead&&whole.page_read){const read=el('button','Read the recorded phase','act act-read');read.type='button';read.onclick=()=>onRead(whole.page_read,'Recorded phase '+phase.id,whole);body.append(read);}
}
export function renderWorkReviewPhaseRows(body,value,{onRead=null}={}){
    if(value.phase&&value.phase.rows==null&&value.phase.rows_state==='NOT_EXPANDED'){renderWorkReviewPhaseHeader(body,value.phase,{onRead});return;}
    for(const row of value.phase?.rows||[]){const item=el('article','','operator-review-phase');const actor=row.actor||{};
      item.append(el('h5',row.phase+(row.state?' · '+String(row.state).toLowerCase().replaceAll('_',' '):'')+(row.verdict?' · '+row.verdict:'')),
        el('p',(actor.actor||'unidentified')+' ('+(actor.origin||'origin not recorded')+(actor.origin==='external'?(actor.verified?', attested by the author':', claimed through a session, unverified'):'')+')'+(actor.profile?' · '+actor.profile:'')+(actor.scope?' · '+actor.scope:'')));
      if(row.recovered_by)item.append(el('p','Recovered by '+(row.recovered_by.actor||'unidentified')+'; the original actor is kept.','muted'));
      if(row.summary)item.append(el('p',row.summary));
      if(row.source_review_plan)renderSourceReviewPlan(item,row.source_review_plan,{onRead});
      const facts=(title,rows)=>{if(!rows.length)return;item.append(el('h6',title));const list=el('ul');for(const text of rows)list.append(el('li',text));item.append(list);};
      facts('Object',Object.entries(row.object||{}).map(([key,value])=>key+': '+value));
      facts('Findings',(row.findings||[]).map(f=>f.id+': '+f.summary));
      if(!row.source_review_plan)facts('Pinned inputs',Object.entries(row.pins||{}).map(([path,pin])=>path+' · '+pin));
      facts('Public evidence',(row.evidence||[]).map(e=>e.path+' · '+e.sha256));
      facts('Covers',row.obligations||[]);facts('Consumes',row.consumes||[]);
      if(row.request)facts('Follow-up request',[row.request.finding+' · '+row.request.closure+' · '+row.request.child.title]);
      item.append(el('p','Recorded '+(row.ts||'')+(row.basis?.work_revision?' on Work basis '+row.basis.work_revision.slice(0,19):''),'muted'));
      body.append(item);}
  }
// This is an offered reading map, not a read ledger or a second review verdict.
export function renderSourceReviewPlan(parent,plan,{onRead=null}={}){
  const section=el('section','','work-source-review-plan');section.append(el('h5','Suggested review reading'));
  const inputs=plan.inputs||[],changed=(plan.candidate_files||[]).filter(row=>row.changed).length;
  section.append(el('p',changed+' changed files · '+inputs.length+' required inputs · '+inputs.reduce((n,row)=>n+(row.initial_reads||[]).length,0)+' starting excerpts.'));
  section.append(el('p',plan.state==='COMPLETE'?'All offered changes and required inputs are structurally represented. Independent review is still required.':'Some required context is missing or unavailable. Inspect the gaps before requesting this review.','work-review-needed'));
  section.append(el('p','These are suggested starting points, not observed reads. Excerpts do not establish that dependencies were considered or that the review is complete.','muted'));
  for(const input of inputs){const card=el('article');card.append(el('h6',input.path),el('p',input.changed?'Changed input':'Supporting input'));
    const windows=(input.requested_context||[]).map(row=>'lines '+row.line_start+'–'+row.line_end).join(', ');
    if(windows)card.append(el('p','Offered context: '+windows+'.'));
    for(const reason of input.reasons||[])card.append(el('p',reason,'work-review-needed'));
    const missing=(input.uninspected_extents||[]).reduce((n,row)=>n+row.chars,0);
    if(missing)card.append(el('p',missing+' characters outside the offered excerpts; expand deliberately when needed for judgement.','muted'));
    if(input.uncovered_edit_ids?.length)card.append(el('p',input.uncovered_edit_ids.length+' changed spans are not covered by the offered context.','work-review-needed'));
    for(const excerpt of input.initial_reads||[]){const line=el('p');
      if(onRead){const read=el('button','Read '+input.path+' · '+excerpt.chars+' characters','act act-read');read.type='button';
        read.onclick=()=>onRead(excerpt.read,input.path+' · suggested excerpt',excerpt);line.append(read);}
      line.append(el('span',' Starts at character '+excerpt.offset+'; stop before '+excerpt.stop_before_offset+'.','muted'));card.append(line);}
    const edits=(input.verified_edits||{}).edits||[];
    if(edits.length){const changes=el('details');changes.append(el('summary','What changed · '+edits.length+' exact edits'));
      for(const edit of edits){changes.append(el('p',edit.id),el('pre','Before:\n'+edit.before.text),el('pre','After:\n'+edit.after.text));}card.append(changes);}
    section.append(card);}
  const exact=el('details','','operator-exact');exact.append(el('summary','Exact plan and source details'));
  exact.append(el('p','Plan '+plan.plan_id+' · '+plan.state+' structural coverage · semantic adequacy unassessed.'));
  const pins=el('ul');for(const[path,pin]of Object.entries(plan.pins||{}))pins.append(el('li',path+' · '+pin));exact.append(pins);
  const raw=el('pre');let materialized=false;exact.ontoggle=()=>{if(exact.open&&!materialized){materialized=true;raw.textContent=JSON.stringify({source_identity:plan.source_identity,candidate_files:plan.candidate_files,inputs:inputs.map(row=>({path:row.path,selected_context:row.selected_context,uninspected_extents:row.uninspected_extents,uncovered_edit_ids:row.uncovered_edit_ids}))},null,2);}};exact.append(raw);section.append(exact);parent.append(section);return section;
}
export function workReviewSection(ports){
  const {project,request,status,reader,select,drafts,dirty,clearDraft,button,readOnly,requestSelection,operatorHTTP,current}=ports;
  const gen=()=>ports.generation(),sel=()=>ports.selected();
  // THE REVIEW LIFECYCLE (M5, WORK-editor-work-review-lifecycle-20261015). A review-managed Work shows ONE surface:
  // what stands (each obligation's outcome, currentness, independence and why), who handed off, the owner's next step,
  // pending follow-up joins with the owner-issued recovery request, then ONE phase recorder limited to the phases
  // allowed_actions.work_review permits, posted to its HTTP door with its guard. Phase arithmetic is the owner's; this
  // view paints the facet and keeps the draft, whose request_id is stable so a retry replays instead of recording twice.
  const REVIEW_TONES={ACCEPTED:'ok',HOLD:'attention',REJECTED:'blocked',AWAITING_REVIEW:'neutral',AWAITING_HANDOFF:'neutral',SATISFIED:'ok',PENDING_CLOSURE:'attention'};
  const REVIEW_WORDS={RECORDED:'Review phase recorded.',REUSED:'This request was already recorded; nothing was recorded twice.',JOINED:'Follow-up Work created and joined.',
    RECOVERED:'The pending follow-up join was completed.',PENDING_JOIN:'The follow-up Work exists, but its join is pending. Complete it with the same request.',
    PENDING_RECEIPT:'The follow-up Work exists, but its receipt is pending. Retry the same request.'};
  const reviewLines=text=>String(text||'').split('\n').map(line=>line.trim()).filter(Boolean);
  const pinLines=text=>Object.fromEntries(reviewLines(text).map(line=>{const at=line.lastIndexOf(' ');if(at<1)throw Error('Each pin is "path sha256:<digest>": '+line);return [line.slice(0,at).trim(),line.slice(at+1)];}));
  async function recordPhase(task,allowed,payload,settle=()=>{}){
    const ticket=gen(),result=await request(operatorHTTP(allowed,{method:'POST'}),{project,...payload});
    // the admitted outcome settles the draft BEFORE any repaint (a completed request id is never re-offered)
    settle(result);
    if(current()&&ticket===gen()&&sel()===task.id){await select(task.id);
      if(current()&&sel()===task.id){status.textContent=REVIEW_WORDS[result?.status]||'Review phase submitted.';status.className='work-status'+(/PENDING/.test(result?.status||'')?' error':'');
        reader.querySelector?.('[data-focus-target="work-review"]')?.focus?.({preventScroll:false});}}
    return result;
  }
  // THE EXACT REVIEW RECORDS (repair1 WR-R4): read lazily, on request, through the owner's own view:review handles; the
  // response must be this project's review record of this Work, or it is refused
  function exactReview(task,label,handle,render){
    return lazySection({label,hideLabel:'Hide '+label.charAt(0).toLowerCase()+label.slice(1),cls:'operator-review-exact',
      load:async()=>{const ticket=gen();const value=await request(operatorHTTP(handle));
        if(!current()||ticket!==gen()||sel()!==task.id)throw Error('The selected Work changed while reading its review record.');
        return admitReview(task,handle,value);},
      render});
  }
  // a reply is admitted only as EXACTLY what its handle asked for (repair2 WR-R4-R1): this Work, the requested phase or
  // obligation, the pinned phase revision, the requested page and the same read cut
  const admitReview=(task,handle,value)=>admitWorkReviewRecord({project,workId:task.id},handle,value);

  // every recorded step of one obligation, page by page under ONE cut: More reads the owner-issued next page; a changed
  // cut or a replaced Work refuses without mixing pages, and focus moves to the first added record (or the refusal)
  function obligationHistory(task,body,value){
    const inputs=value.obligation?.inputs||[];const list=el('ul');for(const path of inputs)list.append(el('li',path));
    body.append(el('h6','Declared inputs'),inputs.length?list:el('p','No declared inputs.','muted'),el('h6','History'));
    const steps=el('div','','operator-review-history');body.append(steps);
    const add=page=>{for(const step of page?.items||[])steps.append(exactReview(task,step.phase+(step.verdict?' · '+step.verdict:'')+' · '+(step.actor?.actor||'unidentified')+' · '+(step.ts||''),step.read,phaseRows));};
    const first=value.history||{};add(first);
    if(!(first.items||[]).length){body.append(el('p','No handoff or review recorded for this obligation yet.','muted'));return;}
    let next=first.next_read,shown=first.items.length;const total=first.total??shown;
    if(!next)return;
    const note=el('p','','work-status');note.tabIndex=-1;
    const label=()=>'Show more history ('+shown+' of '+total+' shown)';
    const more=button(label(),async()=>{const ticket=gen(),asked=next;let page;
      try{page=admitReview(task,asked,await request(operatorHTTP(asked)));}
      catch(error){if(current()&&ticket===gen()&&sel()===task.id&&more.isConnected){note.textContent=error.message+' The records shown stay as read; nothing was mixed.';note.className='work-status error';note.setAttribute('role','alert');note.focus?.();}return;}
      if(!current()||ticket!==gen()||sel()!==task.id||!more.isConnected||asked!==next)return;
      const before=steps.children.length;add(page.history);shown+=(page.history?.items||[]).length;next=page.history?.next_read||null;
      steps.children[before]?.querySelector?.('button')?.focus?.();
      if(next)more.textContent=label();else{more.remove();note.textContent='All '+total+' history records are shown.';note.className='work-status';}},'act act-read');
    body.append(more,note);
  }
  const phaseRows=(body,value)=>{
    const ticket=gen(),workId=sel(),fresh=()=>current()&&ticket===gen()&&sel()===workId&&body.isConnected!==false;
    // a header-only recorded phase reads its body through the shared checked traversal, never the material reader
    const headerBody=value.phase&&value.phase.rows==null&&value.phase.rows_state==='NOT_EXPANDED'&&value.phase.body?value.phase:null;
    const readBody=headerBody?workReviewPhaseBodyReader({project,workId,phase:headerBody,cut:value.read_cut,current:fresh,
      load:async next=>{if(!qualifiedOwnerHTTP(next,project))throw Error('The Work owner did not issue this exact phase page.');
        const page=await request(operatorHTTP(next));if(!fresh())throw Error('The selected Work changed while reading its recorded phase.');return page;}}):null;
    return renderWorkReviewPhaseRows(body,value,{onRead:async(handle,label,extent)=>{
      if(!fresh())return;
      if(readBody&&extent===headerBody.body){await readBody(body,handle,label);return;}
      try{if(!qualifiedOwnerHTTP(handle,project))throw Error('The source owner returned an incompatible reading handle.');
        const {openArtifact}=await import('./writing-artifact.mjs');if(!fresh())return;
        await openArtifact({project,ownerRead:handle,label,request,isCurrent:fresh,
          notice:'Suggested excerpt only: stop before character '+extent.stop_before_offset+'. Any further reading is deliberate expansion, not automatic review completion.'});
      }catch(error){if(fresh())status.textContent=error.message;}
    }});
  };

  function reviewLifecycle(host,task,data){
    if(!readOnly){const setup=el('button','Set up reviews');setup.type='button';setup.dataset.control='work:review-setup';let opening=false;setup.onclick=async()=>{if(opening||!current()||sel()!==task.id)return;opening=true;setup.setAttribute('aria-busy','true');const ticket=gen();try{const module=await import('./review-setup.mjs');if(current()&&ticket===gen()&&sel()===task.id)await module.openReviewSetup({project,workId:task.id,request,read:data.allowed_actions?.review_setup,sourceFile:task.anchor?.file||null,isCurrent:()=>current()&&sel()===task.id});}catch(error){if(current()&&sel()===task.id)status.textContent=error.message;}finally{opening=false;setup.setAttribute('aria-busy','false');}};host.append(setup);}
    const facet=task.review;if(!facet?.managed)return;
    const box=el('section','','operator-work-review');box.dataset.control='work:review';
    const required=facet.obligations.filter(row=>row.required),satisfied=required.filter(row=>row.satisfied).length;
    const heading=el('h3','Review questions');heading.tabIndex=-1;heading.dataset.focusTarget='work-review';
    let nextActions=null;
    // the review owner's disposition of its latest HOLD/REJECT (project_work_review._next disposition), in its own words;
    // this view never infers a verdict, and findings and identities stay under Exact
    const disposition=facet.next?.disposition;
    if(disposition&&typeof disposition==='object'){const words=value=>String(value??'not reported').toLowerCase().replaceAll('_',' ').replaceAll('-',' ');
      const findings=Array.isArray(disposition.findings)?disposition.findings:[],count=Array.isArray(disposition.findings)?findings.length:Number.isInteger(disposition.findings)?disposition.findings:null;
      const line=el('p','Latest review: '+words(disposition.status)+' · decision currentness '+words(disposition.currentness)+' · '+words(disposition.independence)+'.'+(disposition.reason?' '+disposition.reason:'')+(count!=null?' '+count+' finding'+(count===1?'':'s')+' recorded.':''),'operator-review-disposition');
      line.dataset.reviewDisposition=String(disposition.status||'');box.append(line);
      const exact=el('details','','operator-exact');exact.append(el('summary','Review disposition details'),el('p','Review '+(disposition.review_id||'not recorded'),'muted'));
      for(const row of findings)exact.append(el('p',typeof row==='string'?row:(row?.id?row.id+': ':'')+(row?.summary||''),'muted'));box.append(exact);}
    if(facet.next?.kind==='handoff'||facet.next?.says){const handoff=facet.next.kind==='handoff',next=el('p',handoff?'Describe the work to be reviewed, then record its handoff.':facet.next.says,'operator-review-next');next.dataset.reviewNext=facet.next.kind||'';box.append(next);
      if(handoff){nextActions=el('div','','operator-review-next-actions');box.append(nextActions);if(facet.next.says){const exact=el('details','','operator-exact');exact.append(el('summary','Handoff instruction details'),el('p',facet.next.says));box.append(exact);}}}
    box.append(heading,el('p',satisfied+' of '+required.length+' required review obligations satisfied'+(facet.reviews_recorded?' · '+facet.reviews_recorded+' reviews recorded':'')+'.'));
    if(facet.handoff){const handoff=el('details','','operator-exact');handoff.append(el('summary','Handoff details'),el('p','Handed off by '+(facet.handoff.producer||'an unidentified producer')+' ('+(facet.handoff.producer_origin||'origin not recorded')+')'+(facet.handoff.object?.kind?' · '+facet.handoff.object.kind:'')+' · '+(facet.handoff.pins_total||0)+' pinned inputs, '+(facet.handoff.evidence_total||0)+' public evidence files.','muted'));
      if(facet.handoff.source_review_plan){const plan=facet.handoff.source_review_plan;handoff.append(el('p','Suggested review reading: '+plan.changed_file_count+' changed files, '+plan.input_count+' required inputs and '+plan.excerpt_count+' starting excerpts. '+(plan.state==='COMPLETE'?'Structural coverage is represented; review is not established.':'Context is incomplete or unavailable.')));}
      if(facet.handoff.read)handoff.append(exactReview(task,'Inspect the handoff record',facet.handoff.read,phaseRows));box.append(handoff);}
    const list=el('ul','','operator-review-obligations');
    for(const row of facet.obligations){const item=el('li');item.dataset.obligation=row.id;item.append(el('strong',row.label),el('span',row.required?' · required':' · optional','muted'));
      item.append(stateChip({label:String(row.status||'unknown').toLowerCase().replaceAll('_',' '),tone:REVIEW_TONES[row.status]||'neutral'}));
      if(row.review_id&&row.currentness!=='CURRENT')item.append(stateChip({label:row.currentness==='STALE'?'stale':'currentness unknown',tone:'attention'}));
      if(row.independence)item.append(el('span',' · '+workReviewIndependenceLabel(row),'muted'));
      const why=el('details');why.append(el('summary','Why and evidence'));
      why.append(el('p','Scope: '+row.scope));
      if(row.reviewer)why.append(el('p','Reviewer: '+row.reviewer+(row.reviewer_verified===false?' (claimed, unverified)':'')));
      if(row.currentness_reason)why.append(el('p',row.currentness_reason));
      if(row.review_read)why.append(exactReview(task,'Inspect the review record',row.review_read,phaseRows));
      if(row.read)why.append(exactReview(task,'Inspect declared inputs and history ('+(row.inputs_total||0)+' inputs)',row.read,(body,value)=>obligationHistory(task,body,value)));
      item.append(why);
      if(row.closure_work_id)item.append(button('Open follow-up Work',activation=>requestSelection(row.closure_work_id,{activation}),'act'));
      list.append(item);}
    box.append(list);
    const allowed=data.allowed_actions?.work_review;
    // the owner's prepared recovery (allowed_actions.work_review.preparation): each pending join's original request
    const prepared=allowed?.preparation?.phases?.followup?.recovery?.pending;
    for(const pending of prepared||facet.pending_joins||[]){box.append(el('p','The follow-up for “'+pending.finding+'” is '+(pending.state==='PENDING'?'recorded but not completed':'created, but its '+pending.closure+' join is pending')+'.','work-review-needed'));
      if(!readOnly&&allowed?.permitted&&pending.recover)box.append(button('Complete the pending follow-up',()=>recordPhase(task,allowed,{...pending.recover,expected_work_revision:allowed.payload.expected_work_revision}),'act act-write'));}
    if(!readOnly&&allowed?.permitted&&allowed.phases?.length){const recorder=phaseRecorder(task,facet,allowed);box.append(recorder);
      if(nextActions&&recorder.querySelector?.('form')){const ticket=gen(),open=button('Open review form',()=>{
        if(!current()||ticket!==gen()||sel()!==task.id||open.isConnected===false)return;
        // A background update may retain the existing dirty recorder while replacing this read-only instruction.
        // Resolve that recorder from the control's actual current parent, never the detached incoming render.
        const kept=open.closest?.('.operator-work-review')?.querySelector('.operator-review-recorder');
        if(!kept||kept.isConnected===false||!kept.querySelector('form'))return;
        kept.open=true;const target=kept.querySelector('select')||kept.querySelector('summary');target?.focus?.({preventScroll:false});target?.scrollIntoView?.({block:'nearest'});
      },'act act-read');nextActions.append(open);}}
    host.append(box);
  }
  // the owner's composition of the follow-up, unfolded for the person about to record it: each step's effect and the
  // chosen closure's meaning, from project_work_review.followup_composition (no second description of the mechanics)
  function compositionNote(composition,closure){
    const box=el('details','','operator-exact work-composition');box.append(el('summary','What this records, step by step (from the Work owner)'));
    const list=el('ol');for(const step of composition.steps||[])list.append(el('li',step.effect));box.append(list);
    const meaning=el('p','','muted work-composition-closure');const say=value=>{meaning.textContent=value&&composition.closures?.[value]?'This closure: '+composition.closures[value]+'.':'';};say(closure.value);
    box.append(meaning,el('p',composition.recovery||'','muted'));closure.onchange=()=>say(closure.value);return box;
  }
  // the payload value of one owner input (preparation.inputs[].input): the input kinds are the owner's, this is only parsing
  const INPUT_VALUE={lines:reviewLines,pins:pinLines,
    evidence:text=>Object.entries(pinLines(text)).map(([path,sha256])=>({path,sha256})),
    findings:text=>reviewLines(text).map(line=>{const at=line.indexOf(':');if(at<1)throw Error('Each finding is "ID: summary": '+line);return {id:line.slice(0,at).trim(),summary:line.slice(at+1).trim()};})};
  const AREA=new Set(['area','lines','pins','evidence','findings']);
  function assemble(inputs,fields){
    const payload={};
    for(const input of inputs){const raw=fields[input.name]??'',value=INPUT_VALUE[input.input]?INPUT_VALUE[input.input](raw):raw;
      const empty=value===''||(Array.isArray(value)&&!value.length)||(value&&typeof value==='object'&&!Array.isArray(value)&&!Object.keys(value).length);
      if(empty&&!input.required)continue;
      const path=input.path.split('.');let at=payload;for(const key of path.slice(0,-1))at=(at[key]??={});at[path.at(-1)]=value;}
    return payload;
  }
  // THE PHASE RECORDER: phases, titles, consequences, inputs, defaults, options, refusals and the basis a draft consumes all
  // come from the owner's preparation (project_work_review.preparation over PHASE_SPEC, carried by allowed_actions.work_review,
  // the same object the native door serves); this view renders it, keeps the draft and its stable request id.
  function phaseRecorder(task,facet,allowed){
    let prep=allowed.preparation||{phases:{},initial:null};
    const phases=allowed.phases.filter(phase=>prep.phases[phase]);
    // without the owner's preparation there is nothing this view may assume about a phase: say so, record nothing
    if(!phases.length)return el('p','Recording a review phase needs the owner\'s phase preparation, which this read did not supply. Reinspect this Work.','muted operator-review-recorder');
    const box=el('details','','operator-work-editor operator-review-recorder');   // inside the work:review control
    const held=drafts.get(task.id)?.review||{};box.open=!!held.dirty;box.append(el('summary','Record a review phase'));
    const choose=el('select'),chooseLabel=el('label','Phase');for(const phase of phases){const option=el('option',prep.phases[phase].title);option.value=phase;choose.append(option);}
    choose.value=phases.includes(held.phase)?held.phase:(phases.includes(prep.initial)?prep.initial:phases[0]);chooseLabel.append(choose);box.append(chooseLabel);
    const formHost=el('div');box.append(formHost);
    // the exact basis a draft is written against: the owner's per-phase basis (guard and the records the phase names)
    const basisOf=phase=>prep.phases[phase]?.basis||null;
    const sameBasis=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
    const freshId=phase=>'ui-'+phase+'-'+crypto.randomUUID().slice(0,18);
    let shown=null;   // the painted form's controls, for a background basis change (stale)
    const adoptControl=(phase,save,note,form)=>button('Use this inspected basis for my draft',()=>{const review={...drafts.get(task.id).review,basis:basisOf(phase),request_id:freshId(phase)};
      drafts.set(task.id,{...drafts.get(task.id),review,dirty:true});dirty();paint();
      // the adopted draft is still here and recordable: focus its now-enabled submit (repair2 WR-R5-R1), never BODY
      formHost.querySelector?.('[data-review-submit]')?.focus?.({preventScroll:false});});
    const paint=()=>{formHost.replaceChildren();const phase=choose.value,spec=prep.phases[phase],draft=drafts.get(task.id)?.review?.phase===phase?drafts.get(task.id).review:{phase,fields:{}};
      const current_=basisOf(phase),stale=draft.basis&&!sameBasis(draft.basis,current_);
      const form=el('form'),fields={},field=(name,label,{area=false,value='',options=null}={})=>{const wrap=el('label',label),input=el(options?'select':area?'textarea':'input');input.name=name;
        if(options)for(const [optionValue,text]of options){const option=el('option',text);option.value=optionValue;input.append(option);}input.value=draft.fields?.[name]??value;fields[name]=input;wrap.append(input);form.append(wrap);return input;};
      form.append(el('p',spec.says||'','muted operator-review-consequence'));
      if(spec.refused)form.append(el('p',spec.refused,'work-review-needed'));
      if(current_?.consumes)form.append(el('p','Consumes: '+((draft.basis||current_).consumes?.join(', ')||'nothing recorded yet'),'muted'));
      for(const input of spec.inputs||[]){const node=field(input.name,input.label,{area:AREA.has(input.input),options:input.options||null,value:input.default??''});
        if(input.path==='closure'&&spec.composition)form.append(compositionNote(spec.composition,node));}
      const save=el('button',spec.title);save.type='submit';save.dataset.reviewSubmit='true';const note=el('p','','work-status');
      if(stale){note.textContent='This draft was written against an earlier inspection of this Work (its guard, handoff or synthesis changed). Your text is retained; inspect the current Work, then explicitly use its basis before recording.';note.className='work-status error';save.disabled=true;
        form.append(save,note,adoptControl(phase,save,note,form));}
      else form.append(save,note);
      if(spec.refused)save.disabled=true;
      const keep=()=>{const prior=drafts.get(task.id)?.review?.phase===phase?drafts.get(task.id).review:null;
        const review={phase,fields:Object.fromEntries(Object.entries(fields).map(([k,n])=>[k,n.value])),request_id:prior?.request_id||freshId(phase),basis:prior?.basis||current_,dirty:true};
        drafts.set(task.id,{...drafts.get(task.id),review,dirty:true});dirty();return review;};
      form.oninput=keep;
      form.onsubmit=async event=>{event.preventDefault();if(save.disabled)return;save.disabled=true;const review=keep(),basis=review.basis;try{
        if(prep.phases[phase]?.refused)throw Error(prep.phases[phase].refused);
        if(!sameBasis(basis,basisOf(phase)))throw Error('This draft belongs to an earlier inspection; use the inspected basis explicitly first.');
        const payload={id:task.id,phase,request_id:review.request_id,...basis,...assemble(spec.inputs||[],review.fields)};
        await recordPhase(task,allowed,payload,result=>{
          if(/PENDING/.test(result?.status||''))return;   // the same request completes it: keep the draft and its id
          const now=drafts.get(task.id)?.review;
          if(now===review)clearDraft(task.id,['review']);
          else if(now)drafts.set(task.id,{...drafts.get(task.id),review:{...now,request_id:freshId(now.phase)}});   // newer typing is a new operation
        });
      }catch(error){if(current()){note.textContent=error.message+' Your draft and its request are retained; the same request never records twice.';note.className='work-status error';}}finally{if(save.isConnected!==false)save.disabled=!!prep.phases[phase]?.refused;}};
      formHost.append(form);shown={phase,save,note,form};};
    choose.onchange=paint;paint();
    // a background owner observation (repair1 WI-R3): the mounted form, its text, request id and focus stay; when the basis
    // this draft consumed changed, only this form is disabled and offers explicit adoption
    ports.formHooks?.set('review',{stale(allowedNow){const next=allowedNow?.work_review;
      if(!next?.preparation)return false;prep=next.preparation;const now=drafts.get(task.id)?.review;
      if(!shown||!now?.dirty||now.phase!==shown.phase||sameBasis(now.basis,basisOf(shown.phase)))return false;
      shown.save.disabled=true;shown.note.textContent='The basis this draft consumed changed (its guard, handoff or synthesis). Your text and request are kept; use the inspected basis explicitly before recording.';shown.note.className='work-status error';
      if(!shown.form.querySelector?.('[data-adopt-basis]')){const adopt=adoptControl(shown.phase,shown.save,shown.note,shown.form);adopt.dataset.adoptBasis='true';shown.form.append(adopt);}
      return true;}});
    return box;
  }
  return {reviewLifecycle};
}

// TASK PROGRESS AND NEXT ACTION (WORK-eigen-continuity-human-guides-20261030). Purpose: inside the selected Task, the Work
// owner's continuity summary (laplace.work-continuity/1): what was produced, what awaits declared proof, review, synthesis
// or delivery, what is admitted or observed, what is unknown, and the ONE next action the owner issued. Ownership:
// project_work_continuity derives the summary, readiness and next action; work_delivery owns Continue and its replay;
// development_source owns proof arrival; the review recorder above owns phases. This view admits only the selected
// detail's own continuity_read (exact namespace, Work, summary request and route; a stated scope must not name another
// namespace), reads it once per detail observation (reused while the detail cut and observe basis are unchanged), never
// composes a route or promotes a scope, and keeps a sent wire under that Work's draft until its outcome is known. Recorded
// lifecycle, evidence currentness, proof arrival, review judgement and observed execution stay separate words. Public
// contract: admitContinuityRead, admitContinuitySummary, admitContinuityChild, admitContinuityPart, continuityCut,
// continuityModel, continuityNext, continuitySection(ports) -> {render(host, task, data), readChild(handle, label,
// activation), keep(box)}: readChild reads one owner-issued child of the selected Work (a prepared completion) in place;
// keep re-adopts a section a background update kept mounted, so later outcomes paint into the mounted node. Ports: project, request, drafts, dirty, clearDraft, button,
// readOnly, readLink, select, handOff, current(), generation(), selected(). Controls (data-control, data-control-owner project::Work):
// work:continuity-continue, -proof, -check, -resend, -review, -retry, mounted only under their reached condition; their
// declaration rows belong to the shared registry (A). An identity names a control; it never confers authority.
export const CONTINUITY_SCHEMA='laplace.work-continuity/1';
const sameJSON=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
const said=value=>String(value??'not reported').toLowerCase().replaceAll('_',' ').replaceAll('-',' ');
const reasonText=reason=>typeof reason==='string'?reason:reason?.says||reason?.message||reason?.reason||(reason?.code?String(reason.code)+(reason.detail?': '+reason.detail:''):JSON.stringify(reason));
const bareSha=value=>String(value||'').replace(/^sha256:/,'');
// a durable Stop REQUEST withdraws continuation; it is not an observation that the producing process ended
const stopAware=reason=>(reason?.code||reason)==='PRODUCER_STOPPED'?'a Stop request for the producing turn is recorded; it does not show that the turn\'s process has ended':reasonText(reason);
export function admitContinuityRead(handle,{project,workId}){
  if(!handle||typeof handle!=='object'||handle.operation!=='project'||!handle.payload||typeof handle.payload!=='object')throw Error('This task did not carry the Work owner\'s progress read.');
  if(Object.keys(handle).some(key=>!['operation','payload','http','scope'].includes(key)))throw Error('The progress read carries fields this view does not know; nothing was read.');
  const payload=handle.payload;
  if(payload.namespace!==project)throw Error('The progress read names another work namespace; nothing was read.');
  if(payload.view!=='continuity'||payload.id!==workId)throw Error('The progress read names another task; nothing was read.');
  if(Object.keys(payload).some(key=>!['namespace','view','id','request'].includes(key))||!sameJSON(payload.request,{part:'summary'}))throw Error('The progress read is not the owner\'s summary request; nothing was read.');
  const scope=handle.scope;
  if(scope!=null&&(typeof scope!=='object'||(scope.namespace!=null&&scope.namespace!==project)||(scope.kind==='project'&&scope.namespace!==project)))throw Error('The progress read was issued for another scope; nothing was read.');
  const http=handle.http;if(http?.method!=='GET'||typeof http.url!=='string')throw Error('The owner issued no human route for this progress read.');
  const url=new URL(http.url,'http://local'),q=url.searchParams;
  if(url.origin!=='http://local'||url.pathname!=='/work/state'||[...q.keys()].some(key=>!['project','view','id','request'].includes(key)||q.getAll(key).length!==1)||q.get('project')!==project||q.get('view')!=='continuity'||q.get('id')!==workId)throw Error('The progress read route does not match its request; nothing was read.');
  let asked=null;try{asked=JSON.parse(q.get('request'));}catch{asked=null;}
  if(!sameJSON(asked,payload.request))throw Error('The progress read route does not match its request; nothing was read.');
  return url.pathname+url.search;
}
export function admitContinuitySummary(value,{project,workId}){
  if(value?.schema_version!==CONTINUITY_SCHEMA||value.part!=='summary')throw Error('The Work owner returned a different progress record; it is not shown.');
  const subject=value.subject||{};
  if(subject.namespace!==project||subject.id!==workId||subject.qualified_id!==project+'::'+workId)throw Error('The progress summary names another task; it is not shown.');
  if(!value.basis||value.basis.work_revision!==subject.work_revision||value.basis.scope_revision!==subject.scope_revision)throw Error('The progress summary basis does not match its own task; it is not shown.');
  return value;
}
// a child read the owner issued for a step of this Work (a prepared completion, a preflight): exact namespace, Work, closed
// request (writing-owner-read continuityRequest) and its own GET route; another scope or Work is refused before reading
export function admitContinuityChild(handle,{project,workId}){
  if(!handle||typeof handle!=='object'||handle.operation!=='project'||!handle.payload||typeof handle.payload!=='object')throw Error('This step did not carry the Work owner\'s exact read; nothing was read.');
  if(Object.keys(handle).some(key=>!['operation','payload','http','scope'].includes(key)))throw Error('The progress read carries fields this view does not know; nothing was read.');
  const payload=handle.payload;
  if(payload.namespace!==project)throw Error('The progress read names another work namespace; nothing was read.');
  if(payload.view!=='continuity'||payload.id!==workId)throw Error('Only this task\'s own progress reads open here. Select that task to read what its step waits on; nothing was read.');
  const scope=handle.scope;
  if(scope!=null&&(typeof scope!=='object'||(scope.namespace!=null&&scope.namespace!==project)||(scope.kind==='project'&&scope.namespace!==project)))throw Error('The progress read was issued for another scope; nothing was read.');
  const target=qualifiedOwnerHTTP(handle,project);
  if(target?.owner?.kind!=='work-continuity'||target.owner.id!==workId)throw Error('The progress read route does not match its request; nothing was read.');
  return {url:target.url,request:target.owner.request};
}
// the reply to a child read is shown only when it is the part, Work and prepared completion that was asked for
export function admitContinuityPart(value,{project,workId,request}){
  const part=request?.part||'summary';
  if(value?.schema_version!==CONTINUITY_SCHEMA||value.part!==part)throw Error('The Work owner returned a different progress record than this read asked for.');
  const subject=value.subject||{};
  if(subject.namespace!==project||subject.id!==workId||subject.qualified_id!==project+'::'+workId)throw Error('The reply names another task.');
  if(part==='completion'&&value.intent?.id!==request.intent_id)throw Error('The reply names another prepared completion.');
  if(part==='summary')admitContinuitySummary(value,{project,workId});
  return value;
}
// the summary's subject against the selected detail's own revisions (FULL detail keys work_revision/work_scope_revision)
export function continuityCut(value,task){
  const subject=value?.subject||{},pairs=[['work_revision','work_revision'],['work_scope_revision','scope_revision']].filter(([own])=>typeof task?.[own]==='string'&&task[own]);
  if(!pairs.length)return {same:null,says:'The task details carry no revision to compare with this summary.'};
  const changed=pairs.filter(([own,theirs])=>task[own]!==subject[theirs]).map(([own])=>own.replaceAll('_',' '));
  return changed.length?{same:false,says:'This summary was read at a different '+changed.join(' and ')+' than the task details above. Reinspect the task before acting on it.'}
    :{same:true,says:'Read at the same task revision as the details above.'};
}
const READINESS_WORDS={READY:'ready to continue',AWAITING_PROOF:'awaiting declared proof',HELD:'held',CLOSED:'closed',CONTINUED:'continued'};
// the issued route of an action, exactly as issued: a POST inside this engine whose payload is the action's own
function issuedRoute(action,project,label){
  const http=action?.http;
  if(!http)return {gap:'The owner issued this '+label+' action for agents ('+action.operation+' '+(action.payload?.action||'')+') without a human route, so it is not sent from here.'};
  if(http.method!=='POST'||typeof http.url!=='string')return {gap:'The issued '+label+' route is not a supported POST; nothing is sent.'};
  const url=new URL(http.url,'http://local');if(url.origin!=='http://local')return {gap:'The issued '+label+' route is outside this local engine; nothing is sent.'};
  const body=http.payload!==undefined?http.payload:{project,...action.payload};
  if(!body||typeof body!=='object'||body.project!==project)return {gap:'The issued '+label+' route names another project; nothing is sent.'};
  const {project:_named,...rest}=body;if(!sameJSON(rest,action.payload))return {gap:'The issued '+label+' route carries a different payload from its action; nothing is sent.'};
  return {route:url.pathname+url.search,body:structuredClone(body)};
}
// the owner's next step, offered only when it is complete and consistent with the summary it came in
export function continuityNext(value,{project,cut={same:null}}={}){
  const next=value?.next||{},action=next.action||null;
  const out={kind:next.kind||'inspect',reason:next.reason||'The Work owner named no next step.',callable:next.callable===true,template:next.template===true,fill:next.fill||[],
    action,read:next.read||null,preparation:next.preparation||null,route:null,body:null,gap:null,withheld:null,intent:null};
  const payload=action?.payload||{};
  if(out.kind==='continue'){
    const intent=(value.completion?.intents||[]).find(row=>row.id===payload.intent_id)||null;out.intent=intent;
    if(!out.callable||action?.operation!=='work_delivery'||payload.action!=='continue'||typeof payload.expected_basis!=='string'||Object.keys(payload).some(key=>!['action','intent_id','expected_basis'].includes(key)))out.withheld='The owner did not issue a complete Continue action.';
    else if(!intent||intent.readiness?.state!=='READY'||intent.readiness.basis!==payload.expected_basis)out.withheld='The issued Continue does not match its prepared completion in this summary. Reinspect the task.';
    else if(cut.same===false)out.withheld=cut.says;
    if(!out.withheld)Object.assign(out,issuedRoute(action,project,'Continue'));
  }else if(out.kind==='attach-proof'){
    const intent=(value.completion?.intents||[]).find(row=>row.id===payload.intent_id)||null;out.intent=intent;
    if(action?.operation!=='development_source'||payload.action!=='proof'||!sameJSON(out.fill,['payload.reference'])||!intent)out.withheld='The proof template is not one this view can fill.';
    else if(cut.same===false)out.withheld=cut.says;
    if(!out.withheld)Object.assign(out,issuedRoute(action,project,'proof'));
  }
  return out;
}
// one prepared completion in owner words, shared by the summary and its completion read: human meaning leads; every exact
// identity (intent, request, grant, account, sessions, turns) stays under Exact
function intentFacts(intent,{delivered,open,uncertain,exact}){
  const ready=intent.readiness||{},origin=intent.origin||{},made=intent.production||{},facts=ready.facts||{};
  delivered.push('Prepared completion armed '+(intent.ts||'at an unrecorded time')+' by its producing session for '+(made.changed||[]).length+' changed files.');
  (['CONTINUED','CLOSED'].includes(ready.state)?delivered:open).push('Prepared completion: '+(READINESS_WORDS[ready.state]||said(ready.state||intent.state))+'.');
  for(const slot of ready.slots||intent.proof_slots||[]){
    const name='“'+(slot.label||slot.id)+'”';
    if(slot.filled)delivered.push('Declared proof '+name+' arrived ('+said(slot.integrity)+'). Arrival is not a review or acceptance.');
    else open.push('Awaiting declared proof '+name+'.');
    if(slot.filled&&slot.integrity&&slot.integrity!=='VERIFIED')uncertain.push('Declared proof '+name+' no longer matches its pinned bytes ('+said(slot.integrity)+').');
  }
  if(facts.account?.capacity==='UNKNOWN')uncertain.push('The Source account capacity of this prepared completion is UNKNOWN; Continue waits until its owner can establish it.');
  if(facts.source&&facts.source!=='CURRENT')uncertain.push('The produced Source of this prepared completion is '+said(facts.source)+'.');
  if(facts.producer_stopped)delivered.push('A Stop was requested for the producing turn, so this prepared completion is withdrawn from continuing. The request is recorded; it does not show that the turn\'s process has ended.');
  // awaiting proof is already said by its slot lines; a hold is uncertainty, a closure is a recorded fact
  if(ready.state!=='AWAITING_PROOF')for(const reason of ready.reasons||[])(ready.state==='CLOSED'?delivered:uncertain).push('Prepared completion '+(ready.state==='CLOSED'?'closed':ready.state==='HELD'?'held':'waits')+': '+stopAware(reason));
  exact.push('Prepared completion '+intent.id+' · request '+(intent.request_id||'not recorded')+' · grant '+(intent.grant_id||'not recorded')+' · obligation '+(intent.obligation_id||'not recorded')+' · candidate '+(made.candidate_id||'not recorded')+
    ' · effect '+(made.effect_id||'not recorded')+' · account '+(origin.commission_id||'not recorded')+' · producer actor '+(origin.actor||'not recorded')+' · session '+(origin.session_id||'not recorded')+
    ' · turn '+(origin.turn_id||'not recorded')+' · readiness basis '+(ready.basis||'not reported'));
}
// one display model: standing words, delivered facts, admitted/observed activity, uncertainty, exact identities, next step
export function continuityModel(value,{task=null,project=value?.subject?.namespace}={}){
  const cut=continuityCut(value,task),standing=value.standing||{},delivered=[],open=[],activity=[],uncertain=[],exact=[];
  const lifecycle=standing.lifecycle||{},acceptance=standing.current_acceptance||{},readiness=standing.readiness||{};
  const state=['Recorded lifecycle: '+said(lifecycle.status||standing.recorded_status)+(lifecycle.completed?' (completion recorded)':''),
    'Evidence currentness: '+(acceptance.status==='NOT_REQUIRED'?'not required yet':said(acceptance.status)+' · '+said(acceptance.currentness)),
    'Prerequisites: '+said(readiness.status)+((readiness.blocked_by||[]).length?' · waiting on '+readiness.blocked_by.join(', '):'')];
  if(acceptance.status!=='NOT_REQUIRED'&&acceptance.currentness==='UNKNOWN')uncertain.push('Evidence currentness is unknown: current proof could not be established, which is not a failure.');
  const production=value.production||{},effects=production.effects||{},checks=production.checks||{};
  // Delivered holds recorded facts only; what is still awaited goes to Still open (review R2)
  const checked=checks.total?' · checks '+Object.entries(checks.states||{}).map(([name,count])=>count+' '+said(name)).join(', '):' · no checks recorded';
  if(effects.total)delivered.push('Produced: '+(effects.committed??0)+' of '+effects.total+' Source changes applied from '+(production.candidates??0)+' candidates under '+(production.grants??0)+' grant'+(production.grants===1?'':'s')+checked+'. Applied source is provenance, not review.');
  else if(production.grants||production.candidates)open.push('No Source change applied yet ('+(production.grants??0)+' grant'+(production.grants===1?'':'s')+', '+(production.candidates??0)+' candidates'+checked+').');
  if(production.grants||production.candidates||effects.total){
    if((effects.total??0)>(effects.committed??0))uncertain.push(((effects.total??0)-(effects.committed??0))+' Source changes are not recorded as applied; inspect them before relying on this work.');
  }
  for(const intent of value.completion?.intents||[])intentFacts(intent,{delivered,open,uncertain,exact});
  const review=value.review||{};
  for(const row of review.obligations||[]){
    (row.review_id||!/^AWAITING/.test(String(row.status||''))?delivered:open).push('Review “'+row.id+'”: '+said(row.status)+(row.satisfied?' · satisfied':' · not satisfied')+(row.review_id?' · decision currentness '+said(row.currentness):'')+'.');
    if(row.review_id&&row.currentness!=='CURRENT')uncertain.push('Review “'+row.id+'” decision is '+(row.currentness==='STALE'?'stale: its inputs changed':'of unknown currentness')+'.');
  }
  if(review.remaining)open.push(review.remaining+' review obligation'+(review.remaining===1?' remains':'s remain')+(review.next?' · the review owner\'s next phase is '+said(review.next):'')+'.');
  for(const event of value.delivery?.events||[]){
    const dispatcher=event.dispatcher_origin,who=typeof dispatcher==='string'?dispatcher:dispatcher?(dispatcher.actor||'unidentified')+' ('+(dispatcher.origin||'origin not recorded')+')':null;
    delivered.push('Review request for “'+(event.obligation_id||'not recorded')+'”: '+said(event.state)+(event.prepared_completion?.intent_id?' · from the prepared completion':'')+
      (who?' · dispatched by '+who+', recorded apart from the producer':'')+'.');
    const admitted=event.admitted&&typeof event.admitted==='object'?event.admitted:null;
    exact.push('Review request '+event.id+' · handoff '+(event.handoff_id||'not recorded')+' · prepared completion '+(event.prepared_completion?.intent_id||'none')+
      (admitted?' · review session '+(admitted.session_id||'not recorded')+' · turn '+(admitted.turn_id||'not recorded')+' · request '+(admitted.request_id||'not recorded'):''));
    if(admitted){
      activity.push('A review turn was admitted'+(admitted.reused?' (reused)':'')+(admitted.recovered?' (recovered)':'')+'. Admission is not an observed running process.');
      if(!admitted.recipient_ack||admitted.recipient_ack==='UNKNOWN')uncertain.push('The review turn\'s acknowledgement is UNKNOWN: not an error, and not proof that it started.');
    }
    if(event.reason)uncertain.push('A review request: '+reasonText(event.reason));
  }
  const execution=value.execution||{};
  for(const account of execution.accounts||[]){
    exact.push('Source account '+(account.commission_id||'not recorded'));
    activity.push('Source account: '+said(account.state)+' · '+(account.admitted??'?')+' admitted calls, '+(account.remaining??'?')+' remaining · '+(account.app_remaining??'?')+' app turns and '+
      (account.session_remaining??'?')+' sessions remaining'+(account.deadline_at?' · deadline '+account.deadline_at:'')+(account.stop_reason?' · stopped: '+account.stop_reason:'')+'.');
    if(account.state==='UNKNOWN')uncertain.push('A Source account standing is UNKNOWN.');
  }
  if(!activity.length)activity.push('No admitted execution is recorded in this summary. In progress is a declared standing, not an observed running process.');
  if(execution.observed_at)activity.push('Account standing observed '+execution.observed_at+'.'+(execution.qualification?' '+execution.qualification:''));
  const coverage=value.coverage||{};
  if(coverage.intents_omitted)uncertain.push(coverage.intents_omitted+' further prepared completions are not shown in this bounded summary.');
  if(coverage.events_omitted)uncertain.push(coverage.events_omitted+' further review requests are not shown in this bounded summary.');
  if(value.subject?.containment_issue)uncertain.push('Containment: '+reasonText(value.subject.containment_issue));
  if(cut.same===false)uncertain.push(cut.says);
  // Closure facts stay separate owner facts, in the owner's words: currentness and its reason, recorded reviews, receipt
  // by the original parent, adoption/live/publication and check-stage disposition. Absence is said only as the owner says it.
  const closure=[],close=value.closeout||null;
  if(acceptance.status&&acceptance.status!=='NOT_REQUIRED')closure.push('Evidence currentness (owner): '+acceptance.status+(acceptance.currentness&&acceptance.currentness!==acceptance.status?' · '+acceptance.currentness:'')+
    (acceptance.kind?' · '+acceptance.kind:'')+(acceptance.reason?' · '+acceptance.reason:'')+(acceptance.review_required?' · review required':'')+'.');
  if(close){
    closure.push('Handoffs recorded: '+(close.handoffs_total??0)+(close.handoff?' (latest '+close.handoff+')':'')+'.');
    // the owner caps this history; say which part is shown and where the rest is, never imply the rows are complete
    const reviews=close.reviews||[],reviewTotal=Number.isSafeInteger(close.reviews_total)?close.reviews_total:reviews.length;
    if(reviewTotal>reviews.length)closure.push('Recorded reviews: showing the latest '+reviews.length+' of '+reviewTotal+'. Earlier reviews and each phase\'s actor are in the owner\'s exact review history'+(value.review?.read?' (its issued review read).':'.'));
    for(const row of reviews)closure.push('Recorded review '+row.id+': '+said(row.verdict)+(row.obligation_id?' for “'+row.obligation_id+'”':'')+'. A recorded verdict is history; current applicability is the review standing.');
    // the owner bounds this list and reports no total: say it is bounded, never invent a count
    if((close.held||[]).length)closure.push('Held by the owner: '+close.held.join(', ')+' (a bounded list from the owner; no total is reported).');
    if((close.remaining||[]).length)closure.push('Still to be satisfied (owner): '+close.remaining.join(', ')+'.');
    if(close.missing_next)closure.push('Next recorded step (owner): '+close.missing_next+'.');
    // a same-Work synthesis may be recorded by any permitted actor; its existence is not receipt by the original parent,
    // and a consumes list without the handoff may still cover it through a consumed review
    if(close.synthesis){closure.push('Same-Work synthesis recorded: '+close.synthesis+'. Who recorded it, and whether it is the original parent\'s receipt, is in its delivery and phase records; this summary does not establish it.');
      closure.push(close.latest_synthesis_covers_latest_handoff?'It names the latest handoff directly in what it consumes.':'It does not name the latest handoff directly; it may still cover it through a consumed review. This summary does not assess that chain.');}
    else if(close.review_required==='REQUIRED')closure.push('No same-Work synthesis is recorded.');
    for(const [label,key] of [['Adopted','adoption'],['Live','live'],['Published','publication']])
      closure.push(label+': '+(close[key]==='NOT_RECORDED'?'not recorded by the Work owner (owned elsewhere; never inferred from a verdict or an applied candidate).':said(close[key])+'.'));
  }
  if(checks.total&&checks.cleanup)closure.push('Check stages: '+Object.entries(checks.cleanup).map(([state,count])=>count+' '+said(state)).join(', ')+'. Other resources have no recorded disposition here.');
  return {title:value.title||null,goal:value.goal||null,state,delivered,open,activity,uncertain,exact,cut,coverage,closure,next:continuityNext(value,{project,cut})};
}
export function continuitySection(ports){
  const {project,request,drafts,dirty,clearDraft,button,readOnly,readLink,current}=ports;
  const gen=()=>ports.generation(),sel=()=>ports.selected();
  // bounded per-controller memory: one summary per recently selected Work, the latest painted view, local outcomes
  const memo=new Map(),views=new Map(),outcomes=new Map(),inflight=new Set(),byBox=new WeakMap();
  const remember=(id,entry)=>{memo.delete(id);memo.set(id,entry);while(memo.size>8)memo.delete(memo.keys().next().value);};
  const unresolved=held=>!!held&&['pending','uncertain','checked'].includes(held.status);
  const mark=(node,control,workId)=>{node.dataset.control=control;node.dataset.controlOwner=project+'::'+workId;return node;};
  const list=(title,rows,cls)=>{const box=el('div','',cls);box.append(el('h4',title));const items=el('ul');for(const row of rows)items.append(el('li',row));box.append(items);return box;};
  function render(host,task,data){
    if(!data||!Object.hasOwn(data,'continuity_read'))return null;   // this Work owner issues no progress summary
    const box=el('section','','work-continuity'),heading=el('h3','Progress and next action');heading.tabIndex=-1;heading.dataset.focusTarget='work-continuity';
    const body=el('div','','work-continuity-body'),line=el('div','','work-status work-continuity-attempt');line.setAttribute('role','status');
    const child=el('section','','work-continuity-child');child.hidden=true;
    box.append(heading,body,child,line);host.append(box);
    const ticket=gen(),id=task.id,view={box,heading,body,child,line,task,data,path:null,childEpoch:0,fresh:()=>current()&&ticket===gen()&&sel()===id};
    views.set(id,view);byBox.set(box,view);paintAttempt(id);
    if(!data.continuity_read){body.append(el('p','No progress summary was issued for this task: '+(data.continuity_read_gap||'the Work owner gave no reason.'),'muted'));return box;}
    try{view.path=admitContinuityRead(data.continuity_read,{project,workId:id});}catch(error){body.append(el('p',error.message,'error'));return box;}
    const key=JSON.stringify([view.path,data.read_cut?.revision||null,data.observe_basis||null]),held=memo.get(id);
    if(held?.key===key){paintSummary(view,held.value);return box;}
    body.append(pendingRead(el('p','Reading this task\'s progress…','muted')));load(view,key);return box;
  }
  async function load(view,key){
    let value;
    try{value=admitContinuitySummary(await request(view.path),{project,workId:view.task.id});}
    catch(error){if(!view.fresh())return;view.body.replaceChildren(el('p','Progress is unavailable: '+error.message+' The task details are unaffected.','error'),
      mark(button('Read progress again',()=>{view.body.replaceChildren(pendingRead(el('p','Reading this task\'s progress…','muted')));return load(view,key);},'act act-read'),'work:continuity-retry',view.task.id));return;}
    remember(view.task.id,{key,value});
    if(view.fresh())paintSummary(view,value);   // a late reply for another selection or paint is kept only as memory
  }
  function paintSummary(view,value){
    const {body,task,data}=view,model=continuityModel(value,{task,project});view.summary=value;
    body.replaceChildren();
    const ownGoal=data.acceptance?.goal||task.goal||'';
    if(model.goal&&model.goal!==ownGoal)body.append(el('p','Goal: '+model.goal,'operator-work-purpose'));
    body.append(el('p',model.state.join(' · '),'muted work-continuity-standing'));
    body.append(list('Delivered so far',model.delivered.length?model.delivered:['Nothing is recorded as produced, handed off, reviewed or delivered yet.'],'work-continuity-delivered'));
    if(model.closure.length)body.append(list('Closure facts',model.closure,'work-continuity-closure'));
    if(model.open.length)body.append(list('Still open',model.open,'work-continuity-open'));
    body.append(list('Activity',model.activity,'work-continuity-activity'));
    if(model.uncertain.length)body.append(list('Uncertain or unknown',model.uncertain,'work-continuity-uncertain'));
    body.append(nextBlock(view,model));
    const exact=el('details','','operator-exact work-continuity-exact');exact.append(declareControl(el('summary','Exact progress basis and reads'),'work:progress-basis'));
    exact.append(el('p',value.subject.qualified_id+' · work revision '+value.subject.work_revision+' · scope revision '+value.subject.scope_revision,'muted'),
      el('p','Basis '+(value.basis.token||'not reported')+' · development cut '+(value.basis.development_cut||'not reported')+' · delivery cut '+(value.basis.delivery_cut||'not reported'),'muted'),
      el('p',model.cut.says,'muted'));
    const scope=data.continuity_read?.scope;exact.append(el('p',scope?'Read scope: '+(scope.says||scope.kind):'The owner did not state the read scope of this summary.','muted'));
    if(value.mode)exact.append(el('p','Presentation: '+value.mode+'. A person or engine view selects context, never authority.','muted'));
    for(const row of model.exact)exact.append(el('p',row,'muted'));
    if(value.coverage?.meaning)exact.append(el('p',value.coverage.meaning,'muted'));
    // evidence stays behind deliberate reads: human routes as issued, agent-only reads named without a route
    for(const [label,handle,which] of [['Read review records',value.review?.read,'review-records'],['Reinspect task details',value.reads?.detail,'task-details']])if(handle?.http?.method==='GET')exact.append(declareControl(readLink(handle,label),'work:progress-read',which));
    for(const [label,handle] of [['Source production',value.production?.read||value.reads?.development],['Review requests',value.reads?.delivery]])
      if(handle&&!handle.http)exact.append(el('p',label+' for agents: '+handle.operation+' '+JSON.stringify(handle.payload||{})+'. This view has no human route for it.','muted'));
    body.append(exact);
  }
  // READ WHAT THIS STEP WAITS ON (wave 11, census R10). When the issued read is this task's own detail read, the
  // generic reader only reselected the open task and showed nothing; here the issued GET is sent as issued and what it
  // returned is said beside the control: the owner's blockers, or that it names none, with the time of the read.
  // Any other issued read keeps the shared reader (readLink).
  function waitsOn(handle,task){
    let own=false;try{const q=new URL(ports.operatorHTTP(handle),'http://local');own=q.pathname==='/work/state'&&q.searchParams.get('view')==='detail'&&q.searchParams.get('id')===task.id;}catch{own=false;}
    if(!own)return [readLink(handle,'Read what this step waits on')];
    const out=el('p','','work-step-waits');out.setAttribute('role','status');
    const open=button('Read what this step waits on',async()=>{pendingRead(out,'Reading what this step waits on…');
      try{const value=await request(ports.operatorHTTP(handle)),at=new Date().toLocaleTimeString();if(!current())return;
        const blockers=Array.isArray(value?.blockers)?value.blockers:[];
        out.textContent=blockers.length?'Read at '+at+' from this task\'s details: this step waits on '+blockers.map(row=>row.message||row.subject?.qualified_id||'an unnamed blocker').join('; ')+'.':'This step waits on nothing. Read at '+at+' from this task\'s details.';}
      catch(error){if(current())out.textContent='What this step waits on could not be read at '+new Date().toLocaleTimeString()+': '+error.message;}});
    open.dataset.control='work:step-waits-on';open.dataset.controlOwner=project+'::'+task.id;
    return [open,out];
  }
  function nextBlock(view,model){
    const {task}=view,next=model.next,wrap=el('div','','work-continuity-next');wrap.dataset.continuityNext=next.kind;
    wrap.append(el('h4','Next'),el('p',next.reason));
    // a pure read of what this step waits on stays available whatever is withheld or read-only (review R4)
    if(next.read?.http?.method==='GET')wrap.append(...waitsOn(next.read,task));
    else if(next.read)wrap.append(el('p','Agent read: '+next.read.operation+' '+JSON.stringify(next.read.payload||{}),'muted'));
    if(unresolved(drafts.get(task.id)?.continuity)){wrap.append(el('p','An earlier request for this task is unresolved. Its original is kept below; nothing new is offered until its outcome is known.','work-review-needed'));return wrap;}
    if(next.withheld){wrap.append(el('p',next.withheld,'work-review-needed'));return wrap;}
    if(readOnly){if(next.kind==='continue'||next.kind==='attach-proof')wrap.append(el('p','Read-only view: this action is not offered here.','muted'));return wrap;}
    if(next.kind==='continue'){
      if(next.gap)wrap.append(el('p',next.gap,'muted'));
      else wrap.append(mark(button('Continue to the approved review',activation=>send(task.id,{kind:'continue',label:'Continue',intent_id:next.intent.id,url:next.route,body:next.body},activation),'act act-write primary'),'work:continuity-continue',task.id));
      wrap.append(el('p','Continue records one handoff and one approved review request for this prepared completion. It is not a review, acceptance or completion.','muted'));
    }else if(next.kind==='attach-proof'){
      if(next.gap)wrap.append(el('p',next.gap,'muted'));else wrap.append(proofForm(view,next));
    }else if(/^record-/.test(next.kind)){
      const phase=next.kind.slice('record-'.length);
      // offered only where the existing permitted recorder for this owner phase is mounted in the same paint
      const recorderOffer=view.data.allowed_actions?.work_review,offered=!!(recorderOffer?.permitted&&(recorderOffer.phases||[]).includes(phase)&&recorderOffer.preparation?.phases?.[phase]&&view.task.review?.managed);
      if(!offered)wrap.append(el('p','The review form for this phase is not offered on this read.','muted'));
      // a distinct label from the review lifecycle's own 'Open review form' (review R5)
      else wrap.append(mark(button('Open form: '+(next.preparation?.title||recorderOffer.preparation.phases[phase].title||phase),activation=>{
        const recorder=view.box.parentElement?.querySelector?.('.operator-review-recorder');
        if(!recorder||!recorder.querySelector?.('form'))throw Error('This read offers no review form for that phase. Reinspect the task.');
        recorder.open=true;const choose=recorder.querySelector('select');
        // the person's own review draft keeps its phase; otherwise the owner's phase is preselected when it is offered
        if(choose&&!drafts.get(task.id)?.review?.dirty&&[...(choose.options||choose.children||[])].some(option=>option.value===phase)){choose.value=phase;choose.onchange?.();}
        ports.handOff?.(recorder.querySelector('select')||recorder.querySelector('summary'),activation);},'act act-read'),'work:continuity-review',task.id));
      if(next.preparation?.title)wrap.append(el('p','Owner phase: '+next.preparation.title+'. '+(next.preparation.says||''),'muted'));
    }
    return wrap;
  }
  // ONE owner-issued child read of the selected Work (a prepared completion, a preflight), read in place beside its progress.
  // Another namespace, task or a request outside the owner's contract is refused before any read; a reply is shown only when
  // it is the part, task and prepared completion that was asked for. It offers no action: actions come from the summary's Next.
  async function readChild(handle,label,activation){
    const id=sel(),view=views.get(id);
    if(!view?.fresh())throw Error('This task\'s progress is not shown here, so its step reads do not open. Open its Progress and next action and read it there; nothing was read.');
    const {url,request:asked}=admitContinuityChild(handle,{project,workId:id});
    // the slot's observation lease: a later child read of this view supersedes this read's result, error and focus;
    // a new selection or destroy retires the whole view, and with it every lease it issued
    const host=view.child,epoch=++view.childEpoch,live=()=>view.fresh()&&view.childEpoch===epoch&&host.isConnected!==false;
    const heading=el('h4',label);heading.tabIndex=-1;host.hidden=false;host.replaceChildren(heading,pendingRead(el('p','Reading the owner…','muted')));
    let value;
    try{value=admitContinuityPart(await request(url),{project,workId:id,request:asked});}
    catch(error){if(live())host.replaceChildren(heading,el('p','This read is not shown: '+error.message+' The progress above is unaffected.','error'));return;}
    if(!live())return;
    host.replaceChildren(heading);paintChild(host,value);
    if(activation)ports.handOff?.(heading,activation);
  }
  function paintChild(host,value){
    const lines={delivered:[],open:[],uncertain:[],exact:[]};
    if(value.part==='completion'){
      const intent={...value.intent,readiness:value.readiness||value.intent.readiness};intentFacts(intent,lines);
      for(const proof of value.proofs||[])lines.exact.push('Proof '+(proof.id||'not recorded')+' · slot '+(proof.slot_id||'not recorded')+' · artifact '+(proof.reference?.id||proof.artifact_id||'not recorded'));
      if(intent.meaning)host.append(el('p',intent.meaning,'muted'));
    }else if(value.part==='summary'){const model=continuityModel(value,{project});for(const key of Object.keys(lines))lines[key]=model[key];}
    else{host.append(el('p','A preflight checks a prepared request against its current owners. Nothing was recorded.','muted'));
      lines.exact.push(JSON.stringify(Object.fromEntries(Object.entries(value).filter(([key])=>!['schema_version','part','subject'].includes(key)))));}
    if(lines.delivered.length)host.append(list('Recorded',lines.delivered,'work-continuity-child-recorded'));
    if(lines.open.length)host.append(list('Still open',lines.open,'work-continuity-child-open'));
    if(lines.uncertain.length)host.append(list('Uncertain or unknown',lines.uncertain,'work-continuity-child-uncertain'));
    const next=value.next;
    if(next?.reason)host.append(el('p','The owner’s next step: '+(READINESS_WORDS[next.reason]?READINESS_WORDS[next.reason]+'.':next.reason)+' Any action it allows is offered under Next above.','muted'));
    const account=value.execution?.account;
    if(account)host.append(el('p','Source account: '+said(account.state)+(account.capacity?' · capacity '+said(account.capacity):'')+'.'+(value.execution.qualification?' '+value.execution.qualification:''),'muted'));
    const exact=el('details','','operator-exact');exact.append(el('summary','Exact identities of this read'),el('p',value.subject.qualified_id+' · work revision '+(value.subject.work_revision||'not reported'),'muted'));
    for(const row of lines.exact)exact.append(el('p',row,'muted'));
    if(value.execution?.observed_at)exact.append(el('p','Observed '+value.execution.observed_at+'.','muted'));
    host.append(exact);
  }
  function proofForm(view,next){
    const {task}=view,intent=next.action.payload.intent_id,slot=next.action.payload.slot_id,held=drafts.get(task.id)?.continuityProof,own=held&&held.intent_id===intent&&held.slot_id===slot?held:null;
    const form=el('form','','work-continuity-proof'),artifact=el('input'),digest=el('input'),artifactLabel=el('label','Proof artifact id'),digestLabel=el('label','Proof sha256');
    artifact.name='artifact_id';digest.name='expected_sha256';artifact.value=own?.id||'';digest.value=own?.sha||'';artifactLabel.append(artifact);digestLabel.append(digest);
    const save=mark(el('button','Attach arrived proof'),'work:continuity-proof',task.id);save.type='submit';const note=el('p','','work-status');
    form.append(el('p','Attach the exact retained Artifact of declared proof “'+slot+'” once it has arrived. Arrival is recorded, not reviewed or accepted.','muted'),artifactLabel,digestLabel,save,note);
    form.oninput=()=>{drafts.set(task.id,{...drafts.get(task.id),continuityProof:{intent_id:intent,slot_id:slot,id:artifact.value,sha:digest.value},dirty:true});dirty();};
    form.onsubmit=async event=>{event?.preventDefault?.();const id=artifact.value.trim(),sha=digest.value.trim();
      if(!id||!/^(sha256:)?[0-9a-f]{64}$/.test(sha)){note.textContent='Give the exact Artifact id and its sha256 digest.';note.className='work-status error';return;}
      save.disabled=true;
      try{await send(task.id,{kind:'proof',label:'proof',intent_id:intent,slot_id:slot,url:next.route,body:{...structuredClone(next.body),reference:{id,expected_sha256:sha}}},null);}
      catch(error){note.textContent=error.message;note.className='work-status error';}finally{save.disabled=false;}};
    return form;
  }
  // ONE wire per Work: kept under the Work's own draft (captured across navigation and refresh) until its outcome is known
  async function send(id,wire,activation=null){
    if(unresolved(drafts.get(id)?.continuity))throw Error('An earlier request for this task is unresolved; inspect its original outcome first.');
    // live before any paint: only a wire with no request owned by this page is shown as UNKNOWN
    const record={...wire,at:new Date().toISOString(),status:'pending'};inflight.add(record.at);
    drafts.set(id,{...drafts.get(id),continuity:record,dirty:true});dirty();outcomes.delete(id);refresh(id);
    return deliver(id,record,activation);
  }
  async function deliver(id,record,activation){
    const ticket=gen();let result;inflight.add(record.at);
    try{result=await request(record.url,record.body);}
    catch(error){
      if(drafts.get(id)?.continuity?.at!==record.at)return;
      // a thrown failure, even one carrying a parsed owner error body (HTTP 4xx/5xx), has no authoritative no-effect receipt:
      // the owner may already have written. The original wire stays UNKNOWN for Check; nothing is settled or resent.
      const says=error?.result&&!error.transport?'The owner answered the original '+record.label+' request ('+record.at+') with an error: '+(error.message||'no message')+' That answer does not show whether it took effect, so the outcome stays UNKNOWN and the original request is kept; check its outcome.':null;
      drafts.set(id,{...drafts.get(id),continuity:{...record,status:'uncertain',says,error:error?.message||'No acknowledgement.'},dirty:true});dirty();
      refresh(id);return;
    }finally{inflight.delete(record.at);}
    if(drafts.get(id)?.continuity?.at!==record.at)return;
    // a reply is this request's outcome only when it names this Work, its intent and (for proof) its slot and reference
    const foreign=replyMismatch(id,record,result);
    if(foreign){drafts.set(id,{...drafts.get(id),continuity:{...record,status:'uncertain',says:'The owner\'s reply does not name the original '+record.label+' request ('+foreign+'). The original stays UNKNOWN and is kept; check its outcome.',error:null},dirty:true});dirty();refresh(id);return;}
    settle(id,{status:'recorded',label:record.label,at:record.at,result:resultText(record,result)});clearSubmittedProof(id,record);
    if(current()&&ticket===gen()&&sel()===id){await ports.select(id);const view=views.get(id);if(view?.fresh())ports.handOff?.(view.heading,activation);}
  }
  function settle(id,outcome){clearDraft(id,['continuity']);outcomes.set(id,outcome);}
  // the typed proof draft is cleared only while it still equals what the original request sent; newer typing stays
  function clearSubmittedProof(id,record){
    if(record.kind!=='proof')return;const draft=drafts.get(id)?.continuityProof,sent=record.body?.reference||{};
    if(draft&&draft.intent_id===record.intent_id&&draft.slot_id===record.slot_id&&String(draft.id||'').trim()===sent.id&&bareSha(String(draft.sha||'').trim())===bareSha(sent.expected_sha256))clearDraft(id,['continuityProof']);
  }
  // null when a 2xx reply is this request's own outcome; otherwise what it names differently
  function replyMismatch(id,record,result){
    if(!result||typeof result!=='object'||result.ok===false)return 'no owner outcome';
    const read=result.read?.payload;if(read&&(read.namespace!==project||read.id!==id))return 'another Work';
    if(record.kind==='continue'){const continued=result.continued,event=result.event;
      if(!continued||continued.intent_id!==record.intent_id)return 'another prepared completion';
      if(event&&((event.work_id!=null&&event.work_id!==id)||(event.prepared_completion&&event.prepared_completion.intent_id!==record.intent_id)))return 'another review request';
      return null;}
    const proof=result.proof,sent=record.body?.reference||{};
    if(!proof||proof.intent_id!==record.intent_id||proof.slot_id!==record.slot_id)return 'another proof slot';
    if(proof.reference?.id!==sent.id||bareSha(proof.reference?.expected_sha256)!==bareSha(sent.expected_sha256))return 'another proof reference';
    return null;
  }
  function resultText(record,result){
    if(record.kind==='continue'){const continued=result?.continued||{},event=result?.event||{};
      return (result?.reused?'The owner returned the earlier recorded Continue; nothing was recorded twice. ':'Continue recorded. ')+'Handoff '+(continued.handoff_id||'not reported')+' and review request '+(continued.event_id||event.id||'not reported')+' ('+said(event.state)+'). A handoff and request are not a review or acceptance.';}
    return (result?.reused?'This proof was already attached; nothing was recorded twice. ':'Proof arrival recorded'+(result?.proof?.id?' as '+result.proof.id:'')+'. ')+(result?.proof?.meaning||'Arrival is not a review or acceptance.');
  }
  // the issued outcome of the ORIGINAL request, read through the same issued progress read; it never sends anything
  function originalOutcome(value,held){
    const intent=(value.completion?.intents||[]).find(row=>row.id===held.intent_id);
    if(held.kind==='continue'){
      if((value.delivery?.events||[]).some(event=>event.prepared_completion?.intent_id===held.intent_id)||intent?.state==='CONTINUED'||intent?.readiness?.state==='CONTINUED')return 'recorded';
      return intent?.readiness?.state==='READY'&&intent.readiness.basis===held.body?.expected_basis?'none':'unknown';
    }
    if(held.kind==='proof'){const slot=(intent?.readiness?.slots||[]).find(row=>row.id===held.slot_id),want=held.body?.reference||{};
      if(slot?.filled)return slot.reference?.id===want.id&&bareSha(slot.reference?.expected_sha256)===bareSha(want.expected_sha256)?'recorded':'unknown';
      return slot?'none':'unknown';}
    return 'unknown';
  }
  async function check(id){
    const view=views.get(id),held=drafts.get(id)?.continuity;
    if(!view?.path||!held)throw Error('Reinspect this task to check its original request.');
    const value=admitContinuitySummary(await request(view.path),{project,workId:id});
    if(drafts.get(id)?.continuity?.at!==held.at)return;
    const found=originalOutcome(value,held);
    if(found==='recorded'){settle(id,{status:'recorded',label:held.label,at:held.at,result:'The owner shows the original '+held.label+' request ('+held.at+') recorded. Nothing was resent.'});clearSubmittedProof(id,held);
      if(current()&&sel()===id)await ports.select(id);return;}
    const says=found==='none'?'The owner shows no effect of the original '+held.label+' request ('+held.at+') at this read. You may resend that original unchanged; the owner reconciles it as the same request.'
      :'The owner\'s current summary does not settle the original '+held.label+' request ('+held.at+'); it stays UNKNOWN.';
    drafts.set(id,{...drafts.get(id),continuity:{...held,status:found==='none'?'checked':'uncertain',says},dirty:true});dirty();refresh(id);
  }
  // repaint this Work's progress after its own request changed state; keyboard focus that was inside stays inside
  function refresh(id){
    const view=views.get(id);if(!view||!view.fresh())return;
    const doc=globalThis.document;let had=false;for(let at=doc?.activeElement;at;at=at.parentElement)if(at===view.box){had=true;break;}
    if(view.summary)paintSummary(view,view.summary);paintAttempt(id);
    const active=doc?.activeElement;
    if(had&&(!active||active===doc.body||active.isConnected===false||!view.box.contains?.(active)))(view.line.querySelector?.('button')||view.heading).focus?.({preventScroll:true});
  }
  function paintAttempt(id){
    const view=views.get(id);if(!view||!view.fresh())return;
    const line=view.line,done=outcomes.get(id);let held=drafts.get(id)?.continuity;
    // a pending wire restored from memory has no live request here: its outcome is UNKNOWN
    if(held?.status==='pending'&&!inflight.has(held.at)){held={...held,status:'uncertain',says:null};drafts.set(id,{...drafts.get(id),continuity:held,dirty:true});}
    line.replaceChildren();line.className='work-status work-continuity-attempt';
    if(held){
      const label=held.label||held.kind;
      if(held.status==='pending'){line.textContent='Sending the issued '+label+' request ('+held.at+')…';return;}
      line.className+=' error';
      line.append(el('p',held.says||'The '+label+' request sent '+held.at+' has no acknowledgement. Its outcome is UNKNOWN, which does not mean no effect. The original request is kept.'));
      const actions=el('div','','action-row');actions.append(mark(button('Check the original outcome',()=>check(id),'act act-read'),'work:continuity-check',id));
      if(held.status==='checked'&&!readOnly)actions.append(mark(button('Resend the original '+label+' unchanged',()=>{const now=drafts.get(id)?.continuity;if(now?.status!=='checked'||now.at!==held.at)throw Error('Check the original outcome again first.');
        const record={...now,status:'pending',says:null};inflight.add(record.at);drafts.set(id,{...drafts.get(id),continuity:record,dirty:true});dirty();refresh(id);return deliver(id,record,null);},'act act-write'),'work:continuity-resend',id));
      const original=el('details','','operator-exact');original.append(el('summary','Original request'),el('pre',JSON.stringify({sent:held.at,url:held.url,body:held.body,error:held.error||null},null,2)));
      line.append(actions,original);return;
    }
    if(done){line.textContent=done.status==='refused'?'The owner refused the '+done.label+' request: '+done.error+' Nothing else was sent.':done.result;if(done.status==='refused')line.className+=' error';}
  }
  return {render,paintAttempt,readChild,keep:box=>{const view=byBox.get(box);if(view)views.set(view.task.id,view);}};
}
