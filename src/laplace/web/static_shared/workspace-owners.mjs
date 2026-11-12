// SYSTEM OWNERS (app view `owners`, work.owner-discovery). Purpose: start at the declared system entry with a task
// or a subsystem and descend through owner-returned handles to the Work affecting it, then up or across, without
// knowing a project, Work id or path. Ownership: work.owner_discovery owns every fact (GET /work/discovery); this
// module paints its laplace.owner-discovery/1 results and follows each result's own `next` / `up` / `lateral`
// handle URLs. Evidence: each item is the Work owner's own evidence read; "Open evidence" follows that item's
// owner-issued HTTP read (its pin travels in it) and shows the bytes or the owner's refusal; an unavailable item
// shows the owner's capability gap; more than the first page continues in the project's Work view.
// Public contract: mountOwnerDiscovery(host,{request,onWork}) -> {back(),reinspect(),visit,destroy()}.
// Lifetime: a visit stack of immutable owner results, each with its read time. Back repaints the retained result
// marked as retained (read at its time, not reread: standing, activity and permitted actions may have changed;
// observations keep their own expiry) with an explicit Reinspect that rereads the same handle. A newer visit
// generation drops a late response, including a late evidence read. Effects: reads only; mounting or navigating
// never writes and starts nothing. "Open in project" hands the Work's legacy project-qualified handle to onWork
// (the page's existing Work view, which keeps its own drafts and leave guard).
// P1: "Edit title and purpose" mounts the plain-DOM outline (work-port-outline.mjs) over one Work port owned by this view;
// the port keeps drafts and attempts across Back and repaint and is disposed with the view. Leaving: Open in project asks
// first when a draft or unresolved save exists, and the app entry registers leaveGuard on beforeunload.
import {createWorkPort} from './work-port.mjs';
import {mountWorkOutline} from './work-port-outline.mjs';
import {createLifetime} from './selected-lifetime.mjs';   // visit generation, leases and disposal
// Owner explanation and declared source: the inventory owner's own reads, followed in this same visit stack. A source
// page is exact owner bytes; Markdown renders inertly only over the complete same-cut text (Raw stays exact).
import {markdownReading,MARKDOWN_READING_LIMIT,JOIN_PAGE_LIMIT,scalarExtent} from './workspace-material-observation.mjs';
import {pendingRead} from './pending-read.mjs';
import {declareControl} from './workspace-presentation.mjs';
const el=(tag,text='',cls='')=>{const n=document.createElement(tag);n.textContent=text;n.className=cls;return n;};
const ENTRY='/work/discovery?facet=describe';
const clock=at=>at.toISOString().replace('T',' ').slice(0,19)+' UTC';
export async function mountOwnerDiscovery(host,{request,onWork=()=>{},now=()=>new Date()}){
  const life=createLifetime();let outline=null;const stack=[];
  const port=createWorkPort({request});
  const status=el('p','','work-status');status.setAttribute('role','status');
  const body=el('div','','owner-discovery');
  host.replaceChildren(el('h2','System owners'),status,body);
  const link=(label,url,cls='act')=>{const b=el('button',label,cls);b.type='button';b.dataset.url=url;b.dataset.control='owners:read';b.dataset.controlOwner=url;b.onclick=()=>open(url);return b;};
  async function open(url,{replace=false,join=false}={}){
    life.advance();const current=life.lease();pendingRead(status,'Reading from the owner…');status.className='work-status';
    let value;
    try{value=await request(url);}catch(error){if(current()){status.textContent=error.message+' The previous view is kept.';status.className='work-status error';}return null;}
    if(!current())return null;
    if(value?.error){status.textContent=value.error;status.className='work-status error';return null;}
    const entry={url,value,at:now()},previous=stack.slice();if(replace&&stack.length)stack[stack.length-1]=entry;else{remember();stack.push(entry);}
    if(!publish(entry,previous))return null;
    status.textContent='';if(!replace)focusTitle();
    // ONE explicit Read of an explanation file asks for the formatted document: the same guarded, bounded, same-cut join is
    // started once here. Browse, a page link, Back and Reinspect never pass `join`, so they stay exact paged reads.
    if(join&&joinable(value))await assemble(entry,{auto:true});
    return value;
  }
  // an unexpected paint failure never strands a half-replaced view: the last good visit, its body, focus and Back stack return
  function publish(entry,previous){
    try{paint(entry,{retained:false});return true;}
    catch(error){stack.splice(0,stack.length,...previous);const last=stack[stack.length-1];
      if(last){try{paint(last,{retained:true});restore(last);}catch{body.replaceChildren();}}else body.replaceChildren();
      status.textContent='This owner reply could not be shown ('+(error?.message||'render failed')+'). The previous view is kept.';status.className='work-status error';return false;}
  }
  // Back restores the retained visit at its own reading position and returns focus to the control that left it
  function back(){if(stack.length<2)return false;stack.pop();life.advance();const entry=stack[stack.length-1];paint(entry,{retained:true});status.textContent='';restore(entry);return true;}
  function remember(){const entry=stack[stack.length-1];if(!entry)return;const active=globalThis.document?.activeElement;
    entry.scroll=body.scrollTop||0;entry.focusUrl=active?.dataset?.url||null;}
  function restore(entry){if(typeof entry.scroll==='number')body.scrollTop=entry.scroll;
    let target=null;try{target=entry.focusUrl?[...(body.querySelectorAll?.('button')||[])].find(node=>node.dataset?.url===entry.focusUrl)||null:null;}catch{target=null;}
    if(target)target.focus?.();else focusTitle();}
  // a new or restored visit moves keyboard focus to its title; focus never fetches
  function focusTitle(){try{const title=body.querySelector?.('h3');if(title){title.tabIndex=-1;title.focus?.();}}catch{}}
  function reinspect(){return stack.length?open(stack[stack.length-1].url,{replace:true}):null;}
  function coverage(value){const c=value.coverage||{};const p=el('p',[c.unbound,c.withheld].filter(Boolean).join(' '),'muted');p.dataset.coverage='';return p;}
  function scope(value){return el('p',value.scope?.says||'','muted');}
  function header(entry,retained){
    const nav=el('div','','owner-nav');if(stack.length>1){const b=el('button','Back to '+visitTitle(stack[stack.length-2]),'act');b.type='button';b.dataset.back='';b.onclick=back;nav.append(b);}
    const when=el('p',retained?'Retained result read at '+clock(entry.at)+'; not reread. Standing, activity and permitted actions may have changed since; observations keep their own expiry.'
      :'Read from the owner at '+clock(entry.at)+'.',retained?'owner-retained':'muted');when.dataset.freshness=retained?'retained':'fresh';nav.append(when);
    if(retained){const again=el('button','Reinspect','act');again.type='button';again.dataset.reinspect='';again.onclick=reinspect;nav.append(again);}
    return nav;
  }
  // Back names the retained visit it returns to
  const visitTitle=entry=>{const v=entry?.value||{};return v.facet==='describe'?'System entry':v.facet==='discover'?(v.subsystem?.reference?.identity?.id||'subsystem'):v.facet==='inspect'?(v.title||'Work'):v.schema_version==='laplace.source-owner-inventory/1'?'declared source':v.facet==='source-input'?(v.input?.path||'source page'):'previous view';};
  function paintDescribe(value){
    const form=el('form','','owner-task');const input=el('input');input.name='task';input.placeholder='Describe the task, e.g. browser workflow interface';input.value=value.selection?.task||'';
    const find=declareControl(el('button','Find owners'),'owners:find');find.type='submit';form.append(input,find);
    form.onsubmit=event=>{event.preventDefault();open('/work/discovery?'+new URLSearchParams({facet:'describe',task:input.value}));};
    body.append(el('p',value.purpose||'','muted'),form);
    if(value.selection){const section=el('section','','owner-choices');section.append(el('h3','Subsystems your task names'),el('p',value.selection.says,'muted'));
      for(const choice of value.selection.choices){const row=el('div','','owner-row');row.append(link(choice.reference.identity.id,choice.next.http.url),el('span',' · '+choice.terms.join(', '),'muted'));section.append(row);}
      body.append(section);}
    const all=el('section','','owner-subsystems');all.append(el('h3','All subsystems'));
    for(const item of value.subsystems||[]){const row=el('div','','owner-row');row.append(link(item.reference.identity.id,item.next.http.url),
      el('span',' '+item.layer+' · '+item.affecting_work.bound_in_scope+' bound Work','muted'),el('p',item.summary,'muted'));all.append(row);}
    body.append(all);
  }
  function paintDiscover(value){
    const s=value.subsystem;body.append(el('h3',s.reference.identity.id+' ('+s.layer+')'),el('p',s.summary,'muted'),el('p',value.up_summary?.says||''));
    // the declared explanation and source come first, through the inventory owner's own issued reads
    const explain=el('section','','owner-explanation');explain.append(el('h4','Explanation and source'));
    const declared=s.explanation||[];
    explain.append(el('p',declared.length?'Declared explanation: '+declared.join(', '):'This owner declares no explanation document.','muted'));
    const reads=el('div','','owner-actions');
    if(s.explanation_read?.http?.url)reads.append(link('Read the explanation',s.explanation_read.http.url));
    const inputs=s.source_inputs_read||s.source_inventory_read;if(inputs?.http?.url)reads.append(link('Browse declared source',inputs.http.url));
    explain.append(reads);body.append(explain);
    const list=el('ul','','owner-work');
    for(const item of value.items||[]){const li=el('li');li.append(link(item.title||item.reference.identity.id,item.next.http.url),el('span',' · '+(item.status||'')+' · '+item.relations.join(', '),'muted'));list.append(li);}
    body.append(list);if(value.next)body.append(link('More',value.next.http.url));
    body.append(link('Up to the system',value.up_summary.up.http.url,'act owner-up'));
  }
  // one evidence item: the owner's availability and pin; an available owner read is followed, never a built path
  function evidenceItem(item,value,section){
    const row=el('div','','owner-evidence-item');row.append(el('p',item.path||item.owner,'mono'));
    if(item.consumed_revision)row.append(el('p','Pinned '+item.consumed_revision,'muted'));
    if(item.available&&item.http?.url){
      const result=el('div','','owner-evidence-read');const read=el('button','Open evidence','act');read.type='button';read.dataset.url=item.http.url;
      read.onclick=async()=>{const current=life.lease();result.replaceChildren(pendingRead(el('p','Reading through its owner…','muted')));
        try{const bytes=await request(item.http.url);if(!current())return;
          result.replaceChildren(el('pre',typeof bytes?.content==='string'?bytes.content:JSON.stringify(bytes,null,2),'owner-evidence-bytes'));}
        catch(error){if(!current())return;const refusal=el('p','The evidence owner refused this read: '+error.message,'error');refusal.dataset.refusal='';result.replaceChildren(refusal);}};
      row.append(read,result);
      if(item.native_capability_gap)row.append(el('p',item.native_capability_gap,'muted'));
    }else row.append(el('p','Unavailable here: '+(item.capability_gap||'the owner reports no read for this evidence.'),'muted'));
    section.append(row);
  }
  // Next by kind: what each owner action IS at this read. A GET is an inspect-only read; a POST carrying the owner's complete
  // payload is an owner-issued template (shown, never run from here); a POST needing authored fields needs the project form.
  // The owner's readiness word stays separate as view-level standing: it recommends no action and issues no Continue.
  const nextKind=a=>a.http?.method==='GET'?'Inspect-only read (GET)':(a.http?.payload||a.payload)?'Owner-issued template; not run from here':'Needs a form in the project'+(a.requires?': '+a.requires:'');
  function paintInspect(value){
    const ident=value.reference?.identity||{};
    body.append(el('h3',value.title||''),el('p',value.purpose||''));
    if(value.version?.status&&value.version.status!=='UNVERSIONED')body.append(el('p','Requested revision: '+value.version.status,'muted'));
    const facts=el('dl','','owner-facts');
    const fact=(term,text,into=facts)=>{if(text==null||text==='')return;into.append(el('dt',term),el('dd',String(text)));};
    fact('Standing',value.standing?.status);
    // the owner's activity sentence verbatim; a Stop applies to one selected turn, never to the Work
    fact('Activity',value.activity?.qualification);
    if(['requested','starting','waiting','running'].includes(value.activity?.state))fact('Stop','Stop applies to a selected turn, not to this Work; select the turn in its conversation.');
    for(const blocker of value.blockers||[])fact('Blocked',blocker.sentence);
    body.append(facts);
    // Next is painted below as usable controls (after the project door is defined); its exact owner facts live under About this read
    // timestamps, observation standing and identities behind one disclosure
    const about=el('details','','owner-about'),ids=el('dl','','owner-facts');about.append(el('summary','About this read'));
    for(const seen of value.activity?.observations||[])fact('Observation',[seen.observed_state,'observed '+seen.observed_at,seen.expires_at?'expires '+seen.expires_at:'no expiry',seen.current?'current at this read':'not current at this read'].join(' · '),ids);
    fact('Work',[ident.namespace,ident.id].filter(Boolean).join(' :: '),ids);fact('Work revision',value.reference?.version?.work_revision,ids);
    fact('Binding revision',value.binding?.binding_revision,ids);fact('Read cut',value.read_cut?.work?.revision,ids);
    // the owner's readiness word and each action's exact kind, method and route are facts here, never a recommendation
    fact('Owner readiness',value.next?.readiness,ids);
    for(const a of value.next?.actions||[])fact(a.name,(a.permitted?nextKind(a):'Not permitted at this read')+(a.http?.method?' · '+a.http.method+' '+String(a.http.url||'').split('?')[0]:''),ids);
    if(value.next)fact('Permitted at this read',(value.next.actions||[]).filter(a=>a.permitted).map(a=>a.name).join(', ')||'none',ids);
    about.append(ids);
    // leaving for the project page does not carry this view's port: with a draft or an unresolved save it asks first
    const toProject=()=>{const go=()=>onWork({project:ident.namespace,id:ident.id,read:value.legacy?.read});
      if(!port.hasUnresolved())return go();
      body.querySelector?.('.owner-leave')?.remove?.();
      const ask=el('div','','owner-leave');ask.setAttribute('role','alert');
      ask.append(el('p','You have an unsaved title/purpose draft or a save whose outcome is unresolved. Opening the project leaves this view: they are not carried there.'));
      const anyway=el('button','Open in project anyway (the draft is not carried)','act');anyway.type='button';anyway.onclick=()=>{ask.remove?.();go();};
      const stay=el('button','Stay here','act');stay.type='button';stay.onclick=()=>ask.remove?.();ask.append(anyway,stay);body.append(ask);};
    // Next: each permitted owner action as a usable control of its kind. A GET opens that owner read in this view (inspect-only);
    // `task` opens this view's existing title/purpose editor; any other POST, with or without an owner-issued template, opens the
    // project's existing form through the project page. One primary; the readiness word recommends nothing and stays under About.
    const openEdit=async()=>{outline?.destroy();const place=el('div','','owner-work-edit');body.append(place);outline=mountWorkOutline(place,port);
      try{await port.dispatch({type:'select',project:ident.namespace,id:ident.id,read:value.legacy.read});}catch(error){status.textContent=error.message;status.className='work-status error';}};
    const canEdit=!!(ident.namespace&&value.legacy?.read),next=el('section','','owner-next'),row=el('div','','owner-actions');next.append(el('h4','Next'));
    const actions=(value.next?.actions||[]).filter(a=>a.permitted);let editOffered=false,primary=null;
    for(const a of actions){const name=String(a.name||'').replaceAll('_',' '),template=!!(a.http?.payload||a.payload);let b;
      if(a.http?.method==='GET'&&a.http.url){b=link(name+' · inspect',a.http.url);b.dataset.nextKind='inspect';}
      else if(a.name==='task'&&canEdit){b=el('button','Edit title and purpose','act');b.type='button';b.onclick=openEdit;b.dataset.nextKind='form';editOffered=true;}
      else{b=el('button',name+(template?' · owner template · open in project':' · open the project form'),'act');b.type='button';b.onclick=toProject;b.dataset.nextKind=template?'template':'form';}
      if(!primary){primary=b;b.className='act primary';}row.append(b);}
    if(!value.next)next.append(el('p','Unknown at this read: the owner issued no next.','muted'));else if(!actions.length)next.append(el('p','No action is permitted at this read.','muted'));
    next.append(row);if(value.next?.says)next.append(el('p',value.next.says,'muted'));body.append(next,about);
    if(value.evidence?.items?.length){const ev=el('section','','owner-evidence');ev.append(el('h4','Evidence ('+value.evidence.total+')'),el('p',value.evidence.says,'muted'));
      for(const item of value.evidence.items)evidenceItem(item,value,ev);
      if(value.evidence.truncated){const all=el('button','All '+value.evidence.total+' evidence reads in the project Work','act');all.type='button';all.dataset.url=value.evidence.continuation?.http?.url||'';all.onclick=toProject;ev.append(all);}
      body.append(ev);}
    const related=el('section','','owner-related');related.append(el('h4','Related'));
    for(const item of [...(value.up||[]),...(value.lateral||[])]){if(!item.next)continue;const label=item.title||item.reference?.identity?.id||item.says||'System entry';
      const row=el('div','','owner-row');row.append(el('span',item.relation+': ','muted'),link(label,item.next.http.url));related.append(row);}
    body.append(related);
    // one secondary door to the project page; the editor is the `task` Next control when the owner permits it, otherwise offered here
    const open_=el('button','Open in project','act');open_.type='button';open_.onclick=toProject;body.append(open_);
    if(canEdit&&!editOffered){const edit=el('button','Edit title and purpose','act');edit.type='button';edit.onclick=openEdit;body.append(edit);}
  }
  // one bounded page of the inventory owner's declared inputs; each row opens its exact body in this visit stack
  function paintInventory(value){
    const c=value.coverage||{},id=value.reference?.identity?.id||'';
    body.append(el('h3',(c.role==='explanation-source'?'Explanation of ':'Declared source of ')+id),
      el('p',(c.returned??0)+' of '+(c.known??0)+(c.role?' '+c.role+' inputs':' declared inputs')+(c.declared_inputs!=null?' (of '+c.declared_inputs+' declared)':'')+' at this inventory cut.','muted'));
    const list=el('ul','','owner-inputs');
    for(const row of value.items||[]){const li=el('li','','owner-input'),url=row.read?.workspace_read?.http?.url;
      const read=url?link(row.path,url,'act owner-input-read'):el('span',row.path,'mono');
      // in the explanation inventory the person's click on a Markdown file IS the request to read it: that one click joins
      if(url&&c.role==='explanation-source'&&MARKDOWN_PATH.test(row.path||'')){read.dataset.join='explanation';read.onclick=()=>open(url,{join:true});}
      li.append(read,el('span',' · '+(row.roles||[]).join(', ')+' · '+(row.bytes??'?')+' bytes','muted'));
      if(!url)li.append(el('p','Not readable here: '+(row.read_unavailable||'the owner issued no workspace read for this row.'),'muted'));
      list.append(li);}
    body.append(list);
    if(!(value.items||[]).length)body.append(el('p','No declared input with this role is listed at this cut.','muted'));
    const next=value.pagination?.next_read?.http?.url;if(next)body.append(link('Next inputs',next));
    for(const gap of c.unavailable||[])body.append(el('p',(gap.state||'')+': '+(gap.declaration||(gap.declarations||[]).join(', '))+' · '+(gap.reason||''),'muted'));
    if(value.execution_evidence?.qualification)body.append(el('p',value.execution_evidence.qualification,'muted'));
  }
  // one exact page of a declared input; Markdown renders inertly only over the complete same-cut text
  function paintSourceInput(entry){
    const value=entry.value,input=value.input||{},page=value.pagination||{},shown=Array.from(value.content||'').length;
    // the coverage label comes from what is painted: the complete joined text, or this page's own extent
    body.append(el('h3',input.path||'Declared source'),el('p',(input.roles||[]).join(', ')+' · '+(input.bytes??'?')+' bytes · '+(entry.assembled!=null?'Complete · '+scalarExtent(entry.assembled)+' characters at this cut':'characters '+value.offset+'–'+(value.next_offset??(value.offset+shown))),'muted'));
    // READING CONTROLS ABOVE THE TEXT: the bounded-page notice, paging, the complete action or its Cancel, the owner's restart
    // and any refusal are in this bar, so a long first page is never scrolled through to reach them
    const nav=el('div','','owner-actions owner-reading-bar'),reading=el('div','','owner-source-reading');nav.dataset.readingBar='';body.append(nav,reading);
    // a single page is whole only when its terminal fields agree: no remaining offset, no truncation, no continuation
    const issued=page.next_read?.http?.url,contradiction=entry.assembled==null&&!issued&&(value.next_offset!=null||value.truncated===true);
    const markdown=/\.(md|markdown)$/i.test(input.path||''),complete=entry.assembled!=null||(value.offset===0&&value.next_offset==null&&value.truncated!==true&&!issued);
    const text=entry.assembled??value.content??'';
    if(markdown&&complete)reading.append(markdownReading(text));
    else{reading.append(el('pre',text,'owner-source-bytes'));if(markdown&&!contradiction)nav.append(el('p','Bounded text page. The rendered reading needs the complete document at this same cut.','muted'));}
    if(contradiction)nav.append(el('p','The owner reports more text after this page but issued no continuation; this page stays as exact text.','error'));
    if(entry.assembled==null){if(page.previous_read?.http?.url)nav.append(link('Previous page',page.previous_read.http.url));
      if(page.next_read?.http?.url)nav.append(link('Next page',page.next_read.http.url));
      // only the exact first page may start a complete reading; a later page stays paged
      if(markdown&&page.next_read?.http?.url){if(value.offset===0){if(entry.joining){const wait=el('p','Reading the complete document from its owner… ','muted');wait.setAttribute('role','status');const cancel=el('button','Cancel this read','act');cancel.type='button';cancel.dataset.readingControl='cancel';cancel.onclick=()=>cancelJoin(entry,cancel);nav.append(wait,cancel);}
          else{const whole=el('button','Read the complete document','act primary');whole.type='button';whole.dataset.readingControl='complete';whole.onclick=()=>assemble(entry);nav.append(whole);}}
        else nav.append(el('p','Only the first page can start a complete reading; this page stays paged.','muted'));}}
    if(page.restart_read?.http?.url)nav.append(link('Current inventory',page.restart_read.http.url));
    // a refused or failed join says why here, beside the complete action and the owner's Current inventory restart
    if(entry.refusal){const refusal=el('p',entry.refusal+' The page you were reading is kept.','error');refusal.setAttribute('role','alert');refusal.dataset.refusal='';nav.append(refusal);}
    body.append(el('p',value.qualification||'','muted'));
  }
  // joins this visit's own continuations; a changed cut, pin or path refuses the join and keeps the page being read
  // One join per visit, from the exact first page through issued continuations only: same cut, pin and path, each page
  // starting where the previous ended in the owner's coordinates and making progress, with bounded attempts and text.
  const MARKDOWN_PATH=/\.(md|markdown)$/i;
  // eligible for the one automatic join: the exact first page of a Markdown input whose owner issued a continuation
  const joinable=value=>value?.facet==='source-input'&&MARKDOWN_PATH.test(value.input?.path||'')&&value.offset===0&&!!value.pagination?.next_read?.http?.url;
  // FOCUS ACROSS A REPAINT OF THE SAME VISIT. A repaint replaces every node of the view, so a control the person moved to while a
  // read was delayed is named by what it is (Back, Reinspect, or its owner handle and label) and focused again on the repainted
  // view. Focus outside this view is never touched. The reading's own controls, its trigger, no focus at all, or a control the
  // repaint no longer offers are the consumed read: only then does the reading control or the heading take focus. Focus never fetches.
  const focusKey=node=>{const d=node?.dataset;return !d?null:d.back!=null?'back':d.reinspect!=null?'reinspect':typeof d.url==='string'&&d.url?'url:'+d.url+'\n'+(node.textContent||''):null;};
  function focusIntent(trigger){
    const active=globalThis.document?.activeElement||null;
    if(!active||active===globalThis.document?.body||active===trigger||active.isConnected===false||active.dataset?.readingControl!=null)return {owned:true,outside:false,key:null};
    let inside=false;try{inside=body.contains?.(active)===true;}catch{inside=false;}
    return {owned:false,outside:!inside,key:inside?focusKey(active):null};
  }
  function refocus(intent){
    if(!intent?.key)return false;let target=null;
    try{target=[...(body.querySelectorAll?.('button')||[])].find(node=>focusKey(node)===intent.key)||null;}catch{target=null;}
    if(!target)return false;try{target.focus?.();}catch{}return true;
  }
  // repaint the visit on screen in place (a join began, was cancelled or refused). Focus goes to the named reading control only
  // while the consumed read still owns it; a surviving control the person has since chosen is focused again after the repaint.
  function repaintReading(entry,control,trigger=null){
    if(stack[stack.length-1]!==entry)return;
    const intent=focusIntent(trigger);
    try{paint(entry,{retained:!!entry.shownRetained});}catch{return;}
    if(intent.outside||(!intent.owned&&refocus(intent)))return;
    try{[...(body.querySelectorAll?.('button')||[])].find(node=>node.dataset?.readingControl===control)?.focus?.();}catch{}
  }
  // Cancel belongs to this one join: its GET is aborted where the transport supports it and its late reply joins nothing
  function cancelJoin(entry,cancel){const token=entry.joinToken;if(!token)return;token.cancelled=true;token.controller?.abort();entry.joining=false;entry.joinToken=null;entry.refusal=null;
    status.textContent='Complete reading cancelled. The page you were reading is kept.';status.className='work-status';repaintReading(entry,'complete',cancel);}
  async function assemble(entry,{auto=false}={}){
    if(entry.joining)return;
    const value=entry.value,current=life.lease(),trigger=globalThis.document?.activeElement||null;
    // every refusal keeps the exact page and says why in the reading bar above it (and in the view status)
    const refuse=message=>{entry.refusal=message;status.textContent=message+' The page you were reading is kept.';status.className='work-status error';repaintReading(entry,'complete',trigger);};
    if(value.offset!==0)return refuse('Only the first page can start a complete reading; this page stays paged.');
    let text=value.content||'',next=value.pagination?.next_read?.http?.url,at=value.next_offset,attempts=0;
    if(next&&Number.isSafeInteger(at)&&at<=value.offset)return refuse('The first page made no progress, so nothing was joined.');
    // owner offsets are Unicode scalars: the claimed next offset must match the actual returned text (never UTF-16)
    if(next&&Number.isSafeInteger(at)&&at!==value.offset+scalarExtent(text))return refuse('The first page\'s own text does not end where the owner says the next page starts, so nothing was joined.');
    const token={cancelled:false,controller:typeof AbortController==='function'?new AbortController():null},live=()=>current()&&!token.cancelled;
    entry.joining=true;entry.joinToken=token;entry.refusal=null;pendingRead(status,'Reading the complete document from its owner…');status.className='work-status';repaintReading(entry,'cancel',trigger);
    try{while(next){if(++attempts>JOIN_PAGE_LIMIT)throw Error('The document needs more pages than a complete reading allows; use its pages.');
        if(!Number.isSafeInteger(at))throw Error('The owner gave no position for the next page, so nothing was joined.');
        if(text.length>MARKDOWN_READING_LIMIT)throw Error('This document is longer than the rendered-reading limit; use its pages.');
        const page=await request(next,undefined,token.controller?{signal:token.controller.signal}:undefined);if(!live())return;
        if(page?.cut!==value.cut||page?.input?.sha256!==value.input?.sha256||page?.input?.path!==value.input?.path||page?.units!==value.units)
          throw Error('The source changed between pages, so nothing was joined. Read the current inventory.');
        const more=page.pagination?.next_read?.http?.url,chunk=page.content||'';
        if(page.offset!==at)throw Error('The next page does not continue where the previous one ended, so nothing was joined.');
        if(more&&(!Number.isSafeInteger(page.next_offset)||page.next_offset<=page.offset||!chunk))throw Error('The next page made no progress, so nothing was joined.');
        if(more&&page.next_offset!==page.offset+scalarExtent(chunk))throw Error('A page\'s own text does not end where the owner says the next page starts, so nothing was joined.');
        if(!more&&(page.next_offset!=null||page.truncated===true))throw Error('The last page says the document continues, but the owner issued no continuation, so nothing was joined.');
        text+=chunk;
        if(text.length>MARKDOWN_READING_LIMIT)throw Error('This document is longer than the rendered-reading limit; use its pages.');
        at=page.next_offset;next=more;}}
    catch(error){if(live()){entry.joining=false;entry.joinToken=null;refuse(error.message);}return;}
    finally{if(entry.joinToken===token&&!live()){entry.joining=false;entry.joinToken=null;}}
    if(!live())return;entry.joining=false;entry.joinToken=null;entry.assembled=text;entry.refusal=null;
    // later intent wins: the reading returns to its beginning only while the consumed read still owns focus. Focus the person
    // moved to a surviving control of this view (Back, Current inventory) is resolved again on that same control after the
    // repaint; focus outside this view is left exactly where it is, with the reading position untouched.
    const intent=focusIntent(trigger);
    try{paint(entry,{retained:false});status.textContent='';
      // the complete reading starts at its beginning in the pane that actually scrolls: the view's own top (Back and the read
      // time) is brought into reach with the heading under it, and the heading takes focus without scrolling past them
      if(!intent.outside&&!(!intent.owned&&refocus(intent))){body.scrollTop=0;try{const title=body.querySelector?.('h3');if(title){title.tabIndex=-1;(body.firstElementChild||title).scrollIntoView?.({block:'start'});title.focus?.({preventScroll:true});}}catch{}}}
    catch(error){delete entry.assembled;try{paint(entry,{retained:false});}catch{body.replaceChildren();}
      status.textContent='The complete document could not be shown ('+(error?.message||'render failed')+'). The page you were reading is kept.';status.className='work-status error';}
  }
  function paint(entry,{retained}){
    const value=entry.value;entry.shownRetained=!!retained;outline?.destroy();outline=null;body.replaceChildren(header(entry,retained));
    if(value.facet==='describe')paintDescribe(value);else if(value.facet==='discover')paintDiscover(value);
    else if(value.facet==='inspect')paintInspect(value);
    else if(value.schema_version==='laplace.source-owner-inventory/1')paintInventory(value);
    else if(value.facet==='source-input')paintSourceInput(entry);
    else body.append(el('pre',JSON.stringify(value,null,2)));
    body.append(scope(value),coverage(value));
  }
  await open(ENTRY);
  return {back,reinspect,get visit(){return stack.length?stack[stack.length-1]:null;},open,port,get hasDraft(){return port.hasUnresolved();},
    leaveGuard(event){if(life.disposed||!port.hasUnresolved())return false;event?.preventDefault?.();if(event)event.returnValue='';return true;},
    destroy(){if(!life.dispose())return;outline?.destroy();port.dispatch({type:'dispose'});}};
}
