// profile-preferences.mjs — effective profile preferences and their saved suggestions (M5 C8).
// Purpose: read the effective preferences of one (family, scope[, profile]), list saved
//   suggestions as RELATION ROWS (kind Applied/Suggestion, the producing project, a standing
//   chip; Compare is the only door), compare one suggestion against the current text and apply
//   it from the comparison; confirm exact fields as the author's own (architecture only).
// Ownership: /work/profiles (summary, content, candidates, candidate, propose/apply/confirm);
//   generation is a prepared conversation request in a producing project, never a write here.
// Public contract: mountProfilePreferences(host,{project,family,scope,profile,request,
//   onChanged,onGenerate,...}); inspectProfilePreferences; readProfileText;
//   profileActionPayload; profileGenerationIntent / URL / Coordinates.
// Currentness: a comparison re-reads the candidate after its parts and refuses when the
//   effective identity moved; an uncertain apply offers Inspect saved outcome, never a replay.
// Storage: none.
import {relationList,declareControl} from './workspace-presentation.mjs';
/* Profile comparison/application delegates to the existing typed owner.
 * No provider call, configuration store, source editor or hidden project choice.
 */
const el=(tag,text='',cls='')=>{const node=document.createElement(tag);node.textContent=text;node.className=cls;return node;};
const identity=value=>JSON.stringify([value.family,value.scope,value.profile,value.candidate_ref?.id,value.candidate_ref?.version,value.revision]);
const bytes=text=>new TextEncoder().encode(text);
const route=(project,payload)=>'/work/profiles?'+new URLSearchParams({...project?{project}:{},...Object.fromEntries(Object.entries(payload).map(([key,value])=>[key,typeof value==='object'?JSON.stringify(value):String(value)]))});
const ownerURL=(value,path)=>{const base=new URL(globalThis.location?.href||'http://local/'),url=new URL(value,base);if(url.origin!==base.origin||url.pathname!==path||url.username||url.password||url.hash||path.endsWith('/change')&&url.search)throw Error('The profile handle does not name the same-origin profile owner.');return url.pathname+url.search;};

export async function readProfileText(first,request){
  let value=first,offset=0,total=null,hash=null,binding=identity(first),chunks=[];
  while(true){
    const coverage=value.coverage;
    if(!Number.isSafeInteger(coverage?.total)||coverage.total<0||coverage.total>2_000_000)throw Error('The declared profile text size exceeds its bounded owner contract.');
    if(identity(value)!==binding||coverage?.unit!=='utf8-bytes'||coverage.start!==offset||coverage.end<offset||bytes(value.content||'').length!==coverage.end-offset)throw Error('The profile text identity or coverage changed. Your draft is retained.');
    if(total===null){total=coverage.total;hash=coverage.sha256;}
    if(total!==coverage.total||hash!==coverage.sha256||coverage.end>total)throw Error('The profile text changed while reading. Inspect it again.');
    chunks.push(value.content||'');offset=coverage.end;
    if(offset===total){
      if(value.next_read)throw Error('The profile text continuation disagrees with its complete coverage.');
      const text=chunks.join(''),observed='sha256:'+Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes(text))),item=>item.toString(16).padStart(2,'0')).join('');
      if(observed!==hash)throw Error('The complete profile text does not match its retained identity.');
      return text;
    }
    if(!value.next_read?.http?.url||coverage.end===coverage.start)throw Error('This profile text is incomplete; retain the draft and inspect again.');
    value=await request(ownerURL(value.next_read.http.url,'/work/profiles'));
  }
}

