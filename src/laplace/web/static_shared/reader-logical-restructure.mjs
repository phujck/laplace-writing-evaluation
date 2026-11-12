// LOGICAL RESTRUCTURE (split and combine planned units). Purpose: the dialog that previews and
// applies a logical split or merge of paragraph plans through the reader-plan owner's structural
// calls. Ownership: reader_restructure (owner) issues the preview and apply calls with their
// guards; reader-restructure.mjs validates shapes and renders outcomes; this module owns the
// dialog and the draft. Public contract: openLogicalRestructure(options),
// validateLogicalPreparation, createLogicalDraft. Inputs: the owner's prepared call (from the
// detail row or the structure subject read) and the paragraph; outputs: a dialog, then the
// owner's receipt through onSaved. Currentness: the call's expected revisions; a changed plan
// refuses at the owner and the retained draft stays. Storage: the dialog's own draft only.
import {showReaderDialog,labelReaderControl,lockReaderDialog} from './reader-state.mjs';
import {RESTRUCTURE_SCHEMA,validateRestructurePreview,validateRestructureGuards,restructurePreviewSubmission,
  restructureApplySubmission,restructureFollowThroughSubmission,validateRestructureEffect,renderRestructureOutcome,inspectStructuralInput,openMetadataReconciliation} from './reader-restructure.mjs';

const el=(tag,text='',className='')=>{const node=document.createElement(tag);node.textContent=text;node.className=className;return node;};
const clone=value=>structuredClone(value);
const canonical=value=>Array.isArray(value)?value.map(canonical):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(key=>[key,canonical(value[key])])):value;
const equal=(a,b)=>JSON.stringify(canonical(a))===JSON.stringify(canonical(b));
const keySet=rows=>rows.map(row=>row.id||row.paragraph_id);
const unique=rows=>Array.isArray(rows)&&rows.every(row=>typeof (row.id||row.paragraph_id)==='string')&&new Set(keySet(rows)).size===rows.length;
const dispositions={assign:'Assign to new units','retain-retired':'Keep with the retired unit','retain-unresolved':'Retain for scoped review'};

export function validateLogicalPreparation(value,{project,sectionId,kind,draft}={}){
  validateRestructurePreview(value,{project,kind,draft});validateRestructureGuards(value.guards,value.kind);
  if(value.section_id!==sectionId||!kind?.startsWith('logical-')||!unique(value.successors)||
      !unique(value.attachment_inventory)||!unique(value.occurrence_inventory)||typeof value.ready!=='boolean'||!Array.isArray(value.needs_input))
    throw Error('The logical owner did not return the exact successor and attachment inventory.');
  const ids=value.successors.map(row=>row.paragraph_id);
  if(new Set(ids).size!==ids.length||ids.some(id=>typeof id!=='string'||value.draft.paragraph_ids.includes(id))||kind==='logical-split'&&ids.length<2||kind==='logical-merge'&&ids.length!==1)
    throw Error('Use only the unused successor identities issued for this operation.');
  if(!equal(Object.keys(value.guards.expected_reader_basis).sort(),[...value.draft.paragraph_ids].sort())||
      Object.values(value.guards.expected_reader_basis).some(row=>row.project!==project||row.section_id!==sectionId))
    throw Error('The logical reader basis belongs to different predecessor units.');
  if(!Array.isArray(value.predecessors)||!equal(value.predecessors.map(row=>row.paragraph_id).sort(),[...value.draft.paragraph_ids].sort())||
      value.predecessors.some(row=>row.values?.paragraph_id!==row.paragraph_id))throw Error('The exact current predecessor descriptions are unavailable.');
  for(const row of value.successors)if(!Array.isArray(row.fields)||!row.fields.some(field=>field.name==='function')||!row.fields.some(field=>field.name==='proposition'))
    throw Error('The new unit has no authored function and proposition fields.');
  for(const row of value.attachment_inventory)if(!Array.isArray(row.allowed_dispositions)||!row.allowed_dispositions.length||row.allowed_dispositions.some(value=>!Object.hasOwn(dispositions,value))||
      !Array.isArray(row.allowed_successor_ids)||new Set(row.allowed_successor_ids).size!==row.allowed_successor_ids.length||row.allowed_successor_ids.some(id=>!ids.includes(id)))
    throw Error('An attachment has no exact permitted disposition choices.');
  return value;
}