export function profileActionPayload(action,authored={}){
  if(action?.operation!=='profile_change'||!action.permitted||action.http?.method!=='POST'||!action.http.url||!action.payload)throw Error(action?.reason||'This profile action is not available.');
  ownerURL(action.http.url,'/work/profiles/change');
  const base=action.payload;
  if(!base.project||!['propose','apply','confirm'].includes(base.action)||base.action==='apply'&&(!base.candidate_ref?.id||!base.candidate_ref?.version)||base.action!=='apply'&&(!['architecture','voice'].includes(base.family)||!['workspace','project'].includes(base.scope)||base.family==='architecture'&&base.scope!=='workspace'||!base.guards?.profile_input_revision))throw Error('The profile action has incomplete owner identity or scope.');
  const forbidden=['project','family','scope','profile','guards','candidate_ref','action'];
  if(Object.keys(authored).some(key=>forbidden.includes(key)))throw Error('Authored profile fields cannot replace the owner action identity or guards.');
  for(const key of action.required_fields||[])if(!(key in authored))throw Error('Complete the profile action field: '+key);
  return {...structuredClone(action.payload),...structuredClone(authored)};
}

export function profileGenerationIntent(project,basis){
  const {family,scope}=basis,action=basis.propose_action;
  if(!project||!['architecture','voice'].includes(family)||!['workspace','project'].includes(scope)||family==='architecture'&&scope!=='workspace'||!action?.permitted||action.payload?.project!==project)throw Error('Choose the actual project and inspected profile scope before generating a suggestion.');
  const reading={family,scope,view:'content',...(family==='voice'&&scope==='workspace'?{profile:basis.profile}:{})};
  const instruction='Generate a '+(scope==='workspace'?'shared workspace ':'project ')+family+' preference suggestion. Read the effective profile using profile '+JSON.stringify(reading)+'. '+(family==='architecture'?'Its content_contract declares the serialized document schema, example, starter and delivery coverage even when the current profile is absent. Whole-paper planning uses all fields; only its known palette guides relevant sections. Custom fields remain valid whole-paper preferences. Follow that owner contract and current profile_change help. ':'')+'Read only explicitly selected source material. Use profile_change with this exact owner action base '+JSON.stringify(action.payload)+', supplying change and a concise reason. Save an immutable candidate for human comparison; do not apply it, claim personal author confirmation or edit manuscript prose.';
  return {project,family,scope,profile:basis.profile,instruction};
}

export function profileGenerationURL(intent){
  if(!intent?.project||!['architecture','voice'].includes(intent.family)||!['workspace','project'].includes(intent.scope)||intent.family==='architecture'&&intent.scope!=='workspace')throw Error('The generation destination is not an exact supported profile context.');
  return '/project?'+new URLSearchParams({workspace:'writing',corpus:intent.project,view:'overview',profile_generation:intent.family,profile_scope:intent.scope,...(intent.family==='voice'&&intent.scope==='workspace'?{profile_path:intent.profile}:{})});
}

export function profileGenerationCoordinates(parameters){
  if(!parameters.has('profile_generation'))return null;
  const family=parameters.get('profile_generation'),scope=parameters.get('profile_scope');
  if(!['architecture','voice'].includes(family)||!['workspace','project'].includes(scope)||family==='architecture'&&scope!=='workspace')throw Error('The requested profile generation scope is unsupported.');
  const profile=parameters.get('profile_path');
  if(profile&&!(family==='voice'&&scope==='workspace'&&profile.startsWith('profiles/voice/')&&profile.endsWith('.md')&&!profile.split('/').includes('..')&&!profile.includes('\\')))throw Error('The requested shared voice profile has invalid owner coordinates.');
  return {family,scope,view:'summary',...(profile?{profile}:{})};
}

function showDelivery(host,delivery){
  if(!delivery)return;
  host.append(el('p',delivery.whole_paper+' '+delivery.sections+' '+delivery.taste,'muted'));
  const palette=el('details');palette.append(el('summary','Section preference palette'));
  for(const row of delivery.section_fields||[])palette.append(el('p',row.label+' · '+row.contexts.join(', '),'muted'));
  host.append(palette);
}
function showValues(host,family,scope,text,delivery=null){
  if(family==='architecture'){
    const document=JSON.parse(text||'{"profile":{}}');
    for(const [name,value]of Object.entries(document.profile||{})){
      const section=el('section');section.append(el('h5',name.replaceAll('_',' ')),el('p',value.summary||''));
      if(delivery){const selected=delivery.section_fields?.find(row=>row.id===name);section.append(el('p',selected?'Whole paper · Relevant sections: '+selected.contexts.join(', '):'Whole-paper preference · No section-specific delivery','muted'));}
      if(value.evidence){const evidence=el('details');evidence.append(el('summary','Evidence and qualification'),el('p',value.evidence.observation||''));for(const source of value.evidence.sources||[])evidence.append(el('p',source,'muted'));section.append(evidence);}
      host.append(section);
    }
  }else if(scope==='project'){
    const value=JSON.parse(text||'{}');for(const [name,label]of [['profile','Selected voice profile'],['genre','Genre'],['guidance','Project guidance']])if(name in value)host.append(el('h5',label),el('p',value[name]||'Inherit the document default'));
  }else{const value=el('pre',text,'profile-preferences-text');value.style&&(value.style.whiteSpace='pre-wrap');host.append(value);}
}