export function createLogicalDraft(value){
  const authored=value.draft||{};
  return {paragraph_ids:[...authored.paragraph_ids],...(value.kind==='logical-split'?{successor_count:value.successors.length}:{}),
    successors:value.successors.map(row=>({paragraph_id:row.paragraph_id,changes:clone(authored.successors?.find(item=>item.paragraph_id===row.paragraph_id)?.changes||Object.fromEntries(Object.entries(row.values||{}).filter(([,value])=>value!=='')))})),
    attachment_assignments:clone(authored.attachment_assignments||[]),occurrence_assignments:clone(authored.occurrence_assignments||[])};
}

export async function openLogicalRestructure({project,action,kind,plan,paragraph,request,read,onRead,onSaved=async()=>{},opener,isCurrent=()=>true,storage=globalThis.sessionStorage}={}){
  const sectionId=action?.payload?.section_id;
  if(!sectionId||!['logical-split','logical-merge'].includes(kind))throw Error('Choose the exact planned unit’s logical action.');
  const dialog=el('dialog','','spine-binding-dialog reader-logical-dialog'),status=el('p','','work-status'),setup=el('section'),form=el('form','','work-form'),preview=el('section'),outcome=el('section'),controls=el('div','','spine-actions');
  const heading=kind==='logical-split'?'Split planned unit':'Combine planned units';
  dialog.append(el('h2',heading),el('p','Create new planned units and retire the selected identities. Paragraph text keeps its current layout.','muted'),setup,form,preview,outcome,status,controls);
  status.setAttribute('role','status');form.onsubmit=event=>event.preventDefault();
  let alive=true,busy=false,settled=false,uncertain=false,basis=null,prepared=null,stale=null,dirty=false,outcomeController=null;
  const values=new Map(),attachments=new Map(),occurrences=new Map(),retainedChoices=new Map();
  const storageKey='laplace:reader-state-draft:'+project+':'+JSON.stringify(['paragraph-restructure',sectionId,kind,action.payload.draft.paragraph_ids]);
  const fresh=()=>alive&&dialog.isConnected!==false&&isCurrent();
  const say=(text,error=false)=>{status.textContent=text;status.className=error?'work-status error':'work-status';};
  const perform=async run=>{
    if(busy||!fresh())return;busy=true;const unlock=lockReaderDialog(dialog);
    try{await run();}catch(error){if(fresh())say(error.message+' Your choices remain here.',true);}finally{
      unlock();busy=false;apply.disabled=!prepared?.ready||!prepared.apply_action||prepared.apply_action.permitted===false||settled||uncertain||!!stale;review.disabled=settled||!basis;
      if(settled||uncertain)for(const node of form.querySelectorAll('input,textarea,select'))node.disabled=true;
      for(const node of outcome.querySelectorAll('button'))node.disabled=false;
    }
  };
  const button=(label,run)=>{const node=el('button',label);node.type='button';node.onclick=()=>perform(run);return node;};
  const persist=()=>{if(!basis||!dirty)return;try{storage?.setItem(storageKey,JSON.stringify({project,sectionId,kind,basis,values:[...values],attachments:[...attachments],occurrences:[...occurrences],retainedChoices:[...retainedChoices]}));}catch(error){say('Local choices could not be retained for reload. Keep this dialog open: '+error.message,true);}};
  const forget=()=>{try{storage?.removeItem(storageKey);}catch(error){say('The operation is recorded, but its old local draft could not be cleared: '+error.message,true);}};
  const touch=()=>{dirty=true;prepared=null;preview.replaceChildren();apply.disabled=true;persist();};
  const labelled=(host,label,input)=>{const wrapper=el('label',label,input.type==='checkbox'?'reader-logical-choice':'');labelReaderControl(wrapper,input,label);wrapper.append(input);host.append(wrapper);return input;};
  const inspectInput=(handle,label)=>inspectStructuralInput(handle,{project,request,onRead,label,opener:document.activeElement,isCurrent:fresh});
  const inspect=(host,handle,label)=>{if(handle)host.append(button(label,()=>inspectInput(handle,label)));};
  const input=(host,label,value='',multiline=false)=>{const node=el(multiline?'textarea':'input');node.value=value;if(multiline)node.rows=3;return labelled(host,label,node);};
  const draft=()=>({paragraph_ids:[...basis.draft.paragraph_ids],...(kind==='logical-split'?{successor_count:basis.successors.length}:{}),
    successors:basis.successors.map(row=>({paragraph_id:row.paragraph_id,changes:clone(values.get(row.paragraph_id)||{})})),
    attachment_assignments:basis.attachment_inventory.flatMap(row=>attachments.has(row.id)?[clone(attachments.get(row.id))]:[]),
    occurrence_assignments:basis.occurrence_inventory.flatMap(row=>occurrences.has(row.id)?[clone(occurrences.get(row.id))]:[])});
  const destinationChecks=(host,chosen,changed,allowed=basis.successors.map(row=>row.paragraph_id))=>{
    for(const [index,row]of basis.successors.entries()){
      if(!allowed.includes(row.paragraph_id))continue;
      const checkbox=el('input');checkbox.type='checkbox';checkbox.checked=chosen.includes(row.paragraph_id);
      labelled(host,'New unit '+(index+1),checkbox);checkbox.onchange=()=>changed(row.paragraph_id,checkbox.checked);
    }
  };
  function seed(value){
    const authored=createLogicalDraft(value);
    for(const row of authored.successors)if(!values.has(row.paragraph_id))values.set(row.paragraph_id,clone(row.changes));
    for(const row of authored.attachment_assignments)if(!attachments.has(row.attachment_id))attachments.set(row.attachment_id,clone(row));
    for(const row of authored.occurrence_assignments)if(!occurrences.has(row.occurrence_id))occurrences.set(row.occurrence_id,clone(row));
  }
  function adopt(value){
    if(basis){
      const ids=new Set(value.successors.map(row=>row.paragraph_id));
      const currentAttachments=new Map(value.attachment_inventory.map(row=>[row.id,row])),currentOccurrences=new Set(value.occurrence_inventory.map(row=>row.id));
      for(const [id,changes]of values)if(!ids.has(id)&&Object.keys(changes).length)retainedChoices.set('unit:'+id,{label:'Earlier new-unit text',text:Object.values(changes).join('\n')});
      for(const [id,choice]of attachments){
        const current=currentAttachments.get(id),destinations=choice.successor_ids.filter(id=>ids.has(id)&&current?.allowed_successor_ids.includes(id));
        if(!current||!equal(destinations,choice.successor_ids)||!current.allowed_dispositions.includes(choice.disposition))retainedChoices.set('attachment:'+id,{label:'Earlier attachment assignment',text:JSON.stringify(choice)});
        if(!current||!current.allowed_dispositions.includes(choice.disposition)||choice.disposition==='assign'&&!destinations.length)attachments.delete(id);
        else attachments.set(id,{...choice,successor_ids:destinations});
      }
      for(const [id,choice]of occurrences){
        const destinations=choice.successor_ids.filter(id=>ids.has(id));
        if(!currentOccurrences.has(id)||!equal(destinations,choice.successor_ids))retainedChoices.set('occurrence:'+id,{label:'Earlier source assignment',text:JSON.stringify(choice)});
        if(!currentOccurrences.has(id)||choice.successor_ids.length&&!destinations.length)occurrences.delete(id);
        else occurrences.set(id,{...choice,successor_ids:destinations});
      }
    }
    basis=value;seed(value);stale=null;prepared=null;renderForm();
  }
  function renderForm(){
    form.replaceChildren();setup.replaceChildren();
    const prior=el('details');prior.append(el('summary','Current units being retired'));
    for(const row of basis.predecessors){prior.append(el('h4',row.values.proposition||row.values.function||'Current planned unit'));
      if(row.values.function)prior.append(el('p',row.values.function));if(row.values.qualification)prior.append(el('p',row.values.qualification));inspect(prior,row.read,'Inspect current planned unit');}
    form.append(prior);
    const units=el('section');units.append(el('h3','New planned units'));
    for(const [index,row]of basis.successors.entries()){
      const card=el('fieldset');card.dataset.successorId=row.paragraph_id;card.append(el('legend','New unit '+(index+1)));
      const extras=el('details');extras.append(el('summary','Optional explanation and writing constraints'));
      const fields=values.get(row.paragraph_id);
      for(const field of row.fields){
        if(field.type&&field.type!=='string')throw Error('The owner offered an unsupported authored field type.');
        const required=field.required||['function','proposition'].includes(field.name);
        const label=({function:'What this unit does',proposition:'Main point'})[field.name]||field.label||field.name;
        const node=input(required?card:extras,label,fields[field.name]||'',field.multiline||!['function'].includes(field.name));
        node.required=required;
        node.oninput=()=>{if(!node.required&&node.value==='')delete fields[field.name];else fields[field.name]=node.value;touch();};
      }
      if(extras.children.length>1)card.append(extras);
      units.append(card);
    }
    form.append(units);
    const attached=el('section');attached.append(el('h3','Attachments'));
    if(!basis.attachment_inventory.length)attached.append(el('p','No attachments require reassignment.','muted'));
    const predecessorById=new Map(basis.predecessors.map(row=>[row.paragraph_id,row]));
    for(const row of basis.attachment_inventory){
      const card=el('fieldset');card.dataset.attachmentId=row.id;card.append(el('legend',row.label||row.value||row.kind));inspect(card,row.read,'Inspect attachment');
      if(row.origin_unavailable)card.append(el('p','The carried attachment’s typed scope is unproved. Inspect the retained record before choosing.','muted'));
      if(row.prior_disposition){
        const witnesses=row.prior_dispositions,valid=['assign','retain-unresolved','MIXED'].includes(row.prior_disposition)&&Array.isArray(witnesses)&&witnesses.length>0&&
          new Set(witnesses.map(item=>item.paragraph_id)).size===witnesses.length&&witnesses.every(item=>predecessorById.has(item.paragraph_id)&&
            ['assign','retain-unresolved'].includes(item.disposition)&&/^ART-[a-zA-Z0-9-]+$/.test(item.intent_artifact_id||'')&&typeof item.scope_unresolved==='boolean');
        if(valid){
          card.append(el('p',row.prior_disposition==='MIXED'?'Earlier choices differ across these units. Choose explicitly for this change.':
            row.prior_disposition==='retain-unresolved'?'Previously retained for scoped review.':'Previously assigned. Choose explicitly for this change.','muted'));
          if(witnesses.some(item=>item.scope_unresolved))card.append(el('p','An earlier review had no assigned destination; its scope remains unresolved.','muted'));
          const prior=el('details');prior.append(el('summary','Previous choices and exact origins'));
          for(const witness of witnesses){const predecessor=predecessorById.get(witness.paragraph_id),label=predecessor?.values.proposition||predecessor?.values.function||witness.paragraph_id;
            prior.append(el('p',label+' · '+(witness.disposition==='assign'?'Assigned':'Retained for scoped review')+(witness.scope_unresolved?' · destination scope unresolved':'')),el('code',witness.paragraph_id),el('code',witness.intent_artifact_id));}
          card.append(prior);
        }else card.append(el('p','Previous choice details are unavailable. Inspect the exact attachment; no earlier choice was adopted.','muted'));
      }
      const choice=el('select');choice.append(el('option','Choose disposition'));
      for(const disposition of row.allowed_dispositions){const option=el('option',dispositions[disposition]);option.value=disposition;choice.append(option);}
      const previous=attachments.get(row.id);choice.value=previous?.disposition||'';labelled(card,'Keep or assign this attachment',choice);
      const destinations=el('div');card.append(destinations);
      const draw=()=>{
        destinations.replaceChildren();const selected=attachments.get(row.id);if(!selected||selected.disposition==='retain-retired')return;
        destinationChecks(destinations,selected.successor_ids,(id,checked)=>{selected.successor_ids=checked?[...selected.successor_ids,id]:selected.successor_ids.filter(value=>value!==id);touch();},row.allowed_successor_ids);
      };
      choice.onchange=()=>{const before=attachments.get(row.id);if(!choice.value)attachments.delete(row.id);else attachments.set(row.id,{attachment_id:row.id,disposition:choice.value,successor_ids:choice.value==='retain-retired'?[]:before?.successor_ids?.filter(id=>row.allowed_successor_ids.includes(id))||[]});draw();touch();};draw();attached.append(card);
    }
    form.append(attached);
    const passages=el('section');passages.append(el('h3','Saved source passages'));
    if(!basis.occurrence_inventory.length)passages.append(el('p','These planned units have no saved source passages.','muted'));
    for(const row of basis.occurrence_inventory){
      const card=el('fieldset'),line=row.line_start??row.range?.line_start;card.dataset.occurrenceId=row.id;
      card.append(el('legend',row.label||row.file.split('/').at(-1)+':'+line));inspect(card,row.read,'Inspect saved passage');
      if(row.preserved_ids?.length)card.append(el('p','Other planned-unit links in this passage are preserved.','muted'));
      const selected=occurrences.get(row.id),chosen=selected?.successor_ids||[],destinations=el('div');card.append(destinations);
      const unlinked=el('input');unlinked.type='checkbox';unlinked.checked=!!selected&&!chosen.length;
      labelled(card,'Leave these logical links unassigned and flag review',unlinked);
      const draw=()=>{destinations.replaceChildren();destinationChecks(destinations,occurrences.get(row.id)?.successor_ids||[],(id,checked)=>{
        const prior=occurrences.get(row.id)?.successor_ids||[],next=checked?[...prior,id]:prior.filter(value=>value!==id);
        if(next.length)occurrences.set(row.id,{occurrence_id:row.id,successor_ids:next});else occurrences.delete(row.id);
        unlinked.checked=false;touch();
      });};
      unlinked.onchange=()=>{if(unlinked.checked)occurrences.set(row.id,{occurrence_id:row.id,successor_ids:[]});else occurrences.delete(row.id);draw();touch();};draw();passages.append(card);
    }
    form.append(passages);
    if(retainedChoices.size){const held=el('details');held.append(el('summary','Earlier choices retained for inspection'));for(const row of retainedChoices.values())held.append(el('h4',row.label),el('pre',row.text));form.append(held);}
  }
  async function prepare(authored){
    const submission=restructurePreviewSubmission(action,project,kind,authored);
    return validateLogicalPreparation(await request(submission.url,submission.payload),{project,sectionId,kind,draft:authored});
  }
  function renderPreview(value){
    preview.replaceChildren(el('h3','Logical change preview'));
    for(const [index,row]of value.successors.entries())preview.append(el('h4','New unit '+(index+1)),el('p',row.proposition||row.values?.proposition||values.get(row.paragraph_id)?.proposition||''));
    preview.append(el('p',value.occurrence_inventory.length+' saved passage'+(value.occurrence_inventory.length===1?'':'s')+' inspected. New planned units require their own review.','muted'));
    if(value.review_obligations?.length){const details=el('details');details.append(el('summary',value.review_obligations.length+' scoped review obligations'));for(const row of value.review_obligations)details.append(el('p',row.reason||row.message||row.kind?.replaceAll('_',' ').toLowerCase()||'Inspect the scoped obligation.'));preview.append(details);}
    if(!value.ready)say('Complete the required fields and assignments before applying. '+value.needs_input.map(row=>row.reason||row.kind.replaceAll('_',' ').toLowerCase()).join('; '),true);
    else say('Preview ready. Applying records new logical identities and their explicit assignments.');
  }
  function offerFresh(value){
    stale=value;prepared=null;preview.replaceChildren(el('p','The inspected source or plan basis changed. Your choices remain here.'),button('Adopt refreshed basis',()=>{
      adopt(stale);uncertain=false;persist();say('Refreshed basis adopted. Inspect the retained choices and preview again.');
    }));say('Inspect and adopt the refreshed basis before applying.',true);
  }
  const review=button('Preview logical change',async()=>{
    if(settled||!basis)return;if(uncertain)throw Error('Inspect the current reader-plan operation before another application.');const value=await prepare(draft());
    if(!equal(value.guards,basis.guards)||!equal(keySet(value.successors),keySet(basis.successors))||!equal(keySet(value.attachment_inventory),keySet(basis.attachment_inventory))||!equal(keySet(value.occurrence_inventory),keySet(basis.occurrence_inventory))){
      offerFresh(value);return;
    }
    prepared=value;renderPreview(value);apply.disabled=!value.ready||!value.apply_action||value.apply_action.permitted===false;
  });
  const inspectBasis=button('Inspect refreshed basis',async()=>{
    if(settled||!basis)return;
    if(uncertain){
      const current=await read(plan.read_handle),section=current.sections?.find(row=>row.id===sectionId),pending=section?.paragraph_plan?.pending_restructures;
      if(current.project!==project||!Array.isArray(pending))throw Error('The current structural publication state is unavailable. Inspect the reader plan without repeating this operation.');
      if(pending.length){outcome.replaceChildren(el('p','A retained structural record needs attention before another application.','error'));for(const row of pending)inspect(outcome,row.read_handle,'Inspect retained structural record');return;}
    }
    const current=await prepare({paragraph_ids:[...basis.draft.paragraph_ids],...(kind==='logical-split'?{successor_count:basis.successors.length}:{})});
    if(!uncertain&&equal(current.guards,basis.guards)){say('The inspected basis is still current. Your authored choices remain here.');return;}
    offerFresh(current);
  });
  async function effect(submission,options){
    let result;try{result=await request(submission.url,submission.payload);}catch(error){
      if(error.result?.schema_version!==RESTRUCTURE_SCHEMA){
        if(!error.result?.refused){
          uncertain=true;prepared=null;
          outcome.replaceChildren(el('p','The operation has no verified acknowledgement. Inspect its current reader-plan record before another application.','error'));
          inspect(outcome,plan?.read_handle,'Inspect current reader plan');
        }
        throw error;
      }
      result=error.result;
    }
    let observed;
    try{observed=validateRestructureEffect(result,{project,...options});}
    catch(error){uncertain=true;prepared=null;outcome.replaceChildren(el('p','The structural acknowledgement could not be verified. Inspect its saved record before another application.','error'));inspect(outcome,result.read_handle||plan.read_handle,'Inspect structural record');throw error;}
    settled=true;dirty=false;prepared=null;review.disabled=true;apply.disabled=true;forget();
    for(const node of form.querySelectorAll('input,textarea,select'))node.disabled=true;
    outcomeController?.destroy();outcome.replaceChildren();
    outcomeController=renderRestructureOutcome(outcome,result,{project,isCurrent:fresh,onRead:inspectInput,
      onInspectReconciliation:(handle,retained)=>openMetadataReconciliation({project,handle,retained,request,onRead:inspectInput,opener:document.activeElement,isCurrent:fresh,onSaved:async next=>{outcomeController?.destroy();outcome.replaceChildren();outcomeController=renderRestructureOutcome(outcome,next,{project,isCurrent:fresh,onRead:inspectInput});await onSaved(next);if(fresh())say('Reader record reconciled. Later text and review obligations remain.');}}),
      onRecovery:async(action,prior)=>perform(()=>effect(restructureFollowThroughSubmission(action,project,prior),{prior}))});
    if(result.undo_action){outcome.append(button('Undo this logical change',()=>effect(restructureFollowThroughSubmission(result.undo_action,project,result,'undo-restructure'),{prior:result,inverse:true})));}
    for(const node of outcome.querySelectorAll('button'))node.disabled=true;
    try{await onSaved(result);}catch(error){say('The operation is recorded. View refresh failed: '+error.message+' Do not repeat the action.',true);return;}
    say(observed.complete?'Logical change and required records saved.':observed.sourceSettled?
      'The operation is retained. Finish its remaining record steps without repeating the source change.':
      'The source outcome needs inspection. Keep the retained operation and do not repeat the write.',!observed.complete);
  }
  const apply=button(kind==='logical-split'?'Apply logical split':'Apply logical combine',async()=>{
    if(!prepared?.ready||settled||uncertain||stale)throw Error('Preview the complete current logical change first.');
    await effect(restructureApplySubmission(prepared,project),{preview:prepared});
  });apply.disabled=true;
  const close=button('Close',()=>{if(dirty&&!settled){say('Your choices remain open. Use Cancel local choices to discard them explicitly.',true);return;}dialog.close();});
  review.disabled=true;inspectBasis.disabled=true;
  controls.append(review,inspectBasis,apply,button('Cancel local choices',()=>{dirty=false;forget();dialog.close();}),close);
  dialog.addEventListener('cancel',event=>{if(busy||dirty&&!settled){event.preventDefault();say('Your local choices are retained; cancel them explicitly before closing.',true);}});
  dialog.addEventListener('close',()=>{alive=false;outcomeController?.destroy();dialog.remove();if(opener?.isConnected)opener.focus({preventScroll:true});});
  showReaderDialog(dialog,opener);
  let held=null;
  try{
    held=JSON.parse(storage?.getItem(storageKey)||'null');
    if(held){
      if(held.project!==project||held.sectionId!==sectionId||held.kind!==kind)throw Error('The retained logical draft belongs to another scope.');
      validateLogicalPreparation(held.basis,{project,sectionId,kind});
      for(const [map,key]of [[values,'values'],[attachments,'attachments'],[occurrences,'occurrences'],[retainedChoices,'retainedChoices']]){
        if(!Array.isArray(held[key]))throw Error('The retained logical choices are unreadable.');for(const [id,value]of held[key])map.set(id,clone(value));
      }
      basis=held.basis;dirty=true;renderForm();
    }
  }catch(error){held=null;say('A local logical draft could not be restored. Its stored copy was left untouched: '+error.message,true);}
  async function start(ids){
    const value=await prepare({paragraph_ids:ids,...(kind==='logical-split'?{successor_count:2}:{})});if(!fresh())return;
    if(held&&!equal(held.basis.guards,value.guards)){offerFresh(value);review.disabled=false;inspectBasis.disabled=false;say('Recovered local choices need an explicit refreshed-basis adoption before applying.',true);held=null;return;}
    adopt(value);review.disabled=false;inspectBasis.disabled=false;say('Describe the new units, then assign the scoped attachments and saved passages.');
    if(held){say('Recovered local logical choices. Preview them again before applying.');held=null;}
  }
  try{
    if(held)await start(held.basis.draft.paragraph_ids);
    else if(kind==='logical-merge'){
      review.disabled=true;const selected=new Set(action.payload.draft.paragraph_ids),items=new Map();let next=action.choices_read||null;
      const list=el('section');setup.append(el('h3','Choose planned units to combine'),list);
      const add=rows=>{for(const row of rows){if(items.has(row.paragraph_id))continue;items.set(row.paragraph_id,row);const checkbox=el('input');checkbox.type='checkbox';checkbox.checked=selected.has(row.paragraph_id);checkbox.disabled=action.payload.draft.paragraph_ids.includes(row.paragraph_id);labelled(list,row.proposition||row.function||'Planned unit',checkbox);checkbox.onchange=()=>{if(checkbox.checked)selected.add(row.paragraph_id);else selected.delete(row.paragraph_id);};}};
      add(plan?.paragraphs?.items||[paragraph]);
      const more=button('More planned units',async()=>{const value=await read(next),section=value.sections?.find(row=>row.id===sectionId);if(value.project!==project||!section?.paragraph_plan)throw Error('The active planned-unit choices changed.');add(section.paragraph_plan.paragraphs.items);next=section.paragraph_plan.paragraphs.next_read;more.hidden=!next;});more.hidden=!next;
      setup.append(more,button('Continue with selected units',async()=>{if(selected.size<2)throw Error('Select at least two planned units.');await start([...selected]);review.disabled=false;}));
    }else await start(action.payload.draft.paragraph_ids);
  }catch(error){say(error.message,true);}
  return dialog;
}