export async function mountProfilePreferences(host,{project=null,family,scope='workspace',profile=null,request,onDirty=()=>{},onChanged=()=>{},onGenerate=null,onDiscuss=null,getProjects=null,enableEdit=family==='architecture'}={}){
  let alive=true,current=null,selected=null,draftDirty=false,busy=false,producer=project,document=null,form=null,editAction=null;
  const live=()=>alive&&host.isConnected!==false;
  const note=el('p','','work-status');note.setAttribute('role','status');
  const heading=el('h4',family==='architecture'?'Structural writing preferences':scope==='project'?'Project preference suggestions':'Shared voice suggestions');
  const scopeNote=el('p',scope==='workspace'?'These preferences are shared across the workspace.':'These preferences affect only this project.','muted');
  const tools=el('div','','work-actions'),values=el('section'),catalogue=el('section'),editing=el('section'),comparison=el('section');editing.hidden=comparison.hidden=true;
  host.replaceChildren(heading,scopeNote,note,tools,values,catalogue,editing,comparison);
  const message=(text,error=false)=>{note.textContent=text;note.className=error?'work-status error':'work-status';};
  const button=(label,fn,cls='',id=null)=>{const node=el('button',label);if(id)declareControl(node,id);node.type='button';node.onclick=async()=>{if(busy)return;busy=true;lock(true);try{await fn();}catch(error){if(live())message(error.message,true);}finally{busy=false;lock(false);}};return node;};
  const disabled=new Map();
  const lock=value=>{if(value){for(const node of host.querySelectorAll?.('input,textarea,select,button')||[]){if(!disabled.has(node))disabled.set(node,!!node.disabled);node.disabled=true;}}else{for(const [node,original]of disabled)node.disabled=original;disabled.clear();}};
  const query=(view,extra={})=>({family,scope,view,...(profile&&family==='voice'&&scope==='workspace'?{profile}:{}),...extra});
  async function content(payload,context=producer||project,expected=null){const first=await request(route(context,payload));if(expected&&first.revision!==expected)throw Error('Effective preferences changed before their text was read. Inspect again; your draft is retained.');return readProfileText(first,request);}
  async function candidates(){
    const value=await request(route(project,query('candidates',{limit:20})));if(!live())return;
    catalogue.replaceChildren(el('h5','Saved suggestions'));
    if(!value.candidates?.length)catalogue.append(el('p','No saved suggestions for this profile.','muted'));
    // candidates as relation rows (M5 C8): kind, the producing project as the object, a standing
    // chip; Compare is the only door and Apply appears only inside a comparison
    const rows=(value.candidates||[]).map(row=>({kind:row.status==='APPLIED'?'Applied':'Suggestion',label:(row.reason||'Saved suggestion')+' · '+(row.custody_project||row.project),run:()=>compare(row),title:'Compare before applying',chip:row.status==='APPLIED'?{label:'applied',tone:'historical'}:{label:'saved',tone:'neutral'},onError:error=>message(error.message,true)}));
    if(rows.length){const list=relationList(rows);list.setAttribute('data-control','profile:candidate');catalogue.append(list);}
    if(value.pagination?.returned<value.pagination?.total)catalogue.append(el('p','Showing the latest '+value.pagination.returned+' suggestions. Older exact records remain in Activity.','muted'));
  }
  async function refresh(){
    const value=await request(route(project,query('summary')));if(!live())return;
    if(value.family!==family||value.scope!==scope)throw Error('The profile owner returned a different effect scope.');
    if(draftDirty&&current?.revision!==value.revision){message('Saved preferences changed. Your draft and its original basis are retained; compare before applying.',true);return;}
    current=value;
    tools.replaceChildren(button('Refresh preferences',refresh,'','preferences:refresh'),button('Read effective preferences',readEffective,'','preferences:read-effective'),button('Generate suggestion',generate,'','preferences:generate'));
    if(enableEdit)tools.append(button(current.status==='ABSENT'?'Write structural preferences':'Edit structural preferences',edit,'','preferences:edit'));
    await candidates();
  }
  async function readEffective(){
    const context=producer||project,basis=await request(route(context,query('summary')));
    const text=await content(query('content'),context,basis.revision);if(!live())return;values.replaceChildren();showDelivery(values,basis.content_contract?.delivery);showValues(values,family,scope,text,basis.content_contract?.delivery);
    if(family==='architecture')paintConfirmation(values,basis);
    message('These are the current saved preferences. Applying a suggestion does not confirm personal authorship.');
  }
  function paintConfirmation(container,basis){
    const choices=[];const area=el('section');area.append(el('p','Confirm selected exact fields only when they reflect your own preferences. Applying a suggestion and confirming it are separate actions.','muted'));
    for(const [id,value]of Object.entries(basis.effective_values||{})){
      const label=el('label'),box=el('input');box.type='checkbox';box.value=id;box.setAttribute('aria-label','Confirm '+id.replaceAll('_',' '));label.append(box,el('span',id.replaceAll('_',' ')+' · '+(value.confirmed_his?'Recorded author confirmation':value.historical_confirmation_assertion?'Historical assertion; not personally confirmed':'Not personally confirmed')));area.append(label);choices.push(box);
    }
    if(basis.confirm_action?.permitted)area.append(button('Confirm selected preferences as mine',async()=>{
      const fields=choices.filter(node=>node.checked).map(node=>node.value);if(!fields.length)throw Error('Select the exact fields you want to confirm.');
      const result=await request(basis.confirm_action.http.url,profileActionPayload(basis.confirm_action,{fields,reason:'I confirm that these selected exact preferences are mine.'}));
      if(result.family!==family||result.scope!==scope)throw Error('The confirmation returned a different profile.');await refresh();await readEffective();await onChanged(result);message('Selected exact fields now have recorded author confirmation.');
    }));
    else if(!producer&&getProjects)area.append(button('Choose project context for confirmation',()=>chooseProducer(readEffective)));
    container.append(area);
  }
  async function chooseProducer(continuation=generate){
    if(producer)return producer;
    if(!getProjects)throw Error('Choose an existing project conversation to generate shared preferences. The profile effect remains workspace-wide.');
    const response=await getProjects();if(!live())return null;
    const choices=Array.isArray(response)?response:response.projects||[];
    editing.hidden=false;editing.replaceChildren(el('h5','Choose the producing project'),el('p','The conversation and saved suggestion belong to this project. Applying the shared profile still affects the workspace.','muted'));
    const select=el('select');select.setAttribute('aria-label','Producing project');select.append(el('option','Choose an existing project'));select.firstElementChild&&(select.firstElementChild.value='');
    for(const row of choices){const option=el('option',row.title||row.name);option.value=row.name||row.project;select.append(option);}editing.append(select,button('Use this project context',async()=>{if(!select.value||!choices.some(row=>(row.name||row.project)===select.value))throw Error('Choose an existing project explicitly.');producer=select.value;editing.hidden=true;await continuation();}));
    return null;
  }
  async function generate(){
    const selectedProject=await chooseProducer();if(!selectedProject)return;
    if(!onGenerate&&!onDiscuss)throw Error('Open the chosen project conversation to generate this suggestion.');
    const basis=await request(route(selectedProject,query('summary')));if(!live())return;
    const intent=profileGenerationIntent(selectedProject,basis);
    if(onGenerate)await onGenerate(intent);else if(selectedProject===project)await onDiscuss(intent.instruction);else throw Error('Open the explicitly chosen project conversation before generating the shared suggestion.');
    message('Generation request prepared in '+selectedProject+'. After it finishes, refresh suggestions here to compare the saved candidate.');
  }
  async function compare(row){
    const context=row.custody_project||row.project;if(!context||!row.candidate_ref)throw Error('This suggestion has no exact producing project and candidate identity.');
    const payload={view:'candidate',candidate_ref:row.candidate_ref};const value=await request(route(context,payload));
    if(value.family!==family||value.scope!==scope||profile&&value.profile!==profile)throw Error('This suggestion belongs to another profile scope.');
    const [before,after]=await Promise.all(['current','proposed'].map(part=>content({...payload,part},context)));
    const checked=await request(route(context,payload));if(!live())return;
    if(identity(checked.current)!==identity(value.current))throw Error('Effective preferences changed during comparison. The exact suggestion is retained; compare again.');
    selected=checked;comparison.hidden=false;comparison.replaceChildren(el('h5','Compare saved suggestion'),el('p',checked.reason||''),el('p','Producing project: '+context+' · '+(scope==='workspace'?'workspace effect':'project effect'),'muted'));
    showDelivery(comparison,checked.delivery);
    const currentPane=el('section'),proposedPane=el('section');currentPane.append(el('h5','Current preferences'));proposedPane.append(el('h5','Proposed preferences'));showValues(currentPane,family,scope,before,checked.delivery);showValues(proposedPane,family,scope,after,checked.delivery);comparison.append(currentPane,proposedPane);
    const standing={CURRENT:'Inspected inputs are current.',APPLIED_CURRENT:'This suggestion was applied; the effective preferences match its applied version.',APPLIED_SUPERSEDED:'This suggestion was applied historically. The effective preferences have since changed.'};
    comparison.append(el('p',standing[checked.currentness]||checked.recovery||'The original inputs have changed. This exact suggestion is retained; it cannot be silently rebased.','muted'));
    if(checked.apply_action?.permitted)comparison.append(button(checked.application_tracking==='INCOMPLETE'?'Complete preference tracking':'Apply this preference',async()=>{
      let result;
      try{result=await request(checked.apply_action.http.url,profileActionPayload(checked.apply_action));}
      catch(error){
        // Inspect a possibly saved effect; never turn an uncertain write into a
        // generic repeat. The next button comes from the fresh exact owner read.
        comparison.replaceChildren(el('p','The application outcome needs inspection. Your exact suggestion is retained.','error'),button('Inspect saved outcome',()=>compare(row)));
        message(error.message,true);return;
      }
      if(JSON.stringify(result.candidate_ref)!==JSON.stringify(checked.candidate_ref)||['family','scope','profile'].some(key=>result[key]!==checked[key]))throw Error('The application acknowledgement names a different candidate or profile scope.');
      if(!result.application_id){comparison.replaceChildren(el('p','The profile outcome is retained and needs inspection.'),button('Inspect saved outcome',()=>compare(row)));return;}
      selected=result;draftDirty=false;onDirty(false);editing.hidden=true;
      comparison.replaceChildren(el('p','Preference applied; its exact outcome is retained.'),button('Inspect applied preference',()=>compare(result)));
      try{await refresh();await readEffective();await onChanged(result);message(result.metadata_only?'Preference tracking completed without rewriting the profile.':'Preference applied. Read the effective values and inspect the next project conversation’s instructions.');}
      catch(error){message('Preference applied, but its effective view could not reload. Refresh preferences to inspect it. '+error.message,true);}
    }));
    comparison.append(button('Close comparison',()=>{comparison.hidden=true;}));
  }
  async function edit(){
    if(draftDirty&&form){editing.hidden=false;return;}
    const context=await chooseProducer(edit);if(!context)return;
    const basis=await request(route(context,query('summary')));editAction=basis.propose_action;
    const text=await content(query('content'),context,basis.revision);
    if(!text&&basis.content_contract?.schema_version!=='laplace.architecture-profile-content/1')throw Error('The architecture owner has not supplied its content contract. Inspect it before authoring a preference.');
    document=text?JSON.parse(text):structuredClone(basis.content_contract.starter);if(!live())return;
    editing.hidden=false;editing.replaceChildren(el('h5','Edit structural preferences'));form=el('form');const fields=el('div');form.append(fields);let entries=[];
    const add=(name,value)=>{
      const section=el('section'),label=el('label','Preference name'),nameInput=el('input');nameInput.value=name;nameInput.disabled=!!name;nameInput.setAttribute('aria-label','Preference name');label.append(nameInput);
      const summaryLabel=el('label','What to prefer'),summary=el('textarea');summary.value=value.summary||'';summary.rows=4;summary.setAttribute('aria-label','What to prefer');summaryLabel.append(summary);
      const evidenceLabel=el('label','Evidence and qualification'),evidence=el('textarea');evidence.value=value.evidence?.observation||'';evidence.setAttribute('aria-label','Evidence and qualification');evidenceLabel.append(evidence);
      const entry={nameInput,summary,evidence,value};entries.push(entry);section.append(label,summaryLabel,evidenceLabel,button('Remove preference',()=>{entries=entries.filter(row=>row!==entry);section.remove();draftDirty=true;onDirty(true);}));fields.append(section);
    };
    for(const [name,value]of Object.entries(document.profile||{}))add(name,value);
    const reasonLabel=el('label','Reason for this preference'),reason=el('textarea');reason.required=true;reason.setAttribute('aria-label','Reason for this preference');reasonLabel.append(reason);
    form.append(button('Add preference',()=>{add('',{});draftDirty=true;onDirty(true);}),reasonLabel,button('Preview my changes',async()=>{
      if(!reason.value.trim())throw Error('Record a reason for this preference.');const next=structuredClone(document);next.profile={};
      for(const row of entries){const name=row.nameInput.value.trim();if(!name||!row.summary.value.trim()||name in next.profile)throw Error('Every preference needs a unique name and nonempty description.');next.profile[name]={...row.value,summary:row.summary.value,...(row.evidence.value||row.value.evidence?{evidence:{...row.value.evidence,observation:row.evidence.value}}:{})};}
      const candidate=await request(editAction.http.url,profileActionPayload(editAction,{change:{content:JSON.stringify(next)},reason:reason.value}));
      selected=candidate;draftDirty=false;onDirty(false);await candidates();
      await compare(candidate);message('Your exact draft is saved as a suggestion. Compare it before applying.');
    }),button('Cancel local edit',()=>{draftDirty=false;onDirty(false);editing.hidden=true;form=null;}));
    form.oninput=()=>{draftDirty=true;onDirty(true);};form.onsubmit=event=>event.preventDefault();editing.append(form);
  }
  try{await refresh();}catch(error){message('Profile suggestions are unavailable: '+error.message,true);}
  const closeReady=()=>{if(busy){message('The profile action is still being recorded.');return false;}if(draftDirty){message('Save your draft as a suggestion or cancel the local edit before closing.');return false;}return true;};
  return {refresh,compare,closeReady,destroy(){alive=false;},get hasDraft(){return draftDirty;},get pending(){return busy;},get selectedCandidate(){return selected;}};
}

export async function inspectProfilePreferences({project,family='architecture',scope='workspace',profile=null,initialCandidate=null,request,opener,onChanged,onGenerate,onDiscuss,getProjects}={}){
  const dialog=el('dialog','','spine-binding-dialog'),host=el('section');dialog.append(host);
  document.body.append(dialog);
  const controller=await mountProfilePreferences(host,{project,family,scope,profile,request,onChanged,onGenerate,onDiscuss,getProjects});
  if(initialCandidate)await controller.compare(initialCandidate);
  const close=el('button','Close');close.type='button';close.onclick=()=>{if(controller.closeReady())dialog.close();};dialog.append(close);
  dialog.addEventListener('cancel',event=>{if(!controller.closeReady())event.preventDefault();});
  dialog.addEventListener('close',()=>{controller.destroy();dialog.remove();if(opener?.isConnected)opener.focus({preventScroll:true});});
  dialog.showModal();return {dialog,controller};
}
